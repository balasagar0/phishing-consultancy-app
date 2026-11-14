@echo off
rem Starts the website and app on http://127.0.0.1:%MCPD_PORT% (8765 unless .env says otherwise) and opens the browser.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo Run setup_windows.bat first. & pause & exit /b 1 )
if not exist "frontend\dist\index.html" ( echo The website is not built. Run setup_windows.bat first. & pause & exit /b 1 )
set PORT=8765
if exist ".env" for /f "usebackq tokens=1,2 delims==" %%a in (".env") do if /i "%%a"=="MCPD_PORT" set PORT=%%b
echo Starting on http://127.0.0.1:%PORT%  (close this window to stop)
start "" "http://127.0.0.1:%PORT%/"
".venv\Scripts\python.exe" -m uvicorn server.main:app --app-dir backend --host 127.0.0.1 --port %PORT% --no-access-log --timeout-graceful-shutdown 3
