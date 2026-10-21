# Player wading: the water test, the ripples, the depth band and the footstep

US `SLUS_209.73` v2.00, 2026-10-21. This is the prose of `tools/ref_wading.py`. The
original was run against it by `tools/difftest_wading.py`. It answers what the native
client's `codex/water-ripples` branch refused: the player's `water_disturb` arguments, the
water-depth test, and whether wading changes how the player moves.

Evidence labels follow `docs/spec/combat-movement.md`:

- **Executed**: the original instructions ran in `tools/ee_emu.py`, an instruction
  interpreter, on constructed memory. They agreed with the model on the calls and their
  arguments, on every byte stored outside the stack, on the shared seed 0x404464 and its
  draw count, on the cosmetic seed 0x404460, and on the result.
- **Observed**: read at the address given.
- **Inferred**: concluded from Observed or Executed facts.
- **Unknown**: not established.

Nothing here was run on a console, in PCSX2 or on the live rig. No disassembly, decompiler
output or game data is in this file. The names of the sound and lump strings are not
recorded. They are referred to by their addresses only.

This builds on the following documents, all merged into this branch:

- `docs/spec/movement-camera.md` 4.1(f), `t3/research-anim`.
- `docs/spec/water-services.md` and `tools/ref_water_services.py`, `t3/research-anim`.
- `docs/spec/combat-movement.md` 3(f) and `tools/ref_combat_move.py`, `t3/research-combat-walk`.
  The `playerMove` entry there had already executed the call arguments, with the water
  services as stubs.
- `docs/formats/water-draw.md` 5–7, `t3/research-textures`.
- `docs/spec/player-tick.md`, for the two `Player_run` states.

What is new here:

- the water services run for real inside the `Player_move` comparison, so every ripple
  writes the real grid;
- the depth band and the edge band, measured on the original;
- multi-frame sequences;
- an executed A/B test showing that wading does not change the walk;
- `Player_footstep` and `sound_playFoley`;
- the full list of readers of the in-water bit;
- the constants pinned to their instruction addresses.

## 1. In brief

1. **The in-water bit** is creature flag bit 61 of the 64-bit word at +0xa8. Player code
   reads it in three functions only: `Player_move` 0x1b4020, `Player_run` 0x1a5030 and
   `Player_footstep` 0x1beec8 (section 8). *Observed* with `tools/flagxref.py`. The
   behaviour is *Executed*.
2. **Entering the water.** Out of water, on frames where `g_simFrame & 3 == 0`,
   `Player_move` calls `water_test(g_world, copy of position, &height; 12.0)`. On a hit
   it does the following, in this order:
   - one shared-seed draw;
   - sets the bit;
   - a splash sound: volume 1.0 when airborne (+0x47c), else 0.4;
   - an entry ripple, `water_disturb(g_world, (x − 0.0, y, z − 12.0); 3000 or 1000, 24.0)`;
   - when airborne only, a splash burst at the water height.

   *Executed*.
3. **Wading.** While the bit is set, `Player_move` calls
   `water_disturb(g_world, (x − 0.0, y, z − 12.0); 300.0, 12.0)`. It does so every frame
   while the stick speed `s ≥ 0.01`, and only on frames where `frame & 0xf == 0` when
   `s` is lower. When that call touches no water chunk, the bit is cleared. *Executed*.
4. **The depth band.** Let `dz` be the water surface (the chunk's z) minus the player's
   feet (`pos.z`).
   - The player **enters** water for `−1 ≤ dz ≤ 60`, and when the chunk's XY box is
     within **13** of the player.
   - A wading player **stays** in water for `−13 ≤ dz ≤ 48`, and when the box is within
     **12**.

   *Executed* at three heights, in steps of 0.25 (section 4).
5. **The deep band, 48 < dz ≤ 60.** The player enters, leaves on the next frame and
   enters again 4 frames later: one shared draw and one splash sound every 4 frames, and no
   grid write. *Executed* (section 9).
6. **No movement effect.** Wading does not change speed, facing, animation blend,
   velocity or the move. *Executed*: the original was run twice from one memory snapshot,
   in water and dry, 1,000 cases per seed, and gave identical outputs (section 7).
   The water code never touches velocity: in `Player_move`, every read of the bit is in
   the water block. *Observed*.
7. **Two `Player_run` states also ripple while in water.**
   - At jump take-off (state 7): `water_disturb(...; 3000.0, 24.0)`.
   - In every block-walk frame (state 0xb): `water_disturb(...; 1000.0, 12.0)`.

   Neither clears the bit. *Executed* at the call level.
8. **The footstep.** The in-water bit makes `sound_playFoley` play the water footstep:
   variant 1 or 2, drawn from the **cosmetic** seed 0x404460. Without the bit, the boot
   item's flags choose the sound. Footstep timing is not changed. *Executed*.
9. **Hurting water.** On levels whose flag word 0x44fe08 has bit 0x1000, a wading player
   calls `damage_apply` on itself every 16th frame. 3 of the 90 level-table rows set that
   bit (a count only; `docs/data-tables.md` 7.1). *Executed* (the call); what the bit
   means is *Unknown*.

## 2. Fields and globals

| Where | Type | Meaning | Evidence |
|---|---|---|---|
| player +0x10, +0x14, +0x18 | float×3 | position; z is the feet | Executed |
| player +0xa8 bit 61 | u64 bit | standing in water; set by the entry, cleared by a wading ripple that touches nothing | Executed; flagxref (section 8) |
| player +0x47c | u8 | airborne (selects the 3000 entry ripple, volume 1.0 and the burst) | Executed |
| player +0x3c8 | s32 | slot, which selects the record for the footstep | Executed |
| record +0x4400, +0x4418 | item* | equipped-item slots 4 and 10 of the +0x43f0 table (`docs/player.md`); the first one that is non-null supplies the footstep flags; `symbols/player.tsv` calls it the boot item | Executed |
| item +8 | u32 | footstep flags (bits 0x780000) | Executed |
| `g_simFrame` 0x44fdcc | u32 | the `& 3` (entry test) and `& 0xf` (still-wader ripple, hurting water) gates | Executed |
| `g_world` 0x44fdc8 | world* | passed to both services | Executed |
| level flag word 0x44fe08 | u32 | bit 0x1000: hurting water | Executed (call), meaning Unknown |
| cut-skip byte 0x44fcec | u8 | non-zero: `water_disturb` returns 0 at once. A wader then **leaves the water** on that frame | Executed |
| shared seed 0x404464 | u32 | one draw per entry | Executed |
| cosmetic seed 0x404460 | u32 | one draw per audible footstep | Executed |
| ripple grid +0xa90 | s16[32][32] | where the ripples add (`water-services.md`) | Executed |

`s` is the stick speed of `Player_move` 4.1(c). Step (e) sets it to 1.0 in mode 2 or in
action state 1, so a rushing or swinging wader always ripples every frame.

## 3. `Player_move` step (f), with calls and seed draws

This runs after the turn and before the locomotion blend and the move, so it uses the
position from the start of the frame. *Executed* (`playerMoveWater`; the 0x1b4400–0x1b4794
block is executed except for one padding `nop` at 0x1b4714).

```
if P.flags64 & bit61:                                       test 0x1b4430
    if (word 0x44fe08 & 0x1000) and (frame & 0xf) == 0:    0x1b4440, 0x1b4454
        damage_apply(P, P, 100000000, 0, 0, 0x1000030, 0, 0; 1e8, 1e8)     0x1b4490
    touched = 1
    if s >= 0.01 or (frame & 0xf) == 0:                     0x1b4498, 0x1b44b8
        touched = water_disturb(g_world, (x - 0.0, y, z - 12.0); 300.0, 12.0)
                                                            0x1b4518 / 0x1b457c
    if touched == 0:  clear bit 61                          0x1b4594-0x1b45ac
elif (frame & 3) == 0:                                      0x1b45c0
    hit = water_test(g_world, copy of (x, y, z), &height; 12.0)        0x1b4600
    if hit:
        draw the shared seed once (seed = seed * 0x19660d + 0x3c6ef35f)  0x1b461c-0x1b4654
        set bit 61                                          0x1b4634
        name = sprintf(<format 0x537688>, 1)                0x1b4650
        entry = res_find(<lump 0x535ef0>, name)
        if P+0x47c:                                         0x1b465c
            sound_playOnObject(entry, P; 1.0)               0x1b4680
            water_disturb(g_world, (x - 0.0, y, z - 12.0); 3000.0, 24.0)    0x1b46dc
            fx_burst_1fbdf0((x, y, height); 1.0)            0x1b4704
        else:
            sound_playOnObject(entry, P; 0.4)               0x1b4734
            water_disturb(g_world, (x - 0.0, y, z - 12.0); 1000.0, 24.0)    0x1b478c
```

- The value of the entry draw is not used; only the seed word changes. The draw happens
  for every machine's copy of the player, because simulation is lockstep. The ghost run of
  the prediction copy restores the seed (`docs/netcode.md`, the ghost step). The water
  block does not test the copy flag 0x20000. *Executed*: cases with the flag set matched.
- The **entry ripple's return value is ignored**. The bit stays set even when that ripple
  touches nothing.
- `x − 0.0` is computed as written.
- `height` is the chunk's minimum z (`water_test`). It is used only by the airborne burst.

## 4. The depth band and the edge band

`water_test` (radius 12) queries
`((x−12)−1, (y−12)−1, z−1) .. ((x+12)+1, (y+12)+1, z+60)`. The wading ripple queries
around `(x, y, z−12)` with no XY padding: `(x−12, y−12, z−13) .. (x+12, y+12, z+48)`. Both
tests are inclusive against the chunk's bounding box, and only flag-0x80 chunks count
(`water-services.md`). `ref_wading.entry_box` and `wade_box` return these boxes.

The `band` entry runs the original `Player_move` on a flat 384-wide chunk. It sweeps `dz`
from −20 to +70 and the X distance to the chunk's edge from 0 to 20, both in steps of 0.25.
It does this at feet heights 0, 37.5 and −812.25. *Executed*: 2,652 cases per seed, 0
mismatches. The ranges where the bit is set after the call:

| Sweep | Bit before | In water for |
|---|---|---|
| surface − feet | clear (entry) | −1 … 60 |
| surface − feet | set (wading) | −13 … 48 |
| distance to edge (dz = 10) | clear | 0 … 13 |
| distance to edge (dz = 10) | set | 0 … 12 |

The ranges are the same at all three heights. The wading band sits **12 lower** than the
entry band, so the two make a hysteresis:

- A player standing up to 13 above the surface (on a bank or a step) stays "in" water,
  but cannot enter from there.
- Water that rises past 48 above the feet drops the player out of the wading state.

*Inferred* from the table: the band is a box test on chunk bounds. It does not use the
drawn wave height or terrain.

## 5. What the ripples write

`water_disturb` is executed in `docs/spec/water-services.md`. Here it runs inside
`Player_move`: 603 and 610 of the 3,000 cases (seeds 20973 and 7) wrote the grid, all equal. The following
footprints were computed with `ref_wading` on those executed bodies, for a point at a grid
cell centre:

| Chunk width | Ripple | Cells written | Values |
|---|---|---|---|
| 384 | entry on foot, 1000 / 24 | 9 | centre 1000, 4 × 749, 4 × 499 |
| 384 | entry airborne, 3000 / 24 | 9 | centre 3000, 4 × 2249, 4 × 1499 |
| 384 | wading, 300 / 12 | 1 | centre 300 |
| 120 | 1000 / 24 | 129 | 1000 down to 23 |
| 120 | 300 / 12 | 37 | 300 down to 7 |
| 768 | any of the three | 1 | the strength |

The grid radius is `r × 32 / (cells × 12)`. On the common 384-wide tile a wading player
adds 300 to one cell per frame. The four neighbours of that cell are exactly on the circle,
and raw32 rounding puts them just outside it (`water-services.md`). The step and the seams
of `docs/formats/water-draw.md` 5 turn the grid into visible rings on the next frames.

A ripple whose box misses every water chunk writes nothing. An entry in the deep band
(48 < dz ≤ 60) is one of these: the splash sounds, but no ring appears.

## 6. The two `Player_run` ripples

| State | Where | Condition | Call | Clears the bit? |
|---|---|---|---|---|
| 7 (jump) | test 0x1a5fe4, call 0x1a6050 | take-off frame (+0x47e still 0) and bit 61 set | `water_disturb(g_world, (x − 0.0, y, z − 12.0); 3000.0, 24.0)` (z offset 0x1a5ff4, strength 0x1a6034, radius 0x1a6040) | no; the result is ignored |
| 0xb (block-walk) | test 0x1a65c8, call 0x1a662c | every frame with bit 61 set | `water_disturb(...; 1000.0, 12.0)` (0x1a65dc, 0x1a6608) | no |

*Executed* at the call level (`difftest_player.py`, water services as stubs):

- `playerRun` in this difftest counted the calls by argument pattern: 1 call from state 7
  and 29 from state 0xb at seed 20973, and 99 from state 0xb at seed 7 (3,000 ticks each,
  offline and online).
- The full `difftest_player.py` runs passed: 31,990 ticks at seed 20973 and 31,991 at
  seed 7. State 7 started 90 and 69 ticks, and state 0xb 443 and 416, with 0 mismatches.

Both states also call `Player_move` (`player-tick.md`), so a block-walking wader makes the
1000/12 ripple and then the 300/12 ripple from step (f) on the same frame. *Inferred* from
the two Executed bodies.

## 7. Wading does not change movement

`wadeNoSpeed` builds a state in which the player is inside water. It takes a memory
snapshot, then runs the original `Player_move` once with bit 61 set and once with it clear,
on a frame where `frame & 3 ≠ 0` (no entry test). The two runs must give:

- the same calls, apart from `damage_apply`;
- the same stored bytes, apart from the ripple grids and +0xa8;
- the same shared seed.

*Executed*: 1,000 cases per seed, 0 differences. In 820 cases at seed 20973 the player was
moving, and in 479 the wading ripple wrote the grid.

So the speed scale, the turn, the locomotion blend, the velocity (+0x4bc, +0x4c0), the
`creature_moveSimple` vector and the event bits are the same in water and out. There is no
wading slowdown in `Player_move`. `player_speedScale` 0x1bea10 does not read the bit either
(flagxref, section 8).

## 8. Every reader of bit 61 that player code reaches

`python3 tools/flagxref.py <elf> 2000000000000000 a8 --stores` lists 144 functions. Most
are `*_clone` copies of the whole word. The tests and sets reachable from player code are
in the table below. The listing itself is local and not tracked.

| Function | Sites | What it does with the bit |
|---|---|---|
| `Player_move` 0x1b4020 | test 0x1b4430, clear 0x1b45ac, set 0x1b4634 | section 3 |
| `Player_run` 0x1a5030 | tests 0x1a5fe4, 0x1a65c8 | section 6 |
| `Player_footstep` 0x1beec8 | test 0x1bef44 | section 10 |
| `Player_clone` 0x11e870 | copy 0x11ea58 | the prediction copy inherits the bit |

The other tests are in creature and monster code: `Creature_moveBy`, the
`Creature_applyKnockback` mask 0x2000000000100000, and the Cyclops, Froglock and
LavaMonster bodies. Player code does not call them.

Whole-word stores of unknown value can also set or clear the bit. These were not resolved
here (*Unknown*):

- `player_initNewCharacter` 0x1b22c4, 0x1b23e8;
- `Player_processDamage` 0x1b33c8;
- `Player_regenHealth` 0x1b3d18–0x1b3d4c;
- `player_respawn` 0x1bd134;
- `player_importCharacter` 0x1bd600;
- `player_recalcStats` 0x1b6a48;
- `net_predictLocalPlayer` 0x132cbc;
- `script_applyCFlag` 0x1446a0 and 0x1446b0. These set or clear a bit chosen at run time,
  so a level script can force the bit.

## 9. Frame sequences

`sequence` runs 32 consecutive frames of the original. Each frame is also compared with
the model. The player stands on a flat chunk with the stick held at 1.0 (or 0.0), the frame
starts at a multiple of 16 and the dialog is closed. *Executed* at seed 20973 (224 frames,
0 mismatches). Seed 7 gave the same counts.

| Surface − feet | Stick | Start | Entries | Exits | Shared draws | Frames that wrote the grid |
|---|---|---|---|---|---|---|
| +10 | 1.0 | dry | 1 | 0 | 1 | 32 (1 entry + 31 wading) |
| +10 | 0.0 | dry | 1 | 0 | 1 | 2 (entry, frame +16) |
| +55 | 1.0 | dry | 8 | 8 | 8 | 0 |
| −5 | 1.0 | dry | 0 | 0 | 0 | 0 |
| −12 | 1.0 | wet | 0 | 0 | 0 | 32 |
| −14 | 1.0 | wet | 0 | 1 | 0 | 0 |
| +50 | 1.0 | wet | 7 | 8 | 7 | 0 |

## 10. The footstep: `Player_footstep` 0x1beec8 and `sound_playFoley` 0x1e7c40

`Player_footstep(P)` works as follows:

1. Find the record at `0x4d8af0 + slot × 0x4c30`.
2. Find the item: record +0x4400 if it is non-null, else record +0x4418.
3. Take the flags: the low word of `item + 8`, or 0x80000 when there is no item.
4. Call `sound_playFoley(copy of position, bit 61, 0, flags)` and return its result.

It makes no other store and no draw.

`sound_playFoley(pos, wet, _, flags)` works as follows:

- **wet ≠ 0:** draw the cosmetic seed 0x404460 once, with the same LCG. Take
  `n = (d & 1) + 1` and the format at 0x53ddd8.
- **dry**, flags & 0x780000 == 0: no sound. The result register is 0x400000, a value left
  over from the branch's delay slot at 0x1e7cec.
- **dry**, otherwise, the first set bit wins:

  | Bit | Format | Variants | Formula |
  |---|---|---|---|
  | 0x400000 | 0x53dde8 | 5 | `n = d % 5 + 1` |
  | 0x200000 | 0x53de00 | 5 | `n = d % 5 + 1` |
  | 0x100000 | 0x53de18 | 5 | `n = d % 5 + 1` |
  | none of these | 0x53de30 | 4 | `n = (d & 3) + 1` |

- In every audible case, call `res_find(<lump 0x53d688>, sprintf(format, n))`, then
  `sound_playAtPos(entry, copy of position; 1.0)`, and return its result.

*Executed* (`footstep`: 3,000 cases per seed, 0 mismatches; about half of the cases in
water, 302 silent). The shared seed never moves, so the wading footstep is cosmetic and
safe per machine. When footsteps happen is not changed by water: the caller's
animation-event bits decide it (`player-animation-dispatch.md`).

## 11. Constants and addresses

The table is in `ref_wading.player_wade_constants`, which a unit test checks lies inside
`Player_move` or `Player_run`. The addresses are *Observed*. The values are *Executed*
through the call arguments.

| Value | Address | Meaning |
|---|---|---|
| 3 | 0x1b45c0 | entry test only on frames where `frame & 3 == 0` |
| 12.0 (0x41400000) | 0x1b45d4 | `water_test` radius, and the z offset of the entry ripple |
| — | 0x1b4600 | `water_test` call |
| — | 0x1b461c–0x1b4654 | the shared-seed draw on entry |
| 1.0 / 0.4 (0x3f800000 / 0x3ecccccc) | 0x1b4668 / 0x1b4728 | splash volume, airborne / on foot |
| 3000.0 (0x453b8000) | 0x1b46a8 | entry ripple strength, airborne |
| 1000.0 (0x447a0000) | 0x1b475c | entry ripple strength, on foot |
| 24.0 (0x41c00000) | 0x1b46cc, 0x1b477c | entry ripple radius |
| — | 0x1b4704 | airborne splash burst `fx_burst_1fbdf0` |
| 0x1000 | 0x1b4440 | hurting-water level bit (word 0x44fe08) |
| 0xf | 0x1b4454, 0x1b44b8 | 16th-frame gates (damage; still wader's ripple) |
| 0.01 (0x3c23d70a) | 0x1b4498 | moving-wader threshold |
| 300.0 (0x43960000) | 0x1b4500, 0x1b4564 | wading ripple strength (calls 0x1b4518, 0x1b457c) |
| 12.0 (0x41400000) | 0x1b44c4, 0x1b4528 | wading ripple radius and z offset |
| — | 0x1b45ac | clear bit 61 when the wading ripple touches nothing |
| 12.0 / 3000.0 / 24.0 | 0x1a5ff4 / 0x1a6034 / 0x1a6040 | `Player_run` state 7 ripple |
| 12.0 / 1000.0 | 0x1a65dc / 0x1a6608 | `Player_run` state 0xb ripple |
| 0x80000 | 0x1beef8 | footstep flags with no item |
| 0x780000, 0x400000, 0x200000, 0x100000 | 0x1e7ce0–0x1e7d68 | foley flag tests |
| 0x400000 | 0x1e7cec | silent-footstep result (delay slot) |
| 0x404460 | 0x1e7c68 | cosmetic seed used by the foley draw |
| 0x537688, 0x535ef0 | Player_move | splash format, lump |
| 0x53ddd8, 0x53dde8, 0x53de00, 0x53de18, 0x53de30, 0x53d688 | sound_playFoley | foley formats, lump |

## 12. Verification (2026-10-21)

```
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_wading.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_wading.py local/SLUS_209.73 --seed 7
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_player.py local/SLUS_209.73 --seed 20973 -v
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_player.py local/SLUS_209.73 --seed 7 -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
```

| Entry | Seed 20973 | Seed 7 |
|---|---|---|
| playerMoveWater | 3,000 compared, 0 failed, 0 refused. 488 entries (488 shared draws), 979 stayed, 559 left, 603 cases wrote the grid | 3,000 / 0 / 0. 535 entries (535 draws), 953 stayed, 554 left, 610 wrote the grid |
| band | 2,652 / 0 failed, the ranges of section 4 | 2,652 / 0, identical ranges |
| sequence | 224 frames / 0, the table of section 9 | 224 / 0, identical table |
| playerRun | PASS. State 7 started 14 ticks, state 0xb 40; water_disturb 3000/24 ×1, 1000/12 ×29 | PASS. 8 and 133 ticks; 1000/12 ×99 (no take-off in water this seed) |
| wadeNoSpeed | 1,000 / 0 differences (820 moving, 479 rippled) | 1,000 / 0 (849 moving, 502 rippled) |
| footstep | 3,000 / 0 (1,503 in water, 302 silent) | 3,000 / 0 (1,478 in water, 302 silent) |
| difftest_player.py -v | 31,990 ticks, all PASS (state 7: 90, state 0xb: 443) | 31,991 ticks, all PASS (69, 416) |

The executable's sha256 is checked. The figures in sections 4, 6, 7, 9 and 10 come from
these runs.
`playerMoveWater` executes all 384 instructions of the water services 0x189240–0x189840
(the split-node trees are included) and 228 of the 229 instructions of 0x1b4400–0x1b4794.

## 13. What a native client should implement, ranked

1. **The in-water bit with the two bands** (section 3, section 4). Entry: test every 4th
   frame with the padded box, `dz ∈ [−1, 60]`, 13 at the edges. Stay: let the wading
   ripple's own query decide, `dz ∈ [−13, 48]`, 12 at the edges. Clear the bit only on a
   wading ripple that returns 0. The cut-skip byte also counts as a miss. Everything else
   depends on this.
2. **The wading ripple**, 300 / 12 at `(x − 0.0, y, z − 12)`. Every frame while `s ≥ 0.01`
   (and always in mode 2 or state 1), else on 16th frames. Use the native
   `WaterImage::disturb_chunks` / `Field::disturb` path the water-ripples branch already
   routes through the WORLD query. This replaces the refusal of `codex/water-ripples` item 1.
3. **The entry splash.** The shared-seed draw must be taken, because lockstep needs it
   even though the value is unused. Then the bit, the 0.4 or 1.0 splash and the
   1000 / 3000 radius-24 ripple. Ignore its return value.
4. **The `Player_run` ripples**: state 0xb, 1000 / 12 every frame; jump take-off, 3000 / 24.
5. **The water footstep** through `sound_playFoley`, drawn from the cosmetic seed only.
6. **Hurting water** (flag 0x1000), `damage_apply` every 16th frame. Only 3 level rows set
   the flag, and what it means is Unknown.
7. **Do not add a wading slowdown.** There is none (section 7).

The native harness's labelled probe (3000/24 at the player) should become the real calls
above. The splash burst (`fx_burst_1fbdf0`) and the sound names stay presentation.

## 14. Unknown and outside

- What `fx_burst_1fbdf0` 0x1fbdf0 draws, and which sound entries the formats resolve to.
- What level-flag bit 0x1000 means, and whether a script changes word 0x44fe08 at run time.
- The whole-word stores of +0xa8 listed in section 8, including the script `cflag`
  commands.
- Grid lifetime, the water simulation tick and the drawn surface are in
  `docs/formats/water-draw.md`, not here.
- The prediction copy's seed restore is cited from `docs/netcode.md`. It was not
  re-executed here.
