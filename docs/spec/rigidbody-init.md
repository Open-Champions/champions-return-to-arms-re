# Rigid-body initialisation: `rigidbody_init`, `rigidbody_updateDerived` and the quaternion pair

US `SLUS_209.73` v2.00. Prose of `tools/ref_rigidbody.py`. The comparison is
`tools/difftest_rigidbody.py`; the synthetic tests are `tools/test_ref_rigidbody.py`.
Written 2026-10-21 (research round 5, item 1). Evidence words as in `CONTRIBUTING.md`:
**Executed** means the original ran in `tools/ee_emu.py` and the model agreed on every byte
stored outside the stack and on the seeds; **Observed** means read at the address.

Why: the native port runs a prop's constructor chain with `rigidbody_init`, `quat_fromMat3` and
`rigidbody_updateDerived` as recording services, so a built prop's body is all zero and
`PhProp_run` / `GutChunk_run` cannot be enabled in the World without changing rest timing
(`docs/spec/phprop-run.md` §13, `docs/spec/full-placement.md` §7.6). These bodies were never
compared before; they are now. This document is the contract that replaces the recordings.

## 1. The body

The rigid body is `0x98` bytes; a `PhProp` keeps it at `+0x190` (a `GutChunk` too, it is a
PhProp underneath). Offsets below are within the body (add `0x190` for the prop).

| Body offset | Prop offset | Meaning | Written by |
|---|---|---|---|
| `0x00` | `0x190` | inverse mass | init |
| `0x04`, `0x08`, `0x0c` | `0x194`..`0x19c` | inverse inertia about body x, y, z | init (`PhProp_initPhysics` may zero them afterwards for launch bit `0x1000`) |
| `0x10`..`0x18` | `0x1a0`..`0x1a8` | position | init clears; the owner sets it |
| `0x1c`..`0x28` | `0x1ac`..`0x1b8` | orientation x, y, z, w | init, then the owner's `quat_fromMat3`; both normalise |
| `0x2c`..`0x34` | `0x1bc`..`0x1c4` | linear momentum | init clears; owner sets |
| `0x38`..`0x40` | `0x1c8`..`0x1d0` | angular momentum | init clears; owner sets |
| `0x44`..`0x64` | `0x1d4`..`0x1f4` | rotation matrix (3×3, row-major; the transpose of the orientation's matrix) | init, `updateDerived`, `rigidbody_integrate` |
| `0x68`..`0x88` | `0x1f8`..`0x218` | inverse inertia in the world (3×3) | `updateDerived`, `integrate` (init leaves 0) |
| `0x8c`..`0x94` | `0x21c`..`0x224` | angular velocity | init (zero), `updateDerived`, `integrate` |

## 2. `rigidbody_init` `0x1682f0` (body; f12 mass, f13 factor, f14 size x, f15 size y, f16 size z)

*Executed*: 3,000 cases per seed (20973 and 7), 0 mismatches; **140 of 140** instructions.
The inputs were dirty blocks (30 % random words, the rest floats), masses 0.25–8, factors
0.5–3, box sizes of both signs and zero (a zero size divides by zero on the R5900, which both
sides answer alike).

Order of events (instruction addresses in brackets):

1. Four registers are saved into squares: `sx²` `sy²` `sz²` (`0x168310`–`0x168320`).
2. `memset(body, 0, 0x98)` (`addiu a2, 0x98` at `0x1682f4`, call `libc_memset` `0x3b60c0` at
   `0x168344`). The whole body is cleared, so nothing the caller left survives.
3. `M = factor × mass` (`0x168354`). Inertias `about_x = M (sy² + sz²)`, `about_y = M (sx² + sz²)`,
   `about_z = M (sx² + sy²)` (`0x16835c`–`0x168394`).
4. **One cosmetic draw.** The generator is `0x404460` (loaded at `0x168358`, stored at
   `0x1683fc`): `seed = seed × 0x19660d + 0x3c6ef35f` mod 2³² (multiplier `lui 0x19` at
   `0x168360` + `ori 0x660d` at `0x16836c`, the R5900 three-operand `mult` at `0x168370`;
   addend `lui 0x3c6e` at `0x16839c` + `ori 0xf35f` at `0x1683a0`, `addu` at `0x1683a4`). The
   draw is `u = float(seed >> 16) × 2⁻¹⁶` (`srl` `0x1683b4`, `cvt.s.w` `0x1683c0`, scale `lui
   0x3780` at `0x16838c`), so `u` is in [0, 1). **The shared seed `0x404464` is never touched.**
5. Stores: `body[0x24]` = 1.0 (`lui 0x3f80`, `0x168398`); `body[0x28]` = `u` (`0x168404`);
   `body[0x00]` = `1.0 / mass` (`div.s` `0x1683b0`, store `0x1683d4`); `body[0x04]` =
   `12.0 / about_x` (store `0x1683e4`), `body[0x0c]` = `12.0 / about_z` (`0x1683f4`),
   `body[0x08]` = `12.0 / about_y` (`0x1683f8`). The constant 12.0 is `lui 0x4140` at `0x168380`
   (the box's `12 / (M (b² + c²))`). The orientation is therefore `(0, 0, 1, u)`.
6. `quat_normalize(body + 0x1c)` (`0x168400`); `body[0x38]`, `[0x3c]`, `[0x40]` stored as 0
   again (`0x168408`–`0x168418`); `quat_normalize` once more (`0x168414`). The second pass is
   not a no-op: it can move the last bit.
7. `body[0x44..0x64]` = the rotation matrix of the normalised quaternion, transposed; the
   scale 2.0 is `lui 0x4000` at `0x168444`, the identity terms use 1.0 from `0x168374`; stores
   at `0x1684bc`–`0x1684f0`. The products are `component × (other × s)` as in
   `mat3_fromQuat` `0x1668b8` (`ref_core.mat3_from_quat`).
8. `mat3_mulVecTransposed(body + 0x8c, body + 0x68, body + 0x38)` (`0x1684ec`): both inputs
   are zero here, so the angular velocity is zero.

Reads: the five arguments, the cosmetic seed, `body[0x1c..0x28]` (after step 5) and
`body[0x38..0x40]`, `body[0x68..0x88]` (zeros after step 2). Writes: `body[0x00..0x97]` and
`0x404460`. Calls: `libc_memset`, `quat_normalize` ×2, `mat3_mulVecTransposed`; no allocation.

Callers (all *Observed*): `PhProp_initPhysics` `0x155110` at `0x1551f0` (mass 1.0, factor 1.0,
sizes = the model bounds × the prop's scale `+0x240`); `PushPhysicsProp_loadState` `0x15dbd4` at
`0x15dc94` and `PushPhysicsProp_ctorCrate` `0x15dddc` at `0x15dec0` (mass 1.0, factor 1.0, all
three sizes `2 × (obj + 0x100)`; `0x3f999999` = 1.2 at `0x15dc60` / `0x15de84` scales `+0x1c`).

## 3. `rigidbody_updateDerived` `0x167a58` (body)

*Executed*: 3,000 cases per seed, 0 mismatches; **111 of 111** instructions. Orientations were
unnormalised, tiny (1e-3), huge (1e4), identity, and all-zero; the inertia entries and angular
momentum of both signs.

1. `quat_normalize(body + 0x1c)` in place (`0x167a7c`).
2. The rotation matrix of the normalised quaternion is stored transposed at `body[0x44..0x64]`
   (`0x167b2c`–`0x167b5c`; 2.0 `lui 0x4000` `0x167aa8`; 1.0 `lui 0x3f80` `0x167ab4`).
3. `M[row][col] = R[row][col] × inertia[col]` (reads `body[0x04]`, `[0x08]`, `[0x0c]` and the matrix
   just stored, `0x167b60`–`0x167bb0`), `mat3_transpose` of `R` into a temporary
   (`0x167bd0`), `body[0x68..0x88]` = `mat3_mul(M, R^T)` (`0x167be0`).
4. `body[0x8c..0x94]` = `mat3_mulVecTransposed(body[0x68..], angular momentum body[0x38..])`
   (`0x167bf0`).

Reads: `body[0x04..0x0c]`, `[0x1c..0x28]`, `[0x38..0x40]`. Writes: `[0x1c..0x28]` (normalised),
`[0x44..0x94]`. No seed draw, no service. Callers: `PhProp_initPhysics` at `0x155320` and
`PushPhysicsProp_loadState` at `0x15dd34`. The `rigidbody_integrate` tail
(`docs/spec/phprop-run.md` §3) is the same formula; `ref_phprop_run.Model.derive` is shared.

## 4. `quat_fromMat3` `0x164330` and `quat_normalize` `0x166550`

Already executed by `tools/difftest_core.py` (4,000 and 2,500 cases) and re-run here under the
composed chain; `tools/ref_core.py` holds the contract (`quat_from_mat3`, `quat_normalize`).
The difftest above reaches **146 of 146** and **25 of 25** instructions of the two bodies,
including the diagonal-branch arm.

## 5. The composed check: `PhProp_initPhysics` with all four bodies real

`difftest_rigidbody` also runs `PhProp_initPhysics` `0x155110` on `difftest_phprop`'s blocks with
`rigidbody_init`, `quat_fromMat3`, `quat_normalize` and `rigidbody_updateDerived` real instead
of recording stubs (with `mat3_transpose` `0x166298`, `mat3_mul` `0x165710`,
`mat3_mulVecTransposed` `0x165da0` under them), `+0x110` holding a random rotation, a perturbed
one, the identity or random floats. The model is `ref_phprop.Model` with
`ref_rigidbody.RigidMixin`. *Executed*: 1,000 cases per seed, 0 mismatches, the calls to the
remaining stubs, every stored byte (the whole body included) and both seeds equal.

Consequences for a port (*Executed* unless marked):

- **What survives `PhProp_initPhysics`.** `rigidbody_init` leaves its draw only in the cosmetic
  seed and its inertia in `body[0x04..0x0c]` and `body[0x00]`; the orientation it drew is
  **overwritten** by `quat_fromMat3(+0x1ac, +0x110)` (the prop's facing matrix), and `[0x44..]`
  by `updateDerived`. A mutation that corrupted the draw's scale (>> 15 for >> 16) was caught by
  `init` and not by the composed entry, as expected. For a `PhProp` the draw therefore
  matters only through the cosmetic seed `0x404460`, which the draw advances once.
- **The crate keeps the drawn orientation** (`PushPhysicsProp_ctorCrate` writes only the position
  afterwards, *Observed* `docs/issues/rescan.md` R4); its rotation is a turn about z of
  `2 atan2(1, u)` (between 90 and 180 degrees), from `q = (0, 0, 1, u) / |q|`.
- **A port can replace the three recordings by this contract**: the draw count is one cosmetic
  draw per `rigidbody_init` call (one per PhProp, GutChunk, bone prop and item prop built, and
  one per crate), none for `updateDerived`.
- Everything is exact single-precision R5900 arithmetic (truncating); use `tools/ref_core.py`
  for the operation order, not host `float` maths.

## 6. Checks of the comparison itself

Run on 150 cases each, model restored after each:

| Mutation | Result |
|---|---|
| `about_y = M (sx² + sy²)` instead of `(sx² + sz²)` | `init` FAIL 137 / 150, composed FAIL 28 / 50, `derived` pass (as it should) |
| draw scale `seed >> 15` | `init` FAIL 150 / 150 |

Commands:

    PYTHONDONTWRITEBYTECODE=1 python3 -u tools/difftest_rigidbody.py --seed 20973 -v
    PYTHONDONTWRITEBYTECODE=1 python3 -u tools/difftest_rigidbody.py --seed 7 -v
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tools/test_ref_rigidbody.py

| Seed | `init` | `derived` | composed `physics` |
|---|---|---|---|
| 20973 | 3,000 / 0 | 3,000 / 0 | 1,000 / 0 |
| 7 | 3,000 / 0 | 3,000 / 0 | 1,000 / 0 |

(cases / mismatches).

## 7. Not executed here

- `PushPhysicsProp_loadState` and `PushPhysicsProp_ctorCrate` themselves (they call these bodies
  with the arguments of §2; the bodies are the executed part).
- A terrain sweep (`terrain_sweepCircle` `0x185a40`) or any of the world services. Those are
  answered by the host; `phprop-run.md` §12 lists them.
