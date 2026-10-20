"""Fresh installs, interrupted downloads and offline reuse of the same voices."""
from hashlib import sha256
from http.client import IncompleteRead
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from game_speech import SpeechService, valid_model_file
from tools.prepare_speech import download_voice


class VoiceDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="음성 설치 test ")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "models/piper"
        self.model = "en_US-test-medium"
        self.payloads = {
            ".onnx": b"complete model",
            ".onnx.json": json.dumps({"audio": {"sample_rate": 22050},
                                      "phoneme_id_map": {"가": [1]}}, ensure_ascii=False).encode("utf-8"),
        }
        self.specification = {"url": "https://example.invalid/voice", "files": {
            extension: {"size": len(data), "sha256": sha256(data).hexdigest()}
            for extension, data in self.payloads.items()
        }}
        self.opener = Mock(side_effect=lambda request, **kwargs: io.BytesIO(
            self.payloads[".onnx.json" if request.full_url.endswith(".json") else ".onnx"]))

    def download(self, opener=None):
        download_voice(self.model, self.directory, self.specification, opener=opener or self.opener)

    def test_first_install_creates_missing_directories_and_complete_files(self):
        self.download()
        for extension, expected in self.specification["files"].items():
            self.assertTrue(valid_model_file(self.directory / (self.model + extension), expected))
        self.assertEqual(len(list(self.directory.iterdir())), 2)

    def test_verified_models_are_reused_without_internet(self):
        self.download()
        offline = Mock(side_effect=OSError("offline"))
        self.download(offline)
        offline.assert_not_called()

    def test_nonempty_same_size_corrupt_model_is_downloaded_again(self):
        self.download()
        path = self.directory / (self.model + ".onnx")
        path.write_bytes(b"x" * len(self.payloads[".onnx"]))
        self.opener.reset_mock()
        self.download()
        self.assertEqual(path.read_bytes(), self.payloads[".onnx"])
        self.opener.assert_called_once()

    def test_failed_download_preserves_existing_file_and_cleans_temporary_files(self):
        self.directory.mkdir(parents=True)
        path = self.directory / (self.model + ".onnx.json")
        path.write_bytes(b"old damaged config")
        broken = Mock(side_effect=lambda *args, **kwargs: io.BytesIO(b"truncated"))
        with self.assertRaisesRegex(RuntimeError, "run setup again"):
            self.download(broken)
        self.assertEqual(path.read_bytes(), b"old damaged config")
        self.assertEqual(list(self.directory.iterdir()), [path])
        self.assertEqual(broken.call_count, 3)
        self.download()
        self.assertEqual(path.read_bytes(), self.payloads[".onnx.json"])

    def test_interrupted_response_is_retried_before_publishing_the_file(self):
        class Interrupted(io.BytesIO):
            def read(self, size=-1):
                raise IncompleteRead(b"partial", 10)

        opener = Mock(side_effect=[Interrupted(), io.BytesIO(self.payloads[".onnx.json"]), io.BytesIO(self.payloads[".onnx"])])
        self.download(opener)
        self.assertEqual(opener.call_count, 3)
        self.assertEqual(len(list(self.directory.iterdir())), 2)

    def test_speech_service_loads_utf8_bom_configuration(self):
        root = Path(self.temp.name)
        (root / "speech_config.json").write_text(json.dumps({"profiles": {"system": {
            "model": self.model, "label": "시스템 안내"}}}, ensure_ascii=False), encoding="utf-8-sig")
        self.assertEqual(SpeechService(root).profiles["system"]["label"], "시스템 안내")


if __name__ == "__main__":
    unittest.main()
