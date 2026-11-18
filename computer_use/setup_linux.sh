#!/usr/bin/env bash
set -euo pipefail

export PATH="${HOME}/.local/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${HOME}/mcp-gui-workspace"

fail_friendly() {
  local missing="$1"
  local why="$2"
  local fix="$3"
  echo "" >&2
  echo "[!] Missing prerequisite: ${missing}" >&2
  echo "    Why needed : ${why}" >&2
  echo "    How to fix : ${fix}" >&2
  echo "" >&2
  exit 1
}

echo "=== [0/5] Running Linux environment pre-flight checks ==="
if [ "$(uname -s)" != "Linux" ]; then
  fail_friendly "Linux OS" "setup_linux.sh is designed for Ubuntu / Debian Linux (X11)." "On Windows, please run setup_other_device.ps1 instead."
fi

if [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
  echo "  [Note] Wayland session detected. Browser control works anywhere, while full desktop clicking & mouse-shake guard work best under 'Ubuntu on Xorg' (selectable via the gear icon on the login screen)."
fi

echo "=== [1/5] Checking & installing X11 + AT-SPI2 system dependencies ==="
if command -v apt-get >/dev/null 2>&1 && command -v dpkg >/dev/null 2>&1; then
  MISSING_PKGS=()
  for pkg in python3 python3-gi gir1.2-atspi-2.0 python3-xlib python3-tk xdotool wmctrl xclip scrot curl xz-utils git; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
      MISSING_PKGS+=("$pkg")
    fi
  done
  if [ "${#MISSING_PKGS[@]}" -gt 0 ]; then
    if ! command -v sudo >/dev/null 2>&1 && [ "$(id -u)" -ne 0 ]; then
      fail_friendly "sudo (or root privileges)" "Needed to install missing system packages: ${MISSING_PKGS[*]}" "Run as root or install sudo, then re-run this script."
    fi
    echo "  Installing missing packages via apt: ${MISSING_PKGS[*]}"
    if [ "$(id -u)" -eq 0 ]; then
      apt-get update -qq
      apt-get install -y -qq "${MISSING_PKGS[@]}"
    else
      sudo apt-get update -qq
      sudo apt-get install -y -qq "${MISSING_PKGS[@]}"
    fi
  fi
else
  for cmd in git python3 curl xdotool wmctrl xclip; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      fail_friendly "$cmd" "Required for Linux desktop & browser MCP setup." "Please install '$cmd' (plus python3-gobject / at-spi2-core / python3-xlib) using your distro's package manager."
    fi
  done
fi

if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
  fail_friendly "Python 3.10+" "Required by FastMCP, linux-gui-mcp, and computer-control-mcp." "Please install Python 3.10 or newer (e.g., Ubuntu 22.04+ includes Python 3.10+)."
fi
echo "  [OK] python3 : $(command -v python3)"
echo "  [OK] git     : $(command -v git)"

mkdir -p "${WORKSPACE_DIR}"

if ! command -v uv >/dev/null 2>&1; then
  echo "  Installing 'uv' fast Python environment manager..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:/usr/local/bin:${PATH}"
fi

if [ -x "${HOME}/.local/bin/uv" ] && [ ! -x /usr/local/bin/uv ] && command -v sudo >/dev/null 2>&1; then
  sudo ln -sf "${HOME}/.local/bin/uv" /usr/local/bin/uv 2>/dev/null || true
fi

UV_BIN="$(command -v uv || true)"
if [ -z "$UV_BIN" ] && [ -x "${HOME}/.local/bin/uv" ]; then
  UV_BIN="${HOME}/.local/bin/uv"
fi
if [ -z "$UV_BIN" ] || [ ! -x "$UV_BIN" ]; then
  fail_friendly "uv (Python package manager)" "Manages virtual environments for linux-gui-mcp and computer-control-mcp." "Run: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi
UV_RESOLVED="$(readlink -f "$UV_BIN" 2>/dev/null || echo "$UV_BIN")"
echo "  [OK] uv      : ${UV_RESOLVED}"

echo "=== [2/5] Deploying & optimizing Engine 1: linux-gui-mcp (linux-uia-mcp) ==="
LINUX_MCP_DST="${WORKSPACE_DIR}/linux-gui-mcp"
mkdir -p "${LINUX_MCP_DST}"
cp -rf "${SCRIPT_DIR}/linux-gui-mcp/"* "${LINUX_MCP_DST}/"
sed -i 's/\r$//' "${LINUX_MCP_DST}/chrome-devtools-launcher.sh"
chmod +x "${LINUX_MCP_DST}/chrome-devtools-launcher.sh"

pushd "${LINUX_MCP_DST}" >/dev/null
if [ ! -x .venv/bin/python ]; then
  "$UV_RESOLVED" venv --clear --python /usr/bin/python3 --system-site-packages .venv
fi
"$UV_RESOLVED" pip install --python .venv/bin/python -e .
popd >/dev/null

mkdir -p "${HOME}/.linux-mcp"
cp -f "${SCRIPT_DIR}/configs/linux-mcp-config.toml" "${HOME}/.linux-mcp/config.toml"

echo "=== [3/5] Deploying & patching Engine 2: computer-control-mcp (linux-ocr-mcp) ==="
OCR_MCP_DST="${WORKSPACE_DIR}/computer-control-mcp"
if [ ! -d "${OCR_MCP_DST}/.git" ]; then
  rm -rf "${OCR_MCP_DST}"
  if ! git clone https://github.com/AB498/computer-control-mcp.git "${OCR_MCP_DST}"; then
    fail_friendly "GitHub access (computer-control-mcp)" "Needed to clone the local RapidOCR engine." "Check your network connection and re-run ./setup_linux.sh"
  fi
fi
pushd "${OCR_MCP_DST}" >/dev/null
git checkout -- .
git apply --ignore-space-change --ignore-whitespace "${SCRIPT_DIR}/computer-control-mcp-opti.patch"
if [ ! -x .venv/bin/python ]; then
  "$UV_RESOLVED" venv --clear --python /usr/bin/python3 .venv
fi
"$UV_RESOLVED" pip install --python .venv/bin/python -e .
popd >/dev/null

echo "=== [4/5] Installing Node.js LTS & Engine 0: chrome-devtools-mcp ==="
NEED_NODE=0
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  NEED_NODE=1
else
  NODE_MAJOR="$(node -v | sed -E 's/^v([0-9]+).*/\1/')"
  if [ "${NODE_MAJOR:-0}" -lt 20 ]; then
    NEED_NODE=1
  fi
fi

if [ "$NEED_NODE" -eq 1 ]; then
  ARCH="$(uname -m)"
  if [ "$ARCH" = "aarch64" ]; then NODE_ARCH="arm64"; else NODE_ARCH="x64"; fi
  NODE_TAR="$(curl -fsSL https://nodejs.org/dist/latest-v22.x/ | grep -oE "node-v22\.[0-9]+\.[0-9]+-linux-${NODE_ARCH}\.tar\.xz" | head -n 1 || true)"
  if [ -z "$NODE_TAR" ]; then
    fail_friendly "Node.js 20+ & npm" "Could not auto-detect Node.js v22 archive from nodejs.org." "Install Node.js 20+ manually (https://nodejs.org/) and re-run ./setup_linux.sh"
  fi
  echo "  Installing ${NODE_TAR} to /usr/local..."
  curl -fsSL "https://nodejs.org/dist/latest-v22.x/${NODE_TAR}" -o "/tmp/${NODE_TAR}"
  if [ "$(id -u)" -eq 0 ]; then
    tar -xJf "/tmp/${NODE_TAR}" -C /usr/local --strip-components=1
  else
    sudo tar -xJf "/tmp/${NODE_TAR}" -C /usr/local --strip-components=1
  fi
  rm -f "/tmp/${NODE_TAR}"
fi

if ! command -v chrome-devtools-mcp >/dev/null 2>&1; then
  NPM_PREFIX="$(npm config get prefix 2>/dev/null || echo "/usr/local")"
  if [ -w "$NPM_PREFIX" ] || [ "$(id -u)" -eq 0 ]; then
    npm install -g chrome-devtools-mcp@latest
  else
    sudo npm install -g chrome-devtools-mcp@latest
  fi
fi

CHROME_MCP_BIN="$(command -v chrome-devtools-mcp || echo "/usr/local/bin/chrome-devtools-mcp")"
NODE_BIN_DIR="$(dirname "$(command -v node)")"
UV_BIN_DIR="$(dirname "$UV_RESOLVED")"
GUI_PATH="${NODE_BIN_DIR}:${UV_BIN_DIR}:${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin"

echo "=== [5/5] Writing Antigravity MCP config & global/workspace rules ==="
DISPLAY_VAL="${DISPLAY:-:0}"

for TARGET_CFG in \
  "${HOME}/.gemini/config/mcp_config.json" \
  "${HOME}/.gemini/antigravity/mcp_config.json"; do
  mkdir -p "$(dirname "$TARGET_CFG")"
  python3 -B - "$TARGET_CFG" "$WORKSPACE_DIR" "$UV_RESOLVED" "$CHROME_MCP_BIN" "$GUI_PATH" "$DISPLAY_VAL" <<'PY'
import json, sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
ws_dir = sys.argv[2]
uv_bin = sys.argv[3]
chrome_mcp_bin = sys.argv[4]
gui_path = sys.argv[5]
disp = sys.argv[6]

data = {}
if cfg_path.exists() and cfg_path.stat().st_size > 0:
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        data = {}

if not isinstance(data, dict):
    data = {}
servers = data.setdefault("mcpServers", {})
servers["chrome-devtools"] = {
    "command": f"{ws_dir}/linux-gui-mcp/chrome-devtools-launcher.sh",
    "args": [],
    "env": {
        "CHROME_DEVTOOLS_MCP_BIN": chrome_mcp_bin,
        "PATH": gui_path,
    },
}
servers["linux-uia-mcp"] = {
    "command": f"{ws_dir}/linux-gui-mcp/.venv/bin/linux-gui-mcp",
    "args": [],
    "env": {
        "PYTHONIOENCODING": "utf-8",
        "DISPLAY": disp,
        "UV_BIN": uv_bin,
        "PATH": gui_path,
    },
}
servers["linux-ocr-mcp"] = {
    "command": f"{ws_dir}/computer-control-mcp/.venv/bin/computer-control-mcp",
    "args": [],
    "env": {
        "PYTHONIOENCODING": "utf-8",
        "DISPLAY": disp,
        "UV_BIN": uv_bin,
        "PATH": gui_path,
    },
}
cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"  Updated: {cfg_path}")
PY
done

mkdir -p "${HOME}/.gemini/config/rules" "${WORKSPACE_DIR}/.agents/rules"
if [ ! -f "${HOME}/.gemini/config/GEMINI.md" ]; then
  cp -f "${SCRIPT_DIR}/configs/rules_linux.md" "${HOME}/.gemini/config/GEMINI.md"
fi
cp -f "${SCRIPT_DIR}/configs/rules_linux.md" "${HOME}/.gemini/config/rules/gui-control.md"
cp -f "${SCRIPT_DIR}/configs/rules_linux.md" "${WORKSPACE_DIR}/.agents/rules.md"
cp -f "${SCRIPT_DIR}/configs/rules_linux.md" "${WORKSPACE_DIR}/.agents/rules/gui-control.md"
cp -f "${SCRIPT_DIR}/README_DEV.md" "${WORKSPACE_DIR}/README_DEV.md"

echo ""
echo "All done! Two quick steps to finish:"
echo "  1. Open Chrome (chrome://inspect/#remote-debugging) or Edge (edge://inspect/#remote-debugging) -> check 'Enable remote debugging'."
echo "  2. In Antigravity -> '...' (Additional Options) -> MCP Servers -> click 'Refresh'."
