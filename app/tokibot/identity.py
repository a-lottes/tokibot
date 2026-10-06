"""The gotchi's identity: an Ed25519 key pair that *is* the profile.

Created on first start and kept in identity.json on the data partition. The secret
seed never leaves the device, except inside a passphrase-encrypted backup the
owner downloads from the social page.
"""
import base64
import hashlib
import json
import logging
import os
import time

from . import crypto

log = logging.getLogger("tokibot.identity")

NAME_MAX = 12            # bytes of UTF-8, so it fits into a Bluetooth packet
BACKUP_FILES = ("identity.json", "social.json", "life.json")

_FIRST = ["Pixel", "Byte", "Mochi", "Nibble", "Tofu", "Sprout", "Pebble", "Bloop", "Ziggy",
          "Noodle", "Biscuit", "Comet", "Dot", "Fizz", "Gizmo", "Pip"]


def gotchi_id(pub):
    h = hashlib.sha256(pub).hexdigest()
    return f"cg-{h[:4]}-{h[4:8]}"


def default_name(pub):
    h = hashlib.sha256(b"name|" + pub).digest()
    return f"{_FIRST[h[0] % len(_FIRST)]}{h[1] % 100:02d}"


def clean_name(name):
    name = " ".join(str(name).split())
    raw = name.encode("utf-8")[:NAME_MAX]
    return raw.decode("utf-8", "ignore").strip()


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class Identity:
    def __init__(self, seed, beacon_secret, created=0.0, path=None):
        self.seed, self.beacon_secret, self.created, self.path = seed, beacon_secret, created, path
        self.pub = crypto.public_key(seed)
        self.id = gotchi_id(self.pub)

    @classmethod
    def load_or_create(cls, data_dir):
        """Reads identity.json from data_dir, or creates a new identity there. With
        data_dir None (nowhere writable) the identity lives in memory only."""
        path = os.path.join(data_dir, "identity.json") if data_dir else None
        if path:
            try:
                with open(path) as f:
                    d = json.load(f)
                return cls(bytes.fromhex(d["seed"]), bytes.fromhex(d["beacon_secret"]),
                           d.get("created", 0.0), path)
            except FileNotFoundError:
                pass
            except (OSError, ValueError, KeyError) as e:
                # Never overwrite a damaged identity silently: keep it for a restore.
                log.error("identity.json is unreadable (%s); keeping it as identity.json.broken", e)
                try:
                    os.replace(path, path + ".broken")
                except OSError:
                    pass
        me = cls(crypto.new_seed(), os.urandom(16), time.time(), path)
        if path:
            try:
                me.save()
                log.info("New gotchi identity %s", me.id)
            except OSError as e:
                log.warning("Could not save the identity (%s); it is kept in memory only", e)
        return me

    def save(self):
        _write_json(self.path, {"v": 1, "seed": self.seed.hex(),
                                "beacon_secret": self.beacon_secret.hex(), "created": self.created})

    def sign(self, msg):
        return crypto.sign(self.seed, msg)


# --- backup and restore ----------------------------------------------------------

class BackupError(Exception):
    pass


def make_backup(data_dir, passphrase):
    """Everything that makes up the gotchi (identity, friends, progress), encrypted
    with the passphrase. Returns the backup as bytes (JSON)."""
    if len(passphrase) < 8:
        raise BackupError("The passphrase needs at least 8 characters.")
    files = {}
    for name in BACKUP_FILES:
        try:
            with open(os.path.join(data_dir, name)) as f:
                files[name] = f.read()
        except FileNotFoundError:
            pass
    if "identity.json" not in files:
        raise BackupError("There is no identity to back up yet.")
    salt, nonce = os.urandom(16), os.urandom(12)
    key = crypto.passphrase_key(passphrase, salt)
    sealed = crypto.seal(key, nonce, json.dumps(files).encode())
    b64 = lambda b: base64.b64encode(b).decode()
    # The format key keeps the old name (Claudegotchi), so older backups still load
    return json.dumps({"claudegotchi_backup": 1, "kdf": crypto.KDF,
                       "salt": b64(salt), "nonce": b64(nonce), "data": b64(sealed)}).encode()


def read_backup(blob, passphrase):
    """Decrypts a backup. Returns {file name: content}."""
    try:
        d = json.loads(blob)
        if d.get("claudegotchi_backup") != 1:
            raise ValueError
        salt, nonce, sealed = (base64.b64decode(d[k]) for k in ("salt", "nonce", "data"))
        if d.get("kdf") != crypto.KDF:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise BackupError("This is not a Tokibot backup.")
    plain = crypto.open_sealed(crypto.passphrase_key(passphrase, salt), nonce, sealed)
    if plain is None:
        raise BackupError("Wrong passphrase, or the file is damaged.")
    files = json.loads(plain)
    if "identity.json" not in files:
        raise BackupError("The backup has no identity in it.")
    json.loads(files["identity.json"])
    return {k: v for k, v in files.items() if k in BACKUP_FILES}


def restore_backup(data_dir, blob, passphrase):
    files = read_backup(blob, passphrase)
    for name in BACKUP_FILES:
        path = os.path.join(data_dir, name)
        if name in files:
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                f.write(files[name])
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        elif os.path.exists(path):
            os.remove(path)
    return gotchi_id(crypto.public_key(bytes.fromhex(json.loads(files["identity.json"])["seed"])))


def reset(data_dir):
    """Forget the identity and all social data. The critter's XP stays."""
    for name in ("identity.json", "social.json"):
        try:
            os.remove(os.path.join(data_dir, name))
        except FileNotFoundError:
            pass
