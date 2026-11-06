"""Brother P-touch (PT-P710BT) label printer."""
from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .editor_api import async_setup_editor
from .coordinator import PTouchConfigEntry, PTouchCoordinator
from .services import async_register_services

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_register_services(hass)
    await async_setup_editor(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PTouchConfigEntry) -> bool:
    coordinator = PTouchCoordinator(hass, entry)
    stash = hass.data.setdefault(DOMAIN + "_setup_failures", {})
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        stash[entry.entry_id] = (coordinator.last_reason, coordinator.last_message)   # for the `printers` rows
        raise
    stash.pop(entry.entry_id, None)
    entry.runtime_data = coordinator
    # Reload only for real changes: renaming a printer (title) must not interrupt it.
    coordinator.config_snapshot = (dict(entry.data), dict(entry.options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PTouchConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: PTouchConfigEntry) -> None:
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is not None and getattr(coordinator, "config_snapshot", None) == (
            dict(entry.data), dict(entry.options)):
        return
    await hass.config_entries.async_reload(entry.entry_id)
