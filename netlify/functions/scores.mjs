// /api/scores: gotchis post signed score cards (POST), the highscores page reads
// the ranked lists (GET). One blob per gotchi, keyed by its public key.
import { getStore } from "@netlify/blobs";
import { CardError, apply, openCard, rank } from "../lib/board.mjs";

const json = (status, body, headers = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

export default (req) => handle(req, getStore({ name: "scores", consistency: "strong" }), Math.floor(Date.now() / 1000));

// The store is passed in, so the tests can use one in memory.
export async function handle(req, store, now) {

  if (req.method === "GET") {
    const { blobs } = await store.list();
    const entries = (await Promise.all(blobs.map((b) => store.get(b.key, { type: "json" })))).filter(Boolean);
    return json(200, rank(entries, now), {
      "Cache-Control": "public, max-age=60",
      "Netlify-CDN-Cache-Control": "public, s-maxage=60, stale-while-revalidate=300",
    });
  }
  if (req.method !== "POST") return json(405, { error: "GET or POST" });

  let card;
  try {
    const text = await req.text();
    if (text.length > 30000) return json(413, { error: "too large" });
    card = openCard(JSON.parse(text));
    const entry = await store.get(card.pub, { type: "json" });
    const next = apply(entry, card, now);
    if (next === null) {
      await store.delete(card.pub);
      return json(200, { ok: true, removed: true });
    }
    if (next) await store.setJSON(card.pub, next);
    return json(200, { ok: true });
  } catch (e) {
    if (e instanceof CardError || e instanceof SyntaxError) return json(400, { error: e.message });
    throw e;
  }
}

export const config = { path: "/api/scores" };
