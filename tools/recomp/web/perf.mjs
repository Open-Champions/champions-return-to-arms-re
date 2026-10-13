#!/usr/bin/env node
// perf.mjs - drives the native build's page in a Google Chrome of its own (its own profile
// under local/, DevTools protocol on 127.0.0.1) and reads its speed: pictures a second,
// milliseconds per frame of each thread, thread CPU time and instructions retired of the
// page's process, at the title and standing in the first level, as the Mac runs it and
// with the slow-computer stand-in of docs/issues/browser-perf.md (the page's process
// stopped for (rate - 1) / rate of every 20 ms: stopgo.c).  The harness of the emulator
// page's speed work (local/play-web-perf-out/perf.mjs) for this page.
//
//   node tools/recomp/web/perf.mjs measure [--site DIR-NAME] [--scale 2] [--throttle 2,4,6]
//        [--label TEXT] [--title-only] [--sound] [--blend basic] [--shots] [--keys] [--keep-card] [--walk]
//        [--route fight]     the tick-keyed route into the level `valor` and its fight
//                            (local/recomp-web/out/fight3-nodump.rig) instead of the first level:
//                            measured while the fight goes on (ticks 2300 to 4600), paced only
//   node tools/recomp/web/perf.mjs close
//
// Needs the test server: tools/recomp/web/serve.py --port 8975 --site local/recomp-web/build
//                        --disc IMAGE --shots local/recomp-web/out/shots
// (--site names the directory below that one: page-nearest by default.)
// The page is titled "AGENT TEST - native web (...)", stays visible while it is measured and
// the browser is closed afterwards.  Results: local/recomp-web/out/results.jsonl.
import { spawn, execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..", "..");
const LOCAL = path.join(ROOT, "local", "recomp-web");
const OUT = path.join(LOCAL, "out");
const TOOLS = path.join(LOCAL, "build", "tools");            // stopgo, rusage (compiled from the .c files beside this script)
const PORT = parseInt(process.env.RTA_PERF_PORT || "8975", 10);
const DEBUG_PORT = parseInt(process.env.RTA_PERF_DEBUG_PORT || "9336", 10);
const PROFILE_DIR = path.join(LOCAL, "chrome-profile");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const load = () => +os.loadavg()[0].toFixed(0);
let closing = false;

const args = process.argv.slice(2);
const mode = args.shift();
const opt = (name, fallback = null) => { const i = args.indexOf("--" + name); return i < 0 ? fallback : (args[i + 1] === undefined || args[i + 1].startsWith("--") ? true : args[i + 1]); };

// ---- the boot script: the rig's route to the first level, names replaced by addresses -------------
// (the page has no symbol files), with a stop at the title and marks the harness waits for
function bootScript() {
	const symbols = new Map();
	const files = [path.join(ROOT, "names.tsv"), ...fs.readdirSync(path.join(ROOT, "symbols")).filter((n) => n.endsWith(".tsv")).sort().map((n) => path.join(ROOT, "symbols", n))];
	for(const file of files) for(const line of fs.readFileSync(file, "utf8").split("\n")) {
		const m = /^([0-9a-fA-F]{6,8})\t([A-Za-z_][A-Za-z0-9_]*)/.exec(line);
		if(m && !symbols.has(m[2])) symbols.set(m[2], "0x" + m[1].replace(/^0+/, ""));
	}
	const out = [];
	const fight = opt("route") === "fight";
	const source = fight ? path.join(OUT, "fight3-nodump.rig") : path.join(ROOT, "tools", "rig", "examples", "boot-to-hub.rig");
	for(let line of fs.readFileSync(source, "utf8").split("\n")) {
		const code = line.replace(/#.*$/, "").trimEnd();
		if(!code.trim() || code.startsWith("show ") || code.startsWith("dump ")) continue;
		out.push(code.replace(/\b[A-Za-z_][A-Za-z0-9_]*\b/g, (name) => symbols.get(name) || name));
		// (the fight's route is keyed on simulation ticks, which run on at the title: no stop there)
		if(!fight && /^until g_levelName:str8 == intro/.test(code)) out.push("wait 120", "echo AT-TITLE", "wait " + (opt("title-frames") || 1500), "echo LEAVING-TITLE");
		if(fight && /^until g_levelName:str8 == valor/.test(code)) out.push("echo IN-VALOR");
	}
	out.push(fight ? "echo FIGHT-OVER" : "wait 240", fight ? "wait 1" : "echo IN-HUB");
	return out.join("\n") + "\n";
}

// ---- the DevTools protocol ------------------------------------------------------------------------
class Cdp {
	constructor(ws) {
		this.ws = ws; this.next = 1; this.pending = new Map(); this.listeners = [];
		ws.onmessage = (event) => {
			const message = JSON.parse(event.data);
			if(message.id) {
				const p = this.pending.get(message.id);
				this.pending.delete(message.id);
				if(p) message.error ? p.reject(new Error(p.method + ": " + message.error.message)) : p.resolve(message.result);
			} else for(const l of this.listeners) l(message);
		};
	}
	send(method, params = {}, sessionId) {
		const id = this.next++;
		return new Promise((resolve, reject) => {
			this.pending.set(id, { resolve, reject, method });
			this.ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
			// a page that is gone (crashed, or the Mac slept and Chrome dropped it) answers nothing: say so instead of waiting for ever
			setTimeout(() => { if(this.pending.delete(id)) reject(new Error(method + ": no answer in 90 s (the page or the browser is gone, or the Mac slept)")); }, 90000);
		});
	}
	on(listener) { this.listeners.push(listener); }
}
async function gone() {
	for(let i = 0; i < 100; i++) {
		try { await fetch("http://127.0.0.1:" + DEBUG_PORT + "/json/version"); } catch(e) { return; }
		await sleep(200);
	}
}
async function connectChrome() {
	const version = await (await fetch("http://127.0.0.1:" + DEBUG_PORT + "/json/version")).json();
	const ws = new WebSocket(version.webSocketDebuggerUrl);
	await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
	ws.onclose = () => { if(!closing) { console.log("  FAILED: the browser went away"); process.exit(3); } };
	return { cdp: new Cdp(ws), version: version.Browser };
}
async function startChrome() {
	try { return await connectChrome(); } catch(e) { /* none running */ }
	fs.mkdirSync(PROFILE_DIR, { recursive: true });
	// the flags keep Chrome from running a window that is not in front at low priority
	spawn(CHROME, ["--user-data-dir=" + PROFILE_DIR, "--remote-debugging-port=" + DEBUG_PORT,
		"--no-first-run", "--no-default-browser-check", "--autoplay-policy=no-user-gesture-required", "--mute-audio",
		"--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding", "--disable-background-timer-throttling",
		"--window-size=1320,1080", "--window-position=80,60", "about:blank"], { stdio: "ignore", detached: true }).unref();
	for(let i = 0; i < 150; i++) {
		try { return await connectChrome(); } catch(e) { await sleep(200); }
	}
	throw new Error("Chrome did not start");
}

// ---- the page's process from outside ----------------------------------------------------------------
function rendererPid() {
	const out = execFileSync("ps", ["-Ao", "pid,pcpu,command"], { encoding: "utf8", maxBuffer: 1 << 26 }).split("\n");
	let best = null;
	for(const line of out) {
		if(!line.includes("--type=renderer") || !line.includes(PROFILE_DIR)) continue;
		const f = line.trim().split(/\s+/);
		if(!best || parseFloat(f[1]) > best[1]) best = [parseInt(f[0], 10), parseFloat(f[1])];
	}
	return best ? best[0] : 0;
}
function counters(pid) {
	try { return JSON.parse(execFileSync(path.join(TOOLS, "rusage"), [String(pid)], { encoding: "utf8" })); } catch(e) { return null; }
}
function threadTimes(pid) {
	const rows = [];
	for(const line of execFileSync("ps", ["-M", "-p", String(pid)], { encoding: "utf8" }).split("\n").slice(1)) {
		const times = [...line.matchAll(/\b(\d+):(\d\d\.\d\d)\b/g)];
		if(times.length >= 2) rows.push(times.slice(0, 2).reduce((sum, m) => sum + parseInt(m[1], 10) * 60 + parseFloat(m[2]), 0));
	}
	return rows;
}

async function main() {
	if(mode === "close") {
		try { const { cdp } = await connectChrome(); closing = true; await cdp.send("Browser.close"); await gone(); } catch(e) { /* none running */ }
		process.exit();
	}
	if(mode !== "measure") { console.error("usage: perf.mjs measure [options] | perf.mjs close"); process.exit(2); }
	fs.mkdirSync(OUT, { recursive: true });
	const site = opt("site", "page-nearest"), label = opt("label", "");
	const { cdp, version } = await startChrome();
	let targetId = null;
	const result = { site, label, browser: version, when: new Date().toISOString(), load_start: load(), scale: opt("scale", "2"), sound: !!opt("sound") };
	try {
		const url = "http://127.0.0.1:" + PORT + "/" + site + "/index.html?title=" + encodeURIComponent("AGENT TEST - native web (" + site + (label ? " " + label : "") + ")") + "&scale=" + result.scale + "&pause=0";
		({ targetId } = await cdp.send("Target.createTarget", { url: "about:blank" }));
		const { sessionId: page } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
		await cdp.send("Runtime.enable", {}, page);
		const problems = [];
		cdp.on((m) => { if(m.method === "Runtime.exceptionThrown") problems.push(m.params.exceptionDetails.text + " " + (m.params.exceptionDetails.exception?.description || "").slice(0, 300)); });
		await cdp.send("Page.navigate", { url }, page);
		const evaluate = async (expression) => {
			const r = await cdp.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }, page);
			if(r.exceptionDetails) throw new Error("page: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
			return r.result.value;
		};
		for(let i = 0; i < 150; i++) {
			await sleep(200);
			const state = await evaluate("window.rta ? rta.state : ''");
			if(state === "ready") break;
			if(state === "failed" || i === 149) throw new Error("the page did not get ready: " + await evaluate("document.getElementById('status').textContent"));
		}
		const options = { script: bootScript(), sound: !!opt("sound"), card: !!opt("keep-card") };
		if(opt("blend")) options.blend = opt("blend");
		if(opt("args")) options.args = String(opt("args")).split(",").map((a) => "--" + a);    // more program arguments, e.g. --args times,interpret-vu
		const t0 = Date.now();
		if(!(await evaluate("rta.bootUrl('/dev/disc.iso', " + JSON.stringify(options) + ")"))) throw new Error("the page did not start: " + await evaluate("document.getElementById('status').textContent"));
		result.visible = await evaluate("document.visibilityState");
		const said = async (mark, seconds) => {
			for(let i = 0; i < seconds * 4; i++) {
				if(await evaluate("rta.log.some((l) => l.includes(" + JSON.stringify(mark) + "))")) return;
				if(await evaluate("rta.state") !== "running") throw new Error("the game ended: " + JSON.stringify(await evaluate("rta.log.slice(-6)")));
				await sleep(250);
			}
			throw new Error("no " + mark + " after " + seconds + " s; the page's last lines: " + JSON.stringify(await evaluate("rta.log.slice(-6)")));
		};

		// what the page measured over `seconds`, with the CPU time of the busiest threads of its
		// process and the instructions it retired beside it
		const measure = async (name, seconds) => {
			const pid = rendererPid();
			const before = threadTimes(pid), l0 = load(), c0 = counters(pid);
			const r = await evaluate("rta.measure(" + seconds + ")");
			const after = threadTimes(pid), c1 = counters(pid);
			const frames = Math.max(1, r.fps * r.seconds);
			const used = before.map((t, i) => (after[i] ?? t) - t).sort((a, b) => b - a).slice(0, 5).map((s) => +(s * 1000 / frames).toFixed(2));
			const row = { ...r, thread_cpu_ms: used, load: [l0, load()] };
			if(r.vu_run_ms_per_frame) console.log("    VU1 runs %s ms a frame in %d runs (of which GS kicks %s), PATH3 %s; translation %s", r.vu_run_ms_per_frame, r.vu_runs_per_frame, r.kick_ms_per_frame, r.path3_ms_per_frame, r.vu_translated);
			if(c0 && c1) {
				row.minstr = +((c1.instructions - c0.instructions) / 1e6 / frames).toFixed(2);
				row.mcycles = +((c1.cycles - c0.cycles) / 1e6 / frames).toFixed(2);
				row.process_cpu_ms = +((c1.user_ns + c1.system_ns - c0.user_ns - c0.system_ns) / 1e6 / frames).toFixed(2);
			}
			result[name] = row;
			console.log("  %s %s fields/s  wall ms/frame: game %s decoder %s drawing %s  thread cpu ms/frame %s  process %s ms, %s Minstr, %s Mcycles a frame  %d draws %d GL calls  load %d-%d%s",
				name.padEnd(18), String(r.fps).padStart(6), r.game_ms_per_frame, r.decode_ms_per_frame, r.draw_ms_per_frame, JSON.stringify(used), row.process_cpu_ms, row.minstr, row.mcycles,
				r.draws_per_frame, r.gl_calls_per_frame, l0, load(), r.hidden_seconds ? "  PAGE HIDDEN " + r.hidden_seconds + " s" : "");
			return row;
		};

		console.log("== %s  scale %s  %s  %s  load %d  %s", site, result.scale, result.visible, version, load(), label);
		const slowed = async (rate, name, seconds) => {
			const pid = rendererPid();
			const child = spawn(path.join(TOOLS, "stopgo"), [String(pid), String(rate)], { stdio: ["ignore", "ignore", "pipe"] });
			let told = "";
			child.stderr.on("data", (d) => { told += d; });
			await sleep(2500);
			const row = await measure(name, seconds);
			child.kill("SIGTERM");
			await new Promise((r) => child.on("exit", r));
			row.stopgo = told.trim();
			console.log("    " + told.trim());
			await sleep(1500);
		};
		if(opt("route") === "fight") {
			await said("IN-VALOR", 400);
			result.to_valor_s = +((Date.now() - t0) / 1000).toFixed(1);
			for(let i = 0; i < 600 && (await evaluate("rta.info()")).sim < 2300; i++) await sleep(100);
			const tick = async () => (await evaluate("rta.info()")).sim;
			result.fight_ticks = [await tick()];
			await measure("fight", 12);
			result.fight_ticks.push(await tick());
			if(opt("shots")) result.shot_fight = await evaluate("rta.postShot('web-fight" + (label ? "-" + label : "") + ".png')");
			for(const [rate, seconds] of [[2, 10], [4, 8], [6, 8]]) {
				if(!opt("throttle") || !String(opt("throttle")).split(",").includes(String(rate))) continue;
				await slowed(rate, "fight_slow_" + rate, seconds);
				result.fight_ticks.push(await tick());
			}
			result.level = (await evaluate("rta.info()")).level;
			console.log("  level %s; simulation ticks at the ends of the measurements: %s (the fight runs from 2250 to 4620)", result.level, result.fight_ticks.join(", "));
			const end = await evaluate("rta.info()");
			result.end = { arith: end.arith, vu_arith: end.vu_arith, simd: end.simd, vu_fast: end.vu_fast, vu_fast_left: end.vu_fast_left, late: end.late, sound: end.sound, sound_state: end.sound_state };
			console.log("  end: " + JSON.stringify(result.end));
			return;
		}
		await said("AT-TITLE", 240);
		result.to_title_s = +((Date.now() - t0) / 1000).toFixed(1);
		await measure("title", 10);
		if(opt("shots")) result.shot_title = await evaluate("rta.postShot('web-title" + (label ? "-" + label : "") + ".png')");
		if(!opt("title-only")) {
			await said("IN-HUB", 400);
			result.to_hub_s = +((Date.now() - t0) / 1000).toFixed(1);
			result.level = (await evaluate("rta.info()")).level;
			await sleep(4000);
			await measure("hub", 15);
			if(opt("shots")) result.shot_hub = await evaluate("rta.postShot('web-hub" + (label ? "-" + label : "") + ".png')");
			if(opt("keys")) {
				// real key events through the browser: W held (left stick up) moves the character
				const where = "[rta.peek(rta.peek(0x4d8af0 + 0x43d8) + 0x10), rta.peek(rta.peek(0x4d8af0 + 0x43d8) + 0x14)]";
				const a = await evaluate(where);
				await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", code: "KeyW", key: "w", windowsVirtualKeyCode: 87 }, page);
				await sleep(1500);
				await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", code: "KeyW", key: "w", windowsVirtualKeyCode: 87 }, page);
				await sleep(500);
				const b = await evaluate(where);
				const f = (raw) => new Float32Array(new Uint32Array([raw]).buffer)[0].toFixed(1);
				result.keys = { before: a.map(f), after: b.map(f), events: (await evaluate("rta.info()")).key_events };
				console.log("  keyboard: W held 1.5 s moved the character from (%s) to (%s); %d key events seen by the page", result.keys.before.join(", "), result.keys.after.join(", "), result.keys.events);
				if(opt("shots")) await evaluate("rta.postShot('web-hub-walked" + (label ? "-" + label : "") + ".png')");
			}
			await evaluate("rta.limiter(false)");
			await sleep(2000);
			await measure("hub_unlimited", 10);
			await evaluate("rta.limiter(true)");
			await sleep(1000);
			if(opt("throttle")) {
				for(const rate of String(opt("throttle")).split(",").map(Number)) {
					const pid = rendererPid();
					const child = spawn(path.join(TOOLS, "stopgo"), [String(pid), String(rate)], { stdio: ["ignore", "ignore", "pipe"] });
					let told = "";
					child.stderr.on("data", (d) => { told += d; });
					await sleep(2500);
					const row = await measure("hub_slow_" + rate, 12);
					await evaluate("rta.limiter(false)");
					await sleep(1500);
					const free = await measure("hub_slow_" + rate + "_unlimited", 8);
					await evaluate("rta.limiter(true)");
					child.kill("SIGTERM");
					await new Promise((r) => child.on("exit", r));
					row.stopgo = free.stopgo = told.trim();
					console.log("    " + told.trim());
					await sleep(1500);
				}
			}
			// (last: the character ends somewhere else, with another view)
			if(opt("walk")) {
				// the emulator page's "walking and striking" stretch: the left stick in five directions, a strike after each
				await evaluate("window.walking = (async () => { const dirs = [[128, 0], [255, 128], [128, 255], [0, 128], [200, 40]]; for(let i = 0; i < 14; i++) { const d = dirs[i % 5]; rta.stick(d[0], d[1]); await new Promise((r) => setTimeout(r, 700)); rta.stick(128, 128); await rta.tap('square', 120); await new Promise((r) => setTimeout(r, 180)); } })(), 1");
				await measure("hub_walking", 12);
				await evaluate("window.walking");
				if(opt("shots")) await evaluate("rta.postShot('web-hub-struck" + (label ? "-" + label : "") + ".png')");
			}
		}
		if(opt("keep-card")) {
			// the memory card: written by the game into the program's file system, kept in IndexedDB,
			// still there after the page is loaded again (looked at without starting the game)
			const files = await evaluate("rta.cardFiles()");
			const synced = await evaluate("rta.syncCard()");
			const stored = await evaluate("rta.storedCard()");
			result.card = { files: files.length, bytes: files.reduce((sum, f) => sum + f[1], 0), synced, stored: stored ? stored.length : null };
			result.sound_before_reload = (await evaluate("rta.info()")).sound_state;
			await cdp.send("Page.navigate", { url }, page);
			for(let i = 0; i < 100; i++) { await sleep(200); if(await evaluate("window.rta ? rta.state : ''") === "ready") break; }
			const after = await evaluate("rta.storedCard()");
			result.card.after_reload = after ? after.filter((k) => !/\/$/.test(k)).length : null;
			result.card.names = after ? after.slice(0, 12) : null;
			await evaluate("rta.forgetCard()");
			console.log("  memory card: %d files, %d bytes written by the game; store write %s; %s entries in IndexedDB, %s after the page was loaded again: %s",
				result.card.files, result.card.bytes, synced, result.card.stored, result.card.after_reload, JSON.stringify(result.card.names));
			console.log("  sound before the reload: " + JSON.stringify(result.sound_before_reload));
			fs.appendFileSync(path.join(OUT, "results.jsonl"), JSON.stringify(result) + "\n");
			closing = true;
			await cdp.send("Browser.close"); await gone();
			process.exit();
		}
		const end = await evaluate("rta.info()");
		result.end = { arith: end.arith, vu_arith: end.vu_arith, simd: end.simd, vu_fast: end.vu_fast, vu_fast_left: end.vu_fast_left, dual: end.dual, out: end.out, feedback_copies: end.feedback_copies, disc_reads: end.disc_reads, disc_mb: +(end.disc_bytes / 1e6).toFixed(1), disc_ms: end.disc_ms, sound: end.sound, sound_state: end.sound_state, late: end.late };
		result.said = await evaluate("rta.log.filter((l) => /^(rta|sound|page)[: ]/.test(l)).slice(0, 12)");
		for(const line of result.said) console.log("  " + line);
		console.log("  end: " + JSON.stringify(result.end));
		if(problems.length) { result.problems = problems.slice(0, 5); console.log("  page errors: " + JSON.stringify(result.problems)); }
	} catch(e) {
		console.log("  FAILED: " + e.message);
		result.failed = e.message;
		process.exitCode = 1;
	} finally {
		result.load_end = load();
		fs.appendFileSync(path.join(OUT, "results.jsonl"), JSON.stringify(result) + "\n");
		try {
			closing = true;
			if(process.env.RTA_PERF_KEEP === "1" && targetId) await cdp.send("Target.closeTarget", { targetId });
			else { await cdp.send("Browser.close"); await gone(); }
		} catch(e) { /* gone */ }
		await sleep(300);
	}
	process.exit();
}
main();
