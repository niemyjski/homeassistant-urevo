"""Protocol fixtures and command safety without a physical treadmill."""

import asyncio
import importlib.util
import struct
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "urevo_local"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


package = types.ModuleType("urevo_test")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
protocol = load("urevo_test.protocol", ROOT / "protocol.py")
steps_module = load("urevo_test.steps", ROOT / "steps.py")


class ProtocolTests(unittest.TestCase):
    def test_us_proprietary_measurements_match_ftms_resolution(self):
        native = bytes.fromhex("02510a0000b30107007e0000000003b80b0603")
        ftms = bytes.fromhex("842500006e00000c0000000000b301000000")
        expected = protocol.decode_urtm041(ftms)
        values = protocol.decode_urevo_us(native)
        self.assertEqual(values, {key: expected[key] for key in values})
        for raw, kmh in ((6, 0.96), (8, 1.28), (10, 1.60), (40, 6.43)):
            frame = bytearray(native)
            frame[3] = raw
            self.assertEqual(protocol.decode_urevo_us(frame)["speed"], kmh)
        for raw in (41, 256):
            frame = bytearray(native)
            frame[3:5] = raw.to_bytes(2, "little")
            with self.assertRaises(ValueError):
                protocol.decode_urevo_us(frame)

    def test_actual_step_frames_and_reject_truncated_status(self):
        running = bytes.fromhex("0251030e007c0003002c007e0000000000d703")
        paused = bytes.fromhex("02510a00004a010b008200760100000000f603")
        self.assertEqual(protocol.decode_steps(running), (126, 124))
        self.assertEqual(protocol.decode_steps(paused), (374, 330))
        for size in range(len(running)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                protocol.decode_steps(running[:size])
        for frame in (running + b"\x00", b"\x03" + running[1:], running[:-1] + b"\x00"):
            with self.assertRaises(ValueError):
                protocol.decode_steps(frame)

    def test_steps_stop_start_pause_and_duplicate_packets(self):
        counter = steps_module.StepCounter()
        for steps, elapsed in [
            (0, 0),
            (10, 12),
            (10, 12),
            (10, 12),
            (12, 14),
            (0, 0),
            (3, 4),
        ]:
            counter.update(steps, elapsed)
        self.assertEqual(counter.total, 15)

    def test_steps_restore_and_new_session_first_packet_not_zero(self):
        counter = steps_module.StepCounter(100, 20, 40)
        self.assertEqual(counter.update(20, 40), 100)
        self.assertEqual(counter.update(22, 42), 102)
        self.assertEqual(counter.update(3, 5), 105)
        # Reset detectable from elapsed even when the new count is larger.
        self.assertEqual(counter.update(4, 2), 109)

    def test_urtm041_captured_extended_frame(self):
        frame = bytes.fromhex("8425 0101 5e0100 1400 0000 00 00 8b01 fa0000")
        self.assertEqual(
            protocol.decode_urtm041(frame),
            {
                "speed": 2.57,
                "distance": 350,
                "calories": 20,
                "calories_per_hour": 0,
                "calories_per_minute": 0,
                "heart_rate": 0,
                "elapsed": 395,
            },
        )
        with self.assertRaises(ValueError):
            protocol.decode_treadmill(frame)
        for size in range(len(frame)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                protocol.decode_urtm041(frame[:size])
        for invalid in (frame + b"\x00", b"\x84\x65" + frame[2:]):
            with self.assertRaises(ValueError):
                protocol.decode_urtm041(invalid)

    def test_urtm041_idle_and_opaque_extension(self):
        idle = bytes.fromhex("842500000000000000000000000000000000")
        self.assertEqual(protocol.decode_urtm041(idle)["speed"], 0)
        self.assertEqual(
            protocol.decode_urtm041(idle),
            protocol.decode_urtm041(idle[:15] + b"\xff\xff\xff"),
        )
        standard = bytes.fromhex("00009600")
        self.assertEqual(protocol.decode_urtm041(standard), {"speed": 1.5})

    def test_speed_distance_energy_elapsed(self):
        frame = bytes.fromhex("8404 9600 d20400 2a00 6400 02 5802")
        self.assertEqual(
            protocol.decode_treadmill(frame),
            {
                "speed": 1.5,
                "distance": 1234,
                "calories": 42,
                "calories_per_hour": 100,
                "calories_per_minute": 2,
                "elapsed": 600,
            },
        )

    def test_all_optional_fields_preserve_offsets(self):
        frame = struct.pack("<HHH", 0x1FFE, 150, 140)
        frame += (1234).to_bytes(3, "little")
        frame += struct.pack(
            "<hhHHBBHHBBBHHhh",
            -15,
            -20,
            30,
            40,
            5,
            6,
            42,
            100,
            2,
            85,
            30,
            600,
            900,
            -10,
            120,
        )
        result = protocol.decode_treadmill(frame)
        self.assertEqual(result["inclination"], -1.5)
        self.assertEqual(result["elapsed"], 600)
        self.assertEqual(result["heart_rate"], 85)
        self.assertEqual(result["power"], 120)
        self.assertNotIn("steps", result)

    def test_more_data_omits_speed(self):
        self.assertEqual(
            protocol.decode_treadmill(bytes.fromhex("0500 640000")), {"distance": 100}
        )

    def test_reject_truncation_and_extensions(self):
        frame = bytes.fromhex("8404 9600 d20400 2a00 6400 02 5802")
        for size in range(len(frame)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                protocol.decode_treadmill(frame[:size])
        for extra in (frame + b"\x00", b"\x00\xe0\x00\x00"):
            with self.assertRaises(ValueError):
                protocol.decode_treadmill(extra)

    def test_speed_bounds_units_and_increment(self):
        self.assertEqual(
            protocol.speed_command(1.6, (0.5, 6, 0.1), 1.6), b"\x02\xa0\x00"
        )
        for value in (0, -1, 1.65, 6.1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                protocol.speed_command(value, (0.5, 6, 0.1), 1.6)

    def test_invalid_range_or_cap_cannot_bypass_limit(self):
        self.assertEqual(
            protocol.speed_command(1.6, (0.96, 6.43, 0.32), 1.6), b"\x02\xa0\x00"
        )
        for cap in (float("nan"), float("inf"), True):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                protocol.speed_command(4, (0.5, 6, 0.1), cap)
        for limits in (
            (0.5, 6, 0),
            (6, 0.5, 0.1),
            (0.5, 7, 0.1),
            (0.5, 6, float("nan")),
        ):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                protocol.speed_command(1, limits, 1.6)


class FakeCoordinator:
    def __init__(self, hass, *args, **kwargs):
        self.hass = hass
        self.last_update_success = True

    def async_set_updated_data(self, data):
        self.data = data

    def async_update_listeners(self):
        pass

    def async_set_update_error(self, error):
        self.last_update_success = False

    async def async_shutdown(self):
        pass


class SafetyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        modules = {}
        for name in (
            "bleak",
            "bleak_retry_connector",
            "homeassistant",
            "homeassistant.components",
            "homeassistant.components.bluetooth",
            "homeassistant.exceptions",
            "homeassistant.helpers",
            "homeassistant.helpers.update_coordinator",
        ):
            modules[name] = types.ModuleType(name)
        modules["bleak"].BleakClient = object
        self.establish = AsyncMock()
        modules["bleak_retry_connector"].establish_connection = self.establish
        modules["homeassistant.components"].bluetooth = modules[
            "homeassistant.components.bluetooth"
        ]
        modules["homeassistant.components.bluetooth"].async_ble_device_from_address = (
            lambda *a, **k: object()
        )
        modules["homeassistant.exceptions"].HomeAssistantError = RuntimeError
        modules[
            "homeassistant.helpers.update_coordinator"
        ].DataUpdateCoordinator = FakeCoordinator
        modules["homeassistant.helpers.update_coordinator"].UpdateFailed = RuntimeError
        self.modules = patch.dict(sys.modules, modules)
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.module = load("urevo_test.coordinator", ROOT / "coordinator.py")
        entry = types.SimpleNamespace(
            data={"address": "00:11:22:33:44:55"},
            options={"allow_control": True, "max_speed": 1.6},
        )
        self.c = self.module.UrevoCoordinator(
            types.SimpleNamespace(loop=asyncio.get_running_loop()), entry
        )
        self.client = types.SimpleNamespace(
            is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock()
        )
        self.c.client = self.client
        self.c.control_supported = True
        self.c.speed_supported = True
        self.c.limits = (0.5, 6, 0.1)
        self.c.values = {"speed": 0}
        self.c.seen = {"speed": time.monotonic()}
        self.addAsyncCleanup(self.c.async_shutdown)

    def acknowledge(self):
        async def write(uuid, payload, **kwargs):
            self.c._response(None, bytes([0x80, payload[0], 1]))

        self.client.write_gatt_char.side_effect = write

    async def test_native_mode_keeps_session_telemetry_fresh_without_ftms(self):
        self.c.limits = (0.96, 6.43, 0.32)
        self.c.seen.clear()
        frame = bytes.fromhex("0251030e007c0003002c007e0000000000d703")
        self.c._steps(None, frame)
        for key in ("speed", "elapsed", "distance", "calories", "steps"):
            self.assertTrue(self.c.fresh(key), key)
        self.assertEqual(self.c.values["speed"], 2.25)
        self.assertEqual(self.c.values["elapsed"], 124)
        self.assertEqual(self.c.values["distance"], 40)
        self.assertEqual(self.c.values["calories"], 4)
        self.assertEqual(self.c.values["steps"], 126)
        self.client.write_gatt_char.assert_not_called()
        self.c._steps(None, bytes.fromhex("025106010003"))
        self.assertEqual(self.c.values["steps"], 126)

    async def test_unverified_unit_profile_does_not_invent_speed(self):
        self.c.seen.clear()
        self.c._steps(None, bytes.fromhex("0251030e007c0003002c007e0000000000d703"))
        self.assertTrue(self.c.fresh("steps"))
        self.assertFalse(self.c.fresh("speed"))

    async def test_connection_subscribes_without_control_writes(self):
        self.c.client = None
        self.client.services = types.SimpleNamespace(
            get_characteristic=lambda uuid: types.SimpleNamespace(
                properties=["write-without-response"]
            )
        )
        self.client.start_notify = AsyncMock()

        async def read(uuid):
            return (
                struct.pack("<II", 0, 1)
                if uuid == protocol.FEATURE
                else struct.pack("<HHH", 50, 600, 10)
            )

        self.client.read_gatt_char = AsyncMock(side_effect=read)
        self.establish.return_value = self.client
        await self.c._connect()
        self.assertEqual(self.c.limits, (0.5, 6, 0.1))
        self.client.write_gatt_char.assert_awaited_once_with(
            protocol.UREVO_QUERY, protocol.UREVO_SUBSCRIBE, response=False
        )
        self.assertFalse(self.c.armed)
        self.assertFalse(self.c._control_write_response)

    async def test_write_without_response_still_requires_ftms_ack(self):
        self.c._control_write_response = False
        self.acknowledge()
        self.c.arm()
        await self.c.command("start")
        self.assertEqual(self.client.write_gatt_char.call_count, 2)
        for call in self.client.write_gatt_char.call_args_list:
            self.assertFalse(call.kwargs["response"])

        async def reject(uuid, payload, **kwargs):
            self.c._response(None, bytes([0x80, payload[0], 2]))

        self.client.write_gatt_char.reset_mock(side_effect=True)
        self.client.write_gatt_char.side_effect = reject
        self.c.arm()
        with self.assertRaisesRegex(RuntimeError, "Command failed"):
            await self.c.command("start")
        self.assertEqual(self.client.write_gatt_char.call_count, 1)
        self.assertFalse(self.c.fresh("speed"))

    async def test_default_control_disabled(self):
        self.c.entry.options = {}
        with self.assertRaises(RuntimeError):
            self.c.arm()
        with self.assertRaises(RuntimeError):
            await self.c.command("stop")
        self.client.write_gatt_char.assert_not_called()

    async def test_start_requires_arm(self):
        with self.assertRaises(RuntimeError):
            await self.c.command("start")
        self.client.write_gatt_char.assert_not_called()

    async def test_one_arm_one_start(self):
        self.acknowledge()
        self.c.arm()
        await self.c.command("start")
        self.assertEqual(
            [call.args[1] for call in self.client.write_gatt_char.call_args_list],
            [b"\x00", b"\x07"],
        )
        with self.assertRaises(RuntimeError):
            await self.c.command("start")
        self.assertFalse(self.c.armed)

    async def test_concurrent_start_does_not_reuse_arm(self):
        self.acknowledge()
        self.c.arm()
        results = await asyncio.gather(
            self.c.command("start"), self.c.command("start"), return_exceptions=True
        )
        self.assertEqual(sum(isinstance(x, RuntimeError) for x in results), 1)
        self.assertEqual(self.client.write_gatt_char.call_count, 2)

    async def test_stale_and_expired_arms_fail_closed(self):
        self.c.arm()
        self.c.seen["speed"] -= 31
        with self.assertRaises(RuntimeError):
            await self.c.command("start")
        self.c.seen["speed"] = time.monotonic()
        self.c.armed_until = time.monotonic() - 1
        with self.assertRaises(RuntimeError):
            await self.c.command("start")
        self.client.write_gatt_char.assert_not_called()

    async def test_speed_requires_running_belt_and_bounded_value(self):
        self.c.arm()
        with self.assertRaises(RuntimeError):
            await self.c.command("speed", 1.0)
        self.c.values["speed"] = 1
        with self.assertRaises(RuntimeError):
            await self.c.command("speed", 4)
        self.client.write_gatt_char.assert_not_called()
        self.acknowledge()
        await self.c.command("speed", 1.5)
        self.assertEqual(self.client.write_gatt_char.call_args.args[1], b"\x02\x96\x00")

    async def test_disconnect_clears_arm_and_staleness(self):
        self.c.arm()
        self.c._disconnected(self.client)
        self.assertFalse(self.c.armed)
        self.assertFalse(self.c.fresh("speed"))

    async def test_rejection_never_sends_motor_command(self):
        async def reject(uuid, payload, **kwargs):
            self.c._response(None, bytes([0x80, payload[0], 5]))

        self.client.write_gatt_char.side_effect = reject
        self.c.arm()
        with self.assertRaises(RuntimeError):
            await self.c.command("start")
        self.assertEqual(self.client.write_gatt_char.call_count, 1)
        self.client.disconnect.assert_awaited_once()

    async def test_timeout_never_retries_or_leaves_arm(self):
        self.c.arm()
        self.client.write_gatt_char.side_effect = TimeoutError
        with self.assertRaises(RuntimeError):
            await self.c.command("start")
        self.assertEqual(self.client.write_gatt_char.call_count, 1)
        self.assertFalse(self.c.armed)
        self.client.disconnect.assert_awaited_once()

    async def test_bad_frame_does_not_refresh_telemetry(self):
        self.c.seen.clear()
        self.c._data(None, b"\x00")
        self.assertFalse(self.c.fresh("speed"))
        self.c._data(None, bytes.fromhex("0000 9600"))
        self.assertTrue(self.c.fresh("speed"))
        self.assertEqual(self.c.values["speed"], 1.5)

    async def test_stop_is_available_without_arm_with_stale_speed(self):
        self.acknowledge()
        self.c.seen.clear()
        await self.c.command("stop")
        self.assertEqual(self.client.write_gatt_char.call_args.args[1], b"\x08\x01")

    async def test_safety_change_during_control_request_blocks_motor_write(self):
        changes = (
            lambda: self.c.seen.clear(),
            lambda: self.c.values.update(speed=1),
            lambda: self.c._status(None, b"\x03"),
            self.c.disarm,
        )
        for change in changes:
            with self.subTest(change=change):
                self.c.client = self.client
                self.c.control_supported = True
                self.c.values["speed"] = 0
                self.c.seen["speed"] = time.monotonic()
                self.client.write_gatt_char.reset_mock()

                async def write(uuid, payload, change=change, **kwargs):
                    change()
                    self.c._response(None, bytes([0x80, payload[0], 1]))

                self.client.write_gatt_char.side_effect = write
                self.c.arm()
                with self.assertRaises(RuntimeError):
                    await self.c.command("start")
                self.assertEqual(self.client.write_gatt_char.call_count, 1)

    async def test_expired_arm_during_control_request_blocks_motor_write(self):
        clock = [time.monotonic()]
        self.c.arm()

        async def write(uuid, payload, **kwargs):
            clock[0] += 61
            self.c.seen["speed"] = clock[0]
            self.c._response(None, bytes([0x80, payload[0], 1]))

        self.client.write_gatt_char.side_effect = write
        with patch.object(self.module.time, "monotonic", side_effect=lambda: clock[0]):
            with self.assertRaises(RuntimeError):
                await self.c.command("start")
        self.assertEqual(self.client.write_gatt_char.call_count, 1)

    async def test_permission_revoked_during_request_blocks_motor_write(self):
        async def write(uuid, payload, **kwargs):
            self.c.entry.options["allow_control"] = False
            self.c._response(None, bytes([0x80, payload[0], 1]))

        self.client.write_gatt_char.side_effect = write
        self.c.arm()
        with self.assertRaises(RuntimeError):
            await self.c.command("start")
        self.assertEqual(self.client.write_gatt_char.call_count, 1)
        self.assertFalse(self.c.armed)
        self.client.disconnect.assert_awaited_once()

    async def test_lowered_cap_during_request_blocks_speed_write(self):
        async def write(uuid, payload, **kwargs):
            self.c.entry.options["max_speed"] = 1.0
            self.c._response(None, bytes([0x80, payload[0], 1]))

        self.client.write_gatt_char.side_effect = write
        self.c.values["speed"] = 1.0
        self.c.arm()
        with self.assertRaises(RuntimeError):
            await self.c.command("speed", 1.5)
        self.assertEqual(self.client.write_gatt_char.call_count, 1)
        self.assertFalse(self.c.armed)
        self.client.disconnect.assert_awaited_once()

    async def test_each_field_expires_independently(self):
        now = time.monotonic()
        self.c.values.update(distance=100, elapsed=60)
        self.c.seen.update(distance=now - 31, elapsed=now - 5)
        self.c._data(None, bytes.fromhex("0000 9600"))
        self.assertTrue(self.c.fresh("speed"))
        self.assertTrue(self.c.fresh("elapsed"))
        self.assertFalse(self.c.fresh("distance"))
        self.assertEqual(self.c.values["distance"], 100)

    async def test_mismatched_acknowledgment_does_not_complete_request(self):
        future = asyncio.get_running_loop().create_future()
        self.c._pending = (7, future)
        try:
            for frame in (b"", b"\x80\x07", b"\x81\x07\x01", b"\x80\x02\x01"):
                self.c._response(None, frame)
                self.assertFalse(future.done())
            self.c._response(None, b"\x80\x07\x01")
            self.assertEqual(future.result(), 1)
        finally:
            future.cancel()
            self.c._pending = None

    async def test_old_connection_callbacks_are_ignored(self):
        old = types.SimpleNamespace(is_connected=True)
        self.c.arm()
        self.c._disconnected(old)
        self.c._notification(old, self.c._data)(None, bytes.fromhex("0000 9600"))
        self.assertTrue(self.c.armed)
        self.assertEqual(self.c.values["speed"], 0)

    async def test_disarm_does_not_clear_connection_error(self):
        self.c._disconnected(self.client)
        self.c.disarm()
        self.assertFalse(self.c.last_update_success)

    async def test_expiry_notifies_listeners_without_new_packets(self):
        self.c.async_update_listeners = types.MethodType(
            lambda c: updates.append(c.fresh("speed")), self.c
        )
        updates = []
        self.c.arm()
        now = time.monotonic()
        with patch.object(self.module.time, "monotonic", return_value=now + 31):
            self.c._expiry_handle.cancel()
            self.c._expire()
        self.assertEqual(updates, [True, False])
        self.assertFalse(self.c.armed)
        self.assertIsNone(self.c._expiry_handle)

    async def test_pending_command_rejects_rearm_and_competing_command(self):
        entered = asyncio.Event()
        release = asyncio.Event()

        async def write(uuid, payload, **kwargs):
            entered.set()
            await release.wait()
            self.c._response(None, bytes([0x80, payload[0], 1]))

        self.client.write_gatt_char.side_effect = write
        self.c.arm()
        task = asyncio.create_task(self.c.command("start"))
        try:
            await entered.wait()
            with self.assertRaises(RuntimeError):
                self.c.arm()
            with self.assertRaises(RuntimeError):
                await self.c.command("start")
        finally:
            release.set()
            await task
        self.assertEqual(self.client.write_gatt_char.call_count, 2)

    async def test_cancellation_disconnects_and_does_not_retry(self):
        entered = asyncio.Event()

        async def write(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()

        self.client.write_gatt_char.side_effect = write
        self.c.arm()
        task = asyncio.create_task(self.c.command("start"))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIsNone(self.c._pending)
        self.assertIsNone(self.c.client)
        self.assertFalse(self.c.armed)
        self.client.disconnect.assert_awaited_once()

    async def test_shutdown_releases_connection_finishing_setup(self):
        self.c.client = None
        entered = asyncio.Event()
        release = asyncio.Event()

        async def connect(*args, **kwargs):
            entered.set()
            await release.wait()
            return self.client

        self.establish.side_effect = connect
        self.client.services = types.SimpleNamespace(
            get_characteristic=lambda uuid: uuid == protocol.DATA
        )
        self.client.start_notify = AsyncMock()
        connecting = asyncio.create_task(self.c._connect())
        await entered.wait()
        shutdown = asyncio.create_task(self.c.async_shutdown())
        await asyncio.sleep(0)
        release.set()
        with self.assertRaises(RuntimeError):
            await connecting
        await shutdown
        self.assertIsNone(self.c.client)
        self.assertIsNone(self.c._expiry_handle)
        self.client.disconnect.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
