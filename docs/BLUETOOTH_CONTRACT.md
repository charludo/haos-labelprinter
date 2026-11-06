# Printer setup, Bluetooth pairing and connect: shared contract

Three pieces are built in parallel against this document (P: Bluetooth admin library, H: Home Assistant
wiring, F: frontend). **Do not change this file**; if something is impossible, work around it inside your own
files and report it. Repo root `~/claude-projects/ha-brother-ptouch/`, integration dir
`custom_components/brother_ptouch/`. Read `docs/EDITOR_CONTRACT.md` for the existing editor contract; this
extends it.

## 0. Hard rules (all agents)
* **Never touch a real Bluetooth radio or real devices.** A background experiment is using the user's printer
  (`EC:79:49:63:67:DF`) over Bluetooth for the next ~75 minutes and any activity would corrupt it. No
  `StartDiscovery`, `Pair`, `Connect`, `ConnectProfile`, `RemoveDevice`, no `bluetoothctl`, no connecting to
  the system D-Bus object `org.bluez` at all. Test with fakes only (for D-Bus: a private `dbus-daemon --session`
  with exported fake `org.bluez` objects if `dbus-daemon` exists, otherwise a fake bus object). Never hard-code
  that address or any real address in the repo.
* Only edit the files you own. No `git commit/push/checkout`. Tests: core `.venv/bin/python -m pytest -q
  -p no:cacheprovider tests/<file>`; HA `PYTHONPATH=. .venv-ha/bin/python -m pytest -q -p no:cacheprovider
  tests/<file>`; frontend `cd custom_components/brother_ptouch/frontend && node dev/tests/<file>.mjs`.
* Python core (`ptouch/`) has no Home Assistant imports, relative imports only, blocking/sync API (callers use
  an executor).

## 1. Failure reasons (shared vocabulary)
`reason` is one of: `ok`, `asleep` (page timeout / no answer: printer off, out of range or radio asleep),
`not_paired`, `bluetooth_off` (adapter powered off), `no_adapter`, `no_dbus` (cannot reach the system bus /
BlueZ), `no_library` (dbus-fast missing), `busy` (printer is connected to another device or resource busy),
`pairing_failed`, `pairing_timeout`, `not_found` (address not seen), `permission`, `error` (anything else).
`TransportError` (ptouch/errors.py) gains an optional backward-compatible attribute `reason: str = "error"`
(`TransportError(msg, reason="asleep")`).

User-facing wording the UI uses (frontend owns the final copy): asleep = "The printer isn't answering. Press its
power button to switch it on, make sure no phone is connected to it, then try again."; not_paired = "This
printer isn't paired with Home Assistant yet."; bluetooth_off = "Bluetooth is switched off on the Home Assistant
host."; busy = "The printer is connected to something else (a phone?). Disconnect it and try again.";
no_dbus/no_adapter/no_library = "Home Assistant can't use Bluetooth here. Use USB or the network bridge."

## 2. Piece P: `ptouch/btadmin.py` (new) and `ptouch/bluez.py` (edit), `ptouch/errors.py` (add `reason` only)
Owner files: `ptouch/btadmin.py`, `ptouch/bluez.py`, `ptouch/errors.py`, `tests/test_btadmin.py`,
`tests/test_bluez_transport.py`, `docs/BLUETOOTH.md`.
```python
class BtAdminError(PtouchError):  reason: str; message: str     # reason from section 1
def available(bus_address=None) -> tuple[bool, str]             # (ok, reason): "ok"|"no_library"|"no_dbus"|"no_adapter"|"bluetooth_off"
def adapters(bus_address=None) -> list[dict]                    # [{"path","address","name","powered"}]
def power_on(adapter=None, bus_address=None) -> None
def scan(duration=8.0, *, adapter=None, bus_address=None) -> list[dict]
def pair(address, *, pin="0000", timeout=45.0, adapter=None, bus_address=None) -> dict
def forget(address, *, bus_address=None) -> None
def connect_test(address, *, timeout=20.0, bus_address=None) -> dict   # {"ok","reason","seconds","message"}; never raises for expected failures; disconnects afterwards
```
`bus_address=None` means the real system bus; tests pass the address of a private bus.
`scan`: Bluetooth Classic discovery only (`SetDiscoveryFilter` Transport `bredr`), stops discovery after
`duration`, returns BtDevice dicts `{"address","name","paired","trusted","connected","rssi"(int|None),
"is_printer"(bool: name starts with "PT-", "P-touch" or "Brother", case-insensitive)}` including already known
devices, printers first, then by rssi descending; ignores devices without a name unless they are paired.
`pair`: registers an `org.bluez.Agent1` (capability `NoInputNoOutput`, auto-accepts RequestConfirmation /
RequestAuthorization / AuthorizeService, answers RequestPinCode with `pin` and RequestPasskey with `int(pin)`),
calls `Device1.Pair`, then sets `Trusted=True`, unregisters the agent in all cases, returns the BtDevice dict;
already-paired is success; maps BlueZ error names (AuthenticationFailed/Rejected/Canceled, ConnectionAttempt
Failed, page timeout...) to `BtAdminError(reason, friendly message)`. `forget`: `Adapter1.RemoveDevice`.
`connect_test`: same `ConnectProfile(SPP)` approach as `BlueZTransport` with retries up to `timeout`, measures
seconds, classifies failures (`br-connection-page-timeout`/`host-down` => `asleep`, `not paired`/
`AuthenticationFailed` => `not_paired`, `NotReady`/powered off => `bluetooth_off`, `InProgress`/`Busy`/
`br-connection-busy` => `busy`).
`bluez.py`: `BlueZTransport` (and `RFCOMMTransport` in transport.py is not yours, leave it) gets a
`wake_timeout: float | None` attribute (seconds; None = default 12 s) that bounds the total time spent
retrying `ConnectProfile`; failures raise `TransportError(msg, reason=...)` using the same classification, with
messages that are plain English (no raw BlueZ codes in the message). `Transport` base class in transport.py is
**not yours**: H adds `wake_timeout` to it; you only read `self.wake_timeout` with `getattr(self, "wake_timeout", None)`.
Also research and write `docs/BLUETOOTH.md`: what is known/unknown about PT-P710BT Bluetooth (pairing, PIN,
auto power-off, sleep; use the web: load WebSearch/WebFetch via ToolSearch `select:WebSearch,WebFetch`; mark
anything unverified; Brother pages often return only summaries), how our pairing works, and troubleshooting.
Do not state that the printer can be woken over Bluetooth; say it is being measured.

## 3. Piece H: Home Assistant wiring
Owner files: `bluetooth_api.py` (new), `printer_api.py` (new, may be merged into one), `button.py` (new),
`config_flow.py`, `__init__.py`, `const.py`, `coordinator.py`, `entity.py`, `sensor.py`, `binary_sensor.py`
(only if needed), `ptouch/transport.py` (ONLY adding `wake_timeout: float | None = None` to the `Transport`
base class and honouring it in `RFCOMMTransport` retry loop), `editor_api.py` (ONLY the `printers` command rows
and registering the new modules' commands), `services.yaml`, `translations/en.json`, `tests/test_bluetooth_ha.py`,
`tests/test_ha.py` (keep passing). All new WebSocket commands are admin-only, prefix `brother_ptouch/`, errors
use HA error frames with `code` (see below) and a plain-English `message`. `btadmin` calls run in the executor;
before P's module exists on disk, import lazily and test with fakes; re-test with the real module at the end.
* `bluetooth/status` {} -> `{"available": bool, "reason": str, "adapters": [..]}`
* `bluetooth/scan` {duration?: 3..20 (8)} -> `{"devices":[BtDevice + "configured": bool]}` (`configured` = an entry with that address exists)
* `bluetooth/pair` {address, pin?} -> `{"device": BtDevice}`; error codes `bluetooth_unavailable`, `device_not_found`, `pairing_failed`, `pairing_timeout`
* `bluetooth/forget` {address} -> `{}`
* `bluetooth/connect` {entry_id} -> `{"ok": bool, "reason": str, "seconds": float, "message": str}`; uses
  the entry's transport with `wake_timeout` = the entry's `wake_seconds` option (default 20); on success
  refreshes the coordinator; expected failures are returned as `ok:false`, not as error frames
* `printers/add` {transport: usb|bluetooth|bridge, serial?, address?, channel?, url?, token?, name?} -> `{"entry_id","title"}`
  implemented by `hass.config_entries.flow.async_init(DOMAIN, context={"source": "import"}, data=...)` and a new
  `async_step_import` that validates with `get_status`, sets the unique id like the interactive steps and creates the
  entry; error codes `cannot_connect` (message carries the reason text), `already_configured`
* `printers/remove` {entry_id} -> `{}`; `printers/rename` {entry_id, name} -> `{}` (updates entry title)
* `printers/test_print` {entry_id} -> `{}`: prints a small test label (`render_text`) with the text "Printer OK", the
  date and the tape width via `coordinator.async_print` (batching applies)
* existing `printers` command rows gain: `name`, `transport`, `address`/`url`/`serial` (whichever applies, token
  never exposed), `online` (bool), `reason` (section 1), `message` (friendly text or ""), and
  `tape: {"width_mm": 3.5|6|9|12|18|24, "type": str, "colour": str, "text_colour": str} | null`; keep the old
  fields (`entry_id`, `title`, `tape_mm`, `state`)
* Button entity "Connect Bluetooth" for bluetooth-transport entries (press = same as `bluetooth/connect`)
* Options flow: add `wake_seconds` (0..60, default 20) next to the existing options
* Coordinator: store `last_reason`/`last_message` from `TransportError.reason` on update failures; polling uses a
  short `wake_timeout` (8 s), printing uses the `wake_seconds` option; user-visible `HomeAssistantError` messages
  for print failures use the friendly text for the reason
* Config flow: Bluetooth step becomes friendly: when `btadmin.available()` is ok, scan (`async_show_progress`), let
  the user pick a printer from the list (the manual address option stays as "Enter address manually"), pair
  automatically if not paired (progress step with the instruction text), then validate and create the entry. When
  not available fall back to the existing manual step with an explanation.

## 4. Piece F: frontend (`frontend/` only)
Owner: everything under `custom_components/brother_ptouch/frontend/` (plus a short section appended to
`docs/MOBILE_TESTING.md`). Implements the UX in section 5 against the WebSocket API of section 3 (the existing
editor API is in docs/EDITOR_CONTRACT.md). Extend `frontend/dev/mock_backend.py` with a **stateful** fake of every
new command (a couple of fake printers, a scan list with a printer and some phones/headsets, pairing that takes
2 s and can be made to fail, connect that can return `asleep`/`busy`) so the whole flow can be driven in a browser
without hardware. Add pure-logic node tests; verify with the Playwright setup at
`/tmp/claude-1000/-home-apollo/92063214-b67a-42a7-94ee-7ce31da03687/scratchpad/ui-venv` (see
scratchpad/m and scratchpad/g scripts) on desktop, phone (touch) and dark mode, and LOOK at screenshots.

## 5. UX (decided with the user)
* **Top-bar printer chip**: dot + name + short status ("12 mm", "Asleep", "Cover open", "No printer"). Dot: green
  online & tape, amber offline/asleep/busy/no tape, red printer error, grey no printer. Clicking opens the
  **printer drawer** (right-side drawer on desktop, full-screen sheet on phone).
* **Drawer**: list of printers (name, connection icon+detail, state sentence, tape line "12 mm laminated, white
  tape, black text"), per printer: **Connect** (Bluetooth printers; shows progress "Trying to reach the printer…",
  then result with the friendly reason and what to do), **Test print**, **Rename**, **Remove** (confirm), and
  **+ Add printer**. A failed print shows the reason sentence and a **Retry**; while a print waits for a sleeping
  printer, show "Waiting for the printer… (up to N s)".
* **Add printer wizard** (steps with Back/Next, progress dots): 1 How is it connected? three cards: USB, Bluetooth,
  Network bridge (advanced, asks URL + optional token). 2 Bluetooth: checklist (switch the printer on, disconnect
  phones from it, keep it close), **Scan** (progress), list of devices with signal bars, printers highlighted and
  listed first, others collapsed under "Other devices"; each row shows Paired/Not paired and **Pair** or
  **Select**; pairing shows progress and the failure reason with Retry; if `bluetooth/status.available` is false
  show the reason text and steer to USB/bridge. 3 Test: add the printer (`printers/add`), then show the detected tape
  ("Connected: 12 mm laminated"). 4 Name it (default from the device name) and Done; the new printer is selected.
* **First run** (no printers): the editor still works with 12 mm default tape; Print is replaced by a prominent
  "Set up your printer" button that opens the wizard.
* Everything keyboard accessible, 44 px touch targets, safe areas, HA theme variables, no `alert/confirm`.
