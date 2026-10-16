"""Keypad navigation, temporary menus, and tactile category symbols."""
import math
import time


class KeypadUI:
    def toggle_menu(self, page):
        if self.current_page == 'load_game':
            result = self.close_load_game()
            if page == 'load_game': return result
        if self.current_page == page:
            self._menu_stack.clear()
            return self.return_to_scene()
        if page == 'load_game': return self.open_load_game()
        if self.sleep_until is not None: return self.response(tts='Sleeping. Please wait.')
        if self.paused: return self.response(tts='Resume first.')
        if self.day_ended: return self.night_only_response()
        # Menus return to the current region, so do not build nested return stacks.
        self._menu_stack.clear()
        self.pending_visual_completion = None
        self.pointer_pressed = self.care_dragging = self.harvest_dragging = self.cooking_dragging = False
        self.drag_tool = None
        self.current_page = page
        if page == 'inventory': self.inventory_page = 0
        self.clear_hover()
        self.render()
        return self.response(tts='Map. Select a place.' if page == 'minimap' else f'Inventory. {self.resources["coin"]} gold.')

    def key_arrows(self, direction):
        all_arrows = [o for o in self.get_layout_objects() if o.get('type') == 'arrow']
        arrows = [o for o in all_arrows if ('left' if o.get('direction') == 'left' else 'right') == direction]
        if (not arrows and direction == 'right'
                and self.current_page not in ('farm', 'home', 'town', 'mine', 'fishing', 'inventory')
                and all_arrows and all(o.get('direction') == 'left' for o in all_arrows)):
            arrows = all_arrows
        return arrows

    def navigate_key(self, direction):
        if self.paused: return self.response(tts='Resume first.')
        if self.sleep_until is not None: return self.response(tts='Sleeping. Please wait.')
        arrows = self.key_arrows(direction)
        # Previous page takes precedence; on the first shop page Left means back.
        arrows.sort(key=lambda o: not o.get('action','').startswith(('shop_page:', 'inventory_page:')))
        if not arrows: return self.response(tts=f'Cannot go {direction}.')
        # Keep the pressed key direction even when Right aliases a Back action.
        obj = dict(arrows[0], direction=direction)
        self.pointer_pressed = self.care_dragging = self.harvest_dragging = self.cooking_dragging = False
        self.drag_tool = None
        result = self.perform_action(obj.get('action',''), obj)
        if obj.get('action','').startswith('travel:'):
            name = self.get_page_name(self.current_location)
            if not str(result.get('tts') or '').startswith(name):
                result['tts'] = f'{name}. {result.get("tts") or ""}'.strip()
        return result

    def draw_item_frame(self, obj, kind):
        self.icons.frame(obj, 'double_rectangle' if kind=='food' else 'rectangle')

    def draw_category(self, x, y, kind):
        symbol = self.icons.category(kind)
        self.icons.pattern(x,y,self.icons.PATTERNS.get(symbol,self.icons.PATTERNS['material']))

    def draw_catalog_item(self, obj, kind, recipe_id=None):
        self.icons.catalog(obj,kind)

    def draw_facility(self, obj):
        self.icons.draw(obj)
