// Google font picker and MDI icon picker widgets.
import { h, icon, debounce, loadPreviewFonts } from "./ui.js";

const CATEGORIES = ["sans-serif", "serif", "display", "handwriting", "monospace"];
export const ALL_WEIGHTS = [100, 200, 300, 400, 500, 600, 700, 800, 900];

/** Cache of font catalog entries seen so far, keyed by family. */
export const fontInfo = new Map();

export function nearestWeight(weights, w) {
  if (!weights?.length) return w;
  return weights.reduce((b, x) => (Math.abs(x - w) < Math.abs(b - w) ? x : b), weights[0]);
}

export function createFontPicker({ api, getFont, onPick, t = (s) => s }) {
  let open = false, seq = 0;
  const label = h("span", { class: "fp-label" });
  const toggle = h("button", { type: "button", class: "select-like", "aria-haspopup": "listbox", "aria-expanded": "false", onClick: () => setOpen(!open) },
    label, icon("mdi:chevron-down"));
  const search = h("input", { type: "search", placeholder: t("Search fonts"), "aria-label": t("Search fonts"), onInput: debounce(() => load(), 220) });
  const cat = h("select", { "aria-label": t("Category"), onChange: () => load() },
    h("option", { value: "" }, t("All categories")), CATEGORIES.map((c) => h("option", { value: c }, c)));
  const list = h("div", { class: "fp-list", role: "listbox", "aria-label": t("Fonts") });
  const status = h("div", { class: "hint" });
  const panel = h("div", { class: "fp-panel", hidden: true }, h("div", { class: "row" }, search, cat), list, status);
  const el = h("div", { class: "picker" }, toggle, panel);

  const io = "IntersectionObserver" in window ? new IntersectionObserver((entries) => {
    const fams = entries.filter((e) => e.isIntersecting).map((e) => e.target.dataset.family).filter(Boolean);
    if (fams.length) loadPreviewFonts(fams);
  }, { root: list }) : null;

  function row(family, entry) {
    const cur = getFont().family === family;
    const b = h("button", { type: "button", role: "option", "aria-selected": String(cur), class: "fp-row" + (cur ? " sel" : ""), "data-family": family,
      onClick: () => { setOpen(false); onPick(family ? { family, entry } : { family: "" }); } },
      h("span", { class: "fp-name", style: family ? { fontFamily: `"${family}", var(--paper-font-body1_-_font-family, sans-serif)` } : {} }, family || t("Default (built-in)")),
      entry?.category ? h("span", { class: "fp-cat" }, entry.category) : null);
    if (family && io) io.observe(b);
    return b;
  }

  async function load() {
    const my = ++seq;
    status.textContent = t("Loading...");
    try {
      const fonts = await api.searchFonts(search.value.trim(), cat.value || null, 40);
      if (my !== seq) return;
      for (const f of fonts) fontInfo.set(f.family, f);
      list.replaceChildren(...(search.value.trim() ? [] : [row("", null)]), ...fonts.map((f) => row(f.family, f)));
      status.textContent = fonts.length ? "" : t("No fonts found");
    } catch (e) { if (my === seq) status.textContent = e.message || String(e); }
  }

  function setOpen(v) {
    open = v; panel.hidden = !v; toggle.setAttribute("aria-expanded", String(v));
    if (v) { load(); search.focus(); }
  }

  async function resolveInfo(family) {
    if (!family || fontInfo.has(family)) return;
    try {
      const r = await api.searchFonts(family, null, 5);
      const hit = r.find((f) => f.family.toLowerCase() === family.toLowerCase());
      if (hit) { fontInfo.set(hit.family, hit); sync(); }
    } catch { /* offline: leave unknown */ }
  }

  function sync() {
    const { family } = getFont();
    label.textContent = family || t("Default (built-in)");
    label.style.fontFamily = family ? `"${family}", sans-serif` : "";
    if (family) loadPreviewFonts([family]);
    resolveInfo(family);
  }
  sync();
  return { el, sync, close: () => setOpen(false) };
}

export function createIconPicker({ api, getIcon, onPick, t = (s) => s }) {
  let open = false, seq = 0;
  const current = h("span", { class: "ip-current" });
  const toggle = h("button", { type: "button", class: "select-like", "aria-expanded": "false", onClick: () => setOpen(!open) }, current, icon("mdi:chevron-down"));
  const search = h("input", { type: "search", placeholder: t("Search icons"), "aria-label": t("Search icons"), onInput: debounce(() => load(), 220) });
  const grid = h("div", { class: "ip-grid", role: "listbox", "aria-label": t("Icons") });
  const status = h("div", { class: "hint" });
  const panel = h("div", { class: "fp-panel", hidden: true }, search, grid, status);
  const el = h("div", { class: "picker" }, toggle, panel);

  async function load() {
    const my = ++seq;
    status.textContent = t("Loading...");
    try {
      const icons = await api.searchIcons(search.value.trim(), 120);
      if (my !== seq) return;
      grid.replaceChildren(...icons.map((n) => h("button", { type: "button", role: "option", class: "ip-cell" + (n === getIcon() ? " sel" : ""), title: n, "aria-label": n,
        onClick: () => { setOpen(false); onPick(n); } }, icon(n))));
      status.textContent = icons.length ? "" : t("No icons found");
    } catch (e) { if (my === seq) status.textContent = e.message || String(e); }
  }
  function setOpen(v) {
    open = v; panel.hidden = !v; toggle.setAttribute("aria-expanded", String(v));
    if (v) { load(); search.focus(); }
  }
  function sync() { current.replaceChildren(icon(getIcon() || "mdi:help"), h("span", {}, getIcon() || "")); }
  sync();
  return { el, sync, close: () => setOpen(false) };
}
