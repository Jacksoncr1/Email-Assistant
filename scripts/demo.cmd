@echo off
setlocal

cd /d "%~dp0\.."

where py >nul 2>nul
if %errorlevel%==0 (
    set PYTHON_CMD=py
) else (
    set PYTHON_CMD=python
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m email_assistant demo --tenant-id demo-tenant --email demo@example.com
) else (
    %PYTHON_CMD% -m email_assistant demo --tenant-id demo-tenant --email demo@example.com
)
