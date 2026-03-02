@echo off
setlocal

cd /d "%~dp0\.."
title 打包 OfficeSuppliesTracker.exe

echo 正在构建 Windows 可执行文件...
echo.

if not exist "venv\Scripts\python.exe" (
  echo 未检测到虚拟环境，请先运行一次 start_windows.bat 初始化环境。
  pause
  exit /b 1
)

call "venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo 依赖安装失败，构建中止。
  pause
  exit /b 1
)

call "venv\Scripts\python.exe" -m pyinstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name "OfficeSuppliesTracker" ^
  --add-data "static;static" ^
  --collect-all webview ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  desktop.py

if errorlevel 1 (
  echo 打包失败，请根据上方日志排查。
  pause
  exit /b 1
)

echo.
echo 打包完成：
echo dist\OfficeSuppliesTracker\OfficeSuppliesTracker.exe
echo.
echo 将 dist\OfficeSuppliesTracker 整个目录复制到目标 Windows 机器后，双击 exe 即可运行。
