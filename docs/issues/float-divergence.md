# Floating point and lockstep: how exposed is the simulation?

The game's network play is deterministic lockstep, so every machine has to compute the same
bits. The PS2's floating-point unit is not IEEE 754, and today the game is played on
emulators that approximate it with selectable modes. This document asks two questions: where
does simulation code perform an operation whose result depends on the non-IEEE behaviour, and
can any of that explain the Drundar arena (`DRUNARE`) going out of sync.

Everything about the game was read from the executable; nothing was run. Since then the
game has been run in the Play! emulator (`docs/issues/live-rig.md`; `FINDINGS.md`, "Run on
the live game", rows V1–V13) — a third arithmetic implementation, neither a PlayStation 2
nor PCSX2. Its movement distances agree with the documented constants to seven digits,
which says nothing about the last-bit questions of this document: how faithful Play! is to
the console in floating point was not checked, and no two machines or settings have been
compared. Claims are
**Observed** (read at the address given), **Inferred** or **Unknown**. Everything about how
PCSX2 behaves is from general knowledge of that project, **not** from reading its source or
running it here, and is marked as such. The patches at the end are **untested**.

The scan is `tools/fp_hazards.py`; names added are in `symbols/fp.tsv` (the other math
library names used below are in `symbols/movement.tsv`).

## Result in short

| Question | Answer | Kind |
|---|---|---|
| Is there a divide, root or conversion in the arena fight whose *special-case* result (divide by zero, root of a negative, out-of-range conversion, overflow) reaches shared state? | No. Three places really do divide by zero during the fight; one result is thrown away, the others go to a light record. A fourth group needs a status effect nobody has shown to be reachable | Observed per site; completeness Inferred |
| Is the simulation exposed to *ordinary* rounding? | Completely. About 26,000 add, subtract and multiply instructions and 368 divides have no protection, and four of the quickest routes from a last-bit difference to shared state are the stick decoder, the cast origin (which goes through a VU0 microprogram), the monsters' turn damping and Tagar's Insects' arrival test | Observed (the code); Inferred (the consequence) |
| Can floats explain "the arena, every time, for one pair of players"? | Only if the two machines do not compute identically at all (a console against an emulator, two emulator builds, or different rounding or clamping settings). Then the game would normally drift in every level, and the arena, being long and full of seed draws gated by float compares, is where it would show. Two PCSX2 copies of the same version with the same settings on x86 hosts should agree on every site found | Inferred; the PCSX2 part is general knowledge |
| Is the sync hash's float-to-integer conversion well defined? | Yes: `cvt.w.s`, which always truncates on this CPU. It also makes the hash blind to anything smaller than one world unit | Observed (instruction); Inferred (emulator) |

## The machine, as far as this executable uses it

**Observed** by scanning every word of `.text`.

- Only single precision is used on the FPU. There is no double-format instruction;
  `double` arithmetic is done by integer library routines (for example the "random amount
  between minimum and maximum" roll in `damage_apply` goes through `libm_fmod`, 0x3a5a38),
  so it cannot differ between machines. That holds between machines running the original
  code, and only between those: the library routines truncate instead of rounding and
  have no denormals (executed in `docs/spec/core.md` section 9), so a rebuild or port that
  uses the host's `double` gets a different float in about half of all results. Game
  code uses these routines for every `float × literal` written without an `f` suffix.
- The compare instructions are the R5900's three: equal (264 sites), less than (1,994) and
  less or equal (483). There are no unordered compares.
- The only float-to-integer instruction is `cvt.w.s` (1,462 sites). There is no separate
  round, floor or ceil instruction; `libm_floorf` 0x3a57e8 and `libm_ceilf` 0x3a5710 are
  integer bit code.
- The control register is written once, with zero, by the start-up code (0x14fb98) and is
  never read: there is no `cfc1` anywhere. The sticky invalid / divide flags therefore
  cannot influence anything. (By the published descriptions the R5900 has no rounding-mode
  field to set in the first place.)
- No multiply-add instruction is used (one `adda.s` in the start-up code, 0x14fb90).
  `max.s` (59) and `min.s` (121) are used.
- 47 `sqrt.s` and 42 `rsqrt.s` sites use a register other than `$f0` as the operand. A
  generic MIPS disassembler prints those words, and all `max.s` / `min.s`, as unknown;
  `disasm/text.asm` has them as `<unknown>`. `tools/fp_hazards.py` decodes them from the
  executable.
- Decimal constants were truncated, not rounded, when the game was compiled: 0.2 is stored
  as 0x3e4ccccc, 0.05 as 0x3d4ccccc, 1/60 as 0x3c888888. The same is true inside the math
  library (ln 2 is 0x3f317217).
- Outside the SDK, coprocessor 2 (the VU0 vector unit) is used in exactly one function:
  `anim_buildPose` 0x16ed40 starts a VU0 microprogram at two places (0x16f594, and
  0x16f5f4 for each joint) and reads three result registers back (0x16f654–0x16f66c). See
  "The pose goes through VU0" below.

Hardware behaviour assumed throughout (from the project background and published
descriptions of the R5900, not measured here): no NaN or infinity, a result too large
becomes the largest magnitude with the right sign, denormals are zero, a divide by zero
gives the signed maximum, `sqrt.s` of a negative number is the root of its magnitude,
`cvt.w.s` truncates and saturates, and add, subtract and multiply round toward zero with
small differences from IEEE truncation.

## What the scan counts

`python3 -I -B tools/fp_hazards.py --ops` (whole executable):

| Area | div.s | not closed | rsqrt.s | sqrt.s | not plainly ≥ 0 | cvt.w.s | add | sub | mul |
|---|---|---|---|---|---|---|---|---|---|
| startup | 3 | 2 | 0 | 0 | 0 | 26 | 123 | 30 | 182 |
| creatures | 7 | 5 | 3 | 22 | 0 | 64 | 289 | 257 | 461 |
| netcode | 1 | 1 | 0 | 1 | 0 | 5 | 6 | 10 | 7 |
| script | 0 | 0 | 0 | 2 | 0 | 11 | 15 | 8 | 24 |
| objects | 19 | 17 | 9 | 10 | 0 | 103 | 340 | 197 | 530 |
| engine | 99 | 75 | 9 | 17 | 4 | 252 | 1,094 | 717 | 2,134 |
| player | 16 | 16 | 2 | 9 | 0 | 56 | 275 | 180 | 403 |
| ui | 15 | 8 | 4 | 2 | 1 | 112 | 161 | 77 | 202 |
| gameplay | 86 | 66 | 31 | 32 | 1 | 131 | 1,325 | 725 | 2,201 |
| audio-save | 10 | 10 | 9 | 5 | 0 | 126 | 141 | 120 | 255 |
| monsters | 27 | 25 | 40 | 49 | 1 | 241 | 1,977 | 936 | 2,788 |
| skills | 52 | 46 | 21 | 23 | 2 | 303 | 2,522 | 1,165 | 3,423 |
| mainloop | 0 | 0 | 0 | 0 | 0 | 0 | 6 | 4 | 5 |
| netlib | 33 | 31 | 0 | 0 | 0 | 24 | 149 | 120 | 187 |
| runtime | 0 | 0 | 0 | 0 | 0 | 8 | 24 | 17 | 36 |
| **all** | **368** | **302** | **128** | **172** | **9** | **1,462** | **8,447** | **4,563** | **12,838** |

How to read it:

- "Not closed" means the scan found no non-zero constant divisor, no compare-and-branch on
  the divisor and no clamp within a short window. It is a list of sites to read, not a list
  of bugs: of the divides read by hand for this document, most "not closed" ones turned out
  to be guarded further away than the scan looks.
- Of the 66 divides the scan does close, 46 follow a compare against a bound, 19 a compare
  against zero and 1 has a constant divisor. **12 divide by a constant 0.0** (ten of them
  visibly 1.0 / 0.0); all are constructors that set up a light record, like the FireStorm
  one below.
- None of the 128 `rsqrt.s` sites has a zero test in front of it that the scan can see. 117
  take the reciprocal root of a plain sum of squares, i.e. normalise a vector. They are the
  largest family of real divide-by-zero sites: a zero-length vector gives the maximum, and
  the following multiplications by the zero components give zero again.
- 155 of the 172 `sqrt.s` operands are plainly a sum of squares or an absolute value, 7 are
  constants, 1 is guarded. The 9 others are listed by
  `fp_hazards.py --list --kind sqrt --open`; one is on the arena path (`damage_apply`).
- "Overflow chains" cannot be found by pattern. What the scan reports instead is the usual
  seed of one, a constant of magnitude 1e18 or more put in a register: 15 sites, 12 of them
  in the C library (ten uses of `1e30`, two of ±2^63), the other three at 0x149ae4 (lighting
  code), 0x194c38 and 0x194c60 (an unnamed engine function), none of those three followed
  by arithmetic within the scan's window. Constants loaded from memory are not covered.
- 42 compares are reached, in the scan's forward look, from a divide or root it could not
  close. Those are the compares that would see a NaN on a strictly IEEE machine.

For the arena, `--reach` was run from `Horsemen_run`, `Horsemen_setState`, the `Skelight`
constructor / run / set-state, `Cazic_run`, `Cazic_setState`, the FireStorm, FireStormFlare,
DiseaseBolt, Tagar's Insects and Summon Skeleton functions, `damage_apply`, `Player_run`,
`Player_move`, `obj_moveWithCollision`, `obj_moveAndCollide`, `terrain_height` and the
three trigonometry helpers. That selects 919 functions through direct calls (virtual calls
are not followed): 94 divides (72 not closed), 25 `rsqrt.s`, 50 `sqrt.s` (4 not plainly
non-negative), 255 conversions, and about 6,000 add / subtract / multiply instructions.
`Horsemen_run`, `Skelight_run`, `DiseaseBolt_run` and `FireStormFlare_run` contain no
divide, root or conversion of their own; theirs are all in the shared creature, movement
and terrain helpers.

## The arena code, site by site

Each row was read in the disassembly. "Max" means the signed largest value the console
produces for a divide by zero.

### Sites where the hazardous input does occur

| Address | Where | What happens | What the result reaches | Kind |
|---|---|---|---|---|
| 0x2d429c (also 0x2d40e8) | `FireStorm_ctor`, `FireStorm_ctor2` | 1.0 is divided by a constant 0.0 every time the object is constructed | the two inverse-square-radius fields of the light record embedded at object +0x50 (+0x70, +0x78) | Observed |
| 0x2d4854 (0x2d48a8 in the fade-out branch) | `FireStorm_run` | the light radius is `2 × grown radius (+0xa0) + flicker × (grown / full)`; +0xa0 starts at 0 (`FireStorm_initCommon`) and only starts growing 30 frames after the storm begins, so for those 30 frames the code computes 1.0 / (0 × 0). The fade-out branch does the same only if the storm is still at radius 0 in its last second | the same two light fields; the radius itself (0) goes to +0x6c, +0x74 | Observed |
| 0x30cee8 | `SpellTagarsInsects_run` | speed = distance to the victim / (arrival time − now). The arrival time is the smallest "now + distance / 203" seen so far, so the divisor reaches zero, or goes negative, on the frame the swarm arrives; with the swarm exactly on the victim it is 0 / 0 | **nothing**: on that frame the "arrival ≤ now + 1/30" test (0x30cf40) is true and the speed register is reloaded with the constant 203.05 (0x30d050) before its first use (0x30d130). The quotient is only used on frames where that test fails, which puts the divisor above about 1/30 | Observed |

The light record: `docs/objects.md` classes the lighting code (0x147a84–0x14a480) as
drawing only. The readers of the two inverse fields were not enumerated for this document,
so "cosmetic" is **Inferred**. The damage the storm does every 30 frames uses the integer
radius at +0x9c in a box query, not the light.

The second divide in the insects' update (0x30cf20, the height step) is guarded by
"remaining time > 1/60". `SpellTagarsInsects_tickVictims` 0x30d558 has no divide at all; its
two conversions are damage ± 20 %.

### Sites that need a state not shown to be reachable

| Address | Where | Condition | What it reaches | Kind |
|---|---|---|---|---|
| 0x1a81f4 | `Player_run`, cast state | cast speed is multiplied by (60 − slow) / 60 when the slow byte (+0x2fc) is 1…60 (0x1a81a0–0x1a81d8); at slow = 60 the "release frame / speed" divide is n / 0 | converted to an integer (0x1a81f8) and compared for equality with "frames in this state" to decide when `Player_castSkill` runs (0x1a8354, 0x1a898c). The console gives the largest integer, i.e. never | Observed |
| 0x1aa1e0, 0x1aa224, 0x1aa754, 0x1aac70, 0x1aaf94, 0x1aafac, 0x1aafe0 | `Player_run`, melee state | the swing-speed factor gets the same (60 − slow) / 60 scale (0x1aa178–0x1aa1b4) and seven frame constants are divided by it | frame thresholds compared with "frames in this state"; with a zero factor every threshold is the maximum, so the swing does not advance | Observed (divides); Inferred (all seven used that way; three were followed) |

The slow byte is written only by `Creature_run`. From effect timer 1 (+0x344, fed by
`damage_apply`) it is capped at 30 (15 for a monster under one condition); the only route to 60 is status counter 7 (+0x388), which
ramps the byte by 2 per frame and holds it at 60 from the thirtieth frame on unless a
resistance lowers it (0x113738–0x1137d8). That is the counter of ledger rows D14–D16:
whether anything in this game sets it is **Unknown**. If it is reachable, these eight sites
divide by zero for as long as the player is fully slowed. The outcome is "never" on the
console and, as far as general knowledge of the emulator goes, also there, so it would be a
hazard without a divergence.

### Sites in arena code where the hazardous input cannot occur, or cannot matter

| Address | Where | Operation | Why it is safe | Kind |
|---|---|---|---|---|
| 0x1141e0 | `Creature_moveBy` | push-out factor (sum of radii − distance) / distance | tested: \|distance\| > a small constant just before (0x1141ac–0x1141b4) | Observed |
| 0x14d8b4 | `obj_moveWithCollision` | the same computation | tested the same way | Observed |
| 0x185b84 | `terrain_sweepCircle` | 1.0 / horizontal length of the move, **not tested here** | `Creature_moveBy` (0x113f84 on), `Prop_run` and `PhProp_run` (the blood chunk's class) only call with horizontal length² > 0.001. `obj_moveWithCollision` tests the three-dimensional length² instead (0x14d554–0x14d56c), so a purely vertical move would get through; `Player_move`, its caller in this fight, passes a vertical part that is 0 × something, and `Container_run`, `AutoContainer_run` and `RedDragon_run` pass zero | Observed (tests); Inferred (no vertical-only caller: `SpellShadowStep_run`, and `PushPhysicsProp_run` which calls the sweep directly, were not traced) |
| 0x1858d8 | unnamed walk test 0x1857e4 (no direct caller) | 1.0 / distance between two points, not tested | the function returns before using the quotient when the distance is 12 or less | Observed |
| 0x185f68 | `terrain_sweepCircle` | root of radius² − offset² | tested > 0 first | Observed |
| 0x186118 | `terrain_sweepCircle` | normalise contact point − terrain sample | zero only if the circle centre sits exactly on the sample, which needs radius 0; even then the components are 0 × max = 0 | Inferred |
| 0x18a6cc, 0x18a9c4–0x18ab64 | `terrain_raycast` | divides by the ray's horizontal length and by direction components | each follows a compare of the divisor with a bound; a vertical ray takes a separate branch | Observed |
| 0x18ae9c, 0x18b09c | `world_raycast` | 1 / length; root of radius² − perpendicular² | length < 0.01 returns first; the root is taken only when \|perpendicular\| ≤ radius | Observed |
| 0x1e8b60, 0x1e8b6c | `damage_apply` | hit chance = root of (attack rating / defence) | the defence is an integer tested ≥ 1; the root is of a negative number only if a caller passes a negative attack rating. The callers resolved pass 100000, 10000, 3000 or a creature statistic | Observed (test); Inferred (ratings ≥ 0) |
| 0x1e8d04 | `damage_apply` | attack rating / (defence × 0.5) | same integer test | Observed |
| 0x1e931c, 0x1e9b08 | `damage_apply` | damage × 60 / victim's hit points, added to effect timer 1 (+0x344), which `Creature_run` turns into the slow byte | hit points are compared with 0.0 first and the quotient replaced by 60 | Observed |
| 0x111e9c | `Creature_processDamage` | experience base / sum of a per-player record byte, then `libm_powf(…, 1.4)` | zero only if that sum over all players is zero | Observed; that the byte (the level, by its use) is ≥ 1 is Inferred |
| 0x11aab4 | `creature_leadPoint` | distance / projectile speed | `Cazic_run` passes 350.0 at both calls (0x24b5fc, 0x24b900); the arena variant of Cazic casts nothing anyway | Observed |
| 0x16cf60, 0x16cfa0, 0x16d098 | `anim_startBlendInOut`, `anim_start` | 1 / (blend seconds × 60) | each blend time is compared with 1/60 first and the rate set to 1.0 instead | Observed |
| 0x16f630 | `anim_buildPose` | normalise the blended quaternion | not tested; a zero quaternion would give zero components again | Observed; that it cannot be zero is not established |
| 0x1a5538 | `Player_run` | player record hit points (+0xac) / maximum (+0xb0), compared with 0.4 | maximum hit points of zero would be needed | Observed (fields per docs/player.md); what the branch then does was not read |
| 0x1a8324 | `Player_run` | distance / arrow speed | the speed is the constant 748 or 350 | Observed |
| 0x1a8e20 | `Player_run` | normalise the aim vector | zero only if the target is exactly at the origin point; components would be zero | Inferred |
| 0x2d4818 | `FireStorm_run` | grown radius / (float) integer radius | the integer radius is a skill statistic × 12; result goes to the light radius | Observed (use); statistic ≥ 1 Inferred |
| 0x2d4b84 | `FireStorm_run` | normalise the flare's direction (terrain point − spawn point) | the spawn point is 240 above the storm and the target is on the terrain | Inferred |
| 0x30d31c | `SpellTagarsInsects_run` | normalise a random vector from the spell's own generator | zero needs three draws of exactly 0x8000; result goes to particles only | Observed |
| 0x201dec | `LightEffect_ctor` | 1 / fade duration in frames | the frame count is clamped to at least 1 as an integer | Observed |
| 0x104800, 0x104d54 | item generation | divide by the number of players | at least one player | Inferred |
| 0x166630, 0x1666e0 | `math_cos16`, `math_sin16` | — | integer range reduction, then ten multiplies and five adds or subtracts on an argument below 0.79. No divide, root or conversion | Observed |
| 0x166798 | `math_atan2_16` | `libm_atan2f`, × 10430.38, `cvt.w.s`, sign-extend 16 bits | the product is within ±32768; the library settles zero arguments with integer tests before its one divide (0x3a7440) | Observed |
| 0x183820 and its siblings | `terrain_height`, `terrain_heightBelow`, `terrain_heightAtPoint`, `terrain_collectElements` | `libm_floorf` / `libm_ceilf` of position / 4, then `cvt.w.s` to a sample index | positions are bounded by the 120 × 256-unit world; no divide or root | Observed |
| terrain queries and pathfinder, 0x182c98–0x185a40 | | — | the walk test above is the only divide or root in the whole range | Observed |

Conversions: the 255 `cvt.w.s` sites in this set convert positions scaled to grid indices,
angles, damage amounts, statistics and frame counts. None was found whose operand can leave
the 32-bit range except behind one of the divides above (0x1a81f8, 0x1aa228, 0x1aa758).
They were sampled by function, not read one by one.

## Where ordinary rounding reaches shared state fastest

None of these is a hazard in the sense above. They are the places where a difference in
the last bit of an ordinary result turns into different game state with the least delay,
which is what matters when two machines do not compute identically.

### The stick decoder (`netcodec_decodeAxis` 0x13c970)

**Observed** at 0x13cc6c–0x13cddc. Every machine, including the one holding the pad, gets a
player's stick through this decoder. Per axis it keeps two floats, value and velocity, and
runs ten sub-steps per frame:

```
damp  = 1.0 - sqrt(0x3e4ccccc)        ; computed at run time, 0x13cd24 and 0x13cd64
repeat 10 times:
    value    = value + velocity
    velocity = (velocity + (target - value) * 0x3d4ccccc) * damp
stick = truncate(value)               ; cvt.w.s at 0x13cddc
```

So a player's stick byte is the truncation of a float that hovers just below an integer.
A model of this loop in exact arithmetic (my own script; IEEE single precision, not the
console's multiplier) gives:

- with every operation truncated, a held target of 100, 200 or 255 settles at 99, 199, 254;
- truncating versus rounding to nearest in the add / subtract / multiply steps changes the
  decoded byte on about 12 % of the frames of a random stick trace (1,008 of 8,136), the
  first time on frame 27;
- how the square root is rounded does not matter here: both candidate roots (see below)
  give the same `damp`, 0x3f0d8369, once the subtraction is truncated.

**Inferred:** two machines whose add or multiply rounding differs disagree about player
input almost at once, in any level. `docs/netcode.md` says of this decoder that "all
machines agree"; that holds only between machines with identical float arithmetic.

### The pose goes through VU0, and the cast origin comes from the pose

**Observed.** `anim_buildPose` hands each joint's quaternion to a 77-instruction VU0
microprogram (`g_vu0PoseProgram`, loaded from 0x3e5c40): it builds the rotation matrix
with vector add, subtract and multiply, concatenates it with the parent's with
multiply-accumulate, scales the translation by 4.0 and converts to fixed point (12 and 4
fraction bits). It has no divide or root. The results are read back with the interlocked
move at 0x16f654.

`model_getAttachPoint` 0x1754a0 and `model_getSamplePoint` 0x178e18 read that pose, and
simulation code uses them: `Player_castSkill` 0x1a42b8 asks for attach points 0 and 1 and
gives their midpoint to the skill's cast function as the position, so a spell or
projectile a player casts is created at a point derived from the VU0 result. `Cazic_run`
and `Creature_processDamage` also call `model_getAttachPoint`; `Horsemen_run` does not.

**Inferred:** the vector unit's arithmetic is part of the lockstep, not only the FPU's. On
an emulator the VU0 rounding and clamping settings matter as much as the EE ones.

### One square root whose last bit depends on the rounding rule

**Observed.** Four functions take the square root of the constant 0x3e4ccccc (0.2,
truncated) at run time: `Creature_turnToward` 0x10bbc8, its two siblings 0x10bcc4 and
0x10bdcc, and the stick decoder 0x13cd24. The exact root lies between two floats: rounded
toward zero it is 0x3ee4f92d, rounded to nearest 0x3ee4f92e. (Three other constant roots,
0x113b18, 0x2c323c and 0x30b14c, round the same both ways.)

In `Creature_turnToward` the root is the damping of the turn:

```
velocity = velocity + truncate((wanted - facing) * 0x3d4ccccc)
velocity = velocity - truncate(velocity * root)
clamp velocity to ± turn rate;  facing = facing + velocity
```

Enumerating all 65,536 velocities (my own script, IEEE single multiply, truncated): the two
roots give a different result for 34 of them, the smallest ±2889 (16° per frame), then
multiples of 2889 and a second family starting at 18016. **Inferred:** a machine that
rounds this root the other way disagrees about a monster's facing only when a fast
about-face lands on one of those values, which is rare; it is listed because it is a single
instruction whose result can be read on a console and on an emulator to learn how each
rounds `sqrt.s`.

### Tagar's Insects turns a position difference into a seed-draw difference

**Observed.** The frame on which the swarm arrives is decided by a float compare (0x30cf40)
on values built from the swarm's and the victim's positions. On that frame, and only then,
the spell draws from `g_randSeed` (the tag object's seed, in the block after 0x30cf48) and
calls a skill statistic. **Inferred:** if two machines differ in the last bits of a player
position, the arrival can fall on different frames, and the seed, which is in the hash,
then differs at once. Every float compare that gates a shared draw does this (the hit
chance in `damage_apply`, 0x1e8c04, is another); the insects are the arena's own example
because knight variant 2 casts them during the knight fight.

## The sync hash

**Observed** at 0x13af58–0x13b00c: hash = `g_syncAcc` (always 0) + `g_randSeed` + for each
player the integers made from x (+0x10), y (+0x14) and height (+0x18) by `cvt.w.s` at
0x13afe0, 0x13afec and 0x13aff8.

- On the R5900 this instruction always truncates toward zero and saturates; there is no
  mode that could change it and the control register is never touched. Its rounding is
  well defined. Player coordinates are a few tens of thousands at most, far inside the
  range.
- **Inferred (general knowledge):** emulators implement it with a truncating conversion
  that does not depend on the selected rounding mode, so the conversion itself cannot make
  two emulator copies disagree.
- Consequence: the hash sees a float difference only when it moves a player across a whole
  unit or changes the number of shared seed draws. Monster positions, hit points, facing
  and timers are not in it. A float divergence is therefore reported late, and the frame
  of the message says little about where it began.

## What an emulator does with this

### Observed on this machine (nothing was launched)

- `/Applications/PCSX2.app` is version 2.8.2 and its executable is x86-64 only, on an
  arm64 host: here it runs under Apple's translator, not as native ARM code.
- `GameIndex.yaml` has an entry for SLUS-20973 with graphics fixes and memory-card filters
  only: no `roundModes`, `clampModes` or `gameFixes`. The per-game settings file present
  for this game sets networking and patches only. So the emulator's defaults apply.
- The bundled `docs/GameIndex.pdf` gives the numbering: rounding 0 nearest, 1 negative,
  2 positive, 3 chop; `eeClampMode` 0 none, 1 normal (results only), 2 extra + preserve
  sign (operands as well), 3 full; a separate `eeDivRoundMode`; separate VU0 / VU1 rounding
  and clamping; and two fixes that change arithmetic, `FpuMulHack` and `VuAddSubHack`, each
  described there as meant for a few named games.
- In the database `eeClampMode` appears as 0, 2 and 3 but never 1, and `eeDivRoundMode` as
  1 and 3 but never 0, which fits the defaults being 1 (normal) and 0 (nearest).

### From general knowledge of PCSX2 (not verified here)

- Defaults: EE rounding chop, EE division rounding nearest, EE clamping normal; VU rounding
  chop, VU clamping normal. The host's denormals-are-zero and flush-to-zero flags are set.
- The recompiler special-cases a zero divisor in `div.s` and `rsqrt.s` and makes the
  operand of `sqrt.s` positive in every clamping mode, and repairs the sign of a saturated
  `cvt.w.s`. "Normal" additionally turns an infinite or NaN *result* into the largest IEEE
  float; "extra" also clamps operands; "none" does neither; "full" is a different, slower
  code path that keeps the console's wider exponent range.
- "Full" is closer to the console but not exact: multiplication can still be one unit in
  the last place off, and divide and square root round differently.
- The largest value differs: the console (and "full") use the bit pattern 0x7fffffff, the
  other modes the largest IEEE float 0x7f7fffff.
- With chop rounding an IEEE add or multiply that overflows returns the largest finite
  float, not infinity, so under the default rounding "none" and "normal" can differ only
  after a *division* overflows or a value with all exponent bits set is loaded from memory.

### What that means for the hazards found

| Hazard (sites) | (a) console | (b) PCSX2 defaults | (c) clamping none | (c) clamping full | Does the difference reach shared state? |
|---|---|---|---|---|---|
| Divide by zero into a light (0x2d429c, 0x2d40e8, 0x2d4854, 0x2d48a8) | +max 0x7fffffff | +0x7f7fffff | as (b) | as (a) | No (light record), Inferred |
| Divide by zero, result discarded (0x30cee8) | max | max | max | max | No, Observed |
| n / 0 then conversion (0x1a81f4 and the melee group), needs slow = 60 | largest integer | largest integer | the same | the same | Same outcome everywhere; if an emulator did not repair the conversion it would give the most negative integer, which is also "never" for these compares |
| Normalising a zero vector (`rsqrt.s` sites) | components 0 × max = 0 | 0 | 0 | 0 | No. A strictly IEEE machine would get NaN; none of (a)–(c) is that, if the zero-divisor special case is as described |
| Root of a negative number | not found on the arena path | | | | — |
| Overflow of add / multiply | no seed for one found in game code | | | | — |
| Every ordinary add, subtract, multiply | truncation with the console's quirks | IEEE truncation | as (b) | adds the console's guard-bit behaviour; **Unknown** whether (b) has it too | **Yes**, everywhere |
| Every ordinary divide and root (368 + 172 sites) | console rounding | IEEE, in the division rounding mode | as (b) | **Unknown** whether identical to (b) | **Yes**, everywhere |
| The pose (VU0 microprogram) | console VU arithmetic | IEEE truncation; add / subtract differ from the console unless `VuAddSubHack` is on | n/a (VU has its own clamping setting) | n/a | **Yes**: cast origin |

Reading the table:

- **(b) against (b)**, same version, same settings, x86 hosts: scalar and packed IEEE
  operations give the same bits on every x86 processor, so every site in this document
  agrees. **Inferred.** Floats do not explain a desync between two such machines.
- **(a) against (b) or (c):** not one of the special cases above matters, but the ordinary
  rounding of every result does. A console and an emulator should be expected to drift
  apart in any level; how quickly is **Unknown** and can only be measured.
- **(b) against (c):** by the description above, "none" and "extra" give the same bits as
  "normal" at every site read here as long as both use chop rounding, because nothing on
  these paths overflows a division or loads an out-of-range bit pattern. "Full" must be
  assumed different. **Inferred.**
- **Different rounding settings:** immediate, through the stick decoder.
- **x86 against ARM:** this installation is x86-64 code under translation; the basic
  operations should translate exactly, the corner cases where translators differ (NaN
  propagation, denormals) are not produced on the paths read. **Unknown** until two such
  machines are compared. A natively compiled ARM emulator has its own code generator and
  nothing here says how it treats zero divisors, saturation or clamping.
- The interpreter and the recompiler of the same build are not known to agree bit for
  bit. **Unknown.**

## Conclusions

### Sites that can really diverge

Between machines that compute identically: **none found.**

Between machines that do not:

| Address | Condition | What it reaches |
|---|---|---|
| 0x13cdb0–0x13cddc `netcodec_decodeAxis` | add / subtract / multiply rounded differently | every player's stick byte, hence all player movement; within a second of stick use in the model of nearest against chop |
| 0x1a42b8 `Player_castSkill` via 0x16f594 / 0x16f5f4 | VU0 results differ in the bits kept by the fixed-point conversion | the position a cast spell or projectile is created at |
| 0x10bbc8, 0x10bcc4, 0x10bdcc | `sqrt.s` of 0x3e4ccccc rounded up on one machine and down on the other, and an angular velocity among 34 values | a creature's facing |
| any of the 368 `div.s` | division rounding differs and the quotient is inexact | for example animation blend rates (0x16cf60, 0x16d098), the slow build-up in `damage_apply` (0x1e931c), the insects' speed (0x30cee8) |
| 0x30cf40 `SpellTagarsInsects_run`, 0x1e8c04 `damage_apply` | an earlier last-bit difference in a position or statistic | the number or timing of `g_randSeed` draws, which is in the hash |
| 0x1a81f4 and the seven melee divides | slow byte = 60 (D16) | cast and swing frame numbers; same outcome on every machine as far as known |

### Advice for players

Use the same emulator version on every machine and leave these at their defaults, or at
least identical: EE/FPU rounding, EE/FPU division rounding and EE/FPU clamping, the VU0
and VU1 rounding and clamping, the FPU and VU game fixes, and the EE and VU recompilers
(on). A real console against an emulator, or an ARM-native build against an x86 one, has
not been shown to stay in sync and should be expected to drift. If the arena still goes
out of sync with all of that equal, the cause is not floating point.

### Patch proposals (all untested)

One change each. PCSX2 form: `patch=1,EE,<address>,word,<new>`. None of these addresses a
known cause; they remove divides by zero that were found.

| # | Address | Original | New | What it changes | What could go wrong | Every player? |
|---|---|---|---|---|---|---|
| F1 | 0x0014d56c | 46020000 | 00000000 | `obj_moveWithCollision` stops adding the vertical component into its "is there any movement" test, so the test covers the same horizontal length that `terrain_sweepCircle` later divides 1.0 by (0x185b84) | an object given a purely vertical velocity through this function would no longer be moved by it. The callers read (`Player_move`, `Container_run`, `AutoContainer_run`, `RedDragon_run`) pass a zero vertical part, so nothing changes for them; `SpellShadowStep_run` passes a stored vector whose vertical part was not traced | yes |
| F2 | 0x001a81b4 | 2403003c | 2403003d | cast state: the slow scale becomes (61 − slow) / 60, which is 1/60 instead of 0 at slow = 60, so 0x1a81f4 never divides by zero | every slowed player's cast timing is 1/60 quicker than before; at slow = 60 the cast fires after 60 times the normal delay instead of never, while the animation (scaled elsewhere) still stands still | yes |
| F3 | 0x001aa190 | 2403003c | 2403003d | melee state: the same for the swing-speed factor, covering the seven divides listed above | as F2, for swings | yes |

No patch is proposed for the FireStorm light divides (the value is the right one for a
light of radius zero and goes nowhere else) or for the insects (the quotient is discarded).

### Proposed ledger rows

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| new | No float status flag can influence the game: the control register is written once and never read, and there is no double-precision or multiply-add instruction | Observed | 0x14fb98; raw scan of `.text` |
| new | In the arena fight three computations divide by zero: the FireStorm light (constructor, and for the first 30 frames of each storm) and the insects' speed on the arrival frame. The first two feed a light record, the third is overwritten before use | Observed | 0x2d429c, 0x2d4854, 0x2d48a8; 0x30cee8, 0x30cf40, 0x30d050 |
| new | A player with slow byte 60 divides by zero in the cast and melee states; 60 is reachable only through status counter 7 | Observed; reachability is D16 | 0x1a81a0–0x1a81f8, 0x1aa178–0x1aa1b4; 0x113738–0x1137d8 |
| new | Every machine decodes stick input through a ten-step single-precision spring and truncates the result, so player input itself depends on bit-identical float arithmetic | Observed; effect Inferred | 0x13cdb0–0x13cddc |
| new | Skeleton poses are computed by a VU0 microprogram, and `Player_castSkill` places a cast at a point taken from the pose | Observed | 0x16f594, 0x16f5f4, 0x3e5c40; 0x1a42b8 |
| new | `sqrt.s` of the constant 0x3e4ccccc is evaluated at run time in four functions; its correctly rounded value is 0x3ee4f92d or 0x3ee4f92e depending on the rounding rule | Observed (sites), computed (values) | 0x10bbc8, 0x10bcc4, 0x10bdcc, 0x13cd24 |
| new | The sync hash converts player coordinates with `cvt.w.s`, which truncates and has no mode | Observed | 0x13afe0, 0x13afec, 0x13aff8 |
| D25 (add) | Floating-point special cases are not a cause of the arena desync either; a float cause requires machines that do not compute identically, and would not be specific to the arena | Inferred | this document |

## Notes on earlier documents

- `docs/netcode.md`, codec section: "the local player's own input goes through the same
  encode and decode … so all machines agree" needs the condition that the decoder's float
  spring is bit-identical on every machine.
- The premise that Tagar's Insects "divides a distance by a time difference that can reach
  zero" is true of the instruction (0x30cee8) but the quotient is unused in exactly that
  case.
- `docs/engine.md`, "Pose": the per-joint matrix is built by VU0 (`g_vu0PoseProgram` in
  `symbols/fmt-anim.tsv`), which that section does not say. Not wrong, but it is the reason
  the vector unit's settings matter to the simulation.
- Nothing in `docs/issues/arena-desync.md` was found to be wrong.

## Not done

- The readers of the light record's inverse-radius fields were not listed.
- Of 255 conversions and 72 "not closed" divides in the arena set, the conversions were
  sampled by function and the divides in drawing, sound, camera, particle and water code
  (`fx_modelStatusEffects`, `sound_panAtten`, `water_disturb`, `Camera_*`,
  `mat4_setProjection`, `particleDef_init`, the rigid-body functions) were skipped as not
  simulation or not in this level.
- Virtual calls are not followed by `--reach`: the weapon helper objects and the skills a
  *player* brings into the arena were not scanned as part of the arena set.
- Whether `max.s` / `min.s` and the compares treat −0 and +0 alike on console and emulator.
- The melee divides at 0x1aaf94 and 0x1aafac were not followed to their use.
- The attack-rating argument of `damage_apply` was resolved at 37 of its 103 call sites
  only (30 constants, 7 creature statistics).
- How the console itself rounds any particular operation: everything said about it is from
  descriptions, and one measurement (the root of 0x3e4ccccc, or the stick decoder's output
  for a known input) would replace a good deal of inference.
