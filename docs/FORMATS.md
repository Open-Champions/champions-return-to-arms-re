# File formats

What has been worked out so far, and the tool that reads each format. All integers are
little endian unless noted. "Unknown" means nobody has looked yet.

| Format | Status | Tool |
|---|---|---|
| `.GOB` archive | understood | `tools/gob.py` |
| `.LMP` lump | understood | `tools/gob.py` |
| `script.scr` level script | understood, all 51 opcodes in use decoded | `tools/scr.py` |
| `.cut` cutscene | header and key records understood; most camera key types unnamed | none yet |
| `objects.ob` object placement | property strings readable; record layout given below (from `docs/issues/sync-breakers.md`) | none yet |
| `.dbin` dialog trees | understood: 0x448-byte nodes with condition script, text key, voice name, speaker and choices — see [formats/anim-audio.md](formats/anim-audio.md) | `tools/anim_audio_info.py` |
| `*_dialog.bin` voice-stream directory, `.VAT` streams, `.vag` samples | understood: PS2 ADPCM throughout; directory gives offset, rate, stereo flag and language | `tools/anim_audio_info.py` (can decode to WAV) |
| `.anm` animation | understood: bind offsets, joint hierarchy, velocity-coded key stream at 60 ticks per second; not yet compared against the game on screen | `tools/anim_audio_info.py` (can dump tracks to CSV) |
| `.world` level geometry | understood: header, chunk tree, render batches (ready-made VIF packets), terrain heights and flags, path grid; water colour, waves and draw order are [formats/water-draw.md](formats/water-draw.md); a few fields still open — see [formats/world.md](formats/world.md) | `tools/world_info.py`; water in `tools/ref_waterdraw.py` |
| `.vif` models | understood: header, part and variant tables, attach points, meshes as VIF1 streams for the model vertex program (positions, normals, strips, texture coordinates, joint weights); the file holds no skeleton or texture name — see [formats/model-texture.md](formats/model-texture.md) | `tools/model_info.py` (can export OBJ) |
| `.tex` textures | understood: 0x80-byte header plus one GS upload packet; 8-bit images in GS memory order, some 4-bit and 32-bit, no mipmaps | `tools/model_info.py` (can export PPM/PGM) |
| `<LEVEL>.TEX` level textures | understood: cell directory, 0x40-byte headers, block-table form (every texture on the disc): 16 × 16-texel blocks coded with a canonical Huffman code over literals, back-references and a successor table, a shared palette per group, uploaded as 32-bit rectangles and sampled as PSMT8 — see [formats/level-texture.md](formats/level-texture.md). Blend, depth order, environment rows and automap tile codes: [formats/level-draw.md](formats/level-draw.md) | `tools/ref_leveltex.py` (can export PPM); draw state in `tools/ref_leveldraw.py` |
| `PICCACHE.DAT` inventory pictures | serialized header, GIF uploads, swizzle and field weave audited across 11,511 entries; visual comparison pending — [contract](formats/inventory-icons.md) | `tools/ref_inventory_icons.py` |
| `.fnt` UI fonts | bounded header/tables, embedded texture, glyph rectangles and ASCII width; full styled text partial — [contract](formats/ui-fonts.md) | `tools/ref_ui_layout.py` |

Original interface resource rectangles, tiled border assembly and base player HUD
coordinates are documented in [hud-layout.md](hud-layout.md). This identifies
separate frame textures; it does not invent a shared original atlas.

## GOB

A table of 40-byte records, ended by a record whose name is empty:
`char name[32]; u32 offset; u32 size`. Each entry is usually an LMP.

## LMP

`u32 count`, then `count` records of `u32 nameOffset; u32 dataOffset; u32 dataSize`.
Offsets are from the start of the lump.

## script.scr

The header starts at file offset 0x60 and its offsets are relative to 0x60:
`+0x0c` code, `+0x10` strings, `+0x14` end, `+0x20` number of internal entry points,
`+0x24` their table, `+0x28` number of imported built-ins, `+0x2c` their table. Table
records are 24 bytes: `u32 value; char name[20]`. Strings are stored as big-endian 32-bit
words, so every 4-byte group must be reversed.

The code is for an accumulator machine with registers A and X and numbered variables.
`python3 tools/scr.py dis script.scr` prints every entry point as readable pseudo-code with
the original source line numbers the compiler left in.

## .cut

Header: `u32 flags; u32 keyOffset; u32 keyCount; u32 actorOffset; u32 actorCount`. Actor
records are 0x2c bytes. Key records are 20 bytes:
`float time; s16 actor; s16 type; s32 a; s32 b; s32 c`, sorted by time (seconds).

Actor -100 is the camera, -99 is dialog, 0 and up index the actor table (level objects).
For object actors, type 0 = walk to (a, b), 2 = play animation, 8 = show, 10 = teleport to
(a, b), 11 = face angle a. A dialog key of type 3 holds the cutscene until the voice line
has finished; in a net game, until it has finished on every machine.

## objects.ob

A header followed by object records whose properties are plain `key=value` strings
(`name=`, `deathscript=`, `lumpname=`, trigger `w=`/`h=`/`t=` and so on). The class name of
each object (for example `UndeadKnight1`, `Trigger`, `PushTrigger`) selects the C++ class
through the factory around 0x15b804.

Record layout, as used for the disc scans of `docs/issues/sync-breakers.md` (not checked
against the loader here): `u32 count; u32 stringTable;` then per object `u32 className;
u16 size; u16 angle; float x, y, z;` followed by `(size − 20) / 4` property-string
offsets, a zero word ending the list. All string offsets are relative to the string
table.

## Texture names used by the Mac build's dump and replacement

Not a format of the disc: the names the playable Mac build (`tools/play-net`) gives to
textures when it writes them out and when it looks for a replacement. They are listed
here because they are how a texture of this game is told apart outside the game.

`<texels>-<palette>-p<format>-<width>x<height>.png`

- `<texels>` is a figure of the bytes the game sent for the texture, `<palette>` a figure
  of the palette it is drawn with. The same texels with another palette are another
  picture.
- `<format>` is the console's pixel-format number: 19 is 8-bit, 20 is 4-bit, 0 is 32-bit
  (the pixel-format field of the `TEX0` bits a `.tex` header keeps at +0x0c,
  [formats/model-texture.md](formats/model-texture.md)).
- `<width>x<height>` is the size sent, which can be smaller than the size the texture
  register names.

The name does not change from run to run or with where the game puts the texture in video
memory. Beside each dumped picture a `.json` file of the same name records how the game
draws with it (primitive, blending, alpha test, wrap modes, the rectangles used). A PNG
file of the same name and of any whole multiple of the size is drawn in its place.

`tools/play-net/disctex.py` works out the same names from the disc for the textures kept
in lumps (model, monster and item textures, interface art) without playing. It cannot do
that for level textures: `<LEVEL>.TEX` holds them in a packed form that the game unpacks
(now documented in [formats/level-texture.md](formats/level-texture.md); `tools/ref_leveltex.py` unpacks it, but the dump names above depend on what the game sent)
before sending, and that unpacker has not been rewritten.

The rules a replacement has to follow (alpha 128 is opaque, interface art stored as two
fields, texels that were never sent) and the whole pipeline are in
[tools/play-net/README.md](../tools/play-net/README.md), "Texture dump and replacement"
and "Upscaled art". Dumps and packs are the game's art and stay out of the repository.
