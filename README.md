# Antigravity Toolkit

**让 Google Antigravity 更顺手、更安心的模块化实用增强工具集（支持 Windows & Ubuntu/Linux）**

简体中文 | **[English](./README_EN.md)** · [🤖 懒人模式](#-懒人模式直接让-antigravity-自己读仓库自己装推荐) · [✨ 功能模块一览](#-功能模块一览) · [🚀 手动快速上手](#-手动快速上手) · [📖 日常使用与卸载](#-日常使用与卸载) · [❓ 常见问题](#-常见问题排查-faq) · [🤝 参与贡献](./CONTRIBUTING.md)

> 💡 **零侵入官方核心文件 · 官方自动更新不失效 · 模块按需选装 · 随时干净卸载**

---

## 👋 为什么做这个工具集？

日常高频使用 Google Antigravity 时，很多朋友都会遇到这些卡手瞬间：

- **操控网页总丢登录、看桌面又慢又抢鼠标**：默认新开空白浏览器得重新扫码，桌面截图慢、微信/游戏/远程桌面识别不准，想自己动下鼠标还要干等。
- **随手点错 `✕` 或按 `Alt+F4`，跑了一半的任务直接中断**：只是想收起窗口让桌面清爽一点，结果整个程序退出，后台正在干活的 Agent 瞬间断连。
- **长对话聊到一半想换思路，却没法从中间某轮“读档分叉”**：原生分屏只能开空白新对话，无法把前几轮讨论好的上下文带过去。
- **持续扩展的实用工具箱**：围绕真实高频痛点模块化演进，既可一键全装，也可只挑需要的功能单独启用。

---

## 🤖 懒人模式：直接让 Antigravity 自己读仓库、自己装（推荐）

在 Agent 时代，你不需要自己背命令或逐行啃教程——**直接把下面这段话复制进 Antigravity 对话框**，让你的 Agent 自动检查系统环境、按需安装并完成自检：

```text
请读取 https://github.com/hhhzingy/antigravity-toolkit ，结合我的系统环境帮我完成里面的优化安装并自检；如果有需要我选择或手动点一下开关的步骤，直接用简单的话告诉我。
```

- **选装、排障、卸载也只需一句话**：只想装某几个功能、遇到报错或日后想卸载？直接用大白话告诉你的 Agent 即可（例如：`“只帮我装防误关托盘和对话分支”` 或 `“帮我卸载 antigravity-toolkit 里的托盘守护”`）。

---

## ✨ 功能模块一览

| 模块 | 解决痛点 | 核心体验 | 详细说明 |
| :--- | :--- | :--- | :--- |
| **⚡ 桌面与浏览器极速控制**<br>`computer_use` | 新开空白浏览器丢登录、看屏慢、特殊窗口点不准、抢鼠标控制权 | 直连日常已登录 Chrome/Edge；`~0.1s` 极速看屏 + 微信/游戏本地 OCR；**晃动鼠标瞬间接管**（停手 2 秒自动恢复） | [查看详情](./computer_use/README.md) |
| **🛡️ 防误关系统托盘守护**<br>`close_guard` | 误点右上角 `✕` 或按 `Alt+F4` 直接杀掉后台运行中的 AI 任务 | 点关闭键自动收进系统托盘，后台对话与终端任务 **100% 不断连**；空闲 `0.0%` CPU，仅点托盘 `Quit` 才真正退出 | [查看详情](./close_guard/README.md) |
| **🌿 历史对话任意轮次分支**<br>`branch_conversation` | 长对话想从中间某轮换方向探索，却无法保留前文存档 | 按项目分组的可视化“对话时光机”，任选历史轮次 `~0.5s` 免重启直达新分支；也支持在对话框一句话让 AI 帮你分叉 | [查看详情](./branch_conversation/README.md) |

> 💬 **想了解底层原理或进阶配置？** 直接问你的 Agent，或点进表格右侧的模块目录查看详情。

---

## 🚀 手动快速上手

如果你习惯自己在终端敲命令安装（需 **Git** 与 **Python 3.10+**，`computer_use` 另需 **Node.js 20+**；不确定装没装也没关系，自检工具会直接提示）：

**1. 克隆仓库**

```bash
git clone https://github.com/hhhzingy/antigravity-toolkit.git
cd antigravity-toolkit
```

**2. 启动交互式安装向导**（输入 `A` 一键安装全部模块，输入编号按需单装，输入 `D` 健康体检）

- **Windows (PowerShell)**：
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\install.ps1
  ```
- **Ubuntu / Debian Linux**：
  ```bash
  bash ./install.sh
  ```

<details>
<summary>💡 习惯命令行参数一键直达？（点击展开）</summary>

- **Windows ([install.ps1](./install.ps1))**：`powershell -ExecutionPolicy Bypass -File .\install.ps1 -All`（按需单装用 `-Module 2`，体检用 `-Doctor`）
- **Linux ([install.sh](./install.sh))**：`bash ./install.sh --all`（按需单装用 `--module 2`，体检用 `--doctor`）
</details>

**3. 运行健康自检**（检查依赖环境、浏览器直连开关与各模块状态）

```bash
python scripts/doctor.py   # Ubuntu/Linux 若无 python 别名请运行 python3 scripts/doctor.py
```

---

## 📖 日常使用与卸载

所有模块均独立运行在你的个人目录下，随时可单独启用或干净卸载（不懂操作细节？直接让你的 Agent 代劳，或点进模块文档）：

### ⚡ 桌面与浏览器极速控制（`computer_use` · [模块文档](./computer_use/README.md)）
- **首次开启直连（点 2 下）**：在日常 Chrome 地址栏打开 `chrome://inspect/#remote-debugging`（Edge 打开 `edge://inspect/#remote-debugging`）勾选 **Enable remote debugging**，再到 Antigravity 的 **MCP Servers** 点击 **Refresh**。
- **日常体验**：直接让 Agent 查看已打开的网页或点击桌面软件；AI 操作鼠标时**轻轻晃一下鼠标**即可立即接管控制权。
- **单独装卸**：安装运行 `computer_use/setup_other_device.ps1`（Win）或 `computer_use/setup_linux.sh`（Linux）；卸载只需移除 `~/.gemini/config/mcp_config.json` 中对应服务项并删除 `~/mcp-gui-workspace`。

### 🛡️ 防误关系统托盘守护（`close_guard` · [模块文档](./close_guard/README.md)）
- **无感守护**：安装后自动后台运行并设为登录自启；点 `✕` 或按 `Alt+F4`（Linux 含 `Ctrl+Q`）自动隐藏到托盘，后台任务照常运行。
- **唤回与退出**：Windows 左键单击托盘图标唤回窗口（Linux 点击顶栏图标选 `显示 Antigravity 窗口` 或按鼠标中键）；右键托盘选 **`Quit`** 才会彻底退出。
- **一键卸载**：Windows 运行 `powershell -ExecutionPolicy Bypass -File .\close_guard\uninstall_close_guard.ps1`；Linux 运行 `bash ./close_guard/uninstall_close_guard.sh`。

### 🌿 历史对话任意轮次分支（`branch_conversation` · [模块文档](./branch_conversation/README.md)）
- **随手分叉**：右键系统托盘图标点 **`分支克隆对话 (Branch)...`** 选轮次一键跳进新对话；或直接在聊天框对 Agent 说 *“把当前对话克隆到第 5 轮”*；也可运行 `~/mcp-gui-workspace/antigravity-branch/branch_conversation.py --gui`。
- **一键卸载**：Windows 运行 `powershell -ExecutionPolicy Bypass -File .\branch_conversation\uninstall_branch_tool.ps1`；Linux 运行 `bash ./branch_conversation/uninstall_branch_tool.sh`。

---

## ❓ 常见问题排查 (FAQ)

<details>
<summary><b>1. 开启 Chrome / Edge 远程调试怎么操作？会影响平时上网和账号安全吗？</b></summary>

非常安全，只需点两下：
1. 复制 `chrome://inspect/#remote-debugging`（Edge 复制 `edge://inspect/#remote-debugging`），粘贴到浏览器地址栏并回车。
2. 勾选页面中的 **Enable remote debugging** 复选框即可。

该开关仅允许**你本机当前登录账号**下的本地程序连接浏览器，不会向局域网或公网暴露任何端口，账号密码与日常浏览完全不受影响。
</details>

<details>
<summary><b>2. Windows 下点了右上角 <code>✕</code> 把窗口收起来后，右下角没看到图标去哪找？</b></summary>

Windows 默认会把新加入的托盘图标收进折叠区。点击任务栏右下角时间/输入法旁的 **向上小箭头 `^`** 就能看到 Antigravity 图标；按住它直接拖到任务栏外侧，以后就能一眼看见、单击唤起。
</details>

<details>
<summary><b>3. Antigravity 官方自动升级新版本后，我需要重新安装一遍吗？</b></summary>

**完全不需要！** 工具集中的所有模块均以外部协作与标准配置方式工作，绝不改动 Antigravity 自身的安装包文件。无论官方如何静默升级，已安装的增强模块都会持续稳定生效。
</details>

<details>
<summary><b>4. Windows 运行脚本时提示“在此系统上禁止运行脚本”怎么办？</b></summary>

这是 Windows PowerShell 默认的执行策略提示。你可以直接用上方的“懒人模式”让 Agent 帮你处理，或者像手动教程那样加上 `-ExecutionPolicy Bypass` 参数运行（例如 `powershell -ExecutionPolicy Bypass -File .\install.ps1`），无需改动系统全局安全设置。
</details>

<details>
<summary><b>5. Linux 支持哪些桌面环境？Wayland 会话可以使用吗？</b></summary>

目前 Linux 版已在 **Ubuntu / Debian 系列的 X11 (Xorg) 桌面会话**下完成全面测试。若系统默认处于 Wayland 会话，建议在登录界面点击右下角齿轮图标切换为 **Ubuntu on Xorg** 登录，以获得完整的防误关拦截与极速屏幕操控体验。
</details>

<details>
<summary><b>6. 遇到某个功能没生效，不知道哪里缺了配置怎么办？</b></summary>

最省心的办法是直接对 Antigravity 说：*“帮我运行 antigravity-toolkit 的 doctor.py 检查一下哪里没配好并修复”*。你也可以在项目根目录手动运行 `python scripts/doctor.py`（Linux 为 `python3 scripts/doctor.py`），它会逐项扫描依赖工具、浏览器远程调试状态及各模块配置，并给出一步步修复指引。
</details>

---

## 🤝 欢迎一起让它变得更好！

这是一个面向所有 Antigravity 用户的开放式增强工具集，后续还会持续加入更多实用模块。无论你是：
- 在使用中遇到了问题，想把 `doctor.py` 的诊断结果贴到 Issue 里反馈；
- 日常使用 Antigravity 时冒出了“要是能这样就好了”的新模块点子；
- 还是想让自己的 Agent 帮忙改改代码、完善文档或跨平台兼容并发起 Pull Request；

我们都非常欢迎你的加入！第一次参与开源也没关系，可以先阅读 **[参与贡献指南 (CONTRIBUTING.md)](./CONTRIBUTING.md)**；英文说明请见 **[English README (README_EN.md)](./README_EN.md)**。

如果这个工具集帮你省下了重复扫码登录的时间，或者救回了差点被误关的 AI 任务，欢迎在右上角点亮一颗 **Star ⭐** 支持一下！

---

## 📄 开源协议

本项目基于 [MIT License](./LICENSE) 开源，你可以自由地使用、修改和分享。
