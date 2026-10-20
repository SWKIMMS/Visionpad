"""Check this computer's game setup without starting or changing a game."""
import argparse
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import platform
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = {"fastapi": ((0, 110), (1,)), "uvicorn": ((0, 29), (1,)),
                "piper-tts": ((1, 8, 0), (1, 8, 1)), "onnxruntime": (None, None)}
ASSETS = ("water", "soil", "cut", "cook", "crop", "correct", "sleep", "door", "coin",
          "background-basic", "background-minigame", "background-shop", "step", "pickaxe",
          "break", "shine", "destroy", "splash")


def check_setup(root=ROOT, get_version=version, python_version=None, synthesize=False):
    root = Path(root)
    checks = []

    def add(name, ok, detail, fix=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "fix": "" if ok else fix})

    current = python_version or sys.version_info[:3]
    add("Python", current >= (3, 11), ".".join(map(str, current)),
        "Install Python 3.11 or newer, then run the setup file again.")
    for name, (minimum, maximum) in DEPENDENCIES.items():
        try:
            installed = get_version(name)
            numeric = tuple(int(part) for part in installed.split(".") if part.isdigit())
            valid = (minimum is None or numeric >= minimum) and (maximum is None or numeric < maximum)
            # Piper's exact engine version is part of the voice cache identity.
            if name == "piper-tts":
                valid = installed == "1.8.0"
            add(name, valid, installed, "Run setup-mac.command or setup-windows.bat to install requirements.txt.")
        except PackageNotFoundError:
            add(name, False, "Not installed", "Run the setup file in this project folder.")

    required = ("game_app.py", "game_engine.py", "game_speech.py", "speech_queue.py", "game_npc.py", "game_ui.py",
                "game_saves.py", "game_fishing.py", "game_seafood.py", "dotpad.py",
                "spectator_state.py", "game_config.json", "npc_config.json", "requirements.txt",
                "web/game.html", "web/game-audio.js", "web/game-speech.js", "web/game-keys.js",
                "tools/prepare_demo.py", "tools/prepare_speech.py")
    missing = [name for name in required if not (root / name).is_file()]
    add("Game files", not missing, "Complete" if not missing else ", ".join(missing),
        "Copy the complete project source, including web and tools folders.")
    missing = [name for name in ASSETS if not (root / "web/audio" / (name + ".mp3")).is_file()
               or not (root / "web/audio" / (name + ".mp3")).stat().st_size]
    add("Game sounds", not missing, "18 files present" if not missing else ", ".join(missing),
        "Restore web/audio from the project source.")

    config = None
    try:
        config = json.loads((root / "speech_config.json").read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("Invalid voice configuration")
        if not isinstance(config.get("profiles"), dict) or not config["profiles"] or not config.get("samples"):
            raise ValueError("Invalid profiles or samples")
        for profile, entry in config["profiles"].items():
            if not isinstance(entry, dict) or not isinstance(entry.get("model"), str):
                raise ValueError("Invalid voice model entry")
            model = root / "models/piper" / (entry["model"] + ".onnx")
            model_config = model.with_suffix(".onnx.json")
            good = model.is_file() and model.stat().st_size > 0
            reason = "Model missing or empty: " + str(model) if not good else ""
            try:
                values = json.loads(model_config.read_text(encoding="utf-8-sig"))
                good = good and values["audio"]["sample_rate"] > 0 and bool(values["phoneme_id_map"])
            except (OSError, ValueError, KeyError, TypeError) as error:
                good = False
                reason = f"Voice config {model_config}: {type(error).__name__}: {error}"
            add("Voice: " + profile, good, entry["model"] if good else reason or "Invalid voice configuration: " + str(model_config),
                "Run setup-mac.command or setup-windows.bat. If a damaged download remains, rename that model and its .onnx.json file before retrying setup.")
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        add("Voice configuration", False, "speech_config.json is missing or invalid", "Restore speech_config.json.")

    # Probe existing writable locations using disposable files; no saves or caches are removed.
    for name in ("saves", ".cache/speech"):
        directory = root / name
        parent = directory
        while not parent.exists() and parent != root.parent:
            parent = parent.parent
        try:
            with tempfile.TemporaryFile(dir=parent):
                pass
            add("Writable: " + name, not directory.exists() or directory.is_dir(), str(directory),
                "Move the project into a writable folder, outside protected system folders.")
        except OSError as error:
            add("Writable: " + name, False, str(error), "Move the project into a writable folder.")

    if synthesize and config and all(check["ok"] for check in checks):
        sys.path.insert(0, str(root))
        from game_speech import SpeechService
        with tempfile.TemporaryDirectory(prefix="visionpad-voice-check-") as cache:
            service = SpeechService(root, cache_dir=cache)
            for profile in config["profiles"]:
                try:
                    result = service.generate("Voice check. Ready to play.", profile)
                    add("Voice synthesis: " + profile, service.valid_audio(service.audio_path(result["key"])),
                        "Generated valid WAV in temporary storage")
                except Exception as error:
                    add("Voice synthesis: " + profile, False, str(error),
                        "Check Python and audio package support. For an interrupted model download, rename its model/config pair in models/piper and run setup again.")

    return {"ready": all(check["ok"] for check in checks), "platform": platform.platform(),
            "python": sys.executable, "voice_synthesis_requested": synthesize, "checks": checks,
            "scope": "This computer only. Physical pad and headphone perception are not tested."}


def show_report(report):
    for check in report["checks"]:
        print(f"{'OK' if check['ok'] else 'FIX'}  {check['name']}: {check['detail']}")
        if check["fix"]:
            print("     " + check["fix"])
    print("Setup ready." if report["ready"] else "Setup needs attention. Follow the FIX messages above.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthesize", action="store_true", help="Actually generate a short line in each voice")
    parser.add_argument("--report", type=Path, help="Optional JSON report location")
    args = parser.parse_args()
    result = check_setup(synthesize=args.synthesize)
    show_report(result)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
