@echo off
REM Install cinematic PC power-on boot + Jarvis chain into Windows Startup
cd /d "%~dp0"

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS=%STARTUP%\00_JarvisPCBoot.vbs"
set "PYW=C:\Users\ethan\AppData\Local\Programs\Python\Python313\pythonw.exe"
set "PY=C:\Users\ethan\AppData\Local\Programs\Python\Python313\python.exe"
set "BOOT=%~dp0pc_boot.py"

if exist "%PYW%" (
  set "LAUNCHER=%PYW%"
) else if exist "%PY%" (
  set "LAUNCHER=%PY%"
) else (
  set "LAUNCHER=pythonw"
)

REM Remove old direct Jarvis startup so we don't double-launch
if exist "%STARTUP%\JarvisHUD.vbs" del /f /q "%STARTUP%\JarvisHUD.vbs"

> "%VBS%" echo Set sh = CreateObject("WScript.Shell")
>> "%VBS%" echo sh.CurrentDirectory = "%~dp0"
>> "%VBS%" echo sh.Run """%LAUNCHER%"" ""%BOOT%""", 0, False

echo.
echo Installed: %VBS%
echo.
echo On login you will see the Arwes power-on sequence, then Jarvis.
echo Preview now:  "%LAUNCHER%" "%BOOT%" --preview
echo Uninstall:    uninstall_pc_boot.bat
echo.
pause
