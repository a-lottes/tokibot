import importlib.util
import json
import os
import time
import unittest

from claudegotchi.brain import Brain
from claudegotchi.relay import Relay, parse
from claudegotchi.server import make_dispatch
from fake_ntfy import FakeNtfy

CLIENT = os.path.join(os.path.dirname(__file__), "..", "..", "client", "claudegotchi_client.py")


def load_client():
    spec = importlib.util.spec_from_file_location("claudegotchi_client", CLIENT)
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
    ENV = {"claudegotchi": 1, "path": "/hook", "token": "t", "data": {"hook_event_name": "Stop"}}

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
        topic = ntfy.url + "/claudegotchi-test"
        brain = Brain()
        relay = Relay(topic, "secret", make_dispatch(brain, set_clock=False))
        relay.start()
        try:
            time.sleep(0.3)                              # let the subscription open
            client = load_client()
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
