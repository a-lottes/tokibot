"""The Claudegotchi critter: a chunky pixel creature that shows its mood.

The body is drawn on a coarse grid (4 px cells) so it reads as pixel art on the
e-paper. Eyes, mouth and props use a finer grid (2 px cells) for expression.
Every pattern is plain ASCII: "#" is black, anything else is left untouched.
"""

BODY_CELL = 4
FACE_CELL = 2
WIDTH, HEIGHT = 20 * BODY_CELL, 14 * BODY_CELL     # 80 × 56 px

# Body with its outline; "." is the white inside. Offset (col 2, row 0) in body cells.
BODY = [
    "    ########    ",
    "  ##........##  ",
    " #............# ",
    "#..............#",
    "#..............#",
    "#..............#",
    "#..............#",
    "#..............#",
    "#..............#",
    " #............# ",
    "  ############  ",
]
LEGS = {
    "stand": [" ##  ##  ##  ## ", " ##  ##  ##  ## "],
    "step_a": [" ##  ##  ##  ## ", " ##      ##     "],
    "step_b": [" ##  ##  ##  ## ", "     ##      ## "],
}
# Arms: (pattern, top row) in body cells, left side; the right arm is mirrored.
ARMS = {
    "down": (["##", "##", " #"], 6),
    "up": (["# ", "# ", "##", " #"], 1),
    "out": (["##", "##"], 5),
}

# Eyes: 4 × 6 face cells. Left eye at face col 10, right eye at face col 26, row 8.
EYES = {
    "open":    [" ## ", "####", "####", "####", "####", " ## "],
    "left":    ["##  ", "### ", "### ", "### ", "### ", "##  "],
    "right":   ["  ##", " ###", " ###", " ###", " ###", "  ##"],
    "focused": ["    ", "####", "    ", "####", "####", " ## "],
    "wide":    ["####", "#  #", "# ##", "# ##", "#  #", "####"],
    "happy":   ["    ", " ## ", "#  #", "#  #", "    ", "    "],
    "closed":  ["    ", "    ", "    ", "#  #", " ## ", "    "],
    "tired":   ["    ", "    ", "####", "####", " ## ", "    "],
    "x":       ["    ", "#  #", " ## ", " ## ", "#  #", "    "],
    "flat":    ["    ", "    ", "    ", "####", "    ", "    "],
}
# Mouths: 8 × 4 face cells at face col 16, row 16.
MOUTHS = {
    "smile":  ["        ", "#      #", " #    # ", "  ####  "],
    "grin":   ["########", "#      #", " #    # ", "  ####  "],
    "small":  ["        ", "  #  #  ", "   ##   ", "        "],
    "o":      ["   ##   ", "  #  #  ", "  #  #  ", "   ##   "],
    "flat":   ["        ", "  ####  ", "        ", "        "],
    "frown":  ["        ", "  ####  ", " #    # ", "        "],
    "wavy":   ["        ", " ##  ## ", "#  ##  #", "        "],
    "dot":    ["        ", "   ##   ", "        ", "        "],
}
# Props: face cells, drawn around the head.
PROPS = {
    "bang":     ["##", "##", "##", "##", "  ", "##"],
    "question": [" ### ", "#   #", "   # ", "  #  ", "     ", "  #  "],
    "z_small":  ["###", "  #", " # ", "###"],
    "z_big":    ["####", "   #", "  # ", " #  ", "####"],
    "sparkle":  ["  #  ", "  #  ", "## ##", "  #  ", "  #  "],
    "drop":     [" # ", "###", "###", " # "],
    "bolt":     ["  ##", " ## ", "####", " ## ", "##  "],
    "battery":  ["####### ", "#     ##", "#     ##", "####### "],
    "dot":      ["##", "##"],
    "arrow":    ["  #  ", " ### ", "#####", "  #  ", "  #  "],
    "heart":    [" # # ", "#####", "#####", " ### ", "  #  "],
    "crumb":    ["# ", " #"],
    "check":    ["     #", "    ##", "#  ## ", "####  ", " ##   "],
    "wrench":   [" #  #", " #  #", " ####", "  ## ", "  ## ", "  ## ", "  ## "],
}

# What each mood looks like: eyes per animation frame, mouth, arms, legs, props.
# Props are (name, x, y) in px relative to the sprite's top-left corner.
LOOKS = {
    "ready":      {"eyes": ["open", "open", "closed"], "mouth": "small", "arms": ("down", "up"),
                   "props": [[], [], []]},
    "working":    {"eyes": ["focused"], "mouth": "dot", "arms": ("out", "out"),
                   "legs": ["step_a", "step_b"],
                   "props": [[("dot", 30, -8)], [("dot", 30, -8), ("dot", 38, -8)],
                             [("dot", 30, -8), ("dot", 38, -8), ("dot", 46, -8)]]},
    "tired":      {"eyes": ["tired"], "mouth": "wavy", "arms": ("down", "down"),
                   "legs": ["step_a", "step_b"], "props": [[("drop", 70, 4)], [("drop", 70, 8)]]},
    "permission": {"eyes": ["wide"], "mouth": "o", "arms": ("up", "up"),
                   "props": [[("bang", 74, -14)], [("bang", 74, -18)]]},
    "waiting":    {"eyes": ["left", "right"], "mouth": "flat", "arms": ("down", "down"),
                   "props": [[("question", 70, -16)], [("question", 72, -18)]]},
    "done":       {"eyes": ["happy"], "mouth": "grin", "arms": ("up", "up"),
                   "props": [[("sparkle", -2, -6), ("sparkle", 74, -10)],
                             [("sparkle", 2, -12), ("sparkle", 70, -4)]]},
    "error":      {"eyes": ["x"], "mouth": "wavy", "arms": ("down", "down"),
                   "props": [[("bolt", 70, -10)], [("bolt", 72, -14)]]},
    "limit":      {"eyes": ["flat"], "mouth": "flat", "arms": ("down", "down"),
                   "props": [[("battery", 62, -12)]]},
    "idle":       {"eyes": ["closed"], "mouth": "dot", "arms": ("down", "down"),
                   "props": [[("z_small", 66, -6)], [("z_small", 66, -6), ("z_big", 74, -18)]]},
    "levelup":    {"eyes": ["happy"], "mouth": "grin", "arms": ("up", "up"),
                   "props": [[("arrow", 72, -16), ("sparkle", -2, -6)],
                             [("arrow", 72, -22), ("sparkle", 2, -12), ("sparkle", 62, -4)]]},
    "summary":    {"eyes": ["happy", "happy", "closed"], "mouth": "smile", "arms": ("down", "down"),
                   "props": [[("heart", 70, -12)], [("heart", 70, -14)], [("heart", 70, -12)]]},
    "hungry":     {"eyes": ["tired", "left"], "mouth": "o", "arms": ("out", "down"),
                   "props": [[("crumb", 70, 0)], [("crumb", 72, 4)]]},
    "lowbattery": {"eyes": ["tired", "closed"], "mouth": "o", "arms": ("down", "down"),
                   "props": [[("battery", 62, -12)], []]},
    "flow":       {"eyes": ["focused", "happy"], "mouth": "smile", "arms": ("out", "out"),
                   "legs": ["step_a", "step_b"],
                   "props": [[("sparkle", 72, -10)], [("sparkle", 70, -4)]]},
    "struggling": {"eyes": ["tired"], "mouth": "frown", "arms": ("out", "out"),
                   "legs": ["step_a", "step_b"], "props": [[("drop", 74, -6)], [("drop", 74, 0)]]},
    "stuck":      {"eyes": ["x", "left"], "mouth": "wavy", "arms": ("up", "up"),
                   "props": [[("question", 70, -16), ("bolt", -4, -10)],
                             [("question", 72, -18), ("bolt", -2, -14)]]},
    "oops":       {"eyes": ["wide"], "mouth": "o", "arms": ("down", "down"),
                   "props": [[("bang", 74, -14)], [("bang", 74, -18)]]},
    "juggling":   {"eyes": ["left", "right"], "mouth": "o", "arms": ("up", "up"),
                   "props": [[("dot", 2, -14), ("dot", 38, -22), ("dot", 72, -14)],
                             [("dot", 20, -20), ("dot", 56, -20), ("dot", 72, -6)]]},
    "proud":      {"eyes": ["happy"], "mouth": "grin", "arms": ("up", "up"),
                   "props": [[("check", 70, -14)], [("check", 70, -20), ("sparkle", -2, -6)]]},
    "relieved":   {"eyes": ["happy", "closed"], "mouth": "smile", "arms": ("down", "down"),
                   "props": [[("sparkle", 72, -10)], [("sparkle", 68, -4)]]},
    "offline":    {"eyes": ["closed"], "mouth": "dot", "arms": ("down", "down"),
                   "props": [[("z_small", 66, -6), ("z_big", 74, -18)]]},
}


def frames(mood):
    look = LOOKS.get(mood, LOOKS["idle"])
    return max(len(look["eyes"]), len(look["props"]), len(look.get("legs", ["stand"])))


def _blit(draw, pattern, x, y, cell, mirror=False):
    for r, row in enumerate(pattern):
        if mirror:
            row = row[::-1]
        for c, ch in enumerate(row):
            if ch == "#":
                draw.rectangle((x + c * cell, y + r * cell,
                                x + (c + 1) * cell - 1, y + (r + 1) * cell - 1), fill=0)
            elif ch == ".":
                draw.rectangle((x + c * cell, y + r * cell,
                                x + (c + 1) * cell - 1, y + (r + 1) * cell - 1), fill=255)


def draw(draw, x, y, mood, frame=0, extras=()):
    """Draw the critter with its top-left corner at (x, y). `extras`: props it holds,
    e.g. ["wrench"] when the context window is nearly full."""
    look = LOOKS.get(mood, LOOKS["idle"])
    pick = lambda seq: seq[frame % len(seq)]
    b, f = BODY_CELL, FACE_CELL
    bounce = -b if mood in ("done", "permission", "levelup", "proud") and frame % 2 else 0
    y0 = y + bounce

    _blit(draw, BODY, x + 2 * b, y0, b)
    _blit(draw, LEGS[pick(look.get("legs", ["stand"]))], x + 2 * b, y0 + 11 * b, b)
    left, right = look["arms"]
    for side, name in (("left", left), ("right", right)):
        pattern, row = ARMS[name]
        if side == "left":
            _blit(draw, pattern, x, y0 + row * b, b)
        else:
            _blit(draw, pattern, x + 18 * b, y0 + row * b, b, mirror=True)

    eyes = EYES[pick(look["eyes"])]
    _blit(draw, eyes, x + 10 * f, y0 + 8 * f, f)
    _blit(draw, eyes, x + 26 * f, y0 + 8 * f, f)
    _blit(draw, MOUTHS[look["mouth"]], x + 16 * f, y0 + 16 * f, f)

    for name, px, py in pick(look["props"]) if look["props"] else []:
        _blit(draw, PROPS[name], x + px, y + py, f)
    for name in extras:
        if name in PROPS:
            _blit(draw, PROPS[name], x - 6, y0 + 10 * b, f)
