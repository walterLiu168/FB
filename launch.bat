@echo off
setlocal enabledelayedexpansion
title FB POSTER

echo ================================
echo   FB POSTER - Facebook Auto Poster
echo ================================

cd /d "%~dp0"

:: Find Python
set "PYTHON="
for %%p in (
    "C:\Users\icemo\AppData\Local\Programs\Python\Python313\python.exe"
    "C:\Python313\python.exe"
    "C:\Program Files\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Program Files\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Program Files\Python311\python.exe"
) do (
    if exist %%p (
        set "PYTHON=%%~p"
        goto :found_python
    )
)
where python >nul 2>nul && for /f "delims=" %%i in ('where python 2^>nul') do set "PYTHON=%%i" && goto :found_python
echo [ERROR] Python not found. Install Python 3.11+
pause & exit /b 1

:found_python
echo Python: !PYTHON!

:: Check/Create .env
if not exist ".env" if exist ".env.template" (
    echo Creating .env from template...
    copy ".env.template" ".env" >nul
)

:: Quick dep check
!PYTHON! -c "import ttkbootstrap" 2>nul || (
    echo Installing dependencies...
    !PYTHON! -m pip install -r fb_auto_poster\requirements.txt --quiet
)

:: Launch
echo Starting FB POSTER...
!PYTHON! run.py
if errorlevel 1 pause
exit /b 0
