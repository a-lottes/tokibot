import time
import unittest

from claudegotchi.brain import Brain
import os

from claudegotchi.config import _parse_simple_toml, load, shell

DEFAULT_TOML = os.path.join(os.path.dirname(__file__), "..", "..", "os", "board", "claudegotchi", "claudegotchi.toml")


def hook(brain, name, **kw):
    brain.handle_hook({"hook_event_name": name, "session_id": kw.pop("sid", "s1"),
                       "ts": time.time(), **kw})


class BrainTest(unittest.TestCase):
    def test_idle_without_sessions(self):
        self.assertEqual(Brain().view()["mood"], "idle")

    def test_permission_beats_working(self):
        b = Brain()
        hook(b, "UserPromptSubmit", sid="a")
        hook(b, "PermissionRequest", sid="b", tool_name="Bash")
        v = b.view()
        self.assertEqual(v["state"], "permission")
        self.assertIn("Bash", v["message"])

    def test_tired_when_limit_is_close(self):
        b = Brain()
        b.handle_limits({"rate_limits": {"five_hour": {"used_percentage": 85, "resets_at": 0}}})
        hook(b, "UserPromptSubmit")
        self.assertEqual(b.view()["mood"], "tired")

    def test_session_end_forgets(self):
        b = Brain()
        hook(b, "UserPromptSubmit")
        hook(b, "SessionEnd")
        self.assertEqual(b.view()["sessions"], 0)


class ConfigTest(unittest.TestCase):
    def test_defaults_without_file(self):
        cfg = load("/does/not/exist.toml")
        self.assertEqual(cfg["server"]["port"], 8765)
        self.assertIn("USB_ENABLED=1", shell(cfg).splitlines())

    def test_fallback_parser_reads_default_file(self):
        with open(DEFAULT_TOML, encoding="utf-8") as f:
            data = _parse_simple_toml(f.read())
        self.assertEqual(data["server"]["port"], 8765)
        self.assertIs(data["usb"]["enabled"], True)
        self.assertEqual(data["wifi"]["ssid"], "")

    def test_fallback_parser_handles_quotes_and_comments(self):
        text = '[wifi]\nssid = "My \\"Wi-Fi\\"" # comment\npsk = \'a#b\'\n'
        data = _parse_simple_toml(text)
        self.assertEqual(data["wifi"], {"ssid": 'My "Wi-Fi"', "psk": "a#b"})


if __name__ == "__main__":
    unittest.main()
