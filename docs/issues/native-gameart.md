# The game's own art in the portal and the HUD (Godot)

Started 2026-10-13. The owner: "Can you use the games assets and upscale it with that ui". The portal
(`native-portal.md`) and the new HUD (`native-hud.md`) are drawn in a clean style of their own; this work
gives both the look of Champions: Return to Arms with the game's own pictures, **read at run time from the
player's own disc image** and sharpened where the player has the 4x art pack. Every statement says **Ran**
(with what was seen) or **Read**. Kept current; a successor needs only this file.

**Nothing of the game is in the repository.** `tools/godot/project/gameart/` holds code and a catalogue of
WHERE pictures are (archive, entry, field rows, rectangle, the pack's file name) - no pixels, no text of the
game. Pictures are decoded on the player's machine and cached under the player's data folder
(`user://gameart/cache`); tests keep theirs under `local/gameart/godot-home/`.

## STATE (2026-10-13 23:35)

| Part | State | How it is known |
|---|---|---|
| loader `gameart/gameart.gd` (GDScript only, no native helper) | **done** | **Ran**: all 122 catalogue pictures decoded from the disc equal, pixel for pixel, what `tools/play-net/disctex.py` + weaving give (`local/gameart/tools/compare.py`: 122 same, 0 different); every catalogue name equals the content figure the Python tool computes for that entry |
| catalogue `gameart/catalogue.gd` (written by `local/gameart/tools/mkcatalogue.py`) | done, 122 entries, 68 with a 4x pack file on this Mac | |
| HUD skin, portal skin, the switch, pictures | in progress | |

Next: the HUD skin (`gameart/hud_skin.gd`), the portal skin and its hooks, pictures.

## What is read from where

- **The disc image**: the path the game scene uses (`--disc`, `$RTA_DISC`, `user://settings.cfg [game] disc`).
  ISO 9660 and the game's `.LMP` archives (`BG/DATA/*.LMP`: a count, then {name offset, data offset, size})
  are read with `FileAccess`; a `.tex` entry is the GS upload the game sends (a header, then GIF packets:
  palette and image transfers), decoded like `tools/play-net/disctex.py` (plain 4/8/32-bit uploads and
  32-bit pieces swizzled into an 8- or 4-bit page). A `.fnt` is the same texture behind a glyph table
  (section "Fonts").
- **Two fields**: every interface picture is two field pictures one above the other; the catalogue gives the
  rows of a field (from the pack's `.json` files where the art pack had seen the picture, else measured by
  the least comb when woven; the race portraits are not woven).
- **The art pack** (`--art-pack DIR`, `user://gameart.cfg [gameart] pack`, `user://art-pack`, on macOS the
  emulator's `~/Library/Application Support/Play-RTA/textures/replace`): when it has the file of the
  catalogue's name, the first woven copy of that file is used (4 x the texels), cut to the same rectangle.
- **Alpha** is the console's (128 = opaque) and is doubled once at load.

## Cost (Ran, headless, this Mac under load 25-40)

| | |
|---|---|
| first start, no pack: decode all 122 from the disc | 1.6 s on a worker thread; the program does not wait (start() returns in 0.4 ms) |
| first start with the 4x pack | 3.9 s on the thread (PNG reading of the pack files; the 6 paintings 0.5 s each) |
| cached start | **4-5 ms** (the index is read; nothing else) |
| a picture's first use | read from the cache when first drawn: all 122 together 0.3 s, the small ones well under 1 ms |
| cache size | 52 MB with the pack (zstd-compressed RGBA), less without |

## Processes

Every Godot of this work is started by `local/gameart/ga.py run`, which records its pid in
`local/gameart/test/NAME/pid`, waits for it and kills it on a time-out.
