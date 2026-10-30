"""Smoke-test real HA classes without opening any Bluetooth connection."""

import asyncio
import importlib
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

package = types.ModuleType("custom_components")
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components")]
sys.modules["custom_components"] = package


async def main():
    import voluptuous as vol

    for name in ("config_flow", "coordinator", "sensor", "button", "number", "switch"):
        importlib.import_module("custom_components.urevo_local." + name)
    from custom_components.urevo_local import button, number, sensor, switch
    from custom_components.urevo_local.config_flow import options_schema
    from custom_components.urevo_local.coordinator import UrevoCoordinator

    for value in (float("nan"), float("inf"), -1, 6.5):
        try:
            options_schema({})({"max_speed": value})
        except vol.Invalid:
            pass
        else:
            raise AssertionError(f"Invalid option accepted: {value}")
    with tempfile.TemporaryDirectory() as config_dir:
        hass = HomeAssistant(config_dir)
        entry = ConfigEntry(
            domain="urevo_local",
            version=1,
            minor_version=1,
            data={"address": "00:11:22:33:44:55"},
            options={},
            title="Test",
            unique_id="00:11:22:33:44:55",
            source="user",
            discovery_keys={},
            subentries_data=[],
        )
        c = UrevoCoordinator(hass, entry)
        entry.runtime_data = c
        entities = []
        for platform in (sensor, button, number, switch):
            await platform.async_setup_entry(hass, entry, entities.extend)
        assert len(entities) == 11
        assert len({e.unique_id for e in entities}) == 11
        assert all(
            not e.available for e in entities if isinstance(e, sensor.UrevoSensor)
        )
        assert all(
            not e.entity_registry_enabled_default
            for e in entities
            if not isinstance(e, (sensor.UrevoSensor, sensor.UrevoTotalStepsSensor))
        )
        assert all(
            e.state_class is None
            for e in entities
            if isinstance(e, sensor.UrevoSensor) and e.key != "speed"
        )
        assert not c.armed
        c.client = types.SimpleNamespace(is_connected=True, disconnect=AsyncMock())
        c._data(None, bytes.fromhex("0000 9600"))
        speed = next(e for e in entities if e.key == "speed")
        assert speed.available and speed.native_value == 1.5
        updates = []
        unsubscribe = c.async_add_listener(lambda: updates.append(speed.available))
        stamp = c.seen["speed"]
        with patch(
            "custom_components.urevo_local.coordinator.time.monotonic",
            return_value=stamp + 31,
        ):
            c._expiry_handle.cancel()
            c._expire()
            assert not speed.available
        assert updates == [False]
        unsubscribe()
        await c.async_shutdown()
        assert c.client is None and c._expiry_handle is None
    print(
        "Real HA API: imports, options, 11 entities, telemetry expiry and cleanup: PASS"
    )


if __name__ == "__main__":
    asyncio.run(main())
