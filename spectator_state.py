"""Public, detached visual data. Never changes gameplay or exposes hidden rolls."""
import copy
import time


def spectator_snapshot(engine, objects):
    now = time.monotonic()
    fields = ('id', 'type', 'x', 'y', 'width', 'height', 'label', 'selected',
              'resource_kind', 'recipe_id', 'seed_id', 'ingredient_id', 'choice',
              'item_kind', 'shop_kind', 'item_id', 'count', 'price', 'direction',
              'research_kind', 'required_count', 'display_quantities', 'quest_available')
    public_objects = [{k: copy.deepcopy(o[k]) for k in fields if k in o}
                      for o in objects if o.get('type') not in ('arrow', 'route')]
    for public in public_objects:
        kind = public.get('type')
        recipe_id = public.get('recipe_id') or (public.get('item_id') if public.get('shop_kind') == 'food' else None)
        if recipe_id:
            recipe = engine.get_recipe_config(recipe_id)
            if recipe:
                public['effect_description'] = engine.recipe_effect_text(recipe)
        if kind == 'seed':
            public['count'] = int(engine.resources['seeds'].get(public.get('seed_id'), 0))
        elif kind == 'recipe':
            ingredients = engine.get_recipe_config(public.get('recipe_id')).get('ingredients', {})
            public['display_quantities'] = [dict(item=key, label=engine.get_seed_label(key),
                required=int(count), owned=int(engine.resources['crops'].get(key, 0))) for key, count in ingredients.items()]
            if recipe.get('seafood'):
                public['display_quantities'].append(dict(item=recipe.get('allowed_fish',['salmon'])[0],label='Fish',required=recipe.get('fish_required',1),owned=sum(engine.resources.get('fish',{}).get(k,0) for k in recipe.get('allowed_fish',[]))))
        elif public.get('id') == 'plot_detail_fertilizer':
            public['count'] = int(engine.resources.get('fertilizer', 0))
    plots = []
    for definition in engine.get_unlocked_plot_defs():
        state = engine.farm_plots[definition['id']]
        seed = engine.config.get('seeds', {}).get(state.get('seed_id'), {})
        plots.append(dict(id=definition['id'], **copy.deepcopy(state),
                          growth_days=seed.get('growth_days', 1)))

    def targets(items, collected, deadlines):
        return [dict(id=t['id'], x=t['x'], y=t['y'],
                     collected=t['id'] in collected,
                     visible=t['id'] not in collected or deadlines.get(t['id'], 0) > now)
                for t in items]

    return {
        'schema': 1, 'objects': public_objects, 'plots': plots,
        'routes': [{k: o[k] for k in ('x1', 'y1', 'x2', 'y2')}
                   for o in objects if o.get('type') == 'route'],
        'rocks': [{k: r[k] for k in ('id', 'left', 'top', 'width', 'height', 'hits')}
                  for r in engine.mine_rocks],
        'care_targets': targets(engine.care_targets, engine.care_collected_ids, engine.care_visible_until),
        'harvest_targets': targets(engine.harvest_targets, engine.harvest_collected_ids, {}),
        'path': [dict(x=p[0], y=p[1], passed=i < engine.cooking_progress_index,
                      visible=i >= engine.cooking_progress_index or engine.cooking_visible_until.get(i, 0) > now)
                 for i, p in enumerate(engine.cooking_path_samples)],
    }
