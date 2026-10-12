// The browser build as one side of an arithmetic comparison (docs/issues/mixed-arithmetic.md).
//
// Served beside a browser build's Play.js / Play.wasm by tools/play-web/serve.py with
// --disc and --report. It boots the disc with no patches, no memory card kept and no
// sound, after having given the machine, BEFORE it starts, everything the session
// consists of: the machine takes one step per vertical blank from its first one on, so a
// press lands in the same vertical blank in every run and on every machine that counts
// them from power-on.
//
//   ?session=FILE.json   made by tools/arith/session.py: steps (buttons and both sticks),
//                        writes into the game's memory at given vertical blanks, and the
//                        places to read at every vertical blank. Needs a browser build
//                        with the test entry points rtaStep, rtaPokeAt and rtaWatch*
//                        (tools/arith/web-hooks.patch).
//   ?steps=FILE.json&trace=POINTER,OFFSET,SIZE
//                        the same with what every browser build has (rtaTap, rtaStick,
//                        rtaTrace): steps [[buttons, stick, x, y, frames], ...] that hold
//                        either buttons or the left stick, and one place of at most 64
//                        bytes (numbers in hexadecimal).
// What was read is POSTed to /report as {kind: "trace", name, hex}.
import Play from "./Play.js";

const params = new URLSearchParams(location.search);
const logElement = document.getElementById("log");
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
function note(text) {
	logElement.textContent = (logElement.textContent + text + "\n").slice(-6000);
}
async function report(kind, data) {
	await fetch("/report", { method: "POST", body: JSON.stringify({ kind, name: params.get("name") || "", ...data }) }).catch(() => {});
}

async function run() {
	if(!self.crossOriginIsolated) throw new Error("the page is not cross-origin isolated");
	const session = params.get("session") ? await (await fetch(params.get("session"))).json() : null;
	const oldSteps = session ? null : await (await fetch(params.get("steps"))).json();
	const frames = session ? session.frames : oldSteps.reduce((sum, step) => sum + step[4], 0);
	const discUrl = new URL(params.get("disc") || "/dev/disc.iso", location.href).href;
	const head = await fetch(discUrl, { method: "HEAD" });
	if(!head.ok) throw new Error("no disc image at " + discUrl);
	const discSize = parseInt(head.headers.get("content-length"), 10);

	const module = await Play({ print: (text) => note("emulator: " + text), printErr: (text) => note("emulator (error): " + text) });
	if(session && !module._rtaWatchAdd) throw new Error("this browser build has no rtaStep / rtaPokeAt / rtaWatch entry points");
	const writeString = (text) => {
		const bytes = new TextEncoder().encode(text);
		const address = module._malloc(bytes.length + 1);
		module.HEAPU8.set(bytes, address);
		module.HEAPU8[address + bytes.length] = 0;
		return address;
	};
	const empty = writeString("");
	module._rtaSetPatches(empty, empty, 0);
	const canvas = document.getElementById("outputCanvas");
	module._rtaInit(canvas.width, canvas.height, 1, 1, 0, 0);
	for(let i = 0; i < 1500 && !module._rtaReady(); i++) await sleep(20);
	if(!module._rtaReady()) throw new Error("the emulator did not start");
	module.HEAPU32[(module._rtaShared() >> 2) + 6] = params.get("limit") === "1" ? 1 : 0;

	// everything the machine will be given, before its first vertical blank
	let size = 0;
	if(session) {
		for(const [pointer, offset, bytes] of session.watch) size = module._rtaWatchAdd(pointer, offset, bytes);
		module._rtaWatchStart(frames);
		for(const [frame, address, hex] of session.pokes) {
			for(let i = 0; i < hex.length / 2; i++) module._rtaPokeAt(frame, address + i, 1, parseInt(hex.substr(2 * i, 2), 16));
		}
		for(const [buttons, lx, ly, rx, ry, count] of session.steps) module._rtaStep(buttons, lx, ly, rx, ry, count);
	} else {
		const [pointer, offset, bytes] = (params.get("trace") || "0,0,4").split(",").map((text) => parseInt(text, 16));
		size = bytes;
		module._rtaTrace(pointer, offset, bytes, frames);
		for(const [buttons, stick, x, y, count] of oldSteps) {
			if(stick) module._rtaStick(x, y, count); else module._rtaTap(buttons, count, 0);
		}
	}
	await report("start", { browser: navigator.userAgent, frames, steps: (session ? session.steps : oldSteps).length, size });

	const urlPointer = writeString(discUrl), namePointer = writeString("disc.iso");
	module._RtaWebDiscSet(urlPointer, discSize);
	module._rtaBoot(namePointer);
	const started = performance.now();
	const read = () => module.UTF8ToString(session ? module._rtaWatchRead() : module._rtaTrace(0, 0, 0, 0));
	let hex = "", last = 0;
	while(!(hex = read())) {
		await sleep(250);
		const now = performance.now();
		if(now - last > 10000) {
			last = now;
			const info = JSON.parse(module.UTF8ToString(module._rtaInfo()));
			note("frame " + info.frames + " of " + frames);
			await report("progress", { frame: info.frames, seconds: Math.round((now - started) / 1000) });
		}
	}
	await report("trace", { frames, size, seconds: Math.round((performance.now() - started) / 1000), hex });
	await report("done", {});
	note("done");
}

run().catch(async (error) => {
	note("FAILED: " + error.message);
	await report("failed", { error: String(error.message) });
});
