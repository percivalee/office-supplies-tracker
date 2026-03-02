@echo off
setlocal EnableExtensions

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows_env.ps1" %*
exit /b %errorlevel%
