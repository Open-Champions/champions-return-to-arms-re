#!/usr/bin/env python3
"""difftest_leveldraw.py - compare tools/ref_leveldraw.py with the original code.

Needs your own SLUS_209.73 (US v2.00). Without it the script says so and exits 0.
No disc file is read. The automap property also runs the drawer's VU1 microcode
through tools/vu1_emu.py.

  python3 tools/difftest_leveldraw.py [SLUS_209.73]
"""
import hashlib
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# tools/ goes to the END of the path: tools/dis.py must not shadow the standard library's dis
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
from ee_emu import EE                          # noqa: E402
import ref_leveldraw as R                       # noqa: E402
import vu1_emu as V                             # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(_HERE)
FAILS = 0


def f32(bits):
    return struct.unpack('<f', struct.pack('<I', bits & 0xFFFFFFFF))[0]


def find_elf(argv):
    if len(argv) > 1:
        return argv[1]
    for path in (os.path.join(ROOT, 'local', 'SLUS_209.73'),
                 os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'SLUS_209.73')):
        if os.path.isfile(path):
            return path
    return None


def report(name, ok, detail):
    global FAILS
    if not ok:
        FAILS += 1
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, detail))


def chunk_setup(emu, flags, camera, frame=0, options=0, cos=32767, sin=0, quarter=None):
    dl = emu.alloc(0x4000)
    emu.mem.w32(0x44FE10, dl)
    emu.mem.w32(0x44FE0C, dl)
    emu.mem.w32(0x44FDA4, 0x100000)
    emu.mem.w32(0x44FE08, options)
    emu.mem.w32(0x44FDCC, frame)
    emu.mem.w8(0x41C182, 0)
    emu.mem.w8(0x41C1B8 + 1, 0)
    blob = emu.alloc(0x80)
    emu.mem.w32(0x425DF8, blob)
    emu.mem.w32(blob + 0x14, 1)
    emu.mem.w16(blob + 8, 0x010C)
    for i, value in enumerate(camera):
        emu.mem.wf32(0x44F110 + 4 * i, float(value))
    for i, value in enumerate((1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)):
        emu.mem.wf32(0x44F180 + 4 * i, float(value))
    # Markers. A geometry chunk must not copy either ZBUF constant into its packet.
    emu.mem.w32(0x44FD58, 0x11111111)
    emu.mem.w32(0x44FD5C, 0x22222222)
    emu.mem.w32(0x44FD60, 0x33333333)
    emu.mem.w32(0x44FD64, 0x44444444)
    chunk = emu.alloc(0x40)
    emu.mem.w32(chunk, emu.alloc(16))
    emu.mem.w32(chunk + 4, 1)
    emu.mem.w32(chunk + 0x24, flags)
    emu.mem.w32(chunk + 0x28, 16)
    emu.mem.w32(chunk + 0x2C, 32)
    emu.mem.w32(chunk + 0x30, 48)
    emu.mem.w16(chunk + 0x34, 1)
    if quarter is None:
        emu.mem.w16(chunk + 0x36, cos)
        emu.mem.w16(chunk + 0x38, sin)
    else:
        emu.mem.w16(chunk + 0x36, quarter)
        emu.mem.w16(chunk + 0x38, 0)
    lights = []
    emu.stub(0x149AB8, function=lambda e: lights.append(e.r[5] & 0xFFFFFFFF) or 0)
    emu.stub(0x149B90, function=lambda e: lights.append('dyn') or 0)
    queued = []
    emu.stub(0x16B7F0, function=lambda e: queued.append(e.r[5] & 0xFFFFFFFF) or 0)
    emu.stub(0x1EBDF8, 0)
    emu.call(0x1887B8, 0, chunk)
    end = emu.mem.u32(0x44FE10)
    words = struct.unpack('<%dI' % ((end - dl) // 4), emu.mem.read(dl, end - dl))
    regs = {}
    for i in range(len(words) - 3):
        if words[i + 1] == 0 and words[i + 3] == 0 and words[i + 2] in (0x42, 0x43, 0x47, 0x4E):
            regs[words[i + 2]] = words[i]
    rows = None
    for i, word in enumerate(words):
        if word == 0x14000016:
            rows = tuple(f32(words[i - 24 + k]) for k in range(24))
    strow = None
    for i, word in enumerate(words):
        if word == 0x30000000:
            strow = words[i + 1:i + 5]
    light = lights[0]
    if isinstance(light, int) and light >= 0x80000000:
        light -= 0x100000000
    return {
        'regs': regs, 'rows': rows, 'strow': strow, 'layer': queued[0],
        'light': light, 'flags': emu.mem.u32(chunk + 0x24), 'words': words,
    }


def check_chunks(elf):
    camera = [float(i + 1) for i in range(9)]
    cases = (0, 0x10, 0x200, 0x400, 0x600, 0x10000, 0x410, 0x100, 0x110,
             0x2000, 0x2200, 0x2100, 0x11)
    bad = 0
    for flags in cases:
        quarter = (flags & 7) if flags & 1 else None
        got = chunk_setup(EE(elf), flags, camera, quarter=quarter)
        gs = R.chunk_gs(flags)
        kind, value, after = R.chunk_light(flags)
        if got['regs'].get(0x42) != gs['alpha1']:
            bad += 1
        if gs['alpha2'] is None and 0x43 in got['regs']:
            bad += 1
        if gs['alpha2'] is not None and got['regs'].get(0x43) != gs['alpha2']:
            bad += 1
        if got['regs'].get(0x47) != gs['test'] or got['layer'] != gs['layer']:
            bad += 1
        if 0x4E in got['regs']:
            bad += 1
        if got['flags'] != after:
            bad += 1
        if kind == 'dynamic':
            if got['light'] != 'dyn':
                bad += 1
        elif got['light'] != value:
            bad += 1
        if got['strow'] != (16, 32, 48, 0):
            bad += 1
    report('chunk-gs', bad == 0, '%d flag combinations, 0 mismatches' % len(cases) if bad == 0
           else '%d mismatches' % bad)

    # Environment rows: free rotation must not change them; quarter codes and scroll must.
    bad = 0
    samples = []
    samples.append((0x10, camera, 0, 0, 32767, 0, None))
    samples.append((0x10, camera, 0, 0, 0, 32767, None))
    for code in range(8):
        samples.append((0x11, camera, 0, 0, 0, 0, code))
    for frame, opt in ((100, 0), (100, 4), (0x400, 4), (0x3FF, 4), (50, 5)):
        samples.append((0x10, [0.0] * 9, frame, opt, 32767, 0, None))
    for flags, cam, frame, opt, cos, sin, quarter in samples:
        got = chunk_setup(EE(elf), flags, cam, frame, opt, cos, sin, quarter)
        axis = R.axis_xy(cam)
        row4, row5 = R.env_rows(axis, frame, opt, quarter=quarter)
        expect = row4 + row5
        have = got['rows'][16:24]
        for a, b in zip(expect, have):
            if struct.pack('<f', a) != struct.pack('<f', b):
                bad += 1
    report('env-rows', bad == 0, '%d row components' % (len(samples) * 8))


def check_order(elf):
    emu = EE(elf)
    emu.mem.w32(0x41B4D4, 0)
    emu.mem.w32(0x6F4068, 8)
    emu.mem.w32(0x44FDD0, 7)
    emu.mem.w32(0x41C190, 100)
    for layer in range(8):
        entry = 0x6E4068 + layer * 16
        emu.mem.w32(entry + 0x0C, 0)
        emu.mem.w32(0x6F4070 + layer * 4, entry)
    textures = []
    for _ in range(4):
        tex = emu.alloc(0x40)
        emu.mem.w16(tex + 4, 1)
        textures.append(tex)
    packets = [emu.alloc(16) for _ in range(8)]
    items = [
        (0, textures[0], 0, packets[0]),
        (0, textures[1], 0, packets[1]),
        (0, textures[0], 0, packets[2]),
        (0, textures[2], 1, packets[3]),
        (4, textures[0], 0, packets[4]),
        (0, 0, 0, packets[5]),
    ]
    returned = []
    for layer, tex, flags, pkt in items:
        returned.append(emu.call(0x16B7F0, pkt, layer, tex, 0, flags) & 0xFFFFFFFF)

    def walk(layer):
        head = emu.mem.u32(0x6F4070 + layer * 4)
        out, ptr, guard = [], emu.mem.u32(head + 0x0C), 0
        while ptr and guard < 20:
            out.append(emu.mem.u32(ptr) & 0x0FFFFFFF)
            ptr = emu.mem.u32(ptr + 0x0C)
            guard += 1
        return out

    model_items = []
    for layer, tex, flags, pkt in items:
        model_items.append((layer, tex or None, flags, pkt & 0x0FFFFFFF))
    expect = R.sorted_draw_order(model_items)
    ok = walk(0) == expect[0] and walk(4) == expect[4] and walk(1) == []
    # A parent chains behind the entry the previous call returned, and stays out of
    # the layer head. The child is reached by walking from that entry.
    parent = returned[0]
    child = emu.call(0x16B7F0, packets[6], 0, textures[0], parent, 0) & 0xFFFFFFFF
    ok = ok and emu.mem.u32(parent + 0x0C) == child
    report('sort-order', ok, 'texture groups, flag 1, empty texture, layer 4, one parent link')


def automap_vertices(elf, code_of):
    emu = EE(elf)
    emu.mem.map(0x10000000, 16)
    dl = emu.alloc(0x40000)
    emu.mem.w32(0x44FE10, dl)
    emu.mem.w32(0x44FE0C, dl)
    emu.mem.w32(0x44FDA4, 0x800000)
    emu.mem.w32(0x4044DC, 40)
    emu.mem.w32(0x4044E0, 40)
    emu.mem.w32(0x44FD60, 0xA1B2C3D4)
    emu.mem.w32(0x44FD64, 0x01000000)
    tex = emu.alloc(0x40)
    emu.mem.w16(tex, 210)
    emu.mem.w16(tex + 2, 160)
    world = emu.alloc(0x90)
    emu.mem.w32(world + 0x6C, tex)
    pos = emu.alloc(8)
    emu.mem.wf32(pos, 1000.0)
    emu.mem.wf32(pos + 4, 2000.0)
    for y in range(216):
        for x in range(216):
            emu.mem.w16(0x4044F0 + (y * 216 + x) * 2, code_of(x, y) & 0xFFFF)
    spans = []

    def on_copy(e):
        dst, src, n = e.r[4] & 0xFFFFFFFF, e.r[5] & 0xFFFFFFFF, e.r[6] & 0xFFFFFFFF
        data = e.mem.read(src, n)
        spans.append((src - 0x4044F0, data))
        for i, byte in enumerate(data):
            e.mem.w8(dst + i, byte)
        return dst

    layers = []
    emu.stub(0x3B5F0C, function=on_copy)
    emu.stub(0x16B7F0, function=lambda e: layers.append(e.r[5] & 0xFFFFFFFF) or 0)
    emu.stub(0x16A82C, -1)
    emu.call(0x168CAC, world, pos, 0x16A82C, 0,
             fargs=(1000.0, 2000.0, 1.0, 3.0, 10.0, 10.0, 0.0))
    end = emu.mem.u32(0x44FE10)
    data = emu.mem.read(dl, end - dl)
    second = None
    for off in range(16, end - dl, 16):
        word = struct.unpack_from('<I', data, off)[0]
        if (word >> 28) == 1 and (word & 0xFFFF) < 0x80:
            second = dl + off
            break
    gs = V.GifReader()
    vif = V.Vif1(V.Vu1(), kick=gs.path1, direct=gs.path2)
    vif.feed(V.dma_chain_words(lambda a, n: emu.mem.read(a, n), second))
    return spans, gs, layers


def check_automap(elf):
    def code(x, y):
        # Distinct column, orientation, row and explored level inside the bits.
        return ((0xA + (x & 3)) << 12) | ((y & 0xF) << 8) | (((x + y) & 7) << 5) | (x & 0x1F)

    spans, gs, layers = automap_vertices(elf, code)
    rows = []
    for off, data in spans:
        row, col = divmod(off // 2, 216)
        words = struct.unpack('<%dH' % (len(data) // 2), data)
        rows.append((row, col, words))
    ok = len(rows) >= 2 and len({r[1] for r in rows}) == 1
    width = len(rows[0][2]) if ok else 0
    ok = ok and all(len(words) == width for _, _, words in rows)
    expect = []
    if ok:
        origin_col = rows[0][1]
        for j in range(len(rows) - 1):
            for i in range(width - 1):
                quad = R.automap_quad(rows[j][2][i], rows[j + 1][2][i],
                                      rows[j][2][i + 1], rows[j + 1][2][i + 1])
                expect.extend(quad)
    have = [(v.uv[0], v.uv[1], v.rgba[3]) for v in gs.vertices]
    zbuf = [value for addr, value in gs.raw if addr == 0x4E]
    regs = {addr: value for addr, value in gs.raw}
    ok = (ok and have == expect and layers == [5, 5]
          and regs.get(0x42) == R.ALPHA_USUAL and regs.get(0x47) == R.TEST_AUTOMAP
          and regs.get(0x14) == 1 and zbuf == [0x01000000A1B2C3D4])
    report('automap-tiles', ok, '%d vertices, bottom-right tile, per-corner alpha' % len(have))


def main(argv):
    path = find_elf(argv)
    if path is None:
        print('SKIP  difftest_leveldraw  no SLUS_209.73 found')
        return 0
    digest = hashlib.sha256(open(path, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('FAIL  elf  sha256 %s is not US v2.00' % digest)
        return 1
    check_chunks(path)
    check_order(path)
    check_automap(path)
    print('%d failed' % FAILS)
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
