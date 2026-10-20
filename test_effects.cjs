const {test} = require('node:test');
const assert = require('node:assert/strict');
const {GameAudio,SOUND_CUES} = require('./web/game-audio.js');
const tick = () => new Promise(resolve => setImmediate(resolve));
const param = () => ({value:0,setTargetAtTime(v){this.value=v;},setValueAtTime(v){this.value=v;},
    linearRampToValueAtTime(v){this.value=v;},exponentialRampToValueAtTime(v){this.value=v;}});
function setup() {
    const sources=[], tones=[]; let now=0;
    const node = () => ({connect(target){this.target=target;},disconnect(){}});
    const context={state:'running',currentTime:1,destination:{},
        createGain(){return {...node(),gain:param()};},
        createBufferSource(){const s={...node(),start(){this.started=true;},stop(){this.stopped=true;}};sources.push(s);return s;},
        createOscillator(){const s={...node(),frequency:param(),start(at){this.startedAt=at;},stop(at){this.stoppedAt=at;}};tones.push(s);return s;}};
    const audio=new GameAudio({contextFactory:()=>context,now:()=>now});
    audio.load=async name=>({name,duration:1}); audio.unlock();
    return {audio,context,sources,tones,setNow:value=>{now=value;}};
}
const care = page => ({page,care:{},cooking:{dragging:false}});

test('completed physical tasks get confirmation instead of silent suppression',()=>{
    const s=setup(); const cues=[];s.audio.cue=name=>cues.push(name);
    for (const name of ['water','fertilize','harvest','cooking_success']) s.audio.feedback(name);
    assert.deepEqual(cues,['complete','complete','complete','complete']);
});
test('recorded footsteps, doors and coins do not get duplicate synthetic cues',()=>{
    const s=setup();const calls=[];s.audio.cue=name=>calls.push(name);s.audio.oneShot=name=>calls.push(name);
    for (const [sfx,sound] of [['travel','step'],['shop_open','door'],['shop_buy','coin'],['shop_sell','coin'],['research','coin']]) {
        s.audio.feedback(sfx,[{kind:'one_shot',sound}]);
    }
    assert.deepEqual(calls,[]);
    s.audio.feedback('travel');s.audio.feedback('shop_open');s.audio.feedback('research');
    assert.deepEqual(calls,['step','door','complete']);
});
test('miss, rejection, completion and navigation use distinct cues',()=>{
    const s=setup();const calls=[];s.audio.cue=name=>calls.push(name);
    ['fishing_miss','error','cooking_success','open_page','plant'].forEach(name=>s.audio.feedback(name));
    assert.deepEqual(calls,['miss','error','complete','page','plant']);
    assert.equal(new Set(calls.map(name=>JSON.stringify(SOUND_CUES[name]))).size,5);
});
test('held care work uses one active recording; quick taps retain a short cue',async t=>{
    for (const [page,name] of [['water_minigame','water'],['fertilizer_minigame','soil'],['harvest','crop']]) {
        await t.test(page,async()=>{
            const s=setup();t.after(()=>s.audio.stopAll());
            s.audio.inputDown(care(page),10,10);await tick();
            const active=s.sources.filter(source=>source.buffer.name===name && !source.stopped);
            assert.equal(active.length,1);assert.equal(active[0].loop,true);
            s.audio.inputUp();assert.equal(active[0].stopped,true);
            s.audio.inputDown(care(page),10,10);s.audio.inputUp();await tick();
            assert.equal(s.sources.filter(source=>source.buffer.name===name && !source.stopped).length,1);
            assert.equal(s.sources.at(-1).loop,undefined);
            assert.equal(s.sources.at(-1).target.gain.value,s.audio.settings.work_gain[name]);
        });
    }
});
test('TTS gain changes cannot restart idle chopping; movement restores it',async t=>{
    const s=setup();t.after(()=>s.audio.stopAll());
    s.audio.held=true;s.audio.lastMotion=0;await s.audio.startWork('cut');
    s.setNow(1000);s.audio.setDucked(true);assert.equal(s.audio.workGain.gain.value,0);
    s.audio.setDucked(false);assert.equal(s.audio.workGain.gain.value,0);
    s.audio.move(10,10);assert.equal(s.audio.workGain.gain.value,s.audio.settings.work_gain.cut);
    s.audio.setDucked(true);assert.equal(s.audio.workGain.gain.value,s.audio.settings.work_gain_during_tts.cut);
});
test('one-shot and cue volume follows speech and all cue notes stop on mute',async()=>{
    const s=setup();s.audio.cue('complete');
    assert.equal(s.tones.length,3);assert.equal(s.audio.cueSources.size,3);
    s.audio.setDucked(true);assert.equal(s.audio.effectsGain.gain.value,s.audio.settings.one_shot_during_tts);
    s.audio.setDucked(false);assert.equal(s.audio.effectsGain.gain.value,1);
    s.audio.setEnabled(false);assert.equal(s.audio.cueSources.size,0);
    assert.ok(s.tones.every(tone=>tone.stoppedAt===undefined));
    s.audio.feedback('error');assert.equal(s.tones.length,3);
});
test('fast hover exploration is rate limited and progress sounds do not multiply',()=>{
    const s=setup();
    for(let i=0;i<12;i++){s.setNow(i*10);s.audio.feedback('hover_plot');}
    assert.equal(s.tones.length,1);
    s.setNow(300);s.audio.feedback('hover_plot');assert.equal(s.tones.length,2);
    for(const name of ['care_spray','harvest_collect','cooking_trace','cooking_wait']) s.audio.feedback(name,[{kind:'correct',count:1}]);
    assert.equal(s.tones.length,2);
    s.audio.stopAll();
});
test('response routing plays state events and semantic feedback exactly once',()=>{
    const s=setup();const calls=[];s.audio.oneShot=name=>calls.push(name);s.audio.cue=name=>calls.push(name);
    s.audio.handle({page:'home'},[{kind:'one_shot',sound:'coin'}],'shop_buy');
    assert.deepEqual(calls,['coin']);
    s.audio.handle({page:'plot_detail'},[],'water');assert.deepEqual(calls,['coin','complete']);
});

test('evaluation work starts on movement without a press and silences when idle or away',async t=>{
    const s=setup();t.after(()=>s.audio.stopAll());
    s.audio.handle(care('water_minigame'));
    s.audio.move(12,10);await tick();
    assert.equal(s.audio.held,false);assert.equal(s.audio.workName,'water');
    assert.ok(s.audio.work?.started);
    s.audio.inputUp();assert.ok(s.audio.work);
    s.setNow(1000);s.audio.setDucked(true);assert.equal(s.audio.workGain.gain.value,0);
    s.audio.setSuspended(true);assert.equal(s.audio.work,null);
});
test('task positioning retains the team spatial bus and one-shot effects still duck',async t=>{
    const s=setup();t.after(()=>s.audio.stopAll());
    s.context.createPanner=()=>({positionX:param(),positionY:param(),positionZ:param(),connect(){},disconnect(){}});
    s.audio.createTaskSpatialBus();
    s.audio.move(59,20);assert.ok(s.audio.taskBus.panner.positionX.value>0);
    s.audio.move(0,20);assert.ok(s.audio.taskBus.panner.positionX.value<0);
    const bus=s.audio.createSpatialBus([20,20],s.audio.effectsGain);
    assert.equal(bus.gain.target,s.audio.effectsGain);assert.equal(bus.dry.target,s.audio.effectsGain);
    s.audio.setDucked(true);assert.equal(s.audio.effectsGain.gain.value,s.audio.settings.one_shot_during_tts);
    bus.disconnect();
});
