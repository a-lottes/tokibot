"""Render every mood (and its animation frames) into one contact sheet.

  python3 tools/mockups.py [out.png]
"""
import sys

from PIL import Image, ImageDraw

from claudegotchi import critter
from claudegotchi.painter import H, W, Painter

LIMITS = {"five_hour": {"pct": 42.0, "reset": 0}, "seven_day": {"pct": 17.0, "reset": 0}}
CASES = [
    ("ready", "Hi! What are we building?", "claudegotchi", {"ready": 1}),
    ("working", "Busy with Bash", "claudegotchi", {"working": 2, "done": 1}),
    ("tired", "Phew, 86% of my 5h budget used …", "claudegotchi", {"working": 1}),
    ("permission", "May I use Bash? Please!", "my-app", {"permission": 1, "working": 1}),
    ("waiting", "Hello? Your turn!", "claudegotchi", {"waiting": 1}),
    ("done", "Ta-da! Finished.", "claudegotchi", {"done": 1}),
    ("error", "Oh no … overloaded", "claudegotchi", {}),
    ("limit", "Limit reached. zZz until 18:40", "", {}),
    ("idle", "Dreaming of tokens …", "", {}),
    ("levelup", "Level up! I'm level 4 now!", "claudegotchi", {"done": 1}),
    ("summary", "Today: 23 tasks, 412 tools, 2 errors. Streak: 5 days.", "", {}),
    ("hungry", "3 days without code. *stomach growls*", "", {}),
    ("encounter", "Hello Tofu42! (Lv6)", "", {}, "cap", 1, 0),
    ("friend", "Mochi07 is here! Hi friend!", "claudegotchi", {"working": 1}, "bow", 2, 1),
    ("newfriend", "Mochi07 and I are friends now!", "", {}, "bow", 1, 1),
    ("invite", "Tofu42 wants to be friends! Say yes on the social page.", "", {}, "none", 1, 0),
    ("badge", "New badge: Co-working!", "", {}, "glasses", 1, 1),
    ("lowbattery", "Battery at 12% … plug me in?", "", {}, "none", 0, 0),
]
ACCESSORY_CASES = ["cap", "bow", "glasses", "headphones", "nightcap", "party", "crown"]
# With a PiSugar battery: the header shows the charge (lightning bolt = on power)
BATTERY = {"lowbattery": {"pct": 12, "plugged": False}, "done": {"pct": 64, "plugged": True},
           "idle": {"pct": 87, "plugged": False}}
SCALE, PAD, COLS = 2, 16, 3


def main(out):
    painter = Painter()
    tiles = []
    for mood, msg, project, counts, *social in CASES:
        accessory, nearby, friends = social or ("none", 0, 0)
        for frame in range(critter.frames(mood)):
            view = {"mood": mood, "message": msg, "project": project, "counts": counts,
                    "sessions": sum(counts.values()), "tools_today": 12, "level": 4, "streak": 5,
                    "limits": {} if mood == "idle" else LIMITS, "accessory": accessory,
                    "nearby": nearby, "friends_nearby": friends, "battery": BATTERY.get(mood)}
            tiles.append((f"{mood} {frame + 1}/{critter.frames(mood)}", painter.render(view, frame)))
    for accessory in ACCESSORY_CASES:
        view = {"mood": "ready", "message": f"Look, my {accessory}!", "project": "", "counts": {},
                "sessions": 0, "tools_today": 12, "level": 4, "streak": 5, "limits": LIMITS,
                "accessory": accessory}
        tiles.append((f"accessory: {accessory}", painter.render(view, 0)))
    rows = (len(tiles) + COLS - 1) // COLS
    tw, th = W * SCALE, H * SCALE + 18
    sheet = Image.new("L", (COLS * (tw + PAD) + PAD, rows * (th + PAD) + PAD), 225)
    d = ImageDraw.Draw(sheet)
    label_font = painter.f_proj.font_variant(size=13)
    for i, (label, img) in enumerate(tiles):
        x = PAD + (i % COLS) * (tw + PAD)
        y = PAD + (i // COLS) * (th + PAD)
        d.text((x, y), label, font=label_font, fill=0)
        sheet.paste(img.convert("L").resize((W * SCALE, H * SCALE), Image.NEAREST), (x, y + 18))
    sheet.save(out)
    print(f"{len(tiles)} frames → {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "mockups.png")
