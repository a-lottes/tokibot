"""Display drivers. Every driver has show(img, full) and close().

New displays: register the class here and select it in claudegotchi.toml
under [device] display = "<name>".
"""


def open_display(name, rotate=0, png=""):
    if name == "sim":
        from .sim import SimDisplay
        return SimDisplay(png)
    if name == "waveshare_2in13_v4":
        from .waveshare_2in13_v4 import Waveshare2in13V4
        return Waveshare2in13V4(rotate)
    raise ValueError(f"Unknown display: {name}")
