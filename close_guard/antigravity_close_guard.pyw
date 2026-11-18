# -*- coding: utf-8 -*-
"""
Antigravity Close Guard (Windows 10/11)
---------------------------------------
Zero-intrusion close-button & Alt+F4 interceptor for Google Antigravity, paired
with a sleek Modern Windows 11 Rounded Flyout Tray Card (pure Win32 + DWM + GDI/GDI+).

- Attaches automatically to the interactive desktop (WinSta0\\Default) and enables
  Per-Monitor DPI Awareness V2 before creating windows or hooks.
- Enforces Windows logon auto-start automatically on startup (always enabled).
- Clicking top-right 'X' (or pressing Alt+F4) on any Antigravity main window
  immediately hides the window to the System Tray (no taskbar icon; all active
  conversations, subagents, and background tasks keep running uninterrupted).
- Left-clicking the System Tray icon restores & focuses the Antigravity window.
- Right-clicking the System Tray icon opens a hardware-rounded Win11 Flyout Card:
    * Header: Antigravity 守护中 · 点关闭自动驻留后台
    * 显示 Antigravity 窗口       (单击托盘)
    * 对话分支克隆...             (任意轮次)
    * 彻底退出 Antigravity        (Quit)
- Supports `--show-menu-preview` / `--hide-menu-preview` (and custom Win32 messages
  `WM_APP_SHOW_MENU_PREVIEW = WM_USER + 25` / `WM_APP_HIDE_MENU_PREVIEW = WM_USER + 26`
  posted to `AntigravityCloseGuardHiddenWnd`) for live visual inspection.

Runs silently via pythonw.exe with zero third-party dependencies and 0.0% idle CPU.
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
# 1. Interactive Desktop Attachment & Per-Monitor DPI Awareness V2
#    (must run before any Win32 GUI/Hook calls)
# ---------------------------------------------------------------------------
if sys.platform != "win32":
    sys.exit(0)

try:
    _u32 = ctypes.windll.user32
    _u32.OpenDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _u32.OpenDesktopW.restype = wintypes.HANDLE
    _u32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
    _u32.SetThreadDesktop.restype = wintypes.BOOL
    _hdesk_default = _u32.OpenDesktopW("Default", 0, False, 0x01FF)
    if _hdesk_default:
        _u32.SetThreadDesktop(_hdesk_default)
except Exception:
    pass

try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# 2. Win32 / DWM / GDI / GDI+ Constants & 64-bit Safe Type Definitions
# ---------------------------------------------------------------------------
LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
PTR_MASK = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14

WM_DESTROY = 0x0002
WM_ACTIVATE = 0x0006
WM_KILLFOCUS = 0x0008
WM_PAINT = 0x000F
WM_CLOSE = 0x0010
WM_ERASEBKGND = 0x0014
WM_SETCURSOR = 0x0020
WM_CONTEXTMENU = 0x007B
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_TIMER = 0x0113
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MOUSELEAVE = 0x02A3
WM_DPICHANGED = 0x02E0
WM_USER = 0x0400

WA_INACTIVE = 0

WM_TRAYICON = WM_USER + 20             # 0x0414
WM_APP_HIDE_TO_TRAY = WM_USER + 21     # 0x0415
WM_APP_SYNC_TRAY = WM_USER + 22        # 0x0416
WM_APP_EXEC_CMD = WM_USER + 23         # 0x0417
WM_APP_SHOW_MENU_PREVIEW = WM_USER + 25  # 0x0419 (1049)
WM_APP_HIDE_MENU_PREVIEW = WM_USER + 26  # 0x041A (1050)

TIMER_SYNC_ID = 1
TIMER_SYNC_MS = 1500
TIMER_PREVIEW_AUTOHIDE_ID = 2
TIMER_PREVIEW_STANDALONE_MS = 3500
TIMER_PREVIEW_LIVE_SAFETY_MS = 15000

VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_UP = 0x26
VK_DOWN = 0x28
VK_F4 = 0x73
LLKHF_ALTDOWN = 0x20

GA_ROOT = 2
GW_OWNER = 4
GWL_EXSTYLE = -20

CS_VREDRAW = 0x0001
CS_HREDRAW = 0x0002
CS_DROPSHADOW = 0x00020000

WS_POPUP = 0x80000000
WS_CLIPCHILDREN = 0x02000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080

HWND_TOPMOST = wintypes.HWND(-1 & PTR_MASK)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9

MONITOR_DEFAULTTONEAREST = 2
MDT_EFFECTIVE_DPI = 0
TME_LEAVE = 0x00000002

IDC_ARROW_ID = 32512
IDC_HAND_ID = 32649
DI_NORMAL = 0x0003

# DWM Attributes (Windows 11)
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWCP_ROUND = 2
DWM_BORDER_E5E7EB = 0x00EBE7E5  # COLORREF 0x00BBGGRR for #E5E7EB

# GDI Constants
SRCCOPY = 0x00CC0020
TRANSPARENT = 1
DEFAULT_CHARSET = 1
CLEARTYPE_QUALITY = 5
DT_SINGLELINE = 0x0020
DT_VCENTER = 0x0004
DT_RIGHT = 0x0002
DT_NOPREFIX = 0x0800

# GDI+ Constants
SMOOTHING_MODE_ANTIALIAS = 4
PIXEL_OFFSET_MODE_HALF = 4
UNIT_PIXEL = 2
LINE_CAP_ROUND = 2
LINE_JOIN_ROUND = 2

PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Shell_NotifyIcon constants
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIIF_INFO = 0x00000001

# Tray Flyout Action Command IDs
IDM_RESTORE_WINDOWS = 1001
IDM_BRANCH_CONVERSATION = 1002
IDM_QUIT_ANTIGRAVITY = 1003
ACTION_ORDER = (IDM_RESTORE_WINDOWS, IDM_BRANCH_CONVERSATION, IDM_QUIT_ANTIGRAVITY)

ERROR_ALREADY_EXISTS = 183

# Caption Close Button geometry at 96 DPI (Windows 11 Electron titleBarOverlay)
CLOSE_BTN_WIDTH_96DPI = 46
CLOSE_BTN_HEIGHT_96DPI = 34

# Flyout Card base geometry at 96 DPI
FLYOUT_WIDTH_96DPI = 280
FLYOUT_HEIGHT_96DPI = 220

HIDDEN_WND_CLASS = "AntigravityCloseGuardHiddenWnd"
FLYOUT_WND_CLASS = "AntigravityTrayFlyoutWnd"

RUN_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_REG_NAME = "AntigravityCloseGuard"


def _rgb(r: int, g: int, b: int) -> int:
    return (r & 0xFF) | ((g & 0xFF) << 8) | ((b & 0xFF) << 16)


def _argb(a: int, r: int, g: int, b: int) -> int:
    return ((a & 0xFF) << 24) | ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)


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


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("hwndTrack", wintypes.HWND),
        ("dwHoverTime", wintypes.DWORD),
    ]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", wintypes.HDC),
        ("fErase", wintypes.BOOL),
        ("rcPaint", wintypes.RECT),
        ("fRestore", wintypes.BOOL),
        ("fIncUpdate", wintypes.BOOL),
        ("rgbReserved", wintypes.BYTE * 32),
    ]


class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [
        ("GdiplusVersion", ctypes.c_uint32),
        ("DebugEventCallback", ctypes.c_void_p),
        ("SuppressBackgroundThread", wintypes.BOOL),
        ("SuppressExternalCodecs", wintypes.BOOL),
    ]


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32
dwmapi = ctypes.windll.dwmapi
gdi32 = ctypes.windll.gdi32
gdip = ctypes.windll.gdiplus
try:
    shcore = ctypes.windll.shcore
except Exception:
    shcore = None

# user32 prototypes
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
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.restype = wintypes.BOOL
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
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT
]
user32.SetWindowPos.restype = wintypes.BOOL
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.SetFocus.argtypes = [wintypes.HWND]
user32.SetFocus.restype = wintypes.HWND
user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT), wintypes.BOOL]
user32.InvalidateRect.restype = wintypes.BOOL
user32.UpdateWindow.argtypes = [wintypes.HWND]
user32.UpdateWindow.restype = wintypes.BOOL
user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
user32.BeginPaint.restype = wintypes.HDC
user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
user32.EndPaint.restype = wintypes.BOOL
user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
user32.FillRect.restype = ctypes.c_int
user32.DrawTextW.argtypes = [
    wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.RECT), wintypes.UINT
]
user32.DrawTextW.restype = ctypes.c_int
user32.TrackMouseEvent.argtypes = [ctypes.POINTER(TRACKMOUSEEVENT)]
user32.TrackMouseEvent.restype = wintypes.BOOL
user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
user32.MonitorFromPoint.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.GetMonitorInfoW.restype = wintypes.BOOL
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
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadIconW.restype = wintypes.HICON
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.DestroyIcon.restype = wintypes.BOOL
user32.DrawIconEx.argtypes = [
    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HICON,
    ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HBRUSH, wintypes.UINT,
]
user32.DrawIconEx.restype = wintypes.BOOL
user32.PrivateExtractIconsW.argtypes = [
    wintypes.LPCWSTR, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.UINT), wintypes.UINT, wintypes.UINT,
]
user32.PrivateExtractIconsW.restype = wintypes.UINT
user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadCursorW.restype = wintypes.HANDLE
user32.SetCursor.argtypes = [wintypes.HANDLE]
user32.SetCursor.restype = wintypes.HANDLE
user32.GetDpiForWindow.argtypes = [wintypes.HWND]
user32.GetDpiForWindow.restype = wintypes.UINT
user32.GetDpiForSystem.argtypes = []
user32.GetDpiForSystem.restype = wintypes.UINT
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG
user32.EnumWindows.argtypes = [WNDENUMPROC, LPARAM]
user32.EnumWindows.restype = wintypes.BOOL

if shcore is not None:
    try:
        shcore.GetDpiForMonitor.argtypes = [
            wintypes.HMONITOR, ctypes.c_int, ctypes.POINTER(wintypes.UINT), ctypes.POINTER(wintypes.UINT)
        ]
        shcore.GetDpiForMonitor.restype = ctypes.HRESULT
    except Exception:
        shcore = None

# dwmapi prototypes
dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD
]
dwmapi.DwmGetWindowAttribute.restype = ctypes.HRESULT
dwmapi.DwmSetWindowAttribute.argtypes = [
    wintypes.HWND, wintypes.DWORD, wintypes.LPCVOID, wintypes.DWORD
]
dwmapi.DwmSetWindowAttribute.restype = ctypes.HRESULT

# gdi32 prototypes
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.BitBlt.argtypes = [
    wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
gdi32.SetBkMode.restype = ctypes.c_int
gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
gdi32.SetTextColor.restype = wintypes.COLORREF
gdi32.CreateFontW.argtypes = [
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR,
]
gdi32.CreateFontW.restype = wintypes.HFONT

# gdiplus prototypes (built-in Windows OS DLL, zero external dependencies)
gdip.GdiplusStartup.argtypes = [
    ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(GdiplusStartupInput), ctypes.c_void_p
]
gdip.GdiplusStartup.restype = ctypes.c_int
gdip.GdiplusShutdown.argtypes = [ctypes.c_size_t]
gdip.GdiplusShutdown.restype = None
gdip.GdipCreateFromHDC.argtypes = [wintypes.HDC, ctypes.POINTER(ctypes.c_void_p)]
gdip.GdipDeleteGraphics.argtypes = [ctypes.c_void_p]
gdip.GdipSetSmoothingMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
gdip.GdipSetPixelOffsetMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
gdip.GdipCreateSolidFill.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
gdip.GdipDeleteBrush.argtypes = [ctypes.c_void_p]
gdip.GdipCreatePen1.argtypes = [
    ctypes.c_uint32, ctypes.c_float, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)
]
gdip.GdipSetPenStartCap.argtypes = [ctypes.c_void_p, ctypes.c_int]
gdip.GdipSetPenEndCap.argtypes = [ctypes.c_void_p, ctypes.c_int]
gdip.GdipSetPenLineJoin.argtypes = [ctypes.c_void_p, ctypes.c_int]
gdip.GdipDeletePen.argtypes = [ctypes.c_void_p]
gdip.GdipFillEllipse.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float
]
gdip.GdipDrawEllipse.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float
]
gdip.GdipDrawLine.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float
]
gdip.GdipDrawArc.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p,
    ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
]
gdip.GdipDrawBezier.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p,
    ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
    ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
]
gdip.GdipCreatePath.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
gdip.GdipDeletePath.argtypes = [ctypes.c_void_p]
gdip.GdipAddPathArc.argtypes = [
    ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float
]
gdip.GdipClosePathFigure.argtypes = [ctypes.c_void_p]
gdip.GdipFillPath.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
gdip.GdipDrawPath.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]

# kernel32 prototypes
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

# shell32 prototypes
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
shell32.ExtractIconExW.argtypes = [
    wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.HICON), wintypes.UINT
]
shell32.ExtractIconExW.restype = wintypes.UINT


# ---------------------------------------------------------------------------
# 4. GDI+ Drawing Helpers (Anti-Aliased Rounded Pills, Status Dot & Icons)
# ---------------------------------------------------------------------------
def _make_round_rect_path(x: float, y: float, w: float, h: float, r: float) -> ctypes.c_void_p:
    path = ctypes.c_void_p()
    gdip.GdipCreatePath(0, ctypes.byref(path))
    d = max(1.0, min(r * 2.0, w, h))
    gdip.GdipAddPathArc(path, x, y, d, d, 180.0, 90.0)
    gdip.GdipAddPathArc(path, x + w - d, y, d, d, 270.0, 90.0)
    gdip.GdipAddPathArc(path, x + w - d, y + h - d, d, d, 0.0, 90.0)
    gdip.GdipAddPathArc(path, x, y + h - d, d, d, 90.0, 90.0)
    gdip.GdipClosePathFigure(path)
    return path


def _gdip_fill_round_rect(
    g: ctypes.c_void_p, x: float, y: float, w: float, h: float, r: float, color_argb: int
) -> None:
    path = _make_round_rect_path(x, y, w, h, r)
    brush = ctypes.c_void_p()
    gdip.GdipCreateSolidFill(color_argb, ctypes.byref(brush))
    gdip.GdipFillPath(g, brush, path)
    gdip.GdipDeleteBrush(brush)
    gdip.GdipDeletePath(path)


def _gdip_stroke_round_rect(
    g: ctypes.c_void_p, x: float, y: float, w: float, h: float, r: float, color_argb: int, width: float
) -> None:
    path = _make_round_rect_path(x, y, w, h, r)
    pen = ctypes.c_void_p()
    gdip.GdipCreatePen1(color_argb, width, UNIT_PIXEL, ctypes.byref(pen))
    gdip.GdipSetPenLineJoin(pen, LINE_JOIN_ROUND)
    gdip.GdipDrawPath(g, pen, path)
    gdip.GdipDeletePen(pen)
    gdip.GdipDeletePath(path)


def _gdip_make_pen(color_argb: int, width: float) -> ctypes.c_void_p:
    pen = ctypes.c_void_p()
    gdip.GdipCreatePen1(color_argb, width, UNIT_PIXEL, ctypes.byref(pen))
    gdip.GdipSetPenStartCap(pen, LINE_CAP_ROUND)
    gdip.GdipSetPenEndCap(pen, LINE_CAP_ROUND)
    gdip.GdipSetPenLineJoin(pen, LINE_JOIN_ROUND)
    return pen


# ---------------------------------------------------------------------------
# 5. Antigravity Close Guard + Modern Win11 Tray Flyout Implementation
# ---------------------------------------------------------------------------
class AntigravityCloseGuard:
    def __init__(self, preview_only: bool = False) -> None:
        self.preview_only = preview_only
        self.hinstance = kernel32.GetModuleHandleW(None)
        self.msg_hwnd: wintypes.HWND | None = None
        self.flyout_hwnd: wintypes.HWND | None = None
        self.mouse_hook: wintypes.HHOOK | None = None
        self.kbd_hook: wintypes.HHOOK | None = None
        self.hicon_small: wintypes.HICON | None = None

        self.cursor_arrow = user32.LoadCursorW(
            None, ctypes.cast(ctypes.c_void_p(IDC_ARROW_ID), wintypes.LPCWSTR)
        )
        self.cursor_hand = user32.LoadCursorW(
            None, ctypes.cast(ctypes.c_void_p(IDC_HAND_ID), wintypes.LPCWSTR)
        )

        self.swallow_next_lbuttonup = False
        self.tray_added = False
        self.notified_once = False
        self.quitting_agy = False

        # Flyout state & cached DPI resources
        self.flyout_class_registered = False
        self.flyout_visible = False
        self.flyout_dpi = 96
        self.flyout_dwm_rounded = False
        self.hover_item_id = 0
        self.pressed_item_id = 0
        self.tracking_mouse_leave = False
        self._gdip_token = ctypes.c_size_t(0)
        self._header_icons_by_size: dict[int, wintypes.HICON] = {}
        self._fonts_by_dpi: dict[int, tuple[wintypes.HFONT, ...]] = {}

        self.hidden_hwnds: set[int] = set()
        self.pid_cache: dict[int, bool] = {}

        # Keep C callback references alive against GC
        self._wndproc_ref = WNDPROC(self._wnd_proc)
        self._flyout_wndproc_ref = WNDPROC(self._flyout_wnd_proc)
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

    def _is_point_in_flyout(self, x: int, y: int) -> bool:
        if not self.flyout_visible or not self.flyout_hwnd or not user32.IsWindow(self.flyout_hwnd):
            return False
        rc = wintypes.RECT()
        if not user32.GetWindowRect(self.flyout_hwnd, ctypes.byref(rc)):
            return False
        return (rc.left <= x <= rc.right) and (rc.top <= y <= rc.bottom)

    def _find_visible_antigravity_windows(self) -> list[int]:
        found: list[int] = []

        def _enum_cb(h: int, _: int) -> bool:
            if user32.IsWindowVisible(h) and self._is_antigravity_main_window(h, require_large=False):
                found.append(int(h))
            return True

        enum_proc = WNDENUMPROC(_enum_cb)
        user32.EnumWindows(enum_proc, 0)
        return found

    # ---- Low-Level Hooks (Intercept 'X' & Alt+F4 + Outside Flyout Click) --
    def _mouse_hook_proc(self, nCode: int, wParam: int, lParam: int) -> int:
        if nCode >= 0:
            if self.flyout_visible and wParam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN):
                info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if not self._is_point_in_flyout(info.pt.x, info.pt.y) and self.msg_hwnd:
                    user32.PostMessageW(self.msg_hwnd, WM_APP_HIDE_MENU_PREVIEW, 0, 0)

            if not self.quitting_agy:
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
        if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            info = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if self.flyout_visible and info.vkCode == VK_ESCAPE:
                if self.msg_hwnd:
                    user32.PostMessageW(self.msg_hwnd, WM_APP_HIDE_MENU_PREVIEW, 0, 0)
                return 1
            if not self.quitting_agy and info.vkCode == VK_F4 and (info.flags & LLKHF_ALTDOWN):
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
                "后台对话与任务继续运行；左键单击托盘图标恢复窗口，右键点击彻底退出。",
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
        candidates = [
            Path.home() / "mcp-gui-workspace" / "antigravity-branch" / "branch_conversation.py",
            Path(__file__).resolve().parent.parent / "branch_conversation" / "branch_conversation.py",
        ]
        branch_script = next((p for p in candidates if p.exists()), None)
        if branch_script is None:
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

    def _execute_menu_command(self, cmd: int) -> None:
        if cmd == IDM_RESTORE_WINDOWS:
            self._restore_all_windows()
        elif cmd == IDM_BRANCH_CONVERSATION:
            self._open_branch_gui()
        elif cmd == IDM_QUIT_ANTIGRAVITY:
            self._quit_antigravity_completely()

    # ---- System Tray Icon Management --------------------------------------
    def _get_antigravity_exe_path(self) -> Path:
        return Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "antigravity" / "Antigravity.exe"

    def _load_icon(self) -> None:
        if self.hicon_small:
            return
        agy_exe = self._get_antigravity_exe_path()
        if agy_exe.exists():
            large = wintypes.HICON()
            small = wintypes.HICON()
            count = shell32.ExtractIconExW(
                str(agy_exe), 0, ctypes.byref(large), ctypes.byref(small), 1
            )
            if count > 0 and (small.value or large.value):
                if small.value and large.value:
                    user32.DestroyIcon(large)
                self.hicon_small = small if small.value else large
                return
        self.hicon_small = user32.LoadIconW(
            None, ctypes.cast(ctypes.c_void_p(32512), wintypes.LPCWSTR)
        )

    def _get_header_icon(self, px_size: int) -> wintypes.HICON | None:
        cached = self._header_icons_by_size.get(px_size)
        if cached is not None:
            return cached
        agy_exe = self._get_antigravity_exe_path()
        if agy_exe.exists():
            hicon = wintypes.HICON()
            icon_id = wintypes.UINT()
            extracted = user32.PrivateExtractIconsW(
                str(agy_exe), 0, px_size, px_size, ctypes.byref(hicon), ctypes.byref(icon_id), 1, 0
            )
            if extracted > 0 and hicon.value:
                self._header_icons_by_size[px_size] = hicon
                return hicon
        self._load_icon()
        return self.hicon_small

    def _make_nid(self) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.msg_hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self.hicon_small
        nid.szTip = "Antigravity 守护中 (左键显示窗口 / 右键快捷菜单)"
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
        if self.quitting_agy or self.preview_only:
            return
        for h in list(self.hidden_hwnds):
            if not user32.IsWindow(h) or user32.IsWindowVisible(h):
                self.hidden_hwnds.discard(h)

        has_agy = bool(self.hidden_hwnds) or bool(self._find_visible_antigravity_windows())
        if has_agy and not self.tray_added:
            self._ensure_tray_icon()
        elif not has_agy and self.tray_added:
            self._hide_flyout()
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

    # ---- Modern Windows 11 Rounded Flyout Popup Card ----------------------
    def _ensure_gdiplus(self) -> None:
        if self._gdip_token.value:
            return
        si = GdiplusStartupInput(1, None, False, False)
        gdip.GdiplusStartup(ctypes.byref(self._gdip_token), ctypes.byref(si), None)

    def _get_fonts_for_dpi(self, dpi: int) -> tuple[wintypes.HFONT, ...]:
        cached = self._fonts_by_dpi.get(dpi)
        if cached is not None:
            return cached
        s = dpi / 96.0

        def _mk(px_96: float, weight: int) -> wintypes.HFONT:
            return gdi32.CreateFontW(
                -round(px_96 * s), 0, 0, 0, weight, 0, 0, 0,
                DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, "Microsoft YaHei UI",
            )

        fonts = (
            _mk(13.5, 600),  # 0: header title
            _mk(11.5, 400),  # 1: header status
            _mk(13.0, 400),  # 2: item normal
            _mk(13.0, 500),  # 3: item hover medium
            _mk(11.5, 400),  # 4: right hint
        )
        self._fonts_by_dpi[dpi] = fonts
        return fonts

    def _cleanup_flyout_resources(self) -> None:
        for fonts in self._fonts_by_dpi.values():
            for hf in fonts:
                if hf:
                    gdi32.DeleteObject(hf)
        self._fonts_by_dpi.clear()

        for hico in self._header_icons_by_size.values():
            if hico and hico != self.hicon_small:
                user32.DestroyIcon(hico)
        self._header_icons_by_size.clear()

        if self.flyout_hwnd and user32.IsWindow(self.flyout_hwnd):
            user32.DestroyWindow(self.flyout_hwnd)
        self.flyout_hwnd = None

        if self._gdip_token.value:
            gdip.GdiplusShutdown(self._gdip_token.value)
            self._gdip_token = ctypes.c_size_t(0)

    def _ensure_flyout_window(self) -> bool:
        self._ensure_gdiplus()
        if self.flyout_hwnd and user32.IsWindow(self.flyout_hwnd):
            return True

        if not self.flyout_class_registered:
            wc = WNDCLASSEXW()
            wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
            wc.style = CS_HREDRAW | CS_VREDRAW | CS_DROPSHADOW
            wc.lpfnWndProc = self._flyout_wndproc_ref
            wc.hInstance = self.hinstance
            wc.hCursor = None  # Managed explicitly in WM_SETCURSOR for zero flicker
            wc.hbrBackground = None
            wc.lpszClassName = FLYOUT_WND_CLASS
            user32.RegisterClassExW(ctypes.byref(wc))
            self.flyout_class_registered = True

        self.flyout_hwnd = user32.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
            FLYOUT_WND_CLASS,
            "Antigravity Tray Menu",
            WS_POPUP | WS_CLIPCHILDREN,
            0, 0, FLYOUT_WIDTH_96DPI, FLYOUT_HEIGHT_96DPI,
            self.msg_hwnd,
            None,
            self.hinstance,
            None,
        )
        if not self.flyout_hwnd:
            return False

        # Apply Windows 11 hardware-antialiased rounded corners + subtle #E5E7EB border
        corner_pref = ctypes.c_int(DWMWCP_ROUND)
        hr_corner = dwmapi.DwmSetWindowAttribute(
            self.flyout_hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(corner_pref),
            ctypes.sizeof(corner_pref),
        )
        self.flyout_dwm_rounded = (hr_corner == 0)

        border_col = ctypes.c_uint32(DWM_BORDER_E5E7EB)
        dwmapi.DwmSetWindowAttribute(
            self.flyout_hwnd,
            DWMWA_BORDER_COLOR,
            ctypes.byref(border_col),
            ctypes.sizeof(border_col),
        )
        return True

    def _get_monitor_metrics(self, pt: wintypes.POINT) -> tuple[int, wintypes.RECT]:
        hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
        dpi = 0
        if hmon and shcore is not None:
            dpi_x = wintypes.UINT(0)
            dpi_y = wintypes.UINT(0)
            if shcore.GetDpiForMonitor(hmon, MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0:
                dpi = int(dpi_x.value)
        if dpi <= 0 and self.flyout_hwnd:
            dpi = int(user32.GetDpiForWindow(self.flyout_hwnd) or 0)
        if dpi <= 0:
            dpi = int(user32.GetDpiForSystem() or 96)

        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if hmon and user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            work = mi.rcWork
        else:
            work = wintypes.RECT(0, 0, 1920, 1040)
        return dpi, work

    def _get_item_rects(self, width: int, dpi: int) -> dict[int, tuple[int, int, int, int]]:
        s = dpi / 96.0
        header_h = round(60 * s)
        div_px = max(1, round(1 * s))
        x0 = round(8 * s)
        x1 = width - round(8 * s)
        item_h = round(44 * s)

        r1_y = header_h + div_px + round(6 * s)
        r2_y = r1_y + item_h + round(2 * s)
        sep_y = r2_y + item_h + round(6 * s)
        r3_y = sep_y + div_px + round(6 * s)

        return {
            IDM_RESTORE_WINDOWS: (x0, r1_y, x1, r1_y + item_h),
            IDM_BRANCH_CONVERSATION: (x0, r2_y, x1, r2_y + item_h),
            IDM_QUIT_ANTIGRAVITY: (x0, r3_y, x1, r3_y + item_h),
        }

    def _hit_test_item(self, x: int, y: int) -> int:
        s = self.flyout_dpi / 96.0
        w = round(FLYOUT_WIDTH_96DPI * s)
        for cmd_id, (x0, y0, x1, y1) in self._get_item_rects(w, self.flyout_dpi).items():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return cmd_id
        return 0

    def _paint_flyout(self, hwnd: int, hdc_dest: wintypes.HDC) -> None:
        rc_client = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rc_client))
        w = max(1, rc_client.right - rc_client.left)
        h = max(1, rc_client.bottom - rc_client.top)
        dpi = self.flyout_dpi
        s = dpi / 96.0

        mem_dc = gdi32.CreateCompatibleDC(hdc_dest)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_dest, w, h)
        old_bmp = gdi32.SelectObject(mem_dc, hbmp)

        try:
            def _fill_gdi(l: int, t: int, r: int, b: int, col_ref: int) -> None:
                rc = wintypes.RECT(l, t, r, b)
                br = gdi32.CreateSolidBrush(col_ref)
                user32.FillRect(mem_dc, ctypes.byref(rc), br)
                gdi32.DeleteObject(br)

            header_h = round(60 * s)
            div_px = max(1, round(1 * s))
            rects = self._get_item_rects(w, dpi)
            item_x0, r1_y, item_x1, _ = rects[IDM_RESTORE_WINDOWS]
            _, r2_y, _, _ = rects[IDM_BRANCH_CONVERSATION]
            _, r3_y, _, _ = rects[IDM_QUIT_ANTIGRAVITY]
            item_h = round(44 * s)
            sep_y = r2_y + item_h + round(6 * s)

            # 1. Crisp card surfaces & 1px dividers (#FFFFFF body, #F8F9FB header, #ECEEF2 dividers)
            _fill_gdi(0, 0, w, h, _rgb(0xFF, 0xFF, 0xFF))
            _fill_gdi(0, 0, w, header_h, _rgb(0xF8, 0xF9, 0xFB))
            _fill_gdi(0, header_h, w, header_h + div_px, _rgb(0xEC, 0xEE, 0xF2))
            _fill_gdi(round(14 * s), sep_y, w - round(14 * s), sep_y + div_px, _rgb(0xEC, 0xEE, 0xF2))

            # 2. Anti-aliased GDI+ shapes (hover pill, header icon container, status dot, vector glyphs)
            hover_id = self.hover_item_id
            g = ctypes.c_void_p()
            if gdip.GdipCreateFromHDC(mem_dc, ctypes.byref(g)) == 0 and g.value:
                try:
                    gdip.GdipSetSmoothingMode(g, SMOOTHING_MODE_ANTIALIAS)
                    gdip.GdipSetPixelOffsetMode(g, PIXEL_OFFSET_MODE_HALF)

                    pill_r = 8.0 * s
                    pill_w = float(item_x1 - item_x0)
                    if hover_id == IDM_RESTORE_WINDOWS:
                        _gdip_fill_round_rect(
                            g, float(item_x0), float(r1_y), pill_w, float(item_h),
                            pill_r, _argb(255, 0xF3, 0xF4, 0xF6),
                        )
                    elif hover_id == IDM_BRANCH_CONVERSATION:
                        _gdip_fill_round_rect(
                            g, float(item_x0), float(r2_y), pill_w, float(item_h),
                            pill_r, _argb(255, 0xEE, 0xF2, 0xFF),
                        )
                    elif hover_id == IDM_QUIT_ANTIGRAVITY:
                        _gdip_fill_round_rect(
                            g, float(item_x0), float(r3_y), pill_w, float(item_h),
                            pill_r, _argb(255, 0xFE, 0xF2, 0xF2),
                        )

                    # Header app icon badge (#FFFFFF rounded tile with #E5E7EB 1px stroke)
                    icon_box_x = 14.0 * s
                    icon_box_y = 13.0 * s
                    icon_box_sz = 34.0 * s
                    _gdip_fill_round_rect(
                        g, icon_box_x, icon_box_y, icon_box_sz, icon_box_sz,
                        8.0 * s, _argb(255, 0xFF, 0xFF, 0xFF),
                    )
                    _gdip_stroke_round_rect(
                        g, icon_box_x, icon_box_y, icon_box_sz, icon_box_sz,
                        8.0 * s, _argb(255, 0xE5, 0xE7, 0xEB), 1.0 * s,
                    )

                    # Green active status dot (#10B981 solid + #D1FAE5 soft halo, flush with title left)
                    halo_r = 4.8 * s
                    dot_r = 3.0 * s
                    dot_cx = 56.0 * s + halo_r
                    dot_cy = 41.5 * s
                    b_halo = ctypes.c_void_p()
                    b_dot = ctypes.c_void_p()
                    gdip.GdipCreateSolidFill(_argb(255, 0xD1, 0xFA, 0xE5), ctypes.byref(b_halo))
                    gdip.GdipCreateSolidFill(_argb(255, 0x10, 0xB9, 0x81), ctypes.byref(b_dot))
                    gdip.GdipFillEllipse(g, b_halo, dot_cx - halo_r, dot_cy - halo_r, halo_r * 2.0, halo_r * 2.0)
                    gdip.GdipFillEllipse(g, b_dot, dot_cx - dot_r, dot_cy - dot_r, dot_r * 2.0, dot_r * 2.0)
                    gdip.GdipDeleteBrush(b_halo)
                    gdip.GdipDeleteBrush(b_dot)

                    # Left vector glyphs for each action item
                    ic_cx = 26.0 * s
                    stroke_w = 1.6 * s

                    # Glyph 1: Restore Window
                    ic1_cy = r1_y + item_h / 2.0
                    col1 = (
                        _argb(255, 0x11, 0x18, 0x27)
                        if hover_id == IDM_RESTORE_WINDOWS
                        else _argb(255, 0x4B, 0x55, 0x63)
                    )
                    _gdip_stroke_round_rect(
                        g, ic_cx - 6.5 * s, ic1_cy - 5.5 * s, 13.0 * s, 11.0 * s, 2.2 * s, col1, stroke_w
                    )
                    p1 = _gdip_make_pen(col1, stroke_w)
                    gdip.GdipDrawLine(g, p1, ic_cx - 6.2 * s, ic1_cy - 2.0 * s, ic_cx + 6.2 * s, ic1_cy - 2.0 * s)
                    gdip.GdipDeletePen(p1)

                    # Glyph 2: Conversation Branch / Fork
                    ic2_cy = r2_y + item_h / 2.0
                    col2 = (
                        _argb(255, 0x43, 0x38, 0xCA)
                        if hover_id == IDM_BRANCH_CONVERSATION
                        else _argb(255, 0x4B, 0x55, 0x63)
                    )
                    p2 = _gdip_make_pen(col2, stroke_w)
                    nr = 2.0 * s
                    lx = ic_cx - 3.6 * s
                    rx = ic_cx + 3.8 * s
                    ty = ic2_cy - 4.8 * s
                    by = ic2_cy + 4.8 * s
                    ry = ic2_cy - 2.4 * s
                    gdip.GdipDrawEllipse(g, p2, lx - nr, ty - nr, nr * 2.0, nr * 2.0)
                    gdip.GdipDrawEllipse(g, p2, lx - nr, by - nr, nr * 2.0, nr * 2.0)
                    gdip.GdipDrawEllipse(g, p2, rx - nr, ry - nr, nr * 2.0, nr * 2.0)
                    gdip.GdipDrawLine(g, p2, lx, ty + nr, lx, by - nr)
                    gdip.GdipDrawBezier(
                        g, p2,
                        lx, ic2_cy + 2.2 * s,
                        lx, ic2_cy - 0.2 * s,
                        rx, ic2_cy + 1.2 * s,
                        rx, ry + nr,
                    )
                    gdip.GdipDeletePen(p2)

                    # Glyph 3: Power / Complete Quit
                    ic3_cy = r3_y + item_h / 2.0
                    col3 = (
                        _argb(255, 0xDC, 0x26, 0x26)
                        if hover_id == IDM_QUIT_ANTIGRAVITY
                        else _argb(255, 0xB9, 0x1C, 0x1C)
                    )
                    p3 = _gdip_make_pen(col3, stroke_w)
                    pr = 5.6 * s
                    gdip.GdipDrawArc(
                        g, p3, ic_cx - pr, ic3_cy - pr + 0.8 * s, pr * 2.0, pr * 2.0, 308.0, 284.0
                    )
                    gdip.GdipDrawLine(g, p3, ic_cx, ic3_cy - 6.2 * s, ic_cx, ic3_cy - 0.4 * s)
                    gdip.GdipDeletePen(p3)

                    # Fallback subtle border on Windows 10 when DWM rounded border is unavailable
                    if not self.flyout_dwm_rounded:
                        _gdip_stroke_round_rect(
                            g, 0.5, 0.5, float(w - 1), float(h - 1),
                            1.0, _argb(255, 0xE5, 0xE7, 0xEB), 1.0,
                        )
                finally:
                    gdip.GdipDeleteGraphics(g)

            # 3. Crisp DPI-matched Antigravity App Icon inside header badge
            ico_sz = round(22 * s)
            hicon_hdr = self._get_header_icon(ico_sz)
            if hicon_hdr:
                ix = round(14.0 * s + (34.0 * s - ico_sz) / 2.0)
                iy = round(13.0 * s + (34.0 * s - ico_sz) / 2.0)
                user32.DrawIconEx(mem_dc, ix, iy, hicon_hdr, ico_sz, ico_sz, 0, None, DI_NORMAL)

            # 4. Razor-sharp ClearType typography
            f_title, f_sub, f_item, f_item_med, f_hint = self._get_fonts_for_dpi(dpi)
            gdi32.SetBkMode(mem_dc, TRANSPARENT)

            def _draw_text(
                font: wintypes.HFONT,
                text: str,
                l: float,
                t: float,
                r: float,
                b: float,
                col_ref: int,
                flags: int = DT_SINGLELINE | DT_VCENTER | DT_NOPREFIX,
            ) -> None:
                old_f = gdi32.SelectObject(mem_dc, font)
                gdi32.SetTextColor(mem_dc, col_ref)
                rc = wintypes.RECT(round(l), round(t), round(r), round(b))
                user32.DrawTextW(mem_dc, text, -1, ctypes.byref(rc), flags)
                gdi32.SelectObject(mem_dc, old_f)

            # Header Title & Status
            _draw_text(f_title, "Antigravity 守护中", 56 * s, 10 * s, w - 14 * s, 33 * s, _rgb(0x11, 0x18, 0x27))
            _draw_text(f_sub, "点关闭自动驻留后台", 69 * s, 31 * s, w - 14 * s, 52 * s, _rgb(0x6B, 0x72, 0x80))

            # Item 1: Restore Windows
            _draw_text(
                f_item_med if hover_id == IDM_RESTORE_WINDOWS else f_item,
                "显示 Antigravity 窗口",
                44 * s, r1_y, w - 76 * s, r1_y + item_h,
                _rgb(0x11, 0x18, 0x27),
            )
            _draw_text(
                f_hint,
                "单击托盘",
                44 * s, r1_y, w - 18 * s, r1_y + item_h,
                _rgb(0x6B, 0x72, 0x80) if hover_id == IDM_RESTORE_WINDOWS else _rgb(0x9C, 0xA3, 0xAF),
                DT_SINGLELINE | DT_VCENTER | DT_RIGHT | DT_NOPREFIX,
            )

            # Item 2: Branch Conversation
            _draw_text(
                f_item_med if hover_id == IDM_BRANCH_CONVERSATION else f_item,
                "对话分支克隆...",
                44 * s, r2_y, w - 76 * s, r2_y + item_h,
                _rgb(0x1E, 0x3A, 0x8A) if hover_id == IDM_BRANCH_CONVERSATION else _rgb(0x11, 0x18, 0x27),
            )
            _draw_text(
                f_hint,
                "任意轮次",
                44 * s, r2_y, w - 18 * s, r2_y + item_h,
                _rgb(0x63, 0x66, 0xF1) if hover_id == IDM_BRANCH_CONVERSATION else _rgb(0x9C, 0xA3, 0xAF),
                DT_SINGLELINE | DT_VCENTER | DT_RIGHT | DT_NOPREFIX,
            )

            # Item 3: Quit Antigravity
            _draw_text(
                f_item_med if hover_id == IDM_QUIT_ANTIGRAVITY else f_item,
                "彻底退出 Antigravity",
                44 * s, r3_y, w - 56 * s, r3_y + item_h,
                _rgb(0xDC, 0x26, 0x26) if hover_id == IDM_QUIT_ANTIGRAVITY else _rgb(0x37, 0x41, 0x51),
            )
            _draw_text(
                f_hint,
                "Quit",
                44 * s, r3_y, w - 18 * s, r3_y + item_h,
                _rgb(0xEF, 0x44, 0x44) if hover_id == IDM_QUIT_ANTIGRAVITY else _rgb(0x9C, 0xA3, 0xAF),
                DT_SINGLELINE | DT_VCENTER | DT_RIGHT | DT_NOPREFIX,
            )

            # 5. Blit offscreen buffer cleanly to window DC
            gdi32.BitBlt(hdc_dest, 0, 0, w, h, mem_dc, 0, 0, SRCCOPY)
        finally:
            gdi32.SelectObject(mem_dc, old_bmp)
            gdi32.DeleteObject(hbmp)
            gdi32.DeleteDC(mem_dc)

    def _hide_flyout(self) -> None:
        if self.flyout_hwnd and user32.IsWindow(self.flyout_hwnd):
            user32.KillTimer(self.flyout_hwnd, TIMER_PREVIEW_AUTOHIDE_ID)
            user32.ShowWindow(self.flyout_hwnd, SW_HIDE)
        self.flyout_visible = False
        self.hover_item_id = 0
        self.pressed_item_id = 0
        self.tracking_mouse_leave = False
        if self.preview_only:
            user32.PostQuitMessage(0)

    def _show_flyout_at(
        self,
        anchor_pt: wintypes.POINT,
        is_preview: bool = False,
        initial_hover: int = 0,
        autohide_ms: int = 0,
    ) -> None:
        if not self._ensure_flyout_window() or not self.flyout_hwnd:
            return

        dpi, work = self._get_monitor_metrics(anchor_pt)
        self.flyout_dpi = dpi
        s = dpi / 96.0
        card_w = round(FLYOUT_WIDTH_96DPI * s)
        card_h = round(FLYOUT_HEIGHT_96DPI * s)
        margin = round(8 * s)

        if is_preview:
            # Position cleanly near bottom-right work area (e.g. work_right - 300*s, work_bottom - 240*s)
            x = work.right - round(300 * s)
            y = work.bottom - round(240 * s)
        else:
            # Center horizontally above cursor; flip below if near top edge
            x = anchor_pt.x - (card_w // 2)
            y = anchor_pt.y - card_h - margin
            if y < work.top + margin:
                y = anchor_pt.y + margin

        # Clamp strictly within monitor work area so taskbar/edges never clip the card
        x = max(work.left + margin, min(x, work.right - card_w - margin))
        y = max(work.top + margin, min(y, work.bottom - card_h - margin))

        self.hover_item_id = initial_hover
        self.pressed_item_id = 0
        self.tracking_mouse_leave = False
        self.flyout_visible = True

        user32.KillTimer(self.flyout_hwnd, TIMER_PREVIEW_AUTOHIDE_ID)
        if autohide_ms > 0:
            user32.SetTimer(self.flyout_hwnd, TIMER_PREVIEW_AUTOHIDE_ID, autohide_ms, None)

        swp_flags = SWP_SHOWWINDOW | (SWP_NOACTIVATE if is_preview else 0)
        user32.SetWindowPos(self.flyout_hwnd, HWND_TOPMOST, x, y, card_w, card_h, swp_flags)
        user32.InvalidateRect(self.flyout_hwnd, None, False)
        user32.UpdateWindow(self.flyout_hwnd)

        if not is_preview:
            user32.SetForegroundWindow(self.flyout_hwnd)
            user32.SetFocus(self.flyout_hwnd)

    def _show_tray_menu(self) -> None:
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        self._show_flyout_at(pt, is_preview=False, initial_hover=0, autohide_ms=0)

    def _show_tray_menu_preview(self, wparam_hint: int = 0) -> None:
        pt = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            pt = wintypes.POINT(1200, 800)
        hover_map = {
            1: IDM_RESTORE_WINDOWS,
            2: IDM_BRANCH_CONVERSATION,
            3: IDM_QUIT_ANTIGRAVITY,
            IDM_RESTORE_WINDOWS: IDM_RESTORE_WINDOWS,
            IDM_BRANCH_CONVERSATION: IDM_BRANCH_CONVERSATION,
            IDM_QUIT_ANTIGRAVITY: IDM_QUIT_ANTIGRAVITY,
        }
        hover_id = hover_map.get(int(wparam_hint), 0)
        timeout = TIMER_PREVIEW_STANDALONE_MS if self.preview_only else TIMER_PREVIEW_LIVE_SAFETY_MS
        self._show_flyout_at(pt, is_preview=True, initial_hover=hover_id, autohide_ms=timeout)

    def _flyout_wnd_proc(self, hwnd: int, msg: int, wParam: int, lParam: int) -> int:
        if msg == WM_ERASEBKGND:
            return 1

        if msg == WM_PAINT:
            ps = PAINTSTRUCT()
            hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
            if hdc:
                try:
                    self._paint_flyout(hwnd, hdc)
                finally:
                    user32.EndPaint(hwnd, ctypes.byref(ps))
            return 0

        if msg == WM_SETCURSOR:
            if (lParam & 0xFFFF) == 1:  # HTCLIENT
                user32.SetCursor(self.cursor_hand if self.hover_item_id else self.cursor_arrow)
                return 1

        if msg == WM_MOUSEMOVE:
            x = ctypes.c_short(lParam & 0xFFFF).value
            y = ctypes.c_short((lParam >> 16) & 0xFFFF).value
            if not self.tracking_mouse_leave:
                tme = TRACKMOUSEEVENT()
                tme.cbSize = ctypes.sizeof(TRACKMOUSEEVENT)
                tme.dwFlags = TME_LEAVE
                tme.hwndTrack = hwnd
                tme.dwHoverTime = 0
                if user32.TrackMouseEvent(ctypes.byref(tme)):
                    self.tracking_mouse_leave = True
            hit = self._hit_test_item(x, y)
            if hit != self.hover_item_id:
                self.hover_item_id = hit
                user32.SetCursor(self.cursor_hand if hit else self.cursor_arrow)
                user32.InvalidateRect(hwnd, None, False)
            return 0

        if msg == WM_MOUSELEAVE:
            self.tracking_mouse_leave = False
            if self.hover_item_id != 0:
                self.hover_item_id = 0
                user32.InvalidateRect(hwnd, None, False)
            return 0

        if msg == WM_LBUTTONDOWN:
            x = ctypes.c_short(lParam & 0xFFFF).value
            y = ctypes.c_short((lParam >> 16) & 0xFFFF).value
            self.pressed_item_id = self._hit_test_item(x, y)
            return 0

        if msg == WM_LBUTTONUP:
            x = ctypes.c_short(lParam & 0xFFFF).value
            y = ctypes.c_short((lParam >> 16) & 0xFFFF).value
            hit = self._hit_test_item(x, y)
            pressed = self.pressed_item_id
            self.pressed_item_id = 0
            if hit and (pressed == 0 or hit == pressed):
                self._hide_flyout()
                if not self.preview_only and self.msg_hwnd:
                    user32.PostMessageW(self.msg_hwnd, WM_APP_EXEC_CMD, hit, 0)
            return 0

        if msg == WM_KEYDOWN:
            vk = int(wParam)
            if vk == VK_ESCAPE:
                self._hide_flyout()
                return 0
            if vk in (VK_DOWN, VK_UP):
                if self.hover_item_id not in ACTION_ORDER:
                    self.hover_item_id = ACTION_ORDER[0 if vk == VK_DOWN else -1]
                else:
                    idx = ACTION_ORDER.index(self.hover_item_id)
                    step = 1 if vk == VK_DOWN else -1
                    self.hover_item_id = ACTION_ORDER[(idx + step) % len(ACTION_ORDER)]
                user32.InvalidateRect(hwnd, None, False)
                return 0
            if vk in (VK_RETURN, VK_SPACE) and self.hover_item_id in ACTION_ORDER:
                cmd = self.hover_item_id
                self._hide_flyout()
                if not self.preview_only and self.msg_hwnd:
                    user32.PostMessageW(self.msg_hwnd, WM_APP_EXEC_CMD, cmd, 0)
                return 0

        if msg == WM_ACTIVATE:
            if (wParam & 0xFFFF) == WA_INACTIVE and self.flyout_visible:
                self._hide_flyout()
            return 0

        if msg == WM_KILLFOCUS:
            if self.flyout_visible:
                self._hide_flyout()
            return 0

        if msg == WM_TIMER and int(wParam) == TIMER_PREVIEW_AUTOHIDE_ID:
            self._hide_flyout()
            return 0

        if msg == WM_DPICHANGED:
            new_dpi = int(wParam & 0xFFFF)
            if new_dpi > 0:
                self.flyout_dpi = new_dpi
            if lParam:
                suggested = ctypes.cast(lParam, ctypes.POINTER(wintypes.RECT)).contents
                user32.SetWindowPos(
                    hwnd,
                    None,
                    suggested.left,
                    suggested.top,
                    suggested.right - suggested.left,
                    suggested.bottom - suggested.top,
                    SWP_NOZORDER | SWP_NOACTIVATE,
                )
            user32.InvalidateRect(hwnd, None, False)
            return 0

        if msg == WM_CLOSE:
            self._hide_flyout()
            return 0

        return user32.DefWindowProcW(hwnd, msg, wParam, lParam)

    # ---- Hidden Message Window & Main Loop --------------------------------
    def _wnd_proc(self, hwnd: int, msg: int, wParam: int, lParam: int) -> int:
        if msg == WM_APP_HIDE_TO_TRAY:
            self._hide_to_tray(int(wParam))
            return 0
        if msg in (WM_TIMER, WM_APP_SYNC_TRAY):
            self._sync_tray_visibility()
            return 0
        if msg == WM_APP_EXEC_CMD:
            self._execute_menu_command(int(wParam))
            return 0
        if msg == WM_APP_SHOW_MENU_PREVIEW:
            self._show_tray_menu_preview(int(wParam))
            return 0
        if msg == WM_APP_HIDE_MENU_PREVIEW:
            self._hide_flyout()
            return 0
        if msg == WM_TRAYICON:
            ev = int(lParam) & 0xFFFF
            if ev in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self._hide_flyout()
                self._restore_all_windows()
                return 0
            if ev in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_tray_menu()
                return 0
        if msg == WM_CLOSE:
            self._hide_flyout()
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            self._hide_flyout()
            if not self.preview_only:
                self._restore_all_windows()
                self._remove_tray_icon()
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wParam, lParam)

    def run(self) -> None:
        mutex = None
        if not self.preview_only:
            mutex = kernel32.CreateMutexW(None, False, "Local\\AntigravityCloseGuard_v1")
            if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
                if mutex:
                    kernel32.CloseHandle(mutex)
                return

            # Always enforce logon auto-start by default
            self._ensure_autostart()

        msg_cls_name = HIDDEN_WND_CLASS if not self.preview_only else f"{HIDDEN_WND_CLASS}Preview"
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = self.hinstance
        wc.lpszClassName = msg_cls_name
        user32.RegisterClassExW(ctypes.byref(wc))

        self.msg_hwnd = user32.CreateWindowExW(
            0, msg_cls_name, "Antigravity Close Guard", 0, 0, 0, 0, 0, None, None, self.hinstance, None
        )
        if not self.msg_hwnd:
            if mutex:
                kernel32.CloseHandle(mutex)
            return

        if self.preview_only:
            self._show_tray_menu_preview(0)
        else:
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
            if self.msg_hwnd and not self.preview_only:
                user32.KillTimer(self.msg_hwnd, TIMER_SYNC_ID)
            if self.mouse_hook:
                user32.UnhookWindowsHookEx(self.mouse_hook)
            if self.kbd_hook:
                user32.UnhookWindowsHookEx(self.kbd_hook)
            if not self.preview_only:
                self._restore_all_windows()
                self._remove_tray_icon()
            self._cleanup_flyout_resources()
            if self.hicon_small:
                user32.DestroyIcon(self.hicon_small)
                self.hicon_small = None
            if mutex:
                kernel32.CloseHandle(mutex)


def _handle_cli_flags(argv: list[str]) -> bool:
    if "--hide-menu-preview" in argv:
        existing = user32.FindWindowW(HIDDEN_WND_CLASS, None)
        if existing:
            user32.PostMessageW(existing, WM_APP_HIDE_MENU_PREVIEW, 0, 0)
            time.sleep(0.1)
        return True

    if "--show-menu-preview" in argv:
        hover_hint = 0
        for arg in argv:
            if arg.startswith("--hover="):
                try:
                    hover_hint = int(arg.split("=", 1)[1])
                except ValueError:
                    hover_hint = 0
        existing = user32.FindWindowW(HIDDEN_WND_CLASS, None)
        if existing:
            user32.PostMessageW(existing, WM_APP_SHOW_MENU_PREVIEW, hover_hint, 0)
            time.sleep(0.15)
            return True
        guard = AntigravityCloseGuard(preview_only=True)
        guard.run()
        return True

    return False


if __name__ == "__main__":
    if not _handle_cli_flags(sys.argv[1:]):
        guard = AntigravityCloseGuard(preview_only=False)
        guard.run()
