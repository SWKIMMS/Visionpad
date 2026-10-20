const {test} = require('node:test');
const assert = require('node:assert/strict');
const {GameAudio} = require('./web/game-audio.js');
const tick = () => new Promise(resolve => setImmediate(resolve));

function parameter() {
    return {value: 0, setTargetAtTime(value) { this.value = value; }};
}
function setup() {
    const sources = [];
    const context = {
        state: 'running', currentTime: 4, destination: {},
        createGain() { return {gain: parameter(), connect() {}, disconnect() {}}; },
        createPanner() { return {positionX: parameter(), positionY: parameter(), positionZ: parameter(), connect() {}}; },
        createBufferSource() {
            const source = {connect() {}, disconnect() {},
                start(at = 0) { this.startedAt = at; }, stop() { this.stopped = true; }};
            sources.push(source);
            return source;
        }
    };
    const audio = new GameAudio({contextFactory: () => context});
    audio.load = async name => ({name, duration: 1});
    audio.unlock();
    return {audio, context, sources};
}
const lake = overrides => ({page: 'fishing', width: 60, height: 40,
    pointer: {x: 30, y: 20}, fishing: {active: true, target: [30, 20]}, ...overrides});
const waterSources = s => s.sources.filter(source => source.buffer.name === 'water');

test('HRTF follows pointer-relative left, right, ahead and behind', async () => {
    const s = setup(); s.audio.handle(lake()); await tick();
    assert.equal(s.audio.fishingPanner.panningModel, 'HRTF');
    assert.equal(s.audio.fishingPanner.rolloffFactor, 0);
    for (const [x, y, expectedX, expectedZ] of [[20,20,1,0], [40,20,-1,0], [30,30,0,-1], [30,10,0,1]]) {
        s.audio.move(x,y);
        assert.equal(s.audio.fishingPanner.positionX.value, expectedX);
        assert.equal(s.audio.fishingPanner.positionZ.value, expectedZ);
    }
});
test('nearer water is louder and speech retains the exploration cue', async () => {
    const s = setup(); s.audio.handle(lake({fishing:{active:true,target:[49,25]}})); await tick();
    s.audio.move(0,0); const far = s.audio.fishingGain.gain.value;
    s.audio.move(39,25); const middle = s.audio.fishingGain.gain.value;
    s.audio.move(49,25); const near = s.audio.fishingGain.gain.value;
    assert.equal(far, s.audio.settings.fishing.min_gain);
    assert.ok(far < middle && middle < near);
    assert.equal(near, s.audio.settings.fishing.max_gain);
    s.audio.setDucked(true);
    assert.equal(s.audio.fishingGain.gain.value, near);
    s.audio.setDucked(false);
    assert.equal(s.audio.fishingGain.gain.value, near);
});
test('server snapshots preserve local pointer position and reuse one water loop', async () => {
    const s = setup(); s.audio.handle(lake()); s.audio.move(20,20);
    for (let i=0; i<5; i++) s.audio.handle(lake({pointer:{x:0,y:0}}));
    await tick();
    assert.deepEqual(s.audio.fishingPosition, [20,20]);
    assert.equal(s.audio.fishingPanner.positionX.value, 1);
    assert.equal(waterSources(s).length, 1);
    s.audio.handle(lake({fishing:{active:true,target:[10,20]}}));
    assert.equal(s.audio.fishingPanner.positionX.value, -1);
    assert.equal(waterSources(s).length, 1);
});
for (const [name, state] of Object.entries({
    leaving: {page:'mine',fishing:{active:false,target:null}},
    pause: lake({paused:true}), sleep: lake({sleeping:true}), night: lake({day_ended:true})
})) {
    test(`${name} stops water and prevents a late decode from restarting it`, async () => {
        const s = setup(); let finish;
        s.audio.load = name => name === 'water' ? new Promise(resolve => {finish=resolve;}) : Promise.resolve({name,duration:1});
        s.audio.handle(lake()); s.audio.handle(state);
        finish({name:'water',duration:1}); await tick();
        assert.equal(waterSources(s).length, 0);
        assert.equal(s.audio.fishingPending, false);
        s.audio.handle(lake()); await tick();
        // Resolve the fresh load separately; the old request must not own it.
        finish({name:'water',duration:1}); await tick();
        assert.equal(waterSources(s).length, 1);
        const current = waterSources(s)[0];
        s.audio.handle(state);
        assert.equal(current.stopped, true);
    });
}
test('window suspension blocks late state responses; return restores only ambient loops', async () => {
    const s = setup(); s.audio.handle(lake()); await tick();
    const original = waterSources(s)[0];
    s.audio.setSuspended(true);
    assert.equal(original.stopped, true);
    s.audio.handle(lake()); s.audio.unlock();
    await s.audio.oneShot('coin'); await tick();
    assert.equal(waterSources(s).length, 1);
    assert.equal(s.audio.master.gain.value, 0);
    s.audio.setSuspended(false); await tick();
    assert.equal(waterSources(s).length, 2);
    assert.equal(s.sources.filter(source => source.buffer.name === 'coin').length, 0);
    assert.equal(s.audio.work, null);
});
test('returning to the window preserves the user sound mute', async () => {
    const s = setup(); s.audio.handle(lake()); await tick();
    s.audio.setEnabled(false); s.audio.setSuspended(true); s.audio.handle(lake());
    s.audio.setSuspended(false); await tick();
    assert.equal(s.audio.enabled, false);
    assert.equal(s.audio.master.gain.value, 0);
    assert.equal(waterSources(s).length, 1);
    s.audio.setEnabled(true); await tick();
    assert.equal(waterSources(s).length, 2);
});
test('old water and transaction decodes cannot play after returning to the window', async () => {
    const s = setup(); const waterLoads = []; let finishCoin;
    s.audio.load = name => {
        if (name === 'water') return new Promise(resolve => waterLoads.push(resolve));
        if (name === 'coin') return new Promise(resolve => {finishCoin=resolve;});
        return Promise.resolve({name,duration:1});
    };
    s.audio.handle(lake()); const transaction = s.audio.oneShot('coin');
    s.audio.setSuspended(true); s.audio.handle(lake());
    s.audio.setSuspended(false);
    assert.equal(waterLoads.length, 2);
    waterLoads[0]({name:'water',duration:1}); finishCoin({name:'coin',duration:1});
    await transaction; await tick();
    assert.equal(waterSources(s).length, 0);
    assert.equal(s.sources.filter(source => source.buffer.name === 'coin').length, 0);
    assert.equal(s.audio.fishingPending, true);
    waterLoads[1]({name:'water',duration:1}); await tick();
    assert.equal(waterSources(s).length, 1);
});
test('splash and shine start together; stopping pending effects prevents playback', async () => {
    const s = setup(); const playing = s.audio.oneShotGroup(['splash','shine']); await tick();
    const cues = s.sources.filter(source => ['splash','shine'].includes(source.buffer.name));
    assert.equal(cues.length, 2);
    assert.equal(cues[0].startedAt, cues[1].startedAt);
    assert.ok(cues[0].startedAt > s.context.currentTime);
    cues.forEach(source => source.onended()); await playing;
    let finish;
    s.audio.load = () => new Promise(resolve => {finish=resolve;});
    const late = s.audio.oneShot('splash'); s.audio.stopAll();
    finish({name:'splash',duration:1}); await late;
    assert.equal(s.sources.length, 2);
});
