"""Fixed English voice models and a content-addressed WAV cache.

Generation happens on the game server; browsers play the resulting audio and
never choose an OS voice. Piper is imported only when a model is first used.
"""
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import re
from threading import RLock
import wave


class SpeechUnavailable(RuntimeError):
    pass


def valid_model_file(path, expected=None):
    """Check voice files, including UTF-8 configs and pinned download hashes."""
    path = Path(path)
    expected = expected or {}
    try:
        if not path.is_file() or not path.stat().st_size:
            return False
        if expected.get("size") and path.stat().st_size != expected["size"]:
            return False
        if expected.get("sha256"):
            digest = sha256()
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected["sha256"]:
                return False
        if path.suffix == ".json":
            values = json.loads(path.read_text(encoding="utf-8-sig"))
            return values["audio"]["sample_rate"] > 0 and bool(values["phoneme_id_map"])
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def spoken_text(text):
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(text))
    text = re.sub(r"\s+", " ", text).strip()
    numbers = {"1": "one", "2": "two", "3": "three", "4": "four"}
    text = re.sub(r"\bF([1-4])\b", lambda match: "F " + numbers[match[1]], text)
    text = re.sub(r"\bNPC\b", "N P C", text)
    return re.sub(r"\bDotdew\b", "Dot dew", text)


class PiperSynthesizer:
    def __init__(self, root, profiles):
        self.model_dir = Path(root) / "models" / "piper"
        self.profiles = profiles
        self.voices = {}
        self.identities = {}

    def paths(self, profile):
        model = self.profiles[profile]["model"]
        return self.model_dir / (model + ".onnx"), self.model_dir / (model + ".onnx.json")

    def available(self, profile):
        return all(path.is_file() and path.stat().st_size > 0 for path in self.paths(profile))

    def identity(self, profile):
        model_path, config_path = self.paths(profile)
        if not self.available(profile):
            raise SpeechUnavailable("Voice model missing. Run tools/prepare_speech.py --download.")
        if profile not in self.identities:
            digest = sha256()
            for path in (model_path, config_path):
                with path.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
            try:
                engine_version = version("piper-tts")
            except Exception as error:
                raise SpeechUnavailable("Install requirements.txt to enable fixed voices.") from error
            self.identities[profile] = f"piper-{engine_version}:{digest.hexdigest()}"
        return self.identities[profile]

    def synthesize(self, text, profile, rate, destination):
        try:
            import onnxruntime
            onnxruntime.disable_telemetry_events()
            from piper import PiperVoice, SynthesisConfig
            if profile not in self.voices:
                self.voices[profile] = PiperVoice.load(self.paths(profile)[0])
            with wave.open(str(destination), "wb") as output:
                self.voices[profile].synthesize_wav(
                    text, output, syn_config=SynthesisConfig(length_scale=1 / rate)
                )
        except Exception as error:
            raise SpeechUnavailable(f"Could not generate speech: {error}. Run the setup file and retry.") from error


class SpeechService:
    def __init__(self, root, synthesizer=None, cache_dir=None):
        self.root = Path(root)
        self.config = json.loads((self.root / "speech_config.json").read_text(encoding="utf-8-sig"))
        self.profiles = self.config["profiles"]
        self.synthesizer = synthesizer or PiperSynthesizer(self.root, self.profiles)
        self.cache_dir = Path(cache_dir) if cache_dir is not None else self.root / ".cache" / "speech"
        # Piper model access and writes are serialized, outside the ASGI event loop.
        self.lock = RLock()

    def catalogue(self):
        return {
            "engine": "Piper",
            "language": self.config["language"],
            "profiles": [{"id": key, "label": value["label"], "model": value["model"],
                          "ready": self.synthesizer.available(key)}
                         for key, value in self.profiles.items()],
            "samples": self.config["samples"],
        }

    @staticmethod
    def valid_audio(path):
        try:
            with wave.open(str(path), "rb") as source:
                return source.getnframes() > 0 and source.getnchannels() == 1
        except (OSError, EOFError, wave.Error):
            return False

    def audio_path(self, key):
        if not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("Invalid audio key")
        return self.cache_dir / (key + ".wav")

    def generate(self, text, profile="system", rate=1.0):
        if profile not in self.profiles:
            raise ValueError("Unknown voice profile")
        if not isinstance(rate, (int, float)) or not 0.8 <= rate <= 1.5:
            raise ValueError("Speech rate must be between 0.8 and 1.5")
        original = str(text).strip()
        normalized = spoken_text(original)
        if not normalized or len(original) > 1600:
            raise ValueError("Speech text must contain between 1 and 1600 characters")
        with self.lock:
            identity = self.synthesizer.identity(profile)
            cache_input = {"engine": identity, "profile": profile, "text": normalized,
                           "language": self.config["language"], "rate": float(rate),
                           "pronunciation_version": self.config["pronunciation_version"]}
            key = sha256(json.dumps(cache_input, sort_keys=True).encode()).hexdigest()
            path = self.audio_path(key)
            cached = self.valid_audio(path)
            if not cached:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(".tmp")
                try:
                    self.synthesizer.synthesize(normalized, profile, rate, temporary)
                    if not self.valid_audio(temporary):
                        raise SpeechUnavailable("The voice engine returned empty audio. Retry speech.")
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
            return {"key": key, "url": f"/api/speech/audio/{key}.wav", "text": original,
                    "spoken_text": normalized, "profile": profile,
                    "voice": self.profiles[profile]["model"], "cache_hit": cached}
