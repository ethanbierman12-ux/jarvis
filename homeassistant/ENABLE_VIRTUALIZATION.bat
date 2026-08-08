@echo off
title Enable virtualization for Docker / Home Assistant
echo ========================================
echo  Docker needs CPU virtualization (VT-x)
echo ========================================
echo.
echo Your PC reports:
echo   Virtualization Enabled In Firmware: NO
echo   CPU: Intel Core i7-4790 (supports VT-x)
echo.
echo Windows cannot turn this on by itself.
echo You must enable it in the motherboard BIOS, then reboot.
echo.
echo --- BIOS steps (STGAUBRON / typical Intel board) ---
echo  1. Save all work. Restart the PC.
echo  2. As it boots, spam Delete or F2 (sometimes F10 / Esc).
echo  3. Find one of these (names vary):
echo       Advanced -^> CPU Configuration
echo       Advanced -^> Intel Virtualization Technology
echo       Processor -^> VT-x / Virtualization Technology
echo       Security  -^> Virtualization
echo  4. Set Intel Virtualization Technology  = Enabled
echo     (also enable VT-d if you see it)
echo  5. Save and Exit (usually F10, then Yes).
echo.
echo After Windows boots, verify with:
echo   systeminfo ^| findstr /i "Virtualization"
echo You want: Virtualization Enabled In Firmware: Yes
echo.
echo Then start Docker Desktop, and run:
echo   %%USERPROFILE%%\homeassistant\start_homeassistant.bat
echo.
echo If you cannot change BIOS (locked PC / no option):
echo   Run Home Assistant on a Raspberry Pi / mini-PC instead,
echo   or skip Docker HA and keep using Alexa / Hue / ntfy from Jarvis.
echo.
pause
