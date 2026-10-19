import os
import tempfile
import unittest

from tokibot.brain import wifi_connected
from tokibot.painter import Painter


class WifiTest(unittest.TestCase):
    def test_connected_reads_operstate(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "operstate")
            self.assertFalse(wifi_connected(path))           # no wlan0 at all
            for state, want in (("up\n", True), ("dormant\n", False), ("down\n", False)):
                with open(path, "w") as f:
                    f.write(state)
                self.assertEqual(wifi_connected(path), want)

    def test_header_draws_the_icon_next_to_the_clock(self):
        p = Painter()
        base = {"mood": "idle", "message": "zZz", "project": "", "counts": {}, "sessions": 0,
                "tools_today": 0, "limits": {}, "level": 1, "streak": 0}
        header = (180, 0, 220, 15)
        off = p.render(dict(base, wifi=False))
        on = p.render(dict(base, wifi=True))
        self.assertNotEqual(off.crop(header).tobytes(), on.crop(header).tobytes())


if __name__ == "__main__":
    unittest.main()
