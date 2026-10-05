"""Draws a view (critter, speech bubble, status bar) as a 1-bit image."""
import logging
import os
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from . import critter
from .mood import LABELS

W, H = 250, 122
log = logging.getLogger("claudegotchi")

# The DejaVu fonts ship with the package (fonts/), so the display looks the same
# on the device and in the simulator on a Mac.
FONT_DIRS = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"),
             "/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/dejavu/"]

HEADER_H = 15
FOOTER_Y = 106
BUBBLE = (110, 20, W - 3, FOOTER_Y - 5)       # speech bubble box
CRITTER_XY = (14, 44)


def load_font(name, size):
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    log.warning("Font %s not found, using the default font", name)
    return ImageFont.load_default()


class Painter:
    def __init__(self):
        self.f_brand = load_font("DejaVuSansMono-Bold.ttf", 11)
        self.f_text = load_font("DejaVuSans.ttf", 11)
        self.f_proj = load_font("DejaVuSans-Bold.ttf", 11)
        self.f_small = load_font("DejaVuSans.ttf", 10)
        self.f_small_bold = load_font("DejaVuSans-Bold.ttf", 10)

    def wrap(self, text, font, width):
        lines, line = [], ""
        for word in text.split():
            cand = f"{line} {word}".strip()
            if font.getlength(cand) <= width:
                line = cand
            else:
                if line:
                    lines.append(line)
                while font.getlength(word) > width:   # hard-break words that are too long
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

    def header(self, d, view):
        d.rectangle((0, 0, W - 1, HEADER_H - 1), fill=0)
        d.text((4, 1), "claudegotchi", font=self.f_brand, fill=255)
        left = 4 + self.f_brand.getlength("claudegotchi")
        if view.get("level"):
            x = left + 4
            lv = LABELS["level"].format(level=view["level"])
            w = self.f_small_bold.getlength(lv) + 6
            d.rounded_rectangle((x, 2, x + w, HEADER_H - 3), radius=3, fill=255)
            d.text((x + 3, 1), lv, font=self.f_small_bold, fill=0)
            left = x + w
        clock = datetime.now().strftime("%H:%M")
        right = W - 4 - self.f_brand.getlength(clock)
        d.text((right, 1), clock, font=self.f_brand, fill=255)
        # battery (PiSugar), then gotchis nearby left of it: ♥ for friends, ● for others
        if view.get("battery"):
            right = self.battery_icon(d, int(right) - 6, view["battery"])
        near, friends = view.get("nearby", 0), view.get("friends_nearby", 0)
        if near:
            label = f"♥{friends}" if friends else f"●{near}"
            right -= 5 + self.f_small_bold.getlength(label)
            d.text((right, 2), label, font=self.f_small_bold, fill=255)
        # Sessions in the space that is left; shortened or dropped when it gets tight
        # (the footer counts them too).
        n = view["sessions"]
        if n:
            room = right - left - 10
            for label in (f"{n} {LABELS['session'] if n == 1 else LABELS['sessions']}", str(n)):
                w = self.f_small.getlength(label)
                if w <= room:
                    x = min(max((W - w) / 2 + 18, left + 5), right - 5 - w)
                    d.text((x, 2), label, font=self.f_small, fill=255)
                    break

    @staticmethod
    def battery_icon(d, right, bat):
        """White battery in the black header, its right edge at x = right. Returns its left x."""
        x1, x0, y0, y1 = right - 2, right - 20, 3, 11
        d.rectangle((x0, y0, x1, y1), outline=255)
        d.rectangle((x1 + 1, y0 + 2, x1 + 2, y1 - 2), fill=255)         # the nub
        fill = round(15 * max(0, min(100, bat["pct"])) / 100)
        if fill:
            d.rectangle((x0 + 2, y0 + 2, x0 + 1 + fill, y1 - 2), fill=255)
        if bat["plugged"]:                                              # lightning bolt
            bolt = [(x0 - 4, y0 - 1), (x0 - 7, y0 + 5), (x0 - 4, y0 + 5), (x0 - 6, y1 + 2),
                    (x0 - 1, y0 + 3), (x0 - 4, y0 + 3), (x0 - 2, y0 - 1)]
            d.polygon(bolt, fill=255)
            return x0 - 8
        return x0

    def bubble(self, d, view):
        x0, y0, x1, y1 = BUBBLE
        d.rounded_rectangle(BUBBLE, radius=7, outline=0, width=2, fill=255)
        # tail pointing at the critter
        ty = 62
        d.polygon([(x0 + 1, ty - 6), (x0 + 1, ty + 4), (x0 - 9, ty + 4)], fill=255)
        d.line([(x0, ty - 6), (x0 - 9, ty + 4), (x0, ty + 4)], fill=0, width=2)
        x, y, width = x0 + 7, y0 + 5, x1 - x0 - 13
        lines_left = 5
        if view["project"]:
            d.text((x, y), self.ellipsize(view["project"], self.f_proj, width),
                   font=self.f_proj, fill=0)
            y += 15
            lines_left = 4
        for line in self.wrap(view["message"], self.f_text, width)[:lines_left]:
            d.text((x, y), line, font=self.f_text, fill=0)
            y += 14

    def footer(self, d, view):
        d.line((0, FOOTER_Y, W, FOOTER_Y), fill=0)
        x = W - 3
        for key, label in (("seven_day", "7d"), ("five_hour", "5h")):
            w = view["limits"].get(key)
            if not w:
                continue
            pct = max(0, min(100, w["pct"]))
            txt = f"{int(round(pct))}%"
            x -= self.f_small.getlength(txt)
            d.text((x, FOOTER_Y + 3), txt, font=self.f_small, fill=0)
            x -= 32
            d.rounded_rectangle((x, FOOTER_Y + 5, x + 28, FOOTER_Y + 12), radius=3, outline=0)
            fill = int(26 * pct / 100)
            if fill >= 2:
                d.rounded_rectangle((x + 1, FOOTER_Y + 6, x + 1 + fill, FOOTER_Y + 11),
                                    radius=2, fill=0)
            x -= self.f_small_bold.getlength(label) + 2
            d.text((x, FOOTER_Y + 3), label, font=self.f_small_bold, fill=0)
            x -= 8
        room = x - 3

        c = view["counts"]
        chips = []
        if c.get("working"):
            chips.append(("▶", c["working"]))
        waiting = c.get("waiting", 0) + c.get("permission", 0)
        if waiting:
            chips.append(("?", waiting))
        if c.get("done"):
            chips.append(("✓", c["done"]))
        x = 3
        if chips:
            for icon, n in chips:
                label = f"{icon}{n}"
                w = self.f_small_bold.getlength(label) + 8
                d.rounded_rectangle((x, FOOTER_Y + 3, x + w, FOOTER_Y + 14), radius=5, fill=0)
                d.text((x + 4, FOOTER_Y + 3), label, font=self.f_small_bold, fill=255)
                x += w + 4
            return
        streak = view.get("streak", 0)
        keys = ["tools_streak", "tools_streak_short", "tools_today"] if streak >= 2 else ["tools_today"]
        for k in keys:
            label = LABELS[k].format(n=view["tools_today"], streak=streak)
            if self.f_small.getlength(label) <= room:
                break
        d.text((x, FOOTER_Y + 3), self.ellipsize(label, self.f_small, room), font=self.f_small, fill=0)

    def render(self, view, frame=0):
        img = Image.new("1", (W, H), 255)
        d = ImageDraw.Draw(img)
        self.header(d, view)
        critter.draw(d, *CRITTER_XY, view["mood"], frame, view.get("accessory", "none"))
        self.bubble(d, view)
        self.footer(d, view)
        return img
