import io
import os
import tarfile
import tempfile
import unittest

from claudegotchi import settings, update
from claudegotchi.config import DEFAULTS, _parse_simple_toml

TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "..", "os", "board", "claudegotchi",
                        "claudegotchi.toml")
APP = os.path.join(os.path.dirname(__file__), "..")


class TomlTest(unittest.TestCase):
    def test_update_keeps_comments_and_adds_keys(self):
        with open(TEMPLATE) as f:
            text = f.read()
        new = settings.update_toml(text, {("wifi", "ssid"): 'My "Phone"', ("usb", "enabled"): False,
                                          ("device", "rotate"): 180, ("relay", "extra"): "x",
                                          ("new", "key"): "y"})
        data = _parse_simple_toml(new)
        self.assertEqual(data["wifi"]["ssid"], 'My "Phone"')
        self.assertEqual((data["usb"]["enabled"], data["device"]["rotate"]), (False, 180))
        self.assertEqual((data["relay"]["extra"], data["new"]["key"]), ("x", "y"))
        self.assertIn("# Claudegotchi settings", new)
        self.assertEqual(data["wifi"]["country"], "DE")

    def test_form_keeps_empty_secrets(self):
        cfg = {k: dict(v) for k, v in DEFAULTS.items()}
        cfg["wifi"]["psk"] = "old"
        form = {"wifi.ssid": "Home", "wifi.psk": "", "wifi.country": "DE",
                "device.timezone": "Europe/Berlin", "device.rotate": "0", "usb.enabled": "on",
                "server.token": "", "relay.url": "", "relay.auth": ""}
        self.assertEqual(settings.changes_from_form(form, cfg), {("wifi", "ssid"): "Home"})
        form["wifi.psk.clear"] = "on"
        self.assertEqual(settings.changes_from_form(form, cfg)[("wifi", "psk")], "")

    def test_page_renders(self):
        html = settings.page(DEFAULTS, False, "hi")
        self.assertIn("Wi-Fi name", html)
        self.assertIn("No token is set", html)


def make_bundle(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class UpdateTest(unittest.TestCase):
    def test_install_real_bundle_and_reset(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "b.tar.gz")
            update.bundle(APP, out)
            app_dir = os.path.join(d, "app")
            with open(out, "rb") as f:
                version = update.install(f.read(), app_dir)
            self.assertEqual(version, update.claudegotchi.__version__)
            self.assertTrue(os.path.exists(os.path.join(app_dir, "claudegotchi", "fonts")))
            with open(out, "rb") as f:
                update.install(f.read(), app_dir)          # second time keeps the old one
            self.assertTrue(os.path.isdir(app_dir + ".old"))
            update.reset(app_dir)
            self.assertFalse(os.path.exists(app_dir))

    def test_bad_bundles_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            app_dir = os.path.join(d, "app")
            for data in (b"nope",
                         make_bundle({"../evil.py": b"x"}),
                         make_bundle({"other/x.py": b"x"}),
                         make_bundle({"claudegotchi/__init__.py": b"raise SystemExit(3)\n"})):
                with self.assertRaises(update.UpdateError):
                    update.install(data, app_dir)
            self.assertFalse(os.path.exists(app_dir))


if __name__ == "__main__":
    unittest.main()
