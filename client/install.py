#!/usr/bin/env python3
"""Sets up the Tokibot client in Claude Code and other coding harnesses (or removes it).
macOS, Linux, and Windows with Git for Windows (run it from Git Bash).

  python3 install.py                         # default: automatic (USB cable, then Wi-Fi)
  python3 install.py --harness claude,codex  # also report Codex sessions (see HARNESSES)
  python3 install.py --harness auto          # every harness found on this computer
  python3 install.py --gotchi tokibot-3f2a   # pair over Wi-Fi by the name on its screen
  python3 install.py --url http://192.168.1.50:8765 --token secret
  python3 install.py --new-relay             # also send through a new ntfy relay topic
  python3 install.py --cloud-setup > setup.sh   # script for a cloud environment
  python3 install.py --statusline-only       # only the status line, when the hooks come from the plugin
  python3 install.py --uninstall

What happens:
  * tokibot_client.py is copied to ~/.tokibot/
  * ~/.claude/settings.json gets the hooks and the status line
    (a backup settings.json.tokibot-backup is made first)
  * other harnesses get the hooks in their own settings file (with a backup as well)
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
TARGET_DIR = os.path.expanduser("~/.tokibot")
SETTINGS = os.path.join(CLAUDE_DIR, "settings.json")
CLIENT = os.path.join(TARGET_DIR, "tokibot_client.py")
LAUNCHER = os.path.join(TARGET_DIR, "tokibot.sh")
# Before the rename (Claudegotchi) the client lived in ~/.claude/claudegotchi/
LEGACY_DIR = os.path.join(CLAUDE_DIR, "claudegotchi")
MARKS = ("tokibot_client.py", ".tokibot/tokibot.sh",
         "claudegotchi_client.py", "claudegotchi/claudegotchi.sh")


def ours(command):
    return any(m in command for m in MARKS)
DEFAULT_URL = "auto"
RELAY_SERVER = "https://ntfy.sh"

EVENTS = ["SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse",
          "PostToolUseFailure", "PermissionRequest", "Notification", "Stop", "StopFailure",
          "SubagentStart", "SubagentStop", "PreCompact"]


# Other coding harnesses: settings file, how hooks are written there, and their events.
#   nested: Claude Code's layout, {"hooks": {Event: [{"hooks": [entry]}]}}
#   flat:   {"hooks": {Event: [entry]}}
HARNESSES = {
    "codex": {"path": "~/.codex/hooks.json", "style": "nested", "found": "~/.codex",
              "events": ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
                         "PermissionRequest", "Stop", "PreCompact", "SubagentStart",
                         "SubagentStop"],
              "note": "Codex asks before it runs new hooks: open Codex and approve them with /hooks."},
    "gemini": {"path": "~/.gemini/settings.json", "style": "nested", "found": "~/.gemini",
               "events": ["SessionStart", "SessionEnd", "BeforeAgent", "AfterAgent", "BeforeTool",
                          "AfterTool", "Notification", "PreCompress"]},
    "copilot": {"path": "~/.copilot/hooks/tokibot.json", "style": "flat", "found": "~/.copilot",
                "version": 1,
                # PascalCase events get Claude Code's payloads; the rest only exist in camelCase
                "events": ["SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse",
                           "PostToolUse", "PostToolUseFailure", "agentStop", "errorOccurred",
                           "permissionRequest", "preCompact", "subagentStart", "subagentStop"]},
    "cursor": {"path": "~/.cursor/hooks.json", "style": "flat", "found": "~/.cursor", "version": 1,
               "events": ["sessionStart", "sessionEnd", "beforeSubmitPrompt", "preToolUse",
                          "postToolUse", "postToolUseFailure", "subagentStart", "subagentStop",
                          "preCompact", "stop"]},
    "devin": {"path": "~/.codeium/windsurf/hooks.json", "style": "flat", "found": "~/.codeium/windsurf",
              "events": ["pre_user_prompt", "pre_run_command", "post_run_command", "pre_write_code",
                         "post_write_code", "pre_mcp_tool_use", "post_mcp_tool_use",
                         "post_cascade_response"]},
    # Kiro CLI 3: standalone hook files; this one is ours alone
    "kiro": {"path": "~/.kiro/hooks/tokibot.json", "style": "kiro", "found": "~/.kiro",
             "events": ["SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse",
                        "PostToolUse", "Stop"]},
    # Cline: one executable script per hook, named after it
    "cline": {"path": "~/Documents/Cline/Hooks", "style": "scripts", "found": "~/Documents/Cline",
              "events": ["TaskStart", "TaskResume", "TaskCancel", "TaskComplete", "UserPromptSubmit",
                         "PreToolUse", "PostToolUse", "PreCompact"]},
    # OpenCode and Amp have no command hooks, only plugins run by Bun: ours hands the
    # events to the client
    "opencode": {"path": "~/.config/opencode/plugins/tokibot.ts", "style": "plugin",
                 "found": "~/.config/opencode"},
    "amp": {"path": "~/.config/amp/plugins/tokibot.ts", "style": "plugin", "found": "~/.config/amp"},
}

# The plugins send Claude-Code-style payloads to `tokibot.sh hook`, fire and forget.
PLUGIN_SEND = """const LAUNCHER = __LAUNCHER__
function send(event: string, data: Record<string, unknown>) {
  try {
    const p = Bun.spawn(["sh", LAUNCHER, "hook", "--harness", __HARNESS__, "--event", event],
                        { stdin: "pipe", stdout: "ignore", stderr: "ignore" })
    p.stdin.write(JSON.stringify({ hook_event_name: event, ...data }))
    p.stdin.end()
    p.unref()
  } catch {}
}
"""

PLUGINS = {
    "opencode": """// Tokibot: reports OpenCode sessions to the gotchi, with the token counts of
// every finished reply. Written by the Tokibot installer; it removes it again.
""" + PLUGIN_SEND + """
const fed = new Set<string>()
const food: Record<string, { input: number; output: number; cache_read: number; cache_write: number }> = {}
const prompted = new Set<string>()
const calls: Record<string, unknown> = {}          // callID → args, for the shell command afterwards

export const Tokibot = async ({ directory }: { directory: string }) => {
  const base = (sid: string) => ({ session_id: sid, cwd: directory })
  return {
    event: async ({ event }: { event: any }) => {
      const p = event.properties || {}
      if (event.type === "session.created") send("SessionStart", base(p.info?.id ?? ""))
      else if (event.type === "session.deleted") send("SessionEnd", base(p.info?.id ?? ""))
      else if (event.type === "session.error") send("StopFailure", { ...base(p.sessionID ?? ""), error: "unknown" })
      else if (event.type === "permission.asked" || event.type === "permission.updated")
        send("PermissionRequest", { ...base(p.sessionID ?? ""), tool_name: p.type ?? "" })
      else if (event.type === "session.compacted") send("PreCompact", base(p.sessionID ?? ""))
      else if (event.type === "message.updated") {
        const m = p.info || {}
        if (m.role === "user" && !prompted.has(m.id)) {
          prompted.add(m.id)
          send("UserPromptSubmit", base(m.sessionID ?? ""))
        } else if (m.role === "assistant" && m.time?.completed && m.tokens && !fed.has(m.id)) {
          fed.add(m.id)
          const f = (food[m.sessionID] ??= { input: 0, output: 0, cache_read: 0, cache_write: 0 })
          f.input += m.tokens.input ?? 0
          f.output += (m.tokens.output ?? 0) + (m.tokens.reasoning ?? 0)
          f.cache_read += m.tokens.cache?.read ?? 0
          f.cache_write += m.tokens.cache?.write ?? 0
        }
      } else if (event.type === "session.idle") {
        const sid = p.sessionID ?? ""
        const tokens = food[sid]
        delete food[sid]
        send("Stop", tokens ? { ...base(sid), tokens } : base(sid))
      }
    },
    "tool.execute.before": async (input: any, output: any) => {
      calls[input.callID] = output.args ?? {}
      send("PreToolUse", { ...base(input.sessionID ?? ""), tool_name: input.tool, tool_input: output.args ?? {} })
    },
    "tool.execute.after": async (input: any, output: any) => {
      const args = calls[input.callID] ?? input.args ?? {}
      delete calls[input.callID]
      const failed = output?.metadata?.error || output?.metadata?.exit > 0
      send(failed ? "PostToolUseFailure" : "PostToolUse",
           { ...base(input.sessionID ?? ""), tool_name: input.tool, tool_input: args })
    },
  }
}
""",
    "amp": """// Tokibot: reports Amp threads to the gotchi. Written by the Tokibot installer;
// it removes it again.
import type { PluginAPI } from "@ampcode/plugin"

""" + PLUGIN_SEND + """
export const description = "Reports Amp threads to your Tokibot, the e-ink companion."

export default function (amp: PluginAPI) {
  let cwd = ""
  try { cwd = amp.system.workspaceRoot ? amp.helpers.filePathFromURI(amp.system.workspaceRoot) : "" } catch {}
  const base = (e: any) => ({ session_id: e.thread?.id ?? "", cwd })
  amp.on("session.start", async (e: any) => { send("SessionStart", base(e)) })
  amp.on("agent.start", async (e: any) => { send("UserPromptSubmit", base(e)) })
  amp.on("tool.call", async (e: any) => {
    send("PreToolUse", { ...base(e), tool_name: e.tool, tool_input: e.input ?? {} })
    return { action: "allow" }
  })
  amp.on("tool.result", async (e: any) => {
    send(e.status === "error" ? "PostToolUseFailure" : "PostToolUse",
         { ...base(e), tool_name: e.tool, tool_input: e.input ?? {}, is_interrupt: e.status === "cancelled" })
  })
  amp.on("agent.end", async (e: any) => {
    if (e.status === "error") send("StopFailure", { ...base(e), error: "unknown" })
    else send("Stop", base(e))
  })
}
""",
}

CLINE_SCRIPT = """#!/bin/sh
# Tokibot: reports Cline tasks to the gotchi. Written by the Tokibot installer.
exec {cmd} hook --harness cline --event {event}
"""


def harness_entry(name, cmd, event):
    command = f"{cmd} hook --harness {name} --event {event}"
    if name in ("codex", "gemini"):
        entry = {"type": "command", "command": command}
        entry["timeout"] = 10_000 if name == "gemini" else 10      # Gemini counts milliseconds
        if name == "gemini":
            entry["name"] = "tokibot"
        return entry
    if name == "copilot":
        return {"type": "command", "bash": command, "command": command, "timeoutSec": 10}
    if name == "cursor":
        return {"command": command, "timeout": 10}
    return {"command": command, "show_output": False}                # devin


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def has_backup(path):
    """Only the original version is backed up (also by the installer before the rename)."""
    return any(os.path.exists(path + suffix) for suffix in (".tokibot-backup", ".claudegotchi-backup"))


def remove_legacy():
    """Removes what the installer put in place before the rename (Claudegotchi)."""
    shutil.rmtree(LEGACY_DIR, ignore_errors=True)
    old = os.path.expanduser("~/.copilot/hooks/claudegotchi.json")
    if os.path.exists(old):
        os.remove(old)


def save_json(path, data, backup=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if backup and os.path.exists(path) and not has_backup(path):
        shutil.copy2(path, path + ".tokibot-backup")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def strip_flat(hooks):
    for ev in list(hooks):
        kept = [h for h in hooks[ev] if not ours(h.get("command", "") + h.get("bash", ""))]
        if kept:
            hooks[ev] = kept
        else:
            del hooks[ev]


def install_harness(name, cmd):
    h = HARNESSES[name]
    path = os.path.expanduser(h["path"])
    if h["style"] == "plugin":
        launcher = LAUNCHER.replace(os.sep, "/")
        text = PLUGINS[name].replace("__LAUNCHER__", json.dumps(launcher)).replace("__HARNESS__", json.dumps(name))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        return path
    if h["style"] == "kiro":
        hooks = [{"name": f"tokibot-{ev}", "trigger": ev,
                  "action": {"type": "command", "command": f"{cmd} hook --harness kiro --event {ev}"},
                  "timeout": 10, "enabled": True} for ev in h["events"]]
        for hook in hooks:
            if hook["trigger"].endswith("ToolUse"):
                hook["matcher"] = "*"
        save_json(path, {"version": "v1", "hooks": hooks}, backup=False)
        return path
    if h["style"] == "scripts":
        os.makedirs(path, exist_ok=True)
        for ev in h["events"]:
            script = os.path.join(path, ev)
            if os.path.exists(script) and not _ours_file(script):
                print(f"  Cline already has a {ev} hook of its own; left it alone")
                continue
            with open(script, "w") as f:
                f.write(CLINE_SCRIPT.format(cmd=cmd, event=ev))
            os.chmod(script, 0o755)
        return path
    data = load_json(path)
    if h["style"] == "nested":
        strip_ours(data)
        hooks = data.setdefault("hooks", {})
        for ev in h["events"]:
            hooks.setdefault(ev, []).append({"hooks": [harness_entry(name, cmd, ev)]})
    else:
        hooks = data.setdefault("hooks", {})
        strip_flat(hooks)
        for ev in h["events"]:
            hooks.setdefault(ev, []).append(harness_entry(name, cmd, ev))
        if h.get("version"):
            data.setdefault("version", h["version"])
    save_json(path, data)
    return path


def _ours_file(path):
    try:
        with open(path, errors="replace") as f:
            return ours(f.read())
    except OSError:
        return False


def uninstall_harness(name):
    h = HARNESSES[name]
    path = os.path.expanduser(h["path"])
    if not os.path.exists(path):
        return False
    if h["style"] in ("plugin", "kiro"):              # our own file
        if not _ours_file(path):
            return False
        os.remove(path)
        return True
    if h["style"] == "scripts":
        mine = [os.path.join(path, ev) for ev in h["events"] if _ours_file(os.path.join(path, ev))]
        for script in mine:
            os.remove(script)
        return bool(mine)
    data = load_json(path)
    before = json.dumps(data, sort_keys=True)
    if h["style"] == "nested":
        strip_ours(data)
    else:
        strip_flat(data.get("hooks", {}))
        if not data.get("hooks"):
            data.pop("hooks", None)
    if json.dumps(data, sort_keys=True) == before:
        return False
    if name == "copilot" and not data.get("hooks"):
        os.remove(path)                           # our own file
    else:
        save_json(path, data, backup=False)
    return True


def resolve_harnesses(value):
    """"claude,codex" → ["claude", "codex"]; "auto" → Claude Code plus what is installed."""
    names = [n.strip().lower() for n in (value or "claude").split(",") if n.strip()]
    if "auto" in names or "all" in names:
        names = ["claude"] + [n for n, h in HARNESSES.items()
                              if os.path.isdir(os.path.expanduser(h["found"]))]
    unknown = [n for n in names if n != "claude" and n not in HARNESSES]
    if unknown:
        sys.exit(f"Unknown harness: {', '.join(unknown)} (known: claude, {', '.join(HARNESSES)}, auto)")
    return list(dict.fromkeys(names))


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
            g["hooks"] = [h for h in g.get("hooks", []) if not ours(h.get("command", ""))]
            if g["hooks"]:
                groups.append(g)
        if groups:
            hooks[ev] = groups
        else:
            del hooks[ev]
    if not hooks:
        settings.pop("hooks", None)


def read_cfg():
    for path in (os.path.join(TARGET_DIR, "tokibot.json"),
                 os.path.join(LEGACY_DIR, "claudegotchi.json")):
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {}


def resolve(args, old_cfg):
    """url, token, relay from the arguments, falling back to the installed config."""
    url = args.url or old_cfg.get("url") or DEFAULT_URL
    token = args.token if args.token is not None else old_cfg.get("token", "")
    relay = args.relay if args.relay is not None else old_cfg.get("relay", "")
    if args.new_relay:
        relay = f"{RELAY_SERVER}/tokibot-{secrets.token_urlsafe(18)}"
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
    here = os.path.dirname(os.path.abspath(__file__))
    for src, dst in (("tokibot_client.py", CLIENT), ("tokibot.sh", LAUNCHER)):
        shutil.copy2(os.path.join(here, src), dst)
        os.chmod(dst, 0o755)

    settings = load_settings()
    if os.path.exists(SETTINGS) and not has_backup(SETTINGS):
        shutil.copy2(SETTINGS, SETTINGS + ".tokibot-backup")   # back up the original version only

    cfg_path = os.path.join(TARGET_DIR, "tokibot.json")
    old_cfg = read_cfg()

    # Chain an existing status line instead of replacing it
    chain = old_cfg.get("statusline_chain", "")
    sl = settings.get("statusLine") or {}
    if sl.get("command") and not ours(sl["command"]):
        chain = sl["command"]

    url, token, relay = resolve(args, old_cfg)
    harnesses = (["claude"] if args.statusline_only and args.harness is None
                 else resolve_harnesses(args.harness or ",".join(old_cfg.get("harnesses") or ["claude"])))
    with open(cfg_path, "w") as f:
        json.dump({"url": url, "token": token, "relay": relay, "gotchi": resolve_gotchi(args, old_cfg),
                   "statusline_chain": chain, "harnesses": harnesses}, f, indent=2)

    # Forward slashes: on Windows the command runs in Git Bash, which eats backslashes
    cmd = 'sh "{}"'.format(LAUNCHER.replace(os.sep, "/"))
    strip_ours(settings)
    if not args.statusline_only and "claude" in harnesses:
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

    remove_legacy()
    print(f"✓ Client installed: {CLIENT}")
    what = "Status line" if args.statusline_only or "claude" not in harnesses else "Hooks and status line"
    print(f"✓ {what} added to {SETTINGS} (backup: settings.json.tokibot-backup)")
    for name in HARNESSES:
        if name in harnesses:
            print(f"✓ Hooks for {name} added to {install_harness(name, cmd)}")
            if HARNESSES[name].get("note"):
                print(f"  {HARNESSES[name]['note']}")
        elif uninstall_harness(name):
            print(f"✓ Hooks for {name} removed")
    if chain:
        print(f"✓ Your existing status line is still shown: {chain}")
    print(f"→ Gotchi address: {url}")
    if relay:
        print(f"→ Relay: {relay}")
        print("→ Put this into tokibot.toml on the gotchi (it needs Wi-Fi for the relay):\n")
        print(gotchi_settings(token, relay))
    if url != "none":
        print("→ Pairing with your gotchi …")
        if subprocess.run([sys.executable, CLIENT, "pair", resolve_gotchi(args, old_cfg)]).returncode:
            print(f"→ Pair later:  {cmd} pair [tokibot-xxxx]")
    print(f"→ Test:  {cmd} test")
    print("→ Restart running sessions once (Claude Code and the other harnesses) so the hooks take effect.")


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
    for name in ("tokibot_client.py", "tokibot.sh", "install.py"):
        with open(os.path.join(here, name)) as f:
            files[name] = f.read()
    out = ["#!/bin/sh", "# Tokibot: install the hook client in this cloud environment.",
           "set -e", 'd="$(mktemp -d)"']
    for name, text in files.items():
        mark = "END_OF_" + name.replace(".", "_").upper()
        assert mark not in text
        out += [f"cat > \"$d/{name}\" <<'{mark}'", text.rstrip("\n"), mark]
    out.append(f'python3 "$d/install.py" --url none --token "{token}" --relay "{relay}" >/dev/null')
    out.append('rm -rf "$d"')
    print("\n".join(out))
    print("Paste the script above into the cloud environment's setup script.\n"
          "Put this into tokibot.toml on the gotchi:\n\n" + gotchi_settings(token, relay),
          file=sys.stderr)


def uninstall():
    settings = load_settings()
    strip_ours(settings)
    chain = ""
    cfg_path = os.path.join(TARGET_DIR, "tokibot.json")
    if os.path.exists(cfg_path):
        with open(cfg_path) as f:
            chain = json.load(f).get("statusline_chain", "")
    sl = settings.get("statusLine") or {}
    if ours(sl.get("command", "")):
        if chain:
            settings["statusLine"] = {"type": "command", "command": chain}
        else:
            settings.pop("statusLine", None)
    save_settings(settings)
    for name in HARNESSES:
        if uninstall_harness(name):
            print(f"✓ Tokibot removed from {name}")
    shutil.rmtree(TARGET_DIR, ignore_errors=True)
    remove_legacy()
    print("✓ Tokibot removed from Claude Code" + (f"; status line restored to: {chain}" if chain else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=None, help=f"address of the gotchi, or none for relay only (default: {DEFAULT_URL})")
    ap.add_argument("--token", default=None, help="optional token, must match the gotchi")
    ap.add_argument("--gotchi", default=None,
                    help="your gotchi's name as shown on its screen (tokibot-xxxx); "
                         "not needed if it is plugged in with the USB cable")
    ap.add_argument("--relay", default=None, help="ntfy topic URL to publish to as well (\"\" to turn it off)")
    ap.add_argument("--new-relay", action="store_true", help="create a random ntfy.sh topic (and a token)")
    ap.add_argument("--cloud-setup", action="store_true",
                    help="print a setup script for a cloud environment instead of installing")
    ap.add_argument("--statusline-only", action="store_true",
                    help="only the status line (for the budget bars), when the hooks come from the plugin")
    ap.add_argument("--harness", default=None,
                    help="which coding harnesses report to the gotchi, comma-separated: claude, "
                         + ", ".join(HARNESSES) + ", or auto for all found (default: claude, "
                         "or what was installed before)")
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
