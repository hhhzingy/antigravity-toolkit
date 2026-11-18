#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Cross-Platform Launcher for chrome-devtools-mcp (Win / macOS / Linux / Headless)
--------------------------------------------------------------------------------------
Automatically inspects `DevToolsActivePort` across Chrome, Microsoft Edge, Brave, Arc,
and Chromium on Windows, macOS, and Linux:
- Picks whichever active listening browser updated `DevToolsActivePort` most recently:
  * Chrome -> `--autoConnect`
  * Edge / Brave / Arc / Chromium -> `--wsEndpoint ws://127.0.0.1:<port><ws_path>`
- On Headless Linux (e.g., `agy` CLI over SSH without `$DISPLAY` or `$WAYLAND_DISPLAY`)
  when no remote-debugging port is open, automatically appends `--headless` so browser
  automation works cleanly on servers without X11.
- On Windows, binds the child process tree (`cmd.exe` -> `node.exe`) to a Job Object
  with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` so zero orphan `node.exe` remain on exit.
- On macOS / Linux, uses `os.execvp` to replace the wrapper process cleanly.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys

_JOB_HANDLE: int | None = None


def _bind_kill_on_close_job(proc: subprocess.Popen) -> None:
    """Attach `proc` to a Win32 Job Object so `cmd.exe`/`node.exe` die with this wrapper."""
    global _JOB_HANDLE
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        k32 = ctypes.windll.kernel32
        k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        k32.SetInformationJobObject.restype = wintypes.BOOL
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k32.AssignProcessToJobObject.restype = wintypes.BOOL

        hjob = k32.CreateJobObjectW(None, None)
        if not hjob:
            return

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if k32.SetInformationJobObject(hjob, 9, ctypes.byref(info), ctypes.sizeof(info)):
            if k32.AssignProcessToJobObject(hjob, wintypes.HANDLE(int(proc._handle))):
                _JOB_HANDLE = int(hjob)
                return

        k32.CloseHandle(hjob)
    except Exception:
        pass


def _is_port_listening(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.25)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


def _read_active_port(port_file: Path) -> tuple[int, str, float] | None:
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
            return port, ws_path, port_file.stat().st_mtime
    except Exception:
        pass
    return None


def _resolve_chrome_mcp_bin() -> str:
    env_bin = os.environ.get("CHROME_DEVTOOLS_MCP_BIN", "").strip()
    if env_bin and Path(env_bin).is_file():
        return env_bin
    names = ("chrome-devtools-mcp.cmd", "chrome-devtools-mcp") if sys.platform == "win32" else ("chrome-devtools-mcp",)
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            fallback = Path(appdata) / "npm" / "chrome-devtools-mcp.cmd"
            if fallback.is_file():
                return str(fallback)
    elif sys.platform == "darwin":
        for p in (Path("/opt/homebrew/bin/chrome-devtools-mcp"), Path("/usr/local/bin/chrome-devtools-mcp")):
            if p.is_file():
                return str(p)
    else:
        for p in (Path("/usr/local/bin/chrome-devtools-mcp"), Path.home() / ".local" / "bin" / "chrome-devtools-mcp"):
            if p.is_file():
                return str(p)
    return "chrome-devtools-mcp"


def _candidate_port_files() -> list[tuple[bool, Path]]:
    """Return list of (is_google_chrome, DevToolsActivePort_path)."""
    home = Path.home()
    if sys.platform == "win32":
        local_ad = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        return [
            (True, local_ad / "Google" / "Chrome" / "User Data" / "DevToolsActivePort"),
            (False, local_ad / "Microsoft" / "Edge" / "User Data" / "DevToolsActivePort"),
            (False, local_ad / "BraveSoftware" / "Brave-Browser" / "User Data" / "DevToolsActivePort"),
            (False, local_ad / "Chromium" / "User Data" / "DevToolsActivePort"),
        ]
    if sys.platform == "darwin":
        app_sup = home / "Library" / "Application Support"
        return [
            (True, app_sup / "Google" / "Chrome" / "DevToolsActivePort"),
            (True, app_sup / "Google" / "Chrome Canary" / "DevToolsActivePort"),
            (False, app_sup / "Microsoft Edge" / "DevToolsActivePort"),
            (False, app_sup / "BraveSoftware" / "Brave-Browser" / "DevToolsActivePort"),
            (False, app_sup / "Arc" / "User Data" / "DevToolsActivePort"),
            (False, app_sup / "Chromium" / "DevToolsActivePort"),
        ]
    return [
        (True, home / ".config" / "google-chrome" / "DevToolsActivePort"),
        (False, home / ".config" / "microsoft-edge" / "DevToolsActivePort"),
        (False, home / ".config" / "BraveSoftware" / "Brave-Browser" / "DevToolsActivePort"),
        (False, home / ".config" / "chromium" / "DevToolsActivePort"),
        (False, home / "snap" / "chromium" / "common" / "chromium" / "DevToolsActivePort"),
    ]


def main() -> int:
    mcp_bin = _resolve_chrome_mcp_bin()
    extra_args = [a for a in sys.argv[1:] if a not in ("--autoConnect", "--auto-connect")]

    active_matches: list[tuple[float, bool, int, str]] = []
    for is_chrome, pfile in _candidate_port_files():
        info = _read_active_port(pfile)
        if info is not None:
            port, ws_path, mtime = info
            active_matches.append((mtime, is_chrome, port, ws_path))

    is_linux_headless = (
        sys.platform.startswith("linux")
        and not os.environ.get("DISPLAY")
        and not os.environ.get("WAYLAND_DISPLAY")
    )

    if active_matches:
        active_matches.sort(key=lambda item: item[0], reverse=True)
        _, is_chrome, port, ws_path = active_matches[0]
        if is_chrome and sys.platform != "darwin":
            cmd = [mcp_bin, "--autoConnect", "--no-usage-statistics", *extra_args]
        else:
            cmd = [mcp_bin, "--wsEndpoint", f"ws://127.0.0.1:{port}{ws_path}", "--no-usage-statistics", *extra_args]
    elif is_linux_headless and "--headless" not in extra_args:
        cmd = [mcp_bin, "--headless", "--no-usage-statistics", *extra_args]
    else:
        cmd = [mcp_bin, "--autoConnect", "--no-usage-statistics", *extra_args]

    if sys.platform != "win32":
        os.execvp(cmd[0], cmd)

    proc = subprocess.Popen(cmd)
    _bind_kill_on_close_job(proc)

    def _forward_stop(_signum: int, _frame: object) -> None:
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                signal.signal(sig, _forward_stop)
            except Exception:
                pass

    try:
        return proc.wait()
    except KeyboardInterrupt:
        if proc.poll() is None:
            proc.terminate()
        return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
