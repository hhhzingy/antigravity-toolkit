#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:${HOME}/.local/bin:${PATH:-/usr/bin:/bin}"

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

echo "=== [0/5] Running macOS environment pre-flight checks ==="
if [ "$(uname -s)" != "Darwin" ]; then
  fail_friendly "macOS (Darwin)" "setup_macos.sh is designed for macOS 13+ (Apple Silicon & Intel)." "Use setup_linux.sh on Linux or setup_other_device.ps1 on Windows."
fi

if ! command -v git >/dev/null 2>&1; then
  fail_friendly "Git (Xcode Command Line Tools)" "Clones and patches local OCR & MCP engines." "Run: xcode-select --install  (or: brew install git)"
fi

PY_BIN=""
for cand in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
      PY_BIN="$(command -v "$cand")"
      break
    fi
  fi
done

if [ -z "${PY_BIN}" ]; then
  if command -v brew >/dev/null 2>&1; then
    echo "  Installing Python 3.12 via Homebrew..."
    brew install python@3.12 python-tk@3.12
    PY_BIN="$(command -v python3)"
  else
    fail_friendly "Python 3.10+" "macOS system Python (3.9) is older than 3.10 required by FastMCP." "Install Homebrew (https://brew.sh) and run: brew install python@3.12 python-tk@3.12"
  fi
fi

echo "  [OK] python3 : ${PY_BIN}"
echo "  [OK] git     : $(command -v git)"

mkdir -p "${WORKSPACE_DIR}"

if ! command -v uv >/dev/null 2>&1; then
  echo "  Installing 'uv' fast Python environment manager..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:${PATH}"
fi
UV_BIN="$(command -v uv || echo "${HOME}/.local/bin/uv")"
if [ ! -x "${UV_BIN}" ]; then
  fail_friendly "uv" "Manages isolated Python environments for macos-gui-mcp and computer-control-mcp." "Run: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi
echo "  [OK] uv      : ${UV_BIN}"

echo "=== [1/5] Deploying Engine 1: macos-gui-mcp (macos-uia-mcp) ==="
MAC_MCP_DST="${WORKSPACE_DIR}/macos-gui-mcp"
mkdir -p "${MAC_MCP_DST}"
cp -rf "${SCRIPT_DIR}/macos-gui-mcp/"* "${MAC_MCP_DST}/"

pushd "${MAC_MCP_DST}" >/dev/null
if [ ! -x .venv/bin/python ]; then
  "${UV_BIN}" venv --python "${PY_BIN}" .venv
fi
"${UV_BIN}" pip install --python .venv/bin/python -e .
popd >/dev/null

mkdir -p "${HOME}/.macos-mcp"
cp -f "${SCRIPT_DIR}/configs/macos-mcp-config.toml" "${HOME}/.macos-mcp/config.toml"

echo "=== [2/5] Deploying & patching Engine 2: computer-control-mcp (macos-ocr-mcp) ==="
OCR_MCP_DST="${WORKSPACE_DIR}/computer-control-mcp"
if [ ! -d "${OCR_MCP_DST}/.git" ]; then
  rm -rf "${OCR_MCP_DST}"
  git clone https://github.com/AB498/computer-control-mcp.git "${OCR_MCP_DST}"
fi
pushd "${OCR_MCP_DST}" >/dev/null
git checkout -- .
git apply --ignore-space-change --ignore-whitespace "${SCRIPT_DIR}/computer-control-mcp-opti.patch"
if [ ! -x .venv/bin/python ]; then
  "${UV_BIN}" venv --python "${PY_BIN}" .venv
fi
"${UV_BIN}" pip install --python .venv/bin/python -e .
popd >/dev/null

echo "=== [3/5] Installing Node.js 20+ & Engine 0: chrome-devtools-mcp ==="
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    brew install node
  else
    fail_friendly "Node.js 20+ & npm" "Runs chrome-devtools-mcp to connect to Chrome/Edge/Arc/Brave." "Run: brew install node  (or install LTS from https://nodejs.org)"
  fi
fi

if ! command -v chrome-devtools-mcp >/dev/null 2>&1; then
  npm install -g chrome-devtools-mcp@latest
fi
CHROME_MCP_BIN="$(command -v chrome-devtools-mcp || echo "/opt/homebrew/bin/chrome-devtools-mcp")"

echo "=== [4/5] Deploying cross-platform browser launcher & MCP configs (App + IDE + agy CLI) ==="
cp -f "${SCRIPT_DIR}/chrome-devtools-launcher.py" "${WORKSPACE_DIR}/chrome-devtools-launcher.py"
chmod +x "${WORKSPACE_DIR}/chrome-devtools-launcher.py"

"${PY_BIN}" - "${PY_BIN}" "${CHROME_MCP_BIN}" "${UV_BIN}" "${HOME}" <<'PY'
import json, shutil, sys
from pathlib import Path

py_bin, cdp_bin, uv_bin, home_str = sys.argv[1:5]
home = Path(home_str)

mcp_entries = {
    "chrome-devtools": {
        "command": py_bin,
        "args": ["-B", f"{home_str}/mcp-gui-workspace/chrome-devtools-launcher.py"],
        "env": {"CHROME_DEVTOOLS_MCP_BIN": cdp_bin, "PYTHONIOENCODING": "utf-8"},
    },
    "macos-uia-mcp": {
        "command": uv_bin,
        "args": ["--directory", f"{home_str}/mcp-gui-workspace/macos-gui-mcp", "run", "macos-gui-mcp"],
        "env": {"PYTHONIOENCODING": "utf-8"},
    },
    "macos-ocr-mcp": {
        "command": uv_bin,
        "args": ["--directory", f"{home_str}/mcp-gui-workspace/computer-control-mcp", "run", "computer-control-mcp"],
        "env": {"PYTHONIOENCODING": "utf-8"},
    },
}

targets = [
    home / ".gemini" / "config" / "mcp_config.json",
    home / ".gemini" / "antigravity" / "mcp_config.json",
]
cli_dir = home / ".gemini" / "antigravity-cli"
if cli_dir.is_dir() or shutil.which("agy") or Path("/opt/homebrew/bin/agy").is_file() or Path("/usr/local/bin/agy").is_file():
    targets.append(cli_dir / "settings.json")

for cfg_path in targets:
    data = {}
    if cfg_path.is_file() and cfg_path.stat().st_size > 0:
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}
    servers = data.setdefault("mcpServers", {})
    servers.update(mcp_entries)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  Updated: {cfg_path}")
PY

echo "=== [5/5] Installing macOS routing rules ==="
mkdir -p "${HOME}/.gemini/config/rules" "${WORKSPACE_DIR}/.agents/rules"
cp -f "${SCRIPT_DIR}/configs/rules-macos.md" "${HOME}/.gemini/config/rules/gui-control.md"
if [ ! -f "${HOME}/.gemini/config/GEMINI.md" ]; then
  cp -f "${SCRIPT_DIR}/configs/rules-macos.md" "${HOME}/.gemini/config/GEMINI.md"
fi
cp -f "${SCRIPT_DIR}/configs/rules-macos.md" "${WORKSPACE_DIR}/.agents/rules/gui-control.md"
cp -f "${SCRIPT_DIR}/README_DEV.md" "${WORKSPACE_DIR}/README_DEV.md"

echo ""
echo "All done on macOS! Quick finish steps:"
echo "  1. In Chrome (chrome://inspect/#remote-debugging) or Edge (edge://inspect/#remote-debugging), check 'Enable remote debugging'."
echo "  2. Refresh MCP Servers in Antigravity (or run '/mcp' inside 'agy' CLI)."
echo "  3. When first using desktop clicking/screenshots, allow Accessibility & Screen Recording in System Settings -> Privacy & Security."
