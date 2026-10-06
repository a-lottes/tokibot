import importlib.util
import io
import os
import unittest
from unittest import mock

from claudegotchi.brain import Brain
from claudegotchi.life import Life
from claudegotchi.mood import MESSAGES

CLIENT = os.path.join(os.path.dirname(__file__), "..", "..", "client", "claudegotchi_client.py")


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now

    def tick(self, seconds):
        self.now += seconds


class FeelingTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        patcher = mock.patch("time.time", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.brain = Brain(life=Life())

    def hook(self, name, sid="s1", **kw):
        self.clock.tick(1)
        self.brain.handle_hook({"hook_event_name": name, "session_id": sid,
                                "ts": self.clock.now, **kw})

    def mood(self):
        return self.brain.view()["mood"]

    def bash(self, ok, signals=(), sid="s1"):
        self.hook("PreToolUse", sid, tool_name="Bash")
        self.hook("PostToolUse" if ok else "PostToolUseFailure", sid, tool_name="Bash",
                  **({"signals": list(signals)} if signals else {}))

    def test_plain_work_stays_working(self):
        self.hook("UserPromptSubmit")
        self.bash(True)
        self.assertEqual(self.mood(), "working")

    def test_same_tool_failing_three_times_is_stuck(self):
        self.hook("UserPromptSubmit")
        for _ in range(3):
            self.bash(False)
        v = self.brain.view()
        self.assertEqual(v["mood"], "stuck")
        self.assertIn("Bash", v["message"])
        self.bash(True)
        self.assertNotEqual(self.mood(), "stuck")

    def test_tests_green_after_red_is_relieved(self):
        self.hook("UserPromptSubmit")
        self.bash(False, ["test"])
        self.bash(True, ["test"])
        self.assertEqual(self.mood(), "relieved")
        self.clock.tick(3 * 60)
        self.assertNotEqual(self.mood(), "relieved")

    def test_commit_is_proud_and_earns_xp(self):
        self.hook("UserPromptSubmit")
        xp = self.brain.life.summary()["xp"]
        self.bash(True, ["commit", "push"])
        v = self.brain.view()
        self.assertEqual(v["mood"], "proud")
        self.assertIn(v["message"], MESSAGES["proud_push"])
        life = self.brain.life.summary()
        self.assertEqual(life["xp"] - xp, 1 + 5 + 8)      # PreToolUse + commit + push
        self.assertEqual(life["today"]["commits"], 1)

    def test_pull_request_through_mcp_tool(self):
        self.hook("UserPromptSubmit")
        self.hook("PostToolUse", tool_name="mcp__github__create_pull_request")
        v = self.brain.view()
        self.assertEqual(v["mood"], "proud")
        self.assertIn(v["message"], MESSAGES["proud_pr"])

    def test_interrupt_is_oops(self):
        self.hook("UserPromptSubmit")
        self.hook("PostToolUseFailure", tool_name="Bash", interrupt=True)
        self.assertEqual(self.mood(), "oops")

    def test_many_failures_feel_bad_then_fade(self):
        self.hook("UserPromptSubmit")
        for tool in ("Bash", "Edit", "Read", "Bash", "Edit"):
            self.hook("PostToolUseFailure", tool_name=tool)
        self.clock.tick(31)
        self.assertEqual(self.mood(), "struggling")
        self.assertLess(self.brain.view()["feeling"]["valence"], -0.4)
        self.clock.tick(40 * 60)
        self.hook("PreToolUse", tool_name="Read")
        self.clock.tick(31)
        self.assertEqual(self.mood(), "working")

    def test_clean_turns_and_green_tests_bring_flow(self):
        for _ in range(2):
            self.hook("UserPromptSubmit")
            self.bash(True, ["test"])
            self.hook("Stop")
        self.clock.tick(3 * 60)                 # past the short "proud/relieved" moments
        self.hook("UserPromptSubmit")
        self.clock.tick(31)
        self.assertEqual(self.mood(), "flow")

    def test_tint_does_not_flicker(self):
        self.hook("UserPromptSubmit")
        self.assertEqual(self.mood(), "working")
        for tool in ("Bash", "Edit", "Read", "Bash", "Edit"):
            self.hook("PostToolUseFailure", tool_name=tool)
        self.assertEqual(self.mood(), "working")  # held: the last change was just now
        self.clock.tick(31)
        self.assertEqual(self.mood(), "struggling")

    def test_juggling_sessions(self):
        for sid in ("a", "b", "c"):
            self.hook("UserPromptSubmit", sid=sid)
        v = self.brain.view()
        self.assertEqual(v["mood"], "juggling")
        self.assertIn("3", v["message"])

    def test_permission_is_never_tinted(self):
        self.hook("UserPromptSubmit")
        for _ in range(3):
            self.bash(False)
        self.hook("PermissionRequest", tool_name="Bash")
        self.assertEqual(self.mood(), "permission")

    def test_full_context_shows_wrench(self):
        self.hook("UserPromptSubmit")
        self.brain.handle_limits({"session_id": "s1", "context_pct": 91})
        self.assertEqual(self.brain.view()["props"], ["wrench"])
        self.hook("Stop")
        self.clock.tick(3 * 60)
        self.assertEqual(self.brain.view()["props"], [])


class ClientSignalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("claudegotchi_client", CLIENT)
        cls.client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.client)

    def test_classify(self):
        c = self.client.classify
        self.assertEqual(c("cd app && python3 -m unittest discover -s tests"), ["test"])
        self.assertEqual(c("npm run test -- --watch=false"), ["test"])
        self.assertEqual(c("git add -A && git commit -m 'x' && git push -u origin main"), ["push", "commit"])
        self.assertEqual(c("gh pr create --fill"), ["pr"])
        self.assertEqual(c("git status && ls"), [])
        self.assertEqual(c("cat pytest.ini"), [])

    def sent(self, data):
        out = []
        with mock.patch.object(self.client, "post_detached", lambda cfg, path, ev, prepare=None: out.append(ev)), \
                mock.patch("sys.stdin", io.StringIO(__import__("json").dumps(data))):
            self.client.cmd_hook({})
        return out[0]

    def test_hook_sends_categories_not_commands(self):
        ev = self.sent({"hook_event_name": "PostToolUseFailure", "session_id": "s", "cwd": "/x/app",
                        "tool_name": "Bash", "tool_input": {"command": "pytest -q tests/secret_test.py"},
                        "error": "Exit code 1\nsecret output", "is_interrupt": False})
        self.assertEqual(ev["signals"], ["test"])
        self.assertNotIn("error", ev)
        self.assertNotIn("secret", str(ev))
        self.assertNotIn("interrupt", ev)

    def test_stop_failure_error_becomes_error_type(self):
        ev = self.sent({"hook_event_name": "StopFailure", "session_id": "s", "error": "rate_limit"})
        self.assertEqual(ev["error_type"], "rate_limit")

    def test_interrupt_and_compact_trigger(self):
        ev = self.sent({"hook_event_name": "PostToolUseFailure", "session_id": "s",
                        "tool_name": "Read", "is_interrupt": True})
        self.assertTrue(ev["interrupt"])
        ev = self.sent({"hook_event_name": "PreCompact", "session_id": "s", "trigger": "auto"})
        self.assertEqual(ev["trigger"], "auto")


if __name__ == "__main__":
    unittest.main()
