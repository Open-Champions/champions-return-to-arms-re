# Mission 2 round 6: the portal menu, and the loader to arrival

2026-11-09. Adds to round 5 at `abac4ee`
([mission2-round5.md](mission2-round5.md)). Earlier rounds' tests and
reference APIs are not edited. The round-6 audit fixes (R6-1..R6-10) are
folded in below, also dated 2026-11-09.

**STATUS: MORE.** Two results, both under the fixtures listed at the end:

- **Portal (track A).** The portal menu runs from opening to travel in the
  original code. That covers the input, the next-world write, the handoff
  through `mainloop_loadRequestedWorld`, and the destination-list save and
  load.
- **Loader (track B).** `game_loadLevel` runs past the VU1 store and returns.
  The loaded level's objects are built, and the player is constructed at the
  destination gate.

The fixture still supplies boot and `engine_init` state, a bump heap, and
several labelled hardware models. Section 7 lists what is left.

Labels:

- **Observed** means read from the executable's instructions, with
  addresses.
- **Executed** means the original functions ran in `tools/ee_emu.py` and
  [`tools/difftest_mission2_r6.py`](../tools/difftest_mission2_r6.py) asserts
  the result on seeds 20973 and 7.
- **Inferred** and **Unknown** are stated as such.

## 1. Emulator: reused handlers, three new opt-ins

Commit `b8356cc` takes `tools/ee_emu.py` and `tools/test_ee_emu.py` from
`t3/research-death-reload` `0ea7de1d`, death-reload's round-7 audit-fix
commit (R7-1..R7-6), by a three-way merge with base `543ea930`. Those fixes
sit on top of `cd6a07c`: GS named registers, the Status gate on INTC, and
FlushCache and EndOfHeap split out. Round 8 (`b1afa49`..`98ea7a6`) is not
taken. (An earlier version of this section, and the subject of `b8356cc`,
called `0ea7de1d` the round-8 tip. That label was wrong; the merged content
is as described here.) Only the module docstring conflicted, and both texts
are kept. The opt-ins reused unchanged are:

- `install_modelled_boot`
- `install_modelled_intc`
- `install_modelled_gs_privileged`
- `install_ram_mirrors`
- `install_modelled_main_ram`
- `install_modelled_dma_idle`
- `install_modelled_vpu_stat`
- `install_modelled_end_of_heap`

Their contracts are the ones in `docs/death-reload-sequence.md` on that
branch, and they are not restated here. The intc opt-in is installed with
`while_disabled=True`, as death-reload's own tests do, so every delivery
depends on that model.

**The SIF DMA id counter (audit fix R6-5).** Round 5's
`install_modelled_sif_dma` counts its ids in `_next_sif_dma_id`. Before the
audit fix it was named `_next_dma_id`, the same name death-reload `98ea7a6`
(`install_modelled_sif`, syscall 119 at return address `0x355acc`) uses for
its own ids and resets to 1 on install. Had a later merge taken `98ea7a6`,
both models would have shared one counter, and the ids 1..653 asserted here
would no longer hold with both installed. The rename removes that; a comment
at the counter says why.

This round adds three opt-ins. All are off by default.

**`install_vu1_data_memory`**
([ee_emu.py](../tools/ee_emu.py#L1083-L1114),
[test](../tools/test_ee_emu.py#L991-L1030)).

- **Observed:** every `lui` of `0x1100` or `0x1101` in `.text` was read
  (44 sites). Only two functions form addresses in VU1 data memory
  (`0x1100c000`–`0x1100ffff`), and both only store:
  - `light_writeVuConstants` `0x148728`: `0x14877c`–`0x1487b0` write
    `0x1100ffc0`–`0x1100ffdc`, and `0x1487c0` writes `0x1100ffac`.
  - `0x19be08`, an `engine_init` step at `0x19d6b0`: `0x19bed0`–`0x19bef8`
    write `0x1100ffb4`, `0x1100ffb8`, and `0x1100ff60`–`0x1100ff6c`.
- **Observed:** no `lui`-formed address in `.text` is loaded from. The other
  35 sites store `0x11000000` into a packet word: a VIF code carried by DMA,
  not an address. No `lui 0xb100` or `0x9100` alias was found. This static
  scan does not cover pointers read from data or bases computed at run time.
- **Executed:** the model records every load from the window in
  `vu1_reads`, and the test asserts that list is empty in every run that
  installs it: each step of the loader chain, the eight ablations, the
  innovat1 load and the portal-to-hub chain. So the executed paths make no
  load there. Paths not executed are not covered.
- **Observed:** microprograms are started by VIF codes inside packets, for
  example `0x14000017` formed at `0x194674`–`0x19467c`.
- So the EE writes constants for a later VU1 program. It does not kick a
  microprogram by touching this window.
- **Model:** the 16 KB are kept as plain storage, zero until stored. Each
  store is recorded in `vu1_writes` and each load in `vu1_reads`. No
  microprogram runs, and VIF unpacks, which also write this memory on
  hardware, are not modelled. Micro memory and VU0 stay unmapped.

**`install_modelled_dma_tag_address`**
([ee_emu.py](../tools/ee_emu.py#L1041-L1060),
[test](../tools/test_ee_emu.py#L941-L965)).

- It requires `install_modelled_dma_idle` and adds offset `0x30` of the same
  two channels.
- **Observed:** `sceDmaSend` reads that word at `0x350644`. When the word is
  not -1, it stores the packet address there (`bnel` `0x35064c`, delay slot
  `0x350650`).
- **Model:** storage that starts at 0. No tag is walked.

**`install_modelled_timer0_count(count)`**
([ee_emu.py](../tools/ee_emu.py#L1062-L1081),
[test](../tools/test_ee_emu.py#L967-L989)).

- **Observed:** `gfx_endFrame` reads `0x10000000` at `0x19dcd0` and stores 0
  to it at `0x19dcd8`. At `0x19dce0`–`0x19dcf4` it stores
  (count + `0x1314`) / `0x2626` at `0x83d2c8`.
- **Model:** loads return the caller's count, and stores are recorded. The
  tests pass `0x2626`, the divisor itself, which is one frame by the
  function's own arithmetic. That value is chosen, not measured.

The suite has 82 emulator tests: 78 after the merge, three for these
opt-ins, and one added by the audit fix for `vu1_reads`. Defaults are
unchanged: rounds 4 and 5 and the compose test give the same lines as
before, and the logs in section 9 show this.

## 2. Track A: the portal menu

### Observed: `jumpgate_menuRun` `0x27dd74`

**Dispatch.** The state is the byte at `0x8e3a3a`. Values below 8 index the
jump table at `0x547f60`, which holds `0x27ddbc`, `0x27de74`, `0x27dea4`,
`0x27e100`, `0x27e198`, `0x27e1a8`, `0x27e25c`, and `0x27e270`. The pad is
`g_pads[chooser]`, at `0x41bfd8 + 0x58 × chooser`, where the chooser byte is
at `0x8e3a3b`.

**State 0** (`0x27ddbc`): find the current level.

- It calls `level_getQualifiedName` `0x1ec0f0`, then clears the selection
  `0x8e3a38`, the previous selection `0x8e3a39`, and the float at
  `0x8e3a48`.
- It searches the list for the current level and stores its index at
  `0x8e3a40` (`0x27ddec`–`0x27de20`).
- It sets `0x41b4fc` and `0x41b500` to 1.
- With a fixed destination at `0x8e3c34`, it jumps to state 4.
- Offline, it pauses: `0x44fa80 = 1`, `0x41b4f4 = 1` (`0x27de68`, `0x27de70`).

**State 1** (`0x27de74`): fade in. It adds 8 to `0x8e3a3c` until the value
reaches `0x80`, then stores `0x7f`.

**State 2** (`0x27dea4`): input.

- In a net game, when the chooser is local and the pause menu is open, it
  calls `net_lockLocalInput(chooser, 4)` and returns.
- The pressed word at `+0xc` is ANDed with the cancel mask at `0x41bfb8`.
  A hit, or `net_isSlotActive(chooser)` false, plays the accept sound and
  goes to state 3 with travel still 0.
- Otherwise, if the selection is not the current level (`0x27dfa0`) and the
  word ANDs with the confirm mask at `0x41bfbc`, it stores travel
  `0x500ae8 = 1` (`0x27e00c`) and goes to state 3.
- The two masks are static data words, not instructions: `0x120` at
  `0x41bfb8` and `0x40` at `0x41bfbc` in the executable's data. The test
  presses only bit `0x20` (cancel) and bit `0x40` (confirm); bit `0x100` is
  not exercised.
- Otherwise, the word at `+0x10` ANDed with `0x101000` moves up when the
  selection is above 0 (`0x27e05c`). ANDed with `0x204000`, it moves down
  while the selection is below count − 1 (`0x27e0b8`).

**State 3** (`0x27e100`): fade out.

- It subtracts `0x10` from `0x8e3a3c` until the value goes negative, then
  clears the pause words.
- With travel set: `0x41b500 = 0x41b4fc = 1`, `pauseMenu_close` `0x18df90`,
  then state 4.
- Without travel: `net_lockLocalInput(chooser, 5)`, and `task_remove` of the
  run and draw tasks (`0x27e170`–`0x27e188`).

**State 4** (`0x27e198`): `jumpgate_beginTravel` `0x27e6a8`, which reads the
camera at `*0x4f8450`.

**State 5** (`0x27e1a8`): count, then write the next world.

- It counts travel up to 181 (`slti 0xb5` at `0x27e1b4`).
- It then copies the fixed destination, or `0x8e3a50 + 32 × selection`, to
  `g_pendingLevel` `0x41b6d0` (`0x27e1d0`, `0x27e1f8`).
- It stores `0xff` at the orientation byte `0x41b720` (`0x27e210`). Nothing
  else is written for the next world: the path `0x27e1c0`–`0x27e21c` calls
  only the copy and stores only `0x27e210` and the state byte.

**State 6** (`0x27e25c`): goes to state 7.

**State 7** (`0x27e270`): `0x41b4fc = 10`, `0x41b500 = 0`, travel 0,
`0x4f66a8 = 0`, then removes both tasks (`0x27e298`, `0x27e2a4`).

So the gate writes only the name and orientation `0xff`. The entrance comes
from the destination's own gate (section 4). The executed check of that
"only" is under **Travel** below.

### Executed

The menu is opened by round 5's portal use, with the travel word sentinel
and these synthetic inputs:

- seeded prior destinations named `zm…`;
- `g_levelName = innovat1`;
- the camera from section 5.

The real `task_add` registers the menu tasks. The tests then call the run
task once per frame and write the pad word before each call. The draw task
is not run. See [menu_open](../tools/difftest_mission2_r6.py#L419-L443),
[frame](../tools/difftest_mission2_r6.py#L446-L453), and
[menu_select](../tools/difftest_mission2_r6.py#L466-L542).

**Opening and fade-in:**

- The prompt appends the current level, giving 6 entries (seed 20973) or 7
  (seed 7).
- State 0 stores the current index (the last entry) and sets both pause
  words.
- Fade-in takes 16 frames.

**Selection.** A seeded sequence of up and down presses (8 or 5) ends at the
index an independent model predicts
([model_select](../tools/difftest_mission2_r6.py#L456-L463)).

- Seed 20973 lands on the current level. Confirm is refused there, and
  travel stays 0. One more up press, then confirm.
- Seed 7 confirms index 5 directly.

**Travel:**

- Confirm stores travel 1.
- Fade-out takes 8 frames, ends in `pauseMenu_close`, and clears both pause
  words.
- State 4 calls `jumpgate_beginTravel`.
- State 5 runs 181 frames. Travel ends at 181, and `0x41b6d0` holds the
  selected synthetic name.
- The orientation byte goes from sentinel `0x5a` to `0xff`.
- Writes over `0x41b6d0`..`0x41b7e2` (`g_pendingLevel` through
  `g_prevLevelName`) are recorded in every state-5 frame. The first 180
  frames write nothing there. The last frame writes only the name's bytes
  and its terminator, all inside the copy called from `0x27e1f8` (between
  its entry and its return to `0x27e200`), then one byte `0xff` at
  `0x41b720` from `0x27e210`.
- State 6 → 7 keeps travel at 181. State 7 clears travel and calls
  `task_remove(0x27dd74)` and `task_remove(0x27e2d0)` from `0x27e298` and
  `0x27e2a4` ([lines 537–541](../tools/difftest_mission2_r6.py#L537-L541)).

**Cancel:**

- Cancel goes to state 3 with travel 0.
- After 8 fade frames, the code calls `net_lockLocalInput(0, 5)` and removes
  both tasks.
- The pending name holds a nonzero 32-byte sentinel from before the first
  frame. It and the orientation sentinel are unchanged, and writes over
  `0x41b6d0`..`0x41b7e2` are recorded in every frame from the opening to the
  last fade frame: there are none
  ([menu_cancel](../tools/difftest_mission2_r6.py#L545-L568)).

### Saving and loading the destination list

**Observed:**

- `jumpgate_saveDestinations` `0x27dcf4` stores the sign-extended count
  byte as a word. It copies the 480 bytes at `0x8e3a50` after it and returns
  `0x1e4`.
- `jumpgate_loadDestinations` `0x27dd30` stores the word's low byte at
  `0x8e3c30` and copies the 480 bytes back. It also returns `0x1e4`.
- The save writer calls `0x27dcf4` at `0x221a60`. The buffer pointer is the
  header end `+0x70` plus the size the camera section returned
  (`0x203918`, `0x221a54`).
- `save_load` calls `0x27dd30` at `0x221e80`.
- `0x27dcd8` saves into a stack buffer and discards it.

This matches the `+0x134` row of `docs/audio-save.md` line 70 on
`t3/research-save-world` `31a0ca6`. It also matches the save/restore
comparisons in `docs/exits-r3-gate-lifecycle.md` on `t3/research-exits-r3`
`e86f3de`. `docs/audio-save.md` line 141 says `save_load` then sets
`0x41b720 = 0xfd`. That is a different orientation code from the gate's
`0xff`.

**Executed** on the list the real discovery built (6 or 7 entries):

- The save returns `0x1e4`. Its count word equals the list's count, and its
  480 bytes equal the list.
- Fill bytes after the block are untouched.
- The list and count are then overwritten. The load returns `0x1e4` and
  restores both exactly
  ([destinations_round_trip](../tools/difftest_mission2_r6.py#L571-L584)).

The memory card, the checksums, and the rest of the save builder are not
run.

## 3. The handoff to the loader

**Inferred** from `docs/mainloop.md` section 7 (this branch), which says the
main loop acts on `g_pendingLevel` at the top of the next pass: the request
written in state 5 is taken while the menu is in state 6 and travel is still
181. This order was not read from instructions here, and the test runs it in
that order by construction.

**Observed:** `game_clearLevel` calls `0x27dac8` at `0x1e50d0`. Exits round 3
executed that function: it removes both gate tasks only when travel is 0.
So the menu tasks survive a gate load.

**Executed** ([arrival_chain](../tools/difftest_mission2_r6.py#L589-L665)):
the chain lists `hub` before the current `innovat1` and confirms index 0.
After state 5, the original `mainloop_loadRequestedWorld` `0x320edc` runs
and returns 0. The test asserts:

- `save_storeLevelState` `0x21777c` gets `innovat1`.
- `game_loadLevel` `0x1e55c0` gets `hub` from `0x321148` (return address
  `0x321150`).
- `g_levelName` is `hub`, the subname is empty, `g_prevLevelName`
  `0x41b7c2` is `innovat1`, and the pending name is empty.
- `0x41b7c1` is `0xff` and `0x41b720` is `0xfe`.
- Sentinels are planted before the request: `0x5a` at `0x41b7c1` and at
  `0x4f7108`, and a synthetic name at `0x41b7c2`. Writes to those bytes, to
  the subname's first byte `0x41b771` and to `0x41b720` are recorded, and
  the stores are asserted by pc: the string copy at `0x3b8784` writes
  `g_prevLevelName`, `0x3210e4` clears the subname, `0x32112c` stores
  `0xfe`, and `0x321138` stores the saved `0xff`.
- The subname gets no sentinel. `save_storeLevelState` receives the
  qualified name, which joins the subname, so a sentinel there changed the
  stored name in a trial run. Its clearing store is shown by the write
  record instead.

These agree with `mainloop_loadRequestedWorld` as `docs/exits-r4-travel.md`
lines 47–127 at `t3/research-exits-r3` `e86f3de` describe it (the file
changed after that commit). There, `game_loadLevel`
and the placement callees were supplied. Here they are original code.

After the return, the menu is still in state 6 with travel 181. One run
frame moves it to state 7 with travel 181. The next frame clears travel.

## 4. Arrival: objects and player placement

**Observed:** `JumpGate_ctor` places the arriving players. At `0x27c974` it
reads travel, and at `0x27c984` the fixed destination. With travel set and
no fixed destination, it does the following for each player counted at
`0x4d8ae0`:

1. `world_findFreeSpot` `0x14acf8` near the gate (radius `0x24`, `0x27c9d8`).
2. Store the spot at `0x4f70d0 + 12 × slot` (`0x27ca44`, `0x27ca50`,
   `0x27ca5c`).
3. Step `g_randSeed` `0x404464` (multiplier `0x19660d`, increment
   `0x3c6ef35f`).
4. Store the seed's high half as the facing halfword at
   `0x4f8410 + 2 × slot` (`0x27ca70`).

At the end, `0x27ca84` stores 3 at `0x4f7108`. Exits round 4 found that
byte skips the loader's own free-spot search. With travel 0 none of this
runs, and the spawn slots keep earlier values.

**Executed, both seeds:**

- `world_loadRecords` `0x14e808`, called from `0x217b94`, sends all 24 hub
  records through `g_objectFactory` `0x159c94` (`jalr` at `0x14e9a0`).
- The hub's `JumpGate_ctor` runs once and sees travel 181.
- The spawn slot's writes come from `0x27ca44`, `0x27ca50`, `0x27ca5c`,
  then the terrain height at `0x321234`.
- The facing write comes from `0x27ca70` alone, and `0x4f7108` is 3. From
  its `0x5a` sentinel, the byte is written twice: 0 at `0x217ab0` during the
  load, then 3 at `0x27ca84`.
- `Player_ctor` `0x1a1d28` is called once and returns. It receives slot 0,
  the spawn slot's 12 bytes as its position, and the sign-extended facing
  halfword ([lines 646–658](../tools/difftest_mission2_r6.py#L646-L658)).

| Seed | Spawn position | Heading |
|---|---|---|
| 20973 | (−205.62, 124.46, −49.00) | `0xffffeaf9` |
| 7 | (−272.56, 128.37, −49.00) | `0x000078b2` |

**Inferred:** the position differs by seed because the free-spot search and
the facing draw use `g_randSeed`.

**Executed (the round-5 loader target, innovat1):** `game_loadLevel` returns
`0x4f0000`. Exactly three scripts run, asserted in order: `preStart`,
`start`, then a third with another name. **Inferred:** the third is the
level's post-action script (its name is level data and is not committed).
`world_loadRecords` builds 297 objects through the factory, asserted.
`Player_ctor` is not called, because placement belongs to the caller
([arrival_load](../tools/difftest_mission2_r6.py#L393-L414)).

## 5. Track B: each stop past `0x14877c`

[loader_snapshot](../tools/difftest_mission2_r6.py#L262-L284) runs
`game_loadLevel("innovat1")` to the entry of `light_writeVuConstants`, with
everything in section 6 supplied. At that point it asserts round 5's counts:

- 653 modelled SIF DMAs with ids 1..653, the first at `0x875c00` with size
  `0x10`;
- 23 one-file disc reads;
- a call from `gfx_beginFrame` (return address `0x19d8dc`).

The run is copied there.

[loader_chain](../tools/difftest_mission2_r6.py#L317-L345) then installs the
hardware models one more at a time, in the order of
[HARDWARE](../tools/difftest_mission2_r6.py#L231-L243). It asserts each stop
in [HARDWARE_STOPS](../tools/difftest_mission2_r6.py#L288-L301):

| # | Added | Next stop (Executed) | What it is (Observed) |
|---|---|---|---|
| 0 | none | 4-byte write `0x1100ffcc`, pc `0x14877c` | round 5's stop: VU1 data memory |
| 1 | VU1 data memory | 8-byte write `0x3083fad8`, pc `0x19c8a4` | uncached-accelerated alias of main RAM, in `0x19c86c` from `gfx_beginFrame` `0x19d8e4` |
| 2 | RAM mirrors | read `0x1000a000`, pc `0x3501ac` | GIF channel control word, in the DMA wait `0x350190` from `sceDmaSend` |
| 3 | DMA idle | read `0x1000a030`, pc `0x350644` | the tag-address word |
| 4 | tag address | unimplemented CFC2 at `0x34ff5c` | VPU_STAT in `sceGsSyncPath` |
| 5 | VPU stat | WaitSema id 2, count 0, at `0x352a24` | the vsync semaphore; nothing signals it without an interrupt |
| 6 | INTC delivery | 8-byte write `0x12000000`, pc `0x19b6fc` | the vsync handler's PMODE store |
| 7 | GS registers | read `0x10000000`, pc `0x19dcd0` | timer 0 in `gfx_endFrame` |
| 8 | timer 0 | read address 2, pc `0x15086c` | `mem_largestFree` walking the real heap list `0x6dffc8`, empty under the bump allocator |
| 9 | heap diagnostics | test heap exhausted | `world_prepare` asks for a segment cache at `0x1825b4`: the size is the run-time segment count from `0x60(fp)` shifted left by 17 (`0x1825b8`), and the test asserts the one call from that site is `mem_allocTagged(0x760000)`. The bump heap at `0x1000000` is full |
| 10 | heap at `0x4000000` | EndOfHeap (62) at `0x3529c4` | the `sbrk` caller `0x353138`; **Inferred:** libc `malloc` growing its arena |
| 11 | EndOfHeap and main RAM | returns `0x4f0000` | |

The nine VU1 stores in step 1 all come from `0x14877c`–`0x1487c0`. All nine
addresses, `0x1100ffac` included, are asserted to read back what was stored.
(Before the audit fix `0x1100ffac`, the single store at `0x1487c0`, was left
out of that check for no reason.) In every step `vu1_reads` is asserted empty
([lines 337–344](../tools/difftest_mission2_r6.py#L337-L344)).

On steps 8 and 9 (**Observed**): `world_prepare` passes `mem_largestFree`'s
result only to a print (`0x18256c`–`0x18259c`). It then always calls
`mem_dumpHeap` `0x150290` at `0x1825a0`. The segment count comes from
earlier arithmetic, not from the free size. Both functions only read the
real heap's block list, which bump blocks do not have, so both are stubbed
to return 0.

## 6. What boot and `engine_init` would have supplied

Death-reload's `engine_init` stops at the SIF IOP wait (`0x35574c`), before
`0x19d6a8`. [supply_engine_state](../tools/difftest_mission2_r6.py#L188-L207)
makes the same stores with the original callees. In
[ablations](../tools/difftest_mission2_r6.py#L348-L390), each stored word is
removed again from a copy of the full fixture at the snapshot.

| Supplied | How the fixture makes it | Stop when removed (Executed) |
|---|---|---|
| static constructors | the 124 entries after the -1 at `0x3e9980`, last first, as runner `0x3ad250` does (`0x3ad2d0`–`0x3ad2ec`); [run_constructors](../tools/difftest_mission2_r6.py#L142-L152) | not ablated in the loader. [armor_probe](../tools/difftest_mission2_r6.py#L668-L685) runs `player_recalcArmor` `0x1b5790` on the round-5 player: without them it calls skill 63's `0x308a7c` with the skill at `0x6e2e08`, whose vtable word is 0, and faults reading `0x70` at `0x308a98`; with them it returns. Both asserted |
| GIF channel `0x8400d0` | `sceDmaGetChan(2)` = `0x1000a000`, the call and store at `0x19bd84`/`0x19bd94` | read address 0 at `0x3501ac`, in the DMA wait called from `sceDmaSend` at `0x350638` (return address `0x350640`) |
| gfx semaphore `0x6e4060` | CreateSema with max `0x186a0` and count 0, as `0x16c66c`–`0x16c69c` | SignalSema id 0 at `0x352a04`, called at `0x16c454` (return address `0x16c45c`) |
| texture cache | `texcache_setRange(0x359000, 0xa7000)`, the `engine_init` call at `0x19d6f8` (`0x83d298` = `0x359000` from `0x19d31c`/`0x19d338`); ring word `0x7cfe00` | 2-byte write `0x18` at `0x179b30`, round 4's and death-reload's `texcache_reset` stop, called at `0x17fb04` (return address `0x17fb0c`) |
| vsync semaphores `0x8400f0`, `0x8400f4` | two CreateSema calls with max `0x7ffffc17` and count 0, as `0x19d2a4`–`0x19d2d0` | both words removed: PollSema id 0 at `0x352a34`, called at `0x19db84` (return address `0x19db8c`) |
| INTC handler | `AddIntcHandler(2, 0x19b6e4, 0)`, stored at `0x44fd4c`, then `0x353528(2)`; the `engine_init` calls at `0x19d37c`/`0x19d38c` | not ablated |
| camera `0x4f8450` | `Camera_init(0x86ad68)` and the pointer store: `game_initCamera`'s own steps at `0x1e6b8c`/`0x1e6bb0`. Its skill and button-mask steps are not run | 4-byte write `0x34` at `0x207304` (`Camera_setMode`); return address `0x19b5b8`, the call from `cut_start` at `0x19b5b0` |
| `g_levelName` `0x41b721` | written as `0x320edc`'s split does; round 5's loader case left it empty | `cutScene` `0x143f1c` is called, formats `"%s.lmp"` and asks `res_find` for it from `0x143f7c`; `lump_load` gets `.lmp` from `0x173718`; then the miss print at `0x173634` and the write to 0 at `0x17363c`. All asserted. **Inferred:** this `cutScene` is the post-action script's |
| object factory `0x5f76f4` | `objects_registerFactory` `0x15da54`, the boot call at `0x323ecc` | load returns with no factory call (`0x14e998` skips) |
| libc semaphores `0x5075d0`, `0x5075d4` | `0x35c050`, the startup call at `0x35c2a8` | both words removed: WaitSema id 0 at `0x352a24`, called at `0x3b61c8` (return address `0x3b61d0`); **Inferred:** that call is `malloc`'s lock |

Every return address in the last column is asserted
([EXPECT](../tools/difftest_mission2_r6.py#L65-L86)). Before the audit fix, the vsync
and libc rows removed only the first word of each pair; both words are now
removed, and the stops are the same.

**Inferred:** each row is an `engine_init` or boot product that a retail
load finds already made. That is why every removal turns into a stop.
Whether retail values equal these is **Unknown** for the semaphore and
handler ids, which are modelled. The others are the stores the original
code makes.

## 7. Remaining stops to a playable arrival

**Executed so far:** `mainloop_loadRequestedWorld` returns with the hub's
objects built and player 0 constructed at the gate. In `docs/mainloop.md`
section 7, that function is step 6.

**Not run before step 6.** The test calls `0x320edc` directly, so the
steps of the same pass before it do not run:

- Step 2: `g_simFrame = 0`.
- Step 4: `g_ambientCountdown = 60`.
- Step 5: display blanking and `Camera_reset`. In their place the fixture
  supplies the camera through `Camera_init` (section 6).
- Steps 1, 3 and 9 are net-game steps and are not reached offline.

**Not run after step 6, with the first address of each:**

1. Step 7: `mainloop_startWarmup`, then `script_runDeferred` at `0x322e6c`.
2. Step 8: the warm-up loop at `0x322eb0`–`0x322fd0`. Each pass runs
   `game_rebuildAlivePlayers`, `Camera_update`, `drawWorld`,
   `lump_pollAsync`, and terrain streaming.
3. Step 10: shop stock for `hub`, `shop_openOrStock` at `0x3230c4`.
4. Step 11: `loadscreen_stop` `0x3224d8`, then the particle reset and blank
   frames.

**Fixture substitutions still in the path:**

- `game_clearLevel` `0x1e4e88` is stubbed. Run for real, it calls the
  particle reset `0x18ebb8` at `0x1e5024`, which death-reload found faults
  at `0x18ec10` without `particle_init` `0x18e648`. `particle_init` is
  `engine_init`'s call at `0x19d818`, after the SIF stop.
- The heap is the bump allocator: `mem_allocTagged`, `mem_realloc`, and
  `mem_free` are stubbed. `engine_init`'s heap (`mem_malloc` plus
  `mem_initHeap`, `0x19d58c`–`0x19d5c8`) is not built, so the two heap
  diagnostics are stubbed.
- The load-screen thread is created and started under the modelled boot,
  but StartThread does not enter it. No frame advances while loading.
- VU1 microprograms, VIF and GIF transfers, and the GS are not modelled. No
  pixel is claimed.
- The rest of `engine_init` after the SIF stop is not run: `0x19be08`
  (microcode upload and VU1 constants), `0x16c4b8` (DMA handlers),
  `0x166ef8`, `0x17f9f8`, `0x14fcd8`, and `0x1a17d0`. Of the boot function
  `0x323dcc`, only the calls named in section 6 are made.

**Unknown:**

- The retail heap layout.
- The IOP side of SIF.
- Retail semaphore and thread ids.
- Retail timer counts.
- What the skipped inits change for a later frame.

## 8. Fixtures and the claims that depend on them

- **Disc reads (fixture).** Round 5's `cd_readBlocking` stub reads one disc
  file by name. Its `cd_findFile` table holds real names and sizes with
  synthetic sectors `0x1000 + index`. Every disc read here, including
  `hub.gob`, depends on that table.
- **Sector numbers (executed oracle, audit fix R6-9).** Every round-6 run is
  repeated with a second synthetic numbering, `0x7f000 − 3 × index`
  (another base, descending, three apart), and the results are compared
  whole: the menu values, all 653 SIF DMA descriptors and the disc reads at
  the snapshot, the twelve stops, the eight ablation stops and their return
  addresses, the innovat1 objects and scripts, the hub arrival (objects,
  reads, spawn, heading) and the constructor probe. They are equal on both
  seeds. Every `cd_findFile` call is recorded by its call site, and the
  sites are asserted; see section 9 for the list. So no asserted result
  depends on which sector number a file has. That does not say what a
  retail sector would change in code these runs do not reach.
- **Heap (fixture).** The bump allocator, first at `0x1000000`. Before
  `mainloop_loadRequestedWorld` and from loader step 10 on, it continues at
  `0x4000000`–`0x8000000`, above the 32 MB of main RAM. Those addresses are
  fixture addresses. The mirror model refuses them, and no step needed one.
- **Stubs (fixture):** `cd_readBlocking`, `mem_allocTagged`, `mem_realloc`,
  `mem_free`, `FlushCache`, `dbg_checkStack` (round 5), `game_clearLevel`,
  `mem_largestFree`, and `mem_dumpHeap`, all listed in
  [FIXTURE_STUBS](../tools/difftest_mission2_r6.py#L104).
- **Models (opt-in, labelled):**
  - from death-reload: the boot, INTC, GS, mirror, main-RAM, DMA-idle,
    VPU-stat, and EndOfHeap models;
  - from round 5: the SIF DMA model;
  - this round: VU1 data, tag address, and timer 0
    ([OPT_INS](../tools/difftest_mission2_r6.py#L98-L103)).
  - The timer count `0x2626` is chosen. Every INTC delivery runs with
    Status 0 under `while_disabled=True`.
- **Supplied state (fixture):** section 6. The constructors run once at
  boot. Everything else is made before the load starts.
- **Inputs (synthetic):** destination names in track A, the pad words, the
  round-5 player (slot 0, null `r11`), and `g_randSeed` set to the seed.
  The chain loads `hub` by its level name. No disc text key is used, and
  success output prints counts and addresses only.

## 9. Reproduction

On the Mac mini, from this worktree:

```sh
sh local/r6fix-final.sh
```

That is round 6's `local/r6-final.sh` with the audit-fix log names
`local/mission2-r6fix-*.log`. The script writes each log's first lines
first: HEAD, the UTC time, the sha256 of `tools/ee_emu.py`,
`tools/test_ee_emu.py`, `tools/difftest_mission2_r6.py`,
`tools/difftest_mission2_r5.py`, `tools/difftest_mission2_r4.py` and
`tools/difftest_mission2_compose.py`, and whether `tools` and `docs` are
clean. It then runs, for seeds 20973 and 7 and with unittest preloaded so
`tools/dis.py` does not shadow the standard library:

```sh
python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); s=sys.argv[1]; sys.argv=[s]+sys.argv[2:]; runpy.run_path(s,run_name="__main__")' tools/difftest_mission2_r6.py local/SLUS_209.73 "$D" --seed <seed>
```

It also runs the round-5, round-4, and compose difftests and the unittest
suite. `D` is the mini's read-only disc directory.

Round 6 runs everything twice, once per sector numbering (section 8), and
takes about 14 minutes per seed. It prints nine PASS lines, then the
supplied, opt-in, and stub lists. The last PASS line gives the sector
comparison and the `cd_findFile` call sites: `0x1001d4`, `0x173584`,
`0x1a26dc`, `0x1a2780` and `0x321f28`. The sound code's `0x211454` is not
reached in these runs.

The compose test's last line, `LIMIT … arrival, and destination-list
save/load remain open`, is round 3's unedited text
(`tools/difftest_mission2_compose.py`, which later rounds do not edit). It
is stale: arrival and the destination-list save and load are now covered by
this round, sections 2–4.
