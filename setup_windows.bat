@echo off
setlocal
cd /d "%~dp0"

echo === WhisperFlow Local setup ===
set "PYTHON_CMD="
py -3.12 -V >nul 2>&1 && set "PYTHON_CMD=py -3.12"
if not defined PYTHON_CMD py -3.11 -V >nul 2>&1 && set "PYTHON_CMD=py -3.11"
if not defined PYTHON_CMD py -3.10 -V >nul 2>&1 && set "PYTHON_CMD=py -3.10"
if not defined PYTHON_CMD python -V >nul 2>&1 && set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
  echo Python was not found.
  echo Install Python 3.10-3.12 from https://www.python.org/downloads/ and enable "Add Python to PATH".
  echo Then run this file again.
  pause
  exit /b 1
)

if not exist .venv (
  echo Creating virtual environment...
  %PYTHON_CMD% -m venv .venv || goto :fail
)

call .venv\Scripts\activate.bat || goto :fail
python -m pip install --upgrade pip wheel || goto :fail
python -m pip install -r requirements.txt || goto :fail
python smoke_test.py || goto :fail

echo.
echo Setup complete. Run run_windows.bat.
pause
exit /b 0

:fail
echo.
echo Setup failed. Copy the error above if you want help troubleshooting it.
pause
exit /b 1
