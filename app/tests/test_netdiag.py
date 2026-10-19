import os
import tempfile
import unittest

from tokibot import netdiag
from tokibot.painter import Painter


class NetDiagTest(unittest.TestCase):
    def test_report_runs_anywhere_and_hides_password(self):
        text = netdiag.report({"wifi": {"ssid": "casa", "psk": "secret-pass", "country": "DE"}})
        self.assertIn("Configured Wi-Fi: casa, country DE", text)
        self.assertIn("Password set: yes", text)
        self.assertNotIn("secret-pass", text)
        for title, _ in netdiag.COMMANDS:
            self.assertIn(f"== {title}", text)
        self.assertIn("== wpa_supplicant", text)


    def test_wifi_up_reads_operstate(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "operstate")
            self.assertFalse(netdiag.wifi_up(path))          # no wlan0
            for state, up in (("up\n", True), ("down\n", False), ("dormant\n", False)):
                with open(path, "w") as f:
                    f.write(state)
                self.assertEqual(netdiag.wifi_up(path), up)

    def test_header_draws_the_wifi_icon(self):
        p = Painter()
        base = {"mood": "idle", "message": "zZz", "project": "", "counts": {}, "sessions": 0,
                "tools_today": 0, "limits": {}, "level": 1, "streak": 0}
        header = (190, 0, 215, 15)
        off = p.render(dict(base, wifi=False)).crop(header).tobytes()
        on = p.render(dict(base, wifi=True)).crop(header).tobytes()
        self.assertNotEqual(off, on)


if __name__ == "__main__":
    unittest.main()
