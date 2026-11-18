# Requires -Version 5.1
$ErrorActionPreference = "SilentlyContinue"

# 1. Remove HKCU Run autostart & Scheduled Task
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "AntigravityCloseGuard"
Unregister-ScheduledTask -TaskName "AntigravityCloseGuard" -Confirm:$false -ErrorAction SilentlyContinue

# 2. Gracefully notify Close Guard hidden window on WinSta0\Default first so any hidden Antigravity windows pop back onto screen
try {
    Add-Type -Namespace CloseGuardUninstaller -Name Win32 -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
public static extern System.IntPtr OpenDesktopW(string lpszDesktop, uint dwFlags, bool fInherit, uint dwDesiredAccess);
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern bool SetThreadDesktop(System.IntPtr hDesktop);
[System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
public static extern System.IntPtr FindWindowW(string lpClassName, string lpWindowName);
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern bool PostMessageW(System.IntPtr hWnd, uint Msg, System.IntPtr wParam, System.IntPtr lParam);
'@
    $hDesk = [CloseGuardUninstaller.Win32]::OpenDesktopW("Default", 0, $false, 0x01FF)
    if ($hDesk -ne [System.IntPtr]::Zero) {
        [void][CloseGuardUninstaller.Win32]::SetThreadDesktop($hDesk)
    }
    $ExistingHwnd = [CloseGuardUninstaller.Win32]::FindWindowW("AntigravityCloseGuardHiddenWnd", $null)
    if ($ExistingHwnd -ne [System.IntPtr]::Zero) {
        [void][CloseGuardUninstaller.Win32]::PostMessageW($ExistingHwnd, 0x0010, [System.IntPtr]::Zero, [System.IntPtr]::Zero)
        Start-Sleep -Milliseconds 400
    }
} catch {}

# 3. Stop any remaining pythonw instance of antigravity_close_guard.pyw
Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -like "*antigravity_close_guard.pyw*"
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force
}

# 4. Remove deployed script directory
$TargetDir = Join-Path $env:USERPROFILE "mcp-gui-workspace\antigravity-close-guard"
if (Test-Path $TargetDir) {
    Remove-Item -Recurse -Force $TargetDir
}

Write-Host "Antigravity 防误关托盘守护已停止运行，并已彻底移除开机自启与本地脚本。" -ForegroundColor Yellow
