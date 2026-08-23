@echo off
cd /d "%~dp0"

set "PY=C:\Users\peiyilu\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"

echo [1/2] Installing dependencies (first run only, needs network)...
"%PY%" -m pip install -r requirements.txt --disable-pip-version-check --quiet
if errorlevel 1 (
    echo.
    echo Failed to install dependencies. Please check network and run again.
    pause
    exit /b 1
)

echo [2/2] Starting dashboard. Browser will open http://127.0.0.1:8000
"%PY%" app.py
pause