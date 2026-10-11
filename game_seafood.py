"""Fish ingredient selection and food effects shared by harvesting and trading."""
import math
import random

class SeafoodMixin:
    def get_rod_price(self):
        return int(self.fishing_config().get('rod_price',100))

    def get_fish_price(self, fish_id):
        fish=self.fishing_config()['fish'][fish_id]
        cfg=self.fishing_config()
        return self.get_mineral_price(cfg.get('fish_price_base_mineral','copper'))+int(cfg.get('fish_price_grade_bonus',{}).get(fish['grade'],0))

    def selected_fish(self):
        return next((k[5:] for k in self.selected_ingredients if k.startswith('fish:')),None)

    def fish_allowed(self, recipe, fish_id):
        fish = self.fishing_config()['fish'].get(fish_id)
        return bool(fish and fish_id in recipe.get('allowed_fish', [])
                    and fish['grade'] in recipe.get('quality_effects', {})
                    and (not recipe.get('fish_grade') or recipe['fish_grade']==fish['grade']))

    def seafood_ready(self, recipe, selected=False):
        if any(self.resources['crops'].get(k,0)<n for k,n in recipe.get('ingredients',{}).items()):return False
        candidates=[self.selected_fish()] if selected else self.fishing_config()['fish']
        return any(self.fish_allowed(recipe,k) and self.resources['fish'].get(k,0)>=recipe.get('fish_required',1) for k in candidates)

    def seafood_ingredient_objects(self, objects):
        recipe=self.get_recipe_config(self.selected_recipe_id)
        if not recipe.get('seafood'):return objects
        for key,fish in self.fishing_config()['fish'].items():
            count=self.resources['fish'].get(key,0)
            if not self.fish_allowed(recipe,key) or count < recipe.get('fish_required',1):continue
            selected=self.selected_fish()==key
            objects.insert(len(objects)-1,{'id':'ingredient_'+key,'type':'ingredient','ingredient_id':key,'item_kind':'fish',
                'x':8,'y':6,'width':12,'height':9,'hit_width':12,'hit_height':9,'label':fish['label'],
                'count':count,'required_count':recipe.get('fish_required',1),'selected':selected,
                'tts':f"{fish['label']}. Stock {count}. {'Selected.' if selected else 'Choose one fish.'}",
                'action':'toggle_ingredient:fish:'+key})
        return objects

    def toggle_fish(self, key):
        fish_id=key[5:];recipe=self.get_recipe_config(self.selected_recipe_id)
        if not recipe.get('seafood') or not self.fish_allowed(recipe,fish_id) or self.resources['fish'].get(fish_id,0)<recipe.get('fish_required',1):
            return self.response(tts='Fish unavailable.')
        was_selected=key in self.selected_ingredients
        self.selected_ingredients={k for k in self.selected_ingredients if not k.startswith('fish:')}
        if not was_selected:self.selected_ingredients.add(key)
        if set(recipe['ingredients']).issubset(self.selected_ingredients) and self.selected_fish():
            self.pointer_pressed=False
            return self.open_cooking_minigame()
        self.clear_hover();self.render()
        return self.response(tts='Fish deselected.' if was_selected else 'Fish selected.')

    def finish_seafood(self, recipe):
        if not self.seafood_ready(recipe,selected=True):
            self.clear_cooking();self.current_page=self.current_location='home';self.render()
            return self.response(tts='Not enough ingredients.')
        fish=self.selected_fish();grade=self.fishing_config()['fish'][fish]['grade']
        rid=self.selected_recipe_id+'_'+grade
        for key,count in recipe['ingredients'].items():self.resources['crops'][key]-=count
        self.resources['fish'][fish]-=recipe.get('fish_required',1)
        amount=self.loot_amount(1)
        self.resources['foods'][rid]=self.resources['foods'].get(rid,0)+amount
        text=f"{recipe['label']} {amount} made."+(' Bonus.' if amount>1 else '')
        self.clear_cooking();self.clear_hover();self.current_page=self.current_location='home'
        result=self.consume_time('cook');self.render()
        return self.night_response(text) if result['night'] else self.response(tts=text,sfx='cooking_success')

    def boost_rare_weights(self, weights, rare_keys):
        result=dict(weights)
        if self.active_buff.get('kind')=='rare_find' and self.active_buff.get('remaining_ticks',0)>0:
            multiplier=self.active_buff.get('rare_weight_multiplier',1)
            for key in rare_keys:result[key]=result.get(key,0)*multiplier
        return result

    def loot_amount(self, amount):
        if self.active_buff.get('kind')=='double_loot' and self.active_buff.get('remaining_ticks',0)>0:
            if random.random()<self.active_buff.get('double_chance',0):return amount*2
        return amount

    def sale_price(self, price):
        if self.active_buff.get('kind')=='sale_boost' and self.active_buff.get('remaining_sales',0)>0:
            return math.floor(price*self.active_buff.get('multiplier',1))
        return price

    def consume_sale(self):
        if self.active_buff.get('kind')=='sale_boost' and self.active_buff.get('remaining_sales',0)>0:
            self.active_buff['remaining_sales']-=1
            if not self.active_buff['remaining_sales']:
                self.active_buff={'kind':None,'source':None,'multiplier':1,'remaining_ticks':0}
