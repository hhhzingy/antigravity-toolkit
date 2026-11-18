# Requires -Version 5.1
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Check Python availability for friendly hint
$HasPython = Get-Command "python.exe" -All -ErrorAction SilentlyContinue | Where-Object {
    $_.Source -and ($_.Source -notlike "*\Microsoft\WindowsApps\*")
}
if (-not $HasPython) {
    Write-Host "[提示] 当前 PATH 中未检测到 Python，建议安装 Python 3.10+ (winget install Python.Python.3.12) 后使用。" -ForegroundColor Yellow
}

# 1. Deploy branch_conversation.py
$BranchDir = Join-Path $env:USERPROFILE "mcp-gui-workspace\antigravity-branch"
New-Item -ItemType Directory -Force -Path $BranchDir | Out-Null
$SrcPy = Join-Path $ScriptDir "branch_conversation.py"
$DstPy = Join-Path $BranchDir "branch_conversation.py"
if ($SrcPy -ne $DstPy) {
    Copy-Item -Force $SrcPy $DstPy
}

# 2. Deploy global Antigravity Skill (branch-conversation)
$SkillDir = Join-Path $env:USERPROFILE ".gemini\config\skills\branch-conversation"
New-Item -ItemType Directory -Force -Path $SkillDir | Out-Null
$SrcSkill = Join-Path $ScriptDir "SKILL.md"
$DstSkill = Join-Path $SkillDir "SKILL.md"
if ($SrcSkill -ne $DstSkill) {
    Copy-Item -Force $SrcSkill $DstSkill
}

Write-Host "Antigravity 对话分支工具与全局 AI 技能已安装成功！" -ForegroundColor Green
Write-Host " - 工具脚本路径: $DstPy"
Write-Host " - 全局技能路径: $DstSkill"
Write-Host " - 使用方式 1  : 右键系统托盘 Antigravity 图标 -> 点击 '分支克隆对话 (Branch)...'"
Write-Host " - 使用方式 2  : 在聊天框直接对 AI 说 '把当前对话分支一份，忽略最后一条消息'"
