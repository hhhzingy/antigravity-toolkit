#!/usr/bin/env bash
# agy-guard: Persistent terminal session wrapper for Antigravity CLI (`agy`)
# Protects running `agy` CLI sessions from accidental terminal window closure or SSH disconnects.
set -euo pipefail

SESSION_NAME="${AGY_TMUX_SESSION:-agy}"

if ! command -v agy >/dev/null 2>&1; then
  for p in "${HOME}/.local/bin/agy" "/opt/homebrew/bin/agy" "/usr/local/bin/agy" "${HOME}/.gemini/antigravity-cli/bin/agy"; do
    if [ -x "$p" ]; then
      AGY_BIN="$p"
      break
    fi
  done
else
  AGY_BIN="$(command -v agy)"
fi

if [ -z "${AGY_BIN:-}" ]; then
  echo "[!] 'agy' CLI not found. Install via: curl -fsSL https://antigravity.google/cli/install.sh | bash" >&2
  exit 1
fi

if [ -n "${TMUX:-}" ]; then
  exec "${AGY_BIN}" "$@"
fi

if command -v tmux >/dev/null 2>&1; then
  if [ $# -eq 0 ]; then
    exec tmux new-session -A -s "${SESSION_NAME}" "${AGY_BIN}"
  else
    exec tmux new-session -A -s "${SESSION_NAME}" "${AGY_BIN}" "$@"
  fi
fi

# Fallback if tmux is not installed: trap SIGHUP so closing terminal doesn't immediately kill in-flight turn
trap '' HUP
exec "${AGY_BIN}" "$@"
