# Testing the label editor on a real phone

The editor (`custom_components/brother_ptouch/frontend/`) was developed with emulated touch devices
(Chromium via Playwright, Pixel 7 descriptor, CDP `Input.dispatchTouchEvent`). WebKit/iOS could **not** be run
on the dev machine (missing system libraries), and nothing has been tried inside the real Companion app yet.
This file tells you how to do that, and what to look for.

## How the phone UI works (screens narrower than 900 px, or HA `narrow`)

The panel no longer squeezes the desktop three-pane editor onto a phone. On a narrow screen it is a small app with two screens:

* **Home** (opens first): top bar with the HA menu button (fires `hass-toggle-menu`), the title "Labels" and the printer chip
  (opens the printer drawer). A status card appears only when the printer needs attention (offline with the reason and a
  **Connect** button, no tape, error, or "Set up your printer" when none exists). Two big buttons, **New label** and
  **From template**, then **Your labels**: one card per saved design with a live preview thumbnail (loaded lazily, 3 at a time,
  cached per design and tape), the name, a three-dot menu (Open, Duplicate, Delete with an in-app confirmation) and a friendly empty state.
* **Editor** (tap New, a template or a saved label): back arrow (asks Save / Discard / Keep editing when there are unsaved
  changes), the label name (tap to rename), undo/redo, **Print**, and a three-dot menu (Save, tape and length, fit, template, delete).
  Below it a strip with the tape/length chip (opens "Label settings": tape, length, padding, variables), a **Save** chip while
  there are unsaved changes, and a Fit/zoom chip. The canvas fits the label width by default (pinch to zoom, drag to pan, long
  labels scroll sideways) and takes all the remaining height. Tapping empty canvas deselects.
* **Bottom toolbar**: nothing selected = Text, Icon, QR code, Barcode, More; element selected = Edit, Copy, Rotate, Raise, Lower, Delete.
  Adding an element or tapping **Edit** (or double tap / long press on the element) opens the **properties bottom sheet** with three
  snap points (peek, half, full: drag the handle or the header, or tap the handle). The canvas area shrinks and scrolls so the
  selected element always stays visible above the sheet. **Done** closes it. In landscape the sheet is a side panel.
* **Print** opens a small sheet: preview, printer, tape check, copies stepper and a big Print button, then the waiting / failed
  (Try again, Printers) / sent states.
* **Back button**: the editor, the properties sheet and every sheet or dialog (gallery, printers, wizard, print, menus, confirmations)
  push a history entry (`history.pushState`, same URL), so the Android Back button / browser back / iOS edge swipe closes the topmost
  one first, then leaves the editor for Home, then leaves the panel as usual. A reload while editing restores the open label
  (id and unsaved draft are kept in `sessionStorage`).
* **Host awareness**: the panel is `height:100%` of the HA host, uses no `100vh` and no `position:fixed`, and does **not** add safe-area
  padding: HA's `ha-panel-custom` already pads the panel host (the panel is registered with `handle_safe_area` false, the default).
  Overlays are `position:absolute` inside the panel, there is one scroll container per screen. When the soft keyboard is up
  (`visualViewport`) the panel shrinks to the visible area, secondary bars hide and the sheet uses all remaining height.
* Inputs are 16 px, other text at least 14 px, touch targets at least 44 px. Rotation is in 90 degree steps only.
* Desktop (900 px and wider) is unchanged: three panes, no history entries.

## (a) Dev harness on a phone over the LAN

The harness uses the real Python renderer but a **mock** backend: saving keeps designs in memory, printing only logs.

```bash
cd ~/claude-projects/ha-brother-ptouch
.venv/bin/python custom_components/brother_ptouch/frontend/dev/mock_backend.py --host 0.0.0.0 --port 8765
ip -4 addr show | grep inet        # find this computer's LAN address, e.g. 192.168.1.20
```

Open `http://192.168.1.20:8765/dev/index.html?narrow=1` on the phone (same Wi-Fi). Add `&theme=dark` for dark mode.
`?narrow=1` makes the harness behave like HA's narrow mode (shows the menu button; it only dispatches the
`hass-toggle-menu` event, nothing opens in the harness).

Warnings:
* `--host 0.0.0.0` exposes an **unauthenticated** server to everyone on that network. Default is `127.0.0.1`
  (the phone cannot reach it). Stop it when done. A firewall may need `sudo ufw allow from 192.168.1.0/24 to any port 8765`.
* "Print" in the harness is a mock: it prints a line to the server log and sends nothing to any printer.
* The harness loads MDI icons from a CDN and Google Fonts previews, so the phone needs internet access.
* Plain `http://` over the LAN is fine for this panel (no service workers, camera or clipboard APIs are used).
* Alternative without opening the LAN: `adb reverse tcp:8765 tcp:8765` (Android, USB debugging) and browse to
  `http://127.0.0.1:8765/dev/index.html`.

Remote debugging of the phone browser: Android Chrome via `chrome://inspect` on the computer; iOS Safari via
Safari > Develop > your iPhone (Settings > Safari > Advanced > Web Inspector enabled).

## (b) Inside the Home Assistant Companion app

### Installing the editor branch

The editor branch is `label-editor` of `https://github.com/thatgoodpickle/haos-labelprinter` (as named in `manifest.json`).

* **Manual copy (most reliable).** Check out the branch on a computer, copy
  `custom_components/brother_ptouch/` into `<HA config>/custom_components/brother_ptouch/` (Samba/SSH/File editor
  add-on), then restart Home Assistant (Settings > System > Restart).
* **HACS custom repository.** HACS > menu > Custom repositories > add the repo URL, category *Integration*.
  After adding, open the repository in HACS > three dots > **Redownload** > "Need a different version?" and pick the
  branch/commit if it is offered. UNVERIFIED: whether HACS lists non-default branches (it reliably lists releases and
  the default branch). If the branch is not offered, use the manual copy or publish a pre-release tag from the branch.
  Restart HA afterwards.
* The panel appears in the sidebar as **Labels** (admin users only). Its URL is `/brother-ptouch`.

### Getting the new JavaScript after an update (cache)

The panel module is loaded as `/brother_ptouch_static/brother-ptouch-panel.js?v=<manifest version>`; the browser/WebView
may keep the old copy. Note that the imported `lib/*.js` files do **not** carry that query string.

1. Easiest: bump `"version"` in `manifest.json` for each test build **and** restart HA (changes the `?v=` of the entry
   file). Because `lib/*.js` are cached independently, also do one of the steps below if behaviour does not change.
2. Android: Settings > Apps > Home Assistant > Storage > **Clear cache** (not "Clear data": that logs you out).
   Or in the app: Settings > Companion App > Troubleshooting (log/debug options live here) and force-stop the app.
   Updating "Android System WebView" via Play Store can also matter (very old WebViews lack newer CSS).
3. iOS: swipe the app away (force quit) and reopen; pull down on a page to refresh (documented by the companion docs).
   If the old version persists, log out and in again (an in-app cache reset option was not confirmed).
4. Last resort: log out and in again (Android docs advise against uninstalling because of auto-backup).
5. For fast iteration, `chrome://inspect` > Application > Clear storage / "Disable cache" while DevTools are open (Android).

### Remote debugging

* **Android** (confirmed from Companion/Chrome docs): in the app, Settings > Companion App > Troubleshooting, enable
  **Web debugging / Chrome remote debugging** (wording varies by app version). Enable USB debugging on the phone, connect
  by USB, open `chrome://inspect/#devices` in desktop Chrome, find "Home Assistant" and click **inspect**. The panel
  lives in nested shadow DOM; use `$0` / the Elements tree, and the device toolbar is not needed (you are on the real device).
  If the app is not listed: make sure the debug toggle is on, open the Labels panel, refresh `chrome://inspect`.
* **iOS**: UNVERIFIED. Apple only allows Safari Web Inspector on a WKWebView if the app sets `isInspectable = true`
  (iOS 16.4+) or runs a debug build; Settings > Safari > Advanced > Web Inspector must be on and the iPhone must be
  connected to a Mac (Safari > Develop > iPhone). I could not confirm that release builds of the Companion app set that
  flag. If the Develop menu does not list the app, assume it is not inspectable and debug with the harness over the LAN
  in iOS Safari instead (same engine, but no Companion chrome), or use a TestFlight/beta build and check there.
  Fallback for field diagnosis: the panel shows server errors inline; browser console errors are not visible without inspection.

## (c) Manual checklist (phone, portrait first, then landscape)

Use a 360-430 px wide phone. Expected results in parentheses. Steps marked (rig) were also run in the real-HA rig (see the end).

1. Open Labels from the sidebar. (Opens on Home, not the editor; no horizontal page scroll; top bar starts at the very top of the panel with no dead band above it.) (rig)
2. Tap the menu icon at top left. (HA sidebar opens. In wide/tablet layout the icon is absent.) (rig: event fires)
3. Look at Home with no saved labels. (Friendly empty state; New label and From template buttons; printer chip with a coloured dot.)
4. Switch the printer off or make it unreachable and reload. (Amber status card: "... is offline", the reason, **Connect** and **Printers**; Connect shows progress and the outcome.)
5. With no printer configured. (Card "Set up your printer" opens the wizard.)
6. Tap **New label**. (Editor opens, canvas fits the width and fills the height, toolbar shows Text / Icon / QR code / Barcode / More.) (rig)
7. Tap **Text**. (Element appears selected, the properties sheet opens at the peek height with the text box visible; the element is not covered.) (rig)
8. Drag the sheet handle up and down, flick it, tap the handle. (Snaps to peek / half / full; fast flick down closes it; Done closes it.) (rig)
9. Type in the text box. (Keyboard opens; sheet stays above it with fields reachable; top strip and toolbar are hidden meanwhile; layout returns after closing the keyboard.) (rig: keyboard simulated by shrinking the viewport)
10. Scroll the sheet to the end at half height. (Font, weight, size, alignment, position fields all reachable; checkboxes are easy to hit.)
11. Tap **Done**. (Toolbar changes to Edit / Copy / Rotate / Raise / Lower / Delete.) (rig)
12. Tap empty canvas. (Selection clears; Add buttons are back.) (rig)
13. Drag the element, drag a corner handle (all handles are fully on screen), add a thin Line and move it. (Works; page does not scroll or refresh.)
14. Pinch with two fingers, pan with one on empty canvas, tap the zoom chip. (Zooms around the fingers, returns to Fit.)
15. Build a label longer than the screen. (Scrolls sideways; elements near the end are reachable; Fit shows the whole label.)
16. Tap the tape chip. ("Label settings" sheet: tape, length, padding, variables.)
17. Tap the name at the top, rename, press Enter. (Inline edit; no zoom on iOS.)
18. Add Icon, QR code, Barcode and Image (More). (Pickers are scrollable inside the sheet; Image offers camera and gallery.)
19. Rotate, Copy, Raise, Lower, Delete, Undo, Redo. (Each works; disabled states are visible.)
20. Tap **Print**. (Sheet with preview, printer, tape check, copies stepper; with a mismatching tape it says so and the button reads "Print anyway".) (rig)
21. Print. (Waiting state with Stop waiting; then "Sent to the printer" and Done; a failure shows Try again and Printers.) (rig: success)
22. Back button / swipe back: with the print sheet open, then with the properties sheet open, then in the editor. (Each press closes one level; in the editor with changes the Save / Discard / Keep editing dialog appears; finally you are on Home, one more Back leaves the panel.) (harness and rig)
23. Edit, reload the page. (The same label is open again with its unsaved changes.) (harness)
24. On Home tap the three dots of a card. (Open / Duplicate / Delete; Delete asks in-app.) (rig)
25. Tap the printer chip. (Full-screen printer sheet; Back closes it.) (rig)
26. Tap **From template**. (Full-screen gallery, category chips fade at the edge where more exist; picking one opens the editor with the variables sheet at half height.) (rig)
27. Rotate to landscape. (Compact bars, sheet is a side panel with a visible Done even with the keyboard open, nothing clipped by the notch.) (rig)
28. Switch HA to a dark theme and back. (Colours follow HA variables.) (rig)
29. iPhone with a notch / home indicator and an Android gesture bar. (No double inset: one gap at most, from HA itself; toolbar not under the home indicator.)
30. Tablet 768-1024 px. (Portrait uses the phone screens, 900 px and wider uses the desktop three-pane editor.)
31. Swipe down from the top on the canvas (Android). (No pull-to-refresh; UNVERIFIED in the Companion app.)

## Template gallery ("From template")

Entry points: the **From template** button under Designs (desktop), the big **From template** button on the phone Home screen, "Start from a template" in the editor menu, and the
"Start from a template" button on an empty desktop canvas. It opens a centred dialog (desktop) or a full-screen sheet (phone) with search,
category chips and a card grid. Thumbnails are built + rendered by the server at the current tape, lazily as cards scroll into view
(max 3 requests at once, cached in memory per tape). Templates that do not support the current tape are greyed out and say which tape they need.
Choosing one opens a new unsaved design (dirty, named after the template); on phones the editor opens with the Label settings sheet (variables) at half height.
If the current design has unsaved changes the in-app "Discard" dialog appears first (Cancel returns to the gallery).
Phone checks: all targets 44 px, no horizontal scroll, bottom of the grid clears the gesture bar, close button clears the notch, Esc/Enter work with a hardware keyboard.

## Real Home Assistant rig and README screenshots

`tools/ha-rig/` (see its README) runs a real HA with this integration and a fake bridge printer on 127.0.0.1; it never loads HA's Bluetooth.

    UI_VENV=<venv with playwright>
    # one-shot: start HA, drive the phone flows at 390x844 / 412x915 / 360x640, portrait+landscape, light+dark, stop HA
    HA_RIG_DIR=/tmp/rigcfg $UI_VENV/bin/python tools/ha-rig/run.py --shots /tmp/shots
    # iterate: keep HA running (frontend edits load on reload)
    HA_RIG_DIR=/tmp/rigcfg .venv-ha/bin/python tools/ha-rig/serve.py &   # then:  run.py --shots out --attach ;  kill $(cat /tmp/rigcfg/serve.pid)

README phone screenshots (dev harness, mock backend): start `dev/mock_backend.py --port 8765`, then
`$UI_VENV/bin/python custom_components/brother_ptouch/frontend/dev/phone_shots.py docs/images` (writes phone-home / phone-editor / phone-sheet / phone-print .png).
Harness switches for the home states: `?printers=0` (set up your printer card), `_mock/printer` with `online:false` (offline card).

## Known limitations / not verified without a device

* WebKit (iOS Safari, WKWebView) and the Android WebView were **not** run. Verified engine: Chromium (Pixel 7 and iPhone-UA
  emulation, touch via CDP). iOS-specific behaviour (keyboard overlay, rubber banding, long-press callouts, `visualViewport`
  offsets, file chooser) is implemented defensively but untested.
* Compatibility was reviewed against iOS 15 / WebView 100 by code reading: `color-mix()` is only used inside `@supports`
  with plain fallbacks, `:has()`, container queries, `Array.at` and `replaceAll` are not used, `dvh` is not used. `:focus-visible`
  rules are dropped silently on iOS older than 15.4.
* Safe areas: HA pads the panel host itself, the panel adds nothing (verified in the real-HA rig with emulated insets; the Companion apps were not run).
* Pull-to-refresh and edge swipes handled natively by the Companion app cannot be suppressed from web content with certainty.
* Real-device performance (preview debounce values, pinch smoothness) is untested.
* Free rotation, multi-select and on-canvas text editing are not implemented.

## Printer setup (chip, drawer, Add-printer wizard)

Dev harness: start `.venv/bin/python custom_components/brother_ptouch/frontend/dev/mock_backend.py --offline` (binds 127.0.0.1:8765) and open
`http://127.0.0.1:8765/dev/index.html`. It uses a stateful fake of the printer/Bluetooth commands (nothing touches a radio) and resets on every load.
Switches via the query string: `printers=0|1|2` (0 = first run), `pair=ok|fail|timeout`, `connect=ok|asleep|asleep_once|busy`, `bt=ok|no_dbus|bluetooth_off|no_adapter`,
`add=ok|fail`, `wake=<s a sleeping printer makes print/connect wait>`, `pair_secs`. Example first run on a phone: `?printers=0&pair=fail&connect=asleep_once`.
Against real Home Assistant, only the checks that do not depend on a real printer state (layout, focus, touch) apply; stop the mock server when done.

1. Open with `?printers=0`. (Chip reads "Printer - No printer" with a grey dot; Print is replaced by a blue "Set up your printer" button; the editor still works, tape 12 mm.)
2. Tap the button. (Wizard opens: centred dialog on desktop, full-screen sheet on a phone; three cards How is it connected?; Next is disabled until one is chosen.)
3. Choose Bluetooth, Next, tap Scan. (Progress bar and "Scanning..."; list shows printers first with signal bars and Paired/Not paired; phones and headsets are under "Other devices".)
4. With `pair=fail`, tap Pair on the unpaired PT-P710BT. (About 2 s "Pairing..."; then the failure sentence and a Retry button; Next stays disabled.)
5. Switch the mock to `pair=ok` (reload with the query or use the `_mock/set` command), Retry. (Row becomes Paired and selected; Next enables.)
6. Next. (Test step: "Connecting to the printer..." then "Connected: 12 mm laminated, white tape, black text"; "Print a test label" works; Next.)
7. Name step. (Default name from the device; duplicates are refused with a message; Done selects the printer and the chip shows the name, status dot and "12 mm".)
8. Tap the chip. (Right-hand drawer on desktop, full-screen sheet on phone: name, connection, state sentence, tape line, Connect (Bluetooth only), Test print, rename (pencil) and remove (bin); "Add printer" at the bottom; Esc or the close button returns focus to the chip.)
9. With `connect=asleep_once`, tap Connect. ("Trying to reach the printer..."; after the wake time the asleep sentence and Retry; Retry succeeds and the chip dot turns green.)
10. Rename: pencil, type, Enter. (Name updates in the drawer and the chip.) Remove: bin, confirm in the in-app dialog. (Printer disappears; with two printers "Use this printer" switches the active one and the tape follows it.)
11. Make the printer asleep in the mock (`_mock/printer` with `online:false, reason:"asleep"`) and tap Print. (A strip under the top bar shows "Waiting for the printer... (up to 20 s)" with Cancel; afterwards the failure sentence with Retry, Dismiss and Printers. Cancel returns to idle at once and a later Print works.)
12. `bt=no_dbus`, wizard > Bluetooth. (The "can't use Bluetooth here" sentence and buttons Use USB / Use network bridge; bridge URL must start with http:// or https://.)
13. Check on a phone: all buttons at least 44 px, nothing hidden under the notch or gesture bar, no horizontal scroll, dark theme legible, landscape still usable.

Not verified: real Bluetooth behaviour (forbidden for this piece), real WebKit, the wake wait with a real sleeping printer (the mock uses a few seconds instead of up to 20 s).
