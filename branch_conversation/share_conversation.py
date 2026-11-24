#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity Conversation Share / Export / Import Tool (.agyshare + Markdown)
----------------------------------------------------------------------------
Packages any Antigravity conversation (App 2.0 / IDE / `agy` CLI) — including
optional full Swarm teams, nested Subagents, message boards, and Side Questions —
into a portable, privacy-redacted `.agyshare` archive that another Antigravity user
on Windows, macOS, or Linux can import and continue chatting from seamlessly.

Key guarantees:
- 100% read-only online SQLite backup on export (never locks or interrupts live chats).
- Protobuf-aware variable-length path rewriting (safely remaps sender home & workspace
  paths across different usernames and OSes without corrupting varint length prefixes).
- Consistent bijective UUID graph remapping across parent + Swarm workers + Subagents +
  Side Questions + board.jsonl + members.json + subagents/*.json + annotations.
- Built-in secret/token scanner & redactor on export (API keys, PATs, private keys).
- Pure Python standard library (zero external dependencies).

CLI usage:
    python share_conversation.py export --title "my-chat" -o chat.agyshare
    python share_conversation.py export --id <UUID> --turn 5 --lite -o chat.agyshare
    python share_conversation.py export --id <UUID> --format md -o handoff.md
    python share_conversation.py inspect chat.agyshare
    python share_conversation.py import chat.agyshare --workspace /path/to/repo --open
"""

from __future__ import annotations

import argparse
import base64
from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from typing import Any
from urllib.parse import quote, unquote, urlparse
import uuid
import zipfile

try:
    import branch_conversation as bc
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import branch_conversation as bc


BUNDLE_FORMAT_VERSION = 1
PH_HOME_NATIVE = "{{AGY_HOME}}"
PH_HOME_JSON = "{{AGY_HOME_JSON}}"
PH_HOME_JSON2 = "{{AGY_HOME_JSON2}}"
PH_HOME_JSON3 = "{{AGY_HOME_JSON3}}"
PH_HOME_POSIX = "{{AGY_HOME_POSIX}}"
PH_HOME_URI = "{{AGY_HOME_URI}}"
PH_WS_NATIVE = "{{AGY_WORKSPACE}}"
PH_WS_JSON = "{{AGY_WORKSPACE_JSON}}"
PH_WS_JSON2 = "{{AGY_WORKSPACE_JSON2}}"
PH_WS_JSON3 = "{{AGY_WORKSPACE_JSON3}}"
PH_WS_POSIX = "{{AGY_WORKSPACE_POSIX}}"
PH_WS_URI = "{{AGY_WORKSPACE_URI}}"

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

# Common credential / API key patterns for export-time redaction
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    ("openai_key", re.compile(r"\bsk-(?:proj-|live-|test-)?[A-Za-z0-9\-_]{24,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{24,}\b")),
    ("github_pat", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b")),
    ("github_fine_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{12,}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z0-9 ]*PRIVATE KEY-----")),
]


# ---------------------------------------------------------------------------
# 1. Protobuf-Safe Variable-Length String Rewriter (Zero Wire Corruption)
# ---------------------------------------------------------------------------
def _try_parse_pb_strict(buf: bytes) -> list[tuple[int, int, int | bytes]] | None:
    """Strictly parse `buf` as a protobuf message; return None if any wire rule fails."""
    if not buf:
        return None
    pos, end = 0, len(buf)
    fields: list[tuple[int, int, int | bytes]] = []
    try:
        while pos < end:
            # Decode tag varint (max 5 bytes for uint32)
            tag = 0
            shift = 0
            while True:
                if pos >= end or shift > 35:
                    return None
                b = buf[pos]
                pos += 1
                tag |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7
            fnum = tag >> 3
            wtype = tag & 0x07
            if fnum <= 0 or fnum > 536870911 or wtype not in (0, 1, 2, 5):
                return None
            if wtype == 0:
                val = 0
                shift = 0
                while True:
                    if pos >= end or shift > 63:
                        return None
                    b = buf[pos]
                    pos += 1
                    val |= (b & 0x7F) << shift
                    if not (b & 0x80):
                        break
                    shift += 7
                fields.append((fnum, 0, val))
            elif wtype == 1:
                if pos + 8 > end:
                    return None
                fields.append((fnum, 1, buf[pos : pos + 8]))
                pos += 8
            elif wtype == 2:
                ln = 0
                shift = 0
                while True:
                    if pos >= end or shift > 35:
                        return None
                    b = buf[pos]
                    pos += 1
                    ln |= (b & 0x7F) << shift
                    if not (b & 0x80):
                        break
                    shift += 7
                if ln < 0 or pos + ln > end:
                    return None
                fields.append((fnum, 2, buf[pos : pos + ln]))
                pos += ln
            elif wtype == 5:
                if pos + 4 > end:
                    return None
                fields.append((fnum, 5, buf[pos : pos + 4]))
                pos += 4
        return fields if fields else None
    except Exception:
        return None


def _is_clean_text_str(s: str) -> bool:
    for ch in s:
        o = ord(ch)
        if o < 32 and ch not in ("\n", "\r", "\t"):
            return False
    return True


def apply_text_replacements(
    text: str,
    exact_reps: list[tuple[str, str]],
    ci_reps: list[tuple[str, str]] | None = None,
    redact_secrets: bool = False,
) -> tuple[str, int]:
    """Apply exact + case-insensitive string replacements and optional secret redaction."""
    out = text
    redacted = 0

    for old_s, new_s in exact_reps:
        if old_s in (PH_HOME_NATIVE, PH_WS_NATIVE) and new_s.startswith("/") and old_s in out:
            out = re.sub(
                re.escape(old_s) + r"\\([^\s\"'<>|)\]}]+)",
                lambda m, r=new_s: r + "/" + m.group(1).replace("\\", "/"),
                out,
            )
        if old_s and old_s in out:
            out = out.replace(old_s, new_s)

    if ci_reps:
        for old_s, new_s in ci_reps:
            if old_s and old_s.lower() in out.lower():
                out = re.sub(re.escape(old_s), lambda _m, r=new_s: r, out, flags=re.IGNORECASE)

    if redact_secrets:
        for label, pat in _SECRET_PATTERNS:
            out, cnt = pat.subn(f"[REDACTED_{label.upper()}]", out)
            redacted += cnt

    return out, redacted


def _blob_might_match(
    blob: bytes,
    exact_needles: list[bytes],
    ci_needles: list[bytes],
    redact_secrets: bool,
) -> bool:
    for n in exact_needles:
        if n in blob:
            return True
    if ci_needles:
        bl = blob.lower()
        for n in ci_needles:
            if n in bl:
                return True
    if redact_secrets:
        for marker in (b"AIza", b"sk-", b"ghp_", b"gho_", b"ghu_", b"ghs_", b"ghr_", b"github_pat_", b"AKIA", b"xox", b"PRIVATE KEY"):
            if marker in blob:
                return True
    return False


def rewrite_pb_blob(
    blob: bytes | None,
    *,
    exact_reps: list[tuple[str, str]],
    ci_reps: list[tuple[str, str]] | None = None,
    redact_secrets: bool = False,
    _depth: int = 0,
    _exact_needles: list[bytes] | None = None,
    _ci_needles: list[bytes] | None = None,
) -> tuple[bytes | None, int]:
    """
    Recursively rewrites UTF-8 string fields inside a Protobuf binary blob while
    recomputing enclosing varint length prefixes accurately. Opaque binary fields
    (e.g., encrypted signatures or raw images) are preserved byte-for-byte.
    """
    if not blob or _depth > 16:
        return blob, 0

    if _exact_needles is None:
        _exact_needles = [o.encode("utf-8") for o, n in exact_reps if o and o != n]
    if _ci_needles is None:
        _ci_needles = [o.lower().encode("utf-8") for o, n in (ci_reps or []) if o and o.lower() != n.lower()]

    if not _blob_might_match(blob, _exact_needles, _ci_needles, redact_secrets):
        return blob, 0

    fields = _try_parse_pb_strict(blob)
    if fields is None:
        return blob, 0

    changed = False
    total_redacted = 0
    new_fields: list[tuple[int, int, int | bytes]] = []

    for fnum, wtype, val in fields:
        if wtype != 2 or not isinstance(val, bytes) or not val:
            new_fields.append((fnum, wtype, val))
            continue

        if not _blob_might_match(val, _exact_needles, _ci_needles, redact_secrets):
            new_fields.append((fnum, wtype, val))
            continue

        # Try parsing as a nested protobuf submessage first when plausible
        sub_parsed = _try_parse_pb_strict(val)
        replaced_val: bytes | None = None
        if sub_parsed is not None:
            # Guard against plain ASCII strings that coincidentally parse as protobuf
            is_likely_submsg = True
            try:
                decoded_chk = val.decode("utf-8")
                if _is_clean_text_str(decoded_chk) and (
                    "://" in decoded_chk
                    or ":\\" in decoded_chk
                    or "/" in decoded_chk
                    or " " in decoded_chk
                    or "\n" in decoded_chk
                    or decoded_chk.startswith("{")
                ):
                    is_likely_submsg = False
            except UnicodeDecodeError:
                is_likely_submsg = True

            if is_likely_submsg:
                sub_new, sub_red = rewrite_pb_blob(
                    val,
                    exact_reps=exact_reps,
                    ci_reps=ci_reps,
                    redact_secrets=redact_secrets,
                    _depth=_depth + 1,
                    _exact_needles=_exact_needles,
                    _ci_needles=_ci_needles,
                )
                if sub_new is not None and sub_new != val:
                    replaced_val = sub_new
                    total_redacted += sub_red

        if replaced_val is None:
            try:
                s = val.decode("utf-8")
            except UnicodeDecodeError:
                s = None
            if s is not None and _is_clean_text_str(s):
                ns, nred = apply_text_replacements(s, exact_reps, ci_reps, redact_secrets)
                if ns != s:
                    replaced_val = ns.encode("utf-8")
                    total_redacted += nred

        if replaced_val is not None and replaced_val != val:
            changed = True
            new_fields.append((fnum, wtype, replaced_val))
        else:
            new_fields.append((fnum, wtype, val))

    if not changed:
        return blob, 0
    return bc.serialize_pb_fields(new_fields), total_redacted


# ---------------------------------------------------------------------------
# 2. Path & URI Normalization Helpers (Cross-OS Win <-> macOS <-> Linux)
# ---------------------------------------------------------------------------
def path_to_file_uri(path_str: str) -> str:
    """Convert a native OS filesystem path to Antigravity's `file:///` URI format."""
    raw = str(path_str).strip()
    if raw.startswith("/"):
        return f"file://{quote(raw, safe='/')}"
    p = Path(raw).expanduser()
    try:
        p = p.resolve()
    except Exception:
        pass
    s = p.as_posix()
    if re.match(r"^[A-Za-z]:/", s):
        drive = s[0].lower()
        rest = quote(s[2:], safe="/")
        return f"file:///{drive}%3A{rest}"
    return f"file://{quote(s, safe='/')}"


def file_uri_to_native_candidates(uri: str) -> list[str]:
    """Return all path spellings (Windows backslash, slash, lowercase drive, URI) for a `file:///` URI."""
    out: list[str] = []
    u = uri.strip()
    if not u:
        return out
    out.append(u)
    unq = unquote(u)
    if unq != u:
        out.append(unq)

    parsed = urlparse(u)
    if parsed.scheme == "file":
        raw_p = unquote(parsed.path)
        if re.match(r"^/[A-Za-z]:/", raw_p):
            # Windows URI like file:///e%3A/LJY_V2
            win_posix = raw_p[1:]  # e:/LJY_V2
            win_back = win_posix.replace("/", "\\")  # e:\LJY_V2
            drive_up = win_posix[0].upper() + win_posix[1:]
            drive_lo = win_posix[0].lower() + win_posix[1:]
            out.extend(
                [
                    win_back,
                    win_posix,
                    drive_up,
                    drive_lo,
                    drive_up.replace("/", "\\"),
                    drive_lo.replace("/", "\\"),
                    f"file:///{win_posix[0].lower()}%3A{quote(win_posix[2:], safe='/')}",
                    f"file:///{win_posix[0].upper()}%3A{quote(win_posix[2:], safe='/')}",
                    f"file:///{win_posix[0].lower()}:{win_posix[2:]}",
                    f"file:///{win_posix[0].upper()}:{win_posix[2:]}",
                ]
            )
        elif raw_p:
            out.append(raw_p)

    # Deduplicate longest-first so more specific prefixes match before shorter ones
    seen: set[str] = set()
    uniq: list[str] = []
    for item in sorted(out, key=len, reverse=True):
        if item and item not in seen:
            seen.add(item)
            uniq.append(item)
    return uniq


def _build_export_path_replacements(
    home_dir: Path,
    workspace_uris: list[str],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Build (exact_reps, ci_reps) mapping sender home & workspace paths -> portable placeholders."""
    exact: list[tuple[str, str]] = []
    ci: list[tuple[str, str]] = []

    # 1. Workspace paths first (more specific if workspace lives inside home!)
    for uri in workspace_uris:
        for cand in file_uri_to_native_candidates(uri):
            if cand.startswith("file:///"):
                ci.append((cand, PH_WS_URI))
            elif "\\" in cand:
                # Include nested JSON-escaped backslash variants (8x, 4x, 2x) before single-backslash!
                ci.append((cand.replace("\\", "\\\\\\\\\\\\\\\\"), PH_WS_JSON3))
                ci.append((cand.replace("\\", "\\\\\\\\"), PH_WS_JSON2))
                ci.append((cand.replace("\\", "\\\\"), PH_WS_JSON))
                ci.append((cand, PH_WS_NATIVE))
            else:
                ci.append((cand, PH_WS_POSIX))

    # 2. Home directory variants (including nested JSON-escaped backslash variants)
    home_str = str(home_dir)
    home_posix = home_dir.as_posix()
    home_uri = path_to_file_uri(home_str)
    home_uri_plain = unquote(home_uri)

    for uri_cand in (home_uri, home_uri_plain):
        if uri_cand:
            ci.append((uri_cand, PH_HOME_URI))
    if "\\" in home_str:
        ci.append((home_str.replace("\\", "\\\\\\\\\\\\\\\\"), PH_HOME_JSON3))
        ci.append((home_str.replace("\\", "\\\\\\\\"), PH_HOME_JSON2))
        ci.append((home_str.replace("\\", "\\\\"), PH_HOME_JSON))
        ci.append((home_str, PH_HOME_NATIVE))
    ci.append((home_posix, PH_HOME_POSIX))

    # Deduplicate and sort longest-first so deeper escaping / more specific prefixes match first
    seen_ci: set[str] = set()
    uniq_ci: list[tuple[str, str]] = []
    for old_s, new_s in sorted(ci, key=lambda pair: len(pair[0]), reverse=True):
        k = old_s.lower()
        if old_s and k not in seen_ci:
            seen_ci.add(k)
            uniq_ci.append((old_s, new_s))
    return exact, uniq_ci


def _build_import_path_replacements(
    target_home: Path | str,
    target_workspace: Path | str | None,
) -> tuple[list[tuple[str, str]], bool]:
    """Build (exact_reps, is_posix_target) turning portable placeholders into recipient's local paths."""
    home_raw = str(target_home)
    is_posix_target = home_raw.startswith("/")
    home_native = home_raw if is_posix_target else str(Path(home_raw))
    home_posix = home_raw if is_posix_target else Path(home_raw).as_posix()
    home_json = home_native.replace("\\", "\\\\")
    home_json2 = home_native.replace("\\", "\\\\\\\\")
    home_json3 = home_native.replace("\\", "\\\\\\\\\\\\\\\\")
    home_uri = path_to_file_uri(home_native)

    if target_workspace is not None:
        ws_raw = str(target_workspace)
        ws_is_posix = ws_raw.startswith("/")
        ws_native = ws_raw if ws_is_posix else str(Path(ws_raw))
        ws_posix = ws_raw if ws_is_posix else Path(ws_raw).as_posix()
        ws_json = ws_native.replace("\\", "\\\\")
        ws_json2 = ws_native.replace("\\", "\\\\\\\\")
        ws_json3 = ws_native.replace("\\", "\\\\\\\\\\\\\\\\")
        ws_uri = path_to_file_uri(ws_native)
    else:
        ws_native = home_native
        ws_posix = home_posix
        ws_json = home_json
        ws_json2 = home_json2
        ws_json3 = home_json3
        ws_uri = home_uri

    reps = [
        (PH_WS_URI, ws_uri),
        (PH_WS_JSON3, ws_json3),
        (PH_WS_JSON2, ws_json2),
        (PH_WS_JSON, ws_json),
        (PH_WS_POSIX, ws_posix),
        (PH_WS_NATIVE, ws_native),
        (PH_HOME_URI, home_uri),
        (PH_HOME_JSON3, home_json3),
        (PH_HOME_JSON2, home_json2),
        (PH_HOME_JSON, home_json),
        (PH_HOME_POSIX, home_posix),
        (PH_HOME_NATIVE, home_native),
    ]
    return reps, is_posix_target


# ---------------------------------------------------------------------------
# 3. Conversation Tree Discovery (Parent + Swarm + Subagents + Side Questions)
# ---------------------------------------------------------------------------
def _parse_side_questions_from_pbtxt(ann_path: Path) -> tuple[list[str], dict[str, str]]:
    sq_ids: list[str] = []
    sq_titles: dict[str, str] = {}
    if not ann_path.is_file():
        return sq_ids, sq_titles
    txt = ann_path.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r'side_question_cascade_ids\s*:\s*"([0-9a-f\-]{36})"', txt, re.I):
        cid = m.group(1)
        if cid not in sq_ids:
            sq_ids.append(cid)
    for m in re.finditer(
        r'side_question_titles\s*:\s*\{\s*key\s*:\s*"([0-9a-f\-]{36})"\s+value\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}',
        txt,
        re.I,
    ):
        sq_titles[m.group(1)] = m.group(2).replace('\\"', '"').replace("\\\\", "\\")
    return sq_ids, sq_titles


def collect_conversation_tree(
    sum_conn: sqlite3.Connection,
    root_cid: str,
    agy_root: Path,
    cutoff_count: int | None = None,
) -> dict[str, Any]:
    """
    Recursively discovers the full family tree of `root_cid`:
    - Swarm workers (`brain/<cid>/.system_generated/swarm/members.json`)
    - Subagents (`brain/<cid>/.system_generated/subagents/*.json` & `parent_conversation_id`)
    - Side Questions (`conversation_parents` & `annotations/<cid>.pbtxt`)
    """
    cols = [r[1] for r in sum_conn.execute("PRAGMA table_info(conversation_summaries)").fetchall()]

    def _fetch_summary(cid: str) -> dict[str, Any] | None:
        row = sum_conn.execute(
            "SELECT * FROM conversation_summaries WHERE conversation_id = ?", (cid,)
        ).fetchone()
        return dict(zip(cols, row)) if row else None

    parent_edges: list[tuple[str, str]] = []  # (child_cid, parent_cid) in conversation_parents
    visited: set[str] = {root_cid}
    queue: deque[tuple[str, int]] = deque([(root_cid, 0)])
    child_records: dict[str, dict[str, Any]] = {}
    side_question_ids: set[str] = set()
    swarm_member_ids: set[str] = set()

    while queue:
        cur_cid, depth = queue.popleft()
        discovered: list[tuple[str, str]] = []  # (cid, kind)

        # A. Direct children in conversation_summaries
        for (c,) in sum_conn.execute(
            "SELECT conversation_id FROM conversation_summaries WHERE parent_conversation_id = ?",
            (cur_cid,),
        ).fetchall():
            if c and _UUID_RE.match(c):
                discovered.append((c, "child"))

        # B. Side Questions / parent links in conversation_parents
        try:
            for (c,) in sum_conn.execute(
                "SELECT conversation_id FROM conversation_parents WHERE parent_id = ?",
                (cur_cid,),
            ).fetchall():
                if c and _UUID_RE.match(c):
                    discovered.append((c, "side_question"))
                    side_question_ids.add(c)
                    parent_edges.append((c, cur_cid))
        except Exception:
            pass

        # C. Annotations side_question_cascade_ids
        sq_list, _ = _parse_side_questions_from_pbtxt(agy_root / "annotations" / f"{cur_cid}.pbtxt")
        for c in sq_list:
            discovered.append((c, "side_question"))
            side_question_ids.add(c)

        # D. Subagent JSON descriptors (respect cutoff_count on root if truncated!)
        sg_dir = agy_root / "brain" / cur_cid / ".system_generated"
        sub_dir = sg_dir / "subagents"
        if sub_dir.is_dir():
            for jf in sorted(sub_dir.glob("*.json")):
                try:
                    sdata = json.loads(jf.read_text(encoding="utf-8", errors="ignore"))
                    scid = str(sdata.get("conversationId") or jf.stem).strip()
                    spawn_step = sdata.get("spawnStepIndex")
                    if (
                        cur_cid == root_cid
                        and cutoff_count is not None
                        and isinstance(spawn_step, int)
                        and spawn_step >= cutoff_count
                    ):
                        continue
                    if scid and _UUID_RE.match(scid):
                        discovered.append((scid, "subagent"))
                except Exception:
                    pass

        # E. Swarm members.json
        mem_file = sg_dir / "swarm" / "members.json"
        if mem_file.is_file():
            try:
                members = json.loads(mem_file.read_text(encoding="utf-8", errors="ignore")).get("members", {})
                for mname, minfo in members.items():
                    if isinstance(minfo, dict):
                        wcid = str(minfo.get("conversation_id") or "").strip()
                        if wcid and wcid != cur_cid and _UUID_RE.match(wcid):
                            swarm_member_ids.add(wcid)
                            discovered.append((wcid, "swarm_worker"))
            except Exception:
                pass

        for c, kind in discovered:
            if c in visited:
                continue
            conv_db = agy_root / "conversations" / f"{c}.db"
            if not conv_db.is_file():
                continue
            visited.add(c)
            srow = _fetch_summary(c)
            child_records[c] = {
                "conversation_id": c,
                "parent_id": cur_cid,
                "depth": depth + 1,
                "kind": "side_question" if c in side_question_ids else ("swarm_worker" if c in swarm_member_ids else kind),
                "summary": srow,
            }
            queue.append((c, depth + 1))

    # Deduplicate parent_edges preserving order
    uniq_edges = list(dict.fromkeys((c, p) for c, p in parent_edges if c in child_records))
    has_swarm = (agy_root / "brain" / root_cid / ".system_generated" / "swarm" / "swarm.json").is_file()

    return {
        "has_swarm": has_swarm,
        "children": list(child_records.values()),
        "side_question_ids": sorted(side_question_ids & set(child_records.keys())),
        "swarm_worker_ids": sorted(swarm_member_ids & set(child_records.keys())),
        "parent_edges": uniq_edges,
    }


def _rewrite_sqlite_db(
    db_path: Path,
    *,
    exact_reps: list[tuple[str, str]],
    ci_reps: list[tuple[str, str]] | None = None,
    redact_secrets: bool = False,
    cutoff_count: int | None = None,
    new_tid: str | None = None,
    new_cid: str | None = None,
) -> tuple[int, int, int]:
    """
    Rewrites UUIDs and paths safely across all tables of a conversation `.db` using
    Protobuf-aware field rewriting. Returns (final_step_count, last_user_idx, redactions).
    """
    conn = sqlite3.connect(db_path, timeout=15.0)
    total_redactions = 0
    try:
        if cutoff_count is not None:
            conn.execute("DELETE FROM steps WHERE idx >= ?", (cutoff_count,))
            for gm_idx, gm_data in conn.execute("SELECT idx, data FROM gen_metadata").fetchall():
                if gm_data and bc.gen_metadata_max_step(gm_data) >= cutoff_count:
                    conn.execute("DELETE FROM gen_metadata WHERE idx = ?", (gm_idx,))

        # Normalize any in-flight steps to completed/stopped cleanly
        conn.execute("UPDATE steps SET status = 3 WHERE status IN (1, 2)")
        conn.execute("DELETE FROM battle_mode_infos")

        if new_tid and new_cid:
            conn.execute("UPDATE trajectory_meta SET trajectory_id = ?, cascade_id = ?", (new_tid, new_cid))

        step_rows = conn.execute(
            "SELECT idx, metadata, error_details, permissions, task_details, render_info, step_payload FROM steps"
        ).fetchall()
        for idx, meta, err, perm, task_d, rend, payload in step_rows:
            cols_in = [meta, err, perm, task_d, rend, payload]
            cols_out = []
            row_changed = False
            for blob in cols_in:
                nb, nred = rewrite_pb_blob(
                    blob, exact_reps=exact_reps, ci_reps=ci_reps, redact_secrets=redact_secrets
                )
                total_redactions += nred
                if nb != blob:
                    row_changed = True
                cols_out.append(nb)
            if row_changed:
                conn.execute(
                    """UPDATE steps
                       SET metadata=?, error_details=?, permissions=?, task_details=?, render_info=?, step_payload=?
                       WHERE idx=?""",
                    (*cols_out, idx),
                )

        for tbl, pk_col in (
            ("gen_metadata", "idx"),
            ("executor_metadata", "idx"),
            ("parent_references", "idx"),
            ("trajectory_metadata_blob", "id"),
        ):
            for pk, data in conn.execute(f"SELECT [{pk_col}], data FROM [{tbl}]").fetchall():
                if not data:
                    continue
                nb, nred = rewrite_pb_blob(
                    data, exact_reps=exact_reps, ci_reps=ci_reps, redact_secrets=redact_secrets
                )
                total_redactions += nred
                if nb != data:
                    conn.execute(f"UPDATE [{tbl}] SET data=? WHERE [{pk_col}]=?", (nb, pk))

        final_step_count = conn.execute("SELECT COUNT(*) FROM steps").fetchone()[0]
        last_u = conn.execute("SELECT MAX(idx) FROM steps WHERE step_type = 14").fetchone()
        last_user_idx = int(last_u[0]) if (last_u and last_u[0] is not None) else -1

        conn.commit()
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("VACUUM")
    finally:
        conn.close()
    return final_step_count, last_user_idx, total_redactions


def _serialize_summary_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, bytes):
            out[k] = {"__b64__": base64.b64encode(v).decode("ascii")}
        else:
            out[k] = v
    return out


def _deserialize_summary_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, dict) and "__b64__" in v:
            out[k] = base64.b64decode(v["__b64__"])
        else:
            out[k] = v
    return out


def _copy_and_sanitize_brain_dir(
    src_brain: Path,
    dst_brain: Path,
    *,
    include_swarm_state: bool,
    cutoff_count: int | None,
    exact_reps: list[tuple[str, str]],
    ci_reps: list[tuple[str, str]] | None,
    redact_secrets: bool,
    uuid_map: dict[str, str] | None = None,
    target_workspace_uri: str | None = None,
    normalize_for_import: bool = False,
) -> int:
    """Copy `brain/<cid>` safely, rewriting text/JSON/JSONL paths & UUIDs."""
    if not src_brain.is_dir():
        return 0

    allowed_sys_dirs = {"logs", "swarm", "subagents", "messages"} if include_swarm_state else {"logs"}

    def _ignore(dir_path: str, names: list[str]) -> set[str]:
        p = Path(dir_path)
        if p == src_brain:
            return {n for n in names if n == "scratch"}
        if p.name == ".system_generated":
            return {n for n in names if n not in allowed_sys_dirs}
        if p.name == "logs":
            # Exclude redundant chunked mirrors of transcript.jsonl to keep .agyshare compact
            return {n for n in names if n == "chunks"}
        if p.name == "browser_sandbox":
            return {n for n in names if n != "references"}
        return set()

    shutil.copytree(src_brain, dst_brain, ignore=_ignore, dirs_exist_ok=True)
    redactions = 0

    # Rename subagents/<old_cid>.json -> subagents/<new_cid>.json when uuid_map is provided
    sub_dir = dst_brain / ".system_generated" / "subagents"
    if include_swarm_state and sub_dir.is_dir() and uuid_map:
        for jf in list(sub_dir.glob("*.json")):
            if jf.stem in uuid_map:
                new_jf = sub_dir / f"{uuid_map[jf.stem]}.json"
                if new_jf != jf:
                    jf.rename(new_jf)

    for f in list(dst_brain.rglob("*")):
        if not f.is_file():
            continue
        if f.name in ("transcript.jsonl", "transcript_full.jsonl"):
            try:
                kept: list[str] = []
                for ln in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if cutoff_count is not None:
                        try:
                            sidx = int(json.loads(ln).get("step_index", -1))
                            if sidx >= cutoff_count:
                                continue
                        except Exception:
                            pass
                    nln, nred = apply_text_replacements(ln, exact_reps, ci_reps, redact_secrets)
                    redactions += nred
                    kept.append(nln)
                f.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
            except Exception:
                pass
        elif f.suffix.lower() in (".md", ".json", ".jsonl", ".txt", ".resolved", ".pbtxt"):
            try:
                txt = f.read_text(encoding="utf-8")
                ntxt, nred = apply_text_replacements(txt, exact_reps, ci_reps, redact_secrets)
                redactions += nred

                # On import, normalize Swarm runtime states & worktree workspace_mode cleanly
                if normalize_for_import and f.name == "members.json" and f.parent.name == "swarm":
                    try:
                        mobj = json.loads(ntxt)
                        for mname, minfo in (mobj.get("members") or {}).items():
                            if not isinstance(minfo, dict):
                                continue
                            if minfo.get("workspace_mode") in ("share", "branch"):
                                minfo["workspace_mode"] = "inherit"
                            if not minfo.get("killed") and minfo.get("role") != "coordinator":
                                if minfo.get("phase") == "RUNNING":
                                    minfo["phase"] = "STOPPED"
                        ntxt = json.dumps(mobj, ensure_ascii=False, indent=2) + "\n"
                    except Exception:
                        pass
                elif normalize_for_import and f.parent.name == "subagents" and f.suffix == ".json":
                    try:
                        sobj = json.loads(ntxt)
                        if target_workspace_uri is not None:
                            sobj["workspaceUris"] = [target_workspace_uri] if target_workspace_uri else []
                        ntxt = json.dumps(sobj, ensure_ascii=False)
                    except Exception:
                        pass

                if ntxt != txt:
                    f.write_text(ntxt, encoding="utf-8")
            except Exception:
                pass

    return redactions


# ---------------------------------------------------------------------------
# 4. Export Conversation -> Portable `.agyshare` Bundle (or Handoff Markdown)
# ---------------------------------------------------------------------------
def _safe_filename(title: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]+', "_", (title or "antigravity_chat").strip())
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._")
    return (cleaned[:64] or "antigravity_chat")


def export_markdown_handoff(
    *,
    source_cid: str | None = None,
    title_query: str | None = None,
    turn_number: int | None = None,
    drop_last: int | None = None,
    output_path: Path,
    include_swarm: bool = True,
    redact_secrets: bool = True,
    agy_root: Path | None = None,
) -> dict[str, Any]:
    """Export a clean, portable Markdown context handoff document (zero-tool-required fallback)."""
    root_dir = agy_root or bc.AGY_ROOT
    sum_db = root_dir / "conversation_summaries.db"
    if not sum_db.is_file():
        raise FileNotFoundError(f"未找到对话索引数据库: {sum_db}")

    sconn = sqlite3.connect(f"file:{sum_db.as_posix()}?mode=ro", uri=True, timeout=10.0)
    try:
        src = bc.resolve_source_conversation(sconn, source_cid, title_query)
        cid = src["conversation_id"]
        title = src.get("title") or "Untitled"
    finally:
        sconn.close()

    turns = bc.get_conversation_turns(cid, src.get("status", ""))
    completed = [t for t in turns if t["completed"]] or turns
    if drop_last is not None:
        kept_turns = completed[: max(1, len(completed) - drop_last)]
    elif turn_number is not None:
        idx = (len(completed) + turn_number) if turn_number < 0 else turn_number
        kept_turns = turns[: max(1, idx)]
    else:
        kept_turns = completed
    cutoff_count = kept_turns[-1]["cutoff_count"] if kept_turns else int(src.get("step_count") or 0)

    # Read transcript_full.jsonl / transcript.jsonl for clean user + assistant dialogue
    log_dir = root_dir / "brain" / cid / ".system_generated" / "logs"
    tfile = log_dir / "transcript_full.jsonl"
    if not tfile.is_file():
        tfile = log_dir / "transcript.jsonl"

    md_lines = [
        f"# Antigravity 对话接力上下文：{title}",
        "",
        f"- **导出时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- **包含轮次**: 第 1 ~ {len(kept_turns)} 轮（共 {len(turns)} 轮）",
        "- **使用方式**: 将本文件发给其他 Antigravity 或 AI 助手并说明“请基于这份对话上下文继续推进”。",
        "",
        "---",
        "",
    ]

    redactions = 0
    _, ci_reps = _build_export_path_replacements(Path.home(), json.loads(src.get("workspace_uris") or "[]"))

    if tfile.is_file():
        turn_no = 0
        for raw_ln in tfile.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not raw_ln.strip():
                continue
            try:
                obj = json.loads(raw_ln)
            except Exception:
                continue
            sidx = int(obj.get("step_index", -1))
            if sidx >= cutoff_count:
                continue
            stype = obj.get("type")
            content = str(obj.get("content") or "").strip()
            if stype == "USER_INPUT":
                turn_no += 1
                clean_u = bc._extract_user_request_multiline(content)
                clean_u, r = apply_text_replacements(clean_u, [], ci_reps, redact_secrets)
                redactions += r
                md_lines.extend([f"## 第 {turn_no} 轮 · 用户提问", "", clean_u, ""])
            elif stype == "PLANNER_RESPONSE" and content:
                clean_a, r = apply_text_replacements(content, [], ci_reps, redact_secrets)
                redactions += r
                md_lines.extend(["### AI 回复", "", clean_a, ""])
    else:
        for t in kept_turns:
            txt, r = apply_text_replacements(t["full_text"], [], ci_reps, redact_secrets)
            redactions += r
            md_lines.extend([f"## 第 {t['turn']} 轮 · 用户提问", "", txt, ""])

    if include_swarm:
        board = root_dir / "brain" / cid / ".system_generated" / "swarm" / "board.jsonl"
        if board.is_file():
            md_lines.extend(["---", "", "## Swarm 团队共享看板记录", ""])
            for raw_ln in board.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not raw_ln.strip():
                    continue
                try:
                    bo = json.loads(raw_ln)
                except Exception:
                    continue
                agent = bo.get("agent") or "unknown"
                seq = bo.get("seq", "")
                btxt, r = apply_text_replacements(str(bo.get("text") or ""), [], ci_reps, redact_secrets)
                redactions += r
                md_lines.extend([f"### [#{seq}] `{agent}`", "", btxt, ""])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(md_lines), encoding="utf-8")
    return {
        "format": "markdown",
        "source_cid": cid,
        "title": title,
        "output_path": str(output_path),
        "kept_turns": len(kept_turns),
        "total_turns": len(turns),
        "redacted_secrets": redactions,
        "size_bytes": output_path.stat().st_size,
    }


def export_share_bundle(
    *,
    source_cid: str | None = None,
    title_query: str | None = None,
    turn_number: int | None = None,
    drop_last: int | None = None,
    output_path: Path | None = None,
    include_swarm: bool = True,
    redact_secrets: bool = True,
    agy_root: Path | None = None,
    source_home: Path | None = None,
) -> dict[str, Any]:
    """
    Exports a conversation (and optionally its entire Swarm / Subagents / Side Questions tree)
    into a self-contained, path-sanitized, secret-redacted `.agyshare` ZIP bundle.
    100% read-only against live Antigravity files — never affects running processes or chats.
    """
    root_dir = agy_root or bc.AGY_ROOT
    home_dir = source_home or Path.home()
    sum_db = root_dir / "conversation_summaries.db"
    if not sum_db.is_file():
        raise FileNotFoundError(f"未找到 Antigravity 对话索引数据库: {sum_db}")

    # 1. Read-only metadata & family tree discovery
    sconn = sqlite3.connect(f"file:{sum_db.as_posix()}?mode=ro", uri=True, timeout=15.0)
    try:
        src_info = bc.resolve_source_conversation(sconn, source_cid, title_query)
        old_root_cid = src_info["conversation_id"]
        orig_title = src_info.get("title") or "Untitled"

        turns = bc.get_conversation_turns(old_root_cid, src_info.get("status", ""))
        completed_turns = [t for t in turns if t["completed"]] or turns

        cutoff_count: int | None = None
        is_truncated = False
        if drop_last is not None:
            if drop_last < 0 or drop_last >= len(completed_turns):
                raise ValueError(f"--drop-last {drop_last} 超出范围（共 {len(completed_turns)} 轮）")
            sel = completed_turns[len(completed_turns) - 1 - drop_last]
            cutoff_count = sel["cutoff_count"]
            is_truncated = drop_last > 0
            kept_turns = sel["turn"]
        elif turn_number is not None:
            if turn_number < 0:
                pos_idx = len(completed_turns) + turn_number
                if pos_idx < 0 or pos_idx >= len(completed_turns):
                    raise ValueError(f"--turn {turn_number} 超出范围（共 {len(completed_turns)} 轮）")
                sel = completed_turns[pos_idx]
            else:
                matched = [t for t in turns if t["turn"] == turn_number]
                if not matched:
                    raise ValueError(f"未找到第 {turn_number} 轮对话（共 {len(turns)} 轮）")
                sel = matched[0]
            cutoff_count = sel["cutoff_count"]
            is_truncated = sel["turn"] < len(turns)
            kept_turns = sel["turn"]
        else:
            if completed_turns:
                cutoff_count = completed_turns[-1]["cutoff_count"]
                kept_turns = completed_turns[-1]["turn"]
            else:
                cutoff_count = int(src_info.get("step_count") or 0)
                kept_turns = 0

        tree = collect_conversation_tree(sconn, old_root_cid, root_dir, cutoff_count=cutoff_count if is_truncated else None)

        # Fetch FTS rows for root
        fts_cols = [r[1] for r in sconn.execute("PRAGMA table_info(conversations_fts)").fetchall()]
        root_fts_rows: list[dict[str, Any]] = []
        if fts_cols:
            for frow in sconn.execute(
                "SELECT * FROM conversations_fts WHERE conversation_id = ?", (old_root_cid,)
            ).fetchall():
                fd = dict(zip(fts_cols, frow))
                cidx = int(fd.get("chunk_index", 0))
                if cutoff_count is not None and cidx >= 0 and int(fd.get("chunk_first_step", 0)) >= cutoff_count:
                    continue
                root_fts_rows.append(fd)
    finally:
        sconn.close()

    try:
        ws_uris = json.loads(src_info.get("workspace_uris") or "[]")
        if not isinstance(ws_uris, list):
            ws_uris = []
    except Exception:
        ws_uris = []

    exact_path_reps, ci_path_reps = _build_export_path_replacements(home_dir, [str(u) for u in ws_uris])

    # Collect isolated dummy UUIDs when exporting in Lite mode (without children)
    lite_iso_reps: list[tuple[str, str]] = []
    if not include_swarm:
        for ch in tree["children"]:
            lite_iso_reps.append((ch["conversation_id"], str(uuid.uuid4())))

    # Also rewrite sender's project_id UUID to a neutral placeholder in Lite/Full exports
    old_proj_id = (src_info.get("project_id") or "").strip()
    proj_reps: list[tuple[str, str]] = []
    if old_proj_id and old_proj_id != "outside-of-project" and _UUID_RE.match(old_proj_id):
        proj_reps.append((old_proj_id, "outside-of-project"))

    exact_reps = [*exact_path_reps, *lite_iso_reps, *proj_reps]

    if output_path is None:
        suffix = f"_1-{kept_turns}turns" if is_truncated else ""
        output_path = Path.cwd() / f"{_safe_filename(orig_title)}{suffix}.agyshare"
    elif output_path.suffix.lower() != ".agyshare":
        output_path = output_path.with_suffix(".agyshare")

    total_redactions = 0

    with tempfile.TemporaryDirectory(prefix="agyshare_export_") as tmp_s:
        tmp_dir = Path(tmp_s)
        conv_stage = tmp_dir / "conversations"
        brain_stage = tmp_dir / "brain"
        sum_stage = tmp_dir / "summaries"
        conv_stage.mkdir(parents=True, exist_ok=True)
        brain_stage.mkdir(parents=True, exist_ok=True)
        sum_stage.mkdir(parents=True, exist_ok=True)

        # 2. Online-backup & sanitize root DB
        src_root_db = root_dir / "conversations" / f"{old_root_cid}.db"
        if not src_root_db.is_file():
            raise FileNotFoundError(f"未找到源对话数据库: {src_root_db}")
        dst_root_db = conv_stage / f"{old_root_cid}.db"
        sc = sqlite3.connect(f"file:{src_root_db.as_posix()}?mode=ro", uri=True, timeout=15.0)
        dc = sqlite3.connect(dst_root_db, timeout=15.0)
        try:
            sc.backup(dc)
        finally:
            sc.close()
            dc.close()

        root_steps, root_last_u, r_red = _rewrite_sqlite_db(
            dst_root_db,
            exact_reps=exact_reps,
            ci_reps=ci_path_reps,
            redact_secrets=redact_secrets,
            cutoff_count=cutoff_count,
        )
        total_redactions += r_red

        # Sanitize root brain/
        b_red = _copy_and_sanitize_brain_dir(
            root_dir / "brain" / old_root_cid,
            brain_stage / old_root_cid,
            include_swarm_state=include_swarm,
            cutoff_count=cutoff_count,
            exact_reps=exact_reps,
            ci_reps=ci_path_reps,
            redact_secrets=redact_secrets,
        )
        total_redactions += b_red

        # 3. Export children (Swarm workers, Subagents, Side Questions) if include_swarm=True
        exported_children: list[dict[str, Any]] = []
        annotations_map: dict[str, str] = {}

        root_ann = root_dir / "annotations" / f"{old_root_cid}.pbtxt"
        if root_ann.is_file():
            atxt, r_ann = apply_text_replacements(
                root_ann.read_text(encoding="utf-8", errors="ignore"),
                exact_reps,
                ci_path_reps,
                redact_secrets,
            )
            total_redactions += r_ann
            annotations_map[old_root_cid] = atxt

        if include_swarm:
            for ch in tree["children"]:
                ch_cid = ch["conversation_id"]
                src_ch_db = root_dir / "conversations" / f"{ch_cid}.db"
                if not src_ch_db.is_file():
                    continue
                dst_ch_db = conv_stage / f"{ch_cid}.db"
                sc = sqlite3.connect(f"file:{src_ch_db.as_posix()}?mode=ro", uri=True, timeout=15.0)
                dc = sqlite3.connect(dst_ch_db, timeout=15.0)
                try:
                    sc.backup(dc)
                finally:
                    sc.close()
                    dc.close()

                ch_steps, ch_last_u, ch_red = _rewrite_sqlite_db(
                    dst_ch_db,
                    exact_reps=exact_reps,
                    ci_reps=ci_path_reps,
                    redact_secrets=redact_secrets,
                )
                total_redactions += ch_red

                ch_b_red = _copy_and_sanitize_brain_dir(
                    root_dir / "brain" / ch_cid,
                    brain_stage / ch_cid,
                    include_swarm_state=True,
                    cutoff_count=None,
                    exact_reps=exact_reps,
                    ci_reps=ci_path_reps,
                    redact_secrets=redact_secrets,
                )
                total_redactions += ch_b_red

                ch_ann = root_dir / "annotations" / f"{ch_cid}.pbtxt"
                if ch_ann.is_file():
                    catxt, r_ca = apply_text_replacements(
                        ch_ann.read_text(encoding="utf-8", errors="ignore"),
                        exact_reps,
                        ci_path_reps,
                        redact_secrets,
                    )
                    total_redactions += r_ca
                    annotations_map[ch_cid] = catxt

                ch_sum = dict(ch["summary"]) if ch["summary"] else None
                if ch_sum is not None:
                    ch_sum["step_count"] = ch_steps
                    ch_sum["last_user_input_step_index"] = ch_last_u
                    ch_sum["status"] = "CASCADE_RUN_STATUS_IDLE"
                    ch_sum["not_fully_idle"] = 0
                    ch_sum["project_id"] = "outside-of-project"
                    ch_sum["workspace_uris"] = json.dumps([PH_WS_URI] if ws_uris else [])
                    if isinstance(ch_sum.get("raw_summary"), bytes):
                        nraw, nred = rewrite_pb_blob(
                            ch_sum["raw_summary"],
                            exact_reps=exact_reps,
                            ci_reps=ci_path_reps,
                            redact_secrets=redact_secrets,
                        )
                        total_redactions += nred
                        ch_sum["raw_summary"] = nraw or b""
                    ch_sum = _serialize_summary_row(ch_sum)

                exported_children.append(
                    {
                        "conversation_id": ch_cid,
                        "parent_id": ch["parent_id"],
                        "depth": ch["depth"],
                        "kind": ch["kind"],
                        "agent_name": (ch["summary"] or {}).get("agent_name", ""),
                        "title": (ch["summary"] or {}).get("title", ""),
                        "step_count": ch_steps,
                        "summary": ch_sum,
                    }
                )

        # 4. Sanitize root summary & FTS rows
        clean_root_sum = dict(src_info)
        clean_root_sum["step_count"] = root_steps
        clean_root_sum["last_user_input_step_index"] = root_last_u
        clean_root_sum["status"] = "CASCADE_RUN_STATUS_IDLE"
        clean_root_sum["not_fully_idle"] = 0
        clean_root_sum["killed"] = 0
        clean_root_sum["project_id"] = "outside-of-project"
        clean_root_sum["workspace_uris"] = json.dumps([PH_WS_URI] if ws_uris else [])
        for clr in ("parent_conversation_id", "battle_id", "winning_conversation_id", "group_id", "agent_name"):
            if clr in clean_root_sum:
                clean_root_sum[clr] = ""
        if "nesting_depth" in clean_root_sum:
            clean_root_sum["nesting_depth"] = 0
        if isinstance(clean_root_sum.get("raw_summary"), bytes):
            nraw, nred = rewrite_pb_blob(
                clean_root_sum["raw_summary"],
                exact_reps=exact_reps,
                ci_reps=ci_path_reps,
                redact_secrets=redact_secrets,
            )
            total_redactions += nred
            clean_root_sum["raw_summary"] = nraw or b""

        clean_fts_rows: list[dict[str, Any]] = []
        for fd in root_fts_rows:
            cfd = dict(fd)
            for k in ("title", "workspace", "project", "user_body", "agent_body"):
                if isinstance(cfd.get(k), str) and cfd[k]:
                    ntxt, nred = apply_text_replacements(cfd[k], exact_reps, ci_reps=ci_path_reps, redact_secrets=redact_secrets)
                    total_redactions += nred
                    cfd[k] = ntxt
            clean_fts_rows.append(_serialize_summary_row(cfd))

        (sum_stage / "root.json").write_text(
            json.dumps(_serialize_summary_row(clean_root_sum), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (sum_stage / "root_fts.json").write_text(
            json.dumps(clean_fts_rows, ensure_ascii=False),
            encoding="utf-8",
        )
        (sum_stage / "children.json").write_text(
            json.dumps(
                {
                    "children": exported_children,
                    "parent_edges": tree["parent_edges"] if include_swarm else [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (sum_stage / "annotations.json").write_text(
            json.dumps(annotations_map, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 5. Write manifest.json
        ws_hint_name = ""
        if ws_uris:
            cands = file_uri_to_native_candidates(str(ws_uris[0]))
            for c in cands:
                if not c.startswith("file:///"):
                    ws_hint_name = Path(c.replace("\\", "/")).name
                    break

        manifest = {
            "format": "antigravity-share-bundle",
            "version": BUNDLE_FORMAT_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "root_cid": old_root_cid,
            "title": orig_title,
            "step_count": root_steps,
            "kept_turns": kept_turns,
            "total_turns": len(turns),
            "is_truncated": is_truncated,
            "include_swarm": include_swarm,
            "has_swarm": bool(include_swarm and tree["has_swarm"]),
            "has_workspace": bool(ws_uris),
            "workspace_name_hint": ws_hint_name,
            "child_count": len(exported_children),
            "swarm_worker_count": len([c for c in exported_children if c["kind"] == "swarm_worker"]),
            "subagent_count": len([c for c in exported_children if c["kind"] in ("subagent", "child")]),
            "side_question_count": len([c for c in exported_children if c["kind"] == "side_question"]),
            "redacted_secrets": total_redactions,
            "placeholders": {
                "home": [PH_HOME_NATIVE, PH_HOME_JSON, PH_HOME_JSON2, PH_HOME_JSON3, PH_HOME_POSIX, PH_HOME_URI],
                "workspace": [PH_WS_NATIVE, PH_WS_JSON, PH_WS_JSON2, PH_WS_JSON3, PH_WS_POSIX, PH_WS_URI],
            },
        }
        (tmp_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        # 6. Zip into `.agyshare`
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for fp in sorted(tmp_dir.rglob("*")):
                if fp.is_file():
                    zf.write(fp, fp.relative_to(tmp_dir).as_posix())

    return {
        "format": "agyshare",
        "source_cid": old_root_cid,
        "title": orig_title,
        "output_path": str(output_path),
        "kept_turns": kept_turns,
        "total_turns": len(turns),
        "step_count": root_steps,
        "include_swarm": include_swarm,
        "child_count": len(exported_children),
        "swarm_worker_count": manifest["swarm_worker_count"],
        "side_question_count": manifest["side_question_count"],
        "redacted_secrets": total_redactions,
        "size_bytes": output_path.stat().st_size,
    }


# ---------------------------------------------------------------------------
# 5. Inspect & Import `.agyshare` Bundle into Recipient's Antigravity
# ---------------------------------------------------------------------------
def inspect_share_bundle(bundle_path: Path) -> dict[str, Any]:
    if not bundle_path.is_file():
        raise FileNotFoundError(f"未找到分享包文件: {bundle_path}")
    with zipfile.ZipFile(bundle_path, "r") as zf:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        manifest["bundle_path"] = str(bundle_path)
        manifest["size_bytes"] = bundle_path.stat().st_size
        return manifest


def _ensure_summaries_schema(conn: sqlite3.Connection) -> None:
    """Create standard conversation_summaries / conversations_fts / conversation_parents if fresh DB."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS conversation_summaries (
            conversation_id text PRIMARY KEY,
            title text NOT NULL DEFAULT "",
            preview text NOT NULL DEFAULT "",
            step_count integer NOT NULL DEFAULT 0,
            last_modified_time datetime NOT NULL,
            workspace_uris text NOT NULL,
            status text NOT NULL DEFAULT "",
            source text NOT NULL DEFAULT "",
            project_id text NOT NULL DEFAULT "",
            agent_name text NOT NULL DEFAULT "",
            parent_conversation_id text NOT NULL DEFAULT "",
            nesting_depth integer NOT NULL DEFAULT 0,
            battle_id text NOT NULL DEFAULT "",
            winning_conversation_id text NOT NULL DEFAULT "",
            not_fully_idle numeric NOT NULL DEFAULT false,
            killed numeric NOT NULL DEFAULT false,
            last_user_input_time datetime NOT NULL,
            last_user_input_step_index integer NOT NULL DEFAULT -1,
            app_data_dir text NOT NULL DEFAULT "",
            raw_summary blob,
            group_id text NOT NULL DEFAULT ""
        )"""
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS conversation_parents (conversation_id TEXT PRIMARY KEY, parent_id TEXT NOT NULL) WITHOUT ROWID"
    )
    has_fts = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='conversations_fts'"
    ).fetchone()
    if not has_fts:
        conn.execute(
            """CREATE VIRTUAL TABLE conversations_fts USING fts5(
                conversation_id UNINDEXED,
                chunk_index UNINDEXED,
                chunk_first_step UNINDEXED,
                chunk_last_step UNINDEXED,
                last_modified_time UNINDEXED,
                step_count UNINDEXED,
                last_step_created_at UNINDEXED,
                archived UNINDEXED,
                user_step_byte_offsets UNINDEXED,
                agent_step_byte_offsets UNINDEXED,
                title, workspace, project, user_body, agent_body,
                tokenize = 'unicode61 remove_diacritics 2',
                prefix = '1 2 3'
            )"""
        )


def _rebuild_raw_summary_for_import(
    raw: bytes,
    *,
    exact_reps: list[tuple[str, str]],
    new_tid: str,
    new_title: str,
    new_step_count: int,
    new_last_user_idx: int,
    now_ns: int,
    keep_side_questions: bool,
) -> bytes:
    if not raw:
        return b""

    # First rewrite variable-length placeholders & UUIDs safely across the protobuf
    rewritten, _ = rewrite_pb_blob(raw, exact_reps=exact_reps, redact_secrets=False)
    base_bytes = rewritten or raw

    new_tid_b = new_tid.encode("ascii")
    title_b = new_title.encode("utf-8")
    now_ts = bc.make_pb_timestamp(now_ns)

    new_fields: list[tuple[int, int, int | bytes]] = []
    saw_title = False
    saw_status = False

    for fnum, wtype, val in bc.parse_pb_fields(base_bytes):
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
            new_fields.append((5, 0, 1))  # CASCADE_RUN_STATUS_IDLE
            saw_status = True
        elif fnum == 15 and wtype == 2 and isinstance(val, bytes):
            sub_fields: list[tuple[int, int, int | bytes]] = [(1, 2, title_b), (7, 2, now_ts)]
            if keep_side_questions:
                # Preserve remapped side_question_cascade_ids (17) & side_question_titles (18)
                for sf, sw, sv in bc.parse_pb_fields(val):
                    if sf in (17, 18):
                        sub_fields.append((sf, sw, sv))
            new_fields.append((15, 2, bc.serialize_pb_fields(sub_fields)))
        elif fnum == 16 and wtype == 0:
            new_fields.append((16, 0, max(0, new_last_user_idx)))
        elif fnum == 29 and wtype == 0:
            continue
        else:
            new_fields.append((fnum, wtype, val))

    if not saw_title:
        new_fields.insert(0, (1, 2, title_b))
    if not saw_status:
        new_fields.append((5, 0, 1))
    return bc.serialize_pb_fields(new_fields)


def import_share_bundle(
    bundle_path: Path,
    *,
    custom_title: str | None = None,
    project_id: str | None = None,
    workspace_path: Path | str | None = None,
    agy_root: Path | None = None,
    target_home: Path | str | None = None,
) -> dict[str, Any]:
    """
    Imports an `.agyshare` bundle cleanly into the recipient's Antigravity storage:
    - Generates brand-new UUIDs for root + every Swarm worker / Subagent / Side Question.
    - Remaps all portable path placeholders to the recipient's OS home & workspace.
    - Inserts root + all children into `conversation_summaries`, `conversation_parents`,
      `conversations_fts`, and `annotations` (zero restart required!).
    """
    if not bundle_path.is_file():
        raise FileNotFoundError(f"未找到分享包文件: {bundle_path}")

    root_dir = agy_root or bc.AGY_ROOT
    home_val: Path | str = target_home if target_home is not None else Path.home()
    if workspace_path is not None:
        ws_raw = str(workspace_path)
        ws_val: Path | str | None = ws_raw if ws_raw.startswith("/") else Path(ws_raw).expanduser().resolve()
        ws_uri = path_to_file_uri(str(ws_val))
    else:
        ws_val = None
        ws_uri = ""
    target_pid = (project_id or "").strip() or "outside-of-project"

    with tempfile.TemporaryDirectory(prefix="agyshare_import_") as tmp_s:
        tmp_dir = Path(tmp_s)
        with zipfile.ZipFile(bundle_path, "r") as zf:
            # Safe zip extraction (guard against ZipSlip path traversal)
            for member in zf.infolist():
                target_member = (tmp_dir / member.filename).resolve()
                if not str(target_member).startswith(str(tmp_dir.resolve())):
                    raise ValueError(f"拒绝不安全的压缩包路径: {member.filename}")
            zf.extractall(tmp_dir)

        manifest = json.loads((tmp_dir / "manifest.json").read_text(encoding="utf-8"))
        old_root_cid = manifest["root_cid"]
        include_swarm = bool(manifest.get("include_swarm", True))

        root_sum_raw = _deserialize_summary_row(
            json.loads((tmp_dir / "summaries" / "root.json").read_text(encoding="utf-8"))
        )
        root_fts_raw = [
            _deserialize_summary_row(r)
            for r in json.loads((tmp_dir / "summaries" / "root_fts.json").read_text(encoding="utf-8"))
        ]
        children_blob = json.loads((tmp_dir / "summaries" / "children.json").read_text(encoding="utf-8"))
        children_list: list[dict[str, Any]] = children_blob.get("children") or []
        parent_edges: list[list[str]] = children_blob.get("parent_edges") or []
        annotations_map: dict[str, str] = json.loads(
            (tmp_dir / "summaries" / "annotations.json").read_text(encoding="utf-8")
        )

        # 1. Build unified bijective UUID map across the entire family tree (root + all children + tids + init_ids)
        cid_map: dict[str, str] = {old_root_cid: str(uuid.uuid4())}
        tid_map: dict[str, str] = {}
        init_map: dict[str, str] = {}

        all_old_cids = [old_root_cid] + [c["conversation_id"] for c in children_list]
        for oc in all_old_cids:
            if oc not in cid_map:
                cid_map[oc] = str(uuid.uuid4())
            odb = tmp_dir / "conversations" / f"{oc}.db"
            if odb.is_file():
                c = sqlite3.connect(f"file:{odb.as_posix()}?mode=ro", uri=True)
                try:
                    tm = c.execute("SELECT trajectory_id FROM trajectory_meta LIMIT 1").fetchone()
                    if tm and tm[0] and tm[0] not in tid_map:
                        tid_map[tm[0]] = str(uuid.uuid4())
                    tb = c.execute("SELECT data FROM trajectory_metadata_blob LIMIT 1").fetchone()
                    if tb and tb[0]:
                        oid = bc.extract_init_state_id(tb[0])
                        if oid and oid not in init_map and oid not in cid_map and oid not in tid_map:
                            init_map[oid] = str(uuid.uuid4())
                finally:
                    c.close()

        new_root_cid = cid_map[old_root_cid]
        search_token = f"agybranch{new_root_cid.replace('-', '')[:12]}"

        path_reps, is_posix_target = _build_import_path_replacements(home_val, ws_val)
        if is_posix_target:
            # Also normalize immediate Windows backslash following placeholders on POSIX targets
            path_reps = [
                (f"{PH_WS_NATIVE}\\", f"{str(ws_val or home_val).rstrip('/')}/"),
                (f"{PH_HOME_NATIVE}\\", f"{str(home_val).rstrip('/')}/"),
                *path_reps,
            ]
        uuid_reps = (
            list(cid_map.items())
            + list(tid_map.items())
            + list(init_map.items())
        )
        proj_reps = [("outside-of-project", target_pid)] if target_pid != "outside-of-project" else []
        all_exact_reps = [*path_reps, *uuid_reps, *proj_reps]

        # 2. Prepare recipient directories
        (root_dir / "conversations").mkdir(parents=True, exist_ok=True)
        (root_dir / "brain").mkdir(parents=True, exist_ok=True)
        (root_dir / "annotations").mkdir(parents=True, exist_ok=True)

        # 3. Install root + child SQLite DBs & brain/ directories
        new_step_counts: dict[str, tuple[int, int]] = {}
        new_tids_by_cid: dict[str, str] = {}

        for oc in all_old_cids:
            nc = cid_map[oc]
            src_db = tmp_dir / "conversations" / f"{oc}.db"
            if not src_db.is_file():
                continue
            dst_db = root_dir / "conversations" / f"{nc}.db"
            shutil.copy2(src_db, dst_db)

            # Determine this DB's new trajectory_id
            c = sqlite3.connect(f"file:{dst_db.as_posix()}?mode=ro", uri=True)
            try:
                tm = c.execute("SELECT trajectory_id FROM trajectory_meta LIMIT 1").fetchone()
                ntid = tid_map.get(tm[0], str(uuid.uuid4())) if (tm and tm[0]) else str(uuid.uuid4())
            finally:
                c.close()
            new_tids_by_cid[nc] = ntid

            steps_cnt, last_u, _ = _rewrite_sqlite_db(
                dst_db,
                exact_reps=all_exact_reps,
                redact_secrets=False,
                new_tid=ntid,
                new_cid=nc,
            )
            new_step_counts[nc] = (steps_cnt, last_u)

            # Restore WAL mode cleanly matching live Antigravity convention
            wconn = sqlite3.connect(dst_db, timeout=15.0)
            try:
                wconn.execute("PRAGMA journal_mode=WAL")
                wconn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                wconn.close()

            src_b = tmp_dir / "brain" / oc
            if src_b.is_dir():
                _copy_and_sanitize_brain_dir(
                    src_b,
                    root_dir / "brain" / nc,
                    include_swarm_state=include_swarm,
                    cutoff_count=None,
                    exact_reps=all_exact_reps,
                    ci_reps=None,
                    redact_secrets=False,
                    uuid_map=cid_map,
                    target_workspace_uri=ws_uri,
                    normalize_for_import=True,
                )

        # 4. Compute recipient title & timestamps
        now_ns = time.time_ns()
        now_secs = now_ns // 1_000_000_000
        now_nanos = now_ns % 1_000_000_000
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f+00:00")

        sum_db = root_dir / "conversation_summaries.db"
        sconn = sqlite3.connect(sum_db, timeout=15.0)
        try:
            _ensure_summaries_schema(sconn)
            base_title = manifest.get("title") or root_sum_raw.get("title") or "导入的对话"
            new_title = bc.pick_branch_title(sconn, base_title, custom_title, suffix_tag="导入")

            # 5. Write annotations/<new_cid>.pbtxt (preserving remapped side_question_cascade_ids!)
            escaped_title = new_title.replace("\\", "\\\\").replace('"', '\\"')
            root_ann_src = annotations_map.get(old_root_cid, "")
            if include_swarm and root_ann_src and "side_question_cascade_ids" in root_ann_src:
                remapped_ann, _ = apply_text_replacements(root_ann_src, all_exact_reps)
                remapped_ann = re.sub(
                    r'^title\s*:\s*"(?:[^"\\]|\\.)*"',
                    f'title:"{escaped_title}"',
                    remapped_ann,
                )
                (root_dir / "annotations" / f"{new_root_cid}.pbtxt").write_bytes(remapped_ann.encode("utf-8"))
            else:
                (root_dir / "annotations" / f"{new_root_cid}.pbtxt").write_bytes(
                    f'title:"{escaped_title}" last_user_view_time:{{seconds:{now_secs} nanos:{now_nanos}}}'.encode("utf-8")
                )

            for oc, atxt in annotations_map.items():
                if oc == old_root_cid or oc not in cid_map:
                    continue
                remapped_c, _ = apply_text_replacements(atxt, all_exact_reps)
                (root_dir / "annotations" / f"{cid_map[oc]}.pbtxt").write_bytes(remapped_c.encode("utf-8"))

            # 6. Insert root + all child rows into conversation_summaries, conversation_parents & conversations_fts
            db_cols = [r[1] for r in sconn.execute("PRAGMA table_info(conversation_summaries)").fetchall()]

            def _insert_summary(row_dict: dict[str, Any]) -> None:
                use_cols = [c for c in db_cols if c in row_dict]
                ph = ",".join("?" for _ in use_cols)
                cl = ",".join(f"[{c}]" for c in use_cols)
                sconn.execute(
                    f"INSERT OR REPLACE INTO conversation_summaries ({cl}) VALUES ({ph})",
                    [row_dict[c] for c in use_cols],
                )

            root_steps, root_last_u = new_step_counts.get(new_root_cid, (int(root_sum_raw.get("step_count") or 0), -1))
            root_row = dict(root_sum_raw)
            root_row["conversation_id"] = new_root_cid
            root_row["title"] = new_title
            root_row["preview"] = new_title
            root_row["step_count"] = root_steps
            root_row["last_modified_time"] = now_iso
            root_row["status"] = "CASCADE_RUN_STATUS_IDLE"
            root_row["project_id"] = target_pid
            root_row["workspace_uris"] = json.dumps([ws_uri] if ws_uri else [])
            root_row["not_fully_idle"] = 0
            root_row["killed"] = 0
            root_row["parent_conversation_id"] = ""
            root_row["nesting_depth"] = 0
            root_row["last_user_input_step_index"] = root_last_u
            root_row["raw_summary"] = _rebuild_raw_summary_for_import(
                root_sum_raw.get("raw_summary") or b"",
                exact_reps=all_exact_reps,
                new_tid=new_tids_by_cid.get(new_root_cid, str(uuid.uuid4())),
                new_title=new_title,
                new_step_count=root_steps,
                new_last_user_idx=root_last_u,
                now_ns=now_ns,
                keep_side_questions=include_swarm,
            )
            _insert_summary(root_row)

            imported_children_count = 0
            for ch in children_list:
                oc = ch["conversation_id"]
                if oc not in cid_map or not ch.get("summary"):
                    continue
                nc = cid_map[oc]
                csum = _deserialize_summary_row(ch["summary"])
                c_steps, c_last_u = new_step_counts.get(nc, (int(csum.get("step_count") or 0), -1))
                old_p = ch.get("parent_id") or csum.get("parent_conversation_id") or old_root_cid
                new_p = cid_map.get(old_p, new_root_cid)

                csum["conversation_id"] = nc
                csum["parent_conversation_id"] = "" if ch.get("kind") == "side_question" and not csum.get("parent_conversation_id") else new_p
                csum["step_count"] = c_steps
                csum["last_modified_time"] = now_iso
                csum["status"] = "CASCADE_RUN_STATUS_IDLE"
                csum["project_id"] = target_pid
                csum["workspace_uris"] = json.dumps([ws_uri] if ws_uri else [])
                csum["not_fully_idle"] = 0
                csum["last_user_input_step_index"] = c_last_u
                csum["raw_summary"] = _rebuild_raw_summary_for_import(
                    csum.get("raw_summary") or b"",
                    exact_reps=all_exact_reps,
                    new_tid=new_tids_by_cid.get(nc, str(uuid.uuid4())),
                    new_title=str(csum.get("title") or ch.get("agent_name") or ""),
                    new_step_count=c_steps,
                    new_last_user_idx=c_last_u,
                    now_ns=now_ns,
                    keep_side_questions=False,
                )
                _insert_summary(csum)
                imported_children_count += 1

            # Restore conversation_parents edges (Side Questions, etc.)
            for old_c, old_p in parent_edges:
                if old_c in cid_map and old_p in cid_map:
                    sconn.execute(
                        "INSERT OR REPLACE INTO conversation_parents (conversation_id, parent_id) VALUES (?, ?)",
                        (cid_map[old_c], cid_map[old_p]),
                    )

            # Insert FTS5 entries so sidebar & search find the imported conversation immediately without restart
            fts_cols = [r[1] for r in sconn.execute("PRAGMA table_info(conversations_fts)").fetchall()]
            if fts_cols:
                pmap = bc.load_projects_map()
                proj_label = pmap.get(target_pid, "") if target_pid != "outside-of-project" else ""
                fts_cl = ",".join(fts_cols)
                fts_qm = ",".join("?" for _ in fts_cols)
                inserted_meta = False
                inserted_token = False

                for frow in root_fts_raw:
                    fd = dict(frow)
                    cidx = int(fd.get("chunk_index", 0))
                    fd["conversation_id"] = new_root_cid
                    for tk in ("title", "workspace", "project", "user_body", "agent_body"):
                        if isinstance(fd.get(tk), str) and fd[tk]:
                            fd[tk], _ = apply_text_replacements(fd[tk], all_exact_reps)
                    if cidx == -1:
                        fd["last_modified_time"] = now_ns
                        fd["step_count"] = root_steps
                        fd["last_step_created_at"] = now_ns
                        fd["archived"] = 0
                        fd["title"] = new_title
                        fd["workspace"] = proj_label
                        fd["project"] = proj_label
                        inserted_meta = True
                    elif not inserted_token:
                        fd["user_body"] = f"{fd.get('user_body') or ''}\n{search_token}"
                        inserted_token = True
                    sconn.execute(
                        f"INSERT INTO conversations_fts ({fts_cl}) VALUES ({fts_qm})",
                        [fd.get(c) for c in fts_cols],
                    )

                if not inserted_meta:
                    meta_fd = {
                        "conversation_id": new_root_cid,
                        "chunk_index": -1,
                        "chunk_first_step": 0,
                        "chunk_last_step": 0,
                        "last_modified_time": now_ns,
                        "step_count": root_steps,
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
                    sconn.execute(
                        f"INSERT INTO conversations_fts ({fts_cl}) VALUES ({fts_qm})",
                        [meta_fd.get(c) for c in fts_cols],
                    )
                if not inserted_token:
                    tok_fd = {
                        "conversation_id": new_root_cid,
                        "chunk_index": 0,
                        "chunk_first_step": 0,
                        "chunk_last_step": max(0, root_steps - 1),
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
                    sconn.execute(
                        f"INSERT INTO conversations_fts ({fts_cl}) VALUES ({fts_qm})",
                        [tok_fd.get(c) for c in fts_cols],
                    )

            sconn.commit()
        finally:
            sconn.close()

    return {
        "new_cid": new_root_cid,
        "new_title": new_title,
        "search_token": search_token,
        "step_count": root_steps,
        "project_id": target_pid,
        "workspace_uri": ws_uri,
        "imported_children": imported_children_count,
        "has_swarm": bool(manifest.get("has_swarm")),
        "link": f"[{new_title}](conversation://{new_root_cid})",
        "db_path": str(root_dir / "conversations" / f"{new_root_cid}.db"),
    }


# ---------------------------------------------------------------------------
# 6. CLI Entry Point
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export / Inspect / Import portable Antigravity conversation share bundles (.agyshare)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_exp = sub.add_parser("export", help="Export a conversation to a portable .agyshare bundle (or Markdown)")
    p_exp.add_argument("--id", dest="source_cid", help="Source conversation UUID")
    p_exp.add_argument("--title", dest="title_query", help="Match source conversation by title substring")
    p_exp.add_argument("--turn", dest="turn_number", type=int, help="Export up to 1-based turn N")
    p_exp.add_argument("--drop-last", dest="drop_last", type=int, help="Exclude the last K completed turns")
    p_exp.add_argument("-o", "--output", dest="output", help="Output file path (.agyshare or .md)")
    p_exp.add_argument("--format", choices=("agyshare", "md"), default="agyshare", help="Export format (default: agyshare)")
    p_exp.add_argument("--lite", action="store_true", help="Export root conversation only (exclude Swarm workers & Subagents)")
    p_exp.add_argument("--no-redact-secrets", action="store_true", help="Disable automatic API key / token redaction")
    p_exp.add_argument("--agy-root", help="Override ~/.gemini/antigravity directory (for testing)")

    p_ins = sub.add_parser("inspect", help="Inspect metadata of an .agyshare bundle without importing")
    p_ins.add_argument("bundle", help="Path to .agyshare file")

    p_imp = sub.add_parser("import", help="Import an .agyshare bundle into local Antigravity")
    p_imp.add_argument("bundle", help="Path to .agyshare file")
    p_imp.add_argument("--title", dest="custom_title", help="Custom title for imported conversation")
    p_imp.add_argument("--project", dest="project_id", help="Bind to a local project ID or name")
    p_imp.add_argument("--workspace", dest="workspace", help="Remap workspace paths to this local folder")
    p_imp.add_argument("--open", action="store_true", help="Automatically open the imported conversation in Antigravity")
    p_imp.add_argument("--agy-root", help="Override ~/.gemini/antigravity directory (for testing)")

    args = parser.parse_args()

    if args.cmd == "inspect":
        info = inspect_share_bundle(Path(args.bundle))
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "export":
        agy_root = Path(args.agy_root) if args.agy_root else None
        out_p = Path(args.output) if args.output else None
        if args.format == "md":
            if out_p is None:
                out_p = Path.cwd() / "antigravity_handoff.md"
            res = export_markdown_handoff(
                source_cid=args.source_cid,
                title_query=args.title_query,
                turn_number=args.turn_number,
                drop_last=args.drop_last,
                output_path=out_p,
                include_swarm=not args.lite,
                redact_secrets=not args.no_redact_secrets,
                agy_root=agy_root,
            )
        else:
            res = export_share_bundle(
                source_cid=args.source_cid,
                title_query=args.title_query,
                turn_number=args.turn_number,
                drop_last=args.drop_last,
                output_path=out_p,
                include_swarm=not args.lite,
                redact_secrets=not args.no_redact_secrets,
                agy_root=agy_root,
            )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "import":
        agy_root = Path(args.agy_root) if args.agy_root else None
        pid = args.project_id
        if pid and not _UUID_RE.match(pid) and pid != "outside-of-project":
            # Allow passing project display name as well as UUID
            pmap = bc.load_projects_map()
            for k, v in pmap.items():
                if v.lower() == pid.lower():
                    pid = k
                    break
        res = import_share_bundle(
            Path(args.bundle),
            custom_title=args.custom_title,
            project_id=pid,
            workspace_path=Path(args.workspace) if args.workspace else None,
            agy_root=agy_root,
        )
        if args.open and agy_root is None:
            bc.auto_open_in_antigravity(res["search_token"], surface="app", new_cid=res["new_cid"])
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
