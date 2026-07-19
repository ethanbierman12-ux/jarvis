@echo off
REM Install offline steward to Windows Startup (works while Jarvis UI is closed)
set ROOT=%~dp0
set PYW=%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe
if not exist "%PYW%" set PYW=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe
if not exist "%PYW%" set PYW=pythonw

set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set VBS=%STARTUP%\JarvisSteward.vbs

> "%VBS%" echo Set WshShell = CreateObject("WScript.Shell")
>> "%VBS%" echo WshShell.CurrentDirectory = "%ROOT%"
>> "%VBS%" echo WshShell.Run chr(34) ^& "%PYW%" ^& chr(34) ^& " " ^& chr(34) ^& "%ROOT%steward_agent.py" ^& chr(34), 0, False

echo Installed steward to Startup:
echo   %VBS%
echo Starting steward now...
start "" "%PYW%" "%ROOT%steward_agent.py"
echo Done. Steward will keep working offline (weather, vitals, brief, spend).
pause
