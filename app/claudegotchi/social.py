"""Encounters and friendships between gotchis (see docs/social-concept.md).

Everything travels in small Bluetooth LE advertisements, so no connection and no
pairing are needed and it works on the Pi Zero's Bluetooth 4.2 chip. Every packet
is at most 27 bytes:

  "CG" type  body
  BEACON  0x11  ephemeral id (6) · friend tag (4) · level · mood · accessory · flags
  CARD    0x12  link (4) · message (1) · part/count (1) · up to 18 bytes of the signed card
  OFFER   0x13  link (4) · message (1) · part/count (1) · up to 18 bytes of a friendship offer

The link is the first 4 bytes of the sender's ephemeral id, so a receiver knows
which beacon the fragments belong to.

* The ephemeral id is random and changes every 15 minutes, so strangers cannot
  follow a gotchi around. Friends recognise each other by the friend tag, an HMAC
  of the time with a secret only friends know.
* The card (public key, name, level, accessory, signature) is only sent while the
  owner is "open to new friends" or has asked someone to be friends.
* An offer says "I want to be friends with <you> on <day>": a signature over both
  keys and the day, plus our beacon secret encrypted for the other gotchi. When
  both sides have sent one for the same day, both signatures form the friendship
  proof, which a community site can check later without trusting anyone.
"""
import hashlib
import hmac
import json
import logging
import os
import struct
import threading
import time
from collections import deque
from datetime import datetime

from . import crypto
from .identity import Identity, clean_name, default_name
from .life import Life
from .mood import ACCESSORIES, BADGES, COWORK_BONUS, SOCIAL_SHOW, SOCIAL_XP_PER_DAY, XP_SOCIAL

log = logging.getLogger("claudegotchi.social")

MAGIC = b"CG"
T_BEACON, T_CARD, T_OFFER = 0x11, 0x12, 0x13
EPOCH = 15 * 60               # the ephemeral id and friend tag change this often
CHUNK = 18                    # payload bytes per card/offer fragment
ENCOUNTER_SECONDS = 30        # seen this long (and close enough) = an encounter
RSSI_MIN = -80                # dBm; roughly "same room"
NEARBY = 60                   # seconds a peer counts as nearby after its last packet
PEER_FORGET = 120
OFFER_TTL = 15 * 60           # how long a friendship offer stays up
OFFER_LINGER = 3 * 60         # keep sending our offer after the friendship, so the other side completes too
AUTO_AFTER_DAYS = 3           # "auto" befriends gotchis met on this many different days
KNOWN_MAX = 300
SAVE_EVERY = 30
OFFER_LEN = 4 + 4 + 64 + 16 + crypto.TAG_LEN
MAX_OFFERS = 3                # friendship offers sent at the same time

MOOD_CODES = ["idle", "ready", "working", "tired", "waiting", "permission", "done", "error", "limit"]
ACCESSORY_CODES = list(ACCESSORIES)
F_OPEN, F_OFFERING = 1, 2


def epoch_of(now):
    return int(now // EPOCH)


def day_of(now):
    return int(now // 86400)            # UTC day number, the same on both gotchis


def friend_tag(secret, epoch):
    return hmac.new(secret, b"tag" + struct.pack(">I", epoch), hashlib.sha256).digest()[:4]


def proof_message(pub_a, pub_b, day):
    a, b = sorted((pub_a, pub_b))
    return b"claudegotchi-friends-1" + a + b + struct.pack(">I", day)


def make_proof(pub_1, sig_1, pub_2, sig_2, day):
    (a, sa), (b, sb) = sorted(((pub_1, sig_1), (pub_2, sig_2)))
    return {"v": 1, "a": a.hex(), "b": b.hex(), "day": day, "sig_a": sa.hex(), "sig_b": sb.hex()}


def verify_proof(p):
    """True if both gotchis signed the friendship. This is what the community site checks."""
    try:
        a, b = bytes.fromhex(p["a"]), bytes.fromhex(p["b"])
        msg = proof_message(a, b, int(p["day"]))
        return (a < b and crypto.verify(a, msg, bytes.fromhex(p["sig_a"]))
                and crypto.verify(b, msg, bytes.fromhex(p["sig_b"])))
    except (KeyError, ValueError, TypeError):
        return False


# --- packets ---------------------------------------------------------------------

def encode_card(ident, name, level, accessory):
    nb = clean_name(name).encode("utf-8")
    body = ident.pub + bytes([max(1, min(level, 255)), accessory, len(nb)]) + nb
    return body + ident.sign(b"claudegotchi-card-1" + body)


def decode_card(blob):
    if len(blob) < 35 + 64:
        return None
    n = blob[34]
    body, sig = blob[:35 + n], blob[35 + n:]
    if len(sig) != 64 or not crypto.verify(blob[:32], b"claudegotchi-card-1" + body, sig):
        return None
    return {"pub": blob[:32], "level": blob[32], "accessory": blob[33],
            "name": body[35:].decode("utf-8", "replace")}


def _offer_key(ident, peer_pub):
    return crypto.shared_key(ident.seed, peer_pub, b"beacon-secret")


def encode_offer(ident, peer_pub, day):
    sig = ident.sign(proof_message(ident.pub, peer_pub, day))
    nonce = struct.pack(">I", day) + ident.pub[:8]
    sealed = crypto.seal(_offer_key(ident, peer_pub), nonce, ident.beacon_secret)
    return hashlib.sha256(peer_pub).digest()[:4] + struct.pack(">I", day) + sig + sealed


def decode_offer(ident, sender_pub, blob):
    """(day, signature, sender's beacon secret) if the offer is for us and genuine."""
    if len(blob) != OFFER_LEN or blob[:4] != hashlib.sha256(ident.pub).digest()[:4]:
        return None
    day = struct.unpack(">I", blob[4:8])[0]
    sig, sealed = blob[8:72], blob[72:]
    if not crypto.verify(sender_pub, proof_message(sender_pub, ident.pub, day), sig):
        return None
    secret = crypto.open_sealed(_offer_key(ident, sender_pub), struct.pack(">I", day) + sender_pub[:8],
                                sealed)
    return (day, sig, secret) if secret else None


def fragments(kind, link, msg, blob):
    n = (len(blob) + CHUNK - 1) // CHUNK
    assert n <= 15
    return [MAGIC + bytes([kind]) + link + bytes([msg, (i << 4) | n]) + blob[i * CHUNK:(i + 1) * CHUNK]
            for i in range(n)]


def beacon(eph, tag, level, mood, accessory, flags):
    return MAGIC + bytes([T_BEACON]) + eph + tag + bytes([max(1, min(level, 255)), mood, accessory, flags])


# --- the engine ---------------------------------------------------------------------

def accessories_unlocked(level, badges):
    out = []
    for key, (_, rule) in ACCESSORIES.items():
        if not rule or (rule.startswith("level:") and level >= int(rule[6:])) or rule in badges:
            out.append(key)
    return out


class Social:
    def __init__(self, identity, life, path=None, radio=None, accept_all=False):
        self.me, self.life, self.path, self.radio = identity, life, path, radio
        self.accept_all = accept_all          # the simulator's fake gotchi says yes to everyone
        self.lock = threading.RLock()
        self.state = {"v": 1, "name": default_name(identity.pub), "accessory": "none",
                      "open": False, "auto": False, "friends": {}, "known": {}}
        if path:
            try:
                with open(path) as f:
                    self.state.update(json.load(f))
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as e:
                log.warning("Could not read %s (%s), starting with no friends", path, e)
        self.peers = {}           # ephemeral id (hex) -> what we know about that gotchi
        self.links = {}           # link (4 bytes) -> ephemeral id (hex)
        self.frags = {}           # (link, type) -> {"n": .., "parts": {..}}
        self.handled = {}         # (link, type) -> hash of the last message we processed
        self.offers_out = {}      # pub hex -> {"day", "until"}
        self.offers_in = {}       # pub hex -> {"day", "sig", "secret", "until"}
        self.declined = {}        # pub hex -> until
        self.events = deque(maxlen=30)
        self.my_mood = "idle"
        self.cowork = False
        self._epoch, self.eph, self._tags, self._tags_epoch = None, b"", {}, None
        self._packets_key, self._offer_cache, self._card_cache = None, {}, None
        self.dirty, self.saved_at = False, 0.0
        self.stop_evt = threading.Event()
        life.bonus = self.xp_bonus

    # --- lifecycle ---------------------------------------------------------------

    def start(self):
        self.tick()
        if self.radio:
            self.radio.start(self.on_packet)
        threading.Thread(target=self._loop, daemon=True, name="social").start()
        log.info("Social: I am %s (%s)", self.state["name"], self.me.id)
        return self

    def _loop(self):
        while not self.stop_evt.wait(1.0):
            try:
                self.tick()
            except Exception:
                log.exception("Social tick failed")

    def close(self):
        self.stop_evt.set()
        if self.radio:
            self.radio.stop()
        self.save(force=True)

    # --- receiving -----------------------------------------------------------------

    def on_packet(self, addr, rssi, data, now=None):
        if len(data) < 3 or data[:2] != MAGIC:
            return
        now = now or time.time()
        kind = data[2]
        if kind == T_BEACON and len(data) >= 17:
            self._on_beacon(data[3:9], data[9:13], data[13], data[14], data[15], data[16], rssi, now)
        elif kind in (T_CARD, T_OFFER) and len(data) >= 10:
            self._on_fragment((kind, data[3:7], data[7]), data[8] >> 4, data[8] & 15, data[9:], now)

    def _on_beacon(self, eph, tag, level, mood, accessory, flags, rssi, now):
        if eph == self.eph:
            return
        key = eph.hex()
        with self.lock:
            p = self.peers.get(key)
            if p is None:
                p = self.peers[key] = {"eph": key, "first": now, "rssi": rssi, "met": False,
                                       "card": None, "friend": None}
                self.links[eph[:4]] = key
            p.update(last=now, level=level, accessory=accessory, flags=flags,
                     mood=MOOD_CODES[mood] if mood < len(MOOD_CODES) else "idle")
            p["rssi"] = round(0.7 * p["rssi"] + 0.3 * rssi)
            friend = self._tags.get(tag)
            if friend and not p["friend"]:
                p["friend"] = friend
        self._check_encounter(key, now)

    def _on_fragment(self, mkey, idx, n, chunk, now):
        """mkey = (type, link, message number). Collects the parts of one message."""
        if not n or idx >= n:
            return
        kind, link, _ = mkey
        with self.lock:
            buf = self.frags.get(mkey)
            if not buf or buf["n"] != n:
                buf = self.frags[mkey] = {"n": n, "parts": {}, "at": now}
            buf["parts"][idx] = chunk
            if len(buf["parts"]) < n:
                return
            blob = b"".join(buf["parts"][i] for i in range(n))
            del self.frags[mkey]
            digest = hashlib.sha256(blob).digest()
            if self.handled.get(mkey) == digest:
                return
            peer_key = self.links.get(link)
        ok = self._on_card(peer_key, blob, now) if kind == T_CARD else self._on_offer(peer_key, blob, now)
        if ok:
            with self.lock:
                self.handled[mkey] = digest

    def _on_card(self, peer_key, blob, now):
        card = decode_card(blob)
        if not card or card["pub"] == self.me.pub:
            return False
        pub = card["pub"].hex()
        with self.lock:
            p = self.peers.get(peer_key)
            if not p:
                return False           # its beacon will come; the card is sent again
            p["card"] = {"pub": pub, "name": card["name"], "level": card["level"],
                         "accessory": card["accessory"]}
            rec = self.state["friends"].get(pub) or self.state["known"].setdefault(pub, {"days": []})
            rec.update(name=card["name"], level=card["level"], last_seen=int(now),
                       accessory=ACCESSORY_CODES[card["accessory"]]
                       if card["accessory"] < len(ACCESSORY_CODES) else "none")
            if pub in self.state["friends"]:
                p["friend"] = pub
            self.dirty = True
        self._check_encounter(peer_key, now)
        return True

    def _on_offer(self, peer_key, blob, now):
        with self.lock:
            p = self.peers.get(peer_key)
            pub = p["card"]["pub"] if p and p["card"] else None
        if not pub:
            return False               # we need its card first to check the signature
        got = decode_offer(self.me, bytes.fromhex(pub), blob)
        if not got:
            return True                # not for us (or broken): no need to look at it again
        day, sig, secret = got
        complete = invite = False
        with self.lock:
            if pub in self.state["friends"]:
                return True
            self.offers_in[pub] = {"day": day, "sig": sig.hex(), "secret": secret.hex(),
                                   "until": now + OFFER_TTL}
            mine = self.offers_out.get(pub)
            if not mine and (self.accept_all or (self.state["auto"] and self._days_met(pub) >= AUTO_AFTER_DAYS)):
                mine = self.offers_out[pub] = {"day": day, "until": now + OFFER_TTL}
            if mine:
                if mine["day"] != day and abs(mine["day"] - day) <= 1:
                    mine["day"] = day  # the other side started on another (UTC) day; follow it
                complete = mine["day"] == day
            elif self.declined.get(pub, 0) < now:
                invite = True
            name = self._name_of(pub)
        if complete:
            self._complete(pub, now)
        elif invite:
            self._event("invite", pub, name, now)
        return True

    # --- friendship ------------------------------------------------------------------

    def befriend(self, pub, now=None):
        """Ask a gotchi nearby to be friends, or say yes to its request."""
        now = now or time.time()
        with self.lock:
            if pub in self.state["friends"]:
                return "already"
            if pub not in self.state["known"]:
                return "unknown"
            incoming = self.offers_in.get(pub)
            day = incoming["day"] if incoming else day_of(now)
            self.offers_out[pub] = {"day": day, "until": now + OFFER_TTL}
            self.declined.pop(pub, None)
            done = bool(incoming)
        if done:
            self._complete(pub, now)
            return "friends"
        return "asked"

    def decline(self, pub, now=None):
        now = now or time.time()
        with self.lock:
            self.offers_in.pop(pub, None)
            self.offers_out.pop(pub, None)
            self.declined[pub] = now + OFFER_TTL

    def unfriend(self, pub):
        with self.lock:
            rec = self.state["friends"].pop(pub, None)
            if rec:
                rec.pop("secret", None)
                rec.pop("proof", None)
                self.state["known"][pub] = rec
                for p in self.peers.values():
                    if p["friend"] == pub:
                        p["friend"] = None
                self._epoch_tags(epoch_of(time.time()), force=True)
                self.dirty = True
        return bool(rec)

    def _complete(self, pub, now):
        with self.lock:
            incoming = self.offers_in.pop(pub, None)
            mine = self.offers_out.get(pub)
            if not incoming or not mine or pub in self.state["friends"]:
                return
            peer = bytes.fromhex(pub)
            day = incoming["day"]
            proof = make_proof(self.me.pub, self.me.sign(proof_message(self.me.pub, peer, day)),
                               peer, bytes.fromhex(incoming["sig"]), day)
            if not verify_proof(proof):
                log.warning("Friendship proof with %s did not verify", pub[:8])
                return
            rec = self.state["known"].pop(pub, {"days": []})
            rec.update(secret=incoming["secret"], proof=proof, since=int(now), last_seen=int(now))
            self.state["friends"][pub] = rec
            mine["until"] = now + OFFER_LINGER
            for p in self.peers.values():
                if p["card"] and p["card"]["pub"] == pub:
                    p["friend"] = pub
            self._epoch_tags(epoch_of(now), force=True)
            self.dirty = True
            name, n_friends = rec.get("name", "?"), len(self.state["friends"])
        log.info("New friend: %s", name)
        self.life.award(XP_SOCIAL["new_friend"], now)
        for key, need in (("first_friend", 1), ("five_friends", 5), ("ten_friends", 10)):
            if n_friends >= need:
                self.life.add_badge(key, now)
        self._event("newfriend", pub, name, now)

    def _days_met(self, pub):
        rec = self.state["friends"].get(pub) or self.state["known"].get(pub) or {}
        return len(rec.get("days", []))

    def _name_of(self, pub):
        rec = self.state["friends"].get(pub) or self.state["known"].get(pub) or {}
        return rec.get("name") or "?"

    # --- encounters ------------------------------------------------------------------

    def _check_encounter(self, key, now):
        with self.lock:
            p = self.peers.get(key)
            if (not p or p["met"] or now - p["first"] < ENCOUNTER_SECONDS or p["rssi"] < RSSI_MIN):
                return
            p["met"] = True
            pub = p["friend"] or (p["card"]["pub"] if p["card"] else None)
            today = datetime.fromtimestamp(now).date().isoformat()
            if pub:
                rec = self.state["friends"].get(pub) or self.state["known"].setdefault(pub, {"days": []})
                days = rec.setdefault("days", [])
                gain = (XP_SOCIAL["meet_new"] if not days else
                        XP_SOCIAL["meet_again"] if today not in days else 0)
                if today not in days:
                    days.append(today)
                    del days[:-30]
                rec["last_seen"] = int(now)
                self.dirty = True
                kind = "friend" if pub in self.state["friends"] else "encounter"
                name = rec.get("name") or "?"
            else:
                gain, kind, name = XP_SOCIAL["meet_anon"], "encounter_anon", ""
            level = p.get("level", 1)
            together = sum(1 for q in self.peers.values() if q["met"] and now - q["last"] < NEARBY)
        room = max(0, SOCIAL_XP_PER_DAY - self.life.social_xp_today(now))
        if gain and room:
            self.life.award(min(gain, room), now)
        self.life.add_badge("first_meet", now)
        if together >= 4:                      # four others plus me
            self.life.add_badge("conference", now)
        self._event(kind, pub, name, now, level)

    def xp_bonus(self, now):
        return COWORK_BONUS if self.cowork else 0.0

    def _event(self, kind, pub, name, now, level=None):
        with self.lock:
            self.events.append({"kind": kind, "pub": pub, "name": name, "level": level, "at": now})

    # --- the regular tick: rotate ids, expire things, update what we send -----------

    def tick(self, now=None):
        now = now or time.time()
        ep = epoch_of(now)
        rotate = False
        with self.lock:
            if ep != self._epoch:
                rotate = self._epoch is not None
                self._epoch, self.eph = ep, os.urandom(6)
            self._epoch_tags(ep)
            for k in [k for k, p in self.peers.items() if now - p["last"] > PEER_FORGET]:
                link = bytes.fromhex(k)[:4]
                self.links.pop(link, None)
                self.handled = {mk: v for mk, v in self.handled.items() if mk[1] != link}
                del self.peers[k]
            self.frags = {mk: b for mk, b in self.frags.items() if now - b["at"] < PEER_FORGET}
            for d in (self.offers_out, self.offers_in):
                for k in [k for k, o in d.items() if o["until"] < now]:
                    del d[k]
            self.declined = {k: v for k, v in self.declined.items() if v > now}
            working = self.my_mood in ("working", "tired")
            self.cowork = working and any(
                p["friend"] and p["mood"] in ("working", "tired") and now - p["last"] < NEARBY
                for p in self.peers.values())
        if self.cowork:
            self.life.add_badge("coworking", now)
        if rotate and self.radio:
            self.radio.rotate_address()
        self._update_packets(now)
        self.save()

    def _epoch_tags(self, ep, force=False):
        if not force and self._tags_epoch == ep:
            return
        tags = {}
        for pub, rec in self.state["friends"].items():
            secret = bytes.fromhex(rec.get("secret", ""))
            if secret:
                for e in (ep - 1, ep, ep + 1):          # allow for clocks that are a bit off
                    tags[friend_tag(secret, e)] = pub
        self._tags, self._tags_epoch = tags, ep

    def _update_packets(self, now):
        if self._epoch is None:
            return
        life = self.life.summary(now)
        unlocked = accessories_unlocked(life["level"], self.life.badges())
        with self.lock:
            st = self.state
            acc = st["accessory"] if st["accessory"] in unlocked else "none"
            acc_code = ACCESSORY_CODES.index(acc)
            mood = MOOD_CODES.index(self.my_mood) if self.my_mood in MOOD_CODES else 0
            offers = sorted((pub, o["day"]) for pub, o in self.offers_out.items())[:MAX_OFFERS]
            show_card = st["open"] or bool(offers)
            flags = (F_OPEN if st["open"] else 0) | (F_OFFERING if offers else 0)
            key = (self.eph, life["level"], mood, acc_code, flags, st["name"], tuple(offers))
            if key == self._packets_key:
                return
            self._packets_key = key
            name, eph, epoch = st["name"], self.eph, self._epoch
        link = eph[:4]
        packets = [beacon(eph, friend_tag(self.me.beacon_secret, epoch), life["level"], mood, acc_code, flags)]
        extra = []
        if show_card:
            ck = (name, life["level"], acc_code)
            if not self._card_cache or self._card_cache[0] != ck:
                self._card_cache = (ck, encode_card(self.me, name, life["level"], acc_code))
            extra += fragments(T_CARD, link, 0, self._card_cache[1])
        for i, (pub, day) in enumerate(offers):
            ok = (pub, day)
            if ok not in self._offer_cache:
                self._offer_cache[ok] = encode_offer(self.me, bytes.fromhex(pub), day)
            extra += fragments(T_OFFER, link, i + 1, self._offer_cache[ok])
        self._offer_cache = {k: v for k, v in self._offer_cache.items() if k in offers}
        for frag in extra:                      # the beacon between every fragment
            packets += [frag, packets[0]]
        if self.radio:
            self.radio.set_packets(packets)

    # --- persistence -------------------------------------------------------------------

    def save(self, force=False):
        if not self.path or not self.dirty:
            return
        if not force and time.time() - self.saved_at < SAVE_EVERY:
            return
        with self.lock:
            known = self.state["known"]
            if len(known) > KNOWN_MAX:
                for pub in sorted(known, key=lambda k: known[k].get("last_seen", 0))[:-KNOWN_MAX]:
                    del known[pub]
            data = json.dumps(self.state, indent=1)
            self.dirty = False
        self.saved_at = time.time()
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except OSError as e:
            log.warning("Could not save %s (%s)", self.path, e)

    # --- settings from the social page ------------------------------------------------

    def set_profile(self, name=None, accessory=None, open_=None, auto=None):
        with self.lock:
            if name is not None:
                self.state["name"] = clean_name(name) or default_name(self.me.pub)
            if accessory is not None and accessory in ACCESSORIES:
                self.state["accessory"] = accessory
            if open_ is not None:
                self.state["open"] = bool(open_)
            if auto is not None:
                self.state["auto"] = bool(auto)
            self.dirty = True
            self._packets_key = None          # the next tick sends the new profile
        self.save(force=True)

    # --- views ----------------------------------------------------------------------

    def accessory(self):
        life = self.life.summary()
        acc = self.state["accessory"]
        return acc if acc in accessories_unlocked(life["level"], self.life.badges()) else "none"

    def view(self, now=None):
        """For the display: who is around, and the latest thing worth showing."""
        now = now or time.time()
        with self.lock:
            near = [p for p in self.peers.values() if now - p["last"] < NEARBY]
            friends = [self._name_of(p["friend"]) for p in near if p["friend"]]
            event = None
            for ev in reversed(self.events):
                show = SOCIAL_SHOW.get("encounter" if ev["kind"] == "encounter_anon" else ev["kind"], 0)
                if ev["kind"] != "invite" and now - ev["at"] < show:
                    event = dict(ev)
                    break
            invite = next((self._name_of(pub) for pub in self.offers_in
                           if pub not in self.offers_out and self.declined.get(pub, 0) < now), None)
        return {"nearby": len(near), "friends_nearby": friends, "event": event, "invite": invite}

    def page_data(self, now=None):
        """Everything the social page shows."""
        now = now or time.time()
        life = self.life.summary(now)
        badges = self.life.badges()
        with self.lock:
            st = self.state
            nearby = []
            for p in sorted(self.peers.values(), key=lambda p: -p["rssi"]):
                if now - p["last"] > NEARBY:
                    continue
                pub = p["friend"] or (p["card"]["pub"] if p["card"] else "")
                nearby.append({
                    "pub": pub, "name": self._name_of(pub) if pub else "",
                    "level": p.get("level", 1), "mood": p.get("mood", ""), "rssi": p["rssi"],
                    "friend": pub in st["friends"], "met": p["met"],
                    "incoming": pub in self.offers_in, "asked": pub in self.offers_out,
                })
            friends = [dict(pub=pub, name=r.get("name", "?"), level=r.get("level", 1),
                            accessory=r.get("accessory", "none"), since=r.get("since", 0),
                            last_seen=r.get("last_seen", 0), days=len(r.get("days", [])),
                            proof=r.get("proof"))
                       for pub, r in sorted(st["friends"].items(), key=lambda kv: -kv[1].get("last_seen", 0))]
            incoming = [{"pub": pub, "name": self._name_of(pub)} for pub in self.offers_in
                        if pub not in self.offers_out]
            asked = [{"pub": pub, "name": self._name_of(pub)} for pub in self.offers_out
                     if pub not in st["friends"]]
            me = {"id": self.me.id, "pub": self.me.pub.hex(), "name": st["name"],
                  "accessory": st["accessory"], "open": st["open"], "auto": st["auto"]}
        return {"me": me, "level": life["level"], "xp": life["xp"], "nearby": nearby,
                "friends": friends, "incoming": incoming, "asked": asked,
                "badges": {k: (BADGES[k], badges.get(k)) for k in BADGES},
                "unlocked": accessories_unlocked(life["level"], badges)}


class FakePeer:
    """A pretend gotchi for the simulator: open to friends, says yes to every request,
    and asks open gotchis it meets to be friends after a short while."""
    ASK_AFTER = 45

    def __init__(self, name, data_dir, radio):
        os.makedirs(data_dir, exist_ok=True)
        self.life = Life()
        self.life.state["xp"] = 320                  # level 4
        self.social = Social(Identity.load_or_create(data_dir), self.life,
                             os.path.join(data_dir, "social.json"), radio, accept_all=True)
        self.social.set_profile(name=name, accessory="cap", open_=True)
        self.thread = threading.Thread(target=self._loop, daemon=True, name="fake-peer")

    def start(self):
        self.social.start()
        self.thread.start()
        return self

    def _loop(self):
        while not self.social.stop_evt.wait(5):
            now = time.time()
            self.social.my_mood = "working" if int(now // 120) % 2 else "idle"
            with self.social.lock:
                ready = [p["card"]["pub"] for p in self.social.peers.values()
                         if p["card"] and now - p["first"] > self.ASK_AFTER
                         and p["card"]["pub"] not in self.social.state["friends"]
                         and p["card"]["pub"] not in self.social.offers_out]
            for pub in ready:
                self.social.befriend(pub, now)
