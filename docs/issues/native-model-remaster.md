# The game's own models remastered (Godot, Remastered mode)

Started 2026-10-25. The owner's aim: the game's **own** characters, monsters and NPCs at much higher quality, with the same
proportions and the same animation. The work runs on the player's machine, from the player's own disc, as the game plays.
Nothing derived from the game is kept with the program. Everything below says **Ran** (with what was seen) or **Read**.

## STATE (2026-10-26, round 2)

**Working, Ran.** `look.remaster_models = on` is the default in scene mode. The Classic look sets it off. Every skinned
figure of the frame is baked once into a smooth mesh and drawn in place of the game's own skinned packets. Each frame it is
skinned by the very matrices the game's vertex program used. Round 2 (below) makes it **as bright as the game's own figure
from every light the game has** (the game's per-corner light fitted each frame), gives every texel one of seven materials
lit as what it is, fixes the faces (lips, eyes, lashes), and moves the heavy work off the main thread.

The Elden Ring layer and the Tripo outfits still draw over the body:
- A fitted outfit's pieces are placed after the body (the body drawn `dressed_shrink` inside itself under it).
- A figure that `er_layer.gd` replaces is left to it.

Built into `local/godot-r33/` (extension and project). Not committed.

| Step | State |
|---|---|
| 1. Geometry: subdivision with creases, skin weights interpolated, drawn through the skeleton stream | **done, Ran**; round 2: weld only where skinned alike (the mouths were torn open), T-junctions split, decals kept |
| 2. Materials: seven classes per texel, per-model and per-texture overrides; lit as metal / skin / hair / fur / cloth / stone | **done, Ran** (round 2) |
| 3. `look.remaster_models = on/off`, default on, Classic off; ER armour / Tripo over it | **done, Ran**; ER armour over the remastered body of all 12 figures pictured (`gate2/er-armour.jpg`): no poke-through |
| 4. Quality gate: sheets, fps, LOD, room in step | **Ran**: 12 figures x 3 levels, 13 monster kinds in 11 levels, room in step (1,779 ticks); the 60 fps crowd gate **not met on this machine today** (the base game alone ran at 34 a second, other work loading it; see below) |

## How it works

**Read** `tools/godot/extension/src/rta_remaster.{h,cpp}` (new class `RtaRemaster`) and
`tools/godot/project/model_remaster.gd`.

- **What a model is.** Each frame, `RtaRemaster.scan` takes the skeleton stream (`rtag_skeletons_get`: the path of
  `skeleton_export.*` / `er_layer.gd`) and groups the skinned packets by scene object. Rigid packets in the same object
  (a weapon in the hand) stay the game's. An object posed by two skeletons is left to the game. A model's key is a hash
  of its packets' bind-pose sources and corners. Scene object numbers change every frame, so a figure is followed by its
  animation state and its place among that state's objects. A model whose key keeps changing (more than 6 times) is left
  to the game.
- **Geometry** (`Job::run`, on its own thread):
  - The packets are welded by position, so a packet seam becomes an ordinary edge.
  - Degenerate and duplicate triangles are dropped. Each triangle is wound to agree with the game's normals.
  - Loop subdivision runs at 1 -> 4 per level, with **creases** where:
    - the game's normals part across an edge (`crease`, a cosine, default 0.5: its hard edges);
    - the edge is on a boundary;
    - more than two faces meet;
    - the faces fold back on each other.
    Three creases at a vertex make it a corner.
  - Loop pulls a surface inward, which would make thin limbs thinner. So the control points are **fitted** (8
    iterations) until the subdivided surface passes through the game's own vertices again. The largest leftover gap is
    0.004-0.16 units on a 65-unit figure (printed per bake).
  - Skin weights are subdivided with the same weights as the positions (the 4 largest joints kept).
  - UVs are interpolated linearly per triangle, so the texture stays where it was.
  - Normals come from the new surface, averaged only across faces whose game normals agree.
  - Levels:
    - Level 0 is the game's own mesh.
    - Up to `levels` (2) further levels are made while staying under `max_tris` (80,000). The dense player models
      (12k triangles) get one level; monsters (0.5-3k) get two.
- **Drawing.**
  - The packets drawn with one texture state become one surface (`RtaRemaster.merge`). The shaman goes from 337
    packets to a handful of draw calls.
  - A RenderingServer skeleton holds the frame's skin matrices (`RtaRemaster.pose`, with `tween` between game frames).
  - The game's skinned packets of that object are left out by a new drawer call, `RtaDrawer.set_hidden_skinned`:
    - only skinned packets are left out, so held rigid models stay;
    - `set_hidden_objects` of the ER layer is untouched.
  - Draw order is the figure's own first hidden draw (`hidden_orders`), as `er_layer.gd` does.
  - LOD: the finest level within `lod_near` (260 units), the level below it (never level 0 unless it is the only one)
    out to `lod_far` (1200), level 0 beyond.
- **Materials.**
  - `RtaDrawer.get_piece_textures` (new) gives, per skinned packet of the frame, the texture RID (with the art pack's
    picture in place) and its draw state: `st_scale`, `tex_offset`, `tex_size`, alpha test, TEXA, TCC.
  - `shaders/remaster_model.gdshader` reads the texture exactly as `gs_draw` does. It is lit like
    `er_armour.gdshader`, including the game's own light on the figure (`er_layer.gd _game_light`: torches, poison,
    hit flash), so body and armour are lit alike. That light is set per figure as material parameters: the world's
    draws fill Godot's instance-uniform buffer ("Too many instances using shader instance variables" in the first try).
  - `derive_maps`:
    - A bilateral-filtered luminance with the broad shading taken off gives a height. Sobel turns it into a normal map.
    - Per texel, a class (skin / leather / metal / cloth) by hue, saturation, value and local contrast, majority-smoothed.
    - ORM: r is a cavity term, g roughness by class, b metal.
    - It waits up to about 3 s for the art pack's picture to arrive.
- **Overrides.** `tools/godot/project/model_remaster.cfg` (tracked, our numbers only) has sections `[default]`,
  `[player]`, `[player.<class>]`, `[creature]`, `[creature.<Class>]` (the class names of `er_creatures.cfg`). Keys:
  - `off`, `levels`, `crease`, `fit`, `keep`, `max_tris`, `lod_near`, `lod_far`;
  - `class` / `part<N>` (`skin|cloth|leather|metal|auto`), `strength`, `metal`, `rough`, `gain`, `bump`, `cavity`,
    `game_light`.
- **Cache.** Everything goes in the user data folder, never tracked:
  - meshes: `user://model-remaster/mesh/<key>.bin`;
  - maps: `user://model-remaster/maps/<md5 of the picture>-...-{n,orm}.png`.
  A second run loads every model and map from the cache.
- **Tests.**
  - `RTA_REMASTER_DEBUG=1` prints each figure, its bake state and the objects left to the game, every 240 frames.
  - `RTA_REMASTER_MODELS=off` forces it off in one copy.

## The gate (Ran; `local/model-remaster/`)

- Scripts: `route.py` / `run.sh` / `sweep.sh` / `sheets.py` / `fps.sh`.
- **`gate/sheet-c0..c11.jpg`**: all 12 player figures (class choice 0-11) in three levels: the hub, arachna1 (the dark
  cave) and islgoth (the evening hall). For each: close (shoulder) idle original | remastered, close run / attack,
  gameplay (chase) idle original | remastered, gameplay run.
- `gate/players.jpg`: every figure close in the three levels, original | remastered.
- `gate/zoom.jpg`: upper bodies at full size.
- `gate/monsters.jpg`: arachna1 (black widow, scorpions), drunare, storm1 (the lava monster, a giant), valor and fire1.
  Goblins were baked in fire1 (12 variants) and war boars in valor, but they are not near the camera at the shot ticks.
- Seen:
  - Smoother silhouettes (shoulders, arms, tails, hair).
  - The same proportions and the same pose frame for frame: skinned by the game's own matrices.
  - No cracks at packet seams, no missing parts, held weapons kept.
  - Lighting continuous across the figure.
- Differences to know:
  - In arachna1, where the torch-lit / poisoned game figure goes white under the game's 2x light and bloom, the
    remastered one is lit warm but not blown out.
  - Each pair's "on" picture is taken 2 frames after "off", so the camera has sometimes moved.
- **Not met:**
  - Orcs and trolls / cyclopes were not found in the levels probed (`probe/`: storm1, storm3, innovat1, fire3,
    obsidian, honor, nit1, swamp1, blood1, drunare, fire1, valor).
  - Skeletons are not identified by name in the shots (drunare's "unknown" figures).
- **Frame rate** (paced, 3024 x 1964, the hub + arachna1 + islgoth with 24 shots, `gate/fps-{on,off}/frames.csv`):
  - Median picture gap 8.8 ms on vs 9.15 ms off; mean excluding stalls **103.9 fps on, 100.2 off**.
  - "Pictures a second" over the whole run (loading included): 47.3 vs 46.9.
  - The layer's own time is 2.1 ms a frame with 6 figures. It was 5.6 ms before packets with a known texture were
    skipped; worst 30 ms when a model first loads.
- **Room** (Ran, `local/godot-r24/test/room24.py mr1`, both copies Remastered, B with `RTA_REMASTER_MODELS=off`):
  **1,851 ticks compared, no shared column differs**.

## Round 2 (2026-10-26; Ran; `local/model-remaster/gate2/`, build `local/godot-r33/`)

### The game's own light (the biggest change)
- **Read** `RtaRemaster.light_sh`. Each figure's corners carry the colour the game's vertex program computed: ambient,
  sun, fill, the two point lights, poison and hit-flash tints, clamped at 255 (`rtag_scene_full` r, g, b). Each second
  frame those colours are fitted against the corners' normals by second-order spherical harmonics (nine coefficients a
  channel). The shader takes the light from that fit at its own (normal-mapped) normal.
- It is then applied **as `gs_draw` applies the game's light**: texture x light in stored (gamma) values, clamped per
  channel, times the level's ambient; the scene's lights add their share as they do to the game's own figures.
- **Ran, seen**: the figures are now as bright as the game's, front and back (`gate2/players.jpg`). In round 1 the dark
  levels came out 1.6-2x too bright (drundar, boar1, tormedal), the shadowed side too light (the light was applied in
  linear values), and arachna1's poisoned figures came out green where the game's go white. All three now match.
- er_layer.gd's model of the game's light (`_game_light`) is still used for the sun's direction (the highlights).

### Materials: seven classes, tuned on the real textures
- **Read** `analyse` / `maps` in `rta_remaster.cpp` (between `RM_TEXELS_BEGIN` and `_END`, plain C++). The classes are
  skin, leather, metal, cloth, hair, fur and stone. They are decided per texel from:
  - hue, saturation and value;
  - the spread of luminance over 3 game texels, on painted texels only (the empty space between islands is left out);
  - strands: a coherent structure tensor, gradients that cancel (stripes, not one edge) and dense edges over 4 texels;
  - gold (ochre and yellow) and grey worked metal (mail, engraving, bright silver).
- AUX map (r skin, g hair, b/a the strand's direction) and ORM alpha (fur). ORM / AUX at half size past 2048.
- Tuned against every player texture (dumped with `RTA_REMASTER_DUMP=<folder>`, looked at with
  `local/model-remaster/texels/`: the same code built as a command, `sheet.py` / `probe.py` / `grid.py`).
- What could not be told by colour is said in `model_remaster.cfg`, per figure (`player.<class>.<n>`, n the figure
  chosen) and per texture:
  - `tex<K>` = class | `auto:<class>`. A body picture is `auto:skin`; a hair picture is `hair`.
  - `rules`: colour boxes of a class.
  - `shiny`, `gold`, `grey_metal`, the skin band.
  - Creatures: a hide is skin over a wide hue band, gold off, grey metal only on armoured kinds. Skeletons are stone,
    the snow beasts fur, a black widow's legs chrome.
- **Shader**:
  - Metal keeps its painted diffuse (as the game's figure has it); its highlight takes its colour, with Fresnel, and a
    key highlight from the game's sun.
  - Skin has a warm band where light turns to shadow, warmer occlusion and a broad, weak highlight.
  - Hair and fur get a Kajiya-Kay sheen along the texture's own strands (two lobes, the second coloured; fur's broader).
  - Cloth and stone stay rough. Sky reflections are half desaturated (no blue steel).

### Faces and two-pass packets
- **The mouths were torn open in the smooth levels.** Upper and lower lips (and eyelids) meet in the bind pose but
  follow different joints. The weld now joins vertices only when they are skinned alike.
- The "layers" pass (a vertex under another surface drawn inside it) drew the lips apart over the teeth. It is now off
  by default (`layer_gap = 0`).
- **Lashes and brows came out black.** The game draws the bodies with GS blend `Cs + Cd·As`, where alpha 0 is opaque and
  a dark texel of high alpha is mostly what is behind it. Those texels are now not drawn. Standard alpha-blended packets
  are cut at 0.5.
- Two-pass packets:
  - A first pass that is an environment map (120 of a player's 311 packets) is sampled as a sphere map, and the second
    pass is blended over it by its own GS blend.
  - A first pass with the same mapping is laid under the second (`over_tex`).
  - Decals (the same triangles in a later packet) are kept off the surface's shape and drawn 0.04 above it.
- Faces: `gate2/face2`, `face7`, `face4` (close, front and side) now match the game's, with crisper relief.

### Monsters (`gate2/monster-<level>-<kind>.jpg`)
- Each sheet shows close and gameplay distance, in the level's light and in a second light (sun off, the lamp on),
  original | remaster.
- The camera is put on the figure from its far side by `app remaster aim`, after the player was walked there
  (`app remaster seek`, the script's controller).
- **Met**:
  - orc (fay1, valmedal)
  - war boar (boar1)
  - goblin (drundar, fire1's crowd)
  - ogre (drundar)
  - cyclops (islsm3b)
  - black widow and scorpion (arachna1)
  - snow beast and snow boss (storm3, storm4)
  - lava monster, a giant (fire3)
  - red dragon, a boss with wings and a tail (fire5)
- **Not in the frame at the shot**: skeletons (tormedal, wate2a: they rise from the ground later), the minotaur boss
  (disbonus), the vampire lord (nit2). Wolves: the game has none (no such class).
- Cracks: none seen on tails, wings or legs at close range.
  - The weld takes a tolerance of 0.0025 (packets' copies of a seam vertex can differ in the last bits).
  - T-junctions on packet borders are split (orcs 3-6 a model, the hub's people 18).
- The fit leaves at most 0.34 units on one orc variant, 0.004-0.16 elsewhere.

### Elden Ring armour over the remastered body (`gate2/er-armour.jpg`)
- All 12 figures in their fitted outfits, front, side and back, game body | remastered body: no poke-through or
  z-fighting seen.
- The body is drawn `dressed_shrink` (0.35) units inside itself where `er_layer.gd` dresses the figure.

### Cost and frame rate
- The layer's own time:
  - 1.4 ms a frame with 6 figures (the hub, arachna1, islgoth).
  - 3.7 ms with 11.5 figures in fire1's crowd (2.0 of it material parameters; now looked at every 2nd frame for the
    nearest four, every 4th for the rest).
  - A round-2 version with every figure's packets gone through each frame cost 26 ms; now a figure is looked at again
    only every 30 frames once settled.
- `scan` 3.8 -> 0.4 ms: packets are hashed 8 bytes at a step on every third corner, and their keys are made once.
- Main-thread stalls removed:
  - mesh merges and their Godot meshes are built on worker threads;
  - the cache is read and written there;
  - maps' textures are made there.
  - Worst frame 383 -> 24-110 ms, the first sight of a model.
- In a crowd only the 8 figures nearest the eye get the finest level (`fine`).
- fire1's crowd, paced at 3024 x 1964 (`gate2/fps-f-{on,off}`): **45.0 a second with it, 33.6 without** (second half,
  without stalls). The machine was carrying two other agents' games and a build at the time. Not a measure of 60+:
  the base game alone was at 34. To run again on a quiet machine.

### Room
- `local/godot-r33/test/room33.py mr33`: both copies Remastered, B with `RTA_REMASTER_MODELS=off`.
- **1,779 ticks compared, no shared column differs.**

### Tools (local)
- `app remaster aim NAME [SIZES ORBIT RAISE UP] | aim off`: the camera on a figure.
- `app remaster seek NAME [NEAR] | seek off`: walks the player there.
- `app remaster info`.
- `RTA_REMASTER_SET="key=value,..."`: choices over every figure.
- `debug_view` 1-3 shows the game's light, the normals, or skin / strands / metal.
- Scripts in `local/model-remaster/`:
  - `route2.py` / `run3.sh` / `monsters.sh` / `msheet.py`
  - `sweep2.sh` / `sheets2.py`
  - `er.sh` / `esheet.py`
  - `fps2.sh` / `fpsstat.py`
  - `texels/`

## Next

- The 60+ fps crowd gate on a quiet machine (fire1, `fps2.sh`).
- Skeletons, the minotaur boss and the vampire lord on the sheet. Their scripts bring them later; a route that waits or
  triggers them is needed.
- Eight player textures are not yet numbered in the cfg (`texels/mkcfg.py` lists them). They use the automatic classes.
- A two-pass first pass's environment map is sampled as a plain sphere map. The game's own mapping of it is not read.
- The material parameters for a crowd (2 ms with 11 figures) could move to a per-figure buffer.

## Changed

**New (tracked):**
- `tools/godot/extension/src/rta_remaster.{h,cpp}`
- `tools/godot/project/model_remaster.gd`
- `tools/godot/project/model_remaster.cfg`
- `tools/godot/project/shaders/remaster_model.gdshader`
- this file

**Small hunks:**
- `extension/src/register.cpp`: the class registered.
- `rta_drawer.h` / `rta_drawer.cpp`: `get_piece_textures`, `set_hidden_skinned` bound.
- `rta_scene.cpp`: per-packet texture record, `hidden_skinned`.
- `project/er_layer.gd`: `last_hide`.
- `project/scene_view.gd`: look key `remaster_models`, the node created and called.
- `project/portal/edition.gd`: Classic sets `remaster_models=off`.

**Round 2 (tracked, uncommitted):** `rta_remaster.{h,cpp}`, `model_remaster.gd`, `model_remaster.cfg`,
`shaders/remaster_model.gdshader`, `rta_scene.cpp` (the aim camera; the first pass of a two-pass packet and its GS blend
recorded), `scene_view.gd` (`app remaster ...` passed on), this file. (`main.gd`'s `remaster` command word went in with
another agent's commit.)

**Local:** `local/model-remaster/*`, `local/godot-r24/`, `local/godot-r33/` (extension rebuilt, project staged).
