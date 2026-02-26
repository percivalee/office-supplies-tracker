@echo off
setlocal EnableExtensions

cd /d "%~dp0"

where powershell >nul 2>nul
if errorlevel 1 (
  echo [ERROR] powershell.exe not found.
  echo Please run build_windows.ps1 manually in PowerShell.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File ".\build_windows.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Build failed with exit code %EXIT_CODE%.
  pause
  exit /b %EXIT_CODE%
)

echo.
echo Build finished successfully.
pause
exit /b 0
