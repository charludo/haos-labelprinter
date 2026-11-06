#!/usr/bin/env python3
"""One-command phone diagnosis of the label editor inside a REAL Home Assistant.

    python tools/ha-rig/run.py --shots DIR [--only iphone13,pixel7] [--keep-running] [--reset]

Starts the rig (fake printer + HA on 127.0.0.1), drives the editor with Chromium phone emulation, writes
screenshots + measurements.json to DIR, then stops everything.  Run it with the playwright venv, e.g.
    $UI_VENV/bin/python tools/ha-rig/run.py --shots /tmp/shots
(the script re-execs HA from .venv-ha by itself; it only needs `playwright` importable).
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rig import DEEP_JS, DEVICES, Rig, open_panel  # noqa: E402

# JS measuring the host chain + the panel + overflow culprits. Pierces shadow roots.
MEASURE_JS = r"""
() => {
  const deepFind = (root, sel) => { const hit = root.querySelector && root.querySelector(sel); if (hit) return hit; for (const el of (root.querySelectorAll ? root.querySelectorAll("*") : [])) { if (el.shadowRoot) { const r = deepFind(el.shadowRoot, sel); if (r) return r; } } return null; };
  const out = {};
  const q = (root, sel) => root && root.querySelector(sel);
  const ha = document.querySelector('home-assistant');
  const main = q(ha && ha.shadowRoot, 'home-assistant-main');
  const rs = q(main && main.shadowRoot, 'ha-panel-custom');
  const panel = deepFind(document, 'brother-ptouch-panel');
  const r = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)]; };
  out.viewport = { innerW: innerWidth, innerH: innerHeight, vvW: visualViewport.width, vvH: visualViewport.height,
                   vvOffTop: visualViewport.offsetTop, dpr: devicePixelRatio, docScrollW: document.documentElement.scrollWidth,
                   docScrollH: document.documentElement.scrollHeight, scrollY: scrollY };
  out.chain = { 'home-assistant': r(ha), main: r(main), 'ha-panel-custom': r(rs), panel: r(panel) };
  if (main) {
    const hm = main.shadowRoot;
    out.chain.partial_panel_resolver = r(q(hm, 'partial-panel-resolver'));
    out.chain.ha_drawer = r(q(hm, 'ha-drawer'));
    out.chain.ha_sidebar = r(q(hm, 'ha-sidebar'));
  }
  if (panel) {
    out.panel = { narrowProp: panel.narrow, hasHass: !!panel.hass, display: getComputedStyle(panel).display,
                  height: getComputedStyle(panel).height, cw: panel.clientWidth, sw: panel.scrollWidth };
    const sr = panel.shadowRoot;
    const root = q(sr, '.root');
    out.root = root ? { cls: root.className, rect: r(root), dataView: root.dataset.view } : null;
    // visible bars
    const vis = (el) => { const b = el.getBoundingClientRect(); const cs = getComputedStyle(el);
      return b.width > 0 && b.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
    // horizontal overflow culprits inside the panel
    const bad = []; const w = innerWidth;
    sr.querySelectorAll('*').forEach((el) => {
      if (!vis(el)) return; const b = el.getBoundingClientRect();
      if (b.right > w + 1 || b.left < -1) bad.push({ el: (el.tagName.toLowerCase() + '.' + (el.className && el.className.baseVal === undefined ? el.className : '')).slice(0, 60), l: Math.round(b.left), r: Math.round(b.right) });
    });
    out.overflowX = bad.slice(0, 12);
    // small touch targets
    const small = [];
    sr.querySelectorAll('button, input, select, [role=button], a').forEach((el) => {
      if (!vis(el) || el.classList.contains('sr')) return; const b = el.getBoundingClientRect();
      if (b.height < 40 || b.width < 40) small.push({ el: (el.tagName.toLowerCase() + '.' + el.className + ' ' + (el.getAttribute('aria-label') || el.textContent || '').trim()).slice(0, 60), w: Math.round(b.width), h: Math.round(b.height) });
    });
    out.smallTargets = small.slice(0, 16);
    // clipped bottom: any visible button whose bottom is below the visual viewport
    const clipped = [];
    sr.querySelectorAll('button, input, select').forEach((el) => {
      if (!vis(el) || el.classList.contains('sr')) return; const b = el.getBoundingClientRect();
      if (b.bottom > visualViewport.height + 1 || b.top < -1) clipped.push({ el: (el.tagName.toLowerCase() + '.' + el.className + ' ' + (el.getAttribute('aria-label') || el.textContent || '').trim()).slice(0, 50), top: Math.round(b.top), bottom: Math.round(b.bottom) });
    });
    out.clipped = clipped.slice(0, 12);
    out.fontMin = Math.min(...[...sr.querySelectorAll('button, input, select, span, label')].filter(vis).map((e) => parseFloat(getComputedStyle(e).fontSize) || 99));
    out.safeAreaVars = (() => { const cs = getComputedStyle(root || panel); return ['--bp-sai-t', '--bp-sai-b', '--bp-sai-l', '--bp-sai-r'].map((k) => k + '=' + cs.getPropertyValue(k).trim()); })();
    const cs = getComputedStyle(root || panel);
    out.theme = ['--bp-card', '--bp-line', '--bp-accent', '--primary-background-color', '--card-background-color'].map((k) => k + '=' + cs.getPropertyValue(k).trim());
  }
  return out;
}
"""


class Shooter:
    def __init__(self, page, out: Path, tag: str, log: list):
        self.page, self.out, self.tag, self.log = page, out, tag, log
        self.n = 0

    def shot(self, name: str, measure=True):
        self.n += 1
        fn = f"{self.tag}-{self.n:02d}-{name}.png"
        self.page.wait_for_timeout(500)
        self.page.screenshot(path=str(self.out / fn), timeout=60000)
        entry = {"shot": fn}
        if measure:
            try:
                entry["m"] = self.page.evaluate(MEASURE_JS)
            except Exception as e:  # noqa: BLE001
                entry["m_error"] = str(e)[:200]
        self.log.append(entry)
        return fn

    def step(self, name, fn):
        try:
            fn()
            return True
        except Exception as e:  # noqa: BLE001
            self.log.append({"step_failed": name, "error": str(e).splitlines()[0][:200]})
            print(f"   ! step {name!r} failed: {str(e).splitlines()[0][:120]}")
            return False


def set_safe_area(page, ctx, top=0, bottom=0, left=0, right=0):
    """Chromium CDP Emulation.setSafeAreaInsetsOverride (env(safe-area-inset-*)). Returns True if accepted."""
    try:
        cdp = ctx.new_cdp_session(page)
        cdp.send("Emulation.setSafeAreaInsetsOverride", {"insets": {"top": top, "bottom": bottom, "left": left, "right": right}})
        return True
    except Exception as e:  # noqa: BLE001
        print("   safe-area override unavailable:", str(e)[:100])
        return False


def scenario(p, rig: Rig, out: Path, device: str, landscape: bool, dark: bool, results: dict, safe=True, companion=False, full=True):
    tag = f"{device}{'-land' if landscape else ''}{'-dark' if dark else ''}{'-app' if companion else ''}"
    log: list = []
    results[tag] = log
    print("==", tag)
    browser = p.chromium.launch()
    ctx = rig.new_context(p, device, landscape=landscape, dark=dark, companion=companion, browser=browser)
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text[:200]) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append("PAGEERROR " + str(e)[:200]))
    if safe and device != "desktop":
        # iPhone-13-like insets (portrait: 47 top / 34 bottom; landscape: 0/21 and 47 left+right)
        ins = dict(top=0, bottom=21, left=47, right=47) if landscape else dict(top=47, bottom=34, left=0, right=0)
        if device != "iphone13":
            ins = dict(top=0, bottom=0, left=0, right=0)   # Android: no notch inset in the WebView by default
        set_safe_area(page, ctx, **ins)
    s = Shooter(page, out, tag, log)
    try:
        open_panel(page, rig)
    except Exception as e:  # noqa: BLE001
        log.append({"open_panel_failed": str(e)[:200]})
        s.shot("open-failed", measure=False)
        browser.close()
        return
    s.shot("home")
    if not full:
        browser.close()
        return
    loc = lambda sel: page.locator(sel).first  # noqa: E731

    # printer chip + drawer
    if s.step("chip", lambda: loc("button.printer-chip").click(timeout=5000)):
        s.shot("printer-drawer")
        s.step("drawer-close", lambda: loc(".pdrawer button[aria-label='Close']").click(timeout=3000))
        page.wait_for_timeout(300)
    # template gallery
    if s.step("gallery", lambda: loc(".mhome button:has-text('From template')").click(timeout=5000)):
        s.shot("template-gallery")
        s.step("gallery-pick", lambda: loc(".gallery .gal-card, .gallery button.gcard, .gallery [role=listitem] button").click(timeout=4000))
        page.wait_for_timeout(1200)
        s.shot("after-template")
        s.step("back", lambda: loc("button[aria-label^='Back to']").click(timeout=3000))
        page.wait_for_timeout(500)
        s.step("discard", lambda: loc("button:has-text('Discard')").click(timeout=1500))
    # new label -> editor
    if s.step("new", lambda: loc(".mhome button:has-text('New label')").click(timeout=5000)):
        page.wait_for_timeout(800)
        s.shot("editor-empty")
        s.step("add-text", lambda: loc(".tadd button:has-text('Text')").click(timeout=4000))
        page.wait_for_timeout(1000)
        s.shot("text-added-sheet")
        s.step("sheet-full", lambda: loc(".grab").press("Enter"))
        s.shot("sheet-cycled")
        s.step("sheet-full2", lambda: loc(".grab").press("Enter"))
        s.shot("sheet-cycled2")
        # text field focus + simulate soft keyboard by shrinking the visual viewport (layout viewport on Android)
        def kb():
            ta = loc(".bsheet textarea, .bsheet input[type=text]")
            ta.click(timeout=3000)
            ta.fill("Hello phone label 123")
            vp = page.viewport_size
            page.set_viewport_size({"width": vp["width"], "height": int(vp["height"] * 0.55)})
        if s.step("kb", kb):
            s.shot("keyboard-open")
            vp = page.viewport_size
            page.set_viewport_size({"width": vp["width"], "height": int(vp["height"] / 0.55)})
            page.wait_for_timeout(300)
        s.step("done", lambda: loc(".sdone").click(timeout=3000))
        s.shot("sheet-closed")
        s.step("deselect", lambda: page.touchscreen.tap(page.viewport_size["width"] // 2, int(page.viewport_size["height"] * 0.17)))
        s.shot("deselected")
        s.step("add-qr", lambda: loc(".tadd button:has-text('QR code')").click(timeout=3000))
        page.wait_for_timeout(800)
        s.shot("qr-added")
        s.step("more", lambda: loc(".tadd button:has-text('More')").click(timeout=3000))
        s.shot("add-more")
        s.step("esc", lambda: loc(".layer button[aria-label='Close'], .msheet button[aria-label='Close']").click(timeout=2000))
        # overflow / editor menu
        s.step("emore", lambda: loc("button.emore").click(timeout=3000))
        s.shot("editor-menu")
        s.step("esc2", lambda: page.mouse.click(5, 300))
        # print
        if s.step("print", lambda: loc(".medit button.btn.primary:has-text('Print')").click(timeout=4000)):
            page.wait_for_timeout(1500)
            s.shot("print-sheet")
            s.step("print-go", lambda: loc(".print-sheet button.primary:has-text('Print')").click(timeout=3000))
            page.wait_for_timeout(2500)
            s.shot("print-done")
    if errors:
        log.append({"console_errors": errors[:10]})
    browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", required=True, help="output directory for screenshots + measurements.json")
    ap.add_argument("--only", help="comma list of device names (iphone13,pixel7,small360,desktop)")
    ap.add_argument("--matrix", choices=["quick", "full"], default="full",
                    help="quick: portrait light only; full: portrait+landscape x light+dark (flow only on portrait light)")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--attach", action="store_true", help="use an already running rig (serve.py) instead of starting one")
    ap.add_argument("--keep-running", action="store_true", help="leave HA running (stop with serve.pid)")
    ap.add_argument("--port", type=int, default=18123)
    ap.add_argument("--printer-port", type=int, default=18765)
    ap.add_argument("--config-dir")
    a = ap.parse_args()
    out = Path(a.shots)
    out.mkdir(parents=True, exist_ok=True)
    devices = a.only.split(",") if a.only else ["iphone13", "pixel7", "small360"]
    from playwright.sync_api import sync_playwright
    rig = Rig(a.config_dir, a.port, a.printer_port, a.reset, verbose=True)
    if a.attach:
        rig.state = json.loads(rig.state_file.read_text())
        a.keep_running = True
    else:
        rig.start()
    results: dict = {}
    try:
        with sync_playwright() as p:
            for d in devices:
                for land, dark in ([(False, False)] if a.matrix == "quick" else
                                   [(False, False), (False, True), (True, False), (True, True)]):
                    try:
                        scenario(p, rig, out, d, land, dark, results, full=not land and not dark or d == "iphone13")
                    except Exception:  # noqa: BLE001
                        traceback.print_exc()
            try:
                scenario(p, rig, out, "pixel7", False, False, results, companion=True, full=False)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
        (out / "measurements.json").write_text(json.dumps(results, indent=1))
        if rig.printer:
            print("jobs received by the fake printer:", [(len(j), n) for j, n in rig.printer.jobs])
    finally:
        if not a.keep_running:
            rig.stop()
        else:
            print("leaving HA running on", rig.base)


if __name__ == "__main__":
    main()
