@echo off
REM Start Jarvis edge daemon (net watch / backups / deadman / space) at login
cd /d "%~dp0"

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS=%STARTUP%\JarvisEdge.vbs"
set "PYW=C:\Users\ethan\AppData\Local\Programs\Python\Python313\pythonw.exe"
set "PY=C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe"

if exist "%PYW%" (
  set "LAUNCHER=%PYW%"
) else if exist "%PY%" (
  set "LAUNCHER=%PY%"
) else (
  set "LAUNCHER=pythonw"
)

> "%VBS%" echo Set sh = CreateObject("WScript.Shell")
>> "%VBS%" echo sh.CurrentDirectory = "%~dp0"
>> "%VBS%" echo sh.Run """%LAUNCHER%"" -m jarvis.edge_daemon", 0, False

echo Installed: %VBS%
echo Edge daemon will start at login (hidden).
echo Remove that VBS from Startup to disable.
echo NOTE: If Jarvis HUD is also running, you may get duplicate net-watch alerts.
pause
