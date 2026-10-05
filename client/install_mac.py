#!/usr/bin/env python3
"""Sets up the Claudegotchi client in Claude Code (or removes it again). Mac and Linux.

  python3 install_mac.py                         # default: automatic (USB cable, then Wi-Fi)
  python3 install_mac.py --gotchi claudegotchi-3f2a   # pair over Wi-Fi by the name on its screen
  python3 install_mac.py --url http://192.168.1.50:8765 --token secret
  python3 install_mac.py --new-relay             # also send through a new ntfy relay topic
  python3 install_mac.py --cloud-setup > setup.sh   # script for a cloud environment
  python3 install_mac.py --statusline-only       # only the status line, when the hooks come from the plugin
  python3 install_mac.py --uninstall

What happens:
  * claudegotchi_client.py is copied to ~/.claude/claudegotchi/
  * ~/.claude/settings.json gets the hooks and the status line
    (a backup settings.json.claudegotchi-backup is made first)
  * an existing status line is kept and still shown
  * the client pairs with your gotchi (USB cable, or --gotchi NAME): it remembers the
    gotchi's name and, if the gotchi has no token yet, gets one from it
"""
import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys

CLAUDE_DIR = os.path.expanduser("~/.claude")
TARGET_DIR = os.path.join(CLAUDE_DIR, "claudegotchi")
SETTINGS = os.path.join(CLAUDE_DIR, "settings.json")
CLIENT = os.path.join(TARGET_DIR, "claudegotchi_client.py")
MARK = "claudegotchi_client.py"
DEFAULT_URL = "auto"
RELAY_SERVER = "https://ntfy.sh"

EVENTS = ["SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse",
          "PostToolUseFailure", "PermissionRequest", "Notification", "Stop", "StopFailure",
          "SubagentStart", "SubagentStop", "PreCompact"]


def load_settings():
    if not os.path.exists(SETTINGS):
        return {}
    with open(SETTINGS) as f:
        return json.load(f)


def save_settings(s):
    os.makedirs(CLAUDE_DIR, exist_ok=True)
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, SETTINGS)


def strip_ours(settings):
    hooks = settings.get("hooks", {})
    for ev in list(hooks):
        groups = []
        for g in hooks[ev]:
            g = dict(g)
            g["hooks"] = [h for h in g.get("hooks", []) if MARK not in h.get("command", "")]
            if g["hooks"]:
                groups.append(g)
        if groups:
            hooks[ev] = groups
        else:
            del hooks[ev]
    if not hooks:
        settings.pop("hooks", None)


def read_cfg():
    try:
        with open(os.path.join(TARGET_DIR, "claudegotchi.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def resolve(args, old_cfg):
    """url, token, relay from the arguments, falling back to the installed config."""
    url = args.url or old_cfg.get("url") or DEFAULT_URL
    token = args.token if args.token is not None else old_cfg.get("token", "")
    relay = args.relay if args.relay is not None else old_cfg.get("relay", "")
    if args.new_relay:
        relay = f"{RELAY_SERVER}/claudegotchi-{secrets.token_urlsafe(18)}"
        token = token or secrets.token_urlsafe(18)
    return url, token, relay.rstrip("/")


def resolve_gotchi(args, old_cfg):
    name = args.gotchi if args.gotchi is not None else old_cfg.get("gotchi", "")
    return name.strip().removesuffix(".local")


def gotchi_settings(token, relay):
    return (f'[server]\ntoken = "{token}"\n\n'
            f'[relay]\nurl = "{relay}"\n')


def install(args):
    os.makedirs(TARGET_DIR, exist_ok=True)
    shutil.copy2(os.path.join(os.path.dirname(os.path.abspath(__file__)), "claudegotchi_client.py"), CLIENT)
    os.chmod(CLIENT, 0o755)

    settings = load_settings()
    if os.path.exists(SETTINGS) and not os.path.exists(SETTINGS + ".claudegotchi-backup"):
        shutil.copy2(SETTINGS, SETTINGS + ".claudegotchi-backup")   # back up the original version only

    cfg_path = os.path.join(TARGET_DIR, "claudegotchi.json")
    old_cfg = read_cfg()

    # Chain an existing status line instead of replacing it
    chain = old_cfg.get("statusline_chain", "")
    sl = settings.get("statusLine") or {}
    if sl.get("command") and MARK not in sl["command"]:
        chain = sl["command"]

    url, token, relay = resolve(args, old_cfg)
    with open(cfg_path, "w") as f:
        json.dump({"url": url, "token": token, "relay": relay, "gotchi": resolve_gotchi(args, old_cfg),
                   "statusline_chain": chain}, f, indent=2)

    cmd = f'python3 "{CLIENT}"'
    strip_ours(settings)
    if not args.statusline_only:
        hooks = settings.setdefault("hooks", {})
        for ev in EVENTS:
            hooks.setdefault(ev, []).append({"hooks": [
                {"type": "command", "command": f"{cmd} hook", "async": True, "timeout": 10}]})
    if not settings.get("hooks"):
        settings.pop("hooks", None)
    new_sl = {"type": "command", "command": f"{cmd} statusline"}
    if sl.get("padding") is not None:
        new_sl["padding"] = sl["padding"]
    settings["statusLine"] = new_sl
    save_settings(settings)

    print(f"✓ Client installed: {CLIENT}")
    what = "Status line" if args.statusline_only else "Hooks and status line"
    print(f"✓ {what} added to {SETTINGS} (backup: settings.json.claudegotchi-backup)")
    if chain:
        print(f"✓ Your existing status line is still shown: {chain}")
    print(f"→ Gotchi address: {url}")
    if relay:
        print(f"→ Relay: {relay}")
        print("→ Put this into claudegotchi.toml on the gotchi (it needs Wi-Fi for the relay):\n")
        print(gotchi_settings(token, relay))
    if url != "none":
        print("→ Pairing with your gotchi …")
        if subprocess.run([sys.executable, CLIENT, "pair", resolve_gotchi(args, old_cfg)]).returncode:
            print(f'→ Pair later:  python3 "{CLIENT}" pair [claudegotchi-xxxx]')
    print(f'→ Test:  python3 "{CLIENT}" test')
    print("→ Restart running Claude Code sessions once so the hooks take effect.")


def cloud_setup(args):
    """Prints a shell script for a cloud environment's setup script. It carries the
    client and this installer inline, so the cloud container needs no access to this repo."""
    old_cfg = read_cfg()
    url, token, relay = resolve(args, old_cfg)
    if not relay:
        sys.exit("A cloud setup needs a relay: run with --relay URL or --new-relay "
                 "(or install locally with a relay first).")
    here = os.path.dirname(os.path.abspath(__file__))
    files = {}
    for name in ("claudegotchi_client.py", "install_mac.py"):
        with open(os.path.join(here, name)) as f:
            files[name] = f.read()
    out = ["#!/bin/sh", "# Claudegotchi: install the hook client in this cloud environment.",
           "set -e", 'd="$(mktemp -d)"']
    for name, text in files.items():
        mark = "END_OF_" + name.replace(".", "_").upper()
        assert mark not in text
        out += [f"cat > \"$d/{name}\" <<'{mark}'", text.rstrip("\n"), mark]
    out.append(f'python3 "$d/install_mac.py" --url none --token "{token}" --relay "{relay}" >/dev/null')
    out.append('rm -rf "$d"')
    print("\n".join(out))
    print("Paste the script above into the cloud environment's setup script.\n"
          "Put this into claudegotchi.toml on the gotchi:\n\n" + gotchi_settings(token, relay),
          file=sys.stderr)


def uninstall():
    settings = load_settings()
    strip_ours(settings)
    chain = ""
    cfg_path = os.path.join(TARGET_DIR, "claudegotchi.json")
    if os.path.exists(cfg_path):
        with open(cfg_path) as f:
            chain = json.load(f).get("statusline_chain", "")
    sl = settings.get("statusLine") or {}
    if MARK in sl.get("command", ""):
        if chain:
            settings["statusLine"] = {"type": "command", "command": chain}
        else:
            settings.pop("statusLine", None)
    save_settings(settings)
    shutil.rmtree(TARGET_DIR, ignore_errors=True)
    print("✓ Claudegotchi removed from Claude Code" + (f"; status line restored to: {chain}" if chain else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=None, help=f"address of the gotchi, or none for relay only (default: {DEFAULT_URL})")
    ap.add_argument("--token", default=None, help="optional token, must match the gotchi")
    ap.add_argument("--gotchi", default=None,
                    help="your gotchi's name as shown on its screen (claudegotchi-xxxx); "
                         "not needed if it is plugged in with the USB cable")
    ap.add_argument("--relay", default=None, help="ntfy topic URL to publish to as well (\"\" to turn it off)")
    ap.add_argument("--new-relay", action="store_true", help="create a random ntfy.sh topic (and a token)")
    ap.add_argument("--cloud-setup", action="store_true",
                    help="print a setup script for a cloud environment instead of installing")
    ap.add_argument("--statusline-only", action="store_true",
                    help="only the status line (for the budget bars), when the hooks come from the plugin")
    ap.add_argument("--uninstall", action="store_true")
    args = ap.parse_args()
    if args.uninstall:
        uninstall()
    elif args.cloud_setup:
        cloud_setup(args)
    else:
        install(args)


if __name__ == "__main__":
    sys.exit(main())
