# Combat runtime, round 3: disease, gore, the stance phantom, arrow kinds

US `SLUS_209.73` v2.00. Round 3 of `docs/combat-runtime.md`. It is the prose of
`tools/ref_combat_round3.py`. Round 1 and round 2 APIs, pinned vectors and bodies are
unchanged. New bodies are methods on a subclass, or on `ArrowModel`, which subclasses
`RangedModel` and leaves kinds 0 and 3 on that class.

Evidence labels as in round 1. **Executed** means `tools/difftest_combat_round3.py` ran
the original in `tools/ee_emu.py` and the model agreed: calls and arguments, bytes stored
outside the stack, the shared seed and its draw count, the result. **Observed** means
read at the address. **Authored** means a fixture or a callback this harness did not
re-execute. Nothing here was run on a console, in PCSX2 or on the live rig.

`tools/ref_combat_round3.py` subclasses `tools/ref_skills_a.py`'s `Model` for the disease
cloud, GutChunk and the phantom, and subclasses `RangedModel` for the arrows.
`obj_moveAndCollide` stays a call-out of `ArrowModel`. The ranged difftest still runs
that body for real inside kinds 0 and 3.

## 1. DiseaseCloud

Table `0x5186f0` (the addend is `0x86f0`; `symbols/runtime.tsv` already names this
table). Constructor `0x2ce610`, run `0x2ce6e0`. Cross-checked with research-fx
`docs/effects.md` section 17: the cloud's `damage_apply` passes attacker 0.

Constructor (*Executed*, 52 of 52). Stores the level word at `+0x50`, `0x30` at `+0x58`,
`frame + 0xf0` at `+0x54`, `0x14` at `+0x60`, `10.0` at `+0x5c`, sets object flags
`| 3`, then `obj_runEveryFrame`. An owner is linked at `+0x4c` with `handle_link`.

Run (*Executed*, 547 of 551). The four missed instructions (`0x2ceeb0`, `0x2ceeb4`,
`0x2ceedc`, `0x2ceee0`) are the arm that fills a descriptor slot already holding a
different type. A fresh record takes the empty-slot arm, so those four were not run.

- Radius at `+0x5c` grows by `0.5` while it is strictly below the float in `+0x58`,
  before the particle loops.
- Particle count is the integer at `+0x58` divided by 10, reloaded for each of three
  streams. Definitions `0x8e5320`, `0x8e5370`, `0x8e53c0`. Speeds `6`, `6`, `12`.
  Placement is `ref_skills_a`'s unit ball. `particle_spawn`'s speed argument is 0.
- Damage only when `frame % 30 == 0`. Box is the position ± the truncated radius,
  capacity `0x40`. `damage_apply(victim, 0, 100000, 0, 0, 0x1000040, descriptor, 0)`
  with both amount floats 0. The descriptor is type `0x26`, both magnitudes the word
  at `+0x60`.
- Skips: the owner, any object whose handle word is 0, and any object with flag
  `0x40` when another object in the list also has `0x40` (two players). An ownerless
  cloud still deals damage. Attacker is always 0.
- Destroy (slot 1 with 3) when the frame is no longer strictly below `+0x54`.

`disease_attach` is the call at `0x1e9e28` inside `damage_apply` (*Observed* there,
*composed* here, not a mid-function slice). It does `pool_new(0x1b0)`. With a block,
seconds are `trunc(5 - diseaseRes * 5)` where disease resistance is the float at the
victim `+0x68`, then the already-executed `SpellDiseaseEffect_ctor`. `creature_addSpell`
is recorded even when the pool returns 0. The sound before the pool, and the rest of
`damage_apply`, are not this function. Synthetic tests cover it. It is not a difftest
entry.

## 2. GutChunk

Constructor `0x201958`, table `0x50f3b8` (*Executed*, 53 of 53). `PhProp_ctor`
`0x155a0c` stays a callback. The bytes around it copy the object's position at `+0x10`
to `+0x250` and call `PhProp_ctor` with the name block `0x4f86a0` (the `+0x60` name
when the bits have bit 1, otherwise `+0x58`). Kind and `0xb41` follow. `+0x248` is the
bits; if the gore word at `0x44fdc0` is strictly below 2, the stored bits also have bit
0. `+0x25c` is 2. Byte `+0x260` is 0.

## 3. Strong Stance phantom

Constructor `0x1618d4`, run `0x161a54`, table `0x50f448` (*Executed*, 95 of 95 and 33
of 33). `Creature_ctor` `0x109d68` stays a callback. The harness answers it by storing
the class word at `+0x24`, which the constructor then reads for `res_find`. A null
class faults the original.

After that callback: anim cleared at `+0x114`, `res_find` of the class lump and the
name, `anim_startBlendInOut` with `0x802`. Creature flags `+0xa8` gain bit 63. Object
flags gain `0x4005`. `+0x2e0` is copied from the target's `+0x2e0` (a halfword, not
the facing at `+0x38`). `+0x2e8` is `speed * 1.25`. Radius `24`. `+0x3d4` is the flag
argument. Both timers `+0x3cc` and `+0x3d0` are `240` when the flag is set and `75`
otherwise. Then `obj_runEveryFrame` and `handle_link` of the target at `+0x3c8`.

`anim_startBlendInOut` does not write its object register. The constructor reloads the
phantom before `obj_runEveryFrame`.

Run: `Creature_stepAnim` at scale 1, `Creature_applyKnockback` at `0.5`,
`Creature_moveBy` of a zero velocity. The timer loses 1. `obj_delete` when the stored
value is strictly below 1. A timer of 240 lasts 239 steps; 75 lasts 74.

## 4. Arrow kinds 1, 2, 5 and 6

`MissileWeapon_run` `0x15153c`. Kinds 0 and 3 stay the round-2 body. Kinds 1, 2, 5 and
6 share its flight up to the impact test and then diverge (*Executed*,
`difftest_combat_round3.py`, seed 20973). The function is 1,024 instructions. Each
kind's entry executes its own tail; the carried-arrow path (handle `+0x128`) is still
the round-2 body and is not re-run here.

A nonzero move result (bit 1 of `obj_moveAndCollide` cleared, or the splash byte)
plays one impact sample through `res_find(0x532478, …)` and `sound_playOnObject`, and
stores 0 at `+0xec`:

| Kind | Sample |
|---|---|
| 1 and 2 | `0x5324e0` |
| 5 | `0x5324f8` |
| 6 | `0x532518` |

The stone-hit effect (effect 2, 8 or `0x11`, then the stone sample) is kinds 0 and 3
only. Kinds 1, 2, 5 and 6 never reach it. A result of exactly 1 also plays the sample
word at `+0x1bc`. Kind 1, and only kind 1, spawns effect 5 before that sample.

Because a hit stores 0 at `+0xec`, the frame test at the end destroys the arrow (slot
1 with 3) on that same frame, after the light is relinked.

**Kind 2** (exploding). `fx_ringBurst` of the position at scale 2. `pool_new(0xbc)`
and, with a block, `LightEffect_ctor`: colours `0x437f0000`, `0x431b0000`, `0`,
`0xc2000000`, then four zeros; stack `0x43580000`, `0x42f00000`, `1`, `1`. Then
`world_damageInRadius` of the owner at handle `+0x4c` (or 0) for the raw word at
`+0xd8`, flags 0, least 0, skip 0, inner 24, outer 72. No particles in flight. The
position is copied to `+0x1a4` and `light_relink` runs on `+0x174`. No cold puff and
no trail. 201 of 1,024 instructions on this entry (40 cases).

**Kind 5.** Effect 10, then the same pool. Its light has first colour word 0 and third
word `0x437f0000`; the other words match kind 2. No radius damage. Every frame, hit or
miss, 32 particles from definition `0x6e00c0`. Position is the arrow plus its velocity
times `0x3da3d70a` plus a rejection-ball direction times 10. The particle direction is
a second ball times `0x41421062`. The speed argument is 0. Then the same position copy
and `light_relink`. 326 of 1,024 (40 cases).

**Kind 1.** On a hit, `(object draw & 3) + 3` times: `pool_new(0x148)` and, with a
block, `ParticleProp_ctor(block, position, 8)`. Then kind 2's light. No radius damage.
Every frame, 24 pairs. The shared position starts at the arrow plus velocity times
`0x3d75c28f`. Each axis adds `((object draw % 40) - 20) * 0x3dcccccc` and
`velocity * 0x3c23d70a *` the matching axis of a rejection ball. The direction is a
second ball times 4. First particle `0x6dffd0` at that position; second `0x6e0020` at
that position minus velocity times `0x3d75c28f`. Speed argument 0. 392 of 1,024 (40
cases).

**Kind 6.** On a hit, 100 particles from `0x6e0070` at the arrow's own position. The
direction is a rejection ball times `0x41accccc`, and `0x3fd10624` is added to z.
Speed argument 0. The light matches kind 5. Every frame, if the owner object has flag
`0x40`, `player_getPassiveLevel(owner +0x3c8, 0x1000)` runs and the result is not
used. Then the position copy and `light_relink`. 247 of 1,024 (40 cases).

The rejection ball is three coordinates `draw/65536 * 2 - 1` from the object's
generator at `+0x44` (`GameObject_rand`, run for real), accepted when the squared
length is not strictly above 1.

## 5. Not in this round

- Potion kinds 1, 2 and 3 inside `playerProjectile_run` `0x1ba940`. Kind 1 is the
  branch at `0x1ba984` and draws the shared seed inline (the constant `0x404464` is
  loaded there). *Observed* only. Kinds 2 and 3 were not read past that split.
- Deflection. Round 2's `missile_on_touch` already has the branch. `RangedRuntime`
  still refuses `item_parseDescriptor`. This round did not re-execute it and did not
  change that runtime.
- The player's bow release in state 0, inside `Player_run` (three `MissileWeapon_ctor`
  sites near `0x1a9240`, `0x1a9344`, `0x1a944c`). Not read this round.
- Holy Shield's `LightEffect`, and `Player_blockSparks` with silent != 0 (the shared
  seed path near `0x1b9928`). Not read this round.
- Death states beyond the classes round 2 already executed.
- Combat paths of the remaining skills. `describeRank` was not remodelled. The skill
  bodies in `difftest_skills_a/b/c` stay the executed account of those functions.

## 6. What was run

`python3 tools/difftest_combat_round3.py <your SLUS_209.73>` (seed 20973). Calls,
bytes outside the stack, the shared seed, the result. `GameObject_ctor` and
`GameObject_rand` run for real. `PhProp_ctor` and `Creature_ctor` stay callbacks.

`python3 -m unittest tools.test_ref_combat_round3` — synthetic fixtures for the cloud's
skips, `disease_attach`, GutChunk's gore bit, the phantom timers, and one case of each
arrow kind. Those tests are evidence about the model.
