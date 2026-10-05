#!/usr/bin/env python3
"""Claudegotchi client for Claude Code (Mac/Linux).

  claudegotchi_client.py hook        as a Claude Code hook: report the event to the gotchi
  claudegotchi_client.py statusline  as the status line: report limits and print a status line
  claudegotchi_client.py test        send a test sequence to the gotchi
  claudegotchi_client.py pair [NAME]  pair with your gotchi: over the USB cable, or by the
                                     name it shows on screen (claudegotchi-xxxx)

Transport: straight to the gotchi over HTTP (USB cable or Wi-Fi), and/or through a
relay (an ntfy topic) when "relay" is set. The relay is for Claude Code running in the
cloud (e.g. Claude Projects), which cannot reach a gotchi on your local network.

Which gotchi: every gotchi has its own name, claudegotchi-xxxx. The client sends it
along, so a gotchi that is not yours (a friend's on the same Wi-Fi) refuses the event.
With url "auto" the client tries the USB cable first, then <name>.local over Wi-Fi. It
learns the name the first time it reaches a gotchi over USB, or from "pair".

Sends metadata only (event name, session ID, project folder name, tool name,
notification/error type, limit percentages), never prompts, code or replies.
Never blocks Claude Code: sending happens in a detached background process.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
KEEP = ("hook_event_name", "session_id", "notification_type", "error_type",
        "tool_name", "source", "reason")


# "auto": try the USB cable first, then the paired gotchi's name over Wi-Fi.
USB_URL = "http://192.168.77.1:8765"
PORT = 8765
# As a Claude Code plugin the client lives in the plugin cache, which is replaced on
# every update; keep the little state it writes in the plugin's data folder instead.
STATE_DIR = os.environ.get("CLAUDE_PLUGIN_DATA") or HERE
LAST_URL = os.path.join(STATE_DIR, "last_url")
LEARNED = os.path.join(STATE_DIR, "gotchi")     # name learned on first contact over USB
# Where install_mac.py keeps the settings; the plugin reads them from there as well.
INSTALLED_CFG = os.path.expanduser("~/.claude/claudegotchi/claudegotchi.json")


def load_config():
    cfg = {"url": "auto", "token": "", "relay": "", "gotchi": "", "statusline_chain": ""}
    for path in dict.fromkeys((INSTALLED_CFG, os.path.join(HERE, "claudegotchi.json"))):
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
    cfg["url"] = os.environ.get("CLAUDEGOTCHI_URL", cfg["url"]).rstrip("/")
    cfg["token"] = os.environ.get("CLAUDEGOTCHI_TOKEN", cfg["token"])
    cfg["relay"] = os.environ.get("CLAUDEGOTCHI_RELAY", cfg["relay"]).rstrip("/")
    cfg["gotchi"] = os.environ.get("CLAUDEGOTCHI_GOTCHI", cfg["gotchi"]) or read_state(LEARNED)
    return cfg


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
                name = resp.headers.get("X-Claudegotchi-Gotchi") or ""
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
        h["X-Claudegotchi-Token"] = cfg["token"]
    if cfg.get("gotchi"):
        h["X-Claudegotchi-Gotchi"] = cfg.get("gotchi")
    return h


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

    # 2) Report the limits to the gotchi
    if rl:
        post_detached(cfg, "/limits", {"rate_limits": rl, "ts": time.time()})


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
        ({"hook_event_name": "Stop"}, "done"),
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


def save_installed(**values):
    """Merges values into the installed settings file (~/.claude/claudegotchi/)."""
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
    h["X-Claudegotchi-Pair"] = "1"
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
                      "(it is under [server] token in claudegotchi.toml)")
            else:
                print(f"✗ {url} said {e.code}. Is the gotchi up to date?")
            return 1
        except Exception as e:
            err = e
    if info is None:
        hint = ("Plug it in with the USB cable, or pass the name it shows on screen: "
                "pair claudegotchi-xxxx" if urls == [USB_URL] else "Is it on and on the same network?")
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
        cmd_hook(cfg)
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
