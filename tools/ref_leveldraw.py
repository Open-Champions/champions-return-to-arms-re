#!/usr/bin/env python3
"""How a drawn WORLD chunk and an automap cell choose blend, depth order and UVs.

Pure functions. tools/test_ref_leveldraw.py checks them on authored numbers.
tools/difftest_leveldraw.py runs the same inputs through world_drawChunk (0x1887b8),
gfx_addSortedPacket (0x16b7f0) and the automap drawer (0x168cac, then its own VU1
microcode). Nothing here reads a disc file.

The functions describe a geometry chunk: flags 0x80, 0x800, 0x4000 and 0x8000 are
other drawers and are refused.
"""

# GS ALPHA register values written by world_drawChunk. The equations are the ones in
# docs/spec/render-pipeline.md section 6 (As is source alpha, 0x80 = 1).
ALPHA_DARKEN = 0x02          # src * (1 - As); destination is not added
ALPHA_CUTOUT = 0x01          # src * (1 - As) + dst * As; alpha 0 is opaque
ALPHA_ENV_SECOND = 0x09      # src + dst * As
ALPHA_ENV_FIRST = 0x2A       # src
ALPHA_ADD = 0x48             # dst + src * As
ALPHA_USUAL = 0x44           # src * As + dst * (1 - As); the automap tiles

TEST_DEPTH = 0x587F4         # no alpha test, depth >=
TEST_CUTOUT = 0x582F5        # pass alpha < 0x2f, depth >=
TEST_AUTOMAP = 0x3001C       # alpha test off, depth always

LIGHT_FLASH = -230           # flag 0x100, once
LIGHT_FULL = 230             # flag 0x2000
LIGHT_FLAT = 0               # flag 0x200

ENV_SCALE = 6.0
ENV_BIAS = 192.0
ENV_SCROLL_BIT = 0x4         # level option word 0x44fe08
ENV_SCREEN = 0.07            # texels per pixel of screen offset; render-pipeline 4.6

# Automap atlas step. UV is texels * 16. The far edge stops 2/16 of a texel early.
AUTOMAP_TILE = 10
AUTOMAP_UV_STEP = AUTOMAP_TILE * 16          # 160
AUTOMAP_UV_SPAN = AUTOMAP_UV_STEP - 2        # 158

# Four corners in the order the microcode emits them, as (u_edge, v_edge):
# 0 = origin (col * 160 or row * 160), 1 = origin + 158.
# Orientations 0..7. Measured from program entries 0x79a/0x79c.
AUTOMAP_ORIENT = (
    ((0, 0), (0, 1), (1, 0), (1, 1)),
    ((1, 0), (1, 1), (0, 0), (0, 1)),
    ((0, 1), (0, 0), (1, 1), (1, 0)),
    ((1, 1), (1, 0), (0, 1), (0, 0)),
    ((0, 0), (1, 0), (0, 1), (1, 1)),
    ((0, 1), (1, 1), (0, 0), (1, 0)),
    ((1, 0), (0, 0), (1, 1), (0, 1)),
    ((1, 1), (0, 1), (1, 0), (0, 0)),
)

_KIND = 0x80 | 0x800 | 0x4000 | 0x8000


def _geometry(flags):
    if flags & _KIND:
        raise ValueError('flags 0x%x select water, a model, an emitter or a light' % flags)


def chunk_gs(flags):
    """GS state a geometry chunk's header writes, and the sort layer.

    Returns dict alpha1, alpha2 (None when the chunk is not environment-mapped),
    test, layer (0 or 4), env (bool). alpha2 is context 2, written only for flag 0x10.
    """
    _geometry(flags)
    env = bool(flags & 0x10)
    if env:
        alpha1, alpha2 = ALPHA_ENV_SECOND, ALPHA_ENV_FIRST
    elif flags & 0x10000:
        alpha1, alpha2 = ALPHA_ADD, None
    elif flags & 0x600:
        alpha1, alpha2 = ALPHA_CUTOUT, None
    else:
        alpha1, alpha2 = ALPHA_DARKEN, None
    test = TEST_CUTOUT if flags & 0x400 else TEST_DEPTH
    layer = 4 if flags & 0x200 else 0
    return {'alpha1': alpha1, 'alpha2': alpha2, 'test': test, 'layer': layer, 'env': env}


def chunk_light(flags):
    """The light path world_drawChunk takes before it emits the packet.

    ('flash', -230) and the chunk then stores flags with bit 0x100 cleared;
    ('full', 230); ('flat', 0); or ('dynamic', None). 0x100 wins over 0x2000,
    and 0x2000 wins over 0x200. Other bits are kept.
    """
    _geometry(flags)
    if flags & 0x100:
        return ('flash', LIGHT_FLASH, flags & ~0x100)
    if flags & 0x2000:
        return ('full', LIGHT_FULL, flags)
    if flags & 0x200:
        return ('flat', LIGHT_FLAT, flags)
    return ('dynamic', None, flags)


def axis_xy(camera):
    """The six camera-axis components env rows are built from.

    camera is the float list at 0x44f110. Each axis is three floats (x, y, z);
    z is not used. Returns (m00, m01, m10, m11, m20, m21).
    """
    c = list(camera)
    if len(c) < 9:
        raise ValueError('need 9 camera floats')
    return (c[0], c[1], c[3], c[4], c[6], c[7])


def quarter_turn(axis, code):
    """Permute the X and Y axis pairs by a chunk quarter-turn code (flag 0x1).

    Bit 0 negates the first pair, bit 1 the second, bit 2 swaps the two pairs.
    The Z pair is not turned. code is the low 3 bits of chunk +0x36.
    """
    x0, x1, y0, y1, z0, z1 = axis
    bit0, bit1, bit2 = code & 1, (code >> 1) & 1, (code >> 2) & 1
    a = (y0, y1) if bit2 else (x0, x1)
    b = (x0, x1) if bit2 else (y0, y1)
    if bit0:
        a = (-a[0], -a[1])
    if bit1:
        b = (-b[0], -b[1])
    return (a[0], a[1], b[0], b[1], z0, z1)


def env_rows(axis, frame, level_options, quarter=None):
    """The two extra matrix rows uploaded for an environment-mapped chunk.

    axis is the six components from axis_xy. quarter is None when chunk flag 0x1
    is clear (a free rotation does not change these rows) and 0..7 when it is set.
    Returns (row4, row5), each four floats:
    row4 = 6 * (m00, m01, m10, m11), row5 = (6*m20, 6*m21, 192 + scroll, 192).
    scroll is (frame & 0x3ff) * 0.25 when level option bit 2 (value 4) is set.
    """
    x0, x1, y0, y1, z0, z1 = axis if quarter is None else quarter_turn(axis, quarter)
    scroll = ((frame & 0x3FF) / 4.0) if (level_options & ENV_SCROLL_BIT) else 0.0
    return ((ENV_SCALE * x0, ENV_SCALE * x1, ENV_SCALE * y0, ENV_SCALE * y1),
            (ENV_SCALE * z0, ENV_SCALE * z1, ENV_BIAS + scroll, ENV_BIAS))


def env_uv(normal, rows, sx, sy):
    """Second texture coordinate in texels, from the uploaded rows.

    normal is the stored vertex normal (127 = 1 for lighting; this divides by 16).
    rows is (row4, row5) from env_rows. (sx, sy) is the projected pixel offset from
    the buffer centre. This is the formula in render-pipeline section 4.6; the row
    values it consumes are what env_rows matches against the CPU.
    """
    nx, ny, nz = (c / 16.0 for c in normal)
    r4, r5 = rows
    u = r5[2] + nx * r4[0] + ny * r4[2] + nz * r5[0] + ENV_SCREEN * sx
    v = r5[3] + nx * r4[1] + ny * r4[3] + nz * r5[1] + ENV_SCREEN * sy
    return (u, v)


def automap_fields(cell):
    """Split one automap grid cell (a u16).

    Bits 0-4 column, 5-7 orientation, 8-11 row, 12-15 explored level.
    alpha is the whole high byte: (explored << 4) | row. That is what the
    microcode writes to the vertex, so a cell's own row tints its corner.
    """
    cell &= 0xFFFF
    return {
        'col': cell & 0x1F,
        'orient': (cell >> 5) & 7,
        'row': (cell >> 8) & 0xF,
        'explored': (cell >> 12) & 0xF,
        'alpha': (cell >> 8) & 0xFF,
    }


def automap_uv_rect(col, row):
    """GS UV rectangle of one atlas tile: origin and origin+158 on each axis."""
    u0 = col * AUTOMAP_UV_STEP
    v0 = row * AUTOMAP_UV_STEP
    return u0, v0, u0 + AUTOMAP_UV_SPAN, v0 + AUTOMAP_UV_SPAN


def automap_quad(cell_c_r, cell_c_r1, cell_c1_r, cell_c1_r1):
    """One automap quad, corners in the order the microcode emits.

    The four arguments are the cells at (c, r), (c, r+1), (c+1, r), (c+1, r+1).
    The tile and the orientation come from the bottom-right cell (c+1, r+1).
    Each vertex's alpha is the high byte of its own corner. Returns four
    (u, v, alpha) tuples.
    """
    corners = (cell_c_r, cell_c_r1, cell_c1_r, cell_c1_r1)
    src = automap_fields(cell_c1_r1)
    u0, v0, u1, v1 = automap_uv_rect(src['col'], src['row'])
    edges = ((u0, v0), (u1, v1))
    out = []
    for i, (ue, ve) in enumerate(AUTOMAP_ORIENT[src['orient']]):
        u, v = edges[ue][0], edges[ve][1]
        out.append((u, v, automap_fields(corners[i])['alpha']))
    return tuple(out)


def sorted_draw_order(items):
    """Draw order of gfx_addSortedPacket for packets with no parent.

    items is a sequence of (layer, texture, flags, payload). texture None, or
    flags bit 0 set, inserts at the front of that layer. Otherwise the packet
    is inserted immediately after the previous packet of the same texture in
    that layer, so one texture stays together in submission order and texture
    groups run in reverse order of first use. Returns a dict layer -> payloads
    in the order the list is walked (the order they are sent).
    """
    layers = {n: [] for n in range(8)}
    latest = {}
    for layer, texture, flags, payload in items:
        if layer not in layers:
            raise ValueError('layer %r' % (layer,))
        row = layers[layer]
        if texture is None or (flags & 1):
            row.insert(0, payload)
        else:
            prev = latest.get((layer, texture))
            if prev is None:
                row.insert(0, payload)
            else:
                row.insert(row.index(prev) + 1, payload)
        if texture is not None:
            latest[(layer, texture)] = payload
    return layers
