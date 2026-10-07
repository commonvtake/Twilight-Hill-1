@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Cafe.ps1" -Outdoor %*
if errorlevel 1 pause
