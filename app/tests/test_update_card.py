"""The card updater on the website (docs/update-card.py), run against a file as card."""
import hashlib
import importlib.util
import io
import lzma
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
SCRIPT = os.path.join(HERE, "..", "..", "docs", "update-card.py")
spec = importlib.util.spec_from_file_location("update_card", SCRIPT)
uc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uc)

sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import tui_critters  # noqa: E402


def disk_image(fill, data_start=8, data_count=4, sectors=16):
    img = bytearray(fill * (sectors * 512))
    mbr = bytearray(512)
    for i, (start, count) in enumerate([(1, 3), (4, 4), (data_start, data_count)]):
        e = 446 + 16 * i
        mbr[e + 4] = 0x83
        mbr[e + 8:e + 12] = start.to_bytes(4, "little")
        mbr[e + 12:e + 16] = count.to_bytes(4, "little")
    mbr[510:512] = b"\x55\xaa"
    img[:512] = mbr
    return img


class FakePlat:
    def __init__(self, card, boot):
        self.card, self.boot, self.ejected = card, boot, False

    def raw(self, disk):
        return self.card

    def unmount(self, disk):
        pass

    settle = unmount

    def mount_boot(self, disk):
        return self.boot

    def umount_boot(self, mnt, disk):
        pass

    def eject(self, disk):
        self.ejected = True


class UpdateCardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.card = os.path.join(d, "card")
        old = disk_image(b"o")
        old[8 * 512:12 * 512] = b"PROGRESS" * (4 * 512 // 8)
        with open(self.card, "wb") as f:
            f.write(old)
        self.new = disk_image(b"n")
        self.xz = os.path.join(d, "tokibot-zerow.img.xz")
        with open(self.xz, "wb") as f:
            f.write(lzma.compress(bytes(self.new)))
        self.boot = os.path.join(d, "boot")
        os.mkdir(self.boot)
        with open(os.path.join(self.boot, "config.txt"), "w") as f:
            f.write("kernel=zImage\n")
        with open(os.path.join(self.boot, "tokibot.toml"), "w") as f:
            f.write('[wifi]\nssid = "Casa"\n')
        self.screen = uc.Screen(io.StringIO())

    def tearDown(self):
        self.tmp.cleanup()

    def rel(self, sha=None):
        with open(self.xz, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        return {"tag": "v9.9.9", "url": "file://" + self.xz, "size": os.path.getsize(self.xz),
                "sha256": digest if sha is None else sha}

    def test_writes_the_image_and_keeps_progress_and_settings(self):
        plat = FakePlat(self.card, self.boot)
        model, toml, ssid = uc.read_boot(plat, {"name": "x"})
        self.assertEqual((model, ssid), ("zerow", "Casa"))
        with open(os.path.join(self.boot, "tokibot.toml"), "w") as f:
            f.write("overwritten by the new image")
        backup = os.path.join(self.tmp.name, "backup")
        self.assertTrue(uc.update(self.screen, plat, {"name": "x", "toml": toml}, self.rel(), backup))
        with open(self.card, "rb") as f:
            card = f.read()
        self.assertEqual(card[:8 * 512], bytes(self.new[:8 * 512]))           # new image
        self.assertEqual(card[8 * 512:12 * 512], b"PROGRESS" * 256)           # progress back
        with open(os.path.join(self.boot, "tokibot.toml"), "rb") as f:
            self.assertEqual(f.read(), toml)                                    # settings back
        self.assertTrue(os.path.exists(os.path.join(backup, "data.img")))
        self.assertTrue(os.path.exists(os.path.join(backup, "card-start.img.gz")))
        self.assertTrue(plat.ejected)

    def test_bad_checksum_writes_nothing(self):
        with open(self.card, "rb") as f:
            before = f.read()
        ok = uc.update(self.screen, FakePlat(self.card, self.boot), {"name": "x", "toml": None},
                       self.rel(sha="0" * 64), os.path.join(self.tmp.name, "b"))
        self.assertFalse(ok)
        with open(self.card, "rb") as f:
            self.assertEqual(f.read(), before)

    def test_other_layout_writes_nothing(self):
        with open(self.xz, "wb") as f:
            f.write(lzma.compress(bytes(disk_image(b"n", data_start=9))))
        with open(self.card, "rb") as f:
            before = f.read()
        ok = uc.update(self.screen, FakePlat(self.card, self.boot), {"name": "x", "toml": None},
                       self.rel(), os.path.join(self.tmp.name, "b"))
        self.assertFalse(ok)
        with open(self.card, "rb") as f:
            self.assertEqual(f.read(), before)

    def test_critters_are_current(self):
        with open(SCRIPT, encoding="utf-8") as f:
            self.assertIn(tui_critters.block(), f.read(), "run make tui-critters")


if __name__ == "__main__":
    unittest.main()
