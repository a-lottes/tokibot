import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";
import { test } from "node:test";
import { CardError, SIGN_PREFIX, apply, gotchiId, levelFor, openCard, periods, rank } from "../lib/board.mjs";

const NOW = Date.UTC(2026, 9, 7, 12) / 1000;            // a Wednesday
const DAY = 86400;

function keys() {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const pub = publicKey.export({ format: "der", type: "spki" }).subarray(-32).toString("hex");
  return { pub, privateKey };
}

function signed(k, body) {
  const card = JSON.stringify({ v: 1, pub: k.pub, ...body });
  return { card, sig: sign(null, Buffer.from(SIGN_PREFIX + card), k.privateKey).toString("hex") };
}

const score = (k, xp, days, at = NOW) => signed(k, { at, name: "Mochi", xp, level: levelFor(xp), days });

test("a signed card opens, a changed one does not", () => {
  const k = keys();
  const p = score(k, 60, {});
  assert.equal(openCard(p).name, "Mochi");
  assert.throws(() => openCard({ ...p, card: p.card.replace("Mochi", "Mally") }), CardError);
  assert.throws(() => openCard({ ...p, sig: "00".repeat(64) }), CardError);
});

test("a card made by the gotchi (Python) opens", () => {
  // made with tokibot.scores.make_card and a fixed seed of 32 x 0x01
  const p = {
    card: '{"at":1791000000,"best_streak":0,"days":{"2026-10-03":{"est":0,"food":1500,"xp":10}},"level":1,"name":"Mochi","pub":"8a88e3dd7409f195fd52db2d3cba5d72ca6709bf1d94121bf3748801b40f6f5c","v":1,"xp":10}',
    sig: "3b8e737c61822cdc6bf111de8a6eb059b0988af5e511300ed2b5d571ea05a09c6573b7b3c00630849176c100120e53e54078b98759462bde88fc6e785704cb09",
  };
  assert.equal(openCard(p).xp, 10);
  assert.equal(gotchiId(JSON.parse(p.card).pub).length, 12);
});

test("days merge, xp and food stay plausible", () => {
  const k = keys();
  const a = apply(undefined, openCard(score(k, 60, { "2026-10-06": { food: 100, est: 0, xp: 20 } }, NOW - 100)), NOW);
  const b = apply(a, openCard(score(k, 80, { "2026-10-07": { food: 50, est: 10, xp: 20 } })), NOW);
  assert.deepEqual(Object.keys(b.days), ["2026-10-06", "2026-10-07"]);
  assert.equal(b.first_seen, NOW - 100);
  assert.throws(() => apply(b, openCard(score(k, 80, {})), NOW), /older/);
  assert.throws(() => apply(b, openCard(score(k, 10_000_000, {}, NOW + 5)), NOW + 5), /too fast/);
  assert.throws(() => apply(undefined, openCard(score(k, 60, { "2026-10-07": { food: 5, est: 9, xp: 0 } })), NOW), /out of range/);
  assert.throws(() => apply(undefined, openCard(score(k, 60, { "2020-01-01": { food: 5, est: 0, xp: 0 } })), NOW), /out of range/);
  assert.throws(() => apply(undefined, openCard(signed(k, { at: NOW, name: "x", xp: 60, level: 9, days: {} })), NOW), /level/);
  assert.throws(() => apply(undefined, openCard(score(k, 60, {}, NOW - 3 * DAY)), NOW), /clock/);
});

test("a removal deletes the entry", () => {
  const k = keys();
  const a = apply(undefined, openCard(score(k, 60, {}, NOW - 10)), NOW);
  assert.equal(apply(a, openCard(signed(k, { at: NOW, remove: true })), NOW), null);
  assert.equal(apply(undefined, openCard(signed(k, { at: NOW, remove: true })), NOW), undefined);
});

test("week starts on Monday, month on the first", () => {
  assert.deepEqual(periods(NOW), { week: "2026-10-05", month: "2026-10-01", all: "0000-00-00" });
});

test("boards: level, glutton without estimates, gourmet with enough food", () => {
  const [a, b] = [keys(), keys()];
  const big = apply(undefined, openCard(score(a, 500, {
    "2026-10-06": { food: 3_000_000, est: 1_000_000, xp: 300 },
    "2026-09-20": { food: 9_000_000, est: 0, xp: 100 },
  })), NOW);
  const small = apply(undefined, openCard(score(b, 900, { "2026-10-07": { food: 2_500_000, est: 0, xp: 500 } })), NOW);
  const r = rank([big, small], NOW);
  assert.deepEqual(r.boards.level.map((x) => x.value), [900, 500]);
  assert.deepEqual(r.boards.glutton.week.map((x) => x.value), [2_500_000, 2_000_000]);
  assert.deepEqual(r.boards.glutton.all.map((x) => x.value), [11_000_000, 2_500_000]);
  assert.deepEqual(r.boards.gourmet.week.map((x) => x.value), [200, 100]);
  assert.equal(r.boards.gourmet.week[0].id, small.id);
});

test("the function stores, ranks and removes", async () => {
  const { handle } = await import("../functions/scores.mjs");
  const blobs = new Map();
  const store = {
    list: async () => ({ blobs: [...blobs.keys()].map((key) => ({ key })) }),
    get: async (key) => blobs.get(key) ?? null,
    setJSON: async (key, v) => void blobs.set(key, v),
    delete: async (key) => void blobs.delete(key),
  };
  const post = (body) => handle(new Request("https://x/api/scores", { method: "POST", body: JSON.stringify(body) }), store, NOW);
  const k = keys();
  assert.equal((await post(score(k, 60, { "2026-10-07": { food: 10, est: 0, xp: 5 } }, NOW - 5))).status, 200);
  assert.equal((await post({ card: "{}", sig: "zz" })).status, 400);
  const board = await (await handle(new Request("https://x/api/scores"), store, NOW)).json();
  assert.equal(board.boards.level[0].name, "Mochi");
  assert.equal(board.boards.glutton.week[0].value, 10);
  const gone = await (await post(signed(k, { at: NOW, remove: true }))).json();
  assert.deepEqual(gone, { ok: true, removed: true });
  assert.equal(blobs.size, 0);
});
