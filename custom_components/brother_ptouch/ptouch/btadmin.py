"""Bluetooth administration through BlueZ over D-Bus (dbus-fast): list adapters, scan, pair, forget, test.

Blocking API: every call runs its own short-lived event loop, so call it from an
executor thread, never from the Home Assistant event loop. Each call opens (and
closes) its own bus connection, so calls are independent and thread-safe.
``bus_address=None`` means the real system bus; tests pass a private bus address.

Reasons are the shared vocabulary of docs/BLUETOOTH_CONTRACT.md section 1.
No Home Assistant imports. (No ``from __future__ import annotations`` on
purpose: dbus-fast reads the annotations of the Agent1 methods as signatures.)
"""
import asyncio
import logging
import re
import time
import uuid as uuidlib

from . import _bluez_common as _c
from .errors import PtouchError

_LOGGER = logging.getLogger(__name__)

AGENT_CAPABILITY = "NoInputNoOutput"
IF_AGENT_MANAGER = "org.bluez.AgentManager1"
FIND_SECONDS = 10.0       # how long pair() discovers when the address is not yet known to BlueZ
_PRINTER_PREFIXES = ("pt-", "p-touch", "brother")
_ADDR_NAME = re.compile(r"^([0-9A-F]{2}[-:]){5}[0-9A-F]{2}$", re.I)


class BtAdminError(PtouchError):
    """Bluetooth admin failure: ``reason`` (shared vocabulary) and a friendly ``message``."""

    def __init__(self, reason, message=None):
        self.reason = reason
        self.message = message or _c.FRIENDLY.get(reason, _c.FRIENDLY["error"])
        super().__init__(self.message)


def _run(coro_fn):
    """Run ``coro_fn()`` on a fresh loop, converting internal errors to BtAdminError."""
    from_dbus = None
    try:
        from dbus_fast.errors import DBusError
        from_dbus = DBusError
    except ImportError:
        pass
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro_fn())
    except BtAdminError:
        raise
    except _c.LinkError as err:
        _LOGGER.debug("btadmin failed (%s): %s", err.reason, err.detail)
        raise BtAdminError(err.reason, err.message) from err
    except Exception as err:  # noqa: BLE001
        if from_dbus is not None and isinstance(err, from_dbus):
            le = _c.link_error_from_dbus(err)
            raise BtAdminError(le.reason, le.message) from err
        _LOGGER.debug("btadmin unexpected error: %r", err)
        raise BtAdminError("error", f"Bluetooth error: {err}") from err
    finally:
        loop.close()


async def _with_bus(bus_address, fn):
    bus = await _c.open_bus(bus_address)
    try:
        return await fn(bus)
    finally:
        bus.disconnect()


def _adapter_dict(path, props):
    return {"path": path, "address": props.get("Address", ""),
            "name": props.get("Alias") or props.get("Name") or path.rsplit("/", 1)[-1],
            "powered": bool(props.get("Powered"))}


def _device_dict(props):
    addr = str(props.get("Address", "")).upper()
    name = props.get("Name") or ""
    alias = props.get("Alias") or ""
    shown = alias if alias and not _ADDR_NAME.match(alias) else name
    rssi = props.get("RSSI")
    return {
        "address": addr,
        "name": shown,
        "paired": bool(props.get("Paired")),
        "trusted": bool(props.get("Trusted")),
        "connected": bool(props.get("Connected")),
        "rssi": int(rssi) if isinstance(rssi, int) else None,
        "is_printer": any(n.strip().lower().startswith(_PRINTER_PREFIXES) for n in (shown, name, alias)),
    }


# -- public API ----------------------------------------------------------------
def available(bus_address=None):
    """``(ok, reason)``: reason is ok, no_library, no_dbus, no_adapter or bluetooth_off."""
    try:
        import dbus_fast  # noqa: F401
    except ImportError:
        return False, "no_library"

    async def go(bus):
        found = _c.adapters_in(await _c.managed_objects(bus))
        if not found:
            return False, "no_adapter"
        if not any(p.get("Powered") for _, p in found):
            return False, "bluetooth_off"
        return True, "ok"

    try:
        return _run(lambda: _with_bus(bus_address, go))
    except BtAdminError as err:
        return False, err.reason


def adapters(bus_address=None):
    """``[{"path","address","name","powered"}]``."""
    async def go(bus):
        return [_adapter_dict(p, pr) for p, pr in _c.adapters_in(await _c.managed_objects(bus))]
    return _run(lambda: _with_bus(bus_address, go))


async def _power_on(bus, objs, adapter):
    path, props = _c.pick_adapter(objs, adapter)
    if not props.get("Powered"):
        await _c.set_prop(bus, path, _c.IF_ADAPTER, "Powered", "b", True)
        await asyncio.sleep(0.2)
    return path


def power_on(adapter=None, bus_address=None):
    """Switch the adapter (path, ``hciN`` or address; default first) on."""
    async def go(bus):
        await _power_on(bus, await _c.managed_objects(bus), adapter)
    _run(lambda: _with_bus(bus_address, go))


async def _discovery(bus, adapter_path, seconds, stop_when=None):
    """Run a Bluetooth Classic discovery for ``seconds`` (or until ``stop_when()`` is true)."""
    from dbus_fast import Variant
    from dbus_fast.errors import DBusError
    try:
        await _c.call(bus, adapter_path, _c.IF_ADAPTER, "SetDiscoveryFilter", "a{sv}",
                      [{"Transport": Variant("s", "bredr")}])
    except DBusError as err:
        _LOGGER.debug("SetDiscoveryFilter failed: %s", err)
    started = True
    try:
        await _c.call(bus, adapter_path, _c.IF_ADAPTER, "StartDiscovery")
    except DBusError as err:
        if _c.classify(err.type, err.text) == "busy":  # somebody else is already scanning
            started = False
        else:
            raise
    try:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if stop_when is not None and stop_when():
                break
            await asyncio.sleep(min(0.25, max(0.0, end - time.monotonic())))
    finally:
        if started:
            try:
                await _c.call(bus, adapter_path, _c.IF_ADAPTER, "StopDiscovery")
            except Exception:  # noqa: BLE001
                pass


def scan(duration=8.0, *, adapter=None, bus_address=None):
    """Classic Bluetooth discovery; returns BtDevice dicts, printers first then by signal strength."""
    async def go(bus):
        objs = await _c.managed_objects(bus)
        path = await _power_on(bus, objs, adapter)
        await _discovery(bus, path, max(0.0, float(duration)))
        out = []
        for _p, ifaces in (await _c.managed_objects(bus)).items():
            d = ifaces.get(_c.IF_DEVICE)
            if not d or d.get("Adapter") != path:
                continue
            dev = _device_dict(d)
            if not dev["name"] and not dev["paired"]:
                continue
            out.append(dev)
        out.sort(key=lambda x: (not x["is_printer"], -(x["rssi"] if x["rssi"] is not None else -1000)))
        return out
    return _run(lambda: _with_bus(bus_address, go))


def _make_agent(pin, events):
    """An ``org.bluez.Agent1`` that auto-accepts and answers PIN/passkey requests with ``pin``."""
    from dbus_fast.errors import DBusError
    from dbus_fast.service import ServiceInterface, method

    class Agent(ServiceInterface):
        def __init__(self):
            super().__init__("org.bluez.Agent1")

        @method()
        def Release(self):  # noqa: N802
            events.append("Release")

        @method()
        def RequestPinCode(self, device: "o") -> "s":  # noqa: N802,F821
            events.append("RequestPinCode")
            return pin

        @method()
        def DisplayPinCode(self, device: "o", pincode: "s"):  # noqa: N802,F821
            events.append("DisplayPinCode")

        @method()
        def RequestPasskey(self, device: "o") -> "u":  # noqa: N802,F821
            events.append("RequestPasskey")
            try:
                return int(pin) & 0xFFFFFFFF
            except ValueError:
                raise DBusError("org.bluez.Error.Rejected", "The PIN is not numeric.") from None

        @method()
        def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):  # noqa: N802,F821
            events.append("DisplayPasskey")

        @method()
        def RequestConfirmation(self, device: "o", passkey: "u"):  # noqa: N802,F821
            events.append("RequestConfirmation")

        @method()
        def RequestAuthorization(self, device: "o"):  # noqa: N802,F821
            events.append("RequestAuthorization")

        @method()
        def AuthorizeService(self, device: "o", uuid: "s"):  # noqa: N802,F821
            events.append("AuthorizeService")

        @method()
        def Cancel(self):  # noqa: N802
            events.append("Cancel")

    return Agent()


async def _find_or_discover(bus, address, adapter):
    objs = await _c.managed_objects(bus)
    hit = _c.find_device(objs, address)
    if hit:
        return hit
    path = await _power_on(bus, objs, adapter)
    found = []

    def seen():
        return bool(found)

    async def watcher():
        while not found:
            hit = _c.find_device(await _c.managed_objects(bus), address)
            if hit:
                found.append(hit)
            await asyncio.sleep(0.4)

    task = asyncio.ensure_future(watcher())
    try:
        await _discovery(bus, path, FIND_SECONDS, stop_when=seen)
    finally:
        task.cancel()
    if found:
        return found[0]
    hit = _c.find_device(await _c.managed_objects(bus), address)
    if hit:
        return hit
    raise BtAdminError("not_found")


def pair(address, *, pin="0000", timeout=45.0, adapter=None, bus_address=None):
    """Pair (and trust) a device; already paired is success. Returns the BtDevice dict."""
    from dbus_fast.errors import DBusError

    async def go(bus):
        dev_path, props = await _find_or_discover(bus, address, adapter)
        events = []
        if not props.get("Paired"):
            agent_path = f"/org/ptouch/agent{uuidlib.uuid4().hex}"
            bus.export(agent_path, _make_agent(str(pin), events))
            registered = False
            try:
                try:
                    await _c.call(bus, "/org/bluez", IF_AGENT_MANAGER, "RegisterAgent", "os",
                                  [agent_path, AGENT_CAPABILITY])
                    registered = True
                except DBusError as err:
                    if err.type != "org.bluez.Error.AlreadyExists":
                        raise
                    # an agent of ours/another connection exists; pairing may still work without one
                try:
                    await asyncio.wait_for(_c.call(bus, dev_path, _c.IF_DEVICE, "Pair"), float(timeout))
                except asyncio.TimeoutError:
                    try:
                        await _c.call(bus, dev_path, _c.IF_DEVICE, "CancelPairing")
                    except Exception:  # noqa: BLE001
                        pass
                    raise _c.LinkError("pairing_timeout") from None
                except DBusError as err:
                    if err.type != "org.bluez.Error.AlreadyExists":  # AlreadyExists: already paired
                        raise _c.link_error_from_dbus(err, "pair") from err
            finally:
                if registered:
                    try:
                        await _c.call(bus, "/org/bluez", IF_AGENT_MANAGER, "UnregisterAgent", "o", [agent_path])
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    bus.unexport(agent_path)
                except Exception:  # noqa: BLE001
                    pass
        try:
            await _c.set_prop(bus, dev_path, _c.IF_DEVICE, "Trusted", "b", True)
        except DBusError as err:
            _LOGGER.warning("Could not mark %s trusted: %s", address, err)
        now = await _c.get_props(bus, dev_path, _c.IF_DEVICE)
        if not now.get("Paired"):
            raise _c.LinkError("pairing_failed")
        try:  # do not keep the printer's single link occupied
            await _c.call(bus, dev_path, _c.IF_DEVICE, "Disconnect")
        except Exception:  # noqa: BLE001
            pass
        now = await _c.get_props(bus, dev_path, _c.IF_DEVICE)
        return _device_dict(now)

    return _run(lambda: _with_bus(bus_address, go))


def forget(address, *, bus_address=None):
    """Remove the device from BlueZ (unpair). Unknown address is a no-op."""
    async def go(bus):
        hit = _c.find_device(await _c.managed_objects(bus), address)
        if hit is None:
            return
        path, props = hit
        await _c.call(bus, props["Adapter"], _c.IF_ADAPTER, "RemoveDevice", "o", [path])
    _run(lambda: _with_bus(bus_address, go))


def connect_test(address, *, timeout=20.0, bus_address=None):
    """Try to open the Serial Port link (like printing does) and hang up again.

    Returns ``{"ok","reason","seconds","message"}``; expected failures are
    reported in the dict, never raised.
    """
    t0 = time.monotonic()

    def result(ok, reason, message=None):
        return {"ok": ok, "reason": reason, "seconds": round(time.monotonic() - t0, 2),
                "message": message or ("Connected to the printer." if ok else _c.FRIENDLY.get(reason, _c.FRIENDLY["error"]))}

    async def go(bus):
        try:
            sock, dev_path, profile_path = await _c.spp_connect(bus, address, _c.SPP_UUID, float(timeout))
        except _c.LinkError as err:
            return result(False, err.reason, err.message)
        try:
            sock.close()
            await _c.unregister_profile(bus, profile_path)
            try:
                await _c.call(bus, dev_path, _c.IF_DEVICE, "Disconnect")
            except Exception:  # noqa: BLE001
                pass
        finally:
            sock.close()
        return result(True, "ok")

    try:
        return _run(lambda: _with_bus(bus_address, go))
    except BtAdminError as err:
        return result(False, err.reason, err.message)
