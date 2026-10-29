"""One-action authorization expires after a minute and is never restored."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory

from .entity import UrevoEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        [UrevoArm(entry.runtime_data, "arm_controls", "Arm next control")]
    )


class UrevoArm(UrevoEntity, SwitchEntity):
    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        return self.coordinator.armed

    async def async_turn_on(self, **kwargs: object) -> None:
        self.coordinator.arm()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator.disarm()
