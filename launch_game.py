"""Start a checked local game, or reuse an existing game without resetting it."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import webbrowser

from tools.check_setup import check_setup, show_report

ROOT = Path(__file__).resolve().parent


def server_status(url):
    try:
        with urlopen(url + "/openapi.json", timeout=1) as response:
            schema = json.load(response)
        expected = {"/api/state", "/api/speech", "/api/speech/voices"}
        return "game" if schema.get("info", {}).get("title") == "Dotdew Valley" and expected <= schema.get("paths", {}).keys() else "other"
    except HTTPError:
        return "other"
    except URLError as error:
        return "free" if isinstance(error.reason, ConnectionRefusedError) else "other"
    except (OSError, ValueError):
        return "other"


def wait_for_server(process, url, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Game server exited before it was ready. Check the message above.")
        if server_status(url) == "game":
            return
        time.sleep(0.15)
    raise RuntimeError("Game server did not become ready. Check the setup and port.")


def stop_owned_server(process):
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--prepare-demo", action="store_true", help="Prepare voices through this server before opening the game")
    parser.add_argument("--check", action="store_true", help="Check setup without starting a server or opening a browser")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if args.check:
        report = check_setup(ROOT)
        show_report(report)
        return 0 if report["ready"] else 1

    url = f"http://127.0.0.1:{args.port}"
    process = None
    try:
        status = server_status(url)
        if status == "other":
            raise RuntimeError(f"Port {args.port} is busy or is not a ready Dotdew Valley server. It has been left untouched. Use another port or close that program yourself.")
        if status == "game":
            print(f"Game is already running. Reusing {url} without restarting it.", flush=True)
        else:
            report = check_setup(ROOT)
            show_report(report)
            if not report["ready"]:
                return 1
            process = subprocess.Popen([sys.executable, "-m", "uvicorn", "game_app:app", "--host", "127.0.0.1", "--port", str(args.port)], cwd=ROOT)
            wait_for_server(process, url)
        if args.prepare_demo:
            prepared = subprocess.run([sys.executable, str(ROOT / "tools/prepare_demo.py"), "--server", url], cwd=ROOT)
            if prepared.returncode:
                raise RuntimeError("Demo voices are not fully ready. Check the preparation messages and retry.")
        print(f"Ready: {url}", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        if process is not None:
            print("Keep this window open. Hold F3 in the game to save. Control+C stops this server.", flush=True)
            return process.wait()
        return 0
    except (OSError, RuntimeError) as error:
        print(f"Could not launch: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nGame launcher stopped.")
        return 0
    finally:
        # An already running user's server is never owned or terminated here.
        stop_owned_server(process)


if __name__ == "__main__":
    raise SystemExit(main())
