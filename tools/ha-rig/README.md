# ha-rig: the label editor inside a REAL Home Assistant, driven by Playwright Chromium

Everything binds to 127.0.0.1. HA runs from `.venv-ha` with an explicit minimal component list
(`frontend http api websocket_api config onboarding logger` + our integration). It never loads
`bluetooth`, `default_config`, `usb`, `dhcp`; `rig.py` greps the HA log after start and aborts if any were set up.
A fake network-bridge printer (the real `bridge/ptouch_bridge.py` handler + a FakeTransport: 12 mm laminated,
idle, records print jobs) listens on 127.0.0.1:18765. The integration is symlinked from the repo into the
temp config dir; nothing is written to the repo or `~/.homeassistant`.

## Commands
Config dir: `$HA_RIG_DIR` (default `<tmp>/ha-brother-ptouch-rig`). Use the playwright venv for the client side:
`UI_VENV=/tmp/claude-1000/-home-apollo/92063214-b67a-42a7-94ee-7ce31da03687/scratchpad/ui-venv`

    # one command: start rig, take all phone screenshots + measurements.json, stop everything
    HA_RIG_DIR=/path/to/cfg $UI_VENV/bin/python tools/ha-rig/run.py --shots /path/to/out [--only iphone13,pixel7] [--matrix quick]

    # or keep a rig running and attach repeatedly (fast iteration; the frontend is served from the repo with
    # cache_headers=False, so a browser reload picks up edits to custom_components/.../frontend/*)
    .venv-ha/bin/python tools/ha-rig/serve.py [--reset] &        # prints READY; pid in $HA_RIG_DIR/serve.pid
    $UI_VENV/bin/python tools/ha-rig/run.py --shots out --attach
    kill $(cat $HA_RIG_DIR/serve.pid)                            # stops HA + fake printer (SIGTERM is handled)

`--matrix quick` = portrait/light only. Default devices iphone13 (390x844 dpr3, iPhone Safari UA, 47/34 px safe-area
insets), pixel7 (412x915), small360 (360x640); portrait+landscape x light+dark; the full UI flow runs for portrait
light (and every iphone13 variant); the rest only take the first-load shot. Last step is a "Companion-like" pixel7
(app UA string only).

Python helper for your own scripts:

    from rig import Rig, open_panel
    rig = Rig(); rig.start()                       # or Rig(...); rig.state = json.load(rig.state_file) to attach
    ctx = rig.new_context(p, "iphone13", landscape=False, dark=False)   # logged in (hassTokens injected)
    page = ctx.new_page(); open_panel(page, rig)   # lands on /brother-ptouch, waits for <brother-ptouch-panel>
    # safe areas: ctx.new_cdp_session(page).send("Emulation.setSafeAreaInsetsOverride", {"insets": {...}})

`run.py` MEASURE_JS records per screenshot: viewport/visualViewport, the HA host chain rects (home-assistant,
ha-panel-custom, partial-panel-resolver, panel), panel `narrow` prop, `.root` classes, horizontal overflow culprits,
touch targets < 40 px, safe-area CSS vars, theme vars.

## Reset
`serve.py --reset` or `run.py --reset` wipes the config dir (keeps `pylibs/`). Delete the dir for a total reset.

## Gotchas / troubleshooting (all hit while building this)
* `onboarding` is loaded so the UI works; it pulls assist/conversation whose service descriptions need libs missing in
  .venv-ha (hassil, turbojpeg, ...). Without them `get_services` fails and the UI hangs on the splash screen.
  `rig.py` pip-installs them with `--target <dir>/pylibs` (needs network once) and puts that on PYTHONPATH of the hass
  process only; `.venv-ha` is untouched.
* HA 2026.10 migrates the YAML `http:` block to `.storage/http` as an unconfirmed *pending* trial, shows a "Confirm new
  HTTP server configuration" dialog and reverts to port 8123 on ALL interfaces after 5 min. `rig.py` pre-seeds a
  confirmed stable config (127.0.0.1) before first start. Do not delete `.storage/http` while keeping the dir.
* `/api/onboarding` returns 404 once onboarding is finished (used as "HA is up" signal too).
* `panel_custom:` must not appear in configuration.yaml (empty config is invalid); it loads as a dependency.
* Never `pkill -f hass`; use serve.pid. Check `pgrep -af "[b]in/hass"` when finished.
* HA first start ~10-40 s; later starts a few seconds.
* The Bluetooth wizard step calls `bluetooth/status` (reads adapter list, harmless without the component); never
  scan/pair against real hardware from the rig.
* Not emulated: real Companion app WebView (externalApp bus, its own status-bar/inset handling, WKWebView quirks),
  real soft keyboard (we shrink the viewport to simulate it), real iOS Safari/WebKit (Chromium engine only).
