# A live rig: the game running headless on Play!'s core

Status of this document: phase 1 (sections 1–6), phase 2 (section 7: two joined
machines, the baseline, the arena) phase 3 (section 8: fuzzing at scale, a float
mismatch between the machines, the lag sections) phase 4 (section 9: the arena with
characters that have levels and skills — which does diverge — and a tested patch
proposal for the spin skill, SB1) and phase 5 (section 10: the pet and the item bytes
traced, and the arena with every section on) and phase 6 (section 11: every class skill
swept, other levels, and an audit of what a prediction call leaves changed) and phase 7
(section 12: the audit with every fix on and resolved to objects, a block trace that finds
the writing code, the six follow-up questions, and the source of the item bytes with a
21-word fix) and phase 8 (section 13: the real online path — the game's own network stack
on a network behind the emulated Ethernet chip, a network configuration made with the
disc's own program, the sign-in step, and two machines connected to the lobby server; it
stops at the server's terms screen) and phase 9 (section 14: U1 confirmed on the pair with
its section, the route grid compared between machines, pair 410 with and without the
item-record section) and phase 10 (section 15: D26's mechanism shown in the death tick, and
its weapon-swap section; no shared difference produced) and phase 11 (section 16: live
reproductions with and without their sections for D26 — both halves —, E9, U2 and K3, and
the one-sided route-grid test) and phase 12 (section 17: a soak of 120 long real-character
pairs, 5.1 million ticks, with thirteen fix sections on; one class of divergence left — a
heal that passes the maximum, clamped on one machine by the stats page — and the stored
weapon damage still differing with the K3 section on) and phase 13 (section 18: the two
menu sections that answer phase 12 run on the pair — the seven divergent pairs agree with
them and repeat their divergence without them, the stored attack rating agrees, one
scripted pair checks for side effects, and the 27 pairs with a healing skill were soaked
again, 1.2 million ticks, with no difference in anything phase 12 compared) and phase 14
(section 19: the real online path to its end — accounts and characters on the replacement
lobby server, a game hosted and joined, the peer handshake over real sockets, a
lobby-launched lockstep game with the character checksum exchange running, through a
level and an arena fight without a difference). In short: two machines play one lockstep game here;
random input found two real divergences, which are the ledger's K1 and K2, and the test
patch for each removes it; the arena did **not** go out of sync in twelve runs.

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
  packet, which halves the speed of 3-D scenes (4a). `-DRTA_RIG_BREAKPOINTS=OFF` builds
  the other flavour: no `--break`, no `--screen-text`, twice as fast in a level.
  Everything else, the network shim included, works in both.

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
| Controller input from a script | `press`, `release`, `tap`, `tapuntil`, `stick L x y` / `stick R x y`, `pad`, or table lines `<frame> <buttons> [lx ly [rx ry]]`; two ports (`press2` …) |
| Log named addresses | `--watch` (repeatable), `--log file.tsv`, `--log-every N`, `--log-on-change` |
| Stop or log at an EE address | `--break <addr>[,opts]`: logs pc, ra (symbolised), a0–a3, t0–t3, v0, sp, f12–f15; options add a C string (`str=REG`), a 16-bit string (`wstr=REG`), memory (`mem=EXPR:LEN`), typed values (`val=`), the return value (`ret`), a stop (`stop`), a hit limit |
| What is on the screen, without video | `--screen-text` (wrapper): break points on the three text-drawing entry points collect the strings of each frame and print them when the set changes |
| Save and load states | `--load`, `--save-at-end`, script commands `save` / `load` (Play!'s own state files) |
| Arguments for the game's `main` | `--arg` (repeatable) |
| Step through menus without reloading | `rig.py session start`, `send`, `stop`: one runner kept alive, commands through a named pipe; the machine stands still between commands |
| Replace functions of the game by host code | the host-call stub of section 4d; at present used for the ten network-library entries (`--net-shim`, script command `netshim`) |

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
| 1–224 | start-up; the game's console output shows the IOP being restarted from the replacement image on the disc and 23 IOP modules loaded from the disc | `ps2_stdout.txt` in the data directory |
| 225 | first text drawn: the memory-card check | screen-text log |
| 297 | memory-card slot prompt (the boot card check, a modal loop; `g_drawFrame` 0x44fdd0 then advances by exactly 1 per frame, `g_simFrame` 0x44fdcc too) | log: `g_drawFrame` 1024, 1041, 1101, 1161 … at frames 180, 240, 300, 360 |
| about 65 after choosing a slot | the question whether to create save data, since the card is blank; about 60 frames after the answer the data exists (the emulator's card directory then holds the game's save directory) | screen-text log; `vfs/mc0` |
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

- **Ran.** A build without `-O3` (see section 2) ran the front end at 22–26 frames per
  cpu-second instead of 52–67.
- **Ran.** Compiling Play!'s log calls in (`LOGGING_ENABLED`) makes its video thread format
  a line of text for every graphics register write even when nothing is printed; the
  profile showed that formatting as the largest working item on the video thread. It is
  off unless `-DRTA_RIG_PLAY_LOGS=ON`.
- **Ran**, in that early build: with Play!'s usual separate video thread the machine
  thread spent a third of its samples waiting for it on the loaded host. The rig's default
  handler has no thread (README, "What the rig changes"); in the optimised build the two
  arrangements cost the same machine-thread CPU per frame.

Write-protection of translated code pages, which looked like a candidate (16 KB host pages
on Apple silicon), is **not** a cost here: 3,500–17,000 protect requests in a run and no
more than 24 un-protect faults.

**Determinism. Ran.** Two runs from the same state with the same 286-frame script (stick
pushes, movement across the level) produced identical per-frame logs and byte-identical EE
memory (all 32 MB compared). Two cold boots produced the same seeds at the same frames
(`g_randSeed` 0xa3d95fa8 from frame 60 until the front end; `g_cosmeticSeed` 0x002a3038,
then 0x706e7198 from frame 180). The offline movement log was reproduced exactly after
the runner was rebuilt, and the net-game stick log of 4d is identical between the two
build flavours. This is the property phase 2 depends on.

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

### 4d. The network question and the plan for phase 2

The aim of phase 2 is two runners in lockstep, exchanging the game's own datagrams, so
that the arena desync can be reproduced and the two machines' memory compared tick by
tick. This section establishes what stands in the way, and reports the first piece, which
already runs: **a net game on one machine, started without lobby, sign-in or menus.**

#### What the game loads, and what Play! does with it

**Ran.** At boot — not when online play is chosen — the game loads eleven network modules
from the disc among its 23: NETCNF, INET, INETCTL, MSIFRPC, LIBNET, DEV9, PPP, PPPOE,
EZNETCTL, EZNETCNF, SMAP (`ps2_stdout.txt`). They run as real IOP code: their own start-up
lines appear in the console output (INET 2.25.0 with 64 KB of memory, the DEV9 driver
detecting its chip, SMAP 2.25.0, and the control module reporting that interface 1 has no
configuration yet).

**Observed** (Play! at the commit built). Play! substitutes its own implementation only for
modules loaded by a `rom0:` path (`Source/iop/IopBios.cpp`, the `m_hleModules` table) and
this game loads everything from the disc, so the network stack is the game's own. The
hardware under it is two things: `Source/iop/Iop_Dev9.cpp`, a 48-line stub for the
expansion-bay registers, and `Source/iop/Iop_Speed.cpp`, which emulates the adapter's
Ethernet chip far enough for the SMAP driver to start, and offers a transmit callback
(`CSpeed::SetEthernetFrameTxHandler`) and a receive call (`CSpeed::RxEthernetFrame`, one
frame at a time). Nothing in Play! connects them to anything. So in Play! the game's
`sceInet…` calls reach a live IOP stack with a dead wire.

#### Where the game calls the network library

**Observed**, from `symbols/netlib.tsv` and the call sites; arguments 1–8 are in `$a0`–`$a3`,
`$t0`–`$t3`, the ninth is the first word on the stack; results in `$v0`.

| Entry | Called from | Arguments the netcode uses | Result the netcode needs |
|---|---|---|---|
| `net_loadModules` 0x137a10 | `net_gameInit`, once, on the developer paths | none | an interface id (anything but −1000 and −100) |
| `sceLibnetInitialize` 0x365ec0 | `net_gameInit` | (cd 0x5d1458, 0x800, 0x2000, 0x20) | ignored |
| `sceInetGetInterfaceList` 0x365a08 | `net_gameInit`, only when no id is known | (cd, buf, list, 1) | 1, with an id stored in the list |
| `sceInetInterfaceControl` 0x365a90 | `net_gameInit` | (cd, buf, id, 9, 0x5d1440, 16) | a 16-byte address block written at the pointer; this machine's IPv4 address is bytes 4–7, low byte first (d, c, b, a for a.b.c.d) |
| `sceInetCreate` 0x3654a8 | launch code 0x134c60 (launch socket; game socket on the LAN path), end of launch | (cd, buf, block): word 0 of the block 0, word 1 the local port | a connection id greater than 0 |
| `sceInetOpen` 0x365518 | after each create | (cd, buf, id, 1000) | ignored |
| `sceInetClose` 0x365560 | `net_shutdown`, end of launch | (cd, buf, id, ms) | not checked; the shim returns 0 |
| `sceInetSendTo` 0x365830 | `net_sendInputPacket` 0x137d60, `net_sendMsgToPeers` 0x131b00, `net_main`, launch code, LAN lobby | (cd, buf, id, data, length, flags pointer or 0, address block, port, ms) | not checked at every caller; the shim returns the length |
| `sceInetRecvFrom` 0x365670 | `net_pumpReceive` 0x13c078, launch code, LAN lobby | (cd, buf, id, data, capacity 0x7c0, flags pointer, address block out, port out, 0) | length, with sender address block and port stored; **−500** when nothing is waiting (tested at 0x13c158; any other negative value is printed as an error) |
| `net_linkCheck` 0x13e638 | HUD | none | non-zero ("link up") |

The game netcode uses no other entry of the library; the lobby client and SOE's UdpLibrary
use more (`sceInetName2Address`, `sceInetSend`, `sceInetRecv`, `sceInetPoll`), and are not
needed when the lobby is not used.

#### The developer paths that need no lobby

**Observed** in `frontend_run` 0x1e08f0, `frontend_startNetGame` 0x1e21e0 and
`mainloop_runSession`, and — for the first — **Ran**.

1. **`--net` on the command line.** The main loop's level-change code opens the developer
   LAN lobby when three things hold (0x322d38–0x322d5c): `g_networkMode` 0x402791 is set,
   the byte at 0x402792 is set, and `g_netLaunchLatch` 0x5060a4 is clear. The byte at
   0x402792 is **1 in the executable's data** (the word at 0x402790 is 0x00010000), and
   `--net` sets `g_networkMode`. So the argument alone is enough; no debug flag is involved.
   With it there is no front end at all: after the card check and splash screens the
   pending level `strife` (set by `main`) triggers `net_gameInit(0)`, the launch
   preparation 0x134c60 (which, on this path, opens the game socket on port 4000),
   and then `net_debugLanLobby` 0x1345c0 as a modal loop:
   - every 64 displayed frames it sends the four bytes 0xbd3d to 192.168.1.255, port 4000;
   - every datagram 0xbd3d or 0xbd3e from an address not yet in `g_peers` adds a peer (at
     most four), and the table is kept in order of the first stored address byte, the
     last octet, highest first (with two machines, .134 was slot 0 and .132 slot 1) — a
     machine becomes a peer by hearing its own announcement, so the network must
     deliver broadcasts to the sender;
   - the confirm button sends 0xbd3e eight times; on receiving 0xbd3e a machine creates one
     placeholder character per peer and leaves the lobby, and the level loads.
   The broadcast address and the port are constants, so the machines must be 192.168.1.x.
2. **The same lobby from the main menu.** `frontend_run`, state 0, compares the chosen
   entry's key with a fifth key, the string at 0x53cfd8, after the four the retail menu
   offers. No menu table holds that key, so it cannot be chosen; writing the address
   0x53cfd8 over the first key pointer of the main-menu table (0x4f6b88) makes the first
   entry take this branch (**Ran**). It sets `g_networkMode`, creates four placeholder
   characters and asks for a level name the retail disc does not have (the console output
   says the level file is not found and the loading screen never ends) — the pending
   name must be replaced before the lobby is left.
3. **A fixed address table.** In state 1 any key other than the two retail ones leads to
   a host/client menu (state 6, table 0x4f6db8) and on to `frontend_startNetGame` with the
   lobby state zero. That branch (0x1e2268 on) does not discover anything: it copies four
   fixed addresses, 192.168.1.134, .132, .147 and .139 (table at 0x53d0e8), all on port
   4000, finds this machine's own address among them and starts the same launch handshake
   the retail lobby uses, with four expected machines. Not run. It is the path to take if
   the launch handshake itself (character transfer) has to be exercised.

Whether a console or PCSX2 can pass `--net` to the executable was not tried.

#### What was run: one machine, a real net game

The rig replaces the ten entries of the table above. `--net-shim <address>` claims an
address and registers a small range of EE address space (0x1e000000) in Play!'s memory
map; the script command `netshim` writes a four-instruction stub over each entry (load the
range's base, store to word *n* of it, return). The store lands in the rig, which does
the call's work on the host with the arguments still in the registers and sets `$v0`.
This needs no break point support. Datagrams go to a bus inside the process: one sent to
this machine's address or to a broadcast address is queued for the sockets bound to that
port and can be received from the next frame on; anything else is logged and dropped.

**Ran**, `tools/rig/examples/net-solo.rig`, booted with `--arg --net --net-shim
192.168.1.134`:

| Frame | Seen | Evidence (`--net-log`) |
|---|---|---|
| 300 | `g_pendingLevel` reads `strife`; `g_networkMode` still 0 | `show` |
| 464 | network start: `net_loadModules`; `sceLibnetInitialize(cd=0x5d1458, 0x800, 0x2000, 0x20)`; `sceInetInterfaceControl(id=1, code=9, ptr=0x5d1440, len=16)`; `sceInetCreate(type=0, port=4000)` → 1; `sceInetOpen(id=1, ms=1000)` | five log lines, arguments as read in the code |
| 465 | the lobby draws this machine's address | screen text |
| 485 | 4-byte datagram, first word 0xbd3d, to 192.168.1.255:4000; received on the following frame; `g_numPeers` 0x4027c4 becomes 1. (Left in the lobby, as in the run through path 2, the announcement repeats every 64 frames: 189, 253, 317) | send and receive lines |
| 530, the confirm press | eight datagrams 0xbd3e; the first received ends the lobby | eight send lines, one receive line at 531 |
| 750 | player object exists; level `strife`; `g_networkMode` 1 | `show` |
| 906 | `g_netFrame` 0x4027ac = 120 and rising by one per frame | `show` |

Power-on to a running lockstep game: 906 frames, 10 s on the loaded host (7.8 s of
machine-thread CPU, build without break point support).

A net game with one machine ends itself about 100 frames after the level starts (a
disconnection notice, then `g_sessionExitCode` 0x41b508 = 201). For this experiment the
two functions that count active machines were patched in memory: `net_endIfAlone`
0x13ddd8 to return at once and `net_fewerThanTwoActive` 0x13dd88 to answer "no". With
two runners they are left alone. Patching `net_endIfAlone` alone changed nothing and a
break point on it never fired; the game stayed up once `net_fewerThanTwoActive` (four
callers: 0x1db904, 0x1dbe9c in `hud_netStatusDraw`, 0x1e3e10, 0x1e74c4) was patched.
Which caller ends the game was not determined.

What the single machine already shows — all **Ran**, in the hub level reached through
path 2, 200 idle frames unless stated:

| Statement in the documents | Seen |
|---|---|
| once per rendered frame the session calls `net_main` instead of `tasks_run` (`docs/netcode.md`) | 200 entries each of `net_main` 0x132e90, `net_pumpReceive` 0x13c078, `net_frameLoop` 0x139e88, `net_predictLocalPlayer` 0x131d88 and `tasks_run`; `pad_readAll` 0, `pad_readPort` 200 (one port, against four offline) |
| `Player_run` also runs on the prediction copy | 400 entries: two per frame with one frame of lead (`g_localInputFrame` 0x4027a4 = `g_netFrame` + 1) |
| the copy is re-made when `g_netFrame` − `g_ghostRebaseFrame` > 30 | `g_ghostRebaseFrame` 0x4027d4 took the values 394, 425, 456, 487, 518, 549, 580, 611, each at the tick of that number: steps of 31; `Player_clone` 0x11e870 entered 7 times |
| object flags: 0x200000 own player, 0x20000 prediction copy | real player 0x00204060; the object at `g_ghost` 0x4027bc 0x00024060 |
| a machine's own input passes through the stick codec (L6) | `netcodec_encodeAxis` 0x13c450 and `netcodec_decodeAxis` 0x13c970 each entered 8 times per frame, with no remote peer |
| no input packet without a remote peer | `net_sendInputPacket` 0x137d60: 0 entries |
| `g_randSeed` | did not change in 200 idle frames (offline, in the same level, it stepped on 78% of frames) |

**Stick response in a net game (ledger L6). Ran.** Stick pushed fully from rest; the
values are distance moved per tick, sampled once per frame:

| Sample after the pad first shows the push | Prediction copy (what is drawn) | Real player |
|---|---|---|
| 1–4 | 0 | 0 |
| 5 | 0.854 (0.38 of full) | 0 |
| 6 | 1.526 (0.68) | 0.854 |
| 7 | 1.837 (0.82) | 1.526 |
| 8, 9, 10, 11 | 1.992, 2.069, 2.121, 2.147 | one frame behind |
| settled, stick toward 0 | 2.25000 | 2.25000 |
| settled, stick toward 255 | 2.12085 (0.9426 of 2.25) | 2.12085 |
| after release | 2.224, 2.095, 1.862, 1.371, 0.363, 0 | one frame behind |

This is L6 as written: four dead frames, 0.8 reached on the seventh, a ceiling of 0.943
toward 255 and 1.000 toward 0 — and it is MV6's net-game speed, 180 × 0.75 / 60 = 2.25
units per tick. The release takes five frames to die away, which the ledger does not
mention. Offline the same push moves the player at once (4c). The caveat is the one
above: one machine, the developer path, two tests patched; neither touches the input path.

#### The plan for phase 2

1. **Join two runners.** Replace the bus inside the shim by a connection between two
   runner processes (a local socket). Each runner claims its own address (two of
   192.168.1.x); broadcasts go to both; a datagram to the other address goes across.
   Everything else in the shim stays. The ten stubs above are the whole EE-level surface.
2. **Run the two machines in step.** At each vertical blank a runner sends "frame N done"
   with the datagrams its game sent during the frame and waits for the other's; datagrams
   become receivable a fixed number of frames later. Then a run is repeatable to the byte
   (4a), and delay, loss and reordering can be added as a seeded model instead of being
   left to the host.
3. **Start through path 1** (`--arg --net` on both, one confirm press once both list two
   peers). No menu, no character creation, no lobby server, no sign-in.
4. **Compare.** Per tick, on both: the sync ring the game itself keeps (`g_peers` +0x18ac),
   `g_randSeed`, the player records, and a hash of the object pool; full dumps at the
   first tick that differs. The rig's `--log`, `dump` and conditions on `g_netFrame`
   already allow most of this; what is missing is a tool that lines two logs up.
5. **Get to the arena.** Open: the developer path starts in `strife` with level-1
   placeholder characters. Reaching the arena needs either pad input through the hub's
   menus on one machine (the lockstep carries it to the other) or the same memory writes
   on both machines at the same tick; characters with skills need records written before
   the level loads, or the game's own load path. This is where the work of phase 2 is.

What phase 2 will not reproduce without more work:

- **Lobby games.** On the developer paths `g_lobbyLaunch` 0x4f7134 is 0 and the
  characters are not lobby characters, so the code that depends on them (ledger rows on
  `net_allPlayersState2`) takes its other branch. Both can be written identically on the
  two machines before the game starts.
- **Timing.** The shim's calls return at once, where the real ones block for a round trip
  to the IOP; and Play!'s frame times are not a console's (4c). Pacing behaviour (ledger
  L3–L5) is therefore not what a console shows. Simulation results do not depend on
  either, by the game's design — which is exactly what the comparison tests.
- **Saved states** do not hold the shim's sockets and queues; a state taken inside a net
  game can be resumed (sends are dropped, receives report nothing waiting — fine alone)
  but for two runners the shim's state has to be saved with the machine's.

A second design is possible and was not tried: leave the game's network library alone and
join the two emulated adapters at the Ethernet level through the two `CSpeed` calls named
above. It would exercise the whole IOP stack and the real blocking calls, but it needs a
network configuration on the card and an interface brought up by the game's own code, and
it rests on a receive path in Play! that holds one frame and has no user. It is the
fidelity check to do after the EE-level version works, not the way to start.

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

| `symbols/netcode.tsv`, `net_endIfAlone` ("no callers") | | consistent: it was never entered. A lone machine's game ended through a caller of `net_fewerThanTwoActive` instead (4d) |
| `docs/mainloop.md` section 7 step 3, `symbols/netcode.tsv` `net_debugLanLobby` | the developer LAN launch runs "only when flag 0x402792 is set", read as a debug flag | the byte is 1 in the shipped data; what the retail game lacks is only `g_networkMode` at that point, which `--net` supplies (4d) |
| `FINDINGS.md` L6 | (complete as far as it goes) | add: after release the movement takes five frames to die away |

Confirmed on the running net game and worth marking so in the ledger: L6 (four dead
frames, 0.8 on the seventh, 0.943 / 1.000 ceilings), MV6 (0.861945 offline, 0.75 in a net
game, linear in the stick value, along the facing), the 31-tick re-clone of the prediction
copy, and the object flags 0x20000 and 0x200000.

## 6. What blocked, what is not done

- **The host.** Unrelated jobs kept the machine at a load average of 300–600 throughout.
  Wall-clock speeds are therefore pessimistic and noisy; the per-cpu-second figures are
  the ones to trust. The host's own profilers (`sample`, `lldb`) could not be attached in
  this environment, which is why the rig has a sampler of its own (`--profile`).
- **Speed.** The first builds were unoptimised and had Play!'s logging compiled in, which
  hid everything else for a while; both are fixed and explained in sections 2 and 4a.
- **Not done:** two runners (phase 2); the fixed-address-table path; the Ethernet-level
  design; the arena; anything about PCSX2 or a console; the five untested button bits; a
  measurement on an idle host. The mismatch table lists what the documents should say
  now; they have not been edited.
- **Not checked:** how faithful Play! is to the console in floating point. The movement
  distances in 4c agree with the documented constants to seven digits, which is a good
  sign and no more than that.
- **Repository rule.** `AGENTS.md` and `docs/REPOSITORIES.md` say native code and build
  files belong in other repositories. `tools/rig/` is a C++ file and a CMake file, written
  here because this work's brief asked for them here; whether a research harness falls
  under that rule is for the maintainers to decide.

## 7. Phase 2: two machines

Everything in this section is **Ran** unless marked. The limits come first because every
conclusion below depends on them:

- The two machines are two copies of the same emulator build on the same host. They
  cannot differ in floating point, in timing of the real hardware or in anything else that
  two real consoles (or a console and an emulator) might differ in. **A divergence found
  here is a logic difference; no divergence here says nothing about those other causes.**
- The game is started through the developer LAN path (4d): no lobby, `g_lobbyLaunch` 0,
  level-1 placeholder characters. Two runs set the lobby flag and the character kind by
  hand; none used characters with skills.
- Play!, not a PlayStation 2 and not PCSX2.

### 7.1 How the two machines are joined

Two runner processes, one machine each, connected by a local stream socket (`--link`).
At every vertical blank each runner sends one message — its frame number and the
datagrams its game sent since the last one — and waits for the other's message with the
same frame number (`CLink`, `ExchangeWithPeer` in `rig.cpp`). Neither machine can get
ahead, and what a machine receives depends on frame numbers only. A single process
hosting both machines was not tried: Play!'s core keeps one translator and one executor
in static variables.

The libnet shim of 4d is unchanged except for where datagrams go: one for this machine's
own address or a broadcast is queued locally as before; a broadcast or one for any other
address also crosses to the other runner, after the **bus model** (`--bus
delay=N,jitter=N,loss=N,seed=N`): `loss` per thousand are dropped, the rest become
receivable `1 + delay + (0…jitter)` frames after they were sent. The draws come from a
generator seeded by `seed` and the machine letter. The two "alone" patches of 4d are not
used.

`rig.py pair OUTDIR …` starts both (machine A: 192.168.1.132; machine B: 192.168.1.134;
separate memory-card directories), with the same script; lines tagged `A:` or `B:` act
on one machine while the other lets the same number of frames pass.

`tools/rig/examples/pair-start.rig`, both machines from power-on with `--net`:

| Frame (both) | Seen |
|---|---|
| 464 | network start, lobby |
| 485–486 | both announce; each hears itself and the other: `g_numPeers` 2 |
| 530 | machine A presses confirm; eight start datagrams each way |
| 767 | player objects exist; level `strife`; `g_numPlayers` 2 |
| 873 | `g_netFrame` 60 |
| 1,473 | tick 659; states saved for everything below |

Machine A's stick moves player 1 and machine B's player 0. Lead (`g_localInputFrame` −
`g_netFrame` at the tick): 4–5 with no bus delay, about 10 with delay 3 and jitter 3,
14–25 with delay 10 and jitter 6.

A pair is as repeatable as a single machine: the run that diverged at tick 2033 (7.3)
diverged at tick 2033 again, with the same values, in three later runs.

Cost: with break point support (needed for the tick log) each machine runs about 33
frames per cpu-second in a level; a pair of 6,000 frames takes four to five minutes.

### 7.2 What is compared

**The tick log.** A break point at 0x13aee8 — the return from `tasks_run(1, 2)` inside
`net_frameLoop` (call at 0x13aee0) — stops the machine once per lockstep tick, after the
tick's tasks and before the game adds one to `g_netFrame` and hashes. The runner writes
one row there: `g_netFrame`, `g_randSeed`, the level name, and for players 0 and 1
position (raw bits), facing, action state, object seed, hit points, mana, gold,
experience and a checksum of each of the three bags; the sync record the game stored for
the previous tick (this machine's ring, `g_peers` + slot × 0x44e0 + 0x18ac); the
out-of-sync byte of both peers (+0x44d7); and per-machine columns (named `l_…`): the
input frame, the cosmetic seed, the draw frame, the dropped byte. Runs add columns with
`--tick-watch` (cutscene flag 0x44fcd0, selector words 0x41b818, the lockout word
0x41b4fc, `g_localMenuOpen`, the lockstep pads, the pending level).

`tools/rig/compare.py ticks A B` lines the two logs up by tick and reports the first tick
at which a shared column differs and every column that ever does.

**Memory.** `ontick N dump 0 0x2000000 file` writes all of EE memory inside tick N on
both machines; `compare.py mem` diffs two dumps and groups the differences by symbol. Two
machines whose tick logs agree differ in about 567,000 bytes in 1,600 runs: the pose
buffers (124 KB — the per-machine pose cache of ledger row D34 is real), the render lists
and texture bookkeeping, the peer table and sync rings (each machine keeps different
things for the local and the remote peer), each machine's prediction copy, and heap
blocks that the two machines allocated in a different order. The tool's ignore list
(a table at the top of the file) names only the kernel area, the main stack and the
prediction copy; for the rest it takes a baseline — a pair of dumps from an earlier tick
at which the logs agreed — and leaves out every byte that already differed there. One
tick apart, that leaves about 4,000 bytes of per-machine noise (render lists, rings).
**It was not needed for the findings below**, which the tick log and break points
settled; it has been run only on in-sync pairs. `g_cosmeticSeed` differs between the
machines on nearly every tick, as designed.

### 7.3 Baseline in `strife`: two real divergences

From the tick-659 states, seeded random input on both controllers (`fuzz`: left stick,
attack, abilities, block, weapon swap, potions, use; in some runs also right stick,
D-pad, inventory button, stick buttons):

| Run | Bus | Input groups | Ticks compared | Result |
|---|---|---|---|---|
| base1 | none | move, fight, potion, use | 4,149 | no shared column differs |
| base2 | delay 3, jitter 3, loss 5% | same | 5,808 | none in seed, positions, bags (see note) |
| base3 | delay 10, jitter 6, loss 10% | + dpad, select | 5,157 | **bag 2 of player 0 differs from tick 3894** (K2) |
| base4 | none | + rstick, dpad, select, l3r3 | 1,653 | **level and seed differ from tick 2034** (K1) |
| base5 | delay 25, jitter 10, loss 20% | move, fight, potion, use, dpad | 3,504 | no shared column differs |
| disc | none | move | 4,604 | no shared column differs |

Note: in base2 and base3 the `prevhash` column differed on most ticks. That was a mistake
in the log, not in the game: those two runs read the remote peer's ring instead of the
local one (the slot numbers of the two machines were the wrong way round in the launcher,
since corrected), and a remote record arrives later than the tick.

The plain runs exercised movement, melee, casting, blocking, potions (the bags changed)
and picking up gold; nothing in `strife` damaged the players in base1.

**K2 — potion, then inventory, inside the input delay. Confirmed; its patch removes it.**
In base3 at tick 3894 the machine that does not own player 0 took a potion out of the bag
and the owner's machine did not; later both changed again, to different contents. The
scripted version (`examples/pair-k2.rig`, bus delay 10, lead 14): player 1's hit points
are set to 10 on both machines in tick 700; machine A presses R2 and three frames later
the inventory button.

| Tick | Machine A (owner) | Machine B |
|---|---|---|
| 733 | `g_localMenuOpen` 0x41b69d becomes 1 — at once, from the raw pad, 11 ticks before the lockstep pad shows the potion press | 0 throughout |
| 744 | lockstep pad of slot 1 shows 0x2; potion quantities stay 2, 2, 2 | quantities become 2, **1**, 2 |
| 746 | lockstep pad shows 0x100 (inventory) | |
| to the end, tick 1187 | 2, 2, 2 | 2, 1, 2 |

Hit points agree throughout and no out-of-sync byte is ever set: the difference is
silent, as K2 says. With "Net test: potions always leave the bag directly" applied on
both machines (0x1b9fcc and 0x1ba3ac: 0x8043b69d → 0x00001821) both take the potion at
tick 744 and no shared column differs.

**K1 — use, then D-pad, inside the input delay. Confirmed; its patch removes it; the
consequence can be worse than the ledger says.** base4, no bus delay (machine A's lead 5):

| Tick | Machine A (owns player 1) | Machine B |
|---|---|---|
| 2028–2031 | `Player_interact` 0x1b2640 entered for slot 1 from `Player_run`+0xbf4 every tick | the same |
| 2032 | `g_spellSelectorHeld[1]` 0x41b81c becomes 1 (A's D-pad, raw pad); the call from `Player_run` no longer happens | word stays 0; call happens |
| 2033 | lockstep pad of slot 1 shows 0x80 (use), sampled five frames before the D-pad; no call | call happens; `script_newWorld` 0x143dd0 is entered from the level script (`scr_callNative`+0x44) and `g_pendingLevel` 0x41b6d0 reads `blood1` |
| 2034 | still `strife`, seed 0xf146bbff | in `blood1`, seed 0x394f8527 |
| 2036–2037 | each machine sets the other's out-of-sync byte; later each drops the other | |

So the first shared address to differ is `g_pendingLevel`, written by `script_newWorld`
on the machine that does not own the player, because on the owner's machine the gate at
0x1a5c08–0x1a5c1c skipped `Player_interact`. The player was standing at a level exit: one
machine changed level and the other did not. With "Net test: use button works with the
spell selector open" on both machines both write the name in tick 2033, both are in
`blood1` at tick 2034 with seed 0x394f8527, and no shared column differs (1,433 ticks).
With "Net test: menu lockout never blocks weapon swap and use" instead, the divergence is
unchanged: it is K1, not the lockout word. Reproduce with `examples/pair-k1.rig`.

**D26 — dying with the inventory open. Not settled.** In the arena fight machine A opened
its inventory and its player was killed (one scripted run, repeated with a break point):
`g_localMenuOpen` went from 1 to 0 in
the tick of the death (tick 2716), so the menu is closed by the death on that machine, as
the row says. No divergence followed. A break point on `Player_takeDamage` 0x1b5330 on
both machines logged the same 30 calls on each, and the lockout word 0x41b4fc was 0 at
the entry of every one: no damage call fell into the rest of the death tick. The row
needs a hit on the *other* player in that one tick; with two hits on that player in the
whole fight it did not happen, and no way of forcing it was built. Neither confirmed nor
refuted; its patch was therefore not tried.

### 7.4 Getting to the arena

The boot-argument code has no level argument (the strings are `--net`, `--stress`,
`--splash`, `--pvp`, `--char`, `--female`). The route used: `ontick 700 poke
g_pendingLevel:str16 drunare` on both machines — the name is written inside lockstep tick
700 on both, which is the point at which the level script would write it — and the main
loops change level together. Both machines were in `drunare` with two player objects
about 120 frames after the write, the level's title on the HUD, players at (330.8,
−203.2) and (317.9, −233.0); the states saved at tick 870 are the "arena entrance" states. The debug warp
list (`g_debugCheats`) was not needed and not tried.

Characters: the placeholder level-1 ones as they are ("weak"); the same with hit points
and their maximum set to 3,000 in tick 880 on both machines (they still died: "strong"
below was not strong); and with level 50, strength and stamina 3,000 and 30,000 hit
points ("very strong": nobody died and experience was gained, so knights or their
summons were killed).

### 7.5 The arena: no desync in twelve runs

Each run, from the entrance states: machine A's player walks west into the trigger strip;
both machines sit through the opening cutscene without skipping it; then both fight on
seeded random input for 4,000–4,500 frames.

| Run | Bus | Characters | Input groups | Patches | Ticks compared | Shared difference |
|---|---|---|---|---|---|---|
| 1 | none | weak | move, fight, potion, use | — | 5,458 | none |
| 2 | delay 3, jitter 3, loss 5% | weak | same | — | 5,723 | none |
| 3 | delay 10, jitter 6, loss 10% | weak | same | — | 5,644 | none |
| 4 | none | weak | + rstick, dpad, select | K1, K2 | 5,956 | none |
| 5 | none | hp 3,000 | move, fight, potion, use | — | 5,954 | none |
| 6 | delay 5, jitter 5, loss 5% | hp 3,000 | same | — | 5,709 | none |
| 7 | none | hp 3,000 | + rstick, dpad, select | K1, K2 | 5,556 | none |
| 8 | none | weak, lobby flag and kind | move, fight, potion, use | — | 5,958 | none |
| 9 | delay 3, jitter 3, loss 5% | very strong, lobby flag and kind | same | — | 4,530 | none |
| 10 | none | very strong | + rstick, dpad, select | K1, K2 | 6,150 | none |
| 11 | delay 4, jitter 2 | weak | + rstick, dpad, select | — | 5,938 | none |
| 12 | delay 3, jitter 3, loss 5% | weak | move, fight, potion, use | — | 6,105 | none |

Run 12 is `examples/pair-arena.rig` as published: it starts in `strife` at tick 659, so
it includes the level change. 68,685 ticks in all. Marks (the same in every run, as they must be from one pair of
states): first tick in the level 870 (the state); the cutscene flag 0x44fcd0 goes up at
tick **1022**, and 1022 mod 15 = 2, which is what `docs/issues/arena-entry.md` (E4)
derives; it goes down 1,268 ticks later (the document says about 1,270).

What the runs covered: the trigger and cutscene; the knights attacking; both players
dying and being put back (one or two deaths each in the weak runs, after which the
cutscene played a second time); in runs 9 and 10 no deaths, experience gained (81 / 95
and 64 / 100) and a further 772 and 958 ticks with the cutscene flag up, so the fight
went past its first stage. "Lobby flag and kind" means `g_lobbyLaunch` 0x4f7134 = 1 and
the kind bits of both records (+0x4c1c) changed from 1 to 2 on both machines in tick 880.

**Plainly: the arena desync was not reproduced.** Not with zero bus delay, not with
delay, jitter and loss, not with the lobby flag set, not after deaths, not after kills.
Since two identical machines stayed in step through the level's entry, its cutscene and
the fight, the cause of a desync that real players see on every run is probably something
this set-up does not contain:

- a difference between the machines themselves (floating point, which two identical
  emulators cannot show — ledger F rows);
- the real launch path: lobby characters with skills and equipment, the transferred
  records, and whatever the lobby game does that the developer start does not;
- the real route into the level (from `drundar` through its door, with saved level
  state), where this section wrote the level name directly;
- real timing: frames that take two fields, calls that block, packet timing the bus
  model does not imitate (the model delays, drops and reorders, but both machines still
  run their frames in the same number of emulated cycles);
- K1 or K2 happening in the arena to real players (a use press and the D-pad, a potion
  and the inventory button): both are now confirmed, the first can end a session at
  once, and the second is silent. Run 11 had those inputs unpatched and did not trip
  either in the arena; base3 and base4 did in `strife`.

### 7.6 For the ledger

Proposed, for whoever edits `FINDINGS.md` (this document does not):

| Row | What to record |
|---|---|
| new (V9) | Two machines joined through the developer LAN start play one lockstep game; a pair of runs repeats exactly from states, script and bus seed. Ran |
| K1 | Ran: confirmed on two machines; the first shared address to differ was `g_pendingLevel`, written by `script_newWorld` on the non-owner's machine at a level exit — one machine changes level, both flag the other out of sync. The test patch removes it; the lockout patch does not |
| K2 | Ran: confirmed, silent (no out-of-sync byte); the owner keeps a potion the other machine removed. The test patch removes it |
| U4 | Ran, consistent: in the K2 run the owner's menu opened 11 ticks before its potion press reached the tick, at a lead of 14 |
| D26 | Still not run to a divergence: the menu does close in the death tick on the owner's machine, but no damage call fell into the rest of that tick |
| D34 | Ran: between two machines in sync the pose buffers differ in about 124 KB |
| E4 | Ran: the opening cutscene started on tick 1022 (2 modulo 15) and lasted 1,268 ticks |
| D25 | The arena did not desync in twelve runs on two identical machines (68,685 ticks, zero and non-zero bus delay, loss up to 10%, with and without the lobby flag, with deaths and with kills) |

### 7.7 What was not done

- D26 is open (7.3). The "Arena diagnostic" sections of the patch file were not used:
  there was no arena divergence to bisect.
- Characters with skills, stored or lobby characters, the launch handshake (path 3 of
  4d), four machines, the entry from `drundar`, other levels, runs longer than about
  6,000 ticks, the debug warp menu.
- The memory diff has no per-object comparison (the two heaps are not laid out alike),
  and its ignore list is mostly "whatever already differed at the baseline".
- Nothing here is a console result.

## 8. Phase 3: fuzzing at scale, a float mismatch, lag

The limits of section 7 apply unchanged: two copies of one emulator build, the developer
LAN start, level-1 placeholder characters without skills, Play! and not a console.
Everything is **Ran** unless marked.

### 8.1 The driver

`tools/rig/fuzz.py` runs pairs unattended (README, "Fuzzing two machines"): a list of
levels, input mixes and bus settings; one pair per seed; fresh memory-card copies per
pair; the two tick logs compared; a pair that differs run again to see that it repeats;
with `--try-patches`, one more run per "Net test" section of the patch file to see which
removes the difference; divergences grouped by the shared columns that differ at the
first differing tick. Levels other than the states' own are entered by writing the
pending level in one tick on both machines (7.4). The tick log gained columns for this:
checksums of each player's statistics block, points, equipment pointers, ability
records and skill ranks, and of the per-slot button maps 0x41b980–0x41ba3f.

Check of the driver on a known case, with no patches: the seed of 7.3's K1 run came out
as one class, repeated exactly, and "use button works with the spell selector open" was
reported as removing it. So was the lag section "trim leaves one spare frame (LAG-2)":
a section that changes when input is sampled moves the coincidence away without touching
its cause. The lag sections are therefore left out of the trials.

### 8.2 The next desync: none found

With the K1 and K2 sections applied on both machines:

| Batch | Pairs | Frames each | Start levels | Input mixes | Bus settings | Ticks compared | Divergent |
|---|---|---|---|---|---|---|---|
| 1 | 36 | 12,000 | `strife`, `drunare`, `hub`, `drundar`, `blood1`, `bastion1`, `citadel`, `valor`, `storm1`, `fire1`, `nit1`, `wat1` | everything (sticks, attack, abilities, block, weapon swap, both potions, use, D-pad, inventory button, pause button, stick buttons); the same without pause and stick buttons; the same without D-pad | none; delay 3, jitter 3, loss 5%; delay 10, jitter 6, loss 10% | 387,213 | **0** |
| 2 | 24 | 20,000 | `hub2`, `islc1`, `torment0`, `swamp1`, `fay1`, `honor`, `shame1`, `inmine1`, `dis2`, `airarena`, `boar1`, `arachna1` | everything; without D-pad and stick buttons | none; delay 5, jitter 4, loss 5%; delay 2 | 401,461 | 1 — a kick, not a desync (below) |

The pairs did not stay where they started: the level column shows level exits taken on
both machines in the same tick (`strife` → `blood1`, `drundar` → `blood1`) and returns to
`hub`, and the players died and were put back many times.

What the random input reaches and what it does not, counted with break points on one
machine of one pair (8,000 frames, the "everything" mix, 6,691 ticks, in sync):

| Reached | Entries |
|---|---|
| pause menu opened / closed (`pauseMenu_open` 0x18e334, `pauseMenu_close`) | 11 / 23 |
| inventory opened / closed (`menu_openInventory`, `inventory_close`) | 13 / 20 |
| inventory messages applied (`invmsg_dispatch`); equip; drop | 38; 1; 1 |
| shop opened (`shop_openOrStock`) | 4 |
| potions (`Player_usePotion`), casts (`Player_castSkill`) | 196; 9 |
| statistics recomputed (`player_recalcStats`, the K4 path) | 435 |
| game messages queued (`net_sendGameMsg`) | 115 |
| **not reached**: options committed (`config_commitOptions` 0x1e6650, U1) | 0 |
| **not reached**: mission menu (`missionMenu_run`, U2) | 0 |

In this one pair nobody was hit, died or left the level; other pairs did all three (the
level columns above).

The one divergent pair (`torment0`, seed 314) is the game's own **kick**. Machine B's
random input opened its pause menu and chose the entry that removes the other player.
On B the menu closes in tick 7758 and in tick 7759 `net_frameLoop` sets peer 1's dropped
byte (+0x44d5) and calls `Player_takeDamage` for player 1 directly (return address
0x13aeb8), which kills the character there; from then on B ignores machine A's input.
Machine A plays on for some 240 ticks while B sends it the four-byte notice 0xbd43 every
ten frames. It repeated exactly, and no patch section changes it, as it should not. The
driver now recognises the case (a dropped byte set on either machine at the first
differing tick) and reports it as a kick or leave, not as a desync.

So the statement is: with K1 and K2 patched, random play of that kind over 788,674
ticks in 24 levels produced no difference in the shared seed, positions, hit points, bags,
statistics, equipment, skills or button maps. It is not a statement about paths the
random input does not reach (above), nor about characters with skills.

### 8.3 A float mismatch between the machines

`--fp-round` forces a host rounding mode on one machine's thread. Play! runs the EE with
round-toward-zero and its translated code does single-precision arithmetic in the host's
mode, so machine B with `--fp-round nearest` (or `up`, `down`) rounds every add,
subtract, multiply, divide and square root differently from machine A — the kind of
difference ledger rows F5 and F9 consider between a console and an emulator setting.
Machine A is untouched. First tick at which a column differs; "sync flag" is the game's
own out-of-sync byte (peer +0x44d7), after which the session ends:

| Level, input | Rounding on B | Pairs | First raw difference | Sync flag | Ticks from first position difference to the flag |
|---|---|---|---|---|---|
| `strife`, none | nearest, up, down | 6 | none in 3,149 ticks | never | — |
| `strife`, movement only | nearest, up, down | 6 | position, tick 697 (the first tick anybody moves) | ticks 728–782 | 31, 31, 31, 31, 43, 85 |
| `strife`, movement and fighting | nearest, up, down | 6 | position, tick 697–698 | ticks 706–798 | 8, 62, 62, 65, 65, 101 |
| `drunare`, at the entrance, none | nearest, up, down | 3 | hit points (and mana) raw bits from tick 701 with nearest and up; nothing with down | never in 3,240 ticks | — |
| `drunare`, walk to the trigger, then nothing | nearest, up, down | 3 | position, tick 759 (the first step) | tick 872, 766, 872 | 113, 7, 113 |
| `drunare`, walk to the trigger, then fight | nearest, up | 4 | position, tick 759 | tick 872 (nearest), 766 (up) | 113, 7 |

(In the last two rows the flag came during or right after the walk; no mismatched pair
was still in sync when the cutscene or the fight began, so those were never tested as
such.)

Reading:

- **With no input nothing shared differs**, for thousands of ticks, in either level. (In
  `drunare` the raw bits of one player's hit points differ from the first tick — the
  regeneration sum rounds differently — which the game does not hash.)
- **As soon as a player moves, the position's raw bits differ on that tick, and the
  game's sync check trips within 7–113 ticks** — a tenth of a second to two seconds — (it hashes whole-number positions, so
  it needs the difference to cross an integer). That is true in `strife` with movement
  alone, before any fight, and in `drunare` on the walk to the trigger: no pair with a
  rounding mismatch got as far as the arena's cutscene or fight in sync.

So a machine-wide rounding mismatch cannot be why players see the desync at the arena in
particular: it would end every session within a second or two of the first step, in the
first level. If floating point is involved in the arena, it has to be something much
narrower than the rounding rule — an operation whose result differs between machines only
for unusual operands (the divisions by zero and the square root of F3, F4, F7 and MV1 are
the candidates the ledger already names). This experiment does not test that; it would
need the difference injected into those operations alone.

One of the mismatched pairs left machine B making no progress after it had gone out of
sync (no CPU use; killed by hand after 49 minutes). The pair launcher now kills a machine
that is still running two minutes after the other has ended. Not investigated.

### 8.4 The lag sections

A pair in `strife`, bus delay 2 frames each way, movement input; from frame 300 nothing
crosses the bus for 30 frames (half a second). Lead is `g_localInputFrame` − `g_netFrame`
at each tick, averaged over 5-second stretches after the outage; the two machines gave
the same numbers:

| | before | 0–5 s | 5–10 s | 10–15 s | 15–20 s | 20–25 s | 25–30 s | 30–35 s | peak |
|---|---|---|---|---|---|---|---|---|---|
| no patch | 6 | 34 | 32 | 27 | 23 | 18 | 13 | 8 | 34 |
| "equalise at once (LAG-1)" on both | 6 | 11 | 9 | 6 | 6 | 6 | 6 | 6 | 11 |

Ledger L11 predicts 35 frames after a half-second stall, lasting about 30 s after an
outage; L12 predicts about 12 with this section. Both are what the running game does
(34 for about 35 s; 11 for under 10 s). The pair stayed in sync in both runs. The other
lag sections were not run.

### 8.5 Fix sections: which are confirmed live now

| Section | Status |
|---|---|
| use button works with the spell selector open (K1) | confirmed (7.3; again by the driver, 8.1) |
| potions always leave the bag directly (K2) | confirmed (7.3) |
| equalise at once (LAG-1) | confirmed against L11 / L12 (8.4) |
| menu lockout never drops player damage (D26) | not exercised: forcing the case needs a damage call on the other player inside the tick of the death, which means calling game code from the rig at a chosen point; that was not built |
| notice box does not run the pending script (E9), save-point prompt (B9), option commit and the button maps (U1), mission and jump-gate menus (U2), stats page (K3) | not exercised: each needs a menu walked by script (options list, save point, mission menu), and B9 also memory-card characters, which the developer start does not provide. The random input did not produce a divergence that would point at them (8.2) |
| the remaining "Net test" and "Arena diagnostic" sections | not run |

### 8.6 Not done in this phase

- The realistic arena run (characters with levels, skills and items; the entry from
  `drundar` through its door with the quest state; the fight to the boss and the closing
  cutscene; four machines). The fuzz started three pairs in `drundar` and three in
  `drunare` with the placeholder characters; that is all.
- A per-object memory comparison in `compare.py`.
- Float differences confined to particular operations (8.3).

## 9. Phase 4: the arena with real characters

Limits as in section 7 (two copies of one Play! build; the developer LAN start). What is
new is the characters; they have levels, statistics and skills but still only their
starting items. **Ran** unless marked.

### 9.1 The characters

The developer lobby creates its characters itself when the game starts (4d), so there is
no record to prepare before the confirm. Two things are done instead:

- **Class.** The lobby takes each slot's character model from a table at 0x530338 (four
  words: 7, 11, 8, 10). Writing 0 to the first word before the confirm makes slot 0 a
  melee class; slot 1 stays the lobby's caster with a summoned pet (model 11). The
  characters are then built by the game's own `player_initNewCharacter`.
  (`examples/pair-chars-start.rig`.)
- **Level, statistics, skills.** In lockstep tick 680, identically on both machines
  (`examples/pair-chars.rig`, 53 `ontick` writes): level 25 (+0x58, +0x59); base and
  effective statistics 200 / 300 / 150 / 250; the skill-rank list (+0x4b08) rewritten
  with rank 10 for four skills (slot 0: ids 41, 76, 77, 78 — the spin and three shouts)
  or five (slot 1: 89, 87, 88, 90, 94 — a bolt, two area effects, a summon, a shield);
  one ability record per skill in the form the game's own starting skill has (the name
  that marks a `Skill` object, the id at +0x20, the bytes 01 00 at +0x24); the first two
  on the two ability buttons (+0x4a84). No healing skill was included (its id was not
  looked up), and no items.

The game's own recompute then gave maximum hit points 897.5 and 709.0 and maximum mana
580.5. **Equal on both machines:** the tick log's checksums of the statistics block,
points, equipment, ability records and skill ranks agreed on every tick of every pair
below until a divergence, and in the pairs without one to the end. The skills work: in the
first probe pair `Player_castSkill` was entered 30 times on one machine, the spin's update
372 times, the melee player spent 511 ticks in action state 6, and the pair took 236
damage calls and gained experience.

The random input gained a group `cast` (both ability buttons at four times the rate).

### 9.2 The arena, sections K1, K2 and LAG-1 on

Twelve pairs (`fuzz.py`, seeds 400–411, 14,000 frames; mix: movement, attack, block,
weapon swap, abilities, both potions, use, D-pad selector, inventory button; six with no
bus delay, six with delay 4, jitter 3, loss 5%): into `drunare` by the pending-level
write, the walk into the trigger, the unskipped opening cutscene, the fight.

**172,496 ticks; 770 casts and 6,905 spin updates on machine A alone; 13 deaths; in five
pairs the fight was won** — the level column goes `strife` → `drunare` → `hub2` and the
cutscene flag was up for about 5,670 ticks (the opening's 1,268 plus the later ones), so
the boss, the closing cutscene and the automatic level change all ran, in sync. In the
others the party died and came back through `hub`.

**Three of the twelve diverged, each repeating exactly:**

| Pair | First difference | What it is |
|---|---|---|
| 402, tick 4932; 410, tick 6920 (no bus delay) | bag 2 of player 1 | **Stale bytes in a picked-up item.** Both machines add the same item to the same cell in the same tick (definition 0x3fc3d0, quantity 1); the 0x48-byte records differ in one 16-bit field, +0x2e: the value of the second modifier slot, whose id is −1 (unused). Machine A has 0, machine B 0x3f80. Address in pair 402: 0x4dfcd6. The item arrives through `Player_interact` on an `ItemProp`; where the dropped item got the differing bytes was not traced (**Inferred**: an unused field never initialised when the loot was made). Silent: no out-of-sync flag by the end of the run. Whether any reader looks at the value of an unused slot is not known |
| 406, tick 7541 (no bus delay) | the shared seed, then the out-of-sync flag at 7543 | **The summoned pet, through the prediction copy.** Machine B drew seven values that machine A did not. Break points on every named function for ticks 7540–7541 on both machines show why: in tick 7541 `CastBadger_run` (the pet of player 1's summon skill) took its attack branch on B (`GameObject_rand` from +0x2cc, `Creature_hitTargetInArc` from +0x314, then `damage_apply`) and its turn-toward-target branch on A (+0x360, +0x370). The pet object (0x630fc0 on both machines), logged every tick: creature flag word +0xac differs from tick 7481 (bit 0x8000000 set on A, the owner's machine); the animation fields from 7523; position and facing from 7524. With "Arena diagnostic: no prediction copy" added the pair is in step past tick 7961. So the pet's state was changed on its owner's machine by something the prediction copy did. Which instruction set the flag was not found |

### 9.3 The same twelve with the sections off

165,225 ticks; four fights won; **seven of twelve diverged**, all repeating:

| Pair | First difference | Follows |
|---|---|---|
| 402 | bag 2 of player 1, tick 4932 | as with the sections on (stale bytes) |
| 406 | seed, tick 7541 | as with the sections on (the pet) |
| 403 | bag 1 of player 0, tick 6253 | — |
| 404 | bag 0 of player 0, tick 8748 | — |
| 405 | bag 1 of player 0, tick 5306 | bag 2 of player 1 at 5308, hit points at 5373 |
| 409 | bag 2 of player 0, tick 7283 | **seed at 7372, out-of-sync flag at 7379** |
| 410 | bag 1 of player 0, tick 3663 | bag 2 of player 1 at 6920 |

The five that the sections remove are bag differences — an item or a potion in one
machine's copy of a bag and not the other's, which is what K1 (a pickup on the other
machine only) and K2 predict for the arena. (The sections include LAG-1, which changes
timing, so "removed" is not proof for each pair separately; the classes are K1's and
K2's.) One of the five became a seed difference and the game's out-of-sync message 96
ticks later; the other four were still silent when the run ended.

So in an ordinary skilled two-player fight of about four minutes, with these characters
and random but plausible input: K1 / K2 caused a divergence in 5 of 12 fights (42%), one
of them visible; with K1, K2 and LAG-1 patched, 3 of 12 still diverged, one visibly.
That is often, but it is not "every run" — and neither number includes the case below.

### 9.4 Two players of the same class with the spin skill (SB1): every pair, and a fix

States with both lobby models set to 0 (0x530338 and 0x53033c), both characters built
as the melee one above (`examples/pair-chars-same.rig`: the spin, id 41, on the first
ability button; mana refilled on both machines every 200 ticks), level `strife`, input
movement and the two ability buttons, bus delay 8, or 12 with jitter 4; K1, K2 and LAG-1
on.

| | Pairs | Ticks compared | Casts / spin updates (machine A) | Diverged |
|---|---|---|---|---|
| as shipped | 6 | 3,571 | 423 / 5,156 | **6 of 6**, first at ticks 786–1161 (within about 100–500 ticks of the input starting); positions first in five, seed and action state in one; in those five the out-of-sync flag followed 10–55 ticks later |
| with the patch below on both | 6 | 36,761 | 576 / 12,124 | **0** |

This is ledger row SB1 on the running game: `SpellCyclone_ctor` stores into event slot 0
of the spin animation clip, which all characters of the class share, at 0x2d1978 (mask
byte, clip +0x18) and 0x2d197c (time, clip +0x14), before its prediction-copy test at
0x2d19d0. The patch that was tested moves the two stores behind a copy test of their own:

| Address | Original word | New word | Meaning of the new word |
|---|---|---|---|
| 0x2D1978 | A0620018 | 08095EB9 | `j 0x257ae4` (was `sb $v0, 0x18($v1)`) |
| 0x2D197C | E4630014 | 00000000 | `nop` in the delay slot (was `swc1 $f3, 0x14($v1)`) |
| 0x257AE4 | 8E0300E8 | 8E01000C | `lw $at, 0xc($s0)` — the spell's caster |
| 0x257AE8 | 0040882D | 8C21000C | `lw $at, 0xc($at)` — the caster's flags |
| 0x257AEC | 2402FFCF | 00010C42 | `srl $at, $at, 17` |
| 0x257AF0 | 8E040024 | 30210001 | `andi $at, $at, 1` — the prediction-copy bit 0x20000 |
| 0x257AF4 | 00621824 | 14200003 | `bnez $at, 0x257b04` — a copy skips the stores |
| 0x257AF8 | AE0300E8 | 00000000 | `nop` |
| 0x257AFC | 0060282D | A0620018 | `sb $v0, 0x18($v1)` — the first original store |
| 0x257B00 | 0C05E554 | E4630014 | `swc1 $f3, 0x14($v1)` — the second |
| 0x257B04 | 8C84000C | 080B4660 | `j 0x2d1980` — back to the constructor |
| 0x257B08 | 02228826 | 00000000 | `nop` |

As patch-file lines: `patch=1,EE,<address>,word,<new word>` for the twelve rows. The ten
words at 0x257ae4–0x257b0b are inside the unused function `Cyclops_dropClub`, after the
twelve words the pose-cache section already uses.

- What it changes: a prediction copy's cast no longer writes the shared clip; the real
  cast, in the tick, still does.
- What could go wrong: `$at` is used as scratch — it is dead at that point (last used at
  0x2d1960 to load a constant); the caster pointer at spell +0xc is assumed set before
  0x2d1978, which the constructor's own unconditional read at 0x2d19c4 supports but which
  was not checked instruction by instruction; a copy's own spin, started ahead of the real
  one, runs without the event slot having been set by its own cast, so the owner may see
  the predicted spin end differently for a few frames (cosmetic, not looked at); and if
  `Cyclops_dropClub` is called after all, the game runs this code instead of it.
- Every machine with a same-class partner should apply it; a machine without it still
  shifts the other player's spin locally.
- Tested: the six pairs above, in an emulator, on the developer start. Not tested on a
  console, with the class's other spin id (84), or in the arena.

### 9.5 Not done

- The door from `drundar` with the quest state (step 4): not started.
- Items and a healing skill for the characters; lobby characters; more than one build.
- Which patch sections, if any, remove the stale-bytes and pet divergences: the automatic
  trial did not run (a mistake in how it was started), and only "no prediction copy" was
  tried by hand, on the pet case.
- The instruction that first writes each of those two differences.

## 10. Phase 5: the pet, the item bytes, everything on

Same limits as section 7; same twelve real-character pairs as section 9 (seeds 400–411).
**Ran** unless marked.

### 10.1 The pet (pair 406)

1. **With "creatures ignore being touched by the prediction copy" on both machines the
   divergence is gone.** It was run inside the all-on set of 10.3 (so the spin section was
   on as well, which this pair does not use): pair 406 stays in step to the end of the run
   and wins the fight.
2. **Who calls the handler with the copy as toucher: `Creature_moveBy` 0x113c48.** On the
   shipped code (K1, K2, LAG-1 on), a break point at `Creature_onTouch` 0x11a418 logging
   the toucher's flags (`$a1` +0xc): on machine A, which owns the pet's master, 3,271
   entries, **164 with flag 0x20000**, every one with return address 0x114228
   (`Creature_moveBy`+0x5e0, so the call is at 0x114220); the first in tick 7132. On
   machine B 3,107 entries and none with the flag. This is not the path guarded at
   0x14d9b0 in `obj_moveWithCollision`. (The caller of `Creature_moveBy` was not
   captured.) In pair 402 the same break point saw 1,483 entries on each machine and none
   with the flag: the copy does not always get there.
3. **Other touch handlers.** Logged the same way in pair 402: `Player_onTouch` 0x1beaf0
   (4,186 and 4,983 entries) and the gold pick-up touch 0x157a9c (679 on each machine) —
   none with the copy as toucher; the container, damager and fire handlers were never
   entered. In pair 406 only `Creature_onTouch` was logged. So the only handler seen firing
   for the copy is `Creature_onTouch`. Which classes the call at 0x114220 can reach was
   not worked out from the code; it hands the mover to whatever it touched, so in
   principle any (**Inferred**).

### 10.2 The item bytes (pairs 402 and 410)

| Question | Answer |
|---|---|
| The copy into the bag | `inventory_giveItem` 0x1c1868, called from `itemprop_tryPickup` 0x154dbc (+0x230) in tick 4932. The source record already differs at +0x2e: 0x0000 on machine A, 0x3f80 on B |
| Where the dropped item was made | the last item parse before it: tick 4741, `item_parseDescriptor` 0x1069b8 called from `loot_spawnNamedItem` 0x100ba0 (+0xa0) |
| Do the machines' buffers differ there | yes, in general: of 15,952 parser calls made identically on both machines, 3,868 found different bytes already at out +0x2c–0x2f |
| Is the prediction copy behind it | with "Arena diagnostic: no prediction copy" pair 402 has no shared difference in 13,970 ticks: yes, in the sense that without the copy the leftovers agree |
| Does zeroing the record first fix it | **no.** A test patch (jump at 0x1069b8 to twelve words at 0x257b0c that clear the 0x48 bytes at `$a1`, run the two displaced instructions and return) on both machines left pairs 402 and 410 diverging in the same ticks. So the differing value is not a leftover of the output record; the parser or its caller writes it from somewhere else that is uninitialised. Not traced further, and **no patch is proposed** |
| Who reads the bytes | nothing seen. `item_sameIdentityFields` 0x108924 ran 83,823 times in the pair but compares definition, flags and the word at +0x20 (its symbol note). `player_checksum` 0x1bdc98 was never entered, and its decompile reads record offsets 0x20–0x23, 0x58, 0x59, 0x5c, 0x90, 0xc0, 0xc4, 0xe4, 0xe8, 0x3748 and 0x43f0 — not the bags. Neither pair ever raised the out-of-sync flag, in any run |

### 10.3 The arena with every section on

The same twelve pairs, 14,000 frames each:

| Sections on both machines | Ticks compared | Fights won | Diverged | Which |
|---|---|---|---|---|
| none (the run of 9.3; not repeated) | 165,225 | 4 | **7** | 402, 403, 404, 405, 406, 409, 410 |
| K1, K2, LAG-1 (the run of 9.2) | 172,496 | 5 | **3** | 402, 410 (item bytes); 406 (the pet) |
| K1, K2, LAG-1, spin, touch | 180,701 | 6 | **2** | 402, 410 (item bytes, silent) |
| the same plus the record-zeroing test of 10.2 | 180,689 | 6 | **2** | 402, 410, unchanged |

With every published section on, no pair reaches the game's out-of-sync flag; the two
that still differ do so only in the two bytes of 10.2, which nothing was seen to read.
The baseline asked for (six pairs with everything off) was taken from the twelve of 9.3,
which are the same seeds, states and script.

### 10.4 Not done

The caller of `Creature_moveBy` in the copy's path; a static list of the classes
reachable from 0x114220; the real source of the item value; the touch section on pair
406 without the spin section.

## 11. Phase 6: every skill, other levels, and what the prediction leaves behind

Limits as in section 7. "All fix sections" is the list `FIXES` in `tools/rig/fuzz.py`: the
K1, K2 and K3 sections, the two lockout sections, the notice-box section, LAG-1, the spin
section, the touch section and the script-return section. **Ran** unless marked.

### 11.1 The skill sweep: no skill broke sync

The skills each class owns were read from the executable's skill-tree tables
(`g_skillTree0` 0x4f4898 and the six after it; rows of kind 1): 13, 16, 15, 15, 17, 15 and
13 ids for classes 0–6, 104 class–skill pairs in all. For each pair one run
(`tools/rig/sweep.py`): both machines' players that class (both lobby models set, states
`run6-<model>`), level 25, the one skill at rank 10 on the first ability button, mana
refilled every 150 ticks, level `strife`, 3,500 frames of seeded movement, attacks and
ability presses, bus delay 8 or 12 with jitter 4, all fix sections on. Seven more pairs,
one per class, with every passive at level 5.

| Class | Pairs | Ticks | Casts (machine A / B) | Skill ids with no cast | Diverged |
|---|---|---|---|---|---|
| 0 | 14 | 48,323 | 403 / 467 | 49, 38 | 0 |
| 1 | 17 | 60,042 | 684 / 758 | 34, 68 | 0 |
| 2 | 16 | 55,975 | 537 / 510 | 49, 40 | 0 |
| 3 | 16 | 56,079 | 937 / 830 | — | 0 |
| 4 | 18 | 63,615 | 944 / 980 | — | 0 |
| 5 | 16 | 55,346 | 963 / 1,178 | — | 0 |
| 6 | 14 | 49,362 | 654 / 641 | — | 0 |

**111 pairs, 388,742 ticks, casts on both machines in 101 pairs, no shared difference in
any.** The per-skill rows are in `sweep.tsv` (local). So with the fix sections on, no
skill breaks sync by itself the way the spin skill did — within what this run does: one
seed and about a minute per skill, the same class on both machines, level-25 characters
with starting items, the monsters of `strife`, and six skills that were never cast (they
are in the table). The sweep was not repeated with the sections off.

### 11.2 The two real-character builds in other levels

The builds of 9.1, all fix sections on, 12 pairs of 12,000 frames, one each starting in
`hub`, `blood1`, `bastion1`, `citadel`, `valor`, `storm1`, `fire1`, `nit1`, `wat1`,
`hub2`, `islc1`, `torment0`; half with bus delay 4, jitter 3, loss 5%; the full input mix
of 9.2: **135,555 ticks, no pair diverged.** Which of these levels have chests, shops or
save points was not checked.

### 11.3 What a prediction call leaves behind

`--predict-audit` copies EE memory from the start of the data sections up (0x3e9c00 to
0x2000000) at every entry of `net_predictLocalPlayer` 0x131d88 and compares at its
return. Ignored (`AuditIgnored` in `rig.cpp`): the main stack (above 0x1f00000), the
copy's own 0x590-byte block, the two prediction codec states (0x5bf6f8–0x5bf797), the
prediction pad history (0x5d14f0), `g_pads` and `g_netCamYaw`. Run on both machines of
arena pair 402 (real characters; K1, K2, LAG-1 on): 15,452 calls on machine A, and words
changed in 64 groups (60 on B). Grouped by symbol, or by 64 KB of heap; "calls" is the
largest number of calls in which one word of the group changed:

| Group | Words | Calls | Reading |
|---|---|---|---|
| `g_simFrame` | 1 | 15,314 | left one higher than at entry in nearly every call |
| camera and view (`g_cameraPos`, `g_cameraMatrix`, `g_viewProj…`, `g_terrainStamp`, and the words labelled `g_pathBusy`) | ~100 | 6,300–13,900 | the camera update the function is documented to do |
| pose cache (`g_poseLruHead` / `Tail`, `g_poseBuffers`, `g_animCacheLruHead`, heap 0x6f0000–0x7b0000) | ~150,000 | up to 13,267 | the pose cache of D34, rewritten by the copy's animation |
| particles, sound, HUD (`g_lifeTapBlockParticleDef` region, `g_goldPending`, `g_soundObjHandles`, `g_soundRpcClient`, `g_musicVolume`, `g_hudMessageFrames`, `g_cameraShake`, `g_padRumble`, `g_movie`, heap 0x800000–0x820000, 0x1300000–0x1480000) | several thousand | up to 7,818 | presentation, by the look of the symbols; not checked one by one |
| `g_cosmeticSeed`, 0x404468 | 2 | 294, 130 | the two unsynchronised generators |
| player record +0x4a40…+0x4ac0 | 16 | 2,827 | the weapon-trail and ability-button fields `docs/player.md` lists as written by the copy |
| **`g_pathQueue`** | 24 | 6,484 | route-plotting queue; floats moving in the last digits. To review |
| **`g_handleNodes`, `g_handleFreeList`** | 287 | 2,223 | the handle-node pool: the copy links and unlinks handles. To review |
| **`g_grid`, `g_offGridList`** | 12 | 1,256 | the world grid's cell lists. To review |
| **`g_scriptPostAction`** | 4 | 209 | the pending post-action of scripts (ledger E9's variable). To review |
| **heap 0x620000–0x630000, 0x6c0000** | 25 | 73 | the object pool: the pet of 9.2 sat at 0x630fc0, the players' objects at 0x6c88c0 — other objects changed by the copy. To review |
| `g_poolMemory` | 3 | 2 | pool allocation inside a prediction call |
| `g_receivedChecksums`, `g_zeroPad`, `g_streams`, `g_lobbyState`, `g_pauseMenuDebugTable`, `g_worldEmitterTypeCount`, `g_mouthDirRef` | 51 | ≤ 209 | not looked at |

This is a list of where to look, not a list of bugs: nothing here was traced to its
writing instruction, the symbol attached to an address is only the nearest one below it,
and whether the tick's simulation reads each group was not determined. The rows in bold
are the ones that are not obviously presentation. Of the known cases: the spin's clip
header and the pet's flag are instances of the object-pool row (both now patched); the
item bytes of 10.2 do not show up as a site of their own, so the audit does not name
their source.

### 11.4 Not done

The store log on the item's +0x2c–0x2f (step 3); the writing instructions for the audit's
top sites; the audit over the skill sweep and over more than one pair; per-object
resolution of heap addresses.

## 12. Phase 7: following the audit

Limits as in section 7. Every run here has all fix sections on (`FIXES`, section 11). Three
pairs: arena pair 402, arena pair 406 (the pet pair), and the same-class spin pair (states
`run5`, seed 500, bus delay 8). **Ran** unless marked.

### 12.1 Two new tools

- **The audit resolves objects and checks list order.** A changed word inside the object
  pool is reported as (class, field) through `g_poolClasses` 0x403a10 and the virtual table
  at +0x48 (`rig.py` now names the tables from `vtables.txt`); one in the tagged heap as
  the function that allocated the block (`g_heapFirstBlock` 0x6dffc8 points at the first
  block). After every call the audit also walks every cell of `g_grid` and `g_gridB` and
  the off-grid list, before and after, leaving the copy out, and counts the calls after
  which a list holds its real objects in another order, or other real objects.
- **`--predict-trace`: which instruction writes a word.** Play! has no write break points.
  The rig installs its own EE executor (a subclass; Play!'s source is untouched) whose
  break-point filter is called at the head of every translated block once a break point
  sits on every instruction. That is a call per block inside the executor, so the
  machine's timing is that of the same run without the trace (checked: each of the three
  pairs, run with and without it, audited the same number of calls and found the same
  number of changed words). A watched word (`--trace-range`) that differs from its shadow
  was written by the block entered before;
  writes are gathered by site, writing block and call chain (kept from the `jal` return
  addresses). `,all` on a range watches it outside the prediction calls too. A whole arena
  pair with the audit and the trace on one machine runs at 0.8 × real time. The writer is
  known to the block, not to the instruction: the store is then read in the block's few
  instructions. A word written by the emulator's own kernel emulation (not by game code)
  is blamed on whatever block was running; two such words turned up (0x508548, 0x8ee340:
  the "writers" are scattered over unrelated functions).

### 12.2 The audit with every fix on

74,522 prediction calls on the six machines. **No call left a grid cell or the off-grid
list with its real objects in another order, or with other real objects: 0 of 74,522.**
Words changed outside the ignore list, machine A of each pair (words / largest number of
calls in which one of them changed; machine B the same picture unless noted):

| Group | 402 | 406 | spin | What it is, and who writes it (trace) |
|---|---|---|---|---|
| `g_simFrame` | 1 / 15,314 | 1 / 15,306 | 1 / 6,346 | the prediction frame counter, 12.3 a |
| `g_terrainStamp` 0x44f08c, and the stamps in the level's terrain elements (heap blocks of `gob_loadAll`, 24–113 words) | 1 / 13,864 | 1 / 13,918 | 1 / 6,346 | visit counter of the terrain queries: 32 bits (`lw`/`beq` at 0x18338c–0x1833a0), compared for equality inside one query only. Harmless (**Observed**) |
| pose buffers and the pose list (0x791ec0–0x7b8344), animation decoder cache (0x6f0000–0x791e90) | ~150,000 words / up to 13,267 | same | same | the two animation caches, shared by the copy, the real objects and drawing. See the pool rows and 12.3 f |
| camera: `g_cameraPos`, `g_cameraMatrix`, `g_viewProj…`, 0x44f0a8–0x44f104 and 0x7d5c08–0x7d5c64 (labelled `g_pathBusy`, `g_pathQueue` in section 11: wrong), 0x7d89d8, 0x86ad80–0x86aed4 (labelled `g_goldPending`: wrong) | ~130 / 6,500 | same | fewer | `Camera_update` → `Camera_updateFollow`, `Camera_followCollide`, `camera_buildFrustum`. Presentation |
| particles and trails: 0x87072c–0x870780 (labelled `g_scriptPostAction`: wrong), 0x44facc–0x44fca4, 0x8657a0, 0x82d104…, 0x7e0000–0x810000 | thousands / up to 7,818 | same | few | `particle_spawn` ← `fx_modelParticlesNearCamera` ← `Creature_run` ← `Player_run`; `trail_create` ← `Player_weaponTrails`. Presentation |
| sound, voice, HUD, rumble: `g_soundObjHandles`, `g_soundRpcClient`, `g_streams`, `g_musicVolume`, 0x8723e8, 0x86ab7c (labelled `g_receivedChecksums`: wrong; `hud_showMessage`), `g_hudMessageFrames`, `g_padRumble`, `g_cameraShake` | ~120 / up to 369 | same | few | `sound_playOnObject`, `sound_playFoley`, `player_voice`, `hud_showMessage`, all from `Player_run`. Presentation |
| `g_cosmeticSeed`, 0x404468 | 2 / 294, 130 | 2 / 682, 139 | 1 / 27 | the unsynchronised generators: particles, foley, camera shake, voice; 0x404468 by `Player_run` itself |
| the local player's record +0x4a80…+0x4ac0 | 16 / 2,827 | 16 / 4,375 | 15 / 703 | weapon-trail and ability-button fields (`docs/player.md`) |
| `g_handleNodes`, `g_handleFreeList` | 287 / 2,223 | 317 / 1,913 | 20 / 69 | the copy's handles, 12.3 b |
| `g_grid` heads, `g_offGridList` | 12 / 1,256 | 11 / 974 | 5 / 81 | the copy's own cell membership, 12.3 b |
| **pool, field +0x0** of `Horsemen`, `Skelight`, `Cazic`, `CastBadger`, `AutoProp`, `PhProp`, `Gold`, `PoisonBolt`, `DiseaseBolt` and of the real `Player` objects | 15 / 73 | 16 / 52 | — | the object's list of handles that point at it: the copy took or dropped a handle to it, 12.3 b |
| **pool, animation cache pointers**: `Player` +0x120, +0x140, +0x160, +0x180, +0x1a0; `Horsemen` +0x120; `AutoProp` +0x98, +0xa4; `HackDoor` +0xa4; `Gold` +0x58, +0x64 | 13 / 1 | 17 / 2 | 8 / 4 | a pointer into one of the two caches set to 0: the copy's animation took the cache entry of a real object. Up to 9 calls per field on machine B. 12.3 f |
| pool, a free block; `g_poolLastBlock` | — (B: 109 / 7) | — (B: 72 / 8) | 48 / 4 | the spin effect object made and destroyed inside the call, 12.3 e |
| **`g_pathQueueWrite` and queue entries** | — | 1 / 45 (B: 49) | — | the copy queues route requests, 12.3 d |
| 0x508548, 0x8ee340 | 2 / 1,134 | 2 / 1,420 | 1 / 13 | counters written from outside the game's code (12.1) |
| one heap block whose allocator field points into `frustum_testBox` | 20 / 3 | 20 / 3 | 244 / 108 | not identified |

So with every fix on, a prediction call changed two kinds of field in objects other than
the copy and nothing else: the head of the "who points at me" handle list (+0x0), and
animation cache pointers. No position, flag, hit point or state field of a real object
changed in any of the 74,522 calls. The spin's clip header and the pet's flag of section 11
are gone from the table.

### 12.3 The six questions

**a. `g_simFrame` — harmless.** It is the prediction frame counter outside a tick, by
design. `net_frameLoop` saves it and sets it to `g_netFrame` before the tick (0x139fb8,
0x139fdc) and puts the saved value back after `tasks_run` and `path_service`
(0x13af80–0x13af98). The prediction adds one per predicted frame (0x132ca0–0x132cd4), and
the rebase stores a new value (0x13b28c). Traced over a whole pair with the range watched
everywhere: every tick is bracketed by the two stores, so tick code always reads
`g_netFrame`. The saved value also goes into the sync record (+4, 0x13afa0), which
`docs/netcode.md` already lists as not compared.

**b. Grid lists and handle nodes — only the copy.** The order check above is the answer
for the lists the simulation walks: 0 of 74,522. `g_offGridList` is written by
`obj_moveWithCollision` ← `creature_moveSimple` ← `Player_move` ← `Player_run` when the
copy itself leaves the grid. Every change of `g_handleFreeList` inside a prediction call,
by call chain (pair 402 / 406 / spin, machine A):

| Chain | Count | What |
|---|---|---|
| `handle_link`, `handle_clear` ← `Player_run` (0x1aa32c–0x1aa554) | 410 / 219 / 0 | after `world_collectObjectsInBox`: the copy's list of nearby objects (+0x4b8) and its target (+0x234). These put a node into the real object's +0x0 list |
| `handle_link`, `handle_clear` ← `sound_playOnObject`, `sound_playAtPos` ← … ← `Player_run` | 372 / 389 / 2 | sound handles |
| `handle_link` ← `path_requestToPoint` | 0 / 90 / 0 | the requester handle of d |

The nodes come off one free list, so which node a real link later gets differs between
machines; the lists' contents and order do not. Nothing was found that reads a node
address (compare ledger O8), and nothing but `handle_clear` at destruction walks an object's +0x0
list (`docs/objects.md`).

**c. `g_scriptPostAction` — not written.** The words section 11 put under that name are
the particle pool (table above). The variable itself (0x86fa80, 32 bytes watched) was not
written inside any of 37,262 traced calls. Its only writers in the executable are
`script_resetState` 0x1eda90, `script_setPostAction` 0x1edab0 and `script_runPostAction`
0x1edae8 (**Observed**, `tools/gxref.py`); the copy's `Player_run` reached none of them.

**d. The route queue — the copy does queue requests; no effect on shared state shown.**
In pair 406 the copy called `Creature_moveToDest` from `Player_run` 0x1a5604 (the player's
walk-to-a-destination state) and through `Creature_advanceWaypoint` →
`Creature_requestPath` → `path_requestToPoint` put 45 requests into the real queue on
machine A (49 on B), ticks 11078–13766, advancing `g_pathQueueWrite` 0x44f09c. They are
answered by the blocking `path_service(1)` of the next tick, like every request, so no
monster is answered earlier or later (**Observed**, `docs/engine.md`). The answer is
delivered to the requester's slot 7, `Creature_onPathResult` 0x11a260, which stores four
fields of the requester — the copy — and calls nothing (**Observed**). The pair stayed in
step through those ticks. What is left: the search for the copy's request runs inside the
real tick on one machine and leaves its marks in the shared route grid; marks that the
next search's clearing flood does not reach stay and block later searches
(`docs/spec/world-queries.md` 10.3). Whether a copy's search can leave such marks was not
tested (**Unknown**).

**e. Allocation inside a prediction call — one object, freed in the same call.** The pool
free heads (0x403a1c, 0x403a2c, 0x403a3c) and `g_heapFreeBytes` were watched for all
37,262 calls. Pairs 402 and 406, machine A: no write. Spin pair: `pool_new` ←
`SkillCyclone_cast` ← `Player_castSkill` ← `Player_run`, then `SpellCyclone_dtor` ←
`Player_castSkill`, 8 times: the spin's effect object, a 0x180 block, made and destroyed
within the call. The free head is the same at return; the freed block keeps the object's
bytes (the audit's "free block" rows), which `pool_new` clears when it hands the block out
again. On machine B of the arena pairs, whose player has the spin skill, the same rows
appear. ST1 stands for these runs. No tagged-heap allocation or release in any call.

**f. The item bytes — found.** The other words (`g_receivedChecksums`, `g_zeroPad` in
section 11) were mislabelled: a HUD message buffer and animation cache bookkeeping. The
item bytes of 10.2 (V23) come from the stack, in four steps, each traced on pair 402 on
both machines (`--trace-range …,all`):

1. `item_parseDescriptor` 0x1069b8 builds a default record in a local at `sp+0xd0` and
   copies all 0x48 bytes of it over the caller's record (0x106a58–0x106a94) before it
   parses anything. The default initialiser (0x1069f8–0x106a48) sets 26 of the 72 bytes
   (−1 in the halfwords at +0x24, +0x2c, +0x34, +0x3c and the bytes +0x20, +0x21; 0 in
   +0x10…+0x1f). The other 46 bytes are whatever the stack held. **Observed**; this is why
   clearing the caller's record did nothing (10.2).
2. In tick 4741 the bytes at +0x2e of that local (0x01ffccce) were 0x0000 on machine A and
   0x3f80 on B, and the parser's copy carried them into the record (writing block
   0x106a58), from where `PhProp_ctor` 0x155ad4 copied them into the dropped item
   (object 0x630fc0, +0x174).
3. On B the word had last been written, in the same tick, by `anim_buildPose` ←
   `anim_getJointMatrix` ← `model_getAttachPoint` ← `Creature_processDamage` ←
   `Horsemen_run`: 558 writes to those 72 bytes of stack in ticks 4739–4741, the last of
   them in tick 4741. On A `anim_buildPose` did not write there in those ticks at all.
4. So the dying monster's pose was in the cache on A and had to be rebuilt on B, inside
   the tick. The pose is the same either way; the stack it leaves behind is not. The
   audit's pool rows show a prediction call taking the cache entry of a real object;
   that B's entry was lost that way is **Inferred** (with "no prediction copy" the pair
   has no difference, 10.2).

The general statement: **what a tick leaves on the stack differs between machines**,
because the animation caches differ (and prediction calls and drawing run on the same
stack between ticks). Any function of the tick that reads a local it did not write picks
that up. The item parser is the one instance found; the same inlined initialiser occurs at
151 places in the executable (pattern: `sb` −1 to +0x21 and +0x20 of a record), most of
them followed by the parser, which overwrites the whole record.

### 12.4 A fix for the item bytes (proposal)

Replace the parser's default initialiser, in place, by one that clears the whole local
first. 21 words, 0x1069f8–0x106a48; no branch from outside enters that range (checked in
the disassembly). Original words read from the executable:

| Address | Original | New | Meaning of the new word |
|---|---|---|---|
| 0x1069f8 | 27a600d0 | 27a600d0 | `addiu a2, sp, 0xd0` (unchanged) |
| 0x1069fc | 24050020 | fcc00000 | `sd zero, 0x00(a2)` |
| 0x106a00 | 24040003 | fcc00008 | `sd zero, 0x08(a2)` |
| 0x106a04 | 00c51021 | fcc00010 | `sd zero, 0x10(a2)` |
| 0x106a08 | 24a50008 | fcc00018 | `sd zero, 0x18(a2)` |
| 0x106a0c | 2403ffff | fcc00020 | `sd zero, 0x20(a2)` |
| 0x106a10 | 2484ffff | fcc00028 | `sd zero, 0x28(a2)` |
| 0x106a14 | 00000000 | fcc00030 | `sd zero, 0x30(a2)` |
| 0x106a18 | 0481fffa | fcc00038 | `sd zero, 0x38(a2)` |
| 0x106a1c | a4430004 | fcc00040 | `sd zero, 0x40(a2)` |
| 0x106a20 | a0c30021 | 2403ffff | `addiu v1, zero, -1` |
| 0x106a24 | 24040010 | a4c30024 | `sh v1, 0x24(a2)` |
| 0x106a28 | a0c30020 | a4c3002c | `sh v1, 0x2c(a2)` |
| 0x106a2c | 24050003 | a4c30034 | `sh v1, 0x34(a2)` |
| 0x106a30 | 00c41021 | a4c3003c | `sh v1, 0x3c(a2)` |
| 0x106a34 | 24840002 | a0c30021 | `sb v1, 0x21(a2)` |
| 0x106a38 | 0040182d | a0c30020 | `sb v1, 0x20(a2)` |
| 0x106a3c | 24a5ffff | 00000000 | `nop` |
| 0x106a40 | a4400000 | 00000000 | `nop` |
| 0x106a44 | 04a1fffa | 00000000 | `nop` |
| 0x106a48 | a4600008 | 00000000 | `nop` |

What it changes: the fields of an item record that the descriptor does not set are 0 on
every machine instead of stack leftovers. The registers the code after it uses are as
before (`a2` = `sp+0xd0`; `v0`, `v1`, `a0`, `a1` are loaded again at 0x106a4c–0x106a58).

**Tested on the rig only** (Play!; not on PCSX2 or a console): the twelve arena pairs of
9.2 with every fix section and these 21 words on both machines: **180,701 ticks, no pair
differs** — pairs 402 and 410, which differed in two item bytes with every section on
(10.3; pair 402 again today at tick 4932), included.

What could go wrong: a field that held a leftover now holds 0. A leftover was arbitrary,
so code reading such a field had to cope with any value already (**Inferred**; nothing was
seen reading +0x2e, 10.2). Only the arena was run. Records built without the parser keep
their own leftovers (the other inlined initialisers were not followed). Every player must
apply it: a patched and an unpatched machine agree no better than two unpatched ones.

### 12.5 Proposed ledger rows

| Row | Text | Kind |
|---|---|---|
| V27 | With every fix section on, 74,522 prediction calls on three pairs changed, in objects other than the copy, only the handle-list head +0x0 and animation cache pointers; no grid cell or off-grid list changed the order or the set of its real objects | Ran |
| V28 | `g_simFrame` is the prediction frame outside a tick; the tick saves it, runs on `g_netFrame`, and restores it (0x139fb8, 0x139fdc, 0x13af98). Harmless | Observed, Ran |
| V29 | The copy queues real route requests in the walk-to-destination state (`Player_run` 0x1a5604; 45 and 49 in pair 406). Answered in the next tick into the copy; the pair stayed in step. Marks left in the route grid by that search: not tested | Ran; Unknown |
| V30 | V23's source: `item_parseDescriptor` copies a local default record of which 46 of 72 bytes are uninitialised; the stack differs between machines because a pose is rebuilt inside the tick on the machine whose cache lost it. 21-word fix, 12 arena pairs clean | Ran |
| V31 | The only allocation inside a prediction call in these runs is the spin effect object, freed in the same call | Ran |

### 12.6 Not done

- Whether the copy's route search can leave marks in the route grid (12.3 d).
- The other 150 inlined record initialisers: which of them are not followed by the parser.
- Other locals read before written in tick code; the stack finding says this class exists,
  one member was found.
- The heap block attributed to `frustum_testBox`, and the two counters written from
  outside game code.
- The trace on machine B, and the audit over the skill sweep.

## 13. Phase 8: the real online path

Goal: the game's own network stack — the eleven IOP modules of 4d, with no hook at the EE
level — reaching the replacement lobby server on this machine, signing in, and launching a
game through the lobby. Limits as in section 7; in addition, host sockets make these runs
depend on real time, so they do not repeat exactly. **Where it got:** two machines connected to the lobby server
over the game's own stack, at the server's terms screen (13.5 says why it stops there).

### 13.1 What the game asks for first: a network configuration (**Ran**)

"Internet Game" in the front end starts the network menu. With no network configuration
on the memory card it stops there and offers to configure one, which restarts the machine
into the network configuration program on the disc (`NTGUI2.ELF`, Sony's). That program
draws its own text, so the rig's text transcript shows nothing of it. Two additions to the
runner made it usable:

- `--video` runs Play!'s OpenGL video handler on a context without a window, and the
  script command `shot <file.bmp>` writes a picture of the screen (macOS; built in unless
  `-DRTA_RIG_VIDEO=OFF`). Pictures are game output: they stay under `local/`.
- `--eth-pcap <file>` records every Ethernet frame the emulated chip sends or is given, in
  the capture format `tcpdump -r` reads.

With pictures, scripted input walks the configuration program: add a setting, memory card
slot 1, the Ethernet adaptor (it is found), no PPPoE, automatic address, automatic DNS.
It then tests the connection, and **the game's own stack transmits**: DHCP requests from
22:11:22:11:66:44 (the address in Play!'s chip emulation) to the broadcast address, one
every four seconds. That is the first traffic on the emulated wire.

### 13.2 A network behind the chip, and the configuration saved (**Ran**)

`--eth-net server=<address of this host>` puts a small network behind the emulated chip
(`rig.cpp`, the `Ether…` functions; nothing in Play! is changed). The machine is alone on
10.0.2.0/24 with the rig as gateway 10.0.2.2. The rig answers ARP for every address but
the machine's own, DHCP (the machine gets 10.0.2.15), ping, and DNS: `con.soegames.net`
gets the server's address and every other name "does not exist". UDP and TCP to the
server's address are relayed through host sockets — one host UDP socket per port of the
machine, and TCP ended in the rig (the machine only opens connections) and carried on a
host TCP connection. Nothing is relayed to any other address, so this network cannot
reach the Internet. Two runners each have their own; they meet through the host's sockets,
which is also where the server sees them.

Two defects of Play!'s chip emulation are worked around from the rig, by reaching one
private member of `Iop::CSpeed` (the header is included with `private` redefined — a
wart, but the alternative is a patched Play!): its receive ring index wraps at 512 where
the ring has 64 entries, and it is not reset when the driver starts again after the
machine restarts into another program. The chip holds one received frame at a time; the
rig queues frames and hands over the next when the driver has taken the last.

Result: the configuration program's connection test succeeds — discover, offer, request,
acknowledge, the machine's address probe and its ARP for the gateway are all in the
capture — and the program saves the setting. The files are the real thing, written by
Sony's module (`BWNETCNF` with an index, one combination file and two encoded setting
files, and the icon), in the memory card directory. Back in the game, "Internet Game" now
lists the setting ("ezNetCnfGetCount> returned 1" on the console output).

A trap found on the way: Play! stores the memory card directories in the data
directory's `config.xml` as absolute paths, so a *copied* data directory went on using the
cards of the one it was copied from. The runner now sets these paths from `--data` on
every start. (Earlier phases are not affected in their results — pairs start from saved
states and never read the card — but their "fresh copies" of the card directories were
not separate cards.)

Saved states cannot be used on this path: the chip's state is not part of a Play! state,
so after loading one the driver and the chip disagree. Every run here starts from
power-on (about 1,500 frames to the network menu).

### 13.3 The sign-in step, as shipped and with the local sign-in patch (**Ran**)

Accepting the setting in the network menu brings the interface up (DHCP as above). Then:

**As shipped.** The game loads its three sign-in modules, reports the check initialised,
and the stack sends a DNS query for Sony's authentication host. The rig's DNS answers
that the name does not exist; the game shows network error −611. So the sign-in code
runs on Play! as far as it can without Sony's servers. One more thing was seen:
cancelling that error makes the game unload the modules, the unloader reports a failure
on the console output, and the network menu no longer reacts to input. Whether that
happens on a console is **Unknown**; on the rig a failed sign-in ends the run.

**With the local sign-in patch**, applied in the front end before "Internet Game" is
chosen: no sign-in screen appears. About 40 frames after the address is acknowledged the
game says it is connecting, and the lobby client starts. The flag the real check sets on
success (0x507270) stays 0, and the lobby client does not mind. This is the first run of
that patch on a running game: it does what X4 found by executing the function alone.

### 13.4 Gateway and lobby: connected (**Ran**)

Machine A, then A and B at once (two runners, each with its own card and its own network
behind the chip, both relayed to the server on this host):

| Step | On the wire (the game's stack, through the rig) | Result |
|---|---|---|
| name lookup | DNS query for `con.soegames.net`, answered with this host's address | — |
| gateway, TCP 40810 | request 0x43, tracking number 1, version 6, body `u32` 12 (18 bytes with the length word) | reply 35 bytes: result 0, the server's address as text, the lobby port. The game closes the connection (and sends a reset after its close) |
| lobby, TCP 40910 | request 0x27, tracking number 2: a string of 32 hexadecimal digits, then `u32` 12 | reply 54 bytes: result 0, length words, 32 bytes of key. Accepted |
| | request 0x42, tracking number 3: the strings `en` and `us` | reply 492 bytes: the server's welcome text, which the game shows as its terms screen |

Every message is as `docs/lobby-protocol.md` sections 2, 4 and 5 describe; the game's
console output reports result 0 for all three. **No disagreement between client and
server so far.** Three details the protocol notes did not have:

- the string in 0x27 (its meaning is an open question there) is 32 hexadecimal digits,
  and it was the same on both runners — so it is derived from something the two identical
  machines share, not random per connection;
- the two strings of 0x42 are `en` and `us`: language and region;
- the game sends each message as two TCP segments, the length word first.

With both runners at the terms screen the server holds two established connections on
port 40910, one from each runner process.

### 13.5 Where this stops, and why

At the server's terms screen, on both machines. The next two actions are accepting those
terms and then creating an account (a name and a password) on the lobby server. Both are
things this assistant does only on the user's own say-so, and this phase's instructions
came from the coordinating agent. Technically nothing stands in the way: the server is
this host's own process, the account would be a throw-away one, and the screens are the
game's own text, which the transcript shows. The continuation is:
`tools/rig/examples/online-lobby.rig`, then cross on the terms screen, the account
screens, a character, a game on A, the same on B with "join" — and from the first UDP
datagram on, the capture files show what the UDP relay and the peer handshake do.

### 13.6 Not done, and what is untested in what was built

- Everything after the terms screen: accounts, characters, creating and joining a game,
  the launch handshake, play, and the arena with lobby characters (steps 3 and 4).
- **The UDP relay has carried no datagram yet** (the game sends none before log-in), and
  the path between two runners through host UDP sockets is therefore untested. The
  server will see both runners at this host's address with different ports; whether the
  game's peer handshake works through that is the first thing the next run shows.
- The TCP relay has carried a few hundred bytes each way. Loss cannot happen on this
  wire, so its retransmission code has not run.
- The chip delivers one frame per hand-over, at most a few per displayed frame. That is
  enough for a lobby; whether it is enough for game traffic is **Unknown**.
- Play!'s OpenGL handler was used for pictures only; nothing was checked about its
  correctness, and runs with `--video` are slower.

## 14. Phase 9: sections not yet exercised, the route grid, pair 410

The developer LAN pair of sections 7–12 again. Limits as in section 7. **Ran** unless marked.

### 14.1 U1, the option commit and the button maps: reproduced, and the section removes it

Script `tools/rig/examples/pair-u1.rig`, placeholder characters in `strife`, no bus delay.
In tick 680 the button map of slot 1 (machine A's player) gets attack and block exchanged
on both machines (`g_btnAttack`+4 = 0x08, `g_btnBlock`+4 = 0x40) — what the launch
handshake would deliver for a player who remapped them. Machine B then opens its pause
menu, the option list, changes the music volume, leaves the list and answers the save
question with no. Then A's player presses the button that is attack by default.

| | Without the section | With "option commit leaves the button maps alone" on both |
|---|---|---|
| B's tables after leaving the option list | all four slots back to B's own layout (slot 1: attack 0x40, block 0x08); A's unchanged | unchanged on both |
| first difference | tick 1089, the button-map checksum, the tick in which B's commit ran | none in 898 ticks |
| the press | tick 1259: the player's action state differs (it blocks on A and attacks on B); position from tick 1260 | the same on both |
| the game's own flags | out-of-sync set for both players at tick 1270; the lockstep stops at tick 1272 | never set |

U1 is confirmed on the running game, and so is its section.

### 14.2 D26: not reproduced in eight forced trials

From the arena-entrance states with placeholder characters: both players in the crowd, A's
inventory open, both players' hit points raised to 5,000 at tick 900 and A's player set to
1 at tick T on both machines (T = 1800 … 3900 in steps of 300; `local/rig-out/p9-d26.sh`).
None of the eight pairs showed a shared difference in 3,598 ticks. That is not a result
about D26: the difference needs a damage call on the other player in the rest of the tick
in which the owner dies, and whether that happened in any trial was not established (the
attempt to read it from the tick logs failed and was not repaired). D26 and its companion
section stay unexercised.

### 14.3 E9, U2, K3: not attempted

Each needs a scripted situation of its own (a pending post action with a notice box open;
the mission or jump-gate menu with another player's pause menu; a dual-wielding character
with the stats page open and a projectile in flight). None was built.

### 14.4 The route grid after the copy's requests (V29)

Pair 406 with every fix section and the item-record one. All four request functions were
logged on both machines, and every 150 ticks from 11000 to 14600 the route grid (65 × 55
nodes at world +0x38), the request queue with the search rings and goal variables
(0x7d35e0–0x7d89e0) and the search globals (0x44f090–0x44f0a7) were dumped inside the
tick hook.

- Requests: 38 inside a tick on each machine, in the same ticks (2372 … 10326). Outside
  a tick — the copy's — 45 on A (ticks 11078 … 13766) and 49 on B (7042 … 13762), at
  different ticks on the two machines.
- **At all 25 sample ticks the two machines' route grids (links, marks and block counters
  of all 3,575 nodes), queues, rings and globals were byte for byte the same.** Up to 515
  marked nodes were present at a sample, the same ones on both.

So in this pair nothing that differs between the machines was left in the path-finding
memory by the copies' searches. Two reservations. The samples show the same
previous-start node on both machines every time, so the two copies' searches may have been
the same search here (both players walking the same way); a pair in which only one
machine's copy walks would be the stronger test. And the queue's write index is not
monotonic over the samples (65, then 64; 74, then 71): something sets it back, which was
not looked into. Whether a search's marks can survive the next search's clearing was not
tested directly either.

### 14.5 Pair 410, same day

| Sections on both machines | Result |
|---|---|
| every fix section of section 11 | first difference at tick 6920, the second bag checksum of player 1 (as in 10.3) |
| the same plus "item records start from zero, not from stack leftovers" | 15,324 ticks, no shared difference |

Both pairs that differed in two item bytes now have a with and a without result from one
day each (402 in section 12, 410 here).

### 14.6 Not done

D26 (inconclusive), E9, U2, K3; a one-sided test for 14.4; the non-monotonic write index.

## 15. Phase 10: D26 on the running game

Limits as in section 7. Developer LAN pair, placeholder characters, the arena-entrance
states, no bus delay. **Ran** unless marked.

### 15.1 What was set up

Break points at the gate in `Player_run` (0x1a5ba8, a block start) on both machines show,
for every tick, which player objects reach it and in what order: the machine's prediction
copy before the tick, then **slot 1, then slot 0**. So the player that has to die is
slot 1 — machine A's own — with A's inventory open, and the player that runs after it is
slot 0, machine B's. Script (`local/rig-out/p10-d26.sh`): both players into the crowd,
A opens its inventory, both players' hit points set to 5,000 at tick 900 and slot 1's to
1 at tick 2400 on both machines; B's pad presses weapon swap (L1, mask 0x04 in
`g_btnWeaponSwap`) every other frame from then on, in two runs with the presses one frame
apart so that one of them has a press in any given tick.

### 15.2 What happened in the death tick

Slot 1 died in tick 3001 in every run; `net_closeLocalMenus` ran on A in that tick and
not on B.

| In tick 3001 | Without the sections | With the two lockout sections on both |
|---|---|---|
| lockout word 0x41b4fc when slot 0 reaches the gate | A: 60, B: 0 | A: 60, B: 0 (the section stops the code reading it) |
| `Player_weaponSwapInput` called for slot 0 | **A: no, B: yes** | A: yes, B: yes |
| ticks before and after | word 0 on both, the call made on both | the same |

So the mechanism of D26 is confirmed on the running game: for the rest of the tick in
which the local player dies with its inventory open, that machine alone skips weapon swap
(and, behind the same test, interact) for the player that runs after it; and "menu
lockout never blocks weapon swap and use" removes that difference. Both press phases gave
the same picture.

### 15.3 What was not shown

**No shared value differed** — the tick logs of all four runs agree in every column. The
swap that machine A skipped would have changed nothing: in 600 ticks of presses the
weapon-set word (record +0x4a7c) of the placeholder character never changed on either
machine, so for this character the swap is empty (`Player_weaponSwapInput` toggles the set
"in state 2", per its symbol note; which condition failed was not looked at). A visible
divergence needs one of: a character for whom the swap does something (a second weapon
set), something to interact with in reach of slot 0 in that tick, or a damage call on
slot 0 after slot 1's death in the same tick — which is the other half of D26
(`Player_takeDamage`, test at 0x1b53d4) and did not occur in tick 3001. The damage section
"menu lockout never drops player damage" was on in the patched runs but was not exercised.

### 15.4 Not done

E9, U2, K3 and the one-sided route-grid test were not started: the D26 work used what
this session had left. For D26 the next step is the same script from the real-character
states (`run4`) with a second weapon set written into slot 0's record, or a monster made
to hit slot 0 in the death tick.

## 16. Phase 11: live reproductions for the sections not yet exercised

The developer LAN pair again; limits as in section 7 (two copies of one Play! build — not
a PlayStation 2 and not PCSX2 — so only logic differences can show). Each part gives one
run without the section (first differing tick and value) and one with it. **Ran** unless
marked. Scripts: `tools/rig/examples/pair-d26.rig` and the others named below.

### 16.1 D26, both halves: reproduced, and each section removes its half

**Set-up.** The real-character states (`run4`: slot 0 a melee class, slot 1 the lobby's
caster; level 25 by `pair-chars.rig`), into the arena as before. Three things are written
identically on both machines, each in one lockstep tick:

- *A second weapon set for slot 0.* The weapon set is not a free choice: the equip code
  (0x1c27c0) files a weapon under set 1 when its animation class (definition +0x1e) is 4
  (bow) or 6 (thrown) and under set 0 otherwise, and `Player_weaponSwapInput` only moves
  to a set whose primary weapon pointer (record +0x4434, +0x4438) is not null
  (**Observed**). A copy of the character's own sword as "set 1" is therefore refiled as
  set 0 at the first swap (**Ran**: the set word stayed 0). What works is a bow: a record
  for the first row of `g_itemDefs` (a short bow) in the second cell of bag 0, the bag's
  count 2, and its address in +0x4438. Each swap press in state 2 then toggles the set
  word +0x4a7c between 0 and 1, equips the other weapon and changes the stored attack
  rating and damage (+0xcc, +0xd0, +0xd4: 559 / 58 / 62 with the sword, 547 / 45 / 49 with
  the bow) — the same on both machines.
- *The death, in a chosen tick.* Slot 1's object gets 99,999 pending damage (+0xc8) at the
  end of tick 2399, so it dies in its own run of tick 2400, with machine A's inventory
  open. Until then both players' hit points are topped up every 30 ticks.
- *A damage call on slot 0 in that tick.* In a reference run of 1,198 ticks there were 61
  damage calls on the real players, all on slot 1: 51 before either player reached the
  gate at 0x1a5ba8 and 10 between slot 1's gate and slot 0's (one every 30 ticks, a
  lasting effect on slot 1); none after slot 0's gate. The arena's monsters run before
  the players in a tick, so a monster's swing cannot fall into the rest of the death tick
  here. A damage-over-time status can: slot 0's object is given the poison status
  (+0x34c = 30 s, +0x358 / +0x35a = 50), for which `Creature_run` calls `damage_apply` on
  the object itself in every tick whose number is a multiple of 32 (0x113884–0x1138b0).
  Tick 2400 is one, and the two calls it makes there fall between slot 1's gate and slot
  0's.

Machine B presses weapon swap every other frame; the script's phase puts a press into
tick 2400 (column `pad0p`).

**Tick 2400, no section** (break points on `net_closeLocalMenus`, the gate, the swap
function and `Player_takeDamage`, both machines):

| | Machine A (owner of the dead player, inventory open) | Machine B |
|---|---|---|
| `net_closeLocalMenus` | entered once, from slot 1's death | not entered |
| lockout word 0x41b4fc from then on | 60 | 0 |
| `Player_takeDamage` for slot 0 (two calls, the poison's) | entered with the word at 60 (the test at 0x1b53d4 then leaves) | entered with 0: damage taken |
| `Player_weaponSwapInput` for slot 0 | not called | called |
| slot 0's hit points at the end of the tick | 801.794 | **799.794** |
| shared seed at the end of the tick | 0x1654a488 | **0x29917e47** (one draw ahead) |
| slot 0's weapon set (+0x4a7c); attack rating / damage | 0; 559 / 58 / 62 | **1**; 547 / 45 / 49 |

Seven pairs from one pair of post-cutscene states, 1,200 frames each
(first differing tick, columns; then what followed):

| Poison on slot 0 | Sections on both machines | Result |
|---|---|---|
| no | none | tick 2400: weapon set, equipment, stored damage. The players then hold different weapons; seed and action state differ at 2934, out-of-sync flag at 2936 |
| no | weapon swap and use | **no shared column differs** (1,198 ticks) |
| no | player damage | as with none (the section does not concern the swap) |
| yes | none | tick 2400: seed, slot 0's hit points, weapon set, equipment, stored damage; out-of-sync flag at 2402 (B for peer 1) and 2404 (A for peer 0); the lockstep stops |
| yes | weapon swap and use | tick 2400: seed and hit points only; out-of-sync flag at 2402 |
| yes | player damage | tick 2400: weapon set, equipment, stored damage only; seed at 3175, flag at 3177 |
| yes | both | **no shared column differs** (1,198 ticks) |

So both halves of D26 are real on the running game, each of the two sections removes
exactly its own half, and the damage half is not silent: the dropped call also skips a
draw from the shared generator, and the game's own check trips two ticks later.
`examples/pair-d26.rig` is the whole thing in one script from the `run4` states; run as
published it gave the same four results (none / swap / damage / both: tick 2400, tick
2400 seed and hit points, tick 2400 weapon set, nothing in 2,902 ticks).

What this does not show: a monster's hit falling into the window (in this level the
monsters run first), the interact half of the swap section's gate, and the two other
routes to a non-zero lockout word that D26 names (the medal countdown; the jump gate).

### 16.2 E9, the notice box and the pending script: reproduced, and the section removes it

Script `tools/rig/examples/pair-e9.rig`, level `strife`, the `run4` states as they are
(level-1 characters), no bus delay.

- *A pending post action.* In tick 690 the name of an entry point of the level's script is
  written into `g_scriptPostAction` 0x86fa80 on both machines — what the script built-in
  `postAction` leaves there. The entry chosen sets one quest variable (the fourth scout's
  "talked to" flag), lowers a bridge and removes a quest line.
- *A notice on one machine.* Slot 0 (machine B's player) gets a second weapon set it
  cannot wield: the bow record of 16.1 with a required-level modifier (id 0xe) of 60. B's
  weapon-swap press then reaches `inventory_equipItem`, whose wield check refuses the item
  and calls `hud_showPlayerNotice` (return address 0x1c2900) — on both machines, in tick
  724; the function sets the notice flag `g_playerNoticeOpen` 0x41b518 only where the slot
  is local, so the flag is 1 on B and 0 on A.
- A property of this fixture: while the unusable set is the active one,
  `Player_weaponSwapInput` tries the equip again in every tick the player is idle (41
  calls in 41 ticks), which raises the notice again and clears its "button was released"
  latch 0x86aa90, so the box cannot be confirmed. A second swap press (back to set 0) ends
  that. The box itself reads `g_pads` of the slot and the confirm mask 0x41bfbc (0x40),
  as `help_task` 0x1dd194–0x1dd1e0 says.
- *The confirm press* on machine B.

| | Without the section | With "closing a notice box does not run the pending script" on both |
|---|---|---|
| `script_runPostAction` | B: entered once, from `help_task` (return address 0x1dd1f8), outside the tick (`g_inSimTick` 0x402794 = 0); A: never | never on either |
| `vars_set` | B: once, from the script's `setv`, for that quest variable, value 1; A: never | never |
| first difference | **tick 805**: the pending name (A: still set, B: empty), the quest-variable table (checksum of its first 512 bytes: A 0x3348cf3c, B 0xf9fa7b84), the variable itself (A: not in the table, B: 1) | none in 398 ticks; B's box closes, the name stays pending on both |
| the game's own flags | none set in the 253 ticks that followed: quest variables are not in the sync record | — |

E9 is confirmed on the running game and so is its section. Not shown: the potion route
to a notice (`Player_usePotion`, call 0x1b9dd8 — it needs a potion kind of 2 or more,
which the two potion buttons do not pass), what machine A does when it later runs the
name it still holds (E10), and a level script whose post action changes the level.

### 16.3 U2, the mission menu and the jump-gate menu

Both menus are run tasks driven by one player's lockstep pad, and both return before their
pad test when that player is local and `pauseMenu_isOpen()` (0x231a4c–0x231a74,
0x27dee0–0x27df0c). Three things about the pause menu were seen first, because they decide
what can be reproduced:

- **The pause button is taken from the lockstep pad, inside the tick.** `pauseMenu_open`
  was entered with `g_inSimTick` = 1 in the tick whose pad row shows the start bit 0x800
  for that slot, on that slot's own machine only (the poll at 0x18e208 tests
  `net_isLocalSlot`). So the pause menu opens `lead` frames after the press, and whatever
  the player presses in those frames is already in the input stream when it opens. That
  is U2's window, and its order is *pause first, then confirm*.
- **Once it is open the early return also locks the local pad:** it calls
  `net_lockLocalInput(slot, 4)` in every tick of the condition (entered from 0x231a78 and
  0x27df0c), which by its symbol note clears the buttons of the next four samples
  (**Observed**; not tested separately here).
- **The mission menu guards itself twice against the pause button.** `missionMenu_open`
  calls `net_closeLocalMenus` (a pause menu open on the chooser's machine was closed in
  the tick the mission menu came up), and while the task `missionmenurun` exists the pause
  poll refuses to open the pause menu on the first active machine, which is the chooser's
  (0x18e138–0x18e154: with the mission menu up, the chooser's start press never reached
  `pauseMenu_open`). The jump-gate menu has neither guard. `pauseMenu_open` has one more
  caller with no such test, the controller-removed notice (0x1db678); the rig cannot pull
  a controller.

**Jump-gate menu: reproduced as U2 describes; the section removes it.** Script
`tools/rig/examples/pair-u2-gate.rig`, no bus delay. Of 18 levels tried, eight build a
`JumpGate` when entered by the pending-level write (`blood1`, `storm1`, `nit1`, `swamp1`,
`hub2`, `wat1`, `dis2`, `honor`); only in `hub2` is it within a short walk of the start
(about 430 units). Both players walk there. The gate refuses to work while the
destination list has one entry, and on this start it keeps one (`hub2` is added and at
once removed again as a hub that is not the current one, 0x27db60), so a second entry is
written on both machines in one tick. Machine A's player uses the gate (tick 1072: menu
on both machines, chooser slot 1), then presses pause and, one frame later, confirm.

| Tick | Machine A (the chooser's) | Machine B |
|---|---|---|
| 1152 | slot 1's pad shows pause; `pauseMenu_open` runs; `g_pauseMenuOpen` 1 | same pad; nothing (not its slot) |
| 1153 | slot 1's pad shows confirm; the menu returns early (`net_lockLocalInput` from 0x27df0c); state 2, travel 0 | menu state **3**, `g_jumpGateTravel` **1** |
| 1343–1344 | still in `hub2`, menu and pause menu up | pending level `hub`, then in `hub` |

First difference: **tick 1153**, the menu state and the travel counter; the level, seed and
positions from tick 1344. With "jump-gate menu ignores the chooser's pause menu" on both
machines both take the confirm in tick 1153 and both are in `hub` at tick 1344: no shared
column differs in 891 ticks.

**Mission menu: the test and its section exercised with the flag forced; no natural route
found.** Script `tools/rig/examples/pair-u2.rig`, bus delay 10. The menu is opened on both
machines in one tick by writing the name of the hub script's entry point for it into the
list of deferred script calls (`g_scriptDeferNames`, count at 0x86da78) — a way to call a
level-script entry inside a chosen tick that needs no walking. Chooser: slot 0, machine
B's. B presses confirm and three frames later `g_pauseMenuOpen` is set to 1 on machine B
alone, which stands in for a pause menu opened by something other than the button.

| | Without the section | With "mission menu ignores the chooser's pause menu" on both |
|---|---|---|
| tick 934, slot 0's pad shows confirm | A: menu state 5 (mission chosen); B: early return (`net_lockLocalInput` from 0x231a78), state 2 | both: state 5 |
| tick 969 | A: pending level `blood1`; B: none | both: `blood1` |
| first difference | **tick 934**, the menu state | none in 310 ticks |

So the code path of U2 and the patch behave as the ledger says in both menus. For the
mission menu the condition was forced: with the pause button alone it did not arise in
either order (confirm then pause: the pause menu did not open and both machines took the
confirm; pause then menu: the menu closed the pause menu). One thing seen and not looked
into: a confirm press made about 30 frames after the mission menu reached state 2 did not
appear in the lockstep pad of either machine, with the flag or without; one made 100
frames after it did.

**E10 on the way.** A post-action name written in `strife` and left pending was run by
`game_loadLevel` (return address 0x1e60c0) in the next level's script, in the first tick
of `hub` (701), on both machines alike; with the name of the hub's mission-menu entry it
opened the mission menu there.

### 16.4 K3, the stats page and the stored weapon damage: the record differs; no reader run

Script `tools/rig/examples/pair-k3.rig`, level `strife`, the `run4` states as they are, no
bus delay. Slot 0 (machine B's player, class 0) is made a dual wielder on both machines in
one tick: a second one-hand weapon in the second cell of bag 0, level 1 in the class's
dual-wield passive (entry 5 of the class's passive table, mask 0x40000) and the
second-weapon pointer +0x443c; the game's own swap code then equips it into equipment
slot 1 (`inventory_equipItem` from 0x1bba38, once). Machine B opens its inventory and
presses the page button four times, which is the stats page (`stats_screen` 0x1d1db8 is
entered from then on).

| | Without the section | With "stats page does not rewrite stored weapon damage" on both |
|---|---|---|
| `Player_recalcDamage` from the stats page, machine B, outside the tick | from 0x1d2c38 and from 0x1d2d30, 154 times each | from 0x1d2c38 only |
| slot 0's record +0xcc / +0xd0 / +0xd4 at the end of each tick | A: 37 / 20 / 25 (the main weapon); B: **34 / 15 / 20** (the off-hand one) | 37 / 20 / 25 on both |
| first difference | **tick 863**, the first tick after the page was drawn; on every tick to 1019, when B left the inventory (157 ticks); equal again from 1020 | none in 598 ticks |

Two things to add to the ledger's reading of K3:

- **The difference lasts as long as the page is open, not one tick.** While machine B's
  inventory was open, `Player_weaponSwapInput` — whose tail is the per-tick recompute —
  was not called for slot 0 on *either* machine (303 calls in 598 ticks, none in ticks
  725 to 1019 on both; slot 1: 598). The gate in `Player_run` skips it for a player whose menu is
  open, and does so alike everywhere (**Inferred**: the `net_getCamFlag` test at
  0x1a5bc4, the one test of that gate that travels with the input). So nothing repairs the
  record until the menu closes.
- **Nothing read the fields in these runs.** A reader has to be a projectile of that
  player still in flight while the page is open (the readers K3 and SB2 list; the player
  cannot act with the menu up), and the page only makes its second call with the melee
  set active. No such shot was set up, so no difference beyond the three record words was
  produced, and no out-of-sync flag.

A by-product, from a first version of the fixture whose new bag cell had the wrong index
byte: opening the inventory on the owner's machine rewrote byte +0x22 of that cell there
(0 to 1, the cell's position in the bag), and the bag checksum then differed between the
machines for the rest of the run. The item list renumbers the owner's bag cells on the
owner's machine only. Whether play can leave a cell with a stale index is **Unknown**.

### 16.5 The route grid when only one machine's copy asks for routes: it differs

**A correction first: the comparison of 14.4 (ledger V36) was not a comparison.** Its
dumps were written by script lines of the form `A: ontick N dump …` and `B: ontick N dump
…`. In the runner the machine prefix dropped the other machine's *commands*, but an
`ontick` line registers a tick action, and those stayed: both machines ran both lines, so
every `a-` and `b-` file was written by both and holds whichever wrote last
(**Observed** in `rig.cpp`, `ParseScriptLine`; **Ran**: before the fix a file named for
machine A held a write index that machine A's own tick log contradicts). "Byte for byte
the same at all 25 samples" compared a machine with itself, and the write index that
"went back" (65, then 64; 74, then 71) was the two machines' different indexes showing in
turn. The prefix is fixed in `rig.cpp` (the runner was rebuilt; a three-line script
confirms `A: ontick` now runs on A only, and the E9 pair gave tick 805 again). No other
script kept from the earlier phases has a prefixed `ontick` line. From here on the path-finding memory is
compared on every tick, as tick-log columns: the queue indexes 0x44f09c and 0x44f0a0, a
checksum of the queue array (`g_pathQueue`, 6,144 bytes) and a checksum of the route grid
itself (65 × 55 nodes of one word, 14,300 bytes at world +0x38).

**The one-sided pair.** Arena pair 406, every fix section and the item-record one, with
"Arena diagnostic: no prediction copy" on machine B only (`examples/prelude-route.rig`):
B makes no copy after the level is entered (`Player_clone`: 3 entries on B, 639 on A).

| | Machine A | Machine B |
|---|---|---|
| route requests inside a tick | 31, ticks 2372 … 9797 | the same 31 |
| route requests outside a tick (the copy's) | **49**, ticks 11718 … 15046, one every 64 ticks | 0 |
| `Creature_onPathResult`, all inside a tick | 80: the 31, and 49 for the copy | 31 |
| queue write and read index | 32 from tick 11718, 80 at the end | 31 throughout |
| route grid | from tick 11718: **418 nodes differ from machine B's, all in the search-mark bits (8–15)**; 433 marked nodes against 54 | one checksum from tick 11000 to the end of the level |

First difference: **tick 11718**, in all four path-finding columns, and on every tick from
there to the end of the level (3,369 ticks). So the search for a copy's request does run
inside the real tick of that machine alone, and it leaves its marks in the shared route
grid: the question 12.3 d and V29 left open is answered, and the answer is the opposite
of V36. No other shared column differed in 15,295 ticks — no monster asked for a route
after tick 9797 in this pair, so nothing read the marks.

**The ordinary pair, both copies on** (the same pair without the diagnostic): the two
copies ask at different ticks (B 49 from tick 7042, A 45 from tick 11078), and the route
grid differs between the machines on 5,651 ticks, in two stretches (7042–9993 and
11074–13772); the queue indexes differ from tick 7042 to the end of the level. In tick
9994 a real request was made and answered on both machines — on grids that differed
going in — and the grids were identical again after it, as were all later results; the
14 real requests after it started from equal grids. No other shared column differed in
15,330 ticks.

What this establishes and what it does not: the prediction copy's route searches put
per-machine state into memory that tick code reads (the marks; the queue indexes, which
decide the slot a request lands in). In the one case where a real search started from
differing grids, its clearing pass removed the difference. Whether a copy's marks can
survive a real search's clearing and change its result (`docs/spec/world-queries.md`
10.3 describes marks the clearing flood does not reach) is still **Unknown**; it now has
a concrete starting state to test from.

### 16.6 For the ledger, and what is not done

Proposed rows and corrections, for whoever edits `FINDINGS.md` (this document does not):

| Row | What to record |
|---|---|
| D26, V38 | Ran, both halves, with a shared difference: weapon set 0 / 1 in the death tick (tick 2400), and with a damage-over-time hit in that tick 2.0 hit points and one draw of the shared seed, the game's flag two ticks later. Each section removes its half; both together leave nothing (16.1). The natural damage in the window is a status effect on the later-running player; monsters run before the players |
| E9 | Ran: the box closed on one machine ran the pending script there, outside the tick; pending name and one quest variable differ from tick 805; silent. The section removes it (16.2) |
| E10 | Ran: a left-over name was run by `game_loadLevel` in the next level's script, on both machines alike (16.3) |
| U2 | Ran for the jump-gate menu as described (pause, then confirm inside the lead): menu state and travel counter differ at tick 1153, one machine changes level 190 ticks later; the section removes it. Mission menu: the test and its section work, shown with the pause flag forced; with the pause button it did not arise, because `missionMenu_open` closes local menus and the pause poll refuses while the menu's task exists (0x18e138–0x18e154). Add: the pause button is read from the lockstep pad inside the tick; `pauseMenu_open` has a second caller without those guards (controller removed, 0x1db678), not run |
| K3 | Ran: with the stats page open on the owner's machine the record's +0xcc / +0xd0 / +0xd4 differ between machines on every tick until the menu is closed (157 ticks here), not for one tick: the per-tick recompute is skipped on every machine for a player whose menu is open. The section removes it. No reader was run (16.4) |
| V36 | Withdraw: the dumps it rests on were written by both machines (16.5) |
| V29 | Answer: a copy's search does leave marks in the route grid of its machine (418 nodes in the one-sided pair; the ordinary pair's grids differ on 5,651 ticks). One real search from differing grids left them equal again. Effect on a search result: Unknown |
| new | `A:` / `B:` did not apply to `ontick` lines in the runner until this phase (fixed) |
| new | The item list rewrites the index byte +0x22 of the owner's bag cells on the owner's machine (seen with a poked cell whose index was wrong); reachability Unknown |

Not done in this phase:

- D26: a monster's hit in the window; the interact half of the gate; the other two routes
  to a non-zero lockout word.
- E9: the potion route to a notice; a post action that changes the level; what the other
  machine does when it later runs the name it kept.
- U2: a mission-menu case without the forced flag (it needs the controller-removed path);
  cancel instead of confirm; the jump-gate fixture gives the destination list its second
  entry by a write.
- K3: a projectile hit that reads the record while the page is open, and therefore any
  difference beyond the record itself.
- The route grid: a real search whose result is changed by a copy's marks.
- Nothing here is a console or PCSX2 result; two identical Play! instances show logic
  differences only.

## 17. Phase 12: a long soak with every section on

The developer LAN pair again; limits as in section 7: two copies of one Play! build — not a
PlayStation 2 and not PCSX2 — so only logic differences can show; characters built by
writes, seeded random input. **Ran** unless marked. The question was what still diverges
when every fix section is on and the pairs are long: ten to twenty minutes of play each
instead of one to four.

### 17.1 What was run

**Sections on both machines, thirteen:** the ten of `FIXES` in `tools/rig/fuzz.py` (K1, K2,
K3, the two lockout sections, the notice box, LAG-1, the spin, the touch, the script
return) plus "item records start from zero, not from stack leftovers", "option commit
leaves the button maps alone" and "route search always clears the previous search's
marks". `FIXES` itself was not edited. Not on: the two U2 menu sections, the save-point
section, "skeleton queries rebuild inside the tick" and the other "Net test" sections.

**Driver.** A local wrapper around `rig.py pair` in the manner of `fuzz.py`
(`local/rig-out/soak12.py`, not in the repository): one pair per job, the two tick logs
compared as a stream, a divergent pair run again to its first difference, per class one
run per remaining "Net test" section and one with "Arena diagnostic: no prediction copy",
and a memory diff at the first differing tick. A machine that has dropped the other ends
the pair. Besides the launcher's columns the tick log compared the cutscene flag, the
pending level, a checksum of the first 512 bytes of the quest variables, the pending
post-action name, each player's weapon set (+0x4a7c), the jump-gate travel counter and
menu state and the mission-menu state; and, counted on their own (17.4), each player's
stored attack rating and weapon damage (+0xcc, 12 bytes).

**Builds, six, 20 pairs each.** All level 25 with the statistics of 9.1.

| Build | States | Slot 0 / slot 1 | Skills at rank 10 (first two on the ability buttons) |
|---|---|---|---|
| c0+c6 | `run4` | class 0 / class 6 | `examples/pair-chars.rig` (9.1): 41, 76, 77, 78 / 89, 87, 88, 90, 94 |
| c0+c0 | `run5` | class 0 / class 0 | `examples/pair-chars-same.rig` (9.4): the spin on both |
| c1+c4 | new, lobby models 4 and 6 | class 1 / class 4 | five per player, taken in rotation from the class's skill-tree rows (section 11); a different five in each pair |
| c3+c5 | new, lobby models 2 and 10 | class 3 / class 5 | the same way |
| c2+c2 | `run6-8` | class 2 / class 2 | the same way |
| c6+c6 | `run6-11` | class 6 / class 6 (two pets) | the same way |

The two new start states were made as in 9.1 (both words of the model table written
before the confirm). In half the pairs mana was set to 500 on both machines every 300
ticks; in two thirds both players got 50,000 gold at tick 680; in half the pairs of the
four new builds every passive byte was 5 (as in section 11). Every pair enters its level
through a level load at tick 700, before any input: the load is where the game recomputes
maximum hit points and mana from the written statistics, on both machines in one tick
(seen: 900 written at tick 680, the class's own values from tick 701).

**Levels, lengths, input, bus.** 48 pairs start in the arena (`drunare`, walk into the
trigger, unskipped opening); 72 start in 23 other levels, two to four pairs each
(`strife`, `hub`, `hub2`, `drundar`, `blood1`, `bastion1`, `citadel`, `valor`, `storm1`,
`fire1`, `nit1`, `wat1`, `islc1`, `torment0`, `swamp1`, `fay1`, `honor`, `shame1`,
`inmine1`, `dis2`, `airarena`, `boar1`, `arachna1`). 40 pairs each of 30,000, 45,000 and
60,000 frames of random input. Three input mixes, 40 pairs each: everything (sticks,
attack, abilities, block, weapon swap, both potions, use, D-pad, inventory button, pause
button, stick buttons); the same without the right stick and the stick buttons; the same
without the pause button. Bus: none in 57 pairs; delay 4, jitter 3, loss 5% in 29; delay
10, jitter 6, loss 10% in 28; and six pairs with one outage of 60, 90 or 120 frames in
the middle (two of each), on delay 2 or on delay 4, jitter 3, loss 5%.

### 17.2 Totals

| | |
|---|---|
| Pairs run / planned | 120 / 120, 4.2 hours of wall time, seven pairs at a time |
| Frames of random input planned | 5,400,000 |
| Ticks compared | **5,109,338** |
| Pairs with a shared difference | 9: **7 in one class (17.3)**; 2 are the pause menu's kick |
| Pairs in which the game set its own out-of-sync flag | 1 (pair 033, 17.3) |
| Pairs with no usable log, a time-out or a stuck machine | 0 |

| Build | Pairs | Ticks | Divergent |
|---|---|---|---|
| c0+c6 | 20 | 867,369 | 0 |
| c0+c0 (spin) | 20 | 760,159 | 0 |
| c1+c4 | 20 | 941,940 | 3 |
| c3+c5 | 20 | 784,661 | 1 |
| c2+c2 | 20 | 804,293 | 0 |
| c6+c6 | 20 | 950,916 | 3 |

| Split | Pairs / ticks / divergent |
|---|---|
| start in the arena; elsewhere | 48 / 2,049,832 / 5; 72 / 3,059,506 / 2 |
| 30,000; 45,000; 60,000 frames | 40 / 1,147,663 / 0; 40 / 1,712,091 / 4; 40 / 2,249,584 / 3 |
| bus none; delay 4, jitter 3, loss 5%; delay 10, jitter 6, loss 10%; the six outage pairs | 57 / 2,358,999 / 2; 29 / 1,285,519 / 3; 28 / 1,199,266 / 1; 6 / 265,554 / 1 |
| input mix 1; 2; 3 | 40 / 1,676,074 / 3; 40 / 1,740,978 / 2; 40 / 1,692,286 / 2 |

What the pairs did (machine A's log, and entries counted by quiet break points on both
machines together):

| | |
|---|---|
| levels seen | 27: the 24 above and `valor2`, `fay3`, `inmine2`, reached by the players |
| level changes after the first entry | 810, every one in the same tick on both machines |
| ticks in `drunare`; `hub`; `hub2` | 1,443,933; 845,607; 585,224 |
| arena entries; arena left for `hub2` (fight won) | 126 (48 at the start of a pair, 78 later, without any write by the rig); 18 |
| ticks with the cutscene flag up | 161,640 |
| deaths (hit points to zero), slot 0; slot 1 | 223; 254 |
| `Player_castSkill`; `Player_usePotion` | 71,638; 401,330 |
| pause menu opened; `config_commitOptions` entered | 13,725 in the 80 pairs whose mix has the button; 2,312 in 77 pairs |
| inventory opened; inventory messages applied; equips | 23,531; 77,648; 3,988 |
| stats or skill page drawn (`stats_screen`) | 227,786 entries, in all 120 pairs |
| `shop_openOrStock` | 1,016, in 113 pairs |
| `game_loadLevel`; `save_game` | 2,435; 2,486 |
| mission menu task; jump-gate menu opened | 620 entries in 3 pairs; 6 in 1 pair |

No pair differed in the quest variables, the pending post action, the pending level, the
weapon set, the button maps, the bags, the statistics, the equipment, the ability records
or the mission-menu and jump-gate columns. All six outage pairs came through their outage
in step.

**What stopped a pair early.** Two kicks: machine B's random input chose the pause menu's
kick entry (pair 012 at tick 55113, pair 073 at tick 27789; B's pause menu open in the
ticks before, as in 8.2). One leave: machine A left through its pause menu (pair 093,
dropped by B at tick 32166, twelve ticks after A's pause menu closed; no difference
before it). One real desync (pair 033, below). Five more pairs compared fewer than 85% of
their frames as ticks with no drop and no difference: by their level columns the players
went back and forth between two neighbouring levels many times, and no ticks pass while
a level loads (**Inferred**; the longest gap between two ticks was 413 frames).

### 17.3 The class that is left: a heal passes the maximum, and one machine's stats page clamps it

All seven divergent pairs are one class: the first shared column to differ is a player's
hit points (record +0xac; 0x4d8b9c for slot 0, 0x4dd7cc for slot 1), nothing else in that
tick. The four that were run again repeated at the same tick.

| Pair | Build, start level | First tick | Column | Machine A / B at that tick | Maximum | Ticks differing | Then |
|---|---|---|---|---|---|---|---|
| 107 | c6+c6, arena | 4505 | slot 0 | 711.745 / **709.0** | 709.0 | 1,602 | equal again |
| 044 | c1+c4, arena | 9433 | slot 0 | 775.675 / **770.0** | 770.0 | 768 | equal again |
| 032 | c1+c4, arena | 13910 | slot 0 | **770.0** / 773.813 | 770.0 | 581 | equal again at tick 17070, when both had regenerated to the maximum |
| 035 | c6+c6, arena | 32437 | slot 0 | 713.713 / **709.0** | 709.0 | 765 | equal again |
| 038 | c1+c4, `strife` (then in `blood1`) | 33182 | slot 0 | 775.042 / **770.0** | 770.0 | 2 | equal again |
| 033 | c3+c5, arena | 38127 | slot 0 | 776.171 / **772.5** | 772.5 | 6,928, to the end | **seed, position and action state at tick 45050; the game's out-of-sync flag at 45052; the pair ends at 45054** |
| 101 | c6+c6, `arachna1` | 30869 | slot 1 | **709.0** / 713.247 | 709.0 | 4,679, to the end of the pair | still differing when the pair ended |

In every case one machine holds exactly the player's maximum and the other a value a few
points above it.

**What writes the two values** (`--predict-trace` on the hit-point and maximum words,
watched everywhere, pairs 032 and 033, both machines):

1. *In the tick, on both machines alike,* a healing effect takes the hit points over the
   maximum. Pair 032: `SpellHealing_run` 0x2e90b8 (writing block 0x2e92bc, from
   `Creature_updateSpells` ← `Player_updateCast` ← `Player_run`), five writes in ticks
   13905–13909, the last to 773.813 against a maximum of 770.0. Pair 033:
   `SpellMinorHealing_run` (writing block 0x2e0578), four writes in ticks 38118–38121, the
   last to 776.171 against 772.5. The code of the first (**Observed**, 0x2e9294–0x2e92c8):
   it tests "hit points + 1.0 ≤ maximum" before the step and then adds a per-tick amount
   (read from +0x1c of the object it holds in `$s1`) with no upper bound, so a step may
   end up to the amount less one above the maximum (the amounts here were about 7.0 and
   5.4). The second function's code was not read.
2. *Outside the players' run, on one machine only,* `player_recalcStats` 0x1b6458 (writing
   block 0x1b6a38) sets the hit points to the maximum: 773.813 → 770.0 on machine A in
   tick 13910 (pair 032), 776.171 → 772.5 on machine B in tick 38127 (pair 033). Its call
   chain both times is `stats_screen` ← `itemList_draw` ← `itemList_update` ←
   `inventory_runPanel` ← `inventory_runTask`: the stats or skill page of the machine
   whose inventory is open. The other machine has no such write. The recompute is for
   every player on that machine, so it need not be the healed player's own machine (pair
   032: slot 0 healed, machine A — slot 1's — clamped).

This is ledger row K4's path. K4 calls the recompute idempotent (**Inferred** there); it
is not while a player's hit points are above the maximum, and a healing skill puts them
there in ordinary play. The healing skills are ids 55 and 86 (`SpellHealing`) and 50
(`SpellMinorHealing`); 27 of the 120 pairs had one of them in a build, and the seven
divergent pairs are among those 27 (1,282,920 ticks). **The 93 pairs without a healing
skill: 3,826,418 ticks, no shared difference.** Potions, of which there were 401,330
presses, never produced the case.

**From silent to out of sync (pair 033).** Hit points are not in the game's hash, so the
difference is silent. It lasted 6,923 ticks, between 1.1 and 4.2 points. In tick 45050 a
hit left slot 0 with 2.394 hit points on machine A and none on machine B, where the
player died (action state 4 against 2); the shared seed differed in that tick, both
machines raised the out-of-sync flag at tick 45052, and machine B dropped its peer at
45054. That is a complete route from this class to the game's out-of-sync message, in the
arena, with every section on.

**The section trial.** On pair 107, run to 400 frames past its first difference once per
remaining "Net test" section (lag sections excepted) and once without the prediction copy:
only "skeleton queries rebuild inside the tick" left the pair without a difference, and
"no prediction copy" did not. That section moves the coincidence, it does not remove the
cause: with it on for whole pairs, pairs 107 (46,086 ticks) and 032 (60,769 ticks) show
nothing, and pair 044 shows the same thing at another tick — slot 0 at 775.818 on both
machines for the ticks up to 9959, and 734.457 against 728.638 in tick 9960, a hit taken
from the unclamped value on one machine and from 770.0 on the other. No section in the
patch file is aimed at this class.

### 17.4 The stored weapon damage still differs with the K3 section on

The three words K3 is about (record +0xcc, +0xd0, +0xd4; 0x4d8bbc for slot 0) differed
between the machines in **39 of the 120 pairs: 2,872 ticks in 81 stretches, the longest
695 ticks**, always equal again afterwards. Of the 2,872 ticks, 1,855 fell while the
player's own machine had its inventory or pause menu open, 225 while only the other
machine had one open, and 792 with neither — the tail after closing. No other shared
column followed from it in any pair, and no out-of-sync flag.

Traced on one pair (a 10,000-frame test pair of the c0+c6 build, both machines):

| Tick | What happened to slot 0 (machine B's player) |
|---|---|
| 3448 | machine B opens its inventory |
| 3522 | an equipment change is applied in the tick, on both machines alike (the equipment checksum changes on both); the stored values stay 559 / 58 / 62 on both, because the per-tick recompute at the end of `Player_weaponSwapInput` is not run for a player whose menu is open (16.4) |
| 3549–3561 | machine B is on the stats page: `Player_recalcDamage` 0x1b7158, called from `stats_screen`, writes 550 / 51 / 52 — on machine B only, 13 times |
| 3562 | machine B closes the menu |
| 3572 | `Player_recalcDamage` from `Player_weaponSwapInput` ← `Player_run` writes 550 / 51 / 52 on both machines |

So the section "stats page does not rewrite stored weapon damage" removes the stats
page's off-hand call (0x1d2d30) and leaves its first call (0x1d2c38, 16.4), and that call
still writes the record on the owner's machine alone. The two machines agree only as long
as nothing has changed the right value since the menu was opened; an equipment change made
in that same menu does. That is the one case traced; whether the other stretches are
equipment changes too, or a timed effect starting or ending while the menu is open, was
not looked at. The largest differences seen were an attack rating of 963 against 557
(pair 059) and a damage range of 156–180 against 68–74 (pair 116). The readers are the
ones K3 lists (a projectile or thrown-weapon skill of that player still in flight); none
was seen to turn this into another difference in these pairs.

### 17.5 Three things found on the way that were the rig's doing

They are recorded because each shows a real mechanism and a rule for later rig work.

- **Mana written above the maximum.** A first version refilled mana to 900 every 300
  ticks, above every class's maximum. In two of six test pairs the two machines then
  differed in mana: the machine with its inventory open clamped to the maximum (in the
  tick of a refill in one pair, 290 ticks after one in the other), the other kept 900
  until the next recompute inside a tick. This is the same K4 clamp as
  17.3, reached by a write instead of a heal. The soak refilled to 500, below every
  class's maximum (580.5 is the lowest).
- **A pending-level write with a menu open.** A first version sent pairs on to further
  levels by writing the pending level mid-run. One of six test pairs then lost a machine:
  machine B dropped A at tick 9573, six ticks after a level change that took machine A
  3,561 frames and machine B 1,171 (about 250 is usual). Traced with break points on the
  lump functions: machine A's inventory was open across an earlier level change made by
  the write; after it a resource lookup loaded a second copy of the inventory's interface
  lump at another address (`res_find` → `lump_load`) — the level's clearing had taken
  the panel's own copy out of the lump list (**Inferred**); from then on each open
  registered the panel's copy
  (`inventory_pollResources` → `lump_register`) while each close unloaded whichever copy
  `lump_load` found first, and one registration was left behind; at the next level
  change `lump_unloadUpToLevel` (from `game_clearLevel`) released it from memory that had
  been reused, `lump_releaseEntry` handed `libc_strrchr` pointers such as 0x08000000, and
  the machine spent 2,389 frames in that scan (PC histogram) — on a console more likely
  a crash than a wait (**Inferred**). Machine B came out of the level change 2,390 frames
  earlier, ran six ticks and dropped A; A dropped B eight ticks after it came back. It
  repeated exactly. This is taken to be the rig's doing: the script built-ins that change
  level — `script_newWorld` 0x143dd0, `script_simpleNewWorld`, `script_newWorldParameter`
  — and `game_openMissionMenu` are all among the callers of `net_closeLocalMenus`
  0x1eb000 (**Observed**; the order inside them was not read), and the write skips them.
  Whether any game path changes level without closing local menus was not looked for.
  It does show, live, what `docs/netcode.md` gives as inferred: a machine whose level
  load is more than about 900 frames slower than the other's is dropped. Rule: write the
  pending level only before input starts (tick 700 here).
- **Statistics written without a level load after them.** Maximum hit points and mana
  written at tick 680 stay as written until the next recompute; the level load at tick
  700 is what makes them the game's own on both machines in one tick. A pair that stayed
  in `strife` would not get that, so every pair here loads its level, `strife` included.

### 17.6 For the ledger, and what is not done

Proposed rows and changes, for whoever edits `FINDINGS.md` (this document does not):

| Row | What to record |
|---|---|
| new | Soak with thirteen sections on: 120 real-character pairs of 30,000–60,000 frames, six builds, 27 levels, 5,109,338 ticks; the only shared divergence left is the K4 clamp after a heal (7 of the 27 pairs with a healing skill; none in the 93 others, 3,826,418 ticks) |
| K4 | Not idempotent: `SpellHealing_run` and `SpellMinorHealing_run` leave hit points above the maximum (test before the step, no bound after it, 0x2e9294–0x2e92c8), and the stats page's `player_recalcStats` then sets them to the maximum on the machine whose inventory is open, for every player on that machine (writing block 0x1b6a38). Silent until it decides a death: pair 033 went from the clamp at tick 38127 to the game's out-of-sync flag at tick 45052. Ran, traced on two pairs |
| K3 | The section removes one of the stats page's two calls. The other (0x1d2c38) still writes the stored attack rating and damage on the owner's machine only, and differs from the other machine's after an equipment change made with the menu open: 39 of 120 pairs, 2,872 ticks. No reader seen |
| netcode, level change | The drop of a machine that loads about 900 frames slower than the other: seen (with a cause made by the rig) |

Not done:

- The code of `SpellMinorHealing_run`; other effects that add to hit points or mana
  without a bound (only the two that the soak ran into were traced); whether mana can pass
  its maximum the same way.
- Which page of the inventory makes the recompute (a machine with its inventory open did
  not always clamp at once), and K4's other callers.
- A reader for the differing stored damage.
- The U2 menu sections, the save-point section and "skeleton queries rebuild inside the
  tick" were not on. The mission menu ran in 3 pairs and the jump-gate menu opened in 1,
  without a difference.
- Levels were entered by the pending-level write; the door from `drundar` with its quest
  state was not used. Characters have written levels and skills, starting items and what
  they picked up or bought.
- Three or four machines; anything on a console or PCSX2. Two identical Play! instances
  show logic differences only.

## 18. Phase 13: the two menu sections on the rig

The developer LAN pair again; limits as in section 7: two copies of one Play! build — not a
PlayStation 2 and not PCSX2 — so only logic differences can show; characters built by
writes, seeded random input. **Ran** unless marked. Phase 12 left one cause of divergence
(17.3: a heal passes the maximum, and `player_recalcStats`, called from menu code on the
machine with a menu open, trims the hit points there only) and one difference that had done
no harm (17.4: the stored attack rating at record +0xcc). Two sections were added to the
patch file after it and had been run in the function-level interpreter only:

| Section | Words made no-ops |
|---|---|
| "menu screens do not recompute player statistics" | the three calls of `player_recalcStats` 0x1b6458 outside the simulation: 0x1d2e7c (`stats_screen`), 0x1d5950 (`skills_screen`), 0x1ce530 (`itemList_input`) |
| "stats page does not recompute the main weapon's damage either" | the stats page's remaining call of `Player_recalcDamage` 0x1b7158, at 0x1d2c38 |

The rig printed the old and the new word of each when it applied them: 0x0c06d916 → 0 three
times and 0x0c06dc56 → 0, as the patch file says.

### 18.1 What was run

A local wrapper (`local/rig-out/soak13.py`, not in the repository) takes the job list of the
Phase 12 wrapper as it is — pair number, seed, start states, character writes, script,
input mix, length and bus setting — and runs chosen pairs with that phase's thirteen
sections, or with those and the two new ones, on both machines. A pair repeats exactly
from the same states, script and bus seed (section 7), so a pair run again today with the
thirteen sections is the Phase 12 pair, and the same pair with fifteen differs from it by
the two sections alone.

The tick log got more shared columns than in Phase 12, compared at every tick like the
rest: for both players the maximum hit points and mana (record +0xb0, +0xc4), the potion
words (+0xb4 to +0xbf, +0xc8), +0xdc, the load and the load limit (+0x120, +0x124), and
the player object's armour (+0xe4) and the five words from object +0x5c that
`player_recalcArmor` rebuilds. The stored attack rating and damage (+0xcc, 12 bytes) are
counted on their own, as in 17.4. Every run also counted, per machine, the ticks in which a
player's hit points or mana were above the stored maximum.

| Part | Pairs | Sections | Ticks compared |
|---|---|---|---|
| 18.2 the seven pairs of 17.3 | 7 | fifteen | 346,998 |
| 18.2 the same seven, same day | 7 | thirteen | 346,361 |
| 18.3 six pairs of 17.4 | 6 | fifteen | 278,188 |
| 18.4 one scripted pair, four runs | 1 | fifteen and thirteen | 2,347 each |
| 18.5 the 27 pairs with a healing skill | 27 | fifteen | 1,212,349 |

Shorter control runs with thirteen sections are named where they are used (18.3, 18.5).
The first three parts ran eight pairs at a time in 47 minutes.

### 18.2 The seven pairs that diverged on hit points

Addresses: hit points are record +0xac, 0x4d8b9c for slot 0 and 0x4dd7cc for slot 1.

| Pair | Build, start level | Thirteen sections, today: first tick, column, machine A / B | Ticks differing, last | Then | Fifteen sections |
|---|---|---|---|---|---|
| 107 | c6+c6, arena | 4505, slot 0, 711.745 / 709.0 | 1,602, 6106 | equal again | no difference in 46,098 ticks |
| 044 | c1+c4, arena | 9433, slot 0, 775.675 / 770.0 | 768, 10544 | equal again | no difference in 59,283 ticks |
| 032 | c1+c4, arena | 13910, slot 0, 770.0 / 773.813 | 581, 17069 | equal again | no difference in 60,709 ticks |
| 035 | c6+c6, arena | 32437, slot 0, 713.713 / 709.0 | 765, 33201 | equal again | no difference in 59,869 ticks |
| 038 | c1+c4, `strife` (then `blood1`) | 33182, slot 0, 775.042 / 770.0 | 2, 33183 | equal again | no difference in 41,119 ticks |
| 033 | c3+c5, arena | 38127, slot 0, 776.171 / 772.5 | 6,928, 45054 | seed, position and action state at 45050; out-of-sync flag at 45052; machine B drops its peer at 45054 (44,395 ticks) | no difference in 45,032 ticks, to the planned end at tick 45691; no flag, no drop |
| 101 | c6+c6, `arachna1` | 30869, slot 1, 709.0 / 713.247 | 4,679, 35547 | still differing at the end | no difference in 34,888 ticks |

**Thirteen sections, today.** Every one of the seven repeated its Phase 12 row in every
number kept there: ticks compared, first differing tick, column, both values, the count of
differing ticks and the last of them, and for pair 033 the flag and the drop. Pairs 033,
038 and 101 had not been run a second time in Phase 12; they repeat too.

**Fifteen sections.** No shared column differs at any tick of any of the seven, the new
columns included, and the stored attack rating and damage agree at every tick as well
(pairs 101 and 107 differed there in 32 and 13 ticks with thirteen sections, today as in
Phase 12). Pair 033 plays to the end of its input.

The heals still pass the maximum; nothing outside the simulation trims them now. On both
machines alike the healed player's hit points were above the stored maximum in 1,681 ticks
of pair 107, 843 of 044, 1,020 of 032, 1,860 of 035 (and 184 for its other player), 587 of
038, 1,051 of 033 and 4,818 of 101 — there from the heal to the end of the pair — by at
most 6.04 points. With thirteen sections the machine that trimmed counted fewer (pair 101,
machine A: 139 ticks; the other machine 4,818).

Six of the seven took, with fifteen sections, the course their Phase 12 run took: the same
number of ticks, the same last tick, the same sequence of levels, deaths and entry counts
(17.2). In those the early trim on one machine had changed nothing else. Pair 033 is the
one whose course differs, from the death at tick 45050 on.

### 18.3 The stored attack rating: gone in the pairs tried

Six of the 39 pairs of 17.4, one or two of every build, chosen among those with the most
differing ticks and outside the 27 pairs of 18.5:

| Pair | Build, start level | Ticks compared | Ticks with +0xcc differing: Phase 12 (thirteen sections) | Fifteen sections |
|---|---|---|---|---|
| 015 | c3+c5, arena | 29,317 | 46 | 0 |
| 016 | c2+c2, arena | 45,500 | 75 | 0 |
| 020 | c1+c4, `fire1` | 57,683 | 104 | 0 |
| 042 | c0+c6, arena | 31,241 | 32 | 0 |
| 059 | c6+c6, `shame1` | 57,191 | 255 | 0 |
| 119 | c6+c6, `torment0` | 57,256 | 215 | 0 |

No shared column differs in any of them. The 27 pairs of 18.5 hold eight more of the 39
(101 and 107 of 18.2 among them): 1,078 differing ticks in Phase 12, none now. That is
fourteen of the 39 pairs run again, 1,805 ticks of difference with thirteen sections and
none with fifteen. The price is what 18.4 shows: the stored values wait for the menu to
close.

**A pair may take another course with the sections on, and that is not a statistic being
read.** Five of the six took their Phase 12 course (ticks, last tick, levels, deaths, entry
counts); pair 059 did not (57,191 ticks against 57,179), and neither did pair 116 in 18.5.
Pair 059 was run both ways again with the logs kept and the lockstep pad words of both
players (the first 32 bytes of each `g_pads` record) added. On both machines the two runs are equal in
every compared column, tick for tick and frame for frame, up to tick 12389 — the stored
damage apart, which is what the sections change (the thirteen-section run has it differing
between its machines from tick 5371 on, in 255 ticks). What parts first is the input of
machine A's player: its pad words differ between the runs at tick 10332 without consequence,
and at tick 12390 a press of the cross button is in the tick's input in the fifteen-section
run and one tick later, 12391, in the other; the shared seed differs from 12390 and the
player's position from 12391. Machine A's cosmetic seed had been one draw apart between the
runs for two ticks at 12275. So the patched machine took one of its own button presses into
the lockstep input a tick earlier — the input side, which both machines then share.
**Inferred:** drawing a menu page without the recompute calls is less work, which moves the
point inside a frame at which that machine samples its pad. Pair 116's course was not
traced.

### 18.4 Side effects: one pair with a menu open for a long stretch

**The question.** The simulation has its own calls of `player_recalcStats`, the same on
every machine: fourteen call sites in all (**Observed**, every `jal` to 0x1b6458), three of
them the patched ones, the rest in `Player_ctor` (0x1a2458), `player_initNewCharacter`
(0x1b23f8), `inventory_giveItem` (0x1c1a88, 0x1c1c60), `inventory_removeItem` (0x1c20e8),
`inventory_onStatPoint` (0x1c262c), `inventory_equipItem` (0x1c2ef0),
`inventory_unequipItem` (0x1c3314), `inventory_dropItem` (0x1c4910), `player_giveExp`
(0x1d3224) and one in a function at 0x1c2120 that nothing calls directly. None is in the
per-tick player code, and `inventory_onSkillPoint` 0x1c2648 has none. Did anything rely on
the calls made while drawing?

**The pair.** Build c6+c6 of the soak (states `run6-11`; slot 1 with skill 86 on its first
ability button), level 25, every passive byte 5, level load into `strife` at tick 700, no
bus delay. Machine A is slot 1's; everything below is about slot 1. Two writes besides the
soak's, both on both machines at tick 880: the experience of both players to 10,000 short
of the next level, and `g_debugCheats` 0x4f8ee0 to 1 — with it, `hud_run` gives every
player 20,000 experience through `player_giveExp` in the tick in which player 0's lockstep
pad has D-pad down pressed with R1 held (**Observed**, 0x1dbb64–0x1dbbe8; the same code
gives player 0 gold, which was not looked at), which machine B then does once. The pages of the inventory panel, by the page word at panel +0x50 and by
which function is entered: 0, 1, 2 the item lists of the three bags, 3 the stats page, 4
the quest list, 5 the skill tree; R1 and L1 change page, and the panel opens on the page it
was closed on.

Two scripts with every event in the same frame (generated and compared by
`local/rig-out/p13/side.py`, not in the repository). **S**: the menu is open on machine A from
tick 948 to 1709, again from 1778 to 2419 (the level-up page needs the inventory opened
anew) and from 2518 to 2869, 1,756 ticks. **C**: the same events with the menu open only
where an event needs it (948–1087 to unequip, 1118–1229 to equip, 1778–2249 for the
level-up page, 2518–2869), 1,076 ticks. Each was run with fifteen and with thirteen
sections; in all four runs a tick's number is its frame's number plus 417.

| Tick | Event | How |
|---|---|---|
| 905–923 | healed over the maximum: 712.513 of 709.0 | hit points written to 600, then the player's own healing skill (`Player_castSkill` once) |
| 948 | inventory opened (in S it stays open); page 1 from 1019 | |
| 1073 | unequip the armour piece of bag 1 | cross in the item list: inventory message 2, `inventory_unequipItem` |
| 1107 | hit points 716 | a write, both machines |
| 1213 | equip it again | message 1, `inventory_equipItem` |
| 1269 | S: the stats page | |
| 1297 | hit points 716, mana 815 (maximum 799.9) | writes |
| 1365 | a level gained | `player_giveExp` for both players, on both machines |
| 1427 | hit points 726 (maximum now 719.6) | a write |
| 1479, 1504 | S: the quest list, the skill tree | |
| 1547 | hit points 726 | a write |
| 1609, 1634 | S: the quest list, the stats page | |
| 1710 | S: closed | |
| 1778 | opened again: the level-up page; the level acknowledged at 1783 (message 9) | |
| 1853, 1919, 2009 | a point each into strength, intelligence, stamina | message 6, `inventory_onStatPoint` |
| 2179 | a skill point into the carrying passive (mask 0x40) | free cursor moved onto its node by the stick, cross: message 7, `inventory_onSkillPoint` |
| 2250 | C: closed | |
| 2274 | S: the stats page | |
| 2347 | hit points 730 (maximum 721.5) | a write |
| 2420 | S: closed | |
| 2518–2870 | opened once more; unequip at 2763, equip at 2823 | |

**Results.**

| Question | Answer |
|---|---|
| S with fifteen sections: do the two machines agree? | In every shared column at every one of 2,347 ticks — hit points, mana, both maxima, attack rating, damage, armour, load limit, statistics, points, equipment, bags — except the two bytes at record +0xed and +0xee (below) |
| S with thirteen sections | hit points differ in 846 ticks (1298–1364, 1428–1547, 1609–1852, 2348–2762), mana in 67 (1298–1364), the stored attack rating in 150 (2274–2423: 577 on machine A, 557 on B) |
| S against C, fifteen sections, machine A, tick by tick | maximum hit points and mana, damage, armour, load, load limit, hit points, mana, base and effective statistics, points and equipment are equal at every tick. One column differs: the stored attack rating in ticks 2254–2423, 557 in S and 577 in C |
| S with fifteen sections against machine B of S with thirteen | equal at every tick in hit points, mana, both maxima, attack rating, damage, armour and load limit: the patched pair holds on both machines what the machine *without* the menu held before |
| C with thirteen sections | hit points differ in 195 ticks (1832–1852 and 2589–2762): even a menu opened only to level up or to change armour trims on its own machine |

What recomputed, by caller (break point on `player_recalcStats`, return address and tick
logged, from tick 880):

| Caller | Thirteen sections | Fifteen sections |
|---|---|---|
| `inventory_unequipItem`, `inventory_equipItem` | ticks 1073, 2763 and 1213, 2823, both machines | the same |
| `player_giveExp` | tick 1365, twice (two players), both machines | the same |
| `inventory_onStatPoint` | ticks 1853, 1919, 2009, both machines | the same |
| `stats_screen` (0x1d2e7c) | machine A only, 702 calls in ticks 1269–2588: once per frame while page 3, page 4 or the level-up page is drawn | none |
| `skills_screen` (0x1d5950) | machine A only, once, tick 2174: at the press that spends the skill point, five ticks before the message is applied | none |
| `itemList_input` (0x1ce530) | none | none |
| `Player_recalcDamage` from the stats page (0x1d2c38) | machine A only, 449 calls | none |
| `Player_recalcDamage` from `Player_weaponSwapInput` | 2,486 calls on each machine | the same |

So each event that changes a derived statistic brings its own recompute in the tick, on
both machines: armour 89 → 82 → 89 at 1073 and 1213; maximum hit points and mana 709.0 and
799.9 → 719.6 and 805.4 at 1365; load limit 400 → 401 at 1853; maximum mana → 807.8 at
1919; maximum hit points → 721.5 at 2009. The skill point is the one event whose handler
does not call `player_recalcStats`, and it did not need to: the load limit went from 401 to
416 in tick 2179 on both machines, because `player_rebuildAbilities` 0x1d34ac, which the
handler calls, adds 15 to record +0x124 itself for this passive (**Observed**). Nothing
relied on the calls made while drawing.

Three things to know about the patched game, none of them a difference between machines:

- **Hit points and mana above the maximum stay there until the simulation recomputes.**
  Nothing in the tick trims them: 730 of 721.5 lasted 415 ticks, menu open and menu closed
  alike, until the unequip at 2763 trimmed it on both machines in one tick. This is what
  the machine without a menu already did (machine B in the thirteen-section runs). The
  trimming calls are the simulation's callers listed above: an item picked up, removed,
  dropped, equipped or unequipped, a stat point, a level (**Observed** call sites; equip,
  unequip, stat point and level were run here).
- **The stored attack rating waits for the menu to close.** It is level × 20 from the
  *acknowledged* level (+0x58), which the level-up page raises at 1783, and the per-tick
  recompute is not run for a player whose menu is open (16.4). With fifteen sections both
  machines hold 557 until the menu closes at 2420 and 577 from tick 2424; with thirteen,
  machine A's stats page wrote 577 at 2274. That is 17.4's difference, turned into the
  same delay everywhere.
- **Record +0xed and +0xee differ between the machines from tick 1778 to the end** (01 00
  on machine A, 00 01 on machine B), in all four runs: the level-up page's own bookkeeping
  bytes, written by menu code on the owner's machine. The launcher's "points" checksum
  covers them, so that column differs too. Not from the sections; menu code is their only
  reader named in `docs/ui.md`, and a reader in the simulation was not looked for.

**What the open menu shows** (machine A's screen text, fifteen against thirteen sections):
the stats page prints the record, so maximum hit points and mana, armour, the statistics
and the load limit are current — they are written in the tick. It now also shows hit
points or mana above the maximum as they are (716 of 708, 815 of 799, 726 of 719, 730 of
721) where the unpatched page showed them for one frame and then trimmed its own machine;
and it shows the old attack rating (557 where the unpatched page showed 577) until the
menu has been closed. Damage did not change in this pair.

Not exercised here: a weapon changed with the menu open (bag 0's page listed nothing for
this character, also with a second weapon written into the bag; the equipment change was
an armour piece, which moves armour only) — for that case 17.4's trace and 18.3's pairs are
the evidence, and by 17.4 the stats page then shows the old attack rating *and* damage until
the menu closes (**Inferred** for the screen; the record was seen). And the item list's call
at 0x1ce530: it sits on the shop's sell path, after the sell message is queued
(**Observed**, 0x1ce4d0–0x1ce534), and no shop was opened in this pair.

### 18.5 The confirmation soak: the 27 pairs with a healing skill

The 27 pairs of Phase 12 with skill 50, 55 or 86 in a build — eight c1+c4, eight c3+c5,
eleven c6+c6; thirteen starting in the arena and fourteen in ten other levels; 30,000 to
60,000 frames; no bus delay in ten, delay 4, jitter 3, loss 5% in eleven (one with its
120-frame outage), delay 10, jitter 6, loss 10% in six — each with its Phase 12 seed,
script and bus setting and fifteen sections on both machines, eight pairs at a time.

| | |
|---|---|
| Pairs run / planned | 27 / 27; no time-out, no stuck machine |
| Frames of random input planned | 1,260,000 |
| Ticks compared | **1,212,349** (the same pairs in Phase 12: 1,211,563) |
| Pairs differing in a column Phase 12 compared | **0** (Phase 12: 7, all in hit points) |
| Pairs with the game's out-of-sync flag; with a dropped peer | 0; 0 |
| Pairs with the stored attack rating or damage differing | 0 (Phase 12: 8 of these, 1,078 ticks) |
| Pairs differing in one of the new columns | 7, all in one column: the carried load, record +0x120 (below) |
| Hit points above the stored maximum, machine A's log | slot 0 in 10 pairs, 7,755 ticks, by at most 6.04; slot 1 in 6 pairs, 7,709 ticks, by at most 5.46. Mana: never |
| Same course as in Phase 12 | 25 of 27; not pair 033 (18.2) and not pair 116 (57,797 ticks against 57,648; 18.3) |
| Per build: pairs / ticks | c1+c4 8 / 407,945; c3+c5 8 / 279,288; c6+c6 11 / 525,116 |
| Entries, both machines together | `Player_castSkill` 16,944; `Player_usePotion` 83,470; inventory opened 5,511; `stats_screen` 58,320; inventory messages 18,018; equips 1,062; `shop_openOrStock` 223; pause menu 3,331; `game_loadLevel` 612; `save_game` 524 |
| Deaths, slot 0 / slot 1; level changes after the first entry; ticks with the cutscene flag | 45 / 104; 179; 42,904 |

The seven pairs of 18.2 are among the 27 and so ran twice with fifteen sections; the two
runs of each give the same row, field for field.

**The carried load: seven pairs, and not from the sections.** The one new column that
differs is the first of the two words logged at record +0x120 — the load, 0x4d8c10 for
slot 0 and 0x4dd840 for slot 1 — never the limit beside it:

| Pair | Build | First tick, slot, machine A / B | Ticks differing (slot 0; slot 1) | Longest stretch |
|---|---|---|---|---|
| 105 | c3+c5 | 2186, slot 0, 32.346 / 29.196 | 20; 0 | 19 |
| 063 | c3+c5 | 2256, slot 1, 30.146 / 34.846 | 14; 161 | 106 |
| 111 | c3+c5 | 2996, slot 1, 26.596 / 27.596 | 3,352; 1 | 3,352 |
| 069 | c3+c5 | 3435, slot 1, 34.596 / 34.846 | 0; 41 | 9 |
| 027 | c3+c5 | 5408, slot 1, 24.689 / 22.689 | 2,940; 4 | 2,940 |
| 021 | c3+c5 | 8936, slot 1, 12.150 / 12.282 | 0; 1 | 1 |
| 080 | c1+c4 | 22150, slot 1, 17.154 / 19.154 | 0; 21,405 | 21,405, to the end of the pair |

All seven were run again with thirteen sections, each to past its first differing tick (pair
080 to 65 ticks past it, pair 069 to tick 6946): each differs at the same tick with the same
two values, and pair 069 in the same 41 ticks. So this is older than the two sections and
was not seen before only because the column is new. In 27,935 of the 27,939 differing ticks
the machine that owns the player holds the lower value. A break point on `player_recalcLoad`
0x1bec10 in pair 069 (thirteen sections; return address and tick logged, 6,287 ticks): on
each machine every call but seven comes from `Player_run`, call at 0x1a9578; for slot 1 that
is 13,428 calls on machine A, whose player it is, and 1,509 on machine B; for slot 0, 782 on
machine B and 342 on machine A. The owner's extra calls are its prediction copy running
`Player_run` outside the tick: the write is the one `docs/issues/prediction-copy.md` lists
for +0x120 as harmless because the value is the same whoever computes it. The value is; the
tick is not — the other machine keeps the old sum until its own `Player_run` reaches that
call, up to 21,405 ticks here. No other column followed in any of the seven, and the loads
were far below the limits (325 to 400). What reads the load between the two recomputes was
not looked at.

Wall time 1.7 hours, where 50 minutes were expected: for the first hour two more pairs of
mine and another job's two runners ran beside the eight pairs, 22 runner processes on 18
cores, and the pairs fell to between a quarter and a half of their speed (the first eight,
60,000 frames each, took 2,400 to 4,500 seconds instead of about 1,300). Nothing timed out.
Rule for later rig work: count every runner on the machine, and stay at or below the number
of cores.

### 18.6 For the ledger, and what is not done

Proposed rows and changes, for whoever edits `FINDINGS.md` (this document does not):

| Row | What to record |
|---|---|
| V46, K4 | The section "menu screens do not recompute player statistics" **ran**: the seven pairs of V46 with it (and its companion) show no difference in any shared column, the maxima, load limit and armour included; the same seven without it, same day, repeat their Phase 12 rows exactly, pair 033 with its out-of-sync flag at tick 45052. Then the 27 pairs with a healing skill, 1,212,349 ticks: no difference in hit points or in any column the first soak compared, no flag. Play!, two identical instances: logic only |
| K3 | The companion section **ran**: the stored attack rating and damage agree at every tick in fourteen of the 39 pairs that had differed (1,805 ticks with thirteen sections, none with fifteen). With both sections the stored values of a player whose menu is open stay as they were until the menu closes, on every machine alike |
| K4 | Where the drawing-side calls were made: the stats page, the quest list and the level-up page once per frame (0x1d2e7c); the skill tree once per spending press (0x1d5950); the item list on the shop's sell path (0x1ce530). The simulation's own callers recompute in the tick of every event tried (equip, unequip, level, stat point); the skill point's load-limit change is made by `player_rebuildAbilities` 0x1d34ac. With the section, hit points above the maximum last until one of those calls, on every machine alike |
| new | Record +0xed and +0xee (level-up bookkeeping) differ between the machines after a level-up page was opened; no reader in the simulation known |
| prediction copy, +0x120 | The carried load is recomputed by `player_recalcLoad` from `Player_run` (0x1a9578), which the owner's prediction copy runs outside the tick: the two machines hold different loads for a while — 7 of 27 pairs, up to 21,405 ticks, with thirteen sections as with fifteen. No other difference followed; readers not examined |
| menu machine, input timing | With the menu sections on, a machine may take one of its own button presses into the lockstep input a tick earlier (pair 059, tick 12390), so a pair can take another course than without them. Both machines share that input; it is not a divergence |
| V46 | Its split by healing skill does not add up from the Phase 12 table: see below |

**A number in 17.3 that the Phase 12 table does not give.** By `pairs.tsv` of Phase 12 the
27 pairs with skill 50, 55 or 86 in a build compared 1,211,563 ticks and the other 93 pairs
3,897,775; 17.3, 17.6 and row V46 say 1,282,920 and 3,826,418. The total, 5,109,338, and
the pair counts agree. The statement that matters — no shared difference in the 93 —
stands either way.

Not done:

- A weapon changed with the menu open, in a scripted pair (above); a sale in a shop with
  the hit points over the maximum (the third patched call).
- The six stretches of 17.4 "with neither menu open" were not traced; they are gone with
  the others.
- Only the pairs named were run with fifteen sections: 33 of the 120. The 87 others were
  not, and no pair was longer than 60,000 frames.
- Why pair 116 took another course; what reads the carried load (+0x120) in the simulation,
  and whether a load near the limit can make the two machines decide a pick-up differently.
- `SpellMinorHealing_run`'s code, other effects that could pass a maximum, and whether
  hit points left above the maximum for long matter to anything (a heal that tests
  "hit points + 1.0 ≤ maximum" simply does not start).
- The U2 menu sections, the save-point section and "skeleton queries rebuild inside the
  tick" were not on, as in Phase 12.
- Three or four machines; anything on a console or PCSX2. Two identical Play! instances
  show logic differences only: these runs say the two sections remove the difference
  between machines here, not that the patched game behaves on a PlayStation 2.

## 19. Phase 14: through the lobby with the real client

Section 13 stopped at the lobby server's first screen. This phase goes on from there: the
server's terms screen accepted, two throw-away test accounts made on the local server, log
in, a character made through the game's own lobby screens on each machine, a game hosted
on one and joined from the other, the launch, a level in lockstep, and the arena level
with the per-tick comparison running. The user allowed the first two steps explicitly;
both stay on the test machine (the server is the user's own process on the same host, and
the rig's network relays to that host only). **Ran** unless marked; limits as in section
13: Play!, not a PlayStation 2 and not PCSX2; two copies of one emulator build; host
sockets, so real time matters and no run repeats exactly.

**In short:** the whole online path works with the replacement server — account, log in,
character create / list / load / save, host, list, join, the peer-to-peer handshake over
real sockets, start, launch — and the game the lobby launches stays in step through a
level and an arena fight here (19.10). No reply of the server was refused or misread by
the game on that path; what was found is in 19.12.

### 19.1 How it is run

- One runner per machine, each a **live session**: `rig.py session --name N start
  --interactive-live --screen-text --eth-net server=<host address>,guest=<10.0.2.x>
  --eth-pcap <file> --script tools/rig/examples/online-lobby.rig`. With the new
  `--interactive-live` the machine keeps running while the session waits for commands. A
  plain session stands still between commands, which is fatal here: the server drops a
  connection it has not heard from for its `client_timeout` (120 s).
- The runner for this phase was built into `local/rig-build-online` so that the runner
  other work was using stayed as it was.
- The test accounts' names and passwords are random and exist only in a local file
  outside the repository, `local/rig-out/online-accounts.txt` (lines `a.user=…`,
  `a.password=…`, `a.email=…`, `a.birth=…`, `a.handle=…`, and the same for `b`). Scripts
  take them from there (`tools/rig/osk.py … --file F --key a.user`); nothing in the
  repository holds them, and the tools print a password's length only.
- `tools/rig/osk.py` types on the game's two on-screen keyboards and checks each key
  (19.3). `tools/rig/lobbycap.py <capture>` turns a `--eth-pcap` file into one line per
  lobby message: direction, number, tracking number, version or result, and the body field
  by field, with the encrypted strings decrypted by the connection's key — the tables
  below come from it.

### 19.2 What had to change in the runner

| Change (`rig.cpp`) | Why |
|---|---|
| `--interactive-live`: commands are taken from standard input without waiting, at each vertical blank | see 19.1 |
| `SIGPIPE` ignored; a relayed TCP connection whose host side has gone answers the machine's next segment with a reset | the server closed a connection, the game then sent on it, and the runner died silently on the signal. Now the game sees what it would see on a real network |
| the closing segment of a relayed TCP connection is not repeated once acknowledged | it was sent again every two seconds for ever |
| `--eth-net … ,udp=<port>+<port>`: UDP to the server's address goes to the server only on these ports (default 10101, the discovery port); to any other port it goes to `127.0.0.1`, and a datagram arriving from `127.0.0.1` is shown to the machine as coming from the server's address | the path between two runners, 19.8 |
| a line in the log when the machine stood still for more than 20 s of real time | 19.9: nothing else shows that the host slept |

### 19.3 The screens, and typing

Seen by pressing: in the hint lines of the lobby screens the four glyphs the transcript
prints as `~`, `{`, `|`, `}` are cross, circle, triangle, square; `\u0083`/`\u0085` are
L1/R1 and `\u0084`/`\u0086` L2/R2. Circle on the login screen leaves the lobby (the
connection is closed properly and the game returns to the front end; "Internet Game" can
be entered again in the same run, and the terms screen is then not shown a second time —
no second 0x42 is sent).

The lobby keyboard is a grid of 14 columns: digits, three letter rows, a row of accented
letters; R2 held shows the shifted set; cross types, square deletes, triangle is a space,
L2 accepts the field and moves the focus to the next one, circle closes the keyboard. Its
cursor is the word at +0x5e0 of the keyboard window (static pointer 0x5061f4, class
vtable 0x51ce28): row × 14 + column. The cursor stays where it was when the keyboard is
opened again. The character-name screen has its own keyboard: 10 columns, cursor in the
word at 0x8e2ba0 (row × 10 + column; −2 and −1 are its SPACE and DONE keys).

**The game misses short button presses on these screens.** A press held for four frames
was lost now and then on the login and account screens (two of nine keys in the first
name typed that way; none in 60 presses of one key in a row), and nearly always on the
joiner's character screens, where a hold of ten frames was needed. The game draws about
one frame for every two fields on these screens (its draw counter rose by 56 in 120
fields); what makes a particular frame long enough to swallow a press was not
established — Inferred: a network call on the main thread. `osk.py` therefore holds a key
for eight frames, reads the field back from the drawn text after every key and presses
again when the field did not grow; with that, every field of every form matched what was
typed. Menu presses were made the same way: hold eight to ten frames, look for the next
screen, press again if it has not come.

### 19.4 Terms, account, log in

| Step | What the game sent | Reply | Screen |
|---|---|---|---|
| terms | (0x42 with `en`, `us`, as in 13.4) | the server's text | cross accepts; no message is sent for it |
| account form | — | — | six fields: login, password, password again, e-mail, date of birth, chat handle |
| submit | 0x06, 230 bytes: five encrypted strings (name, password, e-mail, date, handle) | result 0, encrypted session id (16 characters) | success notice, then the game list and chat |
| straight after | 0x0E, 0x61 | six room names with their filler; three empty lists | |
| | 0x5B (`u32` 0) | count 0 | |
| | 0x0C with the first room's name | name, empty text, one member (own handle), no moderators | "joined" line in the chat pane |
| | 0x55 (27 bytes after the session id), 0x0E again | eight empty arrays; rooms | "no games" line |
| about every 710 frames while the list is shown | 0x55 | | list refresh |
| idle | empty frame (`00 00 00 04`) about every 760 frames | none | |
| log in (second run, machine A) | 0x16: name, password | result 0, session id, the account's chat handle | as after 0x06 |

Both accounts were made with 0x06 (one per machine) and machine A later logged in with
0x16; both paths end in the same lobby screen. **No disagreement between the game and the
server in this part**: every reply was accepted (the game's console prints the result of
each), and each body has the layout `docs/lobby-protocol.md` gives, with these additions:

- An encrypted string whose text is a multiple of 16 bytes carries **one more block**:
  the 16-character session id (32 bytes) travels as 48 bytes of ciphertext, so a request
  with nothing but a session id is 70 bytes on the wire. `docs/netlib.md` has this rule
  ("rounded down to 16, plus 16"); `docs/lobby-protocol.md` section 3 says "padded to a
  multiple of 16", which is what the test client sends and the server also accepts.
- The discovery datagram is therefore **52 bytes** from the real game (the `u32` 0x20 and
  48 bytes), not 36 (19.6). The server takes anything of 36 bytes or more.
- 0x0E and 0x61 go out one frame apart and are answered in order; 0x5B, 0x0C, 0x55 and
  0x0E likewise. The game has several requests pending at once.

### 19.5 A character made in the lobby

"Host game" (triangle on the game list, then cross) with no character on the server opens
the character screens at once (lobby state 0xb): class and sex (seven classes, each male
then female; triangle there would import one from the memory card instead), appearance,
20 ability points, name. On DONE the game says it is saving to the server, and sends:

| | Sent | Reply |
|---|---|---|
| 0x15 (on "host game") | the public room's name | result 0 |
| 0x58, tracking number *n*, 1026 bytes | `u32` 0, `u32` 0, keys `name`, `raceandclass`, `level`, `ability`, their four values, a first piece of 800 bytes, `u32` 0 | none yet |
| 0x5D, tracking number *n* again, 387 bytes | a piece of 309 bytes, last-piece flag 1 | **one** reply, numbered 0x58, tracking number *n*, result 0, `u32` character id |

The game took the reply (its console shows type 88, result 0) and went on to the
create-game form: the single reply after the last piece, with the id, is what the game
wants, as `server/upstream/FIXES.md` section 5 worked out from the parser. A new level-1
character packs to 1,109 bytes. The values sent for a male Barbarian warrior with the 20
points put into strength and stamina were `0 0`, `1` and six numbers of which the last
two are 0.

### 19.6 Hosting

The create-game form has a name, public or private, difficulty (one choice for a level-1
character), game type (missions, and two arena modes) and mission. R1/L1 move between
its rows and the two chat panes; left and right change a row. Submit:

| Sent | Reply or effect |
|---|---|
| 0x54: `u16` 1, `u32` 0, 50, 10, game info `01,00,00,00,01\|<name>`, an empty attribute list, an empty blob, own address `10.0.2.15` (the machine's address behind the rig), own UDP port **4001**, an empty string, `u32` 0 | result 0, the discovery address and port |
| 0x09 with the game's name | result 0 and the four room fields; **the game then sends 0x19** with the room name and its fixed line, answered with result 0 |
| 0x15 and 0x0C for the public room | result 0 each |
| UDP, from port 4001 to the discovery port: `u32` 0x20 and 48 bytes | notification 0x3E with the address and port the server saw (this host, the rig's host socket for port 4001) |

The game room then lists the host's character with class and level, and offers "start".
So the UDP port is 4001 here, inside the 4000–4004 that `docs/lobby-protocol.md` 9.1
inferred, and 0x19 does follow a well-formed 0x09 reply (section 7 of
`server/upstream/FIXES.md`).

### 19.7 Joining: the first attempt

The other machine's list showed the game after its next 0x55 (one game: info string, an
empty second string, id, one empty blob, the host's address `10.0.2.15` and port 4001,
and the address and port the server saw). Cross on it:

| Machine | Sent or received |
|---|---|
| joiner | 0x66: game id, own address `10.0.2.16`, own UDP port 4001 → result 0, discovery address and port |
| joiner | UDP: the 52-byte discovery datagram, once; then a one-byte datagram (01) to the host's observed address every 200 frames or so |
| joiner | ← 0x40: its own observed address and port |
| host | ← 0x65: the joiner's two address pairs |
| host | UDP: a 14-byte UdpLibrary connect request to the joiner's observed pair **and** another to its own-network pair (`10.0.2.16:4001`), each repeated about every 125 frames; one-byte datagrams to the observed pair |

Nothing arrived on either side and after eight of its one-byte datagrams the joiner said
it could not connect to the host. Everything the lobby server has to do had been done
correctly; the datagrams were lost on the host: **the test machine's firewall drops UDP
between two local programs when it is addressed to the machine's outside address** (two
plain sockets show the same; through 127.0.0.1 they talk). The server's own UDP port is
not affected. See 19.8.

### 19.8 The path between two runners, and the join

The lobby server sees both runners at the host's address with different ports — the rig
is, in effect, one router with both consoles behind it, and the server tells each to find
the other at that one address. A real router has to send such traffic back in ("hairpin");
here the rig does: a datagram for the server's address on a port that is not the server's
goes to 127.0.0.1 on that port, where the other runner's host socket for its machine's
game port is listening, and that runner presents it to its machine as coming from the
shared address (`rig.cpp`, `EtherUdpOut`, `EtherPoll`). The machines' own addresses
(10.0.2.15, 10.0.2.16) are not bridged: the host's second connection attempt, to the
joiner's own-network pair, goes nowhere, as between two houses.

With that the join goes through. What crosses between the two game sockets (each
machine's UDP port is one of 4000–4004, chosen anew in each run; counts from one whole
run; the reading of the bytes beyond size and first two is Inferred from
`docs/netlib.md`):

| Stage | Datagrams (first two bytes, size) | Who |
|---|---|---|
| seek | `01`, 1 byte | joiner → host, until the host's request arrives (2) |
| connect | `00 01`, 14 bytes: protocol version 2, a connection code, maximum size 512 | host → joiner's observed pair (and, unanswered, to its own-network pair) |
| | `00 02`, 21 bytes: the code back, a second code, the options | joiner → host |
| welcome | `00 09`, 234 bytes, reliable, sequence 0: two messages in one datagram — the welcome (0x1d: the joiner's ident 1, the game record, the peer list) and the peer list (0x19) | host → joiner |
| | `00 15`, 4 bytes: acknowledgement | joiner → host |
| in the room | `00 06`, 2 bytes, each way about every 380 frames | keep-alive |
| character chosen | `00 09`, 79 bytes: the joiner's record (0x1b); the host answers with the new peer list (`00 09`, 40 bytes) | |
| start | `00 09`, 8 bytes: message 0x1a; then `00 05`, 8 bytes, each way | host; both close the connection |
| launch | 11 datagrams one way and 13 the other, 512 bytes each but for one of about 1,200, within 210 frames | the netcode's own handshake, on the same sockets |
| play | about 0.42 datagrams per frame each way, first bytes `3f bd`, 40 bytes mostly (28–56) | lockstep input |

On receiving the welcome the joiner sends 0x5F (its session id and the host's), gets result
0, enters the game's chat room with 0x0C (the reply now carries the line the host set
with 0x19, and both members) and leaves the public one; the server also sends 0x3D to the
room when somebody enters. Only then does the joiner get its character screens (lobby
state 0xa). After that both machines list both characters in the game room.

A character already on the server is not offered first: "host" or "join" always opens the
new-character screens, and the stored ones are behind triangle there ("import"), in one
list with the memory card's, marked as network characters. Choosing one sends 0x5C with
its id; the reply here was one frame, 1,024 bytes, last-piece flag 1 (the server keeps
only as much of an upload as expands to a full record, so 1,109 uploaded bytes came back
as less than 1,024, padded). The game showed the character's sheet from it.

### 19.9 The host went to sleep: what the game does when the server drops it

Not planned. The test machine was put to sleep several times during this phase (its power
log shows it), each time for longer than the server's 120 s. On waking, the server dropped
every client in the same instant (**server**, `LobbyServer::Run`: `CheckSocketProblem` runs
before the sockets are read, and its clock, `std::chrono::steady_clock`, had moved on
through the sleep — so clients whose data was waiting in the socket were timed out
unread. A server on a machine that sleeps is not the usual case, but the order is worth
knowing). What the game then did, on both machines:

- its transport noticed the closed connection on its next send, and **connected again by
  itself**: gateway (0x43), lobby (0x27) — and then went on with its periodic 0x55 under
  the old session id, without logging in;
- the server answered that 0x55 from a connection that is not logged in with result 0 and
  an empty list, **and** sent notification 0x41 and closed; the game connected again; and
  so on, about every 650 frames, for as long as it was left alone (seven rounds seen);
- on the screen a notice that the connection was lost sat over the game list all that
  time; accepting it takes the game back to the network menu, from where the lobby is
  entered and logged into again normally.

A machine that was in the middle of the account form when this happened was not
disturbed: its transport reconnected, and its 0x06 went out on the new connection.

### 19.10 Launch, a level, the arena

"Start" on the host:

| Machine | Sent | Reply |
|---|---|---|
| host | 0x23: session id, `u8` 0, `u16` 0, three empty lists (15 zero bytes) | result 0 and a `u32` 0 — taken by the game |
| both | 0x15 for the public room | result 0 |
| both | the peer start message and the launch datagrams of 19.8 | |

About 600 frames later both machines are in the level `hub` with two players,
`g_lobbyLaunch` 1, both records of kind 2 (+0x4c1c), the host's character in slot 0 and
the joiner's in slot 1, and `g_netFrame` counting: **a lockstep game launched through the
lobby, with characters kept by the lobby server, between two machines that found each
other through it.** The lobby connection stays open during play (lobby state 0xc) and
carries the saves of 19.11.

The measured runs (`local/rig-out/p14`; the driver scripts there are local because they
find their way by the text on the screen; the whole path from power-on takes under three
minutes of real time). Run 4: both machines get the thirteen fix sections of
section 17 in the front end, before "Internet Game"; the tick log has the launcher's
columns plus the lobby flag, the two kinds, names and levels, the pending level, the
cutscene flag and the checksum tables of 19.11.

| Stage | Ticks | Seen on both machines |
|---|---|---|
| `hub`, seeded random input (move, fight, potion) for 1,800 frames | 400–2,080 | same seed and positions throughout |
| pending level written as `drunare` in tick 2,688 on both | | both in the arena level about 180 ticks later, same positions |
| the host's player walks west | | cutscene flag up at tick 3,032 — 2 modulo 15, as section 7.5 found — and down about 1,270 ticks later |
| the fight: seeded random input (move, fight, potion, use) for 4,500 frames | 4,320–7,950 | the host's level-1 warrior killed; no out-of-sync flag, no checksum failure |

`compare.py ticks`: **7,948 ticks compared, no shared column differs on any tick.** Run
3, the same path before it, stayed in `hub` (16,000 ticks, 3,000 frames of random input
with "use", the rest standing): no shared column differs either. That run is also where a
mistake of method showed: random "use" had started a conversation with the hub's trader,
the level was then changed under it by the pending-level write, and both players stood
frozen in the arena level with no HUD for the rest of the run. Before forcing a level,
see that nobody is in a conversation.

**With levels and skills.** The same path, with the build of `examples/pair-chars.rig`
(section 9.1: level 25, 900 hit points, four or five skills at rank 10) written into both
records in one lockstep tick in `hub` on both machines, random input that also casts, and
a fight of 6,000 frames. The game saves these characters to the server like any others,
so from the second run on they arrive at level 25 from the server and the write only
repeats what is there.

| Run | Slot 0 / slot 1 | Fix sections | Ticks compared | Result |
|---|---|---|---|---|
| 5 | warrior (class 0) / a new shaman (class 6), the pair of 9.1 | thirteen | 9,923 | no shared column differs |
| 6 | warrior / berserker carrying the same written build | **none** | 11,138 | **bag 0 of slot 0 differs from tick 7,783 to the end**: an item arrives in the bag in that tick on both machines and its bytes are not the same. No out-of-sync flag, no checksum failure |
| 7 | as 6 | thirteen | 9,919 | no shared column differs |

Run 6 is the item-record class of section 10 (ledger V22), now in a lobby-launched game;
runs 6 and 7 are not a replay of one another (real time decides the input delay), so
"removed by the sections" rests on section 12, not on this pair. One run each.

What this does and does not show: two identical emulator instances; three fights with
the sections on, one without. It shows that the lobby launch path, the transferred lobby
characters and the checksum exchange do not by themselves put the arena out of step, and
that what the developer-start pairs found carries over unchanged.

### 19.11 The checksum exchange, and who saves whom

With both kinds 2 and the lobby flag set the exchange of ledger rows B1–B2 runs, and it
does what `docs/issues/sync-breakers.md` section 1 read:

- every 240 ticks, on ticks that are 60 modulo 240, the host (the first active machine)
  calls `hudmsg_sendChecksumStart` (0x1de430); only the host does;
- seven or eight ticks later — the input delay — **both machines call `net_sendChecksums`
  (0x1de46c) in the same tick**, and each receives the two pairs in the same two ticks
  (three or four and about eight ticks after that): `netmsg_0a_checksum_handler`
  (0x1d90a4) runs twice per round on each;
- the two tables (`g_expectedChecksums`, `g_receivedChecksums`) were equal on both
  machines in every round of every run: 33 rounds in the first arena run, 66 in the hub
  run, about 40 in each of runs 5 to 7. The values changed only when a character changed
  (twice in the hub run), on both machines in the same tick. `g_checksumFailed` stayed 0;
- **it does not see everything.** In run 6 one bag differed between the machines for
  3,355 ticks, fourteen rounds, and every round passed: the item bytes that differed are
  not among what `player_checksum` mixes.

**A difference made on purpose** (the gold of slot 0 raised by one on the joiner's machine
only, in tick 14,590 of a quiet game):

| Tick | Joiner's machine (holds the wrong value) | Host's machine (owns slot 0) |
|---|---|---|
| 14,704 | its own value for slot 0 differs from before | — |
| 14,712 | the comparison fails: `g_checksumFailed` 1, `net_disconnectPlayer(0, 1)` from the handler (return address 0x1d91dc); slot 0 marked dropped | comparison passes; nothing |
| 14,718 | plays on alone | stops: no more input from the other. About 930 frames later it marks the other dropped and goes on alone |
| +239 ticks, each from its own drop | **back in the lobby's game list**: front end, lobby state 5, still logged in | the same |

So a covered value that differs on one machine ends the session for both players within
some twenty seconds, without either seeing the out-of-sync notice: the machine with the
difference throws the other out, the other waits out the silence, and each then returns
to the lobby. Why a machine left alone returns to the lobby after 239 ticks was not
traced (Inferred: the exit countdown of game message 8). This is B2 and B13 run for the
first time; with a real difference (a desync in a covered field) the same would follow at
the next round.

**Saves.** About every 2,100–2,400 frames in play a machine sends 0x5E — session id, the
session id of the player being saved, that character's id, the four keys and values, a
first piece of 800 bytes — and a last 0x5D piece under the same tracking number; the
server answers once, result 0, numbered 0x5E. In one run each machine saved only the
*other* player's character; in another each saved both in turn. (Which machine saves
which slot is drawn from the shared seed, `game_sendCharacterToLobby` 0x1eb5c8.) The
character loaded at the next log in carried what the earlier game had given it. This is
the server's "anyone can overwrite another's character" from `FIXES.md` seen from the
game's side: it is how the game saves.

### 19.12 Where the game and the server disagree

In the path that was run — terms, account, log in, character create / list / load / save,
create public game, room and its text, game list, join, discovery, the two address
notifications, join report, start — **every reply was accepted by the game and nothing
the server sent was misread.** What was found is at the edges:

| # | What | On the wire | Where |
|---|---|---|---|
| S1 | A request under a session id from a connection that never logged in is answered as if it were valid (0x55: result 0, empty list) and the connection is then closed with 0x41. The game, which reconnects on its own after a drop and does not log in again, loops (19.9) | reply `55 00`, tracking number, result 0, eight zero counts; then `41 00 00 00 00 00 00 00 00 00` | Observed in the source: `RequestMatchGame_RTA::ProcessRequest` (`Source/Network/Event/RequestMatchGame_RTA.cpp`, the `!user->m_isLoggedIn` branch) calls `UserManager::Disconnect`, which sends 0x41 and marks the socket to be closed, and then returns an ordinary result with an empty list. The game's handler for 0x41 did not take it back to the login screen here (the notice already on the screen was the one for the lost connection). A failure result in the reply, or simply closing without a reply, would at least not look like success; which result the game treats as "log in again" was not looked for |
| S2 | 0x41 carries a `u32`; the game reads a `u16` (`docs/lobby-protocol.md`) | `41 00`, `u32` 0, `u32` 0 | `NotifyForcedLogout::Serialize`. No effect was seen |
| S3 | After a sleep of the server's host every client is timed out unread (19.9) | — | `LobbyServer::Run` calls `CheckSocketProblem` before `ReadSocket` |
| S4 | The first column of the game list shows the game id plus one (18 to 21 for ids 17 to 20). What that column is meant to hold was not found; the game takes the id from array 3 and sends the same number back in 0x66, so the id itself is used correctly | 0x55 reply, array 3 | **Unknown** whether this is a server matter at all: needs the list's drawing code |
| S5 | Array 2 of the list (the short text per game) is empty; the game keeps 14 characters of it per game | 0x55 reply, array 2 | as `FIXES.md` "not fixed" says; nothing visibly missing on the list screen |

Not exercised: private games (0x56, 0x57), a second public game in the list, friends,
ignore, messages, room chat typed by a player, cancelling (0x05, 0x60), deleting a
character, a third and fourth machine, and everything after a player leaves a running
game.

### 19.13 Corrections to earlier documents

- `docs/lobby-protocol.md` 3 and 6: the padding of encrypted strings and the size of the
  discovery datagram, as in 19.4.
- `docs/lobby-protocol.md` 9.1: the UDP port is in 4000–4004 (4001 and 4004 seen), and
  both of the host's connection attempts (observed pair and own-network pair) are made.
- `docs/lobby-protocol.md` 8.3: the stored characters are reached through "import" on the
  new-character screen; 0x5B is sent after log in and again when that list is opened.
- `docs/lobby-protocol.md` "nothing here was confirmed with a real console or an
  emulator", and the same in `server/upstream/FIXES.md`: this section is the first
  exchange of the protocol with the real client (in Play!). The fixes of `FIXES.md`
  sections 3, 5, 6 and 7 (chat handle at log in, one reply per character upload with the
  id, the `u32` after 0x23, the room reply and 0x19) are each seen working with it.
- `docs/netlib.md`, lobby state table: state 0xa is the joiner's character menu after the
  host's welcome, 0xb the host's before the game exists; 5 is the game list, 6 the game
  room.

### 19.14 For the ledger

Proposed, for whoever edits `FINDINGS.md` (this document does not):

| Row | What to record |
|---|---|
| new (V) | The real online path ran end to end on two Play! instances against the replacement lobby server: account, log in, lobby characters, host, join, peer handshake over real sockets, launch; the launched game (lobby flag set, both characters kind 2) stayed in step through `hub` and the arena, three fights with the thirteen sections on. Ran |
| new (V) | Without the sections one lobby-launched fight left a bag different between the machines from the tick an item arrived, silently — the item-record class (V22) on the lobby path. Ran, one run |
| B1, B2 | Ran: the exchange runs every 240 ticks from tick 60 in a lobby game with two kind-2 characters; both machines compute in the same tick; no false mismatch in about 230 rounds |
| B2, B13 | Ran: a covered value changed on one machine makes that machine drop the owner at the next round; the owner freezes for about 930 frames and then drops the other; each returns to the lobby 239 ticks after its drop. Neither sees the out-of-sync notice |
| B13 | Ran: a difference in a bag's item bytes is not seen by the exchange (fourteen rounds passed over it) |
| new (L) | Lobby protocol with the real client: no reply refused on the main path; the encrypted-string padding and the 52-byte discovery datagram; UDP port in 4000–4004; the game reconnects by itself after a drop and does not log in again (S1) |

### 19.15 Not done

- More than one run of each kind: 19.10 is four fights and one run in the hub. The soak
  of sections 17 and 18 was not repeated through the lobby.
- Characters that earned their levels, bought their equipment and learnt their skills in
  play; here the levels and skills are written.
- The door from `drundar`: the arena level was entered by the pending-level write.
- More than two machines; a joiner's own-network path; packet loss or delay on the
  runners' path (it is the host's loopback interface: nothing is lost or late).
- Anything on a console or in PCSX2. Two copies of one Play! build show logic only.
