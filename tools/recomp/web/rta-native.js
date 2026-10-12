// rta-native.js - the page of the native build in a browser (tools/recomp/web).
//
// What a person does: opens the page, picks the disc image (it stays where it is: the
// program asks for the pieces it needs and they are read from the file on the player's
// own computer), plays with the keyboard.  The memory card is kept in the browser
// (IndexedDB); sound goes through an AudioWorklet.
//
// The page must be served with the two cross-origin isolation headers (serve.py does it):
// the program's threads are workers on a shared memory.
//
// Address parameters (the DEV ones are for the developer's own tests on 127.0.0.1):
//   title=TEXT      the page's title (tests: "AGENT TEST - ...")
//   scale=N         the picture is drawn at N times 640 x 448 (1..8, default 2)
//   sound=0         no sound
//   limit=0         as fast as it goes
//   card=0          DEV: the memory card is not kept (a blank one every time)
//   blend=basic     DEV: do not use the dual-source blending extension even where it exists
//   disc=URL        DEV: boot the disc image at this URL of this same local server, read by
//                   range requests (serve.py --disc); only loop-back addresses are taken
// A test drives the rest through window.rta (bottom of this file).
"use strict";

const params = new URLSearchParams(location.search);
if(params.get("title")) document.title = params.get("title");
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// words of the program's shared block (web_main.cpp, struct Shared)
const SHARED = { keys: 0, unpaced: 1, shot: 2, shotW: 3, shotH: 4, shotPtr: 5, canvasW: 6, canvasH: 7, quit: 8, held: 9, sticks: 10, hidden: 11 };
// the controller's buttons (libpad's bits) and the four stick keys above them
const BUTTONS = { select: 0x0001, l3: 0x0002, r3: 0x0004, start: 0x0008, up: 0x0010, right: 0x0020, down: 0x0040, left: 0x0080,
	l2: 0x0100, r2: 0x0200, l1: 0x0400, r1: 0x0800, triangle: 0x1000, circle: 0x2000, cross: 0x4000, square: 0x8000 };
const KEYS = { KeyW: 1 << 16, KeyS: 1 << 17, KeyA: 1 << 18, KeyD: 1 << 19,
	ArrowUp: BUTTONS.up, ArrowRight: BUTTONS.right, ArrowDown: BUTTONS.down, ArrowLeft: BUTTONS.left,
	KeyI: BUTTONS.triangle, KeyJ: BUTTONS.square, KeyK: BUTTONS.cross, KeyL: BUTTONS.circle,
	KeyQ: BUTTONS.l1, KeyE: BUTTONS.r1, Digit1: BUTTONS.l2, Digit3: BUTTONS.r2, KeyX: BUTTONS.l3, KeyC: BUTTONS.r3,
	Enter: BUTTONS.start, Backspace: BUTTONS.select };

let module = null, shared = 0, state = "loading", keys = 0, keyEvents = 0, hiddenSince = 0, hiddenMs = 0;
let audio = null, soundNode = null, soundState = null;
const log = [];
function note(line) { log.push(line); if(log.length > 400) log.shift(); console.log(line); }
function setStatus(text, bad) { $("status").textContent = text; $("status").className = bad ? "bad" : ""; }
const word = (index) => Atomics.load(module.HEAPU32, shared + index);
const setWord = (index, value) => Atomics.store(module.HEAPU32, shared + index, value >>> 0);

// ---- the disc image: read in place ---------------------------------------------------------
function fileReader(file) {
	return { size: file.size, read: (offset, length) => file.slice(offset, offset + length).arrayBuffer() };
}
// DEV: an image the developer's local server hands out by range requests
async function urlReader(address) {
	const url = new URL(address, location.href);
	if(url.origin !== location.origin || !/^(127\.0\.0\.1|localhost|\[::1\])$/.test(url.hostname)) throw new Error("disc= must be a URL of this page's own server on this computer");
	const head = await fetch(url, { method: "HEAD" });
	if(!head.ok) throw new Error("the disc image at " + url.pathname + " cannot be read (" + head.status + ")");
	const size = parseInt(head.headers.get("Content-Length"), 10);
	return { size, read: async (offset, length) => {
		const response = await fetch(url, { headers: { Range: "bytes=" + offset + "-" + (offset + length - 1) } });
		if(response.status !== 206) throw new Error("the server does not answer range requests (" + response.status + ")");
		return response.arrayBuffer();
	} };
}

// ---- start -----------------------------------------------------------------------------------
function loadProgram() {
	return new Promise((resolve, reject) => {
		if(window.RtaNative) { resolve(); return; }
		const script = document.createElement("script");
		script.src = "rta.js";
		script.onload = resolve;
		script.onerror = () => reject(new Error("rta.js is missing: build the page first (tools/recomp/web/build.py page)"));
		document.head.appendChild(script);
	});
}

// options: scale, sound, limit, card, script (text in the rig's script language: DEV), args (more program arguments: DEV)
async function boot(reader, options = {}) {
	if(module) throw new Error("already started: reload the page for another disc image");
	if(!crossOriginIsolated) { setStatus("This page was served without the cross-origin isolation headers; the program's threads cannot start. Use serve.py.", true); state = "failed"; return false; }
	state = "starting";
	setStatus("Starting…");
	try {
		await loadProgram();
		module = await window.RtaNative({ canvas: $("canvas"), print: (t) => note(t), printErr: (t) => note(t), locateFile: (name) => name });
	} catch(e) { setStatus("The program could not be loaded: " + e.message, true); state = "failed"; return false; }
	module.rtaDisc = reader;
	module.rtaEnded = (code) => { state = "ended"; setStatus("The game ended (" + code + ")." + (log.length ? " " + log[log.length - 1] : ""), code !== 0); };
	shared = module._rta_web_shared() >> 2;
	// the memory card: plain files under /data/card, kept in IndexedDB
	const FS = module.FS;
	FS.mkdir("/data");
	FS.mkdir("/data/card");
	if(options.card !== false && params.get("card") !== "0") {
		FS.mount(module.IDBFS, {}, "/data/card");
		await new Promise((done) => FS.syncfs(true, (error) => { if(error) note("memory card: could not be read from the browser's store (" + error + ")"); done(); }));
		let writing = false;
		setInterval(() => { if(!writing) { writing = true; FS.syncfs(false, () => { writing = false; }); } }, 4000);
	}
	const scale = Math.max(1, Math.min(8, parseInt(options.scale || params.get("scale") || "2", 10)));
	const args = ["--scale", String(scale)];
	const sound = options.sound !== false && params.get("sound") !== "0" && $("sound").checked;
	if(!sound) args.push("--no-sound");
	if(options.limit === false || params.get("limit") === "0") args.push("--unpaced");
	if(params.get("blend") === "basic" || options.blend === "basic") args.push("--basic-blend");
	if(options.script) { FS.writeFile("/data/script.rig", options.script); args.push("--script", "/data/script.rig"); }
	if(options.args) args.push(...options.args);
	note("page: starting with " + args.join(" ") + "; disc image of " + reader.size + " bytes");
	module.callMain(args);
	state = "running";
	setStatus("Running.");
	$("choose").disabled = true;
	if(sound) startSound().catch((e) => note("sound: " + e.message));
	setInterval(showFigures, 1000);
	$("canvas").focus();
	return true;
}

// ---- sound: an AudioWorklet that reads the program's ring --------------------------------------
async function startSound() {
	const ring = module._rta_web_sound_ring();
	if(!ring) { note("sound: this build has no sound side"); return; }
	audio = new AudioContext({ latencyHint: "interactive" });
	await audio.audioWorklet.addModule("rta-sound-worklet.js");
	const size = module.HEAPU32[(ring >> 2) + 2];
	soundNode = new AudioWorkletNode(audio, "rta-ring", { numberOfInputs: 0, outputChannelCount: [2], processorOptions: { memory: module.wasmMemory.buffer, ring, size } });
	soundNode.port.onmessage = (event) => { soundState = event.data; };
	soundNode.connect(audio.destination);
	if(audio.state !== "running") await audio.resume();
	note("sound: device at " + audio.sampleRate + " Hz, " + audio.state);
}

// ---- keyboard -------------------------------------------------------------------------------
function key(event, down) {
	const bit = KEYS[event.code];
	if(!bit || event.metaKey || event.ctrlKey || event.altKey) return;
	event.preventDefault();
	if(event.repeat) return;
	keys = down ? (keys | bit) : (keys & ~bit);
	keyEvents++;
	if(module) setWord(SHARED.keys, keys);
}
window.addEventListener("keydown", (e) => key(e, true));
window.addEventListener("keyup", (e) => key(e, false));
window.addEventListener("blur", () => { keys = 0; if(module) setWord(SHARED.keys, 0); });      // nothing stays held when the page is left
document.addEventListener("visibilitychange", () => {
	if(document.hidden) hiddenSince = performance.now();
	else if(hiddenSince) { hiddenMs += performance.now() - hiddenSince; hiddenSince = 0; }
	if(module) setWord(SHARED.hidden, document.hidden ? 1 : 0);
});
const hiddenSeconds = () => (hiddenMs + (hiddenSince ? performance.now() - hiddenSince : 0)) / 1000;

// ---- figures -----------------------------------------------------------------------------------
function info() {
	const data = JSON.parse(module.UTF8ToString(module._rta_web_info()));
	data.hidden_s = hiddenSeconds();
	data.key_events = keyEvents;
	data.sound_state = soundState;
	return data;
}
function rates(a, b) {
	const seconds = (b.now - a.now) / 1000, fields = Math.max(1, b.fields - a.fields), presents = Math.max(1, b.presents - a.presents);
	const r2 = (x) => Math.round(x * 100) / 100;
	return {
		seconds: r2(seconds), fps: r2((b.fields - a.fields) / seconds), presents_per_second: r2((b.presents - a.presents) / seconds),
		game_ms_per_frame: r2((b.game_ms - a.game_ms) / fields), decode_ms_per_frame: r2((b.decode_ms - a.decode_ms) / fields),
		draw_ms_per_frame: r2((b.draw_ms - a.draw_ms) / presents), decoder_waited_ms_per_frame: r2((b.submit_wait_ms - a.submit_wait_ms) / fields),
		draws_per_frame: Math.round((b.draws - a.draws) / presents), vertices_per_frame: Math.round((b.vertices - a.vertices) / presents),
		gl_calls_per_frame: Math.round((b.gl_calls - a.gl_calls) / presents), gl_calls_left_out_per_frame: Math.round((b.gl_skipped - a.gl_skipped) / presents),
		vu_run_ms_per_frame: r2((b.vu_run_ms - a.vu_run_ms) / fields), kick_ms_per_frame: r2((b.kick_ms - a.kick_ms) / fields), path3_ms_per_frame: r2((b.path3_ms - a.path3_ms) / fields),
		vu_runs_per_frame: Math.round((b.vu_runs - a.vu_runs) / fields), vu_translated: b.vu_translated,
		feedback_copies: b.feedback_copies - a.feedback_copies, late: b.late - a.late, sim_ticks: b.sim - a.sim, level: b.level,
		machine_seconds: r2(b.machine_s - a.machine_s), hidden_seconds: r2(b.hidden_s - a.hidden_s),
	};
}
async function measure(seconds) {
	const a = info();
	await sleep(seconds * 1000);
	return rates(a, info());
}
let lastShown = null;
function showFigures() {
	if(!module || state !== "running") return;
	const now = info();
	if(lastShown) {
		const r = rates(lastShown, now);
		$("figures").textContent = r.fps.toFixed(1) + " fields/s (59.94 is full speed)   game " + r.game_ms_per_frame.toFixed(1) + " ms   decoder " + r.decode_ms_per_frame.toFixed(1) +
			" ms   drawing " + r.draw_ms_per_frame.toFixed(1) + " ms a picture   " + r.draws_per_frame + " draws, " + r.gl_calls_per_frame + " WebGL calls" +
			(soundState ? "   sound: " + soundState.queuedMs + " ms queued, ran dry " + soundState.dry + " times" : "") + "   level " + now.level;
	}
	lastShown = now;
}

// a picture of what the program shows, as PNG bytes (rows as drawn, at the drawn size)
async function shot() {
	setWord(SHARED.shot, 1);
	for(let i = 0; i < 400 && word(SHARED.shot) !== 2; i++) await sleep(10);
	if(word(SHARED.shot) !== 2) { setWord(SHARED.shot, 0); throw new Error("no picture (nothing is shown yet)"); }
	const width = word(SHARED.shotW), height = word(SHARED.shotH), pointer = word(SHARED.shotPtr);
	const pixels = new Uint8ClampedArray(width * height * 4);
	pixels.set(module.HEAPU8.subarray(pointer, pointer + pixels.length));
	setWord(SHARED.shot, 0);
	for(let i = 3; i < pixels.length; i += 4) pixels[i] = 255;
	const canvas = new OffscreenCanvas(width, height);
	canvas.getContext("2d").putImageData(new ImageData(pixels, width, height), 0, 0);
	return canvas.convertToBlob({ type: "image/png" });
}

// ---- the page's controls ------------------------------------------------------------------------
$("choose").addEventListener("click", () => $("file").click());
$("file").addEventListener("change", () => { const file = $("file").files[0]; if(file) boot(fileReader(file)); });
$("limit").addEventListener("change", () => { if(module) setWord(SHARED.unpaced, $("limit").checked ? 0 : 1); });
$("sound").addEventListener("change", () => { if(audio) ($("sound").checked ? audio.resume() : audio.suspend()); });

// ---- for tests (and the curious, in the console) ---------------------------------------------------
window.rta = {
	get state() { return state; }, log, params, BUTTONS,
	info, measure, shot,
	bootUrl: async (address, options) => boot(await urlReader(address), options),
	bootFile: (file, options) => boot(fileReader(file), options),
	limiter: (on) => { setWord(SHARED.unpaced, on ? 0 : 1); $("limit").checked = !!on; },
	peek: (address, size = 4) => module._rta_web_peek(address, size) >>> 0,
	// hold buttons (names joined with +) for `hold` ms
	tap: async (names, hold = 80) => {
		let bits = 0;
		for(const name of names.split("+")) bits |= BUTTONS[name] || 0;
		setWord(SHARED.held, bits);
		await sleep(hold);
		setWord(SHARED.held, 0);
	},
	stick: (lx, ly, rx = 128, ry = 128) => setWord(SHARED.sticks, (lx & 255) | (ly & 255) << 8 | (rx & 255) << 16 | (ry & 255) << 24),
	// DEV: the picture is POSTed to the local test server (serve.py --shots), which keeps it under local/
	postShot: async (name) => { const blob = await shot(); const r = await fetch("/shot/" + encodeURIComponent(name), { method: "POST", body: blob }); return r.status; },
	quit: () => setWord(SHARED.quit, 1),
	// the memory card: its files in the program's file system, a write to the browser's store
	// now, and what the store holds (readable without starting the game: after a reload)
	cardFiles: () => {
		const out = [];
		const walk = (dir) => {
			for(const name of module.FS.readdir(dir)) {
				if(name === "." || name === "..") continue;
				const path = dir + "/" + name, stat = module.FS.stat(path);
				if(module.FS.isDir(stat.mode)) walk(path); else out.push([path, stat.size]);
			}
		};
		walk("/data/card");
		return out;
	},
	syncCard: () => new Promise((done) => module.FS.syncfs(false, (error) => done(error ? String(error) : "ok"))),
	storedCard: () => new Promise((done) => {
		const open = indexedDB.open("/data/card");
		open.onerror = () => done(null);
		open.onupgradeneeded = () => { open.transaction.abort(); done([]); };     // there was none
		open.onsuccess = () => {
			const db = open.result;
			if(!db.objectStoreNames.contains("FILE_DATA")) { db.close(); done([]); return; }
			const all = db.transaction("FILE_DATA").objectStore("FILE_DATA").getAllKeys();
			all.onsuccess = () => { db.close(); done(all.result); };
			all.onerror = () => { db.close(); done(null); };
		};
	}),
	forgetCard: () => new Promise((done) => { const r = indexedDB.deleteDatabase("/data/card"); r.onsuccess = r.onerror = r.onblocked = () => done(true); }),
};

(async () => {
	if(!crossOriginIsolated) { setStatus("This page was served without the cross-origin isolation headers. Use tools/recomp/web/serve.py.", true); state = "failed"; return; }
	if(!$("canvas").transferControlToOffscreen) { setStatus("This browser cannot hand a canvas to a worker (OffscreenCanvas).", true); state = "failed"; return; }
	state = "ready";
	setStatus("Ready. Choose your disc image to start.");
	if(params.get("disc")) {
		try { await boot(await urlReader(params.get("disc"))); } catch(e) { setStatus(e.message, true); state = "failed"; }
	}
})();
