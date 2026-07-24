@echo off
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
del /f /q "%STARTUP%\JarvisHUD.vbs" 2>nul
echo Removed JarvisHUD startup entry.
pause
