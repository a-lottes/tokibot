#!/usr/bin/env python3
"""Claudegotchi-Client für Claude Code (Mac/Linux).

  claudegotchi_client.py hook        – als Claude-Code-Hook: Event ans Gotchi melden
  claudegotchi_client.py statusline  – als Statusline: Limits melden + Statuszeile ausgeben
  claudegotchi_client.py test        – Testsequenz an das Gotchi schicken

Sendet nur Metadaten (Event-Name, Session-ID, Projektordner-Name, Tool-Name,
Benachrichtigungs-/Fehlertyp, Limit-Prozente) – niemals Prompts, Code oder Antworten.
Blockiert Claude Code nie: Das Senden läuft in einem abgekoppelten Hintergrundprozess.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
KEEP = ("hook_event_name", "session_id", "notification_type", "error_type",
        "tool_name", "source", "reason")


# "auto": erst das USB-Kabel probieren, dann das WLAN.
AUTO_URLS = ["http://192.168.77.1:8765", "http://claudegotchi.local:8765"]
LAST_URL = os.path.join(HERE, "last_url")


def load_config():
    cfg = {"url": "auto", "token": "", "statusline_chain": ""}
    try:
        with open(os.path.join(HERE, "claudegotchi.json")) as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    cfg["url"] = os.environ.get("CLAUDEGOTCHI_URL", cfg["url"]).rstrip("/")
    cfg["token"] = os.environ.get("CLAUDEGOTCHI_TOKEN", cfg["token"])
    return cfg


def candidates(cfg):
    if cfg["url"] != "auto":
        return [cfg["url"]]
    urls = list(AUTO_URLS)
    try:
        with open(LAST_URL) as f:
            last = f.read().strip()
        if last in urls:                       # zuletzt erfolgreiche Adresse zuerst
            urls.remove(last)
            urls.insert(0, last)
    except OSError:
        pass
    return urls


def post(cfg, path, payload, timeout=3):
    headers = {"Content-Type": "application/json"}
    if cfg["token"]:
        headers["X-Claudegotchi-Token"] = cfg["token"]
    body = json.dumps(payload).encode()
    urls = candidates(cfg)
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


def post_detached(cfg, path, payload):
    """Abkoppeln und im Hintergrund senden – der Aufrufer kehrt sofort zurück."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        if os.fork():
            return
    except (OSError, AttributeError):          # kein fork (z.B. Windows): kurz und knapp senden
        try:
            post(cfg, path, payload, timeout=0.5)
        except Exception:
            pass
        return
    try:
        os.setsid()
        devnull = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(devnull, fd)
        post(cfg, path, payload)
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

    # 1) Statuszeile ausgeben: entweder deine bisherige oder eine kleine eigene
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

    # 2) Limits ans Gotchi melden
    if rl:
        post_detached(cfg, "/limits", {"rate_limits": rl, "ts": time.time()})


def cmd_test(cfg):
    """Spielt einen kleinen Ablauf durch, damit du jede Stimmung siehst."""
    sid = "test-session"
    steps = [
        ({"hook_event_name": "SessionStart"}, "Hallo"),
        ({"hook_event_name": "UserPromptSubmit"}, "arbeitet"),
        ({"hook_event_name": "PreToolUse", "tool_name": "Bash"}, "arbeitet mit Tool"),
        ({"hook_event_name": "Notification", "notification_type": "permission_prompt",
          "tool_name": "Bash"}, "fragt um Erlaubnis"),
        ({"hook_event_name": "PostToolUse", "tool_name": "Bash"}, "arbeitet weiter"),
        ({"hook_event_name": "Stop"}, "fertig"),
        ({"hook_event_name": "Notification", "notification_type": "idle_prompt"}, "wartet auf dich"),
        ({"hook_event_name": "StopFailure", "error_type": "rate_limit"}, "Limit erreicht"),
        ({"hook_event_name": "SessionEnd"}, "Session beendet"),
    ]
    for ev, label in steps:
        ev.update(session_id=sid, project="claudegotchi-test", ts=time.time())
        try:
            url = post(cfg, "/hook", ev)
            print(f"✓ {label}  ({url})")
        except Exception as e:
            print(f"✗ {label}: {e} – erreichbar unter {', '.join(candidates(cfg))}?")
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
