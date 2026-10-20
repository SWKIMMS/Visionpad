const {test} = require('node:test');
const assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const {existsSync} = require('node:fs');
const {join} = require('node:path');
const {GameAudio} = require('./web/game-audio.js');
const tick = () => new Promise(resolve=>setImmediate(resolve));
const param = () => ({value:0,setTargetAtTime(v){this.value=v;},setValueAtTime(v){this.value=v;},
    linearRampToValueAtTime(v){this.value=v;},exponentialRampToValueAtTime(v){this.value=v;}});

function setup() {
    const sources=[], narrations=[], played=[], pending=[];
    const context={state:'running',currentTime:0,destination:{},
        createGain(){return {gain:param(),connect(){},disconnect(){}};},
        createPanner(){return {positionX:param(),positionY:param(),positionZ:param(),connect(){},disconnect(){}};},
        decodeAudioData:async()=>({name:'decoded',duration:0.4})};
    function source(tone=false) {
        const node={frequency:param(),connect(){},disconnect(){},ended:false,endAt:Infinity,
            start(at=0,offset=0,duration){
                this.startedAt=Math.max(context.currentTime,at);
                this.endAt=tone||this.loop?Infinity:this.startedAt+(duration??this.buffer.duration);
                played.push(tone?'tone':this.buffer.name);
            },
            stop(at=context.currentTime){this.endAt=at;if(at<=context.currentTime)this.finish();},
            finish(){if(this.ended)return;this.ended=true;queueMicrotask(()=>this.onended?.());}};
        sources.push(node);return node;
    }
    context.createBufferSource=()=>source();context.createOscillator=()=>source(true);
    const audio=new GameAudio({contextFactory:()=>context,now:()=>context.currentTime*1000,
        onNarration:text=>narrations.push(text)});
    audio.load=async name=>({name,duration:name==='sleep'?4.545:name.startsWith('background')?40:0.52});
    audio.unlock();
    async function advance(seconds) {
        context.currentTime+=seconds;
        for(const node of sources) if(node.endAt<=context.currentTime)node.finish();
        await tick();
    }
    return {audio,context,sources,narrations,played,pending,advance};
}

test('page changes cancel old tap, target, transaction and cue loads',async t=>{
    const s=setup();t.after(()=>s.audio.stopAll());
    s.audio.handle({page:'water_minigame'});await tick();
    const delayed=[];
    s.audio.load=name=>['water','correct','coin'].includes(name)
        ? new Promise(resolve=>{delayed.push({name,resolve});}) : Promise.resolve({name,duration:1});
    s.audio.inputDown({page:'water_minigame'},10,10);
    s.audio.correct();s.audio.oneShot('coin');s.audio.cue('complete');
    const oldTones=s.sources.filter(node=>!node.buffer);
    s.audio.handle({page:'home'},[{kind:'one_shot',sound:'step'}],'travel');
    for(const {name,resolve} of delayed)resolve({name,duration:1});
    await tick();
    assert.equal(s.played.filter(name=>['water','correct','coin'].includes(name)).length,0);
    assert.equal(s.played.filter(name=>name==='step').length,1);
    assert.ok(oldTones.every(node=>node.ended));
    assert.equal(s.audio.held,false);
});
test('leaving the mine cancels deferred loot speech and reward',async t=>{
    const s=setup();t.after(()=>s.audio.stopAll());
    s.audio.handle({page:'mine'});await tick();
    s.audio.handle({page:'mine'},[{kind:'mining_loot',sound:'shine',tts:'Diamond 1 collected.'}]);
    await tick();s.audio.handle({page:'home'});await s.advance(1);
    assert.deepEqual(s.narrations,[]);assert.equal(s.played.includes('shine'),false);
});
test('sleep transition survives the morning and ordinary scene changes',async t=>{
    const s=setup();t.after(()=>s.audio.stopAll());
    s.audio.handle({page:'home',sleeping:true},[{kind:'one_shot',sound:'sleep'}]);await tick();
    const sleep=s.sources.find(node=>node.buffer?.name==='sleep');
    await s.advance(2.1);s.audio.handle({page:'home',sleeping:false});
    s.audio.handle({page:'minimap'});await tick();
    assert.equal(sleep.ended,false);
    await s.advance(2.5);assert.equal(sleep.ended,true);
});
test('back navigation with a recorded step does not add another page tone',()=>{
    const s=setup();const cues=[];s.audio.cue=name=>cues.push(name);
    s.audio.feedback('open_page',[{kind:'one_shot',sound:'step'}]);
    assert.deepEqual(cues,[]);
});
test('temporary asset failure retries on the next action without a request storm',async()=>{
    const s=setup();let requests=0;
    s.audio.urls={water:'/water.mp3'};
    s.audio.load=GameAudio.prototype.load.bind(s.audio);
    s.audio.fetcher=async()=>({ok:++requests>1,arrayBuffer:async()=>new ArrayBuffer(8)});
    assert.equal(await s.audio.load('water'),null);
    for(let i=0;i<5;i++)assert.equal(await s.audio.load('water'),null);
    assert.equal(requests,1);
    await s.advance(2);
    assert.ok(await s.audio.load('water'));assert.equal(requests,2);
});
test('background music can recover from an initial asset failure',async t=>{
    const s=setup();t.after(()=>s.audio.stopAll());let requests=0;
    s.audio.urls={'background-basic':'/background-basic.mp3'};
    s.audio.load=GameAudio.prototype.load.bind(s.audio);
    s.audio.fetcher=async()=>({ok:++requests>1,arrayBuffer:async()=>new ArrayBuffer(8)});
    s.audio.handle({page:'home'});await tick();assert.equal(s.audio.bgm,null);
    await s.advance(2);s.audio.handle({page:'home'});await tick();
    assert.ok(s.audio.bgm);assert.equal(requests,2);
});
test('the full real-engine flow drives the audio module without leftover task loops',async t=>{
    const python=join(__dirname,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
    const run=spawnSync(existsSync(python)?python:'python',['tools/audio_flow.py','--stdout'],{cwd:__dirname,encoding:'utf8'});
    assert.equal(run.status,0,run.stderr);
    const flow=JSON.parse(run.stdout);const s=setup();t.after(()=>s.audio.stopAll());
    let state=null,at=flow.events[0].at,configured=false;
    for(const event of flow.events){
        await s.advance(event.at-at);at=event.at;
        const input=event.input;
        if(input.kind==='command')s.audio.stopTasks();
        if(input.kind==='down')s.audio.inputDown(state,input.x,input.y);
        if(input.kind==='up')s.audio.inputUp();
        if(input.kind==='drag'||input.kind==='move')s.audio.move(input.x,input.y);
        const response=event.response;state=response.state;
        if(!configured){s.audio.configure(state.client_settings.audio);configured=true;}
        if(response.tts)s.audio.miningNarrationToken++;
        s.audio.handle(state,response.sound_events,response.sfx);
        await tick();
        if(!['water_minigame','fertilizer_minigame','harvest','cooking'].includes(state.page))assert.equal(s.audio.work,null);
    }
    for(const expected of ['water','soil','crop','cut','cook','coin','door','pickaxe','break','shine','splash','sleep'])
        assert.ok(s.played.includes(expected),`No ${expected} in full flow`);
    assert.ok(s.narrations.some(text=>text.includes('Diamond')));
    assert.equal(state.page,'fishing');assert.equal(flow.milestones.length,12);
    s.audio.stopAll();await tick();
    assert.ok(s.sources.every(node=>node.ended));
});
