# The Elden Ring WORLD layer (Godot, Remastered mode, owner-local)

Started 2026-10-25. The owner wants the levels to *look* like Elden Ring while the game stays Champions. The collision,
paths and scripts are the game's; only what is seen changes. The Elden Ring files are the owner's own copy, converted on
his machine into `local/souls-ref/er-world/`. They are never tracked, never uploaded, never shared. Without that folder
nothing changes.

Everything below says **Ran** (with what was seen) or **Read**.

## STATE (2026-10-26, seventh session: gate 7)

Phase 1 steps 1-3 are **working, Ran**. Step 4, the hub's rebuild: gate 7 fixed what gate 6 was refused for. **Floating
overlays are fixed**: an overlay is cut by the game packet it lies on and drawn only on the frames the game drew that
packet (a new watch-only volume kind in `rta_world.cpp`). Pixels drawn over the game's sky across the 26 shots went from
26,082 (gate 6) to 4,946, and what is left is silhouette edges. The daises now have crisp steps, and the carving and gold
read at play distance. The gate **refused it on review again** (Gate 7):
- the daises' shape contrast is level with the game's or better, but their tops are still not as pale (on/game 0.89-0.93);
- the trefoil, the stairs and the obelisk are richer, but at play distance they are level with the game, not clearly
  better.

The hub draws the game's own shapes.

| Step | State |
|---|---|
| 1. Materials by class, ER albedo + normal, world scale, triplanar, blended | **done, Ran**: 8 classes; reader + our own table (`er_world.cfg`); wood now read on its own (a mine's beams), metal only by a strict rule (none read on the four levels tried) |
| 2. Grass (MultiMesh, swaying, density by distance, no collision, not on paths / against walls) | **done, Ran**: clears painted flower patches and stones; no tufts in the air; valor 3,509 points |
| 3. Skies: ER cloud layer tinted by the level's own sky | **done, Ran** |
| 4. Hub fitted rebuild (ruin pieces fitted to the Champions shapes, a hand's-width check) | **refused on review** (gate 7, see Gate 7; gates 3-6 before it); arch **refused** by the check (max 13.4 units off), not retried |
| Gate: before/after pictures, 60+ fps, room in step | **Ran**: pictures in `local/er-world/gate7/final/`; 60+ fps with the rebuild on (median frame 8.88 ms on, 8.94 ms off, same load); room in step (1,852 ticks, A drawing the gate-7 pieces) |

Built into `local/godot-r36/` (extension and project). Not committed.

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
- **Watch-only volumes (gate 7)**: a volume with `kinds & 4` never leaves anything out. `RtaDrawer::world_watch`
  (`rta_world.cpp`) marks it drawn on every frame the game draws a level packet whose figure it names in `[9]` (or, when
  it names none, a packet whose box middle lies inside it). `get_world_hide()[v][4]` says whether it was drawn this frame.
  An overlay piece has `"watch": [volume]`, and `er_world.gd` shows it only on those frames. The fitter cuts each overlay
  by the game packet each triangle lies on, taking the packets' figures (`m<hex>` in the dump) from the dumps.
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
- The hub rebuild back on only with pieces that beat the game's (Gates 3-7). After gate 7:
  - the daises: the tops as pale as the game's (on/game 0.89-0.93 now). The crisp step edges are done (shape contrast
    level or better).
  - trefoil and stairs: something the game lacks that reads at play distance. The game's lit ring lips and plain pale
    steps hold up against our braid; for example a lit lip on the inlay's outer gold line.
  - the obelisk: the shaft is slimmer than the game's (side light 1.12-1.26 where the cloud wall shows past it). Fit the
    shaft's flare before the materials.
  - the pieces' light follows the sun more than the game's does. In side light a riser facing the sun is brighter, in
    front light darker. The direct gains trade one against the other (see Gate 7).
- Gate 6's asks (done in gate 7): overlays only where the game draws (watch-only volumes, cut per packet); crisp dais
  steps.
- Gate 5's asks (done in gate 6): the tapered base, the stairs' frieze as light as the game's steps, something at play
  distance on the platforms, an fps run on a quiet machine. Gate 4's list, for the record:
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

## Sweep of all 111 levels (2026-10-26, fourth session, second agent)

Phase 1 had been tuned on hub, valor, arachna1, fire1 and inmine1 only. Every level of the game was now walked in
Remastered with the layer, its faults found (automatically where possible), fixed generically or by a level's own section
in `er_world.cfg`, and walked again. **Ran**, `local/godot-r32/` (built from the working tree; the game library from r28's
snapshot).

### How (local, `local/er-world/sweep/`)

- `walk.py TAG` drives Godot's scene mode through the levels (the `presets.py walk` pattern: power-on, each level asked for
  by name, the opening scene tapped away), at most 3 programs, 4 levels a program, a program that hangs killed (two levels
  hold the game with a message box: innovat1, watbonus at first). `route.py` is the rig script.
- At three stops per level - **a** the chase view standing (300 ticks in), **c** after a walk and a turn, **f** first
  person - pictures with the layer **on**, then **off** 12 frames later (the first frames after the layer is switched draw
  without some pieces while their materials are made: an earlier walk "saw" valor's flagstone floor through its grass
  carpets that way), and at a and c the **class colours** (`er_world_strength -1`), `app er world info`, every grass
  point near the eye and the frame's packets (`app er world dump`).
- `sheet.py` (a sheet per level: off / on / classes x a, c, f), `index.py` (5 levels an image), `check.py`, `table.py`.
- Walks: `v0` (the layer as phase 1 left it), `v1`..`v3` (fixes on the way), **`v4` (final)**. Sheets:
  `local/er-world/sweep/v4/sheets/LEVEL.jpg`; overview `v4/index-NN.jpg`.

### The automatic checks (`check.py`)

Each grass point near the eye against the frame's packets and the classes read:

| Check | What | Final walk |
|---|---|---|
| air | no surface under the point within 3 units, though the level is drawn round it | small counts left; looked at on valor: every one has no packet under it at all in that frame, or only one 80-120 units over it (the game had not drawn the ground there in that frame) - not tufts in the air |
| offclass | the surface it stands on is of no grass class | 0, but islsm2b's a stop (a boss scene's fade: the picture is black) |
| covered | a surface of another class lies 0.5..14 units over it (a path laid on the grass) | 0 |
| water | a see-through sheet (blended, no depth) lies 3..400 units over it | 0 |
| wall | a steep face within 6 units at its height | under 20 on a few levels (the checker's 6 units is finer than the drawer's 8-unit cells: tufts at the foot of a rock, not in it) |
| steep | it stands on a face steeper than 37 degrees | 0 |

Per texture: colours that look like water, lava, ice or snow and what they were read as. Per stop: the lower two thirds'
brightness on / off and colour shift, and the sky's difference (the cloud layer).

### Faults found, and the fixes

**Generic (code):**

1. **Tufts leaning over paths and flagstones** (seen on valor at first; part of what was seen there was the switching
   artifact above and fault 2, but the cause below is real everywhere): a tuft is 0.8 of its height wide (up to 35 units out from its
   foot), and only 10 units round its foot were looked at. Now a point keeps its **room** - how far the nearest thing that
   is not grass lies: rings of 4..34 units in its own texture (a painted flagstone, a path, petals), and the level's other
   surfaces that are not grass at or over its height, or a little under it where no grass covers them (the edge of a grass
   carpet over a stone floor). The tuft is made no wider than its room (`er_world.gd`); under `[grass] clear` (10) none.
2. **Tufts where the game no longer draws the ground** (valor's grass carpets are left out and brought back by the game):
   each tuft keeps its piece, and a piece not drawn for 90 frames grows none; when it is drawn again the grass is
   gathered at once (`get_grass_epoch`).
3. **No grass under water**: a see-through sheet of the level (blended, no depth written: a lake's, a river's surface), or a
   piece read as water, lava or ice, is noted in cells; a point 3..600 units under one is not drawn.
4. **Water, lava, ice: new classes** 9, 10, 11 (`rta_world.cpp`, `er_world.gdshaderinc`, `er_world.gd`), with their own
   materials in the local folder (`local/er-world/work/make_world2.py`: water a neutral albedo with a ripple normal, lava
   the glow map's brightness with its normal, ice a cracked-ice albedo and normal; low-resolution versions). Their scale /
   keep / amount are defaults in `er_world.gd` (`CLASS_DEFAULTS`: they keep most of the game's own picture). None of them
   grows grass; ice that is rough is snow.
   - **Read only where a level's section says so** (`lava = 1`, `water = 1`). Measured on the sweep: read from colour
     alone, water was found on 30 levels and lava on 2 that have none in their solid pieces (a blue night light, a blue
     painted stone, a pale marble; a lamp-lit red wall). The game's lakes and lava seas are not solid level pieces the
     layer draws (fire3, fire4: the lava stays exactly as the game draws it, and grows nothing); the solid ones that are
     water or snow by colour are named per level.
   - Lava is read from the texel itself (it glows whatever the light): a saturated red to orange whose glowing texels
     (bright orange to yellow) are a quarter of it; on a texture page with a flow in a corner it is the second class,
     decided per pixel.
5. **Grass's band of hues** ends at 160 degrees (was 170 with a soft edge to 186): cyan is not grass.
6. **A texture that reads as no family under its light** (a deep coloured light) is read by its texels alone.
7. **Underwater and see-through skies**: a level's section may name `sky_amount`; a level's section may turn the layer off
   (`layer = "off"`, none needed).

**Per level (`er_world.cfg`, a section each, the reason written above its keys):** 65 levels. The reader's mistakes were
of a few kinds, the same on every level where they occur, and none can be told from the texture alone (measured: wood's
edge ratio and coherence overlap fully between beams, bricks and cave rock; snow and dull grass have the same hue and
saturation; the game's textures are stored at about half their drawn brightness, so "pale" cannot be read):

- **boards (wood) on rock, bricks and tiles** - caves, dungeons, the torment levels' stone floors: `remap_wood`;
- **grass on snow, cave floors, paving, volcanic rock, wooden walkways** - `remap_grass` (snow, stone, dirt, cobble, wood);
- **earth (dirt) on volcanic rock, bricks, tiled floors, beach sand** - `remap_dirt` (stone, cobble, sand);
- **cobbles on tree trunks**, **metal on a stone pillar**, **snow and sand on a marble dais**;
- **clouds under water** (compwat, watbonus, wat1, watg2a/b/c) and **through a see-through dome layer** (airarena, half).

### Sky

- **Clouds under a dome**: on the dome levels (airarena, the torment levels, citadel, pvptor, endgood, intro, ...) the game
  draws its dome over the cloud layer, so the clouds show only above its upper edge - except where a dome layer is itself
  see-through: airarena's painted shafts of light (clouds at 0.45 there).
- **Colour against the level's preset**: the clouds take the level's own sky colours (fire levels: red-orange clouds,
  night levels: dark). Lower two thirds' brightness on / off: within 0.88..1.15 on every judged stop but valor's a stop
  (0.81: the dense grass is darker than the game's flat green; as tuned in phase 1).

### Frame rate

Paced, 3024x1964, the layer on and off in one program per level (`fps.py`, `fpsroute.py`: 300 ticks of walking and
turning in the chase view and first person, each half), 16 heavy levels (most draws, most grass, phase 1's slowest).

**The machine was not free**: other agents' Godot programs ran all the while (load average 60 at the first try, 300-420
at the second). Under that, every level ran at 21-76 fps **with the layer and without it alike** (mean of the 15 measured:
on 32.0, off 34.6 fps; within the noise of the load, in either direction). The layer's own time (GDScript) was 55-150 us
a frame. The 60+ fps check could **not** be made on this machine now; phase 1's gate (a free machine) had 106 fps with the
layer on and off. To do: `local/er-world/sweep/fps.py OUT LEVELS` when no other program runs.

| Level | fps on | fps off |
|---|---|---|
| watbonus | 34.3 | 26.4 |
| watg2b | 32.9 | 34.7 |
| watg2a | 32.3 | 39.0 |
| watmedal | 46.8 | 38.0 |
| torment2 | 28.5 | 42.9 |
| pvptor | 76.0 | 76.4 |
| torment3 | 30.4 | 38.4 |
| torbonus | 28.5 | 26.4 |
| valor | - | 30.9 |
| stomedal | 28.5 | 31.4 |
| islsm3a | 27.1 | 29.7 |
| honor2 | 21.3 | 26.7 |
| swamp1 | 30.8 | 31.3 |
| fire1 | 28.9 | 28.4 |
| stobonus | 24.9 | 26.0 |
| nitmedal | 34.3 | 38.0 |

### Per level (final walk v4)

Result: **fixed** (a section of its own in `er_world.cfg`, or a generic fault it showed), **ok** (nothing wrong seen), or
**off** (none). "Checks" counts the grass checks' findings at a and c (see above: `air` and `wall` are the checker's own
noise). "Bright" is the lower two thirds' brightness, layer on / off, at stop a.

| Level | Result | Classes read (a) | Grass points (a) | Checks (a, c) | Bright on/off (a) | Why / what |
|---|---|---|---|---|---|---|
| airarena | fixed | stone 96, dirt 2 | 0 | - | 0.99 | a floating rock with a marble dais: the dais is not snow or sand, the rock not grass (`sky_amount = 0.45, remap_snow = stone, remap_sand = stone, remap_grass = stone`) |
| arachna1 | fixed | stone 4, dirt 3, cobble 1 | 0 | - | 0.979 | a cave: its rock reads as boards (warm, edged one way) (`remap_wood = stone`) |
| bastion1 | fixed | snow 35 | 0 | - | 0.998 | a snowfield under a deep blue night light: its texels are blue themselves - they read as water, which is snow here (`water = 1, remap_water = snow`) |
| blomedal | fixed | stone 70, dirt 44 | 0 | - | 0.973 | a cave arena: cracked rock floor reads as boards (`remap_wood = stone`) |
| blood1 | fixed | dirt 15, stone 4 | 0 | - | 0.97 | rocky ground reads as boards (`remap_wood = stone`) |
| boar1 | fixed | dirt 52, stone 14 | 0 | - | 0.973 | a cave: its rock reads as boards (`remap_wood = stone`) |
| bossevil | ok | dirt 28, stone 22, wood 6 | 0 | - | 1.004 | - |
| bossgood | ok | grass 27, stone 8, dirt 7, wood 1 | 183 | air 2, wall 33 | 1.008 | - |
| citadel | fixed | cobble 13, stone 10 | 0 | - | 0.97 | stone floors and arches under a red-gold light read as boards and earth (as the torment levels) (`remap_wood = stone, remap_dirt = cobble`) |
| compblo | fixed | stone 35, dirt 13, grass 1 | 0 | - | 0.978 | rock reads as boards (`remap_wood = stone`) |
| compdis | ok | dirt 74, wood 28, stone 4, grass 1 | 0 | - | 0.979 | - |
| compsto | ok | - | - | - | 1.101 | - |
| compval | ok | stone 43, dirt 8, grass 4, wood 4 | 71 | air 4 | 0.984 | - |
| compwat | fixed | cobble 31, stone 8, grass 5, wood 1 | 0 | - | 0.993 | under water: no clouds; a pale sea-floor texture reads as ice (`sky_amount = 0.0, remap_ice = stone`) |
| dis2 | ok | dirt 33, grass 2, wood 1 | 0 | - | 0.993 | - |
| disbonus | ok | dirt 66, grass 37, stone 16, cobble 2, wood 2 | 0 | - | 0.996 | - |
| dismedal | fixed | dirt 117 | 0 | - | 0.944 | red, fleshy walls read as boards (`remap_wood = dirt`) |
| drunare | fixed | stone 29, cobble 1, dirt 1 | 0 | - | 0.986 | brick walls (courses of mortar run one way) read as boards (`remap_wood = cobble`) |
| drunarm | fixed | dirt 23, stone 8 | 0 | - | 0.958 | a dwarven cave: rock reads as boards (`remap_wood = stone`) |
| drundar | fixed | dirt 109, stone 10 | 1 | - | 0.97 | a dwarven cave: rock reads as boards (`remap_wood = stone`) |
| endbad | ok | stone 7, grass 5, dirt 1 | 3 | - | 1.035 | - |
| endgood | fixed | stone 32, grass 30, wood 7 | 137 | - | 0.993 | a stone pillar reads as metal (`remap_metal = stone`) |
| fay1 | fixed | dirt 28, stone 13, wood 1 | 0 | - | 0.968 | a cave of roots and mud: its ground reads as grass under the green light (`remap_grass = dirt`) |
| fay2 | fixed | wood 15, stone 4, dirt 1 | 0 | - | 1.001 | wooden walkways read as grass under the green light (`remap_grass = wood`) |
| fay3 | ok | grass 68, stone 33, dirt 7, wood 3 | 353 | air 2, wall 4 | 0.917 | - |
| faybonus | fixed | dirt 28, stone 26, grass 25 | 0 | - | 0.96 | a cave: its rock reads as boards (`remap_wood = stone`) |
| fearboss | ok | stone 13, grass 12 | 124 | air 3 | 0.878 | - |
| firbonus | fixed | stone 24 | 0 | - | 0.996 | it has lava: read it (a glowing red to orange) (`lava = 1, remap_dirt = stone`) |
| fire1 | fixed | stone 50, grass 11 | 4 | wall 2 | 0.988 | it has lava: read it (a glowing red to orange) (`lava = 1, remap_dirt = stone`) |
| fire2 | fixed | stone 55, wood 4 | 0 | - | 0.997 | it has lava: read it (a glowing red to orange) (`lava = 1, remap_dirt = stone`) |
| fire3 | fixed | stone 20, wood 4, grass 2 | 0 | - | 1.046 | its lava pools are not level pieces the layer draws (as the game draws them; no grass); it has lava: read it (a glowing red to orange) (`lava = 1, remap_dirt = stone`) |
| fire4 | fixed | stone 3, wood 1 | 0 | - | 0.992 | its lava sea is not a level piece the layer draws (as the game draws it; no grass); a flow at c reads as lava; it has lava: read it (a glowing red to orange) (`lava = 1, remap_dirt = stone`) |
| fire5 | ok | stone 118, grass 1 | 0 | - | 1.002 | a boss scene; stop f black; it has lava: read it (a glowing red to orange) (`lava = 1, remap_dirt = stone, remap_wood = stone`) |
| firmedal | fixed | stone 30 | 0 | - | 1.002 | it has lava: read it (a glowing red to orange) (`lava = 1, remap_dirt = stone`) |
| honor | fixed | stone 89, cobble 11, dirt 1 | 0 | - | 0.986 | a paved temple: mossy flagstones read as grass (tufts on the paving) (`remap_grass = cobble`) |
| honor2 | ok | grass 64, stone 52, dirt 31, wood 5 | 435 | air 3 | 0.94 | - |
| hub | ok | stone 111, grass 33 | 35 | air 1, wall 2 | 0.986 | not changed here (its section is the rebuild's); walked |
| hub2 | fixed | stone 41, cobble 15 | 0 | - | 1.008 | a paved grotto: its floor reads as earth and boards, its walls as grass (`remap_dirt = cobble, remap_wood = stone, remap_grass = stone`) |
| inmine1 | ok | grass 133, cobble 14, wood 14, stone 6, dirt 2 | 378 | air 9, wall 21 | 0.981 | - |
| inmine2 | ok | grass 22, stone 16, cobble 9, wood 2, dirt 1 | 65 | air 2, wall 18 | 0.891 | - |
| innmedal | ok | dirt 41, stone 10, wood 6, cobble 3, grass 3 | 23 | wall 2 | 0.969 | - |
| innovat1 | ok | dirt 56, stone 19, wood 14, grass 6, cobble 5 | 47 | wall 2 | 0.979 | - |
| innovat2 | ok | stone 26, dirt 23, wood 11, cobble 1 | 14 | wall 4 | 0.96 | - |
| innpit | ok | stone 33, dirt 16, wood 8, cobble 4 | 0 | - | 0.992 | - |
| intro | ok | grass 23, wood 2 | 15 | wall 24 | 1.002 | - |
| islc1 | ok | grass 35, stone 19, dirt 12, cobble 2 | 29 | wall 2 | 0.898 | - |
| islc2 | ok | grass 36, stone 14, cobble 1, dirt 1 | 67 | wall 1 | 0.98 | - |
| islcave1 | ok | stone 13, grass 12 | 124 | air 1 | 0.882 | - |
| islgnome | ok | grass 55, wood 9, dirt 6, sand 6 | 324 | air 2, wall 2 | 0.978 | - |
| islgoth | fixed | stone 29, cobble 17 | 0 | - | 0.973 | a gothic hall: tiled floor reads as earth, stone walls as boards and grass (`remap_dirt = cobble, remap_wood = stone, remap_grass = stone`) |
| islsm1 | ok | grass 34, stone 17, dirt 13, wood 1 | 183 | air 4 | 0.0 | stop a fading in (on darker than off by the fade) |
| islsm2a | ok | grass 23, dirt 2, wood 1 | 174 | wall 1 | 0.986 | - |
| islsm2b | fixed | - | 52 | offclass 44 | 10.776 | stop a is a boss scene's fade (black; its offclass count is from that frame); a beach: its sand reads as earth (`remap_dirt = sand`) |
| islsm3a | fixed | grass 84, sand 49, stone 24, wood 2 | 717 | air 13, offclass 2, wall 2 | 0.986 | a sandy path reads as earth (`remap_dirt = sand`) |
| islsm3b | ok | grass 57, stone 19, cobble 2, dirt 1 | 109 | wall 2 | 0.96 | - |
| nit1 | fixed | stone 23 | 0 | - | 0.991 | a cave: its floor reads as grass, its walls as cobbles (`remap_grass = stone, remap_cobble = stone`) |
| nit2 | fixed | stone 84, grass 9, dirt 3, wood 3 | 6 | air 1 | 0.979 | tree trunks and rock read as cobbles (`remap_cobble = stone`) |
| nitbon2 | fixed | dirt 39, stone 34 | 0 | - | 0.986 | a cave: a mossy patch reads as grass (`remap_grass = dirt`) |
| nitbonus | fixed | grass 16, stone 11, dirt 3, wood 1 | 49 | air 4 | 0.97 | tree trunks and rock read as cobbles (`remap_cobble = stone`) |
| nitdung1 | fixed | cobble 11, stone 1 | 0 | - | 0.978 | a dungeon: its bricks read as earth and boards (`remap_dirt = cobble, remap_wood = cobble`) |
| nitdung2 | fixed | cobble 11 | 0 | - | 0.976 | a dungeon: its bricks read as earth and boards (`remap_dirt = cobble, remap_wood = cobble`) |
| nitdung3 | ok | dirt 72, stone 26, wood 8, cobble 6 | 0 | - | 0.998 | - |
| nitdung4 | fixed | cobble 7, stone 1 | 0 | - | 0.989 | a dungeon: its bricks read as earth and boards (`remap_dirt = cobble, remap_wood = cobble`) |
| nitmar1 | ok | dirt 25, cobble 5, wood 4 | 0 | - | 0.95 | - |
| nitmedal | ok | dirt 35, grass 8, wood 2 | 650 | air 10, offclass 3, steep 1 | 0.97 | - |
| obsfor1 | ok | stone 13, grass 12 | 124 | air 1 | 0.902 | - |
| obsidian | fixed | stone 138 | 0 | - | 0.982 | volcanic swirls read as grass (tufts on the rock) and earth (`remap_grass = stone, remap_dirt = stone`) |
| pvparena | ok | stone 69, dirt 25, wood 20, grass 2 | 0 | - | 0.979 | - |
| pvpbas | fixed | snow 81, dirt 1, stone 1 | 0 | - | 0.993 | icy mountains read as grass under the blue light; its blue snowfield as water (as bastion1) (`remap_grass = snow, water = 1, remap_water = snow`) |
| pvpblo | ok | - | 0 | - | 1.0 | - |
| pvpblo2 | ok | - | 0 | - | 1.0 | - |
| pvpfire | ok | - | 0 | - | 1.0 | - |
| pvpfire2 | fixed | stone 26 | 0 | - | 0.995 | it has lava: read it (a glowing red to orange) (`lava = 1, remap_dirt = stone`) |
| pvpinn | ok | dirt 72, stone 27, wood 23, cobble 8, grass 3 | 0 | - | 0.967 | - |
| pvpnit | fixed | stone 84, dirt 14, wood 12, grass 8 | 16 | - | 1.006 | tree trunks and rock read as cobbles (`remap_cobble = stone`) |
| pvptor | fixed | cobble 91, stone 54 | 0 | - | 0.992 | a stone arena under a red light: its floor reads as boards (`remap_wood = stone, remap_dirt = cobble`) |
| pvpval | ok | stone 35, grass 8, wood 7, dirt 3 | 80 | air 2, wall 1 | 0.987 | - |
| shame1 | fixed | cobble 11, stone 1 | 0 | - | 0.988 | a dungeon: its bricks read as earth and boards (`remap_dirt = cobble, remap_wood = cobble`) |
| stobonus | fixed | snow 129 | 0 | - | 1.014 | a snowy forest: its snow reads as grass (a grey green; tufts stood on the snow) (`remap_grass = snow`) |
| stomedal | ok | grass 92 | 1002 | air 12, wall 16 | 0.954 | - |
| storm1 | fixed | snow 58 | 0 | - | 1.461 | a boss scene, stop c black (a fade); its brightness on / off differs by the fade, not the layer; a snowy forest: its snow reads as grass (a grey green; tufts stood on the snow) (`remap_grass = snow`) |
| storm1a | fixed | stone 58, dirt 28, cobble 1, grass 1, sand 1 | 0 | - | 0.99 | a dungeon: stone walls read as boards (`remap_wood = stone`) |
| storm1b | fixed | stone 13, dirt 7, cobble 3 | 0 | - | 0.981 | a dungeon: a mossy floor reads as grass, walls as boards (`remap_grass = stone, remap_wood = stone`) |
| storm1c | fixed | stone 56, dirt 15 | 0 | - | 0.963 | a dungeon: stone walls read as boards (`remap_wood = stone`) |
| storm2 | fixed | stone 63, dirt 4, wood 1 | 0 | - | 0.968 | dark, icy rock reads as grass (`remap_grass = stone`) |
| storm3 | fixed | snow 36, stone 33, dirt 10 | 0 | - | 1.007 | ice on its icy walls (c); a snowfield reads as grass under the blue light (`remap_grass = snow`) |
| storm4 | fixed | snow 18, ice 3, dirt 1 | 0 | - | 0.872 | a snowfield: reads as grass under the blue light (`remap_grass = snow`) |
| storm5 | ok | ice 59, dirt 1 | 0 | - | 0.997 | its frozen ground reads as ice (cracked-ice material) |
| strife | ok | stone 60, dirt 25, wood 9 | 0 | - | 0.976 | - |
| swamp1 | ok | grass 99, wood 32, dirt 24, stone 2 | 667 | air 5, wall 4 | 0.975 | - |
| swamp2 | fixed | dirt 126, stone 16 | 0 | - | 0.969 | red ground reads as boards (`remap_wood = dirt`) |
| torbonus | fixed | stone 82, cobble 51 | 0 | - | 0.987 | stone floors and arches under a red-gold light read as boards and earth (`remap_wood = stone, remap_dirt = cobble`) |
| tormedal | fixed | stone 45, cobble 9 | 0 | - | 0.99 | stone floors and arches under a red-gold light read as boards and earth (`remap_wood = stone, remap_dirt = cobble`) |
| torment0 | fixed | stone 45 | 0 | - | 0.991 | stone platforms under a red light read as boards and earth (`remap_wood = stone, remap_dirt = stone`) |
| torment2 | fixed | stone 84, cobble 44, grass 2 | 0 | - | 0.984 | stone floors and arches under a red-gold light read as boards and earth (`remap_wood = stone, remap_dirt = cobble`) |
| torment3 | fixed | stone 86, cobble 79, grass 1 | 0 | - | 0.982 | stone floors and arches under a red-gold light read as boards and earth (`remap_wood = stone, remap_dirt = cobble`) |
| tormenta | fixed | stone 20 | 0 | - | 0.988 | stone platforms under a red light read as boards and earth (`remap_wood = stone, remap_dirt = stone`) |
| tormentb | fixed | stone 32, wood 6 | 0 | - | 0.923 | stone towers under a red light read as earth (`remap_dirt = stone`) |
| valmedal | fixed | stone 23, cobble 21, dirt 13 | 0 | - | 0.985 | a paved arena: mossy paving reads as grass (tufts on the paving) (`remap_grass = cobble`) |
| valor | fixed | grass 38, stone 26, wood 5 | 429 | - | 0.875 | tufts that leaned over its flagstone floor, and stood where the game had left its grass carpets out (generic 1, 2); denser, darker grass than the game's flat green (0.87) |
| valor2 | ok | grass 68, stone 49, wood 2, dirt 1 | 718 | air 13, offclass 1, wall 1 | 0.891 | - |
| wat1 | fixed | - | 0 | - | 0.0 | stop a black (dark start); under water: no clouds; a pale sea-floor texture reads as ice (`sky_amount = 0.0, remap_ice = stone`) |
| watbonus | fixed | stone 51, grass 5, cobble 1 | 0 | - | 0.997 | under water: no clouds; a pale sea-floor texture reads as ice (`sky_amount = 0.0, remap_ice = stone`) |
| wate2a | fixed | cobble 45, stone 18, dirt 1 | 0 | - | 0.978 | a sewer: its wet floor reads as grass (`remap_grass = cobble`) |
| wate2b | fixed | cobble 102, stone 29 | 0 | - | 0.969 | a sewer: its wet floor reads as grass (`remap_grass = cobble`) |
| wate2c | fixed | cobble 27, stone 16 | 0 | - | 0.982 | stop f black; a sewer: its wet floor reads as grass (`remap_grass = cobble`) |
| water1 | ok | stone 9, grass 8 | 94 | air 1 | 0.891 | - |
| watg2a | fixed | stone 10, grass 4, dirt 1 | 0 | - | 0.999 | under water: no clouds (`sky_amount = 0.0`) |
| watg2b | fixed | stone 3, dirt 1 | 0 | - | 1.002 | under water: no clouds (`sky_amount = 0.0`) |
| watg2c | fixed | stone 7, dirt 1 | 0 | - | 1.004 | under water: no clouds (`sky_amount = 0.0`) |
| watmedal | ok | stone 4, dirt 1 | 0 | - | 0.99 | - |

### Not judged / known

- Stops with a black or fading picture (a message box, a scene's fade): see the table's notes; every level has at least
  two stops judged.
- Seams: none seen on the class pictures and the on pictures at play distance; no recording was made (flicker not judged).
- The hub's section is the other agent's (its rebuild); the hub was walked and reads as before.
- The water / lava / ice materials are the low-resolution versions of the owner's files.

### Changed (this sweep)

- `tools/godot/extension/src/rta_world.cpp`: classes 9-11, lava from the texel, water / lava read per level, the reading
  without the light, room, ground / cover / sheet cells, pieces present, `lava_member`
- `tools/godot/extension/src/rta_drawer.{h,cpp}`: their state, `get_grass_epoch`
- `tools/godot/project/er_world.gd`: 11 classes, a third vector of per-class values, room, epoch, `layer`, `sky_amount`,
  `lava` / `water` keys, `info` writes tint / hot
- `tools/godot/project/shaders/er_world.gdshaderinc`: classes 9-11, `er_lava`
- `tools/godot/project/er_world.cfg`: 66 new level sections, `lava = 1` in fire1's (none of hub's)
- this file
- Local: `local/er-world/sweep/` (scripts, walks v0-v4, fps), `local/er-world/work/make_world2.py`, the three materials in
  `local/souls-ref/er-world/materials/{water,lava,ice}`, `local/godot-r32/`

## Gate 6 (Ran, sixth session)

The owner's review of gate 5: a slimmer, tapered base under the monument instead of the bulky, bluish podium box (gold
trimmed like the game's, but richer); stair friezes as light as the game's pale steps (gate 5: 0.85); something visible at
play distance on the trefoil's and the daises' tops that keeps the game's engraved rings. Recipe
`local/er-world/gate6/recipe6.py`, fits `gate6/fit/`, route `gate5/route5.py` + `gate6/run6.sh` (game | on), stops
`gate6/stops.txt` (gate 5's), region luma `gate6/regions.py`, tries `gate6/t1..t6`, final run `gate6/g1`.

**1. The podium (`er_world_fit.py` `fit: loft`, Ran).** A turned square base made from a profile: rings `[z, half]` bottom to
top, each span in a material the part names (`gold`, `stone`, `frieze`: a band of the set's carved braid run up the span),
hard corners, a cap. The profile is the game's own, read from its triangles in the 45-degree frame (half 26.2 at the foot,
25.4, 20.6, 18.2, 13.6, 13.3 under the shaft), with a gold foot from the dais top up, a gold bead, a stone slope, the taper in
the braid, a gold moulding and the stepped top in stone. 92 triangles. Its colour is the game's mean (grey-lavender, no
texture hue), gain 0.85 with the scene's light 1.35 (`direct_gain`, below). The check: max 10.4 (the monument above it), p99
2.8; for the loft, a sample is "inside" by the profile itself, not its box.

**2. The stair friezes (Ran).** `er_ruin.gdshader` `direct_gain`: the scene's lights alone made stronger, so a frieze is as
pale as the game's step in front light without lifting it in shade (raising `gain` alone did both: side light went to 0.72).
Stairs: gain 1.85, direct 2.4, contrast 1.2. Luma on/game where the rebuild differs, on the stairs' box: **0.97** (start
chase) and **0.96** (start shoulder); gate 5's pictures on the same boxes 0.74 / 0.73 (the 0.85 of gate 5 was taken over a
larger area).

**3. The platform tops (`inlay`, Ran).** On a surface part, bands laid 0.6 units over the tops at set distances in from every
rim: a worn gold line (1.0-1.9 units in; `metal_wear`: patches where the gold has gone), the carved braid (1.9-5.6) and a
second gold line (5.6-6.4). A rim is an edge of a level top beyond which the top falls away: nothing at its height or above it
1.5 units out; where the dump holds nothing of the target there, the collision 6 units out must be lower. A tread too narrow
for the bands along most of its rim (80%) gets none, so a narrow step carries no broken pieces. So on the trefoil the inlay
runs round the raised rings (the large discs, the small ones, the half discs) and the main top's rim; the game's engraving
inside each ring stays drawn (`gate6/final/inlay-top.png`). Options: `above` (only rims over a height: the trefoil's ragged
foot tier left out), `radial` (a dais: only edges facing out from its centre). Targets may `borrow` a twin's reference: the
dumps held three quarters of the east dais; its corners all lie on the west dais moved 720 units, so it is taken whole from
there.

**Weight.** The whole area 9,671 triangles (gate 5: 19,989: the podium box went), read on worker threads in 148-334 ms.

**Brightness (Ran, `gate6/final/measure.txt`, game / on where they differ, the same pixels).**

| Light | Views | game / on |
|---|---|---|
| front (0) | start, west, east, north, obelisk | 0.98 - 1.09 |
| side (90, 270) | start, west, east, north | 0.94 - 1.13 |
| side, the obelisk close | 90, 270 | 0.79, 0.83 (ours brighter: the shaft) |
| back (180) | start, west, east, north, obelisk | 0.93 - 1.05 |

By region (`regions.txt`, on / game): stairs 0.97 / 0.96, trefoil top 1.04 (front) / 1.08 (back), west dais 0.93, east dais
0.90, the podium close 0.95, at play distance 1.08.

**Frame rate (Ran, `gate6/fps6.sh`, `fpsstat6.py`; paced, 3024x1964, both copies at `nice -n 10`).** The machine was far
quieter than in gate 5 (load average 6-16 against 400-500), still shared, so the medians are the measure:

| Run | Rebuild on | Layer on, rebuild off |
|---|---|---|
| hub + valor | median frame 9.12 ms (110 fps), mean 72.8 fps, p99 33.6 ms; median draw 7.69 ms | 11.98 ms (83 fps), 57.3, 42.7 ms; 8.70 ms |
| hub only (run in the other order) | 8.56 ms (117 fps), mean 93.0 fps, p99 15.6 ms; median draw 7.92 ms | 11.16 ms (90 fps), 69.5, 38.4 ms; 8.28 ms |

Whichever ran later was faster (the load fell during the runs), so the difference is the machine, not the rebuild: its cost
is not measurable, and with it on the hub runs at **60+ fps** (median frame under 9.2 ms).

**Room (Ran).** `local/godot-r35/test/room35.py g6 --level valor` (port 41996), both copies Remastered, A drawing the gate-6
pieces (`RTA_ER_WORLD_DIR` = `gate6/world`; A's log: `rebuild for hub, 6 pieces (9671 triangles)`), B with
`RTA_ER_WORLD=off`: **1,854 ticks compared, no shared column differs.**

**The window fix (a9dfed1).** The gate's pictures are the drawer's own (`app shot`: `get_shown_image`, "Godot's own drawing"),
not the window, and both sides of each pair are taken the same way: the view.gd brightness fix does not touch them.

**Review** (`gate6/final/`: game | rebuild; front, side and back light, close and at play distance):

| Target | Check | Seen | Verdict |
|---|---|---|---|
| obelisk | passed, max 10.4 | the box is gone: a slim tapered base to the game's profile, gold foot and moulding, braid taper (`obelisk-chase-o0.jpg`, `west-chase-o0.jpg`, `dais-close.png`); at play distance it reads like the game's tapered gold-trimmed base, not clearly better (the game's broad gold band and single gold panel read as strongly); the shaft stays brighter in side light | **refused on review** |
| trefoil | passed, 0.6 | gold-framed braid inlays round every raised ring and the rim, the engraving inside kept; visible at play distance (`start-chase-o0.jpg`), light matched; **but drawn where the game culls the far platform: rings and friezes float in the haze** (`float-west-o270.png`; gate 5's risers did the same, `float-west-o270-gate5.png`; `start-chase-o180.jpg`, far left) | **refused on review** |
| stairs | passed, 0.5 | no darker stripes: the risers as pale as the game's (0.97 / 0.96, `north-chase-o0.jpg`); level with the game rather than better; float with the platform when culled | **refused on review** |
| daises | passed, 0.6 | richer (an inlay on each tread, braid risers); at play distance greyer and the steps softer than the game's pale, crisp ones (0.93 / 0.90, contrast std 45 against 51) | **refused on review** |

The reasons are in `local/er-world/hubfit/hub-gate6.json` and the live `rebuild/hub/rebuild.json` (0 pieces). The gate-6
pieces stay in `local/er-world/gate6/world/` (`RTA_ER_WORLD_DIR` to see them).

**Sixth session changed:**

- Modified (tracked): `tools/godot/er_world_fit.py` (`fit: loft` and its inside test, `inlay` with `above` / `radial`, the
  rim test with the collision, `borrow`), `tools/godot/project/shaders/er_ruin.gdshader` (`direct_gain`, `metal_wear`), this
  file. `er_world.gd` and `er_mesh_bake.gd` unchanged (the loader passes any value the recipe names).
- Local: `local/er-world/gate6/` (recipe, fits, tries, `g1`, `final/`, fps, `world/`), `local/er-world/hubfit/hub-gate6.json`,
  `local/godot-r35/` (r34's library, the extension and project built again, `test/room35.py`).

## Gate 7 (Ran, seventh session)

The asks: no floating overlays; daises as pale and crisp as the game's (gate 6: on/game 0.93 / 0.90, contrast 45 against
51); trefoil, stairs and obelisk clearly better at play distance, keeping light within 10% in front, side and back light.
- Recipe: `local/er-world/gate7/recipe7.py`; its knobs come from the environment, and the final set is
  `gate7/knobs-final.sh`.
- Fits and check pictures: `gate7/fit/`.
- Route: `gate7/route7.py` + `run7.sh`. `DUMPSHOT=1` dumps the list after each shot.
- Tries: `gate7/try.sh` (fit, route, regions), `t1..t27`.
- Final run: `gate7/g2`.
- Measures: `measure7.py` (the sky left out, grouped by light), `regions7.py` (contrast of the rebuilt shape itself),
  `floatcheck.py`, `diffmap.py`, `pair.py`.

**1. Floating overlays (Ran).** `rta_world.cpp`:
- `set_world_hide` takes `kinds 4` (watch-only) and `[9]`, the watched packets' figures as hex.
- `world_hidden` calls `world_watch`, which is cached per draw, and never returns a watch volume.
- The hide searches (`world_hidden`, `world_tri_hidden`, `world_model_taken`) skip watch volumes.
- `get_world_hide` adds whether the volume was drawn this frame.

`er_world.gd` shows an overlay only on those frames. It tells the server only of a change, because there are 118 pieces
now. `app er world rebuild` reports the watch volumes.

The first cut was by the 120-unit chunk grid, which was not enough. The game culls packet by packet, so a ring still hung
past a culled tier (`g1/start-chase-o270`). The fitter now cuts each overlay by the packet each triangle lies nearest to
(trefoil 66 parts, stairs 6, daises 24 + 20). Figures are stable across runs and builds: 1,282 of 1,282 of a fresh dump
match gate 5's.

Results:
- Pixels the rebuild draws over the game's sky, over the 26 shots: **26,082 at gate 6, 4,946 now**. What is left is the
  silhouette edges of the 0.6-unit offset (`final/floatcheck*.txt`).
- `final/float-west-chase-o270.png` and `float-start-chase-o180.png` show game | gate 6 | gate 7.

**2. Daises (Ran).** `er_ruin.gdshader` gained:
- `nosing` / `nosing_w`: a pale worn band along a riser's top;
- `foot_ao` / `foot_w`: a dark crease at its foot, sharp to a pixel through `fwidth`;
- for the risers, the normal map's cavity in the crease.

The dais inlay is narrower (gold 0.8-1.6 units in, braid to 3.4, gold to 4.0) and paler, so the game's pale tread stays.
With the obelisk's pieces left out (`t26`), shape contrast and on/game (from `regions7.py`):

| View | Shape contrast (std), game | on | on/game |
|---|---|---|---|
| west | 55.8 | 53.8 | 0.93 |
| start, far | 47.7 | 48.7 | 0.91 |
| north, far | 50.3 | 51.9 | 0.89 |

The edges are now crisp, but the tops are not yet as pale. Darker feet gave more contrast and a greyer dais. More direct
light gave paler fronts and +14-21% in side light (`t22`-`t24`).

**3. Play distance (Ran).** The carving:
- `cavity` darkens the texture's cuts as cavities, squared;
- `crest` lightens its crests as wear (the two balanced round the mean);
- `far_contrast` raises the contrast with distance as the mip maps flatten it.

The gold: inlay glint 2.6, sheen 0.7, less wear. The trefoil's risers got the crisp steps too. The obelisk's shaft:
- slate purple (0.24, 0.20, 0.31);
- `stone_sheen` 2.0, the sky in its face, like the game's environment-mapped pass;
- light flattened (gain 0.95, direct 0.7), because the game's shaft hardly changes with the light.

**Brightness (Ran, `final/measure.txt`, on/game, the sky left out).** Weighted by pixels: front 0.96, side 1.03, back 1.07.

| View | on/game |
|---|---|
| west side | 0.87 |
| start, back | 1.11 |
| obelisk, side | 1.12 / 1.26 (the slimmer shaft) |
| the other 22 views | 0.91 - 1.07 |

**Frame rate (Ran, `gate7/fps7.sh`, `fps7b.sh`; paced, 3024x1964, `nice -n 10`).** The machine was shared, with another
worker's campaign run and load 30-460, so medians are compared only between runs back to back:

| Run | Median frame, on | Median frame, off |
|---|---|---|
| hub, alternating (load 31-51) | **8.88 ms** (113 fps) | **8.94 ms** (112 fps) |
| hub + valor | 9.12 ms (110 fps) | 15.65 ms (64 fps, load rose to 45) |

The layer's own time is 45-90 us a frame. The rebuild's cost is not measurable, and the hub runs at **60+ fps** with it.

**Room (Ran).** Command: `local/godot-r36/test/room36.py g7 --level valor` (port 41997).
- A: `RTA_ER_WORLD_DIR` = `gate7/world`; its log reads `rebuild for hub, 118 pieces (9671 triangles)`.
- B: `RTA_ER_WORLD=off`.
- Result: **1,852 ticks compared, no shared column differs.**

**The check (12 units, Ran):**

| Target | Max off (units) |
|---|---|
| trefoil | 0.6 |
| stairs | 0.5 |
| daises | 0.6 |
| obelisk | 10.4 (p99 2.8) |

All passed.

**Review** (`gate7/final/`, game | rebuild per shot; sheets `sheet-play-start/north/west.jpg`, `sheet-close.jpg`):

| Target | Seen | Verdict |
|---|---|---|
| trefoil | nothing floats. Richer: gold-framed braid rings, crisp tier noses, gold catching the light. Light matched. At play distance from the east the game's lit ring lips read crisper (shape contrast 38 against 49) | **refused on review** |
| stairs | crisp pale nosings and dark feet on carved risers. Level with the game (contrast 33.7 / 37.1 against 38.2 / 39.9; 44.2 against 38.3 from the north) | **refused on review** |
| daises | crisp, contrast level or better. Tops not as pale (0.89-0.93) | **refused on review** |
| obelisk | slate-purple shaft with gold bands and the sky's sheen. Level with the game, not clearly better. Side light 1.12-1.26 (the slimmer shaft) | **refused on review** |

The reasons are in `local/er-world/hubfit/hub-gate7.json` and in the live `rebuild/hub/rebuild.json`, which has 0 pieces
and 0 volumes. The gate-7 pieces stay in `local/er-world/gate7/world/` (point `RTA_ER_WORLD_DIR` at it to see them).

**Seventh session changed:**
- Modified (tracked):
  - `tools/godot/extension/src/rta_world.cpp` and `rta_drawer.h`: watch-only volumes, `world_watch`;
  - `tools/godot/project/er_world.gd`: overlays shown only on frames the game drew their packets; changes only sent to the
    server; the `rebuild` report;
  - `tools/godot/project/shaders/er_ruin.gdshader`: `nosing`, `foot_ao`, `cavity`, `crest`, `far_contrast`,
    `stone_sheen`;
  - `tools/godot/er_world_fit.py`: overlays cut per game packet, `watch` in the pieces;
  - this file.
- Local:
  - `local/er-world/gate7/`;
  - `local/er-world/hubfit/hub-gate7.json`;
  - `local/godot-r36/` (r35's library; the extension and project built again; `test/room36.py`).

