@echo off
title Uninstall Jarvis F3 Wake
cd /d "%~dp0"

set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set VBS=%STARTUP%\JarvisF5Wake.vbs
set LOCK=%~dp0jarvis\data\wake_agent.lock

if exist "%VBS%" (
  del /f /q "%VBS%"
  echo Removed Startup entry.
) else (
  echo No Startup entry found.
)

if exist "%LOCK%" (
  for /f "usebackq delims=" %%p in ("%LOCK%") do (
    taskkill /PID %%p /F >nul 2>&1
  )
  del /f /q "%LOCK%"
)

echo Stopping any wake_agent.py processes...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'wake_agent.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo.
echo F3 wake agent uninstalled.
pause
