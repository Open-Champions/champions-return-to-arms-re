# Combat round 2: monster hit helpers, death, loot and the destructor chain

US `SLUS_209.73` v2.00. Round 2, targets 5 and 6, of the combat research whose first round
is `docs/combat-runtime.md` (read that first). This document is the prose of
`tools/ref_combat_monsters.py`; `tools/difftest_combat_monsters.py` runs the original
functions in `tools/ee_emu.py` against it and `tools/test_ref_combat_monsters.py` pins the
rules on synthetic fixtures.

Labels as in round 1: **Executed** = the original instructions were run one function at a
time in `tools/ee_emu.py` (an instruction interpreter, not a console) on constructed state
and agreed with the model - calls with arguments, every byte stored outside the stack, the
shared seed, the result; the entry point is named. **Observed** = read at the address
given. **Inferred**. **Unknown**. **Authored** = a choice of this contract. Nothing here
was run on a console, in PCSX2 or on the live rig.

Nothing in round 1 changes: `MonsterCombatModel` is a subclass of
`ref_combat_runtime.CombatModel`, `MonsterRuntime` of `Runtime`, and no round-1 method or
test vector is altered. Where a round-1 sentence is short or wrong, section 7 says so; the
fix lives here.

## 1. Sight helpers

All three are *Executed* (entry points `canSeePoint`, `canSeeObjEdge`, `canSeeTargetIn`).
They differ from round 1's `creature_canSeeObj` 0x10c810 in four places, so they are given
as differences:

| | `creature_canSeeObj` 0x10c810 (round 1) | `creature_canSeeObjEdge` 0x10c5b8 | `creature_canSeePoint` 0x10c238 |
|---|---|---|---|
| Arguments | (c, obj, facing, arc, rayMode; near, far, lead) | the same | (c, &pos, facing, arc; near, far) |
| No object | 0 | 0 | - |
| Lead | obj +0x308/+0x30c x lead for a creature, when lead != 0 | the same | none |
| Arc | `abs(s16(atan2_16(v.y, v.x) - facing)) < arc` | the same | `abs(s16(s16(0x4000 - atan2_16(v.x, v.y)) - facing)) < arc` |
| Range (2-D centre distance d) | `(d - obj.r) - c.r < far`, `near <= (d + obj.r) - c.r` | `d < far + obj.r`, `near - obj.r <= d` (no creature radius) | `near <= d < far` (no radius at all) |
| Ray origin | half the creature's height | half height | **full** height |
| Ray mask | 3, or 0 with rayMode | 3, or 0 with rayMode | always 3 |
| Seen when | `t < 0` or `1 < t` (factor 0x3f8ccccc) | the same | the same |

`Creature_canSeeTargetIn` 0x118d40 (c, facing, arc, rayMode; near, far, lead) is 0 without a
target and otherwise a tail call of `creature_canSeeObj` on it (modelled in
`ref_arena_monsters`, executed here again).

## 2. Hit, knock-back, cooldown and notification helpers

*Executed* unless marked. Arguments in register order; "dmg" is
`damage_apply(f32(min), f32(max); victim, c, attack, 0, 0, flags, desc, 0)` and its result.

- **`Creature_hitTargetAtReach` 0x1196e8** (c, min, max, attack, flags, desc; reach):
  no target: 0. Point = `(c.x + cos16(facing) x reach, c.y + sin16(facing) x reach, c.z)`.
  The target must be within 60.0 of the point **in 3-D** (strict) and not dead (flag 8);
  there is **no arc, no sight ray and no enemy test**. Then dmg. The victim is read from the
  handle before the angle calls and the dead test after (the same object in every case).
- **`Creature_hitTargetInArcEdge` 0x119850**: round 1's `hitTargetInArc` with
  `creature_canSeeObjEdge` (ray mode 0, lead 0) as the test.
- **`Creature_hitTargetOrPlayerInArc` 0x119a20** (c, facing, arc, min, max, attack, flags,
  desc; near, far): the target, when there is one and `creature_canSeePoint(target
  position)` passes; otherwise whatever `creature_findPlayerInCone` returns; 0 when neither;
  then dmg. **Neither branch tests the enemy slot or flag 8 itself.**
- **`creature_findPlayerInCone` 0x10ca70** (c, facing, arc; near, far):
  - a **charmed** creature (s16 +0x312 != 0) runs an inline copy of round 1's
    `creature_findEnemyInCone` - same box (`+-single(double(far) x 1.4)`, its double read
    at 0x52fc78, the cone search reads the same value at 0x52fc80), slot-20 score,
    inclusive arc, ray and scoring;
  - otherwise the record objects of slots `0 .. g_numPlayers-1` (`g_players` + slot x
    0x4c30 + 0x43d8): skip none and dead (flag 8); aim at half heights; **strict** arc;
    the 2-D centre distance `d` must be below the best so far (starting at `far`, a
    distance, not squared), below `far + o.r` and at least `near - o.r`; a terrain ray from
    the creature's full height (mask 3) must give `t < 0` or `1 < t`; the nearest wins,
    ties to the earlier slot. **No enemy, team, charm or player-flag test**: whatever object
    the record names is taken. Unlike the enemy cone search, `far` *is* a cap here (the
    `d < far + o.r` test is never decisive, because `d < best <= far` comes first).
- **`Creature_knockbackTarget` 0x119d10** (c; speed): with a target, target +0x2e8 = speed
  and +0x2e0 = `atan2_16(t.y - c.y, t.x - c.x)` (the bearing away from the attacker). No
  other test. The victim moves in its own `Creature_applyKnockback` (round 1 5.4).
- **0x118bf0** (c, frames) - name proposed `Creature_setAttackCooldown`: **nothing without
  a target**; unless the AI state +0x232 is 0x14, slot 27 (set state) with 0x10; then
  +0x318 (16 bits) = frames - so a corpse still gets the cooldown stored.
- **0x118b58** (c, frames, obj) - name proposed `Creature_setAttackCooldownOn`: nothing for a
  boss (`creature_bossRank` != 0) or a null obj; else `handle_clear(+0x234)`,
  `handle_link(+0x234, obj, obj)` (the target becomes obj), then as 0x118bf0. No direct
  caller was found by the disassembler's call count (Unknown who calls it; probably through
  a pointer).
- **`world_notifyObjectsNear` 0x11a2b8** (a, &pos, b; R): one box query of `pos +- R` on all
  three axes, limit 0x80; slot 12 `(a, &copy of pos, b; R)` of every object in list order,
  with no flag, class or distance test.

### 2.1 Which classes use which helper, and on which event

From `t3/research-anim` `docs/spec/creature-animation-dispatch.md` (sections 4 and 5,
*Executed* there) and `docs/monsters-2.md` (*Observed*): a class's swing state calls one of
these helpers on the tick its clip's event fires; the event tick follows that document's
rule 4.2 (`(n-1) x step <= 60 x seconds < n x step`, `step = speed x 0.99999994`).

| Helper | Classes (run-state consumers) | Note |
|---|---|---|
| `Creature_hitTargetInArc` | 36 states: Agony, Amphian, Bubo, CastBadger, Clockwork, FatCyclops, FemaleDarkElf, Hag, Minotaur, Orc, Tormentor, VampireLord, Warrior, Zek, Gnaw, Skelight ... | the target only, sight cone |
| `Creature_hitAllEnemiesInArc` | 39 states: Badger, Cazic, IronGuardian, Marr, Nightmare, Ogre, RedDragon, Tormentor, WarBoar, Zek ... | everyone in the 1.4 x far box, at once in box order |
| `Creature_hitTargetOrPlayerInArc` | 10 states: Arenabeast, Minion, AntQueen | falls back to **any** live player in the cone, ignoring teams |
| `Creature_hitTargetAtReach` | Arenabeast, SpiderQueen; Goblin state 6 (`docs/monsters-2.md`: on `ev & 3`, reach 36) | 3-D sphere of 60 at the reach point, no arc |

So the mask-0x1 (or 0x2) event decides **the tick**; the helper decides **who**, with the
geometry of the tick in which the event fires. A native port that fires the event one tick
late hits with the next tick's positions (Inferred from the order: the state switch runs
after `Creature_applyKnockback` and slot 23 in the same run, round 1 4.2).

## 3. Death and loot

### 3.1 `Creature_deadUpdate` 0x1108a0, the blood decal

*Executed* (`deadUpdate`, now the whole body). Round 1 refused the decal; it is:

with `events & 0x80`, object flag 2 clear, `0 < size` and hold 0, the **first** of the
creature-flag bits 0x1000, 0x2000, 0x4000, 0x40000 that is set picks decal kind 6, 3, 0xa
or 0; then **two own draws** (`GameObject_rand` on +0x44): angle = `s16(first)`, and
`decal_add(position + offset, angle, kind, 1; size + float(second % 10))` (unsigned
remainder). None of the bits: no draw. The decal itself is presentation; **the two draws
are simulation state** (the object's generator), so a port must make them even without
drawing decals. The sinking corpse and the delete test are round 1's.

### 3.2 `Creature_dropLoot` 0x10f2c8

*Executed* (`dropLoot`). Arguments (c, &pos, angle, filter; zOffset, throwSpeed,
goldScale, goldChance, qualityRow, itemChance). Every drop is one call of
`loot_generateDrops` 0x100d54 (&copy of pos, angle, filter or 0, forcePreset; the six
floats), which `tools/ref_items.py` models (executed in `docs/spec/items.md` 8). In order:

1. Nothing for creature flag 0x100000000, or for the `noloot` property (`obj_getPropInt`,
   key 0x52ffd8) outside PvP mode B (0x4f7120).
2. Eleven exact-class tests in this order, each `rtti_typeInfoEquals(typeid(*c),
   Class_typeinfo())`. The first class that matches makes its fixed calls and **returns**:

| Class (type-info getter) | Condition | Ordinary call | Richer calls (goldScale, goldChance, quality, itemChance) | Per player slot |
|---|---|---|---|---|
| SpiderQueen 0x3c4888 | | yes | (4, 1, 6, 2), (5, 1, 7, 2) | coin 0.5: (0, 0, 8, 2) |
| AntQueen 0x3c3c78 | | yes | the same | always forced: (0, 0, 8, 2) |
| UndeadKnight 0x3cc938 | | yes | the same | coin 0.5 |
| VampireLord 0x3cca98 | | yes | the same | coin 0.5 |
| Arenabeast 0x3c9330 | | yes | the same | coin 0.5 |
| SeaMonster 0x3cc568 | creature flag bit 0, else the next test | no | (4, 1, 5, 2), (5, 1, 6, 2) | coin 0.5: (0, 0, 7.5, 2) |
| CloudGiant 0x3ca4ac | word +0x3d8 != 0, else the next test | yes | (4, 1, 6, 2), (5, 1, 7, 2) | always forced |
| Minion 0x3cba24 | | yes | the same | always forced |
| MummyKing 0x3cc29c | | yes | the same | coin 0.5 |
| Innoruuk 0x3cb1a0 | | yes | (15, 1, 6, 2), (20, 1, 7, 2) | coin 0.5 |
| Zek 0x3ccd64 | | no | (4, 1, 4, 2), (4, 1, 5, 2), (6, 1, 7, 2) | coin 0.5: (0, 0, 8.5, 2) |

   "Ordinary" = the caller's filter and six numbers; richer and per-player calls pass
   filter 0 and the caller's zOffset and throwSpeed. A **coin** is one **own draw** of the
   creature per player slot `0 .. g_numPlayers-1` (`float(value) x 2^-16 < threshold`
   forces a preset item); "always forced" makes no draw.
3. Otherwise `creature_bossRank`: rank 2 adds the ordinary call, (4, 1, 6, 2), (5, 1, 7, 2)
   and a per-player coin 0.5 with (0, 0, 8.5, 2); else `creature_bossRank` is called **a
   second time**, and rank 1 adds (4, 1, 3, 1.5), (5, 1, 5, 1.5) and a coin **0.25** with
   (0, 0, 7, 1.5).
4. Then (rank 0, 1 or 2) a tint preset (s8 +0xa0 != 0) multiplies goldScale by 3 and
   qualityRow by 4, and the ordinary call is made **when creature flag bit 0 is clear**.
   So a rank-2 boss without bit 0 gets the ordinary call twice, and a rank-1 creature (bit 0
   is what makes rank 1, `docs/creatures.md`) never gets it (Inferred from `creature_bossRank`'s
   note in `symbols/`; the two tests are on the same bit, Observed here).

No shared draw is made by this function. The type-info getters and `rtti_typeInfoEquals`
are C++ runtime and stay call-outs in the model (they may lazily build descriptors; not
read). The virtual slot-0 call is made with whatever the previous call left in `a0`
(0x10f38c and its ten copies), which a typeid getter does not read (Inferred).

### 3.3 One corpse-phase class: Goblin, state 0x14

*Executed* (`goblinDeath`, the death branch and the shared head of `Goblin_setState`
0x26ccfc; every other state is refused by the model). After `Creature_filterState`
(executed in `ref_creature`; refused: return with +0x232 untouched) and clearing creature
flag 0x200:

1. without the `dead` property (0x546998): one box query of +-96 around the goblin,
   limit 0x80; with **3 or more** objects whose `flags & 0x68 == 0x28` (creature, dead,
   not a player) +0x488 = 1 - the corpse will sink and be deleted (Goblin_run state 0x14,
   `docs/monsters-2.md`); otherwise it stays;
2. unless object flag 2 (hidden): object flag **1 is cleared** (the corpse becomes solid
   again for a moment - Creature_processDamage set flags 9 before calling slot 27), and the
   weapon holder (+0x50) drops hand 1 then hand 2 (holder slot 11 with (hand, c, part table
   0x500448 + family x 0x80, 0));
3. the `dead` property again: set -> object flag 1;
4. the death clip (definition +0x44, flags 6, blend 0.3) - **one call whatever the pending
   flags**: both arms of the knock-back test at 0x26d514 make the same call;
5. unless creature flag 0x100000000: `Creature_dropLoot(c, position, facing, 0; 36, 2,
   1.8, 0.6, 2, 0.25)`, executed for real inside this entry point; then an archer (role
   +0x3d4 == 4) with an **own draw** below 6000 of 65536 and no `noloot` property drops the
   named item `arrows` (`loot_spawnNamedItem`);
6. slot 28 (`Creature_onDeath`, round 1 section 7) with 0; then +0x232 = 0x14.

### 3.4 Death across the classes executed so far

| Class (group in creature-animation-dispatch 5) | setState 0x14 | Corpse | Where executed |
|---|---|---|---|
| Skelight (own) | flag 2, effects, `obj_delete` at once; no loot, no slot 28 | none | `ref_arena_monsters` |
| Horsemen (root motion) | bit 41, the summoned Skelight killed, `Creature_dropLoot`, both hands dropped, clip, slot 28 | `Creature_deadUpdate` | `ref_arena_monsters` |
| Zek (root motion) | bit 41, `Creature_dropLoot`, weapon dropped unless one level, clip, slot 28 | `Creature_deadUpdate` | `ref_arena_monsters` |
| SmallSpider (steered) | flags 9, a decal and a clip by three own draws, slot 28; no loot | `Creature_deadUpdate` | `ref_monsters_1` |
| Gnaw (own) | effects and gut chunks; no loot | `deadUpdate` + `obj_delete` every tick | `ref_monsters_1` |
| Mosquito, Scorpion, Badger (root motion) | `Creature_dropLoot` (36, 2, ...) with own draws; Badger: flag 1 cleared unless hidden | `Creature_deadUpdate` | `ref_monsters_1` |
| Goblin (steered) | 3.3 | sinks in a crowd of 3 corpses | here |

Every corpse phase ends in `Creature_deadUpdate` (sinking by +0.35 a call and `obj_delete`
past the height, or `obj_delete` when the clip ended with hold 1) or in a class's own
delete; the object is destroyed in the next delete-list flush (round 1 section 7).

## 4. The destructor chain (virtual slot 1)

*Executed* (`gameObjectDtor`, `creatureDtor`, `skelightDtor`, `playerDtor`), with the
callees (iterator, handle functions, `AnimState_dtor` 0x171098, `light_dtor` 0x14a490,
0x202500, `objNames_remove` 0x14be58, `pool_free` 0x150470, `game_rebuildAlivePlayers`)
as recording stubs.

- **`GameObject_dtor` 0x14cf90** (o, flags): +0x48 = the GameObject table 0x5122a8. For
  n = 0, 1, ...: the n-th `name=` entry of the property list +0x2c is looked up **twice**
  (two identical scans; before each scan the key string at 0x5321b0 is lower-cased **in
  place**, one byte store per character), and `objNames_remove(value, o)` is called, until
  none is left; with no list (+0x2c == 0) no scan. Keys are compared with `strncmp(entry,
  key, 4)` and `entry[4] == '='`, so `Name=` (capital) is not removed. Then
  `handle_clear` of +8 (grid), +4 (run list), +0 (every handle to it) and `pool_free`
  when bit 0 of flags is set.
- **`Creature_dtor` 0x117128** (c, flags): +0x48 = the Creature table 0x50cc58 (from here on
  a virtual call reaches the base class, not the derived one); each attached spell of
  +0x364 (iterator, mask 0): **spell slot 1 with 3** through the spell's own table at
  +0x14, a node with object word 0 passed over; `iter_end(2)`; `handle_clear` +0x364,
  +0x360; 0x202500(+0x320, 2), a destructor that frees only with bit 0 - nothing here;
  `handle_clear` +0x2e4, +0x238, +0x234; `AnimState_dtor(+0x114, 0)`; `GameObject_dtor(c,
  0)`; `pool_free(c)` when bit 0.
- **`Skelight_dtor` 0x3cc67c**: +0x48 = 0x5174b0; `Creature_dtor(c, 0)`; `pool_free` when
  bit 0. (The derived destructor frees; the base destructors are called with 0.)
- **`Player_dtor` 0x1a1bb8** (P, flags): +0x48 = 0x511308. **Unless `g_inGhostOp`**
  (0x402795): for an ordinary player (+0x462 == 0) record +0x43d8 (the object pointer) =
  0, for a display-only player (+0x462 != 0, `docs/player.md`) the byte 0x4ef360 = 0
  instead (meaning Unknown); in both cases the five record words **+0x43dc ... +0x43ec** =
  0 (meaning Unknown). Then - **also during a ghost operation** -
  `game_rebuildAlivePlayers`; `handle_clear(+0x588)`; `AnimState_dtor(+0x560, 2)`;
  `light_dtor(+0x504, 2)`, `light_dtor(+0x4c8, 2)`; `handle_clear(+0x4b8)`; the array of
  five 0x18-byte elements at +0x3d0 destroyed in reverse: `handle_clear` of +0x438,
  +0x420, +0x408, +0x3f0, +0x3d8; `Creature_dtor(P, 0)`; `pool_free` when bit 0.

Round 1's `Runtime._slot1` clears the creature heads in the order executed here
(+0x364, +0x360, +0x2e4, +0x238, +0x234, then +8, +4, +0) and refuses a creature with
attached spells and any player; it stays as it is. Test
`test_creature_chain_order` pins the executed order.

## 5. What was run

- `python3 tools/difftest_combat_monsters.py <your SLUS_209.73>` (seed 20973, 3,000 cases
  per entry point): see the table. Refused = cases the model declines as outside its
  domain (Goblin states other than 0x14 after the filter); they are not run.

| Entry point | Compared | Mismatches | Instructions executed |
|---|---|---|---|
| `canSeePoint` | 3,000 | 0 | 117 of 117 |
| `canSeeObjEdge` | 3,000 | 0 | 148 of 149 |
| `canSeeTargetIn` | 3,000 | 0 | 19 of 20 |
| `findPlayerInCone` | 3,000 | 0 | 322 of 322 |
| `hitTargetAtReach` | 3,000 | 0 | 90 of 90 |
| `hitTargetInArcEdge` | 3,000 | 0 | 58 of 58 |
| `hitTargetOrPlayerInArc` | 3,000 | 0 | 76 of 77 |
| `knockbackTarget` | 3,000 | 0 | 20 of 20 |
| `setCooldown` | 3,000 | 0 | 24 of 24 |
| `setCooldownOn` | 3,000 | 0 | 38 of 38 |
| `notifyObjectsNear` | 3,000 | 0 | 77 of 77 |
| `gameObjectDtor` | 3,000 | 0 | 166 of 170 |
| `creatureDtor` | 3,000 | 0 | 65 of 65 |
| `skelightDtor` | 3,000 | 0 | 24 of 24 |
| `playerDtor` | 3,000 | 0 | 86 of 91 |
| `deadUpdate` | 3,000 | 0 | 171 of 174 |
| `dropLoot` | 3,000 | 0 | 1276 of 1318 |
| `goblinDeath` | 2,531 | 0 | 233 of 613 |

  **53,531 cases compared, 0 mismatches**; 469 refused (all `goblinDeath`). No entry point
  draws the shared seed.

  A quick run with `--seed 7` also passes (300 cases per entry point, 0 mismatches).
  Instructions not executed are `nop`s, the `cxx_throwBadTypeid` arms of the eleven class tests in `Creature_dropLoot` (only for
  a null creature), and in `Goblin_setState` every state but 0x14.
- Negative controls (made by hand while writing, not kept as tests): with
  `set_cooldown` emptied, the zero-player result of `find_player_in_cone` forced, the
  spell call or the key lower-casing removed from the destructors, or Zek's per-player
  quality changed from 8.5 to 8, the difftest reports failures in the affected entry
  points only.
- `python3 -m unittest tools/test_ref_combat_monsters.py`: 14 synthetic tests.
- Not run: anything on a console, PCSX2 or the live rig.

## 6. For the native client

`MonsterCombatModel` adds the methods below to round 1's model; `MonsterRuntime` is round
1's `Runtime` with this model, so the helpers work inside the shared world (loot generation
and type-info tests are refused there: loot objects are outside the contract's domain).

| Method | Original |
|---|---|
| `can_see_point(c, pos, facing, arc, near, far)` | 0x10c238 |
| `can_see_obj_edge(c, obj, facing, arc, ray_mode, near, far, lead)` | 0x10c5b8 |
| `find_player_in_cone(c, facing, arc, near, far)` | 0x10ca70 |
| `hit_target_at_reach(c, lo, hi, attack, flags, desc, reach)` | 0x1196e8 |
| `hit_target_in_arc_edge(c, facing, arc, lo, hi, attack, flags, desc, near, far)` | 0x119850 |
| `hit_target_or_player_in_arc(...)` (same arguments) | 0x119a20 |
| `knockback_target(c, speed)` | 0x119d10 |
| `set_cooldown(c, frames)`, `set_cooldown_on(c, frames, obj)` | 0x118bf0, 0x118b58 |
| `notify_objects_near(a, pos, b, radius)` | 0x11a2b8 |
| `dead_update(c, events, offset, hold, size)` (whole body) | 0x1108a0 |
| `drop_loot(c, pos, angle, filter, z, throw, gs, gc, q, ic)`; table `LOOT_CLASSES` | 0x10f2c8 |
| `goblin_set_state(c, state)` (death only) | 0x26ccfc |
| `gameobject_dtor`, `creature_dtor`, `skelight_dtor`, `player_dtor` (obj, flags) | 0x14cf90, 0x117128, 0x3cc67c, 0x1a1bb8 |

Rules a port must keep: the own draws of the blood decal and the loot coins advance the
creature's generator; `hitTargetOrPlayerInArc` and `findPlayerInCone` ignore teams;
`hitTargetAtReach` has no arc and a 3-D sphere; the cooldown setters do nothing without a
target (or for a boss); `Creature_dtor` resets the table before the spells are ended.

## 7. Corrections to round 1

| Where | Was | Is | Evidence |
|---|---|---|---|
| `docs/combat-runtime.md` 6.1 "Other helpers" | the two cooldown setters each call slot 27 with 0x10 before storing +0x318; 0x118b58 also relinks the target | 0x118bf0 does nothing without a target and skips slot 27 (not the store) in state 0x14; 0x118b58 does nothing for a boss or a null object, then relinks and acts as 0x118bf0 | Executed (`setCooldown`, `setCooldownOn`) |
| `docs/combat-runtime.md` 6.1 | `hitTargetAtReach`: the target within 60.0 of a point `reach` ahead | the same, in 3-D, with no arc, ray or enemy test | Executed |
| `docs/combat-runtime.md` 8.3 | `creature_findPlayerInCone`: nearest live player in the cone, strict arc, 2-D distance, a clear ray | the same, plus: `far` caps the distance (unlike the enemy cone), the ray starts at full height, and "player" is whatever object the record names (no flag test) | Executed |
| `docs/combat-runtime.md` 2.2 | Player_dtor "clears the record's object pointer (when +0x462 is 0) ... two lights" | under `g_inGhostOp` no record write at all; a display-only player clears 0x4ef360 instead; five more record words +0x43dc.. are zeroed; an `AnimState` at +0x560 is destroyed before the two lights | Executed (`playerDtor`) |
| `docs/combat-runtime.md` 2.2 | `GameObject_dtor` ... and `pool_free` when bit 0 | the derived destructors call their bases with 0 and free last themselves; `Creature_dtor` and `GameObject_dtor` each first store their own table; the spells are ended through their table at +0x14 | Executed |
| `docs/combat-runtime.md` 13 | `Creature_deadUpdate`'s decal path not modelled | modelled (two own draws) | Executed (`deadUpdate`) |
| `docs/monsters.md` / `docs/data-tables.md` 2 | "rank 2 adds two richer calls" | three calls (the ordinary one first) plus per-player; a second `creature_bossRank` call for rank 1; the ordinary call at the end also for rank 2 unless creature flag bit 0 | Executed (`dropLoot`) |

Proposed symbol lines (for whoever edits `symbols/`):

```
00118bf0	Creature_setAttackCooldown	(c, frames): nothing without a target; slot 27 with 0x10 unless state 0x14; +0x318 = frames. Executed (difftest_combat_monsters)
00118b58	Creature_setAttackCooldownOn	(c, frames, obj): nothing for a boss or null obj; target handle = obj; then as 0x118bf0. Executed
00202500	Creature_attachState_dtor	(p, flags): frees p only when bit 0 is set; Creature_dtor calls it on +0x320 with 2. Observed (name Inferred)
```

and notes to add: `creature_findPlayerInCone` 0x10ca70 "far caps the distance; any object
in g_players[i]+0x43d8; charmed: inline copy of findEnemyInCone" (Executed);
`Creature_dropLoot` 0x10f2c8 "eleven class tests (LOOT_CLASSES), boss ranks, tint x3/x4,
ordinary call unless cflag bit 0; own-draw coins" (Executed); `Player_dtor` 0x1a1bb8 "also
during g_inGhostOp: rebuild alive, handles, lights" (Executed).

## 8. Not done, not known

- The other states of `Goblin_setState`, and the set-states of the classes not executed
  anywhere yet (the 5.1 and 5.2 lists minus section 3.4).
- `loot_generateDrops` is not composed into `MonsterRuntime`: drops are pool objects with
  physics, outside the contract's domain (ref_items models the generator).
- Who calls 0x118b58 (no direct caller found) - Unknown.
- The meaning of the byte 0x4ef360 and of record words +0x43dc ... +0x43ec cleared by
  `Player_dtor` - Unknown; settle by a field cross-reference (`tools/fieldxref.py`).
- The type-info getters' lazy initialisation is not modelled (call-outs).
- Nothing was run on a console, in PCSX2 or on the live rig.
