# macOS 桌面 GUI 与浏览器极速操控规则

1. **网页与浏览器操作优先使用 `chrome-devtools` MCP（非桌面截图点击）**：
   - 当任务涉及打开网页、搜索、抓取或操控 Web 应用（如 GitHub、Bilibili、各类云控制台）时，优先调用 `chrome-devtools` MCP 工具（`list_pages`、`select_page`、`new_page`、`navigate_page`、`take_snapshot`、`click`、`fill` 等）直接通过 CDP 精准控制本地日常 Chrome / Edge / Arc / Brave（完整保留登录态）。

2. **macOS 桌面软件优先使用多模态极速视觉（Vision）**：
   - 调用 `macos-uia-mcp` 的 `Snapshot` 时，优先使用默认 `{"use_ui_tree": false, "use_vision": true}` 直接基于 1:1 逻辑坐标截图执行 `Click`（无需换算 Retina 2x 缩放）；
   - 当目标窗口为微信、游戏、远程桌面等无原生 Accessibility 节点的自绘界面且需精确文字坐标时，切换调用 `macos-ocr-mcp` 进行本地离线 OCR 识别后再点击。

3. **快捷键与 `open` 直达优先，禁止冗余动作**：
   - 能用 `open -a "System Settings"`、`open "x-apple.systempreferences:com.apple.Displays-Settings.extension"` 或 `Shortcut`（如 `cmd+space`、`cmd+l`）一步直达的操作，优先命令直达，不要每一步重复截图。
