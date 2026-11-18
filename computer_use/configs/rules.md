# Windows 桌面 GUI 与浏览器极速操控规则

1. **网页与浏览器操作优先使用 `chrome-devtools` MCP（非 Computer Use）**：
   - 当任务涉及打开网页、搜索、抓取或操控 Web 应用（如 Bilibili、GitHub、各类 Web 控制台）时，优先调用 `chrome-devtools` MCP 工具（`list_pages`、`select_page`、`new_page`、`navigate_page`、`take_snapshot`、`click`、`fill` 等）直接通过 CDP / DOM 树精准控制本地日常 Chrome / Edge（完整保留登录态），不使用桌面级鼠标/截图模拟（Computer Use）。

2. **桌面软件优先使用多模态视觉（Vision）**：
   - 调用 `windows-uia-mcp` 的 `Snapshot` 时，优先使用 `{"use_ui_tree": false, "use_vision": true}` 直接看截图操作，或者只对当前活动窗口使用 `use_vision: true`。
   - 当需要操控本地 Windows 桌面 GUI 软件时，若纯视觉或 `windows-uia-mcp`（仅扫描当前焦点窗口）即可定位目标，直接根据画面或控件树坐标点击；若目标窗口为自绘 UI、微信、游戏、Canvas 且需精确文字坐标，切换使用 `windows-ocr-mcp` 进行防黑屏截图与本地 OCR 坐标识别后再点击。

3. **禁止冗余动作**：
   - 用快捷键（如 `win+i`）打开软件后，不要再重复调用 `App launch`；
   - 每次点击明确位置（如已在视野内的“系统 -> 显示”）时，直接根据多模态画面连续执行 `Click`，不要每一步前都重复调用 `Snapshot`。

4. **快捷键与直达命令优先**：
   - 能用系统快捷键或 `win+r` / PowerShell 命令直达的（例如打开显示设置可直接运行 `ms-settings:display`），优先一行命令直达，减少死板的鼠标逐级点击。
