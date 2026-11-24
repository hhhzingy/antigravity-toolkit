# AGENTS.md — Antigravity Toolkit AI Installation & Maintenance Guide

When a user asks you (an AI Agent running inside **Antigravity 2.0 App**, **Antigravity IDE**, **`agy` CLI**, or any coding assistant) to install, update, diagnose, or uninstall optimizations from this repository:

## 1. Zero-Question Environment Auto-Detection (Do NOT Ask the User!)

**NEVER ask the user which OS (`Windows` / `macOS` / `Linux`) or which Antigravity edition (`App 2.0` / `Antigravity IDE` / `agy CLI`) they installed.** You can detect everything locally in `< 1 second`:

1. Run the zero-dependency health & surface detector first:
   - **Windows**: `python scripts/doctor.py --json`
   - **macOS / Linux**: `python3 scripts/doctor.py --json`
2. Inspect `platform` (`os`, `session_mode`, `is_headless`) and `surfaces` (`antigravity_app`, `antigravity_ide`, `agy_cli`) in the JSON output.

## 2. Automated Installation & Adaptation

Unless the user specifically requested only one module (e.g., *"only install close guard"* -> `-Module 2` / `--module 2`), run the unified installer for their OS:

- **Windows (PowerShell)**:
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -All
  ```
- **macOS & Linux (Bash — Desktop or Headless SSH)**:
  ```bash
  bash ./install.sh --all
  ```

Both installers **automatically adapt** to the detected environment:
- **Antigravity 2.0 App & Antigravity IDE**: Configures `~/.gemini/config/mcp_config.json`, global routing rules, system tray / menu-bar close guard, and Studio/CLI conversation branching + cross-user `.agyshare` sharing (with Swarm/Subagent migration and IDE-safe window handling).
- **`agy` CLI (`~/.gemini/antigravity-cli`)**: Automatically syncs MCP server entries into `~/.gemini/antigravity-cli/settings.json` (preserving user preferences), protects active `agy` terminal windows from accidental close (plus `agy-guard` `tmux` persistence on Linux/macOS), and supports branching `agy` CLI transcripts via `branch_conversation.py`.
- **Headless Linux SSH Servers**: Automatically skips X11-only GUI dependencies and configures headless-ready `chrome-devtools` MCP, `agy-guard` (`tmux` session wrapper), and CLI conversation branching.

## 3. Post-Install Verification & User Handoff

1. Run `python scripts/doctor.py` (or `python3 scripts/doctor.py`) to confirm all applicable modules show `[已完整安装]`.
2. Report concisely in the user's language, mentioning **only** the minimal manual action if applicable:
   - **Browser Direct Connect (GUI systems)**: Open `chrome://inspect/#remote-debugging` (or `edge://inspect/#remote-debugging`), check **`Enable remote debugging`**, and click **Refresh** in MCP Servers (or run `/mcp` in `agy` CLI).
   - **macOS Permissions (if using desktop clicking / `Cmd+Q` guard)**: Allow Terminal / Python under **System Settings -> Privacy & Security -> Accessibility & Screen Recording** when prompted.

## 4. Clean Modular Uninstall

- **Windows**: `powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Uninstall` (or append `-Module 1|2|3`)
- **macOS & Linux**: `bash ./install.sh --uninstall` (or append `--module 1|2|3`)
