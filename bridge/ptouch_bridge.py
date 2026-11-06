#!/usr/bin/env python3
"""HTTP bridge for a Brother PT-P710BT / P700 / P750W.

Run it on any machine that can reach the printer (USB or Bluetooth) and point
the Home Assistant integration's "Bridge" option at it.

  python3 ptouch_bridge.py --usb                       # USB
  python3 ptouch_bridge.py --bluetooth AA:BB:CC:DD:EE:FF
  python3 ptouch_bridge.py --device /dev/usb/lp0       # or /dev/rfcomm0
  add --token SECRET to require "Authorization: Bearer SECRET"

API:  GET /health   GET /status -> {"status": "<64 hex>"}
      POST /print?pages=N  (body = raw job bytes) -> {"ok": true}
"""
from __future__ import annotations

import argparse
import hmac
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                "custom_components", "brother_ptouch"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ptouch_core"))  # Docker layout

from ptouch import PrinterError, PtouchError, make_transport  # noqa: E402

MAX_JOB = 8 * 1024 * 1024
_LOGGER = logging.getLogger("ptouch_bridge")


def make_handler(transport, token: str | None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ptouch-bridge/1"

        def log_message(self, fmt, *args):
            _LOGGER.info("%s %s", self.address_string(), fmt % args)

        def _send(self, code: int, obj: dict) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            if not token:
                return True
            got = self.headers.get("Authorization", "")
            if hmac.compare_digest(got, f"Bearer {token}"):
                return True
            self._send(401, {"error": "unauthorized"})
            return False

        def _run(self, fn):
            try:
                return fn()
            except PrinterError as err:
                self._send(409, {"error": ",".join(err.errors)})
            except PtouchError as err:
                self._send(502, {"error": str(err)})
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("unhandled error")
                self._send(500, {"error": str(err)})

        def do_GET(self):  # noqa: N802
            path = urlparse(self.path).path
            if path == "/health":
                return self._send(200, {"ok": True})
            if not self._authorized():
                return
            if path == "/status":
                return self._run(lambda: self._send(200, {"status": transport.get_status().raw.hex()}))
            self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            url = urlparse(self.path)
            if url.path != "/print":
                return self._send(404, {"error": "not found"})
            if not self._authorized():
                return
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= MAX_JOB:
                return self._send(400, {"error": "bad Content-Length"})
            data = self.rfile.read(length)
            pages = max(1, min(int(parse_qs(url.query).get("pages", ["1"])[0]), 100))

            def go():
                transport.print_job(data, pages=pages)
                self._send(200, {"ok": True})
            self._run(go)

    return Handler


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--usb", action="store_true")
    g.add_argument("--bluetooth", metavar="MAC")
    g.add_argument("--device", metavar="PATH", help="/dev/usb/lp0 or /dev/rfcomm0")
    ap.add_argument("--channel", type=int, default=1, help="RFCOMM channel (default 1)")
    ap.add_argument("--usb-serial", help="select a printer by USB serial number")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--token", default=os.environ.get("PTOUCH_BRIDGE_TOKEN"))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.usb:
        transport = make_transport("usb", serial=args.usb_serial)
    elif args.bluetooth:
        transport = make_transport("bluetooth", address=args.bluetooth, channel=args.channel)
    else:
        transport = make_transport("bluetooth", address=args.device)
    if not args.token:
        _LOGGER.warning("no --token set: anyone on the network can print")
    srv = ThreadingHTTPServer((args.host, args.port), make_handler(transport, args.token))
    _LOGGER.info("listening on %s:%d", args.host, args.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
