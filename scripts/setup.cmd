@echo off
setlocal

cd /d "%~dp0\.."

where py >nul 2>nul
if %errorlevel%==0 (
    set PYTHON_CMD=py
) else (
    set PYTHON_CMD=python
)

if not exist ".venv\Scripts\python.exe" (
    %PYTHON_CMD% -m venv .venv
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
".venv\Scripts\python.exe" -m email_assistant init-db

echo.
echo Setup complete.
echo To run tests: scripts\test.cmd
echo To run the demo: scripts\demo.cmd
echo To run the API: scripts\api.cmd
