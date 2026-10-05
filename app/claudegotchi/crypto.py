"""Small, dependency-free crypto for the social features.

Pure Python, so it runs the same on the device and in the simulator without
installing anything:

  * Ed25519 signatures (RFC 8032): the gotchi's identity
  * X25519 key agreement (RFC 7748), with keys derived from the Ed25519 ones
  * ChaCha20 (RFC 8439) + HMAC-SHA256, encrypt-then-MAC
  * PBKDF2 for passphrase-protected backups

Speed is fine for what the gotchi does (a few signatures a minute). This is not
constant-time code; the threat model is a game among friends, not a hardware lab.
"""
import hashlib
import hmac
import os
import struct

# --- Ed25519 -------------------------------------------------------------------

P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
SQRT_M1 = pow(2, (P - 1) // 4, P)


def _inv(x):
    return pow(x, P - 2, P)


def _add(a, b):
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    A = (y1 - x1) * (y2 - x2) % P
    B = (y1 + x1) * (y2 + x2) % P
    C = 2 * t1 * t2 * D % P
    Dd = 2 * z1 * z2 % P
    E, F, G, H = B - A, Dd - C, Dd + C, B + A
    return (E * F % P, G * H % P, F * G % P, E * H % P)


def _mul(s, pt):
    q = (0, 1, 1, 0)
    while s:
        if s & 1:
            q = _add(q, pt)
        pt = _add(pt, pt)
        s >>= 1
    return q


def _recover_x(y, sign):
    if y >= P:
        return None
    x2 = (y * y - 1) * _inv(D * y * y + 1) % P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P:
        x = x * SQRT_M1 % P
    if (x * x - x2) % P:
        return None
    if (x & 1) != sign:
        x = P - x
    return x


_GY = 4 * _inv(5) % P
_GX = _recover_x(_GY, 0)
G = (_GX, _GY, 1, _GX * _GY % P)


def _encode(pt):
    x, y, z, _ = pt
    zi = _inv(z)
    x, y = x * zi % P, y * zi % P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _decode(b):
    if len(b) != 32:
        return None
    y = int.from_bytes(b, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % P)


def _equal(a, b):
    x1, y1, z1, _ = a
    x2, y2, z2, _ = b
    return (x1 * z2 - x2 * z1) % P == 0 and (y1 * z2 - y2 * z1) % P == 0


def _sha512_int(*parts):
    return int.from_bytes(hashlib.sha512(b"".join(parts)).digest(), "little")


def _expand(seed):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed):
    """32-byte Ed25519 public key for a 32-byte secret seed."""
    a, _ = _expand(seed)
    return _encode(_mul(a, G))


def sign(seed, msg):
    a, prefix = _expand(seed)
    pub = _encode(_mul(a, G))
    r = _sha512_int(prefix, msg) % L
    R = _encode(_mul(r, G))
    k = _sha512_int(R, pub, msg) % L
    s = (r + k * a) % L
    return R + s.to_bytes(32, "little")


def verify(pub, msg, sig):
    if len(sig) != 64:
        return False
    A = _decode(pub)
    R = _decode(sig[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= L:
        return False
    k = _sha512_int(sig[:32], pub, msg) % L
    return _equal(_mul(s, G), _add(R, _mul(k, A)))


def new_seed():
    return os.urandom(32)


# --- X25519 --------------------------------------------------------------------

def x25519(scalar, u_bytes):
    k = int.from_bytes(scalar, "little")
    k &= (1 << 254) - 8
    k |= 1 << 254
    x1 = int.from_bytes(u_bytes, "little") & ((1 << 255) - 1)
    x2, z2, x3, z3, swap = 1, 0, x1, 1, 0
    for t in reversed(range(255)):
        bit = (k >> t) & 1
        swap ^= bit
        if swap:
            x2, x3, z2, z3 = x3, x2, z3, z2
        swap = bit
        A, B = (x2 + z2) % P, (x2 - z2) % P
        AA, BB = A * A % P, B * B % P
        E = (AA - BB) % P
        C, Dd = (x3 + z3) % P, (x3 - z3) % P
        DA, CB = Dd * A % P, C * B % P
        x3 = (DA + CB) ** 2 % P
        z3 = x1 * (DA - CB) ** 2 % P
        x2 = AA * BB % P
        z2 = E * (AA + 121665 * E) % P
    if swap:
        x2, z2 = x3, z3
    return (x2 * pow(z2, P - 2, P) % P).to_bytes(32, "little")


def x25519_private(seed):
    """The X25519 secret that belongs to an Ed25519 seed."""
    return hashlib.sha512(seed).digest()[:32]


def x25519_public(ed_pub):
    """Map an Ed25519 public key to its X25519 public key (u = (1+y)/(1-y))."""
    y = int.from_bytes(ed_pub, "little") & ((1 << 255) - 1)
    return ((1 + y) * _inv((1 - y) % P) % P).to_bytes(32, "little")


def shared_key(seed, peer_ed_pub, label):
    """A 32-byte key both sides can compute from their own seed and the other's
    public key."""
    secret = x25519(x25519_private(seed), x25519_public(peer_ed_pub))
    if secret == bytes(32):
        raise ValueError("bad peer key")
    return hashlib.sha256(b"claudegotchi|" + label + b"|" + secret).digest()


# --- ChaCha20 + HMAC -----------------------------------------------------------

def _rotl(v, c):
    return ((v << c) & 0xffffffff) | (v >> (32 - c))


def _block(key, counter, nonce):
    s = [0x61707865, 0x3320646e, 0x79622d32, 0x6b206574]
    s += list(struct.unpack("<8I", key)) + [counter] + list(struct.unpack("<3I", nonce))
    x = s[:]

    def qr(a, b, c, d):
        x[a] = (x[a] + x[b]) & 0xffffffff
        x[d] = _rotl(x[d] ^ x[a], 16)
        x[c] = (x[c] + x[d]) & 0xffffffff
        x[b] = _rotl(x[b] ^ x[c], 12)
        x[a] = (x[a] + x[b]) & 0xffffffff
        x[d] = _rotl(x[d] ^ x[a], 8)
        x[c] = (x[c] + x[d]) & 0xffffffff
        x[b] = _rotl(x[b] ^ x[c], 7)

    for _ in range(10):
        qr(0, 4, 8, 12); qr(1, 5, 9, 13); qr(2, 6, 10, 14); qr(3, 7, 11, 15)
        qr(0, 5, 10, 15); qr(1, 6, 11, 12); qr(2, 7, 8, 13); qr(3, 4, 9, 14)
    return struct.pack("<16I", *((x[i] + s[i]) & 0xffffffff for i in range(16)))


def chacha20(key, nonce, data, counter=1):
    out = bytearray()
    for i in range(0, len(data), 64):
        ks = _block(key, counter + i // 64, nonce)
        chunk = data[i:i + 64]
        out += bytes(a ^ b for a, b in zip(chunk, ks))
    return bytes(out)


def _subkeys(key):
    return (hashlib.sha256(key + b"|enc").digest(), hashlib.sha256(key + b"|mac").digest())


def seal(key, nonce, plaintext, tag_len=16):
    """Encrypt-then-MAC. nonce: 12 bytes, never reused with the same key."""
    ek, mk = _subkeys(key)
    ct = chacha20(ek, nonce, plaintext)
    return ct + hmac.new(mk, nonce + ct, hashlib.sha256).digest()[:tag_len]


def open_sealed(key, nonce, sealed, tag_len=16):
    """Returns the plaintext, or None if the data was tampered with."""
    if len(sealed) < tag_len:
        return None
    ek, mk = _subkeys(key)
    ct, tag = sealed[:-tag_len], sealed[-tag_len:]
    if not hmac.compare_digest(tag, hmac.new(mk, nonce + ct, hashlib.sha256).digest()[:tag_len]):
        return None
    return chacha20(ek, nonce, ct)


def passphrase_key(passphrase, salt, iterations=200_000):
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations)
