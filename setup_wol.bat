@echo off
title Jarvis Wake-on-LAN setup
cd /d "%~dp0"

echo.
echo This configures THIS PC so a second device can clap-wake it via LAN.
echo Run as Administrator for best results (Fast Startup + WOL flags).
echo.
net session >nul 2>&1
if errorlevel 1 (
  echo Not elevated — right-click setup_wol.bat → Run as administrator
  echo Continuing anyway...
  echo.
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_wol.ps1"
echo.
pause
