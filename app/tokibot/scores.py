"""Highscores: the gotchi's signed score card for the list on the website.

Opt-in ([leaderboard] enabled). The card holds the level and, per day, the food
and XP of the last weeks, nothing about the work itself. It is signed with the
gotchi's Ed25519 key, so nobody else can post scores under its name. The website
merges the days and ranks:

  * Level         highest level, all time
  * Glutton       most food in this week / month / all time (estimated food
                  from harnesses without token counts does not count here)
  * Gourmet       most XP per million food points this week / month

Who posts the card: the gotchi itself once an hour when it has internet, and the
client on the computer for a gotchi that only hangs on the USB cable (GET /score
hands it the signed card). Turning it off posts a signed removal once.
"""
import json
import logging
import os
import threading
import time
import urllib.request
from datetime import datetime, timedelta

from .identity import default_name
from .life import level_for

log = logging.getLogger("tokibot.scores")

DEFAULT_URL = "https://tokibot.lottes.dev/api/scores"
SIGN_PREFIX = b"tokibot-score-1|"
CARD_DAYS = 35               # enough for this month and this week
POST_EVERY = 3600
RETRY_AFTER = 600


def make_card(identity, life, name="", now=None, remove=False):
    """{"card": "<json>", "sig": "<hex>"}; the signature covers the exact card text."""
    now = now or time.time()
    body = {"v": 1, "pub": identity.pub.hex(), "at": int(now)}
    if remove:
        body["remove"] = True
    else:
        today = datetime.fromtimestamp(now).date()
        since = (today - timedelta(days=CARD_DAYS - 1)).isoformat()
        with life.lock:
            xp = int(life.state.get("xp", 0))
            days = {k: {"food": int(d.get("food", 0)), "est": int(d.get("food_est", 0)),
                        "xp": int(d.get("xp", 0))}
                    for k, d in life.state.get("days", {}).items() if k >= since}
            best = int(life.state.get("best_streak", 0))
        body.update(name=name or default_name(identity.pub), xp=xp, level=level_for(xp),
                    best_streak=best, days=days)
    text = json.dumps(body, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return {"card": text, "sig": identity.sign(SIGN_PREFIX + text.encode("utf-8")).hex()}


class Scores:
    """Posts the card now and then. identity and name are callables, because a
    restore on the social page can swap the identity while the gotchi runs."""

    def __init__(self, cfg, life, identity, name, state_path=None, post=None):
        self.enabled = bool(cfg.get("enabled"))
        self.url = cfg.get("url") or DEFAULT_URL
        self.life, self.identity, self.name = life, identity, name
        self.state_path = state_path
        self.post = post or _post
        self.state = {"posted": False, "at": 0}
        if state_path:
            try:
                with open(state_path) as f:
                    self.state.update(json.load(f))
            except (OSError, ValueError):
                pass
        self.stop_evt = threading.Event()

    def card(self, now=None):
        return make_card(self.identity(), self.life, self.name(), now)

    def tick(self, now=None):
        """Post when due. Returns the wait until the next try in seconds."""
        now = now or time.time()
        if not self.enabled and not self.state.get("posted"):
            return POST_EVERY
        if self.enabled and now - self.state.get("at", 0) < POST_EVERY:
            return POST_EVERY - (now - self.state.get("at", 0))
        if self.enabled:
            payload = self.card(now)
        else:
            payload = make_card(self.identity(), self.life, now=now, remove=True)
        try:
            self.post(self.url, payload)
        except Exception as e:
            log.info("Highscores: could not post (%s), trying again later", e)
            return RETRY_AFTER
        self.state = {"posted": self.enabled, "at": now}
        self._save()
        log.info("Highscores: %s", "score posted" if self.enabled else "removed from the list")
        return POST_EVERY

    def _save(self):
        if not self.state_path:
            return
        try:
            tmp = self.state_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.state, f)
            os.replace(tmp, self.state_path)
        except OSError as e:
            log.warning("Could not save %s (%s)", self.state_path, e)

    def start(self):
        def loop():
            self.stop_evt.wait(60)              # let the network come up first
            while not self.stop_evt.is_set():
                self.stop_evt.wait(max(60, self.tick()))
        threading.Thread(target=loop, daemon=True, name="scores").start()
        return self


def _post(url, payload, timeout=15):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp.read()
