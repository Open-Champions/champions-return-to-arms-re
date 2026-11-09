# Arrival research round 7: the round-6 refusals that now run

2026-11-09. Original work extends round 6 `56a6760482844e9bb63b8b014aa722df3e8f74d2`.
**STATUS: PARTIAL.** These stages execute the original handlers past the six
refusals named at the end of
[loading-arrival-r6.md lines 184–188](loading-arrival-r6.md#L184). They are not
a loader census and not a playable arrival. Round 7 also corrects one round-6
claim (the delete frees its block) and fixes the two round-6 LOW findings.

Bodies 0–11 and seeds 7 and 20973 agree on every result below. The test keeps
one value per stage and fails if any body or seed differs
([lines 72–78](../tools/difftest_arrival_stage_r7.py#L72)). The executable
digest is the existing loading pin. No instruction is patched and no callee is
stubbed. Two syscalls are modelled, both named below: Deci2 124 function `0x10`
(borrowed) and one WakeupThread return (this round).

## Fixtures and borrowed handlers

Each fixture is disclosed where the test makes it:

- **Stack guard.** `0x19d9f8` checks that the low `0x1400` bytes at `0x1fc0000`
  are `0xa5`. Otherwise it prints and stores to address 0 (`0x19da4c`).
  **Observed:** `engine_init` fills that range at boot. The fill value is set at
  `0x19d230` and stored at `0x19d244`. These fixtures never run `engine_init`, so
  the test plants the low `0x1400` bytes. It asserts the `0x19d230` word first
  ([lines 98–101](../tools/difftest_arrival_stage_r7.py#L98)).
- **Camera.** A sealed camera block at `0x4f8450`, as in round 5. `0x1e2168`,
  reached from `playerSel_finish`, stores through it.
- **Timer 0.** A 16-byte map at `0x10000000`. The warm-up loop stores 0 there
  (`0x322f04`), and `0x17fce0` reads it twice. It is a memory word, not a
  timer model.
- **Deci2 function `0x10`.** `dbg_printf` `0x355490` reaches syscall 124 on
  every newline. Round 7 merges `t3/research-death-reload` `543ea93` and
  calls its opt-in `EE.install_deci2_kputs`. See
  `t3/research-death-reload` `docs/death-reload-sequence.md` lines 116–139.
  That merge only adds to `tools/ee_emu.py`. Default traps are unchanged.
- **WakeupThread, one return.** `0x17fce0` calls syscall 51 (`0x352910`) with the
  id word `0x7cfd04`. The death-reload handlers do not model 51. The test
  answers 51 only when the return address is `0x17fd20`, and writes v0 = 0.
  **Observed:** the instruction at `0x17fd24` overwrites v0 before any read. The
  test asserts that word ([lines 111–118 and 274](../tools/difftest_arrival_stage_r7.py#L111)).
  The retail result is **Unknown**. Every other syscall goes to the
  death-reload dispatcher, which still raises `CpuTrap` for unmodelled numbers.
- **Registers.** The loader stage jumps into `mainloop_runSession` at
  `0x322e58`. It sets s0–s7 and fp to the values that function's own `lui`s
  leave there (`0x322ce0`, `0x322dcc`, `0x322e0c` and others;
  [line 66](../tools/difftest_arrival_stage_r7.py#L66)).
- **Resident lump.** Stage E copies entries from the private route-2 archive
  into emulator memory. No byte is written to a tracked file or a log.

## Stage record

**Observed, Executed** by `tools/difftest_arrival_stage_r7.py`.

| Stage | Reached | Exact next stop |
|---|---|---|
| New-game request | `0x1e3ba0` stores the `0x53d3e8` string at `0x4fdc30`. `0x22a360(0)` copies it to `0x41b6d0`, with orientation `0xff`. `0x320edc` splits it into `0x41b721` and `0x44fe18` | before `game_loadLevel` `0x1e55c0`, a0 = `0x41b721` |
| Loader, `0x322e58` onward | warm-up start, four `dbg_printf` returns, the deferred promote, ten warm-up passes (10 → 0), the shop test | syscall 48 at `0x3528e4`, return address `0x322500`, inside `loadscreen_stop` `0x3224d8` |
| Loader, level `hub` | the same through the warm-up loop, then `shop_openOrStock` `0x1c7af8` → `lump_load` `0x173558` | before the disc lookup `0x1724fc` |
| Clip word non-zero | `anim_push` `0x170838` and `0x170bc8` run. With a capacity byte, one 32-byte entry is pushed. `+0x17c` = clip `+4` + 1 | the entry stops before `0x14598c`, as in round 6 |
| Slot 19, value 1 | `+0xc` bit 0 is set | the entry stops before `0x14598c` |
| Slot 19, value 1, `+0x11c` bit 0 | `0x182b00` is called with world word `0x44fdc8` = 0 | fault at pc `0x182b08`, load address `0x20` |
| Delete, no property list | `0x14cf90(obj, 3)`: three handle clears, then tail-jump to `pool_free` `0x150470` | returns. The block is on the free list |
| Delete, `name=` property | `objNames_remove` `0x14be58` once. Name count 1 → 0. Then the same free | returns |
| `cut_setup` and the cut, real lump | setup once at frame 0, 12 cut actors, 1879 advancing task frames, clock 1 → 1880 | the end frame runs `mainloop_startWarmup`, the camera, and the pending post action (`0x144b44`). The cut-active byte is 0 |

## The request a live new game makes

**Observed, Executed** ([lines 122–243](../tools/difftest_arrival_stage_r7.py#L122)).
`frontend_startPlayerSelect` `0x1e3ba0` copies the executable string at
`0x53d3e8` (`hub`) to `0x4fdc30`. The stores are at `0x1e3c44` and `0x1e3c48`.
It then reaches `playerSel_start` `0x2245b8`, which the test does not enter.
With the word `0x4f70a0` set, it stores only the empty first byte of
`0x53d330`. With PvP mode B (`0x4f7120`) set, it reaches the arena picker
`0x304bc8` first.

**Executed:** `game_getHubName` `0x1ec300` reads three bits at the current
difficulty `0x4f719c`:

- the decision bit, record `+0x4c1b`, at `0x1bf960`;
- the choice bit, record `+0x4c1a`, at `0x1bf8d8`;
- the mission-1 completion bit `0x2` of record `+0x4bbf` + 13 × difficulty + 1, at `0x1bf730`.

All eight combinations ran. It returns `0x53d6c0` (`hub2`) only when all three
bits are set, and `0x53d6b8` (`hub`) otherwise
([line 174](../tools/difftest_arrival_stage_r7.py#L174)).

**Executed:** `playerSel_finish` `0x22a360` with argument 0 copies `0x4fdc30` to
the request `0x41b6d0` with `strcpy` `0x3b868c`. It stores `0xff` at `0x41b720`
from `0x22a484`. The request equals `hub`, so it replaces it with the
`game_getHubName` result. It calls `0x1ec300` once and the fade wait `0x322954`
once. On the fixture records the request is `hub`. With the three bits set, it
is `hub2`.

**Executed:** `mainloop_loadRequestedWorld` `0x320edc` then copies the request
into `g_levelName` `0x41b721`, by bytes from `0x3210ac` and `0x3210d8`. It
copies the base into `0x44fe18` with `strcpy` and clears the first byte of the
request. It enters `game_loadLevel` `0x1e55c0` with a0 = `0x41b721`. Two
other requests split the same way:

- the mission-1 row's start level, read from `g_missionTable` `0x4fe540` + 8 (`blood1`);
- the boot request, the string at `0x554898` (`strife`).

**Observed:** `main` copies `0x554898` into the request at `0x323edc–0x323efc`.
`frontend_start` `0x1e1f34` copies `0x53d0d0` (`intro`) into the same buffer
at `0x1e2098–0x1e20b4`. `main` enters the front end first when offline
([startup.md line 304](startup.md#L304)).

**Inferred:** `game_loadLevel` loads `<base>.gob`
([loading-transitions.md line 177](loading-transitions.md#L177)). That function
is not executed here. Matching each split name to an archive stem in the
private manifest gives these route ordinals
([line 238](../tools/difftest_arrival_stage_r7.py#L238)):

- a new game selects route 0;
- the mission-1 start selects route 2;
- the boot request selects route 1.

**Inferred:** offline, the front end replaces the boot request before a session
runs. A live single-player arrival therefore reaches route 0 first and route 2
from the mission menu. `t3/research-strife-drundar` `docs/strife-drundar.md`
lines 4–6 records that `blood1`'s good-choice exit requests `strife`, which is
route 1. **The manifest order is not the play order.**

**Unknown:** the `game_loadLevel` body for these names. The mission-menu state
that performs the row copy is not executed here (`missionMenu_run` state 8,
`0x2321c4–0x2322d4`).

## The loader from `0x322e58` to `loadscreen_stop`

**Observed, Executed** ([lines 268–332](../tools/difftest_arrival_stage_r7.py#L268)).
The route-0 entry of round 6 runs first, with the same model comparison. The
run then starts at `0x322e58`.

`mainloop_startWarmup` `0x322934` stores 10 at `g_warmupFrames` `0x506048`.
`dbg_printf` prints `b` and returns, and so does every later call. The loader's
one `0x1eda24` call promotes the queue to front 2, back 0, parity 1. It runs no
native and no `0x145690`. `dbg_printf` then prints `c`, the stack check
`0x19d9f8` returns, and the net byte `0x402791` is 0.

Each of the ten warm-up passes calls these, in this order:

1. `game_rebuildAlivePlayers` `0x1e72f8`;
2. `drawWorld` `0x1ebc18`;
3. `lump_pollAsync` `0x172ca8`;
4. `0x17d830`;
5. `0x17fce0`, which makes the WakeupThread call with id 0;
6. `0x17fe88`.

`0x17fe88` returns 0 each time. Each pass stores 0 at the timer word from
`0x322f04`, and the counter falls 10, 9, … 0 through stores at `0x322f30`
([lines 320–330](../tools/difftest_arrival_stage_r7.py#L320)). `Camera_update`
`0x203400` is not called because the camera word is 0. `cut_runFrame` is not
called because the cut byte `0x44fcd0` is 0. `0x1a30b0` is not called because
the player pointer `0x4dcec8` is 0. Each of the four `dbg_printf` calls reaches
Deci2 once.

After the loop, `dbg_printf` prints `d` and the shop test compares the level
name with four executable strings. The fixture level name is empty, so no shop
runs. `dbg_printf` prints `e`. `loadscreen_stop` `0x3224d8` stores 1 at
`0x5060a0` from `0x3224ec`. It then calls `ReferThreadStatus` with the id word
`0x506090`, which is `0xffffffff`, and repeats until the status is `0x10`. That
syscall is the stop ([line 312](../tools/difftest_arrival_stage_r7.py#L312)).

**Executed:** with the level name set to the executable string `0x554678`
(`hub`), the loop is the same. Then `shop_openOrStock` `0x1c7af8` is called from
`0x3230c4` with a1 = 1. It calls `lump_load` `0x173558`, which stops before
`0x1724fc` ([line 302](../tools/difftest_arrival_stage_r7.py#L302)). In a
third run without that stop, the lookup runs once and misses. The miss ends on
the deliberate store to address 0 at `0x17363c`, and `loadscreen_stop` is not
reached.

**Unknown:** the loading-screen thread. `game_loadLevel` starts it at
`0x321e60`, which this fixture does not run. Its id and its status are unknown,
and so is the result of syscall 48 here. WakeupThread's retail result, and
whether `drawWorld` would draw with a world loaded, are also unknown.

## A clip word and slot 19's value

**Observed:** `setState` `0x23d680` reads the clip at `obj + 0x128 + 8 × state`.
When the clip is non-zero it calls `anim_push(obj + 0x98, clip, mode)`. The
mode is 3 when bit `0x2` of `obj + 0x12c + 8 × state` is set, and 6
otherwise. It then calls `0x170bc8(obj + 0x98)` and adds clip `+4` + 1 to
`+0x17c`. Slot 19 receives bit 0 of that `+0x12c` word as its value.

**Executed** ([lines 372–418](../tools/difftest_arrival_stage_r7.py#L372)):

- **Clip `+4` = 5, capacity byte `+0x9d` = 0.** `anim_push` is called once
  with `(obj + 0x98, clip, 6)` and pushes nothing. No store touches
  `obj + 0xa0`–`+0xbf`. `+0x17c` changes from a `0x22222222` sentinel to 6
  (last store at `0x23d764`).
- **Capacity 4.** The depth byte `+0x9c` becomes 1 and the halfword `+0x9e`
  becomes the mode. The entry at `+0xa0` holds the clip, floats 1, 0, 1, 0 at
  `+8`–`+0x14`, 5.0 at `+0x18` (from `0x170bc8`), and the mode at `+0x1c`.
  The last store to each of those fields comes from the named function. Bit
  `0x2` gives mode 3; otherwise the mode is 6.
- **Value 1, `+0x11c` bit 0 clear.** `+0xc` becomes `0x10000001` (store at
  `0x23d878`). No collision call is made.
- **Value 1, `+0x11c` bit 0 set.** `0x182b00` is called from `0x23d7e0` with
  a0 = the word at `0x44fdc8`, which is 0, and a2 = 0. It faults at `0x182b08`
  on address `0x20`. `0x182c98` is not reached and nothing is queued.

**Unknown:** `0x182b00` and `0x182c98` with a real collision world.

## Delete with and without a property list

**Correction to round 6.** Round 6 said the delete "does not call … `pool_free`
`0x150470`" and that the client should "not free it"
([loading-arrival-r6.md lines 27, 136 and 180](loading-arrival-r6.md#L27)).
That check counted only linking calls. **Observed:** `deleteMonster` `0x144b44`
calls slot 1 with a1 = 3 (`0x144bb0`). `GameObject_dtor` `0x14cf90` tail-jumps
to `0x150470` at `0x14d1fc` when a1 bit 0 is set.

**Executed** ([lines 436–495](../tools/difftest_arrival_stage_r7.py#L436)).
With the round-6 fixture, which has no property list, the recorded stores
include exactly two from `pool_free`:

- at `0x1504bc`, the object address goes into the free-list head word, at
  `0x403a1c` + 16 × bucket;
- at `0x1504c4`, the previous head goes into the object's first word.

The name count stays 1, and no store touches it.

**Executed:** with a property list `{"kind=1", "name=<that name>", 0}` at
`+0x2c`:

- `strncmp` `0x3b91d8` is called six times, from `0x14d060` and `0x14d148`.
- `objNames_remove` `0x14be58` is called once from `0x14d19c`, with the value
  after `name=` and the object.
- The name count becomes 0. The only store that touches it is 4 bytes of 0 at
  `0x14be84`.
- The name search `0x14bf58` then returns no object for that name.
- The three handle clears and the same two free-list stores follow.

**Unknown:** objects with several `name=` entries, and a delete of an object
that has no creature flag.

## `cut_setup` past `0x14f498`, and the cut itself

**Executed, fixture refusals** ([lines 529–557](../tools/difftest_arrival_stage_r7.py#L529)):

- With only the round-6 fixture lump, `cut_setup` `0x19a6cc` builds `"%s.lmp"`
  from `0x44fe18`. That name is empty in the fixture, so the request goes to
  `lump_load` → `0x1724fc`, and the miss ends at `0x17363c`.
- With `0x44fe18` set to the fixture level, `res_find(level, "dialog.bin")`
  returns 0, and `0x2168a0` reads address 0.

The cut therefore needs the level's own entries.

**Fixture:** `resident_lump` keeps the `.cut`, `.bin` and `.dbin` entries of the
route-2 archive's level lump, 19 of 22, in archive order
([lines 509–526](../tools/difftest_arrival_stage_r7.py#L509)). The layout
matches the archive: a count, 12-byte records, packed names, and data aligned
to `0x80`. The original `lump_fixup` `0x1717d0` relocates it. **Observed:**
fixup removes the region variants and leaves 16 entries. The archive orders
entries by name with the region prefix stripped. A re-sorted copy fails the
binary search. The lump becomes resident entry 0, and `g_levelName` and
`0x44fe18` are set to its stem. `.world`, `.ob` and `.scr` are not loaded.

**Executed** ([lines 560–651](../tools/difftest_arrival_stage_r7.py#L560)).
The route-2 entries and post action run in the original code. The native order
is round 5's `ROUTE2_ORDER`. `cut_start` now reads the real cut header, which
lies inside the resident copy. The cut byte is 1, `g_warmupFrames` is 10 and
the clock `0x44fce0` is 1. The test then observes every native:

- **Three warm-up frames, `cut_runFrame(1)`, all return 0.** Frame 0 calls
  `cut_setup` once and stores 1 at `0x44fcd2` from `0x199bbc`. That is the
  only store to that byte. `cut_setup` leaves 12 actors at `0x83d188`. No frame
  calls `cut_advance` `0x199214`, and the clock stays 1. Argument 1 does not
  advance even with `g_warmupFrames` at 0.
- **Task frames, `cut_runFrame(0)`, with `g_warmupFrames` at 0.** That is the
  value the loader stage leaves. Every frame calls `cut_advance` once and adds
  1 to the clock. No native runs and the post byte `0x86fa80` stays non-zero
  while the cut is active.
- **The end.** On the 1879th task frame the clock reaches 1880 and the
  cut-active byte becomes 0. That frame calls `mainloop_startWarmup` from
  `0x199f3c`, so `g_warmupFrames` is 10 again. It then calls `0x2072e8` from
  `0x199f5c` and the post-action runner `0x1edac0` from `0x199f6c`.
- **The post action.** It runs the one native round 5 recorded: `deleteMonster`
  `0x144b44`, with a five-character name. The post byte becomes 0 and the
  queue stays empty.
- **One more frame**, in that state, does not advance and runs no native.

**Inferred:** the replacement post action that round 5 ran by hand is the one
the cut runs when it ends. The end also restarts the 10-frame warm-up.

**Unknown:**

- what the 12 actors draw;
- frames with the world, objects and script that the copy leaves out;
- the length of a cut other than this one;
- the `.world`, `.ob` and `.scr` fixups;
- the end path's effect on the loading-screen thread.

## Round-6 LOW fixes

- **R7-1.** The six legacy hide-mask rows now use `plant_mask` at base byte 3
  (offset `0x30`). That is clear of the flag halfword `+0x10` and the base byte
  `+0x21`. The test asserts both after the record writes. Rows 3–6 now run with
  flag bit `0x2` stored, and each still equals the complement.
- **R7-2.** The bag-count and name-count no-store checks now test every byte of
  each word. They use the same range test as the cut-frame check. While the
  object is planted, every store that touches the name count is a 4-byte store
  at its start.

The round-6 note's evidence links now point at the moved lines. The
`arrival_stage_r6` run after the fix passes on bodies 0–11 and both seeds.

## What the native client can implement

Under these fixtures, for every body 0–11:

- **New game.** Write the destination `hub`. Copy it to the request with
  orientation `0xff`. Replace `hub` with `hub2` only when the decision bit, the
  choice bit and mission 1's completion bit are all set at the current
  difficulty. Split the request into `g_levelName` and `0x44fe18` and load
  that level: route 0. The mission-1 start is route 2. The boot request is
  route 1, and offline the front end replaces it with `intro`.
- **Loader after the level load.** Start the 10-frame warm-up and run the
  deferred promote. Run ten passes of the six calls above while streaming is
  idle, counting down by one per pass. Then run the shop test by level name.
  Refuse at `loadscreen_stop`, which waits on a thread this path has not
  started. For `hub`, refuse at the shop's lump load.
- **`setState` with a clip.** Push one entry when the stack has room, with mode
  3 or 6 from bit `0x2`. Add clip `+4` + 1 to `+0x17c`. With a slot-19 value of
  1, set `+0xc` bit 0. Refuse when `+0x11c` bit 0 needs the collision world.
- **Delete.** Remove each `name=` value from the name table, clear the three
  handles, and **free the block**. Round 6's "do not free" is withdrawn.
- **The cut.** With the level's `.cut`, `.bin` and `.dbin` resident: run setup
  on the first warm-up frame and advance one clock step per task frame. When
  the cut-active byte clears (1879 steps for this cut), restart the warm-up and
  run the pending post action.

**Unknown, and still a refusal:**

- `game_loadLevel`, and the loading-screen thread it starts;
- `ReferThreadStatus` at `0x3528e4`;
- the shop's disc lookup;
- `0x182b00` with a collision world;
- the cut's `.world`, `.ob` and `.scr` entries;
- what the actors draw;
- the mission-menu copy for mission 1, which is not executed here;
- the level-name bytes the loader stores, which round 6 also listed.

Run: `PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_arrival_stage_r7.py local/SLUS_209.73 local/arrival-route-r4.json`.
Result: bodies 0–11, seeds 7 and 20973, all stages PASS. Log: `local/arrival-stage-r7.log` (untracked).
