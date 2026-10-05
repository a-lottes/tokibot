"""Moods, timing and the lines the critter says.

All display strings live here so they can be translated later (i18n).
"""

# Highest priority first: whatever needs you most urgently wins.
PRIORITY = ["limit", "permission", "waiting", "error", "working", "done", "ready", "idle"]

# Seconds per animation frame (missing = no animation)
ANIM_PERIOD = {"working": 3, "tired": 6, "waiting": 4, "permission": 2,
               "done": 5, "error": 6, "limit": 20, "idle": 8, "ready": 6,
               "levelup": 2, "summary": 10, "hungry": 7,
               "encounter": 2, "friend": 3, "newfriend": 2, "invite": 3, "badge": 2, "lowbattery": 5}

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
    # social (see social.py)
    "encounter": ["Ooh, a gotchi! Hi {peer}!", "Hello {peer}! (Lv{peer_level})",
                  "Someone's here: {peer}!"],
    "encounter_anon": ["Ooh, another gotchi nearby!", "Psst, a gotchi! Lv{peer_level}.",
                       "I'm not alone! Hello there!"],
    "friend": ["{peer} is here! Hi friend!", "Look, it's {peer}!", "Yay, {peer}!"],
    "newfriend": ["{peer} and I are friends now!", "New friend: {peer}! ♥",
                  "Best day ever: {peer} is my friend!"],
    "invite": ["{peer} wants to be friends! Say yes on the social page.",
               "A friend request from {peer}!"],
    "badge": ["New badge: {badge}!", "I earned a badge: {badge}!"],
    "lowbattery": ["Battery at {battery}% … plug me in?", "Running low: {battery}%",
                   "Feeling weak … {battery}% left."],
    "battery_off": ["Battery empty. Good night!"],
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
          "tools_streak_short": "{streak}-day streak", "level": "Lv{level}",
          "stranger": "a gotchi"}

# Experience per hook event (the critter's life, see life.py)
XP_FOR = {"Stop": 10, "SessionStart": 3, "PreToolUse": 1, "TaskCompleted": 5}
LEVELUP_SHOW = 90            # celebrate a level-up for this many seconds
SUMMARY_FROM_HOUR = 18       # when idle after this hour, show the day's tally instead of zZz
SUMMARY_UNTIL_HOUR = 23
HUNGRY_AFTER_DAYS = 2        # no work for this many days → hungry

# --- social: encounters, friends, badges (social.py) ---------------------------
XP_SOCIAL = {
    "meet_new": 20,          # a gotchi you never met before (its card was seen)
    "meet_again": 5,         # a known gotchi or friend, first time today
    "meet_anon": 2,          # a gotchi that does not show its card
    "new_friend": 30,
}
SOCIAL_XP_PER_DAY = 100      # cap for encounter XP per day (friendships are not capped)
COWORK_BONUS = 0.10          # +10 % XP while a friend nearby is working too
SOCIAL_SHOW = {"encounter": 60, "friend": 45, "newfriend": 120, "badge": 90}

# Badges: key -> (title, how to get it)
BADGES = {
    "first_meet": ("Hello world", "Meet another gotchi"),
    "first_friend": ("First friend", "Become friends with a gotchi"),
    "five_friends": ("Social butterfly", "Have 5 friends"),
    "ten_friends": ("Popular", "Have 10 friends"),
    "conference": ("Conference", "5 gotchis nearby at once"),
    "coworking": ("Co-working", "Work while a friend nearby works too"),
    "night_owl": ("Night owl", "Finish a reply between midnight and 4 am"),
    "streak_7": ("On a roll", "A 7-day streak"),
}

# Accessories for the critter: key -> (label, unlocked by a badge or "level:N")
ACCESSORIES = {
    "none": ("None", ""),
    "cap": ("Cap", "level:3"),
    "bow": ("Bow", "first_friend"),
    "glasses": ("Glasses", "coworking"),
    "headphones": ("Headphones", "level:5"),
    "nightcap": ("Night cap", "night_owl"),
    "party": ("Party hat", "conference"),
    "crown": ("Crown", "ten_friends"),
}

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
