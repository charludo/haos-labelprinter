"""Problem / tape-loaded binary sensors."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PTouchConfigEntry
from .entity import PTouchEntity


async def async_setup_entry(hass: HomeAssistant, entry: PTouchConfigEntry, add: AddEntitiesCallback) -> None:
    add([PTouchProblem(entry.runtime_data), PTouchTape(entry.runtime_data)])


class PTouchProblem(PTouchEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "problem")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.errors)

    @property
    def extra_state_attributes(self):
        return {"errors": self.coordinator.data.errors}


class PTouchTape(PTouchEntity, BinarySensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "tape_loaded")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.has_tape
