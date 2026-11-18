# 桌面 GUI 双引擎 MCP 源码导读与二次开发指南 (`README_DEV.md` — Windows & Linux)

本指南面向希望深入了解底层实现原理、自定义性能参数或参与贡献的开发者。本模块部署的本地桌面 GUI 自动化 MCP 引擎均采用可编辑源码模式（`-e .`）安装于 `~/mcp-gui-workspace`，修改 `.py` 源码后在 Antigravity 的 **MCP Servers** 面板点击 **Refresh** 即可立即生效。

> 日常安装与三步快速上手请参阅用户指南：[`README.md`](./README.md)。

---

## 一、双平台三引擎架构概览与职责分工

| 引擎名称 (MCP ID) | 适用平台 | 本地源码工作目录 | 核心技术栈 | 适用场景 |
| :--- | :--- | :--- | :--- | :--- |
| **`chrome-devtools`** | Windows / Linux | 全局 `npm` 包 + Linux 启动器 [`chrome-devtools-launcher.sh`](./linux-gui-mcp/chrome-devtools-launcher.sh) | Chrome DevTools Protocol (CDP) / `DevToolsActivePort` | 直连日常已登录的 Google Chrome / Microsoft Edge / Chromium，基于 DOM 树 `uid` 精准读写与交互，不受窗口遮挡影响。 |
| **`windows-uia-mcp`** | Windows | `~/mcp-gui-workspace/Windows-MCP`（合入 [`windows-mcp-speedup.patch`](./windows-mcp-speedup.patch)） | Windows UIAutomation (`IUIAutomation2` / `comtypes`) + MSAA/IAccessible2 + DXGI (`dxcam`) | 标准 Windows 原生应用（Win32、WPF、WinForms、UWP、Qt、Office），支持极速多模态纯视觉截图（`< 0.12s`）或仅扫描当前活动窗口的原生控件树（`< 0.2s`）。 |
| **`linux-uia-mcp`** | Linux (X11) | `~/mcp-gui-workspace/linux-gui-mcp`（同步自 [`computer_use/linux-gui-mcp/`](./linux-gui-mcp/)） | X11 (`python-xlib` / `xdotool` / `wmctrl` / `xclip`) + AT-SPI2 (`gir1.2-atspi-2.0`) + `mss` | 标准 Ubuntu / Linux 桌面应用（GTK3/4、Qt5/6、Electron），默认纯视觉极速截图（`~0.08s` 本地抓屏 / `~0.26s` 含 RPC）或仅扫描当前焦点窗口 AT-SPI2 控件树，支持 UTF-8/中文零丢字剪贴板输入与 2 秒晃动鼠标接管保护。 |
| **`windows-ocr-mcp` / `linux-ocr-mcp`** | Windows / Linux | `~/mcp-gui-workspace/computer-control-mcp`（合入 [`computer-control-mcp-opti.patch`](./computer-control-mcp-opti.patch)） | WGC (`win32`) + `mss` + `RapidOCR` (ONNXRuntime) + `PyAutoGUI` + `pywinctl` | 无原生控件树或自绘 UI 软件（微信、RustDesk 远程桌面、游戏、硬件加速窗口、Canvas 画布），通过防黑屏/多屏安全裁剪截图 + 本地离线 OCR 识别文字四顶点坐标框并自动还原屏幕绝对坐标。 |

---

## 二、Linux 引擎：`linux-gui-mcp` (`linux-uia-mcp`) 核心源码地图

- **仓库源码位置**：[`computer_use/linux-gui-mcp/`](./linux-gui-mcp/)（安装后同步至 `~/mcp-gui-workspace/linux-gui-mcp`）
- **Python 虚拟环境**：`~/mcp-gui-workspace/linux-gui-mcp/.venv`（启用 `--system-site-packages` 直接复用系统 `gi.repository.Atspi`）
- **运行时配置文件**：`~/.linux-mcp/config.toml`（模板见 [`configs/linux-mcp-config.toml`](./configs/linux-mcp-config.toml)）
- **极速启动入口**：`~/mcp-gui-workspace/linux-gui-mcp/.venv/bin/linux-gui-mcp`（直接执行虚拟环境二进制，跳过 `uv run` 启动期依赖重解析，冷启动握手仅 `~0.8s`）

| 文件相对路径 | 关键类 / 函数 | 核心职责说明 |
| :--- | :--- | :--- |
| [`linux-gui-mcp/src/linux_gui_mcp/server.py`](./linux-gui-mcp/src/linux_gui_mcp/server.py) | `MouseTakeoverGuard`<br>`get_active_window_info()`<br>`scan_active_window_atspi()`<br>`capture_fast_screenshot()`<br>`Snapshot()` / `Click()` / `Type()` / `Shortcut()` / `App()` | 1. X11 `_NET_ACTIVE_WINDOW` 毫秒级焦点窗口探测；<br>2. 仅针对当前焦点窗口的 AT-SPI2 控件树遍历（自动过滤 `gnome-shell`、`ubuntu-dock` 与所有后台窗口）；<br>3. `mss` 共享内存抓屏 + `compress_level=1` 极速 PNG 编码与高分屏 `Screenshot Coordinate Scale` 换算；<br>4. 基于 `xclip` 的 UTF-8/中文粘贴输入（根据 `WM_CLASS` 自动识别终端 `Ctrl+Shift+V` 与普通 GUI `Ctrl+V`，粘贴后还原原剪贴板）。 |
| [`linux-gui-mcp/chrome-devtools-launcher.sh`](./linux-gui-mcp/chrome-devtools-launcher.sh) | 智能浏览器启动脚本 | 按优先级自动探测 Google Chrome (`DevToolsActivePort` -> `--autoConnect`)、Microsoft Edge / Chromium (`DevToolsActivePort` -> `--wsEndpoint`) 与 `127.0.0.1:9222` (`--browserUrl`)，严格规避 `--autoConnect` 与 `--executablePath` 互斥冲突。 |

**Linux 常用环境变量调优（可写入 `mcp_config.json` 的 `linux-uia-mcp.env`）**：
- `LINUX_MCP_MAX_TREE_ELEMENTS`（默认 `500`）：单次 AT-SPI2 扫描最大控件节点预算；
- `LINUX_MCP_MAX_DEPTH`（默认 `20`）：AT-SPI2 树最大递归深度；
- `LINUX_MCP_MAX_IMAGE_WIDTH` / `LINUX_MCP_MAX_IMAGE_HEIGHT`（默认 `1920` / `1080`）：若希望 2K/4K 屏保持 `1:1` 原始物理像素不缩放，可设为 `2560` / `1440` 或 `3840` / `2160`。

---

## 三、Windows 引擎：`Windows-MCP` (`windows-uia-mcp`) 核心源码地图

- **本地工作目录**：`~/mcp-gui-workspace/Windows-MCP`
- **优化补丁文件**：[`windows-mcp-speedup.patch`](./windows-mcp-speedup.patch)（由 [`setup_other_device.ps1`](./setup_other_device.ps1) 自动拉取并应用）
- **Python 虚拟环境**：`~/mcp-gui-workspace/Windows-MCP/.venv`
- **运行时配置文件**：`~/.windows-mcp/config.toml`（模板见 [`configs/windows-mcp-config.toml`](./configs/windows-mcp-config.toml)）
- **启动入口命令**：`<uv绝对路径> --directory <用户目录>/mcp-gui-workspace/Windows-MCP run windows-mcp serve`（安装脚本会自动解析并写入 `uv.exe` 的完整路径，确保 GUI 进程在任何环境变量下均可稳定拉起）

### 核心源码文件与关键函数位置

| 文件相对路径（位于 `Windows-MCP` 内） | 关键类 / 函数 | 核心职责说明 |
| :--- | :--- | :--- |
| `src/windows_mcp/__main__.py` | `_build_mcp()`<br>`lifespan()`<br>`serve()` | MCP Server 入口，初始化 `FastMCP("windows-mcp")`、挂载人机控制权协调器 `ControlToolGate`、加载 `~/.windows-mcp/config.toml` 并注册所有 Tool。 |
| `src/windows_mcp/infrastructure/config.py` | `ControlConfig`<br>`load_config()` | 解析 `~/.windows-mcp/config.toml` 中的 `[control]`、`[server]`、`[security]`、`[tools]` 配置项（如 `consent_countdown_seconds`、`idle_timeout_seconds`、`mouse_takeover_units`）。 |
| `src/windows_mcp/desktop/control.py` | `ControlCoordinator`<br>`arm_visible()` | **人手晃动鼠标夺回控制权保护**：通过底层 Raw Input / Win32 钩子监测物理鼠标位移（默认累计 `500` 设备单位或按下 `Ctrl+Alt+Shift+Backspace` 立即中断 AI 操作并归还控制权）。 |
| `src/windows_mcp/desktop/service.py` | `Desktop.get_state()`<br>`Desktop.click()`<br>`Desktop.type()`<br>`Desktop.scroll()`<br>`Desktop.get_annotated_screenshot()` | 桌面状态采集与交互核心实现：纯视觉模式（`use_ui_tree=False, use_vision=True`）跳过句柄枚举与虚拟桌面 COM 查询；UI 树模式仅扫描当前活动焦点窗口。 |
| `src/windows_mcp/tree/service.py` | `Tree.get_state()`<br>`Tree.get_window_wise_nodes()`<br>`Tree.tree_traversal()` | **UIA 控件树遍历核心**：在主 STA 线程递归遍历当前焦点窗口控件树，过滤 `Progman`、`Shell_TrayWnd` 等系统壳窗口，默认关闭耗时的 `GetAllWordBoundingBoxes()`（可通过 `WINDOWS_MCP_WORD_NODES=1` 按需开启）。 |
| `src/windows_mcp/tree/budget.py` | `DEFAULT_MAX_TREE_ELEMENTS`<br>`TreeElementBudget` | 限制单次 `Snapshot` 采集的最大控件节点数量（默认 `500`），防止超大型列表或表格阻塞 UIA。 |
| `src/windows_mcp/tree/config.py` | `INTERACTIVE_CONTROL_TYPE_NAMES`<br>`INTERACTIVE_ROLES` | 定义哪些 UIA `ControlType`（如 `ButtonControl`, `EditControl`）与 `LegacyIAccessibleRole` 会被判定为可交互控件并输出坐标。 |
| `src/windows_mcp/desktop/screenshot.py` | `_DxcamBackend`<br>`_MssBackend`<br>`_PillowBackend` | 多后端截图自动降级链：优先使用 DXGI 桌面复制 (`dxcam`)，失败时自动降级至 `mss` 和 `PIL.ImageGrab`。 |
| `src/windows_mcp/tools/_snapshot_helpers.py` | `capture_desktop_state()` | 截图编码辅助函数：补丁已将 PNG 编码改为 `compress_level=1` 以消除大图压缩瓶颈。 |

---

## 四、双平台 OCR 引擎：`computer-control-mcp` 核心源码地图

- **本地工作目录**：`~/mcp-gui-workspace/computer-control-mcp`
- **跨平台优化补丁**：[`computer-control-mcp-opti.patch`](./computer-control-mcp-opti.patch)（由 [`setup_other_device.ps1`](./setup_other_device.ps1) 与 [`setup_linux.sh`](./setup_linux.sh) 自动应用）
- **Python 虚拟环境**：`~/mcp-gui-workspace/computer-control-mcp/.venv`（以 `-e .` 可编辑模式安装）

| 文件相对路径（位于 `computer-control-mcp` 内） | 关键类 / 函数 | 核心职责说明 |
| :--- | :--- | :--- |
| `src/computer_control_mcp/cli.py` | `parse_args()`<br>`main()` | CLI 入口（支持无参数启动 MCP Server，也支持命令行调试 `computer-control-mcp screenshot` / `list-windows` / `gui`）。 |
| `src/computer_control_mcp/server.py` | `main()` | 纯 MCP Server 启动入口，调用 `core.main()`。 |
| `src/computer_control_mcp/core.py` | `engine = RapidOCR()`<br>`_wgc_screenshot()`<br>`_mss_screenshot()`<br>`take_screenshot()`<br>`take_screenshot_with_ocr()`<br>`execute_actions()` | **核心单文件实现**（含 [`computer-control-mcp-opti.patch`](./computer-control-mcp-opti.patch) 增强）：<br>1. Windows 启动期声明 `Per-Monitor DPI V2` 感知，消除高分屏逻辑/物理像素错位；<br>2. 全屏截图（`title_pattern=None`）自动跳过全量窗口枚举；<br>3. `_mss_screenshot()` 针对多屏/阴影负坐标进行虚拟桌面边界裁剪；<br>4. `take_screenshot_with_ocr()` 自动按 `scale_percent_for_ocr` 与单窗口 `(window.left, window.top)` 还原屏幕绝对坐标，并在 `finally` 块自动清理临时目录。 |

---

## 五、二次开发与自定义参数调优指南

### 1. 调整 `Windows-MCP` 控件树遍历预算与深度

#### (1) 提高单次采集节点数上限（防止复杂窗口控件被截断）
可在 `mcp_config.json` 的 `windows-uia-mcp.env` 中添加环境变量（无需改源码）：
```json
"WINDOWS_MCP_MAX_TREE_ELEMENTS": "1500"
```
或直接修改 `src/windows_mcp/tree/budget.py` 中的 `DEFAULT_MAX_TREE_ELEMENTS = 500`。

#### (2) 为递归遍历增加自定义深度上限 (`max_depth`)
若希望进一步限制超深层嵌套应用的遍历深度，可在 `src/windows_mcp/tree/service.py` 的 `tree_traversal()` 中添加 `depth: int = 0, max_depth: int = 25` 参数，当 `depth > max_depth` 时直接 `return`，并在尾部递归调用处传入 `depth=depth + 1, max_depth=max_depth`。

#### (3) 将自定义控件类型加入可交互列表
编辑 `src/windows_mcp/tree/config.py`，在 `INTERACTIVE_CONTROL_TYPE_NAMES` 或 `INTERACTIVE_ROLES` 中加入目标控件的 `ControlTypeName` 或 `AccessibleRoleName`。

#### (4) 调整晃动鼠标夺回控制权的灵敏度
编辑 `~/.windows-mcp/config.toml` 或 `~/.linux-mcp/config.toml`：
```toml
[control]
enabled = true
consent_countdown_seconds = 0
idle_timeout_seconds = 2
mouse_takeover_units = 200  # 默认 500（范围 40~2000），数值越小越容易触发人工接管
```

---

### 2. 调整 `computer-control-mcp` 的 OCR 检测阈值与窗口匹配参数

#### (1) 调整 RapidOCR 检测框与文本置信度阈值
编辑 `~/mcp-gui-workspace/computer-control-mcp/src/computer_control_mcp/core.py` 中的 `engine = RapidOCR()` 初始化参数：
```python
engine = RapidOCR(
    text_score=0.6,    # 默认 0.5：调高可过滤低置信度噪点，调低可召回模糊小字
    box_thresh=0.5,    # DBNet 文本检测框阈值
    unclip_ratio=1.8,  # 文本框外扩比例，文字边缘被截断时可调大至 1.8~2.0
)
```

#### (2) 调整单窗口标题模糊匹配阈值 (`threshold`)
`take_screenshot(threshold=10)` 与 `take_screenshot_with_ocr(threshold=10)` 默认使用 `fuzzywuzzy.fuzz.partial_ratio` 模糊匹配（阈值 `10`）。若桌面同时打开多个相似标题窗口导致误匹配，可将默认阈值调高至 `60`。

---

### 3. 高分屏 (125% / 150% / 200% 2K/4K) DPI 坐标换算说明

#### (1) `Windows-MCP` 与 `linux-gui-mcp` 的坐标系与大图缩放
- **控件树坐标系**：Windows UIA `BoundingRectangle` / `SetCursorPos` 与 Linux X11 / AT-SPI2 `Atspi.CoordType.SCREEN` 均直接工作在**屏幕物理像素坐标系**下，按控件中心点点击不受系统缩放比例影响。
- **纯视觉大图自动缩放 (`Screenshot Coordinate Scale`)**：
  - 当物理屏幕分辨率超过 `1920x1080` 时，截图会自动按等比缩放到 `1080p` 以加速多模态传输，并在返回文本中附带 `Screenshot Coordinate Scale: <scale>`（例如 `2560x1440` 对应 `1.3333`）。
  - 如需保持 `1:1` 原始物理像素不缩放：
    - **Linux**：在 `mcp_config.json` 的 `linux-uia-mcp.env` 中设置 `"LINUX_MCP_MAX_IMAGE_WIDTH": "3840", "LINUX_MCP_MAX_IMAGE_HEIGHT": "2160"`；
    - **Windows**：将 `src/windows_mcp/tools/_snapshot_helpers.py` 中的 `MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT` 改为 `3840, 2160`。

#### (2) `computer-control-mcp` 的高分屏感知与坐标还原公式
[`computer-control-mcp-opti.patch`](./computer-control-mcp-opti.patch) 已内置两项关键坐标对齐逻辑：
1. **Windows Per-Monitor DPI V2 声明**：在导入 `pyautogui` 前调用 `SetProcessDpiAwarenessContext(-4)`，确保 `pywinctl`、`pyautogui` 与 `mss` / `WGC` 统一使用物理像素坐标系。
2. **OCR 缩放比例与单窗口偏移还原公式**：
   ```python
   scale_factor = 100.0 / float(scale_percent_for_ocr)
   offset_x = max(int(window.left), 0) if window else 0
   offset_y = max(int(window.top), 0) if window else 0

   zipped_results = [
       (
           [
               [
                   int(round(pt[0] * scale_factor)) + offset_x,
                   int(round(pt[1] * scale_factor)) + offset_y,
               ]
               for pt in (box.tolist() if hasattr(box, "tolist") else box)
           ],
           text,
           float(score),
       )
       for box, text, score in zipped_results
   ]
   ```
