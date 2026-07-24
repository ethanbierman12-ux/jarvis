@echo off

REM Fast Jarvis launch — no pip on every start (use run.bat deps once)

cd /d "%~dp0"

set PY=C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe

if not exist "%PY%" set PY=python



if /I "%~1"=="deps" (

  echo Installing / updating dependencies…

  "%PY%" -m pip install -r requirements.txt

  goto :eof

)



if /I "%~1"=="wake" (

  echo Installing F3 wake agent…

  call "%~dp0install_f5_wake.bat"

  goto :eof

)



REM Watchdog keeps Jarvis alive: exit 0 = reload, exit 99 = stop, other = recover
"%PY%" runner.py

if errorlevel 1 pause

