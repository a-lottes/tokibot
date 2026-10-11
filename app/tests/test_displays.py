"""The display drivers, with the SPI and GPIO layer replaced by a recorder."""
import itertools
import unittest
from unittest import mock

from PIL import Image, ImageDraw

from tokibot import displays, settings
from tokibot.config import DEFAULTS
from tokibot.displays import sim, waveshare_epd
from tokibot.displays.waveshare import epdconfig
from tokibot.renderer import Renderer


class FakeBus:
    def __init__(self):
        self.sent = 0
        busy = itertools.cycle((0, 1))      # every busy-wait loop ends, whichever level it waits on
        self.patches = [
            mock.patch.object(epdconfig, "module_init", lambda cleanup=False: 0),
            mock.patch.object(epdconfig, "module_exit", lambda cleanup=False: None),
            mock.patch.object(epdconfig, "digital_write", lambda pin, value: None),
            mock.patch.object(epdconfig, "digital_read", lambda pin: next(busy)),
            mock.patch.object(epdconfig, "delay_ms", lambda ms: None),
            mock.patch.object(epdconfig, "spi_writebyte", self.write),
            mock.patch.object(epdconfig, "spi_writebyte2", self.write),
        ]

    def write(self, data):
        self.sent += len(data)

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()


def frame():
    img = Image.new("1", (250, 122), 255)
    ImageDraw.Draw(img).rectangle((10, 10, 60, 40), fill=0)
    return img


class DisplayTest(unittest.TestCase):
    def test_every_driver_draws(self):
        for name, (_, cls) in displays.DISPLAYS.items():
            with self.subTest(name), FakeBus() as bus:
                d = displays.open_display(name, 180)
                self.assertIsInstance(d, getattr(waveshare_epd, cls))
                for full in (True, False, False, True):
                    before = bus.sent
                    d.show(frame(), full)
                    self.assertGreater(bus.sent - before, 0)
                d.close()

    def test_fit_centres_on_larger_panels(self):
        with FakeBus():
            d = displays.open_display("waveshare_2in7_v2")
        img = d.fit(frame())
        self.assertEqual(img.size, (264, 176))
        self.assertEqual(img.getpixel((7 + 10, 27 + 10)), 0)      # the black box moved by the margin
        self.assertEqual(img.getpixel((10, 10)), 255)

    def test_pwnagotchi_names(self):
        self.assertEqual(displays.resolve("waveshare_3"), "waveshare_2in13_v3")
        self.assertEqual(displays.resolve("WS_4"), "waveshare_2in13_v4")
        self.assertEqual(displays.resolve("waveshare27inchv2"), "waveshare_2in7_v2")
        self.assertIsNone(displays.resolve("inky"))

    def test_unknown_display_keeps_running(self):
        with self.assertLogs("tokibot", "ERROR"):
            d = displays.open_display("inky")
        self.assertIsInstance(d, sim.SimDisplay)

    def test_slow_panels_always_refresh_fully(self):
        class Slow(sim.SimDisplay):
            PARTIAL, MIN_INTERVAL = False, 60.0
        r = Renderer(mock.Mock(), Slow(""))
        self.assertEqual((r.partial, r.interval), (False, 60.0))
        r = Renderer(mock.Mock(), sim.SimDisplay(""))
        self.assertEqual((r.partial, r.interval), (True, Renderer.MIN_INTERVAL))


class SettingsTest(unittest.TestCase):
    def cfg(self, display):
        cfg = {k: dict(v) for k, v in DEFAULTS.items()}
        cfg["device"]["display"] = display
        return cfg

    def form(self, display):
        return {"device.display": display, "device.rotate": "180", "device.timezone": "Europe/Berlin",
                "wifi.country": "DE", "usb.enabled": "on", "social.enabled": "on",
                "leaderboard.enabled": "on"}

    def test_choose_display(self):
        cfg = self.cfg("waveshare_2in13_v4")
        self.assertEqual(settings.changes_from_form(self.form("waveshare_2in13_v3"), cfg),
                         {("device", "display"): "waveshare_2in13_v3"})
        self.assertEqual(settings.changes_from_form(self.form("nonsense"), cfg), {})

    def test_pwnagotchi_name_is_kept(self):
        cfg = self.cfg("waveshare_3")
        self.assertEqual(settings.changes_from_form(self.form("waveshare_2in13_v3"), cfg), {})
        self.assertIn('value="waveshare_2in13_v3" selected', settings.page(cfg, True))

    def test_unknown_name_is_shown(self):
        html = settings.page(self.cfg("inky"), True)
        self.assertIn("inky (unknown)", html)


if __name__ == "__main__":
    unittest.main()
