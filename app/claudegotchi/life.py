"""The critter's life: experience, levels, streaks and per-day stats.

Survives restarts: the state is a small JSON file on the data partition
(/data on the device). Written at most once a minute and on shutdown, so the
SD card is not hammered.
"""
import json
import logging
import os
import threading
import time
from datetime import date, datetime, timedelta

from .mood import XP_FOR

log = logging.getLogger("claudegotchi")

KEEP_DAYS = 30
SAVE_EVERY = 60


def xp_for_level(level):
    """Total XP needed to reach a level: 0, 50, 150, 300, 500, ..."""
    return 25 * (level - 1) * level


def level_for(xp):
    level = 1
    while xp >= xp_for_level(level + 1):
        level += 1
    return level


def _empty_day():
    return {"turns": 0, "tools": 0, "errors": 0, "sessions": 0, "xp": 0}


class Life:
    def __init__(self, path=None):
        self.path = path
        self.lock = threading.Lock()
        self.state = {"xp": 0, "streak": 0, "best_streak": 0, "last_day": "", "days": {}}
        self.dirty, self.saved_at, self.save_failed = False, 0.0, False
        self.level_up_at = 0.0
        if path:
            try:
                with open(path) as f:
                    self.state.update(json.load(f))
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as e:
                log.warning("Could not read %s (%s), starting fresh", path, e)

    # --- recording -------------------------------------------------------------

    def record(self, name, ev, now=None):
        """Feed one hook event. Returns True on a level-up."""
        gain = XP_FOR.get(name, 0)
        if name == "StopFailure" and ev.get("error_type") == "rate_limit":
            gain = 0
        counter = {"Stop": "turns", "PreToolUse": "tools", "SessionStart": "sessions",
                   "StopFailure": "errors", "PostToolUseFailure": "errors"}.get(name)
        if not gain and not counter:
            return False
        now = now or time.time()
        today = datetime.fromtimestamp(now).date()
        with self.lock:
            st = self.state
            day = st["days"].setdefault(today.isoformat(), _empty_day())
            if counter:
                day[counter] += 1
            if not gain:
                self.dirty = True
                return False
            self._touch_streak(today)
            before = level_for(st["xp"])
            st["xp"] += gain
            day["xp"] += gain
            self.dirty = True
            if level_for(st["xp"]) > before:
                self.level_up_at = now
                return True
        return False

    def _touch_streak(self, today):
        st = self.state
        last = st["last_day"]
        if last == today.isoformat():
            return
        yesterday = (today - timedelta(days=1)).isoformat()
        st["streak"] = st["streak"] + 1 if last == yesterday else 1
        st["best_streak"] = max(st["best_streak"], st["streak"])
        st["last_day"] = today.isoformat()
        for old in sorted(st["days"])[:-KEEP_DAYS]:
            del st["days"][old]

    # --- reading ---------------------------------------------------------------

    def summary(self, now=None):
        now = now or time.time()
        today = datetime.fromtimestamp(now).date()
        with self.lock:
            st = self.state
            xp = st["xp"]
            day = dict(st["days"].get(today.isoformat(), _empty_day()))
            last = st["last_day"]
            streak = st["streak"]
            best = st["best_streak"]
        level = level_for(xp)
        idle_days = (today - date.fromisoformat(last)).days if last else None
        if idle_days is not None and idle_days > 1:
            streak = 0              # the streak is broken, even if nobody recorded it yet
        return {
            "xp": xp, "level": level,
            "level_xp": xp - xp_for_level(level),
            "level_need": xp_for_level(level + 1) - xp_for_level(level),
            "streak": streak, "best_streak": best,
            "today": day, "idle_days": idle_days,
            "level_up_at": self.level_up_at,
        }

    # --- persistence -----------------------------------------------------------

    def maybe_save(self, force=False):
        if not self.path or not self.dirty:
            return
        if not force and time.time() - self.saved_at < SAVE_EVERY:
            return
        with self.lock:
            data = json.dumps(self.state, indent=1)
            self.dirty = False
        self.saved_at = time.time()
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
            self.save_failed = False
        except OSError as e:
            if not self.save_failed:
                log.warning("Could not save %s (%s); progress is kept in memory only", self.path, e)
            self.save_failed = True
