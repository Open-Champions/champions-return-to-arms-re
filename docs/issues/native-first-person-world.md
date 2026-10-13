# The world seen from the ground

Started 2026-10-13. The owner wants the native build of Champions: Return to Arms
(SLUS-20973 v2.00) playable in first and third person ("sick in first person, and multiple
clean character views"). The camera is `docs/issues/native-first-person.md` (the views:
overhead, action, chase, shoulder, first); controls, aim and the HUD are another work; the
look - sky, fog, shadows, bloom - is done in Godot (`docs/issues/native-godot.md`). This
file is the third part: **what the world itself is when a camera stands in it**, by cause,
and what is done about it in the game's own code and data (C++, valid for any renderer).

Every statement says **Ran** (with what was seen), **Measured** (from the level files, tool
named) or **Read**. Pictures are game output and stay under
`local/recomp-fp-world/pictures/`; nothing derived from the game is in the repository.

## STATE (rewritten at every step; read this first after a stop)

**2026-10-13 14:35 - phase 1 written (sections 1 to 6); phase 2 begun.**

- **Ran:** 16 levels through the camera agent's views at fixed vertical blanks, 12 pictures
  each (`local/recomp-fp-world/pictures/before/`, sheets in `before/sheets/<level>.jpg`),
  and before that the same levels with the game's free camera at knee height (`p1/`).
- **Measured:** 17 levels' geometry with `tools/recomp/render/worldfill_measure.py`
  (section 2); the sky domes of five levels; which of the 111 levels has a dome at all.
- **Phase 2 (section 7):** my snapshot is the shared tree of 13:15 with the camera agent's
  `fpview.patch` applied (`local/recomp-fp-world/root`, program `bin/rta_fpw`). Nothing of
  phase 2 is delivered yet.

Where things are:

| What | Where | In the repository? |
|---|---|---|
| this catalogue | `docs/issues/native-first-person-world.md` | yes |
| the measuring tool (reads a `.world`, prints figures) | `tools/recomp/render/worldfill_measure.py` | yes |
| my copy of the sources, my builds | `local/recomp-fp-world/root` (`tools/recomp` = sources, `local/recomp-out/bin/rta_fpw`), `base/` = the shared tree at 13:15, `base-fp/` = that with `fpview.patch` | no |
| scripts: routes, sheets, level unpacking, dome measuring | `local/recomp-fp-world/work/` (`mkview.py`, `tour.sh`, `sheet2.py`, `extract.py`, `domes.py`, `domegeo.py`; `mkground.py` = the free-camera route) | no |
| pictures | `local/recomp-fp-world/pictures/` (`before/`, `p1/`, later `after-*`) | no |
| run logs | `local/recomp-fp-world/runs/` | no |
| unpacked level files, measurements | `local/recomp-fp-world/work/levels/`, `work/measure.txt`, `measure.tsv`, `domes.txt` | no |

## 1. How it was looked at

- **The route** (`work/mkview.py`, run by `work/tour.sh NAME "LEVELS"`): power-on to the
  first level by the tick-keyed script of `native-render-speed.md`, then every level by its
  name written to `g_pendingLevel`, 420 blanks for the fade-in, and at the place where the
  player stands: the game's own picture, first person in four directions (the game
  camera's yaw word +0x68 poked: 0, 0x4000, 0x8000, 0xC000), first person looking 30
  degrees up (two directions) and 30 down, chase and shoulder in two directions each. Every
  step is counted in vertical blanks by the machine; the program runs off screen, not
  paced, 1280 x 720 at 16:9, 4 samples. Two builds that agree make the same files
  (`sums.txt` beside the pictures).
- **The levels**: hub (the first level, a floating garden), valor (outdoor, cliffs and
  meadows), nitdung1 (dungeon corridors), arachna1 (cave), innovat1 (a scrap-yard between
  walls), citadel and drunare (built interiors: halls, an arena), fearboss (a boss room),
  fire1 (lava field), islsm1 (beach and sea, with a boss on it), swamp1, wat1 (sea floor),
  storm1 (snow forest), tormenta (a fortress floating in cloud), dis2 (a gorge), nit1 (a
  night forest). `bossevil` and `bossgood` cannot be entered by name (the script waits for
  a character that never comes): not looked at.
- **Before the views existed** the same levels were toured with the game's free camera
  (mode 3) at 17 units over the feet - knee height, as it turned out: a character is 60
  high (`fpview.h`), not 20 as `native-godot.md` says. Those pictures (`pictures/p1/`) show
  the near-field faults much enlarged and are kept for that.

## 2. What a level is made of (Measured)

`python3 tools/recomp/render/worldfill_measure.py LEVEL.world` decodes the drawn triangles
(`tools/world_info.py`), sorts their area by the way they face (the stored normals decide:
up, side, down) and by height over the **walked floor** - the terrain's height at the
nodes of the path grid that have links - finds the edges that belong to one triangle only,
and rasters what lies over the floor.

**The terrain's height field is the top surface of everything**: a wall is high ground
nobody can reach. "Height over the ground under the triangle" is therefore useless (the
ground under a wall is the wall's own top) and the tool measures from the nearest walked
floor instead.

| Level | Triangles | up / side / down, % of area | Area above head height, % | Floor with any geometry over it, % | Floor under a ceiling, % | Wall tops: median / third quartile over the floor | Open wall-top edges (upper bound), units | Walked floor, square units |
|---|---|---|---|---|---|---|---|---|
| hub | 24,774 | 68 / 31 / 0.8 | 1 | 0.0 | 0.0 | 120 / 130 | 2,527 | 0.70 M |
| valor | 377,991 | 75 / 24 / 0.8 | 30 | 9.3 (trees) | 0.8 | 98 / 130 | 1,577 | 6.2 M |
| dis2 | 479,995 | 88 / 12 / 0.2 | 11 | 0.1 | 0.0 | 69 / 70 | 91 | 9.1 M |
| nitdung1 | 605,056 | 60 / 38 / 2.2 | 28 | 0.3 | 0.0 | 141 / 148 | 8,495 | 2.7 M |
| arachna1 | 904,675 | 43 / 56 / 0.8 | 30 | 0.0 | 0.0 | 204 / 232 | 14,268 | 4.4 M |
| innovat1 | 585,894 | 63 / 35 / 2.1 | 28 | 0.3 | 0.0 | 134 / 144 | 27,865 | 5.4 M |
| citadel | 167,604 | 56 / 40 / 4.0 | 19 | 0.0 | 0.0 | 120 / 122 | 27,371 | 0.54 M |
| drunare | 66,470 | 54 / 37 / 8.7 | 38 | 7.8 (awnings) | 0.9 | 131 / 192 | 8,282 | 0.78 M |
| fearboss | 11,448 | 64 / 36 / 0.1 | 17 | 0.0 | 0.0 | 82 / 133 | 0 | 0.43 M |
| fire1 | 1,098,342 | 55 / 45 / 0.2 | 0 | 0.0 | 0.0 | 34 / 37 | 3,309 | 7.3 M |
| fire3 | 1,045,466 | 81 / 19 / 0.2 | 2 | 6.3 | 0.0 | 51 / 526 | 13,295 | 11.7 M |
| islsm1 | 88,219 | 100 / 0 / 0.1 | 0 | 0.0 | 0.0 | 117 / 128 | 0 | 18.8 M |
| swamp1 | 800,608 | 59 / 41 / 0.4 | 4 | 0.6 | 0.0 | 73 / 161 | 9,062 | 19.5 M |
| wat1 | 743,737 | 68 / 32 / 0.0 | 4 | 0.0 | 0.0 | 122 / 148 | 0 | 17.0 M |
| storm1 | 976,898 | 38 / 62 / 0.2 | 25 | 0.0 | 0.0 | 125 / 153 | 77,950 | 5.9 M |
| tormenta | 408,440 | 31 / 68 / 1.5 | 3 | 0.0 | 0.0 | 30 / 37 | 30,446 | 6.8 M |
| nit1 | 264,514 | 64 / 34 / 2.2 | 13 | 4.6 | 1.9 | 109 / 190 | 24,743 | 13.7 M |

(Full figures: `local/recomp-fp-world/work/measure.txt`. "Open" edges are matched by
position across chunks; where two chunks meet with different tessellation an edge counts
as open that is closed in the picture, so the lengths are upper bounds. A level has
8 to 10 million units of edge in all.)

What the table says:

1. **No level has a ceiling.** Faces that look down are 0.0 to 8.7 % of the area and lie
   on undersides of ledges, arches and awnings; the walked floor under a down-looking
   face is 0.0 to 1.9 %. Dungeon, cave, hall and boss room are open boxes.
2. **Walls are not "tops only" and they are not open either: they are solid blocks with a
   lid.** The rock between two corridors is drawn as its side faces and one big top
   (nitdung1: 26 % of all area is up-facing with no floor within 96 units - the lids). The
   lids lie 100 to 200 units over the floor (median 98 to 204 in the walled levels): **1.6
   to 3.4 character heights**. From an eye 60 over the floor the lid is never seen; from a
   chase camera 100 over the floor it is seen edge-on, and from the shoulder of a camera
   that rises above about 120 the view goes over the wall into the next room.
3. **Open wall tops are rare.** At most 0.1 to 0.8 % of a level's edge length is a wall's
   upper edge with nothing on it, and that is an upper bound. "Capping walls" is not what
   the levels need; what they need is what belongs *above* the lid.
4. **Low levels**: fire1, tormenta, dis2 and the beach have "walls" 30 to 70 units high -
   a kerb of rocks round a field. Standing in them the eye is above the wall and the level
   is seen to its edge.
5. Undersides exist nowhere they were not seen from above: the hub and tormenta float, and
   their flanks hang down as side faces (hub: 20 % of the area is side faces below the
   floor) - seen from a ledge, a floating island has a flank but the floor's underside is
   absent.
6. Two-sidedness is not a data question: no vertex program tests winding and the GS does
   not cull (`docs/spec/render-pipeline.md` 4.5), so the game draws both sides of
   everything and so does the OpenGL backend. A renderer that culls back faces would lose
   half the triangles (the stored winding is half one way, half the other:
   `docs/formats/world.md`). **Godot: draw the level two-sided.**

**Level of detail does not exist** (Read: `docs/formats/model-texture.md` - every model
file has one mesh table; level chunks have one packet). Nothing gets simpler with distance,
and nothing gets finer near the eye: texels are sized for a camera 340 to 450 away.

### The sky domes (Measured: `work/domes.py`, `work/domegeo.py`)

92 of the 111 levels have **no sky at all**: the picture is cleared to one colour
(`g_backgroundColor` 0x506044, set by a `clearColor` object of the level) and the level is
drawn over it. 19 have a `dome.lmp`, drawn by `game_drawBackdrop` 0x1e78d0 centred on the
camera position, in one of two builds:

| Build | Levels | Shape (model units, seen from the centre) |
|---|---|---|
| rings `a`, `b`, `c` of 8 segments each | hub, tormenta, tormentb, torment0, bossevil (all three); dis2 (`a` only); citadel, pvptor, torbonus, tormedal, torment2, torment3 (`b`, `c` only) | **a bowl under the camera.** `a`: a band 333 to 360 from the axis, height -75 to +110: elevation **-12 to +18 degrees**. `b`: -43 to -12 degrees. `c`: the bottom, -90 to -43. **Nothing above 18 degrees** (20 in dis2); with `b`, `c` only, nothing above -26 |
| `skya*`, `skyb*`, `skyc` (17 files) and the like (`s` x 8 to 24, `p` x 16) | islsm1, airarena, endbad, endgood, fire5, intro, bossgood | a hemisphere: 8 segments -2 to 23 degrees, 8 segments 23 to 51, a cap 51 to 90 |

So the ring domes were painted for a camera that looks down at 55 to 66 degrees: clouds
and far mountains below and around, and the top left open because it was never on screen.

## 3. The catalogue, by cause

### A. Not drawn, because the game prepared the frame for a camera overhead

| # | Seen | Cause | Evidence |
|---|---|---|---|
| A1 | **Holes in the ground at the feet**, wedges of sky colour at the lower corners; in chase and shoulder whole floor tiles missing beside the character (`before/valor-c0.png`, `before/citadel-c0.png`; grossly in `p1/valor-fp0.png`, `p1/storm1-fp2.png`, `p1/fire1-fp2.png`) | **The game never clips a triangle; it drops it.** When a chunk's or a model's box is not wholly inside the 80-degree plane set, the vertex program walks the finished strip and sets the no-draw bit of every vertex whose triangle has a corner more than 1000 pixels from the centre of the 1280 x 448 buffer, or behind the eye (`render-pipeline.md` 4.5, "clip rejection"). From 400 units up every floor triangle is small on screen; at eye height the floor tile under the camera reaches behind it and goes whole | Read; Ran (the pictures) |
| A2 | Textures swim on near floors and walls as the view turns | **Texturing is not perspective-correct**: the programs send texel coordinates (`UV`), not S, T, Q, so the GS interpolates across the screen. Invisible on small triangles far away; a floor triangle that crosses half the picture bends its texture | Read (`native-godot.md` stage 4; `world.md`: the GIF tags are UV, RGBAQ, XYZF2) |
| A3 | The near plane | The projection's depth range is a constant: **near 18, far 1800** (`camera_setView`), 16-bit depth, larger = nearer, 65535 at 18 units. The camera agent's views pass their own near (4 in first person) through `gfx_rt`. With near 4 the 16-bit depth has a step of 0.61 units at 400 and 12 units at 1800 (step = z x z / (16 B), B = 4094.94 x far x near / (far - near) = 16,416; with near 18, B = 74,453, it is 0.13 and 2.7) - **far walls and floors fight over depth** | Read; not yet measured in a picture |
| A4 | Things pop in at a distance while walking; the far corners of a wide view end in a saw-tooth edge | **Texture cells.** A chunk whose 720-unit texture cell is not loaded is not drawn (`world_drawChunk` 0x1887b8), and only the 3 x 3 cells round one point are kept (`worldtex_stream` 0x17d830: nine slots). For the overhead camera that is everything on screen. The camera agent hands the streamer `eye + forward x 600` in a view: the level is then there **1320 to 2040 units ahead, 120 to 840 behind, and 720 to 1440 to either side of that point** - at 1300 ahead a 16:9 view of 70 degrees is 1620 wide to each side | Read |
| A5 | The far plane | `g_farClip` 0x7d8a04 is **1800 in every level looked at** (the game's own cap); cutscenes lower it (`far clip = a x 12`). It is the plane chunks and objects are culled by. Beyond 1800 there would be more level in the big outdoor ones (fire1 is 7,000 across) but the cells of A4 end sooner | Ran (read at run time in 13 levels) |
| A6 | Objects - creatures, props, pick-ups - vanish when the view looks up | `world_drawObjects` 0x14b168 walks the object grid (cells of 256 units) and tests each cell **as a box from the camera's height to 840 below it**. Under a camera that looks up by more than half its field of view the lower plane of the frustum rises above the camera's height and no cell passes. First person looks up to 65 degrees; half of a 70-degree view is 35 | Read; to be shown in a picture (section 7) |
| A7 | The display list | One frame's list holds 35,000 units; `world_draw` **returns** and the object walk stops when fewer than 3,000 are left (`native-graphics.md` 1.2). The fullest frame of the tour took 24,984 (16:9; the overhead view: 21,358). A wider or deeper view runs out, and what is lost is whatever came last: objects | Ran (the program's own report) |
| A8 | Creatures far ahead stand still | Activity is a distance to a *player*, not the screen: 600 units for a creature (`obj_updateActive` 0x14db08), cull radius + 480 for a prop. The overhead view shows 430 to 560 units; a view along the ground shows 1300 and more. The asleep ones **are drawn** (the draw walk does not ask for activity) in their last pose | Read (`native-graphics.md` 1.3) |
| A9 | Scenery animations, emitters and lights only where they were drawn | Emitter and light chunks run in `world_drawChunk` (they are "drawn" to run); scenery models advance in `world_draw`. All follow the frustum of the view that is drawn - more of them run under a far view, and the 16 light slots (least recently drawn is replaced) are shared by more lights | Read |

### B. Not in the data

| # | Seen | What there is | What it would take |
|---|---|---|---|
| B1 | **Black (or the clear colour) above every wall**: dungeon, cave, hall, arena, boss room (`before/nitdung1-u0.png`, `before/arachna1-u1.png`, `before/citadel-u0.png`, `p1/drunare-up0.png`) | no ceiling anywhere (section 2); walls end in a lid 100 to 200 over the floor | a generated ceiling over the walked floor at lid height, or walls carried up into darkness: section 7 |
| B2 | Over the lid from a raised camera: the next room, and the flat top of the rock | the lids are big untextured-looking plates (they have a texture, pre-lit dark) | the camera kept under lid height in walled levels (for the camera agent: the "wall tops" column of section 2), and the ceiling of B1 |
| B3 | **No sky** in 92 levels: a flat colour to the zenith (`before/valor-u0.png` light blue, `before/fire1-u0.png` orange, storm1 grey-blue, wat1 dark blue, the night and interior levels black) | one clear colour per level | a sky made from that colour (Godot) |
| B4 | The ring domes stop: a band of painted cloud or trees at the horizon, the clear colour above 18 degrees (`before/citadel-u0.png`, `p1/tormenta-up0.png`, `p1/dis2-up0.png`); in citadel and five more levels the dome is wholly *below* the horizon | section 2 | the band's top row of colour carried to the zenith (Godot), or the clear colour chosen to match it - in hub and dis2 it already does |
| B5 | **The level's edge**: beyond the last lid nothing; a cliff's back, the outer rim of the rock, the end of the water grid as a saw-tooth (`p1/fire1-fp0.png`: the field ends in a ridge and the clear colour; `native-app.md` 10.2: the sea's rim) | the level ends where the overhead camera could no longer see | a skirt: the outermost lid carried outward and down, in the lid's own darkness (section 7); haze over the far field (Godot) |
| B6 | Trees and forest edges are boxes with a picture of branches on the lid (`p1/storm1-fp0.png`: a wall of fir "blocks"; valor's tree crowns are flat cards seen from below) | made to be read from above | nothing honest at this level; fog and darkness help |
| B7 | Undersides of floating things (hub, tormenta, citadel) | flanks only | not reachable in play; left |

### C. Tuned for looking down

| # | Seen | Cause |
|---|---|---|
| C1 | **No fog, anywhere.** The far field is as crisp and as bright as the near | Read: no primitive of the 3-D scene enables fogging (`render-pipeline.md` 4.3; counted in `native-app.md` 10.2: the only fogged primitives of the game are the bag's item glow). There is no fog colour and no fog distance in the level data: a level has a clear colour and a base light level |
| C2 | Light and shadow are painted into the textures for a top view | Read: vertex colours are not stored; every placed chunk has its own pre-lit texture (`world.md`), and the vertex program adds the base level (128; 64 in arachna1; `g_worldLightLevel`) and up to four point lights. Shadows of trees and walls are *in the floor texture* (`before/valor-game.png`); walls carry the same painted light and read well from the side. Nothing to fix; a renderer must not light the level again as if it were unlit |
| C3 | Characters have a blob shadow projected by the game: a quad 10 units over the floor pulled toward the camera (`native-godot.md` stage 4) - right from above, floating from the side (`before/fire1-c0.png`: a dark patch behind the feet) | `model_drawShadow` 0x1762e8 |
| C4 | **Light shafts are solid boxes from inside** (`before/nitdung1-f0.png`: a white slab in the doorway) | a shaft is an additive mesh meant to be looked through from above; from the floor one stands in it or looks along it |
| C5 | Heat haze (fire levels), glows, the sun flare, particles | built in screen space or as camera-facing sprites sized in pixels of the 1280 x 448 buffer; they keep their size when the view is 4 units from them. The haze copies a piece of the picture (`native-app.md` 10.2) and is right under any camera |
| C6 | Water | a 32 x 32 grid per 120-unit tile at one height, drawn where its tile is in view; the sea of islsm1 holds up to the horizon (`before/islsm1-f3.png`); swamp water was not made out as water in the side views (`p1/swamp1-fp0.png`: dark beyond the bank); why was not looked into. The environment map of flagged chunks is indexed by the camera-space normal plus 0.07 x the screen offset (`render-pipeline.md` 4.6), a look tuned under the overhead camera |
| C7 | Resolution near the eye | floor texels are about 2 units; at eye height a texel under the feet is 20 pixels (`before/valor-d0.png`). The art pack (`native-graphics.md` 3) is the remedy and is unchanged by any of this |
| C8 | Names over heads, prompts, floating numbers | placed in pixels over a projected point; they stay readable but stack when many creatures line up along the view |

## 4. Level by level

`before/sheets/<level>.jpg` holds the twelve pictures of a level; names below are files in
`local/recomp-fp-world/pictures/before/` unless they begin with `p1/`.

| Level | Kind | From the ground it is | Wrong, by the numbers of section 3 | Clear colour (R, G, B) | Sky | Base light |
|---|---|---|---|---|---|---|
| hub | first level | **good**: a floating garden under a lavender sky with a ring of far mountains; the dome's band and the clear colour match (`hub-f0.png`) | A1 at the platform's edge; B4 above 18 degrees is plain lavender (and reads as sky) | 148, 144, 194 | rings a b c | 128 |
| valor | outdoor | a meadow between rock walls, convincing at eye height (`valor-f0.png`) | B3 flat light blue; A1 in chase (`valor-c0.png`); the cliff tops are a hard silhouette; B6 | 117, 165, 193 | none | 128 |
| dis2 | gorge | a sulphur river between layered banks (`p1/dis2-fp0.png`) | banks 70 high: the eye looks over them at the lid; a band of painted trees then dark olive | (not read; dark olive) | ring a | 128 |
| nitdung1 | dungeon | corridors of rough stone, pools of painted light (`nitdung1-f0.png`) | **B1** black above walls 141 high; C4 the shaft in the doorway; the chase camera stands in a wall (`nitdung1-c1.png`) | 0, 0, 0 | none | 128 |
| arachna1 | cave | dark, fire-lit, the best mood of the set (`arachna1-s0.png`) | B1 (walls 204 high: less of it in view); A6 with creatures on ledges | 0, 0, 0 | none | 64 |
| innovat1 | scrap-yard | heaps of junk as walls 134 high (`p1/innovat1-fp3.png`) | B1 black above; the heaps' tops are cut straight | 0, 0, 0 | none | 128 |
| citadel | halls | arcades and torches (`citadel-f0.png`) | **B1/B4** maroon to the zenith inside a building; chase goes outside the hall and sees floors hanging in the colour (`citadel-c0.png`) | 49, 19, 22 | rings b c (below) | 128 |
| drunare | arena | the best interior: awnings and tiers give it a top (`p1/drunare-fp3.png`) | B1 black above the tiers; A1 | 0, 0, 0 | none | 128 |
| fearboss | boss room | (not looked at closely) | B1 | 0, 0, 0 | none | 128 |
| fire1 | lava field | a black lava plain to a ridge (`fire1-f0.png`) | **B3** flat orange over everything; B5 the ridge is the end; C1 | 255, 71, 36 | none | 128 |
| islsm1 | beach | **good**: sea to the horizon, clouds, sun (`islsm1-f1.png`) | A1 at the waterline; the far sea is a flat grey band | 44, 74, 105 | hemisphere | 128 |
| swamp1 | swamp, night | reeds and torches in the dark (`p1/swamp1-fp3.png`) | black beyond 300 units reads as night; the water is not seen as water from the side (C6) | 0, 0, 0 | none | 128 |
| wat1 | sea floor | (`p1/wat1-fp3.png`) | B3 flat dark blue (reads as deep water); A1 | 10, 30, 41 | none | 128 |
| storm1 | snow forest | (`p1/storm1-fp0.png`) | **B6** the forest is a wall of boxes; B3 flat grey-blue | 71, 89, 103 | none | 128 |
| tormenta | floating fortress | walls with spikes, crates, cloud below (`p1/tormenta-fp3.png`) | B4 the cloud band ends at 18 degrees, maroon above | (not read; maroon) | rings a b c | 128 |
| nit1 | night forest | giant roots and trunks, very dark (`nit1-f1.png`) | black sky reads as night; trunks end in a cut | 0, 0, 0 | none | 128 |

Level flag word 0x44fe08 as read: 0x01000000 in most, 0x05000000 in arachna1, 0x104 in
wat1, 0 in citadel, fearboss, fire1. `g_farClip` 1800 in all.

## 5. For the camera work

- Lid heights: the "wall tops" column of section 2. A camera in a walled level should stay
  under the lid of the walls round the character (median 98 to 204 over the floor,
  per level) or it looks over them into nothing. `fpview::ground` at the camera's own
  place returns the **lid** when the camera is over a wall (the terrain is the top
  surface): "6 over the ground under the camera" lifts it on top of the wall instead of
  keeping it out.
- The chase camera 150 behind stands inside walls in corridors (`nitdung1-c1.png`,
  `citadel-c0.png`): `terrain_raycast` is a height-field march, so a camera that ends up
  *over* a wall is not "blocked".
- First person at 60 over the feet with a 70-degree view sees the floor from 86 units
  ahead; looking 30 down from 30 ahead. A1 is worst there.
- Near 4 costs depth precision (A3).

## 6. For the Godot work

- Sky: 92 levels give one colour (section 4, the game's `g_backgroundColor`, bytes R, G, B
  from the low end); 19 give dome textures in `dome.lmp` of the level's GOB (`a00.tex` ...:
  162 x 109 used of 256 x 128, 8-bit with palette; the hemisphere build `skya*.tex`). The
  dome arrives in the draw list as the first 3-D draws of the frame, centred on the eye,
  radius 360 (ring build) or 179 (hemisphere), drawn before everything.
- Fog: the game has none. Distances that make sense from what is there: full haze by
  about 1300 units (the cells of A4), start at 300 to 500; colour = the clear colour where
  there is no dome, the dome's horizon band where there is one. Interiors (clear colour
  black): fog to black is what the game's own darkness already does.
- Draw two-sided (section 2, 6); the level's light is in its textures (C2); the blob shadow
  is the game's quad (C3) and can be told apart by its texture being a surface.

## 7. Phase 2: what is done about it (in progress)

Order: A1 (clipping instead of dropping), A6 (the object walk under a camera that looks
up), A7 (the list), A4 (cells), then B1 / B5 (generated ceilings and skirts through
`tools/recomp/render/worldfill.h`). Nothing delivered yet; this section is rewritten as
each lands, with pictures before and after.
