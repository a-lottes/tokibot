"""Display drivers. Every driver has show(img, full) and close().

Select one in claudegotchi.toml under [device] display = "<name>". New displays: add
the class to DISPLAYS. Pwnagotchi's names for the same panels work too (ALIASES), so a
known Pwnagotchi setup can be copied over.
"""
import logging

log = logging.getLogger("claudegotchi")

# name: (label for the settings page, class in waveshare_epd.py)
DISPLAYS = {
    "waveshare_2in13_v4": ('Waveshare 2.13" V4 (black/white)', "Waveshare2in13V4"),
    "waveshare_2in13_v3": ('Waveshare 2.13" V3 (black/white)', "Waveshare2in13V3"),
    "waveshare_2in13_v2": ('Waveshare 2.13" V2 (black/white)', "Waveshare2in13V2"),
    "waveshare_2in13_v1": ('Waveshare 2.13" V1 (black/white)', "Waveshare2in13V1"),
    "waveshare_2in13b_v4": ('Waveshare 2.13" B V4 (black/white/red, slow)', "Waveshare2in13bV4"),
    "waveshare_2in7_v2": ('Waveshare 2.7" V2 (black/white)', "Waveshare2in7V2"),
    "waveshare_2in7_v1": ('Waveshare 2.7" V1 (black/white, slow)', "Waveshare2in7V1"),
}

# Pwnagotchi's [ui.display] type names
ALIASES = {
    "waveshare_4": "waveshare_2in13_v4", "waveshare4": "waveshare_2in13_v4", "ws_4": "waveshare_2in13_v4",
    "waveshare_3": "waveshare_2in13_v3", "waveshare3": "waveshare_2in13_v3", "ws_3": "waveshare_2in13_v3",
    "waveshare_2": "waveshare_2in13_v2", "waveshare2": "waveshare_2in13_v2", "ws_2": "waveshare_2in13_v2",
    "waveshare_1": "waveshare_2in13_v1", "waveshare1": "waveshare_2in13_v1", "ws_1": "waveshare_2in13_v1",
    "waveshare2in13b_v4": "waveshare_2in13b_v4",
    "waveshare27inch": "waveshare_2in7_v1", "waveshare2in7": "waveshare_2in7_v1",
    "waveshare27inchv2": "waveshare_2in7_v2", "waveshare2in7_v2": "waveshare_2in7_v2",
}


def resolve(name):
    """The DISPLAYS key for a name or alias, or None."""
    name = str(name).strip().lower()
    name = ALIASES.get(name, name)
    return name if name in DISPLAYS else None


def open_display(name, rotate=0, png=""):
    if name == "sim":
        from .sim import SimDisplay
        return SimDisplay(png)
    key = resolve(name)
    if key is None:
        # Keep running without a picture, so the settings page can still fix the name.
        log.error("Unknown display %r, choose one of: %s", name, ", ".join(DISPLAYS))
        from .sim import SimDisplay
        return SimDisplay(png)
    from . import waveshare_epd
    return getattr(waveshare_epd, DISPLAYS[key][1])(rotate)
