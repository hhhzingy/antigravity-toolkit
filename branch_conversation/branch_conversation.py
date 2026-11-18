#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity Conversation Branch / Fork Tool (CLI + Tkinter GUI)
---------------------------------------------------------------
Clones any existing Antigravity conversation into a brand-new, independent
conversation UUID, supporting branching from ANY historical chat turn.

- Works across Windows and Linux (pure Python standard library).
- Groups conversations in the GUI by Project (flat, non-collapsible), with
  non-project ("outside-of-project") conversations placed at the bottom.
- Populates both `conversation_summaries` and `conversations_fts` (FTS5 index)
  so the branched conversation appears in Antigravity's sidebar and Search
  immediately without restarting!
- Clicking "立即创建并打开新对话" clones the conversation AND automatically
  opens the new branch right inside Antigravity on Windows (or places it right
  at the top of the sidebar on Linux/macOS)!
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

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


def _clean_user_request_text(raw_text: str) -> str:
    if "<USER_REQUEST>" in raw_text and "</USER_REQUEST>" in raw_text:
        raw_text = raw_text.split("<USER_REQUEST>", 1)[1].split("</USER_REQUEST>", 1)[0]
    elif "<ADDITIONAL_METADATA>" in raw_text:
        raw_text = raw_text.split("<ADDITIONAL_METADATA>", 1)[0]
    return " ".join(raw_text.strip().split())


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
        groups.append(("未归属项目对话 (Conversations)", False, outside_list))
    return groups


def get_conversation_turns(cid: str, status: str = "") -> list[dict]:
    conv_db = AGY_ROOT / "conversations" / f"{cid}.db"
    if not conv_db.exists():
        return []

    transcript_map: dict[int, tuple[str, str]] = {}
    t_path = AGY_ROOT / "brain" / cid / ".system_generated" / "logs" / "transcript.jsonl"
    if t_path.exists():
        try:
            for line in t_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if '"USER_INPUT"' in line:
                    obj = json.loads(line)
                    if obj.get("type") == "USER_INPUT":
                        sidx = int(obj.get("step_index", -1))
                        created = obj.get("created_at", "")
                        content = _clean_user_request_text(obj.get("content", ""))
                        transcript_map[sidx] = (created, content)
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

        created_at, preview = transcript_map.get(u_idx, ("", ""))
        if not preview and payload:
            candidates = _extract_strings_from_pb(payload)
            best = ""
            for c in candidates:
                if "<USER_REQUEST>" in c:
                    best = _clean_user_request_text(c)
                    break
                if len(c) > len(best):
                    best = _clean_user_request_text(c)
            preview = best

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
                "preview": (preview or "(图片/空消息)")[:120],
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
# 5. Two-Pane Visual Tkinter GUI (Left: Flat Project Tree | Right: Turns)
# ---------------------------------------------------------------------------
def run_gui() -> None:
    if sys.platform == "win32":
        _attach_win32_default_desktop()
        import ctypes

        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

    try:
        import tkinter as tk
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
                subprocess.Popen(["notify-send", "缺少 python3-tk", "请运行: sudo apt-get install -y python3-tk"])
            except Exception:
                pass
        sys.exit(1)

    if sys.platform == "win32":
        ui_font = "Microsoft YaHei UI"
    elif sys.platform == "darwin":
        ui_font = "PingFang SC"
    else:
        ui_font = "Sans"

    root = tk.Tk()
    root.title("Antigravity 对话分支克隆器 (Branch Conversation)")
    root.geometry("1120x620")
    root.minsize(900, 480)

    style = ttk.Style(root)
    try:
        if sys.platform == "win32" and "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass
    style.configure("Treeview", rowheight=28, font=(ui_font, 9))
    style.configure("Treeview.Heading", font=(ui_font, 9, "bold"))

    convo_by_cid: dict[str, dict] = {}
    header_first_cid: dict[str, str] = {}
    selected_cid: str | None = None
    current_turns: list[dict] = []

    # Main Split Container (Left Sidebar: Project-grouped Conversations | Right: Turn List)
    body = ttk.Frame(root, padding=(12, 10, 12, 6))
    body.pack(fill="both", expand=True)

    # ---- Left Pane: Flat Non-Collapsible Project -> Conversation List -----
    left_pane = ttk.Frame(body, width=300)
    left_pane.pack(side="left", fill="y", padx=(0, 12))
    left_pane.pack_propagate(False)

    left_header = ttk.Frame(left_pane)
    left_header.pack(fill="x", pady=(0, 6))
    ttk.Label(left_header, text="1. 选择源对话", font=(ui_font, 10, "bold")).pack(side="left")

    left_tree_wrap = ttk.Frame(left_pane)
    left_tree_wrap.pack(fill="both", expand=True)

    convo_tree = ttk.Treeview(
        left_tree_wrap, columns=("name",), show="", selectmode="browse"
    )
    convo_tree.column("name", width=275, anchor="w", stretch=True)
    convo_tree.tag_configure(
        "proj_header",
        font=(ui_font, 9, "bold"),
        background="#eef2f7",
        foreground="#1e293b",
    )
    convo_tree.tag_configure(
        "convo_item",
        font=(ui_font, 9),
    )

    left_vsb = ttk.Scrollbar(left_tree_wrap, orient="vertical", command=convo_tree.yview)
    convo_tree.configure(yscrollcommand=left_vsb.set)
    convo_tree.pack(side="left", fill="both", expand=True)
    left_vsb.pack(side="right", fill="y")

    # ---- Right Pane: Turn History Table -----------------------------------
    right_pane = ttk.Frame(body)
    right_pane.pack(side="left", fill="both", expand=True)

    right_header = ttk.Frame(right_pane)
    right_header.pack(fill="x", pady=(0, 6))
    right_title_var = tk.StringVar(
        value="2. 选择克隆截止到哪一轮对话结束（选中某一行 = 保留第 1 轮到该轮，自动忽略其后的聊天）："
    )
    ttk.Label(right_header, textvariable=right_title_var, font=(ui_font, 10, "bold")).pack(
        side="left"
    )

    turn_tree_wrap = ttk.Frame(right_pane)
    turn_tree_wrap.pack(fill="both", expand=True)

    cols = ("turn", "time", "steps", "preview")
    turn_tree = ttk.Treeview(turn_tree_wrap, columns=cols, show="headings", selectmode="browse")
    turn_tree.heading("turn", text="轮次")
    turn_tree.heading("time", text="时间")
    turn_tree.heading("steps", text="步骤范围")
    turn_tree.heading("preview", text="你发送的消息内容预览（含本轮 AI 完整回复）")

    turn_tree.column("turn", width=110, anchor="center", stretch=False)
    turn_tree.column("time", width=100, anchor="center", stretch=False)
    turn_tree.column("steps", width=90, anchor="center", stretch=False)
    turn_tree.column("preview", width=460, anchor="w", stretch=True)

    right_vsb = ttk.Scrollbar(turn_tree_wrap, orient="vertical", command=turn_tree.yview)
    turn_tree.configure(yscrollcommand=right_vsb.set)
    turn_tree.pack(side="left", fill="both", expand=True)
    right_vsb.pack(side="right", fill="y")

    # ---- Bottom Action Bar ------------------------------------------------
    bot = ttk.Frame(root, padding=(12, 6, 12, 12))
    bot.pack(fill="x")

    ttk.Label(bot, text="新分支标题（留空则自动命名）：", font=(ui_font, 9)).pack(side="left")
    title_var = tk.StringVar(value="")
    title_entry = ttk.Entry(bot, textvariable=title_var, font=(ui_font, 9), width=36)
    title_entry.pack(side="left", padx=(6, 14))

    def load_turns_for_cid(cid: str) -> None:
        nonlocal current_turns, selected_cid
        c = convo_by_cid.get(cid)
        if not c:
            return
        selected_cid = cid
        for item in turn_tree.get_children():
            turn_tree.delete(item)

        current_turns = get_conversation_turns(cid, c.get("status", ""))
        total = len(current_turns)
        default_sel_idx = total - 1

        for i, t in enumerate(current_turns):
            if not t["completed"]:
                label = f"第 {t['turn']} 轮 (进行中)"
                if i > 0:
                    default_sel_idx = i - 1
            elif i == total - 1 or (i == total - 2 and not current_turns[-1]["completed"]):
                label = f"第 {t['turn']} 轮 (最新)"
            else:
                label = f"第 {t['turn']} 轮"

            iid = str(i)
            turn_tree.insert(
                "",
                "end",
                iid=iid,
                values=(label, t["created_at"], f"0..{t['end_idx']}", t["preview"]),
            )

        if total > 0:
            sel_iid = str(max(0, default_sel_idx))
            turn_tree.selection_set(sel_iid)
            turn_tree.focus(sel_iid)
            turn_tree.see(str(total - 1))

    def on_convo_select(_: object = None) -> None:
        sel = convo_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid.startswith("hdr_"):
            # Clicking a project header automatically jumps to its first conversation
            target_cid = header_first_cid.get(iid) or selected_cid
            if target_cid and f"cid_{target_cid}" in convo_tree.get_children():
                convo_tree.selection_set(f"cid_{target_cid}")
                convo_tree.focus(f"cid_{target_cid}")
            return
        if iid.startswith("cid_"):
            cid = iid[4:]
            if cid != selected_cid:
                load_turns_for_cid(cid)

    def reload_conversations() -> None:
        nonlocal selected_cid
        prev_cid = selected_cid
        convo_by_cid.clear()
        header_first_cid.clear()
        for item in convo_tree.get_children():
            convo_tree.delete(item)

        all_convos = list_all_conversations()
        if not all_convos:
            messagebox.showerror("错误", f"未在 {AGY_ROOT} 下找到任何可克隆的对话。")
            return

        for c in all_convos:
            convo_by_cid[c["conversation_id"]] = c

        groups = group_conversations_by_project(all_convos)
        for g_idx, (g_name, is_proj, items) in enumerate(groups):
            hdr_iid = f"hdr_{g_idx}"
            prefix = "📁 " if is_proj else "💬 "
            convo_tree.insert(
                "",
                "end",
                iid=hdr_iid,
                values=(f" {prefix}{g_name}",),
                tags=("proj_header",),
            )
            if items:
                header_first_cid[hdr_iid] = items[0]["conversation_id"]
            for c in items:
                cid = c["conversation_id"]
                title_str = c["title"] or "(无标题)"
                convo_tree.insert(
                    "",
                    "end",
                    iid=f"cid_{cid}",
                    values=(f"      {title_str}",),
                    tags=("convo_item",),
                )

        # Default to previously selected conversation, or globally most recent conversation
        target_cid = prev_cid if (prev_cid and prev_cid in convo_by_cid) else all_convos[0]["conversation_id"]
        selected_cid = None
        target_iid = f"cid_{target_cid}"
        if target_iid in convo_tree.get_children():
            convo_tree.selection_set(target_iid)
            convo_tree.focus(target_iid)
            convo_tree.see(target_iid)
            load_turns_for_cid(target_cid)

    ttk.Button(left_header, text="刷新", command=reload_conversations, width=7).pack(side="right")
    convo_tree.bind("<<TreeviewSelect>>", on_convo_select)
    reload_conversations()

    def do_branch_and_open() -> None:
        if not selected_cid:
            messagebox.showwarning("提示", "请先在左侧选择要克隆的源对话。")
            return
        sel = turn_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在右侧选择要克隆到的对话轮次。")
            return
        sel_turn = current_turns[int(sel[0])]
        custom_t = title_var.get().strip() or None
        try:
            res = branch_conversation(
                source_cid=selected_cid,
                custom_new_title=custom_t,
                turn_number=sel_turn["turn"],
            )
        except Exception as exc:
            messagebox.showerror("克隆失败", str(exc))
            return

        root.withdraw()
        root.update()
        opened = auto_open_in_antigravity(res["search_token"])
        if not opened:
            root.deiconify()
            messagebox.showinfo(
                "分支已创建",
                f"已成功创建分支：{res['new_title']}\n\n它已实时出现在 Antigravity 左侧对话列表最上方（免重启），点击即可直接继续聊天！",
            )
        root.destroy()

    ttk.Button(bot, text="立即创建并打开新对话", command=do_branch_and_open, width=22).pack(side="right")

    root.lift()
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))
    root.mainloop()


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
