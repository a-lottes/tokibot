import unittest

from claudegotchi import crypto

h = bytes.fromhex


class Ed25519Test(unittest.TestCase):
    # RFC 8032, section 7.1, tests 1 and 2
    def test_rfc8032_vectors(self):
        cases = [
            ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
             "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
             "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
            ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
             "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
             "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
        ]
        for seed, pub, msg, sig in cases:
            self.assertEqual(crypto.public_key(h(seed)), h(pub))
            self.assertEqual(crypto.sign(h(seed), h(msg)), h(sig))
            self.assertTrue(crypto.verify(h(pub), h(msg), h(sig)))

    def test_tampering_is_detected(self):
        seed = crypto.new_seed()
        pub = crypto.public_key(seed)
        sig = crypto.sign(seed, b"hello")
        self.assertFalse(crypto.verify(pub, b"hellO", sig))
        self.assertFalse(crypto.verify(pub, b"hello", sig[:-1] + bytes([sig[-1] ^ 1])))
        self.assertFalse(crypto.verify(crypto.public_key(crypto.new_seed()), b"hello", sig))
        self.assertFalse(crypto.verify(pub, b"hello", b"short"))


class X25519Test(unittest.TestCase):
    def test_rfc7748_vector(self):
        self.assertEqual(
            crypto.x25519(h("a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4"),
                          h("e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c")),
            h("c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552"))

    def test_rfc7748_alice_public_key(self):
        alice = h("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
        self.assertEqual(crypto.x25519(alice, (9).to_bytes(32, "little")),
                         h("8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a"))

    def test_shared_key_from_ed25519_keys(self):
        a, b = crypto.new_seed(), crypto.new_seed()
        ka = crypto.shared_key(a, crypto.public_key(b), b"test")
        kb = crypto.shared_key(b, crypto.public_key(a), b"test")
        self.assertEqual(ka, kb)
        self.assertNotEqual(ka, crypto.shared_key(a, crypto.public_key(b), b"other"))


class SealTest(unittest.TestCase):
    def test_seal_and_open(self):
        key, nonce = bytes(32), bytes(12)
        sealed = crypto.seal(key, nonce, b"secret")
        self.assertEqual(len(sealed), 6 + crypto.TAG_LEN)
        self.assertEqual(crypto.open_sealed(key, nonce, sealed), b"secret")
        broken = bytes([sealed[0] ^ 1]) + sealed[1:]
        self.assertIsNone(crypto.open_sealed(key, nonce, broken))
        self.assertIsNone(crypto.open_sealed(key, bytes(11) + b"x", sealed))

    def test_bad_peer_key(self):
        with self.assertRaises(ValueError):
            crypto.shared_key(crypto.new_seed(), bytes(32), b"test")


if __name__ == "__main__":
    unittest.main()
