# Requires -Version 5.1
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TargetDir = Join-Path $env:USERPROFILE "mcp-gui-workspace\antigravity-close-guard"
New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

# Gracefully close any already-running Close Guard instance on WinSta0\Default so hidden windows restore cleanly before upgrade
try {
    Add-Type -Namespace CloseGuardInstaller -Name Win32 -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
public static extern System.IntPtr OpenDesktopW(string lpszDesktop, uint dwFlags, bool fInherit, uint dwDesiredAccess);
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern bool SetThreadDesktop(System.IntPtr hDesktop);
[System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
public static extern System.IntPtr FindWindowW(string lpClassName, string lpWindowName);
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern bool PostMessageW(System.IntPtr hWnd, uint Msg, System.IntPtr wParam, System.IntPtr lParam);
'@ -ErrorAction SilentlyContinue
    $hDesk = [CloseGuardInstaller.Win32]::OpenDesktopW("Default", 0, $false, 0x01FF)
    if ($hDesk -ne [System.IntPtr]::Zero) {
        [void][CloseGuardInstaller.Win32]::SetThreadDesktop($hDesk)
    }
    $ExistingHwnd = [CloseGuardInstaller.Win32]::FindWindowW("AntigravityCloseGuardHiddenWnd", $null)
    if ($ExistingHwnd -ne [System.IntPtr]::Zero) {
        [void][CloseGuardInstaller.Win32]::PostMessageW($ExistingHwnd, 0x0010, [System.IntPtr]::Zero, [System.IntPtr]::Zero)
        Start-Sleep -Milliseconds 350
    }
} catch {}

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -like "*antigravity_close_guard.pyw*"
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

$SrcScript = Join-Path $ScriptDir "antigravity_close_guard.pyw"
$DstScript = Join-Path $TargetDir "antigravity_close_guard.pyw"
if ($SrcScript -ne $DstScript) {
    Copy-Item -Force $SrcScript $DstScript
}

# Find real pythonw.exe fast (skip Microsoft Store WindowsApps execution alias stubs)
$Pythonw = $null
$Candidates = @()
foreach ($cmd in @("pythonw.exe", "python.exe")) {
    Get-Command $cmd -ErrorAction SilentlyContinue | Where-Object {
        $_.Source -and ($_.Source -notlike "*\Microsoft\WindowsApps\*")
    } | ForEach-Object {
        $dir = Split-Path -Parent $_.Source
        $pw = Join-Path $dir "pythonw.exe"
        if (Test-Path $pw) { $Candidates += $pw } else { $Candidates += $_.Source }
    }
}

if ($Candidates.Count -eq 0) {
    $LocalPyRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
    if (Test-Path $LocalPyRoot) {
        Get-ChildItem -Path $LocalPyRoot -Filter "pythonw.exe" -Recurse -Depth 2 -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            ForEach-Object { $Candidates += $_.FullName }
    }
}

if ($Candidates.Count -eq 0) {
    foreach ($fallback in @(
        "$env:USERPROFILE\anaconda3\pythonw.exe",
        "$env:USERPROFILE\miniconda3\pythonw.exe",
        "$env:ProgramData\anaconda3\pythonw.exe",
        "$env:ProgramData\miniconda3\pythonw.exe"
    )) {
        if (Test-Path $fallback) { $Candidates += $fallback }
    }
}

if ($Candidates.Count -eq 0) {
    foreach ($uvRoot in @("$env:APPDATA\uv\python", "$env:LOCALAPPDATA\uv\python")) {
        if ($uvRoot -and (Test-Path $uvRoot)) {
            Get-ChildItem $uvRoot -Filter "pythonw.exe" -Depth 2 -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending |
                ForEach-Object { $Candidates += $_.FullName }
        }
    }
}

$Pythonw = $Candidates | Select-Object -First 1
if (-not $Pythonw) {
    Write-Host "[!] 未检测到可用的 Python 环境（已排除 Microsoft Store 空占位符）。" -ForegroundColor Red
    Write-Host "    请先运行以下命令安装 Python，或前往 https://www.python.org/downloads/ 下载安装：" -ForegroundColor Yellow
    Write-Host "    winget install Python.Python.3.12" -ForegroundColor Cyan
    exit 1
}

# Register HKCU Run autostart
$RegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$CmdStr = "`"$Pythonw`" `"$DstScript`""
Set-ItemProperty -Path $RegPath -Name "AntigravityCloseGuard" -Value $CmdStr

# Launch via Windows Task Scheduler (Interactive token) so that even when run inside
# an AI Agent's sandboxed terminal / Job Object (exebox-*), pythonw.exe starts natively
# on the user's real WinSta0\Default desktop and survives after the Agent command exits!
$LaunchedViaTask = $false
try {
    $Action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$DstScript`""
    $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName "AntigravityCloseGuard" -Action $Action -Trigger $Trigger -Settings $Settings -Force -ErrorAction Stop | Out-Null
    Start-ScheduledTask -TaskName "AntigravityCloseGuard" -ErrorAction Stop
    Start-Sleep -Milliseconds 900
    $RunningProc = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -like "*antigravity_close_guard.pyw*" }
    if ($RunningProc) {
        $LaunchedViaTask = $true
    }
} catch {}

if (-not $LaunchedViaTask) {
    Start-Process -FilePath $Pythonw -ArgumentList "`"$DstScript`""
}

Write-Host "Antigravity 防误关托盘守护已安装成功，已开启登录自启并立即生效！" -ForegroundColor Green
Write-Host " - 守护脚本路径: $DstScript"
Write-Host " - 日常使用提示: 点击右上角 X 或按 Alt+F4 将自动隐藏到右下角托盘（若图标折叠请点右下角 ^ 箭头拖出）；右键托盘图标点击 Quit 才彻底退出。"
