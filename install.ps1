# Requires -Version 5.1
<#
.SYNOPSIS
    Antigravity Toolkit - Windows 一键交互式安装与管理向导

.DESCRIPTION
    支持零门槛交互式数字菜单，也支持命令行参数直达（适合进阶用户或自动化脚本）。
    所有增强组件均采用外挂与标准配置方式工作，不修改 Antigravity 核心安装文件。

.EXAMPLE
    .\install.ps1               # 启动交互式菜单（推荐新手使用）
    .\install.ps1 -All          # 一键安装全部三项推荐优化
    .\install.ps1 -Module 1     # 仅安装模块 1（支持 1, 2, 3）
    .\install.ps1 -Doctor       # 运行环境与安装状态健康自检
    .\install.ps1 -Uninstall    # 卸载防误关系统托盘守护
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [switch]$All,

    [Parameter(Mandatory = $false)]
    [string[]]$Module,

    [Parameter(Mandatory = $false)]
    [switch]$Doctor,

    [Parameter(Mandatory = $false)]
    [switch]$Uninstall,

    [Parameter(Mandatory = $false)]
    [Alias("h")]
    [switch]$Help
)

$ErrorActionPreference = "Stop"

# Ensure UTF-8 console output so Chinese text renders cleanly
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # Ignore in non-console hosts
}

$RepoRoot = if ($PSScriptRoot) {
    $PSScriptRoot
} else {
    Split-Path -Parent $MyInvocation.MyCommand.Path
}

function Show-Usage {
    Write-Host ""
    Write-Host "Antigravity Toolkit (Windows) 使用说明" -ForegroundColor Cyan
    Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "  .\install.ps1                启动可视化数字菜单（默认推荐）"
    Write-Host "  .\install.ps1 -All           一键安装全部推荐优化 (模块 1 + 2 + 3)"
    Write-Host "  .\install.ps1 -Module 1      按编号安装指定模块 (可选: 1, 2, 3)"
    Write-Host "  .\install.ps1 -Module 2,3    同时安装多个指定模块"
    Write-Host "  .\install.ps1 -Doctor        运行环境与安装状态自检 (Doctor)"
    Write-Host "  .\install.ps1 -Uninstall     停止并卸载防误关系统托盘守护"
    Write-Host "  .\install.ps1 -Help          显示本帮助说明"
    Write-Host ""
}

function Get-PowerShellHostPath {
    $psCmd = Get-Command powershell.exe -ErrorAction SilentlyContinue
    if ($psCmd -and $psCmd.Source) {
        return $psCmd.Source
    }
    $pwshCmd = Get-Command pwsh.exe -ErrorAction SilentlyContinue
    if ($pwshCmd -and $pwshCmd.Source) {
        return $pwshCmd.Source
    }
    return "powershell.exe"
}

function Get-RealPythonExe {
    # Prefer real Python installations and skip Microsoft Store WindowsApps stub aliases
    foreach ($cmdName in @("python.exe", "python3.exe")) {
        $found = Get-Command $cmdName -All -ErrorAction SilentlyContinue | Where-Object {
            $_.Source -and ($_.Source -notlike "*\Microsoft\WindowsApps\*")
        } | Select-Object -First 1
        if ($found) {
            return $found.Source
        }
    }

    $localAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $env:USERPROFILE "AppData\Local" }
    $appData = if ($env:APPDATA) { $env:APPDATA } else { Join-Path $env:USERPROFILE "AppData\Roaming" }

    foreach ($root in @(
        (Join-Path $localAppData "Programs\Python"),
        (Join-Path $env:USERPROFILE "miniconda3"),
        (Join-Path $env:USERPROFILE "anaconda3"),
        (Join-Path $appData "uv\python")
    )) {
        if (Test-Path $root) {
            $direct = Join-Path $root "python.exe"
            if (Test-Path $direct) {
                return $direct
            }
            $nested = Get-ChildItem -Path $root -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -notlike "*\venv\*" } |
                Sort-Object FullName -Descending |
                Select-Object -First 1
            if ($nested) {
                return $nested.FullName
            }
        }
    }
    return $null
}

function Invoke-PowerShellScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath,
        [Parameter(Mandatory = $true)]
        [string]$Title
    )

    $fullPath = Join-Path $RepoRoot $RelativePath
    if (-not (Test-Path $fullPath)) {
        Write-Host "[错误] 未找到安装脚本: $fullPath" -ForegroundColor Red
        Write-Host "请确认您在完整的 antigravity-toolkit 仓库目录中运行此脚本。" -ForegroundColor Yellow
        return $false
    }

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ">>> 正在执行: $Title" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan

    $psExe = Get-PowerShellHostPath
    & $psExe -NoProfile -ExecutionPolicy Bypass -File $fullPath | Out-Host
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host ""
        Write-Host "[提示] '$Title' 执行过程中返回了非零状态码 ($exitCode)。" -ForegroundColor Yellow
        Write-Host "您可以运行 .\install.ps1 -Doctor 查看详细环境诊断与修复建议。" -ForegroundColor Yellow
        return $false
    }

    Write-Host ""
    Write-Host "[完成] $Title 已执行完毕！" -ForegroundColor Green
    return $true
}

function Invoke-ModuleInstall {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Id
    )

    switch ($Id.Trim().ToLowerInvariant()) {
        { $_ -in @("1", "computer_use", "computer-use") } {
            return Invoke-PowerShellScript `
                -RelativePath "computer_use\setup_other_device.ps1" `
                -Title "[模块 1] 桌面与浏览器极速操控 (Computer Use + Chrome 直连)"
        }
        { $_ -in @("2", "close_guard", "close-guard") } {
            return Invoke-PowerShellScript `
                -RelativePath "close_guard\install_close_guard.ps1" `
                -Title "[模块 2] 防误关系统托盘驻留守护 (Close Guard)"
        }
        { $_ -in @("3", "branch_conversation", "branch-conversation", "branch") } {
            return Invoke-PowerShellScript `
                -RelativePath "branch_conversation\install_branch_tool.ps1" `
                -Title "[模块 3] 历史对话任意轮次分支工具 (Branch Conversation)"
        }
        default {
            Write-Host "[错误] 未知的模块标识: '$Id'。可选值为 1、2、3。" -ForegroundColor Red
            return $false
        }
    }
}

function Invoke-InstallAll {
    Write-Host ""
    Write-Host "即将依次为您安装全部 3 项 Antigravity 推荐增强模块..." -ForegroundColor Cyan
    $ok1 = Invoke-ModuleInstall -Id "1"
    $ok2 = Invoke-ModuleInstall -Id "2"
    $ok3 = Invoke-ModuleInstall -Id "3"

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    if ($ok1 -and $ok2 -and $ok3) {
        Write-Host "全部推荐优化已安装完成！" -ForegroundColor Green
        Write-Host "温馨提示：" -ForegroundColor White
        Write-Host "  1. 打开 Chrome 访问 chrome://inspect/#remote-debugging（Edge 访问 edge://inspect/#remote-debugging）并勾选 Enable remote debugging"
        Write-Host "  2. 在 Antigravity 的 MCP Servers 面板点击 Refresh 即可开始使用"
    } else {
        Write-Host "部分模块未完全成功，请查看上方提示或运行 .\install.ps1 -Doctor 进行环境自检。" -ForegroundColor Yellow
    }
    Write-Host "============================================================" -ForegroundColor Cyan
    return ($ok1 -and $ok2 -and $ok3)
}

function Invoke-Doctor {
    $doctorPath = Join-Path $RepoRoot "scripts\doctor.py"
    if (-not (Test-Path $doctorPath)) {
        Write-Host "[错误] 未找到自检脚本: $doctorPath" -ForegroundColor Red
        return $false
    }

    $pyExe = Get-RealPythonExe
    if (-not $pyExe) {
        Write-Host ""
        Write-Host "[提示] 当前系统尚未检测到可用的 Python 3 环境，无法启动详细自检脚本。" -ForegroundColor Yellow
        Write-Host "请先在 PowerShell 运行以下命令一键安装 Python 3.12（安装后重启终端）：" -ForegroundColor Cyan
        Write-Host "  winget install --id Python.Python.3.12 -e" -ForegroundColor White
        Write-Host "或前往 https://www.python.org/downloads/ 下载安装包（记得勾选 Add Python to PATH）。" -ForegroundColor White
        return $false
    }

    $env:PYTHONDONTWRITEBYTECODE = "1"
    & $pyExe -B $doctorPath | Out-Host
    return ($LASTEXITCODE -eq 0)
}

function Invoke-UninstallCloseGuard {
    return Invoke-PowerShellScript `
        -RelativePath "close_guard\uninstall_close_guard.ps1" `
        -Title "卸载防误关系统托盘守护 (Close Guard)"
}

function Show-InteractiveMenu {
    while ($true) {
        Write-Host ""
        Write-Host "================================================================" -ForegroundColor Cyan
        Write-Host "         Antigravity Toolkit - 一键优化与安装向导 (Windows)" -ForegroundColor Cyan
        Write-Host "================================================================" -ForegroundColor Cyan
        Write-Host "  请选择要执行的操作（输入方括号内的编号或字母后按回车）：" -ForegroundColor White
        Write-Host ""
        Write-Host "  [1] 桌面与浏览器极速操控 (Computer Use + Chrome 直连)" -ForegroundColor Green
        Write-Host "      直连日常已登录浏览器、0.1秒极速看屏、微信/游戏本地 OCR 与晃动鼠标接管" -ForegroundColor DarkGray
        Write-Host "  [2] 防误关系统托盘驻留守护 (Close Guard)" -ForegroundColor Green
        Write-Host "      点右上角 X 或按 Alt+F4 自动最小化到系统托盘，保护后台运行中的 AI 任务" -ForegroundColor DarkGray
        Write-Host "  [3] 历史对话任意轮次分支工具 (Branch Conversation)" -ForegroundColor Green
        Write-Host "      按项目分组管理对话，支持从任意历史问答节点一键分叉探索新思路" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "  [A] 一键安装全部推荐优化" -ForegroundColor Cyan
        Write-Host "  [D] 运行环境与状态自检 (Doctor)" -ForegroundColor Yellow
        Write-Host "  [U] 卸载托盘守护" -ForegroundColor DarkYellow
        Write-Host "  [Q] 退出" -ForegroundColor Gray
        Write-Host "----------------------------------------------------------------" -ForegroundColor DarkGray

        if ([Console]::IsInputRedirected) {
            $rawChoice = [Console]::In.ReadLine()
            if ($null -eq $rawChoice) {
                break
            }
        } else {
            $rawChoice = Read-Host "请输入选项 [1/2/3/A/D/U/Q]"
        }

        $choice = if ($null -ne $rawChoice) { $rawChoice.Trim().ToUpperInvariant() } else { "Q" }

        switch ($choice) {
            "1" { [void](Invoke-ModuleInstall -Id "1") }
            "2" { [void](Invoke-ModuleInstall -Id "2") }
            "3" { [void](Invoke-ModuleInstall -Id "3") }
            "A" { [void](Invoke-InstallAll) }
            "D" { [void](Invoke-Doctor) }
            "U" { [void](Invoke-UninstallCloseGuard) }
            "Q" {
                Write-Host "已退出安装向导，祝您使用愉快！" -ForegroundColor Cyan
                break
            }
            "" {
                continue
            }
            default {
                Write-Host "[提示] 未识别的选项 '$rawChoice'，请输入 1、2、3、A、D、U 或 Q。" -ForegroundColor Yellow
                continue
            }
        }

        if ($choice -eq "Q") {
            break
        }

        if ([Console]::IsInputRedirected) {
            continue
        }
        Write-Host ""
        $nextAction = Read-Host "按回车键返回主菜单，或输入 Q 退出"
        if ($null -ne $nextAction -and $nextAction.Trim().ToUpperInvariant() -eq "Q") {
            Write-Host "已退出安装向导，祝您使用愉快！" -ForegroundColor Cyan
            break
        }
    }
}

# --- CLI Dispatch ---
if ($Help) {
    Show-Usage
    exit 0
}

$hasCliAction = $All -or ($Module -and $Module.Count -gt 0) -or $Doctor -or $Uninstall

if (-not $hasCliAction) {
    Show-InteractiveMenu
    exit 0
}

$overallSuccess = $true

if ($All) {
    if (-not (Invoke-InstallAll)) {
        $overallSuccess = $false
    }
}

if ($Module -and $Module.Count -gt 0) {
    foreach ($entry in $Module) {
        foreach ($subId in ($entry -split ",")) {
            if (-not [string]::IsNullOrWhiteSpace($subId)) {
                if (-not (Invoke-ModuleInstall -Id $subId)) {
                    $overallSuccess = $false
                }
            }
        }
    }
}

if ($Uninstall) {
    if (-not (Invoke-UninstallCloseGuard)) {
        $overallSuccess = $false
    }
}

if ($Doctor) {
    if (-not (Invoke-Doctor)) {
        $overallSuccess = $false
    }
}

if (-not $overallSuccess) {
    exit 1
}
exit 0
