#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity Close Guard for macOS (App 2.0 + Antigravity IDE + `agy` CLI)
-------------------------------------------------------------------------
Zero-dependency macOS background guard (pure Python stdlib + CoreGraphics / CoreFoundation ctypes):
- Intercepts accidental `Cmd+Q` on `Antigravity` and `Antigravity IDE`: instead of terminating
  the process and killing active AI conversations / subagents, hides the app cleanly (`Cmd+H`
  semantics) while tasks continue running in the background.
- Intercepts accidental `Cmd+Q` on `Terminal` / `iTerm2` / `Ghostty` / `Warp` ONLY when an
  active `agy` CLI process is running inside, hiding the terminal instead of killing `agy`.
- Explicit quit anytime via:
    * `Cmd+Option+Q` shortcut, or
    * `python3 ~/mcp-gui-workspace/antigravity-close-guard/antigravity_close_guard_macos.py --quit`
- Zero modification to `/Applications/Antigravity.app` (100% survives official auto-updates).
- Event-driven `CFRunLoop` (`0.0%` idle CPU).
"""

from __future__ import annotations

import argparse
import ctypes
from pathlib import Path
import subprocess
import sys
import time

AGY_APP_NAMES = {"Antigravity", "Antigravity IDE"}
TERMINAL_APP_NAMES = {"Terminal", "iTerm2", "iTerm", "Warp", "Ghostty", "Alacritty", "kitty", "WezTerm"}

# macOS Virtual Keycode for 'Q' is 12; 'W' is 13
KC_Q = 12
KC_W = 13

kCGSessionEventTap = 1
kCGHeadInsertEventTap = 0
kCGEventTapOptionDefault = 0
kCGEventKeyDown = 10
kCGEventTapDisabledByTimeout = 0xFFFFFFFE
kCGEventTapDisabledByUserInput = 0xFFFFFFFF

kCGEventFlagMaskCommand = 1 << 20
kCGEventFlagMaskAlternate = 1 << 19
kCGEventFlagMaskControl = 1 << 18
kCGKeyboardEventKeycode = 9


def _get_frontmost_app() -> str:
    try:
        out = subprocess.check_output(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ],
            text=True,
            timeout=1.5,
            stderr=subprocess.DEVNULL,
        )
        return out.strip()
    except Exception:
        return ""


def _any_agy_cli_running() -> bool:
    try:
        res = subprocess.run(["pgrep", "-x", "agy"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.0)
        return res.returncode == 0
    except Exception:
        return False


def _hide_app(app_name: str, notify_msg: str | None = None) -> None:
    safe_app = app_name.replace('"', '\\"')
    script = f'tell application "System Events" to set visible of process "{safe_app}" to false'
    subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if notify_msg:
        safe_msg = notify_msg.replace('"', '\\"')
        n_script = f'display notification "{safe_msg}" with title "Antigravity 已驻留后台"'
        subprocess.Popen(["osascript", "-e", n_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def quit_antigravity_completely() -> int:
    for app in ("Antigravity", "Antigravity IDE"):
        subprocess.run(
            ["osascript", "-e", f'if application "{app}" is running then tell application "{app}" to quit'],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    print("Antigravity has been completely exited.")
    return 0


def restore_antigravity() -> int:
    for app in ("Antigravity", "Antigravity IDE"):
        res = subprocess.run(
            ["osascript", "-e", f'if application "{app}" is running then tell application "{app}" to activate'],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if res.returncode == 0:
            break
    return 0


def open_branch_gui() -> int:
    candidates = [
        Path.home() / "mcp-gui-workspace" / "antigravity-branch" / "branch_conversation.py",
        Path(__file__).resolve().parent.parent / "branch_conversation" / "branch_conversation.py",
    ]
    script = next((p for p in candidates if p.is_file()), None)
    if not script:
        print("branch_conversation.py not found.", file=sys.stderr)
        return 1
    subprocess.Popen([sys.executable, str(script), "--gui"])
    return 0


def run_daemon(self_test: bool = False) -> int:
    if sys.platform != "darwin":
        print("antigravity_close_guard_macos.py requires macOS (darwin).", file=sys.stderr)
        return 1

    cg = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

    CGEventTapCallBack = ctypes.CFUNCTYPE(
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p
    )

    cg.CGEventTapCreate.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint64,
        CGEventTapCallBack,
        ctypes.c_void_p,
    ]
    cg.CGEventTapCreate.restype = ctypes.c_void_p
    cg.CGEventGetFlags.argtypes = [ctypes.c_void_p]
    cg.CGEventGetFlags.restype = ctypes.c_uint64
    cg.CGEventGetIntegerValueField.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    cg.CGEventGetIntegerValueField.restype = ctypes.c_int64
    cg.CGEventTapEnable.argtypes = [ctypes.c_void_p, ctypes.c_bool]

    cf.CFMachPortCreateRunLoopSource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
    cf.CFMachPortCreateRunLoopSource.restype = ctypes.c_void_p
    cf.CFRunLoopGetCurrent.argtypes = []
    cf.CFRunLoopGetCurrent.restype = ctypes.c_void_p
    cf.CFRunLoopAddSource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    cf.CFRunLoopRun.argtypes = []

    kCFRunLoopCommonModes = ctypes.c_void_p.in_dll(cf, "kCFRunLoopCommonModes")

    if self_test:
        print("macOS CoreGraphics & CoreFoundation bindings verified OK.")
        return 0

    notified_once = False
    tap_ref: list[ctypes.c_void_p] = []

    @CGEventTapCallBack
    def _on_event(_proxy: int, event_type: int, event: int, _refcon: int) -> int | None:
        nonlocal notified_once
        if event_type in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
            if tap_ref:
                cg.CGEventTapEnable(tap_ref[0], True)
            return event

        if event_type != kCGEventKeyDown or not event:
            return event

        flags = cg.CGEventGetFlags(event)
        has_cmd = bool(flags & kCGEventFlagMaskCommand)
        has_opt = bool(flags & kCGEventFlagMaskAlternate)
        has_ctrl = bool(flags & kCGEventFlagMaskControl)
        if not has_cmd or has_ctrl:
            return event

        keycode = int(cg.CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode))

        # Allow Cmd+Option+Q as deliberate true-quit shortcut!
        if keycode == KC_Q and has_opt:
            return event

        if keycode == KC_Q and not has_opt:
            front = _get_frontmost_app()
            if front in AGY_APP_NAMES:
                msg = None
                if not notified_once:
                    notified_once = True
                    msg = "已拦截 Cmd+Q 并隐藏至后台保护 AI 任务；点 Dock 图标恢复，按 Cmd+Option+Q 彻底退出。"
                _hide_app(front, msg)
                return None
            if front in TERMINAL_APP_NAMES and _any_agy_cli_running():
                _hide_app(front, "检测到 agy CLI 正在运行，已隐藏终端窗口防止任务中断（按 Cmd+Option+Q 可强制退出）。")
                return None

        if keycode == KC_W and not has_opt:
            front = _get_frontmost_app()
            if front in TERMINAL_APP_NAMES and _any_agy_cli_running():
                _hide_app(front, "检测到 agy CLI 正在运行，已隐藏终端保护会话。")
                return None

        return event

    mask = 1 << kCGEventKeyDown
    # Retry loop in case user hasn't toggled Accessibility permission yet
    while True:
        tap = cg.CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionDefault,
            mask,
            _on_event,
            None,
        )
        if tap:
            tap_ref.append(tap)
            break
        time.sleep(5.0)

    source = cf.CFMachPortCreateRunLoopSource(None, tap_ref[0], 0)
    loop = cf.CFRunLoopGetCurrent()
    cf.CFRunLoopAddSource(loop, source, kCFRunLoopCommonModes)
    cg.CGEventTapEnable(tap_ref[0], True)
    cf.CFRunLoopRun()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Antigravity Close Guard for macOS")
    parser.add_argument("--self-test", action="store_true", help="Verify macOS CoreGraphics bindings")
    parser.add_argument("--quit", action="store_true", help="Completely quit Antigravity / Antigravity IDE")
    parser.add_argument("--restore", action="store_true", help="Activate and restore Antigravity window")
    parser.add_argument("--branch", action="store_true", help="Open visual Conversation Brancher Studio UI")
    args = parser.parse_args()

    if args.self_test:
        return run_daemon(self_test=True)
    if args.quit:
        return quit_antigravity_completely()
    if args.restore:
        return restore_antigravity()
    if args.branch:
        return open_branch_gui()
    return run_daemon(self_test=False)


if __name__ == "__main__":
    raise SystemExit(main())
