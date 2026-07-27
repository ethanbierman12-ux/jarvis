@echo off
REM Start Jarvis Hologram HUD (:3000) + Hub API (:8787)
set ROOT=%~dp0..
cd /d "%ROOT%\hub"

echo Starting Hub API on http://127.0.0.1:8787 ...
start "Jarvis Hub API" cmd /k "npm run dev:server"

timeout /t 2 /nobreak >nul

echo Starting Hologram HUD on http://127.0.0.1:3000 ...
start "Jarvis Hologram" cmd /k "npm run dev:dashboard"

timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:3000"
echo.
echo Hologram: http://127.0.0.1:3000
echo Hub API:  http://127.0.0.1:8787/health
echo Leave both windows open.
