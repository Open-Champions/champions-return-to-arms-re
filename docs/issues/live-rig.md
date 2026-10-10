# A live rig: the game running headless on Play!'s core

Status of this document: phase 1 done (sections 1–4c), the network question answered and
the first piece of phase 2 running (4d). Phase 2 itself — two runners joined — is not
built.

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
     last octet — a machine becomes a peer by hearing its own announcement, so the
     network must deliver broadcasts to the sender;
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
