# Claudegotchi FAQ

Answers to common questions and problems when setting up a Claudegotchi, an e-ink companion for Claude Code that runs on a Raspberry Pi Zero, on macOS, Linux and Windows. Every answer stands on its own. The same text is on https://claudegotchi.lottes.dev/faq.html.

## Basics

### What is a Claudegotchi? {#what-is-it}

A Claudegotchi is a small gadget for your desk: a Raspberry Pi Zero with a 2.13 inch e-paper display. A pixel critter on the display shows what your Claude Code sessions are doing: working, waiting for you, asking for permission, done, or stuck at a rate limit. Claude Code reports to it through hooks and its status line. The gotchi runs its own small operating system image, built with Buildroot.

### Do I need Claude Code? {#need-claude-code}

Yes. The gotchi only shows what Claude Code is doing, so without Claude Code there is nothing to show. Claude Code needs a Claude subscription or an Anthropic API account. It can run on your computer (terminal or IDE extension) or in the cloud, for example in a Claude Project. For cloud sessions see [How do cloud sessions reach the gotchi?](#cloud-relay).

### Which computers are supported? {#supported-systems}

macOS, Linux and Windows. All of them need Python 3.9 or newer for the small client that talks to the gotchi. Windows also needs Git for Windows, because Claude Code runs hooks and the status line in Git Bash there. Over the USB cable the gotchi works without a driver on all three: Windows uses its built-in RNDIS driver, macOS and Linux use CDC-ECM.

### Which hardware do I need? {#hardware}

A Raspberry Pi Zero 2 WH (or Zero W/WH), a Waveshare 2.13 inch e-Paper HAT **V4**, a microSD card with 8 GB or more and a micro-USB **data** cable. That is about 50 to 60 euros and needs no soldering if the Pi already has its header. A PiSugar 3 battery is optional. The full list is at https://claudegotchi.lottes.dev/parts.html.

### Does it work with a Raspberry Pi 3, 4 or 5, or another display? {#other-hardware}

No. The image targets the Pi Zero 2 W and the Pi Zero W only, and it ships a driver only for the V4 revision of the Waveshare 2.13 inch e-Paper HAT. Older revisions (V1, V2, V3) and other sizes need drivers that are not in the image yet. The revision is printed on the back of the display board.

### What data does the gotchi get? Does it see my code? {#privacy}

Only metadata: the event name, session ID, project folder name, tool name, error or notification type, limit and context percentages, and categories of shell commands (test run, commit, push, pull request) that the client recognises on your computer. Prompts, code, commands and replies never leave your computer. With the cloud relay, that metadata passes through the ntfy server you chose.

## Image and flashing

### Which image do I download? {#which-image}

`claudegotchi-zero2w.img.xz` for the Raspberry Pi Zero 2 W and `claudegotchi-zerow.img.xz` for the first-generation Pi Zero W. Both are on https://claudegotchi.lottes.dev/download.html with SHA-256 checksums. Flash the `.img.xz` file as it is; Raspberry Pi Imager unpacks it.

### How do I flash the card? {#flash}

Open Raspberry Pi Imager, choose *Choose OS* → *Use custom*, pick the `.img.xz` file, choose the microSD card and write. Skip Imager's OS customisation (user, Wi-Fi, SSH): the Claudegotchi image does not use it and has its own settings file, `claudegotchi.toml`.

### Windows says "You need to format the disk" after flashing. What do I do? {#windows-format-prompt}

Click **Cancel**. Do not format. The card has partitions that Windows cannot read, which is normal for a Linux image. Formatting would erase the image. The partition Windows can read is called `GOTCHI` and holds `claudegotchi.toml`.

### macOS says "The disk you inserted was not readable by this computer". {#mac-disk-not-readable}

Click **Ignore**. The card has a Linux partition that macOS cannot read, which is normal. The `GOTCHI` drive with `claudegotchi.toml` shows up next to it.

### How do I check the download? {#checksum}

Compare the SHA-256 checksum with the one on the download page. On macOS run `shasum -a 256 claudegotchi-zero2w.img.xz`, on Linux `sha256sum claudegotchi-zero2w.img.xz`, on Windows in PowerShell `Get-FileHash claudegotchi-zero2w.img.xz`.

## Connecting over USB

### Which USB port do I use? {#which-port}

The micro-USB port labelled **USB**, the middle one of the three ports. Not the one labelled **PWR** at the edge. On the USB port the gotchi gets power and shows up on your computer as a network adapter; on PWR it only gets power and your computer does not see it.

### My computer does not see the gotchi at all. {#not-detected}

Check these in order:

- The cable is in the port labelled **USB**, not **PWR**.
- The cable carries data. Many micro-USB cables only charge. Try another cable, or one you have used for data before.
- The first boot takes a little while. Wait until the critter is on the display.
- Open `http://192.168.77.1:8765/` in a browser. If the preview of the display loads, the connection works and the problem is in the client setup.

### What address does the gotchi have? {#address}

Over the USB cable it is always `192.168.77.1`, port `8765`. Your computer gets an address from the gotchi automatically (DHCP, `192.168.77.2` to `.10`). On Wi-Fi the gotchi is `claudegotchi.local`. The gotchi does not route your internet traffic; your normal connection keeps working.

### Windows: the gotchi does not show up as a network adapter. {#windows-rndis}

Open Device Manager. The gotchi should be under *Network adapters* as a USB RNDIS adapter (for example *Remote NDIS Compatible Device*). If it is under *Other devices* with a warning sign instead, Windows did not pick the driver itself: right-click it, choose *Update driver* → *Browse my computer* → *Let me pick*, then *Network adapters* → *Microsoft* → *Remote NDIS Compatible Device*. Some company laptops block RNDIS adapters by policy; then use Wi-Fi instead.

### Windows shows "Unidentified network" for the gotchi. Is that a problem? {#windows-unidentified-network}

No. The gotchi's USB network has no internet and no gateway on purpose, so Windows calls it unidentified. Your internet connection is not affected. The client reaches the gotchi at `192.168.77.1` anyway.

### macOS asks "Allow accessory to connect?" {#mac-allow-accessory}

Click **Allow**. Newer macOS versions ask before a new USB device may connect. If you clicked *Don't Allow*, unplug and plug the gotchi in again, or allow it under System Settings → Privacy & Security.

### macOS shows a self-assigned IP address (169.254.x.x) for the gotchi. {#mac-self-assigned}

The gotchi's DHCP server has not answered yet. Wait until the critter is on the display, then unplug and plug in the cable again. In System Settings → Network the gotchi's adapter should get an address from `192.168.77.2` to `.10`.

### Linux: the adapter shows up but gets no address. {#linux-no-address}

Set the new wired connection to DHCP. With NetworkManager it is usually automatic; if not, set IPv4 to *Automatic (DHCP)* for the adapter (`nmcli device` lists it, often named `usb0` or `enx…`). With systemd-networkd or a manual setup, run a DHCP client on that interface. The gotchi itself is always `192.168.77.1`.

### `claudegotchi.local` does not resolve. {#mdns}

`.local` names need mDNS. On Linux install and start avahi with nss-mdns (on Debian and Ubuntu: `libnss-mdns`). On Windows `.local` lookups are often unreliable. Over the USB cable this does not matter: the client tries `192.168.77.1` first. On Wi-Fi you can set a fixed address instead, for example `--url http://192.168.1.50:8765` or the *Gotchi address* setting of the plugin.

## Installing the client

### Plugin or install script: which one should I use? {#plugin-or-script}

Either one, never both, or every event reaches the gotchi twice. The Claude Code plugin is the usual way: in Claude Code run `/plugin marketplace add https://claudegotchi.lottes.dev/marketplace.json` and `/plugin install claudegotchi@claudegotchi`. Plugins cannot set the status line, so add it with `curl -fsSL https://claudegotchi.lottes.dev/install.sh | sh -s -- --statusline-only`. Without the plugin, `curl -fsSL https://claudegotchi.lottes.dev/install.sh | sh` installs hooks and status line in one go.

### Why does the plugin need an extra step for the status line? {#statusline}

Claude Code plugins can add hooks but cannot set the status line. The gotchi learns how much of your 5-hour and 7-day budget is used only from the status line, so without it the budget bars stay empty and the critter cannot get tired or show the limit in advance. `install.sh --statusline-only` adds just the status line and keeps an existing one: it is still shown.

### `/plugin marketplace add` with the URL fails. {#plugin-url-fails}

Update Claude Code. The plugin is served as a zip archive from the website, and archive sources need Claude Code 2.1.224 or newer. Also check that your network can reach `claudegotchi.lottes.dev`. As an alternative, `curl -fsSL https://claudegotchi.lottes.dev/install.sh | sh` installs the same client without the plugin system.

### I installed both the plugin and install.sh. {#both-installed}

Remove the hooks from one of them, or every event is counted twice. To keep the plugin, run `curl -fsSL https://claudegotchi.lottes.dev/install.sh | sh -s -- --uninstall` and then `curl -fsSL https://claudegotchi.lottes.dev/install.sh | sh -s -- --statusline-only`. To keep the script instead, remove the plugin in `/plugin`.

### Windows: which terminal do I use for the commands? {#windows-terminal}

Git Bash, which comes with Git for Windows. The `curl … | sh` commands and `sh ~/.claude/claudegotchi/claudegotchi.sh test` are shell commands and do not work in PowerShell or cmd. Claude Code itself also runs the gotchi's hooks through Git Bash.

### Windows: "python3" opens the Microsoft Store or is not found. {#windows-python}

Install Python from https://www.python.org/downloads/ and keep the option that adds Python to PATH. On Windows `python3` is often only a stub that opens the Store. The Claudegotchi client and `install.sh` do not depend on it: in Git Bash they try `py -3`, then `python`, then `python3`, and take the first one that is Python 3.9 or newer.

### Windows: hooks do nothing, and Git for Windows is not installed. {#windows-no-git-bash}

Install Git for Windows from https://git-scm.com/downloads/win and restart Claude Code. Without Git Bash, Claude Code runs hooks in PowerShell, where the gotchi's hook command (`sh …`) does not exist, so nothing is sent.

### macOS: "python3" asks me to install the command line developer tools. {#mac-python}

Install them: click *Install*, or run `xcode-select --install`. They bring Python 3, which the client needs. Then run the install command again.

### How do I test the connection? {#test}

Run `sh ~/.claude/claudegotchi/claudegotchi.sh test` (on Windows in Git Bash). It walks the critter through its moods over about a minute and prints, for every step, which address answered. If a step fails it prints the addresses it tried. Both the full install script and `--statusline-only` put this file there.

### The critter does not react to Claude Code. {#not-reacting}

Check these in order:

- Start a new Claude Code session. Sessions that were already running keep their old settings and hooks.
- Run the test: `sh ~/.claude/claudegotchi/claudegotchi.sh test`.
- If the gotchi has a token, the client needs the same one: set it in `/plugin` (plugin) or run the install script again with `--token`.
- Check that plugin and install script are not both installed, see [I installed both](#both-installed).

### Does it work with Claude Code in VS Code or JetBrains? {#ide}

The IDE extensions run Claude Code with the same `~/.claude` settings, so the hooks reach the gotchi there as well. The terminal and the IDE can run at the same time; the gotchi counts every session.

### Several sessions at once: what does the gotchi show? {#several-sessions}

The state that needs you most wins: a permission request or a session waiting for you beats a working one. The footer shows how many sessions are working (▶), waiting for you (?) or done (✓). With three or more sessions working at once the critter juggles.

### How do I remove the client? {#uninstall}

Remove the plugin in `/plugin`, and the status line or full install with `curl -fsSL https://claudegotchi.lottes.dev/install.sh | sh -s -- --uninstall`. The uninstall puts your previous status line back. A backup of your original settings is in `~/.claude/settings.json.claudegotchi-backup`.

## Wi-Fi, settings and security

### How do I put the gotchi on Wi-Fi? {#wifi}

Either before the first start: put the card into your computer, open `claudegotchi.toml` on the `GOTCHI` drive and fill in `ssid`, `psk` and `country` under `[wifi]`. Or later in the browser: open `http://192.168.77.1:8765/settings` over the USB cable. Without Wi-Fi the gotchi works over the USB cable only, which is all you need on your desk.

### Where are the settings? {#settings}

On the settings page at `http://claudegotchi.local:8765/settings`, or `http://192.168.77.1:8765/settings` over USB. It changes Wi-Fi, time zone, rotation, token, relay and Bluetooth and writes `claudegotchi.toml` on the card. You can also edit that file directly on the `GOTCHI` drive.

### Should I set a token? {#token}

Yes, as soon as the gotchi is on a Wi-Fi you share with others. Without a token, anyone who can reach the gotchi on port 8765 can send it events and open the settings page. Set the token on the settings page, then give the client the same one: in `/plugin` for the plugin, or with `--token` for the install script.

### The picture is upside down. {#upside-down}

Set *Rotate display* to 180 on the settings page, or `rotate = 180` under `[device]` in `claudegotchi.toml`.

### The clock is wrong. {#clock}

Set your time zone on the settings page (`timezone`, for example `Europe/Berlin`). On Wi-Fi the gotchi gets the time from the internet (NTP); without Wi-Fi it takes the time from your computer.

### Can I log in to the gotchi with SSH? {#ssh}

No. The image has no SSH, and its root filesystem is read-only. Everything you can change is on the settings page or in `claudegotchi.toml`. App updates are uploaded on the settings page.

## Claude Code in the cloud

### How do cloud sessions reach the gotchi? {#cloud-relay}

Sessions in a Claude Project or in Claude Code on the web run in a cloud container that cannot see your desk. They send their events to a relay, an ntfy topic, and the gotchi listens to that topic over Wi-Fi. Setup, once: give the gotchi Wi-Fi; create a relay with `curl -fsSL https://claudegotchi.lottes.dev/install.sh | sh -s -- --new-relay` and enter the printed token and relay URL on the gotchi's settings page; print the setup script with `curl -fsSL https://claudegotchi.lottes.dev/install.sh | sh -s -- --cloud-setup > cloud-setup.sh`; on claude.ai add your own cloud environment that allows `ntfy.sh` and runs that script. The full walkthrough is at https://claudegotchi.lottes.dev/docs.html#cloud.

### Cloud sessions do not reach the gotchi. {#cloud-not-working}

Check these in order:

- The gotchi is on Wi-Fi with internet. The relay does not work over the USB cable alone.
- The token and relay URL on the gotchi's settings page match what `--new-relay` printed.
- The cloud environment allows `ntfy.sh` under Network access. The built-in environment of a Claude Project blocks it and has no settings, so you need your own environment (Project settings → Cloud environment → Add cloud environment).
- The setup script is pasted in that environment, and the project uses that environment. Only sessions started after the change use it.

### Is the relay secure? {#relay-security}

The topic name is the secret: anyone who knows it can read the events, which are metadata only, and could publish to it. The gotchi ignores relay messages without the right token. You can run your own ntfy server and point `--relay` at it; set `[relay] auth` on the gotchi if your server needs an access token.

## Battery and hardware

### How do I fit the PiSugar 3 battery? {#pisugar-fit}

Screw it under the Pi, battery side down, with the screws and spacers that come with it. Its pogo pins press against the pads of the first pins of the 40-pin header from below and carry power and I2C, so no soldering is needed. The display still goes on top. Step by step: https://claudegotchi.lottes.dev/build.html#battery.

### The gotchi does not show the battery. {#pisugar-not-detected}

The gotchi looks for the PiSugar on I2C (address 0x57) when it starts. If no battery shows in the header: check that the PiSugar is screwed on firmly so the pogo pins touch the header pads, then restart the gotchi. In `claudegotchi.toml`, `model` under `[battery]` must be `auto` or `pisugar3`, not `none`. Only the PiSugar 3 and 3 Plus are supported.

### Why did the gotchi switch itself off? {#battery-shutdown}

On battery, at 15 % the critter asks to be plugged in, and at 5 % it says good night and shuts down cleanly so the SD card is not cut off mid-write. Charge it through the PiSugar's USB-C port and switch it on with the PiSugar's power button. The threshold is `shutdown_at` under `[battery]`.

### The display stays blank. {#blank-display}

Check that the HAT sits flush on all 40 pins, and that it is the **V4** revision of the 2.13 inch display (printed on the back). Give it a moment: e-paper refreshes slowly and the first boot takes a little while. Faint traces of the previous picture are normal for e-paper.

## Friends over Bluetooth

### How do gotchis become friends? {#friends}

Gotchis that meet in real life notice each other over Bluetooth LE. Open the social page at `http://claudegotchi.local:8765/social`, tick *Open for new friends*, and press *Befriend* next to a gotchi nearby; its owner presses *Accept* on their social page. Both gotchis sign the friendship. Only game data travels over Bluetooth: never session contents, folder names or prompts. Turn it off on the settings page (*Meet other gotchis*) or with `[social] enabled = false`.

### How do I keep my critter's progress when I change the card? {#backup}

Download a backup on the social page. It is encrypted with a passphrase you choose and holds the identity, friends and progress. Restore it on the new card or gotchi. Without a backup, all of that lives only on the SD card.

## Updates

### How do I update the gotchi? {#update}

Download `claudegotchi-app.tar.gz` from https://claudegotchi.lottes.dev/download.html and upload it on the settings page. The gotchi checks that the new version starts and keeps it; if it crashes three times in a row right after starting, it goes back to the version built into the image. Kernel or system changes need a new image on the card.

### How do I update the client on my computer? {#update-client}

The plugin updates through `/plugin` when a new version is out. For the install script, run the same install command again; it keeps your address, token and relay.
