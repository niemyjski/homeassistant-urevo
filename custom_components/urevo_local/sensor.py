"""Record reported values; never fabricate zeros or steps on lost telemetry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import UrevoCoordinator

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)

from .entity import UrevoEntity

SENSORS = (
    ("speed", "Speed", "km/h", SensorDeviceClass.SPEED, SensorStateClass.MEASUREMENT),
    (
        "distance",
        "Session distance",
        "m",
        SensorDeviceClass.DISTANCE,
        None,
    ),
    (
        "elapsed",
        "Session time",
        "s",
        SensorDeviceClass.DURATION,
        None,
    ),
    (
        "calories",
        "Session calories",
        "kcal",
        SensorDeviceClass.ENERGY,
        None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        UrevoSensor(entry.runtime_data, *description) for description in SENSORS
    )


class UrevoSensor(UrevoEntity, SensorEntity):
    def __init__(
        self,
        coordinator: UrevoCoordinator,
        key: str,
        name: str,
        unit: str,
        device_class: SensorDeviceClass,
        state_class: SensorStateClass | None,
    ) -> None:
        super().__init__(coordinator, key, name)
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.fresh(self.key)

    @property
    def native_value(self):
        return self.coordinator.values.get(self.key)
