// play-web: the page's side of the browser build (see ../README.md).
//
// What a person does: opens the page, picks the disc image (it is checked, remembered
// where the browser can do that, and read in place), plays with the keyboard or a
// controller. Picture factor and sound are in the menu; saved games and settings stay in
// this browser's storage.
//
// Address parameters (all optional; the ones marked DEV are for tests on the developer's
// own computer and do nothing on a page that is merely opened):
//   res=N          resolution factor for this visit (1..8; otherwise the menu's setting, 2 at first)
//   patches=0      do not apply the patch set          display=0   no display patches
//   sections=*     apply every section of the patch file instead of the suggested ones
//   sound=0        no sound
//   card=0         DEV: an empty memory card that is not kept (tests that must start the same way every time)
//   canvas=LINES   DEV: the canvas's height in pixels (default: what the page shows, at most 896)
//   gl=main        DEV: GL context on the page's main thread, as Play! itself does it
//   limit=0        DEV: the machine runs as fast as it can
//   disc=URL       DEV: boot the disc image at this URL of the same server (range requests)
//   auto=title|hub DEV: press the way to the title screen or into the first level, measure, report
//   auto=trace     DEV: into the first level, then the player's position frame by frame (standing, then walking)
//   report=1       DEV: POST the speed figures to /report of the same server once a second
//   shot=NAME.png  DEV: with auto=hub, POST one picture of the canvas in the level to /shot/NAME.png
//   title=TEXT     the page's title (tests: "AGENT TEST - browser build")
import Play from "./Play.js";

const params = new URLSearchParams(location.search);
if(params.get("title")) document.title = params.get("title");

const GAME_EXECUTABLE = "SLUS_209.73";
const GAME_CRC = 0x4028A55F;

// bit numbers: PS2::CControllerInfo::BUTTON
const B = {
	lx: 0, ly: 1, rx: 2, ry: 3, up: 4, down: 5, left: 6, right: 7, select: 8, start: 9,
	square: 10, triangle: 11, circle: 12, cross: 13, l1: 14, l2: 15, l3: 16, r1: 17, r2: 18, r3: 19,
};
const KEYS = {
	ArrowUp: B.up, ArrowDown: B.down, ArrowLeft: B.left, ArrowRight: B.right,
	KeyI: B.triangle, KeyJ: B.square, KeyK: B.cross, KeyL: B.circle,
	KeyQ: B.l1, KeyE: B.r1, Digit1: B.l2, Digit3: B.r2, KeyX: B.l3, KeyC: B.r3,
	Enter: B.start, Backspace: B.select,
};
// keys that push a stick: [stick (0 left, 1 right), axis (0 x, 1 y), direction]
const STICK_KEYS = {
	KeyA: [0, 0, -1], KeyD: [0, 0, 1], KeyW: [0, 1, -1], KeyS: [0, 1, 1],
	KeyF: [1, 0, -1], KeyH: [1, 0, 1], KeyT: [1, 1, -1], KeyG: [1, 1, 1],
};
// the Gamepad API's "standard" layout
const PAD_BUTTONS = [B.cross, B.circle, B.square, B.triangle, B.l1, B.r1, B.l2, B.r2, B.select, B.start, B.l3, B.r3, B.up, B.down, B.left, B.right, -1, B.select];

const G_IN_FRONTEND = 0x41b510, G_LEVEL_NAME = 0x41b721;

const $ = (id) => document.getElementById(id);
const statusElement = $("status");
const speedElement = $("speed");
const canvas = $("outputCanvas");
const factorElement = $("factor");
const log = [];
function note(text) {
	log.push(text);
	if(log.length > 400) log.shift();
	console.log(text);
}
function setStatus(text, bad = false) {
	statusElement.textContent = text;
	statusElement.classList.toggle("bad", bad);
	note("status: " + text);
}

// settings: this browser's storage for this site
function stored(key, fallback) {
	try { return localStorage.getItem("rta." + key) ?? fallback; } catch(e) { return fallback; }
}
function store(key, value) {
	try { localStorage.setItem("rta." + key, value); } catch(e) { /* private window */ }
}

const options = {
	factor: Math.max(1, Math.min(8, parseInt(params.get("res") || stored("factor", "2"), 10) || 2)),
	patches: params.get("patches") !== "0",
	display: params.get("display") !== "0",
	allSections: params.get("sections") === "*",
	sound: params.get("sound") !== "0",
	muted: stored("muted", "0") === "1",
	glMain: params.get("gl") === "main",
	limit: params.get("limit") !== "0",
	disc: params.get("disc"),
	auto: params.get("auto"),
	report: params.get("report") === "1",
};
factorElement.value = String(Math.min(4, options.factor));
factorElement.addEventListener("change", () => {
	options.factor = parseInt(factorElement.value, 10);
	store("factor", factorElement.value);
	// takes effect at once: the video handler makes its pictures anew at the new size
	if(module && module._rtaReady()) module._rtaSetFactor(options.factor);
	canvas.focus();
});

let module = null;
let shared = 0;           // index into HEAPU32 of the shared words
let running = false;
let audio = null;
const keysDown = new Set();
let padSeen = false;

// ---- the disc -----------------------------------------------------------------------
// A reader is { size, read(offset, length) -> Promise<Uint8Array> }.
function fileReader(file) {
	return { size: file.size, read: async (offset, length) => new Uint8Array(await file.slice(offset, offset + length).arrayBuffer()) };
}
async function urlReader(url) {
	const head = await fetch(url, { method: "HEAD" });
	if(!head.ok) throw new Error("the disc image at " + url + " cannot be read (" + head.status + ")");
	const size = parseInt(head.headers.get("content-length"), 10);
	return {
		size,
		read: async (offset, length) => {
			const response = await fetch(url, { headers: { Range: "bytes=" + offset + "-" + (offset + length - 1) } });
			if(response.status !== 206) throw new Error("the server does not answer range requests (" + response.status + ")");
			return new Uint8Array(await response.arrayBuffer());
		},
	};
}

// Is this the disc the patches and this page are for? As Rta::CheckDisc of the desktop
// application: SYSTEM.CNF names SLUS_209.73, and the program's checksum (all its 32-bit
// words exclusive-ored, as PCSX2 names its patch files) is 4028A55F. Returns "" or the
// reason for refusing.
async function checkDisc(reader) {
	const SECTOR = 2048;
	if(reader.size < 64 * SECTOR) return "this is not a disc image (too small)";
	const volume = await reader.read(16 * SECTOR, SECTOR);
	if(String.fromCharCode(...volume.subarray(1, 6)) !== "CD001") return "this is not a disc image a PlayStation 2 game comes on (no ISO 9660 volume)";
	const view = new DataView(volume.buffer, volume.byteOffset);
	const rootSector = view.getUint32(156 + 2, true), rootSize = view.getUint32(156 + 10, true);
	const root = await reader.read(rootSector * SECTOR, Math.min(rootSize, 64 * SECTOR));
	const files = {};
	for(let offset = 0; offset < root.length;) {
		const length = root[offset];
		if(length === 0) { offset = (Math.floor(offset / SECTOR) + 1) * SECTOR; continue; }
		const entry = new DataView(root.buffer, root.byteOffset + offset, length);
		const nameLength = root[offset + 32];
		const name = String.fromCharCode(...root.subarray(offset + 33, offset + 33 + nameLength)).replace(/;1$/, "");
		files[name] = { sector: entry.getUint32(2, true), size: entry.getUint32(10, true) };
		offset += length;
	}
	if(!files["SYSTEM.CNF"]) return "this is not a PlayStation 2 game disc (no SYSTEM.CNF)";
	const config = String.fromCharCode(...await reader.read(files["SYSTEM.CNF"].sector * SECTOR, Math.min(files["SYSTEM.CNF"].size, 4096)));
	const boot = /BOOT2\s*=\s*cdrom0:\\?([^;\s]+)/i.exec(config);
	if(!boot) return "this is not a PlayStation 2 game disc (SYSTEM.CNF names no program)";
	if(boot[1].toUpperCase() !== GAME_EXECUTABLE) return "this is another game (" + boot[1] + "); wanted is Champions: Return to Arms, " + GAME_EXECUTABLE;
	const program = files[GAME_EXECUTABLE];
	if(!program) return "the disc's program " + GAME_EXECUTABLE + " is missing";
	const bytes = await reader.read(program.sector * SECTOR, program.size);
	const words = new Uint32Array(bytes.buffer, bytes.byteOffset, bytes.length >> 2);
	let crc = 0;
	for(let i = 0; i < words.length; i++) crc ^= words[i];
	crc >>>= 0;
	if(crc !== GAME_CRC) return "this is Champions: Return to Arms, but another version of it (checksum " + crc.toString(16).toUpperCase().padStart(8, "0") + "; wanted is v2.00, " + GAME_CRC.toString(16).toUpperCase() + ")";
	return "";
}

function writeString(text) {
	const bytes = new TextEncoder().encode(text);
	const pointer = module._malloc(bytes.length + 1);
	module.HEAPU8.set(bytes, pointer);
	module.HEAPU8[pointer + bytes.length] = 0;
	return pointer;
}

async function boot(reader, url, name) {
	setStatus("Checking the disc image…");
	let refusal;
	try { refusal = await checkDisc(reader); } catch(e) { refusal = "the disc image could not be read (" + e.message + ")"; }
	if(refusal) {
		setStatus("Not started: " + refusal + ".", true);
		return false;
	}
	const urlPointer = writeString(url), namePointer = writeString(name);
	module._RtaWebDiscSet(urlPointer, reader.size);
	module._rtaBoot(namePointer);
	module._free(urlPointer);
	module._free(namePointer);
	running = true;
	$("start").hidden = true;
	canvas.focus();
	setStatus("Running.");
	return true;
}

// The image the player picked. It is read in place, through a URL that only this page
// can use (URL.createObjectURL): nothing is copied and nothing leaves the computer.
async function bootFile(file, handle) {
	if(discUrl) URL.revokeObjectURL(discUrl);
	discUrl = URL.createObjectURL(file);
	const ok = await boot(fileReader(file), discUrl, /\.(bin|img)$/i.test(file.name) ? "disc.bin" : "disc.iso");
	if(ok && handle) await remember("disc", handle);
	return ok;
}
let discUrl = null;

// A small store in the browser's database: the handle of the picked file can be kept
// there (browsers with the File System Access interface), so that the next visit only
// asks "may this page read it again?" instead of for the file.
function database() {
	return new Promise((resolve, reject) => {
		const request = indexedDB.open("rta-web", 1);
		request.onupgradeneeded = () => request.result.createObjectStore("kept");
		request.onsuccess = () => resolve(request.result);
		request.onerror = () => reject(request.error);
	});
}
async function remember(key, value) {
	try {
		const db = await database();
		await new Promise((resolve, reject) => {
			const transaction = db.transaction("kept", "readwrite");
			if(value === null) transaction.objectStore("kept").delete(key); else transaction.objectStore("kept").put(value, key);
			transaction.oncomplete = resolve;
			transaction.onerror = () => reject(transaction.error);
		});
	} catch(e) { note("the disc image's place could not be remembered (" + e + ")"); }
}
async function remembered(key) {
	try {
		const db = await database();
		return await new Promise((resolve, reject) => {
			const request = db.transaction("kept").objectStore("kept").get(key);
			request.onsuccess = () => resolve(request.result ?? null);
			request.onerror = () => reject(request.error);
		});
	} catch(e) { return null; }
}

$("choose").addEventListener("click", async () => {
	startSound();
	if(!window.showOpenFilePicker) { $("discFile").click(); return; }
	let handle;
	try {
		[handle] = await window.showOpenFilePicker({ id: "rta-disc", types: [{ description: "Disc image", accept: { "application/octet-stream": [".iso", ".bin", ".img"] } }] });
	} catch(e) { return; } // closed without choosing
	await bootFile(await handle.getFile(), handle);
});
$("discFile").addEventListener("change", async (event) => {
	const file = event.target.files[0];
	if(file && module) await bootFile(file, null);
});
$("resume").addEventListener("click", async () => {
	startSound();
	const handle = await remembered("disc");
	if(!handle) return;
	try {
		if((await handle.queryPermission({ mode: "read" })) !== "granted" && (await handle.requestPermission({ mode: "read" })) !== "granted") {
			setStatus("The browser was not allowed to read the image again; choose it once more.", true);
			return;
		}
		await bootFile(await handle.getFile(), handle);
	} catch(e) {
		setStatus("The remembered image is no longer where it was (" + e.name + "); choose it again.", true);
		await remember("disc", null);
		$("resume").hidden = true;
	}
});
$("change").addEventListener("click", () => { saveCard(); location.reload(); });
$("fullscreen").addEventListener("click", () => {
	$("stage").requestFullscreen?.();
	canvas.focus();
});
$("help").addEventListener("click", () => {
	const panel = $("controls");
	panel.hidden = !panel.hidden;
	$("help").setAttribute("aria-expanded", String(!panel.hidden));
	canvas.focus();
});
function showMute() {
	$("mute").textContent = options.muted ? "Sound off" : "Sound on";
	$("mute").setAttribute("aria-pressed", String(options.muted));
	audio?.node?.port.postMessage({ muted: options.muted });
}
$("mute").addEventListener("click", () => {
	options.muted = !options.muted;
	store("muted", options.muted ? "1" : "0");
	startSound();
	showMute();
	canvas.focus();
});
if(!options.sound) $("mute").hidden = true;

// ---- input --------------------------------------------------------------------------
function axisValue(v) {
	// nothing inside 15 % of the way, then evenly to the edge
	const magnitude = Math.abs(v);
	if(magnitude < 0.15) return 128;
	const scaled = Math.sign(v) * Math.min(1, (magnitude - 0.15) / 0.85);
	return Math.max(0, Math.min(255, Math.round(128 + scaled * 127)));
}

function readInput() {
	if(!module || !shared) return;
	let buttons = 0;
	const axes = [128, 128, 128, 128];
	let axesSet = 0;
	for(const code of keysDown) {
		if(code in KEYS) buttons |= 1 << KEYS[code];
		const stick = STICK_KEYS[code];
		if(stick) {
			axes[stick[0] * 2 + stick[1]] = stick[2] < 0 ? 0 : 255;
			axesSet |= 1 << stick[0];
		}
	}
	const pads = navigator.getGamepads ? navigator.getGamepads() : [];
	for(const pad of pads) {
		if(!pad || !pad.connected || pad.mapping !== "standard") continue;
		if(!padSeen) { padSeen = true; note("controller: " + pad.id); $("padname").textContent = "In use: " + pad.id; }
		pad.buttons.forEach((button, index) => {
			const bit = PAD_BUTTONS[index];
			if(bit === undefined || bit < 0) return;
			// the triggers count beyond 30 %
			const pressed = (index === 6 || index === 7) ? button.value > 0.3 : button.pressed;
			if(pressed) buttons |= 1 << bit;
		});
		for(let stick = 0; stick < 2; stick++) {
			const x = axisValue(pad.axes[stick * 2] || 0), y = axisValue(pad.axes[stick * 2 + 1] || 0);
			if(x !== 128 || y !== 128) {
				axes[stick * 2] = x;
				axes[stick * 2 + 1] = y;
				axesSet |= 1 << stick;
			}
		}
		break; // the first controller is the pad in port 1
	}
	const words = module.HEAPU32;
	words[shared + 0] = buttons;
	for(let i = 0; i < 4; i++) words[shared + 1 + i] = axes[i];
	words[shared + 5] = axesSet;
}

window.addEventListener("keydown", (event) => {
	if(!running || event.target instanceof HTMLSelectElement || event.metaKey || event.ctrlKey || event.altKey) return;
	if(event.code in KEYS || event.code in STICK_KEYS) {
		keysDown.add(event.code);
		event.preventDefault();
		startSound();
		readInput();
	}
});
window.addEventListener("keyup", (event) => {
	keysDown.delete(event.code);
	readInput();
});
window.addEventListener("blur", () => { keysDown.clear(); readInput(); });
window.addEventListener("gamepadconnected", (event) => note("controller attached: " + event.gamepad.id + " (" + (event.gamepad.mapping || "no standard layout") + ")"));
canvas.addEventListener("pointerdown", () => { canvas.focus(); startSound(); });

// ---- sound --------------------------------------------------------------------------
// A browser lets a page make sound only after the person has done something on it.
async function startSound() {
	if(!options.sound || !module) return;
	if(audio) { if(audio.context.state === "suspended") audio.context.resume(); return; }
	audio = { context: new AudioContext({ sampleRate: 44100, latencyHint: "interactive" }), dry: 0, queuedMs: 0 };
	try {
		await audio.context.audioWorklet.addModule("rta-sound.js");
		const ring = module._rtaSoundRing();
		const size = module.HEAPU32[(ring >> 2) + 2];
		audio.node = new AudioWorkletNode(audio.context, "rta-ring", {
			numberOfInputs: 0, outputChannelCount: [2],
			processorOptions: { memory: module.wasmMemory.buffer, ring, size },
		});
		audio.node.port.onmessage = (event) => { audio.dry = event.data.dry; audio.queuedMs = event.data.queuedMs; audio.playing = event.data.playing; };
		audio.node.connect(audio.context.destination);
		audio.node.port.postMessage({ muted: options.muted });
		audio.context.resume();
		note("sound: started at " + audio.context.sampleRate + " Hz");
	} catch(e) {
		note("sound: could not be started (" + e + ")");
	}
}

// ---- the memory card ----------------------------------------------------------------
// Play! keeps a memory card as a folder of files. The folder lives in the browser's
// storage for this site (IndexedDB), read when the page starts and written back a few
// seconds after anything in it changed.
const DATA = "/home/web_user/.local/share/Play Data Files"; // where Play! keeps its files in Emscripten's file system
let cardSignature = "";
function cardState() {
	let signature = "";
	const walk = (path) => {
		let names;
		try { names = module.FS.readdir(path); } catch(e) { return; }
		for(const name of names) {
			if(name === "." || name === "..") continue;
			const full = path + "/" + name;
			const stat = module.FS.stat(full);
			if(module.FS.isDir(stat.mode)) walk(full);
			else signature += full + ":" + stat.size + ":" + stat.mtime.getTime() + ";";
		}
	};
	walk(DATA);
	return signature;
}
function mountCard() {
	return new Promise((resolve) => {
		if(params.get("card") === "0") { resolve(); return; } // DEV: an empty card in memory, forgotten afterwards
		try {
			module.FS.mkdirTree(DATA);
			module.FS.mount(module.IDBFS, {}, DATA);
			module.FS.syncfs(true, (error) => {
				if(error) note("memory card: the browser's storage could not be read (" + error + ")");
				cardSignature = cardState();
				resolve();
			});
		} catch(e) {
			note("memory card: not kept in this browser (" + e + ")");
			resolve();
		}
	});
}
function saveCard() {
	if(!module || params.get("card") === "0") return;
	const signature = cardState();
	if(signature === cardSignature) return;
	cardSignature = signature;
	module.FS.syncfs(false, (error) => note(error ? "memory card: could not be written to the browser's storage (" + error + ")" : "memory card: saved in the browser's storage"));
}

// ---- figures ------------------------------------------------------------------------
// A browser runs a page that is not in front (another tab, a covered or minimised window)
// at low priority and lets its timers run late: figures taken then say nothing about the
// build. How long the page was hidden is therefore part of every figure.
let hiddenSince = document.hidden ? performance.now() : null, hiddenTotal = 0;
document.addEventListener("visibilitychange", () => {
	const now = performance.now();
	if(document.hidden) hiddenSince = now;
	else if(hiddenSince !== null) { hiddenTotal += now - hiddenSince; hiddenSince = null; }
});
function info() {
	const result = JSON.parse(module.UTF8ToString(module._rtaInfo()));
	result.hidden_ms = hiddenTotal + (hiddenSince !== null ? performance.now() - hiddenSince : 0);
	return result;
}
function rates(a, b) {
	const seconds = (b.now - a.now) / 1000, frames = b.frames - a.frames;
	const per = (x) => frames ? x / frames : 0;
	return {
		seconds: +seconds.toFixed(2),
		hidden_seconds: +((b.hidden_ms - a.hidden_ms) / 1000).toFixed(2),
		fps: +(frames / seconds).toFixed(2),
		presents_per_second: +((b.presents - a.presents) / seconds).toFixed(2),
		// what the machine's thread needed for a frame: the frame without the wait that holds the rate
		machine_ms_per_frame: +per(((b.now - a.now) * 1000 - (b.wait_us - a.wait_us)) / 1000).toFixed(2),
		video_ms_per_frame: +per((b.video_us - a.video_us) / 1000).toFixed(2),
		gl_calls_per_frame: Math.round(per(b.gl_made - a.gl_made)),
		gl_calls_left_out_per_frame: Math.round(per(b.gl_skipped - a.gl_skipped)),
		block_starts_per_frame: Math.round(per((b.dispatches - a.dispatches) >>> 0)),
		functions_made: b.functions - a.functions,
		function_ms_per_frame: +per((b.function_us - a.function_us) / 1000).toFixed(3),
		draw_calls: b.draw_calls,
		disc_fetches: b.disc_fetches - a.disc_fetches,
	};
}
// Waiting, by a clock in a worker: a browser slows the timers of a page that is not in
// front down to one a second or less, and a test must not depend on being looked at.
const ticker = new Worker(URL.createObjectURL(new Blob(["setInterval(() => postMessage(0), 10);"], { type: "text/javascript" })));
const sleepers = [];
ticker.onmessage = () => {
	const now = performance.now();
	for(let i = sleepers.length - 1; i >= 0; i--) {
		if(sleepers[i].until <= now) sleepers.splice(i, 1)[0].resolve();
	}
};
const sleep = (ms) => new Promise((resolve) => sleepers.push({ until: performance.now() + ms, resolve }));

let lastInfo = null, lastRates = null;
setInterval(() => {
	if(!module || !running) return;
	const now = info();
	if(lastInfo) {
		lastRates = rates(lastInfo, now);
		speedElement.textContent = lastRates.fps.toFixed(1) + " frames/s";
		speedElement.title = "machine " + lastRates.machine_ms_per_frame.toFixed(1) + " ms a frame, video " + lastRates.video_ms_per_frame.toFixed(1) + " ms a frame (16.7 is the limit)";
		if(options.report) {
			fetch("/report", { method: "POST", body: JSON.stringify({ kind: "second", level: rta.levelName(), ...lastRates }) }).catch(() => {});
		}
	}
	lastInfo = now;
}, 1000);
setInterval(saveCard, 5000);
if(options.report) {
	// DEV: the test's local server can send this tab on to another address of the same
	// server or have it closed (a tab opened from a command line may close itself as
	// long as it has shown one page only, hence "replace"), so that a run of tests needs
	// one tab.
	setInterval(async () => {
		try {
			const response = await fetch("/command");
			if(response.status !== 200) return;
			const command = await response.json();
			if(command.goto && new URL(command.goto, location.href).origin === location.origin) location.replace(command.goto);
			if(command.close) window.close();
		} catch(e) { /* the server is gone */ }
	}, 2000);
}

// ---- for tests (the developer's console, or a test driving the page) ------------------
const rta = window.rta = {
	B, options, log, checkDisc, fileReader, urlReader, boot,
	info: () => info(),
	last: () => lastRates,
	peek: (address, size = 4) => module._rtaPeek(address, size) >>> 0,
	poke: (address, size, value) => module._rtaPoke(address, size, value),
	string: (address, limit = 32) => {
		let text = "";
		for(let i = 0; i < limit; i++) {
			const c = module._rtaPeek(address + i, 1);
			if(!c) break;
			text += String.fromCharCode(c);
		}
		return text;
	},
	levelName: () => rta.string(G_LEVEL_NAME, 16),
	inFrontEnd: () => rta.peek(G_IN_FRONTEND, 1) === 1,
	limiter: (on) => { module.HEAPU32[shared + 6] = on ? 1 : 0; },
	pause: (on) => module._rtaPause(on ? 1 : 0),
	sound: () => audio && { state: audio.context.state, dry: audio.dry, queuedMs: audio.queuedMs, playing: audio.playing },
	// 'name' held for 'hold' frames of the machine, then 'wait' frames of nothing
	tap: async (name, hold = 8, wait = 60) => {
		module._rtaTap(name ? 1 << B[name] : 0, hold, wait);
		while(module._rtaStepsLeft() > 0) await sleep(20);
	},
	wait: (frames) => rta.tap(null, 0, frames),
	measure: async (seconds = 10) => {
		const a = info();
		await sleep(seconds * 1000);
		return rates(a, info());
	},
	// consecutive pictures compared: how many pixels of each differ from the one before
	burst: async (count = 8) => {
		module.HEAPU32[shared + 7] = count;
		for(let i = 0; i < 400 && module.HEAPU32[shared + 7] !== 0; i++) await sleep(25);
		return JSON.parse(module.UTF8ToString(module._rtaBurst()));
	},
	// DEV: the video thread's GL calls over 'seconds': [calls, ms] per frame, by name
	glProfile: async (seconds = 5) => {
		module._rtaGlProfile(1);
		const a = info();
		await sleep(seconds * 1000);
		const b = info();
		const pointer = module._rtaGlProfile(0);
		const result = JSON.parse(module.UTF8ToString(pointer));
		module._free(pointer);
		const frames = b.frames - a.frames;
		const calls = Object.entries(result.calls).map(([name, [n, t]]) => [name, +(n / frames).toFixed(1), +(t / frames).toFixed(3)]).sort((x, y) => y[2] - x[2]);
		return { frames, video_ms_per_frame: +((b.video_us - a.video_us) / 1000 / frames).toFixed(2),
			gl_ms_per_frame: +calls.reduce((sum, c) => sum + c[2], 0).toFixed(2), gl_calls_per_frame: Math.round(calls.reduce((sum, c) => sum + c[1], 0)), calls };
	},
	// DEV: what the machine reads as its pad right now: [buttons, lx, ly, rx, ry, sticks given]
	padWords: () => Array.from(module.HEAPU32.subarray(shared, shared + 6)),
	// DEV: the files Play! keeps (memory cards, settings), with their sizes
	files: () => {
		const list = [];
		const walk = (path) => {
			for(const name of module.FS.readdir(path)) {
				if(name === "." || name === "..") continue;
				const full = path + "/" + name, stat = module.FS.stat(full);
				if(module.FS.isDir(stat.mode)) walk(full); else list.push([full.slice(DATA.length + 1), stat.size]);
			}
		};
		try { walk(DATA); } catch(e) { list.push(["error", String(e)]); }
		return list;
	},
	writeFile: (name, text) => { module.FS.mkdirTree((DATA + "/" + name).replace(/\/[^/]*$/, "")); module.FS.writeFile(DATA + "/" + name, text); },
	removeFile: (name) => { module.FS.unlink(DATA + "/" + name); try { module.FS.rmdir((DATA + "/" + name).replace(/\/[^/]*$/, "")); } catch(e) { /* not empty */ } },
	saveCard: () => saveCard(),
	// DEV: the left stick at (x, y), 0..255, for exactly 'frames' frames of the machine
	stick: async (x, y, frames) => {
		module._rtaStick(x, y, frames);
		while(module._rtaStepsLeft() > 0) await sleep(20);
	},
	// DEV: 'size' bytes of the game's memory at [pointer] + offset (pointer 0: at offset),
	// taken at every frame for 'frames' frames; resolves to one hexadecimal string per frame
	trace: async (pointer, offset, size, frames, during = null) => {
		module._rtaTrace(pointer, offset, size, frames);
		if(during) await during();
		let text = "";
		for(let i = 0; i < 3000 && !(text = module.UTF8ToString(module._rtaTrace(0, 0, 0, 0))); i++) await sleep(20);
		const rows = [];
		for(let i = 0; i < text.length; i += size * 2) rows.push(text.slice(i, i + size * 2));
		return rows;
	},
	// DEV: the numbers of the 128 KiB pieces of the image read so far, in order
	discPieces: () => {
		const pieces = [];
		for(let i = 0, n; (n = module._RtaWebDiscFetched(i)) >= 0; i++) pieces.push(n);
		return pieces;
	},
	// DEV: A stand-in for a picked file, for testing the player's path without the file
	// dialog: a Blob as large as the image at 'url' that holds the given pieces of it and
	// zeroes everywhere else (the zero pieces are one Blob named again and again, so it
	// costs no memory). Booting it reads through a blob: URL exactly as a picked file is.
	standIn: async (url, pieces) => {
		const PIECE = 0x20000;
		const size = (await urlReader(url)).size;
		const wanted = new Set(pieces);
		const zero = new Blob([new Uint8Array(PIECE)]);
		const parts = [];
		for(let n = 0; n * PIECE < size; n++) {
			const length = Math.min(PIECE, size - n * PIECE);
			if(wanted.has(n)) parts.push(await (await fetch(url, { headers: { Range: "bytes=" + (n * PIECE) + "-" + (n * PIECE + length - 1) } })).blob());
			else parts.push(length === PIECE ? zero : zero.slice(0, length));
		}
		return new File(parts, "stand-in.iso");
	},
	bootFile: (file) => bootFile(file, null),
	// DEV: the picture on the canvas as a PNG, POSTed to /shot/<name> of the local test
	// server (which keeps it outside the repository's tracked files)
	shot: async (name) => {
		module._rtaShot(1);
		let pixels = 0;
		for(let i = 0; i < 200 && !(pixels = module._rtaShot(0)); i++) await sleep(25);
		if(!pixels) throw new Error("no picture was handed over");
		const width = canvas.width, height = canvas.height;
		const image = new ImageData(width, height);
		for(let y = 0; y < height; y++) {
			image.data.set(module.HEAPU8.subarray(pixels + (height - 1 - y) * width * 4, pixels + (height - y) * width * 4), y * width * 4);
		}
		for(let i = 3; i < image.data.length; i += 4) image.data[i] = 255;
		const copy = new OffscreenCanvas(width, height);
		copy.getContext("2d").putImageData(image, 0, 0);
		const blob = await copy.convertToBlob({ type: "image/png" });
		const response = await fetch("/shot/" + encodeURIComponent(name), { method: "POST", body: blob });
		return { name, width, height, bytes: blob.size, status: response.status };
	},
	// DEV (a build with -DPROFILE=ON): the machine thread's milliseconds per frame by zone
	zones: async (seconds = 5) => {
		const read = () => [info(), JSON.parse(module.UTF8ToString(module._rtaZones()))];
		const [a, za] = read();
		await sleep(seconds * 1000);
		const [b, zb] = read();
		const frames = b.frames - a.frames, result = { frames, fps: +(frames / ((b.now - a.now) / 1000)).toFixed(2) };
		for(const name in zb) result[name] = +(((zb[name] - (za[name] || 0)) / 1e6) / frames).toFixed(2);
		return result;
	},
	// DEV: the GL calls that make up a frame do nothing from here on (reload afterwards)
	glNull: () => module._rtaGlProfile(2),
	// power-on to the title screen's menu: cross through the memory-card question and the logos
	toTitle: async () => {
		await rta.wait(120);
		for(let i = 0; i < 80; i++) {
			if(rta.inFrontEnd() && rta.levelName() === "intro") break;
			await rta.tap("cross", 6, 40);
		}
		if(!(rta.inFrontEnd() && rta.levelName() === "intro")) throw new Error("the front end did not come up");
		await rta.wait(420); // the title's own fade-in
	},
	// on from the title: a new offline game into the first level (local/play-out/tohub.py)
	toHub: async (settle = 300) => {
		for(const frames of [90, 90, 90, 90, 200, 120, 120]) await rta.tap("cross", 8, frames);
		for(let i = 0; i < 20; i++) await rta.tap("right", 4, 6);
		await rta.wait(20);
		await rta.tap("cross", 8, 120);
		for(let i = 0; i < 3; i++) await rta.tap("cross", 4, 8);
		for(let i = 0; i < 6; i++) await rta.tap("down", 4, 8);
		for(let i = 0; i < 5; i++) await rta.tap("right", 4, 8);
		await rta.tap("cross", 8, 60);
		for(let i = 0; i < 120 && rta.levelName() !== "hub"; i++) await rta.wait(30);
		if(rta.levelName() !== "hub") throw new Error("the first level was not reached (level '" + rta.levelName() + "')");
		if(settle) await rta.wait(settle);
	},
	state: "loading",
};

async function report(kind, data) {
	note(kind + ": " + JSON.stringify(data));
	if(options.report) await fetch("/report", { method: "POST", body: JSON.stringify({ kind, ...data }) }).catch(() => {});
}

// what the sound did over an interval: times the ring ran dry, and what was queued at the end
async function soundOver(run) {
	const before = audio ? audio.dry : 0;
	const result = await run();
	if(audio) result.sound = { state: audio.context.state, ran_dry: audio.dry - before, queued_ms: audio.queuedMs, playing: !!audio.playing };
	return result;
}

async function automatic() {
	try {
		// a browser started for tests with --autoplay-policy=no-user-gesture-required lets
		// the sound start without a person; otherwise it stays asleep and is not judged
		startSound();
		await report("start", { browser: navigator.userAgent, canvas: [canvas.width, canvas.height], factor: options.factor,
			gl: options.glMain ? "main thread" : "own canvas", sound: options.sound, patches: options.patches, visible: document.visibilityState });
		rta.state = "to title";
		await rta.toTitle();
		rta.state = "title";
		await report("title", await soundOver(() => rta.measure(10)));
		await report("title-burst", { burst: await rta.burst(8) });
		if(options.auto === "trace") {
			// For comparing arithmetic with the desktop application: the player's position
			// (x, y, z as the raw bytes of three floats) at every frame, first for six
			// seconds from arriving in the level without any input, then while the left
			// stick is held fully right for exactly 60 frames.
			const PLAYER_OBJECT = 0x4d8af0 + 0x43d8;
			rta.state = "to hub";
			await rta.toHub(0);
			rta.state = "trace";
			const runs = (rows) => { const out = []; for(const row of rows) { if(out.length && out[out.length - 1][0] === row) out[out.length - 1][1]++; else out.push([row, 1]); } return out; };
			await report("trace-arrival", { positions: runs(await rta.trace(PLAYER_OBJECT, 0x10, 12, 360)) });
			// place=XXXXXXXX,YYYYYYYY (the bits of two floats): the player is put at that
			// x and y first, so that two builds start the walk from the same bits wherever
			// the game happened to stand the character (where it does depends on how many
			// frames the menus took)
			if(params.get("place")) {
				const [x, y] = params.get("place").split(",").map((text) => parseInt(text, 16));
				const object = rta.peek(PLAYER_OBJECT);
				rta.poke(object + 0x10, 4, x);
				rta.poke(object + 0x14, 4, y);
				await rta.wait(60);
			}
			await report("trace-move", { positions: runs(await rta.trace(PLAYER_OBJECT, 0x10, 12, 110, () => rta.stick(255, 128, 60))) });
		}
		if(options.auto === "hub") {
			rta.state = "to hub";
			await rta.toHub();
			rta.state = "hub";
			// the first seconds in a level: its code is still being translated and the
			// browser is still making the fast version of what was translated
			await report("hub-arrival", await rta.measure(10));
			await report("hub", await soundOver(() => rta.measure(15)));
			await report("hub-burst", { burst: await rta.burst(8) });
			if(params.get("shot")) await report("shot", await rta.shot(params.get("shot")));
			rta.limiter(false);
			await sleep(2000);
			await report("hub-unlimited", await rta.measure(10));
			rta.limiter(true);
		}
		rta.state = "done";
		await report("done", {});
	} catch(e) {
		rta.state = "failed: " + e.message;
		await report("failed", { error: e.message });
	}
}

// ---- start --------------------------------------------------------------------------
async function start() {
	if(!self.crossOriginIsolated) {
		setStatus("This page has to be served with the headers Cross-Origin-Opener-Policy: same-origin and Cross-Origin-Embedder-Policy: require-corp (the emulator runs on several threads).");
		return;
	}
	// The canvas: 4:3, as many pixels as it takes up on this screen, but not more than 896
	// lines (the console's 448 twice; a larger canvas costs speed out of proportion - see
	// docs/issues/browser-build.md) and not fewer than 480. Its size is fixed from here on:
	// the video thread owns it.
	const scale = Math.min(window.devicePixelRatio || 1, 2);
	const stage = $("stage").getBoundingClientRect();
	let height = Math.max(480, Math.min(896, Math.floor(stage.height * scale), Math.floor(stage.width * scale * 3 / 4)));
	if(params.get("canvas")) height = parseInt(params.get("canvas"), 10);
	canvas.height = height;
	canvas.width = Math.round(height * 4 / 3);

	module = await Play({
		print: (text) => note("emulator: " + text),
		printErr: (text) => note("emulator (error): " + text),
	});
	await mountCard();

	if(options.patches) {
		try {
			const [patchText, sectionText] = await Promise.all([
				fetch("SLUS-20973_4028A55F.pnach").then((r) => { if(!r.ok) throw new Error("patch file " + r.status); return r.text(); }),
				fetch("sections.txt").then((r) => { if(!r.ok) throw new Error("section list " + r.status); return r.text(); }),
			]);
			const a = writeString(patchText), b = writeString(options.allSections ? "*" : sectionText);
			const words = module._rtaSetPatches(a, b, options.display ? 1 : 0);
			module._free(a);
			module._free(b);
			note("patches: " + words + " words");
			if(words < 0) { setStatus("The patch file could not be understood: not started."); return; }
		} catch(e) {
			setStatus("The patch file could not be loaded (" + e.message + "): not started.");
			return;
		}
	} else {
		const empty = writeString("");
		module._rtaSetPatches(empty, empty, options.display ? 1 : 0);
		module._free(empty);
	}

	module._rtaInit(canvas.width, canvas.height, options.factor, options.glMain ? 0 : 1, options.sound ? 1 : 0, 0);
	for(let i = 0; i < 1000 && !module._rtaReady(); i++) await sleep(20);
	if(!module._rtaReady()) { setStatus("The emulator did not start."); return; }
	shared = module._rtaShared() >> 2;
	module.HEAPU32[shared + 6] = options.limit ? 1 : 0;
	const frame = () => { readInput(); requestAnimationFrame(frame); };
	requestAnimationFrame(frame);
	setInterval(readInput, 8); // also when the page is not being painted
	rta.state = "ready";
	showMute();

	if(options.disc) {
		// DEV: a disc image served by the developer's own local server
		const url = new URL(options.disc, location.href);
		if(url.origin !== location.origin) { setStatus("disc= must be a URL of this server.", true); return; }
		if(await boot(await urlReader(url.href), url.href, "disc.iso") && options.auto) automatic();
		return;
	}
	const handle = await remembered("disc");
	if(handle) {
		$("resume").textContent = "Continue with " + handle.name;
		$("resume").hidden = false;
		$("choose").textContent = "Choose another disc image…";
	}
	$("choose").hidden = false;
	setStatus(handle ? "Ready." : "Ready. Choose your disc image to start.");
}

start().catch((e) => setStatus("Could not start: " + e.message, true));
window.addEventListener("pagehide", saveCard);
