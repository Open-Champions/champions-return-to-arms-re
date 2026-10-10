# File formats

What has been worked out so far, and the tool that reads each format. All integers are
little endian unless noted. "Unknown" means nobody has looked yet.

| Format | Status | Tool |
|---|---|---|
| `.GOB` archive | understood | `tools/gob.py` |
| `.LMP` lump | understood | `tools/gob.py` |
| `script.scr` level script | understood, all 51 opcodes in use decoded | `tools/scr.py` |
| `.cut` cutscene | header and key records understood; most camera key types unnamed | none yet |
| `objects.ob` object placement | property strings readable; record layout not written down | none yet |
| `.dbin` dialog trees | understood: 0x448-byte nodes with condition script, text key, voice name, speaker and choices — see [formats/anim-audio.md](formats/anim-audio.md) | `tools/anim_audio_info.py` |
| `*_dialog.bin` voice-stream directory, `.VAT` streams, `.vag` samples | understood: PS2 ADPCM throughout; directory gives offset, rate, stereo flag and language | `tools/anim_audio_info.py` (can decode to WAV) |
| `.anm` animation | understood: bind offsets, joint hierarchy, velocity-coded key stream at 60 ticks per second; not yet compared against the game on screen | `tools/anim_audio_info.py` (can dump tracks to CSV) |
| `.world` level geometry | understood: header, chunk tree, render batches (ready-made VIF packets), terrain heights and flags, path grid; a few fields still open — see [formats/world.md](formats/world.md) | `tools/world_info.py` |
| models and textures (`.vif`, `.tex`) | in progress | none yet |

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
