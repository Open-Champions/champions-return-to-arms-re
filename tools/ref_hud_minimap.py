#!/usr/bin/env python3
"""ref_hud_minimap.py - reference model of the automap drawer 0x168cac (SLUS-20973 v2.00).

Called once per drawn frame by minimap_draw 0x1e42e0 (docs/hud-dynamic.md section 9).
It writes three kinds of display-list packet at g_dlCursor 0x44fe10 and hands each to
gfx_addSortedPacket 0x16b7f0 on layer 5:

  A. blips: per object the callback accepts, a shadow triangle and a coloured triangle
     (GIF A+D, built on the EE);
  B. map icons: one textured 4-vertex strip per entry of the icon table 0x6e0f90;
  C. the map itself: per strip of up to 30 automap columns, a VIF packet that loads the
     VU1 program at 0x403e20 (micro address 0x79a), uploads a 15-qword constant block and
     the raw automap cells row by row, and calls the program. The tiles are drawn by
     that VU1 program, which tools/ee_emu.py cannot run.

Everything here is executed against the original by tools/difftest_hud_minimap.py.
Floats are raw 32-bit patterns (ref_core). docs/spec/hud-minimap.md is the prose version.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ref_core as F

M32 = 0xFFFFFFFF
M64 = 0xFFFFFFFFFFFFFFFF

# ---- constants (address where the code loads or builds them) --------------------------
K_ASPECT = 0x3FAA9FBE        # 1.333, 0x168e88: half-width * this / zoom
K_QUARTER = 0x3E800000       # 0.25, 0x168eb0 and 0x16a7e4 (world -> cell, first factor)
K_CELL = 0x3D088888          # 1/30, 0x168ebc and 0x16a7f0 (second factor; together 1/120)
K_STEP = 0x40F00000          # 7.5, 0x168ed4: pixels per cell at zoom 1
K_RADIUS = 0x3E088888        # 0.1333 = 1/7.5, 0x168f00: pixels -> cells
K_BLIP_MIN_ZOOM = 0x3E000000  # 0.125, 0x16904c: blips only when zoom > this
K_ICON_SCALE = 0x3F400000    # 0.75, 0x1698c4: icon half-size = size * 0.75
K_TWO = 0x40000000           # 2.0, 0x169308: blip shadow offset in pixels
K_FIX_Y = 0x41800000         # 16, 0x169314: GS 12.4 fixed point, y
K_FIX_X = 0x42000000         # 32, 0x16931c: x is doubled (1280-wide buffer) then 12.4
K_GS_ORIGIN_FIX = 0x47000000  # 32768 = 2048 * 16, 0x16932c
K_GS_ORIGIN = 0x45000000     # 2048, 0x169eec (VU constant block)
K_TILE_UV = 0x411E6666       # 9.9, 0x169f18: texel extent of one 10-texel atlas tile
CENTRE_X, CENTRE_Y = 0x140, 0xDC   # 320, 220: scissor centre, 0x168dec / 0x168da0
SCREEN_MAX_X, SCREEN_MAX_Y = 0x27F, 0x1BF   # 639, 447, 0x168d80 / 0x168dbc
DL_MIN_FREE = 0x2EE0         # 12000 display-list units, 0x16a868
GRID_DIM = 216               # 0x169870 (clamp 0xd7), row stride 0x1b0 bytes
STRIP_COLS = 0x1E            # 30 columns uploaded per strip, 0x169ca4
STRIP_STEP = 0x1D            # 29: next strip start, 0x16a404 (one column overlap)
LAYER = 5                    # gfx_addSortedPacket a1, 0x169640 / 0x169c10 / 0x16a3f4

# Tables in .data read by 0x168cac (values Observed in the ELF).
BLIP_SHAPE = ((0, 0xBF800000), (0xBF400000, 0x3F800000), (0x3F400000, 0x3F800000))  # 0x404470
ICON_CORNERS = ((0xBF800000, 0xBF800000), (0xBF800000, 0x3F800000),
                (0x3F800000, 0xBF800000), (0x3F800000, 0x3F800000))            # 0x404488
ICON_UV = ((0, 0), (0, 1), (1, 0), (1, 1))                                      # 0x4044b0

# GS / VIF words built from immediates.
GIFTAG_AD = 0x1000000000008000   # NREG 1, EOP, NLOOP patched; register list 0xe (A+D)
VIF_FLUSH = 0x11000000
VIF_DIRECT = 0x50000000
VIF_MSCAL = 0x14000000
VIF_MPG = 0x4A000000
VIF_UNPACK_V4_32 = 0x6C0F0000    # 15 qwords to VU address 0
VIF_UNPACK_V2_8 = 0x66004000     # unsigned, NUM and the 0x200 buffer or-ed in
DMA_CNT, DMA_REF, DMA_RET = 0x10000000, 0x30000000, 0x60000000
VU_PROG_ADDR, VU_PROG_END = 0x403E20, 0x404150   # 102 instructions
VU_LOAD = (0x4000 - ((VU_PROG_END - VU_PROG_ADDR + 15) >> 4 << 4)) >> 3   # 0x79a
TILE_GIFTAG = (0xC0AE4000, 0x31531531, 0x5315)   # upper words: PRE, PRIM 0x15c, 12 regs
DIMX_MAP = 0x1212303012123030    # 0x169d78
DIMX_RESTORE = 0x3131757531317575  # 0x16a2c4
PRIM_BLIP_SHADOW = 0x43          # triangle, alpha blend
PRIM_BLIP = 0x03                 # triangle
PRIM_ICON = 0x154                # strip, textured, alpha, UV
SHADOW_RGBA = 0x60000000
ICON_RGB = 0x808080
TILE_RGBA = 0x80808080
TEST_SPRITES, TEST_MAP = 0x3001D, 0x3001C
TEX1_SPRITES, TEX1_MAP = 0x61, 0x01
ALPHA_BLEND = 0x44


def sx32(v):
    v &= M32
    return (v - (1 << 32)) & M64 if v & 0x80000000 else v


def sll32(v, n):
    return sx32((v & M32) << n)


def r5900_floor(x):
    """libm 0x3a53c0 on the exact double of x, then 0x3afac0 (saturating) - Executed."""
    return _to_int(x, 'floor')


def r5900_ceil(x):
    """libm 0x3a51b0 on the exact double of x, then 0x3afac0 - Executed."""
    return _to_int(x, 'ceil')


def _to_int(x, mode):
    import math
    e = (x >> 23) & 0xFF
    if e == 0:
        return 0
    v = F.to_float(x) if e != 0xFF else (-1 if x & 0x80000000 else 1) * 2.0 ** 129
    n = math.floor(v) if mode == 'floor' else math.ceil(v)
    return max(-0x80000000, min(0x7FFFFFFF, n))


def gate(world_tex, dl_cursor, dl_base, dl_capacity, half_w):
    """0x16a838: 0 without the automap texture (world +0x6c) or with fewer than 12000
    free display-list units; otherwise trunc(half_w) >= 2."""
    if world_tex == 0:
        return 0
    used = F.s32(dl_cursor - dl_base) >> 3
    if F.s32(dl_capacity - used) < DL_MIN_FREE:
        return 0
    return 1 if F.to_int(half_w) >= 2 else 0


def world_to_cell(x, y, origin):
    """0x16a7dc: cell = origin + world * 0.25 * (1/30)."""
    return (F.add(origin[0], F.mul(F.mul(x, K_QUARTER), K_CELL)),
            F.add(origin[1], F.mul(F.mul(y, K_QUARTER), K_CELL)))


class _Buf:
    def __init__(self, fill):
        self.b = {}
        self.fill = fill

    def sb(self, a, v):
        self.b[a] = v & 0xFF

    def sw(self, a, v):
        for i in range(4):
            self.b[a + i] = (v >> (8 * i)) & 0xFF

    def sd(self, a, v):
        for i in range(8):
            self.b[a + i] = (v >> (8 * i)) & 0xFF

    def ld(self, a):
        return sum(self.b.get(a + i, self.fill) << (8 * i) for i in range(8))

    def lw(self, a):
        return sum(self.b.get(a + i, self.fill) << (8 * i) for i in range(4))

    def qw(self, a, data, reg):
        self.sd(a, data)
        self.sd(a + 8, reg)


def _xyz(x, y):
    """XYZ2 data: X, Y in 12.4 with the 2048 origin, Z = 0xa (0x169384..0x1693a4)."""
    gx = F.to_int(F.add(F.mul(x, K_FIX_X), K_GS_ORIGIN_FIX))
    gy = F.to_int(F.add(F.mul(y, K_FIX_Y), K_GS_ORIGIN_FIX))
    return (sx32(gx) | ((sx32(gy) << 16) & M64) | 0xA00000000) & M64


def _header(buf, p, scissor, texture_regs):
    """DMA tag slot, FLUSH, zero pad, DIRECT, GIF A+D tag and the register qwords."""
    buf.sw(p + 8, VIF_FLUSH)
    d = p + 0xC
    while (d & 0xF) != 0xC:
        buf.sb(d, 0)
        d += 1
    buf.sw(d, VIF_DIRECT)
    gif = d + 4
    buf.qw(gif, GIFTAG_AD, 0xE)
    cur = gif + 0x10
    for data, reg in texture_regs + [(scissor, 0x40)]:
        buf.qw(cur, data, reg)
        cur += 0x10
    return d, gif, cur


def _close(buf, p, gif, direct, cur, full_scissor):
    """Restore the full scissor, patch NLOOP, DIRECT qwc and the DMA tag (cnt -> ret)."""
    buf.qw(cur, full_scissor, 0x40)
    cur += 0x10
    _patch(buf, p, gif, direct, cur)
    return cur


def _patch(buf, p, gif, direct, cur):
    dma = ((((cur - p) >> 3) - 2) >> 1) | DMA_CNT
    buf.sd(gif, buf.ld(gif) | ((((cur - gif) >> 3) - 2) >> 1))
    buf.sw(direct, buf.lw(direct) | ((cur - direct - 4) >> 4))
    buf.sd(p, (dma & 0xFFFFFFFF8FFFFFFF) | DMA_RET if (dma >> 28) & 7 == 1 else dma)


def draw(s, fill=0xCD):
    """Run the model. s is a dict of inputs (see the difftest for the full list):

    world_tex, dl_cursor, dl_base, dl_capacity, yaw (s16), centre (x, y), offx, offy,
    zoom, half_w, half_h, blip_size, icon_size, origin (x, y), width, height, grid(bytes
    of the 216x216 s16 automap), blips (callback results: None = skip, else dict with
    x, y, angle, r, g, b, scale), icons (dicts: x, y, tex (0 or pointer), tex_w, tex_h,
    rotate, var, var_ok, script, script_ok), full_scissor (0x44fd74, 0x44fd78), zbuf
    (u64 at 0x44fd60), timer (before, after), counters (0x4044d4, 0x4044d8).

    Returns dict: drawn, bytes {addr: byte}, end, calls [(name, args...)], counters.
    """
    out = {'drawn': False, 'calls': [], 'bytes': {}, 'end': s['dl_cursor'],
           'counters': s['counters']}
    calls = out['calls']
    if not gate(s['world_tex'], s['dl_cursor'], s['dl_base'], s['dl_capacity'], s['half_w']):
        return out
    buf = _Buf(fill)
    zoom = s['zoom']
    hw_i = F.to_int(s['half_w'])
    hh_i = F.to_int(s['half_h'])
    oy_i = F.to_int(s['offy'])
    fhw = F.from_int(hw_i)
    y1 = F.s32(oy_i + hh_i + CENTRE_Y)
    y0 = F.s32(oy_i - hh_i + CENTRE_Y)
    x0 = F.s32(F.to_int(F.sub(s['offx'], fhw)) + CENTRE_X)
    x1 = F.s32(F.to_int(F.add(s['offx'], fhw)) + CENTRE_X)
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, SCREEN_MAX_X), min(y1, SCREEN_MAX_Y)
    scissor = (sll32(x0, 1) | ((sll32(x1, 1) << 16) & M64) | ((y0 & M32) << 32)
               | ((y1 << 48) & M64)) & M64
    v74, v78 = s['full_scissor']
    full = (((v74 & M32) << 32) | 0x04FF0000 | ((v78 << 48) & M64)) & M64

    # rotation by minus the camera yaw (0x168e58..0x168f38)
    a = -s['yaw']
    cos_, sin_ = F.cos16(a), F.sin16(a)
    r = F.mul(fhw, K_ASPECT)
    r = F.div(r, zoom)
    p30 = F.mul(F.mul(cos_, K_STEP), zoom)       # x per cell column
    p31 = F.mul(F.mul(sin_, K_STEP), zoom)       # y per cell column
    p29 = F.mul(F.mul(sin_, K_STEP), zoom)       # x per cell row
    p8 = F.mul(F.mul(F.neg(cos_), K_STEP), zoom)  # y per cell row (0x110 on the stack)
    cx, cy = world_to_cell(s['centre'][0], s['centre'][1], s['origin'])
    r = F.mul(r, K_RADIUS)
    t1 = F.add(F.mul(cx, p30), F.mul(cy, p29))
    t0 = F.add(F.mul(cx, p31), F.mul(cy, p8))
    lo = F.fmax(F.sub(F.sub(cx, r), F.ONE), 0)
    bx = F.sub(s['offx'], t1)                    # screen x of cell (0, 0), minus 320
    by = F.sub(s['offy'], t0)
    c_min = r5900_floor(lo)
    r_min = r5900_floor(F.fmax(F.sub(F.sub(cy, r), F.ONE), 0))
    c_end = r5900_ceil(F.fmin(F.add(cx, r), F.from_int(s['width'])))
    r_end = r5900_ceil(F.fmin(F.add(cy, r), F.from_int(s['height'])))
    calls.append(('ranges', c_min, r_min, c_end, r_end))
    if not (c_min < c_end and r_min < r_end):
        return out
    out['drawn'] = True
    cursor = s['dl_cursor']

    def add_packet(p, end, tex):
        calls.append(('gfx_addSortedPacket', p, LAYER, tex, 0, 0))

    sprite_regs = [(0, 0x3F), (0, 6), (TEX1_SPRITES, 0x14), (ALPHA_BLEND, 0x42),
                   (TEST_SPRITES, 0x47)]
    # ---- A. blips -----------------------------------------------------------------
    if F.lt(K_BLIP_MIN_ZOOM, zoom):
        p = cursor
        direct, gif, cur = _header(buf, p, scissor, sprite_regs)
        stale = dict(s.get('stale', {}))
        for index, blip in enumerate(s['blips']):
            calls.append(('callback', index))
            if blip is None:
                continue
            stale.update(blip)
            b = stale
            u, v = world_to_cell(b['x'], b['y'], s['origin'])
            sy = F.add(F.add(by, F.mul(u, p31)), F.mul(v, p8))
            sx = F.add(F.add(bx, F.mul(u, p30)), F.mul(v, p29))
            ang = (F.s32(s['yaw']) + (b['angle'] & 0xFFFF) - 0x3FFF) & 0xFFFF
            c, sn = F.cos16(ang), F.sin16(ang)
            buf.qw(cur, PRIM_BLIP_SHADOW, 0)
            buf.qw(cur + 0x10, SHADOW_RGBA, 1)
            cur += 0x20
            for shadow in (True, False):
                if not shadow:
                    colour = ((b['r'] | 0x80000000 | (b['b'] << 16) | (b['g'] << 8)) & M32)
                    buf.qw(cur, PRIM_BLIP, 0)
                    buf.qw(cur + 0x10, colour, 1)
                    cur += 0x20
                for tx, ty in BLIP_SHAPE:
                    fx = F.mul(F.mul(tx, s['blip_size']), b['scale']) if not F.eq(zoom, 0) else 0
                    fy = F.mul(F.mul(ty, s['blip_size']), b['scale']) if not F.eq(zoom, 0) else 0
                    yy = F.add(sy, F.add(F.mul(fx, F.neg(sn)), F.mul(fy, c)))
                    xx = F.add(sx, F.add(F.mul(fx, c), F.mul(fy, sn)))
                    if shadow:
                        yy, xx = F.add(yy, K_TWO), F.add(xx, K_TWO)
                    buf.qw(cur, _xyz(xx, yy), 5)
                    cur += 0x10
        calls.append(('callback', len(s['blips'])))
        cur = _close(buf, p, gif, direct, cur, full)
        add_packet(p, cur, 0)
        cursor = cur
    # ---- B. map icons ---------------------------------------------------------------
    for icon in s['icons']:
        if icon['var']:
            calls.append(('vars_get', icon['var']))
            if not icon['var_ok']:
                continue
        if icon['script']:
            calls.append(('script_runByName', icon['script']))
            if not icon['script_ok']:
                continue
        p = cursor
        direct, gif, cur = _header(buf, p, scissor, sprite_regs)
        buf.qw(cur, PRIM_ICON, 0)
        cur += 0x10
        u, v = world_to_cell(icon['x'], icon['y'], s['origin'])
        row = max(0, min(F.to_int(v), GRID_DIM - 1)) if F.to_int(v) < GRID_DIM else GRID_DIM - 1
        col = max(0, min(F.to_int(u), GRID_DIM - 1)) if F.to_int(u) < GRID_DIM else GRID_DIM - 1
        explored = s['grid'][(row * GRID_DIM + col) * 2 + 1] & 0xF0
        alpha = 0x80 if 0x80 < explored else explored
        sx = F.add(F.add(bx, F.mul(u, p30)), F.mul(v, p29))
        sy = F.add(F.add(by, F.mul(u, p31)), F.mul(v, p8))
        half = F.mul(s['icon_size'], K_ICON_SCALE)
        buf.qw(cur, sx32((alpha << 24) | ICON_RGB) & M32, 1)
        cur += 0x10
        for (kx, ky), (tu, tv) in zip(ICON_CORNERS, ICON_UV):
            fx, fy = F.mul(kx, half), F.mul(ky, half)
            if icon['tex']:
                uv = (sll32(tu * icon['tex_w'], 4) | sll32(tv * icon['tex_h'], 20)) & M64
            else:
                uv = 0
            buf.qw(cur, uv, 3)
            cur += 0x10
            if icon['rotate']:
                yy = F.sub(sy, F.add(F.mul(fx, F.neg(sin_)), F.mul(fy, cos_)))
                xx = F.add(sx, F.add(F.mul(fx, cos_), F.mul(fy, sin_)))
            else:
                yy, xx = F.add(sy, fy), F.add(sx, fx)
            buf.qw(cur, _xyz(xx, yy), 5)
            cur += 0x10
        cur = _close(buf, p, gif, direct, cur, full)
        add_packet(p, cur, icon['tex'])
        cursor = cur
    # ---- C. map strips (VU1 program) --------------------------------------------------
    map_regs = [(0, 0x3F), (0, 6), (TEX1_MAP, 0x14), (s['zbuf'], 0x4E), (TEST_MAP, 0x47),
                (ALPHA_BLEND, 0x42), (TILE_RGBA, 1), (DIMX_MAP, 0x44)]
    c = c_min
    while c < c_end:
        n = min(c + STRIP_COLS, c_end) - c
        p = cursor
        direct, gif, cur = _header(buf, p, scissor, map_regs)
        buf.sd(gif, buf.ld(gif) | ((((cur - gif) >> 3) - 2) >> 1))
        buf.sw(direct, buf.lw(direct) | ((cur - direct - 4) >> 4))
        while cur & 0xF:
            buf.sb(cur, 0)
            cur += 1
        prog_qw = (VU_PROG_END - VU_PROG_ADDR + 15) >> 4
        buf.sd(p, ((((cur - p) >> 3) - 2) >> 1) | DMA_CNT)
        buf.sd(cur, (VU_PROG_ADDR << 32) | prog_qw | DMA_REF)
        buf.sw(cur + 8, 0)
        buf.sw(cur + 0xC, VU_LOAD | ((prog_qw << 4) << 13) | VIF_MPG)
        tag2 = cur + 0x10
        d = cur + 0x18
        fc, fr = F.from_int(c), F.from_int(r_min)
        ox = F.add(F.add(bx, F.mul(fc, p30)), F.mul(fr, p29))
        oy = F.add(F.add(by, F.mul(fc, p31)), F.mul(fr, p8))
        ox = F.add(F.add(ox, ox), K_GS_ORIGIN)
        oy = F.add(oy, K_GS_ORIGIN)
        words = [VIF_UNPACK_V4_32,
                 ox, oy, 0, 0,
                 F.add(p30, p30), p31, 0, 0,
                 F.add(p29, p29), p8, 0, 0,
                 K_TILE_UV, 0, 0, 0,
                 0, K_TILE_UV, 0, 0,
                 ((n - 1) | 0x8000) & M32, TILE_GIFTAG[0], TILE_GIFTAG[1], TILE_GIFTAG[2],
                 n & M32, 0, 0, 0]
        for k in range(8):
            o = [0, 3, 6, 9]
            if k & 1:
                o = [6, o[3], 0, o[1]]
            if k & 2:
                o = [o[1], o[0], o[3], o[2]]
            if k & 4:
                o = [o[0], o[2], o[1], o[3]]
            words += o
        words.append(VU_LOAD | VIF_MSCAL)
        for i, w in enumerate(words):
            buf.sw(d + 4 * i, w)
        cur = d + 4 * len(words)
        bufaddr = 0x200
        for row in range(r_min, r_end):
            buf.sw(cur, VIF_UNPACK_V2_8 | bufaddr | (n << 16))
            cur += 4
            src = row * 0x1B0 + c * 2
            calls.append(('memcpy', cur, 0x4044F0 + src, n * 2))
            for i in range(n * 2):
                buf.sb(cur + i, s['grid'][src + i])
            cur += n * 2
            while cur & 0xF:
                buf.sb(cur, 0)
                cur += 1
            buf.sw(cur, (VU_LOAD + 2) | VIF_MSCAL)
            cur += 4
            bufaddr ^= 0x200
        while cur & 0xF:
            buf.sb(cur, 0)
            cur += 1
        buf.sw(cur, VIF_FLUSH)
        d2 = cur + 4
        while (d2 & 0xF) != 0xC:
            buf.sb(d2, 0)
            d2 += 1
        buf.sw(d2, VIF_DIRECT)
        g2 = d2 + 4
        buf.qw(g2, GIFTAG_AD, 0xE)
        buf.qw(g2 + 0x10, DIMX_RESTORE, 0x44)
        buf.qw(g2 + 0x20, full, 0x40)
        cur = g2 + 0x30
        _patch(buf, tag2, g2, d2, cur)
        add_packet(p, cur, s['world_tex'])
        cursor = cur
        c += STRIP_STEP
    out['bytes'] = buf.b
    out['end'] = cursor
    t_before, t_after = s['timer']
    out['counters'] = ((s['counters'][0] + t_after - t_before) & M32,
                       (s['counters'][1] + 1) & M32)
    return out
