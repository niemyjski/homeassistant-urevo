"""Explicit speed setpoint; never present measured speed as a stored target."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfSpeed

from .entity import UrevoEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([UrevoSpeed(entry.runtime_data, "target_speed", "Target speed")])


class UrevoSpeed(UrevoEntity, NumberEntity):
    _attr_entity_registry_enabled_default = False
    _attr_native_unit_of_measurement = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_mode = NumberMode.BOX

    @property
    def available(self) -> bool:
        c = self.coordinator
        return (
            super().available
            and c.control_supported
            and c.limits is not None
            and c.entry.options.get("allow_control", False)
            and c.fresh("speed")
        )

    @property
    def native_min_value(self) -> float:
        return self.coordinator.limits[0] if self.coordinator.limits else 0

    @property
    def native_max_value(self) -> float:
        limit = self.coordinator.limits[1] if self.coordinator.limits else 6.4
        return min(limit, self.coordinator.entry.options.get("max_speed", 1.6))

    @property
    def native_step(self) -> float:
        return self.coordinator.limits[2] if self.coordinator.limits else 0.1

    @property
    def native_value(self) -> None:
        # FTMS target is not readable; a command acknowledgment is not a measurement.
        return None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.command("speed", value)
