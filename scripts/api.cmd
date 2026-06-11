@echo off
setlocal

cd /d "%~dp0\.."

where py >nul 2>nul
if %errorlevel%==0 (
    set PYTHON_CMD=py
) else (
    set PYTHON_CMD=python
)

if exist ".venv\Scripts\uvicorn.exe" (
    ".venv\Scripts\uvicorn.exe" email_assistant.main:app --reload
) else (
    %PYTHON_CMD% -m uvicorn email_assistant.main:app --reload
)
