"""Download the official Bluetooth SDK used by the game's pad adapter."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.prepare_speech import download_file

SOURCE = "https://raw.githubusercontent.com/dotincorp/dotpad-sdk-guide/78661ff559eee6831dc85b5dea9e1e92b2a5798f/Web/3.0.3/DemoApp/src/sdk/"
FILES = {
    "DotPadSDK-3.0.3.js": {"size": 122136, "sha256": "6aa9b3e1821da0b383015e91f71c31ee7e51ba282cffdbe2e38e0b29bfc415be"},
    "DotPadSDK-3.0.3.d.ts": {"size": 5824, "sha256": "777449f4358b3bf8bf18ef96dd5ab4b28f5000884b05b801d2013a2042714ac8"},
}


def main():
    for name, expected in FILES.items():
        download_file(SOURCE + name, ROOT / "web/vendor" / name, expected)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Bluetooth SDK setup failed: {error}", file=sys.stderr)
        raise SystemExit(1)
