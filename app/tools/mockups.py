"""Render every mood (and its animation frames) into one contact sheet, and the
single mood screens the website shows (docs/img/moods/, also in the blueprints).

  python3 tools/mockups.py [out.png] [moods dir]
"""
import os
import sys

from PIL import Image, ImageDraw

from tokibot import critter
from tokibot.painter import H, W, Painter

LIMITS = {"five_hour": {"pct": 42.0, "reset": 0}, "seven_day": {"pct": 17.0, "reset": 0}}
CASES = [
    ("ready", "Hi! What are we building?", "tokibot", {"ready": 1}),
    ("working", "Busy with Bash", "tokibot", {"working": 2, "done": 1}),
    ("tired", "Phew, 86% of my 5h budget used …", "tokibot", {"working": 1}),
    ("permission", "May I use Bash? Please!", "my-app", {"permission": 1, "working": 1}),
    ("waiting", "Hello? Your turn!", "tokibot", {"waiting": 1}),
    ("done", "Ta-da! Finished.", "tokibot", {"done": 1}),
    ("error", "Oh no … overloaded", "tokibot", {}),
    ("limit", "Limit reached. zZz until 18:40", "", {}),
    ("idle", "Dreaming of tokens …", "", {}),
    ("levelup", "Level up! I'm level 4 now!", "tokibot", {"done": 1}),
    ("summary", "Today: 23 tasks, 412 tools, 2 errors. Streak: 5 days.", "", {}),
    ("hungry", "3 days without code. *stomach growls*", "", {}),
    ("encounter", "Hello Tofu42! (Lv6)", "", {}, "cap", 1, 0),
    ("friend", "Mochi07 is here! Hi friend!", "tokibot", {"working": 1}, "bow", 2, 1),
    ("newfriend", "Mochi07 and I are friends now!", "", {}, "bow", 1, 1),
    ("invite", "Tofu42 wants to be friends! Say yes on the social page.", "", {}, "none", 1, 0),
    ("badge", "New badge: Co-working!", "", {}, "glasses", 1, 1),
    ("lowbattery", "Battery at 12% … plug me in?", "", {}, "none", 0, 0),
    ("flow", "In the zone.", "tokibot", {"working": 1}),
    ("struggling", "This one is tricky …", "tokibot", {"working": 1}),
    ("stuck", "Bash keeps failing …", "tokibot", {"working": 1}),
    ("oops", "Oops, wrong way? Tell me.", "tokibot", {"working": 1}),
    ("juggling", "Juggling 3 sessions!", "tokibot", {"working": 3}),
    ("proud", "Committed! 4 today.", "tokibot", {"working": 1}),
    ("relieved", "Green again. Phew!", "tokibot", {"working": 1}),
    ("stuffed", "I'm stuffed! 2.4M tokens today.", "tokibot", {"working": 1}),
    ("peckish", "My tummy is empty … feed me tokens?", "", {}),
]
# How full the critter is (tokens are its food); FOOD_OF wins for single moods
FOOD = {"fullness": 0.8, "total": 1}
FOOD_OF = {"stuffed": {"fullness": 2.1, "total": 1}, "peckish": {"fullness": 0.05, "total": 1}}
# Sessions from another harness show its name next to the project
HARNESS = {"juggling": "codex", "permission": "copilot"}
ACCESSORY_CASES = ["cap", "bow", "glasses", "headphones", "nightcap", "party", "crown"]
# A nearly full context window: the critter carries a wrench
PROPS = {"struggling": ["wrench"]}
# With a PiSugar battery: the header shows the charge (lightning bolt = on power)
BATTERY = {"lowbattery": {"pct": 12, "plugged": False}, "done": {"pct": 64, "plugged": True},
           "idle": {"pct": 87, "plugged": False}}
SCALE, PAD, COLS = 2, 16, 3
# The moods the website shows one by one, first frame, without battery or harness
SITE_MOODS = ["ready", "working", "tired", "permission", "waiting", "done", "error", "limit",
              "idle", "levelup", "summary", "hungry"]


def view_for(mood, msg, project, counts, social, site=False):
    accessory, nearby, friends = social or ("none", 0, 0)
    return {"mood": mood, "message": msg, "project": project, "counts": counts,
            "sessions": sum(counts.values()), "tools_today": 12, "level": 4, "streak": 5,
            "limits": {} if mood == "idle" else LIMITS, "accessory": accessory,
            "nearby": nearby, "friends_nearby": friends,
            "battery": None if site else BATTERY.get(mood),
            "props": PROPS.get(mood, []), "food": FOOD_OF.get(mood, FOOD),
            "harness": "claude" if site else HARNESS.get(mood, "claude")}


def site_moods(painter, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for mood, msg, project, counts, *social in CASES:
        if mood in SITE_MOODS:
            img = painter.render(view_for(mood, msg, project, counts, social, site=True), 0)
            img.convert("L").resize((W * SCALE, H * SCALE), Image.NEAREST).save(
                os.path.join(out_dir, f"{mood}.png"), optimize=True)
    print(f"{len(SITE_MOODS)} mood screens → {out_dir}")


def main(out, moods_dir=None):
    painter = Painter()
    if moods_dir:
        site_moods(painter, moods_dir)
    tiles = []
    for mood, msg, project, counts, *social in CASES:
        for frame in range(critter.frames(mood)):
            view = view_for(mood, msg, project, counts, social)
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
    main(sys.argv[1] if len(sys.argv) > 1 else "mockups.png", sys.argv[2] if len(sys.argv) > 2 else None)
