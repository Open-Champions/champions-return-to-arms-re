# Another game's figures on the game's own skeletons (the Elden Ring layer, step 1)

Started 2026-10-21. The owner's aim: Champions, Champions of Norrath (later) and an Elden Ring layer in one game. This
first step: the Godot version draws Elden Ring character, armour and weapon models in place of the local player,
driven by the game's own animation - the game decides every joint; Godot only draws - on the owner's computer only.
Everything below says **Ran** (with what was seen) or **Read**. A successor needs only this file.

## STATE

**2026-10-22, round 2** (built into `local/godot-r11/`; tests and pictures `local/er-layer/r2/`, rooms `local/er-layer/m6..m9`; not
committed): every player drawn with the layer, each in the outfit of its class and with the Elden Ring weapon of its weapon's
class on the game's own grip; normal and metal/roughness maps; capes, skirts and hair swing; the skeleton reader finds arms on
any person skeleton; the Windows and Linux libraries built with it; the layer costs about 0.3-0.45 ms a frame. Round 2 below.

| Asked | State | Shown |
|---|---|---|
| A. the game's skeletons out of the library | **done, Ran**: per drawn animated model its skeleton (parents, bind pose), its posed joints and skin matrices in the world, the bind-pose mesh with joints and weights; `rtag_skeletons_get` (optional function), `RtaMachine.get_skeletons(with_mesh)`; **round 2**: and the game's players (slot, creature, animation state, character class, Hardcore weapon class, item in hand) | the game's bind mesh re-skinned from the stream: 0.00035 units at most in C++, 0.022 through Godot's `Skeleton3D` (below) |
| B. Elden Ring models, local only | **done, Ran**: 8 outfits, 9 weapons (one per Hardcore class and a shield); **round 2**: normal and metal/roughness maps, tangents, 31 more weapon files fetched (56 MB, remembered login, no password) to find an axe, a mace, a polearm and a bow | `local/souls-ref/er-models/` (never tracked, never uploaded) |
| C. retarget and draw (`look.er_models = on`) | **done, Ran**: joint map plus the bind-pose reader; **round 2**: every player (`er_who = all`), outfit by class (`er_set = auto`), weapons by class on the game's grip, springs | `local/er-layer/r2/step1..5` |
| multiplayer unaffected | **Ran (round 2)**: two Godot portals in one room, copy A with the layer on drawing both players (shaman and berserker), copy B without: **1,828 ticks in step with the final code** (m9), 1,853 (m8), 1,807 (m7), 1,743 (m6), hub > drunare, no shared column differs | `local/er-layer/m7/pictures`, `m8.log` |

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

## Round 2 (2026-10-22): materials, weapons by class, every player, springs, arms on any skeleton, libraries, cost

Built into `local/godot-r11/` (a copy-on-write clone of r10 with `build.py snapshot --refresh`: today's `tools/recomp`, which
has the Hardcore weapons round; `lib`, `extension`, `project`). Tests: `local/er-layer/run.sh` (`OUT=local/godot-r11`; new
switches `HUB=N` a picture in the hub, `DUMP=1`, `COST=1`, `UNPACED=` for a paced run, modes like `on/shaman+er_springs=off`),
`room11.py` (room10 on r11; B takes another class: `ROOM_B_CLASS` presses right on the race-and-class page; A catches a
55-joint skeleton: `app er catch`). Pictures: `local/er-layer/r2/step1-materials` .. `step5-arms` (before | after).

**1. Materials (Ran).** The FLVER materials name their maps by the part (`<MODEL>_a`, `_n`, `_m`; the TPFs were already
extracted to PNG). Read from them (Ran, 5 parts): `_n` holds the normal's x, y in R, G and a gloss in B (high on the metal,
where `_m` is high: BD_M_1500 metal 115 against cloth 16), `_m` is a grey metalness. `scripts/er_gltf.py` now writes per
material a normal map (green turned to glTF's up, z rebuilt), a metal/roughness map (G = 1 - gloss, B = metalness; JPEG,
at most 1024 a side; `ER_MAP_SIDE`), and per-vertex tangents; fur shells (`*fur*` materials, stacked copies the game's fur
shader draws) are left out - drawn plainly they were the shaman's "shards". +3 MB an outfit. In Godot a full-strength metal
map read black (the scene is drawn by the game's own shaders, there are no reflections of Godot's to show), so the layer
takes `look.er_metal` (0.5) of it. Seen in two levels and both views: `step1-materials/{hub,valor}-{shoulder,overhead}.jpg`
(before: the same models built with `ER_FLAT=1`, albedo only). The difference is in the metal parts (chain mail, helm, pauldrons
take relief and highlights); cloth changes little.

**2. Weapons (Ran).** The library now hands over the game's players (`rtag_skeletons::players`, filled on the game's thread
with the poses): slot, creature (record +0x43d8), animation state (+0x114), character class (record +0x50) and the weapon
class by the Hardcore mode's own rule (`soulscombat::weapon_class_in_hand`, new: read only, whether or not the mode is on).
The weapon in hand is drawn as rigid pieces **of its bearer's own object** (not an object of its own: the r10 search by object
found nothing and hid the weapon with the body), their matrix at a hand joint: the game's attach point. Its own long and side
axes are read once per weapon from its bind-pose vertices (Ran: through its matrix they are the drawn corners within 0.0001
units). The Elden Ring weapon of the class (`er-models/weapons/<class>.glb`, its axes in `<class>.json`) is turned so its
long and side axes lie along the game weapon's, its grip put where the game's grip is, measured from the figure's own hand
(`[weapons]` of the joint map: a shift along the weapon and a size, our own numbers). Classes -> models, chosen by looking at
40 weapon models' shapes (the model numbers are not the weapon numbers: 1100 and 1111 are twinblades, 1508 a crossbow, 1601 a
glaive): dagger 0100, sword 0200, axe 0700, mace 0800, great weapon 0300, spear 1001 (a halberd), staff 3000, bow 1401, shield
2101. Ran: the shaman's mace and the berserker's axe (and a bow when B changed weapons) on their grips, through swings:
`step2-weapons/valor-fight{1,3}.jpg` (game | r1 | now), `step3-outfits/room-*.jpg`.

**3. Outfit by class, every player (Ran).** `look.er_set = auto` (default): record class 0 barbarian, 1 cleric, 2
shadowknight -> necromancer, 3 ranger, 4 wizard, 5 berserker, 6 shaman; a name for everyone otherwise. `look.er_who = all`
(default) | `me`. A player's figure is the skeleton posed by its animation state; this machine's own player in a net game is
drawn from its prediction copy, so the local slot takes the skeleton the controls name. Two builds of 64 joints exist
(shaman and berserker: Ran, different joint orders): `[joints64]` is used only when its head and hips are where the reader
finds them, else the skeleton is read by itself. Ran in a room: both players drawn on A (shaman with the mace, berserker with
the axe), B without the layer, in step (above): `step3-outfits/room-{0090,0180,0270,drunare-1}.jpg` (r10: only the local
player, default outfit | now). All eight outfits on one pose: `local/er-layer/r2/sets/`.

**4. Capes and skirts (Ran).** The converter took cloth bones from a part that does not use them (no parent, no place): they
hung from nothing and moved rigidly with the pelvis. Now the part that uses a node gives its parent and place (the capes hang
from the spine, the skirts from the thighs, chains of up to four), and `figure.json` names the bones that swing (cloth, mantle,
cape, cloak, skirt, hair, hood) with the centre of what each carries. Godot's SpringBoneSimulator3D works on a Skeleton3D node;
the layer poses through the RenderingServer, so the springs are our own: per bone a weight at that centre, pulled toward where
the pose puts it (140/s^2), gravity, damping 0.86 a frame, at most 1 radian from the pose; the bone turns toward it; children
follow. Presentation only (`look.er_springs = off` turns them off). `step4-springs/{run,fight1,fight3,fight5}.jpg` (berserker's
wings, off | on).

**5. Arms on any skeleton (Ran).** The bind-pose reader (`_auto_table`) now follows the branch that reaches farthest (a
twist or elbow helper may stick out further sideways than the hand) and reads hand, elbow and shoulder from lengths along the
chain (hand about 78 % along, fingers past it; elbow halfway; a short first link a clavicle). Ran on the two real 64-joint
builds (unchanged results), on synthetic variants (no clavicle; mittens) and on the real 55-joint skeleton caught in drunare:
**clavicle, upper arm, forearm and hand on both sides (17-18 joints mapped, against 10)**. That 55-joint figure is a figure
of drunare's cut scene (state 0x62b1d4, no player's), which r10 and the first round-2 rooms drew in the local player's outfit
because the "nearest skeleton" guess took it: the local slot now needs the skeleton the controls name (Ran, m9: the
cut-scene figure caught again, not drawn as a player).
`step5-arms/catch55-drunare.jpg`.

**Libraries (built).** Windows x86-64 (`build_lib_win.py`, clang for mingw: 41 files, `local/godot-r11/windows/librta_game.dll`,
71 functions, Windows' own DLLs) and Linux aarch64 (`build_lib_linux.py --arch arm64` in the container: 39 files,
`linux/aarch64/librta_game.so`, its load test passes); both link `skeleton_export.cpp` with `soulscombat::weapon_class_in_hand`.
Not run on those systems.

**Cost (Ran, paced, 3024 x 1964 - the display's resolution - shoulder view, the fight route).** The layer's own time a frame
with one figure drawn: **0.31 ms mean in valor's walk and fight, 0.45 ms in the boar fight (worst 0.6 ms)**: get_skeletons
0.05-0.1, finding the players and their weapons 0.1, posing (about 100 bones) and drawing 0.06-0.12; once 183 ms when an
outfit is loaded (the glTF read). Pictures a second 58.1 with the layer against 58.2 without (the route's own pacing).
`local/er-layer/r2/cost-{off,on}/`. (A first measure gave 13 ms: the weapon's one-time request for the meshes was never
cleared, so every frame asked for them; and `get_skeletons` now leaves out the skin matrices and the matrices of pieces that
are not rigid models unless the meshes are asked for.)

**Changed (tracked):** `tools/godot/lib/rtag.h` (`rtag_skeleton_player`, `rtag_skeletons::player_count/players`, appended;
an older host's shorter structure is still served), `rtag.cpp`, `skeleton_export.{h,cpp}` (the players at each draw pass),
`tools/recomp/app/soulscombat.{h,cpp}` (`weapon_class_in_hand`), `tools/godot/extension/src/rta_machine.cpp` (`players`;
lighter dictionary), `tools/godot/project/er_layer.gd` (rewritten: models per outfit, figures per player, weapons, springs,
reader), `er_joint_map.cfg` (`[weapons]`, `[joints64]` only for its build), `scene_view.gd` (`er_set = auto`, `er_who`,
`er_springs`, `er_metal`). Local: `souls-ref/scripts/er_gltf.py` (maps, tangents, cloth parents, `figure.json`, weapons
mode, skin joints only those used plus the mapped ones), `er_sets.sh`.

## What is local only

Everything of either game: `local/souls-ref/` (the depot's files, the partial archives `er/Game/Data0.bdt` and
`Data3.bdt` - sparse, only the fetched ranges - the decrypted headers' index, `er-raw/`, `er-work/`, `er-models/`), the
patched DepotDownloader and its source, SoulsFormatsNEXT and `flverdump`, the ooz builds, `unkrak.exe`, the .NET SDK,
`local/godot-r10/`, `local/godot-r11/`, `local/er-layer/`, the Windows test machine's scratch folder (removed after each
decompression). Tracked: code and our own joint table only.

## Not done, and what to know

- Cloth is springs of our own, not the game's cloth simulation: no collision with the body (a cape can pass through a leg).
- Creatures and other people of a level stay the game's; faces, hair and bare skin are not drawn (the helmets cover them).
- Metal shows only half its strength (`er_metal`): the scene has no reflections of Godot's. The figure is drawn over
  see-through leaves in the overhead view (it is placed in the draw order at its first hidden draw).
- A shield drawn by the game as an object of its own (not of its bearer's) would not be found (only the bearer's own rigid
  pieces count, so loot passing a hand is not taken; no shield was held in the runs). Bows: a bow was found on the berserker's right hand after a
  weapon swap and drawn there (m7); in m9 its class was bow with nothing found at its hands at the moment of the info line
  (the bow not drawn at a hand then, or held otherwise) - not looked into.
- Weapon pairing per class is by shape (model numbers are not weapon numbers); the `[weapons]` shifts are 0 (grip on grip
  looked right in the pictures).
- The 37-joint front-end figure was not tried. Windows and Linux libraries built, not run there.
- Champions of Norrath and the other directions of the merge: not started.
