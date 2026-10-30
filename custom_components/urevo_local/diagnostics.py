"""Bounded telemetry diagnostics without device identifiers or credentials."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    coordinator = entry.runtime_data
    now = time.monotonic()
    return {
        "connected": bool(coordinator.client and coordinator.client.is_connected),
        "values": dict(coordinator.values),
        "age_seconds": {
            key: round(max(0, now - stamp), 3)
            for key, stamp in coordinator.seen.items()
        },
        "last_valid_frames": dict(coordinator.telemetry_frames),
    }
