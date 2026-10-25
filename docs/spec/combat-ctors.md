# AntQueen, Skeleton and Soul: construction and what runs before they fight

US `SLUS_209.73` v2.00. Prose of `tools/ref_combat_ctors.py`; the comparison is
`tools/difftest_combat_ctors.py`, the synthetic tests `tools/test_ref_combat_ctors.py`.

Evidence words as in `CONTRIBUTING.md`. **Executed**: the original ran in
`tools/ee_emu.py` on an object its own constructor built, with the game's own virtual
table and the creature base class running for real underneath (the
`tools/difftest_monsters_1.py` rig and world), and the model agreed on the calls to
everything outside the models (in order, with arguments), every byte stored outside the
stack, the shared seed `0x404464` with its draw count, and the result. Seeds 20973 and 7,
0 mismatches (about 7,970 compared calls each). **Observed**: read at the address.
**Inferred** and **Unknown** as usual. Nothing here ran on a console, in PCSX2 or on the
live rig.

## 1. What was executed before this

The audit of the native client (`cursor-runs/grok-audit.md`, CAI-4) is right: the three
constructors had never been run.

- Combat round 5 (`t3/research-combat`, `tools/difftest_combat_round5.py` at faa7033)
  runs `AntQueen_run` and `Skeleton_run` states 0 and 1 and the Soul phase gate on
  objects the script zero-fills and plants by hand. `Creature_updateActive` and the rest
  of the prologue are recording stubs there. It covers 101 of 607, 143 of 809 and
  126 of 1062 instructions of the three run functions. No constructor or set-state runs.
- Round 3 of the animation work (`t3/research-anim`, `ref_creature_dispatch_data.py`)
  scanned the three set-state functions for their clip operations with
  `Creature_filterState` and every callee stubbed. That is a scan, not a comparison with
  a model, and it leaves out the timers, draws and flags below.
- No tool on any branch called `0x236c70`, `0x2a5af4` or `0x2a9478`.

## 2. Coverage (instructions executed of the body)

| Function | Address | Seed 20973 | Seed 7 | Not executed |
|---|---|---|---|---|
| `AntQueen_ctor` | `0x236c70` | 168 of 168 | 168 of 168 | |
| `AntQueen_setState` | `0x237918` | 526 of 526 | 526 of 526 | |
| `AntQueen_run` to the switch | `0x236f78` | 37 of 38 | 37 of 38 | (a) |
| `Skeleton_ctor` | `0x2a5af4` | 818 of 820 | 814 of 820 | (b) |
| `Skeleton_setState` | `0x2a7768` | 384 of 398 | 384 of 398 | (c) |
| `Skeleton_run` to the switch | `0x2a6864` | 62 of 63 | 62 of 63 | (a) |
| `Soul_ctor` | `0x2a9478` | 128 of 128 | 128 of 128 | |
| `Soul_setState` | `0x2aac38` | 385 of 408 | 385 of 408 | (d) |
| `Soul_run` to the switch | `0x2a9870` | 69 of 70 | 69 of 70 | (a) |
| `Soul_getModel` (slot 16) | `0x2ab298` | 7 of 7 | 7 of 7 | |
| `anm_setEventSlots` | `0x1183d0` | 15 of 15 | 15 of 15 | |

(a) The delay slot of the exit taken when `Creature_run` returns non-zero; it always
returns 0 (`ref_creature.run`). (b) `0x2a633c`: an element above 3, which no roll makes.
Seed 7 also missed one rare element roll at `0x2a5f70`. (c) `0x2a7bd8`, dead (§5).
(d) `0x2ab0d4`, the owner's attach-matrix branch of state 0x21, dead (§6).

To stop each run function at its switch, the difftest replaces the switch's range test
(`0x237004`, `0x2a6954`, `0x2a997c`) in the interpreter with `addiu v0, zero, 0`. The
original then leaves by its own "state out of range" exit. The switches themselves are
round 5's for states 0 and 1, and `docs/monsters-2.md` prose for the rest.

## 3. AntQueen (`0x236c70`, table `0x511078`, size 0x3e8)

Executed:
- One own draw comes BEFORE `Creature_ctor`, from the word `+0x44` that the pool block
  holds before `GameObject_ctor` seeds it. It gives the hit-point argument
  `(float)(d % 14 + 4)`, which `Creature_setStats` then replaces for the type name.
  The world zero-fills pool blocks, so the draw is the generator step from 0. Whether
  the game's pool zero-fills is Inferred from the existing difftest world.
- Turn rate 1.2, radius 45, speed 140, byte `+0x28` = 0x37, kind `+0xb4` = 0x13,
  `+0x5c` = 0.4, creature flags |= 0x8020001000, `+0x3d4` = 180, show mask for variant
  0, clip idle_a (`+0x7c`) pushed with flags 1, the every-60 run list.
- State 0 is stored DIRECTLY. The constructor does not call `AntQueen_setState`, so the
  state-0 entry (`+0xf4` = clock + d % 120, idle blend) does not run, and `+0xf4` stays
  0 from `Creature_ctor`. A second own draw sets `+0x3d8` = clock + 180 + d % 180.
- Event times: attack1 (entry 3) and sting (0x13) at 0.2, attack2 ×3 (4–6) at 0.3, all
  bit 0. Then `Creature_init`.
- Prologue: `processDamage`, `Creature_run`, `Creature_updateActive` (result NOT
  tested), `stepAnim(1.0)`, `applyKnockback(0.5)`, slot 23 (the base
  `Creature_pickTarget`).
- Set-state, all 26 cases. `Creature_filterState` comes first, and a refusal stores
  nothing. Entries that `docs/monsters-2.md` did not have:
  - State 3 starts its walk tracks by weights (`+0xac` at 1/3, `+0xb4`, `+0xbc`), unless
    it comes from 0x12, 6 or 7. Every request for 3 sets the halfword `+0x3c4` = 0xabe0.
  - State 7 with a target asks `creature_findEnemyInCone(0, 40, this, facing − 0x7fff,
    6000)`. If it finds an enemy, the bearing to it minus the facing, plus 0x7fff, as
    s16, picks the clip: above 2000 attack2_right, below −2000 attack2_left, otherwise
    centre. With no enemy found it plays centre. With no target it only stores 7.
  - State 8 sets speed 240 and clears the path. From 0x17 or 9 that is all. Otherwise
    one draw sets `+0x3d4` = clock + 300 + d % 180, and the fly tracks and takeoff play.
  - State 0x12 keeps the old state in 8, 0x17 or 9, and in 6 while clip flag 8 is set.
    Otherwise the hit direction `+0x2e0` picks one of the four hit clips.
  - State 0x14 calls `Creature_dropLoot` (no item; 36, 2, 5, 1, 5, 1), plays death with
    flags 0x16, plays takeoff unless a `+0x3c` track is playing, then slot 28.
  - State 0x17 makes one draw. Speed 240, `+0x3d4` = clock + 180 + d % 120,
    `AntQueen_pickFlyDest` to `+0x104`.
  - States 0x18 and 0x19 each draw for `+0x3d4` or `+0x3d8`. 0x19 makes a second draw
    for `+0xf4` = clock + 120 + d % 60.
  - Any other number, including 0x1a and above, is stored as requested.

## 4. Skeleton (`0x2a5af4`, table `0x5175f8`, size 0x478)

Executed:
- `Creature_ctor(type name, definition 0x5022e0 + 0x40 × set, hit points 10)`. The
  WeaponShield holder is built inline at `+0x3d8`, the same writes as Skelight's.
  `+0x3c8` = `+0x3cc` = 0. The skelcom block `0x5023e0` is resolved name by name with
  `res_find` when its generation word differs from `0x41bf78`.
- Weapon kind is one own draw `% 5`. Then the type-name prefixes, first match wins.
  The table is `ref_combat_ctors.SKEL_PREFIXES`, which agrees with `docs/monsters-2.md`,
  including the blue bow getting side 2.
- Element chance per kind: own draw × 2⁻¹⁶ below 0x3dccca2d (kinds 0 and 1),
  0x3dcccab3 (2), 0x3dcccccc (3) or 0x3dcccbc0 (4), so slightly under 10 % except for
  the spear. The element is `(d & 1) + 1`, or `d % 3 + 1` for the bow. It goes to
  holder slot 4 (1), 2 (2) or 3 (3) after the variant bits. Every hand draw is made even
  without a holder, and the holder pointer was just written, so the null tests never
  fail.
- Variant bits `+0xe8`, show mask, creature-flag class bit, HomeRange 200 with a side
  and 1000 without: as `docs/monsters-2.md`.
- The constructor CALLS `Skeleton_setState(0)` directly, through the filter. So a new
  skeleton has `+0xf4` = clock + 120 and its idle clip (`+0x44` of its kind's row) started
  twice: pushed by the constructor, then by the state.
- Fifteen `anm_setEventSlots` on the skelcom block. Rows 1–3, 0xf–0x11, 0x1f and
  0x2b–0x2d: bit 0 at 0.3. Rows 0x1d and 0x1e: bit 0 at 0.3 and again at 0.9. The bow's
  rows 0x39–0x3b: bit 1 at 0.2, then bit 0 at 1.3. Inferred: two events per bow shot.
- Prologue: `processDamage`, `Creature_run`; `Creature_updateActive`, and an inactive
  skeleton RETURNS (`docs/monsters-2.md` said "as Orc"). Holder slot 21 (skelcom, this;
  0.5), `stepAnim(1.0)`, `applyKnockback(0.7)`, slot 23.

## 5. Skeleton_setState (`0x2a7768`)

Executed, all cases:
- After the filter (a refusal stores nothing), creature flag 0x200 (blocking) is always
  cleared, and 0x200800 is cleared unless the request is 0x17.
- 0x12 tests flag 0x200 after that clear, so the "blocking flinch" clip (`+0x24`,
  block `0x2a7bd8`) is never chosen. Every flinch is `+0x34`, flags 0x10. This was not
  entered in about 2,400 calls; the reading of the code says it cannot be.
- 0x14: holder slot 11 for hands 1 and 2, object flags |= 0x4002, creature flag
  0x20000000000, `Skeleton_shatter(8)`. Then `Creature_dropLoot("bonechip"; 36, 2, 1.6,
  0.6, 1.6, 0.25)` unless creature flag 0x1000000 is set, then `obj_delete` and slot 28.
- 6 and 7 draw `+0xf4` = 20 + d % 20. 6 and 8 draw the swing (`+0x0c` or `+0x14`).
  8 sets `+0xf4` = 1. 0x11 sets the blocking flag. 0x17 pushes `+0x74` and chains `+0x44`.
- Numbers with no case are stored as requested.

## 6. Soul (`0x2a9478`, table `0x517740`, size 0x3e0)

Executed:
- `Creature_ctor(type name, definition 0x502778, hit points 10)`. State 0 is stored
  directly and `+0xf4` = 0, so the state-0 entry draw (`+0xf4` = clock + 60 + d % 120)
  is NOT made at construction. `Creature_setCharm(−1, team 0)`, five resistances 1.0.
- With an owner: object flags |= 9, `handle_link(+0x3c8, owner, owner)`, held clip
  `+0x6c`. Without one, `g_levelName` (`0x41b721`, compared without case) equal to
  "airhub" gives clip `+0x34` and a direct `Soul_setState(0x22)`; otherwise clip `+0x3c`.
- Then creature flag bit 63, the every-frame list, entry 0xb event at 0.7,
  `Creature_init`.
- Prologue: slot 16 (`Soul_getModel`: definition `+0x1c` while owned, else `+0xc`) for
  `processDamage` and again for `Creature_run`. `Creature_updateActive`, and an inactive
  soul RETURNS. `stepAnim(1.0)`, `applyKnockback(0.0)`, slot 23, then
  `Creature_moveBy(0, 0, 0)` unless it is owned or in 0x1b.
- Set-state:
  - On airhub every request becomes 0x22 BEFORE the filter.
  - A filter refusal stores nothing. An owned soul takes only 0x1a–0x20. In 0x1b nothing
    is accepted.
  - Unknown numbers, 0x23 and above included, are STORED as requested.
  - 0x10 and 0x13 keep the old state.
  - 0x19 only from 0x18 (flinch clip). 0x12 re-requests 0x19 or 0x18 through slot 27 and
    then stores 0x12.
  - 0x21: two particles per model sample point. Each velocity is drawn by own-draw
    rejection in the unit ball (three draws a try), but the z word is zeroed before the
    ×15 scale (`0x2ab1f0`), so the burst is flat. Then object flags |= 0x4002 and
    `obj_delete`. The attach-matrix branch for an owner is dead: an owned soul never
    gets there.

## 7. What this means for the native client (audit CAI-1, CAI-2, CAI-4)

- CAI-4 (fabricated objects): the three constructors, set-state (slot 27), the run
  prologue (slot 4 up to its switch) and Soul's slot 16 are now a contract. The other
  slots that differ from the base table are not executed here: 1, 2 (takeDamage),
  3, 5 (draw), 8 and 9 (load, save), 12, 15 and 20 (isEnemy). A port should keep
  refusing them until they are; see §8.
- CAI-1 (prologue): executed for these three classes, with the activity difference
  (AntQueen ignores it).
- CAI-2 (set-state): the real set-states of these three run `Creature_filterState`
  first, and their timers, draws, flags, loot and deletes are above. AntQueen and
  Skeleton start their attack clips as swings (`anim_startBlendInOut`), and the
  dispatch-row baseline is not what runs.

## 8. Open

- The run switches past round 5's states 0 and 1: Skeleton's arrow release, AntQueen's
  flight, Soul's thrown flight. They are prose in `docs/monsters-2.md`, not executed here.
  Since then (2026-10-21): every AntQueen state and `AntQueen_pickFlyDest` are executed
  (`docs/spec/antqueen-run.md`); Skeleton past state 1 and Soul's switch are not.
- `Soul_takeDamage` `0x2aa908` (the Demon test). The difftest sends no damage to a Soul
  for that reason. `Skeleton_takeDamage` `0x2a774c`, `Skeleton_isEnemy` `0x2a7e04`,
  `Skeleton_shatter` `0x2a7ef0`, and `AntQueen_pickFlyDest` `0x238150` stay recording
  stubs. Since then (2026-10-21): `Soul_takeDamage`, `Skeleton_takeDamage`,
  `AntQueen_takeDamage` and `Skeleton_isEnemy` are executed (`docs/spec/combat-ctors-2.md`),
  `AntQueen_pickFlyDest` too (`docs/spec/antqueen-run.md`); `Skeleton_shatter` is not.
- Whether the game's pool hands AntQueen a zeroed `+0x44` (the hit-point argument draw)
  is Inferred. It does not matter after `Creature_setStats`, but the draw advances
  nothing shared: it is the block's own word.
