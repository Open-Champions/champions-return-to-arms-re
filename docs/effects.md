# Visual effects: particles, emitters, glows, trails, beams, decals, gore

Status: first pass 2026-10-17, read from the disassembly and a Ghidra decompile of
`SLUS_209.73` (v2.00); **round 2, 2026-10-18: run against the original** — the functions
were executed in `tools/ee_emu.py` (and the vertex programs in `tools/vu1_emu.py`) and the
references difftested, sections 12–18; corrections to sections 1–11 are listed in section
17, and a round-2 note at the head of a section points there. Nothing was run on a live
game. Each claim is **Observed** (O, read at the address given), **Inferred** (I),
**Unknown** (U) or **Executed** (E, with the difftest property). The reference contracts
are `tools/ref_particles.py`, `tools/ref_fx_render.py`, `tools/ref_fx_recipes.py`,
`tools/ref_fx_skills.py`, `tools/ref_decals.py` and `tools/ref_fx_props.py`.

This document is for a renderer that wants to draw what the game draws. It extends
`docs/engine.md` ("Particles, glows, trails, beams", skimmed there) and the GPU side in
`docs/spec/render-pipeline.md` sections 4.10–4.12, 6 and 7, which it does not repeat.
Lights are in `docs/lighting.md`.

Everything in this document is cosmetic: it draws from `g_cosmeticSeed` (0x404460), not
from the shared seed, unless a line says otherwise (`docs/engine.md`, P1 and "Checked and
found clean"). *Round 2: not so for the effect classes of skills and for `LightEffect`;
see 12.2 and section 17.*

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

*Round 2: executed bit for bit (16.1); the sheet height is answered in 13.9.*

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

*Round 2: slot 0 is never free (31 slots), back-dating rounds toward zero (16.1, 17).*

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

Fields are 16-bit: positions beyond ±32767 wrap. I: no level reaches that, since the light
grid, which must hold every lit place, spans ±11520 (`docs/lighting.md` 4). Velocities of
128 units per 16 ticks or more wrap; whether any caller passes one was not checked (U).

## 4. Motion, size, colour, death

*Round 2: what the vertex program draws, the kind-2 tail alpha and groups: 13.1, 13.2; pools: 16.1.*

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

*Round 2: `emitter_run` and the type definition executed (16.1).*

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

*Round 2: exact geometry and the GS order of the passes: 13.3, 13.7; textures: 14.2.*

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

*Round 2: exact strips, beams and their seeds, the trail builders: 13.4, 13.5, 13.8.*

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

*Round 2: `tools/ref_decals.py`, executed bit for bit (16.2).*

`decal_add(size f12, pos a0, angle16 a1, type a2, grow a3)`.

1. **Option gate** (`g_decalDetail` 0x44fdc0, the user's gore / detail setting, 0–2):
   at 0 only types ≥ 3 are made; at 1 every type but 0; at 2 all. O 0x19f174–0x19f198
2. **Grid**: cell = ((trunc(x) + 3840) >> 8, (trunc(y) + 3840) >> 8), both must be 0…29.
   So decals exist only inside the square ±3840 around the world origin; one outside is
   dropped. O 0x19f1a0–0x19f1d0
3. A cell takes a block from 64 blocks of 0x180 bytes (0x840450, free list through +0x170)
   and holds at most 15 decals; a full cell or no free block drops the decal.
4. The decal is three qwords (0x18 bytes of s16): colour = the **light at the position**
   (0x148ff0, `docs/lighting.md` 6; alpha 0x80), centre × 4 with z + 3 units, a "counted"
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

*Round 2: disintegrate, ice shatter and the part functions: 14.3–14.5.*

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

*Round 2: every id executed, direction terms included: 14.1 (this table has errors, section 17).*

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
per tick; texture 0x4f848c; flags 0) and one particle of 0x870548 at pos + (2u'.x, 2u'.y,
|2u'.z|) with velocity (2u.x, 2u.y, 2u.z + 4.8), u and then u' unit-ball points from the
object's own generator. The glow is queued from `run`, so it is drawn by the next draw
task.

## 11. Skill and spell visuals: how they are chosen and timed

*Round 2: recipes executed for all 161 effect functions of the skill files: section 15; not cosmetic: 15.2.*

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
model-vertex emitters (`fx_emitFromModelVerts`, `fx_shockModel` 0x1f61c0 (beam arcs; round 1 said "with
light"), `fx_burnModel` 0x1f5210), n the class links its own light node, g a particle group, p
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

*Round 2: fully executed, 14.6; the entry value does not scale the amount (section 17).*

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
— 0x1f76e4) and can call `fx_spawn(0x11)` and a glow. Level flag 0x10000000 (level flag word
0x44fe08) makes it return at once, as does a null second argument (decompile of the
first lines). The glowing weapon shell drawn by the model code is in render-pipeline 4.7
("Shell mode") and 6 ("Weapon glow shell").

## 12. Round 2: run against the original (2026-10-18)

Round 1 (sections 1–11) was written from reading. In round 2 the original functions were
**run** in `tools/ee_emu.py` — and, for what the vector unit draws, in `tools/vu1_emu.py`,
a Python port of the project's VU1/VIF model (`tools/recomp/render/vu1.cpp`, `vif1.cpp`)
that runs the microprograms of the user's own executable — and each reference was compared
with them on random states. "Executed" in sections 13–17 names the difftest property.
Floats are compared bit for bit unless a line says otherwise: the references do their
float work in the console's rounding (toward zero; `ref_particles.rz`, `tools/ref_core.py`).
What is still read-only is marked O / I / U as before. Nothing was run on a console or on
the Play! rig: the interpreters' last-bit arithmetic is an assumption (`tools/ee_emu.py`,
"Floating point"; 13.6).

Where each round-1 open item went:

| Round-1 open item | Answer | Section |
|---|---|---|
| Glow, trail and beam geometry (vertices, UVs, widths, segments, jitter and its seeds) | exact formulas, Executed | 13.4, 13.5, 13.7, 13.8 |
| Alpha of the second vertex of kind-2 lines | 0 (Gouraud line fading to the lagged end) | 13.1 |
| Skill-class recipes | 161 / 161 effect functions of the skill files executed; values read at run time by `tools/fx_skill_recipes.py` | 15 |
| Group-matrix rendering | `mat4_mulMat34(mat34_mul(group, view), P)` per live group | 13.2 |
| `fx_modelStatusEffects`, disintegrate, ice shatter, lose-a-part | Executed recipes | 14.3–14.7 |
| Direction terms of `fx_spawn` 7, 0x14, 0x15, 0x16 (and 6, 0xb, 0x12) | every id exact | 14.1 |
| Height of the particle sheet; glow textures 0x4f848c, 0x44fe04 | 512 × 160 used (5 rows of cells); `fx.lmp` : `halo2.tex`, `engine.lmp` : `halo1.tex` | 13.9, 14.2 |

### 12.1 Difftests

Each needs the user's own `SLUS_209.73` (v2.00, SHA-256 checked) and exits 0 without it;
`--quick`, `--seed N`, `-v` as in `tools/difftest_anim.py`. Counts are of the default run
(seed 20973 unless given).

| Tool | Properties | Compared | Mismatches |
|---|---|---|---|
| `tools/difftest_particles.py` | definition, redefine, spawn record, pools, emitter definition, flipbook, emitter | 4,000 + 1,500 definitions (44,699 floats), 6,000 spawn records, 60 pool sequences of 27,164 operations (spawn bursts to the slot and page limits, groups, cutscene ticks, the clock wrap) compared state by state, 2,000 emitter types, 3,000 flipbook steps, 4,000 emitter runs (positions within 4 × 10⁻⁵ relative: `math.cos` against `math_cos16`) | 0 |
| `tools/difftest_lighting.py` | object light, collect, model lights, floor tint, light chunk, light effect, level light | 6,757 object-light operations, 800 node sets × 4 positions, 1,500 model-light blocks (directions within 2.5 × 10⁻⁷), 1,500 floor tints, 170,841 light-chunk runs, 16,935 LightEffect frames; level light 28 cases (colours and base level exact, direction within 1e-5) | 0 |
| `tools/difftest_decals.py` | decals | 80 sequences, 48,100 operations (10,888 decals made, 25,176 dropped, 12,036 growth steps) | 0 |
| `tools/difftest_fx_props.py` | props | 400 objects, 30,013 ticks, 47,843 spawns, light node and generator every tick | 0 |
| `tools/difftest_fx_render.py` | particles, particle groups, trails, beams, glows, trail builders (EE side under the ps2 and chop FPU models), and particles / trails under vu1.cpp's WAITQ reading | particle cells 16,440 (ps2) + 4,560 (chop), of them in groups 10,950 + 2,910; trail vertices 13,000 + 3,384; under vu1.cpp's reading 2,820 cells and 6,470 vertices; 693 beam-frames; 1,912 glow packets; 1,250 builder calls | 0 |
| `tools/difftest_fx_recipes.py` | fx_spawn id 0 … 22, 23, −1; disintegrate; ice shatter; lose part × 8; emit from model verts; model sparkle; model arcs; model glow; weapon status (40) | about 190,000 particle, chunk and glow calls | 0 |
| `tools/difftest_fx_skills.py` | 21 properties over 25 functions (390 of 398 basic blocks), plus every call-out of the four existing skill difftests decoded as a primitive | 16,716 calls; 568,467 call-outs | 0 |

Synthetic unit tests (no game data): `test_vu1_emu.py`, `test_ref_fx_render.py`,
`test_ref_fx_recipes.py`, `test_ref_fx_skills.py`, `test_fx_skill_recipes.py`, `test_fx_level_lights.py`,
`test_ref_decals.py`, `test_ref_fx_props.py`, and the updated `test_ref_particles.py`,
`test_ref_lighting.py`.

### 12.2 What a native client needs from round 2

- The exact formulas are the references: `tools/ref_fx_render.py` (particle and group
  matrices, sprite and line vertices with `waitq_first=True`, which cells are sent, trail
  chunks and strips, beam nodes / drift / points / frame seed, glow projection and
  packets, the trail builders), `tools/ref_fx_recipes.py` (`fx_spawn`, status, death and
  part recipes), `tools/ref_fx_skills.py` (the 21 skill functions round 2 modelled; the
  other 140 are in the skill references), `tools/ref_decals.py`, `tools/ref_fx_props.py`.
- Values stay out of the repository: `fx_particle_defs.py --json` (definitions) and
  `fx_skill_recipes.py --json` (the constant effect arguments per class, plus embedded light
  records) read them from the user's executable at start-up.
- **Per-level light.** `fx_level_lights.py --json ELF` reads `g_levelTable` 0x4f7210
  (name, flag word, base level) and the default marker colours. Optional `objects.ob`,
  lump or GOB arguments add that file's marker sun, ambient and direction. The
  executable has no per-level colour or direction array (`docs/lighting.md` section 10).
- **`light_records`** (optional top-level object in the same JSON): the colour shorts, radius,
  falloff and +0x2c float the three constructors below store into their embedded 0x3c-byte light
  node before `light_link` (layout: **O** `docs/lighting.md` section 2; the same fields
  `ref_skills_c.light_record` writes). Position at +0x30 is filled at run time and is not
  emitted. Keys are the function names; each value has:
  - `colour`: eight unsigned shorts — model quad +0x0a..+0x10, level quad +0x12..+0x18;
  - `radius`: float at +0x1c (and +0x24, observed equal);
  - `falloff`: float at +0x20 (and +0x28); **StaticFire_ctor** and **StaticFire_ctor2** only;
  - `extra`: float at +0x2c (floor term for level geometry in `light_collectNear`).
  Scanned by straight-line constant tracking over the constructor bodies (**O** addresses):
  `StaticFire_ctor` 0x2c5240–0x2c54f8, light at object +0x80; `StaticFire_ctor2`
  0x2c54f8–0x2c5770, +0x80; `SpellPlanarSteelEffect_ctor` 0x2fb728–0x2fb924, spell +0x30
  (radius 0 at cast; falloff omitted). Synthetic coverage: `tools/test_fx_skill_recipes.py`.
- **Function bounds.** A call is reported only when its site belongs to a function whose
  start lies in the requested range. Those starts are the first column of `ghidra_funcs.tsv`.
  When that file is missing, or it lists no start in the range, the tool infers starts from
  `jal` targets, from the instruction after `jr ra` when it is an `addiu`/`daddiu sp, sp, -N`
  prologue, and from the addresses in `ref_fx_skills.RECIPES`. With an empty start list the
  JSON still has the class and phase rows and has no calls. **Observed** for the pinned
  scanner run from a `tools/` copy that did not contain `ghidra_funcs.tsv`.
- **Constants live on a skipped path.** `scan_calls` walks fall-through only, and a call
  clears the caller-saved registers. **Observed** in `SpellArena_run` 0x305bbc: `andi` of
  the particle index with 3 at 0x305d88, `beq` at 0x305e08. The index not divisible by four
  falls through to the particle call at 0x305e10; a multiple of four branches to the call
  at 0x305e28. An unconditional branch at 0x305e18 skips that second call on the
  fall-through. The straight-line walk therefore reaches 0x305e28 only after the first
  call has cleared `a0` and `f12`, and the JSON has those two slots null. They are the
  pair the native loader requires for that class (`needs()` ordinal 1, keys `a0` and
  `f12`). The tool fills a slot the straight-line walk left empty from the first path
  that reaches the call. A slot that walk already holds a value for is copied through
  unchanged. The same fill recovers `a0` and `f12` at `SpellPlanarWind_run` 0x30a71c
  and `a0` at `SpellTagarsInsects_run` 0x30d430. On the US v2.00 executable those five
  slots are the only ones that change. Address order of the arena calls is rest, then
  every fourth. The native comment labels ordinal 0 "every fourth" and ordinal 1
  "rest". **Observed.**
- **SpellHornOmenEffect group matrix** (**O** `SpellHornOmenEffect_run` 0x2fc684 calls
  `mat34_setPosRotZ` 0x163b30 then `particleGroup_setMatrix` 0x18e9e8 on the spell's group
  +0x1c): each tick the group matrix is the creature owner's world position (+0x10) and
  facing (`creature` +0x38, s16 angle passed to `mat34_setPosRotZ`). Particles are spawned in
  model space (sample points at origin, facing 0) and drawn through that matrix (13.2). The
  research model records the matrix argument as the token `'stack'` because the mat34 is
  built on the stack inside the callee, not passed as a constant.
- **Not everything here is cosmetic** (section 17): skill effect classes place particles
  with the object's or spell's own generator, which also rolls damage, every `LightEffect`
  (a `GameObject`) draws the shared seed in its constructor, `fx_spawn` id 5 and the ice
  shatter draw the shared seed, and `StaticFire` / `DiseaseCloud` deal damage from their
  "visual" run functions. A client must run those draws in the simulation even when it
  draws nothing; only the drawing may differ.
- Textures by name from the user's disc: `particletex.tex`, `trail.tex`, `floorsprite.tex`,
  `halo1.tex` (`engine.lmp`); `halo2`–`halo5`, `halo7`, `halo8`, `wisphalo.tex` (`fx.lmp`).

## 13. Drawing: the particle packet, groups, draw order, trails, beams, glows, the sheet (round 2)

Everything in this section was **Executed**: the original functions ran in
`tools/ee_emu.py`, their packets went through `tools/vu1_emu.py` (VIF1, the VU1
microprograms read from the user's own executable, the GIF), and
`tools/difftest_fx_render.py` compared every GS vertex and register write with
`tools/ref_fx_render.py`. Property names are in brackets.

Machine model caveat (applies to every "Executed" here): VU1 is the Python port of
`tools/recomp/render/vu1.cpp` (pair semantics, Q latency 7/13, flags seen 4 cycles later,
no FMAC stalls, round toward zero), with one deliberate difference, `waitq_first` (13.6).
Neither interpreter was checked against a console.

### 13.1 The particle packet (particle_draw 0x194888, particle_emitLists 0x194450)

Executed [particles, particle groups]: 16,440 + 4,560 cells (7,343 live particles, 3,167
drawn, 890 of them lines, 347 inside groups), 0 mismatches, EE FPU models ps2 and chop.

**Matrix.** `M = mat4_mulMat34(view, P)` with
`P = mat4_setProjection(0x3f7fffff, 0x3eeeeeee, g_projScale, 1.0, 4095.94, 18, 1800)` and
then
`P[0][0] *= 0x3aa3d70a (1/800)`, `P[1][1] *= 0x3b23d70a (1/400)`,
`P[2][2] = P[2][2] * 0x3a000080 - 1.0`, `P[3][2] *= 0x3a000080` (0x1949b8–0x194a7c).
The VU registers vf1..vf4 are the four rows of M. `ref_fx_render.particle_matrix`.

**Header** (uploaded with the 128 type-table qwords, entry 0x14): vf5 = (32, 2^23, 2^23+255,
float(particle clock)), vf6 = (800, 400, 0x5dffff00, 1), vf7 = (0x49008000, 0x49008000,
0x6007fff8, 0) — the 2^19 + 2048 offset makes the float's last four mantissa bits the GS
1/16-pixel fraction —, vf9 = (2, 1, 0, 0), the sprite GIF tag (PRIM 0x156: sprite,
textured, blended, UV; regs RGBAQ, UV, XYZF2, UV, XYZF2) and the line tag (PRIM 0x049:
line, Gouraud, blended, untextured; regs RGBAQ, XYZF2, RGBAQ, XYZF2). NLOOP 30 per block.

**Sprite (kinds 0, 1), VU 0x085–0x0a6, per particle** (`sprite_vertices`):
```
age   = clock - birth                       (VU floats; ITOF0 of the s16 fields)
v     = vel_s16 / 4096 * age                (ITOF12)
p     = pos + v ;  p.z = (g * age) * age + p.z          g = record +0x18
size  = rate * age + size0                  rate +0x1c, size0 +0x2c
clip  = ((M0 * p.x + M1 * p.y) + M3) + M2 * p.z          (this order: w before z)
Q     = 1 / clip.w
c     = (clip.x * 800, clip.y * 400, clip.z * Kz, size) * Q ;  c.xyz += vf7.xyz
h     = c.w                                   (= size / w, pixels)
corner 1 = (c.x - 2h, c.y - h)   UV (u0, v0)   z/ADC = whatever VU1 had in vf18.zw
corner 2 = (c.x + 2h, c.y + h, c.z)   UV (u1, v1)   ADC = clip test of the 6 planes
colour   = min(max(c0 + crate * age, 2^23), 2^23 + 255)  → the low byte of each lane
X, Y = low 16 bits of the float patterns; Z = (pattern of c.z >> 4) & 0xffffff (XYZF2)
```
So round 1's half-extent (2·size/w, size/w) pixels is right (Executed). vf18.zw is never
written by the loop: the first corner's z and ADC are left over from an earlier program,
which the GS ignores for a sprite (I).

**Line (kind 2), VU 0x0a9–0x0e3** (`line_vertices`): head = position at `age`, tail = at
`age - lag` (lag = +0x1c = sizeStart; gravity +0x10), both `p = pos + vel/4096·t, z +=
(g·t)·t`,
projected with `((M0 x + M1 y) + M2 z) + M3` (z before w here), `xyz·(800,400,Kz)·Q + vf7`.
**Settled:** the tail's colour is the head's RGB with **ALPHA 0**
(`SUB.w vf19` at 0x0d8: the store in the same pair still sees the old alpha — the head —
and the store two pairs later sees 0 — the tail). PRIM 0x49 is Gouraud, so a kind-2
particle is a line fading from its alpha at the current position to transparent at the
lagged one. ALPHA_1 stays 0x48 from the kind-1 lists (Executed: the packet writes
ALPHA_1 0x44 before the kind-0 lists and 0x48 before the kind-1 lists of every list set,
nothing before kind 2). The head's clip test sets ADC on the **tail** (a line whose head
leaves the view volume is not drawn); the head's own w lane is clip.w·Q, harmless.
The tail is scaled by `MULq | WAITQ` one cycle after its DIV: 13.6.

**Which cells are drawn** (`list_blocks`, Executed): whole 30-particle blocks from the
block holding the list's first live cell to the block holding its last. Retired cells in
front of the head in its block are sent again (their type field is 0 → slot 0's record,
the group definition 0x7e1d00, whose record is colour 2^23 (= 0, alpha 0), rate 0, size 0:
invisible, O in the record the static initialiser leaves);
cells from the tail to the end of the last block are zero-filled by an UNPACK V4-8 before
the closing MSCAL 0x17 (slot 0 again; they come out culled or invisible).

**Colour rounding.** Confirmed by execution: For all 7,343 live particles
the bytes the VU sends equal `ref_particles.ParticleDef.colour_at(age)` (the round-2
version with `rz(c0 + rz(crate·age))`): no difference. so a channel whose rate is inexact
ends one short of
its end value on screen too. (The VU forms `c0·1.0 + crate·age` rounded toward zero,
MAX/MINI on the patterns,
then the low byte — the same value.)

**Kind 3** is never sent (Executed: no kind-3 list reaches the packet).

### 13.2 Groups

Executed [particle groups]. Draw order: the global list set (kinds 0, 1, 2 × life class
0..3), then each **live** group in index order 0..15 with its own lists, then the global
matrix is uploaded again (MSCAL 0x4a) after the last group. Per group the VU gets
```
Mg = mat4_mulMat34(mat34_mul(group mat34 at +0x100, view), P)      (ref_fx_render.group_matrix)
```
uploaded as four qwords by UNPACK and entry 0x4a (which also switches the program back to
sprites, vi5 = 0). So a group's particles are stored and moved in the group's own frame
(birth position, velocity and gravity are all local) and drawn through the group matrix:
moving or turning the group (particleGroup_setMatrix 0x18e9e8) moves every particle it
holds, and a turned group turns gravity with it (I from the formula; Executed for random
rotations, scalings and translations). The ALPHA_1 writes repeat per group.

### 13.3 Draw order of the sorted packets

O (gfx_addSortedPacket 0x16b7f0, gfx_dmaHandler 0x16b998, gfx_swapSortedLists 0x16c938):
keys are drawn 0..7 in order; within a key, a packet whose texture already has an entry
this frame goes right after that texture's last entry, otherwise it is inserted at the
front of the key's list. For the effect drawers of one frame this gives, in GS order:
key 3: the glow_draw(0) packets; key 4: the particle packet, then the glow_draw(1)
packets (last texture first), then the trail packet (each after any later-added key-4
packet with a new texture). **Correction to round 1** (effects.md section 6): glow_draw(1)
is called before the particle packet is built but reaches the GS after it; glow_draw(0) is
called after it but its key-3 packets are drawn before every key-4 packet.

Consequence (Executed on that order): the trail programs do not load a matrix. They use
vf1..vf4, vf6 and vf7 as the particle packet leaves them — the global camera matrix, which
is exactly why particle_draw re-uploads it after the groups (I).

TEX0 (O, 0x16b998): every one of these packets carries TEX0 = 0 as its second A+D pair
(packet +0x30); gfx_dmaHandler patches that qword with
`(block + 4) | header(+0xc) << 14 | block << 37 | 2 << 61` before sending.

### 13.4 Trails

Executed [trails, trails vu1.cpp WAITQ]: 16,384 + 6,470 vertices, 0 mismatches; ring wrap,
odd oldest index, multi-chunk trails all reached.

trail_drawAll 0x193ad0 (one packet for all trails; 0x193b64 is inside it, not a function).
Per live trail with points: six qwords to VU 0..5 then MSCAL 0x28 (`trail_header`):
the strip tag (flags without 2: PRIM 0x154 triangle strip, textured, blended, UV, regs
UV XYZF2 UV XYZF2; flag 2: PRIM 0x15c, Gouraud, regs RGBAQ UV XYZF2 UV XYZF2), a tag for
RGBAQ + A+D, the colour, ALPHA_1 (flag 8: 0x09, flag 4: 0x48, else 0x44), then
(2^19, rowV[row] + 2^19 + 0.5, 128/lifetime, width byte·40) and (0, 0, (oldest&1)+1 —
not read by any of the programs —, clock). The header packet sets TEX1 0x61 (bilinear),
CLAMP_1 region-clamp u 0..128, v 0..512, TEST 0x71001, DTHE 0 (and CLAMP 0, DTHE 1 after).
Points go in chunks (`trail_chunks`): from the oldest index **rounded down to even**
(so a trail whose oldest index is odd draws the slot before it — a point already dropped,
with its old stamp; new finding), to the newest, at most 32 per chunk, split at the
ring's end; each chunk an UNPACK V4-16 (positions are s16 half units) and MSCAL 0x26
(single points) or 0x79e (pairs; the 98-instruction program trail_drawAll loads every
frame from 0x404150 with MPG).

Single points, program 0x26, per point (`trail_vertices`):
```
p    = s16 / 2 (half units) ;  clip = ((M0 x + M1 y) + M2 z) + M3
n    = clip * (1 / clip.w)                         (all four lanes)
d    = n - n_prev   (n_prev = (0,0,0,0) for the trail's first point; kept across chunks)
L    = d.x^2 + d.y^2
side = (d.y, -d.x) * (1 / clip.w) * (W / sqrt(L)),  W = width byte * 40 ;  side.x *= 2
c    = n.xyz * (800, 400, Kz) + vf7.xyz
vertices c + side (v = v0) and c - side (v = v0 + rowheight - 1);  u = 2^19 + (clock - stamp)*128/lifetime
```
`side` is not scaled by (800, 400): the half-width is W/w pixels (2·W/w in x) along a
direction perpendicular in the matrix's pre-divided space, not on the screen (I from the
formula). ADC: the trail's first point (both vertices, w = 0x8000 then counting down), and
a point outside the view volume. A chunk after the first starts by re-sending the
previous chunk's last two vertices so the strip continues.
Correction to round 1 ("half-width ... that over w, I for the unit"): as above, Executed.

Pairs (flag 2), program 0x79e, per pair (a, b): both projected with their own 1/w (no
offsetting), colour = trail RGB with ALPHA = low byte of b's stamp field — which
trail_addPair 0x192650 writes as `int(alpha·255)` —, u from a's stamp, v0 for a and
v0 + rowheight - 1 for b; ADC on both vertices when any of the last four clip judgements
(this pair and the one before it in the same chunk; FCSET 0 at each chunk) is outside.

### 13.5 Beams ("lightning")

Executed [beams]: 693 beam-frames, 21,463 points, 10,308 strip vertices, 0 mismatches;
frozen draws and expiry reached.

- beam_create 0x193088 (jitter f12, scale f13, from a0, to a1, width a2, depth a3,
  rgba t0): two trails (lifetime 1 s, row 0, flags 5 = "not aged" | additive), each given
  `from` once; depth = min(depth, 5); expiry = g_simFrame + 10; +0x72e = made inside a
  simulation tick (g_inSimTick 0x402794), which makes the expiry test use g_netFrame.
  Handle = generation (0x44fca4, shared with trails) << 8 | index.
- beam_buildNodes 0x192a40 (`beam_build_nodes`): a full binary tree in pre-order,
  2^(depth+1) - 1 nodes of 0x1c bytes: per node six **cosmetic** draws s1..s6 (s = 2u - 1),
  `offset = (s1, s2, s3)·jitter`, `drift = (s4·jitter - offset.x, s5·jitter - offset.y,
  s6·jitter - offset.y)·0.099999994` — **the z drift subtracts offset.y** (code as it is) —
  then `count = libc rand() & 7` (an integer word; round 1 called it the "third generator":
  libc_rand 0x3b70f0, state at reent 0x50c7e8 +0xa8); children with jitter·0.5.
  Node cursor: 0x83d100, reset to 0 before every walk.
- Every draw (trail_drawAll, per active beam in index order 0..19): if expiry < frame,
  destroy. Else, unless the game is frozen, beam_driftNodes 0x192e80 (`beam_drift_nodes`):
  pre-order, `offset += drift; count -= 1`; a node whose count was < 1 retargets with three
  cosmetic draws, `drift = (s·jitter_level - offset)·0.099999994` per axis (against the
  moved offset, z correct here), and `count = (seed >> 21) & 7` of a fourth draw. These
  draws use the live g_cosmeticSeed (per drawn frame).
- Then both trails are emptied (oldest = newest = 0, clock = 0), g_cosmeticSeed is set to
  **`g_simFrame·0x229 + index·0x3f3`**, beam_buildPoints 0x192c50 runs with amplitude 1.0,
  and the seed is put back (`beam_frame_seed`). So the random displacement changes once
  per simulation frame and is the same on every draw of that frame; only the drift moves
  per draw. beam_buildPoints (`beam_points`): per segment three cosmetic draws and the next
  node, `mid = (((a + b)·0.5) + node.offset) + ((s·amplitude)·scale)`, left half
  (amplitude·0.5), the point, right half — **the polyline is the 2^(depth+1) - 1 midpoints
  only: `from` and `to` are not points of it** (new). Points go to the trail at +0x724
  on even g_drawFrame, +0x720 on odd (the other stays empty that frame); its clock goes up
  by one after each point, so stamps are 1..N and u = (N - k)·128/60.
- beam_update 0x1933c8 (handle, from, to, alpha, width): ends, both trails' alpha, width
  (>> 2) when width >= 0, expiry = g_simFrame + 2. beam_isAlive 0x193360, beam_destroy
  0x193040 (releases both trails).
- Drawn by the single-point trail program (13.4) with flags 5: additive.

### 13.6 The `MULq | WAITQ` question (affects 13.1 lines and 13.4 single-point trails)

Two programs scale by Q in the same pair as the WAITQ that waits for a divide issued just
before: 0x0d2 (line tail by its own 1/w) and 0x1ca (trail side by W/sqrt(L) after an RSQRT
three pairs earlier). vu1.cpp lets the upper half read the Q still in place (the head's
1/w; the point's 1/w again), `vu1_emu` by default makes the pair wait first.
Both readings are modelled exactly and difftested ([... vu1.cpp WAITQ] properties, 0
mismatches each). They differ for 875 of 890 drawn line tails and 12,188 trail vertices.
**Inferred: the machine waits first** — (1) under the other reading the trail program
ignores its width word and its RSQRT entirely, which no programmer would write; (2) the
VU stalls a whole instruction pair, as emulators that model the stall do. Not checked on a
console. A native renderer should use waitq_first=True (the default of `ref_fx_render`).

### 13.7 Glow sprites

Executed [glows]: 1,912 packets, 3,720 glows drawn, 0 mismatches, every A+D write.
`glow_project` / `glow_vertices` / `glow_packets`:
```
fwd   = column 2 of g_cameraMatrix (0x44f118, 0x44f124, 0x44f130)
p'    = pos - fwd * bias ;  (q, w) = mat4_transformPoint(g_viewProj, p') ;  depth = w + bias
drop unless 20 <= depth, |q.x| <= depth*700, |q.y| <= depth*300
X = int(q.x * (1/depth) * 16) + 0x8000 ;  Y likewise
Z = int(q.z * (1/(depth - bias)) * 16)          (the depth value, toward the camera with bias)
H = int((size * 16) * (1/depth))                (1/16 pixel)
```
RGBAQ = the four bytes, Q = 0. Flags bit 0 clear: SPRITE (X-2H, Y-H)–(X+2H, Y+H), UV
texel (1, 1)–(w-1, h-1) of the texture header (+0, +2). Bit 0 set: a strip (first two by
XYZ3) with C = int(cos16(angle)·float(H)), S = int(sin16(angle)·float(H)):
(X-2C, Y-S) uv (1,1); (X+2S, Y-C) uv (w-1, 1); (X-2S, Y+C) uv (1, h-1); (X+2C, Y+S)
uv (w-1, h-1). X, Y, Z are or-ed into one 64-bit value from 32-bit signed results, so an
X-2H below 0 spills its sign into Y and Z (such a sprite is off screen; kept exact).
Packets: one per (texture, flags) in queue order, all records of that pair taken (texture
field cleared) whether drawn or culled; header TEXFLUSH, TEX0 (patched, 13.3), TEX1 0x61,
TEST 0x71001, DIMX 0x1212303012123030, ALPHA_1 (flags bit 1: 0x48, else 0x44); PRIM 0x15e
(sprite) or 0x15c (strip), Gouraud, textured, blended, UV; DIMX 0x3131757531317575 after.
Pass = flags bit 2 (key 4 if set, key 3 if not; 13.3). No per-frame jitter in glow_draw; the
size wobble of Fire glows is the caller's.

### 13.8 Trail builders

Executed [trail builders]: 1,000 calls, 46,269 points, 0 mismatches.
- 0x192650 `trail_addPair(alpha f12, handle, a, b)`: two ring entries, a stamped clock+1,
  b's stamp field = int(alpha·255) (the pair program's alpha). Refused when the ring is
  within two of full. Callers: fx_modelStatusEffects (swing trail), 0x191ea0.
- 0x191e58 `trail_clear(handle)`: clock, oldest, newest = 0.
- 0x1911e8 `spline_eval(t, points, count, outPos, outTangent)`: Catmull-Rom spline, Hermite
  segments, t clamped to [0, 1]; at t = 1 it reads one point past the array (U what callers
  put there). Callers: SpellWizardBeam_run.
- 0x1918a0 `trail_setSpline(start, end, handle, points, count, steps)`: empties the trail,
  lifetime = (steps // (count-1))·(count-1), per segment `per` Hermite points at
  t = (1/per)·k, the first segment from int(start·per), the last up to int(end·per).
  Callers: SpellWizardBeam_run, SpellUnspokenWord_run.
- 0x191ea0 `trail_sweepPairs(handle, centre, axis, a, b, steps)`: steps = min(steps, 60) is
  also the lifetime; pairs (a+centre, b+centre) with alpha 1, a and b turned each step by
  quat_fromAxisAngle(axis, 0x10000 // (steps-2)). Caller: Innoruuk_run.
- 0x1920e0 `trail_setCircle(radius, handle, centre, normal, steps)`: empties the trail
  (lifetime kept), min(steps,120) points round centre in the plane of normal (basis
  u = normalize(n × r), v = normalize(u × n), r = (1,0,0) or (0,0,1) when n ≈ (1,0,0)),
  angle step 0xffff // steps. Caller: SpellWizardBeam_run.

### 13.9 The particle texture sheet

O (the user's disc, ENGINE.LMP, and the TEX0 path of 13.3): `particletex.tex` is
**512 × 160** texels used (header +0, +2), 8-bit palettised (PSMT8, TCC 1), TEX0 TW = 9,
TH = 8 (the GS sees 512 × 256). So the 32 × 32 cells of round 1 form 16 columns × **5
rows**: tiles 0x00–0x4f are on the sheet, a tile of 0x50 or more samples GS memory below
the uploaded 160 lines (U what is there). The flipbook rows 1, 2, 4 are inside.
Same lump: trail.tex 128 × 448 (TH 9), floorsprite.tex 256 × 128, halo1.tex 32 × 32
(flags 0x1044), the texture of 0x44fe04 (14.2).

## 14. One-shot effects, death and status visuals (round 2)

Everything in this section was **Executed**: the original function ran in
`tools/ee_emu.py` with the primitives it calls replaced by recorders, and
`tools/difftest_fx_recipes.py` compared its call stream (every argument; floats as 32-bit
patterns), the generator states and the memory it owns with `tools/ref_fx_recipes.py`
[property]. Models are synthetic in the difftest (sample points, attach matrices and the
blade segment come from made-up tables), so the recipes are given in terms of those model
queries. Definition values are not given; addresses are keys into `fx_particle_defs.py
--json`.

Notation. `d` = one draw of the cosmetic generator (`seed = seed × 0x19660d + 0x3c6ef35f`,
`d = seed >> 16`); `u` = float(d) × 2⁻¹⁶; `s` = (u + u) − 1; **ball** = three `s` draws
(x, y,
z) repeated while 1 < (x² + y²) + z². All arithmetic is the console's single precision (see
ref_core.py), in the order written. Every `particle_spawn` below has backdate 0 unless a
backdate is given.

### 14.1 `fx_spawn(id, pos)` 0x1ef270, every id [fx_spawn id 0 … id 22, id 23, id −1]

1. Every id but 5 first asks `isNearCameraFocus480(pos)` (per machine) and returns when it
   says no — before anything else, so a far call draws nothing.
2. Then (all ids, also 5 and ids outside the table) the **24** definitions of the function
   are constructed on first use, each behind its own flag at 0x4f87bc + 4i (i = 0 … 23).
3. Ids above 0x16 (and negative ids) then do nothing.
4. Ids 0 and 1 return when `g_decalDetail` (0x44fdc0) is 0 — after step 2.

Centre jitter forms (x, y, z drawn in that order):

| Form | Centre |
|---|---|
| J12 | (pos − 6) + float(d % 12) per axis |
| J12+18 | J12, then z + 18 |
| J10 | (pos − 5) + float(d % 10) per axis |
| J24/36 | x, y: (pos − 12) + float(d % 24); z: (pos − 18) + float(d % 36) |

Per-particle offset "P n": float(d % n − n/2) + centre per axis (an integer, then float).

| id | Recipe (draw order as written) |
|---|---|
| 0, 1, 9 | centre J12. One ball b, normalised (rsqrt) and × 34, z + 4: the burst direction D. One draw: sound `dism_blood_goosh<1 + (d & 3)>.anm` from `fx.lmp` at pos (volume 1.0). 300 ×: ball u, one `u` = r, vel = u × 7.86 + D × r; a second ball is drawn and not used; spawn at the centre (P 0). Defs 0x8704a8 (id 0), 0x8704f8 (id 1), 0x86fc38 (id 9) |
| 2 | centre J24/36; 150 ×: vel = ball × 10.45, P 12, def 0x4f8710 |
| 3 | centre J12+18; 150 ×: vel = ball × 10.16 at the centre, def 0x86fcd8 |
| 6 | as 3 with vel = ball × **16 on all three axes** |
| 4 | centre J12+18; 150 ×: vel = ball × 16, P 24, def 0x86fd28 |
| 5 | **shared seed** (g_randSeed 0x404464), no camera gate: n = 3 + (d & 1); n ×: x = (pos.x − 6) + d % 12, y likewise, z = pos.z + d % 18; `pool_new(0x50)` then `Fire_ctor` at that point when the pool gave a block |
| 7, 0x14 | 3 ×: ball a, ball v; p = (a.x × 15.75 + pos.x, a.y × 15.75 + pos.y, ((a.z × 15.75) × 0.75 + 0.07) + pos.z); vel = (v.x × 4.75, v.y × 4.75, (v.z × 4.75) × 0.77 + 6.05). Def 0x86fd78 (7), 0x86fdc8 (0x14). So: inside a ball of radius 15.75 flattened to 0.75 in height, rising at 6.05 ± 3.66 with ± 4.75 sideways |
| 8 | centre J24/36; 300 ×: vel = ball × 10.45, P 24, def 0x86fe18 |
| 10 | centre J10; 25 ×: ball × 5.45, P 24, def 0x86fe68. Then a new centre J12+18; 80 ×: ball × 20, P 24, def 0x86feb8 |
| 0xb, 0xc | centre J10; 15 ×: ball × 5.45, P 24, def 0x86ff08. New centre C2 = J12+18; 20 ×: ball × 40, P 24, def 0x86ff58. Id 0xb only, 5 ×: ball u, p = u × 5 + C2; ball v; vel = (v.x × 21.6, v.y × 21.6, v.z × 21.6 + 1.633); def 0x86ffa8 |
| 0xd, 0xe, 0xf, 0x10, 0x12 | one draw a (angle = a as s16), r = u; p = pos + (cos16(a) × r × 15, sin16(a) × r × 15, (u′ − 0.5) × 15); **vel 0**. Defs 0x86fff8, 0x870048, 0x870098, 0x8700e8, 0x870138 (so 0x12's velocity is 0) |
| 0x11 | one particle of 0x870188 at pos, vel 0 |
| 0x13 | ball u; vel = (u.x × 21.6, u.y × 21.6, u.z × 21.6 + 1.633), def 0x8701d8 at pos; one draw: on d % 10 = 0 also def 0x870228 at pos with vel × 0.25 |
| 0x15 | 5 ×: ball u; p = pos + (u.x × 36, u.y × 36, A(u.z) × 36); ball v; vel = (v.x × 12, v.y × 12, A(v.z) × 12); def 0x870278. Then 5 ×: ball u; p = pos + (u.x × 6, u.y × 6, A(u.z) × 6); ball v; vel = (v.x × 24, v.y × 24, (float)((double)A′(v.z) × 0.5) × 24); def 0x8702c8. A(x) = float(abs((int)x)), A′ the same as an int: the integer `abs` of a float, which is 0 unless x is exactly −1 (a draw of 0). So the vertical terms are 0 in all but 1 in 65 536 draws: a flat ring (I: the source meant `fabs`) |
| 0x16 | ball u: vel = (u.x × 5, u.y × 5, (|u.z| × 5) × 5), def 0x870318 at pos; ball u: vel = (u.x × 1.28, u.y × 1.28, (|u.z| × 1.28) × 24.72), def 0x870368. Both rise |

Callers (from round 1) stand. Particle counts ignore the pool: `particle_spawn` drops
silently
when a slot or page is missing (section 3).

### 14.2 Glow textures — O

| Global | Holds | Written by | Read by (functions with a load of it) |
|---|---|---|---|
| 0x44fe04 | `engine.lmp` : `halo1.tex` | `engine_init` 0x19d810, again by main at 0x32400c | AutoEmitter_draw, Creature_draw, Gold_draw, IceBall_draw, ItemProp_draw, MissileWeapon_draw, SmokeGen_readParams, Sparks_draw, SpellResurrect_draw, StrongStancePhantom_draw |
| 0x4f848c | `fx.lmp` : `halo2.tex` | main 0x324028 | Fire_run (its flame glow), the light-chunk glow (`game_addCoreTasks` 0x1e6f0c → `lightChunk_setGlowTexture`), fx_modelStatusEffects, fx_drawModelGlowNearCamera, AddParticle_updateLightAndHalo, Creature_draw, FireEffect_draw, Gold_draw, Innoruuk_run, JumpGate_draw, Marr_draw, NPC_draw, Savepoint_draw, SpellSummonBadger_draw, SpiritAnchor_draw, StaticFire_draw, Torch_draw, SmokeGen_readParams |
| 0x4f8490 | `fx.lmp` : `halo3.tex` | main 0x324048 | SmokeGen_readParams |
| 0x4f8494 | `fx.lmp` : `halo4.tex` | main 0x324060 | FireArrowProjectile_draw, FireFly_draw, Lantern_draw, SmokeGen_readParams |
| 0x4f8498 | `fx.lmp` : `wisphalo.tex` | main 0x324078 | HateProjectile_draw, HolyStrike_draw, Lamp_draw, Player_drawMarker, ShockProjectile_draw, SpellBlessed_run, SpellDiseaseEffect_run, SpellDiseaseShield_run, SpellPlanarSteelEffect_run, SmokeGen_readParams |
| 0x4f849c | `fx.lmp` : `halo5.tex` | main 0x324098 | UnholyAura_run, SmokeGen_readParams |
| 0x4f84a0 | `fx.lmp` : `halo7.tex` | main 0x3240b0 | StaticFire_draw, SmokeGen_readParams |
| 0x4f84a4 | `fx.lmp` : `halo8.tex` | main 0x3240c8 | StaticFire_draw, SmokeGen_readParams |

All are `res_find(lump, name)` results (resource entries). The reader lists are direct loads
only (`lw` of the global's low half); a table access through a register (SmokeGen's) is
listed once. There is no `halo6.tex` reference.


### 14.3 Disintegrate — `fx_disintegrateModel` 0x1f4340 [disintegrate]

`(a0 obj, a1 model, a2 anim, a3 pos*, t0 yaw16, t1 alternate, f12 scale, f13 offset)`;
callers `Creature_processDamage` 0x1115c0, `Player_processDamage` 0x1b3344. Nothing
without a
model. Otherwise: `obj +0xc |= 2` (the object is hidden), sound `spel_dsrptn_afteraffct.anm`
(`fx.lmp`) at pos, then over every sample point i of the posed model
(`model_getSamplePoint(scale, model, anim, pos, yaw, i)` → point, size):

```
total += size * size * size                  # running over all points, never reset
while total > 0:
    total -= 8.09e10                         # one particle per 8.09e10 of "volume"
    f   = (size * 1e-5) * 35.35
    p   = point + (u - 0.5) * f              # draws x, y, z
    vel = (u - 0.5) * 3.14                   # draws x, y, z
    if offset != 0: p += (cos16 yaw, sin16 yaw, 0) * offset     (z gets + 0.0)
    spawn(backdate = u * 0.4 seconds, alternate ? 0x870688 : 0x870638, p, vel)
```

Cosmetic seed only. The random back-date (up to 0.4 s, section 3) is what spreads the
particles' ages so the cloud does not vanish at once.

### 14.4 Ice shatter — `fx_shatterToLooseIce` 0x1fb240 [ice shatter]

`(f12 count, f13 scale, f14 offset, a0 model, a1 anim, a2 pos*, a3 yaw16)`; caller
`Creature_processDamage` 0x11165c. **Shared seed** (g_randSeed 0x404464), exactly 1 + n
draws: one for the sound `expl_ice<1 + d % 3>.anm` (`fx.lmp`) at pos, then one per chunk.
n = (int)count (a count of 0 makes the original divide by zero — I: no caller passes it),
step = samplePointCount / n; with step 0 no chunk is made. Chunk k (k = 1 … n) sits at
sample
point (k × step) mod (count asked again), moved by (cos, sin, 0) × offset when offset ≠ 0,
size class from its draw: d % 10 = 0 → part mask 2, 1–2 → 3, 3–9 → 4. Each is
`pool_new(0x248)` → `PhProp_ctor(1.0, pos, "fx.lmp", "icechunk.vif", "icechunk.tex", mask,
launch 0x30a, no item)` with the `LooseIceChunk` table 0x50f328 at +0x48. (I: the chunk
constructor's own `GameObject_ctor` draws the shared seed again — docs/spec/core.md — that
is not part of this recipe.) Because it draws the shared seed, this is the one death visual
that must run identically on every machine.

### 14.5 Losing a body part — the eight callers of `GutChunk_ctorFromProp` 0x201ad0 [lose part …]

Common recipe: a model-variant bit is ORed into the creature's word +0xe8, the show mask
+0x220 is rebuilt (`model_buildHideMask(class data +0xc, +0xe8)`), and one GutChunk (pool
block 0x268) is made from the creature's **own** model showing only the lost part's meshes:

```
GutChunk_ctorFromProp(scale 1.0 (BlackWidow: creature +0xdc), block, creature pos +0x10,
    yaw +0x38, model = class data +0xc, anim = creature +0x114, lump = class data +0,
    model name +8, texture +0x10 (Ant: +0x18 when its colour byte +0x3c8 is 1),
    [stack] mesh mask (64-bit), launch flags, blood bits)
then chunk +0x1c4 (vertical speed) += 2.0          (not BlackWidow)
```

The constructor then stores the bits at +0x248 (| 1 = invisible drop when gore < 2), the
GutChunk table 0x50f3b8, a copy of its position at +0x250, +0x25c = 2, +0x260 = 0 (section 9
GutChunk behaviour applies from there).

| Class (address) | Part → variant bit | Mesh mask | Launch | Blood bits | Notes |
|---|---|---|---|---|---|
| Ant 0x236b0c | n = 0…7 → 2 << n | old show & ~new show | 0xe | 2 (yellow) | texture by colour byte |
| AntQueen? 0x238360 | none | old & ~new (so 0) | 0xe | 0 | **no caller** (no call, jump or stored address; I: dead code) |
| FireBeetle 0x247130 | 2…7 → 1 << (n−1) | constant: 2→0x4, 3→0x6, 4→0x40, 5→0xc00, 6→0x80, 7→0x300, else 0 | 7 | 2 | mask rebuilt after the chunk |
| Ghoul? 0x2672f4 | 0→2, 1→4, 2→8, 3→0x10, 4→1 | constant: 0→0x8, 1→0x10, 2→0x20, 3→0x40, 4→0x2 | 7 | 0 (red) | **no caller** |
| Mosquito 0x2982cc | 1,2→0x10, 3→0x40, 4→2, 5→1, 6→4, 7→8 | old & ~new | 0xe | 2 | |
| Orc 0x2a3de0 | 1…5 → 0x10000000 >> (n−1) | 1: built from the head variants already set (`orc_head_mask`), 2→0x800, 3→0x10, 4→0x1000, 5→0x200 | 7 | 0 | also asks `model_getAttachPoint` (index 1→8, 2→6, 3→7, 4→4, 5→5, yaw − 0x4001) and does not use it; chunk only for parts 1–5; parts 6/7 (drop a held item as a PhProp) never passed |
| Scorpion 0x2a59f0 | 1 << (n & 31) | old & ~new | 0xe | 2 | |
| BlackWidow 0x2acfd8 | n = 0…11 → 1 << n | old & ~new | 0xe | 2 | nothing while +0x414 is 1; no chunk for parts 8–11; scale +0xdc; no lift |

### 14.6 Weapon element visuals — `fx_modelStatusEffects` 0x1f6ac8 [weapon status]

Arguments: f12 **amount**, f13 scale, a0 item, a1 weapon model, a2 state (0x40 bytes,
below),
a3 pos*, t0 yaw16, t1 holder model, t2 holder anim, t3 swinging, stack +0 joint add, stack
+8 matrix override* (0 = none). One call per frame per held weapon (callers in round 1).

State block: +0x00 last frame's weapon matrix (mat34), +0x30 `g_simFrame` of the last
swinging call, +0x34 lightning beam handle, +0x38 swing trail handle, +0x3c swing counter
(s8: +1 per swinging call up to 100, 0 otherwise), +0x3d spark kind, +0x3e sparks left.

1. Return when level flag 0x10000000 (0x44fe08) is set, the weapon model is 0, or
   `dialog_isOpen()` (0x22fbc0 — per-machine UI state; cosmetic only).
2. Matrix M: identity, unless swinging or any element entry (codes 0x18, 0x16, 0x15, 0x17,
   0x26; the value of the FIRST entry with that code must be non-zero) or the item's glow
   colour (+0x10, 64 bits) is set — then M = `model_getAttachMatrix(scale, holder, anim,
   (s8)weapon model +0x13 + joint add)` (identity without a holder) × `mat34_setPosRotZ(pos,
   yaw + 0x4000)`. An override pointer replaces M.
3. If the stored matrix has 1.0 on its diagonal and (translation x = y and z ≠ 1.0, or x ≠ y
   and z ≠ 0) it is replaced by M first (O 0x1f6e70–0x1f6f40; I: meant as "never set",
which a
   zeroed block is not, so a fresh state starts from a zero matrix).
4. **Swing trail** (level flag 0x100 clear). Not swinging, or with an override: trail
handle,
   spark kind and count are cleared. Swinging: the blade runs along M's row 1 (normalised ×
   scale) from `segment.a.y` to `segment.b.y` (`model_getEffectSegment`; defaults 4.5 and
38)
   from M's translation. Width alpha w = min(min(max(|dir − lastDir| × 0.68, 0), 1) × 0.3,
   counter × 0.05). A new trail `trail_create(0.2 s, row 3, width 1000, flags 2 (pairs),
   0x80, 0x80, 0x80, 0)` when there is none or the last swinging frame was not
   `g_simFrame − 1`; otherwise first an in-between pair from the averaged matrix
(translation
   and direction × 0.5, direction re-normalised). Then the pair (tip, base) with
   `trail_addPair(w, handle, tip, base)` 0x192650. Hit sparks: while +0x3e is non-zero
   and gore ≥ 1, for i < count: 2i sparks on a line from a point 0.3 of the way up the
blade,
   pulled back by the blade direction × 2 × (count − i), toward last frame's tip; velocity =
   blade direction × 18; definition by +0x3d: 1 → 0x870bd8, 2 → 0x870c28, 3 → 0x870c78; then
   +0x3e −= 1 (also at gore 0).
   **Level flag 0x100 set** instead: swinging, one draw; with v = clamp(2 × |dir − lastDir|,
   0, 1) the call `fx_spawn(0x11, tip)` happens when d % (6 − (int)(v × 5)) = 0.
5. **Glow**: item glow colour (+0x10, 4 s16) non-zero: one `glow_add` per weapon sample
point
   (through M): bias −12.856, size (sin16(g_simFrame << 10) × 250 + 10000) − 2013, colour =
   the four s16, texture `halo2.tex` (0x4f848c), angle (g_simFrame << 6) as s16, flags 3.
6. Both item colours (+0x18 then +0x10, four s16 each) move 2 toward 0 per call.
7. Elements. The entry value only switches an element on; **its size is the caller's
   amount**. The motion term d = |M·(0,0,36) − last·(0,0,36)| (clamped); particles sit at
   random weapon sample points through a matrix walking from last frame's to this frame's by
   (M − last) / count per particle, jittered by (u − 0.5) × ((size × 1e−5) × 35.35) per
axis;
   the back-date starts at the given value and grows by (1 / count) / 24 per particle:

| Element | Count | Back-date | Particle | Extra |
|---|---|---|---|---|
| lightning 0x18 (needs amount > 0; else beam handle cleared) | count = max(1, (int)(((int)(d × 13.13) + 1) × amount)), d ≤ 15; particles = max(count / 4, 8) | d × 0.00291 | 0x870958, vel = ball × 3 + (0, 0, 19.74) | a beam between two random sample points (through M): `beam_create(7.78, 2.47, a, b, width 0x6b, depth 4, 0x5e808080)` when there is none or `beam_isAlive` fails, else `beam_update(handle, a, b, (int)(amount × 94), −1)` |
| cold 0x16 | (int)(((int)(d × 3.13) + 26) × amount), d ≤ 20 | d × 0.00191 | 0x870ae8, vel 0 | swinging: two ribbons along the blade (below): 0x870b38 (2n), then 0x870b88 (n), speed 2.83, k = 0.229, e = 0.97 |
| fire 0x15 | (int)(((int)(d × 3.13) + 16) × amount), d ≤ 20 | d × 0.00191 | 0x870a48, vel = ball × 6.589 + (0, 0, 19.74) | every 16th particle also 0x8709f8 (same p, vel) and 0x870a98 at p + (0, 0, 6) with vel + ball × 3.5 |
| poison 0x17 | (int)((26 × amount) × 0.156) — d is always 0 | 0 | 0x870cc8, vel 0 | swinging: ribbon 0x870d18 (2n), speed 6.388, k = 0.206, e = 0.667 |
| disease 0x26 | (int)((26 × amount) × 0.578) — d is always 0 | 0 | 0x870d68, vel 0 | then (int)(count × 0.074) of 0x870e08 with vel ball × 3.974 (back-date restarts at 0, matrix continues); swinging: ribbon 0x870db8 (2n), speed 3.974, k = 0.785, e = 0.556 |

   Poison and disease measure the motion with **this frame's matrix twice** (O 0x1f9808,
   0x1fa168; Executed), so their counts do not depend on how fast the weapon moves.
   Ribbon (swinging only): T, R = M's translation and row 1, T′, R′ last frame's; D =
   |(T + 36R) − (T′ + 36R′)| ≤ 30; n = (int)(D × k) (doubled where marked), e′ = D × e; per
   particle: r = u × 30 + 6, f = (e′ × d) × 2⁻¹⁶, p = T + R × r, vel = R × f + ball × speed;
   T, R step toward T′, R′ by 1/n of the difference.
8. When swinging, +0x30 = `g_simFrame` (not when a disease element returned early without a
   swing); the state matrix = M.

### 14.7 Model-vertex helpers

- `fx_emitFromModelVerts` 0x1eb1e8 (f12 speed, a0 obj, a1 count, a2 def, a3 dir* or 0, t0
  offset* or 0) [emit from model verts]: the object's model from its slot 0x84/0x80; per
  particle: vel = dir × speed, or ball × speed when dir is 0; one draw picks sample point
  d % n (scale 1.0, pos obj +0x10, yaw +0x38, anim +0x114); p = point + offset; def. (A
model
  with no sample point divides by zero.) Callers SpellResurrect_run, SpellRetribution_run.
- `fx_burnModel` 0x1f5210 (f13 amount, f14 offset, a0 model, a1 anim, a2 pos*,
  a3 yaw16) [model sparkle]: camera gated; pass 0: round(amount × 16.5936) points, def
  0x870728, speed 10; pass 1: round(amount × 3.7609) points, def 0x870778, speed 9. Per
point
  (draw: index; scale = amount) p = point + (cos, sin, 0) × offset; while size² (−1.145114e8
  per particle) > 0: p += (u − 0.5) × ((size × 1.00597) × 1e−4) — a random walk, not reset
—,
  vel = ball × speed, back-date u × 0.3. Callers Creature_run, Demon_run, Vampire_run.
- `fx_shockModel` 0x1f61c0 (f12 alpha ≤ 1, f13 scale, f14 offset, a0 model, a1
  anim, a2 pos*, a3 yaw16, t0 state, t1 rgba) [model arcs]: three lightning arcs between
  sample points. Per arc (s16 indices at state +8/+0xa, beam handle +0xc, every 8 bytes):
  no beam, or a draw below 20000 (≈ 30 %): two new indices (d % n) and `beam_create(7.78,
  4.47, a, b, width 0xcf, depth 4, rgba)`; otherwise indices above n reset to 0,
  `beam_update(handle, a, b, (int)(alpha × 94), −1)` and a spark at each end exactly like
  `fx_spawn` id 0x13 with defs 0x8708b8 / 0x870908.
- `fx_drawModelGlowNearCamera` 0x1f5890 (a0 obj, a1 model, a2 anim, a3 pos*, t0 yaw16, t2
  target A, t3 target B (4 s16 each), stack +0 mode, stack +8 size add; f13 scale, f14
offset,
  f15 fade seconds) [model glow]: per rendered frame from Creature_draw / FireBeetle_draw;
  needs obj flag 0x20 (+0xc). Mode 0 ramps obj +0x70 (A) and +0x80 (B) up by target /
(fade ×
  60) per call, clamped at the target; mode 2 down, clamped at 0. One glow per sample point
  (pos moved by (cos, sin) × offset in x y): bias −12.856, size ((sin16(frame << 10) × 250 +
  10000) − 2013) + size add, colour (int) B, `halo2.tex`, angle (frame << 6), flags 3.

## 15. Skill and spell visual recipes, executed (round 2)

Every one of the 161 functions of the skill files (0x2c3cd4–0x320000) that calls an effect
primitive is now reproduced by a model that was executed against the original, call for
call and byte for byte: 140 by the skill research that already existed
(`tools/ref_skills_a.py`, `_b.py`, `_c.py`, `tools/ref_arena_monsters.py` and their
difftests), 21 new ones in `tools/ref_fx_skills.py` (`tools/difftest_fx_skills.py`).
Claims are O / I / U or **E** (Executed; the property is named). This extends section 11,
whose timing and call map stand.

### 15.1 Where a skill's visual recipe lives

**The recipe is the model's code, not a table.** A skill id picks a `Skill` object; its
`cast` makes the effect classes; each class makes its visual through the effect primitives
from its own code (O, round 1). The skill models already make every primitive call as a
*call-out* with its exact arguments, because "the own generators that place particles also
roll damage" (`ref_skills_a.py` docstring): a model that skipped a particle would roll the
next damage from the wrong generator state. So:

- what a class spawns, how many per tick, where, with what velocity and from which
  generator = the model method named in `ref_fx_skills.RECIPES` for that function (161 rows:
  class, phase, function, address, model, static call counts, generators);
- the call-out → primitive mapping = `ref_fx_skills.CALLOUTS` / `to_primitive()` (below);
- the constant VALUES (particle definition addresses, LightEffect colours / radii / floor /
  seconds, glow colours, trail rows / widths / lifetimes, decal types, fx_spawn ids) =
  `python3 -I tools/fx_skill_recipes.py <your SLUS_209.73> --json`, read from the user's
  executable at run time; definition contents from `tools/fx_particle_defs.py --json`.
  No retail value is in this repository.

The native skill ports (open-champions-godot `native/src/skills_*.cpp`) already emit the
same call-outs (`typed_invoke("particle_spawn", {definition, point, velocity, backdate})`,
`"LightEffect_ctor"`, `"glow_add"` …). What the native FX layer needs is to receive those
call-outs and apply `to_primitive()`'s field mapping; no new recipe has to be invented. I
(the native code was looked at, not run here).

### 15.2 Generators: a skill visual is not cosmetic

Round 1 section header: "Everything in this document is cosmetic: it draws from
`g_cosmeticSeed` unless a line says otherwise." For skill visuals that is not the rule
(correction in section 17). Of the 161 functions (generator column of `RECIPES`, I from the
models' code; the draws themselves are E through the difftests, which compare the
generator words as written bytes):

| Generator | Functions | Meaning for a renderer |
|---|---|---|
| object's own, +0x44 (`GameObject_rand` 0x1509d0) | 32 | particle positions/velocities of projectiles, clouds, flares, fires; the same word rolls the object's damage (e.g. `FireArrowProjectile_onHit`) |
| spell's own, +0x10 (`Spell_rand` 0x16a964) | 49 | the same for spells on creatures |
| shared 0x404464 | 77 | a shared draw somewhere in the function (often the damage roll next to the visual); in the sync hash |
| shared, inside a `LightEffect` constructor | 40 | every flash is a `GameObject`: its constructor makes ONE SHARED DRAW (`ref_skills_c.light_effect` docstring) |
| cosmetic 0x404460 | 3 | per machine |
| third generator 0x404468 | 3 | per machine |

Consequences (I): a headless or low-detail client must still run every particle draw
(the rejection loops included) of these classes, and must still construct the
`LightEffect` objects, or its object, spell and shared generators fall out of step with the
other machines. Only the *drawing* of the primitives is free to differ.

### 15.3 Call-outs and primitives (`ref_fx_skills.CALLOUTS`)

Canonical arguments (as `ref_creature.Ext` defines them): integer registers a0.. as
unsigned 32-bit, vectors as three float patterns, then f12.., then stack words.

| Call-out | Address | Primitive | Fields, in order |
|---|---|---|---|
| `particle_spawn` | 0x18f3f8 | particle | definition, pos, vel, backdate (s) |
| `glow_add` | 0x18fc78 | glow | pos, r, g, b, a, texture word, angle16, flags, bias (f12), size (f13) |
| `LightEffect_ctor` | 0x201bd8 | light_effect | block, pos, follow, flag, colour 0 (4 floats), colour 1 (4), radius, radius at end, floor, seconds |
| `trail_create` | 0x190ff8 | trail | row, width, flags, r, g, b, a, lifetime (s) |
| `trail_addPoint` | 0x192550 | trail_point | handle, pos |
| `trail_release`, `trail_setColor`, `trail_setLength` (0x1911a8) | | | handle (…) |
| `beam_create`, `beam_update` | 0x193088, 0x1933c8 | beam | from, to, width, depth, rgba, jitter, scale / handle, from, to, alpha, width |
| `decal_add` | 0x19f110 | decal | pos, angle16, type, grow, size |
| `fx_spawn` | 0x1ef270 | fx_spawn | id, pos |
| `particleGroup_create/_begin/_end/_setMatrix/_free` | 0x18e880… | group_* | handle (, matrix) |
| `light_link/_relink/_unlink` | 0x148af8, 0x14a528, 0x14a4f0 | the class's own light node |
| opaque (arguments as recorded) | | `fx_ringBurst`, `fx_impactPuffNearCamera`, `fx_emitFromModelVerts`, `fx_shockModel` 0x1f61c0, `fx_burnModel` 0x1f5210 (14.7), `fx_disintegrateModel`, `fx_shatterToLooseIce`, `trail_setPoints`, `GlowingShaft_ctor`, `LightningBolt_ctor/2`, `GutChunk_ctor`, `camera_shake`, `gfx_setColorOffset` |

E, property "call-outs decoded as primitives": every call-out the ORIGINAL made in all
five difftests decodes, field for field: 568,467 calls (fx skills 87,135; skills_a 37,183;
skills_b 265,566; skills_c 157,354; arena_monsters 21,229), 0 failures.

### 15.4 Timing (unchanged from round 1, now Executed)

cast = the constructor / cast call (the tick the effect is made); run = every simulated
tick (GameObject slot 4, Spell slot 2 or a helper); draw = every rendered frame (GameObject
slot 5, Spell slot 3); event = hit, contact, expiry, absorption, trigger. 71 cast, 69 run,
7 draw, 14 event rows. The particles then live on the particle clock (section 4).

### 15.5 The 21 functions modelled in round 2 (E, `tools/difftest_fx_skills.py`)

Counts, timings and geometry are code constants; colours and definitions by address only
(the model and `fx_skill_recipes.py` have the values).

**Draw slots that queue glows** (each once per rendered frame; nothing changes state):

- `ShockProjectile_draw` 0x2c4e64: one turned glow (flags 1) at the bolt, grey, fading with
  t = min(1, (expiry +0x58 − frame + 300) / 30) (no lower bound), size int(15152 t +
  sin16((frame mod 0x8000) × 0x1dd7) × int(15152 t × 0.195006)), angle (frame << 26) >> 16,
  texture word 0x4f8498.
- `FireArrowProjectile_draw` 0x2d67e8: one additive glow (flags 6), size radius +0x1c ×
  1408,
  bias 10, texture 0x4f8494.
- `HolyStrike_draw` 0x2ecd90: one glow one unit beside the strike (the unit vector
  (dir.y, −dir.x) of +0x6c/+0x70) and one up, size 5000 + 250 sin16(frame << 10), bias 5,
  angle (frame << 25) >> 16, flags 3, texture 0x4f8498.
- `SpellSummonBadger_draw` 0x311034: one glow per model sample point of the badger, alpha
  int(65 f) of the spell's fade +0x1c (folded above 1), size = the sample's second output
  x + 250 sin16(frame << 10), flags 7, texture 0x4f848c.
- `SpellResurrect_draw` 0x312f48: **only with one player in the session**
  (*0x4d8ae0 == 1): a ring of 13 glows, radius int(100 f) + 15, 116 above the owner, angles
  frame × 0x75 + k × 0x13b1, alpha int(128 (1 − f)), f = min(1, (frame − +0x6c) / 60)
  once +0x20 is set; texture 0x44fe04, flags 2. (New: in a net game the resurrect ring is
  not drawn at all.)
- `SmokeGen_draw` 0x31cbf8: when `isNearView(1000)`, one glow per live puff of a 100-entry
  ring at +0x50 (10-byte records), size/colour/alpha interpolated over the puff's age,
  angle ± s16(+0x488 × +0x472) alternating, flags 5, texture word +0x4c.
- `StaticFire_draw` 0x2c65e8: below.

**MultiFireProjectile** (the arrows of Multi Fire; ctor 0x2da164, run 0x2da2bc, end
0x2da928): ctor = `Projectile_ctor` (a shared draw inside), radius 8, speed = skill slot 13
statistic along the angle, a grey trail (row 1, width 0x7a, flags 0, alpha 0x20, 0.15 s)
with its first point. Run: a trail point at the position every tick, move; terrain → end(1);
age ≥ 601 → end(0); else 10 particles of one definition, v = 8 × unit-ball, placed at
pos + v × r (r = one more draw / 65536), all from the arrow's OWN generator. End (once):
trail released; with a reason one own draw picks one of four impact sounds and the burst
is `fx_spawn(8)` (fire) when level flag 0x40000 of 0x44fe08 is set, else `fx_spawn(2)`
(dust); `obj_delete`.

**FireStormFlare_run** 0x2d33c0 (the falling balls of Fire Storm): falling (until it lands
or frame ≥ +0x68): vz −= 0.39999998 a tick, position += velocity, then three streams with
the reversed velocity: scale × 30, × 18, × 4 particles (three definitions), each at
unit-ball × 8.8 × scale behind the ball by r × velocity, velocity a second ball point ×
10.42 (z × 10.26 more), × 5.06 (z × 7.17), raw; lands when less than 16 above
`terrain_height` (a sound). Landed: an expanding ring (+0x58 += 7 a tick up to radius × 3 ×
scale) of 85 particle pairs a tick at ring × (cos, sin)(draw) + 6.76 × ball. Then one draw
in
three lowers it by 6 and lays a scorch decal (type 9, no growth, size = scale), and it
destroys itself. OWN generator only.

**Pustule_run** 0x30bde0 (Pus Storm's blobs): falls with gravity 0.19999199 and three
dribble particles a tick (zero velocity, along the last step); at its floor +0x54 a sound
and ten drops at terrain + 12 within 6.1, launched at ≤ 0.79 × 4.43 sideways and 4.43 up;
the drops fall with 0.440994 and leave one particle a tick each. Destroyed 300 ticks after
launch or 36 after the burst.

**DiseaseCloud_run** 0x2ce6e0: radius +0x5c grows by 0.5 to +0x58; three streams of
+0x58 / 10 particles inside the radius (velocities ball × 6, × 6, × 12); every 30th frame
`damage_apply` with a disease entry (0x26, +0x60, +0x60, 0) to everything in the
± int(radius) box but the owner (two players are skipped) — **with no attacker** (a1 = 0).
E (gameplay, recorded here because the visual function does it).

**SpellArena_run** 0x305bbc: driven by the s16 at 0x5038c8 (I: the arena's countdown);
sets/clears object flag 2 of the fighter at 61; from 30 on int(23 f) particles at random
model sample points (spell generator), every fourth of a second definition, and the
fighter's two tint colours fixed. The two particle calls are at 0x305e10 (the index
masked with 3 is not 0) and 0x305e28 (the index is a multiple of four). **O** 0x305d88,
0x305e08.

**SpellHornOmenEffect** (ctor 0x2fc574, run 0x2fc684; made by a script command, caller
0x146628): the Spell base (ONE SHARED DRAW), a particle group, 600 ticks. Each tick the
group matrix is set to the creature's position turned by its facing (`mat34_setPosRotZ`
0x163b30 → `particleGroup_setMatrix`) and the particles are spawned *inside the group* at
model sample points taken at the origin with facing 0 — i.e. in model space, carried by
the group matrix. Tint ramps over 140 ticks. (A group's particles are local to its matrix:
13.2.)

**SpellPlanarSteelEffect** (ctor 0x2fb728, run 0x2fb9b4; script, caller 0x1466d4): 240
ticks; light radius (kind + 0x42) + 10 sin16(frame × 1000); a 60-particle ring burst 18
above the creature when the countdown +0x1c (= int(height × 3)) first goes negative; two
orbiting glows 40 out (angles −0x5dc a tick) with 6 + 4 sparks each; 10 falling sparks
and 10 ground sparks (`terrain_heightAtPoint` + 5) a tick. Spell generator.

**StaticFire** (ctor 0x2c5240, ctor2 0x2c54f8 for level fires with properties `bigOne`,
`smallOne`, `lockWind`, `radius`, `density`, `fire`; initCommon 0x2c5814; run 0x2c595c;
draw 0x2c65e8; helpers 0x2c6aa8 wind, 0x2c6bc0 add flame, 0x2c6df0 move flames): a ring of
flame points (100 at +0xbc, or 250 in an allocated block for `bigOne`) rises 7/16 a tick
and drifts with the wind (changed every 61 ticks unless `lockWind`); a point is added on
one own draw in 14. While burning, alive and `isNearView(941)`: the light flickers, int(4 ×
density × fade) flame particles a tick, embers on one draw in 33, and every 12th frame
`damage_apply` (fire 0x15) to everything in its box — for players with a shared draw for
the amount (Fire Weapons' tier-2 statistic). The draw slot draws one big glow and one glow
per flame point, coloured by height, dimmed in levels whose name contains a given string.
Constructors call `path_blockNodes` 0x18b6c0 (AI pathing) — gameplay. ctor halves the
life when more than three objects stand within 30. E. The isNearView gate of the damage is
the hazard of `docs/skills.md` table row 7 (D6/D7), now executed.

### 15.6 Executed counts per entry point

`python3 tools/difftest_fx_skills.py --table FILE` (and `--table FILE --decode
difftest_skills_a|_b|_c|difftest_arena_monsters --quick`) writes, per entry point the
difftest called, the least, most and total number of each primitive one call of the
ORIGINAL made. These are ranges over the tests' random states, not limits. Examples (E):

| Entry | Calls | Primitive | least–most |
|---|---|---|---|
| ShockOfFrost_run | 10 | particle | 64–64 |
| SpellConeOfFire_run | 112 | particle | 28–28 |
| HolyStrike_run | 67 | particle / trail_point | 24–99 / 1 |
| DiseaseBolt_run | 70 | particle / fx_spawn | 16–46 / 0–1 |
| MultiFireProjectile_run | 387 | particle / trail_point | 0–10 / 1 |
| FireStormFlare_run | 704 | particle / decal | 0–170 / 0–1 |
| SkillWizardBeam_cast | 8 | trail | 11–21 |
| SkillSummonSkeleton_cast | 8 | particle | 0–232 |
| SpellCriticalHit_run | 157 | particle (in a group) | 0–44 |

Full tables: run the command above on your own executable (376 rows; derived from the
game's behaviour, so kept out of the repository).

### 15.7 Coverage

161 / 161 effect-calling functions of the skill files have an executed model (140 before
this round, 21 now); 91 / 91 classes. Not covered: effect classes outside 0x2c3cd4–0x320000
(monster files, weapon procs, props), which the skill call map does not list; the draw
slots' *GS output* (glow geometry is the render fork's); describeRank (text).

## 16. Pools, emitters, decals and fire props, executed (round 2)

The round-1 references `tools/ref_particles.py` and `tools/ref_lighting.py` were
difftested against the original (`tools/difftest_particles.py`,
`tools/difftest_lighting.py`); the differences found are fixed in them with their APIs
unchanged and listed in section 17. Two new references, `tools/ref_decals.py` and
`tools/ref_fx_props.py`, cover what round 1 described in prose only. Lighting results are
in `docs/lighting.md` section 9.

### 16.1 Pools, definitions, emitters — Executed (`tools/difftest_particles.py`)

- The pools must be built the way the game builds them: the C++ static initialiser
  `particle_staticInit` 0x195d30 (1, 0xffff) sets every list head of the global set
  0x44fa98, of a second list set at 0x44fb98 and of the 16 groups to {0, 0, 1, 0x101};
  `particle_init` 0x18e648 then lays out the pages. Nothing else reads or writes 0x44fb98
  (gxref): an unused second list set (I). Without the static initialiser a group's lists
  have cursor 0, and a spawn into one writes through a null page.
- **Slot 0 is never free.** `particle_init` claims it (0x195bb0) for the definition at
  0x7e1d00, which no spawn uses and no reset releases (`particle_resetAll` clears slots
  1–31). Definitions get at most **31** resident slots; the 32nd distinct definition is
  dropped. Executed ("pools": 4,658 drops for want of a slot in the quick run alone).
- Retirement reads the particle's +0xe: slot = +0xe >> 2, and the definition is found
  through the resident record's +0x18 (the definition's own address, def +0x28). O
  0x18f744–0x18f7a0, Executed ("pools").
- **Group lists belong to the group slot**, not to the handle. `particleGroup_create`
  does not reset them; `particleGroup_free` and the level reset do. `particleGroup_end` and
  `_begin` ignore a stale handle, so a caller that frees a group while it is the current
  list set keeps spawning into the freed slot's lists: those particles are neither retired
  (the updater skips groups whose handle is 0) nor drawn (only live groups are drawn,
13.2), and the next group created in that slot inherits them. Executed ("pools":
  9,288 spawns into a freed group in the quick run). Whether a caller does this was not
  looked for (U).
- Back-dating: `n = trunc(60 × backdate)` is a single-precision multiply rounded toward
  zero, so a back-date of k/60 s gives k − 1 ticks for many k (17, 19, 21, 23, …). Executed
  ("spawn record").
- The definition's rates are cut toward zero: `crate = (end − start) × (1/life)` with both
  operations truncated, so a channel whose rate is inexact ends one short of its end value
  at age = life (e.g. 0x20 → 0xff over 30 ticks ends at 0xfe). Executed for the definition
  bytes ("definition", 44,699 floats bit-identical); the vertex program gives the same
bytes on screen (13.1).
- Trails are aged by `particle_updateTask` only while 0x44fc98 is 0 (0x18fa08). Who sets
  0x44fc98 was not looked for (U); `particle_resetAll` calls an empty function when it is
  set.
- The level emitter type's definition (world_fixup 0x1820d4–0x182164) is exactly
  `ParticleDef.from_emitter_record`. Executed ("emitter definition").
- `emitter_run`: counts, on/off timer (`next = trunc(now + d + (r − 0.5) × d)` in
  truncating single precision) and the cosmetic seed exact; positions and velocities
  within 2.7 × 10⁻⁵ relative, the gap being `math.cos` against `math_cos16`. Executed
  ("emitter").


### 16.2 Floor decals — Executed (`tools/difftest_decals.py`, reference `tools/ref_decals.py`)

- New reference `tools/ref_decals.py`: the gate (an **unsigned** type comparison, so a
  negative type passes at detail 0), the grid, blocks taken from the free list in index
  order, the 15-decal cell limit, the record, the z range of a block (starts at 0, so it
  always includes z = 0), the counted decals and the 16 growing slots.
- Growth adds **0.19999999** (any grow value but 2) or **0.049999997** (grow 2) per
  draw-task call, writes the corner vector from the new size, and releases the slot once
  size ≥ final — so the last size passes the final one by up to one step (1.0 grows in 6
  steps to 1.1999999). Until the first draw-task call the decal has its full size.
- `decal_reset` 0x19f018 clears the blocks and the grid but **not** the 16 growing slots
  0x840310: a decal still growing at a level reset keeps writing its corner vector into the
  recycled block memory until it reaches its size (I from the code; not executed).

### 16.3 Fire props — Executed (`tools/difftest_fx_props.py`, reference `tools/ref_fx_props.py`)

Bit for bit per tick, all draws from the object's generator (+0x44):

- **Torch** (kinds 0–5): flames per tick 1, 1, 3, 1, 4, 3; each: velocity = 2u + (0, 0,
  4.7999997) and position = object + offset − (0, 0, 12), u and the offset unit-ball
  points; offset (4x, 4y, 4z) for kind 0, (10x, 10y, z) kind 1, (10x, 10y, z + 5) kinds 2
  and 5, (5x, 5y, z + 10) kind 3, (15x, 15y, z + 10) kind 4, its z made positive; kind 3
  back-dated 0.25 s. On frames with `g_simFrame & 7 == 0`, after each flame, kinds 0–3 add
  a smoke particle with the **same velocity** plus 20 × r on z, at object + |10w| (z
  positive). Sparks: kinds 1–3 and 5, when a draw ≤ 0x319 (794 in 65,536), velocity 30.36w
  + (0, 0, 12.65) at the object. Radius 160 + trunc(22 × noise); the light moves to object +
  8 × (three noise samples).
- **Candle** (Candle, Candle2): one particle a tick at (object x, y, |u.z| + z − 4), or + 8
  for the big one, velocity (0, 0, 0.29999998 v.z + 3.5); radius every 5th tick.
- **Candle3** (`Candle2_ctor` 0x2b30ec, round 1 "not read"): no light; one particle
  0x8e48d0 a tick at z + |2u.z| + 5, the same rising velocity.
- **Lantern**: as round 1; **Lamp**: 2 particles a tick at the object, velocity 2.846 ×
  normalize(w).
- All stop running (`obj_stopRunning`) on the call where their s8 undrawn counter is 31 or
  more, then count on.

## 17. Corrections to round 1

Round-1 text above is kept as it was written; where it is wrong or incomplete, this list
says so. "§n" is the round-1 section. Lighting corrections are in `docs/lighting.md`
section 9.

| § | Round 1 said | What is true | Evidence |
|---|---|---|---|
| header, 11 | "Everything in this document is cosmetic … unless a line says otherwise" | Skill and effect classes place particles with the object's (+0x44) or spell's (+0x10) own generator in 81 of the 161 effect functions of the skill files; those generators also roll damage. 40 build a `LightEffect`, whose `GameObject` constructor draws the shared seed. `fx_spawn` id 5 and the ice shatter draw the shared seed. Only the particle system's own state, glows, trails, beams, decals and lights are per machine. | E (15.2, 14.1, 14.4) |
| 1, 3 | 32 resident type slots; "if all 32 are used the particle is dropped" | slot 0 is held for good by the definition 0x7e1d00 (`particle_init`): 31 serve definitions | O 0x18e704, E "pools" |
| 1 | the list sets | the static initialiser 0x195d30 also initialises a second list set 0x44fb98 that nothing uses, and the group lists | O, E |
| 3 | +0xe "nothing tests the field" | retirement reads it (slot = +0xe >> 2) to find the definition through the record's +0x18; it is not a dead marker (that part stands) | O 0x18f744, E |
| 3 | back-date n = trunc(60 × backdate) | right, in truncating single precision: k/60 s gives k − 1 ticks for many k | E "spawn record" |
| 4 | "its end colour and size are reached at that age" | an inexact rate is cut toward zero: a channel can end one short of its end value | E "definition", 13.1 |
| 4 | groups: lists per handle (implicit) | lists belong to the group slot; create does not reset them; a freed group that is still the current list set keeps receiving particles, which are neither retired nor drawn and are inherited by the next group in that slot | E "pools" |
| 4 | kind 2: the second vertex's alpha "not settled (U)" | alpha 0 at the lagged end; Gouraud line; the head's clip test sets ADC on the tail | E 13.1 |
| 2 | "The sheet's real height was not read (U)" | 512 × 160 texels used (GS 512 × 256): 16 × 5 cells; tiles 0x50 and up sample GS memory below the sheet | O 13.9 |
| 6 | "glow_draw(1) before the particle packet (sort key 4), glow_draw(0) after it (sort key 3)" | that is the call order; the GS order is the reverse: key 3 (pass 0) first, then the particle packet, then the key-4 glow packets | O, E 13.3 |
| 7 | trail half-width "that over w (I for the unit)" | side = (d.y, −d.x)/\|d\| · W/w with x doubled, W = width byte × 40, d from pre-divided clip space | E 13.4 |
| 7 | trails drawn from the oldest point | from the oldest index rounded down to even | E 13.4 |
| 7 | beams: midpoint + (2r − 1) × amplitude × scale; seed not given; counter "libc rand() & 7" (a third generator) | the points use a seed set to g_simFrame × 0x229 + index × 0x3f3 for the rebuild and then put back, so the shape changes once per simulation frame; the drift uses the live cosmetic seed once per drawn frame; the beam's ends are not points of its polyline; the node's z drift subtracts offset.y; the counter is an integer word from libc `rand()` | E 13.5 |
| 6, 10 | glow textures "0x4f848c", "0x44fe04" unknown | `fx.lmp` : `halo2.tex`, `engine.lmp` : `halo1.tex` | O 14.2 |
| 10 | "The 23 definitions it uses" | 24 (flags 0x4f87bc …) | O, E 14.1 |
| 10 | id 6: "y and z × 16" | all three axes × 16 | E |
| 10 | ids 10, 0xb, 0xc: jitter 12, z + 18 | first group J10 without lift, second J12 + 18; 0xb's extra five at the second centre + ball × 5, velocity ball × 21.6 + (0, 0, 1.633) | E |
| 10 | id 0x13: then 0x870228 at a quarter of that speed | only when a further draw % 10 = 0 | E |
| 10 | id 0x15: 5 + 5 particles, S 24 | first five S 12, second S 24; the vertical terms use an integer `abs` of a float and are 0: a flat ring | E |
| 10 | id 0x16: vel × 5, z × 25 | z uses \|u.z\|: both always rise | E |
| 9 | death and part recipes "not read further (U)" | executed recipes; two of the eight part functions (0x238360, 0x2672f4) have no caller | E 14.3–14.5 |
| 11 | `fx_modelStatusEffects`: "the amount scaled by the entry's value" | the entry value only switches an element on; the amount is the caller's f12; poison and disease measure the motion against the same frame twice, so their counts ignore the motion | E 14.6 |
| 11 | call map: `SpellResurrect … G draw` | drawn only with one player in the session | O 0x312f50, E |
| 11 | call map: `MultiFireProjectile … F end` | `fx_spawn(8)` with level flag 0x40000, else `fx_spawn(2)` | E |
| 11 | call map: `DiseaseCloud … P run`, `StaticFire … P run` | they also deal damage (DiseaseCloud with no attacker; StaticFire only while `isNearView(941)` — the D6/D7 hazard) and StaticFire blocks path nodes | E 15.5 |
| 11 | legend: `fx_modelParticlesNearCamera_1f61c0` "with light", `_1f5210` | 0x1f61c0 = `fx_shockModel` (three beam arcs with end sparks), 0x1f5210 = `fx_burnModel` (two passes of sample-point particles): renamed to the names the skill models use | E 14.7 |
| 8 | growth "until it reaches size" | steps of 0.19999999 / 0.049999997, released once size ≥ final, so the last size overshoots by up to a step; full size until the first draw-task call; `decal_reset` does not clear the growing slots | E 16.2 (the reset: O) |
| 8 | decal gate "at 0 only types ≥ 3" | an unsigned comparison: a negative type passes | E 16.2 |
| 8 | block z range (implicit) | starts at 0, so it always includes z = 0 | E 16.2 |
| lighting 3.2 | `Candle3` "a different class, not read" | no light; one particle 0x8e48d0 a tick (16.3) | E |

## 18. Still open after round 2

- The `MULq | WAITQ` pair (13.6): whether the console's VU waits before the upper half reads
  Q. It changes kind-2 line tails and single-point trail widths. Both readings are
  modelled; waiting first is inferred. One trail drawn with two widths on PCSX2 or a
  console would settle it.
- The last bit of VU and FPU arithmetic against a console: every interpreter here assumes
  round toward zero; none was checked on hardware.
- What GS memory holds below the 160 lines of `particletex.tex` (tiles ≥ 0x50): a GS dump.
- `model_getSamplePoint` / `model_transformSamplePoint` on real models (14.x recipes are
  given in terms of them; the difftests answered them synthetically).
- Who sets 0x44fc98 (trails not aged while it is set), what 0x5038c8 counts (SpellArena),
  whether any caller frees a particle group while it is the current list set (16.1).
- Effect classes outside the skill files (monster files, weapon procs, props other than the
  fire props of 16.3) were not covered by the recipe difftests.
- `light_emitModelLightsVariant` 0x149828 and `light_pickShadowLights` 0x148c98 (lighting).

## 19. `math_cos16` in this subsystem (2026-10-20)

The two routines, the operation order, and every caller are in `docs/spec/trig16.md`.
Short form, for this document:

- **Polynomial, not a table.** `math_cos16` 0x166630 and `math_sin16` 0x1666e0 take a
  16-bit angle. The sine is a copy of the body after subtracting 0x4000. Coefficients are
  immediates. Each multiply and add truncates toward zero. **Executed** over all 65,536
  angles (`tools/difftest_trig.py`).
- **The one table is the haze circle** `g_hazeCircle` 0x7ec0e0. `particle_init` writes 64
  pairs, angle `i << 10`, `trunc(sin16 * 5)` then `trunc(cos16 * 5)`. The words are not in
  the ELF. `particle_drawHaze` reads one pair: index
  `trunc(slot[+0x2c] + slot[+0x3c] * float(clock − cell[+6])) & 63`, no blend. Those two
  slot fields are the start alpha and the alpha rate (section 2). **Executed** for the 64
  pairs; the reader is Observed.
- **Beams do not call either function.** Glows, `trail_setCircle`, the emitter yaw and the
  emitter's eight `mat34_rotateAxis` calls do. `trail_sweepPairs` goes through
  `quat_fromAxisAngle`. Sites and the decal and fx helpers: the spec, sections 5.1 and 5.2.
- `tools/ref_particles.py` `_cs` is still the host cosine. The schedule does not read it.
  At yaw 0 an x offset of 100 stays on the x axis in that model; the original gains a y of
  `−100 × 2⁻²²`, because `sin16(0)` is `+2⁻²²`. The other effect references already call
  the polynomial, so those results do not move.
