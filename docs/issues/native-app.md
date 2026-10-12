# The native application

Started 2026-10-12. The pieces of a native build of Champions: Return to Arms (SLUS-20973
v2.00) existed separately: the translated game and its runtime
(`docs/issues/native-recomp.md`), a renderer (`docs/issues/native-render.md`), a sound
library (`docs/issues/native-sound.md`). This is the program that puts them into one
window: `tools/recomp/app/`. Every statement says whether it was **Ran** (with what was
seen) or only **Read**; "Not reached" and "Left for a release" list the rest.

Nothing derived from the game is in the repository: generated C++, objects, programs,
pictures, streams and memory cards are under `local/recomp-out/`.

## Start it

```
python3 tools/recomp/app/build.py            # once, and after any change (about 1 minute)
local/recomp-out/bin/rta_app --disc "/path/to/Champions - Return to Arms (v2.00).iso"
```

The window is titled "Champions: Return to Arms - native build (experimental)". Memory
cards go to `local/recomp-out/app-data/card` (`--data DIR` for another place). Nothing is
installed anywhere. `rta_app --help` lists the options; the head of
`tools/recomp/app/app_main.cpp` describes each (`--window WxH`, `--fullscreen`, `--scale N`
or `--size WxH`, `--volume V`, `--mute`, `--no-sound`, `--emulator-timing`, `--script`).

Keys: W A S D left stick, arrows direction pad, I J K L triangle / square / cross /
circle, Q E L1 R1, 1 3 L2 R2, X C L3 R3, Return Start, Backspace Select, F or F11 full
screen, Escape leaves it. The first game controller macOS knows is port 1 as well.

## State (2026-10-12, 13:15)

**What a person can do in it today** (each item Ran by script in the window program, see
the sections below): start from power-on; go through the memory-card screens (a blank
card is initialised), the publisher's logo, the title and its menus, character creation;
play in the first level and in a level with monsters: walk, strike, cast, fight, open the
pause menu and its load screen, change level; save (when the game asks for one) and load
the save again from the title menu after a restart; hear the game's sound through the
Mac's sound device; use the keyboard or a game controller.

**What is wrong or missing** (details under "Defects" and "Left for a release"):

- Films are not shown: the developer's logo film and the intro film end at their first
  picture (the film decoder needs the Image Processing Unit, which this machine does not
  have). The game goes from the publisher's logo straight to the title.
- One drawing fault seen in play: during the fight a long thin pole runs from the player
  to the lower right corner for some hundred ticks (stray vertices of 30 small two-pass
  meshes). Not solved.
- Sound drops out for some tens of milliseconds at a time while a level loads.
- Water, trails, heat haze and floor decals: no level that shows them was visited.
- The real DualSense could not be tested (it was not connected, see "Input").

## The parts

| File | Does |
|---|---|
| `app/build.py` | translates the game with the suggested fix set (`recomp.py --pnach`, into `local/recomp-out/gen-app`), compiles it (`build.py run --gen … --name rta_native_fix`), compiles runtime, renderer, sound library and this directory, links `bin/rta_app`. `--original` links `bin/rta_app_orig` from the shared unpatched translation instead (the one compared with the rig) |
| `app/app_main.cpp` | options, the window (Qt 6, OpenGL 4.1 through `render/backend_gl.cpp`), pacing, keyboard, the pad source, the `app …` script commands |
| `app/pipeline.h` | the picture path: the runtime's sink copies on the game's thread, a decoder thread runs VIF1 / VU1 / the GS model, the main thread draws |
| `app/app_rt.h/.cpp` | the few things the window program needs from inside the runtime (script state, finish, reading a file out of the disc image) |
| `app/pad_host.h`, `app/pad_mac.mm` | game controllers through GameController.framework |
| `app/emushots.py` | reference pictures: runs the emulator build silently and offline over the same script and takes its `shotfb` where the script says `app shot`; `--card DIR` starts it on a copy of a native card |

One program, one process. The translated game runs on the runtime's threads; the renderer
is installed through `rta::Hooks::video`, input through `rta::Hooks::pad`;
`tools/recomp/sound/sound_rta.cpp` is linked in place of `rt/sound_null.cpp`. The
executable is taken from the workspace (`SLUS_209.73`) or, when it is not there, copied
out of the disc image into the data directory.

**The fix set.** `rta_app` is the game with the suggested fix set applied (the word
patches of `patches/SLUS-20973_4028A55F.pnach` in the 26 sections of
`tools/play-net/sections-suggested.txt`: 90 words), as every other build of the game here.
Translated code is fixed when it is built, so the patches are written into the image the
translator reads, and the same words are written into memory when the executable is
loaded (`<gen>/patches.cpp`). `rta_app_orig` is the unpatched game.

## 1. From power-on with a picture (Ran)

Script `local/recomp-out/app-test/boot-shots.rig`: the rig's boot route with a picture at
every screen (`app shot`). The same script was run in the emulator build
(`app/emushots.py`) and the pictures were laid side by side.

| Screen | Native against the emulator's `shotfb` |
|---|---|
| card search, slot choice, "no data, initialise?", "initialisation complete" | same |
| publisher's logo | same |
| developer's logo film, intro film | **not shown** (the title appears instead) |
| title with its 3-D backdrop, logo, first menu | same (camera a moment apart) |
| game type, players, mode, difficulty | same |
| character creation: class, appearance, ability points, name grid | same |
| loading screen, first level with HUD | same |

What had to be changed for this (all in `tools/recomp/render/`):

- **A display buffer is as large as the display says.** The game shows two 640 x 224
  buffers, one per field (SMODE2 interlaced + frame mode: the 448 lines of DISPLAY are
  two fields); the film player switches to one 640 x 448 buffer at the same place.
  Surfaces only grew, so after the film set-up one of the two buffers stayed 448 lines
  high and every second picture was squeezed into the upper half. Now a buffer a
  switched-on display circuit named within the last two seconds takes the display's size
  (`Gs::display_size`); start-up names buffer 0 for the first circuit, which is the 3-D
  surface and never shown, hence "switched on" and "recently".
- **The height of a picture is asked for again.** Interface art is stored as two stacked
  field pictures and woven by the height in the game's texture header. From power-on a
  texture is drawn in the frame it is loaded, before the header list of the decoder
  knows it; its height stayed unknown for ever and the weave took the sent size (the
  title logo: 128 instead of 110 rows, so the two fields were 9 rows apart and the
  subtitle showed twice). A texture without a known height is now looked up again; a
  failed look-up makes the game-side list rescan within 3 blanks, and is repeated only
  when the list has grown.
- Uploads straight into a displayed buffer and frames that are 2-D only needed nothing:
  the card screens and the logo are drawn as sprites into the 3-D surface and presented
  like everything else.

Seen in the draw list and **not looked at on screen**: in every second frame (the other
field) the menu's sprites are drawn two lines lower in the 448-line surface and take
their rows from the other half of the picture, a quarter texel off. Woven, each frame is
a whole picture, so menu art may shimmer by 1/224 of the height. The title logo does not
move.

## 2. Input (Ran, with one thing that could not be)

`rta::PadSource` in `app_main.cpp`: port 1 is the script, the controller and the keyboard
together (buttons of all three; each stick from the first that is not at rest). The
runtime hands the state on one blank later, as before.

- **Keyboard.** Every key of the map gives its pad bit (20 keys, `app pads` after each).
  From power-on to the first level by key events alone, then W for 60 frames moved the
  character from (143.8, -141.8) to (41.3, -25.8), D to (149.3, 80.8), S+A to (150.8,
  -70.9), K put it into its strike state, Return opened and closed the pause menu: 110
  key events (`keyboard-play.rig`). The events are `QKeyEvent`s sent to the window's own
  handler; a test window takes no focus and nobody pressed a real key.
- **Controller.** A controller made by the program (`GCController
  controllerWithExtendedGamepad`, as in the emulator-based application) is attached, read
  and detached through the same notifications as a real one: all 16 buttons give their
  bit; a stick at +0.5 gives 180, at (-1, 1) gives 37 / 37, at (0.1, 0.1) stays 128
  (dead zone 0.15), triggers at 0.2 / 0.5 give R2 only (threshold 0.30).
- **The real DualSense was not connected.** `system_profiler` lists "DualSense Wireless
  Controller" under Bluetooth "Not Connected", there is no HID device for it and no USB
  gamepad, and a windowless probe of `[GCController controllers]` sees none. Attach of
  the real device is therefore **not shown**. A real controller is listened to only
  while the application is in front.
- Rumble commands are counted, not sent to the controller.

## 3. Play (Ran)

`play-window.rig` (from `playscript.py`) and `fight-window.rig` (from the pilot's
`fight.rig`), with `app shot` at chosen ticks, in a small test window.

- First level: walking, the talk prompt, striking, the pause menu, its load screen
  ("no save data"), the card check: drawn right.
- Level change to `valor`: loading screen, opening cutscene with its letterbox, then
  play with the HUD, creatures, ground shadows, the fight: drawn, with the pole fault
  below. No access outside memory in either session.
- **Pacing** (window 480 x 360 points, picture 960 x 720, display 120 Hz, the whole play
  session, load average 21 to 32): 4,603 pictures in 83.6 s. Of the 4,602 intervals 4,468
  (97.1 %) stood exactly 2 refreshes (1/60 s), 73 (1.6 %) 3 refreshes, 28 stood 4 to 6,
  33 longer (level loads and card checks; longest 363 ms). Per picture: game side 2.1 ms,
  decoder 6.3 ms, both of wall time. The swap is asked for inside the second refresh so
  that it lands on the refresh the picture is due at; when it does not wait (hidden
  window) a clock holds the period. A display that is not a multiple of 60 Hz gets clock
  pacing at 59.94.
- **Tick identity with renderer and sound attached.** `rta_app_orig` (the unpatched
  game), picture drawn off screen, sound device running silently, given the controller
  bytes of the rig's log (`rigcompare.py boot-native --replay` with `RTA_NATIVE` pointing
  at a wrapper, script `fight3.rig`, 7,904 fields in 39 s at load average 50 to 110),
  then `boot-compare`: the same result as the headless build - front end 1,383 ticks all
  simulation columns identical; first level 99 ticks identical but for the player record
  at tick 7; `valor` 5,410 ticks identical in every simulation column, the object pool
  different in the same window of 27 ticks (3,886 to 3,912). The cosmetic seed differs
  where it did (and for 35 ticks from tick 60 of the first level, where the music start
  is held, section 5). Attaching picture and sound changes nothing in the simulation.

## 4. Defects found and not solved

**The pole.** In the fight, between about ticks 2,195 and 3,302 of `valor`, a thin
textured pole runs from the player to the lower right corner. The emulator's pictures of
the same script show none (they show a faint round shell at the player). A stream
recorded at tick 2,701 (`local/recomp-out/app-test/pole.rtavs`) has 30 pairs of draws of
60 to 165 vertices each - first pass a 128 x 128 texture with blend (Cs - Cd) x As + Cd,
second pass a 1024 x 256 one with blend Cd x As - whose vertices lie at the player
except some at 0xf1a3 / 0xfd87 in GS units: the vertex program (reported entry 0x42,
primitive 0x15c) wrote a negative coordinate, which the GS takes modulo 16 bits. The
positions that go in are ordinary 16-bit model coordinates; the transformed vertex of the
one looked at was (156163, 9607, …, 390.6) before the divide. Not determined: which
object it is, and whether its matrices are wrong here or the console clips it some other
way. `RTA_GS_FAR=1` prints the VIF codes and VU1 registers at the first such vertex.

**Sound during loads.** Sound is rendered on the machine's clock, a field at a time.
While a level loads the game's thread stands still for up to 0.36 s of wall time inside
one field and the device runs dry: 51 times, 301 ms of silence in all, in the 84 s
session (reserve 40 ms). A console's sound processor runs on by itself.

## 5. Sound (Ran)

- **The device.** AudioQueue is opened and started from the application (`sound-out=device`
  is the default; `--volume`, `--mute`, `--no-sound`); tests force the gain to 0 and
  silence the buffers. Paced session: 76.9 s handed over, 82.8 s taken, reserve asked 40
  ms, 48 ms held on average. (In one of the first runs `AudioQueueStart` answered -66681
  as it had for the sound library's author; every later run started.) Nobody listened:
  whether it sounds right through the device is not shown here; the library's output was
  compared with the emulator's in `native-sound.md`.
- **The lost music of the first level: cause.** `mainloop_pollAmbientAudio` 0x322520
  runs once per displayed frame and counts the word at 0x50608c down; a level load leaves
  60 there. At 0 the word is set to a random 4 to 6 minutes and the level's music is
  started - unless `stream_queuedFlags(2)` 0x216310 finds a music entry (flag 0x20)
  active or queued on the music stream. The level change puts stop markers into that
  stream's queue, and the first one fades the title music out for 3.07 s. On a console
  the load outlasts the fade; with fast I/O the first level runs its frame 60 while the
  title music is still fading, the start is skipped, and the next try is minutes away.
  (Not a full queue: `stream_queue` 0x2113c8 refuses only an eighth entry or a file
  `cd_findFile` does not find. Found with a probe build that logged the calls.)
- **Fix** (`rt/runtime.cpp`, `fn_00322520`): the countdown is held at its last step while
  the music in the way is one a queued stop marker is about to end. The game's rule stays
  as it is and the start falls on the first frame the stream is free. Seen: held 33
  frames; the level's music queued at tick 93, playing from tick 240 (console timing:
  queued at 60, playing from 304). `--opt music-start=original` switches the hold off.
- **Times, either way** (machine time, one field = 1/59.94 s; the script's own waits are
  the same in both):

  | | fast I/O (default) | `--emulator-timing` |
  |---|---|---|
  | first level named to its first tick | 96 fields (1.6 s) | 273 fields (4.6 s) |
  | level change asked to the first tick of `valor` | 53 fields (0.9 s) | 206 fields (3.4 s) |
  | power-on to the first level playable, by the boot script | 2,413 fields (40.3 s) | 2,830 fields (47.2 s) |

## 6. Save and load (Ran)

Neither level has a save point within reach of a script (no live `SavePoint` object in
either at the moments looked at; the pause menus have no save entry), so the save was
asked for by calling the game's own request, `memcard_requestSave(0)` 0x2175b4 - what a
save point calls - with the script command `call` (a test aid, below). From there on it
is the game: card check, the list with "Create New Save Game", "Save Successful". The
card directory then held `BASLUS-20973_slot0` (310,392 bytes) beside the three files of
the boot (439,964 bytes written in all).

Quit, start again on the same directory, "Load Saved Game" from the title: 311,272 bytes
read, none written, the game is in the first level with the saved character (name, class,
hit points, gold); the card directory is byte for byte as before.

**Exchange with the emulator build: tried one way.** The native card directory copied
into a new data directory of the emulator build (`emushots.py --card`): the emulator
loads the save into the same level with the same character, and the four files are
unchanged afterwards. A save made by the emulator build loaded here: not tried.

## 7. Changes to the runtime and the translator

`tools/recomp/rt/` (signatures in `rt.h` / `iface.h` unchanged; additions only):

| Change | Why |
|---|---|
| a load from an address where nothing is answers 0xCC in every byte, a store there is dropped; counted, the first 16 listed in the report; `--opt strict-memory=1` stops instead | the game does it in ordinary play (`Player_run` 0x1ab7c0; a button pressed while the publisher's logo shows: call site 0x1501b0, 35 loads and 14 stores), the emulator answers so, and a run died on it |
| `--arg <text>` | arguments for the game's `main()`, written into the kernel's argument block in `SetupThread` |
| `fn_003205ec` (`movie_update`), `--opt films=original` | a film ends at its first update: without an Image Processing Unit the decoder polls 0x10002000 for ever (103 million reads in 25 s) |
| `fn_00322520`, `--opt music-start=original` | the level-music hold, section 5 |
| SIF command 0x80000001 answered (the word at 0x8ef2c4 is set 50 µs later); headset driver function 1 answers 0x8000000A; module loader function 9 answers by the module's own name read from its file | what the network start-up asks; **not exercised here** (offline play does not reach them) |
| patch words applied after the executable is loaded (`recomp_patches`, weak) | a translation made with `--pnach` |
| script commands `app <text>` (handed to the application), `call <address> [a0 [a1]]` (a game function called at a blank; a test aid), `rt_at_finish` | pictures and input from scripts; the save request; the application's figures at the end |

`tools/recomp/recomp.py`: `merge_entangled` merges only the members of a cluster when
more than 16 other units lie between them; such a unit has several address ranges
(`Unit.pieces`). The fix set gives one unit of 3 ranges where it gave one of 1,921
units; the unpatched translation is byte-identical to before (`diff -r`). `--pnach FILE
--sections FILE --section NAME` patch the image before translation and write
`patches.cpp`. `hle.txt` gained 0x3205ec and 0x322520.

## 8. Left for a release

- **Films**: an Image Processing Unit (commands at 0x10002000, DMA channels 3 and 4; the
  game uses Sony's MPEG library) and the film player's upload into its 448-line buffer.
- **The pole** (section 4), and a look at what no visited level shows: water, trails and
  beams, weapon glow shells, heat haze, floor decals; freeing textures.
- **Sound that does not depend on the game's thread** (a mixer thread on real time, or
  the machine's clock advanced during stalls), and a listening test on the device.
- **The two unexplained differences from the rig**: the player record at tick 7 of the
  first level (bytes 0x4a00 to 0x4aff, one tick), and the object pool in 27 consecutive
  ticks of the fight (3,886 to 3,912), every other column identical throughout. Both are
  unchanged by renderer and sound; neither was located.
- **ERX modules** (`LIBINSCK`, `NG_INSCK`, `DNAS_NET`): relocatable code the network
  set-up loads; not translated (`native-recomp.md`, step 4).
- **Network in the application**: `tools/recomp/net` links the runtime with its own
  supplied-function list into a headless program; the application links none of it.
  Needed: its shim as a module of the application, a lobby address option, and the
  front end's network screens looked at.
- **Windows**, exactly: `rt/host_win32.cpp` (thread with a large stack, 64-bit file
  offsets, exit, sleep); a WASAPI or waveOut sink in `sound/audio_out.cpp`; a pad file
  for XInput or Windows.Gaming.Input beside `pad_mac.mm`; the build scripts (clang-cl or
  MSVC: weak definitions in `hle_weak.cpp`, `/fp:strict`); Qt 6 for Windows with a
  desktop OpenGL driver, or a Direct3D backend behind `render/backend.h`.
- **The application itself**: an application bundle with Qt beside it (today it runs from
  the build directory against Homebrew's Qt), settings kept between runs, key and
  controller bindings, a second player, rumble, the delay from a press to the picture
  (three stages hand whole frames on; not measured), a real controller's attach.

## 9. How to repeat

```
export RTA_DISC="/path/to/your/disc image.iso"
T=local/recomp-out/app-test
python3 tools/recomp/app/build.py && python3 tools/recomp/app/build.py --original
# a test run: small window behind the others, no sound, as fast as it goes
local/recomp-out/bin/rta_app --test "native app" --window 320x240 --size 640x448 --unpaced \
    --data $T/data1 --script $T/boot-shots.rig
# the same script in the emulator build, for the pictures beside it
python3 -I -B tools/recomp/app/emushots.py --disc "$RTA_DISC" --data $T/emu1 --script $T/boot-shots.rig --out $T/emu-shots
# paced, with the device (silent in a test): pacing and device figures at the end
local/recomp-out/bin/rta_app --test "native app" --window 480x360 --data $T/data5 --script $T/play-window.rig
# against the rig's log, renderer and sound attached ($T/app-as-native.sh runs rta_app_orig --offscreen)
RTA_NATIVE=$PWD/$T/app-as-native.sh python3 tools/recomp/rigcompare.py boot-native --script local/recomp-out/fight3.rig --replay
python3 tools/recomp/rigcompare.py boot-compare
```

Scripts under `local/recomp-out/app-test/`: `boot-shots.rig`, `input-test.rig`,
`keyboard-play.rig`, `play-window.rig`, `fight-window.rig`, `save1.rig`, `load1.rig`,
`music-probe.rig` with `music-watch.txt`, `times.rig`. Debugging aids in the renderer,
all off unless the variable is set: `RTA_GS_LOG` (display registers, surface sizes),
`RTA_GS_FIELDS` (field sprites), `RTA_GS_FAR` (far vertices).
