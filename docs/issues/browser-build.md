# Browser build (Play! compiled to WebAssembly) — working notes

Status: a first version runs (2026-10-12): built, measured, usable offline, and online
through a relay - between browser players, and since that afternoon between a page and
the Mac application in one game (both tried on one Mac, in step; section "Mixed games").
Not yet tried by a person. The summary is the state; the rest is the record.

Related pages: [STATE-OF-PLAY.md](../STATE-OF-PLAY.md) sets this build beside the other
routes to a game. The desktop application these notes compare with is
[tools/play-net](../../tools/play-net/README.md) (how to play:
[play-online.md](../play-online.md)); the patch set both apply is in
[online-setup.md](../online-setup.md); the sources of this build are in
[tools/play-web](../../tools/play-web/README.md). "Native build" in these notes means
that desktop application. The game's code translated to native C++ is another piece of
work: [native-recomp.md](native-recomp.md).

Question: does Champions: Return to Arms (SLUS-20973 v2.00) run at full speed in Chrome
on an Apple M5 Pro, at the title screen and standing in the first level, with the same
core changes as the native build (`tools/play-net/play-net.patch`) and the same patches?

## Summary

**Does it run at full speed in Chrome on the M5 Pro? Yes, when the Mac is not busy with
other work, at the title and standing in the first level** (Chrome 155, resolution
factor 1 and 2; factor 4 with the canvas the page now uses):

| Where | frames/s | machine thread | video thread | limiter off |
|---|---|---|---|---|
| title screen | 59.95 – 60.04, also at load 115 – 138 (not in three starts under load: point 3 below) | 6 – 9 ms/frame | 2.4 – 3.5 ms/frame | — |
| first level, standing, factor 2 (load 9) | 59.98 | 9.9 ms CPU/frame | 6.2 ms CPU/frame | 93 frames/s |
| first level, standing, factor 1 (load 12) | 59.97 | 11.6 ms CPU/frame | 7.4 ms CPU/frame | 76 frames/s |
| first level, the first 10 s after arriving | 58 | (1,700 blocks of code being translated) | | |

(Play! runs the NTSC machine at 60.00, not 59.94; "full speed" here is 60.) A frame has
16.7 ms; the machine thread is the one nearer the limit, with about a third in reserve.
With the Mac loaded by other test runs (load 80 – 170, which it was for most of this
work) the level drops to 28 – 53 frames a second; the title mostly holds 60.

What limits it, in order:

1. **The machine thread** (10 – 12 ms): game code translated to WebAssembly, one small
   module per block, 194,000 block starts a frame through a dispatcher (the desktop
   build links blocks to each other; the browser port does not). By Play!'s own zones:
   EE 30 %, VU 28 %, GIF 20 %, VIF 12 %, IOP 5 %.
2. **The video thread** (6 – 7 ms, was 30): every WebGL call is checked and shipped to
   another process; fixed by not making calls that change nothing (below).
3. **Other work on the computer, and whether the page is in front**: a hidden or covered
   page is run at low priority with late timers (7 – 45 frames a second, sound breaking
   up). And the load average does not say how busy the fast cores are: in a Chrome
   started in the background by the test, page visible, the title ran at 60.04, 59.99
   and 59.95 in one series (loads 62 – 115) and at 36, 39 and 45 in three other starts
   (loads 51 – 64; two without sound, one with), while Chrome brought to the front with
   `open -a` held 60 at load 138. What the other work is (three native instances drawing
   at 4×, compilers, iCloud) and whether the browser is the application in front both
   seem to matter; not untangled. Nothing a page can do about it.
4. A canvas of 1749 × 1312 pixels instead of 1195 × 896 cost speed in each of the
   three runs that had one (41 – 49 frames a second in the level at load 8, where the
   same level otherwise ran at 60; 27 – 32 at load 80 with the video thread waiting some
   11 ms a frame on top of its work). Point 3 may be part of it and the cause was not
   found; the page keeps its canvas at 896 lines, at which factor 4 ran as fast as
   factor 2 under the same load.

What was changed to get there (all in `tools/play-web`): the video thread owns the
canvas (OffscreenCanvas; upstream sends every GL call to the page's main thread);
redundant GL calls are left out (28,700 WebGL calls a frame became 11,700) and unchanged
uniform blocks are not re-sent (video 30 ms → 13 ms at the same load); the mimalloc allocator; the disc read in place by range requests on the machine's
thread. Tried without gain: compiling the C++ with WebAssembly SIMD.

**What works** (how each was checked is under "Checked" below): build script; boot of the
player's own disc image read in place, with the wrong-disc refusal; the patch set and
the display patches; a steady picture; keyboard; sound; the memory card and the settings
kept in the browser; resolution factor 1 – 4 changeable while playing (2 by default);
title and first level reached and looked at.
**Not checked by a person**: a controller (needs a button pressed on it), the file
dialog and the "continue with the remembered image" button, how the sound sounds, full
screen.
**Online** (section "Online play from a browser: built"): a relay and the page's side of
it; one-step online and games by code as in the desktop application; two Chrome pages
hosted and joined by code and ran 1,387 lockstep frames with equal sync hashes.
**With the Mac application** (section "Mixed games"): one page and one application copy
in one game through the relay, both orders, 2,300 to 3,900 lockstep frames a stretch in
step, across a level change; the application changes its arithmetic by itself and the
page says whether everyone computes the same way. Three players do not get into a game
on the test Mac, with or without a page.
**Not there**: a session that survives a lost connection to the relay, pacing by the
display's refresh, anything beyond the first level.
**Other browsers, first use, robustness** (section "For whoever opens the link"): the
page now asks the browser what it has before it loads anything and says plainly what is
missing; it runs in Brave and in Safari's engine (WebKit 27.2, in a window of the test's
own: Safari's WebDriver is not enabled on this Mac) as well as in Chrome; in Safari's
engine level loads stall, because translating a block of game code costs it 6 to 19
times what it costs Chrome. Firefox, Edge, Windows, Linux, phones and every real
controller: read, not run.

## Where things are

| What | Where |
|---|---|
| sources of the web front end, patch, build script, local test server, README | `tools/play-web/` |
| my copy of Play! (commit 83700b2c + `play-net.patch` + `play-web.patch` + `src/`) | `local/play-web-src` (not in the repository) |
| every Play! file `play-web.patch` touches, as it is after `play-net.patch` | `local/play-web-orig` (`local/play-web-out/mkpatch.sh` writes the patch from the two) |
| build directories | `local/play-web-build`; `local/play-web-build-prof` (`-DPROFILE=ON`, for `rta.zones()`); `local/play-web-build-simd` (the SIMD trial) |
| the page as served | `local/play-web-site` (and `/prof`, `/simd` below it) |
| the relay, its test, how to run it | `tools/play-web/relay/` (`relay.py`, `check.py`, `README.md`) |
| the page's side of online play | `tools/play-web/src/RtaWebNet.cpp`, `RtaWebNet.h`, `RtaWebNetCore.cpp`, `RtaWebSock.h`; the panel and the connection in `web/rta-web.js`, `web/index.html` |
| online test helpers (not in the repository) | `local/play-web-out`: `cdp.py` (drives a Chrome of the test's own through its DevTools port), `online-pair.py` (two pages: host by code, join by code, start), `pair-check.py` and `sample.js` (the two pages' sync hashes compared frame by frame), `makechar.js` (presses through the character screens), `online-rebuild.sh`; the test site `local/play-web-online-site`; `relay.log` |
| putting it on a server (not in the repository: it knows the server and the private path) | `local/friend-download/web-setup.sh` (once: certificate, relay service, site), `web-update.sh` (page and relay up, checks) |
| test helpers and their output (not in the repository) | `local/play-web-out`: `chrome-run.py` (a series of page runs in one Chrome tab, in a Chrome of its own, or in the pane), `cpu.py` (thread CPU time of the renderer), `native-trace.py` and `compare-trace.py` (the position trace against the desktop build), `report*.jsonl`, `*-run*.txt` |
| pictures of the page's canvas (game output) | `local/play-out/web-hub.png`, `web-hub-4x.png` |
| the other-browsers work: its own tree, build and site, browser profiles, the WebKit test window, a server that answers as the deployment does, its output (not in the repository) | `local/play-web-compat/` (listed at the end of the section "For whoever opens the link") |

## Installed

`brew install emscripten` (6.0.12). Homebrew brought its dependencies with it: abseil,
simdutf, hdrhistogram_c, libffi, libnghttp2, libuv, llhttp, merve, simdjson, readline,
highway, python@3.14, openjdk, yuicompressor, and it upgraded node 26.5.0 to 26.11.1.
Nothing else was downloaded (no npm packages: the page is plain HTML and JavaScript, not
Play!'s React application under `js/play_browser`, which needs `npm install`).

## Log (what was done, in order)

1. The tree: `local/play-playable` copied without `.git` to `local/play-web-src`, the
   files under `local/play-orig/Source` put back, `tools/play-net/play-net.patch` applied
   (no rejects). `emcmake cmake … -DBUILD_TESTS=OFF -DBUILD_PLAY=ON -DBUILD_PSFPLAYER=OFF
   -DUSE_QT=OFF`: all 429 objects compile with the patch as it is. Only the link failed
   (`-sUSE_ES6_IMPORT_META=0` is no longer accepted by Emscripten 6).
2. A front end of our own instead of Play!'s React application (which needs `npm
   install`): `RtaWeb.cpp`, a plain page. Video thread given the canvas; disc read by
   range requests; patches written on `OnExecutableChange`; pad, counters, test aids.
   First run in the pane: boots, title 60, level 26 frames a second.
3. `rta.glProfile`: 28,700 GL calls a frame → `GlStateShadow.h`, uniform blocks only when
   changed → video thread 30 → 13 ms.
4. First run in Google Chrome itself (load 160+): title 60, level 28 – 50; picture saved.
5. A build with Play!'s profiler zones (`-DPROFILE=ON`): machine thread EE 30 %, VU 28 %,
   GIF 20 %, VIF 12 %, IOP 5 %. mimalloc. SIMD trial (no gain). Block starts counted:
   194,000 a frame.
6. With the Mac quiet: level 60 at factors 1 and 2 in Chrome; 93 with the limiter off.
7. The "4× is slow" hunt: found that hidden pages and (probably) a background browser
   without sound are held back by the system; visibility recorded with every figure
   from then on; canvas capped at 896 lines.
8. The page for a person: disc picker with the remembered handle, menu (picture factor
   live, sound, controls, full screen, disc), sound through an AudioWorklet, memory card
   and settings in the browser's storage, licences, "not affiliated" line. Stand-in file
   test of the player's disc path; refusals; keyboard; card persistence.
9. Position trace against the desktop build: rounding difference seen in the bits.
   Online design written.
10. Online play built from that design (another session; the first one was stopped after
    the relay and its test were written): the socket calls of `RtaNet.cpp` as relay
    messages, the adaptor's hooks, the network setting on the card, `RtaOnline.cpp`
    compiled in, the panel. Compiled and linked at the first attempt; the first page
    reached the lobby at the first attempt; two pages in one game in step.
11. Found while testing: the test Mac's lid was closed and it went into "Clamshell
    Sleep" every minute or two; at each of those Chrome closed every connection it had.
    A screen wake lock added to the page (it does not help against a closed lid).
12. The scripts for the server written and tried there without changing anything
    (`web-setup.sh --check`); the setup itself is the owner's to run.
13. For whoever opens the link (another session): a build from an empty directory; the
    start-up check; Brave and Safari's engine run; the picked-file path with the real
    image; a file that goes away; pause; one tab; settings, key and controller tables,
    on-screen pad; saved games as a file; cold and warm start; memory over 20 minutes.

## Left to do

- A controller, the file dialog, "Continue with …", full screen and the sound have to be
  tried by a person (start `tools/play-web/serve.py`, open http://127.0.0.1:8973/).
- A level reading of the sound at full speed (the Mac was loaded whenever it was tried).
- Why a 1312-line canvas costs what it does; whether a browser in the background without
  sound is really held back by macOS (two observations, no proof).
- Pacing by the display's refresh (the desktop build's `RtaMac.mm` does it; a worker has
  `requestAnimationFrame`): today the machine runs on a timer at 60.00 and the browser
  shows each picture at its next refresh, so motion can stutter on a 59.94 or 120 Hz
  display although nothing is slow. Not looked at.
- Linking translated blocks with WebAssembly tail calls (`return_call_indirect` through
  table slots that are patched as Play!'s native code patches jump targets): the largest
  remaining lever for the machine thread, perhaps 2 of its 10 ms. Not started.
- Levels beyond the first, fights, spells: not visited. Code the game overwrites after it
  has run is not noticed in a browser (no page protection); nothing of the kind was seen
  up to the first level.
- Safari itself, Firefox, Edge, Windows, a touch screen, every real controller: the list
  "What needs a person, or a machine that is not here" in the section "For whoever opens
  the link". (Safari's engine was run: it has everything the page needs; a build from an
  empty directory by `build.sh` was run too - from a copied tree, not from a clone.)
- Safari's engine needs milliseconds for every block of game code translated (one
  WebAssembly module each): several blocks to a module, or translation ahead of need.
- Frame pacing on Windows on battery power (the waits may be 15.6 ms coarse there): read,
  not measured.
- Online: the relay on the public server (prepared, see "Putting it on a server"); then
  two players in different places; more than two players; a level beyond the first.
- A session that survives a lost connection to the relay (the relay would keep a
  session's sockets for some seconds and both sides would send again what the other has
  not confirmed); WebTransport for the game's datagrams.
- Mixed games (section "Mixed games"): the relay and the page on the server; two
  computers; why a game of three does not start for the third machine.

## How Play!'s browser port works (read in the source)

- The machine thread and the video thread are pthreads (web workers on a shared
  WebAssembly memory): the page must be served with `Cross-Origin-Opener-Policy:
  same-origin` and `Cross-Origin-Embedder-Policy: require-corp`.
- Translated code: every basic block of MIPS code becomes a WebAssembly module of its own
  (`CMemoryFunction`: `new WebAssembly.Module` + `Instance`, put into the function table).
  Blocks are not linked to each other in this configuration (`BasicBlock.cpp`,
  `__EMSCRIPTEN__`): every block returns to the dispatcher.
- No write protection of memory pages: translated code is not thrown away when the game
  overwrites it (`CEeExecutor::SetMemoryProtected` does nothing). Patches therefore have
  to be in place before the code is first run, or the range has to be cleared by hand.
- No control of the floating-point rounding mode (`fesetround(FE_TOWARDZERO)` has no
  effect in WebAssembly): results can differ in the last bit from the native build. This
  matters for online play between a browser and a native player (docs/issues/float-divergence.md).
- Upstream draws through a WebGL context made on the page's main thread and used from
  the video thread: Emscripten then sends every GL call to the main thread.
- Upstream reads the disc by asking the main thread for each piece and polling for it.

## How to boot it and read the numbers (tests on the developer's own Mac)

```
tools/play-web/build.sh                      # Play.js + Play.wasm and the page into local/play-web-site
tools/play-web/serve.py --port 8973 \
    --disc "/path/to/Champions - Return to Arms (v2.00).iso" \
    --report local/play-web-out/report.jsonl --shots local/play-out
open -a "Google Chrome" "http://127.0.0.1:8973/index.html?title=AGENT%20TEST%20-%20browser%20build&disc=/dev/disc.iso&res=1&sound=0&auto=hub&report=1&shot=web-hub.png"
```

The server listens on 127.0.0.1 only and sends the two cross-origin isolation headers.
`--disc` makes the image readable by range requests at `/dev/disc.iso`; nothing is copied.
A player does not need `--disc`: the page's *Choose disc image…* button reads the file
where it is.

Address parameters of the page (`tools/play-web/web/rta-web.js`, top):

| Parameter | Meaning |
|---|---|
| `title=TEXT` | the page's title (tests: `AGENT TEST - browser build`) |
| `disc=/dev/disc.iso` | DEV: boot the image the local server serves, without the file dialog |
| `res=N` | resolution factor (1 … 8) |
| `sound=0` | no sound |
| `patches=0`, `display=0`, `sections=*` | no patch set / no display patches / every section of the patch file |
| `gl=main` | DEV: WebGL context on the page's main thread, as upstream Play! does it (for comparing) |
| `limit=0` | DEV: the machine runs as fast as it can |
| `auto=title` or `auto=hub` | DEV: scripted presses to the title screen, or on into the first level (the button sequence of `local/play-out/tohub.py`), a measurement at each (title 10 s; level: the first 10 s, then 15 s), eight consecutive pictures compared, in the level also 10 s with the limiter off |
| `report=1` | DEV: every figure is POSTed to `/report` (appended to the `--report` file, one JSON object per line: `kind` is `start`, `second`, `title`, `title-burst`, `hub-arrival` (the first 10 s in the level), `hub` (the 15 s after), `hub-burst`, `shot`, `hub-unlimited`, `done` or `failed`) |
| `relay=ws://127.0.0.1:PORT/relay` | DEV: go online through a relay on this computer (only loop-back addresses are taken); otherwise the relay is the one `online.json` beside the page names |
| `shot=NAME.png` | DEV: with `auto=hub`, one picture of the canvas in the level is POSTed to `/shot/NAME.png` (written to the `--shots` directory; game output, keep it under `local/`) |
| `pause=0` | DEV: the game is not paused when the page is hidden (`auto=` and `report=1` imply it: tests run unwatched) |
| `discread=page` | DEV: a picked file is read through the page's main thread, as in a browser that answers no range requests on it |
| `touch=1` | the on-screen pad is shown at once |
| `card=0`, `canvas=LINES` | DEV: an empty memory card that is not kept; the canvas's height |

The page sets four marks for whoever times a start (`performance.getEntriesByType("mark")`):
`rta-checked` (the start-up check is through), `rta-program` (the emulator is loaded),
`rta-ready` (its threads are up: the button is shown) and `rta-boot` (a disc was given).
For tests `rta` also has `rta.check` (the start-up check's answers), `rta.card`,
`rta.disc()`, `rta.paused()`, `rta.bindings()`, `rta.zipCard()`, `rta.importCard(blob)`.

What the figures mean (`rates()` in `rta-web.js`, counters from `rtaInfo` in `RtaWeb.cpp`):

- `fps`: vertical blanks of the emulated machine per second of wall clock (60.0 is full
  speed: Play! runs the NTSC machine at 60, not 59.94). `presents_per_second`: pictures
  handed to the canvas.
- `machine_ms_per_frame`: wall-clock time of a frame on the machine's thread minus the
  time it slept in the frame limiter. It includes any time the thread waited for the
  video thread or the disc. Above 16.7 the game is slow.
- `video_ms_per_frame`: wall-clock time the video thread spent inside its calls (drawing,
  texture work, the GL calls as far as the page's process is concerned). The work of the
  browser's GPU process is not in it.
- Both are wall-clock times: on a loaded computer they grow when the threads are
  pre-empted. CPU time per thread cannot be read from inside a page; from outside:
  `ps -M -p <pid of the tab's renderer process>` twice, some seconds apart, gives every
  thread's user and system time (`local/play-web-out/threads.sh` does that).
- `gl_calls_per_frame` / `gl_calls_left_out_per_frame`: calls of the kinds
  `GlStateShadow.h` watches that were made / were left out because they would have set
  what was set already.
- `functions_made`, `function_ms_per_frame`: blocks of game code translated to
  WebAssembly in the interval, and the time that took.
- In the console of the page: `await rta.measure(10)`, `await rta.burst(8)`,
  `await rta.glProfile(5)` (every WebGL call of the video thread counted and timed by
  name), `rta.info()`, `rta.peek(address)`, `await rta.tap("cross", 8, 60)`.

## Measurements

All on the Apple M5 Pro, resolution factor 1, no sound, patch set and display patches on,
limiter on unless said. "Pane" is the desktop application's built-in browser (Chromium
152 engine); "Chrome" is Google Chrome 155 started with `open -a`. The computer was
shared with other test runs all the time: the load average is given with every row, and
at loads above 100 the wall-clock figures say little.

| Build | Where | Browser | Load | frames/s | machine ms/frame | video ms/frame | draws |
|---|---|---|---|---|---|---|---|
| first (canvas owned by the video thread, no other change) | memory-card screen | pane | 17 | 60.1 | 2.1 | 0.7 | 272 |
| first | title | pane | 17 | 60.1 | 8.8 | 4.0 | 108 |
| first | hub, standing | pane | 18 | 26.0 – 31.0 | 38.5 – 31.7 | 30.3 – 24.3 | 874 |
| + redundant GL calls left out, unchanged uniform blocks not re-sent | title | pane | 66 | 59.95 | 8.75 | 3.74 | 105 |
| the same | hub, standing | pane | 66 | 48.9 | 20.4 | 12.9 | 871 |
| the same | hub, limiter off | pane | 66 | 53.7 | 18.6 | 13.0 | 871 |
| the same | title | Chrome | 125 – 138 | 60.04 | 14.4 | 6.6 | 106 |
| the same | hub, first 10 s (1,789 blocks being translated) | Chrome | 159 – 171 | 28.0 | 35.7 | 20.8 | 875 |
| the same | hub, limiter off | Chrome | 171 | 34.4 | 29.1 | 20.8 | 875 |
| the same | hub, standing, the next 21 s | Chrome | 165 | 50.5 | 20.8 | 15.1 | 875 |

Later builds (+ mimalloc; the computer much quieter). One Chrome tab, scripted route
(`local/play-web-out/chrome-run.py`), canvas 1195 × 896 at factors 1 and 2, 1749 × 1312
at factor 4:

| Factor | Where | Browser | Load | frames/s | machine ms/frame (wall) | video ms/frame (wall) | machine thread CPU ms/frame | video thread CPU ms/frame |
|---|---|---|---|---|---|---|---|---|
| 1 | title | Chrome | 12 | 60.00 | 9.1 | 3.5 | | |
| 1 | hub, first 10 s (1,718 blocks being translated) | Chrome | 12 | 58.1 | 13.6 | 7.5 | | |
| 1 | hub standing, the next 15 s | Chrome | 12 | 59.97 | 13.6 | 8.2 | 11.6 | 7.4 |
| 1 | hub, limiter off | Chrome | 12 | 75.6 | 13.2 | 8.2 | | |
| 2 | title | Chrome | 9 | 59.99 | 6.3 | 2.4 | | |
| 2 | hub standing | Chrome | 9 | 59.98 | 10.1 | 5.9 | 9.9 | 6.2 |
| 2 | hub, limiter off | Chrome | 9 | 93.3 | 10.7 | 6.4 | | |
| 4 | title | Chrome | 8 | 60.04 | 6.2 | 2.4 | | |
| 4 | hub standing | Chrome | 8 | 41.6 – 45.8 | 22 – 24 | 16 – 17 | 20.3 | 14.8 |
| 4 | hub, limiter off | Chrome | 8 | 48.8 | 20.5 | 14.7 | | |
| 1 | hub standing | pane | 12 | 60.0 | 10.5 | 6.4 | 10.4 | 6.6 |
| 1 | hub, limiter off | pane | 12 | 93.0 | 10.8 | 6.5 | | |
| 4 (canvas 969 × 727) | hub standing | pane | 6 | 60.04 | 10.1 | 6.0 | | |

The same 194,000 block starts and 8,300 GL calls per frame at every factor. The first
seconds in a level are slower than what follows: its code is being translated (1,700
blocks) and the browser replaces its quick first translation of each block by an
optimised one in the background.

With the C++ compiled for WebAssembly SIMD (`-msimd128`; a second build directory, same
session, load 9): machine thread 10.3 ms CPU per frame, video 6.5 — the same as without
(10.4 and 6.6). Not used.

A Chrome of its own for the tests (separate profile, started by `chrome-run.py` in
the background, sound allowed without a click and muted by flag; page visible
throughout; the Mac busy again with three native instances of another test):

| Factor, canvas | Sound | Where | Load | frames/s | machine ms/frame wall / CPU | video ms/frame wall / CPU | Sound ran dry |
|---|---|---|---|---|---|---|---|
| 2, 1195 × 896 | on | title | 62 | 60.04 | 11.2 | 4.7 | 0 times in 10 s, 64 ms queued |
| 2, 1195 × 896 | on | hub standing | 85 – 96 | 30 – 48 | 21.0 / 19.2 | 15.1 / 14.0 | 53 times in 15 s |
| 4, 1195 × 896 | on | title | 115 | 59.99 | 12.2 | 5.7 | 0, 67 ms |
| 4, 1195 × 896 | on | hub standing | 107 – 137 | 48 – 53 | 19.0 / 18.1 | 13.8 / 13.4 | 33 times in 15 s |
| 4, 1749 × 1312 | on | title | 74 | 59.95 | 10.6 | 4.8 | 0, 68 ms |
| 4, 1749 × 1312 | on | hub standing | 74 – 94 | 27 – 32 | 37.6 / 21.5 | 26.7 / 15.6 | 53 times in 15 s |
| 1, 1195 × 896 | off (`sound=0`) | title | 51 – 64 | 38.9, 44.7 (two runs) | 25.6, 21.2 | 19.9, 14.3 | — |
| 2, 1195 × 896 (a later start) | on | title | 56 | 36.4 | 27.5 | 12.6 | 33 times in 10 s |
| 2, 1195 × 896 (the same start) | on | hub standing | 76 – 84 | 43 – 46 | 23.1 / 20.2 | 16.7 / 14.8 | 39 times in 15 s |
| 2, 1195 × 896, **`gl=main`: the WebGL context on the page's main thread as upstream Play! has it**, everything else ours (same Chrome session) | on | hub standing | 76 – 123 | 27 – 29 | 35.8 / 20.8 | 35.3 / 18.5, and the page's main thread 12.5 ms CPU a frame | 52 times in 15 s |

| 2, 1195 × 896, the last build (picture `local/play-out/web-hub-2x.png`) | on | title | 97 | 59.94 | 13.1 | 6.1 | 0 times in 10 s, 86 ms queued |
| the same | on | hub standing | 69 – 84 | 43.6 – 46.8 | 23.0 / 20.1 | 16.2 / 14.2 | 44 times in 15 s |

So with the load the same within what can be told, the video thread owning its canvas
gives about 45 frames a second where sending the GL calls to the main thread gives 28.

Figures from the desktop application's browser pane taken while the pane was hidden
(most of them, late in the evening) are left out: 7 to 50 frames a second at the title
with both threads at a third of a core. Every figure the page reports now carries the
time the page was hidden during it (`hidden_seconds`), and the test server stamps the
load average on every line.

Earlier thread CPU time in Chrome at load 165 (`ps -M` on the renderer process, two readings 20 s apart,
1,060 frames between them, load 165): machine thread 18.0 ms per frame, video thread
13.0 ms per frame, every other thread of the renderer under 0.6 ms.

Still picture: on the memory-card screen 12 consecutive pictures are identical (0 pixels
differ, `rta.burst(12)`); title and level are animated all the time (title: 40 % of the
pixels differ from picture to picture, it is a 3-D scene; hub standing: about 1 %, the
idle animation and the water).

Translation of game code: 8,590 blocks from power-on to the memory-card screen in 0.28 s
(33 µs each, at load 17); nothing is translated in steady state.

### Where the video thread's time went (first build, hub, `rta.glProfile(5)`)

28,700 WebGL calls per frame: `texParameteri` 7,763, `bufferData` 2,621, `bindBuffer`
2,624, `bindBufferBase` 1,761, `bindTexture` 1,726, `activeTexture` 1,726, `enable` 1,586,
`drawArrays` 883, `bindVertexArray` 883, `getParameter` 791, `useProgram` 790, `viewport`
795, `colorMask` 794, `scissor` 791, `blendFuncSeparate` 776, `depthMask` 776,
`blendEquationSeparate` 776, `depthFunc` 774. Play!'s handler sets a whole group of state
whenever the game writes the register behind it, changed or not, and this game writes
them all before nearly every one of its 880 draws. A desktop GL driver drops such a call
in nanoseconds; in a browser each one is checked, packed, sent to the GPU process and
checked again. Changes (`tools/play-web/src/GlStateShadow.h`, `play-web.patch`):
the state is remembered on our side and a call that would not change it is not made
(15,000 calls a frame left out, 8,300 of the watched kinds remain), and the two uniform
blocks are sent only when their values differ from what was sent last.

### What the video thread still sends (last build, hub, `glprofile=1`)

11,700 WebGL calls a frame for 894 draws, about 13 a draw: `bufferData` 2,502 (the
vertices of every draw, and the two uniform blocks, which do differ from draw to draw
most of the time), `activeTexture` 1,740, `bindTexture` 1,728, `texParameteri` 1,586,
`bindBuffer` 1,501, `drawArrays` 894, `useProgram` 800, `blendFuncSeparate` 784;
everything else under 40. These are real changes: the game alternates between two kinds
of draw. What could still be taken out: `activeTexture` (by switching the unit only when
a call for it is really made, about 1,600 calls), the two `texParameteri` a draw (sampler
objects), the uniform blocks (one large buffer and `bindBufferRange`). With the video
thread at 6 – 7 ms of a 16.7 ms frame none of it was done.

## Checked

| What | How | Result |
|---|---|---|
| the build from the repository's files | `tools/play-web/build.sh` run on my tree (it finds the patches applied); separately, a copy of the tree put back to Play!'s own files, `play-net.patch` and `play-web.patch` applied to it, `src/` copied in, compared with my tree | builds; the trees are the same except `Source/ui_qt/mainwindow.cpp` (the Qt front end, not part of this build: `play-net.patch` has changed there since I applied it). A build from an empty directory by the script was not run |
| the player's disc path: a picked file read in place through a `blob:` address, by range requests made on the machine's thread | no file dialog can be driven here, so a stand-in: a `File` as large as the image (4,293,984,256 bytes) made in the page of the 236 pieces of 128 KiB the game reads up to the title screen and one zero piece named 32,525 times (`rta.standIn`), given to the same function the picker calls | disc check passed, executable loaded and checked, title screen reached; 249 pieces fetched, 0 errors. (Each fetch took 9 – 32 ms because that stand-in has 32,761 parts; a real file is one part) |
| the wrong-disc refusal | `rta.checkDisc` with a 1,000-byte "image", with zeroes, with the real image but `SYSTEM.CNF` naming `SLUS_209.93`, with the real image and one bit of the program flipped, with the real image | "too small"; "no ISO 9660 volume"; "another game (SLUS_209.93)"; "another version (checksum 4028A55E; wanted 4028A55F)"; accepted |
| patches | the emulator's line at boot | `SLUS_209.73;1`, checksum `4028A55F`, 87 words written (81 from the 19 suggested sections, 6 display patches), in every run |
| steady picture | `rta.burst(12)` on the memory-card screen | 12 consecutive pictures, 0 pixels differ |
| the picture itself | the page's canvas read back on the video thread and saved as PNG by the test server | `local/play-out/web-hub.png` (factor 1) and `web-hub-4x.png` (factor 4): level, character, the other figure, bars and level badge as in the desktop build |
| keyboard | key events for K, ↑, D and Enter sent to the page; the pad word the machine reads | buttons 8720 = ✕ + up + Start, left stick x 255; all zero again after release. Not checked: a key pressed by a hand |
| controller | — | the page reads the first pad the browser reports with the standard layout; a browser reports a pad only after a button was pressed on it, which no test here can do. **Unchecked** |
| sound | a Chrome started with sound allowed without a click and muted (`--autoplay-policy=no-user-gesture-required --mute-audio`); the worklet's count of times the ring ran dry | title: 0 times in 10 s at 60 frames a second, 64 – 68 ms queued, in three runs. First level with the Mac loaded (30 – 48 frames a second): 33 – 53 times in 15 s — the machine makes too little sound when it is slow. No level reading at full speed yet. Nobody listened |
| memory card | the files Play! keeps, listed at the start of a later visit (`rta.files()`); a marker file written, the page loaded again | the game's own folder `vfs/mc0/BASLUS-20973` (3 files, written by the game at its memory-card screen) and the marker were there at the next visit. Not checked: a game saved by playing and loaded again |
| settings | the menu's factor changed while the title ran (2 → 4 → 2) | the picture went on (not black, same brightness within 2 %), the choice was stored. Mute is stored the same way |
| the remembered image (File System Access handle) and the file dialog | later, in the section "For whoever opens the link": the real image given to the page's file chooser without a dialog (DevTools), and dropped on the page (which hands out a handle) | boots from the picked file, read in place; the handle is kept and "Continue with <file>" is offered at the next visit. **Unchecked**: the dialog itself, and the browser's question "may this page read the file again?" after the click (only a person can answer them) |
| one page, one tab | `chrome-run.py` sends one tab from test to test and the page closes itself; or a Chrome of its own with its own profile, ended by the script | no window was left behind by those; the very first test's tab (opened before that existed) had to be left to the user |

## For whoever opens the link: browsers, first use, robustness (2026-10-12)

The page had only ever run in Chrome on one Mac. This section is the work to make it
start, say what is wrong when it cannot, and be pleasant the first time, for a person on
another browser or computer. What was run was run on the same Mac (Chrome 155, Brave 155,
the system's WebKit 27.2); everything about Windows, Linux, Firefox, phones and real
controllers is from reading the code and is marked so. The Mac was under heavy load from
other work the whole time (load average 350 – 490): speeds measured here say little.

### What the page needs, and what each browser on this Mac has

The page asks the browser itself at start (`rtaCheck` in `web/index.html`, a plain script
in old syntax that runs before anything large is loaded - also in a browser too old for
the rest). Answers as given by each browser here:

| What the page needs | What for | Chrome 155 | Brave 155 | WebKit 27.2 (Safari's engine) | Without it |
|---|---|---|---|---|---|
| https or localhost | everything below | yes | yes | yes | **does not start**; says "open the https:// address" |
| cross-origin isolation, shared memory, WebAssembly threads | the emulator's threads | yes | yes | yes | **does not start**; says whether the server sends no headers (the site's fault), the page is inside another page, or the browser is too old or embedded |
| WebAssembly SIMD, bulk memory, sign extension, saturating conversions, 64-bit integers | the emulator, and the code it translates the game to (SIMD) | yes | yes | yes | **does not start**; names what is missing |
| module scripts and module workers | Emscripten starts its threads as module workers | yes | yes | yes | **does not start** |
| WebGL 2 from a worker on an OffscreenCanvas | the video thread draws on its own | yes (ANGLE on Metal) | yes | yes ("Apple GPU") | **falls back** to a context on the page's main thread (`gl=main`, measured earlier: 28 instead of 45 frames a second under the same load) and says so |
| WebGL 2 at all | the picture | yes | yes | yes | **does not start**; says to switch hardware acceleration on. A software renderer (SwiftShader, llvmpipe) is named in a note |
| range request on a picked file's `blob:` address, synchronously, in a worker | the disc read in place by the machine's thread | 206 | 206 | 206 | **falls back** to reading through the page's main thread (new, below); a note |
| 1 GiB of shared memory in one piece | the emulator's fixed memory | yes | yes | yes | not asked beforehand (asking would allocate it twice); the failure is caught and explained ("phones, tablets and 32-bit browsers often cannot") |
| WebAssembly tail calls | linked blocks (speed) | yes | yes | yes | the build falls back by itself (`perf.patch`); nothing said |
| WebAssembly exceptions | only a build made with `-DRTA_WASM_EXCEPTIONS=ON` | yes | yes | yes | such a build would fail to compile: said as "cannot run the emulator's program (…)" |
| File System Access (`showOpenFilePicker`, handles) | "Continue with <file>" | yes | **no** (switched off in Brave; `brave://flags`) | **no** | the ordinary file dialog or a dropped file, at every visit; a note says so |
| AudioWorklet, with the shared memory handed to it | sound | yes | yes | yes | no sound; a note |
| Gamepad API | controllers | yes | yes | yes | keyboard (and touch) only; a note |
| IndexedDB | memory card, remembered image | yes (10 GB allowed) | yes (2 GB) | yes (19 GB in a store of the test's own; 1 GB in a store that is not kept) | the card is not kept; the start screen and Settings say so and offer the file export |
| Web Locks | one tab has the memory card | yes | yes | yes | no guard against a second tab |
| Screen Wake Lock | the screen stays on with a controller | yes | yes | yes | the screen may switch off |
| `DecompressionStream` | loading a zip of saved games that is compressed | yes | yes | yes | only uncompressed zips (the page's own) can be loaded; said when it happens |
| WebSocket | the relay (online play) | yes | yes | yes | — |
| Element full screen | Full screen | yes | yes | yes (Safari; off by default in an embedded WebKit) | the button says there is none |

Whatever makes the page not start is shown as a list in red under "The game cannot run
in this browser", ending with the browser's name; what merely works less well is a list
of notes under the buttons. A file of the page that does not load, a program the browser
cannot parse, a start that takes more than 20 s, the emulator's threads not coming up,
memory refused and a WebAssembly compile error each have their own sentence instead of an
empty page. Checked: every sentence's condition by reading; the paths that a current
browser takes (all present, the Brave note, the WebKit notes) by running.

Not installed on this Mac: **Firefox**, **Edge**. By reading: Edge is Chromium and has
everything Chrome has. Firefox (current and ESR 140) has all of the "does not start" rows
(module workers since 114, OffscreenCanvas WebGL since 105, tail calls since 121), has no
File System Access, and answers a range request on a `blob:` address with 206 according
to Chromium's own note on the matter ("Intent to Ship: Fetch-compliant range handling for
blob URLs" says Firefox does and passes the web platform tests for it) - the check
decides at run time and the fall-back is there either way. How much a block of translated
game code costs Firefox (the question that matters in Safari) is not known. **Not run in
Firefox at all.**

**Safari itself was not driven**: `safaridriver` answers "You must enable 'Allow remote
automation' in the Developer section of Safari Settings", and that setting was left
alone. Instead the system's WebKit - the same engine and version - was run in a small
window of the test's own (`local/play-web-compat/wk`, a WKWebView with a data store of
its own, the page's console piped out, a file chooser answered with a path instead of a
dialog). What that does not cover is Safari's own shell: its file dialog, its full
screen, its rule for sound without a click, its handling of hidden tabs, and that it
removes a site's storage after seven days without a visit.

### What was run where

| What | Chrome 155 | Brave 155 | WebKit 27.2 |
|---|---|---|---|
| start-up check, page reaches "Ready" | yes | yes | yes |
| boot from the test server's disc address, title screen | 60 frames/s (earlier measurements) | 60.0 (machine 11.4 ms, video 5.1 ms, load 361) | 42 – 58 (machine 12 – 22 ms, load 350 – 480) |
| first level by the scripted route, standing | 60 when the Mac is quiet (earlier); 43 – 53 at load 80 – 130 | not run | 35 – 50 at load 350 – 490 (machine 20 – 29 ms, video 13 – 15 ms); 43.7 with the limiter off |
| **the real image through the file chooser's path** (`<input type=file>`, the file given without a dialog), read in place | boots; 57 pieces to the first screen, 2.4 ms a piece | — | boots; 13 – 19 ms a piece |
| the image **dropped on the page**; handle kept; "Continue with …" offered at the next visit | yes; the browser's own question after the click was not answered by a test | — (no handles) | — (no handles) |
| the image read through the page's main thread (`discread=page`) | boots; 0.9 ms a piece | — | boots; 18 ms a piece |
| keys (real key events in Chrome; events made by script in WebKit) | ✕, sticks, release | — | ✕ and stick |
| a key changed in *Controls* by pressing it, and put back | yes | — | — |
| the on-screen pad by touch events | ✕, stick right 243, stick up 0, release | — | — |
| sound through the worklet | runs; 91 ms queued after a late start (343 before the fix below) | asleep without a click, as expected | runs; 71 – 91 ms queued |
| paused when hidden, goes on at a key / click, not by itself | yes (a tab in front of it; 0 frames while hidden; 60 after) | — | yes (its window taken off the screen; 0 frames; 58 after) |
| a second tab | told to wait; went on by itself when the first was closed | — | — |
| loaded again during play | card kept when written 2.2 s before; **lost when written 0.3 s before** (then: the card is now looked at every 0.4 s instead of every 5 s) | — | card kept from one run of the window to the next |
| storage full (quota set to 400 KB by DevTools) | "could NOT be written … (it is full)", Settings says so, "written again" when there is room | — | — |
| the picked file taken away during play (its address withdrawn) and chosen again | the game waits, the page says why and offers the button, the game goes on (121 frames in the next 2 s) | — | — |
| saved games to a zip and back; a zip made by `zip` (deflated, with the application's folder names) loaded | yes; the page's zip passes `unzip -t` and Python's `zipfile` | — | yes |
| full screen | asked for by a real click and **refused by Chrome in the unattended window** ("not granted"); the page said so | — | — |
| cold and warm start, memory over 20 minutes | below | — | — |

### What Safari's engine does differently (measured)

- **Translating game code is 6 to 19 times as expensive.** Every block of game code is
  a WebAssembly module of its own (`new WebAssembly.Module` + `Instance`). Under this
  session's load Chrome needed 0.2 ms a block (18,554 blocks in 3.6 s, load 370 – 395;
  33 µs at load 17 earlier); JavaScriptCore needed 1.2 ms a block up to the title
  (12,116 blocks, 14.1 s of translation, load 480) and 3.5 ms on arriving in the first
  level (1,722 blocks, 6.1 s, with five consecutive seconds in which the machine
  finished no frame). On a quiet Mac both will be less; the ratio is the finding: **in
  Safari the game stops for a noticeable time when a level loads and hitches when new
  code first runs.** Steady play is close to Chrome's under the same load. The cure is
  in the translator (many blocks to a module, or blocks translated ahead on another
  thread), not in the page; not started.
- Reading a piece of a picked file costs 13 – 19 ms (Chrome: 1 – 2.4 ms), whichever way
  it is read: loading from the disc is several times slower.
- The page's own check for "the emulator has stopped" therefore counts translated blocks
  and disc reads as signs of life, and waits half a minute.

### What was changed for it

In `web/index.html` and `web/rta-web.js` unless said (the online panel and the relay
connection were not touched):

- **The start-up check** (above) and the sentences for every way a start can fail.
- **Loading shown**: a bar and a status line - "Loading the emulator… 1.7 MB", "Reading
  the saved games…", "Starting the emulator…", "Checking the disc image…". The program
  is fetched by the page (`instantiateWasm`) so that the bytes can be counted; the
  compiler still gets the server's own response (a copy is read for the count), so the
  browser's cache of compiled code keeps working (warm start below).
- **The disc image**: the button, a file dropped on the page, or "Continue with <file>".
  The refusals name what the file is instead ("a zip archive, not a plain disc image:
  unpack or convert it to an .iso first" for zip, 7-Zip, RAR, gzip, CHD, CSO, ZSO;
  another game or another country's release; this game in another version) and a file
  that cannot be read says so. *Settings* shows which file is in use and can forget the
  remembered one.
- **A picked file that goes away** (`play-web.patch`: `Js_DiscImageDeviceStream.cpp`): a
  piece that cannot be read no longer ends the machine's thread with an exception that
  nobody catches (the picture froze and nothing said why); the thread asks again every
  300 ms, the page sees the error count rise, says "The game is waiting: your disc image
  can no longer be read…" and offers the button; a file chosen then is checked and given
  to the waiting machine, which goes on where it stood. Three seconds without a failed
  read also end it (a drive that came back).
- **Reading through the page's main thread** (same file, `RtaWebDiscMode(1)`): for a
  browser that does not answer a range request on a `blob:` address from a thread, the
  machine's thread asks the main thread for the piece (`file.slice().arrayBuffer()`) and
  waits on a futex. Chosen by the start-up check; `discread=page` forces it.
- **Sound**: the context is asked to run inside the click or key press itself (Safari
  wants that), with the system's sample rate if 44,100 Hz is refused; the button's
  tooltip and a notice say that sound waits for a click when it does; a **volume** slider
  (applied in the worklet, `web/rta-sound.js`); and the worklet now leaves out what piled
  up before it started - a sound that started after the game used to run a third of a
  second late for about a minute (343 ms queued; now 91).
- **Controllers** (not tried with a real one - nothing here can press a button): the pad
  in use is the one a button was pressed on last, not the first in the browser's list
  (a browser may list a keyboard's or a headset's control interface first); a pad
  without the "standard" layout is no longer ignored but used with the standard numbers
  as a guess, with a notice, and *Controls → Set up the controller* asks for every button
  in turn (buttons, axes - also triggers that rest at −1 - and a hat switch reported as
  one axis, as Chrome does for older pads on Windows and Linux); a trigger counts beyond
  30 % of its way, or when the browser only reports it as pressed; a pad that goes away
  is said.
- **Keys**: every key can be changed in *Controls* by clicking and pressing; the table
  shows what is printed on the player's own keys where the browser tells (Chromium's
  keyboard map), so a French keyboard shows Z Q S D where the keys are; keys stuck
  "down" after a command-key combination on a Mac are let go.
- **Touch**: an on-screen pad (left stick, direction pad, four buttons, L1 L2 R1 R2,
  Start, Select; pointer events with capture), shown at the first touch, or always or
  never (*Settings*). Tried with touch events from DevTools only.
- **Pause**: a hidden page pauses an offline game at once (machine and sound), shows
  "Paused" over the picture and goes on at a click, a key or a controller button - not by
  itself, and the press that ends the pause is not passed to the game. An online game is
  never paused; see "A hidden tab and online play" below.
- **Full screen** takes the picture with what lies over it (pause, notices, on-screen
  pad), also by a double click; `webkitRequestFullscreen` for older Safari; a refusal is
  said. The canvas is now sized for the screen, not for the window the page happened to
  have at start (896 lines on any screen that has them), so full screen is sharp.
- **Memory card**: one tab at a time (Web Locks: a second tab says so, waits, and goes
  on by itself when the first is closed, or plays without keeping saved games if the
  player says so); written within half a second of a change; a failed write (storage
  full) is said and stays said until it works again; never written when it could not be
  read at start (an empty card would replace what is there); the browser is asked to keep
  the storage for good (not in Firefox, which would put a question to the player).
- **Saved games as a file** (*Settings*): a zip of the card's folders as Play! and the
  desktop application keep them (`vfs/mc0/…`, `vfs/mc1/…`), written by the page (stored,
  no library); loading takes such a zip at any folder depth, compressed or not, so a zip
  made of the application's own folder works. In the Mac application the two folders
  belong into `~/Library/Application Support/Play-RTA/player1/vfs`. The saved online
  login is not in the file (it is a password).
- **Notices**: one line over the lower edge of the picture for what the page has to tell
  while the game runs; after the start: sound waits for a click, a controller needs a
  button pressed, where the keys are.
- `serve.py` is unchanged. `build.sh` is unchanged; **a build from an empty directory by
  it was run for the first time** (422 steps, 7 min 26 s at load 200+) and gave a
  working page.

### Windows, Linux and other devices: read, not run

What the code does that depends on the system, and what was done about it:

| Matter | By reading | Needs a real machine |
|---|---|---|
| keys | `KeyboardEvent.code` everywhere: positions, not letters; AltGr (reported as Ctrl+Alt on Windows) and Windows-key combinations are ignored as modifiers; Backspace and Enter are prevented from doing anything else | a keyboard without the keys used (a compact one without arrow keys: change them in *Controls*) |
| controllers in Chrome and Edge | Xbox, DualShock 4, DualSense and Switch Pro pads are given the standard layout on Windows, macOS and Linux; the touchpad button (17) is Select | every one of them once: which button is which, the triggers, Bluetooth |
| controllers in Firefox | standard layout for XInput pads on Windows and for the pads it has tables for; others come without a layout, with triggers and the direction pad as axes: guessed, noticed and set by *Set up the controller* | the wizard with such a pad |
| controllers in Safari | pads the system's game controller support knows come with the standard layout | once |
| frame pacing | the machine's thread sleeps to the next sixtieth by `Atomics.wait`; **on Windows a browser's waits are only as fine as the process's timer (15.6 ms unless raised), and Chrome does not raise it on battery power**. The page keeps an 8 ms timer running, which raises it otherwise | a Windows laptop on battery: whether the game holds 60 and the sound stays whole. If not: wait by spinning for the last milliseconds, or pace by the display |
| graphics | WebGL 2 through ANGLE on Direct3D 11 (Chrome, Edge, Firefox on Windows), on Metal here, native GL on Linux: the same calls, other drivers. The 11,700 calls a frame cost what the browser's GPU process makes of them | speed on an integrated Intel or AMD chip; a software renderer is named by the start-up check |
| high-resolution displays | the canvas has min(896, the screen's lines × the pixel ratio, at most 2) lines whatever the scaling (125 %, 150 %) and is scaled by CSS | a 4K display at 150 % |
| the file | the file dialog and the handle are the same interface on Windows; a file on a network share or a removable drive that goes away is the "disc image can no longer be read" path | antivirus that scans every read; a OneDrive placeholder file that is not on the computer |
| pointer lock | not used (no mouse in the game) | — |
| memory | 1 GiB of shared memory in one piece: any 64-bit desktop browser; a 32-bit browser or a phone refuses and is told why | — |
| phones and tablets | the page lays out narrow, has an on-screen pad, and says at start that it is made for a computer. Safari on iPhone and iPad has no File System Access and usually **copies** a picked 4 GB file before a page may read it; iPhone has no full screen for a page; the emulator needs 1 GiB and three busy threads | an iPad with an M-series chip is the only candidate; nothing was run |

**Are touch controls worth having?** A simple pad was cheap and is there. It is worth
little: this is a two-stick action game on a machine that already needs a fast desktop
processor, and on the one kind of touch device that might run it (a recent iPad, a
Windows tablet) a controller is the sensible way to play. It makes the menus and a first
look possible; it has no right stick (the camera) and was not held by a hand.

### First use: what a friend sees

1. The link. "Checking your browser…" for a moment, then a bar: "Loading the emulator…
   0.4 MB … 2.3 MB", "Reading the saved games…", "Starting the emulator…".
2. "Ready. Choose your disc image to start." with one button, a sentence saying what
   file is wanted and that it stays on the computer, notes if this browser lacks
   something, and three hints: sound starts with the first click, a controller is in use
   once a button is pressed on it, saved games stay in this browser.
3. The file dialog (or the file dropped on the page). A wrong file is refused in a
   sentence that says what it is. A right one: "Checking the disc image…", then the game.
4. A notice for a quarter of a minute: where the keys are, press a button on the
   controller. *Controls* lists every key and button and changes them; *Settings* has
   volume, the on-screen pad, saved games as a file, the remembered image.
5. The next visit, in Chrome and Edge: "Continue with <file name>" - one click, and the
   browser asks whether the page may read the file again. In Brave, Safari and Firefox:
   the file dialog again (a note on the start screen says so beforehand).

**Start time** (Chrome 155, a server on the same Mac that answers as the deployment
does - `local/play-web-compat/serve-deploy.py` - so without the line's delay; load 395):

| | checked | emulator in | "Ready" | over the line |
|---|---|---|---|---|
| cold (a new browser profile) | 1.1 s | 1.2 s | **1.5 s** | 807 KB: `Play.wasm` 729 KB (2.41 MB unpacked), `Play.js` 41 KB, `rta-web.js` 33 KB, the page 10 KB, the patch file 11 KB |
| warm (the page opened again), twice | 0.04 s | 0.07 s | **0.37 – 0.40 s** | 1 KB: three "not modified" answers; the build's three files are not asked for at all |
| warm, with the test's disc address | | | 0.40 s | first picture 0.52 s after the address was opened |

On a real line the cold start adds the 807 KB: under a second at 10 Mbit/s, three to
four seconds at 2 Mbit/s. **The deployment's cache headers are right as they are**
(`local/friend-download/web-setup.sh`: the build's directory, named by its content,
"immutable" for a year; everything else "no-cache", which a browser answers with a
conditional request; `gzip_static` for the three large files): nothing to change in
`web-update.sh`. Two things for whoever deploys to look at: the script's own check line
must show `content-type: application/wasm` for `Play.wasm` (with another type the page
still starts - it reads the file whole and says so in its log - but the browser neither
compiles while loading nor keeps the compiled code); and no file was added to the page,
so the script's list of files is still complete.

**Memory** (Chrome 155, a profile of its own, the game standing in the first level at
factor 2, window visible throughout - the page counted 0 s hidden; the tab's renderer
process by `ps` and `vmmap`, the latter's "physical footprint" being what Activity
Monitor shows as Memory; load 220 – 510):

| Minute in the level | tab's process, footprint | resident | GPU process, resident |
|---|---|---|---|
| 0 (just arrived) | 832 MB | 651 MB | 203 MB |
| 5 | 838 MB | 486 MB | 188 MB |
| 10 | 852 MB | 483 MB | 178 MB |
| 15 | 856 MB | 470 MB | 176 MB |
| **20** | **865 MB** | 495 MB | 175 MB |

So after 20 minutes in a level the tab holds about **865 MB**, of which the emulator's
own fixed memory is the larger part, plus 175 MB in the browser's GPU process; 33 MB
more than on arriving (1.6 MB a minute), with 110 more blocks translated. In that run the
test asked the browser once a minute for its own count of the page's memory
(`performance.measureUserAgentSpecificMemory()`, which is useless here: it counts the
emulator's 1 GiB of shared memory once for each of its five threads, 5,127 MB) - and
asking makes the browser collect garbage first.

MEMORY-RUNS

### A hidden tab and online play

A browser runs a page that is not in front at low priority and with late timers (7 – 45
frames a second were measured here earlier; Safari's engine throttles a hidden page's
timers harder still). Offline the page now pauses. Online it must not - every machine in
a lockstep game waits for every other, a paused one stops them all - and it cannot make
the browser run it properly either. ("Online" for this: the page is pressing its way
online, another player's copy is heard, or the game's machine has used its network in
the last twenty seconds, which covers the lobby; read from the state the online code
already keeps, not tried with a relay here.) So it tells the player three times: **when going
online starts** (a notice: keep this page in front, its window uncovered and the computer
awake until you are done), **while it is hidden** (the tab's title becomes "⚠ Come back:
the others are waiting") and **afterwards** (how many seconds it was hidden, and what
that did). What would be better and is not built: the relay telling the other players
whose page is hidden, so that the room can say "waiting for <name>"; and the online
panel itself saying it before *Host* and *Join* are pressed (that panel is the other
session's; the sentence is in the README).

### What needs a person, or a machine that is not here

- A controller in a browser, each kind once (Xbox, DualSense, Switch Pro), and one pad
  without a standard layout through *Set up the controller*.
- Safari itself: the file dialog with a 4 GB file, sound after the first click, full
  screen, a hidden tab, how long a level takes to load on a quiet Mac.
- Firefox: everything (not installed).
- Windows: Chrome and Edge once through - speed on Direct3D, frame pacing on battery,
  a DualSense and an Xbox pad, the file dialog, "Continue with …".
- "Continue with …": the browser's own question after the click (Chrome, on this Mac).
- Full screen (refused in the unattended test window).
- The on-screen pad on a real touch screen.
- A game saved by playing, exported, and loaded in the Mac application (the zip's layout
  was checked against the application's folders and with other zip tools, not by loading
  a real saved game there).

### Test helpers of this work (not in the repository)

`local/play-web-compat/`: `build.sh` (my own tree, build and site: `src`, `build`,
`site`), `t.py` and `drive.py` (a Chrome or Brave of the test's own under `profiles/`,
driven through DevTools: key, touch, mouse and drag events, a file given to a file
chooser, a file dropped), `wk/wk.swift` (the WebKit window), `wkjs.sh`, `quota.py`
(storage full), `serve-deploy.py` (the page laid out and answered as the deployment
does), `time.py` (cold and warm start), `mem.py` (memory over time); output in `out/`.

## Online play from a browser: built (2026-10-12)

Built from the design in the next section; where it differs is said here.

### What there is

- **The relay** (`tools/play-web/relay/relay.py`, Python 3, standard library only, about
  550 lines; `relay/README.md` has the options and limits). One WebSocket connection per
  page. Per session: TCP connections to the configured lobby server's configured ports
  and to nothing else; one UDP socket per socket of the console's network, used for the
  lobby server's discovery port and for datagrams to **other sessions of the same
  relay**, which are handed over inside the program. Different from the design: a
  datagram for any other address is refused and nothing arriving from outside on those
  sockets is passed to a page - so a desktop player could not be reached at all. (That
  was the relay of the morning; "Mixed games" below has what it does now.) Limits: sessions (64),
  sessions per address (4), message size, message and byte rate, a silent page (60 s),
  an idle session (15 min). WebSocket only: **WebTransport was not built**.
- **The sockets** (`src/RtaWebNet.cpp`, `RtaWebSock.h`, `RtaWebNetCore.cpp`):
  `tools/play-net/src/RtaNet.cpp` is compiled without a change; its `socket`, `bind`,
  `connect`, `send`, `recv`, `sendto`, `recvfrom`, `close`, `shutdown`, `poll`,
  `getsockopt`, `setsockopt`, `getsockname`, `fcntl` are renamed by the preprocessor and
  carried out as messages (a connect answers "in progress" and `poll` says when the relay
  has it; a UDP socket is a socket at the relay). The machine's thread never returns to
  the browser's event loop, so the WebSocket belongs to the page's main thread: the
  machine's thread queues a message and wakes the main thread (`emscripten_proxy_async`,
  one wake-up for whatever is queued), the main thread sends; what arrives is put into
  per-socket queues that the machine's thread reads at its next poll (about every
  millisecond of the machine's time, as on the desktop).
- **The adaptor and the card**: the Ethernet chip's two hooks as in `Rta.cpp`; the
  network is made when the relay has said where the lobby server is (its first message
  names the lobby server's address and its own). The network setting the game looks for
  on the memory card is written at start (`WriteNetcnf`, copied from `Rta.cpp`).
- **One-step online and games by code**: `tools/play-net/src/RtaOnline.cpp` compiled in
  without a change and called at every vertical blank; while it drives, the game sees
  its buttons only. The saved login and the remembered character are files beside the
  memory card, so they are kept in the browser's storage with it. The page
  (`web/rta-web.js`): the *Online…* panel (Host a game, Join a game with a code, Just go
  to the lobby, the name asked once, Stop, Forget online login), a strip that shows the
  driver's note, the connection to the relay with a ping every 15 s, a warning when
  another player's patch set differs (the figure is made as the desktop application
  makes it and exchanged the same way).
- **What a page needs to offer it**: `online.json` beside the page (the relay's address,
  the name of the sign-in patch file) and that patch file (not in the repository). The
  sign-in patch's words are not part of the patch-set figure, as on the desktop.
- **The build**: `build.sh` copies `RtaNet.cpp/.h` and `RtaOnline.cpp/.h` from
  `tools/play-net/src` into the Play! tree beside our sources; `play-web.patch` names
  three more source files in `Source/ui_js/CMakeLists.txt` (its only change). The two
  desktop sources are taken as they are at the time of the build: whatever is changed in
  them has to compile for the browser as well (`__EMSCRIPTEN__` is defined there).

### Tried on one Mac

The lobby server on the Mac; the relay on the same Mac (`--lobby` the Mac's network
address, listening on 127.0.0.1:8975); `serve.py --disc`; two Google Chromes with their
own profiles and DevTools ports, windows side by side, pages titled "AGENT TEST - online
A / B", driven by `local/play-web-out/online-pair.py`; player names made by the test.
Nothing was typed into the panel by a person: the test called the same functions the
buttons call (`rta.online.start`, `rta.online.name`), and in one run sent clicks to the
buttons themselves.

| What | Result |
|---|---|
| first start of a page that has no login: *Just go to the lobby*, name given when asked | account made in the game's own form, lobby's game list reached about 25 s after the start (load about 100) |
| *Host a game* from the lobby | code made, the game's character screens came up and were the player's (first time on the server): the test pressed through them; then the room, with the code in the strip |
| a second page, no login: *Join a game* with that code from power-on | account, lobby, the game found in the list and joined, character screens (the test pressed through them), the room |
| the host's ✕ *Start Game* | both pages in the first level, two players, about 14 s later |
| in step? first run (load 130 – 155, both characters made to walk) | 974 consecutive lockstep frames (497 – 1470) for which both pages still held their own sync hash: 974 equal, 0 different, 656 distinct values; each page had also received the other's hashes for about 490 of its frames: all equal to its own; seed, positions and hit points the same raw bits when both were read at the same frame; the game's checksum-failure flag 0 and no player out of sync or dropped, on both |
| the same from two fresh page loads, **no press at all** (saved login, remembered character), load 41 | host in its room 39 s after *Host a game* at power-on; joiner in the room 43 s after *Join*; first level 14 s after *Start Game*; 1,387 consecutive frames (642 – 2028), all hashes equal, 1,122 distinct values; each page held the other's hashes for about 700 frames, all equal; flags as above |
| the same once more with the build made after `RtaNet.cpp` learnt to tell the other players which arithmetic a copy computes with (load 52) | host in its room after 38 s, joiner after 43 s, first level 14 s after *Start Game*; 1,451 consecutive frames (650 – 2100), all hashes equal, 1,190 distinct values; each page's log: "this copy computes with browser arithmetic" told, and the same heard from the other |
| the panel itself, on a page with no login, by clicks sent to its buttons and text put into its box: *Just go to the lobby* | the name box opened by itself with the focus in it; "x" refused with the reason ("at least 3 characters"); a good name taken, the box closed, the buttons greyed and *Stop going online* shown; the strip followed every stage; lobby 31 s after the click at power-on (load about 150); *Forget online login (name)* removed the saved login |
| the relay's own test (`check.py --selftest`, 18 checks) | passes on the Mac and on the project's server inside the service's sandbox |
| the files as laid out for a server (the build in a directory named by its content, the rest beside the page) | boots and connects, served by `serve.py` from that directory |

"In step" was read from the game itself: each machine keeps a ring of its own per-frame
sync hash (`g_peers[local] + 0x18ac`, 256 entries of frame, counter, hash; the hash is
made of the shared seed and every player's position: `docs/netcode.md`), and the ring of
each other player's hashes as received. `pair-check.py` reads both pages' rings every
second and a half and compares them by frame number.

Frame rates while two pages ran on the one Mac: 46 – 61 a second at load 41; 15 – 28
while both were still translating the level's code at load 130 – 155.

### The relay path, measured

| What | Where | Figure |
|---|---|---|
| one message to the relay and its answer (`check.py`) | the Mac, load 105 | median 0.27 ms, 95th 0.41 ms |
| a datagram from one session to another and one back (`check.py`) | the Mac, load 105 | median 0.33 ms, 95th 0.42 ms |
| the same two | the project's server (load 0.1), inside the service's sandbox | 0.51 ms / 0.34 ms median |
| a message from a page to the relay and its answer, timed in the page while the game ran (so with the main thread's own delay) | the Mac, two pages in a game, load 130 – 135 | median 2.3 ms, 95th 13 – 16 ms, worst 17 – 19 ms (100 each from both pages) |
| the game's own figure for the other player's lead (newest input frame minus simulation frame) | the two pages | 9 and 7 frames at load 41; 13 and 9 at load 130 |

The relay and the page add about a millisecond to a datagram on a quiet computer. What a
browser player really pays is the **detour**: every datagram goes player → server →
player instead of player → player. From the test Mac a TCP connection to the project's
server takes 58 ms (median of 9): two players both that far from it would see each other
at about 58 ms one way, whatever the distance between them. Not measured with two real
players.

### What a lost connection does

When the computer sleeps or its screen is switched off, Chrome closes every connection a
page has. Seen on the test Mac three times within four minutes: its lid was closed, the
power log (`pmset -g log`) says "Entering DarkWake state due to 'Clamshell Sleep'" at the
very seconds at which both pages' connections to the relay (and the test's own DevTools
connections) ended. The relay closes a session's sockets with it: the lobby connection
is gone and the game shows its own error; the page connects again by itself as soon as
the game uses its network (seen: 6 – 9 s later). An online game does not survive it. The
page now asks the browser to keep the screen on while the game runs (a controller does
not count as activity); against a closed lid nothing helps.

### Putting it on a server: prepared, not done

Two local scripts (they hold nothing private themselves and take the server and the
private path from the user's own files; not in the repository):

- `web-setup.sh`, once: installs certbot (apt), opens 443/tcp in the firewall, registers
  with Let's Encrypt and gets a certificate for a host name that needs no DNS of ours,
  writes an nginx site of its own (port 80 only for that name's certificate check; port
  443 for the page under the private path with the cross-origin isolation headers,
  gzip, a long cache life for the build's directory, the relay's WebSocket handed on,
  404 for everything else, uploads over 64 KiB refused) and the relay as a systemd
  service (a dynamic user, a read-only system, the network limited to the server's own
  addresses). It does not touch the lobby server, the existing download, or anything else
  on that host. **It was not run**: opening a firewall port and registering with a
  certificate authority are the server owner's own to do.
- `web-update.sh`: lays the files out, uploads them beside the place and swaps them in,
  replaces the relay when it has changed, adds a link to the existing download page, and
  checks what a browser gets (page, headers, the build's files, 404s, an upload being
  refused, the relay through `check.py` without logging in, the existing download as
  before).

Tried on the server without changing anything (`web-setup.sh --check`: a directory in
`/run`, removed again): nginx accepts the generated site file; the relay's self-test
passes 18 of 18 inside the service's sandbox.

### Not tried, not built

- The relay on a public server; two players in different places; more than two players;
  a level beyond the first; a long session.
- WebTransport: the game's datagrams travel on the WebSocket connection, in order: one
  lost packet holds back those behind it for a retransmission time.
- A session that survives a lost connection (above).
- The panel used by a hand (below "Tried": it was gone through by clicks sent to its own
  buttons); a name that is taken on the server (the driver asks again and the page shows
  the box again: the path exists, it was not run); *Stop going online* pressed.
- A page that is not in front: a browser runs it slowly, and in a lockstep game that
  holds up everybody.
- (Was: the lobby keeping browser and desktop players apart. They play together now:
  "Mixed games" below.)
- The relay's limits under real load.

## Mixed games: a page and the application in one game (2026-10-12)

**State: a page and one copy of the application play one game, in step, in both orders,
across a level change. Built into the relay and the page; the application needs no new
build. Tried on one Mac only (local lobby server, local relay). Games of three do not
start for the third machine on that Mac - with the bridge or without it (below). The
relay and the page have to be put on the server; that is the owner's to do.**

The arithmetic side is [mixed-arithmetic.md](mixed-arithmetic.md): the application
changes to "browser arithmetic" by itself while a browser copy is in its room. This
section is the network side and the proof with real copies.

### Why an application player never reached a page

Read in the relay as it was, and then seen:

1. A datagram a page asked to send to anything but the lobby's discovery port or another
   session's socket was refused (the relay said so in a notice).
2. The relay never read its UDP sockets (a 4 KiB buffer and no reader): whatever an
   application player sent there was thrown away by the system.
3. As set up for a server, the service may only talk to the server's own addresses
   (`IPAddressDeny=any`), and the firewall has no UDP port open for it.

Nothing else was in the way. The lobby server already hands a page's relay socket to the
other players as that player's address, the game's hole punching needs nothing new, and
the application sends to that address as to any player's.

### What was built

- **The relay** (`tools/play-web/relay/relay.py`; `README.md` beside it has the options).
  Its UDP sockets are read. A datagram passes between a session's socket and an outside
  address and port only when that pair is *open* for the session, and a pair is opened in
  two ways only:
  - *named*: the lobby server named the address to this page. The relay reads the lobby
    connection as it passes, server to page only, and takes the address the server
    **observed** for the host of a listed game (reply 0x55), of a game found by name
    (reply 0x57) and of a player who wants in (notification 0x65); the layouts are in
    `docs/lobby-protocol.md`. The "own-network" address in the same messages is what a
    player claims and is not taken, and nothing a player can type (chat, a game's name)
    is read as an address. A datagram from the named address with another port than the
    named one opens that port too (a router changes ports; the game accepts by address);
  - *both*: the page has asked to send to the address **and** a datagram from that
    address has arrived on the session's socket, in either order, within 30 s. This is
    for the third player of a game, whom the host introduces player to player and the
    lobby server names to nobody.

  What a page sends to an address that is not open is not sent; what arrives from an
  address that is not open is not shown to a page. So neither a page nor a stranger can
  make the relay send or pass anything alone. Addresses that are not public are left out
  unless `--lan` is given (a test on one computer, a relay on a home network); addresses
  no player can have (loop-back, multicast) are refused with a notice. At most 16 open
  pairs a session, 150 datagrams a second to one of them (the game sent about 10 to 30),
  the session's own message and byte rates on top and the same rates for what arrives;
  a pair that hears nothing for two minutes is closed. `--udp-ports LOW-HIGH` puts the
  sockets in a range a firewall can open; `--pages-only` is the relay as it was.
  `check.py --selftest` goes through all of it with stand-in players (30 checks).
- **The page** (`web/rta-web.js`, `web/index.html`, `src/RtaWebNet.cpp`): a line under
  the driver's strip, made from `CNet::Peers()` by the application's own two rules
  (`CheckPatchSets`, `CheckArithmetic`): green "Everyone computes the same way: N other
  players heard, the same patch set (…), browser arithmetic (… in the Mac application)";
  grey while a copy has not said yet; a red warning for a different patch set, and one
  for a copy that cannot compute as a browser does ("an older copy of the application,
  or one set to its own arithmetic … do not start it"). The texts that said browser
  players only play with browser players are gone.
- **For a copy that cannot follow and has no warning for it** (`tools/play-net/src/
  RtaNet.cpp`, inside `#ifdef __EMSCRIPTEN__`: the application's own behaviour is not
  changed, and the file still compiles for it): an application copy from before the
  arithmetic message tells its patch set and nothing else. If that set is the page's own,
  such a copy would show nothing while the game is about to fall out of step. Six seconds
  after it was first heard the browser copy tells it the patch-set figure `0b50137e`
  ("obsolete") in place of its own, so that the old copy shows the one warning it has -
  another player's patch set differs, do not start, everyone needs the same build.

### Tried (one Mac; lobby server, relay with `--lan`, page server, Chrome and the application all on it)

The application copy in the first six rows is the working build as released
(11:14 that day, patch set 3f5b1e14), started with `--rta-test`, nothing given about
arithmetic. Load average 190 to 500 throughout (other work on the Mac): the times are
slow because of it. "In step" is read as in "Tried on one Mac" above: every machine's
ring of its own per-frame sync hashes and the rings of the others' hashes it received,
compared by frame (`local/mixed-online/sync.py`), for the application through its
control socket.

| What | Result |
|---|---|
| the application hosts by code, the page joins by that code | relay: "path to the player at …:4001 opened (the lobby server named it)"; the application's log: the page "computes with browser arithmetic (can do: the browser's)", then `arith=browser` for itself; the page's line: "Everyone computes the same way: 1 other player heard, the same patch set (3f5b1e14), browser arithmetic (in the Mac application)" |
| the application's ✕ *Start Game* | both in the first level, 2 players, 14 s later |
| in step, first level, both players walking and swinging | 2,315 consecutive lockstep frames (38 – 2352): every hash the same on both, 1,959 distinct values; each side held the other's hashes for about 1,200 of its frames: all equal; checksum-failure, out-of-sync and dropped flags 0 on both; hit points `42033333` on both (the value to nearest) |
| a level change by the game itself: the host's player walked to the hub's character, spoke with her, walked to the gateway and accepted the first mission in the mission menu | both machines in the next level at the same lockstep frame (27,377 – 27,392), 8 s later; 487 frames compared just before it: all equal |
| in step in that level, walking and fighting | 3,929 consecutive frames (27,542 – 31,470): all equal, 1,565 distinct values; monsters hit both players (hit points fell) and killed both; flags 0 on both at frame 31,486 |
| the page hosts by code, the application joins by that code, no press at all (remembered logins and characters) | page in its room after 52 s, application after 38 s; it changed arithmetic in the room ("the machine now computes as a browser copy's does"); the same green line; first level 17 s after the page's *Start Game*; 2,663 consecutive frames (2 – 2664) all equal, 2,258 distinct values, flags 0 |
| the same once more with the page's last build and the application as another job had rebuilt it at 14:37 | first level after 17 s; 786 frames (2 – 787) all equal |
| relay counts of the first game (29 minutes) | 16,941 datagrams to the application, 18,221 back, none dropped, none refused: about 10 a second each way |
| an application copy started with `--rta-arith native` joins the page's room | page, within 3 s: the red arithmetic warning; application's status bar and log: "WARNING: another player's copy cannot compute with Play!'s own arithmetic as this game does - the game would fall out of step: do not start it" |
| a packaged copy from before the arithmetic message (it tells its patch set, df6a6139) joins the page's room | page: both red warnings (different patch set; cannot compute as a browser does); the old copy: "WARNING: another player has a DIFFERENT PATCH SET (0b50137e; yours df6a6139) … do not start it" - it had warned of the page's real figure first, then of this one. After this run the figure is sent only to a copy whose own set is the page's (one that would otherwise show nothing); no such old copy exists to try it on |

**Three players: into one room, yes; into the game, no - and not because of the
bridge.** Three machines (application host, page, second application; and page host
with two applications) came into one room, every copy heard the other two ("2 other
players heard … all in the Mac application"), and the relay opened the page's path to
the application that was not the host ("the lobby server named its address, with another
port; and each has sent to the other" - on one computer all players have one address, so
both rules held). At *Start Game* two machines went into the first level, with three
players counted, and stayed in step with each other (1,710 and 1,822 frames of received
hashes, all equal); the third stayed behind with the game's own launch error that some
players cannot be reached, and was dropped. That happened in 3 of 3 tries with a page in
the game - and with **three application copies and no page and no relay** one try ended
the same way and another with the host back at the game list and nobody in the level,
so it is not the relay's doing. The one try of six that worked was three application
copies without the patch sections; a try with a page and without the sections failed
too. Three players had never been tried in this project. Not found out: whether it is
the load on the Mac that day, something in a game of three through the lobby server, or
- the first suspicion - that every player of a one-computer test has the same address:
the game takes an arriving connection for the first player it is looking for at that
address, whatever the port (`docs/lobby-protocol.md` 9.3). If it is the last, it also
concerns real games: all browser players have the relay's address.

Not tried: two computers; a relay on a public address with players behind routers (the
paths, the firewall range, a router that changes ports); a page in Safari or Firefox; a
person playing. On the test Mac's sleep dips: none were seen in these runs (its sleep was
switched off that afternoon).

### What has to go to the server

- **The relay**: the new `relay.py`, and its service changed - the line that limits the
  service to the server's own addresses has to go (it must reach the players), and
  `--udp-ports LOW-HIGH` added; the firewall opened for that UDP range from anywhere.
  `relay/README.md` has both. Without the firewall range a game of two still works where
  the lobby server named the player (the relay sends first), but a third player and a
  player behind a router that changes ports are not reached.
- **The page**: the new build (`Play.js`, `Play.wasm`) and `index.html`, `rta-web.js`.
  An old page works with the new relay and plays mixed games, but shows no arithmetic
  line; a new page with the old relay is as before (browser players only).
- **The application: nothing.** The released build did everything above as it is.

Test files (not in the repository): `local/mixed-online/` - `up.sh`, `down.sh`, `app.sh`,
`mx.py` (a page through DevTools, an application copy through its control socket),
`scen.py` (the runs above), `sync.py`, `walk.py` (walks a player to a place by reading
its position), `relay.log`.

## Online play from a browser: the design it was built from

### What the game's machine does on its network

As `tools/play-net/src/RtaNet.cpp` carries it today for the desktop application: the
emulated machine is alone on a made-up network with our code as its gateway; ARP, DHCP,
ping and DNS are answered locally; TCP and UDP are carried on host sockets.

| Traffic of the emulated machine | Desktop application | Destination |
|---|---|---|
| DNS query for `con.soegames.net` | answered locally with the lobby server's address; every other name "does not exist" | — |
| TCP connection 1: the gateway ("where is the lobby?") | one host TCP connection | the lobby server, port 40810 (the application accepts 40800–40817) |
| TCP connection 2: the lobby itself (log-in, account, game list, rooms, the hole-punching hand-out) | one host TCP connection | the address and port the gateway's reply names (our server: the same host, port 40910) |
| UDP from the machine's ports 4000–4004: the lobby's discovery port | **one host UDP socket per source port, used for every destination** (a "full cone": the server and every other player see one address and port for it) | the lobby server, UDP 10101 — it learns the socket's outside address there and hands it to the other players |
| UDP from the same ports: the game itself (input, sync records, game messages; unreliable datagrams, up to 60 a second per peer) | the same sockets | **the other players directly**, console to console, at the addresses the lobby handed out |

The machine only ever opens connections; it never listens for TCP.

### What a page cannot do, and what stands in for it

A page has no raw TCP or UDP. It has WebSocket (a TCP connection to a server that speaks
WebSocket; reliable, ordered), WebTransport (HTTP/3: reliable streams **and unreliable
datagrams** to a server; Chrome, Edge and Firefox have it, Safari only recently) and
WebRTC data channels (unreliable datagrams to a peer that speaks WebRTC; peer to peer
between browsers, but a desktop player's game does not speak it). So the browser build
needs a **relay** on a real host that owns the sockets.

### The relay the server could run

One session per browser player, opened by the page when the game's machine first uses
its Ethernet adaptor. Framing: small typed messages (a byte of type, a connection or port
number, a length, the bytes).

1. **Transport**: WebTransport where the browser has it — one reliable stream for the two
   TCP connections and the relay's control messages, datagrams for the game's UDP — and
   WebSocket as the fall-back for everything. Over WebSocket the game's UDP inherits
   TCP's head-of-line blocking: one lost packet holds back everything behind it for a
   retransmission time, which lockstep play shows as a stall. It will work on a good
   line and is the first thing to build; WebTransport datagrams are the proper carrier.
   Either needs TLS and a certificate (a page served over https may only open `wss://`
   or `https://`), i.e. a host name for the server.
2. **TCP** ("open n to address:port", "data n", "close n", both ways): for each connection
   the machine opens, the relay opens a TCP connection. Allowed destinations: the lobby
   server's gateway port and the lobby port its reply names — nothing else (the relay
   must not be an open proxy). Two connections per player at most.
3. **UDP** ("from port s to address:port: bytes", and the reverse with the sender's
   address): per session **one UDP socket on the relay for each source port the machine
   uses** (4000–4004), kept for the session and used for every destination, exactly the
   desktop application's rule. To the lobby and to every other player a browser player
   is then simply a player at the relay's address with those ports, and the game's own
   hole punching works unchanged: desktop players send to the relay's socket, the relay
   forwards to the page. A relay on a public address needs no punching at all (it is
   reachable), which also makes browser players the easy case for desktop players
   behind awkward routers. Allowed destinations: the lobby's UDP 10101 and addresses the
   lobby has named to this session (the relay can read them out of the lobby connection
   it carries, or simply refuse private, loop-back and its own addresses).
4. **Where the user-space network lives**: keep `RtaNet.cpp` whole and compile it into the
   browser build, replacing its `socket`, `connect`, `send`, `recv`, `sendto`, `recvfrom`
   by the relay messages (about 300 lines of it touch sockets). The relay then is a dumb
   forwarder with an allow-list, a few hundred lines in any language, and holds no TCP
   state of the players. (The alternative — ship raw Ethernet frames and run `RtaNet.cpp`
   on the server — puts every player's user-space TCP on the server and gains nothing.)
5. **Where it runs and what it costs**: beside the lobby server (same host name: the
   lobby's rule is that gateway, lobby and discovery are reachable at one address). Per
   browser player: two TCP connections, up to five UDP sockets, and the game's traffic
   (a few kilobytes a second per peer) through the server both ways. Every packet of a
   browser player takes the detour through the relay: the added delay is the round trip
   between that player and the server instead of between the two players.
6. The memory card's network setting (`WriteNetcnf` in `Rta.cpp`, four small files) and
   the one-step online driver (`RtaOnline.cpp`, stand-alone C++) carry over as they are;
   the Ethernet chip's fixes are already in the build (`play-net.patch`, `Iop_Speed.cpp`).

(Written before anything was built. What was built from it, and where it differs, is in
the section before this one.)

### Can a browser player and a desktop player share a game? Measured: not as the builds are

The game is deterministic lockstep: every machine must compute the same bits
(`docs/issues/float-divergence.md`). The console rounds floating-point results toward
zero; the desktop application sets the host processor to do the same
(`fesetround(FE_TOWARDZERO)` on the machine's thread). WebAssembly has no rounding
control: it always rounds to nearest. It also has no "flush tiny results to zero" mode,
which the desktop application sets as well.

**Measurement** (2026-10-11; `local/play-web-out/native-trace.py`, the page's
`auto=trace`): the stable desktop build and the browser build (Chrome 155), same disc,
same patch set, fresh memory card, the same button sequence into the first level; then
the left stick held fully right and the player's position (three floats in the player's
object, `g_players[0]` +0x43d8, +0x10) read as raw bits at every frame.

- While the character walks down the first steps its height is smoothed over a few
  frames through the values −48.15, −48.45, −48.9, −49.5, −50. The desktop build holds
  them as `C2409999`, `C241CCCC`, `C2439998`, `C245FFFE`, `C2480000` (two runs, the same
  bits both times); the browser build as `C240999A`, `C241CCCD`, `C243999A`, `C2460000`,
  `C2480000` (three runs: two in Chrome, one in the pane, the same bits every time).
  `C240999A` is −48.15 rounded to nearest, `C2409999` is it cut off toward zero; the
  later values are one and two places apart because the cut-off error adds up. The same
  computation, the same inputs, different last bits: the rounding difference, seen.
- The steady walking speed itself is the same bits in both builds (x grows by 0x1E231
  places a frame, y by 0x374BC, in both): not every operation is affected, only those
  whose exact result does not fit.
- The x and y of the walk could not be compared frame for frame: where the game stands
  the character on arrival, and which way it faces, depends on how many frames the menus
  took (three browser runs: three places; the desktop runs, whose test presses arrive
  with constant delay: one place), and the first frames of a walk are a turn. Putting the
  browser's character at the desktop run's place (`place=43152305,c2edbc5a`) did not make
  the first frames agree (first step 1.08, 2.32 against 0.67, 2.47: it faces another
  way), so the game's sync hash was not compared for identical ticks either.

What that means for a shared game is already measured in this project
(`docs/issues/live-rig.md` 8.3, `float-divergence.md`: two linked desktop machines, one
forced to round to nearest — which is what a browser machine is): the raw position
differs on the first tick anybody moves and the game's own out-of-sync check trips 7 to
113 ticks later (a tenth of a second to two seconds), in the first level, in every one
of the pairs with movement. **A browser player and a desktop player as the builds are
today would be out of sync within two seconds of the first step.**

Ways out, none built:

1. **Browser players only with browser players.** WebAssembly arithmetic is the same on
   every computer and browser (the specification leaves only the bit patterns of NaNs
   open), so browser-only games agree with each other — on any mix of Macs and PCs,
   which is more than can be said of native builds for different processors without
   testing. The relay above is all that is needed; the lobby would have to keep the two
   kinds of player apart (a version field, or separate servers).
2. **A "browser arithmetic" switch in the desktop application** for mixed games: round to
   nearest and no flushing of tiny results, on every machine of the game. Cheap to build
   (two processor flags not set). Before trusting it, a desktop machine and a browser
   machine have to be compared over long runs: the two translators do not necessarily
   emit the same operations for the same game code (a fused multiply-add on one side and
   a multiply and an add on the other give different last bits; so can the conversions
   to integers at the edges, and minimum/maximum of NaNs). The linked-pair rig of
   `docs/issues/live-rig.md` is the tool; it would need a browser machine as one side.
   Such games are no longer bit-identical to a real console's arithmetic, which matters
   only if consoles (or PCSX2 players) are ever to join.
3. **Rounding toward zero in the browser build**: the translator could compute each
   single-precision add, subtract, multiply, divide and square root in double precision
   and correct the result toward zero. Exact, and it keeps the desktop application as it
   is, but it makes every floating-point operation of game code several times as
   expensive (and the vector unit's four-wide operations have to be taken apart); with
   the machine thread at 10 of 16.7 ms per frame there is some room, not much.

