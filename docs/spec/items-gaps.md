# Item round, open points closed

US `SLUS_209.73` v2.00. This note follows `docs/script-items.md` (branch
`t3/research-items`, 49bc578) and closes the points its section 10 left open. Each topic
has its own model, difftest and tests. "Executed" means run in `tools/ee_emu.py` against
the model by one of the difftests below. Nothing here was seen on a running game.

| Topic | Section | Model / difftest / tests | Spec |
|---|---|---|---|
| writer of the load-limit bonus 0x4d8ae8 | 1 | `tools/ref_items_gaps.py`, `tools/difftest_items_gaps.py` (suite `bonus`) | here |
| the flag that guards launch record +0xf4 | 2 | the same, suites `lobby`, `menu`, `record`, `fill`, `receive` | here |
| `ItemProp_ctor2`'s draw, the ground drop, `givePlayerRandom` | 3 | `tools/ref_item_drops.py`, `tools/difftest_item_drops.py`, `tools/test_ref_item_drops.py` | `docs/spec/item-drops.md` |
| `hideMonster` / `showMonster`; generators and hide targets on the disc | 4 | `tools/ref_hide_monster.py`, `tools/difftest_hide_monster.py`, `tools/test_ref_hide_monster.py`, `tools/objects_census.py` | `docs/spec/hide-monster.md` |
| the 15 non-literal `generateMonster` class names | 5 | `tools/generator_names_census.py`, `tools/test_generator_names_census.py` | `docs/spec/generate-monster-names.md` |

## 1. The load-limit bonus word 0x4d8ae8 has no writer (Observed)

`player_recalcStats` adds 5000.0 (at 0x1b69f4) to the load limit when the word 0x4d8ae8
is non-zero (`docs/script-items.md` 2.3). The executable image holds 0. Every way the
executable could store to it was searched, and none was found:

| Search | Result |
|---|---|
| every loaded segment (`.text`, the `.data` segment, `.loadScreenSection`), every word whose opcode is a load, store or `addiu` and whose 16-bit immediate is 0x8ae8 (−0x7518) | 2 instructions. 0x1b69e0 (`lw`, base high half 0x4e: the reader). 0x1c9984 (`addiu` on high half 0x54: 0x538ae8, an unrelated address) |
| `ori` forms (`lui 0x4d; ori 0x8ae8`) | none in the disassembly |
| data words holding 0x4d8ae8, 0x4d8ae0 (`g_numPlayers`) or 0x4d8af0 (`g_players`) | none in any loaded segment |
| `tools/gxref.py` 0x4d8ae8 (lui + displacement tracked through `addiu`/`move`) | the read at 0x1b69e0. 4 "possible" hits in `mainloop_loadRequestedWorld` 0x3212bc–0x3213e8 are stale registers: they are the 12-byte copies of the 0x4f70d0 array |
| `tools/fieldxref.py 8 --static 4d8ae0 --blocks` and `e8 --static 4d8a00 --blocks` (data flow through every function, wide stores, constant-length block calls) | the read at 0x1b69e0 only |
| stores to the neighbours 0x4d8ae0 and 0x4d8ae4 | all are 32-bit `sw` or a `swl`/`swr` pair (`save_load` 0x221eb4/0x221eb8 on 0x4d8ae0). None is 64- or 128-bit, so none reaches 0x4d8ae8 |

The difftest's suite `bonus` repeats the segment and data-word scan on every run. What a
static search cannot see: an address built at run time from values that are not constants
in the code, and a block copy whose length is computed. Neither was found. A memory poke
from outside the program, such as a cheat device, would also not be seen.

**Consequence:** in the shipped executable the word stays 0, so the +5000 is never added.
The load limit is `min(float(+0x90 + 125) + 15 × passive 0x40, 9999)`. The native client
should keep the word as a constant 0. It can keep the branch for parity, but nothing
writes it.

## 2. The flag that guards launch record +0xf4 is the host bit (Executed)

### 2.1 State

The net settings block is at 0x402a30 (0x14c bytes, `docs/ui.md`). The launch records are
`g_launchRecs` 0x402b90, four records of 0x144 bytes.

| Address | Type | Use |
|---|---|---|
| 0x402a30 | u8 | flags. Bit 0 (1): host. Bit 1 (2) or bit 2 (4): the kind of character |
| 0x402a32, 0x402a33, 0x402a34, 0x402a35 | u8 | difficulty, mode, mission, kill limit |
| 0x402a37 | s8 | player count |
| 0x402a39 | s8 | this machine's player number |
| 0x402a3a | u8 | set to 0xff together with the kind bits (meaning unknown) |
| 0x50613c | ptr | the lobby context. Own number s8 at +0xc80; the room's difficulty, mode, kill limit and mission bytes at +0x13e, +0x140, +0x142, +0x144 |
| 0x4fdba9 | u8 | `& 3` non-zero gives kind bit 4, zero gives kind bit 2 |
| record +0xa0, +0xa1, +0xa2, +0xa3 | u8 | difficulty, mode, kill limit, mission |
| record +0xf4 | s32 | the host's `game_scanCm1Vars(1)` |
| 0x4f719c, 0x4f8408 | s32, u8 | `g_difficultyIdx`, kill limit |
| 0x4f711c, 0x4f7120, 0x4f7124 | s32 | `g_pvpModeA` (mode 2 or 3), `g_pvpModeB` (mode 1, 2 or 3), mode 3 |

### 2.2 Who sets bit 0

- **Lobby** (`lobby_task`, 0x3276a4–0x327728, suite `lobby`). The own number is copied from
  the lobby context to +9. When it is not below the count (signed), the count becomes own
  + 1. Then +0 is cleared on every path: the store sits in the branch's delay slot at
  0x3276d0. Only when the own number is 0 does it copy the room's difficulty, mode and
  kill limit to +2, +3 and +5, set +0 = 1 (the host bit), and set +4 = room mission + 1
  (8-bit). Then kind bit 2 or 4 is ORed in from 0x4fdba9.
- **Front-end menu** (`frontend_run`, 0x1e1b6c–0x1e1b90, suite `menu`). +2 = 1, +3 = 0,
  +0 = 0, then +0 = 1 when the menu routine's result (0x1a01d0, kept in s4) is non-zero.
  `docs/issues/native-rendezvous.md` places this in front-end states 1 and 6, net host or
  client. The kind bits are added at 0x1e0d2c–0x1e0d5c, where byte +0x0a is also set to
  0xff.

The host's player number is always 0 (`frontend_startNetGame` 0x1e21e0 writes 0 on both
branches, `docs/issues/native-rendezvous.md`). So bit 0 is set on exactly the machine that
is player 0.

### 2.3 The builder and the receiver

`net_launchPrepare` 0x134c60 (`net_launchTransfer` in older notes) keeps 0x400000 in `fp`:

1. The own record is 0x402b90 + s8(0x402a39) × 0x144 (0x1351d8–0x135208, suite `record`,
   all 256 own numbers).
2. With bit 0 set (0x1353f4–0x135430, suite `fill`): record +0xa0 = +2 (difficulty),
   +0xa1 = +3 (mode), +0xa2 = +5 (kill limit), +0xa3 = +4 (mission), then
   +0xf4 = `game_scanCm1Vars(1)`. The call is made only on this path. Without bit 0,
   nothing in +0xa0..+0xa3 or +0xf4 is written, and there is no call.

`net_launchUpdate` 0x135638, at the end of a launch (0x137464–0x137518, suite `receive`).
On every machine, record 0 is read, which is the host's because the host is player 0:

```
g_difficultyIdx 0x4f719c = s8(rec0 +0xa0)
kill limit 0x4f8408      = rec0 +0xa2
0x4f711c = 0x4f7120 = 0x4f7124 = 0
m = rec0 +0xa1 (u8)
if (m - 1) unsigned < 3:     0x4f7120 = 1          modes 1, 2, 3
if ((m - 2) & 0xff) < 2:     0x4f711c = 1          modes 2, 3
if s8(m) == 3:               0x4f7124 = 1
if 0x4f711c != 0:            game_set4f7110(rec0 +0xf4)
```

The two calls (`game_scanCm1Vars`, `game_set4f7110`) are stubs in this difftest. Their
bodies were executed in `difftest_script_items` suite `cm1`.

**Answer.** The guard is the host bit. Only the host fills +0xf4, and it does so with its
own profile scan. Only PvP mode A (mode byte 2 or 3) copies that value into 0x4f7110 on
every machine. In the other modes, each machine keeps the word that `frontend_start` gave
it (its own rescan), and only mode A reads that word (`docs/script-items.md` 6). No seed
draw. The per-machine part is the host's profile, and the launch makes it shared.

### 2.4 Runs

`python3 tools/difftest_items_gaps.py --cases 200`, seed 20973: 6 suites, 0 failed (fill:
101 of 200 cases with the host bit; receive: 47 cases with the call). With `--cases 100
--seed 7`: 6 suites, 0 failed. A model with the host bit moved to bit 1 and the mode-3
flag moved fails 4 suites. `python3 -m unittest tools/test_ref_items_gaps.py`: 11 tests.

## 3. `ItemProp_ctor2`, the ground drop and `givePlayerRandom` (Executed, summary)

Full contract: `docs/spec/item-drops.md`.

- All 7 call sites of `ItemProp_ctor2` 0x1590ec pass launch 0. A ground item then costs
  **one shared-seed draw** and **one draw from the prop's own generator**. The shared draw
  is made inside `GameObject_ctor` 0x14cb10 and seeds the own generator at +0x44. The own
  draw is the facing +0x38, in `Prop_ctorNamedLaunch` 0x153e54. `Prop_launch` makes no
  draw at launch 0. Suite `ctor`: 200 cases on seed 20973 and 100 on seed 7, 0 mismatches,
  one shared step each.
- The item record is copied to block +0x148 with 8-byte moves. Flags become
  `(flags | 0x102000) & ~0x1800`, and also `& ~0x3000` when item flag bit 39 is set. The
  vtable 0x511c38 goes at +0x48. No `PhProp_initPhysics`, no sound, nothing per machine.
- `givePlayerRandom` 0x145f18, per player: 1 shared draw for the budget, then 1 to 10
  tries of `item_generateWithAffixes`, each preceded by 1 shared draw (plus that
  generator's own draws), then a give or a ground item (+1 shared draw). When all 10
  tries fail, the record handed on is stale. Suite `random`: 40 cases on seed 20973 and 20
  on seed 7, 0 mismatches, faults agreeing. It has 0 calls on the disc.

## 4. `hideMonster` / `showMonster` and the generators on the disc (Executed, summary)

Full contract: `docs/spec/hide-monster.md`.

- Each command calls `world_findObjectsByName(name, buf, 0x200)` 0x14bf58, which ignores
  case. Then, for each object:
  - Hide: `obj_moveOffGrid` 0x14ef48 (to the front of the off-grid list 0x5f76f0), then
    +0x0c `|= 0x8000`.
  - Show: `obj_updateGridCell` 0x14f028 (to the front of its grid cell), then
    `&= ~0x8000`.
  - Only when +0x0c has 0x20 (set only by `Creature_ctor` 0x109d68): +0x231 bit 3 is set
    or cleared.
  - Returns 0. No seed draw. No other field.
- Runs: 200 cases on seed 20973 and 100 on seed 7, plus 27 fixed edge steps, 0
  mismatches.
- Disc (120 level lumps, 18,675 records, each class decided by running the original
  factory and constructor chain):
  - `ScriptGenerator`: 105 records in 11 levels. 133 of the 136 `generateMonster` calls
    find exactly one in their level.
  - `hideMonster`, 373 calls: 100 find only creatures, 262 only non-creatures, 6 both, 5
    no level-file object, and **0 an undecided class**.
  - `showMonster`, 52 calls: 22, 22, 3 and 5 in the same order, 0 undecided.
- So each of the native client's 119 `hideMonster` refusals can be decided from the class
  of the stub: is the class a creature or not.

## 5. The non-literal `generateMonster` arguments (summary)

Full contract: `docs/spec/generate-monster-names.md`.

- Of the 15 calls, 12 compute the class name and 3 compute the generator name. Every
  computed argument is a row of a constant, never-written string table, indexed through
  a `getRand` shuffle. Executed on the original script machine: 600 runs per seed, 0
  differences, with 4 and 7 shared draws per shuffle run.
- All 9 reachable computed names reach a non-`Skeleton` constructor.
- **2 of the 3 computed-generator calls pass a literal class that the factory builds
  with the `Skeleton` constructor.** So the rise (AI state 0x17) is reachable from
  shipped scripts. This corrects `docs/script-items.md` 7. One of the two picks its
  generator with `getRand() % 16` (1 shared draw).

## 6. What the native client should implement next

Ranked by what each item unblocks in the native sweep
(the items worktree's private report `work/loop-items-r1-report.md`: 119
`hideMonster` refusals and 7 `givePlayerItem` refusals), by lockstep risk, and by size.

| Rank | What | Unblocks | Needs | Spec |
|---|---|---|---|---|
| 1 | `hideMonster` / `showMonster` on stub objects: decide flag 0x20 from the class (creature or not), keep the off-grid list with front insertion, set or clear 0x8000, and +0x231 bit 3 for creatures only | the largest refusal count (119 hide, 14 show in the sweep). All 425 disc calls have a decided class | the class of each stub (its factory row), the grid lists | `hide-monster.md` |
| 2 | The ground item (`pool_new(0x190)` → `ItemProp_ctor2`): 1 shared draw seeding the prop's own generator, 1 own draw for the facing, the record at +0x148, the flags | the drop paths of `givePlayerItem` / `giveOnePlayerItem` and the inventory drop, which now refuse. It also keeps the shared seed in step when a reward does not fit | the prop's own generator, `GameObject_ctor`'s draw | `item-drops.md` |
| 3 | Run the `getRand` shuffles that fill the `generateMonster` index tables (4 and 7 shared draws per run) as ordinary bytecode, with no special case | the 12 computed-class and 3 computed-generator calls, and lockstep in those 2 scripts | a bound seed in the script session | `generate-monster-names.md` |
| 4 | Build the 105 `ScriptGenerator` records as 0x4c-byte objects (constructor 0x265f54) that keep their property list | `generateMonster` → `ScriptGenerator_spawn` in 11 levels | level records, the factory row | `hide-monster.md` |
| 5 | The `Skeleton` rise (AI state 0x17) after `ScriptGenerator_spawn` | the 2 shipped calls that can reach it | the Skeleton constructor and its state 0x17, which stay refused natively | `generate-monster-names.md`, `docs/script-items.md` 5.1 |
| 6 | The launch host bit: only the host (player 0) fills record +0xa0..+0xa3 and +0xf4. Every machine applies record 0, and copies +0xf4 into 0x4f7110 only in modes 2 and 3 | the arena mode-A level index in a net game | the launch records | section 2 |
| 7 | Treat 0x4d8ae8 as a constant 0: no +5000 on the load limit | nothing in play (the word is never written). It removes one refused writer | nothing | section 1 |
| – | `givePlayerRandom` | 0 disc calls: keep refusing it | the item generator | `item-drops.md` |

## 7. Runs (2026-10-21)

- `python3 tools/difftest_items_gaps.py --cases 200` and `--cases 100 --seed 7`: 6 suites
  each, 0 failed.
- `python3 tools/difftest_item_drops.py`: `ctor` 200 / 100 cases, `random` 40 / 20 cases
  (seeds 20973 / 7), 0 mismatches.
- `python3 tools/difftest_hide_monster.py --cases 200` and `--cases 100 --seed 7`: 2
  suites each, 0 failed.
- `python3 tools/generator_names_census.py --difftest --cases 300` on seeds 20973 and 7:
  pass.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'`: 741
  tests, OK.
- Disc outputs (counts only) are in the untracked `local/census/`.
