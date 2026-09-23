@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title WhisperFlow Local

set "PY_VERSION=3.12.10"
set "RUNTIME_DIR=%CD%\.runtime"
set "PY_DIR=%RUNTIME_DIR%\python"
set "PY_EXE=%PY_DIR%\python.exe"
set "PY_ZIP=%CD%\vendor\python-%PY_VERSION%-embed-amd64.zip"
set "GET_PIP=%CD%\vendor\get-pip.py"
set "BOOTSTRAP_MARKER=%RUNTIME_DIR%\bootstrap-v3.ok"
set "PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/python-%PY_VERSION%-embed-amd64.zip"
set "PIP_URL=https://bootstrap.pypa.io/get-pip.py"

if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"
if not exist "%CD%\vendor" mkdir "%CD%\vendor"

if not exist "%PY_EXE%" call :install_python
if errorlevel 1 goto :fail

call :configure_python_path
if errorlevel 1 goto :fail

if not exist "%BOOTSTRAP_MARKER%" call :install_dependencies
if errorlevel 1 goto :fail

cls
echo ============================================
echo   WhisperFlow Local
echo ============================================
echo.
echo Private Python: %PY_EXE%
echo Starting local UI...
echo.
"%PY_EXE%" launch.py
if errorlevel 1 goto :fail
exit /b 0

:install_python
cls
echo ============================================
echo   WhisperFlow Local - First Run Setup
echo ============================================
echo.
echo No system Python is required.
echo The app is preparing its own private Python %PY_VERSION% runtime.
echo.

if not exist "%PY_ZIP%" (
  echo [1/3] Downloading official Python %PY_VERSION% embedded runtime...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '%PY_URL%' -OutFile '%PY_ZIP%'"
  if errorlevel 1 exit /b 1
) else (
  echo [1/3] Using bundled Python runtime package.
)

echo [2/3] Extracting private Python runtime...
if exist "%PY_DIR%" rmdir /s /q "%PY_DIR%"
mkdir "%PY_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Force -Path '%PY_ZIP%' -DestinationPath '%PY_DIR%'"
if errorlevel 1 exit /b 1

rem Enable normal site-packages in the embeddable Python distribution.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='%PY_DIR%\python312._pth'; $c=Get-Content -Raw $p; $c=$c -replace '#import site','import site'; Set-Content -NoNewline -Encoding ASCII $p $c"
if errorlevel 1 exit /b 1

if not exist "%GET_PIP%" (
  echo [3/3] Downloading pip bootstrap...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '%PIP_URL%' -OutFile '%GET_PIP%'"
  if errorlevel 1 exit /b 1
) else (
  echo [3/3] Using bundled pip bootstrap.
)

"%PY_EXE%" "%GET_PIP%" --no-warn-script-location
if errorlevel 1 exit /b 1
exit /b 0

:configure_python_path
rem Embedded Python only imports modules from directories listed in python312._pth.
rem Add the repository root so the UI, CLI, and sitecustomize are importable.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='%PY_DIR%\python312._pth'; if (-not (Test-Path -LiteralPath $p)) { throw 'Missing embedded Python path file' }; $lines=@(Get-Content -LiteralPath $p); if ($lines -notcontains '..\..') { $lines += '..\..'; Set-Content -LiteralPath $p -Value $lines -Encoding ASCII }"
if errorlevel 1 exit /b 1
exit /b 0

:install_dependencies
cls
echo ============================================
echo   WhisperFlow Local - Installing Components
echo ============================================
echo.
echo This only happens on the first run or after a runtime upgrade.
echo.

"%PY_EXE%" -m pip install --disable-pip-version-check --upgrade pip wheel
if errorlevel 1 exit /b 1

"%PY_EXE%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 exit /b 1

where nvidia-smi >nul 2>&1
if not errorlevel 1 (
  echo.
  echo NVIDIA GPU detected. Installing CUDA 12 cuBLAS and cuDNN 9 runtimes...
  echo This is a large one-time download.
  "%PY_EXE%" -m pip install --disable-pip-version-check nvidia-cublas-cu12 nvidia-cudnn-cu12
  if errorlevel 1 (
    echo.
    echo WARNING: Optional NVIDIA runtime installation failed.
    echo WhisperFlow will still work in CPU mode.
  )
) else (
  echo No NVIDIA GPU runtime detected. CPU mode will be available.
)

"%PY_EXE%" smoke_test.py
if errorlevel 1 exit /b 1

echo bootstrap-v3>"%BOOTSTRAP_MARKER%"
exit /b 0

:fail
echo.
echo ============================================
echo WhisperFlow Local could not start.
echo ============================================
echo.
echo Copy the error above into ChatGPT and I can troubleshoot it.
echo.
pause
exit /b 1
