"""Download the configured Piper voices and build reproducible listening samples."""
import argparse
import json
from pathlib import Path
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game_speech import SpeechService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download configured voice models")
    args = parser.parse_args()
    service = SpeechService(ROOT)
    if args.download:
        from piper.download_voices import download_voice
        for model in sorted({profile["model"] for profile in service.profiles.values()}):
            download_voice(model, ROOT / "models" / "piper")
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
    main()
