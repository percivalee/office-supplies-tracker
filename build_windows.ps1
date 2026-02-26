$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Set-Location -Path $PSScriptRoot

$SupportedPythonVersions = @("3.12", "3.11", "3.10")

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    Write-Host $Label
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $Executable $($Arguments -join ' ')"
    }
}

function Get-PythonVersion {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$PrefixArgs
    )

    $versionOutput = & $Executable @($PrefixArgs + @("-c", "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')")) 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $versionOutput) {
        return $null
    }
    return ($versionOutput | Select-Object -Last 1).Trim()
}

function Resolve-PythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in $SupportedPythonVersions) {
            & py "-$v" "-c" "import sys;print(sys.version)" *> $null
            if ($LASTEXITCODE -eq 0) {
                return @{
                    Exe = "py"
                    Args = @("-$v")
                    Version = $v
                    Display = "py -$v"
                }
            }
        }

        $defaultVersion = Get-PythonVersion -Executable "py" -PrefixArgs @("-3")
        if (-not $defaultVersion) {
            $defaultVersion = "unknown"
        }
        throw "Detected Python $defaultVersion via py launcher, but this project requires 3.10-3.12 for PaddleOCR/PaddlePaddle. Install Python 3.12 x64, then rerun."
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        $version = Get-PythonVersion -Executable "python" -PrefixArgs @()
        if ($version -and ($SupportedPythonVersions -contains $version)) {
            return @{
                Exe = "python"
                Args = @()
                Version = $version
                Display = "python"
            }
        }

        if (-not $version) {
            $version = "unknown"
        }
        throw "Detected python $version, but this project requires 3.10-3.12 for PaddleOCR/PaddlePaddle. Install Python 3.12 x64, then rerun."
    }

    throw "Python not found in PATH. Install Python 3.12 x64 first."
}

function Get-ExistingVenvVersion {
    param([Parameter(Mandatory = $true)][string]$VenvPython)

    if (-not (Test-Path $VenvPython)) {
        return $null
    }

    $output = & $VenvPython -c "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($LASTEXITCODE -ne 0 -or -not $output) {
        return $null
    }
    return ($output | Select-Object -Last 1).Trim()
}

try {
    $py = Resolve-PythonCommand
    Write-Host "[0/6] Using Python: $($py.Display) (version $($py.Version))"

    $venvDir = Join-Path $PSScriptRoot "venv"
    $venvPython = Join-Path $venvDir "Scripts\python.exe"
    $existingVenvVersion = Get-ExistingVenvVersion -VenvPython $venvPython

    if ($existingVenvVersion -and ($existingVenvVersion -ne $py.Version)) {
        Write-Host "[1/6] Existing venv uses Python $existingVenvVersion. Recreating with Python $($py.Version)..."
        Remove-Item -Recurse -Force $venvDir
    }

    Invoke-Checked -Label "[1/6] Creating/Reusing virtual environment..." `
        -Executable $py.Exe `
        -Arguments ($py.Args + @("-m", "venv", "venv"))

    $venvPython = Join-Path $venvDir "Scripts\python.exe"

    Invoke-Checked -Label "[2/6] Upgrading packaging tools..." `
        -Executable $venvPython `
        -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")

    Invoke-Checked -Label "[3/6] Installing dependencies..." `
        -Executable $venvPython `
        -Arguments @("-m", "pip", "install", "-r", "requirements.txt")

    Invoke-Checked -Label "[4/6] Preparing offline web assets..." `
        -Executable $venvPython `
        -Arguments @("scripts/prepare_vendor_assets.py")

    Invoke-Checked -Label "[5/6] Building EXE..." `
        -Executable $venvPython `
        -Arguments @("-m", "PyInstaller", "--noconfirm", "--clean", "build.spec")

    Write-Host ""
    Write-Host "[6/6] Build completed:"
    Write-Host "dist\office-supplies-desktop\office-supplies-desktop.exe"
}
catch {
    Write-Host ""
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Build failed."
    exit 1
}
