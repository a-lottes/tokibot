"""Render the pictures for the website's Friends page into docs/img/social/.

  python3 tools/site_social.py ../docs

* acc-<name>.png: the critter wearing each accessory
* <gotchi>-<step>.png: the two displays of the demo, step by step

The pictures come from the real Painter, so they look exactly like the display.
The clock is fixed, so running this twice gives the same files.
"""
import datetime as _dt
import os
import sys
from unittest import mock

from PIL import Image, ImageDraw

from tokibot import critter, painter
from tokibot.mood import ACCESSORIES
from tokibot.painter import Painter

SCALE = 2
LIMITS = {"five_hour": {"pct": 38.0, "reset": 0}, "seven_day": {"pct": 21.0, "reset": 0}}

# The demo: you (Pixel) meet Mochi. Each step is one screen per gotchi:
# (mood, message, accessory, level, nearby, friends nearby, sessions working)
STORY = {
    "start": {
        "pixel": ("working", "Busy with Edit", "none", 3, 0, 0, 1),
        "mochi": ("idle", "Dreaming of tokens …", "cap", 4, 0, 0, 0),
    },
    "meet": {
        "pixel": ("encounter", "Hello Mochi! (Lv4)", "none", 3, 1, 0, 1),
        "mochi": ("encounter", "Ooh, a gotchi! Hi Pixel!", "cap", 4, 1, 0, 0),
    },
    "ask": {
        "pixel": ("encounter", "Hello Mochi! (Lv4)", "none", 3, 1, 0, 1),
        "mochi": ("invite", "Pixel wants to be friends! Say yes on the social page.", "cap", 4, 1, 0, 0),
    },
    "friends": {
        "pixel": ("newfriend", "Mochi and I are friends now!", "none", 4, 1, 1, 1),
        "mochi": ("newfriend", "New friend: Pixel! ♥", "cap", 4, 1, 1, 0),
    },
    "badge": {
        "pixel": ("badge", "New badge: First friend!", "bow", 4, 1, 1, 1),
        "mochi": ("badge", "New badge: First friend!", "bow", 4, 1, 1, 0),
    },
    "cowork": {
        "pixel": ("friend", "Mochi is here! Hi friend!", "bow", 4, 1, 1, 1),
        "mochi": ("working", "Busy with Bash", "bow", 4, 1, 1, 1),
    },
    "glasses": {
        "pixel": ("badge", "New badge: Co-working!", "glasses", 4, 1, 1, 1),
        "mochi": ("badge", "I earned a badge: Co-working!", "glasses", 5, 1, 1, 1),
    },
}


class FixedClock(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 5, 14, 32)


def screen(p, mood, message, accessory, level, nearby, friends, working):
    view = {"mood": mood, "message": message, "project": "my-app" if working else "",
            "counts": {"working": working} if working else {}, "sessions": working,
            "tools_today": 12, "level": level, "streak": 3, "limits": LIMITS,
            "accessory": accessory, "nearby": nearby, "friends_nearby": friends,
            "battery": None, "props": []}
    img = p.render(view, 0).convert("L")
    return img.resize((img.width * SCALE, img.height * SCALE), Image.NEAREST)


def accessory_tiles():
    """The critter with each accessory, all cut to the same box so they line up."""
    tiles = {}
    for name in ACCESSORIES:
        if name != "none":
            img = Image.new("L", (120, 110), 255)
            critter.draw(ImageDraw.Draw(img), 20, 34, "ready", 0, name)
            tiles[name] = img
    boxes = [Image.eval(t, lambda v: 255 - v).getbbox() for t in tiles.values()]
    pad = 6
    box = (min(b[0] for b in boxes) - pad, min(b[1] for b in boxes) - pad,
           max(b[2] for b in boxes) + pad, max(b[3] for b in boxes) + pad)
    return {n: t.crop(box).resize(((box[2] - box[0]) * 4, (box[3] - box[1]) * 4), Image.NEAREST)
            for n, t in tiles.items()}


def main(docs):
    out = os.path.join(docs, "img", "social")
    os.makedirs(out, exist_ok=True)
    with mock.patch.object(painter, "datetime", FixedClock):
        p = Painter()
        for step, gotchis in STORY.items():
            for name, args in gotchis.items():
                screen(p, *args).save(os.path.join(out, f"{name}-{step}.png"), optimize=True)
    for name, tile in accessory_tiles().items():
        tile.save(os.path.join(out, f"acc-{name}.png"), optimize=True)
    print(f"wrote {len(os.listdir(out))} pictures to {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../docs")
