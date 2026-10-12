# play-web — the game in a web browser

Champions: Return to Arms (SLUS-20973 v2.00) in the browser version of the
[Play!](https://github.com/jpd002/Play-) PlayStation 2 emulator, compiled to WebAssembly,
with the same changes to the emulator's core as the desktop application
([tools/play-net](../play-net/README.md)) and the same patches applied while it runs.
A player opens a page, picks the disc image from their own computer and plays: nothing is
installed, the image is read where it is and never leaves the computer.

**State: an experiment that runs.** Offline only. What was measured and what is missing
is at the end; the working notes with every figure are in
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

## Developer aids

`serve.py --disc IMAGE --report FILE --shots DIR` and the page's address parameters
(`disc=/dev/disc.iso`, `auto=hub`, `report=1`, `limit=0`, `gl=main`, `res=N`, `sound=0`,
`shot=NAME.png`, `title=…`) are described in `docs/issues/browser-build.md`, "How to boot
it and read the numbers", with what every figure means. In the page's console `rta` has
the same things for use by hand (`await rta.measure(10)`, `await rta.glProfile(5)`,
`await rta.burst(8)`, `rta.peek(address)`, `await rta.tap("cross", 8, 60)` …).
Pictures and dumps are game output: keep them under `local/`.
