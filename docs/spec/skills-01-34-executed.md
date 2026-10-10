# Skills 1–34: what execution confirmed

Companion to `docs/spec/skills-01-34.md`, which was written from reading only. Here the same
rules are code — `tools/ref_skills_a.py` — and that code is compared with the original
machine code by `tools/difftest_skills_a.py`, which runs the original functions under
`tools/ee_emu.py`. The specification itself is not rewritten; where it turned out wrong or
short the correction is in section 3.

**What "executed" means.** `tools/ee_emu.py` is an instruction interpreter for single
functions, not a console and not the live game (`docs/issues/dynamic-tests.md`). The 101
Skill objects are built by the game's own static initialiser (0x16ac74) and statistics pass
(0x1ebca0), run once in the interpreter. Each function under test is then run on objects
the test builds in the interpreter's memory; everything it calls outside the model is a
recording stub answered by a seeded script. **Matched** below means: for every call the
test made, the model and the original made the same calls to the outside in the same order
with the same arguments (particles, lights and sounds included), stored the same bytes with
the same final values (a spell's own generator at +0x10 and an object's at +0x44 among
them), left the shared seed 0x404464 the same after exactly the number of draws the model
counts, and returned the same value. Floats are compared as 32-bit patterns; results are
bit for bit under the interpreter's floating-point model, which is itself an approximation
of the console's unit. Integer division by zero follows what the R5900 is reported to
leave (`div_zero = 'r5900'`), on both sides. Nothing here was observed on a PlayStation 2
or in the live rig.

What runs for real besides the functions of the table: the Skill base slots, `Spell_rand`,
`GameObject_rand`, `GameObject_ctor`, `Projectile_ctor`, `obj_moveAndCollide`,
`creature_addSpell`, `creature_findSpellByType` with the classes' type-info getters, the
creature base functions a call reaches (`Creature_isEnemy` and slots 30, 31, 35, 36, 37 for
monsters), the angle and matrix functions and the C library. A player's is-enemy and
same-team answers are scripted (`Player_isEnemy` is not modelled); `damage_apply`, the
world queries, terrain, `pool_new` and the handle lists are scripted stubs, so what a
skill's damage *does* is `tools/ref_combat.py`'s business, not this test's.

Run of record: `python3 -I -B tools/difftest_skills_a.py` at its defaults (seed 3411, 80
rounds per scenario) — 105 properties PASS, 0 FAIL; 157,593 comparisons, of which 133,993 are statistic-getter calls and 23,600 are calls of can-use, cast, constructor, run, hit and helper functions - every one equal in calls, bytes, seed and result, and none stopped on one side only (184 s).

## 1. Status per skill

| Id | Name | Status | What ran |
|---|---|---|---|
| 1–34 | statistics | matched | slots 8 (plain and randomised, with the seed), 10, 11 (caps 0, 1, 10, 20, −1), 12 (player, monster, no caster, prediction copy), 13 (three handles), 14, 15 and the mana cost: every id, levels 0–40 and five outside, statistics 0–4; the same slots on 4,000 made-up tables (negative values, tier 2 present or not); the base `initStats` |
| 1–34 | tables | matched | every statistic row of the specification against the executed objects (482 checks, 0 differences), and the static reading of `tools/dump_tables.py` against them (400 checks, 0 differences); kind, recast and flag words too |
| 2 | dodge (and 83) | matched | can-use, cast (base), mana cost, `SkillDodge_getStat0Fraction` |
| 3 | resistpoison | matched | can-use, cast, mana cost (all base), base `initStats` |
| 4 | diseasebolt | matched | can-use, cast, constructor, run to the natural end / into the ground / after a hit / with the owner dead or deleted / with the target swapped, the hit handler on every kind of object |
| 7 | firestorm | matched | can-use, cast (player and monster placement), both constructors, the common part, run through the warning delay, flares, ticks and both endings |
| 9 | riposte (and 82) | matched | cast, `SkillRiposte_counterAttack` for player and monster defenders |
| 11 | summonskeleton | matched | can-use, cast, spell constructor and run — the methods of `tools/ref_arena_monsters.py`, here with the real statistics underneath and the skeleton's constructor as a stub |
| 12 | lightningweapons | matched | can-use, cast, constructor (both weapons, every entry layout, thrown weapons, monster holder), run with the aura and both endings |
| 14 | coldweapons | matched | the same |
| 15 | undeadshield | matched | can-use, cast, constructor, run with the aura, the secondary shield's constructor and run, both reflection helpers |
| 16 | holystrike | matched | can-use, cast, constructor, run (homing, expiry, ground, owner gone), the hit handler |
| 19 | regeneration | matched | can-use, cast, `SkillRegeneration_getStat0` |
| 20 | blindinglight | matched | can-use, cast, effect constructor and run, spell constructor and run to the end |
| 21 | repulseundead | matched | cast, `damage_radial` (also with other flag words, minimums and attackers than the cast's) |
| 23 | shockoffrost | matched | can-use, cast, bolt constructor / run / hit, shard constructor / run / hit, the debris and shard release |
| 24 | poisonrain | matched | can-use, cast, constructor (also as the monsters call it, with a sound), run to both endings |
| 25, 27, 28, 30 | diseaseweapons, hatebeam, ballofhate, hateeffect | matched | can-use, cast, mana cost (all base) — there is nothing else |
| 26 | poisonweapons | matched | as 12 |
| 29 | diseaseeffect | matched | `SpellDiseaseEffect` constructor and run: swarm, contagion, the tick, the source deleted, the end (the Skill object's can-use and cast are the base functions run for ids 3, 25, 27, 28, 30) |
| 31, 32 | clericroot, rangerroot (and 52, 85) | matched | can-use, cast, spell constructor, run through both phases, the resist roll and both endings |
| 33 | rangercriticalhit (and 53, 81) | matched | can-use, cast, constructor, run, `SkillCriticalHit_critBonusFor` |
| 5, 6, 8, 10, 13, 17 | diseaseshield, diseasetrail, fireflares, blessed, fireweapons, hammerofwrath | matched in part | statistics, mana cost, can-use ("carries a spell of its class"). **Cast and effect not run**: not reached in the time available; each has a long presentation-heavy run function (0x2cd318, 0x2cb65c, 0x2dbf10, 0x2df4bc, 0x2e3b28, 0x2ee068) |
| 18 | coneoffire | matched in part | statistics, mana cost, can-use. Cast, constructor and run (0x2f02fc) not run — so the "maximum scaled by 0.25 twice" reading of section 18 is still a reading |
| 1, 22 | wizardbeam, dismissundead | matched in part | statistics, mana cost, can-use (base). Cast and effect not run (0x2f1a44; 0x2f5248, 0x2f57b0, 0x2f5fb4) |
| 34 | shieldbash | not run | statistics and mana cost only. The spell drives `Player_animStep` and `Player_move`, which the specification itself leaves open |

24 of the 34 ids are matched end to end; the other ten are matched as far as their numbers.
Not compared for any id: `describeRank` (slot 4, menu text) and the draw functions (slot 5
of the objects).

## 2. Coverage

Basic blocks of the original entered by the run of record, per skill (the functions are
listed by the test's own report; `-v` prints the blocks never entered):

| Skill | Functions run for real | Blocks entered | of | % |
|---|---|---|---|---|
| shared machinery (Skill base slots, spell attach / find, object constructors, projectile step) | 12 | 114 | 149 | 76.5 |
| 2 dodge | 2 | 4 | 4 | 100.0 |
| 3 resistpoison | 3 | 3 | 3 | 100.0 |
| 4 diseasebolt | 4 | 82 | 84 | 97.6 |
| 7 firestorm | 6 | 66 | 68 | 97.1 |
| 9 riposte | 2 | 17 | 17 | 100.0 |
| 11 summonskeleton | 4 | 59 | 64 | 92.2 |
| 12 lightningweapons | 4 | 121 | 125 | 96.8 |
| 14 coldweapons | 4 | 125 | 129 | 96.9 |
| 15 undeadshield | 8 | 65 | 65 | 100.0 |
| 16 holystrike | 4 | 79 | 81 | 97.5 |
| 19 regeneration | 2 | 2 | 2 | 100.0 |
| 20 blindinglight | 5 | 41 | 41 | 100.0 |
| 21 repulseundead | 2 | 26 | 26 | 100.0 |
| 23 shockoffrost | 7 | 119 | 123 | 96.7 |
| 24 poisonrain | 3 | 42 | 44 | 95.5 |
| 26 poisonweapons | 4 | 118 | 123 | 95.9 |
| 29 diseaseeffect | 2 | 46 | 46 | 100.0 |
| 31 clericroot (and 32 rangerroot) | 4 | 43 | 44 | 97.7 |
| 33 rangercriticalhit | 6 | 56 | 60 | 93.3 |
| ids 5, 6, 8, 10, 13, 17, 18 (can-use only) | 1 each | 1 each | 1 | 100.0 |
| **all** | | **1235** | **1305** | **94.6** |

Blocks never entered are of four kinds: the "slot is neither empty nor of this type" arm of
the inlined descriptor fill, which cannot be taken on a fresh record (one or two blocks in
every hit handler and tick); the `GameObject_ctor` paths for a hidden object and for a
property list, which no object of this range has (the model refuses them);
null-`this` guards before a self-delete; and in `SkillCriticalHit_critBonusFor` the
`rank < 1` arm behind a non-zero best rank.

## 3. Corrections to `docs/spec/skills-01-34.md` and `docs/skills.md`

Each was found as a mismatch between the specification's reading and the executed code, or
settles something the specification left open.

| # | Where | The document says | Executed | Address |
|---|---|---|---|---|
| 1 | spec §21, Repulse Undead | the souls' velocity is `(cos16(a), sin16(a), 50.0)` | `(cos16(a) × 450, sin16(a) × 450, 50)` | 0x2f4d8c–0x2f4dd8 |
| 2 | spec §0.6, projectile step | a water impact makes "one draw from the object's own generator (splash sound variant)" | the draw is made and thrown away; the clip number given to the name format is the constant 1 | 0x150c14–0x150c2c |
| 3 | spec §0.2 and `docs/skills.md` (Skill layout, slot 11) | tier 2 is absent when its first level "is 0xffff" | the test is the sign (`bltz`): any negative first level means "use tier 1". Constructors store −1, so nothing changes for the shipped tables | 0x3c86d8 |
| 4 | spec §7, Fire Storm | "argument order of the second constructor only as far as the stored fields" | `FireStorm_ctor2(object, owner, position, radius, damage, duration in frames, flare period; flare scale)` — matched with its only variant behaviour (variant word 1, straight flares, no looping sound) | 0x2d4048 |
| 5 | spec §24, Poison Rain | three statistic reads in the constructor | four: the duration statistic is read a second time, after `pool_new` for the light succeeded, for the light's last number (`duration + 0.675`). No draw involved; the call order matters to a rebuild that logs virtual calls | 0x2f914c |
| 6 | spec §31, Root cast | "attach new SpellRoot …; count += 1" | when `pool_new` gives nothing `creature_addSpell` is still called (with 0) and the count still rises, so a failed allocation uses up one of the `n` targets. The level first goes through slot 14 (level, 20) | 0x2e6700–0x2e6728 |
| 7 | spec §33, Critical Hit | `return level ? slot10(0, level) × 0.01 : 0` | the level chosen goes through slot 14 (level, 20) first (no effect in this build); the aura owner's ranks are asked in the order 53, 81, 33 (three `player_getSkillRank` calls for every candidate that carries the spell) | 0x2e7910; 0x2e7818–0x2e7840 |
| 8 | spec §12, weapon buffs | one level for all constructor reads | the first duration read uses the level argument as passed (a full register), every later read the level byte stored in the spell, signed. They differ only above level 127 | 0x2e258c against 0x2e25ac |
| 9 | spec §15, Undead Shield | "if o carries neither …" | both look-ups are always made (the secondary one even when the first found a shield) — two type-info calls and two list walks per player in the box | 0x2eadb8–0x2eade8 |
| 10 | `docs/skills.md`, Spell layout | — | the light fields the constructors of `FireStorm` (+0x70, +0x78) and `SpellUndeadShield` (+0x40, +0x48) leave are 0x7fffffff: they are computed as 1 / (0 × 0) at run time, which this FPU answers with its largest number. The decompile shows the IEEE infinity 0x7f800000 as a constant; a rebuild that copies that constant differs in those four words (presentation) | `FireStorm_ctor` 0x2d41f8 (and 0x2d4048); `SpellUndeadShield_ctor` 0x2ea4d8 |

Confirmed as written, among the points the specification flags as surprising: the dodge
fraction (§2); Holy Strike's maximum being one higher than the usual rounding (§16); the
weapon buffs comparing a frame count with the existing entry's minimum damage, in the
constructor and in the aura (§12); Blinding Light looking only at the nearest creature of
the arc (§20); the contagion and the 1-point tick of a level-0 disease (§29); the Root
resist roll `(d mod 100) + 1` against statistic 2 and the push-back of a player victim
(§31); `damage_radial` going straight to slot 2 (§21); the Critical Hit aura (§33); the
`SpellSecondaryUndeadShield` and `SpellDiseaseEffect` leaving their Skill word null (§C).

## 4. Hazard rows SA1–SA5 of `FINDINGS.md`

| Row | Execution |
|---|---|
| SA1 | **Mechanism confirmed.** `SpellBlindingLight_ctor` stores the caster argument as a plain word at +0x1c and `SpellBlindingLight_run` hands that word to `damage_apply` as the attacker on every tick, with no test (matched over the spell's whole life). What a stale pointer then leads to is not something this test can show |
| SA2 | Not executed (Dismiss Undead was not run) |
| SA3 | Not executed (Shield Bash was not run) |
| SA4 | Not executed here: Cone of Fire's run was not reached, so the descriptor values it hands to `damage_apply` are still a reading. (The divide itself is X10's.) |
| SA5 | **Mechanism confirmed.** `SkillCriticalHit_critBonusFor` walks count 0x4f8420 / slots 0x4f8440 in order and skips only the attacker's own slot; the test ran it with lists that lack a player, repeat one, or are empty, and the result follows the list |

## 5. Reads of per-machine state

Nothing new that feeds the simulation. For the record, what the executed functions read or
write outside lockstep state, all of it already in the specification or the area document:

- `SpellCriticalHit_run` asks `net_objOrGhost(owner)` and places its ring around the answer
  (`docs/skills.md`, item 4). Executed: the number of own draws is the same whatever it
  returns; the number of `particle_spawn` calls is not (a ring point whose ground is more
  than 72 from the ghost's z is dropped) — presentation only.
- `SkillRiposte_counterAttack` draws its 200 particles from the cosmetic generator 0x404460.
- `SkillRoot_canUse` raises a HUD message; `SkillBlindingLight_cast` calls
  `gfx_setColorOffset`.
- `SpellDiseaseEffect_run` hands the word at 0x4f8498 (a texture handle) to `glow_add`
  sixteen times a frame. Not listed before; it is a load-time pointer used for drawing only.

One thing the test's own world brought out, not a per-machine read: `BlindingLightEffect_ctor`
calls slot 31 on every object its caster's is-enemy accepts (0x2f4190). That is safe only
because both is-enemy functions admit creatures only: when an early version of the scripted
answer accepted an object that was not a creature, the original ran off the end of that
object's table and into unrelated code.

## 6. Limits of this comparison

- `damage_apply`, the world queries and terrain are stubs: the test proves which calls a
  skill makes with which arguments, not what follows from them.
- `Player_isEnemy` is scripted. The player-caster paths are therefore matched for every
  answer it could give, not for the answer the game would give.
- Object lifetime is not simulated: a self-delete is a recorded call, and the driver stops
  running the object. Run order between a spell and the objects it owns (the specification's
  open point for ids 8 and 15) is not something a single-function test settles.
- The level range is 0–40 plus a few values outside; the statistics sweep is exhaustive in
  that range for all 34 ids, the scenarios draw from it.
