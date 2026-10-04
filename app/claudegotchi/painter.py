"""Zeichnet eine Ansicht (Gesicht, Sprechtext, Fußzeile) als 1-Bit-Bild."""
import logging
import os
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

W, H = 250, 122
log = logging.getLogger("claudegotchi")

# Die benötigten DejaVu-Schriften liegen dem Paket bei (fonts/), damit Gesichter wie
# (◕‿‿◕) auf dem Gerät und am Mac gleich aussehen.
FONT_DIRS = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"),
             "/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/dejavu/"]


def load_font(name, size):
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    log.warning("Schrift %s nicht gefunden – nutze Standardschrift", name)
    return ImageFont.load_default()


class Painter:
    def __init__(self):
        self.f_face = load_font("DejaVuSansMono-Bold.ttf", 30)
        self.f_title = load_font("DejaVuSansMono-Bold.ttf", 11)
        self.f_text = load_font("DejaVuSans.ttf", 11)
        self.f_proj = load_font("DejaVuSans-Bold.ttf", 11)
        self.f_small = load_font("DejaVuSans.ttf", 10)

    def wrap(self, text, font, width):
        lines, line = [], ""
        for word in text.split():
            cand = f"{line} {word}".strip()
            if font.getlength(cand) <= width:
                line = cand
            else:
                if line:
                    lines.append(line)
                while font.getlength(word) > width:   # überlange Wörter hart umbrechen
                    cut = len(word)
                    while cut > 1 and font.getlength(word[:cut]) > width:
                        cut -= 1
                    lines.append(word[:cut])
                    word = word[cut:]
                line = word
        if line:
            lines.append(line)
        return lines

    @staticmethod
    def ellipsize(text, font, width):
        if font.getlength(text) <= width:
            return text
        while text and font.getlength(text + "…") > width:
            text = text[:-1]
        return text + "…"

    def render(self, view, face):
        img = Image.new("1", (W, H), 255)
        d = ImageDraw.Draw(img)

        # Kopfzeile
        d.text((3, 1), "Claudegotchi", font=self.f_title, fill=0)
        clock = datetime.now().strftime("%H:%M")
        d.text((W - 3 - self.f_title.getlength(clock), 1), clock, font=self.f_title, fill=0)
        if view["sessions"]:
            sess = f"{view['sessions']} Session" + ("s" if view["sessions"] != 1 else "")
            d.text(((W - self.f_small.getlength(sess)) / 2, 2), sess, font=self.f_small, fill=0)
        d.line((0, 15, W, 15), fill=0)

        # Gesicht links
        l, t, r, b = d.textbbox((0, 0), "(◕‿‿◕)", font=self.f_face)   # feste Referenz → kein Hüpfen
        fw = self.f_face.getlength(face)
        d.text(((122 - fw) / 2, 16 + (89 - (b - t)) / 2 - t), face, font=self.f_face, fill=0)

        # Sprechtext rechts
        x0, y = 124, 21
        if view["project"]:
            proj = self.ellipsize(view["project"], self.f_proj, W - x0 - 3)
            d.text((x0, y), proj, font=self.f_proj, fill=0)
            y += 15
        for line in self.wrap(view["message"], self.f_text, W - x0 - 3)[:5 if not view["project"] else 4]:
            d.text((x0, y), line, font=self.f_text, fill=0)
            y += 14

        # Fußzeile: Session-Zähler links, Limits rechts
        d.line((0, 105, W, 105), fill=0)
        c = view["counts"]
        parts = []
        if c.get("working"):
            parts.append(f"⚙{c['working']}")
        waiting = c.get("waiting", 0) + c.get("permission", 0)
        if waiting:
            parts.append(f"?{waiting}")
        if c.get("done"):
            parts.append(f"✓{c['done']}")
        n = view["tools_today"]
        left = " ".join(parts) or f"{n} Tool{'' if n == 1 else 's'} heute"
        d.text((3, 108), left, font=self.f_small, fill=0)

        x = W - 3
        for key, label in (("seven_day", "7d"), ("five_hour", "5h")):
            w = view["limits"].get(key)
            if not w:
                continue
            pct = max(0, min(100, w["pct"]))
            txt = f"{int(round(pct))}%"
            x -= self.f_small.getlength(txt)
            d.text((x, 108), txt, font=self.f_small, fill=0)
            x -= 30
            d.rectangle((x, 110, x + 26, 117), outline=0)
            d.rectangle((x + 1, 111, x + 1 + int(24 * pct / 100), 116), fill=0)
            x -= self.f_small.getlength(label) + 2
            d.text((x, 108), label, font=self.f_small, fill=0)
            x -= 8
        return img

