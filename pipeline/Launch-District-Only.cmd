@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Cafe.ps1" -District -PCProfile
if errorlevel 1 pause
