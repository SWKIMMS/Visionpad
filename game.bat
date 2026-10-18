@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"

set "VISIONPAD_PYTHON=.venv\Scripts\python.exe"
if not exist "%VISIONPAD_PYTHON%" set "VISIONPAD_PYTHON=venv\Scripts\python.exe"
if not exist "%VISIONPAD_PYTHON%" (
    echo 먼저 setup-windows.bat를 실행해 주세요.
    pause
    exit /b 1
)

"%VISIONPAD_PYTHON%" launch_game.py --port 8003 --prepare-demo
if errorlevel 1 (
    pause
    exit /b 1
)

pause
endlocal
