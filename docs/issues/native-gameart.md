# The game's own art in the portal and the HUD (Godot)

Started 2026-10-13. The owner: "Can you use the games assets and upscale it with that ui". The portal
(`native-portal.md`) and the new HUD (`native-hud.md`) are drawn in a clean style of their own; this work
gives both the look of Champions: Return to Arms with the game's own pictures, **read at run time from the
player's own disc image** and sharpened where the player has the 4x art pack. Every statement says **Ran**
(with what was seen) or **Read**. Kept current; a successor needs only this file.

**Nothing of the game is in the repository.** `tools/godot/project/gameart/` holds code and a catalogue of
WHERE pictures are (archive, entry, field rows, rectangle, the pack's file name) - no pixels, no text of the
game. Pictures are decoded on the player's machine and cached under the player's data folder
(`user://gameart/cache`); tests keep theirs under `local/gameart/godot-home/` (HOME is redirected there).

## STATE (2026-10-14 01:40) - first version finished; nothing of this work is running

| Part | State | How it is known |
|---|---|---|
| loader `gameart/gameart.gd` (GDScript only, no native helper needed) | **done** | **Ran**: all 122 catalogue pictures decoded from the disc equal, pixel for pixel, what `tools/play-net/disctex.py` + weaving give (`local/gameart/tools/compare.py`: 122 same, 0 different); every catalogue name equals the content figure the Python tool computes for that entry |
| catalogue `gameart/catalogue.gd` (written by `local/gameart/tools/mkcatalogue.py`) | done: 122 entries, 68 with a 4x pack file on this Mac | |
| portal skin `gameart/portal_skin.gd` | **done** | **Ran**: the portal's own picture walk (`portal/dev/shots.gd`: states, friends, room, settings, ratios: 71 pictures) with the game's art and the same 71 clean, 0 script errors. Each of those runs was a FIRST start (empty cache): the art arrived from the thread and the portal switched over by itself |
| HUD skin `gameart/hud_skin.gd` | **done** | **Ran**: a fight in `valor` overhead, third person and first person at 16:9 (1920 x 1080) and overhead at 4:3 with three party frames, chat and a boss bar; the same clean; 0 script errors |
| the switch "Interface art: the game's own / clean" | **runs** in the portal's settings (Interface page); default the game's own when the disc's art is found | settings-interface pictures; **without a disc** (RTA_DISC unset, no settings file) the portal is wholly clean, `pictures/portal-no-disc-falls-back-clean.png`. **Not run**: changing the choice while the program runs (the code reinstalls the skin, relays the portal and sends `theme` to a running HUD) |
| hooks in the portal's and the HUD's scripts | **written as a patch, not merged**: `tools/godot/gameart-hooks.patch` | applied to the staged copy only (`local/gameart/hooks.py`) |
| a disc chosen after the start (portal's disc screen) | written: the backdrop node looks again every 2 s while there is no disc | **not run** |

Pictures, `local/gameart/pictures/` (before = `-clean`, after = `-game`):
portal `state-home`, `friends-six`, `room-guest-ready`, `settings-interface`, `ratio-4x3-home`,
`ratio-720p-friends`; HUD `hud-over169-2600/2760` (overhead), `hud-third169-2700/2760`, `hud-first169-2600/2760`,
`hud-over43-2650` (4:3); `portal-no-disc-falls-back-clean.png`.

## What is read from where

- **The disc image**: the path the game scene uses (`--disc`, `$RTA_DISC`, `user://settings.cfg [game] disc`).
  ISO 9660 and the game's `.LMP` archives (`BG/DATA/*.LMP`: a count, then {name offset, data offset, size})
  are read with `FileAccess`; a `.tex` entry is the GS upload the game sends (a header, then GIF packets:
  palette and image transfers), decoded like `tools/play-net/disctex.py` (plain 4/8/32-bit uploads and
  32-bit pieces swizzled into an 8- or 4-bit page).
- **Two fields**: every interface picture is two field pictures one above the other; the catalogue gives the
  rows of a field (from the pack's `.json` files where the art pack had seen the picture, else measured by
  the least comb when woven, e.g. the title font: 239 rows of a 480-line page). The race portraits
  (`HEADPIC.LMP`) are not woven.
- **Fonts** (`FONT.LMP gamefontmed.fnt`, `PVPFONT.LMP pvpfontbig.fnt`): header {u16 glyph count, u16 8,
  u32 kerning count, u32 glyph records, u32 kerning records, u32 texture}, a 256-entry u16 character map at
  0x14, 16-byte glyph records {code, u0, u1, v0, v1, y offset from the line's top, advance, first kerning
  record}, 6-byte kerning records {left glyph index, right glyph index (the owner), amount}, then a `.tex`
  whose packet offset (+0x10) is not 0x80 but its own (0xb4). Glyph rectangles are in texels of the WOVEN
  page. Made into a Godot `FontFile` (bitmap, glyph index = character code, scaled; mipmaps). The text
  font also holds the PlayStation button glyphs: `}` square, `|` triangle, `{` circle, `~` cross,
  0x83 L1, 0x84 L2, 0x88 L3, 0x85 R1, 0x86 R2, 0x87 R3, 0x7f..0x82 the four arrows (catalogue BUTTON_CHARS).
- **Skill icons**: each skill's own icon is the entry its `Skill<Name>_slot7` returns (symbols/*.tsv notes);
  which skill id is which class: the vtable at skill object +0x60 in a memory image of a running game
  (`g_skillTable` 0x41b170). 77 of 101 skills have one (catalogue SKILL_ICONS, by skill id).
- **The art pack** (`--art-pack DIR`, `user://gameart.cfg [gameart] pack`, `user://art-pack`, on macOS the
  emulator's `~/Library/Application Support/Play-RTA/textures/replace`): when it has the file of the
  catalogue's name, the first woven copy of that file is used (4 x the texels), cut to the same rectangle.
- **Alpha** is the console's (128 = opaque) and is doubled once at load.
- A picture drawn at less than half its loaded size is drawn from a copy made smaller with Lanczos
  (`GameArt.tex(id, scale)`), so the 4x art is neither grainy nor blurred at HUD sizes.

## The catalogue (`gameart/catalogue.gd`, names only)

| id | from | used for |
|---|---|---|
| frame_topleft .. frame_botright, frame_center | INTERFAC tile*.tex (32 x 32 corners and rails; 320 x 224 slate) | every panel: slate in a rounded shape under a bronze rim (rail at texels 2..8 of 32; the corner ornament's inner edge is a circle of 26 texels round the inner corner) |
| button | INTERFAC button.tex (pill at texels 11..72 x 2..33; disc only, no 4x) | buttons, key caps (three slices) |
| dialog | DLGBOX box.tex | (catalogued; not used yet) |
| statusbar, statusbar_glow, bossmeter, fieldmeter | HUD / BUST | (catalogued; the HUD's own layout is kept, so these whole-HUD frames are not used) |
| bar_red, bar_blue, bar_green, bar_yellow | HUD bar_*10.tex, BUST bar_yellow00.tex | bar paint (the last 6 texels, the game's cap block, are left out) |
| socket | BUST frame.tex | the level ring, the radar's disc, the portal's medallions |
| gold | HUD gold03.tex (pile at texels 1..29 x 21..34) | the coin |
| icon_count*, icon_ic* | ICONS.LMP | potion flasks, quick-slot abilities |
| logo | FRONTEND title.tex, texels 3..357 x 0..106 | the portal's top bar |
| shot_lintro, shot_lhub, shot_lbastion, shot_lhonor, shot_lendgood, shot_lbossevi | L<level>.LMP shot.tex (640 x 320 at the left of a 1024 page, two texels of rim left out) | portal backdrop (lintro), character card paintings (by class) |
| head_* | HEADPIC.LMP (race portraits) | catalogued; not used: the portal does not know a character's race |
| font_med, font_small, font_title, font_title_small | FONT / PVPFONT .fnt | text, headings |

## The skins

- **Portal** (`portal_skin.gd`, UI.skin): backdrop painting (LINTRO, cover, darkened to the bottom and left;
  hidden while a game's blurred picture is behind), the logo, frames for panels / tiles / rows / fields /
  choices, bronze buttons (primary: a gold wash; danger: red; quiet "ghost" buttons: a faint frame that
  lights with the focus), medallions on the bust's socket, character card = frame round a painting,
  PlayStation hints with the game's glyphs, fonts: headings in the title face, text in the text face.
  The focus ring stays the portal's gold ring.
- **HUD** (`hud_skin.gd`, a style.gd skin): frames, bar paint in a dark channel with a bronze edge, the game
  font from 13 design pixels up (smaller: the clean font), potion icons, gold pile, the socket for the level
  ring and the radar, the skill's medallion in the quick slots, face buttons from the font, key caps on the
  bronze button.

## Fell back to the clean style, and why (judged in the pictures)

- The portal's notice card, avatars (initials), status chips ("5 online"), the keyboard key caps of the hint
  bar, the row's inline action chips: drawn by code paths without a hook; they read well and are left clean.
- Status icons, skulls, the compass strip, the arrows of attackers out of sight: the game has no matching art
  (its HUD shows none of these) - clean.
- Portal text under 15 screen pixels (`portal_skin.gd font_at`, through the hook `UI.font_at`): the clean
  font - at 1280 x 720 the game's letters for the friends' status lines were not readable (judged in
  `ratio-720p-friends`).
- Text under 13 design pixels in the HUD: the game's letters are 14 texels high caps with a baked rim; below
  that size they turn to grey mush - the clean font.
- The race portraits: not used, the portal has no race for a character.
- The game's whole-HUD frames (statusbar, bossmeter): would force the 2005 layout; the HUD's layout is kept.

## Cost (Ran, this Mac under load 25-40)

| | |
|---|---|
| first start, no pack: decode all 122 from the disc | 1.6 s on a worker thread; the program does not wait (start() returns in 0.4 ms); clean look until then, then everything redrawn once |
| first start with the 4x pack | 3.9 s on the thread (reading the pack's PNG files; the 6 paintings 0.5 s each) |
| cached start | **4-5 ms** (the index is read; nothing else) |
| a picture's first use | read from the cache when first drawn: all 122 together 0.3 s, the small ones well under 1 ms |
| cache size | 52 MB with the pack (zstd-compressed RGBA), less without |
| per frame, HUD (`app hud cost`, the same fight unpaced, 5,486 frames each) | scripts 236 us game / 249 us clean (equal within noise); drawing 288 us game / 275 us clean (+13 us, +5 %: a frame is about 10 textured rectangles and a polygon where the clean one has 2-3 style boxes). The most expensive single frame of the game run, 2.9 ms, is the first one that draws the art (pictures read from the cache, small copies made); after that none |
| per frame, portal | not measured: the portal draws only when something changes (focus easing, a list moving); each surface is about 10 draw calls instead of 2-3 |

## What must be merged where

1. `tools/godot/project/gameart/` (new directory): gameart.gd, catalogue.gd, hud_skin.gd, portal_skin.gd.
2. `tools/godot/gameart-hooks.patch` (HUD agent: hud/style.gd, bottom.gd, status.gd, compass.gd, hud.gd;
   portal agent: portal/ui.gd, widgets.gd, portal.gd, screens/settings.gd). Every hook does nothing when no
   skin is set, so the clean look is unchanged without the disc. In words:
   - style.gd: three more skin hooks `slot_icon(ci, rect, slot, ready)`, `face_button(ci, c, r, label, alpha)`,
     `socket(ci, c, r, alpha)`; bottom.gd calls the first two, status.gd (level ring) and compass.gd (radar)
     the third; hud.gd: with no theme set, `gameart.gd wanted()` picks `res://gameart/hud_skin.gd`.
   - ui.gd: `static var skin` and `skinned(what, args)`; panel() asks it; widgets.gd: each widget's body box
     (`surface` kinds button_<kind>, tile, medal, choice, gauge, field, row), the Portrait (`portrait`), the
     hint glyphs (`pad_glyph`); portal.gd: `portal_skin.gd install(self)` at the start of `_build_layer`,
     `decorate` after the background, `logo` in TopBar._draw; settings.gd: the "Interface art" row.
3. Nothing in the extension (no native helper: GDScript decodes all 122 pictures in 1.6 s).

## How it is built and run here

- `python3 local/gameart/ga.py stage` - `local/gameart/stage`: `tools/godot/project` as it is now, the hooks
  applied (`local/gameart/hooks.py`), `local/gameart/dev` (tests) as `res://gameart_dev`, the binaries of
  `local/godot-spike/project/bin` by link.
- `python3 local/gameart/ga.py run NAME [--no-disc] [--keep-home] ... -- ...` - Godot at nice 10, HOME and
  XDG in `local/gameart/godot-home/NAME`, a run's `--data` emptied first, pid in `local/gameart/test/NAME/pid`.
- `local/gameart/hudset.sh game|clean` - the HUD pictures (routes from `local/godot-hud/routes`, read only).
- Portal pictures: `ga.py run portal-ART res://portal/dev/shots.tscn -- --out DIR --portal-data DIR --only ...
  --art=game|clean --art-pack DIR`.
- `local/gameart/tools/`: lsdisc.py, extract.py (look at the disc's art), mkcatalogue.py, compare.py.

## Processes

Every Godot of this work is started by `local/gameart/ga.py run`, which records its pid, waits for it and
kills it on a time-out. **Checked at the end (01:40)**: none of the pids in `local/gameart/test/*/pid` exists;
no shell script of this work (hudset.sh, after.sh, hudrun.sh, the two log watchers) is running. The one Godot
running then (pid 13613, `local/godot-spike/project`) is another agent's. Test homes trimmed: one cache kept
(`local/gameart/godot-home/cache-pack`, 53 MB); `local/gameart` is 142 MB in all.
