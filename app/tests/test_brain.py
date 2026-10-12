import tempfile
import time
import unittest

from tokibot.brain import Brain
from tokibot.life import Life
import os

from tokibot.config import _parse_simple_toml, load, shell

DEFAULT_TOML = os.path.join(os.path.dirname(__file__), "..", "..", "os", "board", "tokibot", "tokibot.toml")


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

    def test_header_shows_own_name(self):
        b = Brain()
        self.assertEqual(b.view()["name"], "tokibot")
        b.name = "tokibot-3f2a"
        self.assertEqual(b.view()["name"], "tokibot-3f2a")

        class FakeSocial:
            state = {"name": "Pixel42"}
        b.social = FakeSocial()
        self.assertEqual(b.display_name(), "Pixel42")


class StaleLimitsTest(unittest.TestCase):
    """Every session's status line reports the limits of its own last API call."""

    def limits(self, b, pct, reset):
        b.handle_limits({"rate_limits": {"five_hour": {"used_percentage": pct, "resets_at": reset}}})
        return b.view()["limits"]["five_hour"]["pct"]

    def test_idle_session_does_not_lower_the_window(self):
        b, reset = Brain(), time.time() + 3600
        self.assertEqual(self.limits(b, 100, reset), 100)
        self.assertEqual(self.limits(b, 17, reset + 1), 100)
        self.assertEqual(b.view()["state"], "limit")

    def test_older_window_is_ignored(self):
        b, reset = Brain(), time.time() + 3600
        self.limits(b, 40, reset)
        self.assertEqual(self.limits(b, 90, reset - 5 * 3600), 40)

    def test_new_window_starts_low(self):
        b, reset = Brain(), time.time() + 3600
        self.limits(b, 100, reset)
        self.assertEqual(self.limits(b, 3, reset + 5 * 3600), 3)

    def test_after_reset_anything_counts(self):
        b = Brain()
        self.limits(b, 100, time.time() + 3600)
        b.limits["five_hour"]["reset"] = time.time() - 1      # the window has run out
        self.assertNotIn("five_hour", b.view()["limits"])
        self.assertEqual(self.limits(b, 5, time.time() + 5 * 3600), 5)


class RebootTest(unittest.TestCase):
    """A reboot must not forget the rate limits or that a client is paired."""

    def reboot(self, brain, path):
        brain.life.maybe_save(force=True)
        b = Brain(Life(path))
        b.address = "tokibot-3f2a.local"
        return b

    def test_full_limit_survives_reboot(self):
        path = os.path.join(tempfile.mkdtemp(), "life.json")
        b = Brain(Life(path))
        reset = time.time() + 3600
        b.handle_limits({"rate_limits": {"five_hour": {"used_percentage": 100, "resets_at": reset}}})
        v = self.reboot(b, path).view()
        self.assertEqual(v["state"], "limit")
        self.assertEqual(v["limits"]["five_hour"]["pct"], 100)
        self.assertNotIn("pair", v["message"])

    def test_expired_window_is_dropped(self):
        path = os.path.join(tempfile.mkdtemp(), "life.json")
        b = Brain(Life(path))
        b.handle_limits({"rate_limits": {"five_hour": {"used_percentage": 100,
                                                       "resets_at": time.time() - 60}}})
        self.assertEqual(self.reboot(b, path).view()["limits"], {})

    def test_address_only_until_first_contact(self):
        path = os.path.join(tempfile.mkdtemp(), "life.json")
        b = self.reboot(Brain(Life(path)), path)
        self.assertIn("pair", b.view()["message"])
        b.handle_limits({"rate_limits": {}})
        self.assertNotIn("pair", self.reboot(b, path).view()["message"])


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


class FoodMoodTest(unittest.TestCase):
    def test_stuffed_while_working_with_a_full_stomach(self):
        b = Brain()
        hook(b, "UserPromptSubmit")
        self.assertEqual(b.view()["mood"], "working")
        b2 = Brain()
        hook(b2, "Stop", tokens={"output": 5_000_000})
        hook(b2, "UserPromptSubmit")
        v = b2.view()
        self.assertEqual(v["mood"], "stuffed")
        self.assertGreaterEqual(v["food"]["fullness"], 1.5)

    def test_peckish_when_idle_and_empty_during_the_day(self):
        from datetime import datetime
        from unittest import mock
        from tokibot import brain as brain_mod
        b = Brain()
        b.life.state["food_total"] = 1        # it has eaten before
        noon = datetime(2026, 10, 6, 12).timestamp()
        with mock.patch.object(brain_mod.time, "time", return_value=noon):
            self.assertEqual(b.view()["mood"], "peckish")
        night = datetime(2026, 10, 6, 23).timestamp()
        with mock.patch.object(brain_mod.time, "time", return_value=night):
            self.assertEqual(b.view()["mood"], "idle")

    def test_harness_is_shown(self):
        b = Brain()
        hook(b, "UserPromptSubmit", harness="codex", project="api")
        self.assertEqual(b.view()["harness"], "codex")
