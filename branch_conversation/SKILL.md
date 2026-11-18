---
name: branch-conversation
description: Clone / fork / branch an existing Antigravity conversation into a new independent conversation UUID, optionally truncating at any historical chat turn (e.g., full clone, ignore the last N messages, or branch right after Turn #K). Trigger when the user asks to branch, fork, clone, or duplicate a conversation or rewind/branch from an earlier message.
---

# Branch / Fork Antigravity Conversation

Use `~/mcp-gui-workspace/antigravity-branch/branch_conversation.py` to clone any Antigravity conversation into a clean, independent branched conversation (`CASCADE_RUN_STATUS_IDLE`) with full SQLite + FTS5 sidebar/search indexing—without restarting Antigravity.

- **Windows path**: `"$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\branch_conversation.py"`
- **Linux / macOS path**: `"$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py"`

## Commands

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

5. **Open visual GUI picker**:
   ```powershell
   pythonw "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\branch_conversation.py" --gui
   ```

### Linux / macOS (Bash)

```bash
# List turns
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --id <conversation_id> --list-turns

# Full clone / drop last K turns / branch at turn N
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --id <conversation_id> --open
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --id <conversation_id> --drop-last 1
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --id <conversation_id> --turn <N>

# Open visual GUI picker
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --gui
```

## Output Requirement
Always include the returned clickable markdown link `[<new_title>](conversation://<new_cid>)` directly in your reply so the user can jump straight into the branched conversation in one click.
