# Visual effects: particles, emitters, glows, trails, beams, decals, gore

Status: first pass, 2026-10-17, on branch `t3/research-fx`. Everything here was read from
the disassembly and a Ghidra decompile of `SLUS_209.73` (v2.00); nothing was run on a live
game or executed in `tools/ee_emu.py`. Each claim is **Observed** (O, read at the address
given), **Inferred** (I) or **Unknown** (U). The reference contracts are in
`tools/ref_particles.py` (tested by `tools/test_ref_particles.py` on synthetic values).

This document is for a renderer that wants to draw what the game draws. It extends
`docs/engine.md` ("Particles, glows, trails, beams", skimmed there) and the GPU side in
`docs/spec/render-pipeline.md` sections 4.10–4.12, 6 and 7, which it does not repeat.
Lights are in `docs/lighting.md`.

Everything in this document is cosmetic: it draws from `g_cosmeticSeed` (0x404460), not
from the shared seed, unless a line says otherwise (`docs/engine.md`, P1 and "Checked and
found clean").

## 1. Particle system at a glance

| Thing | Where | Size |
|---|---|---|
| particle definition ("def") | static objects in `.bss`, built by `particleDef_ctor` 0x18f3d0 (362 call sites, all in static initialisers) and re-set by `particleDef_set` 0x18f118 (15 call sites) | 0x50 bytes |
| resident type slots | flags `g_particleSlotUsed` 0x82c408 (32 words, −1 = free); records `g_particleTypeTable` 0x82c490 (32 × 0x40, uploaded to VU1 qwords 0–127 every frame) | 32 |
| particle pages | `g_particlePages` 0x7ec300, 64 pages of 0x1000 bytes; page descriptors (one next-pointer each) at 0x82c300, free list head 0x82c400 | 64 × 240 particles |
| global list set | `g_particleLists` 0x44fa98: 16 list heads of 16 bytes | 16 lists |
| groups | 0x7e1d50 + i × 0x138, i < 16: 16 list heads, a mat34 at +0x100, handle +0x130, idle counter +0x134 | 16 |
| clock | `g_particleClock` 0x82cc90, s16, +1 per simulated tick | |
| texture | `engine.lmp` : `particletex.tex` (resource reference 0x7d8a80, set up in 0x195d30) | one sheet |

Particles do not move on the CPU. A particle stores its birth position, velocity and birth
tick; the vertex program computes where it is now from its age (render-pipeline 4.10). The
CPU only appends particles and retires them when they are too old. O 0x18f3f8, 0x18f6e0.

## 2. The definition (0x50 bytes) — O `particleDef_init` 0x18ee70

`particleDef_init(sizeStart f12, sizeEnd f13, gravity f14, def a0, r0 a1, g0 a2, b0 a3,
a0' t0, r1 t1, g1 t2, b1 t3, [stack] a1', lifeClass, kind, tile, terminateCallback)`.
`particleDef_ctor` 0x18f3d0 sets def+4 = −1 and def+8 = 0, then tail-calls it with the
same arguments. The callback must be 0: a non-zero one fails the assertion at line 0x1f8 of
`particle.cc` (0x18eee0), so no definition has one. `lifeClass` and `kind` are clamped to
0…3 (0x18ef04–0x18ef2c).

| Offset | Type | Value |
|---|---|---|
| +0x00 | s32 | list index = kind × 4 + lifeClass |
| +0x04 | s32 | resident slot 0…31, or −1 |
| +0x08 | s32 | live particles of this definition |
| +0x0c | s32 | terminate callback (always 0) |
| +0x10 | s32 | u0 = (col × 32 + 1) × 16. **Kind 2:** f32 gravity / 256 |
| +0x14 | s32 | v0 = (row × 32 + 1) × 16. Kind 2: not written |
| +0x18 | f32 | g = gravity / 256 |
| +0x1c | f32 | size rate = (100 × sizeEnd − 100 × sizeStart) / life. **Kind 2:** sizeStart, unscaled (the tail lag, below) |
| +0x20 | s32 | u1 = (col × 32 + 31) × 16. Kind 2: not written |
| +0x24 | s32 | v1 = (row × 32 + 31) × 16. Kind 2: not written |
| +0x28 | s32 | the definition's own address |
| +0x2c | f32 | size0 = 100 × sizeStart |
| +0x30…+0x3c | f32 × 4 | start colour r0, g0, b0, a0, each + 2^23 (kind 3: without the 2^23) |
| +0x40…+0x4c | f32 × 4 | colour rate (end − start) / life, per channel |

- `col = tile & 15`, `row = tile >> 4`: the sheet is a grid of 32 × 32 cells, 16 per row,
  and each particle uses its cell inset by one texel on each side. u and v are GS texel
  coordinates in 1/16 texel. O 0x18efac–0x18efec. The sheet's real height was not read (U).
- `life = g_particleLifeTicks[lifeClass]`, the table at 0x44fa88 = **11, 30, 60, 90** ticks.
  It is read-only (its only readers are 0x18ef4c and 0x18f780). O
- The 2^23 added to the colours is the usual float trick: after the clamp in the vertex
  program the low mantissa bits are the 8-bit channel. O 0x18f030–0x18f068, VU 0x076.
- +0x10…+0x4f (four qwords) is the record the vertex program reads.

`particleDef_set` 0x18f118 takes the same arguments: it keeps a copy of the 0x50 bytes,
re-runs `particleDef_init`, and when the definition is resident (+4 ≠ −1) and the bytes
changed (`memcmp`) copies the new record into its slot of 0x82c490. Used by level emitters
(section 5), `particles_configure` 0x202ae8 and a few object classes at run time. O

0x18f360 resets a definition to defaults: size 1 → 1, gravity 0, all colours 0, lifeClass
3, kind 1, tile 1 (it does not touch +4/+8 beyond setting them to −1 and 0). O

### Kinds

| kind | Drawn as | `ALPHA_1` | O |
|---|---|---|---|
| 0 | camera-facing sprite, blended | 0x44: `src × As + dst × (1 − As)` | `particle_emitLists` 0x194450 |
| 1 | camera-facing sprite, additive | 0x48: `dst + src × As` | same |
| 2 | line from the position `lag` ticks ago to the position now (VU 0x0ac–0x0dd) | not re-set, so the 0x48 of kind 1 stays (I) | same; MSCAL 0x22 selects the line loop |
| 3 | nothing: `particle_emitLists` walks list sets 0, 1, 2 only (loop bound 3) | — | 0x194450 |

As is texel alpha × vertex alpha with 0x80 = 1 (texture function modulate). All particles
use `TEST_1` 0x71001 (depth test greater, no depth write) and point sampling (`TEX1_1` 1,
restored to 0x61 afterwards). O `particle_draw` 0x194888. Within one list set the order of
drawing is: kind 0 lists, kind 1 lists, kind 2 lists, each by lifeClass 0…3; inside a list,
oldest first. There is no depth sort (render-pipeline section 8). O 0x194450

## 3. Spawning — O `particle_spawn` 0x18f3f8

`particle_spawn(f12 backdate, a0 def, a1 pos[3] float, a2 vel[3] float)`.

1. The list is `listSet + def[0] × 16`, where `listSet` is `g_particleListSet` 0x44fca0:
   0x44fa98 normally, or a group between `particleGroup_begin` and `particleGroup_end`.
2. A definition with no live particle needs a type slot: if all 32 are used
   (0x195b58) the particle is **dropped**. O 0x18f430–0x18f448
3. A list whose cursor is 0x101 takes a page from the free list; with no free page the
   particle is **dropped**. The page is appended to the list. O 0x18f450–0x18f49c
4. The first particle of a definition uploads its record to a free slot (0x195bb0: marks
   the slot, def+4 = slot, copies +0x10…+0x4f to 0x82c490 + slot × 0x40). O
5. The particle goes in the next cell of the page. Cell index = cursor; after the
   increment a cursor whose low five bits are 0x1f skips two cells (the block's MSCAL and
   the next block's VIF header), so a page holds 8 blocks of 30 particles, and the cursor
   value 0x101 means "page full". O 0x18f4b8–0x18f4fc; page layout O `particle_init`
   0x18e648
6. def+8 += 1, and the particle record is written.

Particle record, 16 bytes, signed 16-bit fields — O 0x18f518–0x18f6bc:

| Offset | Value |
|---|---|
| +0x0, +0x2, +0x4 | position x, y, z, world units (`cvt.w.s`: truncated toward zero) |
| +0x6 | birth tick (particle clock) |
| +0x8, +0xa, +0xc | velocity × 256 (truncated) |
| +0xe | slot × 4 (the qword address of its type record in VU memory). Set to 0 when the particle is retired (0x18f82c); slot 0 also gives 0 and nothing tests the field, so it is not a dead marker (I) |

With `backdate ≤ 0`: position = pos, birth = clock, velocity = vel.

With `backdate > 0` (seconds): `n = trunc(60 × backdate)` ticks and the particle is
written as if it had been born n ticks ago and is at `pos` with velocity `vel` now:

```
birth = clock − n
p.xy  = pos.xy − vel.xy × n / 16
vz'   = vel.z − 32 × n × g
p.z   = pos.z − vz' × n / 16 − g × n²
v     = (vel.x, vel.y, vz')
```

(g = def+0x18.) O 0x18f53c–0x18f63c. Most callers pass 0.

Fields are 16-bit: positions beyond ±32767 wrap, which no level reaches (levels are at most
90 × 256 = 23040 units; `docs/lighting.md` 4). Velocities above 127.99 units per 16 ticks
wrap (I: a caller would have to pass one).

## 4. Motion, size, colour, death

Per particle, with `age = clock − birth` (VU 0x089–0x09f, render-pipeline 4.10; O for the
formulas, not executed):

```
pos(age)   = p + v × age / 16 ;   pos.z += g × age²          # world units
size(age)  = size0 + rate × age                                 # kinds 0, 1
colour(age)= clamp(c0 + crate × age, 0, 255) per channel        # 0x80 = unmodified texel
half-extent on screen = (2 × size / w, size / w) pixels of the 1280 × 448 buffer
```

`w` is the clip w of the particle matrix, `mat4_setProjection(…)` with x scaled by 1/800
and y by 1/400 and then multiplied back by (800, 400) (`particle_draw` 0x194888; VU vf6):
so the centre projects exactly like level geometry and `w` is the camera-space depth
(I: render-pipeline section 3 gives `sx = F × cam.x / cam.z`). The sprite is 2:1 in buffer
pixels, which is square-ish on the 4:3 display, and its pixel size does **not** depend on
the field of view.

A velocity is in world units per 16 ticks (I from the ×256 store and the 1/4096 load:
the displacement per tick is v / 16).

Kind 2 lines: the line runs from `pos(age − lag)` to `pos(age)`, lag = def+0x1c, with
gravity from +0x10 (VU 0x0ac–0x0dd). Their colour is the same clamp; whether the second
vertex's alpha is 0 (the `SUB.w` at 0x0d8 overlaps the stores) was not settled (U).

**Death.** `particle_updateTask` 0x18f970 runs in the run phase (task flags 2, priority 15),
once per simulated tick, when 0x44fa80 is 0, 0x4039c0 is set and `game_isFrozen()` is 0:

1. `clock += 1`; when it reaches −0x8000 it is set to 0 and every live particle's birth is
   lowered by 0x8000 (0x18fc00 → 0x18fae8), so ages survive the wrap. O
2. For every list (global set, then each live group), 0x18f6e0 walks from the oldest
   particle and retires while `birth + life < clock`, i.e. a particle is drawn for ages
   0 … life inclusive and gone at age life + 1. Lists are FIFO because every particle of a
   list has the same lifetime, so the walk stops at the first one still alive. A retired
   particle gets +0xe = 0; its definition's count drops and at 0 the slot is freed (+4 = −1,
   0x82c408[slot] = −1). Emptied pages go back to the free list. O 0x18f7a0–0x18f918
3. A group whose lists were all empty on more than 31 consecutive ticks is freed (32nd empty
   tick); during a cutscene the count is held at 0. O 0x18fa2c–0x18fa90
4. `particleGroup_free` 0x18ea90 gives a group's pages back but does not lower the live
   counts of the definitions whose particles were in it, so a group freed by its owner
   while it still holds particles keeps those definitions resident (their slots stay used)
   until the level reset 0x18ebb8 clears slots 1–31. O for the code; that an owner frees a
   non-empty group was not looked for (U)

So a particle has **no per-particle lifetime**: it lives exactly 11, 30, 60 or 90 ticks
after its (possibly back-dated) birth, and its end colour and size are reached at that age.

**Texture animation.** `particle_draw` 0x194888, once per draw-task call while the game is
not frozen, steps the u of every resident type whose v row is 1, 2 or 4 by one cell
(0x200 = 32 texels) with wrap after 16 cells (0x2000): rows 1 and 2 step when `g_simFrame`
is even, row 4 on every call. It changes the shared record, so every particle of that
definition shows the same frame, and a definition that loses its slot restarts at its base
cell the next time. O 0x194930–0x194980. This reads `g_simFrame` and runs per rendered
frame (cosmetic).

## 5. Emitters placed in levels (`.world` chunk flag 0x4000)

`world_fixup` 0x181d30 keeps up to 16 distinct emitter types per level in
`g_worldEmitterTypes` 0x7d35e8 (0x98 bytes each: the chunk's 0x48 data bytes, then a
particle definition at +0x48). Two chunks share a type when their first 0x11 bytes are
equal (0x195318). The definition is built with `particleDef_set` from those bytes
(0x1820c4–0x18215c); the chunk's +4 holds the type index. A 17th distinct type is not
created (U what such a chunk then does; its +4 is not written at 0x1820d0 — I).

Emitter record, 0x48 bytes (the chunk's data) — O from 0x1820d4 (bytes 0–0x10), 0x195400
(the rest):

| Offset | Type | Meaning | `AddParticle` key |
|---|---|---|---|
| 0x00–0x03 | u8 × 4 | start colour r, g, b, a | `psr psg psb psa` |
| 0x04–0x07 | u8 × 4 | end colour r, g, b, a | `per peg peb pea` |
| 0x08 | s16 | sizeStart (as a float) | `pss` |
| 0x0a | s16 | sizeEnd | `pes` |
| 0x0c | s16 | gravity | `pgr` |
| 0x0e | u8 | lifeClass | `plf` |
| 0x0f | u8 | kind | `prm` |
| 0x10 | u8 | tile | `ptx` |
| 0x11 | s8 | rate: n > 0 spawns n particles per run; n < 0 spawns one when `now mod |n| = 0`; 0 none | `bcn` |
| 0x12, 0x14 | s16 × 2 | offset x, y (turned by the caller's yaw; 0 for level chunks) | `bxo byo` |
| 0x16 | s16 | offset z | `bzo` |
| 0x18, 0x1a, 0x1c | s16 × 3 | base velocity x, y, z | `bvx bvy bvz` |
| 0x1e | u16 | yaw of the emitter (angle16) | `byw` |
| 0x20 | u16 | pitch (rotation about y) | `bpt` |
| 0x22, 0x24, 0x26 | u16 × 3 | box: each particle is placed uniformly in ±ext/2 | `box boy boz` |
| 0x28 | s16 | speed spread: speed += (r − 0.5) × spread along the base direction | `bvr` |
| 0x2a | s16 | cone: tilt up to this angle16, about a random axis | `bar` |
| 0x2c | s32 | on time in ticks (0 = always on) | `bot` |
| 0x30 | s32 | off time in ticks | `bft` |
| 0x34 | u8 | bit 0: direction from the weather angle 0x4f66a0 and spawn only while 0x4f66a4 ≠ 0; bit 1: direction from the emitter's own yaw/pitch without the mirror flags | `bwa` (1), `bfa` (2) |
| 0x38 | s32 | run time: tick of the next on/off switch | — |
| 0x3c | u8 | run time: on | — |
| 0x3d | char[] | short name (world.md) | — |

The same 0x48-byte layout is the emitter record of the `AddParticle` helper objects that
props, chests and `AutoEmitter` objects carry (helper +0x64; `docs/monsters-2.md` section 9
lists the property keys, shown in the last column). Correction to that section: `pea`, `plf`,
`prm` and `ptx` are all passed to `particleDef_set` — end alpha, life class, kind and tile
(loads at 0x240424, 0x2403f4, 0x240400, 0x240428; call 0x24043c). So an object emitter and
a level emitter chunk are the same contract; the helper calls the same runner from its slot
18 (0x240c68, 0x240c94) with its own position, yaw and direction.

`world_runEmitterChunk` 0x18b810 (called only from `world_drawChunk` 0x1887b8, at
0x18882c: so per **drawn** chunk and per rendered frame) copies the chunk's
timer (+0x20) and on bit (+4 bit 31) into the record, calls the runner
`emitter_run` 0x195400 with `now = g_simFrame`, yaw 0, the position = chunk translation ×
0.25 and the chunk's quarter-turn bits (+0x34 bits 16, 17, 18: negate x, negate y, swap
x and y), and copies the state back. O

`emitter_run(pos, def, rec, now, yaw, negX, negY, swapXY)` — O 0x195400:

```
count = rate>0 ? rate : rate<0 ? (now % |rate| == 0 ? 1 : return) : 0
if rec.next < now:
    if rec.on_time == 0: on = 1
    else:
        d = on ? rec.off_time : rec.on_time         # length of the period that starts now
        next = trunc(now + d + (r() - 0.5) * d)     # r() = one cosmetic draw
        on = !on
if !on or count <= 0: return
repeat count times:
    o = ((r()-0.5)*ext.x, (r()-0.5)*ext.y, (r()-0.5)*ext.z)          # three draws, x y z
    M1 = identity; rotateAxis(M1, Z, yaw + rec.yaw); rotateAxis(M1, Y, rec.pitch)
    o = M1 · o
    o.x += off.x*cos(yaw) + off.y*sin(yaw);  o.y += -off.x*sin(yaw) + off.y*cos(yaw)
    apply negX / negY / swapXY to o.xy
    p = pos + (o.x, o.y, o.z + off.z)
    v = base velocity; v += normalize(v) * (r() - 0.5) * spread
    M2 = identity; rotateAxis(M2, Z, (s16)(seed >> 16)) ; rotateAxis(M2, Y, (s16)(r() * cone))
    v = M2 · v                                  # the Z draw uses the seed's top half as an angle
    if flags & 1:  v = (rotZ(weatherAngle) then rotY(rec.pitch)) · v
    elif flags & 2: v = (rotZ(rec.yaw) then rotY(rec.pitch)) · v
    else:          v = M1 · v, then negX / negY / swapXY on v.xy
    if !(flags & 1) or weatherOn: particle_spawn(0, def, p, v)
```

`r()` is `seed = seed × 0x19660d + 0x3c6ef35f; return (seed >> 16) / 65536`. `rotateAxis`
and `M · v` are `mat34_rotateAxis` 0x163000 and `mat34_transformPoint` 0x1660a0, exactly as
`docs/spec/core.md` gives them (row operations, `v.x·row0 + v.y·row1 + v.z·row2`). The draw
order above is the order of the code (0x195610–0x195a2c). Its three callers are 0x18b8d4 (level chunks) and 0x240c68 / 0x240c94 (`AddParticle_emit`).

Note: because the level runner is reached from drawing, an emitter that is not on screen
emits nothing and its on/off timer does not advance (I).
