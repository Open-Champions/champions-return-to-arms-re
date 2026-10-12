# Browser build (Play! compiled to WebAssembly) — working notes

Status: IN PROGRESS (started 2026-10-11). Kept current while the work goes on; the
summary at the top is rewritten when figures change.

Question: does Champions: Return to Arms (SLUS-20973 v2.00) run at full speed in Chrome
on an Apple M5 Pro, at the title screen and standing in the first level, with the same
core changes as the native build (`tools/play-net/play-net.patch`) and the same patches?

## Summary

(being rewritten as figures come in; the table under "Measurements" is the record)

- It builds, boots the disc, applies the patch set and the display patches, reaches the
  title and the first level by scripted presses, and draws correctly (a picture of the
  page's canvas in the level was looked at: `local/play-out/web-hub.png`).
- Title screen: full speed (60.0 frames a second) in Chrome 155 and in the Browser pane.
- First level, standing: full speed (59.97 – 60.0) in Chrome 155 at resolution factors 1
  and 2 with the computer otherwise quiet (load 9 – 12): the machine thread needs 10 – 12
  ms of CPU per frame, the video thread 6 – 7 ms; 75 – 93 frames a second with the limiter
  off. With the computer busy with other test runs (load above 100) it drops to 30 – 50.
- Factor 4 in Chrome: see the measurements (41 – 49 frames a second in one run with a
  1749 × 1312 canvas; 60.0 in the pane with a 969 × 727 canvas) — being looked at.

## Where things are

| What | Where |
|---|---|
| sources of the web front end, build script, local test server | `tools/play-web/` |
| my copy of Play! (commit 83700b2c + `play-net.patch` + `play-web.patch`) | `local/play-web-src` (not in the repository) |
| pristine copies of every Play! file `play-web.patch` touches (as they are after `play-net.patch`) | `local/play-web-orig` |
| build directory | `local/play-web-build` |
| the page as served | `local/play-web-site` |

## Installed

`brew install emscripten` (6.0.12). Homebrew brought its dependencies with it: abseil,
simdutf, hdrhistogram_c, libffi, libnghttp2, libuv, llhttp, merve, simdjson, readline,
highway, python@3.14, openjdk, yuicompressor, and it upgraded node 26.5.0 to 26.11.1.
Nothing else was downloaded (no npm packages: the page is plain HTML and JavaScript, not
Play!'s React application under `js/play_browser`, which needs `npm install`).

## Log

- The tree: `local/play-playable` copied without `.git` to `local/play-web-src`, the 18
  files under `local/play-orig/Source` put back, `tools/play-net/play-net.patch` applied
  (no rejects).
- `emcmake cmake … -DBUILD_TESTS=OFF -DBUILD_PLAY=ON -DBUILD_PSFPLAYER=OFF -DUSE_QT=OFF`,
  `cmake --build . --target Play`: all 429 objects compile with the patch as it is (the
  Qt/macOS sources of `tools/play-net/src` are not part of this configuration). Only the
  link failed: Play!'s `-sUSE_ES6_IMPORT_META=0` is no longer accepted by Emscripten 6.

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

## Online play from a browser: what the network module would need (not built)

A page has no raw sockets: it can open WebSocket (TCP to a server that speaks
WebSocket), WebRTC data channels (UDP-like, to a peer that speaks WebRTC), and
WebTransport (to an HTTP/3 server). The game speaks plain TCP and UDP. So the emulated
Ethernet adaptor of the browser build needs a relay on a real host that owns the
sockets. What the game's machine does on its network, as `tools/play-net/src/RtaNet.cpp`
carries it today (one user-space network per emulator: ARP, DHCP, ping and DNS answered
locally, TCP and UDP carried on host sockets):

| Traffic of the emulated machine | Today (desktop) | Destination |
|---|---|---|
| DNS query for `con.soegames.net` | answered locally with the lobby server's address; every other name "does not exist" | — |
| TCP, connections the machine opens (it never listens) | one host TCP connection per connection | the lobby server: the gateway port 40810 (the application accepts 40800–40817), then the lobby port the gateway's reply names (40910 on our server) |
| UDP from the machine's ports 4000–4004 | **one host UDP socket per source port, used for every destination** (a "full cone": the server and every other player see the same address and port for it; the game's hole punching depends on that) | the lobby server's UDP 10101 (it learns the socket's outside address there) and **the other players' consoles directly** (console to console; addresses and ports handed out by the lobby) |

What a relay for browsers has to provide, then:

1. **Per browser player, one session** on the relay (a WebSocket is enough to start
   with; WebTransport datagrams or a WebRTC data channel would spare UDP traffic the
   head-of-line blocking of TCP — the game's own traffic is UDP at up to 60 packets a
   second per peer).
2. **TCP**: for each connection the machine opens, a TCP connection from the relay to
   the lobby server (ports 40810 and the lobby port). Bytes both ways, close both ways.
   The relay should refuse every other destination (it must not be an open proxy).
3. **UDP**: per session, **one UDP socket on the relay for each source port the machine
   uses** (4000–4004), kept for the session and used for every destination. Datagrams
   from the page go out of it with the destination the machine named; whatever arrives
   on it goes to the page with the sender's address and port. That is exactly the
   desktop application's rule, so a browser player looks to the lobby and to desktop
   players like a player whose address is the relay's — desktop and browser players can
   then be in one game, with the browser player's game traffic going through the relay.
   Destinations must be limited (the lobby's UDP 10101 and addresses the lobby has named
   to this session, or at least no private and no loop-back addresses).
4. The simplest framing keeps `RtaNet.cpp` whole: compile it into the browser build and
   replace its `socket`/`connect`/`sendto`/`recvfrom` calls by messages to the relay
   ("open TCP n to a:p", "TCP n data", "UDP from port s to a:p", …). The alternative,
   shipping raw Ethernet frames to a relay that runs `RtaNet.cpp` itself, needs less
   code in the page but puts every player's user-space TCP on the server.
5. **Where it runs**: next to the lobby server is natural (one address for the lobby's
   rule that gateway, lobby and discovery are reachable at one address). It needs TLS
   (a page served over https may only open `wss://`), a certificate, and the
   cross-origin isolation headers are the page's affair, not the relay's.
6. **Two things to settle before building it**: (a) floating point — the browser build
   cannot set the rounding mode the console uses (see above), and the game's lock-step
   play compares simulation results between players: a browser and a desktop player may
   drift apart (docs/issues/float-divergence.md lists what is sensitive); browser-only
   games would agree with each other; (b) latency — every packet of a browser player
   takes the detour through the relay.

The memory card's network setting (`WriteNetcnf` in `Rta.cpp`: four small files) and the
one-step online driver (`RtaOnline.cpp`, stand-alone C++) would carry over as they are.
Nothing here has been tried. The public server was never contacted.
