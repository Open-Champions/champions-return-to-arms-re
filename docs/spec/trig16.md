# `math_cos16` and `math_sin16`

US `SLUS_209.73` v2.00. This is the account of the two angle routines, of the only table
built from them, and of their callers in the effect code and the combat code. The prose
form of the polynomial is also `docs/spec/core.md` section 4. `tools/ref_trig.py` is a
second entry point onto `tools/ref_core.py`'s FPU; `tools/difftest_trig.py` runs the
original functions in `tools/ee_emu.py`.

Evidence: **Observed** = read at the address; **Executed** = the original instructions
were run in the interpreter and the reference agreed; **Inferred**; **Unknown**. Nothing
here was run on a console. The last bit of an add on real hardware is not established
(`docs/issues/dynamic-tests.md`); every match below is against the interpreter, and it
holds under each of the four adder models when the reference uses that same model.

No table from the executable is stored in this repository. The haze circle is not in the
ELF at all: `particle_init` writes it at run time, and `ref_trig.haze_circle` recomputes
one pair.

## 1. The routines are a polynomial

**Observed.** `math_cos16` is 0x166630–0x1666df. `math_sin16` is 0x1666e0–0x166793
(then a nop, and `math_atan2_16` begins at 0x166798). Neither body loads from memory:
there is no `lw` / `lwc1` in 0x166630–0x16679f. The four coefficients are immediate
operands, each a `lui`/`ori` pair:

| Pattern | Role |
|---|---|
| 0x38490fda | π/65536. The folded angle is half the original, in radians |
| 0x3e2aaa57 | 0.16666542. Not the nearest float to 1/6 |
| 0x3c086b24 | 0.008326326 |
| 0x39458017 | 0.00018835101 |

The same half-angle immediate occurs at five places and five only: the two routines,
and the inlined copies in section 6.

`math_sin16` does not call `math_cos16`. It is a second copy of the body. The first
instruction is `addiu v1, a0, −0x4000` on the full 32-bit argument; the sign-extend and
the polynomial then use `v1`. Keeping the low 16 bits of `angle − 0x4000` is that
reduction, including when bits above bit 15 are set, because a subtract modulo 2^16
depends only on the low 16 bits. **Executed:** `sin16(angle)` and `cos16(angle − 0x4000)`
agree for every 16-bit angle, and both agree with the executable when the high bits are
junk (`angle.high-bits`, every 64th angle).

A full turn is 65536. There is no table index and no interpolation inside either
routine. The only scaling is the multiply by 0x38490fda after the angle has been folded.

## 2. Operation order

Each multiply, add and subtract is its own R5900 operation. There is no fused
multiply-add. The reference in `ref_core.cos16` / `ref_trig.cos16` is this order. `f0`
comes back as the result; the last multiply is the delay slot of the return, so it does
run.

```
cos16(angle):
    a = sign_extend_16(angle)                 # sll 16; sra 16. Exact
    sign = +1.0                               # 0x3f800000
    if bit 15 of a != bit 14 of a:            # xor, then andi 0x8000
        sign = -1.0                           # 0xbf800000
        a = sign_extend from bit 14 of a      # sll 17; sra 17. Exact
    x  = float(a) * 0x38490fda                # cvt.s.w, then mul.s
    x2 = x * x
    x3 = x * x2
    p3 = x3 * 0x3e2aaa57
    x5 = x3 * x2
    s  = x - p3
    p5 = x5 * 0x3c086b24
    x7 = x5 * x2
    s  = s + p5
    p7 = x7 * 0x39458017
    s  = s - p7
    return sign * (1.0 - (s + s) * s)         # add, mul, sub, mul

sin16(angle) = cos16(angle - 0x4000)
```

The fold is the second and third quadrants. Bit 15 set and bit 14 clear is 180°–270°;
bit 14 set and bit 15 clear is 90°–180°. Both map into −16384…16383, and the sign makes
the cosine negative. The other two quadrants keep the sign-extended angle and sign +1.
The machine computes `x5` before it subtracts `p3`, and `x7` before it adds `p5`. Those
two results do not depend on each other, so the bits are the bits of the order above.

**Float precision of each step.**

- The two sign-extends and the quadrant test are integer. Exact.
- `cvt.s.w` of the folded angle is exact. The magnitude is at most 16384, and every
  integer in that range is a float32.
- Every `mul.s`, `add.s` and `sub.s` truncates toward zero. None of them rounds to
  nearest. The products `x2`, `x3`, `x5`, `x7` and the three coefficient products each
  round, and so does each of the three adds into `s` and the final `1 − 2s²`.
- The multiply by the sign is a multiply by the exact ±1 already in a register. For
  these magnitudes that copies the value or flips its sign bit.

The adds are where two adder models disagree. Against the interpreter's default `ps2`
model, over all 65,536 angles, both the cosine and the sine differ on 45,278 angles
under `ps2g1`, on 2,830 under `chop`, and on 46,206 under `nearest`. **Executed:** with
the reference and the interpreter on the same model, all 65,536 angles of both routines
match (`angle.ps2`, `angle.ps2g1`, `angle.chop`, `angle.nearest`). A port that wants
these bits uses this truncation and one of those adders. A correctly rounded IEEE cosine
is a different function: the absolute gap against this host's `math.cos` reaches
7.141×10⁻⁷ at angle 0xb96f, and the unit in the last place of a value near 1 is
2⁻²³ ≈ 1.19×10⁻⁷.

## 3. Values at the quarter turns

**Executed**, every angle, default adder. These are the same values as `docs/spec/core.md`
section 4.

| Call | Pattern | Reading |
|---|---|---|
| `cos16(0)` | 0x3f800000 | +1 |
| `cos16(0x8000)` | 0xbf800000 | −1 |
| `sin16(0x4000)` | 0x3f800000 | +1 |
| `sin16(0)`, `cos16(0xc000)` | 0x34800000 | +2⁻²², not 0 |
| `cos16(0x4000)`, `sin16(0x8000)` | 0xb4800000 | −2⁻²², not 0 |

No angle returns +0. `cos16(a) = cos16(−a)` fails for 1,190 angles. A rotation by angle
0 therefore does not leave a matrix unchanged: `mat3_rotateAxis(identity, Z, 0)` has
±2⁻²² off the diagonal.

On this arm64 macOS host, packing `math.cos` / `math.sin` of the same angle to float32
disagrees with the polynomial on 47,374 of 65,536 angles for the cosine and the same
count for the sine; 29,256 angles disagree in both, and 65,492 disagree in at least one.
`math.sin(0)` is +0 on every IEEE libm, so angle 0 is a portable disagreement. The other
counts are this host's libm. Another libm moves them.

## 4. The haze circle, the one table

**Observed** at `particle_init` 0x18e648, **Executed** as `haze.circle` (64 pairs, 0
mismatches).

The loop is `s1 = 0 … 63`. The angle is `s1 << 10` (64 steps of 1024, one full turn).
It stores `cvt.w.s(sin16(angle) * 5.0)` and then `cvt.w.s(cos16(angle) * 5.0)` at
0x007ec0e0 + index × 8. 5.0 is the immediate 0x40a00000. `cvt.w.s` truncates toward
zero, and `swc1` stores the integer's bits. The sine word is at +0, the cosine word at
+4. The table is BSS. It is not in the ELF, and the 64 pairs are not committed here.
`ref_trig.haze_circle(index)` is the pair.

Index 0 is the words (0, 5): 5 × 2⁻²² truncates to 0, and the cosine of 0 is 1. Index
16, angle 0x4000, is (5, 0). Truncation collapses the 64 slots onto 28 distinct pairs.
`haze_circle(0)` and `haze_circle(64)` are the same pair: the reader keeps six index
bits.

**The reader is `particle_drawHaze` 0x18fe18, and it does not interpolate.** The only
formations of an address in 0x7ec000–0x7ec2ff are the write above and two loads here
(0x190378 → 0x7ec0e0, 0x1903ac → 0x7ec0e4). One `lw` each. The index is:

```
age   = float( sign_extend(g_particleClock) − sign_extend(cell[+6]) )    # cvt.s.w, no scale
index = trunc( slot[+0x2c] + slot[+0x3c] * age ) & 63
pair  = words at 0x7ec0e0 + index * 8
```

`g_particleClock` is the halfword at 0x82cc90 (0x190138–0x190154). The cell stride is
16, and +6 is the birth tick already documented for a particle cell. The slot comes from
the unsigned halfword at cell+0xe, shifted `<< 16`, arithmetic `>> 18`, `<< 6`
(0x190164, 0x19019c, 0x1901bc, 0x1901d0), and added to `g_particleTypeTable` 0x82c490.
That is `slot = (cell[+0xe] >> 2)` for the small values the spawn writes, times the
0x40-byte record. The resident record is the definition's +0x10…+0x4f (`docs/effects.md`
section 2), so slot+0x2c is the start alpha and slot+0x3c is the alpha rate. Kind 3
stores those channels without the 2²³ bias; the other kinds add 2²³, which would make a
nonsense circle index. The symbol for this function is the mode-3 drawer, and
`particle_emitLists` does not draw kind 3. **Unknown:** this pass did not re-prove that
no other kind reaches the function.

The fraction discarded by `cvt.w.s` is not used. There is no second sample and no blend.
The cosine word is added into one screen coordinate (0x1903e4) and the sine word into
the other (0x1903fc), each after an arithmetic shift right by 4. Which screen axis is
which was not separated from the rest of the fan (the surrounding adds are the copy
rectangle).

On this same arm64 libm, `trunc(5 * sin)` and `trunc(5 * cos)` of the 64 angles match
all 64 integer pairs. The float results in section 3 still differ; the haze words happen
not to, at this scale, on this libm.

## 5. Callers

A `jal` scan of `.text`: 507 sites call `math_cos16` from 245 functions, 604 sites call
`math_sin16` from 282 functions, 283 functions call at least one. The "245 and 282
callers" in `docs/engine.md` are those function counts. Three further copies are inlined
and are not in the counts (section 6).

An argument below is stated only when the delay slot of the `jal`, or the instruction
immediately before it, writes `a0`. A formula stated in an earlier executed document is
cited, not re-derived. Skill and monster call sites are counted in section 5.5 and were
not opened one by one; their references already call this polynomial.

### 5.1 Particles, glows, trails, beams

| Function | Sites | What the call is |
|---|---|---|
| `particle_init` 0x18e648 | sin 0x18e680, cos 0x18e694 | the haze loop. `a0` is the angle `i << 10` |
| `glow_draw` 0x1907d0 | cos 0x190ca8, sin 0x190cc0 | the rotated quad. The cosine's delay slot is `lh` of record+0x1c. **Executed** geometry: `C = int(cos16(angle) * float(H))`, `S = int(sin16(angle) * float(H))` (`docs/effects.md` 13.7). The quad is skipped when the flag that selects it is clear |
| `trail_setCircle` 0x1920e0 | cos 0x192444, sin 0x192498 | the circle. The cosine takes register `s2` (the instruction before the `jal`). The step is `0xffff // steps` (effects.md 13.8) |
| `emitter_run` 0x195400 | cos 0x195704, sin 0x195710, sin 0x195748, cos 0x195754 | the yaw offset. All four take register `s3`. The executed formula is `off.x*cos + off.y*sin` and `−off.x*sin + off.y*cos` (effects.md section 5) |
| `emitter_run` | eight `jal` to `mat34_rotateAxis`: 0x1956d4, 0x1956e8, 0x195980, 0x1959d8, 0x195a1c, 0x195a2c, 0x195a58, 0x195a68 | the box matrix and the velocity rotations in that same formula (Z then Y, four times). The pairing of each site with a flag is the existing description, not a new branch trace |
| `trail_sweepPairs` 0x191ea0 | `quat_fromAxisAngle` at 0x191fd8 | indirect. The step is `0x10000 // (steps − 2)` (effects.md 13.8). `quat_fromAxisAngle` 0x1663c0 calls cos at 0x166424 and sin at 0x166430 on the half angle (core.md) |

**Beams do not call either routine.** The range 0x192a40–0x193fff, which holds
`beam_buildNodes`, `beam_buildPoints`, `beam_driftNodes`, `beam_create` and
`beam_update`, contains no `jal` to either address. The documented beam shape is the
seed and the offsets in effects.md 13.5. The particle and trail VU programs consume
positions and widths the EE already computed. This pass did not re-read that microcode,
and `tools/vu1_emu.py` was not needed for these two EE functions.

`mat3_rotateAxis` 0x162960 (cos 0x162988, sin 0x162994) and `mat34_rotateAxis` 0x163000
(cos 0x163028, sin 0x163034) are the indirect form used by the sweeps and the emitter.

### 5.2 Decals and the effect helpers

Decals, both pairs **Executed** in `tools/difftest_decals.py` against `tools/ref_decals.py`,
which calls the polynomial:

- `decal_add` 0x19f110: cos 0x19f32c, sin 0x19f360. The delay slots do not write `a0`.
  The model multiplies `cos16`/`sin16` of the caller's angle by the size and by 4
  (0x40800000), then truncates.
- `decal_drawTask` 0x19f4e8: cos 0x19f5b0, sin 0x19f5d0. The sine's delay slot, and the
  instruction before the cosine, are `lh` of the growing slot at +8, the angle in that
  record. Growth adds 0x3d4ccccc, or 0x3e4ccccc when the mode is 2, then the same
  size×4 truncation (effects.md 16.2).

The helpers below are in the effect and gameplay range. Where the delay slot or the
previous instruction writes `a0`, that setup is the right-hand column. The recipes that
name a yaw or a frame shift are the ones already executed in `docs/effects.md` sections
14 and 15; this pass did not attach each `fx_spawn` site to an effect id.

| Function | Sites | Argument at the call |
|---|---|---|
| `fx_pulseColor` 0x1ec360 | sin 0x1ec3b0, cos 0x1ec3e0, sin 0x1ec3fc | the cosine takes `s0`. The first sine's argument is not in the delay slot |
| `fx_spawn` 0x1ef270 | 0x1f1ff8/0x1f2018, 0x1f2170/0x1f2190, 0x1f2240/0x1f2260 | not in the delay slot. Recipes: effects.md section 14 |
| `GlowingCylinder_run` 0x1f3288 | 0x1f32b4/0x1f32d8, 0x1f3350/0x1f3374 | cosine delay slot is `<< 11` of the word just loaded |
| `Fire_run` 0x1f34e0 | sin 0x1f357c | delay slot `<< 10` |
| `fx_disintegrateModel` 0x1f4340 | 0x1f45fc/0x1f4608 | `a0 = s4` |
| `fx_disintegrateModelB` 0x1f4758 | 0x1f49f8/0x1f4a04 | `a0 = s3` |
| `fx_burnModel` 0x1f5210 | 0x1f53a8/0x1f53b4 | `a0 = s6` |
| `fx_drawModelGlowNearCamera` 0x1f5890 | 0x1f5940/0x1f594c, and sin 0x1f5bac | the pair takes `s5`. The extra sine is `<< 10` of a loaded word |
| `fx_modelParticlesNearCamera` 0x1f5c70 | 0x1f5d68/0x1f5d74 | sine takes `s2`. Cosine's argument is not in the delay slot |
| `fx_modelParticlesNearCamera` 0x1f5e18 | 0x1f5ee4/0x1f5ef0 | `a0 = fp` |
| `fx_shockModel` 0x1f61c0 | 0x1f63cc/0x1f63d8, 0x1f6524/0x1f6530 | both pairs take `s3` |
| `fx_modelStatusEffects` 0x1f6ac8 | sin 0x1f7b4c | `<< 10` of a loaded word |
| `fx_spawnIceChunks` 0x1fb058 | 0x1fb140/0x1fb14c | `a0 = s2` |
| `fx_shatterToLooseIce` 0x1fb240 | 0x1fb404/0x1fb410 | sine takes `s3` |
| `FireEffect_draw` 0x1fcef0 | sin 0x1fcfe0, sin 0x1fd06c | not in the delay slot |
| `FrostStormSpell_run` 0x1fe950 | cos 0x1ff4cc, sin 0x1ff4e0 | cosine takes `s0` |
| `RainOfFireSpell_run` 0x1ffcc0 | 0x1fff3c/0x1fff54, 0x1ffff0/0x200008 | the second cosine takes `s0`, after an arithmetic `>> 16` |
| `WaterSpout_ctor` 0x201fa8 | cos 0x202010, sin 0x202040 | cosine argument was arithmetic `>> 16`. Sine takes the halfword at +0x38 |
| `GlowingCylinder_draw` 0x1f2ef0 | `mat34_rotateAxis` 0x1f30a4, 0x1f3168, 0x1f3200 | indirect |
| `IceChunk_run` 0x1faf40 | `mat34_rotateAxis` 0x1fafac | indirect |
| `GlowingShaft_draw` 0x1fda20 | `mat34_rotateAxis` 0x1fdc50, 0x1fdcbc, 0x1fdd50 | indirect |
| `FrostStormIceShard_draw` 0x1fddd0 | `mat34_rotateAxis` 0x1fde44 | indirect |

`MissileTrap_run` 0x1f3a90 and `Shooter_run` 0x1f4ad8 are both an effect object and a
shot. They are in section 5.3.

### 5.3 Combat: hits, blocks, knockback, shots

`+0x38` below is the creature or player facing halfword (the `lh` of offset 56).

`damage_apply` 0x1e8230, three pairs. The block test is combat.md step 11, and it is
**Executed** there, including the spark path. This pass tied the calls to that account:

- 0x1e87c0 cos, 0x1e87cc sin. The instruction before each `jal` is `lh` of victim+0x38,
  and the delay slot does not write `a0`. That is the dot
  `cos16(facing)·(ax−vx) + sin16(facing)·(ay−vy)`, compared `> 0`, under creature flag
  0x200 with flag 0x40 clear.
- 0x1e886c cos, 0x1e8898 sin. The delay slots do not write `a0`. These are the calls in
  the 50-spark branch, which the executed model multiplies by 10 (0x41200000) along
  that same facing. This pass did not re-read the gap between the dot and these sites.
- 0x1ea8f0 cos, 0x1ea8fc sin. Same `lh` of +0x38. This is the PvP text test: player
  state +0x58c being 8 or 11 counts as blocking (`docs/gameplay.md`, the check at
  0x1ea8c0). It is not the block in step 11.

Other combat functions. The argument column is only what is visible at the call.

| Function | Sites | Argument at the call |
|---|---|---|
| `Creature_hitTargetAtReach` 0x1196e8 | cos 0x119740, sin 0x119758 | cosine: `lh` of facing +0x38 is the instruction before the `jal` |
| `creature_isBlockedBy` 0x10d2a8 | cos 0x10d300, sin 0x10d30c | both take facing +0x38. This is a collision test, not the damage block |
| `creature_allyInLineOfFire` 0x10d5e8 | cos 0x10d6cc, sin 0x10d6dc | cosine takes `s0` after an arithmetic `>> 16` |
| `Creature_applyKnockback` 0x115eb8 | cos 0x115f54, sin 0x115f64 | both take the halfword at +0x2e0, the knockback heading (the `lh` is the instruction before each `jal`) |
| `Player_takeDamage` 0x1b5330 | cos 0x1b5544, sin 0x1b5550 | facing +0x38 |
| `Player_findTarget` 0x1bb3c8 | cos 0x1bb410, sin 0x1bb41c | facing +0x38. The 60° cone is the existing symbol note; the cone test itself was not re-derived |
| `Player_blockSparks` 0x1b9658 | cos 0x1b97dc, sin 0x1b9800 | **Unknown.** Neither delay slot writes `a0`, and neither previous instruction does |
| `MissileTrap_run` 0x1f3a90 | 0x1f3af0/0x1f3afc, 0x1f3bb0/0x1f3bbc | the second of the first pair takes facing +0x38 of `s1`. The second pair takes `s0` |
| `Shooter_run` 0x1f4ad8 | 0x1f4e70/0x1f4e84, sin 0x1f4ef8, sin 0x1f4f28, sin 0x1f5060, and 0x1f4eec, 0x1f4f14, 0x1f4ffc/0x1f5008, 0x1f504c | the first pair and the sines at 0x1f4ef8 and 0x1f5060 take facing +0x38. The pair at 0x1f4ffc takes `s0`. The cosine delay slots at 0x1f4eec, 0x1f4f14 and 0x1f504c do not write `a0` |
| `Creature_processDamage` 0x110d30 | 0x110e60/0x110e80, 0x11110c/0x11111c, 0x111b44/0x111b64, 0x111ce4/0x111d04 | the first cosine's delay slot adds 0x7fff to `a0`. The sine at 0x11111c takes facing +0x38. The cosines at 0x111b44 and 0x111ce4 add `s0` after an arithmetic `>> 16`. The four formulas were not reduced |

Shots that only rotate a matrix, or that call the sine from draw code:

- `playerProjectile_draw` 0x1ba730: `mat34_rotateAxis` at 0x1ba798, 0x1ba7ac, 0x1ba7f0.
- `MissileWeapon_draw` 0x15253c: `mat34_rotateAxis` at 0x1525bc, and sin only at 0x152984
  (the delay slot does not write `a0`).
- `MissileWeapon_onTouch` 0x152a18: `mat3_rotateAxis` at 0x152de4.
- `WaveMaker_knockbackAndFoam` 0x15fef4: `mat3_rotateAxis` at 0x15ffd0 and 0x1604dc.
  The knockback angle it writes is +0x2e0 (the symbol note); that store is not itself a
  cosine call.

### 5.4 Same routines, outside the hit and the effect spawn

These call the same two functions. The formulas were not re-derived. The address is the
`jal`. "facing" means the delay slot or the previous instruction is `lh` of +0x38.

Creature draw and steering: `creature_drawPropLight` 0x10ab18 (0x10abe8, 0x10abf4,
0x10ac08, 0x10ac3c); `Creature_draw` 0x10b048 (cos 0x10b0bc facing; sin 0x10b0d8,
0x10b278 `<< 10`, 0x10b440 `<< 10`); `creature_findClearHeading` 0x10eaa8 (five pairs,
0x10eb98 through 0x10edc4); `Creature_spawnScavenger` 0x1125e0 (two pairs);
`Creature_run` 0x112948 (0x112e74/0x112e90 facing, 0x11301c/0x113028);
`Creature_moveToTarget` 0x1143e8, `Creature_moveTo` 0x114510, `Creature_moveToDirect`
0x1155e0, `Creature_fleeFrom` 0x115910, `Creature_stepAnim` 0x1162b0 (sin delay slot
subtracts 16384), `Creature_interact` 0x116bd8, `Creature_interactPrompt` 0x116d50,
`Creature_getVisualPos` 0x118738 (facing), `creature_probeHeading` 0x1194d8. The
function at 0x10e720 (five pairs) and the function at 0x114da0 (four pairs, one of them
facing) have no symbol; their role is **Unknown**.

Player movement and draw, mixed with the combat sites already listed: `Player_draw`
0x1a46c0 (four sines, three of them `<< 10`, plus one `mat34_rotateAxis` at 0x1a4b94);
`Player_run` 0x1a5030 (0x1a68e8/0x1a6904, 0x1a846c/0x1a8478, 0x1a8cec/0x1a8d00,
0x1a8e38/0x1a8e44, 0x1a9390/0x1a93a4, 0x1aa26c/0x1aa278 facing, 0x1ac210/0x1ac224,
0x1ac51c/0x1ac534 facing, sin 0x1ac584); `Player_move` 0x1b4020 (several, including
`+0x4000` and facing); `Player_animStep` 0x1b9520 (0x1b95f4/0x1b9604, delay slot
subtracts 16384 from the facing loaded just before); `Player_drawMarker` 0x1bbff8
(sin 0x1bc11c, sin 0x1bc230, cos 0x1bc240).

Object draw, sine only: `PhProp_draw` 0x156db4 at 0x156eac; `UserParamProp_draw`
0x157530 at 0x1575b4; `ItemProp_draw` 0x15991c at 0x1599b8.

Not effects: `Camera_setupDialogView` 0x203bb8, `Camera_updateOrbit` 0x206fd8,
`Camera_apply` 0x2035c8 (`mat34_rotateAxis`), `Camera_followCollide` 0x204fe0
(`mat3_rotateAxis`). Also in this scan and not part of the effect or combat lists:
`Weather_run`, the HUD drawers, the inventory model, `cut_evalCamera`, `cut_runFrame`,
`cut_anchorToWorld`, and the script built-ins `script_cos1000` 0x141fe0 /
`script_sin1000` 0x141fb0 (the argument is the script slot, `lw` of `a1+4`).

### 5.5 The rest of the executable

Outside the creature, object, player and effect ranges above, 210 functions make 393
cosine calls and 463 sine calls. Those are the skill files, the monster files, and the
remaining UI. The skill references (`tools/ref_fx_skills.py`, `tools/ref_skills_a.py`,
`tools/ref_skills_b.py`, `tools/ref_skills_c.py`, `tools/ref_fx_recipes.py`) already call
`ref_core.cos16` / `sin16`, which is this polynomial. Their results do not move when a
host cosine is replaced, because they do not use one. Per-site formulas in the skill
files were not re-derived in this pass.

## 6. Inlined copies

**Observed.** The immediate pair 0x3849 / 0x0fda is formed at 0x163a30, 0x163ba0,
0x163d28, 0x166668 and 0x16671c only. The first three sit in `mat3_setRotZ` 0x1639d8,
`mat34_setPosRotZ` 0x163b30 and `mat34_setPosRotZScale` 0x163cb8. They are the same
polynomial with the same grouping, not extra callers. core.md section 4 already says so.

## 7. Where a research reference uses the host cosine

A search of `tools/ref_*.py` finds one `math.cos` / `math.sin`. It is
`tools/ref_particles.py` `_cs`, used by `rotate_axis` and by the yaw offset inside
`emitter_run`. Everything else that names `cos16` or `sin16` calls the polynomial:
`ref_core`, the copy in `ref_combat` (compared equal on all 65,536 angles), `ref_trig`,
`ref_decals`, `ref_fx_render`, `ref_fx_recipes`, `ref_fx_skills` and the three skill
references. `_cs` was left as it is. The existing emitter difftest allows a relative gap
of a few 10⁻⁵ for that reason (effects.md 16.1; the particle difftest's own note says
4×10⁻⁵).

`_cs` is host float64 sine and cosine, and the multiplies after it are Python floats.
That is a second gap, past the polynomial. Replacing `_cs` with `math_sin16` /
`math_cos16` changes these results and not the schedule:

- Yaw 0, offset x = 100, box 0, velocity 0. The host sine of 0 is +0, so the position
  is (100, 0, 0). `cos16(0)` is 1 either way, so x stays 100. `sin16(0)` is +2⁻²², so
  the original y is `−100 × 2⁻²²`. `rec.on`, `rec.next` and the rate do not read the
  angle.
- A zero velocity stays zero: every term is multiplied by the velocity. A non-zero
  velocity is rotated by the spin and the tilt, so its x and y change on every angle
  whose sine or cosine bits differ (section 3).
- `rotate_axis` of the identity about Z by angle 0 is the identity under the host sine.
  Under the polynomial the off-diagonal entries are ±2⁻²² (section 3). The box matrix
  and the velocity matrix both go through `rotate_axis`.

The haze integers are not computed by `ref_particles`. Building them with this host's
`math.sin` / `math.cos`, times 5, truncated, matches all 64 pairs (section 4). That is
not true of the float emitter path.

`tools/difftest_*.py` also calls `math.cos` / `math.sin`, to build a camera ray or a
random heading. Those are inputs to a test, not a model of `math_cos16`. The lighting,
world, render and skill difftests compare the original function with a reference that
does not use that cosine. Changing those calls would change the scene, not close a gap
against the polynomial.

## 8. Not established

- The last bit of the adds on a console. The four interpreter models disagree with each
  other on thousands of angles (section 2). The match is model against model.
- The angle into `Player_blockSparks`, the four formulas in `Creature_processDamage`,
  and the role of the unnamed functions at 0x10e720 and 0x114da0.
- Whether `particle_drawHaze` is reached only for kind 3.
- Which screen axis receives the haze sine word and which the cosine word.
- Per-site formulas for the skill and monster call sites in section 5.5.
