#!/usr/bin/env python3
"""
Antigravity Toolkit - Cross-Platform & Multi-Surface Health Checker (Doctor)

Uses Python standard library only. Safe to run on Windows, macOS, and Linux
(including Desktop X11/Wayland and Headless SSH servers), automatically detecting
Antigravity 2.0 App, Antigravity IDE, and Antigravity CLI (`agy`).

Usage:
    python scripts/doctor.py          # Friendly human-readable report
    python scripts/doctor.py --json   # Machine-readable JSON output (for AI Agents)
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def _configure_utf8_output() -> None:
    """Ensure UTF-8 output works cleanly on Windows consoles and redirected pipes."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    if IS_WINDOWS:
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
                return True
        except Exception:
            return bool(os.environ.get("WT_SESSION") or os.environ.get("TERM"))
    return True


class Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def cyan(self, text: str) -> str:
        return self._wrap("36", text)

    def green(self, text: str) -> str:
        return self._wrap("32", text)

    def yellow(self, text: str) -> str:
        return self._wrap("33", text)

    def red(self, text: str) -> str:
        return self._wrap("31", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)


def redact_home(raw_text: str) -> str:
    """Replace the current user's home path with '~' so output stays clean & privacy-safe."""
    if not raw_text:
        return raw_text
    home = str(Path.home())
    home_fwd = home.replace("\\", "/")
    result = raw_text.replace(home, "~").replace(home_fwd, "~")
    if IS_WINDOWS and home:
        pattern = re.compile(re.escape(home), re.IGNORECASE)
        result = pattern.sub("~", result)
        pattern_fwd = re.compile(re.escape(home_fwd), re.IGNORECASE)
        result = pattern_fwd.sub("~", result)
    return result


def display_path(path: Path) -> str:
    return redact_home(str(path)).replace("\\", "/")


def run_cmd_quiet(args: List[str], timeout: float = 4.0) -> Tuple[int, str]:
    """Run an external command safely and return (returncode, output)."""
    try:
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        output = (proc.stdout or "").strip()
        return proc.returncode, output
    except Exception as exc:
        return -1, str(exc)


def is_tcp_port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((host, port)) == 0
    except Exception:
        return False


def detect_session_environment() -> Tuple[str, bool]:
    """Return (session_mode, is_headless)."""
    if IS_WINDOWS:
        return "win32-desktop", False
    if IS_MACOS:
        return "macos-aqua", False
    if IS_LINUX:
        if os.environ.get("WAYLAND_DISPLAY"):
            return "linux-wayland", False
        if os.environ.get("DISPLAY"):
            return "linux-x11", False
        return "linux-headless", True
    return "unknown", False


def detect_antigravity_surfaces() -> Dict[str, Any]:
    """Auto-detect installed Antigravity editions: App 2.0, Antigravity IDE, and `agy` CLI."""
    home = Path.home()

    # 1. Detect `agy` CLI
    agy_cli_bin: Optional[str] = None
    cli_names = ("agy.exe", "agy.cmd", "agy") if IS_WINDOWS else ("agy",)
    for cname in cli_names:
        found = shutil.which(cname)
        if found:
            agy_cli_bin = found
            break
    if not agy_cli_bin:
        extra_cli_paths = [
            home / ".local" / "bin" / ("agy.exe" if IS_WINDOWS else "agy"),
            home / ".gemini" / "antigravity-cli" / "bin" / ("agy.exe" if IS_WINDOWS else "agy"),
        ]
        if IS_MACOS:
            extra_cli_paths.extend([Path("/opt/homebrew/bin/agy"), Path("/usr/local/bin/agy")])
        elif IS_LINUX:
            extra_cli_paths.append(Path("/usr/local/bin/agy"))
        for p in extra_cli_paths:
            if p.is_file():
                agy_cli_bin = str(p)
                break

    cli_dir = home / ".gemini" / "antigravity-cli"
    cli_detected = bool(agy_cli_bin or cli_dir.is_dir())

    # 2. Detect Antigravity 2.0 Desktop App & Antigravity IDE
    app_paths: List[Path] = []
    ide_paths: List[Path] = []

    if IS_WINDOWS:
        local_ad = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        roam_ad = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
        pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        app_candidates = [
            local_ad / "Programs" / "antigravity" / "Antigravity.exe",
            pf / "Antigravity" / "Antigravity.exe",
            roam_ad / "Antigravity" / "app_storage.json",
        ]
        ide_candidates = [
            local_ad / "Programs" / "Antigravity IDE" / "Antigravity IDE.exe",
            local_ad / "Programs" / "antigravity-ide" / "agy-ide.exe",
            roam_ad / "Antigravity IDE",
            roam_ad / "Antigravity" / "User" / "globalStorage",
        ]
    elif IS_MACOS:
        app_candidates = [
            Path("/Applications/Antigravity.app"),
            home / "Applications" / "Antigravity.app",
            home / "Library" / "Application Support" / "Antigravity" / "app_storage.json",
        ]
        ide_candidates = [
            Path("/Applications/Antigravity IDE.app"),
            home / "Applications" / "Antigravity IDE.app",
            home / "Library" / "Application Support" / "Antigravity IDE",
            home / "Library" / "Application Support" / "Antigravity" / "User" / "globalStorage",
        ]
    else:
        xdg = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config")))
        app_candidates = [
            Path("/opt/Antigravity/antigravity"),
            Path("/usr/bin/antigravity"),
            xdg / "Antigravity" / "app_storage.json",
        ]
        ide_candidates = [
            Path("/opt/Antigravity IDE/antigravity-ide"),
            Path("/usr/bin/antigravity-ide"),
            xdg / "Antigravity IDE",
            xdg / "Antigravity" / "User" / "globalStorage",
        ]

    for p in app_candidates:
        if p.exists():
            app_paths.append(p)
    for p in ide_candidates:
        if p.exists():
            ide_paths.append(p)

    # Shared conversation DB also indicates desktop/IDE harness usage
    shared_db = home / ".gemini" / "antigravity" / "conversation_summaries.db"
    app_detected = bool(app_paths or (shared_db.is_file() and not ide_paths))
    ide_detected = bool(ide_paths)

    active_names: List[str] = []
    if app_detected:
        active_names.append("Antigravity 2.0 桌面端")
    if ide_detected:
        active_names.append("Antigravity IDE 编辑器版")
    if cli_detected:
        active_names.append("Antigravity CLI (agy 终端版)")

    return {
        "antigravity_app": {
            "detected": app_detected,
            "evidence": display_path(app_paths[0]) if app_paths else (display_path(shared_db) if shared_db.is_file() else None),
        },
        "antigravity_ide": {
            "detected": ide_detected,
            "evidence": display_path(ide_paths[0]) if ide_paths else None,
        },
        "agy_cli": {
            "detected": cli_detected,
            "binary": redact_home(agy_cli_bin).replace("\\", "/") if agy_cli_bin else None,
            "config_dir": display_path(cli_dir) if cli_dir.is_dir() else None,
        },
        "detected_labels": active_names,
    }


def _find_windows_pythonw() -> Optional[Path]:
    """Locate a real pythonw.exe on Windows (skipping Microsoft Store WindowsApps aliases)."""
    candidates: List[Path] = []

    current_exe = Path(sys.executable)
    if "WindowsApps" not in str(current_exe):
        sibling_pw = current_exe.with_name("pythonw.exe")
        if sibling_pw.is_file():
            candidates.append(sibling_pw)

    for cmd_name in ("pythonw.exe", "python.exe"):
        found = shutil.which(cmd_name)
        if found and "WindowsApps" not in found:
            found_path = Path(found)
            pw = found_path.with_name("pythonw.exe")
            if pw.is_file():
                candidates.append(pw)

    home = Path.home()
    local_app_data = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
    app_data = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))

    search_roots = [
        local_app_data / "Programs" / "Python",
        home / "miniconda3",
        home / "anaconda3",
        app_data / "uv" / "python",
    ]
    if IS_WINDOWS:
        prog_data = os.environ.get("ProgramData", r"C:\ProgramData")
        search_roots.extend([Path(prog_data) / "miniconda3", Path(prog_data) / "anaconda3"])
        for drive in ("C:", "D:", "E:"):
            for sub in ("miniconda3", "anaconda3", "Miniconda3", "Anaconda3", r"Software\miniconda3", r"Software\anaconda3"):
                search_roots.append(Path(f"{drive}\\{sub}"))
        try:
            import winreg

            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(hive, r"Software\Python\PythonCore") as core_key:
                        idx = 0
                        while True:
                            try:
                                ver_tag = winreg.EnumKey(core_key, idx)
                                idx += 1
                                with winreg.OpenKey(core_key, f"{ver_tag}\\InstallPath") as ip_key:
                                    install_dir, _ = winreg.QueryValueEx(ip_key, "")
                                    if install_dir:
                                        pw_reg = Path(str(install_dir)) / "pythonw.exe"
                                        if pw_reg.is_file():
                                            candidates.append(pw_reg)
                            except OSError:
                                break
                except OSError:
                    pass
        except Exception:
            pass

    for root in search_roots:
        if root.is_dir():
            pw_direct = root / "pythonw.exe"
            if pw_direct.is_file():
                candidates.append(pw_direct)
            else:
                try:
                    for sub in sorted(root.rglob("pythonw.exe"), reverse=True):
                        if "venv" not in sub.parts:
                            candidates.append(sub)
                            break
                except Exception:
                    pass

    return candidates[0] if candidates else None


def check_git() -> Dict[str, Any]:
    git_bin = shutil.which("git")
    if git_bin:
        code, out = run_cmd_quiet([git_bin, "--version"])
        if code == 0 and out:
            return {
                "id": "git",
                "name": "Git 版本控制工具 (git)",
                "status": "ok",
                "summary": out.splitlines()[0],
                "purpose": "用于下载和更新开源桌面视觉与本地 OCR 引擎源码",
                "fix": None,
            }
    if IS_WINDOWS:
        fix_cmd = "在 PowerShell 运行: winget install --id Git.Git -e"
    elif IS_MACOS:
        fix_cmd = "在终端运行: xcode-select --install  （或 brew install git）"
    else:
        fix_cmd = "在终端运行: sudo apt-get update && sudo apt-get install -y git"
    return {
        "id": "git",
        "name": "Git 版本控制工具 (git)",
        "status": "missing",
        "summary": "未检测到 git 命令",
        "purpose": "用于下载和更新开源桌面视觉与本地 OCR 引擎源码",
        "fix": fix_cmd,
    }


def check_python(is_headless: bool = False) -> Dict[str, Any]:
    ver_str = f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info < (3, 10):
        if IS_WINDOWS:
            fix_cmd = "在 PowerShell 运行: winget install --id Python.Python.3.12 -e"
        elif IS_MACOS:
            fix_cmd = "在终端运行: brew install python@3.12 python-tk@3.12"
        else:
            fix_cmd = "在终端运行: sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-tk"
        return {
            "id": "python",
            "name": "Python 运行环境 (python)",
            "status": "missing" if sys.version_info < (3, 8) else "warn",
            "summary": f"当前版本偏低 ({ver_str})，推荐 Python 3.10+",
            "purpose": "用于运行托盘防误关守护、历史对话分支工具及 MCP 服务",
            "fix": fix_cmd,
        }

    if IS_WINDOWS:
        pw = _find_windows_pythonw()
        if not pw:
            return {
                "id": "python",
                "name": "Python 运行环境 (python / pythonw)",
                "status": "warn",
                "summary": f"{ver_str} 已安装，但未找到后台无窗口启动器 pythonw.exe",
                "purpose": "pythonw.exe 用于让防误关托盘守护在后台静默运行而不弹出黑框",
                "fix": "建议安装官方完整版 Python: winget install --id Python.Python.3.12 -e （勾选 Add Python to PATH）",
            }
        return {
            "id": "python",
            "name": "Python 运行环境 (python)",
            "status": "ok",
            "summary": f"{ver_str} (后台静默运行器 {pw.name} 已就绪)",
            "purpose": "用于运行托盘防误关守护、历史对话分支工具及健康自检脚本",
            "fix": None,
        }

    if is_headless:
        return {
            "id": "python",
            "name": "Python 运行环境 (python3)",
            "status": "ok",
            "summary": f"{ver_str} (无头终端模式，CLI 功能全部就绪)",
            "purpose": "用于运行 CLI 对话分支工具、MCP 启动器及健康自检脚本",
            "fix": None,
        }

    tk_ok = True
    try:
        import tkinter as _tk  # noqa: F401
    except Exception:
        tk_ok = False

    if not tk_ok:
        fix_tk = (
            "如需打开图形界面窗口可运行: brew install python-tk  （命令行与 AI 对话分支不受影响）"
            if IS_MACOS
            else "在终端运行: sudo apt-get update && sudo apt-get install -y python3-tk"
        )
        return {
            "id": "python",
            "name": "Python 运行环境 (python3)",
            "status": "warn",
            "summary": f"{ver_str} 已就绪，但缺少可选图形界面模块 tkinter（命令行模式仍可正常使用）",
            "purpose": "tkinter 用于打开可视化 Studio 历史对话分支窗口",
            "fix": fix_tk,
        }

    return {
        "id": "python",
        "name": "Python 运行环境 (python3)",
        "status": "ok",
        "summary": f"{ver_str} (含 tkinter 图形界面支持)",
        "purpose": "用于运行托盘守护、历史对话分支工具及健康自检脚本",
        "fix": None,
    }


def check_node_npm() -> Dict[str, Any]:
    node_bin = shutil.which("node")
    npm_bin = shutil.which("npm") or (shutil.which("npm.cmd") if IS_WINDOWS else None)

    if not node_bin or not npm_bin:
        if IS_WINDOWS:
            fix_cmd = "在 PowerShell 运行: winget install --id OpenJS.NodeJS.LTS -e"
        elif IS_MACOS:
            fix_cmd = "运行 bash ./install.sh --module 1 可通过 Homebrew 自动安装，或手动运行: brew install node"
        else:
            fix_cmd = "运行 bash ./install.sh --module 1 可自动安装 Node.js 22 LTS"
        missing_parts = []
        if not node_bin:
            missing_parts.append("node")
        if not npm_bin:
            missing_parts.append("npm")
        return {
            "id": "node_npm",
            "name": "Node.js 与 npm 环境 (node / npm)",
            "status": "missing",
            "summary": f"未检测到 {' / '.join(missing_parts)}",
            "purpose": "用于安装并运行 chrome-devtools-mcp，使 AI 能直接操控浏览器标签页",
            "fix": fix_cmd,
        }

    _, node_out = run_cmd_quiet([node_bin, "--version"])
    _, npm_out = run_cmd_quiet([npm_bin, "--version"])
    node_ver = node_out.splitlines()[0].strip() if node_out else "unknown"
    npm_ver = npm_out.splitlines()[0].strip() if npm_out else "unknown"

    major = 0
    m = re.match(r"^v?(\d+)", node_ver)
    if m:
        major = int(m.group(1))

    cdp_bin = shutil.which("chrome-devtools-mcp")
    if not cdp_bin and IS_WINDOWS:
        app_data = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        candidate = app_data / "npm" / "chrome-devtools-mcp.cmd"
        if candidate.is_file():
            cdp_bin = str(candidate)

    cdp_note = "，chrome-devtools-mcp 已全局安装" if cdp_bin else "，chrome-devtools-mcp 将在安装模块 1 时自动配置"

    if major and major < 20:
        if IS_WINDOWS:
            fix_cmd = "建议升级至 Node.js 20+ LTS: winget install --id OpenJS.NodeJS.LTS -e"
        elif IS_MACOS:
            fix_cmd = "建议升级至 Node.js 20+ LTS: brew upgrade node"
        else:
            fix_cmd = "运行 ./install.sh --module 1 会自动升级至 Node.js 22 LTS"
        return {
            "id": "node_npm",
            "name": "Node.js 与 npm 环境 (node / npm)",
            "status": "warn",
            "summary": f"Node {node_ver}, npm {npm_ver}（版本偏旧，推荐 Node.js v20 及以上）",
            "purpose": "chrome-devtools-mcp 依赖 Node.js 20+ 运行环境",
            "fix": fix_cmd,
        }

    return {
        "id": "node_npm",
        "name": "Node.js 与 npm 环境 (node / npm)",
        "status": "ok",
        "summary": f"Node {node_ver}, npm {npm_ver}{cdp_note}",
        "purpose": "用于安装并运行 chrome-devtools-mcp 浏览器直连控制服务",
        "fix": None,
    }


def check_uv() -> Dict[str, Any]:
    uv_bin = shutil.which("uv")
    if not uv_bin:
        exe_name = "uv.exe" if IS_WINDOWS else "uv"
        fallbacks = [
            Path.home() / ".local" / "bin" / exe_name,
            Path.home() / ".cargo" / "bin" / exe_name,
        ]
        if IS_MACOS:
            fallbacks.extend([Path("/opt/homebrew/bin/uv"), Path("/usr/local/bin/uv")])
        for fallback in fallbacks:
            if fallback.is_file():
                uv_bin = str(fallback)
                break

    if uv_bin:
        code, out = run_cmd_quiet([uv_bin, "--version"])
        ver = out.splitlines()[0] if (code == 0 and out) else "已安装"
        return {
            "id": "uv",
            "name": "uv 极速环境管理器 (uv)",
            "status": "ok",
            "summary": f"{ver} ({redact_home(uv_bin).replace(chr(92), '/')})",
            "purpose": "用于隔离安装并高速拉起桌面视觉与 OCR 服务，不污染系统 Python",
            "fix": None,
        }

    fix_cmd = (
        r'运行 .\install.ps1 -Module 1 会自动安装；或手动在 PowerShell 执行: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
        if IS_WINDOWS
        else "运行 ./install.sh --module 1 会自动安装；或手动执行: curl -LsSf https://astral.sh/uv/install.sh | sh"
    )
    return {
        "id": "uv",
        "name": "uv 极速环境管理器 (uv)",
        "status": "missing",
        "summary": "尚未安装 uv（安装模块 1 时可自动安装）",
        "purpose": "用于隔离安装并高速拉起桌面视觉与 OCR 服务，不污染系统 Python",
        "fix": fix_cmd,
    }


def check_browser_devtools_port(is_headless: bool = False) -> Dict[str, Any]:
    if is_headless:
        return {
            "id": "browser_devtools",
            "name": "浏览器控制模式 (Headless CLI)",
            "status": "ok",
            "summary": "无头服务器环境：chrome-devtools 启动器将自动启用 --headless 无界面模式",
            "purpose": "支持 agy CLI 在远程 SSH 服务器上进行无头网页读取与自动化测试",
            "fix": None,
        }

    home = Path.home()
    candidates: List[Tuple[str, Path]] = []

    if IS_WINDOWS:
        local_app_data = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        candidates = [
            ("Google Chrome", local_app_data / "Google" / "Chrome" / "User Data" / "DevToolsActivePort"),
            ("Microsoft Edge", local_app_data / "Microsoft" / "Edge" / "User Data" / "DevToolsActivePort"),
            ("Brave Browser", local_app_data / "BraveSoftware" / "Brave-Browser" / "User Data" / "DevToolsActivePort"),
            ("Chromium", local_app_data / "Chromium" / "User Data" / "DevToolsActivePort"),
        ]
    elif IS_MACOS:
        app_sup = home / "Library" / "Application Support"
        candidates = [
            ("Google Chrome", app_sup / "Google" / "Chrome" / "DevToolsActivePort"),
            ("Microsoft Edge", app_sup / "Microsoft Edge" / "DevToolsActivePort"),
            ("Brave Browser", app_sup / "BraveSoftware" / "Brave-Browser" / "DevToolsActivePort"),
            ("Arc Browser", app_sup / "Arc" / "User Data" / "DevToolsActivePort"),
            ("Chromium", app_sup / "Chromium" / "DevToolsActivePort"),
        ]
    else:
        candidates = [
            ("Google Chrome", home / ".config" / "google-chrome" / "DevToolsActivePort"),
            ("Microsoft Edge", home / ".config" / "microsoft-edge" / "DevToolsActivePort"),
            ("Brave Browser", home / ".config" / "BraveSoftware" / "Brave-Browser" / "DevToolsActivePort"),
            ("Chromium", home / ".config" / "chromium" / "DevToolsActivePort"),
            ("Chromium (Snap)", home / "snap" / "chromium" / "common" / "chromium" / "DevToolsActivePort"),
        ]

    active_browsers: List[str] = []
    stale_browsers: List[str] = []

    for browser_name, port_file in candidates:
        if port_file.is_file():
            try:
                lines = [ln.strip() for ln in port_file.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
                if lines and lines[0].isdigit():
                    port = int(lines[0])
                    if is_tcp_port_open("127.0.0.1", port):
                        active_browsers.append(f"{browser_name} (端口 {port} 正在监听)")
                    else:
                        stale_browsers.append(f"{browser_name} ({display_path(port_file)})")
            except Exception:
                pass

    if not active_browsers and is_tcp_port_open("127.0.0.1", 9222):
        active_browsers.append("本地调试浏览器 (端口 9222 正在监听)")

    if active_browsers:
        return {
            "id": "browser_devtools",
            "name": "Chrome / Edge 远程调试直连状态 (DevToolsActivePort)",
            "status": "ok",
            "summary": "已激活并连接就绪: " + "，".join(active_browsers),
            "purpose": "让 Antigravity (桌面端 / IDE / agy CLI) 直接复用已登录的浏览器标签页",
            "fix": None,
        }

    guide_steps = (
        "两步开启日常浏览器直连（保留全部已登录状态）："
        "1) 打开 Chrome 访问 chrome://inspect/#remote-debugging（Edge 访问 edge://inspect/#remote-debugging）；"
        "2) 勾选页面顶部的 'Enable remote debugging' 选项并保持浏览器打开。"
    )

    if stale_browsers:
        return {
            "id": "browser_devtools",
            "name": "Chrome / Edge 远程调试直连状态 (DevToolsActivePort)",
            "status": "warn",
            "summary": "已配置过远程调试，但浏览器当前未运行或端口未监听: " + "，".join(stale_browsers),
            "purpose": "让 Antigravity 直接复用您日常已登录的浏览器标签页，无需重复扫码登录",
            "fix": "打开您日常使用的 Chrome 或 Edge 浏览器即可自动恢复连接；若仍未生效，" + guide_steps,
        }

    return {
        "id": "browser_devtools",
        "name": "Chrome / Edge 远程调试直连状态 (DevToolsActivePort)",
        "status": "warn",
        "summary": "尚未检测到已开启的 DevToolsActivePort 远程调试端口",
        "purpose": "让 Antigravity 直接复用您日常已登录的浏览器标签页，无需重复扫码登录",
        "fix": guide_steps,
    }


def check_module_computer_use(surfaces: Dict[str, Any], is_headless: bool) -> Dict[str, Any]:
    home = Path.home()
    mcp_cfg_primary = home / ".gemini" / "config" / "mcp_config.json"
    mcp_cfg_alt = home / ".gemini" / "antigravity" / "mcp_config.json"
    cli_settings = home / ".gemini" / "antigravity-cli" / "settings.json"
    workspace_dir = home / "mcp-gui-workspace"

    if IS_WINDOWS:
        expected_servers = {"chrome-devtools", "windows-uia-mcp", "windows-ocr-mcp"}
        engine_dirs = [workspace_dir / "Windows-MCP", workspace_dir / "computer-control-mcp"]
        control_cfg: Optional[Path] = home / ".windows-mcp" / "config.toml"
        install_cmd = r".\install.ps1 -Module 1"
    elif IS_MACOS:
        expected_servers = {"chrome-devtools", "macos-uia-mcp", "macos-ocr-mcp"}
        engine_dirs = [workspace_dir / "macos-gui-mcp", workspace_dir / "computer-control-mcp"]
        control_cfg = home / ".macos-mcp" / "config.toml"
        install_cmd = "bash ./install.sh --module 1"
    elif is_headless:
        expected_servers = {"chrome-devtools"}
        engine_dirs = []
        control_cfg = None
        install_cmd = "bash ./install.sh --module 1"
    else:
        expected_servers = {"chrome-devtools", "linux-uia-mcp", "linux-ocr-mcp"}
        engine_dirs = [workspace_dir / "linux-gui-mcp", workspace_dir / "computer-control-mcp"]
        control_cfg = home / ".linux-mcp" / "config.toml"
        install_cmd = "bash ./install.sh --module 1"

    items: List[Dict[str, Any]] = []

    # 1. Check global mcp_config.json
    cfg_found = mcp_cfg_primary if mcp_cfg_primary.is_file() else (mcp_cfg_alt if mcp_cfg_alt.is_file() else None)
    if cfg_found:
        try:
            data = json.loads(cfg_found.read_text(encoding="utf-8", errors="replace"))
            servers = set((data.get("mcpServers") or {}).keys()) if isinstance(data, dict) else set()
            present = expected_servers & servers
            missing = expected_servers - servers
            items.append({
                "label": "全局 MCP 服务配置 (App / IDE / CLI 通用)",
                "path": display_path(cfg_found),
                "ok": len(missing) == 0,
                "detail": f"已注册 {', '.join(sorted(present))}" if not missing else f"缺少服务项: {', '.join(sorted(missing))}",
            })
        except Exception:
            items.append({
                "label": "全局 MCP 服务配置",
                "path": display_path(cfg_found),
                "ok": False,
                "detail": "JSON 格式损坏，无法解析",
            })
    else:
        items.append({
            "label": "全局 MCP 服务配置",
            "path": display_path(mcp_cfg_primary),
            "ok": False,
            "detail": "文件不存在",
        })

    # 1b. Check agy CLI settings.json sync if agy CLI is installed
    if surfaces["agy_cli"]["detected"]:
        cli_ok = False
        cli_detail = "尚未同步到 agy CLI 配置"
        if cli_settings.is_file():
            try:
                cdata = json.loads(cli_settings.read_text(encoding="utf-8", errors="replace"))
                cservers = set((cdata.get("mcpServers") or {}).keys()) if isinstance(cdata, dict) else set()
                cmissing = expected_servers - cservers
                cli_ok = len(cmissing) == 0
                cli_detail = "已同步 MCP 服务至 agy CLI" if cli_ok else f"agy CLI 缺少: {', '.join(sorted(cmissing))}"
            except Exception:
                cli_detail = "settings.json 无法解析"
        items.append({
            "label": "agy CLI 专属 MCP 同步",
            "path": display_path(cli_settings),
            "ok": cli_ok,
            "detail": cli_detail,
        })

    # 2. Check ~/mcp-gui-workspace engines (GUI environments)
    if engine_dirs:
        existing_engines = [d.name for d in engine_dirs if d.is_dir()]
        missing_engines = [d.name for d in engine_dirs if not d.is_dir()]
        ws_ok = len(missing_engines) == 0
        items.append({
            "label": "极速视觉与 OCR 工作区",
            "path": display_path(workspace_dir),
            "ok": ws_ok,
            "detail": f"已部署 {', '.join(existing_engines)}" if ws_ok else f"缺少目录: {', '.join(missing_engines)}",
        })

    # 3. Check control config
    if control_cfg is not None:
        ctrl_ok = control_cfg.is_file()
        items.append({
            "label": "鼠标晃动快速接管配置",
            "path": display_path(control_cfg),
            "ok": ctrl_ok,
            "detail": "已配置 (2秒冷却快速恢复)" if ctrl_ok else "配置文件不存在",
        })

    passed = sum(1 for it in items if it["ok"])
    status = "installed" if passed == len(items) else ("partial" if passed > 0 else "not_installed")

    return {
        "id": "computer_use",
        "index": 1,
        "name": "桌面与浏览器极速操控 (Computer Use + Chrome 直连)",
        "status": status,
        "items": items,
        "install_command": install_cmd,
    }


def _check_windows_run_registry(value_name: str) -> Tuple[bool, str]:
    if not IS_WINDOWS:
        return False, "非 Windows 平台"
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        ) as key:
            val, _ = winreg.QueryValueEx(key, value_name)
            has_val = bool(str(val).strip())
            return has_val, ("已注册开机自启 (AntigravityCloseGuard)" if has_val else "注册表项为空")
    except FileNotFoundError:
        return False, "尚未注册开机自启注册表项"
    except Exception as exc:
        return False, f"无法读取注册表项 ({redact_home(str(exc))})"


def _check_windows_close_guard_alive() -> Tuple[bool, str]:
    """Verify AntigravityCloseGuardHiddenWnd is actively running on WinSta0\\Default."""
    if not IS_WINDOWS:
        return False, "非 Windows 平台"
    try:
        import ctypes
        from ctypes import wintypes

        u32 = ctypes.windll.user32  # type: ignore[attr-defined]
        hdesk = u32.OpenDesktopW("Default", 0, False, 0x01FF)
        if hdesk:
            u32.SetThreadDesktop(hdesk)
        hwnd = u32.FindWindowW("AntigravityCloseGuardHiddenWnd", None)
        if hwnd:
            pid = wintypes.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return True, f"后台守护正在运行 (PID {pid.value}，同时保护 App / IDE / agy 终端)"
        return False, "当前未在后台运行（请重新运行 install_close_guard.ps1 启动）"
    except Exception as exc:
        return False, f"状态检测异常 ({redact_home(str(exc))})"


def check_module_close_guard(is_headless: bool) -> Dict[str, Any]:
    home = Path.home()
    guard_dir = home / "mcp-gui-workspace" / "antigravity-close-guard"
    items: List[Dict[str, Any]] = []

    if IS_WINDOWS:
        script_path = guard_dir / "antigravity_close_guard.pyw"
        script_ok = script_path.is_file()
        items.append({
            "label": "托盘守护主程序 (App / IDE / agy 终端防误关)",
            "path": display_path(script_path),
            "ok": script_ok,
            "detail": "已部署" if script_ok else "脚本未安装",
        })

        reg_ok, reg_detail = _check_windows_run_registry("AntigravityCloseGuard")
        items.append({
            "label": "Windows 登录自动启动项",
            "path": r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run\AntigravityCloseGuard",
            "ok": reg_ok,
            "detail": reg_detail,
        })

        alive_ok, alive_detail = _check_windows_close_guard_alive()
        items.append({
            "label": "实时后台驻留进程状态",
            "path": "WinSta0\\Default (AntigravityCloseGuardHiddenWnd)",
            "ok": alive_ok,
            "detail": alive_detail,
        })
        install_cmd = r".\install.ps1 -Module 2"
    elif IS_MACOS:
        script_path = guard_dir / "antigravity_close_guard_macos.py"
        plist_file = home / "Library" / "LaunchAgents" / "com.antigravity.close-guard.plist"
        agy_guard_bin = home / ".local" / "bin" / "agy-guard"
        script_ok = script_path.is_file()
        plist_ok = plist_file.is_file()
        items.append({
            "label": "macOS 防误退守护主程序 (Cmd+Q 拦截 + agy 终端保护)",
            "path": display_path(script_path),
            "ok": script_ok,
            "detail": "已部署" if script_ok else "脚本未安装",
        })
        items.append({
            "label": "macOS LaunchAgents 登录自启",
            "path": display_path(plist_file),
            "ok": plist_ok,
            "detail": "已注册自启并加载" if plist_ok else "尚未注册 LaunchAgent",
        })
        items.append({
            "label": "agy CLI 终端防断连包装器 (agy-guard)",
            "path": display_path(agy_guard_bin),
            "ok": agy_guard_bin.is_file(),
            "detail": "已就绪 (tmux 持久化)" if agy_guard_bin.is_file() else "未部署",
        })
        install_cmd = "bash ./install.sh --module 2"
    elif is_headless:
        agy_guard_bin = home / ".local" / "bin" / "agy-guard"
        ok = agy_guard_bin.is_file()
        items.append({
            "label": "Headless SSH 防断连守护包装器 (agy-guard)",
            "path": display_path(agy_guard_bin),
            "ok": ok,
            "detail": "已就绪（运行 agy-guard 启动会话，SSH 断开任务不断连）" if ok else "尚未安装",
        })
        install_cmd = "bash ./install.sh --module 2"
    else:
        script_path = guard_dir / "antigravity_close_guard_linux.py"
        script_ok = script_path.is_file()
        items.append({
            "label": "托盘守护主程序 (App / IDE / agy 终端防误关)",
            "path": display_path(script_path),
            "ok": script_ok,
            "detail": "已部署" if script_ok else "脚本未安装",
        })

        service_file = home / ".config" / "systemd" / "user" / "antigravity-close-guard.service"
        svc_exists = service_file.is_file()
        svc_active = False
        svc_state_text = "未注册 systemd 用户服务"
        if svc_exists:
            systemctl_bin = shutil.which("systemctl")
            if systemctl_bin:
                code, out = run_cmd_quiet([systemctl_bin, "--user", "is-active", "antigravity-close-guard.service"])
                state = out.splitlines()[0].strip() if out else "unknown"
                svc_active = code == 0 and state == "active"
                svc_state_text = f"服务文件已就绪 (当前状态: {state})"
            else:
                svc_active = True
                svc_state_text = "服务文件已就绪"

        items.append({
            "label": "Linux systemd 用户自启服务",
            "path": display_path(service_file),
            "ok": svc_exists and svc_active,
            "detail": svc_state_text,
        })
        install_cmd = "bash ./install.sh --module 2"

    passed = sum(1 for it in items if it["ok"])
    status = "installed" if passed == len(items) else ("partial" if passed > 0 else "not_installed")

    return {
        "id": "close_guard",
        "index": 2,
        "name": "防误关后台驻留守护 (Close-to-Tray / CLI Guard)",
        "status": status,
        "items": items,
        "install_command": install_cmd,
    }


def check_module_branch_conversation() -> Dict[str, Any]:
    home = Path.home()
    branch_dir = home / "mcp-gui-workspace" / "antigravity-branch"
    branch_script = branch_dir / "branch_conversation.py"
    skill_md = home / ".gemini" / "config" / "skills" / "branch-conversation" / "SKILL.md"

    script_ok = branch_script.is_file()
    skill_ok = skill_md.is_file()

    items = [
        {
            "label": "全版本对话分支工具 (支持 App / IDE / agy CLI)",
            "path": display_path(branch_script),
            "ok": script_ok,
            "detail": "已部署" if script_ok else "脚本未安装",
        },
        {
            "label": "全局对话分支 Skill 技能卡",
            "path": display_path(skill_md),
            "ok": skill_ok,
            "detail": "已部署" if skill_ok else "SKILL.md 未安装",
        },
    ]

    passed = sum(1 for it in items if it["ok"])
    status = "installed" if passed == len(items) else ("partial" if passed > 0 else "not_installed")

    install_cmd = r".\install.ps1 -Module 3" if IS_WINDOWS else "bash ./install.sh --module 3"
    return {
        "id": "branch_conversation",
        "index": 3,
        "name": "历史对话任意轮次分支工具 (Conversation Branching)",
        "status": status,
        "items": items,
        "install_command": install_cmd,
    }


def collect_report() -> Dict[str, Any]:
    session_mode, is_headless = detect_session_environment()
    surfaces = detect_antigravity_surfaces()

    prereqs = [
        check_git(),
        check_python(is_headless=is_headless),
        check_node_npm(),
        check_uv(),
        check_browser_devtools_port(is_headless=is_headless),
    ]
    modules = [
        check_module_computer_use(surfaces=surfaces, is_headless=is_headless),
        check_module_close_guard(is_headless=is_headless),
        check_module_branch_conversation(),
    ]

    os_label = "Windows" if IS_WINDOWS else ("macOS" if IS_MACOS else ("Linux" if IS_LINUX else platform.system()))
    prereq_missing = sum(1 for p in prereqs if p["status"] == "missing")
    prereq_warn = sum(1 for p in prereqs if p["status"] == "warn")
    installed_count = sum(1 for m in modules if m["status"] == "installed")

    return {
        "toolkit": "antigravity-toolkit",
        "platform": {
            "os": os_label,
            "release": platform.release(),
            "arch": platform.machine(),
            "python_version": platform.python_version(),
            "session_mode": session_mode,
            "is_headless": is_headless,
        },
        "surfaces": surfaces,
        "prerequisites": prereqs,
        "modules": modules,
        "summary": {
            "prerequisites_ok": len(prereqs) - prereq_missing - prereq_warn,
            "prerequisites_warn": prereq_warn,
            "prerequisites_missing": prereq_missing,
            "modules_installed": installed_count,
            "modules_total": len(modules),
        },
    }


def print_human_report(report: Dict[str, Any], style: Style) -> None:
    plat = report["platform"]
    surfaces = report["surfaces"]
    detected_labels = surfaces.get("detected_labels") or ["尚未检测到本地会话记录（安装配置将自动预置就绪）"]

    print()
    print(style.bold(style.cyan("================================================================")))
    print(style.bold(style.cyan("   Antigravity Toolkit - 运行环境与全版本安装自检 (Doctor)")))
    print(style.bold(style.cyan("================================================================")))
    print(
        f"  操作系统: {plat['os']} ({plat['release']}, {plat['arch']}, {plat['session_mode']})  |  "
        f"Python: {plat['python_version']}"
    )
    print(f"  识别版本: {style.green(' · '.join(detected_labels))}")
    print()

    # Section 1: Prerequisites
    print(style.bold("[一] 基础依赖与浏览器环境检查"))
    print(style.dim("----------------------------------------------------------------"))
    for item in report["prerequisites"]:
        st = item["status"]
        if st == "ok":
            badge = style.green("[已就绪]")
        elif st == "warn":
            badge = style.yellow("[需留意]")
        else:
            badge = style.red("[未安装]")

        print(f"  {badge} {style.bold(item['name'])}")
        print(f"           状态: {item['summary']}")
        if st != "ok":
            print(f"           作用: {style.dim(item['purpose'])}")
            if item.get("fix"):
                print(f"           解决: {style.yellow(item['fix'])}")
    print()

    # Section 2: Modules
    print(style.bold("[二] 功能增强模块安装状态检查"))
    print(style.dim("----------------------------------------------------------------"))
    for mod in report["modules"]:
        mst = mod["status"]
        if mst == "installed":
            mbadge = style.green("[已完整安装]")
        elif mst == "partial":
            mbadge = style.yellow("[部分已安装]")
        else:
            mbadge = style.dim("[尚未安装]")

        print(f"  {mbadge} 模块 {mod['index']}: {style.bold(mod['name'])}")
        for sub in mod["items"]:
            mark = style.green("  + ") if sub["ok"] else style.yellow("  - ")
            print(f"         {mark}{sub['label']}: {sub['detail']}  {style.dim('(' + sub['path'] + ')')}")
        if mst != "installed":
            print(f"           一键安装/修复命令: {style.cyan(mod['install_command'])}")
        print()

    # Section 3: Friendly Summary
    summ = report["summary"]
    all_cmd = r".\install.ps1" if IS_WINDOWS else "bash ./install.sh"
    print(style.dim("----------------------------------------------------------------"))
    if summ["modules_installed"] == summ["modules_total"] and summ["prerequisites_missing"] == 0:
        print(
            style.green(
                f"  自检完成：全部 {summ['modules_total']} 个增强模块均已按当前环境安装就绪！"
            )
        )
        if summ["prerequisites_warn"] > 0:
            print(
                style.yellow(
                    "  提示：上方有 [需留意] 项（例如日常浏览器尚未打开或未勾选远程调试），按提示开启即可获得完整体验。"
                )
            )
    else:
        print(
            f"  自检汇总：已完整安装 {summ['modules_installed']}/{summ['modules_total']} 个增强模块，"
            f"缺失基础工具 {summ['prerequisites_missing']} 项。"
        )
        print(
            f"  下一步建议：直接运行交互式安装向导 {style.cyan(all_cmd)} 按菜单数字一键安装所需模块！"
        )
    print()


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Antigravity Toolkit 跨平台与多版本健康自检工具 (Doctor)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出机器可读的 JSON 格式自检报告",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="禁用终端彩色输出",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式：若缺少必需基础依赖 (git/python/node) 则返回非零退出码",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    _configure_utf8_output()
    args = parse_args(argv)
    report = collect_report()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        use_color = (not args.no_color) and _supports_color()
        print_human_report(report, Style(enabled=use_color))

    if args.strict and report["summary"]["prerequisites_missing"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
