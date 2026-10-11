"""Settings from Raspberry Pi Imager's OS customisation, taken over on first boot.

Imager writes what was entered in its customisation step as files onto the boot
partition. Tokibot's repository for Imager (downloads/imager.json on the website)
asks for the cloud-init format, which Imager 1.8 and every Imager 2 understand:

  user-data        time zone (also hostname, user, SSH: not used on the gotchi)
  network-config   Wi-Fi name, password and country
  meta-data        nothing of interest

Newer Imagers can also write rpi-preseed.toml, read here too. The values go into
tokibot.toml and the Imager files are deleted, so later changes on the settings
page are not overwritten at the next boot. The gotchi keeps its own name
(tokibot-xxxx), user accounts and SSH do not exist on it.

  python3 -m tokibot.imager [boot dir]   run by the image's S04imager at boot
"""
import os
import re
import sys

from . import settings

try:
    import tomllib
except ImportError:          # Python < 3.11 (e.g. the system Python on a Mac)
    tomllib = None

FILES = ("rpi-preseed.toml", "user-data", "network-config", "meta-data")

_ESCAPES = {"0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v",
            "f": "\f", "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\",
            "N": "\x85", "_": "\xa0", "L": " ", "P": " "}
_HEX = {"x": 2, "u": 4, "U": 8}


def _double_quoted(text):
    """A YAML "double-quoted" scalar at the start of text -> (value, rest after it)."""
    out, i = [], 1
    while i < len(text):
        c = text[i]
        if c == '"':
            return "".join(out), text[i + 1:]
        if c == "\\" and i + 1 < len(text):
            e = text[i + 1]
            if e in _HEX:
                n = _HEX[e]
                out.append(chr(int(text[i + 2:i + 2 + n], 16)))
                i += 2 + n
                continue
            out.append(_ESCAPES.get(e, e))
            i += 2
            continue
        out.append(c)
        i += 1
    raise ValueError("unterminated string")


def _scalar(text):
    if text.startswith('"'):
        return _double_quoted(text)[0]
    if text.startswith("'"):
        m = re.match(r"'((?:[^']|'')*)'", text)
        return m.group(1).replace("''", "'") if m else text
    text = re.split(r"\s#", text, maxsplit=1)[0].strip()
    if text in ("true", "false"):
        return text == "true"
    return text


def parse_yaml(text):
    """Just enough YAML for what Imager writes: nested mappings with plain, 'single'
    or "double" quoted keys and values. Lists and block scalars are skipped."""
    root = {}
    stack = [(-1, root)]
    skip_deeper = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if skip_deeper is not None:
            if indent > skip_deeper:
                continue
            skip_deeper = None
        if stripped == "-" or stripped.startswith("- "):
            skip_deeper = indent                 # a list item and whatever belongs to it
            continue
        if stripped.startswith('"'):
            try:
                key, rest = _double_quoted(stripped)
            except ValueError:
                continue
            if not rest.startswith(":"):
                continue
            rest = rest[1:].strip()
        else:
            m = re.match(r"(.*?):(?:\s+(.*))?$", stripped)
            if not m:
                continue
            key, rest = m.group(1).strip().strip("'"), (m.group(2) or "").strip()
        while stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        if not rest or rest.startswith("#"):
            child = {}
            parent[key] = child
            stack.append((indent, child))
        elif rest[0] in "|>":
            parent[key] = ""
            skip_deeper = indent
        else:
            parent[key] = _scalar(rest)
    return root


def _wifi(ssid, password, country):
    changes = {("wifi", "ssid"): ssid, ("wifi", "psk"): password or ""}
    if country:
        changes[("wifi", "country")] = str(country).strip().upper()
    return changes


def from_cloudinit(user_data="", network_config=""):
    """{(section, key): value} from Imager's cloud-init files."""
    changes = {}
    user = parse_yaml(user_data) if user_data else {}
    if isinstance(user.get("timezone"), str) and user["timezone"].strip():
        changes[("device", "timezone")] = user["timezone"].strip()
    net = parse_yaml(network_config) if network_config else {}
    wifis = (net.get("network") or {}).get("wifis") or {}
    for iface in wifis.values() if isinstance(wifis, dict) else ():
        if not isinstance(iface, dict) or not isinstance(iface.get("access-points"), dict):
            continue
        for ssid, ap in iface["access-points"].items():
            ap = ap if isinstance(ap, dict) else {}
            auth = ap.get("auth") if isinstance(ap.get("auth"), dict) else {}
            password = ap.get("password") or auth.get("password") or ""
            changes.update(_wifi(str(ssid), str(password), iface.get("regulatory-domain")))
            return changes                       # the first network is the one entered
    return changes


def _load_toml(text):
    if tomllib:
        return tomllib.loads(text)
    from .config import _parse_simple_toml
    simple = [l for l in text.splitlines()
              if re.match(r'\s*(\[[^\]]+\]|[A-Za-z0-9_-]+\s*=\s*("|\'|true|false|\d))', l)]
    return _parse_simple_toml("\n".join(simple))


def from_preseed(text):
    """{(section, key): value} from rpi-preseed.toml."""
    data = _load_toml(text)
    changes = {}
    wlan = data.get("wlan") or {}
    ssid = wlan.get("ssid")
    if not ssid and wlan.get("ssid_hex"):
        ssid = bytes.fromhex(wlan["ssid_hex"]).decode("utf-8", "replace")
    if ssid:
        changes.update(_wifi(ssid, wlan.get("password"), wlan.get("country")))
    timezone = (data.get("locale") or {}).get("timezone")
    if timezone:
        changes[("device", "timezone")] = timezone
    return changes


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def read(boot):
    """The settings Imager left on the boot partition."""
    changes = from_cloudinit(_read(os.path.join(boot, "user-data")),
                             _read(os.path.join(boot, "network-config")))
    preseed = _read(os.path.join(boot, "rpi-preseed.toml"))
    if preseed:
        changes.update(from_preseed(preseed))
    return changes


def take_over(boot="/boot", config_path=None):
    """Move Imager's settings into tokibot.toml and delete its files. Returns the changes."""
    found = [os.path.join(boot, n) for n in FILES if os.path.exists(os.path.join(boot, n))]
    if not found:
        return {}
    try:
        changes = read(boot)
    except (ValueError, TypeError) as e:       # unreadable: drop the files, keep the settings
        print(f"Imager settings: cannot read them ({e})", file=sys.stderr)
        changes = {}
    if not config_path:
        config_path = os.path.join(boot, "tokibot.toml")
        legacy = os.path.join(boot, "claudegotchi.toml")
        if not os.path.exists(config_path) and os.path.exists(legacy):
            config_path = legacy
    settings.write_config(config_path, changes, remove=found)
    return changes


def describe(changes):
    parts = []
    if ("wifi", "ssid") in changes:
        parts.append(f"Wi-Fi {changes[('wifi', 'ssid')]}")
    if ("device", "timezone") in changes:
        parts.append(f"time zone {changes[('device', 'timezone')]}")
    return ", ".join(parts) or "nothing to take over"


def main(argv):
    boot = argv[1] if len(argv) > 1 else "/boot"
    if not any(os.path.exists(os.path.join(boot, n)) for n in FILES):
        return 0
    print("Imager settings: " + describe(take_over(boot)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
