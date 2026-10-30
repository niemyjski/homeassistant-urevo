"""Real Home Assistant API tests with no Bluetooth or server connections."""

import asyncio
import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.data_entry_flow import AbortFlow

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
integration = importlib.import_module("custom_components.urevo_local")
flow_module = importlib.import_module("custom_components.urevo_local.config_flow")
vol = flow_module.vol


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_diagnostics_reports_only_bounded_telemetry(self):
        diagnostics = importlib.import_module(
            "custom_components.urevo_local.diagnostics"
        )
        coordinator_module = importlib.import_module(
            "custom_components.urevo_local.coordinator"
        )
        coordinator = coordinator_module.UrevoCoordinator(self.hass, self.entry)
        self.entry.runtime_data = coordinator
        coordinator.client = types.SimpleNamespace(is_connected=True)
        frame = bytes.fromhex("0251030e007c0003002c007e0000000000d703")
        coordinator._steps(None, frame)
        coordinator._steps(None, b"invalid")
        result = await diagnostics.async_get_config_entry_diagnostics(
            self.hass, self.entry
        )
        self.assertTrue(result["connected"])
        self.assertEqual(result["last_valid_frames"], {"urevo": frame.hex()})
        self.assertEqual(result["values"]["steps"], 126)
        self.assertGreaterEqual(result["age_seconds"]["steps"], 0)
        self.assertNotIn(self.entry.data["address"], str(result))
        result["values"].clear()
        self.assertEqual(coordinator.values["steps"], 126)
        if coordinator._expiry_handle:
            coordinator._expiry_handle.cancel()

    async def test_total_steps_restore_duplicate_disconnect_and_reset(self):
        sensor_module = importlib.import_module("custom_components.urevo_local.sensor")
        coordinator = types.SimpleNamespace(
            address="00:11:22:33:44:55",
            values={"steps": 20, "steps_elapsed": 40},
            fresh=lambda key: True,
        )
        sensor = sensor_module.UrevoTotalStepsSensor(coordinator)
        state = State(
            "sensor.test", "100", {"last_session_steps": 20, "last_session_elapsed": 40}
        )
        with (
            patch.object(
                sensor_module.UrevoEntity, "async_added_to_hass", new_callable=AsyncMock
            ),
            patch.object(sensor, "async_get_last_state", return_value=state),
        ):
            await sensor.async_added_to_hass()
        self.assertEqual(sensor.native_value, 100)
        coordinator.values.update(steps=23, steps_elapsed=43)
        sensor._update_counter()
        self.assertEqual(sensor.native_value, 103)
        coordinator.fresh = lambda key: False
        coordinator.values.clear()
        sensor._update_counter()
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, 103)
        coordinator.fresh = lambda key: True
        coordinator.values.update(steps=2, steps_elapsed=3)
        sensor._update_counter()
        sensor._update_counter()
        self.assertEqual(sensor.native_value, 105)
        self.assertEqual(sensor.extra_state_attributes["last_session_steps"], 2)

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.hass = HomeAssistant(self.temp.name)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.entry = ConfigEntry(
            domain="urevo_local",
            version=1,
            minor_version=1,
            data={"address": "00:11:22:33:44:55"},
            options={},
            title="UREVO walking pad",
            unique_id="00:11:22:33:44:55",
            source="user",
            discovery_keys={},
            subentries_data=[],
        )
        self.flow = flow_module.UrevoConfigFlow()
        self.flow.hass = self.hass
        self.flow.context = {"source": "user"}
        self.discovery = types.SimpleNamespace(
            address="00:11:22:33:44:55", name="URTM041"
        )

    async def test_manual_discovery_creates_generic_entry(self):
        with patch.object(
            flow_module.bluetooth,
            "async_discovered_service_info",
            return_value=[self.discovery],
        ):
            form = await self.flow.async_step_user()
            self.assertEqual(form["type"], "form")
            result = await self.flow.async_step_user(
                {"address": self.discovery.address}
            )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "UREVO walking pad")
        self.assertEqual(result["data"], {"address": self.discovery.address})

    async def test_manual_missing_or_disappearing_device_aborts(self):
        with patch.object(
            flow_module.bluetooth, "async_discovered_service_info", return_value=[]
        ):
            for data in (None, {"address": self.discovery.address}):
                result = await self.flow.async_step_user(data)
                self.assertEqual(result["reason"], "no_devices_found")

    async def test_other_model_rejected(self):
        self.discovery.name = "unsupported"
        result = await self.flow.async_step_bluetooth(self.discovery)
        self.assertEqual(result["reason"], "not_supported")

    async def test_bluetooth_confirmation(self):
        result = await self.flow.async_step_bluetooth(self.discovery)
        self.assertEqual(result["step_id"], "confirm")
        result = await self.flow.async_step_confirm({})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "UREVO walking pad")

    async def test_duplicate_discovery_aborts(self):
        with patch.object(
            self.hass.config_entries,
            "async_entry_for_domain_unique_id",
            return_value=self.entry,
        ):
            with self.assertRaises(AbortFlow) as raised:
                await self.flow.async_step_bluetooth(self.discovery)
        self.assertEqual(raised.exception.reason, "already_configured")

    async def test_options_reject_nonfinite_and_boolean_speed(self):
        schema = flow_module.options_schema({})
        self.assertEqual(schema({}), {"allow_control": False, "max_speed": 1.6})
        for value in (True, False, float("nan"), float("inf"), -1, 6.5, "invalid"):
            with self.subTest(value=value), self.assertRaises(vol.Invalid):
                schema({"max_speed": value})
        self.assertEqual(schema({"max_speed": "1.5"})["max_speed"], 1.5)

    async def test_options_submission_is_validated(self):
        flow = flow_module.UrevoOptionsFlow()
        with patch.object(
            type(flow), "config_entry", new=property(lambda _: self.entry)
        ):
            result = await flow.async_step_init({"max_speed": float("nan")})
            self.assertEqual(result["errors"], {"base": "invalid_options"})
            result = await flow.async_step_init({"max_speed": 1.2})
            self.assertEqual(result["type"], "create_entry")
            self.assertEqual(result["data"], {"max_speed": 1.2, "allow_control": False})

    async def test_failed_setup_and_cancellation_cleanup(self):
        for error in (RuntimeError("setup failed"), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                coordinator = types.SimpleNamespace(
                    async_config_entry_first_refresh=AsyncMock(side_effect=error),
                    async_shutdown=AsyncMock(),
                )
                with patch.object(
                    integration, "UrevoCoordinator", return_value=coordinator
                ):
                    with self.assertRaises(type(error)):
                        await integration.async_setup_entry(self.hass, self.entry)
                coordinator.async_shutdown.assert_awaited_once()

    async def test_platform_setup_failure_cleanup(self):
        coordinator = types.SimpleNamespace(
            async_config_entry_first_refresh=AsyncMock(), async_shutdown=AsyncMock()
        )
        with (
            patch.object(integration, "UrevoCoordinator", return_value=coordinator),
            patch.object(
                self.hass.config_entries,
                "async_forward_entry_setups",
                side_effect=RuntimeError("platform failed"),
            ),
            self.assertRaises(RuntimeError),
        ):
            await integration.async_setup_entry(self.hass, self.entry)
        coordinator.async_shutdown.assert_awaited_once()

    async def test_unload_only_disconnects_after_platforms_unload(self):
        coordinator = types.SimpleNamespace(async_shutdown=AsyncMock())
        self.entry.runtime_data = coordinator
        with patch.object(
            self.hass.config_entries, "async_unload_platforms", return_value=False
        ):
            self.assertFalse(
                await integration.async_unload_entry(self.hass, self.entry)
            )
        coordinator.async_shutdown.assert_not_awaited()
        with patch.object(
            self.hass.config_entries, "async_unload_platforms", return_value=True
        ):
            self.assertTrue(await integration.async_unload_entry(self.hass, self.entry))
        coordinator.async_shutdown.assert_awaited_once()
