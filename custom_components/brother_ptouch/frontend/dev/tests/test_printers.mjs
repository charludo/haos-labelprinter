import assert from "node:assert/strict";
import * as L from "../../lib/printer_logic.js";
import { REASON_TEXT } from "../../lib/reasons.js";

let n = 0; const t = (name, fn) => { fn(); n++; console.log("ok -", name); };
const row = (o) => L.normalizePrinter({ entry_id: "p1", title: "Office", name: "Office", transport: "bluetooth", online: true, reason: "ok", message: "", state: "idle",
  tape_mm: 12, tape: { width_mm: 12, type: "laminated", colour: "white", text_colour: "black" }, ...o });

t("normalizePrinter accepts the old row shape", () => {
  const p = L.normalizePrinter({ entry_id: "a", title: "Old", tape_mm: 4, state: "idle" });
  assert.equal(p.name, "Old"); assert.equal(p.online, true); assert.equal(p.tape.width_mm, 3.5); assert.equal(p.tape_mm, 4);
  const q = L.normalizePrinter({ entry_id: "b", title: "Off", tape_mm: null, state: "offline" });
  assert.equal(q.online, false); assert.equal(q.reason, "asleep"); assert.equal(q.tape, null);
});
t("tape line", () => {
  assert.equal(L.tapeLine({ width_mm: 12, type: "laminated", colour: "white", text_colour: "black" }), "12 mm laminated, white tape, black text");
  assert.equal(L.tapeLine({ width_mm: 3.5, type: "", colour: "", text_colour: "" }), "3.5 mm");
  assert.equal(L.tapeLine({ width_mm: 24, type: "Non-laminated", colour: "Clear", text_colour: "Black" }), "24 mm non-laminated, clear tape, black text");
  assert.equal(L.tapeLine(null), "");
});
t("chip: no printer, loading", () => {
  assert.deepEqual(L.chipState([], "", true), { dot: "grey", name: "Printer", status: "No printer", title: "No printer set up" });
  assert.equal(L.chipState([], "", false).status, "…");
  assert.equal(L.chipState([row()], "gone", true).dot, "grey");
});
t("chip: green / amber / red", () => {
  assert.deepEqual([L.chipState([row()], "p1").dot, L.chipState([row()], "p1").status, L.chipState([row()], "p1").name], ["green", "12 mm", "Office"]);
  assert.equal(L.chipState([row({ tape: null, tape_mm: null })], "p1").status, "No tape");
  assert.equal(L.chipState([row({ tape: null, tape_mm: null })], "p1").dot, "amber");
  const a = L.chipState([row({ online: false, reason: "asleep" })], "p1"); assert.deepEqual([a.dot, a.status], ["amber", "Asleep"]);
  assert.equal(L.chipState([row({ online: false, reason: "busy" })], "p1").status, "Busy");
  assert.equal(L.chipState([row({ online: false, reason: "bluetooth_off" })], "p1").status, "Bluetooth off");
  const r = L.chipState([row({ state: "error", message: "Cover open" })], "p1"); assert.deepEqual([r.dot, r.status], ["red", "Cover open"]);
  assert.equal(L.chipState([row({ state: "error", message: "A very long error message indeed." })], "p1").status, "Printer error");
  assert.equal(L.chipState([row({ state: "printing" })], "p1").status, "Printing");
  assert.equal(L.chipState([row({ tape: { width_mm: 3.5 }, tape_mm: 4 })], "p1").status, "3.5 mm");
});
t("state sentence", () => {
  assert.equal(L.stateSentence(row()), "Ready to print.");
  assert.equal(L.stateSentence(row({ online: false, reason: "asleep" })), REASON_TEXT.asleep);
  assert.equal(L.stateSentence(row({ online: false, reason: "not_paired" })), REASON_TEXT.not_paired);
  assert.equal(L.stateSentence(row({ state: "error", message: "Cover open" })), "Cover open");
  assert.match(L.stateSentence(row({ tape: null, tape_mm: null })), /no tape/i);
});
t("active printer choice", () => {
  const ps = [row(), row({ entry_id: "p2" })];
  assert.equal(L.pickActive(ps, "p2"), "p2"); assert.equal(L.pickActive(ps, "zzz"), "p1"); assert.equal(L.pickActive([], "p1"), "");
});
t("drawer actions", () => {
  const bt = L.drawerActions(row(), { active: true, count: 1 });
  assert.ok(bt.connect && bt.test && bt.rename && bt.remove && !bt.use);
  assert.ok(!L.drawerActions(row({ transport: "usb" }), { count: 1 }).connect);
  assert.ok(L.drawerActions(row(), { active: false, count: 2 }).use);
  assert.ok(!L.drawerActions(row(), { active: true, count: 2 }).use);
  const busy = L.drawerActions(row(), { busy: "connect" });
  assert.ok(busy.connectDisabled && busy.testDisabled && busy.removeDisabled);
});
t("connection detail", () => {
  assert.deepEqual(L.connectionDetail(row({ address: "AA:BB" })), { icon: "mdi:bluetooth", text: "Bluetooth · AA:BB" });
  assert.equal(L.connectionDetail(row({ transport: "usb", serial: "S1" })).text, "USB · S1");
  assert.equal(L.connectionDetail(row({ transport: "bridge", url: "http://x" })).text, "Network bridge · http://x");
});
t("names", () => {
  assert.equal(L.defaultName("bluetooth", { name: "PT-P710BT4821" }, []), "PT-P710BT4821");
  assert.equal(L.defaultName("bluetooth", { name: "PT-P710BT4821" }, [{ name: "PT-P710BT4821" }]), "PT-P710BT4821 2");
  assert.equal(L.cleanName("  a   b "), "a b");
  assert.ok(L.nameError("", [])); assert.ok(L.nameError("office", [row()])); assert.equal(L.nameError("office", [row()], "p1"), "");
});
const dev = (name, o = {}) => ({ address: name, name, paired: false, trusted: false, connected: false, rssi: null, is_printer: false, configured: false, ...o });
t("signal bars", () => {
  assert.deepEqual([null, -40, -60, -65, -75, -95, undefined].map(L.signalBars), [0, 4, 4, 3, 2, 1, 0]);
});
t("scan list grouping and sorting", () => {
  const list = [dev("Pixel", { rssi: -40 }), dev("JBL"), dev("PT-P710BT2", { is_printer: true, rssi: -70 }), dev("PT-P710BT1", { is_printer: true, rssi: -50 }),
    dev("", { paired: false }), dev("OldTV", { paired: true, rssi: -90 }), dev("", { address: "x", paired: true }), dev("Brother laser", { is_printer: true })];
  const g = L.groupDevices(list);
  assert.deepEqual(g.printers.map((d) => d.name), ["PT-P710BT1", "PT-P710BT2", "Brother laser"]);
  assert.deepEqual(g.others.map((d) => d.name), ["Pixel", "OldTV", "", "JBL"]);
  assert.equal(L.groupDevices(null).printers.length, 0);
  assert.ok(L.looksLikePrinter({ name: "p-touch cube" }) && L.looksLikePrinter({ name: "PT-P300BT" }) && !L.looksLikePrinter({ name: "Pixel" }));
});
t("device actions", () => {
  assert.equal(L.deviceAction(dev("a")).kind, "pair");
  assert.equal(L.deviceAction(dev("a", { paired: true })).kind, "select");
  const c = L.deviceAction(dev("a", { paired: true, configured: true })); assert.equal(c.kind, "added"); assert.ok(c.disabled);
});

// ---- wizard state machine ----
const W = (o = {}) => ({ ...L.newWizard(), ...o });
t("wizard: how step needs a method", () => {
  const w = W(); assert.ok(!L.canNext(w)); assert.equal(L.nextStep(w), "how");
  w.method = "usb"; assert.ok(L.canNext(w)); assert.equal(L.nextStep(w), "usb");
  assert.equal(L.nextStep({ ...w, method: "bluetooth" }), "bluetooth"); assert.equal(L.nextStep({ ...w, method: "bridge" }), "bridge");
  assert.ok(!L.canBack(w));
});
t("wizard: bluetooth needs a paired selection and no pairing in flight", () => {
  const w = W({ step: "bluetooth", method: "bluetooth" });
  assert.ok(!L.canNext(w));
  w.device = dev("p", { paired: false }); assert.ok(!L.canNext(w));
  w.device = dev("p", { paired: true }); assert.ok(L.canNext(w)); assert.equal(L.nextStep(w), "test");
  w.pair = { status: "pairing", address: "p" }; assert.ok(!L.canNext(w)); assert.ok(!L.canBack(w));
  w.pair = { status: "failed", address: "p", reason: "pairing_failed" }; assert.ok(L.canNext(w) && L.canBack(w));
  assert.equal(L.prevStep(w), "how");
});
t("wizard: bridge URL validation", () => {
  const w = W({ step: "bridge", method: "bridge" });
  for (const bad of ["", "192.168.1.2", "ftp://x", "http://"]) { w.url = bad; assert.ok(!L.canNext(w), bad); }
  w.url = " http://192.168.1.20:8080 "; assert.ok(L.canNext(w));
  w.token = " tok "; assert.deepEqual(L.addPayload(w), { transport: "bridge", url: "http://192.168.1.20:8080", token: "tok" });
  w.token = ""; assert.deepEqual(L.addPayload(w), { transport: "bridge", url: "http://192.168.1.20:8080" });
});
t("wizard: payloads", () => {
  assert.deepEqual(L.addPayload(W({ method: "usb", serial: " " })), { transport: "usb" });
  assert.deepEqual(L.addPayload(W({ method: "usb", serial: "S1" })), { transport: "usb", serial: "S1" });
  assert.deepEqual(L.addPayload(W({ method: "bluetooth", device: dev("PT-P710BT1", { address: "AA" }) })), { transport: "bluetooth", address: "AA", name: "PT-P710BT1" });
});
t("wizard: test step add/retry/back", () => {
  const w = W({ step: "test", method: "usb" });
  w.addStatus = "adding"; assert.ok(!L.canPrimary(w) && !L.canBack(w));
  w.addStatus = "failed"; assert.ok(L.canPrimary(w) && L.canBack(w)); assert.equal(L.primaryLabel(w), "Try again"); assert.equal(L.prevStep(w), "usb");
  w.addStatus = "ok"; w.added = { entry_id: "p3" }; assert.ok(L.canPrimary(w)); assert.equal(L.nextStep(w), "name"); assert.ok(!L.canBack(w));
});
t("wizard: name step", () => {
  const w = W({ step: "name", method: "usb", added: { entry_id: "p3" }, name: "", existing: [row()] });
  assert.ok(!L.canNext(w)); w.name = "Office"; assert.ok(!L.canNext(w)); w.name = "Shop"; assert.ok(L.canNext(w));
  assert.equal(L.nextStep(w), "done"); assert.equal(L.primaryLabel(w), "Done"); assert.ok(!L.canBack(w));
});
t("wizard: progress index", () => {
  assert.deepEqual(["how", "bluetooth", "usb", "bridge", "test", "name"].map((s) => L.stepIndex({ step: s })), [0, 1, 1, 1, 2, 3]);
});
t("bluetooth blocked", () => {
  assert.ok(L.btBlocked({ available: false, reason: "no_dbus" })); assert.ok(!L.btBlocked({ available: true })); assert.ok(!L.btBlocked(null));
  assert.equal(L.btBlockedText({ available: false, reason: "no_dbus" }), REASON_TEXT.no_dbus);
});

// ---- print flow ----
t("print flow: success", () => {
  let f = L.newPrintFlow(); f = L.startPrint(f, 1000); assert.equal(f.phase, "waiting");
  const r = L.finishPrint(f, f.id, { ok: true }); assert.equal(r.flow.phase, "done"); assert.equal(r.late, null);
});
t("print flow: failure keeps reason + text, dismiss, retry", () => {
  let f = L.startPrint(L.newPrintFlow());
  f = L.finishPrint(f, f.id, { ok: false, reason: "asleep", text: REASON_TEXT.asleep }).flow;
  assert.deepEqual([f.phase, f.reason, f.text], ["failed", "asleep", REASON_TEXT.asleep]);
  f = L.dismissPrint(f); assert.equal(f.phase, "idle");
  f = L.startPrint(f); assert.equal(f.phase, "waiting"); assert.equal(f.id, 2);
});
t("print flow: cancelling the wait never breaks later prints", () => {
  let f = L.startPrint(L.newPrintFlow()); const first = f.id;
  f = L.cancelPrint(f); assert.equal(f.phase, "idle");
  f = L.startPrint(f); const second = f.id; assert.notEqual(first, second);
  // the cancelled attempt finishes (fails) while the second is waiting: ignored
  let r = L.finishPrint(f, first, { ok: false, reason: "asleep", text: "x" });
  assert.equal(r.flow.phase, "waiting"); assert.equal(r.late.ok, false); f = r.flow;
  // a cancelled attempt that succeeded is reported as late
  const g = L.cancelPrint(L.startPrint(L.newPrintFlow())); r = L.finishPrint(g, 1, { ok: true }); assert.equal(r.late.ok, true); assert.equal(r.flow.phase, "idle");
  r = L.finishPrint(f, second, { ok: true }); assert.equal(r.flow.phase, "done");
  assert.equal(L.cancelPrint(L.newPrintFlow()).phase, "idle");
  assert.equal(L.dismissPrint(f).phase, "waiting");   // cannot dismiss while waiting
});
t("waiting text", () => {
  const f = L.startPrint(L.newPrintFlow(), 0);
  assert.equal(L.waitingText(f, 1000), "Waiting for the printer… (up to 20 s)");
  assert.equal(L.waitingText(f, 7400), "Waiting for the printer… 7 of up to 20 s");
  assert.equal(L.waitingText(f, 90000), "Waiting for the printer… 20 of up to 20 s");
});
console.log(`${n} tests passed`);
