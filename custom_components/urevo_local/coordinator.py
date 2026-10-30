"""Read-only connection lifecycle; commands are never replayed on reconnect."""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from bleak.backends.characteristic import BleakGATTCharacteristic
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

from bleak import BleakClient
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .protocol import (
    CONTROL,
    DATA,
    FEATURE,
    SPEED_RANGE,
    STATUS,
    UREVO_DATA,
    UREVO_QUERY,
    UREVO_SUBSCRIBE,
    decode_steps,
    decode_urevo_us,
    decode_urtm041,
    speed_command,
)

_LOGGER = logging.getLogger(__name__)
FRESH_SECONDS = 30


class UrevoCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="urevo_local",
            config_entry=entry,
            update_interval=timedelta(seconds=15),
        )
        self.entry = entry
        self.address = entry.data["address"]
        self.client: BleakClient | None = None
        self.values: dict[str, float | str] = {}
        self.seen: dict[str, float] = {}
        self.telemetry_frames: dict[str, str] = {}
        self.limits: tuple[float, float, float] | None = None
        self.speed_supported = False
        self.control_supported = False
        self._control_write_response = True
        self._steps_query_response: bool | None = None
        self._steps_query_at = float("-inf")
        self.armed_until = 0
        self._pending: tuple[int, asyncio.Future[int]] | None = None
        self._command_lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()
        self._closing = False
        self._expiry_handle: asyncio.TimerHandle | None = None
        self._safety_revision = 0

    @property
    def armed(self) -> bool:
        return (
            self.entry.options.get("allow_control", False)
            and time.monotonic() < self.armed_until
        )

    def fresh(self, key: str) -> bool:
        return (
            self.client is not None
            and self.client.is_connected
            and time.monotonic() - self.seen.get(key, float("-inf")) < FRESH_SECONDS
        )

    def _publish(self) -> None:
        # Local state changes must not clear connection errors or postpone polling.
        if not self._closing:
            self.data = dict(self.values)
            self.async_update_listeners()
            self._schedule_expiry()

    def _schedule_expiry(self) -> None:
        if self._expiry_handle is not None:
            self._expiry_handle.cancel()
            self._expiry_handle = None
        now = time.monotonic()
        deadlines = [stamp + FRESH_SECONDS for stamp in self.seen.values()]
        deadlines.append(self.armed_until)
        future = [deadline for deadline in deadlines if deadline > now]
        if future and not self._closing:
            self._expiry_handle = self.hass.loop.call_later(
                min(future) - now, self._expire
            )

    def _expire(self) -> None:
        self._expiry_handle = None
        if not self.fresh("speed") or not self.armed:
            self.armed_until = 0
        self._publish()

    def _notification(
        self,
        client: BleakClient,
        callback: Callable[[BleakGATTCharacteristic, bytearray], None],
    ) -> Callable[[BleakGATTCharacteristic, bytearray], None]:
        def received(sender, payload):
            if not self._closing and self.client is client and client.is_connected:
                callback(sender, payload)

        return received

    async def _disconnect(self, client: BleakClient) -> None:
        if self.client is client:
            self._disconnected(client)
        try:
            async with asyncio.timeout(10):
                await client.disconnect()
        except Exception:
            _LOGGER.warning("Bluetooth disconnect failed", exc_info=True)

    def _disconnected(self, client: BleakClient) -> None:
        if client is not self.client:
            return
        self.client = None
        self._safety_revision += 1
        self.armed_until = 0
        self.control_supported = False
        self._steps_query_response = None
        self.seen.clear()
        if self._pending and not self._pending[1].done():
            self._pending[1].set_exception(
                HomeAssistantError("Treadmill disconnected; command was not retried")
            )
        self._schedule_expiry()
        if not self._closing:
            self.async_set_update_error(UpdateFailed("Treadmill disconnected"))

    def _data(self, sender: BleakGATTCharacteristic, payload: bytearray) -> None:
        try:
            values = decode_urtm041(bytes(payload))
        except ValueError:
            _LOGGER.debug(
                "Discarded malformed treadmill data: %s", bytes(payload).hex()
            )
            return
        self.values.update(values)
        self.telemetry_frames["ftms"] = bytes(payload).hex()
        self.seen.update({key: time.monotonic() for key in values})
        self._publish()

    def _status(self, sender: BleakGATTCharacteristic, payload: bytearray) -> None:
        if not payload:
            return
        if payload[0] in (1, 2, 3, 0xFF):
            self._safety_revision += 1
            self.armed_until = 0
        # A status message is not a speed measurement.
        self.values["machine_status"] = bytes(payload).hex()
        self._publish()

    def _steps(self, sender: BleakGATTCharacteristic, payload: bytearray) -> None:
        try:
            steps, elapsed = decode_steps(bytes(payload))
        except ValueError:
            _LOGGER.debug("Discarded UREVO step frame: %s", bytes(payload).hex())
            return
        self.values.update(steps=steps, steps_elapsed=elapsed)
        self.telemetry_frames["urevo"] = bytes(payload).hex()
        now = time.monotonic()
        self.seen.update(steps=now, steps_elapsed=now)
        # This firmware selects either FTMS or proprietary reporting. The US
        # profile is identified by its captured FTMS range, never HA display units.
        if self.limits == (0.96, 6.43, 0.32):
            try:
                values = decode_urevo_us(bytes(payload))
            except ValueError:
                _LOGGER.debug("Invalid US UREVO measurements: %s", bytes(payload).hex())
            else:
                self.values.update(values)
                self.seen.update({key: now for key in values})
        self._publish()

    async def _request_steps(self, client: BleakClient) -> None:
        self._steps_query_at = time.monotonic()
        async with asyncio.timeout(5):
            await client.write_gatt_char(
                UREVO_QUERY, UREVO_SUBSCRIBE, response=self._steps_query_response
            )

    def _response(self, sender: BleakGATTCharacteristic, payload: bytearray) -> None:
        _LOGGER.debug("FTMS control response: %s", bytes(payload).hex())
        if len(payload) < 3 or payload[0] != 0x80 or self._pending is None:
            return
        opcode, future = self._pending
        if payload[1] == opcode and not future.done():
            future.set_result(payload[2])

    async def _connect(self) -> None:
        async with self._connect_lock, asyncio.timeout(30):
            if self._closing:
                raise UpdateFailed("Integration is shutting down")
            if self.client and self.client.is_connected:
                return
            device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if device is None:
                raise UpdateFailed("Walking pad is not visible to a Bluetooth adapter")
            self.armed_until = 0
            self.seen.clear()
            self.values.clear()
            self.telemetry_frames.clear()
            self.limits = None
            self.speed_supported = False
            self.control_supported = False
            client = await establish_connection(
                BleakClient,
                device,
                "UREVO walking pad",
                disconnected_callback=self._disconnected,
            )
            self.client = client
            try:
                if not client.services.get_characteristic(DATA):
                    raise UpdateFailed("Treadmill does not expose FTMS treadmill data")
                if client.services.get_characteristic(FEATURE):
                    features = bytes(await client.read_gatt_char(FEATURE))
                    _LOGGER.debug("FTMS features: %s", features.hex())
                    self.speed_supported = len(features) == 8 and bool(
                        int.from_bytes(features[4:], "little") & 1
                    )
                if self.speed_supported and client.services.get_characteristic(
                    SPEED_RANGE
                ):
                    raw = bytes(await client.read_gatt_char(SPEED_RANGE))
                    _LOGGER.debug("FTMS speed range: %s", raw.hex())
                    if len(raw) == 6:
                        minimum, maximum, step = struct.unpack("<HHH", raw)
                        if 0 < step <= maximum - minimum and minimum < maximum <= 650:
                            self.limits = (minimum / 100, maximum / 100, step / 100)
                await client.start_notify(DATA, self._notification(client, self._data))
                if client.services.get_characteristic(UREVO_DATA) and (
                    query := client.services.get_characteristic(UREVO_QUERY)
                ):
                    try:
                        await client.start_notify(
                            UREVO_DATA, self._notification(client, self._steps)
                        )
                        # This requests telemetry; it does not start/reset the belt.
                        self._steps_query_response = "write" in query.properties
                        await self._request_steps(client)
                    except Exception:
                        _LOGGER.warning(
                            "UREVO step telemetry setup failed", exc_info=True
                        )
                if client.services.get_characteristic(STATUS):
                    await client.start_notify(
                        STATUS, self._notification(client, self._status)
                    )
                if control := client.services.get_characteristic(CONTROL):
                    _LOGGER.debug("FTMS control properties: %s", control.properties)
                    self._control_write_response = (
                        "write-without-response" not in control.properties
                    )
                    await client.start_notify(
                        CONTROL, self._notification(client, self._response)
                    )
                    self.control_supported = True
                if self._closing or not client.is_connected:
                    raise UpdateFailed("Connection closed during setup")
            except BaseException:
                await self._disconnect(client)
                raise

    async def _async_update_data(self) -> dict[str, float | str]:
        try:
            await self._connect()
        except Exception as error:
            raise UpdateFailed(str(error)) from error
        if not self.fresh("speed"):
            self.armed_until = 0
        if (
            self.client
            and self._steps_query_response is not None
            and not self.fresh("steps")
            and time.monotonic() - self._steps_query_at >= FRESH_SECONDS
            and not self._command_lock.locked()
        ):
            try:
                await self._request_steps(self.client)
            except Exception:
                _LOGGER.warning("UREVO step telemetry request failed", exc_info=True)
        return dict(self.values)

    def arm(self) -> None:
        if self._closing or self._command_lock.locked():
            raise HomeAssistantError(
                "Cannot arm while a command is pending or integration is unloading"
            )
        if (
            not self.entry.options.get("allow_control", False)
            or not self.control_supported
            or not self.fresh("speed")
        ):
            raise HomeAssistantError(
                "Enable controls in integration options and wait for "
                "fresh speed telemetry"
            )
        self.armed_until = time.monotonic() + 60
        self._publish()

    def disarm(self) -> None:
        self._safety_revision += 1
        self.armed_until = 0
        self._publish()

    async def _write(self, client: BleakClient, command: bytes) -> None:
        future = self.hass.loop.create_future()
        self._pending = (command[0], future)
        try:
            async with asyncio.timeout(5):
                await client.write_gatt_char(
                    CONTROL, command, response=self._control_write_response
                )
                _LOGGER.debug("FTMS control write sent: %s", command.hex())
                result = await future
            if result != 1:
                raise HomeAssistantError(
                    f"Treadmill rejected command (FTMS result {result})"
                )
        finally:
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                # A transport error can coincide with a disconnect notification.
                future.exception()
            self._pending = None

    async def command(self, action: str, speed: float | None = None) -> None:
        # Reject competing calls instead of executing delayed physical actions.
        if self._closing or self._command_lock.locked():
            raise HomeAssistantError(
                "Another command is pending or integration is unloading"
            )
        async with self._command_lock:
            if action not in ("start", "stop", "pause", "speed"):
                raise HomeAssistantError("Unsupported treadmill command")
            if (
                not self.entry.options.get("allow_control", False)
                or not self.control_supported
            ):
                raise HomeAssistantError("Treadmill controls are disabled")
            if not self.client or not self.client.is_connected:
                raise HomeAssistantError(
                    "Treadmill disconnected; commands are never queued"
                )
            if action in ("start", "speed") and (
                not self.armed or not self.fresh("speed")
            ):
                raise HomeAssistantError(
                    "Arm controls with fresh telemetry before each start "
                    "or speed change"
                )
            if action == "start" and self.values["speed"] != 0:
                raise HomeAssistantError("Start requires a reported stationary belt")
            if action == "speed":
                if (
                    not self.limits
                    or not self.speed_supported
                    or self.values["speed"] <= 0
                ):
                    raise HomeAssistantError(
                        "Speed changes require a running belt "
                        "and a verified speed range"
                    )
                try:
                    payload = speed_command(
                        speed, self.limits, self.entry.options.get("max_speed", 1.6)
                    )
                except (ValueError, TypeError) as error:
                    raise HomeAssistantError(str(error)) from error
            else:
                payload = {"start": b"\x07", "stop": b"\x08\x01", "pause": b"\x08\x02"}[
                    action
                ]
            client = self.client
            armed_until = self.armed_until
            self.disarm()
            revision = self._safety_revision
            try:
                await self._write(client, b"\x00")
                if (
                    self._closing
                    or self.client is not client
                    or not client.is_connected
                    or not self.entry.options.get("allow_control", False)
                ):
                    raise HomeAssistantError(
                        "Connection changed during control request"
                    )
                if action in ("start", "speed"):
                    if (
                        revision != self._safety_revision
                        or time.monotonic() >= armed_until
                        or not self.fresh("speed")
                    ):
                        raise HomeAssistantError(
                            "Safety conditions changed during control request"
                        )
                    if (
                        action == "start"
                        and self.values["speed"] != 0
                        or action == "speed"
                        and self.values["speed"] <= 0
                    ):
                        raise HomeAssistantError(
                            "Belt state changed during control request"
                        )
                    if action == "speed":
                        if not self.limits or not self.speed_supported:
                            raise HomeAssistantError(
                                "Speed range is no longer available"
                            )
                        payload = speed_command(
                            speed, self.limits, self.entry.options.get("max_speed", 1.6)
                        )
                await self._write(client, payload)
            except asyncio.CancelledError:
                await self._disconnect(client)
                raise
            except Exception as error:
                _LOGGER.debug("FTMS %s command failed", action, exc_info=True)
                # Unknown outcome: discard the connection, never retry a motor command.
                await self._disconnect(client)
                raise HomeAssistantError(
                    "Command failed or was not acknowledged; check the physical remote"
                ) from error

    async def async_shutdown(self) -> None:
        self._closing = True
        self.armed_until = 0
        self._schedule_expiry()
        await super().async_shutdown()
        # A connection that finishes after unload begins must also be released.
        async with self._connect_lock:
            if self.client is not None:
                await self._disconnect(self.client)
