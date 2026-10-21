# The held Soul's attach matrices: creature_getAttachMatrix0, model_getAttachWorldMatrix, model_getAttachMatrix

US `SLUS_209.73` v2.00. Prose of `tools/ref_attach_matrix.py`. The comparison is
`tools/difftest_attach_matrix.py`; the synthetic tests are `tools/test_ref_attach_matrix.py`.
Written 2026-10-21.

Evidence words as in `CONTRIBUTING.md`. **Executed**: the original ran in `tools/ee_emu.py`
and the model agreed on the calls to everything outside the models (in order, with
arguments), every byte stored outside the stack, the shared seed `0x404464` with its draw
count, the cosmetic seed `0x404460` (part 1), and the result. **Observed**: read at the
address. Nothing here ran on a console, in PCSX2 or on the live rig.

## 1. Why

`Soul_run` state 0x1d (a Soul held by its Minion, bursting) was executed in
`docs/spec/soul-run.md` §3.3 with its two matrix sources as recording stubs that wrote 12
scripted floats. Those two bodies, `creature_getAttachMatrix0` `0x287940` and
`model_getAttachMatrix` `0x1795f8`, and `model_getAttachWorldMatrix` `0x175330` under the
first, had no executed body anywhere. This document executes all three, with
`anim_getJointMatrix` `0x16f720` (executed in `docs/spec/animation.md` §8.4) real under them,
and then runs `Soul_run` state 0x1d with both matrices real.

## 2. How it was run, figures and coverage

**Part 1, the bodies alone.** Real: the four bodies above and `tools/ref_core.py`'s
`mat34_setIdentity` `0x165680`, `mat34_mul` `0x162808`, `mat3_scale` `0x165cc0` and
`mat34_setPosRotZScale` `0x163cb8` (executed by `tools/difftest_core.py`). The one stub is
`anim_buildPose` `0x16ed40` (executed by `tools/difftest_anim.py`): the script may attach a
pose buffer to the state it is given, or leave none. Entries:

- **joint**: `anim_getJointMatrix` on states with a pose or none (then the builder may attach
  one, or the default pose `0x7b8380` is read, zero-filled or not); joints below 0, inside,
  past the end; poses of 0, 1, 4, 20, 24 and −5 joints.
- **attach**: `model_getAttachMatrix` with attach headers (`u8 model+0x22`) 2, 3, 4, 6;
  indexes 0–3 and −1; joint words of any size; with and without a state; scales 1, 0.5,
  1.3, 2, 0.01, −1, 0 and random.
- **world**: `model_getAttachWorldMatrix`, the same, plus positions up to ±4000 and facings
  of every width (16-bit, sign-extended, any 32-bit word).
- **creature**: `creature_getAttachMatrix0` on creatures whose class definition, scale,
  position, facing and anim state vary.

**Part 2, the held Soul.** `tools/difftest_soul_run.py`'s rig and world with the two
call-outs of state 0x1d made real (and `anim_buildPose` stubbed as in part 1). The owner
(`world.others[1]`, the Minion's place) gets a class definition with a model carrying
attach records, a scale, a facing and an anim state with or without a pose. The Soul class
definition's held model `+0x1c` is pointed at a real block with attach records (the rig's
fake `0xc00080` is not mapped). The Soul's own anim state has a pose or none. The driver
keeps the soul in 0x1d with its owner 80% of the ticks (owner handle cleared one time in
ten) and answers the animation step with event bit 0 half the time. The model is
`ref_attach_matrix.SoulModel` (`ref_soul_run.Model` with the two call-outs as bodies).

    python3 -u tools/difftest_attach_matrix.py -v                 # seed 20973
    python3 -u tools/difftest_attach_matrix.py -v --seed 7
    python3 -m unittest tools.test_ref_attach_matrix

| | Seed 20973 | Seed 7 |
|---|---|---|
| Part 1 cases (joint, attach, world, creature) | 3,000 each | 3,000 each |
| Part 2 calls (`Soul_ctor`, `Soul_run`) | 369, 3,000 | 350, 2,999 |
| `Soul_run` entered in state 0x1d | 2,817 | 2,822 |
| `creature_getAttachMatrix0` / `model_getAttachMatrix` runs inside it | 834 / 834 | 842 / 842 |
| Mismatches (calls, writes, seed, result, faults) | 0 | 0 |
| Shared or cosmetic draws by the four bodies | 0 | 0 |

| Function | Address | Instructions executed (both seeds) |
|---|---|---|
| `creature_getAttachMatrix0` | `0x287940`–`0x287994` | 22 of 22 |
| `model_getAttachWorldMatrix` | `0x175330`–`0x17549c` | 91 of 92 |
| `model_getAttachMatrix` | `0x1795f8`–`0x1796d8` | 57 of 57 |
| `anim_getJointMatrix` | `0x16f720`–`0x16f87c` | 88 of 88 |

The one instruction never executed is `0x1753c4`, a `nop` after the delay slot of the
unconditional branch at `0x1753bc`; no branch targets it (dead padding, by reading).

**Check.** Changing the model's facing bias `0x4000` → `0x4001` (`--quick`): `world` 243 of
300 and `creature` 245 of 300 cases mismatch on the stored matrix, and 29 of 337 part-2
calls mismatch on the `particle_spawn` points. Restored; 0 mismatches again.

## 3. The bodies

Matrices are 12 floats in `tools/ref_core.py`'s row-vector layout: words 0–8 the rotation
rows, words 9–11 the translation; a point is `v·M + t`.

An **attach record** is `model + 16·u8(model+0x22) + 0x34·index` (32-bit wrap; the index is
not range-checked, so −1 reads the 0x34 bytes before record 0). Its word `+0` is the joint;
`+4`..`+0x33` is a mat34, the attach frame relative to that joint. (`model_getAttachPoint`
`0x1754a0` reads the same record: its "origin" `+0x28` is this matrix's translation row and
its "direction" `+0x10` the rotation's second row; `docs/spec/animation.md` §8.5.)

### 3.1 anim_getJointMatrix `0x16f720` (state, joint, out) — re-executed here

`docs/spec/animation.md` §8.4, confirmed on raw memory:

1. `buf` = the state's word `+0` (the attached pose). When 0: `anim_buildPose(state, 0)`
   (`0x16f744`) and the word is read again; still 0: the default pose `0x7b8380`
   (`0x16f75c`/`0x16f760`).
2. The joint is a signed word; below 0 → 0 (`slti`/`movz` at `0x16f770`/`0x16f778`). Then
   `last = s16 buf+8 − 1`; above `last` → `last` (`0x16f794`/`0x16f79c`). A pose with no
   joints therefore reads joint −1, the 0x18 bytes before its first joint.
3. With `p = buf + 0x18·joint + 0x10` (three rows of four s16):
   `out[3r+k] = float(s16 p[8k+2r]) · 1/4096` (`0x39800000`, `0x16f77c`) and
   `out[9+k] = float(s16 p[8k+6]) · 1/64` (`0x3c800000`, `0x16f814`).

Reads the state word, the pose's joint count `+8` and 24 bytes of one joint. Writes only
`out`. No draw.

### 3.2 model_getAttachMatrix `0x1795f8` (f12 scale, a0 model, a1 state or 0, a2 index, a3 out)

1. `rec` = the attach record (`0x179638`–`0x17964c`).
2. `J` = `anim_getJointMatrix(state, word rec+0)` into the stack (`0x179658`), or
   `mat34_setIdentity` without a state (branch `0x179648`, call `0x179668`).
3. `out = mat34_mul(rec+4, J)` (`0x17968c`).
4. `S = mat34_setIdentity`, `mat3_scale(scale, S)` (`0x179698`, `0x1796a4`),
   `out = mat34_mul(out, S)` (`0x1796b4`): rotation and translation both times the scale.

The model-space frame of attach point `index`; no position or facing. Reads `u8 model+0x22`
and the record. Writes only `out`. No draw.

### 3.3 model_getAttachWorldMatrix `0x175330` (f12 scale, a0 model, a1 pos, a2 facing, a3 state or 0, t0 index, t1 out)

1. A copy of `pos` (`0x17536c`–`0x175384`); the facing narrowed to s16 (`0x175334`,
   `0x175350`).
2. `rec`, `J` and `out = mat34_mul(rec+4, J)` as §3.2 (`0x1753b4`, `0x1753d0`, `0x1753f4`).
3. `inv = 1.0 / scale` (`div.s`, 1.0 = `0x3f800000` at `0x1753fc`), and the nine rotation
   words of `out` times `inv` (loop of three rows, `0x175418`–`0x175444`). The translation is
   not divided.
4. `R = mat34_setPosRotZScale(scale, copy of pos, s16(facing + 0x4000))` (`0x175448`,
   `0x175460`), and `out = mat34_mul(out, R)` (`0x175470`).

So the world frame's rotation is the attach frame's, unscaled (1/scale then scale), turned by
the facing; its translation is the attach offset scaled, turned and placed at `pos`. Scale 0
(a division by zero) was among the cases; the original and the model agreed on it. Writes
only `out`. No draw.

### 3.4 creature_getAttachMatrix0 `0x287940` (creature, out)

`model_getAttachWorldMatrix(scale +0xdc, model = (+0x24 class definition)+0xc, copy of the
position +0x10..+0x18, facing s16 +0x38, anim state +0x114, index 0, out)`
(`0x287958`–`0x287988`). Reads `+0x24` → `+0xc`, `+0xdc`, `+0x10`–`+0x18`, `+0x38`, and
through §3.1 the state word `+0x114`. Writes only `out`. No draw.

*Inferred* (algebra, not executed): its translation row equals, up to float rounding, the
point `model_getAttachPoint(scale, model, pos, facing, +0x114, 0)` returns: both are
`(−p.x·sin f − p.y·cos f, p.x·cos f − p.y·sin f, p.z)·scale + pos` with `p` the record's
translation through the joint.

## 4. What the held Soul does with the matrix

**State 0x1d of `Soul_run` (`0x2aa6a4`–`0x2aa8cc`), Executed (part 2):** on event bit 0, for
every sample point `i < n` of the held model:

1. the point from `model_getSamplePoint(..., (0, 0, 0), −0x4000, i)`;
2. while the owner handle `+0x3c8` is set: `A = creature_getAttachMatrix0(owner)`,
   `B = model_getAttachMatrix(class block +0x1c, soul +0x114, 0; 1.0)` (1.0 at `0x2aa758`),
   `A' = mat34_mul(mat34_invert(B), A)`, and the point is `mat34_transformPoint(A', point)`;
   that is, the held model is placed so that its attach point 0 sits on the owner's attach
   point 0;
3. two particles at that point, each a unit-ball velocity from **own** draws of the soul's
   generator `+0x44` (three draws a try), `particle_spawn(0x8e4600, point, velocity; 0.0)`.

Then object flag 2 and `obj_delete(soul)`.

- **No position or facing write.** The matrix only places particles. The model writes
  nothing else in this arm (the soul's `+0x44` by its draws, `+0xc` |= 2), and the original
  agreed with it on every byte stored outside the stack in every part-2 call, 834 + 842 of
  them with the matrices running.
- **No shared or cosmetic seed draw** by the matrices or by the arm itself (the shared
  seed and its draw count were compared on every call). The only generator moved is the
  soul's own `+0x44`. `particle_spawn` `0x18f3f8`–`0x18f6dc` (a service here) forms the
  address of neither `0x404460` nor `0x404464` and calls only `0x195b58` and `0x195bb0`
  (Observed, by a scan of its instructions).
- Where the held soul's simulation position comes from: **`Minion_run`**, not the soul.
  Each Minion tick, while `+0x3c8` holds a soul, `model_getAttachPoint(scale +0xdc, the
  Minion's model, its position, facing, +0x114, index 0, out, dir out)` (`0x2863a8`), the
  soul's `+0x10`–`+0x18` = that point (`0x2863c4`–`0x2863cc`), its facing `+0x38` = the
  Minion's (`0x2863e0`), and `obj_updateGridCell(soul)` (`0x2863dc`) (Observed, not
  executed). `Soul_run` makes no move while owned (`docs/spec/soul-run.md` §3, prologue
  step 5).
- The same matrix pair is built by `Soul_draw` `0x2a96a4`–`0x2a96e4` (to draw the held model,
  `0x1779b0`) and by `Soul_setState`'s owner branch of 0x21 `0x2ab0d8`–`0x2ab128` (the same
  burst). Neither was executed here.

## 5. Constants (Observed)

| Value | Use | Address |
|---|---|---|
| 0x34 | attach record size | `0x175390`–`0x1753ac`, `0x17960c`–`0x179640` |
| 16 | header unit (`u8 model+0x22` × 16) | `0x175380`, `0x179644` |
| 1.0 `0x3f800000` | numerator of the reciprocal scale | `0x1753fc` |
| 0x4000 | facing bias of the world turn | `0x175448` |
| 0 | attach index of `creature_getAttachMatrix0` | `0x287988` |
| `0x7b8380` | default pose | `0x16f75c`/`0x16f760` |
| 1/4096 `0x39800000`, 1/64 `0x3c800000` | pose rotation, translation | `0x16f77c`, `0x16f814` |
| 1.0 | scale `Soul_run` passes to `model_getAttachMatrix` | `0x2aa758` |

## 6. Corrections

- `symbols/monsters2.tsv`, `0x287940`: "classDef+0xc" is the class definition at `+0x24`,
  then its `+0xc`; executed now.
- `symbols/engine.tsv`, `0x1795f8` `model_getAttachMatrix`: the result is
  `rec·J·scale` in model space (no position, no facing); executed now.
- `docs/spec/soul-run.md` §6 lists both matrices as not executed; they are executed here,
  inside state 0x1d too.

## 7. Still not executed

- `Soul_draw` `0x2a9678` and `Soul_setState`'s owner branch of 0x21 (`0x2ab0d4`–), the two
  other users of the pair.
- `Minion_run`'s placement of the held soul (`0x286364`–`0x2863e0`), and therefore the
  ordering of the Minion's placement against the soul's tick: *Unknown*.
- `anim_buildPose` `0x16ed40` is a stub here (executed in `tools/difftest_anim.py`).
- `particle_spawn` `0x18f3f8`, `model_getSamplePoint` `0x178e18`,
  `model_getSamplePointCount` `0x1799c8`, `obj_delete` `0x14f200`: services, as in
  `docs/spec/soul-run.md`.
