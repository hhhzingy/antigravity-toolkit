#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Windows Launcher for chrome-devtools-mcp (Chrome + Microsoft Edge Auto-Detect)
------------------------------------------------------------------------------------
Automatically inspects `DevToolsActivePort` for both Google Chrome and Microsoft Edge:
- If Edge has remote debugging enabled (`edge://inspect/#remote-debugging`) and is
  listening locally, connects via `--wsEndpoint ws://127.0.0.1:<port><ws_path>`.
- If Chrome has remote debugging enabled (`chrome://inspect/#remote-debugging`) and is
  listening locally, connects via `--autoConnect` (or `--wsEndpoint` fallback).
- Otherwise falls back cleanly to `--autoConnect` so standard behavior is preserved.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys


def _is_port_listening(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.25)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


def _read_active_port(port_file: Path) -> tuple[int, str] | None:
    if not port_file.is_file():
        return None
    try:
        lines = [ln.strip() for ln in port_file.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
        if not lines:
            return None
        port = int(lines[0])
        ws_path = lines[1] if len(lines) >= 2 else "/devtools/browser"
        if not ws_path.startswith("/"):
            ws_path = "/" + ws_path
        if 1 <= port <= 65535 and _is_port_listening(port):
            return port, ws_path
    except Exception:
        pass
    return None


def _resolve_chrome_mcp_bin() -> str:
    env_bin = os.environ.get("CHROME_DEVTOOLS_MCP_BIN", "").strip()
    if env_bin and Path(env_bin).is_file():
        return env_bin
    for name in ("chrome-devtools-mcp.cmd", "chrome-devtools-mcp"):
        found = shutil.which(name)
        if found:
            return found
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        fallback = Path(appdata) / "npm" / "chrome-devtools-mcp.cmd"
        if fallback.is_file():
            return str(fallback)
    return "chrome-devtools-mcp"


def main() -> int:
    local_appdata = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    chrome_port_file = local_appdata / "Google" / "Chrome" / "User Data" / "DevToolsActivePort"
    edge_port_file = local_appdata / "Microsoft" / "Edge" / "User Data" / "DevToolsActivePort"

    chrome_info = _read_active_port(chrome_port_file)
    edge_info = _read_active_port(edge_port_file)

    mcp_bin = _resolve_chrome_mcp_bin()
    extra_args = [a for a in sys.argv[1:] if a not in ("--autoConnect", "--auto-connect")]

    if edge_info and not chrome_info:
        port, ws_path = edge_info
        cmd = [mcp_bin, "--wsEndpoint", f"ws://127.0.0.1:{port}{ws_path}", "--no-usage-statistics", *extra_args]
    elif edge_info and chrome_info:
        # Prefer whichever DevToolsActivePort file was updated more recently
        if edge_port_file.stat().st_mtime >= chrome_port_file.stat().st_mtime:
            port, ws_path = edge_info
            cmd = [mcp_bin, "--wsEndpoint", f"ws://127.0.0.1:{port}{ws_path}", "--no-usage-statistics", *extra_args]
        else:
            cmd = [mcp_bin, "--autoConnect", "--no-usage-statistics", *extra_args]
    else:
        cmd = [mcp_bin, "--autoConnect", "--no-usage-statistics", *extra_args]

    proc = subprocess.Popen(cmd)
    return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
