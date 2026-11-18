#!/usr/bin/env bash
set -euo pipefail

PLIST_FILE="${HOME}/Library/LaunchAgents/com.antigravity.close-guard.plist"
TARGET_DIR="${HOME}/mcp-gui-workspace/antigravity-close-guard"

launchctl unload "${PLIST_FILE}" >/dev/null 2>&1 || true
rm -f "${PLIST_FILE}" "${HOME}/.local/bin/agy-guard"
pkill -f "antigravity_close_guard_macos.py" 2>/dev/null || true
rm -rf "${TARGET_DIR}"

echo "Antigravity Close Guard (macOS) uninstalled cleanly."
