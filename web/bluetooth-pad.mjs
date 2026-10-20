// Bluetooth Dot Pad adapter built on the vendored DotPadSDK (web/vendor).
// The SDK owns the BLE link, packet framing, ACK/retry, diffing and reconnection;
// this adapter only converts game frames to cell hex and pad keys to game keys.
import {DotPadSDK,DotPadScanner,DataCodes,DotPadKey,DisplayMode} from './vendor/DotPadSDK-3.0.3.js';

// One byte per cell: left column rows 0-3 in bits 0-3, right column in bits 4-7.
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
export function cellsToHex(cells) {
    return Array.from(cells,byte=>byte.toString(16).padStart(2,'0')).join('');
}
// SDK key edges -> the key names GameKeys already understands.
const PAD_KEYS = {
    [DotPadKey.KeyFunction1]:'F1',[DotPadKey.KeyFunction2]:'F2',
    [DotPadKey.KeyFunction3]:'F3',[DotPadKey.KeyFunction4]:'F4',
    [DotPadKey.PanningLeft]:'ArrowLeft',[DotPadKey.PanningRight]:'ArrowRight',
};

export function forwardKey(input, key, phase) {
    if (!input) return;
    if (phase === 'down' && input.keyDown) return input.keyDown(key);
    if (phase === 'up' && input.keyUp) return input.keyUp(key);
    return input.command(key, phase);
}

export class BluetoothPad {
    constructor(onStatus,onCommand,{sdk=new DotPadSDK(),scanner=new DotPadScanner()}={}){
        this.onStatus=onStatus;this.onCommand=onCommand;this.sdk=sdk;this.scanner=scanner;
        this.device=null;this.ble=null;this.held=new Set();this.linkLost=false;this.pending=null;this.shown={};
        this.onLinkLost=()=>this.linkDropped();
        sdk.setCallBack((device,code)=>this.handleMessage(device,code),null,
            (device,key)=>this.keyDown(device,key),(device,key)=>this.keyUp(device,key));
    }
    get connected(){return !!this.device?.isConnect;}
    async connect(){
        if(!globalThis.navigator?.bluetooth)throw new Error('Use Chrome or Edge on localhost with Bluetooth enabled.');
        // Chooser filtered to names starting with "DotPad" and the pad's GATT service.
        const ble=await this.scanner.startBleScan();
        if(!ble)throw new Error('Device selection cancelled');
        this.onStatus('Bluetooth connecting · '+(ble.name||'Dot Pad'));
        // Resolves after the SDK handshake (device name + board info) finishes.
        const device=await this.sdk.connectBleDevice(ble);
        if(!device){try{ble.gatt?.disconnect();}catch{}throw new Error('Bluetooth connection failed. Turn the pad on and try again.');}
        if(device.numberCellRows!==10||device.numberCellColumns!==30||device.numberBrailleCellColumns!==20){
            await device.disconnect().catch(()=>{});
            throw new Error('Only 60×40 / 40×4 pads are supported.');
        }
        this.device=device;this.ble=ble;this.linkLost=false;this.shown={};
        ble.addEventListener('gattserverdisconnected',this.onLinkLost);
        this.onStatus('Bluetooth connected · '+(ble.name||'Dot Pad'));
    }
    handleMessage(device,code){
        // Sent after an explicit disconnect or once the SDK gives up reconnecting.
        if(device!==this.device||code!==DataCodes.Disconnected)return;
        this.release();this.onStatus('Bluetooth disconnected');
    }
    keyDown(device,key){
        const name=PAD_KEYS[key];
        if(device!==this.device||!name||this.held.has(name))return;
        this.held.add(name);this.onCommand(name,'down');
    }
    keyUp(device,key){
        const name=PAD_KEYS[key];
        if(device!==this.device||!this.held.delete(name))return;
        this.onCommand(name,'up');
    }
    cancelKeys(){
        const held=[...this.held];this.held.clear();
        for(const name of held)this.onCommand(name,'cancel');
    }
    linkDropped(){
        // The SDK retries the GATT link on its own; hold output until it is back.
        if(!this.device)return;
        this.cancelKeys();this.linkLost=true;this.onStatus('Bluetooth link lost · Reconnecting');
        clearInterval(this.watch);let seen=0;
        this.watch=setInterval(()=>{
            if(!this.device){clearInterval(this.watch);return;}
            // Two consecutive checks give the SDK time to rebind the characteristics.
            seen=this.ble.gatt.connected?seen+1:0;
            if(seen<2)return;
            clearInterval(this.watch);this.linkLost=false;this.onStatus('Bluetooth reconnected');
            if(this.pending){const state=this.pending;this.pending=null;this.update(state);}
        },500);
    }
    update(state){
        if(!this.connected||!state)return;
        if(state.width!==60||state.height!==40||state.time_width!==40||state.time_height!==4){this.onStatus('Only 60×40 / 40×4 pads are supported.');return;}
        if(this.linkLost){this.pending=state;return;}
        const text=cellsToHex(packCells(state.time_dots,0,20));
        const graphic=Array.from({length:10},(_,i)=>cellsToHex(packCells(state.dots,i*4,30))).join('');
        // Skip identical frames; the SDK sends only the changed cell range of each line.
        if(text!==this.shown.text){this.shown.text=text;this.sdk.displayTextData(text,this.device,DisplayMode.TextMode);}
        if(graphic!==this.shown.graphic){this.shown.graphic=graphic;this.sdk.displayGraphicData(graphic,this.device,DisplayMode.GraphicMode);}
    }
    release(){
        clearInterval(this.watch);this.cancelKeys();
        this.ble?.removeEventListener('gattserverdisconnected',this.onLinkLost);
        const device=this.device;this.device=null;this.ble=null;this.linkLost=false;this.pending=null;this.shown={};
        return device;
    }
    async disconnect(){
        const device=this.release();
        if(device?.isConnect){try{await device.disconnect();}catch{}}
        this.onStatus('Bluetooth disconnected');
    }
}
