// Printer drawer and Add-printer wizard (DOM). Logic lives in printer_logic.js / reasons.js.
import { h, icon, iconButton } from "./ui.js";
import { connectOutcome, failureSentence, reasonText, reasonFromError, canRetry, btUnavailable } from "./reasons.js";
import * as L from "./printer_logic.js";

const signalEl = (rssi, t) => {
  const n = L.signalBars(rssi);
  return h("span", { class: "sigbars", "data-bars": n, role: "img", "aria-label": n ? `${t("Signal")}: ${n} / 4` : t("Signal unknown") },
    [1, 2, 3, 4].map((i) => h("i", { class: i <= n ? "on" : "" })));
};

// ======================================================================================================
// Drawer
/**
 * createPrinterDrawer({ api, t, getPrinters, getActive, refresh, onSelect, onAdd, onClose, confirm })
 * getPrinters() -> normalized rows; refresh() -> Promise (re-fetches rows); onSelect(entryId); onAdd(); confirm(msg,{ok,danger}) -> Promise<bool>.
 */
export function createPrinterDrawer({ api, t, getPrinters, getActive, refresh, onSelect, onAdd, onClose, confirm }) {
  const ui = new Map();   // entry_id -> { busy, msg: {kind, text, retry}, renaming, nameDraft, nameErr }
  const st = (id) => { if (!ui.has(id)) ui.set(id, { busy: "", msg: null, renaming: false, nameDraft: "", nameErr: "" }); return ui.get(id); };
  const list = h("div", { class: "pd-list" });
  const empty = h("div", { class: "pd-empty" });
  const closeBtn = iconButton("mdi:close", t("Close"), () => onClose(), { class: "ibtn pd-close" });
  const refreshBtn = iconButton("mdi:refresh", t("Refresh"), async () => { await refresh(); render(); });
  const addBtn = h("button", { class: "btn primary pd-add", type: "button", onClick: () => onAdd() }, icon("mdi:plus"), t("Add printer"));
  const el = h("aside", { class: "pdrawer", role: "dialog", "aria-modal": "true", "aria-label": t("Printers") },
    h("div", { class: "pd-head" }, h("h2", {}, t("Printers")), refreshBtn, closeBtn),
    h("div", { class: "pd-body" }, list, empty),
    h("div", { class: "pd-foot" }, addBtn));
  let timer = null;

  const note = (id, msg) => {
    if (!msg) return null;
    const ic = msg.kind === "ok" ? "mdi:check-circle-outline" : msg.kind === "err" ? "mdi:alert-circle-outline" : null;
    return h("div", { class: `pd-note ${msg.kind}`, role: msg.kind === "err" ? "alert" : "status" },
      ic ? icon(ic) : h("span", { class: "spin", "aria-hidden": "true" }),
      h("span", { class: "grow" }, msg.text),
      msg.retry && h("button", { class: "btn small", type: "button", onClick: msg.retry }, icon("mdi:refresh"), t("Retry")));
  };

  function card(p, count) {
    const s = st(p.entry_id);
    const active = p.entry_id === getActive();
    const a = L.drawerActions(p, { active, count, busy: s.busy });
    const chip = L.chipState([p], p.entry_id);
    const conn = L.connectionDetail(p);
    const tl = L.tapeLine(p.tape);
    const nameRow = s.renaming
      ? h("form", { class: "pd-rename", onSubmit: (e) => { e.preventDefault(); doRename(p); } },
        h("input", { type: "text", value: s.nameDraft, maxLength: 60, "aria-label": t("Printer name"), autocomplete: "off", enterkeyhint: "done",
          onInput: (e) => { s.nameDraft = e.target.value; } }),
        h("button", { class: "btn small primary", type: "submit" }, t("Save")),
        h("button", { class: "btn small", type: "button", onClick: () => { s.renaming = false; s.nameErr = ""; render(); } }, t("Cancel")))
      : h("div", { class: "pd-name" }, h("span", { class: `dot ${chip.dot}`, "aria-hidden": "true" }), h("strong", {}, p.name),
        active && count > 1 && h("span", { class: "badge" }, t("Active")));
    return h("section", { class: "pd-card" + (active ? " active" : ""), "aria-label": p.name },
      nameRow,
      s.nameErr && h("div", { class: "pd-note err", role: "alert" }, icon("mdi:alert-circle-outline"), s.nameErr),
      h("div", { class: "pd-line muted" }, icon(conn.icon), conn.text),
      !(s.msg && s.msg.kind === "err" && s.msg.text === L.stateSentence(p)) && h("div", { class: `pd-state ${chip.dot}` }, t(L.stateSentence(p))),
      tl && h("div", { class: "pd-line" }, icon("mdi:label-outline"), tl),
      note(p.entry_id, s.msg),
      h("div", { class: "pd-acts" },
        a.use && h("button", { class: "btn small", type: "button", onClick: () => { onSelect(p.entry_id); render(); } }, icon("mdi:check"), t("Use this printer")),
        a.connect && h("button", { class: "btn small", type: "button", disabled: a.connectDisabled, onClick: () => doConnect(p) }, icon("mdi:bluetooth-connect"), t("Connect")),
        h("button", { class: "btn small", type: "button", disabled: a.testDisabled, onClick: () => doTest(p) }, icon("mdi:printer-check"), t("Test print")),
        h("span", { class: "grow" }),
        h("button", { class: "ibtn", type: "button", title: t("Rename"), "aria-label": `${t("Rename")} ${p.name}`, disabled: s.renaming, onClick: () => { s.renaming = true; s.nameDraft = p.name; s.nameErr = ""; render(); focusRename(); } }, icon("mdi:pencil-outline")),
        h("button", { class: "ibtn danger", type: "button", title: t("Remove"), "aria-label": `${t("Remove")} ${p.name}`, disabled: a.removeDisabled, onClick: () => doRemove(p) }, icon("mdi:delete-outline"))));
  }
  const focusRename = () => requestAnimationFrame(() => { const i = el.querySelector(".pd-rename input"); i?.focus(); i?.select(); });

  function render() {
    const ps = getPrinters();
    list.replaceChildren(...ps.map((p) => card(p, ps.length)));
    empty.replaceChildren(...(ps.length ? [] : [icon("mdi:printer-off-outline"), h("p", {}, t("No printer set up yet.")),
      h("p", { class: "muted" }, t("Add your PT-P710BT over Bluetooth, USB or the network bridge."))]));
  }

  async function doConnect(p) {
    const s = st(p.entry_id); s.busy = "connect"; s.msg = { kind: "info", text: t("Trying to reach the printer…") }; render();
    try {
      const o = connectOutcome(await api.btConnect(p.entry_id));
      s.msg = { kind: o.ok ? "ok" : "err", text: t(o.text), retry: !o.ok && o.retry ? () => doConnect(p) : null };
    } catch (e) { const f = failureSentence(e); s.msg = { kind: "err", text: f.text, retry: canRetry(f.reason) ? () => doConnect(p) : null }; }
    s.busy = ""; await safeRefresh(); render();
  }
  async function doTest(p) {
    const s = st(p.entry_id); s.busy = "test"; s.msg = { kind: "info", text: t("Sending a test label… (a sleeping printer can take up to 20 s)") }; render();
    try { await api.testPrint(p.entry_id); s.msg = { kind: "ok", text: t("Test label sent. Check the printer.") }; }
    catch (e) { const f = failureSentence(e); s.msg = { kind: "err", text: f.text, retry: () => doTest(p) }; }
    s.busy = ""; await safeRefresh(); render();
  }
  async function doRename(p) {
    const s = st(p.entry_id), name = L.cleanName(s.nameDraft);
    const err = L.nameError(name, getPrinters(), p.entry_id);
    if (err) { s.nameErr = t(err); render(); focusRename(); return; }
    if (name !== p.name) {
      try { await api.renamePrinter(p.entry_id, name); } catch (e) { s.nameErr = e.message || String(e); render(); return; }
    }
    s.renaming = false; s.nameErr = ""; await safeRefresh(); render();
  }
  async function doRemove(p) {
    if (!(await confirm(`${t("Remove")} “${p.name}”? ${t("Home Assistant will forget this printer. You can add it again later.")}`, { ok: t("Remove"), danger: true }))) return;
    const s = st(p.entry_id); s.busy = "remove"; render();
    try { await api.removePrinter(p.entry_id); ui.delete(p.entry_id); }
    catch (e) { s.busy = ""; s.msg = { kind: "err", text: e.message || String(e) }; }
    await safeRefresh(); render();
  }
  async function safeRefresh() { try { await refresh(); } catch { /* shown elsewhere */ } }

  return {
    el, render,
    open() {
      render(); safeRefresh().then(render);
      clearInterval(timer); timer = setInterval(() => { if (!el.isConnected || el.offsetParent === null) return; const busy = [...ui.values()].some((s) => s.busy || s.renaming); if (!busy) safeRefresh().then(render); }, 10000);
      requestAnimationFrame(() => (el.querySelector(".pd-card button:not(:disabled)") || addBtn).focus({ preventScroll: true }));
    },
    close() { clearInterval(timer); timer = null; },
    focusAdd() { addBtn.focus(); },
  };
}

// ======================================================================================================
// Wizard
/**
 * createWizard({ api, t, getPrinters, refresh, onClose, onDone })
 * onDone(entryId) is called after the last step; onClose() when cancelled.
 */
export function createWizard({ api, t, getPrinters, refresh, onClose, onDone, getBtStatus = null }) {
  let w = L.newWizard();
  let gen = 0;           // bump to ignore results of abandoned async work
  let btStatus = null;   // {available, reason}
  const title = h("h2", { tabindex: -1 }, t("Add printer"));
  const dots = h("ol", { class: "wz-dots", "aria-label": t("Progress") });
  const body = h("div", { class: "wz-body", "aria-live": "polite" });
  const back = h("button", { class: "btn", type: "button", onClick: () => goBack() }, icon("mdi:chevron-left"), t("Back"));
  const next = h("button", { class: "btn primary", type: "button", onClick: () => goNext() }, t("Next"));
  const cancel = h("button", { class: "btn", type: "button", onClick: () => onClose() }, t("Cancel"));
  const closeBtn = iconButton("mdi:close", t("Close"), () => onClose(), { class: "ibtn wz-close" });
  const el = h("div", { class: "wizard", role: "dialog", "aria-modal": "true", "aria-label": t("Add printer") },
    h("div", { class: "wz-head" }, title, closeBtn), dots, body,
    h("div", { class: "wz-foot" }, cancel, h("span", { class: "grow" }), back, next));

  const setStep = (s, focus = true) => { w.step = s; render(); if (focus) requestAnimationFrame(() => title.focus({ preventScroll: true })); };

  function open() {
    gen++;
    w = L.newWizard({ existing: getPrinters() });
    btStatus = null;
    render();
    const g = gen;
    api.btStatus().then((s) => { if (g === gen) { btStatus = s; render(); } }).catch(() => { if (g === gen) { btStatus = { available: true, reason: "ok" }; render(); } });
    requestAnimationFrame(() => (body.querySelector(".wz-card") || title).focus({ preventScroll: true }));
  }
  function abort() { gen++; }

  function chooseMethod(m) { w.method = m; render(); }

  function goBack() { if (L.canBack(w)) setStep(L.prevStep(w)); }
  async function goNext() {
    if (!L.canPrimary(w)) return;
    if (w.step === "test" && w.addStatus === "failed") { runAdd(); return; }
    const to = L.nextStep(w);
    if (to === "done") return finish();
    setStep(to);
    if (to === "test") runAdd();
    if (to === "name") w.name = L.defaultName(w.method, w.device, getPrinters().filter((p) => p.entry_id !== w.added?.entry_id)), render();
  }

  async function runAdd() {
    const g = gen;
    if (w.added) { w.addStatus = "ok"; render(); return; }
    w.addStatus = "adding"; w.addError = ""; render();
    try {
      const res = await api.addPrinter(L.addPayload(w));
      if (g !== gen) return;
      w.added = res; w.addStatus = "ok";
      await refresh().catch(() => {});
    } catch (e) {
      if (g !== gen) return;
      w.addStatus = "failed";
      w.addError = e?.code === "already_configured" ? t("This printer is already added.") : failureSentence(e).text;
      w.addReason = e?.code === "already_configured" ? "ok" : reasonFromError(e);
    }
    render();
  }

  async function finish() {
    const g = gen, id = w.added?.entry_id;
    const name = L.cleanName(w.name);
    w.nameErr = "";
    if (id && name && name !== (getPrinters().find((p) => p.entry_id === id)?.name)) {
      w.addStatus = "renaming"; render();
      try { await api.renamePrinter(id, name); } catch (e) { if (g !== gen) return; w.addStatus = "ok"; w.nameErr = e.message || String(e); render(); return; }
    }
    if (g !== gen) return;
    await refresh().catch(() => {});
    onDone(id);
  }

  async function scan() {
    const g = gen;
    w.scan = { status: "scanning", devices: w.scan.devices, error: "" }; w.pair = { status: "idle", address: "", reason: "", text: "" }; render();
    try {
      const devices = await api.btScan(8);
      if (g !== gen) return;
      w.scan = { status: "done", devices, error: "" };
      // keep the selection if the device is still there; auto-select a lone printer that is already paired
      if (w.device) w.device = devices.find((d) => d.address === w.device.address) || null;
      const pr = L.groupDevices(devices).printers.filter((d) => !d.configured);
      if (!w.device && pr.length === 1 && pr[0].paired) w.device = pr[0];
    } catch (e) {
      if (g !== gen) return;
      const f = failureSentence(e);
      w.scan = { status: "error", devices: [], error: f.text, reason: f.reason };
    }
    render();
  }
  async function pair(d) {
    const g = gen;
    w.pair = { status: "pairing", address: d.address, reason: "", text: "" }; render();
    try {
      const dev = await api.btPair(d.address);
      if (g !== gen) return;
      const merged = { ...d, ...dev, paired: true, configured: d.configured };
      w.scan.devices = w.scan.devices.map((x) => (x.address === d.address ? merged : x));
      w.device = merged; w.pair = { status: "ok", address: d.address, reason: "", text: "" };
    } catch (e) {
      if (g !== gen) return;
      const f = failureSentence(e);
      w.pair = { status: "failed", address: d.address, reason: f.reason, text: f.text };
    }
    render();
  }

  // ---- step views ----
  function viewHow() {
    const card = (m, ic, name, desc, extra) => h("button", { class: "wz-card" + (w.method === m ? " sel" : ""), type: "button", role: "radio", "aria-checked": w.method === m ? "true" : "false",
      onClick: () => chooseMethod(m), onDblclick: () => { chooseMethod(m); goNext(); } },
      icon(ic), h("span", { class: "wz-card-t" }, h("strong", {}, name, extra && h("span", { class: "tag" }, extra)), h("span", { class: "muted" }, desc)),
      h("span", { class: "wz-radio", "aria-hidden": "true" }));
    return [h("p", { class: "wz-lead" }, t("How is your printer connected to Home Assistant?")),
      h("div", { class: "wz-cards", role: "radiogroup", "aria-label": t("Connection") },
        card("bluetooth", "mdi:bluetooth", t("Bluetooth"), t("Pair with the printer's radio. The usual choice for the PT-P710BT.")),
        card("usb", "mdi:usb", t("USB"), t("A USB cable between the printer and the Home Assistant host.")),
        card("bridge", "mdi:lan-connect", t("Network bridge"), t("Another computer or ESP that forwards to the printer."), t("Advanced")))];
  }

  function deviceRow(d) {
    const act = L.deviceAction(d), pairing = w.pair.status === "pairing" && w.pair.address === d.address;
    const sel = w.device?.address === d.address;
    const failed = w.pair.status === "failed" && w.pair.address === d.address;
    const btn = act.kind === "added" ? h("span", { class: "muted small" }, t("Already added"))
      : act.kind === "select" ? h("button", { class: "btn small" + (sel ? " primary" : ""), type: "button", "aria-pressed": sel ? "true" : "false", disabled: w.pair.status === "pairing",
        onClick: () => { w.device = d; render(); } }, sel ? [icon("mdi:check"), t("Selected")] : t("Select"))
        : h("button", { class: "btn small", type: "button", disabled: pairing || w.pair.status === "pairing", onClick: () => pair(d) }, icon("mdi:link-variant"), t("Pair"));
    return h("li", { class: "wz-dev" + (L.looksLikePrinter(d) ? " printer" : "") + (sel ? " sel" : "") },
      h("div", { class: "wz-dev-main" },
        icon(L.looksLikePrinter(d) ? "mdi:printer" : /phone|pixel|iphone|galaxy/i.test(d.name || "") ? "mdi:cellphone" : /wh-|buds|airpods|head|jbl|speaker/i.test(d.name || "") ? "mdi:headphones" : "mdi:bluetooth"),
        h("span", { class: "wz-dev-t" }, h("strong", {}, d.name || d.address), h("span", { class: "muted small" }, d.paired ? t("Paired") : t("Not paired"), d.connected ? ` · ${t("connected")}` : "")),
        signalEl(d.rssi, t), btn),
      pairing && h("div", { class: "pd-note info", role: "status" }, h("span", { class: "spin" }), t("Pairing… this takes a few seconds. Keep the printer close.")),
      failed && h("div", { class: "pd-note err", role: "alert" }, icon("mdi:alert-circle-outline"), h("span", { class: "grow" }, w.pair.text),
        canRetry(w.pair.reason) && h("button", { class: "btn small", type: "button", onClick: () => pair(d) }, icon("mdi:refresh"), t("Retry"))));
  }

  function viewBluetooth() {
    if (L.btBlocked(btStatus)) {
      return [h("div", { class: "pd-note err big", role: "alert" }, icon("mdi:bluetooth-off"), h("span", { class: "grow" }, t(L.btBlockedText(btStatus)))),
        btStatus.reason === "bluetooth_off" ? h("p", { class: "muted" }, t("Switch Bluetooth on, then reopen this wizard. Or use another connection:")) : h("p", { class: "muted" }, t("Choose another connection:")),
        h("div", { class: "row" },
          h("button", { class: "btn", type: "button", onClick: () => { w.method = "usb"; setStep("usb"); } }, icon("mdi:usb"), t("Use USB")),
          h("button", { class: "btn", type: "button", onClick: () => { w.method = "bridge"; setStep("bridge"); } }, icon("mdi:lan-connect"), t("Use network bridge")))];
    }
    const g = L.groupDevices(w.scan.devices);
    const scanning = w.scan.status === "scanning";
    const others = g.others;
    return [
      h("ul", { class: "wz-check" },
        ["Switch the printer on.", "Disconnect phones and tablets from it.", "Keep it within a metre of the Home Assistant host."].map((x) => h("li", {}, icon("mdi:check-circle-outline"), t(x)))),
      h("div", { class: "row wz-scanrow" },
        h("button", { class: "btn" + (w.scan.status === "idle" ? " primary" : ""), type: "button", disabled: scanning || w.pair.status === "pairing", onClick: () => scan() },
          icon("mdi:magnify"), scanning ? t("Scanning…") : w.scan.status === "idle" ? t("Scan") : t("Scan again")),
        scanning && h("span", { class: "muted", role: "status" }, t("Looking for devices (about 8 s)…"))),
      scanning && h("div", { class: "progress", role: "progressbar", "aria-label": t("Scanning") }, h("i")),
      w.scan.status === "error" && h("div", { class: "pd-note err", role: "alert" }, icon("mdi:alert-circle-outline"), w.scan.error),
      w.scan.status === "done" && !g.printers.length && h("div", { class: "pd-note info", role: "status" }, icon("mdi:information-outline"), t("No printer found. Check the list above, then scan again.")),
      g.printers.length > 0 && h("ul", { class: "wz-devs", "aria-label": t("Printers found") }, g.printers.map(deviceRow)),
      others.length > 0 && h("details", { class: "wz-others", open: !g.printers.length && w.scan.status === "done" },
        h("summary", {}, `${t("Other devices")} (${others.length})`), h("ul", { class: "wz-devs" }, others.map(deviceRow))),
    ];
  }

  function viewUsb() {
    return [h("p", { class: "wz-lead" }, t("Connect the printer to the Home Assistant host with a USB cable and switch it on.")),
      h("p", { class: "muted" }, t("If more than one P-touch printer is plugged in, enter the serial number of this one. Otherwise leave it empty.")),
      h("div", { class: "field full" }, h("label", { for: "wz-serial" }, t("Serial number (optional)")),
        h("input", { id: "wz-serial", type: "text", value: w.serial, autocomplete: "off", autocapitalize: "off", spellcheck: "false", enterkeyhint: "next", onInput: (e) => { w.serial = e.target.value; }, onKeydown: enterNext }))];
  }
  function viewBridge() {
    const bad = w.url && !L.validUrl(w.url);
    return [h("p", { class: "wz-lead" }, t("Enter the address of the network bridge that forwards to your printer.")),
      h("div", { class: "field full" }, h("label", { for: "wz-url" }, t("Bridge URL")),
        h("input", { id: "wz-url", type: "text", inputmode: "url", value: w.url, placeholder: "http://192.168.1.20:8080", autocomplete: "off", autocapitalize: "off", spellcheck: "false", "aria-invalid": bad ? "true" : "false",
          onInput: (e) => { w.url = e.target.value; render(); }, onKeydown: enterNext }),
        bad && h("span", { class: "err-t small" }, t("Start with http:// or https://"))),
      h("div", { class: "field full" }, h("label", { for: "wz-token" }, t("Access token (optional)")),
        h("input", { id: "wz-token", type: "password", value: w.token, autocomplete: "off", onInput: (e) => { w.token = e.target.value; }, onKeydown: enterNext }))];
  }
  const enterNext = (e) => { if (e.key === "Enter") { e.preventDefault(); goNext(); } };

  function viewTest() {
    if (w.addStatus === "adding") return [h("div", { class: "wz-busy", role: "status" }, h("span", { class: "spin big" }), h("p", {}, t("Connecting to the printer…")), h("p", { class: "muted" }, t("A sleeping printer can take up to 20 seconds.")))];
    if (w.addStatus === "failed") return [h("div", { class: "pd-note err big", role: "alert" }, icon("mdi:alert-circle-outline"), h("span", { class: "grow" }, w.addError)),
      h("p", { class: "muted" }, t("Fix the problem and choose Try again, or go back to change the connection."))];
    const p = getPrinters().find((x) => x.entry_id === w.added?.entry_id);
    const tl = p ? L.tapeLine(p.tape) : "";
    const testBtn = h("button", { class: "btn", type: "button", disabled: w.testing, onClick: async () => {
      const g = gen; w.testing = true; w.testMsg = null; render();
      try { await api.testPrint(w.added.entry_id); if (g === gen) w.testMsg = { kind: "ok", text: t("Test label sent. Check the printer.") }; }
      catch (e) { if (g === gen) w.testMsg = { kind: "err", text: failureSentence(e).text }; }
      if (g === gen) { w.testing = false; render(); }
    } }, icon("mdi:printer-check"), w.testing ? t("Sending…") : t("Print a test label"));
    return [h("div", { class: "pd-note ok big", role: "status" }, icon("mdi:check-circle-outline"),
      h("span", { class: "grow" }, tl ? `${t("Connected")}: ${tl}` : p && !p.tape ? t("Connected. No tape was detected: insert a tape cassette.") : t("Connected."))),
      h("div", { class: "row" }, testBtn),
      w.testMsg && h("div", { class: `pd-note ${w.testMsg.kind}`, role: w.testMsg.kind === "err" ? "alert" : "status" }, icon(w.testMsg.kind === "ok" ? "mdi:check-circle-outline" : "mdi:alert-circle-outline"), w.testMsg.text)];
  }

  function viewName() {
    const err = w.name ? L.nameError(w.name, getPrinters(), w.added?.entry_id) : "";
    return [h("p", { class: "wz-lead" }, t("Give the printer a name.")),
      h("div", { class: "field full" }, h("label", { for: "wz-name" }, t("Printer name")),
        h("input", { id: "wz-name", type: "text", value: w.name, maxLength: 60, autocomplete: "off", enterkeyhint: "done", "aria-invalid": err ? "true" : "false",
          onInput: (e) => { w.name = e.target.value; render(); }, onKeydown: enterNext }),
        err && h("span", { class: "err-t small" }, t(err))),
      w.nameErr && h("div", { class: "pd-note err", role: "alert" }, icon("mdi:alert-circle-outline"), w.nameErr),
      h("p", { class: "muted" }, t("The new printer will be selected for printing."))];
  }

  function render() {
    w.existing = getPrinters();
    const labels = L.WIZARD_DOTS, idx = L.stepIndex(w);
    dots.replaceChildren(...labels.map((x, i) => h("li", { class: i < idx ? "done" : i === idx ? "cur" : "", "aria-current": i === idx ? "step" : false }, h("i"), h("span", {}, t(x)))));
    const views = { how: viewHow, bluetooth: viewBluetooth, usb: viewUsb, bridge: viewBridge, test: viewTest, name: viewName };
    const keep = { id: body.querySelector("input:focus")?.id, scroll: body.scrollTop };
    body.replaceChildren(...(views[w.step] || viewHow)().filter(Boolean));
    body.scrollTop = keep.scroll;
    if (keep.id) { const i = body.querySelector("#" + keep.id); if (i) { i.focus(); try { i.setSelectionRange(i.value.length, i.value.length); } catch { /* ignore */ } } }
    title.textContent = { how: t("Add printer"), bluetooth: t("Bluetooth printer"), usb: t("USB printer"), bridge: t("Network bridge"), test: t("Testing the connection"), name: t("Name your printer") }[w.step];
    el.classList.toggle("tall", w.step === "bluetooth");
    back.hidden = w.step === "how"; back.disabled = !L.canBack(w);
    next.textContent = t(L.primaryLabel(w)); next.disabled = !L.canPrimary(w) || w.addStatus === "renaming";
    next.hidden = w.step === "bluetooth" && L.btBlocked(btStatus);
    cancel.hidden = w.step === "name";
  }

  return { el, open, abort, render, get state() { return w; } };
}
