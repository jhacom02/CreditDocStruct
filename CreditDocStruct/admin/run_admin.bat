@echo off
setlocal

cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Please run setup_admin.bat first.
    pause
    exit /b 1
)

echo [CreditDocStruct] Starting admin application...
echo.
echo Local:   http://localhost:8501
echo Network: http://^<this-PC-IP^>:8501
echo   (Other PCs on the same network can open the Network URL.)
echo   If connection fails, allow inbound TCP 8501 in Windows Firewall.
echo.

call .venv\Scripts\python.exe -m streamlit run admin\admin_main.py --server.address 0.0.0.0 --server.port 8501 --server.headless false
