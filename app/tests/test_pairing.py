"""Several gotchis on one network: each has its own name, and a client only talks
to the one it is paired with."""
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from claudegotchi import config
from claudegotchi.brain import Brain
from claudegotchi.server import Control, make_dispatch, make_handler
from test_relay import load_client


class Gotchi:
    """A gotchi server on a free local port, with its settings in a temp file."""
    def __init__(self, name, token=""):
        self.dir = tempfile.mkdtemp()
        self.cfg_path = os.path.join(self.dir, "claudegotchi.toml")
        with open(self.cfg_path, "w") as f:
            f.write(f'[server]\ntoken = "{token}"\n')
        cfg = config.load(self.cfg_path)
        self.brain = Brain()
        self.brain.address = f"{name}.local"
        control = Control(self.cfg_path, cfg, on_device=False)
        handler = make_handler(self.brain, None, token, make_dispatch(self.brain, False), control, name)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def post(url, body=b"{}", **headers):
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=3) as resp:
        return resp.status, resp.headers, resp.read()


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.g = Gotchi("claudegotchi-aaaa")

    def tearDown(self):
        self.g.close()

    def test_whoami_and_name_header(self):
        with urllib.request.urlopen(self.g.url + "/whoami", timeout=3) as resp:
            self.assertEqual(json.load(resp), {"gotchi": "claudegotchi-aaaa", "token": False})
            self.assertEqual(resp.headers["X-Claudegotchi-Gotchi"], "claudegotchi-aaaa")

    def test_event_for_another_gotchi_is_refused(self):
        ev = json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "s"}).encode()
        with self.assertRaises(urllib.error.HTTPError) as cm:
            post(self.g.url + "/hook", ev, **{"X-Claudegotchi-Gotchi": "claudegotchi-bbbb"})
        self.assertEqual(cm.exception.code, 409)
        self.assertEqual(self.g.brain.view()["state"], "idle")
        status, _, _ = post(self.g.url + "/hook", ev, **{"X-Claudegotchi-Gotchi": "Claudegotchi-AAAA"})
        self.assertEqual(status, 204)
        self.assertEqual(self.g.brain.view()["state"], "working")

    def test_screen_shows_the_address_until_someone_talks(self):
        self.assertIn("claudegotchi-aaaa.local", self.g.brain.view()["message"])
        post(self.g.url + "/limits", b'{"rate_limits": {}}')
        self.assertNotIn("claudegotchi-aaaa", self.g.brain.view()["message"])

    def test_pair_creates_and_saves_a_token_once(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:      # no header: a web page
            post(self.g.url + "/pair")
        self.assertEqual(cm.exception.code, 400)
        _, _, body = post(self.g.url + "/pair", **{"X-Claudegotchi-Pair": "1"})
        info = json.loads(body)
        self.assertEqual(info["gotchi"], "claudegotchi-aaaa")
        self.assertTrue(info["token"])
        self.assertEqual(config.load(self.g.cfg_path)["server"]["token"], info["token"])
        # From now on the token is needed, for events and for pairing again
        for path in ("/hook", "/pair"):
            with self.assertRaises(urllib.error.HTTPError) as cm:
                post(self.g.url + path, **{"X-Claudegotchi-Pair": "1"})
            self.assertEqual(cm.exception.code, 401)
        status, _, _ = post(self.g.url + "/hook", b'{"hook_event_name": "Stop"}',
                            **{"X-Claudegotchi-Token": info["token"]})
        self.assertEqual(status, 204)


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.mine, self.friends = Gotchi("claudegotchi-aaaa"), Gotchi("claudegotchi-bbbb")
        self.client = load_client()
        self.tmp = tempfile.mkdtemp()
        self.client.LEARNED = os.path.join(self.tmp, "gotchi")
        self.client.LAST_URL = os.path.join(self.tmp, "last_url")
        self.client.INSTALLED_CFG = os.path.join(self.tmp, "claudegotchi.json")

    def tearDown(self):
        self.mine.close()
        self.friends.close()

    def ev(self, name):
        return {"hook_event_name": name, "session_id": "s", "ts": time.time()}

    def test_learns_its_gotchi_over_usb_and_skips_a_friends(self):
        cfg = {"url": "auto", "token": "", "relay": "", "gotchi": ""}
        with mock.patch.object(self.client, "USB_URL", self.mine.url):
            self.client.send(cfg, "/hook", self.ev("UserPromptSubmit"))
        self.assertEqual(self.client.read_state(self.client.LEARNED), "claudegotchi-aaaa")
        # Unplugged; a friend's gotchi now answers where ours was. It refuses our events.
        cfg["gotchi"] = "claudegotchi-aaaa"
        with mock.patch.object(self.client, "USB_URL", self.friends.url):
            with self.assertRaises(urllib.error.HTTPError):
                self.client.post(dict(cfg, url=self.friends.url), "/hook", self.ev("Stop"))
        self.assertEqual(self.friends.brain.view()["state"], "idle")

    def test_pair_saves_name_and_token(self):
        cfg = {"url": "auto", "token": "", "relay": "", "gotchi": ""}
        self.assertEqual(self.client.cmd_pair(cfg, self.mine.url), 0)
        with open(self.client.INSTALLED_CFG) as f:
            saved = json.load(f)
        self.assertEqual(saved["gotchi"], "claudegotchi-aaaa")
        self.assertEqual(saved["token"], config.load(self.mine.cfg_path)["server"]["token"])
        cfg.update(saved)
        self.client.post(dict(cfg, url=self.mine.url), "/hook", self.ev("UserPromptSubmit"))
        self.assertEqual(self.mine.brain.view()["state"], "working")


if __name__ == "__main__":
    unittest.main()
