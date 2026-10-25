# The physics prop's frame (PhProp_run) and the gut chunk's frame (GutChunk_run)

US `SLUS_209.73` v2.00. Prose of `tools/ref_phprop_run.py`; the comparison is
`tools/difftest_phprop_run.py`, the synthetic tests `tools/test_ref_phprop_run.py`.
Written 2026-10-21 for item 1 of `docs/spec/full-placement.md` §6.5.

Evidence words as in `CONTRIBUTING.md`. **Executed**: the original ran in `tools/ee_emu.py`
and the model agreed on the calls to everything outside the models (in order, with
arguments; vectors passed by pointer compared by their three words, a stack text buffer by
its text), every byte stored outside the stack, the shared seed `0x404464` with its draw
count, and the cosmetic seed `0x404460` (left alone on both sides). **Observed**: read at
the address. Nothing here ran on a console, in PCSX2 or on the live rig.

## 1. Why

`docs/spec/gut-chunk.md` executed the constructors: a bleeding hit's gut chunk
(`GutChunk_ctor`), a shattered skeleton's bone props (`PhProp_ctor2`), item props
(`PhProp_ctor` with a record). Each of them then runs every frame through its class's slot 4:

| Class | Table | Slot 4 (`+0x24`) | Slot 1 (`+0xc`) |
|---|---|---|---|
| GutChunk | `0x50f3b8` | `GutChunk_run` `0x1edb18` | `GutChunk_dtor` `0x3c4d48` |
| PhProp (bone props, item props, debris) | `0x511ba8` | `PhProp_run` `0x155fcc` | `PhProp_dtor` `0x3c2fc8` |

Observed in the tables. `GutChunk_run` calls `PhProp_run` first (`0x1edb2c`).

`PhProp_run` ends a prop's flight by building a resting `Prop` in its place
(`docs/issues/pose-cache.md` described this from reading). That constructor draws the
**shared** seed. So when a gut chunk or a bone comes to rest is a shared-seed event.

## 2. How it was run

    python3 -u tools/difftest_phprop_run.py --seed 20973 -v
    python3 -u tools/difftest_phprop_run.py --seed 7 -v
    python3 -m unittest tools.test_ref_phprop_run

Real in the interpreter: the ten bodies of §3–§8, and under them `GameObject_ctor`
`0x14cb10`, `GameObject_rand` `0x1509d0`, `item_getResourceIndex` `0x1083f8`, the matrix and
quaternion bodies of `tools/ref_core.py` (`quat_mul` `0x166480`, `quat_normalize`
`0x166550`, `mat3_transpose` `0x166298`, `mat3_mul` `0x165710`, `mat3_mulVecTransposed`
`0x165da0`, `mat3_scale` `0x165cc0`, `mat34_translateLocal` `0x165b10`; executed by
`tools/difftest_core.py`) and the C library. Every other callee is a recording stub (listed in §13).

Five entries:

- **phrun**: `PhProp_run` once on a prop whose every field the body reads is set by the
  generator. The prop is either still or moving, near the ground or not. Its orientation is
  a unit quaternion with its matrix, or a random matrix. Its life is around 0 and −220, its
  part masks are 0, single bits, bit 63 or all bits. It has an item record (with a fake
  definition) or not. It is in water, burning or neither. The globals are random: the frame,
  the gravity option, the player count, the first alive player and that player's height.
  The services answer randomly (the ground near or far, −10000 or −1000000, the sweep
  blocked part of the way). The pool gives a block or 0.
- **gutrun**: `GutChunk_run` once, likewise. The chunk fields are set as well: bits
  `+0x248`, last vertical speed `+0x24c` around −1 and −2, counter `+0x25c`, byte `+0x260`.
  The local option `0x44fdc0` is 0–2.
- **gutLife**, **boneLife**, **propLife**: an object is **built by the real constructor**:
  - `GutChunk_ctor` with kinds 0–3 and 7, bits 0–4, 8 and 9, the gore word 0–2;
  - `PhProp_ctor2` with the shatter's launch `0x107` (or `0x216`, `0x19`, `0x8107`,
    `0x2107`);
  - `PhProp_ctor` with launch mixes, with or without an item record.

  The build runs `rigidbody_init`, `quat_fromMat3` and `rigidbody_updateDerived` for real
  too; it is not compared here (`difftest_phprop` compares the constructors). Then the run
  body steps the object **frame after frame**, both in the interpreter and in the model.
  Every frame is compared, and the next frame starts from the interpreter's state. A life
  ends at its delete or destroy, or after 450 frames. The services answer from a fixed
  world: a flat ground, a slope, steps of 40 units or a pit with no ground; sometimes a wall
  the sweep stops at, and water. In some lives the pool refuses, in some the prop burns
  (`+0x23a` = 1 after the build). One player stands at the ground, 50 above it or 150
  above it.

| | Seed 20973 | Seed 7 |
|---|---|---|
| `phrun` cases (shared draws / own draws seen) | 3,000 (746 / 720) | 3,000 (700 / 739) |
| `gutrun` cases (shared / own) | 3,000 (728 / 2,020) | 3,000 (695 / 2,049) |
| `gutLife`: lives, frames compared | 60, 8,681 | 60, 7,012 |
| `boneLife`: lives, frames | 60, 8,378 | 60, 8,564 |
| `propLife`: lives, frames | 60, 10,161 | 60, 10,256 |
| Shared draws inside the lives (rests with a block) | 20 + 34 + 24 | 10 + 27 + 22 |
| Mismatches (calls, stores, shared seed and count, cosmetic seed, one-sided faults) | 0 | 0 |
| Calls to addresses neither real nor stubbed | 0 | 0 |

| Function | Address | Executed (both seeds) | Not executed |
|---|---|---|---|
| `GutChunk_run` | `0x1edb18` | 333 of 333 | |
| `PhProp_run` | `0x155fcc` | 888 of 890 | `0x15629c`, `0x156598` |
| `rigidbody_pointVelocity` | `0x167008` | 70 of 70 | |
| `rigidbody_applyCollisionImpulse` | `0x167408` | 202 of 202 | |
| `rigidbody_integrate` | `0x167730` | 202 of 202 | |
| `rigidbody_addForceAtPoint` | `0x167c18` | 62 of 62 | |
| `model_getHullPoints` | `0x179320` | 13 of 13 | |
| `Prop_ctorNamed` | `0x153ac0` | 114 of 114 | |
| `Prop_ctorRes` | `0x153c88` | 88 of 88 | |
| `ItemProp_ctor3` | `0x1592bc` | 103 of 103 | |

The two idle instructions are delay slots of likely branches that cannot be taken (Inferred).

- `0x15629c`: "the contact point is not under the level" after its height was. Both are the
  same row-2 dot product plus body z, in the same order (`mat3_mulVecTransposed` computes
  row r · v).
- `0x156598`: "the push is not > 0". depth × 0.006 with depth > 0 is 0 only when the
  product flushes to zero.

Unit tests: `tools/test_ref_phprop_run.py`, 25 tests, all pass. The full suite (`python3 -m
unittest discover -s tools -p 'test_*.py'`) gave 1,178 tests, OK.

Mutation checks (`--quick`, seed 20973). Each model change below was detected, and the
model was then restored:

- the push constant `0x3bc49ba5` → `0x3bc49ba6`: phrun 109 of 300, gutrun 115 of 300, and
  5, 7 and 7 of 10 lives failing;
- the life limit −220 → −221: phrun 71 and gutrun 74 of 300 failing (calls, stores, shared
  seed);
- the resting decal's last type 0 → 1: gutrun 11 of 300 failing.

## 3. PhProp_run `0x155fcc` (prop)

*Executed.* `0x155fcc`–`0x156db0`, 890 instructions (`ghidra_funcs.tsv`). The rigid body is
embedded at `+0x190` (the field table is §3.9). In this order:

### 3.1 Water, every eighth frame

When byte `+0x239` (in water) is 0 and `g_simFrame` `0x44fdcc` & 7 = 0:

1. `water_test(g_world 0x44fdc8, copy of the position, 0; 12.0)`. The constant is
   `0x41400000` at `0x156060`.
2. When it answers non-zero:
   - byte `+0x239` = 1;
   - **one own draw**, whose value is not used (`0x15607c`);
   - `libc_sprintf(buffer, 0x532458 (the small-splash sound name format), 1)`. The 1 is a constant
     (`0x15608c`);
   - `res_find(0x532478 "fx.lmp", buffer)`, then `sound_playOnObject(entry, prop; 0.2)`.
     The 0.2 is `0x3e4ccccc` at `0x1560b0`;
   - `water_disturb(g_world, copy of the position; 700.0, 24.0)`. The constants are
     `0x442f0000` at `0x1560cc` and `0x41c00000` at `0x1560ec`.

### 3.2 Gravity and the contact level

- `+0x1c4` (vertical momentum) −= g / `+0x190` (inverse mass). g is 0.18 (`0x3e3851e9`,
  `0x156134`), or 0.054 (`0x3d5d2f18`, `0x156120`) when the word `0x44fe08` has bit `0x100`.
  The order is a division, then a subtraction.
- The contact level is last frame's ground `+0x228` + 2.0 (`0x40000000`, `0x15615c`).
- `+0x230` = 0. The force and torque sums (on the stack) start at 0.

### 3.3 Ground contact, per hull point

For each set bit k of the 64-bit part mask `+0xe8`, lowest first (`dsrl` loop,
`0x156190`–`0x1565d8`), `model_getHullPoints(+0x4c, k)` gives eight points of signed bytes
(§7). For each point:

1. p = (x, y, z) − the centre `+0xf0`/`+0xf4`/`+0xf8`. Each byte goes through `cvt.s.w`,
   then a subtraction.
2. Its height is ((p.x × R20 + p.y × R21) + p.z × R22) + body z `+0x1a8`, with R20–R22 at
   `+0x1ec`–`+0x1f4` (row 2 of the body matrix). A point at or above the contact level is
   skipped (`c.ole`, so a level ≤ height skips).
3. w = `mat3_mulVecTransposed(R +0x1d4, p)` + body position `+0x1a0`.
4. When the countdown `+0x234` is non-zero it is decremented and the point skipped. This
   happens per point, not per frame.
5. A point not under the contact level (w.z < level fails) is skipped.
6. Contact: the frame's contact flag is set. v = `rigidbody_pointVelocity(body, w)`.
   - v.z < −1.0 (`0xbf800000`, `0x1562dc`) and not in water: the landing sound of §3.10, if
     any: `res_find("fx.lmp", name)`, `sound_playOnObject(entry, prop; 1.0)`.
   - v.z < 0: `rigidbody_applyCollisionImpulse(+0x23c; body, w, (0, 0, 1.0))` and `+0x230`
     = 1. `+0x23c` is the restitution PhProp_initPhysics set (−0.4, or −0.1 with launch
     `0x800`).
   - depth = level − w.z, capped at 1.0. The force is depth × 0.006 (`0x3bc49ba5`,
     `0x156580`). When it is > 0, `rigidbody_addForceAtPoint(body, w, (0, 0, force), force
     sum, torque sum)`.

### 3.4 Spin clamp

When the prop bits `+0x140` have `0x20` (launch `0x10000`): for each axis i
(`+0x1c8`/`+0x194`, `+0x1cc`/`+0x198`, `+0x1d0`/`+0x19c`):

- L_i × I_i > 0.05 (`0x3d4ccccc`, `0x1565f8`) makes L_i = 0.05 / I_i;
- then (re-read) L_i × I_i < −0.05 makes L_i = −0.05 / I_i.

### 3.5 Integration and damping

1. `rigidbody_integrate(1.0; body, force sum, torque sum)` (§4).
2. After a contact this frame, the horizontal momentum `+0x1bc`, `+0x1c0` × 0.95
   (`0x3f733333`, `0x156714`).
3. The angular momentum `+0x1d0`, `+0x1c8`, `+0x1cc` × 0.95 every frame.

### 3.6 The move

1. The object position `+0x10`–`+0x18` = the body position `+0x1a0`–`+0x1a8`.
2. Body z `+0x1a8` += `+0x1c4` × inverse mass. The object's z keeps the old value.
3. The horizontal step d = (`+0x1bc` × m, `+0x1c0` × m, 0), with m the inverse mass.
4. ground = `terrain_heightBelow(g_world, copy of the position; radius +0x1c)`. It is stored
   at `+0x228`. When z − 0.01 (`0x3c23d70a`, `0x1567f4`) ≤ ground, z `+0x18` = ground. Only
   the object's z snaps, not the body's.
5. When d.x² + d.y² > 0.001 (`0x3a83126e`, `0x156828`):
   - t = `terrain_sweepCircle(g_world, copy of the position, d, 1, normal out; radius)`;
   - d × t is added to the position, then `obj_updateGridCell`;
   - when t < 1.0: a = 0.001 − (n.x × p.x + n.y × p.y), with p the momentum. When a > 0
     the momentum gains n × a × 1.5 (`0x3fc00000`, `0x156914`), as (n.y × a) × 1.5 then
     the add;
   - a burning prop (signed byte `+0x23a` non-zero):
     `fx_impactPuffNearCamera(body position, rigidbody_pointVelocity(body, position), 0;
     (float) byte +0x28 × 0.8, 1.0)`. The 0.8 is `0x3f4ccccc` at `0x156958`.
6. Body x, y = the object's x, y. Then `obj_updateGridCell` (a second time after a sweep).

### 3.7 Catching fire

When byte `+0x23a` is 1, all of these hold:

- |z − ground| < 12.0 (`0x41400000`, `0x1569b4`);
- each of `+0x1c8`, `+0x1cc`, `+0x1d0`, `+0x1bc`, `+0x1c0` and `+0x1c4` has | | < 0.8.

Then byte `+0x23a` = 2 and `pool_new(0x4ac)`. With a block:

- **one own draw** d;
- `StaticFire_ctor(block, copy of the position, (d % 40) × 60 + 480, 0, 0; 240.0, 0.5)`.
  The `divu` is at `0x156a7c`; the constants are `0x43700000` and `0x3f000000` at
  `0x156aa0` and `0x156aac`.

Only debris an exploding container marks (1 piece in 8, `docs/monsters-2.md`) has
`+0x23a` = 1. No constructor of this page sets it.

### 3.8 Life, rest, and the player-height delete

life is the signed halfword `+0x10e`. Prop_launch set it to 180, or `0x7fff` with launch
`0x8000`.

- When life < −220 (`slti -0xdc`, `0x156ad8`), **rest** at once, without a decrement.
- Otherwise the halfword is decremented. When life (before the decrement) ≤ 0 and each of
  the six momenta has | | < 0.2 (`0x3e4ccccc`, `0x156af4`): **rest**.
- Otherwise: when `g_numPlayers` `0x4d8ae0` > 0, the first entry of `g_alivePlayers`
  `0x4f8440` is ≥ 0, and that player's object (word `0x4dcec8` + slot × `0x4c30`) is
  non-null, the prop is deleted (`obj_delete`) when z + 120.0 (`0x42f00000`, `0x156d4c`) <
  the player's z `+0x18`.

**Rest** (`0x156b74`–`0x156d04`):

1. The matrix `+0x110` is the transpose of the body matrix `+0x1d4`. The translation
   `+0x134`–`+0x13c` is the body position.
2. `mat3_scale(+0x240, +0x110)`, then `mat34_translateLocal(−centre x, −centre y,
   −centre z, +0x110)`.
3. The resting object, by kind:
   - an item prop (signed byte `+0x238` non-zero): `pool_new(0x190)`, then
     `ItemProp_ctor3(block, copy of the position, +0x148, +0x110)` (§8);
   - a lump name (first byte of `+0x54` non-zero): `pool_new(0x148)`, then
     `Prop_ctorNamed(block, copy of the position, +0x54, +0x64, +0xa4, the 64-bit +0xe8, the
     signed +0x140, +0x110)`;
   - otherwise: `pool_new(0x148)`, then `Prop_ctorRes(block, copy of the position, +0x4c,
     +0x50, +0xe8, +0x140, +0x110)`.

   Each constructor is **one shared draw** (`GameObject_ctor`). Without a block there is
   no draw.
4. `obj_delete(prop)`, with or without a block.

### 3.9 Fields of PhProp_run

Body offsets are in brackets. *Executed* for every entry; width 4 unless given.

| Offset | Read / written | Meaning |
|---|---|---|
| `+0x10`–`+0x18` | R/W | position; z snaps to the ground |
| `+0x1c` | R | radius for the terrain services (4.0 from Prop_launch) |
| `+0x28` (1) | R | puff size (GameObject_ctor sets `0x19`) |
| `+0x44` | R/W | own generator (GameObject_rand) |
| `+0x4c` | R | model entry: the hull table |
| `+0x50` | R | texture entry (Prop_ctorRes only) |
| `+0x54`, `+0x64`, `+0xa4` | R | lump, model and texture names (first byte of `+0x54` tested) |
| `+0xe8` (8) | R | part mask: which meshes collide |
| `+0xf0`–`+0xf8` | R | centre of the parts |
| `+0x10e` (2) | R/W | life |
| `+0x110`–`+0x13c` | W | the resting matrix (rest only) |
| `+0x140` (2) | R | prop bits: 8 and `0x10` landing sounds, `0x20` spin clamp |
| `+0x148`, `+0x150` (8) | R | item record: definition (its bytes `+0x1c`, `+0x1d`) and flags |
| `+0x190` [0] | R | inverse mass |
| `+0x194`–`+0x19c` [4] | R | inverse inertia, body axes |
| `+0x1a0`–`+0x1a8` [`0x10`] | R/W | body position |
| `+0x1ac`–`+0x1b8` [`0x1c`] | R/W | orientation quaternion (x, y, z, w) |
| `+0x1bc`–`+0x1c4` [`0x2c`] | R/W | momentum (= velocity per frame; mass 1) |
| `+0x1c8`–`+0x1d0` [`0x38`] | R/W | angular momentum |
| `+0x1d4`–`+0x1f4` [`0x44`] | R/W | rotation matrix |
| `+0x1f8`–`+0x218` [`0x68`] | R/W | world inverse inertia |
| `+0x21c`–`+0x224` [`0x8c`] | R/W | angular velocity |
| `+0x228` | R/W | ground height under the prop (last frame's, then this frame's) |
| `+0x230` | W | 1 when an impulse was applied this frame |
| `+0x234` | R/W | countdown of ignored contact points |
| `+0x238` (1) | R | item prop |
| `+0x239` (1) | R/W | in water |
| `+0x23a` (1) | R/W | 1: catches fire near the ground; 2: has caught |
| `+0x23c` | R | restitution |
| `+0x240` | R | scale (rest matrix) |

Globals read: `g_simFrame` `0x44fdcc`, `g_world` `0x44fdc8`, `0x44fe08`, `g_numPlayers`
`0x4d8ae0`, `g_alivePlayers` `0x4f8440` and the player record's object word `0x4dcec8` +
slot × `0x4c30`.

### 3.10 The landing sound

These are the names in `fx.lmp`.

A plain prop (`+0x238` = 0):

- prop bits 8: `0x5326c0` (wood drop sound);
- else `0x10`: `0x5326d8` (metal drop sound);
- else none.

An item prop, with D the definition `+0x148` and F the flags `+0x150`:

- D byte `+0x1d` = 0:
  - F `0x800000`: wd;
  - else `0x40000`: mtl;
  - else none.
- D byte `+0x1c` = 3: F `0x800000` or `0x40000` gives `0x5326f0` (shield drop sound);
  otherwise none.
- Otherwise the first of these bits that F has picks the sound:
  - `0x800000`: wd;
  - `0x200000`: `0x532708` (chain drop sound);
  - `0x40000`: `0x532720` (second metal drop sound);
  - `0x100000`: `0x532738` (leather drop sound);
  - `0x80000`: `0x532750` (cloth drop sound);
  - `0x1000000`: `0x532768` (potion drop sound);
  - `0x4000000`, `0x2000000` or `0x10000000`: `0x532780` (jewelry drop sound);
  - none of them: no sound.

The name is copied to a stack buffer first.

## 4. rigidbody_integrate `0x167730` (dt; body, force, torque)

*Executed* (202 of 202 instructions). B is the body.

1. Copies of the force and the torque. ω4 = (B`+0x8c`, 0).
2. q̇ = `quat_mul(ω4, q)`, with q at `+0x1c`. Each q_i += q̇_i × (dt × 0.5). The 0.5 is
   `0x3f000000` at `0x1677c4`.
3. Momentum `+0x2c` += force × dt. Angular momentum `+0x38` += torque × dt.
4. `quat_normalize(q)`.
5. R `+0x44` is the **transpose** of the matrix `mat3_fromQuat` would build:
   - s = 2.0 / (((x² + y²) + z²) + w²);
   - every product is component × (other × s).

   The same formula is in `rigidbody_updateDerived` `0x167a58` and `rigidbody_init`.
6. M[r][c] = R[r][c] × I_c, with I the inverse inertia `+4`/`+8`/`+0xc`. The world inverse
   inertia `+0x68` = `mat3_mul(M, mat3_transpose(R))`.
7. ω `+0x8c` = `mat3_mulVecTransposed(+0x68, +0x38)`.

The position is not moved here; `PhProp_run` moves it (§3.6).

## 5. rigidbody_applyCollisionImpulse `0x167408` (e; body, point, normal)

*Executed* (202 of 202).

1. v = `rigidbody_pointVelocity(body, point)`. vn = (v.x n.x + v.y n.y) + v.z n.z.
2. num = vn × e − vn. Nothing more happens when num ≤ 0.
3. r = point − position. c = r × n. u = `mat3_mulVecTransposed(Iw +0x68, c)`. w = u × r.
4. den = inverse mass + ((w.x n.x + w.y n.y) + w.z n.z). j = num / den.
5. Momentum += n × j. Angular momentum += r × (n × j).
6. ω = `mat3_mulVecTransposed(+0x68, +0x38)`.

## 6. rigidbody_pointVelocity `0x167008` and rigidbody_addForceAtPoint `0x167c18`

*Executed* (70 of 70, 62 of 62).

- **pointVelocity**: out = ω × (point − position) + momentum × inverse mass. Each
  component is (ω_a × r_b − ω_b × r_a), then the add.
- **addForceAtPoint**(body, point, F, force sum, torque sum): force sum += F; torque sum +=
  (point − position) × F.

## 7. model_getHullPoints `0x179320` (model, mesh)

*Executed* (13 of 13). When the model header's byte `+0x25` is 0 the result is 0. Otherwise
it is model + that byte × 16 + mesh × 24: eight points of three signed bytes.

`PhProp_run` does not test for 0 (Observed: `0x1561b8` reads through the result). So a
model without a hull table, with a mask bit set, would read from address 0. The difftest's
models always have a table; that case is not executed.

## 8. The resting prop's constructors

*Executed* (all instructions of each). `Prop_ctorNamed` and `ItemProp_ctor3` were also
executed, independently, by `tools/difftest_gold.py` in the same round (`tools/ref_gold.py`).

- **Prop_ctorNamed** `0x153ac0` (obj, position, lump, model, texture; t1 the 64-bit mask, t2
  the bits, t3 the 3×4 matrix):
  1. `GameObject_ctor(obj, copy, 0, 0)`: **ONE SHARED DRAW**.
  2. Table `0x511d58`. Flags `+0xc` |= `0x1809`.
  3. `obj_updateGridCell`.
  4. `+0x140` = bits | 1. Radius `+0x1c` = 4.0.
  5. The 48-byte matrix goes to `+0x110`.
  6. The three names are copied to `+0x54`/`+0x64`/`+0xa4` (`libc_strcpy`). Then
     `+0x4c` = `res_find(+0x54, +0x64)` and `+0x50` = `res_find(+0x54, +0xa4)`.
  7. `+0xe8` = mask.
  8. With bits 2: `obj_runEveryFrame` and flags |= `0x4000`. With bits 4: flags |=
     `0x1000`.
- **Prop_ctorRes** `0x153c88` (obj, position, model entry, texture entry; t0 the mask, t1 the
  bits, t2 the matrix): the same, with these differences:
  - flags |= `0x5809`;
  - the entries are stored as given;
  - no names, no lookups.
- **ItemProp_ctor3** `0x1592bc` (obj, position, item record, matrix):
  1. `item_getResourceIndex(record)` twice, giving rows a and b.
  2. `Prop_ctorNamed(obj, copy, 0x5326b0 "equipmnt.lmp", word 0x3e9ce0 + 16a, word
     0x3e9ce4 + 16b, mask −1 (64-bit), bits 0, matrix)`.
  3. Table `0x511c38`.
  4. The empty item record of `PhProp_ctor` (`gut-chunk.md` §4), then the record's `0x48`
     bytes over it at `+0x148`.
  5. Flags |= `0x102000` and lose `0x1800`. They also lose `0x3000` when `+0x150` has bit 39
     (`0x8000000000`).
  6. `obj_updateGridCell`.

A gut chunk's prop bits have 2 and 4 (launch `0xb41` has `0x100` and `0x200`). A bone's have
2 (launch `0x107`). So both resting props run every frame, through `Prop_run` `0x154514`,
which is not executed (§11).

## 9. GutChunk_run `0x1edb18` (chunk)

*Executed.* `0x1edb18`–`0x1ee04c`, 333 instructions; the word at `0x1edbfc` is an unreachable `nop`
that `ghidra_funcs.tsv` leaves out. The chunk fields come from `GutChunk_ctor` (`combat-round3.md` §2):

| Offset | R/W | Meaning |
|---|---|---|
| `+0x248` | R | bits (word; read as a 64-bit `ld` for the `& 9` test) |
| `+0x24c` | R/W | last frame's vertical momentum |
| `+0x25c` | R/W | bounce counter (2) |
| `+0x260` (1) | R/W | the resting decal is made |
| `+0x48` | R | table; slot 1 (`+8` adjust, `+0xc` body) for the self-destroy |

The bits of `+0x248` are the constructor's `bits`. Bit 0 is forced on when the gore word
`0x44fdc0` is under 2.

- Bit 0: falling decals; the chunk destroys itself on its first bounce.
- Bit 1 (2): particle `0x870408`, decal types 7 / 6.
- Bit 2 (4): particle `0x870458`, decal types 4 / 3. It wins over bit 1.
- Bit 3 (8): no decals.

In this order:

1. `PhProp_run(chunk)`.
2. When `+0x1c4` > 1.0 (`0x1edb38`):
   - **one own draw** d;
   - when d % 3 (`divu`, `0x1edb58`) = 0 and the word `0x44fdc0` is non-zero:
     `particle_spawn(definition, copy of the position, (0, 0, 0); 0.0)`. The definition is
     `0x870458`, `0x870408` or `0x8703b8` by the bits.
   - The draw happens whatever the option, so the own-draw count does not depend on that
     local option (Observed: the test follows the draw).
3. h = `terrain_height(g_world, copy of the position; 8.0)` (`0x41000000`, `0x1edc24`). The
   spot is (x, y, h).
4. **Falling decal**. All of these must hold:
   - bits & 9 = 1;
   - h < z and h > −10000.0 (`0xc61c4000`);
   - the vertical momentum crossed −1 or −2 downward since last frame: (`+0x24c` > −1 and
     `+0x1c4` < −1) or (`+0x24c` > −2 and `+0x1c4` < −2).

   Then **two own draws**: the angle (signed 16 bits), then the type, base + (d & 1) with
   base 4 / 7 / 1. Then `decal_add(spot, angle, type, 0; 12.0)` (`0x41400000`).
5. **Bounce**: last frame's `+0x24c` < 0 and now `+0x1c4` > 0.
   - When `+0x24c` < −1.0: `res_find(0x53e3c0 "fx.lmp", 0x53e4a0 the water-bounce sound)` and
     `sound_playOnObject(entry, chunk; 0.5)`.
   - Bit 0: when the chunk is non-null, slot 1 of its table with argument 3. For a gut
     chunk this is `GutChunk_dtor` `0x3c4d48`: an immediate destroy, not `obj_delete`.
     Then it **returns** (no `+0x24c` store).
   - Otherwise, while the counter `+0x25c` is non-zero, it is decremented. Without bit 8,
     with h < z and h > −10000, a decal comes first: **two own draws** (the angle, then one
     unused), `decal_add(spot, angle, base 4 / 7 / 1, 0; 12.0)`.
6. **Resting decal**, once. It needs:
   - no bit 0;
   - byte `+0x260` = 0;
   - `+0x1bc` < 0.1 and `+0x1c0` < 0.1, signed, not absolute (`0x3dcccccc`, `0x1edf3c`).

   Then `+0x260` = 1. When also there is no bit 8, h ≤ z and h > −10000: **one own draw**
   (the angle), `decal_add(spot, angle, 3 / 6 / 0, 1; 12.0)`.
7. `+0x24c` = `+0x1c4`.

## 10. Draws and seeds

| Where | Seed | Count | Executed |
|---|---|---|---|
| Water splash (§3.1) | own `+0x44` | 1, once per prop | yes |
| StaticFire burn time (§3.7) | own | 1, once | yes |
| Rest: `Prop_ctorNamed` / `Prop_ctorRes` / `ItemProp_ctor3` (§3.8) | **shared `0x404464`** | 1 when the pool gives a block | yes |
| GutChunk_run rising (§9 step 2) | own | 1 per frame with `+0x1c4` > 1 | yes |
| Falling decal | own | 2 | yes |
| Bounce decal | own | 2 | yes |
| Resting decal | own | 1 | yes |
| `fx_impactPuffNearCamera` (stub) | cosmetic `0x404460` | Observed at `0x1fc324`, `0x1fc3f0`, `0x1fc694`, `0x1fc86c`, `0x1fc938` | no |
| `StaticFire_ctor` (stub) | shared, through its `GameObject_ctor` (`0x14cd54`); own draws in `StaticFire_initCommon` (`0x2c5840`) and at `0x2c6b3c` | — | no |

`particle_spawn`, `decal_add`, `sound_playOnObject`, `water_test`, `water_disturb`,
`terrain_height`, `terrain_heightBelow` and `terrain_sweepCircle` contain no access to
`0x404460`, `0x404464` or `0x404468` and no call to `GameObject_rand`. This includes
everything they reach by `jal`, and none of them makes a `jalr` (Observed by a walk of the
disassembly; `res_find` makes indirect calls in its loader, and those were not followed).

The rest is a shared-seed event, so its frame matters for sync. A gut chunk, bone or item
prop that settles one frame later on one machine moves the shared seed one frame later
there (`docs/issues/pose-cache.md`). What decides the frame is all executed here except the
services' answers (§11).

## 11. When a gut chunk or a bone prop goes away

*Executed* conditions (§3.8, §9), counted in frames of the run slot after the
constructor:

- **A gut chunk with bit 0** destroys itself through `GutChunk_dtor` (slot 1, argument 3)
  on its first bounce. That is the first frame on which `+0x1c4` > 0 after a frame with
  `+0x24c` < 0. Bit 0 is forced whenever the gore word `0x44fdc0` is under 2.
  - Before the destroy it may play the water-bounce sound, if the bounce was harder than −1.
  - It leaves no bounce decal or resting decal, only the falling decals of §9 step 4.
- **Any other gut chunk, a bone prop and any PhProp** go away by one of:
  - **rest**, on the 181st frame at the earliest. Life 180 must have run out (life ≤ 0
    before the decrement) with all six momenta under 0.2;
  - **rest** unconditionally on the 402nd frame (life < −220);
  - `obj_delete` on any frame when the prop is more than 120 under the first alive player.

  Rest builds the resting prop (a shared draw when the pool has a block) and calls
  `obj_delete`. A prop launched with `0x8000` (life `0x7fff`) rests on its 32,768th frame
  at the earliest and its 32,989th at the latest.
- A bit-0 gut chunk is subject to the same rest and player-height deletes in
  `PhProp_run` until it bounces.

In the difftest's world, launch heights were 10–60 above the ground and the player stood at
the ground, 50 or 150 above. Frames to the end, min–max (median):

| | Seed 20973 | Seed 7 |
|---|---|---|
| Gut chunk, destroyed on its bounce (bit 0) | 15 lives: 64–93 (75) | 13: 52–108 (77) |
| Gut chunk, rest | 27: 181–402 (183) | 16: 181–402 (181) |
| Gut chunk, under the player | 18: 1–107 (58) | 31: 1–314 (67) |
| Bone prop (`0x107`), rest | 39: 181–305 (182) | 34: 181–402 (181) |
| Bone prop, under the player | 21: 5–84 (41) | 25: 14–134 (39) |
| Bone prop still running after 450 frames (launch `0x8107`) | 0 | 1 |

These figures come from the synthetic hull tables and terrain of the difftest. The real
models and levels give their own; only the conditions above are the game's.

## 12. What a probe needs to run these objects

- **Run slot**: table `+0x48` slot 4. GutChunk `0x50f3b8` gives `0x1edb18`; PhProp
  `0x511ba8` (bone props, item props, debris) gives `0x155fcc`.
- **World services**, called every frame unless noted:
  - `terrain_heightBelow(g_world, position; radius)`: the ground under the prop;
  - `terrain_height(g_world, position; 8.0)`: gut chunks only, the decal height;
  - `terrain_sweepCircle(g_world, position, step, 1, normal out; radius)`: only when the
    horizontal step is more than about 0.03. It returns the fraction moved and writes a 2D
    normal;
  - `water_test(g_world, position, 0; 12.0)`: every eighth frame (`g_simFrame` & 7 = 0)
    until the prop is in water.
- **Model data**: the hull table of the prop's model (`+0x4c`, header byte `+0x25`): eight
  signed-byte points per mesh in the part mask. For a gut chunk this is `gutchunks.vif` of
  `fx.lmp`; for a bone, the skeleton's model. The probe needs the real model bytes, or must
  answer these points. Without them the contact step reads address 0 (§7).
- **Globals**: `g_simFrame`, `g_world`, `0x44fe08` (gravity option), `0x44fdc0` (particles
  only), `g_numPlayers`, `g_alivePlayers[0]` and that player's object z.
- **Pool**: `pool_new(0x148)` or `(0x190)` at rest, `pool_new(0x4ac)` for a StaticFire.
  `obj_delete`, and for a gut chunk with bit 0 the destructor `GutChunk_dtor`.

## 13. Still not executed

- `StaticFire_ctor` `0x2c5240` and the fire object: a stub here. It is reached only by
  burning debris (`+0x23a` = 1).
- `Prop_run` `0x154514` and `ItemProp`'s slots: the resting prop's own frame.
- `GutChunk_dtor` `0x3c4d48`, `PhProp_dtor` `0x3c2fc8`, `obj_delete` `0x14f200`,
  `obj_updateGridCell`, `pool_new`, `obj_runEveryFrame`: object services, stubs.
- The presentation stubs: `particle_spawn` `0x18f3f8`, `decal_add` `0x19f110`,
  `fx_impactPuffNearCamera` `0x1fc150`, `sound_playOnObject` `0x214230`, `water_disturb`
  `0x189514`, `res_find` `0x17365c`.
- The world services, which a probe answers: `terrain_heightBelow` `0x1834a8`,
  `terrain_sweepCircle` `0x185a40`, `terrain_height` `0x183820` and `water_test` `0x189438`.
- `rigidbody_updateDerived` `0x167a58`, `rigidbody_init` `0x1682f0` and `quat_fromMat3`
  `0x164330`. They ran in the lives' builds but were not compared.
- What happens when `PhProp_run` has called `obj_delete` (rest, or below the player) and
  `GutChunk_run` then destroys the same chunk through slot 1 in that frame (bit 0, a bounce
  with |momenta| < 0.2, or a bounce 120 under the player). The two bodies allow it (Inferred
  from §3.8 and §9 step 5). What the delete list then does with a freed block is Unknown.
