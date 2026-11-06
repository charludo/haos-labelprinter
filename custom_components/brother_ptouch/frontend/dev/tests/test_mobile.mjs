import assert from "node:assert/strict";
import { fitWidthZoom, sheetSnaps, pickSnap, cycleSnap, kbInset, NavStack, restorePlan, homeStatus, homeColumns, designKey, toolbarMode, stepCopies, isNarrowWidth, isVisible } from "../../lib/mobile.js";

let n = 0; const t = (name, fn) => { fn(); n++; console.log("ok -", name); };

t("narrow threshold", () => { assert.ok(isNarrowWidth(390)); assert.ok(isNarrowWidth(899)); assert.ok(!isNarrowWidth(900)); assert.ok(!isNarrowWidth(0)); });

t("fit-to-width zoom: fits, floors, clamps", () => {
  assert.equal(fitWidthZoom(200, 360), 1.8);
  assert.equal(fitWidthZoom(100, 360), 3.6);
  assert.equal(fitWidthZoom(60, 360), 5);           // max
  assert.equal(fitWidthZoom(2000, 360), 1);         // long labels: min 1, scroll sideways
  assert.equal(fitWidthZoom(0, 360), 1);
  assert.equal(fitWidthZoom(200, 0), 1);
  const z = fitWidthZoom(333, 361); assert.ok(z * 333 <= 361 + 1e-6 && z >= 1);
});

t("sheet snaps are ordered and fit the container", () => {
  for (const H of [320, 420, 560, 700, 900]) {
    const s = sheetSnaps(H);
    assert.ok(s.peek > 0 && s.peek < s.half && s.half < s.full, JSON.stringify([H, s]));
    assert.ok(s.full <= H - 80, "leaves canvas strip");
  }
  assert.equal(sheetSnaps(700).peek, 200);
  assert.equal(sheetSnaps(700).half, 350);
});

t("snap picking: nearest, flick, close", () => {
  const s = sheetSnaps(700);
  assert.equal(pickSnap(s.half, 0, s), "half");
  assert.equal(pickSnap(s.half + 20, 0, s), "half");
  assert.equal(pickSnap(s.peek + 30, 0, s), "peek");
  assert.equal(pickSnap(s.peek + 10, 1.5, s), "half");     // flick up
  assert.equal(pickSnap(s.half - 10, 1.5, s), "full");
  assert.equal(pickSnap(s.half, -1, s), "peek");          // flick down
  assert.equal(pickSnap(s.peek, -1, s), "closed");
  assert.equal(pickSnap(40, 0, s), "closed");
  assert.equal(pickSnap(s.full, 2, s), "full");
  assert.equal(cycleSnap("peek"), "half"); assert.equal(cycleSnap("full"), "peek"); assert.equal(cycleSnap("x"), "half");
});

t("visibility test for reveal", () => {
  assert.ok(isVisible(100, 160, 0, 300));
  assert.ok(!isVisible(280, 340, 0, 300));
  assert.ok(!isVisible(0, 40, 20, 300));
});

t("keyboard inset", () => {
  assert.equal(kbInset(800, null), 0);
  assert.equal(kbInset(800, { offsetTop: 0, height: 800 }), 0);
  assert.equal(kbInset(800, { offsetTop: 0, height: 780 }), 0);          // URL bar jitter
  assert.equal(kbInset(800, { offsetTop: 0, height: 480 }), 320);
  assert.equal(kbInset(800, { offsetTop: 100, height: 400 }), 300);      // iOS scrolled the layout viewport
  assert.equal(kbInset(500, { offsetTop: 0, height: 480 }), 0);          // Android resized the layout viewport
});

t("nav stack: editor -> sheet -> layer, Back pops newest first", () => {
  const s = new NavStack();
  s.push("edit"); s.push("sheet"); s.push("layer");
  assert.equal(s.depth, 3); assert.ok(s.has("layer"));
  let r = s.onPopState(); assert.equal(r.entry.kind, "layer"); assert.ok(!r.again);
  r = s.onPopState(); assert.equal(r.entry.kind, "sheet");
  r = s.onPopState(); assert.equal(r.entry.kind, "edit");
  r = s.onPopState(); assert.ok(r.ignore && r.leave, "empty stack: browser leaves the panel");
});

t("nav stack: programmatic close swallows its own popstate", () => {
  const s = new NavStack();
  s.push("edit"); s.push("layer");
  assert.deepEqual(s.close("layer"), { back: true });
  assert.equal(s.depth, 1);
  assert.deepEqual(s.onPopState(), { ignore: true });    // the history.back() we issued
  assert.equal(s.depth, 1);
  const r = s.onPopState(); assert.equal(r.entry.kind, "edit");
  assert.deepEqual(s.close("layer"), { back: false });   // nothing to close
});

t("nav stack: closing a non-top entry leaves a ghost that Back skips", () => {
  const s = new NavStack();
  s.push("edit"); s.push("sheet"); s.push("layer");
  assert.deepEqual(s.close("sheet"), { back: false });
  assert.ok(!s.has("sheet"));
  let r = s.onPopState(); assert.equal(r.entry.kind, "layer"); assert.ok(r.again, "ghost below: go back once more");
  assert.deepEqual(s.onPopState(), { ignore: true });
  r = s.onPopState(); assert.equal(r.entry.kind, "edit");
});

t("restore plan after reload", () => {
  assert.deepEqual(restorePlan("edit", { id: "a" }), { view: "edit", fixHistory: "" });
  assert.deepEqual(restorePlan("edit", { design: { name: "x" } }), { view: "edit", fixHistory: "" });
  assert.deepEqual(restorePlan("layer", { id: "a" }), { view: "edit", fixHistory: "back" });
  assert.deepEqual(restorePlan(undefined, { id: "a" }), { view: "home", fixHistory: "" });
  assert.deepEqual(restorePlan("edit", null), { view: "home", fixHistory: "reset" });
  assert.deepEqual(restorePlan(undefined, null), { view: "home", fixHistory: "" });
});

t("home status card", () => {
  const ok = { entry_id: "a", name: "Office", online: true, reason: "ok", state: "idle", tape: { width_mm: 12 }, transport: "bluetooth" };
  assert.equal(homeStatus([], "", false), null);
  assert.equal(homeStatus([], "", true).kind, "setup");
  assert.equal(homeStatus([ok], "a", true), null);
  const off = homeStatus([{ ...ok, online: false, reason: "asleep" }], "a", true);
  assert.equal(off.kind, "offline"); assert.equal(off.action, "connect"); assert.match(off.text, /power button/);
  assert.equal(homeStatus([{ ...ok, online: false, reason: "no_dbus" }], "a", true).action, "printers");
  assert.equal(homeStatus([{ ...ok, online: false, reason: "asleep", transport: "usb" }], "a", true).action, "printers");
  assert.equal(homeStatus([{ ...ok, tape: null }], "a", true).kind, "notape");
  assert.equal(homeStatus([{ ...ok, state: "error", message: "Cover open" }], "a", true).text, "Cover open");
});

t("columns, keys, toolbar, copies", () => {
  assert.equal(homeColumns(360), 1); assert.equal(homeColumns(700), 2);
  assert.notEqual(designKey({ id: "a", updated: "1" }), designKey({ id: "a", updated: "2" }));
  assert.equal(toolbarMode({ hasSelection: false, sheetOpen: false, keyboard: false }), "add");
  assert.equal(toolbarMode({ hasSelection: true, sheetOpen: false, keyboard: false }), "element");
  assert.equal(toolbarMode({ hasSelection: true, sheetOpen: true, keyboard: false }), "none");
  assert.equal(toolbarMode({ hasSelection: false, sheetOpen: false, keyboard: true }), "none");
  assert.equal(stepCopies(1, -1), 1); assert.equal(stepCopies(20, 1), 20); assert.equal(stepCopies(3, 2), 5); assert.equal(stepCopies("x", 1), 2);
});
console.log(`${n} passed`);
