# Player offence: the attack-animation choice, combos and the armed melee hit

US `SLUS_209.73` v2.00. Round 2 of the combat contract (`docs/combat-runtime.md`), target
"player combat": which swing a player makes, when its hit lands, and what one hit sends to
`damage_apply` for every weapon kind. It is the prose of `tools/ref_combat_melee.py`,
which subclasses round 1's `CombatModel` and `Runtime` without changing them.

Labels as in `docs/combat-runtime.md`: **Executed** (the original run in `tools/ee_emu.py`
on constructed state and found equal to the model; the test is named), **Observed** (read
at the address given), **Inferred**, **Unknown**, **Authored** (a choice of this contract).
Nothing here was run on a console, in PCSX2 or on the live rig.

## 1. In brief

1. **The attack-animation choice draws the shared seed once and ignores the value.**
   `Player_pickAttackAnim` 0x1bba88 advances `g_randSeed` 0x404464 and then chooses the
   variant `P+0x461` from a hash of `g_simFrame`, the record's model index `R+0x54`, the
   weapon class and the old variant. *Executed* (`pickAttackAnim`, 3,000 cases).
2. **A player's hit is a frame count, not an animation event.** One hit per swing, on
   `since == trunc(16.02 / speed)` offline (frame 1 in a net game, and only with
   `P+0x55c == 0`); the next swing may start on a tick with attack in `pad.pressed` once
   `since > (22.02 - trim) / speed` (17.616 for class 7); a swing ends by itself after
   `P+0x470 x 60` frames, which is **not** divided by the speed. *Executed* (the state-1
   model of `tools/ref_player.py`, by `tools/difftest_player.py` and by this round's combo
   runs); the animation side agrees (`docs/spec/player-animation-dispatch.md` 4 on
   `t3/research-anim`: the player's melee clips carry no hit events).
3. **`Player_meleeHit` makes exactly one `damage_apply` call per target**, with the
   weapon's damage bits as flags, the weapon item as the descriptor and the record's damage
   range as written by `Player_recalcDamage` (and raised in place by a heavy attack or a
   scale). *Executed* for every branch (`meleeHitFull`, 3,000 cases).
4. **A heavy attack on a creature costs 200 shared draws** (`Player_hitSparks`
   0x1bcc20: 100 spark pairs, one draw per end). *Executed* (`hitSparks`, 3,000 cases; and
   inside `meleeHitFull`).
5. Round 1's contract is unchanged: `MeleeRuntime` reproduces round 1's pinned duel byte
   for byte (`test_round_one_duel_unchanged`).

## 2. `Player_pickAttackAnim` 0x1bba88 (P, weapon class) - Executed

| Step | What | Where |
|---|---|---|
| 1 | one shared draw (the seed word is stored, the value is never read) | 0x1bbab0-0x1bbafc |
| 2 | `h = (g_simFrame x 0x19660d + 0x3c6ef35f) & 0xffff` - the generator step applied to the frame counter, so the same frame always gives the same `h` | 0x1bbaa8-0x1bbaf4 |
| 3 | the new variant from `R+0x54` (model index), the class, `s8(P+0x461)` and `h` | 0x1bbaf8-0x1bbfe0 |
| 4 | `net_isLocalSlot(slot)`, result discarded | 0x1bbfe4 |

The decision table is `pick_attack_variant()` in the module; it equals the table of
`docs/spec/player-animation-dispatch.md` 3.4 (*Executed* there once by an unrecorded
script; now recorded by `difftest_combat_melee.py`). Two details that table leaves out:
model 9, class 0, old variant 5 stores the byte **twice** (4 in a delay slot at 0x1bbbd4,
then 1 or 3 when `h >= 0x5555`), and classes 4 and 6 (and any class above 7) store
nothing. Every swing from state 2 starts at variant 1 (*Observed*, 0x1a7f7c; ref_player).

Lockstep consequence (*Inferred*): the draw is made for the real player and for the
prediction copy alike (the function has no copy test, *Observed* 0x1bba88-0x1bbff4), so the shared seed moves
on every machine; the variant itself depends only on shared values.

## 3. The combo: `Player_run` state 1 (0x1a9678) as it decides the swing and the hit

The state is *Executed* in `tools/ref_player.py` (`Tick.state_melee`,
`docs/spec/player-tick.md` 6, state 1). This round adds runs of the same comparison with
weapon classes 4, 6 and 7 (`difftest_combat_melee.py`, "combo runs", 12,000 ticks, 0
mismatches), which reach the blocks the earlier runs never entered: the class-7 window
(0x1aab18, 3,138 ticks), the bow/thrown next swing (0x1aae70, 43 ticks), its
`Player_findTarget(P, 60)` (0x1aaeac, 15) and its swing start (0x1aaf00, 5). The driver
enters state 1 for those classes by writing the fields state 2's own bow/thrown punch
path writes (0x1a79fc; *Authored* driver).

Per swing, counted from its start frame `P+0x448` (`combo_timeline()` gives the numbers):

| Weapon class (`R+0x4a86`) | Combo length | Hit frame (speed 1) | Next swing after | Ends by itself |
|---|---|---|---|---|
| 0 one hand | 7 | 16 | 22.02 | 96 |
| 1 two hand | 7 | 16 | 22.02 | 96 |
| 2 two hand, sweep | 4 | 16, and the sweep from `trunc(127 / speed)` | 22.02 | 96 |
| 3 long | 9 | 16 | 22.02 | 96 |
| 4 bow (melee) | 7 | 16 | 22.02, swing only after 39.6 and with a target | 54 (0.9 s) |
| 5 unarmed | 2 | 16 | 22.02 | 96 |
| 6 thrown (melee) | 7 | 16 | 22.02, swing only after 39.6 and with a target | as left by the last writer |
| 7 dual wield | 7 | 16 | 17.616 | 96 |
| heavy attack | 1 | 16 | 22.02 | 51.4 (0.857 s) |

- **Speed** is 1.0, times the best Ancestral Call / Battle Cry factor, times Berserker
  Rage for record class 5, plus haste, then scaled by the slow amount `P+0x2fc`
  (`docs/spec/player-tick.md` state 1 step 4). The hit frame and the sweep frame divide
  by it; the end of the swing does not. *Executed* (ref_player).
- **The combo step** `P+0x460` counts up by one on every next swing and saturates at
  length - 1; it is the step that the dual-wield hand and the class-2 sweep list read.
  Pressing on after the last step keeps swinging. *Executed* (ref_player).
- **Classes 4 and 6** (*Observed* 0x1aae0c-0x1aaf30, *Executed* by the combo runs): the
  step, the heavy-attack flag, `Player_pickAttackAnim` (its draw) and the clip name are
  done **before** the class test, so a press between 22.02 and 39.6 frames advances the
  step and draws the shared seed without starting a swing. After 39.6 frames:
  `Player_findTarget(P, 60.0)`; no target -> no swing; a bow sets `P+0x470` = 0.9; the clip
  (`anim_start`, flags 0x802, blend 0.1); `P+0x448` = frame. The test "since > 54 -> state
  2" at 0x1aaf18-0x1aaf30 sits inside "since <= 39.6" on the same value and can never be
  true (*Observed*; never entered in the runs).
- **Class 2 sweep** (*Executed* in ref_player, consequence *Inferred*): on frame 1 of a
  swing at combo step 3 every hittable object in front (`n . f >= 0`) is linked into
  `P+0x4b8`, the swing's own target included; from `trunc(127 / speed)` each node whose
  bearing the blade has passed is hit through `Player_meleeHit(P, o, 0, 0)` and removed.
  Since the swing ends at 96 frames whatever the speed, the sweep fires only when
  `trunc(127 / speed) <= 96`, that is at a speed above 127/97 (about 1.31) - haste,
  war cry or a battle cry are needed - and the main target is then hit twice (frame 16 and
  the sweep). A heavy attack starts at combo step 0, so it links no sweep list, and it is
  heavy only until its hit (frame 16 clears `P+0x44c`); its raw sweep frame 94 is never
  used.
- **Net game**: the hit is on frame 1 only, and only while `P+0x55c` (16 after any tick of
  blocking, counting down in state 1) is 0. *Executed* (ref_player; `docs/spec/player-tick.md`
  12.1).

## 4. `Player_meleeHit` 0x1b6a98 (scale; P, target, unused, extra) - Executed

`player_melee_hit_full` in the module. In order:

1. Nothing for the prediction copy (0x1b6b00).
2. Scale 0 only: `terrain_raycast(g_world, (P.x + 0.0, P.y, P.z + 36), target - P, 0;
   1.0)`. A hit (`t >= 0`) ends the call **unless** `typeid(*target) == typeid(AutoProp)`
   (0x1b6bb8-0x1b6bfc): slot 0 of the target's table (a static type-info getter, called
   with a leftover `a0`), `AutoProp_typeinfo` 0x3c9508, and `rtti_typeInfoEquals` 0x3b1250
   (same descriptor or same name). So a wall between the player and a monster blocks the
   hit, while an `AutoProp` (by its name a prop object, *Inferred*) is hit through it.
3. The hand (0x1b6c04-0x1b6cdc): with both hand slots filled (`R+0x43f0`, `R+0x43f4`), the
   passive 0x40000 (`player_getPassiveLevel` inlined, record class table 0x4ef538) above 0
   and the combo step `P+0x460` odd, the second weapon `R+0x443c` and hand 1; otherwise the
   primary of the active set `R+0x4434 + 4 x R+0x4a7c`, hand 0.
4. `Player_recalcDamage(P, weapon, 0)`. With a weapon: flags = definition +0x20 (the
   damage-type bits), `a3 = item_getModifiedField1a(weapon)`, `a4` = the low word of item
   +8; unarmed: flags 1, `a3 = a4 = 0`.
5. `| 0x1000` for class 1 after 60 frames of the swing; the knock-back class 0x80000 with
   a scale or for class 3 after 60 frames, else 0x40000.
6. A weapon with class 4, or whose definition +0x1e is 6: `Player_recalcDamage(P, 0, 0)`
   and `| 0x200000` - **a bow or thrown weapon in melee hits with fist damage** but keeps
   the weapon's damage bits, `a3`, `a4` and the item as the descriptor.
7. Heavy attack (`P+0x44c == 2`): `| 0x200000`; `s = skill_rankScale(passive 0x20000)`
   (0x1bf438: `((n - 1) x 9.99999 + 99.99999) x 0.01`, so 0.9 with no passive);
   `R+0xd0 += round(R+0xd0 x s)`, then `R+0xd4` likewise, **stored in the record**
   (rounding half away from zero); a creature target (flag 0x20) gets `Player_hitSparks`.
   With no passive a heavy hit therefore has 1.9 times the range.
8. A non-zero scale: `R+0xd0 = round(R+0xd0 x scale)`, `R+0xd4` likewise, in place.
9. A `SpellHarmTouch` on P (`creature_findSpellByType`): `SpellHarmTouch_applyToHit(spell,
   target, &min, &max)` replaces the range (its body is not modelled; it is a call-out
   here) and `| 0x200000`.
10. `damage_apply(f32(min), f32(max); target, P, R+0xcc, a3, a4, flags | extra, weapon,
    0)`; a landed hit on a creature sets the trail material `R+0x4ac5 + hand x 0x40` (3
    for creature flag 0x2000, 2 for 0x1000, 1 for 0x40000, else 0) and its 5-frame timer
    `R+0x4ac6 + hand x 0x40`.

The record's damage range stays as steps 7 and 8 left it until the next
`Player_recalcDamage` (round 1 already noted this for the scale; *Executed* here for both).

## 5. `Player_hitSparks` 0x1bcc20 (P, target) - Executed

`nA = model_getSamplePointCount(P+0x544)`, `nB` = the same for the target's model (slot
16: 0x3c2738 `*(c+0x24)+0xc` for creatures, 0x3c3b38 `P+0x544` for players). Then 100
times (0x1bcc44, 0x1bce44): one shared draw, point `draw % nA` of P
(`model_getSamplePoint`, P's animation state, position, facing), slot 16 of the target
again, one shared draw, point `draw % nB` of the target; velocity = `rsqrt.s` normalised
`(B - A) x 30`; `particle_spawn(0x865950, B, velocity; 0.0)`. **200 shared draws** per
heavy hit on a creature, made only by the real player (step 1 of section 4). A model
without sample points would divide by zero; the model refuses that case.

Lockstep note (*Inferred*): the count of draws is fixed, so the seed stays in step as long
as every machine makes the same heavy hits; the particle positions read animation state,
which is presentation only.

## 6. In the composed runtime

`MeleeRuntime` is round 1's `Runtime` with `MeleeModel`: the swing's call-out
`Player_meleeHit` reaches `player_melee_hit_full`, the combo's `Player_pickAttackAnim`
runs (round 1 refused the second swing for exactly this draw), and a weapon item is served
by `tools/ref_combat.py`'s executed rules on live views of the image (`LiveItem`,
`LiveItemDef`: `Player_recalcDamage`, `item_getModifiedField1a`, and `damage_apply` with the
item's four modifier slots +0x24 as the descriptor). `give_weapon()` places a weapon
(*Authored* set-up; the equip function and its idle-animation reset are not modelled).
Still refused: bows and thrown weapons and record class 4 in `Player_recalcDamage` (they
read skill statistics), a second weapon (the dual-wield factor reads the class-skill
table, which the image does not hold), the hit sparks (sample points of real models),
`SpellHarmTouch`.

## 7. What was run

- `python3 tools/difftest_combat_melee.py local/SLUS_209.73` (seed 20973, 3,000 cases per
  entry point): **12,000 cases and 12,000 combo ticks compared, 0 mismatches** - calls
  with arguments, every byte stored outside the stack, the shared seed and the number of
  draws, the result. Nothing refused.

| Entry point | Compared | Shared draws | Instructions executed |
|---|---|---|---|
| `Player_pickAttackAnim` | 3,000 | 3,000 | 331 of 348 (the rest are delay-slot `nop`s) |
| `Player_meleeHit`, all branches | 3,000 | 208,600 | 425 of 432 (not: the null-target `typeid` throw, `nop`s) |
| `Player_meleeHit` on round 1's generator | 3,000 | 0 | 224 of 432 |
| `Player_hitSparks` | 3,000 | 600,000 | 153 of 154 |
| `Player_run` state 1, classes 4/6/7 (ref_player) | 12,000 ticks | - | blocks listed in section 3 |

- `python3 -m unittest discover -s tools -p 'test_ref_combat_melee.py'`: 19 synthetic
  tests (the decision table against the animation document, one draw, every meleeHit
  branch, 200 spark draws, the combo timeline, round 1's duel digest unchanged, a combo
  with three swings, an armed hit using the weapon's range, a refused bow).
- Not run: anything on a console, PCSX2 or the live rig.

## 8. Corrections and additions to earlier documents

| Where | Was | Is | Evidence |
|---|---|---|---|
| `docs/combat-runtime.md` 6.2 | `Player_hitSparks` "a shared-seed user, not read" | 200 shared draws, only for a creature target | Executed (`hitSparks`, `meleeHitFull`) |
| `docs/combat-runtime.md` 6.2 | weapon branches Observed | Executed, with the AutoProp exception, the second hand's trail offset (+0x40) and the fist-damage recompute keeping the weapon's flags and descriptor | Executed (`meleeHitFull`) |
| `docs/combat-runtime.md` 13 | `Player_pickAttackAnim` refused | modelled and executed; `MeleeRuntime` runs combos | Executed |
| `docs/spec/player-tick.md` 10 | state 1 draws once "next swing of a combo" | also on a press between 22.02 and 39.6 frames with a bow or thrown weapon, when no swing starts | Observed 0x1aacdc, 0x1aae1c; Executed (combo runs) |
| `docs/spec/player-tick.md` 11 | the bow/thrown next swing 0x1aad90-0x1aaf30 and the class-7 window 0x1aab18 not tested | executed by the combo runs | section 7 |
| `docs/spec/player-animation-dispatch.md` 3.4 (research-anim) | the choice table Executed by an unrecorded script | recorded test; model 9 / class 0 / old 5 stores twice | Executed (`pickAttackAnim`) |
| symbol note of `Player_hitSparks` | "spark particles between random bones" | between random **sample points** of the two models, 100 pairs | Observed 0x1bcc80-0x1bce44 |

Proposed ledger rows (for whoever edits `FINDINGS.md`):

| # | Finding | Kind | Evidence |
|---|---|---|---|
| new | A heavy attack that hits a creature makes 200 shared draws (`Player_hitSparks`), on the real player only | Executed | 0x1b6f34, 0x1bcc20 |
| new | A melee hit whose line of sight is blocked lands only on an `AutoProp` (typeid comparison by name) | Executed | 0x1b6bac-0x1b6bfc |
| new | A bow or thrown weapon used in melee hits with fist damage but keeps the weapon's damage bits and descriptor | Executed | 0x1b6da8-0x1b6de8 |
| new | With a bow or thrown weapon a combo press between 22.02 and 39.6 frames draws the shared seed and advances the combo step without a swing | Executed | 0x1aacdc, 0x1aae1c-0x1aaf28 |
| new | The class-2 sweep fires only above swing speed 127/97: the swing ends at 96 frames whatever the speed | Inferred (from the executed state-1 model) | 0x1aa6b0 on |

## 9. Not done, not known

- `SpellHarmTouch_applyToHit` 0x2d2cbc is a call-out (its symbol note mentions 204
  `Spell_rand` draws; whose generator that is belongs to the spells work).
- Bow and thrown weapons in `Player_recalcDamage` (skill statistics) and the dual-wield
  factor in the composed runtime; the sample points of real models for the hit sparks.
- Whether any shipped character can reach a swing speed above 1.31 with a class-2 weapon
  (it decides whether the sweep is ever seen) - needs the haste modifier values of items
  and the spell factors.
- The prediction copy's state 1 in a net game beyond what `tools/difftest_player.py` ran.
