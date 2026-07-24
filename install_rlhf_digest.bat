@echo off
setlocal
cd /d "%~dp0"

set TASK=JarvisRLHFDigest
set PY=%~dp0.venv\Scripts\python.exe
if not exist "%PY%" set PY=C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe
if not exist "%PY%" set PY=python

schtasks /Delete /TN "%TASK%" /F >nul 2>&1
REM Sunday 21:00 — adapt habits from approve/reject feedback
schtasks /Create /TN "%TASK%" /SC WEEKLY /D SUN /ST 21:00 ^
  /TR "\"%PY%\" \"%~dp0scripts\rlhf_digest.py\"" ^
  /RL LIMITED /F

if errorlevel 1 (
  echo Failed to create scheduled task.
  exit /b 1
)
echo Created weekly task "%TASK%" Sundays at 21:00.
echo Test: "%PY%" "%~dp0scripts\rlhf_digest.py"
endlocal
