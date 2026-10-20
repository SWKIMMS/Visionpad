"""End-to-end game input sequence, without altering the player's running game."""
import unittest
from tools.audio_flow import run_flow


class AudioFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flow=run_flow()

    def test_all_gameplay_milestones_are_reached_by_pointer_and_key_input(self):
        self.assertEqual([item['name'] for item in self.flow['milestones']],
            ['plant','water','fertilize','harvest','cook','sell','buy','mine','fish_high','fish_miss','save','load'])
        self.assertGreater(len(self.flow['events']),150)
        errors=[item['response']['tts'] for item in self.flow['events'] if item['response'].get('sfx')=='error']
        self.assertEqual(errors,[])

    def test_required_action_and_result_sounds_are_present(self):
        events=self.flow['events']
        sfx={item['response']['sfx'] for item in events}
        for expected in ['plant','water','fertilize','harvest','cooking_success','fishing_miss','saved','loaded']:
            self.assertIn(expected,sfx)
        sounds=[event.get('sound') for item in events for event in item['response']['sound_events']]
        for expected in ['sleep','step','door','coin','pickaxe','shine']:
            self.assertIn(expected,sounds)

    def test_save_and_load_preserve_the_completed_session(self):
        milestones={item['name']:item for item in self.flow['milestones']}
        before=self.flow['events'][milestones['save']['event']]['response']['state']
        after=self.flow['events'][milestones['load']['event']]['response']['state']
        for key in ['resources','time','day','page','dialogue']:
            self.assertEqual(before[key],after[key])
        self.assertEqual(after['resources']['foods']['tomato_carrot_stew'],1)
        self.assertTrue(self.flow['fixture']['temporary_saves'])


if __name__=='__main__':
    unittest.main()
