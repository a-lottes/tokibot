# Tokibot

A small e-ink companion for your coding agents with its own slim operating system
image (formerly Claudegotchi). A pixel critter shows what your Claude Code, Codex,
Gemini, Copilot, Cursor or Devin sessions are up to: working, waiting for you,
asking for permission, done, or running into a rate limit. The tokens they burn
are its food.

![Every mood of the critter](docs/mockups.png)

The idea comes from Pwnagotchi, but the image is its own thing. It is built with
Buildroot, has no Debian and no Wi-Fi hacking tools, only the Tokibot service
and the bare minimum around it.

```
Claude Code ── hooks + status line ──► tokibot_client.py ──HTTP──► Pi: tokibot ──► e-paper
                                          (USB cable or Wi-Fi)
```

## Moods

| Mood | When |
|---|---|
| ready | a new session started |
| working | prompt sent, tools running |
| tired | working, but 80 % or more of the 5-hour budget is used |
| permission | Claude asks for permission |
| waiting | Claude waits for your input |
| done | the reply is finished |
| error | API error (overloaded, logged out, …) |
| limit | rate limit reached, with the time it resets |
| idle | nothing going on |
| levelup | the critter just reached a new level |
| summary | idle in the evening (18–23 h): the day's tally |
| hungry | no work for two days or more |
| stuffed | working with a very full stomach (see [Food](#food)) |
| peckish | idle during the day (9–18 h) with an empty stomach |
| lowbattery | on battery with 15 % or less left (only with a PiSugar) |

### How it's going

On top of what is happening, the critter feels how the work is going. Every signal
nudges two values that fade over time: valence (going well or badly, half-life
10 minutes) and energy (how busy, 3 minutes). They tint the situation:

| Mood | When |
|---|---|
| stuck | the same tool failed 3 times in a row |
| oops | you interrupted Claude (shown for 2 minutes) |
| proud | a commit, push or pull request just landed (2 minutes) |
| relieved | tests pass again after failing (2 minutes) |
| struggling | working, but lots went wrong lately |
| juggling | 3 or more sessions working at once |
| flow | working, and lots went right lately (clean replies, green tests) |

Permission, waiting, limit and error are never tinted: anything that needs you
wins. A tint holds for at least 30 seconds so the e-paper does not flicker. When a
session's context window is 85 % full, the critter carries a wrench. The client
recognises test runs, commits, pushes and `gh pr create` on your computer and only
sends the category, never the command.

With several sessions (e.g. worktrees), the state that needs you most wins. The
footer shows how many sessions are working (▶), waiting for you (?) or done (✓),
plus a bar for how full the critter is (`fed`) and Claude Code's 5-hour budget. The
7-day budget only shows when it is 80 % used or more.

## Growing up

The critter earns experience from your work: 10 XP per finished reply, 5 per
completed task, 3 per new session and 1 per tool call, plus 5 per commit, 8 per
push and 15 per pull request. Levels get further apart
as it grows (level 2 at 50 XP, level 3 at 150, level 4 at 300, …), and the level
shows in the header. Every day with at least one finished reply extends the streak;
skip a day and it starts over. In the evening it shows what you did today, and when
you leave it alone for two days it gets hungry.

### Food

Tokens are the critter's food; XP stay its overall level. After every reply the
client reads the token counts from the harness's own session log on your computer
(numbers only) and sends them along. They count as food points: input, output and
cache writes in full, cache reads at 10 %, since those are cheap and would drown
everything else.

The food fills a stomach that empties by half every 90 minutes. How full it is (the
`fed` bar) compares with your own usual day, the average of the last 14 days with
food, so it works the same for a light and a heavy user and has nothing to do with
any rate limit. 100 % is as full as while working on a usual day; from 150 % it is
stuffed, below 10 % and idle during the day it is peckish. Harnesses that report no
token counts (Copilot, Cursor, Devin) feed it an estimate per reply and tool call.

The progress lives in `life.json` on the image's small writable `data` partition
(`~/.tokibot/` in the simulator), so it survives reboots and updates of the
root filesystem. All numbers and texts are in `app/tokibot/mood.py`.

## Friends

Gotchis that meet in real life notice each other over Bluetooth LE, can become
friends, and earn XP, badges and accessories for it. Everything works offline;
the design leaves room for a community site with chat later
([docs/social-concept.md](docs/social-concept.md)).

* **Identity.** On first start the gotchi creates an Ed25519 key pair. The key *is*
  the profile: no sign-up, no password. Name and accessory are set on the social page.
* **Anonymous by default.** A gotchi sends a small beacon with a random id that
  changes every 15 minutes, its level, mood and accessory. Strangers cannot follow it
  around. Friends recognise it by a tag only they can compute.
* **Open for new friends.** Only when you switch this on (social page) does the
  gotchi also send its signed card with name and level, so others nearby can ask
  to be friends.
* **Friendship needs both.** One side asks, the other says yes on its social page
  (or automatically, for gotchis met on three different days, if both allow it).
  Both gotchis sign the friendship; the two signatures are a proof that a community
  site can check later without trusting anyone.
* **Game.** 20 XP for meeting a gotchi for the first time, 5 for meeting it again on
  another day, 2 for an anonymous one (encounter XP is capped at 100 a day), 30 for a
  new friend. +10 % XP while a friend nearby is working too. Badges and levels unlock
  accessories: cap, bow, glasses, headphones, night cap, party hat, crown.
* **On the display.** ♥ and the number of friends nearby (● for other gotchis) next to
  the clock; the critter waves at new gotchis and celebrates new friends.

Open `http://tokibot-xxxx.local:8765/social` (or `/social` in the simulator) to see
who is nearby, befriend them, pick an accessory and download a **backup**. The
identity, friends and progress only live on the SD card; the backup is encrypted
with a passphrase you choose and restores everything on a new card or gotchi.

Only game data travels over Bluetooth: never session contents, folder names or
prompts. Turn it all off with `[social] enabled = false` or on the settings page.

To try it in the simulator, start it with a pretend gotchi nearby, open your gotchi
for new friends on the social page and wait a minute:

```bash
make sim FAKE=Mochi
```

Two simulators on one computer (different `PORT` and settings files) also meet each
other.

## Hardware

* Raspberry Pi Zero 2 W (default) or Pi Zero W
* A Waveshare e-Paper HAT, set in `tokibot.toml` (`[device] display`) or on the
  settings page:

  | Display | `display =` | Pwnagotchi name |
  | --- | --- | --- |
  | 2.13" V4 (250 × 122), default | `waveshare_2in13_v4` | `waveshare_4` |
  | 2.13" V3 | `waveshare_2in13_v3` | `waveshare_3` |
  | 2.13" V2 | `waveshare_2in13_v2` | `waveshare_2` |
  | 2.13" V1 | `waveshare_2in13_v1` | `waveshare_1` |
  | 2.13" B V4, black/white/red (full refresh only) | `waveshare_2in13b_v4` | `waveshare2in13b_v4` |
  | 2.7" V2 (264 × 176) | `waveshare_2in7_v2` | `waveshare27inchv2` |
  | 2.7" V1 (full refresh only) | `waveshare_2in7_v1` | `waveshare27inch` |

  The revision is printed on the back of the board. On the 2.7" the picture is centred
  with a white margin. Smaller panels (Inky pHAT, PaPiRus, 1.54", OLED HATs) are not
  supported: the layout is drawn for 250 × 122.
* A USB data cable to your computer (micro-USB on the port labelled **USB**, not **PWR**)
* Optional: a [PiSugar 3](https://github.com/PiSugar/PiSugar/wiki/PiSugar-3-Series) battery
  (1200 mAh for the Zero), see [Battery](#battery)

## Repository

```
app/       the service on the device (Python, Pillow)
  tokibot/brain.py      folds all sessions into one mood
  tokibot/feeling.py    how the work is going: valence, energy, stuck, proud, …
  tokibot/critter.py    the pixel critter and its expressions
  tokibot/painter.py    header, critter, speech bubble, status bar
  tokibot/mood.py       all display texts (one place, ready for i18n)
  tokibot/displays/     display drivers (simulator, Waveshare 2.13" V1–V4, 2.13" B, 2.7")
  tokibot/config.py     reads tokibot.toml
  tokibot/relay.py      listens to an ntfy topic for cloud sessions
  tokibot/life.py       experience, levels, streaks and daily stats
  tokibot/settings.py   the settings page in the browser
  tokibot/update.py     app updates without flashing
  tokibot/identity.py   the gotchi's key pair, backup and restore
  tokibot/social.py     encounters and friendships (the Bluetooth protocol)
  tokibot/radio.py      Bluetooth LE over raw HCI, and a UDP radio for the simulator
  tokibot/crypto.py     Ed25519, X25519, sealing, backups (libsodium via PyNaCl)
  tokibot/socialpage.py the social page in the browser
  tools/mockups.py           renders docs/mockups.png
client/    hook and status line client for your computer, plus installer
os/        Buildroot extension (br2-external): defconfigs, board files, package
```

## Try it without hardware

```bash
python3 -m pip install pillow pynacl
make test
make sim                       # preview: http://localhost:8765/  (other port: make sim PORT=8766)
TOKIBOT_URL=http://localhost:8765 python3 client/tokibot_client.py test
make mockups                   # every mood in docs/mockups.png
```

Python 3.9 or newer is enough on the computer.

## Build the image

On a Linux machine (Debian/Ubuntu) with the Buildroot dependencies
(`build-essential bc cpio rsync unzip file wget`):

```bash
make zero2w      # or: make zerow
```

You only need this to change the image yourself; ready-made images are on the
[download page](https://tokibot.lottes.dev/download.html). The first build
downloads Buildroot and all sources and takes about an hour.
Result: `output/zero2w/images/tokibot-zero2w.img.xz`. On GitHub, the workflow
`.github/workflows/image.yml` builds both images for every `v*` tag and attaches
them, with the app bundle, to the release.

Flash it with Raspberry Pi Imager: *Use custom* and pick the `.img.xz`.

## Set up

After flashing, the boot partition (`TOKIBOT`) contains `tokibot.toml`.
Put your Wi-Fi, token, rotation and time zone there if you need them. Without
Wi-Fi, the gotchi only talks over the USB cable: your computer gets an address
automatically and the gotchi is reachable at `192.168.77.1`.

On your computer:

```bash
python3 client/install.py          # address "auto": USB first, then your gotchi's name on Wi-Fi
sh ~/.claude/tokibot/tokibot.sh test
```

### Other coding harnesses

The gotchi is not only for Claude Code. The installer can add its hooks to other
harnesses too; their sessions show up like Claude Code's, with the harness's name
next to the project:

```bash
python3 client/install.py --harness claude,codex,gemini   # pick them
python3 client/install.py --harness auto                  # all found on this computer
```

| Harness | Hooks go to | Tokens |
|---|---|---|
| Claude Code | `~/.claude/settings.json` (or the plugin) | from the transcript |
| OpenAI Codex CLI | `~/.codex/hooks.json` (approve them once with `/hooks` in Codex) | from the rollout log |
| Gemini CLI | `~/.gemini/settings.json` | from the session file |
| GitHub Copilot CLI | `~/.copilot/hooks/tokibot.json` | estimated |
| Cursor | `~/.cursor/hooks.json` | estimated |
| Devin Desktop (Windsurf) | `~/.codeium/windsurf/hooks.json` | estimated |

The client translates every harness into Claude Code's hook events, so the gotchi
only knows one vocabulary. Cursor also runs the hooks from `~/.claude/settings.json`;
the client recognises that and reports those sessions as Cursor (or drops them, when
Cursor's own hooks are installed). Without Claude Code there is no 5-hour budget bar,
and the limit mood only shows when a harness reports a rate-limit error.

### Which gotchi?

Every gotchi has its own network name, `tokibot-xxxx`, where `xxxx` comes from
the Pi's serial number. It shows the name on screen until a client talks to it. So
two gotchis on the same Wi-Fi (yours and a friend's) never answer to the same name.

The installer pairs the client with your gotchi: plug the gotchi in with the USB
cable, or pass its name with `--gotchi tokibot-xxxx` for Wi-Fi only. Pairing
remembers the name and, if the gotchi has no token yet, the gotchi makes one, saves
it in `tokibot.toml` and hands it to this computer. From then on it only takes
events from clients with that token. Pair again any time:

```bash
sh ~/.claude/tokibot/tokibot.sh pair                    # over USB
sh ~/.claude/tokibot/tokibot.sh pair tokibot-xxxx  # over Wi-Fi
```

The client sends the gotchi's name with every event. A gotchi with another name
answers 409 and the event is not shown there. Without pairing, the client learns the
name the first time it reaches a gotchi over the USB cable.

The installer adds hooks and a status line to `~/.claude/settings.json`, backs up
the old file, and leaves your existing hooks and status line alone.
Remove it with `python3 client/install.py --uninstall`.

Or install it as a Claude Code plugin from this repository (or from the
website's `https://tokibot.lottes.dev/marketplace.json`):

```
/plugin marketplace add a-lottes/tokibot
/plugin install tokibot@tokibot
```

The plugin brings the hooks only, because plugins cannot set the status line.
Add the status line with `python3 client/install.py --statusline-only`. Use
the plugin or the full installer, not both. `plugin/build.py` packs the plugin
for the website.

Problems during setup? [docs/faq.md](docs/faq.md) answers the common ones per
operating system (also at https://tokibot.lottes.dev/faq.html). After editing it,
run `make faq` to rebuild the page.

## Settings in the browser

Open `http://tokibot-xxxx.local:8765/settings` (or `http://192.168.77.1:8765/settings`
over USB) to change Wi-Fi, time zone, rotation, token and relay. The page writes
`tokibot.toml` on the boot partition, keeps its comments, and restarts the
gotchi. Once a token is set, the page asks for it. Editing the file on the SD
card still works too.

## Updates without flashing

The Python app can be updated in place; only kernel or system changes need a new
image.

```bash
make update GOTCHI=http://tokibot-xxxx.local:8765 TOKEN=your-token
```

This packs `app/` into `output/tokibot-app.tar.gz` and sends it to the gotchi.
You can also upload that file on the settings page; every GitHub release carries
one. The gotchi checks that the new version starts, keeps it in `/data/app`, and
restarts. If it crashes three times in a row right after starting, it falls back
to the version built into the image. "Back to the built-in version" on the
settings page does the same by hand.

## On the go and with Claude in the cloud

Hooks run wherever Claude Code runs. A session on your laptop reaches the gotchi
over the USB cable, or over a shared Wi-Fi such as your phone's hotspot (put it
under `[wifi]`). A session in the cloud, for example in a Claude Project, runs in
a container that cannot see your local network. For that case the gotchi can listen
to a relay: an [ntfy](https://ntfy.sh) topic. Cloud hooks publish to the topic, and
the gotchi keeps one outgoing connection to it, so it works behind any hotspot.

1. Create a relay topic and a token on your computer:

   ```bash
   python3 client/install.py --new-relay
   ```

   It prints a `[server]` token and a `[relay]` url. Put both into
   `tokibot.toml` on the gotchi, and give it Wi-Fi (the phone hotspot works).
2. Print a setup script for the cloud environment and paste it into the
   environment's setup script:

   ```bash
   python3 client/install.py --cloud-setup > cloud-setup.sh
   ```

   The script carries the client inline and installs it with `url = none`, so it
   only publishes to the relay.
3. On claude.ai, add your own cloud environment (in a Claude Project: Project
   settings → Cloud environment → Add cloud environment). Under Network access
   choose Custom and add `ntfy.sh` to the allowed domains; paste `cloud-setup.sh`
   as the setup script. The built-in environment blocks ntfy.sh. New sessions then
   report through the relay. Full walkthrough: https://tokibot.lottes.dev/docs.html#cloud

The topic name is the secret: anyone who knows it can read the events (metadata
only, see below) and could publish to it. The gotchi ignores relay messages
without the right token. You can also run your own ntfy server and point
`--relay` at it; set `[relay] auth` if it needs an access token.

## Battery

With a PiSugar 3 (or 3 Plus) screwed under the Pi, the gotchi runs without a cable.
Nothing needs to be set up: at start it looks for the PiSugar on I2C (address 0x57)
and, if there is one, shows the charge as a small battery in the header, with a
lightning bolt while it is on power. On battery with 15 % or less, the critter asks
to be plugged in. At 5 % it says good night and shuts down cleanly, so the SD card is
not cut off mid-write. To start it again, charge it and switch it on with the PiSugar's button.

Without a PiSugar nothing changes. Settings live under `[battery]` in
`tokibot.toml` (`model = "auto" | "pisugar3" | "none"`, `shutdown_at`).
Try it without hardware: `make sim BATTERY=sim` (a fake battery that drains and
recharges, or `BATTERY=sim:20` to start at 20 %).

## What is in the image

* Read-only root filesystem, `/tmp` and `/run` in RAM. Pulling the plug does not hurt the card.
* A 16 MB writable `data` partition at `/data` for the critter's progress and app updates.
* BusyBox init with a few scripts (`os/board/tokibot/rootfs-overlay/etc/init.d/`):
  read settings, hostname, Bluetooth, USB gadget, Wi-Fi, then the service.
* USB gadget as a network adapter with a DHCP server for your computer: RNDIS for
  Windows, CDC-ECM for macOS and Linux, no driver needed.
* avahi for `tokibot-xxxx.local` (a name of its own per gotchi), NTP on Wi-Fi. Without Wi-Fi the gotchi takes the
  time from your computer.
* Bluetooth LE through the kernel's HCI socket, no bluetoothd.
* No SSH in the default image.

## Privacy

Only metadata is sent: event, harness, session ID, folder name, tool name, limit and
context percentages, token counts, and categories of shell commands (test run, commit, push,
pull request) recognised on your computer. Prompts, code and replies never leave your computer. With a relay,
that metadata passes through the ntfy server you chose.

## Status

Version 0.4.0, the first release ([changelog](CHANGELOG.md)). Ready-made images
and the app bundle are on the [download page](https://tokibot.lottes.dev/download.html)
and in the GitHub release. The images build cleanly on GitHub and the app runs in
the simulator; a test on real hardware is still open, including the Bluetooth radio
for friends.
