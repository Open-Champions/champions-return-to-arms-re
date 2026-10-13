# Graphics for the native build

Started 2026-10-12. The native build of Champions: Return to Arms (SLUS-20973 v2.00) -
the game's code translated to C++ (`docs/issues/native-recomp.md`), our renderer
(`docs/issues/native-render.md`), one window (`docs/issues/native-app.md`) - drew the
console's picture, only larger. This is what a player expects on top of that: widescreen,
any resolution with clean edges, filtered textures with mip maps, the enlarged-art pack,
and settings for all of it. Every statement says whether it was **Ran** (with what was
seen) or only **Read**; "Left" at the end lists what was not reached.

The machine was loaded the whole time (art-enlarging job on the graphics card, emulator
tours, other agents' builds and tests): load average 230 to 510 on 18 cores. Every figure
has the load beside it. Pictures are game output and stay under `local/recomp-gfx/out/`.

## Where things are

| What | Where | In the repository? |
|---|---|---|
| the game side of widescreen: hooks on the game's own view functions, marks for the 2-D layer | `tools/recomp/app/gfx_rt.h`, `gfx_rt.cpp`; 16 addresses in `tools/recomp/hle.txt`; two hook points in `rt/rt.h`, `rt/runtime.cpp` | yes |
| the 2-D layer of a wide picture | `tools/recomp/render/layout.h` | yes |
| replacement pictures, mip-mapped parts, the readers | `tools/recomp/render/texpack.h`, `texpack.cpp` | yes |
| the emulator build's texture names | `tools/recomp/render/xxh3_64.h`, `Gs::name_texture` in `gs.cpp` | yes |
| settings file | `tools/recomp/app/settings.h` | yes |
| changes to the files other work was going on in | `tools/recomp/render/gfx.patch` (to apply: section 7) | yes |
| my copy of the sources, builds, pictures, rig logs, memory images | `local/recomp-gfx/` (`src`, `base`, `merged`, `out`) | no |

## State (2026-10-12)

- **Ran:** 16:9, 16:10, 21:9 and 32:9 from the same camera with the vertical field of view
  kept; everything the game culls by the view is culled by the wide view; HUD at its
  edge, menus and text centred at their 4:3 size, nothing stretched.
- **Ran:** the simulation in widescreen against the emulator rig, tick for tick: every
  simulation value identical; the only bytes of the object pool that differ from a 4:3 run
  are animation-cache pointers (section 1.3).
- **Ran:** drawing size independent of the window; multisampling of the 3-D surface with
  4 and 8 samples (2 is the same code and was not run); mip maps and anisotropic filtering for the game's own textures; the two-line
  hop of HUD text between fields removed.
- **Ran:** the art pack by the emulator build's names: 183 of 185 textures of the first
  level found in the 4x pack at the first try, drawn as parts with mip maps, the same
  screens beside the emulator build with the same pack.
- **Ran:** the settings file (written with its defaults and read back; a file with seven
  keys and one unknown line, with one key overridden on the command line: each took
  effect, the unknown line was reported) and the command line. **Not run:** `frame_cap =
  30` (60 and 0 were).
- **Ran:** a window that changes its shape (`app window W H` in a small test window:
  480 x 270, 640 x 240, 400 x 300): the view follows, nothing is stretched on the way.
- **Not shown:** full screen (a test window must not cover the screen: the toggle is the
  code that was there, and the view follows the window's shape through the path that
  was run by resizing); two players on one machine (no script reaches it: the screen clamp
  was never called in any run); a figure for frames a second on a free machine.

**State of the hand-over (15:50).** `tools/recomp/render/gfx.patch` is against the shared
sources as they stood at 15:43; applied to them it gives, file for file, the tree that was
built here in both flavours (`rta_app` with the films and the network of the other work,
`rta_app_orig`) and applies without a reject (dry run on a copy; the shared files
themselves were not touched). What was run on which sources: the comparisons of section
1.3 and the 21:9 pictures on the merge with the 15:26 sources; the film at 4:3, the
settings file and a last run from power-on to the first level (16:9, 2x pack) on the
merge with the 15:39 sources; one picture of the first level on the 15:43 merge;
everything else on my copy before any merge. The other work touched `gs.cpp`,
`backend_gl.cpp`, `backend.h`, `app_main.cpp` and `app/build.py` three times in that
hour: if a hunk fails later, the places where the two works met are listed at the head of
the patch.

## 1. Widescreen

### 1.1 How: the game makes the wide view

The renderer does not widen anything. The game's own view code is given another shape:

| Game function | What is changed | Hook |
|---|---|---|
| `mat4_setProjection` 0x165950, `mat4_setProjectionVu` 0x1659d0, `mat4_setProjectionVu2` 0x165a70 (sx, sy, scale, ...) | sx x k, k = (4/3) / aspect. Every caller is a view projection with sx = 1, sy = 0.4667, scale = `g_projScale`: `camera_setView` 0x18a2b0 (the three view-projection matrices), `particle_draw` 0x194a08, the model drawer 0x175dec | `fn_00165950` ... in `app/gfx_rt.cpp` |
| `camera_setProjection` 0x18619c (fov, aspect, fov2, v) | aspect / k (the game passes 1.33). It builds the two sets of frustum planes: the view's (with one degree to spare) and an 80-degree set that decides whether a mesh needs the vertex program's clip rejection | `fn_0018619c` |

So `sx = F k x / z`: the unchanged 1280 x 448 buffer holds a picture of the wide view,
squeezed, and is shown at the wide shape. Nothing else in the game is touched: its
buffer, its scissor, its guard band of 1000 pixels (`docs/spec/render-pipeline.md` 4.5)
and every test it makes in pixels of the buffer keep their meaning, because the planes
are widened by exactly what the projection is narrowed. With the aspect at 4:3 every hook
is the plain call of the original (k = 1 is tested first).

The aspect is taken once per frame at `gfx_beginFrame` (`rt_frame_hook`). When it changes
(the window is resized) the planes are rebuilt with the last arguments of
`camera_setProjection` and the three matrices rescaled, so a view that is not rebuilt
every frame follows at once.

### 1.2 What culls or loads by the view (Read, then Ran)

Found with `tools/gxref.py` on the plane sets (camera space 0x7d5bc0 and 0x7d5c68; world
space 0x44f0a8 and 0x7d5c08, made by `camera_buildFrustum` 0x1863fc), on `g_projScale`
0x44f108 and on the three matrices, and by listing the callers of the two box tests:

| Reader | What it decides | In widescreen |
|---|---|---|
| `world_draw` 0x189870 -> `frustum_testBox` 0x1868a4 (3 calls), 0x1869f0 | which level chunks and water tiles are drawn; clip flag | wide planes |
| `world_drawObjects` 0x14b168 -> the same two tests | the walk over the object grid (cells of 256 units, split in halves, each tested as a box from the camera's height to 840 below it) and each object's box | wide planes |
| `world_touchTexturesInView` 0x189df0 | textures loaded ahead for a cutscene's next shot | wide planes |
| `decal_drawTask` 0x19f4e8 | floor decals | wide planes |
| the vertex programs | triangles with a vertex more than 1000 pixels from the centre are dropped; particles outside +-800 x +-400 | in pixels of the squeezed buffer: unchanged in meaning |
| `glow_draw`, `line_draw`, `particle_drawHaze`, `model_drawShadow`, the name and prompt drawers (`Player_draw`, `NPC_draw`, `FlyingText_draw`, ...) | project on the CPU with `g_viewProj` and test against the buffer | follow by themselves |
| lights | chosen per chunk and per model by distance, not by the view; the lights that are objects (torches, lamps) are drawn, and linked, by the object walk | wide planes |
| texture cells (`<LEVEL>.TEX`, 720 units square) | the 3 x 3 cells round the camera focus are kept loaded (0x17d830): **not** by the view | enough up to about 2.7:1 (the far corners of the screen are 720 units to the side there); at 32:9 a chunk at the far edge can lie in a cell that is not loaded. Not seen in the first level at 32:9 (it is small) |
| the display list | the object walk stops drawing when fewer than 3000 of its 35,000 units are left; a wide view draws more | figure in the report: "the fullest frame took N of 35000 units" - section 5 |

What the widening adds is in the pictures: `ws-169-nocull-120.png` (wide projection, the
game's 4:3 planes: `--opt wide-cull=off`) has a wedge of sky where ground belongs at the
right edge and a missing piece at the lower left; `ws-169-120.png` is whole.

### 1.3 What the simulation sees (the comparison)

**Readers of the view inside the simulation - found (Read):**

- `game_buildScreenEdgePlanes` 0x1e71b0, called by `Player_clampToScreen` 0x1b3d90 and by
  0x1be968 (skills): with two or more players alive on one machine (never in a net game:
  both callers test `g_networkMode`) a player cannot walk out of the view. It reads the
  four side planes at 0x44f0a8. **Handled:** a 4:3 set of world planes is kept beside the
  wide one - made by the game's own `camera_buildFrustum` from the 4:3 camera-space set
  its own `camera_setProjection` made, so they are the bytes the unchanged game would
  hold - and put in place for the length of that call. Two players on a wide screen are
  therefore held inside the middle 4:3 of it, as before. `--opt wide-clamp=screen` lets
  the clamp follow the screen: that changes the simulation of an offline two-player game
  and is off by default. **Not run:** no script has two players; the report counts the
  calls (0 in every run here).
- `hud_addGoldFloater` 0x1dc268 is called from simulation code (a gold pickup) and
  projects the place with `g_viewProj`. It writes the floater's screen position and its
  "off screen" byte (0x86a900 + 0x24 i), which only `hud_drawGold` reads; the gold is
  credited by ticks (`hud_tickGold` 0x1dcb80: `(tick - start) x 3 > 0x7f`), whatever the
  position. Draw-only.
- Nothing else reads the planes or the matrices outside drawing: the other readers are the
  drawers in the table above (list: `gxref.py SLUS_209.73 44f0a8 7d5c08 7d5bc0 7d5c68
  44f108 44f140 44f180 44f1c0`).
- **Activity is not the screen.** `obj_updateActive` 0x14db08 asks for the distance to a
  player (600 units for a creature; the camera focus only during a cutscene of a net
  game, FINDINGS D6) and `isNearView` is a square round the players. Neither reads the
  projection, so widescreen does not change who is awake - and for the same reason a
  wide enough screen shows things that are asleep. The corner of the visible ground is
  this far from the player (camera distance 340 / 450 and pitch 55 / 66 degrees at zoom
  1 / 2, `docs/spec/movement-camera.md`):

  | Shape | zoom 1 | zoom 2 (far) |
  |---|---|---|
  | 4:3 | 430 | 461 |
  | 16:10 | 480 | 520 |
  | 16:9 | 513 | 557 |
  | 21:9 (2.37) | 634 | 697 |
  | 32:9 | 894 | 993 |

  Up to 16:9 everything on screen is inside the 600. At 21:9 the two far corners are
  outside it, at 32:9 the outer quarters: a creature standing there does not move until
  the player comes nearer. **Handled by leaving it:** making them wake would change the
  simulation (a larger radius on one machine is a desync in a net game), and nothing on
  the draw side can animate them truthfully. It is the price of a shape the game was not
  made for and is said here, not hidden.
- **Drawing reaches the simulation in the ways the project already knows**, and widescreen
  only changes which objects are drawn on this machine - which differs between the
  machines of a net game anyway, every player having a camera of their own (FINDINGS
  D13). The known routes - the status counters `Creature_draw` counts down (D12 to D16),
  the handle nodes every drawn light takes (D31), the pose cache (D34), the lights that
  run only where they were drawn - are as open or closed with widescreen as without.

**The comparison (Ran).** `tools/recomp/rigcompare.py boot-native --replay`, script
`fight3.rig` (power-on, front end, character creation, first level, level change to
`valor`, a fight with boars), the unpatched translation with the hooks linked
(`rta_app_orig`), picture drawn off screen at 16:9 and at 64:27 (2.37:1, "21:9"),
against the rig's log of the original (`boot-compare`). Load average 250 to 510. The table
is the runs of the sources as merged with the other work at 15:26; the runs before the
merge gave the same lines, down to the same pool CRCs.

| | 4:3 (the same binary) | 16:9 | 2.37:1 |
|---|---|---|---|
| front end, 1,383 ticks | all simulation columns identical | the same; pool differs from tick 258 | the same; pool differs from tick 1 |
| first level, 99 ticks | identical but for the player record at tick 7 | the same one tick; pool differs | as 16:9 |
| `valor`, 5,410 ticks (5,899 in the runs that wrote memory) | identical; pool differs in ticks 3,886 to 3,912 | sim, seed, position, angle, state, object seed, hit points, mana, gold, experience, bag, statistics, equipment, abilities, skills, the whole player record, task table, pads: **identical at every tick**; pool differs | the same columns identical at every tick; pool differs |
| displayed frames at the first tick of `valor` | 3,401 | 3,402 | 3,402 |
| cosmetic seed | as in `native-app.md` | differs from the first level on | as 16:9 |

The 4:3 run is the control: it gives exactly the result `docs/issues/native-app.md` has
for the build without the hooks, the two unexplained differences included.

"Pool" is one CRC over the 947,968 bytes of the object pool, so "differs" needed looking
at. Both runs were made again writing main memory at the same ticks (first level tick
60; `valor` ticks 1500, 2701, 3905 - in the fight - and 5300), and the 16:9 image
compared with the 4:3 one byte for byte (`local/recomp-gfx/out/work/pooldiff.py`):

| Tick | Live objects | Pool bytes that differ, 16:9 / 2.37:1 | Where (both shapes) |
|---|---|---|---|
| first level 60 | 18 | 25 / 28 | +0x114 and +0x120 of 3 `Critter`, 1 `NPC`, the `Player`; +0x98, +0xa4 of the `RingPortal` |
| `valor` 1500 | 197 | 4 / 4 | `Player` +0x114, +0x120 |
| `valor` 2701 | 210 | 29 / 35 | `Player` and 3 `WarBoar`: +0x114, +0x120, +0x140, +0x160, +0x180, +0x1a0 |
| `valor` 3905 | 211 | 44 / 48 | `Player`, 4 `WarBoar`: the same offsets |
| `valor` 5300 | 211 | 41 / 42 | `Player`, 3 `WarBoar`: the same offsets |

+0x114 is the animation state, whose first word is the pointer to its pose buffer;
+0x120 + 0x20 n is word 4 of track n, the pointer to its decoder slot
(`docs/issues/pose-cache.md` section 2, `docs/engine.md` "decoder slot"). Both are
handles into caches that drawing fills: with more objects drawn the buffers are handed
out in another order. (The portal's two words were not looked up; it is a prop with no
run of its own that matters here.) **No position, hit point, state, timer, status counter
or generator of any object differs** at any of the five ticks.

Outside the pool the two images differ where they must: the display lists (62,000 to
76,000 bytes), the planes and the three matrices, the cosmetic seed, the counters of
drawn frames, the pose buffers and decoder slots themselves (0x791ec0 on), the texture
streaming slots and the cell data they hold (5.1 MB of heap: the cells are read over
several drawn frames, and the two runs draw a different number of frames per tick), sound
state, three bytes of the save buffer (the time of day in the save made at boot), stack
leftovers. These were looked at by region and symbol, not word by word.

So: in this session widescreen changed nothing the simulation computes. What is **not**
shown: a session with two players (the clamp), a net game on two machines with different
shapes (the argument above says it is the case of two cameras; no run), levels with the
draw-dependent lights (D31) or creatures under the status counters of D12.

### 1.4 The 2-D layer

The game places its 2-D layer in a 640 x 448 layout, at X = 2x + 1408 of the buffer, and
some things in the 3-D scene in pixels too. Shown wide, all of that would be 1 / k times
too broad (`ws-169-nolayout-120.png`: `--no-layout`). `render/layout.h` moves the
vertices of such primitives in the GS model, by what they are:

| What | Known by | Becomes |
|---|---|---|
| 3-D geometry | kicked by VU1, not a sprite | untouched |
| particles | sprites kicked by VU1 (2,521,389 in the fight session) | narrowed by k about their own centre |
| glows, other depth-tested sprites built on the CPU | path 1, depth test other than "always" | narrowed about their own centre |
| menus, text, dialogue, message boxes, the title's logo | built on the CPU, depth test "always" | scaled by k about the middle of the screen: the 4:3 layout, centred |
| fades, the letterbox, the pause menu's bottom strip, the 20 columns the game clears its buffers with | plain and across the whole width, or a plain column of the whole height | untouched |
| a film | a picture (textured) across the whole width | like a menu: 4:3 in the middle, black beside it (`shots-film/b11-film-a.png`, 21:9; it was stretched across before this rule) |
| the present pass, the shadow surface, the heat haze's copy | not drawn into the 1280-wide buffer, or textured with a surface | untouched |

and by who made the packet. The hooks note the range of the display list each of a few
draw functions fills, and when the runtime walks the list for VIF1 it puts a NOP code
(NUM 0xA5, the kind and a running number in the immediate; 0xA6 / 0xA7 carry k itself,
so a frame's picture and its layout always agree, also in a recorded stream) in front of
the DMA tag where the range begins:

| Kind | Functions | Becomes |
|---|---|---|
| EDGE | `hud_drawPlayerStatus` 0x1d9cd4, `hud_drawGold` 0x1dc708, `hud_drawCompass` 0x1df720, `minimap_draw` 0x1e42e0, `hud_spellSelect` 0x1dd270 | what one call draws is split into clusters along x (gaps over 32 layout pixels); a cluster whose middle is in the left third keeps its distance to the left edge, one in the right third to the right edge, the rest stays centred. The player's name, bars, frame and level badge are one cluster |
| WORLD | `world_drawObjects` 0x14b168 (names over heads, floating numbers, prompts) | each cluster narrowed about its own middle: the place is the projection's |
| BILLBOARD | `glow_draw` 0x1907d0, `particle_drawHaze` 0x18fe18 | each sprite, strip or fan narrowed about its own middle |
| MENU3D | `inventory_drawTask` 0x1c1108, `stats_task` 0x1d1bc0 | the figure is projected 4:3 (k is not applied inside these tasks) and all of it centred like the menu round it |

A scissor round 2-D things (the bars are cut to their length by one) moves with them.

**Ran** (pictures in `local/recomp-gfx/out/app-test/shots-169/`, 1280 x 720, from power-on):
memory-card boxes, the title (logo and menu centred, the 3-D backdrop wide), the four
front-end menus, character creation (the text panel and the figure keep their distance:
both are measured from the middle), the first level (HUD at the left edge), the pause
menu (box centred, its bottom strip across), the load screen, a cutscene (letterbox
across), the fight; at 21:9 with the fix-set build as merged with the films and the
network (`shots-219/`): the publisher's logo, both films, title, menus, character
creation, first level. **Not seen:** the inventory (MENU3D), the compass and the map
(EDGE), a second player's status at the right edge, names over heads (WORLD): no script
opens them; trails (their width is made in the vertex program, doubled in x for the
buffer, and is 1 / k too broad across the screen - not corrected).

## 2. Resolution and edges

- **The size the picture is drawn at is its own** (`resolution`): the window's pixels, a
  size, or a factor of the console's lines. The 3-D scene is drawn at that size - it
  never exists at 1280 x 448 - and the finished picture is scaled to the window with the
  view's shape. A size larger than the window is supersampling (exactly twice is a 2 x 2
  box through the linear filter).
- **Multisampling** (`antialiasing` 2, 4, 8): the 3-D surface gets a multisampled colour
  and depth buffer and is resolved before anything reads it (the present pass, the heat
  haze's copy, a picture written to a file). The display buffers and the shadow surface
  have none. Texture coordinates and colours are taken at the centroid, or the pixels on
  a triangle's edge read past the part of the page the triangle uses.
  Pictures: `cmp-aa-4k.png` (3840 x 2160: the stairs on the platform's rim and the
  character's outline without, smooth with 4 samples).
- **Mip maps and anisotropic filtering for the game's own textures** (`mipmaps`,
  `anisotropy`). The game has no mip maps, and its level textures are pages of which a
  chunk uses a corner with a margin of 3 texels, so mip maps of the page would bleed its
  other pictures into the corner. For every texture the 3-D scene filters, the backend
  gathers the rectangle of texels its triangles use and makes a texture of its own of
  that part plus 4 texels, with mip maps made from the part alone, clamped at its
  border; a draw that goes beyond the part gets the game's texture until the larger part
  is made, and after two such times the whole is taken. Textures that repeat and
  textures drawn by sprites are held whole. 154 parts in the first level, 6 made again.
  The shader takes the mip level from the coordinate before the weave and the region
  wraps break it up (`textureGrad`).
- **No interlace artefacts.** Three things. The half-line of `XYOFFSET` was already
  dropped and interface art already woven from its two fields. Found now: **HUD text and
  one bar hopped by two lines sixty times a second.** The game draws one field per frame:
  in the frames of the display's even lines it reads its art a quarter texel in, in the
  others from the row itself; an element whose top is on an odd line of the 448 is drawn
  from its second field two lines lower in the one kind of frame and from its first field
  in the other. Woven, the whole picture was drawn at the sprite's place in both - a line
  too low and a line too high in turn. Now the woven picture stands where the element is
  on the screen (`gs.cpp`, the field sprite: one line up for "quarter and second field",
  one line down for "row and first field"). Two consecutive pictures of the HUD: 3,463
  of 73,600 pixels differed by more than 40 of 255 before, 136 after (butterflies
  behind it). `hop-before-pair.png`, `hop-after-pair.png`. `RTA_GS_FIELD_HOP=1` gives the
  old behaviour for comparing.
- **Frame cap and pacing** (`frame_cap`): the pacing of `native-app.md` is unchanged - one
  picture per 1/60 s, on the display's refresh when its rate is a multiple of 60, by the
  clock otherwise. 30 shows every other picture (the game still makes all sixty: its
  simulation counts frames); 0 is no cap and no pacing, the game then runs as fast as
  the machine (for measuring). The simulation rate is not touched.

## 3. The art pack

**Names.** The emulator build knows a texture by a figure of the bytes the game sent, a
figure of its palette, its format and the size of what was sent
(`tools/play-net/README.md`, "Texture dump and replacement"). The native renderer knew
textures by a hash of its own. `Gs::name_texture` works the emulator build's name out
from the same upload, when a texture is made and a pack is set:

- the figure chains XXH3-64 over the pieces of the upload as `RecordUpload` does: (figure
  so far, y and x, height and width, XXH3 of the piece's bytes, buffer width and format
  it was sent in); once more with the texture's buffer width and format when the bytes
  are read as another format (8-bit texels sent as 32-bit pixels of half the buffer width
  count as their own);
- a piece in another format or buffer width, or one lying over an earlier piece, starts a
  new upload, as there;
- the palette figure is XXH3 of the 16 or 256 colours in index order;
- the size is the piece itself for one piece from the corner in the texture's format;
  otherwise the pieces are written, all ones, into a scratch GS memory in the format they
  were sent in and read back in the texture's: the smallest rectangle from the corner
  that holds every covered texel. If no file of that size is in the pack the size `TEX0`
  names is tried (how the emulator build knows a texture that is only drawn clamped).

XXH3 is written out in `render/xxh3_64.h` (plain C++, from the published description).
**Ran:** against the library itself (the `xxhash.h` of the emulator's checkout, used for
the test only) for every length from 0 to 2,000 bytes and thirteen up to 1 MB: 2,014
lengths, 0 differ; the library's streaming digest equals the one-shot figure.

**Found (Ran):** first level, 4x pack (`local/hd-pack`, 54,829 files then; it grows while
the enlarging job runs): 185 textures made, **183 found in the pack**. From power-on to
the first level through every menu: figures in section 5. Heaviest level (`shame1`): 348
made, 307 found (the pack is not complete for that level).

**Reading and holding** (`render/texpack.cpp`, `backend_gl.cpp`): the folder is listed
once; a file is read when its texture is first drawn, by three threads of low priority,
and until it is there the game's texture is drawn; at most 24 MB a frame go to the
graphics card. Only the part that is drawn with is handed over, with mip maps of its
own - the same machinery as section 2, and the rule of the emulator build: pictures drawn
by sprites, pictures that repeat, files that are not a whole multiple of the game's
picture and parts of nine tenths or more are held whole; a draw beyond the part reads
the picture again, twice at most. `art_memory` megabytes may be held; beyond it pictures
not drawn with for ten seconds go, the longest unused first; a picture asked for and not
drawn with for two seconds is given up unread. First level at 4x: 184 pictures, 384 MB
with their mip maps (165 as parts; the emulator build holds 603 MB for 256 pictures on
the same screen).

**Two-field interface pictures.** `upscale.py` writes the woven, enlarged picture twice
into a file of twice the vertical factor. Such a file is known by exactly that (factor
in y = 2 x factor in x) and held whole; where the renderer weaves, the shader takes the
woven line itself as the coordinate into the first copy. The HUD frame, the fonts, the
title's logo and the menu art come out whole, no comb.

**Beside the emulator build (Ran).** The same script (`boot-shots.rig`) in the emulator
build with the pack (`--rta-test`, silent, quit afterwards; `shotfb`, 2560 x 892, lines
doubled for looking) and in the native build with the pack at 4:3, 2560 x 1792:
`cmp-emu-title.png`, `cmp-emu-create.png`, `cmp-emu-hub.png`. Section 5 has the figures.

## 4. Settings

`<data>/settings.txt` (written with its defaults at the first start somebody plays;
`--settings FILE` for another, `--no-settings` for none), then the command line. The
keys, each also an option (`tools/recomp/app/settings.h`):

| Key / option | Values | Default |
|---|---|---|
| `window` / `--window WxH` | points | 960x720 |
| `fullscreen` / `--fullscreen` | yes, no; F or F11 switches while running, Escape leaves | no |
| `aspect` / `--aspect` | `auto` (the window's shape), `4:3`, `16:9`, `16:10`, `21:9`, any W:H from 4:3 to 4:1 | auto |
| `resolution` / `--resolution` (`--size`, `--scale` as before) | `window`, `WxH`, `Nx` | window |
| `antialiasing` / `--antialiasing` | off, 2, 4, 8 | 4 |
| `anisotropy` / `--anisotropy` | 1 (off) to 16 | 16 |
| `mipmaps` / `--mipmaps` | yes, no | yes |
| `art_pack` / `--art-pack DIR` | a pack folder (its `replace` subfolder is found) | none |
| `art_memory` / `--art-memory MB` | | 3072 |
| `frame_cap` / `--frame-cap` (`--unpaced` = 0) | 60, 30, 0 | 60 |

`--plain` switches everything off (4:3, no multisampling, no mip maps, no pack): the
picture as before this work, for comparing with the emulator. A narrower shape than 4:3
is not made wider than the game: the picture gets bars.

Script commands for tests: `app window W H` (resize), `app fullscreen`, `app art off|on`
(the same frame with and without the pack and the mip-mapped parts).

**Defaults changed for everybody**: a run without options is now `aspect = auto`, 4
samples, anisotropy 16, mip maps. A window of 960 x 720 is 4:3, so the view is the
console's until the window is made wider.

## 5. Measurements (Ran, on a machine that was never free)

**What can and cannot be said.** With a load average of 220 to 510 on 18 cores a thread
waits for a core most of the time, the graphics card is shared with the enlarging job, and
frames a second measure the neighbours: the same level at the same size gave 30.2
pictures a second with everything on (load 221) and 8.1 with everything off (load 360)
ten minutes later. What does not depend on the neighbours is processor time and memory.
For the build without this work, `docs/issues/native-render.md` has 104 to 118 pictures a
second at 2560 x 1792 at load 20; a figure for 4K on a free machine is **left**.

Heaviest level by art (`shame1`, 1,089 pictures in the emulator build's count), from
power-on by script, standing at its start, 16:9, fix-set build, no window, not paced,
1,200 pictures counted after the level had settled:

| | 3840 x 2160, 4 samples, anisotropy 16, mip maps, 4x pack | 3840 x 2160, `--plain` | 1280 x 720, all on, 4x pack |
|---|---|---|---|
| pictures a second (wall) | 30.2 | 8.1 | 27.9 |
| load average during it | 221 | 360 | 242 |
| processor time per picture, all threads | 11.3 ms | 12.4 ms | 12.8 ms |
| of it the decoder (VIF1, VU1, GS model) | 6.3 ms | 7.3 ms | 7.4 ms |
| main thread in OpenGL per picture (wall, no `glFinish`) | 2.1 ms | 2.5 ms | 1.8 ms |
| memory of the process at the end | 1,478 MB | 713 MB | 1,100 MB |
| replacement pictures held: most at one time / at that place | 605 MB / 64 MB (68 pictures) | - | 432 MB / 64 MB |
| textures named / found in the pack | 348 / 307 | - | 348 / 307 |

So the settings cost no processor time that shows (the differences are inside the
noise), and about 765 MB of memory at 4K: the multisampled surface (3840 x 2160 x 4
samples of colour and of depth, 265 MB, and its resolved copy) and the pictures. The start
of `shame1` is a small dark room; the level's weight is in its 1,089 pictures, of which
the walk there never has more than 68 in view. A tour of the level with the camera, as
the emulator build was measured (3.4 GB with everything kept), was not made.

The renderer alone on a recorded stream of the fight in `valor` (40 pictures at 16:9,
137,000 vertices and 338 commands each, played six times by `rta_replay` at 3840 x 2160
with `glFinish` after every picture):

| | decoder, processor time | OpenGL to `glFinish`, wall | load |
|---|---|---|---|
| plain | 9.5 ms | 23.7 ms | 269 |
| 4 samples | 8.8 ms | 18.5 ms | 272 |
| 4 samples, mip maps (95 parts), anisotropy 16 | 11.2 ms | 45.2 ms | 321 |
| the same + 4x pack (109 of 120 found, 206 MB) | 8.1 ms | 51.1 ms | 299 |
| 8 samples + the rest + pack | 9.1 ms | 50.6 ms | 281 |

The wall times follow the load, not the settings (4 samples "faster" than none). Read as
an upper bound for a loaded machine with a shared graphics card: 20 to 50 ms a picture
at 4K. **Not shown:** that 60 pictures a second hold at 4K with everything on. A paced
run in a small test window gave 3.6 pictures a second with any settings: the window lay
behind others and macOS held its swaps back (272 of 286 pictures stood seven refreshes or
more), which measures nothing.

Other figures:

- The game's display list: the fullest frame took 7,592 of 35,000 units in the first
  level at 4:3, 9,912 at 8:3, 11,760 in the session to the fight at 16:9. The object walk
  stops at 32,000: far away at these shapes.
- Art pack from power-on to the first level through every menu, 4x, 4:3 at 2560 x 1792:
  276 textures made, 268 found; 287 pictures read (202 as parts, 40 read again for a
  larger part); 206 held, 418 MB; process 1,589 MB. First level alone: 183 of 185 found;
  384 MB at 4x, 96 MB at 2x.
- The readers run at low priority on purpose. On this machine that meant seconds: a
  picture taken 200 frames after the level appeared still had the HUD in the game's art
  (18 pictures waiting). Interface art is now read ahead of the rest; `--art-wait` makes a
  test's frames wait for their pictures (used for the comparison with the emulator).
- Beside the emulator build with the same pack, first level: mean colour of the HUD
  region 68.9 / 65.8 / 55.0 there, 69.6 / 66.6 / 56.8 here; of the stone and the
  character 148.7 / 124.9 / 134.2 there, 148.3 / 124.7 / 133.9 here (the cameras stand a
  moment apart, so pixels are not compared). The same enlarged frame, bars, letters,
  stone and skin on both; the native picture has both fields of the interface art, the
  emulator's `shotfb` one.

## 6. What was changed where

New files (in place): `app/gfx_rt.h`, `app/gfx_rt.cpp`, `app/settings.h`,
`render/layout.h`, `render/texpack.h`, `render/texpack.cpp`, `render/xxh3_64.h`.

`tools/recomp/render/gfx.patch` (paths relative to `tools/recomp`):

| File | Change |
|---|---|
| `hle.txt` | 16 addresses: the six view functions and ten draw functions whose packets are marked. Every translation is made again at its next build (`funcs.h` changes: about 3 minutes of compiling per build flavour); a program that does not link `app/gfx_rt.cpp` gets the weak pass-through and is the game as before |
| `rt/rt.h`, `rt/runtime.cpp` | two hook pointers, null unless set: `rt_frame_hook` round `gfx_beginFrame`, `rt_dma_tag` for every tag of a source chain on channel 1 (it may put VIF NOP codes into the stream) |
| `render/vif1.cpp` | a NOP with 0xA5 to 0xA7 in its NUM field is handed to the GS model (after the waiting program has run) |
| `render/gs.h`, `gs.cpp` | `Gs::note`, the layout calls after each primitive, the moved scissor, `DrawCmd::made_by`, `name_texture`, the field sprite's place (section 2), a film is shown 4:3 |
| `render/backend.h` | `DrawCmd::made_by`, `scissor_moved`; `TextureData` name fields; `FrameList::aspect`; `PictureOptions`, `PictureFigures` |
| `render/backend_gl.h`, `backend_gl.cpp` | multisampled surfaces and their resolve; pictures (parts, mip maps, pack) and their samplers; `textureGrad`; centroid; `configure`, `figures`, `set_replacements` |
| `render/replay_main.cpp`, `render/build.py` | `--aa`, `--anisotropy`, `--mipmaps`, `--pack`, `--no-layout`; `texpack.cpp` in the list |
| `app/app_main.cpp`, `app/build.py` | settings and options, the view's shape from the window, picture sized by each list's own shape, frame cap 30, report lines, `app window / fullscreen / art`; `gfx_rt.cpp` and `texpack.cpp` in the list |

Notes for the merge are at the head of the patch.

## 7. Left

(2026-10-13, `native-app.md` 12.6: **full screen** was switched on, for five seconds each
way of presenting, and works - 1512 x 949 points, drawn at 3024 x 1898, the view 16:10
wide; the **30-a-second cap** shows one picture every four refreshes of the 120 Hz display,
as the system itself reports; 24 resizes while walking went through. The window's picture
now goes through a Metal layer by default: 12.3.)

- **Frames a second at 4K on a free machine**, and whether 60 hold; a tour of `shame1`
  with every picture in view (memory against the budget, pictures dropped and read again).
- **Full screen** was not switched on (a test window must not cover the screen).
- **Two players on one machine**: the screen clamp with the 4:3 planes was never called;
  whether holding two players inside the middle 4:3 of a wide screen is what people want
  is a question for whoever plays so (`wide-clamp=screen` is the other answer, and it
  changes the simulation).
- **A net game between a wide and a 4:3 machine**: argued (it is the case of two
  cameras), not run.
- **Idle things at the edges beyond 2:1** (section 1.3): said, not solved.
- **Trails** are 1 / k too broad across the screen; names over heads, the compass, the
  map, the inventory's figure and a second player's HUD have rules (section 1.4) that no
  picture has checked.
- **Texture cells at 32:9** in a large level; the display list's room there.
- **Alpha-tested edges** (leaves) get nothing from multisampling; alpha-to-coverage was
  not tried. Supersampling beyond 2x is filtered by one bilinear tap.
- **Windows**: built since (`docs/issues/native-windows.md`, "The picture options"): the
  Windows program has all of this, and a build without Qt (`RTA_NO_QIMAGE`) reads the
  pack with `render/png_read.h`, which gives QImage's bytes for every file of
  `local/hd-pack`. Not run on Windows. `gfx_rt.cpp`, `layout.h`, `xxh3_64.h` (it uses
  `__uint128_t` and `__builtin_bswap64`: MSVC needs `_umul128` and `_byteswap_uint64`) are
  plain C++ and compile with MinGW's clang and GCC as they are.
- Settings are read, not written back when something is changed while playing (the file
  is made once with the defaults).

## 8. How to repeat

```
export RTA_DISC="/path/to/your disc image.iso"
python3 tools/recomp/app/build.py && python3 tools/recomp/app/build.py --original
B=local/recomp-out
# 16:9 in a window that takes any shape; everything on is the default
$B/bin/rta_app --disc "$RTA_DISC" --window 1280x720 --art-pack local/hd-pack
# pictures without a window: 4K, 21:9, the pack; --plain is the picture as it was
$B/bin/rta_app --offscreen --unpaced --size 3840x2160 --aspect 16:9 --art-pack local/hd-pack \
    --script $B/app-test/boot-shots.rig
# what the widening of the culling adds, and the 2-D layer without its rules
$B/bin/rta_app --offscreen --aspect 16:9 ... -- --opt wide-cull=off
$B/bin/rta_app --offscreen --aspect 16:9 --no-layout ...
# the simulation in widescreen against the rig's log (wrapper: rta_app_orig --offscreen --unpaced
# --size 854x480 --aspect 16:9 -- "$@")
RTA_NATIVE=$PWD/$B/app-test/app-as-native-wide.sh python3 tools/recomp/rigcompare.py boot-native \
    --script local/recomp-out/fight3.rig --replay
python3 tools/recomp/rigcompare.py boot-compare
# the renderer alone on a recorded stream (script line: app record FILE ... app record stop)
$B/bin/rta_replay stream.rtavs --size 3840x2160 --loops 6 --aa 4 --anisotropy 16 --mipmaps --pack local/hd-pack
```

Debugging aids, off unless the variable is set: `RTA_GFX_LOG` (the display-list tags and
buffers as the marks are put in), `RTA_GS_FIELD_HOP` (field sprites where they were before
section 2), and the report at the end of a run (lines starting `rta_app: picture:`).

Local helpers of this work (not in the repository): `local/recomp-gfx/out/work/`
`pooldiff.py` and `symdiff.py` (two memory images of one tick: by region, by object class
and offset, by symbol), `emushots_pack.py` (the emulator build with the pack over a
script), `cmp_emu.py`, `rebase.sh`.
