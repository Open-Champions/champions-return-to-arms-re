# Level-to-level travel, round four

Verified 2026-11-03 against the read-only US v2.00 executable, SHA-256
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
**Observed** is addressed original code. **Executed** means that body ran in
`tools/ee_emu.py` on constructed inputs against `tools/ref_exit_travel.py`.
**Inferred** composes those boundaries. **Unknown** was not run. This is not a
disc load, a Play! session, or removal of a client refusal.

## Act selection

**Observed / Executed:** `save_findAct` `0x217d30` searches the current act at
`0x88d3d4` before acts 0 through 12. Each act has a count at `0x4f8e10` and a
row list at `0x4f8e48`. A row matches when the requested name starts with the
row name (`0x3b91d8`). The first match wins, so `hub2` selects the `hub` row
and `storm1a` selects the earlier `storm1` row. An unknown name returns −1.
`save_actChanged` `0x217f70` calls that search, and calls `save_setAct`
`0x2180a8` only when the found act exists and differs. Ten cases:
`tools/difftest_exit_travel.py`.

Current act 6 and the name `hub` stay on act 6, because that act is searched
before act 0. From act −1 the same name selects act 0. From act 5, `honor`
selects act 6 and the act changes. `SYN_NO_LEVEL` leaves the stored act alone.

## Departure directory

**Observed / Executed:** `save_storeLevelState` `0x21777c` returns 0 on every
path below. It does nothing when the card word `0x88d3a0` is 4 or level flag
`0x44fe08` has bit `0x800` set. Otherwise the reserved size is 35000 when byte
`0x4f85c5` is set. A name starting with `hub` uses row 0 of the current act.
Any other name uses `save_levelIndexInAct` `0x2187a0`: the first current-act
row the name starts with, or no store when the current act is −1 or no row
matches. `storm1a` while the current act is 8 therefore reserves the `storm1`
size, not the later row of the same name.

The directory `0x8ab590` holds 0x18-byte entries, key then a size word at
+0x14. An existing key keeps its stored size. A new key is appended, including
as an 11th entry after ten keys. `save_writeLevelState` `0x218600` is called
at `0x8ab698` plus the sum of the sizes before that entry, and only when
`0x16118 + that sum + this size` is at most `0x4bc78`. The entry is still
created when the bytes will not fit. The writer body is supplied. Fifteen
cases compare the directory and the writer pointer. Actual object, decal and
explored-map bytes remain **Unknown**.

## Qualified name and the load consumer

**Observed / Executed:** `level_getQualifiedName` `0x1ec0f0` copies
`0x41b721`, or joins it to `0x41b771` with `_` when the subname is present.
Four direct cases use no stubs.

**Observed / Executed:** `mainloop_loadRequestedWorld` `0x320edc` then does
the following. Stack checks and presentation calls are supplied.

- A current level name of empty skips the departure save (`0x320f1c`).
  Otherwise a running `deathTask` (`0x19e5e8`) also skips it. The save receives
  the qualified current name from `0x1ec0f0` into `0x21777c`.
- A nonzero save result, supplied here and not produced by the original body
  above, clears the pending name at `0x320f5c` and returns before the act
  check. That branch also stores through the null task pointer at `0x320f54`.
  It is **Observed** in the caller and **Executed** only with a stub. It is
  not a retail failure while `0x21777c` returns 0.
- After a zero save result, both `0x4f713c` and `0x4f85c0` must be set before
  `0x1eb6f8` runs. The tests leave `0x4f85c0` clear, so that restore is not
  entered.
- `0x41b510` nonzero skips `save_actChanged`. The act index is otherwise
  updated even when the later clear block is skipped.
- The clear block runs only when the act changed, card latch `0x4f8f28` is
  clear, and no death task is running (`0x320fa8–0x321020`). It calls
  `save_clearBuffer(0)` `0x21f144`, `jumpgate_resetDestinations` `0x27db00`
  with the new act from `save_getAct` `0x217edc`, `quest_clearAll` `0x1d3adc`,
  and `player_removeFlag39Items` `0x1be1d8` for each slot below `0x4d8ae0`.
  It stores 1 at `0x4f7118` and runs original `vars_clearAll` `0x1ed728`,
  which keeps the variable name and zeroes its value. Those three world
  calls are supplied; their order and arguments are compared.
- `playerSel_applyPending` `0x2247ec` runs on the paths that pass the save
  branch, including a path that does not change acts. It does not run on the
  supplied nonzero-save return. Its body is supplied.
- The previous qualified name is written at `0x41b7c2` before the request is
  split. The request is split at the first `_` into `0x41b721` and `0x41b771`;
  a leading `_` leaves the base empty. The pending name is then cleared, and
  the base is copied to `0x44fe18`.
- The orientation byte at `0x41b720` is saved at `0x41b7c1` and replaced with
  `0xfe` (`0x321118–0x321128`). Supplied `0x216588` is entered with raw
  float argument `0x3d4ccccc`.
- Supplied `game_loadLevel` `0x1e55c0` receives the base name.

**Observed / Executed** placement, still inside `0x320edc`, with terrain,
free-spot search, allocation and the player constructor supplied:

- Recall flag `0x41b51c` copies only x and y from `0x41b520` over the spawn
  slots at `0x4f70d0`. The flag is cleared. Byte `0x41b51e` is cleared before
  the function leaves.
- Supplied terrain height `0x183820` overwrites spawn z for every slot.
- The free-spot search is skipped when `0x4f85b0` is clear, word `0x4f7120`
  is set, or rank byte `0x4f7108` is 3. Slot 0 is also skipped. Otherwise
  supplied `world_findFreeSpot` `0x14acf8` is entered with radius `0x24` and
  argument `0xe`, and the facing halfword at `0x4f8410 + 2*slot` increases by
  `0x1f40`, wrapping in 16 bits. Spawn z is then the terrain result again.
  What the original search reads from geometry or `g_randSeed` remains
  **Unknown**.
- A player object is allocated (`0x14fdb8`, size `0x590`) and constructed
  (`0x1a1d28`) only when hit points at record `0x4d8af0 + slot*0x4c30 + 0xac`
  are greater than 0, supplied peer test `0x13dd40` is true, and, when
  `0x4f713c` is set, original `0x1ec5a8` says this is the medal slot
  `0x4f7148`. The constructor receives the spawn position, the sign-extended
  facing halfword, and the slot. Its body is supplied.
- On an act change, bytes `None` are written at record +0x24 for every slot,
  including a slot with no hit points. Card state `0x217550` equal to 4, or a
  running death task, skips that write. The state function is supplied.
- Original `save_levelStateStored` `0x2182d4` looks up the new qualified name.
  A miss stores 300 at `0x506054`. A hit leaves the previous idle-voice value.
- A set word at `0x505b00` stores 20 at `0x506058` and clears the word.
  Word `0x4f7134` was left clear, so `0x328330` was not entered. That call
  remains **Unknown**.

## What the client can carry, and what it cannot

**Inferred:** a level change can carry the qualified name being left, the act
index (updated even when quests and the save buffer are kept), the base and
subname of the request, orientation `0xfe` plus the saved orientation byte,
the named entrance and post-action from round three, and the player-record
gates above. Clear the act-scoped lists only under the three conditions at
`0x320fa8`. Do not treat the loader's return register as a status.

**Unknown:** `game_loadLevel` itself, the loading screen, warm-up, shop stock,
blocking geometry, the original free-spot search and its seed use, player and
destination constructors, object bytes written by `0x218600`, derived-creature
departure, script bodies, vehicles, and menu states 0–4. No client refusal was
removed.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m tools.difftest_exit_travel --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 -m tools.difftest_exit_travel --seed 7
```

Each seed passes with zero failures. Entry calls are the probed functions
only; nested original callees are not added to that count. Counts and the
retained logs are in `work/cursor-report.md`.
