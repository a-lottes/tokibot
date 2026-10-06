"""Settings from tokibot.toml (on the device: boot partition, /boot/tokibot.toml).

  python3 -m tokibot.config shell [file]   print the values as shell variables
                                                 (used by the image's init scripts)
"""
import copy
import json
import os
import re
import shlex
import sys

try:
    import tomllib
except ImportError:          # Python < 3.11 (e.g. the system Python on a Mac)
    tomllib = None

DEFAULT_PATH = "/boot/tokibot.toml"
LEGACY_PATH = "/boot/claudegotchi.toml"      # from before the rename


def default_path():
    """$TOKIBOT_CONFIG, else /boot/tokibot.toml, else the file from before the rename."""
    env = os.environ.get("TOKIBOT_CONFIG") or os.environ.get("CLAUDEGOTCHI_CONFIG")
    if env:
        return env
    if not os.path.exists(DEFAULT_PATH) and os.path.exists(LEGACY_PATH):
        return LEGACY_PATH
    return DEFAULT_PATH

DEFAULTS = {
    "device": {"display": "waveshare_2in13_v4", "rotate": 0, "timezone": "Europe/Berlin",
               "data_dir": "/data"},
    "server": {"host": "0.0.0.0", "port": 8765, "token": ""},
    "wifi": {"ssid": "", "psk": "", "country": "DE"},
    "usb": {"enabled": True, "address": "192.168.77.1"},
    "relay": {"url": "", "auth": ""},
    "social": {"enabled": True, "radio": "auto"},
    "battery": {"model": "auto", "shutdown_at": 5, "i2c_bus": 1},
}


def _value(raw):
    raw = raw.strip()
    m = re.match(r'"((?:[^"\\]|\\.)*)"', raw)
    if m:                                  # "text": escapes as in JSON
        return json.loads(m.group(0))
    m = re.match(r"'([^']*)'", raw)
    if m:                                  # 'text': literal
        return m.group(1)
    raw = raw.split("#", 1)[0].strip()
    if raw in ("true", "false"):
        return raw == "true"
    try:
        return int(raw)
    except ValueError:
        return float(raw)


def _parse_simple_toml(text):
    """Stand-in for tomllib on Python < 3.11. Enough for tokibot.toml:
    [sections] and key = "text" | 'text' | number | true/false."""
    data, current = {}, None
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.split("#", 1)[0].strip().endswith("]"):
            current = data.setdefault(line.split("#", 1)[0].strip()[1:-1].strip(), {})
            continue
        if "=" not in line:
            raise ValueError(f"line {n}: cannot parse: {line}")
        key, raw = line.split("=", 1)
        (current if current is not None else data)[key.strip()] = _value(raw)
    return data


def load(path=None):
    cfg = copy.deepcopy(DEFAULTS)
    path = path or default_path()
    try:
        with open(path, "rb") as f:
            raw = f.read()
        data = tomllib.loads(raw.decode("utf-8")) if tomllib else _parse_simple_toml(raw.decode("utf-8"))
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
        "SOCIAL_ENABLED": "1" if cfg["social"]["enabled"] and cfg["social"]["radio"] != "off" else "0",
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
