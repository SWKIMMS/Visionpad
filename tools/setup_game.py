"""Create this project's environment and install its game and fixed voices."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def environment_python(root=ROOT, windows=None):
    windows = sys.platform == "win32" if windows is None else windows
    tail = "Scripts/python.exe" if windows else "bin/python"
    for name in (".venv", "venv"):
        python = Path(root) / name / tail
        if python.is_file():
            return python
    return None


def setup(root=ROOT, run=subprocess.run):
    root = Path(root)
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or newer is required. Install it, then run setup again.")
    python = environment_python(root)
    if python is None:
        environment = root / ".venv"
        if environment.exists():
            raise RuntimeError("The .venv folder exists but its Python is missing. Rename that folder and run setup again.")
        run([sys.executable, "-m", "venv", str(environment)], cwd=root, check=True)
        python = environment_python(root)
        if python is None:
            raise RuntimeError("Python could not create the project environment.")
    checked = run([str(python), "-c", "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"], cwd=root, check=False)
    if checked.returncode:
        raise RuntimeError("The project environment needs Python 3.11 or newer. Rename the old environment folder and run setup again.")
    commands = [[str(python), "-m", "pip", "install", "--upgrade", "pip"],
                [str(python), "-m", "pip", "install", "-r", str(root / "requirements.txt")],
                [str(python), "-m", "pip", "check"],
                [str(python), str(root / "tools/prepare_speech.py"), "--download"],
                [str(python), str(root / "tools/check_setup.py"), "--synthesize"]]
    for command in commands:
        run(command, cwd=root, check=True, env={**os.environ, "PYTHONUTF8": "1"})
    return python


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        python = setup()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Setup did not finish: {error}", file=sys.stderr)
        print("Completed downloads are kept. Fix the issue and run setup again.", file=sys.stderr)
        return 1
    print(f"Setup complete: {python}\nStart with start-mac.command or game.bat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
