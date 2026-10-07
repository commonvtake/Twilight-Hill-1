@echo off
if not exist "%~dp0Logs\Connected" mkdir "%~dp0Logs\Connected"
explorer.exe "%~dp0Logs\Connected"
