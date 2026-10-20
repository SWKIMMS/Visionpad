"""Sound changes coexist with the team's Rowan quests and evaluation controls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from game_engine import GameEngine

ROOT = Path(__file__).resolve().parent


class TeamIntegrationTests(unittest.TestCase):
    def setUp(self):
        saved = tempfile.TemporaryDirectory()
        self.addCleanup(saved.cleanup)
        self.engine = GameEngine(json.loads((ROOT / 'game_config.json').read_text()), save_dir=saved.name)
        self.engine.travel_to('town')

    def test_village_has_one_rowan_and_quest_replay_does_not_repeat_gifts(self):
        e = self.engine
        rowans = [obj for obj in e.get_objects() if obj.get('action') == 'talk_rowan']
        self.assertEqual(len(rowans), 1)
        self.assertFalse(any(obj.get('action') == 'npc:shopkeeper:greeting' for obj in e.get_objects()))
        obj = rowans[0]
        result = e.pointer_down(obj['x'], obj['y'])
        e.pointer_up(obj['x'], obj['y'])
        self.assertEqual(result['speech_profile'], 'shopkeeper')
        self.assertEqual(result['speech_channel'], 'quest')
        self.assertEqual(result['state']['dialogue']['speaker'], 'Rowan')
        self.assertEqual(result['state']['dialogue']['name'], 'Rowan')
        self.assertEqual(e.resources['foods']['rowan_soup'], 1)
        before = copy.deepcopy(e.resources)
        replay = e.perform_action('repeat_rowan', {})
        self.assertEqual(replay['speech_profile'], 'shopkeeper')
        self.assertEqual(replay['speech_channel'], 'quest')
        e.talk_rowan()
        self.assertEqual(e.resources, before)

    def test_tutorial_gifts_and_crop_reward_are_still_granted_once(self):
        e = self.engine
        e.talk_rowan()
        e.open_inventory()
        e.use_food('rowan_soup')
        e.travel_to('town')
        before = dict(e.resources['seeds'])
        e.talk_rowan()
        for seed in e.config['seeds']:
            self.assertEqual(e.resources['seeds'][seed], before[seed] + e.config['rowan']['seed_gift_each'])
        e.talk_rowan()
        e.resources['crops']['tomato'] = 1
        e.record_activity('harvest', 'Tomato')
        result = e.talk_rowan()
        self.assertIn('first harvest', result['tts'])
        self.assertEqual(result['state']['page'], 'rowan_submit')
        before = e.resources['coin']
        result = e.submit_rowan_crop('tomato')
        self.assertEqual(result['speech_profile'], 'shopkeeper')
        self.assertEqual(e.resources['coin'], before + e.config['rowan']['vegetable_reward_gold'])
        self.assertEqual(e.resources['crops']['tomato'], 0)
        e.submit_rowan_crop('tomato')
        e.talk_rowan()
        self.assertEqual(e.resources['coin'], before + e.config['rowan']['vegetable_reward_gold'])
        self.assertNotIn('first harvest', e.rowan_dialogue)

    def test_shop_advice_is_selectable_without_advancing_the_quest(self):
        e = self.engine
        e.open_shop()
        advice = next(obj for obj in e.get_objects() if obj.get('action') == 'npc:shopkeeper:greeting')
        before = copy.deepcopy(e.resources), e.rowan_stage, e.time_used_cells
        result = e.pointer_down(advice['x'], advice['y'])
        self.assertEqual(result['state']['page'], 'npc_dialogue')
        self.assertEqual((e.resources, e.rowan_stage, e.time_used_cells), before)

    def test_pre_audio_quest_save_keeps_its_stage_and_does_not_repeat_soup(self):
        e = self.engine
        e.talk_rowan()
        saved = e.snapshot()
        for key in ('npc_visits', 'dialogue', 'activity_counts', 'activity_serial',
                    'recent_activity', 'npc_reactions', 'activity_history_complete'):
            saved.pop(key)
        e.reset()
        e.restore_snapshot(saved)
        self.assertEqual(e.rowan_stage, 'soup_given')
        e.talk_rowan()
        self.assertEqual(e.resources['foods']['rowan_soup'], 1)
        self.assertFalse(e.activity_history_complete)

    def test_motion_without_press_still_collects_targets_and_updates_guidance(self):
        e = self.engine
        e.travel_to('farm')
        plot = e.get_unlocked_plot_defs()[0]['id']
        e.farm_plots[plot].update(seed_id='tomato', mature=False, watered=False)
        e.start_care_minigame(plot, 'water')
        before = e.get_state()['audio_guidance']
        target = before['targets'][0]
        result = e.pointer_move(target['x'], target['y'])
        self.assertFalse(e.pointer_pressed)
        self.assertGreater(result['state']['audio_guidance']['completed'], before['completed'])
        self.assertNotIn(target['id'], {obj['id'] for obj in result['state']['audio_guidance']['targets']})

    def test_evaluation_click_command_keeps_selecting_instead_of_pausing(self):
        e = self.engine
        obj = next(obj for obj in e.get_objects() if obj.get('action') == 'open_shop')
        e.pointer_move(obj['x'], obj['y'])
        result = e.handle_command('click')
        self.assertEqual(result['state']['page'], 'shop_choice')
        self.assertFalse(e.paused)


if __name__ == '__main__':
    unittest.main()
