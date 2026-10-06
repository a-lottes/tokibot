# Changelog

## Unreleased

* Claudegotchi is now **Tokibot**, at https://tokibot.lottes.dev. Gotchis are called
  `tokibot-xxxx` with the same four digits as before. Clients, plugins and gotchis from
  before the rename keep working together: the old `X-Claudegotchi-*` headers and
  name, `claudegotchi.toml`, `~/.claudegotchi`, `CLAUDEGOTCHI_*` variables and the old
  relay messages are still understood, and friendships and backups stay valid.
  Run `install.py` once to move the client to `~/.tokibot`. A gotchi on 0.4.0 cannot
  update itself to this version, the app moved; flash the new image instead.
* The website menu folds into a button on phones and small windows.
* Not only Claude Code: the client also reports OpenAI Codex CLI, Gemini CLI,
  GitHub Copilot CLI, Cursor and Devin Desktop (Windsurf) sessions. Pick them with
  `install.py --harness claude,codex,…` or `--harness auto`. The bubble names the
  harness next to the project.
* Tokens are food: after every reply the client reads the token counts from the
  harness's session log (numbers only). They fill a stomach that empties over time;
  the new `fed` bar compares it with your usual day, not with a rate limit. New moods
  stuffed and peckish. XP stay the overall level.
* More displays, the ones common in Pwnagotchi builds: Waveshare 2.13" V1, V2, V3
  and V4, the 2.13" B V4 (black/white/red) and the 2.7" V1 and V2. Pick yours on the
  settings page or with `display` in `tokibot.toml`; Pwnagotchi's names for them
  (`waveshare_3`, `waveshare_4`, …) work too. Panels without partial refresh redraw
  at most once a minute and skip the animations.
* An unknown display name no longer stops the gotchi: it keeps running without a
  picture, so the settings page can fix it.

## 0.4.0 (first release)

The first release you can download: ready-made images for the Raspberry Pi Zero 2 W
and Zero W, plus the app bundle for updates without reflashing. Get them from the
[download page](https://claudegotchi.lottes.dev/download.html) or the GitHub release.

**Not yet tested on real hardware.** The images build cleanly, and the app runs in
the simulator, but nobody has booted them on a Pi with the e-paper yet. Expect
rough edges; please report what you find.

### The critter

* A pixel critter on a 2.13" e-paper shows what your Claude Code sessions are doing:
  ready, working, waiting for you, asking for permission, done, error, rate limit.
  With several sessions, the one that needs you most wins.
* It feels how the work is going: flow, struggling, stuck, proud after a commit or
  push, relieved when tests pass again, juggling several sessions.
* It grows: XP, levels, streaks, an evening summary, and it gets hungry after two
  days without code.
* Status bar with the 5-hour and 7-day budget.

### Friends

* Gotchis that meet notice each other over Bluetooth LE, become friends when both
  owners agree, and earn XP, badges and accessories for it.
* Anonymous by default, with an id that changes every 15 minutes; only friends
  recognise each other. Each friendship leaves a proof signed by both gotchis.
* The social page (`/social`) shows who is nearby and your friends, and makes an
  encrypted backup of the gotchi's identity, friends and progress.

### Setup and everyday use

* Works over the USB cable without any network, over Wi-Fi, or through a relay for
  Claude Code in the cloud.
* Every gotchi has its own name (`claudegotchi-xxxx`); the client pairs with it and
  gets a token automatically.
* Clients for macOS, Linux and Windows (`client/install.py`), or as a Claude Code
  plugin.
* Settings page in the browser instead of editing the SD card, and app updates
  without reflashing.
* Optional PiSugar 3 battery: charge level in the header, low-battery mood, clean
  shutdown.

### The image

* Buildroot, read-only root filesystem, a small writable data partition, no SSH, no
  Debian. Boot partition `GOTCHI` with `claudegotchi.toml`.

Only metadata leaves your computer (event, session, folder and tool names, limit
percentages); prompts, code and replies never do.
