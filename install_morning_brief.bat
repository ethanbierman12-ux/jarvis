@echo off
setlocal
cd /d "%~dp0"

set TASK=JarvisMorningStandup
set PY=%~dp0.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

schtasks /Delete /TN "%TASK%" /F >nul 2>&1
schtasks /Create /TN "%TASK%" /SC DAILY /ST 06:00 ^
  /TR "\"%PY%\" \"%~dp0scripts\morning_precache.py\"" ^
  /RL LIMITED /F

if errorlevel 1 (
  echo Failed to create scheduled task. Run this bat as your user ^(not necessarily Admin^).
  exit /b 1
)

echo Created daily task "%TASK%" at 06:00.
echo Runs: %PY% scripts\morning_precache.py
echo Output: jarvis\data\morning_standup.txt
echo.
echo Test now:
echo   "%PY%" "%~dp0scripts\morning_precache.py"
endlocal
