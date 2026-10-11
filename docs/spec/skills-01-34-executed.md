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
monsters), the angle and matrix functions and the C library. For the Hammer of Wrath also
`item_parseDescriptor` (with `item_randomizeVariant`) and `item_getResourceIndex`; their
model side is `tools/ref_items.py`, reading the item tables from the memory image. A player's is-enemy and
same-team answers are scripted (`Player_isEnemy` is not modelled); `damage_apply`, the
world queries, terrain, `pool_new` and the handle lists are scripted stubs, so what a
skill's damage *does* is `tools/ref_combat.py`'s business, not this test's.

Run of record: `python3 -I -B tools/difftest_skills_a.py` at its defaults (seed 3411, 80
rounds per scenario) — 140 properties PASS, 0 FAIL; 168,450 comparisons, of which 133,993
are statistic-getter calls and 34,457 are calls of can-use, cast, constructor, run, hit and
helper functions - every one equal in calls, bytes, seed and result, and none stopped on one
side only (121 s). The first pass ended at 105 properties and 157,593 comparisons; its
scenarios draw the same random cases as before (their 105 lines are unchanged), and the
second pass added six scenarios (s13, s18, s17, s34, s22, s01) and the store tables after
them.

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
| 13 | fireweapons | **matched** (second pass) | can-use, cast, constructor (both weapons, every entry layout, thrown weapons, monster holder), run: the opening particles, the light in all three phases, the aura, the end by time and by a dead non-player owner |
| 17 | hammerofwrath | **matched** (second pass) | can-use, cast (shaft, light, hammer, spell; pool failures at each step), `HammerOfWrath_ctor` with the real `item_parseDescriptor`, `SpellHammerOfWrath_ctor` / `_run`, `HammerOfWrath_run` in states 0, 3 and 4: target search, the strike at c = 47, the spin's blows, cutscene, blocking owner, target dead or deleted, owner far or deleted, the orientation springs, the particles of the last 120 frames (3000 on the last). States 1 and 2 - which nothing stores - are not modelled and not run |
| 18 | coneoffire | **matched** (second pass) | can-use, cast, the constructor (also as the Mummy calls it), the run with its 28 particles and the damage tick; player and monster owners, levels 0-40 |
| 22 | dismissundead | **matched** (second pass) | cast, `HolyBolt_ctor` with its target loop, run (homing, vertical speed, terrain bounce with its ten probes, expiry), the hit handler on every kind of object |
| 34 | shieldbash | **matched** (second pass) | can-use (shield, weapon class, monster, prediction copy), cast, constructor, run (wind-up, blow, stun roll, prop fallback, end), `SpellShieldBash_windupFx`, slot 4. `Player_animStep` and `Player_move` are recorded call-outs with scripted answers |
| 5, 6, 8, 10 | diseaseshield, diseasetrail, fireflares, blessed | matched in part | statistics, mana cost, can-use ("carries a spell of its class", also for the prediction copy). **Cast and effect not run**: not reached in the second pass either; each has a long presentation-heavy run function (0x2cd318, 0x2cb65c, 0x2dbf10, 0x2df4bc) |
| 1 | wizardbeam | **matched** (second pass) | cast, constructor (the colours, the trails, the side-beam count), run: the chain laid out, the primary target search, no target / a target / side targets, the pull of the main chain and of each side chain, both segment-length rules, the tint, the ten trail draws, the damage frames (every twentieth), the rings, both chain integrations. **One exclusion:** the point arrays handed to the trail functions (6, 4 and 10 points) are built in the caller's frame and are not compared - the calls, handles and counts are, and so is every word stored in the spell and on the targets |

30 of the 34 ids are matched end to end; the other four are matched as far as their numbers.
Not compared for any id: `describeRank` (slot 4, menu text) and the draw functions (slot 5
of the objects).

## 2. Coverage

Basic blocks of the original entered by the run of record, per skill (the functions are
listed by the test's own report; `-v` prints the blocks never entered):

| Skill | Functions run for real | Blocks entered | of | % |
|---|---|---|---|---|
| shared machinery (Skill base slots, spell attach / find, object constructors, projectile step) | 12 | 114 | 149 | 76.5 |
| 1 wizardbeam | 3 | 131 | 131 | 100.0 |
| 2 dodge | 2 | 4 | 4 | 100.0 |
| 3 resistpoison | 3 | 3 | 3 | 100.0 |
| 4 diseasebolt | 4 | 82 | 84 | 97.6 |
| 7 firestorm | 6 | 66 | 68 | 97.1 |
| 9 riposte | 2 | 17 | 17 | 100.0 |
| 11 summonskeleton | 4 | 59 | 64 | 92.2 |
| 12 lightningweapons | 4 | 121 | 125 | 96.8 |
| 13 fireweapons | 4 | 144 | 148 | 97.3 |
| 14 coldweapons | 4 | 125 | 129 | 96.9 |
| 15 undeadshield | 8 | 65 | 65 | 100.0 |
| 16 holystrike | 4 | 79 | 81 | 97.5 |
| 17 hammerofwrath | 6 | 121 | 129 | 93.8 |
| 18 coneoffire | 4 | 37 | 39 | 94.9 |
| 19 regeneration | 2 | 2 | 2 | 100.0 |
| 20 blindinglight | 5 | 41 | 41 | 100.0 |
| 21 repulseundead | 2 | 26 | 26 | 100.0 |
| 22 dismissundead | 4 | 73 | 73 | 100.0 |
| 23 shockoffrost | 7 | 119 | 123 | 96.7 |
| 24 poisonrain | 3 | 42 | 44 | 95.5 |
| 26 poisonweapons | 4 | 118 | 123 | 95.9 |
| 29 diseaseeffect | 2 | 46 | 46 | 100.0 |
| 31 clericroot (and 32 rangerroot) | 4 | 43 | 44 | 97.7 |
| 33 rangercriticalhit | 6 | 56 | 60 | 93.3 |
| 34 shieldbash | 6 | 67 | 67 | 100.0 |
| ids 5, 6, 8, 10 (can-use only) | 1 each | 1 each | 1 | 100.0 |
| **all** | | **1805** | **1889** | **95.6** |

The six skills of the second pass: 573 of 587 blocks (97.6 %). Their fourteen blocks never
entered: the "slot is neither empty nor of this type" arms (Fire Weapons four, Cone of Fire
two); in `HammerOfWrath_run` the six blocks of states 1 and 2 and the two of state 4's
"no owner handle" arm, which follows a return for exactly that case.

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
| 10 | `docs/skills.md`, Spell layout | — | the light fields the constructors of `FireStorm` (+0x70, +0x78) and `SpellUndeadShield` (+0x40, +0x48) leave are 0x7fffffff: they are computed as 1 / (0 × 0) at run time, which this FPU answers with its largest number. The decompile shows the IEEE infinity 0x7f800000 as a constant; a rebuild that copies that constant differs in those four words (presentation). The same holds for `SpellFireWeapons` (+0x40, +0x48; `div.s` at 0x2e3544) and `SpellConeOfFire` (+0x38, +0x40; 0x2f0100) | `FireStorm_ctor` 0x2d41f8 (and 0x2d4048); `SpellUndeadShield_ctor` 0x2ea4d8 |
| 11 | spec §12, Fire Weapons run | "(opening effect …, or for id 13 during the first 30 frames, plus its light)" | the light has three phases: during the opening and while more than 30 frames are left, range = (float)((int)((sin16(frame × 4000) + sin16(frame × 2000)) × 4) + 110); in the last 30 frames range = min(300, left × (1/30) × 110) with the R5900's `min.s` and no truncation (the decompile shows a bit trick there); both range words = it, both inverse squares = 1 / range², position = run position + (cos, sin of the facing) × 18. Each opening particle takes two own balls (position, then velocity), 10 particles a frame | 0x2e4310–0x2e43f8 (`min.s` at 0x2e43d8), 0x2e43fc–0x2e445c |
| 12 | spec §17, Hammer of Wrath, "When a case falls back to state 0 in the same frame the default k and damp apply" | true only for state 3 losing its target | state 4 sets its own values (position k 0.01, damp 0.2, pitch and roll targets 0, yaw velocity −3500) BEFORE it looks at the target, so the frame in which a dead target ends the spin still moves with the spin's values; state 3's PvP exit at c ≥ 61 likewise keeps the strike's values (0.006, 0.15) for that frame | stores 0x2eec20–0x2eec44 against the target test after 0x2eee5c; 0x2eeadc–0x2eeaec |
| 13 | spec §17, "(orientation springs, model matrix, particles … — presentation)" | not given | now executed: yaw += v where v = (v + (s16)(aim − (int)yaw) × k) × (1 − d) with (k, d) = (0.0003, 0.01) at rest and (0.1, 0.6) with a live target; pitch and roll go to their targets (−10000 and 16384 at rest; pitch −20000 for 31 ≤ c ≤ 41 of the strike) with gain 0.05 and damping 0.2, then both velocities get sin16(frame << 10) × 20 and sin16(frame × 800) × 20. Particle count: 2, or (int)((1 − t) × 100) + 2 with t = frames left × (1/120) below 1, 3000 on the last frame; each particle takes one draw of 0x404468 for the sample point (modulo the point count, not tested for 0), three for a jitter and a ball | 0x2ef0b0–0x2ef24c; 0x2ef42c–0x2ef700 |
| 14 | spec §17, the item record | "The item record is produced by `item_parseDescriptor`" | the parser builds the record in its own frame and copies all 0x48 bytes out (as `tools/ref_items.py` says of every record): bytes +6, +0x22, the values of the three empty slots and +0x44 of the hammer's record are whatever that stack held. Nothing known reads them; they are excluded from this comparison | `item_parseDescriptor` 0x1069b8 |
| 15 | spec §22, HolyBolt fields, "+0xb0 … voice handle" | a handle | the constructor never stores +0xb0 (the result of its `sound_playOnObject` at 0x2f5764 is dropped); the run hands the word to `voice_setPosition` every frame (0x2f5d48). It is whatever the block held | 0x2f5764, 0x2f5d48 |
| 16 | spec §22, aim point without a target | "cos16(caster.facing) × 48000" | (cos16 × 12.0) × 4000.0: two truncating products, not one | 0x2f5664, 0x2f5674 (0x2f5688, 0x2f569c for y) |
| 17 | spec §34, the prop fallback | "first entry of `world_collectInSphere`" | the sphere query is handed the SAME list head as the arc query before it (0x2fb3a4), so it adds to that list, as section 49 of `docs/spec/skills-35-68.md` says of Bash; the walk that follows covers both. (The callee's linking is a stub here; the head being shared is executed.) | 0x2fb380–0x2fb3e0 |
| 18 | spec §1, Wizard Beam, damage | "d = (float) trunc(slot10(0, L) × 0.3333333)" | as written - and worth a number, because the constant is below a third and the product truncates: rank 1 (s0 = 135) deals 44 a tick, not 45; the side beams (135 × 0.25 × 0.3333333) 11 | 0x2f2b70 (call 0x2f2bec); 0x2f2c50 (call 0x2f2cd0) |
| 19 | spec §1, "(side-chain geometry and trails — presentation)" | not given | now executed. Side chain k has four nodes relative to the PRIMARY target; nodes 1-3 are pulled toward side target k's middle by (j × 0.3333333)³, measured from the primary target's position plus half its height; its segment length goes toward min(3 × rest, 1.1 × the side target's plane distance from the tip) × 0.3333333 at rate 0.05, an unused chain's toward the rest length; each side target is tinted like the primary one. The side chains then take the same integration step as the main chain, with their own lengths and spoke directions (cos, sin of frame × 600 + k × (0xfffe / n) + the target's facing) | pull 0x2f25d8–0x2f27bc (`powf` at 0x2f265c); integration 0x2f2cd8–0x2f3120 |

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
| SA2 | **Mechanism confirmed.** `HolyBolt_ctor` stores the chosen object as a plain word at +0x64 and makes no `handle_link` for it (80 casts, none); `HolyBolt_run` reads position and flags through that word every frame and clears it only when the object's flag 8 is set. With the target's memory overwritten under the bolt (279 runs) the aim point and the heading followed the overwritten words every time. Also confirmed: the target loop keeps the LAST qualifying undead in box order while only one side has a best - in 33 staged casts with every undead in front the target was the last one in the query's order each time, and in 28 of them that was not the nearest |
| SA3 | **Mechanism confirmed.** `SpellShieldBash_ctor` stores the head entry of its arc query as a plain word at +0x24 (also when it is a later entry that qualified); `SpellShieldBash_run` hands the three words at that address + 0x10 to the owner's slot 26 on every frame, untested: 308 runs after the target's memory had been overwritten, 308 calls with the overwritten words |
| SA4 | **The descriptor is confirmed.** `SpellConeOfFire_run` builds one fire entry (0x15, v1, v2, 0) with v1 = (int)(s0 × 0.25) and v2 = (int)(((float)v1 + (float)v1 × r/65536 × 0.2) × 0.25) - the second 0.25 at 0x2f0e5c - and passes it with minimum and maximum 0 and flags 0x40. In 69 distinct descriptors of the run of record v2 < v1 whenever v1 > 0; for a monster owner at levels 2 and 3 (tier-2 s0 = 4 and 6) the entry is exactly (0x15, 1, 0, 0), i.e. v2 − v1 + 1 = 0, the divisor of `damage_apply`'s remainder at 0x1e990c. A level-1 player gives v1 = 95 and v2 = 23…28. What the console's divide leaves there is still X10's open point |
| SA5 | **Mechanism confirmed.** `SkillCriticalHit_critBonusFor` walks count 0x4f8420 / slots 0x4f8440 in order and skips only the attacker's own slot; the test ran it with lists that lack a player, repeat one, or are empty, and the result follows the list |

## 4a. The prediction copy and these ten skills

The pattern looked for is SB1's: a cast or constructor that the local player's prediction
copy (object flag 0x20000) can reach and that stores into shared state before it tests for
the copy. Three things were executed for it:

- **The flag word.** Bit 0 of Skill +4 ("the copy may cast") is clear in all ten Skill
  objects as the game's own initialiser builds them (read from the executed objects).
- **The gate.** In `Player_castSkill` the test "flag bit 0 clear and caster has 0x20000 →
  return" is at 0x1a4320–0x1a433c, before that function's own can-use call (0x1a4358) and
  before the cast. (Read, not executed: `Player_castSkill` is outside this model.) The
  cast-start code of `Player_run` asks can-use earlier, for the copy too, so can-use is the
  one function of these skills the copy runs.
- **Can-use for the copy.** Every can-use of the ten was run with the copy as caster: none
  stores a byte. Shield Bash's refusal raises a HUD message (local output).

The casts were run for real casters, and the stores of the original outside the stack, the
blocks `pool_new` had just handed out and the shared seed were collected in order (the
test prints them). "Call-outs" are stubs here, so stores inside them are not in the column.

| Id | Skill | Copy may cast (flag bit 0) | First store of cast or constructor outside its own objects | Copy test | Order |
|---|---|---|---|---|---|
| 1 | wizardbeam | no | none (call-outs: eight to twenty `trail_create`, a sound) | none in the class; gate 0x1a4320 | gate first: not reachable |
| 5, 6, 8, 10 | diseaseshield, diseasetrail, fireflares, blessed | no | not executed (casts not modelled) | none found in the casts as read; gate 0x1a4320 | gate first: not reachable |
| 13 | fireweapons | no | the caster's two weapon items, entry slots (first store 0x2e3890; a monster: holder slot 2). Before it: `light_link` | none; gate | gate first |
| 17 | hammerofwrath | no | the caster's flash quads +0x90…+0x9e (0x2efb74–0x2efb94), first thing in the cast | none; gate | gate first |
| 18 | coneoffire | no | none (call-outs: `light_link`, the looping sound) | none; gate | gate first |
| 22 | dismissundead | no | none (call-outs: `light_link`, `handle_link` of the owner, `obj_runEveryFrame`, trail, voice) | none; gate | gate first |
| 34 | shieldbash | no | caster action state +0x58c = 6 (0x2fad68); then the bash clip's event slot 1 **in the shared clip header**: mask byte +0x20 (0x2fadac), time +0x1c (0x2fadb4) | none; gate | gate first |

So none of the ten is an SB1: the copy cannot reach any of these casts. Shield Bash is the
one that writes a shared animation header (as Bash, id 49, does), on every real cast and on
every machine alike, with a constant; its run function does not move the slot (Cyclone's
does, which is what made SB1 visible). If a patch or another build ever set flag bit 0 on
id 34, it would be an SB1 at once: the two stores are 0x44 bytes into a constructor that has
no copy test at all.

## 4b. Proposed ledger text (not applied: `FINDINGS.md` is not edited from here)

| Row | Proposed addition |
|---|---|
| SA2 | Mechanism confirmed by execution (second pass of X20): `HolyBolt_ctor` stores the target as a plain word and links no handle; `HolyBolt_run` read position and flags through it on 279 of 279 runs made after the target's memory had been overwritten. The constructor's loop keeps the last qualifying undead in box order (33 of 33 staged casts; not the nearest in 28) |
| SA3 | Mechanism confirmed by execution: `SpellShieldBash_run` handed the three words at (+0x24) + 0x10 to the owner's slot 26 on 308 of 308 runs after the target's memory had been overwritten |
| SA4 | Executed for Cone of Fire itself: the entry is (0x15, v1, v2, 0) with v2 scaled by 0.25 a second time (0x2f0e5c), v2 < v1 for every v1 > 0, and exactly (0x15, 1, 0, 0) for a monster owner at levels 2 and 3. "Scaled by 0.25 twice" is no longer a reading. The console's remainder for the zero divisor stays open (X10) |
| SB1 (note) | Ids 1, 5, 6, 8, 10, 13, 17, 18, 22 and 34 checked for the same pattern: flag bit 0 is clear for all ten, so `Player_castSkill` turns the copy away before the cast (0x1a4320–0x1a433c); no can-use of the ten stores anything (the casts of 5, 6, 8 and 10 were not executed). Id 34 writes event slot 1 of the shared bash clip in its constructor (0x2fadac, 0x2fadb4) with no copy test of its own - harmless only because of that gate |

No new row and no patch is proposed.

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
- Second pass. `SpellWizardBeam_run` reads nothing per-machine: the frame counter drives the
  trail phases and the damage frames. `HammerOfWrath_run` draws its particles from 0x404468 (per machine); the count
  of those draws depends on nothing shared except the frames left. `SpellShieldBash_run`
  writes 0x402797 = 60 when `net_isLocalSlot` says so and places its wind-up particles on
  `net_objOrGhost(owner)` with a fixed number of own draws; it reads the pad record of the
  owner's slot (`g_pads`, lockstep input). Cone of Fire, Fire Weapons and Dismiss Undead read
  nothing per-machine. Nothing new for the ledger.

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
- Second pass. A raw pointer "going stale" is staged by overwriting the pointed-to memory;
  what the pool really puts there is not simulated. `Player_animStep`, `Player_move` and the
  owner's slot 26 are stubs: Shield Bash is matched as a sequence of calls and stores, not as
  movement. A world query that adds to a list that is not empty (Shield Bash's second query)
  is scripted to put its entries in front of the old ones; that order inside the real query
  is not executed. The Hammer of Wrath's item record is compared without the bytes the parser
  leaves undefined (correction 14). The Wizard Beam's trail point arrays are not compared
  (they are stack data handed to presentation functions; the code that fills them is
  executed and counted in the coverage, the model does not build them).
