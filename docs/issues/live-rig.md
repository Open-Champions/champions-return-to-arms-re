# A live rig: the game running headless on Play!'s core

Status of this document: phase 1 (sections 1–6), phase 2 (section 7: two joined
machines, the baseline, the arena) phase 3 (section 8: fuzzing at scale, a float
mismatch between the machines, the lag sections) phase 4 (section 9: the arena with
characters that have levels and skills — which does diverge — and a tested patch
proposal for the spin skill, SB1) and phase 5 (section 10: the pet and the item bytes
traced, and the arena with every section on) and phase 6 (section 11: every class skill
swept, other levels, and an audit of what a prediction call leaves changed). In short: two machines play one lockstep game here;
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
