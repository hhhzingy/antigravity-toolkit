# 历史对话分支与跨用户分享工具 (`branch_conversation` + `share_conversation`)

为 Google Antigravity 补齐**“任意轮次分支克隆（Fork / Branch）”**与**“跨用户/跨系统无损导出与导入续聊（`.agyshare` / Markdown，支持完整 Swarm 多智能体团队迁移）”**两大核心能力——不弄乱原对话、无需重启软件、支持 Windows / macOS / Linux 跨平台接力！

> 返回主目录总览：[../README.md](../README.md) · English Overview: [../README_EN.md](../README_EN.md)

---

## 一、它解决什么日常痛点？

跟 AI 深度协作做项目时，我们经常遇到这几种场景：
- **想同时试探方案 A 和方案 B**：前面已经跟 AI 聊了 10 轮，把项目结构、需求和报错信息都交代得清清楚楚了。现在你想让它分别试两种完全不同的实现思路，但如果直接在原对话里接着聊，两条思路就会混在一起互相污染；
- **聊歪了想“读档重来”，但又舍不得删掉后面的参考记录**：比如第 1～8 轮方向都很棒，第 9～12 轮走入了死胡同，你想回到第 8 轮结束那一刻重新出发，同时保留原对话备查；
- **想把一段深度调试对话（甚至一整支 `/swarm` 多智能体团队）发给同事或另一台电脑续聊**：传统做法只能零散截图或复制聊天记录，新窗口里的 AI 根本不知道之前查过哪些文件、Swarm 团队讨论板上达成过哪些结论。

有了本模块：
- **本地“读档分叉”**：选中任意历史对话及目标轮次，一键生成完全独立的新分支，免重启秒见、秒开；
- **跨用户 `.agyshare` 无损接力（含 Swarm 完整迁移）**：一键把主对话连同 `/swarm` 团队成员、嵌套子代理（Subagents）、Swarm 共享讨论板与侧边提问（Side Questions）打包成 `.agyshare` 便携归档（自动脱敏本机路径与 API Key/Token），对方在 Windows / macOS / Linux 导入后可绑定自己的本地代码目录直接接着聊（也支持一键导出精简版 `--lite` 或人类可读的 `.md` 交接文档）。

---

## 二、为什么它足够安全省心？

- **不修改任何 Antigravity 安装文件**：
  完全独立工作在用户目录，不改动软件本体，因此 Antigravity 日常自动升级后功能依然稳定可用。
- **原对话 100% 零改动、热备份不冲突**：
  采用 SQLite 官方的在线热备份机制读取源对话快照——即使源对话里 AI 正在思考或执行任务，也能安全克隆出一个处于干净“待输入”状态的新对话，绝不会损坏或干扰原对话。
- **多智能体（Swarm / Subagents）与侧边提问彻底隔离、防串台**：
  即使源对话使用过 `/swarm` 多智能体协作、后台子智能体或侧边提问（Side Questions），分支工具也会严格按白名单过滤运行态目录、重新生成独立的会话初始化状态并隔离重映射所有子会话标识，绝不会误唤醒或串入原对话的后台智能体。
- **纯 Python 标准库实现**：
  核心克隆逻辑无需安装第三方 Python 包，Windows、macOS 与 Ubuntu / Linux 开箱即用（同时兼容 Antigravity 桌面版、IDE 与 `agy` CLI）。

---

## 三、一键安装与卸载

> **新手推荐**：你也可以直接运行仓库根目录的一键交互向导（Windows 运行 [`../install.ps1`](../install.ps1)，Linux 运行 [`../install.sh`](../install.sh)），输入 `3` 即可自动完成安装！

安装脚本会同时为你部署**可视化/命令行分支工具**以及 **Antigravity 全局 AI 技能 (`branch-conversation`)**。

### Windows 10 / 11

打开 **PowerShell**，进入本仓库目录后运行：

```powershell
# 一键安装分支工具与全局 AI 技能
powershell -ExecutionPolicy Bypass -File .\branch_conversation\install_branch_tool.ps1
```

如需卸载清理：

```powershell
# 一键卸载（注：你之前已经创建好的所有分支对话都会完好保留！）
powershell -ExecutionPolicy Bypass -File .\branch_conversation\uninstall_branch_tool.ps1
```

---

### Ubuntu / Debian Linux

打开终端，进入本仓库目录后运行：

```bash
# 一键安装分支工具与全局 AI 技能（若缺少图形界面库会自动提示或安装 python3-tk）
bash ./branch_conversation/install_branch_tool.sh
```

如需卸载清理：

```bash
# 一键卸载（此前已创建的分支对话均完好保留）
bash ./branch_conversation/uninstall_branch_tool.sh
```

---

## 四、三种超顺手的日常用法

### 用法 1：从系统托盘打开可视化点选界面（最推荐新手！）

如果同时安装了[防误关系统托盘守护 (`close_guard`)](../close_guard/README.md)，连命令行都不用开：
1. **右键点击**系统托盘里的 Antigravity 图标，在弹出的圆角菜单卡片中点击 **`对话分支克隆...`**（Linux 下为 `分支克隆对话 (Branch)...`）；
2. **左侧卡片（源对话列表）**：支持顶部胶囊搜索框实时过滤项目或对话标题，所有对话按 `📁 项目名称` 自动归类并显示计数角标；
3. **右侧卡片（选择分叉节点 + 完整消息预览）**：清晰列出每一轮消息的时间、步骤与摘要，并在下方实时展示**选中轮次的完整发送内容预览**（长消息不再被截断）：
   - 想完整复制整条对话？保持默认选中的 `[最新]` 那一轮（右上角显示绿色 `完整克隆全部 N 轮`）；
   - 想回到第 5 轮重来？点击 **`第 5 轮`**（右上角实时提示 `保留第 1 ~ 5 轮 · 忽略后续 M 轮`）；
4. 底部胶囊输入框可自定义新分支标题（留空则自动按下方预览提示附加 `[分支]` 标记），点击右下角深色主按钮 **`立即创建并打开新对话 →`** 即可！

---

### 用法 2：直接在聊天框用自然语言让 AI 帮你开分支

安装脚本已自动将 [`SKILL.md`](./SKILL.md) 注册为全局技能，因此你可以在任意 Antigravity 聊天窗口里直接用大白话吩咐 AI：

- *“把当前对话分支一份，忽略最后一条消息”*
- *“帮我把当前对话完整克隆一个新分支，准备测试另一套前端方案”*
- *“把标题包含 my-web-app 的对话克隆到第 6 轮结束为止”*

AI 会自动调用本工具完成克隆，并在回复中给你一个可点击的对话链接，鼠标一点即可跳进新分支！

---

### 用法 3：命令行精准调用（适合进阶用户与快捷键绑定）

**Windows (PowerShell)：**

```powershell
# 打开可视化图形点选窗口
pythonw "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\branch_conversation.py" --gui

# 查看某个对话的每一轮消息列表（按标题关键词匹配）
python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\branch_conversation.py" --title "my-web-app" --list-turns

# 将最近活跃的对话忽略最后 1 轮，并自动在 Antigravity 中打开新分支
python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\branch_conversation.py" --drop-last 1 --open

# 指定对话 UUID，只保留第 1..5 轮并自定义新标题
python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\branch_conversation.py" --id <CONVERSATION_UUID> --turn 5 --new-title "my-web-app [方案B]" --open
```

**Ubuntu / Linux (Bash)：**

```bash
# 打开可视化图形点选窗口
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --gui

# 查看指定对话的轮次列表
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --title "my-web-app" --list-turns

# 克隆第 1..5 轮生成新分支并自动打开
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --title "my-web-app" --turn 5 --open
```

---

### 用法 4：跨用户分享与导入对话（`.agyshare` / Markdown，支持 Swarm 团队迁移）

#### 方式 A：在可视化 Studio 窗口一键点选（最简单）
打开分支 Studio 窗口（托盘右键 → `对话分支克隆...`），使用右上角新增的两个按钮：
- **`↗ 导出分享`**：自动识别当前对话关联的 Swarm 成员、子代理与侧边提问数量；可选导出 `.agyshare` 完整接力包（默认勾选迁移 Swarm 团队 + 自动脱敏 API Key/Token）或 `.md` 交接文档。
- **`↙ 导入分享`**：选择别人发来的 `.agyshare` 文件，实时预览包内标题、轮次与 Swarm 成员数，选择归属的本地项目与代码工作区目录（可选），点击导入即可免重启直接打开续聊！

#### 方式 B：在聊天框一句话让 AI 帮你导出 / 导入
- *“帮我把当前对话连同 Swarm 团队导出为 .agyshare 发给同事”*
- *“帮我把桌面上的 `debug_handoff.agyshare` 导入到本地 Antigravity 并绑定到当前代码目录”*

#### 方式 C：命令行调用（`share_conversation.py`）

```powershell
# Windows (PowerShell) — macOS / Linux 将 python 替换为 python3、$env:USERPROFILE 替换为 $HOME
# 1. 导出完整对话（自动打包关联的 Swarm 团队、子代理、讨论板与侧边提问，自动脱敏本机路径与密钥）
python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\share_conversation.py" export --title "my-web-app" -o .\handoff.agyshare

# 2. 精简导出（仅主对话、不包含 Swarm/子代理，且可选截断到第 N 轮）
python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\share_conversation.py" export --title "my-web-app" --lite --turn 8 -o .\handoff.agyshare

# 3. 导出通用可读 Markdown 交接文档（附带 Swarm 团队讨论板记录）
python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\share_conversation.py" export --title "my-web-app" --format md -o .\handoff.md

# 4. 预览收到的 .agyshare 分享包内容
python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\share_conversation.py" inspect .\handoff.agyshare

# 5. 导入收到的 .agyshare（自动重写跨系统路径与 UUID 关系图、重建 FTS5 索引并自动打开）
python "$env:USERPROFILE\mcp-gui-workspace\antigravity-branch\share_conversation.py" import .\handoff.agyshare --workspace "D:\Projects\my-web-app" --open
```

> **安全与隐私保障**：导出过程采用 SQLite 只读在线热备份（`?mode=ro`），绝不影响正在运行的对话与进程；自动通过 Protobuf 变长字段安全重写发送者的用户名、主目录和工作区路径，并自动扫描脱敏常见 API Key / GitHub PAT / AWS Key / 私钥；Swarm 成员导入后自动归一化为 `STOPPED` 待唤醒状态，新用户发送消息或 `@成员名` 即可在本地安全唤醒续聊。

---

## 五、常见问题解答 (FAQ)

<details>
<summary><b>Q1：在新分支里继续聊天、修改计划，会影响原来的对话吗？如果原对话开了 Swarm 多智能体呢？</b></summary>

**完全不会！** 新分支拥有独立的对话 ID、独立的初始化状态、独立的数据库与独立的对话产物目录（`brain/<UUID>/`）；原对话中的 `/swarm` 团队成员、后台子智能体（Subagents）、消息队列与侧边提问（Side Questions）都会被彻底物理隔离并重映射，绝不会误唤醒或串台。需要留意的是，如果你的代码仓库本身在同一个本地文件夹里，让两个对话同时改同一份代码文件自然还是会改到同一个磁盘目录上。
</details>

<details>
<summary><b>Q2：为什么克隆完不需要重启 Antigravity 就能在左边列表看到？</b></summary>

因为工具在复制对话记录的同时，会自动同步更新 Antigravity 本地侧边栏与全局搜索所使用的全文索引表（SQLite FTS5）。因此创建完的一瞬间，左侧列表与顶部 `🔍` 搜索框就能实时看到这条新分支。
</details>

<details>
<summary><b>Q3：如果原对话里最新一轮 AI 还在思考运行中，可以克隆吗？</b></summary>

**可以！** 可视化界面会自动把尚未结束的那一轮标记为 `(进行中)`，并默认帮你选中上一轮已完成的节点；即使克隆正在运行的对话，生成的新分支也会自动重置为干净的空闲待输入状态，随时可以发新消息。
</details>

<details>
<summary><b>Q4：卸载这个工具之后，我以前克隆出来的分支对话会消失吗？</b></summary>

**不会消失。** 所有已创建的分支本身就是标准的 Antigravity 本地对话，即使卸载了分支工具，这些对话依然永久保留在你的 Antigravity 历史列表中。
</details>

<details>
<summary><b>Q5：Linux 下运行 <code>--gui</code> 提示未检测到 <code>tkinter</code> 怎么办？</b></summary>

部分精简版 Linux 系统默认未预装 Python 的图形界面模块，只需在终端运行一行命令即可补齐：
```bash
# Ubuntu / Debian
sudo apt-get update && sudo apt-get install -y python3-tk
```
你也可以随时在仓库根目录运行 `python scripts/doctor.py`（见 [`../scripts/doctor.py`](../scripts/doctor.py)）进行环境自检。
</details>

---

## 六、目录文件说明

| 文件 | 适用系统 | 作用说明 |
| :--- | :--- | :--- |
| [`branch_conversation.py`](./branch_conversation.py) | Windows / macOS / Linux | 对话分支核心工具（含现代 Studio 双栏可视化 GUI 与命令行，集成导出/导入入口） |
| [`share_conversation.py`](./share_conversation.py) | Windows / macOS / Linux | 跨用户 `.agyshare` / Markdown 分享引擎（支持 Swarm/子代理/侧边提问全树无损迁移与脱敏） |
| [`SKILL.md`](./SKILL.md) | Windows / macOS / Linux | 注册给 Antigravity 的全局技能定义，支持在聊天框直接用自然语言开分支或导出/导入分享包 |
| [`install_branch_tool.ps1`](./install_branch_tool.ps1) | Windows 10/11 | Windows 一键部署分支/分享工具与全局技能脚本 |
| [`uninstall_branch_tool.ps1`](./uninstall_branch_tool.ps1) | Windows 10/11 | Windows 一键清理分支/分享工具与全局技能脚本 |
| [`install_branch_tool.sh`](./install_branch_tool.sh) | macOS / Linux | macOS & Linux 一键部署分支/分享工具与全局技能脚本 |
| [`uninstall_branch_tool.sh`](./uninstall_branch_tool.sh) | macOS / Linux | macOS & Linux 一键清理分支/分享工具与全局技能脚本 |
