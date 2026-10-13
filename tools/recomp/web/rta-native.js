// rta-native.js - the page of the native build in a browser (tools/recomp/web).
//
// What a person does: opens the page, picks the disc image (it is checked - is this the
// disc the build is made for? - and stays where it is: the program asks for the pieces it
// needs and they are read from the file on the player's own computer), plays with the
// keyboard or a controller.  The memory card is kept in the browser (IndexedDB); sound
// goes through an AudioWorklet; a game played alone stands while the page is not in front.
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
//   pause=0         DEV: the game is not paused when the page is hidden (tests run unwatched)
//   check=0         DEV: the disc image is not checked
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
const SHARED = { keys: 0, unpaced: 1, shot: 2, shotW: 3, shotH: 4, shotPtr: 5, canvasW: 6, canvasH: 7, quit: 8, held: 9, sticks: 10, pause: 11,
	pad: 12, padSticks: 13, rumble: 14, pauses: 15 };
// the controller's buttons (libpad's bits) and the four stick keys above them
const BUTTONS = { select: 0x0001, l3: 0x0002, r3: 0x0004, start: 0x0008, up: 0x0010, right: 0x0020, down: 0x0040, left: 0x0080,
	l2: 0x0100, r2: 0x0200, l1: 0x0400, r1: 0x0800, triangle: 0x1000, circle: 0x2000, cross: 0x4000, square: 0x8000 };
const KEYS = { KeyW: 1 << 16, KeyS: 1 << 17, KeyA: 1 << 18, KeyD: 1 << 19,
	ArrowUp: BUTTONS.up, ArrowRight: BUTTONS.right, ArrowDown: BUTTONS.down, ArrowLeft: BUTTONS.left,
	KeyI: BUTTONS.triangle, KeyJ: BUTTONS.square, KeyK: BUTTONS.cross, KeyL: BUTTONS.circle,
	KeyQ: BUTTONS.l1, KeyE: BUTTONS.r1, Digit1: BUTTONS.l2, Digit3: BUTTONS.r2, KeyX: BUTTONS.l3, KeyC: BUTTONS.r3,
	Enter: BUTTONS.start, Backspace: BUTTONS.select };
// a controller in the browser's standard layout: button number -> the console's button
const PAD_BUTTONS = [BUTTONS.cross, BUTTONS.circle, BUTTONS.square, BUTTONS.triangle, BUTTONS.l1, BUTTONS.r1, BUTTONS.l2, BUTTONS.r2,
	BUTTONS.select, BUTTONS.start, BUTTONS.l3, BUTTONS.r3, BUTTONS.up, BUTTONS.down, BUTTONS.left, BUTTONS.right];
const GAME_EXECUTABLE = "SLUS_209.73", GAME_CRC = 0x4028A55F;

let module = null, shared = 0, state = "loading", keys = 0, keyEvents = 0, hiddenSince = 0, hiddenMs = 0;
let audio = null, soundNode = null, soundState = null;
let pauseBits = 0;          // 1: the page was hidden; 2: the player paused
const shots = [];           // DEV: pictures a script asked for: { name, number, status }
const log = [];
function note(line) { log.push(line); if(log.length > 400) log.shift(); console.log(line); }
function setStatus(text, bad) { $("status").textContent = text; $("status").className = bad ? "bad" : ""; }
const word = (index) => Atomics.load(module.HEAPU32, shared + index);
const setWord = (index, value) => Atomics.store(module.HEAPU32, shared + index, value >>> 0);

// ---- the disc image: read in place ---------------------------------------------------------
function fileReader(file) {
	return { size: file.size, name: file.name, read: (offset, length) => file.slice(offset, offset + length).arrayBuffer() };
}

// Is this the disc this build is made from?  The check of the emulator's page
// (tools/play-web/web/rta-web.js, checkDisc) and of the desktop application: SYSTEM.CNF
// names SLUS_209.73, and the program's checksum (all its 32-bit words exclusive-ored, as
// PCSX2 names its patch files) is 4028A55F.  It matters more here than there: this page
// *is* that one program, translated; with any other disc it would run its own code over
// another game's data.  Returns "" or the reason for refusing.  It reads 2.3 MB of the image.
async function checkDisc(reader) {
	const SECTOR = 2048;
	const bytesAt = async (offset, length) => new Uint8Array(await reader.read(offset, length));
	if(reader.size < 64 * SECTOR) return "this file is not a disc image (it is far too small)";
	const volume = await bytesAt(16 * SECTOR, SECTOR);
	if(String.fromCharCode(...volume.subarray(1, 6)) !== "CD001") {
		// what people pick instead: the image still packed, or in an emulator's own format
		const head = String.fromCharCode(...(await bytesAt(0, 8)));
		const packed = head.startsWith("PK") ? "a zip archive" : head.startsWith("7z") ? "a 7-Zip archive" : head.startsWith("Rar!") ? "a RAR archive" : head.startsWith("\x1f\x8b") ? "a gzip file" :
			head.startsWith("MComprHD") ? "a CHD image" : head.startsWith("CISO") ? "a CSO image" : head.startsWith("ZISO") ? "a ZSO image" : "";
		if(packed) return "this file is " + packed + ", not a plain disc image: unpack or convert it to an .iso file first and choose that";
		return "this file is not a disc image a PlayStation 2 game comes on (no ISO 9660 volume in it)";
	}
	const view = new DataView(volume.buffer, volume.byteOffset);
	const rootSector = view.getUint32(156 + 2, true), rootSize = view.getUint32(156 + 10, true);
	if((rootSector + 1) * SECTOR > reader.size) return "the disc image is damaged or cut short (its list of files lies beyond the end of the file)";
	const root = await bytesAt(rootSector * SECTOR, Math.min(rootSize, 64 * SECTOR, reader.size - rootSector * SECTOR));
	const files = {};
	for(let offset = 0; offset + 33 < root.length;) {
		const length = root[offset];
		if(length === 0) { offset = (Math.floor(offset / SECTOR) + 1) * SECTOR; continue; }
		if(length < 34 || offset + length > root.length) break;
		const entry = new DataView(root.buffer, root.byteOffset + offset, length);
		const nameLength = root[offset + 32];
		const name = String.fromCharCode(...root.subarray(offset + 33, offset + 33 + nameLength)).replace(/;1$/, "");
		files[name] = { sector: entry.getUint32(2, true), size: entry.getUint32(10, true), folder: !!(root[offset + 25] & 2) };
		offset += length;
	}
	if(!files["SYSTEM.CNF"]) return "this is not a PlayStation 2 game disc (no SYSTEM.CNF)";
	// an image cut short would start and fail later, in a level: the files named at the top must all lie inside it
	const last = Math.max(...Object.values(files).filter((f) => !f.folder).map((f) => f.sector * SECTOR + f.size));
	if(last > reader.size) return "the disc image is cut short: it is " + reader.size + " bytes long and its files reach to byte " + last + " (an unfinished copy or download)";
	const config = String.fromCharCode(...await bytesAt(files["SYSTEM.CNF"].sector * SECTOR, Math.min(files["SYSTEM.CNF"].size, 4096)));
	const boot = /BOOT2\s*=\s*cdrom0:\\?([^;\s]+)/i.exec(config);
	if(!boot) return "this is not a PlayStation 2 game disc (SYSTEM.CNF names no program)";
	if(boot[1].toUpperCase() !== GAME_EXECUTABLE) return "this is the disc of another game, or of another country's release (it names " + boot[1] + "); wanted is Champions: Return to Arms, US release, " + GAME_EXECUTABLE;
	const program = files[GAME_EXECUTABLE];
	if(!program) return "the disc image is damaged: its program " + GAME_EXECUTABLE + " is missing";
	if(program.size > (16 << 20)) return "the disc image is damaged (its program " + GAME_EXECUTABLE + " is said to be " + program.size + " bytes long)";
	const bytes = await bytesAt(program.sector * SECTOR, program.size);
	const words = new Uint32Array(bytes.buffer, bytes.byteOffset, bytes.length >> 2);
	let crc = 0;
	for(let i = 0; i < words.length; i++) crc ^= words[i];
	crc >>>= 0;
	if(crc !== GAME_CRC) return "this is Champions: Return to Arms, but not the version this page is made for, or a changed or damaged copy (its program's checksum is " + crc.toString(16).toUpperCase().padStart(8, "0") + "; wanted is version 2.00, " + GAME_CRC.toString(16).toUpperCase() + ")";
	return "";
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
	if(module || state === "starting") throw new Error("already started: reload the page for another disc image");
	if(options.check !== false && params.get("check") !== "0") {
		setStatus("Checking the disc image…");
		let refusal;
		try { refusal = await checkDisc(reader); } catch(e) {
			refusal = "the file could not be read (" + (/NotReadable|NotFound|Security|NotAllowed/.test(e.name) ? "the browser may not read it any more, or it is no longer where it was" : e.message) + ")";
		}
		if(refusal) {
			note("disc: refused: " + refusal);
			setStatus("Not started: " + refusal + ".", true);
			return false;
		}
	}
	if(!crossOriginIsolated) { setStatus("This page was served without the cross-origin isolation headers; the program's threads cannot start. Use serve.py.", true); state = "failed"; return false; }
	state = "starting";
	setStatus("Starting…");
	try {
		await loadProgram();
		module = await window.RtaNative({ canvas: $("canvas"), print: (t) => note(t), printErr: (t) => note(t), locateFile: (name) => name });
	} catch(e) { setStatus("The program could not be loaded: " + e.message, true); state = "failed"; return false; }
	module.rtaDisc = reader;
	module.rtaShot = takeScriptShot;
	module.rtaEnded = (code) => { state = "ended"; setStatus("The game ended (" + code + ")." + (log.length ? " " + log[log.length - 1] : ""), code !== 0); };
	shared = module._rta_web_shared() >> 2;
	// the memory card: plain files under /data/card, kept in IndexedDB
	const FS = module.FS;
	FS.mkdir("/data");
	FS.mkdir("/data/card");
	if(options.card !== false && params.get("card") !== "0") {
		FS.mount(module.IDBFS, {}, "/data/card");
		await new Promise((done) => FS.syncfs(true, (error) => { if(error) note("memory card: could not be read from the browser's store (" + error + ")"); done(); }));
		cardKept = true;
		setInterval(saveCard, 4000);
		note("memory card: kept in this browser; " + cardFiles().length + " files on it");
	} else note("memory card: not kept (a blank one for this run)");
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
	const built = info();
	note("page: this copy computes " + (built.arith === "zero" ? "as the Mac and Windows programs do (toward zero)" : "as the emulator's page does (to nearest)") +
		"; vertex programs " + (built.vu_arith === "zero" ? "toward zero" : "to nearest") + (built.simd ? ", four at a time" : ""));
	setStatus("Running.");
	$("choose").disabled = true;
	$("pause").disabled = false;
	if(pauseBits) applyPause();
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

// ---- the memory card's store ---------------------------------------------------------------------
let cardKept = false, cardWriting = false, cardAgain = false;
// the card's files go to the browser's store (IndexedDB): every 4 s, and when the page is left
function saveCard() {
	if(!cardKept || !module) return Promise.resolve("not kept");
	if(cardWriting) { cardAgain = true; return Promise.resolve("busy"); }
	cardWriting = true;
	return new Promise((done) => module.FS.syncfs(false, (error) => {
		cardWriting = false;
		if(error) note("memory card: could not be written to the browser's store (" + error + ")");
		if(cardAgain) { cardAgain = false; saveCard(); }
		done(error ? String(error) : "ok");
	}));
}
function cardFiles() {
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
}
window.addEventListener("pagehide", () => { saveCard(); });

// ---- pause ----------------------------------------------------------------------------------------
// A game played alone stands while the page is not in front (a browser gives a hidden page
// little time and no pictures, and nobody is watching), and when the player asks.  It goes
// on at a click, a key or a controller button - not by itself when the page comes back, so
// that nobody returns into a fight.
function applyPause() {
	if(!module) return;
	setWord(SHARED.pause, pauseBits);
	Atomics.notify(module.HEAP32, shared + SHARED.pause);
	$("paused").hidden = !pauseBits;
	$("pausedWhy").textContent = pauseBits & 1 ? "Paused: the page was not in front." : "Paused.";
	$("pause").textContent = pauseBits ? "Go on" : "Pause";
	if(soundNode) soundNode.port.postMessage({ paused: !!pauseBits });
	if(audio) (pauseBits || !$("sound").checked ? audio.suspend() : audio.resume()).catch(() => {});
	// the game goes on at once and the sound device a moment later: what queued up meanwhile is given up, so that the
	// sound is its 70 ms behind again and not a fifth of a second
	if(!pauseBits && soundNode) for(const after of [400, 1200]) setTimeout(() => { if(!pauseBits) soundNode.port.postMessage({ resync: true }); }, after);
	if(pauseBits) { keys = 0; setWord(SHARED.keys, 0); setWord(SHARED.pad, 0); setWord(SHARED.padSticks, 0x80808080); saveCard(); }
	note(pauseBits ? "paused (" + (pauseBits & 1 ? "hidden" : "asked") + ")" : "going on");
}
function pause(bit) { if(state !== "running" || (pauseBits & bit)) return; pauseBits |= bit; applyPause(); }
function resume() { if(!pauseBits) return; pauseBits = 0; applyPause(); $("canvas").focus(); }

// ---- a controller (the browser's Gamepad interface) ----------------------------------------------
// The controller in use is the one a button was pressed on last: a browser shows a
// controller to a page only after a button press on it.  Buttons and sticks are read every
// 4 ms and written to the program's shared words; the game reads them at its next
// vertical blank.  Only the standard layout is known here (the emulator's page can be
// taught others: not built for this one).
let padInUse = -1, padName = "", padHeld = false, padTimer = 0, lastRumble = 0, padEvents = 0;
const buttonValue = (button) => !button ? 0 : Math.max(button.value || 0, button.pressed && !(button.value > 0) ? 1 : 0);
const padBusy = (pad) => pad.buttons.some((button) => buttonValue(button) > 0.5);
function activePad() {
	let pads = [];
	try { pads = navigator.getGamepads ? Array.from(navigator.getGamepads()).filter((pad) => pad && pad.connected) : []; } catch(e) { /* not allowed here */ }
	let pad = pads.find((one) => one.index === padInUse) || null;
	if(!pad || !padBusy(pad)) pad = pads.find((one) => one !== pad && padBusy(one)) || pad;
	if(!pad) { padInUse = -1; return null; }
	if(pad.index !== padInUse || pad.id !== padName) {
		padInUse = pad.index;
		padName = pad.id;
		note("controller: " + pad.id + " (" + (pad.mapping === "standard" ? "standard layout" : "no standard layout in this browser: its buttons may be in other places") + ")");
	}
	return pad;
}
// a stick's axis as the console's byte: nothing inside 15 % of the way, then evenly to the edge
function axisByte(value) {
	const far = Math.abs(value || 0) < 0.15 ? 0 : Math.min(1, (Math.abs(value) - 0.15) / 0.85);
	return Math.max(0, Math.min(255, Math.round(128 + (value < 0 ? -128 : 127) * far)));
}
function readPad() {
	if(!module || state !== "running") return;
	const pad = activePad();
	if(!pad) { if(padEvents) { setWord(SHARED.pad, 0); setWord(SHARED.padSticks, 0x80808080); padEvents = 0; } return; }
	if(pauseBits) {
		// a button ends the pause; that press is not passed on to the game
		if(!document.hidden && padBusy(pad)) { padHeld = true; resume(); }
		return;
	}
	if(padHeld) { if(padBusy(pad)) return; padHeld = false; }
	let bits = 0;
	for(let i = 0; i < PAD_BUTTONS.length; i++) if(buttonValue(pad.buttons[i]) > (i === 6 || i === 7 ? 0.3 : 0.5)) bits |= PAD_BUTTONS[i];     // a trigger counts beyond 30 %
	if(pad.mapping === "standard" && buttonValue(pad.buttons[17]) > 0.3) bits |= BUTTONS.select;        // a PlayStation pad's touchpad
	const sticks = (axisByte(pad.axes[0]) | axisByte(pad.axes[1]) << 8 | axisByte(pad.axes[2]) << 16 | axisByte(pad.axes[3]) << 24) >>> 0;
	if(bits !== word(SHARED.pad) || sticks !== word(SHARED.padSticks)) padEvents++;
	setWord(SHARED.pad, bits);
	setWord(SHARED.padSticks, sticks);
	// the game's rumble: small motor (on or off) and large motor (0..255)
	const rumble = word(SHARED.rumble);
	if(rumble !== lastRumble) {
		lastRumble = rumble;
		const small = rumble & 255, large = (rumble >> 8) & 255, motor = pad.vibrationActuator;
		try {
			if(motor && motor.playEffect) {
				if(small || large) motor.playEffect("dual-rumble", { duration: 5000, weakMagnitude: small ? 1 : 0, strongMagnitude: large / 255 });
				else if(motor.reset) motor.reset();
			}
		} catch(e) { /* a controller without motors */ }
	}
}
function watchPads() { if(!padTimer) padTimer = setInterval(readPad, 4); }
window.addEventListener("gamepadconnected", (event) => { note("controller connected: " + event.gamepad.id); watchPads(); });
window.addEventListener("gamepaddisconnected", (event) => { note("controller disconnected: " + event.gamepad.id); });

// ---- keyboard -------------------------------------------------------------------------------
function key(event, down) {
	if(down && pauseBits && state === "running" && !event.metaKey && !event.ctrlKey && !event.altKey) { event.preventDefault(); if(!event.repeat) resume(); return; }     // any key ends a pause and is not passed on
	if(down && event.code === "KeyP" && state === "running" && !event.repeat && !event.metaKey && !event.ctrlKey && !event.altKey) { event.preventDefault(); pause(2); return; }
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
	if(document.hidden) { saveCard(); if(params.get("pause") !== "0") pause(1); }
});
const hiddenSeconds = () => (hiddenMs + (hiddenSince ? performance.now() - hiddenSince : 0)) / 1000;

// ---- figures -----------------------------------------------------------------------------------
function info() {
	const data = JSON.parse(module.UTF8ToString(module._rta_web_info()));
	data.hidden_s = hiddenSeconds();
	data.key_events = keyEvents;
	data.sound_state = soundState;
	data.paused = pauseBits;
	data.pad = { events: padEvents, name: padName, buttons: word(SHARED.pad), sticks: word(SHARED.padSticks) };
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
			(soundState ? "   sound: " + soundState.queuedMs + " ms queued, ran dry " + soundState.dry + " times" : "") + "   level " + now.level +
			(padName ? "   controller: " + padName.replace(/\s*\((STANDARD GAMEPAD\s*)?Vendor:.*$/i, "") : "");
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

// DEV: a script line "app shot NAME.png" - the picture of that vertical blank, copied here
// and now (the program's thread waits for this call), then posted to the local test server
function takeScriptShot(name, pointer, width, height, number) {
	const pixels = new Uint8ClampedArray(width * height * 4);
	pixels.set(module.HEAPU8.subarray(pointer, pointer + pixels.length));
	for(let i = 3; i < pixels.length; i += 4) pixels[i] = 255;
	const entry = { name, number, width, height, status: 0 };
	shots.push(entry);
	const canvas = new OffscreenCanvas(width, height);
	canvas.getContext("2d").putImageData(new ImageData(pixels, width, height), 0, 0);
	entry.done = canvas.convertToBlob({ type: "image/png" }).then((blob) => fetch("/shot/" + encodeURIComponent(name), { method: "POST", body: blob }))
		.then((r) => { entry.status = r.status; }, (e) => { entry.status = -1; note("shot " + name + ": " + e); });
	note("shot: " + name + " at blank " + number + ", " + width + " x " + height);
}

// ---- the page's controls ------------------------------------------------------------------------
$("choose").addEventListener("click", () => $("file").click());
$("file").addEventListener("change", async () => {
	const file = $("file").files[0];
	if(!file) return;
	note("disc: " + file.name + ", " + file.size + " bytes, picked from this computer");
	let started = false;
	try { started = await boot(fileReader(file), pickedOptions || {}); } catch(e) { setStatus(e.message, true); }
	if(!started && !module) $("file").value = "";        // the same file can be chosen again after it was put right
});
$("pause").addEventListener("click", () => { if(pauseBits) resume(); else pause(2); });
$("paused").addEventListener("click", resume);
let pickedOptions = null;   // DEV: options for the start that follows a picked file (rta.optionsForPick)
$("limit").addEventListener("change", () => { if(module) setWord(SHARED.unpaced, $("limit").checked ? 0 : 1); });
$("sound").addEventListener("change", () => { if(audio) ($("sound").checked && !pauseBits ? audio.resume() : audio.suspend()); });

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
	cardFiles, syncCard: saveCard,
	pause: () => pause(2), resume, paused: () => pauseBits,
	optionsForPick: (options) => { pickedOptions = options; },
	checkDisc: (file) => checkDisc(fileReader(file)),
	checkBytes: (bytes, size) => checkDisc({ size: size || bytes.length, read: async (offset, length) => { const out = new Uint8Array(length); out.set(bytes.subarray(offset, Math.min(bytes.length, offset + length))); return out.buffer; } }),
	shots, shotsDone: () => Promise.all(shots.map((s) => s.done)).then(() => shots.map((s) => ({ name: s.name, number: s.number, status: s.status, width: s.width, height: s.height }))),
	watchPads,
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
	watchPads();
	if(params.get("disc")) {
		try { await boot(await urlReader(params.get("disc"))); } catch(e) { setStatus(e.message, true); state = "failed"; }
	}
})();
