"""Fishing rules. Distances and rarity tables remain server-side."""
import math
import random


class FishingMixin:
    def fishing_config(self):
        return self.config['fishing']

    def reset_fishing(self):
        self.resources['fishing_rod'] = min(1, max(0, int(self.config.get('resources', {}).get('fishing_rod', 0))))
        self.resources['fish'] = dict(self.config.get('resources', {}).get('fish', {}))
        self.fishing_last_catch = None
        self.fishing_attempts = 0
        self.rod_casts = 0
        self.rod_catches = 0
        self.new_fishing_target()

    def lake_geometry(self):
        return {'x': (self.dotpad.width-1)/2, 'y': (self.dotpad.height-1)/2,
                'rx': (self.dotpad.width-5)/2, 'ry': (self.dotpad.height-5)/2}

    def inside_lake(self, x, y):
        g = self.lake_geometry()
        return ((x-g['x'])/g['rx'])**2 + ((y-g['y'])/g['ry'])**2 < 1

    def new_fishing_target(self):
        g = self.lake_geometry()
        angle, radius = random.uniform(0, math.tau), math.sqrt(random.random())*.7
        self.fishing_target = [g['x']+math.cos(angle)*g['rx']*radius,
                               g['y']+math.sin(angle)*g['ry']*radius]

    def get_fishing_objects(self):
        return [self.back_arrow('fishing_exit', 'Mine', 'travel:mine')]

    def draw_lake(self):
        g = self.lake_geometry()
        for i in range(720):
            angle = math.tau*i/720
            self.dotpad.set_dot(round(g['x']+g['rx']*math.cos(angle)),
                                round(g['y']+g['ry']*math.sin(angle)))

    def fishing_public_state(self):
        active = self.current_page == 'fishing' and not (self.paused or self.day_ended or self.sleep_until is not None)
        return {'active': active, 'lake': self.lake_geometry(),
                'target': list(self.fishing_target) if active else None,
                'attempts': self.fishing_attempts,
                'last_catch': dict(self.fishing_last_catch) if self.fishing_last_catch else None}

    def fishing_zone(self, x, y):
        d = math.hypot(x-self.fishing_target[0], y-self.fishing_target[1])
        cfg = self.fishing_config()
        middle_radius = math.sqrt(self.dotpad.width*self.dotpad.height*cfg.get('middle_area_fraction',1/6)/math.pi)
        return 'near' if d <= cfg['near_radius'] else 'middle' if d <= middle_radius else 'far'

    def cast_fishing(self, x, y):
        if self.current_page != 'fishing' or self.paused or self.sleep_until is not None:
            return self.response()
        if self.day_ended:
            return self.night_only_response()
        if not self.resources.get('fishing_rod'):
            return self.response(tts='Fishing rod required. Buy at the shop.')
        if not self.inside_lake(x, y):
            return self.response(tts='Cast inside the lake.')
        zone = self.fishing_zone(x, y)
        cfg = self.fishing_config()
        weights = self.boost_rare_weights(cfg['zone_weights'][zone], ('high',))
        grade = random.choices(list(weights), weights=list(weights.values()), k=1)[0]
        self.fishing_attempts += 1
        events = []
        if grade == 'miss':
            self.fishing_last_catch = {'id': None, 'label': 'No catch', 'attempt': self.fishing_attempts}
            text = 'No catch. Try another spot.'
        else:
            candidates = [key for key, fish in cfg['fish'].items() if fish['grade'] == grade]
            fish_id = random.choice(candidates)
            label = cfg['fish'][fish_id]['label']
            amount = self.loot_amount(1)
            self.resources['fish'][fish_id] = self.resources['fish'].get(fish_id, 0)+amount
            self.fishing_last_catch = {'id': fish_id, 'label': label, 'attempt': self.fishing_attempts}
            text = f'{label} {amount} caught.' + (' Bonus.' if amount>1 else '')
            events.append({'kind':'one_shot_group','sounds':['splash','shine'] if grade=='high' else ['splash']})
        self.rod_casts += 1
        if grade != 'miss':
            self.rod_catches += 1
            chance = min(1, max(0,self.rod_catches-cfg.get('rod_safe_catches',4))*cfg.get('rod_break_increment',.1))
            if chance>0 and random.random()<chance:
                self.resources['fishing_rod']=0
                self.rod_casts=0
                self.rod_catches=0
                text += ' Fishing rod broken. Buy another at the shop.'
                events.append(self.item_destroyed_event('fishing_rod'))
        self.new_fishing_target()
        result = self.consume_time('fish')
        self.render()
        if result['night']: return self.night_response(prefix=text, sound_events=events)
        return self.response(tts=text, sound_events=events)

    def buy_fishing_rod(self):
        if self.resources.get('fishing_rod', 0):
            return self.response(tts='Only one fishing rod allowed.')
        price = self.get_rod_price()
        if self.resources['coin'] < price:
            return self.response(tts=f'Not enough gold. Need {price} gold for Fishing rod.')
        self.resources['coin'] -= price
        self.resources['fishing_rod'] = 1
        self.rod_casts = 0
        self.rod_catches = 0
        self.clear_hover()
        self.render()
        return self.response(tts=f"Fishing rod bought. Gold left: {self.resources['coin']} gold", sound_events=[{'kind':'one_shot','sound':'coin'}])
