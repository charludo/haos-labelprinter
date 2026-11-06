"""Connect Bluetooth button: wake / reach the printer now."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_TRANSPORT, TRANSPORT_BLUETOOTH
from .coordinator import PTouchConfigEntry
from .entity import PTouchEntity


async def async_setup_entry(hass: HomeAssistant, entry: PTouchConfigEntry, add: AddEntitiesCallback) -> None:
    if entry.data.get(CONF_TRANSPORT) == TRANSPORT_BLUETOOTH:
        add([PTouchConnectButton(entry.runtime_data)])


class PTouchConnectButton(PTouchEntity, ButtonEntity):
    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "connect_bluetooth")

    @property
    def available(self) -> bool:      # most useful exactly when the printer is asleep
        return True

    async def async_press(self) -> None:
        result = await self.coordinator.async_connect()
        if not result["ok"]:
            raise HomeAssistantError(result["message"])
