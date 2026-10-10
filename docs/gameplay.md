# Gameplay: damage, triggers, effects, world camera, vehicles

Area `gameplay`, code range 0x1e8000–0x210000 (276 functions, 229 named in
`symbols/gameplay.tsv`). Everything here was read from the decompile and the disassembly;
nothing was run when it was written. Since then the damage function has been executed in
`tools/ee_emu.py` (`docs/spec/combat.md`; marked **executed** where folded in), and the
project has a live game — the Play! emulator, which is not a PlayStation 2 and not PCSX2 — whose
runs are listed in `FINDINGS.md`, "Run on the live game" (rows V1–V13) and `docs/issues/live-rig.md`.
Nothing in this document was re-checked there: none of the runs looked at a hit, a
trigger, an effect or a vehicle. No test patch has been run on a live game.
Claims are **Observed** unless marked *Inferred* or *Unknown*.

## 1. Layout of the range

| Range | Module | Entry points worth knowing |
|---|---|---|
| 0x1e8230–0x1eacb8 | hit resolution | `damage_apply` 0x1e8230 |
| 0x1eacb8–0x1ec900 | small game helpers | `damage_radial` 0x1ead58, `camera_shake` 0x1ebae0, `task_camera` 0x1ebbe0, `drawWorld`, `game_isFrozen`, level-scale getters |
| 0x1ec900–0x1ed694 | trigger classes | `Trigger_run` 0x1ecf3c, `PushTrigger_prompt` 0x1eca94, `PushTrigger_interact` 0x1ecc70, `MonsterTrigger_scan` 0x1ed388 |
| 0x1ed694–0x1edb18 | script launching, quest variables | `script_runByName`, `script_runDeferred` 0x1ed5a0, `script_runPostAction` 0x1edac0, `vars_*` |
| 0x1edb18–0x201958 | effect objects: run, draw and helper bodies | `fx_spawn` 0x1ef270, class run functions |
| 0x201958–0x203210 | effect objects: constructors and tiny virtuals | `FlyingText_ctor` 0x202158, `LightEffect_ctor` 0x201bd8, `poisonGasSpell_ctor` 0x202de8 |
| 0x203210–0x2076ac | world camera | `Camera_update` 0x203400, `Camera_apply` 0x2035c8 |
| 0x2076ac–0x20f7d4 | vehicles (Vehicle, Boat, SkulBoat share code; Wheel) | `Vehicle_run` 0x207c3c, `Vehicle_board` 0x208f08 |
| 0x20f7d4–0x210000 | named path table (level objects of class `Line`) | `paths_findByName` 0x20f9e4 |

## 2. `damage_apply` (0x1e8230)

The one function that turns "A hits B for min..max" into a number, status effects, sounds,
a floating number and a call to the victim's take-damage virtual (vtable slot 2). 103 call
sites. Size 10,784 bytes; frame 0x250.

### 2.1 Parameters

| Reg | Name used here | Meaning |
|---|---|---|
| $f12 | min | lowest base damage (float) |
| $f13 | max | highest base damage (float) |
| $a0 | victim | any GameObject; must not be null in practice (dereferenced at 0x1e8328 before the null test) |
| $a1 | attacker | GameObject or 0 |
| $a2 | attack | integer attack rating compared with the victim's armor (+0xe4). The brief called this "range"; it is not a distance. 75 of 103 sites pass 100000 ("always hits"), melee passes the player's record value at 0x4d8bbc + slot stride (record +0xcc, the attack rating built by `Player_recalcDamage`; monster melee passes creature +0xd4), missiles pass the missile's own +0xe4 |
| $a3, $t0 | — | **not used**: both registers are overwritten (0x1e82d8, 0x1e88b8) before any read. Melee (0x1b6a98) and missiles (0x152a18) still pass values here |
| $t1 | flags | bit set, table below; kept at sp+0x1a4 and modified while running |
| $t2 | desc | damage descriptor, or 0 for an all-empty one built on the stack |
| $t3 | noCrit | non-zero suppresses the critical-hit bonus and roll; only the thorns skill passes 1 ("thorns" in this document is the helper 0x2ddccc of skills 9 and 0x52, which `docs/skills.md` names `Riposte`: `SkillRiposte_counterAttack`) |

Return value: 0 when nothing landed (attacker is the prediction copy, invulnerable, blocked,
shield, miss), 1 otherwise. Note that the "same class as the projectile's owner" early exit
returns 1 without doing anything.

### 2.2 Damage descriptor

A caller-owned record; the function reads only the four effect slots. The stack default
(0x1e82a8–0x1e8308) shows the extent it expects.

| Offset | Type | Meaning | How known |
|---|---|---|---|
| +0x10 | s16[4] | zeroed in the default; not read here | 0x1e82f0 loop |
| +0x18 | s16[4] | zeroed in the default; not read here | same |
| +0x20, +0x21 | u8, u8 | 0xff in the default; not read here | 0x1e82dc–0x1e82e4 |
| +0x24 + 8·i | s16 type | effect type of slot i (i = 0..3), −1 = empty | every lookup loop |
| +0x26 + 8·i | s16 v1 | first value | |
| +0x28 + 8·i | s16 v2 | second value | |
| +0x2a + 8·i | s16 v3 | third value | |

Lookups always take the **first** slot whose type matches. Effect types handled:

| Type | v1 | v2 | v3 | Effect | Needs first hit roll |
|---|---|---|---|---|---|
| 0x15 | min | max | – | fire damage, reduced by fire resistance; sets the burn status (strength 2 − 2·res) unless flag 0x10000000. "min, max" here and in the other elemental rows means: amount = v1 + (draw rem (v2 − v1 + 1)), in integers and with no guard (0x1e98c8–0x1e9914; the same expression at the other six sites). Two skills pass v2 < v1, for which the amount ranges upward from v1 (`docs/spec/skills-01-34.md`). Executed in `docs/spec/combat.md` 3.1: with v2 < v1 − 1 the result is v1 + (draw mod (v1 − v2 − 1)) — values from v1 upward, never below it ((10, 5) gives 10…13); with v2 = v1 − 1 the divisor is zero, the CPU does not trap, and what a console leaves as the remainder is not established | no |
| 0x16 | min | max | – | cold damage, reduced by cold resistance; cold status timer += 60·amount/hp, capped at 60 | no |
| 0x17 | → victim +0x358 | → victim +0x35a | – | poison status, strength 5 − 5·poisonRes | no |
| 0x18 | min | max | – | lightning damage, reduced by lightning resistance; shock status 2 − 2·res | no |
| 0x19 | min | max | – | as 0x18 with fixed shock 2.0, only against victim kind 0x12 | no |
| 0x1a | chance | – | – | against kind 0x12: if rand % 100 ≤ chance, add the victim's current hp to the damage and set flag 0x800 | no |
| 0x1b | percent | – | – | against kind 0x10: damage += damage·percent/100 | no |
| 0x1c | chance | – | – | against kind 0x10: if rand % 100 ≤ chance, add current hp and set flag 0x2000000 | no |
| 0x1d | percent | – | – | critical-hit chance in percent | – |
| 0x1f | chance % | min | max | chance of fire: burn status 1 − res, plus damage | yes |
| 0x20 | chance % | min | max | chance of cold: damage, cold timer as 0x16 but using the running total | yes |
| 0x21 | chance % | strength | – | chance of poison: creates a `poisonGasSpell` object at the victim (life 300, radius 30·v2+30, damage 25·v2+25) | yes |
| 0x22 | chance % | min | max | chance of lightning: shock status 2.0, plus damage | yes |
| 0x26 | non-zero | – | – | disease: attaches a `SpellDiseaseEffect` (0x1b0 bytes, strength 5 − 5·diseaseRes) if the victim has none. `damage_apply` reads only v1, but v2 and v3 are not unused everywhere: `item_getDamageRange` (0x104100) adds v1 to the minimum and v2 to the maximum it returns when asked for elemental damage, and the weapon-buff spells write v2 = round(1.2 × v1) and v3 = frames left into the item's slot (`docs/spec/skills-69-101.md`) | no |
| 0x29 | skill index | chance % | level | chance to cast g_skillTable[v1] (Skill vtable slot 2) from the attacker's position | yes |

Kind 0x10 is *Inferred* to be "undead": the 0x1c proc plays `spel_he_hstrike_hit.anm`, and
the two undead-shield spells fire only for attackers of kind 0x10. Kind 0x12 is *Inferred*
to be "bug" (insects): effect types 0x19 and 0x1a are the item tokens `bugzapper` and
`bugexploder` (as 0x1b and 0x1c are `undeadbonus` and `undeaddestroy`, token table in
`docs/startup.md`), and the ant, fire-beetle and small-spider constructors store 0x12 at
+0xb4 (0x235418, 0x24587c, 0x2ab450). The earlier version said kind 0x12 was Unknown.

### 2.3 Fields read and written on the victim and attacker

Creature-class objects (flag 0x20). Offsets are on the object.

| Offset | Type | Meaning | Use |
|---|---|---|---|
| +0xc | u32 | object flags | 0x8 dead, 0x20 creature, 0x40 player, 0x80 projectile-like object with owner link, 0x20000 prediction copy |
| +0x38 | s16 | facing | block direction test |
| +0x4c | ptr | (attacker with flag 0x80) owner link; owner object at link+0xc | friendly-fire test |
| +0x5c / +0x60 / +0x64 / +0x68 / +0x6c | float | fire / cold / poison / disease / lightning resistance, 0..1 | sound names of the matching procs |
| +0x90..+0x9e | s16[8] | flash colour; written by the thorns, undead-shield and Retribution helpers | 0x2ddccc, 0x2eaec0, 0x314790 |
| +0xa8 | u64 | creature flags, see below | |
| +0xb4 | s8 | creature kind (0x10, 0x12 tested) | |
| +0xcc | float | accumulated damage for flag 0x800000 | written 0x1ea6fc, 0x1ea790 |
| +0xe4 | s16 | armor class | hit chance and player mitigation |
| +0xf0 | s32 | frame stamp, written on the attacker when a hit is reflected | 0x1e8ca0 |
| +0x228 / +0x22c | float | current / maximum hit points of the object (*Inferred*: +0x228 is added to make a kill certain; 0x1e7e40 divides by +0x22c to pick a light/heavy hit sound) | |
| +0x340, +0x344, +0x348, +0x34c | float | burn, cold, shock, poison status values, set through 0x118950, which also re-links the handle at +0x360 to the attacker | |
| +0x358, +0x35a | s16 | written from a 0x17 slot | 0x1e9ce8, 0x1e9d28 |
| +0x398 | s32 | status counter 11; set to 0x11 on the attacker when its hit is reflected | 0x1e8c9c |
| +0x39c | s32 | status counter 12; > 0 enables reflection | 0x1e8c14 |
| +0x3c8 | s32 | player slot (players only) | |
| +0x3e0 | s32 | on class `Innoruuk`: non-zero makes it immune | 0x1e83cc |
| +0x58c | s32 | player state; 8 or 11 count as "blocking" in the PvP text test | 0x1ea8c0 |

Creature flags at +0xa8 tested here: 0x2/0x4 resist/immune to class 4, 0x8/0x10 resist/immune
to class 8, 0x20/0x40 resist/immune to class 1, 0x80/0x100 generic resist/immune mark, 0x200
blocking, 0x800 invulnerable, 0x100000 makes the class-1/class-8 immunity absolute,
bit 45 (0x2000_0000_0000) monster has the thorns skill. The resist/immune bits and the five
resistance floats only choose the colour class of the floating number (0 normal, 1 resisted,
2 immune); the classification code at 0x1ea350–0x1ea510 never changes the amount.

### 2.4 Flag bits

| Bit | Meaning inside `damage_apply` |
|---|---|
| 0x1, 0x4, 0x8 | damage class (*Inferred* physical kinds). Any of them (mask 0xd) arms thorns and undead shields; 0x1/0x8 are refused by a victim with the absolute-immunity flag. Melee takes these bits from the weapon's item definition +0x20 (0x1b6a98; 1 when unarmed), for which `docs/startup.md` infers the names blunt, pierce, slash |
| 0x40 | cannot be blocked, ignores Spirit Shield; also suppresses the PvP "blocked" text test |
| 0x100 | lightning-typed for the colour class |
| 0x200 | no floating number on victims with creature flag 0x100 |
| 0x800 | set here when a 0x1a kill proc fires; passed on to take-damage |
| 0x2000 | passed to take-damage on a miss (0x42000 for non-players) |
| 0x4000 | skip the hit sound (0x1e7e40) |
| 0x8000 | skip the miss sound; with 0x4000 delays the disease sound |
| 0x20000 | a block or Spirit Shield halves the damage instead of cancelling it |
| 0x800000 | damage over time: add to victim +0xcc and deliver the sum only when frame & 31 == 0 |
| 0x1000000 | no floating number; forced on when neither side is a player |
| 0x2000000 | set here when a 0x1c kill proc fires |
| 0x8000000 | only affects victims of kind 0x10 |
| 0x10000000 | a 0x15 slot adds damage but no burn status |
| 0x40000000 | no critical-hit bonus from the attacker's skills |

Other bits seen at call sites (0x10, 0x20, 0x400, 0x10000, 0x40000, 0x80000, 0x100000,
0x4000000) are not tested here; they are for the take-damage implementations.

### 2.5 Sequence, with every draw from `g_randSeed`

"Draw" = one step of the shared generator. Draws happen in exactly this order. `p` is the
hit probability, `dmg` the running amount.

1. **Attacker is the prediction copy** (attacker flag 0x20000): return 0. First test in the
   function, before anything is read or drawn (0x1e828c–0x1e82a4).
2. Music counter: if no cutscene and the victim is within 340 units (x, y) of
   `g_cameraFocus`, increment byte `0x4f7158[s16 at 0x4f717a]` (0x1e830c–0x1e8384). See §8.
3. Class `Innoruuk` with +0x3e0 set: return 0.
4. **Victim is not a creature**: **draw 1** (always), dmg = min + fmod(r, max − min + 1) in
   double precision with r the 16-bit draw; call take-damage(dmg, attacker, flags); return 1.
   ("In double precision" needs two qualifications, here and in step 10 —
   `docs/spec/combat.md` 3.4, executed. The span `(max − min) + 1.0` is computed in single
   precision; only the `fmod` and the sum go through the library's software doubles, and
   those truncate instead of rounding, as does the conversion back. And a span of exactly
   zero, possible only on this non-creature path with max = min − 1, makes `fmod` return a
   not-a-number and dmg the pattern 0x7f800000, which this FPU treats as 2^128.)
5. Refusals, each returning 0: creature flag 0x800; absolute immunity (0x100000 with 0x10 or
   0x40) against class 1/8; flag 0x8000000 against a non-0x10 kind.
6. Friendly fire of projectiles: attacker has flag 0x80 and an owner link, victim is not a
   player, and the victim's class equals the owner's class → return 1.
7. Neither side is a player → flags |= 0x1000000.
8. Armor: AC = victim +0xe4. With `SpellBloodLust` on the victim AC is multiplied by the
   spell's factor (0x3047b0) and floored at 1.
9. Mitigation for player victims (and for every victim in PvP mode A): min and max each lose
   AC/30 but not more than half, floor 0. Uses the unmodified AC.
10. Base roll: if min < max, **draw 2**, dmg = min + fmod(r, max − min + 1); else dmg = min.
11. Block (victim creature flag 0x200, flag 0x40 clear, both objects present, attacker in
    front of the victim's facing): metal hit sound and 50 sparks from the *cosmetic* seed;
    then return 0, or with flag 0x20000 halve dmg and continue.
12. Spirit Shield (flag 0x40 clear, victim has `SpellSpiritShield`): 0x315888 draws
    **draw 3** only if the spell's counter (+0x1c) is not above its limit; on success return
    0, or with flag 0x20000 halve dmg.
13. p = sqrt(attack / AC) when AC > 0, else 1. Crit chance c = v1/100 of a 0x1d slot.
14. **Draw 4 — first hit roll** (always): `hit` = draw16 < p·65536.
15. Reflection: victim counter 12 > 0, `hit`, attacker is a creature other than the victim,
    dmg > 0, attacker kind 0x10 → recursive `damage_apply(dmg, dmg, attacker, victim,
    100000000, 0, 0, 0x100, same descriptor, 0)` with all of its own draws; then attacker
    +0x398 = 0x11 and +0xf0 = frame counter.
16. Frost Armor on the victim: 0x318264 multiplies dmg by 1 − value/100 and, when there is
    an attacker, makes **draw 5**; on success it strikes the attacker through a nested
    `damage_apply` (flags 0x540, a 0x16 slot) and calls `fx_spawn(10)`. The strike's
    amount, not given in the earlier version: both values of the cold slot are
    `trunc(dmg − factor)` — the incoming amount minus the *factor* 1 − value/100, not the
    absorbed part (0x318364–0x318378; `docs/spec/combat.md` section 3, step 15, executed).
17. Rating scale: if AC > 0, dmg ×= min(attack / (AC/2), 1).
18. Skill crit bonus (flag 0x40000000 clear, attacker is a player, noCrit 0): c += the
    largest of three skill values (skill indices 0x21, 0x35, 0x51 through 0x2e76c4, which
    also honours an aura from nearby players). The attacker's own rank counts only while
    a `SpellCriticalHit` is attached to the attacker (0x2e76f8–0x2e7714); without one the
    helper looks for the aura alone (`docs/spec/combat.md` 3.2, executed).
19. **Draw 6 — crit roll**, only if c > 0 and `hit` and noCrit is 0: on success dmg ×= 3,
    `crit` = 1, and a player attacker gets a voice cue (0x1b7ba8, local slot only, cosmetic
    seed).
20. Procs, only if `hit`:
    - 0x29: if the attacker is a creature and v2 ≠ 0, **draw**; success casts the skill
      (a virtual call whose own draws were not traced). The success test is
      `draw < v2 × 655` (0x1e8ebc–0x1e8ed8), so a chance of 100 is 65500 in 65536, not a
      certainty (`docs/spec/combat.md` section 3, step 19, executed).
    - 0x1f: **draw always**, even when the descriptor has no such slot; success: **draw**
      for the amount.
    - 0x20: **draw always**; success: **draw**.
    - 0x21: **draw always**; success creates a `poisonGasSpell` (its constructor draws once,
      as every GameObject constructor does).
    - 0x22: **draw always**; success: **draw**.
21. Always-on slots, in this order, whether or not `hit`: 0x1b (no draw); 0x15 (**draw** if
    v1 ≠ 0); 0x16 (**draw** if v1 ≠ 0); 0x17 (no draw); 0x26 (the Spell constructor
    0x2d5594 draws once when a disease is added); 0x18 (**draw** if v1 ≠ 0); 0x19 (**draw**
    if v1 ≠ 0 and kind 0x12); 0x1a (**draw** if v1 ≠ 0 and kind 0x12); 0x1c (**draw** if
    v1 ≠ 0 and kind 0x10).
22. **Second hit roll** (skipped when `crit`): **draw**; if draw16 ≥ p·65536 the hit
    misses: miss sound, take-damage(0, attacker, 0x2000 or 0x42000), return 0. Everything
    in steps 15–21 has already happened; only the amount is discarded.
23. Colour class from flags and resistances (no draws).
24. Thorns (flags & 0xd, both creatures): player victim with skill 9 and/or skill 0x52 —
    each call of 0x2ddccc **draws once**, and on success draws once more and strikes the
    attacker through a nested `damage_apply` (flags 0x40, noCrit 1), but only if the
    victim's model reports a non-zero vertex count; monster victim with flag bit 45 uses
    skill 9 at the level-wide monster level 0x4f714c.
25. Undead shields (player victim, creature attacker of kind 0x10, flags & 0xd):
    `SpellUndeadShield` or else `SpellSecondaryUndeadShield` strikes back through a nested
    `damage_apply`; they use the per-spell generator, not the shared one.
26. PvP mode A and player victim: dmg ×= 0.5.
27. Flag 0x800000: accumulate (see table) and possibly deliver through take-damage; dmg
    becomes 0 for what follows. "Possibly" is exactly this (`docs/spec/combat.md` section
    3, step 25, executed): delivery happens only on a frame with `frame & 31 == 0`
    (0x1ea700–0x1ea708; the other condition in the code, "hp > 0 and hp ≤ 0", can never
    hold); the amount delivered is whole and at least 1; and step 28 then calls
    take-damage a second time, with 0.
28. Hit sound unless flag 0x4000; then **take-damage(dmg, attacker, flags)**.
29. Attacker is a player: 0x308c10 gives a percent chance for skill 0x40 (0 in PvP mode A and
    for creatures that 0x10d940 rates 2, at most 5 for rating 1), **draw always**; on success 0x308cb4 creates a `LightEffect`
    (constructor draw), **draws** a duration of 1.5–2.5 s and calls victim vtable slot 30.
    `SpellRetribution` on the attacker heals the player record by dmg·value and returns the
    fraction for a second number.
30. Floating number (`FlyingText`, 0x98 bytes, one constructor draw each). Created only if
    all hold: victim is not a player (or PvP mode A between two different players); the
    damage-number option 0x44fcf8 is on **or the game is a net game**; victim not dead; not
    (flag 0x200 and creature flag 0x100); no cutscene; not the PvP "blocked from the front"
    case; flag 0x1000000 clear; for flag 0x800000 only on delivery frames. A second one
    (kind 2) shows the Retribution amount when that fraction is non-zero.

### 2.6 Related functions

- `damage_radial` 0x1ead58 — area damage with linear falloff. Calls take-damage directly,
  so none of the above (no rolls, no descriptor, no numbers). One caller, 0x2f4d34.
- 0x1e7e40 (ui range) — picks and plays the hit/miss sound from the victim's material bits
  or the player's armor; no shared state.
- 0x118950 (creatures range) — status setter used for burn/cold/shock/poison.

## 3. Triggers and script launching

Scripts are started by name through `script_runByName` (0x1ed694): it looks the name up in
the current script (0x86b270) and runs the interpreter; returns the script's result or −1.
`g_scriptActivePlayer` (0x4d8ae4) and the "current object" 0x4039f8 are set by callers.

| Starter | Where | What it runs |
|---|---|---|
| Trigger volume | `Trigger_run` 0x1ecf3c | on enter: script named by +0x5c with the entering player as active player; on leave: the same name prefixed `not` |
| Push trigger, prompt | `PushTrigger_prompt` 0x1eca94 (slot 13) | each `key` property in turn; all must return non-zero for the `message` text, otherwise `lockMessage` |
| Push trigger, use | `PushTrigger_interact` 0x1ecc70 (slot 14) | every `action` property through 0x14dcc8 (objects range), which runs each named script, or its prefixed "off" form when called with 0 (`offOnly`); `once` then deletes the object; a `shop` trigger is refused while `net_anyAlivePlayerFlag800000` is true |
| Monster trigger | `MonsterTrigger_run` 0x1ed344 → `MonsterTrigger_scan` 0x1ed388 | the `script` property once per living non-player creature within `radius` (default 60), optionally filtered by `monstername` against the creature's `name` |
| Deferred call | `script_queueDeferred` 0x1ed52c, `script_runDeferred` 0x1ed5a0 | names queued by the script command run on the next frame (run task "Script", priority 125); at most 64 per frame |
| Cutscene end | `script_setPostAction` 0x1eda9c, `script_runPostAction` 0x1edac0 | one stored name, run by `cut_runFrame`, level load and two other sites |
| Death, NPC talk, state changes | outside this range | call `script_runByName` (40 callers) |

`Trigger` object:

| Offset | Type | Meaning |
|---|---|---|
| +0x4c..+0x58 | float ×4 | rectangle min x, min y, max x, max y (from props `w`, `h`) |
| +0x5c | char* | script name |
| +0x60 | u8 | a player was inside on the last test |
| +0x61 | u8 | the one-time search for a `TriggerParams` object in the rectangle has been done |
| +0x64 | s32 | frames to wait before testing again; −1 = disabled |
| +0x68 | s32 | slot of the player found inside, −1 if none |
| +0x6c | ptr | linked `TriggerParams` (its +0x4c points back) |

`Trigger_run` details: it tests `g_players[i].obj` for i < g_numPlayers with slot 17
(`Trigger_contains`, x/y only) and takes the lowest slot inside; when a player is inside
while the countdown 0x41b51d is non-zero it returns without acting (*Inferred* a recall
countdown: its setter 0x18c230 also creates the `RecallEffect`). With a `TriggerParams` object the props `onOnly`,
`offOnly`, `timeout` (×4 frames) and `needScriptHit` shape re-arming. Slots 8/9 load/save
the 5 bytes {+0x64, +0x60}.

`MonsterTrigger`: +0x4c radius, +0x50 number of matches in the last scan
(`MonsterTrigger_count` 0x1ed4e4 serves the script command `monstersInTrigger`).

Quest variables (`vars_*`, already in names.tsv) live in the same block.

## 4. Effect objects

All are GameObjects; the constructor of each draws once from the shared seed (through
`GameObject_ctor`). None of the run functions in this range reads the camera.

| Class | vtable | ctor | run (slot 4) | draw (5) | Notes |
|---|---|---|---|---|---|
| GutChunk (PhProp) | 0x50f3b8 | 0x201958, 0x201ad0 | 0x1edb18 | 0x201b88 | +0x248 bits: 1 delete on first bounce and never draw, 2/4 blood kind, 8 no decals; +0x25c decals left |
| LightEffect | 0x50e198 | 0x201bd8 | 0x1ee050 | – | fading dynamic light; +0x88 owner handle, +0xb4 end frame |
| RecallEffect | 0x50ee18 | 0x1ee248 | empty | empty | owns a GlowingCylinder |
| GlowingCylinder | 0x50ecf8 | 0x1f2cf0 | 0x1f3288 | 0x1f2ef0 | |
| DummyDamager (base `Projectile`; the earlier version labelled this row `Projectile`, as the old `vtables.txt` did) | 0x50ea28 | 0x201e78 | 0x1ee330 | empty | +0x54 velocity, +0x60 bits (1, 2 deletion rules; 8 fire; 0x10 cold), +0x68 damage, +0x6c life; slot 6 0x1ee7b0 calls `damage_apply` |
| WaterSpout | 0x50eab8 | 0x201fa8 | 0x1ee990 | 0x2020a0 | runs only while recently drawn, see §8 |
| Fire | 0x50f208 | 0x2020e0 | 0x1f34e0 | – | 100 frames; created only by `fx_spawn(5)` |
| FlyingText | 0x50f178 | 0x202158 | 0x2022a8 | 0x1f3830 | +0x4c text, +0x78/+0x7c drift from its own generator, +0x80 colour class, +0x84 crit, +0x8c kind, +0x96 life (30, or 180 for kind ≠ 0) |
| MissileTrap | 0x50ebd8 | 0x202318 | 0x1f3a90 | – | period +0x4e |
| Shooter | 0x50eb48 | 0x2023f8 | 0x1f4ad8 | – | +0x52 kind (0 single shot, 1 bursts), +0x54 period; active within 720 of any player; passes 25, or 60 from the fourth act on (0x217edc), to the shot's constructor (*Inferred* damage) |
| IceChunk / LooseIceChunk / PhIce / Ice | 0x50ed88 / 0x50f328 / 0x511b18 / 0x511968 | 0x202530 / 0x2025f8 / 0x202868 / 0x2028c8 | 0x1faf40 / (PhProp) / 0x1fb7f0 / 0x1fba70 | 0x2025b0 / – / – / 0x202a08 | `fx_shatterToLooseIce` 0x1fb240 draws the shared seed once plus once per chunk |
| LooseFire | 0x50e2b8 | 0x202b70 | 0x202c48 | – | slot 6 0x1fcb70 burns what touches it every 20th frame |
| FireEffect | 0x50eea8 | 0x202c98 | 0x202d70 | 0x1fcef0 | no creator found |
| poisonGasSpell | 0x50d500 | 0x202de8 | 0x1fd0f0 | empty | +0x4c owner, +0x5c end frame, +0x60 radius, +0x6c damage; ticks every 30 frames |
| dustCloud | 0x50d470 | 0x202f08 | 0x1fd5b0 | – | ticks every 60 frames |
| GlowingShaft | 0x50ec68 | 0x202ff0 | 0x2030a8 | 0x1fda20 | |
| FrostStormSpell / IceShard | 0x50d3e0 / 0x512a40 | 0x1fe508 / 0x2030f0 | 0x1fe950 / 0x1fdef8 | empty / 0x1fddd0 | shards every 10 frames, damage every 30 |
| RainOfFireSpell | 0x5129b0 | 0x1ff860 | 0x1ffcc0 | – | damage every 60 frames |

`fx_spawn(id, pos)` 0x1ef270 (91 call sites) is the one-shot effect switch, ids 0..0x16.
Its first statement returns unless the position is within 480 units of the camera focus —
**except for id 5**, which draws the shared seed (1 + 3 per object) and creates 3 or 4 `Fire`
objects. All other ids use only the cosmetic seed, particles and sounds; ids 0 and 1 (blood)
also need the gore option 0x44fdc0.

The remaining `fx_*` functions are particle emitters over a model's vertices; those with
"NearCamera" in the name start with the same 480-unit test. A text scan of the decompile
found no shared-seed write and no allocation in any of them; they were not read line by
line.

## 5. World camera

There is one camera object, reached through the pointer at 0x4f8450 (set by
`game_initCamera` in the ui range). It is per-machine by design.

**Who writes what, and when**

| State | Writer | When |
|---|---|---|
| engine camera position 0x44f038 and matrix 0x44f110 | engine setter 0x18a2b0, called from `Camera_apply` 0x2035c8 (and from `cut_runFrame` and two UI functions outside this range) | whenever a camera mode function runs |
| `g_cameraFocus` 0x44f048 | `camera_updateFocus` 0x18a520 only | `cut_runFrame` (simulation) and `drawWorld` 0x1ebc18 (draw task). Outside cutscenes the focus therefore follows the local camera at draw rate |
| camera object fields | functions below | |
| shake amount 0x4f8488 | raised by `camera_shake` 0x1ebae0 (called from simulation code); decays by 0.5 per `Camera_apply` call while the game is not frozen | |

`Camera_update` 0x203400 is called from: `task_camera` 0x1ebbe0 (run task priority 11, offline
only); `net_predictLocalPlayer` (two sites, once per predicted tick, so in a net game the
camera follows the prediction copy); player respawn 0x1bd040; dialog start 0x22fa50; the
session loop 0x322998. `Camera_apply` callers: `Camera_reset`, `Camera_updateFollow` (twice
per update), `Camera_updateFree`, `Camera_updateOrbit`, `Camera_popState`, 0x204250, 0x22ee84.

Modes (+0x34): 0 held (state pushed for menus/cutscenes), 1 follow, 2 orbit an object named
`InnoruukB`, 3..5 free fly from pad 0.

Camera object (partial):

| Offset | Type | Meaning |
|---|---|---|
| +0x18 | vec3 | target computed by `Camera_computeTarget` |
| +0x24 | vec3 | smoothed look-at point |
| +0x34 | s32 | mode |
| +0x40 / +0x44 | s32 | slot whose pad drives zoom and rotation, and the previous one |
| +0x48 | s32 | reset/transition state (non-zero forces the follow path) |
| +0x54 / +0x58 | s32 | zoom index and previous zoom index (0..2) |
| +0x60 | s32 | user control allowed this update |
| +0x64 | s32 | all alive players sit in the same vehicle |
| +0x68 / +0x6a | s16 | yaw, pitch |
| +0x6c | s16[3] | pitch per zoom index |
| +0x8c | float | distance |
| +0x90 | float | zoom blend 0..1 |
| +0xb0 | float[3] | distance per zoom index (170, 340, 450) |
| +0xfc | float | height offset |
| +0x100 | 0x60 bytes | saved with the game (`Camera_saveState`) |
| +0x160 | u8 | more than one local alive player |
| +0x161 | s8 | followed/spectated slot |
| +0x162..+0x178 | | state pushed by `Camera_pushState` |
| +0x16c / +0x16d | u8 | hold and snap counters |

`Camera_computeTarget` 0x206538 averages the positions of the alive players **local to this
machine** (list 0x4f8430, count 0x4f8424), or uses their vehicle, or — in a net game with no
local player alive — the object of the spectated slot. Zoom and rotation read the lockstep
pad array `g_pads` for the controlling slot.

## 6. Vehicles

`Vehicle` (vtable 0x512ad0), `Boat` (0x51ac78) and `SkulBoat` (0x51ab80) share slots 4, 5, 6,
13, 14, 17, 18, 19 from this range; the subclasses live elsewhere. `Wheel` (0x512bc8) is a
separate small object.

| Offset | Type | Meaning |
|---|---|---|
| +0x190 | s32 | frame of the last prompt request (written by slot 13) |
| +0x2e4 / +0x2e8 | float | throttle and brake, 0..1 |
| +0x328 | float | re-board cooldown, 30 frames after a dismount |
| +0x3b8 | float | steering |
| +0x3bc | s32 | driver's player slot, −1 none |
| +0x3c0 | s32[4] | player slot per seat, −1 empty |
| +0x3d0 / +0x3d4 | s32 | seat count / riders aboard |
| +0x3ec | s32[4] | frame each slot boarded |
| +0x400 | s32 | held by script (`holdVehicle`) |
| +0x408 | s32 | show the driver help text once |
| +0x40c | s32 | "waiting for the other local players" flag, see §8 |
| +0x45c.. | matrix | orientation |
| +0x820.. | ptr[] | turret objects per seat |
| +0x858 | handle | last object touched |
| +0x864 | s32 | driven by an NPC or a path instead of a pad |

A rider's player object has +0x540 = vehicle and +0x58c = 0xd. `Vehicle_board` 0x208f08 and
`Vehicle_dismount` 0x209058 keep both sides consistent. Boarding goes through the normal
interact slot; dismounting is pad bit 0x10 of the rider read in `Vehicle_run`.
`net_closeLocalMenus` ejects everyone on a world change except in level `lava2`.

`Vehicle_run` order: path follower, wait/help HUD text, `Vehicle_followPath` (NPC),
`Vehicle_updateSteering`, `Vehicle_updateBrake`, `Vehicle_updateThrottle`, physics and
collision helpers (0x20bd44, 0x20ce7c, 0x20b80c, 0x209ad8, 0x20b12c, 0x20acdc, 0x20b604 —
not read), then per-seat dismount and turret aim.

The table at 0x871548 (count 0x4f8938) holds named paths built from level objects of class
`Line` (`paths_add`, `paths_joinSegments`, `paths_findByName`); creatures refer to them with
the `PathName` property.

## 7. Small helpers worth knowing

- 0x4f714c is a level-wide float (monster level); `level_getMonsterLevel`,
  `level_monsterLevelTimes0_4`, `level_monsterLevelTimesDifficulty` wrap it.
- `game_sendCharacterToLobby` 0x1eb5c8 reads `g_randSeed` (does not write it) to pick which machine
  makes a lobby-library call.
- `game_isFrozen`, `drawWorld`, `deathTask_schedule`, `isNearCameraFocus480` are in
  names.tsv.

## 8. Per-machine state

Each item: what is read or written, kind of claim, address, and what it can do.

1. **Music counter in `damage_apply`** — reads `g_cameraFocus`, increments a byte in the
   32-byte array 0x4f7158 (index s16 0x4f717a). Observed, 0x1e830c–0x1e8384. The only other
   references to 0x4f7158 are a clear at level load (0x1e5e68) and a clear in 0x322520; the
   index is only ever written with 0. No reader exists by address pairing, and no data word
   holds the address, so the counter is dead and cannot affect the simulation (Observed for
   direct references; an alias through a computed pointer was not excluded). This is the
   only camera read in the function.
2. **Damage-number option in `damage_apply`** — 0x44fcf8 (a user option) is read at
   0x1ea998, but only decides anything when `g_networkMode` is 0; in a net game the
   `FlyingText` object, and so its constructor's seed draw, is created regardless. Observed.
   Handled by the original code. The option is honoured at draw time instead
   (`FlyingText_draw` 0x1f3838).
3. **`fx_spawn` camera gate** — every id but 5 returns early when the position is not near
   the camera focus; id 5, the only one that draws the shared seed and creates objects, is
   exempt (0x1ef270, test at the top; case 5). Observed. Handled by the original code.
4. **GutChunk and the gore option** — the constructors set bit 0 of +0x248 when the user's
   gore setting 0x44fdc0 is below 2 (0x2019e0, 0x201a80, 0x201b3c). `GutChunk_run` then
   deletes the object on its first bounce; otherwise it stays and lays decals. The object's
   lifetime and the number of draws from its own generator therefore differ between machines
   with different gore settings. Observed. Consequence Inferred: GutChunk is a physics prop
   in the world grid, so box queries (which have fixed result limits) and prop collisions
   can see it on one machine and not on another; no path from there to the sync hash was
   found, none was excluded. The creation sites outside this range do force creation in net
   games (0x110d30 line with `gore > 0 || networkMode`; Player_processDamage tests the
   prediction copy before its seed draw).
5. **WaterSpout is run only where it is drawn** — `WaterSpout_draw` 0x2020a0 (draw code)
   clears +0x59 and inserts the object into the every-frame run list 0x5db3a8;
   `WaterSpout_run` removes it once +0x59 exceeds 30. Observed. Shared structure changed
   from draw code. While active it uses only its own generator, particles and a water
   ripple, so the visible effect is cosmetic (Inferred); run-list membership and the
   object's generator state differ per machine.
6. **Level scripts run from draw code** — `PushTrigger_prompt` 0x1eca94 runs the object's
   `key` scripts through `script_runByName`. The prompt slot is called by
   `Player_interact(…, displayOnly = 1)`, which `Player_draw` calls for local slots
   (0x1a46c0 → 0x1b2640), so these scripts execute in the draw phase, on one machine, at
   draw rate, with whatever `g_scriptActivePlayer` was left behind. Observed. In the 120
   shipped scripts every `key` script (the compiler-generated `return…` entries) and every
   script they call uses only query commands: getv, playerHasItem, getEvil, checkPlayerGold,
   countQuestItems, getMissionComplete, getMissionAvailable, demoRunning, getNumPlayers
   (Observed by scanning `scripts/*.txt`). So no shared state changes today; any key script
   with a side effect would desync.
7. **Vehicle prompt stamps the vehicle** — `Vehicle_prompt` 0x2087e4 writes the frame
   counter to vehicle +0x190 from the same prompt path (draw and simulation). Observed. No
   integer reader of vehicle +0x190 was found in this range; effect Unknown.
8. **Vehicle wait flag depends on the local player count** — `Vehicle_run` reads 0x4f8424,
   the number of alive players *local to this machine* (0x207d28). When it is 2 or more, the
   vehicle has a pad driver, and the rider count differs from that number, it sets +0x40c
   and shows the "wait" text; otherwise it clears it. `Vehicle_updateThrottle` ignores the
   accelerator while +0x40c is set (0x20c1b8) and `Vehicle_updateBrake` applies the brake
   (0x20c490, 0x20c4c0). Observed. Consequence Inferred: in a net game where one machine
   hosts two or more players and another hosts one, the same vehicle accelerates on one
   machine and brakes on the other as soon as not all of the first machine's players are
   aboard; riders' positions are in the sync hash. With one player per machine the count is
   0 or 1 everywhere and both take the same branch.
9. **Input lockout 0x41b4fc in vehicle code** — read at 0x2080dc, 0x20812c, 0x20c1c4,
   0x20c368, 0x20c488, 0x20cbfc; local menu code sets it to 60. Observed. `tasks_run`
   zeroes it at the start of every net tick (0x322710) and objects run (priority 10) before
   the HUD task (50), so object code sees 0 unless lockstep code (cutscene, script) set it
   in the same tick. Inferred safe.
10. **Camera** — per-machine throughout; it reads `g_pads` of the controlling slot and the
    local alive list, and writes only its own object, the engine camera, the shake amount,
    HUD hint timers 0x41b828/0x41b8a8 and the cosmetic seed (Observed for stores to absolute
    addresses with tools/ghostreach.py from 0x203400; stores through object pointers were
    read in 0x204938 and 0x206538 only). `g_cameraFocus` is written from the draw task.
    `Camera_getYaw` 0x207450 is read by `net_main` (outside this range): worth checking that
    the yaw is applied before the input record is encoded and not inside the simulation.
11. **`camera_shake`** — called from simulation code; writes the per-machine shake amount
    and rumble. Output only. Observed.
12. **No victim-side test for the prediction copy in `damage_apply`** — only the attacker is
    tested. Inferred unreachable: box queries never return the copy (G6) and monsters do
    not run during prediction.
13. **`Trigger_run`** — uses the real player table and runs only inside the simulation tick;
    the recall countdown it honours (0x41b51d) is set from a game-message handler
    (0x18c230, called from 0x1d8df4). Inferred shared.
14. **Camera-gated emitters** (0x1f5210, 0x1f5890, 0x1f5c70, 0x1f5e18, 0x1f61c0, 0x1fc150)
    — cosmetic seed and particles only by text scan. Observed at scan level. The three
    that simulation code reaches (0x1f5210, 0x1f61c0, 0x1fc150) have since been checked by
    callee list as well (`docs/issues/rescan.md` section 4.2): the lists hold only
    `particle_spawn`, model sample points and a sine table, plus the beam table calls of
    0x1f61c0 (FINDINGS D28); presentation only. Of the other three, 0x1f5890 is called
    from draw code and 0x1f5c70 and 0x1f5e18 have no caller.

## 9. Open questions

- What the descriptor holds at +0x00..+0x23 and which structure it is embedded in (melee
  passes a pointer taken from the player's weapon data in 0x1b6a98). Answered in
  `docs/issues/kill-loot-xp.md`: for a melee hit the descriptor is the weapon's item
  record itself (0x48 bytes, layout in `docs/player.md`), and the four effect slots at
  +0x24 are the item's modifier slots.
- Names of damage classes 0x1/0x4/0x8. (Creature kind 0x12 was listed here too; §2.2 now
  gives the inference.)
- Draws made inside the virtual calls `damage_apply` reaches: Skill slot 2 for a 0x29 proc,
  victim slot 30 for the skill 0x40 proc, and each class's take-damage.
- Whether the thorns helper's "model has vertices" test (0x1799c8 on the victim's model)
  can differ between machines; it gates a seed draw and a nested hit.
- Whether an online game can have two players on one machine. Item 8 only bites then.
- Who reads vehicle +0x190 and player-object flag 0x800000.
- A third global generator at 0x404468 is drawn by code outside this range (0x110d30,
  `Player_run` 0x1a5030 — the earlier version gave 0x1a9678, an address inside it — two
  boss death effects and three skill functions; the seven are listed in
  `docs/monsters.md` §2.3). The sync hash uses 0x404464 only; what 0x404468 feeds was
  not followed.
- `game_sendCharacterToLobby`: answered in docs/issues/sync-breakers.md — 0x3278f0 (`lobby_sendCharacter`) packs the record and passes it to the lobby library.

## 10. Not done

- Vehicle physics and collision (0x209ad8–0x20bd44, 0x20ce7c–0x20e33c, 0x20f244–0x20f4d0,
  0x20fd0c): callers and written fields listed, bodies not read; 30 of them are unnamed.
- `fx_modelStatusEffects` 0x1f6ac8 (17 KB) and the other model emitters: scanned, not read.
- `fx_spawn` ids other than 0, 1, 5, 9, 10 were not described individually.
- Camera functions 0x203bb8, 0x204250, 0x204fe0, 0x205880, 0x205db0, 0x206d18: read in
  outline only. (`docs/spec/movement-camera.md` section 7 has since specified the follow
  camera. One point differs from the note this pass left in `symbols/gameplay.tsv`:
  `Camera_followCollide` 0x204fe0 does not shorten the distance when terrain is in the
  way; it raises the pitch until the followed players are visible.)
- Class-specific take-damage and the Skill/Spell helpers called from `damage_apply` belong
  to other areas; only their seed draws were checked (0x315888, 0x318264, 0x2ddccc,
  0x308cb4, 0x2d5594).
