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

### Getting the definitions

The 362 static definitions take constant arguments, so their values can be read from the
executable instead of copied: `python3 -I tools/fx_particle_defs.py SLUS_209.73 [--json]`
prints every call site of `particleDef_ctor` / `particleDef_init` / `particleDef_set`
with the definition address, the 16 arguments and their meaning. On v2.00 it resolves 369
of the 380 call sites; the other 11 take their values from data at run time (level
emitters 0x18215c, `AddParticle` 0x24043c, `particles_configure` 0x202b5c, weather
0x1d7bd8 … 0x1d879c, script `setParticle` 0x146e08, and the three inside the particle code
itself). Keep its output under `local/`. Counts on v2.00 (resolved definitions): kind 0
128, kind 1 172, kind 2 53, kind 3 19; life class 11 ticks 36, 30 ticks 135, 60 ticks 142,
90 ticks 59. Colour arguments are plain ints and some lie outside 0–255 (start alpha
300, end colour −77 occur); the clamp of section 4 handles them. O for the counts (tool
output), I that the 19 kind-3 definitions are never visible.

## 6. Glow sprites — O `glow_add` 0x18fc78, `glow_draw` 0x1907d0

`glow_add(bias f12, size f13, pos a0, r a1, g a2, b a3, a t0, texture t1, angle t2,
flags t3)` appends a 0x20-byte record to `g_glowQueue` 0x7d8b00 (count 0x82cc94, at most
0x400 per frame; the 0x401st is dropped). The queue is drawn and emptied by the particle
draw task: `glow_draw(1)` before the particle packet (sort key 4), `glow_draw(0)` after it
(sort key 3); flags bit 2 picks the pass.

Per glow:

```
p'  = pos − cameraForward × bias          # cameraForward = column 2 of g_cameraMatrix
q   = g_viewProj · p' ;  depth = q.w + bias
drop unless depth ≥ 20, |q.x| ≤ 700·depth, |q.y| ≤ 300·depth
centre = (q.x, q.y) / depth ;  Z from p'          # bias moves only the depth value, toward the camera
h   = size / depth                                 # pixels of the 1280 × 448 buffer
flags bit 0 clear: sprite from centre − (2h, h) to centre + (2h, h)
flags bit 0 set:   quad turned by `angle`: corners centre + (∓2h·c, ∓h·s), (±2h·s, ∓h·c)  (c, s of angle16)
UV: texel (1, 1) to (width − 1, height − 1) of the texture
```

Colour = the four bytes as the vertex colour (0x80 = unmodified texel; modulate). Flags
bit 1: `ALPHA_1` 0x48 (additive), else 0x44. `TEST_1` 0x71001, bilinear (`TEX1_1` 0x61).
Records with the same texture and flags are drawn in one packet. O 0x1907d0–0x190fe8.

`glow_add` is called from draw code and from some run functions (Fire, below); a record
queued during a tick is drawn at the next draw-task call.

## 7. Trails and beams

### Trails — O 0x190ff8–0x192840

64 trails of 0x410 bytes at 0x82cd00:

| Offset | Type | Meaning |
|---|---|---|
| +0x000 | 128 × {s16 2x, 2y, 2z, s16 stamp} | ring of points; positions in half units |
| +0x400 | u16 | handle (generation << 8 \| index), 0 = free |
| +0x402 | s16 | trail clock (+1 per tick) |
| +0x404, +0x405 | u8 | oldest point, next free point (ring of 128) |
| +0x406 | s8 | texture row (below) |
| +0x407 | u8 | flags: 1 the update does not age it; 2 points come in pairs; 4 additive (`ALPHA_1` 0x48); 8 `ALPHA_1` 0x09 (`src + dst × As`); else 0x44; 0x10 the clock does not advance |
| +0x408 | s16 | point lifetime, ticks = trunc(60 × seconds) |
| +0x40a…+0x40d | u8 × 4 | colour |
| +0x40f | u8 | width / 4 |

- `trail_create(lifetime s f12, row a0, width a1, flags a2, r a3, g t0, b t1, a t2)` →
  handle or 0 when all 64 are used. `trail_setColor` 0x191100, `trail_setWidth` 0x1911a8,
  `trail_release` 0x192800 (frees at once).
- `trail_addPoint(handle, pos)`: stamp = clock + 1; the point is not added when the ring
  would be within two of full.
- `trail_updateAll` 0x192840, from `particle_updateTask` each tick: for every live trail
  without flag 1, clock += 1 unless flag 0x10, then oldest points are dropped while
  `clock − stamp ≥ lifetime` (two at a time with flag 2). A trail that has **no point
  left** — or never had one — is freed by this update. So a trail lives as long as its
  owner keeps adding points.
- Drawing (`trail_drawAll` 0x193ad0 → 0x193b64, VU 0x28, 0x26 or the separate program at
  0x79e for flag 2): the texture is `engine.lmp` : `trail.tex`. Across the trail the v
  range is row r of the table at 0x44fca8: rows start at texel 0, 32, 64, 96, 128, 224,
  256, 288, 351 and each ends one texel before the next start (row 8 ends at 446).
  Along the trail u = age × 128 / lifetime. The width constant handed to the program is
  40 × (+0x40f) (0x193b64); the half-width on screen is that over w (render-pipeline 4.11,
  I for the unit). O for the table and the flags.

### Beams — O 0x193088–0x193440, 0x192a40–0x193040

20 beams of 0x734 bytes at 0x7e30d0. `beam_create(jitter f12, scale f13, from a0, to a1,
width a2, depth a3, rgba t0)` makes two trails (lifetime 1 s, row 0, flags 5) and a tree
of offset nodes (0x1c bytes each: offset xyz, drift xyz, frames until the next target);
depth is clamped to 5. The node offsets start in ±jitter and halve per level; the counter
of each node comes from libc `rand() & 7` (a third generator, cosmetic). Every draw
(unless frozen) each node drifts by its drift and, when its counter runs out, picks a new
target in ±jitter (cosmetic seed) and sets drift = (target − offset) × 0.1, counter =
`(seed >> 21) & 7`. The beam is rebuilt each draw by recursive midpoint displacement:
midpoint = (a + b) / 2 + node offset + (2r − 1) × amplitude × scale, amplitude halving per
level; points go into one trail on even `g_drawFrame` and the other on odd. `beam_update
(handle, from, to, alpha, width)` moves the ends, sets both trails' alpha and keeps the
beam alive until `g_simFrame + 2` (`g_netFrame` if it was created inside a simulation
tick); a beam not updated is destroyed by the next draw after that frame. O

## 8. Floor decals — O `decal_add` 0x19f110, `decal_drawTask` 0x19f4e8

`decal_add(size f12, pos a0, angle16 a1, type a2, grow a3)`.

1. **Option gate** (`g_decalDetail` 0x44fdc0, the user's gore / detail setting, 0–2):
   at 0 only types ≥ 3 are made; at 1 every type but 0; at 2 all. O 0x19f174–0x19f198
2. **Grid**: cell = ((trunc(x) + 3840) >> 8, (trunc(y) + 3840) >> 8), both must be 0…29.
   So decals exist only inside the square ±3840 around the world origin; one outside is
   dropped. O 0x19f1a0–0x19f1d0
3. A cell takes a block from 64 blocks of 0x180 bytes (0x840450, free list through +0x170)
   and holds at most 15 decals; a full cell or no free block drops the decal.
4. The decal is three qwords (0x18 bytes of s16): colour = the **light at the position**
   (0x148ff0, `docs/lighting.md` 7; alpha 0x80), centre × 4 with z + 3 units, a "counted"
   flag (1 for types < 3), (cos, sin) × size × 4, and the VU address of its texture
   rectangle, 0x3d3 + 2 × type. The colour is taken once, when the decal is made. O
5. `grow` ≠ 0 registers the decal in one of 16 growing slots (0x840310, 0x14 bytes): its
   size starts at 0 and `decal_drawTask` adds 0.2 (grow 1) or 0.05 (grow 2) per draw-task
   call while the game is not frozen, until it reaches `size`. O 0x19f45c, 0x19f540–0x19f5f0

Drawing: texture `engine.lmp` : `floorsprite.tex`, 256 × 128 texels used; modulate,
`ALPHA_1` 0x44, `TEST_1` 0x5001d (alpha > 1, depth ≥) with depth writes masked, bilinear;
corners `centre ± (c, s, 0)` and `centre ± (s, −c, 0)` (render-pipeline 4.12). Cells are
culled with boxes from 480 below the camera height up to the camera height (0x44f040)
— I: a decal more than 480 units below the camera, or above it, is not drawn.

Texture rectangle per type (texels, from the table uploaded at 0x19f5f8–0x19f6c0; the
first texel is inset by half a texel) and who makes it:

| Type | Rectangle | Size | Made by (O call sites) | Reading (I) |
|---|---|---|---|---|
| 0 | (0, 0)–(64, 64) | 64 | `GutChunk_run` at rest (red), `Creature_deadUpdate` for cflag 0x40000, `Player_run` (grow 1) | red pool |
| 1, 2 | (64, 64)–(96, 96), (64, 96)–(96, 128) | 32 | `GutChunk_run`, `Creature_processDamage` (1 + rand&1), `Critter_run` | red splats |
| 3 | (64, 0)–(128, 64) | 64 | `GutChunk_run` at rest (green), `Creature_deadUpdate` cflag 0x2000 | green pool |
| 4, 5 | (96, 64)–(128, 96), (96, 96)–(128, 128) | 32 | the same, green; `SpiderQueen_run`, `PoisonProjectile_run` | green splats |
| 6 | (128, 0)–(192, 64) | 64 | `GutChunk_run` at rest (yellow), `Creature_deadUpdate` cflag 0x1000, `SmallSpider_setState` | yellow pool |
| 7, 8 | (128, 64)–(160, 96), (128, 96)–(160, 128) | 32 | the same, yellow; `DiseaseProjectile_run`, `Critter_run` | yellow splats |
| 9 | (0, 64)–(64, 128) | 64 | 18 sites: player and monster projectiles, chests and containers, `Clockwork`, `Droid`, `Zek`, `GroundPoundEffect`, `FireStormFlare`, `FireBomblet` | scorch / impact mark |
| 10 | (192, 0)–(256, 64) | 64 | `Creature_deadUpdate` cflag 0x4000 (grow 1), script `addExpandingPool` (grow 2) | pool of the 0x4000 material |

Decals are saved with the level (`decal_serialize` 0x19ee10, `decal_loadList` 0x1a00b0).

## 9. Gore, hits and deaths

### Body material

The creature flags (cflags, creature +0xa8, `docs/creatures.md`) choose the hit and death
visuals. From the branches of `Creature_processDamage` 0x110d30 and `Creature_deadUpdate`
0x1108a0 (O for the branches; the colour names are I from the definitions they use):

| cflag | Hit burst (`fx_spawn`) | Gib / drop bits | Corpse pool | Colour |
|---|---|---|---|---|
| 0x40000 | 0 (or none at gore 0 offline) | 0 / 1 | type 0, grow 1 | red |
| 0x1000 | 9 | 3 | type 6 | yellow |
| 0x2000 | 3 | 5 | type 3 | green |
| 0x4000 | 10 | — | type 10 | ice-blue (I: the frost burst) |
| 0x8000 | 0xb | — | — | dark smoke |
| 0x10000 | 2 | — | — | dust |
| 0x20000 | — (sound, then 50 kind-2 sparks of definition 0x5bf608) | — | — | metal sparks |

The corpse pool is laid on the animation event 0x80 of the dead creature, at position +
offset, size = height + (own draw % 10), angle from the creature's own generator; never
when the caller passes "no blood". O 0x110a00–0x110b00

### GutChunk — O 0x201958, 0x1edb18, 0x201b88

A `PhProp` (physics prop) using `gutchunks.vif`, made by `Creature_processDamage` (bits 5,
3, 1 or 0), `Player_processDamage` (1), `Gnaw` / `GnawSpawn` and, through
`GutChunk_ctorFromProp` 0x201ad0, by eight monster "lose a body part" functions. Bits at
+0x248:

| Bit | Meaning |
|---|---|
| 1 | an invisible blood drop: never drawn; deleted on its first bounce. **Forced on when `g_decalDetail` < 2** |
| 2 | yellow (particles 0x870408, splats 7/8, pool 6) |
| 4 | green (particles 0x870458, splats 4/5, pool 3); neither: red (0x8703b8, 1/2, 0) |
| 8 | no decals |

Each run: physics; while the vertical speed (+0x1c4) is above 1 and gore ≥ 1, on one call
in three (own generator) one particle of its colour at its position, velocity 0; a
bit-1 drop lays one splat (size 12) as it comes down; on a bounce (vertical speed turning
from negative to positive) a sound when the impact was faster than 1, then a bit-1 drop
deletes itself, otherwise a splat (size 12) while +0x25c (starts at 2) lasts; once at
rest (both horizontal speeds below 0.1) one pool (size 12, grow 1). Splats need ground
below (`terrain_height` radius 8 above −10000). `GutChunk_draw` draws the prop only when
bit 1 is clear and (gore ≠ 0 or offline).

So with gore below 2 nobody sees a gib: the chunks become invisible drops that leave a
particle trail and one splat. Gore 0 (offline) also removes the type 0–2 decals and the
blood bursts 0 and 1.

### Other death visuals

`fx_disintegrateModel` 0x1f4340 (hides the model, plays a sound, turns its vertices into
particles), `fx_shatterToLooseIce` 0x1fb240 (frozen creatures; draws the shared seed —
`docs/gameplay.md`), and the per-class "lose part" functions above. Not read further (U
for their particle recipes; their definitions are listed by `fx_particle_defs.py`).

## 10. One-shot effects: `fx_spawn(id, pos)` 0x1ef270

Every id but 5 returns at once unless `pos` is within 480 units of the camera focus
(`isNearCameraFocus480`, per machine and cosmetic). The 23 definitions it uses are made
on first call (0x1ef2a8–0x1efe5c). Common recipe, O for each case:

```
centre = pos + (rand % J − J/2) per axis  [+ z lift]      # integer jitter from the seed's top half
repeat N:
    u = random point in the unit ball (rejection: three draws 2r − 1 until |u| ≤ 1)
    vel = u × S            (some ids add a common direction, below)
    p   = centre + (rand % P − P/2) per axis
    particle_spawn(0, def, p, vel)
```

| id | Callers (examples) | J (z) | N × definition, S, P |
|---|---|---|---|
| 0, 1 | `Creature_processDamage` (red blood). Return at gore 0 | 12 | 300 × 0x8704a8 (id 0) or 0x8704f8 (id 1, same look, 90 ticks); vel = u × 7.86 + d × r, d = one random unit vector × 34 (+4 z); P 0; plays one of four sounds |
| 9 | yellow blood | 12 | as id 0 with 0x86fc38 |
| 2 | dust: projectiles, `LavaBomb`, `Skelight`, `FatCyclops`, cflag 0x10000 | 24 (z 36) | 150 × 0x4f8710, S 10.45, P 12 |
| 3, 6 | green blood (`Creature_processDamage`, `MummySnake`, `SpiderQueen`); 6 `PoisonProjectile` | 12 (z +18) | 150 × 0x86fcd8, S 10.16 (id 6: y and z × 16) |
| 4 | — | 12 (z +18) | 150 × 0x86fd28, S 16, P 24 |
| 5 | `MissileWeapon`, `LooseFire_ctor` | 12 (z 0…17) | 3 or 4 `Fire` objects; **shared seed** (`docs/gameplay.md`) |
| 7 | `Skeleton`, `Skelight`, `Zek` | — | 3 × 0x86fd78, S 4.75 |
| 8 | fire arrows / multi-fire / missiles | 24 (z 36) | 300 × 0x86fe18, S 10.45, P 24 |
| 10 | frost: `IceBall`, `SnowballSpell`, `ColdArrow`, `FrostShard`, `ShockOfFrost`, `FrostArmor`, cflag 0x4000 | 12 (z +18) | 25 × 0x86fe68 S 5.45 P 24, then 80 × 0x86feb8 S 20 P 24 |
| 0xb, 0xc | cflag 0x8000; `DiseaseBolt` | 12 (z +18) | 15 × 0x86ff08 S 5.45, 20 × 0x86ff58 S 40 (P 24); id 0xb adds 5 × 0x86ffa8 |
| 0xd, 0xe, 0xf | `MummySnake`, model-vertex spawners | point within 15 | 1 × 0x86fff8 / 0x870048 / 0x870098, vel 0 |
| 0x10 | `Creature_run` | point within 15 | 1 × 0x8700e8, vel 0 |
| 0x11 | knockback, `MissileWeapon`, `Player_run`, props | — | 1 × 0x870188 at pos, vel 0 |
| 0x12 | `Creature_run` | point within 15 | 1 × 0x870138 |
| 0x13 | `LightningBolt`, `LightningRod` | — | 1 × 0x8701d8 (kind 2) S 21.6, then 0x870228 at a quarter of that speed |
| 0x14 | `LavaMonster` | — | 3 × 0x86fdc8, S 4.75 |
| 0x15 | `RedDragon` | — | 5 × 0x870278 and 5 × 0x8702c8 (S 24) |
| 0x16 | `Droid` | — | 0x870318 (vel × 5, z × 25) and 0x870368 (× 1.28, z × 24.7) |

"point within 15": a random angle and radius r × 15 in x y and (r − 0.5) × 15 in z.
`fx_spawn` reads `rand % J` from `seed >> 16` (integer modulo), not from the float r().
O for the counts, speeds, jitters and definitions (decompile of 0x1ef270); the reading of
each id from its callers is I. Not read: the direction terms of ids 7, 0x14, 0x15 and
0x16 beyond their speeds (U).

### Fire — O `Fire_run` 0x1f34e0, `Fire_ctor` 0x2020e0

100 ticks. Each tick one glow (bias 5, size 8000 + 250 × sin(g_simFrame × 1024), colour
(255, 150, 0), alpha 60, fading in over the first 20 ticks and out over the last 20 by 3
per tick; texture 0x4f848c; flags 0) and one particle of 0x870548 at pos + (2u.x, 2u.y,
|2u'.z|) with velocity (2u.x, 2u.y, 2u.z + 4.8), u and u' unit-ball points from the
object's own generator.

## 11. Skill and spell visuals: how they are chosen and timed

**Chosen by code, not data.** A skill id selects a `Skill` object (`g_skillTable` 0x41b170,
`docs/skills.md`); its `cast` allocates the effect classes (a `Spell` on a creature, a
projectile or area `GameObject`, or both), and each class draws its visual with the
primitives of this document using the particle definitions its own source file registers
in a static initialiser. There is no visual id, effect table or data file between a skill
and what it shows. O (call map below; `docs/skills.md` "How the pieces fit")

**Timing.** Everything a class does is tied to its gameplay calls, all inside the
simulation tick except `draw`:

| Phase | When | Visual work done there |
|---|---|---|
| `Skill*_cast`, `*_ctor`, `*_initCommon` | the tick the cast happens. A player's cast fires on the tick its cast animation's blend weight reaches 1.0, or 0.5 in a net game (`docs/skills.md`, "How a cast happens", 0x1ab6f4–0x1ab7dc); monsters cast from their state machine; weapon procs inside the damage function | flash `LightEffect`s, trails created, particle groups made, the class's own light node linked |
| `*_run` (Spell slot 2 from `Creature` slot 17 / `Player_updateCast`; GameObject slot 4) | every simulated tick of the effect's life | the steady particles, trail points, beam ends, light node radius / position |
| `*_draw` (GameObject slot 5; Spell slot 3 only for Drowsy, SummonBadger, Resurrect) | every rendered frame | glow sprites |
| `*_onHit`, `*_onContact`, `*_explode`, `*_end`, `*_absorb`, `*_applyToHit`, `*_trigger` | the tick of the impact / expiry / absorption, in the same call that applies the damage or status | bursts (`fx_spawn`, `fx_ringBurst`), impact lights, decals |

So a renderer that mirrors the simulation can start each visual on the tick the code
does; nothing is delayed or interpolated beyond what the particle ages give. The
particles themselves live on the particle clock (section 4), the beams and light chunks on
`g_simFrame`, glows and decal growth on rendered frames.

The call map below was made by `tools/fx_callsites.py <elf> map 2c3cd4 320000` (calls of
each primitive per function, from the instruction stream; names from `symbols/`). Legend:
P `particle_spawn`, L `LightEffect`, G `glow_add`, T `trail_create`, t `trail_addPoint`,
B `beam_create`, b `beam_update`, D `decal_add`, F `fx_spawn`, R `fx_ringBurst`, V / M / m
model-vertex emitters (`fx_emitFromModelVerts`, `fx_modelParticlesNearCamera_1f61c0` with
light, `_1f5210`), n the class links its own light node, g a particle group, p
`fx_impactPuffNearCamera`. A class whose functions call none of these (for example most
passive skills) is not listed. O for the calls; which phase a helper belongs to is I from
its name and caller.

| Class | At cast (ctor / cast) | Each tick (run) | Each frame (draw) | At an event |
|---|---|---|---|---|
| `ShockProjectile` | n ctor | BPb run | G draw |  |
| `StaticFire` | n ctor; n ctor2 | P run | G draw |  |
| `GroundPoundEffect` | n ctor | DLP run |  |  |
| `SpellCharge` | Tnt ctor | Pt run |  | FP onContact |
| `DiseaseBolt` |  | FP run |  |  |
| `DiseaseTrail` |  | P run |  |  |
| `SpellDiseaseTrail` |  | P run |  |  |
| `SpellDiseaseShield` |  | GP run |  |  |
| `DiseaseCloud` |  | P run |  |  |
| `DarknessProjectile` | n ctor | P run |  |  |
| `SpellConvertEnemy` | g ctor | P run |  |  |
| `SpellConvertUndead` | g ctor | P run |  |  |
| `SpellCyclone` | n ctor | P updateFx |  |  |
| `SpellHarmTouch` |  |  |  | LP applyToHit |
| `FireStormFlare` |  | DP run |  |  |
| `FireStorm` | L initCommon; n ctor; n ctor2 |  |  |  |
| `SpellDiseaseEffect` |  | G run |  |  |
| `FireArrowProjectile` | n ctor; n ctor2 | p run | G draw |  |
| `ColdArrowProjectile` | n ctor; n ctor2 | P run |  | F onHit; P end |
| `PoisonArrowProjectile` | n ctor; n ctor2 | P run |  | P end |
| `SkillMultiFire` | L cast |  |  |  |
| `MultiFireProjectile` | Tt ctor | Pt run |  | F end |
| `ExplodeArrowProjectile` |  | P run |  | FLR explode |
| `FireFlare` |  | P run |  |  |
| `SpellFireFlares` | n ctor |  |  |  |
| `SkillRiposte` |  |  |  | P counterAttack |
| `SpellBash` |  | L run; P windupFx |  |  |
| `SpellBlessed` | n ctor | GP run |  |  |
| `SpellAncestralCall` | Lg ctor | BPb run; M tintAndGlow |  |  |
| `SkillSummonSkeleton` | P cast |  |  |  |
| `SpellLightningWeapons` | L ctor | M run |  |  |
| `SpellFireWeapons` | n ctor | P run |  |  |
| `SpellColdWeapons` | L ctor | P run |  |  |
| `SpellRoot` | g ctor | P run |  |  |
| `SpellCriticalHit` | gn ctor | P run |  |  |
| `SpellHolyShield` | g ctor |  |  | LP absorb |
| `SpellHealing` | g ctor | P run |  |  |
| `SpellConeOfFrost` | n ctor | P run |  |  |
| `SpellUndeadShield` | gn ctor | P run |  |  |
| `SpellSecondaryUndeadShield` | g ctor | P run |  |  |
| `HolyStrike` | Tt ctor | LPt run | G draw |  |
| `HammerOfWrath` |  | P run |  |  |
| `SkillHammerOfWrath` | L cast |  |  |  |
| `SpellConeOfFire` | n ctor | P run |  |  |
| `SpellWizardBeam` | T ctor |  |  |  |
| `BlindingLightEffect` | L ctor | P run |  |  |
| `SkillRepulseUndead` | L cast |  |  |  |
| `HolyBolt` | Tnt ctor | Pt run |  | LP onHit |
| `FrostShard` |  | FP run |  |  |
| `ShockOfFrost` | n ctor | FP run |  |  |
| `PoisonRain` | L ctor | LP run |  |  |
| `SpellShieldBash` |  | L run; P windupFx |  |  |
| `SpellPlanarSteelEffect` | n ctor | GP run |  |  |
| `SpellHornOmenEffect` | g ctor | P run |  |  |
| `SpellUnspokenWord` | L cast; T ctor | P run |  |  |
| `SpellSummonAxe` | L cast; g ctor | P run |  |  |
| `SpellSummonArrows` | L cast; g ctor | P run |  |  |
| `SpellRoar` |  | P run |  |  |
| `SpellBattleCry` |  | LPg run |  |  |
| `SpellBloodLust` |  | GP run |  |  |
| `SpellArena` |  | P run |  |  |
| `SkillStrongStance` |  |  |  | LP trigger |
| `SkillStunningStrike` | L spawnEffect |  |  |  |
| `SpellGiantGrowth` | gn ctor | P emitParticles |  |  |
| `SpellPlanarWind` | n ctor | P run |  |  |
| `PusStorm` | Ln ctor |  |  |  |
| `Pustule` |  | P run |  |  |
| `SpellTagarsInsects` |  | P run; P tickVictims |  |  |
| `SpellDrowsy` | L cast | P run |  |  |
| `PoisonBolt` | n ctor | P run |  | P burst |
| `SpellSummonBadger` | L cast | P run | G draw |  |
| `SpellShadowStep` | LP ctor |  |  |  |
| `SpellResurrect` | n ctor | V run | G draw | L onOwnerDeath |
| `SpellRaiseArmy` | L cast | P run |  |  |
| `SpellRetribution` | gn ctor | V run |  |  |
| `SpellSpiritShield` | L ctor | P dissolveParticles; P reformParticles |  |  |
| `SpellPoisonWeapons` | L ctor |  |  |  |
| `SpellWaveOfFlame` | L ctor | P run |  |  |
| `SpellFrostArmor` | L ctor | P run |  | F onHit |
| `SpellDiseaseBlade` | L ctor |  |  |  |
| `SkillFireAxe` | L cast |  |  |  |
| `SkillColdAxe` | L cast |  |  |  |
| `LightningStrikeSpell` | Ln ctor |  |  |  |
| `SpellConeOfShock` | n ctor |  |  |  |
| `SmokeGen` |  |  | G draw |  |

`tools/fx_callsites.py <elf> args LightEffect 2c3cd4 320000` lists every flash with its
start and end colour, radii, floor and duration (stack arguments as floats), and `args
particle` the definition used at each spawn; together with `fx_particle_defs.py` that is the
whole of a skill's look. Values are not reproduced here.

### Weapon element visuals — `fx_modelStatusEffects` 0x1f6ac8 (partly read)

Called from the weapon objects' updates (`Weapon1_slot21` / `_slot22`, `Weapon2_update`),
`Player_weaponTrails` 0x1bc768, `playerProjectile_draw`, `MissileWeapon_draw`, `Cyclops_run`,
`VampireLord_run` and `Innoruuk_run`. It looks through the four effect entries of the item
(+0x24, 8 bytes each, the damage effect block of `docs/gameplay.md` 2.2) for the codes
0x18 lightning, 0x16 cold, 0x15 fire, 0x17 poison and 0x26 disease, and for each one present
emits particles at the weapon's sample points, the amount scaled by the entry's value: O
for the codes and the definitions used per block (lightning 0x870958; cold 0x870ae8,
0x870b38, 0x870b88; fire 0x870a48 / 0x8709f8, 0x870a98; poison 0x870cc8, 0x870d18; disease
0x870d68, 0x870e08, 0x870db8), not read further (U for counts and placement). It also
creates a swing trail (0.2 s, row 3, width 1000, flags 2 = paired points, colour 0x80 grey
— 0x1f6ff0) and can call `fx_spawn(0x11)` and a glow. Level flag 0x10000000 turns it off
(0x1f6b2c). The glowing weapon shell drawn by the model code is in render-pipeline 4.8.
