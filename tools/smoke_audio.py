"""Check the real speech API in a disposable copy, without touching game saves."""
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from urllib.request import Request, build_opener, ProxyHandler
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from launch_game import stop_owned_server, wait_for_server
from tools.check_setup import ASSETS


def link_or_copy(source, destination):
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def main():
    with tempfile.TemporaryDirectory(prefix="dotdew audio test ") as directory:
        root = Path(directory) / "게임 테스트"
        shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(
            ".git", ".venv", "venv", "__pycache__", "models", ".cache", "saves", "output", ".DS_Store"))
        shutil.copytree(ROOT / "models/piper", root / "models/piper", copy_function=link_or_copy)
        # Exercise Windows-edited UTF-8 files with a BOM in a Korean folder.
        for name in ("speech_config.json", "game_config.json", "npc_config.json"):
            path = root / name
            path.write_text(path.read_text(encoding="utf-8-sig"), encoding="utf-8-sig")
        python = sys.executable
        env = {**os.environ, "PYTHONUTF8": "1"}
        subprocess.run([python, "tools/check_setup.py", "--synthesize"], cwd=root, env=env, check=True)
        subprocess.run([python, "tools/prepare_demo.py", "--list"], cwd=root, env=env, check=True,
                       stdout=subprocess.DEVNULL)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        opener = build_opener(ProxyHandler({}))

        def request(path, body=None, method=None):
            data = None if body is None else json.dumps(body).encode("utf-8")
            call = Request(base + path, data=data, method=method,
                           headers={"Content-Type": "application/json"})
            return opener.open(call, timeout=60)

        with (root / "server.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([python, "-m", "uvicorn", "game_app:app", "--host", "127.0.0.1",
                                        "--port", str(port)], cwd=root, env=env, stdout=log, stderr=log)
            try:
                wait_for_server(process, base, timeout=60)
                with request("/api/state") as response:
                    before = json.load(response)
                with request("/") as response:
                    assert response.status == 200
                for sound in ASSETS:
                    with request(f"/static/audio/{sound}.mp3", method="HEAD") as response:
                        assert response.status == 200 and int(response.headers["Content-Length"]) > 0
                for profile in ("system", "shopkeeper"):
                    line = {"text": "Voice check. Ready to play.", "profile": profile}
                    with request("/api/speech", line) as response:
                        result = json.load(response)
                    with request(result["url"]) as response:
                        with wave.open(io.BytesIO(response.read()), "rb") as audio:
                            assert audio.getnframes() > 0 and audio.getnchannels() == 1
                    with request("/api/speech", line) as response:
                        assert json.load(response)["cache_hit"]
                with request("/api/state") as response:
                    assert json.load(response) == before, "Speech changed game progress"
                print("Audio API ready: both voices, cached WAVs, 18 sounds, UTF-8 BOM and Korean paths.")
            finally:
                stop_owned_server(process)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
