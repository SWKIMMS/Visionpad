const {test} = require('node:test');
const assert = require('node:assert/strict');
const {GameSpeech} = require('./web/game-speech.js');
const {GameAudio} = require('./web/game-audio.js');
const tick = () => new Promise(resolve => setImmediate(resolve));
function setup(fetcher) {
    const calls = [], sources = [], gains = [], ducks = [], statuses = [], captions = [];
    const context = {state:'running', destination:{}, decodeAudioData:async()=>({duration:1}),
        createGain(){const gain={context, gain:{value:1,setTargetAtTime(value){this.value=value;}},
            connect(target){this.target=target;},disconnect(){this.disconnected=true;}};gains.push(gain);return gain;},
        createBufferSource(){const source={connect(target){this.target=target;},disconnect(){},start(){source.started=true},stop(){source.stopped=true}};sources.push(source);return source;}};
    const request = async(url, options)=>{
        calls.push([url, options]);
        return url === '/api/speech'
            ? {ok:true,json:async()=>({url:'/audio.wav'})}
            : {ok:true,arrayBuffer:async()=>new ArrayBuffer(8)};
    };
    const speech = new GameSpeech({fetcher:fetcher || request,getContext:()=>context,
        onDucking:active=>ducks.push(active),onStatus:status=>statuses.push(status),onCaption:text=>captions.push(text)});
    return {speech,calls,sources,gains,ducks,statuses,captions,context};
}
test('first input unlocks the pending message, and replay reuses decoded audio',async()=>{
    const s=setup();await s.speech.say('Hello.');assert.equal(s.calls.length,0);
    await s.speech.unlock();assert.equal(s.sources.length,1);
    s.sources[0].onended();await s.speech.replay();assert.equal(s.calls.length,2);
    assert.equal(s.sources.length,2);
});
test('NPC profile and selected rate are sent to the fixed voice service',async()=>{
    const s=setup();s.speech.unlock();s.speech.setRate(1.2);
    await s.speech.say('Rowan. Hello.',{profile:'shopkeeper',priority:'dialogue'});
    const sent=JSON.parse(s.calls[0][1].body);
    assert.deepEqual([sent.text,sent.profile,sent.rate,sent.priority],['Rowan. Hello.','shopkeeper',1.2,'dialogue']);
    assert.equal(sent.client_id,s.speech.clientId);assert.ok(sent.sequence>0);
});
test('speech starts at 85 percent and volume changes reuse the active voice',async()=>{
    const s=setup();s.speech.unlock();await s.speech.say('Hello.');
    assert.equal(s.gains[0].gain.value,0.85);
    assert.equal(s.sources[0].target,s.gains[0]);
    assert.equal(s.gains[0].target,s.context.destination);
    s.speech.setVolume(0.6);assert.equal(s.gains[0].gain.value,0.6);
    assert.equal(s.sources.length,1);assert.equal(s.calls.length,2);
    s.sources[0].onended();assert.equal(s.gains[0].disconnected,true);
    await s.speech.replay();assert.equal(s.gains[1].gain.value,0.6);
    assert.equal(s.calls.length,2);
});
test('speech volume clamps safely and does not change game sound volume',()=>{
    const s=setup();const audio=new GameAudio();const gameVolume=audio.volume;
    s.speech.setVolume(0);assert.equal(s.speech.volume,0);
    s.speech.setVolume(-1);assert.equal(s.speech.volume,0);
    s.speech.setVolume(2);assert.equal(s.speech.volume,1);
    s.speech.setVolume(NaN);assert.equal(s.speech.volume,0.85);
    assert.equal(audio.volume,gameVolume);
});
test('late generation never plays after cancellation or a newer message',async()=>{
    const pending=[];
    const s=setup((url,options)=>url==='/api/speech'
        ? new Promise(resolve=>pending.push({resolve,signal:options.signal}))
        : Promise.resolve({ok:true,arrayBuffer:async()=>new ArrayBuffer(8)}));
    s.speech.unlock();const old=s.speech.say('Old.');const current=s.speech.say('Current.');
    assert.equal(pending[0].signal.aborted,true);
    pending[1].resolve({ok:true,json:async()=>({url:'/current.wav'})});await current;
    pending[0].resolve({ok:true,json:async()=>({url:'/old.wav'})});await old;
    assert.equal(s.sources.length,1);assert.equal(s.speech.active.text,'Current.');
    s.speech.stop();assert.equal(s.sources[0].stopped,true);assert.equal(s.ducks.at(-1),false);
});
test('hover cannot interrupt a dialogue and only the latest hover follows it',async()=>{
    const s=setup();s.speech.unlock();await s.speech.say('Rowan. Welcome.',{priority:'dialogue'});
    await s.speech.say('First object.',{priority:'hover'});await s.speech.say('Latest object.',{priority:'hover'});
    assert.equal(s.sources[0].stopped,undefined);assert.equal(s.calls.length,2);
    s.sources[0].onended();await tick();
    assert.equal(s.speech.active.text,'Latest object.');assert.equal(s.sources.length,2);
});
test('mute drops speech and deferred hover, without replay on re-enable',async()=>{
    const s=setup();s.speech.unlock();await s.speech.say('Important.');
    await s.speech.say('Hover.',{priority:'hover'});s.speech.setEnabled(false);
    s.sources[0].onended();s.speech.setEnabled(true);await tick();
    assert.equal(s.sources.length,1);assert.equal(s.speech.active,null);assert.equal(s.ducks.at(-1),false);
});
test('voice failure restores mixing and replay can retry',async()=>{
    let fail=true;
    const s=setup(async url=>url==='/api/speech'
        ? {ok:!fail,json:async()=>fail?{detail:'Voice unavailable'}:{url:'/ok.wav'}}
        : {ok:true,arrayBuffer:async()=>new ArrayBuffer(8)});
    s.speech.unlock();assert.equal(await s.speech.say('Hello.'),false);
    assert.equal(s.ducks.at(-1),false);assert.match(s.statuses.at(-1),/unavailable/);
    fail=false;assert.equal(await s.speech.replay(),true);
});
test('TTS ducks BGM and restores it while preserving fishing guidance',()=>{
    const audio=new GameAudio();const values=[];
    audio.context={currentTime:0};audio.bgmGain={gain:{setTargetAtTime:value=>values.push(value)}};
    audio.latestState={page:'fishing'};
    audio.setDucked(true);assert.equal(values.at(-1),audio.settings.bgm_gain.basic*audio.settings.fishing.bgm_multiplier*0.25);
    audio.setDucked(false);assert.equal(values.at(-1),audio.settings.bgm_gain.basic*audio.settings.fishing.bgm_multiplier);
    assert.equal(audio.settings.fishing.tts_multiplier,1);
});
test('window suspension discards late narration without autoplay on return',async()=>{
    let finish;
    const s=setup((url,options)=>url==='/api/speech'
        ? new Promise(resolve=>{finish=resolve;})
        : Promise.resolve({ok:true,arrayBuffer:async()=>new ArrayBuffer(8)}));
    s.speech.unlock();const old=s.speech.say('Old scene.');
    s.speech.setSuspended(true);
    await s.speech.say('Late result.');s.speech.unlock();
    s.speech.setSuspended(false);
    finish({ok:true,json:async()=>({url:'/old.wav'})});await old;await tick();
    assert.equal(s.sources.length,0);assert.equal(s.speech.pending,null);
    const replay=s.speech.replay();
    finish({ok:true,json:async()=>({url:'/latest.wav'})});await replay;
    assert.equal(s.sources.length,1);assert.equal(s.speech.last.text,'Late result.');
});
test('suspending active speech restores mixing and keeps speech mute on return',async()=>{
    const s=setup();s.speech.unlock();await s.speech.say('Hello.');
    s.speech.setSuspended(true);
    assert.equal(s.sources[0].stopped,true);assert.equal(s.ducks.at(-1),false);
    s.speech.setEnabled(false);s.speech.setSuspended(false);
    assert.equal(s.speech.enabled,false);assert.equal(s.statuses.at(-1),'Off');
});
test('a delayed game result can update the caption and replay without autoplay',async()=>{
    const s=setup();s.speech.unlock();
    await s.speech.say('Late result.',{silent:true});
    assert.equal(s.calls.length,0);assert.equal(s.speech.pending,null);
    assert.equal(s.captions.at(-1),'Late result.');
    await s.speech.replay();assert.equal(s.sources.length,1);
});
test('stopping a pending line cancels its server sequence without requesting audio',async()=>{
    let finish;const requests=[];
    const s=setup((url,options)=>{
        requests.push([url,JSON.parse(options.body)]);
        return url==='/api/speech'?new Promise(resolve=>{finish=resolve;}):Promise.resolve({ok:true,status:204});
    });
    s.speech.unlock();const old=s.speech.say('Old target.',{priority:'hover'});
    s.speech.stop();
    assert.equal(requests[1][0],'/api/speech/cancel');
    assert.equal(requests[1][1].client_id,requests[0][1].client_id);
    assert.ok(requests[1][1].sequence>requests[0][1].sequence);
    finish({ok:true,status:204});await old;assert.equal(s.sources.length,0);
});
test('a superseded API response is silent and a new result still plays',async()=>{
    let first=true;
    const s=setup(async url=>{
        if(url==='/api/speech'){
            if(first){first=false;return {ok:true,status:204};}
            return {ok:true,status:200,json:async()=>({url:'/fresh.wav'})};
        }
        return {ok:true,arrayBuffer:async()=>new ArrayBuffer(8)};
    });
    s.speech.unlock();assert.equal(await s.speech.say('Superseded.'),false);
    assert.equal(s.speech.active,null);assert.equal(s.sources.length,0);
    assert.equal(await s.speech.say('Current result.'),true);assert.equal(s.sources.length,1);
});

test('quest narration finishes before the latest action and drops hover labels',async()=>{
    const s=setup();s.speech.unlock();
    await s.speech.say('Rowan. Take this soup.',{profile:'shopkeeper',priority:'dialogue',channel:'quest'});
    await s.speech.say('Inventory.',{priority:'action'});
    await s.speech.say('Soup.',{priority:'hover'});
    await s.speech.say('Soup used.',{priority:'action'});
    assert.equal(s.sources.length,1);assert.equal(s.sources[0].stopped,undefined);
    assert.equal(s.speech.last.text,'Rowan. Take this soup.');
    s.sources[0].onended();await tick();
    assert.equal(s.speech.active.text,'Soup used.');assert.equal(s.sources.length,2);
    s.sources[1].onended();await tick();assert.equal(s.sources.length,2);
});
test('locked quest is preserved until activation and retains its latest action',async()=>{
    const s=setup();
    await s.speech.say('Quest.',{profile:'shopkeeper',priority:'dialogue',channel:'quest'});
    await s.speech.say('Inventory.');
    assert.equal(s.speech.pending.text,'Quest.');await s.speech.unlock();
    s.sources[0].onended();await tick();
    assert.equal(s.speech.active?.text,'Inventory.');
});
test('a new quest replaces the old one and cancellation drops deferred actions',async()=>{
    const s=setup();s.speech.unlock();
    await s.speech.say('First quest.',{priority:'dialogue',channel:'quest'});
    await s.speech.say('Old action.');
    await s.speech.say('Next quest.',{priority:'dialogue',channel:'quest'});
    assert.equal(s.sources[0].stopped,true);assert.equal(s.speech.active.text,'Next quest.');
    await s.speech.say('Deferred action.');s.speech.stop();
    s.sources[1].onended();await tick();
    assert.equal(s.speech.active,null);assert.equal(s.sources.length,2);
});
test('replay retains the quest voice and protection channel',async()=>{
    const s=setup();s.speech.unlock();
    await s.speech.say('Quest.',{profile:'shopkeeper',priority:'dialogue',channel:'quest'});
    await s.speech.replay();
    assert.equal(s.speech.active.profile,'shopkeeper');assert.equal(s.speech.active.channel,'quest');
    await s.speech.say('Action.');assert.equal(s.speech.active.text,'Quest.');
    s.speech.setSuspended(true);assert.equal(s.speech.pendingAction,null);
});
