@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Environment not installed yet. Starting setup first...
  call setup_windows.bat
  if errorlevel 1 exit /b 1
)
call .venv\Scripts\activate.bat
python webapp.py
