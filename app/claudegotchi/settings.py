"""The settings page: edit claudegotchi.toml in the browser.

Changes are written back into the same file, line by line, so the comments in it
stay. On the device the file sits on the read-only boot partition, which is
remounted read-write just for the write.
"""
import html
import json
import os
import re
import subprocess

from . import __version__

# (section, key, label, kind, help)
FIELDS = [
    ("wifi", "ssid", "Wi-Fi name", "text", "Leave empty to use only the USB cable."),
    ("wifi", "psk", "Wi-Fi password", "secret", ""),
    ("wifi", "country", "Wi-Fi country", "text", "Two letters, e.g. DE."),
    ("device", "timezone", "Time zone", "text", "e.g. Europe/Berlin"),
    ("device", "rotate", "Rotate display", "rotate", ""),
    ("usb", "enabled", "USB network", "bool", "The gotchi shows up as a network adapter on the USB data port."),
    ("server", "token", "Token", "secret", "Clients and this page need it. Strongly recommended."),
    ("relay", "url", "Relay URL", "text", "ntfy topic for cloud sessions, e.g. https://ntfy.sh/claudegotchi-…"),
    ("relay", "auth", "Relay access token", "secret", "Only for a protected or self-hosted ntfy server."),
    ("social", "enabled", "Meet other gotchis (Bluetooth)", "bool",
     "Your gotchi stays anonymous until you open it on the social page."),
]

STYLE = """body{font-family:system-ui;max-width:560px;margin:2em auto;padding:0 16px;color:#222;background:#f6f6f4}
h1{font-size:1.4em}h2{font-size:1.1em;margin-top:2em}label{display:block;margin-top:1em;font-weight:600}
input[type=text],input[type=password],select{width:100%;padding:.5em;box-sizing:border-box;border:1px solid #bbb;border-radius:6px}
small{color:#666;display:block;margin-top:.2em}button{margin-top:1.5em;padding:.6em 1.2em;border:0;border-radius:6px;background:#222;color:#fff;font-size:1em}
.note{background:#fff3cd;padding:.7em;border-radius:6px}.ok{background:#d4edda;padding:.7em;border-radius:6px}
code{background:#eee;padding:0 .3em;border-radius:3px}"""


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
        else:
            value = form.get(name, "").strip()
            if kind == "secret" and not value:
                if f"{name}.clear" not in form:
                    continue
                value = ""
        if cfg.get(sec, {}).get(key) != value:
            out[(sec, key)] = value
    return out


def write_config(path, changes):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    new = update_toml(text, changes)
    on_boot = path.startswith("/boot/")
    if on_boot:
        subprocess.run(["mount", "-o", "remount,rw", "/boot"], check=True)
    try:
        tmp = path + ".new"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(new)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if on_boot:
            subprocess.run(["sync"])
            subprocess.run(["mount", "-o", "remount,ro", "/boot"])


def page(cfg, token_set, message="", app_source="built-in", error=False):
    e = html.escape
    rows = []
    for sec, key, label, kind, hint in FIELDS:
        name, value = f"{sec}.{key}", cfg.get(sec, {}).get(key, "")
        if kind == "bool":
            field = (f'<label><input type=checkbox name="{name}"{" checked" if value else ""}> '
                     f"{e(label)}</label>")
        elif kind == "rotate":
            opts = "".join(f'<option value={v}{" selected" if int(value or 0) == v else ""}>{v}°</option>'
                           for v in (0, 180))
            field = f'<label>{e(label)}</label><select name="{name}">{opts}</select>'
        elif kind == "secret":
            ph = "unchanged (set)" if value else "not set"
            field = (f'<label>{e(label)}</label><input type=password name="{name}" placeholder="{ph}" '
                     f'autocomplete=new-password>' +
                     (f'<small><input type=checkbox name="{name}.clear"> remove</small>' if value else ""))
        else:
            field = f'<label>{e(label)}</label><input type=text name="{name}" value="{e(str(value))}">'
        rows.append(field + (f"<small>{e(hint)}</small>" if hint else ""))
    auth = ('<label>Current token</label><input type=password name=_token id=tok required>'
            if token_set else
            '<p class=note>No token is set: anyone on this network can change the settings. '
            'Set one below.</p><input type=hidden name=_token id=tok>')
    msg = f'<p class={"note" if error else "ok"}>{e(message)}</p>' if message else ""
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Claudegotchi settings</title><style>{STYLE}</style>
<h1>Claudegotchi settings</h1>{msg}
<form method=post action=/settings>{auth}{"".join(rows)}
<button>Save and restart</button></form>
<h2>App update</h2>
<p>Running version <b>{e(__version__)}</b> ({e(app_source)}). Upload a
<code>claudegotchi-app.tar.gz</code> from <code>make bundle</code> or a GitHub release.</p>
<input type=file id=bundle accept=".gz"> <button onclick="upload()">Install update</button>
<form method=post action=/update/reset><input type=hidden name=_token id=tok2>
<button onclick="tok2.value=tok.value">Back to the built-in version</button></form>
<p id=up></p>
<script>
async function upload(){{
  const f=bundle.files[0]; if(!f) return;
  up.textContent='Uploading …';
  const r=await fetch('/update',{{method:'POST',body:f,headers:{{'X-Claudegotchi-Token':tok.value}}}});
  up.textContent=await r.text();
}}
</script>
<p><a href=/>Live preview</a> · <a href=/social>Friends</a></p>"""
