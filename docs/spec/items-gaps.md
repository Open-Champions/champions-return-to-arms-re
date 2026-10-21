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
