"""HTTP server and program entry point.

Endpoints:
  POST /hook    hook event (from claudegotchi_client.py)
  POST /limits  rate_limits from the status line
  GET  /        live preview in the browser
  GET  /frame.png, GET /state

With [relay] url set, the same events also arrive through an ntfy topic (see relay.py).
"""
import argparse
import errno
import json
import logging
import os
import signal
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

from PIL import Image

from . import config
from .brain import Brain
from .displays import open_display
from .life import Life
from .painter import H, W
from .relay import Relay
from .renderer import Renderer

log = logging.getLogger("claudegotchi")

PREVIEW_HTML = b"""<!doctype html><meta charset=utf-8><title>Claudegotchi</title>
<style>body{font-family:system-ui;background:#eee;display:grid;place-items:center;height:100vh;margin:0}
img{image-rendering:pixelated;width:750px;max-width:95vw;border:12px solid #222;border-radius:10px;background:#fff}</style>
<img id=f src=/frame.png><script>setInterval(()=>f.src='/frame.png?'+Date.now(),2000)</script>"""

# The Pi has no real-time clock. When it only hangs off the USB cable (no NTP), we take
# the time from the timestamp the client sends along.
CLOCK_SANE_AFTER = 1_735_689_600     # 2025-01-01


def maybe_set_clock(ts):
    try:
        ts = float(ts)
    except (TypeError, ValueError):
        return
    if time.time() < CLOCK_SANE_AFTER < ts:
        try:
            time.clock_settime(time.CLOCK_REALTIME, ts)
            log.info("Clock set from the client's timestamp")
        except (OSError, AttributeError):
            pass


def make_dispatch(brain, set_clock):
    """Feeds an event into the brain. Events can arrive twice (directly and through the
    relay), so the client's event id is used to drop the second copy."""
    seen, seen_set, lock = deque(maxlen=500), set(), threading.Lock()

    def dispatch(path, data):
        eid = data.get("id")
        if eid:
            with lock:
                if eid in seen_set:
                    return True
                if len(seen) == seen.maxlen:
                    seen_set.discard(seen[0])
                seen.append(eid)
                seen_set.add(eid)
        if set_clock:
            maybe_set_clock(data.get("ts"))
        if path == "/hook":
            brain.handle_hook(data)
        elif path == "/limits":
            brain.handle_limits(data)
        else:
            return False
        return True

    return dispatch


def make_handler(brain, renderer, token, dispatch):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            log.debug("%s %s", self.address_string(), fmt % args)

        def _send(self, code, body=b"", ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if token and self.headers.get("X-Claudegotchi-Token") != token:
                return self._send(401, b'{"error":"token"}')
            length = int(self.headers.get("Content-Length") or 0)
            if length > 65536:
                return self._send(413)
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._send(400, b'{"error":"json"}')
            if not isinstance(data, dict) or not dispatch(self.path, data):
                return self._send(404)
            self._send(204)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                self._send(200, PREVIEW_HTML, "text/html; charset=utf-8")
            elif path == "/state":
                self._send(200, json.dumps(brain.view(), ensure_ascii=False).encode())
            elif path == "/frame.png":
                img = renderer.frame or Image.new("1", (W, H), 255)
                buf = BytesIO()
                img.save(buf, "PNG")
                self._send(200, buf.getvalue(), "image/png")
            else:
                self._send(404)

    return Handler


def life_path(data_dir):
    """Where the critter keeps its progress: the data partition on the device,
    ~/.claudegotchi elsewhere (e.g. the simulator on a Mac)."""
    for d in (data_dir, os.path.expanduser("~/.claudegotchi")):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            continue
        if os.access(d, os.W_OK):
            return os.path.join(d, "life.json")
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="claudegotchi",
                                 description="Claudegotchi: an e-ink companion for Claude Code")
    ap.add_argument("--config", default=None, help=f"settings file (default: {config.DEFAULT_PATH})")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--relay", default=None, help="ntfy topic URL to subscribe to (overrides [relay] url)")
    ap.add_argument("--sim", action="store_true", help="no e-paper, browser preview only")
    ap.add_argument("--png", default="", help="in sim mode, save every frame to this file")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    cfg = config.load(args.config)
    srv, dev = cfg["server"], cfg["device"]
    port = args.port or int(srv["port"])
    if args.relay is not None:
        cfg["relay"]["url"] = args.relay

    display = open_display("sim" if args.sim else dev["display"], int(dev["rotate"]), args.png)
    path = life_path(dev["data_dir"])
    log.info("Progress file: %s", path or "none (kept in memory)")
    brain = Brain(Life(path))
    renderer = Renderer(brain, display)
    renderer.start()
    dispatch = make_dispatch(brain, set_clock=not args.sim)
    handler = make_handler(brain, renderer, srv["token"], dispatch)
    try:
        server = ThreadingHTTPServer((srv["host"], port), handler)
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        log.error("Port %d is already in use. Is another server running? "
                  "Stop it or pick another port with --port.", port)
        renderer.stop_evt.set()
        return 1
    server.daemon_threads = True

    def shutdown(*_):
        log.info("Bye!")
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    relay = cfg["relay"]
    if relay["url"]:
        Relay(relay["url"], srv["token"], dispatch, relay["auth"]).start()
    log.info("Claudegotchi listening on http://%s:%d", srv["host"], port)
    server.serve_forever()
    renderer.goodbye()
    return 0
