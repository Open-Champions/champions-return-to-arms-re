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
                 os.path.expanduser('~/champions-re/SLUS_209.73')):
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
    print('%d failed' % FAILS)
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
