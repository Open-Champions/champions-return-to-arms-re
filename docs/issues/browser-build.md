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
- First level, standing: NOT full speed yet. About 50 frames a second; the machine thread
  needs about 18 ms of CPU per frame, the video thread 13 ms.

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
| `auto=title` or `auto=hub` | DEV: scripted presses to the title screen, or on into the first level (the button sequence of `local/play-out/tohub.py`), a 10 s measurement at each, eight consecutive pictures compared, in the level also 10 s with the limiter off |
| `report=1` | DEV: every figure is POSTed to `/report` (appended to the `--report` file, one JSON object per line: `kind` is `start`, `second`, `title`, `title-burst`, `hub`, `hub-burst`, `shot`, `hub-unlimited`, `done` or `failed`) |
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

Thread CPU time in Chrome (`ps -M` on the renderer process, two readings 20 s apart,
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
