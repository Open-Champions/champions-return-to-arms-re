# Creatures: the Creature base class, AI helpers, weapon holders, clone functions

Area `creatures`, code 0x109d68–0x131d88 (320 functions). Symbols: `symbols/creatures.tsv`.
Read `docs/objects.md` first: a `Creature` is a `GameObject` (0x4c bytes) with 0x37c more.
Everything here was read from the executable; nothing was run. Claims are marked
**Observed** (read at the address given), **Inferred** or **Unknown** where it is not obvious.

## What is in the range

| Addresses | Contents |
|---|---|
| 0x109d68–0x10af28 | constructor, post-constructor setup, stat scaling |
| 0x10b048–0x10c0f0 | `Creature_draw`, turning, death/revive hooks, `Creature_updateActive` |
| 0x10c238–0x10f190 | **perception and target selection**: line-of-sight tests, cone searches, target/ally pickers |
| 0x10f2c8–0x112948 | loot, corpse handling, `Creature_processDamage` (the largest function, 6 KB) |
| 0x112948–0x1164c0 | `Creature_run`, movement (`moveBy`, `moveTo`, flee), knockback, animation step, path requests |
| 0x116638–0x118418 | damage intake, save/load state, interact, weapon-part helpers |
| 0x1185d8–0x11aaf8 | ~90 small helpers that monster classes call: predicates on the target, attack helpers, path access, status setters, spell-list access |
| 0x11abd0–0x11c180 | virtual functions of the three weapon holder classes `Weapon1`, `Weapon2`, `WeaponShield` |
| 0x11c1a0–0x131a40 | **117 clone functions** (virtual slot 15), one per class that adds fields |
| 0x131b00, 0x131cb8 | two netcode functions that happen to sit here |

How the pieces fit: a monster class (monsters area) overrides slot 4 (run), slot 5 (draw)
and slot 27 (set state). Its run calls `Creature_updateActive`, then usually
`Creature_run` (timers, status effects, follow logic), `Creature_processDamage`, a state
switch that uses the helpers below, `Creature_stepAnim` and `Creature_moveBy`. Its draw
calls `Creature_draw`. The base class's own slots 4 and 5 are empty stubs; `Creature_run`
and `Creature_draw` are ordinary functions (72 and 68 callers), not the virtual entries.

## Virtual slots: 39, not 92

See `docs/objects.md` for why the tool's count was wrong (the corrected `tools/vtab.py`
and `vtables.txt` now give 39). Slots 1–16 are the `GameObject`
slots; the Creature bodies are listed here. Small bodies were emitted inline at
0x3c2688–0x3c2758 (runtime area).

| Slot | Creature body | Meaning | Kind |
|---|---|---|---|
| 1 | 0x117128 | destructor: deletes every attached spell, clears handles | Observed |
| 2 | 0x116638 | take damage (amount, attacker, flags) | Observed |
| 3 | 0x11a5f0 | trigger: named creature runs its `dialogScript` | Observed |
| 4, 5 | stubs | run, draw (overridden by every real class) | Observed |
| 6 | 0x11a418 | touched: a player touching sets cflag bit 59 | Observed |
| 7 | 0x11a260 | path search finished (found) | Observed |
| 8 / 9 | 0x116920 / 0x116780 | load / save state in a level record | Observed |
| 10, 11, 12 | empty | hit terrain / touched objects / nearby event | Observed |
| 13 / 14 | 0x116d50 / 0x116bd8 | interact prompt / interact (player slot) | Observed |
| 15 | 0x11c298 | clone | Observed |
| 16 | 0x3c2738 | get model (first resource of the class definition) | Observed |
| 17 | 0x11a868 | pass a position and the facing to every attached spell (their slot 2). `Creature_run` calls it each frame for non-players with the body centre; `Trigger_run` and script `objInPlayerTrig` also call slot 17 on other classes | Observed |
| 18 | empty | on props this is the "set state" entry of script `autoPropSetState`; `Creature_init` calls it for MiniBoss creatures | Observed |
| 19 | 0x118418 | get display name into a buffer | Observed |
| 20 | 0x119328 | is `other` my enemy: 0 no, 1 yes, 4 priority | Observed |
| 21 | 0x119400 | is `other` my ally | Observed |
| 22 | 0x10de10 | same team as `other` (used by skills to decide who a buff reaches) | Observed |
| 23 | 0x10ded0 | pick target (force) | Observed |
| 24 | 0x10e2c0 | pick ally | Observed |
| 25 | 0x10e658 | can see target (force) | Observed |
| 26 | 0x10bb08 | turn toward a point (mode 1 = away). Returns the signed 16-bit angle from the facing to the point as it was *before* the turn (0x10bb9c–0x10bbb4 leave it in the result register); the creature move helpers halve the move speed and the root motion of that step when its size exceeds 16000 (`docs/spec/movement-camera.md` section 6.3) | Observed |
| 27 | 0x3c2688 | set AI state: the base body only stores +0x232; 241 call sites | Observed |
| 28 | 0x10beb8 | on death | Observed |
| 29 | 0x11a668 | refresh the model-variant handle +0x220 from +0xe8 | Observed |
| 30 | 0x118a58 | stun (frames, flash) → state 0x13 | Observed |
| 31 | 0x118af8 | start the no-target timer +0x316 (frames) | Observed; gameplay name Unknown |
| 32 | 0x10bfc8 | revive (with effect) | Observed |
| 33 / 34 | 0x3c2700 / 0x3c2708 | get / set HomeRange +0x3c0 (script `setMonsterRange`) | Observed |
| 35 | 0x118c50 | returns level scale × 0.3 as an int; monster code passes the result as the level of a skill it casts (`docs/monsters.md` §1.2, `docs/skills.md`) | Observed; purpose Inferred there (this row said Unknown) |
| 36 | 0x118c78 | 0, 4 or 10 by boss rank. Purpose, from `docs/monsters-2.md` (2.1, 9.1): the level used for the Dodge skill against missiles — `MissileWeapon_onTouch` asks a non-player creature for slot 36 and, when the result is non-zero, passes it to the value query of skill 2 (0x152eec–0x152f50). Overrides: Marr 20 while guarding, else 5; IronGuardian 11 | Observed; purpose answered (was Unknown) |
| 37 | 0x3c2730 | get team byte +0x310 | Observed |
| 38 | 0x3c2748 | second resource of the class definition | Observed |
| 39 | 0x3c2758 | returns 0; `Player_run` and `Player_processDamage` call it | Observed; purpose Unknown |

Non-virtual inline accessors in the same block: 0x3c2690 "is charmed" (+0x312 ≠ 0),
0x3c26a8 set root timer, 0x3c26b0–0x3c26f8 get/set pointblankrange, visualrange,
visualarc, 0x3c2720/0x3c2728 get/set the activity radius +0x3c4.

## Creature layout (0x3c8 bytes)

Offsets from `Creature_ctor` 0x109d68 and `Creature_clone` 0x11c298 (which lists every
field once); meanings from the function named in the last column. Fields only ever seen
being copied are marked Unknown.

| Offset | Type | Meaning | Evidence |
|---|---|---|---|
| +0x4c | ptr | virtual table of an embedded holder (class `WeaponObject`, table 0x50d010) | ctor |
| +0x50 | ptr | the weapon object (`Weapon1`/`Weapon2`/`WeaponShield`; its own table at +0) | script `setWeaponType` 0x1448e4, `Creature_init` |
| +0x54 | s32 | path follower: clock value after which a stuck follower is teleported | `Creature_run` |
| +0x58 | s16 | path follower: current point index, −1 = find nearest | `Creature_run` |
| +0x5a | s8 | player slot being followed, −1 none | `Creature_run` |
| +0x5c | float[5] | resistances, in the order fire, cold, poison, disease, lightning (as in `docs/gameplay.md` §2.3; the earlier version of this row named none and left three Unknown). [1] also caps the slow amount from the chill timer, [4] the one from status counter 7 | `Creature_run` 0x113680, 0x1137e4; `damage_apply` 0x1e8230 |
| +0x70 | float[4] | colour bias added while any status counter runs | `Creature_draw` |
| +0x80 | 4 words | Unknown | |
| +0x90, +0x98 | s16[4] ×2 | two flash colour quads; every element moves 2 toward 0 each frame | head of `Creature_run`; set by stun, revive |
| +0xa0 | u8 | tint preset 0–11 applied in draw | `Creature_applyTintPreset` |
| +0xa8 | u64 | creature flags ("cflags"), table below | |
| +0xb0 | float | turn rate; per-frame limit is value × 1092.27 angle units | slot 26 |
| +0xb4, +0xb5 | u8 | +0xb4 creature kind, stored by each class constructor and tested by item effects in `damage_apply`: 0x10 undead, 0x12 insects (both names Inferred, `docs/gameplay.md` §2.2). +0xb5 Unknown. The earlier version gave both as Unknown | e.g. `Skeleton_ctor` 0x2a5af4 stores 0x10, `Ant_ctor` 0x235418 stores 0x12 |
| +0xb8 | float | move speed, units per second | `Creature_moveTo` |
| +0xbc, +0xc0 | float | root motion of the last animation step (world space) | `Creature_stepAnim`, consumed by `Creature_moveBy` |
| +0xc4 | s16 | root rotation of the last animation step | same |
| +0xc8 | float | **pending damage** accumulated since the last `Creature_processDamage` | slot 2 |
| +0xcc | float | damage accumulated by hits flagged 0x800000 (damage over time) and delivered every 32nd frame. Earlier: Unknown | `damage_apply` 0x1ea6f0–0x1ea790 (`docs/gameplay.md` §2.4) |
| +0xd0, +0xd2 | s16 | damage range | `Creature_setStats` |
| +0xd4 | s16 | attack rating: the third value monster melee passes to the hit helpers, which hand it to the damage function as `attack`. The earlier version said "scaled stat, Unknown" | same; `Creature_hitTargetInArc` 0x119938 |
| +0xd8 | float | value used for the experience award on death | `Creature_processDamage` (Inferred) |
| +0xdc | float | scale (`Scale` property / 100) | ctor |
| +0xe0 | float | forward offset of the drawn/attached position | `Creature_getVisualPos` |
| +0xe4 | s16 | armour: what an attacker's attack rating is compared with (`docs/gameplay.md` §2.5). The earlier version said "scaled stat, Unknown" | `Creature_setStats`; `damage_apply` 0x1e8230 |
| +0xe8 | u32 | model variant bits (`change0`…`change31` properties) | `Creature_init` |
| +0xec, +0xf4 | s32 | Unknown | |
| +0xf0 | s32 | frame at which a status counter was last started | `Creature_run`, `Creature_draw` |
| +0xf8 | float[3] | flee destination (−1 = none) | `Creature_fleeFrom` |
| +0x104 | float[3] | move destination | `Creature_moveToDest` |
| +0x110 | s16 | angular velocity | slot 26 |
| +0x114 | 0x10c bytes | animation state; +0x118 current track, +0x11a flags (0x80 = clip finished) | `Creature_stepAnim` |
| +0x220 | 8 bytes | model-variant handle | slot 29 |
| +0x228, +0x22c | float | hit points, maximum hit points | ctor, slot 2 |
| +0x230 | s8 | serial number from the counter 0x4f85c4; staggers periodic work (`(frame ^ serial) & mask == 0`) | ctor, slot 23 |
| +0x231 | u8 | inert bits: 1 `wait` property / set by a save record, 2 and 4 set by cutscene code, 8 hidden, 0x10 frozen by `creatures_freezeAll`. Non-zero stops target picking and damage | ctor, slot 2, slot 23 |
| +0x232 | s16 | AI state (see below) | slot 27 |
| +0x234 | handle | **target** | slot 23 |
| +0x238 | handle | ally (heal/guard subject) | slot 24 |
| +0x23c | {s32 x, s32 y}[16] | path waypoints, −1 terminated | `Creature_requestPath` |
| +0x2bc | s32 | waypoint index; 16 = none / search pending | `Creature_getWaypoint` |
| +0x2c0 | s32 | frame before which no new path is requested | `Creature_moveTo` |
| +0x2c4 | s32 | consecutive failed searches | slot 7 |
| +0x2c8, +0x2d4, +0x2d8 | Vec3, s32, s32 | stuck detection: last progress position, clock then, "side-stepping until" clock | `Creature_moveTo` |
| +0x2dc | u32 | **pending damage flags** (OR of the flags of every hit) | slot 2 |
| +0x2e0 | s16 | angle of the last hit; knockback direction | slot 2 |
| +0x2e4 | handle | last attacker (the owner, for hits by flag-0x80 objects) | slot 2 |
| +0x2e8 | float | knockback speed, decays by 2 per call | `Creature_applyKnockback` |
| +0x2ec | float[3] | steering point | `Creature_moveTo` |
| +0x2f8 | s8 | obstacle-avoidance side: 0 none, 1 or 2 = keep steering to that side (`docs/startup.md`). Earlier: Unknown | `Creature_computeAvoidanceOffset` 0x108a60 |
| +0x2fa | s16 | facing at construction | ctor |
| +0x2fc | s8 | **slow amount** 0–60; scales animation, turning and movement by (60 − n)/60 | `Creature_run`, `Creature_stepAnim` |
| +0x300 | s32 | creature clock: +1 per `Creature_run` unless fully slowed | `Creature_run` 0x113178 |
| +0x304 | s32 | frame of the last damage | slot 2 |
| +0x308, +0x30c | float | velocity of the last move, units per second | `Creature_moveBy` |
| +0x310 | s8 | team, 0xff = none; a charm sets it | `Creature_setCharm` |
| +0x312 | s16 | charm timer, −1 = permanent | `Creature_run` |
| +0x314 | s16 | root timer, −1 = permanent (script `rootMonster`) | `Creature_run`, `Creature_moveBy` |
| +0x316 | s16 | no-target timer (slot 31); effect 0x12 over the head every 4th frame | `Creature_run` |
| +0x318 | s16 | attack cooldown | `Creature_isAttackReady` |
| +0x31a | s16 | timer paired with a speed-changing spell | `Creature_stepAnim` |
| +0x31c | s16 | stun timer (slot 30); effect 0x10 every 4th frame | `Creature_run` |
| +0x320 | 0x38 bytes | effect attachment state passed to effect code; has its own destructor 0x202500 | `Creature_dtor` |
| +0x340 | float | burn seconds: fire visual; every 32nd frame fire damage to itself | `Creature_run` 0x113284–0x113534 |
| +0x344 | float | chill seconds: becomes the slow amount; decays 1/15 per frame | `Creature_run` |
| +0x348 | float | second visual-effect timer (drawn by 0x1f61c0); it is the shock status that lightning hits set (`docs/gameplay.md` §2.3) | `Creature_run`; `damage_apply` calls of 0x118950 with index 2 |
| +0x34c, +0x350 | float | two damage-over-time timers; every 32nd frame damage of (+0x358, +0x35a) / 10 and (+0x35c, +0x35e) / 10. +0x34c is the poison status (`damage_apply` sets it, with +0x358/+0x35a, from an item's poison effect); who sets +0x350 was not traced | `Creature_run` 0x1138b0, 0x113954; 0x118950 index 3 |
| +0x354 | float | glow seconds | `Creature_run` |
| +0x360 | handle | source of the current timed effect; used as the attacker for hits flagged 0x10000000 | `Creature_setEffectTimer`, slot 2 |
| +0x364 | handle list | **attached spells** | below |
| +0x368 | char * | `ShowName` text; non-null makes the creature interactable | ctor |
| +0x36c | s32[16] | **status counters** | below |
| +0x3ac, +0x3ae | u16 | pointblankrange (300), visualrange (500) | ctor |
| +0x3b0 | s16 | visualarc (0x4000); 0x7fff once the creature has been hit | ctor, slot 2 |
| +0x3b4 | float[3] | home position | ctor |
| +0x3c0 | float | HomeRange (1000) | ctor |
| +0x3c4 | u16 | activity radius (600; 44000 while following a path) | `Creature_updateActive` |
| +0x3c8 | s32 | `Player` only: player slot | slot 22 |

### Creature flags at +0xa8 (64-bit)

| Mask | Meaning | Evidence |
|---|---|---|
| 0x1 | MiniBoss property; boss rank 1 | ctor, `creature_bossRank` |
| 0x200 | blocking | `creature_isBlockedBy`, damage function |
| 0x800 | cannot be an enemy or an ally of anyone | slots 20, 21 |
| 0x1000, 0x2000, 0x4000, 0x8000, 0x10000, 0x20000, 0x40000 | body material: choose hit effect, gib and blood type (0x40000 = ordinary blood) | `Creature_processDamage`, `Creature_deadUpdate` |
| 0x100000 | no water/dust ground effects | `Creature_moveBy`, `Creature_applyKnockback` |
| 0x200000 | model not drawn by `Creature_draw` | 0x10b988 |
| 0x400000, 0x800000 | following a player, standing ahead / behind (script `followPlayer` sets 0x800000) | `Creature_run` |
| 0x1000000 | corpse sinks and is deleted once inactive. Only creatures that carry the bit follow this rule; its setters are `Creature_loadState`, the generator spawners (0x265938, 0x265e08, 0x265fc4), 0x29cea8 and 0x2bf538 (`docs/issues/arena-desync.md`) | `Creature_deadUpdate`, tail of `Creature_run` |
| 0x2000000 | `Creature_stepAnim` passes no sound position to `anim_advance` (0x116330–0x116348), which mutes the animation's sound cues. Root motion is produced and applied whether the bit is set or not; the earlier version said "root motion not applied to the position" (`docs/spec/movement-camera.md` section 9) | `Creature_stepAnim` |
| 0x4000000 | friendly (script `friendly`): picks no target, is nobody's enemy | slots 20, 23 |
| 0x8000000 | following a `PathName` path (script `followPath`) | `Creature_run` |
| 0x20000000 | no ice shatter, no gibs | `Creature_processDamage` |
| 0x40000000 | has `light1`/`light2`/`ambient` properties | ctor, `Creature_draw` |
| 0x80000000 | boss health bar is showing — **written from per-machine data**, see C3 | `Creature_run` 0x11399c–0x113ab8 |
| 0x100000000 | revived or loaded dead: gives no loot or experience | slot 32, `Creature_processDamage` |
| 0x40000000000, 0x80000000000 | map marker bits (script `showOnMap`) | 0x1e40a8 |
| 0x100000000000 | priority enemy (script `increaseEnemyRank`) | slot 20 |
| 0x1000000000000 | IgnoreDamage property | slot 2 |
| 0x2000000000000 | dies when its charm ends | `Creature_run` |
| 0x800000000000000 | a player touched it | slot 6 |
| 0x2000000000000000 | standing in water | `Creature_moveBy` |
| 0x4000000000000000, 0x8000000000000000 | was active last frame, is active | `Creature_updateActive` |

Bits 0x10000–0x20000000000 not listed are set in monster constructors and were not traced.

### AI state (+0x232)

Only the numbers the base class itself tests are established: 0 idle; 1 entered when a
player touches an idle charmed creature; 3 a moving state whose animation rate is scaled
by 0x1bea10; 5 held in place (what a rooted creature is forced into); 6–15 attacking
(`Creature_isTargetAttackingMe`); 0x10 waiting out the attack cooldown; 0x13 stunned;
**0x14 dead** (set on death, by script `killMonster`, by the `dead` property and by a dead
save record). `Creature_filterState` 0x10a9c0 is the common filter derived `setState`
bodies call. **Observed.** Other numbers belong to the individual classes.
`docs/monsters.md` §1.4 describes the same numbers from the monster side, and the two
lists are one: in the classes 1 is "walk to the destination +0x104", 3 is the chase and 5
is the wait between attacks; its timers A, B and C are the root (+0x314), attack-cooldown
(+0x318) and stun (+0x31c) timers of the layout above (`Creature_filterState` forces 5,
0x10 and 0x13 while they run).

## Status effects

Three layers exist and they are easy to confuse.

**Frame timers** (+0x312…+0x31c, s16, one step per `Creature_run`): charm, root,
no-target, attack cooldown, spell speed, stun. All **Observed** in `Creature_run`
0x112c6c–0x112d64.

**Second timers** (+0x340…+0x354, float seconds, −1/60 per `Creature_run`): set through
`Creature_setEffectTimer(seconds, creature, which, source)` 0x118950. Burn and the two
damage-over-time timers deal damage through the damage function 0x1e8230 every 32nd frame,
and only when the creature is **not** the prediction copy (tests of 0x20000 at 0x1132f8,
0x113834, 0x1138d8). A burning *player* draws one `g_randSeed` value per tick; a monster
does not. **Observed.**

**The 16 status counters** at +0x36c (FINDINGS D12–D15). What this area adds:

- `Creature_draw` chooses a coloured glow from them in this order of precedence (later
  wins): counter 1, 2, 5, 6, 8, 9, 10, 11, 13; counter 7 overrides all. It then decrements
  the **first non-zero counter in index order** unless that is index 12 or the game is
  frozen (0x10b898–0x10b8d4). **Observed.** The loop stops at the first non-zero counter
  whichever it is, so while counter 12 is non-zero and counters 0–11 are zero, counters
  13–15 are not decremented either (executed, `docs/issues/dynamic-tests.md` i2).
- `Creature_run` reads only counter 7 (+0x388): it becomes the slow amount, ramping at 2
  per frame from the start frame +0xf0, capped by resistance [4] and zeroed on death
  (0x113738–0x1137e4). **Observed.** After the 30-frame ramp the amount is 60 for any
  counter value above 30 and the counter itself only at 30 or below (0x113774–0x1137d8;
  executed, `dynamic-tests.md` z6; `docs/spec/movement-camera.md` 4.6).
- No code in this range writes any counter except through whole-object copies (clone).

## Pending damage

`Creature_takeDamage` (slot 2) subtracts hit points at once **and** accumulates the same
amount in +0xc8 with the flags in +0x2dc. `Creature_processDamage` 0x110d30, called from
the class's run, reacts later in the same or the next frame: hit flash (flag 0x100), hit
effects chosen by cflags, optional gib objects, and at hit points ≤ 0 the death sequence:
flags 0x9, knockback speed from damage flag bits 0x40000 / 0x80000 / 0x100000 / 0x200000
(100 / 150 / 200 / 312.5), state 0x14, flag 0x2000, then (unless the creature has the
`Dead` property or cflag 0x100000000) experience for the players and a `GameObject_rand`
roll for an object dropped for the killer. Slot 28 (on death) and `Creature_dropLoot` are
not called from here; the monster classes call them. A creature with the IgnoreDamage flag
clears its second timers instead of taking damage; an inert creature (+0x231 ≠ 0) ignores
the call. **Observed.** Players use `Player_processDamage` instead.

## The attached-spell list (+0x364)

A handle list of `Spell` objects (spell: back-list head at +4, the `Skill` that made it at
+0x08, the creature it is attached to at +0x0c, virtual table at +0x14; the fields from
+0x18 on belong to each class — layout in `docs/skills.md`). The earlier version gave
"caster at +0x18, skill id at +0x1c" for every spell; that is the layout of the `SpellTag`
marker only, and `creature_findSpell` 0x11a788 tests the class before it reads those two
words (`docs/spec/skills-35-68.md` section 4.6, `docs/spec/skills-01-34.md` section C).
`creature_addSpell` links one; `creature_findSpell`
and `creature_findSpellByType` search it; `creature_removeSpellByType` 0x11a6d0 deletes
one; the destructor deletes all. Three places walk it every frame: slot 17 (spell slot 2,
from `Creature_run`), `Creature_draw` (spell slot 3, **from draw code**, 0x10b928–0x10b970)
and the destructor. `Creature_clone` starts the copy's list empty (FINDINGS G2).
**Observed.**

## AI helper catalogue

All take the creature as their object argument; "target" is the object behind +0x234.
Arcs are 16-bit angles; ranges are world units. Full list with notes in the symbol file.

**Choosing who to attack**

| Address | Name | What it does |
|---|---|---|
| 0x10ded0 | `Creature_pickTarget` | slot 23. Keeps the current target while it is alive and still an enemy. Every 32nd frame (staggered by serial) or when forced: box query of ±HomeRange, candidates scored by slot 20 (+1 if last attacker, +1 if current target), ties broken by 2-D distance. If not damaged in the last 480 frames, candidates outside HomeRange of *home* are accepted only when within 60 units plus radii or when the creature is already farther from home than they are |
| 0x10e2c0 | `Creature_pickAlly` | slot 24, same idea with slot 21, box around home |
| 0x10cf78 | `creature_findEnemyInCone` | same scoring inside a cone, requires a clear terrain ray |
| 0x10ca70 | `creature_findPlayerInCone` | uncharmed: nearest visible live player from `g_players[0..n)` in slot order |
| 0x1124e0, 0x119d60 | `players_findNearestOnTeam`, `players_findFarthestWithin` | pick a player slot by distance |
| 0x119328 / 0x119400 / 0x10de10 | slots 20 / 21 / 22 | enemy / ally / same-team tests |

Nothing in these functions reads the camera, the local-player slot, or what was drawn. They
depend on the grid (box query order), on `g_players`, on the frame counter and on the
creature's serial number. **Observed.**

**Seeing**: `creature_canSeeObj` 0x10c810 and its variants (0x10c238, 0x10c410, 0x10c5b8),
wrappers on the target (0x118cb0–0x118d90), slot 25. All are arc + range + one terrain
ray (0x18a5c0).

**Predicates on the target**: attacking me 0x118e90, blocking 0x118f08, charging 0x118f90,
running away 0x119038, knocked down 0x1190e8, allies near it 0x119258.

**Moving**: `Creature_moveBy` 0x113c48 (the collision step), `Creature_moveTo` 0x114510
(path following with stuck recovery), `Creature_moveToDirect` 0x1155e0,
`Creature_moveToTarget` 0x1143e8, `Creature_moveToDest` 0x119f38, `Creature_moveToAlly`
0x119e98, `Creature_fleeFrom` 0x115910, `Creature_pickWanderDest` 0x119618,
`Creature_isAwayFromHome` 0x10eed8, `Creature_settle` 0x119e38, path access
0x11a020–0x11a1e0, `creature_findClearHeading` 0x10eaa8. Stuck recovery uses the
creature's own generator for the side step and `world_findFreeSpot` (shared seed) for the
last-resort teleport after 300 clock ticks.

**Attacking**: `Creature_hitTargetInArc` 0x119938 and relatives (0x1196e8, 0x119850,
0x119a20, 0x119b58) test geometry and call the damage function 0x1e8230 (gameplay area);
`Creature_knockbackTarget` 0x119d10; aiming helpers 0x11a920–0x11aaf8 lead the target by
its velocity and add a spread from the creature's own generator;
`creature_buildElementDamage` 0x1176e0 draws the shared seed once.

**Animation**: `Creature_stepAnim` 0x1162b0 advances the clip and extracts root motion;
`Creature_turnToward` (slot 26); `Creature_applyKnockback` 0x115eb8.

## Weapon holder classes

`Weapon1` (table 0x50cf40), `Weapon2` (0x50ce70) and `WeaponShield` (0x50cda0) are small
non-`GameObject` classes with 24 virtual functions and the table pointer at +0; a creature
points at one from +0x50. Slot 1 is **not** a destructor: it switches a hand on or off
(hand 1: byte +8 and bit 0 of +4; hand 2: byte +0x98 and bit 1). Slot 11 drops the held
model part as a `PhProp` (`creature_dropHeldPartAsProp` 0x117d30), slot 20 draws it
(0x117f08). The other slots are named `Weapon1_slotN` only; their bodies were not read.
Slots 2–8 are called by `Creature_init` for the `FireWeapons`, `FireBurstWeapons`,
`ColdWeapons`, `PoisonWeapons`, `ShockWeapons`, `DiseaseWeapons`, `NoMagicWeapons`
properties. **Observed** 0x10a3fc–0x10a5b0.

## Clone functions (slot 15)

Each is a compiler-generated copy constructor: `pool_new(size)`, copy every field,
`handle_initEmpty` for every handle. The class comes from the last virtual table the
function stores, the size from its `pool_new` argument, "copied after" from the table
stored just before (the nearest base that has its own copy step, not necessarily the direct
C++ base — the doors, for instance, derive from `WorldPart`). **Observed** for all 117.

| Address | Class | Size | Copied after | Address | Class | Size | Copied after | Address | Class | Size | Copied after |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0x11c1a0 | GameObject | 0x4c | - | 0x11c298 | Creature | 0x3c8 | GameObject | 0x11c7f8 | Projectile | 0x54 | GameObject |
| 0x11c910 | Prop | 0x148 | GameObject | 0x11cb70 | ParticleProp | 0x148 | Prop | 0x11cdd8 | ItemProp | 0x190 | Prop |
| 0x11d080 | PhProp | 0x248 | Prop | 0x11d458 | PhIce | 0x250 | PhProp | 0x11d850 | Gold | 0xc0 | GameObject |
| 0x11d9c0 | Container | 0x84 | GameObject | 0x11db30 | Ice | 0x68 | GameObject | 0x11dc68 | Chest | 0x88 | GameObject |
| 0x11dda8 | CosmeticPropAnim | 0x98 | GameObject | 0x11df00 | CosmeticProp | 0x60 | GameObject | 0x11e028 | UserParamProp | 0x170 | GameObject |
| 0x11e160 | TriggerParams | 0x50 | GameObject | 0x11e268 | Trigger | 0x70 | GameObject | 0x11e3b8 | Blocker | 0x4c | GameObject |
| 0x11e4b8 | VehicleBodySphere | 0x54 | GameObject | 0x11e5c8 | WaveMaker | 0x768 | GameObject | 0x11e770 | PushTrigger | 0x4c | GameObject |
| 0x11e870 | Player | 0x590 | Creature | 0x11f188 | Ant | 0x3e8 | Creature | 0x11f728 | AntQueen | 0x3e8 | Creature |
| 0x11fcd0 | AntWave | 0x3d8 | Creature | 0x120250 | Badger | 0x3d0 | Creature | 0x1207c8 | BlackWidow | 0x420 | Creature |
| 0x120df8 | Critter | 0x448 | Creature | 0x121460 | Cyclops | 0x458 | Creature | 0x121a98 | FemaleDarkElf | 0x478 | Creature |
| 0x122120 | FireBeetle | 0x430 | Creature | 0x122700 | FireFly | 0x470 | FireBeetle | 0x122d90 | Froglock | 0x468 | Creature |
| 0x123408 | Generator | 0x3e8 | Creature | 0x1239a8 | Ghoul | 0x3d8 | Creature | 0x123f28 | Gnome | 0x3d8 | Creature |
| 0x1244b0 | Goblin | 0x498 | Creature | 0x124b78 | LavaMonster | 0x430 | Creature | 0x125160 | MaleDarkElf | 0x4f8 | Creature |
| 0x1258a0 | Orc | 0x488 | Creature | 0x125f48 | Scorpion | 0x3d0 | Creature | 0x1264b8 | Skeleton | 0x478 | Creature |
| 0x126b58 | Skelight | 0x468 | Creature | 0x1271c0 | SpiderQueen | 0x430 | Creature | 0x1277f8 | SmallSpider | 0x3c8 | Creature |
| 0x127d60 | CdEyeball | 0x3d0 | Creature | 0x1282d8 | UndeadKnight | 0x478 | Creature | 0x128978 | Vampire | 0x3c8 | Creature |
| 0x128ee0 | VampireLord | 0x480 | Creature | 0x129568 | WoodElfSoldier | 0x3e8 | Creature | 0x129b18 | Wraith | 0x3d8 | Creature |
| 0x12a098 | NPC | 0x480 | Creature | 0x12a6f0 | GutChunk | 0x268 | PhProp | 0x12ab10 | LooseIceChunk | 0x248 | PhProp |
| 0x12aef8 | Torch | 0x8c | GameObject | 0x12b0b0 | Fire | 0x50 | GameObject | 0x12b1b8 | FlyingText | 0x98 | GameObject |
| 0x12b368 | Candle | 0x94 | GameObject | 0x12b528 | Candle2 | 0x50 | GameObject | 0x12b638 | Lantern | 0x98 | GameObject |
| 0x12b800 | Lamp | 0x8c | GameObject | 0x12b9b0 | FireEffect | 0x58 | GameObject | 0x12bad8 | RecallEffect | 0x60 | GameObject |
| 0x12bc08 | IceChunk | 0x50 | GameObject | 0x12bd10 | FrostStormSpell | 0xac | GameObject | 0x12bf00 | GlowingCylinder | 0x70 | GameObject |
| 0x12c050 | GlowingShaft | 0x5c | GameObject | 0x12c178 | MissileTrap | 0x50 | GameObject | 0x12c288 | Shooter | 0x58 | GameObject |
| 0x12c3d8 | WaterSpout | 0x5c | GameObject | 0x12c500 | DummyDamager | 0x74 | Projectile | 0x12c668 | Sparks | 0xb8 | Projectile |
| 0x12c878 | HolyBolt | 0xc0 | Projectile | 0x12ca98 | OniBall | 0xb8 | Projectile | 0x12cca8 | LostSoul | 0xb0 | Projectile |
| 0x12cea8 | Root | 0xc0 | Projectile | 0x12d0c8 | UnholyAura | 0xa0 | GameObject | 0x12d2a0 | IceBall | 0xac | Projectile |
| 0x12d498 | MissileWeapon | 0x1c8 | Projectile | 0x12d878 | AnimatedMissile | 0x98 | Projectile | 0x12d9e0 | playerProjectile | 0x1d0 | MissileWeapon |
| 0x12dde8 | beetleProjectile | 0x1d0 | MissileWeapon | 0x12e1e0 | WebTrap | 0xa0 | GameObject | 0x12e390 | LooseFire | 0x54 | GameObject |
| 0x12e4a8 | GroundPoundEffect | 0x9c | GameObject | 0x12e690 | LightEffect | 0xbc | GameObject | 0x12e8a0 | Player1 | 0x4c | GameObject |
| 0x12e9a0 | charAmbient_Light | 0x4c | GameObject | 0x12eaa0 | charDirectional_Light | 0x4c | GameObject | 0x12eba0 | charDirectional_LightD | 0x4c | GameObject |
| 0x12eca0 | WorldPart | 0x50 | GameObject | 0x12edb0 | DoorSwing | 0x5c | GameObject | 0x12eed8 | RollDoor | 0x5c | GameObject |
| 0x12f008 | DoorSecret | 0x5c | GameObject | 0x12f138 | Switch | 0x50 | GameObject | 0x12f248 | FloorSwitch | 0x58 | GameObject |
| 0x12f368 | FallPlatform | 0x70 | GameObject | 0x12f4c8 | FireTrail | 0x64 | GameObject | 0x12f600 | FireTrailMaker | 0x70 | GameObject |
| 0x12f768 | Savepoint | 0x118 | GameObject | 0x12f9b0 | JumpGate | 0x164 | GameObject | 0x12fc48 | FireBomb | 0x58 | GameObject |
| 0x12fd78 | FireBomblet | 0xb8 | GameObject | 0x12ff98 | FireBombletJr | 0x70 | GameObject | 0x1300e0 | StaticFire | 0x4ac | GameObject |
| 0x130368 | PokeReflector | 0x4c | GameObject | 0x130468 | Lever | 0x54 | GameObject | 0x130580 | Counter | 0x50 | GameObject |
| 0x130688 | Timer | 0x54 | GameObject | 0x130798 | ShopDaemon | 0x50 | GameObject | 0x1308a0 | WeaponRack | 0x98 | GameObject |
| 0x1309f0 | Teleporter | 0x3c8 | Creature | 0x130f58 | poisonGasSpell | 0x70 | GameObject | 0x1310a8 | dustCloud | 0x6c | GameObject |
| 0x1311e8 | PointSourceSound | 0x68 | GameObject | 0x131320 | PushPhysicsProp | 0x118 | GameObject | 0x131570 | StrongStancePhantom | 0x3d8 | Creature |

Notes: 0x1309f0 is the function `names.tsv` calls `clone_50d590`; table 0x50d590 is
`Teleporter`. `Creature_clone` 0x11c298 is also slot 15 of 42 creature classes that add no
fields; `GameObject_clone` 0x11c1a0 of 55 plain classes; 0x11c7f8 of 16 projectile
classes; 0x12d498 of `LavaBomb`. Classes not in the table have no clone of their own. The
only virtual call of slot 15 is in `net_frameLoop` (0x13b540), for the prediction copy, so
for every class but `Player` these functions are never called.

## Per-machine state

| # | What | Kind | Addresses |
|---|---|---|---|
| C1 | `Creature_draw` decrements a status counter and clears flag 0x100 from draw code (FINDINGS D12; flag 0x100 is read only by drawing) | Observed | 0x10b898–0x10b8d4, 0x10babc |
| C2 | `Creature_draw` calls virtual slot 3 of every attached spell. Any spell whose slot 3 changes shared state runs that change a per-machine number of times. The spell bodies are in the skills area and were not checked here. **Checked since** (`docs/issues/draw-sim-leaks.md`, U6): only three Spell classes override slot 3 — `SpellDrowsy` 0x30ed24, `SpellSummonBadger` 0x311034, `SpellResurrect` 0x312f48 — and all three only draw. No shared state is changed through this call | Observed call; effect: none (answered, was Unknown) | 0x10b928–0x10b970 |
| C3 | The MiniBoss block of `Creature_run` walks the list of alive **local** players (count 0x4f8424, slots 0x4f8430, filled only for `net_isLocalSlot` players by `game_rebuildAlivePlayers`) and, when one is within HomeRange, sets cflag 0x80000000 on the creature; otherwise clears it. That bit is object state written from per-machine data. Its only readers are this block and the script `setCFlag` helper 0x1445fc (which uses it to reset the HUD bar), and `Creature_saveState` does not store it, so no route into simulation was found | Observed write; harmlessness Inferred | 0x11399c–0x113ab8 |
| C4 | A path follower that has not reached its next point for 600 clock ticks is teleported there **if `isNearView(1000, pos)` is false**. `isNearView` uses the players except while `g_cullByCamera` is set, when it uses the camera focus (FINDINGS D6/D7) | Observed | call at 0x112c3c |
| C5 | `Creature_updateActive` → `obj_updateActive` decides whether a creature's AI runs; same camera dependence as C4 during cutscenes. Besides the AI, `Creature_spawnScavenger` keys on the inactive→active transition of a finished corpse and then draws `g_randSeed` and constructs a raven or rat (itself another `g_randSeed` draw). The corpse rule in the flag table ("sinks and is deleted once inactive") is a separate matter and needs creature flag 0x1000000 (tail of `Creature_run`: the bit and state 0x14 are tested together); no arena class sets it, so arena corpses stay for the rest of the level (`docs/issues/arena-desync.md`) | Observed | 0x10c168; `Creature_spawnScavenger` 0x1125e0, called at 0x113ae4 |
| C6 | `Creature_processDamage` reads the options value 0x44fdc0 (`g_decalDetail` in other areas) three times. Each read is arranged so that object creation and `GameObject_rand` calls do not depend on it in a net game: the hit-blood branch takes the option **or** network mode (0x1113fc–0x111410); the "gibs because of the option" branch requires network mode off (0x1116bc); inside the gib branch the option only gates decals and effects 1/3/9, which use the cosmetic seed and a separate seed at 0x404468. The gib objects it creates are the ones in `docs/objects.md` O2 | Observed | 0x1113fc, 0x1116bc, 0x1116f8 |
| C7 | Burn and second-effect visuals are emitted from `Creature_run` only when the routine 0x13e180 (`net_objOrGhost` in the netcode symbols: for a local player it returns the prediction copy) returns the creature itself and flag 0x4000000 is clear. The two effect routines (0x1f5210, 0x1f61c0) use only `g_cosmeticSeed` | Observed; not a hazard | 0x113284–0x1132e8, 0x113550–0x1135b4 |
| C8 | Timed damage in `Creature_run` is skipped for the prediction copy (flag 0x20000), including the `g_randSeed` draw of a burning player | Observed; a guard | 0x1132f8, 0x113834, 0x1138d8 |
| C9 | `Creature_applyKnockback` gives players no knockback at all in a net game (and in PvP mode B) | Observed; a guard | 0x115ef4–0x115f04 |
| C10 | `Creature_interact`: the `shop` branch opens the shop menu only when the interacting slot is local (UI); the dialog branch sets `g_scriptActivePlayer` and runs a script, gated by a global latch 0x4fe53c. `Creature_trigger` uses the same latch. The latch's other writers were not traced here. **Traced since** (`docs/issues/draw-sim-leaks.md`, corrections): local UI code does not touch the latch in a net game — `menu_openInventory` calls the acquire only when `g_networkMode` is 0 (test at 0x1c1600, call at 0x1c1608) and `inventory_close` releases only offline (test at 0x1c52a8, call at 0x1c52b0). The other writers are `Creature_interact`, `Creature_trigger`, `dialog_onMsg`, `dialog_free` and one script built-in | Observed; the latch is not acquired or released by local UI code in a net game (answered, was Unknown) | 0x116c30–0x116d2c, 0x11a5f0, latch routine 0x22fc04 (`menuMutex_tryAcquire` in the audio-save symbols); 0x1c1600–0x1c1608, 0x1c52a8–0x1c52b0 |
| C11 | `Creature_pickTarget` overwrites `g_excludeMask` with 8 for its box query and restores it (see objects O6) | Observed | 0x10e004–0x10e050 |
| C12 | `Creature_updateActive` runs `followLostScript` / `followFoundScript` on activity changes, but tests bits 0x400000/0x800000 of the **object** flag word, which are the message-set player bits, not the follow bits of the cflags word. For monsters the test therefore looks permanently false | Observed; that it is a bug is Inferred | 0x10c170–0x10c1e0 |

Checked and found free of camera, local-slot and drawn-set reads: slots 20–25, the cone
searches, the `players_*` pickers, `Creature_moveBy`, `Creature_moveTo`, `Creature_fleeFrom`,
`Creature_stepAnim`, `Creature_takeDamage`, `Creature_deadUpdate`. The effect spawner
0x1ef270 (`fx_spawn` in other areas) is called with ids 0, 1, 2, 3, 9, 10, 0xb, 0x10, 0x11,
0x12 from this area; only id 5 draws the shared seed or creates an object.

## Open questions

- Meaning of slots 36 and 39, of +0xb5 and +0x80. (This item also listed slot 35, +0xcc,
  +0xd4, +0xe4, +0xb4, +0x2f8 and resistances [0], [2], [3]; other documents answer those
  and the tables above now carry the answers.)
- Gameplay names of the +0x316 timer (slot 31) and of the second damage-over-time timer
  +0x350; the callers are in the skills area. (+0x348 is shock and +0x34c poison, see the
  layout.)
- Who clears the dialog latch 0x4fe53c (C10). (Answered since, in row C10: not local UI
  code in a net game.)
- Whether any spell's slot 3 writes shared state (C2). `tools/vtab.py` on the Spell tables
  plus a scan of slot 3 bodies for stores would settle it. (Answered since, in row C2:
  three overrides, drawing only.)
- `Creature_dropLoot` 0x10f2c8, the second half of `Creature_processDamage`
  (experience and drop arithmetic, 0x111dd4–0x112494), `Creature_interactPrompt`, 0x10e720,
  0x114da0 (a `moveTo` variant with no direct callers), 0x10af28, 0x10bca8, 0x10bdb0,
  0x10ab18 and most Weapon-class slots were skimmed or not read.
- The two net functions at the end of the range (0x131b00, 0x131cb8) belong with netcode.
