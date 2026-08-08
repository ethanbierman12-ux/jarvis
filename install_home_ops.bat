@echo off
REM Install / refresh Jarvis home-ops (net watch, backups, edge deps)
cd /d "%~dp0"

set "PY=C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=py -3.13"
if not exist "%PY%" set "PY=python"

echo [home-ops] installing Python packages...
"%PY%" -m pip install -r requirements.txt -r requirements-edge.txt cryptography>=42.0.0
if errorlevel 1 (
  echo pip failed
  pause
  exit /b 1
)

echo [home-ops] running setup...
"%PY%" scripts\setup_home_ops.py
if errorlevel 1 (
  echo setup failed
  pause
  exit /b 1
)

echo.
echo Optional: double-click install_edge_startup.bat to run the headless
echo edge daemon at login (useful if HUD is not always open).
echo.
pause
