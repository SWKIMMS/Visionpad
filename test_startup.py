"""Startup failures must not reset an existing game or modify unrelated processes."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from importlib.metadata import PackageNotFoundError
from urllib.error import URLError

import launch_game
from tools.check_setup import ASSETS, check_setup
from tools.setup_game import environment_python, setup

ROOT = Path(__file__).resolve().parent
VERSIONS = {"fastapi": "0.143.0", "uvicorn": "0.54.0", "piper-tts": "1.8.0", "onnxruntime": "1.31.0"}


class SetupChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="visionpad setup test ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for path in ROOT.glob("*.py"):
            (self.root / path.name).touch()
        for name in ("web/game.html", "web/game-audio.js", "web/game-speech.js", "web/game-keys.js", "web/hardware.mjs",
                     "tools/prepare_demo.py", "tools/prepare_speech.py", "tools/audio_flow.py", "tools/speech_inventory.py",
                     "game_config.json", "npc_config.json", "requirements.txt"):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
        for name in ASSETS:
            target = self.root / "web/audio" / (name + ".mp3")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"sound")
        config = {"profiles": {"system": {"model": "test-voice"}}, "samples": [{"text": "Hello."}]}
        (self.root / "speech_config.json").write_text(json.dumps(config))
        self.model = self.root / "models/piper/test-voice.onnx"
        self.model.parent.mkdir(parents=True)
        self.model.write_bytes(b"model")
        self.model.with_suffix(".onnx.json").write_text(json.dumps({"audio": {"sample_rate": 22050}, "phoneme_id_map": {"a": [1]}}))

    def report(self, **kwargs):
        return check_setup(self.root, get_version=VERSIONS.__getitem__, python_version=(3, 14, 0), **kwargs)

    def test_complete_setup_reports_ready_without_creating_progress_or_cache(self):
        self.assertTrue(self.report()["ready"])
        self.assertFalse((self.root / "saves").exists())
        self.assertFalse((self.root / ".cache").exists())

    def test_missing_dependency_has_an_actionable_fix(self):
        def absent(name):
            raise PackageNotFoundError(name)
        report = check_setup(self.root, get_version=absent, python_version=(3, 14, 0))
        self.assertFalse(report["ready"])
        self.assertTrue(all(check["fix"] for check in report["checks"] if not check["ok"]))

    def test_broken_model_configuration_is_not_accepted_as_a_ready_voice(self):
        self.model.with_suffix(".onnx.json").write_text("partial download")
        report = self.report()
        self.assertFalse(report["ready"])
        self.assertFalse(next(check for check in report["checks"] if check["name"] == "Voice: system")["ok"])

    def test_missing_sound_and_game_module_are_both_reported(self):
        (self.root / "web/audio/water.mp3").unlink()
        (self.root / "game_fishing.py").unlink()
        failed = {check["name"] for check in self.report()["checks"] if not check["ok"]}
        self.assertEqual(failed, {"Game sounds", "Game files"})

    def test_missing_new_game_modules_and_demo_helpers_are_reported(self):
        for name in ("game_icons.py", "game_village.py", "tools/audio_flow.py", "tools/speech_inventory.py"):
            with self.subTest(file=name):
                path = self.root / name
                path.unlink()
                check = next(item for item in self.report()["checks"] if item["name"] == "Game files")
                self.assertFalse(check["ok"])
                self.assertIn(name, check["detail"])
                path.touch()

    def test_voice_settings_with_korean_and_utf8_bom_ignore_cp949_defaults(self):
        config = self.root / "speech_config.json"
        values = json.loads(config.read_text(encoding="utf-8"))
        values["profiles"]["system"]["label"] = "시스템 안내"
        config.write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8-sig")
        settings = self.model.with_suffix(".onnx.json")
        settings.write_text(json.dumps({"audio": {"sample_rate": 22050}, "phoneme_id_map": {"가": [1]}}, ensure_ascii=False), encoding="utf-8-sig")
        read_text = Path.read_text

        def windows_read(path, encoding=None, **kwargs):
            return read_text(path, encoding=encoding or "cp949", **kwargs)

        with patch.object(Path, "read_text", windows_read):
            self.assertTrue(self.report()["ready"])

    def test_older_python_is_reported_before_starting_any_server(self):
        report = check_setup(self.root, get_version=VERSIONS.__getitem__, python_version=(3, 10, 9))
        self.assertFalse(report["ready"])
        self.assertFalse(report["checks"][0]["ok"])


class StartupTests(unittest.TestCase):
    def test_server_probe_requires_game_title_and_speech_endpoints(self):
        schema = {"info": {"title": "Dotdew Valley"}, "paths": {path: {} for path in ("/api/state", "/api/speech", "/api/speech/voices")}}
        with patch("launch_game.urlopen", return_value=io.BytesIO(json.dumps(schema).encode())):
            self.assertEqual(launch_game.server_status("http://127.0.0.1:8000"), "game")
        schema["paths"] = {}
        with patch("launch_game.urlopen", return_value=io.BytesIO(json.dumps(schema).encode())):
            self.assertEqual(launch_game.server_status("http://127.0.0.1:8000"), "other")
        with patch("launch_game.urlopen", side_effect=URLError(ConnectionRefusedError())), patch("launch_game.port_is_available", return_value=True):
            self.assertEqual(launch_game.server_status("http://127.0.0.1:8000"), "free")

    def test_windows_timeout_does_not_hide_a_free_port(self):
        with patch("launch_game.urlopen", side_effect=URLError(TimeoutError())), patch("launch_game.port_is_available", return_value=True):
            self.assertEqual(launch_game.server_status("http://127.0.0.1:8000"), "free")
        with patch("launch_game.urlopen", side_effect=URLError(TimeoutError())), patch("launch_game.port_is_available", side_effect=OSError("busy")):
            self.assertEqual(launch_game.server_status("http://127.0.0.1:8000"), "other")

    def test_existing_server_is_reused_without_launching_or_stopping_a_process(self):
        with patch("launch_game.server_status", return_value="game"), patch("launch_game.subprocess.Popen") as start:
            self.assertEqual(launch_game.main(["--no-browser"]), 0)
            start.assert_not_called()

    def test_unrelated_busy_port_is_never_replaced(self):
        with patch("launch_game.server_status", return_value="other"), patch("launch_game.subprocess.Popen") as start:
            self.assertEqual(launch_game.main(["--no-browser"]), 1)
            start.assert_not_called()

    def test_startup_failure_terminates_only_the_server_created_by_the_launcher(self):
        process = Mock()
        process.poll.return_value = None
        with patch("launch_game.server_status", return_value="free"), patch("launch_game.check_setup", return_value={"ready": True, "checks": []}), patch("launch_game.subprocess.Popen", return_value=process), patch("launch_game.wait_for_server", side_effect=RuntimeError("startup failed")), patch("launch_game.webbrowser.open") as browser:
            self.assertEqual(launch_game.main([]), 1)
            browser.assert_not_called()
        process.terminate.assert_called_once()

    def test_readiness_failure_is_detected_before_opening_the_browser(self):
        process = Mock()
        process.poll.return_value = 1
        with self.assertRaisesRegex(RuntimeError, "exited"):
            launch_game.wait_for_server(process, "http://127.0.0.1:8000")

    def test_environment_discovery_supports_both_platforms_and_legacy_venv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for tail in ("bin/python", "Scripts/python.exe"):
                target = root / "venv" / tail
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
            self.assertEqual(environment_python(root, windows=False), root / "venv/bin/python")
            self.assertEqual(environment_python(root, windows=True), root / "venv/Scripts/python.exe")

    def test_failed_package_install_stops_before_voice_download(self):
        with tempfile.TemporaryDirectory(prefix="visionpad path with spaces ") as directory:
            root = Path(directory)
            python = root / ".venv/bin/python"
            python.parent.mkdir(parents=True)
            python.touch()
            commands = []

            def fail_install(command, **kwargs):
                commands.append(command)
                if "-r" in command:
                    raise subprocess.CalledProcessError(1, command)
                return subprocess.CompletedProcess(command, 0)

            with patch("tools.setup_game.environment_python", return_value=python):
                with self.assertRaises(subprocess.CalledProcessError):
                    setup(root, run=fail_install)
            self.assertEqual(len(commands), 3)
            self.assertEqual(commands[-1][-1], str(root / "requirements.txt"))

    def test_broken_existing_environment_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / ".venv/user-file"
            marker.parent.mkdir()
            marker.write_text("keep")
            with self.assertRaisesRegex(RuntimeError, "Rename"):
                setup(root, run=Mock())
            self.assertEqual(marker.read_text(), "keep")

    def test_first_setup_installs_only_into_its_new_project_environment(self):
        with tempfile.TemporaryDirectory(prefix="visionpad fresh setup ") as directory:
            root = Path(directory)
            commands = []

            def record(command, **kwargs):
                commands.append(command)
                if command[1:3] == ["-m", "venv"]:
                    target = Path(command[-1]) / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
                    target.parent.mkdir(parents=True)
                    target.touch()
                return subprocess.CompletedProcess(command, 0)

            python = setup(root, run=record)
            self.assertEqual(commands[0][1:3], ["-m", "venv"])
            self.assertTrue(all(command[0] == str(python) for command in commands[1:]))
            self.assertIn("--download", commands[-2])
            self.assertIn("--synthesize", commands[-1])

    def test_old_environment_python_is_rejected_before_installing(self):
        with tempfile.TemporaryDirectory() as directory:
            python = Path(directory) / ".venv/bin/python"
            run = Mock(return_value=subprocess.CompletedProcess([], 1))
            with patch("tools.setup_game.environment_python", return_value=python):
                with self.assertRaisesRegex(RuntimeError, "3.11"):
                    setup(directory, run=run)
            self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
