$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    Write-Host $Label
    & $Action
}

function Resolve-PythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3")
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }
    throw "Python 3 not found in PATH. Please install Python 3.10+ first."
}

$py = Resolve-PythonCommand
$pyExe = $py[0]
$pyArgs = @()
if ($py.Length -gt 1) {
    $pyArgs = $py[1..($py.Length - 1)]
}
$venvPython = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
$venvPip = Join-Path $PSScriptRoot "venv\Scripts\pip.exe"
$venvPyInstaller = Join-Path $PSScriptRoot "venv\Scripts\pyinstaller.exe"

Invoke-Step "[1/6] Creating/Reusing virtual environment..." {
    if (-not (Test-Path $venvPython)) {
        & $pyExe @($pyArgs + @("-m", "venv", "venv"))
    }
}

Invoke-Step "[2/6] Upgrading packaging tools..." {
    & $venvPython -m pip install --upgrade pip setuptools wheel
}

Invoke-Step "[3/6] Installing dependencies..." {
    & $venvPip install -r requirements.txt
}

Invoke-Step "[4/6] Preparing offline web assets..." {
    & $venvPython scripts/prepare_vendor_assets.py
}

Invoke-Step "[5/6] Building EXE..." {
    & $venvPyInstaller --noconfirm --clean build.spec
}

Write-Host ""
Write-Host "[6/6] Build completed:"
Write-Host "dist\office-supplies-desktop\office-supplies-desktop.exe"
