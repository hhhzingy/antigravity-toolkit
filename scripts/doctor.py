#!/usr/bin/env python3
"""
Antigravity Toolkit - Cross-Platform Environment & Installation Health Checker (Doctor)

Uses Python standard library only. Safe to run on Windows and Ubuntu/Linux.
Usage:
    python scripts/doctor.py          # Friendly human-readable report
    python scripts/doctor.py --json   # Machine-readable JSON output
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
        # Enable ANSI VT processing on Windows 10/11 consoles when possible
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
    # Also redact case-insensitive home match on Windows
    if IS_WINDOWS and home:
        pattern = re.compile(re.escape(home), re.IGNORECASE)
        result = pattern.sub("~", result)
        pattern_fwd = re.compile(re.escape(home_fwd), re.IGNORECASE)
        result = pattern_fwd.sub("~", result)
    return result


def display_path(path: Path) -> str:
    return redact_home(str(path)).replace("\\", "/")


def run_cmd_quiet(args: List[str], timeout: float = 4.0) -> Tuple[int, str]:
    """Run an external command safely and return (returncode, first_line_or_output)."""
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
    fix_cmd = (
        "在 PowerShell 运行: winget install --id Git.Git -e  （或访问 https://git-scm.com/download/win 下载安装后重开终端）"
        if IS_WINDOWS
        else "在终端运行: sudo apt-get update && sudo apt-get install -y git"
    )
    return {
        "id": "git",
        "name": "Git 版本控制工具 (git)",
        "status": "missing",
        "summary": "未检测到 git 命令",
        "purpose": "用于下载和更新开源桌面视觉与本地 OCR 引擎源码",
        "fix": fix_cmd,
    }


def check_python() -> Dict[str, Any]:
    ver_str = f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info < (3, 8):
        fix_cmd = (
            "在 PowerShell 运行: winget install --id Python.Python.3.12 -e"
            if IS_WINDOWS
            else "在终端运行: sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-tk"
        )
        return {
            "id": "python",
            "name": "Python 运行环境 (python)",
            "status": "missing",
            "summary": f"当前版本过低 ({ver_str})，建议 Python 3.10+",
            "purpose": "用于运行托盘防误关守护、历史对话分支工具及健康自检脚本",
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

    # On Linux, check if tkinter is importable (helpful for branch_conversation GUI)
    tk_ok = True
    try:
        import tkinter as _tk  # noqa: F401
    except Exception:
        tk_ok = False

    if not tk_ok:
        return {
            "id": "python",
            "name": "Python 运行环境 (python3)",
            "status": "warn",
            "summary": f"{ver_str} 已就绪，但缺少图形界面模块 python3-tk",
            "purpose": "python3-tk 用于打开可视化历史对话分支窗口",
            "fix": "在终端运行: sudo apt-get update && sudo apt-get install -y python3-tk",
        }

    return {
        "id": "python",
        "name": "Python 运行环境 (python3)",
        "status": "ok",
        "summary": f"{ver_str} (含 tkinter 图形界面支持)",
        "purpose": "用于运行托盘防误关守护、历史对话分支工具及健康自检脚本",
        "fix": None,
    }


def check_node_npm() -> Dict[str, Any]:
    node_bin = shutil.which("node")
    npm_bin = shutil.which("npm") or (shutil.which("npm.cmd") if IS_WINDOWS else None)

    if not node_bin or not npm_bin:
        fix_cmd = (
            "在 PowerShell 运行: winget install --id OpenJS.NodeJS.LTS -e  （或前往 https://nodejs.org 下载 LTS 安装包后重开终端）"
            if IS_WINDOWS
            else "运行 ./install.sh --module 1 可自动安装 Node.js 22 LTS；或手动访问 https://nodejs.org 安装 LTS 版本"
        )
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
            "purpose": "用于安装并运行 chrome-devtools-mcp，使 AI 能直接操控日常已登录的浏览器标签页",
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

    # Check if chrome-devtools-mcp is already globally installed
    cdp_bin = shutil.which("chrome-devtools-mcp")
    if not cdp_bin and IS_WINDOWS:
        app_data = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        candidate = app_data / "npm" / "chrome-devtools-mcp.cmd"
        if candidate.is_file():
            cdp_bin = str(candidate)

    cdp_note = "，chrome-devtools-mcp 已全局安装" if cdp_bin else "，chrome-devtools-mcp 将在安装模块 1 时自动配置"

    if major and major < 20:
        fix_cmd = (
            "建议升级至 Node.js 20+ LTS: winget install --id OpenJS.NodeJS.LTS -e"
            if IS_WINDOWS
            else "运行 ./install.sh --module 1 会自动升级至 Node.js 22 LTS"
        )
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
        for fallback in (
            Path.home() / ".local" / "bin" / exe_name,
            Path.home() / ".cargo" / "bin" / exe_name,
        ):
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
        '运行 .\\install.ps1 -Module 1 会自动安装；或手动在 PowerShell 执行: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
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


def check_browser_devtools_port() -> Dict[str, Any]:
    home = Path.home()
    candidates: List[Tuple[str, Path]] = []

    if IS_WINDOWS:
        local_app_data = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        candidates = [
            ("Google Chrome", local_app_data / "Google" / "Chrome" / "User Data" / "DevToolsActivePort"),
            ("Microsoft Edge", local_app_data / "Microsoft" / "Edge" / "User Data" / "DevToolsActivePort"),
            ("Chromium", local_app_data / "Chromium" / "User Data" / "DevToolsActivePort"),
        ]
    else:
        candidates = [
            ("Google Chrome", home / ".config" / "google-chrome" / "DevToolsActivePort"),
            ("Microsoft Edge", home / ".config" / "microsoft-edge" / "DevToolsActivePort"),
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
            "purpose": "让 Antigravity 直接复用您日常已登录的浏览器标签页，无需重复扫码登录",
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


def check_module_computer_use() -> Dict[str, Any]:
    home = Path.home()
    mcp_cfg_primary = home / ".gemini" / "config" / "mcp_config.json"
    mcp_cfg_alt = home / ".gemini" / "antigravity" / "mcp_config.json"
    workspace_dir = home / "mcp-gui-workspace"

    if IS_WINDOWS:
        expected_servers = {"chrome-devtools", "windows-uia-mcp", "windows-ocr-mcp"}
        engine_dirs = [workspace_dir / "Windows-MCP", workspace_dir / "computer-control-mcp"]
        control_cfg = home / ".windows-mcp" / "config.toml"
        install_cmd = r".\install.ps1 -Module 1"
    else:
        expected_servers = {"chrome-devtools", "linux-uia-mcp", "linux-ocr-mcp"}
        engine_dirs = [workspace_dir / "linux-gui-mcp", workspace_dir / "computer-control-mcp"]
        control_cfg = home / ".linux-mcp" / "config.toml"
        install_cmd = "./install.sh --module 1"

    items: List[Dict[str, Any]] = []

    # 1. Check mcp_config.json
    cfg_found = mcp_cfg_primary if mcp_cfg_primary.is_file() else (mcp_cfg_alt if mcp_cfg_alt.is_file() else None)
    cfg_ok = False
    if cfg_found:
        try:
            data = json.loads(cfg_found.read_text(encoding="utf-8", errors="replace"))
            servers = set((data.get("mcpServers") or {}).keys()) if isinstance(data, dict) else set()
            present = expected_servers & servers
            missing = expected_servers - servers
            if not missing:
                cfg_ok = True
                items.append({
                    "label": "MCP 服务配置",
                    "path": display_path(cfg_found),
                    "ok": True,
                    "detail": f"已注册 {', '.join(sorted(present))}",
                })
            else:
                items.append({
                    "label": "MCP 服务配置",
                    "path": display_path(cfg_found),
                    "ok": False,
                    "detail": f"缺少服务项: {', '.join(sorted(missing))}",
                })
        except Exception:
            items.append({
                "label": "MCP 服务配置",
                "path": display_path(cfg_found),
                "ok": False,
                "detail": "JSON 格式损坏，无法解析",
            })
    else:
        items.append({
            "label": "MCP 服务配置",
            "path": display_path(mcp_cfg_primary),
            "ok": False,
            "detail": "文件不存在",
        })

    # 2. Check ~/mcp-gui-workspace engines
    existing_engines = [d.name for d in engine_dirs if d.is_dir()]
    missing_engines = [d.name for d in engine_dirs if not d.is_dir()]
    ws_ok = len(missing_engines) == 0
    items.append({
        "label": "极速视觉与 OCR 工作区",
        "path": display_path(workspace_dir),
        "ok": ws_ok,
        "detail": (
            f"已部署 {', '.join(existing_engines)}"
            if ws_ok
            else f"缺少目录: {', '.join(missing_engines)}"
        ),
    })

    # 3. Check control config (~/.windows-mcp/config.toml or ~/.linux-mcp/config.toml)
    ctrl_ok = control_cfg.is_file()
    items.append({
        "label": "鼠标晃动快速接管配置",
        "path": display_path(control_cfg),
        "ok": ctrl_ok,
        "detail": "已配置 (2秒冷却快速恢复)" if ctrl_ok else "配置文件不存在",
    })

    passed = sum(1 for it in items if it["ok"])
    if passed == len(items):
        status = "installed"
    elif passed > 0:
        status = "partial"
    else:
        status = "not_installed"

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
            return True, f"后台守护正在运行 (PID {pid.value})"
        return False, "当前未在后台运行（请重新运行 install_close_guard.ps1 启动）"
    except Exception as exc:
        return False, f"状态检测异常 ({redact_home(str(exc))})"


def check_module_close_guard() -> Dict[str, Any]:
    home = Path.home()
    guard_dir = home / "mcp-gui-workspace" / "antigravity-close-guard"
    items: List[Dict[str, Any]] = []

    if IS_WINDOWS:
        script_path = guard_dir / "antigravity_close_guard.pyw"
        script_ok = script_path.is_file()
        items.append({
            "label": "托盘守护主程序",
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
    else:
        script_path = guard_dir / "antigravity_close_guard_linux.py"
        script_ok = script_path.is_file()
        items.append({
            "label": "托盘守护主程序",
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
        install_cmd = "./install.sh --module 2"

    passed = sum(1 for it in items if it["ok"])
    if passed == len(items):
        status = "installed"
    elif passed > 0:
        status = "partial"
    else:
        status = "not_installed"

    return {
        "id": "close_guard",
        "index": 2,
        "name": "防误关系统托盘驻留守护 (Close-to-Tray Guard)",
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
            "label": "可视化对话分支工具",
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
    if passed == len(items):
        status = "installed"
    elif passed > 0:
        status = "partial"
    else:
        status = "not_installed"

    install_cmd = r".\install.ps1 -Module 3" if IS_WINDOWS else "./install.sh --module 3"
    return {
        "id": "branch_conversation",
        "index": 3,
        "name": "历史对话任意轮次分支工具 (Conversation Branching)",
        "status": status,
        "items": items,
        "install_command": install_cmd,
    }


def collect_report() -> Dict[str, Any]:
    prereqs = [
        check_git(),
        check_python(),
        check_node_npm(),
        check_uv(),
        check_browser_devtools_port(),
    ]
    modules = [
        check_module_computer_use(),
        check_module_close_guard(),
        check_module_branch_conversation(),
    ]

    os_label = "Windows" if IS_WINDOWS else ("Linux" if IS_LINUX else platform.system())
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
        },
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
    print()
    print(style.bold(style.cyan("================================================================")))
    print(style.bold(style.cyan("   Antigravity Toolkit - 运行环境与功能安装健康自检 (Doctor)")))
    print(style.bold(style.cyan("================================================================")))
    print(
        f"  操作系统: {plat['os']} ({plat['release']}, {plat['arch']})  |  "
        f"Python: {plat['python_version']}"
    )
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
    all_cmd = r".\install.ps1" if IS_WINDOWS else "./install.sh"
    print(style.dim("----------------------------------------------------------------"))
    if summ["modules_installed"] == summ["modules_total"] and summ["prerequisites_missing"] == 0:
        print(
            style.green(
                f"  自检完成：全部 {summ['modules_total']} 个增强模块均已安装就绪！"
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
        description="Antigravity Toolkit 跨平台环境与安装状态健康自检工具 (Doctor)"
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
