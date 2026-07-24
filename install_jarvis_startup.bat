@echo off
REM Install Jarvis HUD watchdog into the Windows Startup folder
cd /d "%~dp0"

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS=%STARTUP%\JarvisHUD.vbs"
set "PYW=C:\Users\ethan\AppData\Local\Programs\Python\Python313\pythonw.exe"
set "PY=C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe"
set "RUNNER=%~dp0runner.py"

if exist "%PYW%" (
  set "LAUNCHER=%PYW%"
) else if exist "%PY%" (
  set "LAUNCHER=%PY%"
) else (
  set "LAUNCHER=pythonw"
)

> "%VBS%" echo Set sh = CreateObject("WScript.Shell")
>> "%VBS%" echo sh.CurrentDirectory = "%~dp0"
>> "%VBS%" echo sh.Run """%LAUNCHER%"" ""%RUNNER%""", 0, False

echo Installed: %VBS%
echo Jarvis will start with Windows via runner.py
pause
