"""HTTP-Server und Programmstart.

Endpunkte:
  POST /hook    – Hook-Event (vom claudegotchi_client.py)
  POST /limits  – rate_limits aus der Statusline
  GET  /        – Live-Vorschau im Browser
  GET  /frame.png, GET /state
"""
import argparse
import errno
import json
import logging
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

from PIL import Image

from . import config
from .brain import Brain
from .displays import open_display
from .painter import H, W
from .renderer import Renderer

log = logging.getLogger("claudegotchi")

PREVIEW_HTML = b"""<!doctype html><meta charset=utf-8><title>Claudegotchi</title>
<style>body{font-family:system-ui;background:#eee;display:grid;place-items:center;height:100vh;margin:0}
img{image-rendering:pixelated;width:750px;max-width:95vw;border:12px solid #222;border-radius:10px;background:#fff}</style>
<img id=f src=/frame.png><script>setInterval(()=>f.src='/frame.png?'+Date.now(),2000)</script>"""

# Der Pi hat keine Echtzeituhr. Hängt er nur am USB-Kabel (kein NTP), übernehmen wir
# die Uhrzeit aus dem Zeitstempel, den der Client mitschickt.
CLOCK_SANE_AFTER = 1_735_689_600     # 2025-01-01


def maybe_set_clock(ts):
    try:
        ts = float(ts)
    except (TypeError, ValueError):
        return
    if time.time() < CLOCK_SANE_AFTER < ts:
        try:
            time.clock_settime(time.CLOCK_REALTIME, ts)
            log.info("Uhrzeit vom Mac übernommen")
        except (OSError, AttributeError):
            pass


def make_handler(brain, renderer, token, set_clock):
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
            if set_clock:
                maybe_set_clock(data.get("ts"))
            if self.path == "/hook":
                brain.handle_hook(data)
            elif self.path == "/limits":
                brain.handle_limits(data)
            else:
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


def main(argv=None):
    ap = argparse.ArgumentParser(prog="claudegotchi",
                                 description="Claudegotchi – E-Ink-Begleiter für Claude Code")
    ap.add_argument("--config", default=None, help=f"Einstellungen (Standard: {config.DEFAULT_PATH})")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--sim", action="store_true", help="ohne e-Paper, nur Browser-Vorschau")
    ap.add_argument("--png", default="", help="im Sim-Modus jedes Bild hierhin speichern")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    cfg = config.load(args.config)
    srv, dev = cfg["server"], cfg["device"]
    port = args.port or int(srv["port"])

    display = open_display("sim" if args.sim else dev["display"], int(dev["rotate"]), args.png)
    brain = Brain()
    renderer = Renderer(brain, display)
    renderer.start()
    handler = make_handler(brain, renderer, srv["token"], set_clock=not args.sim)
    try:
        server = ThreadingHTTPServer((srv["host"], port), handler)
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        log.error("Port %d ist schon belegt. Läuft noch ein anderes Gotchi? "
                  "Beenden oder mit --port einen anderen Port wählen.", port)
        renderer.stop_evt.set()
        return 1
    server.daemon_threads = True

    def shutdown(*_):
        log.info("Tschüss!")
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    log.info("Claudegotchi lauscht auf http://%s:%d", srv["host"], port)
    server.serve_forever()
    renderer.goodbye()
    return 0
