@echo off
setlocal
cd /d "%~dp0"

echo === WhisperFlow Local - Windows GPU setup ===

if not exist .venv\Scripts\activate.bat (
  echo The virtual environment is missing.
  echo Run setup_windows.bat first, then run this file again.
  pause
  exit /b 1
)

call .venv\Scripts\activate.bat || goto :fail
python -m pip install --upgrade pip wheel || goto :fail

echo.
echo Installing NVIDIA CUDA 12 cuBLAS and cuDNN 9 Python runtimes...
echo This is a large download because cuDNN is several hundred MB.
python -m pip install --upgrade nvidia-cublas-cu12 nvidia-cudnn-cu12 || goto :fail

echo.
echo Checking required DLLs...
python -c "import ctypes; [ctypes.WinDLL(x) for x in ('cublas64_12.dll','cublasLt64_12.dll','cudnn64_9.dll')]; print('GPU runtime DLL check passed.')" || goto :fail

echo.
echo GPU runtime setup complete.
echo Close any currently running WhisperFlow Local window and start run_windows.bat again.
pause
exit /b 0

:fail
echo.
echo GPU setup failed. You can still use WhisperFlow Local by choosing Force CPU in the Compute menu.
pause
exit /b 1
