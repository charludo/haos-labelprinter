// Thin wrapper over hass.callWS plus the debounced, sequence-numbered previewer.
export class Api {
  constructor(hass) { this.hass = hass; this._ensured = new Set(); }
  call(type, data = {}) { return this.hass.callWS({ type: `brother_ptouch/${type}`, ...data }); }
  printers() { return this.call("printers").then((r) => r.printers); }
  listDesigns() { return this.call("designs/list").then((r) => r.designs); }
  getDesign(id) { return this.call("designs/get", { design_id: id }).then((r) => r.design); }
  saveDesign(design) { return this.call("designs/save", { design }).then((r) => r.design); }
  deleteDesign(id) { return this.call("designs/delete", { design_id: id }); }
  preview(design, { tape_mm, entry_id, variables } = {}) {
    const msg = { design };
    if (tape_mm != null) msg.tape_mm = tape_mm;
    if (entry_id) msg.entry_id = entry_id;
    if (variables && Object.keys(variables).length) msg.variables = variables;
    return this.call("preview", msg);
  }
  print({ design, id, entry_id, variables, copies }) {
    const msg = {};
    if (id) msg.design_id = id; else msg.design = design;
    if (entry_id) msg.entry_id = entry_id;
    if (variables && Object.keys(variables).length) msg.variables = variables;
    if (copies && copies > 1) msg.copies = copies;
    return this.call("print", msg);
  }
  searchFonts(query = "", category = null, limit = 40) {
    const msg = { query, limit }; if (category) msg.category = category;
    return this.call("fonts/search", msg).then((r) => r.fonts);
  }
  /** Download a font on the server once per (family, weight, italic). */
  async ensureFont(family, weight = 400, italic = false) {
    if (!family) return;
    const key = `${family}|${weight}|${italic}`;
    if (this._ensured.has(key)) return;
    await this.call("fonts/ensure", { family, weights: [weight], italic });
    this._ensured.add(key);
  }
  searchIcons(query = "", limit = 120) { return this.call("icons/search", { query, limit }).then((r) => r.icons); }
}

/**
 * Debounced preview requests. Only the newest response is delivered; stale
 * ones are dropped by sequence number. `maxWait` keeps previews coming during
 * long drags.
 */
export class Previewer {
  constructor(run, deliver, { delay = 150, maxWait = 450 } = {}) {
    this.run = run; this.deliver = deliver; this.delay = delay; this.maxWait = maxWait;
    this.seq = 0; this._timer = null; this._firstPending = 0; this.inflight = 0;
  }
  request() {
    const now = Date.now();
    if (!this._firstPending) this._firstPending = now;
    clearTimeout(this._timer);
    const wait = Math.min(this.delay, Math.max(0, this._firstPending + this.maxWait - now));
    this._timer = setTimeout(() => this.fire(), wait);
  }
  async fire() {
    this._timer = null; this._firstPending = 0;
    const seq = ++this.seq;
    this.inflight++; this.deliver({ loading: true });
    try {
      const res = await this.run();
      if (seq === this.seq) this.deliver({ result: res });
    } catch (err) {
      if (seq === this.seq) this.deliver({ error: err });
    } finally {
      this.inflight--;
      if (seq === this.seq) this.deliver({ loading: false });
    }
  }
  cancel() { clearTimeout(this._timer); this._timer = null; this._firstPending = 0; this.seq++; }
}
