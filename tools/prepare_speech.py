"""Download the configured Piper voices and build reproducible listening samples."""
import argparse
import json
from pathlib import Path
import sys
import wave
import urllib.request
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game_speech import SpeechService

def fallback_download(model, dest_dir):
    """Piper 자체 다운로드 실패 시 HuggingFace에서 직접 파일을 받아옵니다."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # 모델명 파싱 (예: en_US-hfc_female-medium -> en, en_US, hfc_female, medium)
    parts = model.split('-')
    if len(parts) >= 3:
        locale = parts[0]
        lang = locale.split('_')[0]
        voice = parts[1]
        quality = parts[2]
        base_url = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang}/{locale}/{voice}/{quality}/{model}"
    else:
        raise ValueError(f"알 수 없는 모델 형식입니다: {model}")

    for ext in [".onnx", ".onnx.json"]:
        file_url = base_url + ext
        file_dest = dest_dir / (model + ext)
        
        # Download to a temporary file; never leave an incomplete final file.
        print(f"Downloading: {file_url}", flush=True)
        temporary = None
        try:
            req = urllib.request.Request(file_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=60) as response:
                with tempfile.NamedTemporaryFile(dir=dest_dir, suffix=".part", delete=False) as out_file:
                    temporary = Path(out_file.name)
                    shutil.copyfileobj(response, out_file)
                expected = response.headers.get("Content-Length")
                if not temporary.stat().st_size or (expected and temporary.stat().st_size != int(expected)):
                    raise ValueError("Incomplete download")
            if ext == ".onnx.json":
                values = json.loads(temporary.read_text(encoding="utf-8-sig"))
                if values["audio"]["sample_rate"] <= 0 or not values["phoneme_id_map"]:
                    raise ValueError("Invalid voice configuration")
            temporary.replace(file_dest)
        except Exception as error:
            raise RuntimeError(f"Download failed for {model}{ext}: {error}") from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download configured voice models")
    args = parser.parse_args()
    service = SpeechService(ROOT)
    
    if args.download:
        from piper.download_voices import download_voice
        models_dir = ROOT / "models" / "piper"
        models_dir.mkdir(parents=True, exist_ok=True)
        
        for model in sorted({profile["model"] for profile in service.profiles.values()}):
            try:
                # 1. 먼저 Piper 기본 모듈의 다운로드를 시도합니다.
                download_voice(model, models_dir)
            except Exception as e:
                print(f"\nPiper 기본 다운로드에 실패했습니다 ({e}). 대체 주소로 다운로드를 시도합니다...", file=sys.stderr)
                # 2. 실패할 경우 직접 HuggingFace 접속 다운로드 시도
                fallback_download(model, models_dir)
                
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