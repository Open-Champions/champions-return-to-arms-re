# How the game is put together

A map for people starting on this code. Every statement here comes from reading the
executable; the evidence (addresses) is in `FINDINGS.md`, `names.tsv`, `symbols/` and the
area documents in this folder. Nothing in this project has been confirmed on a running game
yet.

Each part of the code has its own document; this page is the summary they were checked
against: [startup](startup.md) (really the item system), [creatures](creatures.md),
[netcode](netcode.md), [script](script.md), [objects](objects.md), [engine](engine.md),
[player](player.md), [ui](ui.md), [gameplay](gameplay.md), [audio-save](audio-save.md),
[monsters](monsters.md), [skills](skills.md), [mainloop](mainloop.md), [netlib](netlib.md),
[runtime](runtime.md). The lobby side is in [lobby-protocol](lobby-protocol.md) and
[online-setup](online-setup.md).

## The executable

| | |
|---|---|
| File | `SLUS_209.73` from the US disc, version 2.00 NTSC |
| SHA-256 | `292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675` |
| CPU | MIPS R5900 (PS2 Emotion Engine), little endian, 32-bit pointers |
| Code | `.text` at 0x100000, 3,038,272 bytes, 7,732 functions; entry point 0x14fa88 |
| Compiler | GCC 2.9x, old C++ ABI; symbols stripped, C++ type names kept |
| Engine | Snowblind (the engine of Baldur's Gate: Dark Alliance and Champions of Norrath) |

## Reading C++ in this binary

- A virtual table is an array of 8-byte entries: `s16 thisDelta, s16 pad, u32 function`.
  Entry 0 is the type-info slot. `tools/vtab.py` numbers entries from 1, so slot *n* is at
  table offset `n * 8` and its function pointer at `n * 8 + 4`. A call looks like
  `addiu r, vtable, n*8; lh delta, 0(r); lw fn, 4(r); jalr fn` with `this + delta` in `$a0`.
- The table pointer sits at `+0x48` in every `GameObject`, `+0x60` in a `Skill`, `+0x14` in
  a `Spell`.
- `GameObject` has 16 virtual slots and `Creature` 39; all are described in
  [objects](objects.md) and [creatures](creatures.md). The ones met most often: 1
  destructor, 2 take damage (amount, attacker, flags), 4 run (once per simulated frame),
  5 draw, 6 "something touched me", 13 interact prompt, 14 interact, 15 clone; `Creature`
  slot 20 answers "is this other object my enemy" and slot 27 sets the AI state.
- 403 class names are in `rtti_classes.txt`; `vtables.txt` gives each class's table address.

## Objects

- Every object starts with three handle-list heads (+0, +4, +8), a flag word at +0xc and a
  position at +0x10/+0x14/+0x18 (x, y, height). Radius is +0x1c, height extent +0x20,
  facing angle (16-bit) +0x38, a private random seed +0x44.
- Flag bits read so far: 0x2 not drawn, 0x8 dead, 0x20 creature, 0x40 player, 0x100 flash
  when drawn, 0x8000 not run, 0x100000 can be interacted with, 0x20000 prediction copy,
  0x200000 this machine's own player, 0x4000000 prediction copy is catching up.
- Objects are referenced through *handle lists* (`handle_link`, `handle_clear`,
  `iter_begin/next/end`): deleting an object nulls every handle that points at it. Iterators
  take a flag mask of objects to skip.
- The world is a 120 × 120 grid of 256-unit cells. `world_collectObjectsInBox` is the
  query nearly everything uses. Objects are run from one of three lists: every frame, every
  15th frame or every 60th frame, depending on whether they are near a player.
- `pool_new` is the allocator; it zero-fills.

## Time and tasks

`tasks_run` runs two kinds of task in priority order: *run* tasks, once per simulated frame,
and *draw* tasks, once per displayed frame. Known run tasks: object visibility (-1), misc
sync (1), `runObjects` (10), camera (11), death handling (20), HUD (50), arena (100),
scripts (125), cutscene (300), route plotting (1000). Known draw tasks: particles (15),
world (30), inventory (50), cutscene (300).

## Randomness

There are several generators and it matters which one code uses:

| Generator | Where | Shared between machines |
|---|---|---|
| Global | `g_randSeed` 0x404464 | yes — part of the sync check |
| Per object | object +0x44, seeded from the global one in the constructor; per spell at spell +0x10 | yes, as long as the object runs identically everywhere |
| Cosmetic | `g_cosmeticSeed` 0x404460 | no — seeded from the CPU cycle counter at boot; meant for particles and sounds |
| A further cosmetic one | 0x404468 | no — effects and decals |
| C library `rand` | 0x3b70f0 | no — seeded by the network library |

Every object constructor draws from the global seed, so creating an object on one machine
only is enough to break sync.

## Online play

- The lobby (`con.soegames.net`, TCP) only matches players. Gameplay is peer to peer: the
  game's own netcode sends plain UDP datagrams. SOE's UdpLibrary is used only for the
  player-to-player handshake before a game starts.
- The simulation is deterministic lockstep: every machine runs the same frame with the same
  inputs. `net_frameLoop` (0x139e88) applies each peer's input record for the frame,
  processes queued game messages, runs the run tasks, then stores a hash of the frame:
  `g_randSeed` plus the integer x, y, height of every player. A peer whose hash differs for
  the same frame is shown as "… IS OUT OF SYNC!".
- Nothing is resent on a timer; every packet repeats the frames the other side has not
  acknowledged. A stalled frame becomes a frame of input delay that drains slowly — see
  [netcode](netcode.md), "Pacing and lag".
- An input record is 24 bytes per frame. A machine's own input goes through the same lossy
  encode → decode as the copy sent over the wire before the simulation uses it.
- To hide latency, each machine keeps a *prediction copy* of its own player (a clone with
  flag 0x20000) and runs the player's code on it for frames that are not confirmed yet
  (`net_predictLocalPlayer`, 0x131d88). Afterwards it restores the global seed, the player's
  hit points and mana, and nothing else. Code that changes shared state must therefore check
  for the copy. The copy is what gets drawn on its owner's screen; the real local player is
  hidden from drawing and from queries made while predicting.
- Three kinds of state exist side by side: shared (must match everywhere), per machine
  (camera, audio position, menus, the prediction copy, what was drawn) and cosmetic. A bug
  that lets the second kind influence the first is a desync. `FINDINGS.md` lists the ones
  found so far.

## Level scripts and cutscenes

- Each level has a `script.scr`: compiled bytecode for the Small/AMX abstract machine (51
  opcodes in use) that calls 191 built-in commands by name. `tools/scr.py` decompiles it.
- Scripts are started by trigger volumes, object death, interaction, deferred calls and
  cutscene end actions.
- A `.cut` file is a timeline of keys for the camera, dialog and level objects.
  `cut_runFrame` advances it once per simulated frame in a net game.

See `docs/FORMATS.md` for the file formats.
