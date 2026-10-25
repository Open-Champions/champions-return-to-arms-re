#!/usr/bin/env python3
"""ref_decals.py - reference contract of the floor decals of Champions: Return to Arms
(SLUS_209.73, US v2.00): decal_add 0x19f110 (detail gate, 30 x 30 cell grid, 64 blocks
of 15 decals, the 0x18-byte record, the 16 growing slots) and the growth step at the head
of decal_drawTask 0x19f4e8.

A research tool, not game code.  Round 2 (2026-10-18): written from the code and compared
with it, executed in tools/ee_emu.py, by tools/difftest_decals.py (bit for bit: the float
work goes through tools/ref_core.py, which follows the console's FPU).  docs/effects.md
section 8 is the prose version.  Standard library only; no game data.

    import ref_decals as D
    store = D.DecalStore(detail=2)
    d = store.add(12.0, (100.0, -40.0, 8.0), angle=0x1234, kind=9, grow=1, tint=(90, 80, 70))
    for _ in range(70):
        store.grow_step()
    print(d.record())          # the 24 bytes the vertex program reads

`tint` is what light_sampleFloor 0x148ff0 returns for the position (ref_lighting.decal_tint).
Floats are Python floats that hold single-precision values; positions given as Python
floats are first rounded to single precision, as a caller storing them would.
"""
import os
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                      # noqa: E402

GRID = 30                    # cells per side, 256 units each, origin -3840 (0xf00)
GRID_ORIGIN = 0xF00
BLOCKS = 64                  # 0x840450, 0x180 bytes each; free head 0x846450, link +0x170
PER_BLOCK = 15               # count at block +0x178
GROW_SLOTS = 16              # 0x840310, 0x14 bytes each
TEX_BASE = 0x3D3             # VU address of the texture rectangle of type 0, two qwords a type
STEP_FAST = C.to_float(0x3E4CCCCC)        # 0.19999999: grow modes other than 2
STEP_SLOW = C.to_float(0x3D4CCCCC)        # 0.049999997: grow mode 2


def _p(x):
    return C.f32(x)


def _f(p):
    return C.to_float(p)


def _trunc(p):
    return C.to_int(p)


def s16(v):
    return C.s16(v)


def allowed(kind, detail):
    """The gate of decal_add (g_decalDetail 0x44fdc0): detail 0 makes only types >= 3 (the
    comparison is unsigned, so a negative type passes), 1 every type but 0, 2 and above all."""
    k = kind & 0xFFFFFFFFFFFFFFFF
    if detail == 0 and k <= 2:
        return False
    if detail == 1 and k == 0:
        return False
    return True


def cell_of(x, y):
    """(cx, cy) of the decal grid or None: ((trunc(x) + 3840) >> 8, (trunc(y) + 3840) >> 8),
    both 0..29.  x, y single-precision floats."""
    cx = (_trunc(_p(x)) + GRID_ORIGIN) >> 8
    cy = (_trunc(_p(y)) + GRID_ORIGIN) >> 8
    if 0 <= cx < GRID and 0 <= cy < GRID:
        return cx, cy
    return None


class Decal:
    __slots__ = ('rgb', 'x4', 'y4', 'z4', 'counted', 'c4', 's4', 'tex', 'kind')

    def record(self):
        """The three qwords of s16 (0x18 bytes) as decal_add writes them; the last s16 is
        not written by decal_add (left as the block held it, 0 here)."""
        return struct.pack('<12h', self.rgb[0], self.rgb[1], self.rgb[2], 0x80,
                           self.x4, self.y4, self.z4, self.counted,
                           self.c4, self.s4, self.tex, 0)


class Block:
    __slots__ = ('index', 'decals', 'zmin', 'zmax', 'counted')

    def __init__(self, index):
        self.index = index
        self.decals = []
        self.zmin = self.zmax = 0      # +0x174 / +0x176 as the reset left them (0)
        self.counted = 0               # +0x17c: decals of types 0-2


class Grower:
    __slots__ = ('mode', 'decal', 'angle', 'size', 'final')


class DecalStore:
    """The decal grid, blocks and growing slots after the level reset (all blocks free in
    index order, cells empty, no growing decal)."""

    def __init__(self, detail=2):
        self.detail = detail
        self.free = list(range(BLOCKS))
        self.cells = {}
        self.growers = [None] * GROW_SLOTS
        self.total = 0                 # 0x4d8a00: decals made (the draw task skips while 0)

    def add(self, size, pos, angle, kind, grow=0, tint=(0, 0, 0)):
        """decal_add(size f12, pos a0, angle16 a1, type a2, grow a3).  Returns the Decal,
        or None when the gate, the grid, the blocks or the cell drop it."""
        if not allowed(kind, self.detail):
            return None
        x, y, z = (_p(c) for c in pos)
        c = cell_of(_f(x), _f(y))
        if c is None:
            return None
        blk = self.cells.get(c)
        if blk is None:
            if not self.free:
                return None
            blk = self.cells[c] = Block(self.free.pop(0))
        if len(blk.decals) >= PER_BLOCK:
            return None
        sz = _p(size)
        four = C.f32(4.0)
        d = Decal()
        d.kind = kind
        d.rgb = tuple(int(v) & 0xFF for v in tint)
        d.x4 = s16(_trunc(C.mul(x, four)))
        d.y4 = s16(_trunc(C.mul(y, four)))
        d.z4 = s16(_trunc(C.mul(C.add(z, C.f32(3.0)), four)))
        d.counted = 1 if (kind & 0xFFFFFFFFFFFFFFFF) < 3 else 0
        d.c4 = s16(_trunc(C.mul(C.mul(C.cos16(angle), sz), four)))
        d.s4 = s16(_trunc(C.mul(C.mul(C.sin16(angle), sz), four)))
        d.tex = s16(kind * 2 + TEX_BASE)
        blk.decals.append(d)
        blk.counted += d.counted
        if C.lt(z, C.from_int(blk.zmin)):
            blk.zmin = s16(_trunc(z))
        if C.lt(C.from_int(blk.zmax), z):
            blk.zmax = s16(_trunc(z))
        self.total += 1
        if grow:
            for i in range(GROW_SLOTS):
                if self.growers[i] is None:
                    gr = Grower()
                    gr.mode, gr.decal, gr.angle = grow & 0xFF, d, angle & 0xFFFF
                    gr.size, gr.final = 0, sz          # sizes as float patterns
                    self.growers[i] = gr
                    break
        return d

    def grow_step(self, frozen=False):
        """The head of decal_drawTask (one call per rendered frame while decals exist and
        the game is not frozen): size += 0.19999999 (0.049999997 for mode 2), the decal's
        corner vector is rewritten from it, and the slot is let go once size >= final - so
        the last size can pass the final one by up to one step."""
        if frozen or self.total == 0:
            return
        four = C.f32(4.0)
        for i, gr in enumerate(self.growers):
            if gr is None:
                continue
            step = C.f32(STEP_SLOW if gr.mode == 2 else STEP_FAST)
            gr.size = C.add(gr.size, step)
            gr.decal.c4 = s16(_trunc(C.mul(C.mul(C.cos16(gr.angle), gr.size), four)))
            gr.decal.s4 = s16(_trunc(C.mul(C.mul(C.sin16(gr.angle), gr.size), four)))
            if C.le(gr.final, gr.size):
                self.growers[i] = None

    def decals(self):
        for c in sorted(self.cells, key=lambda c: (c[1], c[0])):
            for d in self.cells[c].decals:
                yield c, d
