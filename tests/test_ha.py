"""Home Assistant-level tests. Run with the .venv-ha environment."""
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.brother_ptouch.const import DOMAIN
from custom_components.brother_ptouch.ptouch import PrinterError, PrinterStatus, TransportError
from custom_components.brother_ptouch.ptouch.transport import Transport

pytest_plugins = "pytest_homeassistant_custom_component"


def status(width=12, media=0x01, err1=0):
    b = bytearray(32)
    b[0], b[1], b[2], b[3] = 0x80, 0x20, 0x42, 0x30
    b[8], b[10], b[11], b[24], b[25] = err1, width, media, 0x01, 0x08
    return PrinterStatus.parse(bytes(b))


class Fake(Transport):
    def __init__(self):
        self.st, self.jobs, self.fail, self.down = status(), [], None, False

    def get_status(self):
        if self.down:
            raise TransportError("offline")
        return self.st

    def print_job(self, data, pages=1):
        if self.fail:
            raise self.fail
        self.jobs.append((data, pages))


@pytest.fixture(autouse=True)
def _enable(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def _no_real_bluetooth(monkeypatch):
    """Never let a test reach the real BlueZ / system D-Bus (docs/BLUETOOTH_CONTRACT.md section 0)."""
    from custom_components.brother_ptouch import btutil
    monkeypatch.setattr(btutil, "get_btadmin", lambda: None)


@pytest.fixture
def fake():
    f = Fake()
    with patch("custom_components.brother_ptouch.coordinator.make_transport", return_value=f), \
         patch("custom_components.brother_ptouch.config_flow.make_transport", return_value=f):
        yield f


async def setup(hass, data=None):
    entry = MockConfigEntry(domain=DOMAIN, data=data or {"transport": "bridge", "url": "http://x", "token": ""},
                            unique_id="bridge:http://x", options={"batch_window": 0})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_entities(hass: HomeAssistant, fake):
    await setup(hass)
    assert hass.states.get("sensor.brother_p_touch_status").state == "idle"
    assert hass.states.get("sensor.brother_p_touch_tape_width").state == "12"
    assert hass.states.get("sensor.brother_p_touch_tape_type").state == "laminated"
    assert hass.states.get("sensor.brother_p_touch_tape_colour").state == "white"
    assert hass.states.get("binary_sensor.brother_p_touch_problem").state == "off"
    assert hass.states.get("binary_sensor.brother_p_touch_tape_loaded").state == "on"


async def test_print_text_sends_job(hass, fake):
    await setup(hass)
    await hass.services.async_call(DOMAIN, "print_text", {"text": "Hello", "copies": 2}, blocking=True)
    (job, pages), = fake.jobs                  # copies=2 -> ONE job (a 2-label strip)
    assert pages == 1 and job.endswith(b"\x1a") and job.count(b"\x1biz") == 1


async def test_print_qr_and_image(hass, fake, tmp_path):
    from PIL import Image
    await setup(hass)
    await hass.services.async_call(DOMAIN, "print_qr", {"data": "https://example.com", "text": "Hi"}, blocking=True)
    img = tmp_path / "a.png"
    Image.new("RGB", (50, 50), "black").save(img)
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    await hass.services.async_call(DOMAIN, "print_image", {"image_path": str(img)}, blocking=True)
    assert len(fake.jobs) == 2
    hass.config.allowlist_external_dirs = set()
    with pytest.raises(Exception):
        await hass.services.async_call(DOMAIN, "print_image", {"image_path": str(img)}, blocking=True)


async def test_print_refused_on_error_or_no_tape(hass, fake):
    await setup(hass)
    fake.st = status(err1=0b10)  # end of media... any error
    with pytest.raises(HomeAssistantError, match="end_of_media"):
        await hass.services.async_call(DOMAIN, "print_text", {"text": "x"}, blocking=True)
    fake.st = status(width=0, media=0)
    with pytest.raises(HomeAssistantError, match="tape"):
        await hass.services.async_call(DOMAIN, "print_text", {"text": "x"}, blocking=True)
    fake.st = status()
    fake.fail = PrinterError(["cover_open"])
    with pytest.raises(HomeAssistantError, match="cover_open"):
        await hass.services.async_call(DOMAIN, "print_text", {"text": "x"}, blocking=True)
    assert not fake.jobs


async def test_unavailable_when_offline(hass, fake):
    entry = await setup(hass)
    fake.down = True
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.brother_p_touch_status").state == "unavailable"


async def test_setup_retries_when_offline(hass, fake):
    fake.down = True
    entry = MockConfigEntry(domain=DOMAIN, data={"transport": "usb", "serial": ""}, options={"batch_window": 0})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state.name == "SETUP_RETRY"


@pytest.mark.parametrize("choice,form,expected", [
    ("usb", {"serial": ""}, {"transport": "usb", "serial": ""}),
    ("bluetooth", {"address": "aa:bb:cc:dd:ee:ff", "channel": 1},
     {"transport": "bluetooth", "address": "AA:BB:CC:DD:EE:FF", "channel": 1}),
    ("bridge", {"url": "http://10.0.0.5:8765/", "token": "t"},
     {"transport": "bridge", "url": "http://10.0.0.5:8765", "token": "t"}),
])
async def test_config_flow(hass, fake, choice, form, expected):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert r["type"] is FlowResultType.MENU
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"next_step_id": choice})
    assert r["type"] is FlowResultType.FORM
    r = await hass.config_entries.flow.async_configure(r["flow_id"], form)
    assert r["type"] is FlowResultType.CREATE_ENTRY and r["data"] == expected


async def test_config_flow_cannot_connect(hass, fake):
    fake.down = True
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"next_step_id": "bridge"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"url": "http://x", "token": ""})
    assert r["type"] is FlowResultType.FORM and r["errors"] == {"base": "cannot_connect"}


async def test_usb_discovery(hass, fake):
    from homeassistant.helpers.service_info.usb import UsbServiceInfo
    info = UsbServiceInfo(device="/dev/bus/usb/001/002", vid="04F9", pid="20AF",
                          serial_number="E1234", manufacturer="Brother", description="PT-P710BT")
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "usb"}, data=info)
    assert r["step_id"] == "discovery_confirm"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
    assert r["type"] is FlowResultType.CREATE_ENTRY and r["data"]["serial"] == "E1234"


async def test_options_orientation_applied(hass, fake):
    entry = await setup(hass)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"orientation": "rotate_180"})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "print_text", {"text": "x"}, blocking=True)
    assert fake.jobs


async def test_requests_in_window_become_one_strip(hass, fake):
    import asyncio
    entry = await setup(hass)
    hass.config_entries.async_update_entry(entry, options={"batch_window": 0.3})
    await hass.async_block_till_done()
    calls = [hass.services.async_call(DOMAIN, "print_text", {"text": t, "copies": 2}, blocking=True)
             for t in ("one", "two", "three")]
    await asyncio.gather(*calls)
    (job, pages), = fake.jobs                      # ONE job for all three requests (6 labels)
    assert pages == 1 and job.count(b"\x1biz") == 1 and job.endswith(b"\x1a")
    assert b"\x1bid\x1c\x00" not in job


async def test_bad_request_fails_alone(hass, fake):
    import asyncio
    entry = await setup(hass)
    hass.config_entries.async_update_entry(entry, options={"batch_window": 0.3})
    await hass.async_block_till_done()
    good = hass.services.async_call(DOMAIN, "print_text", {"text": "ok"}, blocking=True)
    bad = hass.services.async_call(DOMAIN, "print_qr", {"data": "x" * 3000}, blocking=True)
    res = await asyncio.gather(good, bad, return_exceptions=True)
    assert res[0] is None and isinstance(res[1], Exception)
    assert len(fake.jobs) == 1 and fake.jobs[0][1] == 1
