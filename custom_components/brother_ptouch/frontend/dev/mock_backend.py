#!/usr/bin/env python3
"""Dev server for the label editor.

Serves the frontend directory and a tiny HTTP bridge: POST /api/ws with the
same JSON a hass.callWS message carries; answers {"result": ...} or
{"error": {"code", "message"}}. Uses the real ptouch.design / ptouch.assets
when importable, otherwise stub renderers (grey boxes, canned fonts/icons).

    python dev/mock_backend.py [--port 8765] [--offline]
"""
import argparse
import base64
import io
import json
import re
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
FRONTEND = HERE.parent
sys.path.insert(0, str(FRONTEND.parent))  # custom_components/brother_ptouch

from PIL import Image, ImageDraw  # noqa: E402

try:
    from ptouch import design as ptdesign  # type: ignore
except Exception as exc:  # noqa: BLE001
    ptdesign = None
    print(f"[mock] ptouch.design unavailable ({exc}); using stub renderer")
try:
    from ptouch import assets as ptassets  # type: ignore
except Exception as exc:  # noqa: BLE001
    ptassets = None
    print(f"[mock] ptouch.assets unavailable ({exc}); using stub fonts/icons")

PINS = {4: 24, 6: 32, 9: 50, 12: 70, 18: 112, 24: 128}
ASSETS = None
LOCK = threading.Lock()
DESIGNS: dict[str, dict] = {}
PRINTERS = [
    {"entry_id": "p1", "title": "PT-P710BT Office", "tape_mm": 12, "state": "idle"},
    {"entry_id": "p2", "title": "PT-P710BT Workshop", "tape_mm": 4, "state": "idle"},
]
PRINT_LOG: list[dict] = []
STUB_FONTS = [
    {"id": n.lower().replace(" ", "-"), "family": n, "category": c, "weights": [400, 700], "styles": ["normal", "italic"], "subsets": ["latin"]}
    for n, c in [("Roboto", "sans-serif"), ("Roboto Slab", "serif"), ("Lobster", "display"), ("Pacifico", "handwriting"), ("Roboto Mono", "monospace"), ("Open Sans", "sans-serif")]
]
STUB_ICONS = ["mdi:tag", "mdi:home", "mdi:heart", "mdi:star", "mdi:wifi", "mdi:lightbulb", "mdi:key", "mdi:fire", "mdi:flash", "mdi:food", "mdi:cog", "mdi:alert"]


class WsError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def slug(name):
    base = re.sub(r"[^a-z0-9]+", "-", (name or "label").lower()).strip("-") or "label"
    cand, n = base, 1
    while cand in DESIGNS:
        n += 1
        cand = f"{base}-{n}"
    return cand


def stub_render(design, tape_mm):
    pins = PINS.get(tape_mm, 70)
    els = design.get("elements") or []
    pad = design.get("padding_dots", 6)
    if design.get("length_mm"):
        length = max(1, round(design["length_mm"] * 180 / 25.4))
    else:
        length = max(1, max((e["x"] + e["w"] for e in els), default=0) + 2 * pad)
    img = Image.new("1", (length, pins), 1)
    d = ImageDraw.Draw(img)
    for e in els:
        box = [e["x"], e["y"], e["x"] + e["w"] - 1, e["y"] + e["h"] - 1]
        if e.get("type") == "rect" and e.get("fill"):
            d.rectangle(box, fill=0)
        else:
            d.rectangle(box, outline=0)
            d.line([box[0], box[1], box[2], box[3]], fill=0)
        d.text((e["x"] + 3, e["y"] + 2), e.get("type", "?"), fill=0)
    return img, []


def do_preview(m):
    design = m["design"]
    tape = m.get("tape_mm")
    if tape == 3.5:
        tape = 4
    if tape is None:
        p = next((p for p in PRINTERS if p["entry_id"] == m.get("entry_id")), None)
        tape = (p or {}).get("tape_mm") or 12
    warnings = []
    if ptdesign:
        try:
            design = ptdesign.normalize_design(design)
            img = ptdesign.render_design(design, tape, variables=(m.get("variables") or {}), assets=ASSETS)
            if hasattr(ptdesign, "design_warnings"):
                warnings = ptdesign.design_warnings(design, tape, variables=(m.get("variables") or {}), assets=ASSETS)
        except Exception as exc:  # noqa: BLE001
            raise WsError("invalid_design", str(exc))
    else:
        img, warnings = stub_render(design, tape)
    buf = io.BytesIO()
    img.convert("1").save(buf, "PNG")
    return {"png": base64.b64encode(buf.getvalue()).decode(), "width": img.width, "height": img.height, "tape_mm": tape,
            "length_mm": round(img.width * 25.4 / 180, 1), "warnings": warnings}


def handle(m):
    t = m.get("type", "")
    if not t.startswith("brother_ptouch/"):
        raise WsError("unknown_command", t)
    t = t.split("/", 1)[1]
    if t == "printers":
        return {"printers": PRINTERS}
    if t == "designs/list":
        return {"designs": [{"id": k, "name": v.get("name", k), "updated": v.get("updated", "")} for k, v in DESIGNS.items()]}
    if t == "designs/get":
        if m.get("design_id") not in DESIGNS:
            raise WsError("not_found", "design not found")
        return {"design": DESIGNS[m["design_id"]]}
    if t == "designs/save":
        d = dict(m["design"])
        if ptdesign:
            try:
                d = ptdesign.normalize_design(d)
            except Exception as exc:  # noqa: BLE001
                raise WsError("invalid_design", str(exc))
        if d.get("id") not in DESIGNS:
            d["id"] = slug(d.get("name"))
        from datetime import datetime, timezone
        d["updated"] = datetime.now(timezone.utc).isoformat()
        DESIGNS[d["id"]] = d
        return {"design": d}
    if t == "designs/delete":
        DESIGNS.pop(m.get("design_id"), None)
        return {}
    if t == "preview":
        return do_preview(m)
    if t == "print":
        if ("design" in m) == ("design_id" in m):
            raise WsError("home_assistant_error", "exactly one of design / design_id")
        if "design" in m:
            do_preview(m)  # validates
        PRINT_LOG.append({k: v for k, v in m.items() if k != "design"})
        print("[mock] PRINT", PRINT_LOG[-1])
        return {}
    if t == "fonts/search":
        q = (m.get("query") or "").lower()
        if ASSETS:
            try:
                return {"fonts": ASSETS.search_fonts(q, m.get("category"), m.get("limit", 50))}
            except Exception as exc:  # noqa: BLE001
                raise WsError("asset_error", str(exc))
        fonts = [f for f in STUB_FONTS if q in f["family"].lower() and (not m.get("category") or f["category"] == m["category"])]
        return {"fonts": fonts[: m.get("limit", 50)]}
    if t == "fonts/ensure":
        if ASSETS:
            try:
                for w in m.get("weights") or [400]:
                    ASSETS.ensure_font(m["family"], w, bool(m.get("italic")))
            except Exception as exc:  # noqa: BLE001
                raise WsError("asset_error", str(exc))
        return {"ok": True}
    if t == "icons/search":
        q = (m.get("query") or "").lower()
        if ASSETS:
            try:
                return {"icons": ASSETS.search_icons(q, m.get("limit", 100))}
            except Exception as exc:  # noqa: BLE001
                raise WsError("asset_error", str(exc))
        return {"icons": [i for i in STUB_ICONS if q in i][: m.get("limit", 100)]}
    raise WsError("unknown_command", t)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(FRONTEND), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):  # noqa: N802
        if self.path != "/api/ws":
            self.send_error(404)
            return
        try:
            msg = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            with LOCK:
                body = {"result": handle(msg)}
        except WsError as exc:
            body = {"error": {"code": exc.code, "message": exc.message}}
        except Exception as exc:  # noqa: BLE001
            body = {"error": {"code": "unknown_error", "message": f"{type(exc).__name__}: {exc}"}}
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):
        if "/api/ws" not in (args[0] if args else ""):
            super().log_message(fmt, *args)


def main():
    global ASSETS
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address (default 127.0.0.1). Use 0.0.0.0 to test from a phone on the LAN: "
                         "the server is UNAUTHENTICATED and its print command is only a mock")
    ap.add_argument("--offline", action="store_true", help="use the stub font/icon lists even if ptouch.assets exists")
    ap.add_argument("--cache", default=str(Path(tempfile.gettempdir()) / "ptouch-dev-cache"))
    a = ap.parse_args()
    if ptassets and not a.offline:
        try:
            ASSETS = ptassets.AssetManager(Path(a.cache))
            print(f"[mock] real AssetManager, cache {a.cache}")
        except Exception as exc:  # noqa: BLE001
            print(f"[mock] AssetManager failed: {exc}")
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    if a.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"[mock] WARNING: listening on {a.host}: anyone on this network can reach this unauthenticated dev server. "
              "Print is a mock (nothing is sent to a printer). Stop it when you are done.")
    shown = "<this-computer-LAN-ip>" if a.host in ("0.0.0.0", "::") else a.host
    print(f"[mock] http://{shown}:{a.port}/dev/index.html")
    srv.serve_forever()


if __name__ == "__main__":
    main()
