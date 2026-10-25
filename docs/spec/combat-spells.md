# Combat runtime, round 2: spells in combat

US `SLUS_209.73` v2.00. Round 2 of `docs/combat-runtime.md` (round 1, commit 9289d56). It
covers how a spell gets from the cast to damage on the actors of the one shared world: when
the cast happens, which objects and spell records it makes, when they run, how they find
their victims, how the damage and the burning reach those victims and who gets credit for a
kill, and when the effects go away. It is the prose of `tools/ref_combat_spells.py`.

The skills themselves are already modelled and executed one function at a time by
`tools/ref_skills_a.py`, `ref_skills_b.py` and `ref_skills_c.py`
(`docs/spec/skills-01-34-executed.md`, `skills-35-68-executed.md`,
`skills-69-101-executed.md`). In those tests the services a spell uses to find and hurt its
victims were scripted stubs. This document adds those services, executed against the
original, and composes three representative skills from the three batches with round 1's
runtime:

- **Holy Strike** (id 16, `ref_skills_a`): a homing projectile with a candidate list made at
  the cast. It covers direct damage.
- **Shock of Fire** (id 57, `ref_skills_b`): a projectile with a touch hit and an area
  burst. It covers area damage.
- **Wave of Flame** (id 95, `ref_skills_c`): a spell attached to its caster, with a growing
  ring that sets victims on fire. It covers damage over time and kill credit.

Round 1's APIs and test vectors are unchanged. This module only subclasses them.

Evidence labels are as in round 1:

- **Executed**: the original instructions were run one function at a time in
  `tools/ee_emu.py` (an instruction interpreter, not a console) on constructed state, and
  agreed with the model. The test is `tools/difftest_combat_spells.py` unless another is
  named.
- **Observed**: read at the address given.
- **Inferred**.
- **Unknown**.
- **Authored**: a choice of this contract (a fixture, driver or refusal).

Nothing here was run on a console, in PCSX2 or on the live rig.

## 1. The contract in brief

1. **The cast happens inside the caster's own run.** For a player it happens in
   `Player_run` state 5, at the cast point: cast-track weight 1.0 offline and 0.5 in a net
   game (0x1ab7b8, *Observed*). The track starts at a rate of 1/6 per tick, so that is about
   6 ticks offline and 3 in a net game (*Inferred*;
   `research-anim:docs/spec/player-animation-dispatch.md` section 4). At that point
   `Player_castSkill` 0x1a42b8 calls the Skill's slot 2 and attaches a returned spell with
   `creature_addSpell` (*Executed* in `tools/difftest_player.py`).
2. **Every effect object and every spell record makes ONE shared draw.** For an object it
   is `GameObject_ctor`; for a spell record it is the Spell base, which seeds the spell's
   own generator +0x10. Every `LightEffect` the effect makes draws once too (*Executed* in
   the skills difftests; `test_the_constructors_draw_the_shared_seed`).
3. **When the effect first runs depends on what it is.**
   - An effect *object* (a projectile, a light) joins the front of the every-frame list. It
     is not run by the walk that made it, so it first runs in the next tick, before every
     older actor.
   - An attached *spell* runs in its owner's spell walk. For a player that walk is in the
     tail of its own run (`Player_updateCast` 0x1a3f70 calls slot 17), so the spell first
     runs in the tick of the cast. For a creature the walk is the first step of
     `Creature_run` 0x112948 (the test at 0x112984 skips players), so the spell first runs
     in the creature's next run.
   - Composition tests: `test_a_projectile_first_runs_in_the_next_tick_and_runs_first`,
     `test_an_attached_spell_runs_in_the_casters_tail_in_the_same_tick`.
4. **Victims are found by three services, in grid (box) order** (*Executed*, section 3):
   - `world_collectObjectsInArc` 0x1614f0 gives creatures only. The first entry of its list
     is the nearest; the rest are in reverse order of acceptance.
   - `world_collectInSphere` 0x14ab80 gives any class, in reverse box order.
   - `world_damageInRadius` 0x161270 damages at once, per object, in box order.
5. **Damage is `damage_apply` with the owner as the attacker**, applied at once inside the
   effect's run. The victim reacts in its own run (round 1, section 6). An object that is
   not a creature still costs one shared draw (the base roll) and reaches an empty slot 2.
6. **Burning is credited to whoever set it.** A fire entry in the descriptor sets the burn
   seconds +0x340 and relinks the status-source handle +0x360 to the attacker. The victim's
   own `Creature_run` then damages it on every frame with `frame & 0x1f == 0`, with flags
   0x1180c040. Flag 0x10000000 makes `Creature_takeDamage` name the status source as the
   last attacker, so a burning kill credits the caster (*Executed* pieces: ref_creature,
   ref_combat; composition test
   `test_cast_time_candidates_hit_once_burn_and_credit_the_caster`).
7. **Effects destroy themselves at once** with their own slot 1 and argument 3. There is no
   delete list, so in the same tick later actors no longer see them and the block is back
   in its size class. The destructors are *Executed* (section 6).
8. **A list made by the arc query keeps dangling entries.** Its nodes have no partner
   (+8 = 0), so destroying a listed object does not unlink them. Holy Strike keeps such a
   list at +0x58 and homes on its first node, so it steers toward whatever object the pool
   puts in a destroyed target's block next (*Inferred* from executed pieces;
   `test_the_candidate_list_outlives_its_target`).

## 2. Where each piece comes from

| Piece | Model | Evidence |
|---|---|---|
| `Player_castSkill` 0x1a42b8, `Player_updateCast` 0x1a3f70, state 5 | `ref_player.Tick` | Executed, `tools/difftest_player.py` |
| Skill slots, constructors, runs and hit handlers of ids 16, 57, 95 | `ref_skills_a/b/c` | Executed in their difftests (all three matched) |
| `damage_apply` 0x1e8230 with descriptors | `ref_combat` | Executed, `tools/difftest_combat.py` |
| take-damage, pending damage, burn tick, spell walk (slot 17) | `ref_creature` | Executed, `tools/difftest_creature.py` |
| pool, `GameObject_ctor`, lists, iterator, handle pool | `ref_objects`, `ref_core` | Executed |
| the three victim services, the five effect destructors | `ref_combat_spells.QueryModel` | **Executed here**, section 9 |
| `LightEffect_ctor` 0x201bd8: the simulation part | `SpellRuntime.svc_LightEffect_ctor` | Observed (section 6.2) |
| `LightEffect_run` 0x1ee050: the end test | `SpellRuntime.light_effect_run` | Observed |
| Skill objects, statistics, actors, the cast point | `SpellRuntime.give_skill`, `queue_cast`, `cast` | Authored |

The Skill tables (slots 0-15) and the effect tables (slots 0-16) the runtime installs are
the executable's words, read for this document (*Observed*):

| Table | Class |
|---|---|
| 0x51a108 | SkillHolyStrike |
| 0x51a190 | SkillShockOfFire |
| 0x51c2a8 | SkillWaveOfFlame |
| 0x51a078 | HolyStrike |
| 0x50e998 | Sparks |
| 0x50e198 | LightEffect |
| 0x51c330 | SpellWaveOfFlame |

In the three effect tables, slots 2, 3, 7-14 and 16 are GameObject defaults, and so are
the light's slots 5 and 6. Each is a bare return (some return 0), or (slots 10 and 11) a
copy of a vector argument to the stack and a return.

## 3. Finding victims (Executed)

### 3.1 `world_collectObjectsInArc` 0x1614f0 (pos, facing, out list, filter; radius, arc°, width)

- **The query.** One box query of `pos ± radius` on all three axes, capacity 0x200. There
  is no other range test, so the corners reach `radius × √2` in the plane.
- **The test directions.**
  - `f = (cos16, sin16)(facing)`.
  - With `arc != -1.0`: a half angle `n = round-half-away(arc × 0.5 × 182.04443)`, and two
    edge normals at `s16(facing + n − 0x4000)` and `s16(facing − n + 0x4000)`. A negative
    arc gets −0.5 before the truncation, so the rounding is half away from zero for both
    signs (0x161610-0x161650).
  - With `width != 0`: a side normal at `facing + 0x4000`.
- **The filter, per object in box order:**
  - creature flag 0x20 required;
  - flags 0xd refused;
  - with a filter object, ITS slot 20 must accept;
  - both edge products must be ≥ 0;
  - `|side product| ≤ width`;
  - the forward product must be > 0 (strict).
  - Every product is 2-D: `vec2_dotDelta` 0x166820.
  - `sin16(0)` is 2⁻²² and not 0, so at facing 0 an object exactly abeam on the left still
    passes the forward test.
- **Insertion.** `handle_insertNode` 0x1a19d0 puts the new object behind the first node,
  walking from the head, whose object is not farther in the plane (`<=`). With no such node
  it goes at the head. The head is therefore the nearest object (the earlier of equals), and
  **every later object lands directly behind the head**. The rest of the list is the
  reverse of the acceptance order.
  - Example: box order at distances 50, 20, 80, 30, 90 gives the list 20, 90, 30, 80, 50
    (`test_first_entry_is_the_nearest_and_the_rest_reverse_acceptance`).
  - `docs/spec/skills-69-101.md` says the same from reading. This is the executed form.
- **The nodes have no partner.** The object does not hold them. The caller clears the list
  (`handle_clear`), or keeps it (Holy Strike).

**Consequence for the "first enemy" searches.** `Player_castSkill`'s aim (340, 20°, no
filter) and Disease Bolt's homing (280, 60°, no filter) take the first entry that the
caster's slot 20 accepts. When the nearest creature in the wedge is not an enemy (a charmed
or friendly creature), the target is the most recently accepted enemy of the rest: the last
in box order, not the nearest enemy (*Inferred* from the executed insertion and the executed
callers). The order is deterministic, so this is not a sync risk.

### 3.2 `world_collectInSphere` 0x14ab80 (centre, heading (not read), out list; radius)

- One box query of `centre ± radius`, capacity 0x200.
- Flags 0xd are refused, and there is **no class test**, so projectiles, props and effects
  are listed too.
- An object is kept when its 3-D distance (`sqrt.s`) is below `radius + its radius`
  (strict).
- `handle_addNode` 0x1a1980 links each kept object at the front, so the list is in reverse
  box order.
- Also executed by `tools/difftest_objects.py` (399 sphere queries); this is the call-out
  form.

### 3.3 `world_damageInRadius` 0x161270 (attacker, centre, most, flags, least, skip; inner, outer)

- **The query.** One box query of `centre ± outer`, capacity 0x80.
- **The slope.** `k = most / (outer − inner)` when that span is above 1.0, else 100.0.
  Nothing inside `inner` is treated differently.
- **Who is hit, per object in box order:**
  - never the attacker;
  - for a **player** attacker (flag 0x40), its slot 20 must accept;
  - **any other attacker, or none, damages everything**: other monsters, corpses, effect
    objects, its own projectile;
  - objects with any of the skip flags are left out. Every caller read so far passes 0.
- **The distance.** `d = (|dx| + |dy|) − min.s(|dx|, |dy|) × 0.33299 − radius`, in the
  plane only. Nothing at `outer <= d`.
- **The amount.** `(outer − d) × k`, first raised to `least`, then capped at `most`
  (`min.s`, so `most` wins when `least > most`), truncated.
- **The hit.** `damage_apply(object, attacker, 100000, 0, 0, flags, no descriptor, 0;
  amount, amount)`, applied at once.

## 4. The three spells in the shared world

### 4.1 Holy Strike (16)

- **The cast** (`SkillHolyStrike_cast` 0x2ecfcc): the caster's flash quads, `pool_new(0x80)`
  and `HolyStrike_ctor`. The constructor does `Projectile_ctor` (one shared draw), owner
  handles +0x4c and +0x54, speed 450, homing from frame + 15, expiry at frame + 180, a
  trail, and the candidate list +0x58 = `world_collectObjectsInArc(pos, facing, +0x58,
  owner if a creature; 360, 75°, 0)`. Then it goes on the every-frame list.
- **The run**: particles from its own generator, then homing on the **first node's object**
  (not tested for null). After that, `obj_moveAndCollide` with its touch order (the hit
  object's slot 6, then its own), and the end. At the end it makes a `LightEffect` (one
  shared draw, life 1.0 s = 60 frames) and calls its own slot 1 with 3.
- **The hit** (0x2ecae8) lands once, on what the owner's slot 20 calls an enemy:
  `damage_apply(other, owner, 100000, 0, 0, 0x80000, empty descriptor, 0; d, max)`. Flag
  0x80000 is a knock-back class: the creature reacts in its own `Creature_processDamage`.
- **In the composition** (`HolyStrike` tests):
  - one hit, attributed to the owner;
  - the object is gone from the world inside its own run;
  - the light lasts 60 frames;
  - after the nearest target is deleted, destroyed and its block reused by a new Skelight,
    the bolt turns toward the newcomer.

### 4.2 Shock of Fire (57)

- **The cast**: `pool_new(0xb8)` and `Sparks_ctor`, a projectile.
- **The touch** (0x2900c8) acts only while the end frame is set and the owner's slot 20
  accepts. It makes a `LightEffect` (one shared draw), then calls `damage_apply(other,
  owner, 10000000, low, high, 0xc060, descriptor (0x1f, 100, low, high), 0; 0, 0)`. Entry
  0x1f with 100 % is a certain chance of fire. Then it zeroes the end frame, so only the
  first enemy of a collision step is struck.
- **The next run**: 50 particles, then (with splash) `world_damageInRadius(owner or the
  spark itself, pos, splash, 0x40860, splash, 0; 40, radius)`, then its own slot 1 with 3.
- **In the composition** (`ShockOfFire` tests):
  - A player's burst hits only its enemies, both of them, in box order.
  - A **monster's** burst hits the other monster, the player, the touch's `LightEffect` and
    the spark itself. The last two are non-creatures and cost one shared draw each, through
    `damage_apply`'s base roll.

### 4.3 Wave of Flame (95)

- **The cast**: `pool_new(0x2c)`; `SpellWaveOfFlame_ctor` 0x316d10 does the Spell base (one
  shared draw), a centre fixed at the caster's visual position, a `LightEffect` (one shared
  draw), and the candidate list +0x18. That list is `world_collectInSphere(centre, facing;
  reach)` re-linked with `handle_link`. These are partner nodes, so a destroyed candidate
  leaves the list. The spell is attached to the caster.
- **The run** (0x317000) is called by the owner's spell walk. A ring of radius
  `clock × 72 + 20.098` hits each cast-time candidate it reaches, once:
  `damage_apply(object, owner, 100000, 0, 0, 0x160, descriptor (0x15, 10, 10, 0); stat-1
  range)`. Entry 0x15 adds fire damage and sets the burn status with the owner as the
  source. The spell destroys itself when the ring passes `reach`.
- **In the composition** (`WaveOfFlame` tests):
  - only the cast-time candidate is hit; a creature that steps inside later is not;
  - the burn ticks follow on frames ≡ 0 (mod 32), each with flags 0x1180c040 and the victim
    as its own attacker;
  - the status source and the last attacker are the caster;
  - a creature that dies of the wave gives the kill experience;
  - the spell leaves the caster's list at its end.

## 5. Damage over time and statuses

- **Burn.** `Creature_run` 0x113278 runs it while +0x340 > 0, decreasing it by 1/60 a
  frame. On the copy (0x20000) it never damages. On frames with `frame & 0x1f == 0` it calls
  `damage_apply(c, c, 100000, 0, 0, 0x1180c040, element (0x15, lo, hi), 0; 0, 0)`.
  - A monster gets `lo = hi = 1`.
  - A player gets a level-scaled range: the Skill at `g_skillTable[13]` slot 11 and **one
    shared draw**.
  - Flag 0x10000000 keeps the burn tick from setting the status again (`damage_apply`).
  - It makes `Creature_takeDamage` link +0x2e4 to the status source +0x360 (0x116638).
    That branch comes after the one for an attacker with object flag 0x80 (its owner is
    linked instead). The burning creature is its own attacker and has no flag 0x80, so the
    status-source branch applies.
  - *Executed* in ref_creature and ref_combat.
- **Status source.** The status setter 0x118950 relinks +0x360 with `handle_clear` and
  `handle_link`. The source is the attacker when it is a creature
  (`damage_apply`'s `source`). A destroyed source nulls the handle, and a later burning
  kill then has no killer to credit (*Inferred*).
- **Spells on the victim** that `damage_apply` asks about (BloodLust, Spirit Shield, Frost
  Armor, Disease Effect, the Undead Shields, Retribution, Critical Hit, Ancestral Call,
  Giant Growth) are outside this composition. A victim that carries one is refused, and so
  is a hit with a disease entry (0x26), which would attach a `SpellDiseaseEffect` to the
  victim.

## 6. Removal

### 6.1 Destructors (Executed)

| Destructor | Steps, in order |
|---|---|
| `HolyStrike_dtor` 0x3cf534 | table 0x51a078; clear +0x58, +0x54; table 0x5120b8; clear +0x4c; `GameObject_dtor(this, 0)` |
| `Sparks_dtor` 0x3c5b90 | table 0x50e998; `light_dtor(+0x64, 2)`; table 0x5120b8; clear +0x4c; `GameObject_dtor(this, 0)` |
| `Projectile_dtor` 0x3c2940 | table 0x5120b8; clear +0x4c; `GameObject_dtor(this, 0)` |
| `LightEffect_dtor` 0x3c6888 | table 0x50e198; clear +0x88; `light_dtor(+0x4c, 2)`; `GameObject_dtor(this, 0)` |
| `SpellWaveOfFlame_dtor` 0x3d1bd8 | +0x14 = 0x51c330; clear +0x18; +0x14 = 0x515ba0; clear the back list +4 (this unlinks the spell from its owner's +0x364 list, iterator-safe) |

Each then calls `pool_free(this)` as a tail jump when bit 0 of the argument is set. Every
self-end in these spells passes 3. Clearing Holy Strike's +0x58 frees the arc nodes, which
have no partner.

### 6.2 `LightEffect` (Observed)

- **The constructor** 0x201bd8 does `GameObject_ctor` (one shared draw, grid link), table
  0x50e198, and `flags |= 3` (0x201d60). The light is not solid, so the victim finders and
  contact loops skip it, but `world_damageInRadius` does not.
- With a follow object, a handle at +0x88 (0x201d70).
- It sets an end frame `+0xb4 = frame + max(trunc(life × 60), 1)`, where `life` is the
  fourth stack float (0x201d78-0x201de0), and puts the light on the every-frame list
  (0x201e14).
- **The run** 0x1ee050 steps colours and radius and follows its handle. It makes no draw
  and no call, except, at `frame >= +0xb4`, its own slot 1 with 3 (0x1ee204-0x1ee230).
- The runtime keeps only these simulation parts. Colours and radii are presentation.

## 7. Cross-actor hazards found

| # | Finding | Kind | Evidence |
|---|---|---|---|
| 1 | Holy Strike's candidate list (+0x58) is filled by the arc query with partnerless nodes. Destroying a listed target leaves its node, and the bolt then steers toward whatever object the pool puts in that block next, or reads freed memory | Inferred (composition of executed functions) | 0x1a19d0, 0x2eba48, 0x2ebc50; `test_the_candidate_list_outlives_its_target` |
| 2 | A monster's or an ownerless area burst (`world_damageInRadius`, skip flags 0) damages other monsters, corpses, effect objects and the projectile that made it. Each non-creature costs one shared draw | Executed (service) / composition | 0x161270, 0x1e8230; `test_a_monsters_burst_hits_everything_in_the_box` |
| 3 | A "first enemy in the arc list" target (cast aim, Disease Bolt homing) is not the nearest enemy when the nearest creature in the wedge is not an enemy | Inferred | 0x1614f0, 0x1a42b8, 0x2c9eb0 |
| 4 | Projectiles and lights destroy themselves in their own run (slot 1 with 3), not through `obj_delete`. Box queries later in the same tick no longer return them, and their block is immediately the next one of its size class | Executed (destructors) / composition | section 6 |
| 5 | A player's attached spells run in the tail of its run (after its action state). A creature's run first thing in `Creature_run`, which a Skelight calls after its pending damage of that run (round 1, section 4.2) | Observed | 0x1a3f70, 0x112984 |

## 8. Corrections and sharpenings

| Where | Was | Is | Evidence |
|---|---|---|---|
| `symbols/engine.tsv` note of `world_collectObjectsInArc` | "output format not read" | a handle list in the caller's head: partnerless nodes from `handle_insertNode`, the nearest first, the rest in reverse acceptance order; the box is the only range test | Executed |
| `tools/ref_skills_a.py` `EXTERNALS['world_collectObjectsInArc']` note and the `holystrike_ctor` docstring | "objects, nearest first"; "the owner's enemies, nearest first" | only the FIRST entry is the nearest; the rest is in reverse acceptance order | Executed |
| `docs/spec/skills-35-68.md` 1.6, `world_damageInRadius` | `trunc(clamp((outer − d) × k, minDamage, maxDamage))` | raised to `minDamage` first, then capped at `maxDamage` (`min.s`), so `maxDamage` wins when the two cross; the slope is 100 when the span is ≤ 1.0 | Executed |

No patch is proposed.

## 9. What was run

`python3 tools/difftest_combat_spells.py local/SLUS_209.73` was run at seed 20973 with
4,000 cases per entry point. It compared **32,000 cases with 0 mismatches**: the calls with
their arguments, every byte stored outside the stack, the shared seed and the result. The
harness is `tools/difftest_combat_runtime.py`'s. Real in the original: the entry,
`math_cos16` / `math_sin16`, `vec2_dotDelta`, and the C library. Stubs, answered by the same
seeded script on both sides: the box query (random subsets in random order, with
duplicates), slot 20, `damage_apply`, `handle_insertNode` / `handle_addNode` (linking real
nodes in memory, as `ref_core.HandlePool` does), `handle_clear`, `GameObject_dtor`,
`light_dtor` and `pool_free`.

| Entry point | Compared | Instructions executed |
|---|---|---|
| `world_collectObjectsInArc` | 4,000 | 249 of 249 |
| `world_collectInSphere` | 4,000 | 93 of 94 (the padding after the return) |
| `world_damageInRadius` | 4,000 | 160 of 160 |
| `HolyStrike_dtor` | 4,000 | 34 of 34 |
| `Sparks_dtor` | 4,000 | 33 of 33 |
| `Projectile_dtor` | 4,000 | 27 of 27 |
| `LightEffect_dtor` | 4,000 | 30 of 31 (the padding) |
| `SpellWaveOfFlame_dtor` | 4,000 | 29 of 29 |

The harness was checked on deliberately broken models: a changed constant, a `<=` turned
into `<`, and two destructor steps swapped are each caught.

`tools/test_ref_combat_spells.py` has 23 synthetic tests:

- the three services on a synthetic image;
- the cast timing and the constructors' draws;
- Holy Strike: a single hit, the immediate destruction, the light's lifetime, the dangling
  candidate list;
- Wave of Flame: cast-time candidates, the burn ticks and their flags, the status source
  and kill credit, the spell's end;
- Shock of Fire: the player and monster bursts;
- a refusal;
- a self-pin of a three-spell, 150-tick scenario. The self-pin is evidence about the model
  only.

Not run: anything on a console, PCSX2 or the live rig.

## 10. For the native client

1. Make effect objects and spell records from the one pool, with one shared draw each.
   Link objects to the front of the every-frame list. Attach spells to the front of the
   owner's +0x364 list.
2. Run a player's attached spells in the tail of its own run, and a creature's at the
   start of `Creature_run`.
3. Implement the three victim services exactly, insertion rule included (section 3).
   Several skills walk their lists and stop at the first match or at a count.
4. Deliver every hit through `damage_apply` with the owner as the attacker, and keep the
   status-source handle, so that burning kills are credited (section 5).
5. End effects with their destructor at once (section 6). Keep partnerless list nodes as
   they are: they do not follow their objects.

`tools/ref_combat_spells.py` is the executable form:

- `SpellRuntime()` builds the world;
- `give_skill(id, stats)` installs a Skill object with **authored** statistics;
- `queue_cast(caster, id, level)` casts at the end of the caster's next run (an authored
  stand-in for state 5's cast point);
- `cast(...)` casts at once;
- `tick()` runs one pass;
- `trace` gives the order of every service call;
- `QueryModel` holds the executed services and destructors.

## 11. Not done, not known

- **Not composed:** the player's state 5 itself (the authored cast point stands in), and
  the aim search, mana and recast of `Player_castSkill`. All three are executed in
  `tools/difftest_player.py`.
- **The other 98 skills.** Each needs its objects' tables and destructors installed as
  here. Ids with disease entries, or spells `damage_apply` asks about, need the
  attached-spell paths of `damage_apply` (refused).
- **Monster casters**: which classes cast which skills, and when, is outside this document.
  The composition accepts a monster caster (`test_a_monsters_burst_hits_everything_in_the_box`).
- **`LightEffect_run`'s colour steps** and `light_dtor` are presentation and not modelled.
  `Creature_dtor`'s destruction of attached spells is refused (fork E, the destructor
  chain).
- **Net games**: the cast point at weight 0.5, the prediction copy's cast that is ended at
  once, `FlyingText` damage numbers. All are outside the domain.
