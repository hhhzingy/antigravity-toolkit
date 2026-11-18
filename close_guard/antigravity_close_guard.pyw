# -*- coding: utf-8 -*-
"""
Antigravity Close Guard (Windows 10/11)
---------------------------------------
Zero-intrusion close-button & Alt+F4 interceptor for Google Antigravity.
- Enforces Windows logon auto-start automatically on startup (always enabled).
- Clicking top-right 'X' (or pressing Alt+F4) on any Antigravity main window
  immediately hides the window to the System Tray (no taskbar icon, all active
  conversations, subagents, and background tasks keep running uninterrupted).
- Left-clicking the System Tray icon restores & focuses the Antigravity window.
- Right-clicking the System Tray icon provides:
    * 显示 Antigravity 窗口
    * 分支克隆对话 (Branch)...
    * Quit (the ONLY way to completely exit Antigravity)

Runs silently via pythonw.exe with zero third-party dependencies (pure Win32).
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import winreg

# ---------------------------------------------------------------------------
# 1. Per-Monitor DPI Awareness V2 (must run before any Win32 GUI/Hook calls)
# ---------------------------------------------------------------------------
if sys.platform != "win32":
    sys.exit(0)

try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# 2. Win32 Constants & 64-bit Safe Type Definitions
# ---------------------------------------------------------------------------
LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_TIMER = 0x0113
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_USER = 0x0400

WM_TRAYICON = WM_USER + 20
WM_APP_HIDE_TO_TRAY = WM_USER + 21
WM_APP_SYNC_TRAY = WM_USER + 22

TIMER_SYNC_ID = 1
TIMER_SYNC_MS = 1500

VK_F4 = 0x73
LLKHF_ALTDOWN = 0x20

GA_ROOT = 2
GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
DWMWA_EXTENDED_FRAME_BOUNDS = 9

PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9

# Shell_NotifyIcon constants
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIIF_INFO = 0x00000001

# Menu flags
MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
TPM_RIGHTBUTTON = 0x0002
TPM_BOTTOMALIGN = 0x0020
TPM_NONOTIFY = 0x0080
TPM_RETURNCMD = 0x0100

# Tray Context Menu Command IDs
IDM_RESTORE_WINDOWS = 1001
IDM_BRANCH_CONVERSATION = 1002
IDM_QUIT_ANTIGRAVITY = 1003

ERROR_ALREADY_EXISTS = 183

# Caption Close Button geometry at 96 DPI (Windows 11 Electron titleBarOverlay)
CLOSE_BTN_WIDTH_96DPI = 46
CLOSE_BTN_HEIGHT_96DPI = 34

RUN_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_REG_NAME = "AntigravityCloseGuard"


# ---------------------------------------------------------------------------
# 3. Win32 Structures & Full 64-bit DLL Prototypes
# ---------------------------------------------------------------------------
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, LPARAM)
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, LPARAM)


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32
dwmapi = ctypes.windll.dwmapi

user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, WPARAM, LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, wintypes.LPVOID]
user32.SetTimer.restype = ctypes.c_size_t
user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
user32.KillTimer.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wintypes.ATOM
user32.CreatePopupMenu.argtypes = []
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.AppendMenuW.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.LPVOID
]
user32.TrackPopupMenu.restype = wintypes.BOOL
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.DestroyMenu.restype = wintypes.BOOL
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadIconW.restype = wintypes.HICON
user32.GetDpiForWindow.argtypes = [wintypes.HWND]
user32.GetDpiForWindow.restype = wintypes.UINT
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG
user32.EnumWindows.argtypes = [WNDENUMPROC, LPARAM]
user32.EnumWindows.restype = wintypes.BOOL

dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD
]
dwmapi.DwmGetWindowAttribute.restype = ctypes.HRESULT

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetLastError.argtypes = []
kernel32.GetLastError.restype = wintypes.DWORD
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
kernel32.TerminateProcess.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
shell32.ExtractIconExW.argtypes = [
    wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.HICON), wintypes.UINT
]
shell32.ExtractIconExW.restype = wintypes.UINT


# ---------------------------------------------------------------------------
# 4. Antigravity Close Guard Implementation (Tray-Only + Always-On Autostart)
# ---------------------------------------------------------------------------
class AntigravityCloseGuard:
    def __init__(self) -> None:
        self.hinstance = kernel32.GetModuleHandleW(None)
        self.msg_hwnd: wintypes.HWND | None = None
        self.mouse_hook: wintypes.HHOOK | None = None
        self.kbd_hook: wintypes.HHOOK | None = None
        self.hicon_small: wintypes.HICON | None = None

        self.swallow_next_lbuttonup = False
        self.tray_added = False
        self.notified_once = False
        self.quitting_agy = False

        self.hidden_hwnds: set[int] = set()
        self.pid_cache: dict[int, bool] = {}

        # Keep C callback references alive against GC
        self._wndproc_ref = WNDPROC(self._wnd_proc)
        self._mouse_proc_ref = HOOKPROC(self._mouse_hook_proc)
        self._kbd_proc_ref = HOOKPROC(self._kbd_hook_proc)

    # ---- Always-On Auto-start Registration --------------------------------
    def _get_pythonw_command(self) -> str:
        exe = Path(sys.executable)
        if exe.name.lower() == "python.exe":
            pw = exe.with_name("pythonw.exe")
            if pw.exists():
                exe = pw
        script = Path(__file__).resolve()
        return f'"{exe}" "{script}"'

    def _ensure_autostart(self) -> None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, RUN_REG_NAME, 0, winreg.REG_SZ, self._get_pythonw_command())
        except OSError:
            pass

    # ---- Antigravity Window Detection -------------------------------------
    def _is_antigravity_pid(self, pid: int) -> bool:
        if pid <= 0:
            return False
        cached = self.pid_cache.get(pid)
        if cached is not None:
            return cached

        is_agy = False
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if hproc:
            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(size)):
                    is_agy = buf.value.lower().endswith("\\antigravity.exe")
            finally:
                kernel32.CloseHandle(hproc)

        if len(self.pid_cache) > 512:
            self.pid_cache.clear()
        self.pid_cache[pid] = is_agy
        return is_agy

    def _is_antigravity_main_window(self, hwnd: int | None, require_large: bool = True) -> bool:
        if not hwnd or not user32.IsWindow(hwnd):
            return False
        if user32.GetWindow(hwnd, GW_OWNER):
            return False
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if ex_style & WS_EX_TOOLWINDOW:
            return False

        cls_buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls_buf, 64)
        if cls_buf.value != "Chrome_WidgetWin_1":
            return False

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not self._is_antigravity_pid(pid.value):
            return False

        if require_large and not user32.IsIconic(hwnd):
            rect = self._get_visible_frame(hwnd)
            if (rect.right - rect.left) < 320 or (rect.bottom - rect.top) < 200:
                return False
        return True

    def _get_visible_frame(self, hwnd: int) -> wintypes.RECT:
        frame = wintypes.RECT()
        hr = dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(frame), ctypes.sizeof(frame)
        )
        if hr != 0:
            user32.GetWindowRect(hwnd, ctypes.byref(frame))
        return frame

    def _is_point_on_close_button(self, hwnd: int, x: int, y: int) -> bool:
        frame = self._get_visible_frame(hwnd)
        dpi = user32.GetDpiForWindow(hwnd) or 96
        scale = dpi / 96.0
        btn_w = round(CLOSE_BTN_WIDTH_96DPI * scale)
        btn_h = round(CLOSE_BTN_HEIGHT_96DPI * scale)
        return (frame.right - btn_w <= x <= frame.right + 2) and (frame.top - 2 <= y <= frame.top + btn_h)

    def _find_visible_antigravity_windows(self) -> list[int]:
        found: list[int] = []

        def _enum_cb(h: int, _: int) -> bool:
            if user32.IsWindowVisible(h) and self._is_antigravity_main_window(h, require_large=False):
                found.append(int(h))
            return True

        enum_proc = WNDENUMPROC(_enum_cb)
        user32.EnumWindows(enum_proc, 0)
        return found

    # ---- Low-Level Hooks (Intercept 'X' & Alt+F4 -> Hide to Tray) ---------
    def _mouse_hook_proc(self, nCode: int, wParam: int, lParam: int) -> int:
        if nCode >= 0 and not self.quitting_agy:
            if wParam == WM_LBUTTONDOWN:
                info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                hwnd_pt = user32.WindowFromPoint(info.pt)
                if hwnd_pt:
                    hwnd_root = user32.GetAncestor(hwnd_pt, GA_ROOT)
                    if self._is_antigravity_main_window(hwnd_root) and self._is_point_on_close_button(
                        hwnd_root, info.pt.x, info.pt.y
                    ):
                        self.swallow_next_lbuttonup = True
                        if self.msg_hwnd:
                            user32.PostMessageW(self.msg_hwnd, WM_APP_HIDE_TO_TRAY, hwnd_root, 0)
                        return 1
            elif wParam == WM_LBUTTONUP and self.swallow_next_lbuttonup:
                self.swallow_next_lbuttonup = False
                return 1

        return user32.CallNextHookEx(self.mouse_hook, nCode, wParam, lParam)

    def _kbd_hook_proc(self, nCode: int, wParam: int, lParam: int) -> int:
        if nCode >= 0 and not self.quitting_agy and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            info = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if info.vkCode == VK_F4 and (info.flags & LLKHF_ALTDOWN):
                fg = user32.GetForegroundWindow()
                if self._is_antigravity_main_window(fg):
                    if self.msg_hwnd:
                        user32.PostMessageW(self.msg_hwnd, WM_APP_HIDE_TO_TRAY, fg, 0)
                    return 1
        return user32.CallNextHookEx(self.kbd_hook, nCode, wParam, lParam)

    # ---- Hide / Restore / Branch / Tray-Only Quit -------------------------
    def _hide_to_tray(self, hwnd: int) -> None:
        if not user32.IsWindow(hwnd):
            return
        self._ensure_tray_icon()
        self.hidden_hwnds.add(int(hwnd))
        user32.ShowWindow(hwnd, SW_HIDE)
        if not self.notified_once:
            self.notified_once = True
            self._show_balloon(
                "Antigravity 已隐藏到系统托盘",
                "后台对话与任务继续运行；左键单击托盘图标恢复窗口，右键点击 Quit 彻底退出。",
            )

    def _restore_all_windows(self) -> None:
        restored_any = False
        for hwnd in list(self.hidden_hwnds):
            if user32.IsWindow(hwnd):
                user32.ShowWindow(hwnd, SW_SHOW)
                if user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, SW_RESTORE)
                user32.SetForegroundWindow(hwnd)
                restored_any = True
        self.hidden_hwnds.clear()

        if not restored_any:
            for h in self._find_visible_antigravity_windows():
                user32.ShowWindow(h, SW_SHOW)
                if user32.IsIconic(h):
                    user32.ShowWindow(h, SW_RESTORE)
                user32.SetForegroundWindow(h)

    def _open_branch_gui(self) -> None:
        branch_script = Path.home() / "mcp-gui-workspace" / "antigravity-branch" / "branch_conversation.py"
        if not branch_script.exists():
            self._show_balloon(
                "未检测到对话分支工具",
                "请先安装 branch_conversation 模块后再使用此功能。",
            )
            return
        exe = Path(sys.executable)
        if exe.name.lower() == "python.exe":
            pw = exe.with_name("pythonw.exe")
            if pw.exists():
                exe = pw
        subprocess.Popen([str(exe), str(branch_script), "--gui"])

    def _quit_antigravity_completely(self) -> None:
        if self.quitting_agy:
            return
        self.quitting_agy = True

        target_hwnds = set(self.hidden_hwnds) | set(self._find_visible_antigravity_windows())
        self.hidden_hwnds.clear()

        def _quit_worker() -> None:
            try:
                pids: set[int] = set()
                for h in target_hwnds:
                    if user32.IsWindow(h):
                        pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
                        if pid.value:
                            pids.add(pid.value)
                        user32.PostMessageW(h, WM_CLOSE, 0, 0)

                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    still_open = [h for h in target_hwnds if user32.IsWindow(h)]
                    if not still_open:
                        break
                    time.sleep(0.15)

                time.sleep(0.25)
                for pid in pids:
                    hproc = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
                    if hproc:
                        try:
                            kernel32.TerminateProcess(hproc, 0)
                        finally:
                            kernel32.CloseHandle(hproc)
            finally:
                self.pid_cache.clear()
                self.quitting_agy = False
                if self.msg_hwnd:
                    user32.PostMessageW(self.msg_hwnd, WM_APP_SYNC_TRAY, 0, 0)

        threading.Thread(target=_quit_worker, daemon=True).start()

    # ---- System Tray Icon Management --------------------------------------
    def _load_icon(self) -> None:
        if self.hicon_small:
            return
        agy_exe = (
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Programs"
            / "antigravity"
            / "Antigravity.exe"
        )
        if agy_exe.exists():
            large = wintypes.HICON()
            small = wintypes.HICON()
            count = shell32.ExtractIconExW(
                str(agy_exe), 0, ctypes.byref(large), ctypes.byref(small), 1
            )
            if count > 0 and (small.value or large.value):
                self.hicon_small = small if small.value else large
                return
        self.hicon_small = user32.LoadIconW(
            None, ctypes.cast(ctypes.c_void_p(32512), wintypes.LPCWSTR)
        )

    def _make_nid(self) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.msg_hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self.hicon_small
        nid.szTip = "Antigravity (左键显示窗口 / 右键分支或退出)"
        return nid

    def _ensure_tray_icon(self) -> None:
        if self.tray_added or not self.msg_hwnd:
            return
        self._load_icon()
        nid = self._make_nid()
        if shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            self.tray_added = True

    def _remove_tray_icon(self) -> None:
        if not self.tray_added or not self.msg_hwnd:
            return
        nid = self._make_nid()
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        self.tray_added = False

    def _sync_tray_visibility(self) -> None:
        if self.quitting_agy:
            return
        for h in list(self.hidden_hwnds):
            if not user32.IsWindow(h) or user32.IsWindowVisible(h):
                self.hidden_hwnds.discard(h)

        has_agy = bool(self.hidden_hwnds) or bool(self._find_visible_antigravity_windows())
        if has_agy and not self.tray_added:
            self._ensure_tray_icon()
        elif not has_agy and self.tray_added:
            self._remove_tray_icon()
            self.notified_once = False

    def _show_balloon(self, title: str, msg: str) -> None:
        if not self.msg_hwnd or not self.tray_added:
            return
        nid = self._make_nid()
        nid.uFlags |= NIF_INFO
        nid.szInfoTitle = title[:63]
        nid.szInfo = msg[:255]
        nid.dwInfoFlags = NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _show_tray_menu(self) -> None:
        hmenu = user32.CreatePopupMenu()
        if not hmenu:
            return
        try:
            user32.AppendMenuW(hmenu, MF_STRING, IDM_RESTORE_WINDOWS, "显示 Antigravity 窗口")
            user32.AppendMenuW(hmenu, MF_STRING, IDM_BRANCH_CONVERSATION, "分支克隆对话 (Branch)...")
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(hmenu, MF_STRING, IDM_QUIT_ANTIGRAVITY, "Quit")

            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(self.msg_hwnd)
            cmd = user32.TrackPopupMenu(
                hmenu,
                TPM_RIGHTBUTTON | TPM_BOTTOMALIGN | TPM_NONOTIFY | TPM_RETURNCMD,
                pt.x,
                pt.y,
                0,
                self.msg_hwnd,
                None,
            )
            user32.PostMessageW(self.msg_hwnd, 0, 0, 0)

            if cmd == IDM_RESTORE_WINDOWS:
                self._restore_all_windows()
            elif cmd == IDM_BRANCH_CONVERSATION:
                self._open_branch_gui()
            elif cmd == IDM_QUIT_ANTIGRAVITY:
                self._quit_antigravity_completely()
        finally:
            user32.DestroyMenu(hmenu)

    # ---- Hidden Message Window & Main Loop --------------------------------
    def _wnd_proc(self, hwnd: int, msg: int, wParam: int, lParam: int) -> int:
        if msg == WM_APP_HIDE_TO_TRAY:
            self._hide_to_tray(int(wParam))
            return 0
        if msg in (WM_TIMER, WM_APP_SYNC_TRAY):
            self._sync_tray_visibility()
            return 0
        if msg == WM_TRAYICON:
            if lParam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self._restore_all_windows()
                return 0
            if lParam == WM_RBUTTONUP:
                self._show_tray_menu()
                return 0
        if msg == WM_DESTROY:
            self._restore_all_windows()
            self._remove_tray_icon()
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wParam, lParam)

    def run(self) -> None:
        mutex = kernel32.CreateMutexW(None, False, "Local\\AntigravityCloseGuard_v1")
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            return

        # Always enforce logon auto-start by default
        self._ensure_autostart()

        cls_name = "AntigravityCloseGuardHiddenWnd"
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = self.hinstance
        wc.lpszClassName = cls_name
        user32.RegisterClassExW(ctypes.byref(wc))

        self.msg_hwnd = user32.CreateWindowExW(
            0, cls_name, "Antigravity Close Guard", 0, 0, 0, 0, 0, None, None, self.hinstance, None
        )
        if not self.msg_hwnd:
            return

        self._sync_tray_visibility()
        user32.SetTimer(self.msg_hwnd, TIMER_SYNC_ID, TIMER_SYNC_MS, None)

        self.mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc_ref, self.hinstance, 0)
        self.kbd_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kbd_proc_ref, self.hinstance, 0)

        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            if self.msg_hwnd:
                user32.KillTimer(self.msg_hwnd, TIMER_SYNC_ID)
            if self.mouse_hook:
                user32.UnhookWindowsHookEx(self.mouse_hook)
            if self.kbd_hook:
                user32.UnhookWindowsHookEx(self.kbd_hook)
            self._restore_all_windows()
            self._remove_tray_icon()
            if mutex:
                kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    guard = AntigravityCloseGuard()
    guard.run()
