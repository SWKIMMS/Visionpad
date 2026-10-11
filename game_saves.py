"""Versioned local JSON snapshots; twelve newest files are retained."""
import copy
import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def encode(value):
    if isinstance(value, (set, tuple)):
        return {"$type": type(value).__name__, "items": [encode(v) for v in value]}
    if isinstance(value, dict):
        return {"$type": "dict", "items": [[encode(k), encode(v)] for k, v in value.items()]}
    if isinstance(value, list):
        return [encode(v) for v in value]
    return value


def decode(value):
    if isinstance(value, list):
        return [decode(v) for v in value]
    if isinstance(value, dict):
        kind, items = value["$type"], value["items"]
        if kind == "dict": return {decode(k): decode(v) for k, v in items}
        if kind == "set": return set(map(decode, items))
        if kind == "tuple": return tuple(map(decode, items))
        raise ValueError("Unsupported snapshot type")
    return value


class SaveMixin:
    def snapshot(self):
        state = {k: copy.deepcopy(v) for k, v in vars(self).items()
                 if k not in self._static_fields and k not in {"_static_fields", "_load_return", "_save_slots"}}
        state["random_state"] = random.getstate()
        now = time.monotonic()
        for key in ("sleep_until", "cooking_last_progress_at"):
            if state.get(key) is not None: state[key] -= now
        for key in ("care_visible_until", "cooking_visible_until"):
            state[key] = {k: v-now for k, v in state.get(key, {}).items()}
        if state.get("pending_visual_completion"):
            deadline, kind = state["pending_visual_completion"]
            state["pending_visual_completion"] = (deadline-now, kind)
        # A physical held gesture cannot safely survive a restart.
        for key in ("pointer_pressed", "care_dragging", "harvest_dragging", "cooking_dragging"):
            state[key] = False
        state["drag_tool"] = None
        state["hover_object_id"] = None
        return state

    def restore_snapshot(self, state):
        state = copy.deepcopy(state)
        state.setdefault("_menu_stack", [])
        # Validate structure against a fresh engine before mutating the live game.
        previous_rng = random.getstate()
        try:
            fresh = type(self)(self.config, save_dir=self.save_dir)
        finally:
            random.setstate(previous_rng)
        # Migrate pre-fishing saves without replacing existing progress.
        for key in ('fishing_target', 'fishing_last_catch', 'fishing_attempts', 'rod_casts', 'rod_catches'):
            state.setdefault(key, copy.deepcopy(getattr(fresh, key)))
        state['resources'].setdefault('fishing_rod', 0)
        state['resources'].setdefault('fish', {})
        # Retired high-grade fried fish becomes the supported medium variant.
        foods = state['resources'].setdefault('foods', {})
        retired = foods.pop('fried_fish_high', 0)
        if retired: foods['fried_fish_medium'] = foods.get('fried_fish_medium', 0) + retired
        buff = state.get('active_buff', {})
        if buff.get('source') == 'fried_fish_high': buff['source'] = 'fried_fish_medium'
        recipe = fresh.get_recipe_config(buff.get('source'))
        if recipe.get('seafood'):
            for field, key in [('multiplier','buff_multiplier'), ('rare_weight_multiplier','rare_weight_multiplier'), ('double_chance','double_chance')]:
                if key in recipe: buff[field] = recipe[key]
            if 'sale_uses' in recipe: buff['remaining_sales'] = min(buff.get('remaining_sales',0),recipe['sale_uses'])
            buff['remaining_ticks'] = min(buff.get('remaining_ticks',0),recipe.get('buff_ticks',0))
        expected = set(fresh.snapshot())
        if set(state) != expected: raise ValueError("Incompatible save")
        if any(type(state[k]) is not type(v) and not (type(v) in (int, float) and type(state[k]) in (int, float))
               for k, v in fresh.snapshot().items()
               if v is not None and k not in {"pending_visual_completion", "sleep_until", "cooking_last_progress_at"}):
            raise ValueError("Invalid save state")
        rng = state.pop("random_state")
        random.Random().setstate(rng)
        now = time.monotonic()
        for key in ("sleep_until", "cooking_last_progress_at"):
            if state.get(key) is not None: state[key] += now
        for key in ("care_visible_until", "cooking_visible_until"):
            state[key] = {k: v+now for k, v in state[key].items()}
        if state.get("pending_visual_completion"):
            deadline, kind = state["pending_visual_completion"]
            state["pending_visual_completion"] = (deadline+now, kind)
        fresh.__dict__.update(state)
        fresh.render()
        random.setstate(rng)
        self.__dict__.update(state)
        self._load_return = None
        self.render()

    def list_saves(self):
        slots = []
        for path in sorted(self.save_dir.glob("save_*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("version") != 1: continue
                slots.append({"id": path.stem, "day": int(data["day"]), "created": data["created"]})
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return slots[:12]

    def save_game(self):
        state = self._load_return if self.current_page == "load_game" else self.snapshot()
        stamp = datetime.now(timezone.utc)
        name = "save_" + stamp.strftime("%Y%m%dT%H%M%S%f") + "_" + uuid4().hex[:8]
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            target = self.save_dir / (name + ".json")
            temp = self.save_dir / (name + ".tmp")
            data = {"version": 1, "created": stamp.isoformat(), "day": state["day"], "state": encode(state)}
            temp.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            os.replace(temp, target)
            for old in sorted(self.save_dir.glob("save_*.json"), reverse=True)[12:]: old.unlink()
        except (OSError, ValueError, TypeError):
            return self.response(tts="Could not save the game.")
        if self.current_page == "load_game":
            self._save_slots = self.list_saves()
            self.render()
        self.pointer_pressed = False
        self.care_dragging = self.harvest_dragging = self.cooking_dragging = False
        self.drag_tool = None
        return self.response(tts="Game saved.")

    def open_load_game(self):
        if self.current_page != "load_game": self._load_return = self.snapshot()
        self._save_slots = self.list_saves()
        self.current_page = "load_game"
        self.paused = False
        self.day_ended = False
        self.sleep_until = None
        self.pending_visual_completion = None
        self.pointer_pressed = False
        self.clear_hover()
        self.render()
        return self.response(tts="Choose a save." if self._save_slots else "No saved games.")

    def close_load_game(self):
        if self._load_return is not None: self.restore_snapshot(self._load_return)
        self._menu_stack.clear()
        return self.return_to_scene()

    def load_game(self, slot_id):
        if self.current_page != "load_game" or slot_id not in {s["id"] for s in self._save_slots}:
            return self.response(tts="Save unavailable.")
        try:
            data = json.loads((self.save_dir / (slot_id + ".json")).read_text(encoding="utf-8"))
            if data["version"] != 1: raise ValueError("Save version")
            self.restore_snapshot(decode(data["state"]))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return self.response(tts="Could not load this save.")
        return self.response(tts=f"Game loaded. Day {self.day}. {self.get_page_name(self.current_page)}.")

    def get_load_objects(self):
        objects = []
        for i, slot in enumerate(self._save_slots):
            objects.append({"id": slot["id"], "type": "save_slot", "x": 8+14*(i%4), "y": 5+10*(i//4),
                            "width": 12, "height": 8, "hit_width": 12, "hit_height": 8,
                            "label": f"Save {i+1}", "tts": f"Save {i+1}. Day {slot['day']}. {slot['created'][:16].replace('T', ' ')} UTC.",
                            "action": "load_slot:"+slot["id"]})
        objects.append(self.back_arrow("load_back", "Back", "close_load"))
        return objects
