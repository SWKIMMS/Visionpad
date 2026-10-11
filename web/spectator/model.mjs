export const WORLD = { width: 960, height: 600 };
export const SCENES = ["home", "farm", "town", "mine", "fishing"];
export const TITLES = {
  home: "Home",
  farm: "The farm",
  town: "Village square",
  mine: "Mountain quarry",
  fishing: "Fishing lake",
  minimap: "Valley map",
  inventory: "Your inventory",
  research: "Research workshop",
  recipe_select: "The recipe book",
  ingredient_select: "Gathering ingredients",
  cooking: "In the kitchen",
  seed_select: "Choose your seeds",
  plot_detail: "Tending the plot",
  water_minigame: "Watering",
  fertilizer_minigame: "Fertilizing",
  harvest: "Harvest time",
  shop_choice: "The village shop",
  shop_buy: "Buying supplies",
  shop_sell: "Selling produce",
  load_game: "Saved adventures",
};
export const SPRITES = {
  tomato: 0,
  carrot: 1,
  potato: 2,
  coin: 3,
  fertilizer: 4,
  seed_tomato: 5,
  seed_carrot: 6,
  seed_potato: 7,
  pickaxe: 8,
  stone: 9,
  copper: 10,
  iron: 11,
  diamond: 12,
  tomato_carrot_stew: 13,
  potato_tomato_soup: 14,
  vegetable_tempura: 15,
  vegetable_fritters: 15,
  sprout: 16,
  leaves: 17,
  plant_tomato: 18,
  plant_carrot: 19,
  plant_potato: 20,
  rock: 21,
  farmer: 22,
  water: 23,
  research: 24,
  wood: 25,
};
export function phase(s) {
  const ratio = Math.max(
    0,
    Math.min(1, (s.time?.used_cells || 0) / (s.time?.total_cells || 20)),
  );
  return ratio < 0.25
    ? { name: "Morning", color: "#ffc876", alpha: 0.06 }
    : ratio < 0.6
      ? { name: "Daytime", color: "#ffe8ac", alpha: 0 }
      : ratio < 0.85
        ? { name: "Dusk", color: "#b35b71", alpha: 0.23 }
        : { name: "Evening", color: "#15264f", alpha: 0.46 };
}
export function scene(s) {
  if (s.page?.startsWith("shop_")) return "town";
  return SCENES.includes(s.page)
    ? s.page
    : SCENES.includes(s.current_location)
      ? s.current_location
      : "home";
}
export function plots(s) {
  const source =
    s.spectator?.plots ||
    Object.entries(s.farm_plots || {})
      .slice(0, s.unlocked_plot_count || 0)
      .map(([id, p]) => ({ id, ...p }));
  const objects=s.spectator?.objects||s.objects||[];
  return source.map((p,i)=>{
    const o=objects.find(o=>o.id===p.id), width=o?.width||12, height=o?.height||8;
    const left=o?.x!=null?o.x-Math.floor(width/2):2+(i%3)*15;
    const top=o?.y!=null?o.y-Math.floor(height/2):2+Math.floor(i/3)*14;
    return {...p,x:105+(left-2)*15,y:275+(top-2)*12,w:width*15,h:height*12};
  });
}
export function rockRect(r, s) {
  const k = Math.min(790 / (s.width || 60), 430 / (s.height || 40));
  return {
    x: 85 + r.left * k,
    y: 140 + r.top * k,
    w: r.width * k,
    h: r.height * k,
  };
}
export function spriteFor(o = {}) {
  const raw = o.id || "",
    id = raw
      .replace(/^inventory_/, "")
      .replace(/^food_/, "")
      .replace(/^crop_/, "")
      .replace(/^recipe_/, "");
  if (
    o.type === "seed" ||
    o.resource_kind === "seed" ||
    o.item_kind === "seed" ||
    o.shop_kind === "seed" ||
    id.startsWith("seed_")
  )
    return (
      SPRITES["seed_" + (o.seed_id || o.item_id || id.replace(/^seed_/, ""))] ??
      5
    );
  if (o.recipe_id) return SPRITES[o.recipe_id] ?? 15;
  if (o.ingredient_id) return SPRITES[o.ingredient_id] ?? 0;
  if (o.seed_id) return SPRITES[o.seed_id] ?? 0;
  if (o.item_id) return SPRITES[o.item_id] ?? 9;
  if (SPRITES[id] !== undefined) return SPRITES[id];
  if (o.type === "research")
    return /seed/.test(id) ? 26 : /mine|pickaxe/.test(id) ? 8 : 28;
  if (o.type === "care_button")
    return /water/.test(id) ? 23 : /fert/.test(id) ? 4 : 0;
  if (o.type === "save_slot") return 27;
  if (o.type === "shop_choice") return /sell/.test(id) ? 3 : 5;
  return 24;
}
export function publicCards(s) {
  return (s.spectator?.objects || s.objects || [])
    .filter(
      (o) =>
        ![
          "route",
          "arrow",
          "growth_gauge",
          "plot_detail_field",
          "care_field",
          "care_target",
          "harvest_field",
          "harvest_crop",
          "plot",
          "mine_rock",
        ].includes(o.type),
    )
    .map((o) => ({
      ...o,
      description:
        (s.objects || []).find((x) => x.id === o.id)?.description ||
        o.label ||
        "",
    }));
}
export function snapshot(input) {
  return JSON.parse(JSON.stringify(input));
}
