@echo off
title Install Home Assistant (Docker)
cd /d "%~dp0"
setlocal

echo ========================================
echo  Jarvis helper - install Home Assistant
echo  via Docker Desktop on this PC
echo ========================================
echo.

REM --- Seed user HA folder (always safe) ---
if not exist "%USERPROFILE%\homeassistant" mkdir "%USERPROFILE%\homeassistant"
if not exist "%USERPROFILE%\homeassistant\config" mkdir "%USERPROFILE%\homeassistant\config"
copy /Y "%~dp0homeassistant\docker-compose.yml" "%USERPROFILE%\homeassistant\docker-compose.yml" >nul
copy /Y "%~dp0homeassistant\start_homeassistant.bat" "%USERPROFILE%\homeassistant\start_homeassistant.bat" >nul
copy /Y "%~dp0homeassistant\ENABLE_VIRTUALIZATION.bat" "%USERPROFILE%\homeassistant\ENABLE_VIRTUALIZATION.bat" >nul
echo [ok] Folder ready: %USERPROFILE%\homeassistant

REM --- Firmware virtualization check (Docker hard requirement) ---
systeminfo | findstr /i /c:"Virtualization Enabled In Firmware: No" >nul 2>&1
if not errorlevel 1 (
  echo.
  echo [!] Virtualization is OFF in BIOS - Docker Desktop will fail.
  echo     Run: %~dp0homeassistant\ENABLE_VIRTUALIZATION.bat
  echo     Enable Intel VT-x in BIOS, reboot, then continue.
  echo.
)

REM --- Docker already present? Skip winget upgrade ---
where docker >nul 2>&1
if not errorlevel 1 (
  echo [ok] Docker CLI already installed - skipping winget upgrade.
  goto :engine
)

where winget >nul 2>&1
if errorlevel 1 (
  echo winget not found. Install Docker Desktop manually from:
  echo   https://www.docker.com/products/docker-desktop/
  pause
  exit /b 1
)

echo [1/3] Ensuring WSL is available...
wsl --install --no-distribution --web-download >nul 2>&1

echo [2/3] Installing Docker Desktop (first time only)...
winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo winget reported a problem. If Docker is already installed, continue.
)

:engine
echo [3/3] Next steps:
echo   1. If BIOS virtualization was off, enable VT-x and reboot first.
echo   2. Start Docker Desktop and wait until it says Running.
echo   3. Run:  %USERPROFILE%\homeassistant\start_homeassistant.bat
echo   4. Browser: http://127.0.0.1:8123  - create your HA account.
echo   5. Profile - Long-Lived Access Tokens - create "jarvis" - paste token in Jarvis chat.
echo.
pause
endlocal
