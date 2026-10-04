"""Moods, timing and the lines the critter says.

All display strings live here so they can be translated later (i18n).
"""

# Highest priority first: whatever needs you most urgently wins.
PRIORITY = ["limit", "permission", "waiting", "error", "working", "done", "ready", "idle"]

# Seconds per animation frame (missing = no animation)
ANIM_PERIOD = {"working": 3, "tired": 6, "waiting": 4, "permission": 2,
               "done": 5, "error": 6, "limit": 20, "idle": 8, "ready": 6}

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
LABELS = {"session": "session", "sessions": "sessions", "tools_today": "{n} tools today"}

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
