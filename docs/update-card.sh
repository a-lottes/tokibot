#!/bin/sh
# Tokibot card updater: puts a new image on a gotchi's SD card and keeps its progress.
#
#   curl -fsSL https://tokibot.lottes.dev/update-card.sh | sh
#
# Downloads update-card.py (the menu that does the work, read it at
# https://tokibot.lottes.dev/update-card.py) and starts it. It asks for sudo itself.
set -eu
SITE=${TOKIBOT_SITE:-https://tokibot.lottes.dev}
command -v python3 >/dev/null 2>&1 || {
	echo "The updater needs python3. On macOS: xcode-select --install" >&2; exit 1; }
dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT
curl -fsSL "$SITE/update-card.py" -o "$dir/update-card.py"
python3 "$dir/update-card.py" "$@" < /dev/tty
