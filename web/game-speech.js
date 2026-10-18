/* Fixed server-generated English speech, with cancellation and hover deferral. */
class GameSpeech {
    constructor(options = {}) {
        this.fetcher = options.fetcher || ((...args) => fetch(...args));
        this.getContext = options.getContext;
        this.onCaption = options.onCaption || (() => {});
        this.onStatus = options.onStatus || (() => {});
        this.onDucking = options.onDucking || (() => {});
        this.enabled = true;
        this.suspended = false;
        this.unlocked = false;
        this.rate = 1;
        this.volume = 0.85;
        this.outputGain = null;
        this.setVolume(options.volume ?? 0.85);
        this.sequence = 0;
        this.active = null;
        this.pending = null;
        this.pendingHover = null;
        this.pendingAction = null;
        this.last = null;
        this.cache = new Map();
        this.clientId = options.clientId || (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : 'speech-'+Date.now()+'-'+Math.random().toString(36).slice(2));
        this.serverPending = false;
    }
    async voices() {
        const response = await this.fetcher('/api/speech/voices');
        if (!response.ok) throw new Error('Could not check fixed voices');
        return response.json();
    }
    unlock() {
        if (this.suspended) return;
        this.unlocked = true;
        const context = this.getContext?.();
        if (context?.state === 'suspended') context.resume().catch(() => this.onStatus('Click Replay to enable speech'));
        if (this.pending && !this.active && this.enabled) {
            const job = this.pending;
            const deferred = this.pendingAction;
            this.pending = null;
            const playing = this.play(job);
            if (job.channel === "quest" && this.active === job) this.pendingAction = deferred;
            return playing;
        }
    }
    setRate(rate) { this.rate = Math.max(0.8, Math.min(1.5, Number(rate) || 1)); }
    setVolume(volume) {
        const value = Number(volume);
        this.volume = Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0.85;
        if (this.outputGain) this.outputGain.gain.setTargetAtTime(this.volume, this.outputGain.context.currentTime, 0.02);
    }
    setEnabled(enabled) {
        this.enabled = !!enabled;
        if (!this.enabled) this.stop('Off');
        else this.onStatus(this.suspended ? 'Away' : 'Ready');
    }
    setSuspended(suspended) {
        suspended = !!suspended;
        if (this.suspended === suspended) return;
        this.suspended = suspended;
        if (suspended) this.stop(this.enabled ? 'Away' : 'Off');
        else this.onStatus(this.enabled ? 'Ready' : 'Off');
    }
    say(text, options = {}) {
        const normalized = String(text || '').trim();
        if (!normalized) return Promise.resolve(false);
        const job = {text: normalized, profile: options.profile || 'system',
                     priority: options.priority || 'action', channel: options.channel || 'general', rate: this.rate};
        const protectedJob = this.active || this.pending;
        if (!options.silent && this.enabled && !this.suspended && protectedJob?.channel === 'quest' && job.channel !== 'quest') {
            if (job.priority !== 'hover') this.pendingAction = job;
            return Promise.resolve(false);
        }
        if (!options.silent && job.priority === 'hover' && this.active && this.active.priority !== 'hover') {
            this.pendingHover = job;
            return Promise.resolve(false);
        }
        if (!options.silent && job.priority === 'hover' && this.active?.text === job.text && this.active?.profile === job.profile) {
            return Promise.resolve(false);
        }
        this.last = job;
        this.onCaption(job.text, job.profile);
        if (options.silent || !this.enabled || this.suspended) return Promise.resolve(false);
        if (!this.unlocked) {
            this.pending = job;
            this.onStatus('Click or press a key to enable speech');
            return Promise.resolve(false);
        }
        this.pendingHover = null;
        return this.play(job);
    }
    replay() {
        if (!this.last) return Promise.resolve(false);
        return this.say(this.last.text, {profile: this.last.profile, priority: this.last.priority, channel: this.last.channel});
    }
    stop(status = this.suspended ? 'Away' : this.enabled ? 'Ready' : 'Off') {
        this.sequence++;
        if (this.serverPending) {
            Promise.resolve(this.fetcher('/api/speech/cancel', {method:'POST',keepalive:true,
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({client_id:this.clientId,sequence:this.sequence})})).catch(()=>{});
        }
        this.serverPending = false;
        this.controller?.abort();
        this.controller = null;
        const source = this.source;
        this.source = null;
        this.outputGain = null;
        if (source) { try { source.stop(); } catch {} }
        this.active = null;
        this.pending = null;
        this.pendingHover = null;
        this.pendingAction = null;
        this.onDucking(false);
        this.onStatus(status);
    }
    async play(job) {
        if (!this.enabled || this.suspended) return false;
        this.stop();
        const sequence = this.sequence;
        this.active = job;
        this.last = job;
        this.onCaption(job.text, job.profile);
        this.onStatus('Preparing speech');
        this.controller = new AbortController();
        const signal = this.controller.signal;
        try {
            const context = this.getContext?.();
            if (!context) throw new Error('Audio unavailable. Click Replay to retry.');
            const key = JSON.stringify([job.text, job.profile, job.rate]);
            let buffer = this.cache.get(key);
            if (!buffer) {
                this.serverPending = true;
                const response = await this.fetcher('/api/speech', {
                    method: 'POST', headers: {'Content-Type': 'application/json'}, signal,
                    body: JSON.stringify({text: job.text, profile: job.profile, rate: job.rate,
                        priority:job.priority,client_id:this.clientId,sequence})
                });
                if (sequence !== this.sequence) return false;
                this.serverPending = false;
                if (response.status === 204) {
                    this.active = null;this.controller = null;this.pendingAction = null;this.onStatus('Ready');return false;
                }
                if (!response.ok) {
                    const problem = await response.json().catch(() => ({}));
                    throw new Error(typeof problem.detail === 'string' ? problem.detail : 'Voice unavailable. Click Replay to retry.');
                }
                const audio = await response.json();
                if (sequence !== this.sequence) return false;
                const sound = await this.fetcher(audio.url, {signal});
                if (!sound.ok) throw new Error('Speech audio unavailable. Click Replay to retry.');
                buffer = await context.decodeAudioData(await sound.arrayBuffer());
                if (sequence !== this.sequence) return false;
                if (this.cache.size >= 64) this.cache.delete(this.cache.keys().next().value);
                this.cache.set(key, buffer);
            }
            if (sequence !== this.sequence || !this.enabled || this.suspended) return false;
            if (context.state === 'suspended') await context.resume();
            if (sequence !== this.sequence || !this.enabled || this.suspended) return false;
            const source = context.createBufferSource();
            const gain = context.createGain();
            gain.gain.value = this.volume;
            gain.connect(context.destination);
            source.buffer = buffer;
            source.connect(gain);
            this.source = source;
            this.outputGain = gain;
            source.onended = () => {
                source.disconnect();
                gain.disconnect();
                if (this.outputGain === gain) this.outputGain = null;
                if (sequence !== this.sequence) return;
                this.source = null;
                this.active = null;
                this.controller = null;
                this.onDucking(false);
                this.onStatus('Ready');
                const next = this.pendingAction || this.pendingHover;
                this.pendingAction = null;
                this.pendingHover = null;
                if (next && this.enabled && !this.suspended) this.play(next);
            };
            this.onDucking(true);
            this.onStatus('Speaking');
            source.start();
            return true;
        } catch (error) {
            if (sequence !== this.sequence) return false;
            this.serverPending = false;
            this.active = null;
            this.controller = null;
            this.pendingHover = null;
            this.pendingAction = null;
            this.onDucking(false);
            this.onStatus(error.name === 'AbortError' ? 'Ready' : error.message);
            return false;
        }
    }
}
if (typeof window !== 'undefined') window.GameSpeech = GameSpeech;
if (typeof module !== 'undefined') module.exports = {GameSpeech};
