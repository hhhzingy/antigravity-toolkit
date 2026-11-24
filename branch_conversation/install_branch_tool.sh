#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:${HOME}/.local/bin:${PATH:-/usr/bin:/bin}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRANCH_DIR="${HOME}/mcp-gui-workspace/antigravity-branch"
SKILL_DIR="${HOME}/.gemini/config/skills/branch-conversation"

if ! command -v python3 >/dev/null 2>&1; then
  if [ "$(uname -s)" = "Darwin" ]; then
    echo "[!] python3 was not found. Please install via: brew install python@3.12 python-tk@3.12" >&2
  else
    echo "[!] python3 was not found. Please install via: sudo apt-get install -y python3 python3-tk" >&2
  fi
  exit 1
fi

# Ensure tkinter (and X11 auto-open helpers on Linux) are available on GUI sessions (skip on Headless SSH)
if [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ] || [ "$(uname -s)" = "Darwin" ]; then
  if [ "$(uname -s)" = "Darwin" ]; then
    if ! python3 -c "import tkinter" >/dev/null 2>&1; then
      echo "[Tip] Run 'brew install python-tk' if you want to open the visual --gui window (CLI & AI skill work out of the box)."
    fi
  elif command -v apt-get >/dev/null 2>&1; then
    MISSING_PKGS=()
    python3 -c "import tkinter" >/dev/null 2>&1 || MISSING_PKGS+=("python3-tk")
    if [ -n "${DISPLAY:-}" ]; then
      command -v xdotool >/dev/null 2>&1 || MISSING_PKGS+=("xdotool")
      command -v xclip >/dev/null 2>&1 || MISSING_PKGS+=("xclip")
    fi
    if [ "${#MISSING_PKGS[@]}" -gt 0 ]; then
      echo "Installing Linux GUI / auto-open helpers (${MISSING_PKGS[*]})..."
      sudo apt-get update -qq && sudo apt-get install -y -qq "${MISSING_PKGS[@]}" || \
        echo "[Tip] Run 'sudo apt-get install -y ${MISSING_PKGS[*]}' later for visual --gui & X11 auto-open."
    fi
  elif ! python3 -c "import tkinter" >/dev/null 2>&1; then
    echo "[Tip] Install python3-tk / python3-tkinter via your package manager to enable the visual --gui window."
  fi
fi

mkdir -p "$BRANCH_DIR" "$SKILL_DIR"

SRC_PY="${SCRIPT_DIR}/branch_conversation.py"
DST_PY="${BRANCH_DIR}/branch_conversation.py"
if [ ! "$SRC_PY" -ef "$DST_PY" ]; then
  cp -f "$SRC_PY" "$DST_PY"
fi
chmod +x "$DST_PY"

SRC_SHARE_PY="${SCRIPT_DIR}/share_conversation.py"
DST_SHARE_PY="${BRANCH_DIR}/share_conversation.py"
if [ -f "$SRC_SHARE_PY" ]; then
  if [ ! "$SRC_SHARE_PY" -ef "$DST_SHARE_PY" ]; then
    cp -f "$SRC_SHARE_PY" "$DST_SHARE_PY"
  fi
  chmod +x "$DST_SHARE_PY"
fi

SRC_SKILL="${SCRIPT_DIR}/SKILL.md"
DST_SKILL="${SKILL_DIR}/SKILL.md"
if [ ! "$SRC_SKILL" -ef "$DST_SKILL" ]; then
  cp -f "$SRC_SKILL" "$DST_SKILL"
fi

echo "Antigravity Conversation Brancher, Cross-User Sharer & Global Skill installed successfully (App + IDE + agy CLI)!"
echo " - Branch tool: ${DST_PY}"
echo " - Share tool : ${DST_SHARE_PY}"
echo " - Skill path : ${DST_SKILL}"
echo " - GUI launch : python3 \"${DST_PY}\" --gui"
echo " - Chat usage : Ask Antigravity '把当前对话分支一份' or '把当前对话导出为 .agyshare 发给同事'"
