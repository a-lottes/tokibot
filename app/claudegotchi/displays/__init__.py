"""Display-Treiber. Jeder Treiber hat show(img, full) und close().

Neue Displays: Klasse hier eintragen und in claudegotchi.toml unter
[device] display = "<name>" auswählen.
"""


def open_display(name, rotate=0, png=""):
    if name == "sim":
        from .sim import SimDisplay
        return SimDisplay(png)
    if name == "waveshare_2in13_v4":
        from .waveshare_2in13_v4 import Waveshare2in13V4
        return Waveshare2in13V4(rotate)
    raise ValueError(f"Unbekanntes Display: {name}")
