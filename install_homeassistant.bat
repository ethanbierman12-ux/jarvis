@echo off
title Install Home Assistant (Docker)
cd /d "%~dp0"

echo ========================================
echo  Jarvis helper — install Home Assistant
echo  via Docker Desktop on this PC
echo ========================================
echo.

where winget >nul 2>&1
if errorlevel 1 (
  echo winget not found. Install Docker Desktop manually from:
  echo   https://www.docker.com/products/docker-desktop/
  pause
  exit /b 1
)

echo [1/4] Ensuring WSL is available...
wsl --install --no-distribution --web-download >nul 2>&1

echo [2/4] Installing Docker Desktop (may take several minutes)...
winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo winget reported a problem. If Docker is already installed, continue.
)

echo [3/4] Creating HA folder...
if not exist "%USERPROFILE%\homeassistant" mkdir "%USERPROFILE%\homeassistant"
copy /Y "%~dp0homeassistant\docker-compose.yml" "%USERPROFILE%\homeassistant\docker-compose.yml" >nul 2>&1
if not exist "%USERPROFILE%\homeassistant\docker-compose.yml" (
  echo Writing compose file...
)

echo [4/4] Next steps for YOU:
echo   1. If Windows asked for a reboot (WSL/Docker), reboot now.
echo   2. Start "Docker Desktop" from the Start menu and wait until it says Running.
echo   3. Run:  %USERPROFILE%\homeassistant\start_homeassistant.bat
echo   4. Browser: http://127.0.0.1:8123  — create your HA account.
echo   5. Profile → Long-Lived Access Tokens → create "jarvis" → paste token back in chat.
echo.
echo Data folder: %USERPROFILE%\homeassistant\config
echo.
pause
