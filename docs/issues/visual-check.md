# Visual check of the Mac build: confirmed faults

Stable build at resolution factor 4 with the enlarged-art pack, offline, 2026-10-12. One line each: what,
where, class, severity. Classes: emulator (there at factor 1 with the pack and the display patches off),
display patches, upscaling (only at factor 4), art pack, ours otherwise (texture replacement, texture
identity), the game's own.

| What | Where | Class | Severity |
|---|---|---|---|
| Effect sprites over fire are rectangles of multicolour noise and blue/white stripes | around lava golems in fire3; above the catapult fire in the blood1 arrival cutscene; above every torch, brazier and lamp flame (blood1, strife, islc1, swamp1, honor, bossgood) | emulator: same at factor 1, pack off, display patches off, and with textures known by upload, by memory and by address | high |
| The game runs at 24-37 frames a second while replacement pictures are being read, when the computer is busy; the same scene with the pack off holds 59; 60 when the computer is quiet | hub, and on arriving in a level | ours (texture replacement), under load only | medium |
| The pack is one third complete (40,731 replacements for 120,039 dumped textures); the shop's backdrop painting has no replacement and was never dumped | level art in the fire, storm, fay, nit, dis, honor and boss levels; every shop screen | art pack | medium |
| The count of pictures still to be read never returns to zero once a texture is not drawn again; no cost in speed | any game after a few levels | ours (texture replacement) | low |
| After the resolution factor is changed in a running game, up to 357 draws a frame find their texture by reading video memory instead of by upload | hub and levels after the change | ours (texture identity) | low |
| The top half line of the picture has the title scene's sky colour | title, Options, Controls, Player 1 Configuration | emulator or the game's own (same at factor 1, pack off, display patches off) | low |
| One white console pixel at the left screen edge | skills page of the inventory | emulator or the game's own (same at factor 1, pack off, display patches off) | low |
| Dust motes are dotted squares four pixels wide | strife | upscaling (pack on and off; factor 1 not compared) | low |
| The automap's outline is stair-stepped beside smooth icons | any level, R3 | upscaling (factor 1 not compared) | low |
| Enlarged pictures replace the originals in view during the first moments in a level, for longer when the computer is busy | every level | art pack | low |

No fault was found that is there only with the display patches. No fault was seen in the new-game menus,
character creation, the HUD, the pause menu, the inventory pages, the skill and spell-book screens, the
shop lists, dialogue, level-up, the save-point and memory-card screens.

Not reached: death, a chest or door opening, credits and end films, the player-against-player, medal and
bonus levels, the spells of ten of the twelve class choices. torment2, swamp1 and arachna1 were seen only
from the arrival camera.

## Status after the check (2026-10-12)

- The noise over fire and around the lava golems is an emulator fault and is fixed in the working build: the
  game copies a piece of its 16-bit draw buffer into a 16-bit texture and draws it back displaced; the
  emulator wrote that copy into video memory as 32-bit pixels. It is now kept as a texture of its own
  (`tools/play-net/README.md`).
- The count of pictures still to be read is fixed in the working build: a picture whose texture has not been
  drawn for 120 frames is given up, and a non-zero count no longer makes every texture be set up again.
- The slow-down while pictures are read was seen only with the computer heavily loaded; it was not
  reproduced on the fixed build.
- The art pack was still being made when the check ran.

## Second pass (2026-10-12): the remaining faults, and what the first check did not reach

Working build `local/play-playable-build` (source: `local/play-playable` = `tools/play-net/play-net.patch`
on Play! 83700b2c plus `tools/play-net/src`; the patch on disk reproduces the tree, checked by applying it
to the pristine files). Draw-only: six files of the graphics handler and `src/Rta.cpp`; the shared patch
file, the section list and the set figure (3f5b1e14) are untouched. Pictures, logs and helpers:
`local/vq.nosync` (`shots/`, `sheets/`, `logs/`, `tools/`). How each fault was measured and changed is in
the fault table of `tools/play-net/README.md`; this page keeps the status.

New aids on the control socket: `drawlog FILE [frames [x0 y0 x1 y1]]` (every draw of a frame with its GS
registers; inside a rectangle of the draw buffer every primitive vertex by vertex), `shotview` (the
picture as presented), and four switches for the same frame before and after: `upscale`, `edge`,
`texcentre`, `texorder`.

### Status of the ten faults

| Fault | Class now | Status |
|---|---|---|
| Noise over fire | emulator | fixed before this pass (heat haze); to be looked at again in `fire3` with the final build (standing checks, below) |
| 24-37 frames a second while pictures are read, computer busy | ours | not seen again: level tours of this pass under a load average of 360-430 ran at 60 where no dump was being written (table below) |
| Art pack incomplete | art pack | the enlarging job's; 52,805 replacement files at the time of this pass |
| Count of pictures to be read never 0 | ours | fixed before this pass; still returns to 0 with the changes below |
| After a change of resolution factor textures are found by reading video memory | ours | **fixed**: what the game sent, the textures made of it and the replacement pictures are kept through a change of settings. Factor 4 -> 1 -> 4 several times in a menu, in `strife` and in the hub: `tex_by_memory` stays 0 |
| Top half line of the menu screens has the title's sky colour | the game's own | **handled at the edge of the picture**. `drawlog`: the backdrop is a sprite from line 1 to 449 of the draw buffer's 448 (as shipped, patches off: from line 2 on one field, from -0.5 on the other), line 0 keeps the clear colour. A console sends it, a television hides it (overscan). The outermost line of a field and the same share of the width (3 pixels of 640) are not presented; `edge 0` shows all |
| White pixel at the left edge of the skills page | the game's own (art) | **handled the same way**. It is the wizard's skill-tree page (both sexes; the other five classes have none): its picture `905de2357a18325f...-p19-512x852` has three leftover lines at the top, light grey (205) and transparent but for their first texel, and the page is drawn at the left edge of the screen |
| Dust motes are dotted squares | upscaling | **fixed**: a mote is a cell of 32 x 32 texels with eight specks drawn 3 to 5 pixels wide and read unfiltered; now filtered and read at the console's density. Rain (GS lines, a quarter of their width and light at 4x) is drawn a console pixel wide |
| Automap outline stair-stepped | upscaling | **fixed**: a strip of 10 x 10-texel tiles read unfiltered because the interface drawers leave "nearest" set; now filtered inside each tile |
| Enlarged pictures arrive after the scene is shown | ours (read order), emulator (half a texel) | **fixed as far as it can be** (a picture is still only asked for when it is first drawn): read largest-on-screen first at a priority a busy computer honours; kept wanted through a visit to a menu and handed over while the menu is up; beyond the memory allowed only as many go as it takes. Under a load average of 400: all in view after 0.22-0.26 s (release: 6.8-7.2 s). And the game's own textures no longer sit half a texel off their replacements (Play!'s filter for indexed textures), so the picture does not shift when one comes in |

Found on the way and fixed: Play!'s filter for indexed textures read half a texel up and to the left (the
same paused frame of `strife` with the pack on and off: mean difference 4.52 of 255 before, 2.96 after).

### What the second pass reached (pictures `local/vq.nosync/shots/t`, sheets `sheets/`)

Two labelled test instances at a time, 4x, pack on, texture dump into `local/vq.nosync/tex-*`.

- **Death and respawn** (`blood1`, hit points held at 1 among monsters): death effect, empty bar, the
  level's loading screen, back at the save point with its prompt. No fault. (`sheets/X-death.jpg`)
- **A chest opening** (`orkbox` of `blood1`): "Open chest", the lid, "Pick up 72 Gold", the gold counter.
  The action button has to be held about ten frames (the first check tapped it). No fault.
- **A door opening** (`cpdoor` of `torbonus`): "Open door", the leaf swings. No fault.
- **Mission menu**: opens at the hub's `PushTrigger` (118.9, 354.7, -6; radius 79; "Enter Planar
  Gateway", the action button) when a mission is available and not complete (`lockDetect`); the earlier
  attempt had marked every mission complete, which locks it. Missions, their pictures and texts, the
  strip of entries (story, medal round, bonus level) seen; no fault.
- **Both end films** (`endgood`, `endbad`: letterboxed, subtitles), "Saving Configuration", the save
  list; **credits** from the title's menu. No fault.
- **Player-against-player levels** (10), **medal levels** (9), **bonus levels** (8): entered by name.
  Alone in an arena the character starts outside its ground (only the clear colour is drawn: the
  game's own); the arenas were looked at beside the things placed in them. No fault.
- **torment2, swamp1, arachna1** in play, the camera following. No fault.
- **All twelve class/sex choices**: bag, statistics, quests, skill-tree page with every skill at rank
  10, the ring, and every active skill tried in the arena (`drunare`) with a melee and a ranged
  attempt: 71 different skills cast for certain (the earlier tour: 45). Not cast by any model: 5, 11,
  26, 34 ("requires a shield"), 38, 43-47 (bow skills), 49, 56, 57, 62, 64, 80, 90, 94, 96, 98, 99.
  No fault in what was cast; the ray polygons of the ranger's flash (skill 50) are the game's own (the
  same at 1x, pack off, smoothing off).
- A paused frame is not always still: with weather (snow in `stobonus`) consecutive paused frames
  differ by about 1 of 255 all over the picture - on today's release build too. Without weather they
  are identical (0.000).
- Art pack: flowing lines on the snow of `stobonus` (the known fault of fine low-contrast grain).

Level tours of this pass (2.5 s sample on arrival, dump on, load average 360-430): 60 frames a second
except where new textures were being written on arrival (`torment2` 42, `blomedal` 39, `watmedal` 47,
`firmedal` 32, `watbonus` 26: the video thread 20-36 ms a frame while PNG files are written).

### State at 15:45 (saved on the coordinator's word; finished and not finished)

Finished and in the build: the five changes above (edge of the picture; filtering of point-sampled
effects, the automap, points and lines; texel centre; texture knowledge kept through a change of
settings; read order, warm pictures, least-recently-used eviction), `drawlog`, `shotview`, the switches.
`tools/play-net/play-net.patch` is regenerated and reproduces the tree; `ctl.py` lists the new commands;
the README has the new rows (three places still marked `@@...@@`) and the changed texture section.

Not finished at this time:
- the standing checks on the final build (`local/vq.nosync/tools/std.py still | levels | haze`): still
  screens identical, 60 frames a second in `blood1`, `innovat1`, `shame1`, heat haze in `fire3`, the
  set figure in `rta.log`;
- before/after pictures of the wizard's skills page at 1x (`tools/after.py v7`); the same paused-frame
  and memory-limit comparisons on this build (`after.py flicker new`, `after.py lru new`; the release
  build's figures are in `logs/after.log`);
- the three `@@` places in the README and its "looked at" paragraph;
- handing the tours' dumps to the enlarging loop (`tools/handover.py`; 0 pictures new to the pack so
  far, a few dozen in its dump that are not enlarged yet).
