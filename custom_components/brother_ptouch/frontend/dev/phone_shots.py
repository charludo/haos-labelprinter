#!/usr/bin/env python3
"""Retake the README phone screenshots of the label editor against the dev mock backend.

    .venv/bin/python custom_components/brother_ptouch/frontend/dev/mock_backend.py --port 8765 &
    <venv with playwright>/bin/python custom_components/brother_ptouch/frontend/dev/phone_shots.py docs/images

Writes phone-home.png, phone-editor.png, phone-sheet.png, phone-print.png (iPhone 13 emulation, 390x844 @3x).
Harness only (not real Home Assistant); for the real thing use tools/ha-rig/run.py.
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
out.mkdir(parents=True, exist_ok=True)
URL = "http://127.0.0.1:8765/dev/index.html?narrow=1"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True, user_agent=UA).new_page()
    pg.goto(URL); pg.wait_for_timeout(1500)
    tap = lambda sel: pg.locator(sel).first.tap()

    def make(name, text):
        tap(".cta .primary"); pg.wait_for_timeout(400); tap(".tbtn:has-text('Text')"); pg.wait_for_timeout(300)
        pg.locator("textarea").first.fill(text); tap(".sdone")
        pg.locator(".name").fill(name); tap(".mchip.save"); pg.wait_for_timeout(700); tap(".mback"); pg.wait_for_timeout(500)

    make("Spice jar", "Paprika"); make("Cable flag", "CAT6 / 12"); make("Wi-Fi guest", "Guest Wi-Fi")
    pg.wait_for_timeout(1500); pg.screenshot(path=str(out / "phone-home.png"))
    tap(".lopen"); pg.wait_for_timeout(900); tap(".el"); pg.wait_for_timeout(400); pg.screenshot(path=str(out / "phone-editor.png"))
    tap(".tbtn:has-text('Edit')"); pg.wait_for_timeout(700); pg.screenshot(path=str(out / "phone-sheet.png"))
    tap(".sdone"); tap(".etop .primary"); pg.wait_for_timeout(700); pg.screenshot(path=str(out / "phone-print.png"))
    b.close()
print("wrote", *sorted(x.name for x in out.glob("phone-*.png")))
