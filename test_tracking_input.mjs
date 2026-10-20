import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('./web/hardware.mjs',import.meta.url),'utf8').replace(/^export /gm,'');

function fixture(){
 const elements=new Map(),events=[],timers=[];let now=0;
 function element(id){
  if(!elements.has(id))elements.set(id,{handlers:{},disabled:false,value:'ws://127.0.0.1:8765',
   addEventListener(type,handler){this.handlers[type]=handler},setAttribute(){}});
  return elements.get(id);
 }
 const socket={close(){this.onclose?.()}};
 const input={move:(x,y)=>events.push(['move',x,y]),press:()=>events.push('press'),
  release:()=>events.push('release'),command:key=>events.push(key),state:()=>({})};
 const context={document:{getElementById:element},window:{DotdewInput:input,addEventListener(){}},
  navigator:{},URL,console,Date:{now:()=>now},setTimeout,clearTimeout,clearInterval(){},
  setInterval:handler=>timers.push(handler),WebSocket:function(){return socket}};
 vm.runInNewContext(source,context,{importModuleDynamically:()=>Promise.reject(new Error('SDK not needed for tracking'))});
 element('tracking-button').handlers.click();socket.onopen();
 return {events,elements,send:data=>socket.onmessage({data:JSON.stringify(data)}),
  press:()=>element('tracking-hold').handlers.click(),advance:ms=>{now+=ms;timers.forEach(callback=>callback())}};
}

const position={type:'tracking',hand_detected:true,pad_detected:true,pad:{x:10,y:12},gesture:'pressed'};

test('tracking coordinates move the pointer without gesture clicks',()=>{
 const f=fixture();f.send(position);f.send({...position,pad:{x:11,y:13},gesture:'hover'});
 assert.deepEqual(f.events,[['move',10,12],['move',11,13]]);
 assert.equal(f.elements.get('tracking-hold').disabled,false);
});

test('manual selection remains available and lost coordinates release it',()=>{
 const f=fixture();f.send(position);f.press();assert.equal(f.events.at(-1),'press');
 f.send({...position,hand_detected:false,pad:null});assert.equal(f.events.at(-1),'release');
 assert.equal(f.elements.get('tracking-hold').disabled,true);
});

test('legacy frames work and a timeout ends manual selection',()=>{
 const f=fixture();f.send({type:'frame',hand_detected:true,scaled_tip:[8,9]});
 assert.deepEqual(f.events,[['move',8,9]]);f.press();f.advance(1600);
 assert.equal(f.events.at(-1),'release');assert.equal(f.elements.get('tracking-hold').disabled,true);
});
