# Arena player replacement: constructor, placement, start and shutdown

US `SLUS_209.73` v2.00. **Executed** in `tools/ee_emu.py` by
`tools/difftest_arena_player.py` against `tools/ref_arena_player.py`, seeds 20973
and 7, no mismatches. The owner's disc executable is read only at run time from the
ignored `local/` folder. These are constructed states with fixed service answers,
not a live match. Model-only checks: `tools/test_ref_arena_player.py`.

| Section | What runs for real | Cases per seed |
|---|---|---:|
| 1 bounded constructor | `Player_ctor` `0x1a1d28`; base constructor stubbed | 1 (319 bytes, 16 calls) |
| 2 whole chain | `Player_ctor`, `Creature_ctor` `0x109d68`, `GameObject_ctor` `0x14cb10` | 4 (980 bytes, 144 calls, 1 draw each) |
| 3 destructor | Player slot 1 `0x1a1bb8` | 12 |
| 4 spawn protection | `Player_startSpawnProtection` `0x1b8f28` | 32 |
| 5 countdown reset | `game_resetTimers4f84a8` `0x1ec2b8` | 1 |
| 6 wave replacement | `arena_startWave` `0x305ed4`, `arena_pickSpawnPoint` `0x3050a4`, sections 2, 3, 5 | 1 |
| 7 respawn composition | `player_respawn` `0x1bd040` with sections 2, 3, 4 | 2 |

## 1. Constructor chain and seed draws

`arena_startWave` calls `Player_ctor(block, position, facing, slot, 0)` at `0x30604c`.
The constructor calls `Creature_ctor(block, 0, position copy, facing, 0x4ecc58, 0; 13.0)`
first: type name 0, the Player class definition `0x4ecc58`, no property list, and
placeholder hit points `0x41500000` (13.0). `Creature_ctor` calls
`GameObject_ctor(block, position copy, 0x4ecc58, 0)`.

Shared-seed draws in the whole chain: **exactly one**, in `GameObject_ctor`
(`docs/spec/object-system.md` §2.2). The new seed's top 16 bits go to +0x44.
With type name 0, `Creature_ctor` skips `Creature_setStats`, so it makes no own
draw (`docs/spec/arena-monsters.md` §2.1, step 6). `Player_ctor`'s own instructions
make no draw.

Order of the calls the chain makes (section 2 compares targets and key arguments):

1. `GameObject_ctor`: when the definition's generation word +4 differs from
   `0x41bf78`, `res_find(def+0, name)` once per name entry from +8 in steps of 8
   (111 entries for this definition). Each answer goes to the entry's +4 cell, and
   the generation is copied afterwards. Then `handle_link(cell, block+8, block)`
   `0x1a1738`, where the cell is the 120 × 120 grid head from the truncated
   position, or `0x5f76f0` off the grid. Then `obj_getPropInt(block, "hide")`
   `0x14c880`.
2. `Creature_ctor`: 14 property queries in the documented order (`wait`, `hide`,
   `ShowName`, `Dead`, `HomeRange`, `pointblankrange`, `visualrange`, `visualarc`,
   `Scale`, `MiniBoss`, `IgnoreDamage`, `light1`, `light2`, `ambient`). The three
   string queries use `0x14f4c0`.
3. `Player_ctor`'s own 15 calls: `0x148af8`, `0x14a4f0`, `sprintf`, `res_find`,
   `sprintf`, `res_find`, `0x355490`, `0x1707b0`, `0x1b2470`, `obj_runEveryFrame`
   `0x14f248`, `0x183820`, `player_recalcStats` `0x1b6458`, `0x3b60c0` twice, then
   `game_rebuildAlivePlayers` `0x1e72f8`.

## 2. Fields

Offsets are from the 0x590-byte block. Values are final after the whole chain;
widths and every value are in `chain_writes` / `constructor_fields`.

| Fields | Value | Writer, address |
|---|---|---|
| +0, +4, +8, +0x34, +0x2c | 0 | `GameObject_ctor` |
| +0x10, +0x14 | spawn x, y | `GameObject_ctor` |
| +0x18 | 0.75 (`0x3f400000`) | `Player_ctor` `0x1a245c`, over the spawn z |
| +0x1c, +0x20 | 12.0, 72.0 | `Player_ctor` `0x1a2244` over `GameObject`'s 24.0; height from `GameObject_ctor` |
| +0x24 | `0x4ecc58` | `GameObject_ctor` |
| +0x28, +0x29 | `0x30`, `0x49` | `Player_ctor` first byte of its name buffer, `GameObject_ctor` |
| +0x44 | 16-bit draw | `GameObject_ctor` (the one shared draw) |
| +0x48 | `0x511308` | `GameObject` → `Creature` `0x50cc58` → `Player` `0x1a1dc8` |
| +0x4c, +0x50, +0x119 | `0x50d010`, 0, 8 | `Creature_ctor` |
| +0xc | `0x4060` | `Creature_ctor` sets 0x20; `Player_ctor` `0x1a21f8` ORs in 0x4040 |
| +0x38, +0x2fa | facing | `Creature_ctor` |
| +0x3b4…+0x3bc, +0x3c | home = spawn; drawn height = spawn z | `Creature_ctor` (`sdl`/`sdr` pair at `0x109e44/0x109e48`) |
| +0x228, +0x22c | 13.0 | `Creature_ctor` (record HP is separate, `docs/player.md`) |
| +0x220 | all ones (8 bytes) | `Creature_ctor` |
| +0x230 | serial = `0x4f85c4` byte, which is then incremented | `Creature_ctor` |
| +0x3ac, +0x3ae, +0x3b0, +0x3c0, +0x3c4 | 300, 500, 0x4000, 1000.0, 600 | `Creature_ctor` defaults |
| +0x3c8 | slot | `Player_ctor` `0x1a2200` |
| +0x4b2 | `3600 + 2700 × slot` | `Player_ctor` `0x1a22ec`; matches `docs/spec/player-tick.md` §1 with draw 0 |
| +0x4f8, +0x4fc, +0x500 | spawn x, y, z | `Player_ctor` light record `0x1a1e48–0x1a1e50` |
| +0x4d2…+0x4f0 | light colours ±188/−64, 300.0, 1/90000 | `Player_ctor` `0x1a1e38–0x1a1e9c` |
| +0x544, +0x550 | its two `res_find` answers | `Player_ctor` `0x1a21bc`, `0x1a21f4` |
| +0x548, +0x54c, +0x554, +0x558 | 0 here | `Player_ctor` `0x1a1ffc–0x1a20c4` |
| +0x470, +0x58c, +0x461 | 1.6, state 2 (neutral), 1 | `Player_ctor` `0x1a22d4–0x1a22ec` |
| record +0x43d8 | the block | `Player_ctor` `0x1a221c` (record `0x4d8af0 + slot × 0x4c30`) |
| record +0x4bc8 | 0 | `Player_ctor` `0x1a24b4` |
| `0x4ebbb4` | `0x5353e0` | `Player_ctor` `0x1a1eec` |

Also written: the zeroed latches and counters listed in `constructor_fields`
(+0x5c…+0x8c, +0x36c…+0x3a8, +0x3cc, +0x450…+0x490, +0x4a8 = −1). The
`Creature_ctor` AI fields are listed in `arena-monsters.md` §2.1. The definition's
111 resolved cells and its generation word are global stores. The five
animation-event cells (`0x1a2394–0x1a241c`) all alias one authored part in this
fixture.

## 3. Placement and wave replacement (`arena_startWave` slot loop)

For each slot that passes `net_isSlotActive`, in this order:

| Site | Call |
|---|---|
| `0x306000` | `arena_pickSpawnPoint(1, slot, out position, out facing)`, the ring around entry 0 (`tools/ref_arena_modes.py` `pick_spawn`) |
| `0x306028` | the old object's slot-1 destructor `(old, 3)` |
| `0x306030` | `pool_new(0x590)` returns the old block again: the freed block heads its free list (`object-system.md` §2.2, executed there) |
| `0x30604c` | `Player_ctor(block, position, facing, slot, 0)` |
| `0x306090` | `game_resetTimers4f84a8()` |

The replacement draws once (the constructor). Wave placement (`flag` 1) does not
draw. On both seeds, with one active slot and entry 0 at the origin, the new player
stands at the ring point x = 36.0 (`0x42100000`), y = `0x37100000`, z = 0, facing
`0x0001`. The object fields, the home vector and the seed equal the models.
`arena_pickSpawnPoint` needs the C library and float helpers (`0x3a5000–0x3c0000`)
to run for real. With them stubbed the facing came out wrong (`0x853b`).

`game_resetTimers4f84a8`: halfword `0x4f7194` and the four dead countdowns
`0x4f84a8 + 2 × slot` (slot 3 down to 0) get 240. No calls, no draw.

`arena_startWave` does **not** call `Player_startSpawnProtection`; only
`player_respawn` does.

## 4. Old player destructor (slot 1, `0x1a1bb8`)

Stores: vtable `0x511308`. Record +0x43d8 and the five words +0x43dc…+0x43ec are
set to 0. In the 12 executed cases (slot 0 or 2, record linked or not, flags 0, 1
or 3, prediction-copy flag set in one probe), these stores were unconditional.

Calls in order:

1. `game_rebuildAlivePlayers`;
2. `handle_clear(+0x588)`;
3. `AnimState_dtor(+0x560)`;
4. `light_dtor(+0x504)`, then `light_dtor(+0x4c8)`;
5. `handle_clear(+0x4b8)`, then the five heads +0x438 down to +0x3d8;
6. the Creature destructor `0x117128` with flags 0;
7. only when bit 0 of the flags is set, a tail jump to `pool_free(this)` `0x150470`.

No draw.

## 5. Spawn protection (`0x1b8f28`, from `player_respawn`)

- **Countdown +0x4b4:** 90 when network byte `0x402791` is set, else 60. It is
  overwritten with 1 while `g_recallCountdown` `0x41b51d` is non-zero.
- **Hiding:** calls `SkillResurrect_isSlotBeingRaised(0x6e3010, slot)` and ORs flag
  0x2 into +0xc only when that returns 0.
- **Light:** `pool_new(0xbc)`, then `LightEffect_ctor` `0x201bd8` only if a block
  came back.
- **Sound:** `res_find(0x535ef0, 0x536220)`, then
  `sound_playOnObject(answer, 0; 1.0)`.
- **Particles:** on the first call only (guard word `0x4ef470` = 0),
  `particleDef_ctor(0x865750, …)` runs and the guard is set to 1. Then
  `model_getSamplePointCount(+0x544)` runs, followed by one
  `model_getSamplePoint(+0x544, +0x114, …)` per sample point (0 and 3 executed).

None of the three generators (`0x404464`, `0x404460`, `0x404468`) moves in this
function's own code. `LightEffect_ctor` is a boundary: a `GameObject`-derived
constructor draws once (`tools/ref_skills_a.py` docstring). So a respawn with a
light draws twice in total, which section 7 does not include.

## 6. Start of match and shutdown

- **Start:** `arena_begin` stores waves-left 3 and calls `arena_startWave(1)`
  (`docs/arena-modes.md` §3). Every wave start replaces each active player as in
  §3 above, including wave 0.
- **Respawn:** the `player_respawn` wrapper is executed in
  `docs/spec/arena-match-core.md`. Section 7 here composes it with the real
  destructor, pool reuse, constructor chain and spawn protection, for exact (−1, −1)
  and free-spot (2, 3) placement. Results: the new object reuses the old block and
  stands at the given or found spot; +0x4b4 = 60, flags gain 0x2, record HP is 50 of
  100, and the dead countdown is 240. The seed advances exactly once, because the
  light allocation was refused in this fixture.
- **Shutdown:** `arena_shutdown` `0x304fb0` frees the arena pointers and tasks
  without destroying the player (`arena-match-core.md`). At the end prompt,
  `save_playerCopy` restores the full saved records (same document). The level
  teardown that destroys the last `Player` objects is not executed here.

## 7. Tick and damage reuse

A player built by this constructor chain then runs `Player_run`, `Player_takeDamage`
and `Player_processDamage` against their executed models in
`tools/difftest_arena_player_tick.py` (`docs/spec/arena-player-tick.md`): 1,500 ticks
and 800 damage cases per seed, no mismatches.

## Limits

- Resource answers are authored: one part for every `res_find`.
- Property queries return 0.
- `LightEffect`, `0x355490`, `0x1707b0`, `0x1b2470`, `0x183820`, `0x3b60c0`,
  `player_recalcStats`, and the destructor's handle, light, animation and Creature
  bodies are boundaries.
- Network placement (a shared draw), several active slots, mode A, and a non-zero
  saved-monster count were not run through the replacement loop.
