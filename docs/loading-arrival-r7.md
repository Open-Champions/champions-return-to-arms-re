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
stubbed. Every stage asserts this, including the producer, the prop runs and the
cut refusals (added in round 8), and every stage of
[`difftest_arrival_stage_r8.py`](../tools/difftest_arrival_stage_r8.py). Two
syscalls are modelled, both named below: Deci2 124 function `0x10` (borrowed)
and one WakeupThread return (this round).

Round 8 closes the round-7 audit findings R8-1 to R8-12. Claims the round-7 test
did not check are now either asserted by `tools/difftest_arrival_stage_r8.py`
(bodies 0–11, seeds 7 and 20973) or relabelled. The changes are listed at the end
of this note, under "Round-8 fixes".

## Fixtures and borrowed handlers

Each fixture is disclosed where the test makes it:

- **Stack guard.** `0x19d9f8` checks that the `0x1400` bytes from `0x1fc0000`
  are `0xa5`. **Observed (static, asserted):** the base comes from the `lui` at
  `0x19d9fc`, the compare value from `0x19da2c` and the limit `0x1400` from the
  `slti` at `0x19da50`. On a mismatch it calls `dbg_printf` from `0x19da44` and
  stores to address 0 at `0x19da4c`. **Executed** (`guard`,
  [r8 lines 301–332](../tools/difftest_arrival_stage_r8.py#L301)): an intact guard returns. One changed byte at offset
  0 or `0x13ff` faults at `0x19da4c` on address 0 after one `dbg_printf`. A
  changed byte at offset `0x1400` is not checked.
  **Observed:** `engine_init` fills that range at boot. The fill value is set at
  `0x19d230` and stored at `0x19d244`. These fixtures never run `engine_init`, so
  the test plants the low `0x1400` bytes. It first asserts that the immediate
  at `0x19d230` is `-0x5b`
  ([lines 98–101](../tools/difftest_arrival_stage_r7.py#L98)).
- **Camera.** A sealed camera block at `0x4f8450`, as in round 5. `0x1e2168`,
  reached from `playerSel_finish`, stores through it.
- **Timer 0.** A 16-byte map at `0x10000000`. The warm-up loop stores 0 there
  (`0x322f04`). **Executed:** the run makes 20 reads of the map, all from
  inside `0x17fce0`–`0x17fd43`. It is a memory word, not a timer model.
- **Deci2 function `0x10`.** `dbg_printf` `0x355490` reaches syscall 124 on
  every newline. Round 7 merges `t3/research-death-reload` `543ea93` and
  calls its opt-in `EE.install_deci2_kputs`. See
  `t3/research-death-reload` `docs/death-reload-sequence.md` lines 116–139.
  That merge only adds to `tools/ee_emu.py`. Default traps are unchanged.
  **Disclosure (R8-9):** `543ea93` was audited as FIX. It carries two findings
  that were open at that commit: R7-2 (MEDIUM, `install_modelled_intc` delivers
  without reading COP0 Status; `tools/ee_emu.py` `_deliver_intc_for_sema`) and
  R7-1 (on the "That map is not a GS model" sentence, now at
  `docs/death-reload-sequence.md` line 347). Later death-reload commits close
  both, but that branch's latest audit is still FIX, so no later commit is
  merged here. This branch never calls `install_modelled_intc`. It relies only
  on `install_deci2_kputs` and on the opt-in dispatcher that the WakeupThread
  handler forwards to. Merging this branch still brings that code in.
- **WakeupThread, one return.** `0x17fce0` calls syscall 51 (`0x352910`) with the
  id word `0x7cfd04`. The death-reload handlers do not model 51. The test
  answers 51 only when the return address is `0x17fd20`, and writes v0 = 0.
  **Observed:** the instruction at `0x17fd24` is a `lui` of v0, so v0 is
  overwritten before any read. The test asserts the opcode and target register
  ([lines 111–118 and 278](../tools/difftest_arrival_stage_r7.py#L111)).
  The retail result is **Unknown**. Every other syscall goes to the
  death-reload dispatcher, which still raises `CpuTrap` for unmodelled numbers.
- **Registers.** The loader stage jumps into `mainloop_runSession`
  `0x322998` at `0x322e58`, the return address of its `dbg_printf` call at
  `0x322e50` ([line 66](../tools/difftest_arrival_stage_r7.py#L66)).
  **Observed (static, asserted by `loader_registers`,
  [r8 lines 157–181](../tools/difftest_arrival_stage_r8.py#L157)):** each planted value matches the instruction
  that sets it, and that instruction is the last one before `0x322e58` that
  writes the register:
  - s0 `0x5541f0`: `addiu` from s4 at `0x322e0c`;
  - s1 `0x420000`: `lui` at `0x322cd4`;
  - s3 `0x400000`: `lui` at `0x322ce0`;
  - s4 `0x550000`: `lui` at `0x322dcc` and `0x322e04`;
  - s5 `0x450000`: `lui` at `0x322e1c`;
  - s6 `0x450000`: `lui` at `0x322d2c`;
  - s7 `0x420000`: `lui` at `0x3229ac`;
  - fp `0x500000`: `lui` at `0x3229b4`.

  This scan reads instruction order, not control flow. **Correction (round 9):**
  round 8 said one branch skips `0x322e04`. Four branches before it land past
  it: `0x322b40`, `0x322cdc`, `0x322dc8` and `0x322dec`.
  **Observed (static, asserted by `loader_static`,
  [r9 lines 88–132](../tools/difftest_arrival_stage_r9.py#L88)):** `0x322dc8` is a `bne` (not the likely form)
  to `0x322e08`, with the first s4 setter `0x322dcc` in its delay slot. Every
  branch or `j` that lands in `0x322dd0`–`0x322e58` is itself in
  `0x322dc8`–`0x322e54`. The only `jr` is the epilogue's `jr ra` at
  `0x3235a0`. After `0x322dcc`, only `0x322e04` writes s4. So every path that
  reaches `0x322e58` runs `0x322dcc`, and s4 is `0x550000` on each of them.
  **Inferred:** the calls in between preserve s0–s7 and fp (they are
  callee-saved).
  **s2 is not planted.** No instruction in `0x322998`–`0x322e54` writes it, so
  at `0x322e58` it holds the caller's value. The test fills it with
  `0xa5a5a5a5`. **Observed (static, asserted):** the only instructions after
  `0x322e58` that name s2 are at `0x322ec0` (a `lui`, which writes it),
  `0x322f38`, `0x322f84`, `0x322f90`, `0x323354`, `0x323388`, `0x3233ec` and
  the epilogue `0x323580`. **Executed:** in every run, `0x322ec0` is the first of
  these that is reached, so the caller's s2 is never read.
  **Caller frame:** the run starts with the test's stack pointer and does not
  plant `mainloop_runSession`'s 0x60-byte frame. **Observed (static, asserted
  by `loader_static`):** the frame size is the immediate of `addiu sp, sp,
  -0x60` at `0x32299c` and of `addiu sp, sp, 0x60` at `0x3235a4`, in the delay
  slot of the final `jr ra`. These are the only two writers of sp in the
  function. **Observed (static, asserted):** after `0x322e58` the only stack-based accesses are the
  epilogue's, from `0x323578`. **Executed:** the run reads no byte of
  `[sp, sp + 0x60)`.
- **Resident lump.** Stage E copies entries from the private route-2 archive
  into emulator memory. No byte is written to a tracked file or a log.

## Stage record

**Observed, Executed** by `tools/difftest_arrival_stage_r7.py`.

| Stage | Reached | Exact next stop |
|---|---|---|
| New-game request | `0x1e3ba0` stores the `0x53d3e8` string at `0x4fdc30`. `0x22a360(0)` copies it to `0x41b6d0`, with orientation `0xff`. `0x320edc` splits it into `0x41b721` and `0x44fe18` | before `game_loadLevel` `0x1e55c0`, a0 = `0x41b721` |
| Loader, `0x322e58` onward | warm-up start, four `dbg_printf` returns, the deferred promote, ten warm-up passes (10 → 0), the shop test | syscall 48 at `0x3528e4`, return address `0x322500`, inside `loadscreen_stop` `0x3224d8` |
| Loader, level `hub` | the same through the warm-up loop, then `shop_openOrStock` `0x1c7af8` → `lump_load` `0x173558` | before the disc lookup `0x1724fc` |
| Clip word non-zero | `anim_push` `0x170838` and `0x170bc8` run. With a capacity byte, one 32-byte entry is pushed. `setState` zeroes `+0x17c`, then stores `+0x17c` + clip `+4` + 1, so it ends as clip `+4` + 1 | the entry stops before `0x14598c`, as in round 6 |
| Slot 19, value 1 | `+0xc` bit 0 is set | the entry stops before `0x14598c` |
| Slot 19, value 1, `+0x11c` bit 0 | `0x182b00` is called with world word `0x44fdc8` = 0 | fault at pc `0x182b08`, load address `0x20` |
| Delete, no property list | `0x14cf90(obj, 3)`: three handle clears, then tail-jump to `pool_free` `0x150470` | returns. The block is on the free list |
| Delete, `name=` property | `objNames_remove` `0x14be58` once. Name count 1 → 0. Then the same free | returns |
| `cut_setup` and the cut, real lump | setup once at frame 0, 12 cut actors, 1879 advancing task frames, clock 1 → 1880 | the end frame runs `mainloop_startWarmup`, the camera, and the pending post action (`0x144b44`). The cut-active byte is 0 |

## The request a live new game makes

**Observed, Executed** ([lines 122–247](../tools/difftest_arrival_stage_r7.py#L122)).
`frontend_startPlayerSelect` `0x1e3ba0` copies the executable string at
`0x53d3e8` (`hub`) to `0x4fdc30`. The stores are at `0x1e3c44` and `0x1e3c48`.
It then reaches `playerSel_start` `0x2245b8`, which the test does not enter.
With the word `0x4f70a0` set, it stores only the empty first byte of
`0x53d330`. With PvP mode B (`0x4f7120`) set, it reaches the arena picker
`0x304bc8` first.

**Executed** at each difficulty 1–5 (`hub_name`, [r8 lines 336–363](../tools/difftest_arrival_stage_r8.py#L336);
round 7 ran difficulty 1 only): `game_getHubName` `0x1ec300` reads three bits at
the current difficulty `0x4f719c`:

- the decision bit, record `+0x4c1b`, at `0x1bf960`;
- the choice bit, record `+0x4c1a`, at `0x1bf8d8`;
- the mission-1 completion bit `0x2` of record `+0x4bbf` + 13 × difficulty + 1, at `0x1bf730`.

All eight combinations ran at each difficulty. It returns `0x53d6c0` (`hub2`)
only when all three bits are set, and `0x53d6b8` (`hub`) otherwise
([line 175](../tools/difftest_arrival_stage_r7.py#L175)).

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
([line 242](../tools/difftest_arrival_stage_r7.py#L242)):

- a new game selects route 0;
- the mission-1 start selects route 2. This is the story level at row 0 `+8`.
  The evil alternative `+0x0c` ([data-tables.md line 632](data-tables.md#L632))
  is null in row 0 (`assert evil == 0` in `hub_name`, added in round 9), so it does not replace `+8` for
  mission 1. The menu state that uses `+0x0c` is not executed here;
- the boot request selects route 1.

**Inferred:** offline, the front end replaces the boot request before a session
runs. A live single-player arrival therefore reaches route 0 first and route 2
from the mission menu. `t3/research-strife-drundar` `docs/strife-drundar.md`
lines 4–6 records that `blood1`'s good-choice exit requests `strife`, which is
route 1. **The manifest order is not the play order.**

**Unknown:** the `game_loadLevel` body for these names. The mission-menu state
that performs the row copy is not executed here (`missionMenu_run` state 8,
`0x2321c4–0x2322d4`). `t3/research-story-route` `docs/story-route.md` §2
records the menu's write of `blood1` to the pending-level buffer, as
[loading-transitions.md lines 119–121](loading-transitions.md#L119) cites.

## The loader from `0x322e58` to `loadscreen_stop`

**Observed, Executed** ([r7 lines 272–336](../tools/difftest_arrival_stage_r7.py#L272);
every detail below is also asserted in the fixture, `hub` stop and `hub` miss
runs by `loader` in [r8 lines 185–297](../tools/difftest_arrival_stage_r8.py#L185)). The route-0 entry of
round 6 runs first, with the same model comparison. The run then starts at
`0x322e58`.

`mainloop_startWarmup` `0x322934` stores 10 at `g_warmupFrames` `0x506048`.
`dbg_printf` is called from `0x322e64` with the format at `0x554668`. The
loader's one `0x1eda24` call promotes the queue to front 2, back 0, parity 1. It
runs no native and no `0x145690`. `dbg_printf` is called from `0x322e78` with
`0x554670`. The stack check `0x19d9f8` is called from `0x322e84` with
(`0x5541f0`, `0x7ba`) and returns: its return address `0x322e8c` is reached.
There the net byte `0x402791` is read and is 0, so `0x13dcd0` is not called.

Each of the ten warm-up passes calls these, in this order:

1. `game_rebuildAlivePlayers` `0x1e72f8`;
2. `drawWorld` `0x1ebc18`;
3. `lump_pollAsync` `0x172ca8`;
4. `0x17d830`;
5. `0x17fce0`, which makes the WakeupThread call with id 0;
6. `0x17fe88`.

`0x17fe88` returns 0 each time: v0 is 0 at the branch `0x322f18` that tests it,
in all ten passes (asserted). **Observed (static, asserted by `loader_static`):**
`0x322f18` is `bne v0, zero` to `0x322f34`. It follows `jal 0x17fe88` at
`0x322f10`, whose delay slot does not write v0. Each pass stores 0 at
the timer word from `0x322f04`, and the counter falls 10, 9, … 0 through stores
at `0x322f30` ([r7 lines 324–334](../tools/difftest_arrival_stage_r7.py#L324)).
The calls that are skipped, and the reads that skip them (all asserted):

- `Camera_update` `0x203400`: the camera word `0x4f8450` is read at `0x322ebc`,
  10 times, and is 0.
- `cut_runFrame`: the cut byte `0x44fcd0` is read at `0x322edc`, 10 times, and
  is 0.
- `0x1a30b0`: the player count `0x4d8ae0` is 1 (read at `0x322f38` and
  `0x322f90` in each pass). Player 0's pointer `0x4dcec8` is read at `0x322f58`,
  10 times, and is 0.

Each `dbg_printf` call is followed by exactly one Deci2 call before the next
`dbg_printf`.

After the loop the stack check is called again, from `0x322ff0` with
(`0x5541f0`, `0x7f0`), and returns to `0x322ff8`. `dbg_printf` is called from
`0x322ffc` with `0x554580`. The net byte is read again at `0x323004` and is 0.
The shop test then compares the level name with four executable strings, from
`0x323074`, `0x32308c`, `0x3230ac` and `0x3230d8`. The fixture level name is
empty, so no shop runs. `dbg_printf` is called from `0x3230fc` with `0x5546a8`.
`loadscreen_stop` `0x3224d8` stores 1 at `0x5060a0` from `0x3224ec`. It then
calls `ReferThreadStatus` with the id word `0x506090`, which is `0xffffffff`,
and repeats until the status is `0x10`. That syscall is the stop
([r7 line 316](../tools/difftest_arrival_stage_r7.py#L316)).

**Executed:** with the level name set to the executable string `0x554678`
(`hub`), everything above up to the shop test is the same and is asserted again:
the three `dbg_printf` formats, the pass order, the counter and timer stores,
the promote and the reads. The first comparison (`0x323074`) matches.
`shop_openOrStock` `0x1c7af8` is called from `0x3230c4` with a1 = 1. It calls
`lump_load` `0x173558`, which stops before `0x1724fc`
([r7 line 306](../tools/difftest_arrival_stage_r7.py#L306)). In a third run
without that stop, the lookup runs once and misses. `dbg_printf` is called once
more, from `0x173634`, and the miss ends on the deliberate store to address 0
at `0x17363c`. `loadscreen_stop` is not reached.

**Unknown:** the loading-screen thread. `game_loadLevel` starts it at
`0x321e60`, which this fixture does not run. Its id and its status are unknown,
and so is the result of syscall 48 here. WakeupThread's retail result, and
whether `drawWorld` would draw with a world loaded, are also unknown.

## A clip word and slot 19's value

**Observed:** `setState` `0x23d680` reads the clip at `obj + 0x128 + 8 × state`.
When the clip is non-zero it calls `anim_push(obj + 0x98, clip, mode)`. The
mode is 3 when bit `0x2` of `obj + 0x12c + 8 × state` is set, and 6
otherwise. It then calls `0x170bc8(obj + 0x98)`. Slot 19 receives bit 0 of
that `+0x12c` word as its value.

**Executed** (`props`, [r8 lines 367–459](../tools/difftest_arrival_stage_r8.py#L367)): `setState` stores 0 at
`+0x17c` from `0x23d6ac`, before the push. After `0x170bc8` returns it stores
`+0x17c` + clip `+4` + 1 from `0x23d764`. **Observed (static, asserted by
`loader_static` and `sum_static`, [r9 lines 88–155](../tools/difftest_arrival_stage_r9.py#L88)):** `0x23d734`
is `jal anim_push` and `0x23d73c` is `jal 0x170bc8`, so `0x23d744` is the
return address of the `0x170bc8` call. The sum is built from `0x23d744` to
`0x23d760`: the state word `+0x178`, shifted left by 3 and added to obj + 8,
indexes the clip at `+0x120`. Its word `+4` is added to `+0x17c`, and
`0x23d760` is `addiu v1, v1, 1`. **The `+1` is that immediate.**
**Executed** (`states`, [r9 lines 184–250](../tools/difftest_arrival_stage_r9.py#L184)): `setState` is called
directly on the round-8 prop at states 0, 1, 2 and 5, with clip `+4` = 9 and
`0x40`. Decoy clips (`+4` = `0x3000` + index) sit in every other slot 0–7.
Each run gives exactly the stores (`0x23d6ac`, 0) and (`0x23d764`, clip `+4` +
1), never state + 1, and `+0x178` = the state. The zero store is recorded
before `anim_push` is entered, and the `0x23d764` store after `0x23d744` is
reached. The late-write control holds at states 2 and 5. For clip `+4` = 5, 9 and `0x40`, with
`0x22222222` or `0x13579bdf` planted at `+0x17c` beforehand, the stores to
`+0x17c` are exactly (`0x23d6ac`, 0) and then (`0x23d764`, clip `+4` + 1). In a
control run, a value written into `+0x17c` after `0x170bc8` returns (`0x100` or
`0x7000`) becomes the base of the sum. So the sum's base is the word itself,
which `setState` has just zeroed, and nothing between the two stores writes it.
The result is clip `+4` + 1.

**Executed** ([lines 377–423](../tools/difftest_arrival_stage_r7.py#L377)):

- **Clip `+4` = 5, capacity byte `+0x9d` = 0.** `anim_push` is called once
  with `(obj + 0x98, clip, 6)` and pushes nothing. No store touches
  `obj + 0xa0`–`+0xbf`. `+0x17c` changes from a `0x22222222` sentinel to 6
  (last store at `0x23d764`).
- **Capacity 4.** The depth byte `+0x9c` becomes 1 and the halfword `+0x9e`
  becomes the mode. The entry at `+0xa0` holds the clip, floats 1, 0, 1, 0 at
  `+8`–`+0x14`, 5.0 at `+0x18` (from `0x170bc8`), and the mode at `+0x1c`.
  Bit `0x2` gives mode 3; otherwise the mode is 6.
- **Capacity 4, entry over a sentinel** (round 8). `obj + 0xa0`–`+0xbf` is
  filled with `0x5a` before the call, except `+4`, which is 0 or points at a
  linked block. The halfword `+0x9e` is planted as `0x100`. Every byte of the
  entry is then written, and each field's stores are:
  - `+0`, the clip: `0x170878`;
  - `+4`: not written when it is 0. When it points at a block, `0x17088c` stores
    0 at that block's `+0x14` and `0x170890` stores 0 at `+4`;
  - `+8` = 1.0: `0x1708a8`;
  - `+0xc` = 0: `0x1708a4`;
  - `+0x10` = 1.0: `0x1708ac`;
  - `+0x14` = 0: `0x1708b0`;
  - `+0x18`: 0 from `0x170880`, then 5.0 from `0x170c1c` (in `0x170bc8`);
  - `+0x1c`, the mode: `0x1708a0`;
  - `+0x1e` = 0: `0x170888`.

  `+0x9e` becomes `0x100` OR the mode, in one store at `0x17087c`.
- **`+0x9e` with low bits that overlap the mode** (round 9, `nine_e`,
  [r9 lines 162–180](../tools/difftest_arrival_stage_r9.py#L162)). Capacity 4, over the sentinel. The planted
  halfword and the result:
  - mode 6: `0x105` → `0x107`, `0x1ff` → `0x1ff`, `0x106` → `0x106`, 0 → 6;
  - mode 3: `0x104` → `0x107`, `0x103` → `0x103`, `0x1ff` → `0x1ff`.

  Each value is one store at `0x17087c`. Adding the mode, replacing the low
  byte, or replacing the low 3 bits would each give a different result on at
  least one of these inputs. **Observed (static, asserted by `nine_e_static`,
  [r9 lines 63–77](../tools/difftest_arrival_stage_r9.py#L63)):** `0x17086c` is `lhu v0, 6(a3)`, `0x170874` is
  `or v0, v0, a2` and `0x17087c` is `sh v0, 6(a3)`. a3 is a0 (`0x170840`), and
  nothing else in `anim_push` writes v0 between those two instructions, or a2
  before the `or`. So `anim_push` **ORs** the mode into `+0x9e`.
- **A second push** (round 9, `states`). `setState` clears the depth byte
  `+0x9c` (`sb zero` at `0x23d6f8`, asserted by field) and pushes at depth 0
  again. It does not clear `+0x9e`. After a mode-6 push left `0x106`, a second
  `setState` (state 1, mode 3) stores `0x107` at `0x17087c`. The modes
  accumulate.
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

**Executed** ([lines 441–500](../tools/difftest_arrival_stage_r7.py#L441)).
With the round-6 fixture, which has no property list, the recorded stores
include exactly two from `pool_free`:

- at `0x1504bc`, the object address goes into the free-list head word, at
  `0x403a1c` + 16 × bucket;
- at `0x1504c4`, the previous head goes into the object's first word.
  Round 8 (`free_head`, [r8 lines 463–484](../tools/difftest_arrival_stage_r8.py#L463)) reads the free-list
  table before the delete. The value stored is the head word's old value.
  That is bucket 1, whose head is non-zero in this fixture.

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

**Executed, fixture refusals** ([lines 534–563](../tools/difftest_arrival_stage_r7.py#L534)):

- With only the round-6 fixture lump, `cut_setup` `0x19a6cc` builds `"%s.lmp"`
  from `0x44fe18`. That name is empty in the fixture, so the request goes to
  `lump_load` → `0x1724fc`, and the miss ends at `0x17363c`.
- With `0x44fe18` set to the fixture level, `res_find` `0x17365c` is called
  once. The call is the `jal` at `0x216894` (asserted by field) and it returns
  to `0x21689c` (round-8 log `site=` prints this return address;
  `dialog_site`, [r9 lines 271–275](../tools/difftest_arrival_stage_r9.py#L271)), with a0 = `"<level>.lmp"` and a1 = `"dialog.bin"`. It
  returns 0, and `0x2168a0` reads address 0 (`dialog_refusal`,
  [r8 lines 618–656](../tools/difftest_arrival_stage_r8.py#L618)).

The cut therefore needs the level's own entries.

**Fixture:** `resident_lump` keeps the `.cut`, `.bin` and `.dbin` entries of the
route-2 archive's level lump, 19 of 22, in archive order
([lines 514–531](../tools/difftest_arrival_stage_r7.py#L514)). The layout
matches the archive: a count, 12-byte records, packed names, and data aligned
to `0x80`. A copy built by the round-8 builder is byte-identical. The original
`lump_fixup` `0x1717d0` relocates it.

**Observed (static):** `0x1714a0` compares each name with five executable
strings at `0x533e08`–`0x533e28` and strips a matching prefix in place. Matching
records can be removed at `0x1719c8`–`0x171a34`. `res_find` finds an entry with
the binary search `0x171de4`, which compares with `0x3b8534`.
**Inferred:** the strings are region prefixes.

**Executed** (`lump_order`, [r8 lines 488–614](../tools/difftest_arrival_stage_r8.py#L488); counts only):

- Fixup removes 3 records, at archive indices 13, 14 and 15, and leaves 16.
- Before fixup, 2 adjacent pairs of names are out of order under `0x3b8534`.
  After fixup (prefixes stripped, three removed), 0 are. The binary search
  finds all 16 names, and the cut path runs setup with 12 actors.
- **Negative control, reversed records:** after fixup 15 pairs are out of
  order, the search finds 1 of 16, and the post action faults in `cut_start`
  `0x19b4dc` at `0x19b504` on address 0.
- **Negative control, sorted by the unstripped name** (case-folded, which is not
  the archive order): 1 pair is out of order and the search finds 15 of 16. The
  post action runs, and the first cut frame faults at `0x2168a0` on address 0,
  the same pc as the `dialog.bin` refusal above.

So the archive is in search order once fixup has stripped the prefixes and
removed the three records, and a copy in either other order fails the search.

The lump becomes resident entry 0, and `g_levelName` and
`0x44fe18` are set to its stem. `.world`, `.ob` and `.scr` are not loaded.

**Executed** ([lines 566–666](../tools/difftest_arrival_stage_r7.py#L566)).
The route-2 entries and post action run in the original code. The native order
is round 5's `ROUTE2_ORDER`. `cut_start` now reads the real cut header, which
lies inside the resident copy. The cut byte is 1, `g_warmupFrames` is 10 and
the clock `0x44fce0` is 1. The test then observes every native:

- **Three warm-up frames, `cut_runFrame(1)`, all return 0.** Frame 0 calls
  `cut_setup` once and stores 1 at `0x44fcd2` from `0x199bbc`. That is the
  only store to that byte from the first warm-up frame through the 1879th task
  frame. Round 8 keeps recording stores to that byte through the task frames. `cut_setup` leaves 12 actors at `0x83d188`. No frame
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
  route 1, and offline the front end replaces it with `intro`. The bits were
  executed at difficulties 1–5. "Route 2" is the story level at mission row 0
  `+8`. Row 0's evil alternative `+0x0c` is null, and the menu code that
  reads it is not executed.
- **Loader after the level load.** Start the 10-frame warm-up and run the
  deferred promote. Run ten passes of the six calls above while streaming is
  idle, counting down by one per pass. Then run the shop test by level name.
  Refuse at `loadscreen_stop`, which waits on a thread this path has not
  started. For `hub`, refuse at the shop's lump load.
- **`setState` with a clip.** Set `+0x17c` to 0 on entry. Push one entry when
  the stack has room, with mode 3 or 6 from bit `0x2`. Write all 32 bytes of the
  entry as listed above, and OR the mode into `+0x9e`, keeping its earlier
  bits (a second push ORs in a second mode). Then set `+0x17c` to clip `+4`
  + 1, for the current state's clip, at any state. Do not add it to an older value. With a slot-19 value of
  1, set `+0xc` bit 0. Refuse when `+0x11c` bit 0 needs the collision world.
- **Delete.** Remove the `name=` value from the name table, clear the three
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
- the level-name bytes `game_loadLevel` stores after the split. Round 6 listed
  the loader's level-name bytes; the split itself now runs.

## Round-8 fixes (audit `research-loading-readiness-r7`, 2026-11-09)

The new test is `tools/difftest_arrival_stage_r8.py`. Additions to
`tools/difftest_arrival_stage_r7.py` and `tools/difftest_arrival_stage_r6.py`
only add lines; no assert was removed.

- **R8-1.** `+0x17c` is zeroed at `0x23d6ac`, then set to itself + clip `+4` + 1
  at `0x23d764`. Run with three clip values, two planted values and a late-write
  control. The client text now says "set", not "add".
- **R8-2.** The entry over a `0x5a` sentinel, with every field credited to the
  store that writes it, including the `+4` link and the OR into `+0x9e`.
- **R8-3.** Fixup's removed indices, the order under `0x3b8534` before and after
  fixup, the binary search over every name, and two permuted negative controls,
  all as counts.
- **R8-4.** Every loader detail is asserted in all three runs: the `dbg_printf`
  formats and sites, one Deci2 call per `dbg_printf`, both stack checks and
  their returns, the reads of the net byte, camera word, cut byte, player count
  and player pointer, 20 timer reads, and `0x17fe88`'s v0. The `hub` runs repeat
  the full order, counter and timer checks. "Reads it twice" is replaced by the
  measured count.
- **R8-5.** Each planted register is checked against its setting instruction,
  listed above. s2 is poisoned and shown to be written before use. No byte of
  the unplanted caller frame is read.
- **R8-6.** The previous free-list head is read before the delete and matched.
- **R8-7.** The guard's base, compare value, length and fault store are checked
  by instruction field, with corrupted-byte controls at offsets 0, `0x13ff` and
  `0x1400`.
- **R8-8.** Difficulties 1–5, row 0 `+0x0c` null, and the story-route citation.
- **R8-9.** Disclosed under the Deci2 fixture above.
- **R8-10.** Branch history still holds four whole instruction words, which
  `c61629e` committed and `4487a88` replaced. The tip has none. This round does
  not rewrite history. Folding or squashing before merge is Malik's decision.
- **R8-11.** A pointer comment is added above the round-6 `pool_free` count
  assert. The assert is kept.
- **R8-12.** The setup-byte claim is now recorded through the task frames.
  `res_find`'s arguments, call site and v0 on the `dialog.bin` path are
  asserted. The no-stub and no-patch check is added to the producer, the props
  and the cut refusals.

Run: `PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_arrival_stage_r7.py local/SLUS_209.73 local/arrival-route-r4.json`
and `PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_arrival_stage_r8.py local/SLUS_209.73 local/arrival-route-r4.json`.
Result: bodies 0–11, seeds 7 and 20973, all stages PASS for both. Logs:
`local/arrival-stage-r7-r8.log` and `local/arrival-stage-r8.log` (untracked).

## Round-9 fixes (audit `research-loading-readiness-r7-fix`, 2026-11-09)

The new test is `tools/difftest_arrival_stage_r9.py`. It reuses the round-8
fixtures. `tools/difftest_arrival_stage_r8.py` gains one line (`assert evil ==
0` in `hub_name`), and the r8 links above after that line move down by one. No
assert was removed.

- **R9-1.** `+0x9e` was planted with low bits that overlap the mode: `0x105`,
  `0x1ff`, `0x106` and 0 for mode 6, and `0x104`, `0x103` and `0x1ff` for
  mode 3. Every result is the old halfword OR the mode, and add, replacing the
  low byte, and replacing the low 3 bits are each ruled out. The `lhu`/`or`/`sh`
  fields at `0x17086c`/`0x170874`/`0x17087c` are asserted. A second push ORs a
  second mode in. The operation is **OR**.
- **R9-2.** `hub_name` now asserts that row 0 `+0x0c` is 0.
- **R9-3.** `res_find` is called from `0x216894` and returns to `0x21689c`. The
  round-8 `site=` value is the return address.
- **R9-4.** The four static facts are asserted by field, with one correction.
  Four branches before `0x322e04` land past it, not one. The claim the s4
  value needs is asserted instead: every path into `0x322dd0`–`0x322e58` runs
  `0x322dcc`. Also asserted: the `0x60` frame (`0x32299c`, `0x3235a4`), the
  `bne v0` at `0x322f18` after `jal 0x17fe88`, and `0x23d744` as the return
  address of `jal 0x170bc8` at `0x23d73c`. The zero store is shown, by run
  order, to come before the push.
- **R9-5.** The `+1` is the immediate of `addiu v1, v1, 1` at `0x23d760`, and
  the whole sum `0x23d744`–`0x23d764` is checked by field. `setState` was run
  directly at states 0, 1, 2 and 5, with decoy clips in the other slots, and
  `+0x17c` is clip `+4` + 1 at every state.
- **R9-6.** The run script is tracked as `tools/run_arrival_stage_r9.sh`. It
  holds no private paths.
- **R8-10** is unchanged: this round does not rewrite history. It is Malik's
  decision.

Run: `PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_arrival_stage_r9.py local/SLUS_209.73 local/arrival-route-r4.json`,
or `sh tools/run_arrival_stage_r9.sh` for r9, r8, r7, r6, r5 and the unit tests
with headed logs. Result: bodies 0–11, seeds 7 and 20973, PASS. Log:
`local/arrival-stage-r9.log` (untracked).
