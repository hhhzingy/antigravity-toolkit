# Antigravity Toolkit

**Agent-ready modular enhancements for Google Antigravity across Windows, macOS & Linux — automatically adapting to Antigravity 2.0 App, Antigravity IDE, and `agy` CLI**

**[简体中文](./README.md)** | English · [🤖 Agent-Native Install](#-agent-native-mode-let-antigravity-install-it-for-you-recommended) · [✨ Modules](#-modular-enhancements-overview) · [🚀 Manual Quick Start](#-manual-quick-start) · [📖 Usage & Uninstall](#-daily-usage--clean-uninstall) · [❓ FAQ](#-faq--troubleshooting) · [🤝 Contributing](./CONTRIBUTING.md)

> 💡 **Zero core-file modifications · Survives auto-updates · Modular pick-and-choose · Clean uninstall anytime**

---

## 👋 Why Antigravity Toolkit?

If you use Google Antigravity every day, you have probably run into these workflow paper cuts:

- **Blank browsers lose your logins & screen control feels sluggish**: Default setups launch fresh unlogged browser profiles, take seconds per screenshot, struggle with custom UIs (WeChat, games, remote desktops), and lock out your mouse.
- **One accidental click on `X` kills active AI work**: Clicking `X` or pressing `Alt+F4` just to tidy up your desktop closes the whole app and interrupts running agents mid-task.
- **No built-in way to branch a conversation from an earlier turn**: Native split view opens an empty chat instead of carrying over your conversation history up to Turn K.
- **A growing modular toolkit**: Built around real everyday pain points—install everything at once or pick only the modules you want.

---

## 🤖 Agent-Native Mode: Let Antigravity Install It for You (Recommended)

In the Agent era, you never need to memorize commands or tell your AI what OS (`Windows`/`macOS`/`Linux`) or Antigravity edition (`App 2.0`/`IDE`/`agy` CLI) you use—**just paste this prompt into any Antigravity chat or `agy` terminal**, and built-in [`AGENTS.md`](./AGENTS.md) + [`doctor.py`](./scripts/doctor.py) will auto-detect and configure everything:

```text
Please read https://github.com/hhhzingy/antigravity-toolkit , auto-detect my OS and installed Antigravity editions, install the optimizations, and run the health check. If any step needs a quick manual toggle, tell me in plain English.
```

- **Pick modules, troubleshoot, or uninstall in plain English**: Want only specific features, hit an error, or want to remove something later? Just tell your Agent (e.g., *"Only install the close-to-tray guard and conversation branching"* or *"Uninstall the close guard from antigravity-toolkit"*).

---

## ✨ Modular Enhancements Overview

| Module | Pain Point Solved | Core Experience | Details |
| :--- | :--- | :--- | :--- |
| **⚡ Faster Desktop & Browser Control**<br>`computer_use` | Blank browsers with lost logins, slow screenshots, unreadable custom apps, mouse lockouts | Controls your already-open, logged-in Chrome/Edge tabs; `~0.1s` screen vision + local OCR; **wiggle your mouse anytime to take back control** (resumes 2s after release) | [Read Guide](./computer_use/README.md) |
| **🛡️ Close-to-Tray Guard**<br>`close_guard` | Accidentally clicking `X` or pressing `Alt+F4` and killing active AI tasks | Minimizes quietly to the system tray on `X` / `Alt+F4` (`Ctrl+Q` on Linux) so background agents stay **100% alive**; modern Win11 rounded tray flyout menu, `0.0%` idle CPU, exits only via **`Quit`** | [Read Guide](./close_guard/README.md) |
| **🌿 Visual Conversation Branching**<br>`branch_conversation` | Wanting to explore a new direction from Turn K without losing later turns | Modern Studio "time-machine" UI (live search, project grouping, full turn message preview) that jumps into a branched chat in `~0.5s` with zero restarts—or just ask your Agent in chat to fork for you | [Read Guide](./branch_conversation/README.md) |

> 💬 **Unsure about any detail or option?** Just ask your Agent directly, or open the module guide linked in the table above.

---

## 🚀 Manual Quick Start

Prefer running terminal commands yourself? Make sure you have **Git** and **Python 3.10+** (plus **Node.js 20+** for `computer_use`; if anything is missing, the health checker will tell you how to install it):

**1. Clone the repository**

```bash
git clone https://github.com/hhhzingy/antigravity-toolkit.git
cd antigravity-toolkit
```

**2. Run the interactive installer** (press `A` to install all modules, a number to pick individual ones, or `D` for a health check)

- **Windows (PowerShell)**:
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\install.ps1
  ```
- **macOS & Linux (Desktop or Headless SSH)**:
  ```bash
  bash ./install.sh
  ```

<details>
<summary>💡 Prefer non-interactive CLI flags? (Click to expand)</summary>

- **Windows ([install.ps1](./install.ps1))**: `powershell -ExecutionPolicy Bypass -File .\install.ps1 -All` (or `-Module 2`, `-Doctor`, `-Uninstall`, `-Uninstall -Module 2`)
- **macOS & Linux ([install.sh](./install.sh))**: `bash ./install.sh --all` (or `--module 2`, `--doctor`, `--uninstall`, `--uninstall --module 2`)
</details>

**3. Run the health check anytime** (verifies prerequisites, browser toggle, and installed modules)

```bash
python scripts/doctor.py   # Use python3 scripts/doctor.py on Linux if python is not aliased
```

---

## 📖 Daily Usage & Clean Uninstall

Every module lives inside your user home directory and can be used or removed independently (need a hand? Ask your Agent, or check each module's guide):

### ⚡ Faster Desktop & Browser Control (`computer_use` · [Module Guide](./computer_use/README.md))
- **One-time browser toggle (2 clicks)**: Open `chrome://inspect/#remote-debugging` in Chrome (or `edge://inspect/#remote-debugging` in Edge), check **Enable remote debugging**, then click **Refresh** in Antigravity's **MCP Servers** panel.
- **Everyday use**: Ask your Agent to read your open browser tabs or interact with desktop apps; **shake your mouse** anytime to take back instant control.
- **Standalone install / uninstall**: Install via `computer_use/setup_other_device.ps1` (Win) or `computer_use/setup_linux.sh` (Linux); uninstall cleanly via `powershell -ExecutionPolicy Bypass -File .\computer_use\uninstall_computer_use.ps1` (Win) or `bash ./computer_use/uninstall_computer_use.sh` (Linux).

### 🛡️ Close-to-Tray Guard (`close_guard` · [Module Guide](./close_guard/README.md))
- **Automatic protection**: Runs silently in the background with login auto-start; clicking `X` or pressing `Alt+F4` (`Ctrl+Q` on Linux) hides Antigravity to the system tray while tasks keep running.
- **Restore & true quit**: Left-click the Windows tray icon to restore (on Linux, click the top-bar icon -> `显示 Antigravity 窗口` or middle-click); right-click the tray icon and choose **`Quit`** to exit completely.
- **One-command uninstall**: Windows: `powershell -ExecutionPolicy Bypass -File .\close_guard\uninstall_close_guard.ps1` · Linux: `bash ./close_guard/uninstall_close_guard.sh`.

### 🌿 Visual Conversation Branching (`branch_conversation` · [Module Guide](./branch_conversation/README.md))
- **Fork a chat anytime**: Right-click the system tray icon and choose **`对话分支克隆...`** (`分支克隆对话 (Branch)...` on Linux) to open the modern Studio branch window (with live search & full turn message preview); tell your Agent *"Clone this conversation up to turn 5"*; or run `~/mcp-gui-workspace/antigravity-branch/branch_conversation.py --gui`.
- **One-command uninstall**: Windows: `powershell -ExecutionPolicy Bypass -File .\branch_conversation\uninstall_branch_tool.ps1` · Linux: `bash ./branch_conversation/uninstall_branch_tool.sh`.

---

## ❓ FAQ & Troubleshooting

<details>
<summary><b>1. How do I enable Chrome or Edge remote debugging in 2 clicks? Is it safe?</b></summary>

Yes—it takes two clicks and stays strictly local to your OS user account:
1. Paste `chrome://inspect/#remote-debugging` (or `edge://inspect/#remote-debugging` for Microsoft Edge) into your browser's address bar and press Enter.
2. Check **Enable remote debugging**.

Only local tools running under your own logged-in user session can connect; no network ports are exposed to your LAN or the internet.
</details>

<details>
<summary><b>2. I clicked <code>X</code> on Windows—where did the Antigravity tray icon go?</b></summary>

Windows places newly added tray icons inside the taskbar overflow menu by default. Click the small **upward arrow `^`** near the clock in your taskbar—you can drag the Antigravity icon onto the main taskbar so it stays visible in one glance.
</details>

<details>
<summary><b>3. Do I need to reinstall anything after Antigravity auto-updates?</b></summary>

**No!** Every module in Antigravity Toolkit works externally without patching or modifying Antigravity's core installation files, so automatic updates never overwrite your setup.
</details>

<details>
<summary><b>4. Windows says "running scripts is disabled on this system" when running <code>.ps1</code> files. What should I do?</b></summary>

That is PowerShell's default execution policy prompt. Either let your Agent run the setup for you via Agent-Native Mode above, or include `-ExecutionPolicy Bypass` (e.g., `powershell -ExecutionPolicy Bypass -File .\install.ps1`) to run safely for the current session without changing system-wide settings.
</details>

<details>
<summary><b>5. Which Linux desktops are supported? Does Wayland work?</b></summary>

Linux support is tested for **Ubuntu / Debian X11 (Xorg) desktop sessions**. If your machine defaults to Wayland, click the gear icon on the Ubuntu login screen and switch to **Ubuntu on Xorg** for full close-button interception and fast screen control.
</details>

<details>
<summary><b>6. Something isn't working—how do I check what's missing?</b></summary>

Simply ask Antigravity: *"Run `scripts/doctor.py` in antigravity-toolkit to diagnose and fix my setup."* Or run `python scripts/doctor.py` (`python3 scripts/doctor.py` on Linux) from the repo root to inspect prerequisites, browser connection status, and each module's configuration with step-by-step fix instructions.
</details>

---

## 🤝 Community & Contributing

Antigravity Toolkit is an open, evolving collection of community enhancements—and everyone is welcome to jump in:
- Open an Issue to report a bug or paste your `doctor.py` output for troubleshooting;
- Propose ideas for new modules and quality-of-life improvements you'd love to see next;
- Team up with your Agent to improve docs, cross-platform support, or new modules and open a Pull Request!

Check out **[CONTRIBUTING.md](./CONTRIBUTING.md)** for a beginner-friendly guide, or switch to **[简体中文文档 (README.md)](./README.md)**.

If Antigravity Toolkit saved an active AI task or spared you from logging back into browser tabs, please consider giving the repo a **Star ⭐**!

---

## 🙏 Acknowledgments & Open-Source Credits

The `computer_use` (Faster Desktop & Browser Control) module integrates, patches, and draws inspiration from the following great open-source projects (this repository distributes only original tools, setup scripts, and incremental `.patch` files; upstream repositories are fetched on demand during setup under their respective licenses):

- **[CursorTouch/Windows-MCP](https://github.com/CursorTouch/Windows-MCP)** (MIT): Serves as the foundation for Windows native desktop & vision control, enhanced via `windows-mcp-speedup.patch` for pure-vision speedups and active-window-only scanning. Our Linux X11 engine (`linux-gui-mcp`) also aligns with its MCP tool interface and mouse-shake human takeover design.
- **[AB498/computer-control-mcp](https://github.com/AB498/computer-control-mcp)** (MIT): Serves as the foundation for cross-platform local OCR and hardware-accelerated window capture, enhanced via `computer-control-mcp-opti.patch` with HiDPI scaling awareness, single-window coordinate offset restoration, and multi-monitor bounds clamping.
- **[ChromeDevTools/chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp)** (Apache-2.0): Powers direct browser control, wrapped here with cross-platform auto-connect launchers and routing rules to reuse your everyday logged-in Chrome / Edge tabs.
- Special thanks as well to [RapidOCR](https://github.com/RapidAI/RapidOCR), [windows-capture](https://github.com/NiiightmareXD/windows-capture), [python-mss](https://github.com/BoboTiG/python-mss), [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), and [Astral uv](https://github.com/astral-sh/uv).

---

## 📄 License

Original content in this repository is released under the [MIT License](./LICENSE). Free to use, modify, and share.
