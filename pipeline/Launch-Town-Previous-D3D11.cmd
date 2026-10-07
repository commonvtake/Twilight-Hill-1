@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Cafe.ps1" -Town -PCProfile -LegacyGraphics
if errorlevel 1 pause
