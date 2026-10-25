#!/usr/bin/env python3
"""difftest_waterdraw.py - compare tools/ref_waterdraw.py with the original code.

Needs your own SLUS_209.73 (US v2.00). Without it the script says so and exits 0.
No disc file is read. The vertex property also runs the water VU1 microcode.

  python3 tools/difftest_waterdraw.py [SLUS_209.73]
"""
import hashlib
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# tools/ goes to the END of the path: tools/dis.py must not shadow the standard library's dis
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
from ee_emu import EE                          # noqa: E402
import ref_waterdraw as R                       # noqa: E402
import vu1_emu as V                             # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(_HERE)
FAILS = 0


def report(name, ok, detail):
    global FAILS
    if not ok:
        FAILS += 1
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, detail))


def find_elf(argv):
    if len(argv) > 1:
        return argv[1]
    for path in (os.path.join(ROOT, 'local', 'SLUS_209.73'),
                 os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'SLUS_209.73')):
        if os.path.isfile(path):
            return path
    return None


def new_emu(elf):
    emu = EE(elf)
    emu.mem.map(0x70000000, 0x4000)
    emu.stub(0x1EBDF8, 0)
    return emu


def pool(emu, count=2):
    emu.mem.w32(0x44F058, count)
    base = emu.alloc(0x12B0 * (count + 1))
    emu.mem.w32(0x44F060, base)
    emu.call(0x186BAC)
    return base


def write_grid(emu, block, heights, disturb, gap):
    for row, samples in enumerate(heights):
        for col, value in enumerate(samples):
            emu.mem.w16(block + row * 0x50 + col * 2, value & 0xFFFF)
    for col, value in enumerate(gap):
        emu.mem.w16(block + 0xA50 + col * 2, value & 0xFFFF)
    for row, samples in enumerate(disturb):
        for col, value in enumerate(samples):
            emu.mem.w16(block + 0xA90 + row * 64 + col * 2, value & 0xFFFF)


def read_grid(emu, block):
    heights = [list(struct.unpack('<32h', emu.mem.read(block + row * 0x50, 64)))
               for row in range(33)]
    disturb = [list(struct.unpack('<32h', emu.mem.read(block + 0xA90 + row * 64, 64)))
               for row in range(32)]
    gap = list(struct.unpack('<32h', emu.mem.read(block + 0xA50, 64)))
    return heights, disturb, gap


def link(emu, block, world, chunk, payload, stamp=0):
    emu.mem.w32(chunk, payload)
    emu.mem.w32(payload + 8, block)
    emu.mem.w32(block + 0x1290, world)
    emu.mem.w32(block + 0x12A0, chunk)
    emu.mem.w32(block + 0x1294, stamp)
    for i in range(4):
        emu.mem.w16(payload + 2 * i, 0xFFFF)


def gs_regs(words):
    regs = {}
    for i, word in enumerate(words):
        if word in (0x01, 0x06, 0x14, 0x3F, 0x42, 0x47) and i >= 2 and words[i + 1] == 0:
            regs[word] = (words[i - 2], words[i - 1])
    return regs


def matrix_of(words):
    for i, word in enumerate(words):
        if word == 0x6C054000:
            rows = [words[i + 1 + r * 4:i + 5 + r * 4] for r in range(4)]
            tag = words[i + 17:i + 21]
            return rows, tag
    return None, None


def prepare_draw(emu, flags=0, options=0):
    tex = 0xABC0
    emu.call(0x1875D4, tex)
    base = pool(emu)
    world = emu.alloc(0x80)
    chunk = emu.alloc(0x40)
    payload = emu.alloc(0x90)
    link(emu, base, world, chunk, payload, 0)
    emu.mem.w32(chunk + 0x24, flags)
    for off, value in ((8, 0.4), (0x0C, -1.2), (0x10, 0.0),
                       (0x14, 120.6), (0x18, 10.0), (0x1C, 0.0)):
        emu.mem.wf32(chunk + off, value)
    emu.mem.w32(chunk + 0x30, 8)
    view = (2, 0, 0, 0, 0, 3, 0, 0, 0, 0, 4, 0, 5, 6, 7, 8)
    for i, value in enumerate(view):
        emu.mem.wf32(0x44F1C0 + 4 * i, float(value))
    dl = emu.alloc(0x400)
    emu.mem.w32(0x44FE10, dl)
    emu.mem.w32(0x44FE08, options)
    queued = []
    emu.stub(0x16B7F0, function=lambda e: queued.append((
        e.r[5] & 0xFFFFFFFF, e.r[6] & 0xFFFFFFFF,
        e.r[7] & 0xFFFFFFFF, e.r[8] & 0xFFFFFFFF)) or 0)
    return world, chunk, dl, queued, tex


def draw_words(emu, world, chunk, dl, clip=0):
    emu.mem.w32(0x44FE10, dl)
    emu.call(0x1876E0, world, chunk, clip)
    end = emu.mem.u32(0x44FE10)
    return struct.unpack('<%dI' % ((end - dl) // 4), emu.mem.read(dl, end - dl))


def check_setup(elf):
    emu = new_emu(elf)
    before = emu.mem.u32(0x44F078), emu.mem.u32(0x44F080), emu.mem.u32(0x44F088)
    emu.call(0x1875D4, 0x1111)
    got = (emu.mem.u32(0x44F074), emu.mem.u32(0x44F07C), emu.mem.u32(0x44F084),
           emu.mem.u32(0x44F064), emu.mem.u32(0x44F068), emu.mem.u32(0x44F06C),
           emu.mem.u32(0x44F10C))
    expect = (R.SET0_FIX, R.SET0_COLOUR, R.SET0_SCALE,
              struct.unpack('<I', struct.pack('<f', R.WAVE_STRENGTH))[0],
              struct.unpack('<I', struct.pack('<f', R.WAVE_RADIUS))[0],
              4, 0x1111)
    same = (emu.mem.u32(0x44F078), emu.mem.u32(0x44F080), emu.mem.u32(0x44F088)) == before
    report('setup-constants', got == expect and same and before[0] == R.SET1_FIX,
           'set 0 written, set 1 left as it was')


def check_mask_fill(elf):
    emu = new_emu(elf)
    world = emu.alloc(0x80)
    array = emu.alloc(0x3C * 2)
    payload = emu.alloc(0x90)
    emu.mem.w32(0x44FDC8, world)
    emu.mem.w32(world, 2)
    emu.mem.w32(world + 0x24, array)
    emu.mem.w32(array, payload)
    emu.mem.w32(array + 0x24, 0x80)
    emu.mem.w32(array + 0x3C + 0x24, 0)
    emu.mem.w32(0x44FE08, 0x8)
    emu.call(0x1875D4, 0x2222)
    filled = emu.mem.read(payload + 0x10, 128) == bytes([0xFF]) * 128
    spared = emu.mem.u32(array + 0x3C) == 0
    report('mask-fill', filled and spared, 'option bit 8 fills water masks only')


def check_packet(elf):
    emu = new_emu(elf)
    world, chunk, dl, queued, tex = prepare_draw(emu, 0)
    emu.mem.w32(0x44FDCC, 3)
    words = draw_words(emu, world, chunk, dl, 0)
    regs = gs_regs(words)
    rows, tag = matrix_of(words)
    state = R.gs_state(0)
    ox, oy, oz = R.origin(0.4, -1.2, 8)
    expect = R.upload_matrix(
        [(2, 0, 0, 0), (0, 3, 0, 0), (0, 0, 4, 0), (5, 6, 7, 8)],
        (ox, oy, oz), state['scale'])
    parts = {
        'alpha': regs.get(0x42) == (state['alpha_low'], state['alpha_high']),
        'test': regs.get(0x47) == (state['test'], 0),
        'tex1': regs.get(0x14) == (state['tex1'], 0),
        'colour': regs.get(0x01) == (state['colour'], 0),
        'tex0': regs.get(0x06) == (0, 0),
        'queue': queued == [(3, tex, 0, 0)],
        'rows': [tuple(row) for row in rows] == [tuple(row) for row in expect],
        'step': tag is not None and tag[3] == R.tile_step_bits(0.4, 120.6),
        'tag': tag is not None and tag[0] == 0x803E and tag[1] == 0x20AE4000,
    }
    ok = all(parts.values())
    report('packet-set0', ok, 'blend, test, colour, layer 3, matrix, step')

    emu.mem.w32(0x44FDCC, 9)
    again = draw_words(emu, world, chunk, dl, 0)
    report('no-scroll', matrix_of(words) == matrix_of(again),
           'frame 9 uploads the same matrix and step as frame 3')

    emu.mem.w32(chunk + 0x24, 0x1000)
    emu.mem.w32(0x44FDCC, 3)
    queued.clear()
    words1 = draw_words(emu, world, chunk, dl, 1)
    regs1 = gs_regs(words1)
    rows1, tag1 = matrix_of(words1)
    other = R.gs_state(1)
    expect1 = R.upload_matrix(
        [(2, 0, 0, 0), (0, 3, 0, 0), (0, 0, 4, 0), (5, 6, 7, 8)],
        (ox, oy, oz), other['scale'])
    ok = (regs1.get(0x42) == (other['alpha_low'], other['alpha_high'])
          and regs1.get(0x01) == (other['colour'], 0)
          and [tuple(row) for row in rows1] == [tuple(row) for row in expect1]
          and tag1[3] == tag[3] and queued == [(3, tex, 0, 0)])
    report('packet-set1', ok, 'flag 0x1000 selects the second fix, colour and scale')

    emu.mem.w32(chunk + 0x24, 0)
    emu.mem.w32(0x44F074, 0xFFFFFF9C)
    queued.clear()
    neg = gs_regs(draw_words(emu, world, chunk, dl, 0))
    report('negative-fix', neg.get(0x42) == (0x68, 100), 'FIX -100 becomes additive 100')


def check_layer(elf):
    emu = new_emu(elf)
    world, chunk, dl, queued, tex = prepare_draw(emu, 0x280)
    emu.call(0x1887B8, world, chunk)
    report('flag-0x200', queued == [(3, tex, 0, 0)],
           'a water chunk with flag 0x200 is still one layer-3 packet')


def check_step(elf):
    emu = new_emu(elf)
    block = emu.alloc(0x12B0)
    payload = emu.alloc(0x90)
    heights = [[0] * 32 for _ in range(33)]
    disturb = [[0] * 32 for _ in range(32)]
    gap = [0] * 32
    disturb[4][5] = 1000
    heights[0][3] = 500
    gap[3] = 40
    mask = bytearray(128)
    struct.pack_into('<H', mask, 5 * 2, 1 << (15 - 5))
    struct.pack_into('<H', mask, 3 * 2, 0xFFFF)
    write_grid(emu, block, heights, disturb, gap)
    emu.mem.write(payload + 0x10, bytes(mask))
    emu.call(0x196088, block + 0x50, block + 0xA90, payload + 0x10)
    got = read_grid(emu, block)
    expect = R.step_grid(heights, disturb, gap, bytes(mask))
    report('height-step', got == expect, 'spike, mask bit and the spare row')


def check_life(elf):
    emu = new_emu(elf)
    base = pool(emu)
    world = emu.alloc(0x40)
    chunk = emu.alloc(0x40)
    payload = emu.alloc(0x90)
    link(emu, base, world, chunk, payload, 0)
    emu.mem.write(payload + 0x10, bytes([0xFF]) * 128)
    emu.mem.w16(base + 0xA90 + 4 * 64 + 5 * 2, 1000)
    emu.mem.w32(0x44F200, 3)
    emu.mem.w32(0x44FDCC, 199)
    emu.call(0x186E38)
    kept = (emu.mem.u32(base + 0x12A0) == chunk
            and emu.mem.u32(payload + 8) == base
            and emu.mem.s16(base + 5 * 0x50 + 5 * 2) == 993)
    emu.mem.w32(base + 0x12A0, chunk)
    emu.mem.w32(payload + 8, base)
    emu.mem.w32(base + 0x1294, 0)
    emu.mem.w16(base + 5 * 0x50 + 5 * 2, 4321)
    emu.mem.w32(0x44FDCC, 200)
    emu.mem.w32(0x44F200, 3)
    emu.call(0x186E38)
    dropped = (emu.mem.u32(base + 0x12A0) == 0
               and emu.mem.u32(payload + 8) == 0
               and emu.mem.s16(base + 5 * 0x50 + 5 * 2) == 4321)
    report('lifetime', kept and dropped, '199 frames keeps the block, 200 drops it')


def _pattern():
    heights = [[80 + row * 3 + (col & 3) for col in range(32)] for row in range(33)]
    disturb = [[400 + row * 5 + col for col in range(32)] for row in range(32)]
    gap = [20 + col for col in range(32)]
    return heights, disturb, gap


def check_seams(elf):
    for name, slot in (('columns', 0), ('rows', 2)):
        emu = new_emu(elf)
        base = pool(emu)
        world = emu.alloc(0x80)
        array = emu.alloc(0x3C * 2)
        emu.mem.w32(world + 0x24, array)
        blocks = [base, base + 0x12B0]
        grids = []
        for i in range(2):
            heights, disturb, gap = _pattern()
            # Make the two tiles different so a swapped copy is visible.
            if i == 1:
                disturb = [[sample + 1000 for sample in row] for row in disturb]
                heights = [[sample + 500 for sample in row] for row in heights]
            grids.append((heights, disturb, gap))
            chunk = array + i * 0x3C
            payload = emu.alloc(0x90)
            link(emu, blocks[i], world, chunk, payload, 0)
            emu.mem.write(payload + 0x10, bytes([0xFF]) * 128)
            if i == 0:
                emu.mem.w16(payload + slot * 2, 1)
            write_grid(emu, blocks[i], heights, disturb, gap)
        emu.mem.w32(0x44F200, 4)
        emu.mem.w32(0x44FDCC, 0)
        emu.call(0x186E38)
        stepped = []
        for heights, disturb, gap in grids:
            field, velocity, spare = R.step_grid(heights, disturb, gap, bytes([0xFF]) * 128)
            stepped.append((field, velocity))
        if slot == 0:
            expect = R.seam_columns(stepped[0][0], stepped[0][1], stepped[1][0], stepped[1][1])
        else:
            expect = R.seam_rows(stepped[0][0], stepped[0][1], stepped[1][0], stepped[1][1])
        got = [read_grid(emu, block)[:2] for block in blocks]
        ok = got[0] == (expect[0], expect[1]) and got[1] == (expect[2], expect[3])
        report('seam-' + name, ok, 'post-step copy of the shared edge')


def _vu(elf, rows, matrix, step, clip=0):
    words = [0x04000000 | (clip & 0x3FF), 0x6C054000]
    data = []
    for row in matrix:
        data.extend(row)
    data.extend((0x0000803E, 0x20AE4000, 0x43, step))
    words.extend(data)
    words.append(0x14000036)
    for i, samples in enumerate(rows):
        addr = (0, 0x12C, 0x258)[i % 3]
        signed = []
        for value in samples:
            value = int(value)
            if value >= 0x8000:
                value -= 0x10000
            signed.append(value)
        blob = struct.pack('<32h', *signed)
        words.append(0x04000000 | addr)
        words.append(0x61000000 | (32 << 16) | addr)
        words.extend(struct.unpack('<16I', blob))
        words.append(0x14000038)
    emu = EE(elf)
    gs = V.GifReader()
    vif = V.Vif1(V.Vu1(), kick=gs.path1, direct=gs.path2)
    vif.feed(V.dma_chain_words(emu.mem.read, 0x3E5EC0))
    vif.feed(words)
    return gs


def _bits(rows):
    return [tuple(struct.unpack('<I', struct.pack('<f', float(v)))[0] for v in row) for row in rows]


def check_vu(elf):
    ident = _bits(((0, 1, 0, 0), (0, 0, 1, 0), (1, 0, 0, 0), (0, 0, 0, 1)))
    rows = [[0] * 32 for _ in range(6)]
    rows[2][2] = 160
    rows[3][4] = -80
    rows[4][1] = 40
    step = struct.unpack('<I', struct.pack('<f', 4.0))[0]
    strips = R.project_strips(rows, ident, step)
    gs = _vu(elf, rows, ident, step)
    got = [(v.x, v.y, v.uv[0], v.uv[1], v.adc) for v in gs.vertices]
    flat = [vert for strip in strips for vert in strip]
    report('vertices', got == flat and gs.vertices[0].z == 0,
           '%d vertices, slope UVs, flat depth field' % len(got))

    rows = [[0] * 32 for _ in range(4)]
    sticky = _bits(((0, 0, 0, 0), (0, 0, 0, 0), (0, 100, 0, 0), (0, -2000, 0, 1)))
    strips = R.project_strips(rows, sticky, step, clip=1)
    gs = _vu(elf, rows, sticky, step, clip=1)
    pred = [vert[4] for strip in strips for vert in strip]
    report('clip', [v.adc for v in gs.vertices] == pred,
           'outside ±1000, and the rest of that strip')


def _blank_heights(fill=0):
    return [[fill] * 32 for _ in range(33)]


def check_claim(elf):
    emu = new_emu(elf)
    world = emu.alloc(0x40)
    chunks = emu.alloc(0x3C * 5)
    emu.mem.w32(world + 0x24, chunks)
    payloads = [emu.alloc(0x90) for _ in range(5)]
    blocks = [emu.alloc(0x12B0) for _ in range(5)]
    for index in range(5):
        emu.mem.w32(chunks + index * 0x3C, payloads[index])
        emu.mem.w32(payloads[index] + 8, blocks[index])

    def arm(indices, grids):
        for slot in range(4):
            emu.mem.w16(payloads[0] + 2 * slot, 0xFFFF if indices[slot] < 0 else indices[slot])
        for index, grid in enumerate(grids, start=1):
            if grid is None:
                emu.mem.w32(payloads[index] + 8, 0)
                continue
            emu.mem.w32(payloads[index] + 8, blocks[index])
            write_grid(emu, blocks[index], grid, [[0] * 32 for _ in range(32)], [0] * 32)
        for col in range(32):
            emu.mem.w16(blocks[0] + col * 2, 0x1111)
        for row in range(32):
            for col in range(32):
                emu.mem.w16(blocks[0] + 0xA90 + row * 64 + col * 2, 0x2222)
        emu.call(0x187374, world, payloads[0])
        heights, disturb, _gap = read_grid(emu, blocks[0])
        return heights, disturb

    left = _blank_heights()
    left[1][31] = 1001
    left[1][0] = 7777
    got_h, got_d = arm((1, -1, -1, -1), (left, None, None, None))
    exp_h, exp_d = R.claim_grid((left, None, None, None))
    report('claim-one-edge', got_h[0] == [0x1111] * 32 and got_h[1:] == exp_h[1:] and got_d == exp_d,
           'column 31 fades across columns 0..9, row 0 stays')

    left = _blank_heights()
    right = _blank_heights()
    far = _blank_heights()
    near = _blank_heights()
    for row in range(1, 33):
        left[row][31] = 30000 if row == 1 else 1000 + row
        right[row][0] = -30000 if row == 2 else -50
        right[row][31] = 8888
    for col in range(32):
        far[32][col] = 2000 + col
        far[1][col] = 6666
        near[1][col] = 4000 - col
        near[32][col] = 5555
    slots = (left, right, far, near)
    got_h, got_d = arm((1, 2, 3, 4), slots)
    exp_h, exp_d = R.claim_grid(slots)
    report('claim-four-edges', got_h[1:] == exp_h[1:] and got_d == exp_d,
           'corners blend in slot order, and a lone edge is not normalised')

    got_h, got_d = arm((-1, -1, -1, -1), (None, None, None, None))
    absent = got_h[0] == [0x1111] * 32 and got_h[1:] == [[0] * 32 for _ in range(32)] and got_d == exp_d
    got_h, got_d = arm((1, -1, -1, -1), (None, None, None, None))
    null_block = got_h[1:] == [[0] * 32 for _ in range(32)] and got_d == exp_d
    report('claim-absent', absent and null_block, 'index -1 or a null simulation pointer writes zeros')


def check_splash(elf):
    hit = miss = None
    for seed in range(3000):
        new, splash = R.splash_seed(seed)
        if splash and hit is None:
            hit = seed
        if not splash and miss is None:
            miss = seed
        if hit is not None and miss is not None:
            break

    def disturb_args(seed, options, frozen=0):
        emu = new_emu(elf)
        emu.stub(0x1EBDF8, frozen)
        world, chunk, dl, queued, tex = prepare_draw(emu, 0, options)
        emu.stub(0x189514, 0)
        emu.stub(0x183820, 0)
        emu.stub(0x18F3F8, 0)
        emu.mem.w32(0x404460, seed)
        emu.mem.w32(0x44FDCC, 1)
        emu.calls.clear()
        draw_words(emu, world, chunk, dl, 0)
        return [c.fargs[:2] for c in emu.calls if c.target == 0x189514]

    quiet = disturb_args(hit, 0) == []
    skipped = disturb_args(miss, 0x10) == []
    frozen = disturb_args(hit, 0x10, frozen=1) == []
    strength = struct.unpack('<I', struct.pack('<f', R.SPLASH_STRENGTH))[0]
    radius = struct.unpack('<I', struct.pack('<f', R.SPLASH_RADIUS))[0]
    fired = disturb_args(hit, 0x10) == [(strength, radius)]
    report('splash-gate', quiet and skipped and frozen and fired,
           'option 0x10, not frozen, and the generator hits 0 mod 300')


def _raw_f(value):
    return struct.unpack('<I', struct.pack('<f', float(value)))[0]


def _cell_diff(got, expect):
    bad = [(r, c, got[r][c], expect[r][c])
           for r in range(32) for c in range(32) if got[r][c] != expect[r][c]]
    return '%d cells differ, first %s' % (len(bad), bad[:3])


def call_disturb(elf, grid, bounds, origin, pos, strength, radius, flags=0x80, linked=True, cut=0):
    emu = new_emu(elf)
    world = emu.alloc(0x80)
    node = emu.alloc(16)
    chunk = emu.alloc(0x40)
    payload = emu.alloc(0x90)
    block = emu.alloc(0x12B0)
    emu.mem.w32(world + 4, node)
    emu.mem.w32(world + 0x24, chunk)
    emu.mem.w16(node, 1)
    emu.mem.w16(node + 2, 0)
    emu.mem.w32(chunk, payload)
    emu.mem.w32(chunk + 0x24, flags)
    emu.mem.w32(payload + 8, block if linked else 0)
    for off, value in zip((8, 0x0C, 0x10, 0x14, 0x18, 0x1C), bounds):
        emu.mem.w32(chunk + off, _raw_f(value))
    for off, value in zip((0x28, 0x2C, 0x30), origin):
        emu.mem.w32(chunk + off, int(value) & 0xFFFFFFFF)
    write_grid(emu, block, [[0] * 32 for _ in range(33)], grid, [0] * 32)
    emu.mem.w8(0x44FCEC, cut)
    point = emu.alloc(12)
    for i, value in enumerate(pos):
        emu.mem.w32(point + 4 * i, _raw_f(value))
    ret = emu.call(0x189514, world, point, fargs=(float(strength), float(radius))) & 0xFFFFFFFF
    heights, disturb, gap = read_grid(emu, block)
    return emu, world, block, payload, ret, heights, disturb, gap


def check_disturb(elf):
    blank = [[0] * 32 for _ in range(32)]
    wide = (-60.0, -60.0, -60.0, 60.0, 60.0, 60.0)
    emu, world, block, payload, ret, heights, disturb, gap = call_disturb(
        elf, blank, wide, (0, 0, 32), (0.0, 0.0, 8.0), 1500.0, 6.0)
    expect = R.disturb_cells(blank, _raw_f(1500), _raw_f(6), (0, 0),
                             (_raw_f(-60), _raw_f(60)), (_raw_f(0), _raw_f(0)))
    report('disturb-cells', ret == 1 and disturb == expect and heights == [[0] * 32 for _ in range(33)],
           'centre 1500, rows and columns 15..17' if disturb == expect else _cell_diff(disturb, expect))

    centre = expect
    preset = [[-100] * 32 for _ in range(32)]
    preset[16][16] = 32000
    _emu, _w, _b, _p, ret, _h, disturb, _g = call_disturb(
        elf, preset, wide, (0, 0, 0), (0.0, 0.0, 8.0), 1500.0, 6.0)
    expect = R.disturb_cells(preset, _raw_f(1500), _raw_f(6), (0, 0),
                             (_raw_f(-60), _raw_f(60)), (_raw_f(0), _raw_f(0)))
    narrow_grid = blank
    _emu, _w, _b, _p, nret, _h, narrow, _g = call_disturb(
        elf, narrow_grid, (0.0, 0.0, -10.0, 24.0, 24.0, 10.0), (0, 0, 0),
        (12.0, 12.0, 0.0), 1500.0, 6.0)
    nexpect = R.disturb_cells(narrow_grid, _raw_f(1500), _raw_f(6), (0, 0),
                              (_raw_f(0), _raw_f(24)), (_raw_f(12), _raw_f(12)))
    offset = blank
    _emu, _w, _b, _p, oret, _h, shifted, _g = call_disturb(
        elf, offset, (0.0, 0.0, -10.0, 48.0, 48.0, 10.0), (96, 96, 0),
        (20.0, 24.0, 0.0), 1500.0, 5.0)
    oexpect = R.disturb_cells(offset, _raw_f(1500), _raw_f(5), (96, 96),
                              (_raw_f(0), _raw_f(48)), (_raw_f(20), _raw_f(24)))
    same = disturb == expect and narrow == nexpect and shifted == oexpect
    report('disturb-places', same and ret == 1 and nret == 1 and oret == 1,
           'clamp, a short tile, and an origin in quarter-units'
           if same else _cell_diff(narrow, nexpect) + ' / ' + _cell_diff(shifted, oexpect))

    _emu, _w, _b, _p, cret, _h, cut_grid, _g = call_disturb(
        elf, blank, wide, (0, 0, 0), (0.0, 0.0, 8.0), 1500.0, 6.0, cut=1)
    _emu, _w, _b, _p, fret, _h, flag_grid, _g = call_disturb(
        elf, blank, wide, (0, 0, 0), (0.0, 0.0, 8.0), 1500.0, 6.0, flags=0)
    _emu, _w, _b, _p, zret, _h, bare_grid, _g = call_disturb(
        elf, blank, wide, (0, 0, 0), (0.0, 0.0, 8.0), 1500.0, 6.0, linked=False)
    report('disturb-gates', cret == 0 and cut_grid == blank and fret == 0 and flag_grid == blank
           and zret == 1 and bare_grid == blank,
           'cut byte, flag 0x80 clear, or a missing simulation block')

    mask = bytes([0xFF]) * 128
    emu.mem.write(payload + 0x10, mask)
    emu.call(0x196088, block + 0x50, block + 0xA90, payload + 0x10)
    stepped, stepped_d, stepped_g = read_grid(emu, block)
    exp_h, exp_d, exp_g = R.step_grid([[0] * 32 for _ in range(33)], centre, [0] * 32, mask)
    report('disturb-step', (stepped, stepped_d, stepped_g) == (exp_h, exp_d, exp_g),
           'velocity row r is height row r+1 on the next step')

    ident = _bits(((0, 1, 0, 0), (0, 0, 1, 0), (1, 0, 0, 0), (0, 0, 0, 1)))
    step = _raw_f(4.0)
    rows = stepped[1:]
    strips = R.project_strips(rows, ident, step)
    gs = _vu(elf, rows, ident, step)
    got = [(v.x, v.y, v.uv[0], v.uv[1], v.adc) for v in gs.vertices]
    flat_strips = R.project_strips([[0] * 32 for _ in range(len(rows))], ident, step)
    kicked = [vert for strip in strips for vert in strip]
    flat = [vert for strip in flat_strips for vert in strip]
    report('disturb-draw', got == kicked and got != flat,
           '%d kicked vertices, different from a flat tile' % len(got))


def check_splash_point(elf):
    bounds = [struct.unpack('<I', struct.pack('<f', v))[0]
              for v in (0.4, -1.2, 3.5, 120.6, 10.0, 40.0)]
    seed, point = R.splash_point(324, bounds)
    terrain = 0x42F70000

    def run(start, options, frozen, plant):
        emu = new_emu(elf)
        emu.stub(0x1EBDF8, frozen)
        world, chunk, dl, queued, tex = prepare_draw(emu, 0, options)
        for off, bits in zip((8, 0x0C, 0x10, 0x14, 0x18, 0x1C), bounds):
            emu.mem.w32(chunk + off, bits)
        seen = []

        def disturb(e):
            ptr = e.r[5] & 0xFFFFFFFF
            seen.append(('disturb', e.r[4] & 0xFFFFFFFF,
                         tuple(e.mem.u32(ptr + 4 * i) for i in range(3)),
                         e.f[12], e.f[13]))
            return 0

        def height(e):
            ptr = e.r[5] & 0xFFFFFFFF
            seen.append(('terrain', e.r[4] & 0xFFFFFFFF, e.mem.u32(ptr + 8), e.f[12]))
            if plant:
                e.f[0] = terrain
            return 0

        def spawn(e):
            pos = e.r[5] & 0xFFFFFFFF
            extra = e.r[6] & 0xFFFFFFFF
            seen.append(('spawn', e.r[4] & 0xFFFFFFFF,
                         tuple(e.mem.u32(pos + 4 * i) for i in range(3)),
                         e.f[12], tuple(e.mem.u32(extra + 4 * i) for i in range(3))))
            return 0

        emu.stub(0x189514, function=disturb)
        emu.stub(0x183820, function=height)
        emu.stub(0x18F3F8, function=spawn)
        emu.mem.w32(0x404460, start)
        emu.mem.w32(0x44FDCC, 1)
        draw_words(emu, world, chunk, dl, 0)
        return emu.mem.u32(0x404460), seen

    got_seed, seen = run(324, 0x10, 0, True)
    strength = struct.unpack('<I', struct.pack('<f', R.SPLASH_STRENGTH))[0]
    radius = struct.unpack('<I', struct.pack('<f', R.SPLASH_RADIUS))[0]
    world_ok = len(seen) == 4 and seen[0][1] != 0 and seen[0][1] == seen[1][1]
    hit = (got_seed == seed and world_ok
           and seen[0][2:] == (point, strength, radius)
           and seen[1][2:] == (point[2], radius)
           and seen[2][1:] == (R.PARTICLE_FIRST, (point[0], point[1], terrain), 0, (0, 0, 0))
           and seen[3][1:] == (R.PARTICLE_SECOND,
                               (point[0], point[1], R.second_particle_z(terrain, seed)),
                               0, (0, 0, 0)))
    missed_seed, missed = run(325, 0x10, 0, False)
    quiet_seed, quiet = run(324, 0, 0, False)
    frozen_seed, frozen = run(324, 0x10, 1, False)
    report('splash-point', hit and missed == [] and missed_seed == R.splash_seed(325)[0]
           and quiet == [] and quiet_seed == 324 and frozen == [] and frozen_seed == 324,
           'shared unit interval, z at the minimum, then terrain and the second lift'
           if hit else repr(seen))


def _cstr(emu, addr):
    chars = []
    while True:
        byte = emu.mem.u8(addr)
        if byte == 0 or len(chars) == 80:
            break
        chars.append(chr(byte))
        addr += 1
    return ''.join(chars)


def _lines(emu, texts):
    ptrs = emu.alloc(4 * (len(texts) + 1))
    for index, text in enumerate(texts):
        buf = emu.alloc(len(text) + 1)
        emu.mem.write(buf, text.encode('ascii') + b'\0')
        emu.mem.w32(ptrs + 4 * index, buf)
    emu.mem.w32(ptrs + 4 * len(texts), 0)
    return ptrs


def _globals(emu):
    names = {
        'fix0': 0x44F074, 'fix1': 0x44F078, 'col0': 0x44F07C, 'col1': 0x44F080,
        'scale0': 0x44F084, 'scale1': 0x44F088, 'strength': 0x44F064,
        'radius': 0x44F068, 'timer': 0x44F06C, 'texture': 0x44F10C,
    }
    return {name: emu.mem.u32(addr) for name, addr in names.items()}


def check_level(elf):
    emu = new_emu(elf)
    emu.mem.map(0x7D5000, 0x2000)
    world = emu.alloc(0x80)
    emu.call(0x18B270, world)
    reset = _globals(emu)
    reset_ok = (reset['scale0'] == R.SET1_SCALE and reset['strength'] == _raw_f(R.WAVE_STRENGTH)
                and reset['radius'] == _raw_f(4.0) and reset['timer'] == 6
                and reset['fix0'] == R.SET1_FIX and reset['col0'] == R.SET1_COLOUR
                and reset['scale1'] == 0 and reset['fix1'] == 0 and reset['col1'] == 0)
    emu.call(0x1875D4, 0x2222)
    setup = _globals(emu)
    setup_ok = (setup['fix0'] == R.SET0_FIX and setup['col0'] == R.SET0_COLOUR
                and setup['scale0'] == R.SET0_SCALE and setup['strength'] == _raw_f(R.WAVE_STRENGTH)
                and setup['radius'] == _raw_f(R.WAVE_RADIUS) and setup['timer'] == 4
                and setup['texture'] == 0x2222
                and setup['scale1'] == 0 and setup['fix1'] == 0 and setup['col1'] == 0)
    report('load-reset', reset_ok and setup_ok,
           'reset zeros set 1, then setup replaces set 0 only')

    emu = new_emu(elf)
    for addr in (0x44F064, 0x44F068, 0x44F06C, 0x44F074, 0x44F078, 0x44F07C, 0x44F080, 0x44F084, 0x44F088):
        emu.mem.w32(addr, 0x11111111)
    emu.call(0x22E714, _lines(emu, ['waterColor2=1,2,3,4', 'waterColor=10,20,30,40']))
    colour = _globals(emu)
    colour_ok = (colour['col1'] == R.colour_word(1, 2, 3) and colour['fix1'] == 4
                 and colour['col0'] == R.colour_word(10, 20, 30) and colour['fix0'] == 40
                 and colour['scale0'] == 0x11111111 and colour['scale1'] == 0x11111111)
    emu.call(0x22E714, _lines(emu, ['waterBumpTimer=7']))
    timer_ok = emu.mem.u32(0x44F06C) == 7 and emu.mem.u32(0x44F064) == 0x11111111
    report('level-colour', colour_ok and timer_ok,
           'three colour bytes, the fourth integer is the fix, timer 7')

    emu = new_emu(elf)
    for addr in (0x44F064, 0x44F068, 0x44F084, 0x44F088):
        emu.mem.w32(addr, 0x11111111)
    seen = []

    def deposit(entry):
        text = _cstr(entry, entry.r[4] & 0xFFFFFFFF)
        dest = entry.r[6] & 0xFFFFFFFF
        bits = struct.unpack('<I', struct.pack('<f', float(text.split('=', 1)[1])))[0]
        seen.append((dest, bits))
        entry.mem.w32(dest, bits)
        return 1

    emu.stub(0x3B7F88, function=deposit)
    emu.call(0x22E714, _lines(emu, ['waterWavyness2=0.5', 'waterWavyness=1',
                                   'waterBumpAmount=12.5', 'waterBumpRadius=3']))
    got = _globals(emu)
    half = struct.unpack('<I', struct.pack('<f', 0.5))[0]
    one = struct.unpack('<I', struct.pack('<f', 1.0))[0]
    amount = struct.unpack('<I', struct.pack('<f', 12.5))[0]
    radius = struct.unpack('<I', struct.pack('<f', 3.0))[0]
    wave_ok = (got['scale1'] == R.wavyness_scale(half) and got['scale0'] == R.wavyness_scale(one)
               and got['strength'] == amount and got['radius'] == radius
               and seen == [(0x44F088, half), (0x44F084, one), (0x44F064, amount), (0x44F068, radius)])
    report('level-wave', wave_ok,
           'wavyness is scaled by 0x3cc00000; bump amount and radius are stored as parsed')


def main(argv):
    path = find_elf(argv)
    if path is None:
        print('SKIP  difftest_waterdraw  no SLUS_209.73 found')
        return 0
    digest = hashlib.sha256(open(path, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('FAIL  elf  sha256 %s is not US v2.00' % digest)
        return 1
    check_setup(path)
    check_mask_fill(path)
    check_packet(path)
    check_layer(path)
    check_step(path)
    check_life(path)
    check_seams(path)
    check_vu(path)
    check_claim(path)
    check_splash(path)
    check_splash_point(path)
    check_disturb(path)
    check_level(path)
    print('%d failed' % FAILS)
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
