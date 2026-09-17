#!/bin/sh
# chat - start the local ask-the-wiki server. The macOS/Linux twin of chat.cmd.
#
# The .command extension is what makes Finder run it on a double-click. On
# Linux, or from any terminal, run it by path: tool/chat.command
#
# The window is kept open on any failure, for the same reason chat.cmd does it:
# a one-line error (a taken port, a failed build) must stay readable after the
# process ends instead of looking like "it just closed by itself".
#
#   tool/chat.command                 -> http://127.0.0.1:8787
#   tool/chat.command --port 9090

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

.venv/bin/python tool/chat.py "$@" || halt ""
