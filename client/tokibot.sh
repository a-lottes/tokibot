#!/bin/sh
# Starts tokibot_client.py with whatever Python the computer has.
# Claude Code runs hooks and the status line through sh on macOS and Linux and
# through Git Bash on Windows. On Windows "python3" is often missing or only a
# stub that opens the Microsoft Store, so try "py -3" and "python" there.
here=$(dirname "$0")
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*)
    for py in "py -3" python python3; do
      if $py -c "import sys; sys.exit(sys.version_info < (3, 9))" >/dev/null 2>&1; then
        exec $py "$here/tokibot_client.py" "$@"
      fi
    done
    exit 0 ;;
  *)
    exec python3 "$here/tokibot_client.py" "$@" ;;
esac
