"""Printer sensors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PTouchConfigEntry
from .entity import PTouchEntity
from .ptouch import PrinterStatus


@dataclass(frozen=True, kw_only=True)
class PTouchSensorDescription(SensorEntityDescription):
    value_fn: Callable[[PrinterStatus], str | float | None]


def _pretty(name: str) -> str:
    return name.replace("_", " ")


SENSORS = (
    PTouchSensorDescription(
        key="status", device_class=SensorDeviceClass.ENUM, options=["idle", "printing", "error"],
        value_fn=lambda s: s.state),
    PTouchSensorDescription(
        key="tape_width", native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: (3.5 if s.media_width == 4 else s.media_width) if s.has_tape else None),
    PTouchSensorDescription(
        key="tape_type", entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _pretty(s.media_type_name)),
    PTouchSensorDescription(
        key="tape_colour", entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _pretty(s.tape_colour_name) if s.has_tape else None),
    PTouchSensorDescription(
        key="text_colour", entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _pretty(s.text_colour_name) if s.has_tape else None),
)


async def async_setup_entry(hass: HomeAssistant, entry: PTouchConfigEntry, add: AddEntitiesCallback) -> None:
    add(PTouchSensor(entry.runtime_data, d) for d in SENSORS)


class PTouchSensor(PTouchEntity, SensorEntity):
    entity_description: PTouchSensorDescription

    def __init__(self, coordinator, description: PTouchSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self):
        if self.entity_description.key == "status":
            return {"errors": self.coordinator.data.errors}
        return None
