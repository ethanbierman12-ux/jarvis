@echo off
title Install Jarvis F3 Wake
cd /d "%~dp0"

set PYW=C:\Users\ethan\AppData\Local\Programs\Python\Python313\pythonw.exe
if not exist "%PYW%" set PYW=C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe
if not exist "%PYW%" set PYW=pythonw

set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set VBS=%STARTUP%\JarvisF5Wake.vbs
set AGENT=%~dp0wake_agent.py

echo Creating Startup launcher at:
echo   %VBS%

> "%VBS%" echo Set sh = CreateObject("WScript.Shell")
>> "%VBS%" echo sh.CurrentDirectory = "%~dp0"
>> "%VBS%" echo sh.Run chr(34) ^& "%PYW%" ^& chr(34) ^& " " ^& chr(34) ^& "%AGENT%" ^& chr(34), 0, False

echo Stopping any old wake agent...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'wake_agent.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

timeout /t 1 /nobreak >nul

echo Starting wake agent in background...
start "" wscript "%VBS%"

timeout /t 1 /nobreak >nul

echo.
echo ========================================
echo  Double-tap F3 is now global (single tap does not launch).
echo  - Closed Jarvis  → double-tap F3 launches (via runner watchdog)
echo  - Open Jarvis    → single F3 focuses; double-tap soft-reloads
echo  - Crash recover OFF by default (no phantom relaunches)
echo  - No START spam
echo  Survives reboot (Windows Startup).
echo ========================================
echo.
echo Uninstall: uninstall_f5_wake.bat
echo.
pause
