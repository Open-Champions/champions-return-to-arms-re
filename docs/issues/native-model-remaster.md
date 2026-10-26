# The game's own models remastered (Godot, Remastered mode)

Started 2026-10-25. The owner's aim: the game's **own** characters, monsters and NPCs at much higher quality, with the same
proportions and the same animation. The work runs on the player's machine, from the player's own disc, as the game plays.
Nothing derived from the game is kept with the program. Everything below says **Ran** (with what was seen) or **Read**.

## STATE (2026-10-25)

**Working, Ran.** `look.remaster_models = on` is the default in scene mode. The Classic look sets it off. Every skinned
figure of the frame is baked once into a smooth mesh and drawn in place of the game's own skinned packets. Each frame it is
skinned by the very matrices the game's vertex program used. It is coloured by the game's own art-pack texture, with normal
and ORM maps derived on this machine.

The Elden Ring layer and the Tripo outfits still draw over the body:
- A fitted outfit's pieces are placed after the body.
- A figure that `er_layer.gd` replaces is left to it.

Built into `local/godot-r24/` (extension and project). Not committed.

| Step | State |
|---|---|
| 1. Geometry: subdivision with creases, skin weights interpolated, drawn through the skeleton stream | **done, Ran**: players, NPCs, goblins, war boars, black widows, badgers, lava monster, critters baked (1-66 ms each, on a thread) |
| 2. Materials: normal + ORM from the 4x textures, skin/leather/metal/cloth per texel, per-model override | **done, Ran** (maps cached by picture hash); class heuristics not yet tuned picture by picture |
| 3. `look.remaster_models = on/off`, default on, Classic off; ER armour / Tripo over it | **done, Ran** (on/off pairs below); ER armour over the remastered body **pictured 2026-10-26** (r28, fire1: `local/er-world/haze/armour-fire1-p1-r28.png`; far off in the haze: `native-er-world.md` Gate 3) |
| 4. Quality gate: sheets, 60+ fps, LOD, room in step | **Ran**: sheets of all 12 figures and the monsters met; 104 fps with it against 100 without; LOD in; **room in step** |

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

## Next

- Tune the class heuristics on a per-texture picture sheet; add a debug view of the derived maps.
- Find levels with orcs and trolls for the sheet.
- ~~Picture the ER armour over the remastered body.~~ Done 2026-10-26 (r28, fire1, near and far in the haze).
- A draw that mixes skinned and rigid packets of one object stays drawn by the game, which would double the body. This
  has not been seen.
- The bake on first sight takes up to 66 ms on a thread, but the hand-over and merge happen on the main thread: one
  frame of up to 30 ms.

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

**Local:** `local/model-remaster/*`, `local/godot-r24/` (extension rebuilt, project staged).
