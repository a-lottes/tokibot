"""The social page (/social): profile, gotchis nearby, friends, badges, backup.

Changes here apply right away, without a restart (unlike /settings), except a
restore or reset of the identity.
"""
import html
from datetime import datetime

from .mood import ACCESSORIES
from .settings import STYLE

EXTRA_STYLE = """table{width:100%;border-collapse:collapse}td{padding:.35em .2em;border-bottom:1px solid #ddd;vertical-align:middle}
td form{display:inline}td button{margin:0;padding:.3em .8em;font-size:.9em}.muted{color:#888}
.badge{display:inline-block;margin:.2em;padding:.3em .6em;border-radius:12px;background:#222;color:#fff;font-size:.9em}
.badge.locked{background:#ddd;color:#888}.row{display:flex;gap:.5em;align-items:center}
input[type=file]{margin-top:.6em}"""


def _ago(ts, now):
    if not ts:
        return "never"
    s = now - ts
    if s < 120:
        return "just now"
    if s < 7200:
        return f"{int(s // 60)} min ago"
    if s < 172800:
        return f"{int(s // 3600)} h ago"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _signal(rssi):
    return "▮▮▮" if rssi > -60 else "▮▮▯" if rssi > -72 else "▮▯▯"


def _action(action, pub, label, confirm=""):
    onsubmit = f' onsubmit="return confirm(\'{confirm}\')"' if confirm else ""
    return (f'<form method=post action=/social{onsubmit}><input type=hidden name=_token class=tok>'
            f'<input type=hidden name=action value={action}><input type=hidden name=pub value="{pub}">'
            f'<button>{label}</button></form>')


def page(data, token_set, message="", error=False, now=None):
    e = html.escape
    now = now or datetime.now().timestamp()
    me = data["me"]
    msg = f'<p class={"note" if error else "ok"}>{e(message)}</p>' if message else ""
    auth = ('<label>Token</label><input type=password id=tok required>'
            '<small>Needed for every change on this page.</small>' if token_set else
            '<p class=note>No token is set: anyone on this network can change things here. '
            'Set one in the <a href=/settings>settings</a>.</p><input type=hidden id=tok>')

    acc_opts = "".join(
        f'<option value={k}{" selected" if k == me["accessory"] else ""}'
        f'{"" if k in data["unlocked"] else " disabled"}>{e(label)}'
        f'{"" if k in data["unlocked"] else " (locked)"}</option>'
        for k, (label, _) in ACCESSORIES.items())

    rows = []
    for p in data["nearby"]:
        name = e(p["name"]) if p["name"] else '<span class=muted>anonymous gotchi</span>'
        status = ("♥ friend" if p["friend"] else "wants to be friends" if p["incoming"]
                  else "asked …" if p["asked"] else "")
        if p["friend"] or not p["pub"]:
            btn = ""
        elif p["incoming"]:
            btn = _action("befriend", p["pub"], "Accept") + " " + _action("decline", p["pub"], "Decline")
        elif p["asked"]:
            btn = _action("decline", p["pub"], "Cancel")
        else:
            btn = _action("befriend", p["pub"], "Befriend")
        rows.append(f"<tr><td>{name}</td><td>Lv{p['level']}</td><td>{e(p['mood'])}</td>"
                    f"<td title='{p['rssi']} dBm'>{_signal(p['rssi'])}</td><td>{e(status)}</td><td>{btn}</td></tr>")
    nearby = ("<table>" + "".join(rows) + "</table>" if rows else
              "<p class=muted>No gotchi nearby right now.</p>")
    if data["nearby"] and not any(p["pub"] for p in data["nearby"]):
        nearby += ("<p class=muted><small>Anonymous gotchis only show their name once their owner "
                   "opens them for new friends.</small></p>")

    incoming = "".join(
        f'<p class=note>{e(i["name"])} wants to be friends. {_action("befriend", i["pub"], "Accept")} '
        f'{_action("decline", i["pub"], "Decline")}</p>' for i in data["incoming"]
        if not any(p["pub"] == i["pub"] for p in data["nearby"]))

    frows = [f"<tr><td><b>{e(f['name'])}</b> <span class=muted>Lv{f['level']}</span></td>"
             f"<td>friends since {_ago(f['since'], now)}</td><td>last seen {_ago(f['last_seen'], now)}</td>"
             f"<td>met on {f['days']} day{'s' if f['days'] != 1 else ''}</td>"
             f"<td>{_action('unfriend', f['pub'], 'Unfriend', 'Unfriend ' + e(f['name']).replace(chr(39), '') + '?')}</td></tr>"
             for f in data["friends"]]
    friends = ("<table>" + "".join(frows) + "</table>" if frows else
               "<p class=muted>No friends yet. Meet another gotchi and befriend it.</p>")

    badges = "".join(
        f'<span class="badge{"" if got else " locked"}" title="{e(how)}">{e(title)}</span>'
        for (title, how), got in data["badges"].values())

    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Tokibot friends</title><style>{STYLE}{EXTRA_STYLE}</style>
<h1>{e(me["name"])} <span class=muted>Lv{data["level"]}</span></h1>
<p class=muted>Gotchi ID <code>{e(me["id"])}</code> · {data["xp"]} XP</p>{msg}{auth}{incoming}

<h2>Nearby</h2>{nearby}

<h2>Friends ({len(data["friends"])})</h2>{friends}

<h2>Profile</h2>
<form method=post action=/social><input type=hidden name=_token class=tok><input type=hidden name=action value=profile>
<label>Name</label><input type=text name=name value="{e(me["name"])}" maxlength=12>
<small>Up to 12 characters. Other gotchis see it once you are open for new friends.</small>
<label>Accessory</label><select name=accessory>{acc_opts}</select>
<small>Badges and levels unlock more.</small>
<label><input type=checkbox name=open{" checked" if me["open"] else ""}> Open for new friends</label>
<small>Gotchis nearby see your name and level and can ask you to be friends. When off, you are an
anonymous gotchi with an id that changes every 15 minutes; only friends recognise you.</small>
<label><input type=checkbox name=auto{" checked" if me["auto"] else ""}> Say yes automatically</label>
<small>Accept requests from gotchis you met on three different days.</small>
<button>Save</button></form>

<h2>Badges</h2><p>{badges}</p>

<h2>Backup</h2>
<p>Your gotchi's identity, friends and progress live only on this SD card. Keep a backup
to move them to a new card or a new gotchi.</p>
<form method=post action=/social/backup><input type=hidden name=_token class=tok>
<label>Passphrase</label><input type=password name=passphrase minlength=8 required autocomplete=new-password>
<small>At least 8 characters. Without it, the backup cannot be opened, not even by you.</small>
<button>Download backup</button></form>
<label>Restore a backup</label><input type=file id=restore accept=".json">
<input type=password id=rpass placeholder="Passphrase of that backup">
<button onclick="restoreBackup()">Restore and restart</button><p id=rmsg></p>
<form method=post action=/social/reset onsubmit="return confirm('Forget this identity and all friends? This cannot be undone without a backup.')">
<input type=hidden name=_token class=tok><button style="background:#a33">Reset identity</button>
<small>Forgets the key and all friends. The critter keeps its level.</small></form>

<p><a href=/>Live preview</a> · <a href=/settings>Settings</a></p>
<script>
for (const f of document.forms) f.addEventListener('submit', () => {{
  for (const t of f.querySelectorAll('.tok')) t.value = tok.value;
}});
async function restoreBackup() {{
  const f = restore.files[0]; if (!f) return;
  rmsg.textContent = 'Restoring …';
  const r = await fetch('/social/restore', {{method: 'POST', body: await f.text(),
    headers: {{'X-Tokibot-Token': tok.value, 'X-Passphrase': encodeURIComponent(rpass.value)}}}});
  rmsg.textContent = await r.text();
}}
// Refresh the nearby list now and then, unless you are typing
setInterval(() => {{
  const a = document.activeElement;
  if ((!a || a === document.body) && !tok.value) location.replace('/social');
}}, 15000);
</script>"""
