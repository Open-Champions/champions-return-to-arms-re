# A live rig: the game running headless on Play!'s core

Status of this document: **in progress** (phase 1). It is written as the work goes, so an
interruption loses nothing; sections marked *pending* have not been done yet.

Every earlier statement in this project came from reading the executable or from running
single functions in `tools/ee_emu.py`. This document is the first that reports what the
**running game** does. Statements here are marked

- **Ran** — seen in a log written by the rig, with the address and value quoted;
- **Observed** — read in the executable or in Play!'s source at the place given;
- **Inferred**, **Unknown** — as in the rest of the project.

"Ran" means: ran in the Play! emulator at the commit below, with its high-level BIOS, on
this one disc image. It is not a PlayStation 2 and it is not PCSX2; where the emulator's
accuracy matters to a conclusion, that is said.

## 1. What the rig is

| | |
|---|---|
| Emulator | Play! (github.com/jpd002/Play-, BSD 2-clause), core only: no Qt, no video, no sound |
| Commit built | `83700b2c31e593bc94e845b4b31b797be84dda59` (2026-09-03), submodules as pinned by it |
| Why this emulator | it has a built-in high-level BIOS, so no PS2 BIOS file is needed; none exists on the test machine and none may be downloaded |
| Host | Apple silicon (arm64) macOS; Apple clang 21; CMake 4.4.4 and Ninja 1.13.2 from Homebrew (the only things installed) |
| Disc | the user's own image of SLUS-20973 v2.00, opened read-only |
| Rig source | `tools/rig/` (C++ runner `rig.cpp`, `CMakeLists.txt`, Python wrapper `rig.py`, `README.md`) |
| Where things go | Play! checkout and build: `local/play`, `local/rig-build`; logs, dumps, save states and the emulator's memory-card directory: `local/rig-out/` — all ignored by the repository |

No Play! source is copied into the repository and none is modified. The runner links
Play!'s `PlayCore` static library and uses its public classes.

## 2. Building it

```
brew install cmake ninja                      # if missing; nothing else is needed
git clone --recurse-submodules https://github.com/jpd002/Play-.git local/play
cmake -G Ninja -S tools/rig -B local/rig-build -DPLAY_SOURCE_DIR=$PWD/local/play -DCMAKE_BUILD_TYPE=Release
cmake --build local/rig-build --target rta_rig
```

387 compile steps, a few minutes. Qt, OpenGL, Vulkan, curl and OpenSSL are not needed:
`tools/rig/CMakeLists.txt` adds only `Source/` of the checkout (the target `PlayCore`,
which pulls in Play!'s Framework, CodeGen, zstd, xxHash and libchdr from its own
submodules) and switches the S3 disc-image code off. Notes for whoever repeats this:

- **Observed** — the configure step renames `deps/libchdr/deps/zlib-1.3.1/zconf.h` to
  `zconf.h.included` inside the Play! checkout (zlib's own CMake file does that). It is the
  only change made to the checkout.
- **Ran** — Play!'s `Header` CMake module must be included *after* `project()`. Included
  before it, the release flags lose `-O3` and the whole emulator is built unoptimised; the
  first build here had that mistake (measured cost: see 4a).
- The core is built with `DEBUGGER_INCLUDED`, which is what makes break points possible:
  Play! then compiles a check into the entry of every translated block that contains a
  break point (`Source/BasicBlock.cpp`, `CompileProlog`); other blocks are unaffected.
  The same switch makes Play! analyse the executable for subroutines at boot (a few
  seconds, printed as `CMIPSAnalysis` lines) and record extra data for every graphics
  packet.

## 3. What the runner can do

`local/rig-build/rta_rig --disc <image> [options]`, or through the wrapper
`python3 -I -B tools/rig/rig.py ...`, which adds the disc path (`RTA_DISC`), the data
directory and every symbol file of the repository. `tools/rig/README.md` has the full
list; in short:

| Need | How |
|---|---|
| Boot, null video, no sound, unthrottled | default. Video is Play!'s base `CGSHandler` with nothing drawn; no sound handler is created; the frame limiter preference is off |
| Run N frames or until a condition | `--frames N`; `--until <expr:type> <op> <value>`; script commands `wait`, `at`, `until … timeout N` |
| Read EE memory | watches `name=expr:type`; expressions take symbol names, `0x` numbers, `+ - *`, `[x]` (the word at x) and `$reg`; types `u8 s8 u16 s16 u32 s32 x8 x16 x32 f32 strN hexN` |
| Write EE memory | script command `poke <expr:type> <value>` (translated code on the touched pages is discarded first, so patched instructions take effect) |
| PCSX2-style patches | script command `pnach <file> <section>`: applies the `patch=1,EE,<addr>,word,<value>` lines under `[section]` (`*` for all, `prefix*` for a prefix), printing old and new word |
| Controller input from a script | `press`, `release`, `tap`, `stick L|R x y`, `pad`, or table lines `<frame> <buttons> [lx ly [rx ry]]`; two ports (`press2` …) |
| Log named addresses | `--watch` (repeatable), `--log file.tsv`, `--log-every N`, `--log-on-change` |
| Stop or log at an EE address | `--break <addr>[,opts]`: logs pc, ra (symbolised), a0–a3, t0–t3, v0, sp, f12–f15; options add a C string (`str=REG`), a 16-bit string (`wstr=REG`), memory (`mem=EXPR:LEN`), typed values (`val=`), the return value (`ret`), a stop (`stop`), a hit limit |
| What is on the screen, without video | `--screen-text` (wrapper): break points on the three text-drawing entry points collect the strings of each frame and print them when the set changes |
| Save and load states | `--load`, `--save-at-end`, script commands `save` / `load` (Play!'s own state files) |
| Arguments for the game's `main` | `--arg` (repeatable) |
| Step through menus without reloading | `rig.py session start|send|stop`: one runner kept alive, commands through a named pipe; the machine stands still between commands |

A "frame" in the rig is one vertical blank of the emulated machine (59.94 per emulated
second). All memory access, input and break handling happens on Play!'s machine thread, at
the start of the vertical blank (through the pad handler Play! calls there) or in the break
notification, so nothing races with the emulated CPU.

Limits to know about:

- A break point fires when the translated block containing it is *entered*. At a function
  entry (always a block start) that is exact. An address in the middle of a block reports
  the block's first address instead, and the rig ignores it.
- Break points cost one exit from translated code each: fine at thousands per frame, not at
  millions.
- Frame numbers are per run; a loaded state restarts at 1.

## 4. Results

Speeds are given two ways. The host was heavily loaded by unrelated work during every
measurement (load average 300–600 on 18 cores), so the wall clock understates what the
rig can do; "per cpu-second" is frames divided by the CPU time of Play!'s machine thread,
which is what an idle host would deliver.

### 4a. Boot

**Ran.** The game boots from the disc image with no BIOS file, with null video and no
sound, and reaches its title screens and main menu. From power-on, with a blank memory
card and no input:

| Frame | What happens | Evidence |
|---|---|---|
| 1–224 | start-up; the game's console output shows the IOP being restarted from the replacement image on the disc and 24 IOP modules loaded from the disc | `ps2_stdout.txt` in the data directory |
| 225 | first text drawn: the memory-card check | screen-text log |
| 297 | memory-card slot prompt (the boot card check, a modal loop; `g_drawFrame` 0x44fdd0 then advances by exactly 1 per frame, `g_simFrame` 0x44fdcc too) | log: `g_drawFrame` 1024, 1041, 1101, 1161 … at frames 180, 240, 300, 360 |
| +63 after choosing a slot | "no save data, create it?" question; +250 frames later the data is created (the emulator's card directory then holds the game's save directory) | screen-text log; `vfs/mc0` |
| after the card screens | publisher logo and intro film, about 930 frames if not skipped; a button press skips them | scripted runs with and without presses |
| `g_inFrontend` 0x41b510 = 1 | the front end; `g_levelName` 0x41b721 reads `intro`; the main menu takes input about 240 frames later | log |

With the example script (`tools/rig/examples/boot-to-hub.rig`), which taps through the
splash screens, the main menu is reached at frame 952 and its first choice is taken at
frame 1192.

Speed, optimised build, frames per cpu-second of the machine thread (and × real time):

| Scene | With break point support | Without (`-DRTA_RIG_BREAKPOINTS=OFF`) |
|---|---|---|
| boot and card screens (2-D) | 200–226 (3.3–3.8×) | not measured |
| front end (3-D backdrop) | 52–67 (0.9–1.1×) | not measured |
| character creation | 33 (0.55×) | not measured |
| first level, standing still | 31–36 (0.52–0.60×) | 63–67 (1.05–1.12×) |

Wall-clock rates on the loaded host were 15–50 frames per second for the same runs. Half
of the machine thread's time in a 3-D scene goes into Play!'s graphics path even though
nothing is drawn (`--profile`: the VU1 "kick" handler, the graphics-interface packet
parser and the texture-upload bookkeeping of the base video handler); break point support
doubles that cost because Play! then records extra data per graphics packet.

Three things about speed cost real time to find and are fixed in the rig:

- **Ran.** A build without `-O3` (see section 2) ran the front end at 17–25 frames per
  cpu-second.
- **Ran.** Compiling Play!'s log calls in (`LOGGING_ENABLED`) makes its video thread format
  a line of text for every graphics register write even when nothing is printed; the
  profile showed that formatting as the largest item on the video thread. It is off unless
  `-DRTA_RIG_PLAY_LOGS=ON`.
- **Ran.** With Play!'s usual separate video thread the machine thread spent a third of
  its wall time waiting for it on the loaded host; the rig's default handler has no thread
  (README, "What the rig changes"). Machine-thread CPU per frame is the same either way.

Write-protection of translated code pages, which looked like a candidate (16 KB host pages
on Apple silicon), is **not** a cost here: 3,500–17,000 protect requests in a run and no
more than 24 un-protect faults.

**Determinism. Ran.** Two runs from the same state with the same 286-frame script (stick
pushes, movement across the level) produced identical per-frame logs and byte-identical EE
memory (all 32 MB compared). Two cold boots produced the same seeds at the same frames
(`g_randSeed` 0xa3d95fa8 from frame 60 until the front end; `g_cosmeticSeed` 0x002a3038,
then 0x706e7198 from frame 180). This is the property phase 2 depends on.

### 4b. The symbol map against the running game

**No address or name checked here was wrong.** What was checked, all **Ran**:

| Symbol | Documented | Seen |
|---|---|---|
| `g_randSeed` 0x404464 | LCG, s·1664525 + 1013904223; part of shared state | zero in the file, 0xa3d95fa8 at boot. In the first level, over 399 idle frames, the value moved by exactly one LCG step on 311 frames and stayed on 88; no other step count occurred |
| `g_cosmeticSeed` 0x404460 | separate generator; cutscenes reseed it from the frame counter | advanced once in the same 399 frames. In the front end (a cutscene runs behind the menu) it read 0x6e while `g_simFrame` read 111: the frame counter, as documented |
| third generator 0x404468 | effects and decals | 0 throughout the idle test |
| object seed, object +0x44 | per-object generator | player object: 0x0000ddac, unchanged while idle |
| `g_levelName` 0x41b721 | current level | `intro` in the front end, `hub` in the first level |
| `g_drawFrame` 0x44fdd0 | +1 per rendered frame | +1 per vertical blank at 60 Hz scenes; `gfx_endFrame` 0x19da78 entered once per frame |
| `g_simFrame` 0x44fdcc | ticks since level start | reset on level load; +1 per frame in the level |
| `g_frontendState` 0x4f6b78, `g_frontendMenu` 0x4f6b7c | 0 main menu, 1 game type, 2 players, 3 difficulty, 4 mode | exactly these values in the order 0, 1, 2, 4, 3 as the menus are walked; the menu pointer was 0x4f6bf8, 0x4f6de8, 0x4f6c68, 0x4f6e38 |
| `g_inFrontend` 0x41b510, `g_networkMode` 0x402791, `g_paused` 0x41b4f4, `g_numPlayers` 0x4d8ae0 | | 1 → 0 on leaving the front end; 0; 0; 1 |
| `g_players` 0x4d8af0, record layout of `docs/player.md` | name +0; class +0x50 from model +0x54 (11 → 6); base statistics +0x78; hit points +0xac / +0xb0; mana +0xc0; gold +0xe4 = 500; load limit +0x124 = strength + 125; speed multiplier +0x4c20 = 1.0; object pointer +0x43d8 | the name typed in; 6 and 11 for the last class of the list; 46, 37, 24, 28 — the values the creation screen showed for its four rows in that order, so the order strength, intelligence, dexterity, stamina (given as Inferred) is right; 32.8 / 32.8; 36.7; 500; 171 = 46 + 125; 1.0; a pointer to an object whose table pointer (+0x48) is 0x511308, the Player table, with flags (+0xc) 0x4060 and action state (+0x58c) 2 |
| bags | bag 2 at +0x2540, 0x48 per item, quantity +4, count +0x3740 | 3 items of quantity 2; counts 1 / 3 / 3 for the three bags |
| `g_pads` 0x41bfd8, `g_rawPads` 0x4028d0 | +8 held, +0x14 / +0x18 left stick | see 4c; the raw pad shows the same stick values offline |
| button bits (`docs/netcode.md`, given as Inferred) | 0x1 L2, 0x2 R2, 0x4 L1, 0x8 R1, 0x100 select, 0x200 L3, 0x400 R3, 0x1000 up, 0x2000 right, 0x4000 down, 0x8000 left | each of these eleven confirmed by holding the button and reading `g_pads`+8 |
| button maps 0x41b980 … 0x41ba30, slot 0 | per-slot masks | attack 0x40, ability A 0x20, ability B 0x10, use 0x80, block 0x08, potion A 0x02, potion B 0x01, weapon swap 0x04 |
| functions, by entry count over 200 idle frames in the level | once per simulated frame: `tasks_run`, `runObjects`, `Player_run`; once per displayed frame: `Player_draw`; offline input through `pad_readAll` | 200 each for `tasks_run` 0x3226e4, `Player_run` 0x1a5030, `Player_move` 0x1b4020, `Player_processDamage` 0x1b2cc0, `Player_animStep` 0x1b9520, `Player_regenHealth` 0x1b3b90, `Player_regenMana` 0x1b3900, `Player_draw` 0x1a46c0, `engine_frameStep` 0x19e3a8; 800 for `pad_readPort` 0x17421c (four ports); 1,203 for `Creature_run` 0x112948. In another 115-frame run: 115 each for `runObjects`, `pad_readAll`, `gfx_endFrame`, `game_rebuildAlivePlayers`; 460 for `pad_apply`; **0** for `net_main`, `net_frameLoop`, `net_predictLocalPlayer` |

### 4c. Offline play from scripted input

**Ran.** `tools/rig/examples/boot-to-hub.rig` takes the game from power-on, with a blank
card, to a controllable character: card screens, splash screens, main menu → new game →
offline → one player → mission game → first difficulty → the four character-creation
screens (class, appearance, 20 ability points, name) → level `hub`. 2,829 frames; 58 s on
the loaded host, 46 s of machine-thread CPU. The state saved there is the starting point
of the tests below.

The front end ran at fewer than 60 simulated frames per second of emulated time (111
ticks in 120 vertical blanks at the main menu: about one frame in ten takes two fields);
the level ran at exactly one tick per vertical blank. This is the emulator's timing of a
heavy scene, not something the console is known to do.

**Movement (ledger MV6). Ran, offline.** Stick pushed fully toward 0 from rest, held 90
frames:

| | Value | Expected from MV6 |
|---|---|---|
| distance moved per tick, every tick from the first | 2.585831 – 2.585844 | 180 × 0.861945 / 60 = 2.585835 |
| the same with the stick fully toward 255 (`g_pads`+0x14 = 0.98851) | 2.556112 – 2.556126 | 2.585835 × 0.98851 = 2.556124 |
| direction of travel | the facing angle (object +0x38), which turns toward the stick direction over about 18 ticks | "along the facing" |
| object +0x468 ("last speed") | rises 0.05 per tick to 0.861944854 (0.852041959 with the stick toward 255) | S, and S × stick |

So there is no acceleration in position: the first tick already moves the full distance,
along a facing that is still turning. The value 0.98851 for a stick held toward 255 is the
0.989 `docs/netcode.md` gives for the raw byte offline; toward 0 the pad reads −0.99999994.
The four synthetic direction bits of `g_pads`+8 appeared as documented (0x100000 with the
stick up, 0x800000 right).

**Stick response (ledger L6). Ran, offline: not applicable.** The pad state written at one
vertical blank is in `g_pads` and has moved the player by the second sample after it — no
dead frames. Offline the input path is `pad_readAll` → `pad_apply` and the stick codec is
not in it (`net_main` is never entered). L6 is a statement about net games; it needs
phase 2.

**Potions. Ran.** With the default buttons, potion A (`g_btnPotionA`, mask 0x2, R2) is the
health potion and potion B (mask 0x1, L2) the mana potion — the open question at the end
of `docs/player.md`.

| Step | Seen |
|---|---|
| R2 at full health | nothing: the three bag-2 quantities stay 2, 2, 2 |
| hit points set to 10 (poke), R2 | quantity of bag-2 item 1 goes 2 → 1 within 5 frames; record +0xb4 (healing still to deliver) becomes 22.698 and falls by +0xb8 = 0.0683 per tick while hit points rise 0.0739 per tick (potion plus regeneration) |
| mana set to 5, L2 | quantity of bag-2 item 2 goes 2 → 1; +0xc8 becomes 30.82 and falls by +0xbc = 0.0765 per tick while mana rises |

These are the fields and meanings `docs/player.md` gives for +0xb4, +0xb8, +0xbc, +0xc8.

### 4d. The network question and the plan for phase 2 — *pending*

## 5. Where the running game contradicted the documents

Nothing contradicted an address, a structure offset or a ledger row that was tested. What
needs changing in the documents:

| Where | What it says | What the running game shows |
|---|---|---|
| `docs/OVERVIEW.md`, opening; `docs/netcode.md`, `docs/player.md`, `docs/online-setup.md` openings | nothing has been confirmed on a running game | sections 4a–4c are now confirmed on one (an emulator with a high-level BIOS, offline only) |
| `docs/player.md`, open questions | which button is the health potion | `g_btnPotionA` (default R2) health, `g_btnPotionB` (default L2) mana |
| `docs/player.md`, record +0x78 | statistic order Inferred | confirmed: strength, intelligence, dexterity, stamina |
| `docs/netcode.md`, input record +4 | button bit layout Inferred | eleven of the sixteen bits confirmed (the four face buttons and start were not pressed in isolation) |
| the brief for this work | Play!'s network adapter is a stub | `Source/iop/Iop_Dev9.cpp` is, but `Source/iop/Iop_Speed.cpp` emulates the adapter's Ethernet chip far enough for the game's own driver to start, and has a transmit callback and a receive call that nothing in Play! uses yet (section 4d) |

## 6. What blocked, what is not done — *pending*
