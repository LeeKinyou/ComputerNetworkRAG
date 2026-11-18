@echo off
cd /d "%~dp0"
where pwsh >nul 2>nul
if %errorlevel%==0 (
    pwsh -NoLogo -ExecutionPolicy Bypass -File "%~dp0start.ps1"
) else (
    powershell -NoLogo -ExecutionPolicy Bypass -File "%~dp0start.ps1"
)
if errorlevel 1 pause
