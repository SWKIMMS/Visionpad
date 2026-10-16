/* Separate task / reward channels. Original uploaded MP3 bytes are retained. */
class GameAudio {
    constructor(options = {}) {
        this.contextFactory = options.contextFactory || (() => new (window.AudioContext || window.webkitAudioContext)());
        this.fetcher = options.fetcher || (url => fetch(url));
        this.onNarration = options.onNarration || (() => {});
        this.miningNarrationToken = 0;
        this.onStatus = options.onStatus || (() => {});
        this.now = options.now || (() => performance.now());
        // Fallbacks support old configs; game_config.json overrides these via state.
        this.settings = {
            default_volume:0.9,
            master_gain:1.0,
            task_spatial:{enabled:true,dry_gain:0.35,spatial_gain:1,min_gain:0.65,max_gain:1,distance_scale:40,position_scale:10,smoothing_seconds:0.03},
            fishing:{max_gain:0.85,min_gain:0.12,distance_scale:40,position_scale:10,tts_multiplier:1,bgm_multiplier:0.2},
            bgm_gain:{basic:0.22,minigame:0.10,shop:0.40},
            one_shot_gain:{splash:0.85,sleep:0.8,door:0.7,coin:0.65,pickaxe:0.8,break:0.8,shine:0.8,destroy:0.8},
            one_shot_gain_links:{step:'door'},
            bgm_minigame_pages:['seed_select','water_minigame','fertilizer_minigame','harvest','recipe_select','ingredient_select','cooking'],
            bgm_shop_pages:['shop_choice','shop_buy','shop_sell'],
            work_gain:{water:0.75,soil:0.75,crop:0.75,cut:0.95,cook:0.95},
            work_gain_during_tts:{water:0.30,soil:0.30,crop:0.30,cut:0.38,cook:0.38},
            reward_gain:0.42,reward_gain_during_tts:0.25,
            cooking_correct_interval_ms:650,other_correct_interval_ms:90,
            click_duration_ms:650,motion_idle_ms:450,motion_check_interval_ms:120,
            correct_max_load_age_ms:650,max_reward_sources:2
        };
        this.fishingSource=null; this.fishingToken=0; this.fishingPending=false; this.fishingPosition=null;
        this.latestState = null; this.bgm = null; this.bgmName = null; this.bgmToken = 0;
        this.oneShotSources = new Set(); this.oneShotToken = 0;
        this.enabled = true; this.volume = 0.9; this.ducked = false;
        this.held = false; this.work = null; this.workName = null; this.workToken = 0;
        this.buffers = new Map(); this.raw = new Map(); this.rewardSources = new Set();
        this.clickSources = new Set(); this.clickToken = 0;
        this.effectToken = 0; this.lastPosition = null; this.lastCorrectAt = -Infinity; this.lastMotion = 0;
        this.urls = Object.fromEntries(['water','soil','cut','cook','crop','correct','sleep','door','coin','background-basic','background-minigame','background-shop','step','pickaxe','break','shine','destroy','splash'].map(n => [n, `/static/audio/${n}.mp3`]));
    }
    configure(settings = {}) {
        this.settings = {
            ...this.settings, ...settings,
            fishing:{...this.settings.fishing,...settings.fishing},
            task_spatial:{...this.settings.task_spatial,...settings.task_spatial},
            bgm_gain:{...this.settings.bgm_gain,...settings.bgm_gain},
            one_shot_gain:{...this.settings.one_shot_gain,...settings.one_shot_gain},
            one_shot_gain_links:{...this.settings.one_shot_gain_links,...settings.one_shot_gain_links},
            work_gain:{...this.settings.work_gain,...settings.work_gain},
            work_gain_during_tts:{...this.settings.work_gain_during_tts,...settings.work_gain_during_tts}
        };
        this.updateTaskPosition();
        this.setVolume(this.settings.default_volume);
        this.setDucked(this.ducked);
    }
    preload() {
        for (const [name,url] of Object.entries(this.urls)) {
            this.raw.set(name, this.fetcher(url).then(r => {
                if (!r.ok) throw new Error(`${name} audio failed to load`);
                return r.arrayBuffer();
            }).catch(error => {this.onStatus(error.message);return null;}));
        }
    }
    unlock() {
        try {
            if (!this.context) {
                this.context = this.contextFactory();
                this.master = this.context.createGain(); this.master.connect(this.context.destination);
                this.bgmGain = this.context.createGain(); this.bgmGain.connect(this.master);
                this.createTaskSpatialBus();
                this.workGain = this.context.createGain(); this.workGain.connect(this.taskInput);
                this.rewardGain = this.context.createGain(); this.rewardGain.gain.value = this.settings.reward_gain; this.rewardGain.connect(this.master);
                this.setVolume(this.volume); this.setDucked(this.ducked);
            }
            if (this.context.state === 'suspended') this.context.resume().catch(() => this.onStatus('Press the sound button to enable audio'));
            if (this.latestState) {this.syncBackground(this.latestState);this.syncFishing(this.latestState);}
        } catch {this.onStatus('Audio unavailable · Follow the captions');}
    }
    relativeSound(source,listener,cfg) {
        const dx=source[0]-listener[0],dy=source[1]-listener[1];
        const proximity=Math.max(0,1-Math.hypot(dx,dy)/Math.max(1,cfg.distance_scale));
        return {x:dx/Math.max(1,cfg.position_scale),z:dy/Math.max(1,cfg.position_scale),
                gain:cfg.min_gain+(cfg.max_gain-cfg.min_gain)*proximity**2};
    }
    placeSound(panner,position,smooth=0.03,immediate=false) {
        if(!panner)return;
        const set=(param,value)=>{
            if(immediate)param.value=value;
            else param.setTargetAtTime(value,this.context.currentTime,smooth);
        };
        if(panner.positionX){set(panner.positionX,position.x);set(panner.positionY,0);set(panner.positionZ,position.z);}
        else panner.setPosition(position.x,0,position.z);
    }
    createSpatialBus(position=this.lastPosition) {
        const input=this.context.createGain(), gain=this.context.createGain(), dry=this.context.createGain();
        input.connect(dry);dry.connect(this.master);
        const panner=typeof this.context.createPanner==='function'?this.context.createPanner():null;
        if(panner){
            panner.panningModel='HRTF';panner.rolloffFactor=0;
            input.connect(panner);panner.connect(gain);
        } else input.connect(gain);
        gain.connect(this.master);
        const bus={input,panner,gain,dry,disconnect(){input.disconnect();panner?.disconnect();gain.disconnect();dry.disconnect();}};
        this.positionSpatialBus(bus,position,true);
        return bus;
    }
    positionSpatialBus(bus,position=this.lastPosition,immediate=false) {
        if(!bus)return;
        const cfg=this.settings.task_spatial;
        const center=[((this.latestState?.width||60)-1)/2,((this.latestState?.height||40)-1)/2];
        // Same source-minus-listener calculation as fishing. Here only the source moves.
        const sound=cfg.enabled?this.relativeSound(position||center,center,cfg):{x:0,z:0,gain:1};
        const smooth=Math.max(0.01,Number(cfg.smoothing_seconds)||0.03);
        this.placeSound(bus.panner,sound,smooth,immediate);
        const spatialGain=cfg.enabled?sound.gain*Math.max(0,Number(cfg.spatial_gain)||0):0;
        const dryGain=cfg.enabled?Math.max(0,Number(cfg.dry_gain)||0):1;
        if(immediate){bus.gain.gain.value=spatialGain;bus.dry.gain.value=dryGain;}
        else {
            bus.gain.gain.setTargetAtTime(spatialGain,this.context.currentTime,smooth);
            bus.dry.gain.setTargetAtTime(dryGain,this.context.currentTime,smooth);
        }
    }
    createTaskSpatialBus() {
        this.taskBus=this.createSpatialBus();this.taskInput=this.taskBus.input;
    }
    updateTaskPosition() {this.positionSpatialBus(this.taskBus);}
    playTone(frequency,duration=0.09,volume=0.06,position=this.lastPosition) {
        if(!this.enabled)return;
        this.unlock();if(!this.context)return;
        const bus=this.createSpatialBus(position), oscillator=this.context.createOscillator(),gain=this.context.createGain();
        oscillator.frequency.value=frequency; // Preserve the original cue pitch.
        gain.gain.setValueAtTime(volume,this.context.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001,this.context.currentTime+duration);
        oscillator.connect(gain);gain.connect(bus.input);
        this.oneShotSources.add(oscillator);
        oscillator.onended=()=>{this.oneShotSources.delete(oscillator);oscillator.disconnect();gain.disconnect();bus.disconnect();};
        oscillator.start();oscillator.stop(this.context.currentTime+duration);
    }
    load(name) {
        if (!this.context || !this.urls[name]) return Promise.resolve(null);
        if (!this.raw.size) this.preload();
        if (!this.buffers.has(name)) this.buffers.set(name, this.raw.get(name).then(bytes => bytes ? this.context.decodeAudioData(bytes.slice(0)) : null).catch(() => {this.onStatus(`${name} audio could not be played`);return null;}));
        return this.buffers.get(name);
    }
    setVolume(value) {
        this.volume = Math.max(0,Math.min(1,Number(value)||0));
        if (this.master) this.master.gain.setTargetAtTime(this.enabled ? this.volume * Math.max(0,Number(this.settings.master_gain) || 0) : 0,this.context.currentTime,0.015);
    }
    setEnabled(enabled) {
        this.enabled = !!enabled;
        if (!this.enabled) this.stopAll();
        this.setVolume(this.volume);
        if (this.enabled && this.latestState) {this.syncBackground(this.latestState);this.syncFishing(this.latestState);}
    }
    setDucked(ducked) {
        const workName = this.workName || 'water';
        this.ducked = !!ducked;
        this.updateFishingPosition();
        if (this.workGain) this.workGain.gain.setTargetAtTime(this.ducked ? this.settings.work_gain_during_tts[workName] : this.settings.work_gain[workName],this.context.currentTime,0.03);
        if (this.rewardGain) this.rewardGain.gain.setTargetAtTime(this.ducked ? this.settings.reward_gain_during_tts : this.settings.reward_gain,this.context.currentTime,0.02);
    }
    inputDown(state, x, y) {
        this.lastPosition = [x,y];
        this.held = true; this.lastMotion = this.now(); this.unlock();
        this.updateTaskPosition();
        if (state?.paused || state?.day_ended || state?.sleeping) return;
        if (state?.page === 'water_minigame') {this.clickSound('water');this.startWork('water');}
        else if (state?.page === 'fertilizer_minigame') {this.clickSound('soil');this.startWork('soil');}
        else if (state?.page === 'harvest') {this.clickSound('crop');this.startWork('crop');}
    }
    async clickSound(name) {
        if (!this.enabled) return;
        const token = ++this.clickToken, effect = this.effectToken;
        for (const source of this.clickSources) {try {source.stop();} catch {}}
        this.clickSources.clear();
        const buffer = await this.load(name);
        // A normal release must not cancel a short click while MP3 decoding.
        if (!buffer || !this.enabled || token !== this.clickToken || effect !== this.effectToken) return;
        const source = this.context.createBufferSource();
        source.buffer = buffer; source.connect(this.workGain);
        this.clickSources.add(source);
        source.onended = () => {this.clickSources.delete(source);source.disconnect();};
        source.start(0, 0, Math.min(this.settings.click_duration_ms / 1000, buffer.duration));
    }
    inputUp() {this.held = false; if(!this.motionActive)this.stopWork();}
    move(x,y) {
        if (!this.lastPosition || Math.hypot(x-this.lastPosition[0],y-this.lastPosition[1])>0.05) {this.motionActive=true;this.pulse();this.syncWork(this.latestState);}
        this.lastPosition=[x,y];
        this.updateTaskPosition();
        this.fishingPosition=[x,y];
        this.updateFishingPosition();
    }
    pulse() {
        this.lastMotion = this.now();
        if (this.workGain) this.setDucked(this.ducked);
    }
    async startWork(name) {
        if (!this.enabled || !(this.held || this.motionActive) || !['water','soil','cut','cook','crop'].includes(name)) return;
        if (this.workName === name) return;
        this.stopWork();this.workName=name;
        const token=this.workToken;
        const buffer=await this.load(name);
        if (!buffer || token!==this.workToken || !(this.held || this.motionActive) || !this.enabled) return;
        const source=this.context.createBufferSource();source.buffer=buffer;source.loop=true;
        source.connect(this.workGain);this.work=source;this.setDucked(this.ducked);source.start();
        source.onended=()=>source.disconnect();
        this.onStatus(({water:'Watering',soil:'Fertilizing',cut:'Chopping',cook:'Stirring',crop:'Harvesting'})[name]);
        // Cutting/stirring only remains audible while the pointer is moving.
        this.motionTimer=setInterval(()=>{
            if (this.now()-this.lastMotion>this.settings.motion_idle_ms) {
                this.motionActive=false;this.stopWork();
            }
        },this.settings.motion_check_interval_ms);
    }
    stopWork() {
        const wasWorking = !!this.workName;
        this.workToken++;this.workName=null;clearInterval(this.motionTimer);
        if(wasWorking)this.onStatus(this.enabled?"Task and reward sounds ready":"Sound off");
        if (this.work) {try{this.work.stop();}catch{}this.work=null;}
    }
    async correct(count=1, cooking=false) {
        if (!this.enabled || count<=0) return;
        this.unlock();if(!this.context)return;
        const at=this.now(), token=this.effectToken;
        // One cue per scoring response; dense checkpoints cannot build a queue.
        if (at-this.lastCorrectAt<(cooking ? this.settings.cooking_correct_interval_ms : this.settings.other_correct_interval_ms)) return;
        this.lastCorrectAt=at;
        const buffer=await this.load('correct');
        if (!buffer || !this.enabled || token!==this.effectToken || this.now()-at>this.settings.correct_max_load_age_ms) return;
        while(this.rewardSources.size>=Math.max(1, this.settings.max_reward_sources)) {
            const oldest=this.rewardSources.values().next().value;
            try{oldest.stop();}catch{}this.rewardSources.delete(oldest);
        }
        const source=this.context.createBufferSource();source.buffer=buffer;source.connect(this.rewardGain);
        this.rewardSources.add(source);source.onended=()=>{this.rewardSources.delete(source);source.disconnect();};source.start();
    }
    syncWork(state) {
        // Reward-only responses never own the task channel's lifecycle.
        if (!state) return;
        if (state.paused || state.day_ended || state.sleeping) {
            // Repeated night snapshots must not cancel pending loot narration.
            if (this.held || this.workName || this.clickSources.size || this.rewardSources.size) this.stopTasks();
            return;
        }
        const carePage = ['water_minigame','fertilizer_minigame','harvest'].includes(state.page);
        // Local press/release is authoritative for sprinkling. A queued hover
        // snapshot can still say dragging=false after a newer local press.
        const active = (this.held || this.motionActive) && this.now()-this.lastMotion<=this.settings.motion_idle_ms && (carePage || (state.page==='cooking' && state.cooking?.dragging));
        if (!active) {this.stopWork();return;}
        const desired=state.page==='water_minigame'?'water':state.page==='fertilizer_minigame'?'soil':state.page==='harvest'?'crop':state.cooking.gesture_kind==='stir'?'cook':'cut';
        if(this.workName!==desired)this.startWork(desired);
    }
    handle(state,events=[]) {
        if (state) this.latestState = state;
        this.updateTaskPosition();
        if (state?.paused) { this.stopAll(); return; }
        this.syncWork(state);
        this.syncBackground(state);
        this.syncFishing(state);
        const eventPosition=Number.isFinite(state?.pointer?.x) && Number.isFinite(state?.pointer?.y) ? [state.pointer.x,state.pointer.y] : this.lastPosition;
        // Layer 2 only: never stop, restart, pulse, or change gain of layer 1.
        for (const event of events) {
            if(event.kind==='item_destroyed') {
                if (event.reward_sound) this.miningLoot({...event, sound:event.reward_sound, impact_sound:'destroy'},eventPosition);
                else this.oneShot('destroy',eventPosition);
            }
            if(event.kind==='mining_loot') this.miningLoot(event,eventPosition);
            if(event.kind==='one_shot') {
                let position=eventPosition;
                if(event.sound==='step') {
                    const w=this.latestState?.width||60,h=this.latestState?.height||40;
                    position=[event.direction==='left'?0:event.direction==='right'?w-1:(w-1)/2,(h-1)/2];
                }
                const spatial=event.sound!=='door' && !(event.sound==='coin' && ['shop_buy','shop_sell'].includes(state?.page));
                this.oneShot(event.sound,position,spatial);
            }
            if(event.kind==='one_shot_group') this.oneShotGroup(event.sounds,eventPosition);
            if(event.kind==='correct' && event.count>0) this.correct(event.count, event.activity === 'cooking' || state?.page === 'cooking' || ['cut','cook'].includes(this.workName));
        }
    }
    backgroundFor(state) {
        if (state.page === "fishing") return "basic";
        if (this.settings.bgm_shop_pages.includes(state.page)) return 'shop';
        if (this.settings.bgm_minigame_pages.includes(state.page)) return 'minigame';
        return 'basic';
    }
    syncBackground(state) {
        if (!state) return;
        if (!this.enabled || state.sleeping || state.paused) { this.stopBackground(); return; }
        if (!this.context) return; // Start after the first browser audio activation.
        const name = this.backgroundFor(state);
        this.bgmGain.gain.setTargetAtTime(this.settings.bgm_gain[name] * (state.page==='fishing' ? this.settings.fishing.bgm_multiplier : 1), this.context.currentTime, 0.03);
        if (this.bgmName !== name) this.startBackground(name);
    }
    async startBackground(name) {
        this.stopBackground();
        this.bgmName = name;
        const token = this.bgmToken;
        const buffer = await this.load('background-' + name);
        if (!buffer || token !== this.bgmToken || !this.enabled) return;
        const source = this.context.createBufferSource();
        source.buffer = buffer; source.loop = true; source.connect(this.bgmGain);
        this.bgm = source;
        source.onended = () => source.disconnect();
        source.start();
    }
    stopBackground() {
        this.bgmToken++; this.bgmName = null;
        if (this.bgm) { try { this.bgm.stop(); } catch {} this.bgm = null; }
    }
    oneShot(name,position=this.lastPosition,spatial=true) { return this.oneShotGroup([name],position,spatial); }
    async oneShotGroup(names=[],position=this.lastPosition,spatialEnabled=true) {
        // Capture the action point before decoding; later pointer moves must not move this sound.
        position=position ? [...position] : null;
        if (!this.enabled) return;
        names=[...new Set(names)].filter(n=>['sleep','door','coin','step','pickaxe','break','shine','destroy','splash'].includes(n));
        if (!names.length) return;
        this.unlock();
        if (!this.context) return;
        const token=this.oneShotToken;
        const buffers=await Promise.all(names.map(n=>this.load(n)));
        if (token!==this.oneShotToken || !this.enabled) return;
        const startAt=this.context.currentTime+0.015;
        return Promise.all(buffers.map((buffer,i)=>{
            if(!buffer)return Promise.resolve();
            const name=names[i], gain=this.context.createGain();
            gain.gain.value=this.settings.one_shot_gain[this.settings.one_shot_gain_links[name]||name]??0.8;
            const spatial=spatialEnabled && ['pickaxe','break','destroy','step','coin'].includes(name) ? this.createSpatialBus(position) : null;
            gain.connect(spatial ? spatial.input : this.master);
            const source=this.context.createBufferSource();source.buffer=buffer;source.connect(gain);
            this.oneShotSources.add(source);
            return new Promise(resolve=>{
                source.onended=()=>{this.oneShotSources.delete(source);source.disconnect();gain.disconnect?.();spatial?.disconnect();resolve();};
                // Both buffers are decoded before scheduling the same start time.
                source.start(startAt);
            });
        }));
    }
    async miningLoot(event,position=this.lastPosition) {
        if (!this.enabled) { this.onNarration(event.tts || ''); return; }
        const token = this.miningNarrationToken;
        await this.oneShot(event.impact_sound === 'destroy' ? 'destroy' : 'break',position);
        if (token !== this.miningNarrationToken || !this.enabled) return;
        this.onNarration(event.tts || '');
        if (event.sound === 'shine') this.oneShot('shine');
        else this.correct(1);
    }
    syncFishing(state) {
        const active=state?.page==='fishing' && state.fishing?.active && !state.paused && !state.sleeping && !state.day_ended;
        if (!active || !this.enabled) {this.stopFishing(); return;}
        if (!this.context) return;
        if (!this.fishingGain) {
            this.fishingGain=this.context.createGain();
            this.fishingPanner=this.context.createPanner();
            this.fishingPanner.panningModel='HRTF';
            // Distance loudness is controlled explicitly; panner supplies direction.
            this.fishingPanner.rolloffFactor=0;
            this.fishingPanner.connect(this.fishingGain);this.fishingGain.connect(this.master);
        }
        if (!this.fishingPosition) this.fishingPosition=[state.pointer?.x ?? state.width/2,state.pointer?.y ?? state.height/2];
        this.updateFishingPosition();
        if (!this.fishingSource && !this.fishingPending) this.startFishing();
    }
    updateFishingPosition() {
        const target=this.latestState?.fishing?.target;
        if (!this.fishingGain || !target || !this.fishingPosition) return;
        const cfg=this.settings.fishing, [x,y]=this.fishingPosition;
        const sound=this.relativeSound(target,[x,y],cfg);
        this.fishingGain.gain.setTargetAtTime(sound.gain*(this.ducked?cfg.tts_multiplier:1),this.context.currentTime,0.03);
        // Fishing retains its moving listener and fixed fish target.
        this.placeSound(this.fishingPanner,sound);
    }

    async startFishing() {
        this.fishingPending=true;
        const token=this.fishingToken;
        const buffer=await this.load('water');
        if (token!==this.fishingToken) return;
        this.fishingPending=false;
        if (!buffer || !this.enabled || !this.latestState?.fishing?.active) return;
        const source=this.context.createBufferSource();source.buffer=buffer;source.loop=true;
        source.connect(this.fishingPanner);this.fishingSource=source;
        source.onended=()=>source.disconnect();source.start();
    }
    stopFishing() {
        this.fishingToken++;this.fishingPending=false;this.fishingPosition=null;
        if (this.fishingSource) {try{this.fishingSource.stop();}catch{}this.fishingSource=null;}
    }
    stopAll() {
        this.motionActive=false;
        this.stopFishing();
        this.stopTasks(); this.stopBackground(); this.oneShotToken++;
        for (const source of this.oneShotSources) { try { source.stop(); } catch {} }
        this.oneShotSources.clear();
    }
    stopTasks() {
        this.motionActive=false;
        this.miningNarrationToken++;
        this.effectToken++; this.clickToken++;
        for (const source of this.clickSources) {try {source.stop();} catch {}}
        this.clickSources.clear();
        this.inputUp();
        for(const source of this.rewardSources){try{source.stop();}catch{}}
        this.rewardSources.clear();
    }
}
if(typeof window!=='undefined')window.GameAudio=GameAudio;
if(typeof module!=='undefined')module.exports={GameAudio};
