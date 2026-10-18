import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {SerialPad,forwardKey,extractPackets,displayPacket,packCells} from './web/hardware.mjs';
const require=createRequire(import.meta.url);
const {GameKeys}=require('./web/game-keys.js');
function packet(mask){const body=[0,3,0x32,0,mask<<4];let check=0xa5;for(const v of body)check^=v;return [0xaa,0x55,0,6,...body,check]}
function setup(){
 const commands=[],timers=new Map();let now=0,id=0;
 const keys=new GameKeys(c=>commands.push(c),{now:()=>now,schedule:fn=>{timers.set(++id,fn);return id},unschedule:i=>timers.delete(i)});
 const input={keyDown:k=>keys.down(k),keyUp:k=>keys.up(k),command:(k,phase)=>keys.up(k,phase==='cancel')};
 const pad=new SerialPad(()=>{},(k,phase)=>forwardKey(input,k,phase));
 return {pad,commands,receive:mask=>{for(const p of extractPackets(packet(mask)).packets)pad.handleKeyPacket(p)},advance:ms=>{now+=ms;for(const f of [...timers.values()])f()}};
}
test('F3 release produces one load command',()=>{const s=setup();s.receive(2);s.receive(0);assert.deepEqual(s.commands,['load'])});
test('holding F3 saves once, without a load on release',()=>{const s=setup();s.receive(2);s.receive(2);s.advance(900);s.receive(0);assert.deepEqual(s.commands,['save'])});
test('disconnect cancels an unfinished hold',async()=>{const s=setup();s.receive(2);await s.pad.disconnect();s.advance(1000);assert.deepEqual(s.commands,[])});
test('F1 F2 F4 use the current key mapping',()=>{const s=setup();for(const m of [8,4,1]){s.receive(m);s.receive(0)}assert.deepEqual(s.commands,['minimap','resources','click'])});
test('held status repeats never toggle menus repeatedly',()=>{const s=setup();s.receive(4);s.receive(4);s.receive(4);s.receive(0);assert.deepEqual(s.commands,['resources'])});
test('simultaneous F2 and F3 releases preserve both edges',()=>{const s=setup();s.receive(6);s.receive(2);s.receive(0);assert.deepEqual(s.commands,['resources','load'])});
test('reconnection can press the same key again',async()=>{const s=setup();s.receive(2);await s.pad.disconnect();s.receive(2);s.receive(0);assert.deepEqual(s.commands,['load'])});
test('split serial packets retain their key mask',()=>{const p=packet(2),a=extractPackets(p.slice(0,7));assert.equal(a.packets.length,0);const b=extractPackets([...a.rest,...p.slice(7)]);assert.deepEqual(b.packets,[p]);assert.deepEqual(b.rest,[])});
test('corrupt key reports and other commands do not trigger input',()=>{const s=setup(),p=packet(2);p[p.length-1]^=1;assert.equal(extractPackets(p).packets.length,0);s.pad.handleKeyPacket([0,0,0,0,0,2,1,0,0,0]);assert.deepEqual(s.commands,[])});
test('display packing and output checksums retain their format',()=>{const cells=packCells([[1,0],[0,1],[1,0],[0,1]],0,1);assert.equal(cells[0],0xa5);const p=displayPacket(0,cells);assert.equal(extractPackets(p).packets.length,1)});
function panPacket(mask){const body=[0,3,0x12,0,0,mask];let check=0xa5;for(const b of body)check^=b;return [0xaa,0x55,0,7,...body,check]}
test('left and right Perkins reports map to navigation',()=>{const s=setup();for(const mask of [4,0,2,0])s.pad.handleKeyPacket(extractPackets(panPacket(mask)).packets[0]);assert.deepEqual(s.commands,['left','right'])});
test('pan held status does not repeat travel',()=>{const s=setup();for(const mask of [4,4,4,0])s.pad.handleKeyPacket(panPacket(mask));assert.deepEqual(s.commands,['left'])});
test('pan release does not release a held F3',()=>{const s=setup();s.receive(2);s.pad.handleKeyPacket(panPacket(4));s.pad.handleKeyPacket(panPacket(0));s.advance(800);assert.deepEqual(s.commands,['left','save']);s.receive(0);assert.deepEqual(s.commands,['left','save'])});
test('save fires at threshold before release; release sends no second command',()=>{const s=setup();s.receive(2);assert.deepEqual(s.commands,[]);s.advance(800);assert.deepEqual(s.commands,['save']);assert.equal(s.pad.mask,2);s.receive(0);assert.deepEqual(s.commands,['save'])});
test('unrelated Perkins bits are ignored',()=>{const s=setup();s.pad.handleKeyPacket(panPacket(0x80));assert.deepEqual(s.commands,[])});
