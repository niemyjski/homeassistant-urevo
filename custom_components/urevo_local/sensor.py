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
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import UrevoEntity
from .steps import StepCounter

SENSORS = (
    ("steps", "Session steps", "steps", None, None),
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
        [
            *(UrevoSensor(entry.runtime_data, *description) for description in SENSORS),
            UrevoTotalStepsSensor(entry.runtime_data),
        ]
    )


class UrevoSensor(UrevoEntity, SensorEntity):
    def __init__(
        self,
        coordinator: UrevoCoordinator,
        key: str,
        name: str,
        unit: str,
        device_class: SensorDeviceClass | None,
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


class UrevoTotalStepsSensor(UrevoEntity, SensorEntity, RestoreEntity):
    """Persist total and session baseline together across orderly HA restarts."""

    _attr_native_unit_of_measurement = "steps"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:shoe-print"

    def __init__(self, coordinator: UrevoCoordinator) -> None:
        super().__init__(coordinator, "total_steps", "Total steps")
        self.counter = StepCounter()
        self._ready = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (state := await self.async_get_last_state()) is not None:
            try:
                total = int(state.state)
                steps = int(state.attributes["last_session_steps"])
                elapsed = int(state.attributes["last_session_elapsed"])
                if total < 0 or not 0 <= steps <= 65535 or not 0 <= elapsed <= 65535:
                    raise ValueError("Invalid restored step counter")
                self.counter = StepCounter(total, steps, elapsed)
            except ValueError, TypeError, KeyError:
                pass
        self._ready = True
        self._update_counter()

    def _update_counter(self) -> None:
        if self._ready and self.coordinator.fresh("steps"):
            self.counter.update(
                int(self.coordinator.values["steps"]),
                int(self.coordinator.values["steps_elapsed"]),
            )

    def _handle_coordinator_update(self) -> None:
        self._update_counter()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        return self._ready and self.counter.steps is not None

    @property
    def native_value(self) -> int:
        return self.counter.total

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        return {
            "last_session_steps": self.counter.steps,
            "last_session_elapsed": self.counter.elapsed,
        }
