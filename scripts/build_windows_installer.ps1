param(
  [switch]$ReinstallVenv,
  [string]$AppVersion
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step {
  param([string]$Message)
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Resolve-Iscc {
  $fromEnv = ""
  if ($env:ISCC_PATH) {
    $fromEnv = $env:ISCC_PATH.ToString().Trim()
  }
  if ($fromEnv -and (Test-Path $fromEnv)) {
    return (Resolve-Path $fromEnv).Path
  }

  $fromPath = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
  if ($fromPath -and (Test-Path $fromPath.Source)) {
    return (Resolve-Path $fromPath.Source).Path
  }

  $candidates = @()
  if (${env:ProgramFiles(x86)}) {
    $candidates += (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")
  }
  if ($env:ProgramFiles) {
    $candidates += (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
  }

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return (Resolve-Path $candidate).Path
    }
  }

  throw "ISCC.exe not found. Install Inno Setup 6 first (e.g. winget install JRSoftware.InnoSetup)."
}

function Invoke-AndCheck {
  param(
    [string]$Exe,
    [string[]]$CommandArgs,
    [string]$ErrorMessage
  )
  & $Exe @CommandArgs
  if ($LASTEXITCODE -ne 0) {
    throw $ErrorMessage
  }
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

$buildScript = Join-Path $PSScriptRoot "build_windows.ps1"
$issScript = Join-Path $projectRoot "installer\OfficeSuppliesTracker.iss"
$distExe = Join-Path $projectRoot "dist\OfficeSuppliesTracker\OfficeSuppliesTracker.exe"

if (-not (Test-Path $buildScript)) {
  throw "Missing script: $buildScript"
}
if (-not (Test-Path $issScript)) {
  throw "Missing installer definition: $issScript"
}

if ([string]::IsNullOrWhiteSpace($AppVersion)) {
  $AppVersion = Get-Date -Format "yyyy.MM.dd"
}

try {
  Write-Step "Building desktop executable..."
  $buildArgs = @()
  if ($ReinstallVenv) {
    $buildArgs += "-ReinstallVenv"
  }
  & $buildScript @buildArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Desktop build failed."
  }

  if (-not (Test-Path $distExe)) {
    throw "Desktop build finished but exe not found: $distExe"
  }

  Write-Step "Locating Inno Setup compiler..."
  $iscc = Resolve-Iscc

  Write-Step "Building installer package..."
  Invoke-AndCheck `
    -Exe $iscc `
    -CommandArgs @("/DMyAppVersion=$AppVersion", $issScript) `
    -ErrorMessage "Inno Setup build failed."

  $outputDir = Join-Path $projectRoot "dist-installer"
  $setupPath = Join-Path $outputDir "OfficeSuppliesTracker-Setup-$AppVersion.exe"
  if (-not (Test-Path $setupPath)) {
    throw "Installer build finished but setup file not found: $setupPath"
  }

  Write-Host ""
  Write-Host "Installer build success." -ForegroundColor Green
  Write-Host "SETUP: $setupPath"
  exit 0
}
catch {
  Write-Host ""
  Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
  exit 1
}
