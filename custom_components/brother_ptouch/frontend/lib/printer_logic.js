// Pure logic for printer management (no DOM): row normalising, chip state, drawer actions, scan list,
// Add-printer wizard state machine and the print-flow state. Covered by dev/tests/test_printers.mjs.
import { reasonShort, reasonText, normReason, btUnavailable, reasonFromMessage } from "./reasons.js";

export const DEFAULT_TAPE = 12;
export const WAKE_SECONDS = 20;   // how long a print may wait for a sleeping printer (backend option wake_seconds)

export const tapeWidthText = (mm) => (Number(mm) === 4 || Number(mm) === 3.5 ? "3.5 mm" : `${mm} mm`);

/** Accept both the old row ({entry_id,title,tape_mm,state}) and the extended one of contract section 3. */
export function normalizePrinter(row) {
  const r = { ...row };
  r.name = row.name || row.title || "Printer";
  r.title = row.title || r.name;
  r.state = row.state || "idle";
  r.transport = row.transport || "";
  r.online = row.online != null ? !!row.online : r.state !== "offline";
  r.reason = r.online && !row.reason ? "ok" : normReason(row.reason || (r.online ? "ok" : "asleep"));
  r.message = row.message || "";
  let tape = row.tape || null;
  if (!tape && row.tape_mm) tape = { width_mm: row.tape_mm === 4 ? 3.5 : row.tape_mm, type: "", colour: "", text_colour: "" };
  r.tape = tape;
  r.tape_mm = row.tape_mm != null ? row.tape_mm : tape ? (tape.width_mm === 3.5 ? 4 : tape.width_mm) : null;
  return r;
}

/** "12 mm laminated, white tape, black text" (missing parts are left out). */
export function tapeLine(tape) {
  if (!tape || !tape.width_mm) return "";
  const head = [tapeWidthText(tape.width_mm), tape.type].filter(Boolean).join(" ").toLowerCase().replace(/^(\S+) mm/, "$1 mm");
  const parts = [head];
  if (tape.colour) parts.push(`${String(tape.colour).toLowerCase()} tape`);
  if (tape.text_colour) parts.push(`${String(tape.text_colour).toLowerCase()} text`);
  return parts.join(", ");
}

/** Sentence under the printer name in the drawer. */
export function stateSentence(p) {
  if (!p) return "";
  if (p.state === "printing") return "Printing…";
  if (p.state === "error") return p.message || "The printer reports an error.";
  if (!p.online) return reasonText(p.reason === "ok" ? "asleep" : p.reason, p.message);
  if (!p.tape) return "Connected, but no tape was detected.";
  return "Ready to print.";
}

/**
 * Top-bar chip: { dot: "green"|"amber"|"red"|"grey", name, status, title }.
 * `loaded` false = the list has not been fetched yet.
 */
export function chipState(printers, entryId, loaded = true) {
  const list = printers || [];
  if (!loaded) return { dot: "grey", name: "Printer", status: "…", title: "Loading printers" };
  const p = list.find((x) => x.entry_id === entryId) || null;
  if (!p) return { dot: "grey", name: "Printer", status: "No printer", title: "No printer set up" };
  const name = p.name;
  const sub = (dot, status, title) => ({ dot, name, status, title: title || `${name}: ${status}` });
  if (p.state === "error") return sub("red", shortErr(p.message), p.message || "Printer error");
  if (!p.online) return sub("amber", p.reason === "ok" ? "Offline" : reasonShort(p.reason), stateSentence(p));
  if (p.state === "printing") return sub("green", "Printing");
  if (!p.tape) return sub("amber", "No tape", stateSentence(p));
  return sub("green", tapeWidthText(p.tape.width_mm));
}
function shortErr(msg) {
  const m = String(msg || "").trim().replace(/[.!]$/, "");
  return m && m.length <= 18 ? m : "Printer error";
}

/** Which printer is active: the saved id if it still exists, else the first one, else "". */
export function pickActive(printers, wanted) {
  if (printers.some((p) => p.entry_id === wanted)) return wanted;
  return printers[0]?.entry_id || "";
}

/** Buttons available for a printer row in the drawer. */
export function drawerActions(p, { active = false, count = 1, busy = "" } = {}) {
  const bt = p?.transport === "bluetooth";
  return {
    use: count > 1 && !active,
    connect: bt, connectDisabled: !!busy,
    test: true, testDisabled: !!busy,
    rename: true, remove: true, removeDisabled: busy === "connect" || busy === "test",
  };
}

/** Connection line: "Bluetooth · AA:BB:…", "USB · serial", "Network bridge · url". */
export function connectionDetail(p) {
  const kind = { bluetooth: ["mdi:bluetooth", "Bluetooth", p.address], usb: ["mdi:usb", "USB", p.serial], bridge: ["mdi:lan-connect", "Network bridge", p.url] }[p.transport];
  if (!kind) return { icon: "mdi:printer", text: "Printer" };
  return { icon: kind[0], text: [kind[1], kind[2]].filter(Boolean).join(" · ") };
}

/** Default name proposed for a new printer. */
export function defaultName(method, device, existing = []) {
  let base = method === "bluetooth" && device?.name ? device.name : method === "usb" ? "PT-P710BT (USB)" : method === "bridge" ? "PT-P710BT (bridge)" : "Label printer";
  const names = new Set(existing.map((p) => p.name));
  if (!names.has(base)) return base;
  for (let i = 2; i < 99; i++) if (!names.has(`${base} ${i}`)) return `${base} ${i}`;
  return base;
}

export const cleanName = (s) => String(s || "").replace(/\s+/g, " ").trim().slice(0, 60);
export function nameError(name, existing = [], selfId = "") {
  const n = cleanName(name);
  if (!n) return "Enter a name.";
  if (existing.some((p) => p.entry_id !== selfId && p.name.toLowerCase() === n.toLowerCase())) return "Another printer already uses this name.";
  return "";
}

// ---- scan list ------------------------------------------------------------------------------------
/** 0..4 bars from rssi dBm (null = unknown = 0). */
export function signalBars(rssi) {
  if (rssi == null || !Number.isFinite(Number(rssi))) return 0;
  const r = Number(rssi);
  return r >= -60 ? 4 : r >= -70 ? 3 : r >= -80 ? 2 : 1;
}
const nameOf = (d) => (d.name || "").toLowerCase();
export const looksLikePrinter = (d) => d.is_printer != null ? !!d.is_printer : /^(pt-|p-touch|brother)/i.test(d.name || "");
/** Printers first, then by signal (strongest first), unknown signal last, then by name. Unnamed unpaired devices are dropped. */
export function sortDevices(list) {
  const key = (d) => (d.rssi == null ? -999 : d.rssi);
  return [...list].filter((d) => d.name || d.paired).sort((a, b) =>
    (looksLikePrinter(b) - looksLikePrinter(a)) || (key(b) - key(a)) || nameOf(a).localeCompare(nameOf(b)) || String(a.address).localeCompare(String(b.address)));
}
/** -> {printers:[...], others:[...]} both sorted. */
export function groupDevices(list) {
  const s = sortDevices(list || []);
  return { printers: s.filter(looksLikePrinter), others: s.filter((d) => !looksLikePrinter(d)) };
}
/** What the row offers: "Select" (paired), "Pair" (not paired), or none when already added. */
export function deviceAction(d) {
  if (d.configured) return { kind: "added", label: "Already added", disabled: true };
  return d.paired ? { kind: "select", label: "Select", disabled: false } : { kind: "pair", label: "Pair", disabled: false };
}

// ---- Add-printer wizard state machine -------------------------------------------------------------
// Steps: how -> (bluetooth | usb | bridge) -> test -> name. Progress shows 4 dots.
export const WIZARD_DOTS = ["How", "Details", "Test", "Name"];
export function newWizard(opts = {}) {
  return { step: "how", method: "", device: null, serial: "", url: "", token: "", added: null, addStatus: "idle", addError: "",
    name: "", scan: { status: "idle", devices: [], error: "" }, pair: { status: "idle", address: "", reason: "", text: "" },
    existing: opts.existing || [], ...opts.extra };
}
export const stepIndex = (w) => ({ how: 0, bluetooth: 1, usb: 1, bridge: 1, test: 2, name: 3 }[w.step] ?? 0);
export function isPaired(w) { return !!w.device && !!w.device.paired; }
export function validUrl(u) { try { const x = new URL(String(u).trim()); return x.protocol === "http:" || x.protocol === "https:"; } catch { return false; } }

/** Can the primary button advance from the current step? */
export function canNext(w) {
  switch (w.step) {
    case "how": return !!w.method;
    case "bluetooth": return isPaired(w) && w.pair.status !== "pairing";
    case "usb": return true;
    case "bridge": return validUrl(w.url);
    case "test": return w.addStatus === "ok";
    case "name": return !nameError(w.name, w.existing || []);
    default: return false;
  }
}
/** Is the primary button enabled? Differs from canNext on the test step, where a failed add can be retried. */
export function canPrimary(w) {
  if (w.step === "test") return w.addStatus === "ok" || w.addStatus === "failed";
  return canNext(w);
}
/** Step after `next`. The test step adds the printer; the host runs that and sets addStatus. */
export function nextStep(w) {
  if (!canNext(w)) return w.step;
  if (w.step === "how") return w.method;
  if (w.step === "bluetooth" || w.step === "usb" || w.step === "bridge") return "test";
  if (w.step === "test") return "name";
  return w.step === "name" ? "done" : w.step;
}
export function prevStep(w) {
  if (w.step === "bluetooth" || w.step === "usb" || w.step === "bridge") return "how";
  if (w.step === "test") return w.added ? "test" : w.method;   // once added the printer exists: no way back to "details"
  if (w.step === "name") return "name";
  return "how";
}
export const canBack = (w) => w.step !== "how" && !(w.step === "test" && w.added) && w.step !== "name" && w.addStatus !== "adding" && w.pair.status !== "pairing";
/** Label of the primary button. */
export function primaryLabel(w) {
  if (w.step === "name") return "Done";
  if (w.step === "test") return w.addStatus === "failed" ? "Try again" : "Next";
  return "Next";
}
/** Payload for printers/add. */
export function addPayload(w) {
  if (w.method === "bluetooth") return { transport: "bluetooth", address: w.device.address, name: w.device.name || undefined };
  if (w.method === "usb") return w.serial.trim() ? { transport: "usb", serial: w.serial.trim() } : { transport: "usb" };
  const p = { transport: "bridge", url: w.url.trim() };
  if (w.token.trim()) p.token = w.token.trim();
  return p;
}
/** Wizard intro for Bluetooth when bluetooth/status says it cannot work. */
export function btBlocked(status) { return !!status && status.available === false; }
export function btBlockedText(status) { return status ? reasonText(status.reason, "") : ""; }
export { btUnavailable, reasonFromMessage };

// ---- print flow -----------------------------------------------------------------------------------
// idle -> waiting -> (done | failed); Cancel abandons the waiting UI (the backend call is not aborted).
export function newPrintFlow() { return { phase: "idle", id: 0, started: 0, reason: "", text: "", cancelled: new Set() }; }
export function startPrint(f, now = Date.now()) { return { ...f, phase: "waiting", id: f.id + 1, started: now, reason: "", text: "" }; }
/** Apply the outcome of print attempt `id`. Late results of a cancelled attempt never change the UI. */
export function finishPrint(f, id, outcome) {
  if (id !== f.id || f.phase !== "waiting") return { flow: f, late: f.cancelled.has(id) ? outcome : null };
  return { flow: outcome.ok ? { ...f, phase: "done" } : { ...f, phase: "failed", reason: outcome.reason || "error", text: outcome.text || "" }, late: null };
}
export function cancelPrint(f) {
  if (f.phase !== "waiting") return f;
  return { ...f, phase: "idle", cancelled: new Set([...f.cancelled, f.id]) };
}
export function dismissPrint(f) { return f.phase === "waiting" ? f : { ...f, phase: "idle", reason: "", text: "" }; }
export function waitingText(f, now = Date.now(), max = WAKE_SECONDS) {
  const s = Math.max(0, Math.round((now - f.started) / 1000));
  return s < 3 ? `Waiting for the printer… (up to ${max} s)` : `Waiting for the printer… ${Math.min(s, max)} of up to ${max} s`;
}
