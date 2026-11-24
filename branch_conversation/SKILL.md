---
name: branch-conversation
description: Clone, fork, branch, export, or import an Antigravity conversation (across Antigravity 2.0 App, Antigravity IDE, and `agy` CLI) — including optional turn truncation and cross-user `.agyshare` / Markdown sharing with full Swarm teams, nested Subagents, message boards, and Side Questions. Trigger when the user asks to branch, fork, clone, rewind, export, share, send, or import a conversation or `.agyshare` archive.
---

# Branch / Fork & Cross-User Share Antigravity Conversation (App 2.0 · IDE · `agy` CLI)

Use the tools in `~/mcp-gui-workspace/antigravity-branch/`:
- **`branch_conversation.py`**: Local fork/branch at any historical turn `1..N` (without restarting).
- **`share_conversation.py`**: Cross-user export/inspect/import via portable `.agyshare` archives (supports full **Swarm teams, Subagents, message boards, and Side Questions**, with automatic path rewriting across Windows/macOS/Linux and API-key/secret redaction) or human-readable Markdown handoff (`.md`).

*(Tip: Inside an active `agy` CLI TUI session, `/fork` creates an immediate fork from the latest turn; use `branch_conversation.py` to branch from any earlier turn `1..N`, or `share_conversation.py` to export/import `.agyshare` across different users and machines.)*

- **Windows paths**:
  - `"$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\branch_conversation.py"`
  - `"$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\share_conversation.py"`
- **macOS / Linux paths**:
  - `"$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py"`
  - `"$HOME/mcp-gui-workspace/antigravity-branch/share_conversation.py"`

## Part 1: Local Branch / Fork Commands

### Windows (PowerShell)

1. **Inspect all turns (1-based turn index, timestamp, message preview) of a conversation**:
   ```powershell
   python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\branch_conversation.py" --id <conversation_id> --list-turns
   ```
   *(Omit `--id` to target the latest active conversation, or pass `--title "my-web-app"`.)*

2. **Full clone (all completed turns) & auto-open**:
   ```powershell
   python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\branch_conversation.py" --id <conversation_id> --open
   ```

3. **Ignore the last `K` completed turns (e.g., clone from start up to the 2nd-to-last turn)**:
   ```powershell
   python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\branch_conversation.py" --id <conversation_id> --drop-last 1 --open
   ```

4. **Clone from Turn 1 up to a specific Turn `N` (inclusive)**:
   ```powershell
   python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\branch_conversation.py" --id <conversation_id> --turn <N> --open
   ```

5. **Open visual Studio GUI picker (supports Branch + Export/Import `.agyshare`)**:
   ```powershell
   pythonw "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\branch_conversation.py" --gui
   ```

### macOS / Linux (Bash)

```bash
# List turns
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --id <conversation_id> --list-turns

# Full clone / drop last K turns / branch at turn N
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --id <conversation_id> --open
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --id <conversation_id> --drop-last 1 --open
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --id <conversation_id> --turn <N> --open

# Open visual Studio GUI picker
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --gui
```

## Part 2: Cross-User Share (`.agyshare` / Markdown) — Includes Swarm & Subagents

`share_conversation.py` reads live SQLite databases in strictly read-only mode (`?mode=ro` + online backup), never interrupts active chats, automatically strips local paths & secrets, and remaps all UUIDs + Swarm state cleanly on import.

### Windows (PowerShell)

```powershell
# 1. Export full conversation + Swarm team / Subagents / Side Questions -> .agyshare
python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\share_conversation.py" export --id <conversation_id> -o "C:\path\to\handoff.agyshare"

# 2. Lite export (main conversation only, excluding Swarm/Subagents; optionally truncate to Turn N)
python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\share_conversation.py" export --id <conversation_id> --lite --turn 8 -o "C:\path\to\handoff.agyshare"

# 3. Export human-readable Markdown handoff (includes Swarm message board)
python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\share_conversation.py" export --id <conversation_id> --format md -o "C:\path\to\handoff.md"

# 4. Inspect a received .agyshare bundle before importing
python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\share_conversation.py" inspect "C:\path\to\handoff.agyshare"

# 5. Import a received .agyshare bundle into local Antigravity, bind workspace, and auto-open
python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\share_conversation.py" import "C:\path\to\handoff.agyshare" --workspace "C:\path\to\local-repo" --open
```

### macOS / Linux (Bash)

```bash
# Export (.agyshare with Swarm / Lite / Markdown)
python3 "$HOME/mcp-gui-workspace/antigravity-branch/share_conversation.py" export --id <conversation_id> -o ./handoff.agyshare
python3 "$HOME/mcp-gui-workspace/antigravity-branch/share_conversation.py" export --id <conversation_id> --lite -o ./handoff.agyshare
python3 "$HOME/mcp-gui-workspace/antigravity-branch/share_conversation.py" export --id <conversation_id> --format md -o ./handoff.md

# Inspect & Import
python3 "$HOME/mcp-gui-workspace/antigravity-branch/share_conversation.py" inspect ./handoff.agyshare
python3 "$HOME/mcp-gui-workspace/antigravity-branch/share_conversation.py" import ./handoff.agyshare --workspace /path/to/local-repo --open
```

## Output Requirement
- For **Desktop App / Antigravity IDE** branches or imports: always include the returned clickable markdown link `[<new_title>](conversation://<new_cid>)` directly in your reply so the user can jump straight into the conversation in one click.
- For **`agy` CLI** branches: include the returned `resume_command` (`agy --resume <new_cid>`).
- For **`.agyshare` / `.md` exports**: include a clickable file link to the exported archive, report how many Swarm/Subagent/Side Question sessions and secret redactions were processed, and remind the recipient they can import it via Studio GUI (`↙ 导入分享`) or `share_conversation.py import`.
