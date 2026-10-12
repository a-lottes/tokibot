import hashlib
import importlib.util
import json
import lzma
import os
import tempfile
import unittest

from tokibot import imager
from tokibot.config import load

TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "..", "os", "board", "tokibot",
                        "tokibot.toml")

# As Raspberry Pi Imager 2 writes them for "init_format": "cloudinit"
USER_DATA = """#cloud-config
hostname: "raspberrypi"
manage_etc_hosts: true
packages:
- avahi-daemon

apt:
  preserve_sources_list: true
  conf: |
    Acquire {
      Check-Date "false";
    };

timezone: "Europe/Vienna"
keyboard:
  model: pc105
  layout: "de"
user:
  name: "andreas"
  shell: /bin/bash
  lock_passwd: false
  passwd: "$y$j9T$abc$def"
"""

NETWORK_CONFIG = """network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
      dhcp6: true
      optional: true
  wifis:
    wlan0:
      dhcp4: true
      regulatory-domain: "AT"
      access-points:
        "Caf\\u00e9 \\"Zur Post\\"":
          password: "pa\\\\ss: #1"
      optional: true
"""

# The older layout of Imager 1.8, with the renderer next to the interface
NETWORK_CONFIG_18 = """network:
  version: 2
  wifis:
    renderer: networkd
    wlan0:
      dhcp4: true
      optional: true
      access-points:
        "Home":
          password: "secret"
"""

OPEN_NETWORK = """network:
  version: 2
  wifis:
    wlan0:
      dhcp4: true
      access-points:
        "Guests":
          auth:
            key-management: none
      optional: true
"""

PRESEED = """config_version = "1.0"

[system]
hostname = "raspberrypi"

[user]
name = "pi"
password = "$y$j9T$abc"
password_encrypted = true
groups = ["sudo"]

[ssh]
enabled = true
password_authentication = false
authorized_keys = [
  "ssh-ed25519 AAAA test",
]

[wlan]
ssid = "Office"
password = "hunter22"
hidden = false
country = "de"

[locale]
keymap = "de"
timezone = "Europe/Berlin"
"""


class ParseTest(unittest.TestCase):
    def test_cloudinit_from_imager_2(self):
        self.assertEqual(imager.from_cloudinit(USER_DATA, NETWORK_CONFIG), {
            ("device", "timezone"): "Europe/Vienna",
            ("wifi", "ssid"): 'Café "Zur Post"',
            ("wifi", "psk"): "pa\\ss: #1",
            ("wifi", "country"): "AT",
        })

    def test_cloudinit_from_imager_18(self):
        self.assertEqual(imager.from_cloudinit("", NETWORK_CONFIG_18),
                         {("wifi", "ssid"): "Home", ("wifi", "psk"): "secret"})

    def test_open_network(self):
        self.assertEqual(imager.from_cloudinit("", OPEN_NETWORK),
                         {("wifi", "ssid"): "Guests", ("wifi", "psk"): ""})

    def test_preseed(self):
        self.assertEqual(imager.from_preseed(PRESEED), {
            ("wifi", "ssid"): "Office", ("wifi", "psk"): "hunter22", ("wifi", "country"): "DE",
            ("device", "timezone"): "Europe/Berlin",
        })
        self.assertEqual(imager.from_preseed('[wlan]\nssid_hex = "4869"\n'),
                         {("wifi", "ssid"): "Hi", ("wifi", "psk"): ""})

    def test_nothing_entered(self):
        self.assertEqual(imager.from_cloudinit("#cloud-config\n", ""), {})
        self.assertEqual(imager.from_preseed('config_version = "1.0"\n'), {})


class TakeOverTest(unittest.TestCase):
    def test_moves_settings_into_tokibot_toml_once(self):
        with tempfile.TemporaryDirectory() as boot:
            cfg_path = os.path.join(boot, "tokibot.toml")
            with open(TEMPLATE) as src, open(cfg_path, "w") as dst:
                dst.write(src.read())
            for name, text in (("user-data", USER_DATA), ("network-config", NETWORK_CONFIG),
                               ("meta-data", "instance-id: rpi-imager-1\n")):
                with open(os.path.join(boot, name), "w") as f:
                    f.write(text)

            self.assertEqual(imager.main(["imager", boot]), 0)
            cfg = load(cfg_path)
            self.assertEqual(cfg["wifi"]["ssid"], 'Café "Zur Post"')
            self.assertEqual(cfg["wifi"]["psk"], "pa\\ss: #1")
            self.assertEqual(cfg["wifi"]["country"], "AT")
            self.assertEqual(cfg["device"]["timezone"], "Europe/Vienna")
            self.assertEqual(sorted(os.listdir(boot)), ["tokibot.toml"])
            with open(cfg_path) as f:
                self.assertIn("# Tokibot settings", f.read())

            self.assertEqual(imager.take_over(boot), {})        # nothing left to take over

    def test_unreadable_files_are_dropped(self):
        with tempfile.TemporaryDirectory() as boot:
            cfg_path = os.path.join(boot, "tokibot.toml")
            with open(cfg_path, "w") as f:
                f.write('[wifi]\nssid = "Old"\n')
            with open(os.path.join(boot, "rpi-preseed.toml"), "w") as f:
                f.write("[wlan\nssid = ")
            self.assertEqual(imager.take_over(boot), {})
            self.assertEqual(load(cfg_path)["wifi"]["ssid"], "Old")
            self.assertFalse(os.path.exists(os.path.join(boot, "rpi-preseed.toml")))


def _imager_list():
    path = os.path.join(os.path.dirname(__file__), "..", "tools", "imager_list.py")
    spec = importlib.util.spec_from_file_location("imager_list", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RepositoryTest(unittest.TestCase):
    def test_lists_the_images_with_customisation(self):
        tool = _imager_list()
        with tempfile.TemporaryDirectory() as d:
            raw = b"boot and root" * 1000
            with lzma.open(os.path.join(d, "tokibot-zero2w.img.xz"), "wb") as f:
                f.write(raw)
            self.assertEqual(tool.main(["imager_list", d, "v0.6.0", "2026-10-12T10:00:00Z",
                                        "https://example.org/"]), 0)
            with open(os.path.join(d, "imager.json")) as f:
                repo = json.load(f)
            with open(os.path.join(d, "tokibot.rpi-imager-manifest")) as f:
                self.assertEqual(json.load(f), repo)
        (entry,) = repo["os_list"]
        self.assertEqual(entry["init_format"], "cloudinit")
        self.assertEqual(entry["url"], "https://example.org/downloads/tokibot-zero2w.img.xz")
        self.assertEqual((entry["extract_size"], entry["extract_sha256"]),
                         (len(raw), hashlib.sha256(raw).hexdigest()))
        self.assertEqual((entry["release_date"], entry["devices"]), ("2026-10-12", ["pi3-64bit"]))
        self.assertTrue(any("pi3-64bit" in dev["tags"] for dev in repo["imager"]["devices"]))

    def test_older_releases_without_customisation(self):
        tool = _imager_list()
        with tempfile.TemporaryDirectory() as d:
            with lzma.open(os.path.join(d, "tokibot-zerow.img.xz"), "wb") as f:
                f.write(b"x")
            (entry,) = tool.build(d, "v0.5.0", "2026-10-07")["os_list"]
        self.assertNotIn("init_format", entry)


if __name__ == "__main__":
    unittest.main()
