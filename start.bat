@echo off
title FB Auto Poster

echo ============================================
echo   FB Auto Poster - Launch Tool
echo ============================================
echo.

pushd "%~dp0fb_auto_poster"

set PYTHON=C:\1\.venv\Scripts\python.exe

if not exist "%PYTHON%" (
    echo [ERROR] Python not found: %PYTHON%
    pause
    exit /b 1
)

echo [INFO] Starting application...
start "" /B "%PYTHON%" main.py

timeout /t 2 /nobreak >nul
exit
