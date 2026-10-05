"""Moods, timing and the lines the critter says.

All display strings live here so they can be translated later (i18n).
"""

# Highest priority first: whatever needs you most urgently wins.
PRIORITY = ["limit", "permission", "waiting", "error", "working", "done", "ready", "idle"]
# The feeling layer then tints working/done/ready/idle (brain._tint), most pressing first:
# stuck, oops, proud, relieved, then for working: struggling, juggling, flow.

# Seconds per animation frame (missing = no animation)
ANIM_PERIOD = {"working": 3, "tired": 6, "waiting": 4, "permission": 2,
               "done": 5, "error": 6, "limit": 20, "idle": 8, "ready": 6,
               "levelup": 2, "summary": 10, "hungry": 7, "lowbattery": 5,
               "flow": 4, "struggling": 5, "stuck": 3, "oops": 3, "juggling": 2, "proud": 2,
               "relieved": 5}

MESSAGES = {
    "working": ["Busy building …", "Tap tap tap …", "On it!", "Hmm, interesting …",
                "Leave it to me."],
    "working_tool": ["Now: {tool}", "{tool} running …", "Busy with {tool}"],
    "tired": ["Phew, {pct}% of my 5h budget used …", "Getting tight: {pct}%",
              "Getting sleepy … {pct}%"],
    "permission": ["May I use {tool}? Please!", "Approve {tool}?", "Oh! Can I run {tool}?"],
    "permission_notool": ["May I? Pretty please!", "I need your approval!"],
    "waiting": ["Hello? Your turn!", "Waiting for you …", "Need your input!",
                "Psst! A question for you."],
    "done": ["Done! Take a look.", "All done ✓", "Ta-da! Finished.", "Nailed it!"],
    "ready": ["Hi! What are we building?", "Ready!", "New session, yay!"],
    "error": ["Ouch: {error}", "Oh no … {error}", "Error: {error}"],
    "limit": ["Limit reached. zZz until {reset}", "Out of juice … back at {reset}",
              "Break until {reset}. Coffee?"],
    "idle": ["zZz …", "Wake me with work.", "Bored …", "Dreaming of tokens …"],
    "offline": ["Offline. See you!"],
    "levelup": ["Level up! I'm level {level} now!", "Woohoo, level {level}!",
                "I grew! Level {level}."],
    "summary": ["Today: {turns} tasks, {tools} tools, {errors} errors. Streak: {streak} days.",
                "Good day! {turns} tasks done, {xp} XP earned.",
                "Day's tally: {turns} tasks, {tools} tools. Level {level}."],
    "hungry": ["I'm hungry … feed me some code?", "{idle_days} days without code. *stomach growls*",
               "Did you forget me? Let's build something!"],
    "lowbattery": ["Battery at {battery}% … plug me in?", "Running low: {battery}%",
                   "Feeling weak … {battery}% left."],
    "battery_off": ["Battery empty. Good night!"],
    "flow": ["In the zone.", "Everything clicks!", "Smooth sailing.", "We're on a roll!"],
    "struggling": ["This one is tricky …", "Hmm, not my best moment.", "Bear with me …",
                   "Working through it."],
    "stuck": ["{tool} keeps failing …", "Going in circles with {tool}.", "Stuck on {tool}. Help?"],
    "oops": ["Oops, wrong way? Tell me.", "Stopped! What did I miss?", "Sorry, let's rethink."],
    "juggling": ["Juggling {n} sessions!", "{n} things at once!", "So many tabs: {n}!"],
    "proud_commit": ["Committed! {commits} today.", "Saved in history ✓", "Another commit!"],
    "proud_push": ["Pushed! It's out there.", "Off it goes ✓", "Pushed to the remote!"],
    "proud_pr": ["Pull request opened!", "PR is up. Review time!", "Look, a fresh PR!"],
    "relieved": ["Green again. Phew!", "Tests pass now ✓", "Fixed it!"],
}

# Fallbacks for the {placeholders} above
FILL_DEFAULTS = {"tool": "something", "error": "?", "pct": "?", "reset": "the reset"}

ERROR_LABELS = {
    "overloaded": "overloaded", "server_error": "server error",
    "authentication_failed": "logged out", "billing_error": "billing",
    "account_on_hold": "account on hold", "invalid_request": "bad request",
    "model_not_found": "model missing", "max_output_tokens": "reply too long",
    "oauth_org_not_allowed": "org blocked", "cloud_credential_error": "cloud login",
    "unknown": "unknown",
}

# Labels on the display
LABELS = {"session": "session", "sessions": "sessions", "tools_today": "{n} tools today",
          "tools_streak": "{n} tools · {streak}d streak",
          "tools_streak_short": "{streak}-day streak", "level": "Lv{level}"}

# Experience per hook event (the critter's life, see life.py)
XP_FOR = {"Stop": 10, "SessionStart": 3, "PreToolUse": 1, "TaskCompleted": 5}
LEVELUP_SHOW = 90            # celebrate a level-up for this many seconds
SUMMARY_FROM_HOUR = 18       # when idle after this hour, show the day's tally instead of zZz
SUMMARY_UNTIL_HOUR = 23
HUNGRY_AFTER_DAYS = 2        # no work for this many days → hungry

# Feelings (see feeling.py): how the work is going, on top of what is happening.
# Impulses per signal: (valence, energy). Valence fades with a 10 min half-life, energy with 3 min.
IMPULSES = {
    "tool_failed": (-0.15, 0.05), "stuck": (-0.4, 0.0), "interrupt": (-0.5, 0.0),
    "test_failed": (-0.3, 0.05), "test_fixed": (0.6, 0.1), "test_passed": (0.2, 0.05),
    "commit": (0.4, 0.1), "push": (0.5, 0.1), "pr": (0.7, 0.1),
    "clean_turn": (0.15, 0.0), "api_error": (-0.3, 0.0), "auto_compact": (-0.1, 0.0),
    "tool": (0.0, 0.03),
}
VALENCE_HALF_LIFE = 10 * 60
ENERGY_HALF_LIFE = 3 * 60
TONE_ENTER, TONE_LEAVE = 0.4, 0.25   # hysteresis, so the e-ink face does not flicker
STUCK_AFTER = 3              # the same tool failing this many times in a row
FIXED_WITHIN = 30 * 60       # tests passing this soon after failing count as "fixed"
MOMENT_SHOW = 2 * 60         # proud, relieved and oops last this long
MOOD_HOLD = 30               # a tint stays at least this long
JUGGLING_FROM = 3            # working sessions at once
CONTEXT_FULL_PCT = 85        # context this full → the critter carries a wrench
FOCUS_WEIGHT = 0.7           # the shown session's share of the feeling; the rest share 0.3
XP_FOR_SIGNAL = {"commit": 5, "push": 8, "pr": 15}

# Battery (PiSugar, see battery.py)
BATTERY_LOW = 15             # below this, without power, the critter asks to be plugged in
BATTERY_POLL = 20            # seconds between battery readings

WORKING_EVENTS = {
    "UserPromptSubmit", "UserPromptExpansion", "PreToolUse", "PostToolUse",
    "PostToolUseFailure", "PostToolBatch", "SubagentStart", "SubagentStop",
    "PreCompact", "PostCompact", "TaskCreated", "TaskCompleted",
}
WAITING_NOTIFICATIONS = {"idle_prompt", "agent_needs_input", "elicitation_dialog",
                         "elicitation_url_dialog"}

# After these times a state "fades"
WORKING_STALE = 10 * 60      # claims to be working, but nothing heard for 10 min → idle
DONE_DECAY = 20 * 60         # done/waiting for 20 min → idle (you are probably away)
PERMISSION_DECAY = 60 * 60
LIMIT_FALLBACK = 5 * 3600
SESSION_FORGET = 6 * 3600
LIMIT_WARN_PCT = 80
