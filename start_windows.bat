@echo off
setlocal

cd /d "%~dp0"
title 办公用品采购追踪系统

set "FORCE_INSTALL=0"
if /I "%~1"=="--reinstall" set "FORCE_INSTALL=1"

echo 正在启动办公用品采购追踪系统（Windows 桌面版）...
echo.

if not exist "venv\Scripts\python.exe" (
  echo [1/3] 未检测到虚拟环境，正在创建 venv...
  where py >nul 2>nul
  if errorlevel 1 (
    where python >nul 2>nul
    if errorlevel 1 (
      echo 未检测到 Python，请先安装 Python 3.10+ 并勾选 Add Python to PATH。
      pause
      exit /b 1
    )
    python -m venv venv
  ) else (
    py -3 -m venv venv
  )
  if errorlevel 1 (
    echo 创建虚拟环境失败，请检查 Python 安装。
    pause
    exit /b 1
  )
)

set "DEPS_MARKER=venv\.deps_installed"
if "%FORCE_INSTALL%"=="1" del /f /q "%DEPS_MARKER%" >nul 2>nul

if not exist "%DEPS_MARKER%" (
  echo [2/3] 正在安装依赖（首次启动会较慢）...
  call "venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 (
    echo pip 升级失败。
    pause
    exit /b 1
  )
  call "venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
  )
  echo ok> "%DEPS_MARKER%"
) else (
  echo [2/3] 已检测到依赖，跳过安装。
)

echo [3/3] 启动桌面应用...
call "venv\Scripts\python.exe" desktop.py

if errorlevel 1 (
  echo 应用异常退出。
  pause
  exit /b 1
)
