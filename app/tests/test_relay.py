import importlib.util
import json
import os
import tempfile
import time
import unittest
import urllib.error
from unittest import mock

from tokibot.brain import Brain
from tokibot.relay import Relay, parse
from tokibot.server import make_dispatch
from fake_ntfy import FakeNtfy

CLIENT = os.path.join(os.path.dirname(__file__), "..", "..", "client", "tokibot_client.py")


def load_client():
    spec = importlib.util.spec_from_file_location("tokibot_client", CLIENT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def line(env, mid="x1"):
    return json.dumps({"id": mid, "event": "message", "message": json.dumps(env)})


def wait_for(cond, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


class ParseTest(unittest.TestCase):
    ENV = {"tokibot": 1, "path": "/hook", "token": "t", "data": {"hook_event_name": "Stop"}}

    def test_message(self):
        self.assertEqual(parse(line(self.ENV), "t"), ("x1", "/hook", {"hook_event_name": "Stop"}))

    def test_wrong_token_and_noise_are_skipped(self):
        self.assertIsNone(parse(line(self.ENV), "other"))
        self.assertIsNone(parse('{"event":"keepalive"}', "t"))
        self.assertIsNone(parse(line({"hello": 1}), ""))
        self.assertIsNone(parse(line(dict(self.ENV, path="/etc")), "t"))
        self.assertIsNone(parse("not json", ""))


class DispatchTest(unittest.TestCase):
    def test_duplicates_are_dropped(self):
        b = Brain()
        d = make_dispatch(b, set_clock=False)
        ev = {"hook_event_name": "PreToolUse", "session_id": "s", "tool_name": "Bash",
              "ts": time.time(), "id": "same"}
        d("/hook", dict(ev))
        d("/hook", dict(ev))
        self.assertEqual(b.view().get("tools_today"), 1)


class EndToEndTest(unittest.TestCase):
    def test_client_to_gotchi_through_relay(self):
        ntfy = FakeNtfy()
        topic = ntfy.url + "/tokibot-test"
        brain = Brain()
        relay = Relay(topic, "secret", make_dispatch(brain, set_clock=False))
        relay.start()
        try:
            time.sleep(0.3)                              # let the subscription open
            client = load_client()
            client.RELAY_STATE = os.path.join(tempfile.mkdtemp(), "relay.json")
            cfg = {"url": "none", "token": "secret", "relay": topic, "statusline_chain": ""}
            client.send(cfg, "/hook", {"hook_event_name": "UserPromptSubmit",
                                       "session_id": "cloud", "project": "web", "ts": time.time()})
            self.assertTrue(wait_for(lambda: brain.view()["mood"] == "working"))
            # a message with the wrong token never reaches the brain
            client.send(dict(cfg, token="nope"), "/hook",
                        {"hook_event_name": "SessionEnd", "session_id": "cloud", "ts": time.time()})
            client.send(cfg, "/hook", {"hook_event_name": "Stop", "session_id": "cloud",
                                       "project": "web", "ts": time.time()})
            self.assertTrue(wait_for(lambda: brain.view()["mood"] == "done"))
        finally:
            relay.stop_evt.set()
            ntfy.close()


if __name__ == "__main__":
    unittest.main()


class RelayBudgetTest(unittest.TestCase):
    """ntfy.sh takes 250 messages a day; the client keeps the relay well below that."""
    def setUp(self):
        self.client = load_client()
        self.dir = tempfile.mkdtemp()
        self.state = os.path.join(self.dir, "relay.json")
        self.client.RELAY_STATE = self.state

    def take(self, name, now, **ev):
        return self.client.relay_take("/hook", dict(ev, hook_event_name=name), now=now)

    def test_chatter_now_and_then_moods_always(self):
        c, t = self.client, 1_000_000
        self.assertTrue(self.take("PreToolUse", t))
        self.assertFalse(self.take("PostToolUse", t + 10))            # too soon
        self.assertFalse(c.relay_take("/limits", {}, now=t + 20))
        self.assertTrue(self.take("Stop", t + 30))
        self.assertTrue(self.take("PostToolUse", t + 40, signals=["commit"]))
        self.assertTrue(self.take("PostToolUse", t + 30 + c.RELAY_CHATTER_EVERY))

    def test_budget_runs_out_and_refills(self):
        c, t = self.client, 1_000_000
        for i in range(c.RELAY_BUDGET):
            self.assertTrue(self.take("UserPromptSubmit", t))
        self.assertFalse(self.take("Stop", t))
        self.assertTrue(self.take("Stop", t + c.RELAY_REFILL))
        # two days of a mood change every minute never empty ntfy.sh's bucket
        # (250 messages, refilling one every 345.6 s), even when it starts out half used
        ntfy, at = 125.0, t
        for s in range(t + c.RELAY_REFILL, t + 2 * 86400, 60):
            ntfy = min(250, ntfy + (s - at) / 345.6)
            at = s
            if self.take("Notification", s):
                ntfy -= 1
            self.assertGreaterEqual(ntfy, 0)

    def test_chatter_leaves_a_reserve(self):
        c, t = self.client, 1_000_000
        for i in range(c.RELAY_BUDGET - c.RELAY_RESERVE):
            self.take("UserPromptSubmit", t)
        self.assertFalse(self.take("PreToolUse", t))
        self.assertTrue(self.take("Stop", t))

    def test_food_of_held_back_messages_rides_along(self):
        t = 1_000_000
        food = {"input": 10, "output": 5, "cache_write": 0, "cache_read": 100}
        self.take("PreToolUse", t)
        self.assertFalse(self.take("SubagentStop", t + 1, tokens=food))
        stop = {"hook_event_name": "Stop", "tokens": food}
        self.assertTrue(self.client.relay_take("/hook", stop, now=t + 2))
        self.assertEqual(stop["tokens"], {"input": 20, "output": 10, "cache_write": 0, "cache_read": 200})
        stop2 = {"hook_event_name": "Stop"}
        self.client.relay_take("/hook", stop2, now=t + 3)
        self.assertNotIn("tokens", stop2)                            # handed over once only

    def test_429_empties_the_bucket_and_keeps_the_food(self):
        c, t = self.client, 1_000_000
        food = {"input": 1, "output": 2, "cache_write": 3, "cache_read": 4}
        err = urllib.error.HTTPError("https://ntfy.sh/x", 429, "Too Many Requests", {}, None)
        c.relay_failed({"tokens": food}, err)
        st = json.load(open(self.state))
        self.assertEqual((st["food"], st["left"]), (food, 0))

    def test_direct_first_relay_only_when_the_gotchi_does_not_answer(self):
        ntfy = FakeNtfy()
        try:
            cfg = {"url": "http://127.0.0.1:9", "token": "", "relay": ntfy.url + "/t",
                   "statusline_chain": ""}
            with mock.patch.object(self.client, "post", return_value="direct") as post:
                self.assertEqual(self.client.send(cfg, "/hook", {"hook_event_name": "Stop"}), "direct")
                post.side_effect = OSError("no route")
                self.assertEqual(self.client.send(cfg, "/hook", {"hook_event_name": "Stop"}), ntfy.url + "/t")
            self.assertEqual(len(ntfy.messages), 1)
        finally:
            ntfy.close()


class LegacyEnvelopeTest(unittest.TestCase):
    def test_envelope_from_before_the_rename(self):
        from tokibot.relay import parse
        msg = {"event": "message", "id": "x", "message": json.dumps(
            {"claudegotchi": 1, "path": "/hook", "token": "", "data": {"a": 1}})}
        self.assertEqual(parse(json.dumps(msg), ""), ("x", "/hook", {"a": 1}))
