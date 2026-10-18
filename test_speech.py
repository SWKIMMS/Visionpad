"""Speech cache and NPC integration tests; no model download or audio device needed."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import wave

from game_engine import GameEngine
from game_speech import SpeechService, SpeechUnavailable, spoken_text

ROOT = Path(__file__).resolve().parent


class FakeSynthesizer:
    def __init__(self):
        self.calls = []
        self.revision = "model-v1"
        self.fail = False

    def available(self, profile):
        return True

    def identity(self, profile):
        return self.revision + profile

    def synthesize(self, text, profile, rate, destination):
        self.calls.append((text, profile, rate))
        if self.fail:
            destination.write_bytes(b"partial")
            raise SpeechUnavailable("Temporary failure")
        with wave.open(str(destination), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(22050)
            output.writeframes(b"\0\0" * 500)


class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fake = FakeSynthesizer()
        self.speech = SpeechService(ROOT, self.fake, Path(self.temp.name))

    def test_repeated_text_reuses_complete_audio(self):
        first = self.speech.generate("Gold left: 24 gold.")
        second = self.speech.generate("Gold left: 24 gold.")
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(first["url"], second["url"])
        self.assertEqual(len(self.fake.calls), 1)

    def test_voice_rate_model_and_pronunciation_change_cache_identity(self):
        results = [self.speech.generate("Press F3.")]
        results.append(self.speech.generate("Press F3.", "shopkeeper"))
        results.append(self.speech.generate("Press F3.", rate=1.2))
        self.fake.revision = "model-v2"
        results.append(self.speech.generate("Press F3."))
        self.speech.config["pronunciation_version"] += 1
        results.append(self.speech.generate("Press F3."))
        self.assertEqual(len({result["key"] for result in results}), 5)

    def test_pronunciation_keeps_numbers_and_display_text(self):
        result = self.speech.generate("Press F3. Gold: 24. NPC in Dotdew Valley.")
        self.assertIn("F three", result["spoken_text"])
        self.assertIn("24", result["spoken_text"])
        self.assertIn("F3", result["text"])
        self.assertEqual(spoken_text("  F1\nF4  "), "F one F four")

    def test_partial_audio_is_not_cached_and_retry_succeeds(self):
        self.fake.fail = True
        with self.assertRaises(SpeechUnavailable):
            self.speech.generate("Hello.")
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        self.fake.fail = False
        self.assertFalse(self.speech.generate("Hello.")["cache_hit"])

    def test_corrupt_cache_is_regenerated(self):
        first = self.speech.generate("Hello.")
        self.speech.audio_path(first["key"]).write_bytes(b"corrupt")
        self.assertFalse(self.speech.generate("Hello.")["cache_hit"])
        self.assertEqual(len(self.fake.calls), 2)

    def test_invalid_voice_text_rate_and_path_are_rejected(self):
        for args in [(" ",), ("x" * 1601,), ("Hello", "other"), ("Hello", "system", float("nan"))]:
            with self.assertRaises(ValueError):
                self.speech.generate(*args)
        for key in ["../secret", "A" * 64, "a" * 63]:
            with self.assertRaises(ValueError):
                self.speech.audio_path(key)


class NpcTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = GameEngine(json.loads((ROOT / "game_config.json").read_text()), save_dir=self.temp.name)
        self.engine.travel_to("town")

    def test_npc_is_a_selectable_tactile_target(self):
        self.engine.open_shop()
        marker = next(obj for obj in self.engine.get_objects() if obj["id"] == "rowan")
        result = self.engine.pointer_down(marker["x"], marker["y"])
        self.assertEqual(result["state"]["page"], "npc_dialogue")
        self.assertEqual(result["speech_profile"], "shopkeeper")
        self.assertEqual(result["priority"], "dialogue")
        self.assertIn("Rowan", result["tts"])

    def test_dialogue_topics_do_not_consume_resources_or_time(self):
        before = copy.deepcopy(self.engine.resources)
        time_before = self.engine.time_used_cells
        self.engine.npc_action("shopkeeper", "greeting")
        self.engine.npc_action("shopkeeper", "farming")
        self.engine.npc_action("shopkeeper", "fishing")
        self.assertEqual(self.engine.resources, before)
        self.assertEqual(self.engine.time_used_cells, time_before)

    def test_farming_and_fishing_advice_uses_actual_state(self):
        self.engine.npc_action("shopkeeper", "greeting")
        self.assertIn("planting", self.engine.npc_action("shopkeeper", "farming")["tts"])
        plot = next(iter(self.engine.farm_plots.values()))
        plot.update(seed_id="tomato", mature=False, watered=False)
        self.assertIn("still need water", self.engine.npc_action("shopkeeper", "farming")["tts"])
        plot["mature"] = True
        self.assertIn("ready to harvest", self.engine.npc_action("shopkeeper", "farming")["tts"])
        self.assertIn("will need", self.engine.npc_action("shopkeeper", "fishing")["tts"])
        self.engine.resources["fishing_rod"] = 1
        self.assertIn("have a fishing rod", self.engine.npc_action("shopkeeper", "fishing")["tts"])

    def test_trade_and_goodbye_leave_dialogue_and_revisit_changes_greeting(self):
        self.engine.npc_action("shopkeeper", "greeting")
        result = self.engine.npc_action("shopkeeper", "trade")
        self.assertEqual(result["state"]["page"], "shop_choice")
        self.assertIsNone(result["state"]["dialogue"])
        self.engine.return_to_scene()
        self.assertIn("again", self.engine.npc_action("shopkeeper", "greeting")["tts"])
        self.assertEqual(self.engine.npc_action("shopkeeper", "goodbye")["state"]["page"], "town")

    def test_dialogue_is_unavailable_in_other_locations_and_while_paused(self):
        self.engine.travel_to("farm")
        self.assertIsNone(self.engine.npc_action("shopkeeper", "greeting")["tts"])
        self.engine.travel_to("town")
        self.engine.paused = True  # Evaluation F4 now selects; test the engine pause guard directly.
        self.assertIsNone(self.engine.npc_action("shopkeeper", "greeting")["tts"])

    def test_old_saves_get_npc_defaults_and_current_dialogue_roundtrips(self):
        old = self.engine.snapshot()
        old.pop("npc_visits")
        old.pop("dialogue")
        self.engine.restore_snapshot(old)
        self.assertEqual(self.engine.npc_visits, {})
        self.engine.npc_action("shopkeeper", "greeting")
        saved = self.engine.snapshot()
        self.engine.reset()
        self.engine.restore_snapshot(saved)
        self.assertEqual(self.engine.get_state()["dialogue"]["name"], "Rowan")
        self.assertEqual(self.engine.npc_visits["shopkeeper"], 1)


if __name__ == "__main__":
    unittest.main()
