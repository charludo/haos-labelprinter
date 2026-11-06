// Pure logic for the phone experience (no DOM; covered by dev/tests/test_mobile.mjs):
// view/back-stack state machine, bottom-sheet snap maths, fit-to-width zoom, keyboard inset,
// home-screen status card and toolbar mode.
import { reasonText } from "./reasons.js";

export const NARROW_PX = 900;
export const isNarrowWidth = (w) => w > 0 && w < NARROW_PX;

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

// ---- zoom -----------------------------------------------------------------------------------------
/**
 * Default zoom on a phone: the whole label width fits the canvas (`availPx`), but never below `min`
 * (elements must stay touchable; very long labels then scroll sideways) nor above `max`.
 * Rounded down to `step` so that dots map to whole-ish pixels.
 */
export function fitWidthZoom(contentW, availPx, { min = 1, max = 5, step = 0.05 } = {}) {
  if (!(contentW > 0) || !(availPx > 0)) return min;
  const z = Math.floor((availPx / contentW) / step + 1e-9) * step;
  return Math.round(clamp(z, min, max) * 1000) / 1000;
}

// ---- bottom sheet -------------------------------------------------------------------------------------
export const SNAPS = ["peek", "half", "full"];

/** Heights (px) of the three snap points for a container of height `H`. */
export function sheetSnaps(H, { peek = 200, minCanvas = 88 } = {}) {
  H = Math.max(0, H);
  const full = Math.max(120, Math.round(H - minCanvas));
  const pk = Math.min(peek, Math.round(full * 0.6));
  const half = clamp(Math.round(H * 0.5), pk + 40, Math.max(pk + 40, full - 40));
  return { peek: pk, half: Math.min(half, full), full };
}

/**
 * Where a drag that ended at height `h` with vertical velocity `vel` (px/ms, positive = moving up) settles:
 * the nearest snap to the position it was heading for; well below peek means closed.
 */
export function pickSnap(h, vel, snaps) {
  const proj = h + vel * 160;
  if (proj < snaps.peek * 0.55) return "closed";
  let best = "peek";
  for (const k of SNAPS) if (Math.abs(snaps[k] - proj) < Math.abs(snaps[best] - proj)) best = k;
  return best;
}

/** Next snap when the grabber is tapped: peek -> half -> full -> peek. */
export function cycleSnap(cur) { return { peek: "half", half: "full", full: "peek" }[cur] || "half"; }

/**
 * Is a box (content px, inside a scroller of `viewH` showing from `scrollTop`) fully visible with margin?
 * Used to decide whether the canvas must be scrolled so that the element stays above the sheet.
 */
export function isVisible(lo, hi, scroll, size, margin = 8) {
  return lo - margin >= scroll && hi + margin <= scroll + size;
}

// ---- soft keyboard ---------------------------------------------------------------------------------------
/**
 * Height (px) of the on-screen keyboard that overlaps the panel. `hostBottom` = host.getBoundingClientRect().bottom
 * (layout viewport coords), vv = window.visualViewport ({offsetTop, height}) or null. Android WebViews that resize the
 * layout viewport already shrink the host, so no overlap is seen there (returns 0). Small overlaps (URL bar) are ignored.
 */
export function kbInset(hostBottom, vv, { threshold = 90 } = {}) {
  if (!vv) return 0;
  const visibleBottom = (vv.offsetTop || 0) + vv.height;
  const o = Math.round(hostBottom - visibleBottom);
  return o > threshold ? o : 0;
}

// ---- views and the history back-stack ---------------------------------------------------------------------
/**
 * What the Back button / swipe pops, top first. Each entry mirrors one history.pushState done by the panel:
 *   edit  - the editor view (home is the base, it has no entry)
 *   sheet - the properties bottom sheet
 *   layer - a full-screen sheet / dialog (gallery, printers, wizard, print, menus, confirm)
 * `pop()` is a programmatic close (the caller then calls history.back() and swallows one popstate);
 * `onPopState()` is a Back press and tells which entry the UI must close.
 */
export class NavStack {
  constructor() { this.stack = []; this.skip = 0; }
  get depth() { return this.stack.length; }
  get top() { return this.stack[this.stack.length - 1] || null; }
  has(kind) { return this.stack.some((e) => e.kind === kind && !e.dead); }
  push(kind) { const e = { kind, dead: false }; this.stack.push(e); return e; }
  /** Programmatic close of the newest `kind`. -> {back:true} when a history.back() is needed. */
  close(kind) {
    for (let i = this.stack.length - 1; i >= 0; i--) {
      const e = this.stack[i];
      if (e.kind !== kind || e.dead) continue;
      if (i === this.stack.length - 1) { this.stack.pop(); this.skip++; return { back: true }; }
      e.dead = true;            // not the newest: leave a ghost entry in the browser history
      return { back: false };
    }
    return { back: false };
  }
  /** A popstate event arrived. -> {ignore} | {entry, again}: close `entry` in the UI; `again` = a ghost sits under it, go back once more. */
  onPopState() {
    if (this.skip > 0) { this.skip--; return { ignore: true }; }
    const e = this.stack.pop();
    if (!e) return { ignore: true, leave: true };   // nothing of ours left: the browser is leaving the panel
    let again = false;
    while (this.top && this.top.dead) { this.stack.pop(); this.skip++; again = true; }
    return { entry: e, again };
  }
  reset() { this.stack = []; this.skip = 0; }
}

/** After a reload: what to restore, given history.state.bp and the remembered session. */
export function restorePlan(historyBp, session) {
  const hasDoc = !!session && (session.id || session.design);
  if (!hasDoc) return { view: "home", fixHistory: historyBp === "edit" || historyBp === "sheet" || historyBp === "layer" ? "reset" : "" };
  if (historyBp === "edit") return { view: "edit", fixHistory: "" };
  if (historyBp === "sheet" || historyBp === "layer") return { view: "edit", fixHistory: "back" };
  return { view: "home", fixHistory: "" };
}

// ---- home screen ---------------------------------------------------------------------------------------------
/**
 * Printer status card shown on the home screen only when something needs attention.
 * -> null | { kind: "setup"|"offline"|"error"|"notape"|"loading", tone, title, text, action }.
 */
export function homeStatus(printers, entryId, loaded) {
  if (!loaded) return null;
  if (!printers.length) return { kind: "setup", tone: "info", title: "Set up your printer", text: "Add your PT-P710BT to print the labels you design here.", action: "setup" };
  const p = printers.find((x) => x.entry_id === entryId) || printers[0];
  if (p.state === "error") return { kind: "error", tone: "err", title: `${p.name} reports an error`, text: p.message || "The printer reports an error.", action: "printers" };
  if (!p.online) {
    const r = p.reason === "ok" ? "asleep" : p.reason;
    const bt = p.transport === "bluetooth" || !p.transport;
    return { kind: "offline", tone: "warn", title: `${p.name} is offline`, text: reasonText(r, p.message), action: bt && !["no_dbus", "no_adapter", "no_library", "permission"].includes(r) ? "connect" : "printers" };
  }
  if (!p.tape) return { kind: "notape", tone: "warn", title: "No tape detected", text: "Load a tape cassette and close the lid.", action: "printers" };
  return null;
}

/** How many columns of label cards fit (preview strips are wide, so 1 column on phones). */
export function homeColumns(width) { return width >= 640 ? 2 : 1; }

/** Cache key of a saved design's thumbnail (changes when the design is saved again). */
export const designKey = (d) => `${d.id}@${d.updated || ""}`;

// ---- editor bottom toolbar --------------------------------------------------------------------------------------
/** "add" (nothing selected), "element" (something selected), "none" (a sheet is open or the keyboard is). */
export function toolbarMode({ hasSelection, sheetOpen, keyboard }) {
  if (sheetOpen || keyboard) return "none";
  return hasSelection ? "element" : "add";
}

export const stepCopies = (n, d, max = 20) => clamp((Number(n) || 1) + d, 1, max);
