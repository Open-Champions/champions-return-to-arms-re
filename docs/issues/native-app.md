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

**Merge of the graphics work (15:46, by the coordinator)**: being verified -
`local/recomp-out/app-test/merge/verify.sh` (the rig comparison with `--plain` and with
the new defaults; then the pole, the films, the heat haze, the bag, the dialogue with
both; then sound through ten level changes). Results under `merge/`; this section is
updated when they are in.
