# The Elden Ring WORLD layer (Godot, Remastered mode, owner-local)

Started 2026-10-25. The owner wants the levels to *look* like Elden Ring while the game stays Champions. The collision,
paths and scripts are the game's; only what is seen changes. The Elden Ring files are the owner's own copy, converted on
his machine into `local/souls-ref/er-world/`. They are never tracked, never uploaded, never shared. Without that folder
nothing changes.

Everything below says **Ran** (with what was seen) or **Read**.

## STATE (2026-10-25)

Phase 1 steps 1-3 are **working, Ran**. Step 4 (the hub's fitted rebuild) is **not started**.

| Step | State |
|---|---|
| 1. Materials by class, ER albedo + normal, world scale, triplanar, blended | **done, Ran**: 8 classes; reader + our own table (`er_world.cfg`); hub, valor, arachna1 (cave), fire1 pictured |
| 2. Grass (MultiMesh, swaying, density by distance, no collision, not on paths / against walls) | **done, Ran**: valor 3,340 points, ~330 drawn near the eye; hub 424 |
| 3. Skies: ER cloud layer tinted by the level's own sky | **done, Ran**: valor (blue), fire1 (orange), hub (above its dome) |
| 4. Hub fitted rebuild (ruin pieces fitted to the Champions shapes, a hand's-width check) | **not started** (plan below) |
| Gate: before/after pictures, no seams/flicker, 60+ fps, room in step | **Ran**: pictures in `local/er-world/gate/`; **106.8 fps with the layer, 107.3 without**; **room in step** (1,854 ticks) |

Built into `local/godot-r25/` (extension and project). Not committed.

## How it works

**Read** `tools/godot/extension/src/rta_world.cpp` (new), `tools/godot/project/er_world.gd` (new),
`shaders/er_world.gdshaderinc`, `shaders/er_grass.gdshader` (new) and the hooks in `rta_drawer.*`, `rta_scene.cpp`,
`gs_draw.gdshaderinc`, `sky.gdshader`, `scene_view.gd`.

### Look keys

- `look.er_world = on | off`. The default is on, but nothing happens unless the folder is there.
- The Classic look sets it off (`portal/edition.gd`).
- `RTA_ER_WORLD=off` forces it off whatever the look says (used by the room test).
- `er_world_strength` 0..1. A negative value is a test aid: it paints each class in a colour of its own.
- `er_grass` is the grass density (0 = no grass).
- The folder is `$RTA_ER_WORLD_DIR`, else `local/souls-ref/er-world` beside the staged project.

### 1. What a piece of the level is made of (`rta_world.cpp`)

The level's chunks each have their own pre-lit texture (`docs/formats/world.md`). So the class is read per texture.

- **When it is read.** At the texture's first draw of the level (`world_scan`, called from `scene_take` for every solid
  level draw).
- **What is read.** Its texels times the mean of the game's vertex light over its pieces (`tint`). The hub's grass, for
  example, gets much of its colour from the vertex light.
- **Per texel.** Each texel gets a membership of five families (grass, dirt, sand, snow, stone) by hue, saturation and
  brightness: `member()`, mirrored in the shader as `er_member`.
- **The whole texture** adds what only it shows:
  - strong, even edges on grey read as **cobble** (`cobble_edge`);
  - one-directional edges on brown read as **wood**.
- **The result.** The strongest family is `er_class`. A second family that covers at least 14% of the texture is
  `er_class_b`; the shader picks between the two per pixel (a path through grass).
- **Not read.** A texture whose alpha is in use (some texels high, some low) is a cut-out and stays as it is. A texture
  whose alpha is low everywhere does not use it.
- **Our own table** (`er_world.cfg`, applied by `RtaDrawer.set_world_layer`):
  - `[textures]`: by the art-pack name `figure-palette`;
  - `[remap]` or `[level.<name>] remap_<class>`: a whole class remapped;
  - `grass_hue`: where grass's band of hues starts.
  - Tuned so far:
    - hub: `grass_hue 36`, dirt -> stone, wood -> stone (its grass is a grey olive; its pink floor reads warm);
    - fire1: dirt -> stone (volcanic ground).
- **How it is drawn.** The class goes into the material key (`material_for(..., er)`) with a new variant bit `V_ER` /
  `GS_ER`. For a fused two-pass chunk, each pass carries its own class (`er_class2*`).
- `app er world info FILE` writes every texture drawn in the last 2 frames as JSON: class, guess, table, mean, fractions,
  edge, aniso. `app er world cost` and `app er world grass` print the layer's cost and grass counts.

### Shader (`er_world.gdshaderinc`)

- **Mapping.** Two `Texture2DArray`s (albedo, normal; one layer per class, 1024², mip-mapped), sampled in world space:
  - triplanar, with the game's own normal (`v_er_normal` from CUSTOM1);
  - one repeat every `[scale]` units (a character is about 65 units: 36 units ≈ 1 m);
  - a second, 3.7× larger turned repeat (`big` 0.35) over it, so a field shows no tiling.
- **Detail.** The material's albedo divided by its own mean is a detail factor, scaled by `[amount]`. It goes over
  `mix(low, texel, keep)`, where:
  - `low` is the game's texture read about 2.6 mip levels coarser (its colour where the detail is);
  - `keep` is the share of the game's own detail that stays: the hub floor's carvings, fire1's lava swirls.
- **Relief.** The normal map bends the normal. The difference it makes against the level's light (`rta_sky_sun`)
  brightens or darkens the pixel (0.55..1.45).
- **Two classes.** The shader chooses per pixel by `er_member` of the texel times its vertex light.
- **Steep ground.** Grass, dirt, sand and snow that stand up steeply (|n.z| < 0.62 .. 0.32) go over to stone: banks,
  cliffs and cave sides are rock.
- **Distance.** The detail fades out from 55% of `far` (2600 units) to `far`.
- All derivatives are taken before any branch that differs between pixels, with explicit `textureGrad`, so there are no
  mip seams.

### Materials chosen (local list, `local/er-world/work/make_world.py`)

Each was picked from contact sheets of the low-resolution versions:

| Class | Material |
|---|---|
| grass | the field-grass ground |
| dirt | the soil (normal derived from albedo: the soil's own was not fetched) |
| stone | a cliff rock |
| cobble | square setts |
| wood | vertical planks |
| metal | a grey metal plate |
| sand | a pale sand |
| snow | a snow ground |

The grass card is a wide grass clump. The clouds are a cloud field, made seamless with a half-shifted copy; its alpha is
the cover by brightness.

### 2. Grass

- **Scattering** (`world_scan`). Once per level piece of a grass-class draw:
  - points on triangles facing up (n.z ≥ 0.8), by area, `density` per 1000 square units (2.4);
  - deterministic: hashed from the piece and the triangle;
  - each kept only where the texel under it, times the vertex light, reads as grass (≥ 0.45). A path or stone painted
    into the grass stays bare.
- **Walls.** Every piece's walls (|n.z| < 0.5) are written into an 8-unit cell grid with their height span. A point
  within one cell of a wall at its height is not drawn.
- **No grass on cut-out cards.** Tree crowns were growing grass at first; alpha-tested draws are now skipped.
- **Points near the eye** (`get_grass`):
  - within `radius` 1400 units;
  - all of them out to a third of the radius, then thinning to a quarter at the edge (by each point's own number).
- **Drawing** (`er_world.gd`). One MultiMesh, rebuilt when the eye has moved 40 units or every 45 frames:
  - a tuft is three crossed cards, 34 units high, turned and scaled by the point's number;
  - colour = the ground's own colour there × the card's detail;
  - no shadows cast, no collision.
- **Shader** (`er_grass.gdshader`):
  - wind: a slow wave plus a flutter, bending the tops;
  - a tuft shrinks away before the thinning drops it, so nothing pops;
  - alpha sharpened by its own rate of change, so the blades do not melt into blobs at a distance;
  - lit and hazed like the level's pieces.
  - The world's draws are in Godot's transparent pass, so the grass is too (`blend_mix`, `depth_draw_always`, discard),
    with a sorting offset of 1e6 that puts it after the level. As an opaque material it had been covered by the sky
    sphere: holes in the ground, seen in the first try.

### 3. Sky

- `sky.gdshader` lays the cloud picture as a far ceiling over the procedural sky, drifting slowly.
- It is tinted by the level's own sky colour at that direction (`tint` 0.7) and lit from the level's sun side.
- It is dimmed where the sky is dark, so a night or cave sky stays dark.
- Where the level has a painted dome, the clouds start above the dome's upper edge, where the dome becomes the sky. A
  hard arc seen on the hub at first is gone.

## Gate (Ran)

### Pictures

Before above, after below, 1280×720: `local/er-world/gate/{hub,valor,arachna1,fire1}-{ch,sh}.jpg` (`ch` = chase /
gameplay distance, `sh` = shoulder / close); 3024×1964: `gate/valor-3024-on.png`. Runs: `local/er-world/t/r7` (final),
r3..r6 (tuning).

| Level | What was seen |
|---|---|
| valor | dense swaying ER grass over ER-grass ground; cliffs with rock detail; clouds in the blue sky |
| hub | floor keeps its carvings with fine stone grain; olive grass gets grass detail and a few tufts; clouds only above the dome |
| arachna1 (cave) | gravel on the floor, rock on the walls; subtle, darkness kept |
| fire1 | lava-rock grain over the game's swirls (kept); orange-tinted clouds |

### Seams and flicker

- **Seen:** no seam lines and no new shimmer. The mapping is world-space and the derivatives are explicit.
- **Not judged frame by frame:** flicker. Only stills were taken; no recording was made.

### Frame rate

Paced, 3024×1964; hub, valor, arachna1, fire1; chase and shoulder; `local/er-world/t/fps-{on,off}/frames.csv`:

| | Layer on | Layer off |
|---|---|---|
| Mean fps, stalls over 50 ms left out | **106.8** | 107.3 |
| Median picture gap | 8.93 ms | 8.71 ms |
| 99th percentile gap | 17.2 ms | 17.3 ms |

The layer's own GDScript time is 16 µs a frame (mean); the worst was 1.9 ms, a grass rebuild.

### Room (`local/godot-r25/test/room25.py ew1 --level valor`)

Both copies were Remastered; B ran with `RTA_ER_WORLD=off`. A drew the layer in hub and valor; B drew none.
**1,854 ticks compared, no shared column differs.**

## Fetching the files (local only)

- **Download.** The remembered DepotDownloader login, with the range patch (`RTA_DD_RANGES`, `RTA_DD_ACCOUNT` = the
  stock build's remembered account file). No password was asked. Fetched:
  - the material index (`/material/allmaterial*.matbinbnd`, 5 MB): material names say what each texture is used for;
  - the low-resolution versions of six environment texture groups: 1,379 files. Their chunks are interleaved
    with the full ones, so 1.07 GB was fetched.
  - 15 full packages (9 more chunks).
- **Decompression.** The DCX streams are Oodle Kraken, which the open decoders cannot read. They were decompressed with
  the game's own DLL in the Windows test VM. UTM's `utmctl start` timed out (OSStatus −1712), so the VM was run by
  Homebrew QEMU directly from its UTM disk with `-snapshot` (its disk unchanged): `local/er-world/vm/run.sh`, ssh on
  127.0.0.1:2222. The VM was stopped after.
- **Conversion.** Scripts in `local/er-world/work/`: `undcx.py`, `tpf.py`, `dds2png.py` (sRGB DXGI forms read as plain),
  `make_world.py` (the folder).

## Next

- **Step 4, the hub's fitted rebuild.** Fetch ER ruin assets: the `aeg` geometry bundles of ruins, stairs and stone
  rings, found by material names like the terrain was. Convert them with `flverdump` and fit them to the hub's
  plinth/obelisk and rings by their bounding shapes. The check: sample the seen surface and measure its distance to the
  game's collision triangles (the level's chunks from the scene tap); within ~8 units (a hand's width), else that piece
  is refused.
- Tune the reader per level on class pictures (`er_world_strength -1`): the cave walls read partly dirt (handled by the
  steep rule); wood/metal are only from the table.
- Grass:
  - painted flower patches (blended decals) are grown over; skip points under decal draws;
  - a second card (small plants).
- Fetch the soil's own normal map.
- Flicker check from a recording.

## Changed

**New (tracked):**
- `tools/godot/extension/src/rta_world.cpp`
- `tools/godot/project/er_world.gd`
- `tools/godot/project/er_world.cfg`
- `tools/godot/project/shaders/er_world.gdshaderinc`
- `tools/godot/project/shaders/er_grass.gdshader`
- this file

**Modified (tracked):**
- `tools/godot/extension/src/rta_drawer.{h,cpp}`
- `tools/godot/extension/src/rta_scene.cpp`
- `tools/godot/extension/src/rta_variant.h`
- `tools/godot/project/scene_view.gd`
- `tools/godot/project/portal/edition.gd`
- `tools/godot/project/shaders/gs_draw.gdshaderinc`
- `tools/godot/project/shaders/sky.gdshader`

**Local:**
- `local/souls-ref/er-world/` (the materials)
- `local/er-world/` (scripts, runs, gate, VM runner)
- `local/godot-r25/` (build, `test/room25.py`)
- the partial archives in `local/souls-ref/er/Game/`
