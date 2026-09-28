@echo off
cd /d "%~dp0"

set "PY=C:\Users\peiyilu\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"

echo [1/2] Checking dependencies...
rem Install only when something is actually missing. requirements.txt is
rem version-pinned, so forcing pip install on every start would fight the
rem pins and fail to boot when offline.
"%PY%" scripts\check_deps.py --missing >nul 2>&1
if not errorlevel 1 goto :start

echo     Missing dependencies - installing from requirements.txt (needs network)...
"%PY%" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo Failed to install dependencies. Please check network and run again.
    pause
    exit /b 1
)

:start
echo [2/2] Starting dashboard. Browser will open http://127.0.0.1:8000
"%PY%" app.py
pause