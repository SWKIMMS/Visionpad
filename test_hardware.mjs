import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {BluetoothPad,forwardKey,packCells,cellsToHex} from './web/hardware.mjs';
import {DataCodes,DotPadKey} from './web/vendor/DotPadSDK-3.0.3.js';
const require=createRequire(import.meta.url);
const {GameKeys}=require('./web/game-keys.js');
Object.defineProperty(globalThis,'navigator',{value:{bluetooth:{}},configurable:true});

// Stand-ins for the SDK objects: callbacks are captured so tests can play pad events.
function fakeBle(){const listeners=new Set();return {name:'DotPad320A',gatt:{connected:true,disconnect(){}},addEventListener:(_,f)=>listeners.add(f),removeEventListener:(_,f)=>listeners.delete(f),drop(){this.gatt.connected=false;for(const f of listeners)f()}}}
function fakeSdk(size={rows:10,columns:30,text:20}){
 const sdk={output:[],device:{isConnect:true,numberCellRows:size.rows,numberCellColumns:size.columns,numberBrailleCellColumns:size.text,disconnect:async()=>{sdk.device.isConnect=false;sdk.message(sdk.device,DataCodes.Disconnected,'')}},
  setCallBack(m,k,down,up){Object.assign(sdk,{message:m,down,up})},
  connectBleDevice:async()=>sdk.device,
  displayTextData:(hex,_,mode)=>sdk.output.push(['text',hex,mode]),
  displayGraphicData:(hex,_,mode)=>sdk.output.push(['graphic',hex,mode])};
 return sdk;
}
async function setup(size){
 const commands=[],timers=new Map(),statuses=[];let now=0,id=0;
 const keys=new GameKeys(c=>commands.push(c),{now:()=>now,schedule:fn=>{timers.set(++id,fn);return id},unschedule:i=>timers.delete(i)});
 const input={keyDown:k=>keys.down(k),keyUp:k=>keys.up(k),command:(k,phase)=>keys.up(k,phase==='cancel')};
 const sdk=fakeSdk(size),ble=fakeBle();
 const pad=new BluetoothPad(s=>statuses.push(s),(k,phase)=>forwardKey(input,k,phase),{sdk,scanner:{startBleScan:async()=>ble}});
 await pad.connect();
 const press=key=>sdk.down(sdk.device,key,''),release=key=>sdk.up(sdk.device,key,'');
 return {pad,sdk,ble,commands,statuses,press,release,advance:ms=>{now+=ms;for(const f of [...timers.values()])f()}};
}
const frame=(on=false)=>({width:60,height:40,time_width:40,time_height:4,dots:Array.from({length:40},()=>Array(60).fill(on?1:0)),time_dots:Array.from({length:4},()=>Array(40).fill(0))});

test('F3 release produces one load command',async()=>{const s=await setup();s.press(DotPadKey.KeyFunction3);s.release(DotPadKey.KeyFunction3);assert.deepEqual(s.commands,['load'])});
test('holding F3 saves once, without a load on release',async()=>{const s=await setup();s.press(DotPadKey.KeyFunction3);s.advance(900);s.release(DotPadKey.KeyFunction3);assert.deepEqual(s.commands,['save'])});
test('disconnect cancels an unfinished hold',async()=>{const s=await setup();s.press(DotPadKey.KeyFunction3);await s.pad.disconnect();s.advance(1000);assert.deepEqual(s.commands,[]);assert.equal(s.pad.connected,false)});
test('F1 F2 F4 and panning use the current key mapping',async()=>{const s=await setup();for(const k of [DotPadKey.KeyFunction1,DotPadKey.KeyFunction2,DotPadKey.KeyFunction4,DotPadKey.PanningLeft,DotPadKey.PanningRight]){s.press(k);s.release(k)}assert.deepEqual(s.commands,['minimap','resources','pause','left','right'])});
test('repeated key-down edges never toggle menus repeatedly',async()=>{const s=await setup();for(let i=0;i<3;i++)s.press(DotPadKey.KeyFunction2);s.release(DotPadKey.KeyFunction2);assert.deepEqual(s.commands,['resources'])});
test('pan release does not release a held F3',async()=>{const s=await setup();s.press(DotPadKey.KeyFunction3);s.press(DotPadKey.PanningLeft);s.release(DotPadKey.PanningLeft);s.advance(800);assert.deepEqual(s.commands,['left','save']);s.release(DotPadKey.KeyFunction3);assert.deepEqual(s.commands,['left','save'])});
test('a dropped Bluetooth link cancels held keys and pauses output',async()=>{const s=await setup();s.press(DotPadKey.KeyFunction3);s.ble.drop();s.advance(1000);assert.deepEqual(s.commands,[]);s.pad.update(frame(true));assert.deepEqual(s.sdk.output,[]);assert.equal(s.pad.pending.dots[0][0],1);s.pad.release()});
test('SDK disconnect notice clears the connection',async()=>{const s=await setup();await s.sdk.device.disconnect();assert.equal(s.pad.device,null);assert.equal(s.statuses.at(-1),'Bluetooth disconnected')});
test('frames go to the text line and graphic area once',async()=>{const s=await setup();s.pad.update(frame(true));s.pad.update(frame(true));assert.equal(s.sdk.output.length,2);const [[k1,text,m1],[k2,graphic,m2]]=s.sdk.output;assert.deepEqual([k1,m1,k2,m2],['text','TextMode','graphic','GraphicMode']);assert.equal(text,'00'.repeat(20));assert.equal(graphic,'ff'.repeat(300))});
test('only the changed area is sent again',async()=>{const s=await setup();s.pad.update(frame());const next=frame();next.time_dots[0][0]=1;s.pad.update(next);assert.deepEqual(s.sdk.output.at(-1),['text','01'+'00'.repeat(19),'TextMode']);assert.equal(s.sdk.output.length,3)});
test('pads with another layout are rejected',async()=>{await assert.rejects(setup({rows:10,columns:30,text:0}),/Only 60×40/)});
test('display packing keeps the cell bit layout',()=>{const cells=packCells([[1,0],[0,1],[1,0],[0,1]],0,1);assert.equal(cells[0],0xa5);assert.equal(cellsToHex(cells),'a5')});
