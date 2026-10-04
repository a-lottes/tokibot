"""Stimmungen, Gesichter und Sprüche."""

# Höchste Priorität zuerst: Was dich am dringendsten braucht, gewinnt.
PRIORITY = ["limit", "permission", "waiting", "error", "working", "done", "ready", "idle"]

FACES = {
    "working":    ["( ◕‿◕)", "(◕‿◕ )", "( ◕‿◕)", "(✜‿‿✜)"],
    "tired":      ["( ≖‿≖)", "(≖‿≖ )"],          # arbeitet, aber das Limit naht
    "permission": ["(°▃▃°)", "(⊙▃▃⊙)"],
    "waiting":    ["( ⚆_⚆)", "(☉_☉ )"],
    "done":       ["(^‿‿^)", "(ᵔ◡◡ᵔ)"],
    "ready":      ["(◕‿‿◕)"],
    "error":      ["(☓‿‿☓)", "(╥☁╥ )"],
    "limit":      ["(-__-)", "(≖__≖)"],
    "idle":       ["(⇀‿‿↼)", "(≖‿‿≖)"],
    "offline":    ["(⇀‿‿↼)"],
}

# Sekunden pro Animationsbild (None = keine Animation)
ANIM_PERIOD = {"working": 7, "tired": 10, "waiting": 4, "permission": 3,
               "done": 15, "error": 12, "limit": 30, "idle": 45}

MESSAGES = {
    "working": ["Bin fleißig am Werkeln …", "Tipp, tipp, tipp …", "Läuft bei mir!",
                "Hmm, spannend …", "Ich mach das schon."],
    "working_tool": ["Jetzt: {tool}", "{tool} … läuft!", "Mit {tool} unterwegs"],
    "tired": ["Puh, {pct}% vom 5h-Kontingent weg …", "Wird knapp: {pct}%",
              "Ich werd müde … {pct}%"],
    "permission": ["Darf ich {tool}? Bitte!", "Freigabe für {tool}?", "Huch! Darf ich {tool}?"],
    "permission_notool": ["Darf ich? Bitte bitte!", "Ich brauche eine Freigabe!"],
    "waiting": ["Hallo-ho? Du bist dran!", "Ich warte auf dich …", "Brauche Input!",
                "Huhu! Frage an dich."],
    "done": ["Fertig! Schau mal rein.", "Erledigt ✓", "Tadaa! Fertig.", "Geschafft!"],
    "ready": ["Hallo! Was bauen wir?", "Bereit!", "Neue Session – juhu!"],
    "error": ["Autsch: {error}", "Oh nein … {error}", "Fehler: {error}"],
    "limit": ["Limit erreicht. zZz bis {reset}", "Akku leer … wieder fit {reset}",
              "Pause bis {reset}. Kaffee?"],
    "idle": ["zZz …", "Weck mich mit Arbeit.", "Langweilig …", "Träume von Tokens …"],
    "offline": ["offline – bis später!"],
}

ERROR_LABELS = {
    "overloaded": "überlastet", "server_error": "Serverfehler",
    "authentication_failed": "Login weg", "billing_error": "Abrechnung",
    "account_on_hold": "Konto pausiert", "invalid_request": "ungültige Anfrage",
    "model_not_found": "Modell fehlt", "max_output_tokens": "Antwort zu lang",
    "oauth_org_not_allowed": "Org gesperrt", "cloud_credential_error": "Cloud-Login",
    "unknown": "unbekannt",
}

WORKING_EVENTS = {
    "UserPromptSubmit", "UserPromptExpansion", "PreToolUse", "PostToolUse",
    "PostToolUseFailure", "PostToolBatch", "SubagentStart", "SubagentStop",
    "PreCompact", "PostCompact", "TaskCreated", "TaskCompleted",
}
WAITING_NOTIFICATIONS = {"idle_prompt", "agent_needs_input", "elicitation_dialog",
                         "elicitation_url_dialog"}

# Zeitlimits, nach denen ein Zustand "verblasst"
WORKING_STALE = 10 * 60      # arbeitet angeblich, aber 10 min nichts gehört → idle
DONE_DECAY = 20 * 60         # fertig/wartet seit 20 min → idle (du bist wohl weg)
PERMISSION_DECAY = 60 * 60
LIMIT_FALLBACK = 5 * 3600
SESSION_FORGET = 6 * 3600
LIMIT_WARN_PCT = 80

