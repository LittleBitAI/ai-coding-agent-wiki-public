#!/bin/sh
# mirror - open the Korean mirror. The macOS/Linux twin of mirror.cmd.
#
# The .command extension is what makes Finder run it on a double-click. On
# Linux, or from any terminal, run it by path: tool/mirror.command
#
# The mirror is a tab of the wiki app, not a server of its own. So this walks
# the same path chat.command does and lands on that tab. If the app is already
# running it just opens the tab instead of fighting for the port.
#
#   tool/mirror.command                -> http://127.0.0.1:8787/#mirror
#   tool/mirror.command --port 9090
#
# Which repository it watches is chosen in the page, not here.

halt() {
  [ -n "$1" ] && echo "$1"
  echo
  printf '(stopped. press enter to close this window)'
  read -r _
  exit 1
}

cd "$(dirname "$0")/.." || exit 1
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

if [ ! -x .venv/bin/python ]; then
  halt "Run: python3 tool/setup_chat.py install --agent codex
Or use --agent claude / --agent both. See docs/chat-setup.md."
fi

if [ ! -f web/dist/index.html ]; then
  halt "Run the setup command again to build the page."
fi

.venv/bin/python tool/chat.py --open "#mirror" "$@" || halt ""
