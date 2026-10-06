import json
import os
import tempfile
import unittest

from tokibot import identity, social
from tokibot.identity import Identity
from tokibot.life import Life
from tokibot.radio import ad_payload, parse_reports
from tokibot.social import Social

T0 = 1_791_000_000.0           # some fixed point in time (2026)


class BusRadio:
    """Delivers packets between gotchis in a test, without threads or sockets."""
    def __init__(self, bus):
        self.bus, self.packets, self.on_packet = bus, [], None
        self.rotations = 0
        bus.append(self)

    def start(self, on_packet):
        self.on_packet = on_packet

    def set_packets(self, packets):
        self.packets = list(packets)

    def rotate_address(self):
        self.rotations += 1

    def stop(self):
        pass


def deliver(bus, now, rssi=-50):
    for sender in bus:
        for pkt in sender.packets:
            for receiver in bus:
                if receiver is not sender and receiver.on_packet:
                    receiver.on_packet("x", rssi, pkt, now)


class World:
    def __init__(self, n=2):
        self.tmp = tempfile.TemporaryDirectory()
        self.bus, self.gotchis = [], []
        for i in range(n):
            d = os.path.join(self.tmp.name, f"g{i}")
            os.makedirs(d)
            g = Social(Identity.load_or_create(d), Life(os.path.join(d, "life.json")),
                       os.path.join(d, "social.json"), BusRadio(self.bus))
            g.radio.start(g.on_packet)
            self.gotchis.append(g)
        self.now = T0

    def run(self, seconds, step=1.0, rssi=-50):
        end = self.now + seconds
        while self.now < end:
            for g in self.gotchis:
                g.tick(self.now)
            deliver(self.bus, self.now, rssi)
            self.now += step

    def close(self):
        self.tmp.cleanup()


class PacketTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.a = Identity.load_or_create(os.path.join(self.tmp.name))
        self.b = Identity(b"\x01" * 32, b"\x02" * 16)

    def tearDown(self):
        self.tmp.cleanup()

    def test_card_roundtrip_and_tampering(self):
        blob = social.encode_card(self.a, "Mochi ✨", 7, 2)
        card = social.decode_card(blob)
        self.assertEqual((card["name"], card["level"], card["accessory"]), ("Mochi ✨", 7, 2))
        self.assertEqual(card["pub"], self.a.pub)
        self.assertIsNone(social.decode_card(blob[:40] + b"X" + blob[41:]))

    def test_every_packet_fits_into_an_advertisement(self):
        card = social.encode_card(self.a, "x" * 40, 99, 1)
        offer = social.encode_offer(self.a, self.b.pub, 20000)
        for pkt in social.fragments(social.T_CARD, b"abcd", 0, card) + \
                social.fragments(social.T_OFFER, b"abcd", 1, offer):
            self.assertLessEqual(len(pkt), 27)
            self.assertEqual(len(ad_payload(pkt)), 32)

    def test_offer_only_opens_for_its_target(self):
        offer = social.encode_offer(self.a, self.b.pub, 20000)
        day, sig, secret = social.decode_offer(self.b, self.a.pub, offer)
        self.assertEqual((day, secret), (20000, self.a.beacon_secret))
        stranger = Identity(b"\x03" * 32, b"\x04" * 16)
        self.assertIsNone(social.decode_offer(stranger, self.a.pub, offer))

    def test_hci_report_parsing(self):
        pkt = b"CG\x11" + bytes(14)
        ad = ad_payload(pkt)[1:]
        n = 31
        evt = bytes([0x3E, 0, 0x02, 1, 0x03, 0x01]) + bytes(range(6)) + bytes([n]) + ad + bytes([0xC4])
        (addr, rssi, payload), = parse_reports(evt)
        self.assertEqual((addr, rssi, payload), ("05:04:03:02:01:00", -60, pkt))


class SocialTest(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.a, self.b = self.w.gotchis

    def tearDown(self):
        self.w.close()

    def test_strangers_only_see_an_anonymous_beacon(self):
        self.w.run(5)
        packets = b"".join(self.a.radio.packets)
        self.assertNotIn(self.a.me.pub[:8], packets)
        self.assertEqual({p[2] for p in self.a.radio.packets}, {social.T_BEACON})
        self.assertEqual(len(self.b.peers), 1)
        self.assertIsNone(next(iter(self.b.peers.values()))["card"])

    def test_anonymous_encounter_after_thirty_seconds(self):
        self.w.run(20)
        self.assertEqual(self.b.life.summary(self.w.now)["xp"], 0)
        self.w.run(15)
        self.assertEqual(self.b.life.summary(self.w.now)["xp"], 2)
        self.assertIn("first_meet", self.b.life.badges())
        self.assertEqual(self.b.view(self.w.now)["event"]["kind"], "encounter_anon")

    def test_far_away_is_no_encounter(self):
        self.w.run(60, rssi=-95)
        self.assertEqual(self.b.life.summary(self.w.now)["xp"], 0)

    def test_open_gotchis_exchange_cards(self):
        self.a.set_profile(name="Mochi", open_=True)
        self.b.set_profile(name="Tofu", open_=True)
        self.w.run(40)
        self.assertEqual(self.a.page_data(self.w.now)["nearby"][0]["name"], "Tofu")
        self.assertEqual(self.b.life.summary(self.w.now)["xp"], 20)     # a new gotchi
        self.assertEqual(self.b.view(self.w.now)["event"]["name"], "Mochi")

    def befriend(self):
        self.a.set_profile(name="Mochi", open_=True)
        self.b.set_profile(name="Tofu", open_=True)
        self.w.run(10)
        pub_a, pub_b = self.a.me.pub.hex(), self.b.me.pub.hex()
        self.assertEqual(self.a.befriend(pub_b, self.w.now), "asked")
        self.w.run(10)
        self.assertEqual(self.b.view(self.w.now)["invite"], "Mochi")
        self.assertEqual(self.b.befriend(pub_a, self.w.now), "friends")
        self.w.run(10)
        return pub_a, pub_b

    def test_friendship_needs_both_and_leaves_a_valid_proof(self):
        pub_a, pub_b = self.befriend()
        self.assertIn(pub_b, self.a.state["friends"])
        self.assertIn(pub_a, self.b.state["friends"])
        proof = self.a.state["friends"][pub_b]["proof"]
        self.assertTrue(social.verify_proof(proof))
        self.assertEqual(proof, self.b.state["friends"][pub_a]["proof"])
        forged = dict(proof, day=proof["day"] + 1)
        self.assertFalse(social.verify_proof(forged))
        self.assertIn("first_friend", self.a.life.badges())
        self.assertEqual(self.a.view(self.w.now)["event"]["kind"], "newfriend")

    def test_no_friendship_without_consent(self):
        self.a.set_profile(open_=True)
        self.b.set_profile(open_=True)
        self.w.run(10)
        self.a.befriend(self.b.me.pub.hex(), self.w.now)
        self.w.run(60)
        self.assertEqual(self.a.state["friends"], {})
        self.assertEqual(self.b.state["friends"], {})
        self.b.decline(self.a.me.pub.hex(), self.w.now)
        self.assertIsNone(self.b.view(self.w.now)["invite"])

    def test_friends_recognise_each_other_after_the_id_changes(self):
        pub_a, pub_b = self.befriend()
        self.a.set_profile(open_=False)
        self.b.set_profile(open_=False)
        self.w.run(social.OFFER_LINGER + 10)
        self.w.run(social.EPOCH, step=30)          # new ephemeral ids, no cards any more
        self.assertGreaterEqual(self.a.radio.rotations, 1)
        self.assertEqual({p[2] for p in self.a.radio.packets}, {social.T_BEACON})
        self.w.run(5)
        friends = self.b.view(self.w.now)["friends_nearby"]
        self.assertEqual(friends, ["Mochi"])

    def test_friends_survive_a_restart(self):
        pub_a, pub_b = self.befriend()
        self.a.save(force=True)
        with open(self.a.path) as f:
            self.assertIn(pub_b, json.load(f)["friends"])

    def test_unfriend(self):
        pub_a, pub_b = self.befriend()
        self.assertTrue(self.a.unfriend(pub_b))
        self.assertNotIn(pub_b, self.a.state["friends"])
        self.assertIn(pub_b, self.a.state["known"])

    def test_cowork_bonus(self):
        self.befriend()
        self.a.my_mood = self.b.my_mood = "working"
        self.w.run(5)
        self.assertTrue(self.a.cowork)
        self.assertIn("coworking", self.a.life.badges())
        xp = self.a.life.summary(self.w.now)["xp"]
        for _ in range(10):
            self.a.life.record("Stop", {}, self.w.now)
        self.assertEqual(self.a.life.summary(self.w.now)["xp"] - xp, 110)

    def test_accessories_unlock(self):
        self.assertEqual(social.accessories_unlocked(1, {}), ["none"])
        self.assertIn("bow", social.accessories_unlocked(1, {"first_friend": 1}))
        self.assertIn("cap", social.accessories_unlocked(3, {}))


class BackupTest(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            me = Identity.load_or_create(d1)
            with open(os.path.join(d1, "social.json"), "w") as f:
                f.write('{"name": "Mochi"}')
            blob = identity.make_backup(d1, "correct horse")
            with self.assertRaises(identity.BackupError):
                identity.restore_backup(d2, blob, "wrong horse")
            self.assertEqual(identity.restore_backup(d2, blob, "correct horse"), me.id)
            self.assertEqual(Identity.load_or_create(d2).pub, me.pub)
            with open(os.path.join(d2, "social.json")) as f:
                self.assertIn("Mochi", f.read())

    def test_short_passphrase(self):
        with tempfile.TemporaryDirectory() as d:
            Identity.load_or_create(d)
            with self.assertRaises(identity.BackupError):
                identity.make_backup(d, "short")



class PageTest(unittest.TestCase):
    def test_social_page_renders(self):
        from tokibot import socialpage
        w = World()
        try:
            a, b = w.gotchis
            a.set_profile(name="Mo<chi", open_=True)
            b.set_profile(name="Tofu", open_=True)
            w.run(40)
            html = socialpage.page(b.page_data(w.now), True, "Saved.", now=w.now)
            self.assertIn("Mo&lt;chi", html)
            self.assertIn("Befriend", html)
            self.assertIn("Hello world", html)
            self.assertNotIn("Mo<chi", html)
        finally:
            w.close()


if __name__ == "__main__":
    unittest.main()
