#!/usr/bin/env python3
"""ref_fx_render.py - what the effect drawers of Champions: Return to Arms (SLUS_209.73, US
v2.00) send to the GS: particle sprites and lines (VU1 program entries 0x14 / 0x17 / 0x22 /
0x4a), particle groups, glow sprites, trails and beams.

A research tool, not game code.  It extends tools/ref_particles.py (the particle system's
state) with the geometry; docs/effects.md is the prose version.  Each function was written
from the code at the address in its docstring and is compared with that code, executed
under tools/ee_emu.py (EE side) and tools/vu1_emu.py (VU1 side), by
tools/difftest_fx_render.py.  Standard library only; no game data is embedded (no
microcode words, no particle definition values; the constants below are the immediates of
the drawing code and of the packet headers it builds).

Numbers
    Floats are raw 32-bit patterns, as in tools/ref_core.py.  The EE side (CPU code) uses
    ref_core's FPU (its 'ps2' model by default; C.set_fpu chooses another).  The VU side
    uses class Vu below: the same integer arithmetic in the vector unit's form - an operand
    with exponent 255 is read as the largest finite number, a result rounds toward zero
    ('chop' by default, as tools/vu1_emu.py and the C++ renderer compute).

Vertices
    A drawn vertex is a GsVertex tuple (x, y, z, f, adc, rgba, uv): x and y in GS fixed
    point (1/16 pixel, offset 0x8000 = 2048 pixels), z as the GS receives it (XYZF2: 24
    bits), f the fog byte, adc the "do not draw" bit, rgba a 4-tuple of bytes, uv the
    texel coordinates in 1/16 texel or None.  PRIM is given per packet (constants below).

What each part mirrors
    particle_projection, particle_matrix, group_matrix, particle_header
                        particle_draw 0x194888 (0x1949b8-0x194a7c, the header 0x194b60-)
    sprite_vertices     VU1 sprite loop 0x085-0x0a6 (entries 0x14 / 0x17 / 0x18)
    line_vertices       VU1 line loop 0x0a9-0x0e3 (entry 0x22, then 0x17)
    list_blocks         particle_emitLists 0x194450: which cells of a list are sent
"""
import os
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                                       # noqa: E402

M32 = 0xFFFFFFFF
SIGN = 0x80000000
BIGGEST = 0x7F7FFFFF
ONE = 0x3F800000
TWO23 = 0x4B000000              # 2^23: colours are 2^23 + byte
TWO23_255 = 0x4B0000FF

# GIF tags of the particle packet (VU1 qwords 7 and 10 of the header): 30 vertices pairs
PRIM_SPRITE = 0x156             # sprite, textured (UV), blended
PRIM_LINE = 0x049               # line, Gouraud, blended, untextured
PRIM_TRAIL = 0x154              # triangle strip, textured (UV), blended (flags without 2)
PRIM_TRAIL_PAIRED = 0x15C       # triangle strip, Gouraud, textured, blended (flag 2)
PRIM_GLOW = 0x15E               # sprite ... see glow_vertices
BLOCK = 30                      # particles per VU block (a page holds 8 blocks)

GsVertex = tuple                # (x, y, z, f, adc, rgba, uv)


class Vu:
    """The vector unit's arithmetic on raw patterns (operands: exponent 255 -> largest,
    exponent 0 -> zero; results toward zero by default)."""

    def __init__(self, model='chop'):
        self.f = C.Fpu(model)

    @staticmethod
    def vin(u):
        e = u & 0x7F800000
        if e == 0x7F800000:
            return (u & SIGN) | BIGGEST
        if e == 0:
            return u & SIGN
        return u & M32

    @staticmethod
    def vout(u):
        e = u & 0x7F800000
        if e == 0x7F800000:
            return (u & SIGN) | BIGGEST
        if e == 0:
            return u & SIGN
        return u & M32

    def add(self, a, b):
        return self.vout(self.f.add(self.vin(a), self.vin(b)))

    def sub(self, a, b):
        return self.vout(self.f.add(self.vin(a), self.vin(b) ^ SIGN))

    def mul(self, a, b):
        return self.vout(self.f.mul(self.vin(a), self.vin(b)))

    def madd(self, acc, a, b):
        return self.add(acc, self.mul(a, b))

    def div(self, a, b):
        a, b = self.vin(a), self.vin(b)
        if b & 0x7FFFFFFF == 0:
            return ((a ^ b) & SIGN) | BIGGEST
        return self.vout(self.f.div(a, b))

    def rsqrt(self, a, b):
        a, b = self.vin(a), self.vin(b)
        if b & 0x7FFFFFFF == 0:
            return (a & SIGN) | BIGGEST
        return self.vout(self.f.div(a, self.vout(self.f.sqrt(b & 0x7FFFFFFF))))

    def itof(self, word, shift=0):
        r = self.vout(self.f.from_int(C.s32(word)))
        if shift:
            r = self.mul(r, C.f32(1.0 / (1 << shift)))
        return r

    def ftoi(self, a, shift=0):
        if shift:
            a = self.mul(self.vin(a), C.f32(float(1 << shift)))
        return C.Fpu.to_int(self.vin(a)) & M32

    @staticmethod
    def key(u):
        return -(u & 0x7FFFFFFF) if u & SIGN else u

    def vmax(self, a, b):
        return a if self.key(a) > self.key(b) else b

    def vmin(self, a, b):
        return a if self.key(a) < self.key(b) else b

    def clip(self, v, w):
        """CLIPw.xyz: the six judgement bits (x > |w|, x < -|w|, y ..., z ...)."""
        w = self.vin(w) & 0x7FFFFFFF
        c = 0
        for bit, x in ((1, v[0]), (4, v[1]), (16, v[2])):
            x = self.vin(x)
            if C.Fpu.compare(x, w) > 0:
                c |= bit
            if C.Fpu.compare(x, w | SIGN) < 0:
                c |= bit << 1
        return c

    def transform(self, m, x, y, z, w_last=True):
        """ACC = m0*x; ACC += m1*y; then (w_last) ACC += m2*z; out = ACC + m3*1 - the
        order of the line loop and the trail program - or (not w_last) ACC += m3*1; out =
        ACC + m2*z - the order of the sprite loop.  m: four columns of four (vf1..vf4)."""
        acc = [self.mul(m[0][k], x) for k in range(4)]
        acc = [self.madd(acc[k], m[1][k], y) for k in range(4)]
        if w_last:
            acc = [self.madd(acc[k], m[2][k], z) for k in range(4)]
            return [self.madd(acc[k], m[3][k], ONE) for k in range(4)]
        acc = [self.madd(acc[k], m[3][k], ONE) for k in range(4)]
        return [self.madd(acc[k], m[2][k], z) for k in range(4)]


def gs_xyzf(lanes):
    """(x, y, z, f, adc) of an XYZF2 qword (GIF packed mode)."""
    return (lanes[0] & 0xFFFF, lanes[1] & 0xFFFF, (lanes[2] >> 4) & 0xFFFFFF,
            (lanes[3] >> 4) & 0xFF, (lanes[3] >> 15) & 1)


def gs_rgba(lanes):
    return tuple(x & 0xFF for x in lanes)


# ---------------------------------------------------------------------------------------
# The particle packet: matrices and constants (EE side, particle_draw 0x194888)
# ---------------------------------------------------------------------------------------

PROJ_ARGS = (0x3F7FFFFF, 0x3EEEEEEE, None, ONE, 0x457FFF00, 0x41900000, 0x44E10000)
K_COL0 = 0x3AA3D70A             # 0.00125 = 1/800, element [0][0]
K_COL1 = 0x3B23D70A             # 0.0025 = 1/400, element [1][1]
K_DEPTH = 0x3A000080            # 0.00048828870, elements [2][2] (then - 1.0) and [3][2]
HEADER_SCREEN = (0x44480000, 0x43C80000, 0x5DFFFF00, ONE)        # vf6: 800, 400, depth, 1
HEADER_OFFSET = (0x49008000, 0x49008000, 0x6007FFF8, 0)          # vf7: 2^19 + 2048, ...
SPRITE_HALF = (0x40000000, ONE, 0, 0)                            # vf9: half extent (2h, h)


def particle_projection(proj_scale):
    """The projection particle_draw makes: mat4_setProjection(0x3f7fffff, 0x3eeeeeee,
    g_projScale, 1.0, 4095.94, 18, 1800) with [0][0] * 1/800, [1][1] * 1/400,
    [2][2] * K - 1 and [3][2] * K (0x1949b8-0x194a7c).  The vertex program multiplies x
    and y back by 800 and 400, so a particle's centre projects as level geometry does."""
    sx, sy, _, za, zb, near, far = PROJ_ARGS
    m = C.mat4_set_projection(sx, sy, proj_scale, za, zb, near, far)
    m[0] = C.mul(m[0], K_COL0)
    m[5] = C.mul(m[5], K_COL1)
    m[10] = C.sub(C.mul(m[10], K_DEPTH), ONE)
    m[14] = C.mul(m[14], K_DEPTH)
    return m


def particle_matrix(view, proj_scale):
    """mat4_mulMat34(view, projection): vf1..vf4 of the global list set (and of trails)."""
    return C.mat4_mul_mat34(view, particle_projection(proj_scale))


def group_matrix(group_m, view, proj_scale):
    """A group's matrix (particle_draw, per live group): mat34_mul(group mat34 at +0x100,
    view) then mat4_mulMat34 with the projection.  A group's particles are thus stored in
    the group's own frame and drawn through it; uploaded with MSCAL 0x4a before the group's
    lists, and the global matrix is uploaded again after the last group."""
    return C.mat4_mul_mat34(C.mat34_mul(group_m, view), particle_projection(proj_scale))


def columns(mat4):
    """vf1..vf4 as the VU reads a mat4 upload: row r of the 4x4 (r = 0..3) is register
    vf(r+1); the program multiplies x by vf1, y by vf2, z by vf3 and adds vf4."""
    return [list(mat4[4 * r:4 * r + 4]) for r in range(4)]


def particle_header(view, proj_scale, clock):
    """The constants entry 0x14 loads: (matrix registers, vf5, vf6, vf7, vf9)."""
    clock_f = C.from_int(C.s16(clock))
    return {'m': columns(particle_matrix(view, proj_scale)),
            'vf5': (0x20, TWO23, TWO23_255, clock_f), 'vf6': HEADER_SCREEN,
            'vf7': HEADER_OFFSET, 'vf9': SPRITE_HALF}


# ---------------------------------------------------------------------------------------
# VU1: one particle
# ---------------------------------------------------------------------------------------

def _cell_lanes(cell):
    """The two V4-16 qwords of a 16-byte particle record, sign-extended."""
    w = struct.unpack('<8h', cell)
    return [x & M32 for x in w[:4]], [x & M32 for x in w[4:]]


def _colour(vu, typerec, age):
    c0, crate = typerec[8:12], typerec[12:16]
    out = []
    for k in range(4):
        c = vu.add(vu.mul(c0[k], ONE), vu.mul(crate[k], age))
        out.append(vu.vmin(vu.vmax(c, TWO23), TWO23_255))
    return out


def colour_bytes(typerec, age_raw, vu=None):
    """The four colour bytes the vertex program sends at an age (raw float)."""
    return gs_rgba(_colour(vu or Vu(), typerec, age_raw))


def sprite_vertices(cell, typerec, header, vu=None, stale_zw=(0, 0)):
    """VU1 0x085-0x0a6, one particle of kind 0 or 1: the two sprite corners.
    cell: the 16-byte record; typerec: the 16 words of its type record (+0x10..+0x4f);
    header: particle_header() or group_header(); stale_zw: lanes z, w of vf18, which the
    loop never writes, so the first corner's z and ADC are whatever an earlier program
    left there (the GS ignores both for a sprite).

        age   = clock - birth
        p     = pos + vel/4096 * age ;  p.z += (g * age) * age
        size  = size0 + rate * age
        clip  = ((M0 * p.x + M1 * p.y) + M3) + M2 * p.z
        Q     = 1 / clip.w ;  c = (clip.xyz * (800, 400, Kz), size) * Q ;  c.xyz += offset
        h     = c.w ;  corner 1 = c.xy - (2h, h),  corner 2 = c.xyz + (2h, h, 0)
        colour = clamp(c0 + crate * age, 2^23, 2^23 + 255) ; uv (u0, v0) and (u1, v1)
    A particle outside the view cube (clip test of the 6 planes) gets ADC on corner 2."""
    vu = vu or Vu()
    q0, q1 = _cell_lanes(cell)
    m, vf6, vf7, vf9 = header['m'], header['vf6'], header['vf7'], header['vf9']
    pos = [vu.itof(x) for x in q0]
    vel = [vu.itof(x, 12) for x in q1]
    age = vu.sub(header['vf5'][3], pos[3])
    vel = [vu.mul(vel[k], age) for k in range(3)]
    g, rate, size0 = typerec[2], typerec[3], typerec[7]
    gz = vu.mul(vu.mul(g, age), age)
    a = [vu.add(pos[k], vel[k]) for k in range(3)]
    z = vu.add(gz, a[2])
    size = vu.add(vu.mul(rate, age), size0)
    clip = vu.transform(m, a[0], a[1], z, w_last=False)
    culled = vu.clip(clip, clip[3])
    q = vu.div(ONE, clip[3])
    t = [vu.mul(clip[k], vf6[k]) for k in range(3)] + [size]
    c = [vu.mul(t[k], q) for k in range(4)]
    c = [vu.add(c[k], vf7[k]) for k in range(3)] + [c[3]]
    d = [vu.mul(vf9[k], c[3]) for k in range(4)]
    v1 = [vu.sub(c[0], d[0]), vu.sub(c[1], d[1]), stale_zw[0], stale_zw[1]]
    v2 = [vu.add(c[k], d[k]) for k in range(3)] + [M32 if culled else 0]
    rgba = gs_rgba(_colour(vu, typerec, age))
    uv1 = (typerec[0] & 0x3FFF, typerec[1] & 0x3FFF)
    uv2 = (typerec[4] & 0x3FFF, typerec[5] & 0x3FFF)
    return [gs_xyzf(v1) + (rgba, uv1), gs_xyzf(v2) + (rgba, uv2)]


def line_vertices(cell, typerec, header, vu=None, waitq_first=True):
    """VU1 0x0a9-0x0e3, one particle of kind 2: a Gouraud line from the position now
    (alpha as the colour says) to the position `lag` ticks ago (the same RGB, ALPHA 0).

        age  = clock - birth ;  lag = +0x1c (= sizeStart) ;  g = +0x10
        head = pos + vel/4096 * age, z += (g * age) * age      (the same for age - lag)
        clip = ((M0 * x + M1 * y) + M2 * z) + M3 ;  xyz = clip.xyz * (800, 400, Kz) * Q + offset
    The head's clip test sets ADC on the TAIL (so a line whose head is outside is not
    drawn); the head's own w lane is clip.w * Q (ADC set when that is below 1.0, which
    does nothing on the first vertex of a line).
    waitq_first: the tail is scaled by the `MULq | WAITQ` pair 0x0d2 one cycle after its
    DIV.  True (default): the pair waits for the divider first and uses the tail's own
    1/w.  False: the upper half reads the Q still in place, the head's 1/w - what
    tools/recomp/render/vu1.cpp computes.  Which the machine does is Inferred (True)."""
    vu = vu or Vu()
    q0, q1 = _cell_lanes(cell)
    m, vf6, vf7 = header['m'], header['vf6'], header['vf7']
    pos = [vu.itof(x) for x in q0]
    vel = [vu.itof(x, 12) for x in q1]
    vel[3] = typerec[0]                         # MR32.w: the line gravity (+0x10)
    age = vu.sub(header['vf5'][3], pos[3])
    lag_age = vu.sub(age, typerec[3])

    def at(t):
        p = [vu.mul(vel[k], t) for k in range(4)]
        p[3] = vu.mul(p[3], t)
        p[2] = vu.add(p[2], p[3])
        return [vu.add(p[k], pos[k]) for k in range(4)]
    tail, head = at(lag_age), at(age)
    ch = vu.transform(m, head[0], head[1], head[2])
    culled = vu.clip(ch, ch[3])
    qh = vu.div(ONE, ch[3])
    h = [vu.mul(ch[k], vf6[k]) for k in range(3)] + [ch[3]]
    h = [vu.mul(h[k], qh) for k in range(4)]
    h = [vu.add(h[k], vf7[k]) for k in range(3)] + [h[3]]
    ct = vu.transform(m, tail[0], tail[1], tail[2])
    t = [vu.mul(ct[k], vf6[k]) for k in range(3)] + [ct[3]]
    qt = vu.div(ONE, ct[3]) if waitq_first else qh
    t = [vu.mul(t[k], qt) for k in range(4)]
    t = [vu.add(t[k], vf7[k]) for k in range(3)] + [0xFFFF if culled else 0]
    colour = _colour(vu, typerec, age)
    rgba = gs_rgba(colour)
    tail_rgba = rgba[:3] + (gs_rgba([vu.sub(colour[3], colour[3])])[0],)
    return [gs_xyzf(h) + (rgba, None), gs_xyzf(t) + (tail_rgba, None)]


# ---------------------------------------------------------------------------------------
# Which cells a list sends (particle_emitLists 0x194450)
# ---------------------------------------------------------------------------------------

def list_blocks(pages, head, tail):
    """The VU blocks one list sends: a list of (page index, block number, [cells]) where
    a cell is a cell number 1..30 of the block (31 * block + ...), or None for a cell the
    list zero-fills.  pages: the list's pages oldest first; head: the list's first live
    cell in the first page; tail: the list cursor in the last page (next free cell).

    Whole blocks are sent from the block holding `head` to the block holding the cell
    before `tail`: the retired cells in front of `head` in its block are drawn again with
    whatever they hold (their type field was set to 0 when they were retired, so they
    take slot 0's record, the group definition 0x7e1d00 - Inferred to be invisible:
    every colour of that definition is 0).  The cells from `tail` to the end of its block
    are zero-filled by an UNPACK before the final MSCAL 0x17 (all zero: slot 0 again)."""
    out = []
    for n, page in enumerate(pages):
        first = (head & ~0x1F) if n == 0 else 0
        end = ((tail + 0x1E) & ~0x1F) if n == len(pages) - 1 else 0x100
        for blk in range(first >> 5, end >> 5):
            cells = []
            for c in range(1, 31):
                cell = blk * 32 + c
                cells.append(None if (n == len(pages) - 1 and cell >= tail) else cell)
            out.append((page, blk, cells))
    return out


# ---------------------------------------------------------------------------------------
# Trails: trail_drawAll 0x193ad0 (EE side) and VU1 entries 0x28 (per trail), 0x26 (a chunk
# of single points) and 0x79e (a chunk of point pairs, a program trail_drawAll loads with
# MPG from 0x404150 every frame)
# ---------------------------------------------------------------------------------------

TRAIL_ROW_V = (0.0, 32.0, 64.0, 96.0, 128.0, 224.0, 256.0, 288.0, 351.0, 447.0)   # 0x44fca8
TRAIL_CHUNK = 32                # points per VU chunk
UV_BASE = 0x49000000            # 524288.0 = 2^19: u = 2^19 + age * 128 / lifetime


class Trail:
    """The fields of one 0x410-byte trail (0x82cd00 + i * 0x410) that drawing reads."""
    __slots__ = ('points', 'handle', 'clock', 'oldest', 'newest', 'row', 'flags', 'lifetime',
                 'rgba', 'width4')

    @classmethod
    def from_bytes(cls, b):
        t = cls()
        t.points = [struct.unpack_from('<4h', b, 8 * k) for k in range(128)]
        t.handle, t.clock, t.oldest, t.newest, t.row, t.flags, t.lifetime = \
            struct.unpack_from('<HhBBbBh', b, 0x400)
        t.rgba = tuple(b[0x40A:0x40E])
        t.width4 = b[0x40F]
        return t


def trail_header(t, row_v=TRAIL_ROW_V):
    """The six qwords trail_drawAll 0x193b64 uploads to VU1 0..5 before MSCAL 0x28: the
    strip's GIF tag, a tag for RGBAQ + A+D, the colour, ALPHA_1, then (2^19, v0 + 2^19 +
    0.5, 128 / lifetime, width byte * 40) and (0, 0, (oldest & 1) + 1, clock)."""
    paired = bool(t.flags & 2)
    tag = (0x801E, 0x50AE4000 if paired else 0x40AA4000, 0x43431 if paired else 0x4343, 0)
    v0, v1 = C.f32(row_v[t.row]), C.f32(row_v[t.row + 1])
    vrange = C.sub(C.sub(v1, v0), ONE)
    alpha = 0x09 if t.flags & 8 else 0x48 if t.flags & 4 else 0x44
    q4 = (UV_BASE, C.add(v0, 0x49000008), C.div(0x43000000, C.from_int(t.lifetime)),
          C.from_int(t.width4 * 40))
    return [tag, (1, 0x20000000, 0xE1, vrange), tuple(t.rgba), (alpha, 0, 0x42, 0), q4,
            (0, 0, (t.oldest & 1) + 1, C.from_int(t.clock))]


def trail_chunks(t):
    """The chunks trail_drawAll sends for one trail: (first ring index, count, itop
    parity).  The run starts at the oldest point rounded DOWN to even (so a single-point
    trail whose oldest index is odd draws the slot before it, a point already dropped),
    goes to the newest, at most 32 points per chunk and never across the ring's end."""
    start = t.oldest & 0xFE
    left = (t.newest - start) & 0x7F
    out = []
    while left > 0:
        n = min(left, TRAIL_CHUNK, 0x80 - start)
        out.append((start, n))
        left -= n
        start = (start + n) & 0x7F
    return out


def _gs_xyzf_words(lanes):
    return gs_xyzf(lanes)


def trail_vertices(t, header_m, vf6, vf7, vu=None, waitq_first=True, row_v=TRAIL_ROW_V):
    """Every vertex the trail programs send for trail t, in order (GsVertex tuples with
    rgba as the GS holds it when the vertex arrives; uv in 1/16 texel).  header_m: the
    matrix registers vf1..vf4 VU1 holds - those of the particle packet, which is drawn just
    before (Inferred from the sorted-list order); vf6, vf7 likewise.

    Single points (flags without 2), program 0x26, per point p (positions are half units):
        clip = ((M0 x + M1 y) + M2 z) + M3 ;  n = clip * (1 / clip.w)     (all four lanes)
        d    = n - n_previous (n_previous = 0 for a trail's first point) ;  L = d.x^2 + d.y^2
        side = (d.y, -d.x) * (1 / clip.w) * (width*40 / sqrt(L)), then side.x * 2
        c    = n.xyz * (800, 400, Kz) + offset ;  vertices c + side and c - side
        u    = 2^19 + (clock - stamp) * 128 / lifetime ; v = v0 (first) and v0 + range
    The first point of the trail (and of every chunk's re-sent last point) carries ADC; so
    does a point outside the view cube.  waitq_first=False reproduces vu1.cpp, where the
    second scaling of `side` reads 1 / clip.w again (`MULq | WAITQ` at 0x1ca) and the width
    is lost.
    Pairs (flags 2), program 0x79e, per pair (a, b): both projected (a with its own 1/w,
    b with its own), colour = trail RGB with ALPHA = low byte of b's stamp field (written
    as alpha * 255 by trail_addPair 0x192650), u from a's stamp, v0 for a and v0 + range
    for b; ADC on both when any of the last four clip judgements (this pair and the one
    before in the same chunk) is outside."""
    vu = vu or Vu()
    hdr = trail_header(t, row_v)
    q4, clock_f = hdr[4], hdr[5][3]
    paired = bool(t.flags & 2)
    out = []
    vi10 = (0x8000 + hdr[5][1]) & 0xFFFF
    prev = [0, 0, 0, 0]
    rgba = tuple(x & 0xFF for x in hdr[2])
    saved = None
    first = True

    def mfir(v):
        return (v - 0x10000 if v & 0x8000 else v) & M32

    def proj(p):
        x, y, z = (vu.mul(vu.itof(c, 4), 0x41000000) for c in p[:3])
        return vu.transform(header_m, x, y, z)
    for start, n in trail_chunks(t):
        pts = [t.points[(start + k) & 0x7F] for k in range(n)]
        if not first:
            out += saved
        chunk = []
        if not paired:
            for p in pts:
                clip = proj(p)
                culled = vu.clip(clip, clip[3])
                q = vu.div(ONE, clip[3])
                w = mfir(0x8000 if culled else vi10)
                nd = [vu.mul(clip[k], q) for k in range(4)]
                d = [vu.sub(nd[k], prev[k]) for k in range(4)]
                prev = nd
                sq = [vu.mul(d[k], d[k]) for k in range(4)]
                ln = vu.add(sq[0], sq[1])
                side = [d[1], vu.sub(0, d[0]), 0, 0]
                side = [vu.mul(side[k], q) for k in range(4)]
                q2 = vu.rsqrt(q4[3], ln) if waitq_first else q
                side = [vu.mul(side[k], q2) for k in range(4)]
                side[0] = vu.add(side[0], side[0])
                vi10 = (vi10 - 1) & 0xFFFF
                c = [vu.add(vu.mul(nd[k], vf6[k]), vf7[k]) for k in range(3)]
                left = [vu.add(c[k], side[k]) for k in range(3)] + [w]
                right = [vu.sub(c[k], side[k]) for k in range(3)] + [w]
                age = vu.mul(vu.sub(clock_f, vu.itof(p[3])), q4[2])
                u = vu.add(q4[0], age) & 0x3FFF
                v0 = q4[1] & 0x3FFF
                v1 = vu.add(q4[1], hdr[1][3]) & 0x3FFF
                chunk += [gs_xyzf(left) + (rgba, (u, v0)), gs_xyzf(right) + (rgba, (u, v1))]
        else:
            flags = 0
            for k in range(0, n - 1, 2):
                a, b = pts[k], pts[k + 1]
                ca, cb = proj(a), proj(b)
                flags = ((flags << 6) | vu.clip(ca, ca[3])) & 0xFFFFFF
                flags = ((flags << 6) | vu.clip(cb, cb[3])) & 0xFFFFFF
                qa, qb = vu.div(ONE, ca[3]), vu.div(ONE, cb[3])
                w = mfir(0x8000 if flags else vi10)
                pa = [vu.add(vu.mul(vu.mul(ca[j], qa), vf6[j]), vf7[j]) for j in range(3)] + [w]
                pb = [vu.add(vu.mul(vu.mul(cb[j], qb), vf6[j]), vf7[j]) for j in range(3)] + [w]
                vi10 = (vi10 - 1) & 0xFFFF
                age = vu.mul(vu.sub(clock_f, vu.itof(a[3])), q4[2])
                u = vu.add(q4[0], age) & 0x3FFF
                v0 = q4[1] & 0x3FFF
                v1 = vu.add(q4[1], hdr[1][3]) & 0x3FFF
                col = rgba[:3] + (b[3] & 0xFF,)
                chunk += [gs_xyzf(pa) + (col, (u, v0)), gs_xyzf(pb) + (col, (u, v1))]
                rgba_last = col
            if n & 1:
                raise ValueError('a paired trail chunk with an odd number of points')
        out += chunk
        saved = chunk[-2:]
        first = False
    return out


# ---------------------------------------------------------------------------------------
# Beams ("lightning"): beam_create 0x193088, nodes 0x192a40, drift 0x192e80, points
# 0x192c50, the per-draw rebuild in trail_drawAll 0x193ad0; EE side (ref_core FPU)
# ---------------------------------------------------------------------------------------

K_DRIFT = 0x3DCCCCCC            # 0.099999994
BEAM_COUNT, BEAM_MAX_DEPTH = 20, 5
BEAM_SEED_FRAME, BEAM_SEED_INDEX = 0x229, 0x3F3


class BeamNode:
    __slots__ = ('off', 'drift', 'count')

    def __init__(self, off, drift, count):
        self.off, self.drift, self.count = list(off), list(drift), count

    def words(self):
        return self.off + self.drift + [self.count & M32]


def beam_build_nodes(jitter, depth, cosmetic, libc):
    """beam_buildNodes 0x192a40, called by beam_create with the beam's jitter and depth
    (clamped to 5): a binary tree of offset nodes in pre-order, 2^(depth+1) - 1 of them.
    Per node, six draws of the COSMETIC seed (s = 2u - 1 each, u = draw / 65536), then one
    libc rand():
        offset = (s1, s2, s3) * jitter
        drift  = ((s4 * jitter) - offset.x, (s5 * jitter) - offset.y, (s6 * jitter) - offset.y)
                 * 0.099999994          (z subtracts offset.y, as the code does)
        count  = rand() & 7    (an integer word)
    then the two children with jitter * 0.5.  cosmetic: ref_core.Lcg; libc: ref_core.LibcRand."""
    out = []

    def node(j, d):
        s = [cosmetic.signed_unit() for _ in range(6)]
        off = [C.mul(s[0], j), C.mul(s[1], j), C.mul(s[2], j)]
        drift = [C.mul(C.sub(C.mul(s[3], j), off[0]), K_DRIFT),
                 C.mul(C.sub(C.mul(s[4], j), off[1]), K_DRIFT),
                 C.mul(C.sub(C.mul(s[5], j), off[1]), K_DRIFT)]
        out.append(BeamNode(off, drift, libc.rand() & 7))
        if d != 0:
            node(C.mul(j, C.HALF), d - 1)
            node(C.mul(j, C.HALF), d - 1)
    node(jitter, depth)
    return out


def beam_drift_nodes(nodes, jitter, depth, cosmetic):
    """beam_driftNodes 0x192e80, once per draw while the game is not frozen (trail_drawAll):
    in pre-order, every node moves by its drift and counts down; a node whose count was
    below 1 picks a new target: drift = ((s * jitter) - offset) * 0.099999994 per axis
    (three cosmetic draws, x y z, against the moved offset), count = (seed >> 21) & 7 of a
    fourth draw.  The children use jitter * 0.5."""
    it = iter(nodes)

    def node(j, d):
        n = next(it)
        old = C.s32(n.count)
        n.off = [C.add(n.off[k], n.drift[k]) for k in range(3)]
        n.count = (old - 1) & M32
        if old < 1:
            s = [cosmetic.signed_unit() for _ in range(3)]
            n.drift = [C.mul(C.sub(C.mul(s[k], j), n.off[k]), K_DRIFT) for k in range(3)]
            cosmetic.draw()
            n.count = (cosmetic.state >> 21) & 7
        if d != 0:
            node(C.mul(j, C.HALF), d - 1)
            node(C.mul(j, C.HALF), d - 1)
    node(jitter, depth)


def beam_points(nodes, a, b, depth, scale, cosmetic, amplitude=ONE):
    """beam_buildPoints 0x192c50: recursive midpoint displacement, in order from a to b.
    For each segment (a, b), using the next node in pre-order and three cosmetic draws:
        mid = (((a + b) * 0.5) + node.offset) + ((s * amplitude) * scale)   per axis
    then the left half (amplitude * 0.5), the point mid, the right half.  The ends a and b
    themselves are not points: a beam of depth d is a polyline of 2^(d+1) - 1 midpoints."""
    it = iter(nodes)
    out = []

    def seg(amp, p, q, d):
        s = [cosmetic.signed_unit() for _ in range(3)]
        n = next(it)
        mid = [C.add(C.add(C.mul(C.add(p[k], q[k]), C.HALF), n.off[k]),
                     C.mul(C.mul(s[k], amp), scale)) for k in range(3)]
        if d != 0:
            seg(C.mul(amp, C.HALF), p, mid, d - 1)
        out.append(mid)
        if d != 0:
            seg(C.mul(amp, C.HALF), mid, q, d - 1)
    seg(amplitude, a, b, depth)
    return out


def beam_frame_seed(sim_frame, index):
    """The seed trail_drawAll puts in g_cosmeticSeed while it rebuilds beam `index`'s points
    (and restores afterwards): the shape changes once per simulation frame, the node drift
    once per drawn frame."""
    return (sim_frame * BEAM_SEED_FRAME + index * BEAM_SEED_INDEX) & M32


def trail_point(pos, stamp):
    """trail_addPoint 0x192550: the ring entry for a position (half units, truncated)."""
    return tuple(C.s16(C.to_int(C.add(p, p))) for p in pos) + (C.s16(stamp),)


def beam_trail_points(points):
    """What a beam's drawing trail holds after the rebuild: its clock was set to 0 and goes
    up by 1 after each point, so stamps run 1, 2, ... (trail_addPoint stamps clock + 1).
    Returns (ring entries, clock)."""
    return [trail_point(p, k + 1) for k, p in enumerate(points)], len(points)


# ---------------------------------------------------------------------------------------
# Glow sprites: glow_add 0x18fc78 (the queue) and glow_draw 0x1907d0 (EE side, ref_core FPU)
# ---------------------------------------------------------------------------------------

GLOW_MAX = 0x400
K_SIXTEEN = 0x41800000
K_DEPTH_MIN, K_X_LIMIT, K_Y_LIMIT = 0x41A00000, 0x442F0000, 0x43960000     # 20, 700, 300
GLOW_DIMX_ON, GLOW_DIMX_OFF = 0x1212303012123030, 0x3131757531317575
M64 = (1 << 64) - 1


class Glow:
    """One 0x20-byte record of g_glowQueue 0x7d8b00: pos (3 raw floats) +0, size +0xc,
    bias +0x10, r g b a +0x14..+0x17, texture +0x18, angle (u16) +0x1c, flags (s16) +0x1e.
    glow_add(bias f12, size f13, pos a0, r a1, g a2, b a3, a t0, texture t1, angle t2,
    flags t3) fills one, unless 0x400 are queued already (the 0x401st is dropped)."""
    __slots__ = ('pos', 'size', 'bias', 'rgba', 'tex', 'angle', 'flags')

    def __init__(self, pos, size, bias, rgba, tex, angle, flags):
        self.pos, self.size, self.bias = list(pos), size, bias
        self.rgba, self.tex = tuple(x & 0xFF for x in rgba), tex
        self.angle, self.flags = angle & 0xFFFF, C.s16(flags)

    @classmethod
    def from_bytes(cls, b):
        pos = list(struct.unpack_from('<3I', b, 0))
        size, bias = struct.unpack_from('<II', b, 0xC)
        tex, angle, flags = struct.unpack_from('<IHh', b, 0x18)
        return cls(pos, size, bias, tuple(b[0x14:0x18]), tex, angle, flags)


GS_REG = {'PRIM': 0x00, 'RGBAQ': 0x01, 'UV': 0x03, 'XYZ2': 0x05, 'TEX0_1': 0x06, 'XYZ3': 0x0D,
          'TEX1_1': 0x14, 'TEXFLUSH': 0x3F, 'ALPHA_1': 0x42, 'DIMX': 0x44, 'TEST_1': 0x47}


def _ad(value, reg):
    """One A+D write: (GS register address, 64-bit value)."""
    return (GS_REG[reg], value & M64)


def glow_project(g, cam, viewproj):
    """The screen position of one glow, or None when it is not drawn.
    cam: g_cameraMatrix 0x44f110 (mat34, 12 raw floats); viewproj: g_viewProj 0x44f140.
        fwd   = column 2 of the camera matrix
        p'    = pos - fwd * bias            (per axis: y, z, x in the code's order)
        q, w  = g_viewProj * p' ;  depth = w + bias
        drawn when 20 <= depth, |q.x| <= depth * 700, |q.y| <= depth * 300
        X = int(q.x * (1/depth) * 16) + 0x8000, Y likewise, Z = int(q.z * (1/(depth - bias)) * 16)
        H = int((size * 16) * (1/depth))
    Returns (X, Y, Z, H) as integers."""
    fwd = (cam[2], cam[5], cam[8])
    p = [C.sub(g.pos[k], C.mul(fwd[k], g.bias)) for k in range(3)]
    q, w = C.mat4_transform_point(viewproj, p)
    depth = C.add(w, g.bias)
    if C.lt(depth, K_DEPTH_MIN):
        return None
    if C.lt(C.mul(depth, K_X_LIMIT), C.fabs(q[0])) or C.lt(C.mul(depth, K_Y_LIMIT), C.fabs(q[1])):
        return None
    inv = C.div(ONE, depth)
    invz = C.div(ONE, C.sub(depth, g.bias))
    x, y, z = C.mul(q[0], inv), C.mul(q[1], inv), C.mul(q[2], invz)
    X = C.s32(C.to_int(C.mul(x, K_SIXTEEN))) + 0x8000
    Y = C.s32(C.to_int(C.mul(y, K_SIXTEEN))) + 0x8000
    Z = C.s32(C.to_int(C.mul(z, K_SIXTEEN)))
    H = C.s32(C.to_int(C.mul(C.mul(g.size, K_SIXTEEN), inv)))
    return X, Y, Z, H


def _xyz(x, y, z):
    return (x | (y << 16) | (z << 32)) & M64


def glow_vertices(g, X, Y, Z, H, tex_w, tex_h):
    """The GIF A+D writes of one glow: RGBAQ (Q = 0), then
    flags bit 0 clear: a SPRITE from (X - 2H, Y - H) to (X + 2H, Y + H), UV from texel
        (1, 1) to (width - 1, height - 1) of the texture header (+0, +2);
    flags bit 0 set: a quad (triangle strip, first two vertices by XYZ3) turned by the
        angle: C = int(cos16(angle) * float(H)), S = int(sin16(angle) * float(H)),
        corners (X - 2C, Y - S), (X + 2S, Y - C), (X - 2S, Y + C), (X + 2C, Y + S) with UV
        (1,1), (w-1,1), (1,h-1), (w-1,h-1).
    X, Y and Z are packed into one 64-bit value with 32-bit arithmetic, so an X - 2H below
    0 spills its sign into Y and Z (as the code does; such sprites are off screen anyway)."""
    rgba = g.rgba[0] | g.rgba[1] << 8 | g.rgba[2] << 16 | g.rgba[3] << 24
    rgba = rgba - (1 << 32) if rgba & SIGN else rgba
    out = [_ad(rgba & M32, 'RGBAQ')]
    u1 = ((tex_w - 1) << 4)
    v1 = ((tex_h - 1) << 20)
    if not g.flags & 1:
        out += [_ad(0x100010, 'UV'), _ad(_xyz(X - 2 * H, Y - H, Z), 'XYZ2'),
                _ad(u1 | v1, 'UV'), _ad(_xyz(X + 2 * H, Y + H, Z), 'XYZ2')]
        return out
    hf = C.from_int(H)
    c = C.s32(C.to_int(C.mul(C.cos16(g.angle), hf)))
    s = C.s32(C.to_int(C.mul(C.sin16(g.angle), hf)))
    out += [_ad(0x100010, 'UV'), _ad(_xyz(X - 2 * c, Y - s, Z), 'XYZ3'),
            _ad(u1 | 0x100000, 'UV'), _ad(_xyz(X + 2 * s, Y - c, Z), 'XYZ3'),
            _ad(v1 | 0x10, 'UV'), _ad(_xyz(X - 2 * s, Y + c, Z), 'XYZ2'),
            _ad(u1 | v1, 'UV'), _ad(_xyz(X + 2 * c, Y + s, Z), 'XYZ2')]
    return out


def glow_packets(queue, pass_, cam, viewproj, tex_dims):
    """glow_draw(pass): one packet per (texture, flags) in queue order, for the records
    whose flags bit 2 equals pass.  Returns [(sort key, texture, events)].  The packet is
    handed to gfx_addSortedPacket with key 4 for pass 1 (drawn after the particle packet)
    and key 3 for pass 0 (before every key-4 packet).  Events: the A+D register writes
    TEXFLUSH, TEX0 (0 here: gfx_dmaHandler 0x16b998 patches packet +0x30 with the
    texture's TEX0), TEX1 0x61 (bilinear), TEST 0x71001, DIMX, ALPHA_1 (flags bit 1:
    0x48 additive, else 0x44), PRIM by the tag (0x15e sprite / 0x15c strip, Gouraud,
    textured, blended, UV), the glows, DIMX back.  Records are consumed (texture field
    cleared) by the packet that takes them, drawn or culled; queue: Glow list, modified."""
    out = []
    while True:
        first = next((i for i, g in enumerate(queue) if g.tex and ((g.flags >> 2) & 1) == pass_), None)
        if first is None:
            return out
        tex, flags = queue[first].tex, queue[first].flags
        ev = [_ad(0, 'TEXFLUSH'), _ad(0, 'TEX0_1'), _ad(0x61, 'TEX1_1'), _ad(0x71001, 'TEST_1'),
              _ad(GLOW_DIMX_ON, 'DIMX'), _ad(0x48 if flags & 2 else 0x44, 'ALPHA_1')]
        prim = 0x15C if flags & 1 else 0x15E
        for g in queue[first:]:
            if g.tex != tex or g.flags != flags:
                continue
            g.tex = 0
            sp = glow_project(g, cam, viewproj)
            if sp is not None:
                ev += glow_vertices(g, *sp, *tex_dims[tex])
        ev.append(_ad(GLOW_DIMX_OFF, 'DIMX'))
        out.append((4 if pass_ else 3, tex, prim, ev))


# ---------------------------------------------------------------------------------------
# Trail builders (EE side): trail_addPair 0x192650, spline_eval 0x1911e8, trail_setSpline
# 0x1918a0, trail_sweepPairs 0x191ea0, trail_setCircle 0x1920e0, trail_clear 0x191e58
# ---------------------------------------------------------------------------------------

K_NEAR_X = 0x3A83126E           # 0.0009999999: "normal is (1, 0, 0)" in trail_setCircle
THREE, SIX, MINUS_TWO, MINUS_SIX = 0x40400000, 0x40C00000, 0xC0000000, 0xC0C00000


def trail_pair(alpha, a, b, clock):
    """trail_addPair(alpha f12, handle, a, b): two ring entries, the first stamped clock + 1,
    the second's stamp field holding int(alpha * 255) - the alpha the pair program sends."""
    return [trail_point(a, clock + 1), trail_point(b, C.to_int(C.mul(alpha, 0x437F0000)))]


def _tangent(p, q, r):
    """((q - p) + (r - q)) * 0.5 per axis, as the spline code forms a Catmull-Rom tangent."""
    return [C.mul(C.add(C.sub(q[k], p[k]), C.sub(r[k], q[k])), C.HALF) for k in range(3)]


def spline_eval(t, pts, count, want_pos=True, want_tangent=True):
    """spline_eval 0x1911e8 (t f12, points a0, count a1, position out a2, tangent out a3,
    either may be 0): a Catmull-Rom spline through `count` points, Hermite segments.
        t = min(max(t, 0), 1) ;  f = t * (count - 1) ;  i = int(f) ;  s = f - i
        m0 = 0 for i < 1, else ((p[i] - p[i-1]) + (p[i+1] - p[i])) * 0.5
        m1 = 0 for i >= count - 2, else ((p[i+2] - p[i+1]) + (p[i+1] - p[i])) * 0.5
        position = vec3_hermite(s, p[i], p[i+1], m0, m1), tangent its derivative
    At t = 1, i = count - 1 and p[i+1] is read one point past the array: pts may hold more
    than `count` points to stand for that memory."""
    t = C.fmin(C.fmax(t, C.ZERO), ONE)
    f = C.mul(t, C.from_int(count - 1))
    i = C.s32(C.to_int(f))
    s = C.sub(f, C.from_int(i))
    m0 = [0, 0, 0] if i < 1 else [C.mul(C.add(C.sub(pts[i][k], pts[i - 1][k]),
                                                C.sub(pts[i + 1][k], pts[i][k])), C.HALF)
                                   for k in range(3)]
    m1 = [0, 0, 0] if i >= count - 2 else [C.mul(C.add(C.sub(pts[i + 2][k], pts[i + 1][k]),
                                                         C.sub(pts[i + 1][k], pts[i][k])), C.HALF)
                                            for k in range(3)]
    pos = C.vec3_hermite(s, pts[i], pts[i + 1], m0, m1) if want_pos else None
    tan = C.vec3_hermite_derivative(s, pts[i], pts[i + 1], m0, m1) if want_tangent else None
    return pos, tan


def trail_set_spline(start_t, end_t, pts, count, steps):
    """trail_setSpline 0x1918a0 (start f12, end f13, handle a0, points a1, count a2, steps
    a3): empties the trail, sets its lifetime to per * (count - 1) with per = steps //
    (count - 1), and adds per points along each Hermite segment (tangents as spline_eval),
    at t = (1 / per) * k: k from int(start * per) in the first segment, to below
    int(end * per) in the last, otherwise 0 .. per - 1.  The trail clock goes up by 1
    after each point (stamps 1, 2, ...).  Returns (positions, lifetime)."""
    per = C.s32(steps) // (count - 1) if steps >= 0 else -((-steps) // (count - 1))
    out = []
    perf = C.from_int(per)
    inv = C.div(ONE, perf)
    for i in range(count - 1):
        if i < 1:
            m0, k0 = [0, 0, 0], C.s32(C.to_int(C.mul(start_t, perf)))
        else:
            m0, k0 = [C.mul(C.add(C.sub(pts[i][k], pts[i - 1][k]), C.sub(pts[i + 1][k], pts[i][k])),
                            C.HALF) for k in range(3)], 0
        if i < count - 2:
            m1, k1 = [C.mul(C.add(C.sub(pts[i + 2][k], pts[i + 1][k]), C.sub(pts[i + 1][k], pts[i][k])),
                            C.HALF) for k in range(3)], per
        else:
            m1, k1 = [0, 0, 0], C.s32(C.to_int(C.mul(end_t, perf)))
        for k in range(k0, k1):
            out.append(C.vec3_hermite(C.mul(inv, C.from_int(k)), pts[i], pts[i + 1], m0, m1))
    return out, C.s16(per * (count - 1))


def trail_sweep_pairs(centre, axis, a, b, steps):
    """trail_sweepPairs 0x191ea0 (handle a0, centre a1, axis a2, a a3, b t0, steps t1):
    empties the trail, steps = min(steps, 60) is also the lifetime; q = quat_fromAxisAngle
    (axis, s16(0x10000 // (steps - 2))); then `steps` times: the pair (a + centre, b +
    centre) with alpha 1.0, a and b turned by q (quat_rotateVec), clock + 1.
    Returns ([(p0, p1)], lifetime)."""
    steps = min(steps, 60)
    q = C.quat_from_axis_angle(axis[0], axis[1], axis[2], C.s16(0x10000 // (steps - 2)))
    out = []
    for _ in range(steps):
        out.append(([C.add(a[k], centre[k]) for k in range(3)], [C.add(b[k], centre[k]) for k in range(3)]))
        a = C.quat_rotate_vec(q, a)
        b = C.quat_rotate_vec(q, b)
    return out, steps


def trail_set_circle(radius, centre, normal, steps):
    """trail_setCircle 0x1920e0 (radius f12, handle a0, centre a1, normal a2, steps a3):
    empties the trail (its lifetime is left as it was) and adds min(steps, 120) points on
    the circle round `centre` in the plane of `normal`:
        r = (1, 0, 0), or (0, 0, 1) when |normal - (1, 0, 0)|^2 < 0.001
        u = normalize(normal x r) ; v = normalize(u x normal)   (rsqrt.s(1, |.|^2))
        point k = (centre + u * radius * cos16(A)) + v * radius * sin16(A),
        A = 0, then A + 0xffff // steps as a 16-bit angle.
    Returns the positions."""
    steps = min(steps, 120)
    n = normal
    test = C.add(C.add(C.mul(C.sub(n[0], ONE), C.sub(n[0], ONE)), C.mul(n[1], n[1])), C.mul(n[2], n[2]))
    r = [0, 0, ONE] if C.lt(test, K_NEAR_X) else [ONE, 0, 0]
    u = [C.sub(C.mul(n[1], r[2]), C.mul(n[2], r[1])), C.sub(C.mul(n[2], r[0]), C.mul(n[0], r[2])),
         C.sub(C.mul(n[0], r[1]), C.mul(n[1], r[0]))]
    inv = C.rsqrt(ONE, C.add(C.add(C.mul(u[0], u[0]), C.mul(u[1], u[1])), C.mul(u[2], u[2])))
    u = [C.mul(x, inv) for x in u]
    v = [C.sub(C.mul(u[1], n[2]), C.mul(u[2], n[1])), C.sub(C.mul(u[2], n[0]), C.mul(u[0], n[2])),
         C.sub(C.mul(u[0], n[1]), C.mul(u[1], n[0]))]
    inv = C.rsqrt(ONE, C.add(C.add(C.mul(v[0], v[0]), C.mul(v[1], v[1])), C.mul(v[2], v[2])))
    v = [C.mul(C.mul(x, inv), radius) for x in v]
    u = [C.mul(x, radius) for x in u]
    step = 0xFFFF // steps
    angle = 0
    out = []
    for _ in range(steps):
        c, s = C.cos16(angle), C.sin16(angle)
        out.append([C.add(C.add(centre[k], C.mul(u[k], c)), C.mul(v[k], s)) for k in range(3)])
        angle = C.s16(angle + step)
    return out
