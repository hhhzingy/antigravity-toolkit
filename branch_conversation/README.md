# 历史对话任意轮次分支工具 (`branch_conversation`)

为 Google Antigravity 补齐**“从任意一轮历史聊天一键开分支（Fork / Branch）”**的能力——既不弄乱原来的长对话，也不必重头复制粘贴几千字的背景上下文，还能**免重启直接打开新分支继续聊**！

> 返回主目录总览：[../README.md](../README.md) · English Overview: [../README_EN.md](../README_EN.md)

---

## 一、它解决什么日常痛点？

跟 AI 深度协作做项目时，我们经常遇到这几种尴尬场景：
- **想同时试探方案 A 和方案 B**：前面已经跟 AI 聊了 10 轮，把项目结构、需求和报错信息都交代得清清楚楚了。现在你想让它分别试两种完全不同的实现思路，但如果直接在原对话里接着聊，两条思路就会混在一起互相污染；
- **聊歪了想“读档重来”，但又舍不得删掉后面的参考记录**：比如第 1～8 轮方向都很棒，第 9～12 轮走入了死胡同，你想回到第 8 轮结束那一刻重新出发，同时保留原对话备查；
- **界面自带的 `Split with New` 并不会继承上下文**：Antigravity 自带的分屏新建功能只是在右边开了一个空白的新对话，并不会把之前的历史记录带过去。

有了 `branch_conversation`：
- **像玩游戏“读档开新支线”一样简单**：选中任意一个历史对话、点选你想保留到第几轮结束（比如保留第 `1..8` 轮，自动忽略第 9 轮之后的内容），一键生成一条完全独立的新对话！
- **免重启秒见、秒开**：新创建的分支会立即出现在 Antigravity 左侧会话列表最上方和左上角搜索框里（Windows 下点击创建后还会**自动帮你切进新分支页面**），全程无需重启软件，也不会打断任何正在后台运行的任务。

---

## 二、为什么它足够安全省心？

- **不修改任何 Antigravity 安装文件**：
  完全独立工作在用户目录，不改动软件本体，因此 Antigravity 日常自动升级后功能依然稳定可用。
- **原对话 100% 零改动、热备份不冲突**：
  采用 SQLite 官方的在线热备份机制读取源对话快照——即使源对话里 AI 正在思考或执行任务，也能安全克隆出一个处于干净“待输入”状态的新对话，绝不会损坏或干扰原对话。
- **纯 Python 标准库实现**：
  无需配置复杂的第三方依赖包，Windows 与 Ubuntu / Linux 开箱即用。

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

如果你同时安装了[防误关系统托盘守护 (`close_guard`)](../close_guard/README.md)，连命令行都不用开：
1. **右键点击**系统托盘里的 Antigravity 图标，选择 **`分支克隆对话 (Branch)...`**；
2. **左边面板（1. 选择源对话）**：所有对话按你的 `📁 项目名称` 自动归类展示，一眼就能找到目标对话；
3. **右边面板（2. 选择克隆截止轮次）**：清晰列出每一轮你发出的消息时间与内容摘要：
   - 想完整复制整条对话？直接保持默认选中的 `(最新)` 那一轮；
   - 想回到第 5 轮重来？鼠标点一下 **`第 5 轮`**（代表保留第 1～5 轮，自动忽略第 6 轮及之后的聊天）；
4. 底部可以自定义新分支标题（留空则自动加上 `[分支]` 标记），点击右下角 **`立即创建并打开新对话`** 即可！

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

# 克隆第 1..5 轮生成新分支
python3 "$HOME/mcp-gui-workspace/antigravity-branch/branch_conversation.py" --title "my-web-app" --turn 5
```

---

## 五、常见问题解答 (FAQ)

<details>
<summary><b>Q1：在新分支里继续聊天、修改计划，会影响原来的对话吗？</b></summary>

**完全不会！** 新分支拥有独立的对话 ID、独立的数据库与独立的对话产物目录（`brain/<UUID>/`），和原对话彻底隔离、互不干扰。需要留意的是，如果你的代码仓库本身在同一个本地文件夹里，让两个对话同时改同一份代码文件自然还是会改到同一个磁盘目录上。
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
| [`branch_conversation.py`](./branch_conversation.py) | Windows / Linux | 对话分支核心工具（同时支持双栏可视化 GUI 界面与命令行调用） |
| [`SKILL.md`](./SKILL.md) | Windows / Linux | 注册给 Antigravity 的全局技能定义，支持在聊天框直接用自然语言开分支 |
| [`install_branch_tool.ps1`](./install_branch_tool.ps1) | Windows 10/11 | Windows 一键部署工具与全局技能脚本 |
| [`uninstall_branch_tool.ps1`](./uninstall_branch_tool.ps1) | Windows 10/11 | Windows 一键清理工具与全局技能脚本 |
| [`install_branch_tool.sh`](./install_branch_tool.sh) | Linux | Linux 一键部署工具与全局技能脚本 |
| [`uninstall_branch_tool.sh`](./uninstall_branch_tool.sh) | Linux | Linux 一键清理工具与全局技能脚本 |
