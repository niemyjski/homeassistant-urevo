"""Stable entities share one connection and retain distinct telemetry semantics."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import UrevoCoordinator


class UrevoEntity(CoordinatorEntity[UrevoCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: UrevoCoordinator, key: str, name: str) -> None:
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_name = name
        self._attr_device_info = {
            "identifiers": {("urevo_local", coordinator.address)},
            "connections": {("bluetooth", coordinator.address)},
            "name": "UREVO walking pad",
            "manufacturer": "UREVO",
            "model": "URTM041",
        }
