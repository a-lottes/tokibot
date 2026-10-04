import time
import unittest

from claudegotchi.brain import Brain
from claudegotchi.config import load, shell


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


if __name__ == "__main__":
    unittest.main()
