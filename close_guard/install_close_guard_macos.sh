#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:${HOME}/.local/bin:${PATH:-/usr/bin:/bin}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${HOME}/mcp-gui-workspace/antigravity-close-guard"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_FILE="${LAUNCH_AGENTS_DIR}/com.antigravity.close-guard.plist"
LOCAL_BIN="${HOME}/.local/bin"

PY_BIN="$(command -v python3 || echo "/usr/bin/python3")"

mkdir -p "${TARGET_DIR}" "${LAUNCH_AGENTS_DIR}" "${LOCAL_BIN}"

SRC_PY="${SCRIPT_DIR}/antigravity_close_guard_macos.py"
DST_PY="${TARGET_DIR}/antigravity_close_guard_macos.py"
if [ ! "${SRC_PY}" -ef "${DST_PY}" ]; then
  cp -f "${SRC_PY}" "${DST_PY}"
fi
chmod +x "${DST_PY}"

# Deploy agy-guard persistent CLI wrapper
cp -f "${SCRIPT_DIR}/agy_guard_cli.sh" "${LOCAL_BIN}/agy-guard"
chmod +x "${LOCAL_BIN}/agy-guard"

"${PY_BIN}" "${DST_PY}" --self-test

cat > "${PLIST_FILE}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.antigravity.close-guard</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PY_BIN}</string>
        <string>${DST_PY}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF

launchctl unload "${PLIST_FILE}" >/dev/null 2>&1 || true
launchctl load -w "${PLIST_FILE}" >/dev/null 2>&1 || true

echo "Antigravity Close Guard (macOS + agy CLI) installed and enabled on login!"
echo " - Daemon script : ${DST_PY}"
echo " - CLI wrapper   : ${LOCAL_BIN}/agy-guard"
echo " - Usage         : Cmd+Q hides Antigravity safely to background; press Cmd+Option+Q (or run '${DST_PY} --quit') to exit completely."
echo " - Permission    : Grant Accessibility permission to Python/Terminal in System Settings -> Privacy & Security -> Accessibility if prompted."
