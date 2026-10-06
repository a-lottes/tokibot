"""Feelings: how the work in each session is going, not just what is happening.

Every signal (a tool failing, tests turning green, a commit, the user interrupting)
adds an impulse to two numbers that fade over time:

  valence  -1 … 1   going badly … going well
  energy    0 … 1   calm … busy

The brain uses them to tint the situation (working → flow, struggling, stuck …).
Kept in memory only; the long-term memory is life.py.
"""
import math
import re

from .mood import (ENERGY_HALF_LIFE, FIXED_WITHIN, IMPULSES, STUCK_AFTER, TONE_ENTER,
                   TONE_LEAVE, VALENCE_HALF_LIFE)

# MCP tools that open a pull request, e.g. mcp__github__create_pull_request
PR_TOOL = re.compile(r"create_pull_request|create_merge_request", re.I)
KEEP_IMPULSES = 64


def _new():
    return {"impulses": [], "streak_tool": "", "streak": 0, "clean": True,
            "test_red_at": 0.0, "tone": 0, "moments": {}}


class Feeling:
    def __init__(self):
        self.sessions = {}

    def forget(self, sid):
        self.sessions.pop(sid, None)

    def record(self, sid, ev, now):
        """Feed one hook event (as sent by the client). Returns the signals it produced."""
        f = self.sessions.setdefault(sid, _new())
        name = ev.get("hook_event_name", "")
        tool = ev.get("tool_name", "")
        signals = set(ev.get("signals") or ())
        if tool and PR_TOOL.search(tool):
            signals.add("pr")
        out = []

        if name == "UserPromptSubmit":
            f["clean"], f["streak"], f["streak_tool"] = True, 0, ""
        elif name == "PreToolUse":
            out.append("tool")
        elif name == "PostToolUseFailure":
            f["clean"] = False
            if ev.get("interrupt"):
                out.append("interrupt")
                f["moments"]["oops"] = now
            else:
                out.append("test_failed" if "test" in signals else "tool_failed")
                if "test" in signals:
                    f["test_red_at"] = now
                f["streak"] = f["streak"] + 1 if tool == f["streak_tool"] else 1
                f["streak_tool"] = tool
                if f["streak"] == STUCK_AFTER:
                    out.append("stuck")
        elif name == "PostToolUse":
            if tool == f["streak_tool"]:
                f["streak"], f["streak_tool"] = 0, ""
            if "test" in signals:
                if f["test_red_at"] and now - f["test_red_at"] < FIXED_WITHIN:
                    out.append("test_fixed")
                    f["moments"]["relieved"] = now
                else:
                    out.append("test_passed")
                f["test_red_at"] = 0.0
            landed = [kind for kind in ("pr", "push", "commit") if kind in signals]
            if landed:
                out.extend(landed)
                f["moments"]["proud"] = now
                f["proud_kind"] = landed[0]     # celebrate the biggest one
        elif name == "Stop":
            if f["clean"]:
                out.append("clean_turn")
            f["streak"], f["streak_tool"] = 0, ""
        elif name == "StopFailure" and ev.get("error_type") != "rate_limit":
            out.append("api_error")
        elif name == "PreCompact" and ev.get("trigger") == "auto":
            out.append("auto_compact")

        for sig in out:
            v, e = IMPULSES[sig]
            f["impulses"].append((now, v, e))
        del f["impulses"][:-KEEP_IMPULSES]
        return out

    # --- reading ---------------------------------------------------------------

    def _sum(self, f, now, idx, half_life):
        return sum(imp[idx] * 0.5 ** (max(0.0, now - imp[0]) / half_life) for imp in f["impulses"])

    def valence(self, sid, now):
        f = self.sessions.get(sid)
        return math.tanh(self._sum(f, now, 1, VALENCE_HALF_LIFE)) if f else 0.0

    def energy(self, sid, now):
        f = self.sessions.get(sid)
        return min(1.0, max(0.0, self._sum(f, now, 2, ENERGY_HALF_LIFE))) if f else 0.0

    def blend(self, focus, sids, now, weight):
        """Valence and energy with the shown session counting `weight`, the rest sharing the remainder."""
        others = [s for s in sids if s != focus]
        if focus not in self.sessions or not others:
            pool = [focus] if focus in self.sessions else others
            if not pool:
                return 0.0, 0.0
            return (sum(self.valence(s, now) for s in pool) / len(pool),
                    sum(self.energy(s, now) for s in pool) / len(pool))
        ov = sum(self.valence(s, now) for s in others) / len(others)
        oe = sum(self.energy(s, now) for s in others) / len(others)
        return (weight * self.valence(focus, now) + (1 - weight) * ov,
                weight * self.energy(focus, now) + (1 - weight) * oe)

    def tone(self, sid, valence):
        """-1, 0 or 1 with hysteresis: a tone starts beyond ±TONE_ENTER, ends inside ±TONE_LEAVE."""
        f = self.sessions.setdefault(sid, _new())
        t = f["tone"]
        if valence >= TONE_ENTER:
            t = 1
        elif valence <= -TONE_ENTER:
            t = -1
        elif abs(valence) < TONE_LEAVE:
            t = 0
        f["tone"] = t
        return t

    def stuck(self, sid):
        f = self.sessions.get(sid)
        return bool(f and f["streak"] >= STUCK_AFTER)

    def moment(self, sid, kind, now, within):
        f = self.sessions.get(sid)
        at = f["moments"].get(kind, 0) if f else 0
        return bool(at and now - at < within)

    def info(self, sid):
        f = self.sessions.get(sid) or {}
        return {"tool": f.get("streak_tool", ""), "kind": f.get("proud_kind", "")}
