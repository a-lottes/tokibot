#!/usr/bin/env python3
"""Tokibot client for Claude Code and other coding harnesses (Mac/Linux/Windows).

  tokibot_client.py hook        as a Claude Code hook: report the event to the gotchi
  tokibot_client.py hook --harness codex [--event NAME]
                                     the same for another harness: codex, copilot, gemini,
                                     cursor or devin (see ADAPTERS; install.py sets this up)
  tokibot_client.py statusline  as the status line: report limits and print a status line
  tokibot_client.py test        send a test sequence to the gotchi
  tokibot_client.py pair [NAME]  pair with your gotchi: over the USB cable, or by the
                                     name it shows on screen (tokibot-xxxx)

Transport: straight to the gotchi over HTTP (USB cable or Wi-Fi), and/or through a
relay (an ntfy topic) when "relay" is set. The relay is for Claude Code running in the
cloud (e.g. Claude Projects), which cannot reach a gotchi on your local network.

Which gotchi: every gotchi has its own name, tokibot-xxxx. The client sends it
along, so a gotchi that is not yours (a friend's on the same Wi-Fi) refuses the event.
With url "auto" the client tries the USB cable first, then <name>.local over Wi-Fi. It
learns the name the first time it reaches a gotchi over USB, or from "pair".

Sends metadata only (event name, harness, session ID, project folder name, tool name,
notification/error type, limit and context percentages, token counts, and a few
categories such as "a test run failed" or "a commit succeeded"), never prompts, code,
commands or replies. Token counts are the critter's food; they are read from the
harness's own session log on this computer (numbers only).
Never blocks Claude Code: sending happens in a detached background process.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
KEEP = ("hook_event_name", "session_id", "notification_type", "error_type",
        "tool_name", "source", "reason", "trigger")

# Shell commands are classified here, on this machine; only the category is sent.
# A match must start a command (start of line, or after ; & | or a run wrapper).
START = r"(?:^|[;&|(]\s*)(?:\w+=\S*\s+)*(?:(?:uv|poetry|pipenv|pdm|hatch)\s+run\s+|npx\s+|bunx\s+|time\s+)?"
GIT = r"git\s+(?:-C\s+\S+\s+|-c\s+\S+\s+)*"
SIGNALS = (
    ("pr", re.compile(START + r"gh\s+pr\s+create\b", re.M)),
    ("push", re.compile(START + GIT + r"push\b", re.M)),
    ("commit", re.compile(START + GIT + r"commit\b", re.M)),
    ("test", re.compile(START + (
        r"(?:pytest|py\.test|tox|nox|jest|vitest|mocha|rspec|phpunit|ctest|"
        r"python3?\s+-m\s+(?:pytest|unittest)|go\s+test|cargo\s+test|dotnet\s+test|swift\s+test|"
        r"mix\s+test|mvn\s+(?:-\S+\s+)*test|(?:\./)?gradlew?\s+test|"
        r"(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?test|make\s+(?:test|check))\b"), re.M)),
)
SHELL_TOOLS = {"Bash", "PowerShell"}


def classify(command):
    """Categories of a shell command, e.g. ["commit", "push"]."""
    return [name for name, rx in SIGNALS if rx.search(command or "")]


# "auto": try the USB cable first, then the paired gotchi's name over Wi-Fi.
USB_URL = "http://192.168.77.1:8765"
PORT = 8765
# As a Claude Code plugin the client lives in the plugin cache, which is replaced on
# every update; keep the little state it writes in the plugin's data folder instead.
STATE_DIR = os.environ.get("CLAUDE_PLUGIN_DATA") or HERE
LAST_URL = os.path.join(STATE_DIR, "last_url")
LEARNED = os.path.join(STATE_DIR, "gotchi")     # name learned on first contact over USB
# Where install.py keeps the settings; the plugin reads them from there as well.
INSTALLED_CFG = os.path.expanduser("~/.tokibot/tokibot.json")
# Before the rename (Claudegotchi) the settings lived here; still read if nothing newer is set
LEGACY_CFG = os.path.expanduser("~/.claude/claudegotchi/claudegotchi.json")


def load_config():
    cfg = {"url": "auto", "token": "", "relay": "", "gotchi": "", "statusline_chain": "",
           "harnesses": []}
    for path in dict.fromkeys((LEGACY_CFG, INSTALLED_CFG, os.path.join(HERE, "tokibot.json"))):
        try:
            with open(path) as f:
                cfg.update(json.load(f))
        except (OSError, ValueError):
            pass
    # Options set in the plugin's settings (/config) win over the file, if they are set
    for key in ("url", "token", "relay", "gotchi"):
        value = os.environ.get("CLAUDE_PLUGIN_OPTION_" + key.upper(), "").strip()
        if value:
            cfg[key] = value
    cfg["url"] = env("URL", cfg["url"]).rstrip("/")
    cfg["token"] = env("TOKEN", cfg["token"])
    cfg["relay"] = env("RELAY", cfg["relay"]).rstrip("/")
    cfg["gotchi"] = env("GOTCHI", cfg["gotchi"]) or read_state(LEARNED)
    return cfg


def env(key, default):
    """$TOKIBOT_<key>, or $CLAUDEGOTCHI_<key> from before the rename."""
    return os.environ.get("TOKIBOT_" + key) or os.environ.get("CLAUDEGOTCHI_" + key) or default


def read_state(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def write_state(path, value):
    try:
        with open(path, "w") as f:
            f.write(value)
    except OSError:
        pass


def candidates(cfg):
    if cfg["url"] in ("", "none"):              # relay only
        return []
    if cfg["url"] != "auto":
        return [cfg["url"]]
    urls = [USB_URL]
    if cfg.get("gotchi"):
        urls.append(f"http://{cfg.get('gotchi')}.local:{PORT}")
    try:
        with open(LAST_URL) as f:
            last = f.read().strip()
        if last in urls:                       # last working address first
            urls.remove(last)
            urls.insert(0, last)
    except OSError:
        pass
    return urls


def post(cfg, path, payload, timeout=3):
    """Send straight to the gotchi; returns the URL that worked."""
    urls = candidates(cfg)
    if not urls:
        raise OSError("no direct address configured (url = none)")
    body = json.dumps(payload).encode()
    for i, url in enumerate(urls):
        req = urllib.request.Request(url + path, data=body, headers=headers(cfg), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp.read()
                name = (resp.headers.get("X-Tokibot-Gotchi")
                        or resp.headers.get("X-Claudegotchi-Gotchi") or "")
        except Exception:
            if i == len(urls) - 1:
                raise
            continue
        if cfg["url"] == "auto":
            if i > 0:
                write_state(LAST_URL, url)
            if not cfg.get("gotchi") and url == USB_URL and name:
                write_state(LEARNED, name)         # the gotchi on the cable is yours
        return url


def headers(cfg):
    h = {"Content-Type": "application/json"}
    if cfg["token"]:
        h["X-Tokibot-Token"] = h["X-Claudegotchi-Token"] = cfg["token"]   # old name: older gotchis
    if cfg.get("gotchi"):
        h["X-Tokibot-Gotchi"] = h["X-Claudegotchi-Gotchi"] = cfg.get("gotchi")
    return h


def publish(cfg, path, payload, timeout=5):
    """Send through the relay: one ntfy message whose body is our JSON envelope.
    The gotchi subscribes to the same topic and checks the token."""
    # "claudegotchi": gotchis from before the rename only look for that key
    envelope = {"tokibot": 1, "claudegotchi": 1, "path": path, "token": cfg["token"], "data": payload}
    req = urllib.request.Request(cfg["relay"], data=json.dumps(envelope).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=timeout).read()
    return cfg["relay"]


def send(cfg, path, payload, timeout=3):
    """Relay and direct path; succeeds if at least one of them worked."""
    payload.setdefault("id", uuid.uuid4().hex[:12])    # lets the gotchi drop duplicates
    done, err = [], None
    for fn in ((publish,) if cfg["relay"] else ()) + ((post,) if candidates(cfg) else ()):
        try:
            done.append(fn(cfg, path, payload, timeout))
        except Exception as e:
            err = e
    if not done:
        raise err or OSError("neither url nor relay is configured")
    return ", ".join(done)


def post_detached(cfg, path, payload, prepare=None):
    """Detach and send in the background; the caller returns immediately.
    `prepare` runs first in the background too (e.g. reading token counts)."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        if os.fork():
            return
    except (OSError, AttributeError):          # no fork (e.g. Windows): send with a short timeout
        try:
            if prepare:
                prepare()
            send(cfg, path, payload, timeout=0.5)
        except Exception:
            pass
        return
    try:
        os.setsid()
        devnull = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(devnull, fd)
        if prepare:
            try:
                prepare()
            except Exception:
                pass
        send(cfg, path, payload)
        if path == "/hook" and payload.get("hook_event_name") in SCORE_EVENTS:
            share_score(cfg)
    except Exception:
        pass
    finally:
        os._exit(0)


# --- highscores: post the gotchi's signed score card for it ------------------------
# A gotchi with Wi-Fi posts its card itself. One that only hangs on the USB cable has
# no internet, so the client fetches the card (signed on the gotchi) and posts it.
SCORE_STATE = os.path.join(STATE_DIR, "score_at")
SCORE_EVENTS = {"Stop", "SessionEnd"}
SCORE_EVERY = 3600


def share_score(cfg, now=None, timeout=3):
    """At most once an hour. Returns True when a card was posted."""
    now = now or time.time()
    try:
        last = float(read_state(SCORE_STATE) or 0)
    except ValueError:
        last = 0
    if now - last < SCORE_EVERY:
        return False
    write_state(SCORE_STATE, str(now))       # also when highscores are off: ask hourly at most
    for url in candidates(cfg):
        req = urllib.request.Request(url + "/score", headers=headers(cfg))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read())
        except Exception:
            continue                         # off (404) or not reachable here
        target = body.pop("post_to", "")
        if not str(target).startswith("https://"):
            return False
        req = urllib.request.Request(target, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
        return True
    return False


# --- harnesses -------------------------------------------------------------------
# The gotchi speaks Claude Code's hook vocabulary. Each adapter translates one harness:
#   events  its event name → Claude Code's (None: ignore the event)
#   tools   its tool names → Claude Code's, so shell commands are recognised everywhere
#   json    the harness wants JSON on stdout (an empty object is fine)
ADAPTERS = {
    "claude": {"events": {}, "tools": {}},
    # Codex uses Claude Code's names and payloads already
    "codex": {"events": {}, "tools": {"shell": "Bash", "exec_command": "Bash", "local_shell": "Bash"}},
    # Copilot CLI: PascalCase events get Claude-style payloads; the camelCase-only ones do not
    "copilot": {"events": {"agentStop": "Stop", "errorOccurred": "StopFailure",
                           "permissionRequest": "PermissionRequest", "preCompact": "PreCompact",
                           "subagentStart": "SubagentStart", "subagentStop": "SubagentStop",
                           "notification": None},
                "tools": {"bash": "Bash", "shell": "Bash", "powershell": "PowerShell"}},
    "gemini": {"events": {"BeforeAgent": "UserPromptSubmit", "AfterAgent": "Stop",
                          "BeforeTool": "PreToolUse", "AfterTool": "PostToolUse",
                          "Notification": "PermissionRequest", "PreCompress": "PreCompact",
                          "BeforeModel": None, "AfterModel": None, "BeforeToolSelection": None},
               "tools": {"run_shell_command": "Bash"}, "json": True},
    "cursor": {"events": {"sessionStart": "SessionStart", "sessionEnd": "SessionEnd",
                          "beforeSubmitPrompt": "UserPromptSubmit", "preToolUse": "PreToolUse",
                          "postToolUse": "PostToolUse", "postToolUseFailure": "PostToolUseFailure",
                          "subagentStart": "SubagentStart", "subagentStop": "SubagentStop",
                          "preCompact": "PreCompact", "stop": "Stop"},
               "tools": {"Shell": "Bash"}, "json": True},
    # Devin Desktop (formerly Windsurf) Cascade hooks
    "devin": {"events": {"pre_user_prompt": "UserPromptSubmit", "pre_run_command": "PreToolUse",
                         "post_run_command": "PostToolUse", "pre_write_code": "PreToolUse",
                         "post_write_code": "PostToolUse", "pre_mcp_tool_use": "PreToolUse",
                         "post_mcp_tool_use": "PostToolUse", "post_cascade_response": "Stop"},
              "tools": {}},
    # Kiro CLI: 3.0 triggers are Claude Code's names; older agent-config hooks are camelCase
    "kiro": {"events": {"agentSpawn": "SessionStart", "promptSubmit": "UserPromptSubmit",
                        "userPromptSubmit": "UserPromptSubmit", "preToolUse": "PreToolUse",
                        "postToolUse": "PostToolUse", "agentStop": "Stop", "stop": "Stop"},
             "tools": {"execute_bash": "Bash", "executeBash": "Bash", "shell": "Bash"}},
    # Cline: one hook per script; the payload names the hook and nests the details
    "cline": {"events": {"TaskStart": "SessionStart", "TaskResume": "SessionStart",
                         "TaskCancel": "Stop", "TaskComplete": "Stop"},
              "tools": {"execute_command": "Bash"}, "reply": '{"cancel": false}'},
    # OpenCode and Amp: our plugins (written by install.py) send Claude Code's names already
    "opencode": {"events": {}, "tools": {"bash": "Bash", "edit": "Edit", "write": "Write",
                                         "read": "Read"}},
    "amp": {"events": {}, "tools": {"Bash": "Bash", "shell_command": "Bash"}},
}
# Harnesses whose own plugin sends token counts along (see install.py PLUGINS)
TOKENS_IN_PAYLOAD = {"opencode"}
# Events after which the session log is read for new token counts
FEED_EVENTS = {"Stop", "SubagentStop", "StopFailure", "SessionEnd", "PreCompact"}


def adapt(harness, data, event="", cfg=None):
    """One harness payload → (event for the gotchi, shell command or "") or None to drop it."""
    cfg = cfg or {}
    if harness == "claude" and data.get("cursor_version"):
        # Cursor also runs the Claude Code hooks from ~/.claude/settings.json
        if "cursor" in (cfg.get("harnesses") or ()):
            return None                       # Cursor's own hooks report it already
        harness = "cursor"
    ad = ADAPTERS.get(harness) or ADAPTERS["claude"]
    raw = (data.get("hook_event_name") or data.get("agent_action_name") or data.get("hookName")
           or event or "")
    name = ad["events"].get(raw, raw)
    if not name:
        return None
    info = data.get("tool_info") if isinstance(data.get("tool_info"), dict) else {}
    tool_input = data.get("tool_input") or data.get("toolArgs") or {}
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except ValueError:
            tool_input = {"command": tool_input}
    tool = data.get("tool_name") or data.get("toolName") or ""
    command = (tool_input.get("command") or tool_input.get("cmd") or "") if isinstance(tool_input, dict) else ""
    if isinstance(command, list):                 # e.g. ["bash", "-lc", "git push"]
        args = [str(c) for c in command]
        command = args[-1] if len(args) >= 3 and args[-2] in ("-c", "-lc") else " ".join(args)
    if not isinstance(command, str):
        command = ""
    error = ""

    if harness == "gemini":
        resp = data.get("tool_response") if isinstance(data.get("tool_response"), dict) else {}
        if raw == "AfterTool" and resp.get("error"):
            name = "PostToolUseFailure"
        if raw == "Notification" and data.get("notification_type") != "ToolPermission":
            return None
        if raw == "Notification":
            tool = (data.get("details") or {}).get("tool_name", "") if isinstance(data.get("details"), dict) else ""
    elif harness == "cursor":
        if raw == "stop":
            status = data.get("status", "completed")
            if status == "error":
                name, error = "StopFailure", "unknown"
    elif harness == "copilot":
        if raw == "errorOccurred":
            error = "unknown"
    elif harness == "cline":
        detail = data.get("preToolUse") or data.get("postToolUse") or {}
        if isinstance(detail, dict) and detail:
            tool = detail.get("toolName") or detail.get("tool") or ""
            params = detail.get("parameters") if isinstance(detail.get("parameters"), dict) else {}
            command = params.get("command") or ""
            if raw == "PostToolUse" and detail.get("success") is False:
                name = "PostToolUseFailure"
    elif harness == "devin":
        if raw.endswith("_run_command"):
            tool, command = "Bash", info.get("command_line", "")
        elif raw.endswith("_write_code"):
            tool = "Edit"
        elif raw.endswith("_mcp_tool_use"):
            tool = "mcp__{}__{}".format(info.get("mcp_server_name", "mcp"), info.get("mcp_tool_name", "tool"))

    ev = {k: data[k] for k in KEEP if data.get(k) not in (None, "")}
    ev["hook_event_name"] = name
    if harness != "claude":
        ev["harness"] = harness
    sid = (data.get("session_id") or data.get("sessionId") or data.get("conversation_id")
           or data.get("trajectory_id") or data.get("taskId") or "")
    if sid:
        ev["session_id"] = f"{harness}-{sid}" if harness != "claude" else sid
    elif harness != "claude":
        ev["session_id"] = harness                # one session per harness, better than none
    if tool:
        ev["tool_name"] = ad["tools"].get(tool, tool)
    else:
        ev.pop("tool_name", None)
    if data.get("notificationType") and "notification_type" not in ev:
        ev["notification_type"] = data["notificationType"]
    if name == "StopFailure" and data.get("error") and harness == "claude":
        ev["error_type"] = data["error"]          # StopFailure names its error type "error"
    elif error:
        ev["error_type"] = error
    if name == "PostToolUseFailure" and data.get("is_interrupt"):
        ev["interrupt"] = True
    if harness in TOKENS_IN_PAYLOAD and isinstance(data.get("tokens"), dict):
        tokens = {}
        for kind in TOKEN_KINDS:
            try:
                tokens[kind] = max(0, int(data["tokens"].get(kind) or 0))
            except (TypeError, ValueError):
                tokens[kind] = 0
        if any(tokens.values()):
            ev["tokens"] = tokens
    cwd = data.get("cwd") or info.get("cwd")
    roots = data.get("workspace_roots") or data.get("workspaceRoots")     # Cursor, Cline
    if not cwd and isinstance(roots, list) and roots:
        cwd = roots[0].get("path", "") if isinstance(roots[0], dict) else roots[0]
    if not cwd and harness != "claude":
        cwd = os.getcwd()                         # hooks run in the workspace
    ev["project"] = os.path.basename(str(cwd or "").rstrip("/\\"))
    return ev, command


def cmd_hook(cfg, harness="claude", event=""):
    raw = sys.stdin.read()
    ad = ADAPTERS.get(harness, {})
    if ad.get("reply") or ad.get("json"):
        print(ad.get("reply") or "{}")            # these harnesses expect JSON back
    try:
        data = json.loads(raw)
    except ValueError:
        return
    if not isinstance(data, dict):
        return
    out = adapt(harness, data, event, cfg)
    if not out:
        return
    ev, command = out
    name = ev["hook_event_name"]
    if name in ("PostToolUse", "PostToolUseFailure") and ev.get("tool_name") in SHELL_TOOLS:
        signals = classify(command)
        if signals:
            ev["signals"] = signals
    ev["ts"] = time.time()
    feed = None
    if name in FEED_EVENTS and ev.get("harness", "claude") in TOKEN_READERS:
        paths = [p for p in (data.get("transcript_path"), data.get("agent_transcript_path"))
                 if isinstance(p, str) and p]
        if paths:
            kind = ev.get("harness", "claude")
            feed = lambda: add_tokens(ev, kind, paths)
    post_detached(cfg, "/hook", ev, prepare=feed)


# --- food: token counts from the harness's own session log ---------------------------
# Every reader returns the running total of a log as {"input", "output", "cache_write",
# "cache_read"} plus whatever it needs to continue next time ("state"). Only numbers are
# read; nothing else from the log leaves this computer.
TOKEN_KINDS = ("input", "output", "cache_write", "cache_read")
FOOD_STATE = os.path.join(STATE_DIR, "food.json")
FOOD_FORGET = 30 * 86400
# A log seen for the first time (a session that ran before the client, or a resumed one)
# only counts what happened this recently, not its whole history.
FOOD_FIRST_SIGHT = 30 * 60


def _older(obj, since):
    """True if a log entry carries a timestamp from before `since` (epoch seconds)."""
    ts = obj.get("timestamp") if since and isinstance(obj, dict) else None
    if isinstance(ts, (int, float)):
        return ts / (1000 if ts > 1e11 else 1) < since
    if not isinstance(ts, str):
        return False
    try:
        when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.astimezone()
    return when.timestamp() < since


def _jsonl_from(path, offset):
    """Complete lines of a JSONL file from a byte offset; returns (objects, new offset)."""
    out = []
    with open(path, "rb") as f:
        size = os.fstat(f.fileno()).st_size
        if offset > size:
            offset = 0                            # the file was replaced
        f.seek(offset)
        data = f.read()
    end = data.rfind(b"\n") + 1                  # a last line still being written waits
    for line in data[:end].splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out, offset + end


def read_claude(path, st):
    """Claude Code transcript: "usage" on assistant messages; one message can span several
    lines with the same usage, so each message ID counts once."""
    objs, st["offset"] = _jsonl_from(path, st.get("offset", 0))
    recent = st.setdefault("ids", [])
    total = st.setdefault("total", dict.fromkeys(TOKEN_KINDS, 0))
    since = st.pop("since", 0)
    for obj in objs:
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        usage, mid = msg.get("usage"), msg.get("id") or obj.get("requestId")
        if not isinstance(usage, dict) or not mid or mid in recent:
            continue
        recent.append(mid)
        if _older(obj, since):
            continue
        total["input"] += int(usage.get("input_tokens") or 0)
        total["output"] += int(usage.get("output_tokens") or 0)
        total["cache_write"] += int(usage.get("cache_creation_input_tokens") or 0)
        total["cache_read"] += int(usage.get("cache_read_input_tokens") or 0)
    del recent[:-200]
    return total


def read_codex(path, st):
    """Codex rollout: "token_count" events carry the session's running total. OpenAI counts
    cached input inside input_tokens."""
    objs, st["offset"] = _jsonl_from(path, st.get("offset", 0))
    since = st.pop("since", 0)
    for obj in objs:
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else obj
        info = payload.get("info") if payload.get("type") == "token_count" else None
        usage = info.get("total_token_usage") if isinstance(info, dict) else None
        if isinstance(usage, dict):
            cached = int(usage.get("cached_input_tokens") or 0)
            st["total"] = {"input": max(0, int(usage.get("input_tokens") or 0) - cached),
                           "output": int(usage.get("output_tokens") or 0),
                           "cache_write": 0, "cache_read": cached}
            if _older(obj, since):
                st["base"] = dict(st["total"])   # the running total before we first looked
    return st.get("total") or dict.fromkeys(TOKEN_KINDS, 0)


def read_gemini(path, st):
    """Gemini CLI session file: "tokens" on each model message. Gemini counts cached input
    inside "input"; thoughts are output too."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        doc = json.loads(text)
        messages = doc.get("messages", []) if isinstance(doc, dict) else doc
    except ValueError:                            # newer versions may write JSONL
        messages = []
        for line in text.splitlines():
            try:
                messages.append(json.loads(line))
            except ValueError:
                pass
    total = dict.fromkeys(TOKEN_KINDS, 0)
    seen = set()
    since = st.pop("since", 0)
    for m in messages if isinstance(messages, list) else []:
        t = m.get("tokens") if isinstance(m, dict) else None
        if not isinstance(t, dict) or m.get("id") in seen:
            continue
        seen.add(m.get("id"))
        if _older(m, since):
            st.setdefault("base", dict.fromkeys(TOKEN_KINDS, 0))
            for kind, n in (("input", max(0, int(t.get("input") or 0) - int(t.get("cached") or 0))
                             + int(t.get("tool") or 0)),
                            ("output", int(t.get("output") or 0) + int(t.get("thoughts") or 0)),
                            ("cache_read", int(t.get("cached") or 0))):
                st["base"][kind] += n
        cached = int(t.get("cached") or 0)
        total["input"] += max(0, int(t.get("input") or 0) - cached) + int(t.get("tool") or 0)
        total["output"] += int(t.get("output") or 0) + int(t.get("thoughts") or 0)
        total["cache_read"] += cached
    return total


TOKEN_READERS = {"claude": read_claude, "codex": read_codex, "gemini": read_gemini}


def _locked(path):
    """An exclusive lock next to `path`, so parallel hooks do not count tokens twice."""
    f = open(path + ".lock", "a")
    try:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_EX)
    except (ImportError, OSError):
        pass                                      # Windows: best effort
    return f


def new_tokens(kind, paths, state_path=FOOD_STATE, now=None):
    """Tokens added to these session logs since the last call (per log)."""
    reader = TOKEN_READERS[kind]
    now = now or time.time()
    os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
    lock = _locked(state_path)
    try:
        try:
            with open(state_path) as f:
                state = json.load(f)
        except (OSError, ValueError):
            state = {}
        delta = dict.fromkeys(TOKEN_KINDS, 0)
        for path in paths:
            key = hashlib.sha1(path.encode()).hexdigest()[:16]
            st = state.get(key)
            if st is None:
                st = {"since": now - FOOD_FIRST_SIGHT}
            before = dict(st.get("total") or dict.fromkeys(TOKEN_KINDS, 0))
            try:
                total = reader(path, st)
            except (OSError, ValueError, TypeError, AttributeError):
                continue
            base = st.pop("base", {})     # eaten before the first look (see FOOD_FIRST_SIGHT)
            before = {k: before.get(k, 0) + base.get(k, 0) for k in TOKEN_KINDS}
            st["total"], st["seen"] = dict(total), now
            state[key] = st
            fresh = {k: total.get(k, 0) - before.get(k, 0) for k in TOKEN_KINDS}
            if any(v < 0 for v in fresh.values()):    # a new log under the same name
                fresh = dict(total)
            for k in TOKEN_KINDS:
                delta[k] += max(0, fresh[k])
        state = {k: v for k, v in state.items() if now - v.get("seen", 0) < FOOD_FORGET}
        tmp = state_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, state_path)
    finally:
        lock.close()
    return delta


def add_tokens(ev, kind, paths):
    tokens = new_tokens(kind, paths)
    if any(tokens.values()):
        ev["tokens"] = tokens


def cmd_statusline(cfg):
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except ValueError:
        data = {}
    rl = data.get("rate_limits")

    # 1) Print the status line: either your existing one or a small one of our own
    out = ""
    if cfg.get("statusline_chain"):
        try:
            chain = cfg["statusline_chain"]
            # Claude Code ran it in Git Bash on Windows; shell=True there would mean cmd.exe
            cmd = ["sh", "-c", chain] if os.name == "nt" else chain
            out = subprocess.run(cmd, shell=os.name != "nt", input=raw, text=True,
                                 capture_output=True, timeout=5).stdout.rstrip("\n")
        except Exception:
            out = ""
    if not out:
        parts = [(data.get("model") or {}).get("display_name") or "Claude"]
        for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
            w = (rl or {}).get(key) or {}
            if w.get("used_percentage") is not None:
                parts.append(f"{label} {round(w['used_percentage'])}%")
        out = "(◕‿‿◕) " + " · ".join(parts)
    print(out)

    # 2) Report the limits and how full this session's context is
    ctx = (data.get("context_window") or {}).get("used_percentage")
    if rl or ctx is not None:
        payload = {"ts": time.time()}
        if rl:
            payload["rate_limits"] = rl
        if ctx is not None and data.get("session_id"):
            payload.update(session_id=data["session_id"], context_pct=ctx)
        post_detached(cfg, "/limits", payload)


def cmd_test(cfg):
    """Plays a short sequence so you can see every mood."""
    sid = "test-session"
    steps = [
        ({"hook_event_name": "SessionStart"}, "hello"),
        ({"hook_event_name": "UserPromptSubmit"}, "working"),
        ({"hook_event_name": "PreToolUse", "tool_name": "Bash"}, "working with a tool"),
        ({"hook_event_name": "Notification", "notification_type": "permission_prompt",
          "tool_name": "Bash"}, "asking for permission"),
        ({"hook_event_name": "PostToolUse", "tool_name": "Bash"}, "working again"),
        ({"hook_event_name": "PostToolUseFailure", "tool_name": "Bash"}, "a command fails"),
        ({"hook_event_name": "PostToolUseFailure", "tool_name": "Bash"}, "fails again"),
        ({"hook_event_name": "PostToolUseFailure", "tool_name": "Bash", "signals": ["test"]},
         "third failure in a row: stuck"),
        ({"hook_event_name": "PostToolUse", "tool_name": "Bash", "signals": ["test"]},
         "tests green again: relieved"),
        ({"hook_event_name": "PostToolUse", "tool_name": "Bash", "signals": ["commit"]},
         "a commit: proud"),
        ({"hook_event_name": "Stop"}, "done (still proud of that commit)"),
        ({"hook_event_name": "Notification", "notification_type": "idle_prompt"}, "waiting for you"),
        ({"hook_event_name": "StopFailure", "error_type": "rate_limit"}, "limit reached"),
        ({"hook_event_name": "SessionEnd"}, "session ended"),
    ]
    for ev, label in steps:
        ev.update(session_id=sid, project="tokibot-test", ts=time.time())
        try:
            url = send(cfg, "/hook", ev)
            print(f"✓ {label}  ({url})")
        except Exception as e:
            print(f"✗ {label}: {e} (is it reachable at {', '.join(candidates(cfg) + [cfg['relay']]).strip(', ')}?)")
            return 1
        time.sleep(6)
    return 0


def save_installed(**values):
    """Merges values into the installed settings file (~/.tokibot/)."""
    try:
        with open(INSTALLED_CFG) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data.update(values)
    os.makedirs(os.path.dirname(INSTALLED_CFG), exist_ok=True)
    tmp = INSTALLED_CFG + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, INSTALLED_CFG)


def cmd_pair(cfg, target=""):
    """Finds the gotchi (USB cable, a name, or an address), remembers its name and,
    if it has no token yet, gets a fresh one from it."""
    if target.startswith("http"):
        urls = [target.rstrip("/")]
    elif target:
        urls = [f"http://{target.removesuffix('.local')}.local:{PORT}"]
    elif cfg["url"] not in ("", "none", "auto"):
        urls = [cfg["url"]]
    else:
        urls = candidates(dict(cfg, url="auto"))
    h = headers(dict(cfg, gotchi=""))
    h["X-Tokibot-Pair"] = h["X-Claudegotchi-Pair"] = "1"
    info, err = None, None
    for url in urls:
        try:
            req = urllib.request.Request(url + "/pair", data=b"{}", headers=h, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                info = json.load(resp)
            break
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print(f"✗ {url} has a token already. Install again with --token … "
                      "(it is under [server] token in tokibot.toml)")
            else:
                print(f"✗ {url} said {e.code}. Is the gotchi up to date?")
            return 1
        except Exception as e:
            err = e
    if info is None:
        hint = ("Plug it in with the USB cable, or pass the name it shows on screen: "
                "pair tokibot-xxxx" if urls == [USB_URL] else "Is it on and on the same network?")
        print(f"✗ No gotchi at {', '.join(urls)} ({err}). {hint}")
        return 1
    name, token = info.get("gotchi", ""), info.get("token") or cfg["token"]
    save_installed(gotchi=name, token=token)
    write_state(LEARNED, name)
    print(f"✓ Paired with {name}" + (f" ({name}.local on Wi-Fi)" if name else ""))
    if info.get("token") and info["token"] != cfg["token"]:
        print("✓ The gotchi made a token and only accepts this computer (and whoever has the "
              f"token) from now on. Saved in {INSTALLED_CFG}")
    elif not token:
        print("! No token: anyone on your network can send events to it. "
              "Set one on its settings page.")
    if cfg["relay"] and info.get("token") and info["token"] != cfg["token"]:
        print("! You also use a relay: run the installer with --cloud-setup again so your "
              "cloud environments send the new token.")
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "hook"
    cfg = load_config()
    if cmd == "hook":
        opts = dict(zip(sys.argv[2::2], sys.argv[3::2]))
        cmd_hook(cfg, opts.get("--harness", "claude"), opts.get("--event", ""))
    elif cmd == "statusline":
        cmd_statusline(cfg)
    elif cmd == "test":
        return cmd_test(cfg)
    elif cmd == "pair":
        return cmd_pair(cfg, sys.argv[2] if len(sys.argv) > 2 else "")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
