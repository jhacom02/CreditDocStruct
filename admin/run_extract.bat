@echo off
setlocal

REM App root
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Please run setup_admin.bat first.
    pause
    exit /b 1
)

if not exist ".env" (
    echo .env not found. Copy .env.example to .env and set INPUT_DIR.
    pause
    exit /b 1
)

echo [CreditDocStruct] Starting PDF extraction...
echo Input folder: see INPUT_DIR in .env
echo.

call .venv\Scripts\python.exe main.py
set EXITCODE=%ERRORLEVEL%

echo.
if %EXITCODE% neq 0 (
    echo Extraction failed. Exit code: %EXITCODE%
) else (
    echo Extraction finished. Check results\ and refresh the admin page.
)
pause
exit /b %EXITCODE%
