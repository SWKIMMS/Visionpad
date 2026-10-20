# Dotdew Valley

English | [한국어](README.ko.md)

A farming and life simulation game for the Dot Pad. Players farm, cook, mine, trade, and research upgrades across four locations: home, farm, village, and mine. The activities draw on Stardew Valley, with each task adapted to a 60×40 tactile display.

The browser simulator supports mouse and keyboard input. A USB Dot Pad and an external hand-tracking system can also be connected. A separate Visual Companion window shows the same game state using images.

## Design

The project explores how blind and low-vision players can understand a game world through touch and sound, then act directly on the surface they are reading. Shapes and speech provide guidance without requiring Braille literacy.

| Channel | Use |
|---|---|
| Touch | Position, shape, layout, paths, and progress |
| Speech and sound | Names, quantities, states, and action results |
| Visual display | Images, quantities, and selection highlights for low-vision players and companions |
| Buttons | Navigation, menus, saving, loading, and selection |
| Pointer and hand gestures | Selecting, sweeping, tracing, and tapping |

Exploration and travel cost no game time. Moving over an object and pressing it are separate inputs, so reading the display does not trigger an action.

Farming, cooking, mining, trading, research, fishing, and one authored NPC conversation are implemented. Ranching, music activities, quests, and crafting are planned. The controls below describe the current build; some differ from the initial proposal.

## Running the game

For the first setup, install Python 3.11 or newer and open **setup-mac.command** on Mac or **setup-windows.bat** on Windows. These create a project environment, install the dependencies and download the Bluetooth SDK and both voices. Internet is needed for that setup. For later starts, open **start-mac.command** or **game.bat**. The launcher checks the setup, waits for the server, prepares demo voices and opens the game. An existing game on the selected port is reused without a restart. See the [setup and handoff guide](docs/audio/SETUP.md).

For manual setup, create a Python environment and install the dependencies from the project root.

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

python -m pip install -r requirements.txt
python tools/prepare_pad.py
python tools/prepare_speech.py --download
python launch_game.py --prepare-demo
```

The Mac launcher and manual command default to `http://127.0.0.1:8000`. Windows `game.bat` preserves its existing port, `http://127.0.0.1:8003`. Use the address printed by the launcher. Serve the HTML through the local server rather than opening it directly.

1. Click or press a key on the game page to enable audio.
2. Use the mouse and keyboard, or connect the USB pad and hand-tracking server.
3. Select **Open visual display** to open the companion window. Allow pop-ups for the site if needed.
4. Keep the original game page open while using the companion.

Restart the server after changing the configuration. After replacing web files, hard-refresh the game page and reopen the companion window.

Python 3.12 (64-bit) is recommended for a new installation. The launchers recognize `.venv/` and `venv/`. Settings use UTF-8 on both platforms; setup verifies voice downloads and replaces damaged files. Run `python tools/check_setup.py --synthesize` from the active environment to check files, packages and both voices. See **Audio setup** in GitHub Actions for Windows and Mac installation checks.

## English voices and Rowan

The October 18 update adds server-side cancellation/priority, one-time Rowan reactions to recent results, and directional beacons for farm and mine targets. Toggle **Target cues on/off** to compare them; fishing guidance is unchanged. See [gameplay changes and verification](docs/audio/GAMEPLAY_UPDATE.md). Reactions remember the latest real result and survive saves; older saves use general reactions because their earlier milestones are unknown.

Speech uses Piper on the Python server with fixed English models, rather than the operating system's browser voices. The first setup command above downloads the two models to `models/piper/` and prepares sample audio. These files and generated speech in `.cache/speech/` are excluded from Git. No speech-service account or API key is needed for this implementation. A first request generates audio; repeated requests reuse the saved WAV. The first model load and a new sentence can take longer than cached playback.

- **Test guide** plays button instructions; **Test Rowan** plays the shopkeeper's voice.
- **Replay** repeats the current NPC line during a conversation, or the latest announcement elsewhere. **Stop speech** skips the current line. **Speech on/off** and **Speech rate** control speech separately from game sounds.
- **Speech volume** starts at 85% and changes only speech, including Rowan. **Sound volume** continues to control game sounds. Changing speech volume during a line does not restart it or regenerate audio. Reloading resets speech volume to 85%.
- In **Shop**, select **Ask Rowan for advice**. Choose **Farming**, **Fishing**, **Open shop**, or **Goodbye**. Advice follows the current crops and rod ownership. Advice and replay spend no game time or resources. The village Rowan keeps the team's soup, seeds and crop-submission tutorial.
- Music drops to 25% of its normal gain while speech plays and returns afterward. Hover descriptions wait behind action results and dialogue. Fishing retains its existing HRTF positioning and full exploration-sound gain during speech.
- Leaving the game window silences speech and game sounds, including delayed responses. Returning restores ambient music and lake guidance for the current screen, while keeping mute settings. Old speech and one-shot effects do not replay automatically; delayed text remains available in the caption and with **Replay**.
- Changing scenes cancels old task, target, transaction, and deferred mining sounds. The sleep recording still continues into the next morning. Failed sound assets can retry on a later action or state update after a one-second cooldown; old effects are not replayed.

Voice models and sample sentences are in `speech_config.json`; authored dialogue is in `npc_config.json`. Run `python tools/prepare_speech.py` to regenerate previews in `output/audio/`, or `python tools/speech_inventory.py` to refresh the source sentence inventory. See [the sound map and model sources](docs/audio/SOUND_MAP.md), [team handoff](docs/audio/TEAM_HANDOFF.md). The prototype models use the dataset license listed in their linked model cards (CC BY NC SA 4.0); Piper is GPL 3.0 or later.

Before a demo, keep the game server running and run `python tools/prepare_demo.py` in a second terminal. It prepares fixed guidance, Rowan tutorial and advice branches and representative action/object/reaction announcements through the speech API, without changing player progress. At the current revision it prepares 203 lines at speed 1.0; other rates, changing quantities and save timestamps may still need first-time generation. The report is `output/audio/demo-ready.json`. See [demo preparation and verification](docs/audio/DEMO_READY.md).

Software checks for this update: `python -m unittest test_team_audio test_speech_queue test_speech_api test_gameplay_audio test_speech test_fishing test_sound_events test_audio_flow test_demo_speech test_startup -v` and `node --test test_speech.cjs test_guidance.cjs test_fishing_audio.cjs test_effects.cjs test_audio_integration.cjs test_hardware.mjs` (147 tests total). `python tools/audio_flow.py` records a farming, cooking, NPC/trading, mining, fishing, save/load sequence in temporary progress. For a separate browser check, run `python tools/audio_integration_lab.py` and open `http://127.0.0.1:8001/`; it starts a temporary watering scene and does not use the normal game's progress. See the [integration report](docs/audio/INTEGRATION_REPORT.md) for coverage and fixture differences.

The user accepted the first voices and gave a positive initial assessment of direction cues and effects balance, requesting slightly quieter speech. The 85% speech level implements that feedback. Detailed direction/listening results, pronunciation, another computer, and a physical Dot Pad still require further checks; follow the [listening checklist](docs/audio/LISTENING_CHECK.md).

## Controls

| Input | Action |
|---|---|
| Hover | Hear an object's name and state |
| Click | Select, use a facility, or strike a rock |
| Move over targets or paths | Water, fertilize, harvest, or trace a cooking path |
| F1 | Open the minimap; press again in that menu to return to the current location |
| F2 | Open inventory; press again in that menu to return to the current location |
| F3, short press | Open or close the save list |
| F3, hold | Save to a new slot after about 0.8 seconds; stay on the current screen after `Game saved.` |
| F4 | Select at the pointer (current evaluation mapping) |
| Left/right arrow keys or pad buttons | Travel, go back, or turn a page, depending on the screen |
| W / A / S / D | Move the pointer while the game canvas has focus |
| Shift + W / A / S / D | Move the pointer in larger steps |
| Enter | Select at the pointer position |
| Space | Toggle pressed/released input |

Locations run from left to right: **Farm ↔ Home ↔ Village ↔ Mine**. Travel announces the destination. A direction with no route produces an unavailable-direction message.

Either arrow closes the minimap, inventory, or load screen and returns to the current location. Going back from buying or selling returns to the shop's buy/sell selection screen. Shop page-turn commands remain separate. Use the on-screen previous/next items to turn inventory pages.

Hand tracking supplies coordinates and press state from an external device. A server that sends coordinates only requires the press button or F4 for object selection; farming and cooking use movement alone. The Dot Pad does not detect touch coordinates itself. Guidance uses English speech; a new action announcement replaces the previous one, while hover descriptions wait for an action result or dialogue to finish.

## Locations and activities

| Location | Activities |
|---|---|
| Home | Sleep, research, and cook |
| Farm | Plant seeds, water, fertilize, check growth, and harvest |
| Village | Buy and sell; travel to home or the mine |
| Mine | Break rocks with a pickaxe and collect minerals |

Crops can be sold or cooked. Minerals can be traded or spent on research. Research adds plots and improves seed recovery and mineral drops. Food is consumed from inventory to apply an effect.

### Time and sleep

Time advances when activities finish. The current configuration gives each day 20 ticks. Travel costs 0; planting, watering, and fertilizing cost 2; harvesting, research, and cooking cost 3. Mining costs 4 ticks when a rock breaks, rather than on every hit.

When the daily allowance runs out, the player returns home. During sleep, the tactile panels briefly turn off and background music pauses. The sleep sound plays once and continues to its end after the next day begins. The pad uses a lower tactile time panel; the companion uses a thin orange bar that fills as time is spent.

### Farming

Select a plot to open its management screen. Empty plots accept seeds; planted plots show growth, water, and fertilizer status. On the farm, the plot fills from the bottom as the crop grows. The detail screen provides growth information and care buttons.

Watering and fertilizing use press-and-drag targets. Completion follows `care_minigame.success_ratio`. If the threshold has not been reached, the player can continue over the remaining targets. Watered crops grow after sleep. Fertilizer advances growth immediately.

Harvesting requires every target. Yield comes from the crop's base amount and the active food effect, with no minigame-score multiplier. Seed recovery uses the crop's base chance or its research level.

### Cooking and food

Choose a recipe and select all required ingredients to start cooking. Complete the chopping path and the second path in order. Ingredients and time are spent when both stages are complete. There is no time limit. A marker shows where to resume after progress stalls, and passed sections disappear after a configured delay.

| Food | Ingredients | Effect | Duration |
|---|---|---|---|
| Tomato carrot stew | Tomato, carrot | Harvest boost | 6 hours |
| Potato tomato soup | Potato, tomato | Pickaxe protection | 10 hours |
| Vegetable fritters | Potato, carrot | Time saving | 10 hours |

Durations use game time. The second path for vegetable fritters has eight petals. Food is used from inventory, with one effect active at a time. Eating another dish replaces the effect. Its duration decreases as game time is spent. Player-facing descriptions show the effect and duration without detailed multipliers.

### Shop and inventory

The shop sells seeds, fertilizer, pickaxes, and selected minerals, and buys crops, food, and minerals. Only one pickaxe can be held at a time. Buy another when it breaks.

Inventory hides zero-count items and shows up to 12 items per page. Tactile frames distinguish food with an oval, gold with a diamond, and other items with rectangles and category symbols. The companion uses rectangular cards throughout, with colored borders and the name, quantity, and price below the image.

### Mining and research

Up to seven rocks are placed each day, with gaps between them. A rock normally takes three hits to break. Damage reduces the density of its internal dots using fixed patterns; the outline remains readable.

Rocks drop stone, copper, iron, or diamonds. Research can add bonus drops. Pickaxe durability is handled internally and is not shown as a player-facing value. When a tool breaks, the shared destruction sound replaces the normal hit sound.

| Research | Materials | Effect |
|---|---|---|
| Seed recovery | Gold, copper | Improve seed recovery |
| Farm expansion | Gold, stone | Increase plots from two to six |
| Mineral luck | Gold, iron | Improve mineral drops and bonus quantities |

Research uses three cards per row. There is no harvest-yield research upgrade.

## Code structure

The server owns game state and action checks. The browser sends input and receives dot frames, public state, speech, and sound events. Mouse, keyboard, and device input share move, press, drag, and release events.

### Game and server

| File | Responsibility |
|---|---|
| `game_app.py` | FastAPI server, game page, static files, input and state APIs |
| `game_engine.py` | Locations and activities, game rules, resources, time, tactile rendering, and announcements |
| `game_ui.py` | Keypad navigation, temporary menus, tactile frames, and category icons |
| `game_saves.py` | State serialization, save files, loading, and slot management |
| `game_npc.py`, `npc_config.json` | Rowan's conversation state, authored lines, and game-state advice |
| `game_speech.py`, `speech_config.json` | Fixed voice models, pronunciation rules, and cached WAV generation |
| `dotpad.py` | Dot matrices and drawing primitives |
| `spectator_state.py` | Public object, plot, rock, path, and quantity data for the companion |
| `game_config.json` | Rules, starting resources, activity settings, audio, and layout data |

### Browser, hardware, and audio

| File | Responsibility |
|---|---|
| `web/game.html` | Pad simulator, pointer input, status, speech controls, and companion connection |
| `web/game-speech.js` | Speech playback, replay, cancellation, priority, and audio ducking callbacks |
| `web/game-keys.js` | Function and arrow keys, F3 short/long press, repeat suppression, and cancellation |
| `web/hardware.mjs` | Web Serial pad output and physical buttons; WebSocket hand coordinates |
| `web/game-audio.js` | Separate music, action, reward, and one-shot sound channels |
| `web/audio/` | MP3 assets |
| `game.bat`, `launch_game.py` | Windows startup and server/browser launch helpers |

### Visual Companion

The companion is a separate, read-only window under `web/spectator/`. It follows locations, selections, minigames, time of day, and sleep. Clicking this window does not change game state.

| File | Responsibility |
|---|---|
| `standalone.html` | Companion window entry point |
| `viewer.js` | Scene, card, object, and effect rendering source |
| `model.mjs` | Convert game state into visual layout data |
| `viewer.css` | Cards, quantities, colors, selection highlights, and time bar |
| `display.js` | Runtime bundle loaded by the page |
| `build_display.py` | Build `display.js` from the source files |
| `visual-assets.json` | Background, facility, item, and sprite-region registry |
| `scene-objects.json` | Facility positions, sizes, and draw order |
| `assets/` | Images including `scenes.png`, `scenes2.png`, `facilities.png`, `items.png`, and `extras.png` |

Each plot and rock corresponds to a game object. Individual farm plots have fences. The shop places its catalog on the left and the merchant and counter on the right. Inventory and shop pages fit their items without scrolling.

Backgrounds, facilities, and objects have separate asset entries so existing images can be reused. A page without a visual renderer falls back to the dot display. An unregistered item shows its name in a frame. Rebuild `display.js` after editing its source files.

## Saving and loading

Holding F3 saves before the key is released. Releasing it after a save does not open the load screen. A short press opens the slot list.

Saves are JSON files in `saves/`; the latest 12 are retained. They restore progress including items, gold, day, plots, research, food effects, and NPC visits. Older saves receive empty NPC state. Save files are excluded from version control. Server memory resets on restart, so save and load to continue a session. USB connections, camera calibration, and speech-control settings are separate from game saves.

## Audio

| Asset | Use |
|---|---|
| `background-basic`, `background-minigame`, `background-shop` | Music for the three page groups |
| `water`, `soil`, `crop` | Watering, fertilizing, harvesting |
| `cut`, `cook` | Chopping and stirring |
| `correct` | Target progress and ordinary loot feedback |
| `step`, `door`, `coin` | Travel, shop entry, transactions, and paid research |
| `sleep` | Sleep transition |
| `pickaxe`, `break`, `shine`, `destroy` | Hits, broken rocks, diamonds, and broken items |

Assets use matching MP3 names in `web/audio/`. Reward sounds do not interrupt action sounds. Moving within the same music group does not restart the track. Speech uses server-generated English audio and has separate controls from game audio.

Recorded action sounds and short outcome cues now share `GameAudio`: target progress, task completion, unavailable actions and fishing misses have distinct feedback. Held work avoids overlapping its tap recording, and TTS cannot revive idle chopping or stirring. Recorded doors, footsteps and coins suppress duplicate synthetic cues. Music is quieter, low-level crop and rare-reward recordings are amplified, and one-shot effects also reduce during speech. Original MP3 files are unchanged. Run `python tools/prepare_effects_preview.py` (requires FFmpeg and Node) for a labelled 37-second mono effects reel in `output/audio/effects-preview.wav`; it does not reproduce live mixing or HRTF.

## Configuration

Edit `game_config.json` and restart the server. Values below reflect the current configuration.

Time uses game ticks, `_ms` values use milliseconds, probabilities use 0–1, and coordinates use dot units. Engine-side limits are noted below the tables.

### Rules and starting state

| Path | Setting / current value |
|---|---|
| `game.start_day` | Starting day: 1 |
| `resources` | Starting gold, fertilizer, seeds, and crops; three of each crop for cooking tests |
| `time.total_cells` | Daily allowance: 20 |
| `time.action_costs` | Costs for `travel`, `plant`, `water`, `fertilize`, `harvest`, `research`, `cook`, and `mine` |
| `seeds.<id>.growth_days`, `yield` | Growth days and base yield |
| `seeds.<id>.seed_price`, `crop_price` | Seed purchase and crop sale prices |
| `seeds.<id>.seed_return_chance` | Base seed recovery chance: 0.1 for each crop |
| `fertilizer.growth_day_bonus` | Immediate growth advance: 1 day |
| `shop.fertilizer_price` | Fertilizer price: 12 |
| `recipes.<id>.ingredients` | Ingredient IDs and amounts |
| `recipes.<id>.buff_kind` | `harvest_multiplier`, `pickaxe_protection`, or `time_slow` |
| `recipes.<id>.buff_multiplier`, `buff_ticks` | Effect multiplier and duration |
| `recipes.<id>.gesture_steps` | Per-stage `kind`, `path`, and `tolerance` |
| `research.seed_return` | `costs`, `copper_costs`, `return_chances`, `max_level` |
| `research.field_expansion` | `initial_plot_count`, `costs`, `stone_costs` |
| `research.mineral_luck` | `costs`, `iron_costs`, `max_level`, `diamond_weight_per_level`, `double_drop_chance_per_level` |

Farm expansion costs `[30, 50, 70, 90]` gold and `[5, 10, 15, 20]` stone, adding four plots to the initial two. Seed recovery research uses `[0.3, 0.6]`. These are development settings; detailed probabilities are not announced during play.

### Minigames and feedback

| Path | Setting / current value |
|---|---|
| `care_minigame.target_count`, `target_positions` | Watering/fertilizing target count and candidate positions |
| `care_minigame.tolerance` | Target hit tolerance |
| `care_minigame.success_ratio` | Completion threshold: 0.65; use 1.0 to require every target |
| `harvest_minigame.target_count`, `target_positions` | Harvest target count and candidate positions; all targets are required |
| `interaction.feedback.disappear_delay_ms` | Delay before care targets and cooking paths disappear: 200; use 1000 for one second |
| `interaction.feedback.visual_refresh_interval_ms` | Delayed-feedback refresh interval: 100; engine minimum 50 |
| `interaction.cooking.resume_marker_delay_ms` | Delay before the resume marker appears: 400 |
| `interaction.cooking.stir_scale` | Stirring path scale: 1.6, limited to the display bounds |
| `interaction.inventory.items_per_page` | Items per page: 12; engine range 1–12 |
| `interaction.inventory.hide_zero_items` | Hide empty items: `true` |
| `interaction.sleep.blackout_ms` | Sleep blackout and input wait: 2000 |

Harvest tolerance is fixed at 3.5 in the engine and does not follow `harvest_minigame.tolerance`. Adjust the F3 hold threshold through `holdMs` in `web/game-keys.js`.

### Mining and prices

| Key under `mine` | Setting / current value |
|---|---|
| `daily_rock_limit` | Daily rocks: 7; also capped at 7 by the engine |
| `rock_width`, `rock_height`, `rock_gap` | Rock size and spacing: 10, 10, 5 |
| `hits_to_break` | Hits per rock: 3 |
| `pickaxe_price_multiplier` | Pickaxe price relative to fertilizer: 5 |
| `pickaxe_safe_hits`, `pickaxe_break_increment` | Safe-hit threshold and subsequent break-chance increment: 9, 0.05 |
| `loot_weights` | Diamond 1, iron 15, copper 34, stone 50 |
| `mineral_sell_multipliers` | Mineral sale-price multipliers relative to the reference crop price |
| `mineral_sell_price_bonus` | Added sale price: 3 |
| `mineral_buy_multiplier` | Purchase price relative to sale price: 2 |

### Volume and playback

All keys below are under `interaction.audio`. Gains multiply the source level; the quiet crop and shine recordings use gains above 1. Check the source loudness and the combined game mix when adjusting them.

| Key | Setting |
|---|---|
| `default_volume` | Master game-audio volume: 0.9 |
| `bgm_gain.basic`, `minigame`, `shop` | Music gains: 0.30, 0.20, 0.45 |
| `bgm_during_tts` | Music gain multiplier during speech; defaults to 0.25 |
| `one_shot_during_tts` | Recorded one-shot and synthetic cue multiplier during speech: 0.65 |
| `hover_interval_ms` | Minimum interval between hover tones: 220 ms |
| `work_gain` | Per-action gains for `water`, `soil`, `crop`, `cut`, and `cook` |
| `work_gain_during_tts` | Action gains during speech |
| `reward_gain`, `reward_gain_during_tts` | Reward gains normally and during speech |
| `one_shot_gain` | Per-sound gains for sleep, entry, transactions, mining, and destruction |
| `one_shot_gain_links` | Shared settings; `step` uses `door` |
| `cooking_correct_interval_ms`, `other_correct_interval_ms` | Minimum reward intervals: cooking 650, other activities 90 |
| `click_duration_ms` | Short click-sound duration: 650 |
| `motion_idle_ms`, `motion_check_interval_ms` | Cooking movement timeout and check interval |
| `correct_max_load_age_ms`, `max_reward_sources` | Stale-reward cutoff and simultaneous reward limit |
| `bgm_minigame_pages`, `bgm_shop_pages` | Page IDs assigned to each music group |

### Layout and images

`dotpad` and `time.bar` define panel dimensions. `home`, `farm`, `town`, and `minimap` contain base layouts. The engine normalizes some screens to fixed grids and English names, so changing a coordinate or `label` may not directly change the rendered screen. Check the device dimensions and engine layout code when modifying these settings.

Companion positions and sizes belong in `scene-objects.json`; image registration belongs in `visual-assets.json`; card sizes and colors belong in `viewer.css`.

## Planned work and evaluation

User testing will examine game comprehension and enjoyment, the workload of tactile and spoken information, and the usability and accuracy of hand gestures.

- Improve coordinate calibration, jitter and occlusion handling, and the separation of exploration from action input.
- Measure and reduce input queues, state-transfer delays, and rendering delays on older laptops.
- Expand NPC dialogue and add ranching, music activities, quests, and crafting.
- Evaluate task completion, time, errors, comprehension, workload, and gesture accuracy with approximately six to eight visually impaired participants.

User testing has not yet been conducted. Physical pad refresh speed, tracking under different lighting and camera positions, occlusion, and speech quality remain part of the planned evaluation. The current design assumes usable hearing and hand control.

## Fishing update

Travel order: Farm ↔ Home ↔ Village ↔ Mine ↔ Fishing lake. Buy one fishing rod at the shop before entering the lake. Default price: 75 gold (1.25 times the pickaxe price). Five casts are safe; break chance increases by 10 percentage points per cast from cast six. Misses count. The breaking cast still grants its catch.

Move the mouse or tracked finger toward the looping water sound, then press inside the tactile lake outline to cast. The source is positioned relative to the pointer using HRTF spatial audio, with increasing volume near the target. Use stereo headphones. Each valid cast costs 4 ticks, including a miss, and places the next target at a new position. Holding or dragging does not repeat casts. Clicking outside the lake costs nothing.

Eight fish use the existing items2 atlas: Sardine, Carp, Mackerel, Bass, Catfish, Flounder, Salmon and Rainbow trout. Fish are stored in inventory and can be sold. Grilled fish, fish stew and fried fish are available. Rarity is not spoken or displayed. Coin marks a middle-distance cast; shine marks a near cast, regardless of its reward.

Rules are in `game_fishing.py`, integrated by `game_engine.py`. `game_config.json` contains `fishing.rod_price_multiplier`, `near_radius` (4), `middle_radius` (10), `zone_weights`, and each fish's label, internal grade and sell price. Far/middle/near weights for miss/low/medium/high are 30/40/20/10, 10/30/40/20 and 10/20/30/40. Species within each grade are equally likely. `time.action_costs.fish` controls the cast cost.

`interaction.audio.fishing` controls max_gain (0.28), min_gain (0.025), distance_scale (22), position_scale (10), tts_multiplier (0.55) and bgm_multiplier (0.2). Pointer movement updates sound locally without waiting for a server response. The companion uses scene3's lake and items2's fish; the rod uses the existing name-only placeholder.

Apply the project files, keep your existing saves and virtual environment, restart the server, and hard-refresh both windows. Pre-fishing saves receive empty fish inventory and no rod without resetting other progress.

Validation: `python -m unittest test_fishing -v`, `node test_fishing_audio.cjs`, `node test_hardware.mjs`, plus API and asset-response checks. Physical device output, headphone listening and live browser rendering were not verified in this environment.

## Seafood recipes

Choose one owned fish and the vegetable ingredient in the existing ingredient screen. Cooking starts after both selections and consumes ingredients only after both paths finish. Only fish listed in a recipe’s allowed_fish are accepted. Rarity names and numerical multipliers are not narrated.

- Grilled fish: fish + potato; horizontal zigzag preparation, then one full large square. Boosts iron, diamond and high-grade fish weights by 1.5/2/2.5 for 12/14/16 ticks.
- Fish stew: fish + tomato; fish preparation, then the existing stirring path. Raises all selling prices by 25/50/75 percent (rounded down) for 3/4/5 successful sales. Failed sales and purchases do not use a charge.
- Fried fish: fish + carrot; fish preparation, then the existing flower-shaped frying path. Gives a 30/60 percent chance to double crops, recovered seeds, minerals, fish or completed dishes for 12/14 ticks (low/medium only). Purchases and sale gold are excluded.

These figures are developer settings for low/medium/high fish. Only one food effect is active at a time. New food replaces the previous effect. Existing vegetable recipes and paths remain unchanged. Fish now sell for copper's price plus 0/3/6 gold, currently 21/24/27.

`game_seafood.py` handles ingredient selection and shared effects. `cooking_methods.gestures` contains reusable fish preparation, grilling, stirring and frying paths. Fish recipe stages reference them by `method`. Egg preparation is reserved as a future third preparation method. No egg gameplay is added in this update.

Configure rod durability with `fishing.rod_safe_casts` and `rod_break_increment`; pricing with `rod_price_multiplier`, `fish_price_base_mineral` and `fish_price_grade_bonus`. Food variants and remaining sale charges are saved. Older saves initialize rod usage at zero. Developer tests: `python -m unittest test_fishing test_seafood -v` and `node test_fishing_audio.cjs`.

## Fish cooking groups

- Grilled fish: mackerel (low), carp (medium), salmon (high).
- Fried fish: bass (low), flounder (medium). No high-grade variant is crafted.
- Fish stew: sardine (low), catfish (medium), rainbow trout (high).

Bass is now low grade; carp is medium. Recipe availability, ingredient cards, selection, cooking start and completion all enforce `recipes.<id>.allowed_fish`. Configure strengths through `quality_effects`. Successful and missed casts cost 4 ticks, twice the existing 2-tick completed-rock mining cost. Individual mining hits still consume no time.

Sale prices are floored consistently in previews and payouts. Existing high-grade fried fish is merged into the medium variant on load; active seafood effects adopt the new strengths without resetting remaining duration or sale uses beyond the new maximum. Tests: `python -m unittest test_fishing test_seafood -v` (16 cases) and `node test_fishing_audio.cjs`. Hardware, browser visual rendering and headphone listening are not verified.

## Fishing feedback update (current)

The lake is open without a rod; only casting requires one. Rods cost 100 gold. Each valid cast costs 2 ticks. Four successful casts are safe; break chance starts at 10% on the fifth success and rises by 10 percentage points per success. Misses do not wear the rod; doubled catches count as one successful cast. The breaking cast retains its reward. Old saves initialize the new successful-catch counter at zero.

`fishing.middle_area_fraction=1/6` defines the middle circle by total pad area (radius ~11.28 at 60×40). `near_radius=4` retains the center zone. Adjust rod rules with `rod_price`, `rod_safe_catches`, `rod_break_increment`, and time with `time.action_costs.fish`.

Water gain is 0.12–0.85 with distance_scale 40; tts_multiplier is 1. Fishing uses basic background music at its configured 0.2 multiplier, not minigame music. A successful catch plays splash; high-grade fish play splash and shine at the same scheduled audio timestamp. Misses play neither. Rod destruction also plays destroy.

Cooking uses scene3's kitchen background without the old default stew image. The companion no longer draws the lake boundary or target ripple. The tactile lake outline and visual pointer remain. Tests: `python -m unittest test_fishing test_seafood test_fishing_polish -q`, `node test_fishing_audio.cjs`, `node test_catch_audio.cjs`. Live browser rendering and headphone/device checks were not performed.


## Fish price and effect update

Fish sell prices: Simple 24, Ordinary 27, Luxurious 36 gold. Seafood sale prices use the updated ingredient prices. Luxurious grilled fish uses a 3x rare-draw weight; luxurious fish stew raises sale prices by 80%, rounded down. Seafood names use Simple / Ordinary / Luxurious; effect labels contain only the effect and omit duration and sale counts; effect lifetimes remain unchanged. Configure fish prices with fishing.fish_sell_prices.


Food descriptions show effect duration again, matching vegetable dishes. Fish stew shows its sale-use count. Active effects show the remaining hours or sales. Simple / Ordinary / Luxurious remain on food names only.


## Rowan and weekly offers

Rowan stands beside the shop in the village. Select him to read and hear his dialogue. Either direction button closes the conversation; F1 opens the map and F2 opens the inventory. The visual companion shows his portrait and dialogue without sending game input.

On the first conversation Rowan gives one bowl of Rowan's soup. It uses the tomato carrot stew image and harvest effect, has a base sale price of 100 gold, and cannot be cooked. Use it from the inventory or sell it, then speak to Rowan to receive one seed of each crop. Speak to him again for the farming tutorial. Return with any one crop and select it on the submission screen to receive 100 gold. Gifts and rewards are granted once. Quest progress is included in saves; older saves start Rowan's quests from the beginning.

Game day 1 is Monday. Open Shop → Calendar to hear today's offer or select another day. Offers repeat every seven days:

| Day | Offer |
|---|---|
| Monday | Ore purchases: 20% off |
| Tuesday | Cooked food sales: 20% more |
| Wednesday | Fish sales: 20% more |
| Thursday | Seed purchases: 20% off |
| Friday | Ore sales: 20% more |
| Saturday | Fertilizer, pickaxes and fishing rods: 20% off |
| Sunday | All sales: 20% more |

Prices are rounded down after the daily modifier. An active sale-food effect then applies to that price, rounded down again. Research costs and quest rewards are not affected.

The first inventory page contains gold and usable food. Materials, seeds, crops, fish and tools start on subsequent pages. If more than eleven foods are owned, extra food pages appear before other items; nothing is discarded. Left and right change pages. F2 closes inventory, and F1 switches to the map.

`game_village.py` contains Rowan's quest state, dialogue, crop submission and daily market calculations. `game_config.json` exposes `rowan.seed_gift_each`, `rowan.vegetable_reward_gold`, `weekly_market.discount_percent`, `weekly_market.bonus_percent`, and the seven `weekly_market.days` entries. Rowan's soup is defined in `recipes.rowan_soup`.

`web/spectator/assets/rowan.png` is a transparent atlas containing the dialogue portrait, standing character and fishing rod. Crop rectangles and scene placement are registered in `visual-assets.json` and `scene-objects.json`; existing images are reused. The atlas was generated with the built-in image generator using a cozy pixel-art farmer with auburn hair, beard, straw hat, green shirt and brown overalls, plus a wooden fishing rod on a transparent background.

Validation: `python -m unittest test_village -v` and `node test_hardware.mjs`. Camera and physical-pad checks require the separately supplied tracking module and hardware.


## In-place dialogue and tool visuals

Talking to Rowan keeps the village page and its navigation. Only vegetable submission opens a separate selection page, with owned crops and no NPC icon. Select one crop to submit it and return to the village, or use either direction button to cancel. The shop Calendar button now speaks the seven short daily offers without opening another page.

The portrait canvas uses its own 6:7 aspect ratio; the scene's 8:5 ratio applies only to the main canvas. The detailed fishing rod appears at the lake while a rod is owned. A raised pickaxe appears beside the focused mine rock only while a pickaxe is owned. These are read-only visual cues.

`assets/items3.png` is a 3x3 transparent item atlas, registered in `visual-assets.json`. Row order: fishing rod / calendar / bird; coffee beans / coffee / scissors; animal feed / kitchen knife / bug net. The small rod is used in inventory and shop cards; the original detailed rod is registered as `fishing_rod_equipped`. The other seven future-content items are assets only, not new gameplay.

Generated with the built-in image tool: nine isolated, chunky pixel-art farming inventory sprites, warm colors, transparent background, no text or frames, equal 3x3 cells. All existing assets are retained.
