"""Small shared helpers for the Bluetooth setup code (no Home Assistant imports)."""
from __future__ import annotations

import re
from typing import Any

_MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$")
_PATH_RE = re.compile(r"^/dev/[A-Za-z0-9_./-]{1,64}$")

DEVICE_KEYS = ("address", "name", "paired", "trusted", "connected", "rssi", "is_printer")


def normalize_address(value: Any) -> str:
    """'aa-bb-..' / 'aa:bb:..' -> 'AA:BB:..'. Raises ValueError for anything else."""
    text = str(value).strip()
    if not _MAC_RE.match(text):
        raise ValueError("not a Bluetooth address")
    return text.replace("-", ":").upper()


def normalize_address_or_path(value: Any) -> str:
    """A Bluetooth address, or a /dev/... device file (rfcomm / lp)."""
    text = str(value).strip()
    if _PATH_RE.match(text) and ".." not in text:
        return text
    return normalize_address(text)


def get_btadmin() -> Any | None:
    """The ptouch.btadmin module, or None if it is not installed. Imported lazily (it may not exist)."""
    try:
        from .ptouch import btadmin
    except ImportError:
        return None
    return btadmin


def clean_device(dev: dict) -> dict:
    """Whitelist the BtDevice fields (never pass anything else through to the UI)."""
    out = {k: dev.get(k) for k in DEVICE_KEYS}
    out["address"] = str(out["address"] or "").upper()
    out["name"] = str(out["name"] or "")
    for k in ("paired", "trusted", "connected", "is_printer"):
        out[k] = bool(out[k])
    out["rssi"] = out["rssi"] if isinstance(out["rssi"], int) else None
    return out


def error_code(reason: str) -> str:
    """Map a failure reason to the WebSocket error code of bluetooth/pair etc."""
    if reason in ("pairing_failed", "pairing_timeout"):
        return reason
    if reason == "not_found":
        return "device_not_found"
    if reason in ("no_dbus", "no_adapter", "no_library", "bluetooth_off", "permission"):
        return "bluetooth_unavailable"
    return "pairing_failed"
