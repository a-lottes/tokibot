"""The settings page: edit tokibot.toml in the browser, then apply it by restarting.

Changes are written back into the same file, line by line, so the comments in it
stay. On the device the file sits on the read-only boot partition, which is
remounted read-write just for the write.
"""
import html
import json
import os
import re
import subprocess

from . import __version__, webui
from .displays import DISPLAYS, resolve

# (section, key, label, kind, help)
FIELDS = [
    ("device", "display", "Display", "display", "The revision is printed on the back of the display board."),
    ("device", "rotate", "Rotate display", "rotate", ""),
    ("device", "timezone", "Time zone", "text", "e.g. Europe/Berlin"),
    ("wifi", "ssid", "Wi-Fi name", "text", "Leave empty to use only the USB cable."),
    ("wifi", "psk", "Wi-Fi password", "secret", ""),
    ("wifi", "country", "Wi-Fi country", "text", "Two letters, e.g. DE."),
    ("wifi2", "ssid", "Second Wi-Fi name", "text",
     "e.g. your phone's hotspot. Used when the first Wi-Fi is out of reach."),
    ("wifi2", "psk", "Second Wi-Fi password", "secret", ""),
    ("wifi3", "ssid", "Third Wi-Fi name", "text", "Used when neither of the others is in reach."),
    ("wifi3", "psk", "Third Wi-Fi password", "secret", ""),
    ("usb", "enabled", "USB network", "bool", "The gotchi shows up as a network adapter on the USB data port."),
    ("server", "token", "Token", "secret",
     "Clients send it with every event and these pages ask for it. Pairing a client sets one "
     "if none is set yet. After changing it, give your computers the new one (see below)."),
    ("relay", "url", "Relay URL", "text", "ntfy topic for cloud sessions, e.g. https://ntfy.sh/tokibot-…"),
    ("relay", "auth", "Relay access token", "secret", "Only for a protected or self-hosted ntfy server."),
    ("social", "enabled", "Meet other gotchis (Bluetooth)", "bool",
     "Find gotchis nearby and make friends. Name, profile and friends are on the Friends page."),
    ("leaderboard", "enabled", "Join the highscores", "bool",
     "Posts its name, level, and food and XP per day to tokibot.lottes.dev. Nothing about your work."),
]

# (anchor, title, sections shown in it)
GROUPS = [
    ("device", "Device", ("device",)),
    ("network", "Network", ("wifi", "wifi2", "wifi3", "usb")),
    ("connection", "Connection", ("server", "relay")),
    ("community", "Community", ("social", "leaderboard")),
]

# Applied by the image's init scripts at boot, so changing them needs a reboot.
# Everything else only needs the app to start again.
REBOOT_FOR = ("wifi", "wifi2", "wifi3", "usb", ("device", "timezone"), ("social", "enabled"))


def needs_reboot(changes):
    return any(sec in REBOOT_FOR or (sec, key) in REBOOT_FOR for sec, key in changes)


def config_where(path, on_device):
    """Where tokibot.toml is, in words, for the token help."""
    if on_device:
        return ("<code>tokibot.toml</code> on the SD card's boot partition (the drive "
                "<b>TOKIBOT</b> when you put the card into your computer)")
    return f"<code>{html.escape(path or 'tokibot.toml')}</code>"


def fmt(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def update_toml(text, changes):
    """Set {(section, key): value} in TOML text, keeping comments and layout."""
    lines = text.splitlines()
    pending = dict(changes)
    section, ends = None, {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        m = re.match(r"\[([^\]]+)\]", stripped)
        if m:
            section = m.group(1).strip()
            ends[section] = i + 1
            continue
        m = re.match(r"([A-Za-z0-9_-]+)\s*=", stripped)
        if section and m:
            ends[section] = i + 1
            key = (section, m.group(1))
            if key in pending:
                lines[i] = f"{m.group(1)} = {fmt(pending.pop(key))}"
    for (sec, key), value in pending.items():          # keys the file does not have yet
        if sec in ends:
            lines.insert(ends[sec], f"{key} = {fmt(value)}")
            for s in ends:
                if ends[s] >= ends[sec] and s != sec:
                    ends[s] += 1
            ends[sec] += 1
        else:
            lines += ["", f"[{sec}]", f"{key} = {fmt(value)}"]
            ends[sec] = len(lines)
    return "\n".join(lines) + "\n"


def changes_from_form(form, cfg):
    """Form fields (dict of str) -> {(section, key): value}. Empty secrets are kept."""
    out = {}
    for sec, key, _, kind, _ in FIELDS:
        name = f"{sec}.{key}"
        if kind == "bool":
            value = name in form
        elif kind == "rotate":
            value = 180 if form.get(name) == "180" else 0
        elif kind == "display":
            value = form.get(name, "")
            if value not in DISPLAYS or value == resolve(cfg.get(sec, {}).get(key, "")):
                continue                  # unknown, or the same panel under a Pwnagotchi name
        else:
            value = form.get(name, "").strip()
            if kind == "secret" and not value:
                if f"{name}.clear" not in form:
                    continue
                value = ""
        if cfg.get(sec, {}).get(key) != value:
            out[(sec, key)] = value
    return out


def write_config(path, changes, remove=()):
    """Write changes into the file. remove: files next to it to delete in the same go
    (the boot partition is writable only for a moment)."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    new = update_toml(text, changes)
    on_boot = path.startswith("/boot/")
    if on_boot:
        subprocess.run(["mount", "-o", "remount,rw", "/boot"], check=True)
    try:
        if changes:
            tmp = path + ".new"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(new)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        for name in remove:
            try:
                os.remove(name)
            except FileNotFoundError:
                pass
    finally:
        if on_boot:
            subprocess.run(["sync"])
            subprocess.run(["mount", "-o", "remount,ro", "/boot"])


def _field(cfg, sec, key, label, kind, hint):
    e = html.escape
    name, value = f"{sec}.{key}", cfg.get(sec, {}).get(key, "")
    small = f"<small>{e(hint)}</small>" if hint else ""
    if kind == "bool":
        return (f'<label class=check><input type=checkbox name="{name}"{" checked" if value else ""}>'
                f"<span>{e(label)}{small}</span></label>")
    if kind == "rotate":
        opts = "".join(f'<option value={v}{" selected" if int(value or 0) == v else ""}>{v}°</option>'
                       for v in (0, 180))
        field = f'<label>{e(label)}<select name="{name}">{opts}</select></label>'
    elif kind == "display":
        current = resolve(value)
        opts = "".join(f'<option value="{k}"{" selected" if k == current else ""}>{e(lbl)}</option>'
                       for k, (lbl, _) in DISPLAYS.items())
        if current is None:
            opts = f'<option value="" selected>{e(str(value))} (unknown)</option>' + opts
        field = f'<label>{e(label)}<select name="{name}">{opts}</select></label>'
    elif kind == "secret":
        ph = "unchanged (set)" if value else "not set"
        field = (f'<label>{e(label)}<input type=password name="{name}" placeholder="{ph}" '
                 f'autocomplete=new-password></label>' +
                 (f'<label class=check style="font-weight:400;margin-top:.3em"><input type=checkbox '
                  f'name="{name}.clear"> remove</label>' if value else ""))
    else:
        field = f'<label>{e(label)}<input type=text name="{name}" value="{e(str(value))}"></label>'
    return field + small


def page(cfg, token_set, message="", app_source="built-in", error=False, name="", cfg_path="",
         on_device=False, waiting=False, wrong_token=False):
    e = html.escape
    where = config_where(cfg_path, on_device)
    cards = []
    for anchor, title, sections in GROUPS:
        rows = [_field(cfg, *f) for f in FIELDS if f[0] in sections]
        if anchor == "connection":
            if not token_set:
                rows.insert(0, "<p class=note>No token is set yet: anyone on this network can change "
                               "the settings. Set one here, or pair a client.</p>")
                rows.append(webui.token_help(where))     # else the token box at the top has it
        if anchor == "community":
            rows.append('<a class=go href=/social>Name, profile and friends →</a>')
        cards.append(f'<section class=card id={anchor}><h2>{title}</h2>{"".join(rows)}</section>')
    applies = ("Saving restarts the app, which takes a few seconds. Changes to Wi-Fi, USB, "
               "time zone and Bluetooth reboot the gotchi (about a minute)." if on_device else
               "Saving restarts the simulator with the new settings.")
    body = f"""<h1>Settings</h1>{webui.message(message, error, waiting)}
{webui.token_box(True, where, wrong_token) if token_set else "<input type=hidden id=tok>"}
<form method=post action=/settings><input type=hidden name=_token class=tok>
{"".join(cards)}
<div class=card><button style="margin-top:0">Save and apply</button><small>{applies}</small></div>
</form>
<section class=card id=update><h2>App update</h2>
<p>Running version <b>{e(__version__)}</b> ({e(app_source)}). Upload a
<code>tokibot-app.tar.gz</code> from <code>make bundle</code> or a GitHub release.</p>
<div class=row><input type=file id=bundle accept=".gz"><button type=button onclick="upload()">Install update</button></div>
<form method=post action=/update/reset><input type=hidden name=_token class=tok>
<button class=ghost>Back to the built-in version</button></form>
<p id=up></p></section>"""
    script = """const sf = document.querySelector('form[action="/settings"]');
sf.addEventListener('submit', () => {
  const n = sf.elements['server.token'].value.trim();
  try { if (n) sessionStorage.setItem('tokibot-new-token', n); } catch (e) {}
});
async function upload() {
  const f = bundle.files[0]; if (!f) return;
  remember(); up.textContent = 'Uploading …';
  const r = await fetch('/update', {method: 'POST', body: f, headers: {'X-Tokibot-Token': tok.value}});
  up.textContent = await r.text();
  if (r.ok) {
    up.textContent += ' The page reloads by itself when it is done.';
    """ + webui.wait_script("/settings?applied=update") + """
  }
}"""
    if waiting:
        script += "\n" + webui.wait_script("/settings?applied=1")
    return webui.layout("Settings", "/settings", body, name, script, wrong_token)
