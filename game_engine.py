import copy
import math
import random
import time
from turtle import width

from dotpad import DotPad
from pathlib import Path
from game_saves import SaveMixin
from game_ui import KeypadUI
from game_fishing import FishingMixin
from game_seafood import SeafoodMixin
from game_village import VillageMixin
from spectator_state import spectator_snapshot


class GameEngine(VillageMixin, SeafoodMixin, FishingMixin, KeypadUI, SaveMixin):

    def __init__(self, config, save_dir=None):
        config = self.prepare_display_config(config)
        self.config = config
        self.sleep_blackout_seconds = max(0, float(config.get("interaction", {}).get("sleep", {}).get("blackout_ms", 2000))) / 1000
        interaction = config.get("interaction", {})
        feedback = interaction.get("feedback", {})
        cooking = interaction.get("cooking", {})
        inventory = interaction.get("inventory", {})
        self.disappear_delay_seconds = max(0, float(feedback.get("disappear_delay_ms", 1000))) / 1000
        self.resume_marker_delay_seconds = max(0, float(cooking.get("resume_marker_delay_ms", 2000))) / 1000
        self.stir_scale = max(0.1, float(cooking.get("stir_scale", 1.6)))
        # The physical layout has twelve slots and reserves its bottom row for arrows.
        self.inventory_items_per_page = max(1, min(12, int(inventory.get("items_per_page", 12))))
        self.inventory_hide_zero_items = bool(inventory.get("hide_zero_items", True))
        self.client_settings = {
            "visual_refresh_interval_ms": max(50, int(feedback.get("visual_refresh_interval_ms", 100))),
            "audio": interaction.get("audio", {})
        }

        dot_config = config["dotpad"]
        self.dotpad = DotPad(
            width=dot_config["width"],
            height=dot_config["height"]
        )

        time_bar = config.get("time", {}).get("bar", {})
        self.timepad = DotPad(
            width=int(time_bar.get("panel_width", 40)),
            height=int(time_bar.get("panel_height", 4))
        )

        self.save_dir = Path(save_dir) if save_dir is not None else Path(__file__).resolve().parent / "saves"
        self._static_fields = set(vars(self))
        self.reset()

    @staticmethod
    def prepare_display_config(config):
        # Keep saved rules intact; normalize presentation in a private copy.
        config = copy.deepcopy(config)
        # One editable definition per dish; inventory variants preserve effect strength.
        for recipe_id, recipe in list(config.get('recipes', {}).items()):
            if recipe.get('seafood') and not recipe.get('hidden_recipe'):
                for grade, effect in recipe.get('quality_effects', {}).items():
                    variant = copy.deepcopy(recipe)
                    variant.update(effect)
                    variant.update(hidden_recipe=True, fish_grade=grade, base_recipe=recipe_id)
                    adjective = {'low': 'Simple', 'medium': 'Ordinary', 'high': 'Luxurious'}[grade]
                    variant['label'] = f"{adjective} {recipe['label']}"
                    config['recipes'][recipe_id+'_'+grade] = variant
        names = {"home": "Home", "farm": "Farm", "town": "Village", "mine": "Mine", "fishing": "Fishing lake",
                 "minimap": "Map", "inventory": "Inventory", "research": "Research",
                 "plot_detail": "Plot", "seed_select": "Seeds", "water_minigame": "Watering",
                 "fertilizer_minigame": "Fertilizing", "harvest": "Harvest",
                 "recipe_select": "Recipes", "ingredient_select": "Ingredients", "cooking": "Cooking",
                 "shop_choice": "Shop", "shop_buy": "Buy", "shop_sell": "Sell"}
        for key, label in names.items():
            page = config.setdefault("pages", {}).get(key)
            if isinstance(page, dict):
                page["label"] = label
            elif isinstance(page, str):
                config["pages"][key] = label
        for key, seed in config.get("seeds", {}).items():
            seed["label"] = {"tomato": "Tomato", "carrot": "Carrot", "potato": "Potato"}.get(key, key.replace("_", " ").title())
        for key, recipe in config.get("recipes", {}).items():
            if recipe.get("seafood"): continue
            recipe["label"] = {"tomato_carrot_stew": "Tomato carrot stew", "potato_tomato_soup": "Potato tomato soup",
                               "vegetable_fritters": "Vegetable fritters", "rowan_soup": "Rowan's soup"}.get(key, key.replace("_", " ").title())
            recipe["buff_label"] = {"harvest_multiplier": "Harvest boost", "pickaxe_protection": "Pickaxe protection",
                                    "time_slow": "Time saving"}.get(recipe.get("buff_kind"), "Food effect")
            for stage in recipe.get("gesture_steps", []):
                stage["label"] = ("Trace eight petals" if key == "vegetable_fritters" else "Stir") if stage.get("kind") == "stir" else "Chop"
        for i, plot in enumerate(config.get("farm", {}).get("plots", [])):
            plot["label"] = f"Plot {i + 1}"
        for scene in ("home", "farm", "town"):
            for obj in config.get(scene, {}).get("objects", []):
                action = obj.get("action", "")
                obj["label"] = names.get(action.split(":")[-1], {"bed": "Bed", "chest": "Research", "stove": "Kitchen", "shop_npc": "Shop"}.get(obj.get("type"), obj.get("id", "Object")))
                obj["tts"] = obj["label"]
        return config

    def compact_objects(self, objects):
        """Pack menu objects in reading order, using the same geometry for touch and output."""
        page = self.current_page
        if page in ("load_game", "shop_calendar"):
            return objects
        if page == "inventory":
            objects = [dict(o) for o in objects]
            items = [o for o in objects if o.get("type") == "resource"]
            for i,o in enumerate(items):
                o.update(x=8+14*(i%4), y=5+10*(i//4), width=12, height=8, hit_width=12, hit_height=8)
            for o in objects:
                if o.get("type") == "arrow": o.update(y=34)
            return objects
        if page in ("home", "town"):
            objects = [dict(o) for o in objects]
            facilities = [o for o in objects if o.get("type") in ("bed", "chest", "stove", "shop_npc", "rowan")]
            order = {"bed": 0, "chest": 1, "stove": 2, "shop_npc": 3, "rowan": 4}
            facilities.sort(key=lambda o: order[o["type"]])
            for index, o in enumerate(facilities):
                o.update(x=8 + index*16, y=7, width=12, height=10, hit_width=12, hit_height=10)
            return objects
        if page in ("shop_buy", "shop_sell"):
            objects = [dict(o) for o in objects]
            for o in objects:
                if o.get("type") == "shop_item":
                    o.update(width=12, height=8, hit_width=12, hit_height=8)
            for o in objects:
                if o.get("id") == f"shop_{'buy' if page == 'shop_buy' else 'sell'}_back":
                    o.update(x=55, y=35, size=3, hit_width=7, hit_height=7)
                elif o.get("action", "").startswith("shop_page:"):
                    o.update(x=6 if o["action"].endswith(":-1") else 16, y=35, hit_width=7, hit_height=7)
            return objects
        if page in ("minimap", "cooking", "mine", "fishing", "water_minigame", "fertilizer_minigame", "harvest", "inventory", "shop_buy", "shop_sell"):
            return objects
        objects = [dict(o) for o in objects]
        arrows = [o for o in objects if o.get("type") == "arrow"]
        items = [o for o in objects if o.get("type") != "arrow"]
        if page == "plot_detail":
            buttons = [o for o in items if o["type"] == "care_button"]
            for i, o in enumerate(buttons):
                o.update(x=6 + i * 12, y=6, width=9, height=9, hit_width=9, hit_height=9)
            for o in items:
                if o["type"] == "growth_gauge":
                    o.update(x=30, y=15, hit_width=42, hit_height=5)
                elif o["type"] == "plot_detail_field":
                    o.update(x=30, y=29, hit_width=44, hit_height=18)
            for i, o in enumerate(arrows):
                o.update(x=6 + len(buttons)*12 + i*9, y=6, hit_width=7, hit_height=7)
            return buttons + arrows + [o for o in items if o not in buttons]
        if page == "research":
            for i, o in enumerate(items):
                o.update(x=8+15*(i%3), y=6+12*(i//3), width=12, height=8,
                         hit_width=12, hit_height=8)
            return items + arrows
        if page == "recipe_select":
            for o in items:
                if o.get("type") == "recipe": o.update(width=12, height=8, hit_width=12, hit_height=8)
        if page == "ingredient_select":
            items.sort(key=lambda o: o["type"] != "cooking_start")
        # Restore original frame dimensions. Wrap complete items instead of
        # shrinking every box to force a single row. Reserve two blank edge dots.
        gap, margin = 3, 2
        right = self.dotpad.width-margin
        if page == "shop_choice":
            for o in items: o.update(width=12,height=12)
        x, top, row_height, bottom = margin, margin, 0, margin
        for o in items:
            w = min(o.get("width",10), right-margin)
            h = o.get("height",8)
            if x+w > right:
                x, top, row_height = margin, top+row_height+gap, 0
            o.update(x=x+w//2, y=top+h//2, width=w, hit_width=w, hit_height=h)
            occupied_height=h+(3 if o.get("type") == "plot" else 0)
            row_height=max(row_height,occupied_height)
            bottom=max(bottom,top+occupied_height)
            x += w+gap
        for i, o in enumerate(arrows):
            # Nine-dot tall triangles also keep the outermost rows blank.
            o.update(x=5+i*10, y=min(self.dotpad.height-6, bottom+5), hit_width=7, hit_height=9)
        if page == "shop_choice":
            back = self.back_arrow("shop_choice_back", "Back to village", "return_scene")
            back.update(x=5, y=bottom+5, size=3, hit_width=5, hit_height=9)
            arrows.append(back)
        return items+arrows

    def reset(self):
        self.reset_village()
        self._menu_stack = []
        self._load_return = None
        self._save_slots = []
        self.sleep_until = None
        self.pending_visual_completion = None
        self.shop_page = 0
        self._pickaxe_hits = 0
        self.inventory_page = 0
        self.inventory_page_count = 1
        self.day = int(self.config.get("game", {}).get("start_day", 1))
        self.current_location = "home"
        self.current_page = "home"
        self.paused = False
        self.day_ended = False

        resource_config = self.config.get("resources", {})
        self.resources = {
            "coin": int(resource_config.get("coin", 0)),
            "wood": int(resource_config.get("wood", 0)),
            "stone": int(resource_config.get("stone", 0)),
            "fertilizer": int(resource_config.get("fertilizer", 0)),
            "seeds": dict(resource_config.get("seeds", {})),
            "crops": dict(resource_config.get("crops", {})),
            "foods": dict(resource_config.get("foods", {}))
        }

        for mineral in ("copper", "iron", "diamond"):
            self.resources[mineral] = int(resource_config.get(mineral, 0))
        self.resources["pickaxe"] = min(1, max(0, int(resource_config.get("pickaxe", 0))))

        for seed_id in self.config.get("seeds", {}):
            self.resources["seeds"].setdefault(seed_id, 0)
            self.resources["crops"].setdefault(seed_id, 0)

        for recipe_id in self.config.get("recipes", {}):
            self.resources["foods"].setdefault(recipe_id, 0)

        research = self.config.get("research", {})
        expansion = research.get("field_expansion", {})
        self.research_levels = {"seed_return": 0, "mineral_luck": 0}
        self.unlocked_plot_count = int(expansion.get("initial_plot_count", 2))

        self.farm_plots = {}
        for plot in self.config.get("farm", {}).get("plots", []):
            self.farm_plots[plot["id"]] = self.new_plot_state()

        self.seed_select_plot_id = None
        self.drag_tool = None
        self.drag_target_ids = set()

        self.detail_plot_id = None

        self.care_mode = None
        self.care_targets = []
        self.care_dragging = False
        self.care_collected_ids = set()
        self.care_visible_until = {}

        self.harvest_plot_id = None
        self.harvest_targets = []
        self.harvest_dragging = False
        self.harvest_collected_ids = set()

        self.selected_recipe_id = None
        self.selected_ingredients = set()
        self.cooking_dragging = False
        self.cooking_path_samples = []
        self.cooking_visible_until = {}
        self.cooking_progress_index = 0
        self.cooking_stage_index = 0
        self.cooking_last_progress_at = None
        self.cooking_resume_marker = False

        self.active_buff = {
            "kind": None,
            "source": None,
            "multiplier": 1.0,
            "remaining_ticks": 0
        }

        self.hover_object_id = None
        self.last_pointer = (None, None)
        self.pointer_pressed = False

        time_config = self.config.get("time", {})
        self.time_total_cells = int(time_config.get("total_cells", 20))
        self.time_used_cells = 0
        self.regenerate_mine()
        self.reset_fishing()

        self.render()

    def new_plot_state(self):
        return {
            "seed_id": None,
            "watered": False,
            "fertilized": False,
            "growth": 0,
            "mature": False
        }

    def clear_hover(self):
        self.hover_object_id = None

    def clear_care(self, keep_detail=False):
        if self.pending_visual_completion and self.pending_visual_completion[1] == "care":
            self.pending_visual_completion = None
        self.care_mode = None
        self.care_targets = []
        self.care_dragging = False
        self.care_collected_ids.clear()
        self.care_visible_until = {}
        if not keep_detail:
            self.detail_plot_id = None

    def clear_harvest(self):
        self.harvest_plot_id = None
        self.harvest_targets = []
        self.harvest_dragging = False
        self.harvest_collected_ids.clear()

    def clear_cooking(self, keep_recipe=False):
        if self.pending_visual_completion and self.pending_visual_completion[1] == "cooking":
            self.pending_visual_completion = None
        if not keep_recipe:
            self.selected_recipe_id = None
            self.selected_ingredients.clear()
        self.cooking_dragging = False
        self.cooking_path_samples = []
        self.cooking_visible_until = {}
        self.cooking_progress_index = 0
        self.cooking_stage_index = 0
        self.cooking_last_progress_at = None
        self.cooking_resume_marker = False


    def has_final_consonant(self, text):
        if not text:
            return False
        code = ord(str(text)[-1])
        if 0xAC00 <= code <= 0xD7A3:
            return (code - 0xAC00) % 28 != 0
        return False

    def josa(self, text, consonant_form, vowel_form):
        return consonant_form if self.has_final_consonant(text) else vowel_form

    def ro_particle(self, text):
        if not text:
            return " "
        code = ord(str(text)[-1])
        if 0xAC00 <= code <= 0xD7A3:
            jong = (code - 0xAC00) % 28
            return " " if jong in (0, 8) else " "
        return " "

    def get_page_name(self, page_id):
        if page_id == "load_game": return "Load game"
        return self.config.get("pages", {}).get(page_id, page_id)

    def get_seed_config(self, seed_id):
        return self.config.get("seeds", {}).get(seed_id, {})

    def get_seed_label(self, seed_id):
        return self.get_seed_config(seed_id).get("label", seed_id)

    def get_recipe_config(self, recipe_id):
        return self.config.get("recipes", {}).get(recipe_id, {})

    def get_recipe_label(self, recipe_id):
        return self.get_recipe_config(recipe_id).get("label", recipe_id)

    def get_plot_label(self, plot_id):
        for plot in self.config.get("farm", {}).get("plots", []):
            if plot["id"] == plot_id:
                return plot.get("label", plot_id)
        return plot_id

    def get_action_cost(self, action_name):
        # Movement never consumes time, even with an older configuration.
        if action_name == "travel":
            return 0
        defaults = {"plant": 2, "water": 2, "fertilize": 2, "harvest": 3,
                    "research": 3, "cook": 3, "mine": 2}
        configured = self.config.get("time", {}).get("action_costs", {})
        return max(defaults.get(action_name, 0), int(configured.get(action_name, 0)))

    def get_time_cells(self):
        return max(0, min(self.time_total_cells, self.time_used_cells))

    def time_text(self):
        used = self.get_time_cells()
        remaining = max(0, self.time_total_cells - used)
        if self.day_ended:
            return "Night. Select the bed."
        return f"Activity: {remaining} hours left"

    def recipe_effect_text(self, recipe):
        if recipe.get('buff_kind') == 'sale_boost':
            return f"{recipe.get('buff_label', 'Better sales')}, {recipe.get('sale_uses', 3)} sales"
        return f"{recipe.get('buff_label', 'Food effect')}, {float(recipe.get('buff_ticks', 0)):g} hours"

    def buff_multiplier_for(self, kind):
        if self.active_buff.get("kind") == kind and float(self.active_buff.get("remaining_ticks", 0)) > 0:
            return float(self.active_buff.get("multiplier", 1.0))
        return 1.0

    def buff_text(self):
        if self.active_buff.get('kind')=='sale_boost' and self.active_buff.get('remaining_sales',0)>0:
            return f"Better sales, {self.active_buff['remaining_sales']} sales left"
        remaining = float(self.active_buff.get("remaining_ticks", 0))
        if remaining <= 0:
            return "No food effect"
        recipe = self.get_recipe_config(self.active_buff.get("source")) or {}
        return f"{recipe.get('buff_label', 'Food effect')}, {remaining:g} hours left"

    def tick_buff(self, cost):
        if self.active_buff.get("kind") == "sale_boost": return
        remaining = float(self.active_buff.get("remaining_ticks", 0))
        remaining = max(0, remaining - max(0, float(cost)))
        self.active_buff["remaining_ticks"] = remaining
        if remaining == 0:
            self.active_buff = {"kind": None, "source": None, "multiplier": 1.0, "remaining_ticks": 0}

    def consume_time(self, action_name):
        cost = max(0, self.get_action_cost(action_name))
        if self.day_ended:
            return {"cost": 0, "night": True}

        # Buff duration follows elapsed game hours. Split an action at expiry.
        multiplier = self.buff_multiplier_for("time_slow")
        if 0 < multiplier < 1:
            remaining = float(self.active_buff["remaining_ticks"])
            covered = min(cost, remaining / multiplier)
            cost = covered * multiplier + (cost - covered)
        self.time_used_cells = min(self.time_total_cells, self.time_used_cells + cost)
        self.tick_buff(cost)

        if self.time_used_cells >= self.time_total_cells:
            self.enter_night()
            return {"cost": cost, "night": True}

        return {"cost": cost, "night": False}

    def enter_night(self):
        self.day_ended = True
        self.current_location = "home"
        self.current_page = "home"
        self.seed_select_plot_id = None
        self.drag_tool = None
        self.drag_target_ids.clear()
        self.clear_care()
        self.clear_harvest()
        self.clear_cooking()
        self.pointer_pressed = False
        self.clear_hover()
        self.render()

    def night_response(self, prefix=None, sound_events=None):
        narration = "Night. Home now. Select the bed."
        if prefix:
            narration = f"{prefix}. {narration}"
        return self.response(tts=narration, sfx="day_end", sound_events=sound_events)

    def next_day(self):
        if self.sleep_until is not None:
            return self.response()
        self.sleep_until = time.monotonic() + self.sleep_blackout_seconds
        self.pointer_pressed = False
        self.clear_care()
        self.clear_harvest()
        self.clear_cooking()
        self.clear_hover()
        self.render()
        return self.response(tts="Sleeping.", sound_events=[{"kind": "one_shot", "sound": "sleep"}])

    def finish_sleep(self):
        self.sleep_until = None
        matured = []
        for state in self.farm_plots.values():
            if state["seed_id"] is not None and not state["mature"] and state["watered"]:
                gain = 1
                seed_config = self.get_seed_config(state["seed_id"])
                needed = int(seed_config.get("growth_days", 3))
                state["growth"] = min(needed, state["growth"] + gain)
                if state["growth"] >= needed:
                    state["mature"] = True
                    matured.append(self.get_seed_label(state["seed_id"]))

            state["watered"] = False
            state["fertilized"] = False

        self.day += 1
        self.new_fishing_target()
        self.fishing_last_catch = None
        self.regenerate_mine()
        self.time_used_cells = 0
        self.day_ended = False
        self.current_location = "home"
        self.current_page = "home"
        self.seed_select_plot_id = None
        self.drag_tool = None
        self.drag_target_ids.clear()
        self.clear_care()
        self.clear_harvest()
        self.clear_cooking()
        self.clear_hover()
        self.render()

        text = f"Day {self.day}. Morning."
        if matured:
            names = ", ".join(dict.fromkeys(matured))
            text += f". {names} ready to harvest."
        return self.response(tts=text, sfx="morning")

    def draw_time_bar(self):
        self.timepad.clear()
        bar = self.config.get("time", {}).get("bar", {})
        cell_width = int(bar.get("cell_width", 2))
        cell_height = int(bar.get("cell_height", 4))
        filled_columns = int(self.get_time_cells() * cell_width)
        for x in range(filled_columns):
            for dy in range(cell_height):
                self.timepad.set_dot(x, dy)

    def get_unlocked_plot_defs(self):
        return self.config.get("farm", {}).get("plots", [])[:self.unlocked_plot_count]

    def can_craft_recipe(self, recipe_id):
        recipe = self.get_recipe_config(recipe_id)
        if recipe.get("quest_only"): return False
        ingredients = recipe.get("ingredients", {})
        if recipe.get("seafood"): return self.seafood_ready(recipe)
        if len(ingredients) < 2:
            return False
        for seed_id, needed in ingredients.items():
            if int(self.resources["crops"].get(seed_id, 0)) < int(needed):
                return False
        return True

    def get_food_sell_price(self, recipe_id):
        recipe = self.get_recipe_config(recipe_id)
        if recipe.get("sell_price") is not None: return int(recipe["sell_price"])
        ingredient_total = 0
        for seed_id, count in recipe.get("ingredients", {}).items():
            crop_price = int(self.get_seed_config(seed_id).get("crop_price", 1))
            ingredient_total += crop_price * int(count)
        if recipe.get('seafood'):
            prices=[self.get_fish_price(k) for k,v in self.fishing_config()['fish'].items() if v['grade']==recipe.get('fish_grade','low')]
            ingredient_total += min(prices)*recipe.get('fish_required',1)
        return max(1, int(math.ceil(ingredient_total * 1.2)))

    def get_layout_objects(self):
        if self.sleep_until is not None:
            return []
        pages = {
            "load_game": self.get_load_objects,
            "home": self.get_home_objects,
            "farm": self.get_farm_objects,
            "town": self.get_town_objects,
            "mine": self.get_mine_objects,
            "fishing": self.get_fishing_objects,
            "minimap": self.get_minimap_objects,
            "seed_select": self.get_seed_select_objects,
            "inventory": self.get_inventory_objects,
            "research": self.get_research_objects,
            "plot_detail": self.get_plot_detail_objects,
            "water_minigame": self.get_care_minigame_objects,
            "fertilizer_minigame": self.get_care_minigame_objects,
            "harvest": self.get_harvest_objects,
            "recipe_select": self.get_recipe_select_objects,
            "ingredient_select": self.get_ingredient_select_objects,
            "cooking": self.get_cooking_objects,
            "shop_choice": self.get_shop_choice_objects,
            "shop_buy": self.get_shop_buy_objects,
            "shop_sell": self.get_shop_sell_objects,
            "shop_calendar": self.get_calendar_objects,
            "rowan_dialogue": self.get_rowan_objects,
            "rowan_submit": self.get_rowan_objects
        }
        getter = pages.get(self.current_page)
        objects = self.compact_objects(getter()) if getter else []
        # Normalize after layout so rendering and touch share the same anchors.
        for obj in objects:
            if obj.get("type") == "arrow":
                if obj.get("action", "").startswith("shop_page:"):
                    obj.update(x=15 if obj["direction"] == "left" else 25, y=self.dotpad.height-6)
                elif obj.get("direction") == "up" or (
                self.current_page == "home" and obj.get("direction") == "right"):
                    obj.update(direction="right", x=self.dotpad.width-4, y=5)
                elif obj.get("direction") == "left" or (self.current_page == "home" and obj.get("direction") == "down"):
                    obj.update(direction="left", x=3, y=self.dotpad.height-6)
                w,h=(5,9) if obj.get("direction") in ("left","right") else (9,5)
                obj["hit_width"],obj["hit_height"]=w,h
        # Key navigation follows a linear route; the minimap keeps its own geometry.
        route = ("farm", "home", "town", "mine", "fishing")
        if self.current_page in route:
            origin = route.index(self.current_page)
            for obj in objects:
                action = obj.get("action", "")
                if obj.get("type") == "arrow" and action.startswith("travel:"):
                    target = action.split(":", 1)[1]
                    if target in route:
                        obj["direction"] = "left" if route.index(target) < origin else "right"
                        obj["hit_width"], obj["hit_height"] = 5, 9
        return objects

    def get_objects(self):
        return [o for o in self.get_layout_objects() if o.get("type") != "arrow"]

    def get_home_objects(self):
        objects = []
        stove_y = next(
        (
            obj.get("y")
            for obj in self.config.get("home", {}).get("objects", [])
            if obj.get("id") == "home_stove"
        ),
        None
    )

        for obj in self.config.get("home", {}).get("objects", []):
            copied = dict(obj)

        # 연구대를 stove와 같은 y축에 정렬
            if copied.get("type") == "chest" and stove_y is not None:
                copied["y"] = stove_y

            if self.day_ended and copied.get("id") != "home_bed":
                continue
            if self.day_ended and copied.get("id") == "home_bed":
                copied["tts"] = "Bed. Sleep until morning."
            if copied.get("id") == "home_stove" and not self.day_ended:
                craftable = sum(
                1 for rid in self.config.get("recipes", {})
                if self.can_craft_recipe(rid)
            )
                copied["tts"] = f"Kitchen. Available recipes: {craftable}."

            objects.append(copied)

        return objects

    def get_farm_objects(self):
        farm = self.config.get("farm", {})
        objects = []

        for plot in self.get_unlocked_plot_defs():
            obj = dict(plot)
            obj["type"] = "plot"
            state = self.farm_plots[plot["id"]]
            seed_id = state["seed_id"]

            if seed_id is None:
                obj["tts"] = f"{plot['label']}. Empty. Select to manage."
                obj["action"] = f"open_plot_detail:{plot['id']}"
            else:
                seed_label = self.get_seed_label(seed_id)
                needed = int(self.get_seed_config(seed_id).get("growth_days", 3))
                if state["mature"]:
                    obj["tts"] = f"{plot['label']}. {seed_label}. Ready to harvest."
                else:
                    water_text = "Watered" if state["watered"] else "Needs water"
                    fertilizer_text = "Fertilized" if state["fertilized"] else "Not fertilized"
                    obj["tts"] = (
                        f"{plot['label']}. {seed_label} is growing. "
                        f"Growth {state['growth']} of {needed} days. {water_text}. {fertilizer_text}. "
                        "Select to manage."
                    )
                obj["action"] = f"open_plot_detail:{plot['id']}"
            objects.append(obj)

        for obj in farm.get("objects", []):
            objects.append(dict(obj))
        return objects

    def get_plot_detail_objects(self):
        plot_id = self.detail_plot_id
        state = self.farm_plots.get(plot_id) if plot_id else None
        if state is None:
            return [self.back_arrow("plot_detail_back", "Back to farm", "return_scene")]

        plot_label = self.get_plot_label(plot_id)
        seed_id = state.get("seed_id")
        if seed_id is None:
            return [
                {
                    "id": "plot_detail_empty", "type": "plot_detail_field",
                    "x": 30, "y": 17, "width": 44, "height": 18,
                    "hit_width": 48, "hit_height": 18,
                    "label": f"{plot_label} details",
                    "tts": f"{plot_label}. Empty plot.",
                    "action": ""
                },
                {
                    "id": "plot_detail_plant", "type": "care_button", "care_kind": "plant",
                    "x": 30, "y": 31, "width": 18, "height": 6,
                    "hit_width": 22, "hit_height": 10,
                    "label": "Plant seeds",
                    "tts": "Plant. Choose seeds.",
                    "action": f"open_seed_select:{plot_id}"
                },
                self.back_arrow("plot_detail_back", "Back to farm", "return_scene")
            ]

        seed_label = self.get_seed_label(seed_id)
        needed = int(self.get_seed_config(seed_id).get("growth_days", 3))
        water_text = "Watered" if state["watered"] else "Needs water"
        if state["fertilized"]:
            fertilizer_text = "Fertilized"
        elif int(self.resources.get("fertilizer", 0)) <= 0:
            fertilizer_text = "No fertilizer. Buy at the shop."
        else:
            fertilizer_text = f"Not fertilized. Stock: {self.resources.get('fertilizer', 0)} in stock"

        field_tts = (
            f"{plot_label}. {seed_label}. "
            f"Growth {state['growth']} of {needed} days. {water_text}. {fertilizer_text}"
        )
        if state["mature"]:
            field_tts = f"{plot_label}. {seed_label}. Ready to harvest."

        objects = [{
            "id": "plot_detail_field", "type": "plot_detail_field",
            "x": 30, "y": 17, "width": 44, "height": 18,
            "hit_width": 48, "hit_height": 18,
            "label": f"{plot_label} details", "tts": field_tts, "action": ""
        }, {
            "id": "plot_detail_growth_gauge", "type": "growth_gauge",
            "x": 30, "y": 4, "width": 42, "height": 5,
            "hit_width": 44, "hit_height": 6,
            "label": "Growth",
            "tts": f"Growth. {seed_label}. {needed if state['mature'] else state['growth']} of {needed} days",
            "action": ""
        }]

        if state["mature"]:
            objects.append({
                "id": "plot_detail_harvest", "type": "care_button", "care_kind": "harvest",
                "x": 30, "y": 31, "width": 18, "height": 6,
                "hit_width": 22, "hit_height": 10,
                "label": "Harvest",
                "tts": f"Harvest. {seed_label}. Ready to harvest.",
                "action": f"start_harvest:{plot_id}"
            })
        else:
            water_action = "" if state["watered"] else f"start_care:water:{plot_id}"
            water_tts = (
                "Already watered."
                if state["watered"]
                else "Water. Drag over targets."
            )
            objects.append({
                "id": "plot_detail_water", "type": "care_button", "care_kind": "water",
                "x": 23, "y": 31, "width": 18, "height": 6,
                "hit_width": 21, "hit_height": 10,
                "label": "Water", "tts": water_tts, "action": water_action
            })

            fertilizer_count = int(self.resources.get("fertilizer", 0))
            fertilizer_action = ""
            if not state["fertilized"] and fertilizer_count > 0:
                fertilizer_action = f"start_care:fertilizer:{plot_id}"
            if state["fertilized"]:
                fertilizer_tts = "Already fertilized."
            elif fertilizer_count <= 0:
                fertilizer_tts = "No fertilizer. Buy at the shop."
            else:
                fertilizer_tts = f"Fertilizer. Stock: {fertilizer_count}."
            objects.append({
                "id": "plot_detail_fertilizer", "type": "care_button", "care_kind": "fertilizer",
                "x": 46, "y": 31, "width": 18, "height": 6,
                "hit_width": 21, "hit_height": 10,
                "label": "Fertilize", "tts": fertilizer_tts, "action": fertilizer_action
            })

        objects.append(self.back_arrow("plot_detail_back", "Back to farm", "return_scene"))
        return objects

    def get_care_minigame_objects(self):
        plot_id = self.detail_plot_id
        state = self.farm_plots.get(plot_id) if plot_id else None
        if state is None or state.get("seed_id") is None:
            return []
        seed_label = self.get_seed_label(state["seed_id"])
        mode_label = "Water" if self.care_mode == "water" else "Fertilizer"
        field = self.config.get("care_minigame", {}).get("field", {})
        objects = [{
            "id": "care_field", "type": "care_field",
            "x": int(field.get("x", 30)), "y": int(field.get("y", 20)),
            "width": int(field.get("width", 46)), "height": int(field.get("height", 30)),
            "hit_width": int(field.get("width", 46)), "hit_height": int(field.get("height", 30)),
            "label": f"{mode_label} plot",
            "tts": f" {seed_label} plot. Move to apply {mode_label}.",
            "action": ""
        }]
        for target in self.care_targets:
            if (target["id"] in self.care_collected_ids
                    and self.care_visible_until.get(target["id"], 0) <= time.monotonic()):
                continue
            objects.append({
                "id": target["id"], "type": "care_target", "care_kind": self.care_mode,
                "x": target["x"], "y": target["y"],
                "width": 5, "height": 5, "hit_width": 8, "hit_height": 8,
                "label": f"{mode_label} target",
                "tts": f"{mode_label} target. Move.",
                "action": ""
            })
        return objects

    def get_town_objects(self):
        return [dict(obj) for obj in self.config.get("town", {}).get("objects", [])] + [self.rowan_object()]

    def get_seed_select_objects(self):
        objects = []
        positions = [(12, 18), (30, 18), (48, 18)]
        available = []
        for seed_id, seed_config in self.config.get("seeds", {}).items():
            count = int(self.resources["seeds"].get(seed_id, 0))
            if count > 0:
                available.append((seed_id, seed_config, count))

        for index, (seed_id, seed_config, count) in enumerate(available[:len(positions)]):
            x, y = positions[index]
            yield_count = self.get_harvest_base_yield(seed_id)
            growth_days = int(seed_config.get("growth_days", 3))
            objects.append({
                "id": f"seed_{seed_id}", "type": "seed", "seed_id": seed_id,
                "x": x, "y": y, "width": 12, "height": 10,
                "hit_width": 15, "hit_height": 13,
                "label": f"{seed_config.get('label', seed_id)} seeds",
                "tts": f"{seed_config.get('label', seed_id)} seeds {count}. Growth {growth_days} days, Harvest {yield_count}, Seed recovery level {self.research_levels.get('seed_return', 0)}",
                "action": f"plant:{self.seed_select_plot_id}:{seed_id}"
            })

        objects.append(self.back_arrow("seed_back", "Back to farm", "return_scene"))
        return objects

    def get_inventory_objects(self):
        entries = [
            {"id": "coin", "label": "Gold", "count": int(self.resources.get("coin", 0)), "kind": "coin", "action": ""},
            {"id": "fertilizer", "label": "Fertilizer", "count": int(self.resources.get("fertilizer", 0)), "kind": "fertilizer", "action": ""},
            {"id": "wood", "label": "Wood", "count": int(self.resources.get("wood", 0)), "kind": "material", "action": ""},
            {"id": "stone", "label": "Stone", "count": int(self.resources.get("stone", 0)), "kind": "stone", "action": ""}
        ]
        for item_id, label in [("pickaxe", "Pickaxe"), ("copper", "Copper"), ("iron", "Iron"), ("diamond", "Diamond")]:
            entries.append({"id": item_id, "label": label, "count": self.resources[item_id], "kind": item_id, "action": ""})
        for seed_id, seed_config in self.config.get("seeds", {}).items():
            entries.append({"id": f"seed_{seed_id}", "label": f"{seed_config.get('label', seed_id)} seeds", "count": int(self.resources["seeds"].get(seed_id, 0)), "kind": "seed", "seed_id": seed_id, "action": ""})
        for seed_id, seed_config in self.config.get("seeds", {}).items():
            entries.append({"id": f"crop_{seed_id}", "label": f"{seed_config.get('label', seed_id)} crops", "count": int(self.resources["crops"].get(seed_id, 0)), "kind": "crop", "seed_id": seed_id, "action": ""})
        for recipe_id, recipe in self.config.get("recipes", {}).items():
            count = int(self.resources["foods"].get(recipe_id, 0))
            if count <= 0 and self.inventory_hide_zero_items:
                continue
            entries.append({
                "id": f"food_{recipe_id}", "label": recipe.get("label", recipe_id),
                "count": count, "kind": "food", "recipe_id": recipe_id, "action": f"use_food:{recipe_id}",
                "extra_tts": f"Use: {self.recipe_effect_text(recipe)}"
            })

        entries.append({"id":"fishing_rod", "label":"Fishing rod", "count":self.resources.get("fishing_rod",0), "kind":"tool", "action":""})
        for key, fish in self.fishing_config()['fish'].items():
            entries.append({"id":key, "label":fish['label'], "count":self.resources['fish'].get(key,0), "kind":"fish", "action":""})
        entries = [entry for entry in entries if entry['kind']=='coin' or entry['count']>0]
        page_size = min(12, max(2, self.inventory_items_per_page))
        gold = next(e for e in entries if e['kind']=='coin')
        foods = [e for e in entries if e['kind']=='food']
        others = [e for e in entries if e['kind'] not in ('coin','food')]
        pages = [[gold]+foods[:page_size-1]]
        overflow=foods[page_size-1:]
        pages += [overflow[i:i+page_size] for i in range(0,len(overflow),page_size)]
        pages += [others[i:i+page_size] for i in range(0,len(others),page_size)]
        self.inventory_page_count=len(pages)
        self.inventory_page=max(0,min(self.inventory_page,self.inventory_page_count-1))
        entries=pages[self.inventory_page]
        positions = [
            (9, 5), (23, 5), (37, 5), (51, 5),
            (9, 15), (23, 15), (37, 15), (51, 15),
            (9, 25), (23, 25), (37, 25), (51, 25)
        ]
        objects = []
        for index, entry in enumerate(entries[:len(positions)]):
            x, y = positions[index]
            extra = entry.get("extra_tts", "")
            tts = f"{entry['label']} {entry['count']}."
            if extra:
                tts += f". {extra}"
            objects.append({
                "id": f"inventory_{entry['id']}", "type": "resource",
                "count": entry["count"], "resource_kind": entry["kind"], "recipe_id": entry.get("recipe_id"), "seed_id": entry.get("seed_id"), "x": x, "y": y,
                "width": 10, "height": 8 if entry["kind"] == "food" else 6, "hit_width": 13, "hit_height": 9,
                "label": entry["label"], "tts": tts, "action": entry.get("action", "")
            })
        for delta, x, label, direction in [(-1, 9, "Previous page", "left"), (1, 51, "Next page", "right")]:
            if 0 <= self.inventory_page + delta < self.inventory_page_count:
                objects.append({"id": f"inventory_page_{direction}", "type": "arrow",
                                "x": x, "y": 35, "direction": direction, "size": 2,
                                "hit_width": 11, "hit_height": 7,
                                "label": label, "tts": label,
                                "action": f"inventory_page:{delta}"})
        return objects

    @staticmethod
    def compress_axis(intervals, margin=2, max_gap=8):
        """Preserve occupied spans; shorten only empty gaps between them."""
        merged = []
        for low, high in sorted(intervals):
            if merged and low <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], high)
            else:
                merged.append([low, high])
        if not merged:
            return lambda value: value
        anchors = []
        target = margin
        previous_high = None
        for low, high in merged:
            if previous_high is not None:
                target += min(max_gap, low-previous_high)
            anchors.append((low, target))
            target += high-low
            anchors.append((high, target))
            previous_high = high
        def transform(value):
            if value <= anchors[0][0]: return value-anchors[0][0]+anchors[0][1]
            for (a, ta), (b, tb) in zip(anchors, anchors[1:]):
                if a <= value <= b and b > a:
                    return ta+(value-a)*(tb-ta)/(b-a)
            return value-anchors[-1][0]+anchors[-1][1]
        return transform

    def spatial_objects(self, objects):
        # Scene furniture and exits retain their original relative positions.
        copied = [dict(o) for o in objects]
        if not copied: return copied
        def dims(o):
            if o.get("type") == "arrow":
                return (5,9) if o.get("direction") in ("left","right") else (9,5)
            return o.get("width",10), o.get("height",8)
        tx = self.compress_axis([(o["x"]-dims(o)[0]//2, o["x"]+(dims(o)[0]-1)//2) for o in copied], max_gap=5)
        ty = self.compress_axis([(o["y"]-dims(o)[1]//2, o["y"]+(dims(o)[1]-1)//2) for o in copied], max_gap=5)
        for o in copied:
            w,h=dims(o)
            o.update(x=round(tx(o["x"])), y=round(ty(o["y"])), hit_width=w, hit_height=h)
        return copied

    def get_minimap_objects(self):
        cfg = self.config.get("minimap", {})
        locations = [dict(o) for o in cfg.get("locations", [])]
        if not locations: return []
        # Original nodes are seven-dot outlines. Do not scale their shapes.
        tx = self.compress_axis([(o["x"]-3,o["x"]+3) for o in locations])
        ty = self.compress_axis([(o["y"]-3,o["y"]+3) for o in locations])
        objects = []
        for route in cfg.get("routes", []):
            obj = dict(route)
            obj.update(type="route", x1=round(tx(route["x1"])), x2=round(tx(route["x2"])),
                       y1=round(ty(route["y1"])), y2=round(ty(route["y2"])),
                       label="Path", tts="Path", hit_radius=1)
            objects.append(obj)
        current = next((o for o in locations if o.get("location")==self.current_location), None)
        for source in locations:
            obj = dict(source)
            location = obj["location"]
            label = self.get_page_name(location)
            here = location == self.current_location
            # Directions come from original coordinates, before gap compression.
            direction = self.get_relative_direction(current, source) if current and not here else ""
            obj.update(type="node", x=round(tx(source["x"])), y=round(ty(source["y"])),
                       width=7, height=7, hit_width=7, hit_height=7, current=here,
                       label=label, tts=label+(". You are here." if here else (f". {direction}." if direction else ".")),
                       action=f"travel:{location}")
            objects.append(obj)
        return objects

    def get_research_objects(self):
        objects = []
        coin = int(self.resources.get("coin", 0))
        seed_cfg = self.config.get("research", {}).get("seed_return", {})
        level = int(self.research_levels.get("seed_return", 0))
        max_level = int(seed_cfg.get("max_level", 2))
        costs = list(seed_cfg.get("costs", []))

        if level >= max_level:
            seed_tts = f"Seed recovery. Level {level}. Maximum level."
            seed_action = ""
        else:
            cost = int(costs[level]) if level < len(costs) else 999999
            copper_cost = int(seed_cfg.get("copper_costs", [3, 6])[level])
            seed_tts = f"Seed recovery, level {level}. Next level:  {cost} gold, Copper {copper_cost} required"
            seed_action = "research:seed_return"

        objects.append({
            "id": "research_seed_return", "type": "research", "research_kind": "seed_return",
            "x": 19, "y": 18, "width": 18, "height": 12, "hit_width": 20, "hit_height": 14,
            "label": "Seed recovery", "tts": seed_tts, "action": seed_action
        })

        expand_cfg = self.config.get("research", {}).get("field_expansion", {})
        all_plots = self.config.get("farm", {}).get("plots", [])
        costs = list(expand_cfg.get("costs", []))
        initial = int(expand_cfg.get("initial_plot_count", 2))
        expansion_index = max(0, self.unlocked_plot_count - initial)
        if self.unlocked_plot_count >= len(all_plots):
            expand_tts = f"Farm expansion. Plots: {self.unlocked_plot_count} "
            expand_action = ""
        else:
            cost = int(costs[expansion_index]) if expansion_index < len(costs) else 999999
            material_cost = int(expand_cfg.get("stone_costs", [5, 10])[expansion_index])
            expand_tts = f"Plot {self.unlocked_plot_count}. {cost} gold, Stone {material_cost} to add a plot. Gold: {coin} gold"
            expand_action = "research:field_expand"

        objects.append({
            "id": "research_field_expand", "type": "research", "research_kind": "field_expand",
            "x": 41, "y": 18, "width": 18, "height": 12, "hit_width": 20, "hit_height": 14,
            "label": "Farm expansion", "tts": expand_tts, "action": expand_action
        })
        for kind, label, mineral in [("mineral_luck", "Mineral discovery", "iron")]:
            cfg = self.config.get("research", {}).get(kind, {})
            level = self.research_levels.get(kind, 0)
            action = "" if level >= int(cfg.get("max_level", 2)) else f"research:{kind}"
            text = f"{label}. Level {level}. Maximum level." if not action else f"{label}. Level {level + 1}. Requires {cfg.get('costs', [20, 40])[level]} gold, {self.MINERAL_LABELS[mineral]} {cfg.get(mineral + '_costs', [3, 6])[level]} required"
            objects.append({"id": f"research_{kind}", "type": "research", "research_kind": kind, "label": label, "tts": text, "action": action})
        for i, obj in enumerate(objects):
            obj.update(x=8+15*(i%3), y=6+12*(i//3), width=12, height=8, hit_width=12, hit_height=8)
            kind = obj["research_kind"]
            key = "field_expansion" if kind == "field_expand" else kind
            cfg = self.config.get("research", {}).get(key, {})
            index = expansion_index if kind == "field_expand" else self.research_levels.get(kind, 0)
            material = {"seed_return": "copper", "field_expand": "stone", "mineral_luck": "iron"}[kind]
            obj["display_quantities"] = []
            if obj.get("action"):
                costs = cfg.get("costs", [])
                materials = cfg.get(material + "_costs", [3, 6] if material != "stone" else [5, 10])
                for resource, required in [("coin", costs[index] if index < len(costs) else 999999),
                                           (material, materials[index])]:
                    obj["display_quantities"].append({"item": resource, "label": "Gold" if resource == "coin" else resource.title(),
                                                    "required": int(required), "owned": int(self.resources.get(resource, 0))})
        objects.append(self.back_arrow("research_back", "Back home", "return_scene"))
        return objects

    def get_harvest_objects(self):
        if self.harvest_plot_id is None:
            return []
        state = self.farm_plots.get(self.harvest_plot_id)
        if state is None or state["seed_id"] is None:
            return []
        seed_label = self.get_seed_label(state["seed_id"])
        field = self.config.get("harvest_minigame", {}).get("field", {})
        objects = [{
            "id": "harvest_field", "type": "harvest_field",
            "x": int(field.get("x", 30)), "y": int(field.get("y", 20)),
            "width": int(field.get("width", 46)), "height": int(field.get("height", 30)),
            "hit_width": int(field.get("width", 46)), "hit_height": int(field.get("height", 30)),
            "label": " Plot",
            "tts": f"Move over crops.",
            "action": ""
        }]
        for target in self.harvest_targets:
            if target["id"] in self.harvest_collected_ids:
                continue
            objects.append({
                "id": target["id"], "type": "harvest_crop", "x": target["x"], "y": target["y"],
                "width": 5, "height": 5, "hit_width": 7, "hit_height": 7,
                "label": f"Harvest {seed_label}", "tts": f"Harvest {seed_label}. Move.", "action": ""
            })
        return objects

    def get_recipe_select_objects(self):
        craftable = [(rid, cfg) for rid, cfg in self.config.get("recipes", {}).items() if not cfg.get("hidden_recipe") and self.can_craft_recipe(rid)]
        positions = [(8+15*(i%3),6+12*(i//3)) for i in range(6)]
        objects = []
        for index, (recipe_id, recipe) in enumerate(craftable[:len(positions)]):
            x, y = positions[index]
            ingredient_text = self.recipe_ingredient_text(recipe_id)
            objects.append({
                "id": f"recipe_{recipe_id}", "type": "recipe", "recipe_id": recipe_id,
                "x": x, "y": y, "width": 12, "height": 9, "hit_width": 14, "hit_height": 11,
                "label": recipe.get("label", recipe_id),
                "tts": f"{recipe.get('label', recipe_id)}. {ingredient_text}. {self.recipe_effect_text(recipe)}",
                "action": f"select_recipe:{recipe_id}"
            })
        objects.append(self.back_arrow("recipe_back", "Back home", "return_scene"))
        return objects

    def get_ingredient_select_objects(self):
        recipe = self.get_recipe_config(self.selected_recipe_id)
        if not recipe:
            return [self.back_arrow("ingredient_back", "Back to kitchen", "open_recipes")]
        positions = [(15, 17), (30, 17), (45, 17)]
        objects = []
        for index, (seed_id, needed) in enumerate(recipe.get("ingredients", {}).items()):
            if index >= len(positions):
                break
            x, y = positions[index]
            selected = seed_id in self.selected_ingredients
            count = int(self.resources["crops"].get(seed_id, 0))
            label = self.get_seed_label(seed_id)
            status = "Selected" if selected else "Not selected"
            objects.append({
                "id": f"ingredient_{seed_id}", "type": "ingredient", "ingredient_id": seed_id,
                "count": count, "required_count": int(needed), "selected": selected, "x": x, "y": y, "width": 12, "height": 9,
                "hit_width": 14, "hit_height": 11, "label": f"{label} ingredient",
                "tts": f"{label}. Need {needed}, stock {count}. {status}",
                "action": f"toggle_ingredient:{seed_id}"
            })

        objects.append(self.back_arrow("ingredient_back", "Back to recipes", "open_recipes"))
        return self.seafood_ingredient_objects(objects)

    def get_cooking_objects(self):
        return []

    def get_shop_choice_objects(self):
        return [
            {
                "id": "shop_sell_choice", "type": "shop_choice", "choice": "sell",
                "x": 15, "y": 20, "width": 28, "height": 34, "hit_width": 30, "hit_height": 38,
                "label": "Sell", "tts": "Sell.", "action": "shop_mode:sell"
            },
            {
                "id": "shop_buy_choice", "type": "shop_choice", "choice": "buy",
                "x": 45, "y": 20, "width": 28, "height": 34, "hit_width": 30, "hit_height": 38,
                "label": "Buy", "tts": "Buy.", "action": "shop_mode:buy"
            },
            {"id":"shop_calendar", "type":"calendar_button", "x":38,"y":8,"width":12,"height":12,
             "label":"Calendar", "tts":"Calendar. Weekly offers.", "action":"open_calendar"}
        ]

    def get_shop_buy_objects(self):
        entries = [("seed", seed_id, f"{self.get_seed_label(seed_id)} seeds", self.resources["seeds"].get(seed_id, 0),
                    int(seed.get("seed_price", max(1, round(int(seed.get("crop_price", 1)) * .8)))))
                   for seed_id, seed in self.config.get("seeds", {}).items()]
        entries += [("fertilizer", "fertilizer", "Fertilizer", self.resources["fertilizer"], self.get_fertilizer_price()),
                    ("pickaxe", "pickaxe", "Pickaxe", self.resources["pickaxe"], self.get_pickaxe_price())]
        entries += [("mineral", key, self.MINERAL_LABELS[key], self.resources[key], self.get_mineral_price(key, buying=True))
                    for key in ("stone", "copper", "iron")]
        entries.append(("fishing_rod", "fishing_rod", "Fishing rod", self.resources.get("fishing_rod",0), self.get_rod_price()))
        return self.build_shop_objects(entries, "buy")

    def get_shop_sell_objects(self):
        entries = [("crop", key, f"{self.get_seed_label(key)} crops", self.resources["crops"].get(key, 0), int(seed.get("crop_price", 1)))
                   for key, seed in self.config.get("seeds", {}).items() if self.resources["crops"].get(key, 0) > 0]
        entries += [("food", key, recipe.get("label", key), self.resources["foods"].get(key, 0), self.get_food_sell_price(key))
                    for key, recipe in self.config.get("recipes", {}).items() if self.resources["foods"].get(key, 0) > 0]
        entries += [("mineral", key, label, self.resources[key], self.get_mineral_price(key))
                    for key, label in self.MINERAL_LABELS.items() if self.resources[key] > 0]
        entries += [("fish", key, fish['label'], self.resources['fish'].get(key,0), self.get_fish_price(key))
                    for key, fish in self.fishing_config()['fish'].items() if self.resources['fish'].get(key,0)>0]
        return self.build_shop_objects(entries, "sell")

    def back_arrow(self, object_id, label, action):
        return {
            "id": object_id, "type": "arrow", "x": 6, "y": 35,
            "direction": "left", "size": 2, "hit_width": 11, "hit_height": 9,
            "label": label, "tts": f"{label}.", "action": action
        }

    def recipe_ingredient_text(self, recipe_id):
        recipe = self.get_recipe_config(recipe_id)
        parts = []
        for seed_id, count in recipe.get("ingredients", {}).items():
            parts.append(f"{self.get_seed_label(seed_id)} {count} ")
        if recipe.get("seafood"): parts.append("Choose one fish")
        return ", ".join(parts)

    def get_relative_direction(self, origin, target):
        if origin is None:
            return ""
        dx = float(target["x"]) - float(origin["x"])
        dy = float(target["y"]) - float(origin["y"])
        if abs(dx) > 4 and abs(dy) > 4:
            horizontal = "right" if dx > 0 else "left"
            vertical = "down" if dy > 0 else "up"
            return f"{horizontal} {vertical}"
        if abs(dx) >= abs(dy):
            return "right" if dx > 0 else "left" if dx < 0 else ""
        return "down" if dy > 0 else "up" if dy < 0 else ""

    def render(self):
        self.dotpad.clear()
        if self.sleep_until is not None:
            self.timepad.clear()
            return
        for obj in self.get_objects():
            obj_type = obj.get("type")
            if obj_type == "rowan":
                self.draw_rowan(obj)
            elif obj_type in ("calendar_day", "calendar_button"):
                self.draw_calendar(obj)
            elif obj_type == "save_slot":
                self.dotpad.draw_box(obj["x"], obj["y"], obj["width"], obj["height"])
                self.dotpad.draw_box(obj["x"], obj["y"], 4, 4)
            elif obj_type == "mine_rock":
                self.draw_mine_rock(obj)
            elif obj_type == "arrow":
                self.draw_triangle(obj["x"], obj["y"], obj["direction"], obj.get("size", 2))
            elif obj_type == "box":
                self.dotpad.draw_box(obj["x"], obj["y"], obj.get("width", 6), obj.get("height", 5))
            elif obj_type == "bed":
                self.draw_bed(obj)
            elif obj_type == "chest":
                self.draw_chest(obj)
            elif obj_type == "stove":
                self.draw_stove(obj)
            elif obj_type == "plot":
                self.draw_plot(obj)
            elif obj_type == "node":
                self.draw_node(obj)
            elif obj_type == "route":
                self.dotpad.draw_line(obj["x1"], obj["y1"], obj["x2"], obj["y2"])
            elif obj_type == "watering_can":
                self.draw_watering_can(obj)
            elif obj_type == "fertilizer":
                self.draw_fertilizer(obj)
            elif obj_type == "seed":
                self.draw_seed(obj)
            elif obj_type == "resource":
                self.draw_resource(obj)
            elif obj_type == "research":
                self.draw_research(obj)
            elif obj_type == "plot_detail_field":
                self.draw_plot_detail_field(obj)
            elif obj_type == "growth_gauge":
                self.draw_plot_detail_gauge(obj)
            elif obj_type == "care_button":
                self.draw_care_button(obj)
            elif obj_type == "care_field":
                self.dotpad.draw_box(obj["x"], obj["y"], obj.get("width", 46), obj.get("height", 30))
            elif obj_type == "care_target":
                self.draw_care_target(obj)
            elif obj_type == "harvest_field":
                self.dotpad.draw_box(obj["x"], obj["y"], obj.get("width", 46), obj.get("height", 30))
            elif obj_type == "harvest_crop":
                self.draw_harvest_crop(obj)
            elif obj_type == "recipe":
                self.draw_recipe(obj)
            elif obj_type == "ingredient":
                self.draw_ingredient(obj)
            elif obj_type == "cooking_start":
                self.draw_cooking_start(obj)
            elif obj_type == "shop_npc":
                self.draw_shop_npc(obj)
            elif obj_type == "shop_choice":
                self.draw_shop_choice(obj)
            elif obj_type == "shop_item":
                self.draw_shop_item(obj)

        if self.current_page == "fishing":
            self.draw_lake()
        if self.current_page == "cooking":
            self.draw_cooking_path()
        self.draw_time_bar()

    def draw_triangle(self, x, y, direction, size=2):
        # A 45-degree outline avoids shallow, syringe-like diagonal steps.
        # Right/left: 5 x 9 dots. Up/down: the same pattern rotated, 9 x 5.
        points = {(0,row) for row in range(9)}
        points.update((4-abs(row-4),row) for row in range(9))
        if direction == "left": points={(4-col,row) for col,row in points}
        elif direction == "up": points={(row,4-col) for col,row in points}
        elif direction == "down": points={(row,col) for col,row in points}
        elif direction != "right": raise ValueError("Unknown triangle direction")
        w,h = (5,9) if direction in ("left","right") else (9,5)
        for col,row in points:
            self.dotpad.set_dot(round(x)-w//2+col, round(y)-h//2+row)

    def draw_bed(self, obj):
        self.draw_facility(obj)

    def draw_chest(self, obj):
        self.draw_facility(obj)

    def draw_stove(self, obj):
        self.draw_facility(obj)

    def draw_plot(self, obj):
        left, top, width, height = self.plot_bounds(obj)
        # Draw the frame explicitly so DotPad.draw_box rounding cannot offset the fill.
        for y in range(top, top+height):
            for x in range(left, left+width):
                if x in (left, left+width-1) or y in (top, top+height-1):
                    self.dotpad.set_dot(x, y)
        state = self.farm_plots.get(obj["id"], self.new_plot_state())
        self.draw_plot_progress(obj, state)

    @staticmethod
    def plot_bounds(obj):
        width, height = int(obj.get("width", 10)), int(obj.get("height", 8))
        return round(obj["x"])-width//2, round(obj["y"])-height//2, width, height

    def draw_plot_progress(self, obj, state):
        if state["seed_id"] is None: return
        needed = max(1, int(self.get_seed_config(state["seed_id"]).get("growth_days", 3)))
        ratio = 1.0 if state["mature"] else max(0.0, min(1.0, float(state["growth"]) / needed))
        left, top, width, height = self.plot_bounds(obj)
        rows = min(height-2, math.ceil((height-2)*ratio))
        for y in range(top+height-1-rows, top+height-1):
            for x in range(left+1, left+width-1): self.dotpad.set_dot(x, y)

    def draw_watering_can(self, obj):
        x, y = int(obj["x"]), int(obj["y"])
        self.dotpad.draw_box(x, y, 6, 5)
        self.dotpad.draw_line(x + 3, y - 1, x + 7, y - 3)
        self.dotpad.draw_line(x + 7, y - 3, x + 8, y - 2)
        self.dotpad.draw_line(x - 3, y - 1, x - 5, y - 1)

    def draw_fertilizer(self, obj):
        x, y = int(obj["x"]), int(obj["y"])
        self.dotpad.draw_box(x, y, 6, 7)
        self.dotpad.draw_line(x - 2, y - 1, x + 2, y - 1)
        self.dotpad.set_dot(x, y + 1)
        self.dotpad.set_dot(x - 1, y + 2)
        self.dotpad.set_dot(x + 1, y + 2)

    def draw_seed(self, obj):
        self.draw_catalog_item(obj, "seed")

    def draw_crop_symbol(self, x, y, seed_id):
        # Distinct compact silhouettes: round fruit, tapered root, paired tubers.
        patterns = {
            "tomato": ["00100", "01010", "10001", "10001", "01110"],
            "carrot": ["10101", "01110", "01010", "00100", "00100"],
            "potato": ["11000", "10110", "01101", "00101", "00010"]
        }
        rows = patterns.get(seed_id, ["00100", "01110", "00100", "00000", "00000"])
        for j, row in enumerate(rows):
            for i, raised in enumerate(row):
                if raised == "1":
                    self.dotpad.set_dot(x + i - 2, y + j - 2)

    def draw_resource(self, obj):
        self.draw_catalog_item(obj, obj.get("resource_kind"), obj.get("recipe_id"))

    def draw_filled_square(self, x, y, size=4):
        left, top = round(x)-size//2, round(y)-size//2
        for yy in range(top, top+size):
            for xx in range(left, left+size): self.dotpad.set_dot(xx, yy)

    def draw_node(self, obj):
        if obj.get("current"):
            self.draw_filled_square(obj["x"], obj["y"], 7)
        else:
            self.dotpad.draw_box(obj["x"], obj["y"], 7, 7)

    def draw_icon_pattern(self, x, y, rows):
        if not rows:
            return
        width, height = max(map(len, rows)), len(rows)
        for row_index, row in enumerate(rows):
            for column, value in enumerate(row):
                if value == "1":
                    self.dotpad.set_dot(int(x) + column - width // 2, int(y) + row_index - height // 2)

    def draw_recipe_icon(self, x, y, recipe_id):
        self.draw_icon_pattern(x, y, self.get_recipe_config(recipe_id).get("icon", []))

    def draw_research(self, obj):
        x, y = int(obj["x"]), int(obj["y"])
        self.dotpad.draw_box(x, y, obj.get("width", 20), obj.get("height", 10))
        kind = obj.get("research_kind")
        cfg = self.config.get("research", {}).get("field_expansion" if kind == "field_expand" else kind, {})
        self.draw_icon_pattern(x, y, cfg.get("icon", []))

    def draw_plot_detail_field(self, obj):
        x, y = int(obj["x"]), int(obj["y"])
        width, height = int(obj.get("width", 44)), int(obj.get("height", 18))
        self.dotpad.draw_box(x, y, width, height)
        plot_id = self.detail_plot_id
        state = self.farm_plots.get(plot_id) if plot_id else None
        if not state or state.get("seed_id") is None:
            return
        if state.get("mature"):
            for dx, dy in [(-8, 1), (-4, -2), (0, 2), (5, -1), (9, 2)]:
                for ox, oy in [(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)]:
                    self.dotpad.set_dot(x + dx + ox, y + dy + oy)
        else:
            self.dotpad.set_dot(x, y)
            if state.get("watered"):
                self.dotpad.draw_line(x - 8, y + 5, x + 8, y + 5)
            if state.get("fertilized"):
                self.dotpad.set_dot(x - 10, y - 5)
                self.dotpad.set_dot(x + 10, y - 5)

    def draw_plot_detail_gauge(self, obj):
        plot_id = self.detail_plot_id
        state = self.farm_plots.get(plot_id) if plot_id else None
        if not state or state.get("seed_id") is None:
            return
        needed = max(1, int(self.get_seed_config(state["seed_id"]).get("growth_days", 3)))
        growth = needed if state.get("mature") else min(needed, int(state.get("growth", 0)))
        x1 = obj["x"] - obj["width"] // 2
        x2 = x1 + obj["width"] - 1
        y1 = obj["y"] - obj["height"] // 2
        y2 = y1 + obj["height"] - 1
        self.dotpad.draw_line(x1, y1, x2, y1)
        self.dotpad.draw_line(x2, y1, x2, y2)
        self.dotpad.draw_line(x2, y2, x1, y2)
        self.dotpad.draw_line(x1, y2, x1, y1)
        inner_width = x2 - x1 - 1
        fill = int(round(inner_width * growth / needed))
        for x in range(x1 + 1, x1 + 1 + fill):
            for y in range(y1 + 1, y2):
                self.dotpad.set_dot(x, y)

    def draw_care_button(self, obj):
        x, y = int(obj["x"]), int(obj["y"])
        self.dotpad.draw_box(x, y, obj.get("width", 18), obj.get("height", 7))
        kind = obj.get("care_kind")
        if kind == "water":
            self.draw_icon_pattern(x, y, ["00100", "01110", "11111", "11111", "01110"])
        elif kind == "fertilizer":
            self.draw_category(x, y, "fertilizer")
        elif kind == "harvest":
            self.draw_harvest_crop({"x": x, "y": y})
        elif kind == "plant":
            self.dotpad.set_dot(x, y)
            self.dotpad.set_dot(x - 1, y + 1)
            self.dotpad.set_dot(x + 1, y + 1)
            self.dotpad.set_dot(x, y - 1)

    def draw_care_target(self, obj):
        x, y = int(obj["x"]), int(obj["y"])
        if obj.get("care_kind") == "water":
            self.dotpad.set_dot(x, y - 1)
            self.dotpad.set_dot(x - 1, y)
            self.dotpad.set_dot(x, y)
            self.dotpad.set_dot(x + 1, y)
            self.dotpad.set_dot(x, y + 1)
        else:
            self.dotpad.set_dot(x - 1, y - 1)
            self.dotpad.set_dot(x + 1, y - 1)
            self.dotpad.set_dot(x - 1, y + 1)
            self.dotpad.set_dot(x + 1, y + 1)

    def draw_harvest_crop(self, obj):
        x, y = int(obj["x"]), int(obj["y"])
        for dx, dy in [(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)]:
            self.dotpad.set_dot(x + dx, y + dy)

    def draw_recipe(self, obj):
        self.draw_catalog_item(obj, "food", obj.get("recipe_id"))

    def draw_ingredient(self, obj):
        x, y = int(obj["x"]), int(obj["y"])
        self.dotpad.draw_box(x, y, obj.get("width", 12), obj.get("height", 9))
        if not obj.get("selected"):
            self.draw_category(x, y, obj.get("item_kind", "crop"))
        if obj.get("selected"):
            self.dotpad.draw_line(x - 3, y + 1, x - 1, y + 3)
            self.dotpad.draw_line(x - 1, y + 3, x + 3, y - 2)

    def draw_cooking_start(self, obj):
        x, y = int(obj["x"]), int(obj["y"])
        self.dotpad.draw_box(x, y, obj.get("width", 18), obj.get("height", 7))
        self.dotpad.draw_line(x - 3, y, x + 3, y)
        self.dotpad.draw_line(x, y - 2, x, y + 2)

    def cooking_resume_point(self):
        if not self.cooking_resume_marker or not self.cooking_path_samples:
            return None
        return self.cooking_path_samples[min(self.cooking_progress_index, len(self.cooking_path_samples) - 1)]

    def defer_visual_completion(self, kind, visible_until):
        deadline = max(visible_until.values(), default=0)
        if time.monotonic() >= deadline:
            return False
        self.pending_visual_completion = (deadline, kind)
        return True

    def visual_tick(self):
        if self.current_page == "load_game": return self.response()
        if self.sleep_until is not None:
            if time.monotonic() >= self.sleep_until:
                return self.finish_sleep()
            return self.response()
        # Browser polling keeps physical output current even without movement.
        if not self.paused and self.pending_visual_completion:
            deadline, kind = self.pending_visual_completion
            if time.monotonic() >= deadline:
                self.pending_visual_completion = None
                if kind == "care":
                    return self.finish_care_minigame()
                return self.complete_cooking_step()
        return self.response()

    def update_cooking_marker(self):
        if (self.current_page == "cooking" and not self.paused and self.cooking_dragging
                and self.cooking_last_progress_at is not None
                and time.monotonic() - self.cooking_last_progress_at >= self.resume_marker_delay_seconds
                and not self.cooking_resume_marker):
            self.cooking_resume_marker = True
            self.render()

    def draw_cooking_path(self):
        # Progress is the index of the next checkpoint to visit.
        # Render only unvisited samples; scoring still uses the full path.
        samples = self.cooking_path_samples
        if not samples:
            return
        progress = max(0, min(self.cooking_progress_index, len(samples)))
        visible_progress = next((i for i in range(progress)
                                 if self.cooking_visible_until.get(i, 0) > time.monotonic()), progress)
        remaining = samples[visible_progress:]
        if not remaining:
            return
        for start, end in zip(remaining, remaining[1:]):
            self.dotpad.draw_line(
                round(start[0]), round(start[1]),
                round(end[0]), round(end[1])
            )
        if visible_progress == 0:
            sx, sy = samples[0]
            self.draw_filled_square(sx, sy)
        resume = self.cooking_resume_point()
        if resume is not None:
            self.draw_filled_square(*resume)

    def draw_shop_npc(self, obj):
        self.draw_facility(obj)

    def draw_shop_choice(self, obj):
        x, y = int(obj["x"]), int(obj["y"])
        self.dotpad.draw_box(x, y, obj.get("width", 28), obj.get("height", 34))
        glyph = (["01111","10000","10000","01110","00001","00001","11110"]
                 if obj.get("choice") == "sell" else
                 ["11110","10001","10001","11110","10001","10001","11110"])
        self.draw_icon_pattern(x,y,glyph)

    def draw_shop_item(self, obj):
        self.draw_catalog_item(obj, obj.get("shop_kind"), obj.get("item_id"))

    def point_to_segment_distance(self, px, py, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        nx, ny = x1 + t * dx, y1 + t * dy
        return ((px - nx) ** 2 + (py - ny) ** 2) ** 0.5

    def object_contains(self, obj, x, y):
        if obj.get("type") == "mine_rock":
            left, top = obj["x"] - obj["width"] // 2, obj["y"] - obj["height"] // 2
            return left <= x < left + obj["width"] and top <= y < top + obj["height"]
        if obj.get("type") == "route":
            distance = self.point_to_segment_distance(x, y, obj["x1"], obj["y1"], obj["x2"], obj["y2"])
            return distance <= float(obj.get("hit_radius", 3.0))
        half_width = obj.get("hit_width", obj.get("width", 8)) / 2
        half_height = obj.get("hit_height", obj.get("height", 8)) / 2
        return abs(x - obj["x"]) <= half_width and abs(y - obj["y"]) <= half_height

    def find_object(self, x, y):
        objects = self.get_objects()
        priority_types = ("care_target", "harvest_crop", "care_button", "growth_gauge", "plot", "seed", "ingredient", "recipe", "shop_item", "research", "node", "plot_detail_field")
        for obj_type in priority_types:
            for obj in objects:
                if obj.get("type") == obj_type and self.object_contains(obj, x, y):
                    return obj
        for obj in objects:
            if obj.get("type") != "route" and self.object_contains(obj, x, y):
                return obj
        for obj in objects:
            if obj.get("type") == "route" and self.object_contains(obj, x, y):
                return obj
        return None

    def find_farm_plot_at(self, x, y):
        for obj in self.get_objects():
            if obj.get("type") == "plot" and self.object_contains(obj, x, y):
                return obj
        return None

    def get_object_tts(self, obj):
        kind, label = obj.get("type"), obj.get("label", "")
        if kind == "plot":
            return self.plot_status_text(obj["id"])
        if kind == "plot_detail_field":
            return self.plot_status_text(self.detail_plot_id)
        if kind == "arrow":
            return label
        if kind == "bed":
            return "Bed. Sleep until morning."
        if kind == "chest":
            return "Research. Choose an upgrade."
        if kind == "stove":
            count = sum(self.can_craft_recipe(r) for r in self.config.get("recipes", {}))
            return f"Kitchen. Available recipes: {count} "
        if kind == "shop_npc":
            return "Shop. Buy or sell."
        if kind == "care_button":
            mode = obj.get("care_kind")
            state = self.farm_plots.get(self.detail_plot_id, {})
            if mode == "water":
                return "Watered" if state.get("watered") else f"Water. Move."
            if mode == "fertilizer":
                count = self.resources.get("fertilizer", 0)
                if state.get("fertilized"):
                    return "Fertilized"
                return f"Fertilizer {count}. Water first. Growth bonus: {self.config.get('fertilizer', {}).get('growth_day_bonus', 1)} days." if count else "No fertilizer. Buy at the shop."
            return label
        return obj.get("tts") or label

    def get_hover_sfx(self, obj):
        if obj.get("hover_sfx"):
            return obj["hover_sfx"]
        mapping = {
            "bed": "hover_bed", "chest": "hover_chest", "stove": "hover_stove",
            "plot": "hover_plot", "node": "hover_node", "route": "hover_route",
            "watering_can": "hover_water_tool", "fertilizer": "hover_fertilizer",
            "seed": "hover_seed", "resource": "hover_resource", "research": "hover_research",
            "harvest_crop": "hover_harvest_crop", "harvest_field": "hover_plot", "arrow": "hover_navigation",
            "recipe": "hover_recipe", "ingredient": "hover_ingredient", "cooking_start": "hover_cooking",
            "shop_npc": "hover_shop", "shop_choice": "hover_shop", "shop_item": "hover_shop_item",
            "plot_detail_field": "hover_plot", "growth_gauge": "hover_plot", "care_button": "hover_tool", "care_field": "hover_plot",
            "care_target": "hover_tool"
        }
        return mapping.get(obj.get("type"), "hover_object")

    def move_minigame(self, x, y):
        """Follow the pointer independently of the physical press state."""
        if self.paused or self.day_ended or self.sleep_until is not None or self.pending_visual_completion:
            self.last_pointer=(x,y)
            return self.response()
        px,py=self.last_pointer
        self.last_pointer=(x,y)
        if px is None or py is None: px,py=x,y
        if self.current_page=='cooking':
            if not self.cooking_dragging:
                if not self.cooking_path_samples:return self.response()
                index=min(self.cooking_progress_index,len(self.cooking_path_samples)-1)
                sx,sy=self.cooking_path_samples[index]
                tolerance=float(self.get_cooking_gesture().get('tolerance',4.5))*1.35
                if math.hypot(x-sx,y-sy)>tolerance:return self.response()
                return self.start_cooking_trace(x,y)
            return self.advance_cooking_trace(px,py,x,y)
        care=self.current_page in ('water_minigame','fertilizer_minigame')
        if care:
            self.care_dragging=True
            before=len(self.care_collected_ids)
            self.collect_care_segment(px,py,x,y)
            gained=len(self.care_collected_ids)-before
            complete=bool(self.care_targets) and len(self.care_collected_ids)/len(self.care_targets)>=float(self.config.get('care_minigame',{}).get('success_ratio',0.65))
        else:
            self.harvest_dragging=True
            before=len(self.harvest_collected_ids)
            self.collect_harvest_segment(px,py,x,y)
            gained=len(self.harvest_collected_ids)-before
            complete=bool(self.harvest_targets) and len(self.harvest_collected_ids)==len(self.harvest_targets)
        if complete:
            result=self.finish_care_minigame() if care else self.finish_harvest_minigame()
        else:
            if gained:self.render()
            result=self.response(sfx=('care_spray' if care else 'harvest_collect') if gained else None)
        if gained:result.setdefault('sound_events',[]).append({'kind':'correct','count':gained})
        return result

    def pointer_move(self, x, y):
        if self.current_page in ('water_minigame','fertilizer_minigame','harvest','cooking'):
            return self.move_minigame(x,y)
        if self.sleep_until is not None:
            return self.response()
        self.last_pointer = (x, y)
        if self.paused:
            return self.response()
        if self.current_page in ("mine", "fishing") and self.pointer_pressed:
            return self.response()
        if self.current_page in ("cooking", "fishing"):
            return self.response()
        obj = self.find_object(x, y)
        if obj is None:
            self.clear_hover()
            return self.response()
        object_id = obj["id"]
        if object_id != self.hover_object_id:
            self.hover_object_id = object_id
            return self.response(tts=self.get_object_tts(obj), sfx=self.get_hover_sfx(obj))
        return self.response()

    def pointer_down(self, x, y):
        if self.current_page in ('water_minigame','fertilizer_minigame','harvest','cooking'):
            return self.move_minigame(x,y)
        if self.sleep_until is not None:
            return self.response()
        if self.pending_visual_completion:
            return self.response()
        if self.current_page in ("mine", "fishing") and self.pointer_pressed:
            return self.response()
        self.pointer_pressed = True
        self.last_pointer = (x, y)
        if self.paused:
            return self.response()

        if self.current_page == "fishing":
            return self.cast_fishing(x, y)

        if self.current_page in ("water_minigame", "fertilizer_minigame"):
            self.care_dragging = True
            before = len(self.care_collected_ids)
            collected = self.collect_care_point(x, y)
            if collected:
                self.render()
                return self.response(sfx="care_spray", sound_events=[{"kind": "correct", "count": len(self.care_collected_ids) - before}])
            mode_label = "Water " if self.care_mode == "water" else " fertilizer "
            return self.response(tts=f"{mode_label}. Move over targets.", sfx="tool_pickup")

        if self.current_page == "harvest":
            self.harvest_dragging = True
            before = len(self.harvest_collected_ids)
            collected = self.collect_harvest_point(x, y)
            if collected:
                self.render()
                return self.response(sfx="harvest_collect", sound_events=[{"kind": "correct", "count": len(self.harvest_collected_ids) - before}])
            return self.response(tts="Harvest. Move over crops.", sfx="tool_pickup")

        if self.current_page == "cooking":
            return self.start_cooking_trace(x, y)

        obj = self.find_object(x, y)
        if obj is None:
            return self.response()
        action = obj.get("action", "")

        if action.startswith("drag_tool:"):
            if self.day_ended:
                return self.night_only_response()
            self.drag_tool = action.split(":", 1)[1]
            self.drag_target_ids.clear()
            if self.drag_tool == "water":
                return self.response(tts="Watering can. Drag to a plot.", sfx="tool_pickup")
            if self.drag_tool == "fertilizer":
                count = int(self.resources.get("fertilizer", 0))
                if count <= 0:
                    self.drag_tool = None
                    return self.response(tts="No fertilizer.", sfx="error")
                return self.response(tts=f"Fertilizer. Stock: {count}. Drag to a watered plot.", sfx="tool_pickup")

        return self.perform_action(action, obj)

    def pointer_drag(self, x, y):
        if self.current_page in ('water_minigame','fertilizer_minigame','harvest','cooking'):
            return self.move_minigame(x,y)
        if self.sleep_until is not None:
            return self.response()
        if self.pending_visual_completion:
            return self.response()
        previous_x, previous_y = self.last_pointer
        self.last_pointer = (x, y)
        if self.paused:
            return self.response()

        if self.current_page in ("water_minigame", "fertilizer_minigame") and self.care_dragging:
            if previous_x is None or previous_y is None:
                previous_x, previous_y = x, y
            before = len(self.care_collected_ids)
            collected = self.collect_care_segment(previous_x, previous_y, x, y)
            if collected:
                self.render()
                return self.response(sfx="care_spray", sound_events=[{"kind": "correct", "count": len(self.care_collected_ids) - before}])
            return self.response()

        if self.current_page == "harvest" and self.harvest_dragging:
            if previous_x is None or previous_y is None:
                previous_x, previous_y = x, y
            before = len(self.harvest_collected_ids)
            collected = self.collect_harvest_segment(previous_x, previous_y, x, y)
            if collected:
                self.render()
                return self.response(sfx="harvest_collect", sound_events=[{"kind": "correct", "count": len(self.harvest_collected_ids) - before}])
            return self.response()

        if self.current_page == "cooking" and self.cooking_dragging:
            if previous_x is None or previous_y is None:
                previous_x, previous_y = x, y
            return self.advance_cooking_trace(previous_x, previous_y, x, y)

        if self.drag_tool is None:
            return self.pointer_move(x, y)

        plot = self.find_farm_plot_at(x, y)
        if plot is None:
            return self.response()
        plot_id = plot["id"]
        if plot_id in self.drag_target_ids:
            return self.response()
        self.drag_target_ids.add(plot_id)
        if self.drag_tool == "water":
            return self.water_plot(plot_id)
        if self.drag_tool == "fertilizer":
            return self.fertilize_plot(plot_id)
        return self.response()

    def pointer_up(self, x, y):
        if self.current_page in ('water_minigame','fertilizer_minigame','harvest','cooking'):
            self.pointer_pressed=False
            return self.response()
        if self.sleep_until is not None:
            return self.response()
        if self.paused:
            self.pointer_pressed = False
            self.care_dragging = self.harvest_dragging = self.cooking_dragging = False
            self.drag_tool = None
            return self.response()
        final = self.pointer_drag(x, y) if self.pointer_pressed else None
        self.pointer_pressed = False
        self.last_pointer = (x, y)
        if final and (final.get("sfx") in ("cooking_success", "cooking_step", "cooking_wait", "day_end")):
            final["state"] = self.get_state()
            return final
        if self.current_page in ("water_minigame", "fertilizer_minigame") and self.care_dragging:
            self.care_dragging = False
            result = self.finish_care_minigame()
        elif self.current_page == "harvest" and self.harvest_dragging:
            self.harvest_dragging = False
            result = self.finish_harvest_minigame()
        elif self.current_page == "cooking" and self.cooking_dragging:
            self.cooking_dragging = False
            result = self.fail_or_continue_cooking()
        else:
            self.drag_tool = None
            self.drag_target_ids.clear()
            result = self.response()
        if final:
            result["sound_events"] = final.get("sound_events", []) + result.get("sound_events", [])
        return result

    def perform_action(self, action, obj):
        before = (self.current_page, self.current_location, self.inventory_page, self.shop_page)
        result = self._perform_action(action, obj)
        after = (self.current_page, self.current_location, self.inventory_page, self.shop_page)
        if obj.get("type") == "arrow" and before != after:
            result.setdefault("sound_events", []).append({"kind": "one_shot", "sound": "step"})
        return result

    def _perform_action(self, action, obj):
        if action == 'talk_rowan': return self.talk_rowan()
        if action == 'repeat_rowan': return self.response(tts='Rowan. '+self.rowan_dialogue)
        if action.startswith('rowan_submit:'): return self.submit_rowan_crop(action.split(':',1)[1])
        if action == 'open_calendar': return self.open_calendar()
        if action.startswith('calendar_day:'): return self.response(tts=self.calendar_text(int(action.split(':')[1])))
        if action == "close_load": return self.close_load_game()
        if action.startswith("load_slot:"): return self.load_game(action.split(":", 1)[1])
        if self.day_ended and action != "rest":
            return self.night_only_response()
        if action.startswith("mine_hit:"):
            return self.hit_mine_rock(action.split(":", 1)[1])
        if action.startswith("shop_page:"):
            if self.current_page not in ("shop_buy", "shop_sell"):
                return self.response()
            self.shop_page += int(action.split(":", 1)[1])
            self.clear_hover()
            self.render()
            return self.response(tts="Next page" if action.endswith(":1") else "Previous page")
        if action.startswith("inventory_page:"):
            if self.current_page != "inventory":
                return self.response()
            delta = int(action.split(":", 1)[1])
            self.get_inventory_objects()
            self.inventory_page = max(0, min(self.inventory_page + delta, self.inventory_page_count - 1))
            self.clear_hover()
            self.render()
            return self.response(tts="Next page" if delta > 0 else "Previous page", sfx="open_page")
        if action.startswith("travel:"):
            return self.travel_to(action.split(":", 1)[1])
        if action == "return_scene":
            return self.return_to_scene()
        if action == "open_research":
            return self.open_research()
        if action == "open_recipes":
            return self.open_recipes()
        if action == "return_shop_choice":
            return self.return_to_shop_choice()
        if action == "open_shop":
            return self.open_shop()
        if action.startswith("shop_mode:"):
            return self.open_shop_mode(action.split(":", 1)[1])
        if action.startswith("buy:"):
            _, kind, item_id = action.split(":", 2)
            return self.buy_shop_item(kind, item_id)
        if action.startswith("sell:"):
            _, kind, item_id = action.split(":", 2)
            return self.sell_shop_item(kind, item_id)
        if action.startswith("open_plot_detail:"):
            return self.open_plot_detail(action.split(":", 1)[1])
        if action.startswith("start_care:"):
            _, mode, plot_id = action.split(":", 2)
            return self.start_care_minigame(plot_id, mode)
        if action.startswith("open_seed_select:"):
            return self.open_seed_select(action.split(":", 1)[1])
        if action.startswith("plant:"):
            _, plot_id, seed_id = action.split(":", 2)
            return self.plant_seed(plot_id, seed_id)
        if action.startswith("start_harvest:"):
            return self.start_harvest_minigame(action.split(":", 1)[1])
        if action.startswith("research:"):
            return self.buy_research(action.split(":", 1)[1])
        if action.startswith("select_recipe:"):
            return self.select_recipe(action.split(":", 1)[1])
        if action.startswith("toggle_ingredient:"):
            return self.toggle_ingredient(action.split(":", 1)[1])
        if action == "start_cooking":
            return self.open_cooking_minigame()
        if action.startswith("use_food:"):
            return self.use_food(action.split(":", 1)[1])
        if action.startswith("inspect:"):
            return self.response(tts=self.get_object_tts(obj))
        if action == "rest":
            return self.next_day()
        return self.response(tts=self.get_object_tts(obj))

    def night_only_response(self):
        return self.response(tts="Night. Select the bed.", sfx="error")

    def travel_to(self, location):
        if self.day_ended:
            return self.night_only_response()
        if location not in ("home", "farm", "town", "mine", "fishing"):
            return self.response(tts="Location unavailable.")
        self._menu_stack.clear()
        self.rowan_dialogue = ""
        self.rowan_submit_open = False
        changed = location != self.current_location
        self.current_location = location
        self.current_page = location
        self.seed_select_plot_id = None
        self.clear_care()
        self.clear_harvest()
        self.clear_cooking()
        self.clear_hover()
        if changed:
            result = self.consume_time("travel")
            if result["night"]:
                return self.night_response()
        self.render()
        name = self.get_page_name(location)
        particle = self.ro_particle(name)
        if location == "fishing":
            text = "Fishing lake. Follow the water sound. Tap to fish." if self.resources.get("fishing_rod") else "Fishing lake. Buy a fishing rod to catch fish."
            return self.response(tts=text, sfx="travel")
        if location == "mine":
            text = "Mine. Tap rocks to break them." if self.resources["pickaxe"] else "Mine. Buy a pickaxe to break rocks."
            return self.response(tts=text, sfx="travel")
        if location == 'town' and not self.rowan_greeted:
            self.rowan_greeted=True
            return self.response(tts='Village. Rowan would like to meet you. Select Rowan beside the shop to hear more.',sfx='travel')
        return self.response(tts=f"{name}", sfx="travel")

    def open_minimap(self):
        if self.day_ended:
            return self.night_only_response()
        self.current_page = "minimap"
        self.seed_select_plot_id = None
        self.clear_care()
        self.clear_harvest()
        self.clear_cooking()
        self.clear_hover()
        self.render()
        return self.response(tts="Map. Select a place.", sfx="open_page")

    def open_inventory(self):
        if self.day_ended:
            return self.night_only_response()
        self.inventory_page = 0
        self.current_page = "inventory"
        self.seed_select_plot_id = None
        self.clear_care()
        self.clear_harvest()
        self.clear_cooking()
        self.clear_hover()
        self.render()
        return self.response(tts=f"Inventory. {self.resources['coin']} gold. {self.buff_text()}", sfx="open_page")

    def open_research(self):
        if self.day_ended:
            return self.night_only_response()
        self.current_page = "research"
        self.clear_hover()
        self.render()
        return self.response(tts="Research.", sfx="open_page")

    def navigate_key(self, direction):
        if self.current_page == 'inventory':
            if self.paused: return self.response(tts='Resume first.')
            self.get_inventory_objects()
            delta = -1 if direction=='left' else 1
            if not 0 <= self.inventory_page+delta < self.inventory_page_count:
                return self.response(tts='First page.' if delta<0 else 'Last page.')
            return self._perform_action(f'inventory_page:{delta}', {})
        # Function-key panels close with either physical navigation button.
        if self.current_page in ('minimap', 'load_game'):
            if self.paused: return self.response(tts='Resume first.')
            if self.sleep_until is not None: return self.response(tts='Sleeping. Please wait.')
            if self.current_page == 'load_game': return self.close_load_game()
            self._menu_stack.clear()
            return self.return_to_scene()
        return super().navigate_key(direction)

    def return_to_scene(self):
        self.pointer_pressed = False
        self.current_page = "home" if self.day_ended else self.current_location
        self.seed_select_plot_id = None
        self.drag_tool = None
        self.drag_target_ids.clear()
        self.clear_care()
        self.clear_harvest()
        self.clear_cooking()
        self.clear_hover()
        self.render()
        return self.response(tts=f"{self.get_page_name(self.current_location)}.", sfx="open_page")

    def plot_status_text(self, plot_id):
        state = self.farm_plots.get(plot_id)
        if state is None:
            return "Plot unavailable."
        label = self.get_plot_label(plot_id)
        if not state.get("seed_id"):
            return f"{label}. Empty. Plant seeds."
        seed = self.get_seed_label(state["seed_id"])
        if state["mature"]:
            return f"{label}, {seed}. Ready to harvest"
        needed = int(self.get_seed_config(state["seed_id"]).get("growth_days", 3))
        water = "Watered" if state["watered"] else "Needs water"
        fertilizer = "Fertilized" if state["fertilized"] else "Not fertilized"
        return f"{label}, {seed}. Growth {state['growth']} of {needed} days. {water}. {fertilizer}"

    def open_plot_detail(self, plot_id):
        unlocked = {p["id"] for p in self.get_unlocked_plot_defs()}
        state = self.farm_plots.get(plot_id)
        if state is None or plot_id not in unlocked:
            return self.response(tts="Plot unavailable.", sfx="error")
        self.detail_plot_id = plot_id
        self.current_location = "farm"
        self.current_page = "plot_detail"
        self.clear_care(keep_detail=True)
        self.clear_harvest()
        self.clear_hover()
        self.render()
        text = self.plot_status_text(plot_id)
        return self.response(tts=text, sfx="open_page")

    def start_care_minigame(self, plot_id, mode):
        self.last_pointer = (None, None)
        state = self.farm_plots.get(plot_id)
        if state is None or state.get("seed_id") is None:
            return self.response(tts="Plant seeds first.", sfx="error")
        if state.get("mature"):
            return self.response(tts="Crop ready. Harvest now.", sfx="error")
        if mode == "water" and state.get("watered"):
            return self.response(tts="Already watered.", sfx="error")
        if mode == "fertilizer":
            if not state.get("watered"):
                return self.response(tts="Water first.", sfx="error")
            if state.get("fertilized"):
                return self.response(tts="Already fertilized.", sfx="error")
            if int(self.resources.get("fertilizer", 0)) <= 0:
                return self.response(tts="No fertilizer. Buy at the shop.", sfx="error")

        cfg = self.config.get("care_minigame", {})
        positions = [tuple(v) for v in cfg.get("target_positions", [])]
        target_count = min(int(cfg.get("target_count", 8)), len(positions))
        selected = random.sample(positions, target_count) if target_count else []
        self.detail_plot_id = plot_id
        self.care_mode = mode
        self.care_targets = [
            {"id": f"care_target_{i}", "x": x, "y": y}
            for i, (x, y) in enumerate(selected)
        ]
        self.care_collected_ids.clear()
        self.care_visible_until = {}
        self.care_dragging = False
        self.current_page = "water_minigame" if mode == "water" else "fertilizer_minigame"
        self.clear_hover()
        self.render()
        mode_label = "Water" if mode == "water" else "Fertilize"
        return self.response(
            tts=f"{mode_label}. Move over targets.",
            sfx="care_start"
        )

    def collect_care_point(self, x, y):
        collected = False
        tolerance = float(self.config.get("care_minigame", {}).get("tolerance", 4.0))
        for target in self.care_targets:
            if target["id"] not in self.care_collected_ids and math.hypot(x - target["x"], y - target["y"]) <= tolerance:
                self.care_collected_ids.add(target["id"])
                self.care_visible_until[target["id"]] = time.monotonic() + self.disappear_delay_seconds
                collected = True
        return collected

    def collect_care_segment(self, x1, y1, x2, y2):
        collected = False
        tolerance = float(self.config.get("care_minigame", {}).get("tolerance", 4.0))
        for target in self.care_targets:
            if target["id"] in self.care_collected_ids:
                continue
            if self.point_to_segment_distance(target["x"], target["y"], x1, y1, x2, y2) <= tolerance:
                self.care_collected_ids.add(target["id"])
                self.care_visible_until[target["id"]] = time.monotonic() + self.disappear_delay_seconds
                collected = True
        return collected

    def finish_care_minigame(self):
        if self.detail_plot_id is None or not self.care_targets:
            self.clear_care()
            return self.return_to_scene()
        total = len(self.care_targets)
        collected = len(self.care_collected_ids)
        ratio = collected / total if total else 0.0
        success_ratio = float(self.config.get("care_minigame", {}).get("success_ratio", 0.65))
        percent = int(round(ratio * 100))
        mode = self.care_mode
        plot_id = self.detail_plot_id

        if ratio < success_ratio:
            self.render()
            mode_label = "Water" if mode == "water" else "Fertilizer"
            return self.response(
                tts=f"{mode_label} {percent} percent. Continue over remaining targets.",
                sfx="error"
            )

        if self.defer_visual_completion("care", self.care_visible_until):
            return self.response()

        state = self.farm_plots[plot_id]
        if mode == "water":
            state["watered"] = True
            action_name = "water"
            text = f"Watered. Sleep to grow crops."
            sfx = "water"
        else:
            count = int(self.resources.get("fertilizer", 0))
            if count <= 0:
                self.clear_care(keep_detail=True)
                self.current_page = "plot_detail"
                self.render()
                return self.response(tts="No fertilizer. Buy at the shop.", sfx="error")
            self.resources["fertilizer"] = count - 1
            fertilizer_text = self.apply_fertilizer_bonus(state)
            action_name = "fertilize"
            text = f"Fertilized. {fertilizer_text}.  fertilizer {self.resources['fertilizer']} remaining"
            sfx = "fertilize"

        self.clear_care(keep_detail=True)
        self.current_page = "plot_detail"
        self.clear_hover()
        result = self.consume_time(action_name)
        if result["night"]:
            return self.night_response(text)
        self.render()
        return self.response(tts=text, sfx=sfx)

    def open_seed_select(self, plot_id):
        if self.day_ended:
            return self.night_only_response()
        state = self.farm_plots.get(plot_id)
        unlocked = [p["id"] for p in self.get_unlocked_plot_defs()]
        if state is None or plot_id not in unlocked:
            return self.response(tts="Plot unavailable.", sfx="error")
        if state["seed_id"] is not None:
            return self.response(tts="Plot occupied.")
        available = [f"{self.get_seed_label(seed_id)} {count} " for seed_id, count in self.resources["seeds"].items() if int(count) > 0]
        if not available:
            return self.response(tts="No seeds. Buy at the shop.", sfx="error")
        self.seed_select_plot_id = plot_id
        self.current_page = "seed_select"
        self.clear_hover()
        self.render()
        return self.response(tts="Choose seeds. " + ", ".join(available), sfx="open_page")

    def plant_seed(self, plot_id, seed_id):
        state = self.farm_plots.get(plot_id)
        seed_config = self.get_seed_config(seed_id)
        if state is None or not seed_config:
            return self.response(tts="Cannot plant here.", sfx="error")
        if state["seed_id"] is not None:
            return self.response(tts="Plot occupied.", sfx="error")
        count = int(self.resources["seeds"].get(seed_id, 0))
        if count <= 0:
            return self.response(tts="No seeds of this type.", sfx="error")
        self.resources["seeds"][seed_id] = count - 1
        self.farm_plots[plot_id] = self.new_plot_state()
        self.farm_plots[plot_id]["seed_id"] = seed_id
        self.detail_plot_id = plot_id
        self.current_page = "plot_detail"
        self.current_location = "farm"
        self.seed_select_plot_id = None
        self.clear_hover()
        result = self.consume_time("plant")
        if result["night"]:
            return self.night_response(f"{self.get_seed_label(seed_id)} planted.")
        self.render()
        return self.response(tts=f"{self.get_seed_label(seed_id)} planted. Water, then sleep.", sfx="plant")

    def water_plot(self, plot_id):
        state = self.farm_plots.get(plot_id)
        if state is None:
            return self.response()
        label = self.get_plot_label(plot_id)
        if state["seed_id"] is None:
            return self.response(tts=f"{label} is empty. Plant seeds first.", sfx="error")
        if state["mature"]:
            return self.response(tts=f"{label} is ready to harvest.", sfx="error")
        if state["watered"]:
            return self.response(tts=f"{label} Already watered.", sfx="error")
        state["watered"] = True
        result = self.consume_time("water")
        if result["night"]:
            return self.night_response(f"{label} watered")
        self.render()
        return self.response(tts=f"{label} watered. {self.get_seed_label(state['seed_id'])} will grow after sleep.", sfx="water")

    def apply_fertilizer_bonus(self, state):
        """Apply the saved growth days now; sleep must not apply them twice."""
        needed = int(self.get_seed_config(state["seed_id"]).get("growth_days", 3))
        bonus = max(0, int(self.config.get("fertilizer", {}).get("growth_day_bonus", 1)))
        before = state["growth"]
        state["growth"] = min(needed, before + bonus)
        state["fertilized"] = True
        state["mature"] = state["growth"] >= needed
        saved = state["growth"] - before
        remaining = max(0, needed - state["growth"])
        status = "Ready to harvest" if state["mature"] else f"Water, then sleep {remaining} more days to harvest."
        return f"Harvest {saved} days sooner. {status}"

    def fertilize_plot(self, plot_id):
        state = self.farm_plots.get(plot_id)
        if state is None:
            return self.response()
        label = self.get_plot_label(plot_id)
        if state["seed_id"] is None:
            return self.response(tts=f"{label} is empty. Plant first.", sfx="error")
        if state["mature"]:
            return self.response(tts=f"{label} is ready to harvest.", sfx="error")
        if not state["watered"]:
            return self.response(tts=f"{label} needs water first.", sfx="error")
        if state["fertilized"]:
            return self.response(tts=f"{label} is already fertilized.", sfx="error")
        count = int(self.resources.get("fertilizer", 0))
        if count <= 0:
            return self.response(tts="No fertilizer. Buy at the shop.", sfx="error")
        self.resources["fertilizer"] = count - 1
        fertilizer_text = self.apply_fertilizer_bonus(state)
        result = self.consume_time("fertilize")
        if result["night"]:
            return self.night_response(f"{label} fertilized.")
        self.render()
        return self.response(tts=f"{label} fertilized. {fertilizer_text}.  fertilizer {self.resources.get('fertilizer', 0)} remaining", sfx="fertilize")

    def get_effective_seed_return_chance(self, seed_id):
        cfg = self.config.get("research", {}).get("seed_return", {})
        level = int(self.research_levels.get("seed_return", 0))
        chances = cfg.get("return_chances", [0.3, 0.6])
        chance = chances[min(level - 1, len(chances) - 1)] if level > 0 else self.get_seed_config(seed_id).get("seed_return_chance", 0.0)
        return min(1.0, max(0.0, float(chance)))

    def buy_research(self, research_kind):
        if research_kind == "mineral_luck":
            return self.buy_mineral_research(research_kind)
        if research_kind == "seed_return":
            cfg = self.config.get("research", {}).get("seed_return", {})
            level = int(self.research_levels.get("seed_return", 0))
            max_level = int(cfg.get("max_level", 2))
            costs = list(cfg.get("costs", []))
            if level >= max_level:
                return self.response(tts="Seed recovery at maximum level.", sfx="error")
            cost = int(costs[level]) if level < len(costs) else 999999
            copper_cost = int(cfg.get("copper_costs", [3, 6])[level])
            if self.resources["copper"] < copper_cost:
                return self.response(tts=f"Copper {copper_cost} required", sfx="error")
            if int(self.resources.get("coin", 0)) < cost:
                return self.response(tts=f"Not enough gold. Need {cost}.", sfx="error")
            self.resources["coin"] -= cost
            self.resources["copper"] -= copper_cost
            self.research_levels["seed_return"] = level + 1
            result = self.consume_time("research")
            text = f"Seed recovery level {level + 1}. Gold spent: {cost}."
            if result["night"]:
                return self.night_response(text, sound_events=[{"kind": "one_shot", "sound": "coin"}] if cost > 0 else [])
            self.render()
            return self.response(tts=text, sfx="research", sound_events=[{"kind": "one_shot", "sound": "coin"}] if cost > 0 else [])

        if research_kind == "field_expand":
            cfg = self.config.get("research", {}).get("field_expansion", {})
            plots = self.config.get("farm", {}).get("plots", [])
            initial = int(cfg.get("initial_plot_count", 2))
            costs = list(cfg.get("costs", []))
            if self.unlocked_plot_count >= len(plots):
                return self.response(tts="All plots unlocked.", sfx="error")
            index = max(0, self.unlocked_plot_count - initial)
            cost = int(costs[index]) if index < len(costs) else 999999
            material_cost = int(cfg.get("stone_costs", [5, 10])[index])
            if self.resources["stone"] < material_cost:
                return self.response(tts=f"Stone {material_cost} required", sfx="error")
            if int(self.resources.get("coin", 0)) < cost:
                return self.response(tts=f"Not enough gold. Need {cost}.", sfx="error")
            self.resources["coin"] -= cost
            self.resources["stone"] -= material_cost
            self.unlocked_plot_count += 1
            result = self.consume_time("research")
            text = f"Farm expanded. Plots: {self.unlocked_plot_count}. Gold spent: {cost}."
            if result["night"]:
                return self.night_response(text, sound_events=[{"kind": "one_shot", "sound": "coin"}] if cost > 0 else [])
            self.render()
            return self.response(tts=text, sfx="research", sound_events=[{"kind": "one_shot", "sound": "coin"}] if cost > 0 else [])
        return self.response()

    def start_harvest_minigame(self, plot_id):
        state = self.farm_plots.get(plot_id)
        if state is None or not state["mature"]:
            return self.response(tts="Crop not ready.", sfx="error")
        cfg = self.config.get("harvest_minigame", {})
        positions = [tuple(v) for v in cfg.get("target_positions", [])]
        target_count = min(int(cfg.get("target_count", 6)), len(positions))
        selected = random.sample(positions, target_count)
        self.harvest_plot_id = plot_id
        self.harvest_targets = [{"id": f"harvest_target_{i}", "x": x, "y": y} for i, (x, y) in enumerate(selected)]
        self.harvest_collected_ids.clear()
        self.harvest_dragging = False
        self.last_pointer = (None, None)
        self.current_page = "harvest"
        self.clear_hover()
        self.render()
        return self.response(tts=f"{self.get_seed_label(state['seed_id'])} harvest. Collect all crops.", sfx="harvest_start")

    def collect_harvest_point(self, x, y):
        collected = False
        for target in self.harvest_targets:
            if target["id"] not in self.harvest_collected_ids and abs(x - target["x"]) <= 3.5 and abs(y - target["y"]) <= 3.5:
                self.harvest_collected_ids.add(target["id"])
                collected = True
        return collected

    def collect_harvest_segment(self, x1, y1, x2, y2):
        collected = False
        for target in self.harvest_targets:
            if target["id"] in self.harvest_collected_ids:
                continue
            if self.point_to_segment_distance(target["x"], target["y"], x1, y1, x2, y2) <= 3.5:
                self.harvest_collected_ids.add(target["id"])
                collected = True
        return collected

    def finish_harvest_minigame(self):
        if self.harvest_plot_id is None or not self.harvest_targets:
            self.clear_harvest()
            return self.return_to_scene()
        collected = len(self.harvest_collected_ids)
        total = len(self.harvest_targets)
        if collected < total:
            self.render()
            return self.response(tts=f"Harvest {collected}/{total}. Collect remaining crops.")

        plot_id = self.harvest_plot_id
        state = self.farm_plots[plot_id]
        seed_id = state["seed_id"]
        seed_config = self.get_seed_config(seed_id)
        seed_label = self.get_seed_label(seed_id)
        base_yield = self.get_harvest_base_yield(seed_id)
        buff_multiplier = self.buff_multiplier_for("harvest_multiplier")
        buff_applied = buff_multiplier > 1.0
        yield_count = self.loot_amount(max(1, int(math.ceil(base_yield * buff_multiplier))))
        self.resources["crops"][seed_id] = int(self.resources["crops"].get(seed_id, 0)) + yield_count

        chance = self.get_effective_seed_return_chance(seed_id)
        got_seed = random.random() < chance
        seed_count = self.loot_amount(1) if got_seed else 0
        if got_seed:
            self.resources["seeds"][seed_id] = int(self.resources["seeds"].get(seed_id, 0)) + seed_count

        self.farm_plots[plot_id] = self.new_plot_state()
        self.current_location = "farm"
        self.current_page = "farm"
        self.detail_plot_id = None
        self.clear_harvest()
        self.clear_hover()

        text = f"Harvested. {seed_label} {yield_count}."
        if buff_applied:
            text += ". Harvest boost applied."
        if got_seed:
            text += f". {seed_count} seeds recovered."
        else:
            text += ". No seed recovered."

        result = self.consume_time("harvest")
        if result["night"]:
            return self.night_response(text)
        self.render()
        return self.response(tts=text, sfx="harvest")

    def open_recipes(self):
        if self.day_ended:
            return self.night_only_response()
        craftable = [rid for rid,cfg in self.config.get("recipes", {}).items() if not cfg.get("hidden_recipe") and self.can_craft_recipe(rid)]
        self.selected_recipe_id = None
        self.selected_ingredients.clear()
        self.current_page = "recipe_select"
        self.clear_hover()
        self.render()
        if not craftable:
            return self.response(tts="No recipes available. Gather ingredients.", sfx="open_page")
        names = ", ".join(self.get_recipe_label(rid) for rid in craftable)
        return self.response(tts=f"Choose a recipe.", sfx="open_page")

    def select_recipe(self, recipe_id):
        if self.get_recipe_config(recipe_id).get("hidden_recipe") or not self.can_craft_recipe(recipe_id):
            return self.response(tts="Not enough ingredients.", sfx="error")
        self.selected_recipe_id = recipe_id
        self.selected_ingredients.clear()
        self.current_page = "ingredient_select"
        self.clear_hover()
        self.render()
        return self.response(tts=f"{self.get_recipe_label(recipe_id)}. {self.recipe_ingredient_text(recipe_id)}. Select all ingredients to start cooking.", sfx="open_page")

    def toggle_ingredient(self, seed_id):
        if self.current_page != "ingredient_select":
            return self.response()
        recipe = self.get_recipe_config(self.selected_recipe_id)
        if seed_id.startswith("fish:"): return self.toggle_fish(seed_id)
        if seed_id not in recipe.get("ingredients", {}):
            return self.response(tts="Ingredient not required.", sfx="error")
        if seed_id in self.selected_ingredients:
            self.selected_ingredients.remove(seed_id)
            text = f"{self.get_seed_label(seed_id)} deselected."
        else:
            self.selected_ingredients.add(seed_id)
            label = self.get_seed_label(seed_id)
            particle = self.josa(label, " ", " ")
            text = f"{label} selected."
        self.clear_hover()
        self.render()
        required = set(recipe.get("ingredients", {}).keys())
        if required and required.issubset(self.selected_ingredients) and (not recipe.get("seafood") or self.selected_fish()):
            self.pointer_pressed = False
            return self.open_cooking_minigame()
        return self.response(tts=text, sfx="ingredient_select")

    def get_cooking_steps(self):
        recipe = self.get_recipe_config(self.selected_recipe_id)
        steps = recipe.get("gesture_steps")
        steps = steps if steps else [recipe.get("gesture", {})]
        registry = self.config.get('cooking_methods', {}).get('gestures', {})
        return [copy.deepcopy(registry[step['method']]) if 'method' in step else step for step in steps]

    def get_scaled_cooking_gesture(self):
        steps = self.get_cooking_steps()
        gesture = steps[min(self.cooking_stage_index, len(steps) - 1)]
        path = gesture.get("path", [])
        if gesture.get("kind") != "stir" or len(path) < 2:
            return gesture
        # Enlarge both rendered path and hit-test samples, without editing recipes.
        xs, ys = [p[0] for p in path], [p[1] for p in path]
        span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
        if span_x <= 0 or span_y <= 0:
            return gesture
        width, height = self.config["dotpad"]["width"], self.config["dotpad"]["height"]
        scale = min(self.stir_scale, (width - 10) / span_x, (height - 10) / span_y)
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        return {**gesture, "path": [
            [round((x - cx) * scale + (width - 1) / 2),
             round((y - cy) * scale + (height - 1) / 2)] for x, y in path
        ]}

    def get_cooking_gesture(self):
        gesture = dict(self.get_scaled_cooking_gesture())
        path = [list(p) for p in gesture.get("path", [])]
        if not path: return gesture
        if not gesture.get("closed") and len(path) > 2 and math.dist(path[0], path[-1]) < 8:
            while len(path) > 2 and math.dist(path[0], path[-1]) < 8:
                path.pop()
        # Restore the configured full-field position. Keep the distinct filled
        # start marker and the opening between the start and end of closed paths.
        gesture["path"] = path
        return gesture

    def get_cooking_kind(self):
        return "stir" if self.get_cooking_gesture().get("kind") in ("stir", "grill", "fry") else "cut"

    def get_cooking_stage_label(self):
        return self.get_cooking_gesture().get("label") or ("Stir" if self.get_cooking_kind() == "stir" else "Chop")

    def cooking_step_text(self):
        label = self.get_cooking_stage_label()
        return f"Step {self.cooking_stage_index + 1}. {label}. Start at the filled square. Follow the line."

    def complete_cooking_step(self):
        self.cooking_dragging = False
        if self.defer_visual_completion("cooking", self.cooking_visible_until):
            return self.response(sfx="cooking_wait")
        if self.cooking_stage_index + 1 >= len(self.get_cooking_steps()):
            return self.finish_cooking_success()
        self.last_pointer = (None, None)
        self.cooking_stage_index += 1
        self.cooking_last_progress_at = None
        self.cooking_resume_marker = False
        self.cooking_progress_index = 0
        self.cooking_visible_until = {}
        self.cooking_path_samples = self.build_path_samples(self.get_cooking_gesture().get("path", []))
        self.clear_hover()
        self.render()
        return self.response(tts= self.cooking_step_text(), sfx="cooking_step")

    def open_cooking_minigame(self):
        recipe = self.get_recipe_config(self.selected_recipe_id)
        if not recipe:
            return self.response(tts="Choose a recipe first.", sfx="error")
        required = set(recipe.get("ingredients", {}).keys())
        if recipe.get("seafood") and not self.seafood_ready(recipe, selected=True):
            return self.response(tts="Choose one fish first.")
        if not required.issubset(self.selected_ingredients):
            return self.response(tts="Select all ingredients first.", sfx="error")
        if not self.can_craft_recipe(self.selected_recipe_id):
            return self.response(tts="Not enough ingredients.", sfx="error")
        self.last_pointer = (None, None)
        self.current_page = "cooking"
        self.cooking_dragging = False
        self.cooking_progress_index = 0
        self.cooking_stage_index = 0
        self.cooking_last_progress_at = None
        self.cooking_resume_marker = False
        self.cooking_visible_until = {}
        self.cooking_path_samples = self.build_path_samples(self.get_cooking_gesture().get("path", []))
        self.clear_hover()
        self.render()
        return self.response(tts=f"{self.get_recipe_label(self.selected_recipe_id)}. {self.cooking_step_text()}.", sfx="cooking_start")

    def build_path_samples(self, path, spacing=1.5):
        if len(path) < 2:
            return [tuple(path[0])] if path else []
        samples = [tuple(path[0])]
        for i in range(len(path) - 1):
            x1, y1 = path[i]
            x2, y2 = path[i + 1]
            length = math.hypot(x2 - x1, y2 - y1)
            steps = max(1, int(math.ceil(length / spacing)))
            for step in range(1, steps + 1):
                t = step / steps
                samples.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
        return samples

    def start_cooking_trace(self, x, y):
        if not self.cooking_path_samples:
            return self.response(tts="Cooking path unavailable.", sfx="error")
        recipe = self.get_recipe_config(self.selected_recipe_id)
        tolerance = float(self.get_cooking_gesture().get("tolerance", 4.5))
        resume_index = min(self.cooking_progress_index, len(self.cooking_path_samples) - 1)
        sx, sy = self.cooking_path_samples[resume_index]
        if math.hypot(x - sx, y - sy) > tolerance * 1.35:
            self.cooking_dragging = False
            return self.response(tts="Move to the filled square to continue.", sfx="error")
        self.cooking_dragging = True
        if self.cooking_progress_index == 0:
            self.cooking_visible_until[0] = time.monotonic() + self.disappear_delay_seconds
        self.cooking_progress_index = max(1, self.cooking_progress_index)
        self.cooking_last_progress_at = time.monotonic()
        self.cooking_resume_marker = False
        self.render()
        return self.response(sfx="tool_pickup", sound_events=[{"kind": "work_start", "sound": "cook" if self.get_cooking_kind() == "stir" else "cut"}])

    def advance_cooking_trace(self, x1, y1, x2, y2):
        if not self.cooking_path_samples:
            return self.response()
        recipe = self.get_recipe_config(self.selected_recipe_id)
        tolerance = float(self.get_cooking_gesture().get("tolerance", 4.5))
        if math.hypot(x2 - x1, y2 - y1) < 0.05:
            return self.response()
        before = self.cooking_progress_index
        advanced = False
        while self.cooking_progress_index < len(self.cooking_path_samples):
            px, py = self.cooking_path_samples[self.cooking_progress_index]
            if self.point_to_segment_distance(px, py, x1, y1, x2, y2) <= tolerance:
                self.cooking_visible_until[self.cooking_progress_index] = time.monotonic() + self.disappear_delay_seconds
                self.cooking_progress_index += 1
                advanced = True
            else:
                break
        if self.cooking_progress_index >= len(self.cooking_path_samples):
            gained = self.cooking_progress_index - before
            result = self.complete_cooking_step()
            result["sound_events"] = [{"kind": "correct", "activity": "cooking", "count": gained}]
            return result
        if advanced:
            self.cooking_last_progress_at = time.monotonic()
            self.cooking_resume_marker = False
            self.render()
            return self.response(sfx="cooking_trace", sound_events=[{"kind": "correct", "activity": "cooking", "count": self.cooking_progress_index - before}])
        return self.response()

    def fail_or_continue_cooking(self):
        total = len(self.cooking_path_samples)
        progress = self.cooking_progress_index
        percent = int(round((progress / total) * 100)) if total else 0
        self.cooking_resume_marker = progress > 0
        self.render()
        return self.response(tts=f"Progress {percent} percent.")

    def finish_cooking_success(self):
        recipe_id = self.selected_recipe_id
        recipe = self.get_recipe_config(recipe_id)
        if recipe.get("seafood"): return self.finish_seafood(recipe)
        if not recipe or not self.can_craft_recipe(recipe_id):
            self.clear_cooking()
            self.current_page = "home"
            self.current_location = "home"
            self.render()
            return self.response(tts="Not enough ingredients.", sfx="error")
        for seed_id, count in recipe.get("ingredients", {}).items():
            self.resources["crops"][seed_id] -= int(count)
        food_count = self.loot_amount(1)
        self.resources["foods"][recipe_id] = int(self.resources["foods"].get(recipe_id, 0)) + food_count
        label = self.get_recipe_label(recipe_id)
        self.current_location = "home"
        self.current_page = "home"
        self.clear_cooking()
        self.clear_hover()
        result = self.consume_time("cook")
        text = f"{label} {food_count} made." + (" Bonus." if food_count>1 else "")
        if result["night"]:
            return self.night_response(text)
        self.render()
        return self.response(tts=text, sfx="cooking_success")

    def use_food(self, recipe_id):
        count = int(self.resources["foods"].get(recipe_id, 0))
        recipe = self.get_recipe_config(recipe_id)
        if count <= 0 or not recipe:
            return self.response(tts="No food available.", sfx="error")
        self.resources["foods"][recipe_id] = count - 1
        self.active_buff = {
            "kind": recipe.get("buff_kind", "harvest_multiplier"),
            "source": recipe_id,
            "multiplier": float(recipe.get("buff_multiplier", 1.0)),
            "remaining_ticks": float(recipe.get("buff_ticks", 0)),
            "remaining_sales": int(recipe.get("sale_uses", 0)),
            "rare_weight_multiplier": float(recipe.get("rare_weight_multiplier", 1)),
            "double_chance": float(recipe.get("double_chance", 0))
        }
        self.clear_hover()
        self.render()
        return self.response(tts=f"{self.get_recipe_label(recipe_id)} used. {self.buff_text()}", sfx="eat_food")

    def open_shop(self):
        self.rowan_dialogue = ""
        self.rowan_submit_open = False
        if self.current_location != "town":
            self.current_location = "town"
        self.current_page = "shop_choice"
        self.clear_hover()
        self.render()
        return self.response(tts="Shop. Sell, buy, or check the calendar.", sfx="shop_open", sound_events=[{"kind": "one_shot", "sound": "door"}])

    def return_to_shop_choice(self):
        self.current_page = "shop_choice"
        self.shop_page = 0
        self.clear_hover()
        self.render()
        return self.response(tts="Shop. Sell, buy, or check the calendar.", sfx="open_page")

    def open_shop_mode(self, mode):
        self.shop_page = 0
        if mode == "sell":
            self.current_page = "shop_sell"
            text = "Sell items."
        else:
            self.current_page = "shop_buy"
            text = "Buy items."
        self.clear_hover()
        self.render()
        return self.response(tts=text, sfx="open_page")

    def buy_shop_item(self, kind, item_id):
        if kind == "fishing_rod" and item_id == "fishing_rod":
            return self.buy_fishing_rod()
        if kind in ("pickaxe", "mineral"):
            return self.buy_mine_item(kind, item_id)
        if kind == "seed":
            seed = self.get_seed_config(item_id)
            if not seed:
                return self.response(tts="Seed not sold here.", sfx="error")
            price = int(seed.get("seed_price", max(1, round(int(seed.get("crop_price", 1)) * 0.8))))
            label = f"{self.get_seed_label(item_id)} seeds"
        elif kind == "fertilizer":
            price = self.get_fertilizer_price()
            label = "Fertilizer"
        else:
            return self.response(tts="Item unavailable.", sfx="error")
        price = self.market_price(price, kind, "buy")
        if int(self.resources.get("coin", 0)) < price:
            return self.response(tts=f"Not enough gold. {label} costs {price} gold.", sfx="error")
        self.resources["coin"] -= price
        if kind == "seed":
            self.resources["seeds"][item_id] = int(self.resources["seeds"].get(item_id, 0)) + 1
            count = self.resources["seeds"][item_id]
        else:
            self.resources["fertilizer"] = int(self.resources.get("fertilizer", 0)) + 1
            count = self.resources["fertilizer"]
        self.clear_hover()
        self.render()
        return self.response(tts=f"{label} bought. Gold left: {self.resources['coin']} gold", sfx="shop_buy", sound_events=[{"kind": "one_shot", "sound": "coin"}] if price > 0 else [])

    def sell_shop_item(self, kind, item_id):
        if kind == "fish" and item_id in self.fishing_config()['fish']:
            if self.resources['fish'].get(item_id,0) < 1:
                return self.response(tts="No fish to sell.")
            fish = self.fishing_config()['fish'][item_id]
            price, label = self.get_fish_price(item_id), fish['label']
            self.resources['fish'][item_id] -= 1
        elif kind == "mineral" and item_id in self.MINERAL_LABELS:
            if self.resources[item_id] < 1:
                return self.response(tts="No mineral to sell.", sfx="error")
            price, label = self.get_mineral_price(item_id), self.MINERAL_LABELS[item_id]
            self.resources[item_id] -= 1
        elif kind == "crop":
            count = int(self.resources["crops"].get(item_id, 0))
            if count <= 0:
                return self.response(tts="No crop to sell.", sfx="error")
            price = int(self.get_seed_config(item_id).get("crop_price", 1))
            label = f"{self.get_seed_label(item_id)} crops"
            self.resources["crops"][item_id] = count - 1
        elif kind == "food":
            count = int(self.resources["foods"].get(item_id, 0))
            if count <= 0:
                return self.response(tts="No food to sell.", sfx="error")
            price = self.get_food_sell_price(item_id)
            label = self.get_recipe_label(item_id)
            self.resources["foods"][item_id] = count - 1
        else:
            return self.response(tts="Cannot sell this item.", sfx="error")
        price = self.market_price(price, kind, "sell")
        self.resources["coin"] += price
        self.consume_sale()
        self.clear_hover()
        self.render()
        return self.response(tts=f"{label} sold. Gold left: {self.resources['coin']} gold", sfx="shop_sell", sound_events=[{"kind": "one_shot", "sound": "coin"}] if price > 0 else [])

    def handle_command(self, command):
        command = str(command).lower().strip()
        command = {"f1":"minimap", "f2":"resources", "f3":"load", "f3_long":"save",
                   "f4":"click", "arrowleft":"left", "arrowright":"right"}.get(command, command)
        if command == "save":
            return self.save_game()
        if command == "load": return self.toggle_menu("load_game")
        if command == "minimap": return self.toggle_menu("minimap")
        if command == "resources": return self.toggle_menu("inventory")
        if command in ("left", "right"): return self.navigate_key(command)
        if command == "release":
            self.pointer_pressed = self.care_dragging = self.harvest_dragging = self.cooking_dragging = False
            self.drag_tool = None
            return self.response()
        # TEMP_EVALUATION_CLICK: F4 replaces pause during the user evaluation.
        # Original pause implementation (restore together with game-keys.js):
        # if command == "pause":
        #     self.paused = not self.paused
        #     self.pointer_pressed = self.care_dragging = self.harvest_dragging = self.cooking_dragging = False
        #     self.drag_tool = None
        #     return self.response(tts="Paused." if self.paused else "Resumed.")
        if command in ("click", "pause"):
            x, y = self.last_pointer
            if x is None or y is None:
                return self.response(tts="Move to an item first.")
            result = self.pointer_down(x, y)
            self.pointer_pressed = False
            result["state"] = self.get_state()
            return result
        return self.response()

    def resource_summary_text(self):
        seed_total = sum(int(v) for v in self.resources["seeds"].values())
        crop_total = sum(int(v) for v in self.resources["crops"].values())
        food_total = sum(int(v) for v in self.resources["foods"].values())
        return f"Gold {self.resources.get('coin', 0)},  fertilizer {self.resources.get('fertilizer', 0)}, seeds {seed_total}, crops {crop_total}, food {food_total}. {self.buff_text()}"

    def response(self, tts=None, sfx=None, sound_events=None):
        return {"tts": tts, "sfx": sfx, "sound_events": sound_events or [], "priority": "hover" if (sfx or "").startswith("hover_") else "action", "state": self.get_state()}

    def get_state(self):
        self.update_cooking_marker()
        if self.current_page in ("water_minigame", "fertilizer_minigame", "cooking"):
            self.render()
        plots = {plot_id: dict(state) for plot_id, state in self.farm_plots.items()}
        objects = self.get_objects()
        return {
            "spectator": spectator_snapshot(self, objects),
            "dialogue": {"speaker":"Rowan", "text":self.rowan_dialogue} if self.current_page=='town' and self.rowan_dialogue else None,
            "rowan_submission": self.current_page=="rowan_submit" and self.rowan_submit_open,
            "calendar": {"weekday":self.calendar_days()[self.weekday_index()]['name'], "offer":self.calendar_text()},
            "fishing": self.fishing_public_state(),
            "objects": [{"id": o["id"], "label": o.get("label", ""),
                         "type": o.get("type"), "x": o.get("x"), "y": o.get("y"),
                         "description": self.get_object_tts(o), "actionable": bool(o.get("action"))}
                        for o in objects if o.get("type") != "route"],
            "action_costs": {k: self.get_action_cost(k) for k in ("travel", "plant", "water", "fertilize", "harvest", "research", "cook", "mine", "fish")},
            "sleeping": self.sleep_until is not None,
            "client_settings": self.client_settings,
            "navigation": {d: bool(self.key_arrows(d)) for d in ("left", "right")},
            "page": self.current_page,
            "page_name": self.get_page_name(self.current_page),
            "current_location": self.current_location,
            "current_location_name": self.get_page_name(self.current_location),
            "day": self.day,
            "time": {
                "mode": "action",
                "used_cells": self.get_time_cells(),
                "total_cells": self.time_total_cells,
                "remaining_cells": max(0, self.time_total_cells - self.get_time_cells())
            },
            "day_ended": self.day_ended,
            "paused": self.paused,
            "resources": self.resources,
            "active_buff": dict(self.active_buff),
            "buff_text": self.buff_text(),
            "research_levels": dict(self.research_levels),
            "unlocked_plot_count": self.unlocked_plot_count,
            "farm_plots": plots,
            "seed_select_plot_id": self.seed_select_plot_id,
            "drag_tool": self.drag_tool,
            "plot_detail_id": self.detail_plot_id,
            "care": {
                "mode": self.care_mode,
                "total_targets": len(self.care_targets),
                "collected_targets": len(self.care_collected_ids),
                "dragging": self.care_dragging
            },
            "harvest": {
                "plot_id": self.harvest_plot_id,
                "total_targets": len(self.harvest_targets),
                "collected_targets": len(self.harvest_collected_ids),
                "dragging": self.harvest_dragging
            },
            "inventory": {"page": self.inventory_page + 1, "pages": self.inventory_page_count},
            "cooking": {
                "resume_point": self.cooking_resume_point(),
                "stage_index": self.cooking_stage_index,
                "stage_count": len(self.get_cooking_steps()),
                "gesture_kind": self.get_cooking_kind(),
                "stage_label": self.get_cooking_stage_label(),
                "start_point": list(self.cooking_path_samples[0]) if self.cooking_path_samples else None,
                "recipe_id": self.selected_recipe_id,
                "recipe_name": self.get_recipe_label(self.selected_recipe_id) if self.selected_recipe_id else None,
                "selected_ingredients": list(self.selected_ingredients),
                "progress": self.cooking_progress_index,
                "total": len(self.cooking_path_samples),
                "dragging": self.cooking_dragging
            },
            "dots": self.dotpad.to_list(),
            "width": self.dotpad.width,
            "height": self.dotpad.height,
            "time_dots": self.timepad.to_list(),
            "time_width": self.timepad.width,
            "time_height": self.timepad.height,
            "pointer": {"x": self.last_pointer[0], "y": self.last_pointer[1], "pressed": self.pointer_pressed},
            "hover_object": self.hover_object_id,
            "controls": {"F1": "Map", "F2": "Inventory", "F3": "Load / hold to save", "F4": "Pause"}
        }

    MINERAL_LABELS = {"stone": "Stone", "copper": "Copper", "iron": "Iron", "diamond": "Diamond"}

    def get_fertilizer_price(self):
        cfg = self.config.get("fertilizer", {})
        return int(cfg.get("shop_price", cfg.get("price", self.config.get("shop", {}).get("fertilizer_price", 12))))

    def get_pickaxe_price(self):
        return int(math.ceil(self.get_fertilizer_price() * float(self.config.get("mine", {}).get("pickaxe_price_multiplier", 5))))

    def get_mineral_price(self, mineral, buying=False):
        prices = sorted(float(s.get("crop_price", 1)) for s in self.config.get("seeds", {}).values()) or [1]
        mid = len(prices) // 2
        base = prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) / 2
        cfg = self.config.get("mine", {})
        price = int(math.ceil(base * float(cfg.get("mineral_sell_multipliers", {}).get(mineral, 1))))
        price += int(cfg.get("mineral_sell_price_bonus", 3))
        return int(math.ceil(price * float(cfg.get("mineral_buy_multiplier", 2)))) if buying else price

    def regenerate_mine(self):
        cfg = self.config.get("mine", {})
        width, height = self.dotpad.width, self.dotpad.height
        rw, rh = int(cfg.get("rock_width", 10)), int(cfg.get("rock_height", 10))
        gap = max(5, int(cfg.get("rock_gap", 5)))
        if rw < 1 or rh < 1 or rw > width or rh > height:
            raise ValueError("Rock size must fit the pad.")
        columns, rows = (width + gap) // (rw + gap), (height + gap) // (rh + gap)
        slack_x = width - (columns * rw + (columns - 1) * gap)
        slack_y = height - (rows * rh + (rows - 1) * gap)
        origin_y = random.randint(0, slack_y)
        candidates = []
        for row in range(rows):
            origin_x = random.randint(0, slack_x)
            top = origin_y + row * (rh + gap)
            for col in range(columns):
                left = origin_x + col * (rw + gap)
                candidates.append((left, top))
        random.shuffle(candidates)
        limit = max(0, min(7, int(cfg.get("daily_rock_limit", 7))))
        self.mine_rocks = [
            {"id": f"mine_rock_{self.day}_{i}", "left": x, "top": y,
             "width": rw, "height": rh, "hits": 0}
            for i, (x, y) in enumerate(candidates[:limit])
        ]

    def draw_mine_rock(self, obj):
        """Three fixed damage patterns; preserve a solid two-dot border."""
        width, height = int(obj["width"]), int(obj["height"])
        left, top = obj["x"] - width // 2, obj["y"] - height // 2
        hits = max(0, int(obj.get("hits", 0)))
        hits_to_break = max(1, int(self.config.get("mine", {}).get("hits_to_break", 3)))
        # Default: 0 / 1 / 2 hits. Custom hit counts retain the same three patterns.
        stage = min(2, (2 * hits) // max(1, hits_to_break - 1))
        for row in range(height):
            for col in range(width):
                border = col < 2 or col >= width - 2 or row < 2 or row >= height - 2
                grid_x, grid_y = (col - 2) % 3 == 0, (row - 2) % 3 == 0
                filled = stage == 0 or (stage == 1 and (grid_x or grid_y)) or (grid_x and grid_y)
                if border or filled:
                    self.dotpad.set_dot(left + col, top + row)

    def get_mine_objects(self):
        objects = []
        for rock in self.mine_rocks:
            objects.append({"id": rock["id"], "type": "mine_rock",
                            "x": rock["left"] + rock["width"] // 2,
                            "y": rock["top"] + rock["height"] // 2,
                            "width": rock["width"], "height": rock["height"],
                            "hits": rock.get("hits", 0),
                            "label": "Rock", "tts": "Rock. Tap to break." if self.resources["pickaxe"] else "Pickaxe required.",
                            "action": f"mine_hit:{rock['id']}"})
        exit_arrow = self.back_arrow("mine_exit", "Village", "travel:town")
        exit_arrow.update(x=3, y=self.dotpad.height-6, direction="left", size=3, hit_width=7, hit_height=7)
        objects.append(exit_arrow)
        entrance = self.back_arrow("mine_fishing", "Fishing lake", "travel:fishing")
        entrance["direction"] = "right"
        objects.append(entrance)
        return objects

    def item_destroyed_event(self, item_id, reward_sound=None, loot_tts=None):
        """Shared destruction event for pickaxes and future breakable items."""
        event = {"kind": "item_destroyed", "item_id": item_id}
        if reward_sound is not None:
            event.update(reward_sound=reward_sound, tts=loot_tts or "")
        return event

    def hit_mine_rock(self, rock_id):
        if self.current_page != "mine" or self.paused or self.day_ended:
            return self.response()
        rock = next((r for r in self.mine_rocks if r["id"] == rock_id), None)
        if rock is None:
            return self.response()
        self.hover_object_id = rock_id
        if self.resources.get("pickaxe", 0) < 1:
            return self.response(tts="Pickaxe required. Buy at the shop.", sfx="error")
        cfg = self.config.get("mine", {})
        rock["hits"] += 1
        self._pickaxe_hits += 1
        destroyed = rock["hits"] >= int(cfg.get("hits_to_break", 3))
        text = ""
        events = []
        if destroyed:
            level = self.research_levels.get("mineral_luck", 0)
            research = self.config.get("research", {}).get("mineral_luck", {})
            weights = dict(cfg.get("loot_weights", {"diamond": 1, "iron": 15, "copper": 34, "stone": 50}))
            bonus = float(research.get("diamond_weight_per_level", 1)) * level
            weights["diamond"] += bonus
            weights["stone"] = max(0, weights["stone"] - bonus)
            weights = self.boost_rare_weights(weights, ("iron", "diamond"))
            mineral = random.choices(list(weights), weights=list(weights.values()), k=1)[0]
            doubled = random.random() < min(1, level * float(research.get("double_drop_chance_per_level", .15)))
            amount = self.loot_amount(2 if doubled else 1)
            doubled = amount > 1
            self.resources[mineral] += amount
            self.mine_rocks.remove(rock)
            text = f"{self.MINERAL_LABELS[mineral]} {amount} collected." + (". Bonus." if doubled else "")
        else:
            events.append({"kind": "one_shot", "sound": "pickaxe"})
        safe_hits = int(cfg.get("pickaxe_safe_hits", 9))
        break_chance = min(1, max(0, self._pickaxe_hits - safe_hits) * float(cfg.get("pickaxe_break_increment", .05)))
        break_chance *= self.buff_multiplier_for("pickaxe_protection")
        item_destroyed = break_chance > 0 and random.random() < break_chance
        if item_destroyed:
            self.resources["pickaxe"] = 0
            self._pickaxe_hits = 0
            text += (". " if text else "") + "Pickaxe broken. Buy another at the shop."
        if destroyed:
            fatigue = self.consume_time("mine")
            if fatigue["night"]:
                text += ". Night. Home now. Select the bed."
        self.render()
        if item_destroyed:
            # Replace the mining impact instead of layering both impact sounds.
            reward_sound = ("shine" if mineral == "diamond" else "correct") if destroyed else None
            events = [self.item_destroyed_event("pickaxe", reward_sound, text if destroyed else None)]
        elif destroyed:
            events.append({"kind": "mining_loot", "sound": "shine" if mineral == "diamond" else "correct", "tts": text})
        return self.response(tts=None if destroyed else (text or None), sound_events=events)

    def get_harvest_base_yield(self, seed_id):
        return int(self.get_seed_config(seed_id).get("yield", 1))

    def build_shop_objects(self, entries, mode):
        page_size = 12
        pages = max(1, math.ceil(len(entries) / page_size))
        self.shop_page = max(0, min(self.shop_page, pages - 1))
        objects = []
        for i, (kind, item_id, label, count, price) in enumerate(entries[self.shop_page * page_size:(self.shop_page + 1) * page_size]):
            price = self.market_price(price, kind, mode)
            x, y = (9, 23, 37, 51)[i % 4], (5, 15, 25)[i // 4]
            text = f"{label}, {price} gold. stock {count} " if mode == "buy" else f"{label}, stock {count}. Sell {price} gold"
            if kind == "pickaxe" and count:
                text = "Pickaxe owned. Limit one."
            objects.append({"id": f"shop_{mode}_{kind}_{item_id}", "type": "shop_item", "shop_kind": kind, "item_id": item_id,
                            "x": x, "y": y, "width": 10, "height": 6, "hit_width": 10, "hit_height": 6,
                            "count": int(count), "price": int(price), "label": label, "tts": text, "action": f"{mode}:{kind}:{item_id}"})
        objects.append(self.back_arrow(f"shop_{mode}_back", "Back to shop", "return_shop_choice"))
        for delta, x, direction, label in [(-1, 30, "left", "Previous page"), (1, 51, "right", "Next page")]:
            if 0 <= self.shop_page + delta < pages:
                objects.append({"id": f"shop_page_{direction}", "type": "arrow", "x": x, "y": 35, "direction": direction,
                                "size": 2, "hit_width": 11, "hit_height": 7, "label": label, "action": f"shop_page:{delta}"})
        if not entries:
            objects.append({"id": "shop_empty", "type": "box", "x": 30, "y": 16, "width": 20, "height": 8,
                            "label": "Nothing to sell", "tts": "Nothing to sell.", "action": ""})
        return objects

    def buy_mine_item(self, kind, item_id):
        if kind == "pickaxe":
            if self.resources["pickaxe"] >= 1:
                return self.response(tts="Only one pickaxe allowed.", sfx="error")
            price, label = self.get_pickaxe_price(), "Pickaxe"
        elif kind == "mineral" and item_id in ("stone", "copper", "iron"):
            price, label = self.get_mineral_price(item_id, buying=True), self.MINERAL_LABELS[item_id]
        else:
            return self.response(tts="Item unavailable.", sfx="error")
        price = self.market_price(price, kind, "buy")
        if self.resources["coin"] < price:
            return self.response(tts=f"Not enough gold. Need {price} gold for {label}.", sfx="error")
        self.resources["coin"] -= price
        if kind == "pickaxe":
            self.resources["pickaxe"] = 1
            self._pickaxe_hits = 0
        else:
            self.resources[item_id] += 1
        self.clear_hover()
        self.render()
        return self.response(tts=f"{label} bought. Gold left: {self.resources['coin']} gold", sound_events=[{"kind": "one_shot", "sound": "coin"}])

    def buy_mineral_research(self, kind):
        if kind != "mineral_luck":
            return self.response(tts="Research unavailable.", sfx="error")
        cfg = self.config.get("research", {}).get(kind, {})
        level = self.research_levels.get(kind, 0)
        maximum = int(cfg.get("max_level", 2))
        if level >= maximum:
            return self.response(tts="Maximum research level.", sfx="error")
        mineral = "iron"
        costs, materials = cfg.get("costs", [20, 40]), cfg.get(f"{mineral}_costs", [3, 6])
        cost, material_cost = int(costs[level]), int(materials[level])
        if self.resources["coin"] < cost or self.resources[mineral] < material_cost:
            return self.response(tts=f"Not enough materials. Need {cost} gold, {self.MINERAL_LABELS[mineral]} {material_cost} required", sfx="error")
        self.resources["coin"] -= cost
        self.resources[mineral] -= material_cost
        self.research_levels[kind] = level + 1
        text = f"Mineral discovery level {level + 1} complete."
        result = self.consume_time("research")
        events = [{"kind": "one_shot", "sound": "coin"}]
        if result["night"]:
            return self.night_response(text, sound_events=events)
        self.clear_hover()
        self.render()
        return self.response(tts=text, sound_events=events)

    def draw_mine_item(self, x, y, kind):
        x, y = int(x), int(y)
        if kind == "pickaxe":
            self.dotpad.draw_line(x - 3, y - 2, x + 3, y - 2)
            self.dotpad.draw_line(x, y - 2, x, y + 2)
        elif kind == "diamond":
            for a, b in [((-3, 0), (0, -2)), ((0, -2), (3, 0)), ((3, 0), (0, 2)), ((0, 2), (-3, 0))]:
                self.dotpad.draw_line(x+a[0], y+a[1], x+b[0], y+b[1])
        else:
            for row in range({"stone": 1, "copper": 2, "iron": 3}.get(kind, 1)):
                self.dotpad.draw_line(x-2, y-1+row, x+2, y-1+row)

