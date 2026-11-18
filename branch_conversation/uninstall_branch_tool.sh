#!/usr/bin/env bash
set -euo pipefail

BRANCH_DIR="${HOME}/mcp-gui-workspace/antigravity-branch"
SKILL_DIR="${HOME}/.gemini/config/skills/branch-conversation"

rm -rf "${BRANCH_DIR}" "${SKILL_DIR}"

echo "Antigravity Conversation Brancher & Global Skill uninstalled cleanly (existing branched conversations remain untouched)."
