#!/usr/bin/env python3
"""ref_model_rows.py - the VIF row-register contract of vertex program 0x46 when it occurs
in a model file (.vif), Champions: Return to Arms (SLUS_209.73).

A packet for program 0x46 unpacks its positions with STMOD 1 (docs/formats/world.md,
docs/formats/model-texture.md): the VIF1 adds its four ROW registers to every unpacked
vector.  The ROW registers are VIF1 state, set only by a STROW code earlier in the same
DMA stream, and they stay until the next STROW.  This module states, from the executable,
who writes them and what a standalone reader can therefore do.  docs/formats/model-row-
registers.md is the prose version with the evidence.  Standard library only; no game data.

Observed (O):
  * Exactly two STROW codes are emitted by the rendering code (every other 0x30000000 in
    0x160000-0x1a0000 is a DMA "ref" tag): world_drawChunk 0x1890b4-0x1890c0 writes
    (tx, ty, tz, 0), the geometry chunk's translation, before each level packet; and
    0x175a6c-0x175ae4, inside 0x175950, writes (0, 0, 0, 0).
  * 0x175950 builds the level-program set-up for a model (DIRECT: TEXFLUSH, TEX0_1 = 0,
    ALPHA_1 = model +0x18, TEST_1 = 0x507f5; ITOP 1; UNPACK 4 rows at VU address 0;
    MSCAL 0x16; ITOP 1; MSCAL 0x34; STROW 0, 0, 0, 0) and has no caller
    (tools/dis.py: callers=0; the decompiled body is the only one in the texture area).
  * model_draw 0x1779b0, model_drawPart 0x178c28, model_emitDrawSetup 0x175670,
    world_drawModelChunk 0x187eac and game_drawBackdrop 0x1e78d0 write no STROW.
  * The one model with program 0x46 on the disc is dome.vif of the top-level D_SWAMP.LMP.
    The executable contains no string naming that lump (byte search for "d_swamp" in any
    case: none), the swamp level archives hold no dome.lmp and name no "d_swamp", and
    game_drawBackdrop draws only the lump found as "dome.lmp" (lump_findLoaded, 0x1e5d48).
Inferred (I):
  * A model packet with STMOD 1 drawn through model_draw adds whatever the last
    world_drawChunk before it in the frame's VIF1 stream left in the rows - a translation
    in 1/16 world units - or (0, 0, 0, 0) at power-on.  There is no model-side source.
Unknown (U):
  * Whether anything loads D_SWAMP.LMP.  No loader was found; if none exists the model is
    unreferenced content and the question of its rows never arises on the retail disc.
"""

ENTRY_LEVEL_SETUP = 0x16          # entries called by 0x175950 before the packets
ENTRY_LEVEL_NOP = 0x34
PROGRAM_LEVEL_ONE_PASS = 0x46
PROGRAM_LEVEL_TWO_PASS = 0x48
STROW_CODE = 0x30000000           # VIF code: the next four words load ROW0..ROW3
POSITION_SCALE = 16               # positions are 1/16 world units after the add

# Provenance of the rows a 0x46 packet sees, from the executable.
ROWS_LEVEL_CHUNK = 'level-chunk'          # world_drawChunk: (tx, ty, tz, 0) of the chunk, O 0x1890b4
ROWS_MODEL_SETUP_0x175950 = 'uncalled-0x175950'   # (0, 0, 0, 0), O 0x175a6c; no caller
ROWS_INHERITED = 'inherited'              # model_draw path: whatever the stream last set, I

# The DIRECT block 0x175950 writes (register address, value) - O from the decompiled body.
SETUP_0x175950_GS = ((0x3f, 0), (0x06, 0), (0x42, 'model+0x18'), (0x47, 0x507f5))
SETUP_0x175950_ROWS = (0, 0, 0, 0)


def stmod_add(position, rows):
    """VIF STMOD 1 ("offset mode") on a V3-16 signed unpack: each component is sign-extended
    to 32 bits and the matching ROW register is added as a 32-bit integer; the result wraps
    like the hardware register.  rows is (r0, r1, r2, r3); only r0..r2 meet a V3 unpack."""
    out = []
    for i, p in enumerate(position):
        v = (p + rows[i]) & 0xffffffff
        out.append(v - (1 << 32) if v & 0x80000000 else v)
    return tuple(out)


def world_units(position, rows):
    """Position in world units as the level program sees it: (stored + row) / 16
    (docs/spec/render-pipeline.md 4.6, "p = (stored position + (tx, ty, tz)) / 16")."""
    x, y, z = stmod_add(position, rows)
    return (x / POSITION_SCALE, y / POSITION_SCALE, z / POSITION_SCALE)


def rows_for_level_chunk(tx, ty, tz):
    """What world_drawChunk puts in the rows for a geometry chunk: its translation already in
    1/16 units as the file stores it, fourth word 0 (O 0x1890b4-0x1890c0)."""
    return (int(tx), int(ty), int(tz), 0)


def rows_for_model(provenance, preceding_chunk_rows=None):
    """The rows a model packet with program 0x46 is unpacked with, by provenance:
    ROWS_MODEL_SETUP_0x175950 -> (0, 0, 0, 0) (the code exists but is never called);
    ROWS_INHERITED -> the rows of the last world chunk sent before it, which the caller must
    supply - this module refuses to invent them."""
    if provenance == ROWS_MODEL_SETUP_0x175950:
        return SETUP_0x175950_ROWS
    if provenance == ROWS_INHERITED:
        if preceding_chunk_rows is None:
            raise ValueError('inherited rows: the preceding level chunk is not known; nothing in the executable sets rows for a model')
        return tuple(preceding_chunk_rows)
    if provenance == ROWS_LEVEL_CHUNK:
        raise ValueError('a model is not a level chunk; use rows_for_level_chunk for chunks')
    raise ValueError('unknown provenance %r' % (provenance,))


def packet_positions(stored, rows):
    """All positions of one 0x46 packet after the VIF add, in world units."""
    return [world_units(p, rows) for p in stored]
