"""Fishing speech, sound events and lifecycle; no changes to game balance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from game_engine import GameEngine

ROOT = Path(__file__).resolve().parent


class FishingAudioIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        config = json.loads((ROOT / "game_config.json").read_text())
        self.engine = GameEngine(config, save_dir=self.temp.name)
        self.engine.travel_to("fishing")

    def cast(self, grade):
        self.engine.resources["fishing_rod"] = 1
        self.engine.fishing_target = [30, 20]
        with patch("game_fishing.random.choices", return_value=[grade]):
            return self.engine.cast_fishing(30, 20)

    def test_lake_can_be_explored_without_rod_and_hover_does_not_speak_target(self):
        self.assertTrue(self.engine.get_state()["fishing"]["active"])
        before = self.engine.time_used_cells
        response = self.engine.pointer_move(30, 20)
        self.assertIsNone(response["tts"])
        self.assertEqual(self.engine.time_used_cells, before)
        response = self.engine.pointer_down(30, 20)
        self.assertIn("Fishing rod required", response["tts"])
        self.assertEqual(self.engine.fishing_attempts, 0)
        self.assertEqual(self.engine.time_used_cells, before)

    def test_cast_outside_lake_does_not_spend_time_or_play_catch_cues(self):
        self.engine.resources["fishing_rod"] = 1
        response = self.engine.cast_fishing(0, 0)
        self.assertEqual(response["tts"], "Cast inside the lake.")
        self.assertEqual(response["sound_events"], [])
        self.assertEqual(self.engine.time_used_cells, 0)

    def test_success_and_rare_success_emit_grouped_cues_with_correct_speech(self):
        for grade, sounds in [("low", ["splash"]), ("high", ["splash", "shine"])]:
            with self.subTest(grade=grade):
                before = copy.deepcopy(self.engine.resources["fish"])
                response = self.cast(grade)
                self.assertEqual(response["sound_events"], [{"kind": "one_shot_group", "sounds": sounds}])
                fish = self.engine.fishing_last_catch
                amount = self.engine.resources["fish"][fish["id"]] - before.get(fish["id"], 0)
                self.assertIn(f"{fish['label']} {amount} caught.", response["tts"])
                self.assertEqual(response["speech_profile"], "system")
                self.assertEqual(response["priority"], "action")
                self.assertNotIn(grade, response["tts"].lower())

    def test_miss_has_no_catch_sound_or_rod_wear_but_spends_cast_time(self):
        response = self.cast("miss")
        self.assertEqual(response["sound_events"], [])
        self.assertEqual(response["tts"], "No catch. Try another spot.")
        self.assertEqual(self.engine.rod_catches, 0)
        self.assertEqual(self.engine.time_used_cells, self.engine.get_action_cost("fish"))

    def test_holding_and_dragging_do_not_repeat_casts(self):
        self.engine.resources["fishing_rod"] = 1
        with patch("game_fishing.random.choices", return_value=["miss"]):
            self.engine.pointer_down(30, 20)
            self.engine.pointer_down(30, 20)
            self.engine.pointer_drag(31, 20)
            self.engine.pointer_up(31, 20)
        self.assertEqual(self.engine.fishing_attempts, 1)

    def test_breaking_cast_keeps_reward_and_announces_destruction(self):
        self.engine.rod_catches = self.engine.fishing_config()["rod_safe_catches"]
        with patch("game_fishing.random.random", return_value=0):
            response = self.cast("high")
        self.assertEqual(self.engine.resources["fishing_rod"], 0)
        self.assertEqual(sum(self.engine.resources["fish"].values()), 1)
        self.assertIn("Fishing rod broken", response["tts"])
        self.assertEqual(response["sound_events"][0]["sounds"], ["splash", "shine"])
        self.assertTrue(any(event["kind"] == "item_destroyed" for event in response["sound_events"]))

    def test_pause_menu_and_exit_hide_target_and_resuming_restores_guidance(self):
        target = list(self.engine.fishing_target)
        self.engine.paused = True  # Pause-state support remains; evaluation F4 is selection.
        self.assertFalse(self.engine.get_state()["fishing"]["active"])
        self.engine.paused = False
        self.assertEqual(self.engine.get_state()["fishing"]["target"], target)
        state = self.engine.handle_command("minimap")["state"]
        self.assertFalse(state["fishing"]["active"])
        self.assertIsNone(state["fishing"]["target"])
        self.assertTrue(self.engine.handle_command("minimap")["state"]["fishing"]["active"])
        self.assertFalse(self.engine.handle_command("left")["state"]["fishing"]["active"])

    def test_last_cast_keeps_result_but_stops_guidance_at_night(self):
        self.engine.time_used_cells = self.engine.time_total_cells - 1
        response = self.cast("high")
        self.assertTrue(response["state"]["day_ended"])
        self.assertFalse(response["state"]["fishing"]["active"])
        self.assertIsNone(response["state"]["fishing"]["target"])
        self.assertIn("caught.", response["tts"])
        self.assertIn("Night.", response["tts"])
        self.assertEqual(response["sound_events"][0]["sounds"], ["splash", "shine"])


if __name__ == "__main__":
    unittest.main()
