// rta-sound-worklet.js - plays the sound of the native build's page: an AudioWorklet
// processor that reads stereo 16-bit samples from a ring in the program's shared memory
// (audio_out_web.h): the game's thread writes, this reads; the page's main thread is not
// involved.  The processor is the one of the emulator's page (tools/play-web/web/rta-sound.js).
//
// A reserve is held, as the desktop application's sound handler does: playing starts
// when RESERVE_MS are queued, and the amount queued is held near that by reading very
// slightly faster or slower (at most half a per cent). When the ring runs dry (the
// machine was stopped, or is too slow) silence is played and the reserve is built again.
const RESERVE_MS = 70;

class RtaRing extends AudioWorkletProcessor {
	constructor(options) {
		super();
		const { memory, ring, size } = options.processorOptions;
		this.words = new Uint32Array(memory, ring, 4);     // write, read, size, rate
		this.samples = new Int16Array(memory, ring + 16, size);
		this.mask = size - 1;
		this.playing = false;
		this.position = 0;      // fraction of a stereo frame already consumed
		this.dry = 0;           // times the ring ran dry while playing
		this.report = 0;
		this.muted = false;
		this.port.onmessage = (event) => { if("muted" in event.data) this.muted = event.data.muted; };
	}

	process(inputs, outputs) {
		const left = outputs[0][0], right = outputs[0][1] || outputs[0][0];
		const count = left.length;
		const words = this.words;
		const sourceRate = words[3] || 44100;
		const write = Atomics.load(words, 0);
		let read = Atomics.load(words, 1);
		let queued = ((write - read) >>> 0) >> 1; // stereo frames
		const reserve = (sourceRate * RESERVE_MS / 1000) | 0;
		if(!this.playing && queued >= reserve) this.playing = true;
		if(this.playing) {
			// hold the reserve: up to 0.5 % faster or slower
			let correction = (queued - reserve) / reserve * 0.01;
			correction = Math.max(-0.005, Math.min(0.005, correction));
			const step = (sourceRate / sampleRate) * (1 + correction);
			const samples = this.samples, mask = this.mask;
			let position = this.position;
			let produced = 0;
			for(; produced < count; produced++) {
				if(queued < 2) break;
				const index = read & mask, next = (read + 2) & mask;
				const fraction = position;
				left[produced] = (samples[index] + (samples[next] - samples[index]) * fraction) / 32768;
				right[produced] = (samples[index + 1] + (samples[next + 1] - samples[index + 1]) * fraction) / 32768;
				position += step;
				const whole = position | 0;
				if(whole) {
					position -= whole;
					read = (read + whole * 2) >>> 0;
					queued -= whole;
				}
			}
			if(produced < count) {
				for(let i = produced; i < count; i++) { left[i] = 0; right[i] = 0; }
				this.playing = false;
				this.dry++;
				// what is left (less than a frame) is dropped
				read = Atomics.load(words, 0);
			}
			this.position = position;
			Atomics.store(words, 1, read);
			if(this.muted) { left.fill(0); if(right !== left) right.fill(0); }
		}
		if(++this.report >= 375) { // about once a second
			this.report = 0;
			this.port.postMessage({ dry: this.dry, queuedMs: Math.round(queued * 1000 / sourceRate), playing: this.playing });
		}
		return true;
	}
}

registerProcessor("rta-ring", RtaRing);
