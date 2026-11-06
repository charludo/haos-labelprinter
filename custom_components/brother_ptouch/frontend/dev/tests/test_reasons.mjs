import assert from "node:assert/strict";
import { REASONS, REASON_TEXT, reasonText, reasonShort, normReason, canRetry, btUnavailable, reasonFromMessage, reasonFromError, failureSentence, connectOutcome } from "../../lib/reasons.js";

let n = 0; const t = (name, fn) => { fn(); n++; console.log("ok -", name); };

t("every non-ok reason has a sentence and a short label", () => {
  for (const r of REASONS) {
    assert.ok(REASON_TEXT[r], r);
    if (r !== "ok") assert.ok(reasonShort(r) && reasonShort(r) !== "Offline", r);
  }
});
t("contract wording", () => {
  assert.equal(reasonText("asleep"), "The printer isn't answering. Press its power button to switch it on, make sure no phone is connected to it, then try again.");
  assert.equal(reasonText("not_paired"), "This printer isn't paired with Home Assistant yet.");
  assert.equal(reasonText("bluetooth_off"), "Bluetooth is switched off on the Home Assistant host.");
  assert.equal(reasonText("busy"), "The printer is connected to something else (a phone?). Disconnect it and try again.");
  for (const r of ["no_dbus", "no_adapter", "no_library"]) assert.equal(reasonText(r), "Home Assistant can't use Bluetooth here. Use USB or the network bridge.");
});
t("unknown reasons collapse to error; error keeps the backend text", () => {
  assert.equal(normReason("weird"), "error"); assert.equal(normReason(undefined), "error");
  assert.equal(reasonText("error", "Custom text"), "Custom text");
  assert.equal(reasonText("error"), REASON_TEXT.error);
  assert.equal(reasonText("asleep", "ignored backend text"), REASON_TEXT.asleep);
});
t("bluetooth-unavailable and retryable sets", () => {
  assert.ok(btUnavailable("no_dbus") && btUnavailable("no_adapter") && btUnavailable("no_library") && !btUnavailable("asleep"));
  assert.ok(canRetry("asleep") && canRetry("busy") && !canRetry("no_dbus") && !canRetry("not_paired"));
});
t("message -> reason (friendly texts round trip)", () => {
  for (const r of ["asleep", "not_paired", "bluetooth_off", "busy", "no_dbus"]) assert.equal(reasonFromMessage(REASON_TEXT[r]), r, r);
  assert.equal(reasonFromMessage("Something exploded"), "error");
  assert.equal(reasonFromMessage(""), "error");
  assert.equal(reasonFromMessage(REASON_TEXT.pairing_timeout), "pairing_timeout");
  assert.equal(reasonFromMessage(REASON_TEXT.pairing_failed), "pairing_failed");
});
t("error frames: code wins, then message", () => {
  assert.equal(reasonFromError({ code: "pairing_timeout", message: "x" }), "pairing_timeout");
  assert.equal(reasonFromError({ code: "bluetooth_unavailable", message: "x" }), "no_dbus");
  assert.equal(reasonFromError({ code: "device_not_found" }), "not_found");
  assert.equal(reasonFromError({ code: "home_assistant_error", message: REASON_TEXT.busy }), "busy");
});
t("failureSentence: shared wording for known, backend text otherwise", () => {
  assert.deepEqual(failureSentence({ message: REASON_TEXT.asleep }), { reason: "asleep", text: REASON_TEXT.asleep });
  assert.deepEqual(failureSentence({ message: "Paper jam" }), { reason: "error", text: "Paper jam" });
  assert.equal(failureSentence(null, "fallback").text, "fallback");
});
t("connectOutcome", () => {
  assert.deepEqual(connectOutcome({ ok: true, reason: "ok", seconds: 0.4 }), { ok: true, reason: "ok", text: "Connected.", retry: false });
  assert.equal(connectOutcome({ ok: true, seconds: 7.2 }).text, "Connected after 7 s.");
  const f = connectOutcome({ ok: false, reason: "asleep", message: "raw" });
  assert.equal(f.ok, false); assert.equal(f.text, REASON_TEXT.asleep); assert.ok(f.retry);
  assert.equal(connectOutcome({ ok: false, reason: "no_dbus" }).retry, false);
  assert.equal(connectOutcome({ ok: false, reason: "mystery", message: "Odd" }).text, "Odd");
});
console.log(`${n} tests passed`);
