"""Download the configured Piper voices and build reproducible listening samples."""
import argparse
from http.client import HTTPException
import json
from pathlib import Path
import sys
import wave
import urllib.request
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game_speech import SpeechService, valid_model_file


def download_file(url, target, expected, opener=None, attempts=3):
    """Publish only verified downloads; retain the old file on failure."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    opener = opener or urllib.request.urlopen
    if valid_model_file(target, expected):
        print(f"File ready: {target.name}", flush=True)
        return
    for attempt in range(1, attempts + 1):
        temporary = None
        try:
            print(f"Downloading {target.name} ({attempt}/{attempts})", flush=True)
            request = urllib.request.Request(url, headers={"User-Agent": "Dotdew-Valley"})
            with opener(request, timeout=60) as response:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".download-",
                                                 suffix=target.suffix, delete=False) as output:
                    temporary = Path(output.name)
                    shutil.copyfileobj(response, output)
            if not valid_model_file(temporary, expected):
                raise ValueError("Incomplete or damaged download (size or SHA-256 mismatch)")
            # Both handles are closed before replacement, including on Windows.
            temporary.replace(target)
            return
        except (OSError, ValueError, HTTPException) as error:
            if attempt == attempts:
                raise RuntimeError(f"Could not download {target.name}: {error}. Check the internet connection and run setup again.") from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def download_voice(model, dest_dir, specification, opener=None, attempts=3):
    for extension in (".onnx.json", ".onnx"):
        download_file(specification["url"] + extension, Path(dest_dir) / (model + extension),
                      specification["files"][extension], opener=opener, attempts=attempts)


def prepare_models(service):
    specifications = service.config.get("downloads", {})
    for model in sorted({profile["model"] for profile in service.profiles.values()}):
        if model not in specifications:
            raise RuntimeError(f"Download settings missing for {model}. Restore speech_config.json from the complete project.")
        download_voice(model, service.root / "models" / "piper", specifications[model])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download configured voice models")
    args = parser.parse_args()
    service = SpeechService(ROOT)
    if args.download:
        prepare_models(service)
    output_dir = ROOT / "output" / "audio"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for profile in service.profiles:
        clip_paths = []
        for sample in service.config["samples"]:
            result = service.generate(sample["text"], profile)
            clip_paths.append(service.audio_path(result["key"]))
            manifest.append({"sample": sample["id"], **result})
        target = output_dir / f"{profile}-preview.wav"
        with wave.open(str(target), "wb") as output:
            for index, clip in enumerate(clip_paths):
                with wave.open(str(clip), "rb") as source:
                    if index == 0:
                        output.setnchannels(source.getnchannels())
                        output.setsampwidth(source.getsampwidth())
                        output.setframerate(source.getframerate())
                    output.writeframes(source.readframes(source.getnframes()))
                    output.writeframes(b"\0\0" * int(source.getframerate() * 0.5))
        print(f"Ready: {target.relative_to(ROOT)}", flush=True)
    (output_dir / "samples.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Voice setup failed: {error}", file=sys.stderr)
        raise SystemExit(1)
