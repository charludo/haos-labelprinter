"""Bluetooth Classic via BlueZ's D-Bus Profile API (dbus-fast).

This is the Bluetooth route that works wherever Home Assistant's own Bluetooth
works: HA already talks to BlueZ over the system D-Bus with ``dbus-fast``.
Instead of opening a raw AF_BLUETOOTH socket (often not allowed inside the HA
container), we register a client ``org.bluez.Profile1`` for the Serial Port
UUID, ask BlueZ to ``ConnectProfile`` and receive the connected RFCOMM file
descriptor in ``NewConnection``.

The printer must already be paired/trusted in BlueZ (bluetoothctl).
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
import uuid as uuidlib

from .errors import TransportError
from .transport import RFCOMMTransport

_LOGGER = logging.getLogger(__name__)

SPP_UUID = "00001101-0000-1000-8000-00805f9b34fb"
SYSTEM_BUS_SOCKET = "/run/dbus/system_bus_socket"


def available() -> bool:
    try:
        import dbus_fast  # noqa: F401
    except ImportError:
        return False
    return os.path.exists(SYSTEM_BUS_SOCKET)


class BlueZTransport(RFCOMMTransport):
    """RFCOMM link obtained through BlueZ D-Bus; I/O reuses RFCOMMTransport."""

    def __init__(self, address: str, profile_uuid: str = SPP_UUID) -> None:
        super().__init__(address)
        self._uuid = profile_uuid
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bus = None
        self._profile_path: str | None = None

    # -- async helpers (run on a private loop owned by this thread) ----------
    async def _connect(self) -> socket.socket:
        from dbus_fast import BusType, Variant
        from dbus_fast.aio import MessageBus
        from dbus_fast.service import ServiceInterface, method

        got: asyncio.Future = asyncio.get_running_loop().create_future()

        class Profile(ServiceInterface):
            def __init__(self) -> None:
                super().__init__("org.bluez.Profile1")

            @method()
            def Release(self):  # noqa: N802
                pass

            @method()
            def NewConnection(self, device: "o", fd: "h", props: "a{sv}"):  # type: ignore[name-defined]  # noqa: N802,F821
                if not got.done():
                    got.set_result(fd)

            @method()
            def RequestDisconnection(self, device: "o"):  # type: ignore[name-defined]  # noqa: N802,F821
                pass

        bus = await MessageBus(bus_type=BusType.SYSTEM, negotiate_unix_fd=True).connect()
        self._bus = bus
        dev_path = await self._find_device(bus)

        self._profile_path = f"/org/ptouch/p{uuidlib.uuid4().hex}"
        bus.export(self._profile_path, Profile())
        intro = await bus.introspect("org.bluez", "/org/bluez")
        mgr = bus.get_proxy_object("org.bluez", "/org/bluez", intro).get_interface("org.bluez.ProfileManager1")
        await mgr.call_register_profile(self._profile_path, self._uuid, {
            "Role": Variant("s", "client"),
            "RequireAuthentication": Variant("b", False),
            "RequireAuthorization": Variant("b", False),
        })
        intro = await bus.introspect("org.bluez", dev_path)
        dev = bus.get_proxy_object("org.bluez", dev_path, intro).get_interface("org.bluez.Device1")

        last: Exception | None = None
        for attempt in range(6):
            try:
                await asyncio.wait_for(dev.call_connect_profile(self._uuid), 20)
                break
            except Exception as err:  # noqa: BLE001  (busy / in progress right after a disconnect)
                last = err
                await asyncio.sleep(0.75 * (attempt + 1))
        else:
            raise TransportError(f"BlueZ ConnectProfile failed: {last}")
        try:
            fd = await asyncio.wait_for(got, 10)
        except asyncio.TimeoutError as err:
            raise TransportError("BlueZ connected but gave no RFCOMM descriptor") from err
        return socket.socket(fileno=fd)

    async def _find_device(self, bus) -> str:
        intro = await bus.introspect("org.bluez", "/")
        om = bus.get_proxy_object("org.bluez", "/", intro).get_interface("org.freedesktop.DBus.ObjectManager")
        for path, ifaces in (await om.call_get_managed_objects()).items():
            d = ifaces.get("org.bluez.Device1")
            if d and d["Address"].value.upper() == self._address.upper():
                return path
        raise TransportError(f"{self._address} is not known to BlueZ; pair it first (bluetoothctl pair/trust)")

    async def _cleanup(self) -> None:
        bus, self._bus = self._bus, None
        if bus is None:
            return
        try:
            if self._profile_path:
                intro = await bus.introspect("org.bluez", "/org/bluez")
                mgr = bus.get_proxy_object("org.bluez", "/org/bluez", intro).get_interface("org.bluez.ProfileManager1")
                await mgr.call_unregister_profile(self._profile_path)
        except Exception:  # noqa: BLE001
            pass
        bus.disconnect()
        self._profile_path = None

    # -- transport hooks ------------------------------------------------------
    def _open(self) -> None:
        self._loop = asyncio.new_event_loop()
        try:
            self._sock = self._loop.run_until_complete(self._connect())
        except TransportError:
            self._close()
            raise
        except Exception as err:  # noqa: BLE001
            self._close()
            raise TransportError(f"Bluetooth (BlueZ D-Bus) connection failed: {err}") from err

    def _close(self) -> None:
        super()._close()
        if self._loop is not None:
            try:
                self._loop.run_until_complete(self._cleanup())
            except Exception:  # noqa: BLE001
                pass
            self._loop.close()
            self._loop = None
        time.sleep(0.3)  # let the printer drop the link before the next connect
