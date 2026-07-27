@echo off
REM Call before Windows sleep/shutdown so companion can pick up context.
REM Install: Task Scheduler or Group Policy shutdown script pointing here.
setlocal
cd /d "%~dp0.."

if "%COMPANION_TOKEN%"=="" (
  echo Set COMPANION_TOKEN env var to your companion_token from settings.
  exit /b 1
)

set PORT=8766
if not "%COMPANION_PORT%"=="" set PORT=%COMPANION_PORT%

powershell -NoProfile -Command "$body = @{ target = 'ipad'; context = 'PC shutting down'; project = (Get-Location).Path } | ConvertTo-Json; try { Invoke-RestMethod -Method Post -Uri ('http://127.0.0.1:%PORT%/api/handoff?token=' + $env:COMPANION_TOKEN) -ContentType 'application/json' -Body $body -TimeoutSec 4 | Out-Null; Write-Output 'ok' } catch { $_.Exception.Message }"

exit /b 0
