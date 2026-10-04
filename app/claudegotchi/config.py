"""Einstellungen aus claudegotchi.toml (auf dem Gerät: Boot-Partition, /boot/claudegotchi.toml).

  python3 -m claudegotchi.config shell [datei]   – Werte als Shell-Variablen ausgeben
                                                   (für die Init-Skripte des Images)
"""
import copy
import os
import shlex
import sys
import tomllib

DEFAULT_PATH = "/boot/claudegotchi.toml"

DEFAULTS = {
    "device": {"display": "waveshare_2in13_v4", "rotate": 0, "timezone": "Europe/Berlin"},
    "server": {"host": "0.0.0.0", "port": 8765, "token": ""},
    "wifi": {"ssid": "", "psk": "", "country": "DE"},
    "usb": {"enabled": True, "address": "192.168.77.1"},
}


def load(path=None):
    cfg = copy.deepcopy(DEFAULTS)
    path = path or os.environ.get("CLAUDEGOTCHI_CONFIG", DEFAULT_PATH)
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        data = {}
    for section, values in data.items():
        if isinstance(values, dict):
            cfg.setdefault(section, {}).update(values)
    return cfg


def shell(cfg):
    pairs = {
        "WIFI_SSID": cfg["wifi"]["ssid"],
        "WIFI_PSK": cfg["wifi"]["psk"],
        "WIFI_COUNTRY": cfg["wifi"]["country"],
        "USB_ENABLED": "1" if cfg["usb"]["enabled"] else "0",
        "USB_ADDRESS": cfg["usb"]["address"],
        "TIMEZONE": cfg["device"]["timezone"],
    }
    return "\n".join(f"{k}={shlex.quote(str(v))}" for k, v in pairs.items())


def main(argv):
    if len(argv) >= 2 and argv[1] == "shell":
        print(shell(load(argv[2] if len(argv) > 2 else None)))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
