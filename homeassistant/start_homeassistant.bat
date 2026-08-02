@echo off
title Start Home Assistant
cd /d "%~dp0"

where docker >nul 2>&1
if errorlevel 1 (
  echo Docker is not installed or not on PATH.
  echo Install Docker Desktop, start it, then re-run this script.
  echo Or run: C:\Users\ethan\jarvis\install_homeassistant.bat
  pause
  exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop is not running. Starting it...
  start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
  echo Waiting for Docker engine...
  :wait
  timeout /t 5 /nobreak >nul
  docker info >nul 2>&1
  if errorlevel 1 goto wait
)

echo Pulling / starting Home Assistant and Jarvis MQTT...
docker compose up -d
if errorlevel 1 (
  echo Failed. Is Docker Desktop running?
  pause
  exit /b 1
)

echo.
echo Home Assistant starting.
echo Open: http://127.0.0.1:8123
echo Jarvis MQTT: 127.0.0.1:1883
echo First boot can take 1-3 minutes.
echo.
start "" "http://127.0.0.1:8123"
pause
