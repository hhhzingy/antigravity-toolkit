# 参与贡献指南 / Contributing to Antigravity Toolkit

感谢你对 **Antigravity Toolkit** 的关注与喜爱！🎉  
无论你是刚刚接触命令行的新朋友，还是经验丰富的开发者，你的每一次反馈、点子和改进都能帮助更多 Antigravity 用户获得更顺手的使用体验。

*(English guide is available right below: [Jump to English Section](#-english-contribution-guide))*

---

## 🌟 你可以用哪些方式参与？（不写代码也超棒！）

参与开源并不一定要提交复杂的代码，以下每一件事都对项目非常有价值：

1. **反馈使用体验或报告问题（提 Issue）**：
   - 安装或使用过程中遇到了报错？告诉我们你的操作系统版本（如 Windows 11 或 Ubuntu 22.04）以及运行 `python scripts/doctor.py` 的输出，方便快速定位。
2. **让教程对新手更友好**：
   - 如果你觉得 [README.md](./README.md)、[README_EN.md](./README_EN.md) 或某个子模块说明里有哪句话不够好懂、漏掉了某个小细节，非常欢迎直接修改文档！
3. **分享新点子（Feature Request）**：
   - 日常使用 Antigravity 时还有哪些让你觉得“要是能这样就好了”的小痛点？欢迎开一个 Issue 一起讨论。
4. **提交代码改进（Pull Request）**：
   - 修复 Bug、优化交互提示、改进多显示器或更多 Linux 发行版的兼容性。

---

## 🗂️ 仓库目录结构速览

为了让你一眼找到想修改的地方，整个仓库按功能清晰拆分为以下部分：

- [install.ps1](./install.ps1) / [install.sh](./install.sh)：Windows 与 Linux 根目录一键交互式安装向导
- [scripts/doctor.py](./scripts/doctor.py)：跨平台运行环境与模块状态健康自检工具（仅依赖 Python 标准库）
- [computer_use/README.md](./computer_use/README.md)：⚡ 桌面与浏览器极速控制模块（配置模板、补丁与一键部署脚本）
- [close_guard/README.md](./close_guard/README.md)：🛡️ 防误关系统托盘守护模块（Windows `.pyw` 与 Linux X11 `.py` 守护程序及启停脚本）
- [branch_conversation/README.md](./branch_conversation/README.md)：🌿 历史对话任意轮次分支模块（可视化克隆器、CLI 与全局 AI 技能）
- **新增扩展模块**：欢迎以独立子目录（配套一键安装/卸载脚本与 `README.md`）的形式贡献新的实用功能，或让你的 Antigravity Agent 协助完成编码与自检！

---

## 🛠️ 第一次提交 Pull Request 的极简步骤

如果你是第一次在 GitHub 上提交 PR，跟着下面 5 步走就能轻松完成：

1. **Fork 本仓库**：点击本页面右上角的 **Fork** 按钮，把仓库复制一份到你自己的 GitHub 账号下。
2. **下载到本地并新建分支**：
   ```bash
   git clone https://github.com/<你的GitHub用户名>/antigravity-toolkit.git
   cd antigravity-toolkit
   git checkout -b feat/my-improvement
   ```
3. **进行修改并在本地自检**：
   - 如果修改了 Python 脚本，建议用 `-B` 参数运行语法与健康检查（避免在目录里留下 `__pycache__` 缓存文件夹）：
     ```bash
     python -B -m py_compile scripts/doctor.py
     python -B scripts/doctor.py
     ```
4. **提交前检查隐私与通用性（非常重要 ✅）**：
   - **零个人隐私路径**：请勿在代码、配置或文档中硬编码任何真实的个人电脑用户名、主机名、私人目录路径或真实的本地聊天 `.db` 文件。涉及用户目录时，请始终使用动态变量（如 Python 的 `Path.home()`、PowerShell 的 `$env:USERPROFILE`、Bash 的 `$HOME`），文档示例统一使用 `<YOUR_USERNAME>` 或 `my-web-app`。
   - **保持平实友好的文档语气**：尽量用直观、通俗的语言解释操作步骤，照顾非技术背景的新手用户。
5. **推送到你的仓库并发起 Pull Request**：
   ```bash
   git add .
   git commit -m "docs: clarify Chrome remote debugging steps for beginners"
   git push origin feat/my-improvement
   ```
   随后打开 GitHub 页面，点击 **Compare & pull request** 即可！

---

## 🌍 English Contribution Guide

Thank you for helping make **Antigravity Toolkit** better for everyone! 🎉  
Contributions of all kinds are warmly welcomed—even if this is your very first open-source contribution.

### Ways You Can Contribute

- **Report bugs or UX friction**: Open an Issue describing your OS (e.g., Windows 11 or Ubuntu 22.04) and paste the output of `python scripts/doctor.py` (with any personal info removed if applicable).
- **Improve documentation**: Spot a confusing step in [README_EN.md](./README_EN.md) or [README.md](./README.md)? Clarifications, screenshots, and translations are hugely appreciated.
- **Suggest new ideas**: Share workflow pain points or new enhancement modules you would love to see added next.
- **Submit code & fixes**: Improve cross-platform polish, installer UX, DPI / desktop compatibility, or contribute new standalone modules (feel free to pair with your Antigravity Agent!).

### Quick Pull Request Workflow

1. **Fork** this repository on GitHub and clone your fork locally:
   ```bash
   git clone https://github.com/<YOUR_GITHUB_USERNAME>/antigravity-toolkit.git
   cd antigravity-toolkit
   git checkout -b feat/my-improvement
   ```
2. **Make your changes & test locally**:
   - Use `python -B` when running checks so Python doesn't leave `__pycache__` folders behind:
     ```bash
     python -B -m py_compile scripts/doctor.py
     python -B scripts/doctor.py
     ```
3. **Privacy & Beginner-Friendliness Checklist ✅**:
   - **Zero hardcoded personal paths or device names**: Always resolve paths dynamically (`Path.home()`, `$env:USERPROFILE`, `$HOME`) and use generic placeholders like `<YOUR_USERNAME>` or `my-web-app` in documentation. Never commit personal `.db` conversation files.
   - **Keep docs approachable**: Explain *why* a step matters in friendly, plain language so non-technical users feel right at home.
4. **Commit, push, and open a Pull Request** on GitHub!

---

## 📄 开源协议声明 / License

提交贡献即表示你同意将所提交的内容按照本项目的 [MIT License](./LICENSE) 协议进行开源授权。  
By contributing to Antigravity Toolkit, you agree that your contributions will be licensed under its [MIT License](./LICENSE).
