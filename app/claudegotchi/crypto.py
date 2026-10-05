"""The crypto for the social features, all from libsodium (PyNaCl).

  * Ed25519 signatures: the gotchi's identity
  * X25519 key agreement, with keys derived from the Ed25519 ones
  * XChaCha20-Poly1305 for sealed data
  * Argon2id for passphrase-protected backups

This module only picks the primitives and names them for the rest of the app;
none of the cryptography itself is implemented here.
"""
import hashlib

import nacl.bindings as sodium
import nacl.exceptions
import nacl.pwhash
import nacl.signing
import nacl.utils

KDF = "argon2id"


# --- Ed25519 -------------------------------------------------------------------

def new_seed():
    return nacl.utils.random(32)


def public_key(seed):
    """32-byte Ed25519 public key for a 32-byte secret seed."""
    return bytes(nacl.signing.SigningKey(seed).verify_key)


def sign(seed, msg):
    return nacl.signing.SigningKey(seed).sign(msg).signature


def verify(pub, msg, sig):
    try:
        nacl.signing.VerifyKey(pub).verify(msg, sig)
        return True
    except (nacl.exceptions.BadSignatureError, nacl.exceptions.ValueError, ValueError, TypeError):
        return False


# --- X25519 --------------------------------------------------------------------

def x25519(scalar, u_bytes):
    return sodium.crypto_scalarmult(scalar, u_bytes)


def shared_key(seed, peer_ed_pub, label):
    """A 32-byte key both sides can compute from their own seed and the other's
    public key."""
    try:
        mine = sodium.crypto_sign_ed25519_sk_to_curve25519(seed + public_key(seed))
        theirs = sodium.crypto_sign_ed25519_pk_to_curve25519(peer_ed_pub)
        secret = sodium.crypto_scalarmult(mine, theirs)
    except (nacl.exceptions.CryptoError, nacl.exceptions.RuntimeError, ValueError, TypeError):
        raise ValueError("bad peer key")
    return hashlib.sha256(b"claudegotchi|" + label + b"|" + secret).digest()


# --- sealing -------------------------------------------------------------------

TAG_LEN = sodium.crypto_aead_xchacha20poly1305_ietf_ABYTES      # 16


def _nonce(nonce):
    return nonce.ljust(sodium.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES, b"\0")


def seal(key, nonce, plaintext):
    """Authenticated encryption. nonce: up to 24 bytes, never reused with the same key
    for different plaintexts."""
    return sodium.crypto_aead_xchacha20poly1305_ietf_encrypt(plaintext, None, _nonce(nonce), key)


def open_sealed(key, nonce, sealed):
    """Returns the plaintext, or None if the data was tampered with."""
    try:
        return sodium.crypto_aead_xchacha20poly1305_ietf_decrypt(sealed, None, _nonce(nonce), key)
    except (nacl.exceptions.CryptoError, ValueError, TypeError):
        return None


def passphrase_key(passphrase, salt):
    """32-byte key from a passphrase; salt: 16 bytes."""
    return nacl.pwhash.argon2id.kdf(32, passphrase.encode("utf-8"), salt,
                                    opslimit=nacl.pwhash.argon2id.OPSLIMIT_INTERACTIVE,
                                    memlimit=nacl.pwhash.argon2id.MEMLIMIT_INTERACTIVE)
