# play-web — the game in a web browser

Champions: Return to Arms (SLUS-20973 v2.00) in the browser version of the
[Play!](https://github.com/jpd002/Play-) PlayStation 2 emulator, compiled to WebAssembly,
with the same changes to the emulator's core as the desktop application
([tools/play-net](../play-net/README.md)) and the same patches applied while it runs.
A player opens a page, picks the disc image from their own computer and plays: nothing is
installed, the image is read where it is and never leaves the computer.

**State: an experiment that runs.** Offline only. In Chrome 155 on an Apple M5 Pro it
holds 60 frames a second at the title and standing in the first level (resolution factor
2, the Mac otherwise quiet); what was measured, what was checked and how, and what is
missing is at the end, and the working notes with every figure are in
[docs/issues/browser-build.md](../../docs/issues/browser-build.md).

Nothing of the game and nothing of Play! is in this directory: what is here is our own
source, a patch against Play! and scripts.

| File | What it is |
|---|---|
| `build.sh` | gets Play! at commit `83700b2c31e593bc94e845b4b31b797be84dda59` into `local/play-web-src` (its own copy), applies `../play-net/play-net.patch` and `play-web.patch`, copies `src/` in, builds with Emscripten, and puts the page together in `local/play-web-site` |
| `play-web.patch` | the changes to Play! on top of `play-net.patch` (10 files): the video thread owning the canvas, the disc read in place by range requests, uniform blocks sent only when changed, counters, the build's link options |
| `src/RtaWeb.cpp` | the front end in the emulator (takes the place of Play!'s `Source/ui_js/Main.cpp`): patches and display patches, the pad, sound into a ring, the video handler, counters and test aids |
| `src/GlStateShadow.h` | GL state remembered on our side so that calls which change nothing are not made (see "Speed") |
| `web/index.html`, `web/rta-web.js` | the page: disc picker with the wrong-disc refusal, keyboard and controller, sound start, memory card kept in the browser's storage, the speed line, test aids |
| `web/rta-sound.js` | the AudioWorklet that plays the sound ring |
| `serve.py` | a web server for this computer only (127.0.0.1) that sends the two headers the page needs; with `--disc`, `--report`, `--shots` a developer's test rig |

## Build and run

Apple silicon macOS; tested with Emscripten 6.0.12, CMake 4.4 and Ninja 1.13 from Homebrew.

```
brew install emscripten cmake ninja
tools/play-web/build.sh
tools/play-web/serve.py                # http://127.0.0.1:8973/
```

Open the address in Chrome, press *Choose disc image…* and pick your image of the game.
The page refuses anything else and says why (not a disc image; another game; this game
in another version: the program's checksum has to be `4028A55F`).

The page must be served with `Cross-Origin-Opener-Policy: same-origin` and
`Cross-Origin-Embedder-Policy: require-corp` (the emulator's threads share memory, which
a browser allows only to such pages), and over `https` or from `localhost`/`127.0.0.1`.
`serve.py` does that for local use. Hosting it for others is a matter of putting
`local/play-web-site` on a server that sends those two headers; no part of the game is in
that folder (the patch file is ours).

The first time, the page asks for the image with the browser's file dialog; browsers
that can keep a handle to a picked file (the File System Access interface: Chrome, Edge)
offer "Continue with <file name>" at the next visit and only ask whether the page may
read it again. The memory card (Play! keeps it as a folder of files) and the settings
(picture factor, sound on or off) are kept in the browser's storage for the site.

## Controls

Keyboard (the desktop application's layout): W A S D left stick, arrow keys direction
pad, I J K L = △ □ ✕ ○, Q E = L1 R1, 1 3 = L2 R2, X C = L3 R3, T F G H right stick,
Enter Start, Backspace Select.

Controller: the first one the browser reports with its "standard" layout (Gamepad API;
a DualSense, DualShock or Xbox pad by USB or Bluetooth) is the pad in port 1, with
nothing to bind: sticks with a 15 % dead zone, triggers pressed beyond 30 %, Options =
Start, Create/Share and the touchpad button = Select. A browser shows a controller to a
page only after a button has been pressed on it while the page is in front.

## How it differs from the desktop application

| | Desktop (`tools/play-net`) | Browser |
|---|---|---|
| translated game code | native ARM code, blocks linked to each other | one small WebAssembly module per block, every block returns to the dispatcher |
| graphics | OpenGL (on Metal) | WebGL 2 from a worker that owns the canvas (OffscreenCanvas) |
| code overwritten by the game | noticed through page protection | not noticed (no page protection in WebAssembly); patches are written before the code first runs and checked every frame |
| floating-point rounding | toward zero, as the console | the browser's (to nearest): results can differ in the last bit — this matters for playing online against a desktop player (`docs/issues/float-divergence.md`) |
| network | the game's own stack on real sockets | none yet (see the notes: what a relay would have to do) |
| pacing | by the display's refresh | by a timer (60.00 a second) |
| textures replaced, dumps, one-step online, control socket | yes | no |

## Speed, and what was done for it

Measured in Chrome 155 (figures, loads and method in the notes). A frame has 16.7 ms.

| | machine thread | video thread | frames a second |
|---|---|---|---|
| title | 6 – 9 ms | 2.4 – 3.5 ms | 60 |
| first level, standing, factor 2 | 9.9 ms of CPU | 6.2 ms of CPU | 60 (93 with the limiter off) |
| the same in the first build (the canvas and disc changes below, nothing else; load 18) | 31 – 38 ms (waiting for video) | 24 – 30 ms | 26 – 31 |

With the Mac busy with other work everything is slower: at load averages of 80 – 130 the
level ran at 43 – 53 frames a second. In one such session the two ways of reaching WebGL
were compared directly: ours 43 – 46 frames a second, upstream's (the context on the
page's main thread, `gl=main`) 27 – 29.

| What was slow | Cause | Change |
|---|---|---|
| every GL call crossed to the page's main thread | upstream makes the WebGL context on the main thread and draws from the video thread | the video thread is started with the canvas handed over (OffscreenCanvas), makes the context itself and runs from its worker's event loop, one turn per picture: a browser shows what a worker drew only when its task ends (`play-web.patch`: `GSHandler.cpp`, `g_webCanvas`) |
| 28,700 WebGL calls a frame in the first level, 7,800 of them `texParameteri` | Play!'s handler sets a group of GL state whenever the game writes the register behind it, changed or not, and this game writes them all before nearly every draw; a desktop driver drops such calls for nothing, a browser checks, packs and ships each one | the state is remembered on our side and a call that changes nothing is not made (`src/GlStateShadow.h`: 28,700 calls a frame became 11,700); the two uniform blocks are sent only when their values changed (`GSH_OpenGL.cpp`). Video thread 30 ms → 13 ms at the same load |
| the machine's thread and the video thread waiting on the allocator | every texture the game sends and every batch of register writes is allocated on one thread and freed on the other; Emscripten's default allocator has one lock | linked with `mimalloc` |
| the disc read through the main thread | upstream asks the page's main thread for each 2 KiB and polls it | read on the machine's thread by a synchronous range request, 128 KiB at a time, the last 48 pieces kept (`Js_DiscImageDeviceStream.cpp`) |

Tried without gain: the C++ compiled with WebAssembly SIMD (`-msimd128`). Not tried:
linking translated blocks to each other with WebAssembly tail calls (194,000 block starts
a frame go through the dispatcher), pacing by the display's refresh.

The page keeps its canvas at 896 lines at most (a 1749 × 1312 canvas was slower in every
run that had one; cause not found). A page that is hidden or covered is run slowly by
the browser and the system (7 – 45 frames a second): play with the window in front.

## What has been seen to work, and what not

Checked by test (table "Checked" in the notes): the build; a disc image read in place
through the same path a picked file takes (with a stand-in file, since no test can
answer a file dialog); the four refusals of a wrong image; the patch set and display
patches at every start; a steady picture (12 consecutive identical pictures on a still
screen); title and first level reached by scripted presses and looked at; key events
reaching the machine's pad; sound without gaps at the title (0 times dry in 10 s,
counted, muted); the game's memory-card folder and a marker file surviving a new visit;
the picture factor changed while playing.

Not checked, because it needs a person: a controller (a browser shows one to a page only
after a button press), the file dialog itself and "Continue with …", how the sound
sounds, full screen, a game saved by playing and loaded again.

Not there: online play — browsers have no raw sockets, a relay on the server is needed
(designed in the notes, not built); playing against desktop players even with a relay —
measured: the browser build rounds floating-point results to nearest where the desktop
build and the console round toward zero, so a mixed game would be out of sync within
seconds (the notes give the measurement and three ways out); anything beyond the first
level; Safari and Firefox (untested); replaced textures, dumps and the control socket of
the desktop application.

## Developer aids

`serve.py --disc IMAGE --report FILE --shots DIR` and the page's address parameters
(`disc=/dev/disc.iso`, `auto=hub`, `report=1`, `limit=0`, `gl=main`, `res=N`, `sound=0`,
`shot=NAME.png`, `card=0`, `canvas=LINES`, `auto=trace`, `title=…`) are described in `docs/issues/browser-build.md`, "How to boot
it and read the numbers", with what every figure means. In the page's console `rta` has
the same things for use by hand (`await rta.measure(10)`, `await rta.glProfile(5)`,
`await rta.burst(8)`, `rta.peek(address)`, `await rta.tap("cross", 8, 60)` …).
Pictures and dumps are game output: keep them under `local/`.
