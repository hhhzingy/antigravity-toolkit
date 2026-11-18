---
name: branch-conversation
description: Clone / fork / branch an existing Antigravity conversation (across Antigravity 2.0 App, Antigravity IDE, and `agy` CLI) into a new independent conversation UUID, optionally truncating at any historical chat turn (e.g., full clone, ignore the last N messages, or branch right after Turn #K). Trigger when the user asks to branch, fork, clone, or duplicate a conversation or rewind/branch from an earlier message.
---

# Branch / Fork Antigravity Conversation (App 2.0 · IDE · `agy` CLI)

Use `~/mcp-gui-workspace/antigravity-branch/branch_conversation.py` to clone any Antigravity conversation—whether created in **Antigravity 2.0 Desktop App**, **Antigravity IDE**, or **`agy` CLI** (`~/.gemini/antigravity-cli/`)—at any historical turn without restarting.

*(Tip: Inside an active `agy` CLI TUI session, if the user only wants an immediate fork from the latest turn, `/fork` is also available natively; for rewinding/branching at any specific historical turn `1..N` or ignoring the last `K` turns, use `branch_conversation.py` below.)*

- **Windows path**: `"$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\branch_conversation.py"`
- **macOS / Linux path**: `"$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py"`

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

5. **Open visual Studio GUI picker**:
   ```powershell
   pythonw "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\branch_conversation.py" --gui
   ```

### macOS / Linux (Bash)

```bash
# List turns
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --id <conversation_id> --list-turns

# Full clone / drop last K turns / branch at turn N
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --id <conversation_id> --open
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --id <conversation_id> --drop-last 1
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --id <conversation_id> --turn <N>

# Open visual Studio GUI picker
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --gui
```

## Output Requirement
- For **Desktop App / Antigravity IDE** branches: always include the returned clickable markdown link `[<new_title>](conversation://<new_cid>)` directly in your reply so the user can jump straight into the branched conversation in one click.
- For **`agy` CLI** branches: include the returned `resume_command` (`agy --resume <new_cid>`) so the user can jump straight into the branched CLI session.
