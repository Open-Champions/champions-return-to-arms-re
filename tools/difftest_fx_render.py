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

Properties
    particles, particle groups   random definitions of every kind, spawns (back-dated too,
                       some into groups with random matrices), ticks; every sprite and line
                       vertex of the particle packet and the ALPHA_1 per kind
    trails             random trails (all flag combinations, rows, widths, lifetimes),
                       single points and pairs, ring wrap; every strip vertex, ALPHA_1
    beams              beam_create / beam_update / several draws (frozen ones too): node
                       memory, both random streams, the rebuilt points of the drawing trail,
                       the emptied other trail, expiry; then the strips
    glows              random queues (over 0x400 too), both passes: every A+D write of
                       every packet, PRIM, sort key and texture
    trail builders     spline_eval, trail_setSpline, trail_setCircle, trail_sweepPairs,
                       trail_addPair: outputs and the trail ring
    ..., vu1.cpp WAITQ the line and trail programs with tools/recomp/render/vu1.cpp's reading
                       of `MULq | WAITQ` (vu1_emu waitq_first=False) against the reference's
                       same option: both readings are modelled exactly; which one the
                       machine has is Inferred (docs/effects.md)
    After the properties the script lists how often the cases reached the paths of interest.

    Which order the sorted packets are drawn in is not executed here: gfx_addSortedPacket
    is replaced by a recorder and the packets are sent in the order the code that walks
    the sorted list is Inferred to use (docs: last added first within a key for different
    textures, as gfx_dmaHandler 0x16b998 walks the lists), which matters because the trail
    program uses the matrix the particle packet leaves in VU1.
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
BEAM_CREATE, BEAM_UPDATE = 0x193088, 0x1933C8
G_BEAMS, G_DRAW_FRAME, G_NET_FRAME, G_IN_SIM_TICK, G_LIBC_REENT = 0x7E30D0, 0x44FDD0, 0x4027AC, 0x402794, 0x50C7E8
GLOW_ADD, GLOW_DRAW = 0x18FC78, 0x1907D0
SPLINE_EVAL, TRAIL_SET_SPLINE, TRAIL_SWEEP, TRAIL_CIRCLE = 0x1911E8, 0x1918A0, 0x191EA0, 0x1920E0
G_GLOW_QUEUE, G_GLOW_COUNT, G_CAMERA, G_VIEWPROJ = 0x7D8B00, 0x82CC94, 0x44F110, 0x44F140
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
        self.frozen = 0
        emu.stub(IS_FROZEN, 0, function=lambda e: self.frozen)
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
        self.frozen = 0
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


def prop_particles(rig, rnd, cases, label, groups=False, fpu_vu='chop', waitq_first=True):
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
        vu.waitq_first = waitq_first
        stale = (vu.vf[18][2], vu.vf[18][3])
        for p in part:
            rig.send(vif, p[0])
        want, alphas, live = reference_particle_packet(rig, view, proj, R.Vu(fpu_vu), stale, waitq_first)
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

def draw_scene(rig, rnd, target, waitq_first=True):
    view = random_view(rnd, target)
    proj = f2r(rnd.choice((477.5, rnd.uniform(200, 1200))))
    rig.emu.mem.w32(G_PROJ_SCALE, proj)
    packets = rig.draw(rig.put_floats(view))
    vu, vif, gs = rig.new_vu()
    vu.waitq_first = waitq_first
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
            if waitq_first:
                ch = R.trail_chunks(t)
                cover('trail chunks', len(ch))
                cover('trails over the ring end', int(any(a + n == 0x80 for a, n in ch[:-1])))
                cover('trails with odd oldest', t.oldest & 1)
            alphas.append(R.trail_header(t, row_v)[3][0])
    return out, alphas


def prop_trails(rig, rnd, cases, label, waitq_first=True):
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
        for tick in range(rnd.choice((rnd.randrange(1, 90), rnd.randrange(100, 300)))):
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
        view, proj, gs, vu = draw_scene(rig, rnd, target, waitq_first)
        want, alphas = reference_trails(rig, view, proj, waitq_first)
        got = [v for v in gs.vertices if v.prim in (R.PRIM_TRAIL, R.PRIM_TRAIL_PAIRED)]
        total += len(want)
        b = compare_vertices(got, want, 'case %d' % case, examples)
        # the ALPHA_1 of each trail's header (after the particle packet's two)
        got_alpha = [ev[2] for ev in gs.events if ev[0] == 'reg' and ev[1] == 'ALPHA_1'][2:]
        if got_alpha != alphas:
            b += 1
            examples.append('case %d: trail ALPHA_1 %s, reference %s' % (case, got_alpha, alphas))
        if want and waitq_first:
            old, _ = reference_trails(rig, view, proj, waitq_first=False)
            cover('trail vertices moved by the WAITQ model', sum(1 for a, c in zip(old, want) if a != c))
        cover('trail vertices drawn', sum(1 for v in want if not v[4]))
        bad += 1 if b else 0
    report(label, bad, total, 'trail vertices (single and paired), ALPHA_1 (%d scenes)' % cases, examples)
    return bad


# ---------------------------------------------------------------------------------------
# Beams
# ---------------------------------------------------------------------------------------

class RefBeam:
    pass


def libc_state(rig):
    return rig.emu.mem.u64(rig.emu.mem.u32(G_LIBC_REENT) + 0xA8)


def prop_beams(rig, rnd, cases, label):
    bad = total = 0
    examples = []
    for case in range(cases):
        rig.reset()
        e, m = rig.emu, rig.emu.mem
        b = 0
        sim = rnd.randrange(1000, 1 << 20)
        m.w32(G_SIM_FRAME, sim)
        m.w32(G_NET_FRAME, sim + rnd.randrange(-3, 3))
        m.w32(G_DRAW_FRAME, rnd.randrange(1 << 20))
        e.mem.w32(G_COSMETIC_SEED, rnd.randrange(1 << 32))
        target = [rnd.uniform(-3000, 3000), rnd.uniform(-3000, 3000), rnd.uniform(-200, 400)]
        beams = {}
        for _ in range(rnd.randrange(1, 5)):
            m.w8(G_IN_SIM_TICK, rnd.randrange(2))
            a = [target[k] + rnd.uniform(-150, 150) for k in range(3)]
            z = [target[k] + rnd.uniform(-150, 150) for k in range(3)]
            jitter = f2r(rnd.choice((10.0, rnd.uniform(0, 60))))
            scale = f2r(rnd.choice((1.0, rnd.uniform(0, 20))))
            depth = rnd.choice((0, 1, 2, 3, 4, 5, 6, 9))
            rgba = rnd.randrange(1 << 32)
            width = rnd.choice((1000, rnd.randrange(4, 1024)))
            cos = C.Lcg(m.u32(G_COSMETIC_SEED))
            libc = C.LibcRand(libc_state(rig))
            h = rig.call(BEAM_CREATE, rig.put_floats(a), rig.put_floats(z), width, depth, rgba,
                         fargs=(C.to_float(jitter), C.to_float(scale))) & M32
            if not h:
                continue
            idx = h & 0xFF
            rb = RefBeam()
            rb.depth = min(depth, R.BEAM_MAX_DEPTH)
            rb.nodes = R.beam_build_nodes(jitter, rb.depth, cos, libc)
            rb.jitter, rb.scale = jitter, scale
            rb.a, rb.z = [f2r(x) for x in a], [f2r(x) for x in z]
            beams[idx] = rb
            if cos.state != m.u32(G_COSMETIC_SEED) or libc.state != libc_state(rig):
                b += 1
                examples.append('case %d beam %d: seeds after create differ' % (case, idx))
        view = random_view(rnd, target)
        proj = f2r(rnd.choice((477.5, rnd.uniform(200, 1200))))
        m.w32(G_PROJ_SCALE, proj)
        vaddr = rig.put_floats(view)
        for frame in range(rnd.randrange(1, 6)):
            for idx, rb in beams.items():
                if rnd.random() < 0.3:
                    rb.a = [f2r(C.to_float(x) + rnd.uniform(-5, 5)) for x in rb.a]
                    h = m.u32(G_BEAMS + 0x734 * idx + 0x730)
                    rig.call(BEAM_UPDATE, h, rig.put_floats(rb.a), rig.put_floats(rb.z),
                             rnd.randrange(256), rnd.choice((-1, rnd.randrange(1024))))
            cos = C.Lcg(m.u32(G_COSMETIC_SEED))
            rig.frozen = int(rnd.random() < 0.15)
            cover('frozen beam draws', rig.frozen)
            draw_frame = m.u32(G_DRAW_FRAME)
            sim = m.u32(G_SIM_FRAME)
            alive = {}
            for idx in sorted(beams):
                base = G_BEAMS + 0x734 * idx
                if not m.u8(base + 0x72C):
                    continue
                frame_now = C.s32(m.u32(G_NET_FRAME if m.u8(base + 0x72E) else G_SIM_FRAME))
                if C.s32(m.u32(base + 0x728)) < frame_now:
                    continue                                    # destroyed by this draw
                rb = beams[idx]
                if not rig.frozen:
                    R.beam_drift_nodes(rb.nodes, m.u32(base + 0x718), rb.depth, cos)
                pts = R.beam_points(rb.nodes, [m.u32(base + 0x700 + 4 * k) for k in range(3)],
                                    [m.u32(base + 0x70C + 4 * k) for k in range(3)], rb.depth,
                                    m.u32(base + 0x71C), C.Lcg(R.beam_frame_seed(sim, idx)))
                alive[idx] = pts
            rig.draw(vaddr)
            if cos.state != m.u32(G_COSMETIC_SEED):
                b += 1
                examples.append('case %d frame %d: cosmetic seed after the draw differs' % (case, frame))
            for idx, rb in beams.items():
                base = G_BEAMS + 0x734 * idx
                active = m.u8(base + 0x72C)
                if (idx in alive) != bool(active):
                    b += 1
                    examples.append('case %d beam %d: alive %s, original active %d' % (case, idx, idx in alive, active))
                    continue
                if not active:
                    continue
                total += 1
                got = [m.u32(base + 0x1C * n + 4 * k) for n in range(len(rb.nodes)) for k in range(7)]
                want = [w for n in rb.nodes for w in n.words()]
                if got != want:
                    b += 1
                    k = next(i for i in range(len(got)) if got[i] != want[i])
                    examples.append('case %d beam %d frame %d: nodes differ at node %d word %d: %08x vs %08x' % (
                        case, idx, frame, k // 7, k % 7, got[k], want[k]))
                ring, clock = R.beam_trail_points(alive[idx])
                draw_t = m.u32(base + (0x724 if draw_frame & 1 == 0 else 0x720))
                other = m.u32(base + (0x720 if draw_frame & 1 == 0 else 0x724))
                t = R.Trail.from_bytes(m.read(draw_t, 0x410))
                o = R.Trail.from_bytes(m.read(other, 0x410))
                ring = ring[:125]
                if (t.oldest, t.newest, t.clock) != (0, len(ring), clock) or t.points[:len(ring)] != ring:
                    b += 1
                    examples.append('case %d beam %d frame %d: trail %s/%s/%s %s.., reference %d %d %s..' % (
                        case, idx, frame, t.oldest, t.newest, t.clock, t.points[:2], len(ring), clock, ring[:2]))
                if (o.oldest, o.newest, o.clock) != (0, 0, 0):
                    b += 1
                    examples.append('case %d beam %d: the other trail is not empty' % (case, idx))
                cover('beam points', len(ring))
            m.w32(G_DRAW_FRAME, (m.u32(G_DRAW_FRAME) + 1) & M32)
            if rnd.random() < 0.5:
                m.w32(G_SIM_FRAME, m.u32(G_SIM_FRAME) + rnd.randrange(1, 4))
                m.w32(G_NET_FRAME, m.u32(G_NET_FRAME) + rnd.randrange(0, 4))
        rig.frozen = 1                          # one more draw, sent to the GS: the strips
        view2, proj2, gs, vu = draw_scene(rig, rnd, target)
        want, _ = reference_trails(rig, view2, proj2)
        got = [v for v in gs.vertices if v.prim in (R.PRIM_TRAIL, R.PRIM_TRAIL_PAIRED)]
        b += compare_vertices(got, want, 'case %d strips' % case, examples)
        cover('beam strip vertices drawn', sum(1 for v in want if not v[4]))
        cover('beams destroyed by expiry', sum(1 for i in beams if not m.u8(G_BEAMS + 0x734 * i + 0x72C)))
        bad += 1 if b else 0
    report(label, bad, total, 'beams: nodes, drift, both seeds, rebuilt trail points (%d scenes)' % cases,
           examples)
    return bad


# ---------------------------------------------------------------------------------------
# Glows
# ---------------------------------------------------------------------------------------

def prop_glows(rig, rnd, cases, label):
    bad = total = 0
    examples = []
    for case in range(cases):
        rig.reset()
        e, m = rig.emu, rig.emu.mem
        target = [rnd.uniform(-3000, 3000), rnd.uniform(-3000, 3000), rnd.uniform(-200, 400)]
        view = random_view(rnd, target)
        proj = C.mat4_set_projection(0x3F7FFFFF, 0x3EEEEEEE, f2r(rnd.uniform(300, 900)), R.ONE,
                                     0x457FFF00, 0x41900000, 0x44E10000)
        vp = C.mat4_mul_mat34(view, proj)
        for k in range(12):
            m.w32(G_CAMERA + 4 * k, view[k])
        for k in range(16):
            m.w32(G_VIEWPROJ + 4 * k, vp[k])
        texs = {}
        for _ in range(rnd.randrange(1, 4)):
            t = rig.alloc(0x40)
            w, h = rnd.choice(((32, 32), (64, 64), (rnd.randrange(1, 300), rnd.randrange(1, 300))))
            m.w16(t, w)
            m.w16(t + 2, h)
            texs[t] = (w, h)
        n = rnd.choice((rnd.randrange(1, 40), rnd.randrange(1, 300), 1030 if rnd.random() < 0.05 else 3))
        for _ in range(n):
            pos = [target[k] + rnd.uniform(-400, 400) for k in range(3)]
            bias = rnd.choice((0.0, 5.0, rnd.uniform(-50, 200)))
            size = rnd.choice((8000.0, rnd.uniform(0, 20000), rnd.uniform(0, 300)))
            col = [rnd.randrange(256) for _ in range(4)]
            tex = rnd.choice(list(texs) + [0] * (1 if rnd.random() < 0.1 else 0))
            rig.call(GLOW_ADD, rig.put_floats(pos), *col, tex, rnd.randrange(1 << 16),
                     rnd.choice((0, 1, 2, 3, 4, 5, 6, 7, rnd.randrange(1 << 16))),
                     fargs=(bias, size))
        count = m.u32(G_GLOW_COUNT)
        queue = [R.Glow.from_bytes(m.read(G_GLOW_QUEUE + 0x20 * i, 0x20)) for i in range(count)]
        b = 0
        if count != min(n, R.GLOW_MAX):
            b += 1
            examples.append('case %d: %d glows queued, reference %d' % (case, count, min(n, R.GLOW_MAX)))
        for pass_ in (1, 0):
            rig.packets = []
            rig.call(GLOW_DRAW, pass_)
            want = R.glow_packets(queue, pass_, view, vp, texs)
            got = list(rig.packets)
            if [(k, t) for _, k, t in got] != [(k, t) for k, t, _, _ in want]:
                b += 1
                examples.append('case %d pass %d: packets %s, reference %s' % (
                    case, pass_, [(k, hex(t)) for _, k, t in got], [(k, hex(t)) for k, t, _, _ in want]))
                continue
            for (addr, _, _), (key, tex, prim, ev) in zip(got, want):
                vu, vif, gs = rig.new_vu()
                rig.send(vif, addr)
                total += 1
                if gs.raw != ev or gs.tags[0][3] != prim or not gs.tags[0][2]:
                    b += 1
                    k = next((i for i in range(min(len(gs.raw), len(ev))) if gs.raw[i] != ev[i]), None)
                    examples.append('case %d pass %d: packet differs at write %s: %s vs %s (%d/%d writes)' % (
                        case, pass_, k, gs.raw[k] if k is not None else '', ev[k] if k is not None else '',
                        len(gs.raw), len(ev)))
                cover('glow sprites drawn', sum(1 for r, _ in ev if r == 0x05) // 2 if prim == 0x15E else 0)
                cover('glow quads drawn', sum(1 for r, _ in ev if r == 0x0D) // 2 if prim == 0x15C else 0)
        bad += 1 if b else 0
    report(label, bad, total, 'glow packets: every A+D write, PRIM, sort key, texture (%d scenes)' % cases,
           examples)
    return bad


# ---------------------------------------------------------------------------------------
# Trail builders
# ---------------------------------------------------------------------------------------

def rvec(rnd, scale=300.0):
    return [f2r(rnd.choice((rnd.uniform(-scale, scale), 0.0, float(rnd.randrange(-50, 50))))) for _ in range(3)]


def trail_state(rig, h):
    return R.Trail.from_bytes(rig.emu.mem.read(G_TRAILS + 0x410 * (h & 0xFF), 0x410))


def prop_builders(rig, rnd, cases, label):
    bad = total = 0
    examples = []
    m = rig.emu.mem
    for case in range(cases):
        rig.reset()
        kind = case % 5
        b = 0
        if kind == 0:                                   # spline_eval
            count = rnd.randrange(2, 9)
            pts = [rvec(rnd) for _ in range(count + 1)]
            addr = rig.put_floats([x for p in pts for x in p])
            t = rnd.choice((rnd.uniform(-0.2, 1.2), 0.0, 1.0, rnd.random()))
            outp, outt = rig.alloc(16), rig.alloc(16)
            wp, wt = rnd.random() < 0.8, rnd.random() < 0.8
            rig.call(SPLINE_EVAL, addr, count, outp if wp else 0, outt if wt else 0, fargs=(t,))
            pos, tan = R.spline_eval(f2r(t), pts, count, wp, wt)
            got_p = [m.u32(outp + 4 * k) for k in range(3)] if wp else None
            got_t = [m.u32(outt + 4 * k) for k in range(3)] if wt else None
            if got_p != pos or got_t != tan:
                b += 1
                examples.append('case %d spline_eval t=%r: %s %s vs %s %s' % (case, t, got_p, got_t, pos, tan))
            total += 1
            bad += 1 if b else 0
            continue
        h = rig.call(TRAIL_CREATE, rnd.randrange(9), 1000, 2 if kind == 3 else 0, 1, 2, 3, 4,
                     fargs=(rnd.uniform(0.1, 2.0),)) & 0xFFFF
        old = trail_state(rig, h)
        for _ in range(rnd.randrange(0, 5)):            # leave something in the ring first
            rig.call(TRAIL_ADD, h, rig.put_floats(rvec(rnd)))
        if kind == 1:                                   # trail_setSpline
            count = rnd.randrange(2, 7)
            pts = [rvec(rnd) for _ in range(count)]
            steps = rnd.choice((rnd.randrange(1, 60), 40, rnd.randrange(60, 125)))
            st, en = rnd.choice((0.0, rnd.random())), rnd.choice((1.0, rnd.random(), 0.5))
            rig.call(TRAIL_SET_SPLINE, h, rig.put_floats([x for p in pts for x in p]), count, steps,
                     fargs=(st, en))
            want_pts, life = R.trail_set_spline(f2r(st), f2r(en), pts, count, steps)
            want_pts = want_pts[:126]
            want = [R.trail_point(p, k + 1) for k, p in enumerate(want_pts)]
        elif kind == 2:                                 # trail_setCircle
            n = rvec(rnd, 1.0) if rnd.random() < 0.7 else [R.ONE, 0, 0]
            if all(x & 0x7FFFFFFF == 0 for x in n):
                n = [R.ONE, f2r(0.01), 0]
            steps = rnd.choice((rnd.randrange(1, 126), 32, 130))
            radius = rnd.uniform(0, 200)
            centre = rvec(rnd)
            rig.call(TRAIL_CIRCLE, h, rig.put_floats(centre), rig.put_floats(n), steps, fargs=(radius,))
            want_pts = R.trail_set_circle(f2r(radius), centre, n, steps)[:126]
            want = [R.trail_point(p, k + 1) for k, p in enumerate(want_pts)]
            life = old.lifetime
        else:                                           # trail_sweepPairs (3) / addPair (4)
            steps = rnd.randrange(3, 70)
            centre, axis, pa, pb = rvec(rnd), rvec(rnd, 1.0), rvec(rnd, 50.0), rvec(rnd, 50.0)
            if all(x & 0x7FFFFFFF == 0 for x in axis):
                axis = [0, 0, R.ONE]
            if kind == 3:
                rig.call(TRAIL_SWEEP, h, rig.put_floats(centre), rig.put_floats(axis), rig.put_floats(pa),
                         rig.put_floats(pb), steps)
                pairs, life = R.trail_sweep_pairs(centre, axis, pa, pb, steps)
                want = []
                for k, (p0, p1) in enumerate(pairs[:63]):
                    want += R.trail_pair(R.ONE, p0, p1, k)
            else:
                t0 = trail_state(rig, h)
                alpha = rnd.choice((1.0, rnd.random(), 0.0, 1.5))
                rig.call(TRAIL_ADD_PAIR, h, rig.put_floats(pa), rig.put_floats(pb), fargs=(alpha,))
                full = (t0.newest + 1) & 0x7F == t0.oldest or (t0.newest + 2) & 0x7F == t0.oldest
                want = t0.points[:t0.newest] + ([] if full else R.trail_pair(f2r(alpha), pa, pb, t0.clock))
                life = t0.lifetime
        t = trail_state(rig, h)
        got = t.points[t.oldest:t.newest] if t.newest >= t.oldest else None
        if got != want or t.lifetime != life or (kind != 4 and t.clock != len(want) // (2 if kind == 3 else 1)):
            b += 1
            k = next((i for i in range(min(len(got or []), len(want))) if got[i] != want[i]), None)
            examples.append('case %d kind %d: ring %d..%d clock %d life %d vs %d points life %d; first diff %s: %s vs %s'
                            % (case, kind, t.oldest, t.newest, t.clock, t.lifetime, len(want), life, k,
                               got[k] if k is not None else '', want[k] if k is not None else ''))
        cover('builder points', len(want))
        total += 1
        bad += 1 if b else 0
    report(label, bad, total, 'spline_eval, trail_setSpline / setCircle / sweepPairs / addPair (%d calls)'
           % cases, examples)
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
    ('beams', prop_beams, 80),
    ('glows', prop_glows, 120),
    ('trail builders', prop_builders, 1000),
    ('particles, vu1.cpp WAITQ', lambda rig, rnd, n, label: prop_particles(rig, rnd, n, label, waitq_first=False), 20),
    ('trails, vu1.cpp WAITQ', lambda rig, rnd, n, label: prop_trails(rig, rnd, n, label, waitq_first=False), 20),
]

if __name__ == '__main__':
    sys.exit(main(sys.argv))
