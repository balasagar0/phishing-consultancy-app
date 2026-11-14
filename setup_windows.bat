@echo off
rem One-time setup on Windows (needs the internet once): Python packages, the website build, the database, and the consultant account.
rem Needs Python 3.11 or later and Node.js 18 or later on the PATH.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating the Python environment...
  python -m venv .venv || goto :fail
)
".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
if not exist ".env" copy ".env.example" ".env" >nul
echo Building the website and app...
pushd frontend
call npm ci || (popd & goto :fail)
call npm run build || (popd & goto :fail)
popd
".venv\Scripts\python.exe" scripts\sync_engine.py --verify || goto :fail
pushd backend
"..\.venv\Scripts\python.exe" -m server.cli init || (popd & goto :fail)
echo.
echo Create the consultant account (it manages client organisations):
set /p MCPD_EMAIL=Your email:
"..\.venv\Scripts\python.exe" -m server.cli create-superadmin --email "%MCPD_EMAIL%"
popd
echo.
echo Setup done. Start the app with start_app.bat
pause
exit /b 0
:fail
echo Setup stopped at the step above. Fix it and run setup_windows.bat again.
pause
exit /b 1
