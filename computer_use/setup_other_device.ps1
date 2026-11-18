# Requires -Version 5.1
$ErrorActionPreference = "Stop"

function Write-Step($Title) {
    Write-Host "`n=== $Title ===" -ForegroundColor Cyan
}

function Fail-Friendly($MissingItem, $WhyNeeded, $FixHint) {
    Write-Host "`n[!] Missing prerequisite: $MissingItem" -ForegroundColor Red
    Write-Host "    Why needed : $WhyNeeded" -ForegroundColor Yellow
    Write-Host "    How to fix : $FixHint" -ForegroundColor Green
    Write-Host "    After installing, reopen PowerShell and run this script again.`n"
    exit 1
}

function Test-UsablePython($ExePath) {
    if (-not $ExePath -or -not (Test-Path $ExePath) -or ($ExePath -like "*\WindowsApps\*")) {
        return $false
    }
    try {
        $Ver = & $ExePath -B -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $Ver) {
            $Parts = $Ver.Trim().Split(".")
            if ([int]$Parts[0] -eq 3 -and [int]$Parts[1] -ge 10) {
                return $true
            }
        }
    } catch {}
    return $false
}

function Resolve-WorkingPython {
    foreach ($Candidate in @("python", "python3")) {
        $Cmd = Get-Command $Candidate -ErrorAction SilentlyContinue
        if ($Cmd -and (Test-UsablePython $Cmd.Source)) {
            return $Cmd.Source
        }
    }
    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        try {
            $Resolved = & $PyLauncher.Source -3 -B -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $Resolved -and (Test-UsablePython $Resolved.Trim())) {
                return $Resolved.Trim()
            }
        } catch {}
    }

    # Fallback 1: Windows Registry (HKCU / HKLM PythonCore)
    foreach ($RegHive in @("HKCU:\Software\Python\PythonCore", "HKLM:\Software\Python\PythonCore")) {
        if (Test-Path $RegHive) {
            $SubKeys = Get-ChildItem -Path $RegHive -ErrorAction SilentlyContinue | Sort-Object Name -Descending
            foreach ($Key in $SubKeys) {
                $InstallKey = Join-Path $Key.PSPath "InstallPath"
                if (Test-Path $InstallKey) {
                    $Props = Get-ItemProperty -Path $InstallKey -ErrorAction SilentlyContinue
                    $CandidateExe = if ($Props.ExecutablePath) { $Props.ExecutablePath } elseif ($Props.'(default)') { Join-Path $Props.'(default)' "python.exe" } else { $null }
                    if (Test-UsablePython $CandidateExe) {
                        return $CandidateExe
                    }
                }
            }
        }
    }

    # Fallback 2: Common user & multi-drive Conda / Python directories
    $FallbackDirs = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python"),
        (Join-Path $env:USERPROFILE "miniconda3"),
        (Join-Path $env:USERPROFILE "anaconda3"),
        (Join-Path $env:ProgramData "miniconda3"),
        (Join-Path $env:ProgramData "anaconda3")
    )
    foreach ($Drive in @("C:", "D:", "E:")) {
        foreach ($Sub in @("miniconda3", "anaconda3", "Miniconda3", "Anaconda3", "Software\miniconda3", "Software\anaconda3")) {
            $FallbackDirs += "$Drive\$Sub"
        }
    }
    foreach ($Root in $FallbackDirs) {
        if ($Root -and (Test-Path $Root)) {
            $DirectExe = Join-Path $Root "python.exe"
            if (Test-UsablePython $DirectExe) {
                return $DirectExe
            }
            $Nested = Get-ChildItem -Path $Root -Filter "python.exe" -Depth 2 -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -notlike "*\venv\*" } |
                Sort-Object FullName -Descending
            foreach ($Item in $Nested) {
                if (Test-UsablePython $Item.FullName) {
                    return $Item.FullName
                }
            }
        }
    }
    return $null
}

function Resolve-UvBinary($PythonExe) {
    $UvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($UvCmd -and (Test-Path $UvCmd.Source)) {
        return $UvCmd.Source
    }
    $ExtraCandidates = @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:USERPROFILE ".cargo\bin\uv.exe")
    )
    if ($PythonExe) {
        $PyScripts = Join-Path (Split-Path -Parent $PythonExe) "Scripts\uv.exe"
        $ExtraCandidates += $PyScripts
        try {
            $UserScripts = & $PythonExe -B -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))" 2>$null
            if ($LASTEXITCODE -eq 0 -and $UserScripts) {
                $ExtraCandidates += (Join-Path $UserScripts.Trim() "uv.exe")
            }
        } catch {}
    }
    foreach ($PathItem in $ExtraCandidates) {
        if ($PathItem -and (Test-Path $PathItem)) {
            return (Resolve-Path $PathItem).Path
        }
    }
    return $null
}

function Invoke-GitCloneSafe($RepoUrl, $DestDir) {
    & git clone $RepoUrl $DestDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Retrying git clone with OpenSSL TLS backend..." -ForegroundColor Yellow
        if (Test-Path $DestDir) {
            Remove-Item -Recurse -Force $DestDir -ErrorAction SilentlyContinue
        }
        & git -c http.sslBackend=openssl clone $RepoUrl $DestDir
        if ($LASTEXITCODE -ne 0) {
            Write-Host "`n[!] Failed to clone $RepoUrl. Please check your internet/GitHub connection and try again." -ForegroundColor Red
            exit 1
        }
    }
}

Write-Step "[0/5] Running environment pre-flight checks"

$GitCmd = Get-Command git -ErrorAction SilentlyContinue
if (-not $GitCmd) {
    Fail-Friendly `
        -MissingItem "Git (git)" `
        -WhyNeeded "Downloads and patches the desktop MCP engine repositories." `
        -FixHint "Run: winget install --id Git.Git -e   (or download from https://git-scm.com/download/win)"
}
Write-Host "  [OK] git    : $($GitCmd.Source)" -ForegroundColor Green

$PythonExe = Resolve-WorkingPython
if (-not $PythonExe) {
    Fail-Friendly `
        -MissingItem "Python 3.10+ (python)" `
        -WhyNeeded "Runs the fast desktop vision & local OCR MCP engines." `
        -FixHint "Run: winget install --id Python.Python.3.12 -e   (or download from https://www.python.org/downloads/)"
}
Write-Host "  [OK] python : $PythonExe" -ForegroundColor Green

$NodeCmd = Get-Command node -ErrorAction SilentlyContinue
$NpmCmd = Get-Command npm -ErrorAction SilentlyContinue
if (-not $NodeCmd -or -not $NpmCmd) {
    Fail-Friendly `
        -MissingItem "Node.js & npm" `
        -WhyNeeded "Installs and runs chrome-devtools-mcp to connect to your open Chrome/Edge tabs." `
        -FixHint "Run: winget install --id OpenJS.NodeJS.LTS -e   (or download from https://nodejs.org/)"
}
Write-Host "  [OK] node   : $($NodeCmd.Source)" -ForegroundColor Green

Write-Step "[1/5] Preparing workspace directory & uv package manager"
$WorkspaceDir = Join-Path $env:USERPROFILE "mcp-gui-workspace"
New-Item -ItemType Directory -Force -Path $WorkspaceDir | Out-Null
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$UvExe = Resolve-UvBinary -PythonExe $PythonExe
if (-not $UvExe) {
    Write-Host "  Installing 'uv' fast Python environment manager..." -ForegroundColor Yellow
    & $PythonExe -m pip install --user uv
    if ($LASTEXITCODE -ne 0) {
        & $PythonExe -m pip install uv
    }
    $UvExe = Resolve-UvBinary -PythonExe $PythonExe
}
if (-not $UvExe) {
    Fail-Friendly `
        -MissingItem "uv (Python package manager)" `
        -WhyNeeded "Manages isolated virtual environments for Windows-MCP and computer-control-mcp." `
        -FixHint "Run: winget install --id=astral-sh.uv -e   (or: pip install uv)"
}
Write-Host "  [OK] uv     : $UvExe" -ForegroundColor Green

Write-Step "[2/5] Deploying & optimizing Engine 1: Windows-MCP (windows-uia-mcp)"
$WinMcpDir = Join-Path $WorkspaceDir "Windows-MCP"
if (-not (Test-Path (Join-Path $WinMcpDir ".git"))) {
    if (Test-Path $WinMcpDir) { Remove-Item -Recurse -Force $WinMcpDir }
    Invoke-GitCloneSafe -RepoUrl "https://github.com/CursorTouch/Windows-MCP.git" -DestDir $WinMcpDir
}
Push-Location $WinMcpDir
try {
    $PatchFile = Join-Path $ScriptDir "windows-mcp-speedup.patch"
    & git checkout -- .
    & git apply --ignore-space-change --ignore-whitespace $PatchFile
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to apply windows-mcp-speedup.patch"
    }
    $WinVenvPy = Join-Path $WinMcpDir ".venv\Scripts\python.exe"
    $WinEntryExe = Join-Path $WinMcpDir ".venv\Scripts\windows-mcp.exe"
    $WinAlreadyReady = $false
    if ((Test-Path $WinVenvPy) -and (Test-Path $WinEntryExe)) {
        $PrevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $WinVenvPy -B -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('windows_mcp') else 1)" >$null 2>$null
        if ($LASTEXITCODE -eq 0) { $WinAlreadyReady = $true }
        $ErrorActionPreference = $PrevEap
    }
    $WinLocked = [bool](Get-Process -Name "windows-mcp" -ErrorAction SilentlyContinue)
    if ($WinAlreadyReady -and $WinLocked) {
        Write-Host "  [OK] Source patch applied in-place (active windows-mcp.exe detected; takes effect on MCP Refresh)." -ForegroundColor Green
    } else {
        & $UvExe sync
        if ($LASTEXITCODE -ne 0) {
            throw "uv sync failed in Windows-MCP"
        }
    }
} finally {
    Pop-Location
}

$WinMcpConfigDir = Join-Path $env:USERPROFILE ".windows-mcp"
New-Item -ItemType Directory -Force -Path $WinMcpConfigDir | Out-Null
Copy-Item -Force (Join-Path $ScriptDir "configs\windows-mcp-config.toml") (Join-Path $WinMcpConfigDir "config.toml")

Write-Step "[3/5] Deploying & optimizing Engine 2: computer-control-mcp (windows-ocr-mcp)"
$OcrMcpDir = Join-Path $WorkspaceDir "computer-control-mcp"
if (-not (Test-Path (Join-Path $OcrMcpDir ".git"))) {
    if (Test-Path $OcrMcpDir) { Remove-Item -Recurse -Force $OcrMcpDir }
    Invoke-GitCloneSafe -RepoUrl "https://github.com/AB498/computer-control-mcp.git" -DestDir $OcrMcpDir
}
Push-Location $OcrMcpDir
try {
    $OcrPatchFile = Join-Path $ScriptDir "computer-control-mcp-opti.patch"
    & git checkout -- .
    & git apply --ignore-space-change --ignore-whitespace $OcrPatchFile
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to apply computer-control-mcp-opti.patch"
    }
    $OcrVenvPy = Join-Path $OcrMcpDir ".venv\Scripts\python.exe"
    $OcrEntryExe = Join-Path $OcrMcpDir ".venv\Scripts\computer-control-mcp.exe"
    $OcrAlreadyReady = $false
    if ((Test-Path $OcrVenvPy) -and (Test-Path $OcrEntryExe)) {
        $PrevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $OcrVenvPy -B -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('computer_control_mcp') and importlib.util.find_spec('mcp') else 1)" >$null 2>$null
        if ($LASTEXITCODE -eq 0) { $OcrAlreadyReady = $true }
        $ErrorActionPreference = $PrevEap
    }
    if ($OcrAlreadyReady) {
        $OcrLocked = [bool](Get-Process -Name "computer-control-mcp" -ErrorAction SilentlyContinue)
        if ($OcrLocked) {
            Write-Host "  [OK] Source patch applied in-place (active computer-control-mcp.exe detected; takes effect on MCP Refresh)." -ForegroundColor Green
        } else {
            & $UvExe sync --inexact
            if ($LASTEXITCODE -ne 0) {
                throw "uv sync failed in computer-control-mcp"
            }
        }
    } else {
        if (-not (Test-Path $OcrVenvPy)) {
            & $UvExe venv
        }
        & $UvExe pip install -e .
        if ($LASTEXITCODE -ne 0) {
            throw "uv pip install -e . failed in computer-control-mcp"
        }
        & $UvExe sync
        if ($LASTEXITCODE -ne 0) {
            throw "uv sync failed in computer-control-mcp"
        }
    }
} finally {
    Pop-Location
}

Write-Step "[4/5] Installing Engine 0: chrome-devtools-mcp"
& npm install -g chrome-devtools-mcp@latest
if ($LASTEXITCODE -ne 0) {
    Fail-Friendly `
        -MissingItem "chrome-devtools-mcp global npm package" `
        -WhyNeeded "Connects Antigravity directly to your open Chrome or Edge browser." `
        -FixHint "Check your network/npm permissions and run: npm install -g chrome-devtools-mcp@latest"
}

$NpmBinPath = $null
$ChromeMcpCmd = Get-Command chrome-devtools-mcp.cmd -ErrorAction SilentlyContinue
if ($ChromeMcpCmd -and (Test-Path $ChromeMcpCmd.Source)) {
    $NpmBinPath = $ChromeMcpCmd.Source
} else {
    try {
        $NpmPrefix = (& npm prefix -g 2>$null).Trim()
        if ($NpmPrefix -and (Test-Path (Join-Path $NpmPrefix "chrome-devtools-mcp.cmd"))) {
            $NpmBinPath = Join-Path $NpmPrefix "chrome-devtools-mcp.cmd"
        }
    } catch {}
}
if (-not $NpmBinPath) {
    $NpmBinPath = Join-Path $env:APPDATA "npm\chrome-devtools-mcp.cmd"
}

Write-Step "[5/5] Writing Antigravity MCP config & routing rules"
Copy-Item -Force (Join-Path $ScriptDir "chrome-devtools-launcher.py") (Join-Path $WorkspaceDir "chrome-devtools-launcher.py")
$UserForward = ($env:USERPROFILE -replace "\\", "/")
$PythonForward = ($PythonExe -replace "\\", "/")
$UvForward = ($UvExe -replace "\\", "/")
$NpmBinForward = ($NpmBinPath -replace "\\", "/")

$MergePyScript = @'
import json, sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
python_bin = sys.argv[2]
npm_bin = sys.argv[3]
uv_bin = sys.argv[4]
user_home = sys.argv[5]

data = {}
if cfg_path.exists() and cfg_path.stat().st_size > 0:
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        data = {}

if not isinstance(data, dict):
    data = {}

servers = data.setdefault("mcpServers", {})
servers["chrome-devtools"] = {
    "command": python_bin,
    "args": [
        "-B",
        f"{user_home}/mcp-gui-workspace/chrome-devtools-launcher.py",
    ],
    "env": {
        "CHROME_DEVTOOLS_MCP_BIN": npm_bin,
        "PYTHONIOENCODING": "utf-8",
    },
}
servers["windows-uia-mcp"] = {
    "command": uv_bin,
    "args": [
        "--directory",
        f"{user_home}/mcp-gui-workspace/Windows-MCP",
        "run",
        "windows-mcp",
        "serve",
    ],
    "env": {
        "PYTHONIOENCODING": "utf-8",
    },
}
servers["windows-ocr-mcp"] = {
    "command": uv_bin,
    "args": [
        "--directory",
        f"{user_home}/mcp-gui-workspace/computer-control-mcp",
        "run",
        "computer-control-mcp",
    ],
    "env": {
        "PYTHONIOENCODING": "utf-8",
    },
}

cfg_path.parent.mkdir(parents=True, exist_ok=True)
cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
'@

$CfgTargets = @(
    (Join-Path $env:USERPROFILE ".gemini\config\mcp_config.json"),
    (Join-Path $env:USERPROFILE ".gemini\antigravity\mcp_config.json")
)
$AgyCliDir = Join-Path $env:USERPROFILE ".gemini\antigravity-cli"
$AgyCliBin = Get-Command agy -ErrorAction SilentlyContinue
if ((Test-Path $AgyCliDir) -or $AgyCliBin) {
    $CfgTargets += (Join-Path $AgyCliDir "settings.json")
}

foreach ($TargetCfg in $CfgTargets) {
    $MergePyScript | & $PythonExe -B - $TargetCfg $PythonForward $NpmBinForward $UvForward $UserForward
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to update MCP config: $TargetCfg"
    }
    Write-Host "  Updated: $TargetCfg" -ForegroundColor Green
}

$GlobalRulesDir = Join-Path $env:USERPROFILE ".gemini\config\rules"
New-Item -ItemType Directory -Force -Path $GlobalRulesDir | Out-Null
Copy-Item -Force (Join-Path $ScriptDir "configs\rules.md") (Join-Path $GlobalRulesDir "gui-control.md")

$GlobalGeminiMd = Join-Path $env:USERPROFILE ".gemini\config\GEMINI.md"
if (-not (Test-Path $GlobalGeminiMd)) {
    Copy-Item -Force (Join-Path $ScriptDir "configs\rules.md") $GlobalGeminiMd
}

$AgentsDir = Join-Path $WorkspaceDir ".agents\rules"
New-Item -ItemType Directory -Force -Path $AgentsDir | Out-Null
Copy-Item -Force (Join-Path $ScriptDir "configs\rules.md") (Join-Path $WorkspaceDir ".agents\rules.md")
Copy-Item -Force (Join-Path $ScriptDir "configs\rules.md") (Join-Path $AgentsDir "gui-control.md")
Copy-Item -Force (Join-Path $ScriptDir "README_DEV.md") (Join-Path $WorkspaceDir "README_DEV.md")

Write-Host "`nAll done! Two quick steps to finish:" -ForegroundColor Green
Write-Host "  1. In Chrome (chrome://inspect/#remote-debugging) or Edge (edge://inspect/#remote-debugging), check 'Enable remote debugging'."
Write-Host "  2. In Antigravity -> '...' (Additional Options) -> MCP Servers -> click 'Refresh'."
