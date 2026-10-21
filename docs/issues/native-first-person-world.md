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

**2026-10-20 - section 8.8.** The eight levels flagged in every walk were looked at. Three general causes
were fixed: the eye's near plane in a wall beside it (`app/fpview.cpp`: sideways step, the picture's real width,
a nearer near plane in a corner), ground of resident cells left out for want of a prepared texture (drawn from
the shelf, `app/fpworld.cpp`), and the skirt hiding level geometry (drawn as a background, `render/gs.cpp`). The
fourth, looking over a rim into the void, is the levels' design. All 111 walked again: 93 ok (was 70), 7 flagged
(was 24). The simulation is identical (rig, both views).

**2026-10-19/20 - section 8.1 to 8.7.** The measure is now the clear-colour swap: coverage, not
colour, checked against the game's overhead view. The changes are in `app/fpworld.cpp` and
`rt/runtime.cpp`: a texture shelf for cells the game has unloaded, a guard against the decoder
slot hang that stopped `dismedal`, and wider chunk tests near the feet. An optional second stream
focus is there, off by default. All 111 levels are walked, and the simulation is identical
(rig, both views).

**2026-10-13 22:40 - phase 1 written (sections 1 to 6); phase 2 delivered as a patch and
new files (section 7): the level's generated ceilings and skirts, triangles cut instead of
dropped, textures in perspective, the object walk's cell boxes.**

- **Ran:** 16 levels through the camera agent's views at fixed vertical blanks
  (`local/recomp-fp-world/pictures/before/`, sheets in `before/sheets/<level>.jpg`), and
  before that the same levels with the game's free camera at knee height (`p1/`).
- **Measured:** 17 levels' geometry with `tools/recomp/render/worldfill_measure.py`
  (section 2); the sky domes of five levels; which of the 111 levels has a dome at all.
- **Ran, phase 2:** seven levels before and after with everything on
  (`pictures/fp-before/`, `fp-after/`, sheet `fp-after/before-after.jpg`), on the shared
  tree as it stood at 22:20 (views, look controls, scene tap, the integrator's merges).
  The overhead pictures of that tour are the same files with the parts on and off.
- **Delivered:** `tools/recomp/render/fpworld.patch` (applies to the shared tree of 22:35
  without a reject: dry run on a copy), new files `app/fpworld.h`, `fpworld.cpp`,
  `render/worldfill.h`, `worldfill.cpp`, `worldfill_main.cpp`, `worldfill_measure.py`.
- **Not done:** the texture-cell window (A4), the display list's size (A7), a paced
  measurement at display resolution, `world.*` lines in the settings file, the Windows and
  Godot build lists. Section 7.6 has the list.
- The move of the workspace (2026-10-13 evening): nothing of `local/recomp-fp-world/` was
  among the files that did not come across; the snapshot was taken again from the shared
  tree twice since (`base.stamp`).

Where things are:

| What | Where | In the repository? |
|---|---|---|
| this catalogue | `docs/issues/native-first-person-world.md` | yes |
| the measuring tool (reads a `.world`, prints figures) | `tools/recomp/render/worldfill_measure.py` | yes |
| the game side of phase 2: switches, hooks, the fill at a level load | `tools/recomp/app/fpworld.h`, `fpworld.cpp` | yes |
| generated geometry (ceilings, skirts) as mesh lists | `tools/recomp/render/worldfill.h`, `worldfill.cpp`; `worldfill_main.cpp` builds it from a `.world` file without the game | yes |
| changes to files other work owns | `tools/recomp/render/fpworld.patch` (merge notes at its head) | yes |
| my copy of the sources, my builds | `local/recomp-fp-world/root` (`tools/recomp` = sources, `local/recomp-out/bin/rta_fpw`), `base3/` = the shared tree the patch is made against | no |
| scripts: routes, sheets, level unpacking, dome measuring | `local/recomp-fp-world/work/` (`mkview.py`, `tour.sh`, `sheet2.py`, `extract.py`, `domes.py`, `domegeo.py`; `mkground.py` = the free-camera route) | no |
| pictures | `local/recomp-fp-world/pictures/` (`before/`, `p1/`: phase 1; `fp-before/`, `fp-after/`: phase 2; `x1/`, `t1/`: the cut beside a wall, textures in perspective) | no |
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
| A1 | **A wall one stands against is gone, and the view goes through it; a character close to the camera is a mess of shards** (`x1/cmp-nitdung1-0-f1.jpg`: first person 14 units from a dungeon wall, black where the wall is; `x1/cmp-nitdung1-0-d0.jpg`; `x1/cmp-citadel-0-c1.jpg`: the chase camera pulled in behind the character). With the free camera at knee height also holes in the floor at the feet (`p1/valor-fp0.png`, `p1/storm1-fp2.png`); **not** at the views' own heights in open ground: the wedges of `before/valor-c0.png` and `before/citadel-c0.png`, first put down to this, are a chase camera standing inside the rock | **The game never clips a triangle; it drops it.** When a chunk's or a model's box is not wholly inside the 80-degree plane set, the vertex program walks the finished strip and sets the no-draw bit of every vertex whose triangle has a corner more than 1000 pixels from the centre of the 1280 x 448 buffer, or behind the eye (`render-pipeline.md` 4.5, "clip rejection"). From 400 units up every triangle is small on screen; a wall or a floor tile beside the camera reaches behind it and goes whole | Read; Ran: with the cut of section 7.2 off and on at the same blanks, 20 to 36 % of the picture changes beside a wall and nothing in open ground |
| A2 | Textures swim on near floors and walls as the view turns | **Texturing is not perspective-correct**: the programs send texel coordinates (`UV`), not S, T, Q, so the GS interpolates across the screen. Invisible on small triangles far away; a floor triangle that crosses half the picture bends its texture | Read (`native-godot.md` stage 4; `world.md`: the GIF tags are UV, RGBAQ, XYZF2) |
| A3 | The near plane | The projection's depth range is a constant: **near 18, far 1800** (`camera_setView`), 16-bit depth, larger = nearer, 65535 at 18 units. The camera agent's views pass their own near (4 in first person) through `gfx_rt`. With near 4 the 16-bit depth has a step of 0.61 units at 400 and 12 units at 1800 (step = z x z / (16 B), B = 4094.94 x far x near / (far - near) = 16,416; with near 18, B = 74,453, it is 0.13 and 2.7) - **far walls and floors fight over depth** | Read; not yet measured in a picture |
| A4 | Things pop in at a distance while walking; the far corners of a wide view end in a saw-tooth edge | **Texture cells.** A chunk whose 720-unit texture cell is not loaded is not drawn (`world_drawChunk` 0x1887b8), and only the 3 x 3 cells round one point are kept (`worldtex_stream` 0x17d830: nine slots). For the overhead camera that is everything on screen. The camera agent hands the streamer `eye + forward x 600` in a view: the level is then there **1320 to 2040 units ahead, 120 to 840 behind, and 720 to 1440 to either side of that point** - at 1300 ahead a 16:9 view of 70 degrees is 1620 wide to each side | Read |
| A5 | The far plane | `g_farClip` 0x7d8a04 is **1800 in every level looked at** (the game's own cap); cutscenes lower it (`far clip = a x 12`). It is the plane chunks and objects are culled by. Beyond 1800 there would be more level in the big outdoor ones (fire1 is 7,000 across) but the cells of A4 end sooner | Ran (read at run time in 13 levels) |
| A6 | Objects that stand **higher than the eye and more than a grid cell away** are left out when the view looks up (not seen in any picture: see the evidence column) | `world_drawObjects` 0x14b168 walks the object grid (cells of 256 units) and tests each cell **as a box from the camera's height to 840 below it**. Under a camera that looks up by more than half its field of view the lower plane of the frustum rises above the camera's height; a cell far from the camera then lies wholly under the view and its objects are never asked, whatever their own height. The cells at the camera itself still pass (the box touches the eye) | Read. Ran: first person looking 55 degrees up in hub, drunare, arachna1 and beside the boss of islsm1, the walk as it is and with the cell boxes raised (7.3): the same pictures - the boss's club stays in view either way, because he stands in the camera's own cell. No stop of the tour has a far object above the eye; the first reading of this ("every object vanishes") was wrong |
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
- With the fill on (7.1) a ceiling is drawn only where the eye is under it, so a camera above a lid is not blinded; the ceiling's height over a floor point is in `render::current_fill()`'s meshes.

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
- **Generated geometry**: `render::current_fill()` (`tools/recomp/render/worldfill.h`) gives the loaded level's ceilings and skirts as blocks of triangles in world space (position, normal, a tiling coordinate, a grey level, alpha for the skirt's fade) with a serial number per build; `app/fpworld.cpp` builds and publishes it when a level is first drawn in a view (or call `render::build_fill` on the `.world` yourself - `worldfill_main.cpp` shows how). Section 7.1 says what is in it.
- Draw two-sided (section 2, 6); the level's light is in its textures (C2); the blob shadow
  is the game's quad (C3) and can be told apart by its texture being a surface.

## 7. Phase 2: what is done about it

All of it is switched by `world = views | off | always` (default `views`: only while a view
other than overhead is drawn) and one switch per part; command line `--world KEY=VALUE`,
script and control socket `app world set KEY VALUE`, `app world info` (figures), runtime
options `--opt world-clip=off` and the like. With the overhead view selected none of it runs:
the seven overhead pictures of the tour are the same files with everything on and with
`world=off` (`work/cmp.py pictures/fp-before pictures/fp-after`). Nothing writes a word the
simulation reads: the hooks are on draw functions (`frustum_testBox`, `world_draw`,
`world_drawChunk`, the object walk) and change, for the length of a call, a box on the
caller's stack and nothing else; the fill is built from the level's terrain by reading it.
**Not run:** a tick-for-tick comparison with the rig (the camera work's section 5 is the
place; the argument above is Read, not shown).

### 7.1 Ceilings and skirts: `render/worldfill.h` (Ran)

**What is generated, from what.** `render::build_fill` reads the level's `.world` - the
file's bytes, or the fixed-up structure in the machine's memory - and uses only its terrain
(the height samples every 4 units, which are the top surface of everything) and its path
grid (where the floor is), plus the boxes of the chunk records:

- the **floor** is flooded from the path nodes over ground that steps by at most 10 a
  16-unit cell;
- a **wall that carries a ceiling** is a cell beside the floor whose top is 70 or more over
  it and is not itself walked (the edge of a gallery over a lower court is not a wall: the
  first version hung the court's ceiling at the gallery's feet and hid the far side of
  `honor`);
- the **ceiling** over a floor cell is the lid of the nearest such wall plus half the
  distance to it (a corridor 100 wide gets 25 at its middle, a court 1000 wide 250: with a
  small fixed rise the far buildings of a wide hall were hidden behind the ceiling), never
  nearer than 96 to the highest floor within 190 units, never under anything the level
  draws there (the chunk boxes: awnings, arches, pillar crowns are drawn and not in the
  terrain - the arena's awnings were cut off before this), smoothed, and carried 190 units
  on over the lids and over gaps;
- a **skirt** starts at the level's outer rim where the rim is a lid (40 or more over the
  nearest floor, or no floor near) and runs 480 units outward, sinking 12 %, its alpha
  falling to nothing; a floor that ends at the rim gets none.

Built in 1 to 35 ms a level; 18,000 (arena) to 240,000 (honor) triangles, in blocks of
128 x 128 units with their own boxes.

**What is the game's and what is not.** None of it is the game's art: a vertex has a
position, a normal, a place for a tiling texture (world x, y / 64) and a grey level (how
near the next wall is; a skirt: how far out). The OpenGL program draws a ceiling plain and
dark (grey x 0.10 x the level's base light, slightly warm: 25 of 255 at a wall, 15 in the
middle of a hall) and a skirt in the clear colour x 0.6; **Godot takes the meshes from
`render::current_fill()` and shades them itself.**

**Which level gets what** (`app/fpworld.cpp`, `level_fill`; `world.ceilings`,
`world.skirts` = `auto | on | off`):

| | auto means | Why |
|---|---|---|
| ceilings | the level clears to black, has no sky dome, **and** is walled: the wall cells that would carry a ceiling make up a tenth of the walked floor's area or more | measured: dungeon 0.26, cave 0.23, arena 0.17, scrap-yard 0.13; a night swamp 0.06 and a night forest 0.01 clear to black too and must not be roofed. `citadel` (halls, but a cloud bowl and a maroon clear colour) gets none by this rule: `world.ceilings = on` forces it. Only the 17 levels of section 2 and `honor`, `inmine1` were looked at; the other 92 follow the rule unseen |
| skirts | the level has no sky dome | a dome is a bowl of cloud under a floating level or a painted horizon: there the rim is the design |

**How it reaches the picture** (OpenGL program): at a level's first drawn frame the fill is
built and published; every frame of a view the game side puts a note in the stream in
front of the frame's first level-chunk packet (after the sky, before everything blended)
with the frame's own view-projection matrix, eye, clear colour and base light;
`Gs::draw_fill` culls the blocks, cuts at the near plane and adds plain triangles to the
list (depth tested and written like the level's own; 5,000 to 6,000 triangles a frame in
the tour). **A ceiling is drawn only where the eye is under it**: a camera that has got
above one (a chase camera over a lid) looks through it as before, instead of at its back.
A recorded stream has the note but not the meshes: it plays without the fill.

**Seen** (`pictures/fp-after/before-after.jpg`; pairs `fp-after/ba-<name>.jpg`; whole
levels `fp-after/sheets/`):

| Level | Before | After |
|---|---|---|
| nitdung1 (dungeon) | black above every wall (`fp-before/nitdung1-u1.png`) | a dark vault that meets the wall tops (`fp-after/nitdung1-u1.png`) |
| honor (halls round a court) | black above; the far buildings stand against nothing (`fp-before/honor-f0.png`) | a tent of dark over the court, the far buildings under it (`fp-after/honor-f0.png`, `honor-s1.png`) |
| inmine1 (mine) | black between the beams (`fp-before/inmine1-u0.png`) | closed (`fp-after/inmine1-u0.png`, `inmine1-f2.png`) |
| arachna1 (cave) | black over walls 223 high: little of it in view | closed (`fp-after/arachna1-u1.png`) |
| drunare (arena) | black over the awnings | a ceiling above the awnings (`fp-after/drunare-u0.png`) |
| valor, fire1 (outdoor) | - | no ceiling (the rule); a skirt beyond the rim, not in view from the stops of the tour: **not shown in a picture** |

What it does not do: it is not textured (a level chunk's texture is its own pre-lit
picture, resident only with its cell: none can be borrowed for a ceiling); a ceiling is a
height field like the level, so it does not go *under* an upper floor; a wide hall gets a
tent, not architecture.

### 7.2 Cut instead of drop, and textures in perspective (Ran)

`render/gs.cpp`, `Gs::world_run`; `render/vif1.cpp`, `no_reject`. For strips kicked by the
four mesh programs into the 3-D buffer, while a view is drawn:

- **The vertex programs keep the whole number.** They make integers for the GS by adding
  2^19 + 2^11 to X and Y and 2^65 to the depth and letting the GS take the low bits
  (`render-pipeline.md` 4.3). What lies in VU1 memory at the kick is the float: a position
  3,000 pixels off the centre, a depth beyond the near plane, a point behind the eye (where
  x / w is still the right projective coordinate). `world_run` reads that instead of the 16
  bits.
- **w comes back from the depth**: depth = A + B / w with the view's own near and far
  plane, which the game side sends with every frame (notes NUM 0xB0 / 0xB1). The float
  keeps the depth to 1/16 of a unit of the 16-bit buffer, so w is known to 0.2 units at 1800
  with near 18 and to 0.8 units with near 4 - enough for the texture; the depth *buffer's*
  own step (A3) is unchanged.
- **The programs are started without their clip flag** (`ITOP` before entry 0x16 for a
  chunk, before 0x02 for a model), so their second loop - the one that drops - does not
  run, and the GS model cuts every triangle that crosses the near plane, in the space
  before the division; one wholly behind it is left out.
- **Textures in perspective**: a vertex is given (u q, v q, q) with q = near / w; the
  backend's shader has always divided by q, so no backend changes. Colours stay
  interpolated across the screen.

**Seen**: beside a wall, `x1/cmp-nitdung1-0-f1.jpg` (the wall is there), `cmp-nitdung1-0-d0.jpg`,
`cmp-citadel-0-c1.jpg` (the character is whole); in the last tour 352,660 triangles cut and
5.8 million left out as wholly behind the eye, none with a corner on the eye's plane.
Perspective: `t1/cmp-nitdung1-d0.jpg` (the floor's stones keep their shape; mean difference
7 of 255 over the picture). Models go the same way: a character half behind the camera is
cut, not broken.

**For Godot**: not needed (it draws the packets' complete geometry) and not compatible
with the scene tap's count check - merge notes at the head of the patch.

### 7.3 The object walk (Ran; nothing to show)

`gfxrt::object_walk` hands the walk to `fpworld`; for its length a cell box that
`frustum_testBox` is asked about is taken from 840 below the eye to **600 above it**
(`world.objects`). About 400 boxes a frame are widened. See A6: no picture of the tour
changes, because no stop has a far object above the eye; it is kept because it is right
and costs nothing, and said here as unproven in a picture.

### 7.4 Figures the game side counts (Ran)

`app world info` prints, per pass: chunks drawn, chunks in the frustum **not** drawn
because their texture cell is not loaded or their texture is still on its way, box tests,
display-list units. With the shared tree of the afternoon (far plane 1800 in a view): 69
to 226 chunks drawn and **120 to 215 not drawn for want of their texture cell** in valor,
nitdung1 and citadel - A4 in numbers. With the tree of the evening (the camera work now
culls nearer) the last passes of the tour have none missing. `--opt world-nocull=1` (a
test aid) makes every box pass the frustum test: what is missing then is not culled, it is
not there.

### 7.5 Speed (Ran, on a machine that was never free)

The seven-level tour, off screen, not paced, 1280 x 720, 4 samples, load average 40 to 80
beside it: 193.8 pictures a second of wall time with `world=off`, 177.6 with everything on
(5.2 and 5.6 ms a picture); an earlier pair of the same tour gave 235 and 204. Two-level
runs with one part on at a time did not separate the parts from the noise (348 off, 362
cut and perspective only, 316 fill only, 255 all - the order is not even monotonic).
**Not measured:** paced at display resolution with the interval histogram of
`native-app.md` section 11; processor time by thread. The fill adds 5,000 to 6,000
triangles a frame to a list of 60,000 to 90,000.

### 7.6 Left

- **A4, the texture-cell window.** The streamer has nine slots and loads the 3 x 3 cells
  round one point; chunks outside are not drawn (or, since the camera work's change, drawn
  with whatever texture they have). A wider window means more slots than the game's
  fixed tables hold (the slot index is a signed byte per cell at 0x41c1b8, nine pointers
  at 0x425df8, a block map of 128 x 128 KB) - a host-side cache of whole `.TEX` files
  (0.85 to 47 MB a level) beside the game's nine would do it, with the chunk's texture
  header looked up there when its cell is not resident. Not started.
- **A7, the display list** (35,000 units): the fullest frame of the last tour took 19,430.
  Not touched.
- **A8**: creatures beyond 600 units stand still. Left on purpose (a larger radius changes
  the simulation).
- The skirt was not seen in a picture; its colour in the OpenGL program is a guess.
- `world.*` lines in the settings file; the Windows build list; the fill in recorded
  streams.
- Levels not looked at: 92 of 111. The ceiling rule decides for them unseen. (2026-10-17: all walked
  at eye height, section 8.)

## 8. 2026-10-17: every level at eye height (Ran)

Evidence root `local/fp-ready/` (not tracked).

**The driver** is `tools/recomp/app/tour.py native fpwalk LEVEL... --out DIR` (summary:
`tour.py fpreport DIR...`). It goes from power-on to the first level. Each level is then
asked for by name, the way the game's own level change does it. The driver answers what
holds the game (memory-card question, film, loading screen) and waits out the fade-in. It
then stands at the start and at three places the character walks to (the stick, so the
game's own movement and collision apply). At each place it turns through eight headings
with the look controls (`app fpc mouse`), then looks 40° up and 40° down. That gives 40
pictures at 480×270 per level. Each picture is measured against the level's clear colour
(`g_backgroundColor`):

* `hole`: clear colour in the lower third of a level look, or anywhere in the look down.
* `open`: clear colour in the upper half of a look up, in a level that gets the generated
  ceilings.
* `void`: more than half of a level look is clear colour.
* `inside`: a flat picture.

`app world info` adds the most chunks left undrawn for want of their texture cell. Four
processes run off screen and unpaced. A level that does not load restarts the program.

**Generic causes found and fixed (`app/fpview.cpp`):**

1. **The eye in the wall.** Standing against a wall put the eye (7 ahead of the head) and the
   near plane (14 in arms mode) inside it. The wall was cut away, and the dark inside of the
   block or the room behind showed (`walk-test/nitdung1/p1-*`: black with a strip of the next
   room). The eye now goes back along the heading, at most 16 behind the head. It moves just
   far enough that the level, by the terrain query along the heading and both picture edges,
   is the near plane plus 5 away (`walk-test2/nitdung1/p1-*`: the wall is drawn). This uses
   `terrain_raycast` like the chase camera does. It changes one presentation pointer in the
   object pool (the rig's `pool` column, 1,465 rows); the simulation columns and both
   comparison reports are unchanged (hands document, 2026-10-17).
2. **Sky through the ground near the eye** (valor's boar fight; `hole1/attack-2400.png`, also in
   Godot, `g-c4`). The texture stream's point was 600 ahead of the eye. Every turn swung it
   across 720-unit cells, and the ground just ahead lost its cells (17 chunks without a cell,
   18 still loading). It is now 300 ahead, measured along the level, not along the view
   (`--opt view-stream-ahead=N`). The same frame then has no gaps (`hole-final/`,
   `hole-a250/`, `hole-a400/`). Far chunks without a cell remain (100 to 300 a frame in big
   levels: A4, still open). `world-nocull`, `world-clip=off` and `view-stream=off` were tried
   and did not help.

**Results of 2026-10-17.** 108 levels walked (3 not reached before the run was stopped), 62 ok,
3 fixed, 31 flagged, 12 not applicable. The flags were measures, not verdicts: in levels that
clear to black or a dark colour, night ground and dark floors gave false `hole` flags. That walk
is the "10-17" column of the table in 8.6.

### 8.1 2026-10-19: the measure (Ran)

Evidence root `local/fp-world2/` (not tracked; pictures in `pictures/`, walks in `before-a`,
`before-b`, `final-1` to `final-3`, probes beside them, scripts in `work/`).

The driver is the same command (`tour.py native fpwalk`). What it measures changed:

* **Coverage, not colour.** Every look is taken twice. For the second picture the level's clear
  colour (`g_backgroundColor` 0x506044) is swapped for three blanks for one far from it (magenta,
  or green when the level's own is near magenta). A pixel that takes the swapped colour is one
  nothing was drawn on. A black floor of a night level is a floor, and a dome or a fog that lets
  the clear colour through only in part is not counted
  (`pictures/coverage-masks.png`: `nitdung3`, `obsidian`, `valor`, `swamp2`).
* **The game's own view of the same place.** Where a place has a flag, the overhead view is
  taken the same way. If nothing is drawn round the character there either (more than 3 % of
  the middle of the picture), the `hole` and `void` flags of that place are the game's, not the
  view's: verdict `game`, detail `as-overhead=N`.
* **The pitch is held.** A look is made with `view.first.pitch`, `pitch_min` and `pitch_max` all
  set to its angle. The 10-17 walk tapped cross to answer prompts, which swings the weapon. With
  a target locked, the swing tilt of `fpcontrols` (`swing_tilt`) tipped the view up by about
  25 degrees and kept it there: `obsidian`'s "black ground before the far rocks" was the night
  sky in the lower half of the picture (`pictures/obsidian-tilted-before.png`).
* **`void`** is now "more than half of the *lower* half undrawn". An open night sky above the
  horizon is not a fault.
* **A scene that holds the camera** (`app view info` says "the game's camera") is waited out and
  answered with cross up to 16 times. A place where it never lets go is not judged; a level where
  no place is judged is `held`, and the program is started again after it (after an ending's
  scene the next level change crashed or hung the game twice; started fresh, both levels
  walked).

### 8.2 The three levels not reached; `dismedal` hung the game (Ran)

`wate2b` and `watg2b` walk without a flag. `dismedal` never came back: the 10-17 run had stopped
there, and the first walk today stopped at the same place (`p0-h4`). A sample of the stuck
program shows the game's thread in `animcache_alloc` 0x16e388, called from `anim_emitPose` under
`world_drawObjects` in the view's draw pass. The allocator skips decoder slots whose owner track
carries root motion or yaw. With all 165 held it never returns (`docs/spec/animation.md` 3.1).
Counted over the slots (owner +0x14, flags +0x1c & 0x4800): overhead, `dismedal` holds about 95;
the views draw creatures out to 1,800 units, each pins one or two more, and one object walk went
from 76 to 161.

**Fix (`app/fpworld.cpp`, always on in a view):** while a view's object walk runs, every box it
tests first counts the held slots. From 140 on, a box farther than 650 units from the player is
outside (the overhead camera would not have drawn it either). From 158 on, no box passes. Drawing
only: what is not drawn is not decoded. `dismedal` now walks (`ok`). The guard was active in 386
object walks of its 40 looks. 10,885 boxes were left out (far creatures not drawn while the
crowd is near). The most held was 131, and the hard limit was never reached. `app world info`
prints these figures.

### 8.3 Far ground: the shelf and a second stream focus (Ran)

The game keeps the textures of nine cells of 720 x 720 units. A chunk of any other cell is not
drawn (A4). Since 10-17 the nine are round a point 300 ahead of the eye (for the near ground), so
in a big level 100 to 300 chunks a frame in sight had no cell.

* **The shelf (`world.cells`, on).** A texture of a resident cell is copied once the game's
  texture thread has prepared it. The copy covers its header and its upload chain: NEXT tags
  from one 4 KB page of the thread's pool to the next, a RET at the end (`docs/formats/world.md`).
  It goes to host memory that the runtime shows at guest addresses the console does not have
  (`rt_shelf`, 0x08000000 up, 120 MB at most; `rt/runtime.cpp`: loads, stores and DMA reach it,
  and the hooks of the VIF1 chain are not asked about its tags). A chunk of a cell that is not
  resident is then drawn by the game's own `world_drawChunk`, with its texture copy. For the
  length of that one call, the cell's slot byte and a tenth slot pointer (0x425e1c) show the
  shelf's header table, and both are put back when it returns. The game uploads from the copy
  like any texture. Its `gfx_dmaHandler` writes the destination into the copy, and its texture
  cache marks the copy's header resident or not. A new level empties the shelf. Textures that
  nothing has drawn are put into the thread's queue a few at a time while the queue is nearly
  empty (the way `world_drawChunk` adds them, 0x17fc78), so a cell is on the shelf whole.
* **A second stream focus (`world.sweep`, off by default).** It applies when the view is still
  (less than 12 degrees of turn and 60 units of walk in 45 frames), the nine cells round the near
  point are resident, and every texture of the cells round the eye and round the near point is
  on the shelf. If the last pass still had 16 or more chunks without a cell, the stream is then
  pointed 1,300 units ahead. It returns to the near point when the far cells have been resident
  for 40 frames, after 300 frames, or at once when the view turns or the player walks.

Measured with `work/sweepprobe.py` (eight headings, each looked at for 240 blanks; chunks in
sight without a cell after the wait):

| | `fire3`, 8 headings | `islsm3a`, 8 headings |
| --- | --- | --- |
| `rta_app` | 287 233 222 199 260 251 132 193 | 233 181 13 0 3 0 33 125 |
| shelf and sweep | 47 31 39 29 66 20 11 1 | 221 73 3 0 2 0 0 67 |

Seen: `pictures/fire3-far-ground-before-after.png`: with the sweep, the towers and pyramids on the
horizon of `fire3` are there. **Why it is off:** the same six levels walked three ways
(`ab-old`, `ab-next`, `ab-nosweep`) gave holes near the feet with the sweep on (`storm1b`,
`hub2`) and none with it off. A turn right after a sweep, before the near cells are back, shows
ground whose texture is on the shelf only if it was prepared, and the cells round the eye are
not all the cells a turn brings into view. The first full walk (`interim/`, `final-*` before the
re-walk) had 37 levels with a flag with the sweep on. With the shelf alone, distant ground keeps
its textures for every cell that was once in reach; `world.sweep = on` (or `--opt
world-sweep=on`) brings the far focus back for a still view.

### 8.4 Holes of a chunk's size near the feet: the chunk boxes (Ran)

`obsidian` at (324, -86): a straight-edged gap in the ground just ahead and right, a third of the
lower picture (`pictures/obsidian-chunk-box-before-after.png`, left). The same gap is in
`rta_app` and with the shelf and the sweep off. It is gone with `world-nocull=1` (every box
passes). Boxes taller by up to 2,000 units do not help; boxes 300 wider on every side close it,
and 120 wider nearly does. Some chunk boxes do not cover their ground. From overhead the frustum
is hundreds of units wide at the ground, and such a box still passes. Just in front of an eye
at head height the frustum is a few units wide, and the box falls outside a side plane while its
ground is in the picture.

**Fix:** in a view, `world_draw`'s test of a chunk's own box (call 0x189ca4) is made as the game
makes it. Only when that fails, it is made again with the box 256 units wider on every side.
Only chunks of plain level geometry get the second test: the kinds that draw water, lights or
emitters (flags 0xC880) take numbers from the cosmetic generator and are tested as before. The
box is put back after the test. Undrawn share of the lower third at that spot: 0.345 before,
0.024 after. `world-box-xy=N` and `world-box-z=N` change the margins.

The options of `fpworld` (`world-nocull`, `world-clip=off` and the rest) were read at
`install()`, before the runtime had parsed the command line. None of them ever took. The "tried
and did not help" of 8 (generic cause 2) was therefore not a test. They are now read at the first
frame.

### 8.5 `nitdung3` and `obsidian` (Ran)

* **`nitdung3`**: no floor is drawn ahead and under the feet at the start, in the game's own
  view as well. The emulator build's overhead picture of the same start has the same black, and
  so does the native one (`pictures/nitdung3-emulator-native-overhead.png`). With every box
  passing it is the same, and it shows in the coverage mask as nothing drawn, not as a dark
  floor. It is the level's: verdict `game`.
* **`obsidian`**: the "black ground" was the tilted view (8.1), plus the chunk-box hole of 8.4.
  With both fixed, only one look flags (see the table).

### 8.6 The table

The "10-17" column is the walk of 10-17 with the old measure. "10-19, `rta_app`" is the new
measure with the program as it is (`rta_app`), walked for the 31 flagged and the three not
reached. "10-19, `rta_app_next`" is the new measure with the program as
delivered, for all 111 levels: a full walk, after which the 39 levels with a flag were walked
again once the sweep was switched off (`rewalk-*`; their row is that second walk). Verdicts: `ok`; `game` (every hole is also in the game's overhead view of that place);
`fault`; `held` (a scene keeps the game's camera at every place: the two endings); `n/a` (no
single-player start in this game kind). The "What" column has a description where the pictures
were looked at; otherwise it holds the raw flags of the final walk.

| Level | Looked at before | 10-17 | 10-19, `rta_app` | 10-19, `rta_app_next` | What |
| --- | --- | --- | --- | --- | --- |
| airarena |  | n/a |  | n/a |  |
| arachna1 | yes | fault | ok | ok |  |
| bastion1 |  | fault | game | game | the start stands at the floor's rim (B5); flagged places are the rim, overhead shows the gap too at most of them |
| blomedal |  | ok |  | ok |  |
| blood1 |  | ok |  | ok |  |
| boar1 |  | fault | ok | ok |  |
| bossevil |  | ok |  | ok |  |
| bossgood |  | ok |  | ok |  |
| citadel | yes | ok |  | fault | hole=3(p0-h3) |
| compblo |  | n/a |  | ok |  |
| compdis |  | fault | n/a | fault | hole=2(p0-h3) |
| compsto |  | ok |  | n/a |  |
| compval |  | ok |  | n/a |  |
| compwat |  | n/a |  | fault | hole=1(p2-h3) |
| dis2 | yes | fault | ok | ok |  |
| disbonus |  | ok |  | ok |  |
| dismedal |  | not walked | hung | fault | 10-17 and the first walk today: the game hung (decoder slots, 8.2); now walks, 1 look flagged |
| drunare | yes | ok |  | ok |  |
| drunarm |  | ok |  | ok |  |
| drundar |  | ok |  | ok |  |
| endbad |  | ok |  | held | the ending: a scene holds the camera at every place |
| endgood |  | ok |  | held | the ending: a scene holds the camera at every place |
| fay1 |  | ok |  | ok |  |
| fay2 |  | fault | game | game | rim of the floor; partly also overhead |
| fay3 |  | ok |  | ok |  |
| faybonus |  | fault | ok | ok |  |
| fearboss | yes | ok |  | ok |  |
| firbonus |  | ok |  | fault | the clear colour (orange) is the "lava" below the cliffs: looking over an edge (by design) |
| fire1 | yes | ok |  | ok |  |
| fire2 |  | ok |  | ok |  |
| fire3 | yes | ok |  | ok |  |
| fire4 |  | ok |  | ok |  |
| fire5 |  | ok |  | fault | floating ground: the clear colour beyond the rim, partly also overhead |
| firmedal |  | ok |  | ok |  |
| honor | yes | ok |  | ok |  |
| honor2 |  | ok |  | ok |  |
| hub | yes | ok |  | ok |  |
| hub2 |  | fault | ok | fault | hole=1(p0-h2) |
| inmine1 | yes | fault | fault | ok |  |
| inmine2 |  | ok |  | ok |  |
| innmedal |  | ok |  | fault | hole=1(p2-h7) |
| innovat1 | yes | fault | ok | ok |  |
| innovat2 |  | fault | ok | ok |  |
| innpit |  | ok |  | ok |  |
| intro |  | n/a |  | n/a | not-entered |
| islc1 |  | ok |  | ok |  |
| islc2 |  | ok |  | ok |  |
| islcave1 |  | ok |  | ok |  |
| islgnome |  | ok |  | ok |  |
| islgoth |  | fault | fault | fault | hole=1(p3-h6) |
| islsm1 | yes | ok |  | ok |  |
| islsm2a |  | ok |  | ok |  |
| islsm2b |  | ok |  | ok |  |
| islsm3a |  | ok |  | ok |  |
| islsm3b |  | fault | ok | ok |  |
| nit1 | yes | ok |  | ok |  |
| nit2 |  | fault | ok | held | a scene held the camera at every place in this walk (it walked on 10-17 and in the first walk) |
| nitbon2 |  | ok |  | ok |  |
| nitbonus |  | fault | ok | ok |  |
| nitdung1 | yes | ok |  | fault | hole=5(p0-h7) |
| nitdung2 |  | ok |  | fault | hole=3(p3-h4) |
| nitdung3 |  | fault | game | game | no floor drawn at the start, in the game's own overhead view too (emulator picture the same): the level's |
| nitdung4 |  | fault | fault | fault | hole=2(p2-h5) |
| nitmar1 |  | ok |  | ok |  |
| nitmedal |  | fault | ok | ok |  |
| obsfor1 |  | ok |  | ok |  |
| obsidian |  | fault | fault | fault | 10-17: view tilted about 25 degrees up by the swing tilt (driver), and a chunk-box hole (8.4); now 3 looks at one place |
| pvparena |  | n/a |  | n/a |  |
| pvpbas |  | n/a |  | ok |  |
| pvpblo |  | n/a |  | n/a |  |
| pvpblo2 |  | n/a |  | n/a |  |
| pvpfire |  | n/a |  | n/a |  |
| pvpfire2 |  | n/a |  | n/a | beyond the rim, partly also overhead |
| pvpinn |  | ok |  | n/a |  |
| pvpnit |  | fault | ok | ok |  |
| pvptor |  | n/a |  | ok |  |
| pvpval |  | n/a |  | n/a |  |
| shame1 |  | fault | fault | fault | hole=5(p0-h3) |
| stobonus |  | ok |  | ok |  |
| stomedal |  | ok |  | ok |  |
| storm1 | yes | ok |  | ok |  |
| storm1a |  | fault | fault | fault | hole=4(p0-h2) |
| storm1b |  | fault | ok | ok |  |
| storm1c |  | fault | fault | fault | hole=1(p1-h4) |
| storm2 |  | fault | fault | fault | beyond the rim, partly in the overhead view too; 2 looks |
| storm3 |  | fault | ok | fault | hole=7(p0-h3) |
| storm4 |  | ok |  | ok |  |
| storm5 |  | ok |  | ok |  |
| strife |  | ok |  | ok |  |
| swamp1 | yes | fault | ok | ok |  |
| swamp2 |  | fault | ok | fault | hole=1(p2-h5) |
| torbonus |  | ok |  | ok |  |
| tormedal |  | ok |  | ok |  |
| torment0 |  | ok |  | ok |  |
| torment2 |  | ok |  | fault | hole=2(p2-h3) |
| torment3 |  | ok |  | fault | hole=1(p3-h2) |
| tormenta | yes | ok |  | ok |  |
| tormentb |  | ok |  | ok |  |
| valmedal |  | fault | fault | ok |  |
| valor | yes | ok |  | ok |  |
| valor2 |  | ok |  | ok |  |
| wat1 | yes | ok |  | ok |  |
| watbonus |  | ok |  | fault | hole=1(p3-h2) |
| wate2a |  | ok |  | ok |  |
| wate2b |  | not walked | ok | fault | hole=1(p3-h6) |
| wate2c |  | ok |  | fault | hole=6(p0-h3) |
| water1 |  | fault | ok | ok |  |
| watg2a |  | ok |  | ok |  |
| watg2b |  | not walked | ok | ok |  |
| watg2c |  | ok |  | ok |  |
| watmedal |  | fault | ok | ok |  |

Summary (10-19, `rta_app_next`): 111 levels, 70 ok, 3 `game` (`bastion1`, `fay2`, `nitdung3`), 24
flagged, 3 `held` (the two endings, and `nit2`, where a scene held the camera at every place this
time; on 10-17 and in the first walk today it walked), 11 n/a (arena and PvP kinds without a
single-player start, and `intro`). On 10-17: 62 ok, 3 fixed, 31 flagged, 12 n/a, 3 not reached.
Most of the 24 flags are 1 to 3 looks of 40: thin strips of the clear colour at a screen edge or
over a ledge, or a cell still loading right after a turn. They move from place to place between
walks, because the character's route depends on the fight and the timing; `storm1b`, `nitbonus`,
`inmine1`, `fire3` and `wat1` were flagged in one walk and clean in the next. Larger and repeated:
`firbonus` (13: the orange clear colour is the "lava" below the cliffs, the edge looked over),
`fire5` and `storm2` (beyond the rim, partly in the overhead view too), `storm3`, `wate2c`,
`nitdung1`, `shame1` and `storm1a` (5 to 7). These were not each looked at.

### 8.7 Checked, and left

* **Simulation** (`local/fp-ready/rig/check_rig.py` on `rta_orig_cells`, the unpatched game with
  these sources). The first-person comparison report is byte-identical to section 13's
  (SHA-256 `ba217b43…`), and the overhead report to the reference (`9cdc53c1…`). Against the hands
  work's final first-person TSV every column is identical, `pool` included (the known 1,465
  rows of the eye-collide fix are in both). Only an earlier build differed, in `cosmetic` at 8 ticks (5250 to 5285 of
  `valor`) with the sweep on (8.3); with the program as delivered (sweep off) the TSV is
  identical in every column. The overhead TSV is identical to the hands work's.
* **Left:** cells that were never in reach of the stream point stay without textures (the far
  focus that would reach them is off: it made holes near the feet). The guard of 8.2 can leave far creatures out in a crowded level. The 256-unit chunk
  margin is a margin, not the cause (which boxes are wrong, and by how much, was not measured).
  Not looked at in the Godot drawer. Not measured paced: what the shelf,
  and the wider tests cost a frame.

### 8.8 2026-10-20: the eight that kept their flags (Ran)

Evidence root `local/fp-world3/` (not tracked): walks `walk8-a` to `walk8-c` (the eight levels, after each
step), `all-2` (all 111 with the final build), probes `p-*`, `s*-*`, `nb*-*` beside them, sheets in
`sheets/` (`<level>-before.png` and `<level>-after.png`: the forty looks of a walk, undrawn pixels magenta;
the pairs beside them), scripts in `work/` (`probe.py`: the walk's start, chosen headings, variants given as
control lines; `spot2.py`, `spot3.py`: the player put at a place; `dumpan.py`: the chunk dump by distance and
angle; `flags.py`: every look a walk flags).

`firbonus`, `fire5`, `storm2`, `storm3`, `wate2c`, `nitdung1`, `shame1` and `storm1a` were flagged in every
walk of 8.6. Their pictures were looked at and the flagged places probed with switches changed one at a time
(`app world set`, `app view set`; the test aids are below). Four causes, three of them general:

1. **The near plane in a wall beside the eye** (`nitdung1`, `shame1`, `wate2c`, `storm1a`, `storm3`). **Ran:**
   a strip of nothing along a side edge of the picture, or a wedge in a lower corner, where a wall alongside or
   a corner stands closer than the near plane reaches (`sheets/nitdung1-w.png`, `shame1-w.png`, `wate2c-w.png`;
   `nd1-probe.png`). With the near plane at 4 every one of them closes (`body full`, `near 4`), and with every
   box passing (`world.nocull`) none does. **Read** (`app/fpview.cpp`, 8, cause 1): the eye placement tested the
   level along the heading and at 35 degrees to each side. 35 is the vertical half-angle of the view of 70; the
   picture's side edges are at 43 degrees at 4:3 and at 51 at 16:9. A wall alongside is also not helped by going
   back. **Fix:** the placement now (1) steps sideways, at most 12 units, away from a wall that is nearer to the
   head than the near plane's half width; (2) goes back along the heading (at most 16 behind the head, as
   before) until the way from the head to the near plane's middle, both ends and both lower corners is clear,
   at the picture's real width (`gfxrt::view_aspect()`, new); (3) in a corner where no place is clear, brings the
   near plane in (14, 10, 7, 5). `storm1a` at (-192, -490), 16 headings: two headings with 14 and 12 % of the
   lower third undrawn with steps 1 and 2 alone (`s-storm1a/`); none with step 3 (`s4-storm1a/`; the look
   with near planes 14, 8 and 4: `s3-s1a.png`). The placement takes 8 terrain queries at a free
   place and 18 near a wall, 20 to 45 microseconds (`view.eye-dump`).
2. **Ground of a resident cell left out for want of its texture** (`storm1a`'s pit floor beside the start).
   **Ran:** `world.dump` at that look: 43 chunks of resident cells put nothing into the list; their texture header
   (+0x14) was empty, and the shelf had all 43. Waiting 400 frames, or the far focus, changed nothing; the
   overhead view of the same place has none of them. **Inferred:** the texture thread's page pool keeps what
   the last frames drew and a view draws far more, so a texture is prepared, pushed out and asked for again.
   The thread's queue drains (`work/qprobe.py`: 0 to 4 waiting). **Fix (`app/fpworld.cpp`):** such a chunk is drawn
   from its shelf copy the way a chunk of a non-resident cell is. Undrawn share of the lower third: 0.23 before,
   0 after. `app world info` counts these chunks ("of a resident cell").
3. **The skirt hid level geometry** (`firbonus`, every flag of it). **Ran:** a band of the clear colour between the
   cliffs and the lava sea below them (`sheets/firbonus-w.png`). With `world.skirts off` it is gone
   (`fb-skirt.png`). **Read** (`render/gs.cpp`, `Gs::draw_fill`): the skirt is drawn before the frame's first plain
   level chunk, blended, and it wrote its depth. It is made from the terrain, which does not have the lava sea
   (water-kind chunks). So it hung over the lava nearer to the eye, hid what was drawn behind it later, and
   where its alpha was low the clear colour showed. **Fix:** a skirt is drawn at the farthest depth and writes
   none. It is a background, seen only where nothing of the level is drawn (`fb-skirt3.png`: the lava is
   there). The OpenGL program only: the Godot drawer takes the meshes itself. **Godot, 2026-10-21 (Ran)**: the same
   in scene mode - `firbonus` at its start, first person, heading 6 of the probe above: a pale band over the lava at
   the right edge with the fill on, gone with `app look fill off` (1.45 % of the lower picture differs). The drawer
   draws the skirt in the transparent pass right before the first piece of the level, depth tested and **written**
   (`fill.gdshader`, `depth_draw_always`). Fixed the same way: skirts have their own shader, `fill_skirt.gdshader`
   (`depth_draw_never`, the body shared in `fill.gdshaderinc`; `RtaDrawer.set_fill_shader(shader, skirt_shader)`).
   Drawn before the level and writing no depth, the skirt is covered by whatever of the level lies behind it - the
   same as the farthest depth. After: fill on and off give the same lower picture at both headings (0 % differs);
   the lava is there (`local/aim/r8/skirt/compare.png`). Ceilings are unchanged.
4. **Beyond the rim, the level's own** (`fire5`, `storm2`; also `torment2`, `fay2` and `pvpfire2` in the full
   walk). **Ran:** looking over the edge of floating ground into the chasm or the void below
   (`c-storm2.png`, `c-fire5.png`, `all2-rest.png`). The game's overhead view shows the same void beside the
   character at most of those places (`as-overhead`). The levels are made that way. Not changed.

**Before and after, the eight** (looks flagged of 40; the walks route the character by the fight, so the
places differ from walk to walk):

| Level | 10-19 (8.6) | after 1 (`walk8-a`) | after 1+2 (`walk8-b`) | all four (`walk8-c`) | all 111 (`all-2`) |
| --- | --- | --- | --- | --- | --- |
| firbonus | 13 | 13 | 13 | ok | ok |
| fire5 | 6, +11 as overhead | 7 | game | 4, +6 as overhead | game |
| storm2 | 2, +6 as overhead | 2 | 2 | 2 | 2, +6 as overhead |
| storm3 | 7 | 5 | 2 | ok | 1, +4 as overhead |
| wate2c | 6 | 5 | ok | ok | ok |
| nitdung1 | 5 | 3 | ok | ok | ok |
| shame1 | 5 | 2 | ok | ok | ok |
| storm1a | 4 | 4 | ok | ok | ok |

"after 1" is the first placement change (sideways and the real width, without the nearer near plane), "after
1+2" adds the nearer near plane in a corner and the shelf for unprepared textures, "all four" adds the skirt
change. The full walk is the final build (with the lower corners).

**All 111 levels (`all-2`, the final build):** 93 ok, 3 `game` (`bastion1`, `fire5`, `nitdung3`), 7 flagged, 2
`held` (the two endings), 6 n/a (five arena and PvP kinds without a single-player start, and `intro`). The
10-19 walk (8.6): 70 ok, 3 `game`, 24 flagged, 3 `held`, 11 n/a. `compval`, `pvparena`, `pvpinn`, `pvpval` and
`pvpfire2`, n/a then, had a start this time and were walked; `nit2`, `held` then, walked (ok). Of the 24, 20 are now ok or `game`. The 7:

| Level | 10-19 | now | What |
| --- | --- | --- | --- |
| storm2 | flagged | 2 looks | beyond the rim (4) |
| storm3 | flagged | 1 look | 6 % of the lower third at one place; not looked at further |
| torment2 | flagged | 3 hole and 1 void | beyond the rim: floating halls over the void (4) |
| fay2 | `game` | 6 hole and 1 void, +27 as overhead | beyond the rim; the places differ from 10-19's |
| pvpfire2 | n/a | 17 hole and 8 void, +9 as overhead | floating islands, beyond the rim; walked this time (a start was found) |
| stobonus | ok | 1 look | 4 % at one place |
| nitbonus | ok | 8 hole and 4 void | one place (248, 3322): nothing below a canopy-like surface ahead. The same with the program as it is (`rta_app`) and with the old skirt (`nbs-*`); not the changes of this section, not looked at further |

The endings: after `endgood`'s scene the walk went on in the game's save menu ("overwrite save game?") and
every later look was that menu. Those rows were thrown away and the levels walked again from a fresh start,
`endgood` last.

**Simulation (Ran, `local/fp-ready/rig/check_rig.py` on `rta_fpw_orig3`, the unpatched game with these
sources).** The first-person comparison report is byte-identical to section 13's (SHA-256 `ba217b43…`), and the
overhead report to the reference (`9cdc53c1…`). The first-person TSV is identical in all 28 columns to the
hands work's arms run (`rig-arms`), and so to the run with the eye collision off (`rig-nocol`). Against 8.7's
run (`rig-cells-first`) only `pool` differs, at 1,465 rows: the rows the old eye placement changed (8, cause 1)
are back to the arms run's values. The overhead TSV is identical to 8.7's and to the hands work's in every
column. Everything changed here is drawing: where the eye stands and how near its near plane is, which texture
copy a chunk is drawn with, and the depth of the skirt.

**Test aids added** (not in the settings file): `app world set world.dump N` (the chunks of the next N level
walks to the output: box test, cell, slot, texture header, words put into the list), `world.nocull on|off`,
`world.box-xy N`, `world.box-z N` (until now options only); `app view set view.eye-dump N` (the eye placement of
the next N passes: distances to the walls, shift, place, near plane, queries, time), `view.arms-near N` (the
near cut of arms mode, default 14).

**Left:** the rims (4) are the levels' design; a fill under them would be a new part, as the skirt is for the
outer rim. `nitbonus` at (248, 3322) is not explained. With the nearer near plane in a corner, more of the
own figure can show in an attack (not looked for). The skirt was still not seen in a picture where it fills
anything (fire1 and storm1a, eight headings at the start: skirt on and off differ in under 450 pixels of
129,600). Not measured paced.
