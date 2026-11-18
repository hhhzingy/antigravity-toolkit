# Linux (Ubuntu / X11) 桌面 GUI 与浏览器极速操控规则

1. **网页与浏览器操作优先使用 `chrome-devtools` MCP（非 Computer Use）**：
   - 当任务涉及打开网页、搜索、抓取或操控 Web 应用（如 GitHub、Bilibili、Cloudflare、Google Cloud 等）时，优先调用 `chrome-devtools` MCP 工具（`list_pages`、`select_page`、`new_page`、`navigate_page`、`take_snapshot`、`click`、`fill` 等）直接通过 CDP / DOM 树精准控制本地浏览器（支持直连已开启远程调试的 Google Chrome 或 Microsoft Edge，完整保留登录态），不使用桌面级鼠标截图模拟。

2. **桌面软件优先使用多模态极速视觉（Vision）**：
   - 调用 `linux-uia-mcp` 的 `Snapshot` 时，默认且优先使用 `{"use_ui_tree": false, "use_vision": true}` 纯视觉极速模式（耗时 < 0.08s），直接看截图坐标执行 `Click` / `Type` / `Shortcut`；
   - 如需原生控件精确坐标，再传入 `{"use_ui_tree": true, "use_vision": true}`（仅扫描当前 X11 焦点窗口的 AT-SPI2 控件树，自动过滤 `gnome-shell` 顶栏、Dock 与后台窗口，耗时 < 0.15s）；
   - 若目标窗口为无 AT-SPI2 控件树的自绘 UI（如微信 Linux、远程桌面 RustDesk、游戏、Canvas 画布）且需精确文字坐标，切换使用 `linux-ocr-mcp` 的 `take_screenshot_with_ocr` 进行本地 RapidOCR 文字框定位后再点击。

3. **禁止冗余动作**：
   - 使用命令或快捷键启动软件后，不要再重复调用 `App(mode="launch")`；
   - 画面内已清晰可见的多个连续操作点，直接根据多模态画面连续调用 `Click` / `Type`，不要在每一步点击前机械重复调用 `Snapshot`。

4. **CLI / URI / 快捷键直达优先**：
   - 能用 Linux 命令、`xdg-open`、`gnome-control-center <panel>`（如 `gnome-control-center display` 打开显示设置）或快捷键（如文件管理器中 `Ctrl+L` 聚焦地址栏）直达的操作，优先一行命令或快捷键直达，避免逐级点菜单。
