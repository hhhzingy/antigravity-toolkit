# Requires -Version 5.1
$ErrorActionPreference = "SilentlyContinue"

$BranchDir = Join-Path $env:USERPROFILE "mcp-gui-workspace\antigravity-branch"
$SkillDir = Join-Path $env:USERPROFILE ".gemini\config\skills\branch-conversation"

if (Test-Path $BranchDir) {
    Remove-Item -Recurse -Force $BranchDir
}
if (Test-Path $SkillDir) {
    Remove-Item -Recurse -Force $SkillDir
}

Write-Host "Antigravity 对话分支工具与全局技能已卸载清理完毕（此前已创建的分支对话均完整保留）。" -ForegroundColor Yellow
