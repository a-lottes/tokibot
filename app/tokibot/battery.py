"""Battery support: a PiSugar 3 (or 3 Plus) under the Pi, read over I2C.

The battery is optional. With [battery] model = "auto" the gotchi looks for a PiSugar
at start; without one everything works as before and nothing battery related is shown.

PiSugar 3 registers (I2C address 0x57, bus 1 = pins 3/5, which the pogo pins use):
  0x02        control 1, bit 7 = external power (USB-C on the PiSugar) plugged in
  0x22, 0x23  battery voltage in mV, high byte first
  0x2A        charge in percent (0–100), computed by the PiSugar itself

No extra Python packages: SMBus transfers go straight through the i2c-dev ioctl.
"""
import ctypes
import fcntl
import logging
import os
import threading
import time

from .mood import BATTERY_LOW, BATTERY_POLL

log = logging.getLogger("tokibot")

# <linux/i2c-dev.h>, <linux/i2c.h>
I2C_SLAVE = 0x0703
I2C_SMBUS = 0x0720
I2C_SMBUS_READ = 1
I2C_SMBUS_BYTE_DATA = 2


class _SmbusData(ctypes.Union):
    _fields_ = [("byte", ctypes.c_uint8), ("word", ctypes.c_uint16),
                ("block", ctypes.c_uint8 * 34)]


class _SmbusIoctl(ctypes.Structure):
    _fields_ = [("read_write", ctypes.c_uint8), ("command", ctypes.c_uint8),
                ("size", ctypes.c_uint32), ("data", ctypes.POINTER(_SmbusData))]


class SMBus:
    """Just enough of an SMBus for reading byte registers of one chip."""
    def __init__(self, bus, address):
        self.fd = os.open(f"/dev/i2c-{bus}", os.O_RDWR)
        try:
            fcntl.ioctl(self.fd, I2C_SLAVE, address)
        except OSError:
            os.close(self.fd)
            raise

    def read_byte(self, register):
        data = _SmbusData()
        msg = _SmbusIoctl(I2C_SMBUS_READ, register, I2C_SMBUS_BYTE_DATA, ctypes.pointer(data))
        fcntl.ioctl(self.fd, I2C_SMBUS, msg)
        return data.byte

    def close(self):
        os.close(self.fd)


class PiSugar3:
    ADDRESS = 0x57
    REG_CTRL1, REG_VOLT_HI, REG_VOLT_LO, REG_PERCENT = 0x02, 0x22, 0x23, 0x2A

    def __init__(self, bus):
        self.bus = bus            # anything with read_byte(register)

    def read(self):
        pct = self.bus.read_byte(self.REG_PERCENT)
        mv = (self.bus.read_byte(self.REG_VOLT_HI) << 8) | self.bus.read_byte(self.REG_VOLT_LO)
        plugged = bool(self.bus.read_byte(self.REG_CTRL1) & 0x80)
        if pct > 100 or not 2500 <= mv <= 4600:
            raise ValueError(f"implausible reading: {pct}%, {mv} mV")
        return {"pct": pct, "mv": mv, "plugged": plugged, "charging": plugged and pct < 100}

    def close(self):
        if hasattr(self.bus, "close"):
            self.bus.close()


class SimBattery:
    """Pretend battery for the simulator: drains 1 % every few seconds, then 'charges'
    back up once it is empty, so the low-battery mood and the header icon can be seen."""
    def __init__(self, start=60, seconds_per_pct=4.0):
        self.start, self.rate, self.t0 = start, seconds_per_pct, time.monotonic()

    def read(self):
        steps = int((time.monotonic() - self.t0) / self.rate)
        cycle = self.start + 100          # down to 0, then back up to 100
        n = steps % cycle
        if n < self.start:
            pct, plugged = self.start - n, False
        else:
            pct, plugged = min(100, n - self.start), True
        return {"pct": pct, "mv": 3300 + 9 * pct, "plugged": plugged,
                "charging": plugged and pct < 100}

    def close(self):
        pass


def detect(cfg):
    """The battery from [battery] model: "auto" (look for a PiSugar 3), "pisugar3",
    "sim[:PCT]" (simulator) or "none". Returns None when there is none."""
    model = str(cfg.get("model", "auto")).strip().lower()
    if model in ("", "none", "off"):
        return None
    if model.startswith("sim"):
        start = model.partition(":")[2]
        return SimBattery(int(start) if start.isdigit() else 60)
    if model not in ("auto", "pisugar3"):
        log.warning("Unknown battery model %r, ignoring it", model)
        return None
    bus = int(cfg.get("i2c_bus", 1))
    try:
        dev = PiSugar3(SMBus(bus, PiSugar3.ADDRESS))
    except OSError as e:
        (log.warning if model == "pisugar3" else log.debug)("No I2C bus %d: %s", bus, e)
        return None
    try:
        dev.read()
    except (OSError, ValueError) as e:
        (log.warning if model == "pisugar3" else log.debug)("No PiSugar 3 on I2C bus %d: %s", bus, e)
        dev.close()
        return None
    log.info("PiSugar 3 found on I2C bus %d", bus)
    return dev


class BatteryMonitor(threading.Thread):
    """Polls the battery and powers the gotchi down before the battery dies.

    state is the last good reading (or None). on_empty is called once when the charge
    stayed at or below shutdown_at for EMPTY_READINGS polls in a row without power.
    """
    EMPTY_READINGS = 3

    def __init__(self, device, shutdown_at=5, low_at=BATTERY_LOW, on_empty=None,
                 poll=BATTERY_POLL):
        super().__init__(daemon=True)
        self.device, self.shutdown_at, self.low_at = device, int(shutdown_at), int(low_at)
        self.on_empty, self.poll = on_empty, poll
        self.state, self.empty_count, self.fired = None, 0, False
        self.stop_evt = threading.Event()

    def check(self):
        try:
            s = self.device.read()
        except (OSError, ValueError) as e:
            log.debug("Battery read failed: %s", e)
            return
        if self.state is None or s["plugged"] != self.state["plugged"]:
            log.info("Battery: %d%%, %s", s["pct"], "on power" if s["plugged"] else "on battery")
        self.state = s
        if not s["plugged"] and self.shutdown_at > 0 and s["pct"] <= self.shutdown_at:
            self.empty_count += 1
        else:
            self.empty_count = 0
        if self.empty_count >= self.EMPTY_READINGS and not self.fired and self.on_empty:
            self.fired = True
            log.warning("Battery empty (%d%%), shutting down", s["pct"])
            self.on_empty()

    def low(self):
        s = self.state
        return bool(s and not s["plugged"] and s["pct"] <= self.low_at)

    def run(self):
        while not self.stop_evt.is_set():
            self.check()
            self.stop_evt.wait(self.poll)
