"""The critter's life: experience, levels, streaks, per-day stats and its stomach.

XP make the overall level. Tokens are the food: every harness that reports token
counts feeds the stomach, which empties again over time (mood.STOMACH_HALF_LIFE).
How full it is compares with the critter's own usual day, not with any rate limit.

Survives restarts: the state is a small JSON file on the data partition
(/data on the device). Written at most once a minute and on shutdown, so the
SD card is not hammered.
"""
import json
import logging
import math
import os
import threading
import time
from datetime import date, datetime, timedelta

from .mood import (BADGES, ESTIMATED_HARNESSES, FOOD_ACTIVE_HOURS, FOOD_DEFAULT_DAY,
                   FOOD_ESTIMATE, FOOD_HISTORY_DAYS, FOOD_HISTORY_MIN, FOOD_WEIGHTS,
                   STOMACH_HALF_LIFE, TOOL_XP_PER_DAY, XP_FOR, XP_FOR_SIGNAL,
                   XP_LEVEL_STEP)

log = logging.getLogger("tokibot")

KEEP_DAYS = 30
SAVE_EVERY = 60


def xp_for_level(level):
    """Total XP needed to reach a level: 0, 120, 480, 1080, 1920, ..."""
    return XP_LEVEL_STEP * (level - 1) ** 2


def level_for(xp):
    level = 1
    while xp >= xp_for_level(level + 1):
        level += 1
    return level


def _empty_day():
    return {"turns": 0, "tools": 0, "errors": 0, "sessions": 0, "xp": 0, "commits": 0,
            "food": 0, "food_est": 0, "tool_xp": 0}


def food_points(tokens):
    """Food points for token counts {"input", "output", "cache_write", "cache_read"}."""
    total = 0.0
    for kind, weight in FOOD_WEIGHTS.items():
        try:
            total += weight * max(0, int(tokens.get(kind) or 0))
        except (TypeError, ValueError):
            pass
    return int(total)


class Life:
    def __init__(self, path=None):
        self.path = path
        self.lock = threading.Lock()
        self.state = {"xp": 0, "streak": 0, "best_streak": 0, "last_day": "", "days": {},
                      "badges": {}, "food_total": 0, "stomach": {"level": 0.0, "at": 0.0}}
        self.dirty, self.saved_at, self.save_failed = False, 0.0, False
        self.level_up_at = 0.0
        self.badge_at, self.last_badge = 0.0, ""
        # Extra XP share right now (e.g. the co-working bonus); set by the social module.
        self.bonus = lambda now: 0.0
        self._bonus_carry = 0.0
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
        when = datetime.fromtimestamp(now)
        today = when.date()
        with self.lock:
            st = self.state
            day = st["days"].setdefault(today.isoformat(), _empty_day())
            if counter:
                day[counter] += 1
            if name == "PreToolUse":
                # Busy agents call hundreds of tools a turn; only the first few a day count
                gain = min(gain, max(0, TOOL_XP_PER_DAY - day.get("tool_xp", 0)))
                day["tool_xp"] = day.get("tool_xp", 0) + gain
            if not gain:
                self.dirty = True
                return False
            self._touch_streak(today)
            if name == "Stop" and when.hour < 4:
                self._badge("night_owl", now)
            if st["streak"] >= 7:
                self._badge("streak_7", now)
            bonus = self.bonus(now)
            if bonus:
                self._bonus_carry += gain * bonus
                extra = int(self._bonus_carry)
                self._bonus_carry -= extra
                gain += extra
            return self._gain(gain, day, now)

    def eat(self, name, ev, now=None):
        """Feed the stomach from one event: the token counts it carries, or an estimate
        for harnesses that report none (mood.ESTIMATED_HARNESSES). Returns the food points."""
        estimated = False
        if isinstance(ev.get("tokens"), dict):
            points = food_points(ev["tokens"])
        elif ev.get("harness") in ESTIMATED_HARNESSES:
            points, estimated = FOOD_ESTIMATE.get(name, 0), True
        else:
            points = 0
        if points <= 0:
            return 0
        now = now or time.time()
        today = datetime.fromtimestamp(now).date().isoformat()
        with self.lock:
            st = self.state
            day = st["days"].setdefault(today, _empty_day())
            day["food"] = day.get("food", 0) + points
            if estimated:
                day["food_est"] = day.get("food_est", 0) + points
            st["food_total"] = st.get("food_total", 0) + points
            stomach = st.setdefault("stomach", {"level": 0.0, "at": 0.0})
            stomach["level"] = self._digest(stomach, now) + points
            stomach["at"] = now
            self.dirty = True
        return points

    @staticmethod
    def _digest(stomach, now):
        age = max(0.0, now - (stomach.get("at") or now))
        return (stomach.get("level") or 0.0) * 0.5 ** (age / STOMACH_HALF_LIFE)

    def usual_day(self, now=None):
        """Food on a usual day: the average of the recent days that had food (not today)."""
        today = datetime.fromtimestamp(now or time.time()).date()
        since = (today - timedelta(days=FOOD_HISTORY_DAYS)).isoformat()
        with self.lock:
            days = [d.get("food", 0) for k, d in self.state["days"].items()
                    if since <= k < today.isoformat() and d.get("food", 0) > 0]
        if len(days) < FOOD_HISTORY_MIN:
            return FOOD_DEFAULT_DAY
        return sum(days) / len(days)

    def stomach(self, now=None):
        """How full the critter is: 1.0 = as full as while working on a usual day."""
        now = now or time.time()
        usual = self.usual_day(now)
        # Eating a usual day's food evenly over FOOD_ACTIVE_HOURS keeps this much in the stomach
        reference = usual / (FOOD_ACTIVE_HOURS * 3600) * STOMACH_HALF_LIFE / math.log(2)
        today = datetime.fromtimestamp(now).date().isoformat()
        with self.lock:
            st = self.state
            level = self._digest(st.get("stomach") or {}, now)
            day = st["days"].get(today, {})
            total = st.get("food_total", 0)
            food, est = day.get("food", 0), day.get("food_est", 0)
        return {"fullness": round(level / reference, 3) if reference else 0.0,
                "today": food, "estimated_today": est, "total": total, "usual_day": int(usual)}

    def award(self, gain, now=None):
        """Extra XP from outside the hook events (encounters, friendships).
        Counts as activity for the streak. Returns True on a level-up."""
        now = now or time.time()
        today = datetime.fromtimestamp(now).date()
        with self.lock:
            day = self.state["days"].setdefault(today.isoformat(), _empty_day())
            day.setdefault("social_xp", 0)
            day["social_xp"] += gain
            return self._gain(gain, day, now)

    def social_xp_today(self, now=None):
        today = datetime.fromtimestamp(now or time.time()).date().isoformat()
        with self.lock:
            return self.state["days"].get(today, {}).get("social_xp", 0)

    def _gain(self, gain, day, now):
        st = self.state
        before = level_for(st["xp"])
        st["xp"] += gain
        day["xp"] += gain
        self.dirty = True
        if level_for(st["xp"]) > before:
            self.level_up_at = now
            return True
        return False

    def reward(self, signals, now=None):
        """XP for what landed: commits, pushes and pull requests (see feeling.py).
        Returns True on a level-up."""
        gain = sum(XP_FOR_SIGNAL.get(sig, 0) for sig in signals)
        if not gain:
            return False
        now = now or time.time()
        today = datetime.fromtimestamp(now).date()
        with self.lock:
            st = self.state
            day = st["days"].setdefault(today.isoformat(), _empty_day())
            day["commits"] = day.get("commits", 0) + ("commit" in signals)
            self._touch_streak(today)
            before = level_for(st["xp"])
            st["xp"] += gain
            day["xp"] += gain
            self.dirty = True
            if level_for(st["xp"]) > before:
                self.level_up_at = now
                return True
        return False

    def add_badge(self, key, now=None):
        """Returns True if the badge is new."""
        with self.lock:
            return self._badge(key, now or time.time())

    def _badge(self, key, now):
        if key not in BADGES or key in self.state["badges"]:
            return False
        self.state["badges"][key] = int(now)
        self.badge_at, self.last_badge = now, key
        self.dirty = True
        return True

    def badges(self):
        with self.lock:
            return dict(self.state["badges"])

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
            day = {**_empty_day(), **st["days"].get(today.isoformat(), {})}
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
            "badge_at": self.badge_at, "last_badge": self.last_badge,
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
