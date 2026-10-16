"""Shared tactile slots and frame/symbol composition (3 rows by 4 columns)."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class IconGrid:
    rows: int = 3
    columns: int = 4
    width: int = 12
    height: int = 10

    def place(self, objects, screen_width=60, screen_height=40, used_columns=None):
        """Return copies; a restricted grid uses the left columns, never resizes cells."""
        columns = self.columns if used_columns is None else used_columns
        if not 1 <= columns <= self.columns:
            raise ValueError('Invalid active column count')
        if len(objects) > self.rows * columns:
            raise ValueError('Icon page exceeds grid capacity; paginate its items first')
        pitch_x = (screen_width - 4) // self.columns
        pitch_y = (screen_height - 1) // self.rows
        if pitch_x < self.width + 2 or pitch_y < self.height + 2:
            raise ValueError('Display is too small for separated icon frames')
        result = []
        for index, original in enumerate(objects):
            row, col = divmod(index, columns)
            obj = dict(original)
            obj.update(x=2+self.width//2+col*pitch_x,
                       y=1+self.height//2+row*pitch_y,
                       width=self.width, height=self.height,
                       hit_width=self.width, hit_height=self.height,
                       grid_row=row, grid_column=col, grid_slot=row*self.columns+col)
            result.append(obj)
        return result


@dataclass(frozen=True)
class IconSpec:
    frame: str = 'rectangle'
    symbol: str = 'material'
    pattern: tuple = ()


class IconRenderer:
    """One frame plus one semantic symbol; optional selection/progress overlays."""
    TYPES = frozenset(('bed','chest','stove','shop_npc','rowan','calendar_day',
        'calendar_button','save_slot','plot','seed','resource','research','care_button',
        'recipe','ingredient','cooking_start','shop_choice','shop_item','watering_can','fertilizer'))
    PATTERNS = {
        'seed': ('10001','00000','00100'),
        'crop': ('11111','01110','00100'),
        'fish': ('011010','111110','011010'),
        'mineral': ('111','111','111'),
        'tool': ('00100','11111','01110','11011'),
        'material': ('11111','11111','11111'),
        'food': ('1111111','0111110'),
        'coin': ('111','111','111'),
        'bed': ('1100000','1100000','1111111','1111111','1111111'),
        'chest': ('0011100','0011100','1111111','1111111','1111111','0011100','0011100'),
        'stove': ('00100','01110','11111','11111','01110'),
        'shop_npc': ('1111111','1111111','1100011','1100011','1111111'),
        'rowan': ('00100','01110','00100','11111','00100','01010','01010'),
        'calendar': ('11111','00000','10101','00000','10101'),
        'save': ('11111','10001','10001','10001','11111'),
        'water': ('00100','01110','11111','11111','01110'),
        'harvest': ('00100','01110','11111','01110','00100'),
        'start': ('00100','00110','11111','00110','00100'),
        'sell': ('01111','10000','10000','01110','00001','00001','11110'),
        'buy': ('11110','10001','10001','11110','10001','10001','11110'),
        'check': ('000001','000010','100100','011000'),
    }
    ALIASES = dict.fromkeys(('stone','copper','iron','diamond'), 'mineral') | dict.fromkeys(('pickaxe','fertilizer','fishing_rod'), 'tool')

    def __init__(self, engine):
        self.engine = engine
        self.dotpad = engine.dotpad

    @classmethod
    def category(cls, kind):
        return cls.ALIASES.get(kind, kind or 'material')

    def spec(self, obj):
        kind = obj.get('type')
        symbol = kind
        frame = 'rectangle'
        if kind == 'resource': symbol = self.category(obj.get('resource_kind'))
        elif kind == 'shop_item': symbol = self.category(obj.get('shop_kind'))
        elif kind == 'recipe': symbol = 'food'
        elif kind == 'ingredient': symbol = 'check' if obj.get('selected') else self.category(obj.get('item_kind','crop'))
        elif kind == 'care_button': symbol = {'plant':'seed','fertilizer':'tool'}.get(obj.get('care_kind'),obj.get('care_kind'))
        elif kind == 'watering_can': symbol = 'water'
        elif kind == 'fertilizer': symbol = 'tool'
        elif kind == 'shop_choice': symbol = obj.get('choice')
        elif kind in ('calendar_day','calendar_button'): symbol = 'calendar'
        elif kind == 'save_slot': symbol = 'save'
        elif kind == 'cooking_start': symbol = 'start'
        elif kind == 'research':
            key = obj.get('research_kind')
            symbol = {'seed_return':'seed','field_expand':'tool','mineral_luck':'mineral'}.get(key,'chest')
        if symbol == 'food' or kind == 'rowan' and obj.get('quest_available'): frame = 'double_rectangle'
        elif symbol == 'coin': frame = 'rectangle'
        return IconSpec(frame, symbol)

    def frame(self, obj, shape='rectangle'):
        # Width/height are center-to-center spans: all frames occupy w+1 by h+1 dots.
        # Legacy callers receive the same updated frame classification.
        if shape == 'ellipse': shape = 'double_rectangle'
        if shape == 'double_rectangle':
            self.frame(obj, 'rectangle')
            inner = dict(obj, width=max(2,int(obj.get('width',12))-4),
                         height=max(2,int(obj.get('height',10))-4))
            self.frame(inner, 'rectangle')
            return
        x,y = round(obj['x']),round(obj['y'])
        rx,ry = int(obj.get('width',12))//2,int(obj.get('height',10))//2
        def extent_at(distance):
            if shape == 'rectangle': return rx
            if shape == 'diamond': return round(rx*(1-distance/max(1,ry)))
            return round(rx*math.sqrt(max(0,1-(distance/max(1,ry))**2)))
        for distance in range(ry+1):
            extent=extent_at(distance)
            outer=extent_at(distance+1) if distance<ry else extent
            columns=range(-rx,rx+1) if shape=='rectangle' and distance==ry else {v for dx in range(min(extent,outer)+1,extent+1) for v in (-dx,dx)} | {-extent,extent}
            for dy in {-distance,distance}:
                for dx in columns:self.dotpad.set_dot(x+dx,y+dy)

    def pattern(self, x, y, rows):
        self.engine.draw_icon_pattern(x,y,rows)

    def catalog(self, obj, kind):
        symbol = self.category(kind)
        self.frame(obj, 'double_rectangle' if symbol=='food' else 'rectangle')
        self.pattern(obj['x'],obj['y'],self.PATTERNS.get(symbol,self.PATTERNS['material']))

    def draw(self, obj):
        if obj.get('type') not in self.TYPES: return False
        spec = self.spec(obj)
        self.frame(obj,spec.frame)
        if obj['type'] == 'plot':
            state = self.engine.farm_plots.get(obj['id'],self.engine.new_plot_state())
            if state.get('seed_id'):
                days=max(1,self.engine.get_seed_config(state['seed_id']).get('growth_days',3))
                ratio=1 if state.get('mature') else min(1,max(0,state['growth']/days))
                rx,ry=obj['width']//2,obj['height']//2
                count=math.ceil((2*ry-1)*ratio)
                for y in range(obj['y']+ry-count,obj['y']+ry):
                    for x in range(obj['x']-rx+1,obj['x']+rx):self.dotpad.set_dot(x,y)
        else:
            rows = spec.pattern or self.PATTERNS.get(spec.symbol,self.PATTERNS['material'])
            if spec.frame == 'double_rectangle' and spec.symbol == 'rowan':
                # Keep the person inside the inner border, with a blank-dot gap.
                rows = ('00100','11111','00100','01010','01010')
            self.pattern(obj['x'],obj['y'],rows)
        return True


class IconLayout:
    """Page policy over the same twelve virtual slots."""
    PAGES = frozenset(('home','town','farm','inventory','research','seed_select',
        'recipe_select','ingredient_select','shop_choice','shop_buy','shop_sell',
        'load_game','shop_calendar','rowan_dialogue','rowan_submit'))

    def __init__(self, grid=None):
        self.grid = grid or IconGrid()

    def arrange(self, page, objects, width, height):
        objects = [dict(o) for o in objects]
        if page not in self.PAGES and page != 'plot_detail': return objects
        chosen = [o for o in objects if o.get('type') in IconRenderer.TYPES
                  and (page != 'plot_detail' or o.get('type')=='care_button')]
        if page in ('home','town'):
            order={'bed':0,'chest':1,'stove':2,'shop_npc':3,'rowan':4}
            chosen.sort(key=lambda o:order.get(o['type'],5))
        placed=self.grid.place(chosen,width,height,used_columns=2 if page=='farm' else None)
        by_id={o['id']:o for o in placed}
        return [by_id.get(o.get('id'),o) for o in objects]
