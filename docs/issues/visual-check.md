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

## Second pass (2026-10-12, working notes; the final status is written at the end of this pass)

Working build `local/play-playable-build`, pictures and logs under `local/vq.nosync` (helpers in its
`tools/`). New control-socket aids: `drawlog FILE [frames [x0 y0 x1 y1]]` (every draw of a frame with
its GS registers; inside a rectangle of the draw buffer every primitive vertex by vertex), and the
switches `upscale 0|1`, `edge 0|1`, `texcentre 0|1`, `texorder 0|1` for the same frame before and after.

- Top line of the menu screens: the game's own. The backdrop sprite is drawn from line 1 of the 448
  (with the display patches; as shipped from line 2 on one field and from -0.5 on the other), so line 0
  keeps the colour the draw buffer was cleared to. A console sends that line; a television does not
  show it (overscan). Handled at the edge of the picture: the outermost line and the same share of the
  width are not presented.
- Dust motes: a particle cell of 32 x 32 texels holding eight specks, drawn 3 to 5 pixels wide and read
  unfiltered. Rain: GS lines, drawn one pixel of the enlarged buffer wide. Automap: a strip of tiles
  of 10 x 10 texels from a 120 x 160 sheet, read unfiltered because the interface drawers leave
  "nearest" set. All three are given the higher-resolution treatment (README table).
- Found on the way: Play!'s filter for indexed textures reads half a texel up and to the left. The same
  paused frame with the pack on and off differs by 4.52 of 255 before and 2.96 after (strife).
- Resolution factor changed in a running game: texture knowledge is kept (0 draws by memory after
  4 -> 1 -> 4 several times; before 357 a frame).
- Pictures popping in: read largest-on-screen first, kept through a menu visit; figures in the README.
- Mission menu: the hub's `PushTrigger` at (118.9, 354.7, -6), radius 79, action `callScri8e04`
  (-> `warnDetect` -> `activateMissionMenu`), locked by `lockDetect` unless a mission is available and
  not complete. The earlier attempt had marked every mission complete, which locks it.
