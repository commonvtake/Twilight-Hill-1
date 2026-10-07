@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Apply-PCProfile.ps1" -DataDirectory "%~dp0DistrictTestData" -Force
pause
