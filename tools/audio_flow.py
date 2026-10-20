"""Exercise the real game through pointer/key inputs, in temporary saved progress."""
import argparse
import copy
import json
from pathlib import Path
import random
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from game_engine import GameEngine


def fixture_config():
    config = json.loads((ROOT/'game_config.json').read_text(encoding="utf-8-sig"))
    config['resources']['coin'] = 500
    return config


class Flow:
    def __init__(self, engine):
        self.engine = engine
        self.now = 1000.0
        self.events = []
        self.milestones = []
        self.add({'kind':'state'}, engine.response())

    def add(self, action, response):
        result = copy.deepcopy(response)
        for key in ('dots','time_dots','spectator'):
            result['state'].pop(key,None)
        self.events.append({'at':round(self.now,3),'input':action,'response':result})
        return response

    def command(self, name):
        self.now += 0.12
        return self.add({'kind':'command','command':name},self.engine.handle_command(name))

    def pointer(self, kind, x, y):
        self.now += 0.08
        response = getattr(self.engine,'pointer_'+kind)(x,y)
        return self.add({'kind':kind,'x':x,'y':y},response)

    def click(self, action):
        obj = next((obj for obj in self.engine.get_objects() if obj.get('action') == action),None)
        assert obj is not None, (action,self.engine.current_page,[obj.get('action') for obj in self.engine.get_objects()])
        result = self.pointer('down',obj['x'],obj['y'])
        self.pointer('up',obj['x'],obj['y'])
        return result

    def go(self, place):
        self.command('minimap')
        self.click('travel:'+place)
        assert self.engine.current_page == place, (place,self.engine.current_page)

    def tick(self, seconds=0.3):
        self.now += seconds
        return self.add({'kind':'tick'},self.engine.visual_tick())

    def targets(self, kind):
        targets = list(self.engine.care_targets if kind=='care' else self.engine.harvest_targets)
        self.pointer('down',targets[0]['x'],targets[0]['y'])
        for target in targets[1:]:
            self.pointer('drag',target['x'],target['y'])
        self.pointer('up',targets[-1]['x'],targets[-1]['y'])
        self.tick()

    def mark(self, name):
        self.milestones.append({'name':name,'event':len(self.events)-1,
            'day':self.engine.day,'page':self.engine.current_page})


def run_flow():
    previous_rng = random.getstate()
    try:
        random.seed(20261014)
        with tempfile.TemporaryDirectory(prefix='visionpad-audio-flow-') as saved:
            flow = Flow(GameEngine(fixture_config(),save_dir=saved))
            engine = flow.engine
            with patch('game_engine.time.monotonic',side_effect=lambda:flow.now):
                flow.go('farm')
                plot = engine.get_unlocked_plot_defs()[0]['id']
                flow.click('open_plot_detail:'+plot)
                flow.click('open_seed_select:'+plot)
                flow.click('plant:'+plot+':tomato')
                flow.mark('plant')
                flow.click('start_care:water:'+plot)
                flow.targets('care')
                assert engine.farm_plots[plot]['watered']
                flow.mark('water')
                flow.click('start_care:fertilizer:'+plot)
                flow.targets('care')
                assert engine.farm_plots[plot]['fertilized']
                flow.mark('fertilize')
                for _ in range(2):
                    flow.go('home'); flow.click('rest')
                    flow.tick(engine.sleep_blackout_seconds+0.1)
                    flow.go('farm');flow.click('open_plot_detail:'+plot)
                    if not engine.farm_plots[plot]['mature']:
                        flow.click('start_care:water:'+plot);flow.targets('care')
                assert engine.farm_plots[plot]['mature']
                flow.click('start_harvest:'+plot);flow.targets('harvest')
                flow.mark('harvest')

                flow.go('home');flow.click('open_recipes')
                recipe='tomato_carrot_stew'
                flow.click('select_recipe:'+recipe)
                flow.click('toggle_ingredient:tomato');flow.click('toggle_ingredient:carrot')
                while engine.current_page=='cooking':
                    points=list(engine.get_cooking_gesture()['path'])
                    stage=engine.cooking_stage_index
                    flow.pointer('down',*points[0])
                    for point in points[1:]: flow.pointer('drag',*point)
                    flow.pointer('up',*points[-1]);flow.tick()
                    assert engine.current_page!='cooking' or engine.cooking_stage_index!=stage, 'Cooking path did not finish'
                assert engine.resources['foods'][recipe]==1
                flow.mark('cook')

                flow.go('town');flow.click('open_shop');flow.click('npc:shopkeeper:greeting')
                flow.click('npc:shopkeeper:farming');flow.click('npc:shopkeeper:trade')
                flow.click('shop_mode:sell')
                flow.click('sell:crop:tomato');flow.mark('sell')
                flow.command('left');flow.click('shop_mode:buy')
                for action in ('buy:pickaxe:pickaxe','buy:fishing_rod:fishing_rod'):
                    for _ in range(5):
                        if any(obj.get('action')==action for obj in engine.get_objects()): break
                        flow.command('right')
                    flow.click(action)
                assert engine.resources['pickaxe']==engine.resources['fishing_rod']==1
                flow.mark('buy')

                flow.go('mine')
                rock=engine.mine_rocks[0]['id']
                for _ in range(engine.config['mine']['hits_to_break']):
                    with patch('game_engine.random.choices',return_value=['diamond']):
                        flow.click('mine_hit:'+rock)
                assert engine.resources['diamond']>=1
                flow.tick(1.0)
                flow.mark('mine')
                flow.go('fishing')
                for grade in ('high','miss'):
                    with patch('game_fishing.random.choices',return_value=[grade]):
                        target=list(engine.fishing_target)
                        flow.pointer('down',*target);flow.pointer('up',*target)
                    flow.mark('fish_'+grade)
                flow.command('save');flow.mark('save')
                slot=engine.list_saves()[0]['id']
                flow.command('load');flow.click('load_slot:'+slot);flow.mark('load')
                assert engine.current_page=='fishing'
            return {'fixture':{'starting_gold':500,'temporary_saves':True,
                'accelerated_monotonic_clock':True,'controlled_rare_and_miss_outcomes':True},
                'milestones':flow.milestones,'events':flow.events}
    finally:
        random.setstate(previous_rng)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stdout',action='store_true')
    args=parser.parse_args()
    result=run_flow()
    if args.stdout:
        print(json.dumps(result))
    else:
        target=ROOT/'output/audio/integration-flow.json'
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(result,indent=2)+'\n')
        print(f"Recorded {len(result['events'])} real input responses and {len(result['milestones'])} milestones: {target.relative_to(ROOT)}")


if __name__=='__main__':
    main()
