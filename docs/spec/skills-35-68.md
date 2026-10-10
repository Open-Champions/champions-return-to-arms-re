# Skills 35–68: implementation specification

Status: second-round document. It specifies the skills with ids 35 to 68 closely enough to
be reimplemented from the text. Everything was read from the executable (SLUS_209.73) through
the decompile and the disassembly; **nothing was run**, so every number here is what the code
computes, not what was seen on a screen. Claims are **Observed** (read at the address given)
unless marked *Inferred* or *Unknown*. The catalogue of all 101 skills, the `Skill` and
`Spell` base layouts and the first-round per-machine audit are in `docs/skills.md`; this
document does not repeat them except where a rebuild needs the exact rule.

The table at the end says, per id, what is fully specified, partly specified and not reached.

Conventions used throughout:

- A **frame** is one simulation tick, 1/60 s. `g_simFrame` (0x44fdcc) is the tick counter.
- Angles are 16-bit, 65536 to a full turn. Positions are (x, y, height). Offsets are hex.
- "slot *n*" is virtual function *n* in `tools/vtab.py` numbering.
- Floats that feed a rounding are given as decimal and as the stored bit pattern.
- "player" means an object with flag 0x40 at +0x0c; "creature" flag 0x20; "the copy" is the
  prediction copy of a machine's own player (flag 0x20000).
- Pseudo-code is ours, written from the behaviour; it is not decompiler output.

## Part 1 — Rules shared by every skill

### 1.1 Random generators

All five generators are the same linear congruential step, `s ← s × 1664525 + 1013904223`
(32-bit), and a draw is the upper 16 bits of the new state (0…65535). `r/65536` is used as a
fraction in [0, 1).

| Generator | State | Synchronised between machines |
|---|---|---|
| shared | `g_randSeed` 0x404464 (inlined at every use) | yes: it is in the sync hash and is restored after prediction |
| cosmetic | `g_cosmeticSeed` 0x404460 | no |
| third | `g_unsyncedSeed2` 0x404468 | no |
| per spell | spell +0x10, `Spell_rand` 0x16a964 | only as long as every machine makes the same calls |
| per object | object +0x44, `GameObject_rand` 0x1509d0 | same condition |

Two draws happen implicitly and are counted in every "Random draws" list below:

- constructing any `Spell` draws the shared generator once (the value seeds spell +0x10);
- constructing any `GameObject` draws the shared generator once (seeds object +0x44). That
  includes objects that are pure presentation, such as `LightEffect` (0xbc bytes, constructor
  0x201bd8) and `FlyingText`. A rebuild that drops such an object must still make the draw.

### 1.2 Statistic lookup

A `Skill` holds two tiers of five statistics: first level, base value, step per level
(layout in `docs/skills.md`). The constants are written by the skill's `initStats`
(slot 9), which `skills_callVslot9All` 0x1ebca0 calls once for every id at start-up.

```
getStat(stat, level)                      -- slot 10, 0x3c85fc; tier 1
    if level == 0 or level < first1[stat]: return 0
    v = (float)base1[stat] + step1[stat] * (float)(level - first1[stat])   -- single precision
    return v >= 0 ? trunc(v + 0.5) : trunc(v - 0.5)

getStatTier2(stat, level, cap)            -- slot 11, 0x3c8690
    if level == 0: return 0
    if cap > 0: level = min(level, cap)
    if first2[stat] is negative (0xffff: no tier 2): use the tier-1 tables
    else: use the tier-2 tables
    same test against "first", same formula and rounding

getStatFor(stat, level, caster, cap)      -- slot 12, 0x3c87f0
    caster != null and caster is a player ? getStat(stat, level)          -- cap ignored
                                          : getStatTier2(stat, level, cap)
getStatForHandle(...)                     -- slot 13, 0x3c8864: same, caster given as a handle
adjustLevel(level, n) = level             -- slot 14, 0x3c88dc: n has no effect
manaFromStat4(level, n) = (float)getStat(4, adjustLevel(level, n))        -- slot 15, 0x3c88e4

getStatRange(spread, stat, level, randomise, &lo, &hi)                    -- slot 8, 0x3c82e4
    v = getStat(stat, level)
    randomise == 0:  lo = round(v - v*spread);  hi = round(v + v*spread)
    randomise != 0:  four shared draws a, b, c, d in this order;
                     lo = round(v - v * (b/65536) * spread)   (a only picks the rounding branch)
                     hi = round(v + v * (d/65536) * spread)   (c likewise)
    lo = max(lo, 1);  hi = max(hi, 1)
```

All Observed at the addresses shown. "round" is half away from zero as above. Slots 8 and
10–15 are not overridden by any class.

### 1.3 How a player's cast is sequenced

The pieces below are in the player area; they are restated because every active skill
depends on them. Observed in `hud_onAssignSpell` 0x1de61c, `Player_run` 0x1a5030,
`Player_castSkill` 0x1a42b8 and `Player_updateCast` 0x1a3f70.

**Binding.** Putting a skill on a button writes an ability record (player record +0x4440,
0x68 bytes each): the fixed marker name that selects the `Skill` code path, +0x20 the skill
id, +0x25 **the skill's kind copied from skill +0x08**, +0x24 the player's rank in the skill
at that moment (0x1de61c). So the ability-record kinds of `docs/player.md` are the skill kinds:

| Skill kind | What the button does |
|---|---|
| 0 | cast with the cast animation (action state 5) |
| 1 | channelled: as 0, then held; mana drains per frame |
| 3 | passive; never bound to a cast |
| 7 | instant: `Player_castSkill` is called directly, no animation, also during a melee swing |
| 8 | fired through the ranged-attack state: the record is remembered at player +0x484 and consumed by the next bow release or throw (Part 2, "Bow skills: shared path"); the recast counter is cleared again right after such a cast |

**Recast counter.** Player +0x4ae (s16) is decremented by one at the top of every
`Player_run` while it is above 0 (0x1a5030, before the pad is chosen).

**Starting a kind-0 or kind-1 cast (action state 2).** When the bound button is accepted the
code computes `cost = skill.manaCost(rank)`, halves it for kind 1, and requires
`cost <= mana` (record +0xc0; 0x1a6f34–0x1a7000); otherwise the "not enough mana" voice line
is requested and nothing happens. It then stores the record's own cooldown field (+0x22; zero in a record
that was never a legacy ability — *Inferred* from the record being zero-filled at character
creation and `hud_onAssignSpell` not writing the field) to +0x4ae, sets the action state to 5
and +0x448 to the frame number (0x1a7694–0x1a76a8). The exact button
and state conditions in front of this (which states accept a new ability, the +0x4bc9
lock-out, the split-screen menu test) were not transcribed — see "Not determined" in Part 4.

**Action state 5, each frame** (after the animation step and `Player_move` in mode 1
offline, mode 6 in a net game), with `phase` = player +0x47b and `rec` = the skill record
selected for this frame, normally player +0x488 (0x1ab5c8–0x1ab834):

```
phase 0:  if !skill.canUse(player): rec = 0; state = 2; stop
          if no animation track with flag 0x8000 exists:
              start the cast animation of the current weapon class
                  (anim_start, blend-in 0.1 s, flags 0x8003; skipped for skill kind 6)
              phase = 1
phase 1:  w = blend weight of the 0x8000 track        -- rises by 1/6 per frame
          if w >= T  (T = 1.0 offline, 0.5 in a net game)  or skill kind == 6:
              phase = 2
              Player_castSkill(player, rec)            -- below
              rec = 0
              if skill kind == 0: track life = min(life, 1); life rate = -0.05833333 per frame
phase 2:  if record kind == 1: mana -= manaCost(rank) / 60
          if no 0x8000 track is alive any more: phase = 0; state = 2; rec = 0
```

Phase 2 as written runs only on frames where a skill record is still selected (the button
is held); on other frames the older, non-skill branch of state 5 (0x1ab838 onward) runs and
`Player_updateCast` below does the ending. That branch was not transcribed.

So a kind-0 skill takes effect on the frame the cast animation reaches full blend weight,
about 6 frames after the animation starts offline and about 3 in a net game (*Inferred* from
the blend rate of `anim_start`, `docs/engine.md`; the first track of an empty animation state
reaches full weight on the next frame). No animation event is involved in the cast itself.

**`Player_castSkill(player, rec)`** (0x1a42b8), in order:

1. Return if +0x4ae > 0, if `rec` is null, or if the record is not a skill record.
2. `skill = g_skillTable[rec.id]`. Return if the player is the copy and skill flag bit 0 is
   clear.
3. Return if `skill.canUse(player)` is 0.
4. Cast position: the midpoint of body-model attachment points 0 and 1 in world space. If
   its height differs from the player's feet height by more than 58.0 (absolute value,
   compared in double precision), the height becomes feet + 58.0.
5. Cast facing: `world_collectObjectsInArc(radius 340.0, arc 20.0°, halfWidth 0, player
   position, player facing, list, no filter)` (§1.6), then the first list entry for which the
   player's slot 20 (is enemy) is non-zero. If there is one,
   `facing = (s16)(0x41c2 − atan2_16(target.x − player.x, target.y − player.y))`; otherwise
   the player's own facing. (0x41c2 is a quarter turn plus 450 units, about 2.5°; why the
   extra 450 is *Unknown*.)
6. `rank` = Player slot 39 (the rank stored for the id); `spell = skill.cast(rank, player,
   &pos, facing)`.
7. If a spell came back: for the copy it is destroyed at once (slot 1, argument 3);
   otherwise it is attached with `creature_addSpell`, and for skill kind 1 it is also linked
   at player +0x588.
8. +0x4ae = skill recast (skill +0x0c) — also when cast returned nothing.
9. `mana −= skill.manaCost(rank)`, times 1/60 for kind 1. There is no test here: the
   affordability test is the one made before the cast started.

**Running attached spells.** A player's spells are run from `Player_updateCast`, which
`Player_run` calls after the action-state switch and **only while the record's hit points
are above 0** (test and call at 0x1ac68c–0x1ac6a8): it recomputes the position of step 4
and calls the player's slot 17, which calls slot 2 (run) of every attached spell with (that
position, the player's facing). A player at 0 hit points therefore has no spell run at all:
its spells are frozen, not ended. `Creature_run` (0x112948), which `Player_run` calls first,
makes the slot-17 call only for non-players, at its very start, with the position
(x, y, height + half the height extent). In both cases the list is walked from its head, and
`handle_link` inserts at the head, so **the most recently attached spell runs first**.
Slot 17 body: 0x11a868.

**Releasing.** After running the spells, `Player_updateCast` returns if `rec` (+0x488) is
still set. Otherwise, unless (the ability button that started the cast is still down, the
state is 5 and mana > 0), and once the 0x8000 animation track is absent or fully blended in:
the cast animation is faded out (life rate −0.058333 per frame), phase = 0, state 5 becomes
2, and a spell linked at +0x588 is destroyed. That is what ends a channelled spell: button
released, mana at or below 0, or the state changed by something else.

### 1.4 When a new spell or object first runs

Observed in the list iterator (`iter_begin` 0x1a1a48, `iter_next` 0x1a1b38), `handle_link`
0x1a1738, `obj_runEveryFrame` 0x14f248 and `runObjects` 0x14b910:

- Lists are walked from the head; the iterator sits behind the node being visited. New
  nodes are linked at the head. **A node linked while a list is being walked is not visited
  by that walk.**
- An object that puts itself on the every-frame run list while `runObjects` is walking it
  (anything created by a player, monster, spell or projectile during its own run) gets its
  **first run on the next frame**. The walks of the 15-frame and 60-frame lists come after
  the every-frame walk, so an object created from those is also first run on the next frame.
- A spell a player attaches to itself during the action-state switch is run **in the same
  frame**, because `Player_updateCast` comes later in the same `Player_run`. A spell a
  monster attaches to itself after its `Creature_run` call is first run on the next frame.
  A spell attached to *another* creature is first run in the same frame if that creature's
  run comes later in the walk, otherwise on the next frame; the order of the run list is
  the order of `obj_runEveryFrame` calls, newest first, and is the same on every machine.
- A spell attached to a creature from inside that creature's own spell walk is not run in
  that walk.

Several "first run this frame or the next?" items in the sections of Parts 2 and 3 were
written before this was read; where a section leaves the question open, this is the answer.

### 1.5 The two other ways into a cast function

- **Monsters** call slot 2 from their own run function with `level` = Creature slot 35 =
  `(int)(g_levelMonsterLevel × 0.3)` (0x118c50) and usually attach the result themselves. No
  mana, no recast counter, no canUse unless the monster calls it. Statistic lookups through
  slots 11–13 then use tier 2 where the skill has one. Many monsters do not call slot 2 at
  all but construct the effect object and pass the `Skill` for its numbers.
- **Weapon procs.** A damage-descriptor entry of type 0x29 inside `damage_apply` (0x1e8230;
  `docs/gameplay.md` §2.5 step 20) calls `g_skillTable[id]->cast(level, attacker,
  &attackerPos, facing)` for any creature attacker after one shared draw, and does not
  attach the returned spell. Because of this path each section below says what its
  functions do when the caster is not a player.

### 1.6 Query helpers the skills use

- `world_collectObjectsInBox(min, max, out[], max)` 0x14a928: grid query; never returns the
  copy; skips objects matching `g_excludeMask`; result in grid-cell order then cell-list
  order (`docs/objects.md`).
- `world_collectObjectsInArc(radius, arcDegrees, halfWidth, pos, facing, outList, filter)`
  0x1614f0. Box query of `pos ± radius` on all three axes (at most 511 objects). An object is
  kept when all of these hold: it is a creature (flag 0x20); flags & 0xd == 0; `filter` is
  null or `filter`'s slot 20 accepts it; if `arcDegrees ≠ −1` it lies on the inner side of
  both edges of a wedge of total angle `arcDegrees` centred on `facing` (2-D; the half angle
  in 16-bit units is `round(arcDegrees × 0.5 × 182.04443)`); if `halfWidth ≠ 0` its sideways
  offset from the facing line is at most `halfWidth`; and its centre is strictly in front of
  `pos` along `facing`. There is no distance test other than the box and no allowance for
  the object's radius. Kept objects go into a handle list: a new one is inserted directly
  after the first node (from the head) whose squared 2-D distance is ≤ its own, or at the
  head if there is none. The head is therefore the nearest object; the rest is only partly
  ordered. Observed.
- `world_damageInRadius(inner, outer, attacker, pos, maxDamage, flags, minDamage, skipFlags)`
  0x161270. Box query `pos ± outer` (at most 127 objects). Skips the attacker, objects with
  `flags & skipFlags`, and — when the attacker is a player — everything its slot 20 rejects.
  `d = |dx| + |dy| − 0.333 × min(|dx|, |dy|) − target radius`. If `d < outer`:
  `dmg = trunc(clamp((outer − d) × k, minDamage, maxDamage))` with
  `k = maxDamage / (outer − inner)`, or 100 when `outer − inner ≤ 1`; then
  `damage_apply(dmg, dmg, target, attacker, 100000, 0, 0, flags, null, 0)`. Observed.
- `damage_apply(min, max, victim, attacker, attackRating, –, –, flags, descriptor, noCrit)`
  0x1e8230: `docs/gameplay.md` §2. An attack rating of 100000 means "cannot miss on rating";
  a null descriptor means four empty effect entries.

### 1.7 Who can learn each skill

From the seven class tree tables read by `skills_screen` 0x1d4660 (`docs/data-tables.md`
§4.6; dumped with `tools/dump_tables.py --table skill_trees`). "Level" is the tree row's
base requirement: rank *r* + 1 needs character level ≥ level + *r*; the maximum rank is 20.
Ten alternative prerequisites are hard-coded at 0x1d558c–0x1d5778 and are not shown.

| Id | Name | Class tree (level; prerequisite) |
|---|---|---|
| 35 | charge | barbarian (15; passive mask 0x40) |
| 36 | darkness | shadowknight (10; skill 59) |
| 37 | shock | wizard (5; any rank in skill 60 or 61) |
| 38 | groundpound | barbarian (15; passive mask 0x40) |
| 39 | convertenemy | cleric (15; skill 20) |
| 40 | convertundead | shadowknight (20; skill 9) |
| 41 | cyclone | barbarian (10; skill 53) |
| 42 | harmtouch | shadowknight (25; skill 97) |
| 43 | firearrow | ranger (10; skill 75) |
| 44 | coldarrow | ranger (5; skill 75) |
| 45 | poisonarrow | ranger (15; skill 44) |
| 46 | multifire | ranger (3; skill 48) |
| 47 | explodearrow | ranger (20; skill 43) |
| 48 | archery | ranger (1; none) |
| 49 | bash | barbarian (5; passive mask 0x10), shadowknight (15; skill 5) |
| 50 | minorhealing | ranger (20; skill 19) |
| 51 | ancestralcall | barbarian (20; skill 62) |
| 52 | root | wizard (23; skill 12) |
| 53 | criticalhit | barbarian (8; skill 2) |
| 54 | holyshield | cleric (8; passive mask 0x40) |
| 55 | healing | cleric (8; skill 16) |
| 56 | coneoffrost | wizard (25; skill 14) |
| 57 | shockoffire | wizard (15; skill 58) |
| 58 | froststorm | wizard (8; skill 23) |
| 59 | lifetap | shadowknight (5; skill 61) |
| 60 | Blunt | all seven classes (1; none) |
| 61 | Slashing | barbarian, shadowknight, ranger, berserker, shaman (1; none) |
| 62 | strongstance | barbarian (10; skill 49) |
| 63 | naturalresistance | barbarian (24; skill 64) |
| 64 | stunningstrike | barbarian (19; skill 35) |
| 65 | giantgrowth | shaman (21; skill 94) |
| 66 | planarwind | shaman (24; skill 80) |
| 67 | shadowstep | shadowknight (12; passive mask 0x40) |
| 68 | resurrect | cleric (25; skill 22) |

Class indices: 0 barbarian, 1 cleric, 2 shadowknight, 3 ranger, 4 wizard, 5 berserker,
6 shaman (the class words are *Inferred* from the tree picture names).

### 1.8 Floating point, and how to read the frame counts below

The rules in this document — constants, formulas, the order of operations, comparisons —
are what the code does. Many sections also give **derived** numbers: "the spell is destroyed
on the 600th call", "positive for 121 runs", worked statistic values. Those were obtained by
simulating the rule in single precision, and unless a section says otherwise the simulation
used IEEE round-to-nearest arithmetic. The console's floating-point unit does not: by the
project's working assumption (`docs/issues/float-divergence.md`; hardware background, not
read from the executable) add, subtract and multiply round toward zero and the
float-to-integer conversion truncates. For timers that step by 1/60 (stored as 0x3c888888,
0.016666666, slightly below 1/60) the two arithmetics differ by one frame in a regular way
(computed for this document for N = 1…40 whole seconds, IEEE round-toward-zero standing in
for the console):

| Timer pattern | Round toward zero (console assumption) | Round to nearest (what most sections quote) |
|---|---|---|
| starts at N.0, subtract 0x3c888888 per call, ends on the first call that leaves it below 0 (or at or below 0) | call 60 × N, for every N | call 60 × N + 1, except N = 5…11 where it is 60 × N |
| starts at 0, add 0x3c888888 per call, ends on the first call that leaves it above N.0 | call 60 × N + 1, for every N | call 60 × N + 1, except N = 5…11 where it is 60 × N |

Checked and found to be the same in both arithmetics: Healing's 68 calls (55), Root's roll
on call 32 and end on call 32 + 60 × duration (52), HarmTouch's 40 runs (42), ShadowStep's
25 calls (67). Different: HolyShield's lifetime (54: 601, 661, 721… under truncation, not
600, 660, 721…), a 2.0-second burn (66: 120 runs under truncation, not 121), the
whole-second countdowns of Resurrect (68), GiantGrowth (65) and the convert glow (39, 40),
which follow the first row of the table. Sections 51, 53 and 60/61 already give both
variants. A rebuild should implement the rule with the console's arithmetic and treat any
other "simulated" count as needing the same one-frame check before relying on it.

Statistic values were compared under both arithmetics for this document, for every
statistic of ids 35–68 and of the ids that share their classes (31, 32, 33, 81, 84, 85, 86):
**tier 1 (player casters, ranks 1–20) gives the same integers either way.** Tier 2 (other
casters, levels 1–40) differs in eleven places, all where a step of 0.1 or 0.35 lands on a
half; the truncating result is one lower:

| Id | Statistic (tier 2) | Levels | Round to nearest | Round toward zero |
|---|---|---|---|---|
| 37 shock | 1 | 15, 25 | 2, 3 | 1, 2 |
| 46 multifire | 2 | 6, 16, 26, 36 | 3, 4, 5, 6 | 2, 3, 4, 5 |
| 57 shockoffire | 2 | 15, 25, 35 | 3, 4, 5 | 2, 3, 4 |
| 58 froststorm | 2 | 11, 31 | 7, 14 | 6, 13 |

## Part 2 — Machinery shared by several skills

### Shared projectile machinery (used by 36, 37, 57 and the arrows)

Everything in this section is **Observed** at the addresses given unless marked otherwise.
Correction to the heading, which is the one the task asked for: of the skills specified
below only **57** (class `Sparks`) and **56** (through class `DummyDamager`) are built on
`Projectile_ctor` and `obj_moveAndCollide`. The effect objects of **36** (`DarknessProjectile`)
and **37** (`ShockProjectile`) call `GameObject_ctor` directly (0x2cf4d8, 0x2c4050), move
themselves by adding a stored per-frame step to their position, and do their own box
queries; they never call `obj_moveAndCollide` and have the empty base slot 6. **58**
(`FrostStormSpell`) is a plain `GameObject` too.

#### GameObject_ctor (0x14cb10) — what every effect object starts with

`GameObject_ctor(obj, Vec3 *pos, classDef, props)`:

| Field | Initial value |
|---|---|
| +0x00, +0x04, +0x08 | 0 (handle heads); +0x08 is then linked into the grid cell of `pos` (cell index `((int)coord + 0x3c00) >> 8` per axis; the off-grid list when outside 0..119) |
| +0x0c flags | 0 |
| +0x10 pos | copy of `pos` |
| +0x1c radius | 24.0 (0x41c00000) |
| +0x20 height extent | 72.0 (0x42900000) |
| +0x24, +0x2c | classDef, props |
| +0x28, +0x29 | bytes 0x19, 0x49 (draw box) |
| +0x34 | 0 |
| +0x44 own generator state | **one shared draw**: `g_randSeed = g_randSeed*1664525 + 1013904223; obj+0x44 = g_randSeed >> 16` (0x14cd54, before the name-property loop) |
| +0x48 | base virtual table 0x5122a8 |

The object is not on any run list until the subclass calls `obj_runEveryFrame` (0x14f248).

#### Projectile_ctor (0x150e48)

`Projectile_ctor(obj a0, Vec3 *pos a1, owner a2, classDef a3)`:

1. `GameObject_ctor(obj, pos, classDef, 0)` (one shared draw).
2. +0x4c (owner handle head) = 0; +0x50 (s8 "has splashed") = 0.
3. +0x1c radius = 12.0 (0x41400000). Height extent stays 72.0.
4. +0x48 = virtual table 0x5120b8 (class `Projectile`; its slot 6 is the empty base function 0x3c7ea8).
5. flags |= 0x4081: 0x1 not solid, 0x80 has an owner handle at +0x4c, 0x4000 transient (never saved).
6. If owner != 0: `handle_link(&obj+0x4c, owner, owner)` (0x150ec8). The owner object is then
   `*(obj+0x4c) + 0xc`; the head becomes 0 when the owner is destroyed, because destroying an
   object clears every handle to it.

Layout added by `Projectile` to `GameObject`: +0x4c handle (owner), +0x50 s8 splash flag;
subclass fields start at +0x54.

#### obj_moveAndCollide (0x1509f8)

`int obj_moveAndCollide(obj a0, Vec3 *velocity a1)`; velocity is in **units per second**.
Returns a bit set: 1 = went under the terrain this frame, 2 = touched at least one object.

```
step = velocity * 0.016666666f            (0x3c888888; each component, single precision)
pos += step                               (x, y and height)
obj_updateGridCell(obj)                   (0x150a9c)
result = 0
h = terrain_height(obj.radius, g_world, pos)          (0x150ac8)
if pos.z < h:                                          (0x150ad4, strict)
    result = 1
    k = 0.099999994f                                   (0x3dcccccc)
    repeat:
        cand = pos - step * k                          (step*k per component, then subtract)
        if terrain_height(obj.radius, g_world, cand) <= cand.z: break
        k = k + 0.099999994f
    while k < 2.0f
    pos = cand            # the last candidate is taken even when no trial succeeded;
                          # at most 19 trials (k = 0.1 ... 1.9000002); the grid cell is NOT
                          # relinked after this back-off (no second obj_updateGridCell)
    if obj[+0x50] == 0 and water_test(12.0, g_world, pos, 0) != 0:      (0x150c00)
        obj[+0x50] = 1
        GameObject_rand(obj)        # ONE draw of the object's own generator, value discarded
        play a splash sound on the object at volume 0.2; water_disturb(700.0, 24.0, g_world, pos)
box = [pos.x - r, pos.x + r] x [pos.y - r, pos.y + r] x [pos.z - hext, pos.z + hext]
       (r = obj+0x1c, hext = obj+0x20)
owner = obj[+0x4c] ? *(obj[+0x4c] + 0xc) : 0
list = world_collectObjectsInBox(box.min, box.max, out, 0x100)       (at most 255 objects)
for o in list, in query order:
    skip if o.flags & 0x201          (not solid, or touch-only)
    skip if o.flags & 0x20000000     (objects that projectiles ignore)
    skip if o == obj or o == owner
    skip if o.z + o.hext < obj.z - obj.hext            (0x150d60)
    skip if obj.z + obj.hext < o.z                     (0x150d70; note: o.z, not o.z - o.hext)
    dx = obj.x - o.x; dy = obj.y - o.y; R = obj.radius + o.radius
    if dx*dx + dy*dy < R*R:                            (0x150db8, strict)
        result |= 2
        o.slot6(o, obj)             # the other object's "touched" first   (0x150ddc)
        obj.slot6(obj, o)           # then the projectile's own "touched"  (0x150df8)
return result
```

Notes that matter for a re-implementation:

- The loop does not stop after the first touch and does not re-check that the projectile
  still exists; a projectile class that wants to die on contact records that in a field and
  is destroyed later by its own run function (`Sparks` and `DummyDamager` both do this).
- The water splash is the only use of the object's own generator inside this function. It
  happens at most once per object and only on a frame in which the terrain test failed.
- Query order is the order of `world_collectObjectsInBox` (0x14a928): grid rows (y cell)
  ascending, columns (x cell) ascending, then each cell's list from its head. An object is
  returned when `(flags & g_excludeMask) == 0`, flag 0x20000 (prediction copy) is clear,
  `min.x <= o.x + o.radius`, `o.x - o.radius <= max.x`, the same on y, `o.z <= max.z` and
  `min.z <= o.z + o.hext` (all comparisons inclusive; 0x14aa54–0x14ab04). At most `max - 1`
  pointers are written, then a null.

#### How slot 6 ("touched") is reached

- A projectile's own slot 6 is reached **only** from its own `obj_moveAndCollide` call
  (0x150df8). Movers that use `obj_moveWithCollision` (0x14d4b8) or `Creature_moveBy`
  (0x113c48) skip every object that has flag 0x1 before any slot 6 call (0x14d75c, 0x1140a4),
  and `Projectile_ctor` sets 0x1. So a creature walking into a projectile does not trigger it.
- `obj_moveWithCollision` is not used by any effect object of skills 36, 37, 56, 57, 58.
- `creature_findEnemyInCone` (0x10cf78) is not used by any of them either: none of these
  projectiles homes. The only aim assistance is in `Player_castSkill` (0x1a42b8), which
  passes the cast function a facing toward the first object of the list returned by
  `world_collectObjectsInArc(340.0, 20.0, 0, playerPos, playerFacing, list, 0)` (its head is
  the nearest) that the player's slot 20 accepts, else the player's own facing
  (0x1a44e8–0x1a4544). Skills 36 and 56 ignore that facing or use it only as described in
  their sections.

#### Creature_setEffectTimer (0x118950)

`Creature_setEffectTimer(float seconds f12, creature a0, which a1, source a2)`: stores
`seconds` in +0x340 (which 0, burn), +0x344 (1, chill), +0x348 (2, shock), +0x34c (3, poison)
or +0x350 (4); then, only when `seconds > 0`, clears the handle at creature+0x360 and links
it to `source` when that is non-null. None of the five skills below calls it directly; it is
reached through the descriptor entries they hand to `damage_apply` (types 0x16, 0x18, 0x1f;
see `docs/gameplay.md` section 2.2).

#### Conventions used below

- "Descriptor" = the 0x44-byte damage descriptor of `docs/gameplay.md` section 2.2. Every
  call site below builds it the same way on its stack: the four entry types (+0x24, +0x2c,
  +0x34, +0x3c) = −1, bytes +0x20 and +0x21 = 0xff, the eight s16 at +0x10..+0x1f = 0; then
  the first entry whose type is −1 or already the wanted type is overwritten. Because the
  descriptor is fresh, that is always entry 0.
- `damage_apply(min, max, victim, attacker, attackRating, a3, t0, flags, desc, noCrit)`;
  a3 and t0 are not read by the callee and are listed only for completeness.
- "Shared draw" = one step of `g_randSeed`; "own draw" = `GameObject_rand(obj)` (state at
  obj+0x44); "spell draw" = `Spell_rand(spell)` (state at spell+0x10).
- A "unit-ball sample" is the rejection loop that appears in every particle emitter here:
  three own (or spell) draws a, b, c → `v = (2a/65536 − 1, 2b/65536 − 1, 2c/65536 − 1)`,
  repeated while `v·v > 1.0`. It consumes 3 draws per attempt, on average about 5.73.
- Frame numbers are values of `g_simFrame` (0x44fdcc). Object run functions (slot 4) are
  called from `runObjects` (0x14b910) once per simulated frame: it walks the active list
  from its head with an iterator, and `obj_runEveryFrame` (0x14f248) pushes a new object at
  the head. An object created from inside another object's run is therefore behind the
  iterator and has its first run on the next simulated frame (**Inferred**: `iter_begin`
  and `iter_next` were not read).
- `pool_new(size)` (0x14fdb8) zero-fills the block (`libc_memset` call at 0x14fe5c), so
  a field that no constructor writes is 0. It can return 0; every constructor call below is
  skipped in that case, together with its shared draw.

### Bow skills: shared path (ids 43-47)

Evidence words: **Observed** = read at the address given; **Inferred**; **Unknown**. One
simulation frame is 1/60 s. "Shared draw" = one step of `g_randSeed` 0x404464; "own draw" = one
step of the object's generator (`GameObject_rand` 0x1509d0, state at object +0x44); "cosmetic
draw" = one step of `g_cosmeticSeed` 0x404460. 16-bit angles: 65536 = one turn, direction of
angle a is (cos a, sin a) in x/y (`math_cos16` 0x166630, `math_sin16` 0x1666e0).

Two corrections to the working notes this section was started from, both **Observed**:

- The kind-8 skills do **not** use player +0x480. That byte (1/2/3/5/6) belongs to the older
  inline abilities with ids 4, 5, 6, 0x13, 0x12, which fire a `MissileWeapon` with a kind
  number (state 2 at 0x1a74f8-0x1a7544 stores the byte; state 0 at 0x1a9170-0x1a94b0 consumes
  it). A skill-object bow skill is carried by player **+0x484** (pointer to the ability
  record), set only at one place (0x1a709c, after the canUse call at 0x1a7088) and
  consumed at the release (0x1a9168).
- `SkillMultiFire_cast` builds plain `MissileWeapon` objects (virtual table 0x50e5a0, 0x1c8
  bytes). The class `MultiFireProjectile` has its own table 0x519128, is 0x78 bytes, and is
  constructed only by the MaleDarkElf code (0x25cab4).

#### S.1 What the five active skills share

| Property | Value | Evidence |
|---|---|---|
| kind (skill +0x08) | 8 | constructors 0x2d5ec0, 0x2d6c20, 0x2d865c, 0x2d98e8, 0x2daafc |
| flags (skill +0x04) | 0, so the prediction copy never casts | same; test at 0x1a4320-0x1a4340 |
| recast (skill +0x0c) | 30, but never effective for a player (S.4 step 13) | constructors; 0x1a917c |
| canUse (slot 1) | caster without object flag 0x40: 1. Player: 1 when record +0x4a86 (weapon animation class) is 4 (bow); otherwise a HUD message for 180 frames on that player's slot and 0 | 0x2d5fc4, 0x2d6d40, 0x2d877c, 0x2d9a18, 0x2dac30 (identical bodies apart from the text key) |
| manaCost (slot 5) | forwards to slot 15 with (level, 20): `(float) getStat(4, level)` (tier 1, statistic 4) | 0x2d6204, 0x2d6f80, 0x2da130 identical; 0x2d8a30 and 0x2dae80 see their sections |
| cast (slot 2) return value | always 0 (no Spell); the effect is a free-standing projectile object | 0x2d60e8, and the same tail in each cast |
| slot 14 `adjustLevel` | base implementation 0x3c88dc (returns the level unchanged) in all six classes; the second argument each cast passes (20, 20, 1, 20, 9 for ids 43-47) therefore has no effect | virtual tables 0x518e70, 0x518f88, 0x5190a0, 0x5191b8, 0x5192d0 |

Because cast returns 0, `Player_castSkill` attaches nothing (0x1a45a4), and a weapon proc
(descriptor type 0x29) has nothing to leak.

#### S.2 Player: how a kind-8 skill is started (action state 2)

All in `Player_run` 0x1a5030, case 2 of the switch at 0x1a5e80. **Observed** unless marked.

Each frame in state 2, in this order:

1. `player+0x484 = 0` (0x1a6c38, first statement of the case).
2. Only when player +0x482 is non-zero (on the ground): R = the forced ability record
   (+0x488) or else the record bound to the ability button pressed last (record +0x4a60
   selects the index byte +0x4a84 or +0x4a85; record address = player record + 0x4440 +
   index x 0x68).
3. `start` becomes true when: R's kind byte (+0x25) is not 2, and (the ability button mask at
   record +0x4a80 is held in pad word +8, or +0x450 is set, or R was forced), and record mana
   (+0xc0) > 1.0, and the recast counter +0x4ae is 0, and level flag word 0x44fe08 bit
   0x10000000 is clear. Offline only: cancelled when the word at 0x41b818[slot] is non-zero and
   nothing is forced. Cancelled when R's skill id is -1, when record byte +0x4bc9 is non-zero,
   or when the global 0x4f7128 is non-zero (message instead).
4. With `start` and R +0x24 non-zero and R being a skill-object record: rank = Player slot 39
   (skill id), cost = `manaCost(rank)` (halved for kind 1 only). When cost <= mana (or cost ==
   999.0): for R kind byte 8, `skill->canUse(player)` is called; on 0 both +0x484 and +0x488
   are cleared; on 1 `player+0x484 = R`. When cost > mana: voice cue 4, nothing else.
   No mana is taken here.
5. Button mask for the attack test: the attack mask `g_btnAttack[slot]` 0x41b980, replaced by
   the ability mask (record +0x4a80) when +0x480 or +0x484 is non-zero (0x1a76c4 on).
6. Bow melee: reached on a frame where the mask of step 5 is held (or a forced record with
   +0x484 set). With a bow or thrown weapon and class index 0, 2 or 3, one **own draw of the
   player** is made (`GameObject_rand(player)`, 0x1a7870), and when draw/65536 <= 0.1 or the
   player has no arrows, `Player_findTarget(72.0)`; a target closer than 60 (3-D) starts a
   melee swing (state 1) instead of the shot unless a bow-melee animation is already playing.
   (Not a bow skill; listed because it runs first and consumes an own draw.)
7. Bow branch (record +0x4a86 == 4, 0x1a7b60 on): nothing happens when all of these hold:
   +0x44c == 0, no instant ability pending, not (forced and +0x484 set), and the mask of step
   5 is not held. Otherwise +0x44c = 0 and:
   - ammunition pointer (record +0x4410) null: the real player (not the copy) scans its 64
     bag entries for an item whose definition slot byte (+0x1c) is 8 and stores the last match
     as the ammunition pointer; the state stays 2 this frame;
   - otherwise, unless (forced and +0x484 set): when the analog value of both the attack
     button and the ability button is below 0.13 (`pad_buttonValue` 0x174d80; in a net game
     the value is 0 or 1) the player only moves/animates and no shot starts;
   - otherwise: if the attack mask is held, +0x480 = 0; **state = 0**.
8. On entering state 0 or 1 (0x1a7eb4): +0x448 = `g_simFrame`, +0x470 = 1.6, +0x461 = 1,
   +0x44c = 0, +0x460 = 0, +0x46c = 0, the extra animation tracks are cleared and the weapon
   class's ranged animation is started with a 0.1 s blend in and out.

So a bow skill needs, on the frame it starts: the ability button held, recast counter 0, more
than 1.0 mana and at least the skill's cost, canUse true (bow in hand), the player on the
ground, and an ammunition stack. The state switch has already been evaluated for this frame;
state 0 code first runs on the next frame.

#### S.3 Player: the ranged attack state (state 0) up to the release

Every frame in state 0 (0x1a80e0 on), **Observed**:

- base = 22 frames (11 when +0x480 == 7, a throw); in a net game (`g_networkMode` != 0) the
  base is halved by a logical shift: 11 (5 for a throw).
- W = the primary weapon item of the active set (record +0x4434 + 4 x set byte +0x4a7c). If W
  exists, its four modifiers are scanned for id 0x14; with value v, speed = 1.0 + 2 x (v x
  0.045) (0x3d3851eb), else speed = 1.0. `Player_animStep(speed, player)`.
- Slow: when the byte at player +0x2fc is 1..60, speed x= (60 - slow) x (1/60) (0x3c888888).
  (This multiplication is after the animation step, so it changes only the release frame.)
- releaseFrame = trunc(base / speed) (single precision divide, convert toward zero).
- The release block of S.4 runs on the one frame where `g_simFrame - player+0x448 ==
  releaseFrame` and the ammunition pointer (record +0x4410) is non-null. If the equality is
  never met (speed changed so that the quotient moved past the current count) there is no
  release in that swing.
- After the block: `player_recalcLoad(slot)`; a fresh press of the attack button (pad word
  +0xc) 15 or more frames after the start sets +0x44c = 1 (queue another shot);
  `Player_move(player, 6 in a net game / 1 offline, pad, 0)`; when animation status bit 0x10
  (+0x11a) is clear: +0x3cc = 0 and, once (float)(frames since +0x448) >= +0x48c x 60, state =
  2. +0x48c is rewritten every frame near the top of `Player_run`: 0.33 (0x3ea8f5c2) with a
  bow or no weapon, 0.15 otherwise (0x1a58d8-0x1a593c), so the earliest exit is frame 20.

Timeline for speed 1.0: start frame F (state 2), state 0 from F+1, release on frame F+22
offline or F+11 in a net game, back to state 2 no earlier than F+20 and not before the
animation flag clears.

#### S.4 The release block (bow), in execution order

0x1a8980-0x1a9574. **Observed.** P = player, T = aim target.

1. Spawn point for a plain arrow: `model_getAttachPoint(1.0, model +0x544, pos, facing,
   animation state +0x114, attach 0, out, 0)`.
2. `Player_findTarget(300.0, P)`; if +0x234 is set the player's slot 26 turns it toward the
   target; a lead point is computed when passive mask 0x200000 has a level (the lead point is
   written to a local that the bow branch does not read afterwards; **Observed** dead value).
3. **Shared draw A**: spreadFacing = (s16 facing) + (draw % 500) - 250 (kept as an int).
4. `world_collectObjectsInArc(340.0, 20.0, 0, P.pos, P.facing, list, 0)`; T = the first list
   entry (head first) that P's slot 20 accepts, else none.
5. **Shared draw B**: with T: a = `math_atan2_16(T.x - P.x, T.y - P.y)`, aim = (s16)((draw %
   500) - a + 0x40c8); without T: aim = (s16)(facing + (draw % 500) - 250).
6. **Shared draw C**: dir = (cos(aim) x 1000, sin(aim) x 1000, (float)((draw % 60) - 30)).
7. Only with T: **shared draw D**: n = unit vector from the spawn point to (T.pos + (0, 0,
   0.5 x T height extent +0x20)); dir = (cos(aim) x 1000, sin(aim) x 1000, clamp(n.z x 1000 +
   (float)((draw % 60) - 30), -300, 300)).
8. Real player only (flag 0x20000 clear), T a creature: T's slot 12 is called with (0.0, kind
   2, P.pos, P) ("you are being aimed at").
9. R = forced record (+0x488) or the currently selected ability record (as in S.2 step 2; this
   is re-read now, it is not necessarily the record stored in +0x484). If R exists and its
   skill id is -1, +0x484 = 0.
10. Ammunition: n = quantity (s16 at ammunition item +4). When +0x484 is set and R's skill id
    is 46: n -= `g_skillTable[46]->getStat(2, rank of skill 46)` (slot 10; real player only).
    Otherwise n -= 1 (real player only). n is clamped to >= 0 (0x1a90a4-0x1a90b0). **So every
    bow skill shot uses one arrow, MultiFire uses as many arrows as it fires at that rank, and
    a short stack is simply emptied; the shot is not reduced.**
11. If W (the bow item, record +0x4434 + 4 x set) is null: skip to step 15 (no shot, no
    ammunition change).
12. Weapon attack rating a = `item_getModifiedField1a(W)`, f = low 32 bits of W's flags;
    a level-script hook is run by name (0x1a90f0); **shared draw E**: (draw % 5) + 1 selects
    one of five shot sounds, played on P.
13. If +0x484 != 0: `Player_castSkill(P, +0x484)` (S.5), then `P+0x4ae = 0`.
    Else the plain or old-style arrow: for the real player, one `MissileWeapon` (S.8) with
    kind = +0x480, the spawn point of step 1, velocity = dir, facing = spreadFacing - 0x4000,
    owner P, damage min/max = record +0xd0 / +0xd4 (R +0x26 / +0x28 for a non-zero kind),
    weapon rating a, item flags f, attack rating = record +0xcc, damage flags = item
    definition +0x20 (bit value 0x4 cleared for a non-zero kind), descriptor = W; then +0x480 = 0.
14. Real player only: n == 0 removes the ammunition item from the bag
    (`inventory_removeItem(slot, index, 0, 0)`) and clears record +0x4410; otherwise the
    quantity is set to n.
15. The target list is released.

Consequences, **Observed**: the cast happens on the release frame of the bow animation, not
when the button is pressed; mana is paid inside `Player_castSkill` on that frame; the five
shared draws A-E are made for every bow release whether or not a skill is pending, and they
are made by the prediction copy too (no flag test before 0x1a8b54-0x1a9138); the values of
draws A-D are not used by a skill shot (the skill computes its own direction). With T present
draws are A, B, C, D, E; without T they are A, B, C, E.

#### S.5 `Player_castSkill` 0x1a42b8 as the bow skills see it

**Observed.** Order:

1. Return when +0x4ae > 0; when the record is null or not a skill-object record; when the
   skill's flag bit 0 is clear and P is the prediction copy (always, for these skills); when
   `canUse(P)` is 0. None of these returns refunds the arrow of S.4 step 10.
2. pos = midpoint of model attach points 0 and 1; when |pos.z - P.z| > 58.0 (compared in
   double precision) pos.z = P.z + 58.0.
3. `world_collectObjectsInArc(340.0, 20.0, 0, P.pos, P.facing, list, 0)`; T = first entry
   P's slot 20 accepts. facing = T ? (s16)(0x41c2 - `math_atan2_16(T.x - P.x, T.y - P.y)`) :
   P.facing. (0x4000 - atan2 is the exact bearing; the constant adds 450 units = 2.47 degrees,
   the middle of the plain arrow's 200..699 spread in S.4 step 5.)
4. rank = Player slot 39 (skill id); `skill->cast(rank, P, &pos, facing)`.
5. +0x4ae = skill +0x0c (30); overwritten with 0 by the caller (S.4 step 13), so a bow skill
   can be fired again as soon as the bow animation allows.
6. record mana (+0xc0) -= `manaCost(rank)`. No lower clamp here (0x1a4684-0x1a4690); the
   start test in S.2 step 4 is the only sufficiency test, 22 (11) frames earlier.

There is no height aiming: every player skill arrow of ids 43-47 flies level (vertical
velocity 0) from pos.z - 12 (the casts subtract 12.0 from the height; MultiFire subtracts 6
to 12, section 46).

#### S.6 The weapon damage record and what the skills take from it

`Player_recalcDamage(player, weaponItem, withElemental)` 0x1b7158 rebuilds record +0xd0
(minimum), +0xd4 (maximum) and +0xcc (attack rating). For a bow (**Observed**, 0x1b71b8 on):

1. min = 1, max = 2, AR = level byte (+0x58) x 20.
2. `item_getDamageRange(weapon, &min, &max, withElemental)`; AR += `item_getModifiedField1a`.
3. Weapon class 4 or 6: min, max and AR each += dexterity (record +0x98) / 4 (toward zero).
4. Weapon class 4: f = Archery fraction (section 48); min += round(min x f); max +=
   round(max x f) (both products use the values after step 3; round half away from zero).
5. Blunt/Slashing multipliers when the item's damage type word (definition +0x20) is 1 or 8;
   a group multiplier from a spell class found on any living player; then x1.5 when status
   counter +0x374 is non-zero and x1.2 when +0x37c is non-zero (each `(int)` truncation).

Callers: `Player_weaponSwapInput` 0x1bb718 (tail call at 0x1bba58 with the active set's
primary weapon and withElemental = 1; called from `Player_run` every frame for the real
player when not paused and no menu lock, call at 0x1a5bf0), `Player_meleeHit` 0x1b6a98
(withElemental = 0), and `stats_screen` 0x1d1db8 (draw code, 0x1d2c38 and 0x1d2d30).

How each skill uses the record (details in the skill sections):

| Skill | Weapon damage | Attack rating | Bow item modifiers (descriptor) |
|---|---|---|---|
| plain arrow | record +0xd0 / +0xd4 **read at the release** and stored in the arrow | record +0xcc | yes (the bow item is the descriptor) |
| 43, 44 | record +0xd0 / +0xd4 **read at the moment of the hit** | 100000 | no (own fire / cold proc slot instead) |
| 45 | record +0xd0 / +0xd4 plus statistic 0, read at the moment of the hit | 100000 | no |
| 46 | round(record x stat0 % / count), read at the release | 10000 | no |
| 47 | none: damage comes from the skill table only | 100000 | no |

#### S.7 Projectile base: `Projectile_ctor` 0x150e48 and `obj_moveAndCollide` 0x1509f8

`Projectile_ctor(obj, pos*, owner, classDef)`: `GameObject_ctor` (one **shared draw** for the
own generator at +0x44; default radius 24, height extent +0x20 = 72.0), then +0x4c = 0,
radius +0x1c = 12.0, flags |= 0x4081 (not solid, has owner handle, transient), byte +0x50 = 0,
and the owner handle at +0x4c is linked when owner is non-null. **Observed.**

`obj_moveAndCollide(obj, vel*)`, as used by every arrow class. **Observed** (0x1509f8-0x150e44):

```
step = vel * (1/60)                      # 0x3c888888; velocities are units per second
pos += step;  obj_updateGridCell(obj)
result = 0
if pos.z < terrain_height(radius, world, pos):          # strictly below
    result = 1
    k = 0.1                                             # 0x3dcccccc
    loop: cand = pos - step * k
          if terrain_height(radius, world, cand) <= cand.z: break
          k += 0.1;  continue while k < 2.0
    pos = cand                                          # last candidate, found or not
    if byte +0x50 == 0 and water_test(12.0, world, pos, 0):
        byte +0x50 = 1; one OWN draw (value unused); splash sound;
        water_disturb(700.0, 24.0, world, pos)
box = [pos.xy - radius, pos.xy + radius] x [pos.z - height, pos.z + height]   # height = +0x20
owner = object behind handle +0x4c, or none
for each o in world_collectObjectsInBox(box, 256):       # at most 255 objects, query order
    skip when o.flags & 0x201, or o.flags & 0x20000000, or o is obj, or o is owner
    skip when o.z + o.height < pos.z - height  or  pos.z + height < o.z
    if (pos.x-o.x)^2 + (pos.y-o.y)^2 < (radius + o.radius)^2:
        result |= 2
        o.slot6(obj)          # "something touched me"
        obj.slot6(o)          # the arrow's onHit
return result                 # bit 0 terrain, bit 1 at least one overlap
```

Notes: the position is not rewound after an object overlap; the loop does not stop after the
first overlap and does not look at whether the arrow has already ended, so an arrow class
whose onHit has no "already hit" guard damages every qualifying object it overlaps on that
frame (true for 43; see each section). The box query never returns the prediction copy.

#### S.8 `MissileWeapon` (plain arrows, and the objects MultiFire creates)

Class table 0x50e5a0, size 0x1c8. `MissileWeapon_ctor` 0x150ee4 takes 17 arguments:
(obj, kind, modelA, modelB, pos*, vel*, facing, owner) in registers and on the stack, in
order: launch sample, impact sample, damage min, damage max, weapon rating, item flags, attack
rating, damage flags, item*. **Observed** (0x150ee4-0x151450).

Fields set by the constructor:

| Offset | Type | Value | Meaning |
|---|---|---|---|
| +0x0c | u32 | \|= 0x4001 (on top of 0x4081) | flags |
| +0x1c / +0x20 | float | 12.0 / 72.0; 24.0 / 100.0 when the item's weapon class is 6 | radius / height extent |
| +0x28 | u8 | 0x48 | Unknown |
| +0x38 | s16 | facing argument | model yaw |
| +0x4c | handle | owner | |
| +0xcc | u8 | 0 | hit state: 0 flying, 1 hit a non-player creature, 2 stopped without damage, 3 hit a player |
| +0xcd | u8 | 1 | activity flag for `obj_updateActive` |
| +0xd0 | s32 | kind | 0 plain; 1, 2, 3, 5, 6 old-style special arrows |
| +0xd4, +0xd8 | s32 | damage min, max | |
| +0xdc, +0xe0 | s32 | weapon rating, item flags | passed to `damage_apply` in the two unused argument slots |
| +0xe4 | s32 | attack rating | |
| +0xe8 | s32 | damage flags | |
| +0xec | s32 | `g_simFrame` + 300 | expiry frame |
| +0xf0 | s32 | handle of the launch sample, or 0 | |
| +0xf4 | s32 | 0 | model sample index it is stuck to |
| +0xf8 | u8 | 1 | Unknown |
| +0xfa, +0xfc | s16 | 0, 0 | spin rate, spin angle |
| +0xfe | u8 | 0 | Unknown |
| +0x124 | handle list | empty | creatures already pierced |
| +0x128 | handle | empty | creature it is stuck in |
| +0x12c | ptr | item | used as the damage descriptor (item modifiers at +0x24 have the descriptor's slot layout) |
| +0x170 | ptr | trail (kind 0, no elemental modifier on the item, level flag 0x100 clear) or 0 | presentation |
| +0x174..+0x1af | light record | orange light, radius 168; unlinked at once for kinds 0 and 3 | presentation; position at +0x1a4 |
| +0x1b0 | float[3] | velocity, units per second | |
| +0x1bc | s32 | impact sample | |
| +0x1c0, +0x1c4 | ptr | modelA, modelB | drawn model |

Shared draws in the constructor: one (the `GameObject_ctor` inside `Projectile_ctor`).

`MissileWeapon_run` 0x15153c each frame, kind 0 (**Observed**):

```
if handle +0x128 set:                         # stuck in a creature: follow it
    +0xcd = obj_updateActive(this, +0xcd, 480)
    host = that creature; if host creature flag 0x20000000000: obj_delete(this); return
    pos = model_getSamplePoint(host scale +0xdc, host model, host anim, host pos, host facing,
                               sample +0xf4);  obj_updateGridCell(this);  return
if +0xcc != 0: destroy (slot 1 with 3); return
r = obj_moveAndCollide(this, velocity)        # onTouch may run inside
res = (r & 1) | (+0xcc != 0 ? 2 : 0)          # an overlap counts only when onTouch set +0xcc
if res != 0:
    +0xec = 0
    if res == 2:
        +0xcc == 2: spark effect (fx_spawn 2, or 0x11 with level flag 0x100)
        +0xcc == 3: +0xec = g_simFrame
        +0xcc == 1: +0xec = g_simFrame + 1
    if res == 1: ground impact effect and sound; impact sample +0x1bc when non-zero
    # res == 3 (terrain and a hit on the same frame): nothing more; expiry is already 0
else: trail point (or, with level flag 0x100, one own draw, and when it is divisible by 3 a
      second own draw and a puff)
if +0xec <= g_simFrame: destroy
```

Lifetime: at most 300 frames (5 s); ended by terrain, by a non-creature object, by a hit.
Range for a 1000 units/s plain arrow: 5000 units.

`MissileWeapon_onTouch(this, other)` 0x152a18 (**Observed**):

1. Return when +0xcc != 0 or other is null.
2. other not a creature: when its class is `AutoContainer` or `Container`, other's slot 2
   (take damage) is called with amount 0.0, attacker 0, flags 0; in every non-creature case
   +0xcc = 2; return.
3. Owner present and a creature: return when `owner.slot20(other)` is 0 (the arrow passes).
4. Return when other is in the pierced list +0x124.
5. Owner is a player and kind is 0 or 3: rank = that player's rank in skill 93;
   (u, p) = statistics 0 and 1 of skill 93 at that rank, each x 0.01
   (`SkillPenetratingArrows_getStats01Fraction` 0x314c88). **Shared draw 1**: unblockable =
   (draw/65536 <= u). **Shared draw 2**: pierce = (draw/65536 <= p); when not pierce the list
   +0x124 is cleared. With rank 0 both fractions are 0.0 and each test still succeeds when the
   draw is exactly 0 (1 in 65536).
6. other a creature and owner a player: return when other is a player and `g_pvpModeA` is 0;
   return when other has object flag 0x1000000 and is not a player. When not pierce and kind
   0: link other at +0x128, +0xf4 = slot 17 (nearest model sample point among those whose
   weight is at least 0.75 of the largest; 0x153314); the link is dropped again when the
   index is 0 or other's class is `Skeleton`. Kinds 1, 5, 6 overwrite +0xe8 and set +0xe4 =
   10000.
7. Deflection chance c (percent): other a player: max of the Dodge-style fractions of skills
   2 and 0x53 at that player's ranks x 100 (`SkillDodge_getStat0Fraction` 0x2e8ac0, truncated);
   other a monster whose slot 36 returns a level L != 0: `g_skillTable[2]->getStatTier2(0, L,
   0)`; else 0. **Shared draw 3** (always): when (draw % 100) + 1 < c the arrow is deflected:
   block sparks for a player, three `item_parseDescriptor` calls with variant -1 (each may
   draw the shared generator through the variant chooser; not traced), possibly a dropped
   prop object (one more constructor draw), `obj_delete(this)`, return.
8. `damage_apply(min = (float)+0xd4, max = (float)+0xd8, victim = other, attacker = owner or
   else this, attack = +0xe4, +0xdc, +0xe0, flags = +0xe8 | (unblockable ? 0x40 : 0),
   descriptor = +0x12c, noCrit = 0)`. Result 1 on a non-player: +0xcc = 1; result 1 on a
   player: +0xcc = 3; result 0: +0xcc = 2.
9. pierce and +0xcc != 0: other is appended to +0x124 and +0xcc = 0 (the arrow flies on and
   can hit the next creature; each creature once).

#### S.9 Monster use of the arrow classes

Monsters do not call the Skill's cast. They allocate the projectile and call its second
constructor (or, the Skeleton, the first), passing the Skill object only as the source of
statistics. Read in full: MaleDarkElf 0x25c304-0x25cb70 (**Observed**):

- level argument = `(int) g_levelMonsterLevel` (the float at 0x4f714c truncated; **not** the
  x 0.3 value of Creature slot 35);
- position = monster position + (0, 0, 0.5 x height extent + 12.0);
- direction = 400 x unit vector from (monster position + 60 height) toward the aim point of
  `Creature_leadTargetPoint(400.0, ...)`, plus 40 x a random point in the unit ball
  (rejection sampling, three own draws of the monster per attempt); the second constructors
  normalise this vector, so only its direction matters; unlike the player's cast it has a
  vertical component;
- owner = the monster; skill = `g_skillTable[43 / 44 / 45]`.

The Skeleton (0x2a724c-0x2a7300) passes (position, facing) to the first constructors of 44,
43 and 47 with the same level argument; the Goblin (0x26c0f0-0x26c124) passes (position,
direction) to the second constructor of 47. The MaleDarkElf volley for 46 is in section 46.
The MaleDarkElf chooses the arrow from the value a virtual call on the object at its +0x50
returns (**Inferred**: the equipped weapon's variant): 1 fire, 2 cold, 3 poison, 6 volley,
anything else a plain `MissileWeapon` (0x25c740-0x25c778); this choice is made only when the
MaleDarkElf's own byte +0x3c8 is 0 (the other path, 0x25cb74 on, was not read).

Statistics tier for a non-player owner: the constructors call slot 12 with cap 10 (slot 11:
level limited to 10, tier-2 table when the statistic has one, else tier 1); the hit handlers
call slot 13 with cap 0 (slot 11 with **no** level limit).

#### S.10 Per-machine notes for the shared path

- `stats_screen` 0x1d1db8 runs from draw code on the machine that shows the page and calls
  `Player_recalcDamage` twice (0x1d2c38; and 0x1d2d30 with the off-hand item of set 0 when set
  0 is active). After the second call record +0xd0 / +0xd4 / +0xcc hold the off-hand weapon's
  numbers on that machine only, until that player's next `Player_run`. A skill arrow of ids
  43-45 that hits in between (its run comes before the player's in the run list) would use
  different damage on that machine. **Observed** code; reachability **Inferred** (needs set 0
  active with a second weapon while an arrow shot from the bow set is still flying, and the
  page open during a running simulation).
- The release block's shared draws A-E are also made when the object is the prediction copy;
  whether the copy's run is bracketed by a save/restore of the shared seed is a netcode
  question not re-examined here.
- `Player_castSkill` returns before any effect for the prediction copy; the copy also skips
  the ammunition store (flag tests at 0x1a9054, 0x1a9078, 0x1a94b4).

#### Functions read (shared path)

| Address | Name | What |
|---|---|---|
| 0x1a5030 | `Player_run` | case 2: 0x1a6c30-0x1a8060; case 0: 0x1a80e0-0x1a9654 |
| 0x1a42b8 | `Player_castSkill` | whole |
| 0x1b7158 | `Player_recalcDamage` | whole |
| 0x1bb718 | `Player_weaponSwapInput` | tail call only |
| 0x150e48 | `Projectile_ctor` | whole |
| 0x1509f8 | `obj_moveAndCollide` | whole |
| 0x14cb10 | `GameObject_ctor` | defaults and the seed draw |
| 0x150ee4 | `MissileWeapon_ctor` | whole |
| 0x15153c | `MissileWeapon_run` | whole (kind 0 path described) |
| 0x152a18 | `MissileWeapon_onTouch` | whole |
| 0x153314 | `MissileWeapon_slot17` | whole; proposed name `MissileWeapon_pickStickSample` is not added because the address is already named |
| 0x314c88, 0x2e8ac0 | passive getters | whole |
| 0x25c304-0x25cb70 | inside MaleDarkElf run 0x25bbe4 | arrow selection and construction |

#### Not determined (shared path)

- Whether an object created during `runObjects` gets its first run on the frame of its
  creation (decides whether a skill arrow moves on the release frame).
- What sets ability record +0x25 to 8 for these skills (assumed: copied from skill +0x08).
- Bits 0x100 and 0x10000000 of the level flag word 0x44fe08; the globals 0x41b818 and
  0x4f7128 that veto an ability start.
- The contents of `MissileWeapon_draw` 0x15253c and the kinds 1, 2, 3, 5, 6 end effects
  (old-style arrows; read only as far as shown above).
- Whether any item carries a type-0x29 proc with ids 43-47 (item data not examined).

## Part 3 — The skills

### 35 charge — SkillCharge

#### Identity

| Item | Value | Evidence |
|---|---|---|
| Skill id | 35 (`g_skillTable[35]` at 0x41b1fc → object 0x6e22a8) | Observed: table word |
| Internal name | charge | Observed: constructor 0x2c8760 |
| Skill class | `SkillCharge`, virtual table 0x518320 | Observed |
| Kind (+0x08) | 0, ordinary active skill | Observed: 0x2c8760 |
| Flags (+0x04) | 0: the prediction copy never casts it | Observed: 0x2c8760; test in `Player_castSkill` 0x1a42b8 |
| Recast (+0x0c) | 30 frames | Observed: 0x2c8760 |
| Effect class | `SpellCharge`, 0x88 bytes, virtual table 0x5183a8 (slot 1 destructor 0x2c9c54, slot 2 run 0x2c8f2c; slots 3 and 4 are the base ones) | Observed |
| Who has it | barbarian tree (base level 15, passive mask 0x40). No monster run function uses id 35 (`docs/monsters.md` §6) | §1.7; Observed for the monster list |
| Slot overrides | 2 cast 0x2c8864, 4 describeRank 0x2c8914, 5 manaCost 0x2c8c80, 7 icon getter 0x3ccf3c, 9 initStats 0x2c87cc. canUse is the base one (0x3c8218, always 1) | Observed: `vtab.py show 518320` |

The skill is a forward rush: the caster runs in a straight line at fixed speed for at most 46
frames, may be steered a little at rank 8 and above, and stops with a recoil on the first
thing it runs into, damaging that thing and (from rank 10) everything around the impact.

#### Statistics

Constants written by `SkillCharge_initStats` 0x2c87cc (**Observed**). There is no tier 2 table
(all five tier 2 "first level" words stay 0xffff), and every use goes through slot 10
(`getStat(stat, level)`), so a non-player caster gets the same numbers.

| Stat | Meaning | First level | Base | Step (decimal, hex) | Tier 2 |
|---|---|---|---|---|---|
| 0 | damage to the creature run into (lower bound of the roll) — Observed: 0x2c975c–0x2c9828 | 1 | 120 | 9.99975872 (0x411fff03) | none |
| 1 | damage to everything else in the impact box (lower bound) — Observed: 0x2c98d8–0x2c99e4 | 10 | 55 | 2.99997997 (0x403fffac) | none |
| 2 | impact box half-size in 12-unit steps — Observed: 0x2c9834–0x2c98d0 | 10 | 3 | 1.33098090 (0x3faa5d95) | none |
| 3 | steering strength; ×0.016 = fraction of the remaining angle turned per frame — Observed: 0x2c95a4, used at 0x1b438c | 8 | 1 | 0.33299500 (0x3eaa7e52) | none |
| 4 | mana cost — Observed: 0x2c8c80 → slot 15 | 1 | 35 | 2.99994993 (0x403fff2e) | none |

Formula for all five: `getStat(stat, level)` of §1.2 (0 below the first level; else
base + step × (level − first) in single precision, rounded half away from zero).

| Rank | s0 damage | s1 area damage | s2 (box half-size = s2 × 12) | s3 (turn fraction) | s4 mana |
|---|---|---|---|---|---|
| 1 | 120 | 0 | 0 (no area part) | 0 (no steering) | 35 |
| 8 | 190 | 0 | 0 | 1 (0.016) | 56 |
| 10 | 210 | 55 | 3 (36 units) | 2 (0.032) | 62 |
| 20 | 310 | 85 | 16 (192 units) | 5 (0.080) | 92 |

Full series (computed with single-precision arithmetic from the constants above):
s0 120, 130, … +10 per rank … 310. s1 from rank 10: 55, 58, 61, 64, 67, 70, 73, 76, 79, 82,
85. s2 from rank 10: 3, 4, 6, 7, 8, 10, 11, 12, 14, 15, 16. s3 from rank 8: 1, 1, 2, 2, 2,
3, 3, 3, 4, 4, 4, 5, 5. s4: 35, 38, … +3 per rank … 92.

The rank text (slot 4, 0x2c8914) prints s0 and round(s0 × 1.2) as a range, the same for s1,
then s2 and s3; that is where the "20 % spread" reading of the damage roll comes from
(**Observed**).

#### Cost and limits

- Mana: `manaCost(level)` = slot 15 `manaFromStat4(level, 20)` = (float) getStat(4, level)
  (0x2c8c80, **Observed**; the second argument 20 is ignored by the base slot 14). Rank 1: 35,
  rank 10: 62, rank 20: 92. Charged once by `Player_castSkill`.
- Recast: player+0x4ae = 30 after the cast (`Player_castSkill`). The counter runs down during
  the rush itself, so it never delays the next use in practice (**Inferred** from the 46-frame
  duration).
- canUse: always 1 (base). No weapon-class, target or state condition in the skill itself.
- General player gates (from `Player_run` state 2 and state 5, **Observed** there, common to
  all kind-0 skills): must be in action state 2 with the ground-contact counter +0x482
  non-zero, the ability button held, mana above 1.0 and at least the cost, +0x4ae equal to 0;
  the cast call is made from state 5 on the frame the cast animation track reaches weight 1.0
  (0.5 in a net game).
- Nothing prevents a cast with nothing in front; the rush then simply times out.

#### Behaviour

Frame numbering: F0 is the simulated frame in which `Player_castSkill` calls the cast
function. Within one `Player_run` the order is: damage processing → action-state handler →
`Player_updateCast` 0x1a3f70, which runs every attached spell (Creature slot 17) when the
player record has hit points above 0 (**Observed**: 0x1ac680 block; `Creature_run` runs
attached spells only for non-players, 0x112948 head).

##### Cast — `SkillCharge_cast` 0x2c8864 (skill, level, caster, pos*, facing)

1. Allocate 0x88 bytes and construct a `SpellCharge` (level, caster, skill). The position and
   facing arguments are copied but never used (**Observed**).
2. If the caster has object flag 0x40 (player): caster+0x58c = 9, and the same store on the
   object returned by `net_objOrGhost(caster)` when it is non-null (on the owner's machine
   that is the prediction copy).
3. Return the spell. `Player_castSkill` attaches it to the caster with `creature_addSpell`.

A non-player caster gets the spell and no state change.

##### Constructor — `SpellCharge_ctor` 0x2c8cb4 (spell, level, caster, skill)

Base `Spell` part (one draw of the shared generator into +0x10), then:

| Offset | Type | Initial value | Meaning |
|---|---|---|---|
| +0x00 | s8 | level | rank used for every statistic (read back sign-extended at 0x2c9664) |
| +0x04 | handle list | 0 | back-list (base) |
| +0x08 | Skill* | the SkillCharge object | |
| +0x0c | Creature* | caster | owner; also the attacker of every damage call |
| +0x10 | u32 | shared draw >> 16 | private generator state (`Spell_rand`) |
| +0x14 | ptr | 0x5183a8 | virtual table |
| +0x18 | — | not written | unused |
| +0x1c … +0x40 | handle[10] | ten new trail handles | presentation (ribbon trails) |
| +0x44 | u32 | `g_simFrame` | frame the rush started |
| +0x48 | s32 | 0 | contact flag: 0 running, 1 something was hit |
| +0x4c … +0x87 | light node | colour words (0x6c, 0x66, 0xd0, 0) twice at +0x56 and +0x5e, radius 103.0 at +0x68 and +0x70, 1/103² (0x38c5ad3b) at +0x6c and +0x74, bytes +0x54/+0x55 = 0, +0x78 = 0, position at +0x7c = caster position | presentation (a light that follows the caster) |

Also in the constructor: a sound on the caster (`spel_bw_bull.anm` from `fx.lmp`), the light
is linked, and each trail gets its first point. No `Spell_rand` call.

##### While rushing — `Player_run` state 9 (case 9 of the switch at 0x1a5e80: 0x1a6bf0)

Each frame, for the real player and for the prediction copy alike (**Observed**):

1. Animation track 3 of the player (object +0x17c…): weight rate +0x188 = 0.1, life +0x18c =
   1.0, life rate +0x190 = 0. `Player_animStep(2.0, player)`: the animation advances at
   double speed; the returned event bits are ignored.
2. `Player_move(player, mode 2, pad, 0)` 0x1b4020:
   - Steering. Let m = min(speedFactor × |stick|, speedFactor), where speedFactor is the
     ordinary walk factor (0.861945 offline, 0.75 in a net game, further scaled as for
     walking) and the stick is zeroed while player+0x481 is counting down or a dialog is
     open. Only if m > 0.01:
     `target = (s16)(atan2_16(stick) − net_getCamYaw(slot) − 0x41c2)`,
     `rate = getStat(3, level) × 0.016` (0x3c83126e) taken from the attached `SpellCharge`
     (found by type); if no `SpellCharge` is attached the rate is 0.4;
     `facing = angle_approach(rate, −1, −1, facing, target)`, i.e.
     `d = (s16)(facing − target); facing = (s16)(facing + trunc(|d| × rate) × (d ≥ 1 ? −1 : +1))`.
     Below rank 8 the rate is 0 and the facing cannot change. (0x1b4360–0x1b43c8)
   - Velocity = (cos16(facing) × 300.0, sin16(facing) × 300.0, 0) using the facing just
     updated (0x1b4be0–0x1b4c08). If the slow amount (+0x2fc) is 1…60 all three components are
     multiplied by (60 − slow) × 0.016666666.
   - Offline with two or more players alive the velocity is passed through
     `Player_clampToScreen`.
   - The per-frame displacement accumulator at +0xbc/+0xc0 (animation root motion left by
     `Player_animStep`, plus any push added this frame) is added as accumulator × 60, the sum
     is handed to `creature_moveSimple` → `obj_moveWithCollision(player, velocity, 0, 0)`,
     and the accumulator is cleared. The mover displaces by velocity × 0.016666666, i.e.
     5.0 units per frame along the facing when nothing else contributes.
   - `obj_moveWithCollision` returns bit 1 = terrain blocked the move, bit 2 = pushed out of
     an object, bit 4 = on the ground. For every solid object the player overlaps it calls
     that object's slot 6 with the player (not for the prediction copy) and then
     `Player_onTouch(player, object)`.
   - After the move: if the player is not the prediction copy, bit 4 is set and bit 1 or bit
     2 is set, `SpellCharge_onContact(findSpellByType(player, SpellCharge), 0)` is called
     (0x1b517c–0x1b51bc). So a wall ends the rush only while the player is on the ground.

`Player_onTouch` 0x1beaf0 (Player slot 6; also called when *another* object's movement runs
into the player): only when the player is not the prediction copy and its state is 9. It
finds the attached `SpellCharge` and calls `SpellCharge_onContact(spell, other)` if
`(other.flags & 0x1000220) == 0x20` (a creature that is neither touch-only nor
friendly-to-players) and `|other.height − player.height| < 60.0`; otherwise
`SpellCharge_onContact(spell, 0)`.

##### Impact — `SpellCharge_onContact` 0x2c95f4 (spell, target or 0)

Does nothing when spell+0x48 is already non-zero, or when a target is given and it has the
dead flag (0x8). Otherwise, with L = spell level and C = spell+0x0c (the caster):

1. Sound on C (`spel_bw_bull_hit.anm`), `camera_shake(10.0, 0)`.
2. If target is 0: eight impact puffs, each `fx_spawn(2, p)` with
   p = (C.x − 6 + Spell_rand % 12, C.y − 6 + Spell_rand % 12, C.height + Spell_rand % 72)
   (three private draws per puff, in x, y, height order).
3. If target is non-zero: `d0 = getStat(0, L)`. The hit is made when the target is not a
   creature, or `C->isEnemy(target)` (Creature slot 20) is non-zero. Then one private draw r:
   `damage_apply(min = (float)d0, max = d0 + (d0 × (r × 1/65536)) × 0.19999999, victim =
   target, attacker = C, attack rating = 100000, 0, 0, flags = 0x8c040, descriptor = 0,
   noCrit = 0)`. No descriptor entries. A target that is a creature and not an enemy is not
   damaged, but the rush still ends on it.
4. `R = getStat(2, L) × 12` (integer). If R ≠ 0:
   - `world_collectObjectsInBox(C.pos − (R,R,R), C.pos + (R,R,R), list, 128)` (at most 127
     objects).
   - `d1 = getStat(1, L)`.
   - For each object o in list order: skip when o is C, o is the target, or o has flag 0x8;
     skip when o is a creature and `C->isEnemy(o)` is 0; otherwise one private draw r and
     `damage_apply((float)d1, d1 + (d1 × (r × 1/65536)) × 0.19999999, o, C, 100000, 0, 0,
     0x8c040, 0, 0)`. Non-creature objects in the box are always hit.
   - A ring of particles (presentation, but it consumes private draws): for angle a = 0,
     500, …, 65500 (132 steps): repeat {three private draws} until the three values mapped to
     [−1, 1) lie inside the unit sphere; one more private draw; two particles.
5. spell+0x48 = 1.

Flags 0x8c040 = 0x40 (cannot be blocked) | 0x4000 (no hit sound) | 0x8000 (no miss sound) |
0x80000 (not tested by `damage_apply`; handed to take-damage). Everything else about the hit
(armour scaling for player victims, the shared-generator rolls, floating numbers) is the
ordinary `damage_apply` sequence of `docs/gameplay.md` §2.5 with an empty descriptor and
attack rating 100000.

##### Every frame — `SpellCharge_run` 0x2c8f2c (spell slot 2)

```
elapsed = g_simFrame - spell.start            (unsigned, converted to float)
if spell.hit != 0 or elapsed > 45.0:
    if caster is a player:
        g = net_objOrGhost(caster)
        if spell.hit == 0:
            g.state = 2; caster.state = 2
        else:
            g.state = 3; caster.state = 3              # staggered
            caster track 3 life rate (+0x190) = -0.058333 (0xbd6eeeee)
            player_voice(slot, 12)
            anim_startBlendInOut(0.1, 0.1, caster anim state,
                                 stagger clip of the caster's weapon class, flags 10)
            damage_apply(10.0, 10.0, victim = caster, attacker = caster, 100000, 0, 0,
                         flags 0x4000c040, descriptor 0, noCrit 0)
    g_forceGhostRebase = 1
    destroy the spell (slot 1 with argument 3)
else:
    move the ten trails and the light to the caster (presentation)
    15 particles on random model sample points (private draws, see below)
    g_forceGhostRebase = 1
```

- The stagger clip is the entry at +0x7c of the weapon-class row (0x68 bytes per class, row
  index = player record +0x4a86) of the table at player+0x24: the same clip
  `Player_processDamage` uses for an ordinary stagger (**Observed**: 0x2c901c–0x2c9068
  against 0x1b2cc0 line of the same form).
- The self-hit of 10 uses flags 0x40 | 0x4000 | 0x8000 | 0x40000000 (no skill critical
  bonus). It goes through the whole of `damage_apply` with the caster as both sides, so a
  player caster loses 10 minus the usual armour reduction (each bound loses armour/30, at
  most half), halved again in PvP mode A, and the shared-generator rolls of §2.5 are made.
  Because the state is already 3 when `Player_processDamage` sees the damage on the next
  frame, no stagger roll is made for it (**Observed**: 0x1b2cc0 tests state ≠ 3 first).
- State 3 ends, as for any stagger, when no animation track with flag 0x8 is left
  (`Player_run` case 3), i.e. when the stagger clip has played out.

##### Timeline

| Frame | What happens |
|---|---|
| F0 | cast: spell created (start = F0), state 9. Same frame, later: `SpellCharge_run` with elapsed 0 (particles only) |
| F0+1 … F0+46 | state 9 handler moves the player 5 units; contact tests during that move (and during other objects' moves); then `SpellCharge_run` |
| frame of contact | damage calls happen inside `SpellCharge_onContact` at the moment of contact. The next `SpellCharge_run` (same frame if the contact came from the player's own move, otherwise the next frame after one more state-9 move) ends the rush with the stagger and the self-hit |
| F0+46 | if nothing was hit: elapsed 46 > 45, state back to 2, spell destroyed. 46 moves, 230 units at full speed |

Other rules (**Observed** unless marked):

- Only the first contact counts; later calls return at the top because +0x48 is set.
- `Player_processDamage` does not protect state 9 the way it protects states 6 and 10: a
  staggering or knock-down hit during the rush puts the player in state 3 (0x1b2cc0). The
  spell keeps running; contact calls stop (they need state 9), and when the 46 frames are up
  the spell writes state 2 regardless of the current state, cutting the stagger short.
- While the player record has no hit points `Player_updateCast` is not called, so a dead
  caster's spell is frozen; it is freed with the player object (**Inferred** from the
  call condition and the Creature destructor).
- Non-player owner: `SpellCharge_run` only shows the trails and particles for 46 frames and
  frees itself; nothing moves the creature and nothing calls `SpellCharge_onContact`
  (its two callers are player functions).

##### Destructor — `SpellCharge_dtor` 0x2c9c54

Unlinks the light, releases the ten trails, destroys the light node, clears the handle
back-list, frees the block when bit 0 of the argument is set.

#### Random draws

Shared generator (`g_randSeed`):

1. `SpellCharge_ctor`: one draw (seed of the private generator).
2. Inside each `damage_apply` call (target hit, each area hit, the self-hit): the sequence
   of `docs/gameplay.md` §2.5. Note the base roll there is skipped when min == max, which
   for the two rolled hits happens only when the private draw is 0 or the statistic is 0,
   and is always the case for the self-hit.

Private generator (`Spell_rand`, state at spell+0x10), in execution order:

1. Every non-final `SpellCharge_run` (including the one on F0): 4 + 11 times
   {one draw: sample point index = draw % `model_getSamplePointCount(caster model)`;
   then repeat {three draws x, y, z, each mapped as 2 × (draw × 1/65536) − 1} while
   1.0 < (x² + y²) + z²}. The number of draws per frame is therefore at least 60 and
   depends on the rejections.
2. `SpellCharge_onContact` with no target: 8 × 3 draws (puff positions).
3. `SpellCharge_onContact` with a target that is hit: one draw (upper bound of the damage).
4. Area part: one draw per object actually damaged, in box-query order.
5. Area part, particle ring: 132 × ({three draws} repeated until inside the unit sphere,
   then one draw for the particle's upward speed, 10 + 5 × fraction).

The final `SpellCharge_run` makes no private draw.

#### Presentation only

Ten ribbon trails and a bluish light following the caster; two particle types per frame
(definitions 0x8e5000 and 0x8e4fb0) and a third for the impact ring (0x8e5050), all three
registered by the static initialiser 0x2c9d20; cast and impact sounds; `camera_shake(10, 0)`;
`fx_spawn(2)` puffs on a wall impact; the caster's voice line 12 on impact; the run animation
at double speed and the stagger clip.

#### Per-machine state

- `net_objOrGhost` in `SkillCharge_cast` (0x2c88e4) and `SpellCharge_run` (0x2c8fe0): the
  extra state store lands on this machine's prediction copy only. **Observed**; not shared
  state.
- `g_forceGhostRebase` is set to 1 by `SpellCharge_run` on every frame and at the end, for
  any owner (0x2c90c8, 0x2c9570). Per-machine presentation state.
- The prediction copy has no attached spells (`Creature_clone` starts the list empty), so
  while it predicts state 9 `Player_move` steers it at rate 0.4 instead of the statistic.
  Prediction only; the rebase flag above corrects it.
- Both contact routes are guarded against the copy (`Player_onTouch` 0x1beb10, `Player_move`
  0x1b5188). `obj_moveWithCollision` also does not call other objects' slot 6 for the copy.
- Non-player caster: both uses of +0x3c8 and of the player record in `SpellCharge_run` are
  inside the flag-0x40 branch. **Observed.**
- Weapon-effect cast (damage descriptor type 0x29 with id 35): the returned spell is not
  attached, so it never runs and is never freed (ten trail handles of a pool of 64 and a
  linked light stay allocated). If the attacker is a player it is left in state 9 with no
  spell: nothing ends the rush except a stagger, and both contact routes then call
  `SpellCharge_onContact` with a null spell pointer (the function reads +0x48 of it without
  a test). **Observed** code path; whether any item carries such an entry is **Unknown**.
- The area damage count depends on which objects the box query returns; that query skips
  objects matching `g_excludeMask` (a global of the object area) — not examined here.
- `player_voice` and `camera_shake` are local presentation. Nothing reads the camera, the
  local slot, audio, the cosmetic generator or 0x404468 for a gameplay decision in these
  functions. The steering input (`net_getCamYaw`, the pad) comes from the lockstep input
  record in a net game.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2c8760 | `SkillCharge_ctor` | name, kind 0, recast 30, table 0x518320 |
| 0x2c87cc | `SkillCharge_initStats` | the statistic constants |
| 0x2c8864 | `SkillCharge_cast` | creates the spell, puts a player caster in state 9 |
| 0x2c8914 | `SkillCharge_describeRank` | rank text; confirmed the meaning of s0–s3 |
| 0x2c8c80 | `SkillCharge_manaCost` | slot 15 with (level, 20) |
| 0x2c8cb4 | `SpellCharge_ctor` | |
| 0x2c8f2c | `SpellCharge_run` | timer, end of rush, self-hit |
| 0x2c95a4 | `SpellCharge_getStat3Scaled` | getStat(3, level) × 0.016; called by `Player_move` |
| 0x2c95f4 | `SpellCharge_onContact` (proposed) | impact damage; callers `Player_onTouch` 0x1beb98 and `Player_move` 0x1b51bc |
| 0x2c9c54 | `SpellCharge_dtor` | |
| 0x2c9d20 | `charge_staticInit` | three particle definitions |
| 0x1beaf0 | `Player_onTouch` | Player slot 6 |
| 0x1b4020 | `Player_move` | mode 2 branch, steering, wall contact |
| 0x1a5030 | `Player_run` | case 9; cases 2, 3 and 5 for the cast path and the stagger exit |
| 0x1a3f70 | `Player_updateCast` | where a player's attached spells are run |
| 0x1a42b8 | `Player_castSkill` | |
| 0x14d4b8 | `obj_moveWithCollision` | return bits and slot 6 calls |
| 0x166c18 | `angle_approach` | |
| 0x1b2cc0 | `Player_processDamage` | which states are protected from stagger |
| 0x1b2470 | `player_resetIdleAnim` | flags of the four base tracks |

#### Not determined

- The four base locomotion tracks have flags 0x1205 (`player_resetIdleAnim` 0x1b2470), which
  do not include root motion, so they add nothing to the 5 units per frame (**Observed**).
  Whether a root-motion track from an earlier action (an attack clip still fading out) can be
  alive at the start of a rush and add its delta was not examined.
- The speed-factor details of `Player_move` (level-name special case, record +0x4c20, the
  global at 0x4f8418) matter here only for the "stick deflected" threshold m > 0.01 and were
  not traced to their writers.
- Which item, if any, carries a type-0x29 effect with skill id 35.
- The outcome on real hardware of the null spell pointer in the unattached-spell case.
- `fx_spawn(2)`, `camera_shake` and the take-damage implementations of the victims were not
  read.

### 36 darkness — SkillDarkness

#### Identity

- Id 36, internal name `darkness`. Skill class `SkillDarkness`, virtual table 0x5188a0,
  static object 0x6e2310 (`g_skillTable[36]` at 0x41b200), constructor 0x2cf0e4. Kind 0
  (ordinary, active), flags 0, recast 30 frames.
- Creates one `DarknessProjectile` per cast: size 0xb0, virtual table 0x518810, base class
  `GameObject` directly. Slots: 1 destructor 0x3cd5b0, 4 run 0x2cf690; slot 5 (draw) and
  slot 6 (touched) are the empty base functions, so everything it does is in run.
- The cast function returns 0 (no `Spell`).
- Players: shadowknight tree, base level 10, prerequisite skill 59. No monster run function
  references `g_skillTable[36]` (search for the table slot 0x41b200: no users).

#### Statistics

`SkillDarkness_initStats` 0x2cf150. Tier 2 is "none" for every statistic.

| Stat | Meaning | Tier 1: first, base, step |
|---|---|---|
| 0 | blind threshold T: a roll succeeds when (draw mod 100) + 1 < T (Observed 0x2cf7bc–0x2cf804) | 1, 50, 1.99998 (0x3fffff58) |
| 1 | damage centre value (Observed 0x2cfa7c–0x2cfaf0) | 1, 35, 3.000002 (0x40400008) |
| 2 | seconds the cloud stays after it attaches (Observed 0x2cf9b8–0x2cfa1c) | 1, 1, 0.33300298 (0x3eaa7f5e) |
| 3 | seconds of blindness per successful roll (Observed 0x2cf80c–0x2cf864) | 1, 3, 0.25100398 (0x3e808398) |
| 4 | mana (0x2cf42c) | 1, 33, 3.9998338 (0x407ffd47) |

Every read is **slot 10** (`getStat`, tier 1, no cap), with the level stored in the object;
the caster's type is never consulted. Damage uses slot 8:
`getStatRange(0.19999999 (0x3e4ccccc), stat 1, level, randomise 0, &lo, &hi)`, i.e. with
v = (float) getStat(1, level): lo = round(v − v·0.19999999), hi = round(v + v·0.19999999)
(single precision, half away from zero, each raised to at least 1); no draw.

| Rank | 1 | 10 | 20 |
|---|---|---|---|
| stat 0 (success chance = (T − 1) %, see Behaviour) | 50 | 68 | 88 |
| stat 1 → lo..hi | 35 → 28..42 | 62 → 50..74 | 92 → 74..110 |
| stat 2 → cloud frames | 1 → 60 | 4 → 240 | 7 → 420 |
| stat 3 → blind frames | 3 → 180 | 5 → 300 | 8 → 480 |
| stat 4 | 33 | 69 | 109 |

Stat 2 by rank 1..20: 1 1 2 2 2 3 3 3 4 4 4 5 5 5 6 6 6 7 7 7. Stat 3: 3 3 4 4 4 4 5 5 5 5 6
6 6 6 7 7 7 7 8 8. Stat 0 = 50 + 2·(rank − 1); stat 1 = 35 + 3·(rank − 1); stat 4 = 33 +
4·(rank − 1) (exact for ranks 1..20).

#### Cost and limits

- Mana: slot 5 = slot 15(rank, 1) = (float) getStat(4, rank): 33, 69, 109 at ranks 1, 10, 20.
- Recast 30 frames. canUse: base function, always 1.

#### Behaviour

**Cast** — `SkillDarkness_cast(skill, level, caster, Vec3 *pos, s16 facing)` 0x2cf1e0:

- velocity = (cos16(facing) · 373.0, sin16(facing) · 373.0, 0 · 373.0) units per second
  (0x43ba8000; the direction is **not** normalised, so the speed carries the small error of
  the two table functions).
- start position = (caster.x + 0.0, caster.y, caster.z + 36.0) (0x2cf2c4–0x2cf2f0). The
  `pos` argument is copied to the stack and never used (Observed). The caster pointer is
  dereferenced without a null test.
- `DarknessProjectile_ctor(obj, &start, &velocity, skill, level, caster)` on a 0xb0-byte
  block; returns 0.

**Constructor** 0x2cf460:

1. `GameObject_ctor(obj, start, 0, 0)` — one shared draw (0x2cf4d8). Radius and height
   extent keep the base values 24.0 and 72.0 (they are not used by this class).
2. Light node at +0x58 (radius 168.0, position +0x88 = start), linked.
3. +0xa4 = 0, +0xa8 (caster handle) = 0; flags |= 0x4001 (not solid, transient).
4. +0x4c step = velocity · 0.016666666 per component: 373 × 0.016666666 = 6.2166662 units
   per frame along the facing.
5. +0x94 life = 108 (0x6c); +0xac = skill; +0x98 = level (s32); +0xa0 attached = 0;
   +0x9c moving = 1.
6. A sound on the caster; `handle_link(&obj+0xa8, caster, caster)` when the caster is
   non-null; the light colour is set from a level colour (presentation);
   `obj_runEveryFrame(obj)`.

**Run** 0x2cf690, once per frame:

```
level = obj[+0x98]
if attached(+0xa0) == 1:
    if g_simFrame % 30 == 0 and casterHandle != 0:                    (0x2cf6d4–0x2cf734)
        list = world_collectObjectsInBox(pos - 24, pos + 24, out, 0x80)     # 127 objects
        for o in list, in query order:
            if caster.slot20(o) != 0 and o.hp(+0x228) > 0.0 and o.noTargetTimer(+0x316) == 0:
                T = getStat(0, level)
                r = GameObject_rand(obj)                # own draw, only for such objects
                if (r % 100) + 1 < T:                   # unsigned remainder; chance (T-1) %
                    frames = getStat(3, level) * 60
                    if creature_bossRank(o) != 0: frames = (frames >> 1) + 1
                    o.slot31(frames)                    # Creature_setNoTargetTimer
else:
    if moving(+0x9c) != 0:
        pos += step                                      # x, y and height; no grid relink
        if pos.z < terrain_height(24.0, g_world, pos): moving = 0      (0x2cf8f0–0x2cf910)
    if casterHandle != 0:
        list = world_collectObjectsInBox(pos - 24, pos + 24, out, 0x80)  # box taken here
        for o in list, in query order:
            if caster.slot20(o) == 0: continue
            if attached == 0:                            # first enemy found
                attached = 1
                life(+0x94) = getStat(2, level) * 60
                pos = (o.x + 0.0, o.y, o.z + 36.0)       # jumps onto the victim, then stays
            if caster.slot20(o) != 0:                    # asked a second time
                getStatRange(0.19999999, 1, level, 0, &lo, &hi)
                damage_apply((float)lo, (float)hi, o, caster, 100000, 0, 0, 0x40, 0, 0)
light position = pos; relink the light
8 particles (own generator)
life -= 1
if life == -1: obj_delete(obj); unlink the light                       (0x2cfd40–0x2cfd58)
```

Consequences, all Observed in the code above:

- **Flight.** The cloud flies in a straight line at its starting height (step.z = 0)
  for at most 109 runs (life 108 → −1), about 678 units. Terrain above its
  height stops it (`moving = 0`); it then sits there, still testing its box every frame,
  until its life runs out.
- **Impact test.** Every frame while not attached. The box is ±24 on all three axes; the
  query enlarges it by each object's radius in x and y (a square, not a circle) and accepts
  an object whose span [o.z, o.z + o.hext] meets [pos.z − 24, pos.z + 24]. The first object
  in query order that the caster's slot 20 calls an enemy attaches the cloud.
- **Damage.** Dealt once, on the impact frame only, to **every** enemy in that same box
  list from the attaching one onward (objects earlier in the list were not enemies, so in
  effect to every enemy in the box). The box is the one taken before the cloud jumped onto
  the first victim. Each victim gets its own `damage_apply` call: min = lo, max = hi as
  floats, attack rating 100000, flags 0x40 (cannot be blocked, ignores Spirit Shield), no
  descriptor, critical hits allowed. The base roll between lo and hi is the callee's.
- **Cloud.** After attaching the cloud does not move (it does not follow the victim). Its
  life becomes 60 × stat 2 and is decremented on the impact frame too, so it runs on
  60 × stat 2 further frames and is deleted at the end of the last one (deferred delete:
  destroyed at the start of the next `runObjects`).
- **Blinding.** On every frame of the attached phase whose global frame number is a
  multiple of 30 (not on the impact frame itself, which took the other branch), each live
  enemy in the ±24 box whose no-target timer is 0 gets one roll with success chance
  (T − 1)/100 — the remainder is taken of a 16-bit value, so residues 0..35 are very
  slightly favoured. Success calls the victim's slot 31 with 60 × stat 3 frames. The base
  implementation `Creature_setNoTargetTimer` (0x118af8, shared by 75 classes including
  `Player`) does nothing in PvP mode A and nothing for a creature of non-zero boss rank;
  otherwise it stores the frames in +0x316 and drops the creature's current target. The
  "halve and add one" adjustment for boss ranks made by the cloud is therefore without
  effect for every class that uses the base slot 31 (Observed 0x118af8; no overriding class
  was looked for).
- **Caster gone.** When the caster handle is empty the cloud neither attaches, damages nor
  blinds; it only flies, emits particles and expires.

**DarknessProjectile fields**:

| Offset | Type | Meaning |
|---|---|---|
| +0x4c | float[3] | per-frame step |
| +0x58 | light node, 0x30 bytes | colours +0x62..+0x71, radius +0x74/+0x7c = 168.0, inverse square +0x78/+0x80, position +0x88 |
| +0x94 | s32 | life counter: 108 at creation, 60 × stat 2 at impact; object deleted when it reaches −1 |
| +0x98 | s32 | level |
| +0x9c | s32 | 1 while moving; 0 after the terrain stopped it |
| +0xa0 | s8 | 1 once attached to a victim position |
| +0xa4 | handle | cleared by the destructor; never linked in the functions read |
| +0xa8 | handle | caster |
| +0xac | ptr | the Skill |

#### Random draws

1. Cast: 1 shared draw (constructor).
2. Impact frame: no draw for the range (randomise = 0); then the draws of `damage_apply` for
   each victim in box order (base roll because lo < hi, hit rolls, procs, crit roll when the
   attacker has a crit chance).
3. Every run: 8 unit-ball samples of the **own** generator for the particles (0x2cfb3c–
   0x2cfd38), after the gameplay part of the frame.
4. Attached phase, frames with `g_simFrame % 30 == 0`: one **own** draw per eligible enemy
   in box order (the blind roll). This is the same generator as item 3, so the blind rolls
   depend on how many attempts the particle samples of all earlier frames needed. A
   re-implementation must reproduce the particle sampling loop exactly to reproduce the
   blind rolls.

#### Presentation only

One cast sound on the caster; a dynamic light whose colour is set to 1 minus three bytes
read from 0x5d3478 (a "negative" light) and which follows the cloud; 8 particles per frame
(particle type 0x8e5410) placed at pos + 24·v with velocity step − 0.3167·v for a unit-ball
sample v. There is no draw function and no HUD text.

#### Per-machine state

None found in the gameplay path: no camera, pad, local-slot or option reads. The three
bytes at 0x5d3478 feed only the light colour. The own-generator coupling described under
Random draws is deterministic as long as every machine runs the object on the same frames.
The cloud does not relink its grid cell while it flies (no `obj_updateGridCell` in run), so
it stays in the cell of its birth position; that only affects queries that would return
the cloud itself.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2cf0e4 | SkillDarkness_ctor | Skill constructor |
| 0x2cf150 | SkillDarkness_initStats | statistic tables |
| 0x2cf1e0 | SkillDarkness_cast | builds velocity and start position, constructs the cloud |
| 0x2cf320 | SkillDarkness_describeRank | text arguments: stat 1 range, stat 0, stat 3 |
| 0x2cf42c | SkillDarkness_manaCost | slot 15 with (rank, 1) |
| 0x2cf460 | DarknessProjectile_ctor | above |
| 0x2cf690 | DarknessProjectile_run | above |
| 0x3cd5b0 | DarknessProjectile_dtor | clears two handles and the light |
| 0x3c82e4 | Skill slot 8 (getStatRange) | range arithmetic |
| 0x118af8 | Creature_setNoTargetTimer | slot 31 |
| 0x10d940 | creature_bossRank | 0 / 1 / 2 |
| 0x14a028 | (unnamed) | copies the four bytes at 0x5d3478 into four u16; only caller is the constructor (0x2cf634) |

#### Not determined

- What the bytes at 0x5d3478 are (Inferred: the level's ambient light colour).
- What the no-target timer does to a creature beyond dropping its target (see
  `docs/creatures.md`, +0x316); whether any class overrides slot 31.
- The rank description (0x2cf320) was read only for which statistics it prints.
- Whether a weapon proc (descriptor type 0x29) ever names skill 36; if it does, the cloud
  starts at the attacker's origin + 36 like any other cast, since the position argument is
  ignored.

### 37 shock — SkillShock

#### Identity

- Id 37, internal name `shock`. Skill class `SkillShock`, virtual table 0x518210, static
  object 0x6e2378 (`g_skillTable[37]` at 0x41b204), constructor 0x2c3c68. Kind 0 (ordinary,
  active), flags 0 (the prediction copy never casts it), recast 30 frames (+0x0c = 0x1e,
  0x2c3c68).
- Creates one `ShockProjectile` per cast: size 0x198, virtual table 0x50e228, base class
  `GameObject` directly (not `Projectile`). Slots: 1 destructor 0x2c3f5c, 4 run 0x2c42e4,
  5 draw 0x2c4e64, 6 the empty base, 15 clone 0x13da90 (returns 0).
- The cast function returns 0: no `Spell` is created and nothing is attached to the caster.
- Players: wizard tree, base level 5, prerequisite any rank in skill 60 or 61 (§1.7).
- Monsters that call slot 2 on it: FemaleDarkElf (0x259a98), Goblin (0x26b27c), Hag
  (0x26f504), Orc (0x2a1848). All four pass level = own slot 35, caster = self, position =
  (x, y, height + height extent × 0.5) and either their facing (+0x38: Hag, Orc) or an aim
  angle computed just before (FemaleDarkElf, Goblin).

#### Statistics

`SkillShock_initStats` 0x2c3cd4. Unlisted entries are 0 (tier 1) or "none" (tier 2 first
level 0xffff).

| Stat | Meaning | Tier 1: first, base, step | Tier 2: first, base, step |
|---|---|---|---|
| 0 | lightning damage D (Observed: 0x2c4750–0x2c4838, descriptor entry) | 1, 77, 8.9995365 (0x410ffe1a) | 1, 2, 2.0000019 (0x40000008) |
| 1 | extra chain victims; the projectile may hit stat1 + 1 creatures (Observed: 0x2c4214–0x2c428c) | 5, 1, 0.33299598 (0x3eaa7e73) | 10, 1, 0.099999994 (0x3dcccccc) |
| 4 | mana (Observed: `SkillShock_manaCost` 0x2c3f28) | 1, 19, 3.002884 (0x40402f40) | none |

Uses:

- Both gameplay reads go through **slot 13** (`getStatForHandle`) with the projectile's
  caster handle (+0x194) and **cap 10**: a caster that is a player object uses slot 10 (tier
  1, cap ignored); any other caster, **and an empty handle** (caster already destroyed,
  0x3c8864), uses slot 11 (tier 2) with level = min(level, 10).
- Stat 1 is read once, in the constructor (0x2c4278). Stat 0 is read at the moment of impact
  (0x2c4774), so a player's bolt whose caster object has disappeared in flight deals tier-2
  damage.
- The rank description (0x2c3df8) shows `getStatRange(0.2, stat 0, rank, 0)`, that is
  round(0.8 D)..round(1.2 D). The real roll is D..D + 20 % (see Behaviour); the description
  and the mechanics disagree (Observed).

Worked values (float32 arithmetic, round half away from zero):

| Rank / level | 1 | 5 | 10 | 20 |
|---|---|---|---|---|
| Tier 1 stat 0 | 77 | 113 | 158 | 248 |
| Tier 1 stat 1 (victims = +1) | 0 (1) | 1 (2) | 3 (4) | 6 (7) |
| Tier 1 stat 4 | 19 | 31 | 46 | 76 |
| Tier 2 stat 0 (level capped at 10) | 2 | 10 | 20 | 20 |
| Tier 2 stat 1 (victims) | 0 (1) | 0 (1) | 1 (2) | 1 (2) |

Tier 1 stat 1 by rank 1..20: 0 0 0 0 1 1 2 2 2 3 3 3 4 4 4 5 5 5 6 6.

#### Cost and limits

- Mana: slot 5 = slot 15(rank, 10) = (float) getStat(4, rank) = 19 + 3·(rank − 1): 19, 46,
  76 at ranks 1, 10, 20 (exact for every rank 1..20 with the float step above).
- Recast 30 frames (player+0x4ae, set by `Player_castSkill` after the cast).
- canUse: the base function 0x3c8218, always 1. No weapon or state gate in the skill; the
  common gates of the player cast path apply (`docs/skills.md`, "How a cast happens").
- Monsters and weapon procs pay nothing and have no recast.

#### Behaviour

**Cast** — `SkillShock_cast(skill, level, caster, Vec3 *pos, s16 facing)` 0x2c3d68:
allocate 0x198 bytes and call `ShockProjectile_ctor(obj, &pos, facing, caster, skill,
level)` (0x2c3fe4). Returns 0. For a player the position is the hand midpoint computed by
`Player_castSkill` and the facing is its aim-assisted facing.

**Constructor** 0x2c3fe4, in execution order:

1. `GameObject_ctor(obj, pos, 0, 0)` — one shared draw.
2. Two handle lists zeroed (+0x50, +0x54), virtual table set, a light node initialised at
   +0x14c (radius 156.0, position = pos) and linked.
3. A sound is started on the caster.
4. +0x38 facing = argument; flags |= 0x1 (not solid); +0x4c = skill; +0x58 = `g_simFrame`
   (birth frame); +0x188 = level (s8); +0x1c radius = 12.0; caster handle linked at +0x194
   when the caster is non-null; +0x189 state = 0; +0x190 speed = 341.0 (0x43aa8000).
5. Step per frame: c = cos16(facing), s = sin16(facing) (0x166630, 0x1666e0);
   n = 1/sqrt(c·c + s·s); `step.x = (c·n) · (341.0f · 0.016666666f)`,
   `step.y = (s·n) · (341.0f · 0.016666666f)`, step.z = 0 (0x2c41f8–0x2c427c; note the
   product speed × 1/60 is formed first). 341 × 0.016666666 = 5.6833329 units per frame =
   341 units per second. Stored at +0x120, +0x124, +0x128.
6. +0x18a = (s8)(slot13(stat 1, level, &obj+0x194, 10) + 1) — the maximum number of victims.
7. `obj_runEveryFrame(obj)`; a second sound is started on the projectile.

**Run** 0x2c42e4, once per frame:

```
remaining = birth(+0x58) + 300 - g_simFrame          # computed first, used at the end
pos.x += step.x; pos.y += step.y                      # height is never changed
obj_updateGridCell(obj)
if state == 0:                                        # flying
    if speed != 0 and pos.z < terrain_height(6.0, g_world, pos):     (0x2c43c4)
        state = 2; speed = 0; step = 0; birth = g_simFrame - 270; play the impact sound
    else if (g_simFrame & 7) == 0:                    # global frame, every 8th   (0x2c4430)
        hitTest()                                     # below; may set state = 1
    update the light (presentation)
if state == 1: create or refresh the chain beams (presentation)
emit 42 particle groups (own generator, see Random draws)
if remaining <= 0: destroy self (slot 1 with argument 3)             (0x2c4e04)
```

Lifetime: a bolt that hits nothing is destroyed at the end of its run on frame birth + 300
(5 s; 300 × 5.6833 ≈ 1705 units of travel). After a terrain hit or a strike at frame F the
birth is rewritten to F − 270, so the object runs 30 more frames (F+1 … F+30), standing
still, and is destroyed at the end of frame F + 30. `remaining` is evaluated before the
rewrite, so a strike on the bolt's last frame still deals its damage and the object is
destroyed in that same call.

**hitTest** (0x2c4440–0x2c48f0). Only while flying, only on frames with
`(g_simFrame & 7) == 0`; between two tests the bolt travels 8 × 5.6833 ≈ 45.5 units.

1. `world_collectObjectsInBox(pos − 18, pos + 18, list, 0x200)` on all three axes (at most
   511 objects).
2. Walk the list in query order; the **first** object o that passes both tests is the target T:
   - filter: if the caster handle is non-empty, `caster.slot20(o) != 0` (is my enemy); if it
     is empty, o has flag 0x20 (creature), `(o.flags & 0xd) == 0` and o is not the bolt;
   - distance: `sqrt(dx² + dy²) < o.radius + 18.0` (2-D, strict; 0x2c4560).
   No target: nothing else happens this frame.
3. Candidates: `world_collectObjectsInBox(T.pos − 1200, T.pos + 1200, list, 0x200)` (all
   three axes, 511 objects). Every object that passes the enemy filter of step 2 (the
   distance test is not repeated) is linked into the candidate list +0x50 with `handle_link` (which pushes at the head); in the
   empty-handle variant T itself is skipped here. Then T is linked (0x2c46d4), so T is the
   head of the candidate list (with a live caster T is in the list twice; harmless).
4. +0x18b (victim count) = 0; +0x18c = 44521.0 (0x472de900 = 211²);
   `ShockProjectile_buildChain(obj, &T.pos)` (0x2c4fa8, below).
5. Descriptor: D = slot13(stat 0, level, &obj+0x194, 10) (int). **One shared draw** r
   (0x2c4798–0x2c47d0). `extra = trunc(((float)D · 0.19999999f) · ((float)r · 1.5258789e-05f))`
   (0x3e4ccccc, 0x37800000; truncation toward zero). Entry 0 = {type 0x18, v1 = D,
   v2 = D + extra, v3 = 0} (s16 each). extra is 0..15 at D = 77, 0..49 at D = 248, 0..3 at
   D = 20.
6. For every node of the chain list +0x54 from its head (that is, in **reverse** order of
   chaining — the last creature added is struck first and T last), if the object is still
   there: `damage_apply(0.0, 0.0, victim, attacker, 100000, 0, 0, 0x40, desc, 0)` with
   attacker = the caster object, or the bolt itself when the caster handle is empty
   (0x2c4854–0x2c4894). The same descriptor serves every victim; each call rolls its own
   amount between v1 and v2 inside `damage_apply` (type 0x18: lightning, reduced by the
   victim's lightning resistance, sets the shock status; flag 0x40: cannot be blocked and
   ignores Spirit Shield).
7. speed = 0, state = 1, step = 0, birth = g_simFrame − 270, beam handles
   +0x12c[0 .. count−1] = −1.

**ShockProjectile_buildChain(obj, Vec3 *from)** 0x2c4fa8 (recursive):

```
if count(+0x18b) == max(+0x18a): return
best = none; bestD2 = 99980000.0f                      (0x4cbeb25c)
for node in candidates(+0x50), from the head:
    c = node.object; skip if gone or c.flags & 8 (dead)
    d2 = (c.x - from.x)^2 + (c.y - from.y)^2           # centre to centre, 2-D
    if d2 < range2(+0x18c = 44521.0) and d2 < bestD2 and not inChain(obj, c):
        bestD2 = d2; best = c                          # strict <: on a tie the earlier node wins
if best == none: return
handle_link(&obj+0x54, best, best)                     # push at the head of the chain list
if max != 0:
    count += 1
    buildChain(obj, &best.pos)                         # continue from the new victim
    buildChain(obj, from)                              # then try again from the same point
```

`inChain` is 0x2c50e4 (linear search of +0x54). The first call starts from T's own
position, so T (distance 0) is always the first victim. The result is a depth-first tree:
from each victim the nearest unchained live candidate within 211 units is taken, then the
next nearest from the same victim once the deeper branch is exhausted, until `max` victims
are chained. The chain range does not include the targets' radii and ignores height (the
candidates only had to be inside the ±1200 box around T).

**ShockProjectile fields** (offsets on the object; GameObject part omitted):

| Offset | Type | Meaning |
|---|---|---|
| +0x38 | s16 | facing given to the cast |
| +0x4c | ptr | the Skill |
| +0x50 | handle list | candidates gathered at impact |
| +0x54 | handle list | chained victims, most recent first |
| +0x58 | s32 | birth frame; rewritten to impact frame − 270 |
| +0x5c | s32 | handle passed to `sound_setVolume` every frame; the class never stores to it (Observed: the only access in 0x2c3f5c–0x2c5124 is the load at 0x2c433c), so it is the 0 left by `pool_new`; presentation only |
| +0x60..+0x11f | — | not referenced by the functions read (Unknown; zero) |
| +0x120 | float[3] | per-frame step (z is 0 and never applied) |
| +0x12c | s32[8] | beam handles, −1 = not created yet |
| +0x14c | light node, 0x30 bytes | colours at +0x156..+0x165, radius +0x168/+0x170, inverse square +0x16c/+0x174, position +0x17c |
| +0x188 | s8 | level |
| +0x189 | s8 | state: 0 flying, 1 struck, 2 stopped by terrain |
| +0x18a | s8 | maximum victims = stat 1 + 1 |
| +0x18b | s8 | victims chained |
| +0x18c | float | chain range squared, 44521.0, written at impact |
| +0x190 | float | speed in units per second, 341.0; 0 after impact |
| +0x194 | handle | caster |

#### Random draws

In execution order.

1. Cast: 1 shared draw (the `GameObject` constructor; seeds the bolt's own generator).
2. Every run of the bolt, in every state (0x2c4b20–0x2c4dfc), own generator only: 42 times
   { one unit-ball sample (emission offset, scaled to length 17); one unit-ball sample
   (particle velocity); one draw whose low 5 bits decide a second particle (1 in 32) }. The
   number of own draws per frame is therefore variable (7 minimum per group). Nothing in
   this class uses the own generator for a gameplay decision.
3. At a strike: 1 shared draw for the damage spread (step 5), then the draws of
   `damage_apply` for each chained victim in list order (per `docs/gameplay.md` section 2.5:
   no base roll because min = max = 0; first hit roll; the always-drawn proc rolls; one draw
   for the 0x18 amount; second hit roll; and whatever the victim's shields and the attacker's
   skills add).

#### Presentation only

Two cast sounds (on the caster and on the bolt), one impact sound on terrain; a dynamic
light that flickers with `sin16(g_simFrame · 6000)` and fades over the last 30 frames; up to
8 beams between consecutive chain victims (`beam_create` / `beam_update`, 36 units above
each victim's origin); 42 particle groups per frame; the draw function 0x2c4e64 queues one
glow sprite whose size and alpha scale with min(1, remaining/30). `sound_setVolume(1.0, …)`
is called every frame with the never-written field +0x5c, i.e. with handle 0.

#### Per-machine state

None found in the gameplay path. The functions read no camera, pad, local-slot or option
state; the hit test and the chain use only object positions, flags and the caster's slot 20.
`beam_create` and the glow are draw-side. The prediction copy cannot cast (skill flag bit 0
is clear, `Player_castSkill` 0x1a4320–0x1a433c) and is never returned by the box queries. With an
empty caster handle the bolt hits **any** creature with `(flags & 0xd) == 0`, players
included, and credits itself as attacker; that path is deterministic but changes who is hit.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2c3c68 | SkillShock_ctor | Skill constructor (recast 30, name, virtual table) |
| 0x2c3cd4 | SkillShock_initStats | statistic tables |
| 0x2c3d68 | SkillShock_cast | allocates and constructs the bolt, returns 0 |
| 0x2c3df8 | SkillShock_describeRank | rank text arguments: range of stat 0 at ±20 %, stat 1 + 1 |
| 0x2c3f28 | SkillShock_manaCost | slot 15 with (rank, 10) |
| 0x2c3f5c | ShockProjectile_dtor | clears the three handles and the light, base destructor |
| 0x2c3fe4 | ShockProjectile_ctor | above |
| 0x2c42e4 | ShockProjectile_run | above |
| 0x2c4e64 | ShockProjectile_draw | glow sprite |
| 0x2c4fa8 | ShockProjectile_buildChain (proposed) | recursive chain builder; called from run 0x2c46f4 and from itself |
| 0x2c50e4 | ShockProjectile_isInChain (proposed) | membership test on +0x54; called from 0x2c505c |
| 0x3c8864 | Skill slot 13 | caster-handle statistic selector (null handle → tier 2) |
| 0x119328, 0x1b5ea8 | Creature_isEnemy, Player_isEnemy | the slot 20 filters |

#### Not determined

- Whether the bolt's first run happens on the cast frame or the next (Inferred: next, see
  the conventions of the shared section).
- Fields +0x60..+0x11f of the object (0xc0 bytes that no function read touches), and what
  `sound_setVolume` does when handed handle 0 every frame.
- The four monster call sites were read only as far as the cast arguments; when each
  monster decides to cast was not read.
- The inner draws of `damage_apply` for a type 0x18 entry were taken from
  `docs/gameplay.md`, not re-read.

### 38 groundpound — SkillGroundPound

#### Identity

| Item | Value | Evidence |
|---|---|---|
| Skill id | 38 (`g_skillTable[38]` at 0x41b208 → object 0x6e23e0) | Observed |
| Internal name | groundpound | Observed: constructor 0x2c7014 |
| Skill class | `SkillGroundPound`, virtual table 0x518298 | Observed |
| Kind / flags / recast | 0 / 0 / 30 frames | Observed: 0x2c7014 |
| Effect class | `GroundPoundEffect`, a GameObject of 0x9c bytes, virtual table 0x512218 (slot 1 destructor 0x3c2870, slot 4 run 0x2c7808, slot 15 clone 0x12e4a8; every other slot is the GameObject default). Constructor 0x2c74ac | Observed |
| What the cast returns | nothing (0). The cast only starts an animation and puts a player in action state 10; the effect object is created later by `Player_run` | Observed: 0x2c71ec |
| Who has it | barbarian tree (base level 15, passive mask 0x40). Monsters Cazic and Zek build the effect object themselves | Tree table; 0x24b0dc, 0x2c2e34 |
| Slot overrides | 1 canUse 0x2c7140, 2 cast 0x2c71ec, 4 describeRank 0x2c72ec, 5 manaCost 0x2c7478, 7 icon 0x3cce78, 9 initStats 0x2c7080 | `vtab.py show 518298` |

#### Statistics

`SkillGroundPound_initStats` 0x2c7080 (**Observed**).

| Stat | Meaning | Tier 1: first, base, step | Tier 2: first, base, step |
|---|---|---|---|
| 0 | damage centre value; the hit rolls between 80 % and 120 % of it — Observed: 0x2c7f18–0x2c8074 | 1, 70, 9.99986172 (0x411fff6f) | 1, 20, 5.0 (0x40a00000) |
| 1 | radius in 12-unit steps — Observed: 0x2c7848–0x2c78c0 | 1, 6, 0.99998099 (0x3f7ffec1) | 1, 12, 12.0 (0x41400000) |
| 2 | stun chance in percent — Observed: 0x2c80a4–0x2c80e8 | 10, 10, 2.99998188 (0x403fffb4) | none |
| 3 | stun length in seconds — Observed: 0x2c80f0–0x2c8134 | 10, 2, 0.25 (0x3e800000) | none |
| 4 | mana — Observed: 0x2c7478 | 1, 28, 2.99996495 (0x403fff6d) | none |

Which lookup each use makes:

- radius: no owner → slot 10 `getStat(1, level)`; with an owner → slot 12
  `getStatFor(1, level, owner, cap 10)`: a player owner gets tier 1, any other owner tier 2
  with the level limited to 10;
- damage: no owner → slot 10; with an owner → slot 12 `getStatFor(0, level, owner, cap 0)`
  (tier 2 for non-players, level not limited);
- stun chance and length: always slot 10 (tier 1), whoever the owner is;
- mana: slot 15 `manaFromStat4(level, 4)`.

| Rank | s0 → damage roll range | s1 → radius | s2 stun % | s3 stun | s4 mana |
|---|---|---|---|---|---|
| 1 | 70 → 56…84 | 6 → 72 units | 0 | 0 | 28 |
| 10 | 160 → 128…192 | 15 → 180 | 10 | 2 s (120 frames) | 55 |
| 20 | 260 → 208…312 | 25 → 300 | 40 | 5 s (300 frames) | 85 |

s0 rises by exactly 10 per rank, s1 by 1, s4 by 3; s2 from rank 10: 10, 13, 16, … 40; s3 from
rank 10: 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5.

Tier 2 (monster owner, level L): damage centre 20 + 5 (L − 1) → range round(0.8 d)…round(1.2 d)
(for example L 1: 16…24, L 10: 52…78); radius (12 + 12 (min(L, 10) − 1)) × 12 = 144 × min(L, 10)
units.

The rank text (0x2c72ec) calls slot 8 `getStatRange(0.2, stat 0, level, randomise 0, …)` for
the two damage figures and prints s1, and s2 with s3 when s2 is non-zero.

#### Cost and limits

- Mana: getStat(4, level): 28, 55, 85 at ranks 1, 10, 20. Recast 30 frames.
- `SkillGroundPound_canUse` 0x2c7140 (skill, caster): 1 for a non-player. For a player it
  needs the weapon animation class (record +0x4a86) to be 2, and, when the active weapon set
  has a weapon (record +0x4434 indexed by +0x4a7c), that weapon's damage class word (item
  definition +0x20) to be exactly 1. Otherwise it returns 0 and posts a HUD notice for the
  slot (180 frames). In the words of the other documents: a two-handed weapon of animation
  class 2 whose damage class is 1 (blunt, **Inferred** name).
- General player gates as for any kind-0 skill (see id 35).
- Action state 10 is one of the two states `Player_processDamage` does not replace with a
  stagger (0x1b2cc0), so the animation cannot be interrupted by a hit.

#### Behaviour

##### Cast — `SkillGroundPound_cast` 0x2c71ec (skill, level, caster, pos*, facing)

Only when the caster has flag 0x40 (**Observed**):

1. caster+0x58c = 10. (+0x448 is not written.)
2. clip = `res_find(first word of the table at caster+0x24, "dha_quake.anm")`.
3. The clip's four event slots are **written into the loaded animation**:

   | Slot | Time (s) | Mask |
   |---|---|---|
   | 0 | 0.25 (0x3e800000) | 1 |
   | 1 | 0.5 (0x3f000000) | 2 |
   | 2 | 0.75 (0x3f400000) | 4 |
   | 3 | 1.4779719 (0x3fbd2e2f) | 8 |

4. `anim_startBlendInOut(0.1, 0.1, caster animation state, clip, flags 0x0a)`.
5. Sound on the caster (`spel_bw_pound.anm` from `fx.lmp`).

Returns 0 in every case: there is no Spell, so nothing is attached, and the level argument
is not kept (the rank is looked up again when the effect is made). For a non-player caster
the function does nothing at all.

##### `Player_run` action state 10 (0x1a6818)

Every frame, starting the frame after the cast (the first animation step of the new clip is
made here):

```
ev = Player_animStep(1.0, player)
if ev & 1:
    player_voice(slot, 10)
    sound "spel_bw_pound.anm" on the player object of the record
if player is the prediction copy:  stop here
if ev & 7:
    off = -0x4000 if (ev & 1) else 0 if (ev & 2) else 0x4000      # left, ahead, right
    p = (x + cos16(facing + off) * 24.0,  y + sin16(facing + off) * 24.0,  height + 60.0)
    world_damageInRadius(inner 0.0, outer 48.0, attacker = player, &p,
                         maxDamage 1, flags 0x40000, minDamage 1, skipFlags 0)
if ev & 8:
    e = pool_new(0x9c)
    if e:  GroundPoundEffect_ctor(e, &player.pos, player.facing, g_skillTable[38],
                                   player_getSkillRank(slot, 38), player)
if (animation status +0x11a & 8) == 0:                    # the clip is gone
    state = 2;  top track life = 1.0, life rate = -0.083333 (0xbdaaaaaa);  +0x448 = g_simFrame
```

- `world_damageInRadius` with these arguments gives every object the player's slot 20 accepts,
  whose distance measure (|dx| + |dy| − 0.333 min(|dx|, |dy|) − radius) is below 48 inside a
  box of ±48 on all three axes round p, one call
  `damage_apply(1.0, 1.0, target, player, 100000, 0, 0, 0x40000, 0, 0)` — a one-point hit
  whose flag 0x40000 is the lightest of the four knock bits the take-damage code reads.
- With the cast on frame F0 and animation speed 1.0 the clip's own events fall on: bit 1 at
  F0+16 (shove to the left, voice, sound), bit 2 at F0+31 (ahead), bit 4 at F0+46 (to the
  right), bit 8 at F0+89 (the effect object). Computed from the event test of `anim_advance`
  (window [t/60, (t + step)/60) with step 0.99999994) for a track that starts at time 0 and
  is first advanced on F0+1. A slow effect or the Drowsy factor scales the step and delays
  all four.
- `ev` is the merged mask of all live tracks. The four persistent base locomotion tracks of
  the player stay alive under the clip; if their clips carry events with bits 1, 2 or 4 they
  produce additional shoves (and, for bit 1, the voice and sound) on their own schedule.
  Animation data, not examined (**Unknown**).
- The state ends when no track with flag 0x8 is left, i.e. at the end of the clip (its life
  reaches 0 exactly at its last tick). The clip length is data; it has to be longer than
  1.478 s for the effect to appear.
- The same state and the same clip are used by an older inline ability (ability id 12 with a
  non-Skill record, `Player_run` case 2 near 0x1a7424, **Observed**); that path does not write the
  event slots and relies on whatever the clip holds.

##### `GroundPoundEffect_ctor` 0x2c74ac (effect, pos*, facing, skill, level, owner)

1. `GameObject_ctor(effect, pos, 0, 0)` — one shared draw for the object's own generator.
2. Fields:

| Offset | Type | Initial value | Meaning |
|---|---|---|---|
| +0x10 | float[3] | see step 5 | centre of the pound |
| +0x1c | float | 0 | object radius |
| +0x38 | s16 | facing | |
| +0x44 | u32 | from the shared draw | own generator (`GameObject_rand`): dust ring, then stun rolls |
| +0x48 | ptr | 0x512218 | virtual table |
| +0x4c | s8 | 0 | run counter |
| +0x4d | s8 | level | |
| +0x4f | u8 | `water_test(8.0, world, centre)` | 1 = over water |
| +0x50 | u8 | see step 5 | 1 = the ground under the centre is 144 or more away in height |
| +0x54 | float | 108.0 | light radius, −3.8957684 (0x40795445) per run, floor 0 |
| +0x58 | Skill* | skill | |
| +0x5c … +0x97 | light node | colours (0xc1, 0x75, 0x39, −32) at +0x66 and +0x6e; radius 108.0 at +0x78 and +0x80; 1/108² (0x38b3cc07) at +0x7c and +0x84; position +0x8c | presentation |
| +0x98 | handle | owner (empty when the owner argument is 0) | attacker of the hits; chooses the statistic tier |

3. Impact sound on the owner (`hit_chnmail_bludg_hvy.anm`); owner handle linked when non-zero.
4. `obj_runEveryFrame(effect)`.
5. centre.x = pos.x + cos16(facing) × 30.0, centre.y = pos.y + sin16(facing) × 30.0;
   h = `terrain_height(6.0, world, centre)`; +0x50 = (|h − pos.height| ≥ 144.0, compared in
   double precision); centre.height = h.
6. +0x4f = water test. Over water: +0x50 = 0 and the light is unlinked. Not over water and
   +0x50 set: the light is unlinked. Otherwise the light stays, placed 36 above the centre.

##### `GroundPoundEffect_run` 0x2c7808

Run counter c = +0x4c.

On the first run (c == 0), in this order:

1. s1 lookup as described under Statistics; R = (float)(s1 × 12); if +0x50 is set R = 24.0.
2. Dust ring: for a = 0, 400, …, 65200 (164 steps) three `GameObject_rand` draws each
   (presentation; 492 draws of the object's generator).
3. A `LightEffect` (0xbc bytes) is created 24 units ahead of the centre: start and end colour
   (193, 117, 57, −32), no owner. Being a GameObject, its constructor draws the shared
   generator once.
4. 60 particles, one draw of generator 0x404468 each (type chosen by R: below 152, below 232,
   else).
5. If +0x50 is clear: 23 particles (46 over water), three draws of 0x404468 each.
6. Not over water and +0x50 clear: one draw of 0x404468 for the angle of a floor decal
   (`decal_add(12.0, centre, angle, 9, 0)`), then `camera_shake(level × 0.715 (0x3f3709c7) +
   5.0, 0)`. Over water: `water_disturb(3573.0, 36.0, world, centre)` and the same shake.
7. Damage. `world_collectObjectsInBox(centre − (R,R,R), centre + (R,R,R), list, 512)`. For
   each object o in list order, **only when the owner handle is not empty**:
   - skip unless `owner->isEnemy(o)` (Creature slot 20 of the owner) is non-zero;
   - skip unless sqrt((centre.x − o.x)² + (centre.y − o.y)²) < R + o.radius;
   - d = s0 lookup (see Statistics); lo = max(1, round(d − d × 0.19999999)),
     hi = max(1, round(d + d × 0.19999999)), rounding half away from zero;
   - `damage_apply(min = (float)lo, max = (float)hi, victim = o, attacker = owner, attack
     rating 100000, 0, 0, flags 0x80100, descriptor 0, noCrit 0)`; no descriptor entries;
   - if o is a creature and its hit points (+0x228) are ≥ 0: r = `GameObject_rand(effect)`;
     if (r % 100) + 1 > 100 − getStat(2, level): `o->stun(getStat(3, level) × 60, 1)`
     (Creature slot 30). The draw is made even when the chance is 0.

   An effect without an owner damages nothing.

On every run, the first included: one spark while c < 4 (not over water, +0x50 clear; three
or more draws of 0x404468), or over water two draws of 0x404468 and a small ripple; the light
radius follows +0x54; c += 1. On the run where c is 30 the object deletes itself
(`obj_delete`); it therefore runs 31 times and does damage only on the first.

Flags 0x80100 = 0x100 (the floating number is coloured as lightning-typed) | 0x80000 (passed
through to take-damage). The hit can be blocked (0x40 is not set) and goes through the usual
hit and critical rolls of `docs/gameplay.md` §2.5 with attack rating 100000.

##### Monster callers

| Caller | When | Arguments |
|---|---|---|
| Cazic run, 0x24b0dc | animation event bit 1 of its pound state | pos = own position + 60 × (cos16, sin16)(facing), own facing, `g_skillTable[38]`, level = Creature slot 35 of Cazic ((int)(`g_levelMonsterLevel` × 0.3)), owner = Cazic |
| Zek run, 0x2c2e34 | animation event bit 1 of its state 0xd | pos = own position + 84 × (cos16, sin16)(facing), own facing, `g_skillTable[38]`, level = slot 35, owner = Zek; afterwards Zek+0x478 = its clock + 600 |

Both therefore get the tier 2 damage and radius, and tier 1 stun figures at their slot-35
level (no stun below level 10). The constructor adds its own 30 units, so the centre is 90
(Cazic) or 114 (Zek) units ahead of the monster.

#### Random draws

Shared generator:

1. `GroundPoundEffect_ctor`: one draw (GameObject seed).
2. First run: one draw when the `LightEffect` is constructed (before any damage call).
3. First run: the `damage_apply` sequence for each object hit, in box-query order.
4. Each shove of state 10: the `damage_apply` sequence for each object within reach (min ==
   max there, so no base roll).

Object generator of the effect (`GameObject_rand`, state at +0x44), first run only:

1. 492 draws for the dust ring;
2. then one draw per creature hit whose hit points are not negative (the stun roll), in the
   same order as the damage calls, interleaved with them.

Generator 0x404468 (not synchronised): particles, decal angle and ripple positions only.

#### Presentation only

Dust ring, three sizes of ground burst, sparks or splashes, the fading orange light and the
extra `LightEffect`, floor decal (subject to the local decal option), water ripples,
`camera_shake`, the three sounds, voice line 10. Particle definitions 0x8e4d80–0x8e4f60 are
registered by the static initialiser 0x2c843c.

#### Per-machine state

- Generator 0x404468 feeds only particles, the decal and ripple positions here (**Observed**
  for every use in 0x2c7808). The ripples go into the water grid through `water_disturb`,
  which was not checked for gameplay readers.
- `decal_add` depends on a local option; `camera_shake` and `player_voice` are local.
- `Player_run` state 10: the shoves, the effect creation and the exit to state 2 are all
  inside the not-the-copy branch (test at 0x1a6884–0x1a6890). The prediction copy therefore
  never leaves state 10 on its own; it only plays the animation and the bit-1 sound.
- The cast writes the event slots of a shared animation clip, with constants; flag bit 0 is
  clear, so the prediction copy never runs the cast. Not a hazard.
- canUse and cast both test flag 0x40 before using +0x3c8 or +0x58c. `GroundPoundEffect_run`
  uses no player field; it reaches the owner only through virtual slot 20 and slot 12.
  **Observed.**
- `GroundPoundEffect_run` reads the owner pointer from the handle without a null test once
  the handle itself is non-empty (0x2c7ea0); an owner destroyed between construction and the
  first run would leave a null pointer there (**Inferred**; both happen within a frame or
  two).
- The `LightEffect` and its shared draw are skipped if the pool allocation fails.
- Weapon-effect cast with id 38: harmless for a non-player attacker (the cast does nothing);
  a player attacker is put in state 10 with the clip, exactly as by a normal cast.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2c7014 | `SkillGroundPound_ctor` | |
| 0x2c7080 | `SkillGroundPound_initStats` | tier 1 and tier 2 constants |
| 0x2c7140 | `SkillGroundPound_canUse` | weapon test with notice |
| 0x2c71ec | `SkillGroundPound_cast` | state 10, event slots, clip |
| 0x2c72ec | `SkillGroundPound_describeRank` | |
| 0x2c7478 | `SkillGroundPound_manaCost` | slot 15 with (level, 4) |
| 0x2c74ac | `GroundPoundEffect_ctor` | |
| 0x2c7808 | `GroundPoundEffect_run` | |
| 0x3c2870 | `GroundPoundEffect_dtor` | owner handle, light, GameObject base |
| 0x1a5030 | `Player_run` | case 10 at 0x1a6818 |
| 0x24b014 (inside Cazic run 0x24aaf0) | — | Cazic's construction site |
| 0x2c2d68 (inside Zek run 0x2c2440) | — | Zek's construction site |
| 0x3c8690, 0x3c87f0 | Skill slots 11 and 12 | tier 2 lookup and the player test |
| 0x16d748 | `anim_advance` | event window |

#### Not determined

- Length of "dha_quake.anm" and the event masks of the base locomotion clips (data).
- `world_damageInRadius` was taken from the summary in §1.6, not re-read.
- What the take-damage implementations do with flag bits 0x40000, 0x80000 and 0x100.
- Whether a new object gets its first run in the frame it is created or the next
  (object-list order; decides whether the damage lands on F0+89 or F0+90).
- `LightEffect` beyond its constructor's shared draw; `water_disturb`'s readers.

### 39 convertenemy — SkillConvertEnemy

#### Identity

| Item | Value | Evidence |
|---|---|---|
| id, name | 39, `convertenemy` | `SkillConvertEnemy_ctor` 0x2cfe34 |
| Skill class / virtual table / object | `SkillConvertEnemy`, 0x518928, object 0x6e2448 | Observed |
| kind, flags | 0 (active), 0 (copy may not cast) | Observed 0x2cfe34 |
| recast (+0x0c) | 600 frames (set to 30 by the inlined base constructor, then overwritten) | Observed 0x2cfe34 |
| overridden Skill slots | 1 canUse 0x2cffb8, 2 cast 0x2cff1c, 4 describeRank 0x2d001c, 5 manaCost 0x2d0120, 7 icon 0x3cd794, 9 initStats 0x2cfeac | table 0x518928 |
| effect class | `SpellConvertEnemy`, 0x78 bytes, virtual table 0x5189b0 (slot 1 dtor 0x3cd680, slot 2 run 0x2d0354, slots 3, 4 base); attached to the **caster** | Observed |
| other objects | `FlyingText` (GameObject, 0x98 bytes) for the immunity and resistance notices | Observed 0x2d04c8, 0x2d064c |
| who has it | cleric tree (base level 15, needs skill 20). No monster caller found | tree table |
| active / passive | active, instant; effect resolves 33 frames later | |

#### Statistics

Observed in `SkillConvertEnemy_initStats` 0x2cfeac. Tier 1 only; every lookup in the class is
slot 10 (`getStat`), so the caster's kind makes no difference and no cap is applied.

| Stat | Meaning | first, base, step |
|---|---|---|
| 0 | maximum number of creatures picked at the cast (Observed: constructor loop bound, 0x2d0204, 0x2d031c) | 1, 1, 0.199999988 (0x3e4ccccc) |
| 1 | charm duration in seconds (×60 → charm timer; also the glow seconds) (Observed: run 0x2d03c4–0x2d03f8, 0x2d0608–0x2d0638) | 1, 15, 1.0 (0x3f800000) |
| 2 | success threshold of the 1…100 roll, halved for large creatures (Observed: run 0x2d048c, 0x2d0530–0x2d05d4) | 1, 40, 1.99998689 (0x3fffff92) |
| 3 | not set | — |
| 4 | mana | 1, 97, 6.99981499 (0x40dffe7c) |

Values, ranks 1–20:

- stat 0: 1 1 1 2 2 2 2 2 3 3 3 3 3 4 4 4 4 4 5 5
- stat 1: 15 + (rank − 1) → 15, 24, 34 at ranks 1, 10, 20 (900, 1440, 2040 frames)
- stat 2: 40 + 2 × (rank − 1) → 40, 58, 78
- stat 4: 97 + 7 × (rank − 1) → 97, 160, 230

| Rank | targets | seconds | threshold | chance, radius ≤ 20 | chance, radius > 20 |
|---|---|---|---|---|---|
| 1 | 1 | 15 | 40 | 39 % | 19 % (threshold 20) |
| 10 | 3 | 24 | 58 | 57 % | 28 % (threshold 29) |
| 20 | 5 | 34 | 78 | 77 % | 38 % (threshold 39) |

#### Cost and limits

- Mana: `manaCost(level)` 0x2d0120 = slot 15 (level, 4) = (float) getStat(4, level). Observed.
- Recast 600 frames.
- canUse (`SkillConvertEnemy_canUse` 0x2cffb8): refused only when `g_pvpModeA` ≠ 0 and the
  caster is a player (HUD notice, 90 frames, to slot caster+0x3c8, read behind the player
  test). Otherwise allowed, with or without a target. Observed.
- Not castable by the prediction copy.
- Mana and recast are spent even when nothing is picked or every roll fails.

#### Behaviour

**Cast** (`SkillConvertEnemy_cast` 0x2cff1c): allocate 0x78 bytes; `SpellConvertEnemy_ctor(
spell, level, caster, skill)`; return the spell (null if the allocation failed). No
adjustLevel call. The position and facing arguments are **not used**: the constructor reads
the caster's own position and facing. `Player_castSkill` then attaches the spell to the
player. Observed.

**Constructor** (`SpellConvertEnemy_ctor` 0x2d0154), in order (Observed):

1. +0x00 level, +0x08 skill, +0x04 = 0, +0x0c owner = caster.
2. One shared draw → +0x10. Virtual table 0x5189b0. +0x18 = 0 (empty target list).
3. +0x1c = `g_simFrame` (written, never read again in this class).
4. n = getStat(0, level).
5. +0x70 = 0 (u16 angle), +0x74 = 0.0 (ramp).
6. Sound on the owner (presentation).
7. `world_collectObjectsInArc(radius 333.0 (0x43a68000), arc 139.0 degrees (0x430b0000),
   halfWidth 0, pos = owner+0x10, facing16 = owner+0x38, list, filterObj = null)`.
8. If the list is not empty and n > 0, walk it from the head (nearest first, then the
   query's partial order). An object T is **accepted** when all hold:
   - T object flags & 0x1000000 == 0 (not "friendly to players");
   - T object flags & 0x40 == 0 (not a player);
   - T+0x312 == 0 (not charmed already);
   - `creature_bossRank(T)` == 0;
   - T+0x354 (glow seconds, float) ≤ 0.0.
   There is **no enemy test**: any creature passing these is accepted, whatever its team.
   For each accepted T: count += 1; `handle_link(spell+0x18, T, T)`;
   `particleGroup_create()` → next slot of the handle array at +0x20. Stop at the end of the
   list or when count == n.
   `handle_link` inserts at the **head**, so the target list ends up in reverse order of
   acceptance (Observed 0x1a1738).
9. Free the query list.

`SpellConvertEnemy` layout (0x78 bytes):

| Offset | Type | Meaning |
|---|---|---|
| +0x00 | s8 | level |
| +0x04 | handle back-list | link into the caster's spell list |
| +0x08 | Skill* | |
| +0x0c | Creature* | owner = caster |
| +0x10 | u32 | private generator (never drawn from) |
| +0x14 | ptr | virtual table 0x5189b0 |
| +0x18 | handle list head | targets, newest first; a node's object pointer becomes null when that creature is destroyed |
| +0x1c | s32 | frame of the cast (unused) |
| +0x20 | handle[20] | particle groups, one per accepted target in acceptance order (no bound check; 5 used at rank 20) |
| +0x70 | u16 | spiral angle |
| +0x74 | float | ramp, 0 → just over 4 |

**Run** (`SpellConvertEnemy_run` 0x2d0354), once per frame from the caster's spell update
(`Player_updateCast` for a player: only while the caster is alive). Arguments ignored.
Observed:

```
d      = getStat(1, level)                    -- seconds
frames = d * 60                               -- integer, then converted to float F
angle  = (u16)(angle + 0x172d)
ramp   = ramp + 0.121898249                   (0x3df9a5ca)
final  = (ramp > 4.0)                         -- first true on the 33rd call (ramp 4.02264118)
thr    = final ? getStat(2, level) : 0
for each node of the target list, from the head:
    T = node.object;  if T is null: continue   (the particle-handle index does not advance)
    if not final:
        one spiral particle on T (presentation); advance particle-handle index
    else if T+0xb4 (creature kind) == 0x10:                 -- undead: immune
        create FlyingText at T's position (immunity notice)  -- a GameObject: one shared draw
    else:
        big  = (T+0x1c radius > 20.0)
        thr2 = big ? roundHalfAway((float)thr * 0.5) : thr
        r    = (shared draw) % 100 + 1                       -- unsigned modulo
        if r < thr2:                                         -- converted
            team = owner is a player ? (s8) record[owner+0x3c8]+0x4c24 : -1
            T creature flags (+0xa8, 64-bit) |= 0x400000
            T+0x354 = F * 0.0166666657                       (0x3c888888; glow seconds)
            Creature_setCharm(T, frames, team)
        else if big:
            create FlyingText at T's position (resistance notice)  -- one shared draw
if final: destroy the spell (slot 1, argument 3)
```

`roundHalfAway(x)` is trunc(x + 0.5) for x ≥ 0 and trunc(x − 0.5) otherwise. A failed roll on
a creature of radius ≤ 20 shows nothing. Both FlyingText allocations are skipped silently
(with their shared draw) if the pool allocation fails. The spell lasts exactly 33 calls: 32
frames of spiral particles, then the resolving call. The destructor 0x3cd680 clears the
target list and unlinks the spell.

**`Creature_setCharm(T, frames, team)`** 0x1189f0 (Observed): does nothing when T+0x312 == −1
(permanent charm), when T lacks the creature flag, or when T is a player. Otherwise T+0x310
(s8 team) = team, T+0x312 (s16 charm timer) = frames, and T's target handle (+0x234) is
cleared. Note the two writes made by the spell before the call (flag 0x400000 and the glow
timer) happen even when setCharm then declines.

**What a converted creature does** (all in the creature base class; Observed at the
addresses given):

- *Team.* Slot 37 returns +0x310. `Creature_isEnemy` 0x119328 and `Creature_isAlly`
  0x119400 compare the two slot-37 values, so the creature now treats everything on another
  team — the ordinary monsters, whose team is 0xff — as enemies, and they treat it as one.
  `Creature_pickTarget` 0x10ded0 has no charm-specific code; it just uses slot 20.
- *Players cannot attack it.* `Player_isEnemy` 0x1b5ea8 is false for any creature with a
  non-zero charm timer outside PvP mode A (in which the skill cannot be cast by a player),
  and `Player_findTarget` 0x1bb3c8 skips such creatures.
- *Which players it spares.* The team given is the caster's record byte +0x4c24. That byte
  is 0 for every player in an offline non-PvP game (import screen, 0x22067c) but is the
  **slot number** for every player of a net game (`net_launchUpdate`, 0x1373d8). So offline
  the creature is on the team of all players; in a net game it is on the caster's team only,
  and `Creature_isEnemy` makes the other players its enemies while they cannot target it
  (Observed pieces; Inferred conclusion — a monster class that overrides slot 20 may
  differ, e.g. `Skeleton_isEnemy` 0x2a7e04 adds its own rule on top of the base test).
- *Following.* Creature flag 0x400000 ("follow a player, stand ahead"). Each `Creature_run`
  while the charm timer is non-zero and flag 0x400000 or 0x800000 is set (0x112da8–0x113134):
  - if T+0x5a (followed slot, −1 at construction) is not a valid slot of a live player:
    T+0x5a = `players_findNearestOnTeam(500.0, T position, T team)` (nearest live player
    within 500, three axes, whose team byte equals T's team, any player when the team is
    −1; 0xff when none);
  - otherwise: T's home (+0x3b4) = that player's position + 30 × (cos, sin) of the player's
    facing (minus for flag 0x800000); if `Creature_isAwayFromHome(T)` (more than 120 from
    home, squared 14400, three axes) the move destination (+0x104) = home;
  - then (in both cases), only if T is **not active** (creature flag bit 63 clear): try 32
    directions around home: base angle = `math_atan2_16(T.y − home.y, T.x − home.x)`, offsets
    +k × 0x800 for even tries and −k × 0x800 for odd tries, k = try / 2 = 0…15; for each,
    cast a terrain ray (`terrain_raycast`, first argument 1.1, last 3) of length 500 (the
    float at 0x40278c) from home raised by 11.0; the first direction whose ray is
    unobstructed and whose end point home + 500 × direction has no player within 450
    (`players_anyWithinRadius`) wins: T is **teleported** to that point, re-inserted in the
    grid, marked active, destination = home, path cleared.
- *Timer.* `Creature_run` 0x112d64–0x112da4: a non-zero timer other than −1 is decremented
  once per call; when it reaches 0: team = 0xff and creature flags &= ~0xc00000. The
  creature is then an ordinary monster again (its current target is not cleared by the
  expiry). Lifetime: frames = 60 × stat 1 `Creature_run` calls.
- *Death at expiry* is a separate creature flag (0x2000000000000, tested at 0x113138 when
  the timer is 0); this spell does **not** set it, so the creature survives the charm.
- *Glow.* +0x354 > 0 makes `Creature_run` tint the creature and subtract 0.0166666657 per
  call (0x113214–0x113270). Starting from F × 0.0166666657 it stays positive for 60 × stat 1
  + 1 calls (simulated in single precision for 15…34 s). Besides the tint, the field is the
  constructor's "recently converted" filter above.

**Stacking / refresh.** A creature with a non-zero charm timer or a positive glow timer is
not accepted by a later cast, so the charm cannot be refreshed; it can be re-converted from
the frame after the glow ends. Between cast and resolution (32 frames) nothing marks the
picked creatures, and the recast is 600 frames, so one caster cannot overlap two casts; two
different casters can pick the same creature, and then the second successful resolution
overwrites team and timer (setCharm only refuses −1).

**End conditions.** The 33rd run call. Earlier destruction of the caster (spell deleted with
it; nothing has been written to the targets yet). A dead player caster freezes the spell
(no run calls) until revived. Targets destroyed before resolution are skipped (null node);
targets that died but still exist are **not** skipped — there is no dead-flag test in run,
so a corpse can receive the roll, the flag, the glow and the charm.

**Non-player caster.** canUse passes. Through the weapon-proc path the spell is constructed
(one shared draw, targets linked, particle groups taken) but never attached, so run never
executes: **no conversion**, and the spell with its target-list nodes is never freed
(Observed discard at 0x1e8fa0; Inferred leak). If a non-player owner's spell were run, the
team passed would be −1 (the +0x3c8 read at 0x2d05f0 is behind the player test): the
creature would keep the monsters' team, be untargetable by players and follow the nearest
player. No caller that does this was found.

**Prediction copy.** Cannot cast; never a target (players are excluded; the box query skips
the copy).

#### Random draws

In execution order:

1. Constructor: one shared draw (private seed).
2. Calls 1–32 of run: none (the spiral uses the stored angle, not a generator).
3. Call 33, per target in list order (reverse of acceptance), skipping destroyed targets:
   - undead target: one shared draw inside `GameObject_ctor` of the FlyingText (plus two
     draws of that object's own generator in `FlyingText_ctor`);
   - other target: one shared draw for the roll; then, only when the roll failed and the
     radius is above 20, one shared draw for the FlyingText (plus its two own draws).

No cosmetic-generator or 0x404468 draw; the spell's private generator is never used.

#### Presentation only

Cast sound; per frame one spiral particle per target (definition 0x8e5460, position
0.5 × (cos, sin)(angle) × target radius, height ramp × radius, velocity 6.84999943 ×
0.5 × (cos, sin)); the immunity and resistance floating texts (their creation is not
presentation as far as the shared generator is concerned); the glow tint; the HUD notice
from canUse. Particle definitions registered by `convertEnemy_staticInit` 0x2d0820. The
particle groups taken in the constructor are not released by the destructor.

#### Per-machine state

- canUse: `hud_showMessage` shows only on the slot's own machine; result unaffected.
- The +0x3c8 reads (canUse 0x2cffb8, run 0x2d05f0) are behind player-flag tests. Observed.
- The team byte differs between offline (0) and net games (slot number): a difference
  between game modes, identical on all machines of one game.
- `players_findNearestOnTeam` and the follow code read player records and their object
  pointers each `Creature_run`; these are simulation state (monster updates do not run in
  prediction). No camera, local-slot, audio or option read. None found.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2cfe34 | SkillConvertEnemy_ctor | recast 600, name |
| 0x2cfeac | SkillConvertEnemy_initStats | table above |
| 0x2cff1c | SkillConvertEnemy_cast | allocate and construct |
| 0x2cffb8 | SkillConvertEnemy_canUse | PvP mode A refusal |
| 0x2d001c | SkillConvertEnemy_describeRank | stats 0, 1, 2 into text |
| 0x2d0120 | SkillConvertEnemy_manaCost | slot 15 (level, 4) |
| 0x2d0154 | SpellConvertEnemy_ctor | target pick |
| 0x2d0354 | SpellConvertEnemy_run | spiral, resolution |
| 0x3cd680 | SpellConvertEnemy_dtor | clears the target list |
| 0x1189f0 | Creature_setCharm | team, timer, drop target |
| 0x112948 (0x112d64–0x113174, 0x113214) | Creature_run | charm countdown, expiry, follow and teleport, death-at-expiry flag, glow |
| 0x119328, 0x119400, 0x10de10 | Creature_isEnemy / isAlly / isSameTeam | how the team is used |
| 0x1b5ea8, 0x1bb3c8 | Player_isEnemy, Player_findTarget | charmed creatures are not player targets |
| 0x10ded0 | Creature_pickTarget | checked for charm-specific code (none) |
| 0x1124e0, 0x10eed8 | players_findNearestOnTeam, Creature_isAwayFromHome | follow helpers |
| 0x135638 (0x1373d8), 0x21fa2c (0x220644–0x22067c) | net_launchUpdate, memcard_importScreen | the writers of the team byte |
| 0x1a1738 | handle_link | head insertion |
| 0x202158 | FlyingText_ctor | confirmed it calls GameObject_ctor |

#### Not determined

- The monster classes' own reactions to being charmed (overrides of slots 20, 23; the tail
  of `Creature_run` at 0x113b5c that moves a touched idle charmed creature to state 1) were
  not read class by class.
- `terrain_raycast` semantics in the teleport step were taken from its use (negative result
  treated as "no hit").
- Whether any game mode writes the team byte other than the three stores found.
- Which item data carry a type-0x29 entry with id 39.

### 40 convertundead — SkillConvertUndead

This is skill 39 with a different target filter, a canUse that needs an undead enemy nearby,
and different constants. The two classes are separate copies of the same source shape;
everything not listed under "Differences from 39" is identical to section 39, including what
a converted creature does afterwards.

#### Identity

| Item | Value | Evidence |
|---|---|---|
| id, name | 40, `convertundead` | `SkillConvertUndead_ctor` 0x2d08d0 |
| Skill class / virtual table / object | `SkillConvertUndead`, 0x5189e0, object 0x6e24b0 | Observed |
| kind, flags | 0 (active), 0 (copy may not cast) | Observed 0x2d08d0 |
| recast | 300 frames | Observed 0x2d08d0 |
| overridden Skill slots | 1 canUse 0x2d0a58, 2 cast 0x2d09bc, 4 describeRank 0x2d0b88, 5 manaCost 0x2d0c8c, 7 icon 0x3cd8cc, 9 initStats 0x2d0948 | table 0x5189e0 |
| effect class | `SpellConvertUndead`, 0x78 bytes, virtual table 0x518a68 (slot 1 dtor 0x3cd7b8, slot 2 run 0x2d0edc, slots 3, 4 base); attached to the caster | Observed |
| other objects | `FlyingText` (0x98 bytes) for the resistance notice | Observed 0x2d1164 |
| who has it | shadowknight tree (base level 20, needs skill 9). No monster caller found | tree table |
| active / passive | active, instant; resolves 31 frames later | |

#### Statistics

Observed in `SkillConvertUndead_initStats` 0x2d0948. Tier 1 only; all lookups are slot 10.

| Stat | Meaning | first, base, step |
|---|---|---|
| 0 | maximum number of creatures picked (constructor 0x2d0cc0) | 1, 1, 0.200000986 (0x3e4ccd0f) |
| 1 | charm duration in seconds (run 0x2d0f4c, 0x2d1120–0x2d1150) | 1, 15, 1.00099599 (0x3f8020a3) |
| 2 | success threshold of the 1…100 roll, halved for radius > 20 (run 0x2d1014, 0x2d1044–0x2d10ec) | 1, 60, 1.00099695 (0x3f8020ab) |
| 3 | not set | — |
| 4 | mana | 1, 104, 4.99984074 (0x409ffeb2) |

Values, ranks 1–20:

- stat 0: 1 1 1 2 2 2 2 2 3 3 3 3 3 4 4 4 4 4 5 5 (same integers as skill 39)
- stat 1: 15 + (rank − 1) → 15, 24, 34 (same integers as skill 39)
- stat 2: 60 + (rank − 1) → 60, 69, 79
- stat 4: 104 + 5 × (rank − 1) → 104, 149, 199

| Rank | targets | seconds | threshold | chance, radius ≤ 20 | chance, radius > 20 |
|---|---|---|---|---|---|
| 1 | 1 | 15 | 60 | 59 % | 29 % (threshold 30) |
| 10 | 3 | 24 | 69 | 68 % | 34 % (threshold 35) |
| 20 | 5 | 34 | 79 | 78 % | 39 % (threshold 40) |

(halved thresholds: roundHalfAway(threshold × 0.5), so odd thresholds round up: 61 → 31.)

#### Cost and limits

- Mana: `manaCost(level)` 0x2d0c8c = slot 15 (level, 10) = (float) getStat(4, level).
- Recast 300 frames.
- canUse (`SkillConvertUndead_canUse` 0x2d0a58), in order (Observed):
  1. `g_pvpModeA` ≠ 0 and the caster is a player → HUD notice (90 frames), refuse.
  2. `world_collectObjectsInBox(caster position − 329.0, caster position + 329.0, out, 512)`
     (0x43a48000 on all three axes, at most 511 objects, grid order). Walk it; if any object
     O has caster→slot 20 `isEnemy(O)` ≠ 0 **and** O+0xb4 == 0x10 (creature kind "undead";
     the kind byte is read only after isEnemy accepted O) → allow.
  3. Otherwise a second HUD notice (180 frames) and refuse.
  The notice in both refusals is sent to the slot read from caster+0x3c8; on path 3 that
  read is **not** behind a player test (0x2d0b60).
- The test is a box around the caster in every direction and requires an *enemy*; the
  constructor then uses a 120-degree wedge ahead and does *not* test enmity. So canUse can
  pass (undead enemy behind the caster) and the cast still pick nothing: mana and recast are
  spent.
- Not castable by the prediction copy.

#### Behaviour

**Cast** (`SkillConvertUndead_cast` 0x2d09bc): as 39 — allocate 0x78, construct, return the
spell; position and facing arguments unused.

**Constructor** (`SpellConvertUndead_ctor` 0x2d0cc0), in order (Observed): base fields; one
shared draw → +0x10; virtual table 0x518a68; +0x18 = 0; +0x6c = `g_simFrame` (unused
afterwards); n = getStat(0, level); +0x70 = 0; +0x74 = 0.0; sound on the owner;
`world_collectObjectsInArc(radius 329.0 (0x43a48000), arc 120.0 degrees (0x42f00000),
halfWidth 0, pos = owner+0x10, facing16 = owner+0x38, list, filterObj = null)`; then, when
the list is not empty and n > 0, walk from the head and accept T when all hold, tested in
this order:

1. T object flags & 0x1000000 == 0;
2. T object flags & 0x40 == 0;
3. `creature_bossRank(T)` == 0;
4. T+0x312 == 0;
5. T+0xb4 == 0x10 (undead);
6. T+0x354 ≤ 0.0.

For each accepted T: count += 1; `handle_link(spell+0x18, T, T)` (head insertion);
`particleGroup_create()` → next slot of the array at +0x1c. Stop at the list end or count ==
n.

`SpellConvertUndead` layout (0x78 bytes):

| Offset | Type | Meaning |
|---|---|---|
| +0x00 | s8 | level |
| +0x04 | handle back-list | link into the caster's spell list |
| +0x08 | Skill* | |
| +0x0c | Creature* | owner = caster |
| +0x10 | u32 | private generator (never drawn from) |
| +0x14 | ptr | virtual table 0x518a68 |
| +0x18 | handle list head | targets, newest first |
| +0x1c | handle[20] | particle groups in acceptance order |
| +0x6c | s32 | frame of the cast (unused) |
| +0x70 | u16 | spiral angle |
| +0x74 | float | ramp |

**Run** (`SpellConvertUndead_run` 0x2d0edc). Observed:

```
d      = getStat(1, level);  frames = d * 60;  F = (float)frames
angle  = (u16)(angle + 0x10bb)
ramp   = ramp + 0.129981667                   (0x3e0519ea)
final  = (ramp > 4.0)                         -- first true on the 31st call (ramp 4.02943277)
thr    = final ? getStat(2, level) : 0
for each node of the target list, from the head:
    T = node.object;  if T is null: continue
    if not final:
        one spiral particle on T (presentation)
    else:
        big  = (T+0x1c radius > 20.0)
        thr2 = big ? roundHalfAway((float)thr * 0.5) : thr
        r    = (shared draw) % 100 + 1
        if r < thr2:
            team = owner is a player ? (s8) record[owner+0x3c8]+0x4c24 : -1
            T creature flags (+0xa8) |= 0x400000
            T+0x354 = F * 0.0166666657
            Creature_setCharm(T, frames, team)
        else if big:
            create FlyingText at T's position (resistance notice)   -- one shared draw
if final: destroy the spell (slot 1, argument 3)
```

The converted creature then behaves exactly as described in section 39 (team, untargetable
by players, follow flag 0x400000, countdown, reversion at expiry, glow; the
"dies when its charm ends" creature flag is **not** set here either).

**Differences from 39** (complete list, Observed by comparing the two sets of functions):

| Aspect | 39 convertenemy | 40 convertundead |
|---|---|---|
| recast | 600 | 300 |
| canUse | PvP mode A refusal only | PvP mode A refusal, then needs an undead enemy (slot 20, kind 0x10) in the box ± 329 around the caster |
| unguarded +0x3c8 read | none | canUse refusal path 3 |
| pick query | radius 333, arc 139° | radius 329, arc 120° |
| pick filter | not friendly, not player, not charmed, not boss, glow ≤ 0 | the same five **plus kind == 0x10** (boss test before the charm test; no effect on the result) |
| kind 0x10 targets | accepted at the pick, take a target place, then get the immunity notice at resolution and no roll | the only ones accepted; no immunity branch in run |
| resolving call | 33rd (ramp step 0.121898249) | 31st (ramp step 0.129981667) |
| spiral angle step | 0x172d | 0x10bb |
| statistics | threshold 40 + 2/rank, mana 97 + 7/rank | threshold 60 + 1/rank, mana 104 + 5/rank (targets and seconds equal at every rank 1–20) |
| slot 15 second argument | 4 | 10 (no effect: adjustLevel is the identity) |
| field layout | cast frame at +0x1c, group handles at +0x20 | group handles at +0x1c, cast frame at +0x6c |
| particle definition, speed factor | 0x8e5460, 6.84999943 | 0x8e54b0, 19.9666653 (0x419fbbbb) |
| sound, texts | own resources | own resources |

Everything else — the roll, the halving for radius > 20, the team rule, the flag, the glow
value, the setCharm call, the missing dead-target test, the reverse-order target list — is the
same code shape.

**Stacking, end conditions, non-player caster, prediction copy:** as in 39 (through the
weapon-proc path the spell is built but never run, so nothing is converted). One addition: if
a non-player ever called canUse with no undead enemy in the box, the HUD call would receive
whatever lies at +0x3c8 of that creature as the slot.

#### Random draws

1. Constructor: one shared draw (private seed).
2. Calls 1–30 of run: none.
3. Call 31, per live-node target in list order (reverse of acceptance): one shared draw for
   the roll; then, only when it failed and the radius is above 20 (and the allocation
   succeeded), one shared draw in `GameObject_ctor` of the FlyingText, which also draws twice
   from its own generator.

canUse draws nothing.

#### Presentation only

Cast sound; one spiral particle per target per frame (definition 0x8e54b0); the resistance
floating text; glow tint; the two HUD notices of canUse. Particle definitions registered by
`convertUndead_staticInit` 0x2d133c. Particle groups are not released by the destructor
0x3cd7b8 (it only clears the target list and unlinks).

#### Per-machine state

- canUse posts through `hud_showMessage` (visible on the slot's own machine only); its
  return value depends only on simulation state (box query, slot 20, kind byte). Observed.
- canUse path 3 reads caster+0x3c8 without a player test (0x2d0b60). For a player caster it
  is the slot; for any other caster it is unrelated data used as a HUD slot — a local
  display effect at most. No such caller was found (monsters and the weapon-proc path do not
  call canUse).
- Run's +0x3c8 read (0x2d1108) is behind the player test.
- Team byte: 0 offline, slot number in net games (see section 39).
- No camera, local-slot, audio or option read. None found beyond the above.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2d08d0 | SkillConvertUndead_ctor | recast 300, name |
| 0x2d0948 | SkillConvertUndead_initStats | table above |
| 0x2d09bc | SkillConvertUndead_cast | allocate and construct |
| 0x2d0a58 | SkillConvertUndead_canUse | PvP refusal; undead-enemy box test |
| 0x2d0c8c | SkillConvertUndead_manaCost | slot 15 (level, 10) |
| 0x2d0cc0 | SpellConvertUndead_ctor | target pick |
| 0x2d0edc | SpellConvertUndead_run | spiral, resolution |
| 0x3cd7b8 | SpellConvertUndead_dtor | clears the target list |
| (shared) | Creature_setCharm 0x1189f0, Creature_run charm block, Player_isEnemy 0x1b5ea8, Creature_isEnemy 0x119328 | see section 39 |
| 0x2a7e04 | Skeleton_isEnemy | an undead class's slot-20 override: base test, plus a skeleton-faction rule that applies only while the skeleton is not charmed |

#### Not determined

- `SkillConvertUndead_describeRank` 0x2d0b88 was not read beyond its position in the table.
- Which classes store kind 0x10 at +0xb4 (the "undead" reading is the project's inference
  from `Skeleton_ctor` and from this skill).
- As for 39: per-class reactions to the charm, other writers of the team byte, item data.

### 41 cyclone — SkillCyclone

(The same class serves id 84, berserkercyclone. Everything below applies to both ids; only
the name, the statistics and the tree position differ.)

#### Identity

| Item | Id 41 | Id 84 | Evidence |
|---|---|---|---|
| Internal name | cyclone | berserkercyclone | Observed: constructor 0x2d13ec chooses by its id argument |
| Skill object | 0x6e2518 (`g_skillTable[41]`, word at 0x41b214) | 0x6e3690 (`g_skillTable[84]`, word at 0x41b2c0) | Observed |
| Skill class | `SkillCyclone`, virtual table 0x518ac8; id kept at skill+0x64 | same | Observed |
| Kind (+0x08) | 0 | 0 | Observed |
| Flags (+0x04) | bit 0 set: the prediction copy casts it too | same | Observed: 0x2d1474 |
| Recast (+0x0c) | 30 frames | 30 frames | Observed |
| Effect class | `SpellCyclone`, 0x7c bytes, virtual table 0x518a98 (slot 1 destructor 0x3cd964, slot 2 run 0x2d1a94) | same | Observed |
| Who has it | barbarian tree (base level 10, needs skill 53) | berserker tree (base level 20, passive mask 0x40000) | Tree tables |
| Monsters | none | none | `docs/monsters.md` §6 |
| Slot overrides | 1 canUse 0x2d1484, 2 cast 0x2d161c, 4 describeRank 0x2d16a0, 5 manaCost 0x2d1794, 7 icon 0x3cd940, 9 initStats 0x2d1510 | same | `vtab.py show 518ac8` |

A stick-steered spin: for a number of animation loops the caster is locked in action state 6,
moves slowly where the stick points, and every 4th frame makes an ordinary weapon hit, scaled
down, on each enemy near a point that sweeps round with the weapon hand.

#### Statistics

`SkillCyclone_initStats` 0x2d1510 (**Observed**). No tier 2 tables; every use is slot 10.
Statistic 3 is not initialised (all zero, so it evaluates to 0) and is not used.

Id 41:

| Stat | Meaning | First | Base | Step (decimal, hex) |
|---|---|---|---|---|
| 0 | percent of the weapon's damage range per hit — Observed: 0x2d20b0–0x2d2178 | 1 | 30 | 2.99999285 (0x403fffe2) |
| 1 | number of loops of the spin animation (spin time = s1 × clip length) — Observed: 0x2d190c–0x2d1974 | 1 | 1 | 0.19999999 (0x3e4ccccc) |
| 2 | movement speed, × 1.4312282 units per second at full stick — Observed: 0x2d1d48–0x2d1da0 | 1 | 40 | 1.99996698 (0x3ffffeeb) |
| 4 | mana — Observed: 0x2d1794 | 1 | 24 | 2.99990082 (0x403ffe60) |

Id 84:

| Stat | Meaning | First | Base | Step (decimal, hex) |
|---|---|---|---|---|
| 0 | as above | 1 | 50 | 2.99999285 (0x403fffe2) |
| 1 | as above | 1 | 2 | 0.20099899 (0x3e4dd2ae) |
| 2 | as above | 1 | 45 | 1.99996698 (0x3ffffeeb) |
| 4 | mana | 1 | 51 | 4.00087070 (0x40800722) |

Worked values (single-precision evaluation of `getStat`):

| Rank | 41: s0 | s1 | s2 | s4 | 84: s0 | s1 | s2 | s4 |
|---|---|---|---|---|---|---|---|---|
| 1 | 30 | 1 | 40 | 24 | 50 | 2 | 45 | 51 |
| 10 | 57 | 3 | 58 | 51 | 77 | 4 | 63 | 87 |
| 20 | 87 | 5 | 78 | 81 | 107 | 6 | 83 | 127 |

Series for s1: id 41 ranks 1–20: 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 5, 5;
id 84: 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 6, 6. s0 rises by 3 per rank,
s2 by 2, s4 by 3 (id 41) or 4 (id 84) with no rounding irregularity in ranks 1–20.

The rank text (0x2d16a0) prints s0, s1 and s2 as three plain numbers.

#### Cost and limits

- Mana: slot 15 with (level, 20) = (float) getStat(4, level): id 41 24 / 51 / 81 and id 84
  51 / 87 / 127 at ranks 1 / 10 / 20. Taken once at the cast.
- Recast: 30 frames (player+0x4ae), running during the spin.
- `SkillCyclone_canUse` 0x2d1484 (skill, caster): returns 1 for a non-player. For a player it
  returns 0 when the weapon animation class (record +0x4a86) is 4 (bow) or 6 (thrown), and
  in that case also posts a HUD notice for the caster's slot (180 frames); otherwise 1.
  The notice is posted every time canUse is asked, including for the prediction copy
  (local presentation).
- General gates of the player cast path as for any kind-0 skill (see id 35).
- While spinning the player is in state 6, which `Player_processDamage` excludes from
  stagger and knock-down (0x1b2cc0, **Observed**), so the spin is not interrupted by hits.

#### Behaviour

Notation: P = caster (spell+0x0c), R = P's player record, L = spell level (s8 at +0).

##### Cast — `SkillCyclone_cast` 0x2d161c

Allocates 0x7c bytes and runs the constructor with (level, caster, skill). Position and
facing arguments are ignored. Returns the spell; `Player_castSkill` attaches it (or, for the
prediction copy, destroys it at once).

##### Constructor — `SpellCyclone_ctor` 0x2d17c8 (spell, level, caster, skill)

In order (**Observed**):

1. Base `Spell` part: one shared draw → +0x10.
2. +0x18 = 0; light node fields (table below); the light is linked.
3. **P+0x58c = 6** with no is-player test.
4. +0x58 = `g_simFrame`.
5. clip = `res_find(first word of the table at P+0x24, "cyclone1.anm")`; +0x78 = clip.
6. +0x68 = ((float)clip.length_in_ticks × 0.016666666) × (float)getStat(1, L): the spin time
   in seconds.
7. The clip's own header is modified: event slot 0 mask (clip+0x18) = 1, event slot 0 time
   (clip+0x14) = 0.05 s (0x3d4ccccc). This is a write into the loaded animation resource, not
   into the spell.
8. `anim_push(P anim state, clip, flags 0x23)`: a looping track at full weight, time 0, which
   on its first advance removes every non-persistent track under it.
9. +0x5c = 0, +0x60 = 0, +0x64 = `Spell_rand`, +0x66 = `Spell_rand`, +0x6c…+0x74 = P position.
10. Only when P is not the prediction copy: `player_voice(P slot, 10)`, the cast sound on P,
    and the target list: `world_collectInSphere(480.0, P position, …)` — every object from
    a box query of ±480 (at most 511) with `flags & 0xd == 0` whose 3-D centre distance is
    below 480 + its radius — each linked as a handle into the list at +0x18. The list ends up
    in box-query order (the helper builds a reversed temporary list and the constructor
    reverses it again). It includes P itself, friends and non-creatures; they are filtered
    at hit time.

**The target list is taken once, at the cast.** Anything that was farther than 480 units
then, or did not exist yet, cannot be hit by this spin.

| Offset | Type | Initial value | Meaning |
|---|---|---|---|
| +0x00 | s8 | level | |
| +0x04 | handle list | 0 | back-list |
| +0x08 | Skill* | skill | |
| +0x0c | Creature* | caster | |
| +0x10 | u32 | shared draw >> 16 | private generator (presentation only in this class) |
| +0x14 | ptr | 0x518a98 | virtual table |
| +0x18 | handle list | targets in range at the cast (empty for the prediction copy) | who can be hit |
| +0x1c … +0x57 | light node | colours (0x9e, 0x6f, 0x43, 0) at +0x26 and +0x2e; radius 36.0 at +0x38 and +0x40; 1/36² (0x3a4a4587) at +0x3c and +0x44; +0x24/+0x25 = 0; +0x48 = 0; position at +0x4c = P position | presentation |
| +0x58 | u32 | `g_simFrame` | start frame; never read |
| +0x5c | s32 | 0 | 0 = spinning, 1 = winding down |
| +0x60 | s32 | 0 | set to 1 by animation event bit 4; with +0x5c it switches the hits and the effect off |
| +0x64, +0x66 | s16, s16 | two private draws | particle helix phases (advance by 0x6f5 and 0x2e7 per effect call) |
| +0x68 | float | spin time in seconds | counts down by 0.05 per event bit 1 |
| +0x6c | float[3] | P position | effect anchor; follows P's movement with factor 0.962995 |
| +0x78 | ptr | "cyclone1.anm" header, later "cyclone2.anm" | clip whose event slot is being rewritten |

##### Per frame while the player is in state 6

`Player_run` case 6 (0x1a6a28), before the spell runs (**Observed**):

- prediction copy only: `Player_animStep(1.0)`;
- `Player_move(player, mode 5, pad, zero velocity)` — collision, gravity and any pending push,
  no steering;
- real player only, when a button of the ability mask was newly pressed and the selected
  ability is id 49 or 34: the repeat latch test described under id 49. Nothing for cyclone.

Then `Player_updateCast` calls `SpellCyclone_run(spell, pos, facing)` 0x2d1a94 with
pos = midpoint of model attach points 0 and 1 (height forced to P.height + 58 when it differs
from P.height by more than 58) and facing = P+0x38. The first call is on the cast frame itself.

```
ghost = (g_networkMode != 0) ? net_objOrGhost(P) : 0
ev = Player_animStep(1.0, P)                      # the real player's only animation step this frame
if ev & 1:
    spell.remaining -= 0.05                                       # +0x68
    clip = spell.clip                                             # +0x78
    t = clip.event0.time + 0.05;  clip.event0.time = t
    if clip.length_in_ticks * 0.016666666 < t:  clip.event0.time = t - that
if ev & 4:  spell.flag60 = 1
period = 5 if (level flag word 0x44fe08 & 0x100) else 4          # (int)5.370905, (int)4.4757547
tick   = (g_simFrame % period == 0)

if (P.animStatus(+0x11a) & 0x30) == 0:   P.state = 2;  destroy spell;  return
if P.state != 6:                                      destroy spell;  return

if spell.phase != 0:                                   # winding down
    shrink the light (radius *= 0.916)                  # presentation
else:                                                  # spinning
    if spell.remaining <= 0.071992 (0x3d93708a):        # start the wind-down
        top track of P: life = 1.0, life rate = -0.8333333 (0xbf555554)
        clip2 = res_find(P's animation table, "cyclone2.anm");  spell.clip = clip2
        clip2.event1.mask (clip2+0x28) = 4;  clip2.event1.time (clip2+0x24) = 0.166995 s (0x3e2b00bc)
        anim_startBlendInOut(0.0, 0.225999 (0x3e676c48), P anim state, clip2, flags 0x32)
        same call on ghost's animation state when ghost != 0
        spell.phase = 1
    # movement (also on the frame the wind-down starts)
    speed = (float)getStat(2, L) * 143.12282 (0x430f1f71) * 0.01 (0x3c23d70a)
    yaw   = net_getCamYaw(P.slot)
    a = -yaw - 0x4000;   b = -yaw - 0x8000
    sx = g_pads[P.slot] float at +0x14;   sy = g_pads[P.slot] float at +0x18
    f = (-speed) * sy;   g = speed * sx
    vel.x = (-cos16(a)) * f + (-cos16(b)) * g
    vel.y = (-sin16(a)) * f + (-sin16(b)) * g
    vel.z = 0
    old = P.pos
    Player_move(P, mode 5, &g_pads[P.slot], &vel)
    spell.anchor += (P.pos - old) * 0.962995 (0x3f7686d7)           # +0x6c, presentation

if spell.phase == 0 or spell.flag60 == 0:
    SpellCyclone_updateFx(spell, &pos)                              # 0x2d21e0, presentation
    q = model_getAttachPoint(1.0, P body model (+0x544), origin = pos, facing, P anim state, point 0)
    d = (q.x - pos.x, q.y - pos.y)
    inv = 1.0 / sqrt(d.x*d.x + d.y*d.y)
    h = (pos.x + (d.x*inv) * 28.584467 (0x41e4acfd),  pos.y + (d.y*inv) * 28.584467)
    if tick:
        scale = (float)getStat(0, L) * 0.01
        for node in spell.targets, head to tail:
            o = node.object
            if o == 0: continue                          # object gone
            if P->isEnemy(o) == 0: continue              # Creature slot 20
            if sqrt((o.x-h.x)^2 + (o.y-h.y)^2) < o.radius + 23.0:
                Player_meleeHit(scale, P, o, 0, 0x40000000)

if net_isLocalSlot(P.slot):  g_forceGhostRebase = 0x78
```

Notes on the listing (**Observed** unless marked):

- `ev` is the merged event mask of every live animation track of P, not only of the spin
  clip (`anim_advance` ORs the masks of all tracks whatever their weight). The player's four
  base locomotion tracks are persistent (flags 0x1205, set by `player_resetIdleAnim`
  0x1b2470) and are therefore still alive under the spin clip. If their clips carry events
  with mask bit 1 or 4 (the walking code masks the same return value with 1 or 4 for
  footsteps, 0x1b4020), those also count down +0x68, move the spin clip's event time and set
  +0x60. Which clips carry which masks is animation data and was not available.
- With only the spin clip contributing, event slot 0 fires when the track time window
  [t/60, (t + step)/60) contains the slot time; the slot then moves 0.05 s (3 ticks) ahead,
  so it fires once every 3 frames at animation speed 1.0, first on the fourth run of the
  spell. The spin phase therefore lasts about s1 × clip length frames: the count-down needs
  N firings with (start − 0.05 N) ≤ 0.071992. Slowing effects scale the animation step
  (`Player_animStep` multiplies by (60 − slow)/60 and by the Drowsy factor) and stretch the
  spin accordingly.
- The wind-down: the spin loop track dies within two advances, "cyclone2.anm" plays once
  with a 0.226 s fade-out and no blend-in. Hits continue during the wind-down until an
  event with bit 4 has been seen (the slot written at clip2+0x24 is at 0.167 s, i.e. 10–11
  frames in). The player no longer moves by stick in this phase.
- End: on the first run after which no track with flag 0x10 or 0x20 is alive (the spin clip
  has 0x23, the wind-down clip 0x32) the spell writes state 2 and destroys itself. If the
  player's state is anything other than 6 while such a track is alive (death), the spell
  destroys itself without touching the state.
- The hit point h is the hand midpoint pushed 28.58 units horizontally in the direction of
  attach point 0's offset from the model origin in the current pose; it circles the caster
  as the clip turns the body. P's facing word is not changed by the spell.
- Stick input is read straight from `g_pads[slot]`, not from the pad pointer `Player_run`
  uses (which is a zeroed pad while controls are locked). The earlier `Player_move` call of
  the same frame can zero the stick fields in the real pad (stick-ignore counter +0x481, open
  dialog) before the spell reads them.
- Movement speed at full deflection: rank 1 57.25, rank 10 83.01, rank 20 111.64 units/s for
  id 41 (s2 × 1.4312282); scaled by the slow factor inside `Player_move`.

##### The hit — `Player_meleeHit` 0x1b6a98 (scale, player, target, 0, extraFlags)

Called with scale = s0 / 100 and extraFlags = 0x40000000. With a non-zero scale
(**Observed**):

1. Returns at once for the prediction copy. No line-of-sight test (that is only for scale 0).
2. Weapon W: normally `R.weaponSet[R.activeSet]` (record +0x4434 indexed by the s8 at
   +0x4a7c). When equipment slots 0 and 1 (record +0x43f0, +0x43f4) are both filled, the
   class passive with mask 0x40000 has a level above 0 and the combo step (player+0x460) is
   odd, W is the second weapon (record +0x443c) and the hand index is 1.
3. `Player_recalcDamage(player, W, 0)` rebuilds record +0xd0 (minimum), +0xd4 (maximum) and
   +0xcc (attack rating).
4. flags = W's damage class bits (item definition +0x20), or 1 when unarmed; | 0x1000 when
   the weapon animation class is 1 and at least 60 frames have passed since player+0x448;
   | 0x80000 (scale ≠ 0).
5. If W exists and the weapon animation class is 4 or W's definition byte +0x1e is 6:
   `Player_recalcDamage(player, 0, 0)` (unarmed numbers) and flags |= 0x200000.
6. If player+0x44c is 2 (a heavy attack was pending): flags |= 0x200000, both record bounds
   get the heavy-attack bonus added and, for a creature target, `Player_hitSparks` is called
   (shared draws).
7. Scaling: record +0xd0 = round(record +0xd0 × scale), record +0xd4 = round(record +0xd4 ×
   scale), each rounded half away from zero; the scaled values **stay in the record** until
   the next `Player_recalcDamage`.
8. If the player has a `SpellHarmTouch` attached, `SpellHarmTouch_applyToHit` adds its
   damage (see id 42) and flags |= 0x200000.
9. `damage_apply(min = (float)record +0xd0, max = (float)record +0xd4, victim = target,
   attacker = player, attack rating = record +0xcc, a3 = W's attack-rating field, t0 = low
   word of W's flags (both unused by `damage_apply`), flags | 0x40000000, descriptor = W
   (the item record, whose four modifiers at +0x24 are the descriptor entries; 0 when
   unarmed), noCrit = 0)`.
10. If the call returned non-zero and the target is a creature: the hit-material byte of
    hand's weapon-trail block (record +0x4ac5 + hand × 0x40) is set from the target's
    creature flags (0x2000 → 3, 0x1000 → 2, 0x40000 → 1, else 0) and the 5-frame timer next
    to it (+0x4ac6 + hand × 0x40) to 5.

So each cyclone hit is a normal weapon hit with the weapon's own damage class and on-hit
effects, damage range scaled by s0 %, flag 0x80000 instead of the 0x40000 of a normal swing,
and flag 0x40000000 (no critical-hit bonus from the attacker's skills; a critical chance in
the weapon's own descriptor entry 0x1d still applies).

##### Destructor 0x3cd964

Destroys the light node, clears the target handle list and the back-list, frees the block
when bit 0 of the argument is set.

#### Random draws

Shared generator:

1. `SpellCyclone_ctor`: one draw (also when the prediction copy casts; the prediction loop
   restores the generator).
2. Per hit: whatever `damage_apply` draws (`docs/gameplay.md` §2.5), in target-list order
   within a tick; plus `Player_hitSparks` draws when player+0x44c is 2.

Private generator (never used for a gameplay value in this class):

1. Constructor: two draws (+0x64, +0x66).
2. `SpellCyclone_updateFx`: three draws per call when L > 8 and `g_simFrame % 3 == 0`.

#### Presentation only

Light that follows the hands (radius 36 + 90 × cos16(frame)), a 72-particle helix per frame
(definition 0x8e5500) and extra sparks at rank 9 and above (0x8e5550), both registered by
the static initialiser 0x2d272c; voice line 10 and the cast sound (`spel_bw_cyclone.anm`);
the two animation clips; the HUD notice from canUse.

#### Per-machine state

- **Prediction copy writes a shared animation resource.** Because flag bit 0 lets the copy
  cast, `SpellCyclone_ctor` runs for the copy and, before its copy test at 0x2d19c4, stores
  the event slot of "cyclone1.anm" (0x2d1978, 0x2d197c). That header is shared by every
  object playing the clip. On the owner's machine only, the slot time is reset to 0.05 some
  frames before the real cast. For the caster's own later spin this is harmless (the real
  constructor writes the same values, and no real spin of the same player is running in
  between). If **another player using the same animation set** is in the spin phase at that
  moment, that player's count-down is disturbed on this machine only: the next bit-1 event
  can come up to one clip length late, so the spin ends on a different frame than on the
  other machines. **Observed** stores; the shared-clip condition is **Inferred** (two
  players with the same character model resolve the same resource); not tested.
- Even without prediction, two spinning players who share the clip push the same event slot;
  that interaction is the same on every machine.
- The other constructor writes that reach the copy (state 6, the pushed track, the light) are
  on the copy's own object or are undone when the spell is destroyed. The voice, sound and
  target gathering are skipped for the copy.
- `net_objOrGhost` (0x2d1b04, net games only): starts the wind-down clip on this machine's
  copy as well. Presentation.
- `net_isLocalSlot` → `g_forceGhostRebase = 0x78` each frame (0x2d218c–0x2d21a0). Per-machine,
  presentation.
- `Player_meleeHit` returns for the copy; the copy has no attached spell anyway.
- Non-player caster (weapon-effect cast, or any future monster use): the constructor writes
  +0x58c on an object that is not a Player (0x2d18f8) and passes +0x3c8 of it to
  `player_voice` (0x2d19d8); the run function uses +0x3c8 to index `g_pads` and calls
  `Player_animStep` / `Player_move` on the owner (0x2d1d94, 0x2d1dfc, 0x2d1efc, 0x2d2190).
  None of this is guarded. No monster uses the skill.
- Weapon-effect cast by a player attacker: the spell is not attached, so it never runs;
  the player stays in state 6 (no animation step for the real player in `Player_run` case 6,
  no stagger) until it dies. **Observed** code path; reachability **Unknown** (item data).
- Level flag word 0x44fe08 bit 0x100 changes the hit period from 4 to 5 frames; it comes from
  level data and is the same on every machine.
- No use of the camera (other than `net_getCamYaw`, which in a net game is the input-record
  value), the cosmetic generator, 0x404468 or a local option for a gameplay decision.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2d13ec | `SkillCyclone_ctor` | (skill, id): name by id, flag bit 0 |
| 0x2d1484 | `SkillCyclone_canUse` | bow / thrown weapon refusal with notice |
| 0x2d1510 | `SkillCyclone_initStats` | two constant sets chosen by skill+0x64 |
| 0x2d161c | `SkillCyclone_cast` | |
| 0x2d16a0 | `SkillCyclone_describeRank` | |
| 0x2d1794 | `SkillCyclone_manaCost` | |
| 0x2d17c8 | `SpellCyclone_ctor` | |
| 0x2d1a94 | `SpellCyclone_run` | |
| 0x2d21e0 | `SpellCyclone_updateFx` (proposed) | light and particles; only caller 0x2d1f94 |
| 0x3cd964 | `SpellCyclone_dtor` | light, target list, back-list |
| 0x2d272c | `cyclone_staticInit` | particle definitions |
| 0x1b6a98 | `Player_meleeHit` | the hit |
| 0x1a5030 | `Player_run` | case 6 |
| 0x1a3f70 | `Player_updateCast` | position handed to the spell |
| 0x1b4020 | `Player_move` | mode 5 |
| 0x14ab80 | `world_collectInSphere` | target gathering |
| 0x16d748 | `anim_advance` | event test (head of the function only) |
| 0x170838, 0x16ceb0 | `anim_push`, `anim_startBlendInOut` | track parameters |
| 0x1b2470 | `player_resetIdleAnim` | flags of the base tracks |

#### Not determined

- Lengths and event tables of "cyclone1.anm" / "cyclone2.anm" and of the base locomotion
  clips (data): they fix the spin time in frames and whether footstep events interfere as
  described.
- Whether the table at P+0x24 is one per model (shared by players with the same character)
  — assumed in the hazard above.
- `Player_recalcDamage` and `Player_hitSparks` were used by interface only.
- Exactly when `anim_advance` drops the finished wind-down track relative to the status word
  the spell tests (decides the last frame to within one).
- Which items, if any, cast id 41 or 84 as a weapon effect.

### 42 harmtouch — SkillHarmTouch

#### Identity

| Item | Value | Evidence |
|---|---|---|
| Skill id | 42 (`g_skillTable[42]` at 0x41b218 → object 0x6e2580) | Observed |
| Internal name | harmtouch | Observed: constructor 0x2d2850 |
| Skill class | `SkillHarmTouch`, virtual table 0x518b80 | Observed |
| Kind (+0x08) | 7: an instant skill — no cast animation, no change of action state; the only class that sets 7. `Player_run` tests the type byte of the ability record (+0x25 == 7), which carries the same value (where the record byte is filled from the skill was not read: **Inferred**) | Observed: 0x2d2850; handling in `Player_run` below |
| Flags (+0x04) | 0 | Observed |
| Recast (+0x0c) | 300 frames | Observed |
| Effect class | `SpellHarmTouch`, 0x1c bytes, virtual table 0x518b50 (slot 1 destructor 0x3cdaa8, slot 2 run 0x2d2c0c; slots 3 and 4 base) | Observed |
| Who has it | shadowknight tree (base level 25, needs skill 97). No monster | Tree table; `docs/monsters.md` §6 |
| Slot overrides | 1 canUse 0x2d2984, 2 cast 0x2d2a04, 4 describeRank 0x2d2a88, 5 manaCost 0x2d2950, 7 icon 0x3cda84, 9 initStats 0x2d28cc | `vtab.py show 518b80` |

The skill arms the caster's next melee hit: from the cast frame until 39 frames later, the
first `Player_meleeHit` made against a creature has its damage range **replaced** by the
skill's figure, and the spell is used up.

#### Statistics

`SkillHarmTouch_initStats` 0x2d28cc (**Observed**).

| Stat | Meaning | Tier 1: first, base, step | Tier 2: first, base, step |
|---|---|---|---|
| 0 | damage of the touched hit (lower bound; the upper bound is up to 20 % more) — Observed: 0x2d2f98–0x2d302c | 1, 420, 11.99988079 (0x413fff83) | 1, 5, 5.00000572 (0x40a0000c) |
| 1 | printed by the rank text only; no code in the skill reads it (**Observed**: the skill object is referenced only from the table; the spell asks it for stat 0 only) | 1, 5, 0.33299997 (0x3eaa7ef9) | 1, 4, 0.0 |
| 4 | mana — Observed: 0x2d2950 | 1, 135, 6.00080872 (0x40c006a0) | none |

Lookup used for the damage: slot 12 `getStatFor(0, level, owner, cap 10)` — a player owner
gets tier 1 `getStat(0, level)`; any other owner would get tier 2 with the level limited to
10 (not reachable, see Per-machine state).

| Rank | s0 | s1 (display) | s4 mana |
|---|---|---|---|
| 1 | 420 | 5 | 135 |
| 10 | 528 | 8 | 189 |
| 20 | 648 | 11 | 249 |

s0 +12 per rank, s4 +6 per rank (no rounding irregularity in ranks 1–20); s1: 5, 5, 6, 6, 6,
7, 7, 7, 8, 8, 8, 9, 9, 9, 10, 10, 10, 11, 11, 11. Tier 2 s0: 5 L for L ≤ 10.

The rank text (0x2d2a88) prints the range from slot 8 `getStatRange(0.2, 0, level, 0, …)`
(round(0.8 s0) … round(1.2 s0)) and s1. Note that the real hit never goes below s0.

#### Cost and limits

- Mana: slot 15 with (level, 18) = (float) getStat(4, level): 135 / 189 / 249.
- Recast: 300 frames in the shared ability counter player+0x4ae, so no ability of any kind
  can be started for five seconds after a harm touch.
- `SkillHarmTouch_canUse` 0x2d2984: 1 for a non-player; for a player 0, with a HUD notice
  (180 frames), when the weapon animation class (record +0x4a86) is 4 (bow) or 6 (thrown).
- How an instant skill is started (`Player_run`, **Observed**):
  1. Before the state switch (0x1a5c6c–0x1a5e28), on a frame where +0x4ae is 0 and an ability
     button is newly pressed (or a forced record is pending; without a forced record the
     whole test is skipped while any pad button of mask 0xf000 is held) and that ability
     record is of the instant type with a Skill behind it: canUse is asked, then the rank's mana cost is
     compared with the record's mana (too little: voice line 4, request dropped). On success a
     local value M is set to the button's pad mask (−1 for a forced record).
  2. State 2 (neutral): the ordinary ability path (button held, mana above 1.0, +0x4ae == 0,
     cost ≤ mana) calls `Player_castSkill` at once for an instant record (0x1a7048) and does
     not enter state 5. Later in the same handler a non-zero M counts like a press of the
     attack button: if the minimum time between attacks has passed (+0x48c × 60 frames since
     +0x448), the player enters state 1 and a swing starts on that same frame.
  3. State 1 (swing in progress): where the handler looks for a new attack press to chain
     the combo, a press matching M (or M == −1) calls `Player_castSkill` (0x1aac60) and
     then counts as that attack press.
  In any other state the press does nothing.

#### Behaviour

##### Cast — `SkillHarmTouch_cast` 0x2d2a04

Allocates 0x1c bytes and runs `SpellHarmTouch_ctor(spell, level, caster, skill)`; returns the
spell, which `Player_castSkill` attaches to the caster. Position and facing are ignored.

##### Constructor — `SpellHarmTouch_ctor` 0x2d2b5c

Base `Spell` part (one shared draw → +0x10), then +0x18 = 0.661 (0x3f29372a), and the cast
sound on the caster (`spel_de_harm.anm` from `fx.lmp`).

| Offset | Type | Initial value | Meaning |
|---|---|---|---|
| +0x00 | s8 | level | |
| +0x04 | handle list | 0 | back-list |
| +0x08 | Skill* | skill | |
| +0x0c | Creature* | caster | |
| +0x10 | u32 | shared draw >> 16 | private generator: particles, then the damage spread |
| +0x14 | ptr | 0x518b50 | virtual table |
| +0x18 | float | 0.661 | seconds left |

##### Every frame — `SpellHarmTouch_run` 0x2d2c0c

```
t = spell.time - 0.016666666;  spell.time = t
if t < 0:  destroy the spell (slot 1 with 3)
else:      owner colour flash: +0x96 = 113;  +0x92 = +0x9a = (s16)trunc(min(t, 1.0) * 128.0)
```

For a player the run happens in `Player_updateCast`, after the action-state handler, and the
first run is on the cast frame F0. In single precision the timer goes negative on the 40th
run, so the spell exists while the state handlers of frames F0 … F0+39 execute, and is gone
after that (40 frames in all).

##### The touch — `SpellHarmTouch_applyToHit` 0x2d2cbc (spell, target, int *min, int *max)

Called from exactly one place, `Player_meleeHit` 0x1b7000. There (**Observed**,
0x1b6fd0–0x1b7040), after the weapon has been chosen, `Player_recalcDamage` has filled record
+0xd0/+0xd4 and any scale has been applied (see id 41 for the full sequence):

```
min = record.weaponMin;  max = record.weaponMax          # local copies
s = creature_findSpellByType(player, SpellHarmTouch)
if s:
    SpellHarmTouch_applyToHit(s, target, &min, &max)
    flags |= 0x200000
damage_apply((float)min, (float)max, target, player, record.attackRating, ...,
             flags | extraFlags, descriptor = weapon item, noCrit 0)
```

Inside `SpellHarmTouch_applyToHit`:

1. The owner's colour flash is refreshed as in the run function.
2. If the target is **not** a creature (flag 0x20 clear): return. min and max are untouched
   and the spell stays armed (but the caller has still added flag 0x200000 to that hit).
3. Otherwise:
   - 102 times: one private draw (model sample point of the target, modulo the point count),
     one more private draw whose value is discarded, two particles. 204 draws.
   - A `LightEffect` (0xbc bytes) at the target position + (0, 0, 73), first three colour
     arguments (83, 218, 73): a GameObject, so one shared draw in its constructor (skipped if the allocation fails).
   - d = `getStatFor(0, L, owner, 10)`.
   - `*min = d`.
   - r = one private draw; `*max = d + trunc(((float)d × 0.19999999) × ((float)r × 1/65536))`.
   - The spell destroys itself.

Consequences (**Observed** from the two functions):

- The weapon's own damage range is discarded for that hit, not added to. Everything else
  about the hit is the weapon's: damage class bits, attack rating (the hit can miss or be
  scaled down by armour as usual), the weapon's on-hit descriptor entries, critical rolls.
- The hit carries flag 0x200000, the strongest of the knock bits, in addition to the 0x40000
  or 0x80000 a melee hit already has.
- The touch is spent on the first creature hit whatever `damage_apply` then decides (block,
  miss, immunity).
- Any caller of `Player_meleeHit` triggers it: the normal swing of state 1 and a Cyclone
  tick. With a Cyclone tick the scaled-down weapon range is replaced by the full touch
  damage for that one target.
- `Player_meleeHit` returns before the hook for the prediction copy, and for a normal swing
  when its line-of-sight test fails; the touch is not spent in those cases.
- When the melee hit lands relative to the swing start is a property of state 1
  (`docs/player.md`: 16 frames ÷ attack speed, or the first frame in a net game); it has to
  fall within the window.

Worked damage: rank 1 min 420, max 420…503; rank 10 min 528, max 528…633; rank 20 min 648,
max 648…777 (max = d + trunc(0.2 d × fraction), fraction in [0, 1)).

##### Destructor 0x3cdaa8

Base destructor only.

#### Random draws

Shared generator:

1. `SpellHarmTouch_ctor`: one draw.
2. In the touch: one draw by the `LightEffect` constructor, before the damage call.
3. The `damage_apply` sequence of the melee hit itself (`docs/gameplay.md` §2.5; with
   min < max the base roll draws).

Private generator (seeded in the constructor, not used by the run function): in the touch,
204 draws for particles, then **the 205th draw is the damage spread**.

#### Presentation only

Cast sound, the caster's colour flash while armed, 204 particles at the target whose
velocity points away from the caster (definitions 0x8e55a0 and 0x8e55f0, registered by the
static initialiser 0x2d3060), the `LightEffect` on the target, the HUD notice from canUse.

#### Per-machine state

- canUse tests flag 0x40 before using +0x3c8 (**Observed**). The constructor and the run
  function use no player field. The touch hook runs only from `Player_meleeHit`, on the
  player it was found on.
- Flag bit 0 is clear, so `Player_castSkill` returns for the prediction copy; the copy's
  canUse call can post the HUD notice (local). `Player_meleeHit` returns for the copy.
- The private generator is drawn only inside the touch, a fixed 204 times before the damage
  spread; nothing position- or machine-dependent changes the count (**Observed**: the loop
  bound is constant; the sample-point count only enters as a modulus).
- The `LightEffect` shared draw is skipped when the pool allocation fails.
- Weapon-effect cast with id 42: the spell is created (shared draw, sound) but not attached
  to anything, so it is never found by `Player_meleeHit`, never run and never freed — a
  0x1c-byte leak per trigger, no gameplay effect. Because nothing but `Player_meleeHit`
  looks for the spell, the tier 2 table is never used.
- None found otherwise: no camera, local slot, audio, cosmetic generator or 0x404468 use.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2d2850 | `SkillHarmTouch_ctor` | kind 7, recast 300 |
| 0x2d28cc | `SkillHarmTouch_initStats` | |
| 0x2d2950 | `SkillHarmTouch_manaCost` | slot 15 with (level, 18) |
| 0x2d2984 | `SkillHarmTouch_canUse` | bow / thrown refusal |
| 0x2d2a04 | `SkillHarmTouch_cast` | |
| 0x2d2a88 | `SkillHarmTouch_describeRank` | |
| 0x2d2b5c | `SpellHarmTouch_ctor` | |
| 0x2d2c0c | `SpellHarmTouch_run` | timer and flash |
| 0x2d2cbc | `SpellHarmTouch_applyToHit` (proposed) | replaces the hit's damage range; caller 0x1b7000 |
| 0x3cdaa8 | `SpellHarmTouch_dtor` | |
| 0x1b6a98 | `Player_meleeHit` | the hook and the damage call |
| 0x1a5030 | `Player_run` | instant-skill handling before the switch and in cases 1 and 2 |
| 0x1a42b8 | `Player_castSkill` | |

#### Not determined

- What statistic 1 was meant to be (the rank text shows it; nothing reads it).
- The state-1 swing timing itself was taken from `docs/player.md`, not re-derived.
- What the take-damage implementations do with flag 0x200000.
- Whether any item casts id 42 as a weapon effect.

### 43 firearrow — SkillFireArrow

#### Identity

Id 43, internal name firearrow. Skill class `SkillFireArrow`, virtual table 0x518e70, Skill
object 0x6e25e8 (`g_skillTable[43]`, pointer at 0x41b21c). Kind 8, flags 0, recast field 30
(not effective, S.4 step 13). Active. Effect class `FireArrowProjectile`: 0xb0 bytes, virtual
table 0x518de0, derived directly from `Projectile` (not from `MissileWeapon`). Ranger tree
(level 10, prerequisite skill 75). Monsters that build the projectile themselves: MaleDarkElf
0x25c8a8, Goblin 0x26c0e0, Gremlin 0x26ec1c, Orc 0x2a2670 (second constructor), Skeleton
0x2a72bc (first constructor). All **Observed** (constructor 0x2d5ec0, cross-references).

#### Statistics

Set by `SkillFireArrow_initStats` 0x2d5f34. **Observed.**

| Stat | Meaning (where used) | Tier 1: first, base, step | Tier 2 |
|---|---|---|---|
| 0 | fire damage added to the hit (onHit 0x2d68e8-0x2d6920) | 1, 41, 5.00085497 (0x40a00701) | 1, 2, 2.0 (0x40000000) |
| 1 | flight speed in units per second (constructor calls 0x2d63ac, 0x2d65d8) | 1, 395, 22.4347706 (0x41b37a69) | none |
| 2 | collision radius of the projectile (constructor calls 0x2d6374, 0x2d65a0) | 1, 8, 0.414998978 (0x3ed47abf) | none |
| 3 | unused (first 0, base 0, step 0: always 0) | | none |
| 4 | mana cost (slot 15) | 1, 25, 2.99998093 (0x403fffb0) | none |

Uses: radius and speed through slot 12 `getStatFor(stat, level, caster, 10)` (player: tier 1
at the rank; other: slot 11 with the level limited to 10, tier-1 tables because the
statistics have no tier 2). Damage through slot 13 `getStatForHandle(0, level, &ownerHandle,
0)` (player: tier 1; other: tier 2 with no level limit).

| Rank | stat 0 | stat 1 | units/frame | stat 2 | stat 4 |
|---|---|---|---|---|---|
| 1 | 41 | 395 | 6.583 | 8 | 25 |
| 10 | 86 | 597 | 9.950 | 12 | 52 |
| 20 | 136 | 821 | 13.683 | 16 | 82 |

Stat 0 by rank 1..20: 41 46 51 56 61 66 71 76 81 86 91 96 101 106 111 116 121 126 131 136.
Stat 1: 395 417 440 462 485 507 530 552 574 597 619 642 664 687 709 732 754 776 799 821.
Stat 2: 8 8 9 9 10 10 10 11 11 12 12 13 13 13 14 14 15 15 15 16.
Tier 2 stat 0 at level L: 2L (L = 1: 2; 10: 20; 20: 40).

#### Cost and limits

Mana = `(float) getStat(4, rank)` = 25 + 3 x (rank - 1): 25, 52, 82 at ranks 1, 10, 20, paid on
the release frame (S.5 step 6). No effective recast. canUse: a player needs a bow (weapon
animation class 4); any non-player may. Other gates: all of S.2 (ability button held, recast
counter 0, mana > 1.0 and >= cost, on the ground, an ammunition stack). One arrow of
ammunition is consumed per shot (S.4 step 10).

#### Behaviour

**Cast** `SkillFireArrow_cast(skill, level, caster, pos*, facing)` 0x2d603c (**Observed**):
copy pos, subtract 12.0 from its height; `pool_new(0xb0)`; when that succeeds, level' =
slot 14 (level, 20) (= level) and `FireArrowProjectile_ctor(obj, &pos, facing, caster, level',
skill)`. Returns 0. No test of the caster's kind, mana, weapon or ammunition here.

**First constructor** 0x2d6238 (obj, pos*, s16 facing, owner, level, skill), **Observed**:

1. `Projectile_ctor(obj, pos, owner, 0)`: one shared draw; flags 0x4081; height extent 72.
2. Virtual table 0x518de0; light record at +0x70 filled and linked (`light_link`).
3. +0xac = skill; +0x64 = facing; +0x6c = level.
4. +0x1c (radius) = (float) `getStatFor(2, level, owner, 10)`.
5. s = (float) `getStatFor(1, level, owner, 10)`; velocity +0x54 = (cos16(facing) x s,
   sin16(facing) x s, 0.0).
6. +0x68 = 0 (age), +0x60 = 0 (not ended); `obj_runEveryFrame(obj)`; launch sound on obj.

**Second constructor** 0x2d6440 (obj, pos*, dir*, owner, level, skill), **Observed**: the
same, except +0x64 = `math_atan2_16(dir.y, dir.x)` and velocity = (dir x inv) x s for all
three components, with inv = 1.0 / sqrt(dir.x^2 + dir.y^2 + dir.z^2) computed by one
reciprocal-square-root instruction (0x2d6638) and the two multiplications in that order.

**Run** 0x2d66ac, once per frame while +0x60 == 0 (**Observed**):

```
age (+0x68) += 1
r = obj_moveAndCollide(this, velocity)          # may call onHit, S.7
if r & 1:            end(this, 1)               # terrain
elif age >= 601:     end(this, 0)               # lifetime 600 moving frames
else:                smoke puff (presentation); light position = pos; light_relink
```

An overlap that onHit rejects (bit 1 of r) does not stop the arrow. Range on flat ground
without a hit: 600 x speed / 60 = 10 x speed: 3950 units at rank 1, 8210 at rank 20.

**onHit** 0x2d685c (this, other), called from inside `obj_moveAndCollide` for every
overlapping object (**Observed**):

1. Build an empty descriptor on the stack (four slots of type -1, bytes +0x20/+0x21 = 0xff,
   words +0x10..+0x1e zero).
2. If the owner handle +0x4c is empty: return (the arrow keeps flying and can never hit).
3. D = `skill->getStatForHandle(0, level +0x6c, &ownerHandle, 0)` (slot 13).
4. **One own draw** r (always, before any test).
   hi = D + trunc((float)D x 0.2 (0x3e4ccccc) x (r x 1/65536)) (single precision; convert
   toward zero).
5. Owner is a player (flag 0x40):
   - return when other has object flag 0x1000000 (friendly to players);
   - return when other is a creature with creature flag 0x4000000 (friendly);
   - return when `owner.slot20(other)` is 0;
   - flags by level: <= 5: 0x60; 6..10: 0x40060; 11..15: 0x80060; >= 16: 0x200060 (bits
     0x40000 / 0x80000 / 0x200000 select the corpse knock-back speed 100 / 150 / 312.5 in
     `Creature_processDamage`; 0x40 = cannot be blocked);
   - descriptor: the first slot that is empty or already 0x1f becomes {type 0x1f, v1 = 100,
     v2 = D, v3 = D} (100 % chance of fire for D..D plus the burn status);
   - `damage_apply(min = (float) record+0xd0, max = (float) record+0xd4, victim = other,
     attacker = owner, attack = 100000, 0, 0, flags, &descriptor, noCrit = 0)`, the record
     being the owner's player record **at this moment** (S.6).
6. Owner is not a player:
   - return when `owner.slot20(other)` is 0;
   - descriptor slot {type 0x15, v1 = D, v2 = D, v3 = 0} (fire damage D..D, burn status);
   - `damage_apply(min = (float)D, max = (float)hi, other, owner, 100000, 0, 0, 0x60,
     &descriptor, 0)`.
7. `end(this, 2)`.

There is no "already ended" test at the top of onHit, and `obj_moveAndCollide` keeps
iterating, so when the arrow overlaps several enemies on the same frame **each of them is
damaged** (each with a new own draw and its own `damage_apply` draws); the arrow is deleted
once.

**end** 0x2d6bb8 (this, reason), **Observed**: only when +0x60 == 0: when reason != 0 an
impact sound on the object; `obj_delete(this)` (deferred delete); +0x60 = 1.

What the skill adds to a bow shot, for a player: the hit uses the full current weapon damage
range (with dexterity, Archery and the record multipliers of S.6), always passes the hit rolls
(attack 100000 against armour: p = sqrt(100000 / AC) >= 1 for any AC up to 100000), cannot be
blocked, adds D fire damage through a 100 % proc slot, and is not affected by the bow's item
modifiers, PenetratingArrows, or a target's deflection chance (none of the `MissileWeapon`
logic of S.8 applies).

Field layout of `FireArrowProjectile` (0xb0):

| Offset | Type | Meaning |
|---|---|---|
| +0x00..+0x53 | | `Projectile` part: flags +0x0c, position +0x10, radius +0x1c (stat 2), height extent +0x20 (72.0), own generator +0x44, virtual table +0x48, owner handle +0x4c, water-splash byte +0x50 |
| +0x54 | float[3] | velocity, units per second |
| +0x60 | s32 | ended (0 / 1) |
| +0x64 | s16 | facing |
| +0x68 | s32 | age in frames |
| +0x6c | s32 | level |
| +0x70..+0xab | light record | colour (109, 100, 76) twice at +0x7a and +0x82, radius 96.0 at +0x8c and +0x94, 1/9216 (0x38e38e38) at +0x90 and +0x98, position at +0xa0 |
| +0xac | Skill* | the skill object |

#### Random draws

Player shot, in order: shared draws A-E of the release block (S.4); 1 shared draw in
`Projectile_ctor`; per frame none; on a terrain hit over water 1 own draw (value unused); per
overlapping object with a live owner 1 own draw (value used only for a non-player owner);
then the draws of `damage_apply` (docs/gameplay.md 2.5; with this descriptor the 0x1f proc
roll and its amount roll are both made when the first hit roll succeeds).

#### Presentation only

Launch sound and impact sound on the object; per-frame smoke puff
`fx_impactPuffNearCamera(radius, radius^2 x 0.021989 + 0.267, pos, velocity/60, 1)` (camera
gated, cosmetic generator); a linked light; draw 0x2d67e8 adds one glow of size radius x
1408.

#### Per-machine state

- The player branch reads the owner's record +0xd0 / +0xd4 at hit time; see S.10 for the
  one path found that can make those differ between machines.
- `owner + 0x3c8` is read only inside the is-player branch (no missing test).
- The smoke puff is camera gated and uses only the cosmetic generator; it does not touch the
  arrow's own generator. None found otherwise.

#### Functions read

| Address | Name | What |
|---|---|---|
| 0x2d5ec0 | `SkillFireArrow_ctor` | static object setup |
| 0x2d5f34 | `SkillFireArrow_initStats` | statistics |
| 0x2d5fc4 | `SkillFireArrow_canUse` | bow test |
| 0x2d603c | `SkillFireArrow_cast` | creates the projectile |
| 0x2d6108 | `SkillFireArrow_describeRank` | menu text from stats 0, 1 / 12, 2 |
| 0x2d6204 | `SkillFireArrow_manaCost` | slot 15 forward |
| 0x2d6238 | `FireArrowProjectile_ctor` | facing form |
| 0x2d6440 | `FireArrowProjectile_ctor2` | direction-vector form |
| 0x2d66ac | `FireArrowProjectile_run` | |
| 0x2d67e8 | `FireArrowProjectile_draw` | |
| 0x2d685c | `FireArrowProjectile_onHit` | |
| 0x2d6bb8 | proposed `FireArrowProjectile_end` | sound, deferred delete, ended flag |

#### Not determined

- What Player slot 20 returns for non-creature objects (decides whether a player's fire arrow
  damages breakable props; `damage_apply` has a non-creature path).
- The Goblin, Gremlin and Orc call sites of the second constructor were not read line by
  line (MaleDarkElf and Skeleton were); their level argument is assumed to be the same
  truncated level-wide monster level.
- `FireArrowProjectile_dtor` 0x3cde04 (expected: unlink the light) was not read.

### 44 coldarrow — SkillColdArrow

#### Identity

Id 44, internal name coldarrow. Skill class `SkillColdArrow`, virtual table 0x518f88, Skill
object 0x6e2650 (`g_skillTable[44]`, pointer at 0x41b220). Kind 8, flags 0, recast field 30
(not effective). Active. Effect class `ColdArrowProjectile`: 0xb0 bytes, virtual table
0x518ef8, derived from `Projectile`. Ranger tree (level 5, prerequisite skill 75). Monsters
that build the projectile: MaleDarkElf 0x25c80c, Froglock 0x264d80, Goblin 0x26c0a0, Gremlin
0x26ebdc, Orc 0x2a25d8 (second constructor), Skeleton 0x2a727c (first constructor).
**Observed.**

#### Statistics

`SkillColdArrow_initStats` 0x2d6c94. **Observed.**

| Stat | Meaning (where used) | Tier 1: first, base, step | Tier 2 |
|---|---|---|---|
| 0 | damage of a **non-player** arrow (onHit 0x2d7da4). Not read on any player path found | 1, 40, 5.00084162 (0x40a006e5) | 1, 2, 2.0 (0x40000000) |
| 1 | flight speed, units per second (constructors) | 1, 498, 5.6045146 (0x40b3582f) | none |
| 2 | cold damage of a player's arrow: both values of the cold proc slot (onHit 0x2d7c30, 0x2d7c60) | 1, 6, 4.99997854 (0x409fffd3) | none |
| 3 | chill: half of it, in whole seconds, is added to the victim's chill timer (onHit 0x2d7e54) | 1, 3, 0.332002997 (0x3ea9fc4c) | none |
| 4 | mana cost | 1, 14, 2.99996996 (0x403fff82) | none |

Uses: speed slot 12 (1, level, owner, 10); cold damage slot 13 (2, level, &ownerHandle, 0);
non-player damage slot 13 (0, level, &ownerHandle, 0); chill slot 13 (3, level,
&ownerHandle, 10).

| Rank | stat 2 | stat 3 | chill added (s) | stat 1 | units/frame | stat 4 |
|---|---|---|---|---|---|---|
| 1 | 6 | 3 | 1 | 498 | 8.300 | 14 |
| 10 | 51 | 6 | 3 | 548 | 9.133 | 41 |
| 20 | 101 | 9 | 4 | 604 | 10.067 | 71 |

Stat 2 by rank: 6 + 5 x (rank - 1). Stat 3 by rank 1..20: 3 3 4 4 4 5 5 5 6 6 6 7 7 7 8 8 8
9 9 9 (halved toward zero: 1 1 2 2 2 2 2 2 3 3 3 3 3 3 4 4 4 4 4 4). Stat 1: 498 504 509 515
520 526 532 537 543 548 554 560 565 571 576 582 588 593 599 604. Tier 2 stat 0 at level L:
2L. Tier 1 stat 0 (unused): 40 + 5 x (rank - 1).

#### Cost and limits

Mana = `(float) getStat(4, rank)` = 14 + 3 x (rank - 1): 14, 41, 71 at ranks 1, 10, 20, paid
on the release frame. canUse: bow for a player. Gates of S.2; one arrow of ammunition. No
effective recast.

#### Behaviour

**Cast** 0x2d6db8: identical to 43's (height - 12.0, `pool_new(0xb0)`, slot 14 (level, 20),
`ColdArrowProjectile_ctor(obj, &pos, facing, caster, level, skill)`, return 0). **Observed.**

**Constructors** 0x2d6fb4 (facing) and 0x2d718c (direction vector), **Observed**:
`Projectile_ctor` (one shared draw); virtual table 0x518ef8; light record at +0x70 linked;
+0xac = skill; +0x64 = facing (or atan2 of the direction); radius +0x1c = **7.0** (constant);
+0x68 = level; s = (float) `getStatFor(1, level, owner, 10)`; velocity = (cos x s, sin x s,
0) or (dir x 1/|dir|) x s; +0x6c = 0 (age); +0x60 = 0; `obj_runEveryFrame`; launch sound.

**Run** 0x2d73c8 while +0x60 == 0: age += 1; `obj_moveAndCollide`; terrain: end(1); age >=
601: end(0); otherwise the light follows and 8 particles are emitted (7 + 1), each using two
points in the unit ball by rejection from the **own** generator (3 own draws per attempt).
Range 10 x speed: 4980 units at rank 1, 6040 at rank 20.

**onHit** 0x2d7aac (this, other), **Observed**:

1. Return when the owner handle is empty. Build an empty descriptor.
2. Owner is a player:
   - return when other has object flag 0x1000000; when other is a creature with creature
     flag 0x4000000; when `owner.slot20(other)` is 0;
   - frost burst effect at the arrow;
   - flags by level: <= 10: 0x40; 11..15: 0x40040; >= 16: 0x80040;
   - C = `getStatForHandle(2, level, &ownerHandle, 0)` (called twice, same value);
     descriptor: first empty or 0x20 slot = {type 0x20, v1 = 100, v2 = C, v3 = C} (100 %
     chance of cold for C..C);
   - `damage_apply(min = (float) record+0xd0, max = (float) record+0xd4, other, owner,
     100000, 0, 0, flags, &descriptor, 0)` with the owner's record at this moment.
3. Owner is not a player:
   - return when `owner.slot20(other)` is 0; frost burst effect;
   - D = `getStatForHandle(0, level, &ownerHandle, 0)`; **one own draw** u;
   - `damage_apply((float)D, (float)(D + trunc((float)D x 0.2 x (u x 1/65536))), other,
     owner, 100000, 0, 0, 0x40, null, 0)` (no cold slot).
4. When other is a creature: t = `getStatForHandle(3, level, &ownerHandle, 10)`;
   `Creature_setEffectTimer(other+0x344 + (float)(t / 2), other, 1, owner)`: the chill timer
   is **increased** by t / 2 seconds (integer halving; no cap at this site) and the effect
   source handle +0x360 is re-linked to the owner. This runs whatever `damage_apply`
   returned.
5. end(this, 2).

No "already ended" guard: every enemy overlapped on the same frame is hit (as 43).

What the skill adds for a player: the same always-hitting, unblockable full-weapon hit as 43
(attack 100000, flag 0x40, weapon record read at the hit), a guaranteed cold proc of C
(which, inside `damage_apply`, is reduced by cold resistance and itself adds to the chill
timer in proportion to damage over hit points), then t / 2 further seconds of chill. The
chill timer is what slows the victim (docs/creatures.md, field +0x344).

**end** 0x2d7ecc (this, reason): once; reason 0: nothing but the delete. reason 1 (terrain):
level x 10 + 27 particles around the point one radius ahead (own draws); reason 1 or 2:
level x 10 further particle pairs (own draws) and the impact sound; `obj_delete`; +0x60 = 1.

Field layout of `ColdArrowProjectile` (0xb0 bytes):

| Offset | Type | Meaning |
|---|---|---|
| +0x00..+0x53 | | `Projectile` part: flags +0x0c (0x4081), position +0x10, radius +0x1c (7.0), height extent +0x20 (72.0), own generator +0x44, virtual table +0x48, owner handle +0x4c, water-splash byte +0x50 |
| +0x54 | float[3] | velocity, units per second |
| +0x60 | s32 | ended (0 / 1) |
| +0x64 | s16 | facing |
| +0x68 | s32 | level (43 keeps its age here) |
| +0x6c | s32 | age in frames (43 keeps its level here) |
| +0x70..+0xab | light record | colour (89, 89, 130) twice at +0x7a and +0x82, radius 156.0 at +0x8c and +0x94, 0x382c598a (1/156^2) at +0x90 and +0x98, position at +0xa0 |
| +0xac | Skill* | the skill object |

#### Random draws

Shared A-E (release); 1 shared (constructor); own draws for the 8 flight particles every
frame; for a non-player owner 1 own draw per hit; `damage_apply`'s shared draws (with the
0x20 slot: the cold proc roll and its amount roll when the first hit roll succeeds); own
draws for the end particles.

#### Presentation only

Launch and impact sounds, flight and impact particles (static definitions 0x8e5730,
0x8e5780, 0x8e57d0), frost burst (`fx_spawn` id 10), light, draw 0x2d7980.

#### Per-machine state

Weapon record read at hit time (S.10). `owner + 0x3c8` only inside the is-player branch.
None found otherwise.

#### Functions read

| Address | Name | What |
|---|---|---|
| 0x2d6c20, 0x2d6c94, 0x2d6d40, 0x2d6db8, 0x2d6f80 | `SkillColdArrow_ctor`, `_initStats`, `_canUse`, `_cast`, `_manaCost` | |
| 0x2d6e84 | `SkillColdArrow_describeRank` | shows stats 2, 1 / 12, 3 |
| 0x2d6fb4, 0x2d718c | `ColdArrowProjectile_ctor`, `_ctor2` | |
| 0x2d73c8 | `ColdArrowProjectile_run` | |
| 0x2d7aac | `ColdArrowProjectile_onHit` | |
| 0x2d7ecc | proposed `ColdArrowProjectile_end` | particles, sound, delete |
| 0x118950 | `Creature_setEffectTimer` | whole |

#### Not determined

- `ColdArrowProjectile_draw` 0x2d7980 and the static initialiser 0x2d84cc (not read).
- How the chill timer becomes a slow amount and its cap (in `Creature_run`; see
  docs/creatures.md) was not re-read.
- Monster call sites other than MaleDarkElf and Skeleton.

### 45 poisonarrow — SkillPoisonArrow

#### Identity

Id 45, internal name poisonarrow. Skill class `SkillPoisonArrow`, virtual table 0x5190a0,
Skill object 0x6e26b8 (`g_skillTable[45]`, pointer at 0x41b224). Kind 8, flags 0, recast
field 30 (not effective). Active. Effect classes: `PoisonArrowProjectile` (0xb0 bytes,
virtual table 0x519010, derived from `Projectile`) and, where the arrow ends, one
`poisonGasSpell` (0x70 bytes, virtual table 0x50d500, constructor 0x202de8, a GameObject).
Ranger tree (level 15, prerequisite skill 44). Monsters that build the projectile:
MaleDarkElf 0x25c944, Froglock 0x264ce8 (second constructor). **Observed.**

#### Statistics

`SkillPoisonArrow_initStats` 0x2d86d0. **Observed.**

| Stat | Meaning (where used) | Tier 1: first, base, step | Tier 2 |
|---|---|---|---|
| 0 | player: flat amount added to both ends of the weapon damage range; non-player: the arrow's damage (onHit 0x2d932c head) | 1, 45, 4.99991798 (0x409fff54) | 1, 2, 1.99998689 (0x3fffff92) |
| 1 | flight speed, units per second (constructors) | 1, 366, 30.7386856 (0x41f5e8d4) | none |
| 2 | gas cloud radius = 12 x this value (end 0x2d9690) | 1, 1, 0.599899948 (0x3f19930b) | none |
| 3 | seconds: poison timer set on the victim (onHit) and life of the gas cloud (end 0x2d96c0) | 1, 3, 0.251001984 (0x3e808355) | none |
| 4 | mana cost | 1, 37, 2.99997687 (0x403fff9f) | none |

Uses: speed slot 12 (1, level, owner, 10); damage slot 13 (0, level, &ownerHandle, 0);
timer slot 12 (3, level, owner object, 10); cloud radius and life **slot 10** (2, level) and
(3, level): tier 1 at the stored level whoever the owner is.

| Rank | stat 0 | stat 1 | units/frame | stat 2 | cloud radius | stat 3 | cloud life (frames) | stat 4 |
|---|---|---|---|---|---|---|---|---|
| 1 | 45 | 366 | 6.100 | 1 | 12 | 3 | 180 | 37 |
| 10 | 90 | 643 | 10.717 | 6 | 72 | 5 | 300 | 64 |
| 20 | 140 | 950 | 15.833 | 12 | 144 | 8 | 480 | 94 |

Stat 0 by rank: 45 + 5 x (rank - 1). Stat 2 by rank 1..20: 1 2 2 3 3 4 5 5 6 6 7 8 8 9 9 10
11 11 12 12. Stat 3: 3 3 4 4 4 4 5 5 5 5 6 6 6 6 7 7 7 7 8 8. Stat 1: 366 397 427 458 489 520
550 581 612 643 673 704 735 766 796 827 858 889 919 950. Tier 2 stat 0 at level L: 2L for
L = 1..20 (the step is slightly below 2; recompute with the formula for higher levels).

#### Cost and limits

Mana = `(float) getStat(4, rank)` = 37 + 3 x (rank - 1): 37, 64, 94 at ranks 1, 10, 20
(`SkillPoisonArrow_manaCost` 0x2d8a30 forwards to slot 15 with (level, 1); the 1 is
ignored). Paid on the release frame. canUse: bow for a player. Gates of S.2; one arrow of
ammunition. No effective recast.

#### Behaviour

**Cast** 0x2d87f4: as 43's with slot 14 (level, 1) and `PoisonArrowProjectile_ctor` 0x2d8a64.
**Observed.**

**Constructors** 0x2d8a64 (facing) and 0x2d8c40 (direction vector): as 44's with virtual
table 0x519010, radius +0x1c = **5.0**, light colour (60, 132, 68) radius 120.0; +0x68 =
level, +0x6c = age, +0x60 = ended, +0x64 = facing, +0xac = skill; speed from stat 1 as
above. One shared draw (`Projectile_ctor`).

**Run** 0x2d8e80 while +0x60 == 0: age += 1; `obj_moveAndCollide`; terrain: end(1); age >=
601: end(0); otherwise light follows and 46 particles (two unit-ball rejections from the own
generator each). Range 10 x speed: 3660 units at rank 1, 9500 at rank 20.

**onHit** 0x2d932c (this, other), **Observed**:

1. Return when the owner handle is empty.
2. D = `getStatForHandle(0, level, &ownerHandle, 0)`; **one own draw** u (always).
3. Owner is not a player: return when `owner.slot20(other)` is 0;
   `damage_apply((float)D, (float)(D + trunc((float)D x 0.2 x (u x 1/65536))), other, owner,
   100000, 0, 0, 0x10040, null, 0)`.
4. Owner is a player: return when other has object flag 0x1000000, or is a creature with
   creature flag 0x4000000, or `owner.slot20(other)` is 0. flags by level: <= 10: 0x10040;
   11..15: 0x50040; >= 16: 0x90040.
   `damage_apply(min = (float)(record+0xd0 + D), max = (float)(record+0xd4 + D), other,
   owner, 100000, 0, 0, flags, null, 0)` (integer additions, then conversion; the record is
   read at this moment).
5. When other is a creature: t = `getStatFor(3, level, owner, 10)`;
   `Creature_setEffectTimer((float)t, other, 3, owner)`: the poison timer +0x34c is **set**
   to t seconds (not added) and the source handle re-linked. The per-tick amounts (+0x358,
   +0x35a) are not touched here; they are written only by a type-0x17 descriptor slot.
6. end(this, 2).

No "already ended" guard on onHit (multi-hit on one frame as 43), but end is guarded.

**end** 0x2d95c8 (this, reason); the reason is **not tested**, so a terrain hit, a creature
hit and the silent 600-frame expiry all do the same (**Observed**):

1. A flat ring of 213 particles (angle 0, 309, 618, ... below 65536; speed 9); no generator.
2. When the owner handle is set and `pool_new(0x70)` succeeds:
   `poisonGasSpell_ctor(obj, pos, lifeFrames = getStat(3, level) x 60, radius = getStat(2,
   level) x 12, 0, owner, damage = 5)`: **one shared draw** (GameObject constructor).
3. Impact sound; `obj_delete`; +0x60 = 1.

**The gas cloud** (`poisonGasSpell`, run 0x1fd0f0, **Observed**): fields +0x4c owner handle,
+0x50 position copy, +0x5c end frame = creation frame + lifeFrames, +0x60 s32 target radius
(at least 10), +0x64 float current radius (starts 10.0), +0x68 the unused fifth argument,
+0x6c damage; object flags |= 3. Each frame before the end frame: current radius += 0.5
while below the target; (target radius / 10) particles (own generator); and on every frame
where `g_simFrame % 30 == 0` (global counter, not relative to creation) with a live owner:
box query of position +/- trunc(current radius) on all three axes (at most 63 objects); for
each object the owner's slot 20 accepts: descriptor {type 0x17, v1 = 5, v2 = 5, v3 = 0} and
`damage_apply(0.0, 0.0, object, owner, 100000, 0, 0, 0x1000040, &descriptor, 0)`. Inside
`damage_apply` the 0x17 slot writes 5 to the victim's +0x358 and +0x35a and sets the poison
timer to 5 - 5 x poison resistance seconds (docs/gameplay.md 2.2). At the end frame the
cloud destroys itself.

The poison itself (`Creature_run` 0x112948, **Observed** at its poison block): while +0x34c
> 0 it loses 1/60 per frame, and on frames with `g_simFrame & 31 == 0` (not for the
prediction copy) the creature damages itself: `damage_apply((s16 +0x358) x 0.1, (s16 +0x35a)
x 0.1, self, self, 100000, 0, 0, 0x1080c040, null, 0)`, i.e. 0.5 per tick after a cloud
tick has written 5.

What the skill adds for a player: the always-hitting, unblockable weapon hit of 43 with D
added to both ends of the range and no elemental slot; a poison timer of t seconds; and a
gas cloud at the end point for t seconds that re-poisons enemies standing in it twice a
second. A monster's arrow leaves the cloud sized by the **tier-1** table at the uncapped
level-wide monster level.

Field layout of `PoisonArrowProjectile` (0xb0 bytes):

| Offset | Type | Meaning |
|---|---|---|
| +0x00..+0x53 | | `Projectile` part: flags +0x0c (0x4081), position +0x10, radius +0x1c (5.0), height extent +0x20 (72.0), own generator +0x44, virtual table +0x48, owner handle +0x4c, water-splash byte +0x50 |
| +0x54 | float[3] | velocity, units per second |
| +0x60 | s32 | ended (0 / 1) |
| +0x64 | s16 | facing |
| +0x68 | s32 | level |
| +0x6c | s32 | age in frames |
| +0x70..+0xab | light record | colour (60, 132, 68) at +0x7a, radius 120.0 at +0x8c, position at +0xa0 (other light fields not listed) |
| +0xac | Skill* | the skill object |

Field layout of `poisonGasSpell` (0x70 bytes, a GameObject):

| Offset | Type | Meaning |
|---|---|---|
| +0x0c | u32 | flags \|= 3 |
| +0x4c | handle | owner |
| +0x50 | float[3] | copy of the creation position |
| +0x5c | s32 | end frame |
| +0x60 | s32 | target radius (at least 10) |
| +0x64 | float | current radius, starts 10.0, +0.5 per frame |
| +0x68 | s32 | fifth constructor argument (0 here); not read by the run function |
| +0x6c | s32 | damage value copied into the 0x17 slot |

#### Random draws

Shared A-E (release); 1 shared (arrow constructor); own draws for 46 particles per flight
frame; 1 own draw per touched object with a live owner; `damage_apply`'s shared draws (null
descriptor); 1 shared (gas cloud constructor) at the end; then per cloud frame own draws
for particles and, on tick frames, `damage_apply`'s shared draws for each enemy in the box
(min == max == 0, so no base roll; the 0x17 slot draws nothing).

#### Presentation only

Launch and impact sounds, flight particles (static definitions 0x8e5820, 0x8e5870), the end
ring (0x8e58c0), cloud particles (0x871088), light, draw 0x2d91f8.

#### Per-machine state

Weapon record read at hit time (S.10). The cloud tick is keyed to the global frame counter.
`owner + 0x3c8` only inside the is-player branch. None found otherwise.

#### Functions read

| Address | Name | What |
|---|---|---|
| 0x2d865c, 0x2d86d0, 0x2d877c, 0x2d87f4, 0x2d8a30 | `SkillPoisonArrow_ctor`, `_initStats`, `_canUse`, `_cast`, `_manaCost` | |
| 0x2d88c0 | `SkillPoisonArrow_describeRank` | shows stats 0, 2, 3 (two texts, by stat 2 == 1) |
| 0x2d8a64, 0x2d8c40 | `PoisonArrowProjectile_ctor`, `_ctor2` | |
| 0x2d8e80 | `PoisonArrowProjectile_run` | |
| 0x2d932c | `PoisonArrowProjectile_onHit` | |
| 0x2d95c8 | proposed `PoisonArrowProjectile_end` | ring, gas cloud, delete |
| 0x202de8, 0x1fd0f0 | `poisonGasSpell_ctor`, `_run` | whole |
| 0x112948 | `Creature_run` | poison block only |

#### Not determined

- What damage flag bits 0x10000 (arrow) and 0x1000000 / 0x10000000 / 0x800000 / 0xc000 (cloud
  and tick; partly documented in docs/gameplay.md 2.4) do in the take-damage
  implementations.
- `PoisonArrowProjectile_draw` 0x2d91f8, the static initialiser 0x2d9764; the Froglock call
  site.
- The victim's poison per-tick amounts when it was never touched by a 0x17 slot (the arrow
  sets only the timer; the fields then hold whatever they held, 0 for a fresh creature:
  **Inferred** from the stores found, not from the creature constructor).

### 46 multifire — SkillMultiFire

#### Identity

Id 46, internal name multifire. Skill class `SkillMultiFire`, virtual table 0x5191b8, Skill
object 0x6e2720 (`g_skillTable[46]`, pointer at 0x41b228). Kind 8, flags 0, recast field 30
(not effective). Active. Ranger tree (level 3, prerequisite skill 48).

Objects created, **Observed**:

- by the Skill's cast (player, or any caster reaching slot 2): one `LightEffect` (0xbc bytes,
  constructor 0x201bd8) and N `MissileWeapon` objects (0x1c8 bytes, virtual table 0x50e5a0,
  kind 0), the same class as a plain arrow (S.8);
- by MaleDarkElf only (0x25c954-0x25cad0): N `MultiFireProjectile` objects (0x78 bytes,
  virtual table 0x519128, constructor 0x2da164), a separate `Projectile`-derived class that
  the Skill's cast never creates.

#### Statistics

`SkillMultiFire_initStats` 0x2d995c. **Observed.**

| Stat | Meaning (where used) | Tier 1: first, base, step | Tier 2: first, base, step |
|---|---|---|---|
| 0 | player: total percent of weapon damage, split over the arrows (cast 0x2d9ce8; projectile onHit 0x2da6a8). Non-player: damage per arrow | 1, 120, 10.0008478 (0x41200379) | 1, 2, 2.0 (0x40000000) |
| 1 | arrow speed, units per second (cast 0x2d9c84; projectile ctor 0x2da200) | 1, 478, 7.29491377 (0x40e96fef) | 1, 450, 4.0 (0x40800000) |
| 2 | number of arrows (cast 0x2d9c28; release block 0x1a9040; MaleDarkElf 0x25c984) | 1, 2, 0.201001987 (0x3e4dd377) | 1, 2, 0.099999994 (0x3dcccccc) |
| 3 | unused (always 0) | | none |
| 4 | mana cost | 1, 5, 1.99997699 (0x3fffff3f) | none |

Cast: slot 12 with (stat, level, caster, 10) for stats 2, 1, 0. Release block: slot 10
(2, rank). MaleDarkElf: slot 11 (2, L, 10); its projectiles: slot 13 with cap 10 for stats 1
and 0, slot 10 for stat 2 in the unused player branch.

| Rank | stat 0 (%) | stat 2 (arrows) | % per arrow | stat 1 | units/frame | stat 4 |
|---|---|---|---|---|---|---|
| 1 | 120 | 2 | 60.0 | 478 | 7.967 | 5 |
| 10 | 210 | 4 | 52.5 | 544 | 9.067 | 23 |
| 20 | 310 | 6 | 51.67 | 617 | 10.283 | 43 |

Stat 0 by rank: 120 + 10 x (rank - 1). Stat 2 by rank 1..20: 2 2 2 3 3 3 3 3 4 4 4 4 4 5 5 5
5 5 6 6. Stat 1: 478 485 493 500 507 514 522 529 536 544 551 558 566 573 580 587 595 602 609
617. Tier 2 at level L (limited to 10 where the cap applies): stat 0 = 2L; stat 1 = 450 +
4 x (L - 1); stat 2 = 2 for L <= 5, 3 for L = 6..15, 4 for L = 16..20.

#### Cost and limits

Mana = `(float) getStat(4, rank)` = 5 + 2 x (rank - 1): 5, 23, 43 at ranks 1, 10, 20; paid on
the release frame. canUse: bow for a player. Gates of S.2. Ammunition: the release block
subtracts `getStat(2, rank)` arrows (2..6), clamped at 0; the number of arrows fired is not
reduced when the stack is shorter (S.4 step 10). No effective recast.

#### Behaviour

**Cast** `SkillMultiFire_cast(skill, level, caster, pos*, facing)` 0x2d9a90, **Observed**,
in order:

1. P0 = copy of pos. lvl = slot 14 (level, 20) (= level).
2. `pool_new(0xbc)`; on success `LightEffect_ctor` with colour arguments (124.0, 115.0,
   204.0), position P0 + (0, 0, 20.0), and stack floats 130.0916 (0x43021771), 60.0, 0.5,
   1.0: a short light flash (presentation, but **one shared draw** in its constructor).
3. N = `getStatFor(2, lvl, caster, 10)`.
4. a0 = (s16)(facing - trunc((float)N x 0.5 x 534.5 (0x4405a000))).
5. s = (float) `getStatFor(1, lvl, caster, 10)`.
6. Caster is a player (flag 0x40), 0x2d9ca4-0x2d9dc8:
   - W = primary weapon of the active set (record +0x4434 + 4 x set);
   - pct = `getStatFor(0, level, caster, 10)`; f = ((float)pct x 0.01 (0x3c23d70a)) /
     (float)N (multiply, then divide, single precision);
   - dmin = round((float) record+0xd0 x f), dmax = round((float) record+0xd4 x f), round half
     away from zero; the record is read **now**, at the release;
   - damage flags = 0x40000; weapon rating = `item_getModifiedField1a(W)`; item flags = low
     32 bits of W's flag word.
7. Caster is not a player, 0x2d9dd0-0x2d9ec8:
   - base = `getStatFor(0, level, caster, 10)` (tier 2, level limited to 10); dmin = base;
   - t = (float)base x 0.2 (0x3e4ccccc); **cosmetic draw 1**: only the sign of t x (draw x
     1/65536) is tested (it is never negative, so the rounding term is +0.5); **cosmetic draw
     2**: dmax = base + trunc(t x (draw x 1/65536) + 0.5);
   - damage flags = 0, weapon rating = 0, item flags = 0.
8. For i = 0 .. N-1 (nothing when N <= 0), angle a_i with a_(i+1) = (s16)(a_i + 1069):
   - velocity = (cos16(a_i) x s, sin16(a_i) x s, 0.0);
   - **shared draw**: spawn = (P0.x, P0.y, (P0.z - (draw x 1/65536) x 6.0) + (-6.0)), i.e.
     6 to 12 below the cast position;
   - `pool_new(0x1c8)`; on success `MissileWeapon_ctor(obj, kind 0, g_itemModels[+8],
     g_itemModels[+0xc], &spawn, &velocity, facing = a_i - 0x4000, owner = caster; launch
     sample 0, impact sample 0, dmin, dmax, weapon rating, item flags, attack rating 10000,
     damage flags, item 0)` (one shared draw in the constructor).
9. A sound on the caster. Return 0.

Fan geometry: arrow i flies at facing - trunc(267.25 x N) + 1069 x i (16-bit units; 1069
units = 5.87 degrees). Offsets from the cast facing: N = 2: -534, +535; N = 3: -801, +268,
+1337; N = 4: -1069, 0, +1069, +2138; N = 5: -1336, -267, +802, +1871, +2940; N = 6: -1603,
-534, +535, +1604, +2673, +3742. The fan is centred only for N = 2; for larger N it leans to
the positive-angle side (**Observed** arithmetic; whether intended is Unknown).

**Each arrow** is a kind-0 `MissileWeapon` and behaves exactly as in S.8: radius 12, height
extent 72, speed s units per second in a straight level line, at most 300 frames (range 5 x
s: 2390 units at rank 1, 3085 at rank 20), stopped by terrain or any solid non-creature
object, passes through creatures its owner does not call enemies. On touching an enemy
creature (owner a player), in order: the two PenetratingArrows draws (unblockable, pierce),
the stick-in-target link (unless piercing), the deflection draw against the target's
Dodge-type chance, then

`damage_apply(min = (float)dmin, max = (float)dmax, victim, attacker = owner, attack = 10000,
weapon rating, item flags, flags = 0x40000 | (unblockable ? 0x40 : 0), descriptor = null,
noCrit = 0)`.

So, against a plain bow shot: the arrows carry a fixed share of the weapon damage record
taken at the release; attack rating is the constant 10000 instead of the player's rating (hit
chance sqrt(10000 / AC) capped at 1, damage scale min(10000 / (AC / 2), 1)); the bow's item
modifiers are **not** applied (null descriptor); the corpse knock-back flag 0x40000 replaces
the weapon's damage-class bits (so the thorns / undead-shield class test `flags & 0xd` is
false); PenetratingArrows, sticking, deflection, blocking and critical hits work as for a
plain arrow.

**MaleDarkElf volley** (weapon variant 6), 0x25c954-0x25cad0, **Observed**: L = `(int)
g_levelMonsterLevel`; N = `getStatTier2(2, L, 10)`; aim = (s16)(0x4000 - atan2_16(aim point
- start point)), clamped to facing +/- 1000 when the (s16) difference exceeds that; a0 =
(s16)(aim - trunc((float)N x 0.5 x 500.0)); N times: `pool_new(0x78)` and
`MultiFireProjectile_ctor(obj, pos = monster + (0, 0, 0.5 x height + 12), facing a_i, owner,
L, skill)`, a_(i+1) = (s16)(a_i + 1000).

`MultiFireProjectile_ctor` 0x2da164: `Projectile_ctor` (one shared draw); radius 8.0; +0x64
facing; +0x70 skill; +0x68 level; s = `getStatForHandle(1, level, &ownerHandle, 10)`;
velocity = (cos x s, sin x s, 0); +0x6c = 0; +0x60 = 0; a trail (+0x74);
`obj_runEveryFrame`.

`MultiFireProjectile_run` 0x2da2bc while +0x60 == 0: trail point; age +0x6c += 1;
`obj_moveAndCollide`; terrain: end(1); age >= 601: end(0); otherwise 10 particles, each
taking own draws (a point in the unit ball by rejection, three own draws per attempt, then
one more own draw).

`MultiFireProjectile_onHit` 0x2da610 (this, other): return when the owner handle is empty.
Owner not a player: return when `owner.slot20(other)` is 0; D = `getStatForHandle(0, level,
&ownerHandle, 10)`; t = (float)D x 0.2; **own draw 1** (sign test only), **own draw 2**: hi =
D + trunc(t x (draw x 1/65536) + 0.5); `damage_apply((float)D, (float)hi, other, owner,
100000, 0, 0, 0x40000, null, 0)`; end(2). Owner a player (no creator of this exists):
return when other has object flag 0x1000000 or 0x40, or creature flag 0x4000000; **no slot-20
test**; f = (stat 0 x 0.01) / `getStat(2, level)`; min/max = round(record +0xd0 / +0xd4 x f);
same `damage_apply`. As with 43, no "already ended" guard: every overlapping enemy on that
frame is hit.

`MultiFireProjectile` end 0x2da928 (this, reason): once: trail released; when reason != 0 one
own draw picks one of four impact sounds and an impact effect is spawned; `obj_delete`;
+0x60 = 1.

Field layout of `MultiFireProjectile` (0x78 bytes; the `MissileWeapon` layout is in S.8):

| Offset | Type | Meaning |
|---|---|---|
| +0x00..+0x53 | | `Projectile` part: flags +0x0c (0x4081), position +0x10, radius +0x1c (8.0), height extent +0x20 (72.0), own generator +0x44, virtual table +0x48, owner handle +0x4c, water-splash byte +0x50 |
| +0x54 | float[3] | velocity, units per second |
| +0x60 | s32 | ended (0 / 1) |
| +0x64 | s16 | facing |
| +0x68 | s32 | level |
| +0x6c | s32 | age in frames |
| +0x70 | Skill* | the skill object |
| +0x74 | ptr | trail (presentation) |

#### Random draws

Player shot: shared A-E (S.4); 1 shared (LightEffect constructor, when allocated); per arrow
1 shared (spawn height; made even when the allocation then fails) + 1 shared (constructor).
Per arrow in flight: none (level flag 0x100 clear). Per touched enemy creature: 2 shared
(PenetratingArrows), 1 shared (deflection), then `damage_apply`'s own sequence. A terrain hit
over water: 1 own draw.

Non-player caster through the Skill's cast: the same, plus the 2 cosmetic draws of step 7.

MaleDarkElf volley: 1 shared per projectile (constructor); own draws for particles each
frame; 2 own draws per hit; 1 own draw for the impact sound.

#### Presentation only

Light flash at the caster, shot sound, arrow trails, ground/spark impact effects, the
stuck-arrow model that follows the target's model sample point.

#### Per-machine state

- **Verified: docs/skills.md "Per-machine state (b) item 1".** For a caster without object
  flag 0x40 the maximum damage stored in every arrow (stack argument written at 0x2d9fb4) is
  base + trunc(base x 0.2 x u + 0.5) with u from the **cosmetic** generator 0x404460 (two
  steps, the first only for a sign test), 0x2d9e08-0x2d9ec8. The minimum is base. The player
  branch (0x2d9ca4-0x2d9dc8) uses the weapon damage record and no generator. If the
  non-player branch runs, the arrows' maximum damage differs between machines whose cosmetic
  seeds differ. Reachability: the only monster user (MaleDarkElf) does not call the cast;
  the weapon-proc path (descriptor type 0x29) would reach it for a non-player attacker.
  Whether any item or monster descriptor names skill 46 is **Unknown**.
- The player branch reads the weapon record at the release, inside the simulation step; the
  hazard of S.10 applies only if the record was left stale by the stats page.
- `caster + 0x3c8` is read only inside the is-player branch.

#### Functions read

| Address | Name | What |
|---|---|---|
| 0x2d98e8 | `SkillMultiFire_ctor` | |
| 0x2d995c | `SkillMultiFire_initStats` | |
| 0x2d9a18 | `SkillMultiFire_canUse` | |
| 0x2d9a90 | `SkillMultiFire_cast` | whole, from the disassembly |
| 0x2da130 | `SkillMultiFire_manaCost` | |
| 0x2da164 | `MultiFireProjectile_ctor` | |
| 0x2da2bc | `MultiFireProjectile_run` | |
| 0x2da610 | `MultiFireProjectile_onHit` | |
| 0x2da928 | proposed `MultiFireProjectile_end` | |
| 0x150ee4, 0x15153c, 0x152a18, 0x153314 | `MissileWeapon_*` | S.8 |
| 0x25c954-0x25cad0 | MaleDarkElf volley | |

#### Not determined

- `SkillMultiFire_describeRank` 0x2da048 and `MultiFireProjectile_draw` 0x2da550 (not read).
- The arguments of `LightEffect_ctor` beyond those listed (their meaning; presentation).
- Whether the non-player branch of the cast is reachable in the shipped data.
- What happens when a type-0x29 proc casts this skill for a player whose active primary
  weapon pointer is null (step 6 passes it to `item_getModifiedField1a` without a test).

### 47 explodearrow — SkillExplodeArrow

#### Identity

Id 47, internal name explodearrow. Skill class `SkillExplodeArrow`, virtual table 0x5192d0,
Skill object 0x6e2788 (`g_skillTable[47]`, pointer at 0x41b22c). Kind 8, flags 0, recast
field 30 (not effective). Active. Effect class `ExplodeArrowProjectile`: 0x74 bytes, virtual
table 0x519240, derived from `Projectile`; plus one `LightEffect` (0xbc) at the explosion.
Ranger tree (level 20, prerequisite skill 43). Monsters that build the projectile: Goblin
0x26c120, Gremlin 0x26ec5c, Orc 0x2a2708 (second constructor), Skeleton 0x2a72fc (first
constructor). **Observed.**

#### Statistics

`SkillExplodeArrow_initStats` 0x2dab70. **Observed.**

| Stat | Meaning (where used) | Tier 1: first, base, step | Tier 2: first, base, step |
|---|---|---|---|
| 0 | explosion damage (explode 0x2db81c) | 1, 150, 8.99988079 (0x410fff83) | 1, 2, 2.0 (0x40000000) |
| 1 | flight speed, units per second (constructors) | 1, 417, 12.8468828 (0x414d8cd5) | 1, 400, 5.0 (0x40a00000) |
| 2 | half edge of the explosion box (explode 0x2db780) | 1, 38, 2.9998188 (0x403ffd08) | 1, 45, 1.0 (0x3f800000) |
| 3 | unused (always 0) | | none |
| 4 | mana cost | 1, 55, 2.99996686 (0x403fff75) | none |

All three uses go through slot 12 `getStatFor(stat, level, ownerObject, cap)`: cap 10 for
stats 1 and 2, cap 0 (no limit) for stat 0. Player: tier 1 at the rank. Other: tier 2.

| Rank | stat 0 | max of the damage range | stat 1 | units/frame | stat 2 | stat 4 |
|---|---|---|---|---|---|---|
| 1 | 150 | 179 | 417 | 6.950 | 38 | 55 |
| 10 | 231 | 277 | 533 | 8.883 | 65 | 82 |
| 20 | 321 | 385 | 661 | 11.017 | 95 | 112 |

(The maximum shown is D + trunc(0.2 x D x 65535/65536).) Stat 0 by rank: 150 + 9 x (rank -
1). Stat 2: 38 + 3 x (rank - 1). Stat 1 by rank 1..20: 417 430 443 456 468 481 494 507 520
533 545 558 571 584 597 610 623 635 648 661. Tier 2 at level L: stat 0 = 2L (unlimited);
stat 1 = 400 + 5 x (min(L,10) - 1); stat 2 = 45 + (min(L,10) - 1).

#### Cost and limits

Mana = `(float) getStat(4, rank)` = 55 + 3 x (rank - 1): 55, 82, 112 at ranks 1, 10, 20
(`SkillExplodeArrow_manaCost` 0x2dae80 forwards to slot 15 with (level, 9); the 9 is
ignored). Paid on the release frame. canUse: bow for a player. Gates of S.2; one arrow of
ammunition per shot. No effective recast.

#### Behaviour

**Cast** 0x2daca8 (skill, level, caster, pos*, facing), **Observed**: lvl = slot 14 (level,
9) (= level); pos.z -= 12.0; `pool_new(0x74)`; on success
`ExplodeArrowProjectile_ctor(obj, &pos, facing, caster, lvl, skill)`. Returns 0.

**First constructor** 0x2daeb4 (obj, pos*, s16 facing, owner, level, skill): `Projectile_ctor`
(one shared draw); +0x64 = facing; virtual table 0x519240; radius +0x1c = 8.0; +0x70 = skill;
+0x68 = level; s = (float) `getStatFor(1, level, owner object read back through the handle
+0x4c, 10)`; velocity = (cos16 x s, sin16 x s, 0); +0x6c = 0 (age); +0x60 = 0;
`obj_runEveryFrame`; launch sound. The owner handle is dereferenced without a null test: a
null owner faults (**Observed** 0x2daeb4 body; every caller passes an owner).

**Second constructor** 0x2dafe0 (obj, pos*, dir*, owner, level, skill): the same with +0x64 =
`math_atan2_16(dir.y, dir.x)` and velocity = (dir x 1/|dir|) x s on all three components.

**Run** 0x2db17c while +0x60 == 0:

```
age (+0x6c) += 1
r = obj_moveAndCollide(this, velocity)      # onHit may run inside and explode
if r & 1:          explode(this, 1)         # terrain
elif age >= 601:   explode(this, 0)         # silent removal, no explosion
else:              6 trail particles, each: a point in the unit ball by rejection
                   (3 own draws per attempt) and 1 more own draw
```

Note that the particle loop still runs on the frame an overlap exploded the arrow (the
ended flag is not re-tested), consuming own draws that nothing uses afterwards.

**onHit** 0x2db4f0 (this, other): `explode(this, 2)` with no test of what `other` is. The
arrow therefore explodes on the first frame it overlaps **any** object that
`obj_moveAndCollide` reports: any object without flags 0x201 and 0x20000000 that is not the
owner; allies, other players, containers and solid props included.

**explode** 0x2db50c (this, reason), **Observed**:

1. Return when +0x60 != 0.
2. reason == 0: go to step 9.
3. One **own draw**: (draw & 3) + 1 picks one of four impact sounds; an impact effect; two
   sounds; a ring burst of size max(level x 0.1, 1.0) (cosmetic generator).
4. `pool_new(0xbc)`; on success `LightEffect_ctor` (colour 255, 10, 10; stack floats 120,
   60, 0.5, 0.25) at the position: **one shared draw**.
5. `camera_shake((float)(level / 2), 0)` (integer halving toward zero).
6. Owner handle empty: go to step 9 (no damage).
7. R = (float) `getStatFor(2, level, owner, 10)`.
   K (knock-back flag bits): level <= 5: 0; 6..11: 0x40000; >= 12: 0x80000; but for a
   non-player owner at level >= 12 one **own draw** is made and K = 0x80000 when its low bit
   is 0, else 0x40000.
   D = `getStatFor(0, level, owner, 0)`.
8. Box query `world_collectObjectsInBox(pos - (R, R, R), pos + (R, R, R), out, 128)` (at
   most 127 objects). For each object o in query order:
   - o is a creature and o is not the owner: skip it when `owner.slot20(o)` is 0;
   - o is the owner (creature or not): only when the 3-D distance between the two positions
     is < R x 0.5: `damage_apply(0.0, 0.0, o, attacker = this, 100000, 0, 0, K, null, 0)`;
   - otherwise (enemy creature, or any non-creature object the query returned): one **own
     draw** u; hi = D + trunc((float)D x 0.2 x (u x 1/65536));
     `damage_apply(0.0, 0.0, o, attacker = this, 100000, 0, 0, K, null, 0)`, then
     `damage_apply((float)D, (float)hi, o, attacker = owner, 100000, 0, 0, 0x840, null, 0)`.
9. `obj_delete(this)`; +0x60 = 1.

Properties that follow, **Observed**:

- The damage does **not** use the player's weapon damage, attack rating, Archery, the bow's
  modifiers or dexterity. It is D .. 1.2 D from the skill table alone, with attack 100000
  (always hits) and flag 0x40 (cannot be blocked).
- The area is the box query's shape: an axis-aligned box of half edge R around the impact
  point, widened by each object's own radius in x/y and height extent in z by the query; no
  distance test, no falloff. Only the owner's self-hit has a distance test.
- Every enemy takes two `damage_apply` calls: a zero-damage one credited to the projectile
  carrying only the knock-back bits (it can be blocked, flag 0x40 clear), then the damage
  one credited to the owner with flags 0x40 | 0x800. What a victim's take-damage does with
  a zero amount and with bit 0x800 was not traced.
- Non-creature objects in the box are not filtered at all (no slot-20 test): both calls are
  made on them; `damage_apply` handles a non-creature victim by one shared draw and a direct
  take-damage call. The arrow itself is not excluded from the loop.
- A silent expiry (600 frames) does not explode. Range: 10 x speed = 4170 units at rank 1,
  6610 at rank 20.

Field layout of `ExplodeArrowProjectile` (0x74 bytes):

| Offset | Type | Meaning |
|---|---|---|
| +0x00..+0x53 | | `Projectile` part: flags +0x0c (0x4081), position +0x10, radius +0x1c (8.0), height extent +0x20 (72.0), own generator +0x44, virtual table +0x48, owner handle +0x4c, water-splash byte +0x50 |
| +0x54 | float[3] | velocity, units per second |
| +0x60 | s32 | ended (0 / 1) |
| +0x64 | s16 | facing |
| +0x68 | s32 | level |
| +0x6c | s32 | age in frames |
| +0x70 | Skill* | the skill object |

#### Random draws

Shared A-E (release block); 1 shared (constructor); per flight frame own draws for six
particles (3 per rejection attempt + 1, each); at the explosion: 1 own (sound), 1 shared
(LightEffect, when allocated), for a non-player owner at level >= 12 1 own (knock-back bit);
then per damaged object 1 own (damage spread) followed by the shared draws of two
`damage_apply` calls (for a creature: with min == max == 0 the first call skips the base
roll; with a null descriptor the four proc rolls are still drawn when the first hit roll
succeeds; a non-creature victim costs exactly one shared draw per call).

#### Presentation only

Launch and impact sounds, trail particles (static definition at 0x8e5960, initialiser
0x2dba94), impact effect, ring burst, light flash, camera shake, draw 0x2db430.

#### Per-machine state

- `camera_shake` is local presentation. The ring burst uses the cosmetic generator.
- The explosion passes **every** object the box query returns to `damage_apply`, and each
  non-creature object costs shared draws. If an object that exists on one machine only (a
  purely local presentation object linked into the object grid) lies inside the box, the
  shared generator would step a different number of times there. No such object class was
  identified in this pass; **Inferred hazard, not confirmed**.
- No read of +0x3c8 on a non-player; the only is-player test (0x2db7b4) guards the extra own
  draw.

#### Functions read

| Address | Name | What |
|---|---|---|
| 0x2daafc | `SkillExplodeArrow_ctor` | |
| 0x2dab70 | `SkillExplodeArrow_initStats` | |
| 0x2dac30 | `SkillExplodeArrow_canUse` | |
| 0x2daca8 | `SkillExplodeArrow_cast` | |
| 0x2dae80 | `SkillExplodeArrow_manaCost` | |
| 0x2daeb4 | `ExplodeArrowProjectile_ctor` | |
| 0x2dafe0 | `ExplodeArrowProjectile_ctor2` | |
| 0x2db17c | `ExplodeArrowProjectile_run` | |
| 0x2db4f0 | `ExplodeArrowProjectile_onHit` | |
| 0x2db50c | proposed `ExplodeArrowProjectile_explode` | effects, area damage, delete |
| 0x26c0f0-0x26c124, 0x2a72cc-0x2a7300 | Goblin and Skeleton call sites | |

#### Not determined

- `SkillExplodeArrow_describeRank` 0x2dad68 and `ExplodeArrowProjectile_draw` 0x2db430.
- The effect of damage flag 0x800 and of a zero-amount hit in the take-damage
  implementations.
- Which object classes can appear in the box query besides creatures (decides the exact
  shared-draw count of an explosion).

### 48 archery — SkillArchery

#### Identity

Id 48, internal name archery. Skill class `SkillArchery`, virtual table 0x519358, Skill
object 0x6e27f0 (`g_skillTable[48]`, pointer at 0x41b230). Kind 3 (passive), flags 0,
recast field 30 (never used). canUse and cast are the base implementations (0x3c8218,
0x3c8220); it creates nothing. Ranger tree (level 1, no prerequisite); prerequisite of
skill 46. **Observed** (constructor 0x2dbb44, virtual table).

#### Statistics

`SkillArchery_initStats` 0x2dbbb8. **Observed.**

| Stat | Meaning | Tier 1: first, base, step | Tier 2 |
|---|---|---|---|
| 0 | percent of bow weapon damage added (0x2dbcac, used at 0x1b735c) | 1, 15, 4.99994993 (0x409fff97) | none |
| 4 | "mana cost" (never charged: the skill cannot be cast) | 1, 1, 1.0 (0x3f800000) | none |

Stat 0 by rank 1..20: 15 20 25 30 35 40 45 50 55 60 65 70 75 80 85 90 95 100 105 110 (rank
1: 15, rank 10: 60, rank 20: 110).

#### Cost and limits

None. Passive: always on while the player has a rank and the active primary weapon's
animation class is 4 (bow).

#### Behaviour

`SkillArchery_getStat0Fraction(skill, rank)` 0x2dbcac = `(float) getStat(0, slot14(rank,
20)) x 0.01` (0x3c23d70a); 0.0 at rank 0. **Observed.**

Its only caller is `Player_recalcDamage` at 0x1b735c (cross-reference search), inside the
branch taken when the weapon item's animation class byte (definition +0x1e) is 4, with rank
= `player_getSkillRank(slot, 48)`. There, with f the fraction (0x1b7364-0x1b73f8):

```
min = record+0xd0;  min += trunc(min * f +/- 0.5)     # round half away from zero
max = record+0xd4;  max += trunc(max * f +/- 0.5)     # uses the original max, not the new min
```

Both values at that point already contain the item's damage range (with the elemental
modifier amounts when the caller asked for them) and dexterity / 4 (S.6 steps 2-3). The
attack rating (+0xcc) is **not** multiplied. Later steps of the same function multiply the
result further (S.6 step 5).

So the fraction multiplies the weapon damage record of a bow, and through it: plain arrows
(record read at the release), skills 43, 44, 45 (record read at the hit) and 46 (record read
at the release). It does not affect 47 (which never reads the record), nor the elemental
amounts those skills add from their own tables.

Worked example, rank 10 (f = 0.6), record 20..30 before the step: 20 + 12 = 32, 30 + 18 =
48.

Related, **Observed**: `Player_meleeHit` calls `Player_recalcDamage(player, 0, 0)` (null
weapon: unarmed numbers) when the weapon class is 4 or the item's class is 6 (0x1b6db0-
0x1b6ddc), so a melee swing made while holding a bow gets no Archery bonus and leaves
unarmed numbers in the record until the next per-frame rebuild.

#### Random draws

None.

#### Presentation only

`SkillArchery_describeRank` 0x2dbbf0 (menu text).

#### Per-machine state

None in the skill. The record it feeds is rebuilt from draw code by the stats page (S.10).

#### Functions read

| Address | Name | What |
|---|---|---|
| 0x2dbb44 | `SkillArchery_ctor` | |
| 0x2dbbb8 | `SkillArchery_initStats` | |
| 0x2dbc78 | `SkillArchery_manaCost` | slot 15 forward |
| 0x2dbcac | `SkillArchery_getStat0Fraction` | |
| 0x1b7158 | `Player_recalcDamage` | whole |

#### Not determined

- `SkillArchery_describeRank` 0x2dbbf0 was not read.
- Whether the rank returned by `player_getSkillRank` can include item bonuses above 20.

### 49 bash — SkillBash

#### Identity

| Item | Value | Evidence |
|---|---|---|
| Skill id | 49 (`g_skillTable[49]` at 0x41b234 → object 0x6e2858) | Observed |
| Internal name | bash | Observed: constructor 0x2de23c |
| Skill class | `SkillBash`, virtual table 0x5195e0 | Observed |
| Kind / flags / recast | 0 / 0 / 30 frames | Observed |
| Effect class | `SpellBash`, 0x28 bytes, virtual table 0x5195b0 (slot 1 destructor 0x3ce650, slot 2 run 0x2de7dc, slot 4 `SpellBash_getField18` 0x2defcc; slot 3 base) | Observed |
| Who has it | barbarian tree (base level 5, passive mask 0x10); shadowknight tree (base level 15, needs skill 5). No monster | Tree tables; `docs/monsters.md` §6 |
| Slot overrides | 1 canUse 0x2de334, 2 cast 0x2de3bc, 4 describeRank 0x2de484, 5 manaCost 0x2de60c, 7 icon 0x3ce62c, 9 initStats 0x2de2a8 | `vtab.py show 5195e0` |

A shield strike: the caster is locked in action state 6 for the length of one animation,
turns toward the nearest creature in front, and at a fixed moment of the animation hits up
to s3 enemies in front of the shield hand, each with a chance to be stunned.

#### Statistics

`SkillBash_initStats` 0x2de2a8 (**Observed**). No tier 2; every use is slot 10 (directly, or
through slot 8 for the damage range).

| Stat | Meaning | First | Base | Step (decimal, hex) |
|---|---|---|---|---|
| 0 | damage centre value; the roll is 80 %…120 % of it — Observed: 0x2deac8–0x2deb30 | 1 | 50 | 9.99992752 (0x411fffb4) |
| 1 | stun chance in percent — Observed: 0x2deb4c–0x2deb90 | 1 | 20 | 1.99997199 (0x3fffff15) |
| 2 | stun length in seconds — Observed: 0x2de938–0x2de97c, 0x2deba0 | 1 | 4 | 0.50000197 (0x3f000021) |
| 3 | most enemies hit by one bash — Observed: 0x2de8e0–0x2de90c, 0x2decb8 | 1 | 1 | 0.25 (0x3e800000) |
| 4 | mana — Observed: 0x2de60c | 1 | 16 | 2.99998379 (0x403fffbc) |

Damage bounds: slot 8 `getStatRange(0.19999999, stat 0, level, randomise 0, &lo, &hi)`:
lo = max(1, round(v − v × 0.19999999)), hi = max(1, round(v + v × 0.19999999)) with
v = getStat(0, level); no generator is used because randomise is 0.

| Rank | s0 → lo…hi | s1 stun % | s2 stun | s3 targets | s4 mana |
|---|---|---|---|---|---|
| 1 | 50 → 40…60 | 20 | 4 s (240 frames) | 1 | 16 |
| 10 | 140 → 112…168 | 38 | 9 s (540 frames) | 3 | 43 |
| 20 | 240 → 192…288 | 58 | 14 s (840 frames) | 6 | 73 |

Series: s0 +10 per rank, s1 +2, s4 +3. s2 for ranks 1–20: 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9,
10, 10, 11, 11, 12, 12, 13, 13, 14 (the step is a hair above 0.5, so the halves round up).
s3: 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 6, 6.

The rank text (0x2de484) prints lo, hi, s1, s2, and s3 as well when s3 is not 1.

#### Cost and limits

- Mana: slot 15 with (level, 19) = (float) getStat(4, level): 16 / 43 / 73 at ranks 1 / 10 /
  20. Recast 30 frames.
- `SkillBash_canUse` 0x2de334 (skill, caster): 1 for a non-player. For a player it returns 0,
  with a HUD notice for the slot (180 frames), when equipment slot 3 (record +0x43fc, the
  shield slot) is empty or the weapon animation class (record +0x4a86) is 4 (bow).
- General player gates as for id 35. State 6 is exempt from stagger and knock-down.
- Chaining: see "The repeat latch" below.

#### Behaviour

P = caster, L = spell level.

##### Cast — `SkillBash_cast` 0x2de3bc (skill, level, caster, pos*, facing)

1. lvl = slot 14 `adjustLevel(level, 19)` (returns level).
2. Cast sound on the caster (`spel_bw_bash.anm` from `fx.lmp`).
3. Allocate 0x28 bytes, `SpellBash_ctor(spell, lvl, caster, skill)`; return it (attached by
   `Player_castSkill`). Position and facing arguments are not used.

##### Constructor — `SpellBash_ctor` 0x2de640

1. Base `Spell` part (one shared draw → +0x10).
2. **P+0x58c = 6**, no is-player test (0x2de6c4).
3. clip = `res_find(first word of the table at P+0x24, "bash.anm")`;
   `anim_startBlendInOut(0.1, 0.1, P animation state, clip, flags 0x812)` — root motion
   (0x800), status bit 0x10, purge-lower bit 0x2.
4. The clip's event slot 1 is written into the loaded animation: mask (clip+0x20) = 2, time
   (clip+0x1c) = 0.592001 s (0x3f178d60). The clip pointer is not tested for null.
5. +0x18 = +0x1c = +0x20 = +0x24 = 0.
6. Facing target: `world_collectObjectsInArc(radius 100.0, arc 90.0 degrees, half-width 0.0,
   P position, P facing, &list, filter 0)`. If the list is not empty: when the head (the
   nearest creature) does not have object flag 0x1000000 (friendly to players), +0x24 = head
   object. When the head is friendly, the rest of the list is searched for a non-friendly
   creature and, if one exists, +0x24 is set — to the **head** object, not to the one found
   (0x2de7b4; **Observed** quirk). If every entry is friendly +0x24 stays 0. The list is
   cleared.

| Offset | Type | Initial value | Meaning |
|---|---|---|---|
| +0x00 | s8 | level | |
| +0x04 | handle list | 0 | back-list |
| +0x08 | Skill* | skill | |
| +0x0c | Creature* | caster | |
| +0x10 | u32 | shared draw >> 16 | private generator (particles only) |
| +0x14 | ptr | 0x5195b0 | virtual table |
| +0x18 | s32 | 0 | 1 once the hit has been resolved; returned by slot 4 |
| +0x1c | s32 | 0 | 1 once animation event bit 2 has been seen |
| +0x20 | s32 | 0 | read once as the float half-width argument (0.0); otherwise unused |
| +0x24 | Creature* | see step 6 | creature to turn toward; a plain pointer, not a handle |

##### Per frame

`Player_run` case 6 (0x1a6a28) first: `Player_move(player, mode 5, pad, zero velocity)`, and
the repeat-latch test below. Then, from `Player_updateCast`, `SpellBash_run(spell, pos,
facing)` 0x2de7dc (its two position arguments are not used). The first call is on the cast
frame.

```
ev = Player_animStep(1.0, P)
Player_move(P, mode 3, &g_pads[P.slot], 0)       # no steering, no velocity of its own:
                                                 # only the clip's root motion and pushes move P
if spell.target != 0:
    P->turnToward(0, &spell.target.pos)          # Creature slot 26, mode 0
if ev & 2:  spell.swing = 1                      # +0x1c
if spell.done == 0:                              # +0x18
    if spell.swing == 0:
        SpellBash_windupFx(spell)                # 0x2dedec: 203 particles on the body
    else:
        maxTargets = getStat(3, L)
        chance     = getStat(1, L)
        stunFrames = getStat(2, L) * 60
        knock = 0x40000 if L < 6 else 0x80000 if L < 16 else 0x200000
        q = model_getAttachPoint(1.0, P body model, origin = P.pos, P.facing, P anim state, point 1)
        world_collectObjectsInArc(radius 41.0, arc -1.0 (no wedge test), half-width 0.0,
                                  pos = q, facing = P.facing, &list, filter 0)
        n = 0
        if list not empty and maxTargets > 0:
            for node in list, head first, while n < maxTargets:
                o = node.object
                if o.flags & 0x1000000: continue                 # friendly
                if P->isEnemy(o) == 0:  continue                 # Creature slot 20
                getStatRange(0.19999999, 0, L, 0, &lo, &hi)
                damage_apply((float)lo, (float)hi, victim = o, attacker = P, 100000, 0, 0,
                             flags = knock | 0x40, descriptor 0, noCrit = 1)
                if o.hp (+0x228) > 0.0 and (shared draw % 100) + 1 <= chance:
                    o->stun(stunFrames, 1)                       # Creature slot 30
                else:
                    o colour flash: +0x90 = 100, +0x92 = 100, +0x94 = 64, +0x96 = 64,
                                    +0x98 = 100, +0x9a = 100, +0x9c = 64
                if spell.done == 0:                              # first enemy only
                    create a LightEffect at o.pos + (0, 0, 64)   # GameObject: one shared draw
                n += 1;  spell.done = 1
        if spell.done == 0:                                      # no enemy was hit
            world_collectInSphere(41.0, P.pos, ..., &list)       # prepends to the same list
            o = first object in list with (flags & 0x1000060) == 0   # not friendly, not a creature, not a player
            if o exists:
                getStatRange(0.19999999, 0, L, 0, &lo, &hi)
                damage_apply((float)lo, (float)hi, o, P, 100000, 0, 0, knock | 0x40, 0, noCrit = 0)
        spell.done = 1

if (P.animStatus (+0x11a) & 0x10) == 0  or  P+0x450 != 0:
    P.state = 2;  destroy the spell (slot 1 with 3)
elif net_isLocalSlot(P.slot):
    g_forceGhostRebase = 0x3c
clear the local list
```

Details (**Observed** unless marked):

- The shared draw for the stun roll is made only when the victim's hit points are above 0
  after the damage call; `(draw >> 16) % 100 + 1` is compared with the chance, so the
  probability is exactly s1 percent.
- `world_collectObjectsInArc` with arc −1 keeps every creature with `flags & 0xd == 0` in a
  box of ±41 on all three axes round q whose centre is strictly in front of q along P's
  facing (2-D), nearest first at the head. There is no distance test beyond the box.
- Hit flags: 0x40 (cannot be blocked) plus one knock bit by rank: ranks 1–5 0x40000, ranks
  6–15 0x80000, ranks 16–20 0x200000. noCrit is 1 for creature hits (no critical roll or
  bonus) and 0 for the fallback hit on a non-creature object.
- The fallback lets a bash that hits no enemy break one nearby object (the first
  non-creature within 41 units of P, in reverse box-query order).
- Timing with the cast on F0 and animation speed 1.0: the clip is first advanced by the run
  on F0; the bit-2 event of the clip (0.592 s) falls in the 36th advance, so the hit is
  resolved on **F0+35**. Slow and the Drowsy factor scale the animation step and delay it.
  As for the other skills, `ev` merges the events of all live tracks; a bit 2 coming from a
  base locomotion clip would trigger the hit early (animation data, **Unknown**).
- `turnToward` is the Creature base function 0x10bb08: a damped turn whose angular velocity
  (+0x110) gains 5 % of the remaining angle per frame, loses 44.72 % of itself, is clamped to
  ±(turn rate +0xb0 × 1092.2666) and is added to the facing.
- The spell ends when the bash clip is gone (status bit 0x10 clear) or the repeat latch is
  set; it writes state 2 itself.

##### The repeat latch (why `Player_run` calls Spell slot 4)

In `Player_run` case 6, for the real player only (0x1a6a84–0x1a6b88): if a button of the
ability mask (record +0x4a80) is in the pad's newly-pressed word (pad+0x0c) and the ability
record currently selected (record +0x4a60 chooses +0x4a84 or +0x4a85) has skill id 49, the
attached `SpellBash` is looked up by type and its slot 4 (`SpellBash_getField18`, returns
+0x18) is called; when it is non-zero player+0x450 is set to 1. The same test exists for id
34 with `SpellShieldBash`.

Effect: once the hit has been resolved, pressing the ability button again sets the latch;
`SpellBash_run` later in the same frame sees +0x450, ends the bash at once and returns the
player to state 2; on the next frame state 2 treats the latch like a held button and starts
the ability again (it clears the latch on every path). So a second bash can be queued as
soon as the first has landed, skipping the rest of the recovery animation; mana and the
recast counter (already 0 by then) are checked as usual. Before the hit has landed the press
is ignored.

##### Destructor 0x3ce650

Base destructor only (clears the back-list, frees on bit 0).

#### Random draws

Shared generator:

1. `SpellBash_ctor`: one draw.
2. On the hit frame, per enemy in list order: the `damage_apply` sequence
   (`docs/gameplay.md` §2.5, with noCrit set); then one draw for the stun roll if the
   victim's hit points are above 0; then, for the first enemy only, one draw in the
   `LightEffect` constructor (skipped if the allocation fails).
3. Fallback hit: the `damage_apply` sequence for a non-creature (one draw).

Private generator (presentation only): every run before the swing event calls
`SpellBash_windupFx`: 203 × (one draw for a model sample point, then three draws repeated
until the vector lies inside the unit sphere).

#### Presentation only

Wind-up particles (definition 0x8e5b40, registered by `bash_staticInit` 0x2defd4), the cast
sound, the bash clip, the flash light on
the first victim, the victim's colour flash, HUD notice from canUse.

#### Per-machine state

- `SpellBash_windupFx` takes positions and the model from `net_objOrGhost(P)` (0x2dedec):
  on the owner's machine the particles follow the prediction copy. The number of private
  draws does not depend on which object is used (same model, same loop count). **Observed.**
- `net_isLocalSlot` → `g_forceGhostRebase = 0x3c` (0x2ded9c–0x2dedb0). Presentation.
- Not guarded for a non-player owner: the constructor's store to +0x58c (0x2de6c4); in the
  run function the read of +0x3c8 used to index `g_pads` (0x2de848), `Player_animStep` and
  `Player_move` on the owner, the test of +0x450, the store to +0x58c and the
  `net_isLocalSlot` call (0x2deda0). Reachable only through the weapon-effect cast (no
  monster uses the skill).
- Weapon-effect cast by a player attacker: the spell is not attached and never runs, so
  nothing advances the real player's animation in state 6 and nothing writes state 2 again.
  **Observed** code path; reachability **Unknown**.
- +0x24 is a plain pointer. If the creature is destroyed while the bash plays, the run
  function keeps reading a position out of the freed block (**Inferred** from the missing
  handle; the bash lasts well under two seconds).
- The constructor writes one event slot of the shared "bash.anm" clip with constants; the
  prediction copy never casts this skill (flag bit 0 clear). Not a hazard.
- The repeat latch reads the pad pointer `Player_run` chose (the zeroed pad while controls
  are locked) and is skipped for the prediction copy.
- No gameplay use of the camera, the cosmetic generator, 0x404468 or a local option.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2de23c | `SkillBash_ctor` | |
| 0x2de2a8 | `SkillBash_initStats` | |
| 0x2de334 | `SkillBash_canUse` | shield and bow test |
| 0x2de3bc | `SkillBash_cast` | |
| 0x2de484 | `SkillBash_describeRank` | |
| 0x2de60c | `SkillBash_manaCost` | |
| 0x2de640 | `SpellBash_ctor` | |
| 0x2de7dc | `SpellBash_run` | (the function list splits it at 0x2dec40; it is one function) |
| 0x2dedec | `SpellBash_windupFx` (proposed) | particles; only caller 0x2ded40 |
| 0x2defcc | `SpellBash_getField18` | slot 4 |
| 0x1a5030 | `Player_run` | case 6 at 0x1a6a28 |
| 0x1b4020 | `Player_move` | modes 3 and 5 |
| 0x10bb08 | Creature slot 26 | turn toward a point |
| 0x3c82e4 | Skill slot 8 | non-random damage range |

#### Not determined

- Length, root motion and event table of "bash.anm" (data): they fix how far the caster
  lunges and how long the recovery lasts.
- `world_collectObjectsInArc` was used from the summary in §1.6.
- What Creature slot 30 does with the flash argument, and the take-damage handling of the
  three knock bits.
- Whether any item casts id 49 as a weapon effect.

### 50 minorhealing — SkillMinorHealing

#### Identity

| Item | Value | Evidence |
|---|---|---|
| Id, name | 50 (0x32), `minorhealing` | Observed: constructor 0x2e0180 |
| Class | `SkillMinorHealing`, virtual table 0x519750; own cast 0x2e022c, describeRank 0x2e02cc, manaCost 0x2e0354, initStats 0x2e01ec, icon getter 0x3ce814; canUse is the base (returns 1) | Observed |
| Skill object | 0x6e28c0, table entry 0x41b238 | Observed: static initialiser 0x16b1fc |
| Kind, flags, recast | 0 (ordinary active), 0, 30 frames | Observed |
| Effect class | `SpellMinorHealing`, 0x24 bytes, virtual table 0x519720 (slot 1 destructor 0x3ce838, slot 2 run 0x2e04f8, slots 3, 4 base). The constructor also creates one `GlowingShaft` (0x5c bytes, GameObject, virtual table 0x50ec68, constructor 0x202ff0) | Observed |
| Who has it | ranger tree (row level 20, prerequisite skill 19) | Observed in the tree dump |
| Type | active self heal: a share of maximum hit points delivered over 90 frames |

#### Statistics

`SkillMinorHealing_initStats` 0x2e01ec. Statistics 1 to 3 zero; tier 2 none.

| Stat | Meaning | Tier 1: first, base, step | Tier 2 |
|---|---|---|---|
| 0 | total heal as a percentage of maximum hit points (Observed: constructor 0x2e0470-0x2e04e8) | 1, 30, 3.50092888 (0x40600f38) | none |
| 4 | mana cost (Observed: manaCost calls slot 15) | 1, 100, 8.50169754 (0x410806f4) | none |

Read with slot 10.

| Rank | s0 | s4 |
|---|---|---|
| 1 | 30 | 100 |
| 10 | 62 | 177 |
| 20 | 97 | 262 |

Ladders: s0 = 30, 34, 37, 41, 44, 48, 51, 55, 58, 62, 65, 69, 72, 76, 79, 83, 86, 90, 93, 97;
s4 = 100, 109, 117, 126, 134, 143, 151, 160, 168, 177, 185, 194, 202, 211, 219, 228, 236,
245, 253, 262.

#### Cost and limits

- Mana: slot 15 (level, 20) = (float) slot 10 (4, level): 100 / 177 / 262 at rank 1 / 10 / 20.
- Recast 30 frames. canUse always true. There is no test for a spell of the same class
  already being attached: with enough mana the skill can be cast again after 30 frames while
  the previous heal (90 frames) is still running, and both run.
- No weapon or state gate in the class. The prediction copy does not cast (flag bit 0
  clear).

#### Behaviour

**Cast** `SkillMinorHealing_cast(skill, level, caster, pos*, facing)` 0x2e022c: level2 =
slot 14 (level, 20) (unchanged); allocate 0x24 bytes; when that succeeded run the constructor
(spell, level2, caster, skill); return the spell (the player cast path attaches it).

**Constructor** `SpellMinorHealing_ctor(spell, level, caster, skill)` 0x2e0388, in order:

1. Base Spell fields, **one shared draw**.
2. Sound on the caster (`sound_playOnObject`, resource `spel_he_heal.anm`).
3. spell+0x18 = caster.
4. Allocate 0x5c bytes; when that succeeded `GlowingShaft_ctor(obj, &caster position, 90,
   250, 200, 100)`: **one shared draw** (GameObject constructor); +0x4c = +0x50 = 90
   (frames), s16 +0x54, +0x56, +0x58 = 250, 200, 100, object flags OR 0x4009, byte +0x28 =
   0x30, on the every-frame list. Its run function 0x2030a8 only counts +0x4c down and
   destroys the object when it reaches 0 or less (90 run calls).
5. spell+0x1c = 0.0.
6. spell+0x20 = ((maxHp x (float) slot 10 (0, level)) x 0.01 (0x3c23d70a)) x 0.011111141
   (0x3c360b81), three single-precision multiplications in that order, where maxHp is the
   float at player record +0xb0 of slot caster+0x3c8, **read without a player test**.

| Offset | Type | Meaning |
|---|---|---|
| +0x00 | u8 | level |
| +0x04 | handle list head | base Spell |
| +0x08 | Skill* | 0x6e28c0 |
| +0x0c | Creature* | owner |
| +0x10 | u32 | private generator state (never used) |
| +0x14 | ptr | virtual table 0x519720 |
| +0x18 | Player* | the caster again; the run function uses this copy |
| +0x1c | float | seconds elapsed |
| +0x20 | float | hit points added per frame, fixed at cast time |

**Run** `SpellMinorHealing_run(spell, pos*, facing)` 0x2e04f8, once per frame from
`Player_updateCast` (only while the record's hit points are above 0; first call in the cast
frame):

```
slot = (spell+0x18)->0x3c8                      # no player test
spell+0x1c += 0.016666666
hp = record[slot].hp (+0xac);  max = record[slot].maxHp (+0xb0)
if hp + 1.0 <= max:  record[slot].hp = hp + spell+0x20          # no clamp to max
t = spell+0x1c
if t < 0.49999595 (0x3effff78): owner s16 +0x90 = 104, +0x92 = 107, +0x94 = 64, +0x96 = 63,
                                 +0x98 = 104, +0x9a = 107, +0x9c = 64          # tint
if t > 1.499996 (0x3fbfffde): destroy self (slot 1 with 3)
```

Timing (simulated in single precision, the same under round-to-nearest and truncation):
the spell is destroyed in run call 90, so the heal test runs 90 times; the tint is written in
calls 1 to 29.

What follows from the code (Observed):

- The per-frame amount is fixed from the maximum hit points at cast time; the test each
  frame uses the current maximum.
- A frame is skipped when hp + 1 exceeds the maximum, so healing stops within one point of
  full; the last accepted step is not clamped and can leave hit points above the maximum by
  up to (per-frame amount - 1).
- Total when nothing interrupts: 90 x per-frame amount, i.e. about statistic 0 percent of
  maximum hit points (the constant is slightly above 1/90: maximum 200 at rank 1 gives
  0.6666684 per frame, 60.0002 in total).
- Only record +0xac is written; the object's mirror +0x228 follows through `Player_run`.
- Two overlapping casts add.

**Non-player caster.** No monster references the Skill object. Through a weapon-effect entry
the constructor would take its two shared draws and read "maximum hit points" from the
player record indexed by whatever the creature has at +0x3c8; the spell is not attached, so
run never executes and nothing is healed. For a player attacker through that path the same
happens: draws, sound, shaft, no heal (Inferred from the code paths).

#### Random draws

1. Constructor: one shared draw (spell seed).
2. Constructor: one shared draw (`GlowingShaft`), skipped when its allocation fails.
3. Run: none.

#### Presentation only

The sound, the shaft object, the tint, `describeRank` 0x2e02cc (statistic 0).

#### Per-machine state

- Constructor and run index the player record with owner+0x3c8 with no is-player test
  (0x2e04a8, 0x2e053c). Reachable for a non-player only through the weapon-effect cast.
- No camera, local-slot, cosmetic or 0x404468 use. The prediction copy cannot cast.
- Allocation caveat on the shaft's shared draw.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2e0180 | SkillMinorHealing_ctor | kind 0, recast 30 |
| 0x2e01ec | SkillMinorHealing_initStats | statistics 0 and 4 |
| 0x2e022c | SkillMinorHealing_cast | allocate and construct |
| 0x2e02cc | SkillMinorHealing_describeRank | text only |
| 0x2e0354 | SkillMinorHealing_manaCost | slot 15 (level, 20) |
| 0x2e0388 | SpellMinorHealing_ctor | above |
| 0x2e04f8 | SpellMinorHealing_run | above |
| 0x3ce838 | SpellMinorHealing_dtor | base destructor only |
| 0x202ff0 | GlowingShaft_ctor | presentation object |
| 0x2030a8 | GlowingShaft run (slot 4) | countdown and self-destruction |

#### Not determined

- Whether anything clamps record hit points to the maximum afterwards (regeneration and
  `player_recalcStats` were not read for this).
- `GlowingShaft` draw function 0x1fda20 (not opened).
- Whether any item carries a type-0x29 entry for id 50.

### 51 ancestralcall — SkillAncestralCall

#### Identity

| Item | Value | Evidence |
|---|---|---|
| Id, name | 51 (0x33), `ancestralcall` | Observed: constructor 0x2e0640 |
| Class | `SkillAncestralCall`, virtual table 0x519808 | Observed |
| Skill object | 0x6e2928, table entry 0x41b23c | Observed: static initialiser 0x16b214 |
| Kind | 0 (ordinary active) | Observed |
| Flags | 1: bit 0 set, the prediction copy may cast | Observed: 0x2e0640 ORs 1 into +0x04 |
| Recast | 30 frames | Observed |
| Effect class | `SpellAncestralCall`, 0x84 bytes, virtual table 0x5197d8 (slot 1 destructor 0x3ce95c, slot 2 run 0x2e0d10, slots 3, 4 base). The constructor also creates one `LightEffect` (0xbc bytes, a GameObject) | Observed |
| Who has it | barbarian tree only (row level 20, prerequisite skill 62) | Observed in the tree dump |
| Type | active: a cast animation, then a timed aura that multiplies weapon damage, attack rating and melee swing speed of the caster and of allied players in range |

#### Statistics

`SkillAncestralCall_initStats` 0x2e06bc. All tier-2 first levels are 0xffff (none).

| Stat | Meaning | Tier 1: first, base, step | Tier 2 |
|---|---|---|---|
| 0 | weapon damage and attack rating, percent of normal (Observed: `SpellAncestralCall_getStat0Fraction` 0x2e13d0 = value x 0.01, used in `Player_recalcDamage`) | 1, 125, 4.99998283 (0x409fffdc) | none |
| 1 | melee swing speed, percent of normal (Observed: 0x2e1420 = value x 0.01, used in `Player_run` state 1) | 1, 110, 2.00196385 (0x4000202d) | none |
| 2 | duration in seconds (Observed: constructor stores it at spell+0x20) | 1, 10, 0.500993967 (0x3f004124) | none |
| 3 | aura radius in steps of 12 world units (Observed: 0x2e14a0-0x2e14cc) | 1, 4, 0.507000983 (0x3f01cad1) | none |
| 4 | mana cost (Observed: manaCost 0x2e0980 calls slot 15) | 1, 85, 4.00093365 (0x408007a6) | none |

All reads use slot 10 with the level byte stored in the spell.

| Rank | s0 | s1 | s2 | s3 (radius) | s4 |
|---|---|---|---|---|---|
| 1 | 125 | 110 | 10 | 4 (48) | 85 |
| 10 | 170 | 128 | 15 | 9 (108) | 121 |
| 20 | 220 | 148 | 20 | 14 (168) | 161 |

Ladders: s0 = 125 + 5 x (rank - 1); s1 = 110 + 2 x (rank - 1); s4 = 85 + 4 x (rank - 1);
s2 = 10, 11, 11, 12, 12, 13, 13, 14, 14, 15, 15, 16, 16, 17, 17, 18, 18, 19, 19, 20;
s3 = 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13, 14.

#### Cost and limits

- Mana: slot 15 (level, 10) = (float) slot 10 (4, level); the 10 is passed to the base slot 14,
  which ignores it. 85 / 121 / 161 at rank 1 / 10 / 20. Observed 0x2e0980.
- Recast 30 frames.
- `canUse(skill, caster)` 0x2e060c: true only when the caster has no `SpellAncestralCall`
  attached. Observed.
- No weapon or state gate in the class. The cast animation is chosen by the weapon style but
  every style has one (the default covers the rest).

#### Behaviour

**Cast** `SkillAncestralCall_cast(skill, level, caster, pos*, facing)` 0x2e0750:
level2 = slot 14 (level, 10) (unchanged); allocate 0x84 bytes; when that succeeded run the
constructor with (spell, level2, caster, skill); return the spell. Position and facing are
not used. Observed.

**Constructor** `SpellAncestralCall_ctor(spell, level, caster, skill)` 0x2e09b4, in order:

1. Base Spell fields; **one shared draw** for spell+0x10.
2. spell+0x18 = caster, spell+0x1c = 0.0.
3. Sound on the caster (`sound_playOnObject`, resource `spel_bw_ancestral.anm`).
4. Weapon style = s8 at player record +0x4a86 of slot caster+0x3c8, **read without testing
   that the caster is a player**. Animation by style: 0 `ohw_warcry.anm`, 1 `dhs_warcry.anm`,
   2 `dha_warcry.anm`, 3 `l_warcry.anm`, 5 `nw_warcry.anm`, 7 `dw_warcry.anm`, anything else
   `nw_warcry.anm`; looked up in the caster's own animation set (caster+0x24) and started on
   the caster with `anim_startBlendInOut(0.1, 0.1, caster+0x114, anm, 0x22)` (0x3dcccccc).
5. Everything below is skipped when the caster has object flag 0x20000 (prediction copy):
   - allocate 0xbc bytes; when that succeeded construct a `LightEffect` at the caster's
     position with 36 added to the height, owner = caster, start colour (0, 155, 255, -96),
     end colour 0, radius 180 falling to 144, duration 5 s (300 frames) (**one shared
     draw**, the GameObject constructor; layout in section 64);
   - caster+0x58c = 6 (action state "under control of a skill"), written whether or not the
     light was allocated and without a player test;
   - spell+0x7c = 0, spell+0x28 = `g_simFrame`, spell+0x2c, +0x30, +0x34 = 0;
   - spell+0x20 = (float) slot 10 (2, level); spell+0x24 = (float)(slot 10 (3, level) x 12);
   - spell+0x80 = `particleGroup_create()`.

Field layout of `SpellAncestralCall`:

| Offset | Type | Meaning |
|---|---|---|
| +0x00 | u8 | level |
| +0x04 | handle list head | base Spell |
| +0x08 | Skill* | 0x6e2928 |
| +0x0c | Creature* | owner (used by the query and by `net_objOrGhost`) |
| +0x10 | u32 | private generator state |
| +0x14 | ptr | virtual table 0x5197d8 |
| +0x18 | Player* | the caster again; the run function uses this copy for animation, state and tint |
| +0x1c | float | seconds elapsed, counts up from 0 |
| +0x20 | float | duration in seconds |
| +0x24 | float | radius in world units; written by the constructor and not read by any function of the class (run and query recompute it) |
| +0x28 | s32 | `g_simFrame` at construction (beam timing only) |
| +0x2c, +0x30, +0x34 | u32[3] | beam handles of the cast animation (presentation) |
| +0x38..+0x7b | | not referenced |
| +0x7c | s32 | 0 while the cast animation plays, 1 afterwards |
| +0x80 | u32 | particle group handle |

For the prediction copy the fields from +0x20 on are left uninitialised; the spell is
destroyed by the cast path in the same call, and the destructor (handle list cleared, memory
freed) does not read them. Observed.

**Run** `SpellAncestralCall_run(spell, pos*, facing)` 0x2e0d10. A player's attached spells
are run from `Player_updateCast` 0x1a3f70, called at the end of `Player_run` (0x1ac6a8) only
while the record's hit points (+0xac) are above 0, so the first run call is in the cast
frame, after the state switch (Observed). Per call:

1. spell+0x1c += 0.016666666 (0x3c888888).
2. Cast phase, while spell+0x7c == 0:
   - `Player_animStep(1.0, player)` (the spell advances the player's animation; `Player_run`
     state 6 does not do it for a real player and only calls `Player_move` with mode 5 and a
     zero vector).
   - If bit 0x20 of the animation flag word (player+0x11a, the union of the flags of the live
     tracks) is now clear, the cast animation is gone: the three beam handles are zeroed, a
     looping sound held at player+0x4a8 is stopped and that field set to -1, **player+0x58c =
     2**, spell+0x7c = 1. The store of 2 is unconditional: it also replaces a stagger state
     entered meanwhile (Inferred consequence).
   - Otherwise: beams between the two hand attachment points and a point 360 above the
     position argument, created when `g_simFrame - spell+0x28` equals 23, 47 and 47 (table at
     0x54fc60) and refreshed every frame; sounds at the same moments. Presentation only.
3. Tint and glow on the owner (`SpellAncestralCall_tintAndGlow` 0x2e15a0): s16 writes
   +0x90 = 44, +0x92 = 48, +0x94 = 190, +0x96 = 41, +0x98 = 44, +0x9a = 48, +0x9c = 190,
   +0x9e = 41, then model-vertex particles (`fx_modelParticlesNearCamera_1f61c0`).
4. radius = slot 10 (3, level) x 12. A ring of `level + 14` particles at that radius, one
   `Spell_rand` draw each, centred on `net_objOrGhost(owner)`.
5. For every entry of `g_alivePlayers` in order: P = that slot's player object; skip when P
   is null or P == spell+0x18; when `g_pvpModeA` is non-zero skip unless owner->slot 22 (P)
   is non-zero; if dx x dx + dy x dy < (float)(radius x radius) (2-D, strict) apply step 3 to
   P.
6. If spell+0x20 < spell+0x1c the spell destroys itself (slot 1 with 3). With truncating
   single-precision addition (the console's floating-point unit; Inferred, see the note in
   section 53) a duration of 10 s ends in run call 601 and 11 s in call 661; with
   round-to-nearest 600 and 660. For 12 to 20 s both give 60 x D + 1 (721, 781, ... 1201).
   The count includes the cast animation, and the clock does not advance on frames where the
   owner's record hit points are 0 or less.

The run function makes no damage call and changes no statistic. The buff exists only as the
answers of the query below; it is in force from the moment the spell is attached, including
the cast animation.

**Query** `SpellAncestralCall_queryFor(spell, creature, float *out0, float *out1)` 0x2e1470
(two callers):

```
R = spell.skill.slot10(3, spell.level) * 12                    # integer
if out0: *out0 = (float) slot10(0, level) * 0.01               # 0x2e13d0, 0x3c23d70a
if out1: *out1 = (float) slot10(1, level) * 0.01               # 0x2e1420
if creature == null: return 0
if creature == spell.owner (+0x0c): return 1
if g_pvpModeA != 0 and owner->slot22(creature) == 0: return 0  # same team only
d2 = dx*dx + dy*dy                                             # 2-D
return d2 <= (float)(R*R) ? 1 : 0                              # inclusive
```

**Use 1: damage and attack rating.** `Player_recalcDamage(player, weapon, x)` 0x1b7158, at
0x1b780c-0x1b7970, after the weapon, statistic and weapon-skill terms have produced the
record's minimum (+0xd0), maximum (+0xd4) and attack rating (+0xcc) (also on the unarmed
path, which jumps straight here):

```
f = 0.0
for i in 0 .. g_alivePlayerCount-1:
    P = g_players[g_alivePlayers[i]].object
    s = creature_findSpellByType(P, SpellAncestralCall)
    if s and queryFor(s, player, &v, null) != 0 and f < v: f = v
if f != 0.0:
    for field in (+0xd0, +0xd4, +0xcc):
        x = (float) record.field * f
        record.field = trunc(x + 0.5) if x >= 0 else trunc(x - 0.5)
```

The loop includes the player's own slot (the query answers 1 for the owner), so the caster's
own bonus also depends on being in `g_alivePlayers`. Several sources do not add: the largest
fraction wins. The later steps of the same function (class multipliers, x1.5 for status
counter 2, x1.2 for counter 4) then apply to the multiplied values. `Player_recalcDamage` is
called by `Player_meleeHit` (0x1b6ce8, 0x1b6ddc), by 0x1bb718 and by the statistics screen
0x1d1db8; the multiplied values are what melee passes to `damage_apply` as min, max and
attack rating.

Rounding caution: the fraction is a single-precision product. 125 x 0.01 is exactly 1.25
under round-to-nearest but 1.2499999 under truncation, and a minimum of 10 then becomes 13
or 12 respectively. A reimplementation must reproduce the console's arithmetic here.

**Use 2: swing speed.** `Player_run` state 1 (melee), 0x1aa018-0x1aa0ec, every frame of a
swing:

```
speed = 1.0;  best = 0.0
for i in 0 .. g_alivePlayerCount-1:
    P = g_players[g_alivePlayers[i]].object
    s = creature_findSpellByType(P, SpellAncestralCall)
    if s:   ok = queryFor(s, player, null, &v)
    else:
        s2 = creature_findSpellByType(P, SpellBattleCry)
        if not s2: continue
        ok = 0x302c04(s2, player, &v)               # the BattleCry counterpart
    if ok and best < v: best = v
if best != 0.0: speed = speed * best
```

A player carrying both spells is asked only for AncestralCall. After this the function adds
the additive terms (attack-speed item modifiers, +0.25 for status counter 2, +0.1 for
counter 4, the berserker factor), calls `Player_animStep(speed, player)`, applies the slow
amount and divides the swing's timing tables by the result. So statistic 1 replaces the base
1.0 of the swing speed: 1.10 at rank 1, 1.28 at rank 10, 1.48 at rank 20.

**Stacking and refresh.** No refresh (canUse refuses while attached). Largest value wins
among several casters, separately for damage and for speed.

**Non-player caster.** No monster references the Skill object (Observed with the reference
tool). Through a weapon-effect entry the constructor would, for a creature that is not a
player, read a player-record byte with whatever is at creature+0x3c8 as the slot, look the
animation up in that creature's set, take two shared draws (spell, light) and store 6 at
creature+0x58c, which is outside or unrelated in a non-player object. For a player attacker
through that path the spell is not attached, so nothing ever sets the action state back to
2 and nobody gets the bonus (Inferred from the code paths; whether such an item exists is
Unknown).

**Prediction copy.** Bit 0 of the skill flags lets the copy cast. The constructor then takes
the shared draw, plays the sound and starts the animation on the copy, and stops at the
0x20000 test: no light, no state 6, no timers. The cast path destroys the spell at once, sets
the copy's recast counter and subtracts the mana (both restored by the prediction loop
according to docs/skills.md). `Player_run` state 6 advances the copy's animation itself
(0x1a5030 case 6, only for flag 0x20000). Observed.

#### Random draws

1. Constructor: one shared draw (spell seed).
2. Constructor, real caster only, when the 0xbc allocation succeeds: one shared draw
   (`LightEffect` is a GameObject).
3. Every run call: `level + 14` private draws (`Spell_rand`), ring particle angles. Count is
   position-independent.
4. The queries draw nothing.

#### Presentation only

Cast sound and light; beams and two sounds during the cast animation; the looping sound
handle at player+0x4a8; tint (the eight s16 at +0x90..+0x9e) and model-vertex particles on
owner and allies in range; ring particles (definition 0x8e5c30, static initialiser 0x2e1634)
with the group matrix rotated by `g_simFrame x 67` angle units, each particle shown only when
the terrain under it is within 72 units of the owner's height; `describeRank` 0x2e07f0
(statistics 0, 1, 2, 3); icon getter 0x3ce938.

#### Per-machine state

- Constructor: record read through caster+0x3c8 and the write to caster+0x58c have no
  is-player test (0x2e0a5c, 0x2e0c58). Reachable only through the weapon-effect cast.
- Constructor behaves differently for the prediction copy (above); what it still does on the
  copy is a shared draw (restored), a sound and an animation on the copy.
- Run: `net_objOrGhost(owner)` supplies the ring centre and the height reference
  (0x2e0d10 body, two calls); draw counts do not depend on it. Contained.
- `fx_modelParticlesNearCamera_1f61c0` is camera-gated and uses the cosmetic generator;
  presentation.
- Both uses walk `g_alivePlayers` and take each slot's object from the player table. On a
  machine whose list has lost its own slot (the caveat in docs/player.md) the local caster's
  own multiplier and its allies' multipliers from that caster vanish, which changes weapon
  damage and swing timing on that machine only. Inferred from Observed code.
- No camera, local-slot or cosmetic-seed read feeds a gameplay value.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2e060c | SkillAncestralCall_canUse | no SpellAncestralCall attached |
| 0x2e0640 | SkillAncestralCall_ctor | flags bit 0, recast 30 |
| 0x2e06bc | SkillAncestralCall_initStats | table above |
| 0x2e0750 | SkillAncestralCall_cast | allocate and construct |
| 0x2e07f0 | SkillAncestralCall_describeRank | text only |
| 0x2e0980 | SkillAncestralCall_manaCost | slot 15 (level, 10) |
| 0x2e09b4 | SpellAncestralCall_ctor | above |
| 0x2e0d10 | SpellAncestralCall_run | above |
| 0x2e13d0 | SpellAncestralCall_getStat0Fraction | statistic 0 x 0.01 |
| 0x2e1420 | SpellAncestralCall_getStat1Fraction | statistic 1 x 0.01 |
| 0x2e1470 | SpellAncestralCall_queryFor (proposed) | in-range test plus the two fractions |
| 0x2e15a0 | SpellAncestralCall_tintAndGlow (proposed) | tint writes and model particles |
| 0x2e1634 | ancestralCall_staticInit | particle definition 0x8e5c30 |
| 0x3ce95c | SpellAncestralCall_dtor | base destructor only |
| 0x1b780c-0x1b7970 | part of Player_recalcDamage | use 1 |
| 0x1aa018-0x1aa0ec | part of Player_run state 1 | use 2 |
| 0x1a3f70 (head), 0x1ac680-0x1ac6a8 | Player_updateCast and its call | where a player's spells are run |

#### Not determined

- Length of the six cast animations in frames (the lock in state 6 lasts until the track is
  gone; the animation data was not read).
- The `SpellBattleCry` counterpart 0x302c04 (only its call was read).
- Whether the prediction copy carries the real player's attached-spell list (which would
  decide what canUse sees on the copy).
- Who else reads record +0xd0, +0xd4 and +0xcc between two recalculations (ranged and thrown
  attacks were not traced here).
- Whether any item carries a type-0x29 entry for id 51.

### 52 root — SkillRoot

(One class, four ids: 31 `clericroot`, 32 `rangerroot`, 52 `root`, 85 `shamanroot`. The
behaviour is a single code path with **no id-dependent branch** outside the constructor
(name) and initStats (numbers); skill+0x64 is read nowhere else. Observed: 0x2e62b4, 0x2e637c
are the only readers in the class.)

#### Identity

| Item | Value | Evidence |
|---|---|---|
| ids / Skill objects | 31 at 0x6e2108, 32 at 0x6e2170, 52 at 0x6e2990, 85 at 0x6e36f8 | table; `SkillRoot_ctor` 0x2e62b4 stores the id at +0x64 and picks the name (other ids: name stays null) |
| Skill class / virtual table | `SkillRoot`, 0x519ba0 | Observed 0x2e62b4 |
| kind, flags, recast | 0 (active), 0 (copy may not cast), 30 frames | Observed 0x2e62b4 |
| overridden Skill slots | 1 canUse 0x2e6534, 2 cast 0x2e6598, 4 describeRank 0x2e6790, 5 manaCost 0x2e6894, 7 icon 0x3ceea0, 9 initStats 0x2e637c | Observed, table 0x519ba0 |
| effect class | `SpellRoot`, 0x34 bytes, virtual table 0x519b70 (slot 1 dtor 0x2e7034, slot 2 run 0x2e699c, slots 3, 4 base). One per target, attached to the **target** | Observed |
| who has it | 31: cleric (base level 20, needs skill 20). 32: ranger (12, passive mask 0x40). 52: wizard (23, needs skill 12). 85: shaman (26, needs skill 65). No monster run function was found calling it | tree tables; docs/skills.md |
| active / passive | active, instant | |

#### Statistics

Observed in `SkillRoot_initStats` 0x2e637c. Only tier 1 exists (all tier-2 first levels stay
0xffff); every lookup in this class goes straight to slot 10 (`getStat`), so the numbers are
the same for a player and a non-player caster and no level cap is applied.

| Stat | Meaning | id 31 | id 32 | id 52 | id 85 |
|---|---|---|---|---|---|
| 0 | maximum number of creatures rooted by one cast (Observed: loop bound in cast, 0x2e6638–0x2e6740) | 1, 1, 0.332999974 (0x3eaa7ef9) | 1, 1, 0.332999974 (0x3eaa7ef9) | 1, 1, 0.332982987 (0x3eaa7cbf) | 1, 1, 0.332982987 (0x3eaa7cbf) |
| 1 | root duration in seconds (Observed: SpellRoot+0x20; ×60 → creature root timer, 0x2e6c10) | 1, 5, 0.332999974 (0x3eaa7ef9) | same | same | same |
| 2 | success threshold of the 1…100 roll (Observed 0x2e6b6c–0x2e6bd0) | 1, 50, 2.00000286 (0x4000000c) | 1, 50, 1.99997091 (0x3fffff0c) | 1, 50, 2.00099087 (0x4000103c) | 1, 50, 2.20097589 (0x400cdcca) |
| 3 | not set | — | — | — | — |
| 4 | mana | 1, 55, 4.00001097 (0x40800017) | 1, 30, 3.00098991 (0x40401038) | 1, 88, 8.00095654 (0x410003eb) | 1, 100, 8.00188255 (0x410007b6) |

(each cell: first level, base, step.)

Values by rank (slot 10 rounding), ranks 1–20:

- stat 0 (all four ids): 1 1 2 2 2 3 3 3 4 4 4 5 5 5 6 6 6 7 7 7
- stat 1 (all four ids): 5 5 6 6 6 7 7 7 8 8 8 9 9 9 10 10 10 11 11 11
- stat 2, ids 31, 32, 52: 50 + 2 × (rank − 1) → 50, 68, 88 at ranks 1, 10, 20
- stat 2, id 85: 50 52 54 57 59 61 63 65 68 70 72 74 76 79 81 83 85 87 90 92
- stat 4: id 31 = 55 + 4 × (rank − 1) (55, 91, 131); id 32 = 30 + 3 × (rank − 1) (30, 57, 87);
  id 52 = 88 + 8 × (rank − 1) (88, 160, 240); id 85 = 100 + 8 × (rank − 1) (100, 172, 252)

| Rank | targets | seconds (frames) | threshold 31/32/52 | threshold 85 | success chance = (threshold − 1) % |
|---|---|---|---|---|---|
| 1 | 1 | 5 (300) | 50 | 50 | 49 % |
| 10 | 4 | 8 (480) | 68 | 70 | 67 % / 69 % |
| 20 | 7 | 11 (660) | 88 | 92 | 87 % / 91 % |

#### Cost and limits

- Mana: `manaCost(level)` 0x2e6894 = slot 15 (level, 20) = (float) getStat(4, level); values
  above. Observed.
- Recast 30 frames.
- canUse (`SkillRoot_canUse` 0x2e6534): refused when `g_pvpModeA` ≠ 0 **and** the caster has
  the player flag; in that case a HUD notice (90 frames) is posted to the caster's slot
  (+0x3c8, read behind the player test). Everything else is allowed, including any non-player
  caster. Observed.
- Not castable by the prediction copy (flag bit 0 clear).
- The mana and the recast are spent even when no target is found or every roll fails (cast
  returns null either way; `Player_castSkill` charges regardless — see §1.3).

#### Behaviour

**Cast** (`SkillRoot_cast` 0x2e6598; a1 level, a2 caster, a3 pos*, t0 facing). Observed:

1. level' = slot 14 `adjustLevel(level, 20)` (unchanged).
2. Sound on the caster (presentation).
3. n = getStat(0, level') (slot 10).
4. `world_collectObjectsInArc(radius 248.0 (0x43780000), arc 120.0 degrees (0x42f00000),
   halfWidth 0, pos = the cast position argument, facing16 = the facing argument, list,
   filterObj = null)`. With a null filter the query keeps every creature-flagged object with
   (flags & 0xd) == 0 inside the 120-degree wedge, strictly in front, within the box pos ± 248
   on all three axes; the list head is the nearest, the rest partly ordered (see §1.6).
5. If the list is not empty and n > 0, walk it from the head. For each object T (node+0xc), in
   order, all of these must hold or T is skipped (a skipped T does not count):
   - caster is null, **or** caster→slot 20 `isEnemy(T)` ≠ 0;
   - T object flags (+0x0c) & 0x1000000 == 0 (not "friendly to players");
   - `creature_bossRank(T)` == 0 (no boss, no mini-boss);
   - T+0x314 (s16 root timer) ≤ 0. Note: this accepts −1, the permanent root set by the
     script built-in, and it accepts a creature that already carries a pending SpellRoot
     (its timer is still 0 until that spell's roll).
   Then: allocate 0x34 bytes; if that succeeds `SpellRoot_ctor(spell, level', T, skill)`;
   `creature_addSpell(T, spell)` (a null spell is ignored); count += 1 (also when the
   allocation failed). Stop when the list ends or count == n.
6. Free the two temporary handle lists; **return null**. Nothing is attached to the caster.

For a player the position is the hand midpoint and the facing is toward the first enemy in
the cone ahead or else the player's facing (`Player_castSkill`); for a weapon proc it is the
attacker's position and facing.

**Constructor** (`SpellRoot_ctor` 0x2e68c8), in order (Observed): +0x00 level, +0x08 skill,
+0x0c = T, +0x04 = 0; one shared draw → +0x10; virtual table 0x519b70; +0x18 = 0.0; +0x1c = 0;
+0x24 = `particleGroup_create()`; +0x28..+0x30 = T's position (three floats); +0x20 =
getStat(1, level) (slot 10).

`SpellRoot` layout (0x34 bytes):

| Offset | Type | Meaning |
|---|---|---|
| +0x00 | s8 | level |
| +0x04 | handle back-list | link into the target's spell list |
| +0x08 | Skill* | the SkillRoot object |
| +0x0c | Creature* | owner = the creature being rooted |
| +0x10 | u32 | private generator |
| +0x14 | ptr | virtual table 0x519b70 |
| +0x18 | float | elapsed seconds |
| +0x1c | s32 | phase: 0 pending, 1 rooted |
| +0x20 | s32 | duration in whole seconds (stat 1) |
| +0x24 | handle | particle group |
| +0x28 | float[3] | anchor: owner position at construction |

**Run** (`SpellRoot_run` 0x2e699c), once per simulated frame of the owner (for a non-player
owner it is the first thing `Creature_run` does, before the frame timers; for a player owner
it runs from `Player_updateCast` 0x1a3f70 late in `Player_run`, and only while the player's
hit points are above 0). Arguments ignored. Observed:

```
elapsed += 0.0166666657            (0x3c888888; first statement, every call)
if phase == 0:
    7 particles (14 private draws, see Random draws)
    if elapsed > 0.518993974:      (0x3f04dcca; first true on the 32nd call)
        r = (shared draw) % 100                    (unsigned)
        if r + 1 < getStat(2, level):              (slot 10)   -- success
            colour flash on owner: +0x90=4, +0x92=92, +0x94=0, +0x96=81,
                                   +0x98=4, +0x9a=92, +0x9c=0, +0x9e=81
            if owner is not a player: owner+0x314 = (s16)(duration * 60)
            phase = 1
        else:                                       -- resisted
            burst of 100 particles (private draws); destroy spell (slot 1, 3); return
elif phase == 1:
    22 particles on the model (private draws)
    if owner is a player:
        dx = owner.x - anchor.x;  dy = owner.y - anchor.y
        owner+0x2e8 (knockback speed) = sqrt(dx*dx + dy*dy) * 4.0
        owner+0x2e0 (knockback angle) = (s16)(-0x4000 - atan2_16(dx, dy))
if (float)duration < elapsed - 0.518993974:  destroy spell (slot 1, 3)
```

Timing in frames (single-precision accumulation, simulated): the roll is on the **32nd**
call; on success the spell is destroyed on call 32 + 60 × duration (e.g. call 332 for 5 s, 692
for 11 s). The chance of success is the number of r in 0…99 with r + 1 < threshold, i.e.
(threshold − 1) in 100, with the usual tiny modulo bias toward r < 36 (65536 = 655 × 100 + 36).
There is no level, resistance or hit-point term: the roll depends only on stat 2.

**What rooting does to a creature** (non-player owner). The only write is the root timer
+0x314 = duration × 60, made once, on the roll frame. The spell object afterwards only draws
particles; destroying it (`SpellRoot_dtor` 0x2e7034: frees the particle group, then the base
destructor) does **not** clear the timer. The timer is honoured by the creature code:

- `Creature_run` 0x112cc4–0x112ce0: once per call, if the timer is neither 0 nor −1 it is
  decremented. Because the spell ran earlier in the same `Creature_run`, the timer already
  reads duration × 60 − 1 after the roll frame's `Creature_run` and reaches 0 in the
  (duration × 60)-th `Creature_run` counting the roll frame. Observed.
- `Creature_moveBy` 0x113c48 (0x113cfc): while the timer ≠ 0 the whole requested
  displacement is zeroed — the velocity argument (all three components), the animation root
  motion (+0xbc, +0xc0) and therefore also any knockback, which is delivered through the
  same function. The facing change from animation (+0xc4) is still applied, and the
  recorded velocity +0x308/+0x30c becomes 0. Observed.
- `Creature_filterState` 0x10a9c0 (the filter every derived setState uses): while the timer
  ≠ 0 (`Creature_isNotRooted` 0x1195e0 false), a requested AI state other than 0, 5 and
  6…15 is replaced by 5 ("held in place") when the creature has a target, else by 0 with
  the target handle cleared. The attack states 6…15 are let through, so a rooted creature
  still attacks what is in reach and still turns. A request for state 0x14 (dead) first
  zeroes the root, cooldown, +0x31a and stun timers. The root test comes before the stun and
  cooldown tests. Observed.
- Other ways the timer ends early: `Creature_clearStatus` 0x1188f8, the script built-in that
  un-roots, death (above). Observed stores (field scan of +0x314).
- The out-of-line copy of the inline setter at 0x3c26a8 (two instructions: store the 16-bit
  argument at +0x314) has no direct caller that the reference scan finds; SpellRoot and the
  script built-ins write the field with their own store instructions.

**What rooting does to a player** (owner has the player flag). The root timer is not
written. Instead, every frame of phase 1 the spell rewrites the player's knockback speed and
direction so that `Creature_applyKnockback` 0x115eb8 (called by `Player_run` with scale 1.0
right after `Creature_run`) moves the player toward the anchor with velocity 4 × distance
units per second, i.e. 1/15 of the remaining distance per frame (`Creature_moveBy` multiplies
by 0.016666666); the direction is the reverse of the one a hit from the anchor would give
(Observed formulas at 0x116700 and 0x2e6fa8; Inferred "toward the anchor").
**But `Creature_applyKnockback` zeroes +0x2e8 and returns at once for a player when
`g_networkMode` ≠ 0 or `g_pvpModeB` ≠ 0** (Observed 0x115eb8 head). So in any net game, and in
PvP mode B, a "rooted" player is not held at all; only the flash and the particles show. The
pull works only offline outside PvP mode B. A player is only ever a target of a non-player
caster (weapon proc): `Player_isEnemy` 0x1b5ea8 accepts another player only in PvP mode A,
and in that mode canUse refuses player casters.

**Stacking / refresh.**

- A creature whose root timer is > 0 is skipped by cast and does not consume one of the n
  target places: Root cannot be refreshed while it holds.
- During the 31 frames before the roll the timer is still 0, so another cast (recast is 30
  frames) can attach a second SpellRoot to the same creature; each rolls separately, and a
  later success rewrites the timer with its own duration × 60.
- A creature rooted permanently by script (timer −1) is accepted, and a successful roll
  replaces −1 by a finite duration, i.e. the spell *releases* it after the duration
  (Observed test `> 0` at 0x2e66f8 and unconditional store at 0x2e6c24; reachability depends
  on the level scripts).

**End conditions.** Resisted roll (call 32); elapsed − 0.518993974 > duration; destruction
of the owner (`Creature_dtor` deletes attached spells). There is no test of the owner's dead
flag: a creature that dies during the 31 pending frames still gets the roll and, on success,
a root timer on its corpse (death itself had cleared the timer).

**Non-player caster.** canUse passes. Cast behaves identically (slot 10 statistics at the
given level). With a monster attacker the `isEnemy` filter selects its enemies, which are
normally players: they get the player branch described above. With a null caster there is no
enemy filter at all. Reached only through the weapon-proc path (no monster call site found);
because cast attaches the spells itself and returns null, the proc path is fully functional
for this skill.

**Prediction copy.** Cannot cast. `world_collectObjectsInArc` never returns the copy (the
box query skips it), so the copy is never a target; attached spells are not cloned.

#### Random draws

In execution order:

1. Cast: one shared draw per SpellRoot constructed (private seed), in list-walk order.
2. Run, phase 0, every call (calls 1…32): 7 particles × 2 private draws (x and y offset,
   each (v/65536 − 0.5) × owner radius × 1.24898493).
3. Run, call 32: **one shared draw**, r = value % 100, the success roll. This is the only
   gameplay roll; it happens inside the owner's per-frame update, so its position in the
   shared sequence follows the creature update order.
4. Resisted: 100 burst particles, each 3 private draws repeated until the point lies inside
   the unit sphere (rejection sampling); then the spell is gone.
5. Phase 1, every call: 22 particles, each 1 private draw (model sample point index, value
   modulo the model's sample-point count) followed by 3 private draws repeated until inside
   the unit sphere.

The private generator is used for nothing but particles. No cosmetic-generator or 0x404468
draw.

#### Presentation only

Cast sound on the caster; pending-phase ground particles (definition 0x8e5f00) around the
owner; the green flash on success; 22 particles per frame on random model sample points
while rooted (definition 0x8e5eb0, `model_getSamplePoint` — result used only as a particle
position); the 100-particle burst (definition 0x8e5f50) when resisted; the HUD notice from
canUse. Definitions registered by `root_staticInit` 0x2e70a8.

#### Per-machine state

- canUse posts its notice with `hud_showMessage`, which only shows on the machine owning the
  slot; the return value does not depend on it. Observed.
- `g_networkMode` and `g_pvpModeB` in `Creature_applyKnockback` decide whether the player
  pull works; both are the same on every machine of one game, so this is an offline/online
  difference, not a per-machine one. Observed.
- +0x3c8 is read only in canUse, behind the player test. Run's player test guards the
  knockback writes; the root-timer write is on the non-player side.
- No camera, local-slot, audio, cosmetic-seed or option read. None found.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2e62b4 | SkillRoot_ctor | recast 30, id and name |
| 0x2e637c | SkillRoot_initStats | four per-id tables |
| 0x2e6534 | SkillRoot_canUse | PvP mode A refusal for players |
| 0x2e6598 | SkillRoot_cast | arc query, filters, one SpellRoot per target |
| 0x2e6790 | SkillRoot_describeRank | stats 0, 1, 2 into the rank text |
| 0x2e6894 | SkillRoot_manaCost | slot 15 (level, 20) |
| 0x2e68c8 | SpellRoot_ctor | above |
| 0x2e699c | SpellRoot_run | above |
| 0x2e7034 | SpellRoot_dtor | frees the particle group, base destructor |
| 0x112948 (0x112cc4) | Creature_run | root timer countdown; slot 17 call at the top |
| 0x113c48 | Creature_moveBy | zeroes movement while rooted |
| 0x10a9c0, 0x1195e0 | Creature_filterState, Creature_isNotRooted | AI state rewrite while rooted |
| 0x115eb8 | Creature_applyKnockback | player pull; disabled for players in net games and PvP mode B |
| 0x3c26a8 | inline root-timer setter | same field |
| 0x1a3f70 | Player_updateCast | where a player's attached spells are run |
| 0x10d940 | creature_bossRank | boss immunity test (head only) |

#### Not determined

- The 64 callers of `Creature_isNotRooted` in the monster classes were not read; individual
  monsters may react to the timer in further ways (the base behaviour above is complete).
- Whether a monster's run function keeps calling `Creature_run` (and so the spell and the
  countdown) while the monster is inactive or dead.
- Which item data carry a type-0x29 entry with one of the four ids.
- The modulo by the model's sample-point count has no zero guard; a model with no sample
  points was not checked for (presentation only).

### 53 criticalhit — SkillCriticalHit

(Some earlier lists call id 53 `rangercriticalhit`. The constructor says otherwise: see
Identity. This section covers the whole class, i.e. ids 33, 53 and 81.)

#### Identity

| Item | Value | Evidence |
|---|---|---|
| Class | `SkillCriticalHit`, virtual table 0x519c58, one class for three ids selected by skill+0x64 | Observed: constructor 0x2e7258 stores its second argument at +0x64 |
| Id 53 (0x35) | internal name `criticalhit`, Skill object 0x6e29f8, table entry 0x41b244 | Observed: 0x2e72a0-0x2e72fc (name chosen by id), static initialiser call 0x16b238 |
| Id 33 (0x21) | internal name `rangercriticalhit`, Skill object 0x6e21d8, table entry 0x41b1f4 | Observed: same code, call 0x16b044 |
| Id 81 (0x51) | internal name `berserkercriticalhit`, Skill object 0x6e3558, table entry 0x41b2b4 | Observed: same code, call 0x16b5c8 |
| Kind | 0 (ordinary active skill) | Observed: +0x08 = 0 at 0x2e7300 |
| Flags | 0 (the prediction copy may not cast) | Observed: +0x04 = 0 at 0x2e727c |
| Recast | 30 frames | Observed: +0x0c = 0x1e at 0x2e7264 |
| Effect class | `SpellCriticalHit`, 0x5c bytes, virtual table 0x519c28 (slot 1 destructor 0x3cef88, slot 2 run 0x2e7acc, slots 3 and 4 the base Spell functions) | Observed: allocation size at 0x2e74b0, table written at 0x2e79bc |
| Who has it | id 53: barbarian tree (row level 8, prerequisite skill 2). id 33: ranger tree (row level 10, prerequisite skill 60; the skill screen also accepts Archery, id 48, rank >= 1 as a hard-coded alternative for class 3, test at 0x1d5600-0x1d5624). id 81: berserker tree (row level 10, prerequisite passive mask 0x40) | Observed in the tree table dump and in `skills_screen` 0x1d4660; Inferred that no other class can learn them |
| Type | active self buff with an aura for allied players; its whole gameplay effect is a term added to the critical-hit chance inside `damage_apply` |

The name for an id other than these three is left null (Observed 0x2e72cc, 0x2e72dc).

#### Statistics

`SkillCriticalHit_initStats` 0x2e730c writes only the entries below; everything else in the
tier-1 tables keeps the zero it had in the static object, and all five tier-2 first levels are
0xffff (none), so slots 11, 12 and 13 fall back to tier 1. Statistic 3 is all zero (first
level 0, base 0, step 0) and is not read anywhere in the class.

| Stat | Meaning | Id 53: first, base, step | Id 33: first, base, step | Id 81: first, base, step |
|---|---|---|---|---|
| 0 | critical-hit chance added, in percent (Observed 0x2e7928-0x2e7954: value x 0.01) | 1, 10, 2.00099587 (0x40001051) | 1, 10, 2.00200796 (0x400020e6) | 1, 10, 2.00098491 (0x40001023) |
| 1 | aura radius in steps of 12 world units (Observed 0x2e7860-0x2e7898 and 0x2e7cc8-0x2e7cfc: value x 12) | 1, 6, 1.00099289 (0x3f802089) | 10, 6, 0.300996989 (0x3e9a1c47) | 5, 6, 0.750993967 (0x3f404124) |
| 2 | duration in seconds (Observed: constructor 0x2e7988 stores it as the countdown) | 1, 8, 0.250986993 (0x3e80815e) | 1, 8, 0.250999987 (0x3e808312) | 1, 8, 0.250984997 (0x3e80811b) |
| 3 | unused | 0, 0, 0 | 0, 0, 0 | 0, 0, 0 |
| 4 | mana cost (Observed: manaCost 0x2e7690 calls slot 15) | 1, 25, 3.9999938 (0x407fffe6) | 1, 35, 4.00099373 (0x40800824) | 1, 35, 4.00197172 (0x40801027) |

Every read in the class uses slot 10 (`getStat(stat, level)`), with no cap and no caster
argument: a monster level and a player rank are treated the same.

Worked values (slot 10; identical under round-to-nearest and under truncating single
precision):

| Rank | 53: s0 / s1 / s2 / s4 | 33: s0 / s1 / s2 / s4 | 81: s0 / s1 / s2 / s4 |
|---|---|---|---|
| 1 | 10 / 6 / 8 / 25 | 10 / 0 / 8 / 35 | 10 / 0 / 8 / 35 |
| 10 | 28 / 15 / 10 / 61 | 28 / 6 / 10 / 71 | 28 / 10 / 10 / 71 |
| 20 | 48 / 25 / 13 / 101 | 48 / 9 / 13 / 111 | 48 / 17 / 13 / 111 |

Full ladders, ranks 1 to 20:

- s0, all three ids: 10, 12, 14, ... 48 (10 + 2 per rank; the step excess never reaches a
  rounding boundary within 20 ranks).
- s1: id 53: 6, 7, 8, ... 25. Id 33: 0 for ranks 1-9, then 6, 6, 7, 7, 7, 8, 8, 8, 8, 9, 9.
  Id 81: 0 for ranks 1-4, then 6, 7, 8, 8, 9, 10, 11, 11, 12, 13, 14, 14, 15, 16, 17, 17.
- s2, all three ids: 8, 8, 9, 9, 9, 9, 10, 10, 10, 10, 11, 11, 11, 11, 12, 12, 12, 12, 13, 13.
- s4: id 53: 25 + 4 x (rank - 1). Ids 33 and 81: 35 + 4 x (rank - 1).

#### Cost and limits

- Mana: `manaCost(level)` 0x2e7690 = slot 15 (level, 20) = (float) slot 10 (4, slot 14 (level,
  20)); slot 14 is the base function that returns the level unchanged, so the 20 is not a cap.
  Rank 1 / 10 / 20: 25 / 61 / 101 for id 53, 35 / 71 / 111 for ids 33 and 81. Observed.
- Recast: 30 frames (player+0x4ae, generic cast path).
- `canUse(skill, caster)` 0x2e7224: true only when the caster has no `SpellCriticalHit`
  attached (`creature_findSpellByType(caster, SpellCriticalHit type)` returns null). Because
  the three ids share the effect class, any one of them blocks all three. Observed.
- No weapon, animation or player-state gate in the class. The prediction copy never casts
  (flag bit 0 clear, test in `Player_castSkill` 0x1a42b8). Observed.

#### Behaviour

**Cast** `SkillCriticalHit_cast(skill, level, caster, pos*, facing)` 0x2e74b0: allocates 0x5c
bytes from the pool and, when the allocation succeeded, runs the constructor with (spell,
level, caster, skill). The position and facing arguments are not used. It returns the spell;
the player cast path then attaches it with `creature_addSpell`. No canUse call is made inside
cast. Observed.

**Constructor** `SpellCriticalHit_ctor(spell, level, caster, skill)` 0x2e7988. One shared
draw (the inlined base Spell constructor). Fields:

| Offset | Type | Initial value | Meaning |
|---|---|---|---|
| +0x00 | u8 | level | rank (player) or level argument |
| +0x04 | handle list head | 0 | base Spell |
| +0x08 | Skill* | the skill object used to cast (selects the id and the table) | base Spell |
| +0x0c | Creature* | caster | owner |
| +0x10 | u32 | shared draw (16-bit value) | private generator state |
| +0x14 | ptr | 0x519c28 | virtual table |
| +0x18 | float | (float) slot 10 (2, level) | seconds left |
| +0x1c..+0x57 | embedded light node | linked into the light grid by the constructor (`light_link` 0x148af8). Bytes +0x24, +0x25 = 0; s16 colour quads +0x26, +0x28, +0x2a, +0x2c = 215, 64, 64, 0 and +0x2e, +0x30, +0x32, +0x34 = 215, 64, 64, 0; floats +0x38 = 120.0 (0x42f00000), +0x3c = 6.94444e-05 (0x3891a2b3, 1/120 squared), +0x40 = 120.0, +0x44 = 6.94444e-05, +0x48 = 0; +0x4c float[3] = caster position | presentation |
| +0x58 | u32 | `particleGroup_create()` 0x18e880 (0 when all 16 groups are taken) | presentation |

**Run** `SpellCriticalHit_run(spell, pos*, facing)` 0x2e7acc, once per simulated frame while
attached (the two arguments are copied to the stack and not used). For a player owner the
caller is `Player_updateCast` 0x1a3f70, reached at the end of `Player_run` (0x1ac6a8) only
while the record's hit points are above 0: the first call is in the cast frame, after the
state switch that performed the cast, and the countdown stands still while the owner is at
0 hit points (Observed):

1. `spell+0x18 -= 0.016666666` (0x3c888888). If the result is below 0 the spell destroys
   itself (slot 1 with argument 3) and returns. With the truncating single-precision
   arithmetic of the console's floating-point unit (Inferred: hardware property, not read from
   this executable) a duration of D seconds ends in run call number 60 x D for every D from 8
   to 13; with round-to-nearest arithmetic the counts are 480, 540, 600, 660, 721, 781. The
   destructor 0x3cef88 destroys the light node and clears the handle list; it does not release
   the particle group.
2. Tint the owner (presentation, but it is a write to a creature): owner s16 +0x90 = 68,
   +0x92 = 14, +0x94 = 24, +0x96 = 15 (`SpellCriticalHit_setTint` 0x2e7f58).
3. elapsed = (float) slot 10 (2, level) - spell+0x18. While elapsed <= 2.0 the light follows
   the owner (position = owner position with 60 added to the height; `light_relink`), and
   while elapsed is above 1.0 its colour quads fade: elements +0x28, +0x2a, +0x30, +0x32 =
   trunc((2 - elapsed) x 64), elements +0x26, +0x2e = trunc((2 - elapsed) x 215). After 2.0
   seconds `light_unlink` is called every frame.
4. radius = slot 10 (1, level) x 12 (integer). If radius > 0: `level - k + 14` particles are
   placed on a circle of that radius (k = 1 for id 53, 10 for id 33, 5 for id 81, 1 for any
   other id: the first level of statistic 1), each taking one `Spell_rand` draw for its angle.
   The circle is centred on `net_objOrGhost(owner)`; see Per-machine state.
5. Tint allies: for every entry of `g_alivePlayers` (0x4f8440, count 0x4f8420) in list order,
   P = that slot's player object (record +0x43d8). Skip P == owner. When `g_pvpModeA` is
   non-zero skip P unless owner->slot 22 (P) (same team) is non-zero. If
   (dx x dx + dy x dy) < (float)(radius x radius) (2-D, strict, the product formed in
   integers), write the same four tint values to P.

The run function makes no damage call, changes no statistic and applies no status. Observed
(whole function read in disassembly).

**The bonus itself** is computed on demand by `SkillCriticalHit_critBonusFor(skill, attacker,
ownRank)` 0x2e76c4, whose only three callers are in `damage_apply` (0x1e8d5c, 0x1e8d7c,
0x1e8da4). Call site (damage sequence step 18, 0x1e8d2c-0x1e8db0), executed only when damage
flag 0x40000000 is clear, the attacker is non-null and has object flag 0x40 (player), and the
`noCrit` argument is 0:

```
slot = attacker+0x3c8
a = critBonusFor(SKILL[33], attacker, rank(slot, 33))
b = critBonusFor(SKILL[53], attacker, rank(slot, 53))
c = critBonusFor(SKILL[81], attacker, rank(slot, 81))
critChance += max(a, b, c)            # critChance starts as v1 x 0.01 of a type-0x1d entry
```

`rank(slot, id)` is `player_getSkillRank` 0x1bf330 (first entry with that id in the record's
skill list at record +0x4b08, four bytes per entry {s16 id, s16 rank}, list ended by id -1;
0 when absent).

`critBonusFor(skill, attacker, ownRank)`:

```
level = 0
if ownRank != 0 and attacker has a SpellCriticalHit attached:
    level = ownRank                                   # own buff; the aura is not consulted
else:
    for i in 0 .. g_alivePlayerCount-1:               # list order
        s = g_alivePlayers[i]
        if s == attacker+0x3c8: continue              # not myself
        P = g_players[s].object                       # record +0x43d8
        d = P.pos - attacker.pos
        if not (d.x*d.x + d.y*d.y + d.z*d.z < 1000000.0): continue      # 0x49742400, 3-D
        if g_pvpModeA != 0 and P->slot22(attacker) == 0: continue       # same team only
        if P has no SpellCriticalHit attached: continue
        r = max(rank(s, 53), rank(s, 81), rank(s, 33))
        if r == 0: continue
        R = (float)(skill.slot10(1, r) * 12)          # THIS call's table, the other player's rank
        if not (d.x*d.x + d.y*d.y < R*R): continue    # 2-D, strict
        level = r
        break                                         # first qualifying player wins
level = skill.slot14(level, 20)                       # base: unchanged
if level == 0: return 0.0
return (float) skill.slot10(0, level) * 0.01          # 0x3c23d70a
```

Consequences that follow directly from this code (all Observed in 0x2e76c4):

- The own bonus needs both a non-zero rank in the id being asked about and any attached
  `SpellCriticalHit`. It uses the attacker's current rank, not the level stored in the spell.
- The aura uses the other player's current highest rank among the three ids, not the level
  stored in that player's spell, and evaluates it in the table of the id being asked about.
  Because `damage_apply` asks all three tables and keeps the largest answer, the effective
  aura radius for an ally is the largest of the three statistic-1 values at that rank (the
  id-53 table: (5 + rank) x 12 units, 72 at rank 1, 300 at rank 20), whichever variant the
  caster owns. A ranger below rank 10 or a berserker below rank 5 therefore shows no ring
  (run step 4 uses the caster's own table, radius 0) but still gives allies the bonus inside
  the id-53 radius.
- The first qualifying player in `g_alivePlayers` order ends the search; it is not the best
  one.
- A player whose own buff is active still runs the aura search in the two calls for the ids
  it has no rank in; the maximum of the three answers is used.
- The bonus is the same for own buff and aura: statistic 0 at the chosen level, 10 % at
  rank 1, 28 % at rank 10, 48 % at rank 20.

**What the chance does** (damage sequence step 19, 0x1e8db4-0x1e8e44): if critChance > 0, the
first hit roll succeeded and `noCrit` is 0, one shared draw is taken; when
(float) draw16 < critChance x 65536.0 the running damage is multiplied by 3.0, the crit mark
is set (which later skips the second hit roll), and a player attacker gets a voice cue. A
bonus of 0.48 succeeds for draws 0 to 31457.

**Stacking and refresh.** There is no refresh: canUse refuses while a spell is attached, and
the spell cannot be removed early by anything in the class. Two sources do not add: the three
answers are combined with max, and they are then added to the weapon's own type-0x1d chance.

**Non-player caster.** A monster run function calling slot 2 and attaching the result would
get a spell that tints nearby players and gives nothing: the bonus is only ever asked for a
player attacker, and an aura source must be a slot in `g_alivePlayers`. No monster was found
doing so (the three Skill objects are referenced only from the static initialiser and the
table; Observed with the reference tool). Through a weapon-effect entry (type 0x29) the cast
runs with any creature as caster and the returned spell is attached to nothing: the
constructor still takes its shared draw, links its light at the caster position and takes one
of the 16 particle groups; the spell is never run and never destroyed, so that light and the
0x5c bytes stay for the rest of the level and nobody gets a bonus (Inferred from the code
paths; whether any item carries such an entry is Unknown).

#### Random draws

1. Cast: one shared draw in the Spell constructor (seed of spell+0x10).
2. Every run call with radius > 0: `level - k + 14` draws of the spell's private generator
   (`Spell_rand`), one per ring particle, used as the particle's angle. The count does not
   depend on positions or on the machine.
3. `damage_apply`: the bonus only changes the chance compared against draw 6 of the damage
   sequence (and makes that draw happen when the chance would otherwise be 0). The query
   function itself draws nothing.

#### Presentation only

Ring particles (definition 0x8e5fa0, built by the static initialiser 0x2e7f7c) in the spell's
particle group, whose matrix is the owner's position rotated by `g_simFrame x 118` 16-bit
angle units; a particle is spawned only when the terrain height under it is within 72 units
of the owner's height. The red light for the first two seconds. The tint on owner and allies.
`describeRank` 0x2e7534 formats statistics 0, 2 and 1 (it uses a second text when statistic
1 is 0). Icon getter 0x3cef64. Voice cue on a critical hit (`player_voice`, local slot only).

#### Per-machine state

- `SpellCriticalHit_run` positions the ring on `net_objOrGhost(owner)` (0x2e7cf8): on the
  owner's machine that is the prediction copy. Only the particle-group matrix and the
  terrain-height test that decides whether `particle_spawn` is called use it; the number of
  `Spell_rand` draws is the same on every machine and the private generator feeds nothing
  else. Contained. Observed.
- The aura search and the tint loop walk `g_alivePlayers`, which carries the known caveat in
  docs/player.md (the list can lose the local slot on one machine after the copy dies in
  prediction). A machine in that state would skip its own player as an aura source for the
  other players' attacks and so compute a different critical-hit chance, hence a different
  number of shared draws. Inferred from the two Observed facts.
- `critBonusFor` reads attacker+0x3c8 without testing for a player; its only caller tests
  object flag 0x40 first (0x1e8d2c). Not a hazard as called.
- No camera, local-slot, cosmetic-seed or 0x404468 read in a gameplay decision. The
  prediction copy cannot cast (flag bit 0 clear) and `damage_apply` returns at once for a
  copy attacker.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2e7224 | SkillCriticalHit_canUse | no SpellCriticalHit attached to the caster |
| 0x2e7258 | SkillCriticalHit_ctor | (skill, id): name by id, recast 30, kind 0 |
| 0x2e730c | SkillCriticalHit_initStats | three tables selected by skill+0x64 |
| 0x2e74b0 | SkillCriticalHit_cast | allocates and constructs the spell |
| 0x2e7534 | SkillCriticalHit_describeRank | text only |
| 0x2e7690 | SkillCriticalHit_manaCost | slot 15 (level, 20) |
| 0x2e76c4 | SkillCriticalHit_critBonusFor (proposed) | (skill, attacker, ownRank) -> fraction added to the critical-hit chance |
| 0x2e7988 | SpellCriticalHit_ctor | fields above |
| 0x2e7acc | SpellCriticalHit_run | countdown, light, ring, tint |
| 0x2e7f58 | SpellCriticalHit_setTint | four s16 writes at creature +0x90 |
| 0x2e7f7c | criticalHit_staticInit | particle definition 0x8e5fa0 |
| 0x3cef88 | SpellCriticalHit_dtor | light node destroyed, handle list cleared |
| 0x1e8d2c-0x1e8e44 | part of damage_apply | the three queries, the max, the crit roll |
| 0x1bf330 | player_getSkillRank | record skill-list lookup |
| 0x3c85fc, 0x3c88dc, 0x3c88e4 | Skill slots 10, 14, 15 | base statistic functions |

#### Not determined

- The frame counts above are numbers of run calls; the five call sites of the player cast
  helper were not individually checked to be inside the state switch (they are all inside
  `Player_run` ahead of 0x1ac6a8 by address).
- How a particle group is given back (the destructor does not do it); `particleGroup_create`
  was read, its release path was not.
- Whether any item carries a type-0x29 entry for ids 33, 53 or 81.
- `creature_findSpellByType` was used as documented (exact type match assumed).
- The truncating floating-point behaviour is taken from hardware knowledge, not from the
  executable; both countdown results are given.

### 54 holyshield — SkillHolyShield

#### Identity

| Item | Value | Evidence |
|---|---|---|
| id, name | 54, `holyshield` | `SkillHolyShield_ctor` 0x2e8034 |
| Skill class / virtual table / object | `SkillHolyShield`, 0x519d10, object 0x6e2a60 | Observed |
| kind, flags, recast | 0 (active), 0 (copy may not cast), 30 frames | Observed 0x2e8034 |
| overridden Skill slots | 2 cast 0x2e80fc, 4 describeRank 0x2e819c, 5 manaCost 0x2e82c8, 7 icon 0x3cf0a0, 9 initStats 0x2e80a0; slot 1 canUse is the base (always allowed) | table 0x519d10 |
| effect class | `SpellHolyShield`, 0x28 bytes, virtual table 0x519ce0 (slot 1 dtor 0x3cf0c4 = base only, slot 2 run 0x2e8428, slots 3, 4 base); attached to the caster | Observed |
| other objects | one `GlowingShaft` (0x5c) at the cast; a `LightEffect` (0xbc) on absorbed hits, at most one per 16 frames | Observed 0x2e838c, 0x2e8740 |
| who has it | cleric tree (base level 8, passive mask 0x40). No monster caller found | tree table |
| active / passive | active buff on the caster; it is a **mana shield**: a percentage of every hit is paid from mana instead of hit points | Observed, `Player_takeDamage` 0x1b5628–0x1b5688 |

#### Statistics

Observed in `SkillHolyShield_initStats` 0x2e80a0. Tier 1 only; all lookups are slot 10.

| Stat | Meaning | first, base, step |
|---|---|---|
| 0 | percent of each incoming hit moved from hit points to mana (Observed: 0x2e8810–0x2e8854 returns stat × 0.01; used at 0x1b5664) | 1, 5, 2.99997878 (0x403fffa7) |
| 1 | duration in seconds (Observed: constructor 0x2e83dc–0x2e8410, run 0x2e8474) | 1, 10, 0.250001997 (0x3e800043) |
| 2, 3 | not set | — |
| 4 | mana cost of the cast | 1, 24, 5.99993753 (0x40bfff7d) |

Values, ranks 1–20:

- stat 0: 5 + 3 × (rank − 1) → 5, 32, 62 at ranks 1, 10, 20
- stat 1: 10 10 11 11 11 11 12 12 12 12 13 13 13 13 14 14 14 14 15 15
- stat 4: 24 + 6 × (rank − 1) → 24, 78, 138

#### Cost and limits

- Mana: `manaCost(level)` 0x2e82c8 = slot 15 (level, 20) = (float) getStat(4, level).
- Recast 30 frames. canUse: base, always allowed. Not castable by the prediction copy.
- Nothing stops a second cast while a shield is up (see Stacking).

#### Behaviour

**Cast** (`SkillHolyShield_cast` 0x2e80fc): level' = slot 14 `adjustLevel(level, 20)`
(unchanged); allocate 0x28 bytes; `SpellHolyShield_ctor(spell, level', caster, skill)`;
return the spell (the caller attaches it to the caster). Position and facing arguments
unused. Observed.

**Constructor** (`SpellHolyShield_ctor` 0x2e82fc), in order (Observed):

1. +0x00 level, +0x0c owner = caster, +0x08 skill, +0x04 = 0; one shared draw → +0x10;
   virtual table 0x519ce0.
2. Sound on the owner (presentation).
3. Allocate 0x5c and construct a `GlowingShaft` at the owner's position with (90, 86, 126,
   250) — lifetime 90 frames and a colour. **One more shared draw** (`GameObject_ctor`),
   skipped only if the allocation fails. No gameplay effect.
4. +0x1c = 0.0 (light cooldown), +0x18 = 0.0 (elapsed).
5. +0x20 = (float) getStat(1, level) (duration in seconds).
6. +0x24 = `particleGroup_create()`.

`SpellHolyShield` layout (0x28 bytes):

| Offset | Type | Meaning |
|---|---|---|
| +0x00 | s8 | level |
| +0x04 | handle back-list | link into the owner's spell list |
| +0x08 | Skill* | |
| +0x0c | Creature* | owner |
| +0x10 | u32 | private generator (particles only) |
| +0x14 | ptr | virtual table 0x519ce0 |
| +0x18 | float | elapsed seconds |
| +0x1c | float | seconds until another LightEffect may be created (≤ 0 = allowed) |
| +0x20 | float | duration in seconds |
| +0x24 | handle | particle group |

**Run** (`SpellHolyShield_run` 0x2e8428), once per frame from the owner's spell update (for a
player: `Player_updateCast`, only while alive). Observed:

```
elapsed  += 0.0166666657      (0x3c888888)
cooldown -= 0.0166666657
if duration < elapsed:  destroy the spell (slot 1, argument 3)
else:
    particle-group matrix = owner position and facing        (presentation)
    owner colour flash: +0x90=21, +0x92=28, +0x94=115, +0x96=55,
                        +0x98=21, +0x9a=28, +0x9c=115, +0x9e=55   (rewritten every frame)
```

Lifetime in run calls (single-precision accumulation, simulated): the destroying call is the
600th for 10 s, 660th for 11 s, 721st for 12 s, 781st for 13 s, 841st for 14 s, 901st for
15 s. The shield works for every hit taken before that call.

**What the shield does to incoming hits.** The only reader of the spell from outside is
`Player_takeDamage` (Player slot 2, 0x1b5330; amount in f12, this, attacker, flags), which
every hit on a player goes through. After that function's own early returns and after the
block handling (which may already have set the amount to 0 or half), Observed
0x1b5628–0x1b56a4:

```
S = creature_findSpellByType(player, SpellHolyShield)        -- first match from the list head
if S != null and record.mana (+0xc0) > 0.0:
    f        = SpellHolyShield_absorb(S)                      -- 0x2e8534, see below
    absorbed = amount * f                                     -- single precision
    amount   = amount - absorbed
    mana     = record.mana - absorbed;   record.mana = mana
    if amount < 0.0: amount = 0.0
    if mana   < 0.0: record.mana = 0.0
pending damage (+0xc8) += amount;  pending flags (+0x2dc) |= flags;  ...
```

`SpellHolyShield_absorb(S)` 0x2e8534 (proposed name), in order (Observed):

1. 241 particles on random sample points of the owner's model (private generator; see
   Random draws).
2. If S+0x1c ≤ 0.0: allocate 0xbc and construct a `LightEffect` at owner position + (0, 0,
   60.0) with float arguments 64.0, 64.0, 125.0 and (on the stack) 120.0, 60.0, 0.5,
   0.263001978 — **one shared draw** in `GameObject_ctor` (none if the allocation fails).
   Then, allocation or not, S+0x1c = 0.263001978 (0x3e86a832). With the per-frame decrement
   the next light is possible after 16 run calls.
3. Return (float) getStat(0, level) × 0.01 (0x3c23d70a): 0.0499999970 at rank 1, 0.319999993
   at rank 10, 0.620000005 at rank 20.

Consequences, all Observed from the code above:

- The split is by percentage, one mana point per hit point absorbed, with no cap by the mana
  left: when the absorbed part exceeds the remaining mana the hit is still reduced by the full
  percentage and mana becomes 0. After that the shield is inert (the test is mana > 0) until
  mana regenerates, but it keeps running and keeps its duration.
- It applies to every call of the player's slot 2, whatever the damage type or flags
  (melee, spell, damage over time, falling), and it is applied after blocking.
- It is consulted even when the amount is already 0 (particles, possibly the light and its
  shared draw; no mana change).
- A negative amount would be turned into 0 and add mana (amount × f is subtracted from
  mana); no caller passing a negative amount was looked for.
- Armour, resistances and criticals are not involved here: they were applied by the damage
  function before slot 2 was called.
- Only `Player_takeDamage` looks for the spell. `Creature_takeDamage` 0x116638 does not, so
  on a non-player owner the spell is purely visual.

**Stacking / refresh.** A second cast attaches a second SpellHolyShield (head of the list,
so it is the one `creature_findSpellByType` returns). Only one spell is consulted per hit, so
percentages do not add; the newest spell's level decides while it lasts, then the older one
takes over for the rest of its own duration. There is no refresh of an existing spell.

**End conditions.** elapsed > duration (above); destruction of the owner. Death does not end
it: a dead player's spells are not run, so the timer is frozen until revival.

**Non-player caster.** Through the weapon-proc path: the spell is constructed (two shared
draws, sound, shaft, particle group) with the attacker as owner, never attached, never run,
never found by a damage function — no effect, and the 0x28 bytes are not freed (Inferred
leak). If attached to a non-player by some caller (none found), run would tint the creature
for the duration and nothing else. No +0x3c8 read exists in this class.

**Prediction copy.** Cannot cast. The copy's spell list starts empty, so
`Player_takeDamage` on the copy finds no shield and applies the full amount to the copy's
pending damage and leaves mana alone; the shared draw of the LightEffect therefore never
happens in prediction.

#### Random draws

In execution order:

1. Constructor: one shared draw (private seed), then one shared draw for the GlowingShaft.
2. Each absorbed hit (`SpellHolyShield_absorb`): 241 iterations, each one private draw
   (sample-point index = value modulo the model's sample-point count) followed by three
   private draws repeated until the point (each 2 × v/65536 − 1) lies inside the unit sphere
   (velocity = point × 37.0). Then, when the cooldown allows, **one shared draw** in the
   LightEffect's `GameObject_ctor`.
3. Run: none.

The private generator feeds particles only. Note the shared draw in step 2 happens inside
the damage call chain (after whatever draws the damage function made for that hit).

#### Presentation only

Cast sound; the GlowingShaft; the blue colour flash rewritten every frame; the particle
group following the owner; 241 particles per absorbed hit (definition 0x8e5ff0, registered by
`holyShield_staticInit` 0x2e886c); the LightEffect flash. The particle group is not released
by the destructor.

#### Per-machine state

- No camera, local-slot, audio, cosmetic-seed or option read in the class or in the shield
  block of `Player_takeDamage`. The record read there uses the player's own +0x3c8 (the
  function is the Player class's slot 2).
- `Player_takeDamage` has early returns ahead of the shield that test global and local-menu
  state (0x1b5330 head, `net_isLocalSlot` for closing a local menu); they belong to the
  player area and were not analysed here.
- None found in the skill itself.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2e8034 | SkillHolyShield_ctor | recast 30, name |
| 0x2e80a0 | SkillHolyShield_initStats | table above |
| 0x2e80fc | SkillHolyShield_cast | allocate and construct |
| 0x2e819c | SkillHolyShield_describeRank | stats 0 and 1 into text (two wordings, by stat 1 > 1) |
| 0x2e82c8 | SkillHolyShield_manaCost | slot 15 (level, 20) |
| 0x2e82fc | SpellHolyShield_ctor | above |
| 0x2e8428 | SpellHolyShield_run | timers, tint, end |
| 0x2e8534 | SpellHolyShield_absorb (proposed) | particles, light, returns the absorbed fraction |
| 0x3cf0c4 | SpellHolyShield_dtor | base Spell destructor |
| 0x1b5330 (0x1b5628–0x1b56a4) | Player_takeDamage | the only caller of 0x2e8534; the mana-for-damage split |
| 0x11a710 | creature_findSpellByType | first match from the list head |
| 0x116638 | Creature_takeDamage | checked: no shield lookup |

#### Not determined

- The early-return conditions at the head of `Player_takeDamage` (which hits never reach the
  shield) — player area.
- Whether the damage function reports the pre-shield or post-shield amount in floating
  damage numbers.
- `LightEffect_ctor` argument meanings (radius, colour, fade) beyond their values.
- Which item data carry a type-0x29 entry with id 54.

### 55 healing — SkillHealing

(One class, two ids: 55 `healing` and 86 `shamanhealing`. Everything below applies to both; only
the statistic tables and the name differ, chosen by skill+0x64 in the constructor and in
initStats.)

#### Identity

| Item | Value | Evidence |
|---|---|---|
| ids | 55 (name `healing`), 86 (name `shamanhealing`) | Observed, `SkillHealing_ctor` 0x2e8b3c: the id argument is stored at skill+0x64 and selects the name; any other id leaves the name null |
| Skill class / virtual table | `SkillHealing`, 0x519e50 | Observed 0x2e8b3c |
| Skill objects | id 55 at 0x6e2ac8, id 86 at 0x6e3760 | table |
| kind (+0x08) | 0 (ordinary active) | Observed 0x2e8b3c |
| flags (+0x04) | 0: the prediction copy may not cast it | Observed 0x2e8b3c |
| recast (+0x0c) | 30 frames | Observed 0x2e8b3c |
| overridden Skill slots | 2 cast 0x2e8cf8, 4 describeRank 0x2e8d98, 5 manaCost 0x2e8e94, 7 icon 0x3cf214, 9 initStats 0x2e8bcc; slot 1 canUse is the base (always allowed) | Observed, table 0x519e50 |
| effect class | `SpellHealing`, 0x24 bytes, virtual table 0x519e20 (slot 1 dtor 0x3cf238 = base Spell destructor only, slot 2 run 0x2e90b8, slots 3 and 4 base) | Observed |
| side object | one `GlowingShaft` (GameObject, 0x5c bytes, virtual table 0x50ec68), presentation | Observed 0x2e8f5c |
| who has it | 55: cleric tree (base level 8, needs a rank in skill 16). 86: shaman tree (base level 10, needs a rank in skill 88). Monsters Bubo, FemaleDarkElf, Kobold, Orc cast id 55 | tree tables; monster run functions |
| active / passive | active, instant, no cast animation of its own | |

#### Statistics

Observed in `SkillHealing_initStats` 0x2e8bcc. Tier 1 is written only when skill+0x64 is 55 or
86; tier 2 is written unconditionally and is the same for both ids.

| Stat | Meaning | Tier 1 id 55: first, base, step | Tier 1 id 86: first, base, step | Tier 2 (both): first, base, step |
|---|---|---|---|---|
| 0 | percent of the owner's own maximum hit points restored over the whole spell (Observed: constructor 0x2e8fbc–0x2e90a0) | 1, 30, 3.50096989 (0x40600fe4) | 1, 30, 3.50297999 (0x406030d3) | 1, 15, 5.0 (0x40a00000) |
| 1 | radius in units of 12 world units (Observed: run 0x2e9108–0x2e9140) | 1, 5, 0.333995998 (0x3eab0186) | 1, 5, 0.333999991 (0x3eab020c) | 1, 5, 0.399999976 (0x3ecccccc) |
| 2 | percent of the *recipient's* maximum hit points restored to each other recipient (Observed: run 0x2e92cc, 0x2e94f4) | 1, 20, 4.00298882 (0x4080187c) | 1, 20, 4.00198555 (0x40801044) | 1, 10, 4.0 (0x40800000) |
| 3 | not set (first 0, base 0, step 0) | — | — | none (0xffff) |
| 4 | mana cost | 1, 55, 6.00197458 (0x40c0102d) | 1, 72, 7.00096989 (0x40e007f2) | none (0xffff) |

Which lookup each use applies (all through slot 12 `getStatFor(stat, level, owner, cap)`, which
picks slot 10 for an owner with the player flag and slot 11 otherwise):

| Use | Call | Player owner | Non-player owner |
|---|---|---|---|
| self amount, constructor | stat 0, cap 10 (player branch, 0x2e8fe4) or cap 20 (other branch, 0x2e9054) | tier 1, cap ignored | tier 2, level clamped to 20 |
| radius, every frame | stat 1, cap 20 (0x2e90bc) | tier 1, cap ignored | tier 2, level clamped to 20 |
| amount for others, every frame per recipient | stat 2, cap 20 (0x2e92d8, 0x2e94fc) | tier 1, cap ignored | tier 2, level clamped to 20 |
| mana | slot 15 with (level, 14) = (float) slot 10 (4, level) | tier 1 | not used |

Worked values (same integers for ids 55 and 86 at every rank 1–20 for stats 0, 1, 2; the two
step constants differ too little to change a rounding):

| Rank | stat 0 | stat 1 (radius = ×12) | stat 2 | stat 4 id 55 | stat 4 id 86 |
|---|---|---|---|---|---|
| 1 | 30 | 5 (60) | 20 | 55 | 72 |
| 10 | 62 | 8 (96) | 56 | 109 | 135 |
| 20 | 97 | 11 (132) | 96 | 169 | 205 |

Full tier-1 rows, ranks 1–20: stat 0 = 30 34 37 41 44 48 51 55 58 62 65 69 72 76 79 83 86 90 93
97; stat 1 = 5 5 6 6 6 7 7 7 8 8 8 9 9 9 10 10 10 11 11 11; stat 2 = 20 + 4 × (rank − 1).

Tier 2 (non-player owner; level above 20 counts as 20; level 0 gives 0 for everything):
stat 0 = 15 + 5 × (level − 1) → 15 at 1, 60 at 10, 110 at 20; stat 1 = 5 5 6 6 7 7 7 8 8 9 9 9
10 10 11 11 11 12 12 13 for levels 1–20; stat 2 = 10 + 4 × (level − 1) → 10, 46, 86.

#### Cost and limits

- Mana: `manaCost(level)` 0x2e8e94 = slot 15 (level, 14) = (float) `getStat(4, level)`. Id 55:
  round(55 + 6.00197458 × (rank − 1)) = 55, 61, 67, … +6 per rank: 55 at rank 1, 109 at 10,
  169 at 20. Id 86: round(72 + 7.00096989 × (rank − 1)) = 72 at rank 1, 135 at 10, 205 at 20.
  Observed.
- Recast 30 frames (player+0x4ae), set by `Player_castSkill`.
- canUse is the base function 0x3c8218 (always true). No weapon, state or target requirement.
  Observed (table 0x519e50 slot 1).
- The prediction copy cannot cast it (flag bit 0 clear), so the constructor never runs for the
  copy through the player path.
- Nothing prevents casting a second one while the first is running: the two spells then run
  side by side and both add hit points (Observed: neither cast nor constructor looks for an
  existing `SpellHealing`; the three monster call sites that check do so themselves).

#### Behaviour

**Cast** (`SkillHealing_cast` 0x2e8cf8; a0 skill, a1 level, a2 caster, a3 pos*, t0 facing).
The position and facing arguments are not used. Steps (Observed):

1. level' = slot 14 `adjustLevel(level, 14)` — the base function, returns level unchanged.
2. Allocate 0x24 bytes from the object pool; if that fails return null.
3. `SpellHealing_ctor(spell, level', caster, skill)`; return the spell.

The caller attaches it (`Player_castSkill` → `creature_addSpell(player, spell)`); the spell's
owner (+0x0c) is whatever was passed as the caster.

**Constructor** (`SpellHealing_ctor` 0x2e8ec8), in order (Observed):

1. +0x00 = level (stored as a byte, read back signed), +0x04 = 0, +0x08 = skill, +0x0c = owner.
2. One draw of the shared generator; +0x10 = the 16-bit result (private generator seed).
   Virtual table = 0x519e20.
3. Start a sound on the owner (resource looked up in the effects archive; volume 1.0).
   Presentation.
4. Allocate 0x5c bytes and construct a `GlowingShaft` at the owner's position (owner+0x10..18
   copied) with arguments (90, 250, 200, 100): lifetime 90 frames, three colour components.
   `GlowingShaft_ctor` 0x202ff0 calls `GameObject_ctor`, so this is **one more draw of the
   shared generator** (skipped only if the allocation fails). The shaft sets its flags
   |= 0x4009, counts +0x4c down from 90 once per run and deletes itself at 0
   (`GlowingShaft_run` 0x2030a8); it has no gameplay effect.
5. +0x20 = `particleGroup_create()` (presentation handle; may be 0).
6. +0x18 = 0.0 (elapsed seconds).
7. +0x1c = heal per frame for the owner itself:
   - owner has the player flag (object flags & 0x40): s = getStatFor(0, level, owner, 10);
     M = player record[owner+0x3c8] +0xb0 (maximum hit points);
   - otherwise: s = getStatFor(0, level, owner, 20); M = owner+0x22c.
   - value = (M × 0.014750047) × ((float)s × 0.01), all single precision, in exactly that
     grouping: first the two products, then their product. Constants 0x3c71aa2e and
     0x3c23d70a. (0x2e8ffc–0x2e90a0)

   This is fixed at construction: later changes of the owner's maximum hit points do not
   change the owner's own per-frame amount.

`SpellHealing` layout (0x24 bytes):

| Offset | Type | Meaning |
|---|---|---|
| +0x00 | s8 | level |
| +0x04 | handle back-list | link into the list it is attached to |
| +0x08 | Skill* | the SkillHealing object (55 or 86) |
| +0x0c | Creature* | owner: centre of the effect and the "self" recipient (raw pointer, not a handle) |
| +0x10 | u32 | private generator state |
| +0x14 | ptr | virtual table 0x519e20 |
| +0x18 | float | elapsed time in seconds, starts 0 |
| +0x1c | float | per-frame amount for the owner |
| +0x20 | handle | particle group (presentation) |

**Run** (`SpellHealing_run` 0x2e90b8), once per simulated frame of the creature it is attached
to: for a non-player that is the first thing `Creature_run` does (slot 17 call at the top of
0x112948); for a player it is `Player_updateCast` 0x1a3f70, called near the end of
`Player_run` (0x1ac6a8) and **only while the player's record hit points are above 0** — a
dead player's attached spells are frozen, not ended. The position and facing arguments are
ignored. In order (Observed):

1. r = 12 × getStatFor(1, level, owner, 20) (integer); r2 = r × r (integer, then converted to
   float for the comparisons).
2. Recipients and healing — one of two branches, chosen by the **owner's** player flag:

   **Owner is a player** (0x2e9150–0x2e93bc):
   - Build a list of player slots: for i in 0 … `g_alivePlayerCount` − 1 (count re-read each
     iteration), slot = `g_alivePlayers[i]`, P = record[slot]+0x43d8 (that player's object):
     - if `g_pvpModeA` ≠ 0: skip unless owner→slot 22 `isSameTeam(P)` is non-zero. That
       function is false for the prediction copy, false when the owner's team byte (record
       +0x4c24) is negative, and otherwise true when both team bytes are equal. The team
       byte has three writers (Observed): the net launch sets it to the **slot number** for
       every player (`net_launchUpdate`, store at 0x1373d8), the character import screen
       sets it to the slot number in PvP mode A and to 0 otherwise (0x220668 / 0x22067c). So
       in PvP mode A every player is alone on its team and Healing heals **only the
       caster** (Inferred from those writers); outside PvP mode A the team is not consulted
       at all.
     - skip unless (dx² + dy² + dz²) ≤ r2, the difference of the two object positions on all
       **three** axes (the owner passes with distance 0).
     - append slot (list order = `g_alivePlayers` order; at most 4).
   - For each listed slot, in order:
     - hp = record+0xac, max = record+0xb0. Only if hp + 1.0 ≤ max:
       - if P is the owner: hp += spell+0x1c;
       - else: s2 = getStatFor(2, level, owner, 20); hp += (max × 0.014750047) × ((float)s2 ×
         0.01) with the recipient's own maximum (same grouping as in the constructor).
       - The sum is stored without a clamp, so the last addition can leave hp above max by up
         to (per-frame amount − 1). `Player_regenHealth` 0x1b3b90 does not pull it back (it
         only clamps while hp < max on entry).
     - Independently of the hp test, if spell+0x18 < 0.129939914 (0x3e050ef8): write the
       colour flash of P: s16 +0x90 = 53, +0x92 = 20, +0x94 = 13, +0x96 = 50, +0x98 = 53,
       +0x9a = 20, +0x9c = 13, +0x9e = 50.
   - A player-owned Healing touches players only: pets, charmed monsters and other creatures
     are never recipients.

   **Owner is not a player** (0x2e93c4–0x2e95b0):
   - Nothing happens unless (owner flags & 0x28) == 0x20, i.e. the owner is a creature and
     not dead.
   - `world_collectObjectsInBox(min, max, out, 128)` with min = owner position − r and max =
     owner position + r on all three axes (at most 127 objects, grid order).
   - For each object O in that order:
     - skip unless O is the owner, or owner→slot 21 `isAlly(O)` is non-zero (creature or
       player, not dead, not the prediction copy, creature flag 0x800 clear, same team by
       slot 37, and not "both are players in PvP mode A"; some classes override slot 21,
       e.g. Kobold 0x280434);
     - skip if (dx² + dy²) > r2 (two axes only here);
     - if O is the owner: O+0x228 += spell+0x1c; else s2 = getStatFor(2, level, owner, 20)
       (tier 2, cap 20) and O+0x228 += (O+0x22c × 0.014750047) × ((float)s2 × 0.01).
       **No test against the maximum and no clamp**: a creature's hit points can be pushed
       above its maximum, and nothing in `Creature_run` clamps them (no store to +0x228
       there).
     - if spell+0x18 < 0.129939914: the same eight colour-flash stores on O.
   - If O is a player object (an ally of the owner, e.g. the owner is charmed), the write
     goes to the player object's +0x228, which is only a mirror: `Player_run` overwrites it
     from the record every frame (0x1a527c–0x1a5280). So a creature-owned Healing has no
     lasting effect on a player (Observed store; Inferred consequence).
3. Particles (presentation; only when r ≥ 1): see "Random draws" for the generator use.
4. spell+0x18 += 0.0166666657 (0x3c888888). If the new value > 1.12993991 (0x3f90a1df): call
   the spell's slot 1 with 3 (destroy and free).

**Duration.** With single-precision accumulation the test first succeeds on the 68th call
(the stored value is then 1.13333249). So the spell heals on **68 consecutive frames**. For
a player cast the first call is in the cast frame itself (the cast happens in the action
state machine, which `Player_run` executes before the `Player_updateCast` call; Inferred from
the function layout). The colour flash is rewritten on the first 8 calls (elapsed values 0 …
0.11666666).

**Totals.** Owner: 68 × M × 0.014750047 × s/100 = 1.003 × s % of M; e.g. rank 1: 30.09 % of
maximum, rank 20: 97.3 %. Each other recipient: 1.003 × stat 2 % of its own maximum, as long
as it stays in range and (players) below maximum − 1.

**Non-player caster, by path.**

- *Monster cast* (Observed in `Kobold_run` 0x27f52c, states 8 and 9, on animation event bit
  1): the monster first looks for a revivable corpse of its class within 200
  (`creature_findCorpseOfClass`) and revives it if found; otherwise A =
  `creature_findWoundedAlly(200, self)` — the first object in grid order inside the box
  self ± 200 with (flags & 0x2a) == 0x20, hit points below half its maximum and
  self→isAlly(A) true. If A exists and `creature_findSpellByType(A, SpellHealing)` finds
  nothing, it calls `cast(level = self→slot 35, caster = A, &selfPos, selfFacing)` on
  `g_skillTable[55]` and `creature_addSpell(A, spell)`. So the monster passes **the wounded
  ally as the caster argument**: the ally is the spell's owner and centre, the statistics are
  tier 2 at the casting monster's level (slot 35 = (int)(`g_levelMonsterLevel` × 0.3), capped
  at 20 inside slot 11), and the caster monster itself is healed only if it is an ally of A
  inside A's radius. FemaleDarkElf (0x259a98, call near 0x25a374) and Bubo (0x248598, radius
  360) do the same and attach to the ally. **Orc** (0x2a1848, call at 0x2a2998, radius 400)
  passes the ally as caster too but attaches the spell to **itself** and does not check for
  an existing SpellHealing, so several can run on one ally and the spell's lifetime hangs on
  the Orc's spell list while its +0x0c points at the ally (raw pointer; the run function
  only re-tests the ally's dead flag).
- At monster level 0 (level scale below 3.34) every statistic is 0: r = 0, nothing is
  healed, no particles; the spell still lives 68 frames.
- *Weapon proc* (damage descriptor entry type 0x29): the spell is constructed with the
  attacker as owner (two shared draws, sound, shaft, particle group) but the returned object
  is not attached to anything, so its run function is never called: **no healing happens**,
  and the 0x24-byte spell is never freed (Observed discard at 0x1e8fa0; Inferred leak).

**Prediction copy.** Not castable by the copy (flag bit 0 clear). Attached spells are not
cloned to the copy (`Creature_clone` starts the list empty), so run never executes for it.
`world_collectObjectsInBox` skips the copy and `isSameTeam` / `isAlly` reject it, so the copy
is never a recipient in the creature branch. In the player branch recipients come from the
records; see Per-machine state.

#### Random draws

In execution order:

1. Constructor: one shared draw — the spell's private seed.
2. Constructor: one shared draw inside `GameObject_ctor` for the GlowingShaft (not when its
   allocation fails).
3. Run, every frame in which r ≥ 1, after the healing: n = level − (s16 at skill+0x10) + 5
   draws of the spell's private generator (`Spell_rand`), one per particle position; with
   the tables above skill+0x10 (tier-1 first level of stat 1) is 1, so n = level + 4 (no
   draws when n ≤ 0). Each value is used as a 16-bit angle; the point is r from the centre
   in that direction. Nothing else ever reads this generator, so these draws affect
   presentation only. The count does not depend on the particle being spawned or not.

No draw of the cosmetic generator or of 0x404468 in these functions.

#### Presentation only

Sound on the owner at construction; the GlowingShaft column (90 frames); a particle group
whose matrix is set each frame to the position of `net_objOrGhost(owner)` rotated by
(g_simFrame × 95) as a 16-bit angle; per frame n ring particles (definition 0x8e6040) at
radius r, each spawned only if the terrain height under it is within ±72 of that object's
height; the green colour flash on recipients during the first 8 frames. The particle
definitions are registered by `healing_staticInit` 0x2e979c.

#### Per-machine state

- `net_objOrGhost(owner)` (0x2e95cc) gives the particle centre; on the owner's machine that
  is the prediction copy. Presentation only: the number of `Spell_rand` draws does not depend
  on it, and the private generator feeds nothing else. Observed.
- The player branch walks `g_alivePlayers` / `g_alivePlayerCount` and compares record
  +0x43d8 with the owner. `docs/player.md` (per-machine item 1) records that the copy's death
  can leave this machine's own slot out of the list for one simulated frame; in that frame
  this machine would skip one recipient (hit points diverge). Inherited hazard, not specific
  to this spell.
- The +0x3c8 reads (constructor 0x2e8ffc, and through the record table in run) are all
  behind the owner's player-flag test. Observed.
- A non-player owner never changes a player's record (see the mirror note above).
- No camera, local-slot, audio or local-option read feeds a gameplay value. None found
  beyond the above.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2e8b3c | SkillHealing_ctor | sets recast 30, kind 0, id, name by id |
| 0x2e8bcc | SkillHealing_initStats | tables above |
| 0x2e8cf8 | SkillHealing_cast | allocates and constructs SpellHealing |
| 0x2e8d98 | SkillHealing_describeRank | formats stats 0, 1, 2 (slot 10) into the rank text |
| 0x2e8e94 | SkillHealing_manaCost | slot 15 (level, 14) |
| 0x2e8ec8 | SpellHealing_ctor | above |
| 0x2e90b8 | SpellHealing_run | above |
| 0x3cf238 | SpellHealing_dtor | base Spell destructor (unlink, free) |
| 0x2e979c | healing_staticInit | particle definitions |
| 0x202ff0, 0x2030a8 | GlowingShaft_ctor / _run | 90-frame presentation object; one shared draw |
| 0x27f52c | Kobold_run (states 8, 9) | monster call site read in full |
| 0x259a98, 0x248598, 0x2a1848 | FemaleDarkElf / Bubo / Orc run | call sites read (arguments and attach target only) |
| 0x10f190, 0x10f008 | creature_findWoundedAlly / creature_findCorpseOfClass | target choice of the monsters |
| 0x119400, 0x10de10 | Creature_isAlly / Creature_isSameTeam | recipient filters |
| 0x3c85fc, 0x3c8690, 0x3c87f0, 0x3c88e4 | Skill slots 10, 11, 12, 15 | formulas confirmed |
| 0x1b3b90 | Player_regenHealth | checked for a clamp of hit points above maximum (none in that case) |
| 0x1a3f70 | Player_updateCast | runs a player's attached spells (slot 17), only while alive |

#### Not determined

- Whether any other code clamps a player's record hit points back to the maximum after an
  overshoot (only `Player_regenHealth` was checked).
- Whether a team game mode exists that gives two players the same team byte (only the three
  writers named above were found; with them no two players ever share a team in PvP mode A).
- Whether the particle group handle taken in the constructor is released when the spell ends
  (the destructor does not release it; group recycling was not read). Presentation only.
- Which item data, if any, carry a type-0x29 entry with id 55 or 86.
- The Orc, Bubo and FemaleDarkElf state machines around their call sites were read only far
  enough to establish the arguments, the radius and the attach target.

### 56 coneoffrost — SkillConeOfFrost

#### Identity

- Id 56, internal name `coneoffrost`. Skill class `SkillConeOfFrost`, virtual table
  0x519f08, static object 0x6e2b30 (`g_skillTable[56]` at 0x41b250), constructor 0x2e9848.
  **Kind 1 (channelled)** (+0x08 = 1, 0x2e9848), flags 0, recast 30 frames.
- Creates one `SpellConeOfFrost` per cast: a `Spell`, size 0x58, virtual table 0x519ed8
  (slots: 1 destructor 0x2e9c90, 2 run 0x2e9d10, 3 and 4 the `Spell` base functions). The
  cast function returns it; the caller attaches it.
- While it runs the spell creates `DummyDamager` objects: size 0x74, virtual table 0x50ea28,
  base classes `GameObject` > `Projectile`; slots 1 destructor 0x3c5a98, 4 run 0x1ee330,
  5 draw 0x201fa0 (empty), 6 touched 0x1ee7b0. All damage is done by these.
- Players: wizard tree, base level 25, prerequisite skill 14.
- Monsters: Tormentor (`Tormentor` run 0x287db0, AI state 8): on animation event bit 1 it
  calls slot 2 with level = own slot 35 and attaches the result with `creature_addSpell`;
  on animation event bit 2 it calls `creature_removeSpellByType` with the
  `SpellConeOfFrost` type descriptor (0x3cf35c). The breath lasts between those two events.

#### Statistics

`SkillConeOfFrost_initStats` 0x2e98bc. Tier 2 is "none" for every statistic; statistic 3 is
unused (all zero).

| Stat | Meaning | Tier 1: first, base, step |
|---|---|---|
| 0 | cold damage per second if every projectile hits; each projectile carries stat 0 × 8/60 (Observed 0x2ea230–0x2ea274) | 1, 350, 11.000791 (0x4130033d) |
| 1 | range and speed bonus in percent (Observed 0x2e9db4–0x2e9dfc) | 1, 1, 3.999971 (0x407fff86) |
| 2 | total cone angle in degrees (Observed 0x2e9d74–0x2e9dd0) | 1, 20, 1.0009539 (0x3f801f42) |
| 4 | mana per second (0x2e9ad4) | 1, 48, 0.99997395 (0x3f7ffe4b) |

Every read in the spell is **slot 10** (tier 1) with the level byte stored in the spell;
the caster's type is never consulted, so the Tormentor uses the same table at its monster
level.

| Rank / level | 1 | 10 | 20 |
|---|---|---|---|
| stat 0 → per projectile trunc(stat 0 × 0.13333333) | 350 → 46 | 449 → 59 | 559 → 74 |
| stat 1 → scale = stat 1 × 0.01 + 1.0 | 1 → 1.01 | 37 → 1.37 | 77 → 1.77 |
| stat 2 → spread amplitude trunc(stat 2 × 182.04443) | 20 → 3640 | 29 → 5279 | 39 → 7099 |
| stat 4 | 48 | 57 | 67 |

Exact for ranks 1..20: stat 0 = 350 + 11·(rank − 1), stat 1 = 1 + 4·(rank − 1),
stat 2 = 20 + (rank − 1), stat 4 = 48 + (rank − 1). The rank description (0x2e99d0) prints
the `getStatRange(0.2, stat 0)` range, stat 2 and stat 1.

#### Cost and limits

- Mana: slot 5 = slot 15(rank, 1) = (float) getStat(4, rank), **per second**: 48, 57, 67 at
  ranks 1, 10, 20. Charged as cost × 0.016666666 on the cast frame (`Player_castSkill`
  0x1a4640–0x1a4670) and on every later frame the player stays in the casting state with
  cast phase 2 (0x1ab644–0x1ab6bc).
- To start, the player needs mana ≥ cost × 0.5 (for a skill of kind 1 the starting check
  halves the cost; 0x1a6f84–0x1a6f98) and, like every held ability, mana > 1.0.
- Recast 30 frames, set by `Player_castSkill` when the spell is created; the counter runs
  down while the channel is held.
- canUse: base function, always 1; it is asked again on the first frame of the casting
  state (0x1ab5fc–0x1ab634).
- The prediction copy never casts it (flag bit 0 clear).

#### Behaviour

**When a channelled spell starts and ends for a player** (Observed in `Player_run` state 2
and state 5, 0x1a6c30–0x1a7050 and 0x1ab5d4–0x1ab7e4, in `Player_castSkill` 0x1a42b8 and in
`Player_updateCast` 0x1a3f70; common to every kind-1 skill).

The ability record of a `Skill`-object ability is created zeroed with its kind byte copied
from skill+0x08 (0x1d32e4), so its cooldown field is 0 and its kind is 1.

```
frame A (state 2, neutral): button of the ability held (pad word +8 & record mask +0x4a80),
        cooldown +0x4ae == 0, mana > 1.0, mana >= manaCost(rank) * 0.5, the general gates
        of docs/player.md hold
        -> state +0x58c = 5, +0x448 = g_simFrame, cast phase +0x47b stays 0
frame A+1 (state 5, phase 0): canUse(player) or back to state 2;
        no animation track with flag 0x8000 yet -> anim_start(0.1 s blend-in, cast animation of
        the weapon class, flags 0x8003); phase = 1
following frames (phase 1): idx = anim_findTrackByFlag(player+0x114, 0x8000);
        when track[idx].weight (player+0x124 + 0x20*idx) >= threshold:
            phase = 2; Player_castSkill(player, record); forced-ability pointer +0x488 = 0
        threshold = 1.0 offline, 0.5 when g_networkMode != 0            (0x1ab6f4–0x1ab7c8)
cast frame, inside Player_castSkill: level = rank (Player slot 39);
        spell = cast(level, player, &handMidpoint, aimFacing)  -> SpellConeOfFrost
        creature_addSpell(player, spell); handle_link(&player+0x588, &spell+4, spell)
        +0x4ae = 30; mana -= manaCost(rank) * 0.016666666
every frame in state 5 with phase 2: mana -= manaCost(rank) * 0.016666666;
        if the animation status word (+0x11a) has no 0x8000 bit: phase = 0, state = 2
every frame on which the player record's hit points (+0xac) are > 0.0, later in Player_run
(Player_updateCast, test and call at 0x1ac694–0x1ac6a8):
        mid = midpoint of model attach points 0 and 1; if |mid.z - player.z| > 58: mid.z = player.z + 58
        player.slot17(&mid)   -> run(spell, &mid, player.facing) for every attached spell
        if forced-ability pointer +0x488 != 0: return
        keep = button held and state == 5 and mana > 0.0
        if not keep:
            idx = anim_findTrackByFlag(player+0x114, 0x8000)
            if idx < 0 or track[idx].weight >= 1.0:
                fade the track out (life clamped to 1.0, life rate -0.058333334);
                phase = 0; if state == 5: state = 2
                if the handle +0x588 holds a spell: spell.slot1(3)   # destroy and free
```

So, for a player:

- The spell is created on the frame the cast animation's blend weight reaches 1.0 (offline)
  or 0.5 (net game). The weight rises from 0 by 1/(0.1 × 60) per animation tick, so this is
  about 6 (offline) or 3 (net) ticks after the track is started, which is one frame after
  the state change (**Inferred** from the description of `anim_start` in `docs/engine.md`;
  the exact tick on which the float sum crosses the threshold was not computed).
- The spell runs for the first time on its creation frame (`Player_updateCast` comes after
  the state switch in the same `Player_run`) and then once per frame.
- It ends — is destroyed by `Player_updateCast` — on the first frame on which the button is
  not held, or the mana is ≤ 0 after that frame's drain, or the player is no longer in
  state 5 (stagger, death, any state change), **provided** the 0x8000 track is gone or at
  full weight. In a net game a channel released between weight 0.5 and 1.0 therefore keeps
  running until the weight reaches 1.0.
- `Player_updateCast` is not called at all while the record's hit points are ≤ 0, so a
  player who dies while channelling stops running the spell (no more projectiles) but the
  spell is not destroyed by this path; what removes it then was not traced.
- There is no maximum duration other than mana. Mana is not clamped at 0 in the code read.
- The facing computed by `Player_castSkill` (aim assistance) is not used: the cast function
  ignores its position and facing arguments, and every run receives the player's current
  facing (+0x38). The cone turns with the player.

For a monster the spell is run at the top of `Creature_run` (0x112948: for every non-player
creature, slot 17 is called with (x, y, height + height extent × 0.5)) with the creature's
facing, from the frame after it is attached until it is removed.

**Cast** — `SkillConeOfFrost_cast(skill, level, caster)` 0x2e9930: L = slot 14(level, 1)
(unchanged); `SpellConeOfFrost_ctor(spell, L, caster, skill)` on a 0x58-byte block; returns
the spell (0 if the allocation failed).

**SpellConeOfFrost_ctor** 0x2e9b08: +0x00 = level (u8); **one shared draw** → +0x10
(private generator state); +0x04 = 0; +0x08 = skill; +0x0c = caster; virtual table; a light
node at +0x18 (radius 156.0, position = caster position + (0, 0, 60)), linked; a positional
sound started at the caster's position, handle stored at +0x54. The caster pointer is
dereferenced without a null test.

**SpellConeOfFrost_run(spell, Vec3 *pos, s16 facing)** 0x2e9d10, once per frame:

```
A     = trunc((float)getStat(2, level) * 182.04443f)       # int; 182.04443 = 65536/360
scale = (float)getStat(1, level) * 0.0099999998f + 1.0f
cosmetic particles: 15 + 6 (+ 24 on one frame in five on average), all on Spell_rand
if (g_simFrame & 7) == 0:                                  # every 8th global frame  (0x2ea1a8)
    r   = Spell_rand(spell)
    ang = (s16)(facing + trunc(((float)r * 1.5258789e-05f - 0.5f) * (float)A))
    vel = ((cos16(ang) * 74.0f) * 2 * scale, (sin16(ang) * 74.0f) * 2 * scale, 0)
          # written as x + x in the code; units per second
    dmg = (float)getStat(0, level) * 0.13333333f           (0x3e088888)
    DummyDamager_ctor(dmg, obj, pos, &vel, life 45, radius 10, bits 0x12,
                      damageFlags 0x80c040, owner = spell.owner(+0x0c), 1)   (0x2ea278–0x2ea2a8)
light flicker (presentation)
```

The spread is uniform over ±A/2 sixteen-bit angle units, i.e. a total cone of stat 2
degrees around the facing. One projectile every 8 frames is 7.5 per second, so stat 0 is the
damage per second when every projectile lands. The light node keeps the position it was
given at construction (the run only rewrites its radius).

**DummyDamager_ctor** 0x201e78 (f12 damage, a0 obj, a1 pos, a2 velocity, a3 life,
t0 radius, t1 bits, t2 damage flags, t3 owner, one s16 on the stack):
`Projectile_ctor(obj, pos, owner, 0)` — **one shared draw**; +0x54 velocity (units per
second); +0x6c life (s16) = 45; +0x1c radius = 10.0; object flags = 0x4081 | 0x4008 = 0x4089
(the 0x8 "dead" bit keeps it out of enemy tests and arc queries); +0x68 damage (float);
+0x64 damage flags; +0x6e = the stack argument (1); +0x60 bits; `obj_runEveryFrame`.

**DummyDamager_run** 0x1ee330, once per frame:

```
life -= 1
if (s16)life <= 0: destroy self; return           # 44 moving frames, destroyed on the 45th run
r = obj_moveAndCollide(obj, &velocity)             # shared section; may call onTouch
if r == 0: return
if r == 1:                                         # terrain, no object touched
    if bits & 8: (fire: not used by this skill)
    if bits & 0x10: 128 burst particles (own generator: 2 unit-ball samples each)
    if bits & 2: destroy self; return
if bits & 1: destroy self
```

With bits 0x12 the projectile is destroyed by terrain only; it is **not** destroyed by
touching objects and passes through them. Its travel is 44 steps of 148 × scale / 60:
109.6 units at rank 1, 148.7 at rank 10, 192.1 at rank 20 (speeds 149.48, 202.76 and
261.96 units per second).

**DummyDamager_onTouch(obj, other)** 0x1ee7b0, called for every solid object the
projectile overlaps, every frame it overlaps it (2-D distance < 10 + other.radius, heights
overlapping within the projectile's extent of 72):

1. If `other` is a creature (flag 0x20): return unless `other.slot20(owner) != 0` — the
   test is made by the **victim** about the projectile's owner. The owner object is read
   through the handle **without a null test** (0x1ee7d8–0x1ee7e8).
   If `other` is not a creature the function continues.
2. Fresh descriptor. Because bit 0x10 is set: entry 0 = {type 0x16, v1 = v2 =
   trunc(damage(+0x68)), v3 = 0}; then damage(+0x68) = 0.0.
3. attacker = owner object, or 0 when the handle is empty.
4. `damage_apply(damage(+0x68), damage(+0x68), other, attacker, 1000000, 0, 0, 0x80c040,
   desc, 0)` — the base minimum and maximum are read after step 2 and are therefore 0.0.

Consequences (Observed from the code above):

- A projectile delivers its cold amount on its **first** call that reaches step 2 and
  nothing afterwards: later calls build an entry {0x16, 0, 0, 0}. If that first object is a
  non-creature solid object, the amount is lost, because `damage_apply` does not process
  descriptors for non-creatures.
- `damage_apply` is nevertheless called on every overlap frame (about 27 frames for a
  creature of radius 24 at rank 1), each call making its usual shared draws.
- Damage flags 0x80c040: 0x40 cannot be blocked and ignores Spirit Shield; 0x4000 and 0x8000
  no hit or miss sound; **0x800000 damage over time** — `damage_apply` adds the amount to
  the victim's accumulator (+0xcc) and delivers the sum through take-damage only on frames
  with `g_simFrame & 31 == 0` (`docs/gameplay.md` section 2.4, 2.5 step 27). The cold entry
  also feeds the victim's chill timer.
- Other players are not hit outside PvP mode A (`Player_isEnemy` of the victim), monsters
  hit by a player's cone must regard the player as an enemy (`Creature_isEnemy`: alive, not
  friendly, different team), and a dead owner stops all damage to creatures.

**Fields.** `SpellConeOfFrost` (after the 0x18-byte `Spell` base: +0x00 u8 level, +0x04
back-list, +0x08 Skill, +0x0c owner, +0x10 generator, +0x14 virtual table):

| Offset | Type | Meaning |
|---|---|---|
| +0x18 | light node, 0x30 bytes | colours +0x22..+0x31, radius +0x34/+0x3c (156.0, then 108 + trunc(6·sin16(g_simFrame·1000))), inverse square +0x38/+0x40, position +0x48 |
| +0x54 | s32 | handle of the looping sound; stopped by the destructor |

`DummyDamager` (after the `Projectile` part):

| Offset | Type | Meaning |
|---|---|---|
| +0x54 | float[3] | velocity, units per second |
| +0x60 | u32 | behaviour bits: 1 destroy on any contact, 2 destroy on terrain, 4 (constructor only: object flag 0x1, already set), 8 fire, 0x10 cold |
| +0x64 | u32 | flags passed to `damage_apply` |
| +0x68 | float | damage; zeroed by the first touch that builds a fire or cold entry |
| +0x6c | s16 | life in frames |
| +0x6e | s16 | tenth constructor argument (1 here); not read by the functions read |

#### Random draws

1. Cast: 1 shared draw (the `Spell` constructor seeds +0x10).
2. Every run of the spell, **spell generator**, in order: 15 × 4 draws (first particle
   kind: angle, speed, vertical speed, start offset along the path); 6 × 3 draws (second
   kind: angle, speed, vertical speed); 1 draw — if `r % 5 == 0`, 24 × 3 more draws (third
   kind; the middle one of each three is discarded);
   then, on frames with `(g_simFrame & 7) == 0`, **1 draw for the projectile's direction**.
   The direction draw is a gameplay value taken from the same stream as the particle draws;
   the count before it is fixed per frame (79 or 151), so the stream is reproducible.
3. Each projectile: 1 shared draw at construction. Its own generator is used only for the
   water splash draw of `obj_moveAndCollide` and the 128 burst particles on terrain.
4. Every touch frame: the draws of `damage_apply` (no base roll; first hit roll; the
   always-drawn proc rolls; one draw for the 0x16 amount when it is non-zero; second hit
   roll; for a non-creature object the unconditional first draw only).

#### Presentation only

A looping positional sound for the life of the spell; a flickering light; three particle
kinds per frame fanned over the cone (types 0x8e6090, 0x8e60e0, 0x8e6130); the projectile's
128-particle burst on terrain (type 0x4f8760). The projectiles themselves are invisible
(empty draw function). The cast animation, the casting voice cue and the per-slot aura
values written by `Player_run` state 5 and `Player_updateCast` (0x4d8a90[slot],
0x4d8ab0[slot]) belong to the player code.

#### Per-machine state

- The cast threshold on the animation weight depends on `g_networkMode` (1.0 offline, 0.5 in
  a net game; 0x1ab704). It is the same for every machine of a session, but offline and
  online timings differ by about 3 animation ticks.
- `DummyDamager_onTouch` reads the owner object through the handle at +0x4c without testing
  the handle (0x1ee7d8). If the caster object has been destroyed while a projectile is still
  alive (45 frames) and the projectile touches a creature, the read goes through a null
  pointer. Whether that situation can occur for a player (respawn replaces the player
  object) or for a Tormentor was not traced (**Inferred** hazard).
- No camera, local-slot or option reads were found in the spell or the projectile.
- The prediction copy: `Player_castSkill` returns before the cast for the copy, but the
  state 5 code still drains the copy's mana each frame; mana is restored by the prediction
  loop (`docs/skills.md`).

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2e9848 | SkillConeOfFrost_ctor | Skill constructor (kind 1) |
| 0x2e98bc | SkillConeOfFrost_initStats | statistic tables |
| 0x2e9930 | SkillConeOfFrost_cast | allocates and constructs the spell |
| 0x2e99d0 | SkillConeOfFrost_describeRank | text arguments |
| 0x2e9ad4 | SkillConeOfFrost_manaCost | slot 15 with (rank, 1) |
| 0x2e9b08 | SpellConeOfFrost_ctor | above |
| 0x2e9c90 | SpellConeOfFrost_dtor | stops the sound, removes the light, clears the back-list |
| 0x2e9d10 | SpellConeOfFrost_run | above |
| 0x201e78 | DummyDamager_ctor | above |
| 0x1ee330 | DummyDamager_run | above |
| 0x1ee7b0 | DummyDamager_onTouch | above |
| 0x1a3f70 | Player_updateCast | runs attached spells, ends the channel |
| 0x1a42b8 | Player_castSkill | the cast call, attach, link at +0x588, recast, first mana charge |
| 0x1a5030 | Player_run | only the state 2 start conditions and the state 5 `Skill` path |
| 0x1d32e4 | (function that creates a `Skill` ability record) | zeroes the record, copies the kind byte |
| 0x11a868 | Creature_updateSpells | slot 17 |
| 0x112948 | Creature_run | only its first statement (slot 17 for non-players) |
| 0x287db0 | Tormentor run | only AI state 8 |

#### Not determined

- The exact frame on which the cast animation's weight crosses the threshold
  (`anim_start` and `anim_advance` were not read; see `docs/engine.md`).
- What removes the 0x8000 animation track when the player is staggered, and hence exactly
  how long the spell survives such an interruption; what destroys the attached spell after
  the player's death (`Player_updateCast` is skipped at 0 hit points).
- Whether mana can go below zero for one frame and what clamps it.
- The Tormentor's animation event frames (the distance in frames between its two events)
  and its other AI states.
- The older, inline ability path of state 5 (abilities that are not `Skill` objects) was
  not read.
- The take-damage side of flag 0x800000 (the 32-frame delivery) was taken from
  `docs/gameplay.md`.

### 57 shockoffire — SkillShockOfFire

#### Identity

- Id 57, internal name `shockoffire`. Skill class `SkillShockOfFire`, virtual table
  0x51a190, static object 0x6e2b98 (`g_skillTable[57]` at 0x41b254), constructor 0x2ed38c.
  Kind 0 (ordinary, active), flags 0, recast 30 frames.
- Creates one `Sparks` object per cast: size 0xb8, virtual table 0x50e998, base classes
  `GameObject` > `Projectile`. Slots: 1 destructor 0x3c5b90, 4 run 0x28fa3c, 5 draw
  0x2902e4, 6 touched 0x2900c8, 15 clone 0x12c668. The class lives in the monsters area and
  has five other creators (constructor call sites: MissileTrap 0x1f3b64, Shooter 0x1f4f90,
  Cazic 0x24c7d0, Demon 0x25ea40, Mummy 0x29a2c8).
- A direct hit also creates a `LightEffect` (0xbc bytes). The cast function returns 0.
- Players: wizard tree, base level 15, prerequisite skill 58.
- Monsters: Goblin calls slot 2 (`Goblin_run` 0x26b27c) with level = own slot 35, position
  (x, y, height + height extent × 0.5). Cazic (`Cazic_castShockOfFire` 0x24c5a4) builds the
  `Sparks` object itself with the same four reads as the cast function (slot 8 for stat 0,
  slot 12 for stats 1–3); Demon and Mummy build it from slot 12 values (not read).

#### Statistics

`SkillShockOfFire_initStats` 0x2ed3f8.

| Stat | Meaning | Tier 1: first, base, step | Tier 2: first, base, step |
|---|---|---|---|
| 0 | direct fire damage, centre value (Observed 0x2ed550–0x2ed588 → Sparks +0xac/+0xa8) | 1, 162, 11.001733 (0x41300719) | 1, 3, 2.5 (0x40200000) |
| 1 | splash damage, fixed amount (Observed 0x2ed58c–0x2ed5b8 → Sparks +0xb0) | 5, 45, 2.0019598 (0x4000201c) | 5, 5, 1.0 (0x3f800000) |
| 2 | splash radius in units of 12 (Observed 0x2ed5bc–0x2ed610 → Sparks +0xb4) | 5, 2, 1.2999779 (0x3fa665ad) | 10, 2, 0.099999994 (0x3dcccccc) |
| 3 | speed in units per second (Observed 0x2ed614–0x2ed634) | 1, 243, 5.8849726 (0x40bc51b2) | 1, 243, 1.0 (0x3f800000) |
| 4 | mana (0x2ed80c) | 1, 31, 2.0008218 (0x40000d77) | none |

The cast maps the level through slot 14 with argument 20 (unchanged) and then:

- stat 0 through **slot 8**: `getStatRange(0.19999999, 0, L, randomise 0, &lo, &hi)`, which
  uses slot 10 — **tier 1 for every caster**, players and monsters alike (Observed
  0x3c82e4). The tier-2 row of stat 0 is reached only by callers that ask slot 12 themselves.
- stat 1: slot12(1, L, caster, cap 0); stat 2: slot12(2, L, caster, cap 10) × 12;
  stat 3: slot12(3, L, caster, cap 10).

| Rank (player) | 1 | 5 | 10 | 20 |
|---|---|---|---|---|
| stat 0 → lo..hi | 162 → 130..194 | 206 → 165..247 | 261 → 209..313 | 371 → 297..445 |
| stat 1 | 0 (no splash) | 45 | 55 | 75 |
| stat 2 → radius | 0 | 2 → 24 | 8 → 96 | 21 → 252 |
| stat 3 → units per frame | 243 → 4.05 | 267 → 4.45 | 296 → 4.93 | 355 → 5.92 |
| stat 4 | 31 | 39 | 49 | 69 |

Tier 1 by rank 1..20 — stat 0 = 162 + 11·(rank − 1); stat 1 = 45 + 2·(rank − 5) from rank 5;
stat 2: 0 0 0 0 2 3 5 6 7 8 10 11 12 14 15 16 18 19 20 21; stat 3: 243 249 255 261 267 272
278 284 290 296 302 308 314 320 325 331 337 343 349 355; stat 4 = 31 + 2·(rank − 1).

Non-player caster through the cast function at level L: direct damage = the tier-1 range at
L; stat 1 = L for L ≥ 5, else 0; stat 2 = 2 for L ≥ 10, else 0 (radius 24 or 0); stat 3 =
243 + min(L, 10) − 1.

The rank description (0x2ed6a4) prints the stat 0 range, the `getStatRange(0.2, stat 1)`
range and stat 2; the splash amount actually applied has no spread.

#### Cost and limits

- Mana: slot 5 = slot 15(rank, 20) = (float) getStat(4, rank): 31, 49, 69 at ranks 1, 10, 20.
- Recast 30 frames. canUse: base function, always 1.

#### Behaviour

**Cast** — `SkillShockOfFire_cast(skill, level, caster, Vec3 *pos, s16 facing)` 0x2ed4e4:

1. L = slot 14(level, 20); lo, hi from slot 8; s1, r2 = stat 2 × 12, s3 as above.
2. velocity = (cos16(facing) · (float)s3, sin16(facing) · (float)s3, 0), units per second,
   not normalised.
3. `Sparks_ctor(obj, pos, &velocity, caster, 0, 0, lo, hi, s1, r2)` on a 0xb8-byte block
   (register arguments a0–a3, t0 = 0, t1 = 0, t2 = lo, t3 = hi; s1 and r2 on the stack;
   0x2ed648–0x2ed674). Returns 0.

**Sparks_ctor** 0x28f880:

1. `Projectile_ctor(obj, pos, caster, 0)` — one shared draw; radius 12.0, height extent
   72.0, flags 0x4081, owner handle.
2. Light node at +0x64 (radius 120.0, position +0x94), linked.
3. +0x58 velocity (units per second); +0xb0 = s1; +0xb4 = r2; +0x54 end frame =
   g_simFrame + 600; +0xa8 = hi; +0xac = lo; `obj_runEveryFrame`; a sound on the object;
   +0xa0 = the t1 argument (0 here).

**Sparks_run** 0x28fa3c, once per frame:

```
if g_simFrame < end(+0x54):
    r = obj_moveAndCollide(obj, &velocity)      # shared section; may call Sparks_onTouch
    if r == 1: end = 0                          # terrain and no object touched   (0x28fab4–0x28fac4)
    particles (own generator), light follows
else:                                           # timed out, or end was zeroed last frame
    50 particles (own generator)
    if splash(+0xb0) > 0:
        attacker = owner handle non-empty ? owner object : obj
        fx_ringBurst(2.0, pos)                  # presentation, cosmetic generator
        world_damageInRadius(40.0, (float)radius(+0xb4), attacker, &pos,
                             splash, 0x40860, splash, 0)                (0x28ffe4–0x290070)
    destroy self (slot 1 with argument 3)
```

**Sparks_onTouch(obj, other)** 0x2900c8 (reached only from the object's own
`obj_moveAndCollide`): acts only when end(+0x54) != 0, the owner handle is non-empty and
`owner.slot20(other) != 0`. Then:

1. Allocate and construct a `LightEffect` at the spark's position — one shared draw when the
   allocation succeeds (0x290128–0x2901b4). Presentation otherwise.
2. A sound on the spark.
3. Fresh descriptor, entry 0 = {type 0x1f, v1 = 100, v2 = (s16)lo, v3 = (s16)hi}.
4. `damage_apply(0.0, 0.0, other, owner, 10000000, lo, hi, 0xc060, desc, 0)`
   (0x2902a4–0x2902c0). Flags: 0x40 cannot be blocked and ignores Spirit Shield, 0x4000 and
   0x8000 no hit and no miss sound, 0x20 not read by the callee. The type 0x1f entry is a
   "chance of fire" proc at 100 %: fire damage rolled between lo and hi, reduced by fire
   resistance, plus the burn status (`docs/gameplay.md` section 2.2); it needs the first hit
   roll, which with an attack rating of ten million succeeds against any armour value below
   that.
5. end = 0.

Consequences:

- The spark flies straight at stat 3 units per second (4.05 units per frame at rank 1) for
  at most 600 frames. Its height changes only if the terrain back-off of
  `obj_moveAndCollide` moves it.
- Only the **first** enemy touched takes the direct hit: after it end is 0, and the remaining
  objects of the same collision loop find the handler disabled. Non-enemies (and everything,
  when the owner is gone) are passed through without effect.
- A terrain hit ends the spark only when no object was touched in the same step (result
  exactly 1). With result 3 the spark, already moved back out of the terrain, keeps flying
  and meets the terrain again on a later frame.
- The explosion is one frame later than the hit, terrain contact or timeout: the first run
  with g_simFrame ≥ end takes the else branch. It happens for all three endings.
- Splash (only when stat 1 > 0, i.e. player rank ≥ 5): `world_damageInRadius` takes the box
  pos ± radius (127 objects), skips the attacker, keeps only objects the attacker's slot 20
  accepts **when the attacker is a player**, and for each object with
  d = |dx| + |dy| − 0.333·min(|dx|, |dy|) − o.radius < radius calls
  `damage_apply(s1, s1, o, attacker, 100000, 0, 0, 0x40860, 0, 0)`: because minimum and
  maximum are both stat 1 the falloff term has no effect and every object in range takes
  exactly stat 1. The direct-hit victim is normally in range and takes both.
- For a non-player attacker (Goblin's cast, or the spark itself when its owner is gone) the
  splash has no enemy filter: it strikes every object in range except the attacker,
  including the attacker's allies and non-creature objects.

**Sparks fields** (after the `Projectile` part):

| Offset | Type | Meaning |
|---|---|---|
| +0x54 | s32 | end frame (creation + 600); 0 = explode on the next run |
| +0x58 | float[3] | velocity, units per second |
| +0x64 | light node, 0x30 bytes | radius +0x80/+0x88 = 120.0, position +0x94 |
| +0xa0 | s32 | sixth constructor argument (0 from this skill); not read by run, touched or draw |
| +0xa4 | s32 | voice handle passed to `voice_setPosition` every flying frame; never stored by the constructor, run or touched function (the only access in 0x28f880–0x2903a0 is the load at 0x28facc), so it is the 0 left by `pool_new`; presentation |
| +0xa8 | s32 | direct damage, high end |
| +0xac | s32 | direct damage, low end |
| +0xb0 | s32 | splash damage (stat 1) |
| +0xb4 | s32 | splash radius (stat 2 × 12) |

#### Random draws

1. Cast: 1 shared draw (`Projectile_ctor` → `GameObject_ctor`).
2. Each flying frame, own generator, in order: possibly 1 draw inside `obj_moveAndCollide`
   (water splash, once per object); 3 unit-ball samples (three particles); 5 times { one
   unit-ball sample whose result is overwritten, then one that is used }; 1 draw whose bit 0
   decides a trailing particle, and if set 1 more unit-ball sample.
3. Direct hit (inside the collision step, before item 2 of that frame): 1 shared draw for
   the `LightEffect`, then the draws of `damage_apply` (first hit roll, the 0x1f proc roll
   and its amount roll, the other always-drawn proc rolls, second hit roll).
4. Explosion frame: 50 unit-ball samples of the own generator; then, when stat 1 > 0, the
   draws of `damage_apply` for each object struck, in box order (no base roll since min =
   max; for a non-creature object the unconditional first draw).

The own generator decides nothing but particle directions.

#### Presentation only

Cast sound and hit sound on the spark; the spark's light; the hit light (`LightEffect`
with colour arguments 255, 200, 100); particles (types 0x8e4010, 0x8e4060, 0x8e4150 in
flight, 0x8e4100 at the end); `fx_ringBurst`; the draw function 0x2902e4 queues one glow
sprite pulsing with `sin16(g_simFrame << 10)`.

#### Per-machine state

None found in the gameplay path. `fx_ringBurst` uses the cosmetic generator and is not
followed by any decision. As for the frost storm, the `LightEffect` allocation at a direct
hit carries a shared draw that is skipped if the pool is exhausted.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2ed38c | SkillShockOfFire_ctor | Skill constructor (not read beyond the table data) |
| 0x2ed3f8 | SkillShockOfFire_initStats | statistic tables |
| 0x2ed4e4 | SkillShockOfFire_cast | above |
| 0x2ed6a4 | SkillShockOfFire_describeRank | text arguments |
| 0x2ed80c | SkillShockOfFire_manaCost | slot 15 with (rank, 20) |
| 0x28f880 | Sparks_ctor | above |
| 0x28fa3c | Sparks_run | above |
| 0x2900c8 | Sparks_onTouch | above |
| 0x2902e4 | Sparks_draw | glow sprite |
| 0x3c5b90 | Sparks_dtor | light, owner handle, base destructor |
| 0x161270 | world_damageInRadius | splash |
| 0x150e48, 0x1509f8 | Projectile_ctor, obj_moveAndCollide | shared section |

#### Not determined

- What the take-damage implementations do with flag bits 0x20, 0x800 and 0x40000 of the
  splash flags 0x40860 and 0x20 of the direct-hit flags (they are not tested inside
  `damage_apply`).
- The exact success test of a type 0x1f entry at chance 100 (taken from
  `docs/gameplay.md`; Inferred always true).
- Demon's and Mummy's `Sparks` construction and Goblin's choice logic were not read.
- What `voice_setPosition` does with voice 0 every frame, and the meaning of +0xa0 for the
  other creators.

### 58 froststorm — SkillFrostStorm

#### Identity

- Id 58, internal name `froststorm`. Skill class `SkillFrostStorm`, virtual table 0x51a218,
  static object 0x6e2c00 (`g_skillTable[58]` at 0x41b258), constructor 0x2ed840. Kind 0
  (ordinary, active), flags 0, recast 30 frames.
- Creates one `FrostStormSpell` per cast: size 0xac, virtual table 0x50d3e0, base class
  `GameObject` (despite the name it is not a `Spell`; nothing is attached to the caster and
  the cast function returns 0). Slots: 1 destructor 0x3c79f0, 4 run 0x1fe950, 5 draw
  0x2031e8 (empty), 6 the empty base.
- The storm creates `FrostStormIceShard` objects: size 0x64, virtual table 0x512a40, base
  `GameObject`; slots 1 destructor 0x3c8e90, 4 run 0x1fdef8, 5 draw 0x1fddd0, 6 the empty
  base. The shards are decoration (no damage, no touch handler) but each one is a
  `GameObject` and so costs a shared draw.
- A monster cast also creates one `LightEffect` (0xbc bytes, virtual table 0x50e198) as a
  warning light.
- Players: wizard tree, base level 8, prerequisite skill 23.
- Monsters: Cazic (0x24aaf0) and Mummy (0x298d18) call slot 2 with level = own slot 35,
  their own facing and a position computed just before. **Goblin also casts it**
  (`Goblin_run` 0x26b27c: one branch calls slot 2 on a pointer that is `g_skillTable[58]`,
  or `g_skillTable[7]` when the byte at goblin+0x490 is 1) — the first-round tables list
  Goblin as "statistics only" for this id. Ulthork (0x2b5a08, call at 0x2b625c) builds a
  `FrostStormSpell` itself from four slot 12 reads with level = (int) `g_levelMonsterLevel`
  (not × 0.3) and caps 0, 10, 10, 10, without the 180 clamp. Minion (0x2862c0) uses the four
  statistics to build a `RainOfFireSpell`.

#### Statistics

`SkillFrostStorm_initStats` 0x2ed8ac.

| Stat | Meaning | Tier 1: first, base, step | Tier 2: first, base, step |
|---|---|---|---|
| 0 | damage per tick, total (Observed 0x2edab0–0x2edadc → storm +0x5c) | 1, 28, 2.0009878 (0x4000102f) | 1, 20, 4.0 (0x40800000) |
| 1 | radius in units of 12 (Observed 0x2edae0–0x2edb34: × 12 → storm +0x54) | 1, 2, 0.20098399 (0x3e4dcebf) | 1, 4, 0.79999995 (0x3f4ccccc) |
| 2 | duration in seconds (Observed 0x2edb38–0x2edb68: × 60 frames) | 1, 2, 0.25100198 (0x3e808355) | 1, 3, 0.35 (0x3eb33333) |
| 3 | drift speed, units per second along the cast facing (Observed 0x2edb6c–0x2edba0) | 1, 31, 1.2509819 (0x3fa0202d) | 1, 31, 1.0 (0x3f800000) |
| 4 | mana (0x2edd44) | 1, 40, 8.000706 (0x410002e4) | none |

The cast first maps the level through slot 14 with argument 20 (base function: level
unchanged), then reads through **slot 12** (`getStatFor(stat, level, caster, cap)`): a
player caster gets tier 1 with no cap; any other caster gets tier 2 with the level limited to
the cap. Caps: stat 0 → 0 (none), stat 1 → 10, stat 2 → 20, stat 3 → 10.

| Rank (player, tier 1) | 1 | 10 | 20 |
|---|---|---|---|
| stat 0 | 28 | 46 | 66 |
| stat 1 → radius | 2 → 24 | 4 → 48 | 6 → 72 |
| stat 2 → frames | 2 → 120 | 4 → 240 | 7 → 420 |
| stat 3 → drift per frame | 31 → 0.51666665 | 42 → 0.69999993 | 55 → 0.91666663 |
| stat 4 | 40 | 112 | 192 |

Tier 1 by rank 1..20 — stat 1: 2 2 2 3 3 3 3 3 4 4 4 4 4 5 5 5 5 5 6 6; stat 2: 2 2 3 3 3 3 4
4 4 4 5 5 5 5 6 6 6 6 7 7; stat 3: 31 32 34 35 36 37 39 40 41 42 44 45 46 47 49 50 51 52 54
55; stat 0 = 28 + 2·(rank − 1); stat 4 = 40 + 8·(rank − 1).

| Level (other caster, tier 2) | 1 | 10 | 20 |
|---|---|---|---|
| stat 0 (no cap) | 20 | 56 | 96 |
| stat 1 (cap 10) → radius | 4 → 48 | 11 → 132 | 11 → 132 |
| stat 2 (cap 20) → frames | 3 → 180 | 6 → 360 | 10 → 600 |
| stat 3 (cap 10) | 31 | 40 | 40 |

Tier 2 stat 1 for levels 1..10: 4 5 6 6 7 8 9 10 10 11. With the cap the radius of a
non-player cast never exceeds 132, so the clamp to 180 in the cast function cannot bind
(Observed arithmetic; the clamp is at 0x2edba4–0x2edbac).

The rank description (0x2edc40) prints `getStatRange(0.2, stat 0)` as a range, although the
tick damage has no spread at all.

#### Cost and limits

- Mana: slot 5 = slot 15(rank, 20) = (float) getStat(4, rank): 40, 112, 192 at ranks 1, 10,
  20.
- Recast 30 frames. canUse: base function, always 1.
- There is no limit on the number of storms alive at once.

#### Behaviour

**Cast** — `SkillFrostStorm_cast(skill, level, caster, Vec3 *pos, s16 facing)` 0x2ed9a0
(the caster pointer is dereferenced without a null test):

1. L = slot 14(level, 20) = level.
2. centre = *pos. If the caster has flag 0x40 (player): centre.x += (cos16(facing) · 3.0) ·
   12.0, centre.y += (sin16(facing) · 3.0) · 12.0, centre.z += 0 — 36 units ahead
   (0x2eda40–0x2edaac). For a player `pos` is the hand midpoint from `Player_castSkill`, so
   the storm's centre is at hand height.
3. dmg = slot12(0, L, caster, 0); radius = slot12(1, L, caster, 10) · 12 (int);
   frames = slot12(2, L, caster, 20) · 60; s3 = slot12(3, L, caster, 10).
4. drift = (cos16(facing) · (float)s3, sin16(facing) · (float)s3, 0) units per second.
5. If the caster is not a player and radius > 180: radius = 180.
6. `FrostStormSpell_ctor((float)radius, obj, &centre, frames, dmg, caster, &drift)` on a
   0xac-byte block.
7. A sound on the caster. Returns 0.

**FrostStormSpell_ctor** 0x1fe508 (f12 radius, a0 obj, a1 pos, a2 frames, a3 damage,
t0 caster, t1 drift):

1. `GameObject_ctor(obj, pos, 0, 0)` — shared draw.
2. Light node at +0x70: radius = clamp(radius · 1.715958, 79.0, 300.0) (presentation).
3. +0x54 = radius; flags |= 0x1.
4. If `(caster.flags & 0x60) == 0x20` (a creature that is not a player; 0x1fe6a0):
   - +0x50 start = trunc((float)g_simFrame + 40.499996) = g_simFrame + 40;
     +0x4c end = start + frames;
   - a `LightEffect` is allocated and built in line at pos + (0, 0, 12): second
     `GameObject_ctor` — **second shared draw** (0x1fe754); light radius min(2·radius, 300),
     end frame g_simFrame + 80, flags |= 3, put on the run list. Presentation.
   Otherwise: +0x50 start = 0; +0x4c end = g_simFrame + frames.
5. +0x1c (object radius) = 0; +0x58 multiplier = 1.0; +0x5c = damage (s32);
   +0x60 = drift · 0.016666666 per component; `handle_link(&obj+0x6c, caster, caster)`;
   `obj_runEveryFrame(obj)`.

**FrostStormSpell_run** 0x1fe950, once per frame:

```
if not (start(+0x50) < g_simFrame): return           # monster casts wait 40 frames
pos += drift                                          # x, y, height; no grid relink
radius(+0x54) *= multiplier(+0x58)
light follows; light radius = min(lightRadius * multiplier, 300)
if multiplier == 1.0:                                 # exact float compare     (0x1fea78)
    nAB = (radius * 0.008333333f) * (radius * 0.19999999f)
    for i = 0; (float)i < nAB; i++: snow particle A   (own draws, see Random draws)
    for i = 0; (float)i < nAB; i++: snow particle B
    if g_simFrame % 10 == 0:                                                   (0x1ff088)
        nC = ((radius * 0.050999999f) * 0.0069444436f) * radius
        for i = 0; (float)i < nC; i++: spawn one ice shard   (one shared draw each)
    nD = (radius * 0.39999899f) * (radius * 0.008333333f)
    for i = 0; (float)i < nD; i++: ground particle
if g_simFrame % 30 == 0: damageTick()                                          (0x1ff5c8)
if end(+0x4c) < g_simFrame:                                                    (0x1ff7c0)
    multiplier = 0.94999999f                          (0x3f733333)
    if radius < 12.0: destroy self (slot 1 with argument 3)
```

Each loop runs ceil(n) times (0 when n is 0). With float32 arithmetic:

| radius | 24 | 36 | 48 | 60 | 72 | 132 |
|---|---|---|---|---|---|---|
| snow A and B, each per frame | 1 | 3 | 4 | 6 | 9 | 30 |
| ice shards per 10th frame | 1 | 1 | 1 | 2 | 2 | 7 |
| ground particles per frame | 2 | 5 | 8 | 12 | 18 | 59 |
| frames of shrinking before the radius is below 12 | 14 | 22 | 28 | 32 | 35 | 47 |

(radius 60 gives nAB = 5.999999, hence 6: the order of the multiplications matters.)

**damageTick** (0x1ff5e0–0x1ff7bc), on every frame of the active or shrinking storm whose
global frame number is a multiple of 30:

1. `world_collectObjectsInBox(pos − radius, pos + radius, list, 0x40)` on all three axes, at
   most 63 objects, with the current (possibly shrunken) radius. There is no further
   distance test: the area is an axis-aligned box, enlarged in x and y by each object's
   own radius, and an object qualifies in height when [o.z, o.z + o.hext] meets
   [pos.z − radius, pos.z + radius].
2. For each object o in query order:
   - caster handle non-empty: skip o unless `caster.slot20(o) != 0`; attacker = caster;
   - caster handle empty: **every** object the query returns is struck (creatures of any
     side, props, the storm's own shards, and the storm itself for as long as the grid cell
     it was created in — it is never relinked — lies inside the query's cell range), with
     attacker = 0.
   - half = (float)damage(+0x5c) · 0.5. Fresh descriptor, entry 0 = {type 0x16,
     v1 = v2 = trunc(half), v3 = 0}.
   - `damage_apply(half, half, o, attacker, 100000, 0, 0, 0, desc, 0)`.
   So each tick is half the statistic as an untyped fixed base amount (flags 0: it can be
   blocked, Spirit Shield applies, a player victim's armour mitigation applies to it,
   critical hits are possible) plus the truncated half as cold damage (reduced by cold
   resistance, adds to the chill timer). For an odd statistic the base half keeps its .5
   and the cold half loses it.

Timeline of a player cast made on frame C with duration f = 60 × stat 2 (start = 0, end =
C + f):

- runs from the first frame after creation; drift and particles every frame, shards on
  multiples of 10, ticks on multiples of 30 — about f/30 ticks, phase set by the global
  frame counter, not by the cast frame;
- frame C + f + 1 is the first with end < frame: it is still a full frame (particles,
  possibly shards and a tick), and at its end the multiplier becomes 0.95;
- from frame C + f + 2 the radius shrinks by ×0.95 per frame, particles and shards stop,
  ticks continue with the shrinking box; the object is destroyed at the end of the frame on
  which the radius first falls below 12 (table above: frame C + f + 1 + 14 for radius 24).

A monster cast differs only in the 40 idle frames at the start (first active frame
C + 41, end = C + 40 + f) and the warning light.

**Ice shard** (built in line at 0x1ff344–0x1ff404; an out-of-line constructor with a scale
argument, equivalent at scale 1.0, exists at 0x2030f0 with no caller found). For each shard, in this order:

1. u = unit-ball sample (own draws of the storm); h = one own draw;
   position = (pos.x + u.x · (radius · 1.000001), pos.y + u.y · (radius · 1.000001),
   pos.z + 120.0 + (h/65536) · 12.0).
2. w = unit-ball sample; velocity per frame = (w.x · 0.20500399, w.y · 0.20500399,
   −|w.z · 3.9999869|) (the absolute value and negation are done in double precision).
3. `pool_new(0x64)`; `GameObject_ctor(shard, &position, 0, 0)` — **shared draw**; flags |=
   0x421d (0x1 not solid, 0x4, 0x8, 0x10, 0x200 touch-only, 0x4000 transient); +0x4c landed
   = 0; +0x50 scale = 1.0; +0x54 velocity; +0x60 end frame = g_simFrame + 120; +0x1c radius
   = 12.0; `obj_updateGridCell`; `obj_runEveryFrame`.

Shard run 0x1fdef8: while not landed and g_simFrame < end: velocity.z −= 0.40399897, pos +=
velocity (no grid relink), 1 trail particle (ceil(1·1·0.008333333·4.072701) = 1 iteration,
two unit-ball samples of the shard's own generator), then
`if pos.z − terrain_height(12.0, g_world, pos) < 16.0: landed = 1`. On the next run after
landing, or at the end frame: 5 burst particles (ceil(4.072701); two unit-ball samples
each) and the shard destroys itself. Nothing else reads the shard.

**FrostStormSpell fields**:

| Offset | Type | Meaning |
|---|---|---|
| +0x1c | float | object radius, set to 0 |
| +0x4c | s32 | end frame |
| +0x50 | s32 | start frame (0 for player casts) |
| +0x54 | float | radius: half-size of the damage box and of the particle disc |
| +0x58 | float | per-frame radius multiplier: 1.0, then 0.95 after the end frame |
| +0x5c | s32 | damage per tick (the statistic) |
| +0x60 | float[3] | per-frame drift |
| +0x6c | handle | caster |
| +0x70 | light node, 0x30 bytes | radius +0x8c/+0x94, inverse square +0x90/+0x98, +0x9c = 0.7, position +0xa0 |

**FrostStormIceShard fields**: +0x4c s32 landed; +0x50 float scale (1.0); +0x54 float[3]
velocity per frame; +0x60 s32 end frame.

#### Random draws

1. Cast: 1 shared draw (storm constructor); a monster cast: 1 more (the `LightEffect`).
2. Every active frame with multiplier 1.0, **own** generator of the storm, in this order:
   - nAB times: unit-ball sample (offset), 1 draw (height), unit-ball sample (velocity);
   - nAB times again, the same pattern;
   - on multiples of 10 frames, per shard: unit-ball sample, 1 draw, unit-ball sample, then
     **1 shared draw** (the shard's constructor), in that order, shard after shard;
   - nD times: 2 draws (angle, distance fraction).
   The own generator feeds only particle and shard positions.
3. Each shard: own generator of the shard for its particles (seeded by its shared draw).
4. Multiples of 30 frames: no draw of the storm; then `damage_apply` for each struck object
   in box order (no base roll since min = max; hit rolls and procs; one draw for the 0x16
   amount; and, when the victim is not a creature — possible only with an empty caster
   handle — the unconditional first draw of `damage_apply`).

The shared generator therefore advances by ceil(nC) on every 10th frame for every storm
alive, on top of the hits.

#### Presentation only

Cast sound on the caster; the storm's light (follows the storm, shrinks with it); two kinds
of falling snow particles; ground particles placed at `terrain_heightAtPoint` + 5 and shown
only when that height is at least the storm's height − 148; the shards' model, trail and
burst; the monster warning light.

#### Per-machine state

None found in the gameplay path (no camera, pad, local slot or option). Two things to keep
in mind:

- The shards are pool objects and each allocation that succeeds draws the shared generator;
  an allocation that fails skips the draw (the constructor is not called). The object pool
  is therefore part of the synchronised state for this skill. No per-machine condition was
  found on the shard path itself.
- With an empty caster handle the tick strikes everything in the box including non-creature
  objects; that is deterministic, but it is the only path here where the storm damages
  players and monsters alike.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2ed840 | SkillFrostStorm_ctor | Skill constructor |
| 0x2ed8ac | SkillFrostStorm_initStats | statistic tables |
| 0x2ed9a0 | SkillFrostStorm_cast | above |
| 0x2edc40 | SkillFrostStorm_describeRank | text arguments: stat 0 range, stat 1, stat 2 |
| 0x2edd44 | SkillFrostStorm_manaCost | slot 15 with (rank, 20) |
| 0x1fe508 | FrostStormSpell_ctor | above; second caller Ulthork_run 0x2b625c |
| 0x1fe950 | FrostStormSpell_run | above |
| 0x1fdef8 | FrostStormIceShard_run | shard fall, landing test, burst |
| 0x2030f0 | FrostStormIceShard_ctor | out-of-line copy of the shard constructor; no caller found |
| 0x1fddd0, 0x2031e8 | FrostStormIceShard_draw, FrostStormSpell_draw | draw only / empty (not read beyond their size and callee list) |
| 0x3c87f0 | Skill slot 12 | caster-type statistic selector |

#### Not determined

- The positions Cazic and Mummy pass to the cast, and when Cazic, Mummy and Goblin choose
  this skill (only the call sites were read).
- `LightEffect_run` 0x1ee050 was not read; it is taken from `docs/gameplay.md` to be a
  fading light with no gameplay effect.
- Whether anything reacts to being "touched" by a shard: shards have flag 0x200, so
  `obj_moveWithCollision` calls slot 6 of a mover that overlaps one. The creature-side slot 6
  implementations were not read.
- The inner draws of `damage_apply` for a type 0x16 entry with v1 = v2 were taken from
  `docs/gameplay.md`.

### 59 lifetap — SkillLifeTap

#### Identity

| Item | Value | Evidence |
|---|---|---|
| Id, name | 59 (0x3b), `lifetap` | Observed: constructor 0x2f8ca0 |
| Class | `SkillLifeTap`, virtual table 0x51a9e0; own cast 0x2f8d54 (returns null, no draw), describeRank 0x2f8d7c, manaCost 0x2f8e40 (returns 0.0), initStats 0x2f8d14, icon getter 0x3cfef4; canUse is the base (returns 1) | Observed |
| Skill object | 0x6e2c68, table entry 0x41b25c | Observed: static initialiser 0x16b2c0 |
| Kind, flags, recast | 3 (passive), 0, 30 (unused) | Observed |
| Effect objects | no Spell. A kill can create an `OniBall` (0xb8 bytes, a Projectile-based GameObject, virtual table 0x50e878, constructor 0x294014) | Observed 0x111f94-0x111fcc, 0x1b3694-0x1b36cc |
| Who has it | shadowknight tree (row level 5, prerequisite skill 61); it is itself the prerequisite of skill 36 | Observed in the tree dump |
| Type | passive: kills made by the player may leave a floating orb; a player with the skill who holds block draws orbs in and is healed (or given mana) on contact |

#### Statistics

`SkillLifeTap_initStats` 0x2f8d14. Statistics 2 to 4 zero; tier 2 none.

| Stat | Meaning | Tier 1: first, base, step | Tier 2 |
|---|---|---|---|
| 0 | chance in percent that a kill leaves an orb (Observed: `SkillLifeTap_getStat0Fraction` 0x2f8e78 = value x 0.01) | 1, 10, 0.748993993 (0x3f3fbe12) | none |
| 1 | amount restored by one orb (Observed: `SkillLifeTap_getStat1` 0x2f8eec, used in `OniBall_onTouch`) | 1, 15, 4.99990177 (0x409fff32) | none |

Both getters call slot 14 (rank, 1) first (base: rank unchanged) and then slot 10.

| Rank | s0 | s1 |
|---|---|---|
| 1 | 10 | 15 |
| 10 | 17 | 60 |
| 20 | 24 | 110 |

Ladders: s0 = 10, 11, 11, 12, 13, 14, 14, 15, 16, 17, 17, 18, 19, 20, 20, 21, 22, 23, 23,
24; s1 = 15 + 5 x (rank - 1).

#### Cost and limits

None. The skill is never cast; all effects need rank > 0 at the moment of the check.

#### Behaviour

Every reader of the rank of id 59 (found by scanning all calls of `player_getSkillRank` and
of Player slot 39 for the id constant): 0x111f30, 0x1a62e0, 0x1b3604, 0x29424c, 0x294738,
0x2947a4 and the skill screen 0x1d55c8.

**Skill screen.** `skills_screen` 0x1d4660 uses the rank in one hard-coded alternative
prerequisite (0x1d55b0-0x1d55d8): for class 2 (shadowknight) the row whose id-or-mask field
is 0x40 and whose own prerequisite is a passive (the shadowknight passive with mask 0x40,
normally needing passive 0x10) is also unlocked by LifeTap rank >= 1. The call instruction
at 0x1d55c8 is shared with the "either weapon skill" test, which passes id 61 through the
same instruction. Observed. No gameplay effect beyond what can be bought.

**Site 1: a monster dies.** `Creature_processDamage` 0x110d30, death branch, 0x111ea8-
0x111fd0, after the creature has been put in state 0x14 and unless a script property or
creature flag 0x100000000 ended the branch early:

```
killer = object behind the handle creature+0x2e4 (null handle: skip)
slot = -1
if g_players[0].object == killer: slot = 0
else for i in 1 .. g_numPlayers-1: if g_players[i].object == killer: slot = i   # last match
if slot != -1:
    frac = SkillLifeTap_getStat0Fraction(SKILL[59], player_getSkillRank(slot, 59))
    r = GameObject_rand(creature)            # the dying creature's OWN generator, always drawn
    if (float)(r mod 65536) < frac * 65536.0:
        obj = pool_new(0xb8)
        if obj: OniBall_ctor(obj, &creature position, creature facing, creature, 0)
```

**Site 2: a player dies in PvP mode A.** `Player_processDamage` 0x1b2cc0, death branch,
0x1b3588-0x1b36d4, only when `g_pvpModeA` is non-zero, the dead player's killer handle
(+0x2e4) is set and the killer object has flag 0x40:

```
ks = killer+0x3c8
if record[ks].class (+0x50) == 0: mana (+0xc0) = min(max mana (+0xc4), mana + max mana * 0.33332998)   # not LifeTap, same block
frac = SkillLifeTap_getStat0Fraction(SKILL[59], player_getSkillRank(ks, 59))
d = next SHARED draw                           # always
if (float) d < frac * 3.0 * 65536.0:
    obj = pool_new(0xb8)
    if obj: OniBall_ctor(obj, &dead player position, dead player facing, dead player, 0)
```

**Site 3: blocking glow.** `Player_run` state 8 (blocking), 0x1a62dc-0x1a6560, every frame
the state handler runs: if `player_getSkillRank(slot, 59) > 0`, one particle (definition
0x864eb0, built on first use) is spawned at the midpoint of attachment points 0 and 1 with a
random direction of length up to 10. **The direction comes from the shared generator
`g_randSeed`**: three draws per attempt, repeated while the point lies outside the unit
sphere (x*x + y*y + z*z > 1.0, each coordinate = draw x 2 / 65536 - 1). So a blocking player
with any LifeTap rank consumes 3, 6, 9, ... shared draws per frame. Observed 0x1a6384-0x1a6468
(the address loaded is 0x404464).

**The orb, `OniBall`** (verified against the description in docs/monsters-2.md, which this
agrees with):

Constructor `OniBall_ctor(orb, pos*, facing (unused), dead, 0)` 0x294014:
`Projectile_ctor(orb, pos, 0, 0)` (**one shared draw**); own draws in this order: facing
(+0x38); kind: value mod 65536 < 0x7333 gives kind 0 (health) and sets dead+0x38c (status
counter 8) = 30, otherwise kind 1 (mana) and dead+0x394 (counter 10) = 30; then three for
the wander point. Other writes: orb radius 0, flags OR 0x4000, expiry +0x54 = `g_simFrame` +
600, dead+0xf0 = `g_simFrame`, +0x58 = trunc(dead max hp (+0x22c) x 0.05) (never read),
height += 36, wander point (+0x68, +0x6c, +0x70) = position + (own mod 100 - 50, own mod 100
- 50, own mod 2000 + 36); put on the every-frame list.

| Offset | Type | Meaning |
|---|---|---|
| +0x00..+0x53 | Projectile / GameObject | base (radius +0x1c = 0, facing +0x38 random) |
| +0x54 | s32 | expiry frame |
| +0x58 | s32 | 5 % of the dead creature's maximum hit points; not used |
| +0x5c, +0x60, +0x64 | float[3] | velocity |
| +0x68, +0x6c, +0x70 | float[3] | destination |
| +0x74 | u8 | kind: 0 health, 1 mana |
| +0x80, +0x81 | u8 | 0 |

`OniBall_run` 0x2941e4, per frame:

1. Target slot = the entry of `g_alivePlayers` with LifeTap rank > 0 whose object is nearest
   in 3-D (strictly nearer replaces; none: -1).
2. One own draw; if (value mod 65536) < 0x1428, three more own draws set a new wander point:
   position + (own mod 1000 - 500, own mod 1000 - 500, 500 - own mod 500).
3. Homing when a target exists, its record hit points (+0xac) are above 0 and the pad word
   at `g_pads[slot]`+8 has a bit of `g_btnBlock[slot]` (0x41b9d0) set: destination = target
   position with 36 added to the height.
4. Homing: turn limit 0x666 per frame, speed = trunc(clamp(2-D distance x 0.013888888, 0.6,
   1.0) x 200). Not homing: turn limit 0x147, speed 200.
5. Facing turns toward the destination by at most the limit; velocity x, y = cos, sin of the
   facing x speed; vertical velocity 0 when the truncated height difference is within -9 to
   +9, else +200 or -200. Not homing: the velocity is then replaced by 60 along the facing
   and 50 upward.
6. One particle (kind-dependent definition); `obj_moveAndCollide(orb, velocity)`; when
   +0x54 <= `g_simFrame` the orb destroys itself (slot 1 with 3).

`OniBall_onTouch(orb, other)` 0x2946f8 (slot 6): acts only when `other` is not the
prediction copy (flag 0x20000 clear), is a player (flag 0x40), has LifeTap rank > 0 and holds
block (same pad test):

```
other+0xf0 = g_simFrame
amount = (float) SkillLifeTap_getStat1(SKILL[59], rank)
kind 0: pending = record+0xb4;  record+0xb4 = pending + amount
        if max hp (+0xb0) < hp (+0xac) + pending + amount: record+0xb4 = max hp - hp
        other+0x38c = 30
kind 1: pending = record+0xc8;  record+0xc8 = pending + amount
        if max mana (+0xc4) < mana (+0xc0) + pending + amount: record+0xc8 = max mana - mana
        other+0x394 = 30
orb+0x54 = g_simFrame            # the orb ends at its next expiry test
```

Record +0xb4 and +0xc8 are the "still to be delivered" pools that potions also use; the orb
does not write the per-frame delivery amount (+0xb8), and delivery itself is in the player
regeneration code.

Consequences: any player with the skill can collect an orb, not only the killer; the killer
needs the skill for the orb to appear at all; whether the orb is health or mana is decided
by the orb's own generator, about 45 % health; several orbs add up to the pool limits.

**Non-player.** A kill by a monster or by a non-player object never rolls (the killer must
be a player-table object). The cast slot returns null for any caster.

#### Random draws

1. Site 1: one draw of the dying creature's own generator whenever the killer is a player
   (also with rank 0). On success: one shared draw (Projectile constructor) and five own
   draws of the orb.
2. Site 2: one shared draw whenever the branch is reached; on success the same constructor
   draws.
3. Site 3: 3 x k shared draws per frame of blocking with rank > 0 (k attempts, k >= 1).
4. Orb run: one own draw per frame, plus three on a wander change; `obj_moveAndCollide` may
   take one own draw for a water splash (docs/objects.md).

#### Presentation only

Orb particles, the block glow particle itself (its draws are not presentation), status
counters 8 and 10 set to 30 on the dead creature and on the collecting player (Inferred to
drive a colour flash; their consumers were not read), `describeRank` 0x2f8d7c.

#### Per-machine state

- **Site 3 draws the shared generator for a particle.** It is inside `Player_run`, which also
  runs for the prediction copy; that is safe only because the prediction loop restores the
  shared generator. The number of draws depends on nothing local (rank, state and generator
  only). Observed.
- Site 1 matches the killer against the object pointers in the player table. During
  prediction the local slot's entry is the copy (docs/player.md), so a kill credited to the
  real local player would not match on that machine while prediction is running; whether
  `Creature_processDamage` can run inside prediction was not checked. Unknown.
- Site 2 is in the part of `Player_processDamage` that docs/player.md already lists as not
  guarded for the prediction copy: if the copy dies in PvP mode A the shared draw and a real
  orb object would be made on the predicting machine only. Inferred from that finding plus
  the code read here.
- `OniBall_run` and `OniBall_onTouch` read the lockstep pad word and `g_btnBlock`; both are
  shared inputs. `OniBall_onTouch` tests the prediction-copy flag. The orb walks
  `g_alivePlayers` (caveat in docs/player.md).
- No camera, local-slot or cosmetic-seed read in a gameplay decision.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x2f8ca0 | SkillLifeTap_ctor | kind 3 |
| 0x2f8d14 | SkillLifeTap_initStats | two statistics |
| 0x2f8d54 | SkillLifeTap_cast | returns null |
| 0x2f8e40 | SkillLifeTap_manaCost | returns 0.0 |
| 0x2f8e78 | SkillLifeTap_getStat0Fraction | statistic 0 x 0.01 |
| 0x2f8eec | SkillLifeTap_getStat1 | statistic 1 |
| 0x111ea8-0x111fd0 | part of Creature_processDamage | site 1 |
| 0x1b3588-0x1b36d4 | part of Player_processDamage | site 2 |
| 0x1a62dc-0x1a6560 | part of Player_run state 8 | site 3 |
| 0x294014 | OniBall_ctor | orb construction |
| 0x2941e4 | OniBall_run | orb movement |
| 0x2946f8 | OniBall_onTouch | orb pick-up |

#### Not determined

- Delivery of the pending pools (+0xb4, +0xc8) to hit points and mana (`Player_regenHealth`
  0x1b3b90 and 0x1b3900 were not read here).
- What status counters 8 and 10 do when set to 30.
- `describeRank` 0x2f8d7c and the orb destructor 0x3c5db0 were not opened.
- Whether `Creature_processDamage` runs during prediction (second bullet above).

### 60 Blunt and 61 Slashing — SkillBlunt, SkillSlashing

#### Identity

| Item | Id 60 | Id 61 | Evidence |
|---|---|---|---|
| Name | `Blunt` | `Slashing` | Observed: strings stored at 0x16b338 and 0x16b3c8 |
| Class, virtual table | `SkillBlunt`, 0x512808 | `SkillSlashing`, 0x512780 | Observed |
| Skill object, table entry | 0x6e2cd0, 0x41b260 | 0x6e2d38, 0x41b264 | Observed |
| Constructor | inline in the static initialiser 0x16ac74, at 0x16b2cc-0x16b340 | same, 0x16b35c-0x16b3d0 | Observed |
| Kind, flags, recast | 3 (passive), 0, 30 | same | Observed |
| Own virtual functions | slot 4 (rank text) 0x3c8b24 only | slot 4 0x3c8bec only | Observed with the table tool; every other slot is the base `Skill` function (canUse returns 1, cast returns null, manaCost returns 1.0, initStats 0x3c85b0) |
| Effect objects | none | none | |
| Who has it | all seven class trees (row level 1, no prerequisite) | barbarian, shadowknight, ranger, berserker, shaman (row level 1, no prerequisite) | Observed in the tree dump |
| Type | passive weapon-damage multiplier for weapons of damage type 1 | the same for damage type 8 | |

The small functions at 0x16a98c-0x16ac74, in front of the static initialiser, belong to
other ids (constructors and statistics of ids 25 and 27 to 30); none of them serves ids 60
or 61. Observed.

#### Statistics

Base `Skill_initStats` 0x3c85b0 fills all five tier-1 entries with first level 0, base 1,
step 2.0 (0x40000000); tier 2 none. Verified by reading the function: a five-pass loop
storing 0 at +0x0e + 2i, 1 at +0x18 + 2i and 0x40000000 at +0x24 + 4i.

**No gameplay code reads these tables.** Nothing references the two table entries except
the generic skill screen. The effect uses the rank number directly:

- multiplier(rank) = 1.0 when rank is 0, else (float) rank x 0.049999997 (0x3d4ccccc) +
  1.15 (0x3f933333). Observed 0x1b72a4-0x1b7330.

| Rank | Multiplier (round-to-nearest) | Multiplier (truncating arithmetic) |
|---|---|---|
| 1 | 1.1999999 (0x3f999999) | same |
| 2 | 1.25 (0x3fa00000) | 1.2499999 (0x3f9fffff) |
| 5 | 1.4 (0x3fb33333) | 0x3fb33332 |
| 10 | 1.65 (0x3fd33333) | 0x3fd33332 |
| 15 | 1.8999999 (0x3ff33332) | same |
| 20 | 2.1499999 (0x40099999) | same |

The rank text (slot 4) prints 5 x rank + 10 for rank > 0 and 0 otherwise, which is five
points less than the multiplier's percentage (5 x rank + 15). Observed 0x3c8b24; which rank
the screen passes was not checked.

#### Cost and limits

None; never cast.

#### Behaviour

Readers of the two ranks (complete scan of `player_getSkillRank` call sites and of Player
slot 39 uses): `Player_recalcDamage` 0x1b72ac, 0x1b72bc (id 60), 0x1b72f0, 0x1b7304 (id 61);
`inventory_checkEquipAllowed` 0x1c4d0c (60), 0x1c4d60 (61); the skill screen 0x1d5548 (60),
0x1d55c8 and 0x1d56ac (61). `Player_meleeHit` 0x1b6a98 does not read the ranks itself; it
calls `Player_recalcDamage` and passes the record's results to `damage_apply`.

**Site 1: weapon damage.** `Player_recalcDamage(player, weapon, withElemental)` 0x1b7158.
R is the player record of slot player+0x3c8; `def` is the weapon's item definition
(first word of the item), def+0x1e its weapon class (4 bow, 6 thrown), def+0x20 its damage
type (1, 4 or 8; docs/gameplay.md names them blunt, pierce, slash).

```
s4 = R.stat0 (+0x90) / 4;  d4 = R.stat2 (+0x98) / 4          # signed, toward zero
R.min (+0xd0) = 1;  R.max (+0xd4) = 2;  R.attack (+0xcc) = R.level (+0x58) * 20
if weapon == null:                                            # unarmed: no weapon skill
    R.min = s4 + 1;  R.max = s4 + 2;  R.attack += s4;  go to the AncestralCall step
item_getDamageRange(weapon, &R.min, &R.max, withElemental)
R.attack += item_getModifiedField1a(weapon)
add = d4 if def.class is 4 or 6 else s4
R.min += add;  R.max += add;  R.attack += add
mB = 1.0;  mS = 1.0
if rank(60) != 0: mB = (float) rank(60) * 0.05f + 1.15f
if rank(61) != 0: mS = (float) rank(61) * 0.05f + 1.15f
(class 4: Archery bonus; class 6: thrown-weapon bonus; ids 48 and 79, not part of this section)
if R.secondWeapon (+0x443c) != null and def.class != 6:
    p = level of the class passive with mask 0x40000 (0 when the slot is 5 or more, the class
        has no such row, or the stored level is negative)
    f = ((float) p * 2.5 + 100.0) * 0.01                      # 0x40200000, 0x42c80000, 0x3c23d70a
    if def.type == 1: mB = mB * f
    elif def.type == 8: mS = mS * f
if def.type == 1:   R.min = trunc((float) R.min * mB + 0.5);  R.max = trunc((float) R.max * mB + 0.5)
elif def.type == 8: R.min = trunc((float) R.min * mS + 0.5);  R.max = trunc((float) R.max * mS + 0.5)
(then the class-4 step, the AncestralCall step of section 51, the class steps and the
 x1.5 / x1.2 status steps)
```

Points to note (Observed 0x1b71a4-0x1b76d0):

- Only minimum and maximum damage are multiplied; the attack rating is not.
- Damage type 4 gets neither multiplier.
- Rank 0 gives exactly 1.0; rank 1 gives 1.2, so the first rank is worth 20 %, each later
  rank 5 points.
- The multiplication uses the weapon the function was called with. `Player_meleeHit` calls
  it with the main weapon, or with the second weapon on alternate swings of a dual wielder
  (0x1b6ce8), and again with a null weapon for weapon style 4 or a class-6 item (0x1b6ddc).
- Rounding is x + 0.5 truncated, on a single-precision product. With truncating arithmetic
  the rank-2 and rank-10 multipliers are one unit lower than with round-to-nearest, and a
  base of 10 becomes 12 instead of 13 (rank 2) and 16 instead of 17 (rank 10).

Worked values (base value after the statistic add -> result), round-to-nearest /
truncating where they differ:

| Rank | 10 | 20 | 37 | 100 |
|---|---|---|---|---|
| 1 | 12 | 24 | 44 | 120 |
| 2 | 13 / 12 | 25 | 46 | 125 |
| 10 | 17 / 16 | 33 | 61 | 165 |
| 20 | 21 | 43 | 80 | 215 |

**Site 2: item requirements.** `inventory_checkEquipAllowed(slot, item)` 0x1c4948: the
item's four effect entries (8 bytes each at item+0x24: s16 type, s16 value, ...) are
searched for type 0x27 and type 0x28. If rank(60) < the value of the first type-0x27 entry
(0 when there is none) the result code becomes 7; then if rank(61) < the value of the first
type-0x28 entry the result code becomes 8. Later tests in the same function can replace the
code again. Observed 0x1c4d0c-0x1c4db0. (Result codes other than 0 mean "cannot equip" with
a reason; the caller's handling was not read.)

**Site 3: skill screen.** `skills_screen` 0x1d4660, prerequisite test of a tree row
(0x1d5530-0x1d5778): a row whose prerequisite field is 0 ("either weapon skill") is
satisfied by rank(60) >= 1 or rank(61) >= 1 (0x1d5548, 0x1d55c8). One hard-coded
alternative uses id 61: for class 3 (ranger) the row whose id-or-mask field is 0x40 (the
ranger passive with mask 0x40, normally needing skill 48) is also satisfied by rank(61) >= 1
(0x1d56ac). Observed.

**Non-player, prediction copy.** Only player records have ranks. `Player_recalcDamage` is
reached for the prediction copy only through callers that are not the melee hit
(`Player_meleeHit` returns at once for the copy); it writes the shared record either way.

#### Random draws

None.

#### Presentation only

The rank text of slot 4.

#### Per-machine state

None found in the skill itself. `Player_recalcDamage` is also called from the statistics
screen (0x1d2c38, 0x1d2d30), a local UI path that rewrites record +0xcc, +0xd0 and +0xd4
with whatever weapon argument the screen passes; every melee hit recalculates first, so
melee is not affected, but any reader of those fields that does not recalculate would see a
per-machine value. Whether such a reader exists is Unknown (not traced here).

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x16b2cc-0x16b3d0 | part of the skill static initialiser 0x16ac74 | the two inline constructors |
| 0x3c85b0 | base Skill initStats | first 0, base 1, step 2.0 for all five |
| 0x3c8b24 | SkillBlunt_slot4 | rank text: 5 x rank + 10 |
| 0x3c8bec | SkillSlashing_slot4 | same shape (not opened beyond its size and position) |
| 0x1b7158-0x1b76d0 | Player_recalcDamage, first half | site 1 |
| 0x1b6a98 | Player_meleeHit | caller; no rank read of its own |
| 0x1c4948 (0x1c4cf8-0x1c4db0) | inventory_checkEquipAllowed | site 2 |
| 0x1d4660 (0x1d5530-0x1d5778) | skills_screen | site 3 |
| 0x1bf330 | player_getSkillRank | record +0x4b08 list lookup |

#### Not determined

- Which of the four effective statistics +0x90 and +0x98 are (docs/player.md calls them
  strength and dexterity in its attack-rating row).
- The meaning of every result code of the equip check, and which items carry type-0x27 or
  type-0x28 requirements.
- Which class rows have mask 0x40000 besides the barbarian one seen in the tree dump.
- Whether ranged and thrown attacks recalculate before every shot (their code was not
  traced), which decides whether a bow of damage type 1 or 8 would get these multipliers.

### 62 strongstance — SkillStrongStance

#### Identity

| Item | Value | Evidence |
|---|---|---|
| Id, name | 62 (0x3e), `strongstance` | Observed: constructor 0x30839c |
| Class | `SkillStrongStance`, virtual table 0x51b528; own cast 0x308434 (returns null), describeRank 0x30845c, manaCost 0x3084e4 (returns 0.0), initStats 0x308410; canUse is the base (returns 1) | Observed |
| Skill object | 0x6e2da0, table entry 0x41b268 | Observed: static initialiser 0x16b3f4 |
| Kind, flags, recast | 3 (passive), 0, 30 (unused) | Observed |
| Effect objects | no Spell. On a successful roll against a heavy knockback: one `LightEffect` (0xbc) and one `StrongStancePhantom` (0x3d8 bytes, a Creature subclass, virtual table 0x50f448) | Observed 0x308578 |
| Who has it | barbarian tree (row level 10, prerequisite skill 49) | Observed in the tree dump |
| Type | passive: a percent chance to ignore a heavy knockback (no knock-down state, no knock-down animation, no push) |

#### Statistics

`SkillStrongStance_initStats` 0x308410. Other statistics zero; tier 2 none.

| Stat | Meaning | Tier 1: first, base, step | Tier 2 |
|---|---|---|---|
| 0 | chance in percent to resist (Observed: compared with draw mod 100 at 0x1b2dcc-0x1b2dd8) | 1, 5, 4.99997282 (0x409fffc7) | none |

`SkillStrongStance_getStat0(skill, rank)` 0x30851c = slot 10 (0, slot 14 (rank, 20)); slot 14
is the base, so no cap. Rank 1 / 10 / 20: 5 / 50 / 100. Ladder: 5 x rank for every rank 1 to
20 (the step shortfall never crosses a rounding boundary).

#### Cost and limits

None. manaCost returns 0.0 after calling slot 14; cast copies the position argument and
returns null without drawing.

#### Behaviour

One call site for each helper, both in `Player_processDamage` 0x1b2cc0, which `Player_run`
calls once per frame (also for the prediction copy). The relevant head of that function,
0x1b2ce8-0x1b3030:

```
flags = u32 player+0x2dc                         # pending damage flags of this frame's hits
if not (flags & 0x20000000):
    if g_cutsceneActive or dialog_isOpen(): player+0x2dc = 0; player+0xc8 = 0; return
rel = (s16)(u16 player+0x2e0 - u16 player+0x38)  # knock direction minus facing
sev = 0; resist = false
if (flags & 0x3c0000) != 0 and player+0x58c != 6 and player+0x58c != 10:
    rank   = player->slot39(62)                  # virtual call at 0x1b2d6c
    chance = SkillStrongStance_getStat0(SKILL[62], rank)
    d      = next shared draw                    # always, also with rank 0
    resist = (d mod 100) < chance                # unsigned remainder, signed compare
    if   flags & 0x40000:  force = 100.0; sev = 1
    elif flags & 0x80000:  force = 150.0; sev = 2
    elif flags & 0x100000: force = 200.0; sev = 3
    else:                  force = 250.0; sev = 3          # 0x200000
    float player+0x2e8 = force
if g_pvpModeA != 0:
    if sev == 0: skip to the damage part
    sev = sev - 1;  player+0x2e8 *= 0.5
if sev <= 0: skip to the damage part
if player+0x58c == 8 and (rel < -0x5fff or rel >= 0x6000): sev = sev - 1     # blocking, knock direction opposite to the facing
light = sev < 2
if light or not resist:
    player+0x58c = 3; player+0x448 = g_simFrame
    if net_isLocalSlot(slot): g_forceGhostRebase = 1
    player_voice(slot, 12)
if light:
    (unless flags & 0x400000) start the ordinary hit animation
else:
    name = ("knockdown2_" if weapon style is 2 or 3 else "knockdown1_")
         + ("a.anm" if rel < -0x5fff or rel >= 0x6000
            else "c.anm" if ((rel + 0x6000) & 0xffff) <= 0x4000
            else "b.anm" if ((rel + 0x2000) & 0xffff) <= 0x4000
            else "d.anm")
    if resist:
        if not (player flags & 0x20000):
            SkillStrongStance_trigger(SKILL[62], player, name, trunc(player+0x2e8))
        player+0x2e8 = 0.0
    else:
        start animation `name` on the player (flags 0x80a) unless it is already playing
```

So the skill only matters for a knockback that is still "heavy" (severity 2 or more) after
the PvP and blocking reductions: on success the player keeps its action state, plays no
knock-down animation and has the knockback speed zeroed. Light staggers (severity 1) always
put the player in state 3, whatever the roll. The damage amount is not changed. The roll is
skipped entirely in action states 6 and 10. Observed.

`SkillStrongStance_trigger(skill, player, animName, force)` 0x308578:

1. n = `model_getSamplePointCount(player model)`.
2. Allocate 0xbc bytes; when that succeeded construct a `LightEffect` at the player position
   with 36 added to the height, no owner: start colour (128, 100, 100, 0), end colour 0,
   radius 120 falling to 36, duration 0.5 s. **One shared draw.**
3. 25 particles (definition 0x8e7368): each takes one draw of the third generator 0x404468
   (index = draw mod n of a model sample point) and three cosmetic draws per attempt of a
   rejection loop for a direction (speed 10).
4. Allocate 0x3d8 bytes; when that succeeded `StrongStancePhantom_ctor(obj, player, animName,
   force, 0)`. **One shared draw** (the GameObject constructor inside `Creature_ctor`; the
   Creature constructor and its statistics helper draw nothing).

**`StrongStancePhantom`** (constructor 0x1618d4; a ghost image that plays the knock-down the
player avoided):

| Offset | Type | Initial value | Meaning |
|---|---|---|---|
| +0x000 | Creature | `Creature_ctor(0, obj, 0, &player position, player facing, player+0x24, 0)`: no type name, so default statistics | base; shares the player's animation set |
| +0x00c | u32 | OR 0x4005 | not solid (0x1), 0x4 (excluded from the sphere and arc queries with mask 0xd), transient (0x4000) |
| +0x01c | float | 24.0 | radius |
| +0x0a8 | u64 | OR bit 63 | "is active" creature flag |
| +0x114 | animation state | cleared, then `anim_startBlendInOut(0, 0, state, animName looked up in the set, 0x802)` | the knock-down clip |
| +0x2e0 | s16 | player+0x2e0 | knock direction |
| +0x2e8 | float | (float) force x 1.25 | knockback speed |
| +0x3c8 | handle | linked to the player | owner (note: the offset where a Player keeps its slot number) |
| +0x3cc | float | 75.0 (kind 0) or 240.0 | frames left |
| +0x3d0 | float | same as +0x3cc | initial frames (fade denominator) |
| +0x3d4 | s32 | kind: 0 from Strong Stance; the other caller 0x313198 passes its own value | |

The constructor also puts the object on the every-frame run list.

`StrongStancePhantom_run` 0x161a54, once per frame: `Creature_stepAnim(1.0, this)`;
`Creature_applyKnockback(0.5, this)` (moves along +0x2e0 with velocity speed x 0.5 through
`Creature_moveBy`, then speed -= 2 with a floor of 0; dust particles from the object's own
generator); `Creature_moveBy(this, zero vector)`; +0x3cc -= 1.0; when the result is below
1.0 the object is deleted (`obj_delete`). Kind 0 therefore lives 75 run calls.
`StrongStancePhantom_draw` 0x161adc draws one glow per sample point of the owner's model at
the phantom's pose, with brightness (+0x3cc / +0x3d0) x 128, and nothing when the owner
handle is empty. Slot 15 is its own clone function 0x131570.

**Non-player.** `Player_processDamage` is a Player function; monsters have no equivalent
call. The cast slot returns null for any caster.

#### Random draws

1. `Player_processDamage`: one shared draw per call whose pending flags contain any of
   0x3c0000 while the action state is not 6 or 10. Independent of rank.
2. Trigger (real player, heavy knockback, roll succeeded), in order: one shared draw (light,
   if allocated); 25 x (one draw of 0x404468, then 3 cosmetic draws per rejection attempt);
   one shared draw (phantom, if allocated).
3. Phantom, per run call while it moves and did not hit a wall or object: two dust puffs of
   at least 9 draws each from the phantom's own generator (obj+0x44).

#### Presentation only

Light, particles, the phantom's drawing and dust, the voice cue, `describeRank` 0x30845c.
The phantom is a real Creature object in the world lists, but nothing in its class deals
damage or changes another object.

#### Per-machine state

- The trigger uses generator 0x404468 to choose particle sample points and the cosmetic
  generator for directions; both feed particles only. Observed.
- The prediction copy takes the shared draw of step 1 (no 0x20000 test before it) but never
  calls the trigger, so the two constructor draws happen only for the real player. The
  prediction loop restores the shared generator (docs/skills.md), so this is consistent as
  long as that holds.
- `net_isLocalSlot` / `g_forceGhostRebase` in the stagger branch belong to the netcode, not
  to the skill; a successful resist of a heavy knockback skips that branch, so the forced
  rebase does not happen on that frame.
- Allocation caveat: each of the two shared draws in the trigger depends on its pool
  allocation succeeding.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x30839c | SkillStrongStance_ctor | kind 3 |
| 0x308410 | SkillStrongStance_initStats | statistic 0 |
| 0x308434 | SkillStrongStance_cast | returns null |
| 0x30845c | SkillStrongStance_describeRank | text only |
| 0x3084e4 | SkillStrongStance_manaCost | returns 0.0 |
| 0x30851c | SkillStrongStance_getStat0 | chance for a rank |
| 0x308578 | SkillStrongStance_trigger | light, particles, phantom |
| 0x3088b8 | strongStance_staticInit | particle definition (not opened) |
| 0x1618d4 | StrongStancePhantom_ctor | above |
| 0x161a54 | StrongStancePhantom_run | above |
| 0x161adc | StrongStancePhantom_draw | above |
| 0x3c4c88 | StrongStancePhantom_dtor | clears the owner handle, Creature destructor |
| 0x115eb8 | Creature_applyKnockback | push and decay |
| 0x1b2ce8-0x1b3030 | part of Player_processDamage | the roll and its use |

#### Not determined

- Which attacks set the four knockback bits 0x40000 to 0x200000 (they come in through the
  take-damage flags; the setters are in the monster and skill code).
- Units of the velocity handed to `Creature_moveBy`, and therefore the phantom's exact path.
- What the second caller of the phantom constructor (0x313198, in the id-68 code range) uses
  it for.
- Whether anything can target or damage the phantom (its flags exclude it from the arc and
  sphere queries; other queries were not checked).

### 63 naturalresistance — SkillNaturalResistance

#### Identity

| Item | Value | Evidence |
|---|---|---|
| Id, name | 63 (0x3f), `naturalresistance` | Observed: constructor 0x30895c |
| Class | `SkillNaturalResistance`, virtual table 0x51b5b0; own describeRank 0x3089f4 and initStats 0x3089d0; canUse, cast and manaCost are the base functions (1, null, 1.0) | Observed with the table tool |
| Skill object | 0x6e2e08, table entry 0x41b26c | Observed: static initialiser 0x16b40c |
| Kind, flags, recast | 3 (passive), 0, 30 (unused) | Observed |
| Effect objects | none | |
| Who has it | barbarian tree (row level 24, prerequisite skill 64) | Observed in the tree dump |
| Type | passive: a flat addition to all five elemental resistances of the player object |

#### Statistics

`SkillNaturalResistance_initStats` 0x3089d0. Other statistics zero; tier 2 none.

| Stat | Meaning | Tier 1: first, base, step | Tier 2 |
|---|---|---|---|
| 0 | percentage points added to each resistance (Observed: getter 0x308a7c = value x 0.01, added at 0x1b5d00-0x1b5d20) | 1, 3, 3.00495481 (0x4040512e) | none |

`SkillNaturalResistance_getStat0Fraction(skill, rank)` 0x308a7c = (float) slot 10 (0, slot
14 (rank, 1)) x 0.01 (0x3c23d70a). Rank 1 / 10 / 20: 3 / 30 / 60, i.e. fractions 0.03, 0.30,
0.60. Ladder: 3 x rank for every rank 1 to 20.

#### Cost and limits

None; never cast.

#### Behaviour

One reader of the rank (0x1b5ccc) and one caller of the getter (0x1b5cdc), both in
`player_recalcArmor(slot)` 0x1b5790, whose only caller is `player_recalcStats` 0x1b6458
(0x1b6954). The function does nothing when the slot's object pointer (record +0x43d8) is
null. Otherwise:

1. It zeroes the five floats object+0x5c, +0x60, +0x64, +0x68, +0x6c (fire, cold, poison,
   disease, lightning resistance; names from docs/gameplay.md).
2. It adds the contributions of the equipped items (not part of this section).
3. Natural Resistance, 0x1b5cc8-0x1b5d20:

```
f = SkillNaturalResistance_getStat0Fraction(SKILL[63], player_getSkillRank(slot, 63))
for i in 0 .. 4:
    r = float object[+0x5c + 4*i] + f
    object[+0x5c + 4*i] = r
    if 1.0 < r: object[+0x5c + 4*i] = 1.0
```

4. It returns the armour total plus statistic +0x98 / 2.

Consequences (Observed):

- The addition is the same for all five resistances and comes after the items, so the cap
  of 1.0 is applied to the sum; this step is also what caps item-only resistance, and it
  runs for every player (with f = 0 at rank 0).
- There is no lower clamp: a negative item total stays negative after the addition.
- The value changes only when `player_recalcStats` runs (construction, equipment changes
  and the other callers of 0x1b6458; 14 references). Whether buying a rank triggers it was
  not checked.
- The resistances are consumed by `damage_apply` (elemental entries scale by 1 - resistance
  and derive the status strength from it; docs/gameplay.md section 2.2).

**Non-player.** Monsters have no such call; their resistances come from their own data.

#### Random draws

None.

#### Presentation only

`describeRank` 0x3089f4.

#### Per-machine state

- The write goes to the object the player table points at. During prediction that entry is
  the copy (docs/player.md), so a recalculation that happened inside prediction would
  update the copy's resistances and not the real object's. Whether `player_recalcStats` can
  run inside prediction was not checked. Unknown.
- Nothing else: no generator, camera or local-slot use.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x30895c | SkillNaturalResistance_ctor | kind 3 |
| 0x3089d0 | SkillNaturalResistance_initStats | statistic 0 |
| 0x308a7c | SkillNaturalResistance_getStat0Fraction | statistic 0 x 0.01 |
| 0x1b5790 (head and 0x1b5cc8-0x1b5d38) | player_recalcArmor | the only use |

#### Not determined

- The item part of `player_recalcArmor` (read only far enough to place the skill step).
- The callers of `player_recalcStats` were counted, not classified.
- `describeRank` 0x3089f4 was not opened.

### 64 stunningstrike — SkillStunningStrike

#### Identity

| Item | Value | Evidence |
|---|---|---|
| Id, name | 64 (0x40), `stunningstrike` | Observed: constructor 0x308af0 |
| Class | `SkillStunningStrike`, virtual table 0x51b638. Slots 1, 2, 5 are the base functions (canUse returns 1, cast returns null, manaCost returns 1.0); own functions: describeRank 0x308b88, initStats 0x308b64 | Observed with the table tool |
| Skill object | 0x6e2e70, table entry 0x41b270 | Observed: static initialiser 0x16b424 |
| Kind | 3 (passive) | Observed: +0x08 = 3 at 0x308af0 |
| Flags, recast | 0; 30 (never used, the skill is not cast) | Observed |
| Effect objects | no Spell. One `LightEffect` (0xbc bytes, GameObject, virtual table 0x50e198) per successful roll | Observed 0x308d20-0x308dcc |
| Who has it | barbarian tree (row level 19, prerequisite skill 35) | Observed in the tree dump |
| Type | passive: a per-hit chance, rolled inside `damage_apply`, to stun the victim |

#### Statistics

`SkillStunningStrike_initStats` 0x308b64 sets one statistic; the other four keep zero first
level, base and step. Tier 2: none.

| Stat | Meaning | Tier 1: first, base, step | Tier 2 |
|---|---|---|---|
| 0 | stun chance in percent (Observed: compared with draw mod 100 at 0x1ea850-0x1ea85c) | 1, 5, 2.25196481 (0x40102031) | none |

Read with slot 10 (0, rank). Rank 1 / 10 / 20: 5 / 25 / 48. Full ladder: 5, 7, 10, 12, 14,
16, 19, 21, 23, 25, 28, 30, 32, 34, 37, 39, 41, 43, 46, 48.

#### Cost and limits

None: no mana, no recast, no canUse condition. The rank is read from the attacker's record
at the moment of each hit.

#### Behaviour

The whole skill is two helper functions called from one place, `damage_apply` step 29
(0x1ea7f0-0x1ea870), directly after the victim's take-damage virtual has been called for a
landed hit. The block runs only when the attacker is non-null and has object flag 0x40
(player). It is not limited to weapon swings: nothing at the call site looks at the damage
flags, the amount or the weapon, so every `damage_apply` call that lands and names the
player object itself as attacker (melee, and any skill or timed damage that passes the
player rather than a projectile object) goes through the roll. Observed for the call site;
which callers pass the player object was not enumerated.

```
rank   = player_getSkillRank(attacker+0x3c8, 64)
chance = SkillStunningStrike_getStat0ForTarget(SKILL[64], victim, rank)
d      = next shared draw (16 bits)                 # always, also with rank 0
if (d mod 100) < chance:                            # unsigned remainder, signed compare
    SkillStunningStrike_spawnEffect(SKILL[64], victim, rank)
```

`SkillStunningStrike_getStat0ForTarget(skill, target, rank)` 0x308c10:

```
if target == null: return 0
if target lacks object flag 0x20 (creature): return 0
if g_pvpModeA != 0: return 0
c = skill.slot10(0, rank)                           # 0 when rank is 0
b = creature_bossRank(target)                       # 0x10d940
if b >= 2: return 0
if b <= 0: return c
return min(c, 5)                                    # b == 1
```

`SkillStunningStrike_spawnEffect(skill, target, rank)` 0x308cb4 (the rank is not used):

1. Return when target is null or not a creature.
2. Sound at the target position (`sound_playAtPos`, resource `spel_bw_stunstrike.anm`).
3. Allocate 0xbc bytes. When that succeeded construct a `LightEffect` at the target position
   with 64 added to the height, no owner: start colour (161, 138, 64, 0), end colour all 0,
   start radius 180, end radius 60, +0x78 value 0.5, duration 0.5 s (30 frames). **One shared
   draw** (GameObject constructor).
4. **One shared draw** d2; frames = trunc(((float) d2 x 1.5258789e-05 (0x37800000) + 1.5
   (0x3fc00000)) x 60.0 (0x42700000)). Range 90 to 149 frames (1.5 s to just under 2.5 s).
5. target->slot 30 (frames, 1).

**Slot 30** for every monster class is the base `Creature_stun(creature, frames, flash)`
0x118a58 (the only class with a different slot 30 is Player, whose slot is an empty function
0x3c3b10; Observed by scanning all creature virtual tables):

```
if creature_bossRank(creature) != 0: return          # mini-bosses and bosses are never stunned
if s16 creature+0x232 == 0x14: return                # dead
s16 creature+0x31c = frames                          # overwrite, not max and not add
creature->slot27(0x13)                               # setState(stunned), the class's own body
if flash: s16 +0x90 = 58, +0x92 = 155, +0x94 = 154, +0x96 = 72, +0x98 = 58, +0x9a = 155, +0x9c = 154
```

What the timer then does is base creature behaviour, restated here because it defines the
stun: `Creature_run` subtracts 1 from +0x31c every frame while it is non-zero
(0x112d0c-0x112d20) and spawns effect 0x10 above the creature on frames where `g_simFrame`
and 3 is 0; `Creature_filterState` 0x10a9c0, the filter the classes' setState bodies call,
replaces any requested state by 0x13 while +0x31c is non-zero (the root timer is tested
first and wins), and a request for state 0x14 (dead) zeroes the timer. Observed.

Consequences (Observed from the three functions):

- Against a creature of boss rank 1 the chance is capped at 5 % but `Creature_stun` then
  refuses: the sound, the light and both draws happen and nothing is stunned.
- Against a player victim outside PvP mode A the roll can succeed and slot 30 does nothing.
- A second stun replaces the remaining time, even with a shorter one.
- A victim killed by the same hit still goes through the roll; the dead test in
  `Creature_stun` stops the stun, not the draws.
- In PvP mode A the chance is 0 for everything.

**Non-player attacker:** the block is skipped (no draw). **Prediction copy as attacker:**
`damage_apply` returns in its first test. The base cast (slot 2, 0x3c8220) returns null
without drawing, so a weapon-effect entry naming id 64 does nothing.

#### Random draws

In `damage_apply` order, all from the shared generator:

1. One draw per landed `damage_apply` call with a player attacker, compared (mod 100) with
   the chance. Taken even when the attacker has no rank.
2. On success: one draw in the `LightEffect` constructor (skipped if the allocation fails).
3. On success: one draw for the stun length.

#### Presentation only

The sound, the light, the colour flash written by `Creature_stun`, the periodic effect 0x10
while stunned, `describeRank` 0x308b88 (statistic 0).

#### Per-machine state

None found. The chance depends on `g_pvpModeA`, the victim's boss rank and the attacker's
record; the draws are unconditional once the block is entered. If the 0xbc-byte pool
allocation failed on one machine only, that machine would take one draw fewer (the usual
allocation caveat; Inferred).

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x308af0 | SkillStunningStrike_ctor | kind 3 |
| 0x308b64 | SkillStunningStrike_initStats | statistic 0 |
| 0x308b88 | SkillStunningStrike_describeRank | text only |
| 0x308c10 | SkillStunningStrike_getStat0ForTarget | chance for a victim |
| 0x308cb4 | SkillStunningStrike_spawnEffect | sound, light, stun |
| 0x1ea7f0-0x1ea870 | part of damage_apply | the roll |
| 0x118a58 | Creature_stun | base slot 30 |
| 0x112d0c-0x112d60 | part of Creature_run | timer step |
| 0x10a9c0 | Creature_filterState | forces state 0x13 |
| 0x201bd8 | LightEffect_ctor | field layout below |
| 0x3c8218, 0x3c8220, 0x3c82a8 | base Skill slots 1, 2, 5 | return 1, null, 1.0 |

`LightEffect` layout as written by its constructor (register arguments: start colour in the
first four float registers, end colour in the next four, object, position pointer, owner,
one word; stack: start radius, end radius, one float, duration in seconds):

| Offset | Type | Meaning |
|---|---|---|
| +0x00..+0x4b | GameObject | base; flags OR 3 |
| +0x4c | light node | linked into the light grid; +0x54, +0x55 u8 = 0; +0x56 s16[4] colour; +0x5e s16[4] colour; +0x68, +0x70 float radius; +0x6c, +0x74 float 1 / radius squared; +0x78 float (third stack argument); +0x7c float[3] position |
| +0x88 | handle | owner link (only when an owner is given) |
| +0x8c | float[4] | current colour |
| +0x9c | float[4] | colour change per frame = (end - start) / frames |
| +0xac, +0xb0 | float | current radius; radius change per frame |
| +0xb4 | s32 | end frame = `g_simFrame` + frames, frames = max(1, trunc(duration x 60)) |
| +0xb8 | u32 | the last register argument |

#### Not determined

- The `LightEffect` run function (0x1ee050 according to docs/gameplay.md) was not read; the
  object is assumed to do nothing but fade and delete itself at +0xb4.
- What each monster class does in state 0x13 (class-specific setState and run bodies).
- The full name list inside `creature_bossRank` (only its shape was read: 2 for a fixed list
  of type names, otherwise bit 0 of the creature flags).

### 65 giantgrowth — SkillGiantGrowth

#### Identity

| Item | Value | Evidence |
|---|---|---|
| Skill id / internal name | 65, `giantgrowth` | Observed: `SkillGiantGrowth_ctor` 0x308e64 |
| Skill class, virtual table | `SkillGiantGrowth`, 0x51b6f0 | Observed |
| Skill object | 0x6e2ed8 | `tools/dump_tables.py --table skills` |
| Kind (+0x08) | 0, ordinary active cast | Observed |
| Flags (+0x04) | 0: the prediction copy may not cast it | Observed |
| Recast (+0x0c) | 30 frames | Observed |
| Effect class | `SpellGiantGrowth`, 0x138 bytes, virtual table 0x51b6c0, constructor 0x3090d0, destructor 0x309368, run 0x309420 (draw and slot 4 are the base ones) | Observed 0x308fcc-0x308fec |
| Who has it | shaman tree (level 21, needs skill 94). No monster call site known | §1.7 |

A timed self-buff: the caster's model scale grows by 0.006 per frame to a target, stays
there, shrinks back the same way, and the spell ends about 30 frames later. While it exists
it rewrites the caster's movement-speed multiplier every frame, and `Player_recalcDamage`
uses the current scale as a melee damage and attack-rating multiplier.

#### Statistics

Set by `SkillGiantGrowth_initStats` 0x308ed0 (Observed). Stats 2 and 3 are not written and
not read. No tier-2 tables. Both reads are slot 10 `getStat(stat, level)` in the constructor.

| Stat | Meaning (how known) | Tier 1: first, base, step |
|---|---|---|
| 0 | size increase in percent: target scale = stat * 0.01 + 1.0 (Observed: ctor 0x309244-0x30928c) | 1, 50, 2.50097 (0x40200fe4) |
| 1 | hold counter in seconds: +0x20 = stat * 60 frames (Observed: ctor 0x309288-0x3092a8) | 1, 5, 0.500001 (0x3f000010) |
| 4 | mana cost (Observed: slot 15 via 0x30909c) | 1, 75, 7.50078 (0x40f00663) |

| Rank | stat 0 (%) | target scale | stat 1 (s) | stat 4 (mana) |
|---|---|---|---|---|
| 1 | 50 | 1.50 | 5 | 75 |
| 2 | 53 | 1.53 | 6 | 83 |
| 3 | 55 | 1.55 | 6 | 90 |
| 4 | 58 | 1.58 | 7 | 98 |
| 5 | 60 | 1.60 | 7 | 105 |
| 6 | 63 | 1.63 | 8 | 113 |
| 7 | 65 | 1.65 | 8 | 120 |
| 8 | 68 | 1.68 | 9 | 128 |
| 9 | 70 | 1.70 | 9 | 135 |
| 10 | 73 | 1.73 | 10 | 143 |
| 11 | 75 | 1.75 | 10 | 150 |
| 12 | 78 | 1.78 | 11 | 158 |
| 13 | 80 | 1.80 | 11 | 165 |
| 14 | 83 | 1.83 | 12 | 173 |
| 15 | 85 | 1.85 | 12 | 180 |
| 16 | 88 | 1.88 | 13 | 188 |
| 17 | 90 | 1.90 | 13 | 195 |
| 18 | 93 | 1.93 | 14 | 203 |
| 19 | 95 | 1.95 | 14 | 210 |
| 20 | 98 | 1.98 | 15 | 218 |

The target scale is the single-precision value of ((float)stat0 * 0.01 (0x3c23d70a)) + 1.0,
e.g. 1.5 exactly at rank 1 and 1.7300000190734863 at rank 10.

#### Cost and limits

- Mana: slot 15 with (level, 10) = round(75 + 7.50078 * (rank - 1)): 75, 143, 218 at ranks
  1, 10, 20. Recast 30 frames. Observed 0x30909c.
- `SkillGiantGrowth_canUse` 0x308f2c: allowed only when the caster has no
  `SpellGiantGrowth` attached. So it cannot be refreshed or stacked while one is running
  (about 469 frames at rank 1, 1229 at rank 20, see below). Observed.
- `SkillGiantGrowth_cast` refuses a caster that is not a player (below).
- Prediction copy: cannot cast (flag bit 0 clear).

#### Behaviour

**Cast** — `SkillGiantGrowth_cast` 0x308f60 (skill, level, caster, pos*, facing). Observed.
level = slot 14 `adjustLevel(level, 10)` (unchanged). **If the caster does not have object
flag 0x40 (player) the function returns null** (test at 0x308fc0). Otherwise
`pool_new(0x138)` and `SpellGiantGrowth_ctor(spell, level, caster, skill)`. Position and
facing are unused.

**When the spell runs.** A player's attached spells are not run from `Creature_run` (its
slot-17 call at the top is made only for objects without flag 0x40). `Player_run` 0x1a5030
runs them through `Player_updateCast` 0x1a3f70, called at 0x1ac6a8 — after `Creature_run`,
`Player_processDamage` and the action-state switch — and **only when the record's hit
points (+0xac) are above 0.0** (test at 0x1ac68c-0x1ac69c). The cast happens inside the
state switch, so run call 1 is made **in the cast frame itself**, at the end of that
`Player_run`. While the owner's hit points are <= 0 the spell is not run at all: scale,
counter and speed multiplier stay frozen at their last values until the player object is
destroyed (which deletes the spell and runs the destructor below). Observed.

**Constructor** — `SpellGiantGrowth_ctor` 0x3090d0. Observed, in order:

1. Base part, owner = caster, one shared draw for the private generator.
2. +0xf8 handle = 0; light node at +0xfc: colour (200, 84, 85), radius 120.0, position =
   caster position; `light_link`.
3. `handle_link(spell + 0xf8, caster, caster)`: a handle to the caster.
4. +0x18 = the caster's current scale (creature +0xdc) — the value restored at the end.
5. +0x2c = `particleGroup_create()`.
6. +0x1c target scale = ((float)getStat(0, level) * 0.01) + 1.0.
7. +0x20 = getStat(1, level) * 60 (integer frames); +0x24 end flag = 0.
8. +0x28 = `model_getSamplePointCount(caster model at +0x544)`.
9. 50 four-byte particle slots at +0x30 are zeroed, then for each: one private draw -> the
   16-bit angle, one private draw -> sample index = draw % count (100 private draws).
10. Cast sound at the caster's position.

**Run** — `SpellGiantGrowth_run` 0x309420. Observed.

```
if spell.ownerHandle (+0xf8) is empty:
    spell.endFlag = 1
else:
    P = the object behind the handle
    stepScale(spell, P)                    0x309524
    emitParticles(spell, P)                0x309678, presentation
    light position = P.pos + (0, 0, 50.0); light_relink
if spell.endFlag: destroy self (slot 1 with argument 3)
```

`stepScale` 0x309524 (proposed `SpellGiantGrowth_stepScale`), Observed:

```
s = P.scale (+0xdc)
if s == spell.target (+0x1c):                       exact float equality
    spell.frames (+0x20) -= 1
    if spell.frames < 30:  spell.target = spell.original (+0x18)
    if spell.frames < 0:   spell.endFlag (+0x24) = 1
else:
    d = +0.006 (0x3bc49ba5) if s < spell.target else -0.006
    s = s + d
    if d > 0 and s > spell.target: s = spell.target
    if d < 0 and s < spell.target: s = spell.target
    P.scale = s
    r = ((s - 1.0) * 3.0 + 7.0) * 12.0;  light radius = r, 1 / r^2      (presentation)
m = P.scale * 0.75
g_players[P.playerSlot (+0x3c8)] +0x4c20 = (m < 1.0) ? 1.0 : m
```

So, frame by frame (run call numbers, original scale 1.0, single precision):

| Rank | target | reaches target at call | last call at full size | back at 1.0 at call | last call (spell destroyed) | speed multiplier at full size |
|---|---|---|---|---|---|---|
| 1 | 1.50 | 84 | 355 | 439 | 469 | 1.125 |
| 2 | 1.53 | 89 | 420 | 509 | 539 | 1.1475 |
| 5 | 1.60 | 100 | 491 | 591 | 621 | 1.20 |
| 10 | 1.73 | 122 | 693 | 815 | 845 | 1.2975 |
| 15 | 1.85 | 142 | 833 | 975 | 1005 | 1.3875 |
| 20 | 1.98 | 164 | 1035 | 1199 | 1229 | 1.485 |

In general, with N = stat 1 * 60 and G = the number of 0.006 steps from the original scale
to the target: the counter only runs while the scale equals the current target, so the
caster is at full size for N - 28 calls (the call that reaches it plus the N - 29 that count
N-1 .. 29), then shrinks for G calls, then the counter runs 28 .. -1 for 30 more calls at the
original size. Total N + 2G + 1 calls.

**Every number the growth changes** (Observed unless marked):

1. **Scale**, creature +0xdc: written by `stepScale` each frame it moves, restored by the
   destructor. For a player this is the drawn size (and the size given to effects that read
   it, such as model sample points and the burn effect). The collision radius (+0x1c) and
   height are not touched by the spell.
2. **Movement speed**: player record +0x4c20 = max(1.0, scale * 0.75), rewritten on every run
   call (so about 1.0 until the scale passes 1.333, then rising to the table value).
   `player_speedScale` 0x1bea10 multiplies the base walking speed by this field
   (`docs/player.md`).
3. **Melee damage and attack rating**: `Player_recalcDamage` 0x1b7158, at 0x1b7a3c-0x1b7ac8:
   a multiplier f starts at 1.0; **only when the record's class field (+0x50) is 6 (shaman)
   and the player's action state (+0x58c) is 1 (melee swing)**, it looks for a
   `SpellGiantGrowth` on the record's player object and, if found, raises f to the owner's
   current scale (`SpellGiantGrowth_getOwnerField0dc` 0x3098c8; f = max(f, scale)). Then
   record +0xd0 (damage minimum), +0xd4 (damage maximum) and +0xcc (attack rating) are each
   replaced by trunc(value * f). During the grow and shrink phases the multiplier is the
   scale of that frame. Bows and thrown weapons (action state 0) get nothing; a character of
   another class holding the spell gets nothing.
4. **Hit points**: nothing. No function of the class writes the record hit points or maximum,
   and the spell's type is looked up only by canUse and `Player_recalcDamage` (reference
   search on the type-info getter 0x3d0da8). Observed by search.

**How it is undone.** `SpellGiantGrowth_dtor` 0x309368: if the owner handle is still set,
owner scale = +0x18 and the owner's record +0x4c20 = 1.0; then light, handle and base
clean-up. This runs at the natural end (when the scale is already back at the original) and
when the owner object is destroyed (`Creature_dtor` deletes attached spells before the
object's handles are cleared, so the handle is still valid then — Observed order in
0x117128). The damage multiplier needs no undoing: it exists only inside
`Player_recalcDamage` while the spell is attached.

**Interaction with skill 68.** `SpellResurrect` writes the same record field (+0x4c20 = 0.5
during its channel, 1.0 at its end). While a `SpellGiantGrowth` is attached its per-frame
write replaces the 0.5 on the next run call, so a giant caster is not slowed while raising a
player; and the Resurrect destructor's 1.0 is likewise overwritten. Conversely the Giant
Growth destructor's 1.0 cancels a Resurrect slow-down that is still running. Inferred from
the three stores (0x309668, 0x3093c4, 0x312a28).

**Stacking.** Prevented by canUse for the player path. Through any path that skips canUse a
second spell would capture the already enlarged scale as its "original".

**Non-player caster.** The cast function returns null before allocating, so the unguarded
uses of +0x3c8 in `stepScale` (0x309640) and in the destructor (0x3093a8) are only ever
reached with a player owner: the constructor has a single caller (0x308fec). Observed.

**Prediction copy.** Cannot cast. `Player_clone` copies +0xdc, so the copy has the current
scale; it has no attached spells.

##### SpellGiantGrowth layout (0x138 bytes)

| Offset | Type | Meaning | Evidence |
|---|---|---|---|
| +0x00 | s8 | level | ctor |
| +0x04 | handle | base back-list | ctor |
| +0x08 | Skill* | the skill | ctor |
| +0x0c | Creature* | owner = caster (read by 0x3098c8) | ctor |
| +0x10 | u32 | private generator state (particles only) | ctor |
| +0x14 | ptr | virtual table 0x51b6c0 | ctor |
| +0x18 | float | owner's scale at the cast | ctor 0x309220 |
| +0x1c | float | current target scale (grown value, later the original) | ctor 0x30928c, stepScale |
| +0x20 | s32 | frame counter, starts at stat 1 * 60 | ctor 0x3092a8 |
| +0x24 | s32 | end flag | ctor, stepScale, run |
| +0x28 | s32 | model sample point count | ctor |
| +0x2c | handle | particle group | ctor |
| +0x30 | 50 x {u8 age, u8 sample index, s16 angle} | particle slots | ctor, 0x309678 |
| +0xf8 | handle | the owner (run and destructor go through this) | ctor 0x309210 |
| +0xfc | light node (0x3c bytes) | +0x104, +0x105 u8 0; +0x106 s16[3] colour 200, 84, 85; +0x10c s16 0; +0x10e s16[3] same colour; +0x114 s16 0; +0x118 and +0x120 radius; +0x11c and +0x124 1 / radius^2; +0x128 0.0; +0x12c float[3] position | ctor, stepScale, run |

#### Random draws

- At the cast: shared, one draw (base `Spell` construction); then 100 private draws
  (`Spell_rand`) for the 50 particle slots (angle, sample index).
- Every run call, private generator only (0x309678): k slots are serviced, k = 47 while
  growing, 4 while holding at full size, 11 once the target has been set back to the
  original; each serviced slot draws once (`(draw & 3) + 41` is the age at which the slot
  restarts) and draws once more when it restarts (new sample index).
- No shared draw after the constructor, and no gameplay value comes from the private
  generator.

#### Presentation only

Cast sound; the light that follows the caster and grows with the scale; the particle group
and the particles of definition 0x8e73b8 (registered by `giantGrowth_staticInit` 0x3098d4)
emitted from model sample points by 0x309678; the rank text (0x309014 shows stat 0); icon
slot 7 (0x3d0d84).

#### Per-machine state

None found in the class: no camera, pad, local-slot, option or audio read, no cosmetic or
0x404468 generator. Two things outside it are worth recording:

- `Player_recalcDamage` finds the spell through the player object stored in the record
  (+0x43d8) and reads the scale from the spell's owner pointer. Whether that function also
  runs for the prediction copy, and what the record then holds, was not checked here; the
  copy itself has no spells, so a lookup on the copy would give no multiplier.
- The +0x3c8 uses without an is-player test (0x309640, 0x3093a8) are unreachable for a
  non-player, as shown above. `docs/skills.md` lists them as unguarded; the guard is one
  level up, in the cast function.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x308e64 | SkillGiantGrowth_ctor | skill object set-up |
| 0x308ed0 | SkillGiantGrowth_initStats | statistic tables |
| 0x308f2c | SkillGiantGrowth_canUse | no spell of this class attached |
| 0x308f60 | SkillGiantGrowth_cast | player-only; constructs the spell |
| 0x309014 | SkillGiantGrowth_describeRank | rank text |
| 0x30909c | SkillGiantGrowth_manaCost | slot 15 with (level, 10) |
| 0x3090d0 | SpellGiantGrowth_ctor | |
| 0x309368 | SpellGiantGrowth_dtor | restores scale and speed multiplier |
| 0x309420 | SpellGiantGrowth_run | |
| 0x309524 | SpellGiantGrowth_stepScale (proposed) | only caller 0x30945c |
| 0x309678 | SpellGiantGrowth_emitParticles (proposed) | only caller 0x30946c |
| 0x3098c8 | SpellGiantGrowth_getOwnerField0dc | returns the owner's scale; callers 0x1b7a70 |
| 0x3098d4 | giantGrowth_staticInit | one particle definition |
| 0x1b7158 (0x1b7970-0x1b7ac8) | Player_recalcDamage | the multiplier chain |
| 0x1bea10 | player_speedScale | reader of record +0x4c20 (first part) |
| 0x117128 | Creature_dtor | order of spell deletion |

#### Not determined

- When `Player_recalcDamage` is called relative to a swing (once per swing, every frame),
  and therefore which frame's scale a given hit uses.
- Whether the particle group taken in the constructor is ever released (the destructor does
  not release it; the pool has 16 groups).
- Other simulation readers of the player's scale were only screened by a field-offset
  search (`Creature_stepAnim` 0x1163bc scales root motion by it for creatures that use that
  function; `Player_animStep` does not).

### 66 planarwind — SkillPlanarWind

#### Identity

| Item | Value | Evidence |
|---|---|---|
| Skill id / internal name | 66, `planarwind` | Observed: name pointer stored by `SkillPlanarWind_ctor` 0x309978 |
| Skill class, virtual table | `SkillPlanarWind`, 0x51b7a8 | Observed 0x309978 |
| Skill object | 0x6e2f40 (pointer cell 0x41b278, used by Marr at 0x284264) | Observed |
| Kind (+0x08) | 0, ordinary active cast | Observed 0x309978 |
| Flags (+0x04) | 0: the prediction copy may not cast it | Observed 0x309978 |
| Recast (+0x0c) | 30 frames | Observed 0x309978 |
| Effect class | `SpellPlanarWind`, 0xac bytes, virtual table 0x51b778, constructor 0x309d0c, destructor 0x3d0e6c, run 0x30a0b0; draw and slot 4 are the base `Spell` ones | Observed 0x309acc, table 0x51b778 |
| Who has it | shaman tree (level 24, needs skill 80); the monster Marr casts it (0x284264) | §1.7; Observed call site |

The effect is a flat "front" that starts at the caster, travels straight ahead for at most 54
frames while slowing down, and strikes every enemy that was inside a corridor in front of the
caster at the moment of the cast, once, when the front passes that enemy's centre.

#### Statistics

Set by `SkillPlanarWind_initStats` 0x3099e4 (Observed; every store read).

| Stat | Meaning (how known) | Tier 1: first, base, step | Tier 2: first, base, step |
|---|---|---|---|
| 0 | centre of the damage range (Observed: run 0x30a1e0 / 0x30a220) | 1, 200, 10.001777 (0x41200747) | 1, 40, 10.0 (0x41200000) |
| 1 | half-width of the corridor in world units (Observed: ctor 0x309ef8 stores it at +0x30, used as the `halfWidth` argument at 0x30a034); also sizes the light and the particle count | 1, 40, 3.5409288 (0x40629e94) | 1, 40, 3.0 (0x40400000) |
| 2 | starting speed of the front in world units per second (Observed: ctor 0x309e80 -> +0x34, run 0x30a0f8) | 1, 631, 35.0305 (0x420c1f3b) | 1, 631, 35.0 (0x420c0000) |
| 3 | percent chance that a struck target is also set burning (Observed: ctor 0x30a010 -> +0x60, run 0x30a344) | 10, 20, 1.9999869 (0x3fffff92) | 10, 20, 2.0 (0x40000000) |
| 4 | mana cost (Observed: slot 15 through `SkillPlanarWind_manaCost` 0x309cd8) | 1, 75, 3.000978 (0x40401006) | none (first level 0xffff, left by the constructor) |

Which accessor each use applies:

- Stats 1, 2 and 3 are read once, in the constructor, through slot 12
  `getStatFor(stat, level, caster, cap = 10)`. A player caster gets the tier-1 value at the
  full level (the cap is ignored on that path); any other caster gets the tier-2 value with
  the level limited to 10.
- Stat 0 is read each time a target is struck (in the run function, not at cast time).
  Player owner: slot 8 `getStatRange(spread = 0.19999999 (0x3e4ccccc), stat 0, level,
  randomise = 0, &lo, &hi)`, which gives lo = round(v - v*spread), hi = round(v + v*spread),
  each at least 1, with no generator draw. Any other owner (or a null owner): slot 12
  `getStatFor(0, level, owner, cap = 0)` (tier 2, level not limited), then
  lo = trunc(v - v*0.19999999), hi = trunc(v + v*0.19999999) in single precision
  (truncation, not rounding; no floor of 1).

Worked values (computed in single precision from the constants above):

| Caster | Level | stat 0 | lo..hi | stat 1 | stat 2 | stat 3 | stat 4 |
|---|---|---|---|---|---|---|---|
| player | 1 | 200 | 160..240 | 40 | 631 | 0 | 75 |
| player | 10 | 290 | 232..348 | 72 | 946 | 20 | 102 |
| player | 20 | 390 | 312..468 | 107 | 1297 | 40 | 132 |
| monster | 1 | 40 | 32..48 | 40 | 631 | 0 | - |
| monster | 5 | 80 | 64..96 | 52 | 771 | 0 | - |
| monster | 10 | 130 | 104..156 | 67 | 946 | 20 | - |
| monster | 20 | 230 | 184..276 | 67 (capped) | 946 (capped) | 20 (capped) | - |

Stat 3 is 0 below level 10 in both tiers (first level 10).

#### Cost and limits

- Mana: `SkillPlanarWind_manaCost` 0x309cd8 calls slot 15 with (level, 20), which is
  (float) slot10(4, slot14(level, 20)); slot 14 is the base one that returns the level
  unchanged. Cost = round(75 + 3.000978 * (rank - 1)): 75 at rank 1, 102 at rank 10, 132 at
  rank 20. Observed.
- Recast 30 frames (player +0x4ae, written by `Player_castSkill`).
- canUse is the base function 0x3c8218 (always allowed). No weapon, animation or state gate
  exists in the Skill or Spell code. Observed (virtual table 0x51b7a8 slot 1).
- The prediction copy cannot cast it: skill flag bit 0 is clear, so `Player_castSkill`
  0x1a42b8 returns before calling canUse or cast. Observed.
- A monster caster pays nothing and has no recast (general monster path).

#### Behaviour

**Cast** — `SkillPlanarWind_cast` 0x309acc (skill, level, caster, pos*, facing). Observed.

1. Copies the 12-byte position.
2. level = slot 14 `adjustLevel(level, 20)` (unchanged in this build).
3. Allocates 0xac bytes with `pool_new`; when that succeeds calls
   `SpellPlanarWind_ctor(spell, level, caster, skill, &posCopy)`.
4. Returns the spell (or null). **The facing argument is never read**: the direction comes
   from the caster's own facing field, so the aim-assist facing that `Player_castSkill`
   computes has no effect on this skill.

The caller attaches the spell to the caster (`creature_addSpell`): `Player_castSkill` for a
player, Marr's run function for Marr. The caster pointer is dereferenced without a null test
in the constructor.

**When the spell runs.** Observed (decompiled form of the three functions, and the
disassembly at 0x1ac68c-0x1ac6a8):

- *Non-player owner (Marr)*: `Creature_run` 0x112948 calls the owner's slot 17
  (`Creature_updateSpells` 0x11a868) at its very top, only for objects without flag 0x40,
  with the position (x, y, height + height extent * 0.5). Marr's run 0x283afc calls
  `Creature_run` before its state machine reaches the cast, so the constructor runs in the
  cast frame and **run call 1 comes in the following frame**.
- *Player owner*: `Creature_run` does not run a player's spells. `Player_run` 0x1a5030 runs
  them through `Player_updateCast` 0x1a3f70, called at 0x1ac6a8 after `Creature_run`,
  `Player_processDamage` and the action-state switch (which is where `Player_castSkill` is
  reached), and only when the record's hit points (+0xac) are above 0.0. So **run call 1 is
  made in the cast frame itself**, at the end of that `Player_run`, and each later call
  comes at the same point of the following frames. The position handed over (the hand
  midpoint) is not used by this spell.
- Slot 17 walks the attached list from its head, i.e. the most recently attached spell
  first (`creature_addSpell` 0x11a838 links at the head through `handle_link`; that the
  iterator starts at the head is taken from its use, the iterator itself was not re-read).

**Constructor** — `SpellPlanarWind_ctor` 0x309d0c. Observed. In execution order:

1. Base `Spell` part: level byte, back-list 0, skill, owner = caster, **one shared draw**
   whose 16-bit value becomes the private generator state (+0x10), virtual table.
2. Target list head (+0x6c) = 0. Embedded light node at +0x70 filled in (see the layout);
   its position (+0xa0) = the caster's position; `light_link` 0x148af8.
3. +0x34 speed = (float) getStatFor(2, level, caster, 10).
4. Direction: +0x24 = `math_cos16(caster facing)`, +0x28 = `math_sin16(caster facing)`,
   +0x2c = 0.0. The facing is the signed 16-bit field at caster +0x38.
5. Position: +0x18, +0x1c = cast position x, y; +0x20 = cast position height + 12.0
   (0x41400000).
6. +0x30 half-width w = (float) getStatFor(1, level, caster, 10).
7. Light radius r = min(300.0, max(60.0, w * 1.5)), stored at +0x8c and +0x94;
   1 / (r * r) stored at +0x90 and +0x98. (Presentation.)
8. +0x5c particle count = trunc(((w * 3.570941 (0x40648a4c)) * 0.0069444436 (0x3be38e37)) * w):
   39 at w = 40, 128 at w = 72, 283 at w = 107. (Presentation, but it sets how many private
   draws the spell makes per frame.)
9. Plays the cast sound at the cast position (`sound_playAtPos`).
10. +0x38 = 3x3 rotation about the vertical axis by (caster facing + 0x4000)
    (`mat3_setRotZ`); used only to scatter particles.
11. +0x64 knock-back flag chosen by level: level < 6 -> 0x80000; 6..10 -> 0x100000;
    level >= 11 -> 0x200000.
12. +0x60 burn chance = getStatFor(3, level, caster, 10) (integer percent); +0x68 frame
    counter = 0.
13. **Target gathering, once only**: `world_collectObjectsInArc(radius = 960.0 (0x44700000),
    arcDegrees = -1.0 (no wedge test), halfWidth = w, pos = the cast position as passed
    (without the +12), facing16 = caster facing, &tempList, filterObj = caster)`. So a target
    is taken when it is a creature, has none of the object flags 0x1 / 0x4 / 0x8, the
    caster's slot 20 calls it an enemy, it lies inside the box of +-960 around the cast
    position on all three axes, its sideways offset from the caster's facing line is at most
    w, and its centre is strictly in front of the cast position.
14. Each object of the temporary list, walked head to tail, is linked into +0x6c with
    `handle_link(spell + 0x6c, obj, obj)`. `handle_link` inserts at the head, so **the
    spell's list is the temporary list reversed**. The temporary list is then cleared.

Because the links are handles, a target that is destroyed before the front reaches it drops
out of the list by itself (Inferred from `handle_clear` removing both partner nodes; the
object-destruction side was not re-read here). A target that merely dies stays in the list:
nothing is re-tested at strike time.

**Run** — `SpellPlanarWind_run` 0x30a0b0, once per simulated frame while attached. Observed.
The position and facing arguments passed by the owner are not used.

```
step  = ((dir * speed) * 0.016666666)            per component; 0x3c888888
pos  += step
for node in list(+0x6c), head to tail (the next pointer is read before the body):
    t = node.object;  if t == null: continue
    if dot(dir, t.pos - pos) >= 0: continue      vec3_dotDelta 0x1667d8, all three axes
                                                 (dir has no vertical part)
    -- the front has passed t's centre: strike it --
    if owner != null and (owner.flags & 0x40):   player
        (lo, hi) = getStatRange(0.19999999, 0, level, 0)
    else:
        v  = (float) getStatFor(0, level, owner, 0)
        lo = trunc(v - v * 0.19999999);  hi = trunc(v + v * 0.19999999)
    flags = spell.knockFlag(+0x64) | 0x40
    if g_pvpModeA != 0 and (t.flags & 0x40):
        r = shared draw
        if r % 100 >= 21: flags = 0x40           knock-back bits kept only 21 times in 100
    damage_apply(min = lo, max = hi, victim = t, attacker = owner, attackRating = 100000,
                 0, 0, flags, desc = null, noCrit = 1)
    r = shared draw                               always, whatever damage_apply returned
    if (int)(r % 100) < spell.burnChance(+0x60):
        Creature_setEffectTimer(2.0, t, which = 0, source = owner)
    hit sound at t.pos; if t's model (GameObject slot 16) is non-null:
        72 times: one private draw (Spell_rand) -> a model sample point -> one particle
    handle_removeNode(node)                       each target is struck at most once
light position (+0xa0) = pos - dir * 60.0;  light_relink
speed = speed - ((speed * 0.016 (0x3c83126e)) * 0.99999994 (0x3f7fffff))
particle loop: count(+0x5c) times, six private draws each (see Random draws)
h   = terrain_height(8.0, g_world, &pos)
old = counter(+0x68);  counter = old + 1
if old >= 53 or pos.height < h:  destroy self (Spell slot 1 with argument 3)
```

Consequences worth stating outright:

- **Duration**: the run function executes at most 54 times; the 54th execution destroys the
  spell. It ends earlier in the first frame in which the terrain under the front (highest
  sample under a disc of radius 8) is higher than the front's fixed height (cast height + 12).
  The strike loop of that last frame has already run. For a player caster the 54 calls fall
  in the cast frame and the 53 after it; for Marr in the 54 frames after the cast. While a
  player caster's hit points are <= 0 the spell is not run: the front stops, strikes nothing
  and its frame counter does not advance; it is deleted with the player object.
- **Speed and reach**: speed starts at stat 2 and is multiplied each frame by a factor just
  under 0.984. Total travel over 54 frames, computed in single precision: 382.19 units at
  stat 2 = 631, 572.98 at 946, 785.58 at 1297. Targets gathered at the cast but farther
  ahead than the front gets are never struck.
- **Hit test**: only "the plane through the front, perpendicular to the direction, has
  passed the target's centre". No distance, sideways or height test is repeated; the corridor
  test was done once at the cast position. A target that walks sideways out of the corridor
  after the cast is still struck; one that walks in is not.
- **Order of strikes inside one frame**: list order, i.e. the reverse of the order in which
  `world_collectObjectsInArc` produced the temporary list (whose head is the nearest target
  and whose remainder is only partly ordered by distance). The order matters because every
  strike draws from the shared generator.
- **Damage**: an un-typed hit (no damage-class bits, no descriptor), attack rating 100000,
  flag 0x40 (cannot be blocked, ignores Spirit Shield), critical hits suppressed (noCrit 1).
  The bits 0x80000 / 0x100000 / 0x200000 are not interpreted by `damage_apply`; they reach
  the victim's take-damage and select the knock-back speed of a killing blow (150 / 200 /
  312.5 per `docs/creatures.md`, not re-read here).
- **Burn**: `Creature_setEffectTimer` 0x118950 with index 0 writes 2.0 into the target's burn
  timer (+0x340), clears the target's effect-source handle (+0x360) and links it to the
  owner. It overwrites any burn already running (refresh to 2.0, never added). The timer
  loses 1/60 per `Creature_run` and is positive for 121 runs (computed in single precision
  from 2.0 and 0x3c888888); while positive the burn tick fires on frames where
  `g_simFrame & 31 == 0` (`Creature_run` 0x1132f8 onward; see `docs/creatures.md`). What
  a tick does, as read there (decompiled form): it is skipped for the prediction copy;
  otherwise `damage_apply(0.0, 0.0, victim = the creature, attacker = the creature itself,
  100000, 0, 0, flags = 0x1180c040, &desc, noCrit = 0)` with a one-entry descriptor of type
  0x15 (fire): for a non-player v1 = 1, v2 = 1 and no draw; for a player one shared draw r,
  f = 0.15 * (tier-2 stat 0 of skill 13 `fireweapons` at level trunc(`g_levelMonsterLevel`),
  slot 11 with cap 0), v1 = trunc(f), v2 = trunc(f + f * 0.2 * r / 65536). Flag 0x10000000
  stops the tick from renewing the burn; the source handle stored by
  `Creature_setEffectTimer` is what the victim's take-damage credits for such hits
  (`docs/creatures.md`, +0x360).
- **Stacking**: nothing looks for an existing `SpellPlanarWind`. A second cast while the
  first is still travelling creates an independent front with its own target list; a target
  in both lists is struck by each.

**Destructor** — 0x3d0e6c: `light_dtor(spell + 0x70, 2)`, clears the target list, clears the
base back-list, frees the block when bit 0 of the argument is set. Observed.

**Non-player caster.** Marr (run function 0x283afc, AI state 9, on animation event bit 0,
call at 0x284264) casts with level = Creature slot 35 = trunc(`g_levelMonsterLevel` *
0.29999998), pos = Marr's own position (the feet, object +0x10), facing = own facing, then
`creature_addSpell(Marr, spell)` and zeroes his counter at +0x460. Everything above applies
with the tier-2 numbers: stats 1 to 3 at min(level, 10), stat 0 at the uncapped level with
truncation. Nothing in the three functions reads the player slot (+0x3c8). Observed.

**Weapon-effect cast** (damage descriptor type 0x29, any creature as caster): the
constructor runs in full (shared draw, light linked, sound, target list built) but the
returned spell is not attached, so its run function is never called: no movement, no damage,
and the 0xac-byte block, its handles and its light are never released. Inferred from the
caller described in `docs/skills.md` plus the fact that only the owner's slot 17 calls run;
whether any item carries skill 66 is Unknown.

**Prediction copy.** Cannot cast (above). As a target it is never gathered
(`world_collectObjectsInArc` skips it). As an attacker `damage_apply` would return at once.

##### SpellPlanarWind layout (0xac bytes)

| Offset | Type | Meaning | Evidence |
|---|---|---|---|
| +0x00 | s8 | level | ctor |
| +0x04 | handle | base back-list | ctor |
| +0x08 | Skill* | the skill (0x6e2f40) | ctor |
| +0x0c | Creature* | owner = caster, also the attacker of every strike | ctor, run |
| +0x10 | u32 | private generator state | ctor |
| +0x14 | ptr | virtual table 0x51b778 | ctor |
| +0x18 | float[3] | position of the front (x, y, height) | ctor, run |
| +0x24 | float[3] | unit direction (cos, sin, 0) | ctor |
| +0x30 | float | corridor half-width (stat 1) | ctor |
| +0x34 | float | current speed, units per second (stat 2 at the start) | ctor, run |
| +0x38 | float[9] | rotation matrix for particle scatter | ctor 0x309fb4, run 0x30a590 |
| +0x5c | s32 | particles per frame | ctor 0x309f80 |
| +0x60 | s32 | burn chance, percent (stat 3) | ctor 0x30a024 |
| +0x64 | u32 | knock-back flag for the damage call | ctor 0x309fe4 |
| +0x68 | s32 | frames run so far | ctor, run 0x30a784 |
| +0x6c | handle list | targets not yet struck | ctor, run |
| +0x70 | light node (0x3c bytes) | +0x78, +0x79 u8 0; +0x7a s16[3] colour 155, 76, 418; +0x80 s16 0; +0x82 s16[3] the same colour; +0x88 s16 0; +0x8c and +0x94 radius; +0x90 and +0x98 1 / radius^2 (first written as 0.0069444445 (0x3be38e38) with radius 12.0, then overwritten in step 7); +0x9c 0.0; +0xa0 float[3] light position | ctor 0x309e04-0x309e58 |

#### Random draws

In execution order.

At the cast:

1. Shared generator, one draw: the base `Spell` construction (value -> +0x10).

Each frame, for each target struck that frame, in list order:

2. Shared, one draw — only when `g_pvpModeA` is non-zero and the target is a player: keeps
   or drops the knock-back flag.
3. Shared, whatever `damage_apply` draws for these arguments (`docs/gameplay.md` section 2.5:
   the base roll when lo < hi, the first hit roll, the four "chance" procs, the second hit
   roll, and so on; no critical roll because noCrit is 1; thorns and undead shields are not
   armed because no damage-class bit is set).
4. Shared, one draw: burn chance (`r % 100 < stat 3`). Drawn even when stat 3 is 0.
5. Private (`Spell_rand`), 72 draws when the target has a model: each picks a model sample
   point (`draw % sample point count`) for one hit particle.

Each frame, after the strike loop, `count` (+0x5c) times, private generator, six draws each:

6. a rotation angle (low 16 bits) for the scatter matrix;
7. a distance fraction (draw / 65536 * half-width);
8. 9. 10. three velocity perturbations ((draw / 65536 - 0.5) * 0.5 each; they accumulate on
   the frame's step vector from one particle to the next);
11. particle type: `draw & mask == 0` picks the first particle definition, otherwise the
    second; mask = 0x7f at level 1, 0x3f at levels 2..4, 0x1f at 5..9, 0x0f at 10 and above.

The private generator feeds particles only; no gameplay value in this class comes from it.

#### Presentation only

Cast and hit sounds (`sound_playAtPos`), the travelling light (embedded node, trails 60
units behind the front), three particle definitions built by `planarWind_staticInit`
0x30a7f4 (0x8e7408, 0x8e7458 for the stream, 0x8e74a8 for hits), the scatter matrix, the
rank text (`SkillPlanarWind_describeRank` 0x309b70: damage range from stat 0 with the 0.2
spread, stat 1 divided by 12 as a width, stat 3 when non-zero), the icon (slot 7, 0x3d0e48).

#### Per-machine state

None found. The three functions read no camera, pad, local-slot, option or audio state, do
not call `net_isLocalSlot` / `net_objOrGhost`, do not use the cosmetic generator or 0x404468,
and never read +0x3c8. The only owner test is the is-player flag that selects the statistic
tier. The number of private draws per frame depends only on the level, stat 1 and on whether
a struck target has a model.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x309978 | SkillPlanarWind_ctor | skill object set-up (name, kind 0, recast 30, flags 0) |
| 0x3099e4 | SkillPlanarWind_initStats | statistic tables |
| 0x309acc | SkillPlanarWind_cast | allocates and constructs the spell |
| 0x309b70 | SkillPlanarWind_describeRank | rank text |
| 0x309cd8 | SkillPlanarWind_manaCost | slot 15 with (level, 20) |
| 0x309d0c | SpellPlanarWind_ctor | all initial state and the one-time target query |
| 0x30a0b0 | SpellPlanarWind_run | movement, strikes, decay, end test |
| 0x30a7f4 | planarWind_staticInit | three particle definitions |
| 0x3d0e6c | SpellPlanarWind_dtor | light, list and base clean-up |
| 0x283afc (0x284264) | Marr run | the monster call site |
| 0x1667d8, 0x1a1738, 0x1a1868, 0x118950, 0x118c50, 0x3c82e4, 0x1a42b8 | vec3_dotDelta, handle_link, handle_removeNode, Creature_setEffectTimer, Creature slot 35, getStatRange, Player_castSkill | helpers, read for their semantics |

#### Not determined

- Whether any item carries a type-0x29 entry for skill 66.
- `world_collectObjectsInArc`, the take-damage use of the knock-back bits and the burn tick
  were taken from §1.6 and the area documents; only the burn timer countdown and the
  tick gate were re-read (0x1132f8-0x113534).
- What happens to the strike loop if a strike destroys another listed object in the same
  frame (the next-node pointer is fetched before the strike); no such immediate destruction
  path was looked for.

### 67 shadowstep — SkillShadowStep

#### Identity

| Item | Value | Evidence |
|---|---|---|
| Skill id / internal name | 67, `shadowstep` | Observed: `SkillShadowStep_ctor` 0x31127c |
| Skill class, virtual table | `SkillShadowStep`, 0x51bd78 | Observed 0x31127c |
| Skill object | 0x6e2fa8 | `tools/dump_tables.py --table skills` |
| Kind (+0x08) | 0, ordinary active cast | Observed 0x31127c |
| Flags (+0x04) | 0: the prediction copy may not cast it | Observed 0x31127c |
| Recast (+0x0c) | 30 frames | Observed 0x31127c |
| Effect classes | `SpellShadowStep`, 0x34 bytes, virtual table 0x51bd48, constructor 0x311638, destructor 0x311da0, run 0x311e3c (draw and slot 4 are the base ones). From rank 5 it also creates `StaticFire` objects (GameObject, 0x4ac bytes, virtual table 0x50da38, constructor 0x2c5240); at ranks 1 to 5 one `LightEffect` (0xbc bytes, constructor 0x201bd8) | Observed 0x311340, 0x31188c, 0x3119c8, 0x311cac |
| Who has it | shadowknight tree (level 12, passive mask 0x40). No monster call site is known | §1.7 |

What it is: not a teleport. The caster becomes non-solid and hidden, is moved straight
ahead by the collision mover for 25 frames (about 154 units when nothing stops it), and is
turned to face the opposite way half-way through. At the moment of the cast, nearby enemies
that were targeting the caster lose their target for a while; from rank 5 a fire is left at
the starting point, from rank 6 a ring of further fires as well, and those enemies are given
a knock-back impulse directed at the starting point.

#### Statistics

Set by `SkillShadowStep_initStats` 0x3112e8 (Observed). Stats 2 and 3 are never written
(tier-1 first level, base and step stay 0) and never read. There are no tier-2 tables
(all five first levels stay 0xffff).

| Stat | Meaning (how known) | Tier 1: first, base, step | Tier 2 |
|---|---|---|---|
| 0 | length in frames of the "no target" time given to affected enemies (Observed: ctor 0x311850 -> argument of Creature slot 31 at 0x311a90; the rank text shows it as seconds, stat / 60) | 1, 60, 20.003422 (0x41a00702) | none |
| 1 | number of fires: 0 none, 1 one at the start point, n >= 2 adds n - 1 in a ring and switches the knock-back on (Observed: ctor 0x311878-0x311a04, 0x311ab0) | 5, 1, 0.501 (0x3f004189) | none |
| 4 | mana cost (Observed: slot 15 via 0x311604) | 1, 64, 5.0 (0x40a00000) | none |

Both gameplay stats are read with slot 10 `getStat(stat, level)` (tier 1 for every caster,
no cap, no is-player test).

| Rank | stat 0 (frames) | stat 1 (fires) | stat 4 (mana) |
|---|---|---|---|
| 1 | 60 | 0 | 64 |
| 4 | 120 | 0 | 79 |
| 5 | 140 | 1 | 84 |
| 6 | 160 | 2 | 89 |
| 8 | 200 | 3 | 99 |
| 10 | 240 | 4 | 109 |
| 12 | 280 | 5 | 119 |
| 14 | 320 | 6 | 129 |
| 16 | 360 | 7 | 139 |
| 18 | 400 | 8 | 149 |
| 20 | 440 | 9 | 159 |

(stat 1 by rank, 5 to 20: 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9.)

#### Cost and limits

- Mana: `SkillShadowStep_manaCost` 0x311604 = slot 15 with (level, 20) = round(64 + 5 *
  (rank - 1)): 64, 109, 159 at ranks 1, 10, 20. Observed.
- Recast 30 frames. The step itself lasts 25 run calls, and during it the player is in action
  state 0xe, which `Player_run` does not handle (`docs/player.md`), so no other action can
  start until the spell's destructor puts the state back to 2.
- canUse: base function 0x3c8218 (always allowed). Observed (virtual table slot 1).
- Prediction copy: cannot cast (flag bit 0 clear; `Player_castSkill` returns first).

#### Behaviour

**Cast** — `SkillShadowStep_cast` 0x311340 (skill, level, caster, pos*, facing). Observed.
level = slot 14 `adjustLevel(level, 20)` (unchanged); `pool_new(0x34)`; when that succeeds
`SpellShadowStep_ctor(spell, level, caster, skill)`. The position and facing arguments are
not used at all: everything is taken from the caster object. Returns the spell or null.

**Constructor** — `SpellShadowStep_ctor` 0x311638. Observed. In execution order:

1. Base `Spell` part: level, back-list 0, skill, owner = caster, **one shared draw** for the
   private generator (+0x10), virtual table 0x51bd48.
2. +0x1c = 370.0 (0x43b90000), +0x18 progress t = 0.0.
3. +0x20 = `math_cos16(caster facing)`, +0x24 = `math_sin16(caster facing)`, +0x28 = 0.0.
4. Writes on the caster: **+0x58c = 0xe** (action state), **object flags (+0x0c) |= 0x5**
   (0x1 not solid; 0x4 excluded from sphere and arc queries together with 0x1 and 0x8).
   Spell +0x30 = caster facing - 0x8000 (16-bit, i.e. the opposite direction);
   +0x2c = caster.
5. The vector at +0x20 is normalised (multiplied by 1 / sqrt(x*x + y*y + z*z)) and then
   multiplied by +0x1c: it becomes a velocity of length 370 units per second along the
   caster's facing.
6. Cast sound at the caster's position.
7. Box corners: caster position -+ (97.0, 97.0, 1000.0).
8. s0 = getStat(0, level); s1 = getStat(1, level).
9. If s1 != 0 (rank >= 5): `pool_new(0x4ac)`; when it succeeds,
   `StaticFire_ctor(120.0, 1.0, obj, &casterPos, life = 360, owner = caster, secondary = 0)`
   — the **centre fire**. Then n = s1 - 1, and if n != 0 (rank >= 6):

   ```
   step  = 0xffff / n                       integer division
   angle = caster facing (signed 16-bit, accumulated in 32 bits)
   repeat n times:
       p.x = caster.x + math_sin16(angle) * 75.0
       p.y = caster.y + math_cos16(angle) * 75.0
       angle += step
       p.z = terrain_heightAtPoint(g_world, &p)
       if |owner.z - p.z| <= 72.0:           compared in double precision
           obj = pool_new(0x4ac)
           if obj: StaticFire_ctor(120.0, 1.0, obj, &p, life = 240, owner = caster,
                                   secondary = 1)
   ```
   If s1 == 0, n is taken as 0.
10. `world_collectObjectsInBox(&min, &max, list, 0x40)` (at most 63 objects; the prediction
    copy and `g_excludeMask` objects are never returned). For each object o in list order,
    all of these must hold:
    - o has object flag 0x20 (creature);
    - the caster's slot 20 (is-enemy) returns non-zero for o;
    - o's target handle (+0x234) is non-null and the object behind it is the caster.

    Then: **o's Creature slot 31 is called with s0** (start the no-target timer). The base
    implementation 0x118af8 does this only when `g_pvpModeA` is 0 and `creature_bossRank(o)`
    is 0: o +0x316 = s0 (stored as 16 bits) and o's target handle is cleared.
    After that call, **only when n != 0** (rank >= 6): o +0x2e8 (knock-back speed) = 151.0
    (0x43170000) and o +0x2e0 (knock-back angle) = `math_atan2_16(o.y - caster.y,
    o.x - caster.x)` - 0x8000. These two writes do not depend on what slot 31 did.
    Since `Creature_applyKnockback` 0x115eb8 moves a creature along (cos, sin) of +0x2e0, the
    impulse points from the creature **toward** the caster's position at the cast: the
    ordinary hit path (0x116638) stores the angle of the vector attacker -> victim there,
    and this code stores the angle of caster -> creature turned by half a circle. (Inferred
    from the angle conventions of the three functions; not checked in the running game.) The
    impulse is
    consumed by the creature's own run code (speed falls by 2 per `Creature_applyKnockback`
    call; a player target gets none in a net game or in `g_pvpModeB`).
11. 86 particles on the caster's model (private generator, see Random draws).
12. Only when n == 0 (ranks 1 to 5): `pool_new(0xbc)` and, when it succeeds, a `LightEffect`
    at the caster's position + (0, 0, 36): start colour (128, 79, 53, -96), end colour
    (0, 0, 0, 0), radius 120 growing to 180, 1.0 second, no owner. Presentation, but a
    GameObject construction (one shared draw).

Nothing in the constructor looks for an existing `SpellShadowStep` on the caster, tests
whether the caster is a player, or tests the prediction flag.

**The fires** (class `StaticFire`, belongs to the StaticFire source file; read here once, in
decompiled form only, as far as this skill uses it). `StaticFire_ctor` 0x2c5240
(f12 = 120.0 -> +0x50; f13 = 1.0 multiplies +0x68; a2 = life in frames -> +0x7c;
a3 = owner, stored as a **raw pointer** at +0x4a8; t0 = "secondary"):

- `GameObject_ctor` (one shared draw seeds the object's own generator), then
  `StaticFire_initCommon` 0x2c5814: radius (+0x1c) 16.0, object flags |= 0x40001 (not
  solid), intensity (+0x64) 1.0, one draw from the object's own generator for a phase value
  (+0x4c = draw % 300), the object is put on the run-every-frame and always-draw lists.
- +0x6e = 1 (this fire deals damage). A secondary fire unlinks its own light; a primary one
  unlinks the lights of other `StaticFire` objects whose bodies overlap a box of -+30 around
  it.
- It counts the objects other than itself returned by a box query of -+30 on all three axes
  around its position (limit 127); **when more than 3 are found its life is halved**
  (360 -> 180, 240 -> 120). The centre fire's box normally contains the caster.
- Each frame (`StaticFire_run` 0x2c595c): life -= 1; intensity rises by 1/60 per frame up
  to 1.0 while life >= 120 and falls by 1/120 per frame below that; at life 0 the fire stops
  and deletes itself once its remaining particles are gone.
- Damage, only while life != 0 and `isNearView(941.0 (0x446b4000), pos)` is true, on frames
  where `g_simFrame % 12 == 0`: box query of -+(16.0 * intensity) on all three axes (limit
  63); for each object other than the fire that does not have flag 0x1, a damage descriptor
  with one entry is built: type 0x15 (fire); for a non-player victim v1 = 1, v2 = 1; for a
  player victim f = max(1.0, 0.15 * stat) where stat = slot 11 `getStatTier2(0,
  trunc(g_levelMonsterLevel), 0)` of skill 13 `fireweapons` (table cell 0x41b1a4), **one shared
  draw** r, v1 = trunc(f), v2 = trunc(f + f * 0.2 * r / 65536). Then, the owner being a
  creature here: if owner's slot 20 accepts the victim,
  `damage_apply(0.0, 0.0, victim, attacker = owner, 100000, 0, 0, flags = 0x100c040,
  &desc, noCrit = 0)`. (With a null or non-creature owner the fire itself is the attacker and
  every creature in the box is hit.) Flags: 0x40 unblockable, 0x4000 and 0x8000 no hit or
  miss sound, 0x1000000 no floating number. The 0x15 entry adds 1 to 1 fire damage (reduced
  by fire resistance) and sets the burn status, per `docs/gameplay.md` section 2.2.

So for this skill each fire damages only what the caster's is-enemy test accepts, every 12th
frame, for at most 360 (centre) or 240 (ring) frames.

**Run** — `SpellShadowStep_run` 0x311e3c, once per simulated frame. Observed. C is the
creature at +0x2c (the caster).

```
s   = (t - 0.5) + (t - 0.5)                      t = +0x18 before this frame's increment
v   = copy of the velocity (+0x20, three floats)
if g_networkMode == 0:
    Player_clampToScreen(C, &v, &mask)           may shorten or zero v, see below
v   = v * 0.5                                     each component
C.scale(+0xdc) = (s * s) * s
obj_moveWithCollision(C, &v, ignoreObj = 0, ignoreCreatures = 1)
obj_moveWithCollision(C, &v, 0, 1)                the same call a second time
g_forceGhostRebase (0x402797) = 1
if C.scale < 0.5:  C.creatureFlags(+0xa8) |= 0x200000      model not drawn
t  += 0.04088309 (0x3d277507)
if t > 0.5:  owner.facing(+0x38) = spell.endFacing(+0x30)
if t > 1.0:  destroy self (Spell slot 1 with argument 3)
```

- **Length**: computed in single precision, t exceeds 1.0 on the 25th call, so the run
  function executes exactly 25 times and the destructor runs at the end of the 25th.
  A player's spells are run by `Player_updateCast` 0x1a3f70, which `Player_run` calls at
  0x1ac6a8 after `Creature_run`, `Player_processDamage` and the action-state switch, and
  only while the record's hit points are above 0.0 (`Creature_run` runs spells only for
  non-players). The cast is made inside the state switch, so **call 1 happens in the cast
  frame F itself**: the caster is moved at the end of `Player_run` in frames F .. F+24, the
  destructor runs at the end of frame F+24, and the first state switch that sees action
  state 2 again is that of frame F+25. In frames F+1 .. F+24 the frame's damage processing
  and the (empty) state-0xe case come before the move. `Player_updateCast` itself changes
  the action state only from 5 to 2, so it leaves 0xe alone. Observed.
- **Movement**: `obj_moveWithCollision` treats its vector as units per second and moves by
  vector / 60 per call, so each frame moves the caster twice by 185 / 60 = 3.083 units:
  6.167 units per frame, 154.17 units over 25 frames when nothing blocks. Because of
  ignoreCreatures = 1 the mover skips every object with flag 0x20 (no push-out and no touch
  callbacks for creatures); walls, terrain and non-creature solid objects still stop or
  deflect it, and each call also applies the mover's gravity and ground snap
  (`docs/objects.md`). No destination is chosen in advance and nothing checks where the
  caster ends up.
- **Offline branch** (`g_networkMode` == 0): `Player_clampToScreen` 0x1b3d90 converts the
  full velocity to a per-frame move, rebuilds the four side planes of the view from camera
  data (0x1e71b0 reading 0x44f038 and 0x44f0a8), and if the caster is already outside any
  plane and the move goes further outward it removes the outward component (a second
  offending plane zeroes the move); the corrected velocity is written back. So offline the
  step cannot carry the caster further off screen. **Net branch**: the call is skipped and
  the velocity is used as it is. Every machine of a net game takes the same branch.
- **Scale and visibility**: the first frame writes scale -1.0 and sets creature flag
  0x200000 (model not drawn); nothing in the run function clears the flag again, so the
  model stays hidden for the whole step. The scale written per frame runs -1.0, -0.774,
  -0.585, ... , about 0 at frames 13 and 14, ... , 0.510 (frame 23), 0.683, 0.891 (frame
  25). The destructor restores 1.0. Whether simulation code reads +0xdc during those frames
  was not checked.
- **Facing**: from the 13th call on (t = 0.5315 after the increment) the owner's facing is
  set every frame to the reversed facing captured at the cast.
- **`g_forceGhostRebase`** is set every frame so that the prediction copy is rebuilt from
  the moved player (purpose Inferred; the reader of 0x402797 is in the netcode).

**Destructor** — `SpellShadowStep_dtor` 0x311da0. Observed. On the creature at +0x2c:
scale = 1.0; object flags &= ~0x5; +0x58c = 2 (neutral); creature flags &= ~0x200000. Then
the base clean-up and the optional free. Both flag bits and the state are cleared
unconditionally: if the caster already had flag 0x1 or 0x4, or was put into another action
state during the step while still alive (stagger 3 from `Player_processDamage`), the
destructor overwrites that at the end of the 25th call.
**If the caster's hit points reach 0 during the step** the spell stops being run (the
hit-point test in front of `Player_updateCast`), so the remaining calls and the destructor
do not happen while that player object exists: the dead player keeps the scale of the last
call, creature flag 0x200000 (model not drawn) and object flag 0x4; action state and flag
0x1 are then those of the death sequence. The destructor runs only when the object is
destroyed (respawn), where its writes land on the dying object. Observed order; the visible
result (an invisible body) is Inferred.

**Stacking and refresh.** Not applicable in normal play: the caster is locked in state 0xe
for the 25 frames. The enemy effects are plain overwrites (timer, target handle, knock-back
speed and angle).

**Non-player caster** (only reachable through the weapon-effect cast as far as known):

- The constructor writes +0x58c on the caster without an is-player test (0x31173c) and the
  destructor does the same. On a creature that is not a player this is a store past the
  fields of its class (for a class smaller than 0x590 bytes, past the end of its block).
  Observed code; reachability Unknown.
- The player slot (+0x3c8) is not read anywhere in the class.
- Offline, `Player_clampToScreen` would be applied to it as well (it only uses the
  position).
- Through the weapon-effect path the returned spell is not attached, so run and the
  destructor never execute: the caster would keep state 0xe, flags 0x5 and (for a player)
  never leave the state. Inferred from the caller; reachability Unknown.

**Prediction copy.** Cannot cast. The copy is cloned from a player that is in state 0xe with
flags 0x5 but with an empty spell list, so nothing moves it; the rebase flag above is what
keeps it in step (Inferred).

##### SpellShadowStep layout (0x34 bytes)

| Offset | Type | Meaning | Evidence |
|---|---|---|---|
| +0x00 | s8 | level | ctor |
| +0x04 | handle | base back-list | ctor |
| +0x08 | Skill* | the skill | ctor |
| +0x0c | Creature* | owner = caster (facing is written through this pointer) | ctor, run 0x311f68 |
| +0x10 | u32 | private generator state | ctor |
| +0x14 | ptr | virtual table 0x51bd48 | ctor |
| +0x18 | float | progress t, 0 at the start, +0.04088309 per frame | ctor, run |
| +0x1c | float | speed 370.0 | ctor |
| +0x20 | float[3] | velocity: unit facing direction * 370 (vertical part 0) | ctor |
| +0x2c | Creature* | the creature being moved (= caster) | ctor 0x311750 |
| +0x30 | s16 | facing to apply in the second half (cast facing - 0x8000) | ctor 0x311744 |

#### Random draws

At the cast, in order:

1. Shared, one draw: base `Spell` construction.
2. Shared, one draw: centre `StaticFire` construction — only when stat 1 != 0 and the
   allocation succeeds. (Its `initCommon` then draws once from the fire's own generator.)
3. Shared, one draw per ring fire actually created (stat 1 - 1 candidates, each skipped when
   the ground there differs by more than 72 in height or the allocation fails), in ring
   order.
4. Private (`Spell_rand`), for each of 86 particles: three draws per attempt for a point in
   the cube [-1, 1)^3, repeated until the point is inside the unit sphere; then one draw for
   the model sample point index (`draw % count`).
5. Shared, one draw: `LightEffect` construction — only when stat 1 <= 1 (ranks 1 to 5) and
   the allocation succeeds.

Slot 31 and the knock-back writes draw nothing. The run function draws nothing.

Later, per fire, on its damage frames: one shared draw per **player** victim in its box
(before the is-enemy test, so also for players the fire then does not damage), followed by
`damage_apply`'s own draws for each victim actually struck. The fire's particle code uses its
own generator.

#### Presentation only

Cast sound; 86 particles of the definition at 0x8e84b8 (registered by `shadowStep_staticInit`
0x311fc8); the `LightEffect` at low ranks; the fires' lights, flames and particles; hiding
the model through creature flag 0x200000; the rank text (`SkillShadowStep_describeRank`
0x3113e0: stat 0 as seconds and tenths, three text variants for stat 1 = 0, 1, more); icon
slot 7 (0x3d1544).

#### Per-machine state

- `SpellShadowStep_run` reads view planes derived from the camera through
  `Player_clampToScreen`, but only when `g_networkMode` is 0 (0x311ea8). In a net game the
  branch is never taken on any machine. Observed.
- It writes `g_forceGhostRebase` (0x402797) = 1 on each of its 25 frames (0x311f20).
  Observed.
- The fires' damage tick is gated by `isNearView(941.0, pos)` (`StaticFire_run`): per
  `docs/skills.md` item 7 this is "near any player" in a net game and "near the camera
  focus" during a cutscene; the tick includes shared draws. Not specific to this skill.
- Each fire keeps the caster as a raw pointer (+0x4a8) for up to 360 frames and calls its
  slot 20 and passes it to `damage_apply`; nothing in the code read here clears it if the
  caster object is destroyed or replaced meanwhile (for example by a respawn). Observed
  store; consequence Inferred.
- Missing is-player test before the +0x58c writes (constructor and destructor), above.
- No use of the local player slot, pads, options, audio state, the cosmetic generator or
  0x404468 in the three functions.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x31127c | SkillShadowStep_ctor | skill object set-up |
| 0x3112e8 | SkillShadowStep_initStats | statistic tables |
| 0x311340 | SkillShadowStep_cast | allocates and constructs the spell |
| 0x3113e0 | SkillShadowStep_describeRank | rank text |
| 0x311604 | SkillShadowStep_manaCost | slot 15 with (level, 20) |
| 0x311638 | SpellShadowStep_ctor | state change, fires, enemy effects, particles |
| 0x311da0 | SpellShadowStep_dtor | restores scale, flags, action state |
| 0x311e3c | SpellShadowStep_run | the 25-frame move |
| 0x311fc8 | shadowStep_staticInit | one particle definition |
| 0x2c5240, 0x2c5814, 0x2c595c | StaticFire_ctor, StaticFire_initCommon, StaticFire_run | the fire object (decompile only) |
| 0x1b3d90, 0x1e71b0 | Player_clampToScreen and its view-plane helper | offline clamp |
| 0x118af8 | Creature slot 31 (base) | no-target timer |
| 0x115eb8 | Creature_applyKnockback | first 60 lines, for the angle convention |
| 0x14d4b8 | obj_moveWithCollision | first part, for the per-second scaling and the creature skip |
| 0x201bd8 | LightEffect_ctor | argument meaning |

#### Not determined

- The exact path through `obj_moveWithCollision` (terrain slide, push-out, gravity) was not
  specified here; a reimplementation needs `docs/objects.md` for it.
- Whether and how damage can reach the caster during the step (which queries and attacks
  still accept an object with flags 0x5) was not traced; what follows when it does is
  described under the destructor.
- Which classes override Creature slot 31 (the base version was the only one read).
- `StaticFire_run` was read in decompiled form only; its particle and light code, the
  deletion condition (+0x78 / +0x7a) and 0x2c6aa8 / 0x2c6bc0 / 0x2c6df0 were not read.
- Whether simulation code reads the caster's scale (+0xdc) while it is negative or near 0.

### 68 resurrect — SkillResurrect

#### Identity

| Item | Value | Evidence |
|---|---|---|
| Skill id / internal name | 68, `resurrect` | Observed: `SkillResurrect_ctor` 0x31206c |
| Skill class, virtual table | `SkillResurrect`, 0x51be30 | Observed 0x31206c |
| Skill object | 0x6e3010 (pointer cell 0x41b280, used by `Player_startSpawnProtection` 0x1b8fbc) | Observed |
| Kind (+0x08) | 0, ordinary active cast | Observed |
| Flags (+0x04) | 0: the prediction copy may not cast it | Observed |
| Recast (+0x0c) | 30 frames | Observed |
| Effect class | `SpellResurrect`, 0x70 bytes, virtual table 0x51be00, constructor 0x3127b4, destructor 0x312a70, run 0x312b30, draw 0x312f48. One helper called from `Player_processDamage`: 0x3130f4, which can create a `StrongStancePhantom` (Creature, 0x3d8 bytes, constructor 0x1618d4) and a `LightEffect` (0xbc bytes) | Observed |
| Who has it | cleric tree (level 25, needs skill 22). No monster call site known | §1.7 |

The skill is two different effects selected by `g_numPlayers` (0x4d8ae0):

- **Mode B, two or more players**: a channel on a dead player's body that ends by
  re-creating that player where the body lies.
- **Mode A, one player**: a timed ward on the caster; while it lasts, each time the caster's
  hit points reach 0 a percentage roll decides whether the death is cancelled.

#### Statistics

Set by `SkillResurrect_initStats` 0x3120d8 (Observed). No tier-2 tables. Every read is slot
10 `getStat(stat, level)`.

| Stat | Meaning (how known) | Tier 1: first, base, step |
|---|---|---|
| 0 | mode B: length of the channel in seconds (Observed: ctor 0x312930 -> +0x60) | 1, 10, -0.499999 (0xbeffffde) |
| 1 | mode B: percent of maximum hit points the revived player gets (Observed: run 0x312e60-0x312ec4) | 1, 25, 3.7499428 (0x406fff10) |
| 2 | mode A: length of the ward in seconds (Observed: ctor 0x312924 -> +0x60) | 1, 3, 0.499999 (0x3effffde) |
| 3 | mode A: percent chance that a death is cancelled (Observed: 0x3130f4) | 1, 10, 3.7499778 (0x406fffa3) |
| 4 | mana cost (Observed: slot 15 via 0x3126d8) | 1, 90, 7.9999146 (0x40ffff4d) |

| Rank | stat 0 (s) | stat 1 (%) | stat 2 (s) | stat 3 (%) | stat 4 (mana) |
|---|---|---|---|---|---|
| 1 | 10 | 25 | 3 | 10 | 90 |
| 2 | 10 | 29 | 3 | 14 | 98 |
| 3 | 9 | 32 | 4 | 17 | 106 |
| 4 | 9 | 36 | 4 | 21 | 114 |
| 5 | 8 | 40 | 5 | 25 | 122 |
| 6 | 8 | 44 | 5 | 29 | 130 |
| 7 | 7 | 47 | 6 | 32 | 138 |
| 8 | 7 | 51 | 6 | 36 | 146 |
| 9 | 6 | 55 | 7 | 40 | 154 |
| 10 | 6 | 59 | 7 | 44 | 162 |
| 11 | 5 | 62 | 8 | 47 | 170 |
| 12 | 5 | 66 | 8 | 51 | 178 |
| 13 | 4 | 70 | 9 | 55 | 186 |
| 14 | 4 | 74 | 9 | 59 | 194 |
| 15 | 3 | 77 | 10 | 62 | 202 |
| 16 | 3 | 81 | 10 | 66 | 210 |
| 17 | 2 | 85 | 11 | 70 | 218 |
| 18 | 2 | 89 | 11 | 74 | 226 |
| 19 | 1 | 92 | 12 | 77 | 234 |
| 20 | 1 | 96 | 12 | 81 | 242 |

(Computed in single precision with the rounding of slot 10; note that the steps are slightly
off the round numbers, which is why rank 2 still gives 10 seconds and rank 20 gives 12.)

#### Cost and limits

- Mana: `SkillResurrect_manaCost` 0x3126d8 = slot 15 = (float) getStat(4, level): 90, 162,
  242 at ranks 1, 10, 20. Recast 30 frames.
- `SkillResurrect_canUse` 0x312168 (skill, caster). Observed, in this order:
  1. `g_pvpModeA` != 0 and the caster is a player: a HUD notice (90 frames, caster's slot)
     and refuse.
  2. If `g_numPlayers` >= 2: `SkillResurrect_findTarget(skill, caster)` (0x312240, below)
     must return a slot; when it returns -1: a HUD notice (180 frames) if the caster is a
     player, and refuse.
  3. Allowed only when the caster has **no `SpellResurrect` attached**
     (`creature_findSpellByType(caster, SpellResurrect typeinfo)` is null). So neither mode
     can be stacked on one caster.
- The +0x3c8 reads in steps 1 and 2 are behind the is-player test.
- `Player_castSkill` calls canUse after its own gates (recast counter, prediction copy).
  The monster and weapon-effect paths do not call canUse at all.

#### Behaviour

##### Target search — 0x312240 (proposed `SkillResurrect_findTarget`), Observed

```
fwd  = (cos16(caster.facing), sin16(caster.facing), 0)
side = (cos16(caster.facing + 0x4000), sin16(caster.facing + 0x4000), 0)
best = -1; bestF = 9999999.0
for slot = 0 .. g_numPlayers - 1:
    if g_playerDeadCountdown[slot] (s16 at 0x4f84a8 + 2*slot) >= 61: continue
    T = g_players[slot].object (record +0x43d8);  if T == null: continue
    f = dot(fwd,  T.pos - caster.pos);   if not (-12.0 < f < 136.0): continue
    l = dot(side, T.pos - caster.pos);   if not (l < 56.0): continue      one-sided test
    if not (f < bestF): continue
    if SkillResurrect_isSlotBeingRaised(skill, slot): continue            0x31270c
    best = slot; bestF = f
return best
```

- The countdown at 0x4f84a8 is 240 at level start and after every respawn
  (`player_respawn` 0x1bd0a4, `arena_respawnPlayer`, 0x1ec2b8) and `game_checkAllDead`
  0x1e7438 lowers it by 1 per frame for a slot whose record hit points are <= 0 (not during
  a cutscene or pause, and only while not every player is alive). "< 61" therefore means
  **the player has been dead for at least 180 counted frames**. There is no other test that
  the target is dead: a living player always has 240 here.
- The sideways test has no lower bound (0x312360-0x31236c compare l < 56.0 only): bodies on
  the side where l is negative qualify at any sideways distance, as long as the forward
  distance is inside (-12, 136). Observed; presumably an oversight.
- The winner is the eligible body with the smallest forward distance; on a tie the lower
  slot.
- 0x31270c (skill, slot) returns 1 when any player in `g_alivePlayers` has a
  `SpellResurrect` attached whose target (+0x18) has that player slot: two living players
  cannot raise the same body at once. It reads +0x3c8 of the spell's target without an
  is-player test.

##### Cast — `SkillResurrect_cast` 0x3123e4 (skill, level, caster, pos*, facing), Observed

level = slot 14 `adjustLevel(level, 1)` (unchanged). Position and facing arguments unused.

- `g_numPlayers` < 2: target = the caster.
- otherwise: slot = findTarget(skill, caster); -1 -> return null (no spell, but
  `Player_castSkill` still starts the recast and takes the mana — the player path cannot get
  here because canUse ran the same search in the same frame); target = that slot's player
  object.

`pool_new(0x70)`; null -> return null. `SpellResurrect_ctor(spell, level, target, skill,
caster)`. The caller attaches the spell **to the caster**.

**When the spell runs.** Observed. A player's spells are run by `Player_updateCast`
0x1a3f70, called from `Player_run` at 0x1ac6a8 — after `Creature_run`,
`Player_processDamage` and the action-state switch — and **only when the caster's record
hit points (+0xac) are above 0.0** (0x1ac68c-0x1ac69c); `Creature_run` runs spells only for
non-players. Therefore: run call 1 is made in the cast frame itself, at the end of that
`Player_run`; in every later frame `Player_processDamage` comes **before** the spell's run;
and a caster whose hit points are <= 0 has no spell run at all.

##### Constructor — `SpellResurrect_ctor` 0x3127b4, Observed, in order

1. Base part with **owner (+0x0c) = the target**, not the caster; one shared draw for +0x10.
2. Light node at +0x24: colour (115, 86, 119), radius 12.0, position = target position +
   (0, 0, 1.0); `light_link`.
3. +0x18 = target (raw pointer).
4. +0x60 = (float) getStat(`g_numPlayers` == 1 ? 2 : 0, level): the remaining time in
   seconds. +0x68 = caster (raw pointer). +0x1c = 0.
5. +0x64 = (float)((1.0 / (double)+0x60) * 0.17400299012660980) (double arithmetic, the
   constant is the 8 bytes at 0x552a08): the animation rate used in mode B.
   +0x20 = 0, +0x6c = 0.
6. Cast sound at the target's position.
7. Only when `g_numPlayers` != 1:
   - if the caster is a player: `g_players[caster slot]` +0x4c20 (movement speed multiplier)
     = 0.5;
   - `anim_start(0.1, target animation state (+0x114), clip, 3)` where clip is the pointer at
     +0x44 of the target's animation table (target +0x24) — the first entry of the per-weapon
     idle table that `player_resetIdleAnim` indexes (Inferred). This starts blending the
     body out of its death pose.

##### Run — `SpellResurrect_run` 0x312b30, once per simulated frame while the caster's hit points are above 0, Observed

```
a = (g_simFrame * 3900) mod 65536                 signed remainder as the code computes it
r = sin16(a) * 7.0 + 97.0;  light radius = r, 1/r^2            (presentation)
if g_numPlayers == 1:
    light position = owner.pos + (0, 0, 48.0); light_relink
T = spell.target (+0x18)
T flash colours: +0x90 = 98, +0x92 = 75, +0x94 = 46, +0x96 = 46, +0x9a = 75, +0x9c = 46,
                 +0x9e = 46                                     (s16 each; +0x98 not written)
if g_numPlayers >= 2:
    C = spell.caster (+0x68): the same seven colour writes on C
    dir = normalise(T.pos - C.pos)                              three components
    fx_emitFromModelVerts(41.0, C, 18, particle A, &dir, null)
    fx_emitFromModelVerts(39.0, T, 38, particle B, &dir, &(dir * -42.0))
    if spell.remaining (+0x60) < 0.25 and spell.revived (+0x1c) == 0:
        slot = T.playerSlot (+0x3c8)
        player_respawn(slot, &T.pos, T.facing, -1, -1)
        player_resetIdleAnim(slot)
        arena_addLife(slot)                                  0x3058c0
        spell.target = g_players[slot].object                   the new Player object
        pct  = getStat(1, level)
        slot = spell.target.playerSlot
        spell.revived = 1
        g_players[slot].hp (+0xac) = (g_players[slot].maxHp (+0xb0) * (float)pct) * 0.01
    Player_animStep(spell.rate (+0x64), spell.target)
    g_forceGhostRebase = 1
spell.remaining -= 0.016666666 (0x3c888888)
if spell.remaining < 0:  destroy self (slot 1 with argument 3)
```

Timing, computed in single precision (the countdown is a float, so the frame counts are not
exactly 60 per second). Call k is made at the end of the caster's `Player_run` in frame
F + k - 1, F being the cast frame, provided the caster's hit points stay above 0:

| Seconds at cast | Run calls in total | Run call that performs the respawn (mode B) |
|---|---|---|
| 1 | 61 | 47 |
| 2 | 121 | 107 |
| 3 | 181 | 167 |
| 4 | 241 | 227 |
| 5 | 300 | 286 |
| 6 | 360 | 346 |
| 7 | 420 | 406 |
| 8 | 480 | 466 |
| 9 | 540 | 526 |
| 10 | 600 | 586 |
| 11 | 660 | (mode A only) |
| 12 | 721 | (mode A only) |

##### Mode B in words (two or more players)

- **Who can be raised**: a player slot with an existing player object, dead for at least
  180 counted frames, inside the strip described under the target search, not already the
  target of a living player's `SpellResurrect`; never in PvP mode A for a player caster.
- **During the channel** (stat 0 seconds): the caster keeps full control but his record
  speed multiplier is 0.5; nothing checks that he stays near the body or that the body is
  still the same object. **If the caster's own hit points reach 0 the channel stops**: his
  spells are no longer run, so the countdown, the flash and the body's animation freeze and
  the respawn never happens; his record speed multiplier stays 0.5. The frozen spell is
  deleted (and the multiplier set back to 1.0) only when his player object is destroyed,
  and since every revival replaces that object it cannot resume (Inferred from the revival
  paths read here). Because a dead caster is no longer in `g_alivePlayers`
  (`game_rebuildAlivePlayers` 0x1e72f8 lists objects without flag 0x8), 0x31270c stops
  counting his spell and another player may start raising the same body. While the channel
  runs, both creatures get the colour flash every frame, and
  the body's animation set is advanced every frame at the spell's rate through
  `Player_animStep` (which also rewrites the body's root-motion fields +0xbc / +0xc0).
- **The revival** happens once, in the first run call that starts with less than 0.25 s left
  (about 15 frames before the end). `player_respawn(slot, pos, facing, -1, -1)` 0x1bd040:
  countdown[slot] = 240; local menus closed if the slot is local; **the old player object is
  destroyed immediately**; record hit points = half of maximum (maximum in PvP mode A); a new
  `Player` (0x590 bytes) is constructed **at the body's position with the body's facing**
  (the -1 arguments select "exactly here", no free-spot search);
  `Player_startSpawnProtection` (protection counter +0x4b4 = 60, or 90 in a net game, 1
  while `g_recallCountdown` is set; it calls 0x31270c for the slot and sets object flag 0x2
  on the new object — hiding it — only when no living player's `SpellResurrect` targets the
  slot, so after this skill's revival the player is expected to stay visible; one
  `LightEffect`); `g_forceGhostRebase` = 1; `game_rebuildAlivePlayers`; camera reset and a
  4-frame fade on the machine that owns the slot in a net game.
  Note the order: at the time of that 0x31270c call the spell's +0x18 still holds the
  address of the **old** object, which `player_respawn` has just destroyed and freed, and
  0x31270c reads +0x3c8 through it. The result is right only because the freed block either
  still holds the slot number or has just been reused for the new `Player` (both blocks are
  0x590 bytes from the same pool; reuse Inferred, not traced in `pool_new`). Observed order
  0x1bd0d8-0x1bd0f4 (destroy) before the call of 0x1b8f28.
  Traced since (`docs/issues/stale-pointers.md` section 3, FINDINGS ST2): `player_respawn`
  frees the old `Player` (destructor call at 0x1bd0f0) and allocates the new one (`pool_new`
  at 0x1bd138) with no call between, and the pool's free lists are last-in-first-out, so
  the new object always gets the old block, on every machine. The read through the stale
  target therefore always sees the new object's slot and 0x31270c returns 1; the "either
  … or" above reduces to its second half.
- **Hit points** are then overwritten: maximum * stat 1 / 100 (25 % at rank 1 to 96 % at
  rank 20).
- **Mana**: not written by any function on this path (`SpellResurrect_run`,
  `player_respawn`, `Player_startSpawnProtection`, `Player_ctor` were searched for stores to
  record +0xc0): the player comes back with the mana he died with. Observed by search.
- **Experience**: no store to the experience field (record +0x5c) on this path or in the
  death branch of `Player_processDamage` (pattern search). Observed by search.
- **Arena**: when `g_pvpModeB` is set and `g_pvpModeA` is clear, 0x3058c0 adds 1 to the
  slot's arena life counter (s16 at 0x50389a + 12 * slot), undoing the life that the death
  cost (`arena_loseLife` 0x305650 is the decrement).
- After the revival the spell runs on for its last frames with the new object as target
  (flash, particles, animation step) and then ends.
- **Destructor** 0x312a70: when `g_numPlayers` > 1 and the caster is a player, the caster's
  record +0x4c20 = 1.0; light destroyed; base clean-up.
- **What the dead player experiences meanwhile**: nothing in the spell is specific to his
  machine. His object stays in action state 4 (dead) until it is replaced; all machines run
  the same simulation. The per-machine parts are inside `player_respawn` (menus, camera,
  fade for the local slot) and the sound cues of `Player_animStep`, which are skipped for a
  machine's own real player.
- Creature slot 32 (revive, 0x10bfc8) is **not** used by this skill: there is no call
  through that slot anywhere in 0x31206c-0x3133d0; the revival is always the replacement of
  the Player object by `player_respawn`. Observed.

##### Mode A in words (one player)

- Target = owner = caster. The spell lasts stat 2 seconds (3 at rank 1, 12 at rank 20; run
  counts in the table) and only shows a light that follows the caster (height +48), the
  colour flash, and the ring drawn by the draw function. It never calls `player_respawn`.
- Order inside a frame: `Player_processDamage` (and with it the roll below) comes before
  the cast and before the spell's run. The ward is attached in the cast frame F after that
  frame's damage processing and is destroyed by its last run call at the end of frame
  F + N - 1 (N = the run-call total of the table), so the roll is available to
  `Player_processDamage` in frames F+1 .. F+N-1: 180 frames for 3 s, 240 for 4 s, 299 for
  5 s, 359, 419, 479, 539, 599, 659 and 720 for 12 s.
- `Player_processDamage` 0x1b2cc0, at the point where the player's record hit points are
  <= 0 (0x1b3370): if the player has a `SpellResurrect` attached **and `g_numPlayers` == 1**
  it calls 0x3130f4 (proposed `SpellResurrect_onOwnerDeath`) and stores the returned float
  as the record hit points (0x1b33b0-0x1b33c8). If they are now above 0 the death sequence
  is skipped and the function returns after clearing the pending-damage flags (+0x2dc).
- 0x3130f4 (spell), Observed:
  1. one shared draw r; chance = getStat(3, level);
  2. if (int)(r % 100) < chance — **saved**: `pool_new(0x3d8)` and, when it succeeds,
     `StrongStancePhantom_ctor(obj, source = spell target, clip name taken from +8 of the
     target's animation table, 0, 1)` (a Creature construction: one shared draw; a non-solid
     copy of the player's model that plays one clip, linked to the player by handle);
     `pool_new(0xbc)` and, when it succeeds, a `LightEffect` at the caster's position +
     (0, 0, 36) (start colour 137, 102, 92, -96; one shared draw). Returns
     `g_players[target slot].maxHp * 0.5`.
  3. otherwise — **failed**: +0x20 = 1, +0x6c = `g_simFrame`, `light_unlink(spell + 0x24)`;
     returns 0.0, and the death proceeds. From then on the spell is not run any more (hit
     points <= 0): its countdown stops and it stays attached, drawn as the fading ring,
     until the player object is destroyed.
- A successful save changes nothing in the spell: hit points are above 0 again before the
  hit-point test at 0x1ac68c of the same frame, so the spell's run is not even skipped once;
  it stays for the rest of its time and rolls again at the next death. Hit points after a
  save are exactly half of maximum; mana and everything else are untouched.

##### Mode changes while a spell exists

`g_numPlayers` is tested separately at the cast (< 2), in the constructor (== 1, twice), in
the run function (== 1 and < 2), in the destructor (> 1), in the draw function (== 1) and in
`Player_processDamage` (== 1). A spell created in one mode therefore behaves as the other
mode from the frame a player joins or leaves. Consequences that follow from the code
(Inferred, not tested): a ward cast alone and still running when a second player joins takes
the mode-B branch with target = caster and, once less than 0.25 s remain, calls
`player_respawn` on the living caster, destroying the object the spell is attached to while
its run function is executing (the call comes from inside that same object's `Player_run`,
through `Player_updateCast`); a channel started with two players whose count drops to 1
ends without restoring the caster's speed multiplier (it stays 0.5 until something else
writes record +0x4c20).

##### Non-player caster and prediction copy

- Constructor and destructor test the caster's is-player flag before using +0x3c8
  (0x3129fc, 0x312a8c). Observed.
- The reads of +0x3c8 in the run function (0x312e10, 0x312ea4), in 0x31270c and in 0x3130f4
  are of the **target** (+0x18), not of the caster. In mode B the target comes from the
  player table, so it is a player object unless the pointer has gone stale.
- Through the weapon-effect cast the spell is not attached: constructor effects only (a
  player caster's speed multiplier would stay at 0.5, the body's animation is started, the
  light is linked) and no revival. Inferred; reachability Unknown.
- The prediction copy cannot cast (flag bit 0 clear). The copy's spell list is empty
  (`docs/creatures.md`, clone), so when `Player_processDamage` runs for the copy the ward is
  not found and the copy takes the death branch even where the real player will be saved;
  this only matters in a net game with exactly one player. Inferred.

##### SpellResurrect layout (0x70 bytes)

| Offset | Type | Meaning | Evidence |
|---|---|---|---|
| +0x00 | s8 | level | ctor |
| +0x04 | handle | base back-list | ctor |
| +0x08 | Skill* | the skill | ctor |
| +0x0c | Creature* | "owner" = the target (the spell is attached to the caster instead) | ctor 0x312884 |
| +0x10 | u32 | private generator state (never used by this class) | ctor |
| +0x14 | ptr | virtual table 0x51be00 | ctor |
| +0x18 | Creature* | current target, raw pointer; replaced by the new Player object after the respawn | ctor 0x312908, run 0x312e7c |
| +0x1c | s32 | 1 once the respawn has been done | run 0x312ea8 |
| +0x20 | s32 | mode A: 1 after a failed save | 0x3130f4 |
| +0x24 | light node (0x3c bytes) | +0x2c, +0x2d u8 0; +0x2e s16[3] colour 115, 86, 119; +0x34 s16 0; +0x36 s16[3] same colour; +0x3c s16 0; +0x40 and +0x48 radius; +0x44 and +0x4c 1 / radius^2; +0x50 0.0; +0x54 float[3] position | ctor, run |
| +0x60 | float | seconds remaining | ctor, run |
| +0x64 | float | animation rate for the body, 0.174003 / seconds | ctor 0x31299c |
| +0x68 | Creature* | caster, raw pointer | ctor 0x312958 |
| +0x6c | s32 | mode A: `g_simFrame` of the failed save (fade start for the ring) | 0x3130f4, draw |

#### Random draws

- At the cast: shared, one draw (base `Spell` construction).
- Mode B, in the respawn frame, inside `player_respawn`: shared, one draw for the new
  `Player` object (GameObject construction) and one for the `LightEffect` of
  `Player_startSpawnProtection`, each only if its allocation succeeds; then that function's
  particle draws come from the new object's own generator. (No free-spot search, so none of
  `world_findFreeSpot`'s draws.)
- Mode A, at each death while the ward is attached: shared, one draw (the roll); on success
  one more for the phantom and one more for the `LightEffect` (allocation permitting).
- Every frame of mode B: `fx_emitFromModelVerts` twice — cosmetic generator only.
- The spell's private generator is never drawn from.

#### Presentation only

Cast sound; the pulsing light; the colour-flash writes on target and caster (+0x90..+0x9e);
the two particle streams (definitions 0x8e8508 and 0x8e8558, registered by
`resurrect_staticInit` 0x3132c4); the phantom and light of a successful save; the HUD
notices of canUse; the two description functions (0x312500 picks one of two texts by
`g_numPlayers`; 0x31256c shows stats 2 and 3 with one player, stats 0 and 1 otherwise).
**Draw function** 0x312f48 (Spell slot 3, called from draw code): only with one player, 13
glow sprites on a ring of radius 15 + trunc(fade * 100) around the target at height +116,
rotating with `g_simFrame`, fading out over 60 frames after a failed save (fade = min(1,
(g_simFrame - +0x6c) / 60)). It reads `g_numPlayers`, `g_simFrame` and spell fields and
writes nothing but locals and the glow queue (`glow_add`). Observed.

#### Per-machine state

- `hud_showMessage` in canUse and everything local inside `player_respawn`
  (`net_isLocalSlot` -> menus, camera, fade): shared decision, local presentation. Observed.
- `Player_animStep` on the body skips sound cues for a machine's own real player; its return
  value is not used here. Observed (helper note), not re-read.
- Mode B writes `g_forceGhostRebase` (0x402797) = 1 every frame (0x312edc), and
  `player_respawn` writes it once more.
- Raw pointers: +0x18 (target) and +0x68 (caster) are plain pointers. The target is written
  to (colour flash) and animated every frame of the channel; if the dead player's object is
  replaced by another route during the channel (the save-point revival of
  `docs/monsters.md`, which needs the countdown at 0; an arena respawn; the player leaving),
  the spell keeps using the freed object, and at the respawn frame reads the slot number
  from it. Observed stores and uses; consequence Inferred.
- The mode switch on `g_numPlayers` described above.
- The is-player tests: caster guarded in constructor and destructor; target unguarded in
  run, 0x31270c and 0x3130f4 (see above).
- The countdown at 0x4f84a8 that gates the target search is shared state (written only by
  simulation code), but it is also read by camera and HUD code (`Camera_computeTarget`
  0x206618, `hud_drawNetCamPrompt` 0x1e022c): that is where the dead player's own machine
  behaves differently while he waits. Reference search only; those two were not read.
- No use of pads, camera, options, the cosmetic generator for decisions, or 0x404468.

#### Functions read

| Address | Name | What it is |
|---|---|---|
| 0x31206c | SkillResurrect_ctor | skill object set-up |
| 0x3120d8 | SkillResurrect_initStats | statistic tables |
| 0x312168 | SkillResurrect_canUse | PvP gate, target gate, no-stacking gate |
| 0x312240 | SkillResurrect_findTarget (proposed) | picks the body to raise; callers canUse 0x3121d0 and cast 0x312458 |
| 0x3123e4 | SkillResurrect_cast | chooses the target and constructs the spell |
| 0x312500 | SkillResurrect_describeExtra | one of two texts by player count |
| 0x31256c | SkillResurrect_describeRank | rank text |
| 0x3126d8 | SkillResurrect_manaCost | slot 15 |
| 0x31270c | SkillResurrect_isSlotBeingRaised (proposed) | callers 0x312384 and `Player_startSpawnProtection` 0x1b8fbc |
| 0x3127b4 | SpellResurrect_ctor | |
| 0x312a70 | SpellResurrect_dtor | |
| 0x312b30 | SpellResurrect_run | |
| 0x312f48 | SpellResurrect_draw | ring of glows, one player only |
| 0x3130f4 | SpellResurrect_onOwnerDeath (proposed) | the mode-A roll; caller `Player_processDamage` 0x1b33b0 |
| 0x3132c4 | resurrect_staticInit | two particle definitions |
| 0x1bd040 | player_respawn | read in full |
| 0x1b8f28 | Player_startSpawnProtection | first part (counter, hide flag, light) |
| 0x1b2cc0 (0x1b3354-0x1b3520) | Player_processDamage | the death test and the call of 0x3130f4 |
| 0x1e7438, 0x1ec2b8 | game_checkAllDead, countdown reset | who changes 0x4f84a8 |
| 0x3058c0, 0x305650, 0x305784 | arena life refund, arena_loseLife, arena_respawnPlayer | the arena counter |
| 0x1618d4 | StrongStancePhantom_ctor | arguments and construction draw |

#### Not determined

- Whether anything other than the caster's death (hit points <= 0, see mode B) interrupts
  the channel; a staggered but living caster's spell keeps running.
- What `Player_animStep` at rate 0.174 / seconds amounts to in clip time, and which clip
  +0x44 of the animation table is (taken by analogy with `player_resetIdleAnim`).
- The allocation-failure path of `player_respawn` (old object destroyed, no new one): the
  run function then dereferences the record's object pointer unchecked (0x312e70-0x312ea4).
- `Player_ctor` and `Player_startSpawnProtection` were not read beyond what is quoted;
  their shared draws are counted from the construction rule only.
- Reachability of the weapon-effect path and of the player-count change mid-spell.

## Part 4 — Status, findings, corrections

### 4.1 How this document was produced and checked

Each section of Parts 2 and 3 was written from one reading of the functions listed under its
"Functions read", by decompile and disassembly. Nothing was executed. A second pass then
checked the following; it did **not** re-read every function:

- every statistic constant of ids 35–68 against `tools/dump_tables.py --table skills` (all
  step bit patterns and the rank 1 / 10 / 20 mana values agree);
- statistic values and the main timers under the console's truncating arithmetic (§1.8);
- the shared rules of Part 1 (cast sequence, spell run order, first-run frame, the arc
  query, slots 8 and 10–15), read independently;
- individual claims chosen because other sections lean on them: the HarmTouch hook in
  `Player_meleeHit` (0x1b6a98, call of 0x2d2cbc), the Shock and FireArrow damage calls, the
  Healing constants and both recipient branches, the MultiFire projectile class (table
  0x50e5a0 is `MissileWeapon`), the Cyclone constructor's write into the animation clip, the
  ShadowStep step size, the Resurrect speed-multiplier store (0x312a28), the `StaticFire`
  view radius, the id ↔ name mapping of the multi-id classes.

One error of substance was found and corrected that way (which function runs a player's
spells, and therefore the frame of the first run); §1.4 is the result. Treat everything not
in the list above as a single careful reading.

### 4.2 What is specified

"Full" means: every function of the skill's own classes and the outside code the skill
depends on was read, and the section gives rules, constants, draws and end conditions.
"Full (needs clip data)" means the same, but a duration or distance depends on an animation
file's length, event times or root motion, which is data on the disc and is given here as a
formula. No id in the range was left unreached.

| Id | Name | Status | What a rebuild still lacks (see the section's "Not determined") |
|---|---|---|---|
| 35 | charge | Full | whether a root-motion track left from an earlier action adds to the rush; the writers of `Player_move`'s speed factors |
| 36 | darkness | Full | what the no-target timer (Creature slot 31) does beyond dropping the target, and which classes override it |
| 37 | shock | Full | when each monster chooses to cast |
| 38 | groundpound | Full (needs clip data) | length of the pound clip (end of action state 10); by §1.4 the effect object created on the event frame first runs one frame later |
| 39 | convertenemy | Full | per-class reactions to being charmed |
| 40 | convertundead | Full | which classes carry creature kind 0x10 |
| 41 | cyclone (and 84) | Full (needs clip data) | lengths and event tables of the two spin clips, which fix the spin time in frames |
| 42 | harmtouch | Full | — |
| 43 | firearrow | Full | Player slot 20 on non-creature objects; three monster call sites read only for their arguments |
| 44 | coldarrow | Full | the chill-to-slow conversion is in `docs/creatures.md`, not re-read |
| 45 | poisonarrow | Full | take-damage handling of the cloud's flag bits |
| 46 | multifire | Full | reachability of the non-player branch (cosmetic generator) |
| 47 | explodearrow | Full | which object classes besides creatures a box query can return |
| 48 | archery | Full | — |
| 49 | bash | Full (needs clip data) | root motion and length of the bash clip (lunge distance, recovery) |
| 50 | minorhealing | Full | whether anything clamps hit points after an overshoot |
| 51 | ancestralcall | Full (needs clip data) | length of the six cast clips (how long action state 6 lasts) |
| 52 | root (and 31, 32, 85) | Full | per-monster reactions to the root timer |
| 53 | criticalhit (and 33, 81) | Full | — |
| 54 | holyshield | Full | the early returns at the head of `Player_takeDamage` |
| 55 | healing (and 86) | Full | monster state machines around the call sites |
| 56 | coneoffrost | Full | exact survival of the channel through a stagger; the older non-skill branch of state 5 |
| 57 | shockoffire | Full | take-damage handling of the splash flag bits |
| 58 | froststorm | Full | positions monsters pass to the cast |
| 59 | lifetap | Full | delivery of the pending health / mana pools (player regeneration code) |
| 60, 61 | Blunt, Slashing | Full | meaning of each equip-check result code |
| 62 | strongstance | Full | units of the phantom's knockback velocity |
| 63 | naturalresistance | Full | the item part of the armour recalculation |
| 64 | stunningstrike | Full | what each monster class does in the stunned state |
| 65 | giantgrowth | Full | on which frame of a swing the damage recalculation samples the scale |
| 66 | planarwind | Full | — |
| 67 | shadowstep | Full | the collision step itself is `obj_moveWithCollision` (`docs/objects.md`), not restated |
| 68 | resurrect | Full (needs clip data) | clip rate of the revive animation; the allocation-failure path of `player_respawn` |

Open in every section and not repeated in the table:

- **Item data.** Whether any item carries a type-0x29 effect for a given id decides whether
  the "weapon-effect cast" behaviour described in each section can happen at all. The
  consequences are written down (most return an unattached spell that never runs; Charge,
  Cyclone and Bash would leave a player stuck in an action state) but reachability is
  Unknown.
- **Take-damage flag bits.** `damage_apply` passes flag bits it does not interpret
  (0x20, 0x800, 0x10000, 0x40000, 0x80000, 0x100000, 0x200000 …) to the victim's
  take-damage function. The sections give the bits; what each class does with them belongs
  to the creature and player documents.
- **Animation data.** Clip lengths, event times and root motion were not read from the
  disc.
- **Floating point.** See §1.8.

### 4.3 Things a rebuild is likely to get wrong

Collected from the sections; each is Observed there.

- Presentation objects cost shared draws: every `LightEffect`, `GlowingShaft`, `FlyingText`
  and each cosmetic ice shard of FrostStorm is a `GameObject` whose constructor draws the
  shared generator. HolyShield creates one inside the damage chain. If the pool allocation
  fails the draw does not happen (this is ledger row D21 again).
- LifeTap's blocking glow takes its particle direction from the **shared** generator: three
  draws per attempt, repeated until the point is inside the unit sphere, every frame a
  player with any LifeTap rank blocks (`Player_run` state 8, 0x1a6384–0x1a6468).
- The private generator of a spell or object is often drawn a fixed number of times for
  particles before a gameplay roll (HarmTouch: 204 draws before the damage spread). The
  particles can be dropped, the draws cannot.
- Several skills ignore the cast position or the aim-assisted facing that
  `Player_castSkill` computes (PlanarWind, Healing, Darkness …); each section says which
  arguments are used.
- In a net game the cast fires at animation blend weight 0.5 instead of 1.0, a melee hit
  lands on frame 1 of the swing, players take no knockback, and Root cannot hold a player.
- A player at 0 hit points runs no spells; timers on its spells stop, they do not expire.
- A kind-1 (channelled) skill needs only half of its per-second cost to start.
- Rank text is not the rule: Shock's description shows ±20 % but the roll is from the
  statistic to +20 %.
- Statistic tiers follow the slot the code calls, not who the caster is: Root, both Converts
  and HolyShield call slot 10 (tier 1 for everyone); ShockOfFire's direct damage uses slot 8
  (tier 1) even for monsters.

### 4.4 Per-machine findings — proposed ledger rows

Numbering is local to this document. "Kind" is how the *consequence* is known; the code at
the addresses was read in every case. None was tested on a running game.

| # | Finding | Kind | Where |
|---|---|---|---|
| S1 | Cyclone is castable by the prediction copy, and `SpellCyclone_ctor` writes event slot 0 of the shared spin clip (time 0.05, mask 1) before its copy test. The run function counts that slot's time down in the clip header, which every object playing the clip shares. On the owner's machine the copy's cast therefore resets the slot some frames before the real cast; another player with the same character model who is spinning at that moment would end the spin on a different frame on that machine | Observed stores; consequence Inferred | stores 0x2d1978, 0x2d197c; copy test 0x2d19c4; section 41 |
| S2 | Addition to K3 (stats page leaves off-hand numbers in record +0xcc / +0xd0 / +0xd4 on one machine): the hit handlers of FireArrow, ColdArrow and PoisonArrow read +0xd0 / +0xd4 from the owner's record at the moment of the hit, so an arrow in flight is one more reader inside that window | Observed readers; reachability Inferred | 0x2d685c, 0x2d7aac, 0x2d932c; `stats_screen` 0x1d2c38, 0x1d2d30; Part 2 bow section |
| S3 | `StaticFire` objects left by ShadowStep (rank 5 and above) keep the caster as a raw pointer, not a handle, for up to 360 frames; `SpellBash` keeps its target the same way (+0x24); `SkillResurrect_isSlotBeingRaised` reads the raw target pointer of a `SpellResurrect` after `player_respawn` has freed the old object. A freed block's contents depend on pool history, which is not the same on every machine (D21) | Observed pointers; consequence Inferred | section 67 (+0x4a8 of the fire), section 49, section 68 (0x31270c) |
| S4 | Resurrect chooses between its two modes by `g_numPlayers` at eight separate places, at cast time and while running, so a player joining or leaving mid-spell switches mode under it | Observed tests; consequence Inferred (same on all machines if the count changes on the same frame everywhere) | section 68 |
| S5 | New unguarded uses of the caster's player slot or action state by a possibly non-player caster (weapon-effect path only): `SpellCyclone_ctor` and `SpellBash_ctor` store +0x58c; `SpellShadowStep_ctor` and `SpellAncestralCall_ctor` store +0x58c as well; `SkillConvertUndead_canUse` reads +0x3c8 for a HUD message | Observed | 0x2d18f8, 0x2de6c4, 0x31173c, 0x2e0c58, 0x2d0b60 |
| S6 | `DummyDamager_onTouch` (the damage carrier ConeOfFrost uses) dereferences its owner handle without a null test | Observed | 0x1ee7d8; section 56 |
| S7 | Confirmed from `docs/skills.md` (b) item 1: a non-player MultiFire caster takes the upper damage figure from two draws of the cosmetic generator. No caller was found that reaches it | Observed; reachability Unknown | 0x2d9e08–0x2d9ec8; section 46 |
| S8 | ExplodeArrow hands every object its box query returns to `damage_apply`, with shared draws for each. Any object that exists in the grid on one machine only would change the draw count. None was identified (launched props live in grid B and are not returned) | Observed; no instance found | 0x2db888–0x2dba44; section 47 |

Already covered by existing rows and only confirmed here: the alive-player list readers
(G19: the critical-hit aura, both AncestralCall queries, Healing); pool-dependent shared
draws (D21).

### 4.5 Patch proposals

None. No finding above has an observed route to a desync in ordinary play: S1 needs two
players with the same model spinning within a few frames of each other, S2 is K3's
condition plus an arrow in flight, S3 needs a pointer to outlive its object. A patch for S1
would move two stores in `SpellCyclone_ctor` behind the copy test; it was not written
because the reader of the shared slot was traced by one reading only and nothing was run.

### 4.6 Corrections to earlier documents

Proposed rows for `docs/issues/doc-corrections.md`. Each was read at the address given.

| Document | It says | Read here |
|---|---|---|
| `docs/skills.md`, Spell slot table | slot 2 (run) is reached through Creature slot 17, "which Creature_run and Player_run call" | `Creature_run` makes the call for non-players only (top of 0x112948). A player's spells are run from `Player_updateCast` 0x1a3f70, called at 0x1ac6a8 after the action-state switch and only while hit points are above 0 |
| `docs/skills.md`, Skill +0x08 | "What tests 7 and 8 was not looked for" | The kind is copied into the ability record (+0x25) by `hud_onAssignSpell` 0x1de61c. Kind 7: `Player_run` calls `Player_castSkill` directly (0x1a7048, 0x1aac60). Kind 8: tested at 0x1a7034–0x1a7058, the record is kept at player +0x484 (store at 0x1a709c) and consumed by the ranged release, whose two sites call `Player_castSkill` at 0x1a837c and 0x1a9174 |
| `docs/skills.md`, "How a cast happens" | cost must be available; cast at the cast point | a kind-1 skill needs half its cost to start (0x1a6f84); the cast fires when the cast animation's blend weight reaches 1.0, or 0.5 in a net game (0x1ab6f4–0x1ab7dc) |
| `docs/skills.md`, statistics | tier 1 for players, tier 2 for everything else | true only where the code calls slots 11–13. Root, ConvertEnemy, ConvertUndead and HolyShield call slot 10; ShockOfFire's direct damage calls slot 8 |
| `docs/skills.md`, id table, 46 | cast creates "Projectile@0x50e5a0 (0x1c8)" | table 0x50e5a0 is `MissileWeapon`; the cast builds plain `MissileWeapon` objects (0x2d9fc4). `MultiFireProjectile` is table 0x519128, 0x78 bytes, built only by MaleDarkElf (0x25cab4) |
| `docs/skills.md`, opening | "constructors and statistics functions of eight skill classes (ids 3, 25, 27–30, 60, 61; 0x16a98c–0x16ac74)" | those functions serve ids 25 and 27–30. Blunt and Slashing are constructed inline in the static initialiser (0x16b2cc, 0x16b35c) and use the base statistics function |
| `docs/skills.md`, cast path | copy-castable ids "leave no trace" | `SpellCyclone_ctor` writes the animation clip header before its copy test (S1) |
| `docs/skills.md`, (a) unguarded list | 0x2d19d8 "posts a player notice"; GiantGrowth 0x3093a8 / 0x309640 unguarded; `SpellResurrect_run` 0x312e10 / 0x312ea4 use the caster's index | 0x2d19d8 is the `player_voice` call; GiantGrowth is guarded one level up, in cast (0x308fc0 returns for a non-player); the two Resurrect reads are of the target player |
| `docs/skills.md`, player record +0x4c20 | "written 1.0 / 0.75 × by GiantGrowth and Resurrect" | GiantGrowth writes max(1, 0.75 × scale); Resurrect writes 0.5 (0x312a28). They overwrite each other |
| `docs/skills.md`, (b) item 7 | `isNearView(940, pos)` in `StaticFire_run` | the constant is 941.0 (0x446b4000) |
| `docs/skills.md` and `docs/monsters.md` §6 | Goblin uses FrostStorm for statistics only | Goblin casts it through slot 2 (in 0x26b27c) |
| `docs/skills.md`, helpers list | LifeTap helper 0x2f8e78 among the functions the damage and player code call | its callers are the death branches of `Creature_processDamage` (0x111f40) and, in PvP mode A, `Player_processDamage` (0x1b3614); it is not called from melee code |
| `docs/skills.md`, projectile pattern | effects are "ordinary GameObjects (slot 4 run, 5 draw, 6 touched)" in the DiseaseBolt pattern | Shock and Darkness call `GameObject_ctor` directly (0x2c4050, 0x2cf4d8), not `Projectile_ctor`, do their own hit tests in run, and have an empty slot 6 |
| `docs/skills.md`, monster cast | monsters cast then attach to the target | for Healing the monster passes the wounded ally as the *caster* argument; Orc then attaches the spell to itself (0x2a2998) |
| `docs/player.md`, ability record +0x25 and object +0x480 | "8 toggle"; +0x480 kinds 1/2/3/5/6 are the special arrows | kind 8 means "fire through the ranged state" via +0x484; +0x480 is set only by the older inline ability ids (0x1a74f8–0x1a7544) |
| `docs/creatures.md`, attached-spell list | spell: "caster at +0x18, skill id at +0x1c" | that is the layout of `SpellTag` only (0x11a788); a `Spell` has the layout in `docs/skills.md` |
| `docs/monsters.md` §1.2 / `docs/skills.md` | monsters pass Creature slot 35 (level scale × 0.3) as the skill level | true for slot-2 casts; the arrow constructors are given `(int)g_levelMonsterLevel` unscaled (0x25c7d8, 0x2a7274) |

`docs/gameplay.md` §4 ("shards every 10 frames, damage every 30") is confirmed for
FrostStorm; the section adds that each damage tick is half untyped and half cold and that
each shard costs a shared draw.

### 4.7 Where the next pass should start

1. Read the item tables for type-0x29 entries; that closes the "weapon-effect cast" question
   for all 34 ids at once.
2. Read the animation files named in sections 38, 41, 49, 51 and 68 for length, event times
   and root motion, and turn the formulas into frame counts.
3. Re-derive every "simulated" count under the console's arithmetic (§1.8 gives the pattern
   and the cases already checked).
4. Document the take-damage functions' handling of the knock and type bits the skills pass.
5. Trace the reader of the shared clip slot for S1 a second time and decide on the patch.
6. Transcribe the rest of `Player_run` state 2 and state 5 (ability acceptance conditions,
   the older non-skill branch), which §1.3 summarises but does not complete.
