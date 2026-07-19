@echo off

REM Silent Jarvis launch — used by shortcuts / F5 wake agent

cd /d "%~dp0"

set PYW=C:\Users\ethan\AppData\Local\Programs\Python\Python313\pythonw.exe

set PY=C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe

if exist "%PYW%" (

  start "" /B "%PYW%" runner.py

) else if exist "%PY%" (

  start "" /B "%PY%" runner.py

) else (

  start "" /B pythonw runner.py

)

