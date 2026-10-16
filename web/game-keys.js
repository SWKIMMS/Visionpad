/* One press produces one command, including auto-repeat and cancelled holds. */
class GameKeys {
    constructor(send, options = {}) {
        this.send = send;
        this.holdMs = options.holdMs || 800;
        this.schedule = options.schedule || setTimeout;
        this.unschedule = options.unschedule || clearTimeout;
        this.now = options.now || (() => performance.now());
        this.pressed = new Map();
    }
    down(key) {
        key = String(key).toUpperCase();
        if (this.pressed.has(key)) return;
        // TEMP_EVALUATION_CLICK: restore F4:'pause' after the evaluation.
        const commands = {F1:'minimap', F2:'resources', F4:'click', ARROWLEFT:'left', ARROWRIGHT:'right'};
        if (key !== 'F3' && !commands[key]) return;
        const press = {long:false, timer:null, started:this.now()};
        this.pressed.set(key, press);
        if (key === 'F3') {
            press.timer = this.schedule(() => {
                if (this.pressed.get(key) !== press) return;
                press.long = true;
                this.send('save');
            }, this.holdMs);
        } else this.send(commands[key]);
    }
    up(key, cancelled = false) {
        key = String(key).toUpperCase();
        const press = this.pressed.get(key);
        if (!press) return;
        this.pressed.delete(key);
        if (press.timer !== null) this.unschedule(press.timer);
        if (key === 'F3' && !press.long && !cancelled) {
            // A delayed timer must not turn a genuine long press into a short press.
            this.send(this.now()-press.started >= this.holdMs ? 'save' : 'load');
        }
    }
    cancel() { for (const key of [...this.pressed.keys()]) this.up(key, true); }
}
if (typeof window !== 'undefined') window.GameKeys = GameKeys;
if (typeof module !== 'undefined') module.exports = {GameKeys};
