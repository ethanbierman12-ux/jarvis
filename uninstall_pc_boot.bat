@echo off
REM Remove PC power-on boot from Startup (optionally restore Jarvis-only)
cd /d "%~dp0"

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS=%STARTUP%\00_JarvisPCBoot.vbs"

if exist "%VBS%" (
  del /f /q "%VBS%"
  echo Removed: %VBS%
) else (
  echo PC boot shortcut was not installed.
)

echo.
echo To restore Jarvis-only on startup, run: install_jarvis_startup.bat
echo.
pause
