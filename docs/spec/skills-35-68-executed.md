# Skills 35–68: what was executed

Companion to `docs/spec/skills-35-68.md`. That document was written from reading only. This
one says which parts of it have since been **executed**: the original machine code of the
skill functions was run, function by function, under `tools/ee_emu.py` (an instruction
interpreter, not a console, and not a running game), beside a Python model written from the
specification, `tools/ref_skills_b.py`, and the two were compared by
`tools/difftest_skills_b.py`. Nothing here was seen on a PlayStation 2 or in an emulator of
one; no skill was cast in a live game.

"Matched" below means: for every call the test made, the model and the original made the
same calls to everything outside the model, in the same order with the same arguments;
stored the same bytes with the same final values (the spell's and the object's own
generator state, the two per-machine generators 0x404460 / 0x404468 and the handle-node pool
included); left the shared seed 0x404464 at the same value, advanced exactly as often as
the model counts; and returned the same value. Floats are compared as 32-bit patterns, bit
for bit, under the interpreter's default floating-point model (`ps2`: add, subtract and
multiply truncate; `docs/issues/dynamic-tests.md` gives its limits). A match is a statement
about the inputs the test covers and nothing more; section 2 says what those are.

Reproduce (needs your own SLUS_209.73; exits 0 without it):

```
python3 tools/difftest_skills_b.py            # everything, about 8 to 14 minutes
python3 tools/difftest_skills_b.py --quick    # a tenth of the scenarios, about 4 minutes
python3 tools/difftest_skills_b.py -k froststorm -v   # one skill of the third pass, under a minute
python3 tools/difftest_skills_b.py -k cyclone -v
python3 tools/test_ref_skills_b.py            # the model's own logic, no game files
```

## 1. Status per skill

| Id | Name | Status | What was executed |
|---|---|---|---|
| 35 | charge | **matched** (second pass) | cast (player, monster; the state store on `net_objOrGhost`), `SpellCharge_ctor`, `_run` (trails, particles, the end by time, by contact and by a clock behind the cast), `_getStat3Scaled`, `_onContact` (creature, prop, wall, the area part and its ring) |
| 36 | darkness | **matched** (second pass) | cast, `DarknessProjectile_ctor`, `_run`: flight, the terrain stop, attaching with a damage call per enemy of the box, the blind roll on frames divisible by 30, the caster deleted, the end |
| 37 | shock | **matched** (second pass) | cast (player, monster, no caster), `ShockProjectile_ctor`, `_run` (terrain stop, the hit test on every eighth frame, the candidate list, the damage calls, the beams, the fade and the end), `_buildChain`, `_inChain` |
| 38 | groundpound | **matched** (second pass) | can-use, cast (the clip's four event slots), `GroundPoundEffect_ctor` (dry ground, water, a ledge), `_run` (the first run with its damage and stun rolls, the 30 after it). The shoves and the creation of the effect are in `Player_run` state 10, outside this range |
| 39 | convertenemy | **matched** (second pass) | can-use, cast, constructor with its target choice, run: the spiral, the roll for every target, the immunity and resistance notices, the end |
| 40 | convertundead | **matched** (second pass) | as 39, with its own target rule; can-use with its box query |
| 41 | cyclone (and 84) | **matched** | can-use, cast, `SpellCyclone_ctor`, `_run`, `_updateFx`; player, prediction-copy and monster casters; offline and net game; the spin ended by the status bits, by the action state and through the stop clip |
| 42 | harmtouch | **matched** | can-use, cast, constructor, the countdown, `SpellHarmTouch_applyToHit` |
| 43 | firearrow | **matched** | can-use, cast, both constructors, run, hit handler, end; player and monster owners |
| 44 | coldarrow | **matched** | as 43 |
| 45 | poisonarrow | **matched** | as 43 (the gas cloud it leaves is a call-out) |
| 46 | multifire | matched in part | can-use and cast. The arrows are plain `MissileWeapon` objects: the seventeen constructor arguments are compared, their run and hit handler (`docs/spec/skills-35-68.md` S.8) were not modelled. `MultiFireProjectile` (MaleDarkElf only) not run |
| 47 | explodearrow | **matched** | as 43; the explosion with its box query |
| 48 | archery | **matched** | `SkillArchery_getStat0Fraction` at every level; base can-use and cast |
| 49 | bash | **matched** | can-use, cast, constructor, run (wind-up, strike, stun roll, prop fallback, end), `SpellBash_windupFx` |
| 50 | minorhealing | **matched** | cast, constructor, run to the end |
| 51 | ancestralcall | **matched** (second pass) | can-use, cast and constructor for a player, a monster and the **prediction copy**, run (the cast animation with its beams and sounds, the ring, the tint on players in reach, the end), `_queryFor` with both outputs, the two fraction getters, `_tintAndGlow` |
| 52 | root | **matched**, in `tools/difftest_skills_a.py` | the class is `SkillRoot` / `SpellRoot` of ids 31 and 32: the same four functions, run there with the Skill object of id 52 among the four (scenario s31: can-use, cast, constructor, run to both endings). Here only its statistics and mana cost |
| 53 | criticalhit (and 33, 81) | **matched** | can-use, cast, constructor, run, `SkillCriticalHit_critBonusFor` |
| 54 | holyshield | **matched** | cast, constructor, run, `SpellHolyShield_absorb` |
| 55 | healing (and 86) | **matched** | cast, constructor, run for player and non-player owners, PvP mode A on and off |
| 56 | coneoffrost | **matched** (third pass) | cast, `SpellConeOfFrost_ctor`, `_run` (the three particle fans, the projectile of every eighth frame, the light) for player and monster owners; the object that carries the damage - `DummyDamager_ctor`, `_run` (its 45 frames, the terrain, the burst), `_onTouch` (the victim's is-enemy answer, the one delivery, a touch without an owner) - also built directly with every combination of its behaviour bits, as the monsters use it |
| 57 | shockoffire | **matched** (third pass) | cast (player and monster; with and without splash), `Sparks_ctor`, `Sparks_run` (flight with its particles, terrain, the time limit, the burst with `world_damageInRadius`, owner deleted), `Sparks_onTouch` (the first enemy only; the light with the pool refusing) |
| 58 | froststorm | **matched** (third pass) | cast (player: moved ahead; monster: the wait and the warning light built in line), `FrostStormSpell_ctor`, `FrostStormSpell_run` (snow, shards with their shared draws, ground particles, the tick with and without a caster, the shrinking end), `FrostStormIceShard_run` (fall, landing, time-out) |
| 59 | lifetap | **matched** | cast (returns nothing), `SkillLifeTap_getStat0Fraction`, `_getStat1`. The pending-pool logic lives in the damage and player code and is outside this range |
| 60 | Blunt | **matched** | no function of its own: every slot is the base's |
| 61 | Slashing | **matched** | as 60 |
| 62 | strongstance | **matched** | cast, `SkillStrongStance_getStat0`, `SkillStrongStance_trigger` (the phantom it creates is a call-out) |
| 63 | naturalresistance | **matched** | `SkillNaturalResistance_getStat0Fraction` |
| 64 | stunningstrike | **matched** | `SkillStunningStrike_getStat0ForTarget`, `_spawnEffect` |
| 65 | giantgrowth | **matched** (third pass) | can-use, cast (a player; a monster is refused), `SpellGiantGrowth_ctor`, `_run`, `_stepScale` (grow, hold, shrink, the thirty frames after; a scale changed from outside), `_emitParticles` (47 / 4 / 11 slots), `_getOwnerField0dc`; the owner deleted. The destructor (which puts the scale and the speed factor back) is not modelled, as for every spell |
| 66 | planarwind | **matched** (third pass) | cast, `SpellPlanarWind_ctor` with its one target query, `_run` to its end: the strike of every target the front has passed (both statistic paths, the PvP roll, the burn roll, hit particles with and without a model), targets deleted before the front arrives, the stream particles, terrain, the 54th run |
| 67 | shadowstep | **matched** (second pass) | cast at every rank (no fire, the centre fire, the ring), the enemies that lose their target and are pulled, `SpellShadowStep_run` for its 25 calls offline and in a net game. `StaticFire_ctor` is a call-out; the fire itself is not modelled (section 4a executes it as it is) |
| 68 | resurrect | **matched** | can-use, target search, `_isSlotBeingRaised`, cast, constructor, run in both modes, `SpellResurrect_onOwnerDeath` |

Thirty-three of the 34 ids are now matched end to end (52 in the other test) and one, 46,
in part as before - its arrows are plain `MissileWeapon` objects, compared as constructor
arguments. The first
pass ended at twenty, the second at twenty-nine; the third added the five that were left -
56 coneoffrost, 57 shockoffire, 58 froststorm, 65 giantgrowth and 66 planarwind - each with
its cast, constructors and every per-frame function, and with the two effect classes that
live outside the skills area (`DummyDamager`, `Sparks`) and the Frost Storm's objects.

Not modelled for any id: `describeRank` (slot 4, menu text), the icon slot, the static
initialisers that build particle definitions, the draw slots, and the destructors (a spell
ending itself is the recorded call of its slot 1).

## 2. What the comparison covers

**Statistics, all 34 ids** — exhaustive: slots 10, 11 (caps 0, 10, 20, −1), 12 (no caster,
player, monster; caps 0 and 10), 13 (empty handle, player, monster) for statistics 0–4 at
levels 0–40, 41, 60 and −1; slot 8 with and without the random spread (spreads 0.1–1.5,
random seeds); slots 5, 14, 15 per level: 109,208 calls, no mismatch. The Skill objects are
the executable's own: the test runs the static initialiser 0x16ac74 and the statistics
set-up 0x1ebca0 first, so no table is embedded in the model or the test.

**Shared machinery** — the Skill base on a synthetic object (negative steps, both tiers);
`handle_link`, `handle_clear`, `handle_removeNode`, `list_push` and the list iterator on
random lists (objects destroyed, nodes linked and removed during a walk);
`creature_addSpell` and `Creature_updateSpells` (newest spell first); `Spell_rand`,
`GameObject_rand`; `Projectile_ctor`; `obj_moveAndCollide` (terrain back-off, the water
splash, overlaps).

**Per skill** — seeded random scenarios: player and monster casters (and the prediction
copy for Cyclone), levels 1–40, the pool refusing a block (5 % of allocations), targets in
and out of range, owners destroyed in flight, the spell or arrow run to its natural end.

What is a stub: every virtual call on a creature, player or prop; `damage_apply`; world
queries; animation; object constructors other than `Projectile_ctor`; the pool; particles,
lights, sound, text. Their answers are scripted; the calls and arguments are compared.
Three things follow from that:

- `GameObject_ctor` and the constructors built on it (`LightEffect`, `GlowingShaft`,
  `poisonGasSpell`, `MissileWeapon`, `StrongStancePhantom`) are stubs whose script makes the
  one shared draw the specification says the real constructor makes. The draw **count** of
  each skill function is therefore executed only up to those call-outs; the draw inside
  them rests on `docs/spec/object-system.md`.
- The order in which a world query returns objects is scripted, not executed.
- A null or stale pointer the original does not test stops both sides (counted as "stopped
  on both"); what the console would do with it is not modelled.

**Second pass** - the same kind of scenario for ids 35-40, 51 and 67, appended after the
sections of the first pass so that those draw the same random cases as before (their 95
result lines are unchanged). Casters: the four players, monsters, the prediction copy
(can-use of every id; cast of 51), and no caster where the code allows one (Shock, the
Ground Pound effect). New stubs with scripted answers: trails, beams, `StaticFire_ctor`,
`FlyingText_ctor`, `Player_clampToScreen` (hands back a corrected velocity),
`obj_moveWithCollision`. `world_collectObjectsInBox` answers with random objects, as in
the first pass: which objects a box holds is not executed, what the code does with each
kind of object is.

**Third pass** - the same kind of scenario for ids 56, 57, 58, 65 and 66, appended after
everything else, so that the 144 result lines of the first two passes are unchanged (they
were compared line by line with a run made before the pass). Casters: the four players and
the monsters; a monster's Giant Growth is refused by the cast, which is executed too. The
objects a skill makes are run as well: every `DummyDamager` a Cone of Frost channel
creates, to its end; the spark; the storm and up to five of its shards at a time. The
`DummyDamager` is also built directly with the behaviour bits other creators use (fire,
"delete on any contact", the flag bit), because the class is shared with the monsters. New
stubs with scripted answers: `voice_setPosition`, `world_damageInRadius`; `sound_playAtPos`
now hands back a handle (the Cone keeps it) and `model_getSamplePoint` can hand back the
3×3 matrix Giant Growth asks for. Run for real besides the functions of the table:
`mat3_rotateAxis` and `mat3_setRotZ` (model side: `tools/ref_core.py`) and the C library's
double-precision helpers through which the storm takes −|z|. `GameObject_ctor` is still the
stub that makes the shared draw, so the storm, its warning light and its shards are compared
from that call on; `StaticFire_ctor` and `LightEffect_ctor` likewise. Not staged: a model
without sample points (the test stops on a division by zero, section 5), a null caster,
and levels above 40.

A check of the comparison itself, made once by hand and not part of the test: four
deliberate errors in the model of the third pass - the sign of the snow's fall, the Planar
Wind's particle mask, Giant Growth's hold test one frame off, one discarded draw of the
spark left out - each turned its section to FAIL (calls, and bytes where a generator or a
field is involved).

Coverage of the original as executed (basic blocks entered / basic blocks of the function
bodies; full run, seed 3568, after the third pass):

| Part | Functions | Basic blocks | Instructions |
|---|---|---|---|
| shared machinery (Skill base, lists, iterator, spell walk, generators, projectile base) | 23 | 160 of 161 | 1009 of 1016 |
| 41 cyclone | 6 | 62 of 63 | 1063 of 1066 |
| 42 harmtouch | 6 | 24 of 24 | 399 of 399 |
| 43 firearrow | 8 | 49 of 53 | 691 of 699 |
| 44 coldarrow | 8 | 76 of 78 | 1363 of 1369 |
| 45 poisonarrow | 8 | 48 of 48 | 848 of 849 |
| 46 multifire | 3 | 25 of 27 | 394 of 409 |
| 47 explodearrow | 8 | 47 of 47 | 802 of 803 |
| 48 archery | 2 | 2 of 2 | 42 of 42 |
| 49 bash | 6 | 67 of 67 | 707 of 708 |
| 50 minorhealing | 4 | 15 of 15 | 214 of 214 |
| 53 criticalhit | 7 | 58 of 61 | 611 of 617 |
| 54 holyshield | 5 | 22 of 22 | 401 of 401 |
| 55 healing | 4 | 52 of 52 | 617 of 618 |
| 59 lifetap | 4 | 4 of 4 | 76 of 76 |
| 62 strongstance | 4 | 12 of 12 | 255 of 255 |
| 63 naturalresistance | 1 | 1 of 1 | 29 of 29 |
| 64 stunningstrike | 2 | 15 of 15 | 149 of 149 |
| 68 resurrect | 8 | 67 of 67 | 838 of 838 |
| 35 charge (second pass) | 6 | 65 of 65 | all |
| 36 darkness | 5 | 43 of 43 | all |
| 37 shock | 6 | 110 of 112 | 1054 of 1061 |
| 38 groundpound | 5 | 82 of 85 | 1098 of 1116 |
| 39 convertenemy | 5 | 50 of 51 | 504 of 512 |
| 40 convertundead | 5 | 55 of 56 | 536 of 543 |
| 51 ancestralcall | 9 | 81 of 81 | all |
| 67 shadowstep | 4 | 46 of 46 | all |
| 56 coneoffrost (third pass; with `DummyDamager`) | 7 | 62 of 68 | 1013 of 1032 |
| 57 shockoffire (with `Sparks`) | 5 | 47 of 49 | 786 of 790 |
| 58 froststorm (with the storm and its shards) | 5 | 91 of 94 | 1798 of 1806 |
| 65 giantgrowth | 8 | 45 of 45 | all |
| 66 planarwind | 4 | 45 of 45 | all |
| **all** | 192 | **1629 of 1660** | **21848 of 21971** |

284,354 calls were compared in that run (265,003 after the second pass, 235,931 after the
first); none mismatched. 169 result lines, all PASS: the 144 of the first two passes, word
for word as before, and five for each of the five new sections. The run took 801 s on a
machine that was busy with other work (the run before the third pass took 300 s there);
eleven of its calls stopped on both sides, all of them the `DummyDamager` touch without an
owner (section 5).

Of the five skills of the third pass 290 of 301 blocks were entered (the rows above count
each skill's mana-cost slot too). The eleven missed are all the same thing: the "this slot
of the record is already in use" arms of the inlined descriptor fill - six in
`DummyDamager_onTouch` (two entry types), two in `Sparks_onTouch`, three in the Frost
Storm's tick - which a record built two instructions earlier cannot reach.

Of the eight skills of the second pass 532 of 539 blocks were entered; the seven missed are
the "slot already in use" arms of Shock's descriptor fill (two), the statistic-0 read of a
Ground Pound without an owner (which can damage nothing) and four rounding branches that
need a negative product.

The thirteen blocks never entered by the first pass: rounding branches that need a negative product
(Cyclone's effect, MultiFire's damage share); the "slot already in use" tails of the
descriptor loops in the FireArrow and ColdArrow hit handlers (the descriptor is always
fresh); in CriticalHit the paths for a negative rank and for a Skill object whose id is not
33, 53 or 81; the free branch of `iter_end`.

## 3. Frame counts settled by execution

Section 1.8 of the specification says most quoted counts assume round-to-nearest and shift
by one frame under the console's arithmetic. Executed under the interpreter's default model
(`ps2`), number of run calls until the thing ends itself:

| What | Executed | Specification |
|---|---|---|
| Skill arrow (43, 44, 45, 47) that meets nothing | ends in run 601, **after moving 601 times** | "age ≥ 601: end"; range quoted as 600 steps |
| HarmTouch unused (0.661 s) | 40 | 40 |
| MinorHealing | 90 | 90 |
| Healing | 68 | 68 |
| HolyShield, N = 10 … 20 s | 60 N + 1 for every N: 601, 661, 721, 781, 841, 901, 961, 1021, 1081, 1141, 1201 | section 54 quotes 600, 660, 721, 781, 841, 901 …; section 1.8 predicts 601, 661, 721 |
| CriticalHit, N = 8 … 13 s | 60 N: 480, 540, 600, 660, 720, 780 | section 53 gives both variants; the truncating one holds |
| Resurrect, N = 1 … 13 s, total | 60 N: 60, 120, 180, 240, 300, 360, 420, 480, 540, 600, 660, 720, 780 | table in section 68: 61, 121, 181, 241, 300 … 600, 660, 721 |
| Resurrect, call that respawns the target (several players) | 60 N − 14: 46, 106, 166, 226, 286 … 586 | 47, 107, 167, 227, 286 … 586 |
| ShadowStep | 25 | 25 |
| ConvertEnemy / ConvertUndead, the call that rolls and ends the spell | 33 / 31 | 33 (section 39) |
| Ground Pound effect object | 31 runs, damage on the first | 31 |
| Charge without contact | ends in the run where frame − cast frame is 46 | 46 |
| `DummyDamager` of the Cone of Frost that meets no terrain (third pass) | deletes itself in its 45th run, after 44 moves | 44 moving frames, destroyed on the 45th run |
| Spark of Shock Of Fire that meets nothing | bursts and deletes itself in its 600th run, after 599 moves | "at most 600 frames" |
| Frost Storm, runs with the factor 0.95 before it deletes itself, by radius | 24 → 14, 36 → 22, 48 → 28, 72 → 35, 132 → 47 | 14, 22, 28, 35, 47 |
| Giant Growth, from the cast to the run that ends the spell (scale 1.0 at the cast) | rank 1: 469, rank 2: 539, rank 10: 845 | 469, 539, 845 |
| Planar Wind over flat ground | 54 | 54 |

Both rows of the table in section 1.8 are confirmed for every N tried. The statistic table
of section 1.8 was also executed: tier 1 (ranks 1–20) gives the same integer under the
console arithmetic and under round-to-nearest for every statistic of ids 35–68, and tier 2
(levels 1–40) differs in exactly the eleven places listed there, the console value one
lower.

## 4. SB1 — confirmed

FINDINGS row SB1 says `SpellCyclone_ctor` writes a shared animation-clip header before its
prediction-copy test. Executed, three parts (`difftest_skills_b.py -k sb1`):

1. **The stores.** `SkillCyclone_cast` run for a caster with object flag 0x20000: the only
   stores into the clip header are 0x2d1978 (mask byte +0x18 = 1) and 0x2d197c (time +0x14
   = 0.05 s, 0x3d4ccccc); the branch at 0x2d19d0 then skips the voice line, the sound and
   the target list. The clip is what `res_find(class lump, "cyclone1.anm")` returns, so every
   object of that class - the real player, its copy, another player of the same class -
   gets the same header (read, not executed: `res_find` is a stub here).
2. **The reader.** The executable's `anim_advance` 0x16d748 run on a state playing that
   clip reads the four slot times at 0x16d874 and the mask at 0x16d898, and returns the mask
   only on the tick whose window contains the slot time. `SpellCyclone_run` gets that mask
   through `Player_animStep`; on bit 1 it takes 0.05 s off the spin time and moves the slot
   time 0.05 s on **in the header** (0x2d1b64–0x2d1b84).
3. **The consequence.** One player's Cyclone was run from the cast to the tick its stop clip
   starts, the event bits coming from the real `anim_advance` on the shared header, once
   undisturbed and once with a prediction copy of the same class casting Cyclone in between
   (the copy's spell is destroyed at once; only the constructor's stores remain). The spin
   ended later in 9 of 9 cases: clip of 20 ticks, level 1: tick 19 without, 30 or 36 with
   the copy; 30 ticks, level 1: 28 against 49 or 55; 30 ticks, level 12: 88 against 109 or
   115. The clip lengths are stand-ins (the real clip is disc data); the mechanism does not
   depend on them.

So the route is real under execution: on the machine that owns the copy, and only there,
another same-class player's spin lasts longer. Its `Player_move` calls, hits and the end of
action state 6 then fall on different frames on that machine. Still not shown: that two
players of one class do spin within those frames of each other in a real game, and what
the live game does (no skill has been cast on the rig).

G22 (`SpellCyclone_run` starts the stop clip a second time on the "object or copy") was
executed as well: with `g_networkMode` set the second `anim_startBlendInOut` call is made
on whatever `net_objOrGhost` returns - the owner again when that is the owner.

## 4a. SB3 - mechanism confirmed

FINDINGS row SB3 (S3 of the specification): the `StaticFire` objects ShadowStep leaves keep
the caster as a raw pointer. `StaticFire` is not modelled; its constructor 0x2c5240 and run
function 0x2c595c were executed as they are (`difftest_skills_b.py -k sb3`; everything they
call that this test does not run is a stub returning 0, `isNearView` answers 1).

1. **The store.** In 40 of 40 constructions the owner argument is stored as a plain word at
   +0x4a8, and no `handle_link` is made for it (0 calls whose head is fire + 0x4a8).
   ShadowStep passes the caster there for the centre fire (life 360) and for every ring fire
   (life 240) - the matched `SpellShadowStep_ctor` shows the arguments.
2. **The use, owner alive.** On a damage frame (frame % 12 == 0, a creature in the fire's
   box) the run function reads the word, finds the creature flag at word + 0xc, calls slot 20
   of that object with the victim and passes the word to `damage_apply` as the attacker: 40
   of 40.
3. **The use, owner gone.** With the owner's memory rewritten as another creature the same
   happens with whatever is there - its slot 20 decides who burns and it is credited as the
   attacker (40 of 40). Rewritten as something that is not a creature, the fire takes the
   other branch: no is-enemy test at all, the fire itself is the attacker and every creature
   in its box is hit (40 of 40).

So nothing tests the pointer for up to 360 frames. What the pool really puts at a freed
player's address, and whether machines agree on it, is ST-row territory and not shown here.
The same pass confirms the other half of S3 for id 49's twin: `SpellShieldBash` (id 34)
keeps its turn target as a plain word (`docs/spec/skills-01-34-executed.md`, SA3).

## 4b. The prediction copy and the skills of the second pass

The pattern is SB1's: a cast or constructor the prediction copy (object flag 0x20000) can
reach that stores into shared state before it tests for the copy.

- **Flag bit 0** of the Skill objects, as the game's initialiser builds them: set for 41
  and 84 (Cyclone) and for 51 (AncestralCall); clear for every other id of this range.
- **The gate**: `Player_castSkill` returns for a copy when the bit is clear, at
  0x1a4320–0x1a433c, before its own can-use call (0x1a4358) and the cast (read, not
  executed). The cast-start code asks can-use earlier, for the copy too.
- **Can-use for the copy**, executed for 35-40, 51, 56-58, 65-67 (52 in the other test): no
  can-use stores a byte. 38, 39 and 40 can raise a HUD message; 40 also makes a box query;
  51 and 65 look for a spell of their class.
- **The one castable id, 51**: `SkillAncestralCall_cast` and `SpellAncestralCall_ctor` were
  run with the copy as caster. The copy test is at 0x2e0b80. Before it the constructor makes
  the spell's shared draw (prediction restores the seed) and four call-outs - `res_find`
  twice, a sound on the copy, `anim_startBlendInOut` on the copy's OWN animation state - and
  stores nothing outside the spell block, which `Player_castSkill` destroys at once. No store
  into the clip (Cyclone's mistake) and none into the caster. After the test, for a real
  caster only: the light, action state 6 (0x2e0c58), the statistics, the particle group.

The casts of the other ids were run for real casters; their stores outside the stack, the
blocks just allocated, list nodes and the shared seed, in order of first appearance:

| Id | Skill | Copy may cast | First store of cast or constructor outside its own objects | Copy test | Order |
|---|---|---|---|---|---|
| 35 | charge | no | caster action state +0x58c = 9 (0x2c88e8), then the same word of `net_objOrGhost(caster)` (0x2c88f0: the copy, on its own machine - a per-machine store by design). Before them, in the constructor: `light_link`, a sound, ten trails (call-outs) | none in the class; gate 0x1a4320 | gate first: not reachable |
| 36 | darkness | no | the caster's back list (`handle_link` of the cloud's caster handle, 0x1a17b4). Before it: `GameObject_ctor`, `light_link`, a sound | none; gate | gate first |
| 37 | shock | no | the caster's back list (`handle_link`, 0x1a17b4), after `GameObject_ctor`, `light_link`, a sound | none; gate | gate first |
| 38 | groundpound | no | caster action state +0x58c = 10 (0x2c722c); then **four event slots of the pound clip, in the shared clip header**: 0x2c727c–0x2c72a4 (times +0x14, +0x1c, +0x24, +0x2c; masks +0x18, +0x20, +0x28, +0x30) | none in the cast; gate | gate first |
| 39, 40 | convertenemy, convertundead | no | the back lists of the creatures chosen as targets (`handle_link`, 0x1a17b4); before it the sound and the arc query | none; gate | gate first |
| 51 | ancestralcall | **yes** | for the copy: **none**. For a real caster: action state +0x58c = 6 (0x2e0c58) | 0x2e0b80 | test first: every store outside the spell comes after it |
| 52 | root | no | (other test) the victims' spell lists | none; gate | gate first |
| 56 | coneoffrost | no | **none** in the cast or the constructor: every store is into the spell (call-outs: `light_link`, `res_find`, `sound_playAtPos`). The first store outside comes from the RUN, on the first frame with (frame & 7) == 0: the owner's back list, when `Projectile_ctor` links the `DummyDamager`'s owner handle (`handle_link`, 0x1a17b4) | none in the class; gate 0x1a4320 | gate first: not reachable |
| 57 | shockoffire | no | the caster's back list: `handle_link` of the spark's owner handle (0x1a17b4), inside `Projectile_ctor`. Before it only `GameObject_ctor` (call-out); after it `light_link`, `obj_runEveryFrame`, a sound | none; gate | gate first |
| 58 | froststorm | no | the caster's back list: `handle_link` of the storm's caster handle +0x6c (0x1a17b4), the last thing the constructor does but for `obj_runEveryFrame`. Before it `GameObject_ctor` (twice for a monster caster) and `light_link`; after the constructor a sound on the caster | none; gate | gate first |
| 65 | giantgrowth | no | the caster's back list: `handle_link` of the spell's owner handle +0xf8 (0x1a17b4). Nothing else in the cast: the stores that matter are the RUN's, every frame - the owner's scale +0xdc (0x3095a0, and 0x3095b0 / 0x3095d4 when it reaches the aim) and the speed factor of the owner's player record +0x4c20 (0x309668, 0x30966c); the test prints them | none; gate. The cast itself returns 0 for a caster without the player flag (0x308fc0) | gate first |
| 66 | planarwind | no | the back lists of the targets gathered: one `handle_link` (0x1a17b4) for each object the arc query hands back; none when it hands back nobody. Before it `light_link`, the cast sound and the query (call-outs) | none; gate | gate first |
| 67 | shadowstep | no | caster action state +0x58c = 0xe (0x31173c) and object flags \|= 5 (0x31174c), with no player test; later the knock-back words of the creatures that were targeting the caster (+0x2e8 at 0x311ab8, +0x2e0 at 0x311ae0) | none; gate | gate first |

The five rows of the third pass (56, 57, 58, 65, 66) come from the same collection: the
original's stores outside the stack, the blocks `pool_new` had just handed out, the list
nodes and the shared seed, in order. For all five the first - and, in the cast, only -
place is the first word of another object, written by `handle_link` when it puts a partner
node on that object's back list; that word is freed with the spell or object that holds the
handle. None of the five writes a clip header, an action state, a flag word or a player
record in its cast or constructor, and none has a copy test of its own: flag bit 0 is
clear for all five, so the copy is turned away at the gate. (Which objects the Planar
Wind's query returns is scripted here; the real query is said to pass over the copy.)

So within the second and third pass there is no second SB1: the only id the copy can cast, 51,
tests first.
Ground Pound is the one to remember: its cast rewrites four slots of a shared clip header on
every real cast (constants, the same on every machine, and nothing in the class moves them
afterwards), behind nothing but the gate - if flag bit 0 were ever set for id 38 it would be
an SB1 with four slots instead of one. Bash (49) and Shield Bash (34) write one slot the same
way in their constructors.

## 4c. Proposed ledger text (not applied: `FINDINGS.md` is not edited from here)

| Row | Proposed addition |
|---|---|
| SB6 | Mechanism confirmed by execution (third pass): with the owner handle emptied, `DummyDamager_onTouch` loads through the empty handle at 0x1ee7e8 on every touch of a creature (the interpreter stops there, on the model's side too: 11 calls of the run of record); a touch of a non-creature does not make the load and reaches `damage_apply` with attacker 0. The handle is emptied by the owner's deletion while a projectile still has up to 45 frames to live. What the console reads at address 0xc is not modelled |
| SB3 | Mechanism confirmed by execution: `StaticFire_ctor` stores its owner argument as a plain word at +0x4a8 with no handle (40 of 40); on a damage frame `StaticFire_run` asks slot 20 of whatever that word points at and passes it to `damage_apply` as the attacker, also after the owner's memory was rewritten as another creature (40 of 40); rewritten as a non-creature, the fire itself attacks every creature in its box (40 of 40). `SpellShadowStep_ctor` (matched) hands the caster to every fire, lives 360 and 240 frames |
| SB1 (note) | Ids 35-40, 51 and 67 checked for the same pattern. Only 51 can be cast by the copy; its constructor stores nothing outside the spell before its copy test at 0x2e0b80 (executed with the copy as caster). Id 38's cast writes four event slots of a shared clip header (0x2c727c–0x2c72a4) and has no copy test of its own: not reachable while its flag bit 0 stays clear |
| SB1 (note, third pass) | Ids 56, 57, 58, 65 and 66 executed and checked: flag bit 0 clear for all five; the only store any of their casts or constructors makes outside its own new objects is the back-list word of the caster (57, 58, 65) or of the gathered targets (66) through `handle_link` 0x1a17b4, and 56 makes none. No shared clip header, action state or record is written before - or without - a copy test. With these the whole range 35-68 has been executed for the pattern |

No new row and no patch is proposed.

## 5. Corrections to `docs/spec/skills-35-68.md`

Every other rule of the sections listed as matched held as written, constants included.
What execution changes:

| Where | It says | Executed |
|---|---|---|
| Section 68, timing table | run calls 61, 121, 181, 241 for 1–4 s and 721 for 12 s; respawn call 47, 107, 167, 227 | 60 N for every N (60, 120, 180, 240 … 720, 780); respawn on call 60 N − 14 (46, 106, 166, 226). Countdown at 0x312ee0–0x312f00, respawn test at 0x312ddc. The quoted numbers are the round-to-nearest ones |
| Section 54, "Lifetime in run calls" | 600th call for 10 s, 660th for 11 s | 601st, 661st: 60 N + 1 for every N from 10 to 20 (0x2e8428). Section 1.8 already has this right |
| Section 53, duration | both variants given | the truncating one: 60 N (720 and 780 for 12 and 13 s, not 721 and 781) (0x2e7acc) |
| Sections 43, 44, 45, 47, lifetime and range | "600 moving frames", range 600 × speed / 60 | the age test follows the move (FireArrow: move 0x2d66f8, test 0x2d6724; the others alike), so an arrow that meets nothing is moved 601 times before run 601 ends it: range 601 steps |
| Section 41, wind-down | "clip2.event1.mask (clip2+0x28) = 4; clip2.event1.time (clip2+0x24)" | the offsets are right, the name is not: +0x24 / +0x28 is event slot 2 (slot k is at +0x14 + 8k), stores 0x2d1d04 and 0x2d1d0c |
| Sections 42, 49, 54, 62 (particles on model sample points) | the sample point is "draw mod n" | n is the model's sample-point count and is not tested: for a model without sample points the code divides by zero (0x3086b8 in the StrongStance trigger; the same pattern in `SpellHarmTouch_applyToHit`, `SpellHolyShield_absorb`, `SpellBash_windupFx`). The R5900 does not trap; the index is then undefined. Whether any player model has no sample points is disc data, not examined |
| Section 68, run | not stated | the run stores the tint through the target pointer +0x18 with no null test (0x312c88 on). After the respawn the pointer is re-read from the slot's record (0x312e70); a record without an object leaves it null. This is the "allocation-failure path of `player_respawn`" the section lists as not determined, seen from the spell's side |
| Part 2, S.1 | can-use text keys not given | the five bow skills pass different text keys to `text_lookup` (0x54f278, 0x54f360, 0x54f448, 0x54f550, 0x54f648 for ids 43–47); nothing else differs between the five bodies - confirmed |
| Section 38, first run, step 6 | "one draw of 0x404468 for the angle of a floor decal" | the angle handed to `decal_add` is the generator's new STATE shifted right 16 as a signed word (0x2c7d98–0x2c7de8), i.e. the draw sign-extended from 16 bits - not the unsigned draw the other sites use. Presentation, per-machine generator |
| Section 38, the `LightEffect` of the first run | colours only | executed arguments: start and end colour (193, 117, 57, −32), then 9.0, 0.0, 0.8, 0.3 on the stack (0x2c7a50–0x2c7abc) |
| Section 67, constructor step 9 | "p.z = terrain_heightAtPoint(g_world, &p)" | the point handed to the query carries the PREVIOUS ring point's height as its z (0.0 for the first): one frame variable serves as input and result (0x311900–0x311960). Whether the query reads the z is `docs/spec/world-queries.md`'s business |
| Section 51, layout, "+0x00 u8 level" | unsigned | read as a signed byte everywhere it is used (ring count level + 14, `lb` at 0x2e1100; statistic reads) |
| Section 37, hit test | - | confirmed as written, including the two points a rebuild is likeliest to get wrong: with a live caster the target is linked into the candidate list twice, and the chained victims are damaged newest first |
| Section 56, random draws, "15 × 4 draws (first particle kind: angle, speed, vertical speed, start offset along the path)" | the fourth draw places the particle | the fourth draw is made, its product (velocity × d × 1/60 added to the run position) is built in the frame and never handed on: `particle_spawn` gets the run position itself for all three kinds (0x2e9ec0–0x2e9f80; the position argument is set at 0x2e9f04). The draw count stands |
| Section 56, the three particle kinds | amplitudes and speeds not given | angle amplitude A for the first kind, (int)(A × 0.999977) for the second (0x2e9f8c), (int)(A × 1.7489879) for the third (0x2ea0a4); speeds d × 74 × scale, (d × 0.2 + 0.9) × 60 × scale and a flat 42 (not scaled); rise (d − 0.5) × 6, × 4 and × 17, each × scale |
| Section 56, `DummyDamager_run`, "if bits & 8: (fire: not used by this skill)" | not given | executed for the monsters' sake: ONE OWN DRAW d, f = (d × 2^-16 × 6 + 2) × 60, `pool_new(0x4ac)` and a `StaticFire` at the position with life (int) f, first number f, second 0.5, no owner (0x1ee460–0x1ee4c0; one shared draw inside the constructor). With both bits 0x10 and 8 the touch handler builds the cold entry only (0x1ee86c before 0x1ee8d0) |
| Section 56, `DummyDamager_onTouch`, the owner read "without a null test" | Inferred hazard | executed: with the owner handle emptied, every touch of a creature stops at the load 0x1ee7e8 (address 0xc) - on both sides, in every case staged (the calls the test counts as "stopped on both"). A touch of a non-creature does not read it and calls `damage_apply` with attacker 0. What the console does with that load is not modelled |
| Section 57, direct hit, the `LightEffect` | "colour arguments 255, 200, 100" | all twelve numbers: 255, 200, 100, −32, four zeros, and on the stack 180, 120, 1, 1 (0x29013c–0x2901b8) |
| Section 57, flight | "for at most 600 frames" | a spark that meets nothing moves 599 times and bursts in its 600th run (end = frame of the cast + 600, tested before the move, 0x28fa88) |
| Section 58, snow and shards | velocities not given | snow A: an own ball × 7 with z × 11.036939, snow B: × 6.8 with z × 2.073994, shard: × 0.20500399 sideways and z × 3.999987; z is then made −\|z\| through the double-precision library (0x1fecd8–0x1fed28 and twice more), which gives +0 for a zero of either sign. The z part of the offset ball is multiplied out and overwritten by the height draw (0x1fec10–0x1fec18) |
| Section 58, table of shrinking frames | 24 → 14, 36 → 22, 48 → 28, 60 → 32, 72 → 35, 132 → 47 | confirmed for the five radii the run of record met (all but 60); other runs of the section also gave 84 → 38 and 120 → 45, which the table does not have |
| Section 65, particles (0x309678) | "emitted from model sample points" | each serviced slot asks `model_getSamplePoint` for three things - the point, a number and a 3×3 matrix - with the owner's scale as the float argument; the matrix is turned about its third axis by the slot's angle (`mat3_rotateAxis`, 0x30978c) and the particle goes to (point − owner position) + first row × (number × 0.001 × 0.662995), velocity 0, inside the particle group whose matrix is the owner's position; the angle then advances by 0x5da. The slot restarts when (d & 3) + 41 < age after the increment (0x309864). The 4-slot case is "aim ≤ scale" (0x309710), so it also holds while something else has pushed the scale above the aim |
| Section 65, timeline table | 469 / 539 / 845 runs at ranks 1 / 2 / 10 | confirmed by execution from the cast to the call that ends the spell (owner scale 1.0 at the cast) |
| Sections 65 and 66, sample points | "draw % count" | as in sections 42, 49, 54 and 62 the count is not tested: `SpellGiantGrowth_ctor` 0x3092ec, `_emitParticles` 0x30987c and the hit particles of `SpellPlanarWind_run` 0x30a404 divide by it. Not staged here (this test stops on a division by zero) |
| Section 66, hit particles | "one private draw → a model sample point → one particle" | the 72 particles all get the frame's step vector as their velocity, as it is before the stream loop adds its nudges (copied at 0x30a3dc–0x30a3f0) |
| Section 66, stream particles, draws 6 and 7 | "a rotation angle for the scatter matrix; a distance fraction" | a COPY of the matrix at +0x38 is turned about its second axis by the drawn angle (`mat3_rotateAxis(copy, 1, angle)`, 0x30a5fc) and the particle is put at front + first row of the copy × (d × 2^-16 × half width) (0x30a630–0x30a668) |
| Section 66, damage bounds | player rounded, others truncated | confirmed, and worth a number: a statistic of 55 gives 44..66 for a player owner and 44..65 for any other (0x30a25c–0x30a274) |

Every other rule of sections 56, 57, 58, 65 and 66 held as written, constants included: the
Cone of Frost's projectile on frames with (frame & 7) == 0 carrying statistic 0 × 0.13333333
with bits 0x12 and flags 0x80c040, the victim - not the owner - deciding whether a
`DummyDamager` hurts it, and the amount being delivered once (later touches carry an entry of
0); the spark's direct hit on the first enemy only, its burst one run later with
`world_damageInRadius(40, radius; splash, 0x40860, splash, 0)` and the spark itself as
attacker when the owner is gone; the Frost Storm's loop counts in the stated order of
multiplications, its shared draw per shard (none when the pool refuses), the tick asking the
CASTER's slot 20 and striking everything in the box without one, half as base damage and
half (truncated) as cold; Giant Growth refusing a non-player before it allocates, its exact
float comparison of scale and aim and the speed factor max(1, scale × 0.75) written on every
run; the Planar Wind's list being the query reversed, its strike test on the centre only, the
burn draw made at chance 0 too, the PvP draw keeping the knock-back bit 21 times in 100, the
speed step and the 54 runs.

Every other rule of sections 35, 36, 37, 38, 39, 40, 51 and 67 held as written, constants
included: Charge's unsigned frame difference and its contact rules, Darkness asking the
caster's slot 20 twice per victim and rolling `r % 100 + 1 < T`, Shock's 211-unit chain,
Ground Pound's stun roll `100 − s2 < r % 100 + 1` with the draw made even at chance 0, the
Convert roll with the halved chance for wide targets and the signed team byte, AncestralCall's
inclusive query against its strict tint test, ShadowStep's 0.04088309 per call.

Confirmed by execution and worth saying because other sections lean on them: the four
shared draws of slot 8 with the first of each pair only choosing the rounding direction
(1.2); HarmTouch's 204 own draws before the damage spread (section 42); the FireArrow hit
handler's missing "already hit" guard - every object overlapped in one frame is damaged,
while the end function runs once (section 43); ExplodeArrow's own draw per object of its
box query, creature or not (SB8); MultiFire's two draws of the presentation generator for a
non-player caster (SB7); the Bash constructor storing the list head, not the entry it
found, as its target (section 49); Resurrect's write of 0.5 to the caster's record +0x4c20
(0x312a28) and of 0x402797 = 1 on every machine every tick; Healing reading
`g_alivePlayers` 0x4f8440 with the count 0x4f8420 re-read each iteration.

### `docs/skills.md`

No new correction. Executed and consistent with its current text: the base slot 5 returns
1.0 (0x3c82a8), LifeTap's and StrongStance's slot 5 call slot 14 and return 0.0; the base
cast (and the casts of 59 and 62) copies the position into its frame and returns 0; the
MultiFire cast builds `MissileWeapon` objects through 0x150ee4; slot 14 returns its level
argument whatever the second argument is.

## 6. Per-machine state

No read of per-machine state was found in the executed functions that the ledger does not
already have. The ones met, by address:

| Read | Where | Ledger |
|---|---|---|
| `g_alivePlayers` / `g_alivePlayerCount` | `SpellHealing_run` 0x2e9158, 0x2e9180; `SkillCriticalHit_critBonusFor` 0x2e7724, 0x2e7744; `SpellCriticalHit_run` 0x2e7e58 (tint only); `SkillResurrect_isSlotBeingRaised` 0x312718, 0x312748 | G18, G19, SA5; `docs/issues/prediction-copy.md` |
| `net_objOrGhost` | `SpellCyclone_run` 0x2d1b04 (G22); `SpellHealing_run`, `SpellCriticalHit_run`, `SpellBash_windupFx`: where particles go and whether a ring particle is kept - the number of own draws does not depend on it | G22, G23 |
| `net_isLocalSlot` → 0x402797 | `SpellCyclone_run` 0x2d218c (120), `SpellBash_run` (60) | `docs/skills.md` (c) |
| presentation generator 0x404460 | `SkillMultiFire_cast` for a non-player caster (damage figure) | SB7 |
| generators 0x404460 and 0x404468 | `SkillStrongStance_trigger` (particles only) | presentation; no row needed |
| the shared clip header | `SpellCyclone_ctor` / `_run` | SB1 (section 4) |

`SpellCyclone_run` reads the two stick values straight from `g_pads[slot]` (+0x14, +0x18,
0x2d1e3c). Inside a lockstep tick that array holds the frame's agreed input
(`docs/netcode.md`, `net_frameLoop` step 2), so this is not a per-machine read; it is noted
because it bypasses the pad pointer `Player_run` uses.

No ledger row and no patch is proposed by this pass.

Third pass: nothing per-machine is read by the functions of 56, 57, 58, 65 and 66. They
read the frame counter (the Cone's projectile and light, the storm's shards and tick, the
spark's time limit), `g_world` for terrain, and `g_pvpModeA` 0x4f711c in
`SpellPlanarWind_run` (0x30a27c; a setting of the session, as in Healing). None calls
`net_objOrGhost` or `net_isLocalSlot`, none touches 0x402797, the cosmetic generator
0x404460 or 0x404468 in its own code (`fx_ringBurst`, which the spark's burst calls, uses the
cosmetic generator inside - a call-out here, as the specification says). Their own
generators - the spell's for 56, 65 and 66, the object's for the `DummyDamager`, `Sparks`,
the storm and its shards - feed particles only, with one exception the specification
already has: the Cone of Frost's aim draw comes from the spell's generator. Writes to
shared state outside the caster's own objects: Giant Growth's two per-frame stores (the
owner's scale and the record's speed factor), both inside lockstep state.

Second pass, by address: `net_objOrGhost` in `SkillCharge_cast` 0x2c88e4 and
`SpellCharge_run` 0x2c8fe0 (the extra state store lands on this machine's copy);
`SpellAncestralCall_run` asks it once for the ring's matrix (0x2e1144) and again for every ring particle (0x2e1214) - placement only, the
number of own draws is fixed; `g_alivePlayers` in `SpellAncestralCall_run` (tint only) -
the query that carries the aura's effect does not read the list, its two callers do (G18,
G19); 0x402797 written by `SpellCharge_run` (= 1, every frame) and `SpellShadowStep_run`
(= 1); the generator 0x404468 in `GroundPoundEffect_run` (particles, decal angle, ripples -
the stun rolls use the object's own generator); `g_networkMode` in `SpellShadowStep_run`
(offline only: `Player_clampToScreen`, which reads the camera). Nothing that is not already
in the specification's per-machine notes.

## 7. Files

- `tools/ref_skills_b.py` - the model. `FUNCTIONS` lists every original function it
  mirrors with its address range; `SKILLS` groups them by id.
- `tools/difftest_skills_b.py` - the comparison; prints, per skill, the functions executed,
  the basic blocks covered and the calls with a mismatch, and the frame counts of section 3.
- `tools/test_ref_skills_b.py` - twenty-five unit tests of the model's own logic (no game files).
