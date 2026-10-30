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

    def send(self, cfg, ev, gotchi_answers):
        with mock.patch.object(self.client, "post", return_value="direct") as post:
            if not gotchi_answers:
                post.side_effect = OSError("no route")
            return self.client.send(cfg, "/hook", ev)

    def test_relay_gets_its_share_also_when_the_gotchi_answers(self):
        ntfy = FakeNtfy()
        try:
            cfg = {"url": "http://127.0.0.1:9", "token": "", "relay": ntfy.url + "/t",
                   "statusline_chain": ""}
            self.assertEqual(self.send(cfg, {"hook_event_name": "Stop"}, True),
                             ntfy.url + "/t, direct")
            self.send(cfg, {"hook_event_name": "PreToolUse"}, True)
            self.assertEqual(self.send(cfg, {"hook_event_name": "PostToolUse"}, True), "direct")
            self.assertEqual(self.send(cfg, {"hook_event_name": "PostToolUse"}, False), "")
            self.assertEqual(len(ntfy.messages), 2)
        finally:
            ntfy.close()

    def test_food_that_reached_no_one_rides_along_once(self):
        ntfy = FakeNtfy()
        try:
            cfg = {"url": "http://127.0.0.1:9", "token": "", "relay": ntfy.url + "/t",
                   "statusline_chain": ""}
            food = {"input": 10, "output": 5, "cache_write": 0, "cache_read": 100}
            self.send(cfg, {"hook_event_name": "PreToolUse"}, False)          # uses the chatter slot
            self.send(cfg, {"hook_event_name": "SubagentStop", "tokens": food}, True)  # gotchi has it
            self.send(cfg, {"hook_event_name": "SubagentStop", "tokens": food}, False)  # lost: kept
            stop = {"hook_event_name": "Stop", "tokens": food}
            self.send(cfg, stop, False)
            self.assertEqual(stop["tokens"], {"input": 20, "output": 10, "cache_write": 0, "cache_read": 200})
            stop2 = {"hook_event_name": "Stop"}
            self.send(cfg, stop2, False)
            self.assertNotIn("tokens", stop2)                               # handed over once only
        finally:
            ntfy.close()

    def test_429_empties_the_bucket(self):
        c = self.client
        err = urllib.error.HTTPError("https://ntfy.sh/x", 429, "Too Many Requests", {}, None)
        cfg = {"url": "none", "token": "", "relay": "https://ntfy.sh/x", "statusline_chain": ""}
        with mock.patch.object(c, "publish", side_effect=err):
            with self.assertRaises(urllib.error.HTTPError):
                c.send(cfg, "/hook", {"hook_event_name": "Stop"})
        self.assertEqual(c._relay_state(self.state)["left"], 0)
        self.assertFalse(self.take("Stop", time.time() + 1))


class LegacyEnvelopeTest(unittest.TestCase):
    def test_envelope_from_before_the_rename(self):
        from tokibot.relay import parse
        msg = {"event": "message", "id": "x", "message": json.dumps(
            {"claudegotchi": 1, "path": "/hook", "token": "", "data": {"a": 1}})}
        self.assertEqual(parse(json.dumps(msg), ""), ("x", "/hook", {"a": 1}))
