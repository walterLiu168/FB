@echo off
title License Generator - Admin Only
cls

echo ============================================
echo   License Generator - Admin Only
echo ============================================
echo.

pushd "%~dp0fb_auto_poster"

set PYTHON=C:\1\.venv\Scripts\python.exe

if not exist "%PYTHON%" (
    echo [ERROR] Python not found: %PYTHON%
    pause
    exit /b 1
)

"%PYTHON%" license_generator.py

pause
