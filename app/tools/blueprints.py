"""Draw the isometric blueprint figures for the website and put them into docs/*.html.

  python3 tools/blueprints.py ../docs

Every figure is plain SVG built from boxes in millimetres, projected isometrically.
The HTML pages carry markers like <!-- fig:hero --> … <!-- /fig:hero -->; this script
replaces what is between them, so the pages stay plain static files. Colours come from
CSS classes (bp-*) in docs/style.css, so the figures follow light and dark mode.
"""
import math
import os
import re
import sys

C30 = math.cos(math.radians(30))


class Fig:
    def __init__(self, scale):
        self.s = scale
        self.items = []         # drawn in order
        self.labels = []        # drawn last, on top
        self.minx = self.miny = 1e9
        self.maxx = self.maxy = -1e9

    # projection --------------------------------------------------------------

    def p(self, x, y, z):
        X = (x - y) * C30 * self.s
        Y = ((x + y) * 0.5 - z) * self.s
        self.minx, self.maxx = min(self.minx, X), max(self.maxx, X)
        self.miny, self.maxy = min(self.miny, Y), max(self.maxy, Y)
        return X, Y

    def pts(self, points):
        return " ".join(f"{X:.1f},{Y:.1f}" for X, Y in (self.p(*q) for q in points))

    # primitives --------------------------------------------------------------

    def poly(self, points, cls):
        self.items.append(f'<polygon class="{cls}" points="{self.pts(points)}"/>')

    def line(self, a, b, cls="bp-line"):
        (x1, y1), (x2, y2) = self.p(*a), self.p(*b)
        self.items.append(f'<line class="{cls}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>')

    def path(self, points, cls="bp-line"):
        d = "M" + " L".join(f"{X:.1f},{Y:.1f}" for X, Y in (self.p(*q) for q in points))
        self.items.append(f'<path class="{cls}" d="{d}"/>')

    def box(self, x, y, z, dx, dy, dz, tone=""):
        """A cuboid. Visible faces: front (+y), right (+x), top."""
        t = f" {tone}" if tone else ""
        X, Y, Z = x + dx, y + dy, z + dz
        self.poly([(x, Y, z), (X, Y, z), (X, Y, Z), (x, Y, Z)], "bp-l" + t)
        self.poly([(X, y, z), (X, Y, z), (X, Y, Z), (X, y, Z)], "bp-r" + t)
        self.poly([(x, y, Z), (X, y, Z), (X, Y, Z), (x, Y, Z)], "bp-t" + t)

    def curve(self, a, b, c, d, cls="bp-cable"):
        """A cubic Bézier through projected control points (for cables)."""
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = (self.p(*q) for q in (a, b, c, d))
        self.items.append(f'<path class="{cls}" d="M{x0:.1f},{y0:.1f} C{x1:.1f},{y1:.1f} '
                          f'{x2:.1f},{y2:.1f} {x3:.1f},{y3:.1f}"/>')

    def ellipse(self, cx, cy, z, r, cls="bp-hole", n=20):
        self.poly([(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n), z)
                   for i in range(n)], cls)

    def flat_text(self, x, y, z, text, size=2.2, cls="bp-silk"):
        """Text printed on a horizontal surface (like silkscreen), in mm."""
        X, Y = self.p(x, y, z)
        a, b, c, d = C30 * self.s, 0.5 * self.s, -C30 * self.s, 0.5 * self.s
        self.items.append(f'<text class="{cls}" font-size="{size}" '
                          f'transform="matrix({a:.3f} {b:.3f} {c:.3f} {d:.3f} {X:.1f} {Y:.1f})">{text}</text>')

    def image_on_top(self, href, x, y, z, w, h, px_w, px_h):
        """Put a bitmap flat on a horizontal surface (the e-paper screen)."""
        X, Y = self.p(x, y, z)
        self.p(x + w, y + h, z)
        su, sv = w / px_w, h / px_h
        a, b = C30 * self.s * su, 0.5 * self.s * su
        c, d = -C30 * self.s * sv, 0.5 * self.s * sv
        self.items.append(f'<image class="bp-screen" href="{href}" width="{px_w}" height="{px_h}" '
                          f'preserveAspectRatio="none" '
                          f'transform="matrix({a:.4f} {b:.4f} {c:.4f} {d:.4f} {X:.1f} {Y:.1f})"/>')

    def label(self, at, text, dx, dy, accent=False):
        """A callout: a dot on the part, a leader line and a mono caption.
        dx/dy is where the caption sits relative to the dot, in screen pixels."""
        X, Y = self.p(*at)
        tx, ty = X + dx, Y + dy
        anchor = "end" if dx < 0 else "start"
        gap = -6 if dx < 0 else 6
        cls = " bp-accent" if accent else ""
        lines = text.split("\n")
        tspans = "".join(f'<tspan x="{tx + gap:.1f}" dy="{0 if i == 0 else 13}">{t}</tspan>'
                         for i, t in enumerate(lines))
        self.labels.append(
            f'<g class="bp-callout{cls}">'
            f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="2.6"/>'
            f'<polyline points="{X:.1f},{Y:.1f} {X + dx * 0.35:.1f},{ty:.1f} {tx:.1f},{ty:.1f}"/>'
            f'<text text-anchor="{anchor}" y="{ty + 4:.1f}">{tspans}</text></g>')
        width = 7 * max(len(t) for t in lines) + 8
        self.minx = min(self.minx, tx - width if dx < 0 else tx)
        self.maxx = max(self.maxx, tx + width if dx > 0 else tx)
        self.miny = min(self.miny, ty - 8)
        self.maxy = max(self.maxy, ty + 13 * len(lines))

    def svg(self, title, pad=14):
        x, y = self.minx - pad, self.miny - pad
        w, h = self.maxx - self.minx + 2 * pad, self.maxy - self.miny + 2 * pad
        return (f'<svg class="bp" viewBox="{x:.0f} {y:.0f} {w:.0f} {h:.0f}" role="img" aria-label="{title}">'
                + "".join(self.items) + "".join(self.labels) + "</svg>")


# parts (all sizes in mm, from the Raspberry Pi and Waveshare drawings) ----------

PI_W, PI_D, PCB = 65.0, 30.0, 1.4
HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 26.5), (61.5, 26.5)]
HEADER_X, HEADER_Y = 7.1, 1.0      # 2 × 20 pins at 2.54 mm
PITCH = 2.54
PORTS = {"hdmi": (12.4, 11.2, 3.3), "usb": (41.4, 7.8, 2.8), "pwr": (54.0, 7.8, 2.8)}


def pi_zero(f, ox=0.0, oy=0.0, oz=0.0, pins=True, accent_usb=False):
    """Raspberry Pi Zero 2 W, header at the back, ports facing the viewer."""
    f.box(ox, oy, oz, PI_W, PI_D, PCB, "bp-pcb")
    top = oz + PCB
    for hx, hy in HOLES:
        f.ellipse(ox + hx, oy + hy, top, 1.4)
    f.flat_text(ox + 20, oy + 24.5, top, "Raspberry Pi Zero 2 W", 2.3)
    # SD card slot on the left edge, camera connector on the right
    f.box(ox + 1.5, oy + 10, top, 11.5, 12, 1.3, "bp-metal")
    f.box(ox + 61, oy + 8, top, 3.2, 14, 1.2)
    # the SoC with its RAM on top
    f.box(ox + 25, oy + 9.5, top, 14, 14, 1.2, "bp-chip")
    f.flat_text(ox + 27.2, oy + 17.4, top + 1.2, "RP3A0", 2.6, "bp-silk-chip")
    f.box(ox + 16, oy + 12, top, 4, 4, 0.8, "bp-chip")
    f.box(ox + 44, oy + 13, top, 5, 3, 0.8, "bp-chip")
    if pins:
        f.box(ox + HEADER_X, oy + HEADER_Y, top, 20 * PITCH, 2 * PITCH, 2.5, "bp-plastic")
        for row in (0, 1):
            for i in range(20):
                px = ox + HEADER_X + PITCH / 2 + i * PITCH
                py = oy + HEADER_Y + PITCH / 2 + row * PITCH
                f.line((px, py, top + 2.5), (px, py, top + 8.5), "bp-pin")
    # ports on the front edge
    for name, (cx, w, h) in PORTS.items():
        tone = "bp-metal bp-accent" if (name == "usb" and accent_usb) else "bp-metal"
        f.box(ox + cx - w / 2, oy + PI_D - 5.5, top, w, 6.0, h, tone)


HAT_Z_PCB = 1.6
SCREEN = (6.0, 3.2, 48.5, 23.7)      # active area on the HAT: x, y, w, h


def hat(f, ox=0.0, oy=0.0, oz=0.0, socket=True, screen="img/moods/ready.png"):
    """Waveshare 2.13" e-Paper HAT V4 with its female header underneath."""
    if socket:
        f.box(ox + HEADER_X, oy + HEADER_Y, oz - 8.5, 20 * PITCH, 2 * PITCH, 8.5, "bp-plastic")
    f.box(ox, oy, oz, PI_W, PI_D, HAT_Z_PCB, "bp-pcb")
    top = oz + HAT_Z_PCB
    for hx, hy in HOLES:
        f.ellipse(ox + hx, oy + hy, top, 1.4)
    # the glass panel, its flex cable and the active area
    f.box(ox + 2.5, oy + 1.2, top, 57.5, 27.6, 1.0, "bp-glass")
    f.box(ox + 60, oy + 8, top, 3.5, 14, 0.4, "bp-flex")
    sx, sy, sw, sh = SCREEN
    glass = top + 1.0
    f.poly([(ox + sx - 0.6, oy + sy - 0.6, glass), (ox + sx + sw + 0.6, oy + sy - 0.6, glass),
            (ox + sx + sw + 0.6, oy + sy + sh + 0.6, glass), (ox + sx - 0.6, oy + sy + sh + 0.6, glass)],
           "bp-paper")
    if screen:
        f.image_on_top(screen, ox + sx, oy + sy, glass, sw, sh, 500, 244)


def sd_card(f, ox, oy, oz):
    f.box(ox, oy, oz, 15, 11, 1.0, "bp-card")
    f.flat_text(ox + 3, oy + 7, oz + 1.0, "microSD", 2.2)


def usb_plug(f, ox, oy, oz, tail=40, tone="bp-accent"):
    """Micro-USB plug pointing at -y (into a port), with its cable running towards +y."""
    f.box(ox - 3.6, oy, oz, 7.2, 6.5, 2.4, "bp-metal " + tone)
    f.box(ox - 5.5, oy + 6.5, oz - 1.6, 11, 12, 5.6, tone)
    cx, cy, cz = ox, oy + 18.5, oz + 1.2
    f.curve((cx, cy, cz), (cx, cy + tail * 0.7, cz), (cx + tail * 0.2, cy + tail, cz),
            (cx + tail * 1.1, cy + tail * 1.05, cz), "bp-cable " + tone)


SUGAR_PCB = 1.2
BATTERY = (4.0, 2.5, 57.0, 25.0, 5.5)   # x, y, w, d, h of the LiPo pouch under the board


def pisugar(f, ox=0.0, oy=0.0, oz=0.0, battery=True):
    """PiSugar 3: a Pi Zero sized board with its battery underneath and pogo pins on top
    that touch the Pi's header pads 1-6 (5 V, GND, SDA, SCL) from below. Simplified."""
    if battery:
        bx, by, bw, bd, bh = BATTERY
        f.box(ox + bx, oy + by, oz - bh, bw, bd, bh, "bp-plastic")
    f.box(ox, oy, oz, PI_W, PI_D, SUGAR_PCB, "bp-pcb")
    top = oz + SUGAR_PCB
    for hx, hy in HOLES:
        f.ellipse(ox + hx, oy + hy, top, 1.4)
    f.flat_text(ox + 22, oy + 22, top, "PiSugar 3", 2.6)
    # pogo pins under header pins 1-6, the first three columns of the header
    for row in (0, 1):
        for i in range(3):
            px = ox + HEADER_X + PITCH / 2 + i * PITCH
            py = oy + HEADER_Y + PITCH / 2 + row * PITCH
            f.box(px - 0.5, py - 0.5, top, 1.0, 1.0, 1.6, "bp-metal bp-accent")
    f.box(ox + 30, oy + 10, top, 6, 6, 0.9, "bp-chip")
    f.box(ox + PI_W - 7.5, oy + 11.5, top, 7.5, 9, 3.2, "bp-metal")        # USB-C for charging
    f.box(ox + 46, oy + PI_D - 4, top, 4, 3, 1.4, "bp-plastic")            # power button


# figures -----------------------------------------------------------------------

def fig_hero():
    f = Fig(4.2)
    sd_card(f, -24, 10.5, 0.3)
    pi_zero(f, accent_usb=True)
    usb_plug(f, PORTS["usb"][0], PI_D + 12, PCB + 0.2, tail=26)
    gap = 38
    for hx in (HEADER_X, HEADER_X + 20 * PITCH):
        f.line((hx, HEADER_Y, PCB + 9), (hx, HEADER_Y, gap - 8.5), "bp-dash")
    f.line((-9, 16.5, 0.8), (1.5, 16.5, 0.8), "bp-dash")
    f.line((PORTS["usb"][0], PI_D + 1, PCB + 1.4), (PORTS["usb"][0], PI_D + 12, PCB + 1.4), "bp-dash")
    hat(f, 0, 0, gap)
    f.label((63, 2, gap + 2.6), "2.13\" E-PAPER HAT V4\n250 × 122 px", 40, -42)
    f.label((HEADER_X + 20 * PITCH - 1, HEADER_Y + 4, PCB + 8.5), "40-PIN HEADER", 64, -34)
    f.label((62, 4, PCB), "RASPBERRY PI\nZERO 2 W", 52, -6)
    f.label((-16.5, 21.5, 0.8), "MICROSD CARD", -26, 40)
    f.label((54, PI_D + 0.5, PCB + 1.4), "PWR (NOT NEEDED)", 66, 34)
    f.label((PORTS["usb"][0] + 5.5, PI_D + 24, PCB), "USB DATA CABLE\nPOWER + NETWORK", 70, 26, accent=True)
    return f.svg("Exploded view: e-paper HAT, Raspberry Pi Zero 2 W, microSD card and USB cable")


def fig_stack(screen="img/moods/working.png"):
    """Assembled gotchi, used on the parts and docs pages."""
    f = Fig(4.4)
    pi_zero(f, accent_usb=True)
    hat(f, 0, 0, PCB + 2.5 + 8.5, socket=True, screen=screen)
    usb_plug(f, PORTS["usb"][0], PI_D + 0.5, PCB + 0.2, tail=30)
    f.label((63, 2, PCB + 14), "E-PAPER HAT", 38, -26)
    f.label((63.5, 6, PCB), "PI ZERO 2 W", 40, 4)
    f.label((PORTS["usb"][0] + 5.5, PI_D + 12, PCB), "TO YOUR COMPUTER", 60, 28, accent=True)
    return f.svg("The assembled gotchi with its USB cable")


def fig_pi():
    f = Fig(3.6)
    pi_zero(f)
    return f.svg("Raspberry Pi Zero 2 WH with header", pad=6)


def fig_hat():
    f = Fig(3.6)
    hat(f, 0, 0, 8.5, screen="img/moods/ready.png")
    return f.svg("Waveshare 2.13 inch e-Paper HAT V4", pad=6)


def fig_sd():
    f = Fig(6.5)
    sd_card(f, 0, 0, 0)
    return f.svg("microSD card", pad=6)


def fig_cable():
    f = Fig(4.0)
    usb_plug(f, 0, 0, 0, tail=34, tone="")
    return f.svg("Micro-USB data cable", pad=6)


def fig_sugar():
    f = Fig(3.6)
    pisugar(f, 0, 0, 5.5)
    return f.svg("PiSugar 3 battery board with its battery underneath", pad=6)


def fig_battery():
    """Exploded view: the PiSugar goes under the Pi, its pogo pins touch the header pads."""
    f = Fig(4.0)
    pisugar(f, 0, 0, 0)
    gap = 34
    for i in (0, 2):
        px = HEADER_X + PITCH / 2 + i * PITCH
        f.line((px, HEADER_Y + PITCH / 2, SUGAR_PCB + 1.6), (px, HEADER_Y + PITCH / 2, gap), "bp-dash")
    for hx, hy in ((61.5, 26.5), (3.5, 26.5), (61.5, 3.5)):
        f.line((hx, hy, SUGAR_PCB), (hx, hy, gap), "bp-dash")
    pi_zero(f, 0, 0, gap)
    f.label((HEADER_X + PITCH, HEADER_Y + 2 * PITCH, SUGAR_PCB + 1.6), "POGO PINS\n5 V · GND · SDA · SCL", -125, -14, accent=True)
    f.label((61.5, 3.5, gap * 0.45), "SCREWS + SPACERS", 70, -20)
    f.label((PI_W, 16, SUGAR_PCB + 3.2), "USB-C: CHARGING", 60, 34)
    f.label((48, PI_D - 1, SUGAR_PCB + 1.4), "POWER BUTTON", 40, 70)
    f.label((20, BATTERY[1] + BATTERY[3], -3), "BATTERY", -60, 40)
    f.label((62, 4, gap + PCB), "PI ZERO 2 W\n(HAT GOES ON TOP)", 52, -16)
    return f.svg("Exploded view: the PiSugar 3 screws under the Pi Zero; its pogo pins touch the header from below")


def fig_ports():
    """Plan view (from above) of the Pi with dimensions and the two USB ports."""
    s = 7.0
    W, D = PI_W * s, PI_D * s
    o = []
    o.append(f'<rect class="bp-t bp-pcb" x="0" y="0" width="{W}" height="{D}" rx="{3 * s}"/>')
    for hx, hy in HOLES:
        o.append(f'<circle class="bp-hole" cx="{hx * s}" cy="{hy * s}" r="{1.4 * s}"/>')
    o.append(f'<rect class="bp-t bp-plastic" x="{HEADER_X * s}" y="{HEADER_Y * s}" '
             f'width="{20 * PITCH * s}" height="{2 * PITCH * s}"/>')
    for row in range(2):
        for i in range(20):
            cx = (HEADER_X + PITCH / 2 + i * PITCH) * s
            cy = (HEADER_Y + PITCH / 2 + row * PITCH) * s
            o.append(f'<rect class="bp-pinhead" x="{cx - 3}" y="{cy - 3}" width="6" height="6"/>')
    o.append(f'<rect class="bp-t bp-metal" x="{1.5 * s}" y="{10 * s}" width="{11.5 * s}" height="{12 * s}"/>')
    o.append(f'<rect class="bp-t bp-chip" x="{25 * s}" y="{9.5 * s}" width="{14 * s}" height="{14 * s}"/>')
    o.append(f'<text class="bp-silk" x="{32 * s}" y="{17.3 * s}" text-anchor="middle" font-size="13">RP3A0</text>')
    o.append(f'<rect class="bp-t" x="{61 * s}" y="{8 * s}" width="{3.2 * s}" height="{14 * s}"/>')
    for name, (cx, w, _) in PORTS.items():
        cls = "bp-t bp-metal bp-accent" if name == "usb" else "bp-t bp-metal"
        o.append(f'<rect class="{cls}" x="{(cx - w / 2) * s}" y="{(PI_D - 5.5) * s}" '
                 f'width="{w * s}" height="{6 * s}"/>')
    # dimension lines
    o.append(f'<g class="bp-dim"><line x1="0" y1="{-26}" x2="{W}" y2="{-26}"/>'
             f'<line x1="0" y1="-34" x2="0" y2="-6"/><line x1="{W}" y1="-34" x2="{W}" y2="-6"/>'
             f'<text x="{W / 2}" y="-34" text-anchor="middle">65 MM</text>'
             f'<line x1="{W + 26}" y1="0" x2="{W + 26}" y2="{D}"/>'
             f'<line x1="{W + 6}" y1="0" x2="{W + 34}" y2="0"/><line x1="{W + 6}" y1="{D}" x2="{W + 34}" y2="{D}"/>'
             f'<text x="{W + 40}" y="{D / 2 + 4}">30 MM</text></g>')
    # callouts below the ports
    def call(cx, text, accent=False, dy=44):
        cls = "bp-callout bp-accent" if accent else "bp-callout"
        x, y = cx * s, D + 2
        return (f'<g class="{cls}"><circle cx="{x}" cy="{y}" r="2.6"/>'
                f'<polyline points="{x},{y} {x},{D + dy}"/>'
                f'<text x="{x}" y="{D + dy + 14}" text-anchor="middle">{text}</text></g>')
    o.append(call(PORTS["hdmi"][0], "MINI HDMI"))
    o.append(call(PORTS["usb"][0], "↑ USB · PLUG IN HERE", True, 70))
    o.append(call(PORTS["pwr"][0], "PWR", False, 30))
    o.append(f'<text class="bp-note" x="0" y="{-50}">TOP VIEW · HEADER AT THE BACK · PORTS AT THE FRONT</text>')
    return (f'<svg class="bp" viewBox="-12 -66 {W + 110:.0f} {D + 66 + 100:.0f}" role="img" '
            f'aria-label="Top view of the Pi Zero: plug the cable into the port labelled USB, not PWR">'
            + "".join(o) + "</svg>")


def fig_system():
    """Laptop → cable → gotchi."""
    f = Fig(1.6)
    lx, ly = -112, -14
    f.box(lx, ly, 0, 84, 58, 3, "bp-pcb")
    f.box(lx + 4, ly + 5, 3, 76, 28, 0.5, "bp-plastic")
    f.box(lx + 30, ly + 39, 3, 24, 14, 0.3)
    f.box(lx, ly - 3, 3, 84, 3, 54)
    f.poly([(lx + 4, ly, 7), (lx + 80, ly, 7), (lx + 80, ly, 53), (lx + 4, ly, 53)], "bp-paper")
    for i, w in enumerate([40, 58, 26, 50, 34, 62]):
        z = 48 - i * 6.5
        cls = "bp-code bp-accent" if i == 3 else "bp-code"
        f.line((lx + 9, ly, z), (lx + 9 + w, ly, z), cls)
    f.curve((lx + 84, ly + 34, 1.5), (lx + 120, ly + 34, 1.5), (PORTS["usb"][0], PI_D + 60, 1.5),
            (PORTS["usb"][0], PI_D + 18.5, 1.5), "bp-cable bp-accent")
    pi_zero(f, 0, 0, 0, accent_usb=True)
    hat(f, 0, 0, PCB + 2.5 + 8.5, screen="img/moods/done.png")
    f.box(PORTS["usb"][0] - 3.6, PI_D, PCB + 0.2, 7.2, 6.5, 2.4, "bp-metal bp-accent")
    f.box(PORTS["usb"][0] - 5.5, PI_D + 6.5, PCB - 1.4, 11, 12, 5.6, "bp-accent")
    f.label((lx + 2, ly - 1.5, 45), "CLAUDE CODE\nHOOKS + STATUS LINE", -36, -24)
    f.label((lx + 104, ly + 40, 1.5), "USB CABLE OR WI-FI\nHTTP · METADATA ONLY", -46, 74, accent=True)
    f.label((63, 2, 16), "CLAUDEGOTCHI\nONE MOOD FOR ALL SESSIONS", 30, -46)
    return f.svg("Claude Code on your computer sends events over the USB cable or Wi-Fi to the gotchi")


FIGURES = {
    "hero": fig_hero,
    "stack": fig_stack,
    "part-pi": fig_pi,
    "part-hat": fig_hat,
    "part-sd": fig_sd,
    "part-cable": fig_cable,
    "part-sugar": fig_sugar,
    "battery": fig_battery,
    "ports": fig_ports,
    "system": fig_system,
}


def main(docs):
    rendered = {}
    for name in sorted(os.listdir(docs)):
        if not name.endswith(".html"):
            continue
        path = os.path.join(docs, name)
        html = open(path, encoding="utf-8").read()

        def fill(m):
            key = m.group(1)
            if key not in rendered:
                rendered[key] = FIGURES[key]()
            return f"<!-- fig:{key} -->{rendered[key]}<!-- /fig:{key} -->"

        new = re.sub(r"<!-- fig:([\w-]+) -->.*?<!-- /fig:\1 -->", fill, html, flags=re.S)
        if new != html:
            open(path, "w", encoding="utf-8").write(new)
            print("updated", name)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../docs")
