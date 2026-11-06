# Testing the label editor on a real phone

The editor (`custom_components/brother_ptouch/frontend/`) was developed with emulated touch devices
(Chromium via Playwright, Pixel 7 descriptor, CDP `Input.dispatchTouchEvent`). WebKit/iOS could **not** be run
on the dev machine (missing system libraries), and nothing has been tried inside the real Companion app yet.
This file tells you how to do that, and what to look for.

## What changed for touch (short)

* One finger on an element drags it, handles resize it (hit boxes are 44 css px; on tiny elements they sit
  outside the box so the body stays draggable). One finger on the empty canvas pans, two fingers pinch-zoom and pan.
  Double tap or long press (about 0.5 s) on an element opens its properties and focuses the text field.
* Phone layout (panel narrower than 900 px): compact top bar (menu, name, Save, Print, three-dot menu with tape,
  length, printer, copies, New design), zoom and undo/redo strip, action bar with **Add**, Edit, Rotate,
  Duplicate, Forward, Backward, Delete, properties as a bottom sheet (side panel in landscape), bottom tab bar.
* Rotation is in 90 degree steps only (the design format has no free rotation), via the Rotate button.
* All confirmations are in-app dialogs (no `window.confirm`). Inputs are 16 px (no iOS focus zoom).
* Keyboard: when a text field is focused on a phone the tab bar, action bar and zoom strip hide so the sheet and the
  field stay visible (`visualViewport` based).

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

## (c) Manual checklist

Use a 360-430 px wide phone in portrait first. Expected results in parentheses.

1. Open Labels from the sidebar. (Panel fills the screen, no page horizontal scroll, top bar on one row.)
2. Tap the menu icon at top left. (HA sidebar opens. In wide/tablet layout the icon is absent: HA shows its own.)
3. Tap **Add** > **Text**. (Bottom sheet with a 4-column grid, tiles at least 44 px; element appears and is selected; canvas scrolls to it.)
4. Drag the element with one finger. (It follows the finger, snapping guides show, page does not scroll, no pull-to-refresh, no text selection or magnifier.)
5. Drag it towards the right screen edge on a long label. (Canvas auto-scrolls.)
6. Drag a corner handle. (Element resizes; handle is easy to hit; the preview image updates a moment after release.)
7. Add a 2 px **Line**, then try to move it and to resize it. (Hit area is bigger than the line; handles sit outside it.)
8. Tap the rotate button on the action bar. (Rotates by 90 degrees each tap.)
9. Tap Duplicate, then Delete, then Undo and Redo in the strip at the top. (Each works without a keyboard.)
10. Pinch outwards with two fingers on the canvas. (Zooms continuously around the fingers, page itself does not zoom.)
11. Pan with two fingers while pinching, then with one finger on empty canvas. (Scrolls, with momentum.)
12. Tap the zoom percentage chip. (Returns to the default zoom, 200% or more on a phone.)
13. Build a label longer than the screen. (Horizontal scrolling works; elements near the end are reachable.)
14. Double tap a text element. (Properties sheet opens, text field focused, soft keyboard appears.)
15. Long press a text element for about half a second. (Same as double tap; no OS context menu or text selection.)
16. While the keyboard is open, type text. (Field stays visible above the keyboard; tab bar and action bar are hidden; label preview still partly visible; after closing the keyboard the layout returns.)
17. Focus any input. (No page zoom on iOS, since fonts are 16 px.)
18. Tap Properties in the tab bar, change font via the picker, search a font. (List scrolls inside the sheet; sheet does not hide the selected element: canvas scrolls it into view; the arrow button makes the sheet taller/shorter.)
19. Select an icon element and pick an icon. (Grid cells are at least 44 px; icons render.)
20. Add **Image**. (OS offers camera and photo/file picker; chosen image is scaled to the tape height and previewed.)
21. Open the three-dot menu. (Tape, length, printer (if more than one), copies, New design, Reset zoom; all selects open the native picker.)
22. Tap New design with unsaved changes. (In-app "Discard unsaved changes?" dialog, red Discard button; no browser alert.)
23. Print with a mismatching tape. (In-app confirmation; then a "Sent to printer" message.)
24. Switch Labels tab, open a saved design, delete one. (Delete asks in-app; list buttons are 44 px.)
25. Rotate the phone to landscape. (Tab bar becomes a left rail, properties open as a right-hand panel, nothing cut off by the notch.)
26. Switch HA to a dark theme and back. (Colours follow HA variables; handles and text stay legible.)
27. Check the bottom of the screen on a phone with a gesture bar. (Tab bar is not under the system bar; UNVERIFIED whether HA already pads the safe area, so look for a double gap or a clipped bar.)
28. On a tablet (768-1024 px) in portrait and landscape. (Portrait uses the phone layout; landscape at 900 px and wider uses the three-pane desktop layout.)
29. Leave the panel open for a few minutes while editing. (No lag when dragging; preview requests are debounced to 250 ms/800 ms max on touch devices.)
30. Swipe down from the top on the empty canvas (Android). (Canvas does not trigger the app's pull-to-refresh. UNVERIFIED: native SwipeRefreshLayout may still fire; if so report it.)

## Template gallery ("From template")

Entry points: the **From template** button under Designs (desktop and the phone Labels tab), the three-dot menu on phones, and the
"Start from a template" button on an empty canvas. It opens a centred dialog (desktop) or a full-screen sheet (phone) with search,
category chips and a card grid. Thumbnails are built + rendered by the server at the current tape, lazily as cards scroll into view
(max 3 requests at once, cached in memory per tape). Templates that do not support the current tape are greyed out and say which tape they need.
Choosing one opens a new unsaved design (dirty, named after the template); on phones the properties sheet opens scrolled to the Variables.
If the current design has unsaved changes the in-app "Discard" dialog appears first (Cancel returns to the gallery).
Phone checks: all targets 44 px, no horizontal scroll, bottom of the grid clears the gesture bar, close button clears the notch, Esc/Enter work with a hardware keyboard.

## Known limitations / not verified without a device

* WebKit (iOS Safari, WKWebView) and the Android WebView were **not** run. Verified engine: Chromium (Pixel 7 and iPhone-UA
  emulation, touch via CDP). iOS-specific behaviour (keyboard overlay, rubber banding, long-press callouts, `visualViewport`
  offsets, file chooser) is implemented defensively but untested.
* Compatibility was reviewed against iOS 15 / WebView 100 by code reading: `color-mix()` is only used inside `@supports`
  with plain fallbacks, `:has()`, container queries, `Array.at` and `replaceAll` are not used, `dvh` is not used. `:focus-visible`
  rules are dropped silently on iOS older than 15.4.
* Whether HA already applies `env(safe-area-inset-*)` to custom panels is unknown; the panel adds its own padding.
* Pull-to-refresh and edge swipes handled natively by the Companion app cannot be suppressed from web content with certainty.
* Real-device performance (preview debounce values, pinch smoothness) is untested.
* Free rotation, multi-select and on-canvas text editing are not implemented.
