"""WebSocket commands for Bluetooth setup: status, scan, pair, forget, connect (admin only).

``ptouch.btadmin`` is imported lazily (see btutil.get_btadmin); every call into it runs in the executor.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from . import btutil
from .const import (CONF_ADDRESS, CONF_TRANSPORT, CONF_WAKE_SECONDS, DEFAULT_WAKE_SECONDS, DOMAIN,
                    TRANSPORT_BLUETOOTH, friendly_message)
from .editor_api import _NotFound, _command
from .ptouch import PtouchError, make_transport

_LOGGER = logging.getLogger(__name__)

LOCK_KEY = DOMAIN + "_bt_lock"


class _WsError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _bt_lock(hass: HomeAssistant) -> asyncio.Lock:
    return hass.data.setdefault(LOCK_KEY, asyncio.Lock())


def _address(value: Any) -> str:
    try:
        return btutil.normalize_address(value)
    except ValueError:
        raise vol.Invalid("invalid Bluetooth address") from None


def _err_message(err: Exception, reason: str) -> str:
    msg = getattr(err, "message", None) or str(err)
    return msg if msg and msg != reason else friendly_message(reason, "Bluetooth operation failed.")


async def _admin(hass: HomeAssistant, fn: str, *args: Any, **kwargs: Any) -> Any:
    """Run btadmin.<fn> in the executor; BtAdminError -> _WsError with a bluetooth_* code."""
    mod = btutil.get_btadmin()
    if mod is None:
        raise _WsError("bluetooth_unavailable", friendly_message("no_library"))
    try:
        return await hass.async_add_executor_job(lambda: getattr(mod, fn)(*args, **kwargs))
    except PtouchError as err:
        reason = getattr(err, "reason", "error")
        raise _WsError(btutil.error_code(reason), _err_message(err, reason)) from err


async def _require_available(hass: HomeAssistant) -> None:
    mod = btutil.get_btadmin()
    if mod is None:
        raise _WsError("bluetooth_unavailable", friendly_message("no_library"))
    ok, reason = await hass.async_add_executor_job(mod.available)
    if not ok:
        raise _WsError("bluetooth_unavailable", friendly_message(reason, "Bluetooth is not available."))


def bt_entries(hass: HomeAssistant) -> set[str]:
    """Normalised addresses of the configured Bluetooth printers."""
    out = set()
    for e in hass.config_entries.async_entries(DOMAIN):
        addr = e.data.get(CONF_ADDRESS)
        if e.data.get(CONF_TRANSPORT) == TRANSPORT_BLUETOOTH and addr:
            out.add(str(addr).upper())
    return out


def find_entry(hass: HomeAssistant, entry_id: str) -> ConfigEntry:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise _NotFound("Printer not found")
    return entry


def _wrap(func):
    """Turn _WsError into an error frame (everything else goes to the common handler)."""
    async def wrapper(hass, connection, msg):
        try:
            await func(hass, connection, msg)
        except _WsError as err:
            connection.send_error(msg["id"], err.code, str(err))
    wrapper.__name__ = func.__name__
    return wrapper


def _cmd(schema: dict):
    def deco(func):
        return _command(schema)(_wrap(func))
    return deco


@_cmd({vol.Required("type"): "brother_ptouch/bluetooth/status"})
async def ws_status(hass, connection, msg):
    mod = btutil.get_btadmin()
    if mod is None:
        connection.send_result(msg["id"], {"available": False, "reason": "no_library", "adapters": []})
        return
    ok, reason = await hass.async_add_executor_job(mod.available)
    adapters: list = []
    if ok:
        try:
            adapters = [{"path": str(a.get("path", "")), "address": str(a.get("address", "")),
                         "name": str(a.get("name", "")), "powered": bool(a.get("powered"))}
                        for a in await hass.async_add_executor_job(mod.adapters)]
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("listing Bluetooth adapters failed: %s", err)
    connection.send_result(msg["id"], {"available": bool(ok), "reason": reason, "adapters": adapters})


@_cmd({vol.Required("type"): "brother_ptouch/bluetooth/scan",
       vol.Optional("duration", default=8): vol.All(vol.Coerce(float), vol.Range(min=3, max=20))})
async def ws_scan(hass, connection, msg):
    await _require_available(hass)
    async with _bt_lock(hass):
        devices = await _admin(hass, "scan", msg["duration"])
    configured = bt_entries(hass)
    out = []
    for d in devices:
        dev = btutil.clean_device(d)
        dev["configured"] = dev["address"] in configured
        out.append(dev)
    connection.send_result(msg["id"], {"devices": out})


@_cmd({vol.Required("type"): "brother_ptouch/bluetooth/pair",
       vol.Required("address"): _address,
       vol.Optional("pin", default="0000"): vol.All(str, vol.Match(r"^[0-9A-Za-z]{1,16}$"))})
async def ws_pair(hass, connection, msg):
    await _require_available(hass)
    async with _bt_lock(hass):
        dev = await _admin(hass, "pair", msg["address"], pin=msg["pin"])
    connection.send_result(msg["id"], {"device": btutil.clean_device(dev)})


@_cmd({vol.Required("type"): "brother_ptouch/bluetooth/forget", vol.Required("address"): _address})
async def ws_forget(hass, connection, msg):
    await _require_available(hass)
    async with _bt_lock(hass):
        try:
            await _admin(hass, "forget", msg["address"])
        except _WsError as err:
            if err.code != "device_not_found":      # forgetting an unknown device is a no-op
                raise
    connection.send_result(msg["id"], {})


async def async_connect_entry(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Reach the printer of ``entry`` now. Expected failures come back as ok=False."""
    if entry.data.get(CONF_TRANSPORT) != TRANSPORT_BLUETOOTH:
        raise HomeAssistantError("This printer is not connected over Bluetooth")
    if entry.state is ConfigEntryState.LOADED:
        return await entry.runtime_data.async_connect()
    # Not set up (typically: asleep when Home Assistant started). Try with a throw-away transport.
    cfg = dict(entry.data)
    transport = make_transport(cfg.pop(CONF_TRANSPORT), **cfg)
    try:
        transport.wake_timeout = float(entry.options.get(CONF_WAKE_SECONDS, DEFAULT_WAKE_SECONDS))
    except (TypeError, ValueError):
        transport.wake_timeout = float(DEFAULT_WAKE_SECONDS)
    start = time.monotonic()
    try:
        await hass.async_add_executor_job(transport.get_status)
    except PtouchError as err:
        reason = getattr(err, "reason", "error") or "error"
        return {"ok": False, "reason": reason, "seconds": round(time.monotonic() - start, 1),
                "message": friendly_message(reason, str(err))}
    hass.config_entries.async_schedule_reload(entry.entry_id)
    return {"ok": True, "reason": "ok", "seconds": round(time.monotonic() - start, 1),
            "message": "Connected."}


@_cmd({vol.Required("type"): "brother_ptouch/bluetooth/connect", vol.Required("entry_id"): str})
async def ws_connect(hass, connection, msg):
    result = await async_connect_entry(hass, find_entry(hass, msg["entry_id"]))
    connection.send_result(msg["id"], result)


COMMANDS = (ws_status, ws_scan, ws_pair, ws_forget, ws_connect)
