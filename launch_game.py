"""Start a checked local game, or reuse an existing game without resetting it."""
import argparse
import json
import socket
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler

# Loopback readiness checks must not use system or environment proxies.
urlopen = build_opener(ProxyHandler({})).open
import webbrowser

from tools.check_setup import check_setup, show_report

ROOT = Path(__file__).resolve().parent


def port_is_available(url):
    """Check local binding independently of HTTP timeout/refusal behavior."""
    address = urlsplit(url)
    if address.hostname != "127.0.0.1":
        raise ValueError("The launcher only probes IPv4 loopback.")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        # Do not allow Windows to share a port with an existing listener.
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind((address.hostname, address.port))
    return True


def server_status(url):
    try:
        with urlopen(url + "/openapi.json", timeout=1) as response:
            schema = json.load(response)
        expected = {"/api/state", "/api/speech", "/api/speech/voices"}
        if (isinstance(schema, dict)
                and isinstance(schema.get("info"), dict)
                and isinstance(schema.get("paths"), dict)
                and schema["info"].get("title") == "Dotdew Valley"
                and expected <= schema["paths"].keys()):
            return "game"
        server_status.detail = "HTTP server responded, but its API is not the expected game API."
        return "other"
    except (URLError, OSError, ValueError) as error:
        # Windows may time out before returning connection-refused. A timeout
        # alone says nothing about whether Uvicorn can bind this port.
        try:
            port_is_available(url)
        except OSError as bind_error:
            server_status.detail = f"HTTP probe: {error!r}; local bind: {bind_error!r}"
            return "other"
        return "free"


server_status.detail = "No diagnostic available."


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
            raise RuntimeError(f"Port {args.port} is busy or is not a ready Dotdew Valley server. It has been left untouched. Use another port or close that program yourself.\nDetails: {server_status.detail}")
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
