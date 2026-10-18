#!/usr/bin/env python3
"""difftest_fx_render.py - compare tools/ref_fx_render.py with the game's own drawing code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_fx_render.py [path/to/SLUS_209.73] [--quick] [--seed N] [-k TEXT] [-v]

    --quick   a tenth of the cases
    --seed N  seed of the random choices (default 20973); one seed repeats exactly
    -k TEXT   run only the properties whose name contains TEXT
    -v        print up to three failing cases per property

Every property prints one line: PASS or FAIL, the name, the number of cases compared and
what was compared.  Exit status 1 when any property fails.

How a property is tested
    The ORIGINAL functions are executed by tools/ee_emu.py on memory this script prepares:
    the particle system is set up by the game's own static initialiser 0x195d30 and
    particle_init 0x18e648, definitions are made by particleDef_init, particles spawned by
    particle_spawn (also inside groups), ticks run by particle_updateTask, trails and beams
    made by their own functions, glows queued by glow_add.  Then the game's draw function
    runs (particle_draw 0x194888, which calls trail_drawAll and glow_draw), and the packets
    it hands to gfx_addSortedPacket are sent, as DMA would send them, through
    tools/vu1_emu.py: VIF1, the VU1 microprograms of YOUR executable (loaded by the game's
    own microcode packet at 0x3e5ec0) and the GIF.  What reaches the GS - every vertex
    (x, y, z, fog, ADC, colour, texture coordinates) and every register write - is compared
    with what the reference computes from the same inputs (definitions, particle records,
    camera, trail points as the original left them in memory).

    "Bit for bit" means: identical under the interpreters' floating-point models.  The EE
    side uses ee_emu's model (default 'ps2', repeated under 'chop'); the VU side uses
    vu1_emu's ('chop').  Neither was checked against a console.

    Which order the sorted packets are drawn in is not executed here: gfx_addSortedPacket
    is replaced by a recorder and the packets are sent in the order the code that walks
    the sorted list is Inferred to use (docs: last added first within a key for different
    textures), which matters because the trail program uses the matrix the particle packet
    leaves in VU1.
"""
import hashlib
import math
import os
import random
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, M32                                  # noqa: E402
import ref_core as C                                        # noqa: E402
import ref_fx_render as R                                   # noqa: E402
import vu1_emu as V                                         # noqa: E402
import ref_particles as P                                   # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False}
RESULTS = []
COVER = {}


def cover(what, n=1):
    if n:
        COVER[what] = COVER.get(what, 0) + n

# ---- addresses in SLUS_209.73 -----------------------------------------------------------
STATIC_INIT, RESREF_CTOR, PARTICLE_INIT, TASK_ADD = 0x195D30, 0x173768, 0x18E648, 0x19E4A0
DEF_INIT, SPAWN, UPDATE_TASK, DRAW = 0x18EE70, 0x18F3F8, 0x18F970, 0x194888
GROUP_CREATE, GROUP_BEGIN, GROUP_END, GROUP_SETMAT = 0x18E880, 0x18E958, 0x18E9A0, 0x18E9E8
ADD_SORTED, RESREF_GET, IS_FROZEN, LINE_DRAW, HAZE = 0x16B7F0, 0x17377C, 0x1EBDF8, 0x1934C0, 0x18FE18
TRAIL_CREATE, TRAIL_ADD, TRAIL_UPDATE, TRAIL_ADD_PAIR = 0x190FF8, 0x192550, 0x192840, 0x192650
G_TRAILS, G_TRAIL_ROW_V = 0x82CD00, 0x44FCA8
GLOW_ADD = 0x18FC78
VU_BOOT = 0x3E5EC0
G_DL_BASE, G_DL_CURSOR, G_DL_CAPACITY = 0x44FE0C, 0x44FE10, 0x44FDA4
G_PROJ_SCALE, G_ENABLED, G_PCLOCK = 0x44F108, 0x4039C0, 0x82CC90
G_LISTS, G_GROUPS, G_TYPE_TABLE, G_PAGES, G_PAGE_DESC = 0x44FA98, 0x7E1D50, 0x82C490, 0x7EC300, 0x82C300
G_SIM_FRAME, G_COSMETIC_SEED = 0x44FDCC, 0x404460


def wanted(name):
    return OPTIONS['filter'] is None or OPTIONS['filter'].lower() in name.lower()


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-24s %7d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:3]:
            print('        ' + line)
    sys.stdout.flush()


def scaled(count):
    return max(count // 10, 3) if OPTIONS['quick'] else count


def f2r(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


# ---------------------------------------------------------------------------------------
# The rig: one EE with the particle system set up, restored before every case
# ---------------------------------------------------------------------------------------

class Rig:
    def __init__(self, elf, fpu='ps2'):
        emu = self.emu = EE(elf, fpu_model=fpu)
        emu.stub(TASK_ADD, 0)
        emu.stub(RESREF_CTOR, 0)
        emu.call(STATIC_INIT, 1, 0xFFFF)
        emu.unhook(RESREF_CTOR)
        emu.call(PARTICLE_INIT)
        self.dl = emu.alloc(0x100000)
        self.tex = {}
        for ref, (w, h) in ((0x7D8A80, (256, 256)), (0x7D8A90, (128, 512)), (0x7D8AA0, (16, 16))):
            t = emu.alloc(0x40)
            emu.mem.w16(t, w)
            emu.mem.w16(t + 2, h)
            self.tex[ref] = t
        self.packets = []
        emu.stub(ADD_SORTED, 0, function=lambda e: self.packets.append(
            (e.r[4] & M32, e.r[5] & M32, e.r[6] & M32)))
        emu.stub(RESREF_GET, 0, function=lambda e: self.tex.get(e.r[4] & M32, 0))
        emu.stub(IS_FROZEN, 0)
        emu.stub(LINE_DRAW, 0)
        emu.stub(HAZE, 0)
        emu.mem.w8(G_ENABLED, 1)
        self.scratch = emu.alloc(0x10000)
        emu.record_writes = False
        emu.record_calls = False
        self.snapshot = {k: bytes(v) for k, v in emu.mem.pages.items()}
        self.heap = emu._heap
        self.boot_vu()

    def boot_vu(self):
        """VU1 as the game's microcode packet leaves it (program 0 run: memory cleared)."""
        self.vu0 = V.Vu1()
        vif = V.Vif1(self.vu0)
        vif.feed(V.dma_chain_words(self.read, VU_BOOT))
        self.vif_state = (vif.base, vif.ofst, vif.tops, vif.dbf)

    def reset(self):
        pages = self.emu.mem.pages
        for k in list(pages):
            if k not in self.snapshot:
                del pages[k]
        for k, v in self.snapshot.items():
            pages[k][:] = v
        self.emu._heap = self.heap
        self.packets = []
        self.cursor = self.scratch
        self.emu.mem.w32(G_DL_BASE, self.dl)
        self.emu.mem.w32(G_DL_CURSOR, self.dl)
        self.emu.mem.w32(G_DL_CAPACITY, 0x100000 // 8)

    def read(self, a, n):
        return self.emu.mem.read(a & 0x0FFFFFFF, n)

    def alloc(self, n):
        a = (self.cursor + 15) & ~15
        self.cursor = a + n
        return a

    def put_floats(self, values):
        a = self.alloc(4 * len(values))
        for k, x in enumerate(values):
            self.emu.mem.w32(a + 4 * k, x if isinstance(x, int) else f2r(x))
        return a

    def call(self, addr, *args, fargs=()):
        return self.emu.call(addr, *args, fargs=fargs)

    def make_def(self, size_start, size_end, gravity, c0, c1, life, kind, tile):
        d = self.alloc(0x50)
        e = self.emu
        sp = e.r[29]
        for off, v in ((0, c1[3]), (8, life), (0x10, kind), (0x18, tile), (0x20, 0)):
            e.mem.w32(sp + off, v & M32)
        e.call(DEF_INIT, d, c0[0] & M32, c0[1] & M32, c0[2] & M32, c0[3] & M32, c1[0] & M32,
               c1[1] & M32, c1[2] & M32, fargs=(size_start, size_end, gravity))
        return d

    def spawn(self, d, pos, vel, backdate=0.0):
        self.call(SPAWN, d, self.put_floats(pos), self.put_floats(vel), fargs=(backdate,))

    # -- drawing: the VU pipeline ---------------------------------------------------------
    def new_vu(self):
        vu = V.Vu1()
        vu.micro[:] = self.vu0.micro
        vu.data = list(self.vu0.data)
        vu.vf = [list(r) for r in self.vu0.vf]
        vu.vi = list(self.vu0.vi)
        gs = V.GifReader()
        vif = V.Vif1(vu, kick=gs.path1, direct=gs.path2)
        vif.base, vif.ofst, vif.tops, vif.dbf = self.vif_state
        return vu, vif, gs

    def draw(self, view_addr):
        self.packets = []
        self.call(DRAW, view_addr)
        return list(self.packets)

    def send(self, vif, packet_addr):
        vif.feed(V.dma_chain_words(self.read, packet_addr))


# ---------------------------------------------------------------------------------------
# Random scenes
# ---------------------------------------------------------------------------------------

def random_view(rnd, target):
    """A camera mat34 (rows: right, down?, forward as the game's matrices are used, then the
    translation) looking at `target` from a random direction and distance."""
    yaw, pitch = rnd.uniform(0, 2 * math.pi), rnd.uniform(-1.2, 1.2)
    dist = rnd.choice((rnd.uniform(30, 200), rnd.uniform(200, 1500)))
    fwd = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
    cam = [target[k] - fwd[k] * dist for k in range(3)]
    up = (0.0, 0.0, 1.0)
    right = (fwd[1] * up[2] - fwd[2] * up[1], fwd[2] * up[0] - fwd[0] * up[2],
             fwd[0] * up[1] - fwd[1] * up[0])
    n = math.sqrt(sum(x * x for x in right)) or 1.0
    right = [x / n for x in right]
    down = [right[1] * fwd[2] - right[2] * fwd[1], right[2] * fwd[0] - right[0] * fwd[2],
            right[0] * fwd[1] - right[1] * fwd[0]]
    # world -> camera: x' = right . (p - cam), y' = down . (p - cam), z' = fwd . (p - cam)
    # as a row-vector mat34: rows are the world axes' images
    rot = [[right[0], down[0], fwd[0]], [right[1], down[1], fwd[1]], [right[2], down[2], fwd[2]]]
    trans = [-sum(cam[r] * rot[r][c] for r in range(3)) for c in range(3)]
    if rnd.random() < 0.1:                               # noise in the matrix
        rot = [[x + rnd.uniform(-0.05, 0.05) for x in row] for row in rot]
    return [f2r(x) for row in rot for x in row] + [f2r(x) for x in trans]


def random_mat34(rnd, scale=1.0):
    a, b = rnd.uniform(0, 2 * math.pi), rnd.uniform(-1, 1)
    ca, sa, cb, sb = math.cos(a), math.sin(a), math.cos(b), math.sin(b)
    rot = [[ca, sa, 0.0], [-sa * cb, ca * cb, sb], [sa * sb, -ca * sb, cb]]
    if rnd.random() < 0.3:
        rot = [[x * rnd.uniform(0.5, 2.0) for x in row] for row in rot]
    t = [rnd.uniform(-500, 500) * scale for _ in range(3)]
    return [f2r(x) for row in rot for x in row] + [f2r(x) for x in t]


def random_def(rig, rnd, kind=None):
    kind = rnd.randrange(4) if kind is None else kind
    life = rnd.randrange(4)
    ss = rnd.choice((rnd.uniform(0.05, 6.0), rnd.uniform(-2, 2), 1.0, 0.0))
    se = rnd.choice((rnd.uniform(0.05, 12.0), ss, 0.0))
    if kind == 2:
        ss = rnd.choice((rnd.uniform(0.0, 20.0), float(rnd.randrange(0, 12))))
    g = rnd.choice((0.0, rnd.uniform(-60, 60), rnd.uniform(-600, 600)))

    def col():
        return rnd.choice((rnd.randrange(256), rnd.randrange(-100, 400), 0, 255, 128))
    c0 = [col() for _ in range(4)]
    c1 = [col() for _ in range(4)]
    tile = rnd.randrange(256)
    return rig.make_def(ss, se, g, c0, c1, life, kind, tile), kind


def run_ticks(rig, n):
    for _ in range(n):
        rig.call(UPDATE_TASK)


def compare_vertices(got, want, label, examples):
    """got: vu1_emu Vertex list; want: GsVertex tuples.  Returns mismatches."""
    bad = 0
    for i in range(max(len(got), len(want))):
        g = got[i] if i < len(got) else None
        w = want[i] if i < len(want) else None
        gk = None if g is None else (g.x, g.y, g.z, g.f, g.adc, g.rgba,
                                     g.uv if g.prim & 0x10 else None)
        if gk != w:
            bad += 1
            if len(examples) < 6:
                examples.append('%s vertex %d: original %s, reference %s' % (label, i, gk, w))
    return bad


# ---------------------------------------------------------------------------------------
# The particle packet
# ---------------------------------------------------------------------------------------

def list_cells_from_memory(rig, list_addr):
    """(pages, head, tail) of one list as the original's memory holds it."""
    m = rig.emu.mem
    first, last, head, tail = (m.u32(list_addr + 4 * k) for k in range(4))
    pages = []
    p = first
    while p:
        pages.append((p - G_PAGE_DESC) // 4)
        if p == last:
            break
        p = m.u32(p)
    return pages, head, tail


def reference_particle_packet(rig, view, proj_scale, vu, stale_zw, waitq_first=True):
    """The vertices and blend registers the reference expects from the particle packet."""
    m = rig.emu.mem
    clock = m.s16(G_PCLOCK)
    typerecs = [[m.u32(G_TYPE_TABLE + 0x40 * s + 4 * k) for k in range(16)] for s in range(32)]
    out, alphas, live = [], [], []
    header = R.particle_header(view, proj_scale, clock)
    sets = [(G_LISTS, header)]
    for g in range(16):
        base = G_GROUPS + g * 0x138
        if m.u32(base + 0x130):
            gm = [m.u32(base + 0x100 + 4 * k) for k in range(12)]
            hdr = dict(header)
            hdr['m'] = R.columns(R.group_matrix(gm, view, proj_scale))
            sets.append((base, hdr))
    for base, hdr in sets:
        for kind in range(3):
            if kind < 2:
                alphas.append(0x44 if kind == 0 else 0x48)
            for life in range(4):
                lst = base + 16 * (kind * 4 + life)
                if not m.u32(lst):
                    continue
                pages, head, tail = list_cells_from_memory(rig, lst)
                for page, blk, cells in R.list_blocks(pages, head, tail):
                    for c in cells:
                        cell = (bytes(16) if c is None else
                                m.read(G_PAGES + page * 0x1000 + c * 16, 16))
                        slot = struct.unpack_from('<H', cell, 14)[0] // 4
                        rec = typerecs[slot & 31]
                        if kind == 2:
                            vs = R.line_vertices(cell, rec, hdr, vu, waitq_first)
                        else:
                            vs = R.sprite_vertices(cell, rec, hdr, vu, stale_zw)
                        out += vs
                        if c is not None and slot:
                            live.append((kind, base != G_LISTS, cell, rec, hdr, vs))
    return out, alphas, live


def prop_particles(rig, rnd, cases, label, groups=False, fpu_vu='chop'):
    bad = total = 0
    examples = []
    for case in range(cases):
        rig.reset()
        e = rig.emu
        e.mem.w32(G_SIM_FRAME, rnd.randrange(1 << 16))
        e.mem.w16(G_PCLOCK, rnd.choice((0, rnd.randrange(1 << 15), 0x7FF0)))
        target = [rnd.uniform(-3000, 3000), rnd.uniform(-3000, 3000), rnd.uniform(-200, 400)]
        defs = [random_def(rig, rnd) for _ in range(rnd.randrange(1, 7))]
        handles = []
        if groups:
            for _ in range(rnd.randrange(1, 4)):
                h = rig.call(GROUP_CREATE) & M32
                if h:
                    handles.append(h)
                    if rnd.random() < 0.8:
                        rig.call(GROUP_SETMAT, h, rig.put_floats(random_mat34(rnd, 0.2)))
        for tick in range(rnd.randrange(1, 40)):
            for _ in range(rnd.randrange(0, 12)):
                d, kind = rnd.choice(defs)
                h = rnd.choice(handles) if handles and rnd.random() < 0.6 else 0
                if h:
                    rig.call(GROUP_BEGIN, h)
                spread = rnd.choice((30.0, 300.0))
                pos = [target[k] + rnd.uniform(-spread, spread) for k in range(3)]
                if h:
                    pos = [rnd.uniform(-spread, spread) for k in range(3)]
                vel = [rnd.choice((0.0, rnd.uniform(-60, 60), rnd.uniform(-400, 400))) for _ in range(3)]
                back = rnd.choice((0.0, 0.0, rnd.uniform(0, 1.6), -1.0))
                rig.spawn(d, pos, vel, back)
                if h:
                    rig.call(GROUP_END, h)
            run_ticks(rig, rnd.choice((1, 1, 2, 7)))
        view = random_view(rnd, target)
        proj = f2r(rnd.choice((477.5, rnd.uniform(200, 1200))))
        e.mem.w32(G_PROJ_SCALE, proj)
        vaddr = rig.put_floats(view)
        packets = rig.draw(vaddr)
        part = [p for p in packets if p[2] == rig.tex[0x7D8A80]]
        vu, vif, gs = rig.new_vu()
        vu.model = fpu_vu
        stale = (vu.vf[18][2], vu.vf[18][3])
        for p in part:
            rig.send(vif, p[0])
        want, alphas, live = reference_particle_packet(rig, view, proj, R.Vu(fpu_vu), stale)
        got = [v for v in gs.vertices if v.prim in (R.PRIM_SPRITE, R.PRIM_LINE)]
        for kind, in_group, cell, rec, hdr, vs in live:
            shown = int(not vs[1][4] and bool(vs[0][5][3] or vs[1][5][3]))
            cover('live particles')
            cover('drawn (not culled, alpha > 0)', shown)
            cover('lines drawn', int(shown and kind == 2))
            cover('group particles drawn', int(shown and in_group))
            # ref_particles.colour_at (coordinator's round-2 rounding) against the bytes sent
            d = P.ParticleDef()
            d.kind = kind
            d.c0 = tuple(C.to_float(x) for x in rec[8:12])
            d.crate = tuple(C.to_float(x) for x in rec[12:16])
            birth = struct.unpack_from('<h', cell, 6)[0]
            age = e.mem.s16(G_PCLOCK) - birth
            if d.colour_at(float(age)) != vs[0][5]:
                cover('ref_particles.colour_at differs from the VU colour')
            cover('colour_at compared')
            if kind == 2:
                old = R.line_vertices(cell, rec, hdr, R.Vu(fpu_vu), waitq_first=False)
                cover('line tails moved by the WAITQ model', int(old[1] != vs[1] and bool(shown)))
        total += len(want) // 2
        b = compare_vertices(got, want, 'case %d' % case, examples)
        got_alpha = [ev[2] for ev in gs.events if ev[0] == 'reg' and ev[1] == 'ALPHA_1']
        if got_alpha != alphas:
            b += 1
            examples.append('case %d: ALPHA_1 sequence %s, reference %s' % (case, got_alpha, alphas))
        bad += 1 if b else 0
    report(label, bad, total, 'particles: every sprite/line vertex, ALPHA_1 per kind (%d scenes)' % cases,
           examples)
    return bad


# ---------------------------------------------------------------------------------------
# Trails
# ---------------------------------------------------------------------------------------

def draw_scene(rig, rnd, target):
    view = random_view(rnd, target)
    proj = f2r(rnd.choice((477.5, rnd.uniform(200, 1200))))
    rig.emu.mem.w32(G_PROJ_SCALE, proj)
    packets = rig.draw(rig.put_floats(view))
    vu, vif, gs = rig.new_vu()
    order = ([p for p in packets if p[2] == rig.tex[0x7D8A80]] +
             [p for p in packets if p[2] not in (rig.tex[0x7D8A80], rig.tex[0x7D8A90])][::-1] +
             [p for p in packets if p[2] == rig.tex[0x7D8A90]])
    for p in order:
        rig.send(vif, p[0])
    return view, proj, gs, vu


def reference_trails(rig, view, proj, waitq_first=True):
    m = rig.emu.mem
    hdr = R.particle_header(view, proj, 0)
    row_v = tuple(C.to_float(m.u32(G_TRAIL_ROW_V + 4 * k)) for k in range(10))
    out, alphas = [], []
    for i in range(64):
        t = R.Trail.from_bytes(m.read(G_TRAILS + 0x410 * i, 0x410))
        if t.handle and t.oldest != t.newest:
            out += R.trail_vertices(t, hdr['m'], hdr['vf6'], hdr['vf7'], R.Vu(), waitq_first, row_v)
            alphas.append(R.trail_header(t, row_v)[3][0])
    return out, alphas


def prop_trails(rig, rnd, cases, label):
    bad = total = 0
    examples = []
    for case in range(cases):
        rig.reset()
        e = rig.emu
        target = [rnd.uniform(-3000, 3000), rnd.uniform(-3000, 3000), rnd.uniform(-200, 400)]
        trails = []
        for _ in range(rnd.randrange(1, 6)):
            flags = rnd.choice((0, 0, 2, 2, 4, 6, 8, 0x10, 0x14, 1, 0xA))
            life = rnd.choice((0.2, 0.5, 1.0, rnd.uniform(0.05, 3.0)))
            col = [rnd.randrange(256) for _ in range(4)]
            h = rig.call(TRAIL_CREATE, rnd.randrange(9), rnd.choice((1000, rnd.randrange(1, 1024))),
                         flags, *col, fargs=(life,)) & 0xFFFF
            if h:
                trails.append((h, flags))
        pos = {h: [target[k] + rnd.uniform(-100, 100) for k in range(3)] for h, _ in trails}
        for tick in range(rnd.randrange(1, 90)):
            for h, flags in trails:
                if rnd.random() < 0.8:
                    p = pos[h]
                    p = [p[k] + rnd.uniform(-20, 20) for k in range(3)]
                    pos[h] = p
                    if flags & 2:
                        q = [p[k] + rnd.uniform(-30, 30) for k in range(3)]
                        rig.call(TRAIL_ADD_PAIR, h, rig.put_floats(p), rig.put_floats(q),
                                 fargs=(rnd.choice((1.0, rnd.random(), 0.5)),))
                    else:
                        rig.call(TRAIL_ADD, h, rig.put_floats(p))
            rig.call(TRAIL_UPDATE)
        view, proj, gs, vu = draw_scene(rig, rnd, target)
        want, alphas = reference_trails(rig, view, proj)
        got = [v for v in gs.vertices if v.prim in (R.PRIM_TRAIL, R.PRIM_TRAIL_PAIRED)]
        total += len(want)
        b = compare_vertices(got, want, 'case %d' % case, examples)
        # the ALPHA_1 of each trail's header (after the particle packet's two)
        got_alpha = [ev[2] for ev in gs.events if ev[0] == 'reg' and ev[1] == 'ALPHA_1'][2:]
        if got_alpha != alphas:
            b += 1
            examples.append('case %d: trail ALPHA_1 %s, reference %s' % (case, got_alpha, alphas))
        if want:
            old, _ = reference_trails(rig, view, proj, waitq_first=False)
            cover('trail vertices moved by the WAITQ model', sum(1 for a, c in zip(old, want) if a != c))
        cover('trail vertices drawn', sum(1 for v in want if not v[4]))
        bad += 1 if b else 0
    report(label, bad, total, 'trail vertices (single and paired), ALPHA_1 (%d scenes)' % cases, examples)
    return bad


def main(argv):
    args = []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == '--quick':
            OPTIONS['quick'] = True
        elif a == '--seed':
            i += 1
            OPTIONS['seed'] = int(argv[i])
        elif a == '-k':
            i += 1
            OPTIONS['filter'] = argv[i]
        elif a == '-v':
            OPTIONS['verbose'] = True
        else:
            args.append(a)
        i += 1
    elf = args[0] if args else os.path.join(ROOT, 'SLUS_209.73')
    if not os.path.exists(elf):
        print('difftest_fx_render: no executable at %s - nothing to compare (your own copy '
              'of SLUS_209.73 is needed)' % elf)
        return 0
    with open(elf, 'rb') as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('difftest_fx_render: %s is not US v2.00 (sha256 %s)' % (elf, digest))
        return 0
    seed = OPTIONS['seed']
    for fpu in ('ps2', 'chop'):
        C.set_fpu(fpu)
        rig = Rig(elf, fpu)
        tag = '' if fpu == 'ps2' else ' [chop]'
        share = 1 if fpu == 'ps2' else 4
        for name, fn, n in PROPERTIES:
            if wanted(name):
                fn(rig, random.Random('%s/%s/%d' % (name, fpu, seed)), max(scaled(n) // share, 2),
                   name + tag)
    C.set_fpu('ps2')
    if COVER:
        print('reached: ' + ', '.join('%s %d' % kv for kv in sorted(COVER.items())))
    failed = [n for n, ok in RESULTS if not ok]
    print('%d properties, %d failed' % (len(RESULTS), len(failed)))
    return 1 if failed else 0


PROPERTIES = [
    ('particles', lambda rig, rnd, n, label: prop_particles(rig, rnd, n, label), 60),
    ('particle groups', lambda rig, rnd, n, label: prop_particles(rig, rnd, n, label, groups=True), 60),
    ('trails', prop_trails, 60),
]

if __name__ == '__main__':
    sys.exit(main(sys.argv))
