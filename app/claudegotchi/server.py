"""HTTP server and program entry point.

Endpoints:
  POST /hook    hook event (from claudegotchi_client.py)
  POST /limits  rate_limits from the status line
  GET  /        live preview in the browser
  GET  /frame.png, GET /state
  GET  /settings, POST /settings   settings page (writes claudegotchi.toml, then restarts)
  POST /update, POST /update/reset app update bundle (see update.py)

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
import urllib.parse
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

from PIL import Image

from . import battery as battery_mod
from . import config, settings, update
from .brain import Brain
from .displays import open_display
from .life import Life
from .painter import H, W
from .relay import Relay
from .renderer import Renderer

log = logging.getLogger("claudegotchi")

PREVIEW_HTML = b"""<!doctype html><meta charset=utf-8><title>Claudegotchi</title>
<style>body{font-family:system-ui;background:#eee;display:grid;place-items:center;min-height:100vh;margin:0}
img{image-rendering:pixelated;width:750px;max-width:95vw;border:12px solid #222;border-radius:10px;background:#fff}</style>
<div><img id=f src=/frame.png><p style="text-align:center"><a href=/settings>Settings</a></p></div><script>setInterval(()=>f.src='/frame.png?'+Date.now(),2000)</script>"""

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


RESTART = 75          # exit code that asks claudegotchi-run to start the app again


class Control:
    """What the web pages may do to the running service."""
    def __init__(self, cfg_path, cfg, on_device):
        self.cfg_path, self.cfg, self.on_device = cfg_path, cfg, on_device
        self.exit_code = 0
        self.stop = lambda: None

    def restart(self, reboot=False):
        def later():
            time.sleep(1.5)
            if reboot and self.on_device:
                os.system("reboot")
            else:
                self.exit_code = RESTART
                self.stop()
        threading.Thread(target=later, daemon=True).start()


def make_handler(brain, renderer, token, dispatch, control=None):
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

        def _same_origin(self):
            origin = self.headers.get("Origin")
            return not origin or urllib.parse.urlparse(origin).netloc == self.headers.get("Host")

        def _form(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length > 65536:
                return None
            raw = self.rfile.read(length).decode("utf-8", "replace")
            return {k: v[-1] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}

        def _html(self, code, body):
            self._send(code, body.encode(), "text/html; charset=utf-8")

        def do_POST(self):
            if control and self.path in ("/settings", "/update", "/update/reset"):
                return self.web_post()
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

        def web_post(self):
            if not self._same_origin():
                return self._send(403, b"cross-site request refused", "text/plain")
            if self.path.startswith("/update") and not control.on_device:
                return self._send(400, b"App updates only work on the device, not in the simulator.",
                                  "text/plain")
            if self.path == "/update":
                if token and self.headers.get("X-Claudegotchi-Token") != token:
                    return self._send(401, b"Wrong token.", "text/plain")
                length = int(self.headers.get("Content-Length") or 0)
                if length > update.MAX_BUNDLE:
                    return self._send(413, b"Bundle too large.", "text/plain")
                try:
                    version = update.install(self.rfile.read(length))
                except (update.UpdateError, OSError) as e:
                    return self._send(400, f"Update failed: {e}".encode(), "text/plain")
                log.info("App update %s installed, restarting", version)
                self._send(200, f"Version {version} installed. Restarting …".encode(), "text/plain")
                return control.restart()

            form = self._form()
            if form is None:
                return self._send(413)
            if token and form.get("_token") != token:
                return self._html(401, settings.page(control.cfg, True, "Wrong token.",
                                                     update.running_from(), error=True))
            if self.path == "/update/reset":
                update.reset()
                self._html(200, settings.page(control.cfg, bool(token),
                                              "Back to the built-in version. Restarting …"))
                return control.restart()
            changes = settings.changes_from_form(form, control.cfg)
            if not changes:
                return self._html(200, settings.page(control.cfg, bool(token), "Nothing changed.",
                                                     update.running_from()))
            try:
                settings.write_config(control.cfg_path, changes)
            except Exception as e:
                log.exception("Saving settings failed")
                return self._html(500, settings.page(control.cfg, bool(token), f"Saving failed: {e}",
                                                     update.running_from(), error=True))
            for (sec, key), value in changes.items():
                control.cfg.setdefault(sec, {})[key] = value
            log.info("Settings changed: %s", ", ".join(f"{s}.{k}" for s, k in changes))
            note = ("Saved. Restarting the gotchi …" if control.on_device
                    else "Saved. Restart the simulator to apply.")
            self._html(200, settings.page(control.cfg, bool(control.cfg["server"]["token"]), note,
                                          update.running_from()))
            if control.on_device:
                control.restart(reboot=True)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/settings" and control:
                self._html(200, settings.page(control.cfg, bool(token), "", update.running_from()))
            elif path == "/":
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


def power_off(renderer, on_device):
    """The battery is about to run out: say good night and shut down cleanly,
    so the SD card is not cut off mid-write."""
    if not on_device:
        log.warning("Battery empty: on the device the gotchi would power off now")
        return
    renderer.farewell = "battery_off"
    renderer.goodbye()
    os.system("poweroff")


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
    ap.add_argument("--battery", default=None,
                    help='battery model, overrides [battery] model (e.g. "sim" or "sim:20" for a fake one)')
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
    cfg_path = args.config or os.environ.get("CLAUDEGOTCHI_CONFIG", config.DEFAULT_PATH)
    on_device = not args.sim and cfg_path.startswith("/boot/")
    bat_cfg = dict(cfg["battery"])
    if args.battery is not None:
        bat_cfg["model"] = args.battery
    elif args.sim and bat_cfg["model"] == "auto":
        bat_cfg["model"] = "none"          # no I2C in the simulator unless asked for
    bat_dev = battery_mod.detect(bat_cfg)
    monitor = battery_mod.BatteryMonitor(bat_dev, bat_cfg["shutdown_at"]) if bat_dev else None
    brain = Brain(Life(path), battery=monitor)
    renderer = Renderer(brain, display)
    if monitor:
        monitor.on_empty = lambda: power_off(renderer, on_device)
        monitor.check()                     # so the first frame already knows the charge
        monitor.start()
    renderer.start()
    dispatch = make_dispatch(brain, set_clock=not args.sim)
    control = Control(cfg_path, cfg, on_device)
    handler = make_handler(brain, renderer, srv["token"], dispatch, control)
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

    control.stop = shutdown

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    relay = cfg["relay"]
    if relay["url"]:
        Relay(relay["url"], srv["token"], dispatch, relay["auth"]).start()
    log.info("Claudegotchi listening on http://%s:%d", srv["host"], port)
    server.serve_forever()
    if control.exit_code == RESTART:
        renderer.stop_evt.set()
        brain.life.maybe_save(force=True)
        return RESTART
    renderer.goodbye()
    return 0
