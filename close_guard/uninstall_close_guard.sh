#!/usr/bin/env bash
set -euo pipefail

if [ "$(uname -s)" = "Darwin" ]; then
  exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/uninstall_close_guard_macos.sh"
fi

SERVICE_NAME="antigravity-close-guard.service"
SYSTEMD_FILE="${HOME}/.config/systemd/user/${SERVICE_NAME}"
AUTOSTART_FILE="${HOME}/.config/autostart/antigravity-close-guard.desktop"
TARGET_DIR="${HOME}/mcp-gui-workspace/antigravity-close-guard"

echo "Stopping and disabling ${SERVICE_NAME}..."
systemctl --user disable --now "${SERVICE_NAME}" 2>/dev/null || true
rm -f "${SYSTEMD_FILE}" "${AUTOSTART_FILE}" "${HOME}/.local/bin/agy-guard"
systemctl --user daemon-reload 2>/dev/null || true

pkill -f "antigravity_close_guard_linux.py" 2>/dev/null || true
rm -rf "${TARGET_DIR}"

echo "Antigravity Close Guard (Linux) uninstalled cleanly."
