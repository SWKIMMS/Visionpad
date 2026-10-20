// Frame-state edges prevent held gestures from producing repeated clicks.
export class TrackingGestureInput {
    constructor(input){this.input=input;this.pressed=false;this.ready=false;}
    reset(){
        if(this.pressed)this.input.command('release');
        this.pressed=false;this.ready=false;
    }
    update(point,pressed){
        this.input.move(point[0],point[1]);
        // After connect/loss, observe an open thumb before permitting a press.
        if(!this.ready){if(!pressed)this.ready=true;return;}
        if(pressed&&!this.pressed){this.pressed=true;this.input.press();}
        else if(!pressed&&this.pressed){this.pressed=false;this.input.release();}
    }
}

// Independent adapter for the packet layout in eun022/hand_drawing.
// Reference commit: 2fdfa07c7f61cdc5a6603c33fc8b643a2b4036fb.
export function packCells(dots, y, columns) {
    return Uint8Array.from({length:columns},(_,cell)=>{
        let bits=0;
        for(let row=0;row<4;row++) {
            if(dots[y+row]?.[cell*2]) bits|=1<<row;
            if(dots[y+row]?.[cell*2+1]) bits|=1<<(row+4);
        }
        return bits;
    });
}
export function displayPacket(line, cells) {
    const body=Uint8Array.from([line,2,0,line===0?128:0,0,...cells]);
    let check=0xa5;for(const byte of body)check^=byte;
    const length=body.length+1;
    return Uint8Array.from([0xaa,0x55,length>>8,length&255,...body,check]);
}
export function extractPackets(buffer) {
    const packets=[];let data=Array.from(buffer);
    while(data.length>=4) {
        if(data[0]!==0xaa||data[1]!==0x55){data.shift();continue;}
        const size=(data[2]<<8)+data[3]+4;
        if(size<9||size>1024){data.shift();continue;}
        if(data.length<size)break;
        const packet=data.splice(0,size);let check=0xa5;
        for(const byte of packet.slice(4,-1))check^=byte;
        if(check===packet.at(-1))packets.push(packet);
    }
    return {packets,rest:data};
}
// High-nibble function-key bits already used by this adapter's packet format.
const FUNCTION_KEYS = [[8,'F1'],[4,'F2'],[2,'F3'],[1,'F4']];
// Perkins notification 0x0312: keys 13/14, MSB-first, are panning left/right.
// Protocol cross-check: nvaccess/nvda source/brailleDisplayDrivers/dotPad/{defs,driver}.py
const PANNING_KEYS = [[4,'ArrowLeft'],[2,'ArrowRight']];

export function forwardKey(input, key, phase) {
    if (!input) return;
    if (phase === 'down' && input.keyDown) return input.keyDown(key);
    if (phase === 'up' && input.keyUp) return input.keyUp(key);
    return input.command(key, phase);
}

export class SerialPad {
    constructor(onStatus,onCommand){this.onStatus=onStatus;this.onCommand=onCommand;this.previous=[];this.buffer=[];this.mask=0;this.panMask=0;this.pending=null;this.busy=false;}
    async connect(){
        if(!navigator.serial)throw new Error('Use Chrome or Edge on localhost for USB access.');
        this.port=await navigator.serial.requestPort({filters:[{usbVendorId:1027,usbProductId:24592},{usbVendorId:1027,usbProductId:24597}]});
        await this.port.open({baudRate:115200,dataBits:8});
        this.writer=this.port.writable.getWriter();this.reader=this.port.readable.getReader();this.connected=true;
        this.previous=[];this.buffer=[];this.mask=0;this.panMask=0;this.readTask=this.read();this.onStatus('USB connected · Checking output');
    }
    async read(){
        try{
            while(this.connected){
                const {value,done}=await this.reader.read();if(done)break;
                const parsed=extractPackets([...this.buffer,...value]);this.buffer=parsed.rest;
                for(const p of parsed.packets){
                    if(p[5]===2&&p[6]===1&&this.ack&&this.ack.line===p[4]){
                        const ack=this.ack;this.ack=null;
                        p[8]===0?ack.resolve():ack.reject(new Error('The pad rejected the output.'));
                    }
                    this.handleKeyPacket(p);
                }
            }
        }catch(error){if(this.connected)this.onStatus('USB input stopped: '+error.message);}
        finally{this.connected=false;this.cancelKeys();this.reader.releaseLock();this.onStatus('USB disconnected');}
    }
    handleKeyPacket(packet) {
        if(packet.length < 10 || packet[5]!==3)return;
        let keys, property, next;
        if(packet[6]===0x32){
            keys=FUNCTION_KEYS;property='mask';next=(packet[8]>>4)&15;
        }else if(packet[6]===0x12 && packet.length>=11){
            keys=PANNING_KEYS;property='panMask';next=packet[9]&6;
        }else return;
        const previous=this[property];this[property]=next;
        for(const [bit,key] of keys){
            if((next&bit)&&!(previous&bit))this.onCommand(key,'down');
            else if(!(next&bit)&&(previous&bit))this.onCommand(key,'up');
        }
    }
    cancelKeys() {
        const groups=[[FUNCTION_KEYS,this.mask],[PANNING_KEYS,this.panMask]];
        this.mask=0;this.panMask=0;
        for(const [keys,previous] of groups){
            for(const [bit,key] of keys)if(previous&bit)this.onCommand(key,'cancel');
        }
    }
    update(state){
        if(!this.connected||!state)return;
        if(state.width!==60||state.height!==40||state.time_width!==40||state.time_height!==4){this.onStatus('Only 60×40 / 40×4 pads are supported.');return;}
        this.pending=state;if(!this.busy)this.flush();
    }
    async send(line,bytes){
        let timer;
        const response=new Promise((resolve,reject)=>{
            this.ack={line,resolve,reject};
            timer=setTimeout(()=>{this.ack=null;reject(new Error('No pad response. Check the USB connection.'));},900);
        });
        // Observe the ACK immediately, including a write failure or disconnect.
        const result=response.then(()=>null,error=>error);
        try{await this.writer.write(displayPacket(line,bytes));const error=await result;if(error)throw error;}
        finally{clearTimeout(timer);this.ack=null;}
    }
    async flush(){
        this.busy=true;
        try{
            while(this.pending&&this.connected){
                const state=this.pending;this.pending=null;
                const lines=[packCells(state.time_dots,0,20),...Array.from({length:10},(_,i)=>packCells(state.dots,i*4,30))];
                for(let line=0;line<lines.length;line++){
                    const key=Array.from(lines[line]).join(',');
                    if(this.previous[line]===key)continue;
                    await this.send(line,lines[line]);this.previous[line]=key;
                }
                this.onStatus('USB connected · Output confirmed');
            }
        }catch(error){this.pending=null;await this.disconnect(false);this.onStatus(error.message);}
        finally{this.busy=false;}
    }
    async disconnect(report=true){
        this.connected=false;this.pending=null;this.cancelKeys();
        if(this.ack){this.ack.reject(new Error('USB disconnected'));this.ack=null;}
        try{await this.reader?.cancel();await this.readTask;}catch{}
        try{this.writer?.releaseLock();await this.port?.close();}catch{}
        this.writer=null;this.port=null;
        if(report)this.onStatus('USB disconnected');
    }
}
if(typeof document!=='undefined'){
    const status=document.getElementById('hardware-status');
    const pad=new SerialPad(text=>status.textContent=text,(key,phase)=>forwardKey(window.DotdewInput,key,phase));
    const usb=document.getElementById('usb-button');
    usb.addEventListener('click',async()=>{
        usb.disabled=true;
        try{
            if(pad.connected)await pad.disconnect();
            else {await pad.connect();pad.update(window.DotdewInput.state());}
        }catch(error){status.textContent=error.name==='NotFoundError'?'Device selection cancelled':error.message;await pad.disconnect(false);}
        finally{usb.disabled=false;usb.textContent=pad.connected?'Disconnect USB pad':'Connect USB pad';}
    });
    window.addEventListener('dotdew-state',event=>pad.update(event.detail));
    let socket=null,held=false,valid=false,lastFrame=0;
    const button=document.getElementById('tracking-button'),hold=document.getElementById('tracking-hold'),trackingStatus=document.getElementById('tracking-status');
    const gestureInput=new TrackingGestureInput(window.DotdewInput);
    function stopHold(){if(held)window.DotdewInput.command('release');held=false;hold.textContent='Press';hold.setAttribute('aria-pressed','false');}
    hold.addEventListener('click',()=>{
        if(!valid){trackingStatus.textContent='Waiting for valid hand coordinates.';return;}
        held=!held;window.DotdewInput[held?'press':'release']();hold.textContent=held?'Release':'Press';hold.setAttribute('aria-pressed',String(held));
    });
    button.addEventListener('click',()=>{
        if(socket){socket.close();return;}
        try{
            const address=new URL(document.getElementById('tracking-url').value);
            if(!['ws:','wss:'].includes(address.protocol))throw new Error('Enter a ws:// or wss:// address.');
            socket=new WebSocket(address.href);button.disabled=true;
            socket.onopen=()=>{button.disabled=false;button.textContent='Disconnect hand tracking';trackingStatus.textContent='Connected · Waiting for hand coordinates';};
            socket.onmessage=event=>{
                try{
                    const data=JSON.parse(event.data);
                    if(!['tracking','frame'].includes(data.type))return;
                    const pt=data.type==='tracking' ? (data.pad ? [data.pad.x,data.pad.y] : null) : data.scaled_tip;
                    valid=!!data.hand_detected && data.pad_detected!==false && data.tracking_quality!=='lost'
                        && Array.isArray(pt)&&pt.length===2&&pt.every(Number.isFinite)&&pt[0]>=0&&pt[0]<60&&pt[1]>=0&&pt[1]<40;
                    hold.disabled=!valid;lastFrame=Date.now();
                    if(!valid){gestureInput.reset();stopHold();trackingStatus.textContent='No valid hand coordinates';return;}
                    const automatic=['hover','pressed'].includes(data.gesture);
                    if(automatic){
                        hold.disabled=true;
                        if(held)stopHold();
                        gestureInput.update(pt,data.gesture==='pressed');
                    } else {
                        gestureInput.reset();
                        window.DotdewInput.move(pt[0],pt[1]);
                    }
                    trackingStatus.textContent=`Hand coordinates ${pt[0].toFixed(1)}, ${pt[1].toFixed(1)} · ${automatic?(data.gesture==='pressed'?'Thumb folded · Pressed':data.armed===false?'Open thumb to enable clicking':'Exploring'):held?'Pressed':'Exploring'}`;
                }catch{gestureInput.reset();stopHold();valid=false;hold.disabled=true;trackingStatus.textContent='Invalid hand-coordinate message';}
            };
            socket.onerror=()=>{trackingStatus.textContent='Could not connect to the hand-tracking server';};
            socket.onclose=()=>{gestureInput.reset();stopHold();valid=false;hold.disabled=true;socket=null;button.disabled=false;button.textContent='Connect hand tracking';trackingStatus.textContent='Disconnected';};
        }catch(error){socket=null;button.disabled=false;trackingStatus.textContent=error.message;}
    });
    setInterval(()=>{if(valid&&Date.now()-lastFrame>1500){valid=false;hold.disabled=true;gestureInput.reset();stopHold();trackingStatus.textContent='Hand tracking timed out';}},500);
}
