"""Zeichen-Schleife: holt die Ansicht vom Gehirn und schickt sie ans Display."""
import json
import logging
import threading
import time
from datetime import datetime

from .mood import ANIM_PERIOD, FACES, MESSAGES
from .painter import Painter

log = logging.getLogger("claudegotchi")


class Renderer(threading.Thread):
    MIN_INTERVAL = 2.0          # e-Ink nicht öfter als alle 2 s anfassen
    FULL_EVERY = 40             # nach so vielen Teil-Updates einmal voll (gegen Geisterbilder)
    FULL_SECONDS = 30 * 60

    def __init__(self, brain, display):
        super().__init__(daemon=True)
        self.brain, self.display, self.painter = brain, display, Painter()
        self.last_key, self.last_draw, self.last_full, self.partials = None, 0.0, 0.0, 0
        self.frame = None
        self.stop_evt = threading.Event()
        self.draw_lock = threading.Lock()

    def face_for(self, mood, now):
        frames = FACES[mood]
        period = ANIM_PERIOD.get(mood)
        return frames[int(now // period) % len(frames)] if period else frames[0]

    def run(self):
        while not self.stop_evt.is_set():
            try:
                with self.draw_lock:
                    if not self.stop_evt.is_set():
                        self.tick()
            except Exception:
                log.exception("Zeichnen fehlgeschlagen")
            self.stop_evt.wait(1.0)

    def tick(self):
        now = time.time()
        view = self.brain.view()
        face = self.face_for(view["mood"], now)
        key = (face, view["message"], view["project"], json.dumps(view["counts"], sort_keys=True),
               json.dumps({k: int(v["pct"]) for k, v in view["limits"].items()}, sort_keys=True),
               datetime.now().strftime("%H:%M"), view["sessions"])
        if key == self.last_key or now - self.last_draw < self.MIN_INTERVAL:
            return
        img = self.painter.render(view, face)
        full = (self.last_draw == 0 or self.partials >= self.FULL_EVERY
                or now - self.last_full > self.FULL_SECONDS)
        self.display.show(img, full)
        self.frame = img
        self.last_key, self.last_draw = key, now
        if full:
            self.partials, self.last_full = 0, now
        else:
            self.partials += 1
        log.info("Anzeige: %s – %s%s", view["mood"], view["message"], " (voll)" if full else "")

    def goodbye(self):
        self.stop_evt.set()
        view = {"state": "offline", "mood": "offline", "message": MESSAGES["offline"][0],
                "project": "", "counts": {}, "sessions": 0, "limits": {}, "tools_today": 0}
        try:
            with self.draw_lock:
                img = self.painter.render(view, FACES["offline"][0])
                self.display.show(img, True)
                self.frame = img
                self.display.close()
        except Exception:
            log.exception("Abschiedsbild fehlgeschlagen")

