param(
  [switch]$OnlySetup,
  [switch]$ReinstallVenv
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step {
  param([string]$Message)
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-AndCheck {
  param(
    [string]$Exe,
    [string[]]$Args,
    [string]$ErrorMessage
  )
  & $Exe @Args
  if ($LASTEXITCODE -ne 0) {
    throw $ErrorMessage
  }
}

function Resolve-SystemPython {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    return @{
      Exe = "py"
      Prefix = @("-3")
    }
  }
  if (Get-Command python -ErrorAction SilentlyContinue) {
    return @{
      Exe = "python"
      Prefix = @()
    }
  }
  throw "Python 3 is not installed or not in PATH."
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

$logDir = Join-Path $projectRoot "build_logs"
if (-not (Test-Path $logDir)) {
  New-Item -ItemType Directory -Path $logDir | Out-Null
}
$logPath = Join-Path $logDir ("build_windows_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
Start-Transcript -Path $logPath -Force | Out-Null

try {
  $python = Resolve-SystemPython
  $versionText = & $python.Exe @($python.Prefix + @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"))
  if ($LASTEXITCODE -ne 0) {
    throw "Unable to query system Python version."
  }
  $version = [version]($versionText.Trim())
  if ($version -lt [version]"3.10") {
    throw "Python 3.10+ is required. Current: $version"
  }

  if ($ReinstallVenv -and (Test-Path "venv")) {
    Write-Step "Removing existing venv..."
    Remove-Item -Recurse -Force "venv"
  }

  $venvPython = Join-Path $projectRoot "venv\Scripts\python.exe"
  if (-not (Test-Path $venvPython)) {
    Write-Step "Creating virtual environment..."
    Invoke-AndCheck -Exe $python.Exe -Args ($python.Prefix + @("-m", "venv", "venv")) -ErrorMessage "Failed to create virtual environment."
  }

  Write-Step "Upgrading pip..."
  Invoke-AndCheck -Exe $venvPython -Args @("-m", "pip", "install", "--upgrade", "pip") -ErrorMessage "Failed to upgrade pip."

  Write-Step "Installing requirements..."
  Invoke-AndCheck -Exe $venvPython -Args @("-m", "pip", "install", "-r", "requirements.txt") -ErrorMessage "Failed to install requirements."

  if ($OnlySetup) {
    Write-Host ""
    Write-Host "Environment setup complete." -ForegroundColor Green
    Write-Host "Log: $logPath"
    exit 0
  }

  Write-Step "Building exe with PyInstaller..."
  $pyinstallerArgs = @(
    "-m", "pyinstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", "OfficeSuppliesTracker",
    "--add-data", "static;static",
    "--collect-all", "webview",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.protocols.websockets.auto",
    "--hidden-import", "uvicorn.lifespan.on",
    "desktop.py"
  )
  Invoke-AndCheck -Exe $venvPython -Args $pyinstallerArgs -ErrorMessage "PyInstaller build failed."

  $exePath = Join-Path $projectRoot "dist\OfficeSuppliesTracker\OfficeSuppliesTracker.exe"
  if (-not (Test-Path $exePath)) {
    throw "Build finished but exe not found: $exePath"
  }

  Write-Host ""
  Write-Host "Build success." -ForegroundColor Green
  Write-Host "EXE: $exePath"
  Write-Host "Log: $logPath"
  exit 0
}
catch {
  Write-Host ""
  Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "Log: $logPath"
  exit 1
}
finally {
  Stop-Transcript | Out-Null
}
