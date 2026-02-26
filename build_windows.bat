@echo off
setlocal EnableExtensions

cd /d "%~dp0"

echo [1/6] Detecting Python...
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD where python >nul 2>nul && set "PY_CMD=python"
if not defined PY_CMD goto :no_python
echo Using: %PY_CMD%

echo [2/6] Creating/Reusing virtual environment...
if not exist "venv\Scripts\python.exe" %PY_CMD% -m venv venv || goto :error

call "venv\Scripts\activate.bat" || goto :error

echo [3/6] Upgrading packaging tools...
python -m pip install --upgrade pip setuptools wheel || goto :error

echo [4/6] Installing dependencies...
pip install -r requirements.txt || goto :error

echo [5/6] Preparing offline web assets...
python scripts\prepare_vendor_assets.py || goto :error

echo [6/6] Building EXE...
pyinstaller --noconfirm --clean build.spec || goto :error

echo.
echo Build completed:
echo dist\office-supplies-desktop\office-supplies-desktop.exe
pause
exit /b 0

:no_python
echo [ERROR] Python 3 not found in PATH.
echo Install Python 3.10+ and enable "Add python.exe to PATH".
pause
exit /b 1

:error
echo.
echo Build failed. See errors above.
pause
exit /b 1
