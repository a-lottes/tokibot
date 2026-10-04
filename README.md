# Claudegotchi (◕‿‿◕)

Ein kleiner E-Ink-Begleiter für Claude Code mit eigenem, schlankem Betriebssystem-Image.
Er zeigt mit einem Gesicht, was deine Claude-Code-Sessions gerade machen: arbeiten,
auf dich warten, um Erlaubnis fragen, fertig sein oder ins Limit laufen.

Die Idee stammt von Pwnagotchi, das Image ist aber eine eigene Sache. Es wird mit
Buildroot gebaut, enthält kein Debian und keine WLAN-Hacking-Werkzeuge, nur den
Claudegotchi-Dienst und das Nötigste drumherum.

```
Claude Code ── Hooks + Statusline ──► claudegotchi_client.py ──HTTP──► Pi: claudegotchi ──► e-Paper
                                          (USB-Kabel oder WLAN)
```

## Hardware

* Raspberry Pi Zero 2 W (Standard) oder Pi Zero W
* Waveshare 2.13" e-Paper HAT V4 (250 × 122)
* Ein USB-Datenkabel zum Mac (Micro-USB am Port **USB**, nicht **PWR**)

## Repository

```
app/       der Dienst auf dem Gerät (Python, Pillow)
  claudegotchi/brain.py      fasst alle Sessions zu einer Stimmung zusammen
  claudegotchi/painter.py    zeichnet Gesicht, Sprechtext, Fußzeile
  claudegotchi/displays/     Display-Treiber (Simulator, Waveshare 2.13" V4)
  claudegotchi/config.py     liest claudegotchi.toml
client/    Hook- und Statusline-Client für den Mac, plus Installer
os/        Buildroot-Erweiterung (br2-external): Defconfigs, Board-Dateien, Paket
```

## Ohne Hardware ausprobieren

```bash
python3 -m pip install pillow
make test
make sim                       # Vorschau: http://localhost:8765/
CLAUDEGOTCHI_URL=http://localhost:8765 python3 client/claudegotchi_client.py test
```

## Image bauen

Auf einem Linux-Rechner (Debian/Ubuntu) mit den Buildroot-Abhängigkeiten
(`build-essential bc cpio rsync unzip file wget`):

```bash
make zero2w      # oder: make zerow
```

Der erste Build lädt Buildroot und alle Quellen herunter und dauert gut eine Stunde.
Ergebnis: `output/zero2w/images/claudegotchi-zero2w.img.xz`. Auf GitHub baut der
Workflow `.github/workflows/image.yml` beide Images bei jedem Tag `v*`.

Flashen mit dem Raspberry Pi Imager: *Eigenes Image verwenden* und die `.img.xz` wählen.

## Einrichten

Nach dem Flashen liegt auf der Boot-Partition (`CLAUDEGOTCHI`) die Datei
`claudegotchi.toml`. Dort trägst du bei Bedarf WLAN, Token, Drehung und Zeitzone ein.
Ohne WLAN-Eintrag läuft das Gotchi nur über das USB-Kabel: Der Mac bekommt automatisch
eine Adresse, das Gotchi ist unter `192.168.77.1` erreichbar.

Am Mac:

```bash
python3 client/install_mac.py          # Adresse "auto": erst USB, dann claudegotchi.local
python3 ~/.claude/claudegotchi/claudegotchi_client.py test
```

Der Installer trägt Hooks und Statusline in `~/.claude/settings.json` ein, sichert die
alte Datei und lässt deine bisherigen Hooks und deine Statusline in Ruhe.
Entfernen: `python3 client/install_mac.py --uninstall`.

## Was im Image steckt

* Root-Dateisystem nur lesbar, `/tmp` und `/run` im RAM. Stromziehen schadet der Karte nicht.
* BusyBox-Init mit wenigen Skripten (`os/board/claudegotchi/rootfs-overlay/etc/init.d/`):
  Einstellungen lesen, USB-Gadget, WLAN, dann der Dienst.
* USB-Gadget als CDC-ECM-Netzwerkkarte mit DHCP-Server für den Mac.
* avahi für `claudegotchi.local`, NTP im WLAN. Ohne WLAN übernimmt das Gotchi die
  Uhrzeit vom Mac.
* Kein SSH im Standard-Image.

## Datenschutz

Übertragen werden nur Metadaten: Ereignis, Session-ID, Ordnername, Tool-Name und
Limit-Prozente. Prompts, Code und Antworten verlassen deinen Mac nicht.

## Stand

Version 0.1.0. Die App läuft im Simulator, die Buildroot-Defconfigs sind gegen
Buildroot 2026.02.3 geprüft. Ein vollständiger Image-Build und der Test auf echter
Hardware stehen noch aus.
