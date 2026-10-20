"""Real game results drive NPC memory and remaining-target sound guidance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from game_engine import GameEngine

ROOT = Path(__file__).resolve().parent
MEMORY = ('activity_counts', 'activity_serial', 'recent_activity', 'npc_reactions', 'activity_history_complete')


class GameplayAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = GameEngine(json.loads((ROOT/'game_config.json').read_text()), save_dir=self.temp.name)

    def harvest(self):
        e = self.engine
        e.travel_to('farm')
        plot = e.get_unlocked_plot_defs()[0]['id']
        e.farm_plots[plot].update(seed_id='tomato', mature=True, watered=True)
        e.start_harvest_minigame(plot)
        targets = list(e.harvest_targets)
        e.pointer_down(targets[0]['x'], targets[0]['y'])
        for target in targets[1:]:
            e.pointer_drag(target['x'], target['y'])
        e.pointer_up(targets[-1]['x'], targets[-1]['y'])

    def talk(self):
        self.engine.travel_to('town')
        return self.engine.npc_action('shopkeeper', 'greeting')

    def test_real_harvest_gets_a_first_reaction_without_extra_resources_or_time(self):
        self.harvest()
        e = self.engine
        self.assertEqual(e.recent_activity['kind'], 'harvest')
        before = copy.deepcopy(e.resources), e.time_used_cells, e.day
        text = self.talk()['tts']
        self.assertIn('first harvest', text)
        self.assertIn('Tomato', text)
        self.assertEqual((e.resources, e.time_used_cells, e.day), before)

    def test_reaction_is_remembered_across_save_and_dialogue_replay(self):
        self.harvest()
        first = self.talk()['state']['dialogue']['text']
        snapshot = self.engine.snapshot()
        self.engine.reset()
        self.engine.restore_snapshot(snapshot)
        self.assertEqual(self.engine.get_state()['dialogue']['text'], first)
        self.engine.npc_action('shopkeeper', 'goodbye')
        self.assertNotIn('first harvest', self.talk()['tts'])

    def test_old_progress_does_not_claim_a_first_ever_harvest(self):
        old = self.engine.snapshot()
        for key in MEMORY:
            old.pop(key)
        self.engine.restore_snapshot(old)
        self.harvest()
        self.assertFalse(self.engine.recent_activity['first'])
        self.assertNotIn('first harvest', self.talk()['tts'])

    def test_first_fishing_catch_uses_the_actual_fish_name(self):
        e = self.engine
        e.travel_to('fishing')
        e.resources['fishing_rod'] = 1
        with patch('game_fishing.random.choices', return_value=['low']):
            e.cast_fishing(*e.fishing_target)
        self.assertEqual(e.activity_counts['fishing'], 1)
        text = self.talk()['tts']
        self.assertIn('first catch', text)
        self.assertIn(e.recent_activity['item'], text)

    def test_rejected_action_does_not_record_a_success(self):
        e = self.engine
        e.travel_to('fishing')
        e.resources['fishing_rod'] = 0
        e.cast_fishing(*e.fishing_target)
        self.assertIsNone(e.recent_activity)
        self.assertEqual(e.activity_counts, {})

    def test_real_tool_break_gets_replacement_advice(self):
        e = self.engine
        e.config['mine'].update(pickaxe_safe_hits=0, pickaxe_break_increment=1)
        e.resources['pickaxe'] = 1
        e.travel_to('mine')
        e.hit_mine_rock(e.mine_rocks[0]['id'])
        self.assertEqual(e.resources['pickaxe'], 0)
        self.assertEqual(e.recent_activity['kind'], 'tool_broken')
        self.assertIn('Pickaxe broke', self.talk()['tts'])

    def test_cooking_reaction_is_recorded_only_after_a_dish_is_created(self):
        e = self.engine
        recipe = 'tomato_carrot_stew'
        for ingredient, count in e.get_recipe_config(recipe)['ingredients'].items():
            e.resources['crops'][ingredient] = count
        e.selected_recipe_id = recipe
        e.finish_cooking_success()
        self.assertEqual(e.activity_counts['cooking'], 1)
        self.assertGreater(e.resources['foods'][recipe], 0)
        self.assertIn('first dish', self.talk()['tts'])

    def test_guidance_excludes_collected_targets_and_stops_during_pause(self):
        e = self.engine
        e.travel_to('farm')
        plot = e.get_unlocked_plot_defs()[0]['id']
        e.farm_plots[plot].update(seed_id='tomato', mature=False, watered=False)
        e.open_plot_detail(plot)
        e.start_care_minigame(plot, 'water')
        before = e.get_state()['audio_guidance']
        target = before['targets'][0]
        e.pointer_down(target['x'], target['y'])
        after = e.get_state()['audio_guidance']
        self.assertNotIn(target['id'], {item['id'] for item in after['targets']})
        self.assertGreater(after['completed'], 0)
        self.assertEqual(before['total'], after['total'])
        e.paused = True  # Current evaluation controls reserve F4 for selecting.
        self.assertEqual(e.get_state()['audio_guidance']['targets'], [])
        e.paused = False
        self.assertGreater(len(e.get_state()['audio_guidance']['targets']), 0)

    def test_mined_rock_disappears_from_guidance_and_hit_progress_is_reported(self):
        e = self.engine
        e.config['mine']['pickaxe_safe_hits'] = 100
        e.resources['pickaxe'] = 1
        e.travel_to('mine')
        rock = e.mine_rocks[0]['id']
        result = e.hit_mine_rock(rock)
        progress = result['sound_events'][0]['progress']
        self.assertGreater(progress, 0)
        for _ in range(e.config['mine']['hits_to_break']-1):
            e.hit_mine_rock(rock)
        self.assertNotIn(rock, {target['id'] for target in e.get_state()['audio_guidance']['targets']})
        self.assertEqual(e.recent_activity['kind'], 'mining')


if __name__ == '__main__':
    unittest.main()
