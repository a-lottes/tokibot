#!/bin/sh
# Installs the Claudegotchi client into Claude Code on macOS, Linux, or Windows
# (in Git Bash, which comes with Git for Windows).
#
#   curl -fsSL https://claudegotchi.lottes.dev/install.sh | sh
#   curl -fsSL https://claudegotchi.lottes.dev/install.sh | sh -s -- --token my-secret
#   curl -fsSL https://claudegotchi.lottes.dev/install.sh | sh -s -- --statusline-only
#   curl -fsSL https://claudegotchi.lottes.dev/install.sh | sh -s -- --uninstall
#
# It downloads install.py, claudegotchi_client.py and claudegotchi.sh from this
# website into a temporary folder and runs the installer with the arguments you
# pass after "--".
set -eu

SITE="${CLAUDEGOTCHI_SITE:-https://claudegotchi.lottes.dev}"

# On Windows "python3" is often missing or a stub that opens the Microsoft Store
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) candidates="py -3|python|python3"; hint="Get it from https://www.python.org/downloads/" ;;
  Darwin) candidates="python3"; hint="On a Mac: xcode-select --install" ;;
  *) candidates="python3"; hint="Install python3 with your package manager." ;;
esac
py=""
IFS='|'
for c in $candidates; do
  unset IFS
  if $c -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then py=$c; break; fi
  IFS='|'
done
unset IFS
if [ -z "$py" ]; then
  echo "Claudegotchi needs Python 3.9 or newer. $hint" >&2
  exit 1
fi
if [ ! -d "$HOME/.claude" ]; then
  echo "Note: ~/.claude does not exist yet. Install Claude Code first: https://claude.com/claude-code" >&2
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
for f in install.py claudegotchi_client.py claudegotchi.sh; do
  curl -fsSL "$SITE/client/$f" -o "$tmp/$f"
done
$py "$tmp/install.py" "$@"
