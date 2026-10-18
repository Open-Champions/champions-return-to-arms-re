#!/usr/bin/env python3
"""difftest_decals.py - compare tools/ref_decals.py with the game's own machine code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_decals.py [path/to/SLUS_209.73] [--quick] [--seed N] [-v]

How it is tested
    decal_reset 0x19f018, decal_add 0x19f110 and the growth step at the head of
    decal_drawTask 0x19f4e8 (run up to the end of its slot loop, 0x19f60c) are executed by
    tools/ee_emu.py.  light_sampleFloor 0x148ff0 is replaced by a stub that returns a random
    packed colour, handed to the model as the tint (it is difftested on its own by
    tools/difftest_lighting.py, "floor tint").  After every operation the grid (900 cell
    pointers), the free-block list in order, every used block (count, z range, counted
    decals, the 0x18-byte records), the 16 growing slots (mode, decal, angle, size and final
    size as bit patterns) and the decal total are compared with the model, bit for bit.

Property
    decals      random sequences of decal_add (types -1..12, sizes, angles, grow modes 0-3,
                detail 0-2, positions inside and outside the grid, full cells, all 64 blocks
                used) and growth steps (frozen and not)
"""
import hashlib
import os
import random
import struct
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, M32                 # noqa: E402
import ref_core as C                       # noqa: E402
import ref_decals as D                     # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = {'quick': False, 'seed': 20973, 'verbose': False}

DECAL_RESET, DECAL_ADD, DECAL_DRAW, GROW_END, GROW_FROZEN = 0x19F018, 0x19F110, 0x19F4E8, 0x19F60C, 0x19F610
SAMPLE_FLOOR, IS_FROZEN = 0x148FF0, 0x1EBDF8
G_DETAIL, G_BLOCKS, G_FREE, G_GRID, G_GROW, G_TOTAL, G_ENABLED = (
    0x44FDC0, 0x840450, 0x846450, 0x846458, 0x840310, 0x4D8A00, 0x4D8A08)
BLOCK = 0x180


class Game:
    def __init__(self, elf):
        e = self.emu = EE(elf)
        e.record_writes = e.record_calls = False
        self.tint = 0
        self.frozen = 0
        e.stub(SAMPLE_FLOOR, function=lambda emu: self.tint)
        e.stub(IS_FROZEN, function=lambda emu: self.frozen)
        e.call(DECAL_RESET)
        e.mem.write(G_GROW, bytes(16 * 0x14))     # (decal_reset leaves these alone)
        e.mem.w8(G_ENABLED, 1)
        self.pos = e.alloc(16)

    def add(self, size, pos, angle, kind, grow):
        m = self.emu.mem
        for i in range(3):
            m.wf32(self.pos + 4 * i, pos[i])
        self.emu.call(DECAL_ADD, self.pos, angle & 0xFFFF, kind & 0xFFFFFFFFFFFFFFFF, grow,
                      fargs=(size,))

    def grow(self):
        e = self.emu
        e.r[31] = e.RETURN_ADDR
        e.run(start=DECAL_DRAW, until=[GROW_END, GROW_FROZEN])

    def state(self):
        m = self.emu.mem
        block_of = lambda a: (a - G_BLOCKS) // BLOCK
        grid = {}
        for cy in range(30):
            for cx in range(30):
                a = m.u32(G_GRID + 4 * (cy * 30 + cx))
                if a:
                    grid[(cx, cy)] = block_of(a)
        free, a = [], m.u32(G_FREE)
        while a:
            free.append(block_of(a))
            a = m.u32(a + 0x170)
        blocks = {}
        for c, b in grid.items():
            base = G_BLOCKS + BLOCK * b
            n = m.s32(base + 0x178)
            recs = tuple(m.read(base + 0x18 * i, 0x16) for i in range(n))
            blocks[b] = (n, m.s16(base + 0x174), m.s16(base + 0x176), m.s32(base + 0x17C), recs)
        grow = []
        for i in range(16):
            g = G_GROW + 0x14 * i
            p = m.u32(g + 4)
            if p:
                b, off = divmod(p - G_BLOCKS, BLOCK)
                grow.append((i, m.u8(g), b, (off - 0x10) // 0x18, m.u16(g + 8), m.u32(g + 0xC), m.u32(g + 0x10)))
        return grid, tuple(free), blocks, tuple(grow), m.s32(G_TOTAL)


def model_state(st):
    grid = {c: b.index for c, b in st.cells.items()}
    blocks = {}
    for c, b in st.cells.items():
        recs = tuple(d.record()[:0x16] for d in b.decals)
        blocks[b.index] = (len(b.decals), b.zmin, b.zmax, b.counted, recs)
    grow = []
    for i, gr in enumerate(st.growers):
        if gr is not None:
            blk = next(b for b in st.cells.values() if gr.decal in b.decals)
            grow.append((i, gr.mode, blk.index, blk.decals.index(gr.decal), gr.angle, gr.size, gr.final))
    return grid, tuple(st.free), blocks, tuple(grow), st.total


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    positional = []
    while argv:
        a = argv.pop(0)
        if a == '--quick':
            OPTIONS['quick'] = True
        elif a == '-v':
            OPTIONS['verbose'] = True
        elif a == '--seed':
            OPTIONS['seed'] = int(argv.pop(0), 0)
        else:
            positional.append(a)
    elf = next((p for p in positional + [os.path.join(ROOT, 'SLUS_209.73')] if os.path.isfile(p)), None)
    if elf is None:
        print('SKIP  no SLUS_209.73 found (pass its path); nothing was tested')
        return 0
    with open(elf, 'rb') as h:
        if hashlib.sha256(h.read()).hexdigest() != EXPECTED_SHA256:
            print('SKIP  %s is not the US v2.00 executable this test was written for' % elf)
            return 0
    t0 = time.time()
    rng = random.Random(OPTIONS['seed'])
    cases = 8 if OPTIONS['quick'] else 80
    fails, ex, ops, made, dropped, grown = 0, [], 0, 0, 0, 0
    for case in range(cases):
        g = Game(elf)
        detail = rng.choice([0, 1, 2, 2])
        g.emu.mem.w32(G_DETAIL, detail)
        st = D.DecalStore(detail)
        spread = rng.choice([300.0, 1500.0, 5000.0])
        bad = None
        for step in range(rng.choice([100, 400, 1500])):
            if rng.random() < 0.75:
                size = C.to_float(C.f32(rng.choice([12.0, rng.uniform(0, 80), float(rng.randint(1, 40))])))
                pos = tuple(C.to_float(C.f32(v)) for v in (rng.uniform(-spread, spread), rng.uniform(-spread, spread),
                                                          rng.uniform(-500, 500)))
                angle = rng.randint(0, 0xFFFF)
                kind = rng.choice([0, 1, 2, 3, 4, 6, 9, 10, rng.randint(-1, 12)])
                grow = rng.choice([0, 0, 0, 1, 2, 3])
                tint = rng.getrandbits(24)
                g.tint = tint
                g.add(size, pos, angle, kind, grow)
                d = st.add(size, pos, angle, kind, grow, (tint & 0xFF, (tint >> 8) & 0xFF, (tint >> 16) & 0xFF))
                made += d is not None
                dropped += d is None
                what = 'add %r' % ((size, pos, angle, kind, grow),)
            else:
                g.frozen = 1 if rng.random() < 0.1 else 0
                g.grow()
                st.grow_step(frozen=bool(g.frozen))
                grown += 1
                what = 'grow (frozen %d)' % g.frozen
            ops += 1
            so, sm = g.state(), model_state(st)
            if so != sm:
                names = ('grid', 'free', 'blocks', 'growers', 'total')
                bad = 'step %d %s: differs in %s' % (step, what, [n for n, a, b in zip(names, so, sm) if a != b])
                break
        if bad:
            fails += 1
            ex.append('case %d (detail %d): %s' % (case, detail, bad))
    ok = not fails
    print('executable %s, seed %d' % (elf, OPTIONS['seed']))
    print('%s  decals         %7d cases  %d operations (%d decals made, %d dropped, %d growth steps): grid, '
          'free list, blocks, records, growing slots, total, bit for bit%s'
          % ('PASS' if ok else 'FAIL', cases, ops, made, dropped, grown, '' if ok else '  [%d mismatches]' % fails))
    if not ok and OPTIONS['verbose']:
        for line in ex[:3]:
            print('        ' + line)
    print('1 properties, %d failed, %.0f s' % (0 if ok else 1, time.time() - t0))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
