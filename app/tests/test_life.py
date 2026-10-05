import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from unittest import mock

from claudegotchi import brain as brain_mod
from claudegotchi.brain import Brain
from claudegotchi.life import Life, level_for, xp_for_level


def at(day, hour=12):
    return datetime(2026, 10, day, hour).timestamp()


class LevelTest(unittest.TestCase):
    def test_curve(self):
        self.assertEqual([xp_for_level(n) for n in (1, 2, 3, 4)], [0, 50, 150, 300])
        self.assertEqual([level_for(x) for x in (0, 49, 50, 149, 150)], [1, 1, 2, 2, 3])

    def test_level_up_is_reported(self):
        life = Life()
        ups = [life.record("Stop", {}, at(5)) for _ in range(5)]
        self.assertEqual(ups, [False, False, False, False, True])
        self.assertEqual(life.summary(at(5))["level"], 2)

    def test_rate_limit_gives_no_xp_but_counts_nothing_else(self):
        life = Life()
        life.record("StopFailure", {"error_type": "rate_limit"}, at(5))
        self.assertEqual(life.summary(at(5))["xp"], 0)


class StreakTest(unittest.TestCase):
    def test_consecutive_days(self):
        life = Life()
        for day in (3, 4, 5):
            life.record("Stop", {}, at(day))
        self.assertEqual(life.summary(at(5))["streak"], 3)

    def test_gap_breaks_the_streak(self):
        life = Life()
        life.record("Stop", {}, at(1))
        life.record("Stop", {}, at(2))
        self.assertEqual(life.summary(at(5))["streak"], 0)       # not shown as alive any more
        life.record("Stop", {}, at(5))
        s = life.summary(at(5))
        self.assertEqual((s["streak"], s["best_streak"]), (1, 2))


class PersistTest(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "life.json")
            life = Life(path)
            life.record("Stop", {}, at(5))
            life.record("PreToolUse", {}, at(5))
            life.maybe_save(force=True)
            again = Life(path).summary(at(5))
            self.assertEqual((again["xp"], again["today"]["turns"], again["today"]["tools"]), (11, 1, 1))

    def test_unwritable_path_does_not_crash(self):
        life = Life("/proc/nope/life.json")
        life.record("Stop", {}, at(5))
        life.maybe_save(force=True)


class MoodTest(unittest.TestCase):
    def view_at(self, b, ts):
        with mock.patch.object(brain_mod.time, "time", return_value=ts):
            return b.view()

    def test_level_up_celebration(self):
        b = Brain()
        now = time.time()
        for i in range(5):
            b.handle_hook({"hook_event_name": "Stop", "session_id": "s", "ts": now + i})
        v = b.view()
        self.assertEqual((v["mood"], v["level"]), ("levelup", 2))
        self.assertIn("2", v["message"])

    def test_evening_summary_and_hungry(self):
        life = Life()
        life.record("Stop", {}, at(5, 10))
        life.level_up_at = 0
        b = Brain(life)
        self.assertEqual(self.view_at(b, at(5, 20))["mood"], "summary")
        self.assertEqual(self.view_at(b, at(5, 23, ))["mood"], "idle")
        self.assertEqual(self.view_at(b, at(8, 12))["mood"], "hungry")


if __name__ == "__main__":
    unittest.main()
