"""Network diagnostics for /network: what the Wi-Fi driver and interface are doing.

The image has no SSH, so this is the way to see why a gotchi is not on Wi-Fi.
Never prints the Wi-Fi password.
"""
import mmap
import os
import socket
import struct
import subprocess
import tempfile

COMMANDS = (
    ("Wi-Fi driver", ["sh", "-c", "lsmod | grep -E '^(brcmfmac|brcmutil|cfg80211)' || echo 'brcmfmac not loaded'"]),
    ("Interfaces", ["ip", "addr"]),
    ("Routes", ["ip", "route"]),
    ("Kernel messages", ["sh", "-c", "dmesg | grep -iE 'brcm|wlan|cfg80211|ieee80211|firmware' | tail -n 60"]),
    ("wpa_supplicant start", ["sh", "-c", "cat /run/wpa_supplicant.log 2>/dev/null || echo '(no log)'"]),
    ("I2C kernel", ["sh", "-c", "ls /dev/i2c* /sys/bus/i2c/devices/ 2>&1; "
                    "cat /proc/device-tree/soc/i2c@7e804000/status 2>&1; echo; "
                    "dmesg | grep -iE 'i2c|pisugar' | tail -n 20"]),
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


def i2c_scan(bus=1):
    """Addresses on the I2C bus that answer (like i2cdetect), to see which battery
    board is there: PiSugar 3 at 0x57, PiSugar 2 at 0x75 (+ RTC at 0x32)."""
    from .battery import SMBus
    found = []
    for addr in range(0x08, 0x78):
        try:
            dev = SMBus(bus, addr)
        except OSError as e:
            if addr == 0x08:
                return f"(no I2C bus {bus}: {e})"
            continue
        try:
            dev.read_byte(0)
            found.append(f"0x{addr:02x}")
        except OSError:
            pass
        finally:
            dev.close()
    return " ".join(found) or "(nothing answers)"


ALT = {0: "input", 1: "output", 4: "alt0", 5: "alt1", 6: "alt2", 7: "alt3", 3: "alt4", 2: "alt5"}


def gpio_functions(pins=(2, 3), gpiomem="/dev/gpiomem"):
    """What GPIO 2/3 (I2C SDA/SCL, pins 3/5) are set to; I2C needs alt0."""
    try:
        with open(gpiomem, "r+b") as f:
            m = mmap.mmap(f.fileno(), 4096)
            regs = {}
            for pin in pins:
                reg = pin // 10
                if reg not in regs:
                    regs[reg] = struct.unpack_from("<I", m, reg * 4)[0]
                regs_val = (regs[reg] >> ((pin % 10) * 3)) & 7
                yield f"GPIO{pin}: {ALT.get(regs_val, regs_val)}"
            m.close()
    except OSError as e:
        yield f"(cannot read {gpiomem}: {e})"


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
    lines += ["== I2C bus 1 (battery)", i2c_scan(), *gpio_functions(), ""]
    lines += ["== wpa_supplicant", wpa("STATUS"), "", "== Networks in range", wpa("SCAN_RESULTS"), ""]
    return "\n".join(lines)
