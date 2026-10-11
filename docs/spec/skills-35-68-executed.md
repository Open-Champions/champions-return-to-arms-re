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
python3 tools/difftest_skills_b.py            # everything, about 5 to 12 minutes
python3 tools/difftest_skills_b.py --quick    # a tenth of the scenarios, about 3 minutes
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
| 56 | coneoffrost | not run | statistics, mana cost and can-use (the base) only |
| 57 | shockoffire | not run | statistics, mana cost and can-use (the base) only |
| 58 | froststorm | not run | statistics, mana cost and can-use (the base) only |
| 59 | lifetap | **matched** | cast (returns nothing), `SkillLifeTap_getStat0Fraction`, `_getStat1`. The pending-pool logic lives in the damage and player code and is outside this range |
| 60 | Blunt | **matched** | no function of its own: every slot is the base's |
| 61 | Slashing | **matched** | as 60 |
| 62 | strongstance | **matched** | cast, `SkillStrongStance_getStat0`, `SkillStrongStance_trigger` (the phantom it creates is a call-out) |
| 63 | naturalresistance | **matched** | `SkillNaturalResistance_getStat0Fraction` |
| 64 | stunningstrike | **matched** | `SkillStunningStrike_getStat0ForTarget`, `_spawnEffect` |
| 65 | giantgrowth | matched in part | statistics, mana cost and can-use ("carries a SpellGiantGrowth"). Cast and effect not run |
| 66 | planarwind | not run | statistics, mana cost and can-use (the base) only |
| 67 | shadowstep | **matched** (second pass) | cast at every rank (no fire, the centre fire, the ring), the enemies that lose their target and are pulled, `SpellShadowStep_run` for its 25 calls offline and in a net game. `StaticFire_ctor` is a call-out; the fire itself is not modelled (section 4a executes it as it is) |
| 68 | resurrect | **matched** | can-use, target search, `_isSlotBeingRaised`, cast, constructor, run in both modes, `SpellResurrect_onOwnerDeath` |

Twenty-nine of the 34 ids are matched (46 only in part, as before; 52 in the other test),
and 65 as far as its can-use. The first pass ended at twenty. The five left - 56 coneoffrost, 57 shockoffire, 58 froststorm, 66
planarwind and the cast of 65 giantgrowth - were not reached in the second pass either;
nothing was found that prevents them. For them only the statistic getters, the mana-cost
slot and can-use were executed.

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

Coverage of the original as executed (basic blocks entered / basic blocks of the function
bodies; full run, seed 3568):

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
| 65 giantgrowth (can-use) and the mana-cost slot of the five ids not run | 7 | 7 of 7 | all |
| **all** | 169 | **1345 of 1365** | **17039 of 17131** |

265,003 calls were compared in that run (274 s; the first pass alone: 235,931); none
mismatched. 144 result lines, all PASS.

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
| 56, 57, 58, 66 | coneoffrost, shockoffire, froststorm, planarwind | no | not executed (casts not modelled) | gate | gate first |
| 65 | giantgrowth | no | not executed | gate | gate first |
| 67 | shadowstep | no | caster action state +0x58c = 0xe (0x31173c) and object flags \|= 5 (0x31174c), with no player test; later the knock-back words of the creatures that were targeting the caster (+0x2e8 at 0x311ab8, +0x2e0 at 0x311ae0) | none; gate | gate first |

So within this pass there is no second SB1: the only id the copy can cast, 51, tests first.
Ground Pound is the one to remember: its cast rewrites four slots of a shared clip header on
every real cast (constants, the same on every machine, and nothing in the class moves them
afterwards), behind nothing but the gate - if flag bit 0 were ever set for id 38 it would be
an SB1 with four slots instead of one. Bash (49) and Shield Bash (34) write one slot the same
way in their constructors.

## 4c. Proposed ledger text (not applied: `FINDINGS.md` is not edited from here)

| Row | Proposed addition |
|---|---|
| SB3 | Mechanism confirmed by execution: `StaticFire_ctor` stores its owner argument as a plain word at +0x4a8 with no handle (40 of 40); on a damage frame `StaticFire_run` asks slot 20 of whatever that word points at and passes it to `damage_apply` as the attacker, also after the owner's memory was rewritten as another creature (40 of 40); rewritten as a non-creature, the fire itself attacks every creature in its box (40 of 40). `SpellShadowStep_ctor` (matched) hands the caster to every fire, lives 360 and 240 frames |
| SB1 (note) | Ids 35-40, 51 and 67 checked for the same pattern. Only 51 can be cast by the copy; its constructor stores nothing outside the spell before its copy test at 0x2e0b80 (executed with the copy as caster). Id 38's cast writes four event slots of a shared clip header (0x2c727c–0x2c72a4) and has no copy test of its own: not reachable while its flag bit 0 stays clear |

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
- `tools/test_ref_skills_b.py` - seventeen unit tests of the model's own logic (no game files).
