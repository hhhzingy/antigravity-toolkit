#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${HOME}/mcp-gui-workspace"

# 1. Remove only computer_use MCP entries from mcp_config.json & agy CLI settings.json
if command -v python3 >/dev/null 2>&1; then
  for cfg in \
    "${HOME}/.gemini/config/mcp_config.json" \
    "${HOME}/.gemini/antigravity/mcp_config.json" \
    "${HOME}/.gemini/antigravity-cli/settings.json"; do
    if [[ -f "${cfg}" ]]; then
      python3 - "${cfg}" <<'PY' || true
import json, sys
from pathlib import Path

p = Path(sys.argv[1])
try:
    data = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

if isinstance(data, dict) and isinstance(data.get("mcpServers"), dict):
    changed = False
    for k in ("chrome-devtools", "linux-uia-mcp", "linux-ocr-mcp", "macos-uia-mcp", "macos-ocr-mcp"):
        if k in data["mcpServers"]:
            del data["mcpServers"][k]
            changed = True
    if changed:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
    fi
  done
fi

# 2. Stop running Linux / macOS desktop/OCR MCP processes
pkill -f "linux_gui_mcp" 2>/dev/null || true
pkill -f "macos_gui_mcp" 2>/dev/null || true
pkill -f "computer-control-mcp" 2>/dev/null || true
pkill -f "chrome-devtools-launcher" 2>/dev/null || true

# 3. Remove rules deployed by computer_use (preserve custom GEMINI.md if modified by user)
rm -f "${HOME}/.gemini/config/rules/gui-control.md"
for tpl in "${SCRIPT_DIR}/configs/rules_linux.md" "${SCRIPT_DIR}/configs/rules-macos.md"; do
  if [[ -f "${HOME}/.gemini/config/GEMINI.md" && -f "${tpl}" ]]; then
    if cmp -s "${HOME}/.gemini/config/GEMINI.md" "${tpl}"; then
      rm -f "${HOME}/.gemini/config/GEMINI.md"
    fi
  fi
done

# 4. Remove computer_use engine directories & config (keep close_guard / branch_conversation intact!)
rm -rf \
  "${WORKSPACE_DIR}/linux-gui-mcp" \
  "${WORKSPACE_DIR}/macos-gui-mcp" \
  "${WORKSPACE_DIR}/computer-control-mcp" \
  "${WORKSPACE_DIR}/chrome-devtools-launcher.py" \
  "${WORKSPACE_DIR}/.agents" \
  "${WORKSPACE_DIR}/README_DEV.md" \
  "${HOME}/.linux-mcp" \
  "${HOME}/.macos-mcp"

if [[ -d "${WORKSPACE_DIR}" ]] && [[ -z "$(ls -A "${WORKSPACE_DIR}" 2>/dev/null)" ]]; then
  rmdir "${WORKSPACE_DIR}" 2>/dev/null || true
fi

echo "Antigravity Faster Desktop & Browser Control (computer_use) uninstalled cleanly (other MCP servers and toolkit modules remain untouched)."
