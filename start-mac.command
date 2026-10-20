#!/bin/zsh
set -eu

VISIONPAD_DIR="${0:A:h}"
cd "$VISIONPAD_DIR"

VISIONPAD_PYTHON="$VISIONPAD_DIR/.venv/bin/python"
if [[ ! -x "$VISIONPAD_PYTHON" && -x "$VISIONPAD_DIR/venv/bin/python" ]]; then
    VISIONPAD_PYTHON="$VISIONPAD_DIR/venv/bin/python"
fi
if [[ ! -x "$VISIONPAD_PYTHON" ]]; then
    print -r -- "먼저 setup-mac.command를 실행해 주세요."
    read -r "?엔터를 누르면 닫힙니다. "
    exit 1
fi

if ! "$VISIONPAD_PYTHON" launch_game.py --port 8000 --prepare-demo; then
    read -r "?위의 안내를 확인한 뒤 엔터를 누르세요. "
    exit 1
fi
