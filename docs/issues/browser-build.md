# Browser build (Play! compiled to WebAssembly) — working notes

Status: a first version runs (2026-10-12): built, measured, usable offline, and online
between browser players through a relay (built and tried on one Mac: two pages in one
game, in step; the relay is not on a public server yet). Not yet tried by a person. The
summary is the state; the rest is the record.

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
**Not there**: playing with desktop players (measured: the arithmetic differs in the last
bit, below), a session that survives a lost connection to the relay, pacing by the
display's refresh, anything beyond the first level, other browsers than Chrome.

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
- Safari and Firefox: untested (WebAssembly threads, OffscreenCanvas with WebGL 2 and
  synchronous range requests on `blob:` addresses in a worker are all needed).
- A build from an empty directory by `build.sh` (clone, both patches, full compile) was
  not run; the script was run on the existing tree, and the patches were checked to
  reproduce it.
- Online: the relay on the public server (prepared, see "Putting it on a server"); then
  two players in different places; more than two players; a level beyond the first.
- A session that survives a lost connection to the relay (the relay would keep a
  session's sockets for some seconds and both sides would send again what the other has
  not confirmed); WebTransport for the game's datagrams.
- Keeping browser and desktop players apart in the lobby (or making them compatible:
  `docs/issues/mixed-arithmetic.md`).

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
| the remembered image (File System Access handle) and the file dialog | — | **unchecked** (a dialog only a person can answer) |
| one page, one tab | `chrome-run.py` sends one tab from test to test and the page closes itself; or a Chrome of its own with its own profile, ended by the script | no window was left behind by those; the very first test's tab (opened before that existed) had to be left to the user |

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
  sockets is passed to a page - so a desktop player cannot be reached at all, which is
  what is wanted as long as the two kinds fall out of step. Limits: sessions (64),
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
- The lobby keeping browser and desktop players apart: a desktop player who joins a
  browser player's room by hand will not get into the game (the relay does not carry
  datagrams to or from outside).
- The relay's limits under real load.

## Mixed games: a page and the application in one game (2026-10-12, work in progress)

Working notes of the session that builds this; the finished account replaces them.

- **Why an application player never reached a page** (read in `relay.py` as it was): (1) a
  datagram a page asked to send to any address but the lobby's discovery port or another
  session's socket was refused; (2) the relay never read its UDP sockets (4 KiB buffer,
  no reader), so whatever an application player sent there was thrown away by the
  system; (3) as deployed, the service may only talk to the server's own addresses
  (`IPAddressDeny=any`) and the firewall has no UDP port open for it. The game, the lobby
  and the application need nothing: the lobby already hands a page's relay socket to the
  other players as that player's address.
- **Built in `relay.py`** (self-test `check.py --selftest`: 30 checks pass): the sockets
  are read; a datagram passes between a session's socket and an outside address and port
  only when that pair is *open*: the lobby server named it to this page (the relay reads
  the observed address out of replies 0x55 and 0x57 and notification 0x65 as they pass;
  the own-network address a player claims is not taken), or the page has asked to send
  there *and* that address has sent to the session's socket, within 30 s. Nothing else is
  sent and nothing else is passed on. Options: `--udp-ports LOW-HIGH` (for a firewall),
  `--lan` (private addresses and programs on the relay's own computer: tests),
  `--pages-only` (as before), `--peer-rate`.
- **Still to do** when this note was written: the page's warnings (patch set, arithmetic,
  "everyone computes the same way"), the build, then the proof with one application copy
  and one page (both orders), a level change, three players, an application copy that
  cannot change its arithmetic; the documents. Test files: `local/mixed-online/`.

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

