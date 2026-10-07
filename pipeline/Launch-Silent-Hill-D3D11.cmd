@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Cafe.ps1" -OldTown -PCProfile -LegacyGraphics
if errorlevel 1 pause
