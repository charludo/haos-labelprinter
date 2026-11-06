// "New from template" gallery: DOM component. Logic lives in templates.js.
import { h, icon, iconButton } from "./ui.js";
import { arrangeByTape, categoryChips, filterTemplates, tapeCompatible, tapesText, ThumbCache } from "./templates.js";
import { tapeLabel } from "./geometry.js";

/**
 * createGallery({ api, t, getTape, onPick, onClose })
 * api.templatesList() -> {templates, categories}; api.buildTemplate(id, tape) -> {design}; api.preview(design, {tape_mm}).
 * onPick(template) is called when a card is chosen. Returns { el, open(), focus() }.
 */
export function createGallery({ api, t, getTape, onPick, onClose }) {
  const state = { list: null, categories: [], category: "", query: "", tape: 12, error: "", loading: false, cards: new Map() };
  const cache = new ThumbCache(async (tape, id) => {
    const { design } = await api.buildTemplate(id, tape);
    const r = await api.preview(design, { tape_mm: tape });
    return { src: `data:image/png;base64,${r.png}`, w: r.width, h: r.height };
  }, { concurrency: 3 });

  const tapeNote = h("span", { class: "gal-tape" });
  const search = h("input", { type: "search", class: "gal-search", placeholder: t("Search templates"), "aria-label": t("Search templates"), enterkeyhint: "search", autocomplete: "off",
    onInput: () => { state.query = search.value; render(); } });
  const chips = h("div", { class: "gal-chips", role: "toolbar", "aria-label": t("Categories") });
  const grid = h("div", { class: "gal-grid", role: "list" });
  const status = h("div", { class: "gal-status", role: "status" });
  const banner = h("div", { class: "gal-banner", role: "alert", hidden: true });
  const scroller = h("div", { class: "gal-scroll" }, banner, grid, status);
  const closeBtn = iconButton("mdi:close", t("Close"), () => onClose(), { class: "ibtn gal-close" });
  const el = h("div", { class: "gallery", role: "dialog", "aria-modal": "true", "aria-label": t("New from template") },
    h("div", { class: "gal-head" }, h("h2", {}, t("New from template")), tapeNote, closeBtn),
    h("div", { class: "gal-tools" }, search, chips), scroller);

  let io = null;
  const observe = () => {
    io?.disconnect();
    if (typeof IntersectionObserver === "undefined") return;
    io = new IntersectionObserver((entries) => {
      for (const en of entries) {
        const c = en.target._card; if (!c) continue;
        c.visible = en.isIntersecting;
        if (c.visible) loadThumb(c);
      }
    }, { root: scroller, rootMargin: "120px 0px" });
  };

  async function loadThumb(c) {
    if (c.loaded || c.loading || !c.compat) return;
    const tape = state.tape, id = c.tpl.id;
    const hit = cache.peek(tape, id);
    if (hit) { showThumb(c, hit); return; }
    c.loading = true; c.thumb.classList.add("loading");
    try {
      const v = await cache.get(tape, id, () => !c.visible || tape !== state.tape || !c.node.isConnected);
      if (v && tape === state.tape) showThumb(c, v);
    } catch (e) {
      if (tape === state.tape) { c.thumb.classList.remove("loading"); c.thumb.classList.add("failed"); c.thumb.replaceChildren(h("span", { class: "gal-fail", title: e?.message || "" }, t("Preview unavailable"))); c.loaded = true; }
    } finally { c.loading = false; if (!c.loaded) c.thumb.classList.remove("loading"); }
    if (!c.loaded && c.visible && tape === state.tape && c.node.isConnected && !c.thumb.classList.contains("failed")) setTimeout(() => loadThumb(c), 0);
  }
  function showThumb(c, v) {
    c.loaded = true; c.thumb.classList.remove("loading");
    c.thumb.replaceChildren(h("img", { src: v.src, alt: "", draggable: false, width: v.w, height: v.h }));
  }

  function makeCard(tpl) {
    const compat = tapeCompatible(tpl, state.tape);
    const thumb = h("div", { class: "gal-thumb" + (compat ? "" : " off") },
      compat ? null : h("span", { class: "gal-need" }, icon("mdi:ruler"), `${t("Needs")} ${tapesText(tpl.tapes)}`));
    const node = h("button", { class: "gal-card" + (compat ? "" : " incompatible"), type: "button", role: "listitem", disabled: !compat,
      title: compat ? tpl.description : `${tpl.description}\n${t("Needs")} ${tapesText(tpl.tapes)} ${t("tape; the current tape is")} ${tapeLabel(state.tape)}`,
      onClick: () => onPick(tpl) },
    thumb,
    h("span", { class: "gal-name" }, tpl.name),
    h("span", { class: "gal-desc" }, tpl.description),
    compat ? null : h("span", { class: "gal-note" }, `${t("Needs")} ${tapesText(tpl.tapes)} ${t("tape")}`));
    const c = { tpl, node, thumb, compat, visible: !io, loaded: false, loading: false };
    node._card = c;
    return c;
  }

  let chipSig = "";
  function renderChips() {
    const cats = categoryChips(state.categories, state.list);
    const sig = cats.join("\u0001");
    if (sig !== chipSig) {   // rebuild only when the set changes, so a focused chip keeps focus
      chipSig = sig;
      const chip = (value, label) => h("button", { type: "button", class: "chip", "data-cat": value,
        onClick: () => { state.category = value; render(); } }, label);
      chips.replaceChildren(chip("", t("All")), ...cats.map((c) => chip(c, c)));
    }
    for (const b of chips.children) { const on = b.dataset.cat === state.category; b.classList.toggle("on", on); b.setAttribute("aria-pressed", String(on)); }
  }

  function render() {
    state.tape = getTape();
    banner.hidden = true;
    tapeNote.textContent = `${t("Tape")}: ${tapeLabel(state.tape)}`;
    renderChips();
    io?.disconnect(); state.cards.clear();
    if (!state.list) {
      grid.replaceChildren();
      status.replaceChildren(...(state.error
        ? [h("div", { class: "gal-err" }, state.error), h("button", { class: "btn", type: "button", onClick: () => load(true) }, t("Retry"))]
        : [h("div", { class: "hint" }, t("Loading templates..."))]));
      return;
    }
    const shown = arrangeByTape(filterTemplates(state.list, { category: state.category, query: state.query }), state.tape);
    const cards = shown.map(makeCard);
    for (const c of cards) state.cards.set(c.tpl.id, c);
    grid.replaceChildren(...cards.map((c) => c.node));
    status.replaceChildren(...(shown.length ? [] : [h("div", { class: "hint" }, t("No templates match."))]));
    if (io) for (const c of cards) io.observe(c.node);
    else for (const c of cards) loadThumb(c);
  }

  async function load(force) {
    if (state.list && !force) return;
    state.loading = true; state.error = ""; render();
    try {
      const r = await api.templatesList();
      state.list = r.templates || []; state.categories = r.categories || [];
    } catch (e) { state.error = e?.message || String(e); }
    state.loading = false; render();
  }

  // keyboard: Tab stays inside the dialog; ArrowDown from search goes to the first card; Enter on a card picks it (native button)
  el.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowDown" && ev.target === search) {
      const first = grid.querySelector(".gal-card:not(:disabled)"); if (first) { ev.preventDefault(); first.focus(); }
    }
    if (ev.key !== "Tab") return;
    const f = [...el.querySelectorAll("button:not(:disabled), input")].filter((n) => !n.hidden && n.offsetParent !== null);
    if (!f.length) return;
    const root = el.getRootNode(), active = root.activeElement;
    if (ev.shiftKey && active === f[0]) { ev.preventDefault(); f[f.length - 1].focus(); }
    else if (!ev.shiftKey && active === f[f.length - 1]) { ev.preventDefault(); f[0].focus(); }
  });

  observe();
  return {
    el,
    showError(msg) { banner.textContent = msg; banner.hidden = !msg; if (msg) banner.scrollIntoView?.({ block: "nearest" }); },
    cache,
    /** Call after the container became visible. */
    open({ focusSearch = true, reset = true } = {}) {
      if (reset) { state.category = ""; state.query = ""; search.value = ""; }
      observe(); scroller.scrollTop = 0; render(); load();
      if (focusSearch) requestAnimationFrame(() => search.focus({ preventScroll: true }));
      else requestAnimationFrame(() => closeBtn.focus({ preventScroll: true }));
    },
    focus() { search.focus(); },
  };
}
