#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${HOME}/mcp-gui-workspace/antigravity-close-guard"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
AUTOSTART_DIR="${HOME}/.config/autostart"
LOCAL_BIN="${HOME}/.local/bin"
SERVICE_NAME="antigravity-close-guard.service"

mkdir -p "${LOCAL_BIN}"
cp -f "${SCRIPT_DIR}/agy_guard_cli.sh" "${LOCAL_BIN}/agy-guard"
chmod +x "${LOCAL_BIN}/agy-guard"

if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  echo "[Auto-Detect] Headless Linux / SSH terminal detected — installed '${LOCAL_BIN}/agy-guard' (tmux session wrapper for agy CLI)."
  echo " - Usage: Run 'agy-guard' instead of 'agy' so SSH disconnects or terminal closures never interrupt running tasks."
  exit 0
fi

PYTHON_BIN="/usr/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

echo "=== [1/4] Checking & installing system dependencies (Linux X11) ==="
if command -v dpkg >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
  MISSING_PKGS=()
  for pkg in python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 gir1.2-notify-0.7 python3-xlib; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
      MISSING_PKGS+=("$pkg")
    fi
  done

  if [ "${#MISSING_PKGS[@]}" -gt 0 ]; then
    echo "Installing missing packages: ${MISSING_PKGS[*]}"
    sudo apt-get update -qq
    sudo apt-get install -y -qq "${MISSING_PKGS[@]}"
  fi
fi

echo "=== [2/4] Deploying Antigravity Close Guard script ==="
mkdir -p "$TARGET_DIR" "$SYSTEMD_USER_DIR" "$AUTOSTART_DIR"
SRC_SCRIPT="${SCRIPT_DIR}/antigravity_close_guard_linux.py"
DST_SCRIPT="${TARGET_DIR}/antigravity_close_guard_linux.py"

if [ ! "$SRC_SCRIPT" -ef "$DST_SCRIPT" ]; then
  cp -f "$SRC_SCRIPT" "$DST_SCRIPT"
fi
chmod +x "$DST_SCRIPT"

echo "=== [3/4] Running X11 passive-grab self-test ==="
if [ -n "${DISPLAY:-}" ]; then
  "$PYTHON_BIN" "$DST_SCRIPT" --self-test
else
  echo "No active X11 DISPLAY detected in current shell; skipping live GUI self-test."
fi

echo "=== [4/4] Registering & starting systemd user service ==="
cat > "${SYSTEMD_USER_DIR}/${SERVICE_NAME}" <<EOF
[Unit]
Description=Antigravity Close Guard (Hide to System Tray on Close / Alt+F4 / Ctrl+Q)
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
ExecStart=${PYTHON_BIN} ${DST_SCRIPT}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target default.target
EOF

cat > "${AUTOSTART_DIR}/antigravity-close-guard.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Antigravity Close Guard
Comment=Intercept Antigravity close button and hide to system tray
Exec=/bin/systemctl --user start ${SERVICE_NAME}
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF

if systemctl --user daemon-reload >/dev/null 2>&1; then
  systemctl --user enable "${SERVICE_NAME}" >/dev/null 2>&1 || true
  if [ -n "${DISPLAY:-}" ]; then
    systemctl --user restart "${SERVICE_NAME}"
    sleep 1
    systemctl --user is-active "${SERVICE_NAME}"
  fi
fi

echo "Antigravity Close Guard (Linux + agy-guard CLI) installed, enabled on login, and ready!"
echo " - Script path : ${DST_SCRIPT}"
echo " - CLI wrapper : ${LOCAL_BIN}/agy-guard"
