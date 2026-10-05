#!/bin/sh
# Installs the Claudegotchi client into Claude Code on macOS or Linux.
#
#   curl -fsSL https://claudegotchi.lottes.dev/install.sh | sh
#   curl -fsSL https://claudegotchi.lottes.dev/install.sh | sh -s -- --token my-secret
#   curl -fsSL https://claudegotchi.lottes.dev/install.sh | sh -s -- --uninstall
#
# It downloads install_mac.py and claudegotchi_client.py from this website into a
# temporary folder and runs the installer with the arguments you pass after "--".
set -eu

SITE="${CLAUDEGOTCHI_SITE:-https://claudegotchi.lottes.dev}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Claudegotchi needs python3 (3.9 or newer). On a Mac: xcode-select --install" >&2
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
  echo "Claudegotchi needs Python 3.9 or newer, found $(python3 --version 2>&1)." >&2
  exit 1
fi
if [ ! -d "$HOME/.claude" ]; then
  echo "Note: ~/.claude does not exist yet. Install Claude Code first: https://claude.com/claude-code" >&2
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
for f in install_mac.py claudegotchi_client.py; do
  curl -fsSL "$SITE/client/$f" -o "$tmp/$f"
done
python3 "$tmp/install_mac.py" "$@"
