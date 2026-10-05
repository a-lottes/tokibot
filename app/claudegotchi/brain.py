"""The brain: folds all Claude Code sessions into a single mood."""
import random
import threading
import time
from datetime import datetime

from .life import Life
from .mood import (BADGES, DONE_DECAY, ERROR_LABELS, FILL_DEFAULTS, HUNGRY_AFTER_DAYS, LABELS,
                   LEVELUP_SHOW, LIMIT_FALLBACK, LIMIT_WARN_PCT, MESSAGES, PERMISSION_DECAY,
                   PRIORITY, SESSION_FORGET, SOCIAL_SHOW, SUMMARY_FROM_HOUR, SUMMARY_UNTIL_HOUR,
                   WAITING_NOTIFICATIONS, WORKING_EVENTS, WORKING_STALE)

# Moods a level-up celebration may cover; anything that needs you wins over it.
CELEBRATE_OVER = {"working", "done", "ready", "idle", "error"}


class Brain:
    def __init__(self, life=None, social=None, battery=None):
        self.life = life or Life()
        self.social = social          # social.Social, or None when Bluetooth social is off
        self.battery = battery        # battery.BatteryMonitor, or None without a battery
        self.lock = threading.Lock()
        self.sessions = {}
        self.limits = {}          # {"five_hour": {"pct":.., "reset":..}, ...}
        self.tools_today = 0
        self.day = datetime.now().date()
        self.address = ""         # e.g. claudegotchi-3f2a.local, shown until a client talks to us
        self.heard = False

    def handle_hook(self, ev):
        name = ev.get("hook_event_name", "")
        sid = str(ev.get("session_id") or "unknown")
        ts = float(ev.get("ts") or time.time())
        now = time.time()
        self.heard = True
        self.life.record(name, ev, now)
        with self.lock:
            if name == "SessionEnd":
                self.sessions.pop(sid, None)
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
        self.heard = True
        with self.lock:
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

        pct5 = limits.get("five_hour", {}).get("pct")
        mood = state
        if state == "working" and pct5 is not None and pct5 >= LIMIT_WARN_PCT:
            mood = "tired"

        life = self.life.summary(now)
        hour = datetime.fromtimestamp(now).hour
        soc = {"nearby": 0, "friends_nearby": [], "event": None, "invite": None}
        if self.social:
            self.social.my_mood = mood
            soc = self.social.view(now)
        event = soc["event"] or {}
        celebrate = state in CELEBRATE_OVER
        battery = self.battery.state if self.battery else None
        if self.battery and self.battery.low() and celebrate:
            mood = "lowbattery"
        elif now - life["level_up_at"] < LEVELUP_SHOW and celebrate:
            mood = "levelup"
        elif event.get("kind") == "newfriend" and celebrate:
            mood = "newfriend"
        elif soc["invite"] and celebrate:
            mood = "invite"
        elif now - life["badge_at"] < SOCIAL_SHOW["badge"] and celebrate:
            mood = "badge"
        elif event.get("kind") in ("encounter", "encounter_anon", "friend") and celebrate:
            mood = "friend" if event["kind"] == "friend" else "encounter"
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
            "peer": soc["invite"] if mood == "invite" else (event.get("name") or LABELS["stranger"]),
            "peer_level": event.get("level") or "?",
            "badge": BADGES.get(life["last_badge"], ("?",))[0],
            "battery": battery["pct"] if battery else "?",
            "address": self.address,
        }
        key = mood
        if mood == "encounter" and event.get("kind") == "encounter_anon":
            key = "encounter_anon"
        if mood == "working" and s.get("tool") and (int(now // 20) % 2):
            key = "working_tool"
        if mood == "permission" and not s.get("tool"):
            key = "permission_notool"
        if mood == "idle" and not self.heard and self.address:
            key = "address"           # nobody has talked to us yet: say where to find us
        seed = datetime.fromtimestamp(now).date() if mood in ("summary", "hungry") else s.get("since")
        if mood in ("encounter", "friend", "newfriend"):
            seed = event.get("at")
        rng = random.Random(f"{sid}|{state}|{seed}|{key}|{life['level_up_at']}")
        message = rng.choice(MESSAGES[key]).format(**fill)

        return {
            "state": state, "mood": mood, "message": message,
            "project": s.get("project", ""), "counts": counts,
            "sessions": len(eff), "limits": limits, "tools_today": tools_today,
            "level": life["level"], "streak": life["streak"], "life": life,
            "nearby": soc["nearby"], "friends_nearby": len(soc["friends_nearby"]),
            "accessory": self.social.accessory() if self.social else "none",
            "battery": dict(battery) if battery else None,
        }

