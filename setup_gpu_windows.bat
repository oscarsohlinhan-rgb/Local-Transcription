@echo off
setlocal
cd /d "%~dp0"
echo WhisperFlow Local now installs the NVIDIA runtime automatically.
echo Forcing the one-click launcher to re-check dependencies...
if exist ".runtime\bootstrap-v3.ok" del /q ".runtime\bootstrap-v3.ok"
call run_windows.bat
exit /b %errorlevel%
