"""Semantic sound responses from actual game actions; isolated from player saves."""
import json
from pathlib import Path
import tempfile
import unittest

from game_engine import GameEngine

ROOT = Path(__file__).resolve().parent


class ActionSoundTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = GameEngine(json.loads((ROOT / 'game_config.json').read_text()), save_dir=self.temp.name)

    def test_travel_and_shop_entry_emit_the_matching_recording_once(self):
        response = self.engine.handle_command('right')
        self.assertEqual(response['sound_events'], [{'kind':'one_shot','sound':'step','direction':'right'}])
        response = self.engine.open_shop()
        self.assertEqual(response['sound_events'], [{'kind':'one_shot','sound':'door'}])

    def test_buying_and_selling_emit_coin_but_rejections_do_not(self):
        bought = self.engine.buy_shop_item('seed','tomato')
        self.assertEqual(bought['sound_events'], [{'kind':'one_shot','sound':'coin'}])
        self.engine.resources['crops']['tomato'] = 1
        sold = self.engine.sell_shop_item('crop','tomato')
        self.assertEqual(sold['sound_events'], [{'kind':'one_shot','sound':'coin'}])
        self.engine.resources['coin'] = 0
        rejected = self.engine.buy_shop_item('seed','tomato')
        self.assertEqual(rejected['sfx'], 'error')
        self.assertEqual(rejected['sound_events'], [])

    def test_care_and_harvest_completion_keep_success_feedback(self):
        engine = self.engine
        plot_id = engine.get_unlocked_plot_defs()[0]['id']
        engine.farm_plots[plot_id].update(seed_id='tomato',mature=False,watered=False)
        engine.start_care_minigame(plot_id,'water')
        engine.care_collected_ids = {target['id'] for target in engine.care_targets}
        self.assertEqual(engine.finish_care_minigame()['sfx'], 'water')
        engine.start_care_minigame(plot_id,'fertilizer')
        engine.care_collected_ids = {target['id'] for target in engine.care_targets}
        self.assertEqual(engine.finish_care_minigame()['sfx'], 'fertilize')
        engine.farm_plots[plot_id]['mature'] = True
        engine.start_harvest_minigame(plot_id)
        engine.harvest_collected_ids = {target['id'] for target in engine.harvest_targets}
        self.assertEqual(engine.finish_harvest_minigame()['sfx'], 'harvest')

    def test_cooking_completion_has_success_feedback(self):
        engine = self.engine
        recipe_id = next(key for key,value in engine.config['recipes'].items() if not value.get('seafood'))
        recipe = engine.get_recipe_config(recipe_id)
        engine.resources['crops'].update(recipe['ingredients'])
        engine.selected_recipe_id = recipe_id
        self.assertEqual(engine.finish_cooking_success()['sfx'], 'cooking_success')

    def test_menus_save_and_load_have_feedback_without_spending_time(self):
        engine = self.engine
        self.assertEqual(engine.handle_command('minimap')['sfx'], 'open_page')
        engine.handle_command('minimap')
        self.assertEqual(engine.handle_command('resources')['sfx'], 'open_page')
        engine.handle_command('resources')
        self.assertEqual(engine.handle_command('save')['sfx'], 'saved')
        self.assertEqual(engine.handle_command('load')['sfx'], 'open_page')
        self.assertEqual(engine.load_game(engine._save_slots[0]['id'])['sfx'], 'loaded')
        self.assertEqual(engine.time_used_cells, 0)

    def test_fishing_miss_and_invalid_cast_have_different_feedback(self):
        from unittest.mock import patch
        engine = self.engine
        engine.travel_to('fishing')
        self.assertEqual(engine.cast_fishing(30,20)['sfx'], 'error')
        engine.resources['fishing_rod'] = 1
        self.assertEqual(engine.cast_fishing(0,0)['sfx'], 'error')
        with patch('game_fishing.random.choices',return_value=['miss']):
            result = engine.cast_fishing(30,20)
        self.assertEqual(result['sfx'], 'fishing_miss')
        self.assertEqual(result['sound_events'], [])


if __name__ == '__main__':
    unittest.main()
