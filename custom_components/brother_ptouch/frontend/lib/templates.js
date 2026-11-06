// Pure logic for the "New from template" gallery (no DOM; usable from node tests).

/** API tape value (3.5 mm tape is reported as 4). */
export const normTape = (t) => (Number(t) === 3.5 ? 4 : Number(t));

/** Does the template support this tape width? */
export function tapeCompatible(tpl, tape) {
  return (tpl?.tapes || []).includes(normTape(tape));
}

/** Tapes list as text, e.g. "9 / 12 / 18 mm" (4 shown as 3.5). */
export function tapesText(tapes) {
  const nums = [...(tapes || [])].sort((a, b) => a - b).map((t) => (t === 4 ? "3.5" : String(t)));
  return nums.length ? `${nums.join(" / ")} mm` : "";
}

const hay = (t) => [t.name, t.description, t.category, ...Object.values(t.variables || {}).map((v) => v?.label || "")]
  .join(" ").toLowerCase();

/** Filter by category (null/"" = all) and a free-text query (every word must match somewhere). */
export function filterTemplates(list, { category = "", query = "" } = {}) {
  const terms = String(query || "").toLowerCase().split(/\s+/).filter(Boolean);
  return (list || []).filter((t) => (!category || t.category === category) && terms.every((w) => hay(t).includes(w)));
}

/** Stable order: templates that fit the tape first, the rest keep their relative order. */
export function arrangeByTape(list, tape) {
  const ok = [], no = [];
  for (const t of list) (tapeCompatible(t, tape) ? ok : no).push(t);
  return [...ok, ...no];
}

/** Category chips: the backend order first, then any category only seen on templates; empty ones dropped. */
export function categoryChips(categories, list) {
  const seen = new Set((list || []).map((t) => t.category));
  const out = [];
  for (const c of categories || []) if (seen.has(c) && !out.includes(c)) out.push(c);
  for (const c of seen) if (!out.includes(c)) out.push(c);
  return out;
}

/** Runs at most `max` async jobs at once. A job whose `skip()` is true when its turn comes is dropped (resolves `undefined`). */
export class Limiter {
  constructor(max = 3) { this.max = max; this.active = 0; this.queue = []; this.peak = 0; }
  run(fn, skip) {
    return new Promise((resolve, reject) => {
      this.queue.push({ fn, skip, resolve, reject });
      this._pump();
    });
  }
  _pump() {
    while (this.active < this.max && this.queue.length) {
      const job = this.queue.shift();
      if (job.skip?.()) { job.resolve(undefined); continue; }
      this.active++; this.peak = Math.max(this.peak, this.active);
      Promise.resolve().then(job.fn).then(job.resolve, job.reject).finally(() => { this.active--; this._pump(); });
    }
  }
}

/** In-memory thumbnail cache keyed by tape + template; in-flight loads are shared; failures are not cached forever. */
export class ThumbCache {
  constructor(load, { concurrency = 3 } = {}) {
    this.load = load; this.limiter = new Limiter(concurrency);
    this.done = new Map(); this.inflight = new Map(); this.errors = new Map();
  }
  static key(tape, id) { return `${normTape(tape)}|${id}`; }
  peek(tape, id) { return this.done.get(ThumbCache.key(tape, id)); }
  /** Resolves the thumbnail, or `undefined` when skipped (not visible any more). Rejects on a load error. */
  get(tape, id, skip) {
    const k = ThumbCache.key(tape, id);
    if (this.done.has(k)) return Promise.resolve(this.done.get(k));
    if (this.inflight.has(k)) return this.inflight.get(k);
    const p = this.limiter.run(async () => {
      const v = await this.load(normTape(tape), id);
      this.done.set(k, v);
      return v;
    }, skip).finally(() => this.inflight.delete(k));
    this.inflight.set(k, p);
    return p;
  }
  clear() { this.done.clear(); }
}
