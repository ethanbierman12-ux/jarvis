@echo off
REM Start GPT-SoVITS API on http://127.0.0.1:9880 for Jarvis voice clone
cd /d "%~dp0GPT-SoVITS"
if not exist "%~dp0sovits_env\Scripts\python.exe" (
  echo Missing tools\sovits_env — recreate with uv + Python 3.10.
  pause
  exit /b 1
)
echo Starting GPT-SoVITS API on 127.0.0.1:9880 ...
"%~dp0sovits_env\Scripts\python.exe" api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml
pause
