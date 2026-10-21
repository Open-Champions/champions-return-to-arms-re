# The gut chunk's constructor chain (PhProp_ctor, Prop_ctorNamedLaunch, Prop_launch, PhProp_initPhysics), the bone props (PhProp_ctor2) and the gold pile (Gold_ctor2)

US `SLUS_209.73` v2.00. Prose of `tools/ref_phprop.py`. The comparison is
`tools/difftest_phprop.py`; the synthetic tests are `tools/test_ref_phprop.py`.
Written 2026-10-21 for item 6 of `docs/spec/full-placement.md` §4 (blood).

Evidence words as in `CONTRIBUTING.md`. **Executed**: the original ran in `tools/ee_emu.py`
and the model agreed on the calls to everything outside the models (in order, with
arguments), every byte stored outside the stack, the shared seed `0x404464` with its draw
count, and the result. **Observed**: read at the address. Nothing here ran on a console,
in PCSX2 or on the live rig.

## 1. Why

`GutChunk_ctor` `0x201958` was already executed (`docs/spec/combat-round3.md` §2, 53 of 53)
with `PhProp_ctor` `0x155a0c` a callback. A bleeding hit makes `Creature_processDamage` ask
`pool_new(0x268)` and, given a block, call `GutChunk_ctor(block, point, 2, k; 1.0)`
(`docs/spec/creature-tick.md`). The Full-placement probe refused every pool block, so it
never got there. Everything under `PhProp_ctor` had no executed body; one of its calls,
`GameObject_ctor`, draws the **shared** seed. So a port that skips gut chunks or builds
them its own way moves the shared seed differently.

## 2. How it was run

These bodies run for real:

- `GutChunk_ctor`, `PhProp_ctor`, `Prop_ctorNamedLaunch` `0x153e54`, `Prop_launch`
  `0x1541a0`, `PhProp_initPhysics` `0x155110`;
- `GameObject_ctor` `0x14cb10` (`tools/ref_skills_a.py`) and `GameObject_rand` `0x1509d0`;
- `libc_strcpy` `0x3b868c`.

`libc_sprintf` `0x3b7ef0` is a stub that records `(format, value)` and writes the text the
library would write. Every other callee is a recording stub, answered by the same seeded
script on both sides.

The five entries are called directly:

- **gutChunk**: `GutChunk_ctor` on a zero-filled 0x268 block, as `pool_new` hands it out
  (`docs/spec/object-system.md`). The kinds are 0–3, 7, `0x80000000` and `0xffffffff`;
  the bits are 0–3; the gore word `0x44fdc0` is any value.
- **phprop**: `PhProp_ctor` on zeroed or dirty blocks. Every launch bit is tried, alone and
  in mixes, with and without an item record (its word `+8` with `0x20000` or not). The
  scale is 0.5–3. The damping word `0x44fe08` is any value.
- **namedLaunch**: `Prop_ctorNamedLaunch` with the same mixes, and bounds of either sign up
  to ±2³¹.
- **launch** and **physics**: `Prop_launch` and `PhProp_initPhysics` on dirty blocks. The
  dirty fields are `+0x140`, `+0x238`, `+0x150`, a 64-bit `+0xe8`, and `+0x30` around 400.

Commands:

    python3 -u tools/difftest_phprop.py --seed 20973 -v
    python3 -u tools/difftest_phprop.py --seed 7 -v
    python3 -m unittest tools.test_ref_phprop

| | Seed 20973 | Seed 7 |
|---|---|---|
| Cases per entry (gutChunk, phprop, namedLaunch, launch, physics, phprop2, gold) | 3,000 each | 3,000 each |
| Shared draws seen (one per construction) | 15,000 | 15,000 |
| Mismatches (calls, writes, seed, result, faults) | 0 | 0 |

| Function | Address | Executed |
|---|---|---|
| `GutChunk_ctor` | `0x201958` | 53 of 53 |
| `PhProp_ctor` | `0x155a0c` | 116 of 116 |
| `Prop_ctorNamedLaunch` | `0x153e54` | 117 of 117 |
| `Prop_launch` | `0x1541a0` | 221 of 221 |
| `PhProp_initPhysics` | `0x155110` | 161 of 161 |
| `PhProp_ctor2` | `0x1556c0` | 211 of 211 |
| `Gold_ctor2` | `0x157668` | 59 of 59 |

Both seeds give the same coverage.

Checks (`--quick`): each of these model changes was detected.

- Launch bit 8's span set to 324 instead of 224: 3 failing checks.
- The spin factor set to 10 for bit 0x10 only, not 0x400: `phprop` writes 28, `physics`
  writes 24.
- `PhProp_ctor2`'s angle `facing + 0x3fff` instead of `+ 0x4000`: `phprop2` writes 300 of 300.
- `Gold_ctor2`'s flags `| 0x200c` instead of `| 0x220c`: `gold` writes 300 of 300.

The second two were added on 2026-10-21 for the death path (`docs/spec/full-placement.md`
§3.2). The entries **phprop2** and **gold** are:

- **phprop2**: `PhProp_ctor2` with the shatter's arguments (launch `0x107`) and others. The
  part bits are any 64-bit value, the facing any value. The joint matrix the stub answers
  is the identity or random. An item record is present or not.
- **gold**: `Gold_ctor2` with values 0 to `0xffffffff`.

The matrix bodies run for real: `mat34_setPosRotZScale` `0x163cb8`, `mat34_mul`
`0x162808` and `mat34_transformPoint` `0x1660a0`. They come from `tools/ref_core.py` and
were executed by `tools/difftest_core.py`.

## 3. GutChunk_ctor (block G, point P, kind, bits; 1.0)

*Executed*; unchanged from `combat-round3.md`. It calls `PhProp_ctor(G, copy of P, lump,
model, texture, kind, 0xb41, no item; 1.0)`:

- the lump is the word at `0x4f86a0` (`fx.lmp`);
- the model is the word at `0x4f86f0` (`gutchunks.vif`);
- the texture is the word at `0x4f86a0 + 0x60` when the bits have bit 1, otherwise
  `+0x58`;
- the kind goes in as the whole register (`move t1, a2` at `0x201990`), so the 64-bit part
  mask is the sign-extended kind.

## 4. PhProp_ctor `0x155a0c` (obj, position, lump, model, texture, part mask, launch, item; scale)

*Executed*, in this order:

1. `Prop_ctorNamedLaunch(obj, copy of the position, lump, model, texture, part mask,
   launch)`, with the registers passed on unchanged.
2. Table `0x511ba8` at `+0x48` (`0x155a54`/`0x155a58`).
3. An empty item record at `+0x148`:
   - the four slot ids `+0x16c + 8k` are `0xffff`;
   - bytes `+0x168` and `+0x169` are `0xff`;
   - the halfwords `+0x158`–`+0x15e` and `+0x160`–`+0x166` are 0.

   This is the stack descriptor shape of `difftest_monsters_1`.
4. `+0x240` = the scale. Flags `+0xc |= 0x4000`.
5. **With an item record** (`t3`): its 0x48 bytes are copied to `+0x148`, byte `+0x238` =
   1, `+0x34` = `0x403ab8` (`0x155b1c`/`0x155b20`), and the flags gain `0x100000` and lose
   `0x800` and `0x4000`.
6. Byte `+0x23a` = 0, `+0x234` = 0.
7. `PhProp_initPhysics(obj, launch)`.
8. When the signed byte `+0x238` is non-zero and the launch has any of `0x19`:
   - **one own draw** d;
   - `libc_sprintf(buffer, 0x532688 "game_swish_chest%d.anm", d % 3 + 1)`. The modulo is
     `divu`, at `0x155b7c`;
   - `res_find(0x532478 "fx.lmp", buffer)`;
   - `sound_playOnObject(entry, obj; 1.0)`.

Reads: the position, the item record, `+0xc`, `+0x238`. Writes: as listed, plus those of
the three callees.

## 5. Prop_ctorNamedLaunch `0x153e54` (obj, position, lump, model, texture, part mask, launch)

*Executed.*

1. `GameObject_ctor(obj, copy of the position, no definition, no properties)`. This is
   **ONE SHARED DRAW**: the object's own generator `+0x44` is set to the 16-bit draw
   (`tools/ref_skills_a.py`). Its calls are `handle_link` to the grid cell and
   `obj_getPropInt(obj, "hide", 0)`.
2. Table `0x511d58` at `+0x48`.
3. `libc_strcpy` of the lump, model and texture names to `+0x54`, `+0x64` and `+0xa4`.
4. `+0x4c = res_find(+0x54, +0x64)`, then `+0x50 = res_find(+0x54, +0xa4)`. Both are given
   the copies.
5. `+0xe8` = the 64-bit part mask (`sd`).
6. **One own draw**: the facing `+0x38` takes its low 16 bits.
7. `+0x10c` = 0 (halfword). `+0x30`, `+0x100` and `+0xfc` = 0.0.
8. `model_getBounds(+0x4c, the 64-bit +0xe8, six words)`. This gives minimum x, y, z and
   maximum x, y, z, as integers.
9. The centre on each axis is `(min + max) >> 1`: a 32-bit add, then an arithmetic shift,
   then the result made a float. It goes to `+0xf0` (x), `+0xf4` (y) and `+0xf8` (z).
   `+0x108` = centre z − (float) minimum z.
10. Launch bit 4: the position `+0x10`–`+0x18` gains the centre, then
    `obj_updateGridCell(obj)`.
11. `Prop_launch(obj, launch)`.

## 6. Prop_launch `0x1541a0` (obj, launch)

*Executed.* In this order, with f the own draw × 2⁻¹⁶ (`0x37800000`):

1. Flags `|= 0x1809`, then `obj_updateGridCell`. Radius `+0x1c` = 4.0 (`0x40800000`,
   `0x1541d4`).
2. Bit `0x100`: halfword `+0x140 |= 2` and flags `|= 0x4000`. Bit `0x200`: `+0x140 |= 4`.
3. The velocity. Each bit that is set overwrites what the bits before it wrote.

   | Bit | Writes | Own draws | Constants (address) |
   |---|---|---|---|
   | 1 | `+0xfc`, `+0x100` = (f − 0.5) × 124 | 2 | 124 `0x42f80000` (`0x154248`), 0.5 `0x3f000000` |
   | 8 | the same × 224 | 2 | 224 `0x43600000` (`0x1542ac`) |
   | `0x10` | the same × 324, then `+0x30` = f × 480 | 3 | 324 `0x43a20000` (`0x154310`), 480 `0x43f00000` (`0x15434c`) |
   | `0x20` | `+0x30` = f × 30 + 130 | 1 | 30 `0x41f00000`, 130 `0x43020000` (`0x15438c`, `0x154394`) |
   | `0x40` | `+0x30` = f × 60 + 260 | 1 | 60 `0x42700000`, 260 `0x43820000` (`0x1543d0`, `0x1543d8`) |

4. Bit 2: `+0x10c` = 2000.
5. `obj_runEveryFrame(obj)`.
6. The life `+0x10e` is `0x7fff` with bit `0x8000`, otherwise 180.
7. `+0x140 |= 8` with bit `0x2000`; otherwise `|= 0x10` with bit `0x4000`.
8. `+0x140 |= 0x20` with bit `0x10000`.
9. Bit `0x80`: life 0 and `+0x140 |= 1`. Unless `+0x140` (as read before) has 2,
   `obj_stopRunning(obj)` follows.
10. Bit `0x100` of the word `0x44fe08` damps the launch:
    - `+0x30` is clamped to 400 (`0x43c80000`) when 400 < it, then multiplied by 0.25
      (`0x3e800000`);
    - `+0xfc` and `+0x100` are multiplied by 0.5.

## 7. PhProp_initPhysics `0x155110` (obj, launch)

*Executed.*

1. An item prop (signed byte `+0x238` non-zero) whose record word `+0x150` has `0x20000`
   adds launch bit `0x1000`.
2. `model_getBounds` again. The extents are scaled by `+0x240`:
   `rigidbody_init(+0x190; 1.0, 1.0, max x·s − min x·s, max y·s − min y·s,
   max z·s − min z·s)`. Each bound is converted, then multiplied, then subtracted.
3. The position is copied to `+0x1a0`–`+0x1a8`.
4. `+0x1bc`, `+0x1c0` and `+0x1c4` = `+0xfc`, `+0x100` and `+0x30` × 1/60 (`0x3c888888` at
   `0x155210`).
5. The spin `+0x1c8`, `+0x1cc` and `+0x1d0` = (2f − 1) × k, from **three own draws**.
   k is 2.0, or 10.0 with launch bit `0x10` or `0x400` (`0x41200000`).
6. `+0x22c` = −1. When the part mask `+0xe8` is non-zero, `+0x22c` becomes the index of its
   highest set bit, from a `dsrl` loop over all 64 bits.
7. `quat_fromMat3(+0x1ac, +0x110)`, `quat_normalize(+0x1ac)`,
   `rigidbody_updateDerived(+0x190)`.
8. `+0x23c` = −0.1 (`0xbdcccccc`) with launch bit `0x800`, otherwise −0.4 (`0xbecccccc`).
9. Launch bit `0x1000`: `+0x19c`, `+0x194` and `+0x198` = 0.

## 7a. PhProp_ctor2 `0x1556c0`: the shattered skeleton's bone props

Arguments: obj, position, facing, model, anim state, lump, model name, texture; scale in
f12. Three more are 64-bit slots in the caller's outgoing stack (`ld 0x140(sp)`, `lw
0x148(sp)`, `lw 0x150(sp)` at `0x155708`–`0x155740`): the part bits, the launch flags and
the item record. `Skeleton_shatter` passes its class definition's words and the launch
`0x107` (`docs/spec/combat-death.md`).

*Executed*, in this order:

1. `Prop_ctorNamedLaunch(obj, copy of the position, lump, model name, texture, part bits,
   launch | 4)` (`ori` at `0x155738`). The bit 4 moves the prop by its parts' centre and
   relinks it. This is **one shared draw** plus the facing's and the launch's own draws
   (§5, §6).
2. As `PhProp_ctor` (the shared part, `phprop_record` in the model):
   - table `0x511ba8`;
   - the empty item record;
   - `+0x240` = scale, flags `|= 0x4000`;
   - the item branch.
3. `+0x22c` = −1, byte `+0x23a` = 0, `+0x234` = 0. When the part mask `+0xe8` is non-zero,
   `+0x22c` becomes the index of its highest bit (the same `dsrl` loop as
   `PhProp_initPhysics`).
4. J = `anim_getJointMatrix(anim state, model_getMeshJoint(model, +0x22c))`, a 3×4 matrix
   on the stack.
5. R = `mat34_setPosRotZScale(+0x240, (0, 0, 0), s16(s16 facing + 0x4000))`. Then
   `mat34_mul(J, J, R)`, which writes back into J.
6. The prop's offset from the given position (its position now, less the copy) is
   transformed by J (`mat34_transformPoint`). The given position plus that offset becomes
   the new `+0x10`–`+0x18`.
7. `PhProp_initPhysics(obj, launch)`, with the launch as given (without the 4).
8. The item sound of `PhProp_ctor` (one own draw) when `+0x238` is set and the launch has
   any of `0x19`.
9. Flags `|= 0x2000`.

Draws: one shared, then own draws as in §8 for its launch. The shatter's `0x107` gives:

- bit 1: two own draws;
- bit 2: `+0x10c` = 2000;
- bit 4: the centre move;
- bit `0x100`: `+0x140 |= 2` and flags `|= 0x4000`;
- the spin: three own draws.

So each bone costs 1 shared and 6 own draws, and makes no sound. The damping is −0.4.

## 7b. Gold_ctor2 `0x157668` (obj, position, value): the gold pile

*Executed*, in this order:

1. `GameObject_ctor(obj, copy of the position, no definition, no properties)`. This is
   **one shared draw**.
2. Table `0x511a88` (`0x1576b0`/`0x1576b8`).
3. Byte `+0x5d` = 1. This is the embedded anim state's `+5`; the anim state is at `+0x58`.
4. An empty five-pass loop (`0x1576c4`–`0x1576e8`, only `nop`s).
5. Byte `+0x4c` = `0x29`. `+0x80` = the value. Flags `|= 0x220c`.
6. `anim_clear(+0x58)`.
7. `+0x50` = `g_simFrame`.
8. `anim_push(+0x58, resref_get(0x6e01b0), 0x204)`.
9. `obj_runEveryFrame(obj)`.

No own draws.

## 8. What one gut chunk costs (Executed)

The launch is `0xb41` with no item. That gives:

- **1 shared draw** (`GameObject_ctor`);
- **7 own draws**: the facing 1, bit 1's velocity 2, bit `0x40`'s height 1, the spin 3.

There is no sound. The other launch bits set the prop's state:

- bit `0x100`: flags `|= 0x4000`, `+0x140 |= 2`;
- bit `0x200`: `+0x140 |= 4`;
- bit `0x800`: damping −0.1;
- life 180.

The prop runs every frame; `GutChunk_run` `0x1edb18` is its slot 4.

`rigidbody_init` takes a value from the cosmetic seed, not the shared one
(`symbols/runtime.tsv`). `pool_new` returns 0 when no block is free, and then none of this
happens (`docs/objects.md` O1). So each chunk a bleeding hit makes is a shared draw only
when the pool has a block.

## 9. Still not executed

- `GutChunk_run` `0x1edb18` (≈333 instructions: own draws, blood decals, deletion on the
  first bounce with bit 0 of `+0x248`) and `PhProp_run` `0x155fcc` under it.
- `rigidbody_init`, `quat_fromMat3`, `quat_normalize`, `rigidbody_updateDerived`,
  `model_getBounds`, `obj_updateGridCell`, `obj_runEveryFrame`, `obj_stopRunning`,
  `sound_playOnObject`, `res_find` and `handle_link`. All were recording stubs.
- `model_getMeshJoint` `0x179358` and `anim_getJointMatrix` `0x16f720` (`PhProp_ctor2`),
  and `resref_get`, `anim_clear` and `anim_push` (`Gold_ctor2`). All were recording stubs.
- `Gold_run` `0x157b58` and `Gold_onTouch` `0x157a9c`: the pile's frame and its pickup.
