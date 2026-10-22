# Another game's figures on the game's own skeletons (the Elden Ring layer, step 1)

Started 2026-10-21. The owner's aim: Champions, Champions of Norrath (later) and an Elden Ring layer in one game. This
first step: the Godot version draws Elden Ring character, armour and weapon models in place of the local player,
driven by the game's own animation - the game decides every joint; Godot only draws - on the owner's computer only.
Everything below says **Ran** (with what was seen) or **Read**. A successor needs only this file.

## STATE

| Asked | State | Shown |
|---|---|---|
| A. the game's skeletons out of the library | **done, Ran**: per drawn animated model its skeleton (parents, bind pose), its posed joints and skin matrices in the world, the bind-pose mesh with joints and weights; `rtag_skeletons_get` (optional function), `RtaMachine.get_skeletons(with_mesh)` | the game's bind mesh re-skinned from the stream: 0.00035 units at most in C++, 0.022 through Godot's `Skeleton3D` (below) |
| B. Elden Ring models, local only | **done, Ran**: 50 part files and the shared body textures fetched by byte range (188 MB of the 14.7 GB the two archives hold), decrypted, decompressed, read with SoulsFormatsNEXT, written as glTF: 8 outfits, one per Champions class | `local/souls-ref/er-models/<set>/` (never tracked, never uploaded) |
| C. retarget and draw (`look.er_models = on`) | **done, Ran**: a joint map of our own (`tools/godot/project/er_joint_map.cfg`) plus a reader of any person skeleton's bind pose; the figure drawn in the world's draw order; nothing changes without the folder | pictures below; running and attacking, overhead and shoulder views |
| multiplayer unaffected | **Ran**: two Godot portals in one room, copy A with the layer on (shoulder view), copy B without: **1,851 ticks in step** hub > drunare, no shared column differs | `local/er-layer/m2/` |

Built into `local/godot-r10/` (`RTA_GODOT_OUT=local/godot-r10`; a copy-on-write clone of `local/godot-r9`, its snapshot of
`tools/recomp` with this round's `render/scene_tap.*`; `build.py lib`, `extension`, `project`). Tests, routes and pictures:
`local/er-layer/` (`run.sh NAME VIEW MODES` - the fight route with pictures per mode; `mkroute.py`; `room10.py` - the room;
`final/` - the pictures of this report).

## A. The skeleton stream

**Where the game computes its bones (Read: `docs/spec/animation.md` 2.4, 8.1-8.4; `render-pipeline.md` 4.7).**
`anim_buildPose` 0x16ed40 blends a state's tracks and composes them down the hierarchy (the VU0 program at 0x3e5c50)
into a pose buffer (0x620 bytes; 100 pooled at 0x791ec0): per joint three s16 rows, rotation x 4096, translation x 64,
a matrix that takes BIND-POSE model-space points to posed model space. The skeleton - depth list (+0x10) and bind
offsets (+0x0c, unit 1/64) - is the top track's clip's. `anim_emitPose` 0x16f880 stamps the buffer with `g_drawFrame`
(0x44fdd0) and the draw list uploads it to VU1 (MSCAL 0x3a); MSCAL 0x0c makes the 64 joint matrices (pose x the
object's transform, object -> clip) that the vertex program skins the packet's bind-pose vertices with.

**How it is taken (`tools/godot/lib/skeleton_export.{h,cpp}`).**
- Game's thread, when a draw pass has returned (`scene_export.cpp` `drawn()`): every pool buffer stamped with this pass's
  `g_drawFrame` is a pose this pass drew. Each is recorded - matrices, owner state (+0x610), the owner's top track's clip
  (state +8 + (count-1) x 0x20), that clip's depth list and bind offsets - as one batch under a number. The number rides in
  the VIF stream as word 64 of the camera block the tap already carries (`render::TapFrame::batch`;
  `tools/recomp/render/scene_tap.{h,cpp}`: + `batch`, `clip_to_world`, `full_source`).
- A first version hooked the DMA tags (`rt_dma_tag`): in the front end the pose reaches VU1 by a REF tag to the buffer,
  but **in a level no tag of the chain points into the pool (Ran: 0 in the hub and valor)** - the stamp holds in both.
- Decoder's thread (`skel::build`, from `scene::take`): per skinned object the tap's 64 joint matrices are taken back
  through the inverse view-projection into the world (`skin[j]`); the object is tied to the batch's pose that is those
  matrices through one object matrix (largest difference 0.05 units allowed). Parents from the depth list (joint j
  composes with stack level d, written by the last joint of depth d-1); `bind[j]` = -offset/64; the posed joint frame
  `joint[j] = skin[j] x T(bind[j])`.
- C interface (`rtag.h`, added without changing version 6): `rtag_skeleton` (object, pose, state, clip, buffer,
  joint_count, parent[64], depth[64], bind[64][3], skin[64][12], joint[64][12], scale, pose_error), `rtag_skin_piece`
  (per scene piece: skeleton, its bind-pose sources, slot 0 in the world - a rigid model's own matrix), `rtag_skin_source`
  (= `render::TapSource`), `full_source` (per complete-geometry corner: its source). `rtag_has("skeletons")`.
- Godot (`RtaMachine.get_skeletons(with_mesh)`): per skeleton `parent`, `bind` (PackedVector3Array), `joints` and `skins`
  (Transform3D); per piece its skeleton, object, kind, flags, corner and source ranges, `slot0`; with_mesh also the sources
  and the drawn corners. **Skeleton3D-compatible**: bone j's rest `T(bind[j] - bind[parent])`, a Skin bind pose `T(-bind[j])`,
  global pose `joints[j]` (`er_layer.gd` `_skeleton3d`, `_skin_of`).

**Ran - the game's own bind mesh re-skinned from the stream** (the fight route: power-on, hub, valor, a run through the
level and a fight with the boars, attacks; `local/recomp-speed/out/det-fast.rig`):

| | |
|---|---|
| `rtag_host --scene3d --skeleton-check` (C++, every frame) | 5,084 draw passes, 15,053 poses drawn (all with the clip's skeleton); 17,493 skinned objects tied to their pose (through one object matrix: mean 0.00004, largest 0.00025 units); **202,688,121 drawn corners re-skinned from their bind-pose sources: largest difference 0.00035 units (mean 0.000042) through the skin matrices, 0.00037 through joint frames x inverse rest; none over 0.01** (23 animation states, 21 clips) |
| Godot, `app er check FILE` (every frame, the stream into `Skeleton3D` nodes: rest from the bind pose, local poses from the joint frames, then Godot's global poses x inverse rest) | the player (64 joints, 7 clips: run, attacks): 1,810 frames, 103,253,805 corners, **largest 0.022 units, mean 0.0030** (the figure is 65 units tall); the boars (25 joints): 0.0037 .. 0.018; a front-end figure (63 joints) 0.009. The extra over C++: `Skeleton3D` keeps position, rotation and scale per bone and drops the shear of the game's 12-bit matrices |
| Logs | `local/er-layer/a1/out3.txt`, `local/er-layer/final/check-{shoulder,overhead}.txt` |
| Pictures: the game's figure / its bind mesh skinned in Godot (`er_models = self`) / the Elden Ring figure | `local/er-layer/final/sheet-overhead-zoom.jpg` (five moments, overhead), `final/sheet-shoulder-*.jpg` |

## B. The Elden Ring files (local only)

The owner's copy (app 1245620) keeps characters and parts inside `Game/Data3.bdt` (chr, 2.86 GB) and `Game/Data0.bdt`
(parts, 11.8 GB), not as loose files: a filelist for `chr/` and `parts/` finds nothing (Ran). On this line (about
0.6 MB/s) the whole archives were hours away, so:

1. `Data*.bhd` fetched (15 MB) and decrypted with the archive keys of UXM (its `ArchiveKeys.cs`, already in
   `local/souls-ref/tools/uxm`); the paths hashed (`/parts/...`, prime 133, 64-bit) against UXM's Elden Ring dictionary:
   offset, size and AES ranges of every wanted file (`local/souls-ref/scripts/er_bhd.py`).
2. DepotDownloader built from its source (SteamRE/DepotDownloader, .NET 8 SDK from Microsoft's installer script into
   `local/souls-ref/tools/dotnet`) with a local patch: only the manifest chunks that hold given byte ranges
   (`RTA_DD_RANGES`), and the remembered login of the stock build read in place (`RTA_DD_ACCOUNT`; no password was
   entered or asked for). 182 of the archive's chunks: **188 MB**.
3. The DCX files are Oodle Kraken. The open decoders (ooz, both forks; oozextract) stop at the second 256 KB block:
   the archives use the "excess bytes" table mode none of them supports (Ran). The game's own `oo2core_6_win64.dll`
   (fetched from the owner's depot, 1 MB) decompressed all 51 in the owner's Windows test VM, through a 30-line x86-64
   program (`local/souls-ref/tools/oodle-win/unkrak.c`, built with the llvm-mingw toolchain); the VM folder was removed
   after.
4. SoulsFormatsNEXT (GitHub, built for .NET 8) reads the BND4 / FLVER2 / TPF: `local/souls-ref/tools/src/flverdump`
   writes each model's nodes, meshes, weights and materials, and the DDS textures. Pillow turns the DDS into PNG.
5. `local/souls-ref/scripts/er_gltf.py` writes glTF binaries: one skeleton (c0000's whole player skeleton, plus each
   part's own cloth and dummy nodes - a part carries every node, but those it does not use with no parent and no place),
   the four armour parts skinned to it, the part's albedo; x mirrored (FromSoftware's space is left-handed), weapons
   rigid in their own space. `scripts/er_sets.sh`: default (1500 + longsword), barbarian (1400 + greatsword), berserker
   (1100 + Executioner's Greataxe), cleric (1700 + mace + wooden shield), shaman (1600 + spear), ranger (1210 + dagger),
   wizard (2000 + Scepter of the All-Knowing), necromancer (1300 + Bloody Helice). 9 to 17 MB each.

Not taken: normal, metallic and blend maps (albedo only), hair, faces and bare skin (the helmets and armour cover the
figure), cloth simulation.

## C. Retargeting and drawing (`tools/godot/project/er_layer.gd`, `er_joint_map.cfg`)

- `look.er_models` = `off` (default) | `on` | `self`; `look.er_set` = an outfit folder (`--look er_models=on,er_set=cleric`,
  `app look er_models on`). The folder: `$RTA_ER_MODELS`, else `local/souls-ref/er-models` beside the staged project. If
  the outfit is not there, nothing is hidden and nothing is drawn: the game's figure as always (Ran with
  `RTA_ER_MODELS` pointing nowhere: `local/er-layer/nofolder/cmp.jpg`, the lizard drawn with the layer on).
- Each frame, before the drawer takes it: the local player's skeleton is the one whose animation state is the player
  object's (+0x114; the controls' `player` address), else the one nearest the view's player. All objects posed by that
  state are the figure (body, head, what it wears); rigid models whose own origin is within 20 units of a hand go with
  it. `RtaDrawer.set_hidden_objects` leaves their draws out (`rta_scene.cpp`).
- **The joint map.** `[joints64]` is our own table for the 64-joint player skeleton (told apart by the bind pose: z up,
  the figure's left at +x, facing -y; pelvis 1, spine 12-15, head 16, legs 2-6 / 7-11, arms 29-32 / 43-46, fingers from
  33 and 47, a cape chain 57-63). Any other person skeleton is read by itself (`_auto_table`: the pelvis is the joint two
  of whose branches go down on either side; the spine goes up to the joint the arms leave sideways; legs and arms follow
  their lowest / widest branch; the hand is where the fingers part), with the bone names of `[auto]`, and prints what it
  found. **Ran** (`app er auto`, `local/er-layer/auto/out-dump.txt`): on the 64-joint skeleton it gives every row of
  `[joints64]`, but for the finger a hand aims at (36 / 50 instead of 39 / 53).
- **The retarget.** The two bind poses are laid onto each other once: up, sides and size from head, toes and thighs
  (41.9 units a metre for the default outfit); for every mapped pair the shortest turn that lays the model's bone (toward
  its aim bone) along the game's joint (toward its aim joint) - an arm held out against an arm hanging. Each frame a
  mapped bone takes the game joint's turn since its bind pose (the game's bind pose has every joint's axes along the
  model's), applied to that aligned rest; its place comes from its parent by the model's own proportions; the pelvis is
  put where the game's is; unmapped bones (twists, fingers, cloth) follow their parents as they rest. Weapons hang on
  the model's `R_Weapon` / `L_Weapon`.
- **Drawn among the game's draws.** Every draw of the world is in Godot's transparent pass, ordered by a sorting offset
  (`RtaDrawer::place`), the game's clearing of the frame among them: an opaque figure was painted over by that clear
  (the first pictures: a sky-coloured silhouette). The figure's materials are put in the transparent pass with depth
  written, at the place of the first draw it stands in for (`get_scene_info().hidden_order`). In views without Godot's
  sun (the game's overhead view) a key and a fill light of its own, on its own layer, light it.
- Nothing reaches the simulation: the layer reads the frame and draws; the library's change is read-only.

**Pictures** (`local/er-layer/final/`, 1280 x 720 scene mode, the fight route):
`sheet-shoulder-{run,fight1..fight5}.jpg` (shoulder view: the game / its bind mesh through `Skeleton3D` / the Elden Ring
figure), `sheet-overhead-zoom.jpg` (overhead, five moments, the same three); the outfits side by side:
`local/er-layer/a8/sets.jpg`; the room: `local/er-layer/m2/pictures/er-*.png` (copy A, hub and drunare).

**The room (Ran, `local/er-layer/room10.py m2`).** room7.py of the seventh round on the r10 build: a service of our own on
127.0.0.1, two Godot portals (`portal/dev/shots.tscn`), friends, invitation, the game's character screens, Start, the hub,
drunare; copy A with `app view shoulder` and `app look er_models on` and a picture every 90 blanks, copy B as it was.
`compare.py ticks a b`: **1,851 ticks compared, no shared column differs**. (A first run, `m1`, the same: 1,818 ticks.)

## What is local only

Everything of either game: `local/souls-ref/` (the depot's files, the partial archives `er/Game/Data0.bdt` and
`Data3.bdt` - sparse, only the fetched ranges - the decrypted headers' index, `er-raw/`, `er-work/`, `er-models/`), the
patched DepotDownloader and its source, SoulsFormatsNEXT and `flverdump`, the ooz builds, `unkrak.exe`, the .NET SDK,
`local/godot-r10/`, `local/er-layer/`. Tracked: code and our own joint table only.

## Not done, and what to know

- Cloth, capes and skirts stand as they rest (no cloth simulation): on a leaning figure they stick out; outfits without
  them look best (default, cleric, wizard).
- Only the local player is replaced; other players and creatures stay the game's. The outfit is chosen by `er_set`, not
  by the character's class (the class is not read yet).
- Weapons: the model's own weapon dummy, not calibrated against the game's grip; the game's weapon is hidden by distance
  from the hand (20 units), which may miss a long weapon held at its end.
- Only albedo; the lighting is Godot's (sun in the views along the ground, an own key light overhead), not the game's
  vertex light the rest of the scene has.
- A 55-joint skeleton (seen in drunare in the room) was read with legs, spine and head but no arms; the front end's
  37-joint figure was not tried with the layer.
- Not built or run: the Linux and Windows libraries with `skeleton_export.cpp` (their builders list it); the layer's cost
  per frame was not measured (GDScript over 562 bones and 20 mapped joints a frame).
- Champions of Norrath and the other directions of the merge: not started.
