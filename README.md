# Antigravity Toolkit

**让 Google Antigravity 更好用、更顺手、更安心的三合一实用增强工具包（支持 Windows & Ubuntu/Linux）**

简体中文 | **[English](./README_EN.md)** · [30 秒快速上手](#-30-秒快速上手) · [三大功能详解](#-三大实用功能详解) · [使用与卸载](#-日常使用与随时卸载指南) · [常见问题](#-常见问题排查-faq) · [参与贡献](./CONTRIBUTING.md)

---

## 👋 为什么做这个工具包？

Google Antigravity 已经是非常强大的 AI 编程与桌面助手，但在日常高频使用中，很多朋友都会遇到三个让人头疼的小烦恼：

1. **操控浏览器总是丢登录，看屏幕又慢又卡**：想让 AI 帮忙处理网页任务，它却新开了一个空白浏览器，你平时登录好的账号全没了；看一眼桌面往往要等好几秒，遇到微信、游戏界面或远程桌面更是经常“看不见、点不准”；中途你想自己动一下鼠标，还可能被锁住干等半分钟。
2. **随手点错右上角 `✕`，跑了一半的任务瞬间中断**：AI 正在后台认真跑任务、改代码，你只是想把窗口收起来让桌面清爽一点，顺手点了右上角 `✕` 或按了 `Alt+F4`，结果整个程序直接关闭，正在进行的对话和后台任务全断了。
3. **聊到一半想换个方向试一试，却没法“存档分叉”**：和 AI 讨论了十几轮，突然想回到第 5 轮换一种思路试试，但又舍不得删掉后面的聊天记录——原生的分屏功能只会开一个空白新对话，并不会帮你把前 5 轮的上下文带过去。

**Antigravity Toolkit** 就是为了贴心解决这三件事而准备的。它**完全不修改 Antigravity 的官方核心安装文件**（因此每次官方自动更新后依然稳稳生效），三项增强既可以一键全装，也可以只挑你最需要的那一个单独安装，随时都能一行命令干净卸载。哪怕你平时很少敲命令，跟着下面的向导半分钟就能搞定！

---

## ✨ 三大实用功能详解

| 功能模块 | 解决的核心痛点 | 给你带来的日常体验提升 | 模块文档 |
| :--- | :--- | :--- | :--- |
| **⚡ 桌面与浏览器极速控制**<br>`computer_use` | 新开空白浏览器丢失登录态、桌面截图慢、特殊窗口识别不到、抢鼠标控制权 | • **直连日常 Chrome / Edge**：直接操控你已经打开并登录好的标签页，免重复扫码登录<br>• **0.1 秒极速看屏 + 本地文字识别**：桌面响应快如闪电，连微信、游戏、远程桌面也能看清点准<br>• **晃动鼠标瞬间接管**：想自己操作时轻轻晃一下鼠标，AI 立即停手让路，停手 2 秒自动恢复 | [查看详情](./computer_use/README.md) |
| **🛡️ 防误关系统托盘守护**<br>`close_guard` | 误点右上角 `✕` 或按 `Alt+F4` 直接杀掉正在工作的 AI 任务 | • **像微信一样安心收进托盘**：点 `✕` 或按 `Alt+F4`（Linux 含 `Ctrl+Q`）时自动把窗口藏进系统托盘，后台 AI 对话与终端任务 **100% 不断连继续跑**<br>• **零占用、不怕更新**：空闲时 CPU 占用 `0.0%`，不改动官方安装文件；只有点托盘菜单里的 **`Quit`** 才会真正退出 | [查看详情](./close_guard/README.md) |
| **🌿 历史对话任意轮次分支**<br>`branch_conversation` | 长对话想从中间某一轮换思路探索，却无法保留前文分叉 | • **对话“时光机存档”**：可视化界面按项目（Project）清晰分组，点选任意历史轮次即可一键分叉出新对话<br>• **免重启 0.5 秒直达**：点击按钮后无需重启软件，自动创建并直接跳转到新分支接着聊；也支持在聊天框直接让 AI 帮你分叉 | [查看详情](./branch_conversation/README.md) |

---

## 🚀 30 秒快速上手

> **准备事项**：电脑上只需装有 **Git** 和 **Python 3.10+**（如果使用“桌面与浏览器极速控制”，还会用到 **Node.js 20+**）。不确定电脑里有没有装齐？完全不用担心——直接运行下面的安装向导或自检工具，它会用大白话告诉你缺什么、怎么装！

### 第一步：下载本工具包

打开终端（Windows 打开 **PowerShell**，Ubuntu/Linux 打开 **Terminal**），运行：

```bash
git clone https://github.com/hhhzingy/antigravity-toolkit.git
cd antigravity-toolkit
```

### 第二步：启动一键交互式安装向导（推荐新手）

根据你的操作系统运行对应命令：

- **Windows (PowerShell)**：
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\install.ps1
  ```
- **Ubuntu / Debian Linux**：
  ```bash
  bash ./install.sh
  ```

运行后你会看到一个清爽的交互式数字菜单：
- 输入 **`A`**：一键安装全部三项增强（最省心推荐）
- 输入 **`1` / `2` / `3`**：只单独安装你想要的那一项功能
- 输入 **`D`**：运行环境与安装状态健康体检
- 输入 **`U`**：一键停止并卸载系统托盘守护

<details>
<summary>💡 进阶用法：喜欢直接用命令行参数一键执行？（点击展开）</summary>

如果你习惯跳过交互菜单直接安装（例如在多台电脑上快速配置），可以直接传入命令行参数：

**Windows ([install.ps1](./install.ps1))**：
```powershell
# 一键安装全部三项功能
powershell -ExecutionPolicy Bypass -File .\install.ps1 -All

# 仅安装指定模块（1 = 桌面与浏览器极速控制，2 = 防误关托盘守护，3 = 对话分支工具）
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Module 2

# 直接运行健康自检
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Doctor
```

**Ubuntu / Linux ([install.sh](./install.sh))**：
```bash
# 一键安装全部三项功能
bash ./install.sh --all

# 仅安装指定模块（1 / 2 / 3）
bash ./install.sh --module 2

# 直接运行健康自检
bash ./install.sh --doctor
```
</details>

### 第三步：运行健康自检，确认一切就绪

任何时候想检查环境是否配置妥当，都可以运行内置的跨平台体检脚本 [scripts/doctor.py](./scripts/doctor.py)：

```bash
python scripts/doctor.py
```

*(提示：在 Ubuntu/Linux 上如果提示找不到 `python`，请运行 `python3 scripts/doctor.py`)*

它会逐项检查软件依赖、浏览器连接开关和三个模块的安装状态，并在发现未完成项时给出清晰的一步步提示。

---

## 📖 日常使用与随时卸载指南

你可以随时只使用其中一个模块，或者把不需要的模块干干净净地卸载掉：

### 1. ⚡ 桌面与浏览器极速控制（`computer_use`）

- **单独安装**：
  - Windows：`powershell -ExecutionPolicy Bypass -File .\computer_use\setup_other_device.ps1`
  - Linux：`bash ./computer_use/setup_linux.sh`
- **日常怎么用（只需点 2 下开启浏览器直连）**：
  1. 打开你平时用的 **Chrome**，在地址栏输入 `chrome://inspect/#remote-debugging` 并回车（如果用 **Edge**，则输入 `edge://inspect/#remote-debugging`），勾选页面上的 **Enable remote debugging**（开启远程调试）。
  2. 回到 Antigravity，打开 **MCP Servers** 面板点击 **Refresh**（刷新）。
  3. 现在你就可以直接在聊天框里对 AI 说：*“帮我看看我浏览器里刚打开的那篇文档讲了什么”* 或 *“帮我在桌面软件里点击设置按钮”*！当 AI 操作鼠标时，如果你想自己接手，**随时晃动一下鼠标**就能立刻拿回控制权。
- **如何卸载**：
  - 本模块的所有运行文件都整齐地存放在你的个人文件夹 `~/mcp-gui-workspace`（Windows 下为 `%USERPROFILE%\mcp-gui-workspace`）中，配置位于 `~/.gemini/config/mcp_config.json`。删除 `mcp_config.json` 中对应的服务项并移除 `mcp-gui-workspace` 文件夹即可恢复如初。更多说明请见 [computer_use/README.md](./computer_use/README.md)。

### 2. 🛡️ 防误关系统托盘守护（`close_guard`）

- **单独安装**：
  - Windows：`powershell -ExecutionPolicy Bypass -File .\close_guard\install_close_guard.ps1`
  - Linux：`bash ./close_guard/install_close_guard.sh`
- **日常怎么用**：
  - **自动生效**：安装完成后会自动在后台静默运行，并设置为开机登录自启，平时无需手动操心。
  - **隐藏到托盘**：当你点击 Antigravity 窗口右上角 `✕` 或按 `Alt+F4`（Linux 下含 `Ctrl+Q`）时，窗口会立刻安静收进系统托盘，正在工作的 AI 任务毫发无损。
  - **重新唤出窗口**：Windows 下**左键单击**右下角系统托盘里的 Antigravity 图标；Ubuntu/Linux 下点击顶栏右上角托盘图标并选择 **`显示 Antigravity 窗口`**（或在图标上按一下鼠标中键）。
  - **真正退出程序**：想彻底关闭 Antigravity 时，右键点击系统托盘图标，选择 **`Quit`** 即可。
- **如何卸载（一键还原）**：
  - Windows：`powershell -ExecutionPolicy Bypass -File .\close_guard\uninstall_close_guard.ps1`
  - Linux：`bash ./close_guard/uninstall_close_guard.sh`
  - 运行后会立即停止守护并清除开机自启项。更多说明请见 [close_guard/README.md](./close_guard/README.md)。

### 3. 🌿 历史对话任意轮次分支工具（`branch_conversation`）

- **单独安装**：
  - Windows：`powershell -ExecutionPolicy Bypass -File .\branch_conversation\install_branch_tool.ps1`
  - Linux：`bash ./branch_conversation/install_branch_tool.sh`
- **日常怎么用（三种顺手方式任你选）**：
  1. **从系统托盘一键呼出（最直观）**：右键点击系统托盘里的 Antigravity 图标，选择 **`分支克隆对话 (Branch)...`**。在弹出的窗口左侧选择一段对话，右侧点选你想保留到第几轮，最后点击 **`立即创建并打开新对话`**——不到一秒钟就会自动跳进新分支对话！
  2. **直接在聊天框用自然语言告诉 AI**：安装时已自动为你配好全局技能，直接在任意对话里对 AI 说：*“把当前对话分支一份，忽略最后一条消息”* 或 *“把这个对话克隆到第 5 轮”*，AI 就能自动帮你建好分支。
  3. **命令行随时打开可视化窗口**：
     - Windows：`python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\branch_conversation.py" --gui`
     - Linux：`python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --gui`
- **如何卸载（一键还原）**：
  - Windows：`powershell -ExecutionPolicy Bypass -File .\branch_conversation\uninstall_branch_tool.ps1`
  - Linux：`bash ./branch_conversation/uninstall_branch_tool.sh`
  - 更多命令行高级参数与说明请见 [branch_conversation/README.md](./branch_conversation/README.md)。

---

## ❓ 常见问题排查 (FAQ)

<details>
<summary><b>1. 开启 Chrome / Edge 远程调试怎么操作？会影响平时上网和账号安全吗？</b></summary>

非常安全，也只需点两下：
1. 复制 `chrome://inspect/#remote-debugging`（Edge 浏览器复制 `edge://inspect/#remote-debugging`），粘贴到浏览器地址栏后按回车。
2. 勾选页面中的 **Enable remote debugging** 复选框即可。

这个开关只允许**你本机当前登录账号**下的程序连接浏览器，不会向局域网或互联网开放任何端口，你的账号密码与日常浏览完全不受影响。
</details>

<details>
<summary><b>2. Windows 下点了右上角 <code>✕</code> 把窗口收起来后，右下角没看到图标去哪找？</b></summary>

Windows 默认会把新加入的托盘图标收纳进折叠区。请点击任务栏右下角输入法/时间旁边的 **向上小箭头 `^`**，就能在里面看到 Antigravity 图标啦！你可以用鼠标按住它直接拖到任务栏外侧，以后每次都能一眼看见、单击唤起。
</details>

<details>
<summary><b>3. Antigravity 官方自动升级新版本后，我需要重新安装一遍吗？</b></summary>

**完全不需要！** 本工具包里的所有功能都是以外部助手的方式配合工作，绝不改动 Antigravity 自身的任何安装包文件。无论官方怎么静默升级，你的防误关托盘、浏览器极速直连和对话分支工具都会一直稳稳生效。
</details>

<details>
<summary><b>4. Windows 运行脚本时提示“在此系统上禁止运行脚本”怎么办？</b></summary>

这是 Windows PowerShell 默认的脚本执行策略提示。只需像上面教程里写的那样，加上 `-ExecutionPolicy Bypass` 参数运行（例如 `powershell -ExecutionPolicy Bypass -File .\install.ps1`），就可以在不修改系统全局安全设置的前提下顺利完成安装。
</details>

<details>
<summary><b>5. Linux 支持哪些系统环境？Wayland 会话可以使用吗？</b></summary>

目前 Linux 版已在 **Ubuntu / Debian 系列的 X11 (Xorg) 桌面会话**下完成全面适配测试。如果你的 Ubuntu 默认处于 Wayland 会话，建议在系统登录界面点击右下角的小齿轮图标，切换为 **Ubuntu on Xorg** 登录，即可获得完整的托盘防误关与极速屏幕操控体验。
</details>

<details>
<summary><b>6. 遇到某个功能没生效，不知道哪里缺了配置怎么办？</b></summary>

直接在项目根目录运行 `python scripts/doctor.py`（Linux 下为 `python3 scripts/doctor.py`）。它会帮你快速扫描依赖工具、浏览器远程调试状态以及三个模块的文件配置，并给出对应的解决步骤。
</details>

---

## 🤝 欢迎一起让它变得更好！

这是一个面向所有 Antigravity 用户的开源小工具箱。无论你是：
- 在使用中遇到了小问题、或者觉得哪句教程写得不够好懂，想提一个 Issue 告诉我们；
- 脑海里冒出了让 Antigravity 更好用的新点子；
- 还是想动手修复 Bug、完善跨平台适配并提交 Pull Request；

我们都非常欢迎你的加入！哪怕你以前从未参与过开源项目，也可以先看看我们为新手准备的 **[参与贡献指南 (CONTRIBUTING.md)](./CONTRIBUTING.md)**。如果你希望阅读英文版说明，请访问 **[English README (README_EN.md)](./README_EN.md)**。

如果这个小工具包帮你省下了重新登录浏览器的时间，或者救回了你差点误关的 AI 任务，欢迎在右上角点亮一颗 **Star ⭐** 支持一下！

---

## 📄 开源协议

本项目基于 [MIT License](./LICENSE) 开源，你可以自由地使用、修改和分享。
