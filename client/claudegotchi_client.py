#!/usr/bin/env python3
"""Claudegotchi client for Claude Code (Mac/Linux).

  claudegotchi_client.py hook        as a Claude Code hook: report the event to the gotchi
  claudegotchi_client.py statusline  as the status line: report limits and print a status line
  claudegotchi_client.py test        send a test sequence to the gotchi

Transport: straight to the gotchi over HTTP (USB cable or Wi-Fi), and/or through a
relay (an ntfy topic) when "relay" is set. The relay is for Claude Code running in the
cloud (e.g. Claude Projects), which cannot reach a gotchi on your local network.

Sends metadata only (event name, session ID, project folder name, tool name,
notification/error type, limit and context percentages, and a few categories such as
"a test run failed" or "a commit succeeded"), never prompts, code, commands or replies.
Never blocks Claude Code: sending happens in a detached background process.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import uuid

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


# "auto": try the USB cable first, then Wi-Fi.
AUTO_URLS = ["http://192.168.77.1:8765", "http://claudegotchi.local:8765"]
# As a Claude Code plugin the client lives in the plugin cache, which is replaced on
# every update; keep the little state it writes in the plugin's data folder instead.
LAST_URL = os.path.join(os.environ.get("CLAUDE_PLUGIN_DATA") or HERE, "last_url")
# Where install_mac.py keeps the settings; the plugin reads them from there as well.
INSTALLED_CFG = os.path.expanduser("~/.claude/claudegotchi/claudegotchi.json")


def load_config():
    cfg = {"url": "auto", "token": "", "relay": "", "statusline_chain": ""}
    for path in dict.fromkeys((INSTALLED_CFG, os.path.join(HERE, "claudegotchi.json"))):
        try:
            with open(path) as f:
                cfg.update(json.load(f))
        except (OSError, ValueError):
            pass
    # Options set in the plugin's settings (/config) win over the file, if they are set
    for key in ("url", "token", "relay"):
        value = os.environ.get("CLAUDE_PLUGIN_OPTION_" + key.upper(), "").strip()
        if value:
            cfg[key] = value
    cfg["url"] = os.environ.get("CLAUDEGOTCHI_URL", cfg["url"]).rstrip("/")
    cfg["token"] = os.environ.get("CLAUDEGOTCHI_TOKEN", cfg["token"])
    cfg["relay"] = os.environ.get("CLAUDEGOTCHI_RELAY", cfg["relay"]).rstrip("/")
    return cfg


def candidates(cfg):
    if cfg["url"] in ("", "none"):              # relay only
        return []
    if cfg["url"] != "auto":
        return [cfg["url"]]
    urls = list(AUTO_URLS)
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
    headers = {"Content-Type": "application/json"}
    if cfg["token"]:
        headers["X-Claudegotchi-Token"] = cfg["token"]
    body = json.dumps(payload).encode()
    for i, url in enumerate(urls):
        req = urllib.request.Request(url + path, data=body, headers=headers, method="POST")
        try:
            urllib.request.urlopen(req, timeout=timeout).read()
        except Exception:
            if i == len(urls) - 1:
                raise
            continue
        if cfg["url"] == "auto" and i > 0:
            try:
                with open(LAST_URL, "w") as f:
                    f.write(url)
            except OSError:
                pass
        return url


def publish(cfg, path, payload, timeout=5):
    """Send through the relay: one ntfy message whose body is our JSON envelope.
    The gotchi subscribes to the same topic and checks the token."""
    env = {"claudegotchi": 1, "path": path, "token": cfg["token"], "data": payload}
    req = urllib.request.Request(cfg["relay"], data=json.dumps(env).encode(), method="POST",
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


def post_detached(cfg, path, payload):
    """Detach and send in the background; the caller returns immediately."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        if os.fork():
            return
    except (OSError, AttributeError):          # no fork (e.g. Windows): send with a short timeout
        try:
            send(cfg, path, payload, timeout=0.5)
        except Exception:
            pass
        return
    try:
        os.setsid()
        devnull = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(devnull, fd)
        send(cfg, path, payload)
    except Exception:
        pass
    finally:
        os._exit(0)


def cmd_hook(cfg):
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    ev = {k: data[k] for k in KEEP if data.get(k) not in (None, "")}
    name = data.get("hook_event_name")
    if name == "StopFailure" and data.get("error"):
        ev["error_type"] = data["error"]          # StopFailure names its error type "error"
    if name == "PostToolUseFailure" and data.get("is_interrupt"):
        ev["interrupt"] = True
    if name in ("PostToolUse", "PostToolUseFailure") and data.get("tool_name") in SHELL_TOOLS:
        signals = classify((data.get("tool_input") or {}).get("command"))
        if signals:
            ev["signals"] = signals
    ev["project"] = os.path.basename((data.get("cwd") or "").rstrip("/"))
    ev["ts"] = time.time()
    post_detached(cfg, "/hook", ev)


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
            out = subprocess.run(cfg["statusline_chain"], shell=True, input=raw, text=True,
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
        ev.update(session_id=sid, project="claudegotchi-test", ts=time.time())
        try:
            url = send(cfg, "/hook", ev)
            print(f"✓ {label}  ({url})")
        except Exception as e:
            print(f"✗ {label}: {e} (is it reachable at {', '.join(candidates(cfg) + [cfg['relay']]).strip(', ')}?)")
            return 1
        time.sleep(6)
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "hook"
    cfg = load_config()
    if cmd == "hook":
        cmd_hook(cfg)
    elif cmd == "statusline":
        cmd_statusline(cfg)
    elif cmd == "test":
        return cmd_test(cfg)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
