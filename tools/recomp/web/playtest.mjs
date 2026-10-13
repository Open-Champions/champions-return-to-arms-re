#!/usr/bin/env node
// playtest.mjs - what a player does with the native build's page, done by a script in the
// test Chrome of perf.mjs (its own profile under local/, DevTools protocol on 127.0.0.1,
// pages titled "AGENT TEST - ...", closed afterwards):
//
//   node tools/recomp/web/playtest.mjs discs  [--site NAME]    files that are not the disc, through the page's file input: what the page says
//   node tools/recomp/web/playtest.mjs play   [--site NAME]    the real image through the file input (read in place: File.slice), then in
//                                                              the first level: sound queue, a controller (a stand-in object behind
//                                                              navigator.getGamepads), pause by the player and by a hidden tab
//   node tools/recomp/web/playtest.mjs card   [--site NAME]    a new game saved through the game's own screens, the page loaded again,
//                                                              the save loaded from the main menu: the memory card in IndexedDB
//   node tools/recomp/web/playtest.mjs pictures [--site NAME] --script FILE   a route with `app shot NAME.png` lines: the pictures are
//                                                              posted to the test server (serve.py --shots)
//
// Needs the test server: tools/recomp/web/serve.py --port 8975 --site local/recomp-web/build4 --shots DIR
// (no --disc: the image goes through the file input here, except for `card` and `pictures`,
// which use the server's /dev/disc.iso like perf.mjs).  The image: --disc PATH or $RTA_DISC.
// Results: local/recomp-web/out/playtest.jsonl.
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..", "..");
const LOCAL = path.join(ROOT, "local", "recomp-web");
const OUT = path.join(LOCAL, "out");
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
const site = opt("site", "page");
const DISC = opt("disc") || process.env.RTA_DISC || "";

// a script of the rig's language for the page: names replaced by addresses (the page has no
// symbol files), `show` kept (its line is printed: the test reads it), dumps left out
function pageScript(file, marks = {}) {
	const symbols = new Map();
	const files = [path.join(ROOT, "names.tsv"), ...fs.readdirSync(path.join(ROOT, "symbols")).filter((n) => n.endsWith(".tsv")).sort().map((n) => path.join(ROOT, "symbols", n))];
	for(const f of files) for(const line of fs.readFileSync(f, "utf8").split("\n")) {
		const m = /^([0-9a-fA-F]{6,8})\t([A-Za-z_][A-Za-z0-9_]*)/.exec(line);
		if(m && !symbols.has(m[2])) symbols.set(m[2], "0x" + m[1].replace(/^0+/, ""));
	}
	const out = [];
	for(const line of fs.readFileSync(file, "utf8").split("\n")) {
		const code = line.replace(/#.*$/, "").trimEnd();
		if(!code.trim() || code.startsWith("dump ")) continue;
		if(code.startsWith("quit")) { out.push("echo SCRIPT-END"); continue; }       // the page goes on
		if(code.startsWith("app shot ")) { out.push("app shot " + (marks.shotPrefix || "") + path.basename(code.slice(9).trim())); continue; }
		if(code.startsWith("show ")) { out.push("echo SHOW " + code.slice(5), code.replace(/\b[A-Za-z_][A-Za-z0-9_]*\b/g, (name) => symbols.get(name) || name)); continue; }
		out.push(code.replace(/\b[A-Za-z_][A-Za-z0-9_]*\b/g, (name) => symbols.get(name) || name));
		for(const [pattern, lines] of marks.after || []) if(pattern.test(code)) out.push(...lines);
	}
	out.push(...(marks.end || ["echo SCRIPT-END"]));
	return out.join("\n") + "\n";
}
const hubScript = () => pageScript(path.join(ROOT, "tools", "rig", "examples", "boot-to-hub.rig"), { end: ["wait 240", "echo IN-HUB"] });

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
			setTimeout(() => { if(this.pending.delete(id)) reject(new Error(method + ": no answer in 60 s (the page or the browser is gone, or the Mac slept)")); }, 60000);
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
	// The flags keep Chrome from treating a window that is covered, or on a display that is asleep (the Mac's lid may be
	// closed), as hidden: such a page gets one task a second on its main thread, and every disc read of this page goes through
	// that thread - a run without them made 716 pictures in 16 minutes.  A tab put behind another tab is still hidden.
	spawn(CHROME, ["--user-data-dir=" + PROFILE_DIR, "--remote-debugging-port=" + DEBUG_PORT, "--no-first-run", "--no-default-browser-check",
		"--autoplay-policy=no-user-gesture-required", "--mute-audio", "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
		"--disable-background-timer-throttling", "--window-size=1320,1080", "--window-position=80,60", "about:blank"], { stdio: "ignore", detached: true }).unref();
	for(let i = 0; i < 150; i++) {
		try { return await connectChrome(); } catch(e) { await sleep(200); }
	}
	throw new Error("Chrome did not start");
}

// one page of the site, ready for its disc image
async function openPage(cdp, label, query = "") {
	const url = "http://127.0.0.1:" + PORT + "/" + site + "/index.html?title=" + encodeURIComponent("AGENT TEST - native web play (" + site + " " + label + ")") + query;
	const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
	const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
	await cdp.send("Runtime.enable", {}, sessionId);
	await cdp.send("DOM.enable", {}, sessionId);
	// The test window may be behind the owner's own windows or on another desktop: the page is then hidden to the browser
	// (document.hidden, a few pictures a second at most).  Focus emulation makes the page count as in front.
	await cdp.send("Emulation.setFocusEmulationEnabled", { enabled: true }, sessionId);
	await cdp.send("Page.bringToFront", {}, sessionId).catch(() => {});
	const page = { targetId, sessionId, url, problems: [] };
	cdp.on((m) => { if(m.sessionId === sessionId && m.method === "Runtime.exceptionThrown") page.problems.push(m.params.exceptionDetails.text + " " + (m.params.exceptionDetails.exception?.description || "").slice(0, 300)); });
	page.evaluate = async (expression) => {
		const r = await cdp.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }, sessionId);
		if(r.exceptionDetails) throw new Error("page: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
		return r.result.value;
	};
	page.ready = async () => {
		for(let i = 0; i < 150; i++) {
			await sleep(200);
			const state = await page.evaluate("window.rta ? rta.state : ''");
			if(state === "ready") return;
			if(state === "failed") break;
		}
		throw new Error("the page did not get ready: " + await page.evaluate("document.getElementById('status').textContent"));
	};
	page.navigate = async () => { await cdp.send("Page.navigate", { url }, sessionId); await page.ready(); };
	page.status = () => page.evaluate("document.getElementById('status').textContent");
	// the page's file input is given a file of this computer, as the file dialog would: the page gets a File and reads it in place
	page.pick = async (file) => {
		const { root } = await cdp.send("DOM.getDocument", {}, sessionId);
		const { nodeId } = await cdp.send("DOM.querySelector", { nodeId: root.nodeId, selector: "#file" }, sessionId);
		await cdp.send("DOM.setFileInputFiles", { files: [file], nodeId }, sessionId);
	};
	page.said = async (mark, seconds) => {
		for(let i = 0; i < seconds * 4; i++) {
			if(await page.evaluate("rta.log.some((l) => l.includes(" + JSON.stringify(mark) + "))")) return;
			const state = await page.evaluate("rta.state");
			if(state !== "running" && state !== "starting") throw new Error("the game is not running (" + state + "): " + await page.status() + " " + JSON.stringify(await page.evaluate("rta.log.slice(-6)")));
			await sleep(250);
		}
		throw new Error("no " + mark + " after " + seconds + " s; the page's last lines: " + JSON.stringify(await page.evaluate("rta.log.slice(-6)")));
	};
	page.key = async (code, key, vk, ms = 60) => {
		await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", code, key, windowsVirtualKeyCode: vk }, sessionId);
		await sleep(ms);
		await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", code, key, windowsVirtualKeyCode: vk }, sessionId);
	};
	page.where = async () => {
		const raw = await page.evaluate("[rta.peek(rta.peek(0x4d8af0 + 0x43d8) + 0x10), rta.peek(rta.peek(0x4d8af0 + 0x43d8) + 0x14), rta.peek(rta.peek(0x4d8af0 + 0x43d8) + 0x18)]");
		return raw.map((r) => +new Float32Array(new Uint32Array([r]).buffer)[0].toFixed(1));
	};
	await page.navigate();
	return page;
}

const result = { mode, site, when: new Date().toISOString(), load_start: load() };
const say = (...a) => console.log(...a);

async function discs(cdp) {
	// files a person might pick that are not the disc (made by local/recomp-web/out/mkdisctests.py)
	const dir = path.join(OUT, "disc-tests");
	result.refusals = {};
	const page = await openPage(cdp, "discs");
	for(const name of fs.readdirSync(dir).sort()) {
		await page.pick(path.join(dir, name));
		let status = "";
		for(let i = 0; i < 100; i++) { await sleep(150); status = await page.status(); if(/^Not started|^Running|^Starting/.test(status)) break; }
		result.refusals[name] = status;
		say("  %s (%d bytes): %s", name.padEnd(22), fs.statSync(path.join(dir, name)).size, status);
		if(!/^Not started/.test(status)) { say("  FAILED: not refused"); process.exitCode = 1; break; }
	}
	result.state_after = await page.evaluate("rta.state");
	say("  the page after the refusals: %s (it still takes a disc image)", result.state_after);
}

async function play(cdp) {
	if(!DISC) throw new Error("give the disc image: --disc PATH or RTA_DISC");
	const page = await openPage(cdp, "play", "&card=0");
	await page.evaluate("rta.optionsForPick(" + JSON.stringify({ script: hubScript() }) + ")");
	const t0 = Date.now();
	await page.pick(DISC);
	await page.said("IN-HUB", 400);
	const info = await page.evaluate("rta.info()");
	result.picker = { to_hub_s: +((Date.now() - t0) / 1000).toFixed(1), disc_reads: info.disc_reads, disc_mb: +(info.disc_bytes / 1e6).toFixed(1), disc_ms: info.disc_ms, level: info.level,
		said: await page.evaluate("rta.log.filter((l) => /^(disc|page|memory card|sound)[: ]/.test(l))") };
	say("  file input: the image picked from this computer; in the first level after %s s; %d reads, %s MB, %s ms in all (File.slice on the page's thread); level %s",
		result.picker.to_hub_s, info.disc_reads, result.picker.disc_mb, info.disc_ms, info.level);
	for(const line of result.picker.said) say("    " + line);

	// ---- sound: how far behind is what is heard? ----
	const queue = [];
	for(let i = 0; i < 30; i++) { await sleep(1000); const s = (await page.evaluate("rta.info()")).sound_state; if(s) queue.push(s); }
	const last = queue[queue.length - 1] || {};
	result.sound = { samples: queue.length, queued_ms: queue.map((s) => s.queuedMs), most_ms: Math.max(...queue.map((s) => s.mostMs || 0)), dry: last.dry, bursts: last.bursts, given_up_ms: last.givenUpMs, playing: last.playing,
		audio: await page.evaluate("(() => { try { return rta.info().sound; } catch(e) { return String(e); } })()") };
	say("  sound over 30 s in the first level: queued %s ms (asked 70); most seen %d ms; ran dry %s times; %s bursts given up since the start, %s ms in all; playing %s  [load %d]",
		result.sound.queued_ms.join(" "), result.sound.most_ms, last.dry, last.bursts, last.givenUpMs, last.playing, load());

	// ---- a controller through the Gamepad interface (a stand-in object: no controller is attached to this Mac) ----
	await page.evaluate(`(() => {
		const pad = { index: 0, id: "AGENT TEST stand-in pad (STANDARD GAMEPAD Vendor: 0000 Product: 0000)", connected: true, mapping: "standard", timestamp: 0,
			axes: [0, 0, 0, 0], buttons: Array.from({ length: 17 }, () => ({ pressed: false, touched: false, value: 0 })), effects: [],
			vibrationActuator: { playEffect(kind, how) { pad.effects.push([kind, how.weakMagnitude, how.strongMagnitude]); return Promise.resolve("complete"); }, reset() { pad.effects.push(["reset"]); return Promise.resolve("complete"); } } };
		window.fakePad = pad;
		navigator.getGamepads = () => [pad];
		window.padPress = (i, on) => { pad.buttons[i] = { pressed: on, touched: on, value: on ? 1 : 0 }; };
	})()`);
	const p0 = await page.where();
	await page.evaluate("padPress(0, true)");                  // a press shows the controller to the page
	await sleep(300);
	await page.evaluate("padPress(0, false)");
	await sleep(300);
	const before = await page.where();
	await page.evaluate("fakePad.axes[1] = -1");               // left stick up
	await sleep(1500);
	const during = await page.evaluate("rta.info().pad");
	await page.evaluate("fakePad.axes[1] = 0");
	await sleep(500);
	const after = await page.where();
	await page.evaluate("fakePad.axes[0] = 0.1");              // inside the dead zone: nothing
	await sleep(400);
	const dead = await page.evaluate("rta.info().pad");
	await page.evaluate("fakePad.axes[0] = 0");
	result.pad = { name: during.name, stick_word: during.sticks.toString(16), moved: [before, after], dead_zone_word: dead.sticks.toString(16), where_first: p0 };
	say("  controller (stand-in object behind navigator.getGamepads): left stick up for 1.5 s moved the character from (%s) to (%s); stick word %s, in the dead zone %s",
		before.join(", "), after.join(", "), result.pad.stick_word, result.pad.dead_zone_word);
	if(before[0] === after[0] && before[1] === after[1]) process.exitCode = 1;

	// ---- pause: asked by the player (the P key), ended by a key ----
	const tick = async () => { const i = await page.evaluate("rta.info()"); return { sim: i.sim, fields: i.fields, paused_ms: i.paused_ms, pauses: i.pauses, queued: i.sound_state ? i.sound_state.queuedMs : null, dry: i.sound_state ? i.sound_state.dry : null }; };
	const a0 = await tick();
	await page.key("KeyP", "p", 80);
	await sleep(600);
	const a1 = await tick();
	await sleep(3000);
	const a2 = await tick();
	const sign = await page.evaluate("[document.getElementById('paused').hidden, document.getElementById('pausedWhy').textContent, document.getElementById('pause').textContent]");
	await page.key("KeyK", "k", 75);                           // any key: the pause ends, the key is not the game's
	await sleep(2000);
	const a3 = await tick();
	result.pause_asked = { before: a0, paused: a1, three_seconds_later: a2, after_key: a3, sign };
	say("  pause by the P key: fields %d -> %d -> %d over 3 s of pause (simulation tick %d -> %d), sign \"%s\"; after a key %d fields 2 s later (tick %d); the game stood %s ms in all; sound ran dry %s -> %s times",
		a0.fields, a1.fields, a2.fields, a1.sim, a2.sim, sign[1], a3.fields, a3.sim, a3.paused_ms, a0.dry, a3.dry);
	if(a2.fields !== a1.fields || a3.fields <= a2.fields) { say("  FAILED: the pause did not hold or did not end"); process.exitCode = 1; }

	// ---- pause: the tab is hidden (another tab is put in front of it), then comes back ----
	const b0 = await tick();
	await cdp.send("Emulation.setFocusEmulationEnabled", { enabled: false }, page.sessionId);
	const other = await cdp.send("Target.createTarget", { url: "about:blank" });        // a new tab in the same window: in front
	await sleep(1500);
	const hidden = await page.evaluate("[document.hidden, document.visibilityState, rta.paused()]");
	const b1 = await tick();
	await sleep(3000);
	const b2 = await tick();
	await cdp.send("Target.activateTarget", { targetId: page.targetId });
	await cdp.send("Emulation.setFocusEmulationEnabled", { enabled: true }, page.sessionId);
	await sleep(1500);
	const back = await page.evaluate("[document.hidden, rta.paused(), document.getElementById('pausedWhy').textContent]");
	const b3 = await tick();
	await cdp.send("Target.closeTarget", { targetId: other.targetId });
	await cdp.send("Input.dispatchMouseEvent", { type: "mousePressed", x: 600, y: 500, button: "left", clickCount: 1 }, page.sessionId);
	await cdp.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: 600, y: 500, button: "left", clickCount: 1 }, page.sessionId);
	await sleep(2000);
	const b4 = await tick();
	result.pause_hidden = { before: b0, hidden, at_hide: b1, three_seconds_hidden: b2, back, back_in_front: b3, after_click: b4 };
	say("  pause by a hidden tab: document.hidden %s, paused %s; fields %d -> %d over 3 s hidden; back in front it stays paused (%s, \"%s\"), fields %d; after a click on the sign %d fields 2 s later; sound ran dry %s -> %s times",
		hidden[0], hidden[2], b1.fields, b2.fields, back[1], back[2], b3.fields, b4.fields, b0.dry, b4.dry);
	if(!hidden[0]) say("  (the tab did not become hidden in this browser window: the hidden-tab pause was NOT exercised)");
	else if(b2.fields !== b1.fields || b3.fields !== b2.fields || b4.fields <= b3.fields) { say("  FAILED: the hidden pause did not hold or did not end"); process.exitCode = 1; }
	// sound after the pauses
	await sleep(4000);
	const s = (await page.evaluate("rta.info()")).sound_state;
	result.sound_after_pauses = s;
	say("  sound 6 s after the pauses: %s", JSON.stringify(s));
	// ---- the controller's buttons, last (one of them opens a menu of the game's, which stops its simulation): which bits the program is given
	const bits = [];
	for(let i = 0; i < 16; i++) {
		if(i === 9) { bits.push(null); continue; }             // Start would open the game's own menu here
		await page.evaluate("padPress(" + i + ", true)"); await sleep(60);
		bits.push((await page.evaluate("rta.info().pad")).buttons);
		await page.evaluate("padPress(" + i + ", false)"); await sleep(60);
	}
	const want = [0x4000, 0x2000, 0x8000, 0x1000, 0x0400, 0x0800, 0x0100, 0x0200, 0x0001, null, 0x0002, 0x0004, 0x0010, 0x0040, 0x0080, 0x0020];
	Object.assign(result.pad, { buttons_ok: bits.every((b, i) => b === want[i]), bits: bits.map((b) => b === null ? null : b.toString(16)), rumble_effects: await page.evaluate("fakePad.effects.length"), rumbles: (await page.evaluate("rta.info()")).rumbles });
	say("  controller: 15 buttons give the console's bits: %s; rumble calls by the game %d, effects played %d", result.pad.buttons_ok ? "all right" : "WRONG " + JSON.stringify(result.pad.bits), result.pad.rumbles, result.pad.rumble_effects);
	if(!result.pad.buttons_ok) process.exitCode = 1;
	result.problems = page.problems.slice(0, 5);
}

async function card(cdp) {
	const scripts = path.join(ROOT, "local", "recomp-out", "app-test");
	const page = await openPage(cdp, "card");
	await page.evaluate("rta.forgetCard()");
	await page.navigate();
	result.store_at_start = (await page.evaluate("rta.storedCard()")).length;
	// 1. a new game, saved through the game's own save screens
	if(!(await page.evaluate("rta.bootUrl('/dev/disc.iso', " + JSON.stringify({ script: pageScript(path.join(scripts, "save1.rig"), { shotPrefix: "card-" + site + "-" }), sound: false }) + ")"))) throw new Error("not started: " + await page.status());
	await page.said("SCRIPT-END", 500);
	const shows1 = await page.evaluate("rta.log.filter((l) => /SHOW|=/.test(l) && /memcard|0x/.test(l)).slice(-12)");
	const files = await page.evaluate("rta.cardFiles()");
	const synced = await page.evaluate("rta.syncCard()");
	await sleep(500);
	const synced2 = await page.evaluate("rta.syncCard()");
	const who1 = await page.evaluate("rta.log.filter((l) => /^(memory card|page)[: ]/.test(l))");
	result.save = { files, bytes: files.reduce((sum, f) => sum + f[1], 0), synced: [synced, synced2], said: who1, shows: shows1, shots: await page.evaluate("rta.shotsDone()") };
	say("  save: the game wrote %d files, %d bytes to its card; store write %s", files.length, result.save.bytes, synced2);
	for(const f of files) say("    %s  %d", f[0], f[1]);
	// 2. the page is loaded again: the store still has them
	await page.navigate();
	const stored = await page.evaluate("rta.storedCard()");
	result.after_reload = stored;
	say("  after the page was loaded again the browser's store holds %d entries (%d files)", stored.length, stored.filter((k) => /\.[A-Za-z0-9]+$|icon|SLUS/.test(k)).length);
	// 3. the game from the kept card: main menu, load
	if(!(await page.evaluate("rta.bootUrl('/dev/disc.iso', " + JSON.stringify({ script: pageScript(path.join(scripts, "load1.rig"), { shotPrefix: "card-" + site + "-" }), sound: false }) + ")"))) throw new Error("not started: " + await page.status());
	await page.said("SCRIPT-END", 500);
	const info = await page.evaluate("rta.info()");
	const shows2 = await page.evaluate("rta.log.filter((l, i, all) => /SHOW/.test(l) || (i > 0 && /SHOW/.test(all[i - 1]))).slice(-16)");
	result.load = { level: info.level, sim: info.sim, shows: shows2, where: await page.where(), said: await page.evaluate("rta.log.filter((l) => /^(memory card|page)[: ]/.test(l))"), files: await page.evaluate("rta.cardFiles()"),
		shots: await page.evaluate("rta.shotsDone()") };
	say("  load: second start says: %s", result.load.said.join(" | "));
	say("  load: level %s, simulation tick %d, the character at (%s)", info.level, info.sim, result.load.where.join(", "));
	for(const line of shows2) say("    " + line);
	result.problems = page.problems.slice(0, 5);
	await page.evaluate("rta.forgetCard()");
}

async function pictures(cdp) {
	const script = opt("script");
	if(!script) throw new Error("--script FILE");
	const page = await openPage(cdp, "pictures", "&card=0&pause=0");
	if(!(await page.evaluate("rta.bootUrl('/dev/disc.iso', " + JSON.stringify({ script: pageScript(script, { shotPrefix: opt("prefix", "pic-" + site + "-") }), sound: false }) + ")"))) throw new Error("not started: " + await page.status());
	await page.said("SCRIPT-END", 600);
	await sleep(500);
	result.shots = await page.evaluate("rta.shotsDone()");
	const info = await page.evaluate("rta.info()");
	result.info = { arith: info.arith, vu_arith: info.vu_arith, level: info.level, sim: info.sim, out: info.out, vu_fast_left: info.vu_fast_left };
	for(const s of result.shots) say("  %s at blank %d, %d x %d: %s", s.name, s.number, s.width, s.height, s.status === 204 ? "posted" : "NOT POSTED (" + s.status + ")");
	say("  game arithmetic %s, vertex programs %s; level %s at the end", info.arith, info.vu_arith, info.level);
	result.problems = page.problems.slice(0, 5);
}

async function main() {
	const modes = { discs, play, card, pictures };
	if(!modes[mode]) { console.error("usage: playtest.mjs discs|play|card|pictures [--site NAME] [--disc PATH] [--script FILE]"); process.exit(2); }
	fs.mkdirSync(OUT, { recursive: true });
	const { cdp, version } = await startChrome();
	result.browser = version;
	say("== %s  %s  %s  load %d", mode, site, version, load());
	try { await modes[mode](cdp); } catch(e) {
		say("  FAILED: " + e.message);
		result.failed = e.message;
		process.exitCode = 1;
	} finally {
		result.load_end = load();
		fs.appendFileSync(path.join(OUT, "playtest.jsonl"), JSON.stringify(result) + "\n");
		try { closing = true; await cdp.send("Browser.close"); await gone(); } catch(e) { /* gone */ }
		await sleep(300);
	}
	process.exit();
}
main();
