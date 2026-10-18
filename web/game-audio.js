/* Separate task / reward channels. Original uploaded MP3 bytes are retained. */
// Frequency, start offset, duration, level. Short cues describe UI and outcomes;
// recorded sounds continue to describe physical actions.
const SOUND_CUES = {
    hover: [[620,0,0.04,0.025]],
    page: [[440,0,0.055,0.055]],
    select: [[520,0,0.055,0.065],[780,0.06,0.065,0.045]],
    plant: [[260,0,0.09,0.11],[390,0.08,0.07,0.06]],
    complete: [[660,0,0.08,0.085],[880,0.09,0.09,0.075],[1047,0.19,0.14,0.065]],
    error: [[220,0,0.09,0.085],[165,0.12,0.14,0.07]],
    miss: [[260,0,0.07,0.06],[196,0.17,0.13,0.045]],
    night: [[392,0,0.12,0.06],[294,0.15,0.18,0.05]],
    morning: [[392,0,0.1,0.06],[523,0.13,0.16,0.055]]
};
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
            guidance:{min_gain:0.025,max_gain:0.065,near_interval_ms:350,far_interval_ms:900,distance_scale:50,position_scale:10},
            fishing:{max_gain:0.85,min_gain:0.12,distance_scale:40,position_scale:10,tts_multiplier:1,bgm_multiplier:0.2},
            bgm_gain:{basic:0.30,minigame:0.20,shop:0.45},
            bgm_during_tts:0.25,
            one_shot_during_tts:0.65,hover_interval_ms:220,
            one_shot_gain:{splash:0.85,sleep:0.8,door:0.7,coin:0.65,pickaxe:0.8,break:0.8,shine:3.0,destroy:0.8},
            one_shot_gain_links:{step:'door'},
            bgm_minigame_pages:['seed_select','water_minigame','fertilizer_minigame','harvest','recipe_select','ingredient_select','cooking'],
            bgm_shop_pages:['shop_choice','shop_buy','shop_sell'],
            work_gain:{water:0.60,soil:0.35,crop:1.4,cut:0.45,cook:0.70},
            work_gain_during_tts:{water:0.40,soil:0.25,crop:0.8,cut:0.30,cook:0.55},
            reward_gain:0.42,reward_gain_during_tts:0.25,
            cooking_correct_interval_ms:650,other_correct_interval_ms:90,
            click_duration_ms:650,motion_idle_ms:450,motion_check_interval_ms:120,
            correct_max_load_age_ms:650,max_reward_sources:2,audio_retry_ms:1000
        };
        this.fishingSource=null; this.fishingToken=0; this.fishingPending=false; this.fishingPosition=null;
        this.latestState = null; this.bgm = null; this.bgmName = null; this.bgmToken = 0;
        this.oneShotSources = new Set(); this.oneShotNames = new Map(); this.oneShotToken = 0;
        this.cueSources = new Set(); this.lastHoverAt = -Infinity;
        this.enabled = true; this.suspended = false; this.volume = 0.9; this.ducked = false;
        this.held = false; this.work = null; this.workName = null; this.workToken = 0;
        this.buffers = new Map(); this.raw = new Map(); this.retryAt = new Map(); this.rewardSources = new Set();
        this.clickSources = new Set(); this.clickToken = 0;
        this.clickGains = new Map();
        this.effectToken = 0; this.lastPosition = null; this.lastCorrectAt = -Infinity; this.lastMotion = 0;
        this.guidanceEnabled=true;this.guidancePosition=null;this.guidanceTargetId=null;
        this.guidanceSources=new Set();this.guidanceTimer=null;this.lastGuidanceAt=-Infinity;
        this.urls = Object.fromEntries(['water','soil','cut','cook','crop','correct','sleep','door','coin','background-basic','background-minigame','background-shop','step','pickaxe','break','shine','destroy','splash'].map(n => [n, `/static/audio/${n}.mp3`]));
    }
    configure(settings = {}) {
        this.settings = {
            ...this.settings, ...settings,
            fishing:{...this.settings.fishing,...settings.fishing},
            task_spatial:{...this.settings.task_spatial,...settings.task_spatial},
            guidance:{...this.settings.guidance,...settings.guidance},
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
        for (const name of Object.keys(this.urls)) this.fetchRaw(name);
    }
    fetchRaw(name) {
        const pending = Promise.resolve().then(()=>this.fetcher(this.urls[name])).then(response=>{
            if (!response.ok) throw new Error(`${name} audio failed to load`);
            return response.arrayBuffer();
        }).catch(error=>{
            if (this.raw.get(name)===pending) this.raw.delete(name);
            this.retryAt.set(name,this.now()+this.settings.audio_retry_ms);
            this.onStatus(error.message);return null;
        });
        this.raw.set(name,pending);
        return pending;
    }
    unlock() {
        if (this.suspended) return;
        try {
            if (!this.context) {
                this.context = this.contextFactory();
                this.master = this.context.createGain(); this.master.connect(this.context.destination);
                this.bgmGain = this.context.createGain(); this.bgmGain.connect(this.master);
                this.createTaskSpatialBus();
                this.workGain = this.context.createGain(); this.workGain.connect(this.taskInput);
                this.rewardGain = this.context.createGain(); this.rewardGain.gain.value = this.settings.reward_gain; this.rewardGain.connect(this.master);
                this.effectsGain = this.context.createGain(); this.effectsGain.connect(this.master);
                this.setVolume(this.volume); this.setDucked(this.ducked);
            }
            if (this.context.state === 'suspended') this.context.resume().catch(() => this.onStatus('Press the sound button to enable audio'));
            if (this.latestState) {this.syncBackground(this.latestState);this.syncFishing(this.latestState);this.syncGuidance(this.latestState);}
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
    createSpatialBus(position=this.lastPosition, destination=this.master) {
        const input=this.context.createGain(), gain=this.context.createGain(), dry=this.context.createGain();
        input.connect(dry);dry.connect(destination);
        const panner=typeof this.context.createPanner==='function'?this.context.createPanner():null;
        if(panner){
            panner.panningModel='HRTF';panner.rolloffFactor=0;
            input.connect(panner);panner.connect(gain);
        } else input.connect(gain);
        gain.connect(destination);
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
        if(!this.enabled || this.suspended)return;
        this.unlock();if(!this.context)return;
        const bus=this.createSpatialBus(position,this.effectsGain), oscillator=this.context.createOscillator(),gain=this.context.createGain();
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
        if (this.buffers.has(name)) return this.buffers.get(name);
        if (this.now()<(this.retryAt.get(name)??-Infinity)) return Promise.resolve(null);
        const raw = this.raw.get(name) || this.fetchRaw(name);
        const pending = raw.then(bytes=>bytes ? this.context.decodeAudioData(bytes.slice(0)) : null)
            .catch(()=>{this.onStatus(`${name} audio could not be played`);return null;})
            .then(buffer=>{
                if (!buffer && this.buffers.get(name)===pending) {
                    this.buffers.delete(name);
                    if (this.raw.get(name)===raw) this.raw.delete(name);
                    this.retryAt.set(name,this.now()+this.settings.audio_retry_ms);
                }
                return buffer;
            });
        this.buffers.set(name,pending);
        return pending;
    }
    setVolume(value) {
        this.volume = Math.max(0,Math.min(1,Number(value)||0));
        if (this.master) this.master.gain.setTargetAtTime(this.enabled && !this.suspended ? this.volume * Math.max(0,Number(this.settings.master_gain) || 0) : 0,this.context.currentTime,0.015);
    }
    setEnabled(enabled) {
        this.enabled = !!enabled;
        if (!this.enabled) this.stopAll();
        this.setVolume(this.volume);
        if (this.enabled && !this.suspended && this.latestState) {this.syncBackground(this.latestState);this.syncFishing(this.latestState);this.syncGuidance(this.latestState);}
    }
    setSuspended(suspended) {
        suspended = !!suspended;
        if (this.suspended === suspended) return;
        this.suspended = suspended;
        if (suspended) this.stopAll();
        this.setVolume(this.volume);
        // Only ambient loops return. Tasks and one-shot effects need new input.
        if (!suspended && this.enabled && this.context && this.latestState) {
            this.syncBackground(this.latestState);
            this.syncFishing(this.latestState);
            this.syncGuidance(this.latestState);
        }
    }
    setDucked(ducked) {
        this.ducked = !!ducked;
        this.updateFishingPosition();
        this.applyBackgroundGain();
        this.applyWorkGain();
        if (this.rewardGain) this.rewardGain.gain.setTargetAtTime(this.ducked ? this.settings.reward_gain_during_tts : this.settings.reward_gain,this.context.currentTime,0.02);
        if (this.effectsGain) this.effectsGain.gain.setTargetAtTime(this.ducked ? this.settings.one_shot_during_tts : 1,this.context.currentTime,0.025);
        for (const {gain,name} of this.clickGains.values()) gain.gain.setTargetAtTime(this.ducked ? this.settings.work_gain_during_tts[name] : this.settings.work_gain[name],this.context.currentTime,0.02);
    }
    applyWorkGain() {
        if (!this.workGain || !this.context) return;
        const name = this.workName || 'water';
        const idle = this.now()-this.lastMotion > this.settings.motion_idle_ms;
        const gain = idle ? 0 : this.ducked ? this.settings.work_gain_during_tts[name] : this.settings.work_gain[name];
        this.workGain.gain.setTargetAtTime(gain,this.context.currentTime,0.03);
    }
    cue(name) {
        if (!this.enabled || this.suspended || !SOUND_CUES[name]) return;
        if (name === 'hover') {
            const now = this.now();
            if (now-this.lastHoverAt < this.settings.hover_interval_ms) return;
            this.lastHoverAt = now;
        }
        this.unlock();
        if (!this.context) return;
        const at = this.context.currentTime + 0.005;
        for (const [frequency,offset,duration,level] of SOUND_CUES[name]) {
            const source = this.context.createOscillator(), gain = this.context.createGain();
            source.type = 'sine'; source.frequency.value = frequency;
            const start = at+offset, end = start+duration;
            gain.gain.setValueAtTime(0.0001,start);
            gain.gain.linearRampToValueAtTime(level,start+0.008);
            gain.gain.exponentialRampToValueAtTime(0.0001,end);
            source.connect(gain); gain.connect(this.effectsGain);
            this.cueSources.add(source);
            source.onended = () => {this.cueSources.delete(source);source.disconnect();gain.disconnect();};
            source.start(start); source.stop(end+0.01);
        }
    }
    feedback(name, events=[]) {
        if (!name || !this.enabled || this.suspended) return;
        if (name.startsWith('hover_')) {this.cue('hover');return;}
        const recorded = new Set(events.flatMap(event => event.kind==='one_shot' ? [event.sound] : event.kind==='one_shot_group' ? event.sounds || [] : []));
        if (name==='travel') {if (!recorded.has('step')) this.oneShot('step');return;}
        if (name==='open_page' && recorded.has('step')) return;
        if (name==='shop_open') {if (!recorded.has('door')) this.oneShot('door');return;}
        if (['shop_buy','shop_sell','research'].includes(name)) {if (!recorded.has('coin')) this.cue('complete');return;}
        // Continuous work and individual targets already have recorded cues.
        if (['care_spray','harvest_collect','cooking_trace','cooking_wait'].includes(name)) return;
        if (name==='tool_pickup' && (events.some(event => event.kind==='work_start') || this.workName)) return;
        const kind = {open_page:'page',plant:'plant',water:'complete',fertilize:'complete',harvest:'complete',
            cooking_success:'complete',eat_food:'complete',saved:'complete',loaded:'complete',error:'error',fishing_miss:'miss',
            morning:'morning',day_end:'night',cooking_step:'select'}[name] || 'select';
        this.cue(kind);
    }
    inputDown(state, x, y) {
        if (this.suspended) return;
        this.lastPosition = [x,y];
        this.guidancePosition = [x,y];
        this.held = true; this.lastMotion = this.now(); this.unlock();
        this.updateTaskPosition();
        if (state?.paused || state?.day_ended || state?.sleeping) return;
        if (state?.page === 'water_minigame') {this.clickSound('water');this.startWork('water');}
        else if (state?.page === 'fertilizer_minigame') {this.clickSound('soil');this.startWork('soil');}
        else if (state?.page === 'harvest') {this.clickSound('crop');this.startWork('crop');}
    }
    async clickSound(name) {
        if (!this.enabled || this.suspended) return;
        const token = ++this.clickToken, effect = this.effectToken;
        for (const source of this.clickSources) {try {source.stop();} catch {}}
        this.clickSources.clear();
        this.clickGains.clear();
        const buffer = await this.load(name);
        // A normal release must not cancel a short click while MP3 decoding.
        if (!buffer || !this.enabled || this.suspended || token !== this.clickToken || effect !== this.effectToken) return;
        const source = this.context.createBufferSource();
        const gain = this.context.createGain();
        gain.gain.value = this.ducked ? this.settings.work_gain_during_tts[name] : this.settings.work_gain[name];
        gain.connect(this.taskInput);
        source.buffer = buffer; source.connect(gain);
        this.clickSources.add(source);
        this.clickGains.set(source,{gain,name});
        source.onended = () => {this.clickSources.delete(source);this.clickGains.delete(source);source.disconnect();gain.disconnect();};
        source.start(0, 0, Math.min(this.settings.click_duration_ms / 1000, buffer.duration));
    }
    inputUp() {this.held = false; if(!this.motionActive)this.stopWork();}
    move(x,y) {
        if (!this.lastPosition || Math.hypot(x-this.lastPosition[0],y-this.lastPosition[1])>0.05) {this.motionActive=true;this.pulse();this.syncWork(this.latestState);}
        this.lastPosition=[x,y];
        this.updateTaskPosition();
        this.guidancePosition=[x,y];
        if (this.guidanceTimer) this.pulseGuidance();
        this.fishingPosition=[x,y];
        this.updateFishingPosition();
    }
    pulse() {
        this.lastMotion = this.now();
        if (this.workGain) this.setDucked(this.ducked);
    }
    async startWork(name) {
        if (!this.enabled || this.suspended || !(this.held || this.motionActive) || !['water','soil','cut','cook','crop'].includes(name)) return;
        if (this.workName === name) return;
        this.stopWork();this.workName=name;
        const token=this.workToken;
        const buffer=await this.load(name);
        if (!buffer && token===this.workToken) this.workName=null;
        if (!buffer || token!==this.workToken || !(this.held || this.motionActive) || !this.enabled || this.suspended) return;
        // A quick tap keeps its short cue; a held action uses one source only.
        this.clickToken++;
        for (const click of this.clickSources) {try {click.stop();} catch {}}
        this.clickSources.clear();
        this.clickGains.clear();
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
        if (!this.enabled || this.suspended || count<=0) return;
        this.unlock();if(!this.context)return;
        const at=this.now(), token=this.effectToken;
        // One cue per scoring response; dense checkpoints cannot build a queue.
        if (at-this.lastCorrectAt<(cooking ? this.settings.cooking_correct_interval_ms : this.settings.other_correct_interval_ms)) return;
        this.lastCorrectAt=at;
        const buffer=await this.load('correct');
        if (!buffer || !this.enabled || this.suspended || token!==this.effectToken || this.now()-at>this.settings.correct_max_load_age_ms) return;
        while(this.rewardSources.size>=Math.max(1, this.settings.max_reward_sources)) {
            const oldest=this.rewardSources.values().next().value;
            try{oldest.stop();}catch{}this.rewardSources.delete(oldest);
        }
        const source=this.context.createBufferSource();source.buffer=buffer;source.connect(this.rewardGain);
        const guidance=this.latestState?.audio_guidance;
        if (!cooking && guidance?.total && source.playbackRate) source.playbackRate.value=1+0.22*Math.min(1,guidance.completed/guidance.total);
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
        // The evaluation build performs work while moving, without a held press.
        const active = (this.held || this.motionActive) && this.now()-this.lastMotion<=this.settings.motion_idle_ms && (carePage || (state.page==='cooking' && state.cooking?.dragging));
        if (!active) {this.stopWork();return;}
        const desired=state.page==='water_minigame'?'water':state.page==='fertilizer_minigame'?'soil':state.page==='harvest'?'crop':state.cooking.gesture_kind==='stir'?'cook':'cut';
        if(this.workName!==desired)this.startWork(desired);
    }
    handle(state,events=[],feedback=null) {
        if (state && this.latestState && state.page !== this.latestState.page) {
            this.stopGuidance();this.guidancePosition=null;
            this.stopTasks();
            this.stopSceneEffects(true);
        }
        if (state) this.latestState = state;
        this.updateTaskPosition();
        if (this.suspended || state?.paused) { this.stopAll(); return; }
        this.syncWork(state);
        this.syncBackground(state);
        this.syncFishing(state);
        this.syncGuidance(state);
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
                this.oneShot(event.sound,position,spatial,event.progress);
            }
            if(event.kind==='one_shot_group') this.oneShotGroup(event.sounds,eventPosition);
            if(event.kind==='correct' && event.count>0) this.correct(event.count, event.activity === 'cooking' || state?.page === 'cooking' || ['cut','cook'].includes(this.workName));
        }
        this.feedback(feedback,events);
    }
    backgroundFor(state) {
        if (state.page === "fishing") return "basic";
        if (this.settings.bgm_shop_pages.includes(state.page)) return 'shop';
        if (this.settings.bgm_minigame_pages.includes(state.page)) return 'minigame';
        return 'basic';
    }
    syncBackground(state) {
        if (!state) return;
        if (!this.enabled || this.suspended || state.sleeping || state.paused) { this.stopBackground(); return; }
        if (!this.context) return; // Start after the first browser audio activation.
        const name = this.backgroundFor(state);
        this.applyBackgroundGain(state);
        if (this.bgmName !== name) this.startBackground(name);
    }
    applyBackgroundGain(state=this.latestState) {
        if (!this.bgmGain || !this.context) return;
        const name = state ? this.backgroundFor(state) : this.bgmName || 'basic';
        const fishing = state?.page === 'fishing' ? this.settings.fishing.bgm_multiplier : 1;
        const speech = this.ducked ? this.settings.bgm_during_tts : 1;
        this.bgmGain.gain.setTargetAtTime(this.settings.bgm_gain[name] * fishing * speech, this.context.currentTime, 0.03);
    }
    async startBackground(name) {
        this.stopBackground();
        this.bgmName = name;
        const token = this.bgmToken;
        const buffer = await this.load('background-' + name);
        if (!buffer && token===this.bgmToken) this.bgmName=null;
        if (!buffer || token !== this.bgmToken || !this.enabled || this.suspended) return;
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
    oneShot(name,position=this.lastPosition,spatial=true,progress=0) { return this.oneShotGroup([name],position,spatial,progress); }
    async oneShotGroup(names=[],position=this.lastPosition,spatialEnabled=true,progress=0) {
        // Capture the action point before decoding; later pointer moves must not move this sound.
        position=position ? [...position] : null;
        if (!this.enabled || this.suspended) return;
        names=[...new Set(names)].filter(n=>['sleep','door','coin','step','pickaxe','break','shine','destroy','splash'].includes(n));
        if (!names.length) return;
        this.unlock();
        if (!this.context) return;
        const token=this.oneShotToken;
        const buffers=await Promise.all(names.map(n=>this.load(n)));
        if (token!==this.oneShotToken || !this.enabled || this.suspended) return;
        const startAt=this.context.currentTime+0.015;
        return Promise.all(buffers.map((buffer,i)=>{
            if(!buffer)return Promise.resolve();
            const name=names[i], gain=this.context.createGain();
            gain.gain.value=this.settings.one_shot_gain[this.settings.one_shot_gain_links[name]||name]??0.8;
            const spatial=spatialEnabled && ['pickaxe','break','destroy','step','coin'].includes(name) ? this.createSpatialBus(position,this.effectsGain) : null;
            gain.connect(spatial ? spatial.input : this.effectsGain);
            const source=this.context.createBufferSource();source.buffer=buffer;source.connect(gain);
            if (name==='pickaxe' && source.playbackRate) source.playbackRate.value=1+0.18*Math.max(0,Math.min(1,progress||0));
            this.oneShotSources.add(source);
            this.oneShotNames.set(source,name);
            return new Promise(resolve=>{
                source.onended=()=>{this.oneShotSources.delete(source);this.oneShotNames.delete(source);source.disconnect();gain.disconnect?.();spatial?.disconnect();resolve();};
                // Both buffers are decoded before scheduling the same start time.
                source.start(startAt);
            });
        }));
    }
    async miningLoot(event,position=this.lastPosition) {
        if (this.suspended) return;
        if (!this.enabled) { this.onNarration(event.tts || ''); return; }
        const token = this.miningNarrationToken;
        await this.oneShot(event.impact_sound === 'destroy' ? 'destroy' : 'break',position);
        if (token !== this.miningNarrationToken || !this.enabled || this.suspended) return;
        this.onNarration(event.tts || '');
        if (event.sound === 'shine') this.oneShot('shine');
        else this.correct(1);
    }
    syncFishing(state) {
        const active=state?.page==='fishing' && state.fishing?.active && !state.paused && !state.sleeping && !state.day_ended;
        if (!active || !this.enabled || this.suspended) {this.stopFishing(); return;}
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
        if (!buffer || !this.enabled || this.suspended || !this.latestState?.fishing?.active) return;
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
        this.stopGuidance();
        this.stopFishing();
        this.stopTasks(); this.stopBackground(); this.stopSceneEffects();
    }
    stopSceneEffects(preserveSleep=false) {
        this.oneShotToken++;
        for (const source of this.oneShotSources) {
            // Sleep intentionally continues into the next morning.
            if (preserveSleep && this.oneShotNames.get(source)==='sleep') continue;
            try {source.stop();} catch {}
            this.oneShotSources.delete(source);this.oneShotNames.delete(source);
        }
        for (const source of this.cueSources) {try {source.stop();} catch {}}
        this.cueSources.clear();
    }
    stopTasks() {
        this.motionActive=false;
        this.stopGuidance();
        this.miningNarrationToken++;
        this.effectToken++; this.clickToken++;
        for (const source of this.clickSources) {try {source.stop();} catch {}}
        this.clickSources.clear();
        this.clickGains.clear();
        this.inputUp();
        for(const source of this.rewardSources){try{source.stop();}catch{}}
        this.rewardSources.clear();
    }
    setGuidanceEnabled(enabled) {
        this.guidanceEnabled=!!enabled;
        if (!this.guidanceEnabled) this.stopGuidance();
        else if (this.latestState) this.syncGuidance(this.latestState);
    }
    syncGuidance(state) {
        const targets=state?.audio_guidance?.targets;
        if (!this.enabled || this.suspended || !this.guidanceEnabled || state?.paused || state?.sleeping || state?.day_ended || !targets?.length || !this.context?.createOscillator) {
            this.stopGuidance();return;
        }
        if (!this.guidancePanner) {
            this.guidancePanner=this.context.createPanner();
            this.guidancePanner.panningModel='HRTF';this.guidancePanner.rolloffFactor=0;
            this.guidancePanner.connect(this.effectsGain);
        }
        if (!this.guidancePosition) this.guidancePosition=[state.pointer?.x??0,state.pointer?.y??0];
        if (!this.guidanceTimer) {
            this.guidanceTimer=setInterval(()=>this.pulseGuidance(),120);
            this.guidanceTimer.unref?.();
        }
        this.pulseGuidance();
    }
    pulseGuidance() {
        const data=this.latestState?.audio_guidance, cfg=this.settings.guidance;
        if (!this.guidanceEnabled || !this.enabled || this.suspended || !data?.targets?.length || !this.guidancePosition || !this.guidancePanner) return;
        const [x,y]=this.guidancePosition;
        const distance=target=>Math.hypot(target.x-x,target.y-y);
        let target=data.targets.reduce((a,b)=>distance(a)<=distance(b)?a:b);
        const previous=data.targets.find(item=>item.id===this.guidanceTargetId);
        // Keep the selected beacon stable near the boundary between two targets.
        if (previous && distance(previous)<=distance(target)+1.5) target=previous;
        this.guidanceTargetId=target.id;
        const p=this.guidancePanner,t=this.context.currentTime,scale=Math.max(1,cfg.position_scale);
        const px=(target.x-x)/scale,pz=(target.y-y)/scale;
        if(p.positionX){p.positionX.setTargetAtTime(px,t,0.025);p.positionY.setTargetAtTime(0,t,0.025);p.positionZ.setTargetAtTime(pz,t,0.025);}
        else p.setPosition(px,0,pz);
        const proximity=Math.max(0,1-distance(target)/Math.max(1,cfg.distance_scale));
        const interval=cfg.far_interval_ms-(cfg.far_interval_ms-cfg.near_interval_ms)*proximity;
        if (this.now()-this.lastGuidanceAt<interval) return;
        this.lastGuidanceAt=this.now();
        const source=this.context.createOscillator(),gain=this.context.createGain();
        source.type='sine';source.frequency.value=({water:560,soil:420,crop:720,mine:300}[data.kind]||560)+140*proximity;
        const at=t+0.005,level=cfg.min_gain+(cfg.max_gain-cfg.min_gain)*proximity;
        gain.gain.setValueAtTime(0.0001,at);gain.gain.linearRampToValueAtTime(level,at+0.008);
        gain.gain.exponentialRampToValueAtTime(0.0001,at+0.085);
        source.connect(gain);gain.connect(p);this.guidanceSources.add(source);
        source.onended=()=>{this.guidanceSources.delete(source);source.disconnect();gain.disconnect();};
        source.start(at);source.stop(at+0.095);
    }
    stopGuidance() {
        if(this.guidanceTimer)clearInterval(this.guidanceTimer);
        this.guidanceTimer=null;this.guidanceTargetId=null;this.lastGuidanceAt=-Infinity;
        for(const source of this.guidanceSources){try{source.stop();}catch{}}
        this.guidanceSources.clear();
    }
}
if(typeof window!=='undefined')window.GameAudio=GameAudio;
if(typeof module!=='undefined')module.exports={GameAudio,SOUND_CUES};
