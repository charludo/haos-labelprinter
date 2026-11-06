// Failure-reason vocabulary shared with the backend (docs/BLUETOOTH_CONTRACT.md section 1), plus the
// wording the UI shows. Pure module (no DOM): used by the drawer, the wizard, the print flow and node tests.

export const REASONS = ["ok", "asleep", "not_paired", "bluetooth_off", "no_adapter", "no_dbus", "no_library", "busy",
  "pairing_failed", "pairing_timeout", "not_found", "permission", "error"];

const CANT_USE_BT = "Home Assistant can't use Bluetooth here. Use USB or the network bridge.";

/** Full sentence: what happened and what to do. */
export const REASON_TEXT = {
  ok: "Connected.",
  asleep: "The printer isn't answering. Press its power button to switch it on, make sure no phone is connected to it, then try again.",
  not_paired: "This printer isn't paired with Home Assistant yet.",
  bluetooth_off: "Bluetooth is switched off on the Home Assistant host.",
  busy: "The printer is connected to something else (a phone?). Disconnect it and try again.",
  no_dbus: CANT_USE_BT, no_adapter: CANT_USE_BT, no_library: CANT_USE_BT,
  pairing_failed: "Pairing didn't work. Switch the printer off and on, keep it close, make sure no phone is connected to it, then try again.",
  pairing_timeout: "The printer didn't respond while pairing. Switch it on, keep it close and try again.",
  not_found: "Home Assistant can't see that printer. Switch it on, keep it close and scan again.",
  permission: "Home Assistant isn't allowed to use Bluetooth here. Check the permissions of the Bluetooth service, or use USB or the network bridge.",
  error: "Something went wrong talking to the printer.",
};

/** 1-2 word status for the top-bar chip and list rows. */
export const REASON_SHORT = {
  asleep: "Not answering", busy: "Busy", not_paired: "Not paired", bluetooth_off: "Bluetooth off",
  no_dbus: "No Bluetooth", no_adapter: "No Bluetooth", no_library: "No Bluetooth",
  pairing_failed: "Pairing failed", pairing_timeout: "Pairing timed out", not_found: "Not found", permission: "No permission", error: "Error",
};

/** Reasons that mean this host cannot do Bluetooth at all (steer the user to USB / bridge). */
export const BT_UNAVAILABLE = new Set(["no_dbus", "no_adapter", "no_library", "permission"]);

export function normReason(r) { return REASONS.includes(r) ? r : "error"; }
export const btUnavailable = (r) => BT_UNAVAILABLE.has(r);

/** Sentence for a reason; `message` (backend text) is only used for unknown/generic reasons. */
export function reasonText(reason, message = "") {
  const r = normReason(reason);
  if (r === "error" && message) return message;
  return REASON_TEXT[r];
}
export function reasonShort(reason) { return REASON_SHORT[normReason(reason)] || "Offline"; }

/** Reasons the user can fix by waking/moving the printer (a Retry makes sense). */
export const RETRYABLE = new Set(["asleep", "busy", "not_found", "pairing_timeout", "pairing_failed", "error", "bluetooth_off"]);
export const canRetry = (reason) => RETRYABLE.has(normReason(reason));

// Backend error frames carry only a message; map the friendly texts (and a few raw phrases) back to a reason.
const PATTERNS = [
  ["asleep", /isn'?t answering|not answering|page timeout|no answer|asleep|host is down/i],
  ["not_paired", /isn'?t paired|not paired|not been paired/i],
  ["bluetooth_off", /bluetooth is switched off|bluetooth is off|powered off|not powered/i],
  ["busy", /connected to something else|connected to another|resource busy|in use|\bbusy\b/i],
  ["no_dbus", /can'?t use bluetooth|cannot use bluetooth|no bluetooth adapter|d-?bus/i],
  ["pairing_timeout", /didn'?t respond while pairing|pairing timed out/i],
  ["pairing_failed", /pairing (didn'?t work|failed)|authentication failed/i],
  ["not_found", /can'?t see that printer|not found/i],
];
export function reasonFromMessage(message) {
  const m = String(message || "");
  for (const [r, re] of PATTERNS) if (re.test(m)) return r;
  return "error";
}

/** Error frame code from the wizard/pairing API -> reason. */
const CODE_REASON = { bluetooth_unavailable: "no_dbus", device_not_found: "not_found", pairing_failed: "pairing_failed", pairing_timeout: "pairing_timeout" };
export function reasonFromError(err) {
  const c = err?.code;
  if (CODE_REASON[c]) return CODE_REASON[c];
  return reasonFromMessage(err?.message);
}

/**
 * Turn a WebSocket error / result into the sentence shown to the user.
 * Known reasons get the shared wording; unknown errors keep the backend's own text.
 */
export function failureSentence(err, fallback = "Something went wrong.") {
  const msg = (err && (err.message || String(err))) || "";
  const r = reasonFromError(err);
  if (r !== "error") return { reason: r, text: REASON_TEXT[r] };
  return { reason: "error", text: msg || fallback };
}

/** Result of bluetooth/connect ({ok, reason, seconds, message}) -> {ok, reason, text, retry}. */
export function connectOutcome(res) {
  if (res?.ok) {
    const s = Number(res.seconds);
    return { ok: true, reason: "ok", text: Number.isFinite(s) && s >= 1 ? `Connected after ${Math.round(s)} s.` : "Connected.", retry: false };
  }
  const reason = normReason(res?.reason);
  return { ok: false, reason, text: reasonText(reason, res?.message), retry: canRetry(reason) };
}
