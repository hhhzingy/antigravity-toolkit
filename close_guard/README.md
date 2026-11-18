# 防误关系统托盘守护 (`close_guard`)

让 Google Antigravity 拥有像微信、Slack 或 Clash 一样的**“点击关闭按钮自动收进系统托盘”**体验，从此告别手滑关窗导致 AI 任务前功尽弃！

> 返回主目录总览：[../README.md](../README.md) · English Overview: [../README_EN.md](../README_EN.md)

---

## 一、它解决什么日常痛点？

在使用 Antigravity 让 AI 帮你写代码、跑长耗时分析或调用多个后台智能体（Subagents）时，你一定遇到过这种崩溃瞬间：
- 想顺手整理桌面，习惯性点了窗口右上角的 **`✕`**，或者按下了 **`Alt + F4`**（Linux 下还有 **`Ctrl + Q`**）；
- 没有任何二次确认，整个 Antigravity 窗口瞬间被关掉——**正在思考的 AI 回复、跑了一半的后台命令和子智能体全部中断！**

装上 `close_guard` 之后：
1. **手滑点 `✕` 不再掉线**：点击右上角 `✕` 或按 `Alt + F4`（Linux 含 `Ctrl + Q`）时，主窗口会**安静地隐藏到系统托盘**，任务栏不再占位置，而后台所有的 AI 对话、终端命令与多智能体任务 **100% 继续全速运行**。
2. **一键秒回桌面**：需要查看进度时，点一下系统托盘里的 Antigravity 图标，窗口立刻回到屏幕最前方。
3. **只有点 `Quit` 才真正退出**：只有当你明确在托盘图标菜单中点击 **`Quit`** 时，才会彻底关闭 Antigravity。

---

## 二、为什么它足够安全省心？

- **零修改官方安装文件，不怕版本自动更新**：
  很多第三方补丁会去拆解或篡改软件安装目录里的核心包（如 `app.asar`），不仅容易触发安全告警，而且每次 Antigravity 自动升级后就会失效。`close_guard` 完全运行在用户空间，**不碰任何官方安装文件**——无论 Antigravity 升级多少次，托盘保护始终自动生效。
- **平时几乎不占任何电脑资源**：
  采用操作系统原生的事件通知机制（空闲时 **CPU 占用 `0.0%`**），Windows 版无需安装任何额外第三方 Python 库，且只针对 Antigravity 主窗口生效，绝不影响你电脑上的任何其他软件或文件弹窗。
- **随时一键干净卸载**：
  如果卸载时你的 Antigravity 窗口正藏在托盘里，卸载脚本也会先自动把窗口弹回桌面，绝不会把窗口“弄丢”。

---

## 三、一键安装与卸载

> **新手推荐**：你也可以直接运行仓库根目录的一键交互向导（Windows 运行 [`../install.ps1`](../install.ps1)，Linux 运行 [`../install.sh`](../install.sh)），输入 `2` 即可自动完成安装！

### Windows 10 / 11

打开 **PowerShell**，进入本仓库目录后运行：

```powershell
# 一键安装（立即后台生效，并自动开启开机自启）
powershell -ExecutionPolicy Bypass -File .\close_guard\install_close_guard.ps1
```

如果以后不想用了，随时一行命令彻底卸载：

```powershell
# 一键停止并彻底卸载
powershell -ExecutionPolicy Bypass -File .\close_guard\uninstall_close_guard.ps1
```

---

### Ubuntu / Debian Linux（X11 桌面环境）

打开终端，进入本仓库目录后运行：

```bash
# 一键检查依赖、自检并启用登录自启服务
bash ./close_guard/install_close_guard.sh
```

随时一行命令彻底卸载：

```bash
# 一键停止服务并清理卸载
bash ./close_guard/uninstall_close_guard.sh
```

---

## 四、日常怎么用？

安装完成后无需重启电脑，立即生效：

- **隐藏到后台**：像平时一样点击 Antigravity 右上角的 **`✕`**，或按下 **`Alt + F4`**（Linux 下还支持 **`Ctrl + Q`**）。首次隐藏时右下角/右上角会弹出一条温馨提示，告知你程序仍在后台运行。
- **恢复主窗口**：
  - **Windows**：**左键单击**右下角托盘里的 Antigravity 图标（或右键菜单点击 `显示 Antigravity 窗口`）。
  - **Ubuntu / Linux**：点击屏幕顶栏右上角的 Antigravity 托盘图标并选择 **`显示 Antigravity 窗口`**（也可以在图标上**按下鼠标中键**一键直达恢复）。
- **快速给对话开分支（联动彩蛋）**：
  如果你同时安装了[对话分支工具 (`branch_conversation`)](../branch_conversation/README.md)，右键点击托盘图标并选择 **`分支克隆对话 (Branch)...`**，就能随时呼出可视化界面，从任意一轮历史聊天分叉出新对话！
- **彻底退出 Antigravity**：
  右键点击系统托盘图标，选择最下方的 **`Quit`**，即可干净退出所有 Antigravity 窗口与后台进程。下次重新打开 Antigravity 时，托盘守护会自动再次就位。

---

## 五、常见问题解答 (FAQ)

<details>
<summary><b>Q1：Windows 点击 ✕ 隐藏后，右下角没看到 Antigravity 图标怎么办？</b></summary>

Windows 默认会把新出现的托盘图标收进右下角任务栏的 **`^`（展开隐藏的图标）** 小箭头里。
- 点一下右下角的 `^` 箭头就能看到它；
- 你也可以按住那个图标，直接把它**拖拽到任务栏外侧常驻显示**，以后左键一点就能秒开！
</details>

<details>
<summary><b>Q2：Antigravity 自动更新到新版本后，需要重新运行安装脚本吗？</b></summary>

**完全不需要！** 因为 `close_guard` 不修改 Antigravity 的任何安装文件，软件升级后托盘守护依然原样工作。
</details>

<details>
<summary><b>Q3：在 Antigravity 里打开“选择文件 / 保存文件”小窗口时，点小窗口的 ✕ 也会把主程序藏起来吗？</b></summary>

**不会。** 守护脚本会自动区分主工作窗口与临时的子对话框/小工具窗，关闭“打开文件”等弹窗完全保持系统原样。
</details>

<details>
<summary><b>Q4：Ubuntu / Linux 下支持 Wayland 吗？</b></summary>

Linux 版基于标准 X11 窗口事件机制实现（在 Ubuntu 登录界面的右下角齿轮图标中选择 **Ubuntu on Xorg** 即可获得完整体验）。你也可以随时运行以下命令做一次无打扰的本地自检（不会影响正在运行的对话）：
```bash
/usr/bin/python3 ./close_guard/antigravity_close_guard_linux.py --self-test
```
或者在仓库根目录运行 `python scripts/doctor.py`（见 [`../scripts/doctor.py`](../scripts/doctor.py)）一键检查整体运行状态。
</details>

---

## 六、目录文件说明

| 文件 | 适用系统 | 作用说明 |
| :--- | :--- | :--- |
| [`antigravity_close_guard.pyw`](./antigravity_close_guard.pyw) | Windows 10/11 | Windows 无黑框后台托盘守护主程序（纯标准库实现，适配多显示器高分屏缩放） |
| [`install_close_guard.ps1`](./install_close_guard.ps1) | Windows 10/11 | Windows 一键安装、平滑升级与开机自启配置脚本 |
| [`uninstall_close_guard.ps1`](./uninstall_close_guard.ps1) | Windows 10/11 | Windows 一键停止守护、自动恢复隐藏窗口并清理脚本 |
| [`antigravity_close_guard_linux.py`](./antigravity_close_guard_linux.py) | Linux (X11) | Ubuntu / Debian 系统托盘守护主程序（内置 `--self-test` 自检模式） |
| [`install_close_guard.sh`](./install_close_guard.sh) | Linux (X11) | Linux 自动检查依赖、自检并配置 `systemd --user` 登录自启脚本 |
| [`uninstall_close_guard.sh`](./uninstall_close_guard.sh) | Linux (X11) | Linux 一键停止服务并清理卸载脚本 |
