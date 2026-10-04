# claudegotchi

A small e-ink companion for Claude Code with its own slim operating system image.
A pixel critter shows what your Claude Code sessions are up to: working, waiting
for you, asking for permission, done, or running into a rate limit.

![Every mood of the critter](docs/mockups.png)

The idea comes from Pwnagotchi, but the image is its own thing. It is built with
Buildroot, has no Debian and no Wi-Fi hacking tools, only the Claudegotchi service
and the bare minimum around it.

```
Claude Code ── hooks + status line ──► claudegotchi_client.py ──HTTP──► Pi: claudegotchi ──► e-paper
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

With several sessions (e.g. worktrees), the state that needs you most wins. The
footer shows how many sessions are working (▶), waiting for you (?) or done (✓),
plus bars for the 5-hour and 7-day budget.

## Hardware

* Raspberry Pi Zero 2 W (default) or Pi Zero W
* Waveshare 2.13" e-Paper HAT V4 (250 × 122)
* A USB data cable to your computer (micro-USB on the port labelled **USB**, not **PWR**)

## Repository

```
app/       the service on the device (Python, Pillow)
  claudegotchi/brain.py      folds all sessions into one mood
  claudegotchi/critter.py    the pixel critter and its expressions
  claudegotchi/painter.py    header, critter, speech bubble, status bar
  claudegotchi/mood.py       all display texts (one place, ready for i18n)
  claudegotchi/displays/     display drivers (simulator, Waveshare 2.13" V4)
  claudegotchi/config.py     reads claudegotchi.toml
  tools/mockups.py           renders docs/mockups.png
client/    hook and status line client for your computer, plus installer
os/        Buildroot extension (br2-external): defconfigs, board files, package
```

## Try it without hardware

```bash
python3 -m pip install pillow
make test
make sim                       # preview: http://localhost:8765/  (other port: make sim PORT=8766)
CLAUDEGOTCHI_URL=http://localhost:8765 python3 client/claudegotchi_client.py test
make mockups                   # every mood in docs/mockups.png
```

Python 3.9 or newer is enough on the computer.

## Build the image

On a Linux machine (Debian/Ubuntu) with the Buildroot dependencies
(`build-essential bc cpio rsync unzip file wget`):

```bash
make zero2w      # or: make zerow
```

The first build downloads Buildroot and all sources and takes about an hour.
Result: `output/zero2w/images/claudegotchi-zero2w.img.xz`. On GitHub, the workflow
`.github/workflows/image.yml` builds both images for every `v*` tag.

Flash it with Raspberry Pi Imager: *Use custom* and pick the `.img.xz`.

## Set up

After flashing, the boot partition (`CLAUDEGOTCHI`) contains `claudegotchi.toml`.
Put your Wi-Fi, token, rotation and time zone there if you need them. Without
Wi-Fi, the gotchi only talks over the USB cable: your computer gets an address
automatically and the gotchi is reachable at `192.168.77.1`.

On your computer:

```bash
python3 client/install_mac.py          # address "auto": USB first, then claudegotchi.local
python3 ~/.claude/claudegotchi/claudegotchi_client.py test
```

The installer adds hooks and a status line to `~/.claude/settings.json`, backs up
the old file, and leaves your existing hooks and status line alone.
Remove it with `python3 client/install_mac.py --uninstall`.

## What is in the image

* Read-only root filesystem, `/tmp` and `/run` in RAM. Pulling the plug does not hurt the card.
* BusyBox init with a few scripts (`os/board/claudegotchi/rootfs-overlay/etc/init.d/`):
  read settings, USB gadget, Wi-Fi, then the service.
* USB gadget as a CDC-ECM network adapter with a DHCP server for your computer.
* avahi for `claudegotchi.local`, NTP on Wi-Fi. Without Wi-Fi the gotchi takes the
  time from your computer.
* No SSH in the default image.

## Privacy

Only metadata is sent: event, session ID, folder name, tool name and limit
percentages. Prompts, code and replies never leave your computer.

## Status

Version 0.1.0. The app runs in the simulator and the Buildroot defconfigs are
checked against Buildroot 2026.02.3. A full image build and a test on real
hardware are still open.
