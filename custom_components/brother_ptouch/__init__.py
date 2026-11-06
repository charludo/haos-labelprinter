"""Brother P-touch (PT-P710BT) label printer."""
from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .editor_api import async_setup_editor
from .coordinator import PTouchConfigEntry, PTouchCoordinator
from .services import async_register_services

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_register_services(hass)
    await async_setup_editor(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PTouchConfigEntry) -> bool:
    coordinator = PTouchCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PTouchConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: PTouchConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
