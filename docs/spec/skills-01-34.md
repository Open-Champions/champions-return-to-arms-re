# Skills 1–34: implementation specification

Second-round document. `docs/skills.md` catalogues all 101 skills; this file specifies ids
1 to 34 closely enough to reimplement them: what each cast creates, what those things do on
every simulated frame, every damage call with its arguments, and every draw from a random
generator in order. It was written from the decompile of each function listed, with the
disassembly consulted wherever the decompile was ambiguous. Nothing here was run on a
console or an emulator. That still holds: the emulator the project now runs the game in
(Play!, not a PlayStation 2 and not PCSX2; `FINDINGS.md`, "Run on the live game" (rows V1–V13) and `docs/issues/live-rig.md`)
has not been used to look at a skill, and the only test patches run on a live game are the two for K1 and K2 (FINDINGS V10, V11).

Every statement is **Observed** (read at the address given) unless it is marked *Inferred*
or *Unknown*. Pseudo-code is mine; it is not decompiler output. Numbers are decimal unless
written 0x…. Angles are 16-bit (65536 = full turn; 182 = 0xb6 ≈ one degree). A "frame" is
one simulated frame (60 per second); `frame` is the frame counter `g_simFrame` 0x44fdcc.

Coverage is summarised in the table at the end. Skills that share a class are specified
once: 12/13/14/26 (weapon buffs), 31/32 (Root, with 52 and 85), 33 (CriticalHit, with 53
and 81), 2 (Dodge, with 83), 9 (Riposte, with 82).

## 0. Machinery every section relies on

This section repeats, in exact form, the few shared routines whose arithmetic decides a
skill's numbers. The area documents describe them; the details below were re-read for this
specification.

### 0.1 Random generators

All five are the same linear congruential generator: `state = state × 0x19660d +
0x3c6ef35f` (32-bit wrap); a *draw* returns `state >> 16` (0…65535).

| Name here | State | Step function | Notes |
|---|---|---|---|
| shared | global 0x404464 | inlined everywhere | in the sync hash; restored after prediction |
| object's own | object +0x44 | `GameObject_rand` 0x1509d0 | seeded by `GameObject_ctor` 0x14cb10 with one **shared** draw: state = that 16-bit draw |
| spell's own | spell +0x10 | `Spell_rand` 0x16a964 | seeded by every Spell constructor with one **shared** draw, same way |
| cosmetic | global 0x404460 | inlined | particles only |
| fourth | global 0x404468 | inlined | particles and decals only; per-machine |

So **creating any GameObject or any Spell costs one shared draw**, including purely visual
ones (`LightEffect`, `GlowingShaft`, `LostSoul`, `FireStormFlare`, debris props). Sections
below list them because they move the shared stream.

Many effects draw their particles from the object's or spell's own generator and later use
the *same* generator for a damage roll. Where that happens the particle draws have to be
reproduced too, in order. The recurring particle idiom is:

```
unitSphere(gen):                      # rejection loop, at least 3 draws
    repeat:
        x = 2*draw(gen)/65536 - 1;  y = 2*draw(gen)/65536 - 1;  z = 2*draw(gen)/65536 - 1
    until x*x + y*y + z*z <= 1.0      # float32 arithmetic; the loop repeats while the sum is > 1.0
```

"`k × (S, S)`" below means k particles, each made from two consecutive `unitSphere` calls
(position, then velocity). Because the loop length depends on the values drawn, the number
of draws per frame is not constant.

### 0.2 Statistics

A Skill holds two tiers of five statistics (`docs/skills.md`, Skill layout). The lookup
slots are the base-class functions for every class in this document:

```
round(v) = (v >= 0) ? trunc(v + 0.5) : trunc(v - 0.5)          # float32, then float→int truncation

slot10 getStat(stat, level)                      # 0x3c85fc, tier 1
    if level == 0 or level < first1[stat]: return 0
    return round(base1[stat] + step1[stat] * (level - first1[stat]))

slot11 getStatTier2(stat, level, cap)            # 0x3c8690
    if level == 0: return 0
    if cap > 0: level = min(level, cap)
    if first2[stat] is 0xffff (unset):           # no tier 2 for this statistic
        if level < first1[stat]: return 0
        return round(base1[stat] + step1[stat] * (level - first1[stat]))
    if level < first2[stat]: return 0
    return round(base2[stat] + step2[stat] * (level - first2[stat]))

slot12 getStatFor(stat, level, caster, cap)      # 0x3c87f0
    caster is a player (flag 0x40)  → slot10(stat, level)        # cap ignored
    otherwise (or caster null)      → slot11(stat, level, cap)

slot13 getStatForHandle(stat, level, handle*, cap)   # 0x3c8864: as slot12 with the caster read
                                                     # through a handle; an empty handle → slot11
slot14 adjustLevel(level, n) = level             # 0x3c88dc
slot15 manaFromStat4(level, n) = (float) slot10(4, level)       # 0x3c88e4
slot 8 getStatRange(spread, stat, level, randomise, *lo, *hi)   # 0x3c82e4
    v = slot10(stat, level)
    randomise == 0:  lo = round(v - v*spread);  hi = round(v + v*spread)
    randomise != 0:  for each bound two shared draws are made; the first only decides the
                     rounding direction, the second is used: bound = round(v ∓ v*spread*d/65536)
    lo = max(lo, 1);  hi = max(hi, 1)
```

Which tier a statistic comes from is therefore decided per call site: a `slot10` call gives
tier 1 numbers even to a monster. The sections say which slot each read uses. A statistic
that `initStats` never writes is 0 at every level (the objects live in zero-filled memory),
except in the classes that use the **base** `initStats` 0x3c85b0, which writes first level
0, base 1, step 2.0 for all five tier-1 statistics.

The per-skill tables give the stored values; "Step bits" is the float32 pattern, so
`base + step × n` can be evaluated bit-exactly. All of this arithmetic is single precision
on the console, whose FPU is not IEEE (products and sums are truncated, not rounded; see
`tools/ee_emu.py` and `tools/fp_hazards.py`). The steps are stored slightly off round
numbers (9.008915 for 9), which keeps `value + 0.5` clear of integer boundaries in the
cases checked, but a rebuild should evaluate these formulas with the console's rounding
rule rather than assume the two agree at every level (*Inferred*; not checked level by
level).

### 0.3 Objects, spells and what a cast is handed

- `GameObject_ctor` 0x14cb10: radius (+0x1c) 24, height (+0x20) 72, one shared draw.
  `Projectile_ctor` 0x150e48 (object, position, owner, 0): the same plus radius 12, flags
  |= 0x4081, owner handle at +0x4c (empty when owner is null), "has splashed" byte +0x50 = 0.
- Every Spell constructor writes level (+0, u8), back-list head (+4) = 0, Skill* (+8),
  owner (+0xc), own seed (+0x10) from one shared draw, virtual table (+0x14).
- `cast(level, caster, pos*, facing)` (Skill slot 2) is reached three ways
  (`docs/skills.md`): the player helper `Player_castSkill` 0x1a42b8, a monster's own run
  function, and a weapon effect of type 0x29 inside `damage_apply`.

`Player_castSkill`, as far as it matters to the skills here (Observed, 0x1a42b8):

```
if player.recast(+0x4ae) > 0: return
skill = g_skillTable[record.skillId]
if skill.flags bit 0 clear and player is the prediction copy: return   # all of ids 1–34
if not skill.canUse(player): return
pos = midpoint of model attachment points 0 and 1; if |pos.z - player.z| > 58: pos.z = player.z + 58
list = world_collectObjectsInArc(340.0, 20.0, 0, player.pos, player.facing, no filter)   # §0.5
target = first entry of list for which player.isEnemy(entry)
facing = target ? (s16)(0x41c2 - atan2_16(target.x - player.x, target.y - player.y))
                : player.facing                  # 0x4000 - atan2(dx,dy) is the bearing; the extra
                                                 # 0x1c2 (about 2.5°) is in the code
level = player rank of the skill (record table +0x4b08, Player slot 39)
spell = skill.cast(level, player, &pos, facing)
if spell: attach it to the player (creature +0x364); kind 1 also links it at player +0x588
player.recast = skill.recast (+0x0c)
mana -= skill.manaCost(level)        (÷ 60 when skill.kind == 1)
```

The mana test (`mana >= manaCost(level)`, else the "not enough mana" voice cue) and the
first `canUse` are in `Player_run` before the cast animation starts (0x1a5c6c…); `canUse`
is asked again when the animation starts. In action state 5 the cast happens when the
cast-animation track (flag 0x8000) has blended in to weight 1.0, or 0.5 in a net game
(`Player_run`; the helper has five call sites, 0x1a7048, 0x1a837c, 0x1a9174, 0x1aac60 and
0x1ab7dc — which of them serves which state was not sorted out here).
The cost is deducted even when `cast` returns no Spell. For a held ability (ability record
kind 1) `Player_run` then takes `manaCost(level)/60` every frame of cast phase 2, and
`Player_updateCast` 0x1a3f70 destroys the spell linked at +0x588 when the button is
released, mana is not above 0, or the state is no longer 5.

A monster passes `level = (int)(g_levelMonsterLevel × 0.29999998)` (Creature slot 35,
0x118c50) unless noted, and attaches the returned Spell itself.

A weapon effect (descriptor type 0x29: skill id, chance %, level) makes one shared draw
when the chance is non-zero and, if `draw < chance × 655`, calls
`cast(level, attacker, &attacker.pos, attacker.facing)`; the returned Spell is **not
attached to anything**, so its run function never executes (0x1e8ea8–0x1e8fa0).

**Where a Spell's run gets its position.** Creature slot 17 (0x11a868) calls
`run(pos*, facing)` on every attached spell with the creature's facing (+0x38). For a
non-player it is called at the top of `Creature_run` with `pos = (x, y, z + height/2)`
(0x112948). For a player it is called from `Player_updateCast` at the end of `Player_run`
with the same attachment-point midpoint as above (z clamp 58). "run position" below means
this argument.

### 0.4 Team tests

`isEnemy(a, b)` is Creature slot 20: for a player `Player_isEnemy` 0x1b5ea8, otherwise
`Creature_isEnemy` 0x119328.

- Player a: b ≠ a, b is a creature (0x20), not dead (0x8), object flag 0x1000000 clear,
  creature flags 0x4000000 (friendly) and 0x800 clear. If b is a player: enemy only in PvP
  mode A and on a different team. If b is a monster: enemy, unless it is charmed (+0x312 ≠
  0), in which case only in PvP mode A with b's team ≥ 0 and different from a's.
- Non-player a: b non-null, b ≠ a, b has flag 0x20 or 0x40, flags 0x20008 clear (dead,
  prediction copy), creature flags 0x4000000 and 0x800 clear, and team(a) ≠ team(b)
  (slot 37). Returns 4 instead of 1 for a priority enemy.

`sameTeam(a, b)` is slot 22, 0x10de10.

### 0.5 World queries

`world_collectObjectsInBox(min, max, out, n)` 0x14a928: grid cells row by row (y ascending,
then x ascending), list order inside a cell; skips objects matching `g_excludeMask` and
always the prediction copy; keeps an object when its x/y circle (radius +0x1c) touches the
box and `obj.z <= max.z` and `min.z <= obj.z + obj.height`; at most n − 1 results.
"box order" below is this order. **A box query is the only area test most skills make:
their "radius" is the half-width of a square, widened by each target's own radius.**

`world_collectObjectsInArc(radius, arcDeg, halfWidth, pos, facing, list, filter)` 0x1614f0:

```
box = pos ± radius on all three axes, at most 511 objects
keep o when:  o is a creature (0x20) and (o.flags & 0xd) == 0
              filter == null or filter.isEnemy(o)
              arcDeg == -1.0, or o is on the inner side of both arc edges:
                    h = round(arcDeg * 0.5 * 182.04443)
                    dot(o.xy - pos.xy, dir(facing + h - 0x4000)) >= 0 and
                    dot(o.xy - pos.xy, dir(facing - h + 0x4000)) >= 0
              halfWidth == 0, or |dot(o.xy - pos.xy, dir(facing + 0x4000))| <= halfWidth
              dot(o.xy - pos.xy, dir(facing)) > 0
insert kept objects one at a time (box order):
    walk the list from its head; at the first node whose 2-D distance² to pos is <= the new
    object's, insert the new object directly AFTER that node and stop;
    if there is no such node, insert at the head
```

There is no distance test other than the box. The insertion rule keeps the **nearest
object at the head** (ties: the earlier one stays ahead) but does not sort the rest; a
rebuild has to copy the rule, because several skills walk the list and stop at a count.
`dir(a)` = (cos16(a), sin16(a)).

`world_collectInSphere(radius, pos, …, list)` 0x14ab80: box ± radius (511), keeps objects
with `(flags & 0xd) == 0` and 3-D distance < radius + object radius.

### 0.6 Projectile step

`obj_moveAndCollide(obj, velocity*)` 0x1509f8, velocity in units per second:

```
pos += velocity / 60
if terrain_height(radius, world, pos) > pos.z:                   # went into the ground
    result |= 1
    back the position off along this frame's step in tenths (0.1, 0.2 … 1.9 of the step)
    until the terrain height there is <= z; keep that position
    once per object (byte +0x50): if the spot is water, one draw from the object's own
    generator (splash sound variant) and a ripple
for each o in the box pos ± (radius, radius, height), box order, at most 255:
    skip if o.flags & 0x201, or o.flags & 0x20000000, or o is obj, or o is the owner (+0x4c)
    if the z ranges overlap and 2-D distance² < (obj.radius + o.radius)²:
        result |= 2;   o.slot6(obj);   obj.slot6(o)              # "touched", both ways
return result
```

### 0.7 Damage calls

`damage_apply(min, max, victim, attacker, attack, -, -, flags, descriptor, noCrit)`
0x1e8230 is specified in `docs/gameplay.md` §2. Calls are written below as
`damage(min, max, victim, attacker, attack, flags, descriptor, noCrit)`; the two dead
arguments are always 0. Three facts are used repeatedly:

1. Base roll: only when `min < max` one shared draw is made and the amount is
   `min + fmod(draw, max − min + 1)`; otherwise the amount is `min`, with no draw.
2. An "empty descriptor" has all four effect slots at type −1. Skills build it on the stack
   and usually fill slot 0 with one entry `{type, v1, v2, v3}` (s16 each).
3. The elemental entries (always-on 0x15 fire, 0x16 cold, 0x18/0x19 lightning, and the
   chance entries 0x1f, 0x20, 0x22) compute their amount with **integer** arithmetic and no
   guard (fire: 0x1e98c8–0x1e9914; the other six sites have the same expression):

   ```
   if v1 != 0:  d = shared draw;  amount = v1 + (d rem (v2 - v1 + 1))     # MIPS signed `div`, HI
                total += amount - amount * resistance
   ```

   When a caller passes `v2 < v1` the divisor is negative and the remainder is
   `d mod |v2 − v1 + 1|`, so the amount ranges **upward** from v1. When `v2 == v1 − 1` the
   divisor is 0; there is no trap instruction after the `div`, and on the R5900 the
   remainder register then holds the dividend (*Inferred* from the processor's documented
   behaviour; not tested), giving `v1 + d`. Cone of Fire (id 18) passes such values.

The colour quads written by many skills ("flash") are the creature fields +0x90…+0x96 and
+0x98…+0x9e (four s16 each, decaying by 2 per frame in `Creature_run`); they are
presentation and are listed only briefly.

### 0.8 Timed weapon entries

A player's melee damage descriptor is the weapon's item record, whose four modifier slots
at item +0x24 are `{s16 type, s16 v1, s16 v2, s16 v3}`. `Player_tickEnchantTimers`
0x1bc560 runs every frame for a real player (not the prediction copy): for each of the 17
equipped items and each type in the list at 0x537c08 (0x15, 0x16, 0x18, 0x26, 0x17), it
takes v3 of the first entry of that type; if v3 ≥ 1 it writes v3 − 1 back, and when that
reaches 0 it sets every entry of that type on the item to −1. An entry with v3 = 0 is
permanent. Only equipped items are ticked.

## 1. wizardbeam — `SkillWizardBeam`

**Identity.** object `0x6e14d8`, virtual table `0x51a528`, kind 1, recast 30 frames, flags 0x0; canUse `0x3c8218`, cast `0x2f3b0c`, manaCost `0x2f3da8`, initStats `0x2f3aa0`. Channelled (kind 1). Class tree: wizard (class 4), base level
10, prerequisite skill 37. No monster casts it. canUse is the base function (always 1).

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 135 | 10.999804 | 0x412fff32 |
| s1 | 1 (players) | 1 | 8 | 0.33299997 | 0x3eaa7ef9 |
| s2 | 1 (players) | 5 | 1 | 0.33299997 | 0x3eaa7ef9 |
| s3 | 1 (players) | 5 | 4 | 0.19999999 | 0x3e4ccccc |

s0 damage per second, s1 reach (segment length and capture radius), s2 number of side
beams (capped at 6), s3 side-beam radius. Every read is `slot10` (tier 1) whoever the owner
is. describeRank prints s0 … round(1.2·s0), s1 and, when s2 ≠ 0, s2 and s3 (0x2f3b90).

**Cost and limits.** manaCost(L) = 26 + 2.0000079 × (L − 1) per second, i.e. that amount
when the cast fires and 1/60 of it per frame while held (§0.3). Recast 30 frames. Ends when
`Player_updateCast` destroys the held spell.

**Cast** (0x2f3b0c): allocate 0x380 bytes, `SpellWizardBeam_ctor(spell, L, caster, skill)`,
return the spell. Position and facing arguments are ignored.

**Constructor** (0x2f1528). Spell fields beyond the base:

| Offset | Type | Initial value | Meaning |
|---|---|---|---|
| +0x19, +0x1a | u8 | 0 | "chain initialised", "side chains initialised" |
| +0x28 + 12·i | vec3 ×6 | set on first run | chain nodes N[0..5], relative to the run position |
| +0x70 + 12·i | vec3 ×6 | set on first run | node velocities V[0..5] |
| +0xb8 | s32 | min(slot10(2, L), 6) | nSide |
| +0xec + 0x30·k + 12·j | vec3 | first hit | side chain k, node j (0..3); velocities at +0x20c + … |
| +0x32c + 4·k | float ×6 | 3 × slot10(3, L) | side chain segment length |
| +0x344 | float | 3 × slot10(3, L) | side segment length at rest |
| +0x348 | float | 2 × slot10(1, L) | segLen, current segment length |
| +0x34c | float | 2 × slot10(1, L) | segMax |
| +0x1c…+0x24, +0xbc…, +0xd4…, +0x350…, +0x37c | | | trail handles and ring timers (presentation) |
| +0x378 | u32 | from the hue draw | beam colour (presentation) |

Draws: one shared (seed), then one from the spell's own generator (the hue).

**Run** (0x2f1a44), every frame with `(pos, facing)` from §0.3:

```
dir = (cos16(facing), sin16(facing), 0)
if not initialised:  initialised = 1;  for i in 0..5:  N[i] = dir * (i * segLen);  V[i] = 0

R1 = slot10(1, L) * 12          R3 = slot10(3, L) * 12
tip = pos + N[5]

# 1. primary target
best = none;  bestD2 = R1*R1;  bestDist = 0
for o in box(tip ± (R1, R1, 100000)), at most 63, box order:
    if owner.isEnemy(o):
        d2   = |o.pos - tip|²                    # 3-D
        dist = sqrt((o.x-pos.x)² + (o.y-pos.y)²) # 2-D, from the run position
        if d2 < bestD2 and dist < segMax * 5:  best = o; bestD2 = d2; bestDist = dist

if best is none:
    segLen += (segMax - segLen) * 0.049999997
else:
    (sound, every frame)
    if not sideInitialised: sideInitialised = 1; lay out the side chains (presentation)

    # 2. side targets
    side = []
    for o in box(tip ± (R3, R3, 100)), at most 63, box order:
        if o != owner and o != best and o is a creature and owner.isEnemy(o)
           and |o.pos - tip|² < R3*R3 and len(side) < nSide:
            side.append(o)                       # with its 2-D distance from tip (presentation)

    # 3. pull the chain onto the target
    centre = best.pos + (0, 0, best.height * 0.5)
    for i in 1..5:  N[i] += (centre - (N[i] + pos)) * powf(i * 0.19999999, 3.0)
    segLen += (min(segMax * 5, bestDist * 1.0999999) * 0.19999999 - segLen) * 0.049999997

    (flash on best; side-chain geometry and trails — presentation)
    if best's model has sample points (count n != 0):
        10 draws from the spell's generator (sample index = draw mod n)     # trail only

    # 4. damage, three times a second
    if frame % 20 == 0:
        d = (float) trunc(slot10(0, L) * 0.3333333)
        r = draw(spell)
        damage(d, d + d * r/65536 * 0.19999999, best, owner, 100000, 0x100, null, 0)
        for s in side (in the order found):
            d = (float) trunc(slot10(0, L) * 0.25 * 0.3333333)
            r = draw(spell)
            damage(d, d + d * r/65536 * 0.19999999, s, owner, 100000, 0x100, null, 0)

# 5. chain physics — always, target or not
prev = dir * segLen
for i in 1..5:
    want = N[i-1] + prev
    N[i] += V[i]
    if i < 5:  want = (want * 3 + (N[i+1] + N[i-1]) * 0.5) * 0.25
    seg  = N[i] - N[i-1]
    V[i] = (V[i] + (want - N[i]) * 0.060439996) * 0.85499996
    prev = normalize(seg) * segLen
    N[i] = N[i-1] + prev
```

`powf` is the library routine reached through 0x3a5ac8 (*Inferred* from the body at
0x3a7930, a standard single-precision pow). N[0] stays (0, 0, 0). The chain is five
segments long, so without a target the tip rests 10 × s1 units ahead of the run position
and a target is captured inside a box of ± 12 × s1 around the tip. In step 5 the three
components are updated in the order z, x, y for `N[i] += V[i]` and y, z, x for V; it makes
no numerical difference.

A null descriptor makes `damage_apply` use its all-empty default. Flag 0x100 is the
lightning colour class.

**Draws, in order.** Cast: shared ×1 (seed), spell ×1. Per frame with a target: spell ×10
if the target's model has sample points; on frames divisible by 20: spell ×1 then
`damage_apply`'s own shared draws for the primary, then the same for each side target.

**Presentation only.** All trails (`trail_create` 0x190ff8 and helpers 0x1918a0, 0x191e58,
0x1911e8, 0x1920e0), the colour pulse written to the targets' flash fields, both sounds,
the side-chain node simulation (+0xec…, +0x20c…, +0x32c…), ring timers at +0x350.

**Per-machine state.** None read. The frame counter drives only trail phases. Not cast for
the prediction copy (flag bit 0 clear). A non-player caster would work but would get tier-1
numbers, since every read is `slot10`.

**Functions read.** 0x2f3a2c (ctor, via the table tool), 0x2f3aa0, 0x2f3b0c, 0x2f3b90,
0x2f3da8, 0x2f1528, 0x2f1a44, 0x2f3928 (dtor: releases trails).

**Not determined.** Float behaviour of the library `powf` beyond its identity; the
presentation helpers were not read.

## 2. dodge (and 83 berserkerdodge) — `SkillDodge`

**Identity.** object `0x6e1540`, virtual table `0x519d98`, kind 3, recast 30 frames, flags 0x0; canUse `0x3c8218`, cast `0x3c8220`, manaCost `0x2e8a88`, initStats `0x2e89a4`. Id 83 is the same class (object 0x6e3628; the constructor
0x2e8914 takes the id and picks the name). Passive (kind 3): never cast; cast is the base
function returning 0. Trees: id 2 barbarian (class 0), base level 5, prerequisite skill 61;
id 83 berserker (class 5), base level 12, prerequisite passive mask 0x40.

**Statistics** (identical for 2 and 83, `SkillDodge_initStats` 0x2e89a4):

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 20 | 2.9999838 | 0x403fffbc |
| s0 | 2 (others) | 1 | 5 | 5 | 0x40a00000 |

s0 is the chance, in percent, to dodge a missile.

**Cost.** manaCost 0x2e8a88 returns 0.

**Behaviour.** The only reader is `MissileWeapon_onTouch` 0x152a18 (objects area), at
0x152e5c–0x152f70, when a missile object touches something (the preceding parts of that
function — owner tests, the two shared draws it makes for skill 93 when the missile belongs
to a player — were not read for this document):

```
chance = 0
if victim is a player:
    c2  = trunc( (rank(2)  ? slot10(0, rank(2))  * 0.01 : 0) * 100.0 )      # 0x2e8ac0
    c83 = trunc( (rank(83) ? slot10(0, rank(83)) * 0.01 : 0) * 100.0 )
    chance = max(c2, c83)
else if victim is a creature and victim.slot36() != 0:      # 4 for a mini-boss, 10 for a boss
    chance = Dodge(2).slot11(0, victim.slot36(), cap 0)     # tier 2: 20 and 50
d = shared draw                                             # always, even when chance is 0
if (d mod 100) + 1 < chance:
    dodged: player victims get the block-spark effect (0x1b9658);
            if the missile has a model and is not one of three named item models, a debris
            prop (0x248 bytes, `PhProp`) is created at the missile's position;
            the missile is deleted; no damage call is made
```

So the real probability is (chance − 1) %. For players the percentage goes through two
single-precision multiplies (× 0.01, then × 100.0) and a truncation, which loses 1 whenever
the product lands just under the integer. *Inferred* (computed, not seen on hardware): with
a multiplier that truncates, which is how this project models the console's FPU
(`tools/ee_emu.py`), the result is s0 − 1 at every level 1–20, so a level-1 player dodges
18 % of missiles, not 20 %; with IEEE round-to-nearest only levels 1, 2, 12 and 14 lose the
1. A rebuild has to follow the console's rule. Three item descriptors are parsed on the dodge
path to learn the excluded models; their definitions have no variants, so no draw is made
there (item definitions 122, 123, 126: variant bits 0). The debris prop is a GameObject:
one shared draw (*Inferred*: its constructor 0x155bdc was not read, only seen to reach the
common prop constructor).

**Per-machine state.** None in the part read. The prediction copy is never a missile
victim (box queries skip it).

**Functions read.** 0x2e8914, 0x2e89a4, 0x2e8a00, 0x2e8a88, 0x2e8ac0; in
`MissileWeapon_onTouch` only the block from 0x152e5c (victim classification) through the
dodge branch and its deletion call.

**Not determined.** The rest of `MissileWeapon_onTouch`.

## 3. resistpoison — `SkillResistPoison`

**Identity.** Object 0x6e15a8, built inline by the static initialiser 0x16ac74 (no separate
constructor), virtual table 0x5126f8, passive (kind 3), recast 30. Every slot is the base
function except describeRank (0x3c8cb4). Not in any class tree.

**Statistics.** Base `initStats` 0x3c85b0:

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 0 | 1 | 2 | 0x40000000 |
| s1 | 1 (players) | 0 | 1 | 2 | 0x40000000 |
| s2 | 1 (players) | 0 | 1 | 2 | 0x40000000 |
| s3 | 1 (players) | 0 | 1 | 2 | 0x40000000 |
| s4 | 1 (players) | 0 | 1 | 2 | 0x40000000 |

**Behaviour.** None found. Nothing loads the table entry 0x41b17c, no call of
`player_getSkillRank` passes id 3, and no tree row offers it, so no rank can exist and no
code asks for a value (Observed for direct references; a computed index into
`g_skillTable` reaches only ids taken from ability records and tree rows). Treat as unused.

**Per-machine state.** None; nothing runs.

**Functions read.** 0x3c85b0, 0x3c8220 (base cast, returns 0), 0x3c82a8 (base manaCost,
returns 1.0).

## 4. diseasebolt — `SkillDiseaseBolt` / `DiseaseBolt`

**Identity.** object `0x6e1610`, virtual table `0x518468`, kind 0, recast 30 frames, flags 0x0; canUse `0x2cb368`, cast `0x2cb1c0`, manaCost `0x2cb33c`, initStats `0x2cb14c`. Active. Class tree: shadowknight (class 2), base level 3,
prerequisite skill 60. Monsters: Bubo and Horsemen call the cast slot; the Mummy builds the
projectile itself (`docs/skills.md`). canUse always 1.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 30 | 9.008915 | 0x41102484 |
| s1 | 1 (players) | 5 | 1 | 0.33299997 | 0x3eaa7ef9 |
| s0 | 2 (others) | 1 | 2 | 2.0000038 | 0x40000010 |
| s1 | 2 (others) | 1 | 1 | 0.099999994 | 0x3dcccccc |

s0 damage, s1 homing turn rate in degrees per frame. describeRank prints s0 …
round(1.2·s0).

**Cost.** manaCost(L) = 9 + 2.0000129 × (L − 1). Recast 30.

**Cast** (0x2cb1c0): caster flash (+0x98, +0x9a, +0x9c = −100, +0x9e = 0); allocate 0x7c;
`DiseaseBolt_ctor(obj, facing, L, pos, caster, skill)`; returns 0 (no Spell).

**`DiseaseBolt`** (0x7c bytes, table 0x5183d8; constructor 0x2c9eb0):

| Offset | Type | Initial value | Meaning |
|---|---|---|---|
| +0x38 | s16 | facing | heading |
| +0x4c | handle | caster | owner (from `Projectile_ctor`) |
| +0x54 | handle | caster | owner again (used by the hit handler) |
| +0x58 | handle | see below | homing target |
| +0x5c | Skill* | skill | |
| +0x60 | s16 | L | level |
| +0x64, +0x68, +0x6c | float | cos16(facing)·350, sin16(facing)·350, 0 | velocity, units per second |
| +0x70 | s32 | frame + 300 | expiry frame |
| +0x74 | s32 | frame + 10 | homing starts after this frame |
| +0x78 | s32 | 0 | "has hit" |

Radius 12, flags |= 0x4081. Target choice in the constructor, only when there is an owner:
`world_collectObjectsInArc(279.99988, 60.0, 0, pos, facing, list, no filter)`; the target is
the first list entry for which `owner.isEnemy(entry)`. Then the object joins the every-frame
run list. Draws: one shared (seed).

**Run** (0x2ca1a8), each frame:

```
particles from the object's generator:  5 × (S, S),  5 × (S, S),  6 × (S, S)        # §0.1
if target handle is set and frame > armFrame(+0x74):
    step = slot13(1, L, &owner(+0x4c), cap 10) * 182
    diff = atan2_16(target.y - y, target.x - x) - facing       # plain integers, NOT wrapped to 16 bits
    if |diff| < step:  facing += diff
    elif diff < 1:     facing -= step
    else:              facing += step                           # facing is stored as s16
    velocity = (cos16(facing)*350, sin16(facing)*350, 0)
r = obj_moveAndCollide(self, velocity)                          # may call onHit, §0.6
if (r & 2) and hasHit:  expiry = 0
if (r & 1):             expiry = 0
if expiry <= frame:
    sound; fx_spawn(0xc, pos); 10 × [(S, S), (S, S), (S, S)] particles; delete self
```

Because the angle difference is not wrapped, a target on the far side of the ±0x8000 seam
is turned toward the long way round. With s1 = 0 (player levels 1–4) the step is 0 and the
bolt flies straight. The handle empties when the target object is deleted; a dead but
present creature is still followed.

**Hit** (slot 6, 0x2caec8), called for every object the bolt overlaps:

```
if hasHit: return
if owner(+0x54) is empty:
    if other is not a creature: hasHit = 1                      # and carry on
else if not owner.isEnemy(other): return                        # allies are passed through
if other is a non-player creature with creature flag 0x200 (blocking): return
dmg = slot13(0, L, &owner(+0x4c), cap 0)
desc = empty;  desc.slot0 = {0x26, dmg, dmg, 0}                 # disease, see id 29
r = draw(object)
damage(dmg, dmg + dmg * r/65536 * 0.19999999, other, owner or null, 100000, 0, desc, 0)
hasHit = 1
```

**Draws, in order.** Cast: shared ×1. Each frame: object ×(16 particles × 2 sphere loops);
on a water impact object ×1 inside the move; on a hit object ×1 then `damage_apply`'s
shared draws (which include the SpellDiseaseEffect constructor's seed when the victim gets
the disease); on expiry object ×(60 sphere loops).

**Presentation only.** Particles, the two sounds, `fx_spawn(0xc)` (cosmetic generator,
camera-gated inside), the draw function 0x2ca09c.

**Per-machine state.** None. A non-player owner gets tier 2 and the level cap 10 on the
turn rate.

**Functions read.** 0x2cb0e0, 0x2cb14c, 0x2cb1c0, 0x2cb264, 0x2cb33c, 0x2cb368, 0x2c9eb0,
0x2ca1a8, 0x2caec8.

## 5. diseaseshield — `SkillDiseaseShield` / `SpellDiseaseShield`

**Identity.** object `0x6e1678`, virtual table `0x518638`, kind 0, recast 30 frames, flags 0x0; canUse `0x2ce2b0`, cast `0x2cdff8`, manaCost `0x2ce284`, initStats `0x2cdf64`. Active. Class tree: shadowknight, base level 10, prerequisite
skill 6. Monsters: Bubo calls the cast slot; the Mummy constructs the spell directly.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 20 | 2 | 0x40000000 |
| s1 | 1 (players) | 1 | 2 | 0.250008 | 0x3e80010c |
| s2 | 1 (players) | 1 | 5 | 0.24999899 | 0x3e7fffbc |
| s0 | 2 (others) | 1 | 1 | 2 | 0x40000000 |
| s1 | 2 (others) | 1 | 5 | 0.049999997 | 0x3d4ccccc |
| s2 | 2 (others) | 1 | 1 | 0.099999994 | 0x3dcccccc |

s0 damage per tick, s1 radius in 12-unit steps, s2 duration in seconds. All reads are
`slot12` with the caster, so a monster gets tier 2 and the caps below.

**Cost and limits.** manaCost(L) = 43 + 4.0000167 × (L − 1). Recast 30. canUse (0x2ce2b0):
refused while the caster already carries a `SpellDiseaseShield`.

**Cast** (0x2cdff8): caster flash (+0x98, +0x9a, +0x9c = −100, +0x9e = 0); allocate 0x1b0;
`SpellDiseaseShield_ctor(spell, L, caster, skill)`; return the spell.

**Constructor** (0x2ccfc8):

| Offset | Type | Value | Meaning |
|---|---|---|---|
| +0x18 + 12·i, +0xd8 + 12·i | vec3 ×16 each | from the spell's generator | swarm positions and velocities (presentation) |
| +0x198 | vec3 | caster position | last owner position (presentation) |
| +0x1a4 | s32 | frame + slot12(2, L, caster, cap 20) × 60 | end frame |
| +0x1a8 | s32 | slot12(1, L, caster, cap 10) × 12 | full radius |
| +0x1ac | float | 0 | current radius |

Draws: shared ×1 (seed), then spell ×16 × (S, S) for the swarm.

**Run** (0x2cd318), each frame with the run position `pos`:

```
if frame >= end: delete self; return
if radius < fullRadius: radius += 0.5
particles and swarm from the spell's generator (counts grow with radius² — presentation)
if frame % 30 == 0:
    R = (float) trunc(radius)
    for o in box(pos ± R on all axes), at most 63, box order:
        if owner.isEnemy(o):
            dmg  = slot12(0, L, owner, cap 0)
            desc = empty; desc.slot0 = {0x26, dmg, dmg, 0}
            r = draw(spell)
            damage(dmg, (dmg + dmg * r/65536 * 0.19999999) * 0.5, o, owner, 100000, 0x40, desc, 0)
```

The second argument is half of the rolled value and therefore always below the first
(0x2cddec–0x2cde2c: `min` is copied before the roll is added, `max` is the sum times 0.5).
By §0.7 fact 1 `damage_apply` then makes no base roll and deals exactly `dmg` before its
own modifiers. The spell's draw is still made. The tick is on the global frame counter, not
on time since the cast, so the first tick comes 0–29 frames after the cast. Flag 0x40: not
blockable. The radius reaches its full size after 2 × fullRadius frames.

**Stacking.** One per caster (canUse). Nothing refreshes it. The disease entry attaches a
`SpellDiseaseEffect` to a victim that has none (id 29).

**Draws.** Cast: shared ×1, spell ×(32 sphere loops). Each frame: spell ×(particles). Each
tick: spell ×1 per enemy, then `damage_apply`'s shared draws. The spell's generator never
decides anything (the one roll it feeds is discarded), so it need not be reproduced.

**Presentation only.** Particles (definitions 0x8e5280, 0x8e52d0), the 16-point swarm drawn
as glows, two sounds.

**Per-machine state.** None.

**Functions read.** 0x2cdef8, 0x2cdf64, 0x2cdff8, 0x2ce284, 0x2ce2b0, 0x2ccfc8, 0x2cd318.
Not read: describeRank 0x2ce090; `DiseaseCorpse` (0x2ce3f8, 0x2ce4a4) and `DiseaseCloud`
(0x2ce610, 0x2ce6e0), which share the source file but are created only by monster code
(0x2996c4), never by this skill.

## 6. diseasetrail — `SkillDiseaseTrail` / `SpellDiseaseTrail` / `DiseaseTrail`

**Identity.** object `0x6e16e0`, virtual table `0x518580`, kind 0, recast 30 frames, flags 0x0; canUse `0x2cce28`, cast `0x2ccba0`, manaCost `0x2ccdfc`, initStats `0x2ccb64`. Active. Class tree: shadowknight, base level 8, prerequisite
skill 4. No monster use found.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 10 | 2 | 0x40000000 |
| s1 | 1 (players) | 1 | 3 | 0.33299997 | 0x3eaa7ef9 |

s0 damage of a trail segment, s1 lifetime of a segment in seconds. Both are read with
`slot10` (tier 1) by the segment object. describeRank prints s0 … round(1.2·s0) and s1,
choosing a singular text when s1 = 1.

**Cost and limits.** manaCost(L) = 36 + 3.503986 × (L − 1). Recast 30. canUse (0x2cce28):
refused while the caster carries a `SpellDiseaseTrail`.

**Cast** (0x2ccba0): caster flash as id 5; allocate 0x30;
`SpellDiseaseTrail_ctor(spell, pos, L, caster, skill)`; return the spell.

**`SpellDiseaseTrail`** (0x30 bytes, table 0x518608; constructor 0x2cc080):

| Offset | Type | Value | Meaning |
|---|---|---|---|
| +0x18 | handle | first segment | newest segment (never read back) |
| +0x1c | vec3 | cast position | last drop point |
| +0x2c | float | (float) trunc(frame + 180.0) | end frame |

The constructor creates the first segment with both end points at the cast position, and
plays a sound. Draws: shared ×1 (spell seed), shared ×1 (segment's `GameObject_ctor`).

Run (0x2cc248), each frame with run position `pos`:

```
if (float)frame >= end: delete self; return
4 particles from the spell's generator (1 draw + (S, S) each)       # presentation only
if |last - pos| > 36.0 (3-D)  and  (pos.x-last.x)² + (pos.y-last.y)² > 1024.189:
    clear the segment handle
    new DiseaseTrail(L, from = last, to = pos, owner, skill)        # shared ×1
    last = pos
```

So the caster drops a segment every time it has moved more than about 36 units, for 180
frames. The spell's generator feeds only particles.

**`DiseaseTrail`** (0x68 bytes, table 0x5184f0; constructor 0x2cb4e8):

| Offset | Type | Value | Meaning |
|---|---|---|---|
| +0x10 | vec3 | `from` | position (the damage box is centred here) |
| +0x1c, +0x20 | float | 33, 36 | radius, height |
| +0x4c | vec3 | `to` | other end (particles only) |
| +0x58 | s32 | frame + slot10(1, L) × 60 | expiry |
| +0x5c | handle | owner | |
| +0x60, +0x64 | s32, Skill* | L, skill | |

Flags |= 0x4421f, which includes the dead and not-drawn bits, so no query returns it.

Run (0x2cb65c), each frame:

```
if frame >= expiry: delete self; return
particles from the object's generator: 4 × (1 draw, S, S)          # counts 1, 1, 2 by type
if frame % 15 == 0:
    hitAny = false
    for o in box(position ± 19 on all axes), at most 63, box order:
        if o is a creature and not dead:
            if owner handle is set and not owner.isEnemy(o): continue
            dmg  = slot10(0, L)
            desc = empty; desc.slot0 = {0x26, dmg, dmg, 0}
            r = draw(object)
            damage(dmg, dmg + dmg * r/65536 * 0.19999999, o, owner or null, 100000, 0x40, desc, 0)
            hitAny = true
    if hitAny: sound; delete self
```

A segment is a one-shot trap: on the first 15-frame tick that finds a target it damages
every target in the box and disappears. With the owner gone (handle empty) it hits every
living creature, players included, with no attacker.

**Draws.** Per segment: shared ×1 at creation; each frame object ×(4 + 8 sphere loops);
per target object ×1 then `damage_apply`'s draws.

**Presentation only.** Particles (0x8e5190, 0x8e51e0, 0x8e5230), sounds.

**Per-machine state.** None. A non-player caster gets tier-1 numbers (the reads are
`slot10`).

**Functions read.** 0x2ccaf8, 0x2ccb64, 0x2ccba0, 0x2ccc3c, 0x2ccdfc, 0x2cce28, 0x2cc080,
0x2cc248, 0x2cb4e8, 0x2cb65c.

## 7. firestorm — `SkillFireStorm` / `FireStorm` / `FireStormFlare`

**Identity.** object `0x6e1748`, virtual table `0x518d28`, kind 0, recast 30 frames, flags 0x0; canUse `0x2d532c`, cast `0x2d4f7c`, manaCost `0x2d5300`, initStats `0x2d4ef4`. Active. Class tree: wizard, base level 20, prerequisite skill
57. Monsters: Cazic and Horsemen call the cast slot; Goblin, Demon, Mummy and RedDragon
construct `FireStorm` themselves (`docs/skills.md`). A second constructor, 0x2d4048, takes
radius, damage, duration, flare period and flare scale as arguments and sets the variant
field to 1; its one caller is the monster function 0x25f988.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 108 | 2.001009 | 0x40001088 |
| s1 | 1 (players) | 1 | 2 | 0.33299997 | 0x3eaa7ef9 |
| s2 | 1 (players) | 1 | 2 | 0.33299997 | 0x3eaa7ef9 |
| s0 | 2 (others) | 1 | 5 | 2.5 | 0x40200000 |
| s1 | 2 (others) | 1 | 2 | 0.099999994 | 0x3dcccccc |
| s2 | 2 (others) | 1 | 2 | 0.099999994 | 0x3dcccccc |

s0 fire damage per second, s1 radius in 12-unit steps (also the casting distance), s2
duration in seconds. describeRank prints s0 … round(1.2·s0), s1, s2.

**Cost and limits.** manaCost(L) = 43 + 10.999907 × (L − 1). Recast 30. canUse (0x2d532c),
players only:

```
rank = player rank of skill 7
pt   = caster.pos.xy + dir(caster.facing) * (slot10(1, rank) * 12);   pt.z = 0
if terrain_height(12.0, world, pt) - caster.z < -144.0: refuse       # target spot far below
```

**Cast** (0x2d4f7c):

```
r1 = slot12(1, L, caster, cap 10)
centre.xy = pos.xy + (caster is a player ? dir(facing) * r1 * 12 : 0)
centre.z  = terrain_height((float) r1, world, centre) + 6.0
new FireStorm(0xb4 bytes)(L, caster, centre, skill)                   # returns 0, no Spell
```

`facing` is the auto-aimed cast facing (§0.3), while canUse tested the player's own facing.

**`FireStorm`** (table 0x518c98; constructor 0x2d41f8, common part 0x2d4480):

| Offset | Type | Value | Meaning |
|---|---|---|---|
| +0x4c | handle | caster | owner |
| +0x50…+0x88 | | | embedded light (presentation) |
| +0x8c | s32 | slot13(0, L, &owner, cap 0) | damage per second |
| +0x90 | s32 | see below | end frame |
| +0x94 | s32 | slot13(2, L, &owner, cap 20) × 60 | duration |
| +0x98 | s32 | see below | start frame |
| +0x9c | s32 | slot13(1, L, &owner, cap 10) × 12 | radius R |
| +0xa0 | float | 0 | light radius (presentation) |
| +0xa4 | float | L × k × 0.5 + 0.29999998, k = 0.049999997 for a player owner, 0.02 otherwise | flare scale (presentation) |
| +0xa8 | s32 | 15 | flare period |
| +0xac | s32 | sound handle | |
| +0xb0 | s32 | 0 | variant (1 for the second constructor) |

Flags |= 0x421b. The common part dereferences the owner without a null test.

```
if owner is a non-player creature:
    start = trunc(frame + 40.499996)                 # 40-frame warning
    new LightEffect at centre + (0, 0, 12)           # shared ×1
    end = duration + start
else:
    start = 0;  end = duration + frame
```

Draws at cast: shared ×1 (`GameObject_ctor`), plus shared ×1 for the warning light when the
owner is a monster.

**Run** (0x2d470c), each frame:

```
if not (start < frame): return
if frame >= end or owner handle is empty: delete self; return
(light radius animation — presentation)
if frame % period == 0:                              # every 15th frame
    P = unitSphere(object)
    from = (x + P.x*R, y + P.y*R, z + 240.02234)
    if variant == 0:  Q = unitSphere(object);  to = position + Q*R
    else:             to = from
    to.z = terrain_height(12.0, world, to)
    new FireStormFlare(scale, from, normalize(to - from) * 15.000689, variant)     # shared ×1
if frame % 30 == 0:
    for o in box(position ± R on all axes), at most 63, box order:
        if owner.isEnemy(o):
            half = damage / 2                        # integer division
            r = draw(object)
            desc = empty; desc.slot0 = {0x15, half, half + (s16)trunc(half * r/65536 * 0.19999999), 0}
            damage(0, 0, o, owner, 100000, 0x40, desc, 0)
```

All damage is the fire entry (§0.7 fact 3): `half … 1.2·half`, less fire resistance, and
the burn status. `FireStormFlare` (0x6c bytes, table 0x518c08, constructor 0x2d3184, run
0x2d33c0) is a falling fireball with no damage call: it moves, emits particles from its own
generator, may leave a decal, and deletes itself. It matters only because creating it
costs a shared draw every 15 frames.

**Draws, in order within a frame.** Frame % 15 == 0: object ×(one or two sphere loops), then
shared ×1 (flare). Frame % 30 == 0: per enemy object ×1, then `damage_apply`'s shared draws
(one for the fire entry among them).

**Presentation only.** The light, the looping sound, flares, the warning `LightEffect`.

**Per-machine state.** None. Non-player owner: tier 2 numbers with level caps 10 (radius)
and 20 (duration), the 40-frame delay and the extra shared draw.

**Functions read.** 0x2d4e88, 0x2d4ef4, 0x2d4f7c, 0x2d510c, 0x2d5300, 0x2d532c, 0x2d4048,
0x2d41f8, 0x2d4480, 0x2d4664, 0x2d470c, 0x2d3184, 0x2d33c0 (run: checked for damage calls,
stores to other objects and generator use only).

## 8. fireflares — `SkillFireFlares` / `SpellFireFlares` / `FireFlare`

**Identity.** object `0x6e17b0`, virtual table `0x519470`, kind 0, recast 30 frames, flags 0x0; canUse `0x2dd8b8`, cast `0x2dd4e8`, manaCost `0x2dd88c`, initStats `0x2dd470`. Active. Class tree: wizard, base level 18, prerequisite skill
57. No monster use found.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 95 | 5.0009108 | 0x40a00776 |
| s1 | 1 (players) | 7 | 32 | 0.999999 | 0x3f7fffef |
| s2 | 1 (players) | 1 | 8 | 0.999994 | 0x3f7fff9b |
| s3 | 1 (players) | 1 | 1 | 0.33299997 | 0x3eaa7ef9 |

s0 damage of a flare, s1 explosion damage (0 below level 7), s2 duration in seconds, s3
number of flares (capped at 16). Every read is `slot10`.

**Cost and limits.** manaCost(L) = 17 + 10.999825 × (L − 1). Recast 30. canUse (0x2dd8b8):
refused while the caster carries a `SpellFireFlares`.

**Cast** (0x2dd4e8): allocate 0x78; `SpellFireFlares_ctor(spell, L, caster, pos, skill)`;
return the spell. No flash.

**`SpellFireFlares`** (table 0x5194f8; constructor 0x2dcd40):

| Offset | Type | Value | Meaning |
|---|---|---|---|
| +0x18 | handle list | the flares | |
| +0x28 | s32 | frame + slot10(2, L) × 60 | end frame |
| +0x68 | s32 | 2·L + 65 | orbit radius target |
| +0x6c | s32 | 4500 / ((2·L + 65) / 12) | angle step per frame (both divisions integer) |
| +0x70 | s32 | 0 | current orbit radius |
| +0x2c…+0x64, +0x74 | | | light, sound handle (presentation) |

```
n  = min(slot10(3, L), 16)
da = (s16)(0xfffe / n)                         # integer division; n = 0 divides by zero
a  = 0
repeat n times:
    new FireFlare(0x6c bytes)(position = cast pos, L, caster, skill, angle = (s16) a)     # shared ×1 each
    link it into the list;  a += da
```

Draws: shared ×1 (spell seed), then shared ×1 per flare.

Run (0x2dd1ac), each frame with run position `pos`:

```
if frame >= end: delete self; return
if cur < target: cur += 2
for each flare still in the list:
    flare.angle += step                        # s16 wrap
    flare.position = (pos.x + cos16(angle)*cur, pos.y + sin16(angle)*cur, pos.z)
    update the flare's grid cell
if the list is empty: delete self
```

The destructor (0x2dd0c8) deletes every remaining flare.

**`FireFlare`** (table 0x5193e0; constructor 0x2dbd20): radius 24, flags |= 0x421d, caster
kept as a **raw pointer** at +0x4c (safe only because the spell, and with it the flares,
is destroyed with the caster), level +0x50, Skill +0x54, state +0x58 = 0, angle +0x5c,
burst size +0x5e = 0.

Run (0x2dbf10), each frame:

```
state 0 (orbiting):
    particles from the object's generator: 6 × (S, S), 7 × (S, S), 4 × (S, S)
    if frame % 10 == 0:
        r24 = (float) trunc(radius)                                   # 24
        victim = first o in box(position ± r24), at most 63, box order, with caster.isEnemy(o)
        if victim:
            d = slot10(0, L);  r = draw(object)
            desc = empty; desc.slot0 = {0x15, d, d + (s16)trunc(d * r/65536 * 0.19999999), 0}
            damage(0, 0, victim, caster, 100000, 0x40, desc, 0)
            state = 1;  remember victim position (+0x60);  sound
            if slot10(1, L) != 0:                                     # explosion, level 7 up
                for o in box(position ± 2*r24), at most 63, box order, with caster.isEnemy(o):
                    d1 = slot10(1, L);  r = draw(object)
                    desc = empty; desc.slot0 = {0x15, d1, (s16)trunc(d1 + d1 * r/65536 * 0.19999999), 0}
                    damage(0, 0, o, caster, 100000, 0x40, desc, 0)
state 1 (burst):
    if burst < radius*3 and slot10(1, L) != 0:  burst += 7; 110 burst particles; return
    delete self
```

The explosion box contains the first victim again, so it is hit twice. Without an explosion
the flare vanishes on the frame after its hit; with one it lingers 11 frames. A deleted
flare drops out of the spell's list; when none are left the spell ends early.

**Draws.** Per orbiting flare per frame: object ×(34 sphere loops). On a hit: object ×1,
`damage_apply`'s shared draws, then per explosion victim object ×1 and the same.

**Order within a frame.** Flares are GameObjects on the every-frame run list; the spell
moves them from the caster's own run. Which comes first decides whether a flare tests its
box at this frame's or last frame's position; it follows the run-list order (objects area)
and was not pinned down here.

**Presentation only.** Particles (0x8e59b0, 0x8e5a00, 0x8e5a50), the light, sounds, draw
0x2dbe00.

**Per-machine state.** None.

**Functions read.** 0x2dd404, 0x2dd470, 0x2dd4e8, 0x2dd570, 0x2dd88c, 0x2dd8b8, 0x2dcd40,
0x2dd0c8, 0x2dd1ac, 0x2dbd20, 0x2dbf10.

## 9. riposte (and 82 berserkerriposte) — `SkillRiposte`

**Identity.** object `0x6e1818`, virtual table `0x519528`, kind 3, recast 30 frames, flags 0x0; canUse `0x3c8218`, cast `0x2ddb90`, manaCost `0x3c82a8`, initStats `0x2ddae4`. Id 82 is the same class (constructor 0x2dda54 takes the id).
Passive (kind 3); cast (0x2ddb90) returns 0; canUse and manaCost are the base functions.
Trees: id 9 barbarian (base level 15, prerequisite skill 41) and shadowknight (base level
15, prerequisite skill 67); id 82 berserker (base level 15, prerequisite skill 81).

**Statistics** (`SkillRiposte_initStats` 0x2ddae4). Id 9:

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 0 | 20 | 4 | 0x40800000 |
| s1 | 1 (players) | 1 | 10 | 0 | 0x00000000 |
| s0 | 2 (others) | 1 | 2 | 2.0000088 | 0x40000025 |
| s1 | 2 (others) | 1 | 15 | 0 | 0x00000000 |

Id 82 differs only in the tier-1 base of s0:

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 0 | 10 | 4 | 0x40800000 |
| s1 | 1 (players) | 1 | 10 | 0 | 0x00000000 |
| s0 | 2 (others) | 1 | 2 | 2.0000088 | 0x40000025 |
| s1 | 2 (others) | 1 | 15 | 0 | 0x00000000 |

s0 damage dealt back, s1 chance in percent. Note the first level of s0 is 0, so the value
at level L is base + 4 × L. describeRank prints s0 … round(1.2·s0) and s1.

**Behaviour.** `SkillRiposte_counterAttack(skill, defender, attacker, level)` 0x2ddccc is
called from `damage_apply` (calls at 0x1ea568 and 0x1ea5c8; `docs/gameplay.md` §2.5 step 24) after the
second hit roll, when the hit has an attacker, its flags have any of the bits 0xd, and both
sides are creatures:

- defender is a player: called with skill 9 and the player's rank of 9 if that rank is not
  0, then again with skill 82 and the rank of 82 if not 0 (both can fire on one hit);
- defender is a monster with creature flag bit 45 (0x200000000000): called with skill 9 and
  level = trunc(`g_levelMonsterLevel` 0x4f714c).

```
counterAttack(skill, defender, attacker, level):
    if level == 0: return
    dmg    = slot12(0, level, defender, cap 10)
    chance = slot12(1, level, defender, cap 10)
    d = shared draw
    if trunc(d/65536 * 100.0) < chance:
        defender flash: both colour quads = (0x82, 0x82, 0x83, 0x55)
        if the defender's model (slot 16) reports a non-zero sample-point count:
            200 particles placed with the cosmetic generator
            d2 = shared draw
            damage(dmg, dmg + dmg * d2/65536 * 0.19999999, attacker, defender, 100000, 0x40, empty, noCrit 1)
```

The counter-hit is an ordinary `damage_apply` call with its own draws; flag 0x40 without
any of 0xd means it cannot itself be riposted or reflected. A monster defender uses tier 2
with the level capped at 10 (s0 ≤ 20, s1 = 15).

**Draws.** Shared ×1 per call; on success shared ×1 more, then the nested call's draws.

**Per-machine state.** The cosmetic generator is used for the particles only. The gate on
the model's sample-point count (0x1799c8) decides a shared draw and a hit; the count comes
from model data, which is the same on every machine (*Inferred*).

**Functions read.** 0x2dda54, 0x2ddae4, 0x2ddb90, 0x2ddbb8, 0x2ddccc; call sites in
`damage_apply` 0x1ea568 and 0x1ea5c8.

## 10. blessed — `SkillBlessed` / `SpellBlessed`

**Identity.** object `0x6e1880`, virtual table `0x519668`, kind 0, recast 30 frames, flags 0x0; canUse `0x2e000c`, cast `0x2dfeb8`, manaCost `0x2e0040`, initStats `0x2dfe5c`. Active. Class tree: cleric (class 1), base level 8,
prerequisite skill 55. No monster use.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 90 | 10 | 0x41200000 |
| s1 | 1 (players) | 1 | 30 | 0 | 0x00000000 |
| s2 | 1 (players) | 1 | 1 | 0.33339998 | 0x3eaab367 |
| s4 | 1 (players) | 1 | 1 | 1 | 0x3f800000 |

s0 mana regeneration bonus in percent, s1 duration in seconds (30 at every level), s2
number of orbiting sparkles (presentation, capped at 6), s4 mana cost. describeRank prints
s0.

**Cost and limits.** manaCost(L) = slot15 = (float) slot10(4, L) = L. Recast 30. canUse
(0x2e000c): refused while the caster carries a `SpellBlessed`; cast tests the same again.

**Cast** (0x2dfeb8): if the caster already has the spell return 0. Caster flash: both quads
(0x4b, 0x4b, 200, 0xf). Allocate 0xfc; `SpellBlessed_ctor(spell, L, caster, skill)`;
return the spell.

**Constructor** (0x2df078): end frame (+0xb4) = frame + slot10(1, L) × 60; six sparkle
records (+0x18…, +0x60…) from the spell's generator; a light at +0xc0. Draws: shared ×1,
then spell draws for the sparkles.

**Run** (0x2df4bc): while `frame < end`, light, a pulsing tint on the owner and
min(slot10(2, L), 6) sparkles with their particles (spell's generator); otherwise delete
self. Nothing else.

**Effect.** `Player_regenMana` 0x1b3900 (every frame, real players only, while hit points
> 0 and mana < maximum) computes the per-frame gain (the Regeneration call is at 0x1b3ae0):

```
gain = maxMana * 0.0001
p = passive level for mask 0x200;  if p > 0: gain *= (p * 0.14999999 + 1.1999999)
gain += (s8) playerObject[+0x475] * 0.0001
if class index (record +0x50) == 0: gain = 0
for each of the 17 equipped items with a modifier of id 0xc and value v: gain *= (v * 0.01 + 1.0)
if the player carries a SpellBlessed:  gain += gain * slot10(0, spell.level) * 0.01      # this skill
r = player rank of skill 19;  if r != 0: gain += gain * slot10(0, r) * 0.01              # id 19
mana = min(mana + gain, maxMana)
```

So Blessed multiplies natural mana regeneration by (1 + s0/100) for 30 seconds. A class-0
character (barbarian) has no natural regeneration to multiply.

**Draws.** Cast: shared ×1. The spell's generator feeds sparkles only.

**Presentation only.** Everything in the run function.

**Per-machine state.** None in the skill. `Player_regenMana` returns at once for the
prediction copy.

**Functions read.** 0x2dfdf0, 0x2dfe5c, 0x2dfeb8, 0x2dff84, 0x2e000c, 0x2e0040, 0x2df078,
0x2df42c, 0x2df4bc, 0x2dfdb8, and `Player_regenMana` 0x1b3900 as far as the block above.

## 11. summonskeleton — `SkillSummonSkeleton` / `SpellSummonSkeleton` / `Skelight`

**Identity.** object `0x6e18e8`, virtual table `0x519890`, kind 0, recast 30 frames, flags 0x0; canUse `0x2e2368`, cast `0x2e18a4`, manaCost `0x2e2340`, initStats `0x2e1844`. Active. Class tree: shadowknight, base level 15, prerequisite
skill 36. Monsters: Cazic, Horsemen and FemaleDarkElf call the cast slot.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 13 | 1 | 0x3f800000 |
| s1 | 1 (players) | 1 | 5 | 5 | 0x40a00000 |
| s0 | 2 (others) | 1 | 10 | 1 | 0x3f800000 |
| s1 | 2 (others) | 1 | 5 | 3.000048 | 0x404000c9 |

s0 the skeleton's strength (used as its monster level), s1 chance in percent that it gets
an elemental weapon. Reads are `slot12` with the caster and cap 10. describeRank prints s0
and s1.

**Cost and limits.** manaCost(L) = 86 + 5 × (L − 1). Recast 30. canUse (0x2e2368):

```
name = caster is a player ? per-slot name from the table at 0x503778 (slot >= 4 → refuse)
                          : the monsters' shared name (0x503788)
allow only if no object with that name exists (world_findObjectByName 0x14f498)
```

One skeleton per player slot, and one for all monster casters together. Monster run code
has to call canUse itself; the cast does not.

**Cast** (0x2e18a4):

```
caster flash: +0x98 = -128, +0x9a = -110, +0x9c = -128, +0x9e = 30
if the caster's model has sample points: 32 + 200 particles from the cosmetic generator
spawn.xy = pos.xy + dir(facing) * 72;   spawn.z = terrain_height(12.0, world, spawn)
if |spawn.z - caster.z| > 24.0:
    world_findFreeSpot(&out, caster.pos, range 72, radius 12, &found, 0)     # shared draws, 3 per try
    if found: spawn = out
d1 = shared draw                                                             # always
strength = slot12(0, L, caster, cap 10)
props = caster is a player ? property list for its slot (0x503750 + slot*8) : list at 0x503770
skel = new Skelight(0x468 bytes)(spawn, facing, props, strength)             # a creature
skel.flags |= 0x4000
chance = slot12(1, L, caster, cap 10)
if d1/65536 < chance * 0.01:
    k = (shared draw) mod 3
    weapon holder of the skeleton (+0x50): k = 0 → slot 2, k = 1 → slot 4, k = 2 → slot 6, each with argument 0
if caster is a player and L > 0:
    skel[+0x5a] = caster slot                      # followed player; arena kill credit
    skel.creatureFlags |= 0x400000                 # follows a player
    Creature_setCharm(skel, -1 (permanent), team of the caster)        # 0x1189f0
    skel.pointBlankRange(+0x3ac) = 400
    skel.slot34(500)                               # home range
sound
if skel was allocated: return new SpellSummonSkeleton(0x1c bytes)(L, caster, skill, skel)
return 0
```

Weapon-holder slots 2, 4 and 6 are the ones `Creature_init` calls for the `FireWeapons`,
`ColdWeapons` and `ShockWeapons` properties (`docs/creatures.md`); each builds an elemental
damage entry through `creature_buildElementDamage` 0x1176e0, which makes one shared draw and
reads tier 2 of skill 13, 14 or 12 at the current monster level.

`Skelight_ctor` 0x2a8770 (monsters area) stores the strength at +0x460 and sets the level
scale `g_levelMonsterLevel` to it while it calls `Creature_setStats(1.33, 1.2, 1.2, 1.0, …,
rollHp = 1)`, then restores the scale; creature kind 0x10 (undead). The skeleton's own
behaviour belongs to `docs/monsters.md`.

`SpellSummonSkeleton` (table 0x519918; constructor 0x2e16ec, run 0x2e177c) only holds a
handle to the skeleton at +0x18 and deletes itself when the handle empties. It does not
dismiss the skeleton when the caster dies.

**Draws, in order.** (`world_findFreeSpot` draws, if the height test fails) → shared ×1
(d1) → `Skelight` construction (its `GameObject_ctor` draw and whatever `Creature_ctor`,
`Creature_setStats` and `Creature_init` draw — not traced here) → on the elemental branch
shared ×1 (k) and the holder's draw → shared ×1 (spell seed).

**Presentation only.** Flash, particles (cosmetic generator), sound.

**Per-machine state.** Cosmetic generator for particles only. The player-slot reads are
guarded by the is-player test. For a non-player caster the skeleton is not charmed and is
named with the shared monster name.

**Functions read.** 0x2e17d8, 0x2e1844, 0x2e18a4, 0x2e227c, 0x2e2340, 0x2e2368, 0x2e16ec,
0x2e177c, `Skelight_ctor` 0x2a8770 (head only).

**Not determined.** The draws made inside the creature constructor chain; the contents of
the property lists at 0x503750–0x503788.

## 12. lightningweapons, 13. fireweapons, 14. coldweapons, 26. poisonweapons — the weapon buffs

Four classes built from the same template. They are specified together here; the sections
for 13, 14 and 26 only repeat identity and numbers.

**Identity.**

| Id | Skill class | Spell class (size, table) | Entry type T | Class tree (base level, prerequisite) | Monsters calling cast |
|---|---|---|---|---|---|
| 12 | `SkillLightningWeapons` | `SpellLightningWeapons` (0x24, 0x5199d0) | 0x18 lightning | wizard (12, skill 1) | — |
| 13 | `SkillFireWeapons` | `SpellFireWeapons` (0x60, 0x519a88) | 0x15 fire | wizard (20, skill 8) | Goblin |
| 14 | `SkillColdWeapons` | `SpellColdWeapons` (0x24, 0x519b40) | 0x16 cold | wizard (15, skill 96) | Goblin |
| 26 | `SkillPoisonWeapons` | `SpellPoisonWeapons` (0x24, 0x51c278) | 0x17 poison | shaman (14, skill 87) | FemaleDarkElf |

Id 12: object `0x6e1950`, virtual table `0x519948`, kind 0, recast 30 frames, flags 0x0; canUse `0x2e34ac`, cast `0x2e3184`, manaCost `0x2e3480`, initStats `0x2e30dc`.

**Statistics of id 12** (the others are in their own sections):

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 10 | 6.999984 | 0x40dfffde |
| s1 | 1 (players) | 1 | 10 | 0.50200194 | 0x3f008333 |
| s2 | 1 (players) | 6 | 8 | 1 | 0x3f800000 |
| s3 | 1 (players) | 6 | 21 | 0.99999696 | 0x3f7fffcd |
| s0 | 2 (others) | 1 | 2 | 1.9999969 | 0x3fffffe6 |
| s1 | 2 (others) | 1 | 15 | 2 | 0x40000000 |

For all four: s0 damage added to the weapon (the entry is s0 … round(1.2·s0)), s1 duration
in seconds, s2 radius of the aura in 12-unit steps (0 until its first level), s3 damage the
aura lends to other players' weapons; for id 26, s4 is the mana cost. describeRank prints
s0 … round(1.2·s0), s1 and, when s2 ≠ 0, s2 and s3 … round(1.2·s3).

**Cost and limits.**

| Id | manaCost(L) | Duration cap for non-players |
|---|---|---|
| 12 | 20 + 7.0007706 × (L − 1) | level capped at 20 |
| 13 | 35 + 11.000826 × (L − 1) | level capped at 20 |
| 14 | 25 + 9.0008745 × (L − 1) | no cap |
| 26 | (float) slot10(4, L) | level capped at 10 |

Recast 30. canUse (0x2e34ac, 0x2e4df8, 0x2e616c, 0x315bb0): refused while the caster
carries a spell of the same class. The four do not exclude each other.

**Cast** (0x2e3184, 0x2e4ad0, 0x2e5e44, 0x315be4): allocate the spell,
`ctor(spell, L, caster, skill)`, return it. Position and facing are ignored.

**Constructor** (0x2e24d8, 0x2e34e0, 0x2e4f94, 0x315f54):

```
end(+0x18) = frame + slot12(1, L, caster, cap) * 60
radius     = slot12(2, L, caster, cap 10) * 12      # ids 12, 13, 14: s32 at +0x1c
           = (float) slot10(2, L) * 12.0            # id 26: float at +0x20
fxEnd      = id 12: trunc(frame + 29.999878) at +0x20;   id 14: trunc(frame + 22.499683) at +0x20
             id 13: start frame at +0x5c;                id 26: frame + 30 at +0x1c (not read again)
dmg    = slot12(0, L, caster, cap 0)
frames = slot12(1, L, caster, cap) * 60

if caster is not a player:
    weapon holder (creature +0x50), if any: call its slot 6 / 2 / 4 / 5 (ids 12 / 13 / 14 / 26) with argument 1
else:
    w1 = record.weaponSet[activeSet]      (record +0x4434 + 4 × the s8 at +0x4a7c)
    w2 = record +0x443c                   (second weapon when dual wielding)
    for w in (w1, w2):
        if w is null or w.flags(+8, 64-bit) has bit 24 (thrown weapon): skip
        cur = v1 of the first entry of type T on w, or 0 when there is none
        if 0 <= cur < frames:
            if cur <= dmg:
                the first entry that is empty (−1) or already of type T becomes
                    {T, dmg, round(dmg + dmg * 0.19999999), frames}

ids 12, 14, 26: new LightEffect at the caster's position                    # shared ×1
flash on the caster: id 12 (+0x98..) = (0x6f, 0x70, 0x9a, 0x1e); id 14 (0x2d, 0x32, 0xff, 0);
                     id 26 (0x23, 0x80, 0x41, 0x1e); id 13 none (it carries its own light)
sound
```

The test `0 <= cur < frames` reads **v1, the minimum damage** of the existing entry, not
its remaining frames (0x2e26d0–0x2e2798: both lookups load the half-word at +0x26 of the
matching slot). With frames at least 600 it is true for any realistic entry, so the rule in
effect is: overwrite when there is no entry of that type or its minimum is not above the
new one. Each weapon is treated separately.

The entry then sits on the item (§0.8): every melee hit with that weapon carries it into
`damage_apply`, and the per-frame tick removes it when its v3 has counted down from
`frames`. It stays on the weapon if the spell ends early, and stops counting while the
weapon is not equipped. Types 0x15, 0x16, 0x18 add elemental damage `v1 … v2` per hit;
type 0x17 sets the victim's poison status values (`docs/gameplay.md` §2.2).

**Run** (0x2e2ac4, 0x2e3b28, 0x2e5578, 0x3164fc), each frame with run position `pos`:

```
if frame >= end:
    if owner is a non-player creature with a weapon holder: holder.slot8(a, 0)   # a = 0 for 12 and 26, 1 for 13 and 14
    delete self; return
(opening effect while frame < fxEnd, or for id 13 during the first 30 frames, plus its light)
if radius != 0 and owner is a player and frame % 30 == 0:
    aura = id 12, 26: slot10(3, L);  id 13: slot12(3, L, owner, cap 10);  id 14: slot12(3, L, owner, cap 0)
    for o in box(pos ± radius on all axes), at most 63, box order:
        if o != owner and o is a player and (PvP mode A is off or owner.sameTeam(o)):
            for w in (o's w1, o's w2) as above, skipping null and thrown weapons:
                cur = v1 of the first entry of type T, or 0
                if 0 <= cur < 31:
                    if cur <= aura:
                        first empty-or-T entry becomes {T, aura, round(aura + aura * 0.19999999), 31}
id 13 only, after the above: if the owner is a dead non-player creature:
    holder.slot8(1, 0); delete self
```

The aura gives nearby players a 31-frame entry every 30 frames. The same misread applies:
an ally's entry is refreshed only while its **minimum damage is below 31**. s3 reaches 31 at
level 16 for id 12, level 12 for id 14 and level 4 for id 26 (never within 20 levels for id
13); from there on an aura entry is written once, lapses after 31 frames and is written
again on the next tick after that, rather than being held continuously. The same test also
stops the aura from touching any weapon that already has an entry of that type with a
minimum of 31 or more, whatever its source. The caster's own weapon is never touched by the
aura.

Weapon-holder slot 8 is the one `Creature_init` uses for the `NoMagicWeapons` property
(`docs/creatures.md`); slots 2, 4, 5, 6 are FireWeapons, ColdWeapons, PoisonWeapons,
ShockWeapons. The holder bodies were not read.

**Monsters without the skill.** `creature_buildElementDamage` 0x1176e0 (creatures area),
called by those holder slots, reads tier-2 s0 of skill 13, 14, 26, 12 or 25 with level
trunc(`g_levelMonsterLevel`), makes one shared draw d and writes the entry
`{type, s0, s0 + (s16)trunc(s0 * 0.19999999 * d/65536), 0}` (types 0x15, 0x16, 0x17, 0x18,
0x26; a sixth case writes type 0x1f from skill 13).

**Draws.** Cast: shared ×1 (seed), shared ×1 (`LightEffect`, not id 13). The spell's own
generator is used only by the opening particles of ids 13 and 14. No draw in the aura.

**Presentation only.** `LightEffect`, flash, sounds, model particle effect (id 12,
0x1f61c0, camera-gated), particles (ids 13, 14), the light of id 13.

**Per-machine state.** None. Player-record reads are behind the is-player test in both
functions. Through the weapon-effect route (§0.3) the constructor still writes the entries
but the spell never runs, so there is no aura and no expiry handling for a monster's holder.

**Functions read.** Id 12: 0x2e3070, 0x2e30dc, 0x2e3184, 0x2e3208, 0x2e3480, 0x2e34ac,
0x2e24d8, 0x2e2ac4. Id 13: 0x2e4ad0, 0x2e4dcc, 0x2e4df8, 0x2e34e0, 0x2e3a98, 0x2e3b28.
Id 14: 0x2e5e44, 0x2e6140, 0x2e616c, 0x2e4f94, 0x2e5578. Id 26: 0x315be4, 0x315f20,
0x315bb0, 0x315f54, 0x3164fc. `Player_tickEnchantTimers` 0x1bc560,
`creature_buildElementDamage` 0x1176e0. The constructors and run functions of 13, 14 and 26
were compared against id 12 line by line and only their differences read; describeRank of
13, 14, 26 (0x2e4b54, 0x2e5ec8, 0x315c84) not read.

## 13. fireweapons — `SkillFireWeapons`

object `0x6e19b8`, virtual table `0x519a00`, kind 0, recast 30 frames, flags 0x0; canUse `0x2e4df8`, cast `0x2e4ad0`, manaCost `0x2e4dcc`, initStats `0x2e4a2c`. Behaviour: section 12.

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 21 | 6.999981 | 0x40dfffd8 |
| s1 | 1 (players) | 1 | 10 | 0.50299895 | 0x3f00c48a |
| s2 | 1 (players) | 6 | 2 | 0.33299997 | 0x3eaa7ef9 |
| s3 | 1 (players) | 6 | 15 | 1 | 0x3f800000 |
| s0 | 2 (others) | 1 | 2 | 2.0000188 | 0x4000004f |
| s1 | 2 (others) | 1 | 15 | 2 | 0x40000000 |

## 14. coldweapons — `SkillColdWeapons`

object `0x6e1a20`, virtual table `0x519ab8`, kind 0, recast 30 frames, flags 0x0; canUse `0x2e616c`, cast `0x2e5e44`, manaCost `0x2e6140`, initStats `0x2e5d98`. Behaviour: section 12.

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 14 | 7.0009737 | 0x40e007fa |
| s1 | 1 (players) | 1 | 10 | 0.50099695 | 0x3f004156 |
| s2 | 1 (players) | 6 | 12 | 1 | 0x3f800000 |
| s3 | 1 (players) | 6 | 25 | 0.999989 | 0x3f7fff47 |
| s0 | 2 (others) | 1 | 2 | 2.0000148 | 0x4000003e |
| s1 | 2 (others) | 1 | 15 | 2 | 0x40000000 |

## 15. undeadshield — `SkillUndeadShield` / `SpellUndeadShield` / `SpellSecondaryUndeadShield`

**Identity.** object `0x6e1a88`, virtual table `0x519f90`, kind 0, recast 30 frames, flags 0x0; canUse `0x2eb970`, cast `0x2eb7cc`, manaCost `0x2eb944`, initStats `0x2eb770`. Active. Class tree: cleric, base level 10, prerequisite skill
54. No monster use.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 50 | 4.002001 | 0x40801064 |
| s1 | 1 (players) | 1 | 10 | 1.249995 | 0x3f9fffd6 |
| s2 | 1 (players) | 1 | 25 | 2.002008 | 0x400020e6 |

s0 percentage of an undead attacker's damage thrown back, s1 duration in seconds, s2 the
percentage given to nearby players. All reads are `slot10`. describeRank prints s0, s1, s2.

**Cost and limits.** manaCost(L) = 41 + 4.000025 × (L − 1). Recast 30. canUse (0x2eb970):
refused while the caster carries a `SpellUndeadShield`.

**Cast** (0x2eb7cc): allocate 0x64; `SpellUndeadShield_ctor(spell, L, caster, skill)`;
return the spell.

**Constructor** (0x2ea4d8): end (+0x18) = frame + slot10(1, L) × 60; aura half-width
(+0x1c) = 85; a light (+0x20…), a particle group (+0x5c), a looping sound (+0x60). Draws:
shared ×1.

**Run** (0x2ea74c), each frame with run position `pos`:

```
if frame >= end: delete self; return
(light and owner tint — presentation)
if the owner's model has sample points (count n != 0):
    4 × [ 1 draw (index mod n), S, S ]  from the spell's generator        # particles
if frame % 15 == 0:
    for o in box(pos ± 85 on all axes), at most 63, box order:
        if o != owner and o is a player and (PvP mode A is off or owner.sameTeam(o)):
            if o carries neither SpellUndeadShield nor SpellSecondaryUndeadShield:
                attach new SpellSecondaryUndeadShield(0x24 bytes)(0.5 s, percent = slot10(2, L), o)   # shared ×1
```

`SpellSecondaryUndeadShield` (table 0x51a018; constructor 0x2eb050, run 0x2eb170): level
byte and Skill pointer are 0, percent at +0x1c, end (+0x18) = trunc(frame + 0.5 × 60.0). Its
run draws the same four model particles from its own generator and deletes itself at the
end frame. It lasts 30 frames and is handed out again only when absent, so whether an ally
is covered without a gap depends on whether the ally's or the caster's run comes first on
the frame it lapses (player run order; not pinned down here).

**Reflection.** `damage_apply` step 25 (`docs/gameplay.md`), after the riposte: when the
victim is a player, the attacker is a creature of kind 0x10 (undead) and the hit's flags
have any of 0xd, it looks for a `SpellUndeadShield` on the victim and, failing that, a
secondary one, and calls (0x1ea644, 0x1ea668)

```
SpellUndeadShield_damageAttacker(spell, victim, attacker, trunc(damage so far))        # 0x2eaec0
    if spell.level == 0: return
    victim flash: both quads = (100, 0x4d, 0x3f, 0x14)
    d = (float) trunc(incoming * slot10(0, L) * 0.01)
    r = draw(spell)
    damage(d, d + d * r/65536 * 0.19999999, attacker, victim, 100000, 0x40, empty, 0)

SpellSecondaryUndeadShield_damageAttacker(spell, victim, attacker, incoming)            # 0x2eb5b4
    the same with percent = spell[+0x1c] and no level test
```

**Draws.** Cast: shared ×1. Each frame: spell ×(4 + 8 sphere loops) when the model has
sample points. Each secondary created: shared ×1. Each reflection: spell ×1 (of whichever
spell reflected), then the nested call's shared draws. The reflection roll makes the
spell's particle draws matter.

**Presentation only.** Light, tint, particles, sound.

**Per-machine state.** None.

**Functions read.** 0x2eb704, 0x2eb770, 0x2eb7cc, 0x2eb850, 0x2eb944, 0x2eb970, 0x2ea4d8,
0x2ea6a4, 0x2ea74c, 0x2eaec0, 0x2eb050, 0x2eb170, 0x2eb5b4.

## 16. holystrike — `SkillHolyStrike` / `HolyStrike`

**Identity.** object `0x6e1af0`, virtual table `0x51a108`, kind 0, recast 30 frames, flags 0x0; canUse `0x2ed20c`, cast `0x2ecfcc`, manaCost `0x2ed1e4`, initStats `0x2ecf74`. Active. Class tree: cleric, base level 1, prerequisite skill
60. No monster use. canUse always 1.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 18 | 7.0009527 | 0x40e007ce |
| s1 | 1 (players) | 1 | 35 | 9.999926 | 0x411fffb2 |
| s2 | 1 (players) | 5 | 1 | 0.25 | 0x3e800000 |

s0 damage, s1 damage against undead (kind 0x10), s2 homing turn rate in degrees per frame
(0 below level 5). All reads are `slot10`. describeRank prints s0 … round(1.2·s0) and s1 …
round(1.2·s1).

**Cost.** manaCost(L) = 7 + 3 × (L − 1). Recast 30.

**Cast** (0x2ecfcc): caster flash, both quads (0xff, 200, 0x87, 0x40); allocate 0x80;
`HolyStrike_ctor(obj, facing, L, pos, caster, skill)`; returns 0.

**`HolyStrike`** (table 0x51a078; constructor 0x2eba48):

| Offset | Type | Value | Meaning |
|---|---|---|---|
| +0x38 | s16 | facing | heading |
| +0x4c, +0x54 | handle | caster | owner (twice, as in `DiseaseBolt`) |
| +0x58 | handle list | see below | candidate targets |
| +0x5c | s16 | L | |
| +0x60 | s32 | frame + 180 | expiry |
| +0x64 | s32 | frame + 15 | homing starts after this frame |
| +0x68 | Skill* | | |
| +0x6c, +0x70, +0x74 | float | cos16·450, sin16·450, 0 | velocity |
| +0x78 | s32 | 0 | "has hit" |
| +0x7c | s32 | trail handle | presentation |

Radius 12. Targets:
`world_collectObjectsInArc(360.0, 75.0, 0, pos, facing, &list(+0x58), filter)` with the
filter being the caster when it is a creature, so the list holds only the caster's enemies,
nearest at the head. Draws: shared ×1.

**Run** (0x2ebc50), each frame:

```
particles from the object's generator: 5 × (S, S), 10 × (S, S), 9 × (S, S)
if the list is not empty and frame > armFrame:
    target = object of the list's head node
    step = slot10(2, L) * 182
    turn toward the target exactly as DiseaseBolt does (unwrapped difference, section 4)
    velocity = (cos16(facing)*450, sin16(facing)*450, 0)
r = obj_moveAndCollide(self, velocity)
if (r & 2) and hasHit: expiry = 0
if (r & 1): expiry = 0
if expiry <= frame:
    sound; new LightEffect at the position (shared ×1); 25 × 3 particles (6 sphere loops each); delete self
```

**Hit** (slot 6, 0x2ecae8):

```
if hasHit: return
if owner is set and not owner.isEnemy(other): return
if other is a non-player creature with creature flag 0x200: return
kind = byte at other +0xb4                         # read whatever `other` is
dmg  = slot10(kind == 0x10 ? 1 : 0, L)
flags = PvP mode A ? 0 : 0x80000
r1 = draw(object)                                  # only decides a rounding branch
r2 = draw(object)
max = (float) trunc(dmg + dmg * r2/65536 * 0.19999999 + 1.0)     # when the r1 test value is >= 0, i.e. always for dmg > 0
damage(dmg, max, other, owner or null, 100000, flags, empty, 0)
other flash: both quads (0xff, 200, 0x87, 0x40)
hasHit = 1
```

The rounding adds 0.5 twice on the positive branch (0x2ecc8c: the constant is 1.0), so the
maximum is one higher than the usual `round(1.2·dmg)` idiom would give. The negative branch
computes `(x + 0.5) − 0.5`. Flag 0x80000 is one of the knock-back classes read by the
death code (`docs/creatures.md`, pending damage).

**Draws.** Cast: shared ×1. Each frame: object ×(48 sphere loops). Hit: object ×2, then
`damage_apply`'s draws. Expiry: shared ×1 (`LightEffect`), object ×(150 sphere loops).

**Presentation only.** Particles, trail, sounds, `LightEffect`, draw 0x2ecd90.

**Per-machine state.** None. Tier 1 for any owner.

**Functions read.** 0x2ecf08, 0x2ecf74, 0x2ecfcc, 0x2ed08c, 0x2ed1e4, 0x2ed20c, 0x2eba48,
0x2ebc50, 0x2ecae8.

**Not determined.** Whether a deleted target's node leaves the handle list or stays with a
null object (the run code dereferences the head node's object without a test).

## 17. hammerofwrath — `SkillHammerOfWrath` / `HammerOfWrath` / `SpellHammerOfWrath`

**Identity.** object `0x6e1b58`, virtual table `0x51a330`, kind 0, recast 30 frames, flags 0x0; canUse `0x2efef8`, cast `0x2efb20`, manaCost `0x2efecc`, initStats `0x2efacc`. Active. Class tree: cleric, base level 10, prerequisite skill
34. No monster use.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 40 | 2 | 0x40000000 |
| s1 | 1 (players) | 1 | 15 | 0.19999999 | 0x3e4ccccc |
| s2 | 1 (players) | 1 | 5 | 2.5 | 0x40200000 |

s0 damage of a blow, s1 lifetime in seconds, s2 chance in percent of the spinning attack.
All reads are `slot10`, and all use **level L + 1** (see the constructor). describeRank
prints s0 … round(1.2·s0), s1 … round(1.2·s1) and s2 at the plain level.

**Cost and limits.** manaCost(L) = 75 + 7.000969 × (L − 1). Recast 30. canUse (0x2efef8):
refused while the caster carries a `SpellHammerOfWrath`, i.e. while its hammer exists.

**Cast** (0x2efb20):

```
caster flash: both quads (-100, -100, -100, 0)
new GlowingShaft(0x5c bytes) at pos                                   # shared ×1, visual
new LightEffect at pos + (0, 0, 36)                                   # shared ×1, visual
hammer = new HammerOfWrath(0xe8 bytes)(pos + (0, 0, 60), facing, caster, L, skill)
return hammer ? new SpellHammerOfWrath(0x1c bytes)(L, caster, skill, hammer) : 0      # shared ×1
```

`SpellHammerOfWrath` (table 0x51a3b8; 0x2ef974, 0x2efa04) holds a handle to the hammer at
+0x18 and deletes itself when it empties.

**`HammerOfWrath`** (table 0x51a2a0; constructor 0x2edd78):

| Offset | Type | Value | Meaning |
|---|---|---|---|
| +0x38 | s16 | facing | rest heading (presentation) |
| +0x4c | handle | caster | owner |
| +0x50 | handle | empty | current target |
| +0x58 | item record, 0x48 bytes | see below | the damage descriptor of every blow |
| +0xa0 | s32 | 0 | state counter c |
| +0xa4 | s32 | L + 1 | level used for all statistics |
| +0xa8 | s32 | slot10(1, L + 1) × 60 | frames left |
| +0xac…+0xc0 | float | +0xb4 = 16384.0, rest 0 | orientation angles and their velocities (presentation) |
| +0xc4 | Skill* | | |
| +0xc8 | s32 | 0 | state |
| +0xcc | vec3 | 0 | velocity, units per **frame** |
| +0xd8 | vec3 | start position | goal point |

Flags |= 1. The item record is produced by `item_parseDescriptor` 0x1069b8 from one of five
descriptor texts chosen by L: base item `warhammer` with one `frostburst` modifier (effect
type 0x20: chance %, minimum, maximum cold damage):

| L | 0 | 1 | 2 | 3 | 4 and above |
|---|---|---|---|---|---|
| chance, min–max | 10, 10–20 | 12, 12–24 | 14, 14–26 | 16, 16–28 | 18, 18–30 |

The parser is called with variant −1, which ends in `item_randomizeVariant` 0x1046e0; the
`warhammer` definition has two model variants (bits 11–15 of its flag word are 2), so
**one shared draw** is made there (`draw mod 2`, model only). After parsing, the stored
level is incremented, which is why every later statistic lookup is one level high
(0x2edefc). The constructor also increments a byte counter at 0x41b4f0 that the destructor
(0x2edfd0) decrements; nothing else references it.

Draws at cast, in order: shared ×1 (shaft), ×1 (light), ×1 (hammer's `GameObject_ctor`),
×1 (variant), ×1 (spell seed).

**Run** (0x2ee068), each frame. `lvl` is +0xa4.

```
if owner handle is empty: delete self; return
anchor = owner.pos + (0, 0, 60)
if |anchor - position|² > 360000: state = 0                 # more than 600 away
if a cutscene is active: state = 0
blocked = owner is a player whose action state (+0x58c) is 8 (blocking);  if blocked: state = 0
k = 0.0029999998;  damp = 0.049999997                       # position spring, defaults

state 0 — follow and look for a target
    L0 = |goal - anchor|;  if L0 > 60: goal += (anchor - goal) * (1 - 60/L0)
    if no cutscene and not blocked:
        best = none;  bestD2 = 32400                        # 180²
        for o in box(anchor ± (180, 180, 1200)), at most 127, box order:
            if terrain_raycast(1.0, world, position, o.pos - position, 0) <= 0     # 0x18a5c0: nothing in the way
               and owner.isEnemy(o) and |anchor - o.pos|² < bestD2:
                best = o;  bestD2 = that distance²
        if best:
            target = best;  c = 0
            r = draw(object)
            state = (r/65536 * 100.0 < slot10(2, lvl)) ? 4 : 3

state 3 — strike
    if target handle is empty or target is dead (flag 8): state = 0
    else:
        a = target.pos + (0, 0, 60);  L3 = |goal - a|;  if L3 > 24: goal += (a - goal) * (1 - 24/L3)
        k = 0.0059999996;  damp = 0.14999999
        c += 1
        if c == 47:
            d = slot10(0, lvl);  r = draw(object)
            damage(d, d + d * r/65536 * 0.19999999, target, owner, 300000, 0x101, &itemRecord, 0)
        if c >= 61:  c = 0;  if PvP mode A: state = 0

state 4 — spin
    k = 0.01;  damp = 0.19999999
    c += 1
    if c >= 61 and c % 20 == 0:                              # c = 80, 100, 120
        victim = the o in box(position ± (72, 72, 1200)), at most 127, that is a creature,
                 not a player, not dead, with the smallest |position - o.pos|² below 5184
        if victim:
            d = slot10(0, lvl);  r = draw(object)
            damage(d, d + d * r/65536 * 0.19999999, victim, owner, 3000, 0x101, &itemRecord, 0)
    if target handle is empty:
        goal = owner.pos + (0, 0, 36) + (cos16(c << 9) * 36, sin16(c << 9) * 36, 0)
    else if target is dead: state = 0;  (skip the rest of this case)
    else: a = target.pos + (0, 0, 60);  L4 = |goal - a|;  if L4 > 24: goal += (a - goal) * (1 - 24/L4)
    if (c << 9) > 0x10000: state = 0                         # after c = 128

then, in every state:
    velocity.x += sin16(frame * 0x193) * 0.01
    velocity.y += sin16(frame * 0x166) * 0.01
    velocity.z += sin16(frame * 0x14c) * 0.01
    velocity += (goal - position) * k
    position += velocity
    velocity -= velocity * damp
    update the grid cell
    (orientation springs, model matrix, particles from generator 0x404468 — presentation)
    framesLeft -= 1;  if framesLeft < 1: delete self
```

Points worth copying exactly:

- The strike at c = 47 has no distance test. Once a target is chosen it is hit every 61
  frames (first after 47) for as long as it lives, the hammer is within 600 of the owner
  and the owner is not blocking, wherever the hammer model happens to be. Attack rating
  300000 makes the hit certain against any armour.
- The spin hits **any** living non-player creature near the hammer — there is no enemy
  test, so friendly creatures and the caster's own summoned skeleton qualify. The attacker
  passed is still the owner.
- State 0 runs the box query and one terrain ray per candidate every frame.
- When a case falls back to state 0 in the same frame the default k and damp apply.
- States 1 and 2 exist in the switch (a wind-up and a lunge that damages on contact) but no
  instruction in the class stores 1 or 2 from state 0 (stores to +0xc8 in the function:
  0, the 3-or-4 choice at 0x2ee638, 2 at 0x2ee6cc inside case 1, 3 at 0x2ee96c inside case
  2), so they are unreachable (*Inferred*: no other code writes the field).
- Flags 0x101: damage class bit 0x1 (arms riposte and undead shields on the victim) and
  the lightning colour bit.

**Draws.** Own generator: ×1 on each acquisition outside cutscenes, ×1 per blow; nothing
else uses it, so the sequence is short and exact. Each blow then makes `damage_apply`'s
shared draws, including the always-drawn chance roll for the cold entry.

**Presentation only.** Shaft, light, the hammer model and its orientation springs
(+0xac…+0xc0, driven by heading differences and `sin16(frame × 1024)`, `sin16(frame × 800)`),
particles (fourth generator), sounds, draw 0x2ef78c.

**Per-machine state.** The particle count uses the fourth generator 0x404468, which is
per-machine; it feeds nothing else. The cutscene flag is read from simulation code (shared
as long as cutscenes are, `docs/engine.md`).

**Functions read.** 0x2efa60, 0x2efacc, 0x2efb20, 0x2efd44, 0x2efecc, 0x2efef8, 0x2edd78,
0x2edfd0, 0x2ee068, 0x2ef974, 0x2efa04; `item_randomizeVariant` 0x1046e0 and the variant
branch of `item_parseDescriptor`.

**Not determined.** The exact return convention of the terrain ray 0x18a5c0 (used as "≤ 0
means clear"); whether `Creature_takeDamage` lets a friendly creature be hurt by the spin.

## 18. coneoffire — `SkillConeOfFire` / `SpellConeOfFire`

**Identity.** object `0x6e1bc0`, virtual table `0x51a3e8`, kind 1, recast 30 frames, flags 0x0; canUse `0x2f123c`, cast `0x2f1078`, manaCost `0x2f1210`, initStats `0x2f1008`. Channelled (kind 1). Class tree: wizard, base level 28,
prerequisite skill 7. Monsters: the Mummy constructs the spell directly with level
trunc(`g_levelMonsterLevel`) (0x299c68). canUse always 1.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 380 | 11.000813 | 0x41300354 |
| s1 | 1 (players) | 1 | 30 | 0.19999999 | 0x3e4ccccc |
| s0 | 2 (others) | 1 | 2 | 2 | 0x40000000 |
| s1 | 2 (others) | 1 | 30 | 0.049999997 | 0x3d4ccccc |

s0 nominal damage per second, s1 arc in degrees. Reads are `slot12` with the owner (cap 10
on s1, none on s0). describeRank prints s0 … round(1.2·s0) and s1.

**Cost and limits.** manaCost(L) = 51 + 1.000001 × (L − 1) per second (§0.3). Recast 30.
Ends when the held spell is destroyed.

**Cast** (0x2f1078): allocate 0x58; `SpellConeOfFire_ctor(spell, L, caster, skill)`; return
the spell. The constructor (0x2f00ac) sets up a light and a looping sound only. Draws:
shared ×1.

**Run** (0x2f02fc), each frame with run position `pos` and the owner's facing:

```
(light flicker)
a = slot12(1, L, owner, cap 10)
28 particles from the spell's generator: each (S, S, 2 draws), sprayed within ± a/2 degrees   # counts 20, 5, 3
if frame % 15 == 0:
    origin = (pos.x - cos16(facing)*12, pos.y - sin16(facing)*12, pos.z)
    arc    = slot12(1, L, owner, cap 10) + 10
    list   = world_collectObjectsInArc(96.0, arc, 0, origin, facing, no filter)
    for o in list, in list order:
        if owner.isEnemy(o):
            s0 = slot12(0, L, owner, cap 0)
            v1 = (s16) trunc(s0 * 0.25)
            q  = (float) trunc(s0 * 0.25)
            r  = draw(spell)
            v2 = (s16) trunc((q + q * r/65536 * 0.19999999) * 0.25)
            desc = empty; desc.slot0 = {0x15, v1, v2, 0}
            damage(0, 0, o, owner, 100000, 0x40, desc, 0)
```

**The maximum is scaled by 0.25 twice** (the code from 0x2f0da0 on), so v2 is about 0.25–0.3 of
v1. By §0.7 fact 3 the fire amount is then `v1 + (d mod (v1 − v2 − 1))` with d the shared
draw: for a level-1 player (s0 = 380, v1 = 95, v2 = 23…28) each tick deals 95 to about
165 before resistance, four ticks a second — noticeably more than the description's
380–456 per second. A rebuild that "fixes" the range will not reproduce the game's numbers.

When v1 = 1 (s0 from 4 to 7) v2 is 0 and the divisor is 0. That needs a non-player owner
(tier 2: s0 = 4 at level 2, 6 at level 3), i.e. a Mummy on a level whose monster level is 2
or 3. What the console then does is *Inferred* in §0.7 (the amount becomes 1 + d, up to
65536); it was not tested, and whether a Mummy appears at such a level was not checked.

**Draws.** Cast: shared ×1. Each frame: spell ×(56 sphere loops + 56). Each tick: spell ×1
per enemy, then `damage_apply`'s shared draws. The spell's draw changes v2 and through it
the modulus, so the particle draws have to be reproduced.

**Presentation only.** Particles, light, three sounds (start loop, hit, end in the
destructor 0x2f0224).

**Per-machine state.** None.

**Functions read.** 0x2f0f94, 0x2f1008, 0x2f1078, 0x2f10fc, 0x2f1210, 0x2f123c, 0x2f00ac,
0x2f0224, 0x2f02fc; the fire block of `damage_apply` 0x1e9850–0x1e9950.

## 19. regeneration — `SkillRegeneration`

**Identity.** object `0x6e1c28`, virtual table `0x51a4a0`, kind 3, recast 30 frames, flags 0x0; canUse `0x3c8218`, cast `0x2f1440`, manaCost `0x3c82a8`, initStats `0x2f141c`. Passive (kind 3); cast (0x2f1440) returns 0. Class tree:
ranger (class 3), base level 15, prerequisite skill 33.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 10 | 5.0000176 | 0x40a00025 |

s0 is a percentage added to natural mana regeneration.

**Behaviour.** One reader, `Player_regenMana` 0x1b3900: when the player's rank r of skill
19 is not 0, `gain += gain × slot10(0, r) × 0.01`, applied after the Blessed bonus (the
whole formula is in section 10). No cast, no cost, no draws.

**Per-machine state.** None; the function does nothing for the prediction copy.

**Functions read.** 0x2f13a8, 0x2f141c, 0x2f1440, 0x2f1468, 0x2f14f0.

## 20. blindinglight — `SkillBlindingLight` / `BlindingLightEffect` / `SpellBlindingLight`

**Identity.** object `0x6e1c90`, virtual table `0x51a670`, kind 0, recast 180 frames, flags 0x0; canUse `0x2f4b10`, cast `0x2f47dc`, manaCost `0x2f4ae4`, initStats `0x2f4768`. Active. Class tree: cleric, base level 10, prerequisite skill
10. No monster use. canUse always 1.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 50 | 0.99999696 | 0x3f7fffcd |
| s1 | 1 (players) | 1 | 35 | 1.9999989 | 0x3ffffff7 |
| s2 | 1 (players) | 1 | 3 | 0.200333 | 0x3e4d2418 |
| s3 | 1 (players) | 1 | 2 | 0.25 | 0x3e800000 |

s0 chance in percent to affect each enemy, s1 damage per second while blinded, s2 duration
in seconds, s3 radius in 12-unit steps. All reads are `slot10`. describeRank prints s0, s1
… round(1.2·s1), s2, s3.

**Cost and limits.** manaCost(L) = 45 + 7.0009565 × (L − 1). **Recast 180 frames.**

**Cast** (0x2f47dc):

```
caster flash: both quads (0x56, 0x80, 0xfa, 0x6e)
gfx_setColorOffset(0x80, 0x80, 0x80, 0)                    # 0x19b6bc: whole-screen flash
list = world_collectObjectsInArc(360.0, 90.0, 0, pos, facing, no filter)
sound on the caster
if the list is not empty and caster is not null:
    first = object at the head of the list                 # nearest creature in the arc, friend or foe
    if caster.isEnemy(first):
        new BlindingLightEffect(0x54 bytes)(first.pos, L, caster, skill)
return 0
```

If the nearest creature in the 90° arc is not an enemy (another player, a friendly
creature), nothing happens, although mana and the recast are still spent.

**`BlindingLightEffect`** (table 0x51a5e0; constructor 0x2f3f38): flags |= 0x421b; end
(+0x4c) = frame + 60; R (+0x50) = slot10(3, L) × 12. Everything that matters happens in the
constructor:

```
for o in box(position ± R on all axes), at most 63, box order:
    if caster.isEnemy(o):
        chance = slot10(0, L)
        if creature_bossRank(o) != 0:  chance = chance / 2 + 1          # integer division; 0x10d940
        r = draw(object)
        if r/65536 * 100.0 < chance:
            attach new SpellBlindingLight(0x20 bytes)(L, caster, o, skill) to o     # shared ×1
            o.slot31(slot10(2, L) * 60)                    # Creature slot 31: no-target timer +0x316
new LightEffect at the position                            # shared ×1
new GlowingShaft at the position                           # shared ×1
```

Its run (0x2f42e4) emits 12 particles a frame (4 draws each from its own generator) for 60
frames and deletes itself.

**`SpellBlindingLight`** (table 0x51a6f8; constructor 0x2f4474): owner = the victim; end
(+0x18) = frame + slot10(2, L) × 60; **the caster as a raw pointer at +0x1c**. Run
(0x2f4538):

```
if frame >= end: delete self; return
if victim.hitPoints(+0x228) > 0 and frame % 30 == 0:
    s1 = slot10(1, L);  r = draw(spell)
    damage((float)(s1 / 2), (s1 + s1 * r/65536 * 0.19999999) * 0.5, victim, caster, 100000, 0x40, empty, 0)
```

`s1 / 2` is an integer division. A second cast can attach a second spell to the same
creature (no test for an existing one); each ticks independently and the no-target timer is
simply set again.

**Draws, in order.** Cast: shared ×1 (effect object); per enemy in the box: object ×1 and,
on success, shared ×1 (spell seed); then shared ×2 (light, shaft). Per tick: spell ×1, then
`damage_apply`'s draws.

**Presentation only.** The screen flash, flashes, particles, light, shaft, sound.

**Per-machine state.** `gfx_setColorOffset` writes renderer state from simulation code on
every machine, for any caster — everybody's screen flashes. It is output only.
**Hazard:** the caster pointer in `SpellBlindingLight` is not a handle. A player object is
destroyed and rebuilt on respawn and on a level change (`docs/player.md`); a spell still
ticking on a monster would then pass a stale pointer to `damage_apply` as the attacker for
up to s2 seconds (*Inferred*; see section B).

**Functions read.** 0x2f46f0, 0x2f4768, 0x2f47dc, 0x2f4970, 0x2f4ae4, 0x2f4b10, 0x2f3f38,
0x2f42e4, 0x2f4474, 0x2f4538.

## 21. repulseundead — `SkillRepulseUndead`

**Identity.** object `0x6e1cf8`, virtual table `0x51a728`, kind 0, recast 30 frames, flags 0x0; canUse `0x3c8218`, cast `0x2f4d34`, manaCost `0x2f50a8`, initStats `0x2f4cfc`. Active. Class tree: cleric, base level 15, prerequisite skill
15. No monster use. canUse is the base function (always 1).

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 200 | 10 | 0x41200000 |
| s1 | 1 (players) | 1 | 6 | 0.5 | 0x3f000000 |

s0 damage, s1 radius in 12-unit steps (full damage inside s1 × 12, none beyond s1 × 24).
Reads are `slot10`. describeRank prints s0 and s1.

**Cost.** manaCost(L) = 59 + 3 × (L − 1). Recast 30.

**Cast** (0x2f4d34) — the whole skill; there is no spell or lasting object:

```
step = 0x10000 / (L + 4)                                   # integer division
for a = 0; a < 0x10000; a += step:
    new LostSoul(0xb0 bytes)(pos + (0, 0, 36), velocity (cos16(a), sin16(a), 50.0), a, owner none, mode 1, no light)   # shared ×1 each
new LightEffect at pos + (0, 0, 36)                        # shared ×1
dmg = slot10(0, L);   r = slot10(1, L)
damage_radial(inner r*12, outer r*24, caster, pos, dmg, flags 0xa100900, minimum 0, skip 0x40)
sound;  return 0
```

The number of souls is floor(65535 / step) + 1: 6 at level 1 (step 13107), 8 at level 4
(step 8192), 25 at level 20 (step 2730).

`damage_radial` 0x1ead58 (its only caller is this cast):

```
scale = (outer - inner > 1.0) ? dmg / (outer - inner) : 100.0
for o in box(pos ± outer on all axes), at most 127, box order:
    if o is not a creature:  skip when flags has 0x8000000 (it has)
    else: require (flags lacks 0x8000000 or o.kind(+0xb4) == 0x10)
          and (attacker is null or not a creature or attacker.isEnemy(o))
    if o == attacker or (o.flags & skip): continue
    dx = |o.x - pos.x|;  dy = |o.y - pos.y|
    dist = dx + dy - min(dx, dy) * 0.33299997 - o.radius   # octagonal approximation
    if dist < outer:
        amount = min(max((outer - dist) * scale, minimum), dmg)
        o.takeDamage((float) trunc(amount), attacker, flags)      # virtual slot 2, directly
```

So only undead enemies of the caster are hurt, players never (skip 0x40), and the amount
goes straight to take-damage: no hit roll, no armour, no resistance, no critical, no
floating number. Flags 0xa100900 = 0x8000000 (undead only) | 0x2000000 | 0x100000
(knock-back class on death) | 0x800 | 0x100 (hit flash).

`LostSoul` in mode 1 (`LostSoul_ctor` 0x2931bc, `LostSoul_run` 0x2933f4, monsters area) is
a rising trail: radius 0, no owner, lives 60 frames, moves by `obj_moveAndCollide` with its
velocity, and adds 50 to the vertical velocity each frame during its last 30 frames. It
does no damage. Because it moves through `obj_moveAndCollide` it still calls the touch
handlers of objects standing on its spot (§0.6).

**Draws.** Shared ×(number of souls), shared ×1 (light). Nothing else.

**Presentation only.** Souls, light, sound.

**Per-machine state.** None.

**Functions read.** 0x2f4c90, 0x2f4cfc, 0x2f4d34, 0x2f4fe4, 0x2f50a8, `damage_radial`
0x1ead58, `LostSoul_ctor` 0x2931bc, `LostSoul_run` 0x2933f4.

## 22. dismissundead — `SkillDismissUndead` / `HolyBolt`

**Identity.** object `0x6e1d60`, virtual table `0x51a7b0`, kind 0, recast 30 frames, flags 0x0; canUse `0x3c8218`, cast `0x2f645c`, manaCost `0x2f6674`, initStats `0x2f6404`. Active. Class tree: cleric, base level 25, prerequisite skill
21. No monster use. canUse is the base function.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 350 | 9.99986 | 0x411fff6d |
| s1 | 1 (players) | 1 | 80 | 7.9999347 | 0x40ffff77 |
| s2 | 1 (players) | 1 | 3 | 0.25 | 0x3e800000 |

s0 damage against undead, s1 damage against anything else, s2 lifetime in seconds. Reads
are `slot10`. describeRank prints s1 … round(1.2·s1), s0 … round(1.2·s0), s2.

**Cost.** manaCost(L) = 70 + 2.0010228 × (L − 1). Recast 30.

**Cast** (0x2f645c): allocate 0xc0; `HolyBolt_ctor(obj, pos, facing, L, caster, skill)`;
returns 0. No flash.

**`HolyBolt`** (table 0x50e908; constructor 0x2f5248):

| Offset | Type | Value | Meaning |
|---|---|---|---|
| +0x1c | float | 18 | radius |
| +0x38 | s16 | facing | heading |
| +0x4c | handle | caster | owner |
| +0x54 | s32 | frame + slot10(2, L) × 60 | expiry; 0 once it has hit |
| +0x58 | vec3 | cos16·350, sin16·350, 0 | velocity (replaced on the first run) |
| +0x64 | **raw pointer** | see below | target |
| +0x68 | vec3 | see below | aim point |
| +0xb8, +0xbc | Skill*, s32 | skill, L | |
| +0x74…, +0xb0, +0xb4 | | | light, voice handle, trail (presentation) |

Flags |= 0x4001 on top of the projectile flags. Target choice (the caster is dereferenced
without a null test):

```
front = none; frontD = 1e7;  back = none; backD = 1e7
for o in box(position ± 360 on all axes), at most 31, box order:
    if o is self or the caster or not a creature: continue
    d = |o.pos - position|                                  # 3-D
    if not (d < frontD or d < backD): continue
    if o.kind == 0x10 and o is not dead and caster.isEnemy(o):
        if dot(dir(caster.facing), o.xy - caster.xy) > 0:  front = o; frontD = d
        else:                                              back  = o; backD  = d
target = front if any, else back if any, else none
if none: aim = (x + cos16(caster.facing) * 48000, y + sin16(caster.facing) * 48000, z + 36)
```

The entry test is "nearer than **either** best", and the branch then overwrites its own
best unconditionally. Until an undead enemy behind the caster has been seen (`backD` still
1e7) every qualifying undead in front replaces the previous one, so the choice is the
**last** such creature in box order, not the nearest; the mirror-image holds for `back`. A
rebuild has to copy the loop as written. Draws: shared ×1.

**Run** (0x2f57b0), each frame:

```
if target:
    aim = (target.x, target.y, target.z + 36)
    diff = (s16)(atan2_16(aim.y - y, aim.x - x) - facing)   # wrapped here
    facing += (|diff| > 0x443) ? (diff < 1 ? -0x444 : 0x444) : diff
    if target is dead (flag 8): target = none
velocity.x = cos16(facing) * 240;  velocity.y = sin16(facing) * 240
dz = (s16) trunc(aim.z - z)
velocity.z = (-9 <= dz <= 9) ? 0 : (dz < 1 ? -50 : 50)
r = obj_moveAndCollide(self, velocity)
(trail)
if r == 1:                                                  # terrain only
    a = draw(object);  facing += (s16)(a mod 0x7fff) - 0x4000
    repeat 10 times:
        a = draw(object);  cand = (s16)(facing + (a mod 0x7fff) - 0x4000)
        if terrain_raycast(2.0, world, position, 24 units toward cand, 0) <= 0:  facing = cand
    sound; 25 particles (object's generator)
if expiry <= frame: delete self
```

The speed is 350 only until the first run sets it to 240. The bolt bounces off terrain
instead of ending there. The target pointer is cleared only when the target is flagged
dead; it is not a handle.

**Hit** (slot 6, 0x2f5fb4):

```
if other is not a creature: return
if owner is set and not owner.isEnemy(other): return
if expiry == 0: return
expiry = 0                                                  # deleted at the end of this run
new LightEffect at the position                             # shared ×1
50 particles (one sphere loop each, object's generator); sound
dmg = slot10(other.kind == 0x10 ? 0 : 1, L)
r = draw(object)
max = dmg + trunc(r/65536 * 0.19999999 * dmg)
damage((float)dmg, (float)max, other, owner or null, 10000000, 0x200c040, null, 0)
if other.hitPoints(+0x228) <= 0:
    new LostSoul(position, velocity, facing, mode 0, with light)        # shared ×1, visual, 600 frames
```

Any enemy creature stops the bolt, undead or not. Flags 0x200c040: unblockable, both sound
bits, 0x2000000.

**Draws.** Cast: shared ×1. Terrain bounce: object ×11 plus particles. Hit: shared ×1,
object ×(50 sphere loops), object ×1, `damage_apply`'s draws, shared ×1 if the victim died.

**Presentation only.** Light, trail, voice, particles, `LightEffect`, `LostSoul`, draw
0x2f5ddc.

**Per-machine state.** None. **Hazard:** the raw target pointer (section B).

**Functions read.** 0x2f6398, 0x2f6404, 0x2f645c, 0x2f64ec, 0x2f6674, 0x2f5248, 0x2f57b0,
0x2f5fb4.

## 23. shockoffrost — `SkillShockOfFrost` / `ShockOfFrost` / `FrostShard`

**Identity.** object `0x6e1dc8`, virtual table `0x51a958`, kind 0, recast 30 frames, flags 0x0; canUse `0x2f8b24`, cast `0x2f8840`, manaCost `0x2f8af8`, initStats `0x2f879c`. Active. Class tree: wizard, base level 1, prerequisite "any
rank in skill 60 or 61". Monsters: Goblin calls the cast slot; four monster functions
construct `ShockOfFrost` directly (functions 0x24c7fc, 0x287db0, 0x298d18, 0x2b5a08;
`docs/skills.md` lists Tormentor, Ulthork and Mummy). canUse always 1.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 30 | 7.9998927 | 0x40ffff1f |
| s1 | 1 (players) | 5 | 3 | 0.25 | 0x3e800000 |
| s2 | 1 (players) | 5 | 27 | 4 | 0x40800000 |
| s0 | 2 (others) | 1 | 3 | 3.000011 | 0x4040002e |
| s1 | 2 (others) | 10 | 1 | 0.099999994 | 0x3dcccccc |
| s2 | 2 (others) | 10 | 14 | 2 | 0x40000000 |

s0 cold damage of the bolt, s1 number of shards released when it ends, s2 cold damage of a
shard. Reads are `slot13` through the owner handle (tier 2 for monsters; cap 20 on s1).

**Cost.** manaCost(L) = 7 + 3.000033 × (L − 1). Recast 30.

**Cast** (0x2f8840): allocate 0xd0; `ShockOfFrost_ctor(obj, pos, facing, L, caster,
skill)`; returns 0. No flash.

**`ShockOfFrost`** (table 0x51a838; constructor 0x2f7404):

| Offset | Type | Value | Meaning |
|---|---|---|---|
| +0x38 | s16 | facing | |
| +0x4c, +0x54 | handle | caster | owner, twice |
| +0x94 | s16 | L | |
| +0x98 | s32 | 0 | spin angle (presentation) |
| +0x9c | vec3 | cos16·350, sin16·350, 0 | velocity |
| +0xc0 | s32 | frame + 120 | expiry |
| +0xc4 | s32 | 0 | "has hit" |
| +0xc8 | Skill* | | |
| +0xcc | pointer | 0 | last object hit (only compared, never dereferenced) |
| +0x58…+0x90, +0xa8…+0xbc | | | light, ribbon points (presentation) |

Radius 12. Draws: shared ×1.

**Run** (0x2f77c0), each frame:

```
(light, ribbon)
particles from the object's generator: 30 × (S, S), 20 × (S, S), 7 × (S, S, S, S)
r = obj_moveAndCollide(self, velocity)
if (r & 2) and hasHit: expiry = 0
if (r & 1): expiry = 0
if expiry <= frame:
    sound; fx_spawn(10, position)
    i = 0
    loop:                                                   # ice debris
        a = draw(object)
        if not (i < trunc(a/65536 * 4.0)): break
        new debris PhProp(0x248 bytes) at the position, model part 1 << i     # shared ×1 (GameObject) + its own draws
        i += 1
    n = slot13(1, L, &owner(+0x54), cap 20)
    repeat n times:
        a = draw(object);  ang = (s16)(facing + (a mod 0x7fff) - 0x4000)
        repeat 10 times:
            c = (s16) draw(object)
            if terrain_raycast(2.0, world, position, 24 units toward c, 0) <= 0:  ang = c
        new FrostShard(0x7c bytes)(position, ang, L, owner object, skill, exclude = lastHit)   # shared ×1
    delete self
```

The shard direction ends up as the last of ten random headings that had a clear 24-unit
path, or the first ±90° guess if none had. The owner handle at +0x54 is dereferenced
without a test when a shard is made. The debris loop draws once more than it creates.

**Hit** (slot 6, 0x2f84e4) — note there is no "already hit" test, so every object
overlapped in a frame is processed:

```
lastHit = 0;  attacker = null
if other is a creature:
    if owner(+0x4c) is set:
        if not owner.isEnemy(other): return
        attacker = owner
else: hasHit = 1                                            # a non-creature stops the bolt
if other is a non-player creature with creature flag 0x200: return
d = slot13(0, L, &owner(+0x4c), cap 0)
r = draw(object)
desc = empty; desc.slot0 = {0x16, d, d + (s16)trunc(d * 0.19999999 * r/65536), 0}
damage(0, 0, other, attacker, 100000, 0, desc, 0)
lastHit = other;  hasHit = 1
```

A non-creature is "damaged" with no attacker; `damage_apply` treats non-creatures with one
shared draw and a take-damage of 0 (`docs/gameplay.md` §2.5 step 4).

**`FrostShard`** (table 0x51a8c8; constructor 0x2f68e0, run 0x2f6b3c, hit 0x2f71ac):
projectile, radius 12, owner handles at +0x4c and +0x54, level +0x58, velocity (+0x60) =
dir(ang) × 350, expiry (+0x6c) = frame + 60, "has hit" +0x70, Skill +0x74, excluded object
+0x78. Run: particles 30 × (S, S) and 20 × (S, S) from its own generator, move, the same
two expiry rules, and on expiry one own draw (sound variant), `fx_spawn(10)`, the same
debris loop, delete. Hit: return if it has hit or `other` is the excluded object;
otherwise exactly the bolt's handler with statistic 2 instead of 0 and without the lastHit
bookkeeping. So shards do not hit the creature the bolt hit, and each shard hits once.

**Draws.** Bolt per frame: object ×(128 sphere loops). Hit: object ×1 per object, then
`damage_apply`'s draws (one for the cold entry). End: object ×(1 + debris count), shared ×1
per debris prop, then per shard object ×11 and shared ×1. Shards likewise. The debris props
are physics props in grid B (`docs/objects.md`). Their constructor chain (`PhProp_ctor`
0x155a0c → 0x153e54 → `GameObject_ctor`) contains no other reference to the shared
generator (checked by search, bodies not read); everything else they draw comes from the
prop's own generator.

**Presentation only.** Particles, light, ribbon, sounds, `fx_spawn(10)`, debris props, draw
0x2f76a8 / 0x2f6a18.

**Per-machine state.** None in these functions. The debris props are subject to the
low-memory cull in `runObjects` (`docs/objects.md`), which is per-machine offline only.

**Functions read.** 0x2f8730, 0x2f879c, 0x2f8840, 0x2f8af8, 0x2f8b24, 0x2f7404, 0x2f7604,
0x2f77c0, 0x2f84e4, 0x2f68e0, 0x2f6b3c, 0x2f71ac. Not read: describeRank 0x2f88d0.

## 24. poisonrain — `SkillPoisonRain` / `PoisonRain`

**Identity.** object `0x6e1e30`, virtual table `0x51aaf8`, kind 0, recast 30 frames, flags 0x0; canUse `0x2f9dec`, cast `0x2f9a3c`, manaCost `0x2f9dc4`, initStats `0x2f99c4`. Active, but in no class tree, and its tier-1 statistics are
all 0: it is a monster skill. FemaleDarkElf calls the cast slot; Mummy and Orc construct
`PoisonRain` directly. canUse always 1.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 0 | 0 | 0x00000000 |
| s1 | 1 (players) | 1 | 0 | 0 | 0x00000000 |
| s2 | 1 (players) | 1 | 0 | 0 | 0x00000000 |
| s0 | 2 (others) | 1 | 2 | 2 | 0x40000000 |
| s1 | 2 (others) | 1 | 2 | 0.099999994 | 0x3dcccccc |
| s2 | 2 (others) | 1 | 3 | 0.049999997 | 0x3d4ccccc |

s0 poison strength per tick, s1 radius in 12-unit steps, s2 duration in seconds. Reads are
`slot12`/`slot13` with caps 10 on s1 and s2.

**Cost.** manaCost(L) = 222 + 12 × (L − 1) (never charged to a monster).

**Cast** (0x2f9a3c): as Fire Storm's —

```
r1 = slot12(1, L, caster, cap 10)
centre.xy = pos.xy + (caster is a player ? dir(facing) * r1 * 12 : 0)
centre.z  = terrain_height((float) r1, world, centre) + 12.0
new PoisonRain(0x6c bytes)(L, caster, centre, skill, no sound)       # returns 0
```

**`PoisonRain`** (table 0x51aa68; constructor 0x2f8f48):

| Offset | Type | Value | Meaning |
|---|---|---|---|
| +0x4c | s32 | start + slot13(2, L, &owner, cap 10) × 60 | end frame |
| +0x50 | s32 | owner is a non-player creature ? trunc(frame + 40.499996) : 0 | start frame |
| +0x54 | float | slot13(1, L, &owner, cap 10) × 12 | radius R |
| +0x58 | s32 | slot13(0, L, &owner, cap 0) | (stored; the tick reads the statistic again) |
| +0x5c, +0x60 | s32, Skill* | L, skill | |
| +0x64 | handle | owner (linked without a null test) | |
| +0x68 | s32 | −1 or a sound handle | |

Flags |= 0x421b. A `LightEffect` is created (shared ×1). For a **player** owner the start
is 0 and the end is therefore the absolute frame number `duration × 60`, not a time from
now — the rain would end at once in any game older than a few seconds. With tier-1
statistics all 0 this path has no effect anyway.

**Run** (0x2f9254), each frame:

```
if not (start < frame): return
if frame >= end or owner handle is empty:
    stop the sound; new LightEffect (shared ×1); delete self; return
particles from the object's generator: two loops whose lengths are
    R*R*3.1415899*0.40243298*0.006944444 (3 draws each) and R*R*3.1415899*0.40464997*0.006944444 (4 draws each)
if frame % 30 == 0:
    Ri = (float) trunc(R)
    for o in box(position ± Ri on all axes), at most 63, box order:
        if owner.isEnemy(o):
            d = slot13(0, L, &owner, cap 0);  r = draw(object)
            desc = empty; desc.slot0 = {0x17, d, d + (s16)trunc(d * r/65536 * 0.19999999), 0}
            damage(0, 0, o, owner, 100000, 0x40, desc, 0)
```

Entry 0x17 writes its two values into the victim's poison fields (+0x358, +0x35a) and
starts the poison status (`docs/gameplay.md` §2.2); the damage itself is then dealt by
`Creature_run`'s 32-frame poison tick.

**Draws.** Cast: shared ×2 (object, light). Each frame: object ×(particle loops, counts
fixed by R). Each tick: object ×1 per enemy, then `damage_apply`'s draws. End: shared ×1.

**Presentation only.** Particles, lights, sound.

**Per-machine state.** None.

**Functions read.** 0x2f9958, 0x2f99c4, 0x2f9a3c, 0x2f9dc4, 0x2f9dec, 0x2f8f48, 0x2f9254.
Not read: describeRank 0x2f9bd0.

## 25. diseaseweapons, 27. hatebeam, 28. hatebeam (`SkillBallOfHate`), 30. hateeffect — statistic tables

These four ids have a Skill object but no behaviour of their own: cast is the base function
(returns 0), canUse the base (1), manaCost the base (1.0), and none is in a class tree.
Monster code reads one statistic from each. Constructors and `initStats` are outside the
skills range and were unnamed; names are proposed in `symbols/spec-skills-a.tsv`.

| Id | Class | Object | Table | Constructor | initStats | Kind |
|---|---|---|---|---|---|---|
| 25 | `SkillDiseaseWeapons` | 0x6e1e98 | 0x512560 | 0x16a98c | 0x16a9f8 | 0 |
| 27 | `SkillHateBeam` | 0x6e1f68 | 0x5124d8 | 0x16aa18 | 0x16aa8c | 1 |
| 28 | `SkillBallOfHate` | 0x6e1fd0 | 0x512450 | 0x16aaac | 0x16ab20 | 1 |
| 30 | `SkillHateEffect` | 0x6e20a0 | 0x5123c8 | 0x16abe0 | 0x16ac54 | 1 |

Id 25:

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 2 (others) | 1 | 4 | 2 | 0x40000000 |

Ids 27, 28 and 30 (identical):

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 2 (others) | 1 | 2 | 2 | 0x40000000 |

Tier 1 is unset, so a `slot10` read gives 0 and a player caster would get nothing. There
is no cast, no cost, no draw and no per-machine state in the skill objects themselves.

Readers found (each passes the Skill pointer on; what the receiving class does with it
belongs to `docs/monsters.md` and was not read here):

- 25: `creature_buildElementDamage` 0x1176e0, case 5 — a monster with the `DiseaseWeapons`
  property gets a disease entry `{0x26, s0, s0 + (s16)trunc(s0 × 0.19999999 × d/65536), 0}`
  with s0 = slot11(0, trunc(`g_levelMonsterLevel`), cap 0) and d one shared draw (see
  section 12).
- 27: `Innoruuk_run` 0x273bd0 passes it to `HateBeam_ctor` 0x277468 (object of 0xb0 bytes)
  with level trunc(`g_levelMonsterLevel`).
- 28: `Innoruuk_run` passes it to `HateProjectile_ctor` 0x278158 (0x190 bytes), three per
  volley, same level.
- 30: `HateBeam_run` 0x2775e8 and `HateProjectile_run` 0x2783e8 attach a `SpellHateEffect`
  (constructor 0x27930c, 0x30 bytes) to creatures they hit that have none, with arguments
  (3, trunc(`g_levelMonsterLevel`), victim, no attacker, skill 30).

## 26. poisonweapons — `SkillPoisonWeapons`

object `0x6e1f00`, virtual table `0x51c1f0`, kind 0, recast 30 frames, flags 0x0; canUse `0x315bb0`, cast `0x315be4`, manaCost `0x315f20`, initStats `0x315af8`. Behaviour: section 12 (entry type 0x17, weapon-holder slot 5, aura from
level 5). Class tree: shaman (class 6), base level 14, prerequisite skill 87. Cast passes
the level through slot 14, which changes nothing.

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 40 | 6.0009656 | 0x40c007e9 |
| s1 | 1 (players) | 1 | 15 | 2.0019948 | 0x400020af |
| s2 | 1 (players) | 5 | 2 | 0.334002 | 0x3eab024f |
| s3 | 1 (players) | 1 | 25 | 2.007998 | 0x4000830a |
| s4 | 1 (players) | 1 | 70 | 10.0007925 | 0x4120033f |
| s0 | 2 (others) | 1 | 2 | 2 | 0x40000000 |
| s1 | 2 (others) | 1 | 15 | 2 | 0x40000000 |

## 29. diseaseeffect — `SkillDiseaseEffect` / `SpellDiseaseEffect`

**Identity.** Object 0x6e2038, table 0x5125e8, constructor 0x16ab40, initStats 0x16abb4,
kind 1, recast 30; cast, canUse and manaCost are the base functions. Not in any tree. It is
the statistic table of the disease status that entry type 0x26 applies.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 3 | 1 | 0x3f800000 |
| s0 | 2 (others) | 1 | 1 | 1 | 0x3f800000 |

s0 is twice the damage of one disease tick.

**`SpellDiseaseEffect`** (0x1b0 bytes, table 0x518db0; constructor 0x2d5594, arguments
(spell, seconds, level, victim, attacker, skill)):

| Offset | Type | Value | Meaning |
|---|---|---|---|
| +0x00 | u8 | level | |
| +0x08 | Skill* | **0** | the base field is left null; the skill is kept at +0x1ac |
| +0x0c, +0x19c | Creature* | victim | owner |
| +0x18 | handle | attacker (empty when null) | source of the disease |
| +0x1c + 12·i, +0xdc + 12·i | vec3 ×16 each | spell's generator | swarm (presentation) |
| +0x1a0 | s32 | frame + seconds × 60 | end frame |
| +0x1a4 | s32 | seconds | |
| +0x1a8 | s32 | level | |
| +0x1ac | Skill* | skill | |

Draws: shared ×1 (seed), then spell ×16 × (S, S).

Who creates it:

- `damage_apply`, entry 0x26 with v1 ≠ 0, when the victim has no `SpellDiseaseEffect`:
  seconds = trunc(5.0 − victim.diseaseResistance(+0x68) × 5.0), **level 0**, the hit's
  victim and attacker, skill 29 (block at 0x1e9d68, constructor call at 0x1e9e28). The entry's v1 and v2 are not used
  for anything else, so Disease Bolt's "damage" in the entry only switches the status on.
- its own spread (below), also with level 0;
- `Bubo_run` 0x248598 in its death state, on itself (call at 0x249368): seconds 5, level =
  its slot 35, victim and attacker both itself;
- the script built-ins `hornOmen` (0x146628) and `planarSteel` (0x1466d4) pass skill 29
  and the value 1 to two other spell classes, one spell per player
  (`SpellHornOmenEffect_ctor` 0x2fc574, `SpellPlanarSteelEffect_ctor` 0x2fb728); those
  classes were not read.

**Run** (0x2d5854), each frame with run position `pos`:

```
if frame >= end: delete self; return
16 swarm points: one unitSphere(spell) each                      # particles, but see Draws
victim flash: +0x98 = 255, +0x9a = 255, +0x9c = 0, +0x9e = 0
if seconds > 1 and frame % 30 == 0:                              # contagion
    w = (float) trunc(victim.radius * 2)
    for o in box(pos ± w on all axes), at most 63, box order:
        if attacker handle is set and o is a creature
           and (attacker is not a creature or attacker.isEnemy(o))
           and o has no SpellDiseaseEffect:
            attach new SpellDiseaseEffect(trunc(seconds * 0.5 - o.diseaseResistance * 5.0), level 0,
                                          o, attacker, skill)     # shared ×1 + its swarm
if frame % 30 == 0 and attacker handle is set:
    d = trunc(slot12(0, level, attacker, cap 0) * 0.5);  if d < 1: d = 1
    r = draw(spell)
    damage(d, d + d * r/65536 * 0.19999999, victim, attacker, 100000, 0xc040, empty, 0)
```

With level 0 every statistic read returns 0, so a disease caught from a hit or by contagion
does **1 to 1.2 points every 30 frames** whatever the source's level; only Bubo's
self-inflicted one uses the table (tier 2: 1 + 1 × (level − 1), halved). Each generation of
contagion halves the seconds and subtracts the new victim's resistance term, so a 5-second
disease spreads to 2-second ones (resistance 0), which spread 1-second ones that do not
spread. A spread spell whose seconds come out 0 or negative is still constructed (draws
included) and deletes itself on its first run. The box is centred on the run position and
includes dead creatures. When the attacker is deleted the handle empties and both the
contagion and the damage stop, but the spell runs out its time. Flags 0xc040: unblockable,
no hit or miss sound.

**Stacking.** One per creature; a second application while one is present does nothing
(no refresh).

**Draws, in order within a tick frame.** Spell ×(16 sphere loops); per newly infected
creature shared ×1 and that spell's 32 sphere loops; then spell ×1 and `damage_apply`'s
shared draws. The damage roll reads the spell's generator after the swarm draws, so those
have to be reproduced.

**Presentation only.** The swarm (drawn as glows), flash.

**Per-machine state.** None.

**Functions read.** 0x16ab40, 0x16abb4, 0x2d5594, 0x2d5854, the 0x26 block of
`damage_apply`, the creation site in `Bubo_run`.

## 31. clericroot, 32. rangerroot (and 52 root, 85 shamanroot) — `SkillRoot` / `SpellRoot`

**Identity.** Id 31: object `0x6e2108`, virtual table `0x519ba0`, kind 0, recast 30 frames, flags 0x0; canUse `0x2e6534`, cast `0x2e6598`, manaCost `0x2e6894`, initStats `0x2e637c`. One class for four ids; the constructor 0x2e62b4 takes
the id and picks the name, `initStats` 0x2e637c picks the numbers. Active. Trees: 31 cleric
(base level 20, prerequisite skill 20); 32 ranger (12, passive mask 0x40); 52 wizard (23,
skill 12); 85 shaman (26, skill 65). No monster use.

**Statistics.** Id 31:

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 1 | 0.33299997 | 0x3eaa7ef9 |
| s1 | 1 (players) | 1 | 5 | 0.33299997 | 0x3eaa7ef9 |
| s2 | 1 (players) | 1 | 50 | 2.0000029 | 0x4000000c |
| s4 | 1 (players) | 1 | 55 | 4.000011 | 0x40800017 |

Id 32:

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 1 | 0.33299997 | 0x3eaa7ef9 |
| s1 | 1 (players) | 1 | 5 | 0.33299997 | 0x3eaa7ef9 |
| s2 | 1 (players) | 1 | 50 | 1.9999709 | 0x3fffff0c |
| s4 | 1 (players) | 1 | 30 | 3.00099 | 0x40401038 |

(Ids 52 and 85 are outside this document's range; `initStats` gives them their own
numbers, listed in `docs/skills.md`.) s0
maximum number of targets, s1 duration in seconds, s2 chance in percent, s4 mana cost. All
reads are `slot10`. describeRank prints s0, s1, s2.

**Cost and limits.** manaCost(L) = (float) slot10(4, L). Recast 30. canUse (0x2e6534): in
PvP mode A a player caster is refused and shown a HUD message for 90 frames; otherwise 1.
The message is raised for the prediction copy too, since canUse runs before the copy test
(local output only).

**Cast** (0x2e6598):

```
sound on the caster
n = slot10(0, L)
list = world_collectObjectsInArc(248.0, 120.0, 0, pos, facing, no filter)
count = 0
for o in list, in list order, while count < n:
    if (caster is null or caster.isEnemy(o))
       and o.flags lacks 0x1000000
       and creature_bossRank(o) == 0                # no mini-bosses, no bosses
       and o.rootTimer(+0x314) < 1:
        attach new SpellRoot(0x34 bytes)(L, o, skill) to o      # shared ×1
        count += 1
return 0
```

`pos` is the cast position (for a player the hand midpoint), `facing` the auto-aimed one.

**`SpellRoot`** (table 0x519b70; constructor 0x2e68c8): owner = the victim; elapsed seconds
t (+0x18, float) = 0; phase (+0x1c) = 0; duration (+0x20) = slot10(1, L); particle group
(+0x24); victim's position at the cast (+0x28).

Run (0x2e699c), each frame of the victim:

```
t += 0.016666666
phase 0:
    7 particles (2 draws each from the spell's generator)
    if t > 0.518994:                                    # reached on the 32nd run
        d = shared draw
        if slot10(2, L) <= (d mod 100) + 1:             # resisted
            100 particles; delete self; return
        victim flash: both quads (4, 0x5c, 0, 0x51)
        if victim is not a player: victim.rootTimer(+0x314) = (s16)(duration * 60)
        phase = 1
phase 1:
    22 particles on the victim's model (spell's generator)
    if victim is a player:
        victim.knockbackSpeed(+0x2e8) = sqrt((x - x0)² + (y - y0)²) * 4.0
        victim.knockbackAngle(+0x2e0) = (s16)(-0x4000 - atan2_16(x - x0, y - y0))
if duration < t - 0.518994: delete self
```

A monster is held by its root timer, which `Creature_run` counts down and `Creature_moveBy`
honours (`docs/creatures.md`); the spell itself only decorates it. A player victim is
instead pushed back toward the spot where the spell caught it, every frame, through the
knock-back fields (which `Creature_applyKnockback` ignores for players in a net game —
`docs/creatures.md` C9 — so in a net game a rooted player is not held at all; *Inferred*
from that note). The success probability is (s2 − 1) %.

**Stacking.** The cast skips a creature whose root timer is running, but a creature whose
spell is still in phase 0 can receive a second spell from another cast; each rolls
separately and the later success just rewrites the timer.

**Draws.** Cast: shared ×1 per target. Per spell: shared ×1 on its 32nd frame. The spell's
own generator feeds particles only.

**Presentation only.** Particles, flash, sound.

**Per-machine state.** The HUD message in canUse. Nothing else.

**Functions read.** 0x2e62b4, 0x2e637c, 0x2e6534, 0x2e6598, 0x2e6790, 0x2e6894, 0x2e68c8,
0x2e699c, 0x2e7034.

## 33. rangercriticalhit (and 53 criticalhit, 81 berserkercriticalhit) — `SkillCriticalHit` / `SpellCriticalHit`

**Identity.** Id 33: object `0x6e21d8`, virtual table `0x519c58`, kind 0, recast 30 frames, flags 0x0; canUse `0x2e7224`, cast `0x2e74b0`, manaCost `0x2e7690`, initStats `0x2e730c`. One class for three ids. The constructor 0x2e7258 gives
id 0x21 (33) the name `rangercriticalhit` and id 0x35 (53) the name `criticalhit`
(`docs/skills.md` has the two names the other way round; `docs/data-tables.md` already
notes it). Active. Trees: 33 ranger (base level 10, prerequisite skill 60); 53 barbarian
(8, skill 2); 81 berserker (10, passive mask 0x40). No monster use.

**Statistics.** Id 33:

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 10 | 2.002008 | 0x400020e6 |
| s1 | 1 (players) | 10 | 6 | 0.300997 | 0x3e9a1c47 |
| s2 | 1 (players) | 1 | 8 | 0.251 | 0x3e808312 |
| s4 | 1 (players) | 1 | 35 | 4.0009937 | 0x40800824 |

s0 critical-hit chance in percent while the spell is active, s1 radius of the aura in
12-unit steps, s2 duration in seconds, s4 mana cost. All reads are `slot10`. describeRank
prints s0, s2 and, when s1 > 0, s1.

**Cost and limits.** manaCost(L) = (float) slot10(4, L). Recast 30. canUse (0x2e7224):
refused while the caster carries a `SpellCriticalHit`.

**Cast** (0x2e74b0): allocate 0x5c; `SpellCriticalHit_ctor(spell, L, caster, skill)`;
return the spell.

**`SpellCriticalHit`** (table 0x519c28; constructor 0x2e7988): time left (+0x18, float) =
slot10(2, L) seconds; a light (+0x1c…); a particle group (+0x58). Draws: shared ×1.

Run (0x2e7acc), each frame: `t −= 0.016666666`; if `t < 0` delete self. Otherwise only
presentation: a tint on the owner (+0x90…+0x96 = 0x44, 0xe, 0x18, 0xf), the light during
the last two seconds, a ring of particles of radius slot10(1, L) × 12 (spell's generator),
and the same tint on every other living player inside that radius (same team in PvP mode
A).

**Effect.** The skill does nothing by itself; `damage_apply` asks for it in step 18
(`docs/gameplay.md`): when flag 0x40000000 is clear, the attacker is a player and `noCrit`
is 0,

```
c += max( chanceFor(Skill 33, attacker, rank(33)),
          chanceFor(Skill 53, attacker, rank(53)),
          chanceFor(Skill 81, attacker, rank(81)) )

chanceFor(skill, attacker, rank):                           # SkillCriticalHit_critBonusFor 0x2e76c4;
                                                            # calls at 0x1e8d5c, 0x1e8d7c, 0x1e8da4
    level = 0
    if rank != 0 and attacker carries a SpellCriticalHit:
        level = rank
    else:
        for slot in g_alivePlayers, in list order, slot != attacker's:
            p = that player's object
            if |p.pos - attacker.pos|² < 1e6                # 3-D, 1000 units
               and (PvP mode A is off or p.sameTeam(attacker))
               and p carries a SpellCriticalHit:
                r = max(rank of 53, rank of 81, rank of 33) of p
                if r != 0 and (p.x-attacker.x)² + (p.y-attacker.y)² < (skill.slot10(1, r) * 12)²:
                    level = r;  break
    return level ? skill.slot10(0, level) * 0.01 : 0
```

and then, if `c > 0` and the first hit roll succeeded, one shared draw decides the critical
hit (`draw < c × 65536` → damage × 3). Consequences to copy:

- a rank without the buff running gives nothing; the buff matters only through this query;
- the caster's own spell is found by class, not by which id cast it, and the percentage
  comes from each of the three tables at the attacker's rank of that id — a character has
  only one of the three, so in practice it is its own table;
- an ally in the aura gets the percentage of **each queried table at the aura owner's best
  rank**, with the aura radius also taken from the queried table; the largest of the three
  results is used. An ally therefore benefits even with no rank of its own, and the radius
  that applies is whichever table gives the largest s0 among those whose s1 reaches.

`g_alivePlayers` here is the all-players list (slots at 0x4f8440, count 0x4f8420), not
the local-only list at 0x4f8430, so the aura is shared state. It inherits that list's known
weakness: FINDINGS G11/G13 (after the prediction copy dies, one machine can run a frame
with its own player missing from the list). On such a frame the aura owner would be skipped
on that machine only, the chance `c` could differ, and with it whether the critical-hit
draw is made (*Inferred* consequence of G11; no new mechanism).

**Draws.** Cast: shared ×1. The crit roll is `damage_apply`'s.

**Presentation only.** Everything in the run function. The ring's particle count is
L − k + 14 with k = 1, 10, 5 for ids 53, 33, 81.

**Per-machine state.** The run function calls `net_objOrGhost` 0x13e180 on the owner for
particle placement (`docs/skills.md`, item 4); the number of draws does not depend on it.
The player-list dependence is described above.

**Functions read.** 0x2e7224, 0x2e7258, 0x2e730c (through the table tool), 0x2e74b0,
0x2e7534, 0x2e7690, 0x2e76c4, 0x2e7988, 0x2e7acc, 0x2e7f58; the call site in
`damage_apply`.

## 34. shieldbash — `SkillShieldBash` / `SpellShieldBash`

**Identity.** object `0x6e2240`, virtual table `0x51ada0`, kind 0, recast 30 frames, flags 0x0; canUse `0x2faa00`, cast `0x2faa88`, manaCost `0x2facb0`, initStats `0x2fa970`. Active. Class tree: cleric, base level 5, prerequisite skill
16. No monster use; the code assumes a player caster throughout.

**Statistics.**

| Stat | Tier | First level | Base | Step per level | Step bits (float32) |
|---|---|---|---|---|---|
| s0 | 1 (players) | 1 | 30 | 4.9999847 | 0x409fffe0 |
| s1 | 1 (players) | 1 | 20 | 2.0000048 | 0x40000014 |
| s2 | 1 (players) | 1 | 4 | 0.499999 | 0x3effffde |
| s3 | 1 (players) | 1 | 1 | 0.25000098 | 0x3e800021 |
| s4 | 1 (players) | 1 | 27 | 4.0019736 | 0x4080102b |

s0 damage (dealt as round(0.8·s0) … round(1.2·s0)), s1 stun chance in percent, s2 stun
duration in seconds, s3 maximum number of targets, s4 mana cost. All reads are tier 1.
describeRank prints the s0 range, s1, s2 and, when s3 ≠ 1, s3.

**Cost and limits.** manaCost(L) = (float) slot10(4, L). Recast 30. canUse (0x2faa00): a
player with no shield equipped (record +0x43fc, equipment slot 3) or with weapon class 4
(bow; record +0x4a86) is refused and shown a HUD message for 180 frames. Non-players pass.

**Cast** (0x2faa88): allocate 0x28; `SpellShieldBash_ctor(spell, L, caster, skill)`; return
the spell.

**Constructor** (0x2face4):

```
caster.actionState(+0x58c) = 6                  # "under control of a skill"
anm = the bash animation from the caster's class lump
start it: anim_startBlendInOut(blend in 0.1 s, blend out 0.1 s, flags 0x812)
anm.eventSlot[1] = { time 0.5940 s (0x3f181040), mask 2 }      # written into the shared animation data each cast
done(+0x18) = 0;  eventSeen(+0x1c) = 0;  (+0x20) = 0;  faceTarget(+0x24) = none
list = world_collectObjectsInArc(100.0, 90.0, 0, caster.pos, caster.facing, no filter)
if the list is not empty and any entry lacks flag 0x1000000:
    faceTarget = the object at the head of the list     # a raw pointer; nearest creature in the arc
```

(The loop that looks past a head entry with flag 0x1000000 stores the head's object again
rather than the entry it found — the load at 0x2fae58 is from the head node — so the result
is as written.) Draws: shared ×1.

**Run** (0x2fae80), each frame, driven from the caster's spell update:

```
ev = Player_animStep(1.0, player)               # 0x1b9520: the spell advances the player's animation
Player_move(player, mode 3, &g_pads[slot], 0)   # 0x1b4020
if faceTarget: player.slot26(0, faceTarget.pos) # turn toward it
if ev & 2: eventSeen = 1
if not done:
    if not eventSeen:
        wind-up particles (0x2fb49c: 203 × (1 draw, S) from the spell's generator)
    else:
        maxTargets = slot10(3, L);  stunChance = slot10(1, L);  stunFrames = slot10(2, L) * 60
        kb = L < 6 ? 0x40000 : (L > 15 ? 0x200000 : 0x80000)
        hand = model attachment point 1 of the player
        list = world_collectObjectsInArc(41.0, -1.0 (no arc), 0, hand, player.facing, no filter)
        hits = 0
        if maxTargets >= 1:
            for o in list, in list order, while hits < maxTargets:
                if o.flags lacks 0x1000000 and player.isEnemy(o):
                    getStatRange(0.2, stat 0, L, no randomising, &lo, &hi)      # slot 8, §0.2
                    damage(lo, hi, o, player, 100000, kb | 0x40, null, noCrit 1)
                    if o.hitPoints(+0x228) <= 0:  flash o
                    else:
                        d = shared draw
                        if stunChance < (d mod 100) + 1:  flash o             # no stun
                        else: o.slot30(stunFrames, 1)                         # Creature slot 30: stun
                    if this is the first hit: new LightEffect at o.pos + (0, 0, 64)   # shared ×1
                    hits += 1
        if hits == 0:
            o = first entry of world_collectInSphere(41.0, player.pos) that is neither creature
                nor player and lacks flag 0x1000000
            if o: getStatRange(...); damage(lo, hi, o, player, 100000, kb | 0x40, null, 1)    # breaks props
        done = 1
if the player's animation flags (+0x11a) lack bit 0x10, or player[+0x450] != 0:
    player.actionState = 2; delete self
else if net_isLocalSlot(slot): g_forceGhostRebase (0x402797) = 60
```

The blow lands on the frame the animation passes 0.594 s. `kb` is the knock-back class the
death code reads. A surviving target is stunned when `(d mod 100) + 1 <= stunChance`, i.e.
with probability stunChance %. A killed target costs no stun draw.
`Player_run` polls spell slot 4 (0x2fb67c, returns `done`) for ids 34 and 49.

**Draws, in order.** Cast: shared ×1. Wind-up frames: spell ×(203 × at least 4). Blow: per
target `damage_apply`'s shared draws (base roll, since lo < hi), then shared ×1 for the
stun unless the target died, and shared ×1 for the light on the first target. The spell's
generator feeds particles only.

**Presentation only.** Wind-up particles, flash (both quads set to 100, 100, 0x40, 0x40
with the last word of the second quad left alone), `LightEffect`.

**Per-machine state.**

- Reads `g_pads[slot]`, the lockstep pad array (shared).
- Writes `g_forceGhostRebase` when the caster's slot is local — per-machine by design
  (`docs/skills.md`, section (c)).
- The wind-up helper places particles on `net_objOrGhost(owner)`; its draw count is fixed.
- canUse raises a HUD message and is also called for the prediction copy.
- **Non-player caster:** the constructor writes +0x58c and the run function calls
  `Player_animStep`, `Player_move` and indexes `g_pads` and the player record by +0x3c8 —
  all beyond the end of a plain creature. Reaching this cast through a weapon effect on a
  monster would corrupt memory (`docs/skills.md` (a)); the run part would not execute
  because that route never attaches the spell.
- **Hazard:** `faceTarget` is a raw pointer dereferenced every frame of the bash.

**Functions read.** 0x2fa904, 0x2fa970, 0x2faa00, 0x2faa88, 0x2fab28, 0x2facb0, 0x2face4,
0x2fae80, 0x2fb49c, 0x2fb67c.

**Not determined.** `Player_move` in mode 3 and `Player_animStep` (player area); which
animation track flag 0x10 marks, beyond "the bash animation is still playing".

## A. Behaviour for the prediction copy and for non-player casters, in one place

- **Prediction copy (object flag 0x20000).** None of ids 1–34 has flag bit 0 in the Skill
  flag word, so `Player_castSkill` never calls their cast for the copy. `canUse` is called
  for the copy; the only canUse functions here with an effect are Root and Shield Bash
  (a HUD message). Spells are attached to the real player and `Creature_clone` starts the
  copy's spell list empty, so no run function here executes for the copy. Every damage call
  goes through `damage_apply`, which returns at once for an attacker that is the copy, and
  box queries never return the copy.
- **Non-player caster.** Differences are tier 2 statistics wherever a read is `slot11`,
  `slot12` or `slot13` (ids 2, 4, 5, 7, 9, 11, 12–14, 18, 23, 24, 26, 29; ids 1, 6, 8, 10,
  15, 16, 17, 20–22, 31–34 read tier 1 for everyone), the 40-frame delay and warning light of Fire
  Storm and Poison Rain, the weapon-holder calls of the weapon buffs, and the uncharmed,
  shared-name skeleton. Shield Bash is not safe for a non-player caster (section 34).
- **Weapon-effect route.** Any cast here can be invoked by an item entry of type 0x29 with
  the attacker as caster, the attacker's feet as position and its facing; a returned Spell
  is then never attached and never run. Whether any item carries such an entry for these
  ids needs the item tables (open question 1 of `docs/skills.md`).

## B. Hazards found (proposed ledger rows)

Not added to `FINDINGS.md`; offered for review. None was tested. No patch is proposed: each
would need the stale-pointer or stale-list condition reproduced first, and none is a
one-word change.

| Proposed id | Finding | Kind | Where |
|---|---|---|---|
| SA1 | `SpellBlindingLight` keeps its caster as a plain pointer and passes it to `damage_apply` as the attacker every 30 frames for up to s2 seconds. If the caster's object is destroyed meanwhile (a player object is rebuilt on respawn and on a level change) the pointer is stale; what `damage_apply` then reads depends on what the pool put there, and pool contents are not identical between machines (the prediction copy and gore-dependent objects are per-machine allocations) | Observed pointer; consequence Inferred | store 0x2f4474 (+0x1c), use 0x2f4538 |
| SA2 | `HolyBolt` (Dismiss Undead) keeps its homing target as a plain pointer and reads its position and flags every frame; it is cleared only when the target is flagged dead, not when the object is deleted | Observed; consequence Inferred | constructor 0x2f5248 (+0x64), run 0x2f57b0 |
| SA3 | `SpellShieldBash` keeps the creature it turns the player toward as a plain pointer for the length of the bash (about a second) | Observed; consequence Inferred | constructor 0x2face4 (+0x24), run 0x2fae80 |
| SA4 | The elemental entries of `damage_apply` take `draw rem (v2 − v1 + 1)` with a signed machine divide and no zero test. Cone of Fire passes v2 < v1 always, and v2 = v1 − 1 (divisor 0) when its statistic 0 is 4–7, which a monster caster gets at levels 2 and 3. The result of a divide by zero is processor-defined; a rebuild or another emulator that differs from the console here computes a different damage | Observed arithmetic; console result Inferred | 0x1e990c (`div`), caller 0x2f02fc |
| SA5 | The Critical Hit aura walks the all-players alive list, so it inherits G11/G13: on a frame where one machine's list lacks its own player, the aura owner is skipped there, the chance differs, and the shared critical-hit draw is made on one machine and not the other | Inferred from G11 | `SkillCriticalHit_critBonusFor` 0x2e76c4 |

Two smaller facts for the same readers: Blinding Light calls `gfx_setColorOffset` from
simulation code, so every machine's screen flashes for any caster (output only, 0x2f47dc);
and Hammer of Wrath's particle count comes from the per-machine fourth generator
(0x404468), which feeds nothing else.

## C. Corrections and additions to earlier documents

| Document | Says | Found | Evidence |
|---|---|---|---|
| `docs/skills.md`, slot 9 | the base `initStats` "zeroes tier 1" | it writes first level 0, base 1, step 2.0 for all five tier-1 statistics | 0x3c85b0 |
| `docs/skills.md`, Spell layout | +0x08 is "the skill that made it" for every spell | `SpellDiseaseEffect` and `SpellSecondaryUndeadShield` leave +0x08 null; the former keeps its Skill at +0x1ac | 0x2d5594, 0x2eb050 |
| `docs/skills.md`, id table, 21 | cast creates "Projectile@0x50e7e8 (0xb0)" | that class is `LostSoul`, several purely visual objects; the effect is the `damage_radial` call | 0x2f4d34 |
| `docs/skills.md`, id table, 17 | — | every statistic of the hammer is read at level + 1, and its constructor makes an extra shared draw for the item variant | 0x2edefc, 0x1046e0 |
| `docs/skills.md`, statistics note | DiseaseBolt s0 damage "Inferred" | Observed; and the 0x26 entry's values are not a damage — the disease it starts ticks for 1 unless Bubo started it | 0x2caec8, 0x2d5854 |
| `docs/gameplay.md` §2.2 | elemental entries have "min, max" | the amount is `v1 + draw rem (v2 − v1 + 1)` in integers, which matters because two skills pass v2 < v1 | 0x1e98c8–0x1e9914 |
| `docs/creatures.md`, attached-spell list | "caster at +0x18, skill id at +0x1c" | fields from +0x18 on are per class; the base has the Skill pointer at +0x08 and the owner at +0x0c | every constructor here |
| `docs/player.md`, cast step 8 | cost / 60 "per frame while held" in the helper | the helper charges cost / 60 once; the per-frame charge is in `Player_run` cast phase 2 and keys on the ability record's kind byte | 0x1a42b8 tail; `Player_run` state 5 |

## D. What is specified, and what is left

"Full" means every function that can change game state for that id was read and is written
out above; what remains unknown lies in a callee owned by another area.

| Id | Name | State | Left open |
|---|---|---|---|
| 1 | wizardbeam | full | trail helpers (presentation); the library `powf` taken as standard |
| 2 | dodge | full for the skill | the rest of `MissileWeapon_onTouch` 0x152a18 around the dodge block |
| 3 | resistpoison | full (unused) | — |
| 4 | diseasebolt | full | — |
| 5 | diseaseshield | full | `DiseaseCorpse` 0x2ce3f8 / 0x2ce4a4 and `DiseaseCloud` 0x2ce610 / 0x2ce6e0 (monster-only objects in the same file) not reached; describeRank not read |
| 6 | diseasetrail | full | — |
| 7 | firestorm | full | argument order of the second constructor 0x2d4048 only as far as the stored fields |
| 8 | fireflares | full | run order of flare objects against the caster's spell update |
| 9 | riposte | full | — |
| 10 | blessed | full | — |
| 11 | summonskeleton | partly | the cast is complete; the draws inside `Creature_ctor` / `Creature_setStats` / `Creature_init`, the `Skelight` class and the property lists were not read |
| 12 | lightningweapons | full | weapon-holder slot bodies (creatures area) |
| 13 | fireweapons | full, by comparison with 12 | same; describeRank not read |
| 14 | coldweapons | full, by comparison with 12 | same |
| 15 | undeadshield | full | player run order (gap in the secondary shield) |
| 16 | holystrike | full | handle-list behaviour when a listed target is deleted |
| 17 | hammerofwrath | full for game state | orientation springs only outlined; terrain-ray return convention |
| 18 | coneoffire | full | console result of the zero divisor |
| 19 | regeneration | full | — |
| 20 | blindinglight | full | — |
| 21 | repulseundead | full | — |
| 22 | dismissundead | full | — |
| 23 | shockoffrost | full | bodies of the debris prop constructors (`PhProp_ctor` 0x155a0c, `PhProp_initPhysics` 0x155110) checked only for shared-generator use |
| 24 | poisonrain | full | describeRank not read |
| 25 | diseaseweapons | table only (there is nothing else) | weapon-holder slot that consumes it |
| 26 | poisonweapons | full, by comparison with 12 | describeRank not read |
| 27 | hatebeam | table only | `HateBeam` class 0x277468 / 0x2775e8 (monsters) not reached |
| 28 | hatebeam (`SkillBallOfHate`) | table only | `HateProjectile` class 0x278158 / 0x2783e8 not reached |
| 29 | diseaseeffect | full for `SpellDiseaseEffect` | `SpellHornOmenEffect` 0x2fc574 / 0x2fc684 and `SpellPlanarSteelEffect` 0x2fb728 / 0x2fb9b4, which also use this table, not reached |
| 30 | hateeffect | table only | `SpellHateEffect` 0x27930c / 0x279420 not reached |
| 31, 32 | clericroot, rangerroot | full | — |
| 33 | rangercriticalhit | full | — |
| 34 | shieldbash | partly | spell complete; `Player_move` mode 3 and `Player_animStep` not read, so the caster's motion during the bash is not specified |

Not read anywhere in this pass: the draw functions (slot 5) of the objects above, the
static initialisers that register particle definitions, the sound and trail helpers, and
the take-damage implementations that `damage_radial` and `damage_apply` end in.

Things a running game would settle quickly: the dodge percentage at level 1 (18 % or
another value, section 2); Cone of Fire's damage per tick (95–165 at level 1 against an
unresisting target, section 18); the Hammer of Wrath duration being that of the next level
(section 17); the aura of the weapon buffs lapsing on alternate ticks once s3 reaches 31
(section 12).
