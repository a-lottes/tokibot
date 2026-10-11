"""Look and frame of the gotchi's own web pages: live preview, settings, friends.

Everything is inline (no fonts or scripts from the internet), because the gotchi
is often reachable only over the USB cable. The colours follow the website.
"""
import html
import secrets

# Changes with every start of the app: a page that waits for a restart polls
# /whoami until it sees another value, then reloads.
STARTED = secrets.token_hex(4)

NAV = [("/", "Live"), ("/settings", "Settings"), ("/social", "Friends")]

CSS = """:root{--paper:#f1efe8;--card:#f8f7f2;--ink:#1c1c1a;--muted:#6d6b63;--rule:#c9c5b8;
--accent:#ff4f00;--accent-2:#d84300;--on-accent:#fff;--ok:#dcefd9;--ok-ink:#1d4d1a;--warn:#fff1c7;--warn-ink:#5a4500;
--bad:#b3261e;--field:#fff;--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root{--paper:#161614;--card:#21201d;--ink:#e8e5da;--muted:#9a978c;--rule:#3a3934;
--ok:#1f3a1c;--ok-ink:#cdeac8;--warn:#3d3215;--warn-ink:#f3e2a8;--bad:#e5675e;--field:#2b2a26}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:660px;margin:0 auto;padding:0 16px 3em}
header{display:flex;flex-wrap:wrap;align-items:center;gap:.6em 1em;padding:1em 0 .8em;border-bottom:1px solid var(--rule);margin-bottom:1.2em}
.brand{font-family:var(--mono);font-weight:700;font-size:1.05em;text-decoration:none;color:var(--ink);margin-right:auto}
.brand span{color:var(--accent)}.brand small{font-weight:400;color:var(--muted);margin-left:.4em}
nav{display:flex;gap:.3em}
nav a{font-family:var(--mono);font-size:.9em;text-decoration:none;color:var(--ink);padding:.35em .8em;border:1px solid var(--rule);border-radius:999px}
nav a:hover{border-color:var(--ink)}nav a.on{background:var(--ink);color:var(--paper);border-color:var(--ink)}
h1{font-size:1.5em;margin:.2em 0 .1em}h2{font-size:1.05em;margin:0 0 .6em;font-family:var(--mono);letter-spacing:.02em}
.card{background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:1em 1.1em;margin:0 0 1em}
.card>p:first-of-type{margin-top:0}
label{display:block;margin-top:.9em;font-weight:600}.card>label:first-of-type,.card>h2+label{margin-top:0}
label.check{display:flex;gap:.5em;align-items:flex-start;font-weight:600}label.check input{margin-top:.3em}label.check small{font-weight:400}
input[type=text],input[type=password],select{width:100%;margin-top:.3em;padding:.55em .65em;border:1px solid var(--rule);
border-radius:8px;background:var(--field);color:var(--ink);font:inherit}
input:focus,select:focus{outline:2px solid var(--accent);outline-offset:1px}
small,.muted{color:var(--muted)}small{display:block;margin-top:.25em;font-size:.85em}
button{margin-top:1em;padding:.6em 1.2em;border:0;border-radius:8px;background:var(--accent);color:var(--on-accent);font:inherit;font-weight:600;cursor:pointer}
button:hover{background:var(--accent-2)}button.ghost{background:transparent;color:var(--ink);border:1px solid var(--rule)}
button.ghost:hover{border-color:var(--ink)}button.danger{background:var(--bad)}
.msg{padding:.7em .9em;border-radius:10px;margin:0 0 1em}.ok{background:var(--ok);color:var(--ok-ink)}
.note{background:var(--warn);color:var(--warn-ink);padding:.7em .9em;border-radius:10px}
code{font-family:var(--mono);font-size:.9em;background:var(--paper);border:1px solid var(--rule);padding:0 .3em;border-radius:4px}
details{margin-top:.7em}summary{cursor:pointer;color:var(--accent-2);font-weight:600}details p{margin:.5em 0}
.row{display:flex;gap:.6em;align-items:center;flex-wrap:wrap}.row button{margin-top:0}
a{color:var(--accent-2)}.go{display:inline-block;margin-top:.8em;font-weight:600;text-decoration:none}
footer{margin-top:2em;color:var(--muted);font-size:.85em;text-align:center}"""

# Fills every form's hidden token fields from the one token box, remembers the
# token in this browser if wanted, and keeps a token that was just set on the
# settings page.
TOKEN_JS = """const tok = document.getElementById('tok'), keep = document.getElementById('keep');
const store = {get(k){try{return localStorage.getItem(k)}catch(e){return null}},
  set(k,v){try{v===null?localStorage.removeItem(k):localStorage.setItem(k,v)}catch(e){}}};
try {
  const fresh = sessionStorage.getItem('tokibot-new-token');
  sessionStorage.removeItem('tokibot-new-token');
  if (fresh && !WRONG_TOKEN && (!keep || keep.checked)) store.set('tokibot-token', fresh);
} catch (e) {}
if (WRONG_TOKEN) store.set('tokibot-token', null);
if (tok && !tok.value) tok.value = store.get('tokibot-token') || '';
// No token at hand yet: show where to find it right away
if (tok && tok.type === 'password' && !tok.value) {
  const help = tok.closest('.card') && tok.closest('.card').querySelector('details');
  if (help) help.open = true;
}
function remember() {
  if (keep) store.set('tokibot-token', keep.checked && tok.value ? tok.value : null);
}
for (const f of document.forms) f.addEventListener('submit', () => {
  remember();
  for (const t of f.querySelectorAll('.tok')) t.value = tok ? tok.value : '';
});"""

WAIT_JS = """(function(){
  const old = %s, dest = %s, t0 = Date.now(), out = document.getElementById('waitmsg');
  async function poll() {
    try {
      const r = await fetch('/whoami', {cache: 'no-store'});
      if ((await r.json()).started !== old) return location.replace(dest);
    } catch (e) {}
    if (Date.now() - t0 < 180000) setTimeout(poll, 1500);
    else if (out) out.textContent = 'The gotchi is not back yet. Check its screen, then reload this page.';
  }
  setTimeout(poll, 2000);
})();"""


def wait_script(dest):
    """JS that reloads `dest` once the app runs again after a restart or reboot."""
    return WAIT_JS % (f'"{STARTED}"', '"' + dest.replace('"', "") + '"')


def message(text, error=False, waiting=False):
    if not text:
        return ""
    e = html.escape
    extra = ' <span id=waitmsg>The page reloads by itself when it is done.</span>' if waiting else ""
    return f'<p class="msg {"note" if error else "ok"}">{e(text)}{extra}</p>'


def token_help(where):
    """Where the token comes from, for the token box and the settings field."""
    return f"""<details><summary>Where do I find the token?</summary>
<p>Pairing makes it. The first time you install the client on a computer, a gotchi without
a token creates one and hands it over. Your computer keeps it in
<code>~/.tokibot/tokibot.json</code>; show it there with
<code>grep token ~/.tokibot/tokibot.json</code> (on Windows, in Git Bash). With the Claude Code
plugin it is under <code>/plugin</code> → Tokibot → Token, if you entered one there.</p>
<p>The gotchi keeps the same token in {where}, under <code>[server]</code> as <code>token</code>.
Lost it? Edit it there.</p>
<p>When you set a new token on the settings page, give it to your computers too: run the
install script again with <code>--token NEW</code>, or enter it under <code>/plugin</code>.</p></details>"""


def token_box(token_set, where, wrong=False):
    """The one token field of a page. Forms copy it into their hidden .tok fields."""
    if not token_set:
        return ('<div class=card><p class=note>No token is set: anyone on this network can change '
                'things here. Pair a client or set one under <a href="/settings#connection">'
                'Connection</a>.</p><input type=hidden id=tok></div>')
    return f"""<div class=card><label for=tok>Token</label>
<input type=password id=tok autocomplete=current-password{' autofocus' if wrong else ''}>
<small>On the computer you paired, <code>grep token ~/.tokibot/tokibot.json</code> shows it.</small>
<label class=check style="font-weight:400"><input type=checkbox id=keep checked> Remember it in this browser</label>
{token_help(where)}</div>"""


def layout(title, active, body, name="", script="", wrong_token=False, css=""):
    e = html.escape
    nav = "".join(f'<a href="{href}"{" class=on" if href == active else ""}>{label}</a>'
                  for href, label in NAV)
    gotchi = f"<small>{e(name)}</small>" if name else ""
    return f"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>{e(title)} · Tokibot</title>
<style>{CSS}{css}</style><div class=wrap>
<header><a class=brand href="/">toki<span>bot</span>{gotchi}</a><nav>{nav}</nav></header>
{body}</div>
<script>const WRONG_TOKEN = {"true" if wrong_token else "false"};
{TOKEN_JS}
{script}</script></html>"""


def preview_page(name=""):
    body = """<div class=card style="text-align:center;padding:1.2em">
<img id=f src=/frame.png alt="What the gotchi shows right now" style="image-rendering:pixelated;width:100%;
max-width:620px;border:10px solid #1c1c1a;border-radius:12px;background:#fff">
<p class=muted style="margin:.6em 0 0"><small>The same picture as on the e-paper, refreshed every 2 s.</small></p></div>"""
    return layout("Live", "/", body, name, "setInterval(()=>f.src='/frame.png?'+Date.now(),2000)")
