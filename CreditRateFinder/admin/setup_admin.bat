@echo off
setlocal

REM Move to app root (CreditRateFinder\CreditRateFinder)
cd /d "%~dp0.."

echo [CreditRateFinder] Starting admin application setup...

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Python 3.11 64-bit is required. Please install it first.
        pause
        exit /b 1
    )
)

echo Installing packages...
call .venv\Scripts\python.exe -m pip install --upgrade pip
call .venv\Scripts\python.exe -m pip install -r requirements.txt
call .venv\Scripts\python.exe -m pip install -r admin\requirements.txt

if errorlevel 1 (
    echo Installation failed.
    pause
    exit /b 1
)

echo.
echo Setup completed successfully.
echo To run the app later, use run_admin.bat.
pause
