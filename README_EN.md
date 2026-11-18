# Antigravity Toolkit

**Three friendly, zero-intrusion enhancements that make Google Antigravity faster, safer, and easier to use every day (Windows & Ubuntu/Linux)**

**[简体中文](./README.md)** | English · [30-Second Quick Start](#-30-second-quick-start) · [What's Inside](#-three-everyday-enhancements) · [Usage & Uninstall](#-step-by-step-usage--clean-uninstall) · [FAQ](#-faq--troubleshooting) · [Contributing](./CONTRIBUTING.md)

---

## 👋 Why Antigravity Toolkit?

Google Antigravity is an awesome AI coding and desktop assistant, but if you use it every day, you have probably bumped into three frustrating little pain points:

1. **Fresh blank browsers lose your logins, and screen control feels sluggish**: When you ask the AI to check a webpage or click around an app, default setups often launch a brand-new blank browser profile (forcing you to log in to everything all over again), take several seconds per screenshot, struggle with apps like WeChat, games, or remote desktops, and lock out your mouse for half a minute when you try to step in.
2. **One accidental click on `X` kills active AI work**: An agent is halfway through a long task in the background, you click the top-right `X` or press `Alt+F4` just to tidy up your desktop, and the whole window closes—interrupting every running conversation and background terminal job on the spot.
3. **No easy way to branch a conversation from an earlier turn**: Twelve turns into a great brainstorming session, you want to go back to Turn 5 and explore a different direction without losing Turns 6–12. Built-in split view opens an empty chat rather than carrying over your history up to that point.

**Antigravity Toolkit** solves all three problems cleanly. Best of all, it **never modifies Antigravity's core installation files**—meaning your enhancements survive every automatic Antigravity update, can be installed individually or all at once, and can be uninstalled cleanly whenever you like. Even if you are brand new to the command line, the interactive setup wizard gets you up and running in about 30 seconds!

---

## ✨ Three Everyday Enhancements

| Enhancement | Everyday Pain Point Solved | What You Get | Module Guide |
| :--- | :--- | :--- | :--- |
| **⚡ Faster Desktop & Browser Control**<br>`computer_use` | Blank browser sessions with lost logins, slow screenshots, unreadable custom apps, 30s mouse lockouts | • **Use your already-open Chrome / Edge tabs** with all your active logins intact<br>• **~0.1s screen vision + offline local OCR** so even WeChat, games, and remote desktops work smoothly<br>• **Instant mouse-shake takeover**: wiggle your mouse anytime to take control back immediately (resumes smoothly 2s after you let go) | [Read Guide](./computer_use/README.md) |
| **🛡️ Close-to-Tray Guard**<br>`close_guard` | Accidentally clicking `X` or pressing `Alt+F4` and terminating running AI tasks | • **Minimizes quietly to your system tray** when you click `X` or press `Alt+F4` (plus `Ctrl+Q` on Linux), keeping active AI agents and background tasks **100% alive**<br>• **`0.0%` idle CPU & update-proof**: touches zero Antigravity core files, and exits completely only when you choose **`Quit`** from the tray menu | [Read Guide](./close_guard/README.md) |
| **🌿 Visual Conversation Branching**<br>`branch_conversation` | Wanting to try a new idea from Turn K of a chat without losing later turns | • **Time-machine checkpoints for your chats** (like Codex fork): browse chats grouped neatly by Project, pick any historical turn, and fork in one click<br>• **Opens in ~0.5s with zero restarts**: jumps straight into your new branched chat—or just ask the AI in plain language to branch the chat for you! | [Read Guide](./branch_conversation/README.md) |

---

## 🚀 30-Second Quick Start

> **What you need**: Just **Git** and **Python 3.10+** (plus **Node.js 20+** if you install Faster Desktop & Browser Control). Not sure what is installed on your computer? Don't worry—our interactive installer and health checker will tell you in plain English what is missing and how to install it!

### Step 1: Download the Toolkit

Open **PowerShell** (on Windows) or **Terminal** (on Ubuntu/Linux) and run:

```bash
git clone https://github.com/hhhzingy/antigravity-toolkit.git
cd antigravity-toolkit
```

### Step 2: Launch the One-Click Interactive Installer (Recommended)

Run the launcher for your operating system:

- **Windows (PowerShell)**:
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\install.ps1
  ```
- **Ubuntu / Debian Linux**:
  ```bash
  bash ./install.sh
  ```

An interactive menu will appear right away:
- Press **`A`** to install all three enhancements at once (recommended!)
- Press **`1`**, **`2`**, or **`3`** to pick only the individual tool(s) you want
- Press **`D`** to run a friendly environment & status health check
- Press **`U`** to stop and uninstall the Close-to-Tray Guard

<details>
<summary>💡 Power-user tip: Prefer non-interactive CLI flags? (Click to expand)</summary>

You can also run [install.ps1](./install.ps1) or [install.sh](./install.sh) directly with flags—handy for scripting or setting up a new machine quickly:

**Windows**:
```powershell
# Install all 3 enhancements
powershell -ExecutionPolicy Bypass -File .\install.ps1 -All

# Install a single module (1 = Desktop & Browser, 2 = Close Guard, 3 = Conversation Branching)
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Module 2

# Run the health checker
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Doctor
```

**Ubuntu / Linux**:
```bash
# Install all 3 enhancements
bash ./install.sh --all

# Install a single module (1 / 2 / 3)
bash ./install.sh --module 2

# Run the health checker
bash ./install.sh --doctor
```
</details>

### Step 3: Run the Health Check (`doctor.py`)

Anytime you want to verify that everything is set up properly, run [scripts/doctor.py](./scripts/doctor.py):

```bash
python scripts/doctor.py
```

*(On Ubuntu/Linux, use `python3 scripts/doctor.py` if `python` is not aliased.)*

It checks your prerequisites, browser remote-debugging toggle, and each module's status—printing clear, step-by-step instructions if anything needs attention.

---

## 📖 Step-by-Step Usage & Clean Uninstall

Every enhancement lives cleanly inside your user home folder and can be installed or removed independently at any time:

### 1. ⚡ Faster Desktop & Browser Control (`computer_use`)

- **Install individually**:
  - Windows: `powershell -ExecutionPolicy Bypass -File .\computer_use\setup_other_device.ps1`
  - Linux: `bash ./computer_use/setup_linux.sh`
- **How to use day-to-day (2 clicks to connect your browser)**:
  1. Open your everyday **Chrome** and visit `chrome://inspect/#remote-debugging` (or `edge://inspect/#remote-debugging` in **Microsoft Edge**), then check **Enable remote debugging**.
  2. In Antigravity, open **MCP Servers** and click **Refresh**.
  3. Ask the AI things like *"Summarize the article open in my current Chrome tab"* or *"Click the settings button in my desktop app."* Whenever you want to use the mouse yourself, **simply shake your mouse** and the AI yields control immediately!
- **How to uninstall**:
  - All files live inside `~/mcp-gui-workspace` (`%USERPROFILE%\mcp-gui-workspace` on Windows) and `~/.gemini/config/mcp_config.json`. Remove the server entries from `mcp_config.json` and delete `~/mcp-gui-workspace` whenever you want a clean slate. Full details in [computer_use/README.md](./computer_use/README.md).

### 2. 🛡️ Close-to-Tray Guard (`close_guard`)

- **Install individually**:
  - Windows: `powershell -ExecutionPolicy Bypass -File .\close_guard\install_close_guard.ps1`
  - Linux: `bash ./close_guard/install_close_guard.sh`
- **How to use day-to-day**:
  - **Works automatically**: Once installed, it starts quietly in the background and launches automatically when you sign in.
  - **Minimize to tray**: Click the top-right `X` button or press `Alt+F4` (plus `Ctrl+Q` on Linux) and Antigravity hides neatly into your system tray while all active AI chats and background tasks keep running.
  - **Bring the window back**: On Windows, **left-click** the Antigravity tray icon. On Ubuntu/Linux, click the top-bar tray icon and select **`显示 Antigravity 窗口`** (or middle-click the icon).
  - **Quit completely**: Right-click the tray icon and click **`Quit`** whenever you genuinely want to exit Antigravity.
- **How to uninstall (one command)**:
  - Windows: `powershell -ExecutionPolicy Bypass -File .\close_guard\uninstall_close_guard.ps1`
  - Linux: `bash ./close_guard/uninstall_close_guard.sh`
  - Stops the background helper immediately and removes login auto-start. Full details in [close_guard/README.md](./close_guard/README.md).

### 3. 🌿 Visual Conversation Branching (`branch_conversation`)

- **Install individually**:
  - Windows: `powershell -ExecutionPolicy Bypass -File .\branch_conversation\install_branch_tool.ps1`
  - Linux: `bash ./branch_conversation/install_branch_tool.sh`
- **How to use day-to-day (pick whichever feels easiest)**:
  1. **From the system tray (easiest)**: Right-click the Antigravity tray icon and click **`分支克隆对话 (Branch)...`**. Pick a conversation on the left, select the turn you want to branch from on the right, and click **`立即创建并打开新对话`**—your new branched chat opens right in front of you in ~0.5 seconds!
  2. **Ask the AI in plain language**: A global skill is installed automatically, so you can simply type *"Branch this conversation and drop the last message"* or *"Clone this chat up to turn 5"* right inside Antigravity.
  3. **Launch the visual tool from terminal**:
     - Windows: `python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\branch_conversation.py" --gui`
     - Linux: `python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --gui`
- **How to uninstall (one command)**:
  - Windows: `powershell -ExecutionPolicy Bypass -File .\branch_conversation\uninstall_branch_tool.ps1`
  - Linux: `bash ./branch_conversation/uninstall_branch_tool.sh`
  - Full CLI options and details in [branch_conversation/README.md](./branch_conversation/README.md).

---

## ❓ FAQ & Troubleshooting

<details>
<summary><b>1. How do I enable Chrome or Edge remote debugging in 2 clicks? Is it safe?</b></summary>

Yes, it only takes two clicks and stays strictly local to your user account:
1. Paste `chrome://inspect/#remote-debugging` (or `edge://inspect/#remote-debugging` for Microsoft Edge) into your browser's address bar and press Enter.
2. Check the **Enable remote debugging** box.

This only allows local tools running under your own OS user session to talk to the browser—nothing is exposed to your network or the internet.
</details>

<details>
<summary><b>2. I clicked <code>X</code> on Windows, where did the Antigravity tray icon go?</b></summary>

Windows tucks newly added tray icons inside the taskbar overflow menu by default. Click the small **upward arrow `^`** near your clock in the bottom-right corner of the taskbar—you will spot the Antigravity icon right there! Tip: drag and drop it onto the main taskbar so it stays visible in one glance.
</details>

<details>
<summary><b>3. Do I need to reinstall anything after Antigravity updates itself?</b></summary>

**No!** None of the tools in Antigravity Toolkit patch or alter Antigravity's internal program files. Automatic updates won't overwrite your setup.
</details>

<details>
<summary><b>4. Windows says "running scripts is disabled on this system" when running <code>.ps1</code> files. What should I do?</b></summary>

That is PowerShell's default script execution policy prompt. Run the command with `-ExecutionPolicy Bypass` just as shown above (for example: `powershell -ExecutionPolicy Bypass -File .\install.ps1`), which runs the installer safely for that session without changing your global Windows settings.
</details>

<details>
<summary><b>5. Which Linux desktops are supported? Does Wayland work?</b></summary>

Linux support is designed and tested for **Ubuntu / Debian X11 (Xorg) desktop sessions**. If your Ubuntu machine defaults to Wayland, click the gear icon in the bottom-right corner of your Ubuntu login screen and select **Ubuntu on Xorg** for full window-close interception and fast screen control.
</details>

<details>
<summary><b>6. Something isn't working as expected—how do I check what's missing?</b></summary>

Run `python scripts/doctor.py` (or `python3 scripts/doctor.py` on Linux) from the repository root. It inspects your installed prerequisites, browser connection, and module files, and tells you exactly how to fix anything that is missing.
</details>

---

## 🤝 Community & Contributing

Everyone is welcome here—whether you are a first-time beginner or a seasoned developer! You can help by:
- Opening an Issue to report a bug, ask a question, or point out a step in the docs that could be clearer;
- Sharing ideas for new quality-of-life improvements for Antigravity;
- Submitting a Pull Request to improve cross-platform support, UX, or translations.

Check out **[CONTRIBUTING.md](./CONTRIBUTING.md)** for a friendly step-by-step guide to getting involved, or switch to **[简体中文文档 (README.md)](./README.md)** if you prefer reading in Chinese.

If Antigravity Toolkit saved you from losing an active AI task or logging back into your browser tabs, consider giving the repo a **Star ⭐**!

---

## 📄 License

Released under the [MIT License](./LICENSE). Free to use, modify, and share.
