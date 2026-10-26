# The Elden Ring WORLD layer (Godot, Remastered mode, owner-local)

Started 2026-10-25. The owner wants the levels to *look* like Elden Ring while the game stays Champions. The collision,
paths and scripts are the game's; only what is seen changes. The Elden Ring files are the owner's own copy, converted on
his machine into `local/souls-ref/er-world/`. They are never tracked, never uploaded, never shared. Without that folder
nothing changes.

Everything below says **Ran** (with what was seen) or **Read**.

## STATE (2026-10-26, fifth session: gate 5)

Phase 1 steps 1-3 are **working, Ran**. Step 4, the hub's rebuild: the owner's three asks of gate 4 are **done, Ran** - the
gilding is clean (no faceted shards), the pieces are lit as the level's own surfaces are (they darken in side and back light
with it, measured), and the trefoil platform, its stairs and both daises are rebuilt in the same set (carved friezes on every
riser), the whole area about 20k triangles read on worker threads. The gate **refused it on review again** (Gate 5: matches
and is richer close up, but not clearly better as a whole at play distance). The hub draws the game's own shapes.

| Step | State |
|---|---|
| 1. Materials by class, ER albedo + normal, world scale, triplanar, blended | **done, Ran**: 8 classes; reader + our own table (`er_world.cfg`); wood now read on its own (a mine's beams), metal only by a strict rule (none read on the four levels tried) |
| 2. Grass (MultiMesh, swaying, density by distance, no collision, not on paths / against walls) | **done, Ran**: clears painted flower patches and stones; no tufts in the air; valor 3,509 points |
| 3. Skies: ER cloud layer tinted by the level's own sky | **done, Ran** |
| 4. Hub fitted rebuild (ruin pieces fitted to the Champions shapes, a hand's-width check) | **refused on review** (gate 5, see Gate 5; gates 3 and 4 before it); arch **refused** by the check (max 13.4 units off), not retried |
| Gate: before/after pictures, 60+ fps, room in step | **Ran**: pictures in `local/er-world/gate5/final/`; room in step (1,858 ticks, A drawing the gate-5 pieces); fps see Gate 5 (the machine was too loaded for a clean number) |

Built into `local/godot-r34/` (extension and project). Not committed.

## How it works

**Read** `tools/godot/extension/src/rta_world.cpp`, `tools/godot/project/er_world.gd`, `shaders/er_world.gdshaderinc`,
`shaders/er_grass.gdshader`, `shaders/er_ruin.gdshader` (new), `tools/godot/er_world_fit.py` (new) and the hooks in
`rta_drawer.*`, `rta_scene.cpp`, `gs_draw.gdshaderinc`, `sky.gdshader`, `scene_view.gd`.

### Look keys

- `look.er_world = on | off`. The default is on, but nothing happens unless the folder is there.
- The Classic look sets it off (`portal/edition.gd`).
- `RTA_ER_WORLD=off` forces it off whatever the look says (used by the room test).
- `er_world_strength` 0..1. A negative value is a test aid: it paints each class in a colour of its own.
- `er_grass` is the grass density (0 = no grass; 1.2 now, see Grass).
- `er_rebuild = on | off` (default on): the fitted Elden Ring pieces (step 4). It needs `er_world` on.
- The folder is `$RTA_ER_WORLD_DIR`, else `local/souls-ref/er-world` beside the staged project.

### 1. What a piece of the level is made of (`rta_world.cpp`)

The level's chunks each have their own pre-lit texture (`docs/formats/world.md`). So the class is read per texture.

- **When it is read.** At the texture's first draw of the level (`world_scan`, called from `scene_take` for every solid
  level draw).
- **What is read.** Its texels times the mean of the game's vertex light over its pieces (`tint`). The hub's grass, for
  example, gets much of its colour from the vertex light.
- **Per texel.** Each texel gets a membership of five families (grass, dirt, sand, snow, stone) by hue, saturation and
  brightness: `member()`, mirrored in the shader as `er_member`.
- **The whole texture** adds what only it shows (measured on class pictures of hub, valor, fire1 and inmine1):
  - **wood**: a warm texture (the dirt or sand family, or a warm grey) whose edges are much stronger along one of its
    axes than the other (`wood_aniso` 1.45: a mine's beams measure 1.5..1.9, rock and lava swirls 1.0..1.2) and strong
    enough (`wood_edge`). It no longer has to read as dirt first: inmine1's beams are read as wood (13 textures).
    The structure tensor's coherence (edges one way at any turn) is measured too, but it is 0.2..0.5 for beams, rock and
    grass alike, so it counts only over `wood_coherence` 0.6;
  - **metal**: a near-colourless grey (saturation < 0.1), smooth (edge < 0.5), with a share of glints (texels 1.8× over
    its middle brightness: `metal_glint` 0.1) and a strong spread of brightness (`metal_contrast` 0.85). A first, looser
    rule read valor's cliffs as metal (they are cool and have a few glints); this one reads **no** texture as metal on
    the four levels tried, so metal is still mostly the table's. Not checked on a level with real metal;
  - strong, even edges on grey read as **cobble** (`cobble_edge`).
- `app er world info FILE` also writes `coherence`, `sat`, `contrast`, `glint`, `cool` per texture.
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
  - points on triangles facing up (n.z ≥ 0.8), by area, `density` per 1000 square units (1.2);
  - **a triangle's side is the game's normals'.** The strips' winding alternates, so half of every ground's triangles
    had been taken as facing down. With that fixed, the same density gave twice the points, so the density is halved
    (valor 3,509 points; 3,340 before);
  - **only on ground pieces:** a piece whose area faces up for less than `[grass] ground` 0.3 of it (a bush's mound,
    a rock, the hub's round shrubs: 0.06) grows none;
  - deterministic: hashed from the piece and the triangle;
  - each kept only where the texel under it, times the vertex light, reads as grass (≥ 0.45). A path or stone painted
    into the grass stays bare;
  - **painted features**: valor's flower patches are painted into the ground's own pre-lit texture. The texels within
    `[grass] clear` 10 units of the point (a 5 × 5 pattern, by the triangle's texels per unit) are looked at too: two that
    are not grass, or far brighter than the grass there (white and yellow petals), and no tuft is put there;
  - a see-through texel (a cut-out's) grows nothing;
  - **decals**: an alpha-blended level draw whose texture is see-through somewhere (≥ 2%) is a decal laid on the
    ground. The game draws them with depth written, like the ground. Where its texel × vertex alpha covers ≥ 0.35 with
    something not grass, its 4-unit cells are kept, and no point within a cell of them is drawn.
- **Walls.** Every piece's walls (|n.z| < 0.5) are written into an 8-unit cell grid with their height span. A point
  within one cell of a wall at its height is not drawn.
- **No grass on cut-out cards.** Tree crowns were growing grass at first; alpha-tested draws are now skipped.
- **No grass from the screen before.** The hub's "flat dark grass slabs" near the arch were tufts standing 25..60 units
  in the air. **Ran:** they matched no piece of the hub. They grew on the character choice's own little scene, still drawn
  for a few pictures after the level name had become `hub`. The grass is now forgotten once more when the level has run a
  moment (`g_simFrame` started again and passed 30, or 120 pictures went by).
- **The ground's own painted features** (a flower's petals, a pale stone) are also kept by the ground material: where the
  texel is far brighter than its coarse colour, the material's detail gives way (`er_world.gdshaderinc`).
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

### 4. The rebuild: Elden Ring pieces fitted over the hub's shapes

**What.** Three of the hub's shapes are drawn by Elden Ring ruin pieces:

- the two round stone daises with their three steps and engraved rings: each step is a circular stone platform with a
  flower pattern, scaled to that step's radius and height and turned against the one under it;
- the obelisk's plinth and shaft: a grave obelisk with a stepped base, turned 45° like the game's.
  The game's gem in its cage stays on top.

The game's collision, paths and scripts are untouched: only what is drawn changes.

**Making it (local, `tools/godot/er_world_fit.py RECIPE --pictures DIR`).** The inputs are all local:

- the recipe (`local/er-world/hubfit/hub.json`): the volumes of the shapes and which piece goes where;
- the level's chunks (`world_info.py --obj`);
- the models (`app er world dump FILE`: the scene tap's packets, world space);
- the level's terrain height field (the collision);
- the converted pieces (`flverdump`) and their textures.

The fitting:

- **disc**: the piece's footprint centre to the step's centre, its radius to the step's, its height to the step's span;
- **box**: the piece's own box, turned, onto the shape's box.

**The check (automatic, per target).** It refuses a target that fails; nothing of a refused target is written, and the
game's shape stays.

- The piece's surface is sampled about every 3 units, with every corner.
- A sample is **not seen** when it faces down onto the ground or onto another part of the target, or when it lies
  inside the rebuilt shape itself. The last is found by a ray out along its normal: if the first surface it meets is a
  back face, the sample is inside (the top of the plinth under the obelisk's shaft).
- Every seen sample must lie within **12 units** (a hand's width) of the surface the game draws there. That surface is
  exactly what the drawer leaves out at run time (point-to-triangle distance).
- For the level's own chunks, every seen sample that faces up and lies within reach of the ground (40 units: a floor or a
  step, not an arch's crown) must also lie within 12 units of a terrain collision sample next to it.
- A model's collision is its own circle, so for a model only the surface is checked.

**Ran:**

| Target | Result | Distance to the game's surface | To the collision (up) |
|---|---|---|---|
| west dais (3 steps) | passed | max 1.5, mean 0.3 | max 1.0 |
| east dais (3 steps) | passed | max 1.5, mean 0.3 | max 1.0 |
| obelisk (plinth + shaft) | passed | max 11.8, p99 5.6, mean 1.4 | (a model) |
| arch | **refused** | best max 13.4; 762 of 10,118 seen samples over | max 43 |

The arch: an arch on two columns (the closest of three Elden Ring arches tried) was fitted in two parts, the arch stones
to the ring's crown and the columns to its legs. It comes within 13.4 units. Its column capitals stand out of the game's
legs, so it is refused, and the game's own arch stays. Pictures of every check: `local/er-world/gate2/check-*.png`
(green within, red over).

**Leaving the game's shape out (`RtaDrawer.set_world_hide`, `rta_world.cpp`).** Each volume is
`[cx, cy, cz, hx, hy, hz, yaw, cylinder, kinds]`.

- A level draw (kind 1) all of whose corners lie inside a level volume is not made. This is drawing only; its walls
  still go into the grass's wall grid.
- A model draw (kind 2) whose packets' middle lies inside a model volume loses the triangles that lie wholly inside the
  volumes. They are collapsed to a point; the gem above stays. Such a draw is not curved. Its kept meshes are keyed with
  the volumes' generation.
- Per volume, the drawer notes where in the list its first draw left out stood, and the mean colour of those draws (their
  texture's mean × the game's vertex light): `get_world_hide()`. `app er world rebuild` prints them.

**Drawing (`er_world.gd`, `er_ruin.gdshader`).**

- The pieces are read from `rebuild/<level>/rebuild.json` in the folder when the level is entered with the rebuild on.
  This takes about 210 ms: the worst frame of the layer, once, at the hub's start.
- Each piece is drawn at the place in the list of the draws it stands in for: in the transparent pass, depth tested and
  written, like every world draw. Its shadow comes from an opaque twin drawn only into the shadow maps.
- **Colour.** Each surface's albedo is drawn towards the colour of the shape it replaces: its hue fully (`tint` 1.0), and
  its brightness to the game's. `gain` 1.3 was measured on the hub: the game's own pieces come out about that much
  brighter in their light.
- **Light.** Lit like `remaster_model.gdshader`: the level's ambient given form, the scene's lights, the haze.
- **Haze.** The level's pieces add the sky's and the haze's colours as stored values, before they turn to linear
  (`gs_draw.gdshaderinc`). The piece now does too. Added as linear at first, the far daises came out washed to the haze's
  lavender.
- Measured on the near views: the rebuilt dais is a little greyer than the game's pink-white (115/99/101 against
  125/101/111).

## Gate (Ran)

### Pictures (second session)

In `local/er-world/gate2/`, 1280×720 halves.

- **Hub** (`hub-<place>-<view>-o<orbit>.jpg`): the layer off | on without the rebuild | on, from five places:
  - the start, chase and shoulder;
  - the west dais, from two sides;
  - a close shoulder view at the west dais (0.6 of the camera's distance);
  - the east side, from two sides;
  - a close view at the east dais.

  The player was put at each place by poking its position. The runs are `local/er-world/t2/g4` (route
  `local/er-world/hubroute.py`) and `t2/x3` (the far view after the haze fix).
- **Valor and fire1** (`valor-{chase,shoulder}.jpg`, `fire1-*.jpg`): the layer off | on, after the grass fixes. Run:
  `t2/g2`.
- **Checks**: `check-*.png`, one per target of the fit.

| Where | What was seen |
|---|---|
| hub, near the daises | flagstone steps in place of the pink marble, a dark stone obelisk with its stepped base under the game's gem; colours close to the game's, a little greyer |
| hub, far | the rebuilt daises and obelisk hazed like everything around them |
| hub, by the arch | no tufts in the air any more (the round shrubs and the screen before grew none) |
| valor | the flower patches and the brown patch by the player stay clear of tufts; petals kept by the ground material |
| fire1 | stone, no false wood; as before |
| class pictures (`t2/c2`) | valor's cliffs stone (a first metal rule had made them metal), fire1's lava ground stone (a first wood rule had made it wood), inmine1's beams wood |

### Seams and flicker

- **Seen:** no seam lines and no new shimmer. The rebuilt pieces sit on the game's ground without gaps in any of the
  views.
- **Not judged frame by frame:** flicker. Only stills were taken; no recording was made.

### Frame rate (second session)

Paced, 3024×1964; hub (with the rebuild), valor, arachna1, fire1; chase and shoulder. Files:
`local/er-world/t2/fps-{on,off}/frames.csv`; script: `local/er-world/fps27.sh`.

| | Layer on | Layer off |
|---|---|---|
| Mean fps, stalls over 50 ms left out | **106.3** | 106.3 |
| Median picture gap | 8.95 ms | 8.67 ms |
| 99th percentile gap | 17.6 ms | 17.2 ms |
| hub | 98.3 | 95.5 |
| fire1 (the slowest level, as before) | 66.6 | 68.7 |

The layer's own GDScript time is 41..51 µs a frame (mean). The worst frame, 180..210 ms, is the rebuild's loading when
the hub is entered.

### Room (`local/godot-r27/test/room27.py ew3 --level valor`)

Both copies were Remastered; B ran with `RTA_ER_WORLD=off`. A drew the layer and the rebuild in the hub, and the layer
in valor; B drew none (it did not even load the rebuild). **1,856 ticks compared, no shared column differs.**
An earlier run (`ew2`, before the last shader changes) gave 1,849, also in step.

### First session's gate

Pictures in `local/er-world/gate/`; 106.8 / 107.3 fps; room in step over 1,854 ticks (`local/godot-r25`).

## Fetching the files (local only)

- **Download.** The remembered DepotDownloader login, with the range patch (`RTA_DD_RANGES`, `RTA_DD_ACCOUNT` = the
  stock build's remembered account file). No password was asked. Fetched:
  - the material index (`/material/allmaterial*.matbinbnd`, 5 MB): material names say what each texture is used for;
  - the low-resolution versions of six environment texture groups: 1,379 files. Their chunks are interleaved
    with the full ones, so 1.07 GB was fetched.
  - 15 full packages (9 more chunks).
  - Second session:
    - 26 asset geometry bundles (ruins, platforms, columns, pedestals, obelisks, arches; 28 MB of chunks);
    - the 24 texture packages their materials name (35 MB).

    They were picked by a community list of the assets' names (Smithbox's alias file, read into
    `local/souls-ref/tools/er-assets.json`) and a contact sheet of the converted models (`local/er-world/hubfit/
    ruins_sheet.jpg`). Materials without textures in the model were resolved through the material index.
- **Decompression.** The DCX streams are Oodle Kraken, which the open decoders cannot read. They were decompressed with
  the game's own DLL in the Windows test VM. UTM's `utmctl start` timed out (OSStatus −1712), so the VM was run by
  Homebrew QEMU directly from its UTM disk with `-snapshot` (its disk unchanged): `local/er-world/vm/run.sh`, ssh on
  127.0.0.1:2222. The VM was stopped after.
- **Conversion.** Scripts in `local/er-world/work/`: `undcx.py`, `tpf.py`, `dds2png.py` (sRGB DXGI forms read as plain),
  `make_world.py` (the folder). The models go through `local/souls-ref/tools/flverdump` into `local/er-world/ruins/flv`.

## Next

- The arch: a piece made of parts, each part fitted on its own (the crown, the legs), or a column without a capital. The
  check says how far it is.
- The hub's other shapes: the trefoil platform's stepped rims, the stairs up to the arch, the broken stone rings by the
  arch (a model).
- The same fitting on other levels' landmarks: a recipe per level, a dump of the level (`app er world dump`).
- The rebuild's loading (about 210 ms at the hub's start): read the pieces ahead, or on a worker.
- Metal: try the strict rule on a level that has real metal (the gnome levels).
- The hub rebuild back on only with pieces that beat the game's (Gates 3-5). After gate 5 (gold, light, surroundings done):
  a slimmer, tapered base under the monument in place of the podium box, in the game's colours; the stairs' frieze as light
  as the game's steps; something at play distance on the platforms (a carved border inlaid in the tops along the rims, kept
  to the game's own engraving); an fps run on a quiet machine. Gate 4's list, for the record:
  - the daises: a stepped round piece whose risers stand (the engraved floor's rim is a low band; fitted to a 7-unit step it
    reads flat), drawn with the trefoil platform and the stairs beside it in the same stone, or not at all;
  - the obelisk: one large gold panel per face (the game's focal point) rather than gilt relief; a gold mask made per
    vertex by the fitter (relief faces against the panel's plane) instead of the screen-space bend, which shows the
    relief's facets close up;
  - the pieces' light: they stay brighter than the game's shapes in back light (the ambient fill dominates);
  - a lighter dais mesh (the engraved floor is 92k triangles a step: 552k for both daises) or the meshes made once per
    model and placed, not re-read per piece: the GDScript reader takes 0.8 s alone, 4-8 s on a loaded machine.
- Grass: a second card (small plants).
- Fetch the soil's own normal map.
- Flicker check from a recording.

## Gate 3 (Ran, third session)

**The review.** The second session's rebuild was put beside the game's own shapes (`local/er-world/gate3/v1/hub-*.jpg`:
game | gate 2 rebuild | gate 3 try; `gate3/zoom-*.png`: game | gate 3 try, close). The rule: never a downgrade.

| Target | Tried | Check | Seen | Verdict |
|---|---|---|---|---|
| obelisk | octagonal stepped base `AEG022_029` + grave obelisk `AEG200_009` on the shaft alone (scale 13/13/10, near even, against 25/25/14 before) | passed, max 9.3 (was 11.8) | a slimmer, better-shaped stone obelisk, but plain grey-pink stone and a dark drum where the game has gold panels and a gold-trimmed base | **refused on review** |
| obelisk | the base + column `AEG230_497`, + pedestal `AEG270_194`, + stele `AEG001_101`; the tower `AEG099_070`; the pedestal alone | passed at base inset 2-3 / refused 21-26 | the column, pedestal and tower have no textures fetched: untextured | not used |
| daises | the three discs with the weathered material (below) | passed, max 1.5 | steps read better than gate 2 (worn edges, moss), but still flatter and muddier than the game's pink marble; the carved step edge and the engraved ring of the close view are lost | **refused on review** |

A target refused on review is written in the recipe (`"review": "<why>"`); `er_world_fit.py` then refuses it like a
failed check, and its reason goes into `rebuild.json`. The hub's rebuild now has no pieces (`rebuild for hub, 0 pieces`).

**The ruin material (`er_ruin.gdshader`)**, for any future piece: the texture's carving lifted from its local mean
(`contrast` 1.35), worn light on outer edges and dark in inner corners from the geometry's bend (`edge_wear` 0.45),
grime near the piece's foot (`ground_z`, set by `er_world.gd`), moss in patches on what faces up and in the cracks.

**The haze in the figures.** `remaster_model.gdshader` and `er_armour.gdshader` now turn the haze's colour and the sky's
(stored values) to linear light before adding them, as `er_ruin.gdshader` does. Near figures are unchanged
(`gate3/figures-haze-*.jpg`: r27 | r28).

**The haze check far off (Ran, 2026-10-26).** The same r27 | r28 pair in two hazy levels, with the figures far from the eye:
`local/er-world/haze/hazerun.sh BUILD LEVEL` (power-on, the level asked for, chase view, the camera pulled back 1, 3, 5, 7,
orbit 0 and 180, the Elden Ring armour on and off; pictures `haze/BUILD-LEVEL/`, pairs `haze/zoom-*`, `cmp-*`).
- **fire1** (red haze): in r27 every remastered figure beyond the near ground - the creatures across the level and the
  player itself at pull 3 and more - is drawn white-hot over the haze (near-white pixels in the picture at pull 1 / 3 / 5 / 7:
  1,474 / 567 / 431 / 190); in r28 they take the haze's colour like the level's pieces round them (0 / 0 / 0 / 0). The
  shaman close with the armour on (`armour-fire1-p1-r28.png`: the necromancer outfit over the remastered body) is the same
  in both.
- **swamp1** (a dark, misty night level): r27 draws the far player a pale blue-white; r28 the haze's dark brown; near, the
  same.
No change in the near pictures, so the fix holds; nothing else found.

**Build** `local/godot-r28` (`build.py all`, `run.py import`: exit 0).

**Smoke and room** (`local/godot-r28/test/room28.py g3 --level valor`, both copies Remastered by the portal's card, B
with `RTA_ER_WORLD=off`): portal -> Remastered -> hub -> valor; no script or shader error; A **109.7 fps** mean (median
gap 8.97 ms, p99 17.2 ms; valor part 106.8); **1,857 ticks compared, no shared column differs.**

## Changed

**First session.**

- New (tracked):
  - `tools/godot/extension/src/rta_world.cpp`
  - `tools/godot/project/er_world.gd`
  - `tools/godot/project/er_world.cfg`
  - `tools/godot/project/shaders/er_world.gdshaderinc`
  - `tools/godot/project/shaders/er_grass.gdshader`
  - this file
- Modified (tracked):
  - `tools/godot/extension/src/rta_drawer.{h,cpp}`
  - `tools/godot/extension/src/rta_scene.cpp`
  - `tools/godot/extension/src/rta_variant.h`
  - `tools/godot/project/scene_view.gd`
  - `tools/godot/project/portal/edition.gd`
  - `tools/godot/project/shaders/gs_draw.gdshaderinc`
  - `tools/godot/project/shaders/sky.gdshader`

**Second session.**

- New (tracked):
  - `tools/godot/er_world_fit.py`
  - `tools/godot/project/shaders/er_ruin.gdshader`
- Modified (tracked):
  - `tools/godot/extension/src/rta_world.cpp`: reader, grass, decals, hide volumes, dump
  - `tools/godot/extension/src/rta_drawer.{h,cpp}`: declarations, bindings
  - `tools/godot/extension/src/rta_scene.cpp`: the hooks
  - `tools/godot/project/er_world.gd`: rebuild, commands, second reset
  - `tools/godot/project/er_world.cfg`: `[keep]` header restored, reader and grass keys, density 1.2
  - `tools/godot/project/scene_view.gd`: `er_rebuild`, `er_grass` 1.2
  - `tools/godot/project/shaders/er_world.gdshaderinc`: painted features kept
  - this file

  In the first session's `er_world.cfg` the `[keep]` header had been lost, so its values sat outside any section and the
  shader used 0.6 for every class. They are in force now: grass 0.45, stone 0.85, and so on.

**Local:**
- `local/souls-ref/er-world/` (the materials; `rebuild/hub/`: the fitted pieces, their textures, `rebuild.json` with the
  check)
- `local/er-world/` (scripts, runs, gate, gate2, VM runner, `hubfit/`: recipe, check pictures, loaders; `ruins/`: the
  fetched pieces and textures)
- `local/godot-r25/`, `local/godot-r27/` (builds; `test/room27.py`)
- the partial archives in `local/souls-ref/er/Game/`

**Third session.**

- Modified (tracked):
  - `tools/godot/project/shaders/remaster_model.gdshader`, `er_armour.gdshader`: the haze and sky colours made linear
  - `tools/godot/project/shaders/er_ruin.gdshader`: the weathering
  - `tools/godot/project/er_world.gd`: `ground_z` per piece
  - `tools/godot/er_world_fit.py`: `review`
  - this file
- Local: `local/er-world/gate3/`, `local/er-world/hubfit/hub-gate3.json`, `local/godot-r28/`

## Gate 4 (Ran, fourth session)

**Fetched (local only).** The remembered DepotDownloader login with the range patch (`DOTNET_ROOT` set to the local .NET;
no password asked): 20 more asset geometry bundles (6.7 MB of ranges, 56 MB of chunks) and 106 texture packages (the 11
the gate-3 candidates lacked, then the 95 the new pieces' materials name: 264 MB of chunks). Decompressed in the Windows
VM (QEMU, `-snapshot`; stopped after), converted to `local/er-world/ruins/{flv,dds,png}`. Lists and logs:
`local/er-world/gate4/fetch/`. Textured contact sheets (`gate4/texview.py`, a small numpy rasteriser):
`gate4/final/sheet1.jpg`, `sheet2.jpg`; maps: `texsheet1.jpg`, `texsheet2.jpg`.

**Read from the sheets.** The richer pieces: a tall elaborate brazier pedestal (`aeg022_028`), the inscribed monument
(`aeg099_070`: a flat slab, 1.8 × 1.1, a sculpted crown), an engraved round floor with a carved rim (`aeg210_459`), an
engraved podium with relief panels and two mouldings (`aeg210_460`), a tapered pink-marble monument with figural relief
bands (`aeg237_039`), white spires and columns (`aeg250_141`, `aeg250_526`, `aeg240_550`), a dark carved spire whose
materials carry real metal maps (`aeg230_744`). No piece of the list is gold itself: gold is the material's (the `_m`
maps are metal masks; `_1m` / `_3m` are blend and cavity masks).

**The material (tracked, generic).**

- `er_world_fit.py`: a part's `surfaces` (by the model's mesh number or `*`) give a mesh another albedo or normal, a metal
  or mask map, shader values and its own tint. Pictures written at most 1024² (`MAX_SIDE`).
- `er_ruin.gdshader`: `metallic` (or a metal map's channel and range), `recolour` (the texture's carving laid in another
  colour: marble, gold), `metal_colour` (gold inlaid where a mask says), `gild` (the geometry's raised edges gilt),
  `riser_dark`, `mask_polish`; a metal's light is the sky and the level's light in its own colour, whiter at a grazing
  angle, with a coloured highlight and a broad sheen from the scene's lights (`glint`, `metal_sheen`).
- `er_world.gd`: loads the metal and mask maps, sets the values, and takes a surface's own tint and its laid colour as its
  mean.

**Tried** (recipes `local/er-world/gate4/fit/try1..7.json`; runs `gate4/r1..r7`, route `gate4/run4.sh`, pictures game |
rebuild):

| Target | Pieces and material | Check | Seen | Verdict |
|---|---|---|---|---|
| daises | the engraved round floor, three discs per dais; pink marble laid over its carving, risers darker | passed, max 3.0 | the engraved ring and carved rim read close up, far more carving than the game's; at play distance the three steps read as one patterned slab, busy; it no longer matches the untouched trefoil platform and stairs in the game's stone beside it; in back light it stays bright (dais 105/84/86 against the game's 71/56/73) | **refused on review** |
| obelisk | the engraved podium on the plinth, its two mouldings gold; the relief monument on the shaft, its base and cap gold, its relief gilt | passed, max 10.4 | close up far richer (relief figures, gold mouldings that catch the light); at play distance the game's large gold panel on dark stone reads stronger than gilt lines on pale marble; the gilt relief shows its facets close up; the pale shaft stays bright in back light | **refused on review** |
| arch | not tried (step 3 waits on the hub passing) | - | - | - |

The reasons are in `local/er-world/hubfit/hub-gate4.json` and the live `rebuild/hub/rebuild.json` (0 pieces).

**A fault found and fixed in the recipe.** The obelisk's shaft volume (yaw 0, half 14) left the game's shaft fins drawn:
its lower corners reach 19.3 units out along the axes. Turned 45° with the shaft, every shaft triangle is left out
(Ran: none of them remains; the gem's cage stays). Gate 2's pictures had this fault.

**Frame rate (Ran, machine shared with other agents' runs: the numbers are noisy).** Paced, 3024×1964, hub + valor,
`local/er-world/gate4/fps4.sh`: with the gate-4 pieces **59.5 fps** mean (median gap 11.9 ms, p99 147 ms, 852 stalls over
50 ms); the layer off 69.3 (9.5 ms, 71.5 ms, 261 stalls). Loading the pieces: 0.84 s alone, 4.4 s and 7.9 s on the loaded
machine. Another reason the daises' mesh cannot ship as it is.

**Room (Ran).** `local/godot-r30/test/room30.py g4 --level valor` (port 41993), both copies Remastered, A drawing the
gate-4 pieces (`RTA_ER_WORLD_DIR` = the gate-4 folder), B with `RTA_ER_WORLD=off`: **1,792 ticks compared, no shared
column differs.** Both copies ran about 50 fps there (the machine's load).

**Live state (Ran).** The live folder's rebuild: `rebuild for hub, 0 pieces`; no shader error.

**Fourth session changed:**

- Modified (tracked): `tools/godot/er_world_fit.py` (surfaces, picture size), `tools/godot/project/er_world.gd` (the
  rebuild's materials only), `tools/godot/project/shaders/er_ruin.gdshader` (metal, recolour, gild, riser), this file.
- Local: `local/er-world/gate4/` (fetch lists, fits, runs, `final/` pictures, `fps4.sh`, `run4.sh`, `pair.py`,
  `texview.py`), `local/er-world/ruins/` (the new pieces and textures), `local/er-world/hubfit/hub-gate4.json`,
  `local/godot-r30/`.

## Gate 5 (Ran, fifth session)

The owner's review of gate 4 (`gate4/final/obelisk-chase-o0.jpg`, `west-chase-o0.jpg`): fix the gold and the brightness, and
match the stairs. Recipe `local/er-world/gate5/work/recipe5.py`, fits `gate5/fit/`, runs `gate5/g1..g4`, route
`gate5/route5.py` + `run5.sh` (modes off | game = the layer on, rebuild off | on), pairs `pair5.py` (game | on), luma
`measure5.py`.

**1. Gold (Ran).** The shards came from the old gild: metal where the screen-space bend of the geometry's normal was convex,
which on a relief of a few thousand flat triangles is one value per triangle. Now:

- `er_world_fit.py` makes the mask **per vertex from the mesh** (`relief`: `mode: panels` finds each face's sunk panels from
  the piece's own outer extent per height and facing, eight directions, so a tapering shaft works; `what`: the panels with
  their figures, their frames, or the figures alone; a height band; or the older smoothed-height measure), and bakes a
  cavity (deeper = darker) into the vertex colour. Normals are made smooth across split corners (`smooth_normals`).
- `er_ruin.gdshader` reads it from `COLOR.a`, interpolated across the triangles, through a threshold whose soft edge widens
  with the screen footprint (`fwidth`: far away it averages instead of flickering).
- A metal is a worn, painted gold lit like the stone round it (its brightness the game's light there over the shape's
  mean), with fine streaks along the brushing, the sky in its face blurred across the brushing, and a soft anisotropic GGX
  highlight from the scene's lights (none in its own shadow).

Seen (`final/obelisk-chase-o0.jpg`): the monument's five relief panels are clean, continuous gold with the figures standing
in them, the mouldings gilt; no shard anywhere, near or far.

**2. Brightness (Ran).** Gate 4's pieces had a light model of their own: the colour times the ambient in linear light (more
than twice the level's in shade), a fill and floor light. Now a piece is lit **as the level's pieces are**
(`gs_draw.gdshaderinc`, `GS_LIT` + `GS_NORMALS`): a colour in the game's stored values times the ambient and plus the haze in
stored values before it turns linear, the sun by the same wrap, a face turned from the sun in its own shadow. The colour is
**the game's own, per vertex**: the fitter takes, for every corner, the nearest triangle the game draws there (a normal
that disagrees costs 6 units) and its colour - the texture's mean (`app er world info`) times the game's vertex light from
the dump (`v x y z r g b`) - and carries it in `COLOR.rgb`. For a model the game draws in several passes, a colour is given
and the game's vertex light over the shape (0.3-2x) is kept round it. One gain (1.32, stairs 1.85) was measured: the mean
of a texture comes out darker than the level draws it.

A fault found on the way: a `Color` handed to a `vec3` uniform is made linear by Godot; the loader now passes `Vector3`.

Luma where the rebuild differs from the game (`final/measure.txt`, `on` over `game`, the same pixels):

| Light | Views | game / on |
|---|---|---|
| front (orbit 0) | start, west, east, north | 1.08 - 1.18 (ours a little darker) |
| side (90, 270) | start, west, east, north | 0.91 - 1.23 |
| back (180) | start, west, east, north | 0.90 - 1.05 |
| the obelisk close | 0, 90, 180, 270 | 0.78 / 0.87 / 1.15 / 0.85 (its stone and gold are not the game's dark purple paint) |

Gate 4 in back light: dais 105 against the game's 71 (0.68). In every view now the rebuilt surfaces sit within about 20% of
the game's own, and darken with the level in side and back light (`final/west-chase-o180.jpg`, `obelisk-chase-o270.jpg`).

**3. The surroundings (Ran).** No Elden Ring piece fits a trefoil or a flight of stairs, so these are **the game's own
surface in the set's material** (`fit: surface`): the triangles the game draws in the target, welded, smooth-shaded by
angle; what stands (a riser, a rim) gets a band of the set's carved frieze, run along the riser (unrolled over its faces)
and as tall as it; what lies flat a world-scaled material; a ground tuft drawn in the same piece in the game's colour alone.
Tried both ways:

- **replacing the whole surface** (r1, r2): the engraved rings and painted cracks of the game's tops are lost, the steps
  read flat - worse; dropped.
- **an overlay on the risers** (`overlay`: drawn 0.5 units in front of the game's riser, which stays; no volume left out):
  the trefoil's three rims, both daises' steps and the stairs' risers carry the braid frieze; the tops stay the game's (with
  the layer's material). The check measures them 0.5 units off.

Obelisk: the engraved podium (gilt mouldings) and the relief monument (gilt panels) in a dark lavender stone near the game's.

**Weight and loading (Ran).** `tools/godot/er_mesh_bake.gd` (run by the fitter through Godot, headless): each surface's
tangents, made lighter by meshoptimizer (`ImporterMesh.generate_lods`) until it fits its budget, lower levels of detail under
it, saved as Godot resources; pictures as Images with their mip maps. The loader asks for them on worker threads
(`ResourceLoader.load_threaded_request`); until they are in, the game's own shapes are drawn; the pictures go on the card two
a frame. The whole area: **19,989 triangles** (gate 4's daises alone: 552k). Read in 225-285 ms on the worker threads on a
quiet machine (1.3-2.2 s on the loaded one); on the main thread 13-22 ms (one spike of 163 ms before the pictures were
spread; then 22 + 24 ms over several frames).

**Frame rate (Ran, the machine shared: load average 400-500 during these runs, other agents' Godot copies running).**
Paced, 3024x1964, hub + valor (`gate5/fps5.sh`, `fpsstat.py`): rebuild on 54.5 fps mean (median gap 12.2 ms, p99 50.9 ms);
the layer on without the rebuild 65.1 (11.3 ms, 41.1 ms); the layer off 66.8 (9.1 ms, 43.1 ms). Median draw time 7.8 / 7.5 /
7.3 ms. A hub-only pair came out the wrong way round (rebuild on 49.4, without it 37.5): at this load the means are noise; the
medians say the rebuild costs well under a millisecond. 60+ fps not shown on this machine today; to repeat on a quiet one.

**Room (Ran).** `local/godot-r34/test/room34.py g5 --level valor` (port 41995), both copies Remastered, A drawing the gate-5
pieces (`RTA_ER_WORLD_DIR` = `gate5/world`), B with `RTA_ER_WORLD=off`: **1,858 ticks compared, no shared column differs.** A
read the pieces in the room (`rebuild for hub, 6 pieces (19989 triangles)`).

**Review** (`final/`: game | rebuild; front, side and back light, several orbits, close and play distance):

| Target | Check | Seen | Verdict |
|---|---|---|---|
| obelisk | passed, max 10.4 | close up richer than the game's (gold relief panels, gilt mouldings, clean metal); darkens with the level; at play distance about level with the game's gold panel on dark stone, and its podium is a bulky, bluish box beside the game's tapered gold-trimmed base | **refused on review** |
| trefoil, daises | passed, 0.5 | the rims carry the frieze and match the set and the light; at play distance the platforms read as the game's own | **refused on review** (with the obelisk: the area is not clearly better) |
| stairs | passed, 0.5 | the frieze risers read as darker stripes than the game's pale steps in front light (0.85) | **refused on review** |

The reasons are in `local/er-world/hubfit/hub-gate5.json` and the live `rebuild/hub/rebuild.json` (0 pieces). The gate-5
pieces stay in `local/er-world/gate5/world/` (`RTA_ER_WORLD_DIR` to see them).

**Fifth session changed:**

- New (tracked): `tools/godot/er_mesh_bake.gd`.
- Modified (tracked): `tools/godot/er_world_fit.py` (dump colours, several dumps, texture means, the game's colour per
  vertex, `fit: surface`, overlays, relief masks, smooth normals, the v2 mesh and the bake), `tools/godot/project/er_world.gd`
  (the rebuild loader only: worker threads, baked meshes, `Vector3` values, no tint over the game's colour),
  `tools/godot/project/shaders/er_ruin.gdshader` (rewritten: the level's light, the game's colour, the gold), this file.
- Local: `local/er-world/gate5/` (dumps `d1/`, fits, runs, `final/`, fps, `world/`), `local/er-world/hubfit/hub-gate5.json`,
  `local/godot-r34/` (build, `test/room34.py`).
