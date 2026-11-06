"""Real-Home-Assistant test rig for the brother_ptouch label editor.

Starts, all on 127.0.0.1 only:
  * a fake network-bridge printer (the real bridge HTTP handler + a FakeTransport),
  * a headless Home Assistant (.venv-ha) with an explicit, minimal component list
    (NO bluetooth / default_config) and this repo's integration symlinked in,
and logs a Playwright Chromium into it by injecting tokens into localStorage.

See README.md. Python API:  Rig(...).start(); rig.new_context(p, device="iphone13"); open_panel(page)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INTEGRATION = REPO / "custom_components" / "brother_ptouch"
HASS_BIN = REPO / ".venv-ha" / "bin" / "hass"
HOST = "127.0.0.1"
USERNAME, PASSWORD, NAME = "rig", "rig-password-1", "Rig"

CONFIGURATION_YAML = """\
# Explicit minimal component list. DO NOT add default_config / bluetooth / usb / dhcp / ssdp / zeroconf.
homeassistant:
  name: Rig
  latitude: 52.0
  longitude: 5.0
  elevation: 0
  unit_system: metric
  time_zone: UTC
http:
  server_host: 127.0.0.1
  server_port: {port}
frontend:
api:
websocket_api:
config:
onboarding:
logger:
  default: info
"""

# ---------------------------------------------------------------- devices
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")
PIXEL_UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Mobile Safari/537.36")
# name -> (css width, css height, dpr, user agent) in PORTRAIT
DEVICES = {
    "iphone13": (390, 844, 3, IPHONE_UA),
    "pixel7": (412, 915, 2.625, PIXEL_UA),
    "small360": (360, 640, 3, PIXEL_UA),
    "desktop": (1280, 800, 1, None),
}


def free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex((HOST, port)) != 0


# ---------------------------------------------------------------- fake printer
def status_bytes(width=12, media=0x01, err1=0, err2=0, stype=0x00, phase=0x00, colour=0x01, text=0x08) -> bytes:
    b = bytearray(32)
    b[0], b[1], b[2], b[3] = 0x80, 0x20, 0x42, 0x30
    b[8], b[9], b[10], b[11], b[18], b[19], b[24], b[25] = err1, err2, width, media, stype, phase, colour, text
    return bytes(b)


class FakePrinter:
    """HTTP bridge (real handler) backed by a fake transport; records received jobs."""

    def __init__(self, port: int, token: str | None = None):
        sys.path.insert(0, str(REPO / "bridge"))
        sys.path.insert(0, str(INTEGRATION))
        from ptouch.protocol import PrinterStatus  # noqa: PLC0415
        from ptouch.transport import Transport  # noqa: PLC0415
        import ptouch_bridge  # noqa: PLC0415

        outer = self
        self.jobs: list[tuple[bytes, int]] = []
        self.raw = status_bytes()          # 12 mm laminated, idle; change with set_status()

        class FakeTransport(Transport):
            def get_status(self):
                return PrinterStatus.parse(outer.raw)

            def print_job(self, data, pages=1):
                outer.jobs.append((bytes(data), pages))

        self.token = token
        self.server = ThreadingHTTPServer((HOST, port), ptouch_bridge.make_handler(FakeTransport(), token))
        self.port = port
        self.url = f"http://{HOST}:{port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def set_status(self, **kw) -> None:
        self.raw = status_bytes(**kw)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


# ---------------------------------------------------------------- HA rig
def _http(method, url, data=None, headers=None, form=False, timeout=30):
    body = None
    h = dict(headers or {})
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            h["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:  # noqa: BLE001
            return e.code, raw


class Rig:
    def __init__(self, config_dir: str | os.PathLike | None = None, port: int = 18123, printer_port: int = 18765,
                 reset: bool = False, verbose: bool = True):
        base = os.environ.get("HA_RIG_DIR") or os.path.join(tempfile.gettempdir(), "ha-brother-ptouch-rig")
        self.dir = Path(config_dir or base).resolve()
        if str(self.dir).startswith(str(REPO)) or self.dir == Path.home() / ".homeassistant":
            raise SystemExit("refusing to use the repo or ~/.homeassistant as the rig config dir")
        self.port, self.printer_port = port, printer_port
        self.base = f"http://{HOST}:{port}"
        self.reset, self.verbose = reset, verbose
        self.proc: subprocess.Popen | None = None
        self.printer: FakePrinter | None = None
        self.state_file = self.dir / "rig-state.json"
        self.state: dict = {}

    def log(self, *a):
        if self.verbose:
            print("[rig]", *a, flush=True)

    # ---- lifecycle
    def start(self) -> "Rig":
        if self.reset and self.dir.exists():
            for child in self.dir.iterdir():          # keep pylibs (slow to download)
                if child.name != "pylibs":
                    shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
        for p in (self.port, self.printer_port):
            if not free(p):
                raise SystemExit(f"port {p} is busy; pass --port/--printer-port")
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "configuration.yaml").write_text(CONFIGURATION_YAML.format(port=self.port))
        cc = self.dir / "custom_components"
        cc.mkdir(exist_ok=True)
        link = cc / "brother_ptouch"
        if link.is_symlink() or link.exists():
            link.unlink() if link.is_symlink() else shutil.rmtree(link)
        link.symlink_to(INTEGRATION)
        if self.state_file.exists():
            self.state = json.loads(self.state_file.read_text())
            if self.state.get("port") != self.port or self.state.get("printer_port") != self.printer_port:
                raise SystemExit("config dir was created with other ports; use --reset or the same ports")
        self._seed_http_storage()
        self.printer = FakePrinter(self.printer_port).start()
        self.log("fake printer on", self.printer.url)
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONPATH=self._ensure_pylibs())
        logf = open(self.dir / "hass.out", "w")
        self.proc = subprocess.Popen([str(HASS_BIN), "-c", str(self.dir), "--skip-pip"], stdout=logf, stderr=logf,
                                     env=env, start_new_session=True)
        self.log("hass pid", self.proc.pid, "port", self.port, "config", self.dir)
        try:
            self._wait_up()
            self._ensure_user_and_entry()
            self.verify_no_bluetooth()
        except BaseException:
            self.stop()
            raise
        return self

    def _seed_http_storage(self) -> None:
        """HA >= 2026.10 migrates the YAML http: block into .storage/http as an unconfirmed *pending* trial, shows
        a 'Confirm new HTTP server configuration' dialog in the UI and after 5 min reverts to the stable default
        (port 8123, ALL interfaces). Pre-seed a confirmed stable config bound to 127.0.0.1 so neither happens."""
        f = self.dir / ".storage" / "http"
        if f.exists():
            return
        f.parent.mkdir(exist_ok=True)
        stable = {"server_port": self.port, "server_host": [HOST], "cors_allowed_origins": [],
                  "login_attempts_threshold": -1, "ip_ban_enabled": False, "ssl_profile": "modern",
                  "use_x_frame_options": True, "created_at": "2026-01-01T00:00:00+00:00", "error": None,
                  "error_message": None}
        f.write_text(json.dumps({"version": 2, "minor_version": 2, "key": "http", "data": {
            "stable": stable, "pending": None, "yaml_migration_done": True}}))

    # HA's `onboarding` pulls in assist/conversation, whose service descriptions need these libs; without them
    # the frontend's get_services call fails and the UI never leaves the splash screen. They go in <dir>/pylibs
    # (never into .venv-ha) and are put on PYTHONPATH for the hass process only.
    EXTRA_LIBS = ("hassil==3.12.1", "unicode-rbnf", "home-assistant-intents", "gazetteer-matcher",
                  "PyTurboJPEG", "ha-ffmpeg", "mutagen", "pymicro-vad", "pyspeex-noise")

    def _ensure_pylibs(self) -> str:
        d = self.dir / "pylibs"
        if not d.exists():
            self.log("installing helper libs into", d)
            subprocess.run([str(HASS_BIN.with_name("python")), "-m", "pip", "install", "-q", "--no-deps", "--target", str(d),
                            *self.EXTRA_LIBS], check=True)
        return str(d)

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
                self.proc.wait(timeout=30)
            except Exception:  # noqa: BLE001
                os.killpg(self.proc.pid, signal.SIGKILL)
        if self.printer:
            self.printer.stop()

    __enter__ = start

    def __exit__(self, *a):
        self.stop()

    def _wait_up(self, timeout=180):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc.poll() is not None:
                raise SystemExit("hass exited early; see " + str(self.dir / "hass.out"))
            try:
                code, _ = _http("GET", self.base + "/api/onboarding", timeout=3)
                if code in (200, 404):          # 404 = onboarding finished (endpoint removed)
                    self.log(f"HA up after {time.time() - t0:.0f}s")
                    time.sleep(3)
                    return
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1)
        raise SystemExit("HA did not come up in time")

    # ---- onboarding / login / integration
    @property
    def client_id(self) -> str:
        return self.base + "/"

    def _token(self, **form):
        code, js = _http("POST", self.base + "/auth/token", {"client_id": self.client_id, **form}, form=True)
        if code != 200:
            raise SystemExit(f"/auth/token failed {code}: {js}")
        return js

    def _ensure_user_and_entry(self) -> None:
        code, steps = _http("GET", self.base + "/api/onboarding")
        pending = [s["step"] for s in steps if not s["done"]] if code == 200 else []
        if "user" in pending:
            code, js = _http("POST", self.base + "/api/onboarding/users", {
                "client_id": self.client_id, "name": NAME, "username": USERNAME, "password": PASSWORD,
                "language": "en"})
            assert code == 200, (code, js)
            tok = self._token(grant_type="authorization_code", code=js["auth_code"])
            self.state = {"port": self.port, "printer_port": self.printer_port, "refresh_token": tok["refresh_token"]}
            self.state_file.write_text(json.dumps(self.state))
            auth = {"Authorization": "Bearer " + tok["access_token"]}
            for step, body in (("core_config", {}), ("analytics", {}),
                               ("integration", {"client_id": self.client_id, "redirect_uri": self.client_id})):
                c, r = _http("POST", f"{self.base}/api/onboarding/{step}", body, auth)
                self.log("onboarding", step, c)
        elif not self.state.get("refresh_token"):
            raise SystemExit("user exists but rig-state.json lost; run with --reset")
        auth = self.auth_header()
        c, entries = _http("GET", self.base + "/api/config/config_entries/entry", headers=auth)
        if not any(e["domain"] == "brother_ptouch" for e in entries):
            c, flow = _http("POST", self.base + "/api/config/config_entries/flow",
                            {"handler": "brother_ptouch", "show_advanced_options": False}, auth)
            if c != 200 or not isinstance(flow, dict):
                raise SystemExit(f"starting the config flow failed: {c} {flow!r:.300}")
            fid = flow["flow_id"]
            c, flow = _http("POST", f"{self.base}/api/config/config_entries/flow/{fid}", {"next_step_id": "bridge"}, auth)
            c, flow = _http("POST", f"{self.base}/api/config/config_entries/flow/{fid}",
                            {"url": self.printer.url, "token": ""}, auth)
            if flow.get("type") != "create_entry":
                raise SystemExit(f"config flow did not create an entry: {flow}")
            self.log("integration entry created:", flow.get("title"))
            time.sleep(3)

    def auth_header(self) -> dict:
        tok = self._token(grant_type="refresh_token", refresh_token=self.state["refresh_token"])
        return {"Authorization": "Bearer " + tok["access_token"]}

    def verify_no_bluetooth(self) -> None:
        out = (self.dir / "hass.out").read_text(errors="replace")
        log = self.dir / "home-assistant.log"
        out += log.read_text(errors="replace") if log.exists() else ""
        bad = [l for l in out.splitlines() if re.search(r"Setting up (bluetooth|default_config|usb|dhcp)\b", l)]
        if bad:
            self.stop()
            raise SystemExit("SAFETY: a forbidden component was set up:\n" + "\n".join(bad))
        ours = [l for l in out.splitlines() if "brother_ptouch" in l and ("Setting up" in l or "panel" in l.lower())]
        self.log("no bluetooth/usb/dhcp/default_config set up; integration log lines:", len(ours))

    # ---- browser
    def hass_tokens_js(self) -> str:
        tok = {"access_token": "x", "token_type": "Bearer", "expires_in": 1800, "hassUrl": self.base,
               "clientId": self.client_id, "expires": 1, "refresh_token": self.state["refresh_token"]}
        return json.dumps(tok)

    def new_context(self, p, device="iphone13", landscape=False, dark=False, companion=False, browser=None, **extra):
        """Chromium context emulating a phone. companion=True fakes the Companion app WebView (UA + externalApp bridge)."""
        w, h, dpr, ua = DEVICES[device]
        if landscape:
            w, h = h, w
        mobile = device != "desktop"
        kw = dict(viewport={"width": w, "height": h}, device_scale_factor=dpr, is_mobile=mobile, has_touch=mobile,
                  color_scheme="dark" if dark else "light", locale="en-US")
        if ua:
            kw["user_agent"] = ua
        if companion:
            kw["user_agent"] = (PIXEL_UA.replace("; wv", "") + " Home Assistant/2026.10.0-rig (Android 14)")
        kw.update(extra)
        browser = browser or p.chromium.launch(args=["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"]
                                               if os.environ.get("HA_RIG_OFFLINE") else [])
        ctx = browser.new_context(**kw)
        theme = json.dumps(json.dumps({"dark": bool(dark)}))
        ctx.add_init_script(f"""
          try {{
            if (!localStorage.getItem('hassTokens')) localStorage.setItem('hassTokens', JSON.stringify({self.hass_tokens_js()}));
            localStorage.setItem('selectedTheme', {theme});
            localStorage.setItem('dockedSidebar', '"auto"');
          }} catch (e) {{}}
        """)
        return ctx


DEEP_JS = """
function deepFind(root, sel) {
  const hit = root.querySelector && root.querySelector(sel); if (hit) return hit;
  const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
  for (const el of all) { if (el.shadowRoot) { const r = deepFind(el.shadowRoot, sel); if (r) return r; } }
  return null;
}
"""


def open_panel(page, rig: Rig, path="/brother-ptouch", wait_ms=1500, timeout=60000):
    """Navigate to the editor panel and wait until the custom element has rendered."""
    page.goto(rig.base + path, wait_until="load", timeout=timeout)
    page.wait_for_function("() => { " + DEEP_JS + " return !!deepFind(document, 'brother-ptouch-panel'); }", timeout=timeout)
    page.wait_for_timeout(wait_ms)
    return page
