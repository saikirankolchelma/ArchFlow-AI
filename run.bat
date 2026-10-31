@echo off
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
rem Open the browser once the server is up (keep this window open while using the app)
start "" /b powershell -NoProfile -Command "for($i=0;$i -lt 30;$i++){try{Invoke-WebRequest http://127.0.0.1:8000/api/meta -UseBasicParsing -TimeoutSec 1 | Out-Null; Start-Process http://127.0.0.1:8000; break}catch{Start-Sleep 1}}"
.venv\Scripts\python -m app
pause
