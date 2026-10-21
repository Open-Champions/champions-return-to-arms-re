# `StaticFire_ctor`: the fire that burning debris leaves

US `SLUS_209.73` v2.00. Prose of `tools/ref_staticfire.py`. The comparison is
`tools/difftest_staticfire.py`; the synthetic tests are `tools/test_ref_combat5.py`. Written
2026-10-21 (research round 5, item 3). Evidence words as in `CONTRIBUTING.md`: **Executed** means
the original ran in `tools/ee_emu.py` and the model agreed on the calls to everything outside the
models (in order, with arguments), every byte stored outside the stack, the shared seed `0x404464`
with its draw count and the object's own generator; **Observed** means read at the address.

Who builds one (Observed, `symbols/skills.tsv`): `PhProp_run` `0x155fcc` (debris from an exploding
container, `docs/spec/phprop-run.md` §3.7: `StaticFire_ctor(block, copy of position, (d % 40) × 60 +
480, 0, 0; 240.0, 0.5)`), `0x1ee330`, `FireBomblet_onBounce` `0x262f7c`, `FireBombletJr_onBounce`
`0x263b78` and `SpellShadowStep_ctor` `0x311638`. `StaticFire_ctor2` `0x2c54f8` (one caller,
`0x159c94`) shares `StaticFire_initCommon` and is not covered here.

## 1. Entry

`StaticFire_ctor(a0 fire, a1 position*, a2 life, a3 owner, t0 flag; f12 size, f13 scale)`.
The block is `pool_new(0x4ac)`, zero-filled; a refused pool means no fire and no draw
(`phprop-run.md` §12). Table `0x50da38`.

## 2. What it does (*Executed*)

*Executed*: 3,000 cases per seed (20973 and 7), 0 mismatches. 172 of 174 instructions; the two it
does not reach (`0x2c5468`, `0x2c546c`) are the null-object `cxx_throwBadTypeid` arm of the box
loop, which the list's own terminator makes unreachable.

| # | Address | Step |
|---|---|---|
| 1 | `0x2c52a4` | `GameObject_ctor(fire, copy of position, 0, 0)`: **ONE SHARED DRAW**; its calls are `handle_link(grid cell, fire + 8, fire)` and `obj_getPropInt(fire, "hide", 0)`; it seeds the object's own generator `+0x44` |
| 2 | `0x2c52f4` | table `+0x48` = `0x50da38` (`lui 0x51` at `0x2c52ac`, `addiu -0x25c8` at `0x2c52c0`) |
| 3 | `0x2c52b8`–`0x2c5318` | light position `+0xb0`..`+0xbb` = `(x + 0.0, y, z + 36.0)` (`lui 0x4210` at `0x2c52b8`) |
| 4 | `0x2c5324`–`0x2c5378` | light record at `+0x80`: byte `+0x89` = 0; radius `+0x9c` and `+0xa4` = 120.0 (`lui 0x42f0` at `0x2c52fc`); falloff `+0xa0` and `+0xa8` = `0x3891a2b3` (`0x2c5308`/`0x2c530c`); `+0xac` = 1.0 (`lui 0x3f80`, `0x2c531c`); colour 255, 128, 0, 0 as 16-bit values at `+0x8a`..`+0x90` and again at `+0x92`..`+0x98`; byte `+0x88` = 0 (delay slot); `light_link(fire + 0x80)` |
| 5 | `0x2c537c`, `0x2c5380` | bytes `+0x6f` and `+0x70` = 0 |
| 6 | `0x2c5384` | `StaticFire_initCommon(fire)` (§3) |
| 7 | `0x2c538c`–`0x2c53ac` | `+0x7c` = life; `+0x68` = `+0x68 × scale` (initCommon's 25,000.0 × scale); `+0x50` = size (over initCommon's 480.0); `+0x4a8` = owner as a **plain word, no handle** (`skills-35-68-executed.md` SB3); byte `+0x6e` = 1 |
| 8 | `0x2c53a8`–`0x2c53b4` | flag ≠ 0: `light_unlink(fire + 0x80)` (the fire does not own its light) |
| 9 | `0x2c53d0`–`0x2c5418` | `world_collectObjectsInBox((x−30, y−30, z−30), (x+30, y+30, z+30), list, 0x80)` (`lui 0x41f0` at `0x2c53d0`; the position is the stored `+0x10` copy) |
| 10 | `0x2c5430`–`0x2c54a8` | for each object `o` of the list: `o == fire` is skipped; with flag 0, `o`'s slot-0 type-info getter is compared (`StaticFire_typeinfo` `0x3c7318`, `rtti_typeInfoEquals` `0x3b1250`) and an equal one is `light_unlink(o + 0x80)`'d; **every other object counts, a StaticFire or not, flag or not** |
| 11 | `0x2c54b0`–`0x2c54cc` | four or more counted objects: `+0x7c` = `(life + (life < 0)) >> 1` (arithmetic, so signed halving toward zero) |

**Seed draws**: shared ×1 (step 1); the object's own generator ×2 (both in step 6: one in
`StaticFire_initCommon`, one in the particle push of §4). **No cosmetic draw.**

**Calls in order** (outside the bodies run for real): `handle_link`, `obj_getPropInt` (inside
`GameObject_ctor`), `light_link`, `obj_runEveryFrame`, `obj_addToAlwaysDraw` `0x14edd8`,
`path_blockNodes` `0x18b6c0` (all from initCommon), optionally `light_unlink(fire + 0x80)`,
`world_collectObjectsInBox`, and per eligible object `Creature.v0` (slot 0), `StaticFire_typeinfo`,
`light_unlink`.

The count of step 10 includes whatever the box query returns beside the fire: creatures that stand
within 30 units count as well as other fires (*Inferred* for a player: the query's own filter is
not part of this document), so building a fire among three other objects halves its life.

## 3. `StaticFire_initCommon` `0x2c5814` (fire)

*Executed*: 3,000 cases per seed, 0 mismatches, **82 of 82**. Run for real by `StaticFire_ctor` and
by the second constructor.

| Address | Step |
|---|---|
| `0x2c5818`–`0x2c5838` | `+0x1c` = 16.0 (`lui 0x4180`); s16 `+0x38` = 0; byte `+0x28` = 60; s16 `+0x78` = 0 and `+0x7a` = 0 |
| `0x2c5840` | ONE OWN DRAW `d` (`GameObject_rand` `0x1509d0`); `d mod 300` (`divu` by 300, `0x2c5848`/`0x2c584c`; `mfhi` at `0x2c5898`) |
| `0x2c5850`–`0x2c58a8` | flags `+0xc` \|= `0x40001` (`lui 4` / `ori 1` at `0x2c5860`/`0x2c586c`); `+0x68` = 25,000.0 (`0x46c35000`, `0x2c5854`); `+0x7c` = −1; `+0x54` and `+0x64` = 1.0; byte `+0x6c` = 0; `+0x4c` = `float(d mod 300)` |
| `0x2c58a4` | `StaticFire_pushParticles(fire, s16 +0x38)` (§4) |
| `0x2c58ac`, `0x2c58b4` | `obj_runEveryFrame(fire)`, `obj_addToAlwaysDraw(fire)` |
| `0x2c58bc`–`0x2c58e4` | `path_blockNodes(g_world (0x44fdc8), copy of position, radius +0x1c)`: the pathing grid's block counter (`world-queries.md` §10) |
| byte `+0x6f` ≠ 0: `0x2c5904`–`0x2c591c` | s16 `+0x76` = 250; `+0x4a4` = `mem_allocTagged(0x9c4, "smokebomb" (0x54e768), fire + 0xbc)`; `+0x50` = 600.0 (`0x44160000`) |
| else: `0x2c5920`–`0x2c5948` | `+0x50` = 480.0 (`0x43f00000`); s16 `+0x76` = 100; `+0x4a4` = `fire + 0xbc` (a buffer inside the object); byte `+0x70` ≠ 0: `+0x50` = 240.0 (`0x43700000`) |

`StaticFire_ctor` zeroes `+0x6f` and `+0x70` before calling it, so the debris fire always takes the
second branch with `+0x50` overwritten afterwards by the size argument (240.0 for debris). The
`+0x6f` arm (a smoke-bomb fire with a 2,500-byte particle ring) belongs to the other constructor and
to nothing met so far; it was executed here by calling `initCommon` directly.

## 4. The particle push `0x2c6aa8` (`StaticFire_pushParticles`, my name)

*Executed*: 3,000 cases per seed, 0 mismatches, **70 of 70**. Called from `initCommon` and,
*Inferred* from the symbol table's caller count (2) and the live ring, from the fire's run.

`(fire, facing)`: `math_cos16` and `math_sin16` of the 16-bit facing (`0x166630`, `0x1666e0`, real);
`n = cos² + sin²` renormalised with `rsqrt.s` (the word `0x2c6b0c`, which the disassembler lists as
unknown); `cos' × 3.7333` and `sin' × 3.7333` (`0x406eeeee`, `lui` at `0x2c6af0`) truncated to s16
at `+0x72` and `+0x74`. ONE OWN DRAW `r`. When the particle index `+0x7a` differs from the stop
`+0x78`: for each index (wrapping to 0 at the ring size `+0x76`), the 10-byte record at
`(+0x4a4) + 10 × index` has its u16 at `+6` increased by `+0x72` and its u16 at `+8` by `+0x74`
when `(index & 3) == (r & 3)`. From the constructor both `+0x78` and `+0x7a` are 0, so the ring is
untouched and only the velocity words and the draw happen.

## 5. Fields read and written, by the constructor chain

| Offset | Read | Written | By |
|---|---|---|---|
| `+0x00`–`+0x08`, `+0x0c`, `+0x10`–`+0x1c`, `+0x20`, `+0x24`, `+0x28`, `+0x29`, `+0x2c`, `+0x34`, `+0x44` | `+0xc` | all | `GameObject_ctor` (`phprop-run`/`skills-35-68` Part 2) |
| `+0x1c` | radius (path block) | 16.0 | initCommon |
| `+0x38` | facing | 0 | initCommon |
| `+0x48` | | `0x50da38` | ctor |
| `+0x4c` | | `float(d mod 300)` | initCommon |
| `+0x50` | | 480.0 / 600.0 / 240.0, then size | initCommon, ctor |
| `+0x54`, `+0x64` | | 1.0 | initCommon |
| `+0x68` | 25,000.0 | 25,000.0, then × scale | initCommon, ctor |
| `+0x6c`, `+0x6e`, `+0x6f`, `+0x70` | `+0x6f`, `+0x70` | 0, 1, 0, 0 | initCommon, ctor |
| `+0x72`, `+0x74` | | cos / sin parts | push |
| `+0x76` | ring size | 100 or 250 | initCommon |
| `+0x78`, `+0x7a` | both | 0 | initCommon |
| `+0x7c` | life | −1, then life, then halved | initCommon, ctor |
| `+0x80`–`+0xac` | | the light record (registered by `light_link`) | ctor (§2 step 4) |
| `+0xb0`–`+0xbb` | | light position | ctor (§2 step 3) |
| `+0x4a4`, `+0x4a8` | | ring pointer, owner | initCommon, ctor |

## 6. Not executed

- `StaticFire_run` `0x2c595c` (slot 4), `StaticFire_draw` `0x2c65e8`, `StaticFire_dtor` `0x2c5770`
  and `StaticFire_clone` `0x1300e0`: what the fire does each frame and how it ends are *Unknown*
  here (`docs/spec/combat-round6.md` lists them as the next bodies). From the ctor alone: life
  `+0x7c` counts down (initial −1 is the "no life yet" value), the radius `+0x50` (240.0 for
  debris) and `+0x68` (25,000 × scale = 12,500) are what the run reads (*Inferred*: no run was
  read for this document).
- `path_blockNodes`, `obj_addToAlwaysDraw`, `mem_allocTagged` and the light calls remain
  recording call-outs.

## 7. Checks of the comparison itself

300 cases each, model restored after each:

| Mutation | Result |
|---|---|
| the neighbour count test `≥ 5` instead of `≥ 4` | `ctor` FAIL 33 / 300 |
| the push's `(index & 3) == (r & 3)` changed to `(r ^ 1)` | `push` FAIL 219 / 300 |

Commands:

    PYTHONDONTWRITEBYTECODE=1 python3 -u tools/difftest_staticfire.py --seed 20973 -v
    PYTHONDONTWRITEBYTECODE=1 python3 -u tools/difftest_staticfire.py --seed 7 -v
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tools/test_ref_combat5.py

| Seed | `ctor` | `init` | `push` |
|---|---|---|---|
| 20973 | 3,000 / 0 | 3,000 / 0 | 3,000 / 0 |
| 7 | 3,000 / 0 | 3,000 / 0 | 3,000 / 0 |

(cases / mismatches; the ctor cases place 0–6 objects in the box and answer the type-info getter
with the fire's descriptor or a creature's.)
