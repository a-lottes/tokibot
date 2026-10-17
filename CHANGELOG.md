# Changelog

## Unreleased

* Open source: the repository is public as `a-lottes/tokibot` (formerly
  `claudegotchi`). New: CONTRIBUTING.md, SECURITY.md and an issue form for bugs.
* The website links to the source code, the legal notice and the privacy policy.
* The highscore API accepts at most 30 requests a minute per address.
* The planning document for friends moved from the website to `design/social-concept.md`.

## 0.5.2

* The 5h and 7d budget no longer drops to an old value. Every Claude Code session's
  status line reports the limits of its own last API call, so an idle session or a
  second computer could replace a used-up 5h window (100%) with e.g. 17%. Within one
  window the gotchi now keeps the highest value and ignores reports from an earlier
  window; windows that have reset are no longer shown.
* Tested on real hardware: the images boot on a Pi Zero with the 2.13" e-paper,
  so the website and README no longer warn that a hardware test is open.

## 0.5.1

* Wi-Fi and time zone can be entered in Raspberry Pi Imager. The website has a list
  for Imager (double-click `tokibot.rpi-imager-manifest`, or the URL
  `https://tokibot.lottes.dev/downloads/imager.json` under *Content Repository*) whose
  images offer Imager's OS customisation. On first boot the gotchi moves what was
  entered into `tokibot.toml` and deletes Imager's files.
* Wi-Fi names with quotes or other special characters work, as do hidden networks and
  passwords given as a 64-digit hex key.
* Slower progression. Levels need more XP (level 2 at 120, 3 at 480, 4 at 1,080, 5 at
  1,920: 120 × (level − 1)²), a reply is worth 5 XP instead of 10, and tool calls earn
  XP only for the first 40 a day. Before, a few agentic prompts reached level 7.
  Existing XP stay, so a gotchi may show a lower level after the update.
* The `fed` bar no longer shoots past 100 %. The client counts only the last 30
  minutes of a session log it sees for the first time instead of its whole history,
  the assumed usual day before there is history is 6 million food points instead of
  1.5 million, and the bar stops at 100 % (the critter is stuffed beyond that).
* The settings page applies changes by itself: saving restarts the app (or reboots
  the gotchi for Wi-Fi, USB, time zone and Bluetooth) and the page reloads once the
  gotchi is back. The simulator restarts itself too, no more manual restart.
* The settings page explains where the token comes from (pairing, kept in
  `~/.tokibot/tokibot.json` on your computer and in `tokibot.toml` on the gotchi) and
  can remember it in the browser for the settings and friends pages.
* New look for the gotchi's own pages: one header with Live, Settings and Friends,
  settings grouped into Device, Network, Connection and Community, dark mode.
* New gotchis join the highscores and are open for new friends from the start. Both
  can be turned off; existing settings are kept.

## 0.5.0

* Claudegotchi is now **Tokibot**, at https://tokibot.lottes.dev. Gotchis are called
  `tokibot-xxxx` with the same four digits as before. Clients, plugins and gotchis from
  before the rename keep working together: the old `X-Claudegotchi-*` headers and
  name, `claudegotchi.toml`, `~/.claudegotchi`, `CLAUDEGOTCHI_*` variables and the old
  relay messages are still understood, and friendships and backups stay valid.
  Run `install.py` once to move the client to `~/.tokibot`. A gotchi on 0.4.0 cannot
  update itself to this version, the app moved; flash the new image instead.
* The website menu folds into a button on phones and small windows.
* The website and the assembly guide explain the other harnesses: step 7 installs
  hooks with `--harness`, the docs list which file each harness uses. Installing for
  other harnesses only no longer creates or changes Claude Code's settings.
* Four more harnesses: Kiro CLI 3, Cline, OpenCode and Amp (`install.py --harness`).
  OpenCode and Amp get a small plugin; the OpenCode one brings the token counts of
  every reply. Not yet tried against the real tools.
* Highscores on the website: Level (all time), Glutton (most food) and Gourmet (XP per
  food) for this week, this month and all time. Opt-in with *Join the highscores* on the
  settings page; the gotchi signs its card with its own key and posts it hourly, or the
  client posts it for a gotchi on the USB cable. Turning it off removes the entry.
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
