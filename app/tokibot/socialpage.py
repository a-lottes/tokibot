"""The social page (/social): profile, gotchis nearby, friends, badges, backup.

Changes here apply right away, without a restart (unlike /settings), except a
restore or reset of the identity.
"""
import html
from datetime import datetime

from . import settings, webui
from .mood import ACCESSORIES

EXTRA_STYLE = """table{width:100%;border-collapse:collapse}td{padding:.45em .3em;border-bottom:1px solid var(--rule);vertical-align:middle}
tr:last-child td{border-bottom:0}td form{display:inline}td button{margin:0;padding:.3em .8em;font-size:.9em}
.badge{display:inline-block;margin:.2em;padding:.3em .7em;border-radius:999px;background:var(--ink);color:var(--paper);font-size:.9em}
.badge.locked{background:transparent;color:var(--muted);border:1px dashed var(--rule)}
.me{display:flex;align-items:baseline;gap:.6em;flex-wrap:wrap}.me h1{margin:0}
.count{font-family:var(--mono);font-size:.85em;color:var(--muted);font-weight:400}
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


def page(data, token_set, message="", error=False, now=None, name="", cfg_path="", on_device=False,
         waiting=False, wrong_token=False):
    e = html.escape
    now = now or datetime.now().timestamp()
    me = data["me"]
    where = settings.config_where(cfg_path, on_device)
    auth = (webui.token_box(True, where, wrong_token) if token_set else
            '<p class=note>No token is set: anyone on this network can change things here. '
            'Set one in the <a href="/settings#connection">settings</a>.</p><input type=hidden id=tok>')

    acc_opts = "".join(
        f'<option value={k}{" selected" if k == me["accessory"] else ""}'
        f'{"" if k in data["unlocked"] else " disabled"}>{e(label)}'
        f'{"" if k in data["unlocked"] else " (locked)"}</option>'
        for k, (label, _) in ACCESSORIES.items())

    rows = []
    for p in data["nearby"]:
        who = e(p["name"]) if p["name"] else '<span class=muted>anonymous gotchi</span>'
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
        rows.append(f"<tr><td>{who}</td><td>Lv{p['level']}</td><td>{e(p['mood'])}</td>"
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

    n_friends = len(data["friends"])
    body = f"""<div class=me><h1>{e(me["name"])}</h1><span class=count>Lv{data["level"]} · {data["xp"]} XP</span></div>
<p class=muted style="margin-top:.2em"><small>Gotchi ID <code>{e(me["id"])}</code></small></p>
{webui.message(message, error, waiting)}{auth}{incoming}

<section class=card id=nearby><h2>Nearby</h2>{nearby}</section>

<section class=card id=friends><h2>Friends <span class=count>{n_friends}</span></h2>{friends}</section>

<section class=card id=profile><h2>Profile</h2>
<form method=post action=/social><input type=hidden name=_token class=tok><input type=hidden name=action value=profile>
<label>Name<input type=text name=name value="{e(me["name"])}" maxlength=12></label>
<small>Up to 12 characters. Other gotchis see it while you are open for new friends.</small>
<label>Accessory<select name=accessory>{acc_opts}</select></label>
<small>Badges and levels unlock more.</small>
<label class=check><input type=checkbox name=open{" checked" if me["open"] else ""}><span>Open for new friends
<small>Gotchis nearby see your name and level and can ask you to be friends. When off, you are an
anonymous gotchi with an id that changes every 15 minutes; only friends recognise you.</small></span></label>
<label class=check><input type=checkbox name=auto{" checked" if me["auto"] else ""}><span>Say yes automatically
<small>Accept requests from gotchis you met on three different days.</small></span></label>
<button>Save profile</button></form></section>

<section class=card id=badges><h2>Badges</h2><p>{badges}</p></section>

<section class=card id=backup><h2>Backup</h2>
<p>Your gotchi's identity, friends and progress live only on this SD card. Keep a backup
to move them to a new card or a new gotchi.</p>
<form method=post action=/social/backup><input type=hidden name=_token class=tok>
<label>Passphrase<input type=password name=passphrase minlength=8 required autocomplete=new-password></label>
<small>At least 8 characters. Without it, the backup cannot be opened, not even by you.</small>
<button>Download backup</button></form>
<label style="margin-top:1.4em">Restore a backup</label><input type=file id=restore accept=".json">
<input type=password id=rpass placeholder="Passphrase of that backup">
<button type=button onclick="restoreBackup()">Restore and restart</button><p id=rmsg></p>
<form method=post action=/social/reset onsubmit="return confirm('Forget this identity and all friends? This cannot be undone without a backup.')">
<input type=hidden name=_token class=tok><button class=danger>Reset identity</button>
<small>Forgets the key and all friends. The critter keeps its level.</small></form></section>

<p class=muted><small>Bluetooth, highscores and the token are in the <a href="/settings#community">settings</a>.</small></p>"""
    script = """async function restoreBackup() {
  const f = restore.files[0]; if (!f) return;
  remember(); rmsg.textContent = 'Restoring …';
  const r = await fetch('/social/restore', {method: 'POST', body: await f.text(),
    headers: {'X-Tokibot-Token': tok.value, 'X-Passphrase': encodeURIComponent(rpass.value)}});
  rmsg.textContent = await r.text();
  if (r.ok) {
    rmsg.textContent += ' The page reloads by itself when it is done.';
    """ + webui.wait_script("/social?applied=restore") + """
  }
}
// Refresh the nearby list now and then, unless you are busy with the page
let busy = false;
document.addEventListener('input', () => { busy = true; });
setInterval(() => {
  const a = document.activeElement;
  if (!busy && (!a || a === document.body)) location.replace('/social');
}, 15000);"""
    if waiting:
        script += "\n" + webui.wait_script("/social?applied=1")
    return webui.layout("Friends", "/social", body, name, script, wrong_token, EXTRA_STYLE)
