#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity Conversation Branch / Fork Tool (CLI + Antigravity 2.0 Studio GUI)
------------------------------------------------------------------------------
Clones any existing Antigravity conversation into a brand-new, independent
conversation UUID, supporting branching from ANY historical chat turn.

- Works across Windows and Linux (pure Python standard library).
- Groups conversations in the GUI by Project (flat, non-collapsible), with
  non-project ("outside-of-project") conversations placed at the bottom, plus
  real-time search filtering and full turn prompt preview.
- Populates both `conversation_summaries` and `conversations_fts` (FTS5 index)
  so the branched conversation appears in Antigravity's sidebar and Search
  immediately without restarting!
- Clicking "立即创建并打开新对话 →" clones the conversation AND automatically
  opens the new branch right inside Antigravity on Windows (or places it right
  at the top of the sidebar on Linux/macOS)!
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import time
import uuid
import zlib

AGY_ROOT = Path.home() / ".gemini" / "antigravity"
PROJECTS_DIR = Path.home() / ".gemini" / "config" / "projects"


def _get_app_storage_path() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", "")) / "Antigravity" / "app_storage.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Antigravity" / "app_storage.json"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else (Path.home() / ".config")
    return base / "Antigravity" / "app_storage.json"


APP_STORAGE_PATH = _get_app_storage_path()


# ---------------------------------------------------------------------------
# 1. Pure-Python Protobuf Wire-Format Helpers (Zero External Dependencies)
# ---------------------------------------------------------------------------
def encode_varint(value: int) -> bytes:
    if value < 0:
        value &= (1 << 64) - 1
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def decode_varint(buf: bytes, pos: int) -> tuple[int, int]:
    val = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            return val, pos
        shift += 7


def parse_pb_fields(buf: bytes) -> list[tuple[int, int, int | bytes]]:
    pos, end = 0, len(buf)
    fields: list[tuple[int, int, int | bytes]] = []
    while pos < end:
        tag, pos = decode_varint(buf, pos)
        fnum, wtype = tag >> 3, tag & 0x07
        if wtype == 0:
            val, pos = decode_varint(buf, pos)
            fields.append((fnum, wtype, val))
        elif wtype == 1:
            fields.append((fnum, wtype, buf[pos : pos + 8]))
            pos += 8
        elif wtype == 2:
            ln, pos = decode_varint(buf, pos)
            fields.append((fnum, wtype, buf[pos : pos + ln]))
            pos += ln
        elif wtype == 5:
            fields.append((fnum, wtype, buf[pos : pos + 4]))
            pos += 4
        else:
            raise ValueError(f"Unsupported protobuf wire type {wtype}")
    return fields


def serialize_pb_fields(fields: list[tuple[int, int, int | bytes]]) -> bytes:
    out = bytearray()
    for fnum, wtype, val in fields:
        out.extend(encode_varint((fnum << 3) | wtype))
        if wtype == 0:
            assert isinstance(val, int)
            out.extend(encode_varint(val))
        elif wtype == 2:
            assert isinstance(val, (bytes, bytearray))
            out.extend(encode_varint(len(val)))
            out.extend(val)
        elif wtype in (1, 5):
            assert isinstance(val, (bytes, bytearray))
            out.extend(val)
    return bytes(out)


def make_pb_timestamp(epoch_ns: int) -> bytes:
    secs = epoch_ns // 1_000_000_000
    nanos = epoch_ns % 1_000_000_000
    fields: list[tuple[int, int, int | bytes]] = [(1, 0, secs)]
    if nanos:
        fields.append((2, 0, nanos))
    return serialize_pb_fields(fields)


def gen_metadata_max_step(blob: bytes) -> int:
    try:
        for fnum, wtype, val in parse_pb_fields(blob):
            if fnum == 2 and wtype == 2 and isinstance(val, bytes):
                pos, max_s = 0, -1
                while pos < len(val):
                    s, pos = decode_varint(val, pos)
                    if s > max_s:
                        max_s = s
                return max_s
    except Exception:
        pass
    return -1


def rebuild_raw_summary(
    raw: bytes,
    *,
    old_cid: str,
    new_cid: str,
    old_tid: str,
    new_tid: str,
    new_title: str,
    new_step_count: int,
    new_last_user_idx: int,
    now_ns: int,
) -> bytes:
    if not raw:
        return b""

    old_cid_b = old_cid.encode("ascii")
    new_cid_b = new_cid.encode("ascii")
    old_tid_b = old_tid.encode("ascii")
    new_tid_b = new_tid.encode("ascii")
    title_b = new_title.encode("utf-8")
    now_ts = make_pb_timestamp(now_ns)

    new_fields: list[tuple[int, int, int | bytes]] = []
    saw_title = False
    saw_status = False

    for fnum, wtype, val in parse_pb_fields(raw):
        if fnum == 1 and wtype == 2:
            new_fields.append((1, 2, title_b))
            saw_title = True
        elif fnum == 2 and wtype == 0:
            new_fields.append((2, 0, new_step_count))
        elif fnum == 3 and wtype == 2:
            new_fields.append((3, 2, now_ts))
        elif fnum == 4 and wtype == 2:
            new_fields.append((4, 2, new_tid_b))
        elif fnum == 5 and wtype == 0:
            new_fields.append((5, 0, 1))  # 1 = CASCADE_RUN_STATUS_IDLE
            saw_status = True
        elif fnum == 15 and wtype == 2 and isinstance(val, bytes):
            sub = parse_pb_fields(val)
            new_sub: list[tuple[int, int, int | bytes]] = []
            has_sub_title = False
            for sf, sw, sv in sub:
                if sf == 1 and sw == 2:
                    new_sub.append((1, 2, title_b))
                    has_sub_title = True
                elif sf == 7 and sw == 2:
                    new_sub.append((7, 2, now_ts))
                else:
                    if isinstance(sv, bytes):
                        sv = sv.replace(old_cid_b, new_cid_b).replace(old_tid_b, new_tid_b)
                    new_sub.append((sf, sw, sv))
            if not has_sub_title:
                new_sub.insert(0, (1, 2, title_b))
            new_fields.append((15, 2, serialize_pb_fields(new_sub)))
        elif fnum == 16 and wtype == 0:
            new_fields.append((16, 0, max(0, new_last_user_idx)))
        elif fnum == 29 and wtype == 0:
            continue
        else:
            if isinstance(val, bytes):
                val = val.replace(old_cid_b, new_cid_b).replace(old_tid_b, new_tid_b)
            new_fields.append((fnum, wtype, val))

    if not saw_title:
        new_fields.insert(0, (1, 2, title_b))
    if not saw_status:
        new_fields.append((5, 0, 1))

    return serialize_pb_fields(new_fields)


# ---------------------------------------------------------------------------
# 2. Project Grouping & User-Turn Inspection Helpers
# ---------------------------------------------------------------------------
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def load_projects_map() -> dict[str, str]:
    """Map project_id -> human-readable project name from ~/.gemini/config/projects/*.json."""
    pmap: dict[str, str] = {}
    if PROJECTS_DIR.exists():
        for jf in PROJECTS_DIR.glob("*.json"):
            try:
                data = json.loads(jf.read_text(encoding="utf-8", errors="ignore"))
                if data.get("sidecar"):
                    continue
                pid = data.get("id") or jf.stem
                pname = data.get("name") or pid[:8]
                pmap[pid] = pname
            except Exception:
                pass
    return pmap


def _extract_user_request_multiline(raw_text: str) -> str:
    if "<USER_REQUEST>" in raw_text and "</USER_REQUEST>" in raw_text:
        raw_text = raw_text.split("<USER_REQUEST>", 1)[1].split("</USER_REQUEST>", 1)[0]
    elif "<ADDITIONAL_METADATA>" in raw_text:
        raw_text = raw_text.split("<ADDITIONAL_METADATA>", 1)[0]
    return raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _clean_user_request_text(raw_text: str) -> str:
    return " ".join(_extract_user_request_multiline(raw_text).split())


def _extract_strings_from_pb(buf: bytes, depth: int = 0) -> list[str]:
    if depth > 5 or not buf:
        return []
    found: list[str] = []
    try:
        for _, wtype, val in parse_pb_fields(buf):
            if wtype == 2 and isinstance(val, bytes) and len(val) >= 2:
                try:
                    s = val.decode("utf-8")
                    if s.isprintable() or any("\u4e00" <= ch <= "\u9fff" or ch in "\r\n\t" for ch in s):
                        if not _UUID_RE.match(s) and not s.startswith("file:///") and not s.startswith("image/"):
                            found.append(s)
                            continue
                except UnicodeDecodeError:
                    pass
                found.extend(_extract_strings_from_pb(val, depth + 1))
    except Exception:
        pass
    return found


def list_all_conversations() -> list[dict]:
    sum_db = AGY_ROOT / "conversation_summaries.db"
    if not sum_db.exists():
        return []
    pmap = load_projects_map()
    conn = sqlite3.connect(f"file:{sum_db.as_posix()}?mode=ro", uri=True, timeout=10.0)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(conversation_summaries)").fetchall()]
        # Also pull fallback project names from conversations_fts chunk_index = -1
        fts_proj: dict[str, str] = {}
        try:
            for cid, proj in conn.execute(
                "SELECT conversation_id, project FROM conversations_fts WHERE chunk_index = -1 AND project != ''"
            ).fetchall():
                fts_proj[cid] = proj
        except Exception:
            pass

        rows = conn.execute(
            "SELECT * FROM conversation_summaries WHERE parent_conversation_id = '' AND killed = 0 ORDER BY last_modified_time DESC"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            cid = d["conversation_id"]
            if not (AGY_ROOT / "conversations" / f"{cid}.db").exists():
                continue
            pid = (d.get("project_id") or "").strip()
            if pid and pid != "outside-of-project":
                d["project_name"] = pmap.get(pid) or fts_proj.get(cid) or pid[:8]
                d["is_in_project"] = True
            else:
                d["project_name"] = ""
                d["is_in_project"] = False
            out.append(d)
        return out
    finally:
        conn.close()


def group_conversations_by_project(convos: list[dict]) -> list[tuple[str, bool, list[dict]]]:
    """
    Returns ordered list of groups: (group_title, is_project, [conversations...])
    - Projects appear first (ordered by the most recently modified conversation in each project).
    - Non-project conversations ("outside-of-project") appear at the very bottom.
    """
    project_order: list[str] = []
    project_buckets: dict[str, list[dict]] = {}
    outside_list: list[dict] = []

    for c in convos:
        if c.get("is_in_project"):
            pname = c["project_name"]
            if pname not in project_buckets:
                project_order.append(pname)
                project_buckets[pname] = []
            project_buckets[pname].append(c)
        else:
            outside_list.append(c)

    groups: list[tuple[str, bool, list[dict]]] = []
    for pname in project_order:
        groups.append((pname, True, project_buckets[pname]))
    if outside_list:
        groups.append(("未归属项目对话", False, outside_list))
    return groups


def get_conversation_turns(cid: str, status: str = "") -> list[dict]:
    conv_db = AGY_ROOT / "conversations" / f"{cid}.db"
    if not conv_db.exists():
        return []

    transcript_map: dict[int, tuple[str, str, bool]] = {}
    t_path = AGY_ROOT / "brain" / cid / ".system_generated" / "logs" / "transcript.jsonl"
    if t_path.exists():
        try:
            for line in t_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if '"USER_INPUT"' in line:
                    obj = json.loads(line)
                    if obj.get("type") == "USER_INPUT":
                        sidx = int(obj.get("step_index", -1))
                        created = obj.get("created_at", "")
                        trunc_fields = obj.get("truncated_fields") or []
                        is_trunc = "content" in trunc_fields
                        full_txt = _extract_user_request_multiline(obj.get("content", ""))
                        transcript_map[sidx] = (created, full_txt, is_trunc)
        except Exception:
            pass

    conn = sqlite3.connect(f"file:{conv_db.as_posix()}?mode=ro", uri=True, timeout=10.0)
    try:
        max_row = conn.execute("SELECT MAX(idx) FROM steps").fetchone()
        max_idx = int(max_row[0]) if (max_row and max_row[0] is not None) else -1
        user_rows = conn.execute(
            "SELECT idx, step_payload FROM steps WHERE step_type = 14 ORDER BY idx ASC"
        ).fetchall()
        active_steps = {
            int(r[0])
            for r in conn.execute("SELECT idx FROM steps WHERE status IN (1, 2)").fetchall()
        }
    finally:
        conn.close()

    turns: list[dict] = []
    total_u = len(user_rows)
    for i, (u_idx, payload) in enumerate(user_rows):
        next_u_idx = user_rows[i + 1][0] if (i + 1 < total_u) else (max_idx + 1)
        end_idx = next_u_idx - 1

        is_last_turn = i == total_u - 1
        has_active_step = any(u_idx <= s <= end_idx for s in active_steps)
        in_flight = is_last_turn and (status == "CASCADE_RUN_STATUS_RUNNING" and has_active_step)

        created_at, full_text, is_trunc = transcript_map.get(u_idx, ("", "", False))
        if (not full_text or is_trunc) and payload:
            candidates = _extract_strings_from_pb(payload)
            best = ""
            for c in candidates:
                if "<USER_REQUEST>" in c:
                    best = _extract_user_request_multiline(c)
                    break
                cleaned = _extract_user_request_multiline(c)
                if len(cleaned) > len(best):
                    best = cleaned
            if best:
                full_text = best

        single_line = " ".join(full_text.split()) if full_text else ""

        if created_at:
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone()
                created_fmt = dt.strftime("%m-%d %H:%M")
            except Exception:
                created_fmt = created_at[:16]
        else:
            created_fmt = ""

        turns.append(
            {
                "turn": i + 1,
                "start_idx": u_idx,
                "end_idx": end_idx,
                "cutoff_count": end_idx + 1,
                "completed": not in_flight,
                "created_at": created_fmt,
                "preview": (single_line or "(图片/空消息)")[:140],
                "full_text": full_text or "(本轮为图片或附件消息，无纯文本输入内容)",
            }
        )
    return turns


# ---------------------------------------------------------------------------
# 3. Auto-Open Newly Cloned Conversation Inside Antigravity Window (Win32)
# ---------------------------------------------------------------------------
def _get_antigravity_zoom_factor() -> float:
    try:
        if APP_STORAGE_PATH.exists():
            data = json.loads(APP_STORAGE_PATH.read_text(encoding="utf-8", errors="ignore"))
            zl = float(data.get("zoomLevel", "0"))
            return 1.2 ** zl
    except Exception:
        pass
    return 1.0


def _attach_win32_default_desktop() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        u32 = ctypes.windll.user32
        u32.OpenDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        u32.OpenDesktopW.restype = wintypes.HANDLE
        u32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
        u32.SetThreadDesktop.restype = wintypes.BOOL
        hdesk = u32.OpenDesktopW("Default", 0, False, 0x01FF)
        if hdesk:
            u32.SetThreadDesktop(hdesk)
    except Exception:
        pass


def auto_open_in_antigravity(search_token: str) -> bool:
    if sys.platform != "win32":
        return False

    _attach_win32_default_desktop()

    import ctypes
    from ctypes import wintypes

    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    dwmapi = ctypes.windll.dwmapi

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, ctypes.c_ssize_t)
    user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.c_ssize_t]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.GetDpiForWindow.argtypes = [wintypes.HWND]
    user32.GetDpiForWindow.restype = wintypes.UINT
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    agy_hwnds: list[int] = []

    def _cb(hwnd: int, _: int) -> bool:
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value != "Chrome_WidgetWin_1":
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        hproc = kernel32.OpenProcess(0x1000, False, pid.value)
        if hproc:
            try:
                buf = ctypes.create_unicode_buffer(1024)
                sz = wintypes.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(sz)):
                    if buf.value.lower().endswith("\\antigravity.exe"):
                        agy_hwnds.append(int(hwnd))
            finally:
                kernel32.CloseHandle(hproc)
        return True

    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    if not agy_hwnds:
        return False

    hwnd = agy_hwnds[0]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
        time.sleep(0.18)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.12)

    frame = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(frame), ctypes.sizeof(frame)) != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(frame))

    dpi = user32.GetDpiForWindow(hwnd) or 96
    dpi_scale = dpi / 96.0
    zoom = _get_antigravity_zoom_factor()

    search_x = frame.left + round(159.5 * zoom * dpi_scale)
    search_y = frame.top + round((30.0 + 21.0 * zoom) * dpi_scale)

    old_pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(old_pt))

    user32.SetCursorPos(search_x, search_y)
    time.sleep(0.02)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.02)
    user32.SetCursorPos(old_pt.x, old_pt.y)

    time.sleep(0.24)

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class _INPUT_U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_U)]

    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT

    inputs: list[INPUT] = []
    for ch in search_token:
        code = ord(ch)
        down = INPUT(type=1)
        down.u.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=0x0004, time=0, dwExtraInfo=0)
        up = INPUT(type=1)
        up.u.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=0x0004 | 0x0002, time=0, dwExtraInfo=0)
        inputs.extend([down, up])

    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))

    time.sleep(0.30)
    enter_down = INPUT(type=1)
    enter_down.u.ki = KEYBDINPUT(wVk=0x0D, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
    enter_up = INPUT(type=1)
    enter_up.u.ki = KEYBDINPUT(wVk=0x0D, wScan=0, dwFlags=0x0002, time=0, dwExtraInfo=0)
    enter_arr = (INPUT * 2)(enter_down, enter_up)
    user32.SendInput(2, enter_arr, ctypes.sizeof(INPUT))
    return True


# ---------------------------------------------------------------------------
# 4. Core Branching Execution (Populates SQLite DB + Summaries + FTS5 Index)
# ---------------------------------------------------------------------------
def resolve_source_conversation(
    sum_conn: sqlite3.Connection, cid: str | None, title_query: str | None
) -> dict:
    cols = [r[1] for r in sum_conn.execute("PRAGMA table_info(conversation_summaries)").fetchall()]
    if cid:
        row = sum_conn.execute(
            "SELECT * FROM conversation_summaries WHERE conversation_id = ?", (cid,)
        ).fetchone()
    elif title_query:
        row = sum_conn.execute(
            "SELECT * FROM conversation_summaries WHERE title LIKE ? AND parent_conversation_id = '' ORDER BY last_modified_time DESC LIMIT 1",
            (f"%{title_query}%",),
        ).fetchone()
    else:
        row = sum_conn.execute(
            "SELECT * FROM conversation_summaries WHERE parent_conversation_id = '' ORDER BY last_modified_time DESC LIMIT 1"
        ).fetchone()

    if not row:
        raise RuntimeError("未找到匹配的源对话")
    return dict(zip(cols, row))


def pick_branch_title(
    sum_conn: sqlite3.Connection, base_title: str, custom_title: str | None, suffix_tag: str = "分支"
) -> str:
    if custom_title:
        return custom_title
    existing = {
        r[0] for r in sum_conn.execute("SELECT title FROM conversation_summaries").fetchall()
    }
    candidate = f"{base_title} [{suffix_tag}]"
    if candidate not in existing:
        return candidate
    idx = 2
    while f"{base_title} [{suffix_tag} {idx}]" in existing:
        idx += 1
    return f"{base_title} [{suffix_tag} {idx}]"


def replace_uuid_bytes(
    blob: bytes | None, old_cid_b: bytes, new_cid_b: bytes, old_tid_b: bytes, new_tid_b: bytes
) -> bytes | None:
    if blob is None:
        return None
    return blob.replace(old_cid_b, new_cid_b).replace(old_tid_b, new_tid_b)


def branch_conversation(
    *,
    source_cid: str | None = None,
    title_query: str | None = None,
    custom_new_title: str | None = None,
    turn_number: int | None = None,
    drop_last: int | None = None,
    up_to_step: int | None = None,
) -> dict:
    sum_db_path = AGY_ROOT / "conversation_summaries.db"
    if not sum_db_path.exists():
        raise FileNotFoundError(f"未找到 Antigravity 对话索引数据库: {sum_db_path}")

    sum_conn = sqlite3.connect(sum_db_path, timeout=15.0)
    try:
        src_info = resolve_source_conversation(sum_conn, source_cid, title_query)
        old_cid = src_info["conversation_id"]
        orig_title = src_info["title"] or "Untitled"

        turns = get_conversation_turns(old_cid, src_info.get("status", ""))
        completed_turns = [t for t in turns if t["completed"]]
        if not completed_turns and turns:
            completed_turns = turns

        selected_turn_info = None
        suffix_tag = "分支"

        if up_to_step is not None:
            cutoff_count = up_to_step + 1
            suffix_tag = f"分支 S{up_to_step}"
        elif drop_last is not None:
            if drop_last < 0 or drop_last >= len(completed_turns):
                raise ValueError(
                    f"--drop-last {drop_last} 超出范围：当前已完成对话共 {len(completed_turns)} 轮"
                )
            target_idx = len(completed_turns) - 1 - drop_last
            selected_turn_info = completed_turns[target_idx]
            cutoff_count = selected_turn_info["cutoff_count"]
            if drop_last > 0:
                suffix_tag = f"分支 1..{selected_turn_info['turn']}轮"
        elif turn_number is not None:
            if turn_number < 0:
                pos_idx = len(completed_turns) + turn_number
                if pos_idx < 0 or pos_idx >= len(completed_turns):
                    raise ValueError(f"--turn {turn_number} 超出范围（共 {len(completed_turns)} 轮）")
                selected_turn_info = completed_turns[pos_idx]
            else:
                matched = [t for t in turns if t["turn"] == turn_number]
                if not matched:
                    raise ValueError(f"未找到第 {turn_number} 轮对话（共 {len(turns)} 轮）")
                selected_turn_info = matched[0]
            cutoff_count = selected_turn_info["cutoff_count"]
            if selected_turn_info["turn"] < len(turns):
                suffix_tag = f"分支 1..{selected_turn_info['turn']}轮"
        else:
            if completed_turns:
                selected_turn_info = completed_turns[-1]
                cutoff_count = selected_turn_info["cutoff_count"]
            else:
                cutoff_count = int(src_info.get("step_count", 0))

        new_title = pick_branch_title(sum_conn, orig_title, custom_new_title, suffix_tag)
    finally:
        sum_conn.close()

    src_conv_db = AGY_ROOT / "conversations" / f"{old_cid}.db"
    if not src_conv_db.exists():
        raise FileNotFoundError(f"未找到源对话数据库: {src_conv_db}")

    new_cid = str(uuid.uuid4())
    new_tid = str(uuid.uuid4())
    search_token = f"agybranch{new_cid.replace('-', '')[:12]}"
    dst_conv_db = AGY_ROOT / "conversations" / f"{new_cid}.db"
    dst_conv_db.parent.mkdir(parents=True, exist_ok=True)

    src_conn = sqlite3.connect(f"file:{src_conv_db.as_posix()}?mode=ro", uri=True, timeout=15.0)
    dst_conn = sqlite3.connect(dst_conv_db, timeout=15.0)
    try:
        src_conn.backup(dst_conn)
    finally:
        src_conn.close()

    old_cid_b = old_cid.encode("ascii")
    new_cid_b = new_cid.encode("ascii")

    try:
        tmeta = dst_conn.execute("SELECT trajectory_id, cascade_id FROM trajectory_meta LIMIT 1").fetchone()
        old_tid = tmeta[0] if tmeta else str(uuid.uuid4())
        old_tid_b = old_tid.encode("ascii")
        new_tid_b = new_tid.encode("ascii")

        dst_conn.execute("DELETE FROM steps WHERE idx >= ?", (cutoff_count,))
        dst_conn.execute("UPDATE steps SET status = 3 WHERE status IN (1, 2)")

        for gm_idx, gm_data in dst_conn.execute("SELECT idx, data FROM gen_metadata").fetchall():
            if gm_data and gen_metadata_max_step(gm_data) >= cutoff_count:
                dst_conn.execute("DELETE FROM gen_metadata WHERE idx = ?", (gm_idx,))

        dst_conn.execute(
            "UPDATE trajectory_meta SET trajectory_id = ?, cascade_id = ?",
            (new_tid, new_cid),
        )

        step_rows = dst_conn.execute(
            "SELECT idx, metadata, error_details, permissions, task_details, render_info, step_payload FROM steps"
        ).fetchall()
        for idx, meta, err, perm, task_d, rend, payload in step_rows:
            dst_conn.execute(
                """UPDATE steps
                   SET metadata=?, error_details=?, permissions=?, task_details=?, render_info=?, step_payload=?
                   WHERE idx=?""",
                (
                    replace_uuid_bytes(meta, old_cid_b, new_cid_b, old_tid_b, new_tid_b),
                    replace_uuid_bytes(err, old_cid_b, new_cid_b, old_tid_b, new_tid_b),
                    replace_uuid_bytes(perm, old_cid_b, new_cid_b, old_tid_b, new_tid_b),
                    replace_uuid_bytes(task_d, old_cid_b, new_cid_b, old_tid_b, new_tid_b),
                    replace_uuid_bytes(rend, old_cid_b, new_cid_b, old_tid_b, new_tid_b),
                    replace_uuid_bytes(payload, old_cid_b, new_cid_b, old_tid_b, new_tid_b),
                    idx,
                ),
            )

        for tbl, pk_col in [
            ("gen_metadata", "idx"),
            ("executor_metadata", "idx"),
            ("parent_references", "idx"),
            ("trajectory_metadata_blob", "id"),
            ("battle_mode_infos", "idx"),
        ]:
            for pk, data in dst_conn.execute(f"SELECT [{pk_col}], data FROM [{tbl}]").fetchall():
                if data:
                    new_data = replace_uuid_bytes(data, old_cid_b, new_cid_b, old_tid_b, new_tid_b)
                    dst_conn.execute(f"UPDATE [{tbl}] SET data=? WHERE [{pk_col}]=?", (new_data, pk))

        final_step_count = dst_conn.execute("SELECT COUNT(*) FROM steps").fetchone()[0]
        last_user_row = dst_conn.execute("SELECT MAX(idx) FROM steps WHERE step_type = 14").fetchone()
        new_last_user_idx = (
            int(last_user_row[0]) if (last_user_row and last_user_row[0] is not None) else -1
        )

        dst_conn.commit()
        dst_conn.execute("PRAGMA journal_mode=WAL")
        dst_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        dst_conn.close()

    # Copy brain/<old_cid> -> brain/<new_cid> & trim transcript.jsonl
    src_brain = AGY_ROOT / "brain" / old_cid
    dst_brain = AGY_ROOT / "brain" / new_cid
    if src_brain.exists():
        def _ignore_heavy_temp(dir_path: str, names: list[str]) -> set[str]:
            p = Path(dir_path)
            if p.name == ".system_generated":
                return {n for n in names if n in ("tasks", "steps")}
            if p.name == "scratch":
                return set(names)
            return set()

        shutil.copytree(src_brain, dst_brain, ignore=_ignore_heavy_temp, dirs_exist_ok=True)
        for f in dst_brain.rglob("*"):
            if not f.is_file():
                continue
            if f.name in ("transcript.jsonl", "transcript_full.jsonl"):
                try:
                    kept_lines = []
                    for ln in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                        try:
                            sidx = int(json.loads(ln).get("step_index", -1))
                            if sidx >= cutoff_count:
                                continue
                        except Exception:
                            pass
                        kept_lines.append(ln.replace(old_cid, new_cid))
                    f.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""), encoding="utf-8")
                except Exception:
                    pass
            elif f.suffix.lower() in (".md", ".json", ".resolved"):
                try:
                    txt = f.read_text(encoding="utf-8")
                    if old_cid in txt:
                        f.write_text(txt.replace(old_cid, new_cid), encoding="utf-8")
                except Exception:
                    pass

    # Write annotations/<new_cid>.pbtxt
    now_ns = time.time_ns()
    now_secs = now_ns // 1_000_000_000
    now_nanos = now_ns % 1_000_000_000
    escaped_title = new_title.replace("\\", "\\\\").replace('"', '\\"')
    ann_path = AGY_ROOT / "annotations" / f"{new_cid}.pbtxt"
    ann_path.parent.mkdir(parents=True, exist_ok=True)
    ann_path.write_bytes(
        f'title:"{escaped_title}" last_user_view_time:{{seconds:{now_secs} nanos:{now_nanos}}}'.encode(
            "utf-8"
        )
    )

    # Insert into conversation_summaries AND conversations_fts
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f+00:00")
    new_raw_summary = rebuild_raw_summary(
        src_info.get("raw_summary") or b"",
        old_cid=old_cid,
        new_cid=new_cid,
        old_tid=old_tid,
        new_tid=new_tid,
        new_title=new_title,
        new_step_count=final_step_count,
        new_last_user_idx=new_last_user_idx,
        now_ns=now_ns,
    )

    new_row = dict(src_info)
    new_row["conversation_id"] = new_cid
    new_row["title"] = new_title
    new_row["preview"] = new_title
    new_row["step_count"] = final_step_count
    new_row["last_modified_time"] = now_iso
    new_row["status"] = "CASCADE_RUN_STATUS_IDLE"
    new_row["not_fully_idle"] = 0
    new_row["killed"] = 0
    new_row["last_user_input_step_index"] = new_last_user_idx
    new_row["raw_summary"] = new_raw_summary

    pmap = load_projects_map()
    pid_val = (src_info.get("project_id") or "").strip()
    proj_label = pmap.get(pid_val, "") if (pid_val and pid_val != "outside-of-project") else ""

    sum_conn = sqlite3.connect(sum_db_path, timeout=15.0)
    try:
        cols = list(new_row.keys())
        placeholders = ",".join("?" for _ in cols)
        col_list = ",".join(f"[{c}]" for c in cols)
        sum_conn.execute(
            f"INSERT INTO conversation_summaries ({col_list}) VALUES ({placeholders})",
            [new_row[c] for c in cols],
        )

        fts_cols = [r[1] for r in sum_conn.execute("PRAGMA table_info(conversations_fts)").fetchall()]
        if fts_cols:
            fts_col_list = ",".join(fts_cols)
            fts_qmarks = ",".join("?" for _ in fts_cols)
            src_fts_rows = sum_conn.execute(
                "SELECT * FROM conversations_fts WHERE conversation_id = ?", (old_cid,)
            ).fetchall()

            inserted_meta = False
            inserted_token = False
            for frow in src_fts_rows:
                fd = dict(zip(fts_cols, frow))
                cidx = int(fd.get("chunk_index", 0))
                if cidx >= 0 and int(fd.get("chunk_first_step", 0)) >= cutoff_count:
                    continue
                fd["conversation_id"] = new_cid
                if cidx == -1:
                    fd["last_modified_time"] = now_ns
                    fd["step_count"] = final_step_count
                    fd["last_step_created_at"] = now_ns
                    fd["archived"] = 0
                    fd["title"] = new_title
                    inserted_meta = True
                elif not inserted_token:
                    fd["user_body"] = f"{fd.get('user_body') or ''}\n{search_token}"
                    inserted_token = True
                sum_conn.execute(
                    f"INSERT INTO conversations_fts ({fts_col_list}) VALUES ({fts_qmarks})",
                    [fd[c] for c in fts_cols],
                )

            if not inserted_meta:
                meta_fd = {
                    "conversation_id": new_cid,
                    "chunk_index": -1,
                    "chunk_first_step": 0,
                    "chunk_last_step": 0,
                    "last_modified_time": now_ns,
                    "step_count": final_step_count,
                    "last_step_created_at": now_ns,
                    "archived": 0,
                    "user_step_byte_offsets": None,
                    "agent_step_byte_offsets": None,
                    "title": new_title,
                    "workspace": proj_label,
                    "project": proj_label,
                    "user_body": "",
                    "agent_body": "",
                }
                sum_conn.execute(
                    f"INSERT INTO conversations_fts ({fts_col_list}) VALUES ({fts_qmarks})",
                    [meta_fd[c] for c in fts_cols],
                )
            if not inserted_token:
                tok_fd = {
                    "conversation_id": new_cid,
                    "chunk_index": 0,
                    "chunk_first_step": 0,
                    "chunk_last_step": max(0, final_step_count - 1),
                    "last_modified_time": 0,
                    "step_count": 0,
                    "last_step_created_at": 0,
                    "archived": 0,
                    "user_step_byte_offsets": b"[]",
                    "agent_step_byte_offsets": b"[]",
                    "title": "",
                    "workspace": "",
                    "project": "",
                    "user_body": search_token,
                    "agent_body": "",
                }
                sum_conn.execute(
                    f"INSERT INTO conversations_fts ({fts_col_list}) VALUES ({fts_qmarks})",
                    [tok_fd[c] for c in fts_cols],
                )

        sum_conn.commit()
    finally:
        sum_conn.close()

    kept_turns = len([t for t in turns if t["start_idx"] < cutoff_count])
    return {
        "source_cid": old_cid,
        "source_title": orig_title,
        "new_cid": new_cid,
        "new_tid": new_tid,
        "new_title": new_title,
        "search_token": search_token,
        "kept_turns": kept_turns,
        "total_turns": len(turns),
        "step_count": final_step_count,
        "link": f"[{new_title}](conversation://{new_cid})",
        "db_path": str(dst_conv_db),
    }


# ---------------------------------------------------------------------------
# 5. Antigravity 2.0 Studio Visual GUI (Pure Stdlib Tkinter + Win32 DWM)
# ---------------------------------------------------------------------------
def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _encode_rgb_png(w: int, h: int, rows_rgb: list[bytes]) -> bytes:
    raw = b"".join(b"\x00" + r for r in rows_rgb)

    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw, 6))
        + _chunk(b"IEND", b"")
    )


def _find_antigravity_exe() -> Path | None:
    if sys.platform != "win32":
        return None
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "antigravity" / "Antigravity.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Antigravity" / "Antigravity.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Antigravity" / "Antigravity.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Antigravity" / "Antigravity.exe",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def run_gui() -> None:
    if sys.platform == "win32":
        _attach_win32_default_desktop()
        import ctypes
        from ctypes import wintypes

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Google.Antigravity.BranchConversation"
            )
        except Exception:
            pass
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

    try:
        import tkinter as tk
        import tkinter.font as tkfont
        from tkinter import messagebox, ttk
    except ImportError:
        msg = (
            "未检测到图形界面支持库 tkinter。\n"
            "  - Ubuntu / Debian 请运行: sudo apt-get install -y python3-tk\n"
            "  - Fedora / RHEL 请运行: sudo dnf install -y python3-tkinter\n"
            "  - 你也可以直接使用命令行模式（如 --list-turns / --turn N）或在聊天框中让 AI 直接创建分支。"
        )
        print(msg, file=sys.stderr)
        if sys.platform.startswith("linux") and shutil.which("notify-send"):
            try:
                subprocess.Popen(
                    ["notify-send", "缺少 python3-tk", "请运行: sudo apt-get install -y python3-tk"]
                )
            except Exception:
                pass
        sys.exit(1)

    # Antigravity 2.0 Minimalist Studio Palette
    C_BG_APP = "#F8F9FB"
    C_BG_CARD = "#FFFFFF"
    C_BG_SUBTLE = "#F9FAFB"
    C_BG_INPUT = "#F3F4F6"
    C_BG_HOVER = "#F3F4F6"
    C_BG_SEL = "#EEF2FF"
    C_BORDER = "#E5E7EB"
    C_BORDER_HOVER = "#D1D5DB"
    C_BORDER_FOCUS = "#2563EB"
    C_ACCENT = "#2563EB"
    C_TEXT_PRI = "#111827"
    C_TEXT_SEC = "#374151"
    C_TEXT_MUTED = "#6B7280"
    C_TEXT_HINT = "#9CA3AF"
    C_TURN_SEL_FG = "#1E3A8A"
    C_BADGE_IND_BG = "#EEF2FF"
    C_BADGE_IND_FG = "#4338CA"
    C_BADGE_IND_BD = "#C7D2FE"
    C_BADGE_GRN_BG = "#ECFDF5"
    C_BADGE_GRN_FG = "#047857"
    C_BADGE_GRN_BD = "#A7F3D0"
    C_CTA_BG = "#111827"
    C_CTA_HOVER = "#27272A"
    C_CTA_ACTIVE = "#09090B"
    C_SCROLL_THUMB = "#D1D5DB"
    C_SCROLL_HOVER = "#9CA3AF"

    root = tk.Tk()
    root.withdraw()
    root.configure(bg=C_BG_APP)
    root.title("对话分支克隆 — Antigravity")

    # Determine crisp High-DPI scaling factor
    dpi_scale = 1.0
    if sys.platform == "win32":
        try:
            sys_dpi = ctypes.windll.user32.GetDpiForSystem() or 96
            dpi_scale = max(1.0, sys_dpi / 96.0)
            root.tk.call("tk", "scaling", sys_dpi / 72.0)
        except Exception:
            pass
    else:
        try:
            px_per_in = float(root.winfo_fpixels("1i"))
            dpi_scale = max(1.0, px_per_in / 96.0)
        except Exception:
            pass

    def S(px: int | float) -> int:
        return max(1, int(round(px * dpi_scale)))

    # Select clean platform UI typography
    avail_fonts = set(tkfont.families(root))
    if sys.platform == "win32":
        for cand in ("Microsoft YaHei UI", "Segoe UI Variable Display", "Segoe UI"):
            if cand in avail_fonts:
                ui_font = cand
                break
        else:
            ui_font = "Microsoft YaHei UI"
    elif sys.platform == "darwin":
        ui_font = "PingFang SC" if "PingFang SC" in avail_fonts else "Helvetica Neue"
    else:
        for cand in ("Noto Sans CJK SC", "WenQuanYi Micro Hei", "Ubuntu", "Sans"):
            if cand in avail_fonts:
                ui_font = cand
                break
        else:
            ui_font = "Sans"

    f_title = tkfont.Font(root=root, family=ui_font, size=14, weight="bold")
    f_sub = tkfont.Font(root=root, family=ui_font, size=9)
    f_card_hdr = tkfont.Font(root=root, family=ui_font, size=11, weight="bold")
    f_sec_hdr = tkfont.Font(root=root, family=ui_font, size=9, weight="bold")
    f_item = tkfont.Font(root=root, family=ui_font, size=9)
    f_item_bold = tkfont.Font(root=root, family=ui_font, size=9, weight="bold")
    f_small = tkfont.Font(root=root, family=ui_font, size=8)
    f_small_bold = tkfont.Font(root=root, family=ui_font, size=8, weight="bold")
    f_cta = tkfont.Font(root=root, family=ui_font, size=10, weight="bold")

    def ellipsize(text: str, font_obj: tkfont.Font, max_px: int) -> str:
        if max_px <= 24 or not text or font_obj.measure(text) <= max_px:
            return text
        lo, hi = 0, len(text)
        best = "…"
        while lo <= hi:
            mid = (lo + hi) // 2
            cand = text[:mid].rstrip() + "…"
            if font_obj.measure(cand) <= max_px:
                best = cand
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    # Analytical SDF Anti-Aliased 9-Slice Corner Cache (Pure Stdlib PNG)
    aa_cache: dict[
        tuple[int, str, str, str, int],
        tuple[tk.PhotoImage, tk.PhotoImage, tk.PhotoImage, tk.PhotoImage],
    ] = {}
    setattr(root, "_aa_corner_cache", aa_cache)

    def get_aa_corners(
        r: int, fill_hex: str, border_hex: str, bg_hex: str, border_px: int = 1
    ) -> tuple[tk.PhotoImage, tk.PhotoImage, tk.PhotoImage, tk.PhotoImage]:
        key = (r, fill_hex, border_hex, bg_hex, border_px)
        cached = aa_cache.get(key)
        if cached is not None:
            return cached

        fr, fg, fb = _hex_to_rgb(fill_hex)
        br, bg_c, bb = _hex_to_rgb(bg_hex)
        has_bd = bool(border_hex and border_px > 0)
        bdr, bdg, bdb = _hex_to_rgb(border_hex) if has_bd else (fr, fg, fb)
        bw = float(border_px) if has_bd else 0.0
        rf = float(r)

        def _make_corner(cx: float, cy: float) -> tk.PhotoImage:
            rows: list[bytes] = []
            for iy in range(r):
                py = iy + 0.5
                dy2 = (py - cy) * (py - cy)
                row = bytearray(r * 3)
                pos = 0
                for ix in range(r):
                    px = ix + 0.5
                    dist = math.sqrt((px - cx) * (px - cx) + dy2) - rf
                    a_out = min(1.0, max(0.0, 0.5 - dist))
                    if has_bd:
                        a_in = min(1.0, max(0.0, 0.5 - (dist + bw)))
                        a_bd = a_out - a_in
                        cr = br * (1.0 - a_out) + bdr * a_bd + fr * a_in
                        cg = bg_c * (1.0 - a_out) + bdg * a_bd + fg * a_in
                        cb = bb * (1.0 - a_out) + bdb * a_bd + fb * a_in
                    else:
                        cr = br * (1.0 - a_out) + fr * a_out
                        cg = bg_c * (1.0 - a_out) + fg * a_out
                        cb = bb * (1.0 - a_out) + fb * a_out
                    row[pos] = int(cr + 0.5)
                    row[pos + 1] = int(cg + 0.5)
                    row[pos + 2] = int(cb + 0.5)
                    pos += 3
                rows.append(bytes(row))
            return tk.PhotoImage(master=root, data=_encode_rgb_png(r, r, rows))

        quad = (
            _make_corner(rf, rf),      # top-left
            _make_corner(0.0, rf),     # top-right
            _make_corner(rf, 0.0),     # bottom-left
            _make_corner(0.0, 0.0),    # bottom-right
        )
        aa_cache[key] = quad
        return quad

    def draw_aa_box(
        cv: tk.Canvas,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        radius: int,
        *,
        fill: str,
        border: str = "",
        bg: str = C_BG_CARD,
        border_px: int = 1,
        tags: str | tuple[str, ...] = (),
    ) -> None:
        w = x2 - x1
        h = y2 - y1
        if w <= 2 or h <= 2:
            return
        r = max(2, min(int(radius), w // 2, h // 2))
        bw = border_px if border else 0
        tl, tr, bl, br = get_aa_corners(r, fill, border, bg, bw)

        cv.create_image(x1, y1, image=tl, anchor="nw", tags=tags)
        cv.create_image(x2 - r, y1, image=tr, anchor="nw", tags=tags)
        cv.create_image(x1, y2 - r, image=bl, anchor="nw", tags=tags)
        cv.create_image(x2 - r, y2 - r, image=br, anchor="nw", tags=tags)

        if x2 - r > x1 + r:
            if bw > 0:
                cv.create_rectangle(x1 + r, y1, x2 - r, y1 + bw, fill=border, outline="", tags=tags)
                cv.create_rectangle(x1 + r, y2 - bw, x2 - r, y2, fill=border, outline="", tags=tags)
                if y2 - bw > y1 + bw:
                    cv.create_rectangle(
                        x1 + r, y1 + bw, x2 - r, y2 - bw, fill=fill, outline="", tags=tags
                    )
            else:
                cv.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="", tags=tags)

        if y2 - r > y1 + r:
            if bw > 0:
                cv.create_rectangle(x1, y1 + r, x1 + bw, y2 - r, fill=border, outline="", tags=tags)
                cv.create_rectangle(x2 - bw, y1 + r, x2, y2 - r, fill=border, outline="", tags=tags)
                if r > bw:
                    cv.create_rectangle(
                        x1 + bw, y1 + r, x1 + r, y2 - r, fill=fill, outline="", tags=tags
                    )
                    cv.create_rectangle(
                        x2 - r, y1 + r, x2 - bw, y2 - r, fill=fill, outline="", tags=tags
                    )
            else:
                cv.create_rectangle(x1, y1 + r, x1 + r, y2 - r, fill=fill, outline="", tags=tags)
                cv.create_rectangle(x2 - r, y1 + r, x2, y2 - r, fill=fill, outline="", tags=tags)

    # Analytical SDF Anti-Aliased Vector Icons (Search Magnifier & Header Branch Badge)
    icon_cache: dict[tuple, tk.PhotoImage] = {}
    setattr(root, "_aa_icon_cache", icon_cache)

    def _seg_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
        vx, vy = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        c1 = vx * wx + vy * wy
        if c1 <= 0.0:
            return math.hypot(px - ax, py - ay)
        c2 = vx * vx + vy * vy
        if c2 <= c1:
            return math.hypot(px - bx, py - by)
        t = c1 / c2
        return math.hypot(px - (ax + t * vx), py - (ay + t * vy))

    def get_search_icon(focused: bool, bg_hex: str) -> tk.PhotoImage:
        sz = S(16)
        fg_hex = C_ACCENT if focused else C_TEXT_MUTED
        key = ("search", sz, fg_hex, bg_hex)
        if key in icon_cache:
            return icon_cache[key]
        fr, fg_c, fb = _hex_to_rgb(fg_hex)
        br, bg_c, bb = _hex_to_rgb(bg_hex)
        cx, cy, rad = sz * 0.42, sz * 0.42, sz * 0.27
        stroke = max(1.35, 1.45 * dpi_scale)
        half_s = stroke * 0.5
        hx0, hy0 = cx + rad * 0.72, cy + rad * 0.72
        hx1, hy1 = sz * 0.84, sz * 0.84
        rows: list[bytes] = []
        for iy in range(sz):
            py = iy + 0.5
            row = bytearray(sz * 3)
            pos = 0
            for ix in range(sz):
                px = ix + 0.5
                d_ring = abs(math.hypot(px - cx, py - cy) - rad) - half_s
                d_hand = _seg_dist(px, py, hx0, hy0, hx1, hy1) - half_s
                d = min(d_ring, d_hand)
                a = min(1.0, max(0.0, 0.5 - d))
                row[pos] = int(br * (1.0 - a) + fr * a + 0.5)
                row[pos + 1] = int(bg_c * (1.0 - a) + fg_c * a + 0.5)
                row[pos + 2] = int(bb * (1.0 - a) + fb * a + 0.5)
                pos += 3
            rows.append(bytes(row))
        img = tk.PhotoImage(master=root, data=_encode_rgb_png(sz, sz, rows))
        icon_cache[key] = img
        return img

    def make_branch_badge_img() -> tk.PhotoImage:
        sz = S(38)
        key = ("branch_badge", sz)
        if key in icon_cache:
            return icon_cache[key]
        br, bg_c, bb = _hex_to_rgb(C_BG_APP)
        cr_bg, cg_bg, cb_bg = _hex_to_rgb(C_CTA_BG)
        rad_box = float(S(10))
        half_sz = sz * 0.5
        bx_in = half_sz - rad_box

        # Crisp Git-branch vector coordinates in [0, sz]
        x_left = sz * 0.36
        x_right = sz * 0.65
        y_top = sz * 0.28
        y_mid = sz * 0.54
        y_bot = sz * 0.73
        y_rtop = sz * 0.33
        node_r = sz * 0.078
        ring_w = max(1.5, 1.65 * dpi_scale)
        stem_r = max(0.85, 0.92 * dpi_scale)

        rows: list[bytes] = []
        for iy in range(sz):
            py = iy + 0.5
            dy_b = max(abs(py - half_sz) - bx_in, 0.0)
            row = bytearray(sz * 3)
            pos = 0
            for ix in range(sz):
                px = ix + 0.5
                dx_b = max(abs(px - half_sz) - bx_in, 0.0)
                d_box = math.hypot(dx_b, dy_b) - rad_box
                a_box = min(1.0, max(0.0, 0.5 - d_box))
                if a_box <= 0.0:
                    row[pos], row[pos + 1], row[pos + 2] = br, bg_c, bb
                    pos += 3
                    continue

                # Branch stems (clipped cleanly outside node interiors)
                d_s1 = _seg_dist(px, py, x_left, y_top + node_r, x_left, y_bot - node_r) - stem_r
                d_s2 = _seg_dist(px, py, x_left, y_mid, x_right - node_r * 0.55, y_rtop + node_r * 0.65) - stem_r
                # Three hollow circular nodes
                dn1 = abs(math.hypot(px - x_left, py - y_top) - node_r) - ring_w * 0.5
                dn2 = abs(math.hypot(px - x_left, py - y_bot) - node_r) - ring_w * 0.5
                dn3 = abs(math.hypot(px - x_right, py - y_rtop) - node_r) - ring_w * 0.5
                # Mask stem inside node centers so nodes remain crisp hollow rings
                in_hole = min(
                    math.hypot(px - x_left, py - y_top),
                    math.hypot(px - x_left, py - y_bot),
                    math.hypot(px - x_right, py - y_rtop),
                ) < (node_r - ring_w * 0.35)
                d_glyph = min(dn1, dn2, dn3) if in_hole else min(d_s1, d_s2, dn1, dn2, dn3)
                a_fg = min(1.0, max(0.0, 0.5 - d_glyph))

                ir_c = cr_bg * (1.0 - a_fg) + 255.0 * a_fg
                ig_c = cg_bg * (1.0 - a_fg) + 255.0 * a_fg
                ib_c = cb_bg * (1.0 - a_fg) + 255.0 * a_fg

                row[pos] = int(br * (1.0 - a_box) + ir_c * a_box + 0.5)
                row[pos + 1] = int(bg_c * (1.0 - a_box) + ig_c * a_box + 0.5)
                row[pos + 2] = int(bb * (1.0 - a_box) + ib_c * a_box + 0.5)
                pos += 3
            rows.append(bytes(row))
        img = tk.PhotoImage(master=root, data=_encode_rgb_png(sz, sz, rows))
        icon_cache[key] = img
        return img

    # ---- Reusable Sleek Thin Pill Scrollbar (Zero Win98 Arrow Buttons) ----
    class ModernScrollbar(tk.Canvas):
        def __init__(self, parent: tk.Widget, command, *, track_bg: str = C_BG_CARD) -> None:
            super().__init__(
                parent,
                width=S(10),
                bg=track_bg,
                bd=0,
                highlightthickness=0,
                relief="flat",
            )
            self._command = command
            self._first = 0.0
            self._last = 1.0
            self._hovered = False
            self._dragging = False
            self._drag_offset = 0.0

            self.bind("<Configure>", lambda _e: self._redraw())
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
            self.bind("<ButtonPress-1>", self._on_press)
            self.bind("<B1-Motion>", self._on_motion)
            self.bind("<ButtonRelease-1>", self._on_release)

        def set(self, first: str | float, last: str | float) -> None:
            self._first = max(0.0, min(1.0, float(first)))
            self._last = max(0.0, min(1.0, float(last)))
            self._redraw()

        def _thumb_bounds(self) -> tuple[float, float, int] | None:
            h = self.winfo_height()
            if h <= S(16) or (self._first <= 0.001 and self._last >= 0.999):
                return None
            pad = S(3)
            usable = max(1.0, float(h - 2 * pad))
            min_len = float(min(S(28), max(S(14), h // 3)))
            span = max(min_len, (self._last - self._first) * usable)
            max_top = pad + usable - span
            denom = max(1e-6, 1.0 - (self._last - self._first))
            frac = min(1.0, max(0.0, self._first / denom))
            y0 = pad + frac * max(0.0, usable - span)
            y1 = min(float(h - pad), y0 + span)
            return y0, max(y0 + S(8), y1), h

        def _redraw(self) -> None:
            self.delete("all")
            bounds = self._thumb_bounds()
            if bounds is None:
                return
            y0, y1, _ = bounds
            w = max(S(8), self.winfo_width())
            cx = w / 2.0
            thick = max(4, S(5))
            r = thick / 2.0
            color = C_SCROLL_HOVER if (self._hovered or self._dragging) else C_SCROLL_THUMB
            self.create_line(
                cx,
                y0 + r,
                cx,
                max(y0 + r + 1.0, y1 - r),
                width=thick,
                fill=color,
                capstyle=tk.ROUND,
            )

        def _on_enter(self, _e: tk.Event) -> None:
            self._hovered = True
            self._redraw()

        def _on_leave(self, _e: tk.Event) -> None:
            self._hovered = False
            if not self._dragging:
                self._redraw()

        def _on_press(self, e: tk.Event) -> None:
            bounds = self._thumb_bounds()
            if bounds is None:
                return
            y0, y1, h = bounds
            if y0 <= e.y <= y1:
                self._dragging = True
                self._drag_offset = e.y - y0
            else:
                self._dragging = True
                self._drag_offset = (y1 - y0) / 2.0
                self._move_to_y(e.y, y1 - y0, h)
            self._redraw()

        def _move_to_y(self, pointer_y: float, span: float, h: int) -> None:
            pad = S(3)
            usable = max(1.0, float(h - 2 * pad) - span)
            frac = min(1.0, max(0.0, (pointer_y - self._drag_offset - pad) / usable))
            vis = max(0.0, self._last - self._first)
            self._command("moveto", frac * max(0.0, 1.0 - vis))

        def _on_motion(self, e: tk.Event) -> None:
            if not self._dragging:
                return
            bounds = self._thumb_bounds()
            if bounds is None:
                return
            y0, y1, h = bounds
            self._move_to_y(e.y, y1 - y0, h)

        def _on_release(self, _e: tk.Event) -> None:
            self._dragging = False
            self._redraw()

    # ---- Reusable Anti-Aliased Rounded Card Container ---------------------
    class RoundedCard(tk.Canvas):
        def __init__(
            self,
            parent: tk.Widget,
            *,
            bg_behind: str = C_BG_APP,
            card_fill: str = C_BG_CARD,
            border_color: str = C_BORDER,
            radius: int = 12,
            pad_x: int = 16,
            pad_y: int = 14,
            **kwargs,
        ) -> None:
            super().__init__(
                parent,
                bg=bg_behind,
                bd=0,
                highlightthickness=0,
                relief="flat",
                **kwargs,
            )
            self._bg_behind = bg_behind
            self._card_fill = card_fill
            self._border_color = border_color
            self._radius = S(radius)
            self._px = S(pad_x)
            self._py = S(pad_y)
            self.inner = tk.Frame(self, bg=card_fill, bd=0, highlightthickness=0)
            self._win_id = self.create_window(self._px, self._py, window=self.inner, anchor="nw")
            self.bind("<Configure>", self._on_configure)

        def _on_configure(self, e: tk.Event) -> None:
            w, h = e.width, e.height
            if w < 10 or h < 10:
                return
            self.delete("card_bg")
            draw_aa_box(
                self,
                0,
                0,
                w,
                h,
                self._radius,
                fill=self._card_fill,
                border=self._border_color,
                bg=self._bg_behind,
                border_px=1,
                tags="card_bg",
            )
            self.tag_lower("card_bg")
            self.coords(self._win_id, self._px, self._py)
            self.itemconfigure(
                self._win_id,
                width=max(1, w - 2 * self._px),
                height=max(1, h - 2 * self._py),
            )

    # ---- Reusable Anti-Aliased Stadium Pill Button ------------------------
    class PillButton(tk.Canvas):
        def __init__(
            self,
            parent: tk.Widget,
            *,
            text: str,
            command,
            width: int,
            height: int,
            bg_behind: str,
            fill_normal: str,
            fill_hover: str,
            fill_active: str,
            fg: str,
            font_obj: tkfont.Font,
            border_normal: str = "",
            border_hover: str = "",
        ) -> None:
            w_px, h_px = S(width), S(height)
            super().__init__(
                parent,
                width=w_px,
                height=h_px,
                bg=bg_behind,
                bd=0,
                highlightthickness=0,
                relief="flat",
                cursor="hand2",
            )
            self._text = text
            self._command = command
            self._bg_behind = bg_behind
            self._fill_n = fill_normal
            self._fill_h = fill_hover
            self._fill_a = fill_active
            self._fg = fg
            self._font = font_obj
            self._bd_n = border_normal
            self._bd_h = border_hover
            self._state = "normal"  # normal | hover | active | disabled

            self.bind("<Configure>", lambda _e: self._redraw())
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
            self.bind("<ButtonPress-1>", self._on_press)
            self.bind("<ButtonRelease-1>", self._on_release)

        def set_loading(self, loading: bool, text: str | None = None) -> None:
            if text is not None:
                self._text = text
            self._state = "disabled" if loading else "normal"
            self.configure(cursor="watch" if loading else "hand2")
            self._redraw()

        def _redraw(self) -> None:
            self.delete("all")
            w = self.winfo_width() or int(self["width"])
            h = self.winfo_height() or int(self["height"])
            if self._state == "disabled":
                fill = "#374151" if self._fill_n == C_CTA_BG else C_BG_HOVER
                bd = self._bd_n
            elif self._state == "active":
                fill = self._fill_a
                bd = self._bd_h or self._bd_n
            elif self._state == "hover":
                fill = self._fill_h
                bd = self._bd_h or self._bd_n
            else:
                fill = self._fill_n
                bd = self._bd_n

            draw_aa_box(
                self,
                0,
                0,
                w,
                h,
                h // 2,
                fill=fill,
                border=bd,
                bg=self._bg_behind,
                border_px=1 if bd else 0,
            )
            self.create_text(
                w // 2,
                h // 2,
                text=self._text,
                fill=self._fg,
                font=self._font,
                anchor="center",
            )

        def _on_enter(self, _e: tk.Event) -> None:
            if self._state != "disabled":
                self._state = "hover"
                self._redraw()

        def _on_leave(self, _e: tk.Event) -> None:
            if self._state != "disabled":
                self._state = "normal"
                self._redraw()

        def _on_press(self, _e: tk.Event) -> None:
            if self._state != "disabled":
                self._state = "active"
                self._redraw()

        def _on_release(self, e: tk.Event) -> None:
            if self._state == "disabled":
                return
            w, h = self.winfo_width(), self.winfo_height()
            inside = 0 <= e.x <= w and 0 <= e.y <= h
            self._state = "hover" if inside else "normal"
            self._redraw()
            if inside and callable(self._command):
                self._command()

    # ---- Reusable Anti-Aliased Pill Input (Search & New Branch Title) -----
    class PillInput(tk.Canvas):
        def __init__(
            self,
            parent: tk.Widget,
            *,
            textvariable: tk.StringVar,
            placeholder: str,
            bg_behind: str = C_BG_CARD,
            fill_idle: str = C_BG_INPUT,
            fill_focus: str = C_BG_CARD,
            height: int = 36,
            show_search_icon: bool = False,
            on_return=None,
        ) -> None:
            h_px = S(height)
            super().__init__(
                parent,
                height=h_px,
                bg=bg_behind,
                bd=0,
                highlightthickness=0,
                relief="flat",
                cursor="xterm",
            )
            self.var = textvariable
            self._placeholder = placeholder
            self._bg_behind = bg_behind
            self._fill_idle = fill_idle
            self._fill_focus = fill_focus
            self._show_search = show_search_icon
            self._focused = False
            self._clear_hover = False
            self._clear_bbox: tuple[int, int, int, int] | None = None

            self.entry = tk.Entry(
                self,
                textvariable=self.var,
                font=f_item,
                bg=fill_idle,
                fg=C_TEXT_PRI,
                insertbackground=C_TEXT_PRI,
                selectbackground="#DBEAFE",
                selectforeground=C_TURN_SEL_FG,
                bd=0,
                highlightthickness=0,
                relief="flat",
            )
            self._ph_label = tk.Label(
                self,
                text=placeholder,
                font=f_item,
                bg=fill_idle,
                fg=C_TEXT_HINT,
                bd=0,
                padx=0,
                pady=0,
                anchor="w",
                cursor="xterm",
            )
            self._win_id = self.create_window(0, 0, window=self.entry, anchor="w")
            self._ph_id = self.create_window(0, 0, window=self._ph_label, anchor="w")

            self._ph_label.bind("<Button-1>", lambda _e: self.focus_input())
            self.bind("<Button-1>", self._on_canvas_click)
            self.bind("<Motion>", self._on_canvas_motion)
            self.bind("<Leave>", self._on_canvas_leave)
            self.bind("<Configure>", lambda _e: self._redraw())
            self.entry.bind("<FocusIn>", self._on_focus_in)
            self.entry.bind("<FocusOut>", self._on_focus_out)
            self.entry.bind("<Escape>", self._on_escape)
            if on_return is not None:
                self.entry.bind("<Return>", lambda _e: on_return())

            self.var.trace_add("write", lambda *_: self._sync_state())

        def focus_input(self) -> None:
            self.entry.focus_set()

        def _on_focus_in(self, _e: tk.Event) -> None:
            self._focused = True
            self._sync_state()

        def _on_focus_out(self, _e: tk.Event) -> None:
            self._focused = False
            self._sync_state()

        def _on_escape(self, _e: tk.Event) -> None:
            if self.var.get():
                self.var.set("")
            else:
                root.focus_set()

        def _on_canvas_click(self, e: tk.Event) -> None:
            if self._clear_bbox:
                x1, y1, x2, y2 = self._clear_bbox
                if x1 <= e.x <= x2 and y1 <= e.y <= y2:
                    self.var.set("")
                    self.entry.focus_set()
                    return
            self.entry.focus_set()

        def _on_canvas_motion(self, e: tk.Event) -> None:
            was = self._clear_hover
            if self._clear_bbox:
                x1, y1, x2, y2 = self._clear_bbox
                self._clear_hover = x1 <= e.x <= x2 and y1 <= e.y <= y2
            else:
                self._clear_hover = False
            self.configure(cursor="hand2" if self._clear_hover else "xterm")
            if was != self._clear_hover:
                self._redraw()

        def _on_canvas_leave(self, _e: tk.Event) -> None:
            if self._clear_hover:
                self._clear_hover = False
                self.configure(cursor="xterm")
                self._redraw()

        def _sync_state(self) -> None:
            fill = self._fill_focus if self._focused else self._fill_idle
            self.entry.configure(bg=fill)
            self._ph_label.configure(bg=fill)
            self._redraw()

        def _redraw(self) -> None:
            w = self.winfo_width()
            h = self.winfo_height()
            if w < 30 or h < 16:
                return
            self.delete("chrome")
            fill = self._fill_focus if self._focused else self._fill_idle
            bd = C_BORDER_FOCUS if self._focused else C_BORDER
            draw_aa_box(
                self,
                0,
                0,
                w,
                h,
                h // 2,
                fill=fill,
                border=bd,
                bg=self._bg_behind,
                border_px=1,
                tags="chrome",
            )

            cy = h // 2
            left_x = S(14)
            if self._show_search:
                ic_img = get_search_icon(self._focused, fill)
                self.create_image(S(18), cy, image=ic_img, anchor="center", tags="chrome")
                left_x = S(33)

            has_text = bool(self.var.get())
            right_pad = S(32) if has_text else S(14)
            if has_text:
                cx_btn = w - S(17)
                r_btn = S(8)
                self._clear_bbox = (cx_btn - S(11), cy - S(11), cx_btn + S(11), cy + S(11))
                if self._clear_hover:
                    self.create_oval(
                        cx_btn - r_btn,
                        cy - r_btn,
                        cx_btn + r_btn,
                        cy + r_btn,
                        fill="#E5E7EB",
                        outline="",
                        tags="chrome",
                    )
                x_arm = S(3.5)
                x_col = C_TEXT_PRI if self._clear_hover else C_TEXT_MUTED
                self.create_line(
                    cx_btn - x_arm,
                    cy - x_arm,
                    cx_btn + x_arm,
                    cy + x_arm,
                    fill=x_col,
                    width=max(1, S(1.5)),
                    capstyle=tk.ROUND,
                    tags="chrome",
                )
                self.create_line(
                    cx_btn - x_arm,
                    cy + x_arm,
                    cx_btn + x_arm,
                    cy - x_arm,
                    fill=x_col,
                    width=max(1, S(1.5)),
                    capstyle=tk.ROUND,
                    tags="chrome",
                )
            else:
                self._clear_bbox = None

            self.tag_lower("chrome")
            entry_w = max(24, w - left_x - right_pad)
            self.coords(self._win_id, left_x, cy)
            self.itemconfigure(self._win_id, width=entry_w)

            show_ph = (not has_text) and (not self._focused)
            if show_ph:
                self.coords(self._ph_id, left_x, cy)
                self.itemconfigure(self._ph_id, width=entry_w, state="normal")
            else:
                self.itemconfigure(self._ph_id, state="hidden")

    # ---- Dynamic Summary Pill Badge (Right Card Header) -------------------
    class SummaryBadge(tk.Canvas):
        def __init__(self, parent: tk.Widget, *, bg_behind: str = C_BG_CARD) -> None:
            super().__init__(
                parent,
                width=S(180),
                height=S(28),
                bg=bg_behind,
                bd=0,
                highlightthickness=0,
                relief="flat",
            )
            self._bg_behind = bg_behind
            self._text = ""
            self._mode = "full"  # full | branch | empty

        def update_badge(self, text: str, mode: str) -> None:
            self._text = text
            self._mode = mode
            h = S(28)
            w = max(S(110), f_small_bold.measure(text) + S(26))
            self.configure(width=w, height=h)
            self.delete("all")
            if mode == "branch":
                fill, fg, bd = C_BADGE_IND_BG, C_BADGE_IND_FG, C_BADGE_IND_BD
            elif mode == "full":
                fill, fg, bd = C_BADGE_GRN_BG, C_BADGE_GRN_FG, C_BADGE_GRN_BD
            else:
                fill, fg, bd = C_BG_INPUT, C_TEXT_MUTED, C_BORDER

            draw_aa_box(
                self,
                0,
                0,
                w,
                h,
                h // 2,
                fill=fill,
                border=bd,
                bg=self._bg_behind,
                border_px=1,
            )
            self.create_text(
                w // 2,
                h // 2,
                text=text,
                fill=fg,
                font=f_small_bold,
                anchor="center",
            )

    # ---- Configure Initial Window Geometry (1080x720 Centered, Min 880x580)
    win_w, win_h = S(1080), S(720)
    min_w, min_h = S(880), S(580)
    root.minsize(min_w, min_h)

    pos_x = max(0, (root.winfo_screenwidth() - win_w) // 2)
    pos_y = max(0, (root.winfo_screenheight() - win_h) // 2)
    if sys.platform == "win32":
        try:
            work_rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work_rect), 0):
                ww = work_rect.right - work_rect.left
                wh = work_rect.bottom - work_rect.top
                pos_x = work_rect.left + max(0, (ww - win_w) // 2)
                pos_y = work_rect.top + max(0, (wh - win_h) // 2)
        except Exception:
            pass
    root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")

    # Configure Flat Modern `clam` Treeview Style for Turn Timeline
    style = ttk.Style(root)
    try:
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass

    style.layout("Timeline.Treeview", [("Timeline.Treeview.treearea", {"sticky": "nswe"})])
    style.configure(
        "Timeline.Treeview",
        background=C_BG_CARD,
        fieldbackground=C_BG_CARD,
        foreground=C_TEXT_PRI,
        borderwidth=0,
        relief="flat",
        rowheight=S(36),
        font=(ui_font, 9),
    )
    style.map(
        "Timeline.Treeview",
        background=[("selected", C_BG_SEL)],
        foreground=[("selected", C_TURN_SEL_FG)],
    )
    style.configure(
        "Timeline.Treeview.Heading",
        background=C_BG_SUBTLE,
        foreground=C_TEXT_MUTED,
        borderwidth=0,
        relief="flat",
        padding=(S(10), S(8)),
        font=(ui_font, 9, "bold"),
    )
    style.map(
        "Timeline.Treeview.Heading",
        background=[("active", C_BG_HOVER), ("pressed", C_BG_HOVER)],
        foreground=[("active", C_TEXT_PRI)],
        relief=[("active", "flat"), ("pressed", "flat")],
    )

    # ---- Application State ------------------------------------------------
    all_convos_cache: list[dict] = []
    convo_by_cid: dict[str, dict] = {}
    selected_cid: str | None = None
    current_turns: list[dict] = []
    is_cloning = False

    # =======================================================================
    # ROOT LAYOUT: Top Studio Header + Two-Card Split Body
    # =======================================================================
    outer = tk.Frame(root, bg=C_BG_APP, padx=S(20), pady=S(14))
    outer.pack(fill="both", expand=True)

    # ---- 1. Top Header Bar ------------------------------------------------
    top_bar = tk.Frame(outer, bg=C_BG_APP)
    top_bar.pack(fill="x", pady=(0, S(12)))

    # Studio geometric Git-branch badge icon on left of header
    hdr_badge = tk.Canvas(
        top_bar,
        width=S(38),
        height=S(38),
        bg=C_BG_APP,
        bd=0,
        highlightthickness=0,
    )
    hdr_badge.pack(side="left", padx=(0, S(12)))
    hdr_badge.create_image(0, 0, image=make_branch_badge_img(), anchor="nw")

    hdr_titles = tk.Frame(top_bar, bg=C_BG_APP)
    hdr_titles.pack(side="left", fill="y")
    tk.Label(
        hdr_titles,
        text="对话分支克隆",
        font=f_title,
        bg=C_BG_APP,
        fg=C_TEXT_PRI,
        anchor="w",
    ).pack(anchor="w")
    tk.Label(
        hdr_titles,
        text="从任意历史轮次无损创建独立新分支，免重启秒级直达",
        font=f_sub,
        bg=C_BG_APP,
        fg=C_TEXT_MUTED,
        anchor="w",
    ).pack(anchor="w")

    hdr_right = tk.Frame(top_bar, bg=C_BG_APP)
    hdr_right.pack(side="right", anchor="center")

    total_count_var = tk.StringVar(value="")
    tk.Label(
        hdr_right,
        textvariable=total_count_var,
        font=f_small,
        bg=C_BG_APP,
        fg=C_TEXT_MUTED,
    ).pack(side="left", padx=(0, S(10)))

    # Forward placeholder for reload callback
    reload_cb_ref: list = []
    refresh_btn = PillButton(
        hdr_right,
        text="↻  刷新",
        command=lambda: reload_cb_ref[0]() if reload_cb_ref else None,
        width=92,
        height=34,
        bg_behind=C_BG_APP,
        fill_normal=C_BG_CARD,
        fill_hover=C_BG_HOVER,
        fill_active="#E5E7EB",
        fg=C_TEXT_SEC,
        font_obj=f_item_bold,
        border_normal=C_BORDER,
        border_hover=C_BORDER_HOVER,
    )
    refresh_btn.pack(side="right")

    # ---- 2. Main Split Body (Left Card | Right Card) ----------------------
    split_body = tk.Frame(outer, bg=C_BG_APP)
    split_body.pack(fill="both", expand=True)

    # =======================================================================
    # LEFT CARD: 源对话列表 (Live Search + Project-Grouped Modern Canvas List)
    # =======================================================================
    left_card = RoundedCard(
        split_body,
        bg_behind=C_BG_APP,
        card_fill=C_BG_CARD,
        border_color=C_BORDER,
        radius=12,
        pad_x=14,
        pad_y=14,
        width=S(334),
    )
    left_card.pack(side="left", fill="y", padx=(0, S(14)))
    left_card.pack_propagate(False)

    lc_hdr = tk.Frame(left_card.inner, bg=C_BG_CARD)
    lc_hdr.pack(fill="x")
    tk.Label(
        lc_hdr,
        text="源对话列表",
        font=f_card_hdr,
        bg=C_BG_CARD,
        fg=C_TEXT_PRI,
    ).pack(side="left")
    left_sub_var = tk.StringVar(value="按项目分组")
    tk.Label(
        lc_hdr,
        textvariable=left_sub_var,
        font=f_small,
        bg=C_BG_CARD,
        fg=C_TEXT_MUTED,
    ).pack(side="right")

    search_var = tk.StringVar(value="")
    search_pill = PillInput(
        left_card.inner,
        textvariable=search_var,
        placeholder="搜索项目或对话标题...",
        bg_behind=C_BG_CARD,
        fill_idle=C_BG_INPUT,
        fill_focus=C_BG_CARD,
        height=36,
        show_search_icon=True,
    )
    search_pill.pack(fill="x", pady=(S(10), S(10)))

    left_list_wrap = tk.Frame(left_card.inner, bg=C_BG_CARD)
    left_list_wrap.pack(fill="both", expand=True)

    convo_canvas = tk.Canvas(
        left_list_wrap,
        bg=C_BG_CARD,
        bd=0,
        highlightthickness=0,
        relief="flat",
        yscrollincrement=1,
    )
    left_vsb = ModernScrollbar(left_list_wrap, command=convo_canvas.yview, track_bg=C_BG_CARD)
    convo_canvas.configure(yscrollcommand=left_vsb.set)
    convo_canvas.pack(side="left", fill="both", expand=True)
    left_vsb.pack(side="right", fill="y", padx=(S(2), 0))

    # Row metadata for custom Canvas conversation list
    # Each entry: {"kind": "header"|"item", "y0": int, "y1": int, "cid": str, "title": str, "is_proj": bool, "count": int}
    convo_rows: list[dict] = []
    hovered_row_idx: int = -1

    # =======================================================================
    # RIGHT CARD: 选择分叉节点 (Header + Timeline + Full Preview + Action Bar)
    # =======================================================================
    right_card = RoundedCard(
        split_body,
        bg_behind=C_BG_APP,
        card_fill=C_BG_CARD,
        border_color=C_BORDER,
        radius=12,
        pad_x=16,
        pad_y=14,
    )
    right_card.pack(side="left", fill="both", expand=True)

    # Zone A (Top): Card Header + Dynamic Summary Badge
    rc_hdr = tk.Frame(right_card.inner, bg=C_BG_CARD)
    rc_hdr.pack(side="top", fill="x", pady=(0, S(10)))

    rc_hdr_left = tk.Frame(rc_hdr, bg=C_BG_CARD)
    rc_hdr_left.pack(side="left", fill="x", expand=True)
    tk.Label(
        rc_hdr_left,
        text="选择分叉节点",
        font=f_card_hdr,
        bg=C_BG_CARD,
        fg=C_TEXT_PRI,
        anchor="w",
    ).pack(side="left")
    tk.Label(
        rc_hdr_left,
        text="选中任一轮次即可保留至该轮结束，其后聊天自动忽略",
        font=f_small,
        bg=C_BG_CARD,
        fg=C_TEXT_MUTED,
        anchor="w",
    ).pack(side="left", padx=(S(10), 0))

    summary_badge = SummaryBadge(rc_hdr, bg_behind=C_BG_CARD)
    summary_badge.pack(side="right")

    # Zone D (Packed Bottom First so it NEVER clips on small window heights!)
    bot_divider = tk.Frame(right_card.inner, bg=C_BG_HOVER, height=1)
    bot_action = tk.Frame(right_card.inner, bg=C_BG_CARD)
    bot_action.pack(side="bottom", fill="x", pady=(S(10), 0))
    bot_divider.pack(side="bottom", fill="x", pady=(S(12), 0))

    bot_left = tk.Frame(bot_action, bg=C_BG_CARD)
    bot_left.pack(side="left", fill="x", expand=True, padx=(0, S(16)))

    title_row = tk.Frame(bot_left, bg=C_BG_CARD)
    title_row.pack(fill="x")
    tk.Label(
        title_row,
        text="新分支标题",
        font=f_sec_hdr,
        bg=C_BG_CARD,
        fg=C_TEXT_SEC,
    ).pack(side="left", padx=(0, S(10)))

    title_var = tk.StringVar(value="")
    do_branch_ref: list = []
    title_pill = PillInput(
        title_row,
        textvariable=title_var,
        placeholder="输入自定义标题（留空则自动命名）...",
        bg_behind=C_BG_CARD,
        fill_idle=C_BG_SUBTLE,
        fill_focus=C_BG_CARD,
        height=40,
        show_search_icon=False,
        on_return=lambda: do_branch_ref[0]() if do_branch_ref else None,
    )
    title_pill.pack(side="left", fill="x", expand=True)

    auto_hint_var = tk.StringVar(value="留空自动命名：—")
    auto_hint_lbl = tk.Label(
        bot_left,
        textvariable=auto_hint_var,
        font=f_small,
        bg=C_BG_CARD,
        fg=C_TEXT_MUTED,
        anchor="w",
    )
    auto_hint_lbl.pack(fill="x", pady=(S(4), 0))

    cta_btn = PillButton(
        bot_action,
        text="立即创建并打开新对话  →",
        command=lambda: do_branch_ref[0]() if do_branch_ref else None,
        width=224,
        height=40,
        bg_behind=C_BG_CARD,
        fill_normal=C_CTA_BG,
        fill_hover=C_CTA_HOVER,
        fill_active=C_CTA_ACTIVE,
        fg="#FFFFFF",
        font_obj=f_cta,
    )
    cta_btn.pack(side="right", anchor="n")

    # Zone C (Packed above Bottom Action Bar): Full Message Preview Box
    preview_section = tk.Frame(right_card.inner, bg=C_BG_CARD)
    preview_section.pack(side="bottom", fill="x", pady=(S(12), 0))

    prev_hdr = tk.Frame(preview_section, bg=C_BG_CARD)
    prev_hdr.pack(fill="x", pady=(0, S(6)))
    tk.Label(
        prev_hdr,
        text="选中轮次消息完整预览",
        font=f_sec_hdr,
        bg=C_BG_CARD,
        fg=C_TEXT_SEC,
    ).pack(side="left")
    prev_meta_var = tk.StringVar(value="")
    tk.Label(
        prev_hdr,
        textvariable=prev_meta_var,
        font=f_small,
        bg=C_BG_CARD,
        fg=C_TEXT_MUTED,
    ).pack(side="right")

    preview_card = RoundedCard(
        preview_section,
        bg_behind=C_BG_CARD,
        card_fill=C_BG_SUBTLE,
        border_color=C_BORDER,
        radius=10,
        pad_x=10,
        pad_y=8,
        height=S(126),
    )
    preview_card.pack(fill="x")
    preview_card.pack_propagate(False)

    preview_text = tk.Text(
        preview_card.inner,
        bg=C_BG_SUBTLE,
        fg=C_TEXT_PRI,
        font=f_item,
        wrap="word",
        bd=0,
        highlightthickness=0,
        relief="flat",
        spacing1=3,
        spacing2=2,
        spacing3=3,
        selectbackground="#DBEAFE",
        selectforeground=C_TURN_SEL_FG,
        inactiveselectbackground="#DBEAFE",
        cursor="xterm",
        state="disabled",
    )
    prev_vsb = ModernScrollbar(preview_card.inner, command=preview_text.yview, track_bg=C_BG_SUBTLE)
    preview_text.configure(yscrollcommand=prev_vsb.set)
    preview_text.pack(side="left", fill="both", expand=True)
    prev_vsb.pack(side="right", fill="y", padx=(S(4), 0))

    # Zone B (Middle Expandable): Flat Modern Turn Timeline Table
    timeline_wrap = tk.Frame(
        right_card.inner,
        bg=C_BG_CARD,
        highlightbackground=C_BORDER,
        highlightcolor=C_BORDER,
        highlightthickness=1,
        bd=0,
    )
    timeline_wrap.pack(side="top", fill="both", expand=True)

    cols = ("turn", "time", "steps", "preview")
    turn_tree = ttk.Treeview(
        timeline_wrap,
        style="Timeline.Treeview",
        columns=cols,
        show="headings",
        selectmode="browse",
    )
    turn_tree.heading("turn", text="轮次", anchor="w")
    turn_tree.heading("time", text="时间", anchor="center")
    turn_tree.heading("steps", text="步骤", anchor="center")
    turn_tree.heading("preview", text="发送内容摘要", anchor="w")

    turn_tree.column("turn", width=S(124), minwidth=S(100), anchor="w", stretch=False)
    turn_tree.column("time", width=S(104), minwidth=S(88), anchor="center", stretch=False)
    turn_tree.column("steps", width=S(88), minwidth=S(72), anchor="center", stretch=False)
    turn_tree.column("preview", width=S(350), minwidth=S(180), anchor="w", stretch=True)

    turn_tree.tag_configure("hover_row", background=C_BG_SUBTLE)
    turn_tree.tag_configure("latest_row", font=(ui_font, 9, "bold"))
    turn_tree.tag_configure("running_row", foreground=C_TEXT_MUTED)

    right_vsb = ModernScrollbar(timeline_wrap, command=turn_tree.yview, track_bg=C_BG_CARD)
    turn_tree.configure(yscrollcommand=right_vsb.set)
    turn_tree.pack(side="left", fill="both", expand=True, padx=(S(1), 0), pady=S(1))
    right_vsb.pack(side="right", fill="y", padx=(S(2), S(2)), pady=S(2))

    hovered_tree_iid: str = ""

    def _on_tree_motion(e: tk.Event) -> None:
        nonlocal hovered_tree_iid
        iid = turn_tree.identify_row(e.y)
        if iid == hovered_tree_iid:
            return
        if hovered_tree_iid and turn_tree.exists(hovered_tree_iid):
            cur_tags = [t for t in turn_tree.item(hovered_tree_iid, "tags") if t != "hover_row"]
            turn_tree.item(hovered_tree_iid, tags=tuple(cur_tags))
        hovered_tree_iid = iid
        if iid and iid not in turn_tree.selection():
            cur_tags = list(turn_tree.item(iid, "tags"))
            if "hover_row" not in cur_tags:
                cur_tags.append("hover_row")
            turn_tree.item(iid, tags=tuple(cur_tags))
        turn_tree.configure(cursor="hand2" if iid else "")

    def _on_tree_leave(_e: tk.Event) -> None:
        nonlocal hovered_tree_iid
        if hovered_tree_iid and turn_tree.exists(hovered_tree_iid):
            cur_tags = [t for t in turn_tree.item(hovered_tree_iid, "tags") if t != "hover_row"]
            turn_tree.item(hovered_tree_iid, tags=tuple(cur_tags))
        hovered_tree_iid = ""
        turn_tree.configure(cursor="")

    turn_tree.bind("<Motion>", _on_tree_motion)
    turn_tree.bind("<Leave>", _on_tree_leave)

    # =======================================================================
    # Interactive Synchronization Logic (Preview, Summary Badge, Auto Title)
    # =======================================================================
    raw_auto_hint_text = "留空自动命名：—"

    def _refresh_hint_ellipsis() -> None:
        avail_w = max(S(160), bot_left.winfo_width() - S(8))
        auto_hint_var.set(ellipsize(raw_auto_hint_text, f_small, avail_w))

    bot_left.bind("<Configure>", lambda _e: _refresh_hint_ellipsis())

    def _set_preview_content(content: str) -> None:
        preview_text.configure(state="normal")
        preview_text.delete("1.0", "end")
        preview_text.insert("1.0", content)
        preview_text.yview_moveto(0.0)
        preview_text.configure(state="disabled")

    def _update_turn_details() -> None:
        nonlocal raw_auto_hint_text
        c = convo_by_cid.get(selected_cid or "")
        orig_title = (c.get("title") if c else "") or "Untitled"
        total = len(current_turns)
        sel = turn_tree.selection()

        if not c or total == 0 or not sel:
            summary_badge.update_badge("暂无可分叉轮次", "empty")
            prev_meta_var.set("")
            _set_preview_content("当前对话暂无可预览的用户消息记录。")
            raw_auto_hint_text = f"留空自动命名：{orig_title} [分支]"
            _refresh_hint_ellipsis()
            return

        sel_idx = int(sel[0])
        if sel_idx < 0 or sel_idx >= total:
            return
        t = current_turns[sel_idx]
        turn_no = t["turn"]
        ignored = max(0, total - turn_no)

        if ignored == 0:
            summary_badge.update_badge(f"完整克隆全部 {total} 轮", "full")
            suffix_tag = "分支"
        else:
            summary_badge.update_badge(f"保留第 1 ~ {turn_no} 轮 · 忽略后续 {ignored} 轮", "branch")
            suffix_tag = f"分支 1..{turn_no}轮"

        full_msg = t.get("full_text") or t.get("preview") or ""
        time_part = f" · {t['created_at']}" if t.get("created_at") else ""
        prev_meta_var.set(
            f"第 {turn_no} 轮{time_part} · 步骤 0..{t['end_idx']} · 共 {len(full_msg)} 字"
        )
        _set_preview_content(full_msg)

        user_custom = title_var.get().strip()
        if user_custom:
            raw_auto_hint_text = f"将使用自定义标题：{user_custom}"
        else:
            raw_auto_hint_text = f"留空自动命名：{orig_title} [{suffix_tag}]"
        _refresh_hint_ellipsis()

    title_var.trace_add("write", lambda *_: _update_turn_details())
    turn_tree.bind("<<TreeviewSelect>>", lambda _e: _update_turn_details())
    turn_tree.bind("<Double-1>", lambda _e: preview_text.focus_set())

    def _preview_col_budget() -> int:
        tw = turn_tree.winfo_width()
        if tw < S(260):
            tw = S(666)
        fixed_cols = S(124) + S(104) + S(88) + S(26)
        return max(S(140), tw - fixed_cols)

    def _refresh_turn_previews() -> None:
        if not current_turns:
            return
        budget = _preview_col_budget()
        for i, t in enumerate(current_turns):
            iid = str(i)
            if turn_tree.exists(iid):
                cur_vals = list(turn_tree.item(iid, "values"))
                if len(cur_vals) == 4:
                    f_row = f_item_bold if "latest_row" in turn_tree.item(iid, "tags") else f_item
                    cur_vals[3] = ellipsize(t["preview"], f_row, budget)
                    turn_tree.item(iid, values=tuple(cur_vals))

    turn_tree.bind("<Configure>", lambda _e: _refresh_turn_previews())

    def load_turns_for_cid(cid: str) -> None:
        nonlocal current_turns, selected_cid, hovered_tree_iid
        c = convo_by_cid.get(cid)
        if not c:
            return
        selected_cid = cid
        hovered_tree_iid = ""
        for item in turn_tree.get_children():
            turn_tree.delete(item)

        current_turns = get_conversation_turns(cid, c.get("status", ""))
        total = len(current_turns)
        default_sel_idx = total - 1
        budget = _preview_col_budget()

        for i, t in enumerate(current_turns):
            row_tags: list[str] = []
            f_row = f_item
            if not t["completed"]:
                label = f"  第 {t['turn']} 轮 · 进行中"
                row_tags.append("running_row")
                if i > 0:
                    default_sel_idx = i - 1
            elif i == total - 1 or (i == total - 2 and not current_turns[-1]["completed"]):
                label = f"  第 {t['turn']} 轮  [最新]"
                row_tags.append("latest_row")
                f_row = f_item_bold
            else:
                label = f"  第 {t['turn']} 轮"

            iid = str(i)
            turn_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    label,
                    t["created_at"] or "—",
                    f"0 .. {t['end_idx']}",
                    ellipsize(t["preview"], f_row, budget),
                ),
                tags=tuple(row_tags),
            )

        if total > 0:
            sel_iid = str(max(0, default_sel_idx))
            turn_tree.selection_set(sel_iid)
            turn_tree.focus(sel_iid)
            turn_tree.see(str(total - 1))
        _update_turn_details()

    # =======================================================================
    # Custom Left Conversation List Rendering, Search Filter & Selection
    # =======================================================================
    def render_convo_list(*, ensure_visible: bool = False) -> None:
        convo_canvas.delete("all")
        cw = convo_canvas.winfo_width()
        ch = convo_canvas.winfo_height()
        if cw < 40:
            cw = S(290)

        if not convo_rows:
            convo_canvas.create_text(
                cw // 2,
                max(S(80), ch // 2 - S(10)),
                text="未找到匹配的源对话",
                fill=C_TEXT_HINT,
                font=f_item,
                anchor="center",
            )
            convo_canvas.configure(scrollregion=(0, 0, cw, max(1, ch)))
            left_vsb.set(0.0, 1.0)
            return

        sel_y0, sel_y1 = None, None
        for idx, row in enumerate(convo_rows):
            y0, y1 = row["y0"], row["y1"]
            ymid = (y0 + y1) // 2
            if row["kind"] == "header":
                prefix = "📁 " if row["is_proj"] else "💬 "
                cnt_str = str(row["count"])
                badge_w = max(S(22), f_small_bold.measure(cnt_str) + S(12))
                badge_h = S(18)
                bx2 = cw - S(6)
                bx1 = bx2 - badge_w
                by1 = ymid - badge_h // 2
                by2 = by1 + badge_h
                draw_aa_box(
                    convo_canvas,
                    bx1,
                    by1,
                    bx2,
                    by2,
                    badge_h // 2,
                    fill=C_BG_INPUT,
                    border="",
                    bg=C_BG_CARD,
                    border_px=0,
                )
                convo_canvas.create_text(
                    (bx1 + bx2) // 2,
                    ymid,
                    text=cnt_str,
                    fill=C_TEXT_MUTED,
                    font=f_small_bold,
                    anchor="center",
                )
                hdr_max_w = max(S(60), bx1 - S(14))
                hdr_txt = ellipsize(f"{prefix}{row['title']}", f_sec_hdr, hdr_max_w)
                convo_canvas.create_text(
                    S(6),
                    ymid,
                    text=hdr_txt,
                    fill=C_TEXT_MUTED,
                    font=f_sec_hdr,
                    anchor="w",
                )
            else:
                cid = row["cid"]
                is_sel = cid == selected_cid
                is_hov = idx == hovered_row_idx and not is_sel
                rx1, rx2 = S(2), cw - S(4)
                ry1, ry2 = y0 + S(2), y1 - S(2)

                if is_sel:
                    draw_aa_box(
                        convo_canvas,
                        rx1,
                        ry1,
                        rx2,
                        ry2,
                        S(8),
                        fill=C_BG_SEL,
                        border="",
                        bg=C_BG_CARD,
                        border_px=0,
                    )
                    # Crisp 3px left accent bar inside active selection pill
                    bar_x = rx1 + S(5)
                    convo_canvas.create_line(
                        bar_x,
                        ry1 + S(7),
                        bar_x,
                        ry2 - S(7),
                        fill=C_ACCENT,
                        width=max(2, S(3)),
                        capstyle=tk.ROUND,
                    )
                    txt_font = f_item_bold
                    txt_fg = C_TEXT_PRI
                    sel_y0, sel_y1 = y0, y1
                elif is_hov:
                    draw_aa_box(
                        convo_canvas,
                        rx1,
                        ry1,
                        rx2,
                        ry2,
                        S(8),
                        fill=C_BG_HOVER,
                        border="",
                        bg=C_BG_CARD,
                        border_px=0,
                    )
                    txt_font = f_item
                    txt_fg = C_TEXT_PRI
                else:
                    txt_font = f_item
                    txt_fg = C_TEXT_SEC

                tx = rx1 + S(15)
                max_tw = max(S(60), rx2 - tx - S(10))
                t_disp = ellipsize(row["title"], txt_font, max_tw)
                convo_canvas.create_text(
                    tx,
                    ymid,
                    text=t_disp,
                    fill=txt_fg,
                    font=txt_font,
                    anchor="w",
                )

        total_h = convo_rows[-1]["y1"] + S(6)
        scroll_h = max(ch, total_h)
        convo_canvas.configure(scrollregion=(0, 0, cw, scroll_h))

        if ensure_visible and sel_y0 is not None and sel_y1 is not None and total_h > ch > 0:
            vis_top = convo_canvas.canvasy(0)
            vis_bot = vis_top + ch
            if sel_y0 < vis_top:
                convo_canvas.yview_moveto(max(0.0, (sel_y0 - S(8)) / scroll_h))
            elif sel_y1 > vis_bot:
                convo_canvas.yview_moveto(max(0.0, (sel_y1 - ch + S(8)) / scroll_h))

    def rebuild_filtered_list(*, prefer_cid: str | None = None, ensure_visible: bool = False) -> None:
        nonlocal hovered_row_idx
        hovered_row_idx = -1
        convo_rows.clear()

        q = search_var.get().strip().lower()
        if q:
            filtered = [
                c
                for c in all_convos_cache
                if q in (c.get("title") or "").lower()
                or q in (c.get("project_name") or "").lower()
            ]
            left_sub_var.set(f"匹配 {len(filtered)} 项")
        else:
            filtered = list(all_convos_cache)
            left_sub_var.set("按项目分组")

        groups = group_conversations_by_project(filtered)
        y = S(2)
        visible_cids: list[str] = []
        for g_idx, (g_name, is_proj, items) in enumerate(groups):
            if g_idx > 0:
                y += S(8)
            h_hdr = S(30)
            first_cid = items[0]["conversation_id"] if items else ""
            convo_rows.append(
                {
                    "kind": "header",
                    "y0": y,
                    "y1": y + h_hdr,
                    "cid": first_cid,
                    "title": g_name,
                    "is_proj": is_proj,
                    "count": len(items),
                }
            )
            y += h_hdr
            for c in items:
                cid = c["conversation_id"]
                visible_cids.append(cid)
                h_row = S(38)
                convo_rows.append(
                    {
                        "kind": "item",
                        "y0": y,
                        "y1": y + h_row,
                        "cid": cid,
                        "title": c.get("title") or "(无标题)",
                        "is_proj": is_proj,
                        "count": 0,
                    }
                )
                y += h_row

        target = prefer_cid or selected_cid
        if visible_cids:
            if not target or target not in visible_cids:
                target = visible_cids[0]
            if target != selected_cid or not current_turns:
                load_turns_for_cid(target)
        render_convo_list(ensure_visible=ensure_visible)

    def _row_index_at(canvas_y: float) -> int:
        for i, r in enumerate(convo_rows):
            if r["y0"] <= canvas_y < r["y1"]:
                return i
        return -1

    def _on_convo_motion(e: tk.Event) -> None:
        nonlocal hovered_row_idx
        cy = convo_canvas.canvasy(e.y)
        idx = _row_index_at(cy)
        if idx >= 0 and convo_rows[idx]["kind"] == "header":
            convo_canvas.configure(cursor="hand2" if convo_rows[idx]["cid"] else "")
            idx = -1
        else:
            convo_canvas.configure(cursor="hand2" if idx >= 0 else "")
        if idx != hovered_row_idx:
            hovered_row_idx = idx
            render_convo_list()

    def _on_convo_leave(_e: tk.Event) -> None:
        nonlocal hovered_row_idx
        if hovered_row_idx != -1:
            hovered_row_idx = -1
            convo_canvas.configure(cursor="")
            render_convo_list()

    def _on_convo_click(e: tk.Event) -> None:
        cy = convo_canvas.canvasy(e.y)
        idx = _row_index_at(cy)
        if idx < 0:
            return
        target_cid = convo_rows[idx].get("cid")
        if target_cid and target_cid != selected_cid:
            load_turns_for_cid(target_cid)
            render_convo_list(ensure_visible=True)

    convo_canvas.bind("<Configure>", lambda _e: render_convo_list())
    convo_canvas.bind("<Motion>", _on_convo_motion)
    convo_canvas.bind("<Leave>", _on_convo_leave)
    convo_canvas.bind("<ButtonRelease-1>", _on_convo_click)

    search_var.trace_add("write", lambda *_: rebuild_filtered_list(ensure_visible=True))

    # Smart hover-routed smooth scrolling across Left List, Turn Timeline, and Preview Box
    def _is_descendant(widget: tk.Widget | None, ancestor: tk.Widget) -> bool:
        cur = widget
        while cur is not None:
            if cur == ancestor:
                return True
            cur = getattr(cur, "master", None)
        return False

    def _dispatch_scroll(x_root: int, y_root: int, steps: int) -> str | None:
        target = root.winfo_containing(x_root, y_root)
        if target is None:
            return None
        if _is_descendant(target, left_card):
            first, last = convo_canvas.yview()
            if not (first <= 0.0 and last >= 1.0):
                convo_canvas.yview_scroll(steps * S(28), "units")
            return "break"
        if _is_descendant(target, preview_card):
            preview_text.yview_scroll(steps, "units")
            return "break"
        if _is_descendant(target, timeline_wrap):
            turn_tree.yview_scroll(steps, "units")
            return "break"
        return None

    def _on_mousewheel(e: tk.Event) -> str | None:
        if sys.platform == "darwin":
            steps = -1 if e.delta > 0 else 1
        else:
            steps = -int(e.delta / 120) if abs(e.delta) >= 120 else (-1 if e.delta > 0 else 1)
        return _dispatch_scroll(e.x_root, e.y_root, steps)

    root.bind_all("<MouseWheel>", _on_mousewheel)
    if sys.platform.startswith("linux"):
        root.bind_all("<Button-4>", lambda e: _dispatch_scroll(e.x_root, e.y_root, -2))
        root.bind_all("<Button-5>", lambda e: _dispatch_scroll(e.x_root, e.y_root, 2))

    # ---- Reload & Branch Actions ------------------------------------------
    def reload_conversations() -> None:
        nonlocal selected_cid
        prev_cid = selected_cid
        all_convos_cache.clear()
        convo_by_cid.clear()

        fetched = list_all_conversations()
        if not fetched:
            total_count_var.set("共 0 个对话")
            convo_rows.clear()
            render_convo_list()
            messagebox.showerror("错误", f"未在 {AGY_ROOT} 下找到任何可克隆的对话。", parent=root)
            return

        all_convos_cache.extend(fetched)
        for c in fetched:
            convo_by_cid[c["conversation_id"]] = c

        total_count_var.set(f"共 {len(fetched)} 个对话")
        target_cid = prev_cid if (prev_cid and prev_cid in convo_by_cid) else fetched[0]["conversation_id"]
        selected_cid = None
        rebuild_filtered_list(prefer_cid=target_cid, ensure_visible=True)

    reload_cb_ref.append(reload_conversations)

    def do_branch_and_open() -> None:
        nonlocal is_cloning
        if is_cloning:
            return
        if not selected_cid:
            messagebox.showwarning("提示", "请先在左侧选择要克隆的源对话。", parent=root)
            return
        sel = turn_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在右侧选择要分叉的对话轮次。", parent=root)
            return

        sel_turn = current_turns[int(sel[0])]
        custom_t = title_var.get().strip() or None

        is_cloning = True
        cta_btn.set_loading(True, "正在创建分支...")
        root.update_idletasks()
        root.update()

        try:
            res = branch_conversation(
                source_cid=selected_cid,
                custom_new_title=custom_t,
                turn_number=sel_turn["turn"],
            )
        except Exception as exc:
            is_cloning = False
            cta_btn.set_loading(False, "立即创建并打开新对话  →")
            messagebox.showerror("克隆失败", str(exc), parent=root)
            return

        root.withdraw()
        root.update()
        opened = auto_open_in_antigravity(res["search_token"])
        if not opened:
            root.deiconify()
            messagebox.showinfo(
                "分支已创建",
                f"已成功创建分支：{res['new_title']}\n\n它已实时出现在 Antigravity 左侧对话列表最上方（免重启），点击即可直接继续聊天！",
                parent=root,
            )
        root.destroy()

    do_branch_ref.append(do_branch_and_open)

    # ---- Win32 Real Antigravity Icon + Win11 DWM Rounded Light Chrome -----
    extracted_icons: list[int] = []

    def _apply_win32_studio_chrome() -> None:
        if sys.platform != "win32":
            return
        try:
            u32 = ctypes.windll.user32
            s32 = ctypes.windll.shell32
            dwm = ctypes.windll.dwmapi

            u32.GetParent.argtypes = [wintypes.HWND]
            u32.GetParent.restype = wintypes.HWND
            u32.SendMessageW.argtypes = [
                wintypes.HWND,
                wintypes.UINT,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            u32.SendMessageW.restype = wintypes.LPARAM
            dwm.DwmSetWindowAttribute.argtypes = [
                wintypes.HWND,
                wintypes.DWORD,
                wintypes.LPCVOID,
                wintypes.DWORD,
            ]
            dwm.DwmSetWindowAttribute.restype = ctypes.c_long

            top_hwnd = u32.GetParent(root.winfo_id()) or root.winfo_id()
            if not top_hwnd:
                return

            # Win11 DWM Rounded Corners + Matching #F8F9FB Caption & #111827 Title Text
            corner_pref = ctypes.c_int(2)  # DWMWCP_ROUND
            caption_col = ctypes.c_uint32(0x00FBF9F8)  # COLORREF for #F8F9FB
            text_col = ctypes.c_uint32(0x00271811)  # COLORREF for #111827
            dwm.DwmSetWindowAttribute(top_hwnd, 33, ctypes.byref(corner_pref), ctypes.sizeof(corner_pref))
            dwm.DwmSetWindowAttribute(top_hwnd, 35, ctypes.byref(caption_col), ctypes.sizeof(caption_col))
            dwm.DwmSetWindowAttribute(top_hwnd, 36, ctypes.byref(text_col), ctypes.sizeof(text_col))

            # Extract Real Antigravity Icon from Antigravity.exe
            if not extracted_icons:
                exe_path = _find_antigravity_exe()
                if exe_path is not None:
                    s32.ExtractIconExW.argtypes = [
                        wintypes.LPCWSTR,
                        ctypes.c_int,
                        ctypes.POINTER(wintypes.HICON),
                        ctypes.POINTER(wintypes.HICON),
                        wintypes.UINT,
                    ]
                    s32.ExtractIconExW.restype = wintypes.UINT
                    hbig = wintypes.HICON()
                    hsmall = wintypes.HICON()
                    cnt = s32.ExtractIconExW(
                        str(exe_path), 0, ctypes.byref(hbig), ctypes.byref(hsmall), 1
                    )
                    if cnt > 0:
                        if hsmall.value:
                            extracted_icons.append(int(hsmall.value))
                        if hbig.value:
                            extracted_icons.append(int(hbig.value))

            WM_SETICON = 0x0080
            if len(extracted_icons) >= 2:
                h_sm, h_bg = extracted_icons[0], extracted_icons[1]
            elif len(extracted_icons) == 1:
                h_sm = h_bg = extracted_icons[0]
            else:
                h_sm = h_bg = 0

            if h_sm or h_bg:
                if h_sm:
                    u32.SendMessageW(top_hwnd, WM_SETICON, 0, h_sm)
                if h_bg:
                    u32.SendMessageW(top_hwnd, WM_SETICON, 1, h_bg)
                try:
                    set_cls = getattr(u32, "SetClassLongPtrW", None)
                    if set_cls is not None:
                        set_cls.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
                        set_cls.restype = ctypes.c_ssize_t
                        if h_bg:
                            set_cls(top_hwnd, -14, h_bg)  # GCLP_HICON
                        if h_sm:
                            set_cls(top_hwnd, -34, h_sm)  # GCLP_HICONSM
                except Exception:
                    pass
        except Exception:
            pass

    # Populate initial data while hidden so first frame is 100% rendered & flicker-free
    root.update_idletasks()
    reload_conversations()

    root.deiconify()
    root.update_idletasks()
    _apply_win32_studio_chrome()
    render_convo_list(ensure_visible=True)

    root.lift()
    root.attributes("-topmost", True)

    def _finish_topmost() -> None:
        try:
            root.attributes("-topmost", False)
            _apply_win32_studio_chrome()
        except Exception:
            pass

    root.after(200, _finish_topmost)

    try:
        root.mainloop()
    finally:
        if sys.platform == "win32" and extracted_icons:
            try:
                ctypes.windll.user32.DestroyIcon.argtypes = [wintypes.HICON]
                for hico in extracted_icons:
                    ctypes.windll.user32.DestroyIcon(hico)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 6. CLI Entry Point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Branch / Fork an Antigravity conversation at any turn")
    parser.add_argument("--gui", action="store_true", help="Open visual Tkinter GUI conversation & turn selector")
    parser.add_argument("--list-turns", action="store_true", help="List all turns of the target conversation")
    parser.add_argument("--open", action="store_true", help="Automatically open the newly created branch in Antigravity")
    parser.add_argument("--id", dest="source_cid", help="Source conversation UUID")
    parser.add_argument("--title", dest="title_query", help="Match source conversation by title substring")
    parser.add_argument("--new-title", dest="custom_new_title", help="Custom title for branched conversation")
    parser.add_argument("--turn", dest="turn_number", type=int, help="Clone up to 1-based turn N (or -2 for 2nd-to-last)")
    parser.add_argument("--drop-last", dest="drop_last", type=int, help="Ignore the last K completed turns (e.g. --drop-last 1)")
    parser.add_argument("--step", dest="up_to_step", type=int, help="Clone up to raw step index")
    args = parser.parse_args()

    if args.gui:
        run_gui()
        return

    if args.list_turns:
        sum_conn = sqlite3.connect(f"file:{(AGY_ROOT / 'conversation_summaries.db').as_posix()}?mode=ro", uri=True)
        try:
            src = resolve_source_conversation(sum_conn, args.source_cid, args.title_query)
        finally:
            sum_conn.close()
        turns = get_conversation_turns(src["conversation_id"], src.get("status", ""))
        print(f"Conversation: {src['title']} ({src['conversation_id']})")
        for t in turns:
            state = "DONE" if t["completed"] else "RUNNING"
            print(f"  [Turn {t['turn']:2d}] ({state}, steps {t['start_idx']:3d}..{t['end_idx']:3d}) {t['created_at']} | {t['preview']}")
        return

    res = branch_conversation(
        source_cid=args.source_cid,
        title_query=args.title_query,
        custom_new_title=args.custom_new_title,
        turn_number=args.turn_number,
        drop_last=args.drop_last,
        up_to_step=args.up_to_step,
    )
    if args.open:
        auto_open_in_antigravity(res["search_token"])
    print("=== Conversation Branched Successfully! ===")
    for k, v in res.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
