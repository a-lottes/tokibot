import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from http.server import ThreadingHTTPServer

from tokibot import crypto
from tokibot.identity import Identity
from tokibot.life import Life
from tokibot.brain import Brain
from tokibot.scores import POST_EVERY, RETRY_AFTER, SIGN_PREFIX, Scores, make_card
from tokibot.server import make_dispatch, make_handler
from test_relay import load_client

T0 = 1_791_000_000.0           # some fixed point in time (2026)


def fed_life():
    life = Life()
    life.eat("Stop", {"tokens": {"input": 1000, "output": 500, "cache_read": 10000}}, now=T0)
    life.eat("Stop", {"harness": "cursor"}, now=T0)
    life.record("Stop", {}, now=T0)
    life.state["days"]["2020-01-01"] = {"food": 5, "food_est": 0, "xp": 1}     # long ago
    return life


class CardTest(unittest.TestCase):
    def setUp(self):
        self.me = Identity(crypto.new_seed(), os.urandom(16))

    def test_signed_and_complete(self):
        out = make_card(self.me, fed_life(), "Mochi", now=T0)
        self.assertTrue(crypto.verify(self.me.pub, SIGN_PREFIX + out["card"].encode(),
                                      bytes.fromhex(out["sig"])))
        card = json.loads(out["card"])
        today = datetime.fromtimestamp(T0).date().isoformat()
        self.assertEqual(card["pub"], self.me.pub.hex())
        self.assertEqual(card["name"], "Mochi")
        self.assertEqual(card["at"], int(T0))
        self.assertEqual(list(card["days"]), [today])        # old days stay at home
        day = card["days"][today]
        self.assertEqual(day["food"], 1000 + 500 + 1000 + day["est"])
        self.assertGreater(day["est"], 0)
        self.assertEqual(day["xp"], card["xp"])

    def test_a_changed_card_fails(self):
        out = make_card(self.me, fed_life(), "Mochi", now=T0)
        forged = out["card"].replace('"Mochi"', '"Mallory"')
        self.assertFalse(crypto.verify(self.me.pub, SIGN_PREFIX + forged.encode(),
                                       bytes.fromhex(out["sig"])))

    def test_removal(self):
        card = json.loads(make_card(self.me, fed_life(), now=T0, remove=True)["card"])
        self.assertEqual(card, {"v": 1, "pub": self.me.pub.hex(), "at": int(T0), "remove": True})


class PosterTest(unittest.TestCase):
    def setUp(self):
        self.me = Identity(crypto.new_seed(), os.urandom(16))
        self.sent, self.fail = [], False
        self.path = os.path.join(tempfile.mkdtemp(), "scores.json")

    def post(self, url, payload):
        if self.fail:
            raise OSError("offline")
        self.sent.append((url, json.loads(payload["card"])))

    def scores(self, enabled):
        return Scores({"enabled": enabled, "url": ""}, fed_life(), lambda: self.me,
                      lambda: "Mochi", self.path, post=self.post)

    def test_off_posts_nothing(self):
        self.assertEqual(self.scores(False).tick(T0), POST_EVERY)
        self.assertEqual(self.sent, [])

    def test_posts_hourly_and_retries(self):
        s = self.scores(True)
        self.fail = True
        self.assertEqual(s.tick(T0), RETRY_AFTER)
        self.fail = False
        s.tick(T0 + 1)
        s.tick(T0 + 100)                                     # not due yet
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][0], "https://tokibot.lottes.dev/api/scores")
        s.tick(T0 + 1 + POST_EVERY)
        self.assertEqual(len(self.sent), 2)

    def test_turning_off_removes_the_entry_once(self):
        self.scores(True).tick(T0)
        off = self.scores(False)                             # after the restart
        off.tick(T0 + 10)
        off.tick(T0 + 10 + POST_EVERY)
        self.assertEqual([c.get("remove", False) for _, c in self.sent], [False, True])


class ClientRelaysTest(unittest.TestCase):
    """A gotchi on the USB cable has no internet: the client posts its card."""
    def serve(self, enabled):
        me = Identity(crypto.new_seed(), os.urandom(16))
        brain = Brain(fed_life())
        scores = Scores({"enabled": enabled, "url": "https://example.test/api/scores"}, brain.life,
                        lambda: me, lambda: "Mochi")
        handler = make_handler(brain, None, "", make_dispatch(brain, False), name="tokibot-aaaa",
                               scores=scores)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return me, f"http://127.0.0.1:{server.server_port}"

    def client(self, url):
        client = load_client()
        client.SCORE_STATE = os.path.join(tempfile.mkdtemp(), "score_at")
        cfg = {"url": url, "token": "", "relay": "", "gotchi": ""}
        posted = []
        real = urllib.request.urlopen

        def urlopen(req, timeout=None):
            if req.full_url.startswith("https://"):
                posted.append((req.full_url, json.loads(req.data)))
                return real(url + "/whoami", timeout=timeout)       # any response will do
            return real(req, timeout=timeout)
        client.urllib.request.urlopen = urlopen
        self.addCleanup(setattr, client.urllib.request, "urlopen", real)
        return client, cfg, posted

    def test_card_is_forwarded_hourly(self):
        me, url = self.serve(True)
        client, cfg, posted = self.client(url)
        self.assertTrue(client.share_score(cfg, now=T0))
        self.assertFalse(client.share_score(cfg, now=T0 + 60))
        self.assertEqual(len(posted), 1)
        target, body = posted[0]
        self.assertEqual(target, "https://example.test/api/scores")
        self.assertEqual(set(body), {"card", "sig"})
        self.assertTrue(crypto.verify(me.pub, SIGN_PREFIX + body["card"].encode(),
                                      bytes.fromhex(body["sig"])))

    def test_nothing_when_off(self):
        _, url = self.serve(False)
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(url + "/score", timeout=3)
        self.assertEqual(e.exception.code, 404)
        client, cfg, posted = self.client(url)
        self.assertFalse(client.share_score(cfg, now=T0))
        self.assertEqual(posted, [])


if __name__ == "__main__":
    unittest.main()
