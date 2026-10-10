# Skills 69–101: implementation specification

Scope: the 33 skill ids 69–101 of Champions: Return to Arms (SLUS-209.73 v2.00), written so
that the rules can be re-implemented without the machine code. It builds on
`docs/skills.md` (class layouts, slot meanings, the id table), `docs/gameplay.md` (the
damage function), `docs/creatures.md`, `docs/player.md`, `docs/engine.md`,
`docs/data-tables.md` and `docs/objects.md`, and does not repeat them.

Everything was read from the executable — the decompile, checked against the disassembly
wherever a branch, an argument register or a constant mattered. **Nothing was run.**
A statement without a marker is **Observed** at the address given for the function it sits
under; **Inferred** and **Unknown** are marked. Numbers in formulas are the stored
constants; a hexadecimal value in square brackets is the bit pattern of a single-precision
constant.

## Where each id is

| Id | Name | Section | State |
|---|---|---|---|
| 69 | retribution | [69](#69--retribution-retribution) | full |
| 70 | unspokenword | [70](#70--unspoken-word-unspokenword) | full |
| 71, 73, 74, 79, 92, 93 | berserkerrage, axebandolier, lightquiver, throwing, battlemage, penetratingarrows | [passives](#the-six-passives-71-73-74-79-92-93) | full (helpers) |
| 72, 75 | summonaxe, summonarrows | [72 / 75](#72--summon-axe-summonaxe-and-75--summon-arrows-summonarrows) | part |
| 76, 77, 78 | roar, battlecry, bloodlust | [76–78](#76--roar-77--battle-cry-78--blood-lust-roar-battlecry-bloodlust) | full |
| 80, 100 | pusstorm, lightningstrike | [100 / 80](#100--lightning-strike-lightningstrike-and-80--pus-storm-pusstorm) | full |
| 81–86 | berserkercriticalhit, berserkerriposte, berserkerdodge, berserkercyclone, shamanroot, shamanhealing | [81–86](#ids-8186-the-berserker-and-shaman-variants-of-six-shared-classes) | part |
| 87 | tagarsinsects | [87](#87--tagars-insects-tagarsinsects) | full |
| 88 | drowsy | [88](#88--drowsy-drowsy) | full |
| 89 | poisonbolt | [89](#89--poison-bolt-poisonbolt) | full |
| 90 | summonbadger | [90](#90--summon-badger-summonbadger) | full |
| 91 | raisearmy | [91](#91--raise-army-raisearmy) | full |
| 94 | spiritshield | [94](#94--spirit-shield-spiritshield) | full |
| 95 | waveofflame | [95](#95--wave-of-flame-waveofflame) | full |
| 96 | frostarmor | [96](#96--frost-armor-frostarmor) | full |
| 97 | diseaseblade | [97](#97--disease-blade-diseaseblade) | full |
| 98, 99 | fireaxe, coldaxe | [98 / 99](#98--fire-axe-fireaxe-and-99--cold-axe-coldaxe) | part |
| 101 | coneofshock | [101](#101--cone-of-shock-coneofshock) | full |

The closing table says exactly what "full" and "part" leave out.

## Shared machinery

What every section below relies on. Each item was read for this document at the address
given; where an earlier document already says the same, that document is named.

### Notation

- A **frame** is one simulated tick; there are 60 per second. Spell and object clocks are
  single-precision sums of the constant 0x3c888888 (0.016666666), not frame counts, unless
  the text says `g_simFrame` (0x44fdcc).
- Angles are 16-bit, 65536 to the turn. `cos16` / `sin16` are 0x166630 / 0x1666e0; a heading
  `a` points along (cos16(a), sin16(a)). `atan2_16(y, x)` is 0x166798:
  `(s16)trunc(atan2f(y, x) × 10430.378)`.
- `trunc` is the float-to-integer instruction (toward zero); `round(x)` is
  `trunc(x + 0.5)` for x ≥ 0 and `trunc(x − 0.5)` below — always written out in the code.
- **Flash quads**: every creature has two colour quads of four s16 at +0x90 and +0x98
  ("quad 1", "quad 2"); `Creature_run` moves each element 2 toward 0 per frame and drawing
  uses them (`docs/creatures.md`). Skills write them as a visible cue. They are object state
  written from simulation code, the same on every machine, and nothing in this range reads
  them back. They are listed because they are writes to the target, and are presentation.
- `getStat(n, L)`, `stat(n, L, caster, cap)`, `statRange(spread, n, L)`: see the next
  heading.

### Statistic lookup (Skill slots 8, 10, 11, 12, 14, 15)

A Skill holds two tables of five statistics (`docs/skills.md`): tier 1 {first level, base,
step} at +0x0e / +0x18 / +0x24 and tier 2 at +0x38 / +0x42 / +0x4c, where a tier-2 first
level of −1 means "this statistic has no tier 2".

```
value(first, base, step, L):                       # 0x3c85fc and both arms of 0x3c8690
    if L == 0 or L < first: return 0
    f = (float)base + step * (float)(L - first)    # single precision
    return round(f)

getStat(n, L)            = value(tier 1 of n, L)                          # slot 10, 0x3c85fc
getStatTier2(n, L, cap):                                                  # slot 11, 0x3c8690
    if L == 0: return 0
    if cap > 0: L = min(L, cap)
    return value(tier 2 of n, L) if tier 2 exists for n else value(tier 1 of n, L)
stat(n, L, caster, cap)  = getStat(n, L) if caster is a player            # slot 12, 0x3c87f0
                           else getStatTier2(n, L, cap)                   # also for a null caster
statRange(spread, n, L):                                                  # slot 8, 0x3c82e4,
    v  = getStat(n, L)                                                    # with "randomise" 0
    lo = max(1, round(v - v * spread)) ; hi = max(1, round(v + v * spread))
adjustLevel(L, k)        = L                                              # slot 14, 0x3c88dc
manaFromStat4(L, k)      = (float)getStat(4, L)                           # slot 15, 0x3c88e4
```

Consequences used throughout:

- `getStat` and `statRange` are tier 1 **whoever the caster is**. A section that says "slot
  10" or "slot 8" means a monster caster gets the player numbers there.
- The `cap` clamps the level only on the tier-2 path. Players are never clamped by it; the
  skill menu limits a rank to 20 (`docs/data-tables.md` §4.6).
- A statistic whose first level was never written has first level 0, base 0, step 0 (the
  objects are in zero-initialised memory) and evaluates to 0.
- Most cast functions start by passing the level through slot 14 with some constant
  (1, 2, 5, 10, 14, 20); slot 14 returns the level unchanged, so the constant is dead.
  (Critical Hit and Cyclone do not make the call.)
- The "±20 %" spread constant is 0x3e4ccccc (0.19999999), not 0.2. Where the code does its
  own spread for non-player casters it **truncates** (`trunc(v ± v × 0.19999999)`) instead
  of rounding and has no floor of 1.
- With "randomise" set, slot 8 makes two shared draws per bound; no caller in this range
  sets it.

The tables in each section list the stored step (decimal, and bits where it is not a short
binary fraction) and the values for ranks 1–20, computed with single-precision arithmetic
for both round-to-nearest and truncating multiplication; the two agree for every statistic
and rank in this range (`tools/dump_tables.py --table skills` gives the stored numbers).

### How a cast arrives, and what `pos` and `facing` are

Every cast function has the signature `cast(skill, level, caster, pos*, facing)` and returns
a Spell or 0.

| Route | Level | `pos` | `facing` | What happens to the returned Spell |
|---|---|---|---|---|
| Player — `Player_castSkill` 0x1a42b8 | the player's rank (virtual slot 39 → `player_getSkillRank`) | midpoint of body-model attach points 0 and 1; if its height differs from the feet by more than 58, feet + 58 | heading to the first entry of `world_collectObjectsInArc(340, 20°, 0, player position, player facing, no filter)` that the player's slot 20 calls an enemy, computed as `(s16)(0x41c2 − atan2_16(dx, dy))`; the player's own facing if there is none | attached to the player (`creature_addSpell`); for kind 1 also linked at player +0x588; destroyed at once for the prediction copy |
| Monster | usually virtual slot 35 = trunc(level-wide monster level × 0.29999998) (0x118c50); Cazic's Frost Armor passes the whole monster level | chosen by the monster (itself, its target, an ally) | its own facing | the monster attaches it where it wants, or drops it |
| Weapon proc, `damage_apply` type 0x29 | from the item | attacker position | attacker facing | dropped. No item descriptor can produce type 0x29 (`docs/data-tables.md` §1.3), so this route is dead unless an item is built in code |

Before the cast `Player_castSkill` requires recast counter ≤ 0, `canUse`, and (in
`Player_run`) mana ≥ `manaCost(rank)`; after it, recast counter = skill +0x0c (30 for every
id here) and mana −= cost. It does not look at what the cast returned, so a cast that fails
to allocate still costs mana.

Attached spells are run once per frame through Creature virtual slot 17 (0x11a868), which
calls each spell's slot 2 with `(pos*, facing = creature +0x38)`:

- for a non-player creature, at the very top of `Creature_run` (0x112948), with
  `pos` = its position raised by half its height (+0x20 × 0.5);
- for a player, from `Player_updateCast` (0x1a3f70) late in `Player_run`, with `pos` = the
  same clamped hand midpoint as above.

A spell destroys itself by calling its own slot 1 with argument 3. `Creature_dtor` destroys
whatever is still attached.

### World queries

All three start from `world_collectObjectsInBox(min, max, out, n)` (0x14a928,
`docs/objects.md`): objects of the main grid whose radius reaches into the box in x/y and
whose height span reaches it in z, never the prediction copy, at most n − 1 results,
**in cell order then list order**. That order is simulation state (it follows the order of
movement calls) and everything below inherits it.

`world_collectInSphere(R, centre, _, list)` — 0x14ab80. Box of half-size R around the
centre (at most 511 objects); keeps an object when its flags & 0xd == 0 (not flag 0x1
"not solid", not 0x4, not 0x8 "dead") and its centre is closer than R + its radius in 3-D.
Any kind of object qualifies, props included. Each kept object is pushed at the head of
`list`, so the list is in **reverse** box order; callers that copy it into a second list by
pushing again end up back in box order (noted per skill).

`world_collectObjectsInArc(R, arcDeg, halfWidth, centre, facing, list, owner)` — 0x1614f0.
Box of half-size R (at most 511). An object is kept when all hold:

- it is a creature (flag 0x20) with flags & 0xd == 0;
- `owner` is null or `owner`'s virtual slot 20 ("is enemy") returns non-zero for it;
- `arcDeg` is −1, or the object is on the inner side of both edges of the wedge: with
  h = round(arcDeg × 0.5 × 182.04443) as a 16-bit angle,
  dot(dir16(facing + h − 0x4000), o − centre) ≥ 0 and dot(dir16(facing − h + 0x4000),
  o − centre) ≥ 0 (2-D);
- `halfWidth` is 0, or |dot(dir16(facing + 0x4000), o − centre)| ≤ halfWidth;
- dot(dir16(facing), o − centre) > 0.

There is **no distance test beyond the box**: the shape is a wedge clipped by a square.
Insertion: walk the list from its head; at the first entry whose squared 2-D distance is ≤
the new object's, insert the new object *after* that entry; if there is none, push it at
the head. The head is therefore always the nearest object (the earlier one of two equals),
but the rest is **not sorted**: every later, farther object lands directly behind the
current head. For box order 10, 5, 7, 20, 3 (distances) the list is 3, 5, 20, 7, 10. Skills
that take "the first valid entry" or "the first N entries" depend on this exact order.

"Is enemy" — Creature slot 20: `Creature_isEnemy` 0x119328 for monsters (other is a
creature or player, not dead, not the prediction copy, without creature flags 0x4000000
and 0x800, and its team byte from slot 37 differs; returns 4 for a "priority" target, else
1) and `Player_isEnemy` 0x1b5ea8 for players (other is a live creature without object flag
0x1000000 and without those two creature flags; a player only in PvP mode A on another
team; a charmed monster only in PvP mode A on another team).

### Spell base and the marker class

Spell layout and slots are in `docs/skills.md`. The base constructor is inlined in every
subclass constructor and makes **one draw from the shared generator** (state × 0x19660d +
0x3c6ef35f; the spell's own generator state at +0x10 is the new shared state >> 16).
`Spell_rand` (0x16a964) steps the spell's own state with the same constants and returns
state >> 16, a 16-bit value.

A recurring idiom, called "3 per try" in the draw tables: draw x, y, z as
`(r / 65536) × 2 − 1` and repeat while `1.0 < x² + y² + z²` (a uniform point in the unit
sphere). Where a spell's own generator also decides something that matters, these loops
have to be reproduced draw for draw, and the comparison is in single precision.

`SpellTag` (table 0x51ba90, 0x20 bytes) is a marker with no behaviour: Spell base, then
+0x18 a creature pointer and +0x1c an integer. `creature_findSpell(creature, id, who)`
(0x11a788) finds a `SpellTag` on `creature` with +0x1c == id and +0x18 == who. Tagar's
Insects uses id 0x57.

### Things most casts create that are presentation

- **`LightEffect`** (0xbc bytes, constructor 0x201bd8, run 0x1ee050): a fading dynamic light.
  It is a GameObject, so constructing one makes **one shared draw** (skipped when the pool
  has no block) and it occupies a pool block until its end frame. It changes nothing else.
  "Following X" means it holds a handle to X and copies its position.
- **Sounds** (`sound_playAtPos` 0x214428, `sound_playOnObject` 0x214230) and **particles**
  (`particle_spawn` 0x18f3f8, which silently does nothing when its pool is empty).
- **Particle groups** (`particleGroup_create` 0x18e880): a handle into a 16-entry table,
  taken in simulation code.
- Embedded **light records** inside some spells and objects.

Names of sounds are given once per section because they are how the effect is recognised;
several are borrowed from other skills, which is marked (sic).

### Calling the damage function

`damage_apply(min, max, victim, attacker, attack, _, _, flags, descriptor, noCrit)` is
0x1e8230, specified in `docs/gameplay.md` §2 with every draw it makes. Every direct damage
call in this range passes attack = 100000 (so the armour comparison cannot make it miss),
the two unused arguments as 0 and noCrit = 0 unless stated. A "descriptor slot
{type, v1, v2, v3}" is one of the four 8-byte effect entries; where a section says
"descriptor slot 0 = …" the other three are empty (type −1) and the rest of the record is
the same all-empty default the damage function builds for itself.

Flag bits passed by skills in this range, with what is known of them:

| Bit | Known meaning | Where from |
|---|---|---|
| 0x40 | cannot be blocked; ignores Spirit Shield | `docs/gameplay.md` §2.4 |
| 0x100, 0x20, 0x400, 0x800, 0x10000 | passed through to take-damage; 0x100 selects the lightning colour class | same |
| 0x40000 / 0x80000 / 0x100000 / 0x200000 | knock-back speed 100 / 150 / 200 / 312.5 when the hit kills | `docs/creatures.md`, "Pending damage" |
| 0x1000000 | no floating number | `docs/gameplay.md` |
| 0x2000000 | passed through (the damage function sets the same bit itself for an "undead kill" proc) | same |
| 0x4000000 | `Player_processDamage` does not take its "shrug off" exit for this hit (0x1b2cc0, decompile line 277) | read here |
| 0x40000000 | no critical-hit bonus from the attacker's skills | `docs/gameplay.md` |

### Projectile step

`obj_moveAndCollide(obj, velocity)` — 0x1509f8, used by Poison Bolt and the thrown axes:

```
position += velocity * (1/60) ; obj_updateGridCell
result = 0
if terrain_height(obj.radius, world, position) > position.z:        # below the ground
    result |= 1
    step back along the velocity in tenths of a frame (0.1, 0.2 … below 2.0) until above ground
    if obj.+0x50 == 0 and water_test(12, world, position):
        obj.+0x50 = 1 ; one draw from the OBJECT'S OWN generator (value unused)
        splash sound ; water_disturb(700, 24, …)
list = world_collectObjectsInBox(x,y ± radius; z ± height (+0x20); at most 255)
for o in list:
    skip o with object flags 0x1, 0x200 or 0x20000000, the object itself, and its owner (+0x4c)
    if the height spans overlap and dist2D < obj.radius + o.radius:
        result |= 2
        o.touched(obj) ; obj.touched(o)                             # virtual slot 6 of each
return result
```

### Floating point

Clock comparisons (`tEnd <= t`, `clock < 0.5`), the unit-sphere rejection test and the
rounding of statistics are single-precision operations in the order written. The console's
floating-point unit does not round the way an IEEE host does by default; that is a general
property of the machine and not something this executable states, so it is noted here once
and not repeated. Where a frame number is quoted for a float threshold (for instance
"run 31" for `clock >= 0.5`) it was computed for both truncating and round-to-nearest
addition and came out the same.

## 69 — Retribution (`retribution`)

**Fully specified.**

### Identity

| | |
|---|---|
| Skill class / table / object | `SkillRetribution` / 0x51bfa0 / 0x6e3078 |
| Kind, flags, recast | 0, 0, 30 |
| Tree | cleric (class 1): base level 25, needs skill 39 |
| Other casters | none found |
| Creates | `SpellRetribution` (0x5c bytes, table 0x51bf70) on the caster |

### Statistics (slot 10, tier 1, in every lookup)

| Stat | Meaning | Formula | Ranks 1–20 |
|---|---|---|---|
| 0 | duration, seconds | 4 + 0.333004 × (L−1) [0x3eaa7f80] | 4 4 5 5 5 6 6 6 7 7 7 8 8 8 9 9 9 10 10 10 |
| 1 | percent of damage dealt that is returned as hit points | 20 + 2.999987 × (L−1) [0x403fffc9] | 20, 23 … 77 |
| 4 | mana | 75 + 7.999959 × (L−1) [0x40ffffaa] | 75, 83 … 227 |

### Cost and limits

Mana = statistic 4. canUse (0x3142bc): the caster must not already carry a
`SpellRetribution`.

### Behaviour

Cast (0x3142f0): `pool_new(0x5c)`, construct, return the spell.

Constructor (0x314488): Spell base (shared draw 1); a light record at +0x18 placed 20 above
the caster; sound `spel_bw_stunstrike.anm` (sic); a particle group handle at +0x54
(`particleGroup_create`). The clock at +0x58 is never written by the constructor — it is 0
because `pool_new` zero-fills.

Run (0x314618), once per frame: 49 particles from the owner's model vertices
(`fx_emitFromModelVerts`, cosmetic generator); light flicker and position (the position
slot 17 hands in); clock += 1/60; if `(float)getStat(0, level) < clock` the spell destroys
itself. The destructor (0x3d1828) releases the light; it does not release the particle
group (Observed; whether the group pool recycles it by itself is Unknown — presentation
either way).

The heal — `SpellRetribution_healOwner` 0x314790. `damage_apply` calls it near its end
(0x1e8230, decompile lines 1258–1269; `docs/gameplay.md` §2.5 step 29) when the
**attacker is a player** and carries the spell, with `dmg` = the amount just handed to the
victim's take-damage:

```
owner flash: +0x90 = 0x46, +0x92 = 0x80, +0x94 = 0x4b, +0x96 = 0x3f,
             +0x9a = 0x80, +0x9c = 0x4b, +0x9e = 0x3f        # +0x98 is left alone
frac = getStat(1, level) * 0.01
if owner is a player:
    if record.hp <= 0: return 0
    record.hp = min(record.hp + dmg * frac, record.maxHp)
return frac
```

`damage_apply` uses the returned fraction only for a second floating number
(`trunc(dmg × frac + 0.5)`, a `FlyingText` of kind 2 — one more shared draw when it is
created, under the conditions of step 30).

What counts as "damage dealt": every `damage_apply` call that reaches its end with this
player as the attacker — melee, missiles (the owner is credited), and every skill in this
document that passes the player as attacker. A hit that was missed, blocked or absorbed
returned earlier and heals nothing; a hit flagged 0x800000 arrives here with `dmg` = 0.
In PvP mode A the amount has already been halved for a player victim.

### Random draws

Constructor: shared 1. Nothing else of its own; the spell's own generator is never used.
The second floating number costs one shared draw per qualifying hit.

### Presentation only

Sound, the light, the model-vertex particles, the green flash on each heal.

### Per-machine state

- Player-record access is behind the is-player test in the heal (0x314790, decompile line
  26) and the call site tests the attacker first.
- `fx_emitFromModelVerts` uses only the cosmetic generator.
- A non-player owner would get the flash and the second number but no hit points.

### Functions read

0x3141f4, 0x314260, 0x3142bc, 0x3142f0, 0x314454, 0x314488, 0x314618, 0x314790, 0x3d1828,
call site in 0x1e8230. Not read: describeRank 0x314390.

## 70 — Unspoken Word (`unspokenword`)

**Fully specified.**

### Identity

| | |
|---|---|
| Skill class / table / object | `SkillUnspokenWord` / 0x51ae88 / 0x6e30e0 |
| Kind, flags, recast | 0, 0, 30 |
| Tree | cleric (class 1): base level 25, needs skill 31 |
| Other casters | none found |
| Creates | `SpellUnspokenWord` (0x38 bytes, table 0x51af10) on the caster; one `LightEffect`; two trail handles (presentation) |

### Statistics (slot 10 / slot 8, tier 1, in every lookup)

| Stat | Meaning | Formula | Ranks 1–20 |
|---|---|---|---|
| 0 | damage before the ±20 % spread | 20 + 4.999982 × (L−1) [0x409fffda] | 20, 25 … 115 |
| 1 | final ring radius in 12-unit steps | 7 + 0.500003 × (L−1) [0x3f000032] | 7 8 8 9 9 10 10 11 11 12 12 13 13 14 14 15 15 16 16 17 |
| 2 | percent chance to stun | 25 + 2.0009518 × (L−1) [0x40000f98] | 25, 27 … 63 |
| 3 | stun, seconds | 3 + 0.33399698 × (L−1) [0x3eab01a7] | 3 3 4 4 4 5 5 5 6 6 6 7 7 7 8 8 8 9 9 9 |
| 4 | mana | 51 + 8.000916 × (L−1) [0x410003c0] | 51, 59 … 203 |

### Cost and limits

Mana = statistic 4. Base canUse (always allowed).

### Behaviour

Cast (0x2fd030): caster flash both quads = {0x40, 0x40, 0x80, 0x80}; sound
`spel_he_unspoken.anm` at `pos`; `LightEffect` at `pos` + 36 following the caster (shared
draw); `pool_new(0x38)`, construct, return the spell.

Constructor (0x2fd368): Spell base (shared draw); +0x18 = the caster (a plain pointer);
start frame (+0x2c) = `g_simFrame`; centre (+0x20) = caster position, fixed from then on;
two trails; candidate list (+0x1c) = every **creature** with flags & 0xd == 0 returned by
`world_collectInSphere(getStat(1) × 12 × 1.5, centre)`, in box-query order.

Run (0x2fd5d4), once per frame:

```
age = g_simFrame - start
if age >= 30: destroy the spell; return
r = (age / 30.0) * getStat(1, level) * 12.0
trails; and when age/30 > 0.5: particles        # own generator, see the draw table
hit(r)
```

`hit(r)` (0x2fddf0, `SpellUnspokenWord_hitRing` in the new symbol file), for each candidate
in list order:

```
if object gone: drop; continue
if dist2D(centre, o) - o.radius > r: continue
if o.flags & 9 or not caster.isEnemy(o): drop; continue
(lo, hi) = statRange(0.2, stat 0, level)
flags = 0x40940 below level 6; 0x80940 for 6-10; 0x2100940 for 11-15; 0x2200940 from 16
damage_apply(lo, hi, o, caster, 100000, 0, 0, flags, no descriptor, 0)
if o.hp (+0x228) >= 0.0:
    d = Spell_rand()
    if (d % 100) + 1 > 100 - getStat(2, level):
        o.stun(frames = getStat(3, level) * 60, flash = 1)      # Creature virtual slot 30
drop
```

- The ring reaches its full radius on the last frame (age 29: 96.7 % of it); the candidate
  sphere is half as large again, and a creature counts as reached when the ring touches its
  own radius.
- Each creature is hit once. The stun roll is made only if the hit left it with hit points
  at or above zero — it uses the object's hit-point field, which for monsters is reduced by
  take-damage at once.
- Flags: 0x40 unblockable; 0x100 and 0x800 are passed on (0x800 is the mark `damage_apply`
  itself sets for a "killing proc"); the high bits pick the knock-back speed of a killing
  blow (0x40000 → 100, 0x80000 → 150, 0x100000 → 200, 0x200000 → 312.5) and 0x2000000 is
  passed on to take-damage.

### Random draws

| When | Generator | Count |
|---|---|---|
| cast | shared | 1 (`LightEffect`) + 1 (Spell) |
| frames with age/30 > 0.5 (ages 16–29), before the hits | own | n = getStat(1) × 6 particles, then n / 2 more, each 3 per try until inside the unit sphere |
| each creature hit that survives | own | 1 — **the stun roll** |
| each creature hit | shared | those of `damage_apply` |

Stun rolls on ages 16–29 come after that frame's particle draws; the particle count and the
rejection loop therefore have to be reproduced.

### Presentation only

Sound, light, the two spiralling trails (their length and colour fade over the second half),
the particles.

### Per-machine state

None found. All statistics are tier 1 whoever casts; no player-record access.

### Functions read

0x2fcf30, 0x2fcf9c, 0x2fd030, 0x2fd334, 0x2fd368, 0x2fd550, 0x2fd5d4, 0x2fddf0.
Not read: describeRank 0x2fd1dc; the three trail helpers (0x1911a8, 0x191100, 0x1918a0).

## The six passives: 71, 73, 74, 79, 92, 93

All six have kind 3 (never cast), the base canUse / cast / manaCost, no spell and no object.
Each is a statistic table plus one or two small helper functions that code in the player
and object areas calls with the player's rank from `player_getSkillRank` (0x1bf330). All
lookups are slot 10 (tier 1). **A rank of 0 gives the value 0** (the slot-10 rule), which
matters for 92.

**All fully specified** as far as their helpers go; the callers were read only around the
call.

| Id | Name | Class / table / object | Tree | Stat 0 | Stat 1 |
|---|---|---|---|---|---|
| 71 | `berserkerrage` | `SkillBerserkerRage` / 0x51af40 / 0x6e3148 | berserker, base level 15, needs skill 83 | 10 + 3.000959 × (L−1) [0x40400fb6] → 10, 13 … 67 | 30 + 2.000989 × (L−1) [0x40001034] → 30, 32 … 68 |
| 73 | `axebandolier` | `SkillAxeBandolier` / 0x51b080 / 0x6e3218 | berserker, base level 20, needs skill 98 | 20 + 3 × (L−1) → 20 … 77 | — |
| 74 | `lightquiver` | `SkillLightQuiver` / 0x51b108 / 0x6e3280 | ranger, base level 21, needs skill 45 | 15 + 3 × (L−1) → 15 … 72 | — |
| 79 | `throwing` | `SkillThrowing` / 0x51b470 / 0x6e3488 | berserker, base level 1, no prerequisite | 15 + 5.0079546 × (L−1) [0x40a0412a] → 15, 20 … 110 | — |
| 92 | `battlemage` | `SkillBattleMage` / 0x51c028 / 0x6e39d0 | wizard, base level 13, needs the passive with mask 0x40 | 80 + 4.0019407 × (L−1) [0x40800fe6] → 80, 84 … 156 | — |
| 93 | `penetratingarrows` | `SkillPenetratingArrows` / 0x51c0b0 / 0x6e3a38 | ranger, base level 25, needs skill 74 | 45 + 2.0019999 × (L−1) [0x400020c4] → 45, 47 … 83 | 35 + 2.001992 × (L−1) [0x400020a3] → 35, 37 … 73 |

### 71 Berserker Rage

Two helpers, same shape (0x2fe324 and 0x2fe49c; `SkillBerserkerRage_swingFactor` and
`_damageFactor` in the new symbol file), arguments (skill, rank, player record, frames):

```
if record.hp / record.maxHp > 0.5: return 1.0
t = min(1.0, frames * (1/60))
[swingFactor only: flash on the record's player object, if any:
   +0x90 = trunc(t*96), +0x92 = 0, +0x94 = 0, +0x96 = trunc(t*15),
   +0x98 = trunc(t*64), +0x9a = trunc(t*16), +0x9c = trunc(t*16), +0x9e = 0]
return 1.0 + getStat(0 for swing / 1 for damage, rank) * 0.01 * t
```

- Swing: `Player_run`, melee-swing state, for class 5 with rank ≥ 1 (0x1aa158; decompile
  lines 1617–1627): animation speed = speed × swingFactor(frames = `g_simFrame` − player
  +0x458) + the item haste term. With rank 0 the haste term is simply added.
- Damage: `Player_recalcDamage` (0x1b79e0; lines 308–328): for class 5 in action state 1,
  and only while `g_simFrame` − player +0x45c < 27, factor = damageFactor(frames =
  `g_simFrame` − player +0x458); it is used if above 1. The final multiplier is the larger
  of this and the Blood Lust factor (id 78), applied to minimum damage, maximum damage and
  attack rating with truncation.

So below half health a berserker's swings ramp, over the first second of an attack chain
(+0x458 is the chain's frame stamp, `docs/player.md`), to +10…67 % speed and +30…68 %
damage. The record's hit points are the lockstep value; the prediction loop restores them.

### 73 Axe Bandolier and 74 Light Quiver

`…_getStat0Complement` (0x2ff2e4, 0x2ff4b4): max(0, 1 − getStat(0, rank) × 0.01).
Only caller `player_itemWeight` (0x1b6338): weight = `item_getWeight(item)` × f, where

- for an item whose definition has equipment slot 8 (ammunition): f = 0.25 if the class
  passive with mask 0x10000 has a rank (the code applies its 0.5 twice), and × the Light
  Quiver complement if rank(74) ≠ 0;
- otherwise, for an item with flag bit 42 (thrown axes): f = the Axe Bandolier complement if
  rank(73) ≠ 0;
- otherwise f = 1.

Ammunition weighs 85 … 28 % with Light Quiver, thrown axes 80 … 23 % with Axe Bandolier.
The weight feeds the carried load (record +0x120, `player_recalcLoad`).

### 79 Throwing

`SkillThrowing_getStat0Fraction` (0x304b54): getStat(0, rank) × 0.01. Only caller
`Player_recalcDamage` (0x1b7410–0x1b74c0), when the weapon's animation class is 6 (thrown):

```
f    = fraction
min += round(min * f)
max += round(min * f)          # sic: the already-raised minimum, not the maximum
```

(`round` = add 0.5 and truncate.) Observed at 0x1b7478–0x1b7488: the register multiplied the
second time is the new minimum. The Archery branch just above it (id 48) multiplies the
maximum by the factor as one would expect.

### 92 Battle Mage

`SkillBattleMage_getStat0Fraction` (0x314a78): getStat(0, rank) × 0.01. Only caller
`Player_recalcDamage` (0x1b7750; lines 221–259), for class 4 (wizard) only:

```
eligible = false
if weapon animation class == 0 and item flag bit 36 is clear
   and definition +0x20 (damage-type word) is 8 or 4:  eligible = true
if item flag bit 43 is set:                             eligible = true
if eligible: min = round(min * f) ; max = round(max * f)
```

The range is **replaced** by the fraction of itself: 80 % at rank 1, 100 % at rank 6, 156 %
at rank 20 — and 0 at rank 0, because the fraction is then 0. Whether a wizard without the
skill can equip an eligible weapon at all is decided elsewhere (Unknown here).

### 93 Penetrating Arrows

`SkillPenetratingArrows_getStats01Fraction` (0x314c88): the two statistics × 0.01. Only
caller `MissileWeapon_onTouch` (0x152a18, lines 112–131 and 327–351), each time a missile
whose owner is a player and whose kind word (+0xd0) is 0 or 3 touches something it may hit:

```
(f0, f1) = fractions at rank(93)
r1, r2 = two SHARED draws                       # made at every rank, including 0
unblockable = (r1 / 65536 <= f0)                # adds damage flag 0x40 to this hit
pierce      = (r2 / 65536 <= f1)
if not pierce: clear the missile's list of creatures already hit (+0x124)
... damage_apply ...
if pierce and the hit set the missile's "has hit" byte:
    add the victim to that list and clear the byte          # the arrow flies on
```

A touched object already in the list is ignored. At rank 0 both tests pass only when the
draw is exactly 0 (1 in 65536).

### Per-machine state (all six)

None of the helpers reads per-machine state. 71's swing helper writes the flash colour of
the record's current object — during prediction that is the copy. The callers'
own hazards (the alive-player list in `Player_run`, G19) are theirs.

### Functions read

0x2fe188, 0x2fe1fc, 0x2fe23c, 0x2fe324, 0x2fe49c; 0x2ff1a4, 0x2ff218, 0x2ff2e4; 0x2ff374,
0x2ff3e8, 0x2ff4b4; 0x304a10, 0x304a84, 0x304b54; 0x314934, 0x3149a8, 0x314a78; 0x314aec,
0x314b60, 0x314c88; the call sites named above. Not read: the other describeRank functions.

## 72 — Summon Axe (`summonaxe`) and 75 — Summon Arrows (`summonarrows`)

**Partly specified.** The two skills are the same code with a different item. What they do
inside the skill files is fully read; the three inventory functions they hand the item to
(`inventory_giveItem` 0x1c1868, `inventory_equipItem` 0x1c27c0, `player_itemWeight`
0x1b6338) belong to the player and UI areas and were read only as far as noted.

### Identity

| | 72 Summon Axe | 75 Summon Arrows |
|---|---|---|
| Skill class / table / object | `SkillSummonAxe` / 0x51afc8 / 0x6e31b0 | `SkillSummonArrows` / 0x51b190 / 0x6e32e8 |
| Kind, flags, recast | 0, 0, 30 | 0, 0, 30 |
| Tree | berserker (class 5): base level 5, needs skill 79 | ranger (class 3): base level 4, needs skill 46 |
| Spell | `SpellSummonAxe` (0x20 bytes, table 0x51b050) | `SpellSummonArrows` (0x20 bytes, table 0x51b218) |
| Other casters | none found; **the constructors assume a player** | same |

### Statistics (slot 10, tier 1)

| Stat | Meaning | 72 | 75 |
|---|---|---|---|
| 0 | number of items in the stack | 10 + 5.0009446 × (L−1) [0x40a007bd] → 10, 15 … 105 | 20 + 2 × (L−1) → 20, 22 … 58 |
| 4 | mana | 26 + 6.0009847 × (L−1) [0x40c00811] → 26, 32 … 140 | 38 + 5.002966 × (L−1) [0x40a0184c] → 38, 43 … 133 |

### Cost and limits

Mana = statistic 4. canUse: 72 uses the base (always 1); 75 has its own that always
returns 1 (0x2ff5ec). The real limit is the carrying capacity test in the constructor.

### Behaviour

Cast (0x2fe644 / 0x2ff5f4): caster flash (72: both quads {0x40, 0x40, 0x80, 0x66}; 75: both
quads {0x40, 0x80, 0x40, 0x80}); sound at `pos` (`spel_vb_summonaxe.anm` /
`spel_bw_summonarrow.anm`); `LightEffect` at `pos` + 36 following the caster (shared draw);
`pool_new(0x20)`, construct, return the spell.

Constructor (0x2feb88 / 0x2ff87c), in order:

1. Spell base — shared draw.
2. start frame (+0x18) = `g_simFrame`; a particle group handle at +0x1c.
3. Build an item record (0x48 bytes) on the stack: quantity (+4) = getStat(0, level);
   modifier slots empty; then the descriptor parser `item_parseDescriptor(name, record,
   variant = −1, 0)`. With variant −1 the parser calls `item_randomizeVariant` (0x1046e0),
   which makes **one shared draw** when the item definition has more than zero visual
   variants.
   - 75: name `arrows`, nothing else.
   - 72: helper 0x2fe96c (`SkillSummonAxe_buildItem`) picks the name by level — below 5
     `sumthrowingaxe`, below 9 `sumlightthrowingaxe`, below 13 `sumnormalthrowingaxe`, below
     17 `sumwarthrowingaxe`, else `sumgreatthrowingaxe` — and then adds three modifiers, each
     in the first slot that is empty or already holds that code: {0x25 cost modifier, 1},
     {0x24 weight modifier, 10}, {0x0e required level, 5 / 9 / 13 / 17 / 21 for the five
     names}. (Codes as in `docs/startup.md`.) describeRank calls the same helper with a flag
     that makes the variant 0 instead of −1, so the menu draws nothing from the generator.
4. slot = `caster + 0x3c8` — **no is-player test**.
5. If record load (+0x120) + `player_itemWeight(slot, item)` ≤ record load limit (+0x124):
   `i = inventory_giveItem(slot, item, 1)`; `player_recalcLoad(slot)`;
   `inventory_equipItem(slot, &bag[item definition +0x1d][i], 0)`;
   `player_resetIdleAnim(slot)`.
6. Otherwise (too heavy): `player_voice(slot, 0)` (local machine only); mana =
   min(mana + manaCost(level), maximum mana); start frame = −1.

Because `Player_castSkill` subtracts the cost after the cast returns, the refund in step 6
nets to zero unless it was clipped at maximum mana.

That the quantity written in step 3 survives the parser is Inferred (the parser was not
checked for a later store to +4; nothing else uses statistic 0).

Run (0x2feddc / 0x2ffad4): if the start frame is −1, free the particle group and destroy the
spell. Otherwise emit particles for the first 30 frames
(`trunc(sin16(trunc(age × 0.03333333 × 32768)) × 50)` of them for the axe, `× 15` for the
arrows; one model sample point and one angle each from the spell's own generator) and after frame 120 free the group and destroy
the spell. The spell is decoration around a one-off inventory change.

### Random draws

| When | Generator | Count |
|---|---|---|
| cast | shared | 1 (`LightEffect`), 1 (Spell), 0 or 1 (item variant) — plus whatever `inventory_giveItem` / `inventory_equipItem` draw (not checked) |
| run, first 30 frames | own | 2 per particle; nothing else reads it |

### Per-machine state

- **Unguarded player index** in both constructors (0x2fecb8–0x2fed68, 0x2ff9b0–0x2ffa60, as
  listed in `docs/skills.md`): inventory, load, mana and equipment of record
  [caster + 0x3c8] are written for any caster. Only a player can reach the cast through the
  trees; item code 0x29, the other way in, cannot be produced by any item descriptor
  (`docs/data-tables.md` §1.3).
- The particle positions follow `net_objOrGhost(owner)` (the prediction copy on the owner's
  machine); counts and draws do not depend on it (`docs/skills.md` (b) item 4).
- `player_voice` and the equip sounds inside `inventory_equipItem` are local-slot output.
- Skill flag bit 0 is clear, so the prediction copy never runs these constructors.

### Functions read

72: 0x2fe598, 0x2fe604, 0x2fe644, 0x2fe938, 0x2fe96c, 0x2feb88, 0x2feddc, 0x3d045c.
75: 0x2ff544, 0x2ff5b0, 0x2ff5ec, 0x2ff5f4, 0x2ff848, 0x2ff87c, 0x2ffad4 (identical to
0x2feddc apart from particle constants). Also `item_randomizeVariant` 0x1046e0.
Not determined: stacking and equip rules inside the inventory functions; the item
definitions behind the five axe names (they are rows of the item table on the disc).

## 76 — Roar, 77 — Battle Cry, 78 — Blood Lust (`roar`, `battlecry`, `bloodlust`)

The three berserker shouts share one skeleton: the cast locks the player into a shout
animation that the *spell* drives; the effect starts on an animation event; being knocked out
of the animation before that event refunds half the mana.

**76 fully specified. 77 fully specified** for its own code (the swing-speed consumer is in
`Player_run`). **78 fully specified** for its gameplay; the second half of its run function
(particles, 0x303680–0x3047b0) was only scanned for writes.

### Identity

| | 76 Roar | 77 Battle Cry | 78 Blood Lust |
|---|---|---|---|
| Skill class / table / object | `SkillRoar` / 0x51b248 / 0x6e3350 | `SkillBattleCry` / 0x51b300 / 0x6e33b8 | `SkillBloodLust` / 0x51b3b8 / 0x6e3420 |
| Kind, flags, recast | 0, 0, 30 | 0, 0, 30 | 0, 0, 30 |
| Tree (berserker, class 5) | base level 3, needs skill 61 | base level 25, needs the passive with mask 0x40000 | base level 8, needs skill 76 |
| Spell | `SpellRoar` 0x50 bytes, table 0x51b2d0 | `SpellBattleCry` 0x58 bytes, table 0x51b388 | `SpellBloodLust` 0x4c bytes, table 0x51b440 |
| Other casters | none; **all three assume a player** | | |

### Statistics (slot 10 / slot 8, tier 1, in every lookup)

| Id | Stat | Meaning | Formula | Ranks 1–20 |
|---|---|---|---|---|
| 76 | 0 | wave radius in 12-unit steps | 6 + 0.251009 × (L−1) [0x3e808440] | 6 6 7 7 7 7 8 8 8 8 9 9 9 9 10 10 10 10 11 11 |
| 76 | 1 | damage before the ±20 % spread | 40 + 9.00281 × (L−1) [0x41100b82] | 40, 49 … 211 |
| 76 | 4 | mana | 16 + 3.002991 × (L−1) [0x40403101] | 16, 19 … 73 |
| 77 | 0 | percent chance to stun | 20 + 2.0009878 × (L−1) [0x4000102f] | 20, 22 … 58 |
| 77 | 1 | swing speed, percent | 125 + 3.0010078 × (L−1) [0x40401083] | 125, 128 … 182 |
| 77 | 2 | duration in seconds; also the stun length (× 19.979939 frames) | 15 + 0.500974 × (L−1) [0x3f003fd5] | 15 16 16 17 17 18 18 19 19 20 20 21 21 22 22 23 23 24 24 25 |
| 77 | 3 | radius in 12-unit steps | 4 + 0.50298595 × (L−1) [0x3f00c3b0] | 4 5 5 6 6 7 7 8 8 9 9 10 10 11 11 12 12 13 13 14 |
| 77 | 4 | mana | 60 + 6.9999356 × (L−1) [0x40dfff79] | 60, 67 … 193 |
| 78 | 0 | duration, seconds, from the cast | 10 + 1.000996 × (L−1) [0x3f8020a3] | 10, 11 … 29 |
| 78 | 1 | melee damage bonus, percent | 30 + 2.002003 × (L−1) [0x400020d1] | 30, 32 … 68 |
| 78 | 2 | armour lost, percent | 40 − 0.00001 × (L−1) [0xb727c5ac] | 40 at every rank |
| 78 | 4 | mana | 30 + 3.0019848 × (L−1) [0x40402085] | 30, 33 … 87 |

### Cost and limits

Mana = statistic 4. canUse (0x2fff64, 0x301464, 0x30300c): the caster must not already
carry a spell of the same class.

### The shared skeleton

Cast (0x2fff98, 0x301498, 0x303040): `pool_new`, construct, return the spell. Blood Lust
plays its sound at `pos` first.

Constructor (0x30016c, 0x301714, 0x303254):

1. Spell base — shared draw.
2. `owner.+0x58c = 6` — the player action state "under control of a skill". **No is-player
   test.**
3. The shout animation is chosen by the weapon-style byte of record [owner + 0x3c8]
   (+0x4a86): 0 `ohw_`, 1 `dhs_`, 2 `dha_`, 3 `l_`, 7 `dw_`, anything else `nw_`, followed by
   `roar.anm` / `battlecry.anm` / `bloodlust.anm`, looked up in the owner's own animation lump.
4. **The constructor writes the event slots of that animation file's header** (slot i is
   {float seconds at +0x14 + 8i, mask byte at +0x18 + 8i}, `docs/engine.md`):

   | | slot 1 | slot 2 | slot 3 |
   |---|---|---|---|
   | Roar | 0.316999 s [0x3ea24db1] → 2 | 1.23597 s [0x3f9e3443] → 4 | — |
   | Battle Cry | 0.101002 s [0x3dceda22] → 2 | 2.35095 s [0x401675ee] → 4 | 1.17799 s [0x3f96c83e] → 8 |
   | Blood Lust | 0.487999 s [0x3ef9db01] → 2 | — | — |

5. `anim_startBlendInOut(0.1, 0.1, owner animation state, file, flags)` with flags 0x22
   (Roar, Battle Cry) or 0x822 (Blood Lust: root motion as well).
6. Sound (Roar, Battle Cry keep the handle to stop it on interruption).

Run, the common part, once per frame:

```
[77, 78: clock += 1/60 here; 76 advances its clock at the end]
if net game and net_isLocalSlot(owner.+0x3c8): g_forceGhostRebase = 1
if animating:
    if owner.+0x58c != 6:                       # something else took the player over
        animating = 0
        if the effect has not started:
            mana = min(mana + manaCost(level) * 0.5, maximum mana)
            stop the sound ; interrupted = 1 ; endTime = clock + 0.5
    if animating:
        ev = Player_animStep(1.0, owner)        # the spell advances the player's animation
        if owner animation flags (+0x11a) no longer have 0x20:      # the shout track is gone
            animating = 0 ; owner.+0x58c = 2
        else: handle ev                          # per skill, below; ev is compared for EQUALITY
```

`ev` is the OR of every event that fired in this step on any track, compared with `== 2`,
`== 4`, `== 8`; an event from another track in the same step would hide it. With the
animation running at normal speed the events fall on the spell's 20th and 75th run (Roar),
7th, 71st and 142nd (Battle Cry) and 30th (Blood Lust) — Inferred from the event rule in
`docs/engine.md` (an event fires in the step whose start time t satisfies
t/60 ≤ seconds < (t + step)/60), not observed. `Player_animStep` scales the step by the
Drowsy factor and the slow amount, so those stretch the timing.

### 76 Roar — the effect

Fields: +0x18 owner, +0x1c candidate list, +0x20 centre, +0x2c clock, +0x30 shout time
(−1), +0x34 end time (−1), +0x38 ground height, +0x3c sound, +0x40 animating (1), +0x44
interrupted, +0x48 shouting, +0x4c in water.

```
ev == 2:
    shouting = 1 ; shoutTime = clock
    camera_shake(level * 0.5 + 3.5)
    centre = owner model attach point 7
    groundHeight = terrain_height(6.0, world, centre) ; inWater = water_test(8.0, world, centre)
    candidates = every object with flags & 0xd == 0 from
                 world_collectInSphere(getStat(0) * 12 * 1.5, centre)      # box order
ev == 4: shouting = 0
while shouting: mouth particles                      # own generator, 2-4 draws
--- after the common part ---
if not interrupted and shoutTime >= 0:
    f = (clock - shoutTime) * 2
    if f <= 1.0:
        r = f * 12.0 * getStat(0, level)
        hit(r)
        ring particles                               # own generator
        if inWater and clock == shoutTime: water_disturb(3500, 36, world, centre)
    else: endTime = clock
if not animating:
    if endTime >= 0 and clock < endTime: goto tick
    if not interrupted and owner.+0x58c == 6: owner.+0x58c = 2
    destroy the spell ; return
tick: clock += 1/60 ; if clock > 6.0: destroy the spell
```

`hit(r)` (0x300f54, `SpellRoar_hitRing`): for each candidate in list order — gone: drop;
`dist2D(centre, o) − o.radius > r`: keep for later; a creature with flags & 9 or not an
enemy of the owner: drop; otherwise
`damage_apply(lo, hi, o, owner, 100000, 0, 0, flags, none, 0)` with
(lo, hi) = statRange(0.2, stat 1, level) and flags 0x80940 below level 5, 0x100940 for 5–9,
0x200940 from 10 (unblockable; knock-back 150 / 200 / 312.5 on a kill), then drop.
Non-creature objects in the list are hit without any test.

The wave grows for half a second to stat 0 × 12 units. The spell ends when the animation
ends; an interrupted spell lingers 0.5 s.

### 77 Battle Cry — the effect

Fields: +0x18 owner, +0x1c clock, +0x20 end time (= (float)getStat(2) at construction),
+0x24 cry time (−1), +0x28 aura radius (−1), +0x2c sound, +0x30 animating (1), +0x34
streamers on, +0x38 interrupted, +0x3c particle group, +0x40 / +0x4c last hand positions.

```
ev == 2: streamers = 1          ev == 4: streamers = 0
ev == 8: cryTime = clock ; particle group created
--- after the common part ---
if endTime <= clock:
    if not interrupted and owner.+0x58c == 6: owner.+0x58c = 2
    destroy the spell ; return
if cryTime >= 0:
    g = min(1, (clock - cryTime) * 2.000012)
    radius = 38.42372 ; R = getStat(3, level) * 12.0
    if R > 3.2019768: radius = (R - 38.42372) * g + 38.42372
    ground particles                                   # own generator, 1 draw each
    tint (both flash quads {0x5c, 0x21, 0x0f, 0x23}) the owner and every player in
      g_alivePlayers other than the owner who is within `radius` (3-D) and, in PvP mode A,
      on the owner's team (virtual slot 22)
if cryTime == clock:                                   # the frame of the cry
    LightEffect at the run position + 36, following the owner          # shared draw
    list = world_collectObjectsInBox(run position ± R on three axes, at most 511)
    for o in list: if o is a creature and owner.isEnemy(o)
                      and dist3D(run position, o) <= R + o.radius and o.hp >= 0:
        d = Spell_rand()
        if (d % 100) < getStat(0, level):
            o.stun(frames = trunc(getStat(2, level) * 19.979939), flash = 1)
```

"Run position" is what `Player_updateCast` hands to slot 17: the midpoint of the hands.

The lasting effect is read by `Player_run` in the melee-swing state (0x1aa018–0x1aa0ec):
for every player in `g_alivePlayers` who carries a `SpellAncestralCall`, or failing that a
`SpellBattleCry`, it asks that spell whether the swinging player is covered and takes the
largest fraction; a non-zero result **multiplies** the swing animation speed. For Battle
Cry the question is 0x302c04 (`SpellBattleCry_affects`): fraction = getStat(1) × 0.01; yes
if the swinger is the owner (from the moment of the cast), or — once the cry has happened —
is within the aura radius of the owner in 3-D and, in PvP mode A, on the owner's team.

So for stat 2 seconds from the cast: swing speed × 1.25–1.82 for the caster and for allies
who stay within stat 3 × 12 units; and once, at the cry, a stat 0 % chance to stun each
enemy in range for stat 2 × 0.333 seconds.

### 78 Blood Lust — the effect

Fields: +0x18 owner, +0x1c clock, +0x20 start time, +0x24 end time (= (float)getStat(0)),
+0x28 animating (1), +0x2c active, +0x30 interrupted, +0x34 / +0x40 last hand positions.

`ev == 2`: active = 1, start time = clock. After the common part: if `endTime <= clock` the
spell ends as for Battle Cry; otherwise, while active, the owner's flash quad 1 is set to a
pulsing dark red (values from the clock and `g_simFrame`), glows and particles are emitted.

Two other functions read the `active` flag:

- `SpellBloodLust_getStat2Complement` 0x3047b0 — `damage_apply` step 8: when the *victim*
  carries the spell and it is active, the victim's armour is multiplied by
  1 − getStat(2) × 0.01 = 0.6 (floor 1) for the hit-chance and rating-scale steps.
- `SpellBloodLust_getStat1Multiplier` 0x30481c — `Player_recalcDamage` (0x1b7158, decompile
  lines 308–346): for a class-5 player in action state 1 (a melee swing) the final damage
  multiplier is the **larger** of the Berserker Rage factor (id 71) and
  1 + getStat(1) × 0.01; minimum damage, maximum damage and attack rating are each
  multiplied by it and truncated.

### Random draws

| Skill | When | Generator | Count |
|---|---|---|---|
| all | constructor | shared | 1 |
| 76 | each victim of the wave | shared | those of `damage_apply` |
| 76 | while shouting / during the wave | own | particles only: 1–4 per frame at the mouth; 277 (370 from level 10) + 9 (12) × (1 + 3 per try) on the ring |
| 77 | the cry | shared | 1 (`LightEffect`) |
| 77 | while streamers are on, every frame | own | 10 × (3 per try + 3 per try + 2) |
| 77 | every frame after the cry | own | level + 13 (four times that during the first half second), 1 each |
| 77 | the cry, per enemy in range | own | 1 — **the stun roll**, after that frame's particle draws |
| 78 | every frame while active | own | particles; **the count depends on per-machine inputs** (below) |

### Presentation only

Animations and sounds; Roar's camera shake, mouth and ring particles and water ripple;
Battle Cry's hand streamers, ground ring, tint; Blood Lust's glow, flash and blood drops.

### Per-machine state

- **Unguarded player index** in all three constructors and run functions (addresses in
  `docs/skills.md`, table (a)): the weapon-style byte, the mana refund, `net_isLocalSlot`,
  the action state at +0x58c (beyond the end of a plain Creature) and the body model at
  +0x544 are used for any owner. Players only, by the trees.
- `g_forceGhostRebase` is written every frame on the owner's machine (per-machine state by
  design).
- Battle Cry reads `g_alivePlayers` for the tint, and `Player_run` reads it for the swing
  speed: the list FINDINGS G11–G13 show can be wrong for part of one frame on one machine.
- Battle Cry's ground particles are centred on `net_objOrGhost(owner)`; the number of draws
  does not depend on it, which matters because the stun roll shares the generator.
- Blood Lust's particle loop takes its counts from how far the hands of
  `net_objOrGhost(owner)` moved and from the option `g_decalDetail` (0x44fdc0), so its own
  generator diverges between machines; in the part of the function read here nothing but
  particles consumes it (`docs/skills.md` (b) item 2 reaches the same conclusion for the
  whole function).
- Roar calls `camera_shake` (output only) and `water_disturb` (returns 0 while a cutscene
  skip is active; the return value is not used).

### Functions read

76: 0x2ffe9c, 0x2fff08, 0x2fff64, 0x2fff98, 0x300138, 0x30016c, 0x3003d8, 0x300f54.
77: 0x301364, 0x3013d0, 0x301464, 0x301498, 0x3016e0, 0x301714, 0x301a34, 0x302bd0, 0x302c04,
and the consumer at 0x1aa018–0x1aa0ec. 78: 0x302f2c, 0x302f98, 0x30300c, 0x303040, 0x303220,
0x303254, 0x3034dc up to 0x303680 in full and the rest scanned for stores and calls,
0x3047b0, 0x30481c, and `Player_recalcDamage` lines 308–375.
Not read: the three describeRank functions; `Player_animStep`'s callee `anim_advance`
(taken from `docs/engine.md`); what `Player_run` itself does in action state 6.

## 100 — Lightning Strike (`lightningstrike`) and 80 — Pus Storm (`pusstorm`)

**Both fully specified.** The two are one piece of code compiled twice with different
numbers: a slowly drifting "storm" object that damages everything hostile under it twice a
second and scatters decorative strikes. They are described together; differences are
called out.

### Identity

| | 100 Lightning Strike | 80 Pus Storm |
|---|---|---|
| Skill class / table / object | `SkillLightningStrike` / 0x51c670 / 0x6e3f50 | `SkillPusStorm` / 0x51b950 / 0x6e34f0 |
| Kind, flags, recast | 0, 0, 30 | 0, 0, 30 |
| Tree | **none** — no class can learn it | shaman (class 6): base level 19, needs skill 26 |
| Other casters | `Hag` (on animation event bit 2 with a target; position = the target's; table load at 0x2700b0) | `FemaleDarkElf` (table load at 0x25a710) |
| Storm object | `LightningStrikeSpell`, a GameObject of 0xbc bytes, table 0x51c5e0 | `PusStorm`, a GameObject of 0xc0 bytes, table 0x51b830 |
| Decoration | `LightningBolt` (0x60 bytes, table 0x5168e8, 17 frames) | `Pustule` (0x160 bytes, table 0x51b8c0) |

Neither cast returns a Spell (both return 0), so nothing is attached to the caster: the
storm lives until its own last frame, or until its owner object is destroyed.

### Statistics

| Stat | Meaning | 100 tier 1 | 100 tier 2 | 80 tier 1 | 80 tier 2 |
|---|---|---|---|---|---|
| 0 | radius in 12-unit steps | 2 + 0.32999998 × (L−1) [0x3ea8f5c2] | 5 + 0.32999998 × (L−1) | 2 + 0.201004 × (L−1) [0x3e4dd3fe] | 2 + 0.32999998 × (L−1) |
| 1 | damage before spread; each tick deals half | 50 + 5 × (L−1) | 20 + 2 × (L−1) | 85 + 5.0089717 × (L−1) [0x40a0497f] | 50 + 5 × (L−1) (**never used**, see below) |
| 2 | seconds the storm lasts | 2 + 0.32999998 × (L−1) | same | 2 + 0.25100398 × (L−1) [0x3e808398] | 2 + 0.32999998 × (L−1) |
| 3 | drift speed, units per second | 32 + 1 × (L−1) | same | 32 + 0.75199795 × (L−1) [0x3f4082f0] | 10 + 1 × (L−1) |
| 4 | mana | 1 + 1 × (L−1) | — | 55 + 6.0009637 × (L−1) [0x40c007e5] | — |

Statistics 0, 2 and 3 are looked up with the level clamped to 10 for non-player casters
(cap argument 10); statistic 1 with no clamp.

Ranks 1–20, tier 1. Id 80: radius steps 2 2 2 3 3 3 3 3 4 4 4 4 4 5 5 5 5 5 6 6; damage
85, 90 … 180; seconds 2 2 3 3 3 3 4 4 4 4 5 5 5 5 6 6 6 6 7 7; speed 32 33 34 34 35 36 37 37
38 39 40 40 41 42 43 43 44 45 46 46; mana 55, 61 … 169. Id 100 tier 2, levels 1–10: radius
steps 5 5 6 6 6 7 7 7 8 8; seconds 2 2 3 3 3 4 4 4 5 5; speed 32 … 41.

### Cost and limits

Mana = statistic 4. Both use the base canUse (always allowed).

### Cast — 0x31a920 (id 100), 0x30aaa8 (id 80): (level, caster, pos, facing)

```
level = slot 14(level)                                   # no-op
# damage range
id 100: if caster is a player: (lo, hi) = statRange(0.2, stat 1, level)        # slot 8
        else: v = stat(1, level, caster, cap 0); hi = trunc(v + v*0.19999999); lo = trunc(v - v*0.19999999)
id 80:  (lo, hi) = statRange(0.2, stat 1, level)        # slot 8 = TIER 1 for every caster
s0 = stat(0, level, caster, cap 10)
s2 = stat(2, level, caster, cap 10)
s3 = stat(3, level, caster, cap 10)
if caster is a player: off = (cos16(facing), sin16(facing)) * s0 * 12.0
else:                  off = (cos16(facing), sin16(facing)) * s0 * -6.0
c = pos + off ; c.z = terrain_height(24.0, world, c)
vel = (cos16(facing) * s3, sin16(facing) * s3, 0)        # units per second
id 80:  sound, then pool_new(0xc0)
id 100: pool_new(0xbc), then sound                        # spel_ew_froststorm.anm in both
if the block was obtained:
    construct(radiusSteps = s0, c, vel, durFrames = s2 * 60,
              interval = 20 - trunc(level * 0.5), lo, hi, caster)
return 0
```

A player's storm starts one radius ahead of the cast point; a monster's starts half a
radius *before* the position it was given (the Hag gives its target's position), along the
monster's facing. Both casts read the caster's flag word without a null test at the offset
step, so a null caster would fault there.

### Storm object

| Offset (100 / 80) | Type | Meaning | Initial value |
|---|---|---|---|
| +0x10 | Vec3 | position | `c` |
| +0x4c | Vec3 | velocity per frame | `vel` × (1/60) |
| +0x58 | s32 | start frame | frame + 1; **frame + 41 when the caster is a creature that is not a player**, and then a second `LightEffect` (a warning light) is created at `c` + 12 up |
| +0x5c | s32 | first damage frame | 100: start. 80: start + 48 |
| +0x60 | s32 | last frame on which decorations are spawned (exclusive) | start + durFrames |
| +0x64 | s32 | last frame of life | 100: start + durFrames. 80: start + 48 + durFrames |
| +0x68 | s32 | decoration interval | 20 − trunc(level / 2) |
| +0x6c | s32 | next decoration frame, −1 = not yet set | −1 |
| +0x70, +0x74 | s32 | lo, hi | |
| +0x78 | float | radius | s0 × 12.0 |
| +0x7c | handle (100) / float (80) | 100: owner handle. 80: fall time 48.990772 frames [0x4243f68d] | |
| +0x80 | (80) handle | owner handle (id 100 has its light record here) | |

Constructor (0x31ae48 / 0x30af6c): `GameObject_ctor` — one shared draw; object flags
|= 0x420f (transient, touch-only, and bits 1, 2, 4, 8, which keep it out of drawing,
sphere queries and every "alive" test); a light record (presentation); the fields above;
`obj_runEveryFrame`.

Run (0x31b25c / 0x30b428), once per frame:

```
if frame < start: return
if lastFrame < frame  or  the owner handle is empty:
    destroy the object; return
position += velocity ; obj_updateGridCell
centre = position                         # id 100
centre = position - velocity * 48.990772  # id 80: where the storm was 49 frames ago
# (light radius flicker: presentation)
if next < 0: next = frame
if frame < spawnEnd and next <= frame:
    spawn one decoration                  # below
    next = frame + interval / 2 + (own draw) % interval
if firstDamage <= frame and (frame - firstDamage) % 30 == 0:
    dmin = lo / 2 ; dmax = hi / 2         # integer division
    list = world_collectObjectsInBox(centre.xy ± radius, centre.z ± 2*radius, at most 63)
    for o in list (box order):
        if owner.isEnemy(o):
            id 100: descriptor slot 0 = {0x18, dmin, dmax, 0}      # lightning
            id 80:  descriptor slot 0 = {0x26, dmin, dmax, 0}      # disease
            damage_apply(dmin, dmax, o, owner, 100000, 0, 0, flags 0x40, descriptor, 0)
```

- Ticks happen on frames firstDamage, +30, +60 … up to and including the last frame of
  life, because the duration is a whole number of seconds: 2 × s2 + 1 ticks.
- The area is the box, not a circle: `world_collectObjectsInBox` tests each object's
  radius against the box in x/y and its height in z, nothing more.
- Each tick on each victim is a full `damage_apply`: base roll dmin…dmax, then for id 100 the
  lightning slot (another dmin…dmax reduced by lightning resistance, and the shock status),
  for id 80 the disease slot (attaches skill 29's disease spell if the victim has none).
  Flag 0x40: cannot be blocked, ignores Spirit Shield.
- The owner handle empties when the owner object is destroyed, which ends the storm on its
  next run.

Decoration, id 100: a point `p` = position + (random point in the unit sphere) × radius,
`p.z` = terrain height (radius 8) there; `pool_new(0x60)` and `LightningBolt_ctor(p, life 17,
no light)` — a GameObject, so **one shared draw** when the block was obtained. The bolt is a
240-unit vertical beam that calls `fx_spawn(0x13)` each frame and deletes itself after 17
frames; it damages nothing.

Decoration, id 80: the same ground point `g`; a start point 240 above it and
`((draw / 65536) × 10 + 10) × 12` units away horizontally in direction `draw` (a 16-bit
angle); `pool_new(0x160)` and `Pustule_ctor(start, g, velocity = (g − start).xy / 48.990772,
angle)` — again a GameObject and **one shared draw**. A `Pustule` falls with gravity
0.19999199 per frame², and when it reaches the ground height plays a sound and becomes ten
droplets for 36 frames; it is deleted after that or after 300 frames in the air. It
damages nothing; the 48-frame delay of the damage centre is what makes the damage coincide
with the blobs landing.

### Random draws

| When | Generator | Count |
|---|---|---|
| cast | shared | 1 (storm object); 1 more (`LightEffect`) for a non-player creature caster |
| each decoration | storm's own | 3 per try until the point is inside the unit sphere; id 80: 2 more (distance, angle); then 1 for the next interval |
| each decoration | shared | 1 (`LightningBolt` / `Pustule` constructor), 0 if the pool is empty |
| each damage tick, per enemy in the box | shared | those of `damage_apply` |
| `Pustule` | its own | particles only |

The storm's own generator is seeded from the shared one and decides how many decoration
objects are built, hence how many shared draws happen: it has to be reproduced exactly,
including the rejection loop (`1.0 < x² + y² + z²` in single precision).

### Hazards in the interval arithmetic (Observed code, Inferred reach)

`interval = 20 − trunc(level / 2)` is 0 for levels 40 and 41 and negative from 42. The
remainder at 0x31b5ac (and the same expression in `PusStorm_run`) is a `div` with no
zero test or trap after it. What a zero divisor leaves in the remainder register is the
processor's business, not something this executable shows; the usual description of the
R5900 is "the dividend", which would put the next decoration up to 65535 frames away. With
−1 the remainder is 0 and `interval / 2` is 0, so a decoration is spawned every frame. Players cannot exceed rank 20. A monster passes
trunc(monster level × 0.3), which reaches 40 at monster level 134 — inside the range
`docs/data-tables.md` §5 gives for the highest difficulty. A rebuild must reproduce the
console's divide-by-zero result or the shared generator will be consumed differently there.

### Presentation only

Sounds; the storm's light (radius min(300, radius × 1.75), flickering, in id 80 following
the delayed centre); the warning `LightEffect` for monster casts; the bolts and blobs
themselves; `fx_spawn(0x13)`.

### Per-machine state

- No camera, local-slot, pad, audio or cosmetic-generator read in cast, constructor or run.
  `fx_spawn(0x13)` inside `LightningBolt_run` is camera-gated but only cosmetic.
- Non-player caster: 40 extra frames before the storm starts, one extra shared draw, tier 2
  numbers for id 100. **Id 80 takes its damage from tier 1 whoever casts it** (0x30ab54–0x30ab74:
  slot 8, which never looks at the caster), so the dark elf's Pus Storm hits with the
  player table's 85 + 5 per level while its radius, duration and speed come from tier 2.
- `Pustule_draw` (0x30bc88) and the storm's (empty) draw write nothing.

### Functions read

Id 100: 0x31a808, 0x31a874, 0x31a920, 0x31ae14, 0x31ae48, 0x31b1cc, 0x31b25c; `LightningBolt`
0x295360, 0x2957e4. Id 80: 0x30a958, 0x30a9c4, 0x30aaa8, 0x30af38, 0x30af6c, 0x30b398,
0x30b428, 0x30bb38, 0x30bde0. Call sites 0x2700b0 (Hag), 0x25a710 (FemaleDarkElf).
Not read: the two describeRank functions, `Pustule_draw` beyond a scan for stores, what
position the dark elf passes (a stack vector filled earlier in its run function).

## Ids 81–86: the berserker and shaman variants of six shared classes

Each of these ids is a second or third static object of a class whose first id lies below
69: Critical Hit (33, 53, **81**), Riposte (9, **82**), Dodge (2, **83**), Cyclone (41,
**84**), Root (31, 32, 52, **85**), Healing (55, **86**). The object stores its id at +0x64;
the constructor uses it to pick the name and `initStats` to pick the numbers. **Apart from
that the id is read in exactly one place** — the particle count in `SpellCriticalHit_run`
(0x2e7c88) — so behaviour is the class's, and the class sections of the documents
for ids 1–68 are the reference. What follows gives each id's own data in full and the
class behaviour as read here, in less detail than the sections above: **partly specified.**

How that was checked: every load instruction with displacement 0x64 in the six classes'
address ranges was listed from the instruction words. There are eleven: one in each
`initStats` (0x2d1518, 0x2ddaec, 0x2e6384, 0x2e7314, 0x2e89a4, 0x2e8bd4), the one at
0x2e7c88 in `SpellCriticalHit_run`, and four in the Cyclone particle helper 0x2d21e0 whose
base register is the spell, not the skill (spell + 0x64 is a particle phase).

### 81 — `berserkercriticalhit` (class `SkillCriticalHit`, table 0x519c58, object 0x6e3558)

Berserker tree: base level 10, needs the passive with mask 0x40. Kind 0, recast 30.

| Stat | Meaning | Formula | Ranks 1–20 |
|---|---|---|---|
| 0 | critical-hit chance added, percent | 10 + 2.000985 × (L−1) [0x40001023] | 10, 12 … 48 |
| 1 | aura radius in 12-unit steps, from level 5 | 6 + 0.75099397 × (L−5) [0x3f404124] | 0 0 0 0 6 7 8 8 9 10 11 11 12 13 14 14 15 16 17 17 |
| 2 | duration, seconds | 8 + 0.250985 × (L−1) [0x3e80811b] | 8 8 9 9 9 9 10 10 10 10 11 11 11 11 12 12 12 12 13 13 |
| 4 | mana | 35 + 4.0019717 × (L−1) [0x40801027] | 35, 39 … 111 |

Class behaviour (0x2e7224, 0x2e74b0, 0x2e7988, 0x2e7acc, 0x2e76c4, all read):

- canUse: no `SpellCriticalHit` on the caster. Cast: `pool_new(0x5c)`, construct, return.
- Constructor: Spell base (shared draw); a light; time left (+0x18) = (float)getStat(2,
  level); a particle group.
- Run: time left −= 1/60; below 0 the spell destroys itself. Otherwise tint the owner
  (flash quad 1 = {0x44, 0x0e, 0x18, 0x0f}) and every other player in `g_alivePlayers`
  within getStat(1, level) × 12 units in 2-D (same team only in PvP mode A); ground
  particles, one own draw each, `level − first + 14` of them where `first` is 1, 10 or 5 for
  ids 53, 33, 81 — the level at which that id's statistic 1 starts.
- The bonus is fetched by `damage_apply` (step 18) for a player attacker: for each of the
  ids 33, 53, 81 it calls 0x2e76c4 (unnamed; called `bonusFor` below)
  with that id's Skill object and the attacker's rank in it, and adds the largest result to
  the critical chance:

  ```
  bonusFor(skill, attacker, rank):
      if rank != 0 and attacker carries a SpellCriticalHit: lvl = rank
      else:
          lvl = 0
          for p in g_alivePlayers, p's slot != attacker's slot:
              if dist3D(p, attacker)^2 < 1000000 and (not PvP mode A or p.sameTeam(attacker))
                 and p carries a SpellCriticalHit:
                  r = max(p's rank in 53, in 81, in 33)
                  if r != 0 and dist2D(p, attacker)^2 < (skill.getStat(1, r) * 12)^2:
                      lvl = r ; break
      return skill.getStat(0, lvl) * 0.01 if lvl != 0 else 0
  ```

  Note the aura case evaluates **the queried id's** tables at the *other* player's best
  rank, and the test "attacker carries the spell" does not check which of the three ids the
  attacker's spell came from.

### 82 — `berserkerriposte` (class `SkillRiposte`, table 0x519528, object 0x6e35c0)

Berserker tree: base level 15, needs skill 81. Kind 3 (passive); cast returns 0.

| Stat | Meaning | Tier 1 | Tier 2 |
|---|---|---|---|
| 0 | counter-attack damage | 10 + 4 × L (first level 0) → 14, 18 … 90 | 2 + 2.0000088 × (L−1) |
| 1 | chance, percent | 10 | 15 |

(Id 9 differs only in the base of statistic 0: 20.)

`SkillRiposte_counterAttack` (0x2ddccc; skill, victim, attacker, rank), called by
`damage_apply` step 24 for a player victim once for id 9 and once for id 82 (table load
0x1ea58c), with the victim's rank in each:

```
if rank == 0: return
dmg = stat(0, rank, victim, cap 10) ; chance = stat(1, rank, victim, cap 10)
r = SHARED draw
if trunc(r / 65536 * 100) >= chance: return
victim flash: both quads = {0x82, 0x82, 0x83, 0x55}
if the victim's model has no sample points: return
200 particle steps                                    # cosmetic generator
r2 = SHARED draw
damage_apply(dmg, dmg + dmg * (r2 / 65536) * 0.19999999, attacker, victim (as attacker),
             100000, 0, 0, flags 0x40, empty descriptor, noCrit = 1)
```

### 83 — `berserkerdodge` (class `SkillDodge`, table 0x519d98, object 0x6e3628)

Berserker tree: base level 12, needs the passive with mask 0x40. Kind 3; mana function
returns 0.

| Stat | Meaning | Tier 1 | Tier 2 |
|---|---|---|---|
| 0 | chance to dodge a missile, percent | 20 + 2.9999838 × (L−1) [0x403fffbc] → 20, 23 … 77 | 5 + 5 × (L−1) |

(Identical to id 2.) `SkillDodge_getStat0Fraction` (0x2e8ac0): getStat(0, rank) × 0.01, 0
at rank 0. Its only callers are in `MissileWeapon_onTouch` (0x152e8c for id 2, 0x152eb4 for
id 83): for a player victim, chance = the larger of the two ids' values × 100, truncated;
one shared draw `r`; the missile is dodged when `(r % 100) + 1 < chance`. What a dodge then
does (the code that follows builds an item from the descriptor `explodingpotion`) was not
read.

### 84 — `berserkercyclone` (class `SkillCyclone`, table 0x518ac8, object 0x6e3690)

Berserker tree: base level 20, needs the passive with mask 0x40000. Kind 0, recast 30,
**flag bit 0 set** (the prediction copy runs the cast too).

| Stat | Meaning | Formula | Ranks 1–20 |
|---|---|---|---|
| 0 | percent of a melee hit dealt by each strike | 50 + 2.9999928 × (L−1) [0x403fffe2] | 50, 53 … 107 |
| 1 | number of loops of the spin animation | 2 + 0.20099899 × (L−1) [0x3e4dd2ae] | 2 2 2 3 3 3 3 3 4 4 4 4 4 5 5 5 5 5 6 6 |
| 2 | movement speed while spinning (× 1.4312282 units per second) | 45 + 1.999967 × (L−1) [0x3ffffeeb] | 45, 47 … 83 |
| 4 | mana | 51 + 4.0008707 × (L−1) [0x40800722] | 51, 55 … 127 |

Class behaviour (0x2d1484, 0x2d161c, 0x2d17c8, 0x2d1a94 read; helper 0x2d21e0 not):

- canUse: a player whose weapon-style byte is 4 (bow) or 6 (thrown) is refused with the
  text `cyclone_warn`; everyone else is allowed.
- Constructor: Spell base (shared draw); `owner.+0x58c = 6` (no is-player test); the looping
  animation `cyclone1.anm` is pushed (flags 0x23) with its event slot 0 set to 0.05 s, mask
  1; spin time (+0x68) = clip length in seconds × getStat(1); two own draws for particle
  phases. Unless the owner is the prediction copy: voice, sound, and the candidate list =
  everything `world_collectInSphere(480, owner position)` returns.
- Run, per frame: `ev = Player_animStep(1.0, owner)`. Each time event bit 1 fires, spin
  time −= 0.05 and the event is moved 0.05 s later in the clip (wrapping), so it fires
  every three frames. When spin time ≤ 0.071991995 the closing animation `cyclone2.anm`
  (event slot 2: 0.166995 s, mask 4) is started and the spin phase ends. While spinning the
  player is moved by `Player_move` with a velocity built from the analog stick of
  `g_pads[slot]`, the per-slot camera yaw (`net_getCamYaw`) and getStat(2). Until event bit
  4, on frames where `g_simFrame % 4 == 0` (`% 5` in levels whose flag word 0x44fe08 has
  0x100): every candidate the owner's slot 20 calls an enemy and whose centre is within its
  radius + 23 of the point 28.584467 units from the run position toward attach point 0
  gets `Player_meleeHit(getStat(0) × 0.01, owner, target, 0, 0x40000000)`. The spell ends
  when the animation tracks are gone or the action state stops being 6.
- Per-machine notes already in `docs/skills.md` and FINDINGS G22 apply unchanged.

### 85 — `shamanroot` (class `SkillRoot`, table 0x519ba0, object 0x6e36f8)

Shaman tree: base level 26, needs skill 65. Kind 0, recast 30.

| Stat | Meaning | Formula | Ranks 1–20 |
|---|---|---|---|
| 0 | most creatures rooted | 1 + 0.332983 × (L−1) [0x3eaa7cbf] | 1 1 2 2 2 3 3 3 4 4 4 5 5 5 6 6 6 7 7 7 |
| 1 | seconds rooted | 5 + 0.33299997 × (L−1) [0x3eaa7ef9] | 5 5 6 6 6 7 7 7 8 8 8 9 9 9 10 10 10 11 11 11 |
| 2 | percent chance per target | 50 + 2.200976 × (L−1) [0x400cdcca] | 50 52 54 57 59 61 63 65 68 70 72 74 76 79 81 83 85 87 90 92 |
| 4 | mana | 100 + 8.001883 × (L−1) [0x410007b6] | 100, 108 … 252 |

(The four ids differ in statistic 4 and slightly in the steps of statistics 0 and 2.)

Class behaviour (0x2e6534, 0x2e6598, 0x2e68c8 read; 0x2e699c read for its gameplay lines):

- canUse: a player in PvP mode A is refused (`pvpcast_warn`); otherwise allowed.
- Cast: sound on the caster; `world_collectObjectsInArc(248, 120°, 0, pos, facing, no
  filter)`; walking the list, up to getStat(0) targets that are enemies of the caster, not
  friendly-to-players (object flag 0x1000000), not bosses (`creature_bossRank` 0) and not
  already rooted (timer +0x314 < 1) each get a `SpellRoot` (0x34 bytes, one shared draw).
  Returns 0. The same shape as Drowsy's cast (id 88), which appears to be modelled on it.
- `SpellRoot` run: clock += 1/60; for the first 0.518994 s (31 runs) only particles (own
  generator); on run 32 **one shared draw** `r`: if `(r % 100) + 1 >= getStat(2)` the spell
  bursts and destroys itself; otherwise the victim flashes, and — monsters only — its root
  timer +0x314 = seconds × 60. From then on, for a *player* victim, every frame sets the
  knock-back speed (+0x2e8) to 4 × its distance from where it stood and the knock-back
  angle (+0x2e0) back toward that spot. The spell ends when clock − 0.518994 exceeds the
  duration.

### 86 — `shamanhealing` (class `SkillHealing`, table 0x519e50, object 0x6e3760)

Shaman tree: base level 10, needs skill 88. Kind 0, recast 30.

| Stat | Meaning | Tier 1 | Tier 2 (level clamped to 20) |
|---|---|---|---|
| 0 | percent of the caster's own maximum hit points restored | 30 + 3.50298 × (L−1) [0x406030d3] → 30 34 37 41 44 48 51 55 58 62 65 69 72 76 79 83 86 90 93 97 | 15 + 5 × (L−1) |
| 1 | radius in 12-unit steps | 5 + 0.334 × (L−1) [0x3eab020c] → 5 5 6 6 6 7 7 7 8 8 8 9 9 9 10 10 10 11 11 11 | 5 + 0.39999998 × (L−1) |
| 2 | percent of maximum hit points restored to others in range | 20 + 4.0019855 × (L−1) [0x40801044] → 20, 24 … 96 | 10 + 4 × (L−1) |
| 4 | mana | 72 + 7.00097 × (L−1) [0x40e007f2] → 72, 79 … 205 | — |

(Id 55 differs only in the float steps and in statistic 4: 55 + 6 per level.)

Class behaviour (0x2e8cf8, 0x2e8ec8, 0x2e90b8 read):

- Cast: `pool_new(0x24)`, construct, return. Constructor: Spell base (shared draw); sound;
  a `GlowingShaft` object (0x5c bytes, a GameObject: shared draw); a particle group;
  per-frame amount (+0x1c) = own maximum hit points × 0.014750047 × stat 0 × 0.01, with the
  maximum taken from the player record (+0xb0) for a player and from the object (+0x22c)
  otherwise.
- Run, on each of 68 frames (the spell destroys itself once its clock exceeds 1.1299399):
  R = stat(1) × 12.
  Player owner: every player in `g_alivePlayers` within R in 3-D (same team only in PvP
  mode A), provided record hp + 1 ≤ record max hp, gains the per-frame amount (the owner) or
  their own max hp × 0.014750047 × stat 2 × 0.01 (others). Nothing clamps the sum to the
  maximum here.
  Non-player owner (only while it is a live creature): `world_collectObjectsInBox(position
  ± R, at most 127)`; the owner itself and everything its virtual slot 21 ("is ally")
  accepts within R in 2-D gain hit points the same way, on the object's +0x228, with no
  "below maximum" test at all.
  68 × 0.014750047 = 1.003, so the whole heal is the printed percentage.
- `g_alivePlayers` is the list of FINDINGS G11–G13 and G21.

### Functions read for this section

Critical Hit 0x2e7224, 0x2e7258, 0x2e74b0, 0x2e76c4, 0x2e7988, 0x2e7acc, 0x2e7f58. Riposte
0x2dda54, 0x2ddb90, 0x2ddccc. Dodge 0x2e8a88, 0x2e8ac0. Cyclone 0x2d13ec (through the table
dump), 0x2d1484, 0x2d161c, 0x2d17c8, 0x2d1a94. Root 0x2e62b4, 0x2e6534, 0x2e6598, 0x2e68c8,
0x2e699c (lines 47–58, 74–130, 164–184 of the decompile). Healing 0x2e8cf8, 0x2e8ec8,
0x2e90b8. Not read: the six `initStats` bodies (numbers are from `tools/dump_tables.py`,
which follows their id branches), the describeRank functions, 0x2d21e0, `Player_meleeHit`,
`Player_move`.

## 87 — Tagar's Insects (`tagarsinsects`)

**Fully specified.** Every function of the class was read in the disassembly.

### Identity

| | |
|---|---|
| Skill class / table / object | `SkillTagarsInsects` / 0x51b9d8 / 0x6e37c8 |
| Kind, flags, recast | 0 (active), 0, 30 frames |
| Tree | shaman (class 6): base level 8, needs a rank in skill 89 |
| Other casters | `Horsemen` variant 2 (the arena's `UndeadKnight3` if the variants follow the order of FINDINGS D3 — Inferred) |
| Creates | one `SpellTagarsInsects` (0x94 bytes, table 0x51ba60) attached to the caster; one `SpellTag` marker (0x20 bytes, table 0x51ba90) per victim, attached to the victim |

### Statistics

| Stat | Meaning (Observed from use) | Tier 1 (player caster) | Tier 2 (other caster) |
|---|---|---|---|
| 0 | number of victims, further capped at 8 | 1 + 0.251 × (L−1) [0x3e808312] | 1 + 0.25 × (L−1), L clamped to 10 |
| 1 | damage per tick before the ±20 % spread | 20 + 2.0009758 × (L−1) [0x40000ffd] | 10 + 2 × (L−1), no clamp |
| 2 | seconds a victim stays infested, counted **from the cast**, not from the moment it is reached | 3 + 0.334999 × (L−1) [0x3eab84fd] | 2 + 0.24999899 × (L−1) [0x3e7fffbc], L clamped to 10 |
| 4 | mana | 30 + 13.000847 × (L−1) [0x41500378] | — |

Values, ranks 1–20 (tier 1): victims 1 1 2 2 2 2 3 3 3 3 4 4 4 4 5 5 5 5 6 6; damage
20 22 24 … 58 (= 20 + 2(L−1)); seconds 3 3 4 4 4 5 5 5 6 6 6 7 7 7 8 8 8 9 9 9; mana
30 43 56 … 277 (= 30 + 13(L−1)).
Tier 2, levels 1–10: victims 1 1 2 2 2 2 3 3 3 3 (then constant); damage 10 + 2(L−1);
seconds 2 2 2 3 3 3 3 4 4 4 (then constant).

### Cost and limits

- Mana: statistic 4 at the cast level (slot 5 → slot 15, 0x30c928). Recast 30 frames.
- canUse (0x30c700) always returns 1: no weapon, target or "already active" test. A second
  cast while the first is alive creates a second, independent swarm; the two skip each
  other's victims only through the marker test below, which is per caster — so two swarms
  of the *same* caster never share a victim, swarms of different casters can.

### Cast — `SkillTagarsInsects_cast` 0x30c708 (level, caster, pos, facing)

1. Level through slot 14 (no-op).
2. Sound `spel_is_tagar_cast.anm` at `pos` (presentation).
3. `pool_new(0x94)`; when it fails return 0 (the sound has played; a player caster still
   pays mana and recast in `Player_castSkill`).
4. Construct the spell (0x30c95c). One draw from the shared generator (the Spell base).
5. Return the spell. The player cast helper attaches it to the player; the knight attaches it
   to itself (0x272bfc). `pos` and `facing` are not otherwise used — the constructor reads
   the caster.

### `SpellTagarsInsects` layout

| Offset | Type | Meaning | Initial value |
|---|---|---|---|
| +0x00…+0x14 | | Spell base (level, back-list, skill, owner = caster, own generator, table) | |
| +0x18 | handle[8] | victim handles, in the order they were reached | all empty |
| +0x38 | float[8] | per slot. While the swarm is flying to that victim: the latest allowed arrival time. After arrival: the time the infestation ends. −1: finished | 0 |
| +0x58 | float[8] | per slot: time of the next damage tick | 0 |
| +0x78 | float | `t`, seconds since the cast (+1/60 per run) | 0 |
| +0x7c | float | `tEnd`: after this the swarm stops hunting | 2.000984 [0x4000101f] |
| +0x80 | s16 | slot being flown to, −1 = none | −1 |
| +0x82 | s16 | `n`, victims reached so far | 0 |
| +0x84 | s16 | heading | caster facing (+0x38) |
| +0x86 | s16 | wander offset added to the heading | 0 |
| +0x88 | Vec3 | swarm position | caster position + 24 × (cos, sin)(facing), z + 48 |

All times are on the spell's own clock `t`, a float that accumulates the constant
0x3c888888 (0.016666666) once per run.

### Run — `SpellTagarsInsects_run` 0x30cbc8, once per simulated frame of the caster

```
active = tickVictims()                      # below; uses t before the increment
t += 1/60
if tEnd <= t:
    if not active: destroy the spell (slot 1, argument 3)
    return                                  # no movement, no draws, no particles
limit = min(8, stat(0, level, owner, cap 10))
if limit <= n: return                       # everything reached: the swarm object is idle
                                            # (still no draws); only tickVictims works
# --- current target ---
tgt = none
if cur >= 0:
    if handle[cur] is empty:  cur = -1
    else:
        tgt = handle[cur].object
        if not valid(tgt, markerTest = false): cur = -1
if cur < 0:
    tgt = pickTarget(first = (n == 0))      # may be none
    if tgt:
        cur = n
        link handle[n] to tgt
        slotTime[n] = t + dist2D(tgt, swarm) * 0.0049248165      # 0x3ba1605b = 1/203.05
speed = 203.05324                            # 0x434b0da1, units per second
if tgt:
    dx = tgt.x - swarm.x ; dy = tgt.y - swarm.y
    if dx*dx + dy*dy > 1.0:
        d = atan2_16(dy, dx) - heading                # int, heading sign-extended
        if d >= 0x4000:       d = 0x7fff - d
        elif d < -0x3fff:     d = -0x8000 - d
        heading = (s16)(heading + d / 5)              # C integer division
    dist = sqrt(dx*dx + dy*dy)
    eta  = t + dist * 0.0049248165
    if eta < slotTime[cur]: slotTime[cur] = eta
    left = slotTime[cur] - t
    speed = dist / left
    if left > 1/60:
        swarm.z += ((tgt.z + 48.0) - swarm.z) / (left * 60.0)
    if slotTime[cur] <= t + 0.03333333:               # 0x3d088888: arrival
        n += 1
        slotTime[cur] = (float)stat(2, level, owner, cap 10) + 0.03333333
        nextTick[cur] = t
        m = pool_new(0x20)                            # SpellTag marker
        if m: m = {level 1, skill 0, owner = tgt, own generator = one SHARED draw >> 16,
                   +0x18 = caster, +0x1c = 0x57}
        creature_addSpell(tgt, m)                     # ignores a null m
        sound spel_is_tagar_hit.anm at tgt
        cur = -1
        tEnd += 0.50100195                            # 0x3f0041aa
        speed = 203.05324
# --- wander and move (also runs with no target) ---
r = Spell_rand()
if r < 0x4906:                                        # 18694 / 65536
    wander = (s16)trunc((Spell_rand() / 65536.0 - 0.5) * 7938.0)
a = (s16)(heading + wander)
swarm.x += cos16(a) * speed * (1/60)
swarm.y += sin16(a) * speed * (1/60)
emit the cloud                                        # presentation, but draws: see below
```

Notes on the listing (all Observed in 0x30cbc8–0x30d0ac):

- The reflection of the heading error (`0x7fff − d`, `−0x8000 − d`) is what the code does; it
  is not a wrap to ±180°. A target more than a quarter turn off the heading is steered to as
  if it were mirrored.
- A victim's infestation time is the *absolute* clock value `stat 2 + 1/30`. A victim reached
  at t = 1.5 s with stat 2 = 3 is infested for 1.5 s. With the hop time bounded by the
  120-unit search radius (0.59 s) and `tEnd` starting at 2.0 s, a late victim always gets
  less than the printed duration.
- `tEnd` grows by 0.501 s per victim reached, so the hunt window is 2.0 + 0.501 × n seconds.
- `dist / left` is computed even when `left` is 0; the result is only used when no arrival
  happens in the same frame, and an arrival resets `speed`.

### Target selection — `SpellTagarsInsects_pickTarget` 0x30d998

`valid(o, markerTest)` (0x30db9c): `o` exists, has neither object flag 0x1 nor 0x8, the
owner's virtual slot 20 ("is enemy") returns non-zero for it, and — with `markerTest` — it
does not carry a `SpellTag` with id 0x57 whose caster field is this owner
(`creature_findSpell` 0x11a788).

- **First victim** (`n == 0`): `world_collectObjectsInArc(radius 120, arc 90°, width 0,
  swarm position, heading, list, owner)` (see "World queries" in the shared section: a
  square box of half-size 120 clipped to a 90° wedge, creatures only, enemies of the owner
  only). The **first entry of the returned list** that passes `valid(…, true)` is taken. The
  list head is the nearest creature in 2-D; the rest is in the order that function leaves
  them, which is not sorted.
- **Later victims** (`n > 0`): `world_collectInSphere(120, swarm position)` — every object
  with flags & 0xd == 0 whose centre is within 120 + its radius in 3-D. Each entry must pass
  `valid(…, true)` and must not already be in one of the `n` handle slots; among those the
  one with the **smallest 3-D squared distance** to the swarm is taken (strict `<`, so the
  first of equals in list order wins; start value 1,000,000).

A victim whose marker has been removed (its time ran out) can be picked again by the same
swarm only if it is not still referenced by a handle slot — it always is, because slots are
never cleared before the spell dies. So each creature is infested at most once per cast.

### Per-victim work — `SpellTagarsInsects_tickVictims` 0x30d558

Runs first in every run, with the clock value of the previous frame. For slot i in 0…n−1:

```
if handle[i] empty or its object gone: continue
if slotTime[i] < 0: continue
if slotTime[i] <= t  or  not valid(victim, markerTest = false):
    marker = creature_findSpell(victim, 0x57, owner); if marker: destroy it
    slotTime[i] = -1
    continue
victim flash quad 2 (+0x98…+0x9e) = {100, 0, 0, 4}
active += 1
if nextTick[i] <= t:
    if owner exists and is a player:
        (lo, hi) = statRange(0.2, stat 1, level)          # slot 8, tier 1, no randomising
    else:
        v = stat(1, level, owner, cap 0)                  # tier 2
        hi = trunc(v + v * 0.19999999) ; lo = trunc(v - v * 0.19999999)
    damage_apply(min = lo, max = hi, victim, attacker = owner, attack = 100000,
                 0, 0, flags = 0x4000000, descriptor = none, noCrit = 0)
    nextTick[i] += 1.0
5 particles on the victim                                  # presentation; draws, see below
return active > 0
```

- First tick: on the frame after arrival (`nextTick` was set to the arrival-frame clock,
  which is what the next call sees). Then one tick each time the clock passes a further
  whole second; the clock is a float sum, so the tick frames are 60 or 61 apart depending
  on rounding. With stat 2 = 3 and arrival at t ≈ 0.4 s a victim takes 3 ticks.
- The hit cannot miss on attack rating (100000) but goes through the whole of
  `damage_apply` (`docs/gameplay.md` §2.5): mitigation for player victims, the base roll
  (one shared draw when lo < hi), block and Spirit Shield, both hit rolls, the always-drawn
  proc rolls, critical-hit bonus when the owner is a player, and so on.
- Flag 0x4000000 is not read by `damage_apply`. `Player_processDamage` tests it at
  0x1b2cc0 (decompile line 277): with it set, the "shrug off" exit after the stagger roll is
  not taken, so a player victim that reaches that test is always staggered (Inferred from
  that one test; the roll itself is still drawn).
- A dead or no-longer-hostile victim is dropped at once and its marker destroyed.

### End and clean-up

- The spell destroys itself on the first frame where `tEnd <= t` and no slot is active.
  With no victim that is run 121 (2.0166 s). It also dies with its owner
  (`Creature_dtor` deletes attached spells).
- Destructor 0x30caa4: destroys the marker of every slot whose victim still exists, clears
  the eight handles, the base back-list, frees the block.
- The `SpellTag` marker has no behaviour of its own (run is the empty base function). Its
  destructor is 0x3d10b0.

### Random draws, in order

| When | Generator | Count | Use |
|---|---|---|---|
| spell constructor | shared | 1 | seeds the spell's own generator |
| each arrival | shared | 1 (0 if `pool_new` failed) | seeds the marker's generator (never used) |
| each damage tick | shared | whatever `damage_apply` draws | |
| every run with `t < tEnd` and `n < limit`: tickVictims first | own | per active victim: 5 particles × (3 per try, repeated while the point is outside the unit sphere) | particle velocity |
| same run, after the target code | own | 1, and 1 more when the first is below 0x4906 | **wander angle — gameplay** |
| same run, cloud | own | 50 particles × [3 per try until inside the unit sphere; 3 per try until inside the unit sphere; 1; 1] | particle velocity, offset direction, offset length, particle type |
| runs with `t >= tEnd` or `n >= limit` | own | only the tickVictims draws | |

The wander draws and the particle draws come from the same generator, so a rebuild that
wants the same swarm path has to perform the particle draws — including the two rejection
loops, whose pass/fail test is `1.0 < x² + y² + z²` in single precision with
x = (r / 65536) × 2 − 1 — even where it draws nothing. No cosmetic-generator or 0x404468
draw occurs in this class.

### Presentation only

Cast and hit sounds; 50 + 1 particles per frame around the swarm position (three particle
types chosen by the last draw: ≤ 15000, ≤ 32000, else); 5 particles per infested victim
per frame circling at the victim's radius; the red flash on the victim (flash quad 2, which
`Creature_run` fades by 2 per frame). The cloud's size ramps up over the first 0.394 s
(`min(1, t × 2.5380647)`).

### Per-machine state

- Nothing in the class reads the camera, the local slot, pads, audio or the cosmetic
  generators. `g_simFrame` is used only for particle angles.
- Prediction copy: skill flag bit 0 is clear, so `Player_castSkill` never calls the cast for
  the copy. Queries cannot return the copy (FINDINGS G6).
- Non-player caster: tier 2 numbers, the truncating ±20 % spread instead of the rounding one,
  level clamp 10 on statistics 0 and 2, no player-record access anywhere. The knight passes
  level = its virtual slot 35 = trunc(level-wide monster level × 0.29999998).
- The damage ticks depend on the float clock. Two implementations that accumulate 1/60
  differently will tick on different frames.

### Functions read

0x30c5d8 constructor, 0x30c644 initStats, 0x30c700 canUse, 0x30c708 cast, 0x30c7d0
describeRank, 0x30c928 manaCost, 0x30c95c spell constructor, 0x30caa4 destructor, 0x30cbc8
run, 0x30d558 tickVictims, 0x30d998 pickTarget, 0x30db9c valid, 0x3d10b0 marker destructor,
0x11a788 `creature_findSpell`, call site 0x272b94–0x272c00 in `Horsemen_run`.

Not determined: whether a dead *player* caster still has its spells run (that is
`Player_run`'s business); what the knight's level works out to in the arena (needs the
level's monster level).

## 88 — Drowsy (`drowsy`)

**Fully specified** for the skill's own code. The nine places that apply the slow-down
factor are in the creature and player areas; only one (`Creature_stepAnim`) was opened.

### Identity

| | |
|---|---|
| Skill class / table / object | `SkillDrowsy` / 0x51bac0 / 0x6e3830 |
| Kind, flags, recast | 0, 0, 30 |
| Tree | shaman (class 6): base level 3, needs skill 61 |
| Other casters | none found |
| Creates | one `SpellDrowsy` (0x34 bytes, table 0x51bb48) **on each victim**; one `LightEffect`. The cast returns 0, so nothing is attached to the caster |

### Statistics (every lookup in this class is slot 10, i.e. tier 1, whoever casts)

| Stat | Meaning | Formula | Ranks 1–20 |
|---|---|---|---|
| 0 | most creatures affected by one cast | 2 + 0.50199896 × (L−1) [0x3f008301] | 2 3 3 4 4 5 5 6 6 7 7 8 8 9 9 10 10 11 11 12 |
| 1 | seconds the effect lasts | 4 + 0.251 × (L−1) [0x3e808312] | 4 4 5 5 5 5 6 6 6 6 7 7 7 7 8 8 8 8 9 9 |
| 2 | percent chance per victim | 50 + 1.503019 × (L−1) [0x3fc062ed] | 50 52 53 55 56 58 59 61 62 64 65 67 68 70 71 73 74 76 77 79 |
| 3 | speed while affected, percent | 60 − 0.001003 × (L−1) [0xba837718] | 60 at every rank |
| 4 | mana | 21 + 4.008978 × (L−1) [0x4080498c] | 21, 25 … 97 |

### Cost and limits

Mana = statistic 4. Base canUse (always allowed).

### Cast — 0x30e1f0 (level, caster, pos, facing)

1. Sound `spel_ew_shock.anm` (sic) on the caster; both caster flash quads =
   {0x40, 0x40, 0x80, 0x2e} (the caster pointer is used without a null test).
2. `LightEffect` at `pos` + 36 up, following the caster — one shared draw.
3. `max` = getStat(0, level).
4. `list = world_collectObjectsInArc(radius 240, arc 120°, width 0, pos, facing, no owner
   filter)`.
5. Walk the list in order until it ends or `max` victims have been taken. An entry is taken
   when all hold: the caster's virtual slot 20 calls it an enemy (skipped if the caster is
   null); it does not have object flag 0x1000000 (friendly to players);
   `creature_bossRank` (0x10d940) is 0 — neither a `MiniBoss` nor one of the named bosses;
   its timer at +0x31a is below 1 (it is not already affected). For each taken entry:
   `pool_new(0x34)`, construct a `SpellDrowsy` on it (one shared draw), attach it to the
   victim. A failed allocation still counts as taken.
6. Return 0.

### `SpellDrowsy`

| Offset | Type | Meaning | Initial |
|---|---|---|---|
| +0x0c | Creature* | the **victim** (Spell base owner field) | |
| +0x18 | float | clock, seconds | 0 |
| +0x1c | float | clock value when the current phase began | 0 |
| +0x20 | s32 | duration in seconds = getStat(1, level) | |
| +0x24 | s32 | phase: 0 wind-up, 1 failed, 2 working | 0 |
| +0x28 | float[3] | heights of the three floating letters (draw data) | 0, −16.9618, −33.9236 |

Run (0x30e6f0), once per frame of the victim:

```
clock += 1/60
if victim has object flag 8 (dead): destroy the spell; return
phase 0:
    15 particles                                   # own generator: 2 + 3 per try each
    if clock < 0.5: return                         # true for the first 30 runs
    r = Spell_rand()                               # run 31
    if (r % 100) < getStat(2, level):
        phase = 2 ; phaseStart = clock
        victim.+0x31a = (s16)(duration * 60)
    else:
        phase = 1 ; phaseStart = clock
phase 1:
    15 particles
    if clock - phaseStart > 0.17799999: destroy the spell
phase 2:
    if clock - phaseStart > (float)duration: destroy the spell; return
    advance the three letter heights by 0.32423055 (wrap to 0 above 51.61134)
    both victim flash quads = {0x40, 0x40, 0x80, 0x2e}
    if net game and victim is a player in a local slot: g_forceGhostRebase = 1
```

What "working" means: the victim's field +0x31a is one of the s16 frame timers that
`Creature_run` counts down. While it is above 0 **and** the creature carries a
`SpellDrowsy`, nine functions multiply a speed by `getStat(3, level) × 0.01`
(`SpellDrowsy_getStat3Fraction` 0x30ef08): the animation rate in `Creature_stepAnim`
(0x116314, read) and in `Player_animStep` (0x1b9560), and the movement speed in
`Creature_moveTo` and its relatives (0x114af8, 0x11532c, 0x11582c, 0x115dbc),
`Player_move` (0x1b41b4) and two monster functions (0x2bf96c, 0x2c0f4c) — call sites
Observed, the last eight bodies not read. So the effect is a slow-down to 60 % for
`duration` seconds; nothing in this class stuns, roots or makes the victim lose its target.

The timer also blocks a second application (step 5 of the cast) until it has run out.
Timer and spell end within a frame or two of each other; the factor needs both.

### Random draws

| When | Generator | Count |
|---|---|---|
| cast | shared | 1 (`LightEffect`) + 1 per victim (Spell constructor) |
| each victim, runs 1–31 | victim spell's own | 15 particles × (2 + 3 per try) per run |
| each victim, run 31 | victim spell's own | 1 — **the success roll** |
| phase 1 | own | particles, as above |

The roll comes out of the same generator as 31 frames of particle draws, so those — with
their rejection loop on `1.0 < x² + y² + z²` — have to be reproduced to get the same
outcome.

### Presentation only

Sound, light, the caster's and victims' blue flash, the wind-up and failure particle
bursts, and the three letters drawn above an affected creature by `SpellDrowsy_draw`
(0x30ed24, Spell slot 3, called from `Creature_draw`). The draw function reads the heights
the run function advances and writes nothing.

### Per-machine state

- `net_isLocalSlot` is read in phase 2, only to set `g_forceGhostRebase` (0x402797), which
  is itself per-machine prediction state (`docs/skills.md`, table (c)). No shared state
  depends on it.
- A player can be a victim only where the caster's "is enemy" test accepts players (PvP
  mode A, other team).
- Every statistic is tier 1 regardless of the caster, and there is no player-record access.

### Functions read

0x30e0f0, 0x30e15c (through the table dump), 0x30e1f0, 0x30e5ec, 0x30e620, 0x30e6f0,
0x30ed24, 0x30ef08, `Creature_stepAnim` 0x1162b0. Not read: describeRank 0x30e4c4 and the
other eight users of the factor.

## 89 — Poison Bolt (`poisonbolt`)

**Fully specified**, including the gas cloud it leaves (`poisonGasSpell`, a gameplay-area
class, read here because this skill is its main user).

### Identity

| | |
|---|---|
| Skill class / table / object | `SkillPoisonBolt` / 0x51bc08 / 0x6e3898 |
| Kind, flags, recast | 0, 0, 30 |
| Tree | shaman (class 6): base level 1, needs skill 60 |
| Other casters | none found |
| Creates | `PoisonBolt`, a `Projectile` of 0xb8 bytes, table 0x51bb78; on impact a `poisonGasSpell` (0x70 bytes, table 0x50d500). The cast returns 0 |

### Statistics (all lookups are slot 10 / slot 8, tier 1, whoever casts)

| Stat | Meaning | Formula | Ranks 1–20 |
|---|---|---|---|
| 0 | impact damage before the ±20 % spread | 26 + 5.0019617 × (L−1) [0x40a01012] | 26, 31 … 121 |
| 1 | cloud radius in 12-unit steps | 1 + 0.251 × (L−1) [0x3e808312] | 1 1 2 2 2 2 3 3 3 3 4 4 4 4 5 5 5 5 6 6 |
| 2 | poison value the cloud applies | 12 + 2.0059848 × (L−1) [0x4000620e] | 12, 14 … 50 |
| 3 | seconds: cloud life, and the poison timer set by a direct hit | 2 + 0.25100097 × (L−1) [0x3e808333] | 2 2 3 3 3 3 4 4 4 4 5 5 5 5 6 6 6 6 7 7 |
| 4 | mana | 8 + 2.00097 × (L−1) [0x40000fe4] | 8, 10 … 46 |

### Cast — 0x30f168 (level, caster, pos, facing)

Caster flash: both quads = {0, 0x80, 0, 0} (caster used without a null test).
`pool_new(0xb8)`; construct `PoisonBolt(pos, facing, level, caster, skill)`. Returns 0.

### `PoisonBolt`

Constructor 0x30f398: `Projectile_ctor` (a GameObject: **one shared draw**; object flags
|= 0x4081; radius 12; owner handle at +0x4c), then:

| Offset | Type | Meaning | Initial |
|---|---|---|---|
| +0x38 | s16 | heading | `facing` |
| +0x90 | handle | owner (second handle to the caster) | caster |
| +0x94 | handle | homing target | see below |
| +0x98, +0x9c | Skill*, s16 | skill and level | |
| +0xa0 | Vec3 | velocity, units per second | 350 × (cos16, sin16)(facing), 0 |
| +0xac | s32 | expiry frame | frame + 113 |
| +0xb0 | s32 | homing starts after this frame | frame + 11 |
| +0xb4 | s32 | "has hit" flag | 0 |

Homing target (only with a caster): `world_collectObjectsInArc(280, 60°, 0, pos, facing, no
filter)`; the first list entry the caster's slot 20 calls an enemy. Then
`obj_runEveryFrame` and the launch sound on the object. An embedded light record is
presentation.

Run 0x30f800, once per frame:

```
if target handle set and homingStart < frame:
    d = atan2_16(tgt.y - y, tgt.x - x) - heading          # int, not wrapped
    if |d| < 0x222: heading += d
    elif d < 1:     heading -= 0x222
    else:           heading += 0x222                       # 3 degrees per frame
    velocity = 350 * (cos16, sin16)(heading), 0
r = obj_moveAndCollide(this, velocity)       # shared section; calls onHit for what it touches
if (r & 2) and hasHit: expiry = 0
if (r & 1): expiry = 0                       # terrain
if frame < expiry: trail particles; return
sound; burst(); destroy the object
```

`onHit(other)` 0x310028 (GameObject slot 6):

```
if hasHit: return
if no owner:
    if other is not a creature: hasHit = 1     # an ownerless bolt stops on props, nothing else
    return                                     # (creatures: nothing happens at all)
if not owner.isEnemy(other): return            # props, allies, corpses: the bolt flies on
if other is a creature with creature flag 0x200 (blocking): return   # passes a blocker
(lo, hi) = statRange(0.2, stat 0, level)       # slot 8
flags = 0x10040; if level > 10: 0x50040; if level > 15: 0x90040
damage_apply(lo, hi, other, owner, 100000, 0, 0, flags, no descriptor, 0)
if other is a creature:
    Creature_setEffectTimer(seconds = getStat(3, level), other, which = 3, source = owner)
hasHit = 1
```

- Timer 3 is the creature field +0x34c, the first damage-over-time timer; `Creature_run`
  deals (+0x358 … +0x35a) / 10 every 32nd frame while it runs (`docs/creatures.md`). **The
  direct hit sets the timer but not the two damage fields**; those are written only by a
  type-0x17 descriptor slot, which the cloud supplies on its next tick.
- Flags: 0x40 unblockable; 0x40000 / 0x80000 select the knock-back speed of a killing blow
  (100 / 150, `docs/creatures.md` "Pending damage"); 0x10000 is passed on to take-damage.
- Reach: 113 frames at 350 units/s = 659 units.

`burst()` 0x3101cc (named `PoisonBolt_burst` in the new symbol file): if the owner handle
is set and stat 1 × 12 > 0, `pool_new(0x70)` and
`poisonGasSpell_ctor(position, life = getStat(3) × 60 frames, radius = getStat(1) × 12, 0,
owner, damage = getStat(2))` — a GameObject, **one shared draw**. Then 321 particles from
the bolt's own generator (the bolt is destroyed right after).

### `poisonGasSpell` (constructor 0x202de8, run 0x1fd0f0)

Fields: +0x4c owner handle, +0x5c end frame, +0x60 target radius (at least 10), +0x64
current radius (starts at 10.0), +0x6c value. Object flags |= 3. Run, once per frame:

```
if frame >= endFrame: destroy; return
if radius < targetRadius: radius += 0.5
(targetRadius / 10) particles                              # own generator
if frame % 30 == 0 and owner handle set:
    h = trunc(radius)
    list = world_collectObjectsInBox(position ± h on all three axes, at most 63)
    for o in list: if owner.isEnemy(o):
        descriptor slot 0 = {0x17, value, value, 0}
        damage_apply(0, 0, o, owner, 100000, 0, 0, flags 0x1000040, descriptor, 0)
```

The 0x17 slot writes `value` into the victim's +0x358 and +0x35a and starts the poison
status with strength 5 − 5 × poison resistance (`docs/gameplay.md` §2.2); flag 0x1000000
suppresses the floating number. The cloud is a cube, ticks on global frame multiples of 30,
and dies with its owner handle.

### Random draws

| When | Generator | Count |
|---|---|---|
| cast | shared | 1 (bolt constructor) |
| first time the bolt is under terrain over water | bolt's own | 1 (unused value; inside `obj_moveAndCollide`) |
| each frame of flight | bolt's own | 36 particles × (3 per try + 1 + 3 per try); nothing gameplay reads it |
| impact on a creature | shared | those of `damage_apply` |
| end of flight | shared | 1 (cloud constructor), 0 without owner or pool block |
| cloud, each frame | cloud's own | particles only |
| cloud, each tick per enemy | shared | those of `damage_apply` (none from the 0x17 slot itself) |

### Presentation only

Flash, sounds, the bolt's light and two-colour trail, the burst, the cloud particles.
`PoisonBolt_draw` (0x30f6b4) writes nothing.

### Per-machine state

None found in cast, constructor, run, onHit, burst or the cloud. `obj_moveAndCollide` plays
a splash and disturbs the water surface (presentation). Every statistic is tier 1 regardless
of the caster.

### Functions read

0x30f06c, 0x30f0d8, 0x30f168, 0x30f364, 0x30f398, 0x30f608 (skimmed), 0x30f800, 0x310028,
0x3101cc, `obj_moveAndCollide` 0x1509f8, `Projectile_ctor` 0x150e48,
`Creature_setEffectTimer` 0x118950, `poisonGasSpell` 0x202de8 and 0x1fd0f0.
Not read: describeRank 0x30f23c.

## 90 — Summon Badger (`summonbadger`)

**Fully specified** for the skill and its spell. The summoned creature (`CastBadger`) is a
monster class described in `docs/monsters-2.md` ("Family: badgers").

### Identity

| | |
|---|---|
| Skill class / table / object | `SkillSummonBadger` / 0x51bc90 / 0x6e3900 |
| Kind, flags, recast | 0, 0, 30 |
| Tree | shaman (class 6): base level 15, needs skill 87 |
| Other casters | none found (the code has a non-player branch) |
| Creates | a `CastBadger` creature (0x3d0 bytes, constructor 0x244e4c); a `SpellSummonBadger` (0x20 bytes, table 0x51bd18) on the caster; one `LightEffect` |

### Statistics

| Stat | Meaning | Tier 1 | Tier 2 |
|---|---|---|---|
| 0 | the badger's level (level clamped to 10 for non-player casters) | 1 + 1 × (L−1) = L | the same |
| 4 | mana | 120 + 8.00093 × (L−1) [0x410003cf] → 120, 128 … 272 | — |

### Cost and limits

Mana = statistic 4. canUse (0x310690): there must be no object in the world registered
under this caster's badger name. The name is `badglightp1` … `badglightp4` for a player in
slot 0–3 (a player with a slot above 3 is refused) and `badglightm` for every non-player —
so one badger per player, and one shared by all monsters. The lookup is
`world_findObjectByName`, which also finds dead and delete-queued objects (FINDINGS D23 for
the skeleton's equivalent).

### Cast — 0x3106f4 (level, caster, pos, facing)

```
spot = pos + (cos16, sin16)(facing) * 5.999953 * 12.0          # about 72 units ahead
spot.z = terrain_height(48.0, world, spot)
if |spot.z - caster.z| > 24.0:                                 # compared in double precision
    (p, ok) = world_findFreeSpot(centre = caster position, range 71, radius 24, anyHeight 0)
    if ok: spot = p                                            # up to 50 tries, 3 SHARED draws each
lvl = stat(0, level, caster, cap 10)
props = "name=badglightm" if caster is not a player
        "name=badglightp<slot+1>" if caster slot < 4, else none
b = pool_new(0x3d0); if none: return 0
CastBadger_ctor(b, "CastBadger", spot, facing, props, lvl)      # its draws: docs/monsters-2.md
b.flags |= 0x4002            # transient; not drawn until the spell below clears bit 2
b.typeName = "CastBadger"
b.cflags |= 0x1000000        # corpse sinks and is deleted
if caster is a player:
    b.+0x5a = caster slot    # the slot it follows; arena kill credit reads this byte
    b.cflags |= 0x400000     # follow a player, standing ahead
    Creature_setCharm(b, frames = -1 (permanent), team = caster's virtual slot 37)
    b.pointblankrange (+0x3ac) = 400
    b.setHomeRange(500)      # virtual slot 34
caster flash: both quads = {0x54, 0xc0, 0x33, 0x41}
LightEffect at spot + 36 up, following the caster              # one shared draw
sound spel_gatescroll.anm at pos
s = pool_new(0x20); if s: SpellSummonBadger_ctor(s, level 1, caster, skill, b)   # one shared draw
return s
```

The badger is in the world grid from the moment it is constructed (flag 0x2 is set after
linking), so it can be targeted and hit during the second in which it is not yet drawn.

### `SpellSummonBadger`

+0x18 handle to the badger, +0x1c clock. Run (0x310cd0), on the caster:

```
if badger handle empty: destroy the spell; return
f = clock if clock <= 1.0 else 2.0 - clock
if f < 0: destroy the spell; return
clock += 1/60
if f <= 0: return
if clock > 1.0: badger.flags &= ~2            # becomes visible after one second
trunc(f * 38) particles on the badger's model sample points (own generator)
```

The spell lives two seconds and does nothing else. `SpellSummonBadger_draw` (0x311034, Spell
slot 3) adds glows and writes nothing.

### Random draws

| When | Generator | Count |
|---|---|---|
| cast, only when the spot ahead is more than 24 units above or below the caster | shared | 3 per try of `world_findFreeSpot`, at most 50 tries |
| cast | shared | the creature's constructor (GameObject base 1 + what `Creature_ctor` and `Creature_setStats` draw), 1 `LightEffect`, 1 Spell |
| run | own | 3 per try per particle; nothing else reads it |

### Per-machine state

- The player-slot reads (canUse, the property choice, +0x5a) are behind the is-player test
  (tests at 0x31069c, 0x3108e4, 0x310974, each just ahead of the read).
- No camera, local-slot or cosmetic-generator read.
- A non-player caster gets an unfollowing, uncharmed badger named `badglightm` — hostile to
  whatever its own class code decides. No monster was found casting the skill.

### Functions read

0x3105e0, 0x31064c, 0x310690, 0x3106f4, 0x310c08, 0x310c3c, 0x310cd0, 0x311034 (scan).
Not read: describeRank 0x310b5c; the `CastBadger` class itself (see `docs/monsters-2.md`).

## 91 — Raise Army (`raisearmy`)

**Fully specified** for the skill's own code. What the factory and each monster constructor
do when a corpse is re-created is theirs (`docs/objects.md`, `docs/monsters.md`).

### Identity

| | |
|---|---|
| Skill class / table / object | `SkillRaiseArmy` / 0x51beb8 / 0x6e3968 |
| Kind, flags, recast | 0, 0, 30 |
| Tree | shadowknight (class 2): base level 30, needs skill 11 |
| Other casters | none found |
| Creates | `SpellRaiseArmy` (0x34 bytes, table 0x51bf40) on the caster; one `LightEffect`; one new creature per corpse raised |

### Statistics (every lookup is slot 10, tier 1)

| Stat | Meaning | Formula | Ranks 1–20 |
|---|---|---|---|
| 0 | radius in 12-unit steps | 5 + 0.50098795 × (L−1) [0x3f0040bf] | 5 6 6 7 7 8 8 9 9 10 10 11 11 12 12 13 13 14 14 15 |
| 1 | most corpses raised | 2 + 0.17499799 × (L−1) [0x3e3332ac] | 2 2 2 3 3 3 3 3 3 4 4 4 4 4 4 5 5 5 5 5 |
| 2 | percent of the original's maximum hit points the raised creature starts with | 10 + 1.001992 × (L−1) [0x3f804146] | 10, 11 … 29 |
| 4 | mana | 160 + 7.000992 × (L−1) [0x40e00820] | 160, 167 … 293 |

### Cost and limits

Mana = statistic 4. canUse (0x3134b0): the caster must not already carry a `SpellRaiseArmy`
(one wave at a time; the wave lasts about a second).

### Behaviour

Cast (0x3134e4): caster flash both quads = {0x80, 0x32, 0, 0x32}; sound at `pos`;
`LightEffect` at `pos` + 36 following the caster (shared draw); `pool_new(0x34)`,
construct, return the spell.

`raisable(c)` (0x313b38, `SpellRaiseArmy_isRaisable` in the new symbol file) — all of:
object flag 0x8 (dead) set, 0x40 (player) clear, 0x2 clear; the animation state's flag word
(+0x11a) has 0x80 (its clip has finished — the corpse is lying still); creature flags
0x1, 0x800, 0x1000000, 0x4000000 and 0x100000000 all clear (not a `MiniBoss`, not neutral, not
already sinking, not friendly, not a revived or loaded corpse); `creature_bossRank` is 0;
object flag 0x1000000 clear.

Constructor (0x3137d8): Spell base (shared draw); centre (+0x1c) = caster position;
R = getStat(0) × 12; duration (+0x2c) = R × 0.005907856 seconds (the wave travels at
169.27 units per second); clock (+0x28) = 0; count (+0x30, s16) = 0.
`world_collectObjectsInBox(centre ± R on three axes, at most 255)`; every creature in it
that is `raisable` goes into the candidate list (+0x18). Linking pushes at the head, so the
list is in **reverse** box order.

Run (0x31399c), once per frame:

```
f = 1.0 - (duration - clock) / duration
if f > 1.0: destroy the spell; return
r = f * 12.0 * getStat(0)
206 particles on the ring                      # one own draw each; nothing else reads it
raise(r)
clock += 1/60
```

`raise(r)` (0x313bd4, `SpellRaiseArmy_raiseInRing`): for each candidate, in list order:

```
if corpse gone: drop the entry; continue
if dist2D(centre, corpse) - corpse.radius > r: continue          # the ring has not arrived
if not raisable(corpse): drop the entry; continue
if corpse.typeName:
    n = world_createObject(corpse.typeName, corpse position, corpse facing)
    if n and n is a creature:
        n.hp = getStat(2) * 0.01 * corpse.maxHp ; if n.hp < 1.0: n.hp = 1.0
        obj_runEveryFrame(n)
        n.cflags |= 0x8002000101400000   # active; dies when its charm ends; gives no loot or
                                         # experience; corpse sinks; follows a player
        n.+0x5a = (u8) caster.+0x3c8     # NO is-player test
        Creature_setCharm(n, 3600 frames, team = caster's virtual slot 37)
        n starts in the corpse's pose: its animation state is emptied and the corpse's top
          track is pushed with the same weights and time; then n.setState(0)
        n's weapon holder copies, for hand 1 and hand 2, what the corpse's holder reports
          (holder slot 15 -> slot 1, slot 16 -> slot 8, which rebuilds an element descriptor
          and so can make one shared draw per hand)
        n.variantBits (+0xe8) = corpse's, unless the type name starts with "WoodElf" or
          "evilwoodelf"; n's hide mask is rebuilt
        type names starting with "ant": n.+0x3e0 = corpse.+0x3e0 and the tint preset follows it
        n flash: both quads = {0x80, 0x32, 0, 0x32}
        corpse.+0x2f4 = 0 ; corpse.cflags |= 0x1000000      # the old body sinks and can
                                                            # never be raised again
sound at the corpse; drop the entry
count += 1
if getStat(1) <= count: duration = clock; return             # ends the spell next frame
```

- The count goes up, and the entry is consumed, even when the factory returned nothing.
- A raised creature is a fresh instance of the same class at 10–29 % health, charmed onto
  the caster's team for 60 seconds, after which the 0x2000000000000 flag kills it.
- The wave only sees corpses that existed and lay still when the spell was cast.

### Random draws

| When | Generator | Count |
|---|---|---|
| cast | shared | 1 (`LightEffect`) + 1 (Spell) |
| each corpse raised | shared | everything the class constructor draws (GameObject base, hit-point roll, class extras), plus up to 2 for the weapon elements |
| each frame | own | 206 |

### Per-machine state

- **Unguarded player index**: `raise` reads `caster + 0x3c8` as a byte for the "followed
  slot" without testing that the caster is a player (0x313d74). Harmless for the only
  caster the trees allow.
- No camera, local-slot, cosmetic-generator or option read. Every statistic is tier 1.

### Functions read

0x3133cc, 0x313438, 0x3134b0, 0x3134e4, 0x3137a4, 0x3137d8, 0x31399c, 0x313b38, 0x313bd4.
Not read: describeRank 0x31368c; `world_createObject` 0x14f6c8 and the weapon-holder slots
15 and 16 beyond their call sites.

## 94 — Spirit Shield (`spiritshield`)

**Fully specified** (gameplay). The two particle helpers were read only far enough to see
what they write.

### Identity

| | |
|---|---|
| Skill class / table / object | `SkillSpiritShield` / 0x51c138 / 0x6e3aa0 |
| Kind, flags, recast | 0, 0, 30 |
| Tree | shaman (class 6): base level 16, needs skill 86 |
| Other casters | `FemaleDarkElf` (state 8, on itself, table load at 0x25a25c), `Marr` (`Marr_setState` cases 0x17 and 0x18, on itself); both pass level = slot 35 and attach the result to themselves |
| Creates | `SpellSpiritShield` (0x24 bytes, table 0x51c1c0) on the caster; one `LightEffect` |

### Statistics

| Stat | Meaning | Tier 1 | Tier 2 (level clamped to 10 in every lookup) |
|---|---|---|---|
| 0 | duration, seconds | 10 + 1 × (L−1) | 10 + 1 × (L−1) → at most 19 |
| 1 | chance in percent that a hit is absorbed | 10 + 2.0009959 × (L−1) [0x40001051] → 10, 12 … 48 | 20 + 1 × (L−1) → at most 29 |
| 4 | mana | 85 + 10.0008745 × (L−1) [0x41200395] → 85, 95 … 275 | — |

### Cost and limits

Mana = statistic 4. canUse (0x314e1c): the caster must not already carry a
`SpellSpiritShield` (type test over the attached-spell list, `creature_findSpellByType`).
`FemaleDarkElf` and `Marr` make the same test themselves before casting.

### Behaviour

Cast (0x314e50): `pool_new(0x24)`, construct, return the spell (the caller attaches it to
the caster).

Constructor (0x31500c): Spell base (shared draw 1); phase (+0x18) = 0; clock (+0x1c) = 0;
a `LightEffect` at the caster's visual position + 36 up, following the caster (shared draw 2,
skipped if the pool is empty); sound `spel_is_spiritshield.anm`.

| Offset | Type | Meaning |
|---|---|---|
| +0x18 | s32 | phase: 0 idle, 1 dissolving, 2 gone, 3 re-forming |
| +0x1c | float | clock in seconds (+1/60 per run) |
| +0x20 | float | clock value at which the current phase ends |

Run (0x3151b4), every frame:

1. Owner flash quad 1 (+0x90…+0x96) = {27, 17, 30, 38}.
2. clock += 1/60.
3. Phase 0: if `(float)stat(0, level, owner, cap 10) < clock` the spell destroys itself.
   Phases 1–3 do not test the duration, so a shield that absorbs a hit just before it runs
   out lives up to 0.75 s longer (but absorbs nothing more, see below).
4. Phase 1: particles (helper 0x31539c); once the dissolve is more than half done the owner
   gets object flag 0x2 (not drawn by the grid walk — a draw-only flag, `docs/objects.md`).
   When clock ≥ phase end: phase 2, phase end = clock + 0.063999996.
5. Phase 2: when clock ≥ phase end: phase 3, phase end = clock + 0.492997.
6. Phase 3: particles (helper 0x315610); flag 0x2 is cleared once more than half done. When
   clock ≥ phase end: phase 0.

Absorbing a hit — `SpellSpiritShield_playHitEffect` 0x315888 (the name in the symbol file
undersells it: this is the roll). `damage_apply` calls it for a victim carrying the spell
when the hit does not have flag 0x40 (`docs/gameplay.md` §2.5 step 12):

```
dur    = stat(0, level, owner, cap 10)
chance = stat(1, level, owner, cap 10)
if clock <= dur:
    r = shared draw (16 bit)
    if r % 100 < chance:
        if phase == 0: phase = 1; phaseEnd = clock + 0.19199899
        sound spel_is_spirithit.anm at the owner
        return 1            # damage_apply cancels the hit, or halves it with flag 0x20000
return 0
```

The shared draw is made for every qualifying hit while the clock is within the duration,
whatever the phase; a hit absorbed during phases 1–3 does not restart the animation.

### Random draws

| When | Generator | Count |
|---|---|---|
| constructor | shared | 1 (Spell) + 1 (`LightEffect`) |
| each incoming hit without flag 0x40, clock ≤ duration | shared | 1 |
| phases 1 and 3, per frame | own | 1 + 3 per try for each of up to 38 (phase 1) or 74 (phase 3) particles; nothing else reads this generator |

### Presentation only

Light, two sounds, the grey flash, the dissolve / re-form particles on the owner's model
sample points, object flag 0x2 on the owner for about 0.4 s (0.096 + 0.064 + 0.246 s).

### Per-machine state

None found: no camera, local-slot, audio or cosmetic-generator read. The owner's flag 0x2
is written from simulation code on every machine alike. Non-player casters differ only in
the tier and the level clamp.

### Functions read

0x314d40, 0x314dac, 0x314e1c, 0x314e50, 0x314fd8, 0x31500c, 0x3151b4, 0x315888 in full;
0x31539c, 0x315610 (helpers) for their writes and draws; call sites 0x25a25c, 0x2848c4,
0x284938. Not read: describeRank 0x314ef0.

## 95 — Wave of Flame (`waveofflame`)

**Fully specified.**

### Identity

| | |
|---|---|
| Skill class / table / object | `SkillWaveOfFlame` / 0x51c2a8 / 0x6e3b08 |
| Kind, flags, recast | 0, 0, 30 |
| Tree | wizard (class 4): base level 29, needs skill 13 |
| Other casters | `Cazic` (state 0xd, on animation event bit 1, when it already carries Frost Armor; level = slot 35; attached to itself; table load at 0x24bc64) |
| Creates | `SpellWaveOfFlame` (0x2c bytes, table 0x51c330) on the caster; one `LightEffect` |

### Statistics

| Stat | Meaning | Tier 1 | Tier 2 |
|---|---|---|---|
| 0 | final ring radius in 12-unit steps (level clamped to 10 for non-players) | 5 + 0.33400097 × (L−1) [0x3eab022d] → 5 5 6 6 6 7 7 7 8 8 8 9 9 9 10 10 10 11 11 11 | 5 + 0.32999998 × (L−1) [0x3ea8f5c2] → 5 5 6 6 6 7 7 7 8 8 |
| 1 | damage before the ±20 % spread | 210 + 20.004927 × (L−1) [0x41a00a17] → 210, 230 … 590 | 20 + 2 × (L−1), no clamp |
| 4 | mana | 60 + 4.9998946 × (L−1) [0x409fff23] → 60, 65 … 155 | — |

### Cost and limits

Mana = statistic 4. canUse (0x316b1c) always 1.

### Behaviour

Cast (0x316b24): `pool_new(0x2c)`; construct with a zero offset; return the spell.

Constructor (0x316d10), in order:

1. Spell base — shared draw 1.
2. centre (+0x1c, Vec3) = `Creature_getVisualPos(caster)` (+ the zero offset); clock (+0x28)
   = 0. The centre never moves afterwards.
3. Sound `spel_ew_flamewave.anm` at the centre.
4. `LightEffect` at centre + 36 up, no owner — shared draw 2 (skipped if the pool is empty).
5. Candidate list (+0x18, a handle list): `world_collectInSphere(R, centre)` with
   R = stat(0, level, caster, cap 10) × 24 (computed as ×12 + ×12). Every returned object
   that still has flags & 0xd == 0 is linked into the list. The two list reversals cancel,
   so the list is in box-query order.

The list is a snapshot: something that walks into the area later is never hit.

Run (0x317000), every frame:

```
clock += 1/60
r = clock * 6.0 * 12.0 + 20.098            # 0x41a0c8b4; the ring grows 72 units per second
if (float)stat(0, level, owner, cap 10) * 12.0 < r:
    destroy the spell; return
hitTest(r)
particles                                   # presentation
```

So the ring lives for (12 × stat0 − 20.098) / 72 seconds: 0.55 s at stat 0 = 5, 1.55 s at
11. The snapshot radius is twice the distance the ring ever reaches.

`hitTest(r)` (0x317570) walks the candidate list in order; for each entry:

```
if object gone: drop the entry
elif (dx*dx + dy*dy) - object.radius <= r*r:        # 2-D; the radius is subtracted
                                                    # unsquared, as coded
    if object is a creature:
        if object.flags & 9  or  not owner.isEnemy(object): drop the entry; continue
    # non-creatures (props, containers) are hit without any test
    if owner is a player: (lo, hi) = statRange(0.2, stat 1, level)        # slot 8, tier 1
    else: v = stat(1, level, owner, cap 0); hi = trunc(v + v*0.19999999); lo = trunc(v - v*0.19999999)
    descriptor = empty, slot 0 = {type 0x15, 10, 10, 0}                  # 10 fire damage + burn
    damage_apply(lo, hi, object, owner, 100000, 0, 0, flags 0x160, descriptor, 0)
    sound spel_ew_heatwpn_hit.anm at the object
    drop the entry                                   # each object is hit once
```

Flags 0x160 = 0x100 | 0x40 | 0x20: 0x40 makes the hit unblockable and ignores Spirit Shield;
0x100 and 0x20 are passed on to the victim's take-damage (`docs/gameplay.md` §2.4). The
descriptor's fire slot costs one shared draw and applies the burn status scaled by the
victim's fire resistance.

### Random draws

| When | Generator | Count |
|---|---|---|
| constructor | shared | 1 (Spell) + 1 (`LightEffect`) |
| each object hit | shared | those of `damage_apply` (base roll, hit rolls, proc rolls, the 0x15 slot) |
| each frame | own | per particle 1 + 3 per try; trunc(f×5) + trunc(f×65) + trunc(f×6) particles with f = min(1, r × 0.027999999). Nothing else reads this generator, so a rebuild may skip these draws |

### Presentation only

Sounds, the light, three particle rings at the ring radius (height wobble from
`sin16(g_simFrame × 0xd09)`).

### Per-machine state

None found. A non-player owner gets tier 2 and the truncating spread; Cazic's level is its
slot 35.

### Functions read

0x316a24, 0x316a90, 0x316b1c, 0x316b24, 0x316cdc, 0x316d10, 0x317000, 0x317570 (named
`SpellWaveOfFlame_hitTest` in the new symbol file); Cazic call site at 0x24bc64.
Not read: describeRank 0x316bdc.

## 96 — Frost Armor (`frostarmor`)

**Fully specified.**

### Identity

| | |
|---|---|
| Skill class / table / object | `SkillFrostArmor` / 0x51c360 / 0x6e3b70 |
| Kind, flags, recast | 0, 0, 30 |
| Tree | wizard (class 4): base level 9, needs skill 58 |
| Other casters | `Cazic` (state 0xd, event bit 1, when Summon Skeleton's canUse refuses and it has no Frost Armor; **level = trunc(level-wide monster level), not × 0.3**; table load at 0x24bbe8). `Kobold` (state 9, level = slot 35; 0x27fcd0). Both attach it to themselves |
| Creates | `SpellFrostArmor` (0x1c bytes, table 0x51c3e8) on the caster; one `LightEffect` |

### Statistics

| Stat | Meaning | Tier 1 | Tier 2 |
|---|---|---|---|
| 0 | duration, seconds (level clamped to 20 for non-players) | 10 + 0.502001 × (L−1) [0x3f008323] → 10 11 11 12 12 13 13 14 14 15 15 16 16 17 17 18 18 19 19 20 | 15 + 1 × (L−1) → at most 34 |
| 1 | percent of each hit removed (no clamp) | 20 + 2.000995 × (L−1) [0x4000104d] → 20, 22 … 58 | 30 + 1 × (L−1) |
| 2 | percent chance to strike the attacker back (no clamp) | 20 + 1 × (L−1) | 20 + 1 × (L−1) |
| 4 | mana | 41 + 5.000982 × (L−1) [0x40a0080b] → 41, 46 … 136 | — |

For Cazic the level is the whole monster level (3–36 on the first difficulty, up to about
142 on the last, `docs/data-tables.md` §5), so statistic 1 reaches 100 at level 71 and
statistic 2 at level 81.

### Cost and limits

Mana = statistic 4. canUse (0x317afc): the caster must not already carry a `SpellFrostArmor`.

### Behaviour

Cast (0x317b30): `pool_new(0x1c)`, construct, return the spell.

Constructor (0x317d1c): Spell base (shared draw 1); clock (+0x18) = 0; `LightEffect` at the
caster's visual position + 36 up, following the caster (shared draw 2); sound
`spel_ew_frostarmor.anm`.

Run (0x317ec0), every frame: clock += 1/60; if
`(float)stat(0, level, owner, cap 20) < clock` destroy the spell; otherwise set both owner
flash quads to {0x40, 0x40, 0x80, 0x11} and emit 11 particles.

Taking a hit — function 0x318264 (`SpellFrostArmor_onHit` in the new symbol file), called by
`damage_apply` for a victim carrying the spell (`docs/gameplay.md` §2.5 step 16) with the
running damage `dmg` and the attacker:

```
f = 1 - stat(1, level, owner, cap 0) * 0.01 ; if f < 0: f = 0
if attacker:
    r = shared draw (16 bit)                              # always, when there is an attacker
    if r % 100 < stat(2, level, owner, cap 0):
        x = (s16) trunc(dmg - f)                          # sic: dmg minus the factor
        descriptor = empty, slot 0 = {type 0x16, x, x, 0}
        damage_apply(0, 0, attacker, owner, 100000, 0, 0, flags 0x540, descriptor, 0)
        sound spel_ew_shockfrost_hit.anm at the attacker
        fx_spawn(10, attacker position)                   # camera-gated, cosmetic
return f                                                  # damage_apply multiplies dmg by it
```

The cold damage struck back is `trunc(dmg − f)`, where `f` is a number between 0 and 1
(0x318364: one `sub.s` of the two registers). It is therefore the incoming damage minus less
than one point, not the absorbed part. The nested call has min = max = 0, so its base roll
draws nothing; its 0x16 slot draws once and adds to the attacker's chill timer. Flags
0x540 = 0x400 | 0x100 | 0x40.

### Random draws

| When | Generator | Count |
|---|---|---|
| constructor | shared | 1 + 1 (`LightEffect`) |
| each hit on the owner that has an attacker | shared | 1, plus those of the nested `damage_apply` on success |
| each frame | own | 11 particles × (3 per try + 1); nothing else reads it |

### Presentation only

Light, sounds, the blue flash, frost particles on model sample points, `fx_spawn(10)`.

### Per-machine state

None in the class. `fx_spawn(10)` returns early away from the local camera focus but uses
only the cosmetic generator (`docs/gameplay.md` §4).

### Functions read

0x3179f4, 0x317a60, 0x317afc, 0x317b30, 0x317ce8, 0x317d1c, 0x317ec0, 0x318264; call sites
0x24bbe8 (Cazic), 0x27fcd0 (Kobold). Not read: describeRank 0x317bd0.

## 97 — Disease Blade (`diseaseblade`)

**Fully specified** for what the class itself does. What a disease modifier does on a hit
belongs to `damage_apply` (type 0x26, `docs/gameplay.md` §2.2) and to skill 29's spell,
which is outside this range.

### Identity

| | |
|---|---|
| Skill class / table / object | `SkillDiseaseBlade` / 0x51c418 / 0x6e3bd8 |
| Kind, flags, recast | 0, 0, 30 |
| Tree | shadowknight (class 2): base level 22, needs skill 49 |
| Other casters | `Bubo` casts it **with one of its allies as the caster argument** and attaches the result to that ally (table load at 0x249014); level = Bubo's slot 35, position = the ally's |
| Creates | `SpellDiseaseBlade` (0x24 bytes, table 0x51c4a0) on the caster; one `LightEffect` |

It is one of the weapon-buff family (with ids 12, 13, 14 and 26): on a player it writes a
timed modifier into the weapon item records; on a monster it switches the weapon holder's
element.

### Statistics

| Stat | Meaning | Tier 1 | Tier 2 |
|---|---|---|---|
| 0 | disease value written into the weapon (no clamp) | 21 + 2.001994 × (L−1) [0x400020ab] → 21, 23 … 59 | 21 + 2 × (L−1) (looked up but unused for monsters) |
| 1 | duration, seconds (level clamped to 20 for non-players) | 15 + 2.0019848 × (L−1) [0x40002085] → 15, 17 … 53 | 15 + 2 × (L−1) → at most 53 |
| 2 | aura radius in 12-unit steps; **always read from tier 1** (slot 10) | from level 5: 3 + 0.50100195 × (L−5) [0x3f0041aa] → 0 0 0 0 3 4 4 5 5 6 6 7 7 8 8 9 9 10 10 11 | — |
| 3 | disease value written into allies' weapons | 15 + 1.0009999 × (L−1) [0x3f8020c4] → 15, 16 … 34 | — |
| 4 | mana | 50 + 6.0009556 × (L−1) [0x40c007d4] → 50, 56 … 164 | — |

### Cost and limits

Mana = statistic 4. canUse (0x318730): the caster must not already carry a
`SpellDiseaseBlade`.

### The modifier record

An item record has four 8-byte modifier slots at +0x24: {s16 id, s16 v1, s16 v2, s16 v3}
(`docs/player.md`; the same shape as a damage-descriptor slot). For id 0x26 the game uses
v1 = disease value, v2 = upper value, v3 = frames left. `Player_tickEnchantTimers`
(0x1bc560) counts v3 down by one per frame for the ids 0x15, 0x16, 0x18, 0x26, 0x17 (list
at 0x537c08) on every equipped item, and empties the slot when it reaches 0; it does nothing
for the prediction copy.

`writeDisease(item, value, frames, limit)` — the block that appears four times in this
class, twice in the constructor (from 0x318c70 and from 0x318de8) and twice in the run:

```
if item is null or item flag bit 24 (thrown weapon) is set: return
old = v1 of the item's first 0x26 slot, 0 if it has none
if old < 0 or old >= limit: return           # sic: the old VALUE is compared with a frame count
if old > value: return
slot = first slot whose id is -1 or 0x26     # none: return
slot = {0x26, value, round(value + value * 0.19999999), frames}
```

`round` is add 0.5 and truncate. The comparison of the old value with `limit` reads the
same field (v1) as the second comparison — Observed at 0x318ca8/0x318d60 and
0x318d4c–0x318d58; with the constructor's limit (at least 900) it never refuses, with the
aura's limit of 31 it does (below).

### Behaviour

Cast (0x318764): `pool_new(0x24)`, construct, return the spell.

Constructor (0x318ad4), in order:

1. Spell base — shared draw 1.
2. +0x18 (s32) = `g_simFrame` + stat(1, level, caster, cap 20) × 60: the expiry frame.
   +0x1c = `g_simFrame` + 30 (never read). +0x20 (float) = getStat(2, level) × 12.0.
3. value = stat(0, level, caster, cap 0); frames = stat(1, level, caster, cap 20) × 60.
4. Caster is not a player: if it has a weapon holder (+0x50), call the holder's virtual slot
   7 with hand 1 (0x3c1df8). That calls `creature_buildElementDamage(holder + 4,
   holder + 0x50, kind 5)` (0x1176e0), which empties the four effect slots of the record at
   holder + 0x50 (Inferred: the damage descriptor of hand 1) and writes
   slot 0 = {0x26, a, a + trunc(a × 0.19999999 × r / 65536), 0} with a = tier-2 statistic 0
   of **skill 25** at trunc(level-wide monster level) and r one shared draw. Any element the
   monster had before is lost.
5. Caster is a player: `writeDisease(A, value, frames, limit = frames)` and the same for B,
   where A = record item pointer +0x4434 + 4 × active weapon set (+0x4a7c) and
   B = record +0x443c (the second weapon).
6. `LightEffect` at the caster's position — shared draw (skipped if the pool is empty).
7. Caster flash quad 2 = {0x80, 0x80, 0, 0x1e}; sound `spel_ew_coldwpn.anm` (sic).

Run (0x319068), every frame, with the position slot 17 hands in:

```
if g_simFrame < expiry:
    R = aura radius (+0x20)
    if R != 0 and owner is a player and g_simFrame % 30 == 0:
        list = world_collectObjectsInBox(pos - R, pos + R on all three axes, at most 63)
        for o in list (box order):
            if o is not the owner and o is a player
               and (not PvP mode A, or owner's virtual slot 22 "same team" accepts o):
                v = stat(3, level, owner, cap 0)
                writeDisease(o's A, v, frames = 31, limit = 31)
                writeDisease(o's B, v, frames = 31, limit = 31)
else:
    if owner is a creature and not a player and has a weapon holder:
        holder slot 8 (hand 1, element 0)       # empties the same four slots, no draw
    destroy the spell
```

Consequences of the code as written (Inferred from the listing):

- The aura is a cube test, not a sphere, and exists only from rank 5.
- The aura refreshes a 31-frame modifier every 30 frames. Once statistic 3 is 31 or more
  (rank 17 and up) the modifier it wrote itself fails the `old >= limit` test, so an ally's
  buff then runs 31 frames, lapses, and is written again at the next multiple of 30 — on for
  31 frames out of 60. An ally whose own weapon already has a disease value of 31 or more
  (their own Disease Blade from rank 6) is never touched.
- The caster's own modifier is written once and counts down in the item; the spell object
  only marks the time. Swapping to the other weapon set leaves the buff on the old weapon.
- On a monster the effect is the descriptor change in step 4 and its removal at expiry.

### Random draws

| When | Generator | Count |
|---|---|---|
| constructor | shared | 1 (Spell); 1 more for a non-player caster with a weapon holder; 1 for the `LightEffect` |
| run | — | none |

The spell's own generator is never used.

### Presentation only

Light, sound, the yellow flash at cast.

### Per-machine state

- Player-record reads and writes (+0x4434, +0x443c, +0x4a7c and the item records behind
  them) are all behind the is-player test (0x318c3c in the constructor, 0x3190dc in the
  run). Item records are part of the shared player record.
- The aura's timing uses `g_simFrame % 30`, which is lockstep state inside the simulation.
- `Player_tickEnchantTimers` skips the prediction copy, so the copy does not shorten the
  buff.
- Non-player caster: no item writes; one extra shared draw at cast.

### Functions read

0x318610, 0x31867c, 0x318730, 0x318764, 0x318aa0, 0x318ad4 (decompile, and 0x318c50–0x318dd0
in the disassembly for the two comparisons), 0x319068, 0x3c1df8, 0x11aff0, 0x1176e0 (the
disease case), 0x1bc560, list 0x537c08, Bubo call site. Not read: describeRank 0x318804
(668 bytes); who else reads modifier 0x26 values (`item_getDamageRange` 0x104100 adds v1
and v2 to the range it returns when asked for elemental damage).

## 98 — Fire Axe (`fireaxe`) and 99 — Cold Axe (`coldaxe`)

**Partly specified.** The two cast functions are identical except for the element, the
colours and the sound, and were read in full. The thrown object is a `playerProjectile`
(player area); its run function was read, its hit handler `MissileWeapon_onTouch`
(0x152a18) only in part. How `Player_run` gets from the button to this cast for a kind-8
skill was not traced.

### Identity

| | 98 Fire Axe | 99 Cold Axe |
|---|---|---|
| Skill class / table / object | `SkillFireAxe` / 0x51c4d0 / 0x6e3c40 | `SkillColdAxe` / 0x51c558 / 0x6e3dc8 |
| Kind, flags, recast | 8 ("weapon"), 0, 30 | 8, 0, 30 |
| Tree (berserker, class 5) | base level 10, needs skill 72 | base level 25, needs skill 73 |
| Object size | 0x188: the 0x68-byte Skill plus four 0x48-byte item records at +0x68, one per player slot | same |
| Creates | one `playerProjectile` (0x1d0 bytes, table 0x50e470); one `LightEffect`. Returns 0 | same |

The static constructor (0x319598 / 0x319ed4) fills each of the four item records by parsing
the descriptor `throwingaxe` (variant −1, so start-up makes up to four shared draws per
skill, before any game exists).

### Statistics (slot 10, tier 1)

| Stat | Meaning | 98 | 99 |
|---|---|---|---|
| 0 | horizontal speed of the axe, units per second | 300 + 20.003998 × (L−1) [0x41a00830] → 300, 320 … 680 | 300 + 20.003603 × (L−1) [0x41a00761] → the same values |
| 1 | elemental value written into the axe's item record | 50 + 5.9999638 × (L−1) [0x40bfffb4] → 50, 56 … 164 | 150 + 5.9998136 × (L−1) [0x40bffe79] → 150, 156 … 264 |
| 4 | mana | 25 + 3.0009768 × (L−1) [0x40401001] → 25, 28 … 82 | 70 + 3.000984 × (L−1) [0x4040101f] → 70, 73 … 127 |

### Cost and limits

Mana = statistic 4. canUse (0x319710 / 0x31a04c): a non-player is always allowed. For a
player the item in equipment slot 2 (record +0x43f8) must exist and have item flag bit 42
(the same bit `player_itemWeight` treats as "thrown axe" for skill 73); otherwise the text
`axecast_warn` is shown for 180 frames on that player's machine and the cast is refused.

### Cast — 0x31979c / 0x31a0d8 (level, caster, pos, facing)

Everything after the first three lines uses `caster + 0x3c8` with **no is-player test**.

```
caster flash: both quads = {0x73, 0x4f, 0x38, 0x23} (98) / {0x3c, 0x3c, 0x5e, 0x26} (99)
LightEffect at pos + 36 following the caster                       # shared draw
sound spel_vb_fireaxe.anm / spel_vb_coldaxe.anm at pos
speed = getStat(0, level)
hand  = attach point 0 of the caster's body model
if caster has no target (+0x234 empty):
    r1, r2 = two SHARED draws
    a  = (s16)(caster facing + r1 % 2600 - 1300)                   # ±7.1 degrees
    vz = (float)(r2 % 40) + 40.0
else:
    t  = target position
    a  = 0x4000 - atan2_16(t.x - hand.x, t.y - hand.y)             # the heading to the target
    vz = dist3D(hand, t) - 120.0
vel = (cos16(a) * speed, sin16(a) * speed, vz)
stack = record[+0x43f8]                                            # the equipped axe stack
model = g_itemModels row of item_getResourceIndex(stack)           # two words, +8 and +0xc
main  = record[+0x4434 + 4 * active weapon set]
if main is null: return 0                                          # nothing thrown; mana is still spent
rec = &skill.itemRecord[slot]                                      # skill + 0x68 + slot * 0x48
item_copyMutableFields(rec, main)                                  # count, flags, affixes, 4 modifiers
v = getStat(1, level)
first slot of rec that is empty or holds the element code =
    {0x15 (98) / 0x16 (99), v, round(v + v * 0.19999999), 600}
p = pool_new(0x1d0)
if p: playerProjectile_ctor(p, model, hand, vel, heading = a + 0x4000, owner = caster,
        damage min = record.+0xd0, damage max = record.+0xd4, attack = 100000,
        kind = 4, item = rec)
if 1 <= stack.count <= 20:                                         # HUD low-ammunition notice
    hudTimer[slot] (0x41b844 + slot*0x20) = 240 ; 0x41b8c4 + slot*0x20 = (0x1dacf4)(slot, 7)
if caster is not the prediction copy: stack.count -= 1
if stack.count < 1: inventory_removeItem(slot, index of stack in bag 0, bag 0, 0)
return 0
```

Observed details: the per-slot record takes its modifiers from the **primary weapon of the
active set**, not from the axe stack, and keeps the `throwingaxe` definition; the record is
shared by every axe that player throws, so a later cast rewrites the element values under
axes still in flight (they hold a pointer, not a copy). The weapon damage range is copied by
value at the moment of the throw.

### The projectile (Observed in 0x1bef58, 0x150ee4, 0x1ba940; hit handler in part)

`playerProjectile_ctor` → `MissileWeapon_ctor` → `Projectile_ctor`: a GameObject (**one
shared draw**), flags |= 0x4081 then 0x4001; fields used here: velocity +0x1b0, damage
+0xd4 / +0xd8, attack +0xe4, damage flags +0xe8 = 4, item pointer +0x12c, life end +0xec =
frame + 300, kind byte +0x1ce = 4, spin +0x1cc = 2000, owner handles +0x4c and +0x1c8.
When the item's definition has weapon class 6 the constructor sets radius 24 and
half-height 100 (0x150ee4, decompile lines 105–109); that `throwingaxe` is such a
definition is Inferred.

`playerProjectile_run` (0x1ba940), once per frame, for kind 4: spin += 3000;
velocity.z −= 8.999999; `obj_moveAndCollide`; if it hit terrain, or an earlier touch set the
"has hit" byte (+0xcc), the life end is set to 0 and the object is destroyed that frame.
Kinds 1–3 (fire, gas and exploding arrows) have extra code there; kind 4 has none.

On touching something, `MissileWeapon_onTouch` ends in
`damage_apply(min, max, victim, owner, attack, +0xdc, +0xe0, flags = +0xe8, descriptor =
item record, 0)` (0x152a18, decompile lines 327–340). With the record prepared above that
means: weapon damage range, attack 100000, damage class bit 0x4, and a fire (0x15) or cold
(0x16) slot of v … 1.2 v on top, plus whatever modifiers the primary weapon carries. The
dodge roll, the ownership tests and the rest of that handler were not read.

### Random draws

| When | Generator | Count |
|---|---|---|
| start-up | shared | up to 4 per skill (item variants) |
| cast | shared | 1 (`LightEffect`); 2 when the caster has no target; 1 (projectile) |
| hit | shared | `MissileWeapon_onTouch` and `damage_apply` |

### Per-machine state

- **Unguarded player index** throughout the cast (`docs/skills.md` table (a)): inventory,
  equipment and two per-slot HUD arrays are written for any caster, and canUse lets a
  non-player through.
- The cast tests the prediction-copy flag before decrementing the stack (0x319d14), which
  suggests it can be reached for the copy; skill flag bit 0 is clear, so
  `Player_castSkill` would not do that. Which caller does was not found (Unknown). If the
  cast does run for the copy, the `LightEffect`, the projectile and the element write into
  the shared skill record are not guarded.
- `hud_showMessage` in canUse shows text only on the owning machine.
- The projectile reads a pointer into the static skill object; that object is the same on
  every machine as long as the casts are.

### Functions read

98: 0x319598, 0x3196b4, 0x319710, 0x31979c (decompile, and 0x319b20–0x319db0 in the
disassembly), 0x319ea0. 99: 0x319ed4, 0x319ff0, 0x31a04c, 0x31a0d8 by difference from 98,
0x31a7d4. Also 0x1bef58, 0x150ee4, 0x1ba940; 0x152a18 lines 50–135 and 318–354.
Not determined: the path from `Player_run` to the cast; the remainder of
`MissileWeapon_onTouch`; what 0x1dacf4 returns for the HUD.

## 101 — Cone of Shock (`coneofshock`)

**Fully specified** for the spell. The player-side handling of a channelled skill is not
exercised, because no class has this skill.

### Identity

| | |
|---|---|
| Skill class / table / object | `SkillConeOfShock` / 0x51c728 / 0x6e3fb8 |
| Kind, flags, recast | 1 (channelled), 0, 30 |
| Tree | **none** |
| Other casters | `Hag`: state 7, on animation event bit 1, if it carries no `SpellConeOfShock`; level = slot 35; position = its feet + half its height; attaches the result to itself and sets its own timer +0x3d0 to clock + 300 (table load at 0x26fe80). `Hag_setState` (0x270264) removes any `SpellConeOfShock` at the top of every state change, which is the only thing that ends it. The Hag also asks slot 11 for statistic 1 (cap 25) to decide whether the target is in reach (0x26fab4, 0x26fb84) |
| Creates | `SpellConeOfShock` (0x58 bytes, table 0x51c6f8) on the caster; a `LightningBolt` decoration at intervals |

### Statistics

| Stat | Meaning | Tier 1 | Tier 2 |
|---|---|---|---|
| 0 | four times the lightning damage of one tick (no clamp) | 275 + 5 × (L−1) | 2 + 2 × (L−1) |
| 1 | reach in 12-unit steps (level clamped to 25 for non-players) | 1 + 0.19999999 × (L−1) [0x3e4ccccc] → 1 1 1 2 2 2 2 2 3 3 3 3 3 4 4 4 4 4 5 5 | same formula → 1 … 6 at level 25 |
| 2 | cone angle in degrees, before the +10 (level clamped to 10 for non-players) | 30 + 0.19999999 × (L−1) → 30 30 30 31 31 31 31 31 32 32 … | same → at most 32 |
| 4 | mana per second | 42 + 2 × (L−1) | — |

### Behaviour

Cast (0x31b8f0): `pool_new(0x58)`, construct, return the spell.

Constructor (0x31bac8): Spell base (shared draw 1); an embedded light record at +0x18 placed
60 above the caster (presentation); a looping sound `spel_ew_cfrost.anm` (sic) whose handle
is kept at +0x54. Destructor (0x31bc50): stops that sound, unlinks the light, frees.

Run (0x31bcd0) — (pos, facing) from Creature slot 17, i.e. for a monster its position raised
by half its height and its facing:

```
arc   = stat(2, level, owner, cap 10)                 # degrees
reach = stat(1, level, owner, cap 25) * 12.0
period = 60 / ((level / 4) * 2 + 2)                   # integer arithmetic: 30, 15, 10, 7, 6, 5 …
if g_simFrame % period == 0:                          # decoration
    r = Spell_rand()
    a = (s16)(facing + trunc((float)(s16)trunc(arc * 182.04443) * (r / 65536.0 - 0.5)))
    near = pos + 12 * (cos16(a), sin16(a)) ; far = pos + (reach + 12) * (cos16(a), sin16(a))
    b = pool_new(0x60); if b: LightningBolt_ctor2(b, far, near, life 11, no light)   # one SHARED draw
if g_simFrame % 15 == 0:                              # damage, four times a second
    origin = pos - 12 * (cos16(facing), sin16(facing))
    list = world_collectObjectsInArc(radius = reach, arc = arc + 10.0, width 0,
                                     origin, facing, owner filter = none)
    for o in list (list order):
        if owner.isEnemy(o):
            s0 = stat(0, level, owner, cap 0)
            r  = Spell_rand()
            v1 = (s16)trunc(s0 * 0.25)
            v2 = v1 + (s16)trunc((float)trunc(s0 * 0.25) * (r / 65536.0) * 0.19999999)
            descriptor slot 0 = {0x18, v1, v2, 0}
            damage_apply(0, 0, o, owner, 100000, 0, 0, flags 0x40, descriptor, 0)
            hit = true
    if hit: sound spel_ew_cfire_hit.anm (sic) at the owner
light radius flicker                                   # presentation
```

- The whole damage is the lightning slot: v1 … v2 reduced by the victim's lightning
  resistance, plus the shock status (`docs/gameplay.md` §2.2, type 0x18). The base range is
  0…0, so the base roll draws nothing.
- **The upper bound of the range comes from the spell's own generator**, and that generator
  is also advanced by the decoration draw, so the two streams cannot be separated: the
  decoration draw (when its period falls on the frame) comes first, then one draw per enemy
  in list order.
- The arc query is a wedge of `arc + 10` degrees clipped by a square of half-size `reach`
  around `origin`, creatures only (see the shared section). With reach 12–72 units this is a
  short-range attack.
- Timing is by `g_simFrame`, not by the spell's age: the first tick comes 0–14 frames after
  the cast.
- At skill level 1 a non-player's statistic 0 is 2, so v1 = trunc(0.5) = 0; a 0x18 slot
  whose first value is 0 is skipped by the damage function (`docs/gameplay.md` §2.5 step
  21), so that cone does no damage at all (Inferred from the two documents' rules, not
  traced through the call).
- A player holding a channelled spell would lose it in `Player_updateCast` (0x1a3f70): once
  the ability button is up, the action state is no longer 5 or mana is at 0, and the cast
  animation track has blended in or gone, the spell linked at player +0x588 is destroyed.
  Read there, but not exercised by this skill.

### Random draws

| When | Generator | Count |
|---|---|---|
| constructor | shared | 1 |
| frame % period == 0 | own, then shared | 1, then 1 (bolt constructor; 0 if the pool is empty) |
| frame % 15 == 0 | own | 1 per enemy hit |
| same | shared | those of `damage_apply` per enemy (hit rolls, proc rolls, the 0x18 slot) |

### Presentation only

The loop sound, the light, the bolts (11 frames each), the hit sound.

### Per-machine state

None found. Player casters would differ only in tier and the missing level clamps; the
spell has no player-record access.

### Functions read

0x31b7f4, 0x31b868, 0x31b8f0, 0x31ba94, 0x31bac8, 0x31bc50, 0x31bcd0 (with 0x31bf40–0x31bfa8
in the disassembly for the query arguments), `LightningBolt_ctor2` 0x295584, Hag sites
0x26fab4, 0x26fb84, 0x26fe80, 0x270264. Not read: describeRank 0x31b990.

## Per-machine state: summary for ids 69–101

Details are in each section; this collects them.

| What | Where | Effect |
|---|---|---|
| Player index used with no is-player test | constructors and run functions of 72, 75, 76, 77, 78, 84; casts of 98, 99; `SpellRaiseArmy` raise step (0x313d74, **not in the list in `docs/skills.md`**) | wrong-memory reads and writes if a non-player ever casts them. Reachable only by players: the trees are the only source, and no item descriptor can produce the weapon-proc type |
| `net_isLocalSlot` | run functions of 76, 77, 78, 84; Drowsy phase 2 | only to write `g_forceGhostRebase`, which is per-machine prediction state |
| `net_objOrGhost` | 72, 75, 77, 78 (particle positions); 84 (`docs/skills.md`, FINDINGS G22) | presentation, except G22 |
| `g_alivePlayers` (FINDINGS G11–G13) | 77 tint and its swing-speed consumer in `Player_run`; 81 tint and bonus query; 86 heal | shared effects decided from a list that can be wrong for part of one frame on one machine |
| Option `g_decalDetail` and prediction-copy motion deciding how many own-generator draws are made | 78 run | that spell's own generator differs per machine; only particles read it |
| HUD text from canUse | 84, 85, 98, 99 | shown on the owner's machine only; canUse is also called for the prediction copy |
| Cosmetic generator 0x404460 | 69 (model-vertex particles), 82 (counter-attack particles), `fx_spawn(10)` in 96, `fx_spawn(0x13)` in the bolts of 100 | presentation |
| Generator 0x404468 | not used by any function read for this range | — |
| The lockstep pad array `g_pads[slot]` and the per-slot camera yaw (`net_getCamYaw`) | 84 run, as input to `Player_move` | lockstep data (`docs/player.md`), not the raw controller |
| Camera, raw pads, the local player slot, audio position, hardware timers | none found. Besides the reading, the decompile of all 246 functions in the address ranges of the classes that belong only to this id range (0x2fcf30–0x304bc8, 0x30a958–0x30ddc4, 0x30e0f0–0x31127c, 0x3133cc–0x315a8c, 0x316a24–0x31c2a0) was searched for the named per-machine globals and helpers; the only hits are the ones in this table. The six shared classes of ids 81–86 were not part of that search | — |

A spell's **own** generator is seeded from the shared one and so is identical on every
machine, but in five skills it decides something that matters *and* is advanced by particle
code in the same function: 87 (the swarm's wander), 88 (the success roll), 70 and 77 (stun
rolls), 101 (the top of the damage range). In 100 and 80 the storm object's own generator
decides how many decoration objects — and therefore shared draws — are made. A rebuild has
to execute those particle draws, rejection loops included, whether or not it renders them.

## What is specified, what is not

| Ids | State | Read in full | Left out — where the next pass starts |
|---|---|---|---|
| 87 | full | every function of the class in the disassembly | whether a dead player caster's spells keep running (`Player_run`); the knights' actual level in the arena |
| 69 | full | all but describeRank | whether the particle-group handle leaks (presentation) |
| 70 | full | all but describeRank | — |
| 76 | full | all but describeRank | what `Player_run` does itself in action state 6; `anim_advance` taken from `docs/engine.md` |
| 77 | full | all but describeRank, plus the consumer in `Player_run` 0x1aa018–0x1aa0ec | same |
| 78 | full (gameplay) | constructor, the two getters, run up to 0x303680, `Player_recalcDamage` tail | run 0x303680–0x3047b0 (particles) only scanned for stores and calls |
| 80, 100 | full | cast, constructor, run, both decoration classes | the position the dark elf passes; describeRank |
| 88 | full | all but describeRank | eight of the nine users of the slow-down factor (0x114af8, 0x11532c, 0x11582c, 0x115dbc, 0x1b41b4, 0x1b9560 read, 0x2bf96c, 0x2c0f4c) |
| 89 | full | all, plus `poisonGasSpell` and `obj_moveAndCollide` | describeRank; destructor skimmed |
| 90 | full (skill) | all but describeRank | the `CastBadger` class (`docs/monsters-2.md`); draws inside its constructor |
| 91 | full (skill) | all but describeRank | `world_createObject` and each class constructor's draws; weapon-holder slots 15 / 16 |
| 94 | full | all but describeRank; the two particle helpers for writes and draws only | — |
| 95 | full | all but describeRank | — |
| 96 | full | all but describeRank | — |
| 97 | full | all but describeRank (668 bytes) | other readers of modifier 0x26's values |
| 101 | full | all but describeRank | the player-side handling of a channelled skill (no class has this one) |
| 71, 73, 74, 79, 92, 93 | full (helpers) | every helper; each caller around the call | `MissileWeapon_onTouch` as a whole (93); equip rules for wizards (92) |
| 72, 75 | part | everything in the skill files | `inventory_giveItem`, `inventory_equipItem` (stacking, equip, any draws); whether the parser keeps the quantity; the item rows on the disc |
| 98, 99 | part | cast, canUse, constructor; `playerProjectile` constructor and run | how `Player_run` reaches the cast for kind 8 and whether it does so for the prediction copy; the rest of `MissileWeapon_onTouch`; 0x1dacf4 |
| 81–86 | part | 81, 82, 83, 86: every gameplay function of the class; 84, 85: cast, constructor, and the gameplay lines of run | 84: helper 0x2d21e0, `Player_move`, `Player_meleeHit`; 85: particle parts of the run; 83: what a dodged missile does; all: `initStats` bodies (numbers come from the table dump) |
| — | not reached | — | every describeRank function except 87's and 71's (which statistic each text slot prints); the static initialisers (particle type registration); draw functions beyond a scan for stores (0x30bc88, 0x30ed24, 0x30f6b4, 0x311034) |

## Proposed ledger rows

For `FINDINGS.md`; none of this was run.

| Proposed id | Claim | Kind | Evidence |
|---|---|---|---|
| SC1 | Tagar's Insects, the skill the arena's third knight casts, reads nothing per-machine. Its outcome depends on the shared generator, on the spell's own generator (including the particle loops between two wander draws) and on a single-precision clock | Observed | 0x30c708–0x30dc30, section 87 |
| SC2 | Five skills in ids 69–101 take a gameplay decision from the spell's own generator, in a stream shared with particle draws (ids 70, 77, 87, 88, 101); two more let an object's own generator decide how many shared draws follow (80, 100) | Observed | 0x2fddf0, 0x302adc (in 0x301a34), 0x30d0ac, 0x30e6f0, 0x31bcd0; 0x30b428, 0x31b25c |
| SC3 | The decoration interval of Lightning Strike and Pus Storm is `20 − level / 2` and is used as a divisor with no zero test; it is 0 at skill level 40–41 and negative above. A monster's skill level is trunc(monster level × 0.3), which reaches 40 at monster level 134 | Observed (code); reachability Inferred from the monster-level range in `docs/data-tables.md` §5 | 0x31a920, 0x31b5ac, 0x30aaa8 |
| SC4 | Frost Armor strikes back with `trunc(damage − factor)` cold damage, the factor being a number between 0 and 1: nearly the whole incoming hit, not the absorbed part | Observed | 0x318364 |
| SC5 | Pus Storm takes its damage from the player table for every caster; the dark elf's storm hits with 85 + 5 per level | Observed | 0x30ab54–0x30ab74 (slot 8, called with no test of the caster) |
| SC6 | `Player_recalcDamage` raises a thrown weapon's maximum by fraction × the already-raised minimum; Battle Mage replaces the weapon range by a fraction that is 0 at rank 0 | Observed | 0x1b7478–0x1b7488; 0x314a78 with slot 10's level-0 rule |
| SC7 | Disease Blade's two "is the old enchantment weaker" tests compare the old disease *value* with a frame count; with the aura's limit of 31 the ally buff is on for 31 frames in every 60 from rank 17 | Observed (code); effect Inferred | 0x318ca8, 0x318d4c; run 0x319068 |
| SC8 | `SpellRaiseArmy`'s raise step reads `caster + 0x3c8` without an is-player test | Observed | 0x313d74 |
| SC9 | (Already corrected in `docs/skills.md` when this was integrated.) The id table of `docs/skills.md` had the names of ids 33 and 53 exchanged: 33 is `rangercriticalhit` (ranger tree), 53 is `criticalhit` (barbarian tree) | Observed | constructor 0x2e7258; tree tables 0x4f5108, 0x4f4898 |

## Patches

None proposed. Nothing found in this range calls for one as a sync fix; SC3–SC7 are rule
quirks a rebuild should reproduce, not repair, if it is to play like the original.

## Corrections to earlier documents

1. `docs/skills.md`, id table and statistics table: ids 33 and 53 carry each other's names
   (SC9). The numbers in each row belong to the id in that row.
2. `docs/skills.md`, table (a) "not guarded": add `SpellRaiseArmy` raise 0x313d74 (a
   byte load, which a scan for word loads at displacement 0x3c8 would miss).
3. `symbols/skills.tsv`: `SpellSpiritShield_playHitEffect` (0x315888) is the absorb roll —
   it draws from the shared generator and returns whether the hit is absorbed; the sound is
   incidental. The name is left as it is.
4. `docs/creatures.md`, "The attached-spell list": "caster at +0x18, skill id at +0x1c"
   describes the `SpellTag` marker only (`creature_findSpell` tests the type before reading
   them). Other Spell classes use +0x18 for whatever they like.
5. `docs/skills.md`, Monsters column: Bubo's Disease Blade is cast with an ally as the
   caster argument and attached to that ally (0x249014); Cazic's Frost Armor is cast with
   the whole monster level, not slot 35 (0x24bbe8).
6. `docs/gameplay.md` §2.2, type 0x26: the modifier's second value is not unused
   everywhere — `item_getDamageRange` (0x104100) adds v1 to the minimum and v2 to the maximum
   it returns when asked for elemental damage, and the weapon buffs write
   v2 = round(1.2 × v1) and v3 = frames left.

## Functions named by this pass

`symbols/spec-skills-c.tsv` names thirteen previously unnamed helpers of these classes
(0x2fddf0, 0x2fe324, 0x2fe49c, 0x2fe96c, 0x300f54, 0x302c04, 0x3101cc, 0x313b38, 0x313bd4,
0x31539c, 0x315610, 0x317570, 0x318264). Two unnamed helpers of the shared classes
(0x2e76c4, 0x2d21e0) are left to the pass that owns those classes.
