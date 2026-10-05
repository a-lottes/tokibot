# Social concept: friends, encounters and a community

Status: phases 1–4 are built (version 0.3.0, see "Friends" in the README);
phases 5–7 are still a plan. Builds on XP, levels and streaks in `life.json` on the
`/data` partition, the settings page, app updates without flashing, and the ntfy
relay.

### How the build differs from this plan

* **No GATT connection.** Cards and friendship offers travel in fragments inside
  the advertisements themselves (27 bytes each). That needs no connection and no
  bluetoothd, and works on the Pi Zero's Bluetooth 4.2 chip.
* **The card is only sent when the owner is "open for new friends"** (or has asked
  someone). Otherwise a gotchi is fully anonymous; a public key next to a rotating
  id would make it trackable again.
* **Consent** is the social page (or "say yes automatically" after three meetings
  on different days). The hardware button is still to come.
* **Accessories instead of colours**, since the display is black and white. The
  "gift from a friend" and the "far away" badge are not built.
* **Crypto** is plain Python (`crypto.py`, checked against the RFC test vectors), so
  nothing new has to be installed on the device or the Mac.
* **Reset** forgets the key and friends, but keeps the critter's XP.

## Goal

Turn the gotchi into a small social gadget. Gotchis that meet in real life
notice each other over Bluetooth, become friends, and earn something for it.
Later, a community site lets friends chat and keep in touch between meetings.

**The profile is bound to the gotchi.** There is no separate sign-up: the
device's key *is* the identity, on the device and on the site. Whoever holds the
gotchi holds the profile.

### Non-goals

* No Claude session content ever leaves the device for social features: no
  prompts, folders, tool names or session IDs. Social only sees game data.
* No public tracking. A stranger must not be able to follow a gotchi around.
* No phone app in the first phases. The gotchi, its settings page and later the
  site are enough.

## Phases

| Phase | What | Needs a server |
|---|---|---|
| 1 Identity | key pair, profile, backup and restore | no |
| 2 Encounters | BLE beacons, seeing other gotchis nearby | no |
| 3 Friends | mutual friendship over BLE, signed friendship proof | no |
| 4 Game | XP for encounters, badges, critter variants | no |
| 5 Community site | sign in with the gotchi, profile page, friend list | yes |
| 6 Chat | end-to-end encrypted messages between friends | yes |
| 7 Community | groups, events, leaderboards (opt-in) | yes |

Phases 1–4 work fully offline. Everything they create (identity, friendship
proofs) is designed so phases 5–7 can trust it without trusting the server.

## 1. Identity

* On first boot the gotchi creates an **Ed25519 key pair** and stores it in
  `/data/identity/` (writable partition, survives updates). The private key never
  leaves the device, except in an encrypted backup the owner asks for.
* **Gotchi ID** = first 16 bytes of `sha256(public key)`, shown as a short code
  like `cg-7f3a-91c2`.
* **Profile**, signed by the key and versioned:
  ```json
  {"v": 1, "id": "cg-7f3a-91c2", "pub": "<ed25519 pub>",
   "name": "Pixel", "variant": "classic-orange", "level": 7,
   "badges": ["first-friend"], "updated": 1759680000, "sig": "<sig>"}
  ```
  Name and variant are set on the settings page. Level and badges come from
  `life.json`.
* **Backup and restore** on the settings page: download the identity, encrypted
  with a passphrase the owner chooses. Restoring it on a new SD card or a new
  gotchi moves the whole profile, friends included. Without a backup, a lost card
  means a new gotchi. The page says so plainly.
* **Reset** deletes the key and all social data; friends see this gotchi as gone.

## 2. Encounters over Bluetooth LE

The Pi Zero 2 W and Zero W have BLE. The image gets BlueZ (also needed for
Bluetooth tethering) and the app a `social.py` module that talks to BlueZ over
D-Bus.

**Beacon.** Every gotchi advertises a small manufacturer-data block every few
seconds:

| Field | Size | Content |
|---|---|---|
| magic + version | 3 B | `CG` + `1` |
| ephemeral ID | 6 B | random, changes every 15 minutes |
| friend tag | 4 B | `HMAC(beacon_secret, 15-min epoch)`, truncated |
| level | 1 B | |
| mood | 1 B | current mood (working, waiting, …) |
| variant | 1 B | critter variant |

* Strangers see only a random ID that changes every 15 minutes, plus level, mood
  and variant. They cannot tell that two sightings are the same gotchi.
* **Friends recognise each other**: when two gotchis become friends they swap
  their `beacon_secret`. A friend can compute the current friend tag and knows
  who is near; nobody else can.
* **Encounter** = another gotchi seen for at least 30 s above an RSSI threshold
  (roughly "same table"). The critter waves; the header shows the other's level,
  or the friend's name.
* Scanning runs in intervals (e.g. 10 s every minute) to save battery.
  Advertising is cheap and runs all the time while social is on.

## 3. Friendship

When two gotchis have an encounter, they open a short BLE GATT connection and
swap **signed profiles**. A friendship needs consent from both sides:

* **Button**: both owners press the button within 30 s (needs the GPIO button
  from the hardware list), or
* **Settings page**: "Befriend Pixel nearby?" with a confirm button, or
* **Auto**, if both owners enable it: after the third encounter on different
  days.

Then both devices sign a **friendship proof**:

```json
{"v": 1, "a": "<pub A>", "b": "<pub B>", "met_at": 1759680000,
 "sig_a": "<sig by A>", "sig_b": "<sig by B>"}
```

Both keep it, along with the friend's profile and `beacon_secret`, in
`/data/social/friends.json`. The proof is the bridge to the community site: it
shows that two gotchis really met, signed by both, without any server being
involved. Unfriending deletes the local record; on the site it removes the link
for both.

## 4. Game

Fits into the existing XP system in `mood.py`:

* **XP**: an encounter with a new gotchi (+20), a friend seen again on a new
  day (+5), a new friendship (+30). Capped per day so a room full of gotchis
  does not break the curve.
* **Badges**: first friend, 10 friends, 5 gotchis at once ("conference"), a
  friend from far away (by their time zone), co-working (a friend nearby while
  both are in `working`), night owl, long streaks.
* **Critter variants**: colours and accessories unlocked by badges, or as a
  gift from a friend (once per friendship).
* **Co-working buff**: two friends nearby, both working with Claude, both get
  +10 % XP and the critters cheer each other on.
* Everything is decided on the device. Signed encounters and proofs make
  cheating dull rather than impossible; that is enough for a game among friends.

## 5. Community site

A web site (and API) that mirrors what the gotchis already know. It never sees
Claude session data.

**Sign in with the gotchi.** No password, no e-mail needed:

1. The owner opens the site and clicks "Sign in with my gotchi".
2. The site shows a short code. The owner enters it on the gotchi's settings
   page (or scans a QR code the e-ink shows).
3. The gotchi signs a challenge with its key; the site checks it against the
   public key and creates the account for that gotchi ID.
4. That browser becomes a **linked browser**: it gets its own key pair, and the
   gotchi signs it. The owner can see and revoke linked browsers on the
   settings page or on the site.

**What the site keeps**: the signed profile, friendship proofs the gotchi
uploads, linked browsers, and later messages. A friend appears on the site only
if a friendship proof signed by both exists, so the friend graph comes from
real meetings, not from the server.

**Sync**: the gotchi uploads its profile and new proofs when it has internet,
over HTTPS to the site's API. The site can also push notifications back
("new message from Pixel") through the same kind of outgoing connection the
ntfy relay uses today, so no port is opened on the gotchi.

**Privacy controls**: profile visible to friends only (default) or public;
shown on leaderboards yes/no; delete account, which deletes everything on the
server and is also triggered by a gotchi reset.

## 6. Chat

* Only between friends with a valid friendship proof.
* **End-to-end encrypted.** Each gotchi and each linked browser has an X25519
  key, signed by the gotchi's identity key. A message is encrypted for all of the
  friend's keys and all of the sender's own linked browsers. The server stores
  and forwards ciphertext only.
* Written and read on the site (desktop or phone browser). The gotchi itself
  shows a notification ("✉ Pixel") and the critter's reaction; with the button
  it can send quick reactions: wave, high five, "coffee?".
* Small extras that fit the theme: share your current mood with a friend, a
  "focus mode" status from the gotchi so friends know you are deep in work.
* Moderation: block and report per friend, rate limits, no messages from
  non-friends.

## 7. Community

Opt-in and later: groups (team, meetup, city), event codes that award a badge
to everyone present at a meetup, weekly leaderboards among friends, and a
public profile page for those who want one.

## Changes in the repository

| Where | What |
|---|---|
| `os/` | BlueZ and Bluetooth firmware in the defconfigs; `dbus`; enable the BT UART |
| `app/claudegotchi/identity.py` | key pair, profile, signing, backup/restore |
| `app/claudegotchi/social.py` | BLE beacon, scanning, GATT exchange, friends store |
| `app/claudegotchi/mood.py` | social XP, badges, texts for encounters |
| `app/claudegotchi/painter.py` | wave, friend name in the header, message icon |
| settings page | name, variant, social on/off, friends list, backup, linked browsers |
| simulator | a fake nearby gotchi so all of this can be tried without hardware |
| new: `community/` | site and API (phase 5+), separate from the device code |

Crypto on the device uses one small, well-known library (PyNaCl or
`cryptography`); both are in Buildroot.

## Open questions

1. Where does the community site run, and who operates it? (Self-hosted by you,
   a small managed host, or federated so anyone can run one.)
2. Should a gotchi be able to *move* to a new owner (sold or given away)? Then a
   "transfer" that keeps level and badges but drops friends and chats.
3. Age and legal side of a community with chat: terms, imprint, data protection
   notice, minimum age.
4. Is a phone app ever wanted? It would make encounters possible without a
   gotchi, which changes the idea; this concept assumes no.
5. Name for the community.
