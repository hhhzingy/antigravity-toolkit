#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity Close Guard for Linux (Ubuntu / GNOME / X11)
--------------------------------------------------------
Zero-intrusion close-button ('X'), Alt+F4, and Ctrl+Q interceptor for Google Antigravity.
- Clicking top-right 'X' (or pressing Alt+F4 / Ctrl+Q) on any Antigravity main window
  immediately hides (withdraws) the window to the System Tray (Ubuntu AppIndicators)
  without destroying the Electron window or interrupting active AI conversations,
  subagents, or background terminal tasks.
- Clicking '显示 Antigravity 窗口' (or middle-clicking the tray icon) restores & focuses
  the Antigravity window immediately.
- Clicking '分支克隆对话 (Branch)...' opens the visual conversation branching tool.
- Antigravity can ONLY be completely exited via the System Tray menu -> 'Quit'.

Zero modification to /opt/Antigravity/resources/app.asar (survives auto-updates).
Idle CPU usage: 0.0% (event-driven GLib + X11 fd watch).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gtk

try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator3
except (ValueError, ImportError):
    try:
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3  # type: ignore
    except (ValueError, ImportError):
        AppIndicator3 = None  # type: ignore

try:
    gi.require_version("Notify", "0.7")
    from gi.repository import Notify
except (ValueError, ImportError):
    Notify = None  # type: ignore

from Xlib import X, XK, display, error as xerror
from Xlib.protocol import event as xevent

# Ubuntu Electron titleBarOverlay close button geometry at 96 DPI:
# Measured on Ubuntu 22.04 Yaru: Minimize=[84..107], Maximize=[47..70], Close=[10..33] from right, y=[3..26].
# Using width=41px from right edge catches the entire Close circle + top-right corner (Fitts's law)
# while staying clear of Maximize (starts at 47px from right).
CLOSE_BTN_WIDTH_96DPI = 41
CLOSE_BTN_HEIGHT_96DPI = 32

SYSTEMD_UNIT_NAME = "antigravity-close-guard.service"
AGY_DEFAULT_BIN = "/opt/Antigravity/antigravity"
AGY_ASAR_PATH = "/opt/Antigravity/resources/app.asar"
AGY_STORAGE_PATH = Path.home() / ".config" / "Antigravity" / "app_storage.json"
CACHE_DIR = Path.home() / ".cache" / "antigravity-close-guard"


def extract_antigravity_icon() -> tuple[str, str]:
    """Extracts icon.png from app.asar (read-only) into ~/.cache for crisp tray rendering."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    icon_out = CACHE_DIR / "antigravity-tray.png"
    if icon_out.exists() and icon_out.stat().st_size > 1024:
        return str(CACHE_DIR), "antigravity-tray"

    asar = Path(AGY_ASAR_PATH)
    if asar.exists():
        try:
            with asar.open("rb") as f:
                pre = f.read(16)
                hdr_pickle_size = struct.unpack("<I", pre[4:8])[0]
                hdr_json_size = struct.unpack("<I", pre[12:16])[0]
                hdr_total = 8 + hdr_pickle_size
                header = json.loads(f.read(hdr_json_size).decode("utf-8"))
                node = header.get("files", {}).get("icon.png")
                if node and "offset" in node and "size" in node:
                    f.seek(hdr_total + int(node["offset"]))
                    icon_out.write_bytes(f.read(int(node["size"])))
                    return str(CACHE_DIR), "antigravity-tray"
        except Exception:
            pass

    return "", "applications-development"


def ensure_run_in_background_setting() -> None:
    """Belt-and-suspenders: ensures runInBackground='true' in Antigravity's app_storage.json."""
    try:
        if not AGY_STORAGE_PATH.exists():
            return
        data = json.loads(AGY_STORAGE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("runInBackground") != "true":
            data["runInBackground"] = "true"
            tmp = AGY_STORAGE_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(AGY_STORAGE_PATH)
    except Exception:
        pass


class LinuxAntigravityCloseGuard:
    def __init__(self, target_wm_class: str = "antigravity") -> None:
        self.target_wm_class = target_wm_class.lower()
        self.dpy = display.Display()
        self.root = self.dpy.screen().root

        # Intern X11 atoms
        self.atom_wm_protocols = self.dpy.intern_atom("WM_PROTOCOLS")
        self.atom_wm_delete = self.dpy.intern_atom("WM_DELETE_WINDOW")
        self.atom_wm_role = self.dpy.intern_atom("WM_WINDOW_ROLE")
        self.atom_net_wm_pid = self.dpy.intern_atom("_NET_WM_PID")
        self.atom_net_wm_window_type = self.dpy.intern_atom("_NET_WM_WINDOW_TYPE")
        self.atom_net_wm_type_normal = self.dpy.intern_atom("_NET_WM_WINDOW_TYPE_NORMAL")
        self.atom_net_wm_state = self.dpy.intern_atom("_NET_WM_STATE")
        self.atom_max_horz = self.dpy.intern_atom("_NET_WM_STATE_MAXIMIZED_HORZ")
        self.atom_max_vert = self.dpy.intern_atom("_NET_WM_STATE_MAXIMIZED_VERT")
        self.atom_gtk_frame_extents = self.dpy.intern_atom("_GTK_FRAME_EXTENTS")
        self.atom_net_active_window = self.dpy.intern_atom("_NET_ACTIVE_WINDOW")
        self.atom_net_close_window = self.dpy.intern_atom("_NET_CLOSE_WINDOW")

        self.keycode_f4 = self.dpy.keysym_to_keycode(XK.XK_F4)
        self.keycode_q = self.dpy.keysym_to_keycode(XK.XK_q)

        self.dpi_scale = self._detect_dpi_scale()
        self.grabbed_xids: set[int] = set()
        self.hidden_windows: dict[int, dict] = {}
        self.known_pids: set[int] = set()
        self.quitting_agy = False
        self.notified_once = False

        self.indicator = None
        self.menu_autostart_item: Gtk.CheckMenuItem | None = None
        self._updating_check = False

        if Notify is not None:
            try:
                Notify.init("Antigravity Close Guard")
            except Exception:
                pass

    def _detect_dpi_scale(self) -> float:
        try:
            out = subprocess.check_output(["xrdb", "-query"], text=True, timeout=2)
            m = re.search(r"Xft\.dpi:\s*([0-9.]+)", out)
            if m:
                dpi = float(m.group(1))
                if dpi > 48:
                    return dpi / 96.0
        except Exception:
            pass
        return 1.0

    # ---- Window Inspection & Matching -------------------------------------
    def _get_atom_prop(self, win, atom) -> list[int]:
        try:
            prop = win.get_full_property(atom, X.AnyPropertyType)
            if prop and prop.value:
                return list(prop.value)
        except Exception:
            pass
        return []

    def _get_str_prop(self, win, atom) -> str:
        try:
            prop = win.get_full_property(atom, X.AnyPropertyType)
            if prop and prop.value:
                if isinstance(prop.value, bytes):
                    return prop.value.decode("utf-8", errors="ignore").strip("\x00")
                return str(prop.value)
        except Exception:
            pass
        return ""

    def _is_target_main_window(self, xid: int, require_min_size: bool = True) -> bool:
        try:
            win = self.dpy.create_resource_object("window", xid)
            wm_class = win.get_wm_class()
            if not wm_class:
                return False
            if not any(self.target_wm_class == c.lower() for c in wm_class):
                return False

            # Exclude transient / dialog child windows (e.g., Open/Save File dialogs)
            if win.get_wm_transient_for():
                return False

            role = self._get_str_prop(win, self.atom_wm_role)
            wtypes = self._get_atom_prop(win, self.atom_net_wm_window_type)
            if role and role != "browser-window" and self.target_wm_class == "antigravity":
                return False
            if wtypes and (self.atom_net_wm_type_normal not in wtypes):
                return False

            if require_min_size:
                geom = win.get_geometry()
                if geom.width < 320 or geom.height < 200:
                    return False

            pids = self._get_atom_prop(win, self.atom_net_wm_pid)
            if pids:
                self.known_pids.add(int(pids[0]))
            return True
        except xerror.XError:
            return False
        except Exception:
            return False

    def _enumerate_visible_target_windows(self) -> list[int]:
        found: list[int] = []
        try:
            children = self.root.query_tree().children
            for w in children:
                xid = w.id
                try:
                    attrs = w.get_attributes()
                    if attrs.map_state == X.IsViewable and self._is_target_main_window(xid, require_min_size=True):
                        found.append(xid)
                except xerror.XError:
                    continue
        except Exception:
            pass
        return found

    # ---- X11 Passive Grabs (0.0% idle CPU, zero impact on other apps) -----
    def _attach_grabs(self, xid: int) -> None:
        if xid in self.grabbed_xids:
            return
        try:
            win = self.dpy.create_resource_object("window", xid)
            win.change_attributes(event_mask=X.StructureNotifyMask)

            # 1. Synchronous passive Button1 grab on Antigravity window ONLY:
            #    Clicks outside the top-right 'X' are replayed natively via ReplayPointer (<0.05ms).
            win.grab_button(
                1,
                X.AnyModifier,
                False,
                X.ButtonPressMask | X.ButtonReleaseMask,
                X.GrabModeSync,
                X.GrabModeAsync,
                X.NONE,
                X.NONE,
            )

            # 2. Passive Key grabs for Alt+F4 and Ctrl+Q across CapsLock / NumLock states
            lock_variants = (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask)
            if self.keycode_f4:
                for extra in lock_variants:
                    win.grab_key(self.keycode_f4, X.Mod1Mask | extra, False, X.GrabModeAsync, X.GrabModeAsync)
            if self.keycode_q:
                for extra in lock_variants:
                    win.grab_key(self.keycode_q, X.ControlMask | extra, False, X.GrabModeAsync, X.GrabModeAsync)

            self.dpy.flush()
            self.grabbed_xids.add(xid)
        except xerror.XError:
            pass

    def _detach_grabs(self, xid: int) -> None:
        self.grabbed_xids.discard(xid)
        try:
            win = self.dpy.create_resource_object("window", xid)
            win.ungrab_button(1, X.AnyModifier)
            if self.keycode_f4:
                win.ungrab_key(self.keycode_f4, X.AnyModifier)
            if self.keycode_q:
                win.ungrab_key(self.keycode_q, X.AnyModifier)
            self.dpy.flush()
        except Exception:
            pass

    def _scan_and_attach_all(self) -> None:
        if self.quitting_agy:
            return
        for xid in self._enumerate_visible_target_windows():
            self._attach_grabs(xid)
        self._sync_tray_visibility()

    def _is_point_on_close_button(self, xid: int, event_x: int, event_y: int) -> bool:
        try:
            win = self.dpy.create_resource_object("window", xid)
            geom = win.get_geometry()
            extents = self._get_atom_prop(win, self.atom_gtk_frame_extents)
            inset_right = int(extents[1]) if len(extents) >= 4 else 0
            inset_top = int(extents[2]) if len(extents) >= 4 else 0
            states = set(self._get_atom_prop(win, self.atom_net_wm_state))
            if (self.atom_max_horz in states) or (self.atom_max_vert in states):
                inset_right = 0
                inset_top = 0

            visible_right = geom.width - inset_right
            visible_top = inset_top
            btn_w = round(CLOSE_BTN_WIDTH_96DPI * self.dpi_scale)
            btn_h = round(CLOSE_BTN_HEIGHT_96DPI * self.dpi_scale)
            return (visible_right - btn_w <= event_x <= visible_right + 2) and (
                visible_top - 2 <= event_y <= visible_top + btn_h
            )
        except Exception:
            return False

    # ---- Hide / Restore / Branch / Quit Logic -----------------------------
    def _withdraw_x11_window(self, xid: int) -> None:
        """ICCCM-compliant XWithdrawWindow so GNOME/Mutter hides window cleanly without closing."""
        win = self.dpy.create_resource_object("window", xid)
        states = set(self._get_atom_prop(win, self.atom_net_wm_state))
        was_max = (self.atom_max_horz in states) or (self.atom_max_vert in states)
        geom = win.get_geometry()
        # Translate top-left to root coordinates
        coords = self.root.translate_coords(win, 0, 0)
        self.hidden_windows[xid] = {
            "was_maximized": was_max,
            "x": coords.x,
            "y": coords.y,
            "width": geom.width,
            "height": geom.height,
        }

        win.unmap()
        ev = xevent.UnmapNotify(
            event=self.root,
            window=win,
            from_configure=False,
        )
        self.root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        self.dpy.flush()

    def _hide_to_tray(self, xid: int) -> None:
        try:
            self._withdraw_x11_window(xid)
            self._sync_tray_visibility()
            if not self.notified_once and Notify is not None:
                self.notified_once = True
                try:
                    n = Notify.Notification.new(
                        "Antigravity 已隐藏到系统托盘",
                        "后台 AI 对话与终端任务继续运行；点击顶部托盘图标恢复窗口，选择 Quit 彻底退出。",
                        "applications-development",
                    )
                    n.show()
                except Exception:
                    pass
        except Exception:
            pass

    def _send_ewmh_state(self, win, action: int, atom1: int, atom2: int = 0) -> None:
        ev = xevent.ClientMessage(
            window=win,
            client_type=self.atom_net_wm_state,
            data=(32, [action, atom1, atom2, 1, 0]),
        )
        self.root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)

    def _activate_window(self, win) -> None:
        ev = xevent.ClientMessage(
            window=win,
            client_type=self.atom_net_active_window,
            data=(32, [2, X.CurrentTime, 0, 0, 0]),
        )
        self.root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)

    def restore_all_windows(self, *_args) -> None:
        restored_any = False
        for xid, meta in list(self.hidden_windows.items()):
            try:
                win = self.dpy.create_resource_object("window", xid)
                win.map()
                if meta.get("was_maximized"):
                    self._send_ewmh_state(win, 1, self.atom_max_horz, self.atom_max_vert)
                self._activate_window(win)
                self.dpy.flush()
                self._attach_grabs(xid)
                restored_any = True
            except xerror.XError:
                pass
            finally:
                self.hidden_windows.pop(xid, None)

        if not restored_any:
            visible = self._enumerate_visible_target_windows()
            if visible:
                for xid in visible:
                    try:
                        win = self.dpy.create_resource_object("window", xid)
                        win.map()
                        self._activate_window(win)
                        self.dpy.flush()
                    except Exception:
                        pass
            elif self.target_wm_class == "antigravity" and Path(AGY_DEFAULT_BIN).exists():
                subprocess.Popen([AGY_DEFAULT_BIN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        self._sync_tray_visibility()

    def open_branch_gui(self, *_args) -> None:
        branch_script = Path.home() / "mcp-gui-workspace" / "antigravity-branch" / "branch_conversation.py"
        if not branch_script.exists():
            if Notify is not None:
                try:
                    n = Notify.Notification.new(
                        "未检测到对话分支工具",
                        "请先安装 branch_conversation 模块后再使用此功能。",
                        "dialog-information",
                    )
                    n.show()
                except Exception:
                    pass
            return
        py_bin = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else sys.executable
        subprocess.Popen([py_bin, str(branch_script), "--gui"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def quit_antigravity_completely(self, *_args) -> None:
        if self.quitting_agy:
            return
        self.quitting_agy = True

        all_xids = set(self.hidden_windows.keys()) | set(self._enumerate_visible_target_windows())
        self.hidden_windows.clear()
        for xid in list(self.grabbed_xids):
            self._detach_grabs(xid)

        pids = set(self.known_pids)
        for xid in all_xids:
            try:
                win = self.dpy.create_resource_object("window", xid)
                p = self._get_atom_prop(win, self.atom_net_wm_pid)
                if p:
                    pids.add(int(p[0]))
            except Exception:
                pass

        def _quit_worker() -> None:
            try:
                # Graceful SIGTERM triggers Electron before-quit -> flushes window_state & stops LS cleanly
                for pid in pids:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass

                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline:
                    alive = []
                    for pid in pids:
                        try:
                            os.kill(pid, 0)
                            alive.append(pid)
                        except ProcessLookupError:
                            pass
                    if not alive:
                        break
                    time.sleep(0.15)

                for pid in pids:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            finally:
                self.known_pids.clear()
                self.quitting_agy = False
                GLib.idle_add(self._sync_tray_visibility)

        threading.Thread(target=_quit_worker, daemon=True).start()

    # ---- Autostart Helper (systemd --user) --------------------------------
    def _is_autostart_enabled(self) -> bool:
        try:
            res = subprocess.run(
                ["systemctl", "--user", "is-enabled", SYSTEMD_UNIT_NAME],
                capture_output=True,
                text=True,
                timeout=3,
            )
            return res.returncode == 0 and "enabled" in res.stdout
        except Exception:
            return False

    def _on_toggle_autostart(self, item: Gtk.CheckMenuItem) -> None:
        if self._updating_check:
            return
        desired = item.get_active()
        action = "enable" if desired else "disable"
        try:
            subprocess.run(["systemctl", "--user", action, SYSTEMD_UNIT_NAME], check=False, timeout=5)
        except Exception:
            pass

    # ---- System Tray Indicator (AyatanaAppIndicator3) ---------------------
    def _init_tray_indicator(self) -> None:
        if AppIndicator3 is None:
            return
        icon_dir, icon_name = extract_antigravity_icon()
        if icon_dir:
            self.indicator = AppIndicator3.Indicator.new_with_path(
                "antigravity-close-guard",
                icon_name,
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
                icon_dir,
            )
        else:
            self.indicator = AppIndicator3.Indicator.new(
                "antigravity-close-guard",
                icon_name,
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
            )
        self.indicator.set_title("Antigravity Guard")

        menu = Gtk.Menu()

        item_restore = Gtk.MenuItem(label="显示 Antigravity 窗口")
        item_restore.connect("activate", self.restore_all_windows)
        menu.append(item_restore)

        item_branch = Gtk.MenuItem(label="分支克隆对话 (Branch)...")
        item_branch.connect("activate", self.open_branch_gui)
        menu.append(item_branch)

        menu.append(Gtk.SeparatorMenuItem())

        self.menu_autostart_item = Gtk.CheckMenuItem(label="开机自动启动托盘守护")
        self._updating_check = True
        self.menu_autostart_item.set_active(self._is_autostart_enabled())
        self._updating_check = False
        self.menu_autostart_item.connect("toggled", self._on_toggle_autostart)
        menu.append(self.menu_autostart_item)

        menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", self.quit_antigravity_completely)
        menu.append(item_quit)

        menu.show_all()
        self.indicator.set_menu(menu)
        # Middle-click on Ubuntu top-bar indicator triggers restore in one click
        self.indicator.set_secondary_activate_target(item_restore)
        self._sync_tray_visibility()

    def _sync_tray_visibility(self) -> bool:
        if self.indicator is None:
            return False
        # Clean up any hidden windows that no longer exist or became visible externally (e.g. via Dock)
        for xid in list(self.hidden_windows.keys()):
            try:
                win = self.dpy.create_resource_object("window", xid)
                attrs = win.get_attributes()
                if attrs.map_state == X.IsViewable:
                    self.hidden_windows.pop(xid, None)
                    self._attach_grabs(xid)
            except xerror.XError:
                self.hidden_windows.pop(xid, None)

        has_agy = bool(self.hidden_windows) or bool(self._enumerate_visible_target_windows())
        if has_agy:
            self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        else:
            self.indicator.set_status(AppIndicator3.IndicatorStatus.PASSIVE)
            self.notified_once = False
        return False

    # ---- Event-Driven X11 Processing inside GLib MainLoop -----------------
    def _process_x11_events(self, _fd: int, _condition: GLib.IOCondition) -> bool:
        while self.dpy.pending_events():
            ev = self.dpy.next_event()
            etype = ev.type

            if etype == X.ButtonPress and ev.detail == 1:
                win_xid = ev.window.id
                if not self.quitting_agy and self._is_point_on_close_button(win_xid, ev.event_x, ev.event_y):
                    # Swallow both ButtonPress and ButtonRelease so Electron never receives the close click
                    self.dpy.allow_events(X.AsyncPointer, ev.time)
                    self.dpy.flush()
                    self._hide_to_tray(win_xid)
                else:
                    # Replay click immediately to Antigravity window natively
                    self.dpy.allow_events(X.ReplayPointer, ev.time)
                    self.dpy.flush()

            elif etype == X.KeyPress:
                win_xid = ev.window.id
                if not self.quitting_agy and ev.keycode in (self.keycode_f4, self.keycode_q):
                    self._hide_to_tray(win_xid)

            elif etype == X.MapNotify:
                xid = ev.window.id
                if xid in self.hidden_windows:
                    self.hidden_windows.pop(xid, None)
                if not self.quitting_agy and self._is_target_main_window(xid, require_min_size=True):
                    self._attach_grabs(xid)
                    self._sync_tray_visibility()

            elif etype == X.DestroyNotify:
                xid = ev.window.id
                was_tracked = (xid in self.grabbed_xids) or (xid in self.hidden_windows)
                self.grabbed_xids.discard(xid)
                self.hidden_windows.pop(xid, None)
                if was_tracked:
                    self._sync_tray_visibility()

        return True

    def _periodic_reconcile(self) -> bool:
        """Lightweight safety check every 5s in case WM_CLASS is set slightly after MapNotify."""
        self._scan_and_attach_all()
        return True

    def run(self) -> None:
        ensure_run_in_background_setting()
        self.root.change_attributes(event_mask=X.SubstructureNotifyMask)
        self.dpy.flush()

        self._init_tray_indicator()
        self._scan_and_attach_all()

        GLib.io_add_watch(self.dpy.fileno(), GLib.IO_IN, self._process_x11_events)
        GLib.timeout_add_seconds(5, self._periodic_reconcile)

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._graceful_daemon_stop)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._graceful_daemon_stop)

        Gtk.main()

    def _graceful_daemon_stop(self) -> bool:
        # Stopping the guard daemon itself restores any hidden windows rather than losing them
        self.restore_all_windows()
        for xid in list(self.grabbed_xids):
            self._detach_grabs(xid)
        Gtk.main_quit()
        return False


def run_self_test() -> int:
    """Automated X11 self-test using a temporary GTK window + XTest clicks (never touches live Antigravity)."""
    import warnings
    from Xlib.ext import xtest

    warnings.filterwarnings("ignore", category=DeprecationWarning)
    test_class = f"agy_guard_selftest_{os.getpid()}"
    guard = LinuxAntigravityCloseGuard(target_wm_class=test_class)

    clicks_received: list[tuple[int, int]] = []
    win = Gtk.Window(title="CloseGuard SelfTest")
    win.set_wmclass(test_class, test_class)
    win.set_role("browser-window")
    win.set_decorated(False)
    win.set_default_size(500, 300)
    win.move(200, 200)
    win.add_events(1 << 8)  # GDK_BUTTON_PRESS_MASK

    def _on_btn(_w, event):
        clicks_received.append((int(event.x), int(event.y)))
        return False

    win.connect("button-press-event", _on_btn)
    win.show_all()

    GLib.io_add_watch(guard.dpy.fileno(), GLib.IO_IN, guard._process_x11_events)

    results: dict[str, bool] = {}
    state = {"interior_count": 0}
    test_dpy = display.Display()

    def _step1_attach():
        guard._scan_and_attach_all()
        results["grab_attached"] = len(guard.grabbed_xids) == 1
        if not results["grab_attached"]:
            Gtk.main_quit()
            return False

        # Simulate interior click at (120, 120) -> should pass through via ReplayPointer
        xid = next(iter(guard.grabbed_xids))
        xwin = test_dpy.create_resource_object("window", xid)
        coords = test_dpy.screen().root.translate_coords(xwin, 0, 0)
        test_dpy.screen().root.warp_pointer(coords.x + 120, coords.y + 120)
        test_dpy.sync()
        xtest.fake_input(test_dpy, X.ButtonPress, 1)
        test_dpy.sync()
        xtest.fake_input(test_dpy, X.ButtonRelease, 1)
        test_dpy.sync()
        GLib.timeout_add(150, _step2_check_passthrough)
        return False

    def _step2_check_passthrough():
        state["interior_count"] = len(clicks_received)
        results["interior_click_passed_through"] = state["interior_count"] >= 1
        # Simulate click on top-right 'X' at (width - 18, 14) -> should be swallowed & hide window!
        xid = next(iter(guard.grabbed_xids))
        xwin = test_dpy.create_resource_object("window", xid)
        geom = xwin.get_geometry()
        coords = test_dpy.screen().root.translate_coords(xwin, 0, 0)
        test_dpy.screen().root.warp_pointer(coords.x + geom.width - 18, coords.y + 14)
        test_dpy.sync()
        xtest.fake_input(test_dpy, X.ButtonPress, 1)
        test_dpy.sync()
        xtest.fake_input(test_dpy, X.ButtonRelease, 1)
        test_dpy.sync()
        GLib.timeout_add(200, _step3_check_hidden)
        return False

    def _step3_check_hidden():
        results["close_click_swallowed"] = len(clicks_received) == state["interior_count"]
        results["window_hidden_to_tray"] = len(guard.hidden_windows) == 1
        guard.restore_all_windows()
        GLib.timeout_add(200, _step4_check_restored)
        return False

    def _step4_check_restored():
        results["window_restored"] = (len(guard.hidden_windows) == 0) and (
            len(guard._enumerate_visible_target_windows()) == 1
        )
        win.destroy()
        Gtk.main_quit()
        return False

    GLib.timeout_add(250, _step1_attach)
    Gtk.main()

    print("Self-test results:", json.dumps(results, indent=2))
    return 0 if all(results.values()) and len(results) == 5 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Antigravity Close Guard for Linux (X11/GNOME)")
    parser.add_argument("--self-test", action="store_true", help="Run automated X11 interception self-test and exit")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    uid = os.getuid()
    lock_dir = Path(f"/run/user/{uid}") if Path(f"/run/user/{uid}").is_dir() else Path("/tmp")
    lock_file = lock_dir / f"antigravity_close_guard_{uid}.lock"
    fp = lock_file.open("w")
    try:
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0

    guard = LinuxAntigravityCloseGuard()
    guard.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
