# Player tick: `Player_run` 0x1a5030, one tick in order

`Player_run` (0x1a5030–0x1ac7a4, 7,646 instructions, virtual slot 4 of `Player`) is the
per-tick simulation of one player. It runs once per simulated tick for every real player
and, on each machine, extra times on the prediction copy of that machine's own player
(object flag 0x20000).

This document is the prose of `tools/ref_player.py`. Every statement in sections 1–8 was
read from the instructions at the address given and is **Observed**; the parts that
`tools/difftest_player.py` also *executed* against the original and found equal are listed
in section 11 with their coverage. Nothing here was run on a console or in an emulator of
the whole machine; the executing tool is the instruction interpreter `tools/ee_emu.py`
(`docs/issues/dynamic-tests.md`).

## 0. Conventions

- `P` is the player object, `R` the player record `g_players + slot × 0x4c30`
  (`slot` = `P+0x3c8`), `pad` the pad the tick chose (section 2), `frame` = `g_simFrame`
  0x44fdcc, `since` = `frame − P+0x448` (frames since the current action started).
- Floats are given as bit patterns with the nearest decimal: the game's literals are
  truncated, not rounded (0.1 is 0x3dcccccc). "×" and "+" on floats mean one R5900
  single-precision operation in the order written.
- "real only" = skipped when `P+0xc & 0x20000` (the prediction copy). "copy too" = no such
  test.
- The animation state is at `P+0x114`: track count `P+0x118` (s8), a second count
  `P+0x119`, flag word `P+0x11a`, then 0x20-byte tracks from `P+0x11c`
  (+0 animation, +8 the value the cast and block code compare with 1.0 and 10.0,
  +0x10 weight, +0x14 weight change per tick, +0x18 time). `top(k)` below means
  `P + count × 0x20 + k`, the addressing the code uses for "the last track" (and, with
  `k` = 0xf0, the one before it).
- `anim(k)` is a pointer from the player's animation table: `*(P+0x24) + class × 0x68 + k`,
  `class` = `R+0x4a86`, the weapon animation class (0 one-hand, 1 and 2 two-hand kinds,
  3 long, 4 bow, 5 unarmed, 6 thrown, 7 dual).
- `selected` is the ability record of the button pressed last: `R+0x4a60` (0 or 1) picks
  the index byte `R+0x4a84` or `R+0x4a85`; record = `R + 0x4440 + index × 0x68`. A record is
  a *Skill-object* record when its name equals the string at 0x535e30 (compared with
  `libc_strcmp` before every use), otherwise an *older* record handled by code inside
  `Player_run`. `skill(rec)` = `g_skillTable[rec+0x20]`; its virtual table is at skill+0x60
  (slot 1 canUse, 2 cast, 5 mana cost, 10 getStat); skill+4 flags, +8 kind, +0xc recast.
- `rank(id)` is Player virtual slot 39, `enemy(o)` slot 20, `turnTo(point)` slot 26,
  `aimAt(point)` slot 17.
- Button masks are per slot: attack 0x41b980, ability A 0x41b990, ability B 0x41b9a0,
  block 0x41b9d0, potion A 0x41ba10, potion B 0x41ba20, swap 0x41ba30.
- Constants that only feed presentation callbacks (the colours of the `LightEffect` calls,
  the particle definitions) are not repeated here; they are in `tools/ref_player.py` at
  the same place.
- A **shared draw** advances `g_randSeed` 0x404464 (`s = s × 0x19660d + 0x3c6ef35f`, value
  `s >> 16`). An **own draw** is `GameObject_rand` on `P+0x44`. The third generator
  0x404468 is per machine.

## 1. Entry (0x1a5030–0x1a5624)

1. **Breath puff.** When the level flag word 0x44fe08 has bit 0x100, and
   `(frame ^ P+0x230) & 0xe0` is 0, and one own draw is even: own draws in threes
   (`2u − 1` each, `u = draw × 2⁻¹⁶`) until the point lies in the unit ball, one more own
   draw `h`, then `fx_spawn(0x11, P.pos + 2·point + (0, 0, P+0x20 + h × 2⁻¹⁶ × 12.0))`.
   Copy too. Own draws only.
2. `Creature_run(P, P+0x544)`, then `Creature_applyKnockback(P, 1.0)`.
3. `P+0x228` = record hit points `R+0xac`.
4. **White light** (the light object at `P+0x4c8`): range = `0x4f83f4 × 240.0`, times
   0x3f28f5c2 (0.66) when `g_alivePlayerCount` 0x4f8420 is exactly 2; stored at `P+0x4e4`
   and `+0x4ec`, `1 / range²` at `P+0x4f0` and `+0x4e8` (a zero range stores 0x7fffffff).
   Position `P+0x4f8..` = `P.pos + (0, 0, 64.0)`. `light_relink(P+0x4c8)`,
   `light_unlink(P+0x504)`.
5. **Hit immunity** `R+0x4c27` (u8): minus 1, floored at 0. Real only.
6. **Spawn protection** `P+0x4b4` (s16): when non-zero, minus 1, and below 20 the object
   flag 2 is cleared. Copy too.
7. **Idle voice.** Only with `R+0xac > 0`. The counter `P+0x4b0` is zeroed when
   `net_getCamFlag(slot)`, or `g_cutsceneActive` 0x44fcd0, or `game_isFrozen()`, or the
   **held word of the slot's own lockstep pad** (0x41bfe0 + slot × 0x58 — the real pad,
   whatever section 2 chooses) is non-zero. Otherwise it goes up by 1, and when it exceeds
   `P+0x4b2`: `player_voice(slot, 1)`, counter 0, **one shared draw** `d`,
   `P+0x4b2 = ((d % 30) + slot × 45) × 60 + 3600`.
8. **Ability recast** `P+0x4ae` (s16): minus 1 while positive.
9. **Low-health rumble.** Offline always; in a net game unless (`g_medalMission` 0x4f713c
   and `g_medalDialogTicks` 0x4f7114 both non-zero) or `memcard_isBusy()`. Then, with
   `0 < hp` and `hp / maxhp < 0x3ecccccc` (0.4): `pad_rumble(slot, 0x3df5c28f, 1.0)` when
   `frame & 0x3f` is 0 and `pad_rumble(slot, 0x3db851eb, 1.0)` when it is 20. Nothing else
   depends on this block.
10. **Scripted control.** When `P+0x231` (s8) is non-zero the tick ends here: state 0 runs
    `Player_animStep(P, 1.0)`; state 1 runs it, `Player_footstep(P)` on event bit 1, and
    `Creature_moveToDest(P)`; then `P+0x488 = 0` and return. No damage, no regeneration,
    no countdowns.
11. `P+0x4c4 = 1.0`. When `P+0x464` is 0 (written by `Player_draw`: 0 = drawn last frame)
    and object flag 8 is clear: `Player_weaponTrails(P)`.

## 2. Which pad the tick reads (0x1a5640–0x1a5764)

The all-zero pad `g_zeroPad` 0x8667f0 replaces the slot's lockstep pad
(0x41bfd8 + slot × 0x58; +8 held, +0xc pressed, +0x14/+0x18 stick) when the first of
these holds, tested in this order with short-circuit:

1. `g_menuInputLockout` 0x41b4fc ≠ 0 **and** offline;
2. `dialog_isOpen()`;
3. `P+0x4b4` ≠ 0 (spawn protection);
4. `g_recallCountdown` 0x41b51d ≠ 0;
5. `g_medalDialogTicks` ≠ 0;
6. `net_getCamFlag(slot)`;
7. `task_isRunning` of the task named at 0x535eb8, then of the one at 0x535ec8;
8. `net_isSlotActive(slot)` is 0;
9. object flag 0x400000;
10. word 0x503890 ≠ 0;
11. byte 0x4f66c8 ≠ 0;
12. `R+0xac ≤ 0`.

Everything below that says `pad` means the result. The idle voice (1.7) and
`Player_weaponSwapInput`'s caller gate do not use it for their own tests.

## 3. After the pad (0x1a5768–0x1a5b10)

1. `Player_idleFidget(P, pad)` (section 9.1): **one shared draw on every tick in which the
   player has exactly four animation tracks** and the stick is at rest or no fidget is
   running.
2. When `dialog_isOpen()` and `R+0xac > 0`: `P+0x38 = angle_approach(0.125, −1, −1,
   P+0x38, fn_22fbd0(P.pos))` (turn toward the speaker).
3. **Aura globals** (read only by drawing and by the tail's light, written by the copy as
   well): `g_playerAuraFade[slot]` 0x4d8aa0 += `g_playerAuraFadeRate[slot]` 0x4d8a90,
   clamped to [0, 1]; `g_playerAuraLevel[slot]` 0x4d8a40 += 3 × `g_playerAuraDir[slot]`
   0x4d8ab0, clamped to [0, 0x50].
4. `P+0x4c0 = P+0x4bc = 0` (last movement velocity).
5. **Minimum time between attacks** `P+0x48c`: 0x3ea8f5c2 (0.33) with no primary weapon
   (`R+0x4434 + 4 × R+0x4a7c`) or one whose definition class (+0x1e) is 4, else 0x3e199999
   (0.15).
6. **Potion buttons** (only with `R+0xac > 0`; pressed word of `pad`): potion A →
   `Player_usePotion(P, 0, 0, 0, −1)`; potion B → `Player_usePotion(P, 1, 0, 0, −1)` unless
   `g_levelName` 0x41b721 contains the string at 0x535ed8. No copy test here; the function
   returns at once for the copy (9.7).
7. **Which ability button is "the" ability button** (real only). `R+0x4a80` holds a pad
   mask; if it equals neither of the slot's two ability masks it is zeroed. Unless the
   state is 5: ability A pressed → `R+0x4a80` = mask A, `R+0x4a60 = 0`; else ability B
   pressed → mask B, `R+0x4a60 = 1`.
8. **Status counter 2 costs class 0 mana** (copy too): when `R+0x50` is 0 and `P+0x374` ≠ 0
   and the state is not 0xc: `mana −= maxmana × 0x3ada740d` (0.0016666); at or below 0 the
   mana becomes 0 and `P+0x374 = 0`.

## 4. Regeneration, kill plane, damage, the swap / interact gate (0x1a5b14–0x1a5c20)

All of this section is skipped when object flag 8 (dead) is set.

1. `Player_regenHealth(P)`, `Player_regenMana(P)`, `Player_tickEnchantTimers(P)` — each
   returns at once for the copy (9.4–9.6).
2. **Kill plane.** When `g_killPlaneZ` 0x4f7188 > 0xc7afc800 (−90000) and `P.z` is below
   it: object flag 2 is set unless `g_debugInvulnerable` 0x44f20c; `P+0x2dc = 0`;
   `P+0xc8 = 0x49742400` (1,000,000 pending damage). Copy too.
3. `Player_processDamage(P)`. Copy too. (A callback of the model: it is where the state
   becomes 3 or 4.)
4. **The gate.** In this order: `g_paused` 0x41b4f4 = 0, `g_menuInputLockout` 0x41b4fc = 0
   (no network test here — this is D26), `dialog_isOpen()` = 0, `net_getCamFlag(slot)` = 0,
   not the copy. Then `Player_weaponSwapInput(P, pad, 0)` (9.8, which always ends in
   `Player_recalcDamage`), and then, only when `g_spellSelectorHeld[slot]` 0x41b818 is 0
   (K1), `Player_interact(P, pad, 0)`.

## 5. Instant abilities and the block request (0x1a5c24–0x1a5e7c)

`instant` is a local of the tick: 0, a button mask, or −1.

- Skipped (instant = 0) when no record is forced (`P+0x488` = 0) and `pad.held & 0xf000`.
- Otherwise, when `P+0x4ae` ≠ 0: `P+0x488 = 0`, instant = 0.
- Otherwise, for the forced record, or else for ability A then ability B when that button
  is in `pad.pressed` (record index from `R+0x4a84 + i`): if the record's kind byte (+0x25)
  is 7 and it is a Skill-object record: `canUse(P)` (0 → `P+0x488 = 0`, stop);
  `cost = manaCost(rank(id))`; `cost > mana` → `player_voice(slot, 4)`, `P+0x488 = 0`,
  stop; else instant = −1 for a forced record, the button's mask otherwise, stop. A forced
  record of another kind stops the loop; an older record of kind 7 stops it too.
- **Block request** `P+0x454` = 0; then 1 when the block button is in `pad.held`, level
  flag 0x10000000 is clear and `player_canBlock(slot, state)` (9.2).

## 6. The action-state switch (0x1a5e80, jump table 0x536260)

States 0xf and above do nothing. `move(m)` = `Player_move(P, m, pad, 0)`;
`step(s)` = `Player_animStep(P, s)` returning event bits.

### State 2 — neutral (0x1a6c30)

`P+0x484 = 0` first, always.

**A. Ability start** — only when `P+0x482` ≠ 0 (on the ground). `rec` = the forced record
or `selected`; if `R+0x4a60` is neither 0 nor 1 and nothing is forced the switch is left
(the tail still runs).

1. `start` is set when the recast `P+0x4ae` is 0, level flag 0x10000000 is clear, and:
   for a record of kind 2, (forced or the ability button is in `pad.pressed`) and the
   track count is at least 4; for any other kind, (ability button in `pad.held`, or
   `P+0x450` ≠ 0, or forced) and `mana > 1.0`. With the level flag set and the other
   conditions met the only effect is `player_voice(slot, 6)`.
2. **Offline only**: `g_spellSelectorHeld[slot]` ≠ 0 with nothing forced clears `start`
   (0x1a6dec; in a net game the word is not read here).
3. `start` is cleared when the record's id is −1, when `R+0x4bc9` ≠ 0, when the global
   0x4f7128 is set (with a HUD message for nobody in particular), for id 0x25 with weapon
   class 4 or 6 (HUD message for the slot), and for a cost field (+0x2c) of exactly 999.0
   when `mana < maxmana`. `P+0x450 = 0` in every case.
4. With `start` and `rec+0x24` ≠ 0: cost = `manaCost(rank(id))`, halved when the skill's
   kind (skill+8) is 1, for a Skill-object record; `(passive 0x20000 level − 1) ×
   0x407fffb0 + 26.0` for older id 0x25; else `rec+0x2c`. If `cost ≤ mana` or cost = 999.0:
   - Skill-object, kind byte 7: `Player_castSkill(P, rec)` now (9.9).
   - Skill-object, kind byte 8: `canUse(P)` → `P+0x484 = rec`; refused → `P+0x484 =
     P+0x488 = 0`.
   - Skill-object, any other kind, and older ids not listed below: `P+0x4ae = rec+0x22`,
     `player_voice(slot, 0xb)`, **state 5**, `P+0x448 = frame`; the switch is left.
   - Older id 0xe (war cry), only when `P+0x374` is 0: animation by weapon class,
     `P+0x374 = 0x30c`, **state 0xc**, `P+0xf0 = frame`; left.
   - Older id 0x25 (heavy attack), only when `P+0x44c` is 0 and the track count is below 6:
     a sound, `P+0xb0 = 0x40333333`, `P+0x470 = 0x3f5b645a`, `P+0x460 = 0`,
     `P+0x46c = 0`, `P+0x448 = frame`, `P+0x44c = 2`, `mana −= cost`, the weight fields of
     tracks 1.. cleared, `anim_startBlendInOut(anim(0x64), 0x812)`, a `LightEffect` for the
     real player (`pool_new(0xbc)`), **state 1**. The code then falls into part B.
   - Older id 0xc: **state 10**, `P+0x448 = frame`, an animation with flags 10.
   - Older ids 4, 5, 6, 0x13, 0x12 (arrows): with a weapon class other than 4 and a
     primary weapon in set 1, `R+0x4a7c = 1` (**a record store with no copy test**); with a
     bow and an ammunition pointer `R+0x4410`: `P+0x44c = 1`, `P+0x480` = 1, 2, 3, 5, 6 by
     id; low-ammunition notice; `P+0x4ae = rec+0x22`.
   Otherwise (`cost > mana`): `player_voice(slot, 4)`.

**B. Attack, shot, block** (0x1a76c0).

1. `mask` = the attack mask, or `R+0x4a80` when `P+0x480` ≠ 0 or `P+0x484` ≠ 0. When the
   ability button is not held and nothing is forced, `P+0x480 = 0`.
2. With level flag 0x10000000: `player_voice(slot, 6)` when `pad.held & mask`, or block is
   in `pad.pressed`, or a forced record waits in `P+0x484`.
3. The attack path is taken when (flag clear and instant = −1), or (forced and `P+0x484`
   ≠ 0), or `pad.held & (mask | instant)`. **The level flag does not stop it.** Otherwise
   the block path: when `P+0x454` is 1, or block is held and the flag is clear:
   `player_canBlock` → **state 8**, else a HUD message for the slot.
4. Attack path:
   - Record class (`R+0x50`) 0, 2 or 3 with weapon class 4 or 6: **one own draw**; when
     `draw × 2⁻¹⁶ ≤ 0.1` or there is no ammunition (pointer null or count < 1):
     `Player_findTarget(P, 72.0)`; with a target, `turnTo(target)`, and unless one of two
     named animations is already playing: `P+0x448 = frame`, and when the target is nearer
     than 60.0 (3-D): **state 1** with the bow or thrown-weapon melee animation (flags
     0x802; `P+0x470 = 0x3f666666` for the bow); left.
   - Global 0x4f7128 set: only a thrown weapon whose item name passes
     `str_prefixDiffers(name, 0x535fd8) == 0` may go on; otherwise a HUD message and no
     attack.
   - Weapon class 6: when `pad.held & mask`, or forced with `P+0x484`: **state 0**,
     `P+0x480 = 7`.
   - Weapon class 4: unless `P+0x44c` = 0, instant ≠ −1, not (forced with `P+0x484`) and
     `pad.held & (mask | instant)` = 0: `P+0x44c = 0`, then
     - no ammunition pointer: the real player scans the 64 cells of bag 0 for an item
       whose definition slot byte (+0x1c) is 8 and stores the **last** match in
       `R+0x4410`; state stays 2;
     - else, unless forced with `P+0x484`: when `pad_buttonValue(pad, attack mask)` and
       `pad_buttonValue(pad, R+0x4a80)` are both below 0x3e051eb8 (0.13): track 1..
       weight rates = 0xbdeeeeee, `move(1)`, `step(1.0)`, left;
     - else `P+0x480 = 0` when attack is held, **state 0**.
     Real only: the low-ammunition notice (count 1..20: HUD notice 6 for 240 frames) and
     with no ammunition `player_voice(slot, 5)` and HUD notice 3 for 120 frames.
   - Any other weapon class: when `P+0x48c × 60.0 ≤ since` and (`P+0x44c` ≠ 0, or
     instant ≠ 0, or attack is in `pad.pressed`): **state 1**.
   - If the state is now 0 or 1: `P+0x448 = frame`, `P+0x470 = 0x3fcccccc` (1.6),
     `P+0x461 = 1`, `P+0x44c = 0`, `P+0x460 = 0`, `P+0x46c = 0`, tracks 1.. cleared,
     `anim_startBlendInOut(anim(0x74), 0x12 for state 0 / 0x802 for state 1)`; left.
5. `Player_tryBlockMove(P, pad)` (9.3). `R+0x4a5c += 1/60`; at 0.25 or more it becomes 0.5
   (copy too; nothing reads it). `e = move(0)`; `Player_footstep(P)` when `e & 5`.

### State 1 — melee (0x1a9678)

1. `gap = frame − P+0x45c`; `P+0x45c = frame`; `gap > 60` → `P+0x458 = frame`.
2. Combo length by weapon class: 4 (class 2), 7 (1), 9 (3), 2 (5), 7 (others), and 1 for a
   heavy attack (`P+0x44c` = 2), which also stores eight 16-bit colour words at
   `P+0x90..0x9e` (0x8e, 0x3a, 0x52, 0x40 twice). Two tables are copied to the stack; the
   float one is divided by the speed and never read; of the integer one only entry 4 is
   used, the sweep frame: 0x7f for class 2 (divided by the speed), 0x5e raw for a heavy
   attack with a class-2 weapon.
3. **Haste**: with a primary weapon, the larger of `modifier 0x14 × 0x3d3851eb` (0.045) of
   the primary and of the item in equipment slot 1 (`R+0x43f4`); halved for class 7; plus
   0.25 when `P+0x374` ≠ 0 and 0x3dcccccc when `P+0x37c` ≠ 0.
4. **Speed**: for every alive player (`g_alivePlayers`), the first of `SpellAncestralCall`
   / `SpellBattleCry` on that player's object, asked whether it affects `P`
   (`SpellAncestralCall_queryFor` / `SpellBattleCry_affects`); speed = the largest
   returned factor, 1.0 with none. For record class 5 with `rank(0x47) > 0`: speed ×=
   `SkillBerserkerRage_swingFactor(skill 0x47, rank, R, frame − P+0x458)`. speed += haste.
   `step(speed)`. Then the slow amount `P+0x2fc` in 1..60 scales it:
   `speed × ((60 − slow) × 0x3c888888)` — at 60 the speed is 0 and every frame threshold
   below becomes 0x7fffffff.
5. **Target.** On frame 1 of the swing, or without a target handle `P+0x234`:
   `world_collectObjectsInBox(P.pos ∓ (r, r, 72), …, 256)` with r = 48 (58 for classes 1
   and 3); `handle_clear(P+0x4b8)`. For each object other than `P` that is hittable —
   flags & 0x49 = 0, not flag 0x1000000, and for a creature (0x20) `+0x312` = 0 and not
   bit 0x4000000 of `+0xa8`; or, in PvP mode A, a creature that `enemy()` accepts — with
   the 2-D unit direction `n` to it and the facing `f` = (cos, sin)(P+0x38): if
   `n·f ≥ 0`: with a class-2 weapon on combo step 3 it is linked into `P+0x4b8`; if
   `n·f ≥ 0.5` and `d = distance − target+0x1c < r`, score `d − n·f × 32`, the lowest
   score (ties: the later one) wins. `handle_clear(P+0x234)`, link the winner; a creature
   winner gets its slot 12 called with kind 3 (**copy too**).
   With a target and `since ≤ 0x41ed1eb7` (29.64): `turnTo(target)`.
6. `move(4)` while `since ≤ 0x3eddb22d × 60` (0.433 s; 0x3f1126e9 = 0.567 s for a heavy
   attack), else `move(3)`.
7. **Hit frame** (t = `since` after the move). Offline: `t == trunc(0x418028f5 / speed)`
   (16.02). **Net game: `t == 1` and `P+0x55c == 0`**; `P+0x55c` then counts down by 1.
   A class-2 weapon instead sweeps from `t ≥ sweep frame`: every node of `P+0x4b8` whose
   bearing relative to the facing has been passed (`(s16)(0x4000 − facing − atan2) <
   (s16)(0x4000 − (t − sweep) × 0x708)`) gets `Player_meleeHit(P, target, 0, 0)` and is
   removed; `P+0x44c = 0`. Otherwise, on the hit frame: `Player_meleeHit(P, target, flag,
   0)` when there is a target (`flag` = 1 offline, 0 in a net game), `P+0x44c = 0`.
8. **Swing sound and shout** on t = 6 and t = 9: offline always; **in a net game only when
   `net_isLocalSlot(slot)` is 0 or `P` is the copy**. The sound variant is one draw of the
   third generator 0x404468. Nothing else depends on this.
9. **Combo window**: `window = 0x41b028f5 − trim` (22.02; 0x418ced91 = 17.616 for class
   7), `trim = min(haste × 60 × 0.5, 0x418b3332)`.
   - Neither attack nor a ready instant ability in `pad.pressed`, and instant ≠ −1: when
     `P+0x454` is 1, or block is in `pad.pressed` with the level flag clear:
     `player_canBlock` → **state 8**, else a HUD message for nobody.
   - Otherwise: a ready instant ability is cast now (`Player_castSkill`; a forced one
     clears `P+0x488`). Then, when `window / speed < since`: combo step `P+0x460` + 1
     (capped at length − 1), `P+0x44c = 1` unless 2, `P+0x454 = 0`,
     `Player_pickAttackAnim(P, class)` (**one shared draw**, 9.10), the next attack
     animation (`anim_start`, flags 0x802), `P+0x470 = 0x3fcccccc`, `P+0x448 = frame`.
     Classes 4 and 6 only do this after 39.6 frames and with a target from
     `Player_findTarget(P, 60.0)`.
   - When `window / speed ≤ since` and `selected` has id 0x25 and its button is in
     `pad.pressed`: `P+0x450 = 1`.
10. **End of the swing**: when (stick length > 0x3f4ccccc and `since ≥ 0x421d3332`
    (39.3)), or `P+0x470 × 60 ≤ since`, or `P+0x450` ≠ 0: `P+0x44c = 0`,
    `P+0xb0 = 0x3fb33333`, tracks 4.. faded, **state 2**, `P+0x448 = frame`.
11. `Player_tryBlockMove(P, pad)`.

### State 0 — ranged (0x1a80e0)

1. base = 22 frames, 11 when `P+0x480` is 7; **halved in a net game** (11, 5).
   speed = `1.0 + 2 × (modifier 0x14 of the primary × 0.045)`; `step(speed)`; the slow
   amount scales it as in state 1. `release = trunc(base / speed)`.
2. **Throw** (`P+0x480` = 7 with a primary weapon). `Player_findTarget(P, 300.0)`,
   `turnTo`, and a lead by the target's velocity when passive 0x200000 has a level. On
   `since == release`, real only: with `P+0x484` set, `Player_castSkill(P, P+0x484)`,
   `P+0x4ae = 0`. Otherwise **shared draw 1** (heading spread `% 0xa28 − 0x514`, unused
   with a target), **shared draw 2** (rise `% 40 + 40`, unused with a target), one own
   draw for the sound, a `playerProjectile` (`pool_new(0x1d0)`), the stack count
   (`R+0x43f8` item, +4) minus 1 and `inventory_removeItem` at 0; HUD notice 7 at 1..20.
3. **Bow** (otherwise), on `since == release` with an ammunition pointer: the release
   block. `Player_findTarget(P, 300.0)` and `turnTo`; **shared draw A** (spread
   `% 500 − 250`); `world_collectObjectsInArc(P.pos, facing, 340.0, 20.0)`, the first
   object `enemy()` accepts is the target; **shared draw B** (aim); **shared draw C**
   (pitch `% 60 − 30`); with a target **shared draw D** (pitch again, clamped to ±300);
   real only: the target creature's slot 12 with kind 2; ammunition left = count − 1 (real
   only), or − `getStat(2, rank)` of skill 0x2e when `P+0x484` is set and the record id is
   0x2e; with a bow item: `script_runByName` of the hook named at 0x536030 (**copy too**),
   **shared draw E** (sound), then `Player_castSkill(P, P+0x484)` and `P+0x4ae = 0`, or a
   `MissileWeapon` (`pool_new(0x1c8)`, real only) of kind `P+0x480` and, for kinds 1, 2, 3,
   5, 6, `mana −= rec+0x2c` (**copy too**); `P+0x480 = 0`. Real only: the new count is
   stored, or at 0 the stack is removed and `R+0x4410 = 0`.
4. `player_recalcLoad(slot)`. Attack in `pad.pressed` with `since > 14` → `P+0x44c = 1`.
   `move(1)` offline, `move(6)` in a net game. When flag 0x10 of `P+0x11a` is clear:
   `P+0x3cc = 0` and, once `P+0x48c × 60 ≤ since`, **state 2**.

### State 5 — casting (0x1ab4f8)

`rec` = forced or `selected`, none when its id is −1. `step(1.0)`; `move(1)` offline,
`move(6)` in a net game.

- **Skill-object record.** Phase byte `P+0x47b`:
  - 0: `canUse(P)`; refused → `P+0x488 = 0`, **state 2**. Then
    `t = anim_findTrackByFlag(P+0x114, 0x8000)`; with no such track: the cast animation
    (`anim_start(anim(0x6c), 0x8003)`, not for skill kind 6), phase 1.
  - 1: when the skill's kind is 6, or track `t`'s +8 value has reached the **cast point —
    1.0 offline, 0.5 in a net game**: phase 2, `Player_castSkill(P, rec)`, `P+0x488 = 0`;
    for skill kind 0 the track's weight is capped at 1.0 and set to fall by 0xbd6eeeee.
  - 2: a record of kind 1 pays `manaCost(rank) × 1/60` per tick (copy too); when flag
    0x8000 of `P+0x11a` is clear: phase 0, **state 2**, `P+0x488 = 0`.
- **Older record (or none).** No copy test anywhere in this branch. The hand midpoint is
  taken (two `model_getAttachPoint` calls); phase 0 sets `g_playerAuraDir[slot] = 1`. Kind
  1 (held): cast animation, phase 1; when the ability button is released: sound stop, aura
  off, **state 2**. Kind 2 (timed): colours from the record, animation, a sound; when the
  top track's +8 value reaches 10.0: **state 2**. Kind 0: phase 0 sets colours and starts
  the animation (ids 0x1a and 0x1b also write `P+0xf0` and a status counter of the
  record's object, id 0x1b makes a `LightEffect`); at +8 ≥ 1.0 phase 2 fires by id: 0x19 a
  `Root`-class object, 0x15 a ring of 219 particles, a `LightEffect` and
  `world_damageInRadius`, 0x1a an `UnholyAura`; when flag 0x20 of `P+0x11a` is clear:
  **state 2**.

### States 3 and 4 — hit reaction and death

- **3** (0x1ab1f0): a running cast is torn down (sound stop, aura off, phase 0), a block
  flag `P+0x47f` cleared; `step(1.0)`; when flag 8 of `P+0x11a` is clear: `P+0x480 = 0`,
  `P+0x44c = 0`, **state 2**, `P+0x448 = frame`, `P+0x3cc = 0`. No move call.
- **4** (0x1ab2f0): sound stop, aura off. Outside PvP mode A, on the one tick where
  `since` equals 180 (compared as doubles; the constant is at 0x5362a0): the hand
  midpoint, **two shared draws** (angle, then size `% 10 + 25`), `decal_add` (copy too).
  `step(1.0)` while `g_playerDeadCountdown[slot]` 0x4f84a8 > 1. The state never leaves;
  `player_respawn` replaces the object.

### State 8 and 0xb — block and block move

- **8** (0x1a60e0): `step(1.0)`; the block-idle animation is started when missing
  (`anim(0x9c)`, flags 0x2801); `P+0x55c = 16` (in a net game a melee hit lands only at
  0). Block released: once the top track's +8 value is ≥ 1.0 and fewer than 7 tracks:
  `R+0x4a5c = 0`, `P+0x47f = 0`, **state 2**, `P+0x454 = 0`. Block held: when `P+0x47f`
  is 0 or neither block animation is playing, `P+0x47f = 1`, `anim_start(anim(0x84),
  0x803)`; `R+0x4a5c −= 1/60`. With `rank(0x3b) > 0` (read from the record):
  **three shared draws per try** until the point is in the unit ball, and a particle (copy
  too). `move(1)`. `Player_tryBlockMove`.
- **0xb** (0x1a6588): **returns from the function at once, skipping the tail, while
  `g_recallCountdown` ≠ 0.** Else `step(1.0)` (footstep on bits 5), water ripple when bit
  61 of `P+0xa8`, `P+0x55c = 16`; when flag 8 of `P+0x11a` is clear: block held →
  `P+0x47f = 1`, **state 8**; else **state 2**. `move(1)`.

### The remaining states

- **6 / 0xe** (0x1a6a28): the copy runs `step(1.0)`. State 0xe does nothing else. State 6:
  `Player_move(P, 5, pad, (0,0,0))`; real only, with the ability button in `pad.pressed`:
  for `selected` id 0x31 / 0x22 the `SpellBash` / `SpellShieldBash` on `P` is asked
  (spell slot 4) and `P+0x450 = 1` on yes.
- **7** (0x1a5f98): once the top track's time reaches 0x4080a3d6 (4.02) or `P+0x47d` is
  set: first time (`P+0x47e` = 0) `player_voice(slot, 0xd)`, `P+0x30 = 360.0`,
  `P.z += 0x3ca3d70a`; `P+0x47d = 1`. While `P+0x30 > 0` it loses 0x4157fffe (13.5).
  `move(0)`.
- **9** (0x1a6bf0): three track fields set (`P+0x188 = 0.1`, `P+0x18c = 1.0`,
  `P+0x190 = 0`), `step(2.0)`, `move(2)`.
- **10** (0x1a6818): `e = step(1.0)`; bit 1 → voice and a sound; real only: bits 1/2/4 →
  `world_damageInRadius` 24 units to the side or ahead, bit 8 → a `GroundPoundEffect`;
  flag 8 of `P+0x11a` clear → **state 2**. No move call.
- **0xc** (0x1a66d8): `step(1.0)`; a `LightEffect` on the tick where `P+0xf0 == frame −
  30` (copy too); flag 0x20 clear → **state 2**, `P+0xf0 = frame`. No move call.
- **0xd** (0x1a5ea8): the copy with bit 0x10 in `pad.pressed` → **state 2**. Else
  `step(1.0)`, the vehicle's slot 17, `obj_updateGridCell(P)`, the riding animation when
  missing.

Move call by state: 0 → 1 / 6 (net); 1 → 4 then 3; 2 → 0; 5 → 1 / 6; 6 → 5; 7 → 0; 8 → 1;
9 → 2; 0xb → 1; 3, 4, 10, 0xc, 0xd, 0xe → none.

## 7. Tail (0x1ac460–0x1ac7a4)

1. **Aura light.** When `g_playerAuraFade[slot] > 0`: `light_link2(P+0x504)`. **If
   `R+0x4a60` is neither 0 nor 1 the function returns here** — no `Player_updateCast`, no
   countdowns. Light position: `P.pos + (0, 0, 36)`, moved 40 units along the facing when
   `selected`'s name equals the string at 0x536250 and `g_recallCountdown` is 0;
   `light_relink`; radius = `trunc(sin16(frame × 6000) × 4.0) + 180`; colour words
   `P+0x50e..0x51c` = `g_playerAuraLightColor[slot]` 0x8659a0 × fade.
2. `Player_updateCast(P, pad)` when `R+0xac > 0` (9.11).
3. **Record countdowns** (real only): `R+0x4bca` (u16) −1 while non-zero; `R+0x4bc8` (u8)
   −1 while non-zero, and on reaching 0 object flag 0x400000 is cleared; `R+0x4bc9` (u8)
   −1 while non-zero.
4. `P+0x488 = 0` unless the state is 5.

## 8. Reads that are not lockstep state

"Gates" lists everything that changes when the value differs between two machines.

| Read | Where | Gates |
|---|---|---|
| `g_menuInputLockout` 0x41b4fc | 0x1a5644 (offline only), 0x1a5ba8 (always) | offline: the zero pad. Always: `Player_weaponSwapInput` — i.e. the weapon-set toggle `R+0x4a7c`/`+0x4a7d`, `inventory_equipItem`, and the per-tick `Player_recalcDamage` (`R+0xcc/0xd0/0xd4`) — and `Player_interact` (D26) |
| `g_spellSelectorHeld[slot]` 0x41b818 | 0x1a5c08 (always), 0x1a6e04 (offline only) | `Player_interact` (K1). Offline also the start of an ability |
| `g_paused` 0x41b4f4 | 0x1a5b9c | the same two calls as the lockout |
| `P+0x464` (written by `Player_draw`) | 0x1a5618 | `Player_weaponTrails` only |
| `net_isLocalSlot(slot)` | 0x1aa6f4 (state 1, net game) | swing sound and shout on frames 6 and 9, and with them one draw of the third generator 0x404468 |
| `net_isLocalSlot(slot)`, `g_localMenuOpen` 0x41b69d, `g_itemListCells` 0x4ebbb0 | `Player_usePotion` 0x1b9f7c, 0x1b9fcc–0x1b9fec | the sound; and whether the potion leaves bag 2 now (stack count, `inventory_removeItem`) or by `invmsg_sendDrop` (K2). The amount to deliver and the rates are the same either way |
| `memcard_isBusy()` | 0x1a54fc (net game) | `pad_rumble` only |
| the prediction-copy flag 0x20000 | throughout | see "real only" / "copy too" in sections 1–7 |
| third generator 0x404468 | 0x1aa980 | the swing sound variant only |
| level flag word 0x44fe08, `g_simFrame`, globals 0x4f7128, 0x503890, 0x4f66c8, `g_recallCountdown`, `g_medalDialogTicks`, `g_killPlaneZ`, `g_pvpModeA`, `g_playerDeadCountdown` | sections 1–7 | lockstep by their writers as far as the earlier documents established (`docs/issues/draw-sim-leaks.md`); listed because the tick branches on them |
| `net_getCamFlag`, `dialog_isOpen`, `task_isRunning`, `net_isSlotActive`, `game_isFrozen` | sections 1, 2, 4 | callbacks of the model; whether each is the same on every machine is the business of its own area document |

Stores the copy makes to shared state inside the tick (no test in the code): status-2 mana
drain (3.8), the kill-plane pending damage on its own object (4.2), `R+0x4a5c` (state 2,
8), `R+0x4a7c` for older arrow ids (state 2 A.4), mana for older arrow kinds and
`script_runByName` (state 0), the kind-1 mana cost per tick (state 5), every store of the
older-record cast branch, the aura globals, slot 12 of a melee target, `decal_add` (state
4), the block particle and its three shared draws (state 8).

## 9. The helpers the model includes

1. **`Player_idleFidget` 0x1bc2f8.** Stick length > 0x3c23d70a (0.01) with a fidget
   running (`P+0x463`): flag cleared, tracks 4.. faded. Otherwise, with exactly four
   tracks: **one shared draw**; below 0xe2 (226 of 65,536) and no fidget running: the idle
   animation of the weapon class is started (`res_find` in the lump of the **record's**
   object, `anim_start(…, 1; 0.5)`), `P+0x463 = 1`.
2. **`player_canBlock` 0x1bee48**: false in state 0xb or with a class-4 item in equipment
   slot 2; else true with an item in slot 0, 2 or 3 (`R+0x43f0`, `+0x43f8`, `+0x43fc`).
3. **`Player_tryBlockMove` 0x1bf150**: level flag 0x10000000 clear, `P+0x47f` set, swap
   in `pad.pressed`, block in `pad.held` → **state 0xb**, `P+0x481 = 47`,
   `anim_startBlendInOut(anim(0xa4), 0x808; 0.1, 0x3e999999)`.
4. **`Player_regenHealth` 0x1b3b90** (real only, `hp > 0`). Below the maximum: amount =
   `max × 0x38d1b717` (0.0001), × `(level × 0.1 + 0x3f999999)` with a level of passive
   0x10, + `P+0x477 × 0.0001`, × `(1 + value × 0x3c23d70a)` for modifier 0xb of each of the
   17 equipped items; added and capped. Then, while `R+0xb4 > 0`: `hp += R+0xb8` (capped;
   on the cap the remainder is dropped) and `R+0xb4 −= R+0xb8`, floored at 0.
5. **`Player_regenMana` 0x1b3900**: the same with passive 0x200 (`level × 0x3e199999`),
   `P+0x475`, modifier 0xc, **0 for record class 0**, then + amount × `stat × 0.01` for a
   `SpellBlessed` on the player and again for a rank of skill 0x13
   (`SkillRegeneration_getStat0`); potion fields `R+0xc8`, `R+0xbc`.
6. **`Player_tickEnchantTimers` 0x1bc560** (real only): for each equipped item and each id
   in the list at 0x537c08 with a frame count above 0: the modifier is rewritten into the
   first slot that is empty or holds that id, with the count minus 1; at 0 every slot with
   that id becomes −1.
7. **`Player_usePotion` 0x1b9cb8** (real only, `hp > 0`). `R+0xb8 = min(maxhp ×
   0x3b088888, 0x3effffff)`, `R+0xbc` likewise from the maximum mana — both on every call.
   Nothing more when `current + pending ≥ maximum`. The nine potion names of the kind
   (pointer tables 0x4ef478, 0x4ef4a0, smallest first) are looked up in bag 2 (the last
   matching cell per size); wanted size = `trunc(missing + 1) / 60`, at most 8; when that
   size is missing: size 8 if present, else the largest present; none → HUD notice 1 or 2.
   `pending += (size + 1) × 60`, capped at what is missing. Then the per-machine part of
   section 8, `player_countPotions` (1..5 left → HUD notice 4 or 5), the carried load
   `R+0x120` summed again over the three bags, and a use counter (0x4f85ca / 0x4f85c8).
8. **`Player_weaponSwapInput` 0x1bb718.** States 8 and 0xb clear `R+0x4a7d`. Block held
   and `player_canBlock` → return (no recompute). With level flag 0x10000000 clear: outside
   states 2 and 3 a swap press sets `R+0x4a7d`; in state 2 a swap press (or the latch)
   steps `R+0x4a7c` to the other set that has a primary weapon, and the set's primary (and
   for set 0 the second weapon `R+0x443c`) is equipped through `inventory_equipItem` when
   it is not already. Always last: `Player_recalcDamage(P, primary of the set, 1)`.
9. **`Player_castSkill` 0x1a42b8.** Nothing when `P+0x4ae > 0`, the record is null or not
   a Skill-object record, the copy with skill flag bit 0 clear, or `canUse` refuses. Aim
   point = hand midpoint (z replaced by `P.z + 58` when more than 58 away, compared in
   software double precision); `world_collectObjectsInArc(P.pos, facing; 340, 20, 0)`,
   first object `enemy()` accepts; facing = `0x41c2 − atan2_16` toward it, else the
   player's; `spell = cast(rank, P, point, facing)`; for the copy the spell is ended at
   once (spell slot 1 with 3), otherwise `creature_addSpell` and, for skill kind 1, a
   handle at `P+0x588`. `P+0x4ae = skill+0xc`. `mana −= manaCost(rank)` (× 1/60 for kind
   1) — **for the copy too**, on the shared record.
10. **`Player_pickAttackAnim` 0x1bba88** is a callback of the model. Executed on its own:
    it makes exactly one shared draw whose value it does not use, stores only `P+0x461`,
    and picks the variant from `g_simFrame`, the record's model index, the weapon class and
    the old variant. It ends with a call of `net_isLocalSlot` whose result is discarded.
11. **`Player_updateCast` 0x1a3f70.** `aimAt(hand midpoint)`. Then, unless a record is
    forced: when the ability button is not held, or the state is not 5, or `mana ≤ 0`, and
    the track with flag 0x8000 is missing or its +8 value is ≥ 1.0: aura off
    (`g_playerAuraDir = −1`, fade rate 0xbd4ccccc), that track capped and fading, phase 0,
    state 5 → **2**, and the held spell at `P+0x588` is told to stop (slot 1 with 3).

## 10. Shared-seed draws of one tick, in order

| # | Where | Condition | Count |
|---|---|---|---|
| 1 | idle voice 0x1a549c | the counter passes its limit | 1 |
| 2 | `Player_idleFidget` 0x1bc3d0 | four tracks, and stick at rest or no fidget | 1 |
| 3 | `Player_processDamage` | callback; not modelled | ? |
| 4 | state 0, throw 0x1a8420 | release tick, real player, no `P+0x484` | 2 |
| 4 | state 0, bow 0x1a8980– | release tick with ammunition | 3; 4 with a target; plus 1 with a bow item |
| 4 | state 1 `Player_pickAttackAnim` | next swing of a combo | 1 |
| 4 | state 4 0x1ab3f0– | `since` = 180, not PvP mode A | 2 |
| 4 | state 8 | `rank(0x3b) > 0`, every tick | 3 per try |
| 5 | `Player_move` | callback; not modelled | ? |

Rows 4 are alternatives (one state per tick). Constructors called through callbacks
(`LightEffect`, `MissileWeapon`, …) draw once each from the shared seed in
`GameObject_ctor`; the prediction loop restores the seed afterwards.

## 11. What the differential test covers

`python3 tools/difftest_player.py` runs eight sequences — real player / prediction copy ×
offline / net game × two "machines" (machine B owns the slot, has its menus, selector and
lockout busy far more often, and answers `net_isLocalSlot` with 1) — of 4,000 ticks each
with seeded pad input, and compares, per tick: the callbacks in order with arguments, the
set of bytes stored outside the stack with their final values, the shared seed and the
number of draws, and the exit path. Floats are compared as bit patterns under the
interpreter's default FPU model; the tick's own float work is a few dozen multiply-adds,
no result of which is near a rounding boundary by construction, so agreement means "same
operations in the same order", not "same as a console".

Result of `python3 tools/difftest_player.py` at seed 20973 (the default), 8 × 4,000 ticks:

| Property | Result |
|---|---|
| calls, stores, seed — each of the eight sequences | PASS, 31,990 ticks compared, 0 mismatches |
| ticks in which the original read unmapped memory | 10 (all at 0x1ab7c0, see below); the model faulted on the same ticks |
| `Player_pickAttackAnim` on its own (2,500 calls) | PASS (9.10) |
| action states entered | all of 0–14, and 15 (no handler) |

Ticks per state at the start of the tick: 0: 2,238; 1: 3,201; 2: 15,866; 3: 1,901;
4: 5,390; 5: 351; 6: 340; 7: 90; 8: 1,398; 9: 248; 10: 107; 0xb: 443; 0xc: 80; 0xd: 100;
0xe: 181; 15: 56.

Coverage of the original as executed in that run (counted from the interpreter's trace;
a block starts at the function entry, at a branch or jump-table target and after a
conditional branch's delay slot):

| Function | Basic blocks | Instructions | Branch outcomes |
|---|---|---|---|
| `Player_run` | 978 of 1,045 (93.6%) | 7,053 of 7,646 (92.2%) | 1,061 of 1,194 (88.9%) |
| `Player_usePotion` | 91 of 95 | 566 of 590 | 93 of 102 |
| `Player_castSkill` | 26 of 27 | 248 of 258 | 27 of 30 |
| `Player_weaponSwapInput` | 52 of 52 | 219 of 219 | 63 of 66 |
| `Player_updateCast` | 21 of 21 | 209 of 209 | 26 of 26 |
| `Player_regenHealth` / `Player_regenMana` | 25 of 25 / 31 of 31 | 123 of 126 / 160 of 163 | 24 of 26 / 30 of 32 |
| `Player_tickEnchantTimers` | 35 of 37 | 119 of 126 | 33 of 38 |
| `Player_idleFidget` | 24 of 24 | 146 of 150 | 26 of 26 |
| `player_canBlock`, `Player_tryBlockMove`, `Player_hasAnim` | all | all | 23 of 24 |
| `player_getSkillRank`, `player_getPassiveLevel` | 14 of 15 | 56 of 59 | 12 of 14 |

The 67 blocks of `Player_run` that were never entered, and are therefore **not tested**
in the model: the war-cry animation choice for weapon classes 5, 2 and 7 (0x1a70f0–);
the kind bytes for older arrow ids 5, 6, 0x13, 0x12 (0x1a7530–) and everything their
release does differently (kind 3 and the mana charge, 0x1a925c–0x1a949c, including the
several-arrow loop 0x1a9354–0x1a9468, which is unreachable as written because its count is
0 or negative); the thrown-weapon branches that depend on item flags and names
(0x1a85f4–0x1a8800); the ammunition count of skill 0x2e (0x1a9014–0x1a9090); the next
swing of the bow / thrown-weapon melee (0x1aad90–0x1aaf30) and its class-6 start
(0x1a7a20); the combo window of class 7 (0x1aab18); the id 0x22 result in state 6
(0x1a6be0); the older cast ids 0x1a / 0x1b in phase 0 and 0x19 / 0x1a in phase 2
(0x1abcd0–0x1ac13c); a block flag in state 3 (0x1ab208); the no-ammunition voice in the
bow branch (0x1a7de8); and two clamps of the aura globals (0x1a581c, 0x1a587c). `-v`
prints the list.

**An out-of-bounds read in the original** (found by the faults above). In state 5, phase
1, the code compares the cast point with the +8 value of track
`t = anim_findTrackByFlag(0x8000)` without testing `t` (0x1ab7b8–0x1ab7c4; skill kinds
other than 6). When no track carries the flag the function's "not found" value
−1,000,000,000 is used as the index: the float is read from `P + 0x124 + t × 0x20`, far
outside the object. `Player_updateCast` tests the same index properly. Whether a cast
animation track can vanish while the phase is still 1 was not established (Unknown; it
needs `anim_advance` read for when a finished track is dropped). The model reproduces the
address arithmetic.

What stays scripted (not game data): animation events and flags, damage and death,
landing, targets, skill and spell objects, inventory side effects, respawn; and states 6,
7, 9, 0xd, 0xe, which the driver enters by writing the state as skill and vehicle code
does (10 and 0xc are entered both ways). Stack-passed arguments beyond the eight integer
and eight float registers (`LightEffect_ctor`, `particleDef_ctor`) are not compared. The
callbacks' answers are random within plausible ranges, so combinations a real callee can
never produce are tested too, and combinations only a real callee produces may be missed.

## 12. Where earlier documents turned out wrong or short when executed

1. `docs/player.md` ("Two net-game differences") says the net-game melee hit is applied
   on frame 1 of the swing. Sharper, and executed: on frame 1 **only when `P+0x55c` is 0**
   (the field table of the same document has the field, the sentence does not). `P+0x55c`
   is 16 after any tick in state 8 or 0xb and counts down by one per tick spent in state 1
   in a net game, and frame 1 is the only hit frame — so no swing lands until 16 melee
   ticks have passed since the last block.
2. `docs/player.md` "Order of work" omits three exits that skip the tail (and with it
   `Player_updateCast` and the record countdowns): the scripted-control exit (`P+0x231`,
   0x1a55a4), which also skips damage and regeneration; state 0xb while
   `g_recallCountdown` ≠ 0 (0x1a6588); and `R+0x4a60` outside {0, 1} while the aura light
   is on (0x1ac4c0).
3. `docs/issues/dynamic-tests.md` 2.12 (m6) lists state 1 as move mode 3. That is the
   blank-player case; a fresh swing gets mode 4 first, as `docs/spec/movement-camera.md`
   4.4 says. No contradiction, but m6 did not show it.
4. `docs/spec/movement-camera.md` 4.5 lists the zero-pad conditions without their order;
   the order decides which calls are made (section 2), and the hit-points test is last.
5. Level-flag bit 0x10000000 is described in `docs/spec/skills-35-68.md` S.2 as a veto of
   ability starts. Executed across the tick: it also vetoes block (0x1a5e58, 0x1a7ff0),
   the block move and the weapon swap, but **not** the plain attack (state 2 B.3).
6. `docs/spec/skills-35-68.md` S.4 step 2 calls the lead point a dead value. That holds
   for the bow; the throw uses it (state 0, step 2).
7. `docs/spec/skills-35-68.md` S.4 step 4 writes the arc query as `(340.0, 20.0, 0,
   P.pos, P.facing, list, 0)`. Executed: the third value is a float (0.0 in f14); the
   integer registers hold (position, facing, list, 0). Likewise the `?` in the symbol
   notes of `world_collectObjectsInArc` and `particle_spawn` is a float argument.
8. The 16-bit facing is passed sign-extended to `GroundPoundEffect_ctor`, `Root_ctor` and
   `model_getAttachPoint`, and the dead state's decal angle is the draw as a signed 16-bit
   number.
9. New detail rather than a correction: `Player_usePotion` rewrites both per-tick
   delivery rates `R+0xb8` and `R+0xbc` on every call, before any test other than "real
   player, alive" — a potion button pressed at full health still stores them.

## 13. New per-machine reads found

None beyond the ones already in the ledger (K1, K2, D26, the swing-sound test). Two
details are new: `Player_pickAttackAnim` calls `net_isLocalSlot` and discards the result
(0x1bbfe4, harmless); and the idle-voice counter reads the slot's lockstep pad directly
(0x1a5420), not the chosen pad, so it keeps counting input while controls are locked.

## 14. Not done

- `Player_processDamage` 0x1b2cc0, `Player_move` 0x1b4020, `Player_animStep` 0x1b9520,
  `Player_meleeHit` 0x1b6a98, `Player_interact` 0x1b2640, `Player_findTarget` 0x1bb3c8 and
  `Player_pickAttackAnim` 0x1bba88 are callbacks, not models. The first two contain
  shared draws.
- `Player_recalcDamage` and the damage function are modelled by `tools/ref_combat.py`;
  the model here calls them as callbacks and does not wire the two together.
- The older-record branches are modelled and compared, but whether any shipped character
  owns such a record is the open question D15/D16.
