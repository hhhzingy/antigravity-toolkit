#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRANCH_DIR="${HOME}/mcp-gui-workspace/antigravity-branch"
SKILL_DIR="${HOME}/.gemini/config/skills/branch-conversation"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[!] python3 was not found. Please install Python 3 first (e.g., sudo apt-get install -y python3 python3-tk)." >&2
  exit 1
fi

# Ensure python3-tk is available for --gui mode on Debian/Ubuntu if possible
if ! python3 -c "import tkinter" >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    echo "Installing python3-tk for the visual conversation branching window..."
    sudo apt-get update -qq && sudo apt-get install -y -qq python3-tk || \
      echo "[Tip] Run 'sudo apt-get install -y python3-tk' later if you want to open the visual --gui window."
  else
    echo "[Tip] Install python3-tk / python3-tkinter via your package manager to enable the visual --gui window."
  fi
fi

mkdir -p "$BRANCH_DIR" "$SKILL_DIR"

SRC_PY="${SCRIPT_DIR}/branch_conversation.py"
DST_PY="${BRANCH_DIR}/branch_conversation.py"
if [ "$(realpath "$SRC_PY")" != "$(realpath -m "$DST_PY")" ]; then
  cp -f "$SRC_PY" "$DST_PY"
fi
chmod +x "$DST_PY"

SRC_SKILL="${SCRIPT_DIR}/SKILL.md"
DST_SKILL="${SKILL_DIR}/SKILL.md"
if [ "$(realpath "$SRC_SKILL")" != "$(realpath -m "$DST_SKILL")" ]; then
  cp -f "$SRC_SKILL" "$DST_SKILL"
fi

echo "Antigravity Conversation Brancher & Global Skill installed successfully!"
echo " - Tool path : ${DST_PY}"
echo " - Skill path: ${DST_SKILL}"
echo " - GUI launch: python3 \"${DST_PY}\" --gui  (or click '分支克隆对话 (Branch)...' in the tray menu)"
echo " - Chat usage: Ask Antigravity '把当前对话分支一份，忽略最后一条消息'"
