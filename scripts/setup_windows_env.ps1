param(
  [switch]$ReinstallVenv
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptPath = Join-Path $PSScriptRoot "build_windows.ps1"
if (-not (Test-Path $scriptPath)) {
  Write-Host "[ERROR] Missing script: $scriptPath" -ForegroundColor Red
  exit 1
}

& $scriptPath -OnlySetup -ReinstallVenv:$ReinstallVenv
exit $LASTEXITCODE
