"""Rowan's sequential tutorials and the village's weekly trading calendar."""


class VillageMixin:
    def reset_village(self):
        self.rowan_stage = 'new'
        self.rowan_greeted = False
        self.rowan_dialogue = ''
        self.rowan_submit_open = False

    def weekday_index(self):
        return (self.day - 1) % 7

    def calendar_days(self):
        return self.config['weekly_market']['days']

    def market_price(self, price, kind, mode):
        day = self.calendar_days()[self.weekday_index()]
        categories = day.get(mode, [])
        if 'all' in categories or kind in categories:
            percentage = self.config['weekly_market']['bonus_percent' if mode == 'sell' else 'discount_percent']
            price = int(price) * (100 + percentage if mode == 'sell' else 100 - percentage) // 100
        return self.sale_price(price) if mode == 'sell' else int(price)

    def calendar_text(self, index=None):
        index = self.weekday_index() if index is None else index
        day = self.calendar_days()[index]
        percent=self.config['weekly_market']['bonus_percent' if day.get('sell') else 'discount_percent']
        return f"{day['name']}. {day['description'].format(percent=percent)}"

    def open_calendar(self):
        offers = ['Monday: ore discount!', 'Tuesday: better food prices!',
                  'Wednesday: better fish prices!', 'Thursday: seed discount!',
                  'Friday: better ore prices!', 'Saturday: tool discount!',
                  'Sunday: better prices for everything!']
        return self.response(tts='Today is '+self.calendar_days()[self.weekday_index()]['name']+'. '+offers[self.weekday_index()])

    def get_calendar_objects(self):
        result = []
        for i, day in enumerate(self.calendar_days()):
            result.append(dict(id=f'calendar_{i}', type='calendar_day', x=8+14*(i%4), y=7+12*(i//4),
                width=12,height=9,hit_width=12,hit_height=9,label=day['name'],
                selected=i==self.weekday_index(), tts=self.calendar_text(i), action=f'calendar_day:{i}'))
        result.append(self.back_arrow('calendar_back','Back to shop','return_shop_choice'))
        return result

    def rowan_object(self):
        return dict(id='town_rowan',type='rowan',x=24,y=7,width=12,height=10,hit_width=14,hit_height=12,
                    label='Rowan',tts='Rowan. Quest available.' if self.rowan_stage!='done' else 'Rowan.',
                    quest_available=self.rowan_stage!='done',action='talk_rowan')

    def show_rowan(self, text, page='rowan_dialogue', events=None):
        self.rowan_dialogue=text
        self.current_page='rowan_submit' if page=='rowan_submit' else 'town'
        self.rowan_submit_open = page=='rowan_submit'
        self.clear_hover(); self.render()
        return self.response(tts=f'Rowan. {text}',sound_events=events)

    def talk_rowan(self):
        if self.current_location != 'town': return self.response(tts='Rowan is in the village.')
        cfg=self.config['rowan']
        if self.rowan_stage=='new':
            self.resources['foods']['rowan_soup']=self.resources['foods'].get('rowan_soup',0)+1
            self.rowan_stage='soup_given'
            return self.show_rowan("Welcome! I'm Rowan. Here's my soup. Press the second button, F2, to open your inventory. Select Rowan's soup to eat it. Press F2 again to return to the village, then talk to me.")
        if self.rowan_stage=='soup_given':
            if self.resources['foods'].get('rowan_soup',0)>0:
                return self.show_rowan("Try my soup. Press the second button, F2, and select Rowan's soup. Press F2 again to return here.")
            for seed in self.config['seeds']:
                self.resources['seeds'][seed]=self.resources['seeds'].get(seed,0)+cfg['seed_gift_each']
            self.rowan_stage='seeds_given'
            return self.show_rowan("Glad you enjoyed the soup! Here are tomato, carrot, and potato seeds. Talk to me again when you're ready.")
        if self.rowan_stage=='seeds_given':
            self.rowan_stage='vegetable_requested'
            return self.show_rowan("I'm short of vegetables. Could you bring me one? Go to the farm, select a plot, and plant a seed. Water it, then sleep at home. Water it each day as it grows. When it's ready, harvest it and bring me any one vegetable.")
        if self.rowan_stage=='vegetable_requested':
            text = 'Choose one vegetable to give me. You can leave and come back anytime.' if any(self.resources['crops'].values()) else 'You have no vegetables yet. Plant a seed, water it each day, and sleep until it grows. Come back after harvesting.'
            return self.show_rowan(text, 'rowan_submit')
        return self.show_rowan('Thanks for your help. Good luck on the farm!')

    def get_rowan_objects(self):
        result=[]
        if self.current_page!='rowan_submit': return result
        for key in self.config['seeds']:
            count=self.resources['crops'].get(key,0)
            if count:
                result.append(dict(id='rowan_crop_'+key,type='ingredient',ingredient_id=key,seed_id=key,
                    item_kind='crop',x=8+16*len(result),y=22,width=12,height=9,hit_width=12,hit_height=9,
                    label=self.get_seed_label(key),count=count,required_count=1,selected=False,
                    tts=f"{self.get_seed_label(key)}. Stock {count}. Give one to Rowan.",action='rowan_submit:'+key))
        result.append(self.back_arrow('rowan_back','Back to village','return_scene'))
        return result

    def submit_rowan_crop(self, seed):
        if self.current_page!='rowan_submit' or not self.rowan_submit_open or self.rowan_stage!='vegetable_requested':return self.response()
        if seed not in self.config['seeds'] or self.resources['crops'].get(seed,0)<1:
            return self.response(tts='No vegetable to give.')
        self.resources['crops'][seed]-=1
        self.resources['coin']+=self.config['rowan']['vegetable_reward_gold']
        self.rowan_stage='done'
        return self.show_rowan(f"Thank you! This is just what I needed. Here's {self.config['rowan']['vegetable_reward_gold']} gold.",events=[{'kind':'one_shot','sound':'coin'}])

    def draw_rowan(self, obj):
        self.draw_item_frame(obj, 'food' if obj.get('quest_available') else 'material')
        self.draw_icon_pattern(obj['x'],obj['y'],['00100','01110','00100','11111','00100','01010','01010'])

    def draw_calendar(self, obj):
        self.dotpad.draw_box(obj['x'],obj['y'],obj.get('width',12),obj.get('height',9))
        self.draw_icon_pattern(obj['x'],obj['y'],['11111','00000','10101','00000','10101'])
        if obj.get('selected'):self.dotpad.set_dot(obj['x'],obj['y'])
