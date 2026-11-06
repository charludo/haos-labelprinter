import assert from "node:assert/strict";
import { normTape, tapeCompatible, tapesText, filterTemplates, arrangeByTape, categoryChips, Limiter, ThumbCache } from "../../lib/templates.js";

let n = 0; const t = async (name, fn) => { await fn(); n++; console.log("ok -", name); };
const L = [
  { id: "a", name: "Pantry jar", category: "kitchen", description: "Big label for jars", tapes: [12, 18, 24], variables: { item: { label: "Item name", default: "Rice" } } },
  { id: "b", name: "Wi-Fi", category: "network", description: "SSID + QR", tapes: [24], variables: {} },
  { id: "c", name: "Cable flag", category: "network", description: "Wrap-around flag", tapes: [4, 6, 9, 12], variables: {} },
  { id: "d", name: "Spice", category: "kitchen", description: "Spice jar lid", tapes: [9, 12], variables: {} },
];
const ids = (l) => l.map((x) => x.id).join("");

await t("tape normalisation and compatibility", () => {
  assert.equal(normTape(3.5), 4); assert.equal(normTape("12"), 12);
  assert.ok(tapeCompatible(L[2], 3.5)); assert.ok(tapeCompatible(L[2], 4)); assert.ok(!tapeCompatible(L[1], 12));
  assert.ok(!tapeCompatible(undefined, 12));
  assert.equal(tapesText([24, 4, 12]), "3.5 / 12 / 24 mm");
});
await t("filter by category", () => {
  assert.equal(ids(filterTemplates(L, { category: "kitchen" })), "ad");
  assert.equal(ids(filterTemplates(L, { category: "" })), "abcd");
  assert.equal(ids(filterTemplates(L, { category: "nope" })), "");
});
await t("filter by search (name, description, variable labels, all terms, case-insens.)", () => {
  assert.equal(ids(filterTemplates(L, { query: "JAR" })), "ad");
  assert.equal(ids(filterTemplates(L, { query: "jar lid" })), "d");
  assert.equal(ids(filterTemplates(L, { query: "item name" })), "a");
  assert.equal(ids(filterTemplates(L, { query: "  qr " })), "b");
  assert.equal(ids(filterTemplates(L, { query: "jar", category: "network" })), "");
  assert.equal(ids(filterTemplates(L, { query: "zzz" })), "");
});
await t("arrange: compatible first, stable", () => {
  assert.equal(ids(arrangeByTape(L, 12)), "acdb");
  assert.equal(ids(arrangeByTape(L, 24)), "abcd");
  assert.equal(ids(arrangeByTape(L, 4)), "cabd");
});
await t("category chips", () => {
  assert.deepEqual(categoryChips(["kitchen", "empty", "network"], L), ["kitchen", "network"]);
  assert.deepEqual(categoryChips([], L), ["kitchen", "network"]);
});
await t("limiter never exceeds max and runs everything", async () => {
  const lim = new Limiter(3); let cur = 0, peak = 0, done = 0;
  const job = () => async () => { cur++; peak = Math.max(peak, cur); await new Promise((r) => setTimeout(r, 5)); cur--; done++; };
  await Promise.all(Array.from({ length: 12 }, () => lim.run(job())));
  assert.equal(peak, 3); assert.equal(done, 12); assert.equal(lim.active, 0);
});
await t("limiter drops skipped jobs and survives errors", async () => {
  const lim = new Limiter(1); let ran = 0;
  const a = lim.run(async () => { await new Promise((r) => setTimeout(r, 5)); ran++; return 1; });
  const b = lim.run(async () => { ran++; }, () => true);
  const c = lim.run(async () => { throw new Error("x"); });
  const d = lim.run(async () => { ran++; return 4; });
  assert.equal(await a, 1); assert.equal(await b, undefined);
  await assert.rejects(c, /x/); assert.equal(await d, 4); assert.equal(ran, 2);
});
await t("thumb cache: per tape, shared in-flight, not re-fetched", async () => {
  const calls = []; let cur = 0, peak = 0;
  const cache = new ThumbCache(async (tape, id) => { calls.push(`${tape}:${id}`); cur++; peak = Math.max(peak, cur); await new Promise((r) => setTimeout(r, 4)); cur--; return { src: `${tape}-${id}` }; }, { concurrency: 3 });
  const [x, y] = await Promise.all([cache.get(12, "a"), cache.get(12, "a")]);
  assert.equal(x, y); assert.equal(calls.length, 1);
  assert.equal((await cache.get(12, "a")).src, "12-a"); assert.equal(calls.length, 1);
  assert.equal((await cache.get(18, "a")).src, "18-a"); assert.equal(calls.length, 2);   // other tape: separate entry
  assert.equal((await cache.get(3.5, "a")).src, "4-a"); assert.equal(cache.peek(4, "a").src, "4-a");   // 3.5 == 4
  await Promise.all(Array.from({ length: 10 }, (_, i) => cache.get(24, "t" + i)));
  assert.ok(peak <= 3, `peak ${peak}`);
});
await t("thumb cache: skipped loads are not cached, errors are retryable", async () => {
  let fail = true, calls = 0;
  const cache = new ThumbCache(async () => { calls++; if (fail) throw new Error("boom"); return { src: "ok" }; }, { concurrency: 1 });
  const blocker = cache.get(12, "block"); 
  assert.equal(await cache.get(12, "s", () => true), undefined); await blocker.catch(() => {});
  assert.equal(cache.peek(12, "s"), undefined);
  await assert.rejects(cache.get(12, "e"), /boom/); fail = false;
  assert.equal((await cache.get(12, "e")).src, "ok");
});
console.log(`${n} tests passed`);
