# Brother P-touch (PT-P710BT) for Home Assistant

Print labels from automations, scripts and dashboards on a Brother **PT-P710BT**
(also PT-P700 / PT-P750W, same raster protocol).

> **Status: 0.1.0.** Verified on a real PT-P710BT over USB, Bluetooth (direct) and the bridge
> (Bluetooth): status, text printing and orientation. The Home Assistant layer is covered by tests
> against a fake printer; not yet run inside a live Home Assistant.

## Three ways to connect

| Mode | Use when | Needs |
|---|---|---|
| **USB** | Printer is plugged into the HA host | `libusb-1.0` on the host; `/dev/bus/usb` visible to HA (udev permissions) |
| **Bluetooth** | HA host has a BT adapter and BlueZ | Printer paired with the host. Enter its MAC (RFCOMM socket) or a device path (`/dev/rfcomm0`, `/dev/usb/lp0`) |
| **Bridge** | Printer is far from HA, or HA OS can't reach it | `bridge/ptouch_bridge.py` on any Linux box (Pi, PC) next to the printer |

> The PT-P710BT speaks **Bluetooth Classic (RFCOMM)**, not BLE, so Home Assistant's BLE stack and
> ESPHome Bluetooth proxies can't carry it. Instead the integration uses what HA already has on the host:
> BlueZ over the system D-Bus (`dbus-fast`, which HA ships) and its `Profile1` API to open the serial link,
> so no raw sockets are needed. If D-Bus isn't reachable it falls back to a raw RFCOMM socket. If neither
> works (e.g. no Bluetooth on the HA machine) use the bridge on another machine. Pairing is still done once
> on the host with `bluetoothctl` (HA has no UI for pairing Classic devices).

### Bluetooth pairing (host or bridge machine)
```
bluetoothctl
  scan on          # printer shows as PT-P710BT####
  pair  AA:BB:CC:DD:EE:FF
  trust AA:BB:CC:DD:EE:FF
```
Only one device can hold the RFCOMM link: disconnect your phone's P-touch app first. Channel is 1
on the models we know of (`sdptool browse AA:BB:...` to check).

### Bridge
```
python3 bridge/ptouch_bridge.py --usb --token SECRET                    # USB
python3 bridge/ptouch_bridge.py --bluetooth AA:BB:CC:DD:EE:FF --token SECRET
python3 bridge/ptouch_bridge.py --device /dev/usb/lp0 --token SECRET
```
Docker (from repo root): `docker build -f bridge/Dockerfile -t ptouch-bridge .` then
`docker run -d --restart unless-stopped --device /dev/bus/usb -p 8765:8765 -e PTOUCH_BRIDGE_TOKEN=SECRET ptouch-bridge --usb`.
A systemd unit is in `bridge/ptouch-bridge.service`. In HA choose *Bridge* and enter `http://<host>:8765`.
Always set a token; the bridge will print for anyone who can reach it.

## Install
Copy `custom_components/brother_ptouch` into your HA `config/custom_components/` (or add this repo to
HACS as a custom repository), restart, then *Settings → Devices & services → Add integration → Brother P-touch*.
A USB-attached printer is also auto-discovered.

## Entities
`sensor`: status (idle/printing/error), tape width, tape type, tape colour, text colour.
`binary_sensor`: problem (with `errors` attribute), tape loaded. Status is polled every 60 s.

## Services
All take an optional `device_id` (only needed with several printers), `copies`, `auto_cut`, `margin_mm`.
Labels are sized automatically to whatever tape is loaded.

```yaml
action: brother_ptouch.print_text
data:
  text: "Kitchen\nSpices"      # multiple lines auto-fit the tape height
action: brother_ptouch.print_qr
data:
  data: "https://home.example.com/box/42"
  text: "Box 42"
action: brother_ptouch.print_image
data:
  image_path: /config/www/logo.png    # must be in allowlist_external_dirs; or image_url
  dither: false
```

Example: print a label when a shopping-list item is added, a door is left open, etc. just call the service
from any automation; `text` supports templates.

## Saving tape
A P-touch wastes ~25 mm of blank tape (head-to-cutter distance) at the start of every job, and it can't
be avoided or "held" across jobs: the printer finishes and cuts the previous label as soon as a new job starts.
So the integration merges print requests that arrive within a few seconds of each other into **one job**:
one leader, no cut between labels, one cut at the end. Set the window under **Configure** ("Strip window",
default 3 s, 0 = off). Use `cut_each: true` on a service call if you want a cut after every label, or
`copies:` for several of the same label.

## Calibrating orientation (do this once)
Print `brother_ptouch.print_text` with `text: "ABC"`. On the PT-P710BT the default (*Normal*) is correct. If a
different unit prints mirrored or upside down, open **Configure** and pick one of the flip options.

## Things to know / verify on hardware
* The printer must be on **tape (TZe)** with a cassette in; the cover closed.
* USB ID `04F9:20AF` is confirmed for the PT-P710BT. PT-P700 (`2061`) and PT-P750W (`2062`) are also matched but untested.
* **Never send the printer a print command without page data** (e.g. a bare `0x1A`): it faults into a
  flashing-red state until power-cycled. Status polling deliberately sends no `ESC @` (initialize).
* Printable pins per tape follow Brother's PT-P700 raster reference (9 mm = 50 pins, 39 margin, etc.).

## Development
```
python -m venv .venv    && .venv/bin/pip install pillow pytest segno pyusb
.venv/bin/python -m pytest tests/test_core.py            # protocol, renderer, bridge
python -m venv .venv-ha && .venv-ha/bin/pip install pytest-homeassistant-custom-component pyusb segno
PYTHONPATH=. .venv-ha/bin/python -m pytest tests/test_ha.py   # HA integration
```
The protocol core (`custom_components/brother_ptouch/ptouch/`) has no HA imports and is shared by the
integration and the bridge.
