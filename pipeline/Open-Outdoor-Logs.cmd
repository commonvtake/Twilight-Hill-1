@echo off
if not exist "%~dp0Logs\Outdoor" mkdir "%~dp0Logs\Outdoor"
explorer.exe "%~dp0Logs\Outdoor"
