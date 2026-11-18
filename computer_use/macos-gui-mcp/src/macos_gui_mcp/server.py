# -*- coding: utf-8 -*-
"""
macos-gui-mcp: Fast macOS Aqua + CoreGraphics Computer Use MCP Server
---------------------------------------------------------------------
Mirrors the speed & safety optimizations of Windows-MCP & linux-gui-mcp:
1. Default multimodal vision (`use_vision=True, use_ui_tree=False`) -> ~0.08s pure-vision Snapshot
   normalized 1:1 to macOS Retina logical point coordinates (`coord_scale = 1.0`).
2. Active-Window-Only Accessibility UI Tree (`use_ui_tree=True`) via JXA / System Events.
3. Human mouse-shake takeover guard (`~/.macos-mcp/config.toml`: 0s countdown, 2s cooldown).
4. Zero-drop UTF-8 / CJK text input via macOS `pbcopy` + `Cmd+V` paste with clipboard restore.
"""

from __future__ import annotations

import base64
import ctypes
from dataclasses import dataclass
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
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


# ---------------------------------------------------------------------------
# 1. CoreGraphics / ApplicationServices ctypes Bindings (Built into macOS)
# ---------------------------------------------------------------------------
class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


_cg = None
if sys.platform == "darwin":
    try:
        _cg = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        _cg.CGMainDisplayID.argtypes = []
        _cg.CGMainDisplayID.restype = ctypes.c_uint32
        _cg.CGDisplayPixelsWide.argtypes = [ctypes.c_uint32]
        _cg.CGDisplayPixelsWide.restype = ctypes.c_size_t
        _cg.CGDisplayPixelsHigh.argtypes = [ctypes.c_uint32]
        _cg.CGDisplayPixelsHigh.restype = ctypes.c_size_t
        _cg.CGEventCreate.argtypes = [ctypes.c_void_p]
        _cg.CGEventCreate.restype = ctypes.c_void_p
        _cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]
        _cg.CGEventGetLocation.restype = CGPoint
        _cg.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]
        _cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
        _cg.CGEventSetIntegerValueField.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int64]
        _cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        _cg.CGEventCreateScrollWheelEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32]
        _cg.CGEventCreateScrollWheelEvent.restype = ctypes.c_void_p
        _cg.CFRelease.argtypes = [ctypes.c_void_p]
    except Exception:
        _cg = None

# CGEvent constants
kCGEventLeftMouseDown = 1
kCGEventLeftMouseUp = 2
kCGEventRightMouseDown = 3
kCGEventRightMouseUp = 4
kCGEventMouseMoved = 5
kCGEventLeftMouseDragged = 6
kCGEventRightMouseDragged = 7
kCGEventOtherMouseDown = 25
kCGEventOtherMouseUp = 26
kCGEventOtherMouseDragged = 27
kCGMouseButtonLeft = 0
kCGMouseButtonRight = 1
kCGMouseButtonCenter = 2
kCGHIDEventTap = 0
kCGMouseEventClickState = 1
kCGScrollEventUnitLine = 1


def _get_logical_display_size() -> tuple[int, int]:
    if _cg is not None:
        try:
            did = _cg.CGMainDisplayID()
            w = int(_cg.CGDisplayPixelsWide(did))
            h = int(_cg.CGDisplayPixelsHigh(did))
            if w > 0 and h > 0:
                return w, h
        except Exception:
            pass
    return 1440, 900


def _get_cursor_pos() -> tuple[float, float] | None:
    if _cg is None:
        return None
    try:
        ev = _cg.CGEventCreate(None)
        if not ev:
            return None
        try:
            pt = _cg.CGEventGetLocation(ev)
            return float(pt.x), float(pt.y)
        finally:
            _cg.CFRelease(ev)
    except Exception:
        return None


def _cg_mouse_move(x: float, y: float) -> None:
    if _cg is None:
        raise RuntimeError("CoreGraphics unavailable (requires macOS)")
    ev = _cg.CGEventCreateMouseEvent(None, kCGEventMouseMoved, CGPoint(x, y), kCGMouseButtonLeft)
    if ev:
        try:
            _cg.CGEventPost(kCGHIDEventTap, ev)
        finally:
            _cg.CFRelease(ev)


def _cg_mouse_click(x: float, y: float, button: str = "left", clicks: int = 1) -> None:
    if _cg is None:
        raise RuntimeError("CoreGraphics unavailable (requires macOS)")
    b = button.lower()
    if b == "right":
        down_t, up_t, btn = kCGEventRightMouseDown, kCGEventRightMouseUp, kCGMouseButtonRight
    elif b == "middle":
        down_t, up_t, btn = kCGEventOtherMouseDown, kCGEventOtherMouseUp, kCGMouseButtonCenter
    else:
        down_t, up_t, btn = kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGMouseButtonLeft

    pt = CGPoint(x, y)
    _cg_mouse_move(x, y)
    time.sleep(0.015)
    for i in range(1, max(1, clicks) + 1):
        ev_down = _cg.CGEventCreateMouseEvent(None, down_t, pt, btn)
        ev_up = _cg.CGEventCreateMouseEvent(None, up_t, pt, btn)
        if ev_down and ev_up:
            try:
                _cg.CGEventSetIntegerValueField(ev_down, kCGMouseEventClickState, i)
                _cg.CGEventSetIntegerValueField(ev_up, kCGMouseEventClickState, i)
                _cg.CGEventPost(kCGHIDEventTap, ev_down)
                time.sleep(0.015)
                _cg.CGEventPost(kCGHIDEventTap, ev_up)
            finally:
                _cg.CFRelease(ev_down)
                _cg.CFRelease(ev_up)
        if i < clicks:
            time.sleep(0.03)


def _cg_mouse_drag(fx: float, fy: float, tx: float, ty: float, button: str = "left") -> None:
    if _cg is None:
        raise RuntimeError("CoreGraphics unavailable (requires macOS)")
    b = button.lower()
    if b == "right":
        down_t, drag_t, up_t, btn = kCGEventRightMouseDown, kCGEventRightMouseDragged, kCGEventRightMouseUp, kCGMouseButtonRight
    else:
        down_t, drag_t, up_t, btn = kCGEventLeftMouseDown, kCGEventLeftMouseDragged, kCGEventLeftMouseUp, kCGMouseButtonLeft

    _cg_mouse_move(fx, fy)
    time.sleep(0.02)
    ev_down = _cg.CGEventCreateMouseEvent(None, down_t, CGPoint(fx, fy), btn)
    if ev_down:
        _cg.CGEventPost(kCGHIDEventTap, ev_down)
        _cg.CFRelease(ev_down)
    steps = 12
    for s in range(1, steps + 1):
        ix = fx + (tx - fx) * (s / steps)
        iy = fy + (ty - fy) * (s / steps)
        ev_drag = _cg.CGEventCreateMouseEvent(None, drag_t, CGPoint(ix, iy), btn)
        if ev_drag:
            _cg.CGEventPost(kCGHIDEventTap, ev_drag)
            _cg.CFRelease(ev_drag)
        time.sleep(0.01)
    ev_up = _cg.CGEventCreateMouseEvent(None, up_t, CGPoint(tx, ty), btn)
    if ev_up:
        _cg.CGEventPost(kCGHIDEventTap, ev_up)
        _cg.CFRelease(ev_up)


# ---------------------------------------------------------------------------
# 2. Human Mouse-Shake Takeover Guard (~/.macos-mcp/config.toml)
# ---------------------------------------------------------------------------
@dataclass
class ControlConfig:
    enabled: bool = True
    consent_countdown_seconds: float = 0.0
    idle_timeout_seconds: float = 2.0
    mouse_takeover_units: float = 500.0


def load_control_config() -> ControlConfig:
    cfg_path = Path.home() / ".macos-mcp" / "config.toml"
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
    def __init__(self, cfg: ControlConfig) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._ai_busy = 0
        self._accum_dist = 0.0
        self._last_takeover_ts = 0.0
        self._started = False

    def start(self) -> None:
        if self._started or not self.cfg.enabled or _cg is None:
            return
        self._started = True
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _monitor_loop(self) -> None:
        pos = _get_cursor_pos()
        if pos is None:
            return
        last_x, last_y = pos
        while True:
            time.sleep(0.04)
            cur = _get_cursor_pos()
            if cur is None:
                continue
            cx, cy = cur
            dx, dy = cx - last_x, cy - last_y
            last_x, last_y = cx, cy
            dist = math.hypot(dx, dy)
            with self._lock:
                if self._ai_busy == 0:
                    if dist > 4.0:
                        self._accum_dist += dist
                        if self._accum_dist >= self.cfg.mouse_takeover_units:
                            self._last_takeover_ts = time.monotonic()
                            self._accum_dist = 0.0
                    else:
                        self._accum_dist = max(0.0, self._accum_dist * 0.85)

    def begin_ai_action(self) -> None:
        while self.cfg.enabled:
            with self._lock:
                rem = self.cfg.idle_timeout_seconds - (time.monotonic() - self._last_takeover_ts)
                if rem <= 0:
                    self._ai_busy += 1
                    return
            time.sleep(min(0.1, rem))
        with self._lock:
            self._ai_busy += 1

    def end_ai_action(self) -> None:
        with self._lock:
            self._ai_busy = max(0, self._ai_busy - 1)


GUARD = MouseTakeoverGuard(load_control_config())


# ---------------------------------------------------------------------------
# 3. Focused Window Info & Fast Retina-Normalized Screenshot
# ---------------------------------------------------------------------------
def get_active_window_info() -> dict[str, Any]:
    jxa = """
    const se = Application('System Events');
    const procs = se.applicationProcesses.whose({frontmost: true});
    if (procs.length === 0) { JSON.stringify({app: '', title: '', pid: 0, bounds: [0,0,0,0]}); }
    else {
      const p = procs[0];
      let title = '', bounds = [0,0,0,0];
      try {
        if (p.windows.length > 0) {
          const w = p.windows[0];
          title = w.name() || '';
          const pos = w.position();
          const sz = w.size();
          bounds = [pos[0], pos[1], sz[0], sz[1]];
        }
      } catch (e) {}
      JSON.stringify({app: p.name(), title: title, pid: p.unixId(), bounds: bounds});
    }
    """
    try:
        out = subprocess.check_output(["osascript", "-l", "JavaScript", "-e", jxa], text=True, timeout=2.5)
        return json.loads(out.strip())
    except Exception:
        return {"app": "", "title": "", "pid": 0, "bounds": [0, 0, 0, 0]}


def scan_focused_window_ax(limit: int = 200) -> list[dict[str, Any]]:
    jxa = f"""
    const se = Application('System Events');
    const procs = se.applicationProcesses.whose({{frontmost: true}});
    const out = [];
    if (procs.length > 0 && procs[0].windows.length > 0) {{
      const win = procs[0].windows[0];
      const elems = win.entireContents();
      const maxN = Math.min(elems.length, 600);
      for (let i = 0; i < maxN && out.length < {limit}; i++) {{
        try {{
          const el = elems[i];
          const role = el.role();
          if (!['AXButton','AXTextField','AXTextArea','AXCheckBox','AXRadioButton','AXPopUpButton','AXMenuItem','AXLink','AXTabGroup','AXStaticText'].includes(role)) continue;
          const name = (el.title() || el.description() || el.value() || '').toString().slice(0, 80);
          const pos = el.position();
          const sz = el.size();
          if (sz[0] > 2 && sz[1] > 2) {{
            out.push({{id: out.length + 1, role: role, name: name, x: Math.round(pos[0] + sz[0]/2), y: Math.round(pos[1] + sz[1]/2), bbox: [pos[0], pos[1], sz[0], sz[1]]}});
          }}
        }} catch (e) {{}}
      }}
    }}
    JSON.stringify(out);
    """
    try:
        raw = subprocess.check_output(["osascript", "-l", "JavaScript", "-e", jxa], text=True, timeout=4.0)
        return json.loads(raw.strip())
    except Exception:
        return []


def capture_fast_screenshot(annotate_nodes: list[dict[str, Any]] | None = None) -> tuple[bytes, float, tuple[int, int]]:
    logical_w, logical_h = _get_logical_display_size()
    img: Image.Image | None = None

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        tmp_png = tf.name
    try:
        res = subprocess.run(["screencapture", "-x", "-t", "png", tmp_png], check=False, timeout=3)
        if res.returncode == 0 and os.path.getsize(tmp_png) > 0:
            with Image.open(tmp_png) as cap:
                img = cap.convert("RGB")
    except Exception:
        img = None
    finally:
        try:
            os.unlink(tmp_png)
        except OSError:
            pass

    if img is None:
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0])
            img = Image.frombytes("RGB", shot.size, shot.rgb)

    # Normalize Retina 2x backing pixels directly into 1:1 macOS logical point space
    if img.size != (logical_w, logical_h) and logical_w > 0 and logical_h > 0:
        img = img.resize((logical_w, logical_h), Image.Resampling.BILINEAR)

    if annotate_nodes:
        draw = ImageDraw.Draw(img)
        for node in annotate_nodes:
            bx, by, bw, bh = node["bbox"]
            draw.rectangle([bx, by, bx + bw, by + bh], outline=(255, 40, 40), width=2)
            draw.text((bx + 2, max(0, by - 12)), f"[{node['id']}]", fill=(255, 40, 40))

    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=1)
    return buf.getvalue(), 1.0, (logical_w, logical_h)


# ---------------------------------------------------------------------------
# 4. MCP Tools
# ---------------------------------------------------------------------------
mcp = FastMCP("macos-gui-mcp")


@mcp.tool()
def Snapshot(use_vision: bool = True, use_ui_tree: bool = False) -> list[TextContent | ImageContent]:
    """
    Capture macOS desktop state (1:1 Retina logical point coordinates).
    - Fast Pure-Vision Mode (default: use_vision=True, use_ui_tree=False): ~0.08s.
    - Focused-Window Accessibility Mode (use_ui_tree=True): extracts interactive AX elements.
    """
    GUARD.start()
    t0 = time.perf_counter()
    active = get_active_window_info()
    nodes = scan_focused_window_ax() if use_ui_tree else []
    lines = [
        f"Active App: {active['app']!r} | Window: {active['title']!r} (pid={active['pid']}, bounds={active['bounds']})"
    ]
    contents: list[TextContent | ImageContent] = []
    if use_vision:
        png_bytes, coord_scale, (lw, lh) = capture_fast_screenshot(nodes if use_ui_tree else None)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        lines.append(f"Logical Point Space: {lw}x{lh} | Coordinate Scale: {coord_scale} | Elapsed: {elapsed_ms}ms")
        if use_ui_tree:
            lines.append(f"Interactive AX Elements (Focused Window, count={len(nodes)}):")
            for n in nodes:
                lines.append(f"  [{n['id']}] {n['role']} {n['name']!r} -> center=({n['x']}, {n['y']})")
        contents.append(TextContent(type="text", text="\n".join(lines)))
        contents.append(
            ImageContent(type="image", data=base64.b64encode(png_bytes).decode("ascii"), mimeType="image/png")
        )
    else:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        lines.append(f"Elapsed: {elapsed_ms}ms | Interactive AX Elements (count={len(nodes)}):")
        for n in nodes:
            lines.append(f"  [{n['id']}] {n['role']} {n['name']!r} -> center=({n['x']}, {n['y']})")
        contents.append(TextContent(type="text", text="\n".join(lines)))
    return contents


@mcp.tool()
def Click(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
    """Click at macOS logical screen coordinates (x, y). button: left | middle | right."""
    GUARD.start()
    GUARD.begin_ai_action()
    try:
        _cg_mouse_click(float(x), float(y), button=button, clicks=clicks)
    finally:
        GUARD.end_ai_action()
    return f"Clicked ({x}, {y}) button={button} clicks={clicks}"


@mcp.tool()
def Move(x: int, y: int) -> str:
    """Move cursor to macOS logical screen coordinates (x, y)."""
    GUARD.start()
    GUARD.begin_ai_action()
    try:
        _cg_mouse_move(float(x), float(y))
    finally:
        GUARD.end_ai_action()
    return f"Moved cursor to ({x}, {y})"


@mcp.tool()
def Drag(from_x: int, from_y: int, to_x: int, to_y: int, button: str = "left") -> str:
    """Drag mouse from (from_x, from_y) to (to_x, to_y) in logical coordinates."""
    GUARD.start()
    GUARD.begin_ai_action()
    try:
        _cg_mouse_drag(float(from_x), float(from_y), float(to_x), float(to_y), button=button)
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
    """Type Unicode/Chinese/English text cleanly via macOS pbcopy + Cmd+V paste."""
    GUARD.start()
    GUARD.begin_ai_action()
    try:
        if x is not None and y is not None:
            _cg_mouse_click(float(x), float(y), "left", 1)
            time.sleep(0.05)
        if clear:
            subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to keystroke "a" using command down', "-e", 'tell application "System Events" to key code 51'],
                check=False,
                timeout=3,
            )
            time.sleep(0.03)

        prev_clip: bytes | None = None
        res = subprocess.run(["pbpaste"], capture_output=True, timeout=2)
        if res.returncode == 0:
            prev_clip = res.stdout

        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, timeout=3)
        subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
            check=True,
            timeout=3,
        )
        time.sleep(0.08)
        if prev_clip is not None:
            subprocess.run(["pbcopy"], input=prev_clip, check=False, timeout=2)

        if press_enter:
            subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 36'], check=False, timeout=2)
    finally:
        GUARD.end_ai_action()
    return f"Typed {len(text)} chars (press_enter={press_enter})"


@mcp.tool()
def Shortcut(keys: str) -> str:
    """Send macOS shortcut, e.g. 'cmd+l', 'cmd+space', 'cmd+shift+p', 'ctrl+c', 'Escape'."""
    GUARD.start()
    parts = [p.strip().lower() for p in keys.replace("-", "+").split("+") if p.strip()]
    mods: list[str] = []
    key_token = ""
    for p in parts:
        if p in ("cmd", "command", "super", "win"):
            mods.append("command down")
        elif p in ("ctrl", "control"):
            mods.append("control down")
        elif p in ("alt", "opt", "option"):
            mods.append("option down")
        elif p in ("shift",):
            mods.append("shift down")
        else:
            key_token = p

    special_codes = {"enter": 36, "return": 36, "esc": 53, "escape": 53, "tab": 48, "space": 49, "backspace": 51, "delete": 117}
    using_clause = f" using {{{', '.join(mods)}}}" if mods else ""
    if key_token in special_codes:
        script = f'tell application "System Events" to key code {special_codes[key_token]}{using_clause}'
    else:
        safe_k = key_token.replace('"', '\\"')
        script = f'tell application "System Events" to keystroke "{safe_k}"{using_clause}'

    GUARD.begin_ai_action()
    try:
        subprocess.run(["osascript", "-e", script], check=True, timeout=3)
    finally:
        GUARD.end_ai_action()
    return f"Sent shortcut: {keys}"


@mcp.tool()
def Scroll(x: int | None = None, y: int | None = None, direction: str = "down", amount: int = 4) -> str:
    """Scroll wheel at (x, y) or current cursor. direction: up | down."""
    GUARD.start()
    GUARD.begin_ai_action()
    try:
        if x is not None and y is not None:
            _cg_mouse_move(float(x), float(y))
            time.sleep(0.02)
        if _cg is not None:
            delta = int(amount) if direction.lower() == "up" else -int(amount)
            ev = _cg.CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitLine, 1, delta)
            if ev:
                _cg.CGEventPost(kCGHIDEventTap, ev)
                _cg.CFRelease(ev)
    finally:
        GUARD.end_ai_action()
    return f"Scrolled {direction} amount={amount}"


@mcp.tool()
def App(mode: str = "launch", name: str = "") -> str:
    """Manage macOS apps. mode: launch | switch | list."""
    m = mode.lower()
    if m == "list":
        out = subprocess.check_output(
            ["osascript", "-e", 'tell application "System Events" to get name of every application process whose background only is false'],
            text=True,
            timeout=3,
        )
        return out.strip()
    if m in ("launch", "switch"):
        subprocess.run(["open", "-a", name], check=True, timeout=5)
        return f"Activated macOS application {name!r}"
    raise ValueError(f"Unsupported mode: {mode!r} (expected launch | switch | list)")


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
