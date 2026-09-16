@echo off
setlocal
cd /d "%~dp0"
echo WhisperFlow Local now has automatic one-click setup.
echo Starting run_windows.bat...
call run_windows.bat
exit /b %errorlevel%
