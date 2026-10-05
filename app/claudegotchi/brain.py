"""The brain: folds all Claude Code sessions into a single mood."""
import random
import threading
import time
from datetime import datetime

from .feeling import Feeling
from .life import Life
from .mood import (CONTEXT_FULL_PCT, DONE_DECAY, ERROR_LABELS, FILL_DEFAULTS, FOCUS_WEIGHT,
                   HUNGRY_AFTER_DAYS, JUGGLING_FROM, LEVELUP_SHOW, LIMIT_FALLBACK, LIMIT_WARN_PCT,
                   MESSAGES, MOMENT_SHOW, MOOD_HOLD, PERMISSION_DECAY, PRIORITY, SESSION_FORGET,
                   SUMMARY_FROM_HOUR, SUMMARY_UNTIL_HOUR, WAITING_NOTIFICATIONS, WORKING_EVENTS,
                   WORKING_STALE)

# Moods a level-up celebration may cover; anything that needs you wins over it.
CELEBRATE_OVER = {"working", "done", "ready", "idle", "error"}
# Situations the feeling layer may tint; permission, waiting, limit and error never are.
TINTABLE = {"working", "done", "ready", "idle"}
# Tints of "working": they swap among each other at most every MOOD_HOLD seconds.
WORKING_MOODS = {"working", "flow", "struggling", "juggling", "tired"}


class Brain:
    def __init__(self, life=None, battery=None):
        self.life = life or Life()
        self.feeling = Feeling()
        self.context = {}         # session id → context window used, in percent
        self.shown, self.shown_since = "", 0.0
        self.battery = battery    # battery.BatteryMonitor, or None without a battery
        self.lock = threading.Lock()
        self.sessions = {}
        self.limits = {}          # {"five_hour": {"pct":.., "reset":..}, ...}
        self.tools_today = 0
        self.day = datetime.now().date()

    def handle_hook(self, ev):
        name = ev.get("hook_event_name", "")
        sid = str(ev.get("session_id") or "unknown")
        ts = float(ev.get("ts") or time.time())
        now = time.time()
        self.life.record(name, ev, now)
        with self.lock:
            if name == "SessionEnd":
                self.sessions.pop(sid, None)
                self.feeling.forget(sid)
                self.context.pop(sid, None)
                return
            s = self.sessions.setdefault(sid, {
                "state": "ready", "since": now, "updated": now, "ts": 0.0,
                "project": "", "tool": "", "error": ""})
            # Hooks run asynchronously, so events can overtake each other. Ignore older ones.
            if ts < s["ts"]:
                return
            s["ts"] = ts
            s["updated"] = now
            if ev.get("project"):
                s["project"] = ev["project"]
            signals = self.feeling.record(sid, ev, now)
            self.life.reward(signals, now)

            new = None
            if name == "SessionStart":
                new = "ready"
            elif name in WORKING_EVENTS:
                new = "working"
                if name == "PreToolUse":
                    self._count_tool()
            elif name == "PermissionRequest":
                new = "permission"
            elif name == "Notification":
                nt = ev.get("notification_type", "")
                if nt == "permission_prompt":
                    new = "permission"
                elif nt in WAITING_NOTIFICATIONS:
                    new = "waiting"
                elif nt == "quota_auto_resume_fired":
                    new = "working"
            elif name == "Stop":
                new = "done"
            elif name == "StopFailure":
                et = ev.get("error_type", "unknown")
                if et == "rate_limit":
                    new = "limit"
                else:
                    new = "error"
                    s["error"] = ERROR_LABELS.get(et, et)

            if ev.get("tool_name"):
                s["tool"] = ev["tool_name"]
            elif name in ("UserPromptSubmit", "Stop"):
                s["tool"] = ""
            if new and new != s["state"]:
                s["state"] = new
                s["since"] = now

    def handle_limits(self, data):
        rl = data.get("rate_limits") or {}
        with self.lock:
            if data.get("session_id") and data.get("context_pct") is not None:
                self.context[str(data["session_id"])] = float(data["context_pct"])
            for key in ("five_hour", "seven_day"):
                w = rl.get(key)
                if isinstance(w, dict) and w.get("used_percentage") is not None:
                    self.limits[key] = {"pct": float(w["used_percentage"]),
                                        "reset": float(w.get("resets_at") or 0)}

    def _count_tool(self):
        today = datetime.now().date()
        if today != self.day:
            self.day, self.tools_today = today, 0
        self.tools_today += 1

    def _limit_reset(self, now):
        """Time until which a full rate-limit window blocks work (or None)."""
        resets = [w["reset"] for w in self.limits.values()
                  if w["pct"] >= 100 and w["reset"] > now]
        return max(resets) if resets else None

    def _effective(self, s, now):
        st, age, quiet = s["state"], now - s["since"], now - s["updated"]
        if st == "working" and quiet > WORKING_STALE:
            return "idle"
        if st in ("done", "waiting", "ready", "error") and age > DONE_DECAY:
            return "idle"
        if st == "permission" and age > PERMISSION_DECAY:
            return "idle"
        if st == "limit":
            reset = self.limits.get("five_hour", {}).get("reset", 0)
            if (reset and reset < now and reset > s["since"]) or age > LIMIT_FALLBACK:
                return "idle"
        return st

    def view(self):
        now = time.time()
        with self.lock:
            for sid in [k for k, s in self.sessions.items() if now - s["updated"] > SESSION_FORGET]:
                del self.sessions[sid]
                self.feeling.forget(sid)
                self.context.pop(sid, None)
            eff = [(self._effective(s, now), sid, s) for sid, s in self.sessions.items()]
            counts = {}
            for st, _, _ in eff:
                counts[st] = counts.get(st, 0) + 1
            limit_reset = self._limit_reset(now)
            limits = {k: dict(v) for k, v in self.limits.items()}

            if eff:
                state, sid, s = min(eff, key=lambda e: (PRIORITY.index(e[0]), -e[2]["updated"]))
                s = dict(s)
            else:
                state, sid, s = "idle", "", {"project": "", "tool": "", "error": "", "since": 0}
            if limit_reset and state != "permission":
                state = "limit"
            tools_today = self.tools_today

            active = [k for st, k, _ in eff if st != "idle"]
            valence, energy = self.feeling.blend(sid, active, now, FOCUS_WEIGHT)
            mood = self._tint(state, sid, valence, counts.get("working", 0), now)
            pct5 = limits.get("five_hour", {}).get("pct")
            if mood in ("working", "flow", "juggling") and pct5 is not None and pct5 >= LIMIT_WARN_PCT:
                mood = "tired"
            if (mood in WORKING_MOODS and self.shown in WORKING_MOODS and mood != self.shown
                    and now - self.shown_since < MOOD_HOLD):
                mood = self.shown
            if mood != self.shown:
                self.shown, self.shown_since = mood, now
            feel = self.feeling.info(sid)
            context_pct = self.context.get(sid)

        life = self.life.summary(now)
        hour = datetime.fromtimestamp(now).hour
        battery = self.battery.state if self.battery else None
        if self.battery and self.battery.low() and state in CELEBRATE_OVER:
            mood = "lowbattery"
        elif now - life["level_up_at"] < LEVELUP_SHOW and state in CELEBRATE_OVER:
            mood = "levelup"
        elif state == "idle" and (life["idle_days"] or 0) >= HUNGRY_AFTER_DAYS:
            mood = "hungry"
        elif (state == "idle" and life["today"]["turns"]
              and SUMMARY_FROM_HOUR <= hour < SUMMARY_UNTIL_HOUR):
            mood = "summary"

        reset = limit_reset or (limits.get("five_hour", {}).get("reset") if state == "limit" else None)
        fill = {
            "tool": s.get("tool") or FILL_DEFAULTS["tool"],
            "error": s.get("error") or FILL_DEFAULTS["error"],
            "pct": int(pct5) if pct5 is not None else FILL_DEFAULTS["pct"],
            "reset": datetime.fromtimestamp(reset).strftime("%H:%M") if reset else FILL_DEFAULTS["reset"],
            "level": life["level"], "streak": life["streak"], "idle_days": life["idle_days"] or 0,
            "turns": life["today"]["turns"], "tools": life["today"]["tools"],
            "errors": life["today"]["errors"], "xp": life["today"]["xp"],
            "battery": battery["pct"] if battery else "?",
            "n": counts.get("working", 0), "commits": life["today"].get("commits", 0),
        }
        if mood == "stuck":
            fill["tool"] = feel["tool"] or fill["tool"]
        key = mood
        if mood == "proud":
            key = "proud_" + (feel["kind"] or "commit")
        if mood == "working" and s.get("tool") and (int(now // 20) % 2):
            key = "working_tool"
        if mood == "permission" and not s.get("tool"):
            key = "permission_notool"
        seed = datetime.fromtimestamp(now).date() if mood in ("summary", "hungry") else s.get("since")
        rng = random.Random(f"{sid}|{state}|{seed}|{key}|{life['level_up_at']}")
        message = rng.choice(MESSAGES[key]).format(**fill)

        return {
            "state": state, "mood": mood, "message": message,
            "project": s.get("project", ""), "counts": counts,
            "sessions": len(eff), "limits": limits, "tools_today": tools_today,
            "level": life["level"], "streak": life["streak"], "life": life,
            "battery": dict(battery) if battery else None,
            "feeling": {"valence": round(valence, 2), "energy": round(energy, 2)},
            "context_pct": context_pct,
            "props": (["wrench"] if context_pct is not None and context_pct >= CONTEXT_FULL_PCT
                      and mood in WORKING_MOODS | {"stuck"} else []),
        }

    def _tint(self, state, sid, valence, working, now):
        """The situation plus how it is going → the mood (see feeling.py)."""
        if state not in TINTABLE or not sid:
            return state
        f = self.feeling
        if state == "working" and f.stuck(sid):
            return "stuck"
        for kind in ("oops", "proud", "relieved"):
            if f.moment(sid, kind, now, MOMENT_SHOW):
                return kind
        tone = f.tone(sid, valence)
        if state != "working":
            return state
        if tone < 0:
            return "struggling"
        if working >= JUGGLING_FROM:
            return "juggling"
        return "flow" if tone > 0 else "working"
