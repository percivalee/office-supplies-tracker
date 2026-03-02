@echo off
setlocal EnableExtensions

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows_installer.ps1" %*
exit /b %errorlevel%
