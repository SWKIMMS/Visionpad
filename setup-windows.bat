@echo off
chcp 65001 > nul
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
where py > nul 2>&1
if not errorlevel 1 (
    py -3.12 -c "import sys" > nul 2>&1
    if not errorlevel 1 (
        py -3.12 tools\setup_game.py
    ) else (
        py -3 tools\setup_game.py
    )
) else (
    where python > nul 2>&1
    if errorlevel 1 (
        echo Python 3.11 이상을 먼저 설치하고 PATH에 추가한 뒤 다시 실행해 주세요.
        pause
        exit /b 1
    )
    python tools\setup_game.py
)
if errorlevel 1 (
    echo 준비하지 못한 항목이 있습니다. 위의 안내를 확인하고 다시 실행하세요.
    pause
    exit /b 1
)
echo 준비가 끝났습니다. game.bat를 열어 주세요.
pause
endlocal
