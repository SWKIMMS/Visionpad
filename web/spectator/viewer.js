import {
  WORLD,
  SCENES,
  TITLES,
  SPRITES,
  phase,
  scene,
  plots,
  rockRect,
  spriteFor,
  publicCards,
  snapshot,
} from "./model.mjs";
const base = new URL(".", import.meta.url);
const css = document.createElement("link");
css.rel = "stylesheet";
css.href = new URL("viewer.css", base);
document.head.append(css);
const root = document.createElement("section");
root.className = "dotdew-observer";
root.setAttribute("aria-label", "Dotdew Valley visual companion");
root.innerHTML = `<header class="dv-heading"><div><div class="dv-eyebrow"><span class="dv-live"></span>Visual companion · read only</div><h2>Dotdew Valley</h2></div><div class="dv-tools"><button type="button" data-view="detach">Open window</button></div></header><div class="dv-stage"><canvas width="960" height="600" aria-label="Visual representation of the current game"></canvas><div class="dv-hud"><span class="dv-badge" data-place>Waiting for the game</span><span class="dv-badge" data-clock>Live view</span></div><section class="dv-menu" hidden><h3></h3><div class="dv-subtitle"></div><div class="dv-cards"></div></section><div class="dv-shade" hidden></div></div><footer class="dv-time-footer"><span class="dv-time-label">Activity time</span><div class="dv-time-gauge" role="progressbar" aria-label="Activity time used" aria-valuemin="0" aria-valuemax="20" aria-valuenow="0"><div class="dv-time-fill"></div></div></footer>`;
(document.querySelector(".container") || document.body).append(root);
const canvas = root.querySelector(".dv-stage>canvas"),
  ctx = canvas.getContext("2d");
ctx.imageSmoothingEnabled = false;
const sheets = {};
let sceneDefinitions={scenes:{}}, assetCatalog={backgrounds:{},facilities:{},objects:{},pages:{}};
const assetsReady=Promise.all([
 fetch(new URL('scene-objects.json?v=fishing-polish-4',base)).then(r=>{if(!r.ok)throw new Error('Scene registry unavailable');return r.json();}).then(d=>{sceneDefinitions=d;}),
 fetch(new URL('visual-assets.json?v=fishing-polish-4',base)).then(r=>{if(!r.ok)throw new Error('Asset registry unavailable');return r.json();}).then(async d=>{assetCatalog=d;await Promise.all(Object.entries(d.textures||{}).map(([name,url])=>new Promise(resolve=>{const i=new Image();i.onload=()=>{sheets[name]=i;resolve();};i.onerror=()=>resolve();i.src=new URL(url,base);})));})
]).catch(error=>{console.warn(error);}).then(()=>{menuKey='';if(state)updateUI();});
let animationFrame = 0;
let state = null,
  lastEnvelope = null,
  menuKey = "",
  message = "Explore at your own pace.",
  particles = [],
  history = [],
  lastEventAt = 0;
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const q = (s) => root.querySelector(s);
function text(s, x, y, color = "#baff91", size = 18) {
  ctx.font = `${size}px Georgia`;
  ctx.fillStyle = "#251e19bb";
  ctx.fillRect(x - 7, y - size - 3, ctx.measureText(s).width + 14, size + 12);
  ctx.fillStyle = color;
  ctx.fillText(s, x, y);
}
function drawAsset(asset,x,y,w,h,c=ctx,fit=true) {
 const i=sheets[asset?.texture];if(!i)return false;
 const r=asset.source||[0,0,i.width,i.height];c.imageSmoothingEnabled=false;
 const scale=fit?Math.min(w/r[2],h/r[3])*.92:1,dw=fit?r[2]*scale:w,dh=fit?r[3]*scale:h;
 c.drawImage(i,...r,x+(w-dw)/2,y+(h-dh)/2,dw,dh);return true;
}
function sprite(index,x,y,w=60,h=w,c=ctx) {
 const key=typeof index==='string'?index:Object.keys(SPRITES).find(k=>SPRITES[k]===index&&k!=='farmer');
 return drawAsset(assetCatalog.objects[key],x,y,w,h,c);
}
function objectArt(name, bounds) {
  const art=assetCatalog.facilities?.[name];if(!art)return;
  const image=sheets[art.texture];if(!image)return;
  const source=art.source||[0,0,image.width,image.height];
  const [x,y,w,h]=bounds, scale=Math.min(w/source[2],h/source[3]);
  const dw=source[2]*scale,dh=source[3]*scale;
  ctx.drawImage(image,...source,x+(w-dw)/2,y+h-dh,dw,dh);
}
function environment(name, x=0,y=0,w=960,h=600) {
  return drawAsset(assetCatalog.backgrounds[name],x,y,w,h,ctx,false);
}
function sceneObjects(name) {
  const config=sceneDefinitions.scenes[name];if(!config)return;
  environment(config.background);
  const gameObjects=state.spectator?.objects||state.objects||[];
  for(const object of [...config.objects].sort((a,b)=>(a.layer||0)-(b.layer||0))) {
    const linked=gameObjects.find(o=>o.id===object.game_id)||(object.game_type?gameObjects.find(o=>o.type===object.game_type):null);
    if(object.game_id&&!linked&&SCENES.includes(state.page))continue;
    objectArt(object.art,object.bounds);
    if(linked&&focused(linked.id)) {
      outline(...object.bounds,linked.id);
      text(linked.label,object.bounds[0]+8,object.bounds[1]+object.bounds[3]+18);
    }
  }
}
function currentPlot() {
  const id=state.page==='harvest'?state.harvest?.plot_id:state.plot_detail_id;
  return state.spectator?.plots?.find(p=>p.id===id)||state.farm_plots?.[id]||{};
}
function cropImage(plot,forceMature=false) {
  return forceMature||plot.mature ? (SPRITES['plant_'+plot.seed_id]??17) : plot.growth ? 17 : 16;
}
function background(name) {
  return drawAsset(assetCatalog.backgrounds[name],0,0,960,600,ctx,false);
}
function focused(id) {
  return state.hover_object === id;
}
function outline(x, y, w, h, id) {
  if (!focused(id)) return;
  ctx.strokeStyle = "#23170d";
  ctx.lineWidth = 10;
  ctx.strokeRect(x - 5, y - 5, w + 10, h + 10);
  ctx.strokeStyle = "#ff9a1a";
  ctx.lineWidth = 5;
  ctx.strokeRect(x - 5, y - 5, w + 10, h + 10);
}
function fence(x,y,w,h) {
  ctx.save();
  ctx.fillStyle='#312119';ctx.fillRect(x-5,y-5,w+10,10);ctx.fillRect(x-5,y+h-5,w+10,10);
  ctx.fillRect(x-5,y,10,h);ctx.fillRect(x+w-5,y,10,h);
  ctx.strokeStyle='#f1ce8b';ctx.lineWidth=5;ctx.strokeRect(x,y,w,h);
  const post=(px,py)=>{ctx.fillStyle='#412a1a';ctx.fillRect(px-6,py-10,12,22);ctx.fillStyle='#e7bb72';ctx.fillRect(px-3,py-8,6,18);};
  for(let px=x;px<=x+w;px+=38){post(px,y);post(px,y+h);}
  for(let py=y+32;py<y+h;py+=38){post(x,py);post(x+w,py);}
  ctx.restore();
}
function farm() {

  for (const p of plots(state)) {
    ctx.fillStyle = p.watered ? "#503d2c" : "#815532";
    ctx.fillRect(p.x, p.y, p.w, p.h);
    ctx.strokeStyle = "#cc5500";
    ctx.lineWidth = 4;
    ctx.strokeRect(p.x, p.y, p.w, p.h);
    ctx.fillStyle = p.watered ? "#3a3026" : "#624126";
    for (let y = 10; y < p.h; y += 20)
      ctx.fillRect(p.x + 6, p.y + y, p.w - 12, 3);
    if (p.seed_id) {
      const growth = p.growth || 0;
      const idx = cropImage(p);
      const sz = p.mature ? 57 : growth === 0 ? 29 : 34 + 20 * Math.min(1, growth / (p.growth_days || 3));
      for (let i = 0; i < 3; i++) {
        const x = p.x + 8 + (i % 3) * 58,
          y = p.y + 7 + Math.floor(i / 3) * 48;
        sprite(idx, x + (54 - sz) / 2, y + 50 - sz, sz);
      }
    }
    if (p.fertilized) {
      ctx.fillStyle = "#d6b465";
      for (let i = 0; i < 6; i++)
        ctx.fillRect(p.x + 10 + i * 29, p.y + p.h - 7, 3, 3);
    }
    fence(p.x-3,p.y-3,p.w+6,p.h+6);
    outline(p.x, p.y, p.w, p.h, p.id);
    text(
      `${p.id.replaceAll("_", " ")} · ${p.mature ? "Ready" : p.seed_id || "Empty"}`,
      p.x + 8,
      p.y + p.h - 9,
      "#baff91",
      16,
    );
  }
}
function mine() {
  for (const r of state.spectator?.rocks || []) {
    const b = rockRect(r, state);
    sprite(21, b.x, b.y, b.w, b.h);
    if (r.hits) {
      ctx.strokeStyle = "#302e39";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(b.x + b.w * 0.5, b.y + b.h * 0.22);
      ctx.lineTo(b.x + b.w * 0.4, b.y + b.h * 0.53);
      ctx.lineTo(b.x + b.w * 0.64, b.y + b.h * 0.75);
      if (r.hits > 1) ctx.lineTo(b.x + b.w * 0.32, b.y + b.h * 0.8);
      ctx.stroke();
    }
    outline(b.x, b.y, b.w, b.h, r.id);
  }
}
function fishing() {
  const f=state.fishing, g=f?.lake;
  if(!g)return;
  // Match the tactile lake coordinates inside the water part of scene3.
  const at=(x,y)=>[100+x/(state.width-1)*740,75+y/(state.height-1)*365];
  const pointer=state.pointer;
  if(pointer?.x!=null && pointer?.y!=null){
    const [x,y]=at(pointer.x,pointer.y);
    ctx.strokeStyle='#ffffff';ctx.lineWidth=3;
    ctx.beginPath();ctx.arc(x,y,9,0,Math.PI*2);ctx.stroke();
  }
  const last=f.last_catch;
  if(last){
    ctx.fillStyle='#162b22ed';ctx.fillRect(620,480,325,100);
    if(last.id)drawAsset(assetCatalog.objects[last.id],630,488,95,78);
    text(last.label, last.id?730:645,535,'#baff91',20);
  }
}
function facilities() {
  sceneObjects(state.page);
}

function map() {
  ctx.fillStyle = "#e3d4a6";
  ctx.fillRect(65, 90, 830, 450);
  const nodes = (state.spectator?.objects || []).filter(
    (o) => o.type === "node",
  );
  if (!nodes.length) return;
  const xs = nodes.map((n) => n.x),
    ys = nodes.map((n) => n.y),
    minX = Math.min(...xs),
    minY = Math.min(...ys),
    dx = Math.max(...xs) - minX || 1,
    dy = Math.max(...ys) - minY || 1;
  const at = (x, y) => [
    200 + ((x - minX) / dx) * 560,
    190 + ((y - minY) / dy) * 240,
  ];
  ctx.strokeStyle = "#8e8558";
  ctx.lineWidth = 7;
  for (const r of state.spectator?.routes || []) {
    ctx.beginPath();
    ctx.moveTo(...at(r.x1, r.y1));
    ctx.lineTo(...at(r.x2, r.y2));
    ctx.stroke();
  }
  for (const node of nodes) {
    const name = node.id.replace("map_", ""),
      [x, y] = at(node.x, node.y),
      i = sheets.scenes;
    if (name === "fishing") {
      drawAsset(assetCatalog.backgrounds.fishing,x-72,y-50,144,92,ctx,false);
    } else if (i) {
      const n = SCENES.indexOf(name),
        seam = i.height * 0.46875;
      ctx.drawImage(
        i,
        ((n % 2) * i.width) / 2,
        n < 2 ? 0 : seam,
        i.width / 2,
        n < 2 ? seam : i.height - seam,
        x - 72,
        y - 50,
        144,
        92,
      );
    }
    ctx.strokeStyle =
      focused(node.id) ? "#ff9a1a" : state.current_location === name ? "#baff91" : "#bd4e00";
    ctx.lineWidth = state.current_location === name ? 6 : 3;
    ctx.strokeRect(x - 72, y - 50, 144, 92);
    text(node.label, x - 40, y + 67, "#baff91", 18);
    if (state.current_location === name) text("You are here",x-44,y-63,"#baff91",16);
  }
}
function mini() {
  const page = state.page,
    cook = page === "cooking";
  if (!cook) environment("soil");
  else environment("kitchen");
  ctx.strokeStyle = "#d8b17d";
  ctx.lineWidth = 7;
  ctx.strokeRect(75, 95, 810, 450);
  const project = (x, y) => [
    95 + (x / (state.width || 60)) * 770,
    110 + (y / (state.height || 40)) * 415,
  ];
  if (cook) {
    const path = state.spectator?.path || [];

    ctx.lineWidth = 9;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (let i = 1; i < path.length; i++) {
      if (!path[i].visible && !path[i - 1].visible) continue;
      ctx.strokeStyle = path[i].passed ? "#9cad69" : "#f7e6b7";
      ctx.beginPath();
      ctx.moveTo(...project(path[i - 1].x, path[i - 1].y));
      ctx.lineTo(...project(path[i].x, path[i].y));
      ctx.stroke();
    }
    for (const point of [
      path[0]?.visible ? state.cooking?.start_point : null,
      state.cooking?.resume_point,
    ]) {
      if (!point) continue;
      const [x, y] = project(...point);
      ctx.fillStyle = "#fce7aa";
      ctx.fillRect(x - 10, y - 10, 20, 20);
    }
    text(
      `${state.cooking?.stage_label || "Cooking"} · ${state.cooking?.recipe_name || ""}`,
      95,
      82,
    );
  } else {
    const targets =
      page === "harvest"
        ? state.spectator?.harvest_targets
        : state.spectator?.care_targets;
    for (const t of targets || []) {
      if (!t.visible) continue;
      const [x, y] = project(t.x, t.y);
      ctx.globalAlpha = t.collected ? 0.4 : 1;
      const plot=currentPlot();
      if(t.collected && page!=='harvest') {
        ctx.fillStyle=page==='water_minigame'?'#355d6380':'#d8bb7160';
        ctx.beginPath();ctx.ellipse(x,y+19,31,10,0,0,Math.PI*2);ctx.fill();
      }
      sprite(cropImage(plot,page==='harvest'),x-31,y-34,62,62);
      ctx.strokeStyle=t.collected?'#bfe8ac':'#f2db9b80';ctx.lineWidth=2;
      ctx.beginPath();ctx.ellipse(x,y+22,24,7,0,0,Math.PI*2);ctx.stroke();
      ctx.globalAlpha = 1;
    }
  }
  const p = state.pointer;
  if (p && Number.isFinite(p.x) && Number.isFinite(p.y)) {
    const [x, y] = project(p.x, p.y);
    ctx.strokeStyle = p.pressed ? "#fffac6" : "#eeeeee90";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(x, y, 17, 0, Math.PI * 2);
    ctx.stroke();
    if (p.pressed) {
      sprite(
        cook
          ? state.cooking?.gesture_kind === "stir"
            ? 14
            : 1
          : page === "water_minigame"
            ? 23
            : page === "fertilizer_minigame"
              ? 4
              : 8,
        x + 12,
        y - 34,
        38,
      );
    }
  }
}
function detail() {
  const id=state.plot_detail_id,p=state.spectator?.plots?.find(p=>p.id===id);
  environment('soil');
  ctx.fillStyle='#332214dd';ctx.fillRect(75,337,810,213);

  for(let i=0;i<10;i++)if(p?.seed_id)
    sprite(cropImage(p),115+(i%5)*150,365+Math.floor(i/5)*72,70);
  text(`${id||'Plot'} · ${p?.seed_id||'Empty soil'}`,95,324,'#baff91',20);
  text(`${p?.watered?'Watered':'Needs water'} · ${p?.fertilized?'Fertilized':'No fertilizer'}`,95,580,'#baff91',18);
}

const renderers=new Set([...Object.keys(TITLES),"background"]);
function fallbackPage() {
 const spec=assetCatalog.pages?.[state.page];
 if(!spec||!renderers.has(spec.renderer))return true;
 if(spec.renderer==='background'){const a=assetCatalog.backgrounds[spec.background];return !a||!sheets[a.texture];}
 const bg=state.page==='cooking'?'kitchen':state.page.startsWith('shop_')?'shop':['plot_detail','water_minigame','fertilizer_minigame','harvest'].includes(state.page)?'soil':scene(state)==='home'?'room':scene(state)==='town'?'square':scene(state);
 const asset=assetCatalog.backgrounds[bg];
 return !asset||!sheets[asset.texture];
}
function tactileFallback() {
 const rows=state.dots||[],w=state.width||rows[0]?.length||60,h=state.height||rows.length||40;
 ctx.fillStyle='#162019';ctx.fillRect(0,0,960,600);
 const step=Math.min(840/w,440/h),ox=(960-w*step)/2,oy=100+(440-h*step)/2;
 for(let y=0;y<h;y++)for(let x=0;x<w;x++){
  ctx.fillStyle=rows[y]?.[x]?'#f0e9bd':'#2b382d';ctx.beginPath();ctx.arc(ox+(x+.5)*step,oy+(y+.5)*step,Math.max(1,step*.25),0,Math.PI*2);ctx.fill();
 }
 text('DotPad live view',ox,76,'#baff91',18);
}
function itemKey(o) {
 const id=(o.id||'').replace(/^inventory_/,'').replace(/^(food_|crop_|recipe_|ingredient_)/,'');
 const kind=o.resource_kind||o.shop_kind||o.item_kind||o.type;
 if(kind==='seed'||id.startsWith('seed_'))return 'seed_'+(o.seed_id||o.item_id||id.replace(/^seed_/,''));
 return o.recipe_id||o.ingredient_id||o.seed_id||o.item_id||id;
}
function itemFrame(o) {
 if(['oval','diamond','rectangle'].includes(o.frame_shape))return o.frame_shape;
 const kind=o.resource_kind||o.shop_kind||o.item_kind||o.kind;
 if(kind==='food'||o.type==='recipe'||o.recipe_id||/^inventory_food_/.test(o.id||''))return 'food';
 if(kind==='coin'||kind==='currency'||kind==='special'||/^inventory_coin$/.test(o.id||''))return 'diamond';
 return 'rectangle';
}
function itemSprite(o) {
 const key=itemKey(o);if(assetCatalog.objects[key])return key;
 // Only existing non-item controls retain their fixed interface images.
 if(['research','care_button','save_slot','shop_choice'].includes(o.type))return spriteFor(o);
 return null;
}
function render() {
  if (!state) return;
  if(fallbackPage()){tactileFallback();return;}
  const pageSpec=assetCatalog.pages[state.page];
  if(pageSpec.renderer==="background"){drawAsset(assetCatalog.backgrounds[pageSpec.background],0,0,960,600,ctx,false);return;}
  const loc = scene(state);
  background(loc);
  if (state.page === "farm") farm();
  else if (state.page === "mine") mine();
  else if (state.page === "fishing") fishing();
  if (loc === "home" || loc === "town") sceneObjects(loc);
  if (state.page.startsWith('shop_')) sceneObjects('shop');
  const ph = phase(state);
  ctx.fillStyle = ph.color;
  ctx.globalAlpha = ph.alpha;
  ctx.fillRect(0, 0, 960, 600);
  ctx.globalAlpha = 1;
  if (state.page === "minimap") map();
  if (
    ["cooking", "harvest", "water_minigame", "fertilizer_minigame"].includes(
      state.page,
    )
  )
    mini();
  if (state.page === "plot_detail") detail();
  if (state.sleeping) {
    ctx.fillStyle = "#11192c99";
    ctx.fillRect(0, 0, 960, 600);
  }
  drawParticles();
}
function drawParticles() {
  const now = performance.now();
  particles = particles.filter((p) => p.until > now);
  for (const p of particles) {
    const t = (p.until - now) / 1100;
    ctx.globalAlpha = Math.max(0, t);
    ctx.fillStyle = p.color;
    ctx.fillRect(p.x + p.dx * (1 - t), p.y - 60 * (1 - t), 5, 5);
    ctx.globalAlpha = 1;
  }
}
function burst(color = "#f6d786") {
  if (reduced) return;
  const pointer = state.pointer || {};
  let x = 480,
    y = 300;
  if (
    ["cooking", "water_minigame", "fertilizer_minigame", "harvest"].includes(
      state.page,
    )
  ) {
    x = 95 + ((pointer.x ?? 30) / (state.width || 60)) * 770;
    y = 110 + ((pointer.y ?? 20) / (state.height || 40)) * 415;
  } else if (state.page === "mine") {
    x =
      85 +
      (pointer.x ?? 30) *
        Math.min(790 / (state.width || 60), 430 / (state.height || 40));
    y =
      140 +
      (pointer.y ?? 20) *
        Math.min(790 / (state.width || 60), 430 / (state.height || 40));
  }
  for (let i = 0; i < 12; i++)
    particles.push({
      x,
      y,
      dx: (i - 6) * 12,
      color,
      until: performance.now() + 1100,
    });
  if (!animationFrame) animationFrame = requestAnimationFrame(frame);
}
function quantityBadge(label,value) {
  const b=document.createElement('span');b.className='dv-quantity';
  const n=document.createElement('b');n.textContent=String(value);
  const t=document.createElement('span');t.textContent=label;b.append(n,t);return b;
}
function appendQuantities(card,o) {
  const row=document.createElement('div');row.className='dv-quantities';
  if(Number.isFinite(o.count))row.append(quantityBadge('Owned',o.count));
  if(Number.isFinite(o.required_count))row.append(quantityBadge('Needed',o.required_count));
  if(Number.isFinite(o.price))row.append(quantityBadge('Gold',o.price));
  if(row.childNodes.length)card.append(row);
  for(const cost of o.display_quantities||[]) {
    const line=document.createElement('div');line.className='dv-cost';
    const c=document.createElement('canvas');c.width=c.height=48;sprite(cost.item,0,0,48,48,c.getContext('2d'));
    line.append(c,quantityBadge('Needed',cost.required),quantityBadge('Owned',cost.owned));card.append(line);
  }
}
function menus() {
  const show =
    !fallbackPage() && (renderers.has(state.page)||assetCatalog.pages[state.page]?.items===true) && !SCENES.includes(state.page) &&
    ![
      "minimap",
      "cooking",
      "water_minigame",
      "fertilizer_minigame",
      "harvest",
    ].includes(state.page);
  const menu = q(".dv-menu");
  menu.hidden = !show;
  if (!show) return;
  const cards = publicCards(state),
    key = JSON.stringify([
      state.page,
      cards,
      state.hover_object,
      state.resources,
      state.cooking?.selected_ingredients,
    ]);
  if (key === menuKey) return;
  menuKey = key;
  root.dataset.page=state.page;
  menu.style.left=state.page.startsWith('shop_')?'3%':'';
  menu.style.right=state.page.startsWith('shop_')?'28%':'';
  q(".dv-menu h3").textContent = TITLES[state.page] || state.page_name;
  q(".dv-subtitle").textContent =
    state.page === "inventory"
      ? `Page ${state.inventory?.page || 1} of ${state.inventory?.pages || 1}`
      : state.page === "ingredient_select"
        ? "Following the player’s ingredient selection"
        : state.page === "load_game"
          ? "Saved slots · viewing only"
          : "Player selection";
  const grid = q(".dv-cards");
  grid.replaceChildren();
  grid.style.gridTemplateColumns = ['research','recipe_select','ingredient_select'].includes(state.page)?'repeat(3,minmax(0,1fr))'
    :state.page==='plot_detail'?'repeat(3,minmax(0,1fr))'
    :state.page==='shop_choice'?'repeat(2,minmax(0,1fr))':'repeat(4,minmax(0,1fr))';
  // Use actual tactile row/column order, including sparse final rows.
  const xs=[...new Set(cards.map(o=>o.x).filter(Number.isFinite))].sort((a,b)=>a-b);
  const ys=[...new Set(cards.map(o=>o.y).filter(Number.isFinite))].sort((a,b)=>a-b);
  grid.style.gridTemplateRows=['inventory','shop_buy','shop_sell','load_game'].includes(state.page)?'repeat(3,minmax(0,1fr))':'';
  for (const o of cards) {
    const card = document.createElement("article");
    card.className =
      "dv-card" +
      (focused(o.id) ? " is-focused" : "") +
      (o.selected ? " is-selected" : "");
    card.dataset.objectId = o.id;
    if(['research','inventory','shop_buy','shop_sell','plot_detail'].includes(state.page)&&xs.length&&ys.length){
      card.style.gridColumn=String(xs.indexOf(o.x)+1);card.style.gridRow=String(ys.indexOf(o.y)+1);
    }
    card.dataset.category=itemFrame(o);
    card.dataset.frame='rectangle';
    const c=document.createElement('canvas');c.width=c.height=80;
    const key=itemSprite(o),hasArt=key!==null&&sprite(key,0,0,80,80,c.getContext('2d'));
    const title=document.createElement('strong');title.textContent=o.label||itemKey(o);
    if(hasArt){
      const top=document.createElement('div');top.className='dv-item-top';top.append(c);card.append(top,title);
      appendQuantities(card,o);
      const description = ['shop_buy','shop_sell','ingredient_select'].includes(state.page) ? '' : (o.effect_description || '');
      if(description){const small=document.createElement('small');small.textContent=description;card.append(small);}
    }
    else {card.classList.add('dv-placeholder');card.append(title);}
    grid.append(card);
  }
  if (!cards.length) {
    const empty = document.createElement("p");
    empty.textContent = "Nothing to display on this page.";
    grid.append(empty);
  }
}
function drawTimeGauge() {
  const gauge=q('.dv-time-gauge');
  const total=Math.max(1,Number(state.time?.total_cells)||20);
  const used=Math.max(0,Math.min(total,Number(state.time?.used_cells)||0));
  q('.dv-time-fill').style.width=`${100*used/total}%`;
  gauge.setAttribute('aria-valuemax',String(total));
  gauge.setAttribute('aria-valuenow',String(used));
  gauge.setAttribute('aria-valuetext',`${used} of ${total} used`);
}
function updateUI() {
  const ph = phase(state);
  q("[data-place]").textContent =
    TITLES[state.page] || state.page_name || "Dotdew Valley";
  q("[data-clock]").textContent =
    `Day ${state.day} · ${ph.name} · ${state.resources?.coin ?? 0} gold`;
  drawTimeGauge();
  const shade = q(".dv-shade");
  shade.hidden = !state.sleeping && !state.paused;
  shade.replaceChildren();
  if (!shade.hidden) {
    const title = document.createElement("div");
    title.textContent = state.sleeping
      ? "Resting until morning…"
      : "Game paused";
    const small = document.createElement("small");
    small.textContent = state.sleeping
      ? "☾  ·  ✦  ·  ☾"
      : "The adventure will resume with the player";
    title.append(small);
    shade.append(title);
  }
  menus();
  render();
}
export function receive(envelope) {
  if (!envelope?.state) return;
  const packet = snapshot(envelope),
    prev = state;
  state = packet.state;
  lastEnvelope = packet;
  if (packet.message) message = packet.message;
  else if (prev?.page !== state.page)
    message = TITLES[state.page] || state.page_name;
  const changedDay = prev && prev.day !== state.day;
  if (changedDay) {
    message = `A new morning. Day ${state.day}.`;
    burst("#ffe9a3");
  }
  for (const e of packet.events || []) {
    if (e.kind === "correct") burst();
    else if (e.kind === "item_destroyed") burst("#ef986c");
    else if (e.sound === "shine" || e.reward_sound === "shine")
      burst("#9cedff");
    else if (e.sound !== "step") burst("#e7c88a");
  }
  updateUI();
}
let channel = null;
const isDetached = document.body.dataset.spectator === "standalone",
  isDemo = document.body.dataset.spectator === "demo";
let session = new URL(location.href).searchParams.get("session");
if (!isDetached && !isDemo)
  session = crypto.randomUUID?.() || String(Date.now());
try {
  if (!isDemo) channel = new BroadcastChannel("dotdew-view-" + session);
} catch {}
if (channel)
  channel.onmessage = (e) => {
    if (isDetached && e.data?.kind === "snapshot") receive(e.data.payload);
    else if (!isDetached && e.data?.kind === "request" && lastEnvelope)
      channel.postMessage({ kind: "snapshot", payload: lastEnvelope });
  };
function relay(data) {
  receive(data);
  if (channel && !isDetached)
    channel.postMessage({ kind: "snapshot", payload: lastEnvelope });
}
if (!isDetached && !isDemo) {
  window.addEventListener("dotdew-state", (e) => relay({ state: e.detail }));
  window.addEventListener("dotdew-observer", (e) => relay(e.detail));
  const initial = window.DotdewInput?.state?.();
  if (initial) relay({ state: initial });
}
if (isDetached || isDemo) {
  q('[data-view="detach"]').hidden = true;
  channel?.postMessage({ kind: "request" });
}
q('[data-view="detach"]').onclick = () => {
  window.open(
    new URL("standalone.html?session=" + encodeURIComponent(session), base),
    "dotdew-visual-" + session,
    "width=1150,height=850",
  );
};
function frame(now) {
  animationFrame = 0;
  if (document.hidden) {particles = []; return;}
  render();
  if (particles.length) animationFrame = requestAnimationFrame(frame);
}
export const ready = assetsReady;
