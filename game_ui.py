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
        obj = arrows[0]
        self.pointer_pressed = self.care_dragging = self.harvest_dragging = self.cooking_dragging = False
        self.drag_tool = None
        result = self.perform_action(obj.get('action',''), obj)
        if obj.get('action','').startswith('travel:'):
            name = self.get_page_name(self.current_location)
            if not str(result.get('tts') or '').startswith(name):
                result['tts'] = f'{name}. {result.get("tts") or ""}'.strip()
        return result

    @staticmethod
    def item_bounds(obj):
        w,h=int(obj.get('width',12)),int(obj.get('height',8))
        return round(obj['x'])-w//2, round(obj['y'])-h//2, w, h

    def draw_item_frame(self, obj, kind):
        left,top,w,h=self.item_bounds(obj)
        if kind not in ('food','coin'):
            # Keep the original DotPad box geometry and icon center unchanged.
            self.dotpad.draw_box(obj['x'], obj['y'], w, h)
            return
        # Keep the existing outline; insert only a central column and row.
        # A 12-by-8 outline becomes 13-by-9, centered on the original box center.
        previous=(w-2)//2
        half=max(1,(h-1)//2)
        for row in range((h+1)//2):
            t=row/half
            if kind == 'coin':
                inset=max(0,round((w-2)/2*(1-t)))
            else:
                inset=w//4 if row==0 else max(0,round((w-2)/2*(1-math.sqrt(max(0,1-(1-t)**2)))))
            cols=set(range(inset,w-inset)) if row==0 else set(range(inset,max(inset+1,previous)))
            cols |= {w-1-col for col in cols}
            previous=inset
            for col in cols:
                for yy in {row,h-1-row}:self.draw_expanded_item_dot(left,top,w,h,col,yy)

    def draw_expanded_item_dot(self, left, top, w, h, col, row):
        columns = [col if col < w//2 else col+1]
        rows = [row if row < h//2 else row+1]
        if col == w//2-1: columns.append(w//2)
        if row == h//2-1: rows.append(h//2)
        for yy in rows:
            for xx in columns:self.dotpad.set_dot(left+xx,top+yy)

    def draw_category(self, x, y, kind):
        if kind in ('stone','copper','iron','diamond','mineral'): kind='mineral'
        if kind in ('pickaxe','tool','fertilizer','fishing_rod'): kind='tool'
        patterns={
            'seed':['10001','00000','00100'],
            'crop':['11111','01110','00100'],
            'fish':['011010','111110','011010'],
            'mineral':['111','111','111'],
            'tool':['00100','11111','01110','11011'],
            'fertilizer':['11011','11011','00000'],
            'material':['11111','11111','11111'],
            'coin':['1'],
        }
        self.draw_icon_pattern(x,y,patterns.get(kind,['111','111','111']))

    def draw_catalog_item(self, obj, kind, recipe_id=None):
        self.draw_item_frame(obj, kind)
        if kind == 'food':
            # One shared bowl symbol; recipe identity is given by speech.
            left,top,w,h=self.item_bounds(obj)
            rows=['111111','011110']
            x0,y0=left+(w-6)//2,top+(h-2)//2
            for row,pattern in enumerate(rows):
                for col,value in enumerate(pattern):
                    if value=='1':self.draw_expanded_item_dot(left,top,w,h,x0-left+col,y0-top+row)
        elif kind == 'coin':
            left,top,w,h=self.item_bounds(obj)
            for y in range(top+(h-2)//2,top+(h-2)//2+2):
                for x in range(left+(w-2)//2,left+(w-2)//2+2):self.draw_expanded_item_dot(left,top,w,h,x-left,y-top)
        else: self.draw_category(obj['x'],obj['y'],kind)

    def draw_facility(self, obj):
        self.dotpad.draw_box(obj['x'],obj['y'],12,10)
        patterns={
            'bed':['1100000','1100000','1111111','1111111','1111111'],
            'chest':['0011100','0011100','1111111','1111111','1111111','0011100','0011100'],
            'stove':['00100','01110','11111','11111','01110'],
            'shop_npc':['1111111','1111111','1100011','1100011','1111111'],
        }
        self.draw_icon_pattern(obj['x'],obj['y'],patterns[obj['type']])
