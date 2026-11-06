"""btadmin against a fake org.bluez on a private dbus-daemon (never the real bus)."""
import sys
import time

import pytest

from fake_bluez import FakeBlueZ, available as dbus_daemon_available
from ptouch import _bluez_common as common
from ptouch import btadmin
from ptouch.btadmin import BtAdminError

pytestmark = pytest.mark.skipif(not dbus_daemon_available(), reason="dbus-daemon not installed")

A = "AA:BB:CC:00:00:01"
B = "AA:BB:CC:00:00:02"
C = "AA:BB:CC:00:00:03"


@pytest.fixture(autouse=True)
def never_system_bus(monkeypatch):
    real = common.open_bus

    async def guarded(bus_address=None, timeout=5.0):
        assert bus_address, "tests must never use the real system bus"
        return await real(bus_address, timeout)
    monkeypatch.setattr(common, "open_bus", guarded)


@pytest.fixture
def fake():
    f = FakeBlueZ().start()
    yield f
    f.stop()


def test_available_ok_and_adapters(fake):
    assert btadmin.available(fake.address) == (True, "ok")
    ad = btadmin.adapters(fake.address)
    assert ad == [{"path": "/org/bluez/hci0", "address": "00:11:22:33:44:55", "name": "fakehost", "powered": True}]


def test_available_reasons(fake, monkeypatch):
    assert btadmin.available("unix:path=/nonexistent/bus") == (False, "no_dbus")
    fake.set_powered(False)
    time.sleep(0.1)
    assert btadmin.available(fake.address) == (False, "bluetooth_off")
    monkeypatch.setitem(sys.modules, "dbus_fast", None)
    assert btadmin.available(fake.address) == (False, "no_library")


def test_available_no_adapter():
    f = FakeBlueZ(with_adapter=False).start()
    try:
        assert btadmin.available(f.address) == (False, "no_adapter")
        assert btadmin.adapters(f.address) == []
        with pytest.raises(BtAdminError) as e:
            btadmin.scan(0.1, bus_address=f.address)
        assert e.value.reason == "no_adapter"
    finally:
        f.stop()


def test_no_dbus_raises_btadmin_error():
    with pytest.raises(BtAdminError) as e:
        btadmin.adapters("unix:path=/nonexistent/bus")
    assert e.value.reason == "no_dbus"


def test_power_on(fake):
    fake.set_powered(False)
    time.sleep(0.1)
    btadmin.power_on(bus_address=fake.address)
    assert fake.powered is True
    btadmin.power_on("hci0", bus_address=fake.address)  # already on: no error
    with pytest.raises(BtAdminError) as e:
        btadmin.power_on("hci9", bus_address=fake.address)
    assert e.value.reason == "no_adapter"


def test_scan_ranking_filtering(fake):
    fake.add_device("11:00:00:00:00:01", "Headset", rssi=-40)
    fake.add_device("11:00:00:00:00:02", "PT-P710BT0001", rssi=-80)
    fake.add_device("11:00:00:00:00:03", "brother label", rssi=-55)
    fake.add_device("11:00:00:00:00:04", "")                      # no name, not paired: dropped
    fake.add_device("11:00:00:00:00:05", "", paired=True)         # no name but paired: kept
    fake.add_device("11:00:00:00:00:06", "NoSignal")
    fake.add_device("11:00:00:00:00:07", "Found Later", rssi=-30, visible=False)  # only appears during discovery
    fake.add_device("11:00:00:00:00:08", "P-touch Cube", paired=True)
    out = btadmin.scan(0.3, bus_address=fake.address)
    assert fake.discovery_filter == {"Transport": "bredr"}
    assert [c[0] for c in fake.calls if c[0] in ("StartDiscovery", "StopDiscovery")] == ["StartDiscovery", "StopDiscovery"]
    assert not fake.discovering
    printers = [d["address"] for d in out if d["is_printer"]]
    assert printers == ["11:00:00:00:00:03", "11:00:00:00:00:02", "11:00:00:00:00:08"]  # rssi desc, None last
    assert out[:3] == [d for d in out if d["is_printer"]]
    rest = [d["address"] for d in out if not d["is_printer"]]
    assert rest == ["11:00:00:00:00:07", "11:00:00:00:00:01", "11:00:00:00:00:06", "11:00:00:00:00:05"] \
        or rest == ["11:00:00:00:00:07", "11:00:00:00:00:01", "11:00:00:00:00:05", "11:00:00:00:00:06"]
    assert "11:00:00:00:00:04" not in [d["address"] for d in out]
    nosig = next(d for d in out if d["name"] == "NoSignal")
    assert nosig["rssi"] is None and nosig["paired"] is False
    assert set(out[0]) == {"address", "name", "paired", "trusted", "connected", "rssi", "is_printer"}


def test_scan_powers_adapter_on_and_survives_foreign_discovery(fake):
    fake.set_powered(False)
    time.sleep(0.1)
    fake.discovering = True  # somebody else is scanning: InProgress must not break us
    fake.add_device(A, "PT-P710BT", rssi=-50)
    out = btadmin.scan(0.2, bus_address=fake.address)
    assert fake.powered and [d["address"] for d in out] == [A]
    assert fake.discovering is True and ("StopDiscovery",) not in fake.calls


@pytest.mark.parametrize("flow", ["just_works", "pin", "passkey", "confirm", "authorize", "service", "display"])
def test_pair_success_flows(fake, flow):
    st = fake.add_device(A, "PT-P710BT", rssi=-50, pair_flow=flow, pin="0000")
    dev = btadmin.pair(A, bus_address=fake.address)
    assert dev["paired"] and dev["trusted"] and dev["is_printer"] and st.trusted
    assert ("RegisterAgent", "NoInputNoOutput") in fake.calls
    assert fake.agent is None and any(c[0] == "UnregisterAgent" for c in fake.calls)
    if flow == "pin":
        assert st.agent_results == ["0000"]
    if flow == "passkey":
        assert st.agent_results == [0]


def test_pair_custom_pin(fake):
    fake.add_device(A, "PT-P710BT", pair_flow="pin", pin="1234")
    assert btadmin.pair(A, pin="1234", bus_address=fake.address)["paired"]
    fake.add_device(B, "PT-P710BT", pair_flow="passkey", pin="1234")
    assert btadmin.pair(B, pin="1234", bus_address=fake.address)["paired"]


def test_pair_wrong_pin_unregisters_agent(fake):
    fake.add_device(A, "PT-P710BT", pair_flow="pin", pin="9999")
    with pytest.raises(BtAdminError) as e:
        btadmin.pair(A, pin="0000", bus_address=fake.address)
    assert e.value.reason == "pairing_failed" and "0000" in e.value.message
    assert fake.agent is None


def test_pair_already_paired_is_success_and_sets_trusted(fake):
    st = fake.add_device(A, "PT-P710BT", paired=True, trusted=False)
    dev = btadmin.pair(A, bus_address=fake.address)
    assert dev["paired"] and dev["trusted"] and st.trusted
    assert st.pair_calls == 0  # nothing to do


@pytest.mark.parametrize("err,reason", [
    ("org.bluez.Error.AuthenticationFailed", "pairing_failed"),
    ("org.bluez.Error.AuthenticationRejected", "pairing_failed"),
    ("org.bluez.Error.AuthenticationCanceled", "pairing_failed"),
    ("org.bluez.Error.AuthenticationTimeout", "pairing_timeout"),
    ("org.bluez.Error.ConnectionAttemptFailed", "pairing_failed"),
    ("org.bluez.Error.Failed", "pairing_failed"),
    ("org.bluez.Error.InProgress", "busy"),
    ("org.bluez.Error.NotReady", "bluetooth_off"),
])
def test_pair_error_mapping(fake, err, reason):
    st = fake.add_device(A, "PT-P710BT", pair_mode=("error", err, "x"))
    with pytest.raises(BtAdminError) as e:
        btadmin.pair(A, bus_address=fake.address)
    assert e.value.reason == reason and e.value.message
    assert fake.agent is None and any(c[0] == "UnregisterAgent" for c in fake.calls)
    assert not st.trusted and not st.paired


def test_pair_page_timeout_means_asleep(fake):
    fake.add_device(A, "PT-P710BT", pair_mode=("error", "org.bluez.Error.ConnectionAttemptFailed", "br-connection-page-timeout"))
    with pytest.raises(BtAdminError) as e:
        btadmin.pair(A, bus_address=fake.address)
    assert e.value.reason == "asleep"


def test_pair_timeout_cancels_and_unregisters(fake):
    fake.add_device(A, "PT-P710BT", pair_mode="hang")
    t0 = time.monotonic()
    with pytest.raises(BtAdminError) as e:
        btadmin.pair(A, timeout=0.6, bus_address=fake.address)
    assert e.value.reason == "pairing_timeout" and time.monotonic() - t0 < 3
    assert ("CancelPairing", A) in fake.calls and fake.agent is None


def test_pair_discovers_unknown_device_then_not_found(fake, monkeypatch):
    monkeypatch.setattr(btadmin, "FIND_SECONDS", 1.0)
    fake.add_device(A, "PT-P710BT", visible=False)
    assert btadmin.pair(A, bus_address=fake.address)["paired"]
    with pytest.raises(BtAdminError) as e:
        btadmin.pair(C, bus_address=fake.address)
    assert e.value.reason == "not_found"
    assert not fake.discovering


def test_pair_agent_registration_failure_and_alreadyexists_agent(fake):
    fake.add_device(A, "PT-P710BT")
    fake.register_agent_error = ("org.bluez.Error.AlreadyExists", "Already Exists")
    # another agent is registered: we still attempt to pair (and our flow has no agent -> failure)
    with pytest.raises(BtAdminError) as e:
        btadmin.pair(A, bus_address=fake.address)
    assert e.value.reason == "pairing_failed"
    fake.register_agent_error = ("org.bluez.Error.NotReady", "off")
    with pytest.raises(BtAdminError) as e:
        btadmin.pair(A, bus_address=fake.address)
    assert e.value.reason == "bluetooth_off"


def test_forget(fake):
    fake.add_device(A, "PT-P710BT", paired=True, trusted=True)
    btadmin.forget(A, bus_address=fake.address)
    assert A not in fake.devs and any(c[0] == "RemoveDevice" for c in fake.calls)
    btadmin.forget(A, bus_address=fake.address)  # unknown: no-op


def test_connect_test_ok(fake):
    st = fake.add_device(A, "PT-P710BT", paired=True)
    r = btadmin.connect_test(A, bus_address=fake.address)
    assert r["ok"] is True and r["reason"] == "ok" and r["seconds"] < 3 and r["message"]
    assert st.disconnects == 1 and not st.connected
    assert fake.profile is None
    assert len(st.connect_times) == 1


def test_connect_test_unknown_device(fake):
    r = btadmin.connect_test(C, bus_address=fake.address)
    assert (r["ok"], r["reason"]) == (False, "not_paired")


@pytest.mark.parametrize("err,text,reason", [
    ("org.bluez.Error.Failed", "br-connection-page-timeout", "asleep"),
    ("org.bluez.Error.Failed", "host-down", "asleep"),
    ("org.bluez.Error.ConnectionAttemptFailed", "page-timeout", "asleep"),
    ("org.bluez.Error.Failed", "br-connection-busy", "busy"),
    ("org.bluez.Error.InProgress", "Operation already in progress", "busy"),
    ("org.bluez.Error.AuthenticationFailed", "Authentication Failed", "not_paired"),
    ("org.bluez.Error.Failed", "Device is not paired", "not_paired"),
    ("org.bluez.Error.NotReady", "Resource Not Ready", "bluetooth_off"),
    ("org.bluez.Error.Failed", "Input/output error", "error"),
])
def test_connect_test_classification(fake, err, text, reason):
    st = fake.add_device(A, "PT-P710BT", paired=True, connect=(("error", err, text),))
    t0 = time.monotonic()
    r = btadmin.connect_test(A, timeout=1.2, bus_address=fake.address)
    assert (r["ok"], r["reason"]) == (False, reason), r
    assert r["message"] and "br-connection" not in r["message"]
    assert time.monotonic() - t0 < 6
    if reason in common.FATAL:
        assert len(st.connect_times) == 1          # no pointless retries
    else:
        assert len(st.connect_times) >= 2          # retried until the deadline
    assert fake.profile is None                    # profile always unregistered


def test_connect_test_retries_then_succeeds(fake):
    st = fake.add_device(A, "PT-P710BT", paired=True, connect=(
        ("error", "org.bluez.Error.Failed", "br-connection-page-timeout"), "ok"))
    r = btadmin.connect_test(A, timeout=10, bus_address=fake.address)
    assert r["ok"] and len(st.connect_times) == 2 and 0.7 < r["seconds"] < 4


def test_connect_test_hang_is_bounded(fake, monkeypatch):
    monkeypatch.setattr(common, "MIN_ATTEMPT", 0.1)
    fake.add_device(A, "PT-P710BT", paired=True, connect=("hang",))
    t0 = time.monotonic()
    r = btadmin.connect_test(A, timeout=1.0, bus_address=fake.address)
    assert (r["ok"], r["reason"]) == (False, "asleep")
    assert 0.9 < r["seconds"] < 3 and time.monotonic() - t0 < 4
    assert fake.profile is None


def test_connect_test_bluetooth_off_and_no_dbus(fake):
    fake.add_device(A, "PT-P710BT", paired=True)
    fake.set_powered(False)
    time.sleep(0.1)
    assert btadmin.connect_test(A, bus_address=fake.address)["reason"] == "bluetooth_off"
    r = btadmin.connect_test(A, bus_address="unix:path=/nonexistent/bus")
    assert (r["ok"], r["reason"]) == (False, "no_dbus")


def test_classify_names():
    assert common.classify("org.bluez.Error.AccessDenied", "") == "permission"
    assert common.classify("org.freedesktop.DBus.Error.ServiceUnknown", "") == "no_dbus"
    assert common.classify("org.bluez.Error.DoesNotExist", "") == "not_found"
    assert common.classify("org.bluez.Error.AlreadyExists", "") == "error"
    assert common.classify("org.bluez.Error.AuthenticationTimeout", "", "pair") == "pairing_timeout"


def test_agent_methods_have_correct_signatures():
    from dbus_fast.service import ServiceInterface
    events = []
    agent = btadmin._make_agent("0042", events)
    assert isinstance(agent, ServiceInterface) and agent.name == "org.bluez.Agent1"
    sigs = {m.name: (m.in_signature, m.out_signature) for m in ServiceInterface._get_methods(agent)}
    assert sigs == {
        "Release": ("", ""), "RequestPinCode": ("o", "s"), "DisplayPinCode": ("os", ""),
        "RequestPasskey": ("o", "u"), "DisplayPasskey": ("ouq", ""), "RequestConfirmation": ("ou", ""),
        "RequestAuthorization": ("o", ""), "AuthorizeService": ("os", ""), "Cancel": ("", "")}
