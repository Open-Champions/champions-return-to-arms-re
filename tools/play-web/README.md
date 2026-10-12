# play-web — the game in a web browser

Champions: Return to Arms (SLUS-20973 v2.00) in the browser version of the
[Play!](https://github.com/jpd002/Play-) PlayStation 2 emulator, compiled to WebAssembly,
with the same changes to the emulator's core as the desktop application
([tools/play-net](../play-net/README.md)) and the same patches applied while it runs.
A player opens a page, picks the disc image from their own computer and plays: nothing is
installed, the image is read where it is and never leaves the computer.

**State: an experiment that runs.** Offline, and **online with other browser players**
through a small relay on the server (section "Online play"; two pages were put through a
whole game start and stayed in step). In Chrome 155 on an Apple M5 Pro it
holds 60 frames a second at the title and standing in the first level (resolution factor
2, the Mac otherwise quiet); what was measured, what was checked and how, and what is
missing is at the end, and the working notes with every figure are in
[docs/issues/browser-build.md](../../docs/issues/browser-build.md). It also starts and
plays in Brave and in Safari's engine, and tells a visitor whose browser lacks something
what that is (section "Browsers"); Firefox, Edge and Windows have not been tried.
[docs/STATE-OF-PLAY.md](../../docs/STATE-OF-PLAY.md) sets this build beside the other
routes to a game: the desktop application ([docs/play-online.md](../../docs/play-online.md)),
PCSX2 with the patch file ([docs/online-setup.md](../../docs/online-setup.md)) and the
native build ([docs/issues/native-recomp.md](../../docs/issues/native-recomp.md)).

Nothing of the game and nothing of Play! is in this directory: what is here is our own
source, a patch against Play! and scripts.

| File | What it is |
|---|---|
| `build.sh` | gets Play! at commit `83700b2c31e593bc94e845b4b31b797be84dda59` into `local/play-web-src` (its own copy), applies `../play-net/play-net.patch`, `play-web.patch` and `perf.patch`, copies `src/` in, builds with Emscripten, and puts the page together in `local/play-web-site` |
| `play-web.patch` | the changes to Play! on top of `play-net.patch` (10 files): the video thread owning the canvas, the disc read in place by range requests (or through the page's main thread where a browser has none on a picked file; a piece that cannot be read is asked for again instead of ending the machine), uniform blocks sent only when changed, counters, the build's link options |
| `perf.patch` | applied by `build.sh` after the two above (18 files): about a fifth less work per frame with the picture and the simulation unchanged - VU1's flags computed only where its program reads them, picture transfers by row, the VIF unpack, linked blocks ([docs/issues/browser-perf.md](../../docs/issues/browser-perf.md)); its option `-DRTA_WASM_EXCEPTIONS=ON` is off |
| `src/RtaWeb.cpp` | the front end in the emulator (takes the place of Play!'s `Source/ui_js/Main.cpp`): patches and display patches, the pad, sound into a ring, the video handler, counters and test aids |
| `src/RtaWebNet.cpp`, `RtaWebNet.h` | online play: the sockets of the desktop application's network turned into messages for the relay, the Ethernet adaptor's hooks, the network setting on the memory card, and the "one-step online" driver's link to the page |
| `src/RtaWebNetCore.cpp`, `RtaWebSock.h` | `../play-net/src/RtaNet.cpp` compiled for the browser without a change: its socket calls are given other names, which `RtaWebNet.cpp` carries out |
| `relay/relay.py` | the relay: what stands in for the sockets a page does not have (Python 3, standard library only); `relay/check.py` tests one; `relay/README.md` says how to run it on a server |
| `src/GlStateShadow.h` | GL state remembered on our side so that calls which change nothing are not made (see "Speed") |
| `web/index.html` | the page, and in it the **start-up check**: a plain script that asks the browser what it has of what the page needs and says what is missing before anything large is loaded |
| `web/rta-web.js` | the page's program: loading with a progress bar, the disc image (button, dropped file, "Continue with …", the wrong-file refusals, a file that goes away), keyboard, controller and on-screen pad with their tables (*Controls*), sound start and volume, pause when the page is hidden, the memory card kept in the browser's storage (one tab at a time) and saved to or loaded from a file (*Settings*), the speed line, the *Online…* panel and the connection to the relay, test aids |
| `web/rta-sound.js` | the AudioWorklet that plays the sound ring (volume and mute are applied there) |
| `serve.py` | a web server for this computer only (127.0.0.1) that sends the two headers the page needs; with `--disc`, `--report`, `--shots` a developer's test rig |

## Build and run

Apple silicon macOS; tested with Emscripten 6.0.12, CMake 4.4 and Ninja 1.13 from Homebrew.

```
brew install emscripten cmake ninja
tools/play-web/build.sh
tools/play-web/serve.py                # http://127.0.0.1:8973/
```

Open the address in a current browser on a computer (section "Browsers"), press *Choose
your disc image…* and pick your image of the game, or drop the file on the page. The page
refuses anything else and says why (not a disc image; an archive or another emulator's
format that has to be unpacked to an .iso first; another game; this game in another
version: the program's checksum has to be `4028A55F`).

The page must be served with `Cross-Origin-Opener-Policy: same-origin` and
`Cross-Origin-Embedder-Policy: require-corp` (the emulator's threads share memory, which
a browser allows only to such pages), and over `https` or from `localhost`/`127.0.0.1`.
`serve.py` does that for local use. Hosting it for others is a matter of putting
`local/play-web-site` on a server that sends those two headers; no part of the game is in
that folder (the patch file is ours). Online play needs two things more on that server
(section "Online play").

The first time, the page asks for the image with the browser's file dialog; browsers
that can keep a handle to a picked file (the File System Access interface: Chrome, Edge)
offer "Continue with <file name>" at the next visit and only ask whether the page may
read it again; in the others (Brave as it comes, Safari, Firefox) the file is chosen at
every visit. When the file can no longer be read while the game runs (moved, its drive
removed, the permission ended) the game waits, the page says so, and it goes on where it
stood once the file is chosen again.

The memory card (Play! keeps it as a folder of files) and the settings (picture factor,
volume, keys, controller buttons) are kept in the browser's storage for the site. One tab
has the card at a time: a second tab says so and waits. **Saved games as a file**:
*Settings → Saved games → Save to a file…* writes a zip of the card's folders
(`vfs/mc0/…`, `vfs/mc1/…`) and *Load from a file…* takes one, compressed or not, at any
folder depth. That is the way to another browser or computer, to a copy for safe keeping
(Safari removes a site's storage after a week without a visit; a private window keeps
nothing), and into the Mac application: its card is the same two folders in
`~/Library/Application Support/Play-RTA/player1/vfs`. The saved online login is not in
the file.

A page that is not in front is run slowly by a browser. A game played alone is
**paused** when the page is hidden ("Paused" over the picture; a click, a key or a
controller button goes on). An online game cannot be paused - everybody's machine waits
for it - so the page warns instead: when going online starts, in the tab's title while it
is hidden, and afterwards.

## Controls

Everything is listed, and can be changed by clicking an entry and pressing the key or
button wanted, under *Controls*.

Keyboard (the desktop application's layout, by the keys' places, so the same on every
keyboard): W A S D left stick, arrow keys direction pad, I J K L = △ □ ✕ ○, Q E = L1 R1,
1 3 = L2 R2, X C = L3 R3, T F G H right stick, Enter Start, Backspace Select.

Controller: the one a button was pressed on last is the pad in port 1. With the "standard"
layout of the Gamepad API (a DualSense, DualShock, Xbox or Switch Pro pad in Chrome, Edge
and Safari; most of them in Firefox) there is nothing to bind: sticks with a 15 % dead
zone, triggers pressed beyond 30 %, Options = Start, Create/Share and the touchpad button
= Select. A pad the browser has no standard layout for is used with the same numbers as a
guess, and *Controls → Set up the controller* asks for every button in turn. A browser
shows a controller to a page only after a button has been pressed on it while the page is
in front. **No controller was tried in a browser** (no test can press a button).

Touch screen: an on-screen pad (left stick, direction pad, the four buttons, L1 L2 R1 R2,
Start, Select) appears at the first touch; *Settings* has "always" and "never". It is
plain, has no right stick, and was only tried with touch events made by a test.

## Browsers

At start the page asks the browser what it has and says plainly what is missing; the
table with every item, what stands in for it and what each browser here answered is in
the notes ("For whoever opens the link").

| Browser | State |
|---|---|
| Chrome 155 (macOS) | everything; what the build was measured in |
| Brave 155 (macOS) | runs (title 60 frames a second); no "Continue with …" unless Brave's flag for the File System Access interface is on |
| Safari 27 | its engine (WebKit 27.2, in a test window: Safari's WebDriver is not enabled here) has everything the page needs and plays, with sound; **level loads stall for seconds** (translating a block of game code costs it 6 – 19 times what it costs Chrome) and reading the image is slower; no "Continue with …". Safari's own window was not tried |
| Edge | not installed here; Chromium, expected as Chrome |
| Firefox | not installed here; by reading it has what the page cannot do without; no "Continue with …"; **never run** |
| Windows, Linux, ChromeOS | never run; what the code does that depends on the system is listed in the notes, with frame pacing on a Windows laptop on battery as the open risk |
| phones, tablets | not what this is for (1 GB of memory, three busy threads, a 4 GB file); the page says so at start |

What a browser lacks that the page cannot do without - threads with shared memory
(cross-origin isolation), WebAssembly with SIMD, module workers, WebGL 2 - stops the
start with a sentence that names it. What it can do without has a fall-back: no WebGL 2
on a thread's own canvas → the context on the page's main thread (slower); no range
requests on a picked file from a thread → the pieces are read through the main thread;
no File System Access → the file dialog every time; no storage → saved games only as a
file; no Gamepad API → keyboard.

## Online play

Browser players play with browser players, through the same lobby server as everybody
else. **A browser player and a player with the desktop application cannot share a game**
(their machines round differently and fall out of step within seconds: see the notes);
the lobby does not keep the two kinds apart, so say which kind you are hosting.

**For a player** it is the desktop application's "one-step online" (`docs/play-online.md`,
section 4) as buttons on the page - the same code, compiled in:

- *Online…* → **Host a game**: the page presses its own way from wherever the game is
  (power-on or the title screen) through *Internet Game*, the network setting, the
  server's terms and the log-in, opens a game named with a **code of four letters** and
  stops in its room. Tell your friends the code; press ✕ *Start Game* when they are there.
- *Online…* → **Join a game** with the code: the same way in, then into that game's room.
- **Just go to the lobby** stops at the game list.
- The first time, the page asks for a **player name** (3 to 15 letters and digits). That
  is all: the account is made by the page in the game's own account form, with a random
  password that is kept in the browser's storage for the site (beside the memory card)
  and is never shown. *Forget online login* removes it.
- The first time on a server the game's **character screens** are yours (make one, or △
  for a stored one); after that Host and Join take the character used last by themselves.
- While the page is pressing, your keys and controller are not passed to the game; a strip
  under the title says where it is, and why it stopped if it did.
- The page keeps the screen awake while the game runs (a controller does not count as
  activity for the computer's idle timer). When the computer sleeps or the screen is
  switched off, a browser closes the page's connections and an online game is lost; the
  page connects again by itself for the next attempt.
- **Keep the page in front while you play online.** A browser runs a hidden or covered
  page slowly, and every machine in the game waits for the slowest. The page cannot
  pause an online game; it says this when going online starts, turns the tab's title into
  "Come back: the others are waiting" while it is hidden, and tells afterwards for how
  long it was.

**For whoever serves the page** two things are needed beside the page's files:

1. **The relay** (`relay/relay.py`, `relay/README.md`). A page has no TCP or UDP, only
   connections to a web server. The page opens one WebSocket connection to the relay;
   the relay owns the real sockets: the two TCP connections to the lobby server (it will
   connect to the configured lobby server's ports and to nothing else) and one UDP socket
   per UDP port the console uses, so that the lobby server sees a browser player as an
   ordinary player at the relay's address. Game traffic between two browser players is
   handed from one session to the other inside the relay. A page served over `https`
   may only open `wss://`: the relay sits behind the web server that has the certificate.
2. **`online.json` beside `index.html`**: `{ "relay": "relay", "signin": "NAME.pnach" }`.
   `relay` is the address of the relay's WebSocket, relative to the page or complete;
   `signin` names a patch file beside the page that takes the game past its sign-in
   step. That file is not in this repository (as for the desktop application: see
   `docs/play-online.md`); a page without it shows the panel and says that it cannot go
   online. Without `online.json` the page is the offline page and shows nothing of this.

How it is put together: the console's own network stack talks to an emulated Ethernet
adaptor; `RtaNet.cpp` (the desktop application's user-space network: address by DHCP,
the lobby's name by DNS, TCP ended locally, one socket per UDP port) is compiled in
unchanged and its dozen socket calls become messages (`RtaWebSock.h`). The machine's
thread never returns to the browser, so the WebSocket belongs to the page's main thread
and the two meet in a pair of queues; a datagram costs one hand-over to the main thread
and one WebSocket message each way. `RtaOnline.cpp` is called at every vertical blank,
as in the application.

Trying it on one computer, with a lobby server running on the same computer:

```
tools/play-web/relay/relay.py --lobby <this computer's network address, not 127.0.0.1>
tools/play-web/serve.py --port 8973 --disc "/path/to/image.iso"
# two browser profiles, each:  http://127.0.0.1:8973/index.html?disc=/dev/disc.iso&relay=ws://127.0.0.1:8975/relay
```

(with the sign-in patch file and an `online.json` naming it put into `local/play-web-site`
by hand: `build.sh` does not). `relay/check.py --selftest` tests a relay against a
stand-in lobby; `relay/check.py wss://…` checks a running one without logging in anywhere.

## How it differs from the desktop application

| | Desktop (`tools/play-net`) | Browser |
|---|---|---|
| translated game code | native ARM code, blocks linked to each other | one small WebAssembly module per block, every block returns to the dispatcher |
| graphics | OpenGL (on Metal) | WebGL 2 from a worker that owns the canvas (OffscreenCanvas) |
| code overwritten by the game | noticed through page protection | not noticed (no page protection in WebAssembly); patches are written before the code first runs and checked every frame |
| floating-point rounding | toward zero, as the console | the browser's (to nearest): results can differ in the last bit — this matters for playing online against a desktop player (`docs/issues/float-divergence.md`) |
| network | the game's own stack on real sockets | the same stack; the sockets are a relay's, reached over one WebSocket connection |
| online | with other desktop players (and consoles) | with other browser players only |
| pacing | by the display's refresh | by a timer (60.00 a second) |
| one-step online, games by code | yes (menu *Online*) | yes (button *Online…*): the same code |
| textures replaced, dumps, control socket | yes | no |

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

Checked later, for whoever opens the link (the notes' section of that name has how):
the start-up check in Chrome, Brave and Safari's engine; the real image through the file
chooser's path (given without a dialog) in Chrome and in Safari's engine, and dropped on
the page in Chrome, with "Continue with …" offered at the next visit; the image read
through the page's main thread; a picked file taken away during play and chosen again;
keys by real key events, a key changed in *Controls*; the on-screen pad by touch events;
pause when hidden and the way back, in Chrome and Safari's engine; a second tab; the
page loaded again during play; storage full; saved games to a zip and back, and a zip
made by another tool; sound in Safari's engine; a cold start (1.5 s plus 807 KB over the
line) and a warm one (0.4 s, 1 KB); the tab's memory over 20 minutes in a level; a build
from an empty directory by `build.sh`.

Not checked, because it needs a person or a machine that is not here: a controller (a
browser shows one to a page only after a button press), the file dialog itself and the
browser's question after "Continue with …", how the sound sounds, full screen (asked for
and refused in the unattended test window), a game saved by playing and loaded again,
Safari's own window, Firefox, Edge, Windows, a real touch screen.

Online, checked by test on one Mac (two Chrome pages with their own profiles, the relay
and a lobby server on the same Mac; the notes have the figures): a first start that made
its account and reached the lobby by itself; a game hosted by code and joined by code;
both pages in the first level after *Start Game*; 1,387 consecutive lockstep frames for
which both pages held the game's own sync hash, all equal, with both characters walking;
a second start that needed no press at all (saved login, remembered character). The
relay's own test (`relay/check.py --selftest`: destinations it must refuse, limits,
datagrams from session to session) passes. Not checked: more than two players, a game
beyond the first level, two players in different places (everything was on one computer),
the panel used by a hand (a test went through it by clicks sent to its buttons), WebTransport (not built: the game's datagrams travel
on the WebSocket connection, in order, so a lost packet delays the ones behind it).

Not there: playing against desktop players —
measured: the browser build rounds floating-point results to nearest where the desktop
build and the console round toward zero, so a mixed game would be out of sync within
seconds (the notes give the measurement and three ways out); a session that survives a
lost connection to the relay; anything beyond the first
level; quick level loads in Safari (section "Browsers"); replaced textures, dumps and the
control socket of the desktop application.

## Developer aids

`serve.py --disc IMAGE --report FILE --shots DIR` and the page's address parameters
(`disc=/dev/disc.iso`, `auto=hub`, `report=1`, `limit=0`, `gl=main`, `res=N`, `sound=0`,
`shot=NAME.png`, `card=0`, `canvas=LINES`, `auto=trace`, `title=…`, `pause=0`, `discread=page`, `touch=1`, `relay=ws://127.0.0.1:PORT/relay`) are described in `docs/issues/browser-build.md`, "How to boot
it and read the numbers", with what every figure means. In the page's console `rta` has
the same things for use by hand (`await rta.measure(10)`, `await rta.glProfile(5)`,
`await rta.burst(8)`, `rta.peek(address)`, `await rta.tap("cross", 8, 60)` …; for online
play `rta.online.state()`, `rta.online.start(1)`, `rta.online.start(2, "CODE")`,
`rta.online.name("…")`, `await rta.online.pings(50)`).
Pictures and dumps are game output: keep them under `local/`.
