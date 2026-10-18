#!/bin/zsh
set -eu
VISIONPAD_DIR="${0:A:h}"
cd "$VISIONPAD_DIR"
if ! command -v python3 >/dev/null 2>&1; then
    print -r -- "Python 3.11 이상을 먼저 설치한 뒤 다시 실행해 주세요."
    read -r "?엔터를 누르면 닫힙니다. "
    exit 1
fi
if ! python3 tools/setup_game.py; then
    read -r "?위의 안내를 확인한 뒤 엔터를 누르세요. "
    exit 1
fi
read -r "?준비가 끝났습니다. 엔터를 누르고 start-mac.command를 여세요. "
