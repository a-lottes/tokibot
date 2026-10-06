import ctypes
import time
import unittest
from unittest import mock

from tokibot import battery
from tokibot.brain import Brain
from tokibot import server
from tokibot.painter import Painter
from tokibot.renderer import Renderer


class FakeI2C:
    """Stands in for the PiSugar 3 on the I2C bus: a register map."""
    def __init__(self, pct=80, mv=3900, plugged=False):
        self.regs = {}
        self.set(pct, mv, plugged)
        self.fail = False

    def set(self, pct, mv=3900, plugged=False):
        self.regs.update({0x2A: pct, 0x22: mv >> 8, 0x23: mv & 0xFF,
                          0x02: 0x80 | 0x40 if plugged else 0x40})

    def read_byte(self, register):
        if self.fail:
            raise OSError(121, "Remote I/O error")
        return self.regs[register]


def monitor(bus, **kw):
    return battery.BatteryMonitor(battery.PiSugar3(bus), **kw)


class PiSugar3Test(unittest.TestCase):
    def test_reads_percent_voltage_and_power(self):
        s = battery.PiSugar3(FakeI2C(pct=73, mv=3987, plugged=True)).read()
        self.assertEqual(s, {"pct": 73, "mv": 3987, "plugged": True, "charging": True})

    def test_full_and_plugged_is_not_charging(self):
        s = battery.PiSugar3(FakeI2C(pct=100, mv=4200, plugged=True)).read()
        self.assertFalse(s["charging"])

    def test_implausible_reading_is_refused(self):
        with self.assertRaises(ValueError):
            battery.PiSugar3(FakeI2C(pct=255)).read()
        with self.assertRaises(ValueError):
            battery.PiSugar3(FakeI2C(mv=0)).read()

    def test_smbus_read_goes_through_the_ioctl(self):
        regs = {0x2A: 42, 0x22: 0x0F, 0x23: 0x3C, 0x02: 0x00}
        calls = []

        def fake_ioctl(fd, request, arg):
            calls.append(request)
            if request == battery.I2C_SMBUS:
                self.assertEqual((arg.read_write, arg.size), (1, battery.I2C_SMBUS_BYTE_DATA))
                arg.data.contents.byte = regs[arg.command]
            else:
                self.assertEqual((request, arg), (battery.I2C_SLAVE, 0x57))
            return 0

        with mock.patch.object(battery.os, "open", return_value=99), \
                mock.patch.object(battery.os, "close"), \
                mock.patch.object(battery.fcntl, "ioctl", fake_ioctl):
            dev = battery.detect({"model": "auto"})
            self.assertEqual(dev.read(), {"pct": 42, "mv": 3900, "plugged": False, "charging": False})
        self.assertEqual(calls[0], battery.I2C_SLAVE)

    def test_ioctl_struct_matches_the_kernel(self):
        # struct i2c_smbus_ioctl_data: u8, u8, u32, pointer
        self.assertEqual(ctypes.sizeof(battery._SmbusIoctl), 8 + ctypes.sizeof(ctypes.c_void_p))
        self.assertEqual(ctypes.sizeof(battery._SmbusData), 34)


class DetectTest(unittest.TestCase):
    def test_none_and_sim(self):
        self.assertIsNone(battery.detect({"model": "none"}))
        self.assertIsInstance(battery.detect({"model": "sim:20"}), battery.SimBattery)
        self.assertEqual(battery.detect({"model": "sim:20"}).read()["pct"], 20)

    def test_auto_without_i2c_bus_finds_nothing(self):
        self.assertIsNone(battery.detect({"model": "auto", "i2c_bus": 99}))

    def test_sim_drains_then_charges(self):
        b = battery.SimBattery(start=3, seconds_per_pct=0.01)
        seen = set()
        end = time.monotonic() + 0.2
        while time.monotonic() < end:
            s = b.read()
            seen.add((s["pct"] <= 3, s["plugged"]))
        self.assertIn((True, False), seen)
        self.assertIn((False, True), seen)


class MonitorTest(unittest.TestCase):
    def test_shuts_down_after_three_empty_readings(self):
        bus, calls = FakeI2C(pct=4), []
        m = monitor(bus, shutdown_at=5, on_empty=lambda: calls.append(1))
        m.check()
        m.check()
        self.assertEqual(calls, [])
        m.check()
        m.check()
        self.assertEqual(calls, [1])           # only once

    def test_no_shutdown_on_power_or_when_disabled(self):
        calls = []
        m = monitor(FakeI2C(pct=2, plugged=True), on_empty=lambda: calls.append(1))
        for _ in range(5):
            m.check()
        m = monitor(FakeI2C(pct=2), shutdown_at=0, on_empty=lambda: calls.append(1))
        for _ in range(5):
            m.check()
        self.assertEqual(calls, [])

    def test_a_good_reading_resets_the_count(self):
        bus, calls = FakeI2C(pct=4), []
        m = monitor(bus, on_empty=lambda: calls.append(1))
        m.check()
        m.check()
        bus.set(30)
        m.check()
        bus.set(4)
        m.check()
        m.check()
        self.assertEqual(calls, [])

    def test_read_errors_keep_the_last_state(self):
        bus = FakeI2C(pct=50)
        m = monitor(bus)
        m.check()
        bus.fail = True
        m.check()
        self.assertEqual(m.state["pct"], 50)


class BrainBatteryTest(unittest.TestCase):
    def test_no_battery_changes_nothing(self):
        v = Brain().view()
        self.assertIsNone(v["battery"])
        self.assertEqual(v["mood"], "idle")

    def test_low_battery_mood(self):
        m = monitor(FakeI2C(pct=12))
        m.check()
        v = Brain(battery=m).view()
        self.assertEqual(v["mood"], "lowbattery")
        self.assertIn("12%", v["message"])
        self.assertEqual(v["battery"]["pct"], 12)

    def test_low_but_plugged_in_is_fine(self):
        m = monitor(FakeI2C(pct=12, plugged=True))
        m.check()
        self.assertEqual(Brain(battery=m).view()["mood"], "idle")

    def test_permission_beats_low_battery(self):
        m = monitor(FakeI2C(pct=12))
        m.check()
        b = Brain(battery=m)
        b.handle_hook({"hook_event_name": "PermissionRequest", "session_id": "s",
                       "ts": time.time(), "tool_name": "Bash"})
        self.assertEqual(b.view()["mood"], "permission")

    def test_header_draws_the_battery(self):
        p = Painter()
        base = {"mood": "idle", "message": "zZz", "project": "", "counts": {}, "sessions": 0,
                "tools_today": 0, "limits": {}, "level": 1, "streak": 0}
        without = p.render(dict(base, battery=None))
        full = p.render(dict(base, battery={"pct": 100, "plugged": False}))
        empty = p.render(dict(base, battery={"pct": 0, "plugged": True}))
        header = (150, 0, 210, 15)
        self.assertNotEqual(without.crop(header).tobytes(), full.crop(header).tobytes())
        self.assertNotEqual(full.crop(header).tobytes(), empty.crop(header).tobytes())


class PowerOffTest(unittest.TestCase):
    def test_says_good_night_once_then_powers_off(self):
        shown = []

        class Display:
            def show(self, img, full):
                shown.append(img)

            def close(self):
                pass

        m = monitor(FakeI2C(pct=3))
        m.check()
        r = Renderer(Brain(battery=m), Display())
        with mock.patch.object(server.os, "system") as system:
            server.power_off(r, on_device=True)
            r.goodbye()                      # the service stop afterwards draws nothing new
        system.assert_called_once_with("poweroff")
        self.assertEqual(len(shown), 1)
        self.assertEqual(r.farewell, "battery_off")

    def test_simulator_only_logs(self):
        r = Renderer(Brain(), None)
        with mock.patch.object(server.os, "system") as system:
            server.power_off(r, on_device=False)
        system.assert_not_called()


if __name__ == "__main__":
    unittest.main()
