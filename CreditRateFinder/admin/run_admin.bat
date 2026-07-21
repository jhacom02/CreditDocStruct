@echo off
setlocal

cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Please run setup_admin.bat first.
    pause
    exit /b 1
)

echo [CreditRateFinder] Starting admin application...
echo The browser will open automatically. (http://localhost:8501)
echo.
echo To allow access from other PCs on an internal server, use:
echo   --server.address 0.0.0.0

call .venv\Scripts\python.exe -m streamlit run admin\admin_main.py --server.headless false
