"""Network diagnostics for /network: what the Wi-Fi driver and interface are doing.

The image has no SSH, so this is the way to see why a gotchi is not on Wi-Fi.
Never prints the Wi-Fi password.
"""
import os
import socket
import subprocess
import tempfile

COMMANDS = (
    ("Wi-Fi driver", ["sh", "-c", "lsmod | grep -E '^(brcmfmac|brcmutil|cfg80211)' || echo 'brcmfmac not loaded'"]),
    ("Interfaces", ["ip", "addr"]),
    ("Routes", ["ip", "route"]),
    ("Kernel messages", ["sh", "-c", "dmesg | grep -iE 'brcm|wlan|cfg80211|ieee80211|firmware' | tail -n 60"]),
    ("wpa_supplicant start", ["sh", "-c", "cat /run/wpa_supplicant.log 2>/dev/null || echo '(no log)'"]),
    ("Processes", ["sh", "-c", "ps | grep -E 'wpa_supplicant|udhcpc|ntpd' | grep -v grep"]),
)


def wifi_up(operstate="/sys/class/net/wlan0/operstate"):
    """True while wlan0 is associated with a network (for the header icon)."""
    try:
        with open(operstate) as f:
            return f.read().strip() == "up"
    except OSError:
        return False


def wpa(command, ctrl="/run/wpa_supplicant/wlan0"):
    """Ask wpa_supplicant over its control socket (the image has no wpa_cli)."""
    local = os.path.join(tempfile.gettempdir(), f"tokibot-wpa-{os.getpid()}")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        if os.path.exists(local):
            os.unlink(local)
        s.bind(local)
        s.settimeout(5)
        s.connect(ctrl)
        s.send(command.encode())
        return s.recv(16384).decode(errors="replace").rstrip()
    except OSError as e:
        return f"(wpa_supplicant not reachable: {e})"
    finally:
        s.close()
        if os.path.exists(local):
            os.unlink(local)


def report(cfg):
    wifi = cfg.get("wifi", {})
    lines = [f"Configured Wi-Fi: {wifi.get('ssid') or '(none)'}, country {wifi.get('country') or '?'}",
             f"Password set: {'yes' if wifi.get('psk') else 'no'}", ""]
    for title, cmd in COMMANDS:
        lines.append(f"== {title}")
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            lines.append((out.stdout + out.stderr).rstrip() or "(no output)")
        except (OSError, subprocess.TimeoutExpired) as e:
            lines.append(f"(not available: {e})")
        lines.append("")
    lines += ["== wpa_supplicant", wpa("STATUS"), "", "== Networks in range", wpa("SCAN_RESULTS"), ""]
    return "\n".join(lines)
