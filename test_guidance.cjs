const {test}=require('node:test');
const assert=require('node:assert/strict');
const {GameAudio}=require('./web/game-audio.js');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const param=()=>({value:1,setTargetAtTime(v){this.value=v;},setValueAtTime(v){this.value=v;},linearRampToValueAtTime(v){this.value=v;},exponentialRampToValueAtTime(v){this.value=v;}});
function setup(t){
    const sources=[],tones=[];
    const context={state:'running',currentTime:1,destination:{},
        createGain(){return {gain:param(),connect(){},disconnect(){}};},
        createPanner(){return {positionX:param(),positionY:param(),positionZ:param(),connect(){}};}};
    function source(tone=false){
        const node={frequency:param(),playbackRate:param(),connect(){},disconnect(){},
            start(){this.started=true;},stop(at){if(at===undefined){this.stopped=true;this.onended?.();}}};
        (tone?tones:sources).push(node);return node;
    }
    context.createBufferSource=()=>source();context.createOscillator=()=>source(true);
    const audio=new GameAudio({contextFactory:()=>context,now:()=>context.currentTime*1000});
    audio.load=async name=>({name,duration:1});audio.unlock();t.after(()=>audio.stopAll());
    return {audio,context,sources,tones};
}
const field=(kind='water',targets=[{id:'one',x:40,y:20}])=>({page:'water_minigame',pointer:{x:30,y:20},
    audio_guidance:{kind,targets,total:8,completed:0}});

test('beacons follow pointer-relative direction immediately without a server round trip',t=>{
    const s=setup(t);s.audio.handle(field());
    assert.equal(s.audio.guidancePanner.panningModel,'HRTF');
    assert.equal(s.audio.guidancePanner.positionX.value,1);
    s.audio.move(50,20);assert.equal(s.audio.guidancePanner.positionX.value,-1);
    s.audio.move(40,30);assert.equal(s.audio.guidancePanner.positionZ.value,-1);
    s.audio.move(40,10);assert.equal(s.audio.guidancePanner.positionZ.value,1);
});
test('nearest target stays stable at a boundary and changes when collected',t=>{
    const s=setup(t);const targets=[{id:'a',x:20,y:20},{id:'b',x:40,y:20}];
    s.audio.handle(field('water',targets));assert.equal(s.audio.guidanceTargetId,'a');
    s.audio.move(30.2,20);assert.equal(s.audio.guidanceTargetId,'a');
    s.audio.handle(field('water',[targets[1]]));assert.equal(s.audio.guidanceTargetId,'b');
});
test('closer targets use faster pulses and a higher pitch',t=>{
    const s=setup(t);s.audio.handle(field());const farPitch=s.tones[0].frequency.value;
    s.context.currentTime+=0.4;s.audio.move(40,20);
    assert.equal(s.tones.length,2);assert.ok(s.tones[1].frequency.value>farPitch);
    s.context.currentTime+=0.1;s.audio.pulseGuidance();assert.equal(s.tones.length,2);
    s.context.currentTime+=0.3;s.audio.pulseGuidance();assert.equal(s.tones.length,3);
});
test('farm and mine activities have distinct beacon pitches',t=>{
    const s=setup(t);const pitches=[];
    for(const kind of ['water','soil','crop','mine']){
        s.audio.stopGuidance();s.audio.handle(field(kind));pitches.push(s.tones.at(-1).frequency.value);
    }
    assert.equal(new Set(pitches).size,4);
});
test('pause, leaving, mute and window suspension stop every pending beacon',t=>{
    const s=setup(t);
    for(const stop of [()=>s.audio.handle({page:'home'}),()=>s.audio.handle({...field(),paused:true}),
        ()=>s.audio.setEnabled(false),()=>s.audio.setSuspended(true)]){
        s.audio.setEnabled(true);s.audio.setSuspended(false);s.audio.handle(field());
        const active=[...s.audio.guidanceSources];assert.ok(active.length);
        stop();assert.equal(s.audio.guidanceTimer,null);assert.ok(active.every(node=>node.stopped));
    }
});
test('target cue preference survives suspension and does not disable fishing',async t=>{
    const s=setup(t);s.audio.handle(field());s.audio.setGuidanceEnabled(false);
    s.audio.setSuspended(true);s.audio.setSuspended(false);
    assert.equal(s.audio.guidanceTimer,null);assert.equal(s.audio.guidanceEnabled,false);
    s.audio.handle({page:'fishing',pointer:{x:0,y:0},fishing:{active:true,target:[20,20]}});await tick();
    assert.ok(s.audio.fishingSource);assert.equal(s.audio.guidanceTimer,null);
});
test('crop progress changes confirmation pitch while cooking retains its original cue',async t=>{
    const s=setup(t);s.audio.handle({...field(),audio_guidance:{...field().audio_guidance,completed:4}});
    await s.audio.correct();assert.equal(s.sources.at(-1).playbackRate.value,1.11);
    s.context.currentTime+=1;await s.audio.correct(1,true);assert.equal(s.sources.at(-1).playbackRate.value,1);
});
test('successive mine hits change impact pitch without altering the recording',async t=>{
    const s=setup(t);s.audio.handle({page:'mine'},[{kind:'one_shot',sound:'pickaxe',progress:1/3}]);await tick();
    const first=s.sources.find(source=>source.buffer.name==='pickaxe');
    s.audio.handle({page:'mine'},[{kind:'one_shot',sound:'pickaxe',progress:2/3}]);await tick();
    const last=s.sources.filter(source=>source.buffer.name==='pickaxe').at(-1);
    assert.ok(first.playbackRate.value<last.playbackRate.value);assert.equal(last.buffer.name,'pickaxe');
});
