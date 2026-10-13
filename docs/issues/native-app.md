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

**What was wrong or missing at 13:15, and where it stands** (section 10 has each):

- Films were not shown. **They play** (10.3): the game's own film player on a host
  MPEG-2 decoder, whole frames, in step with their sound.
- The pole in fights. **Solved** (10.1): VU1 computed with the host's numbers.
- Sound dropped out while a level loads. **It does not any more** (10.4): the sound
  side runs by itself on the device's real-time thread.
- Water, heat haze, the bag, the map, dialogue were never looked at. **Toured in both
  builds** (10.2): the heat haze, the bag's item glow and item pictures and everything
  after a dialogue were wrong and are corrected; water, lava, light shafts, menus were
  right. Trails, hit effects and decals in a fight: drawn, not compared close up.
- The real DualSense could not be tested (it was not connected, see "Input"): unchanged.
- Still open: 10.7.

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
  set-up loads; not translated (`native-recomp.md`, step 4). (Since found to serve the
  sign-in step only, which the lobby path does not reach: `native-online.md`.)
- **Network in the application**: done since by `tools/recomp/net` (`native-online.md`):
  `app/build.py` links its driver and the one-step online into `rta_app`, which was run
  through the lobby into a game as host and as joiner in a test window;
  `tools/recomp/net/play-native.sh` starts it with `--server`, `--online`, `--host`,
  `--join CODE`. Left there: the name question on the window was built and not run.
- **Windows**: written since, and built on the Mac with a cross-compiler
  (`docs/issues/native-windows.md`): `rt/host_win32.cpp`, a WASAPI / waveOut device,
  XInput, a Win32 window with OpenGL through WGL in place of Qt (`app/win_main.cpp`),
  the picture settings, the art pack read without Qt, and the network over Winsock.
  It compiles and links (`app/build_win.py`); **nothing of it has been run on Windows** -
  what is left is a person with a PC and the test plan in that file.
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

## 10. The defects, worked through (2026-10-12, afternoon and later)

Kept current while the work goes on; each item says **Ran** with what was seen. The list of
what is still open is at the end of this section.

### 10.1 The pole: solved (Ran)

**Cause.** The vector unit's arithmetic was done with the host's numbers. The unit has no
NaN and no infinity - an exponent of 255 is an ordinary exponent - and an exponent of 0 is
zero whatever the fraction says. The game relies on it:

- the trail drawer (entry 0x28 of the main VU1 program) unpacks the points of a weapon
  trail, four signed 16-bit values each, to qwords 0x60 to 0x7f of VU1 data memory
  (`UNPACK` V4-16, 32 rows, absolute address 0x60) - the joint slots 24 to 31;
- in the next frame the pose upload (entry 0x3a, instructions 0x27e to 0x286) writes every
  joint row as `new x weight + old x other weight`, with the weights 1 and 0 for a plain
  pose, reading `old` from the slot itself. A trail point such as -3677 is the bit pattern
  0xfffff1a3: to the host a NaN, and NaN x 0 is NaN. The console computes
  (a large number) x 0 = 0;
- joint 24 so became NaN in two rows, entry 0x0c (pose x transform) spread it over the
  row, and every mesh weighted to that joint (about 30 small two-pass meshes of the
  player's model) got Q = 1 / NaN and positions whose low 16 bits were
  0xf1a3: the far corner the pole ran to.

So it showed only while a weapon trail existed (the fight), and only on models with 25 or
more joints.

**Fix** (`tools/recomp/render/vu1_step.h`): what an arithmetic instruction reads is first
brought into the unit's range (`vu_in`: the largest number for exponent 255, zero for
exponent 0), a result too small to be a number is zero (`vu_out`), `MAX` / `MINI` compare
the bit patterns as sign and magnitude and hand one on unchanged, `DIV`, `RSQRT`, `FTOI`
and `CLIP` read the same way. Results cannot overflow because the unit rounds toward zero
and so does the host while a program runs.

**Seen.** The recorded stream `local/recomp-out/app-test/pole.rtavs` played back: 40
vertices far outside the surface before (the log stops counting at 40), none after. The
script `pole-fixed.rig` (the fight, picture at tick 2,701 of `valor`):
`shots/pole-app.png` before, `shots/pole-fixed.png` after, side by side in
`shots/cmp-pole.png` - the pole is gone, the rest of the picture is the same.
Cost: 1.0 ms more VU1 time a picture in that scene (decoding without the kicks 5.7 ms
before, 6.7 ms after; 762,000 instruction pairs; load average 36).

How it was found: `RTA_GS_FAR=1` now prints the whole input half, the strip and the joint
slots at the first far vertex; `RTA_WATCH=lo-hi` (hexadecimal qwords, `rta_replay`) lists
every VU1 store and every `UNPACK` into a range of data memory with the entry that did it.

What the reference emulator models and this interpreter does not, found on the way
(Read in its source, `Source/ee/VuBasicBlock.cpp`): stalls when an instruction reads a
float register written less than four cycles before (they move the time at which Q and the
flags change), and a conditional branch that tests an integer register written by the
instruction directly before it taking the value from four instructions earlier - except in
the four-instruction store loops at 0x117 and 0x25e, which it exempts by name of the
engine. A scan of the main program (`local/recomp-out/render/work/hazard.py`) finds three
more such branches: 0x084 (particles), 0x1f3, 0x255 (entry 0x34, whose result nothing
reads). None is on the path of a mesh. See 10.2 for whether a scene shows them.

### 10.2 What the first level does not show: a tour (Ran)

**A control socket and a driver for both builds.** `rta_app --control PATH`
(`tools/recomp/app/control.h`) listens on a UNIX socket and speaks the protocol of the
emulator build's control socket (`tools/play-net/ctl.py`: `press`, `release`, `tap`,
`stick`, `wait`, `peek`, `poke`, `shotfb`, `info`, `quit`; one command a line, carried out
on the game's thread at a vertical blank). `tools/recomp/app/tour.py native|emu levels NAME…`
drives either build through the same stops: power-on to the first level, then every level
asked for by writing its name to `g_pendingLevel` 0x41b6d0 (the emulator tours' way), a
picture where the level starts and more with the game's free camera (camera mode 3,
`g_camera` + 0x34) above places spread over the level's chunks; `tour.py sheet` lays the
pictures of the two builds one above the other. `info` gives memory, textures held, made
and freed, draws without their texture, surface copies, and how many primitives were drawn
with each piece of GS state the model only approximates.

**Toured** (20 levels, three pictures each, both builds; `local/recomp-out/app-test/tour2/`,
sheets `cmp-A.png` … `cmp-C.png`): hub, valor, wat1, fire1, fire3, islc1, swamp1, storm1,
nit1, tormenta, fay1, dis2, arachna1, blood1, innovat1, drunare, watg2a, islsm1, honor,
boar1.

| Seen | Native against the emulator build |
|---|---|
| level geometry, textures, point lights, environment-mapped chunks, sky dome (hub), lava (fire1, fire3), light shafts (watg2a), the arena (drunare) | same |
| water: the sea at the beach of islsm1 with its foam; the saw-tooth edge of the water grid at the level's rim is in both | same |
| HUD, level name banner, "Check Point Saved", prompts | same |
| chunks far from the character under the free camera | the emulator build shows holes (background colour) where the native build draws ground: it loads a level's cells as slowly as a console, the native build at once. With `--settle 500` (vertical blanks to wait at a view) the four fire3 views are the same in both, down to an untextured dark triangle the game itself draws there (`tour4/cmp.png`) |
| **heat haze** | was wrong, see below |

**Heat haze: the copy was not carried out.** `particle_drawHaze` 0x18fe18 copies a small
rectangle of the 3-D surface (12 x 6 to 40 x 20 pixels) into a texture with a GS
local-to-local transfer and draws it back displaced as a fan with blend
`(Cs - Cd) x As + Cd`. The model honoured such a transfer only when the destination began
on a page (a multiple of 32 blocks); the haze's destination lies in the middle of texture
memory, so the copy was dropped and the fan drawn without a texture: 15,958 transfers
dropped and 16,709 draws without their texture over the 20 levels (fire3, islc1, fay1,
arachna1, blood1, innovat1, drunare most). Fixed in `tools/recomp/render/gs.cpp`:
surfaces are known by the block they start at (a frame buffer's FBP x 32, or wherever a
copy out of a surface was put), a texture that starts a whole number of pages into a
surface is that surface with an offset as before, and a surface read as a texture of a
format without eight bits of alpha takes its alpha from `TEXA` as such a texture does
(`DrawCmd::texa_mode`; the 3-D surface is 16 bit). After: over 40 level changes 9,849
copies carried out, none dropped. Read in the draw list of a recorded fire3 frame
(`tour3/haze.rtavs`): each copy is followed by its 12-vertex fan sampling the copied
piece.

**The GS approximations of `native-render.md`: counted; one was needed.** Every
primitive is now counted against the state the model does not apply exactly
(`GsStats::approx`): an alpha test with a fail rule other than "keep" (besides "never
passes", which is exact), the destination-alpha test, a blend factor of destination
alpha, `FBA`, `PABE`, fog, `AA1`, a partial `FBMSK`, `COLCLAMP` off, region-repeat
wrapping. From power-on through the front end and the 20 levels none of them is used by
any primitive; in the bag **fog** is (7,200 primitives in a visit: the glow around the
selected item is its model drawn additively with fogging on and the fog colour green),
and without it the glow was white and hid the item. Fogging is now applied
(`DrawCmd::fog`, `Vertex::fog`: after the texture function the colour is
F x colour + (1 - F) x `FOGCOL`, F from `XYZF2` or the `FOG` register). The others were
left as they are, since no scene draws with them; the count stays in the final report
("primitives drawn with GS state the model approximates ... none") so that a scene that
needs one shows up. What also mattered: the local-to-local transfer (above), uploads
straight into a displayed buffer (10.3), and the two things under "screens" below.

**Screens** (`tour.py native|emu screens`; `local/recomp-out/app-test/screens/`,
`cmp-1.png`, `cmp-bag.png`, `cmp-talk.png`): pause menu, options, the bag's six pages
(items, the character in the alcove, statistics, quests, skill tree), the map overlay, a
dialogue with its close-up, the talk prompt. Same as the emulator build after these
three corrections:

| Seen | Cause | Change |
|---|---|---|
| the bag's selected item glowed white and hid the item | fog not applied | above |
| the bag's item pictures showed twice, one copy between the lines of the other | they are 94 x 98 pictures in textures named 128 x 128 whose record carries no block number (+0x18 is 0), so the picture's height was not found and the second field was looked for by the size that was sent, 15 rows too low | a sprite that draws rows 0 to n or n to 2n of such a picture at half a row a line is taken to draw one field of a picture 2n rows high (`gs.cpp`, where field sprites are recognised); `TexIndex::resident_at` also finds records of textures without a palette or with a 16-colour one |
| **from the first dialogue on the whole picture was blurred and all text unreadable** | during a dialogue the game draws into the 3-D surface under the GS's reset scissor (2,048 lines); a surface was "as high as its scissor", so the 3-D surface became 1280 x 2048 and everything after was drawn at a quarter of its lines | a scissor higher than 512 lines leaves a surface's height as it is |

Not reached by the script in either build: the shop's lists.

**Surfaces are freed too.** The shadow surface and the heat haze's piece of the picture
are textures of the game's ring of resident textures; each time the ring hands them
other blocks a surface was made at the new place and the old ones stayed (47 within the
first minutes of a session). A surface nothing has drawn into, sampled, copied or shown
for 600 frames is now given back (`Gs::free_unused_targets`, `FrameList::dead_targets`).

**Draws without their texture that remain** (`RTA_GS_MISSING=1` lists each texture
once): 69 from power-on to the first level - the present pass reading the 3-D surface
before anything was ever drawn into it; and 400 to 600 in a visit of tormenta or blood1
- level strips that name a 1 x 1 eight-bit texture (`TEX0` with TW = TH = 0) whose
palette was sent and whose picture never was. On the console such a strip takes its one
colour from whatever lies at that block; here it is drawn without a texture. No picture
of the tour shows a difference from the emulator build there. (A first suspicion, that
an upload took away neighbouring textures, was real but not the cause: a narrow
rectangle skips blocks in GS memory and the model had counted every block up to its
last one as overwritten; it now takes away only textures that start in a block the
rectangle writes.)

**Textures are freed; memory.** A texture no draw has named for 600 frames is given back
(`Gs::free_unused_textures`, `FrameList::dead_textures`, deleted by the backend;
`RTA_TEX_KEEP=frames`, 0 = never), and a batch buffer that held a level's whole texture
upload (tens of megabytes; three of them go round the picture path) is released instead
of kept (`pipeline.h`). Measured over 40 level changes (the 20 levels twice, unpaced,
`local/recomp-out/app-test/mem2/run.txt`; memory is the process footprint): 428 MB in the
first level, 512 to 586 MB over the first round, 544 to 601 MB over the second; textures
held 166 to 395 (27 to 67 MB as RGBA) whatever the round. So what is held follows the
level, not the number of levels; the second round lies 15 MB above the first on average
(0.75 MB a level change), which is not textures (their count is the same) and was not
traced. Before these two changes the same 20 levels ended at 861 MB.

Not compared with the emulator at the same instant: weapon trails, hit and spell effects
and floor decals in a fight (they are drawn - the pole of 10.1 came from a trail's data -
but the two builds' fights do not stay in step, and no close-up pair was made).

### 10.3 Films (Ran)

**Chosen: the game's own film player on top of a host decoder, replacing Sony's MPEG
library at the seven entry points the player calls - not a model of the Image Processing
Unit, and not a separate host player.** Why:

- The game does not talk to the unit; Sony's library does (bit reading, variable-length
  decoding, the inverse transform and the colour conversion are commands to the unit,
  with data going round through DMA channels 3 and 4 and the answer polled). A model of
  the unit would be a model of that library's private dealings with it, used by nothing
  else in the game.
- The player uses seven library functions and no callback (Read in the disassembly):
  0x3734f0 init, 0x372948 create (mp, work area, size), 0x3735a0 delete, 0x373688 reset
  (zeroes the frame number at mp + 8), 0x3735a8 add stream data (mp, data, size),
  0x373708 "at the end", 0x3735e8 get picture (mp, RGBA macroblocks, count 0x546).
  That is a small, clean boundary.
- The player itself stays the game's code: it reads the stream from the disc in pieces
  into two alternating buffers, builds its own GS upload (one 16 x 16 rectangle per
  macroblock, column after column: `0x31fdf4`), switches the display to one 640 x 448
  buffer and ends the film. A separate host player would have had to redo all of that.

**The parts.** `tools/recomp/app/mpeg2.h`: an MPEG-2 video decoder written from the
standard, standard library only (I, P and B frame pictures with frame prediction and frame
DCT, both coefficient tables, both scans, both quantiser scales, half-sample motion
compensation; field pictures and field prediction are refused and counted).
`tools/recomp/app/film.cpp`: the seven functions (`tools/recomp/app/hle-app.txt` names
them for the translator; only `rta_app`'s translation leaves them open, so the headless
runtime and `rta_app_orig` are unchanged and still end a film at its first picture).
`tools/recomp/render/gs.cpp`: pixels sent straight into a buffer of display size are
collected per buffer and drawn into the surface as one picture when the frame ends
(`Gs::upload_to_surface`, `flush_uploads`): the film's 1,120 rectangles a picture become
one texture and one draw. `rta_app --no-films` gives the old behaviour.

**The films on the disc** (Ran: the stream headers): `PORKO.LMP` holds `porko0.m2v` (60
pictures) and the index `porko.bin` of six pieces of `PORKO.SMG` (350 pictures); all are
MPEG-2 Main Profile, 640 x 448, 29.97 pictures a second, frame pictures with
`frame_pred_frame_dct` = 1, I / P / B in groups of 15, alternate scan, non-linear
quantiser scale, the second coefficient table in I pictures. The sound is the stream
entry `porko_l.vag` on stream 0, played by the sound side like any other stream.

**Seen.**
- The decoder against another decoder (ffmpeg, already on this computer; nothing was
  installed): all 410 pictures of the two streams, display order, 63.8 dB PSNR at worst
  (the difference is rounding in the inverse transform). `tools/recomp/app/mpeg2_test.cpp`
  writes the pictures as raw planes for such a comparison.
- In the application from power-on with no button pressed (`film-test.rig`): publisher's
  logo, then the developer's film from its first to its last picture, then the title
  (`local/recomp-out/app-test/film/sheet.png`, larger `sheet2.png`): 410 pictures from 7
  pieces of stream, no unsupported picture, no slice with an error, 4.5 ms of processor
  time a picture. Whole frames of 640 x 448 (the display is one 448-line buffer during
  the film and is shown whole at every blank): nothing bobs.
- **Pace.** The player does not time the film: its wait for a field (`movie_waitForField`
  0x3201ec) has no caller and its check against the sound stream (`g_movieAudioSync`) is
  never switched on; it decodes one picture in every frame of the loop. On the console
  decoding takes longer than a field, so the loop comes round every second field. Here
  decoding takes no machine time and the film ran at one picture a field, twice its
  speed (and the emulator build does the same: 410 pictures in about 480 fields). The
  get-picture call therefore takes the machine time of a little more than a field
  (`rt_sleep`): one picture every two fields, measured (54 pictures in 108 fields), which
  is the rate the stream is coded for.
- **Sound in step.** At picture 391 (13.05 s of film) stream 0 had played 354,304 bytes,
  12.93 s at the two-voice stream's 27,398 bytes a second.
- Colour against the emulator build's film pictures (same scene, not the same picture):
  average 110, 137, 161 native; 114, 138, 160 emulator.

### 10.4 Sound through level loads (Ran)

Design: `native-sound.md` section 8. In short: paced, with a window, the sound side
(chip, `LIBSD` commands, stream driver and its 6 ms timer) runs on the device's own
real-time thread and clock (`sound-clock=real`, the default output unit asking for every
buffer); the game's calls are carried out when they are made. A run that is not paced
or has no window keeps the sound on the machine's clock (`sound-clock=machine`).

**Gaps over a session with ten level changes** (`tour.py native levels valor wat1 fire1
islc1 swamp1 storm1 nit1 tormenta fay1 dis2 --paced --views 0`, a test window, gain 0;
the computer was shared with other jobs the whole afternoon: load average 280 to 430):

| Sound on | Session | Taken by the device | Nothing to play |
|---|---|---|---|
| the machine's clock (the old way, same build, same session) | 345 s | 344.4 s, of which only 136.7 s had been rendered | 883 times, 5,564 ms of silence (the game itself reached 23.7 pictures a second under that load) |
| its own clock, AudioQueue asking (first attempt) | 243 s | 241.45 s in 24,146 requests | 1 request 0.9 s late: an AudioQueue's callback thread is an ordinary one |
| **its own clock, the default output unit (as built now)** | 294 s | **293.29 s in 27,496 requests** | **none: longest time between two requests 10.8 ms, none more than 30 ms apart** |

In the last, 44 of the game's 28,000 sound calls found the device rendering and waited,
1.4 ms at most; rendering a request took 0.056 ms on average, 0.12 ms at most; the sound
side cost 0.51 % of one processor. Files: `local/recomp-out/app-test/snd1/` (the first
two rows), `snd2/` (the last). The same in the three runs against the rig below: 261 s,
218 s and 386 s without one late request.

**Tick identity with sound attached** (`rta_app_orig`, picture off screen, the fight
session `fight3.rig` of 7,904 fields given the rig's controller bytes, `rigcompare.py
boot-native --replay` then `boot-compare`; a private copy of the rig's log in
`local/recomp-out/app-test/rigsnd/`, wrappers `as-native-*.sh`, `rc.py`):

| Sound on | Simulation columns | Cosmetic seed against the rig |
|---|---|---|
| the machine's clock | identical in all five episodes, as before this work: only the player record at tick 7 of the first level and the object pool in ticks 3,886 to 3,912 of `valor` differ | first level: 35 ticks from tick 60 (the music-start hold); `valor`: from tick 1,218, 2,343 of 5,410 ticks - the same line for line as before |
| its own clock, not paced | the same | first level: none; `valor`: from tick 1,218, 1,847 ticks |
| its own clock, paced by the clock | the same | first level: none; `valor`: from tick 1,218, 4,193 ticks |
| its own clock, not paced, after the runtime's flush-to-zero | the same | first level: 39 ticks from tick 60; `valor`: from tick 1,205, 1,169 ticks |

So **what changed is the cosmetic seed and nothing else**: with the sound side on its
own clock the answers the game reads back (voice end flags every 8th sound frame, stream
positions) depend on when in real time it asks, the cosmetic generator is drawn from
when sounds start and end, and the number of ticks at which it differs from the rig is
different in every run (1,169 to 4,193 of 5,410) where it was the same every time on the
machine's clock. No simulation column follows it. A run that has to be the same twice
(a comparison, a recording) uses `-- --opt sound-clock=machine`.

**The runtime's arithmetic** (asked for by the coordinator while this was running):
the game's threads now flush denormals to zero besides rounding toward zero
(`rt/runtime.cpp`, `thread_main`; `native-recomp.md`, status). The machine-clock
comparison above was repeated with it: the same line for line. `--opt arith=nearest`
sets neither (the host's own arithmetic), `RTA_SOFT_RZ` leaves the processor's mode
alone for a build that does it in software; a line at the start of a run says which is
in force.

### 10.5 to 10.7: state of the work at 15:45 (saved before a possible stop)

Done and written above: the pole (10.1), the tour with its corrections (10.2), films
(10.3), sound (10.4). The tree builds: `python3 tools/recomp/app/build.py` (and
`--original`), `python3 tools/recomp/render/build.py replay`.

**Running when this was written** (background chain `local/recomp-out/app-test/final.sh`,
then `final2.sh`; results go to the files named, nothing else needs to be kept):

- press-to-picture latency: `app latency BUTTONS [pictures [before]]` / `app latency
  report` in `app_main.cpp` (a press put on port 1 at one controller read; every
  presented picture reduced to a 40 x 28 grid of brightness; the first that differs from
  its predecessor by more than three times what the pictures before the press differed).
  Helper `local/recomp-out/app-test/perf/latency.py` (title menu, an attack in the first
  level, the pause menu); output `perf/latency.txt`. To compare with the emulator
  build's figure in `tools/play-net/README.md` ("in a menu the first picture after a
  press shows the change ...; in the first level an attack shows in picture 5 or 6").
- speed and pacing: `perf/perf.py find LEVELS` (pictures a second not paced at 640 x 448
  per level: the lowest is the heaviest), `size LEVEL 2560x1792` and `2619x1964`, `paced
  LEVEL 2560x1792` (1,800 blanks, then `app stats`); output `perf/find.txt`, `size.txt`,
  `paced.txt`. Quote the load average beside every figure: it was 280 to 430 all
  afternoon, so the figures are a floor, not the program's speed.
- the screens tour again with all corrections: `screens2/cmp-1.png`, `cmp-2.png`.
- memory over 40 level changes with surfaces freed as well: `mem3/run.txt` (before that
  change: 428 MB in the first level, 512 to 601 MB over two rounds of 20 levels; without
  freeing textures 1,068 MB and 2,782 textures after one round, `snd1/keep0.txt`).

**Not done:**

- a close-up comparison of weapon trails, hit and spell effects and floor decals with
  the emulator build (helper written, not run: `local/recomp-out/app-test/fx/fx.py
  native|emu` - swings in the first level at the near zoom, paused pictures);
- the shop's lists (the script's route did not open the shop in either build);
- a film compared picture for picture with the emulator build (it plays the film at
  about twice its coded rate, so only the colour was compared);
- the stalls and the integer branch hazard of VU1 that the reference emulator models
  (10.1, last paragraph): no toured scene showed a need;
- the 1 x 1 textures whose picture is never sent (10.2);
- a listening test: no sound was made at any point (gain 0 in every run);
- the 15 MB by which the second round of 20 levels lay above the first (10.2) - to be
  read again from `mem3/run.txt`, since surfaces that were never freed are a likely
  cause.

**Partial results, 15:55** (the chain was stopped when the graphics work was merged into
the shared tree; these are from the build before that merge, load average 217 to 300):

- Press to picture, paced, `perf/latency.txt`: an attack in the first level (cross)
  shows in the picture of the 6th, 7th, 7th and 9th blank after the one whose controller
  read was given the press (the emulator build: picture 5 or 6); the pause menu (start)
  in the 5th, twice. In milliseconds 157 to 295 from the press to the present - but the
  application reached only about 28 pictures a second under that load, so the
  milliseconds say nothing about the program. The title menu's move (down / up) was not
  detected by the test: the measure was the mean difference over the whole grid and the
  title's moving backdrop is larger than a moved highlight. To do: the largest
  difference of a cell in place of the mean, and the move inside the pause menu.
- Pictures a second, not paced, 640 x 448, by level (`perf/find.txt`): valor 36, fire3
  21, arachna1 20, islc1 77, honor 67, swamp1 103, drunare 82. So arachna1 and fire3 are
  the heaviest of those toured (many heat-haze copies a frame, each a blit between
  surfaces in the middle of the frame). The runs at 2560 x 1792 and at the display's
  resolution were made in the wrong place by a mistake in the helper (it handed the time
  of day on as the level's name) and are **not** figures for the heaviest level: 73 and
  90 pictures a second in the first level, load 364 and 295. To do again:
  `perf.py size fire3 2560x1792`, `size fire3 2619x1964`, `paced fire3 2560x1792`.

### 10.8 The merged tree (graphics work merged 15:46 by the coordinator): verified (Ran)

`local/recomp-out/app-test/merge/verify.sh`, results under `merge/`. `rta_app`,
`rta_app_orig` and `rta_replay` build from the merged tree (16 more addresses in
`hle.txt`: both translations made and compiled again).

| Check | With the new defaults (aspect auto, 4 samples, anisotropy 16, mip maps) | With `--plain` |
|---|---|---|
| the fight session against the rig's log (`rta_app_orig`, sound on the machine's clock) | the same as before the merge, line for line (compared as text with the result of 10.4) | the same, line for line |
| the pole (picture at tick 2,701 of `valor`) | none (`merge/check-default.png`) | none (`check-plain.png`) |
| films from power-on with no button pressed | 410 pictures, no unsupported picture, no slice with an error | the same |
| heat haze (fire3, islc1) | 3,483 copies carried out, none dropped, no new draw without its texture | 3,450, none dropped |
| bag: item glow (fog) and item pictures | green glow, clean pictures | the same |
| dialogue and the picture after it (the quarter-height fault) | text readable; the 3-D surface stays 1280 x 448 (`RTA_GS_LOG`) | the same |
| sound through ten level changes, paced | 132.07 s taken in 12,382 requests, longest time between two 10.7 ms, none late | not run again |

**What the merge broke: nothing that these checks show.** Found on the way, and mine,
not the merge's: every film picture is a texture of its own (the player sends the
picture to texture memory and draws it with one sprite; the upload path of 10.3 for
pixels sent straight into a displayed buffer is not what this film uses), and a texture
was kept until 600 frames had passed without it: 330 film pictures, 577 MB, at the
peak of the intro film, gone again some seconds into the title. Textures now have a
budget (`Gs::texture_budget`, 96 MB of RGBA): above it the ones not used in this frame
or the one before are given back first, oldest first.

(`RTA_GS_FAR` cannot be used to look for the pole in a whole session: its 40 lines are
used up at power-on by a row of sprites drawn at an offset of zero. The picture was
looked at instead.)

**Pacing in that paced session** (ten level changes, load average falling from 100 to
40): 8,180 pictures in 132.7 s; of 8,179 intervals 8,154 (99.7 %) stood exactly 2
refreshes of the 120 Hz display, 8 stood 3, 17 longer (the level loads; longest 138 ms).

**After that**, as the coordinator asked: `tools/recomp/web/shared-sources.patch` applied
(`rt/fpu.h`, `rt/vu0.h`, `render/vu1_step.h`, `render/vu1.cpp`, `sound/audio_out.cpp`;
it changes nothing unless `RTA_SOFT_RZ`, `RTA_SOFT_RZ_VU1` or `__EMSCRIPTEN__` is
defined), the start-up line about the arithmetic corrected for WebAssembly, everything
built again and the rig comparison repeated: `merge/rig-final-compare.txt` (see the last
lines of this file for the result).

### 10.9 Final figures and what is left (2026-10-12, 20:30; this replaces the "state of the work" and "partial results" above)

Everything below is from the final build (`rta_app` of 16:13 from the merged tree, with
the web agent's `shared-sources.patch`, the texture budget and, since 19:55, a lower
threshold in the latency test), default picture settings unless `--plain` is said. The
computer was shared the whole time; the load average is beside every figure and was
never low while a measurement ran (the 17 of 19:50 lasted minutes), so **the speeds are
floors under load, not the program's speed**; the counts (pictures after a press,
requests of the sound device, textures, megabytes) do not depend on it.

**The rig comparison after the last source change** (`merge/rig-final-compare.txt`,
`--plain`, sound on the machine's clock): the same as before the merge, line for line.
The final build's own checks again: no pole, bag and dialogue right
(`merge/check-final.png`); the intro film now holds 96 to 112 MB of textures while it
plays (577 MB before the budget), 545 to 575 MB of memory in all.

**10.5 Speed, pacing, memory.**

| What | Figure | Load average |
|---|---|---|
| not paced, 640 x 448, by level (`perf/find3.txt`) | valor 22, fire3 61, arachna1 75, islc1 54, honor 20, swamp1 15, drunare 32 pictures a second; four hours earlier (`find.txt`): 36, 21, 20, 77, 67, 103, 82 - the order follows the load, not the level | 269 to 349; earlier 217 to 289 |
| fire3 (heat haze: the most surface copies a frame), not paced, 2560 x 1792 | 28 and, with `--plain`, 32 pictures a second; earlier 88 | 237, 113; earlier 135 |
| fire3, not paced, the display's 2619 x 1964 | 88; earlier 55 | 219; earlier 92 |
| arachna1, not paced, 2560 x 1792 | 77 | 134 |
| fire3 paced at 2560 x 1792, 1,800 blanks (`perf/paced3.txt`) | 50.8 pictures a second; of 1,804 intervals 1,251 stood 2 refreshes of the 120 Hz display, 512 stood 3, 39 stood 4, 2 stood 5; longest 40 ms; no restart after a stall | 119 |
| the same session: processor time | 18.6 ms a picture over all threads; decoder 11.7 ms of its own processor time (VIF1, VU1, GS model); game side 8.0 ms and decoder 26.6 ms of wall time, main thread 8.6 ms in OpenGL and the swap; 195,000 vertices and 761 draws a picture | 119 |
| the same session: sound | 149.9 s in 14,055 requests, longest time between two 10.9 ms, none late | 119 |
| ten level changes paced, 640 x 448 (10.8) | 99.7 % of 8,179 intervals exactly 2 refreshes | 100 falling to 40 |
| memory over 40 level changes, final build, default picture (`mem3/run.txt`) | 600 MB in the first level; first round of 20 levels 695 to 895 MB, second round 613 to 780 MB: **the second round is not above the first**; textures held 169 to 408 (as in every earlier tour); 21,536 heat-haze copies, none dropped | 144 at the end |
| the same before surfaces were freed and before the merge (`mem2`) | 428 MB first level, 512 to 586 then 544 to 601 MB (second round 15 MB above the first) | 380 to 500 |
| without freeing textures, one round (`snd1/keep0.txt`) | 1,068 MB, 2,782 textures (486 MB) | 380 |

The one figure that says what the program costs is the processor time: about 12 ms of
decoder time a picture in the heaviest scene found, so the decoder alone allows some 85
pictures a second there on a free machine; that could not be shown, because the machine
was never free. The default picture (4 samples, mip maps) holds about 170 MB more than
`--plain` (600 against 430 MB in the first level).

**10.6 Press to picture** (`app latency`, paced, `perf/latency3.txt`; the count is in
vertical blanks from the controller read that was given the press to the picture that
first shows a change, so it does not depend on the load; the milliseconds do, load 320):

| Press | First changed picture | Milliseconds to its present |
|---|---|---|
| a move in the pause menu (down / up; a still picture, so the first change of any cell counts) | the 7th blank after the press, four times out of four | 170 to 178 |
| the pause menu opens (start) | the 5th | 142 |
| an attack in the first level (cross; found against the idle animation's own movement) | the 6th, 9th, 9th, 6th | 162 to 327 |
| a move in the title menu | not found: the moving backdrop changes cells more (12 to 16) than the highlight does | |

The emulator build's figure (`tools/play-net/README.md`): "in a menu the first picture
after a press shows the change"; "in the first level an attack shows in picture 5 or 6
(82 to 104 ms)". For the attack the native application is therefore about one picture
later (6 where the emulator has 5 or 6; the two 9s are the detection waiting for the
swing to outgrow the idle movement). That one picture is the runtime handing the pad
state to the game one blank after it was read (`pad-delay`, as the console and the rig
do; `--opt pad-delay=0` hands it over at once). For the menu the two figures do not
measure the same menu: the emulator's was a front-end menu, this one the pause menu,
which answers a held direction two blanks later than it answers start. Running the
emulator's own `latency.py` in the same two scenes was tried (`perf/emu_latency.py`) and
did not finish in 14 minutes at a load of 220; it was stopped. In wall time the picture
path adds its two hand-overs (game to decoder, decoder to the window) to the count; with
the application reaching 50 pictures a second instead of 60 under this load the
milliseconds above are an upper bound.

**10.7 Trails in both builds** (`fx/fx.py native|emu`, `fx/cmp-swing.png`): six swings in
the first level at the near zoom, the game paused for each picture. Both builds draw the
swing's trail as the same faint translucent arc behind the weapon; the two do not stop at
the same phase of the swing, so it is the same kind of picture, not the same picture.

**Left, in the order a release would want it:**

1. Speed on a free machine (the three `perf.py` lines above), and the emulator's
   `latency.py` in the pause menu and for the attack, for a like-for-like count.
2. Hit and spell effects and floor decals against the emulator close up (only the swing
   trail was paired); the shop's lists (the script's route opens the dialogue but not the
   shop, in both builds).
3. A film compared picture for picture with the emulator build (it plays the film at
   about twice its coded rate; colour and decoder were compared, 10.3).
4. The level strips that name a 1 x 1 texture whose picture is never sent (10.2): drawn
   without a texture here.
5. VU1's stalls and the integer branch hazard the reference emulator models (10.1): no
   toured scene needed them.
6. A listening test: every run was silent (gain 0).
7. Unchanged from section 8: the two unexplained differences from the rig (player record
   at tick 7 of the first level, object pool in ticks 3,886 to 3,912 of `valor`; they are
   not denormals, 10.4), the real controller, Windows, the application bundle.

**How to repeat** (all under `local/recomp-out/app-test/`, `RTA_DISC` set):

```
python3 tools/recomp/app/build.py && python3 tools/recomp/app/build.py --original
P=python3   # one with numpy and Pillow for the tour's level plans and sheets
$P tools/recomp/app/tour.py native levels fire3 islc1 --out local/recomp-out/app-test/t/native --views 2
$P tools/recomp/app/tour.py emu    levels fire3 islc1 --out local/recomp-out/app-test/t/emu --views 2 --settle 500
$P tools/recomp/app/tour.py sheet  local/recomp-out/app-test/t/cmp.png local/recomp-out/app-test/t/native local/recomp-out/app-test/t/emu
$P tools/recomp/app/tour.py native screens --out local/recomp-out/app-test/s/native
$P tools/recomp/app/tour.py native levels valor wat1 fire1 islc1 swamp1 storm1 nit1 tormenta fay1 dis2 \
     --out local/recomp-out/app-test/snd/real --views 0 --paced          # sound through ten level changes
local/recomp-out/bin/rta_app --test "films" --window 320x240 --size 640x448 --unpaced \
     --data local/recomp-out/app-test/d --script local/recomp-out/app-test/film-test.rig
sh local/recomp-out/app-test/merge/verify.sh                             # the rig comparison and every correction, default and --plain
```

## 11. The merged program, paced (2026-10-12, night; kept current as the work goes on)

Owner of `tools/recomp/rt`, `render`, `app`, `sound` from 22:40. Helpers and results of
this section: `local/recomp-out/app-test/s11/` (nothing of it is in the repository).
Every statement says **Ran** or **Read**. What `bin/rta_app` is now: 11.8; what is left: 11.9.
(There is no 11.4: its state note was replaced by 11.8.)

### 11.1 The merged tree, rebuilt and verified (Ran, 22:46 to 23:02)

`python3 tools/recomp/app/build.py --as rta_app_next` (and `--original --as
rta_app_orig_next`): the tree with the speed work (`native-render-speed.md`; the
translator's `local/recomp-out/gen-vu/vu1_fast.cpp` is picked up) and the shared socket
layer (`net/sock.h`). 34 s. Two things about the build itself:

- `app/build.py --as NAME` makes the program under another name in `bin/` (it must lie in
  `bin/`: it finds the workspace from there), and every link is now made beside its place
  and moved over it, so a copy somebody is starting never sees a half-written file. A
  build that is to be checked first is made as `rta_app_next` and moved over `rta_app`
  afterwards.
- **The fix set is not the one of this afternoon.** `patches/SLUS-20973_4028A55F.pnach`
  was changed at 22:30 by other work; the translator now reports "patched: 91 words of 26
  sections" (90 until then) and the program announces patch set 27f61e1d with 91 words
  online (3f5b1e14 with 90 before). Every build made from now on has it; a copy built
  before 22:30 and one built after are warned about each other in a lobby room.

Checks, all against the candidate before it became `bin/rta_app`:

| Check | Result |
|---|---|
| the fight session against the rig's log, controller rows replayed (`s11/rig.sh`: `rta_app_orig`, picture off screen, sound on the machine's clock): `--plain` with the fast renderer; `--plain` with `RTA_VU1_INTERPRET=1 RTA_GS_SLOW=1 RTA_VIF_SLOW=1`; default picture with the fast renderer | all three the same file as `merge/rig-final-compare.txt`, byte for byte (`cmp`) |
| pictures at 11 simulation ticks (`s11/det.sh`: the speed work's tick-keyed route with seven more pictures in the fight in `valor`; 1280 x 896, no window): fast renderer, reference switches, and the previous program (`rta_app` of 19:52), each with the default picture and with `--plain` | 11 PNG files the same three ways, both settings (`s11/detcmp.py`) |
| **the 20-level tour as a script** (`s11/mktour.py`, `s11/tour.sh`: the stops of `tour.py levels` - where the level starts and two views with the free camera - but every step counted in vertical blanks by the machine instead of sent over a socket, so that two runs make the same pictures): fast, reference, previous program; default picture, 640 x 448 | 60 PNG files the same three ways. (The socket-driven `tour.py` cannot give this: the blanks between two of its commands depend on the wall clock.) 5,534 textures made, 5,278 freed, 1,253 draws without their texture, 49 transfers inside GS memory not carried out, no approximated GS state - the same figures in all three |
| two copies of the window program through this computer's lobby into one game (`lobbypair.py run s11/online/pair-next --host window --join window --play 1800 --level drunare --play2 1800`, `RTA_NATIVE_APP` the candidate; new accounts, new characters, throw-away names) | 4,830 ticks compared through the level change into `drunare`: "no shared column differs on any tick"; the game's own checksum exchange agreed (expected = received, `g_checksumFailed` 0) on both; each copy saw the other's patch set as its own; 161 s |

The session to the fight (5,307 blanks, 1280 x 896, default picture, no window, load 30
to 60): the previous program 144 pictures a second and 8.8 ms of processor time a picture
over all threads (decoder 5.5 ms); the merged one 285 and 5.6 ms (decoder 1.85 ms); on the
reference switches 105 and 11.0 ms (decoder 8.1 ms).

With that `bin/rta_app` **is** the merged build (23:02; `bin/rta_app.merged` is a copy of
it). `bin/rta_app.prev` is the program of 19:52 that was there before, `rta_app_orig.prev`
likewise. `rta_replay` rebuilt.

### 11.2 Pacing (Ran, 23:02 to 23:50)

**The display of this computer was asleep the whole night** (`CGDisplayIsAsleep` 1; nobody
had touched it for three hours), and so it was during the evening's measurements of the
other work: a swap asked of a sleeping display returns at once (0.3 to 0.7 ms), no picture
waits for a refresh, and every interval quoted tonight - here and in
`native-render-speed.md` - is the program's own clock, not the glass. I did not wake the
display. What a lit display does to a swap is stood in for by a test aid (below); **the
first run on the lit display is the owner's**, and the last lines the program prints
(`pacing:` and `path:`) say how it went.

**Where the merged program stood** (`s11/pace.sh base-448`: the session of
`s11/mkpace.py` - first level standing, fire3 standing, fire3 fighting -, 640 x 448 in a
small test window, 4 samples, anisotropy 16, art pack; load average 14 to 16): 60.4 to
63.0 pictures a second; 2,998 of 3,000 intervals 2 refreshes. Two things in it:

- it ran **up to 5 % fast** (63.0 a second standing in the first level): a picture that
  arrived within 1.5 ms of its time was taken as on time and the next period counted from
  there;
- the game's pace was whatever the window's thread let through: game, decoder and window
  each held a finished picture for the next, so a press was read while three pictures
  were still on their way, and a swap that waits long holds the game, its sound and a
  lockstep partner back with it.

**Who waits for whom** (the figures `app stats` and the final report now print, per
picture: `path:`). In the merged program the decoder waited for the window's thread for
most of every period (it handed a list over only when the picture before had been
swapped), and the game waited for the decoder the same way: no part was short of time, the
waiting was the pacing. Per picture in the fire3 fight at 640 x 448: game side 1.9 to
2.3 ms, decoder 3.5 to 4.2 ms, OpenGL 2.1 ms of calls and 4.1 ms to `glFinish` (the
graphics card's time: it used to be hidden in the swap), swap 0.3 to 0.4 ms when the
card has finished before it is asked.

**What it is now** (`app/pipeline.h` `Pacer`, `app/app_main.cpp` `Screen`):

- **The game is let go by a clock**, one frame per period, `lead` before the moment its
  picture is due. `lead` is what game + decoder + OpenGL (to `glFinish`) lately took - the
  third longest of the last two seconds, with what the game's thread woke late by, without
  the time a list stood behind the picture before it - plus a margin (half a refresh and
  a millisecond where swaps are asked for inside the last refresh; 2.5 periods at most).
  A picture arrives just before it is shown instead of waiting in two hand-overs.
- **The moments are a grid** one period apart. Where the swap waits for the display, the
  grid is moved toward the times the swaps return at (a tenth of the difference per
  picture, half a millisecond at most); whether swaps wait is found out from how long
  they take (2.5 ms or more when asked 3 ms or more before the moment: six more of those
  than of the others). Where they do not wait the grid is the clock's and a picture is
  held to its moment by the clock: exactly 60.000 a second on this 120 Hz display.
- **No thread waits for another across a swap.** Lists go from the decoder to the
  window's thread through a queue of three; a picture that is overtaken (the one behind
  it is due as well) is drawn and not shown. A swap that takes long makes that picture
  late and nothing else.
- **The controller is read after the wait**, not before it (`rt/runtime.cpp`
  `on_vblank`: the picture sink is called before the controller is read; the sink touches
  nothing of the machine).
- The picture's threads and the game's ask for the user-interactive class
  (`pthread_set_qos_class_self_np`; `rt/host.h` `interactive_threads`), and the process
  tells the system its timers matter (`NSActivityLatencyCritical`,
  `app/pad_mac.mm` `keep_timers`; it does not keep the display awake).
- `--pacing queued` is the old way (same program), for comparing.
- Test aids: `RTA_FAKE_DISPLAY=HZ[,PPM[,PHASE_MS]]` - every swap waits for the next
  refresh of a display that is not there; `RTA_PACE_LOG=1` - a line per picture.

**Figures** (`s11/pace.sh`; small test window; 4 samples, anisotropy 16, art pack on;
the computer was shared - load average beside each; processor time does not depend on it):

| Session part | Picture drawn at | Intervals (refreshes of the 120 Hz display) | Pictures a second | Path: game / decoder / OpenGL to `glFinish`, ms | Let go ahead | Processor time a picture: all / decoder / window's thread / rest | Load |
|---|---|---|---|---|---|---|---|
| first level, standing (600) | 640 x 448 | not kept apart in this run | | | | | |
| fire3, a fight (900), no display | 640 x 448 | 2: 899 of 899; longest 17.9 ms | 60.000 | 1.9 / 3.5 / 4.1 | 16.6 ms | - | 15 to 19 |
| fire3, a fight (1,800), the display that is not there (120.036 Hz) | 640 x 448 | 2: 1,789; 1: 5; 3: 5 (five pictures one refresh late, all in OpenGL) | 60.018 (the display's) | 2.2 / 4.0 / 4.1 | 20.7 ms | - | 23 to 28 |
| first level, standing (600), no display | 2619 x 1964 | 2: 599 of 599; longest 17.9 ms | 60.000 | 1.9 / 3.3 / 6.0 | 23.1 ms | 8.7 / 3.3 / 3.0 / 2.4 ms | 17 to 20 |
| fire3, standing at its start (600) | 2619 x 1964 | 2: 598; 3: 1; longest 23.3 ms | 60.000 | 1.7 / 3.4 / 8.7 | 24.5 ms | 12.3 / 3.4 / 5.6 / 3.3 ms | 20 |
| fire3, a fight (1,800) | 2619 x 1964 | 2: 1,799 of 1,799; longest 19.4 ms | 60.000 | 2.3 / 4.2 / 6.1 | 24.3 ms | 10.3 / 4.2 / 3.0 / 3.2 ms | 20 |

(The whole session, power-on and level loads included, has the late pictures a load
makes: at the display's resolution 2,760 of 2,790 intervals 2 refreshes from power-on to
the first level.) 2619 x 1964 is the display's height at 4:3. Files: `s11/pace/a2-448`,
`fake-448`, `a3-1964` (`out.txt`).

### 11.3 Input delay (Ran, 23:45 to 23:55)

**Where the blank was**: `rt/iop.cpp` `pad_sample` handed everything the pad source
answered to the game one blank later (`g_pad_delay`, as the console's I/O processor and
the rig do). Now only what the **script** holds is delayed (so a script still presses on
the same tick here and in the rig); the rest of the answer - keyboard, controller, the
control socket, the latency test's press - is in the game's buffer at the blank it was
read at. The runtime tells the two apart itself (a button is the script's when the script
holds it too), so no pad source had to change (`net/online.cpp` wraps the application's
and still sees and masks every button). `--opt pad-live-delay=1` gives the delay back.
Replayed controller rows (`pad-replay`) replace both, as before: the rig comparison is
the same file as before, byte for byte (11.5).

**Counted again** with the method of 10.9 (`s11/latency.py`: `app latency`, paced, the
same program both ways in the same minutes, load 19; "old way" is `--pacing queued --
--opt pad-live-delay=1`):

| Press | Old way: first changed picture / ms to its present | Now |
|---|---|---|
| the pause menu opens (start) | the 5th blank after the press / 125 ms | **the 4th / 62 to 67 ms** |
| a move in the pause menu (6 each) | the 7th, six times / 155 to 162 ms | **the 6th, twelve times of twelve / 94 to 101 ms** |
| an attack in the first level (cross; 8 and 16 presses) | 6, 8, 9, 8, 9, 9, 9, 11 / 139 to 223 ms | 5, 8, 5, 9, 8, 8, 8, 6 and 6, 8, 8, 6, 10, 8, 10, 7 / 78 to 165 ms |

The emulator application's figure (`tools/play-net/README.md`): an attack in picture 5 or
6, 82 to 104 ms. The native program's earliest is now the 5th (78 and 82 ms) where it was
the 6th; the later counts are the test waiting for the swing to outgrow the idle
movement, in both columns. One blank less in the count is the pad delay; the rest of the
60 ms is the pictures that no longer wait in the hand-overs and the controller being read
after the wait. Not done: the emulator's own `latency.py` in the same scenes (a release
agent owns the emulator copies tonight).

### 11.5 The two known faults (Ran)

**(a) Controller replay through a level load: fixed** (`rt/iop.cpp` `replay_step`).
At a blank where the tick stands at T the replay hands over the other machine's next row
of tick T if it has one, else the first row of tick T + 1. While a level loads, the frames
shown are the loading screen's (its own thread, `loadscreen_renderLoop` 0x32187c; flag
`g_loadscreenActive` 0x506094), and the rig showed three to eight times as many of them
as this machine: the last blank of the load got one of the rig's loading rows, and the
level's first tick read it. Seen blank by blank (`RTA_REPLAY_LOG=1`): the first level
stands at tick 0 for 38 blanks, then 59 with the loading screen up, and the blank after
those is already tick 1; `valor` 6, 46, tick 1. So: **at a blank at which the loading
screen is up, the row handed over is the next tick's first.**

- The fight session against the rig's log: the same file as before, byte for byte (no
  loading row differs from its first-tick row there).
- With the stick made to be held from the first tick of `valor` on in the rig's log
  (`s11/replaytest.py`: a level entered with input held, the case of `native-proof.md`
  3b.3): the old lookup gives the game other controller bytes at tick 1 than the rig's
  row (10 rows of the tick log differ); the new one gives the tick log, byte for byte
  (md5), that the old one gives with the proof work's `first_tick_fix` applied to the
  replay file - and the same again with `first_tick_fix` applied on top of the new
  lookup. **The workaround in `tools/recomp/proof/cmp.py` can go** (it needs
  `bin/rta_proof` built again from `rt/iop.cpp` as it is now; `session.py NAME native
  --no-first-tick-fix` on `h6`, `s2`, `s3` is the check in the proof work's own
  sessions, which I did not run: that program is the proof work's).
- **Not for the front end's own level** (`intro`, the title's backdrop). After its load
  the front end runs ten frames of its own before tick 1, and they have to see what they
  saw on the rig: tried with the rule on (Ran), a button the rig held through that load
  becomes a button pressed anew after it and the front end goes another way from tick 222
  (cosmetic seed, pool, tasks). So in that one episode the controller bytes of ticks 1
  and 2 still differ from the rig's as they always did (`pads`, `padraw`, 2 of 1,383
  ticks), with every simulation column identical. A notice over a level before its first
  tick is likewise followed by the rows of the standing tick, as before.
- The report line of a replayed run now says at how many blanks of a load the first-tick
  row was handed over where the rig's loading row held something else.

**(b) `cur_path` after a texture is sent again: a fault with a visible effect; fixed in
one place for both paths** (`render/gs.cpp`, where `rebuild_state` calls
`restore_texture`). The texture comes back as GIF data of path 3 in the middle of the
VU1 packet being read, and the path was not put back: the rest of that packet was (1)
marked as built on the CPU (`DrawCmd::made_by` 1), which keeps the backend from asking
for the mip-mapped picture of that texture until another draw names it, and (2) **in a
wide picture taken for part of the 2-D layer** (`layout.primitive`, the moved scissor):
for one frame a piece of the 3-D scene is laid out as interface art. It happens whenever
a texture that was given back (unused for 600 frames, or the budget) is drawn with again.
`triangle_run` reads the path after the state is made, exactly as `kick()` does, so
putting the path back at the one call corrects the fast path and the reference together;
their lists stay the same bytes.

### 11.6 The picture path's copies and the OpenGL thread (Ran)

| Change | Where | What it gives (two copies of the session side by side at 2619 x 1964, same load, 45) |
|---|---|---|
| the words of a DMA transfer are put together in one kept buffer instead of one allocated, grown and freed per transfer (20 to 60 a frame, 4 to 5 MB) | `rt/runtime.cpp` `dma_start` | game side 2.07 to 1.71 ms a picture standing in the first level, 2.99 to 2.74 ms in the fire3 fight |
| a draw sets only what differs from the draw before (uniforms, texture, sampler, depth, masks, blend, scissor) | `render/backend_gl.cpp` `execute` | the window's thread 3.07 to 2.80 ms of processor time a picture (first level), 3.84 to 3.72 (fight) |
| a copy out of the multisampled 3-D surface (heat haze: about ten a frame in fire3) resolves the rectangle it copies, not the whole surface | `render/backend_gl.cpp` `resolve_part` | the window's thread 7.24 to 6.78 ms at the start of fire3; the graphics card's share could not be told apart with two copies sharing the card |
| `glFinish` before the wait for the swap, the window's copy drawn before it | `app/app_main.cpp` | the swap itself 0.3 to 0.6 ms: the card's time is counted where it is spent |

What is left in the path, by size (fire3, 2619 x 1964): the window's thread still spends
3 to 7 ms of processor time a picture, about 9 microseconds a draw command - the cost of
a draw call itself in Apple's OpenGL, which only fewer draws (the GS model merging more,
or texture arrays) would lower - and `prepare_pictures` walks every vertex of every
textured draw each frame for the art pack's parts (195,000 to 330,000 divisions); the
vertex list is handed to the card with one `glBufferSubData` (6 to 10 MB); the sink still
copies each transfer once into the frame's batch (the decoder's own thread needs it to
outlive the game's frame).

### 11.7 The morning of 2026-10-13: where it was cut, the quiet machine, the display link (Ran, 07:26 to 07:50)

**Cut off at 23:59 with nothing half-way**: `bin/rta_app` was candidate c2 (checked,
11.2 to 11.5), candidate c3 (11.6 and the `cur_path` correction) had passed
`s11/verify.sh` at 23:59 and not been put in place, the Windows chain had ended at 23:58,
no process of mine was left. Since then `net/netdrv.cpp` and `netdrv.h` were changed by
the network work, and copies of object files named "c_003 2.o" (a file synchroniser's)
appeared beside the game's objects in `obj-rta_native_fix`, `obj-run`, `obj-app` and
`win/obj-clang`: the link took them for objects and failed on duplicate symbols.
`app/build.py` and `app/build_win.py` now take objects and generated files by their own
names only. The stray files (and `bin/rta_app 2`) are not mine and were left.

**The display was lit and the machine quiet** (load average 5 to 10) from 07:26: the
figures of 11.2 and 11.3 again, `s11/pace.sh q-448`, `q-1964` (candidate c4: c3 with the
network work's files), 4 samples, anisotropy 16, art pack on:

| Session part | Drawn at | Intervals (refreshes of the 120 Hz display) | A second | Game / decoder / OpenGL to `glFinish`, ms | Let go ahead | Processor time a picture: all / decoder / window's thread / rest | Load |
|---|---|---|---|---|---|---|---|
| first level, standing | 640 x 448 | 2: 599 of 599; longest 16.7 ms | 60.000 | 1.0 / 1.8 / 2.6 | 11.7 ms | 4.57 / 1.80 / 1.50 / 1.27 ms | 8 |
| fire3, standing at its start | 640 x 448 | 2: 599 of 599; longest 20.0 ms | 60.000 | 0.8 / 1.8 / 5.3 | 15.0 ms | 6.39 / 1.79 / 2.93 / 1.67 ms | 7 |
| fire3, a fight (1,800) | 640 x 448 | 2: 1,799 of 1,799; longest 20.0 ms | 60.000 | 1.1 / 2.2 / 3.7 | 15.5 ms | 5.44 / 2.21 / 1.52 / 1.70 ms | 6 |
| first level, standing | 2619 x 1964 | 2: 593; 1: 3; 3: 3; longest 22.4 ms | 60.000 | 0.9 / 1.7 / 6.6 | 16.0 ms | 4.37 / 1.70 / 1.49 / 1.17 ms | 5 |
| fire3, standing at its start | 2619 x 1964 | 2: 598 of 598; longest 19.2 ms | 60.000 | 0.8 / 1.8 / 8.3 | 18.5 ms | 6.42 / 1.79 / 2.90 / 1.72 ms | 7 |
| fire3, a fight (1,800) | 2619 x 1964 | 2: 1,788; 1: 5; 3: 5; longest 23.0 ms | 60.000 | 1.1 / 2.2 / 7.2 | 18.5 ms | 5.50 / 2.20 / 1.54 / 1.75 ms | 6 |

The eight late pictures at the display's resolution were each a swap that took up to
10 ms (0.4 ms otherwise) asked half a refresh before the moment. So on a quiet machine a
picture costs **4.4 to 6.4 ms of processor time** in the heaviest level found (it was
18.6 ms in 10.9, 8.1 to 9.4 ms in the merged program last night under load), and the
path from letting the game go to a drawn picture is 5 to 11 ms.

**Press to picture on the quiet machine** (`s11/latency.py q-old`, `q-new`; load 12 to
14; the same program both ways):

| Press | Old way (`--pacing queued -- --opt pad-live-delay=1`) | Now |
|---|---|---|
| the pause menu opens (start) | the 5th blank / 133 ms | **the 4th / 59 ms** |
| a move in the pause menu (6 each) | the 7th, six of six / 165 to 167 ms | **the 6th, six of six / 91 to 95 ms** |
| an attack (cross, 8 each) | 6, 9, 9, 7, 11, 9, 8, 8 / 150 to 232 ms | 5, 6, 8, 8, 9, 9, 8, 8 / 75 to 142 ms |

**A swap does not wait for the display on this system, lit or not** (0.25 ms; 13 of
1,800 took more than a millisecond): what 11.2 calls "where the swap waits" does not
happen here, and a grid left to the clock drifts against the display (the display link
measured 119.984 callbacks a second against a nominal 120). So the grid is now set by
the **display link** (`app/app_main.cpp` `DisplayClock`: `CVDisplayLink` of the main
display; it is handed, about 11 ms ahead, the time of the refresh a frame will be shown
at): after each picture the refresh nearest to its moment is asked for and the grid
moved toward it as it would be toward a swap's return. Where swaps do not wait and the
link ticks, the swap is asked for nine tenths of a refresh before the moment (shortly
after the refresh before it: when the system expects a frame for the next) instead of
half a refresh, which makes the lead 3.3 ms longer. The link's answer is used only when
it is less than a tenth of a second old and its refreshes are the window's rate apart;
otherwise (display asleep, another display's rate) the grid is the clock's as before.
`RTA_NO_DISPLAY_LINK=1` switches it off.

Ran on the lit display (`s11/pace.sh l-448`, candidate c5, `RTA_PACE_LOG=1`, load 9 to
13): every picture's moment was set against the link (6,769 of 6,824), the moments lay
on the display's refreshes to the hundredth of a millisecond, the grid was moved 0.6 ms
in all over the session; in the fight 1,791 of 1,793 intervals 2 refreshes, lead 20.2 ms,
and **one stall of 108 ms** (two of 129 ms in the part before): the list waited 81 ms for
the window's thread, which was held outside this program's code (the owner was at the
machine, windows moved above the test window); the five pictures behind it were
overtaken and the grid went on. Not seen in the three runs before it. What the glass
shows cannot be measured from here (no capture); that is the owner's eye.

### 11.8 STATE 07:50 - what `bin/rta_app` is now

`bin/rta_app` = **candidate c5** (07:36): everything of 11.2 to 11.7. Checked with
`s11/verify.sh c5` (11 tick pictures and 60 tour pictures the same with the fast
renderer, the reference switches and the previous program; the rig comparison the same
file as `merge/rig-final-compare.txt` three ways) and a two-copy lobby game
(`s11/online/pair-c5`: 4,833 ticks through a level change, no shared column differs,
checksum exchange agreed on both; load 44 while it ran). `bin/rta_app_c5` is a copy of
it; `bin/rta_app.prev` the program of 19:52 yesterday, `bin/rta_app.merged` the merged
tree with the old pacing; `rta_app_orig` likewise c5, `rta_app_orig.prev` the one before.
The earlier candidates are removed.

Press to picture with the program in place (c5, the display link on; `s11/latency.py
c5-new`, load 20): the pause menu opens in the 4th blank (64 ms), a move in it shows in
the 6th, six of six (95 to 97 ms), an attack in 5, 6, 8, 8, 9, 9, 8, 8 (84 to 150 ms):
the counts of 11.7, and 4 ms more than candidate c4 because the swap is asked for earlier
before the refresh. (A first try of this run ended after 38 s with the program's ordinary
report: the test window was closed from outside - the owner was at the machine.)

### 11.9 The Windows folder (Built; Ran on the Mac where it says so) and what is left

`s11/win/chain.sh`, last night at 23:53 and again at 07:47 from the tree as it is now:
`build_win.py --compiler gcc`, `build_win.py`, `--standin`, `--reference`,
`win/standin_compare.py`, the two `fpcheck` stand-ins.

- **Built**: `local/recomp-out/win/rta-windows` holds `rta_app.exe` (27.9 MB, clang) and
  `rta_app_gcc.exe` (25.6 MB), `rta_native.exe`, `fpcheck.exe`, `pnghash.exe` and their
  GCC twins, all of 07:47. The script finds the translator's output
  (`gen-vu/vu1_fast.cpp` is compiled: `win/obj-clang/r_vu1_fast.o`), so the Windows
  program has the speed work; it also has what of this section lives in shared files:
  a person's input without the blank's delay and read after the wait (`rt/iop.cpp`,
  `rt/runtime.cpp`), the replay fix, the `cur_path` correction, the OpenGL thread's
  fewer calls and the partial resolve, the kept DMA buffer.
- **Not in the Windows program**: the pacing of 11.2 and the display link.
  `app/win_main.cpp` has its own window thread, which holds the game back through the
  hand-overs as the Mac program did until last night (in `pipeline.h` terms the pacer is
  off there); porting `Screen`'s side of it is an hour's work that nobody could run.
- **Ran on the Mac** (the stand-ins): the x86-64 and arm64 tick logs of the fight
  session identical (7,798 rows), memory at ticks 300 and 3,900 identical, both
  comparisons with the rig the same text - and the same text as last night's pass but
  for run times; `fpcheck` 2e77df4dc13ec9c5 on both.
- **README figures** (`--reference`, 07:48): `frames=2309 ... fields=2413
  units=113069982`, `VU0: 466083 microprogram calls, 26111361 instructions` (as before),
  **patch set 27f61e1d (91 words)** (was 3f5b1e14, 90 words: the pnach of 22:30),
  `pnghash` figure b4ed3d8917871960 (as before).
- Not run, as before: anything on Windows. New in that: the translated VU1 programs in
  their SSE2 form inside `rta_app.exe` (the speed work ran that form in its bench under
  Rosetta, not in this program).

**For the other work** (said to the coordinator as well):

- Interfaces: `render/backend.h`, `gs.h`, `vu1*.h` are unchanged. `rt/iface.h`: comments
  only (`PadSource::read` is asked after the picture sink's `vblank`, and what is not
  the script's is not delayed). `app/pipeline.h` (the web page includes it): `app::Sink`
  gained `pacer`, `current` and timing fields and calls `pacer.wait_release()` in
  `vblank`; with the pacer left off, as the web page and the Windows program leave it,
  it behaves as before.
- Proof work: 11.5 (a): `first_tick_fix` can go once `bin/rta_proof` is built from the
  present `rt/iop.cpp`.
- Everybody: the stray "... 2.o" copies in the object directories (11.7); the patch set
  of every build since 22:30 yesterday (11.1).

**Left, in the order I would take it:**

1. **The owner's eye on the lit display.** The grid sits on the display link's refreshes
   and the swap is asked for 7.5 ms before one; that the system then shows each picture
   at that refresh is Apple's convention, not something measured here. If motion judders,
   `RTA_NO_DISPLAY_LINK=1` (the clock's grid) and `--pacing queued` (the old way) are the
   two comparisons; the last lines the program prints say how its own clock saw it.
2. The 100 ms stalls of the window's thread seen once with the owner at the machine
   (11.7): what the thread was doing is not known (`path:` only says the list waited for
   it). A sample of the main thread at such a moment would say.
3. The window's thread: 1.5 to 3 ms of processor time a picture, most of it the cost of
   600 to 1,400 draw calls (11.6); and `prepare_pictures`' walk over every vertex.
4. The Windows program's pacing (above).
5. **Not done: step 6 of the brief** (hit and spell effects, floor decals, the shop's
   lists beside the emulator): it needs an emulator copy, which was not to be started
   without asking, and the time went into the display link.
6. The emulator's own `latency.py` in the pause menu and for the attack, for a like-for-
   like count (10.9); a keyboard or controller press timed by a person rather than by
   `app latency`.
7. `frame_cap = 30` and full screen with the new pacing were not run (a test window must
   not cover the screen); a display that is not a multiple of 60 Hz gets the clock's
   grid at 59.94 as before (the code path of an unlit display, which was run).
8. Idle display sleep: a game played with a controller does not count as the user being
   active; the program asks the system to keep its timers, not to keep the display awake.

**How to repeat** (helpers under `local/recomp-out/app-test/s11/`; `RTA_DISC` is set
inside them):

```
python3 tools/recomp/app/build.py --as rta_app_next && python3 tools/recomp/app/build.py --original --as rta_app_orig_next
B=$PWD/local/recomp-out/bin; S=local/recomp-out/app-test/s11
$S/verify.sh TAG $B/rta_app_next $B/rta_app_orig_next        # 11 + 60 pictures three ways, the rig comparison three ways -> $S/verify-TAG.txt
RTA_NATIVE_APP=$B/rta_app_next python3 tools/recomp/net/lobbypair.py run $S/online/pair-TAG --host window --join window --play 1800 --level drunare --play2 1800
PACE_SCRIPT="--fight 1800 --stand 600" $S/pace.sh NAME $B/rta_app_next 640x448 --art-pack $PWD/local/hd-pack     # and 2619x1964
PACE_ENV="env RTA_FAKE_DISPLAY=120,300,3.1 RTA_PACE_LOG=1" $S/pace.sh NAME ...                                   # a display that is not there
RTA_TOUR_APP=$B/rta_app_next python3 -B $S/latency.py NAME [--pacing queued -- --opt pad-live-delay=1]
python3 $S/replaytest.py NAME $B/rta_app_orig_next [workaround]                                                  # 11.5 (a)
mv $B/rta_app_next $B/rta_app                                                                                    # only when all of it passed
sh $S/win/chain.sh                                                                                               # the Windows folder and its Mac checks
```


## 12. The loose ends (2026-10-13, from 12:15; kept current as the work goes on)

Owner of `tools/recomp/rt`, `render`, `app`, `sound` and `net` from 12:15. Helpers and
results of this section: `local/recomp-out/app-test/s12/` (nothing of it is in the
repository). Every statement says **Ran** or **Read**. The list worked through is the one
of 11.9 and of `native-online.md` ("What the second round found outside ..."), in this
order: threads left behind, the control socket, the stalls, full screen and the 30-a-second
cap, the pacing in the Windows program, a person's first start, the smaller things.

### 12.0 STATE (rewritten at every step; read this first after a stop)

**13:03.** `bin/rta_app` = **candidate n4** since 12:51 (thread fix, control socket, stall
probe, runs without a window drawn by a thread of their own; translation of 22:45
yesterday, set 27f61e1d). It passed `s12/verify.sh n4` (11 + 11 + 60 pictures the same as
before, rig comparison the same file three ways) and a two-copy lobby game
(`s12/online/pair-n4`: 4,634 ticks through the change into `drunare`, no shared column
differs). `rta_app.prev` = c5 of 07:35 (also `rta_app_c5`); `rta_app_orig` / `.prev` likewise.

In the sources since n4, not yet in `bin/rta_app`:

- presenting through a Metal layer from a drawing thread of its own (`app/present_host.h`,
  `present_mac.mm`; `--present metal|opengl`, `RTA_PRESENT`; default still `opengl`), the
  system's word on when each picture was on the glass (12.3);
- the Windows program's pacing (`app/win_main.cpp`, 12.5): compiled and linked
  (`build_win.py --no-game`, 13:00), not run anywhere;
- **the new fix set**: the coordinator said at 13:00 it has landed (29 sections, 99 words,
  figure 073064bb). `app/build.py` without `--no-game` at 13:00 translated with it
  ("patched: 99 words of 29 sections") and candidate **n7** (`bin/rta_app_n7`) announces
  "patch set 073064bb (99 words)". The headless `bin/rta_native_fix` was rebuilt by that
  build (13:00), with the runtime as it is now.

Running now: the ten-minute fight two ways side by side in visible test windows (12.3;
ends about 13:08). Next: `s12/verify.sh n7` + a lobby pair, then 12.6 (full screen, the cap,
resize), 12.7 (first start), the Windows folder rebuilt on the new set.

Processes of this work running now: the lobby server instance `s12/lobby/champions-server`
(pid in `s12/lobby/server.pid`; ports 42800-42817, 42900, 42910, UDP 12101, bound to
192.168.1.123); two copies of `rta_app_n6` (pids in `s12/long.pids`) and two of
`s12/cover/cover` (pids in `s12/cover-longa.pid`, `cover-longb.pid`).

### 12.1 Threads left behind (Ran)

**Found** (`rt/runtime.cpp`). `TerminateThread` (system calls 0x25 / 0x26) makes the
other thread a zombie, takes it out of the schedule and sets `kill` on it; its host thread
waits in `wait_for_baton` for `g_cur == self`, which an unlinked thread never becomes, so
it stood there for ever. With `RTA_THREAD_LOG=1` (new: one line per ended thread) every
case in ten online games is the same one: thread 1 ends thread 5, procedure 0x17ca58, in
state 2 (asleep in `SleepThread`), waiting on no semaphore - three times on the way to
the lobby's game list and four more with every game.

**Changed.**

- `wait_for_baton` ends on `kill` as well, and case 0x25 wakes the thread's condition
  variable. The ended thread gets the big lock when the thread that ended it next gives it
  up, unwinds by the `ThreadKill` exception that `ExitThread` already used, and leaves
  through `thread_main`.
- It must not touch the machine on its way out: by then its thread number may belong to
  a new thread. `thread_main` marks a zombie and unlinks only when the procedure
  *returned*; a thread that was ended (by itself or by another) has been dealt with by
  whoever ended it.
- `rt_poll` gave the big lock back in its `unique_lock`'s destructor when an exception
  passed through it (it released the lock object only on the normal way out); a thread
  ended while it waits there - pre-empted, not asleep - would have unlocked a mutex that
  `thread_main` unlocks again. It now releases on every way out, as the system-call path
  and `rt_sleep` did.
- Counters: `rt_thread_figures` (`rt.h`): host threads carrying a guest thread now,
  started in all, ended from outside. The window program prints them in its last lines
  ("the game's threads: ...") and in the control socket's `info`
  (`game_threads=`, `game_threads_made=`, `game_threads_ended=`).
- Read, not changed: a thread ended while it waits on a semaphore would leave the
  semaphore's waiter count one too high (a later `SignalSema` would wake nobody and not
  count either). The game does not do it (43 of 43 ended threads were asleep, on no
  semaphore); the log line says so if it ever does.

**Proven** (load average 550 to 780 the whole time: other work on the machine).

| What | Program of 07:35 (c5) | Candidate n1 (the fix) |
|---|---|---|
| `lobbyparty.py --players 2 --kinds window,window --scenario leave --rounds N --port-shift 2000 --play 900`: the same two window processes host, join, play 900 frames, leave by the pause menu, are back at the game list, and again | 4 games, all started and in step (1,413 / 1,410 / 1,412 / 1,410 ticks) | **10 games**, all started, both back at the list every time, in step game by game: 1,409 / 1,411 / 1,412 / 1,412 / 1,409 / 1,409 / 1,413 / 1,410 / 1,411 / 1,408 ticks, no shared column differs |
| threads of the host's process, read every 20 s (`ps -M`; `run1/resources.txt`) | 20 20 20 23 21 23 23 25 27 30 29 31 30 32 | 18 17 16 17 17 16 16 16 16 16 16 16 15 15 14 16 15 15 15 15 14 14 15 15 14 15 15 15 15 15 14 15 15 |
| ... of the joiner's | 20 20 19 23 22 23 26 27 27 29 29 31 31 33 | 17 17 17 17 16 16 16 16 16 17 15 16 15 15 14 15 14 16 14 15 15 15 16 15 15 15 15 15 15 15 14 14 14 |
| the program's own last line | - | "the game's threads: 5 now, 70 started in all, 43 ended by the game from outside" |

So: three to four more threads per game before, none after (the count falls a little over
the first games as the system's own helper threads go idle). Sockets as before (4, then
one more per UDP port the game takes, five at most). Files: `s12/online/leave-n1`,
`leave-c5` (each with `.log`).

The standing checks on n1 (`s12/verify.sh n1`: `s12/verify-n1.txt`): 11 tick-keyed
pictures the same with the fast renderer, the reference switches and the program in place
(c5), default picture and `--plain`; 60 tour pictures the same three ways, 20 levels, no
time-out; the rig comparison the same file as `merge/rig-final-compare.txt` three ways,
byte for byte (`cmp`).

### 12.2 The control socket (Ran)

`app ...` lines arriving on the socket now go the way a script's `app` line goes
(`apprt::command` in `app/app_rt.cpp`: `script_app_command`, in front of which
`net/online.cpp` chains itself, then the window program's own handler). What worked,
works: every picture and figure of the checks came through the old commands. **Ran over
the socket**: 12.7 (the walk of a person's first start sends `app online ...` and
`app net ...` that way). `--opt online-commands=FILE` still exists; nothing needs it any
more.

### 12.3 The stalls (Ran; in progress)

**What holds the window's thread: AppKit's own work for the window, on the main thread.**
New debugging aid, `RTA_STALL_LOG=1` (`app/app_main.cpp`, `StallWatch`): when a list that
is ready to be drawn is not taken within 25 ms (`RTA_STALL_MS`), a thread of its own
stops the window's thread for microseconds at a time, copies its call stack, and prints
the stacks with the loader's names once the list is taken; the main thread's event loop
is watched the same way by a timer that should come by every 8 ms. The last lines of the
run count both. No other program is involved (no `sample`, no permission asked).

Three stalls caught in the first paced run with it (candidate n2, small test window,
load average 570; `s12/pace/st1/out.txt`), each with the main thread inside the run
loop's own callbacks, never in this program's code:

| Waited | Where the main thread was |
|---|---|
| 93.6 ms (at the first pass through the event loop) | `HIToolbox _CheckEventsInited`: the window server's port (`SLWindowServerCreateServerPort`), the Apple-event registration and "application ready" (`LaunchServices`): messages answered by other processes |
| 140.3 ms (the window's first display) | the run loop's display cycle (`CA::Transaction::flush_as_runloop_observer` > `NSDisplayCycleFlush`): the window's layout (`-[NSWindow layoutIfNeeded]`, the title bar's views, its symbols loaded through SwiftUI and CoreUI), `-[NSWindow displayIfNeeded]`, `-[_NSOpenGLViewBackingLayer display]` > Qt's `displayLayer:` > `QCocoaScreen::isOnline` > `SLSDisplayStatusQuery` (a message to the window server) |
| 172.4 ms | the same display cycle, in `CA::Transaction::commit` > `_NSCGSTransactionGetEntanglingHandle_` > `+[CAFenceHandle newFenceFromDefaultServer]` > `mach_msg`: waiting 150 ms for the window server to answer |

So it is not App Nap, not timer coalescing, not the display link's thread and not a
priority class: the main thread is running, or waiting inside, AppKit's display cycle for
the window (layout, the title bar, the layer's display, the commit of the Core Animation
transaction), and that cycle makes calls to the window server that are answered late when
the window server is busy - a person moving windows about is exactly that. Such a cycle
runs when something about the window changes: its first display, being covered and
uncovered, another window ordered above it, a resize.

**A thread of its own for drawing: not possible with the window as an OpenGL view.**
Tried (candidate n3): the context moved to a drawing thread (`Screen::painter_loop`,
`draw_one`), the window's size and exposure mirrored for it by the main thread
(`GameWindow::mirror`). Without a window it works and is now how every run without a
window draws (11 pictures the same as before; 293 pictures a second unpaced, 285 before).
With a window AppKit ended the program at the first resize: "-[NSOpenGLContext update]
must be called from the main thread if the context has a view" (an exception breakpoint
in `QCocoaGLContext::update`, called by Qt from `makeCurrent`; the crash report is
`~/Library/Logs/DiagnosticReports/rta_app_n3-2026-10-13-123901.ips`); Qt says of itself
that OpenGL from another thread is not supported on macOS. `RTA_PICTURE_THREAD=main`
forces the main thread; with a window as an OpenGL view it is the only way.

### 12.4 Build scripts, and a link that had broken (Ran)

- **The native programs did not link any more.** `tools/play-net/src/RtaOnline.cpp` (the
  emulator application's file, linked as it is) has called `Rta::CNet::NoteGame` since
  09:35 today - the release work gave the application's network layer the disconnect hold
  of `native-online.md`. A native build does not contain that layer; `net/online.cpp` now
  defines the function, empty (the driver here has its own hold and reads the lobby state
  word itself). Every native build with the network needs it: `app/build.py`,
  `build_win.py`, `net/build_online.py`.
- **The list of the game's files comes from the translation, not from a directory
  listing**: new `tools/recomp/genfiles.py` (the names `recomp.py` writes: `c_000.cpp`
  counted up without a gap, `table.cpp`, `hle_weak.cpp`, `patches.cpp`), used by
  `tools/recomp/build.py` (it compiled every `.cpp` of the directory - and that is the
  script `app/build.py` runs for the game), `app/build.py`, `app/build_win.py` (the
  game's jobs and the `--mac` link), `render/build.py`, `net/build_net.py`. The object
  directories hold strays today: `obj-run` 97 of them ("c_026 3.o", "table 2.o",
  "runtime 3.o" ...), `obj-rta_native_fix` three. Source listings of `rt/` and `net/`
  in those scripts leave out names with a space as well. `app/build.py --no-game` says
  so when a game object is missing instead of failing in the linker.
