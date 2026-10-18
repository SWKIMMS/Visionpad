"""Demo preparation keeps exact voice profiles and reports incomplete preparation."""
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from game_speech import spoken_text
from tools.prepare_demo import demo_lines, prepare, ServerSpeech

ROOT = Path(__file__).resolve().parent


class FakeSpeech:
    def __init__(self, ready=True):
        self.ready = ready
        self.calls = []
        self.cached = set()
        self.fail = None

    def catalogue(self):
        return {"profiles": [{"id": profile, "ready": self.ready} for profile in ("system", "shopkeeper")]}

    def generate(self, text, profile, rate):
        self.calls.append((text, profile, rate))
        if text == self.fail:
            raise RuntimeError("Temporary voice failure")
        key = (text, profile, rate)
        hit = key in self.cached
        self.cached.add(key)
        return {"cache_hit": hit, "key": "a" * 64, "url": "/api/speech/audio/clip.wav"}


class DemoSpeechTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lines = demo_lines()

    def test_source_lines_are_unique_and_include_exact_npc_branches(self):
        keys = [(line["profile"], spoken_text(line["text"])) for line in self.lines]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(key[1] for key in keys))
        self.assertFalse(any(line["text"].startswith("Save 1. Day") for line in self.lines))
        npc = json.loads((ROOT / "npc_config.json").read_text())["shopkeeper"]
        text = {line["text"] for line in self.lines if line["profile"] == "shopkeeper"}
        expected = [npc[key] for key in ("greeting", "return_greeting", "goodbye")]
        expected += list(npc["farming"].values()) + list(npc["fishing"].values())
        for line in expected:
            self.assertIn(npc["name"] + ". " + line, text)

    def test_repeat_preparation_reuses_audio_and_rate_has_its_own_cache(self):
        service = FakeSpeech()
        lines = self.lines[:3]
        first = prepare(lines, service)
        second = prepare(lines, service)
        different_rate = prepare(lines, service, rate=1.2)
        self.assertEqual(first["generated"], 3)
        self.assertEqual(second["cache_hits"], 3)
        self.assertTrue(second["complete"])
        self.assertEqual(different_rate["generated"], 3)
        self.assertEqual(service.calls[-1][2], 1.2)

    def test_missing_models_fail_before_generation(self):
        service = FakeSpeech(ready=False)
        with self.assertRaisesRegex(RuntimeError, "Voice setup needed"):
            prepare(self.lines, service)
        self.assertEqual(service.calls, [])

    def test_failed_line_is_not_reported_as_ready_and_can_retry(self):
        service = FakeSpeech()
        service.fail = self.lines[1]["text"]
        result = prepare(self.lines[:3], service)
        self.assertFalse(result["complete"])
        self.assertEqual(result["ready"], 2)
        self.assertEqual(len(result["failures"]), 1)
        service.fail = None
        result = prepare(self.lines[:3], service)
        self.assertTrue(result["complete"])
        self.assertEqual(result["generated"], 1)
        self.assertEqual(result["cache_hits"], 2)

    def test_server_preparation_only_calls_speech_endpoints(self):
        requests = []

        def reply(request, timeout):
            requests.append(request)
            if request.full_url.endswith("/api/speech/voices"):
                result = FakeSpeech().catalogue()
                self.assertIsNone(request.data)
            else:
                self.assertEqual(request.full_url, "http://127.0.0.1:8000/api/speech")
                self.assertEqual(json.loads(request.data)["rate"], 1.0)
                result = {"cache_hit": True, "key": "a" * 64, "url": "/api/speech/audio/clip.wav"}
            return io.BytesIO(json.dumps(result).encode())

        with patch("tools.prepare_demo.urlopen", side_effect=reply):
            result = prepare(self.lines[:3], ServerSpeech("http://127.0.0.1:8000/"))
        self.assertEqual(len(requests), 4)
        self.assertEqual(result["cache_hits"], 3)


if __name__ == "__main__":
    unittest.main()
