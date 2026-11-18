# -*- coding: utf-8 -*-
"""
linux-gui-mcp: Ultra-fast Linux X11 + AT-SPI2 Computer Use MCP Server
---------------------------------------------------------------------
Mirrors the speed & safety optimizations of patched Windows-MCP:
1. Default multimodal vision (`use_vision=True, use_ui_tree=False`) -> <0.08s pure-vision Snapshot
   (skips AT-SPI2 traversal, background window enumeration, and full-image deep copies; uses PNG compress_level=1).
2. Active-Window-Only AT-SPI2 UI Tree (`use_ui_tree=True`) -> <0.15s
   (filters out gnome-shell/dock/panels/background windows; caps traversal budget & depth).
3. Human mouse-shake takeover guard (`~/.linux-mcp/config.toml`: 0s consent countdown, 2s cooldown).
4. Reliable UTF-8 / CJK text input via X11 clipboard (`xclip`) with terminal shortcut auto-detection.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import io
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent
import mss
from PIL import Image, ImageDraw

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore

try:
    from Xlib import X, display as xdisplay
except ImportError:
    xdisplay = None  # type: ignore

try:
    import gi

    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
except Exception:
    Atspi = None  # type: ignore


DEFAULT_MAX_TREE_ELEMENTS = int(os.environ.get("LINUX_MCP_MAX_TREE_ELEMENTS", "500"))
DEFAULT_MAX_DEPTH = int(os.environ.get("LINUX_MCP_MAX_DEPTH", "20"))
MAX_IMAGE_WIDTH = int(os.environ.get("LINUX_MCP_MAX_IMAGE_WIDTH", "1920"))
MAX_IMAGE_HEIGHT = int(os.environ.get("LINUX_MCP_MAX_IMAGE_HEIGHT", "1080"))

IGNORED_SHELL_NAMES = {
    "gnome-shell",
    "mutter",
    "ubuntu-dock",
    "plank",
    "polybar",
    "waybar",
    "xfce4-panel",
    "plasmashell",
    "desktop",
    "ding",
}

TERMINAL_WM_CLASSES = {
    "gnome-terminal",
    "gnome-terminal-server",
    "kitty",
    "alacritty",
    "wezterm",
    "konsole",
    "xfce4-terminal",
    "terminator",
    "tilix",
    "xterm",
    "urxvt",
}

INTERACTIVE_ATSPI_ROLES = {
    "push button",
    "toggle button",
    "check box",
    "radio button",
    "menu item",
    "check menu item",
    "radio menu item",
    "combo box",
    "text",
    "password text",
    "entry",
    "spin button",
    "slider",
    "page tab",
    "link",
    "list item",
    "tree item",
    "table cell",
    "icon",
    "tool bar",
}


@dataclass
class ControlConfig:
    enabled: bool = True
    consent_countdown_seconds: float = 0.0
    idle_timeout_seconds: float = 2.0
    mouse_takeover_units: float = 500.0


def load_control_config() -> ControlConfig:
    cfg_path = Path.home() / ".linux-mcp" / "config.toml"
    if not cfg_path.exists():
        return ControlConfig()
    try:
        raw = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
        sec = raw.get("control") or raw.get("desktop_control") or {}
        return ControlConfig(
            enabled=bool(sec.get("enabled", True)),
            consent_countdown_seconds=float(sec.get("consent_countdown_seconds", 0.0)),
            idle_timeout_seconds=float(sec.get("idle_timeout_seconds", 2.0)),
            mouse_takeover_units=float(sec.get("mouse_takeover_units", 500.0)),
        )
    except Exception:
        return ControlConfig()


class MouseTakeoverGuard:
    """Monitors physical cursor movement so shaking the mouse immediately pauses AI clicks for 2s."""

    def __init__(self, cfg: ControlConfig) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._ai_busy = 0
        self._accum_dist = 0.0
        self._last_takeover_ts = 0.0
        self._started = False

    def start(self) -> None:
        if self._started or not self.cfg.enabled or xdisplay is None:
            return
        self._started = True
        t = threading.Thread(target=self._monitor_loop, daemon=True)
        t.start()

    def _monitor_loop(self) -> None:
        try:
            dpy = xdisplay.Display()
            root = dpy.screen().root
            qp = root.query_pointer()
            last_x, last_y = qp.root_x, qp.root_y
        except Exception:
            return

        while True:
            time.sleep(0.12)
            try:
                qp = root.query_pointer()
                cx, cy = qp.root_x, qp.root_y
                dx, dy = cx - last_x, cy - last_y
                last_x, last_y = cx, cy
                step = math.hypot(dx, dy)
                with self._lock:
                    if self._ai_busy > 0:
                        self._accum_dist = 0.0
                        continue
                    if step > 2.0:
                        self._accum_dist += step
                        if self._accum_dist >= self.cfg.mouse_takeover_units:
                            self._last_takeover_ts = time.monotonic()
                            self._accum_dist = 0.0
                    else:
                        self._accum_dist = max(0.0, self._accum_dist * 0.6)
            except Exception:
                time.sleep(0.5)

    def check_allowed(self) -> None:
        if not self.cfg.enabled:
            return
        with self._lock:
            elapsed = time.monotonic() - self._last_takeover_ts
            if self._last_takeover_ts > 0 and elapsed < self.cfg.idle_timeout_seconds:
                rem = round(self.cfg.idle_timeout_seconds - elapsed, 2)
                raise RuntimeError(
                    f"USER_CONTROL: Physical mouse movement detected; cooling down for {rem}s before resuming."
                )

    def begin_ai_action(self) -> None:
        self.check_allowed()
        if self.cfg.consent_countdown_seconds > 0:
            time.sleep(self.cfg.consent_countdown_seconds)
        with self._lock:
            self._ai_busy += 1

    def end_ai_action(self) -> None:
        with self._lock:
            self._ai_busy = max(0, self._ai_busy - 1)
            self._accum_dist = 0.0


CONTROL_CFG = load_control_config()
GUARD = MouseTakeoverGuard(CONTROL_CFG)


def get_active_window_info() -> dict[str, Any]:
    """Fast (<1ms) X11 query of the active focused window."""
    info: dict[str, Any] = {
        "xid": 0,
        "pid": 0,
        "title": "",
        "wm_class": "",
        "bounds": None,
    }
    if xdisplay is None:
        return info
    try:
        dpy = xdisplay.Display()
        root = dpy.screen().root
        prop = root.get_full_property(dpy.intern_atom("_NET_ACTIVE_WINDOW"), X.AnyPropertyType)
        if not prop or not prop.value or not prop.value[0]:
            dpy.close()
            return info
        xid = int(prop.value[0])
        win = dpy.create_resource_object("window", xid)
        info["xid"] = xid

        pid_prop = win.get_full_property(dpy.intern_atom("_NET_WM_PID"), X.AnyPropertyType)
        if pid_prop and pid_prop.value:
            info["pid"] = int(pid_prop.value[0])

        wm_cls = win.get_wm_class()
        if wm_cls:
            info["wm_class"] = wm_cls[-1]

        name_prop = win.get_full_property(dpy.intern_atom("_NET_WM_NAME"), X.AnyPropertyType)
        if name_prop and name_prop.value:
            val = name_prop.value
            info["title"] = val.decode("utf-8", errors="ignore") if isinstance(val, bytes) else str(val)
        else:
            info["title"] = win.get_wm_name() or ""

        geom = win.get_geometry()
        coords = root.translate_coords(win, 0, 0)
        info["bounds"] = (coords.x, coords.y, geom.width, geom.height)
        dpy.close()
    except Exception:
        pass
    return info


def scan_active_window_atspi(active_info: dict[str, Any]) -> list[dict[str, Any]]:
    """Scans ONLY the focused application window in AT-SPI2 (skips shell, dock, and background windows)."""
    if Atspi is None:
        return []
    target_pid = active_info.get("pid") or 0
    target_title = (active_info.get("title") or "").strip().lower()
    elements: list[dict[str, Any]] = []

    try:
        desktop = Atspi.get_desktop(0)
        app_count = desktop.get_child_count()
        matched_frames = []

        for i in range(app_count):
            app = desktop.get_child_at_index(i)
            if not app:
                continue
            app_name = (app.get_name() or "").strip().lower()
            if app_name in IGNORED_SHELL_NAMES:
                continue
            try:
                app_pid = app.get_process_id()
            except Exception:
                app_pid = 0

            win_count = app.get_child_count()
            for j in range(win_count):
                frame = app.get_child_at_index(j)
                if not frame:
                    continue
                try:
                    state_set = frame.get_state_set()
                    is_active = state_set.contains(Atspi.StateType.ACTIVE)
                except Exception:
                    is_active = False

                fname = (frame.get_name() or "").strip()
                if is_active or (target_pid and app_pid == target_pid and fname):
                    matched_frames.append(frame)
                elif target_title and fname and fname.lower() == target_title:
                    matched_frames.append(frame)

        # Prefer frames explicitly marked ACTIVE
        if len(matched_frames) > 1:
            active_only = []
            for fr in matched_frames:
                try:
                    if fr.get_state_set().contains(Atspi.StateType.ACTIVE):
                        active_only.append(fr)
                except Exception:
                    pass
            if active_only:
                matched_frames = active_only[:1]
            else:
                matched_frames = matched_frames[:1]

        def _walk(node, depth: int) -> None:
            if len(elements) >= DEFAULT_MAX_TREE_ELEMENTS or depth > DEFAULT_MAX_DEPTH or node is None:
                return
            try:
                st = node.get_state_set()
                if not st.contains(Atspi.StateType.SHOWING) or not st.contains(Atspi.StateType.VISIBLE):
                    return
                role_name = (node.get_role_name() or "").lower()
                if role_name in INTERACTIVE_ATSPI_ROLES:
                    comp = node.get_component_iface()
                    if comp is not None:
                        rect = comp.get_extents(Atspi.CoordType.SCREEN)
                        if rect.width >= 4 and rect.height >= 4 and rect.x >= -10 and rect.y >= -10:
                            label = (node.get_name() or "").strip()
                            if not label:
                                txt_iface = node.get_text_iface()
                                if txt_iface is not None:
                                    try:
                                        cnt = min(txt_iface.get_character_count(), 80)
                                        if cnt > 0:
                                            label = txt_iface.get_text(0, cnt).strip()
                                    except Exception:
                                        pass
                            elements.append(
                                {
                                    "id": len(elements),
                                    "role": role_name,
                                    "name": label[:80],
                                    "x": int(rect.x + rect.width // 2),
                                    "y": int(rect.y + rect.height // 2),
                                    "bbox": (int(rect.x), int(rect.y), int(rect.width), int(rect.height)),
                                }
                            )
                child_cnt = node.get_child_count()
                for k in range(min(child_cnt, 150)):
                    if len(elements) >= DEFAULT_MAX_TREE_ELEMENTS:
                        break
                    _walk(node.get_child_at_index(k), depth + 1)
            except Exception:
                return

        for fr in matched_frames:
            _walk(fr, 0)
    except Exception:
        pass

    return elements


def capture_fast_screenshot(annotate_nodes: list[dict[str, Any]] | None = None) -> tuple[bytes, float, tuple[int, int]]:
    """Captures X11 screen via MSS and encodes fast PNG (compress_level=1)."""
    with mss.mss() as sct:
        mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        raw = sct.grab(mon)
        orig_w, orig_h = raw.width, raw.height
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    if annotate_nodes:
        draw = ImageDraw.Draw(img)
        for node in annotate_nodes:
            bx, by, bw, bh = node["bbox"]
            draw.rectangle([bx, by, bx + bw, by + bh], outline=(255, 40, 40), width=2)
            draw.text((bx + 2, max(0, by - 12)), f"[{node['id']}]", fill=(255, 40, 40))

    coord_scale = 1.0
    if orig_w > MAX_IMAGE_WIDTH or orig_h > MAX_IMAGE_HEIGHT:
        scale_w = MAX_IMAGE_WIDTH / float(orig_w)
        scale_h = MAX_IMAGE_HEIGHT / float(orig_h)
        ratio = min(scale_w, scale_h)
        new_w = max(1, int(round(orig_w * ratio)))
        new_h = max(1, int(round(orig_h * ratio)))
        img = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
        coord_scale = round(1.0 / ratio, 4)

    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=1)
    return buf.getvalue(), coord_scale, (orig_w, orig_h)


def _run_xdotool(args: list[str]) -> None:
    subprocess.run(["xdotool", *args], check=True, timeout=8)


mcp = FastMCP("linux-gui-mcp")


@mcp.tool()
def Snapshot(use_vision: bool = True, use_ui_tree: bool = False) -> list[TextContent | ImageContent]:
    """
    Capture desktop state.
    - Fast Pure-Vision Mode (default: use_vision=True, use_ui_tree=False): ~0.06s, skips AT-SPI2 traversal.
    - Active-Window AT-SPI2 Mode (use_ui_tree=True): scans ONLY the focused window (<0.15s).
    """
    GUARD.start()
    t0 = time.perf_counter()
    active = get_active_window_info()
    nodes = scan_active_window_atspi(active) if use_ui_tree else []

    lines = [
        f"Active Window: {active['title']!r} (class={active['wm_class']!r}, pid={active['pid']}, bounds={active['bounds']})"
    ]

    contents: list[TextContent | ImageContent] = []
    if use_vision:
        png_bytes, coord_scale, (sw, sh) = capture_fast_screenshot(nodes if use_ui_tree else None)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        lines.append(f"Screen Physical Size: {sw}x{sh} | Screenshot Coordinate Scale: {coord_scale} | Elapsed: {elapsed_ms}ms")
        if use_ui_tree:
            lines.append(f"Interactive Controls (Focused Window Only, count={len(nodes)}):")
            for n in nodes:
                lines.append(f"  [{n['id']}] {n['role']} {n['name']!r} -> center=({n['x']}, {n['y']}) bbox={n['bbox']}")
        contents.append(TextContent(type="text", text="\n".join(lines)))
        contents.append(
            ImageContent(
                type="image",
                data=base64.b64encode(png_bytes).decode("ascii"),
                mimeType="image/png",
            )
        )
    else:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        lines.append(f"Elapsed: {elapsed_ms}ms | Interactive Controls (count={len(nodes)}):")
        for n in nodes:
            lines.append(f"  [{n['id']}] {n['role']} {n['name']!r} -> center=({n['x']}, {n['y']}) bbox={n['bbox']}")
        contents.append(TextContent(type="text", text="\n".join(lines)))

    return contents


@mcp.tool()
def Click(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
    """Click at physical screen coordinates (x, y). button: left | middle | right."""
    GUARD.start()
    btn_map = {"left": "1", "middle": "2", "right": "3"}
    b = btn_map.get(button.lower(), "1")
    GUARD.begin_ai_action()
    try:
        _run_xdotool(["mousemove", "--sync", str(x), str(y), "click", "--repeat", str(max(1, clicks)), b])
    finally:
        GUARD.end_ai_action()
    return f"Clicked ({x}, {y}) button={button} clicks={clicks}"


@mcp.tool()
def Move(x: int, y: int) -> str:
    """Move mouse cursor to physical screen coordinates (x, y)."""
    GUARD.start()
    GUARD.begin_ai_action()
    try:
        _run_xdotool(["mousemove", "--sync", str(x), str(y)])
    finally:
        GUARD.end_ai_action()
    return f"Moved cursor to ({x}, {y})"


@mcp.tool()
def Drag(from_x: int, from_y: int, to_x: int, to_y: int, button: str = "left") -> str:
    """Drag mouse from (from_x, from_y) to (to_x, to_y)."""
    GUARD.start()
    btn_map = {"left": "1", "middle": "2", "right": "3"}
    b = btn_map.get(button.lower(), "1")
    GUARD.begin_ai_action()
    try:
        _run_xdotool(
            [
                "mousemove",
                "--sync",
                str(from_x),
                str(from_y),
                "mousedown",
                b,
                "mousemove",
                "--sync",
                str(to_x),
                str(to_y),
                "mouseup",
                b,
            ]
        )
    finally:
        GUARD.end_ai_action()
    return f"Dragged ({from_x}, {from_y}) -> ({to_x}, {to_y})"


@mcp.tool()
def Type(
    text: str,
    x: int | None = None,
    y: int | None = None,
    clear: bool = False,
    press_enter: bool = False,
) -> str:
    """Type Unicode/Chinese/English text cleanly via X11 clipboard paste."""
    GUARD.start()
    GUARD.begin_ai_action()
    try:
        if x is not None and y is not None:
            _run_xdotool(["mousemove", "--sync", str(x), str(y), "click", "1"])
            time.sleep(0.05)

        active = get_active_window_info()
        is_term = (active.get("wm_class") or "").lower() in TERMINAL_WM_CLASSES

        if clear:
            _run_xdotool(["key", "--clearmodifiers", "ctrl+a", "BackSpace"])
            time.sleep(0.03)

        prev_clip: bytes | None = None
        if shutil.which("xclip"):
            res = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, timeout=2)
            if res.returncode == 0:
                prev_clip = res.stdout
            subprocess.run(
                ["xclip", "-selection", "clipboard", "-i"],
                input=text.encode("utf-8"),
                check=True,
                timeout=3,
            )
            paste_Combo = "ctrl+shift+v" if is_term else "ctrl+v"
            _run_xdotool(["key", "--clearmodifiers", paste_Combo])
            time.sleep(0.08)
            if prev_clip is not None:
                subprocess.run(["xclip", "-selection", "clipboard", "-i"], input=prev_clip, check=False, timeout=2)
        else:
            _run_xdotool(["type", "--clearmodifiers", "--delay", "5", text])

        if press_enter:
            _run_xdotool(["key", "--clearmodifiers", "Return"])
    finally:
        GUARD.end_ai_action()
    return f"Typed {len(text)} chars (press_enter={press_enter})"


@mcp.tool()
def Shortcut(keys: str) -> str:
    """Send keyboard shortcut, e.g. 'ctrl+l', 'alt+Tab', 'super', 'ctrl+shift+t', 'Escape'."""
    GUARD.start()
    key_map = {
        "win": "Super_L",
        "super": "Super_L",
        "cmd": "Super_L",
        "enter": "Return",
        "esc": "Escape",
        "del": "Delete",
        "backspace": "BackSpace",
        "pgup": "Prior",
        "pgdn": "Next",
    }
    parts = [p.strip() for p in keys.replace("-", "+").split("+") if p.strip()]
    mapped = [key_map.get(p.lower(), p) for p in parts]
    combo = "+".join(mapped)
    GUARD.begin_ai_action()
    try:
        _run_xdotool(["key", "--clearmodifiers", combo])
    finally:
        GUARD.end_ai_action()
    return f"Sent shortcut: {combo}"


@mcp.tool()
def Scroll(x: int | None = None, y: int | None = None, direction: str = "down", amount: int = 3) -> str:
    """Scroll wheel at (x, y) or current cursor. direction: up | down | left | right."""
    GUARD.start()
    dir_map = {"up": "4", "down": "5", "left": "6", "right": "7"}
    btn = dir_map.get(direction.lower(), "5")
    GUARD.begin_ai_action()
    try:
        cmd: list[str] = []
        if x is not None and y is not None:
            cmd.extend(["mousemove", "--sync", str(x), str(y)])
        cmd.extend(["click", "--repeat", str(max(1, amount)), btn])
        _run_xdotool(cmd)
    finally:
        GUARD.end_ai_action()
    return f"Scrolled {direction} x{amount}"


@mcp.tool()
def App(
    mode: str = "launch",
    name: str = "",
    x: int = 0,
    y: int = 0,
    width: int = 1280,
    height: int = 800,
) -> str:
    """Manage desktop apps/windows. mode: launch | switch | resize | list."""
    m = mode.lower()
    if m == "list":
        out = subprocess.check_output(["wmctrl", "-l", "-x"], text=True, timeout=4)
        return out.strip()
    if m == "switch":
        subprocess.run(["wmctrl", "-a", name], check=True, timeout=4)
        return f"Switched focus to window matching {name!r}"
    if m == "resize":
        target = name if name else ":ACTIVE:"
        subprocess.run(["wmctrl", "-r", target, "-b", "remove,maximized_vert,maximized_horz"], check=False, timeout=4)
        subprocess.run(["wmctrl", "-r", target, "-e", f"0,{x},{y},{width},{height}"], check=True, timeout=4)
        return f"Resized {target!r} to {width}x{height}+{x}+{y}"
    if m == "launch":
        if name.endswith(".desktop"):
            subprocess.Popen(["gtk-launch", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(name, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Launched {name!r}"
    raise ValueError(f"Unsupported mode: {mode!r} (expected launch | switch | resize | list)")


@mcp.tool()
def Wait(seconds: float = 1.0) -> str:
    """Wait for UI transitions (capped at 15s)."""
    dur = max(0.0, min(float(seconds), 15.0))
    time.sleep(dur)
    return f"Waited {dur}s"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
