# Lighting: level light, light nodes, torches, light effects, fog

Status: first pass, 2026-10-17, on branch `t3/research-fx`, read from the disassembly and a
Ghidra decompile of `SLUS_209.73` (v2.00). Round 2, 2026-10-18: executed against the
original in `tools/ee_emu.py` (`tools/difftest_lighting.py`, `tools/difftest_fx_props.py`);
results and corrections in section 9. Round 3, 2026-10-20: the per-level light record
(section 10). **Observed** (O) = read at
the address given, **Inferred** (I), **Unknown** (U). Reference contract:
`tools/ref_lighting.py`, tested by `tools/test_ref_lighting.py` on synthetic values.

The GPU side — what the vertex programs do with the lights they are given — is in
`docs/spec/render-pipeline.md` sections 4.6 (level chunks), 4.7 (models) and 5; this
document does not repeat its formulas but gives everything that decides **which** lights,
**what** colours and radii they have, and how they change over time. Particles, glows and
decals are in `docs/effects.md`.

Short answer for a renderer:

- There is **no fog** and no per-pixel lighting. The GS fog field is never enabled
  (render-pipeline 4.3); distance ends at the far clip (≤ 1800 units, `camera_setFarClip`
  0x18617c, lowered by the script command `setFarClip` 0x144104 and by cutscenes).
- Level geometry: the texture already carries the baked light; each vertex adds a base
  level (0x80, 0x40 or 0x20 by level flag) plus up to four point lights.
- Models: ambient + sun + fill + the two best point lights, per vertex, Lambert, no
  specular. The sun has no shadowing (the visibility lookup is a stub returning 1.0).
- Point lights come from the level file (16 slots, flickering), fire objects (torches,
  candles, lamps, lanterns), the `AddParticle` helper, `LightEffect` objects (spells,
  hits) and two per-creature property lights.

## 1. Level light — O

`light_setLevelLight(dir, sunR, sunG, sunB, sunA, ambR, ambG, ambB, ambA, level)` 0x14a2d8
stores, at 0x5d3448:

| Address | Meaning |
|---|---|
| 0x5d3448 | sun direction (unit vector **towards** the light), normalised here |
| 0x5d3474 … 0x5d3477 | sun colour as set (rgba bytes) |
| 0x5d3478 … 0x5d347b | ambient colour as set |
| 0x5d346c, 0x5d3470 | the same eight bytes scaled each frame (below) |
| 0x5d347c | `g_worldLightLevel`, the base level of every level vertex |

`game_loadLevel` fills it from the marker objects `charAmbient_Light`,
`charDirectional_Light`, `charDirectional_LightD` (position × 0.5 = colour; the third's
position = direction), with defaults ambient 0x20 grey, sun 0x44 grey, direction (0, −1,
1), alphas 0 (render-pipeline 5.1, O 0x1e60e0–0x1e6154). The base level is 0x80, or 0x40
with level flag 0x04000000, or 0x20 with 0x20000000 (the level flag word 0x44fe08,
`docs/data-tables.md`). Both of those flags set yields 0x40. The executable has no
per-level colour or direction array; section 10 is the index, the marker record and the
defaults. Before any level `light_init` 0x1489c0 uses direction (−0.577,
−0.577, 0.577), sun (0x40, 0x46, 0x50), ambient 0x20 grey, level 0x80.

**Each frame** `light_writeVuConstants` 0x148728 writes the scaled copies: channel =
clamp(trunc(`g_lightScale` × as-set), 0, 255), `g_lightScale` 0x4039ac (set by
`light_setScale` 0x14a480; cutscenes pass their header +0x70 through `cut_setup`), with the
scale forced to 1 while the render layer 0x4039a4 is not 0 (the inventory and stats
screens). The base level is **not** scaled. O

`light_recalcSun` 0x148018 (task, priority 0xc) turns the sun direction into camera space
and builds the **fill** direction `normalize(−sun.x, −sun.y, 0.5 × sun.z)` (world), both
uploaded with z negated (render-pipeline 4.7). `light_pushLevelLight` 0x148578 /
`light_popLevelLight` 0x14a3c8 save and restore the whole record around screens that draw
their own scene.

### Per-object light state — O 0x148340

At the end of every object draw `light_resetObjectLight` rebuilds the per-object colours
that the model light emitters read:

| Address | Value after reset |
|---|---|
| `g_objAmbient` 0x5db370 (s16 × 4) | scaled ambient (0x5d3470) |
| `g_objSunColor` 0x5db378 | scaled sun (0x5d346c) |
| `g_objFillColor` 0x5db380 | trunc(0.8 × ambient **as set**) — the fill ignores `g_lightScale` |
| 0x5db388, 0x5db38c, 0x5db390 | point-light scale r, g, b = 1.0 |

Draw code changes them for one object before `model_draw`:

- `light_addObjectAmbient(bias)` 0x148140: ambient = ambient **as set** + bias per channel,
  clamped below at 0 (no upper clamp here; the vertex program clamps at 255).
- `light_setObjectAmbient(rgba)` 0x14a0c8: ambient = rgba.
- `light_scaleObjectLight(r, g, b)` 0x148210: ambient, sun and fill × (r, g, b) and the
  point-light scale = (r, g, b).
- `light_setObjectSun` / `light_setObjectFill` 0x14a150 / 0x14a1d8: replace a direction and
  colour.

`Creature_draw` 0x10b048 uses them so (O 0x10b0e0–0x10b3a0; the status names are those of
`docs/creatures.md`):

| Condition | Change |
|---|---|
| object flag 0x100 (set by a hit, cleared after this draw) | ambient = (255, 255, 255, 0): the white hit flash, one frame |
| object flag 0x2000000 | all × 0.6 |
| creature +0x98 (status colour bias) | `light_addObjectAmbient(+0x98)` |
| chill +0x344 = f > 0 (clamped to 1) | ambient bias (−100f, −100f, +100f, +50f): blue |
| poison +0x34c = f > 0 | bias (−100f, +50f, −100f, +50f): green |
| +0x350 = f > 0 | trunc(3f) glow sprites (size 12000 + 250 sin(g_simFrame × 1024), colour (0, 200, 0, 70), texture 0x44fe04) at the top of the creature |
| `light1` / `light2` properties | `creature_drawPropLight` 0x10ab18: a sun (light1) or fill (light2) replacement, direction from two angles (yaw a, pitch b: `(cos a cos b, sin a cos b, sin b)`), colour × (1 − flicker × `math_noise(g_simFrame × 16 + 0x7efe41)`) |

## 2. Light nodes — O `light_link` 0x148af8, `light_collectNear` 0x147bf0

Every point light is a 0x3c-byte node linked into `g_lightGrid` 0x5d34d8, 90 × 90 cells
of 256 units: cell = ((trunc(x) + 11520) >> 8, (trunc(y) + 11520) >> 8); a node outside the
grid goes on the overflow list 0x5db368 (I: such a node is never collected, since
`light_collectNear` walks grid cells only). A node must be re-linked when it moves
(`light_relink` 0x14a528, or unlink + link).

| Offset | Type | Meaning |
|---|---|---|
| +0x00, +0x04 | ptr | next node, address of the pointer that points here |
| +0x08 | s8 | render layer; only nodes of the current layer (0x4039a4) are collected |
| +0x09 | u8 | counts for the floor-decal tint (section 6). Set to 1 by the fire objects; 0 by `LightEffect` and the level light slots |
| +0x0a | s16 × 4 | colour for **models** (rgb used, alpha ignored by the model emitter) |
| +0x12 | s16 × 4 | colour for **level geometry** |
| +0x1c, +0x20 | f32 | radius and falloff for models |
| +0x24, +0x28 | f32 | radius and falloff for level geometry |
| +0x2c | f32 | floor for level geometry: < 1 a directional term, ≥ 1 non-directional (render-pipeline 4.6) |
| +0x30 | f32 × 3 | position |

`light_collectNear(pos, out, 32)` walks the cells within ±300 units of pos and returns
(at most 31) nodes of the current layer whose cube of half-size **model radius** around
the node contains pos. `light_collectInBox` 0x147de0 does the same for a box (level
chunks). The level slots and `AddParticle` clamp their radius to 299 and the fire objects
stay below 300, so for them the ±300 cell window loses nothing; `LightEffect` radii are not
clamped, so one above 300 would be cut off at the window edge (I; no such constant was
looked for).

### What a model gets — O `light_emitModelLights` 0x149268

1. Candidates from `light_collectNear(model position)`.
2. Rank by `key = (trunc(D² − R²) << 7) | index` (D = distance, R = model radius); keep the
   two smallest keys. Ties keep the earlier node.
3. For each of the two: direction = normalize(node − model) in camera space (z negated);
   colour = node model colour × clamp((R² − D²) × falloff, 0, 1) × point-light scale,
   per channel, truncated to s16; alpha 0. Missing ones are zero.
4. Slot 2 = fill (direction, `g_objFillColor`), slot 3 = sun (direction, `g_objSunColor` ×
   shade); ambient = `g_objAmbient`. **shade** = 0x18b18c(world, pos), a function that
   returns 1.0 and nothing else; 1.0 is also used with no world or a non-zero layer.
5. A caller can preselect the two nodes for one draw (0x4039b0 set: nodes 0x5db398,
   0x5db39c).

With falloff 1/R² (every source below) the weight is `1 − D²/R²`. The vertex program then
does `min(ambient + Σ max(n·L, 0) × colour, 255)` (render-pipeline 4.7). Scenery models
use the ambient-only or no-point variants by their chunk's lighting word (render-pipeline
5.4).

### What a level chunk gets — render-pipeline 5.3

Up to four nodes nearest the chunk centre among those whose box overlaps the chunk bounds,
using the **level** colour, radius, falloff and floor; floor-≥ 1 nodes fill the slots from
the top. Chunks with flags 0x100 / 0x200 / 0x2000 get a constant instead (−230 for one
frame, 0, +230).

## 3. Light sources

### 3.1 Level light chunks (`.world` chunk flag 0x8000) — O `world_runLightChunk` 0x18ba18

Run from `world_drawChunk` 0x1887b8 (0x188858) — so only for chunks being drawn, once per
rendered frame. A chunk claims one of 16 slots (`world_claimLightSlot` 0x18b93c): a chunk
keeps its slot (chunk +4 = slot + 1) while it is drawn; otherwise the slot with the oldest
draw stamp (`g_drawFrame`) is taken over and its previous chunk loses it. Slot records are
0x44 bytes from 0x7d3f68: draw stamp, owner chunk, the node.

Chunk data, 0x30 bytes (corrections to `docs/formats/world.md` marked ✱):

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | char[16] | name |
| 0x10, 0x12 | u16 | radius low, high |
| 0x14 | u16 | mode (below) |
| 0x16 | u16 | period, simulation frames |
| 0x18 | u16 × 4 | colour (both node colours) |
| 0x20 | u16 | glow size ✱ (the second `glow_add` argument) |
| 0x22 | u8 | glow wobble shift ✱: size += trunc(22 × noise) << shift |
| 0x23 | u8 × 4 | glow colour |
| 0x27 | u8 | draw a glow |
| 0x28 | u8 | glow depth bias ✱ (the first `glow_add` argument, not the size) |

Radius per call, with `timer` = chunk +0x20 and the previous radius r of the slot:

| Mode | Rule |
|---|---|
| 0 | r = low |
| 1 | when `g_simFrame > timer`: timer = g_simFrame + period, r = low + trunc((high − low) × rnd) (one cosmetic draw); else r unchanged |
| 2 | when `g_simFrame > timer`: timer = now + period; if the direction bit (chunk +4 bit 31) is set, r = low and clear it, else r = high and set it. Then, if period ≠ 0, r += (set ? −1 : +1) × trunc((high − low) / period) — **every call**, so the ramp speed follows the frame rate |
| 3 | when `g_simFrame > timer`: timer = now + period; r = low, or high when r was low |
| 4 | the node is not linked (the light is off); the glow is still drawn |

Because the tests are `g_simFrame > timer` with `timer = now + period`, a phase lasts
period + 1 simulation frames; at one call per frame the mode-2 ramp therefore takes
period + 1 steps and ends one step beyond the end it heads for (below `low`, above
`high`) before the next switch puts it back.
| other | r unchanged |

Then (modes ≠ 4) r is clamped to 0…299 and the node is written: both colours = the
chunk colour, both radii r, falloff 1/r², floor 0, layer 0, position = chunk translation
× 0.25, and linked. The glow: `glow_add(bias = +0x28, size = +0x20 + (trunc(22 ×
math_noise(slot address × 0x19660d + g_simFrame × 16 + 0x7efe41)) << +0x22), position, glow
colour, texture *0x4f848c, angle 0, flags 2 = additive)`, only when +0x27 is set and the
texture pointer 0x7d8a08 is set (`game_addCoreTasks` 0x1e6f0c stores *0x4f848c there).
The glow texture is `fx.lmp` : `halo2.tex` (round 2, section 9).

### 3.2 Fire objects — O 0x2b1e80–0x2b3a64

| Class (factory names) | Node colours (models / level) | Radius each tick | Floor | Particles |
|---|---|---|---|---|
| Torch (Torch, Fire, Campfire, Firepot, Firepot2, OilLamp; kind +0x8a = 0–5, I in that order) | (200, 150, 50) / (51, 39, 18) | 160 + trunc(22 × noise) | 1.0 | flames 0x8e4740 (1, or 3 for kinds 2 and 5, 4 for kind 4; kind 3 back-dated 0.25 s), smoke 0x8e47e0 every 8th tick except kinds 4–5, sparks 0x8e4830 about 1 tick in 80 except kinds 0 and 4 |
| Candle (factory names Candle, Candle2; `Candle3` is a different class, `Candle2_ctor` 0x2b30ec, not read) | the same | every 5 ticks 48 + ((rnd − 8) & 15), or 84 + … when +0x90 = 1 (own generator) | 1.0 | 0x8e4880 |
| Lantern | the same | 160 + trunc(22 × noise); the **level** radius is 0 in any level whose name contains `mine` | 1.0 | — |
| Lamp | the same | 216 + trunc(22 × noise) | 1.0 | 2 × 0x8e4920 per tick, speed 2.846 in a random direction |

All set node +9 = 1 (they tint decals). The constructors start with radius 240 and
falloff 1/240²; the run functions overwrite them. Only the torch also moves its light:
each axis = object position + 8 × noise (three lookups with g_simFrame × 2), without a
re-link.
`noise` = `math_noise(object address × 0x19660d + g_simFrame × 16 + 0x7efe41)`, a table built
from the per-machine seed (`docs/engine.md` P2): cosmetic, different on each machine. The
torch constructor also blocks the path cells under it (`docs/engine.md`, Pathfinding).
These objects run only while drawn recently (off the run list after 31 undrawn frames,
`docs/monsters.md`), so an unseen torch keeps its last radius. O

### 3.3 `LightEffect` — O `LightEffect_ctor` 0x201bd8, `LightEffect_run` 0x1ee050

A short-lived light object (vtable 0x50e198, 57 constructor call sites: spells, hits,
projectiles). `LightEffect_ctor(r0, g0, b0, a0, r1, g1, b1, a1 in f12…f19, this, pos,
owner, signed; stack: radius0, radius1, floor, seconds)`:

- node at +0x4c, both colours = start colour, both radii = radius0, falloff 1/radius0²,
  floor = the stack argument, layer 0, decal flag 0; linked;
- life = max(1, trunc(60 × seconds)) ticks; end = `g_simFrame` + life;
- per-tick rates (end − start) / life for the four colour channels and the radius.

Each run (every frame while it exists): colour += rate, radius += rate; channels clamped
to 0…255, or to −255…255 when `signed` ≠ 0 (a darkening light); falloff = 1/radius²;
if the owner handle is alive the light follows the owner at owner position + (0, 0, 36);
deleted when `g_simFrame` ≥ end. The node is not re-linked when the position changes
(I: it stays in the cell of its creation; collection still finds it within ±300 of that
cell, so a light that travels further than that is lost from view).

### 3.4 Others

- `AddParticle` helper `DynamicLight` (props, chests, `AutoEmitter`): radius modes 0–3 of
  section 3.1 with its own generator, colour from the `lsr…lsa` keys, radius clamp 0…299
  (`docs/monsters-2.md` section 9).
- Spell objects create `LightEffect`s (e.g. `FrostStormSpell_ctor`, `RainOfFireSpell_ctor`);
  `docs/effects.md` section 11 lists how a skill's visual is built.

## 4. Coordinates and ranges

| Thing | Covers |
|---|---|
| light grid | x, y in [−11520, 11520): 90 × 90 cells of 256 |
| decal grid (`docs/effects.md` 8) | x, y in [−3840, 3840): 30 × 30 cells of 256 |
| radius clamp | 0…299 (level light slots, `AddParticle`) |

## 5. Order within a frame

`light_writeVuConstants` (frame start) → object draws (each: modifiers, `model_draw` with
`light_emitModel*`, `light_resetObjectLight`) and the world walk (each drawn light chunk
re-links its slot; each drawn level chunk collects up to four nodes). A light chunk drawn
after the chunks it lights takes effect the next frame for them (I from the walk order;
not checked).

## 6. Floor-decal tint — O 0x148ff0 (`light_sampleFloor`)

When a decal is made its vertex colour is fixed to the light at its position:

```
for each node from light_collectNear(pos) with node+9 ≠ 0:
    d = node.pos − pos ;  w = clamp((R² − |d|²) × falloff × d.z / |d|, 0, 1)    # model radius, falloff
    c += node model colour × w                                                   # only lights above count
s = max(sunDir.z × shade, 0)                                                     # shade = 1.0
rgb = clamp(trunc(c + sun as set × s + ambient as set), 0, 255)
```

So fire objects colour decals; level light chunks and `LightEffect`s do not. O

## 7. Per-machine notes

All of it is cosmetic: the noise table, the light-slot LRU (by rendered frame), the
flicker draws of mode 1 (cosmetic seed), the ramp of mode 2 (per call) and the fire
objects' own generators. Nothing in this document feeds the simulation that was found;
`docs/engine.md` P2 already lists the torch/lantern/lamp noise.

## 8. Open

- ~~The file of the glow texture *0x4f848c and of 0x44fe04~~: `halo2.tex` and `halo1.tex` (section 9).
- Which code sets the render layer 0x4039a4 besides the screens (U).
- `light_emitModelLightsVariant` 0x149828 and `light_pickShadowLights` 0x148c98 details
  (shadow blobs; render-pipeline 4.9).

## 9. Round 2: run against the original (2026-10-18)

`tools/difftest_lighting.py` runs `light_writeVuConstants`, `light_resetObjectLight`,
`light_addObjectAmbient`,
`light_setObjectAmbient`, `light_scaleObjectLight`, `light_link` + `light_collectNear`,
`light_emitModelLights`,
`light_sampleFloor`, `world_runLightChunk` and `LightEffect_ctor` / `_run` in
`tools/ee_emu.py` and compares
them with `tools/ref_lighting.py`: 6 properties, 0 mismatches (6,757 object-light
operations, 800
node sets, 1,500 model-light blocks, 1,500 floor tints, 170,841 light-chunk runs, 16,935
LightEffect
frames; colours, radii, timers and choices exact, directions within 2.5 × 10⁻⁷). The fire
props are
executed by `tools/difftest_fx_props.py` against the new `tools/ref_fx_props.py`
(docs/effects.md 16.3).
The corrections below are applied in `ref_lighting.py`; its API is unchanged.


- The **fill** colour is trunc(**0.79999995** × ambient as set) (the constant 0x3f4ccccc),
  so an ambient that is a multiple of 5 gives one less than 0.8 would. Its alpha is the
  scaled sun alpha (unused). Executed ("object light").
- `light_resetObjectLight` also: lowers the render layer 0x4039a4 by 10 when it is above 9,
  restores the camera-space sun and fill directions (0x5d34b8 / 0x5d34c8) from the level
  ones, and clears 0x4039a8 and 0x4039a0. `light_writeVuConstants` calls it before and
  after rescaling. O 0x148340, Executed ("object light").
- `LightEffect` keeps the **fractions** of its colour: the accumulators are clamped
  (0…255, or −255…255 signed) but not truncated; the node gets trunc() of them. A rate
  below one unit per tick therefore still changes the light (round 1's reference truncated
  every tick and froze it). Executed ("light effect").
- Level light chunks: the chunk translation is an **s32** (cvt.s.w at 0x18ba3c), × 0.25.
  The 16 slots are shared: the radius a mode keeps "unchanged" is the slot's, so a chunk
  that takes over a slot starts from the previous owner's radius
  (`ref_lighting.LightSlots`). Executed ("light chunk", 16 slots shared by up to 20 chunks).
- `light_emitModelLights`: the two best are tracked in one pass from an initial key
  0x1000001f; a node whose key (trunc(D² − R²) << 7 | index) is above that is never
  chosen (only for radii above about 840, I). A missing light reads `out[31]`, which the
  function zeroes first. Executed ("model lights": colours exact, directions within
  2.1 × 10⁻⁷).
- `light_sampleFloor` and `light_collectNear` are as round 1 described. Executed.
- The glow texture of light chunks and `Fire_run` (*0x4f848c) is `fx.lmp` : `halo2.tex`;
  0x44fe04, the
  status glow of `Creature_draw`, is `engine.lmp` : `halo1.tex` (docs/effects.md 14.2).
Section 8's first item is answered.
- **Not cosmetic:** a `LightEffect` is a `GameObject`, and its constructor draws the
  shared seed once
  (docs/effects.md 15.2). Section 7 ("all of it is cosmetic") holds for the light state,
not for making
  a LightEffect: a client must construct them in the simulation even when it does not
light anything.

## 10. Per-level light record (2026-10-20)

The executable does not store a sun colour, an ambient colour or a sun direction for each
level. The level table's rows are 0x30 bytes (`docs/data-tables.md` 7.1). The only
lighting field in a row is the flag word at +0x20. **Observed.** On the US v2.00
executable the 90 rows and the default row select base level 0x80 or 0x40. The load
tail still contains the 0x20 store.

What does vary per level:

1. **Index.** `g_levelTable` 0x4f7210, 90 rows of 0x30 plus the null-name row, which is
   also the default. `game_loadLevel` 0x1e55c0 selects a row by name: `strcpy` of the
   level name, `strcat` of the literal `"_"` at 0x53da70 and of `g_levelSubName`
   0x41b771, then `strcmp` (call at 0x1e57ec); then `strncmp` of the plain name against
   each row over the name's length (call at 0x1e584c); then `strstr` of the plain name
   for a row name (call at 0x1e58b8). The row pointer advances by 48. The first hit
   wins. **Observed.** `tools/fx_level_lights.py` `lookup_level` is that order, tested
   on synthetic names.

2. **Base level.** The load tail 0x1e60e0 reads the selected flag word from 0x44fe08
   (fp 0x450000, offset −504). The value starts at 0x80. Flag 0x20000000 stores 0x20.
   Flag 0x04000000 stores 0x40 and wins when both are set. **Observed**, same rule as
   `ref_lighting.base_level`. Executed.

3. **Sun, ambient, direction.** `world_loadRecords` 0x14e808 writes the defaults into
   the marker block 0x44fde0 before objects: ambient ints 0x20, 0x20, 0x20 at +0, sun
   ints 0x44, 0x44, 0x44 at +12, direction floats (0, −1, 1) at +24. **Observed** and
   executed. Each marker object then overwrites its slot. `charAmbient_Light` 0x158bcc
   stores trunc(position × 0.5) at +0; `charDirectional_Light` 0x158c6c the same at +12;
   `charDirectional_LightD` 0x158d0c stores the position floats at +24. **Observed** and
   executed. The three class-name strings are referenced by the factory compare at
   0x159c94 and by typeinfo. They are not an array of colours in the executable.

4. **The record the renderer reads** is the one `light_setLevelLight` 0x14a2d8 writes
   at 0x5d3448 (section 1). The load tail copies the marker ints through the low 8 bits,
   the direction, both alphas 0, and the base level, then calls it (0x1e60e0–0x1e6158).
   **Observed.** Executed against `LevelLight.from_markers` (`difftest_lighting.py`,
   property "level light").

Marker block 0x44fde0, 36 bytes:

| Offset | Meaning |
|---|---|
| +0 | ambient r, g, b as signed ints; the byte stored later is the low 8 bits |
| +12 | sun r, g, b as signed ints |
| +24 | direction x, y, z floats, not normalised here |

Runtime record 0x5d3448 (`light_getLevelLight` 0x1484c8):

| Offset | Meaning |
|---|---|
| +0 | sun direction, 3 floats, unit length, towards the light |
| +0x2c | sun rgba bytes (0x5d3474) |
| +0x30 | ambient rgba bytes (0x5d3478) |
| +0x34 | base level word (0x5d347c) |

`tools/fx_level_lights.py --json ELF` reads the table from the user's executable and
prints each row's name, flags and base level, plus these defaults. Optional `objects.ob`,
lump or GOB arguments add the marker colours from those files and attach them to the row
whose name matches the file stem. Retail values stay out of this repository.

`light_setLevelLightFromRecord` 0x14a260 unpacks a different record (colour bytes and a
trailing word) and has no caller in the cross-reference. **Unknown** whether anything
reaches it. The other callers of `light_setLevelLight` pass fixed screen and inventory
colours, not a row of this table. **Observed.**

**Inferred.** A client lights a real level by reading that level's flag word for the
base level and the three marker objects from its `objects.ob`, and by using the defaults
above when a marker is absent. The colours are the marker objects. The executable's
per-level contribution is the flag word and those defaults.
