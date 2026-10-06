// Highscores: checks signed score cards from gotchis and ranks them.
// Pure logic without storage, so it can be tested with `npm test` in netlify/.
// The card format is made in app/tokibot/scores.py.
import { createHash, createPublicKey, verify } from "node:crypto";

export const SIGN_PREFIX = "tokibot-score-1|";
export const MAX_CARD = 20000;              // bytes of card text
export const MAX_DAY_FOOD = 1_000_000_000;  // food points a day; far above any real day
export const MAX_DAY_XP = 50_000;
export const MAX_XP = 100_000_000;
export const KEEP_DAYS = 400;
export const CARD_DAYS = 40;
export const GOURMET_MIN_FOOD = 2_000_000;
export const TOP = 50;
const SPKI_ED25519 = Buffer.from("302a300506032b6570032100", "hex");

export class CardError extends Error {}

const DAY = 86400;
const isInt = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;

export function xpForLevel(level) {
  return 25 * (level - 1) * level;
}

export function levelFor(xp) {
  let level = 1;
  while (xp >= xpForLevel(level + 1)) level++;
  return level;
}

export function gotchiId(pubHex) {
  const h = createHash("sha256").update(Buffer.from(pubHex, "hex")).digest("hex");
  return `cg-${h.slice(0, 4)}-${h.slice(4, 8)}`;
}

export function isoDate(ts) {
  return new Date(ts * 1000).toISOString().slice(0, 10);
}

// Ed25519 signature over SIGN_PREFIX + the exact card text. Returns the parsed card.
export function openCard(payload) {
  if (!payload || typeof payload.card !== "string" || typeof payload.sig !== "string") {
    throw new CardError("card and sig are needed");
  }
  if (Buffer.byteLength(payload.card) > MAX_CARD) throw new CardError("card too large");
  if (!/^[0-9a-f]{128}$/.test(payload.sig)) throw new CardError("bad signature format");
  let card;
  try {
    card = JSON.parse(payload.card);
  } catch {
    throw new CardError("card is not JSON");
  }
  if (!card || card.v !== 1 || typeof card.pub !== "string" || !/^[0-9a-f]{64}$/.test(card.pub)) {
    throw new CardError("unknown card");
  }
  const key = createPublicKey({ key: Buffer.concat([SPKI_ED25519, Buffer.from(card.pub, "hex")]), format: "der", type: "spki" });
  const ok = verify(null, Buffer.from(SIGN_PREFIX + payload.card, "utf8"), key, Buffer.from(payload.sig, "hex"));
  if (!ok) throw new CardError("signature does not match");
  return card;
}

export function cleanName(name) {
  const s = String(name ?? "").replace(/[\u0000-\u001f\u007f<>]/g, "").replace(/\s+/g, " ").trim();
  let out = "";
  for (const ch of s) {                     // at most 12 bytes, like on the gotchi
    if (Buffer.byteLength(out + ch) > 12) break;
    out += ch;
  }
  return out;
}

// What to store after this card: the merged entry, null to delete it, or
// undefined when nothing changes. Throws CardError for cards that make no sense.
export function apply(entry, card, now) {
  if (!isInt(card.at, now - 2 * DAY, now + 600)) throw new CardError("card time is off, is the gotchi's clock right?");
  if (entry && card.at <= entry.at) throw new CardError("older than the stored card");
  if (card.remove === true) return entry ? null : undefined;

  const name = cleanName(card.name);
  if (!name) throw new CardError("name missing");
  if (!isInt(card.xp, 0, MAX_XP)) throw new CardError("xp out of range");
  if (card.level !== levelFor(card.xp)) throw new CardError("level does not match xp");
  if (!card.days || typeof card.days !== "object" || Array.isArray(card.days)) throw new CardError("days missing");
  const keys = Object.keys(card.days);
  if (keys.length > CARD_DAYS) throw new CardError("too many days");
  const first = isoDate(now - CARD_DAYS * DAY), last = isoDate(now + DAY);
  const days = { ...(entry?.days || {}) };
  for (const k of keys) {
    const d = card.days[k];
    if (!/^\d{4}-\d{2}-\d{2}$/.test(k) || k < first || k > last) throw new CardError(`day ${k} out of range`);
    if (!d || !isInt(d.food, 0, MAX_DAY_FOOD) || !isInt(d.est, 0, d.food) || !isInt(d.xp, 0, MAX_DAY_XP)) {
      throw new CardError(`day ${k} out of range`);
    }
    days[k] = { food: d.food, est: d.est, xp: d.xp };
  }
  if (entry) {
    const elapsed = Math.max(1, Math.ceil((card.at - entry.at) / DAY) + 1);
    if (card.xp - entry.xp > elapsed * MAX_DAY_XP) throw new CardError("xp grew too fast");
  }
  const kept = Object.keys(days).sort().slice(-KEEP_DAYS);
  return {
    pub: card.pub, id: gotchiId(card.pub), name, xp: card.xp, level: card.level,
    best_streak: isInt(card.best_streak, 0, 100000) ? card.best_streak : 0,
    at: card.at, first_seen: entry?.first_seen ?? card.at,
    days: Object.fromEntries(kept.map((k) => [k, days[k]])),
  };
}

// Monday of the ISO week and the first of the month, as YYYY-MM-DD (UTC).
export function periods(now) {
  const d = new Date(now * 1000);
  const monday = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - ((d.getUTCDay() + 6) % 7)));
  return {
    week: monday.toISOString().slice(0, 10),
    month: isoDate(now).slice(0, 8) + "01",
    all: "0000-00-00",
  };
}

function sums(entry, from) {
  let food = 0, est = 0, xp = 0;
  for (const [k, d] of Object.entries(entry.days || {})) {
    if (k >= from) { food += d.food; est += d.est; xp += d.xp; }
  }
  return { food, exact: food - est, xp };
}

const row = (e, value) => ({ name: e.name, id: e.id, level: e.level, value });
const top = (rows) => rows.filter((r) => r.value > 0).sort((a, b) => b.value - a.value || a.name.localeCompare(b.name)).slice(0, TOP);

export function rank(entries, now) {
  const p = periods(now);
  const boards = { level: top(entries.map((e) => row(e, e.xp))), glutton: {}, gourmet: {} };
  for (const [period, from] of Object.entries(p)) {
    boards.glutton[period] = top(entries.map((e) => row(e, sums(e, from).exact)));
    boards.gourmet[period] = top(entries.map((e) => {
      const s = sums(e, from);
      return row(e, s.food >= GOURMET_MIN_FOOD ? Math.round((s.xp / s.food) * 1e6 * 10) / 10 : 0);
    }));
  }
  return { updated: now, periods: { week: p.week, month: p.month }, gotchis: entries.length, boards };
}
