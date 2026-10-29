"""Manual controls; no automatic motor actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.components.button import ButtonEntity

from .entity import UrevoEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        UrevoButton(entry.runtime_data, action, action.title())
        for action in ("start", "stop", "pause")
    )


class UrevoButton(UrevoEntity, ButtonEntity):
    _attr_entity_registry_enabled_default = False

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.control_supported
            and self.coordinator.entry.options.get("allow_control", False)
        )

    async def async_press(self) -> None:
        await self.coordinator.command(self.key)
