# Combat runtime, round 4

US `SLUS_209.73` v2.00. Round 4 of `docs/combat-runtime.md`. It is the prose of
`tools/ref_combat_round4.py`. Round 1, round 2 and round 3 APIs, pinned vectors and
bodies are unchanged. New bodies are methods on a subclass.

Evidence labels as in round 1. **Executed** means `tools/difftest_combat_round4.py` ran
the original in `tools/ee_emu.py` and the model agreed: calls and arguments, bytes stored
outside the stack, the shared seed and its draw count, the result. **Observed** means
read at the address. Nothing here was run on a console, in PCSX2 or on the live rig.

## 1. Potion kinds 1, 2 and 3

`playerProjectile_run` `0x1ba940`. Kinds 0 and 4 and above stay the round-2 body.
Kinds 1, 2 and 3 share its spin, its gravity and `obj_moveAndCollide`, then diverge
(*Executed*, `difftest_combat_round4.py`, seed 20973, 40 cases each, and again with
seed 7). The function is 674 instructions. Each kind's entry executes its own tail.
The other two tails, and the spin arms for kinds 0 and 4–6, are not in that entry.

A potion keeps the mover's result whole. Kinds 0 and 4 and above clear bit 1 and set
it again when the splash byte `+0xcc` is set. Kinds 1, 2 and 3 do not. A nonzero
result stores 0 at `+0xec`. A result of exactly 2 plays the stone-hit sample only when
`+0xcc` is 0. A result of exactly 1 always plays it, after `terrain_height` of the
projectile's position with the radius at `+0x1c`, plus 5 on z. Neither result spawns
the stone effect: that effect is kinds 0, 4, 5 and 6. Any other nonzero result (bit 1
and bit 2 together) stores 0 at `+0xec` and plays nothing.

While the frame is strictly below `+0xec` the run returns. Otherwise the kind's ending
runs and slot 1 is called with 3. A hit stores 0, so the ending runs on that frame. A
miss runs it only once the stored frame has been reached.

The spin for these three kinds is the same arm as any kind that is not 0 and not 4, 5
or 6: the halfword at `+0x1cc` loses 200 while it is not strictly below −4999.

**Kind 1**, every run, before the spin. The shared seed at `0x404464` is advanced
inline, three draws a sample, the same step `draw` uses. A sample is kept when the
squared length is not strictly above 1. The vertical coordinate is negated when it is
strictly below +0. Then:

| | Definition | Count | Direction |
|---|---|---|---|
| first | `0x8658b0` | 2 | `(x, y, z)` times 5, and z times 5 again |
| second | `0x865900` | 1 | `(x, y)` times `0x3fa3d70a`; z times that and then `0x41c5c28f` |

The position is the projectile's. The speed argument is 0.

On the ending: `res_find` of `0x535ef0` and `0x537b90`, played on the projectile. Then
five times: a ball scaled by 20, added to the position; `terrain_height` of the
projectile (not the offset point) with radius 6; z replaced by that height plus 1;
`pool_new(0x54)` and, with a block, `LooseFire_ctor(block, that point, owner)`. The
owner is the object behind the handle at `+0x1c8`, or 0. Then one shared draw, and
`decal_add` of the same x and y with z one higher, angle the draw as a signed
halfword, kind 9, flag 0, size 36. The decal is made even when the pool returns 0.

**Kind 2.** No flame in flight. On the ending, `pool_new(0x70)`. With a block,
`poisonGasSpell_ctor(block, position, 300, 20, 0, owner, 5)`, then `res_find` of
`0x537bb0` played on the cloud. With no block there is no constructor and no cloud
sound. The projectile is destroyed either way.

**Kind 3.** No flame in flight. On the ending, the position with 14.699999 added to z
is given to `fx_ringBurst` at scale 2, after `res_find` of `0x537bc8` on the
projectile. `world_damageInRadius(owner, position, 50, 0x40840, 0, 0; 40, 180)` runs
unless the level name at `0x44fe18` matches `0x535ed8` (`innpit`) with case ignored.
The comparison is the C library. Then `terrain_height` of the position with radius 6.
The gap `height − z` is taken to a double, made non-negative with the soft-double
subtract, and compared with 4.0. Strictly inside that, one shared draw and
`decal_add` of `(x, y, z+1)`, kind 9, flag 0, size 48. Then `pool_new(0xbc)` and, with
a block, `LightEffect_ctor`: the eight register floats are 128, 100, 78, −32, 0, 0, 0,
0, and the four stack words are 168, 60, 1 and `0x3eb33333`.

Coverage of the 674-instruction function, 40 cases each: kind 1 is 452, kind 2 is 203,
kind 3 is 325. Kind 1's entry does not run the gas or blast tails. Kind 2's entry does
not run the flame or the blast. Kind 3's entry does not run the flame or the gas.

## 2. Not in this section yet

- Deflection inside the runtime. Round 2's `missile_on_touch` has the branch.
  `RangedRuntime` still refuses `item_parseDescriptor`.
- The player's bow release in state 0.
- Holy Shield's `LightEffect`, and `Player_blockSparks` with silent ≠ 0.
- Death states beyond the classes already executed.
- Combat paths of the remaining skills.

## 3. What was run

`python3 tools/difftest_combat_round4.py <your SLUS_209.73>` (seed 20973, and seed 7).
Calls, bytes outside the stack, the shared seed, the result. `sprintf`, `strcasecmp`
and the soft-double helpers run for real. They are the C library.

`python3 -m unittest tools.test_ref_combat_round4` — synthetic fixtures. Those tests
are evidence about the model. `RangedModel.thrown_run` still refuses a potion.
