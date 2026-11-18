# Requires -Version 5.1
$ErrorActionPreference = "SilentlyContinue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceDir = Join-Path $env:USERPROFILE "mcp-gui-workspace"

# 1. Remove only computer_use MCP entries from mcp_config.json (preserve user's other MCP servers)
$PyCmd = Get-Command python.exe -All -ErrorAction SilentlyContinue | Where-Object {
    $_.Source -and ($_.Source -notlike "*\Microsoft\WindowsApps\*")
} | Select-Object -First 1

$CleanMcpPy = @'
import json, sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
if not cfg_path.is_file():
    raise SystemExit(0)
try:
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

if isinstance(data, dict) and isinstance(data.get("mcpServers"), dict):
    removed = False
    for key in ("chrome-devtools", "windows-uia-mcp", "windows-ocr-mcp"):
        if key in data["mcpServers"]:
            del data["mcpServers"][key]
            removed = True
    if removed:
        cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
'@

foreach ($CfgPath in @(
    (Join-Path $env:USERPROFILE ".gemini\config\mcp_config.json"),
    (Join-Path $env:USERPROFILE ".gemini\antigravity\mcp_config.json")
)) {
    if (Test-Path $CfgPath) {
        if ($PyCmd) {
            $CleanMcpPy | & $PyCmd.Source -B - $CfgPath
        } else {
            try {
                $Raw = Get-Content -Raw -Encoding UTF8 $CfgPath | ConvertFrom-Json
                if ($Raw.mcpServers) {
                    foreach ($Name in @("chrome-devtools", "windows-uia-mcp", "windows-ocr-mcp")) {
                        $Raw.mcpServers.PSObject.Properties.Remove($Name)
                    }
                    $JsonOut = $Raw | ConvertTo-Json -Depth 10
                    [System.IO.File]::WriteAllText($CfgPath, $JsonOut + "`n", [System.Text.UTF8Encoding]::new($false))
                }
            } catch {}
        }
    }
}

# 2. Stop running desktop/OCR MCP engine processes so virtualenvs unlock cleanly
foreach ($ProcName in @("windows-mcp", "computer-control-mcp")) {
    Get-Process -Name $ProcName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*chrome-devtools-launcher.py*"
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 300

# 3. Remove rules deployed by computer_use (preserve custom GEMINI.md if modified by user)
$GuiRulePath = Join-Path $env:USERPROFILE ".gemini\config\rules\gui-control.md"
if (Test-Path $GuiRulePath) {
    Remove-Item -Force $GuiRulePath
}

$GeminiMdPath = Join-Path $env:USERPROFILE ".gemini\config\GEMINI.md"
$TemplateRulesPath = Join-Path $ScriptDir "configs\rules.md"
if ((Test-Path $GeminiMdPath) -and (Test-Path $TemplateRulesPath)) {
    $CurText = (Get-Content -Raw -Encoding UTF8 $GeminiMdPath).Trim()
    $TplText = (Get-Content -Raw -Encoding UTF8 $TemplateRulesPath).Trim()
    if ($CurText -eq $TplText) {
        Remove-Item -Force $GeminiMdPath
    }
}

# 4. Remove computer_use engine directories & config (keep close_guard / branch_conversation intact!)
foreach ($RelItem in @(
    "Windows-MCP",
    "computer-control-mcp",
    "chrome-devtools-launcher.py",
    ".agents",
    "README_DEV.md"
)) {
    $ItemPath = Join-Path $WorkspaceDir $RelItem
    if (Test-Path $ItemPath) {
        Remove-Item -Recurse -Force $ItemPath
    }
}

$WinMcpCfgDir = Join-Path $env:USERPROFILE ".windows-mcp"
if (Test-Path $WinMcpCfgDir) {
    Remove-Item -Recurse -Force $WinMcpCfgDir
}

if (Test-Path $WorkspaceDir) {
    $Remaining = Get-ChildItem -Force $WorkspaceDir -ErrorAction SilentlyContinue
    if (-not $Remaining -or $Remaining.Count -eq 0) {
        Remove-Item -Force $WorkspaceDir
    }
}

Write-Host "Antigravity 桌面与浏览器极速操控模块 (computer_use) 已卸载清理完毕（其他 MCP 服务与其他增强模块均完好保留）。" -ForegroundColor Yellow
Write-Host " - 提示: 如在 Antigravity 打开状态执行，可在 MCP Servers 面板点击一次 Refresh 同步列表。" -ForegroundColor Gray
