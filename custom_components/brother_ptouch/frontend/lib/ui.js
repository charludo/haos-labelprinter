// Small DOM helpers shared by components.
const PROPS = new Set(["value", "checked", "disabled", "selected", "textContent", "innerHTML", "hidden", "tabIndex", "type", "min", "max", "step", "placeholder", "rows", "enterKeyHint"]);

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k === "style") {
      if (typeof v === "string") el.style.cssText = v;
      else for (const [sk, sv] of Object.entries(v)) { if (sk.startsWith("--")) el.style.setProperty(sk, String(sv)); else el.style[sk] = sv; }
    }
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (PROPS.has(k)) el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return el;
}

/** Icon via <ha-icon>; plain text fallback when it is not registered. */
export function icon(name, cls = "") {
  if (customElements.get("ha-icon")) return h("ha-icon", { icon: name, class: "ico " + cls });
  return h("span", { class: "ico fallback " + cls, textContent: name.split(":")[1]?.slice(0, 2) || "" });
}

export function iconButton(name, label, onClick, props = {}) {
  return h("button", { class: "ibtn", type: "button", title: label, "aria-label": label, onClick, ...props }, icon(name));
}

export function debounce(fn, ms) {
  let t;
  const d = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  d.cancel = () => clearTimeout(t);
  return d;
}

export const storage = {
  get(k, d) { try { const v = localStorage.getItem("brother_ptouch." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("brother_ptouch." + k, JSON.stringify(v)); } catch { /* ignore */ } },
};

let _loadedFamilies = new Set();
let _queue = new Set();
let _timer = null;
/** Lazily load Google Fonts CSS (browser preview only) for visible picker rows. */
export function loadPreviewFonts(families) {
  for (const f of families) if (f && !_loadedFamilies.has(f)) { _loadedFamilies.add(f); _queue.add(f); }
  if (_timer || !_queue.size) return;
  _timer = setTimeout(() => {
    _timer = null;
    const list = [..._queue]; _queue = new Set();
    for (let i = 0; i < list.length; i += 12) {
      const q = list.slice(i, i + 12).map((f) => "family=" + encodeURIComponent(f).replace(/%20/g, "+")).join("&");
      const link = document.createElement("link");
      link.rel = "stylesheet"; link.href = `https://fonts.googleapis.com/css2?${q}&display=swap`;
      document.head.append(link);
    }
  }, 80);
}
