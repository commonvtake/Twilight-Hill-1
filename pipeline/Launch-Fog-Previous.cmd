@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Cafe.ps1" -Fog
if errorlevel 1 pause
