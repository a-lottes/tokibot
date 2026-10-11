"""Draw loop: takes the view from the brain and sends it to the display."""
import json
import logging
import threading
import time
from datetime import datetime

from . import critter
from .mood import ANIM_PERIOD, MESSAGES
from .painter import Painter

log = logging.getLogger("tokibot")


class Renderer(threading.Thread):
    MIN_INTERVAL = 2.0          # touch the e-paper at most every 2 s
    FULL_EVERY = 40             # full refresh after this many partial updates (against ghosting)
    FULL_SECONDS = 30 * 60

    def __init__(self, brain, display):
        super().__init__(daemon=True)
        self.brain, self.display, self.painter = brain, display, Painter()
        # Panels without partial refresh redraw fully every time, so less often.
        self.partial = getattr(display, "PARTIAL", True)
        self.interval = max(self.MIN_INTERVAL, getattr(display, "MIN_INTERVAL", 0.0))
        self.last_key, self.last_draw, self.last_full, self.partials = None, 0.0, 0.0, 0
        self.frame = None
        self.farewell = "offline"     # which goodbye to show (MESSAGES key)
        self.said_goodbye = False
        self.stop_evt = threading.Event()
        self.draw_lock = threading.Lock()

    def frame_for(self, mood, now):
        period = ANIM_PERIOD.get(mood)
        return int(now // period) % critter.frames(mood) if period else 0

    def run(self):
        while not self.stop_evt.is_set():
            try:
                with self.draw_lock:
                    if not self.stop_evt.is_set():
                        self.tick()
            except Exception:
                log.exception("Drawing failed")
            self.brain.life.maybe_save()
            self.stop_evt.wait(1.0)

    def tick(self):
        now = time.time()
        view = self.brain.view()
        # A full refresh flashes the panel, so slow panels show no animation.
        frame = self.frame_for(view["mood"], now) if self.partial else 0
        key = (view["mood"], frame, view["message"], view["project"], json.dumps(view["counts"], sort_keys=True),
               json.dumps({k: int(v["pct"]) for k, v in view["limits"].items()}, sort_keys=True),
               datetime.now().strftime("%H:%M"), view["sessions"], view.get("level"), view.get("streak"),
               view.get("nearby"), view.get("friends_nearby"), view.get("accessory"),
               json.dumps(view.get("battery") and {k: view["battery"][k] for k in ("pct", "plugged")}),
               tuple(view.get("props") or ()), view.get("harness"),
               int((view.get("food") or {}).get("fullness", 0) * 20))
        if key == self.last_key or now - self.last_draw < self.interval:
            return
        img = self.painter.render(view, frame)
        full = (not self.partial or self.last_draw == 0 or self.partials >= self.FULL_EVERY
                or now - self.last_full > self.FULL_SECONDS)
        self.display.show(img, full)
        self.frame = img
        self.last_key, self.last_draw = key, now
        if full:
            self.partials, self.last_full = 0, now
        else:
            self.partials += 1
        log.info("Display: %s: %s%s", view["mood"], view["message"], " (full)" if full else "")

    def goodbye(self):
        self.stop_evt.set()
        self.brain.life.maybe_save(force=True)
        last = self.brain.view()
        view = {"state": "offline", "mood": "offline", "message": MESSAGES[self.farewell][0],
                "project": "", "counts": {}, "sessions": 0, "limits": {}, "tools_today": 0,
                "name": last.get("name"), "level": last.get("level"), "streak": 0, "battery": last.get("battery")}
        try:
            with self.draw_lock:
                if self.said_goodbye:
                    return
                self.said_goodbye = True
                img = self.painter.render(view)
                self.display.show(img, True)
                self.frame = img
                self.display.close()
        except Exception:
            log.exception("Goodbye frame failed")

