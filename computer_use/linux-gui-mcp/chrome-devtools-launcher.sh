#!/usr/bin/env bash
# Smart Linux launcher for chrome-devtools-mcp:
# 1. Connects via --autoConnect when Google Chrome remote debugging (DevToolsActivePort) is active.
# 2. Connects via --wsEndpoint when Microsoft Edge / Chromium remote debugging (DevToolsActivePort) is active.
# 3. Connects via --browserUrl http://127.0.0.1:9222 if a port-9222 debug browser is listening.
# 4. Otherwise launches / auto-connects cleanly without mixing mutually exclusive flags.
set -euo pipefail

export PATH="${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

BIN="${CHROME_DEVTOOLS_MCP_BIN:-}"
if [ -z "$BIN" ] || [ ! -x "$BIN" ]; then
  if [ -x "/usr/local/bin/chrome-devtools-mcp" ]; then
    BIN="/usr/local/bin/chrome-devtools-mcp"
  else
    BIN="$(command -v chrome-devtools-mcp || true)"
  fi
fi

if [ -z "$BIN" ] || [ ! -x "$BIN" ]; then
  echo "Error: chrome-devtools-mcp binary not found. Please run: npm install -g chrome-devtools-mcp@latest" >&2
  exit 1
fi

check_port_open() {
  local port="$1"
  python3 -c "import socket, sys; s = socket.socket(); s.settimeout(0.25); sys.exit(0 if s.connect_ex(('127.0.0.1', int('$port'))) == 0 else 1)" 2>/dev/null
}

# 1. Google Chrome DevToolsActivePort -> native --autoConnect
CHROME_PORT_FILE="${HOME}/.config/google-chrome/DevToolsActivePort"
if [ -f "$CHROME_PORT_FILE" ]; then
  PORT="$(sed -n '1p' "$CHROME_PORT_FILE" | tr -d '\r\n')"
  if [ -n "$PORT" ] && check_port_open "$PORT"; then
    exec "$BIN" --autoConnect --no-usage-statistics "$@"
  fi
fi

# 2. Microsoft Edge or Chromium DevToolsActivePort -> --wsEndpoint
for ALT_PORT_FILE in \
  "${HOME}/.config/microsoft-edge/DevToolsActivePort" \
  "${HOME}/.config/chromium/DevToolsActivePort" \
  "${HOME}/snap/chromium/common/chromium/DevToolsActivePort"; do
  if [ -f "$ALT_PORT_FILE" ]; then
    PORT="$(sed -n '1p' "$ALT_PORT_FILE" | tr -d '\r\n')"
    WS_PATH="$(sed -n '2p' "$ALT_PORT_FILE" | tr -d '\r\n')"
    if [ -n "$PORT" ] && [ -n "$WS_PATH" ] && check_port_open "$PORT"; then
      exec "$BIN" --wsEndpoint "ws://127.0.0.1:${PORT}${WS_PATH}" --no-usage-statistics "$@"
    fi
  fi
done

# 3. Classic port 9222 remote debugging
if check_port_open 9222; then
  exec "$BIN" --browserUrl "http://127.0.0.1:9222" --no-usage-statistics "$@"
fi

# 4. Fallback: if Google Chrome is installed use --autoConnect, else point --executablePath to Edge/Chromium
if command -v google-chrome >/dev/null 2>&1 || command -v google-chrome-stable >/dev/null 2>&1; then
  exec "$BIN" --autoConnect --no-usage-statistics "$@"
elif command -v microsoft-edge >/dev/null 2>&1; then
  exec "$BIN" --executablePath "$(command -v microsoft-edge)" --no-usage-statistics "$@"
elif command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1; then
  CHROME_ALT="$(command -v chromium || command -v chromium-browser)"
  exec "$BIN" --executablePath "$CHROME_ALT" --no-usage-statistics "$@"
else
  exec "$BIN" --autoConnect --no-usage-statistics "$@"
fi
