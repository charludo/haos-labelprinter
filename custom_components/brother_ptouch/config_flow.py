"""Config flow: USB, Bluetooth (RFCOMM / device file) or HTTP bridge."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (NumberSelector, NumberSelectorConfig, SelectSelector,
                                            SelectSelectorConfig)
from homeassistant.helpers.service_info.usb import UsbServiceInfo

from .const import (CONF_ADDRESS, CONF_BATCH_WINDOW, CONF_CHANNEL, CONF_ORIENTATION, DEFAULT_BATCH_WINDOW, CONF_TOKEN, CONF_TRANSPORT,
                    CONF_URL, CONF_USB_SERIAL, DEFAULT_ORIENTATION, DOMAIN, TRANSPORT_BLUETOOTH,
                    TRANSPORT_BRIDGE, TRANSPORT_USB)
from .ptouch import DEFAULT_RFCOMM_CHANNEL, ORIENTATIONS, PtouchError, make_transport


class PTouchConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered_serial: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> "PTouchOptionsFlow":
        return PTouchOptionsFlow()

    async def _try(self, data: dict[str, Any]) -> str | None:
        cfg = dict(data)
        try:
            transport = make_transport(cfg.pop(CONF_TRANSPORT), **cfg)
            await self.hass.async_add_executor_job(transport.get_status)
        except PtouchError:
            return "cannot_connect"
        except Exception:  # noqa: BLE001
            return "unknown"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="user", menu_options=[TRANSPORT_USB, TRANSPORT_BLUETOOTH, TRANSPORT_BRIDGE])

    async def async_step_usb(self, user_input=None) -> ConfigFlowResult:
        """Manual USB setup (menu choice) or, when given UsbServiceInfo, discovery."""
        if isinstance(user_input, UsbServiceInfo):
            self._discovered_serial = user_input.serial_number
            await self.async_set_unique_id(f"usb:{self._discovered_serial or 'default'}")
            self._abort_if_unique_id_configured()
            self.context["title_placeholders"] = {"name": "Brother P-touch (USB)"}
            return await self.async_step_discovery_confirm()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {CONF_TRANSPORT: TRANSPORT_USB, CONF_USB_SERIAL: user_input.get(CONF_USB_SERIAL, "").strip()}
            if not (err := await self._try(data)):
                await self.async_set_unique_id(f"usb:{data[CONF_USB_SERIAL] or 'default'}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Brother P-touch (USB)", data=data)
            errors["base"] = err
        return self.async_show_form(
            step_id="usb", errors=errors,
            data_schema=vol.Schema({vol.Optional(CONF_USB_SERIAL, default=(user_input or {}).get(CONF_USB_SERIAL, "")): str}))

    async def async_step_discovery_confirm(self, user_input=None) -> ConfigFlowResult:
        data = {CONF_TRANSPORT: TRANSPORT_USB, CONF_USB_SERIAL: self._discovered_serial or ""}
        if user_input is not None:
            return self.async_create_entry(title="Brother P-touch (USB)", data=data)
        return self.async_show_form(step_id="discovery_confirm")

    async def async_step_bluetooth(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {CONF_TRANSPORT: TRANSPORT_BLUETOOTH,
                    CONF_ADDRESS: user_input[CONF_ADDRESS].strip().upper() if not user_input[CONF_ADDRESS].startswith("/") else user_input[CONF_ADDRESS].strip(),
                    CONF_CHANNEL: user_input[CONF_CHANNEL]}
            if not (err := await self._try(data)):
                await self.async_set_unique_id(f"bt:{data[CONF_ADDRESS]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"Brother P-touch ({data[CONF_ADDRESS]})", data=data)
            errors["base"] = err
        d = user_input or {}
        return self.async_show_form(
            step_id="bluetooth", errors=errors,
            data_schema=vol.Schema({
                vol.Required(CONF_ADDRESS, default=d.get(CONF_ADDRESS, "")): str,
                vol.Optional(CONF_CHANNEL, default=d.get(CONF_CHANNEL, DEFAULT_RFCOMM_CHANNEL)): vol.All(int, vol.Range(min=1, max=30)),
            }))

    async def async_step_bridge(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {CONF_TRANSPORT: TRANSPORT_BRIDGE, CONF_URL: user_input[CONF_URL].strip().rstrip("/"),
                    CONF_TOKEN: user_input.get(CONF_TOKEN, "")}
            if not (err := await self._try(data)):
                await self.async_set_unique_id(f"bridge:{data[CONF_URL]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"Brother P-touch ({data[CONF_URL]})", data=data)
            errors["base"] = err
        d = user_input or {}
        return self.async_show_form(
            step_id="bridge", errors=errors,
            data_schema=vol.Schema({
                vol.Required(CONF_URL, default=d.get(CONF_URL, "http://")): str,
                vol.Optional(CONF_TOKEN, default=d.get(CONF_TOKEN, "")): str,
            }))


class PTouchOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_ORIENTATION, DEFAULT_ORIENTATION)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_ORIENTATION, default=current): SelectSelector(
                SelectSelectorConfig(options=list(ORIENTATIONS), translation_key="orientation", mode="dropdown")),
            vol.Required(CONF_BATCH_WINDOW, default=self.config_entry.options.get(CONF_BATCH_WINDOW, DEFAULT_BATCH_WINDOW)):
                NumberSelector(NumberSelectorConfig(min=0, max=30, step=0.5, unit_of_measurement="s", mode="box")),
        }))
