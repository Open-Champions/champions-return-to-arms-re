#!/usr/bin/env python3
"""difftest_particles.py - compare the round-1 particle contract (tools/ref_particles.py)
with the game's own machine code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_particles.py [path/to/SLUS_209.73] [--quick] [--seed N] [-k TEXT] [-v]

    --quick   a tenth of the samples
    --seed N  seed of the random choices (default 20973); one seed repeats exactly
    -k TEXT   run only the properties whose name contains TEXT
    -v        print up to three failing cases per property

Every property prints one line: PASS or FAIL, the name, the number of cases compared and
what was compared.  Exit status 1 when any property fails.

How a property is tested
    The ORIGINAL functions are executed by tools/ee_emu.py (an instruction interpreter, not
    a console) on memory this script prepares: the static initialiser 0x195d30 (1, 0xffff)
    and particle_init 0x18e648 build the pools as the game does at start-up (resource
    references and task_add are stubbed), definitions are built by
    the game's own particleDef_ctor 0x18f3d0 / particleDef_set 0x18f118 in memory this
    script allocates, and every operation is applied to the original and to the model.

    Integer state is compared exactly: the 16-byte particle records, the page lists of
    every list of the global set and of every group (first, last, head and tail cursors and
    the pages between), the free-page list in order, the 32 slot flags and the slot of
    every definition, the live counts, the group handles, idle counters and matrices, the
    particle clock, the resident type records, the cosmetic seed.

    Floats: tools/ref_particles.py is a Python-float model (round to nearest), the console
    rounds toward zero, so its float fields are compared with a tolerance that each
    property states (one unit in the last place for the definition, a relative bound for
    the emitter, whose angles the model takes from math.cos instead of math_cos16).  The
    number of bit-identical floats is printed as well.

Properties
    definition      particleDef_ctor on random arguments (out-of-range classes, kinds 2 and 3,
                    colours outside 0..255): the 0x50 bytes against ParticleDef.build
    redefine        particleDef_set on resident and idle definitions: the 0x50 bytes and the
                    copy into the type table only when the bytes changed
    spawn record    particle_spawn with random positions, velocities and back-dates: the
                    16-byte record against spawn_record
    pools           random sequences of spawn, update ticks, groups (create, begin, end, set
                    matrix, free), cutscene ticks and the clock wrap: the whole pool state
                    against ParticleSystem after every operation
    emitter definition
                    the level emitter type's definition, built in world_fixup from the record's
                    first 17 bytes, against ParticleDef.from_emitter_record
    flipbook        the step of particle_draw (0x1948f0-0x194990) on random resident
                    records and frame numbers against flipbook_step
    emitter         emitter_run 0x195400 on random records, positions, yaws, flips and weather:
                    the (position, velocity) list handed to particle_spawn, the on/off state
                    and the cosmetic seed against ref_particles.emitter_run
"""
import hashlib
import math
import os
import random
import struct
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError, M32          # noqa: E402
import ref_particles as P                     # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False}
RESULTS = []
COVER = {}


def cover(what, count=1):
    if count:
        COVER[what] = COVER.get(what, 0) + count

# ---- addresses in SLUS_209.73 -----------------------------------------------------------
PARTICLE_INIT, DEF_CTOR, DEF_SET, SPAWN = 0x18E648, 0x18F3D0, 0x18F118, 0x18F3F8
UPDATE_TASK, RESET_ALL = 0x18F970, 0x18EBB8
GROUP_CREATE, GROUP_BEGIN, GROUP_END, GROUP_SET_MATRIX, GROUP_FREE = (
    0x18E880, 0x18E958, 0x18E9A0, 0x18E9E8, 0x18EA90)
EMITTER_RUN = 0x195400
STATIC_INIT, RESOURCE_REF_CTOR = 0x195D30, 0x173768
FIXUP_DEF_LO, FIXUP_DEF_HI, WORLD_EMITTER_DEFS = 0x1820D4, 0x182164, 0x7D3630
FLIP_LO, FLIP_HI, FLIP_FROZEN = 0x1948E0, 0x194990, 0x194998
TASK_ADD, ASSERT_FAIL, IS_FROZEN = 0x19E4A0, 0x17FD48, 0x1EBDF8
G_CLOCK, G_SLOT_USED, G_TYPES = 0x82CC90, 0x82C408, 0x82C490
G_FREE_HEAD, G_PAGE_DESC, G_PAGES = 0x82C400, 0x82C300, 0x7EC300
G_LISTS, G_LIST_SET, G_GROUPS, GROUP_SIZE = 0x44FA98, 0x44FCA0, 0x7E1D50, 0x138
G_SIM_FRAME, G_COSMETIC_SEED = 0x44FDCC, 0x404460
G_WEATHER_ANGLE, G_WEATHER_ON = 0x4F66A0, 0x4F66A4
G_PARTICLES_OFF, G_GAME_STARTED, G_CUTSCENE = 0x44FA80, 0x4039C0, None
SLOT0_DEF = 0x7E1D00


def wanted(name):
    return OPTIONS['filter'] is None or OPTIONS['filter'].lower() in name.lower()


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-16s %7d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:3]:
            print('        ' + line)
    sys.stdout.flush()


def scaled(count):
    return max(count // 10, 4) if OPTIONS['quick'] else count


def fbits(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def bits_f(u):
    return struct.unpack('<f', struct.pack('<I', u & M32))[0]


def ulps(a, b):
    """Distance in units of the last place between two float bit patterns."""
    def key(u):
        return -(u & 0x7FFFFFFF) if u & 0x80000000 else u
    return abs(key(a) - key(b))


def find_cutscene_flag():
    """g_cutsceneActive as particle_updateTask reads it (the byte at the lb in 0x18fa2c..)."""
    return 0x44FCD0


# ---------------------------------------------------------------------------------------
# The original, prepared
# ---------------------------------------------------------------------------------------

class Game:
    def __init__(self, elf, fpu='ps2'):
        emu = self.emu = EE(elf, fpu_model=fpu)
        emu.record_writes = False
        emu.record_calls = False
        emu.stub(TASK_ADD, ret=0)
        emu.stub(ASSERT_FAIL, function=self._assert)
        self.frozen = 0
        emu.stub(IS_FROZEN, function=lambda e: self.frozen)
        self.spawned = None
        emu.stub(RESOURCE_REF_CTOR, ret=0)
        emu.call(STATIC_INIT, 1, 0xFFFF)          # the C++ static initialiser: list heads
        emu.call(PARTICLE_INIT)
        self.scratch = emu.alloc(0x20)
        emu.mem.w8(G_PARTICLES_OFF, 0)
        emu.mem.w8(G_GAME_STARTED, 1)

    @staticmethod
    def _assert(emu):
        raise EmuError('particle.cc assertion (line %d) at %#x' % (emu.r[5], emu.r[31]))

    def call(self, addr, *args, fargs=(), stack=()):
        emu = self.emu
        sp = emu.r[29] & M32
        for i, v in enumerate(stack):
            emu.mem.w32(sp + 8 * i, v & M32)
        return emu.call(addr, *args, fargs=fargs)

    # -- definitions --
    def def_args(self, a):
        """a: dict of the 16 arguments of particleDef_init."""
        regs = (a['r0'], a['g0'], a['b0'], a['a0'], a['r1'], a['g1'], a['b1'])
        stack = (a['a1'], a['life'], a['kind'], a['tile'], 0)
        return regs, stack, (a['s0'], a['s1'], a['grav'])

    def make_def(self, a, addr=None):
        if addr is None:
            addr = self.emu.alloc(0x50)
        regs, stack, fl = self.def_args(a)
        self.call(DEF_CTOR, addr, *regs, fargs=fl, stack=stack)
        return addr

    def set_def(self, addr, a):
        regs, stack, fl = self.def_args(a)
        self.call(DEF_SET, addr, *regs, fargs=fl, stack=stack)

    def spawn(self, addr, pos, vel, backdate=0.0):
        m = self.emu.mem
        pv = self.scratch
        for i in range(3):
            m.wf32(pv + 4 * i, pos[i])
            m.wf32(pv + 0x10 + 4 * i, vel[i])
        self.call(SPAWN, addr, pv, pv + 0x10, fargs=(backdate,))

    # -- state --
    def page_of(self, desc):
        return (desc - G_PAGE_DESC) // 4

    def read_lists(self, base):
        m = self.emu.mem
        out = []
        for k in range(16):
            lp = base + 16 * k
            first, last, head, tail = (m.u32(lp), m.u32(lp + 4), m.u32(lp + 8), m.u32(lp + 12))
            pages, cells = [], []
            if first:
                d = first
                while True:
                    pages.append(self.page_of(d))
                    if d == last:
                        break
                    d = m.u32(d)
                    if len(pages) > 64:
                        raise EmuError('page chain does not reach the last page')
                # cells from (first, head) to (last, tail)
                pi, c = 0, head
                guard = 0
                while not (pi == len(pages) - 1 and c == tail):
                    pg = pages[pi]
                    rec = m.read(G_PAGES + pg * 0x1000 + c * 16, 16)
                    cells.append((pg, c, struct.unpack('<8h', rec)))
                    c += 1
                    if c & 0x1F == 0x1F:
                        if c == 0xFF and pi != len(pages) - 1:
                            pi, c = pi + 1, 1
                        else:
                            c += 2
                    guard += 1
                    if guard > 64 * 240:
                        raise EmuError('cell walk does not end')
            out.append((tuple(pages), head if first else None, tail if first else None, tuple(cells)))
        return out

    def free_pages(self):
        m = self.emu.mem
        out, d = [], m.u32(G_FREE_HEAD)
        while d:
            out.append(self.page_of(d))
            d = m.u32(d)
            if len(out) > 64:
                raise EmuError('free list loops')
        return out

    def state(self, defs):
        m = self.emu.mem
        s = {'clock': m.s16(G_CLOCK), 'free': tuple(self.free_pages())}
        s['slots'] = tuple(m.u32(G_SLOT_USED + 4 * i) != M32 for i in range(32))
        s['defs'] = tuple((m.s32(a + 4), m.s32(a + 8)) for a in defs)
        s['global'] = self.read_lists(G_LISTS)
        groups = []
        for i in range(16):
            g = G_GROUPS + i * GROUP_SIZE
            h = m.u32(g + 0x130)
            if h:
                mat = tuple(m.u32(g + 0x100 + 4 * j) for j in range(12))
                groups.append((h, m.s32(g + 0x134), mat, self.read_lists(g)))
        s['groups'] = tuple(groups)
        s['set'] = m.u32(G_LIST_SET)
        return s

    def resident_records(self):
        m = self.emu.mem
        return {i: m.read(G_TYPES + 0x40 * i, 0x40) for i in range(32)
                if m.u32(G_SLOT_USED + 4 * i) != M32}


# ---------------------------------------------------------------------------------------
# The model, put in the same form
# ---------------------------------------------------------------------------------------

def def_from_args(a, previous=None):
    return P.ParticleDef.build(a['s0'], a['s1'], a['grav'], (a['r0'], a['g0'], a['b0'], a['a0']),
                               (a['r1'], a['g1'], a['b1'], a['a1']), a['life'], a['kind'],
                               a['tile'], previous=previous)


def def_image(d, addr):
    """The 0x50 bytes the model says particleDef_init leaves (callback 0)."""
    head = struct.pack('<iiii', d.list_index, d.slot, d.live, 0)
    rec = bytearray(d.record())
    struct.pack_into('<I', rec, 0x18, addr)
    return head + bytes(rec)


INT_FIELDS = {0x00, 0x04, 0x08, 0x0C, 0x14, 0x20, 0x24, 0x28}


def compare_def(orig, model, kind):
    """-> (exact integer fields?, worst ulp of the float fields, floats bit-identical, floats)"""
    ints = set(INT_FIELDS)
    if kind != P.KIND_LINE:
        ints.add(0x10)
    ok, worst, same, total = True, 0, 0, 0
    for off in range(0, 0x50, 4):
        a = struct.unpack_from('<I', orig, off)[0]
        b = struct.unpack_from('<I', model, off)[0]
        if off in ints:
            ok = ok and a == b
        else:
            u = ulps(a, b)
            worst = max(worst, u)
            same += u == 0
            total += 1
    return ok, worst, same, total


def random_def_args(rng, kind=None):
    def colour():
        return rng.choice([rng.randint(0, 255), rng.randint(-120, 400), 0, 255, 0x80])
    a = {'s0': rng.choice([rng.uniform(0, 4), rng.uniform(0, 40), 1.0, 0.0]),
         's1': rng.choice([rng.uniform(0, 4), rng.uniform(0, 40), 1.0, 0.0]),
         'grav': rng.choice([0.0, rng.uniform(-60, 60), float(rng.randint(-40, 40))]),
         'r0': colour(), 'g0': colour(), 'b0': colour(), 'a0': colour(),
         'r1': colour(), 'g1': colour(), 'b1': colour(), 'a1': colour(),
         'life': rng.choice([0, 1, 2, 3, rng.randint(-3, 7)]),
         'kind': rng.choice([0, 1, 1, 2, 3, rng.randint(-2, 6)]) if kind is None else kind,
         'tile': rng.randint(0, 255)}
    return a


# ---------------------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------------------

def prop_definition(elf):
    if not wanted('definition'):
        return
    rng = random.Random(OPTIONS['seed'] * 31 + 1)
    g = Game(elf)
    fails, ex, worst, same, total = 0, [], 0, 0, 0
    n = scaled(4000)
    for _ in range(n):
        a = random_def_args(rng)
        addr = g.make_def(a)
        orig = g.emu.mem.read(addr, 0x50)
        d = def_from_args(a)
        ok, w, s, t = compare_def(orig, def_image(d, addr), d.kind)
        worst, same, total = max(worst, w), same + s, total + t
        if not ok or w > 0:
            fails += 1
            ex.append('%r: worst %d ulp, ints %s' % (a, w, ok))
    report('definition', fails, n, 'particleDef_ctor 0x50 bytes vs ParticleDef.build, bit for bit '
           '(worst float %d ulp; %d of %d floats bit-identical)'
           % (worst, same, total), ex)


def prop_redefine(elf):
    if not wanted('redefine'):
        return
    rng = random.Random(OPTIONS['seed'] * 31 + 2)
    g = Game(elf)
    fails, ex = 0, []
    n = scaled(1500)
    for i in range(n):
        a = random_def_args(rng, kind=rng.choice([0, 1, 2, 3]))
        addr = g.make_def(a)
        resident = rng.random() < 0.7
        if resident:
            g.spawn(addr, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        slot = g.emu.mem.s32(addr + 4)
        before = g.emu.mem.read(G_TYPES + 0x40 * slot, 0x40) if slot >= 0 else None
        b = dict(a) if rng.random() < 0.3 else random_def_args(rng, kind=rng.choice([a['kind'] % 4, 0, 1, 2]))
        old = g.emu.mem.read(addr, 0x50)
        g.set_def(addr, b)
        orig = g.emu.mem.read(addr, 0x50)
        prev = def_from_args(a)
        d = def_from_args(b, previous=prev if b['kind'] in (2,) else None)
        if b['kind'] == 2:
            # kind 2 keeps the +0x14 / +0x20 / +0x24 the object held
            d.v0 = struct.unpack_from('<i', old, 0x14)[0]
            d.u1 = struct.unpack_from('<i', old, 0x20)[0]
            d.v1 = struct.unpack_from('<i', old, 0x24)[0]
        d.slot = struct.unpack_from('<i', old, 4)[0]
        d.live = struct.unpack_from('<i', old, 8)[0]
        ok, w, _, _ = compare_def(orig, def_image(d, addr), d.kind)
        good = ok and w == 0
        if slot >= 0:
            after = g.emu.mem.read(G_TYPES + 0x40 * slot, 0x40)
            changed = old != orig
            want = orig[0x10:0x50] if changed else before
            good = good and after == want
        if not good:
            fails += 1
            ex.append('%r -> %r resident %s' % (a, b, resident))
        if i % 25 == 24:
            g = Game(elf)
    report('redefine', fails, n, 'particleDef_set: the 0x50 bytes (kind 2 keeps +0x14/+0x20/+0x24), '
           'and the type-table copy made only when the bytes changed', ex)


def prop_spawn_record(elf):
    if not wanted('spawn record'):
        return
    rng = random.Random(OPTIONS['seed'] * 31 + 3)
    g = Game(elf)
    defs = [g.make_def(random_def_args(rng, kind=rng.choice([0, 1, 2]))) for _ in range(8)]
    models = {}
    fails, ex = 0, []
    n = scaled(6000)
    for i in range(n):
        if i % 200 == 199:
            g.call(RESET_ALL)
        addr = rng.choice(defs)
        mem = g.emu.mem
        clock = rng.randint(-0x8000, 0x7FFF)
        mem.w16(G_CLOCK, clock & 0xFFFF)
        pos = tuple(P.f32(rng.choice([rng.uniform(-3000, 3000), rng.uniform(-40000, 40000),
                                      float(rng.randint(-100, 100)) + 0.5])) for _ in range(3))
        vel = tuple(P.f32(rng.choice([rng.uniform(-30, 30), rng.uniform(-200, 200), 0.0]))
                    for _ in range(3))
        back = rng.choice([0.0, 0.0, rng.uniform(0, 2), -rng.uniform(0, 1), rng.randint(1, 90) / 60.0])
        before = g.read_lists(G_LISTS)
        g.spawn(addr, pos, vel, back)
        after = g.read_lists(G_LISTS)
        k = mem.s32(addr)
        new = [c for c in after[k][3] if c not in before[k][3]]
        if not new:
            fails += 1
            ex.append('no particle written')
            continue
        rec = new[-1][2]
        d = models.get(addr)
        if d is None:
            raw = mem.read(addr, 0x50)
            d = models[addr] = P.ParticleDef()
        d.gravity = bits_f(mem.u32(addr + 0x18))
        slot = mem.s32(addr + 4)
        want = P.spawn_record(d, pos, vel, clock, back, slot)
        if tuple(rec) != tuple(want):
            fails += 1
            ex.append('pos %r vel %r back %r: original %r model %r' % (pos, vel, back, rec, tuple(want)))
    report('spawn record', fails, n, 'particle_spawn record (s16 position, birth, velocity x 256, '
           'slot x 4; back-dating) vs spawn_record, exact', ex)


class PoolCase:
    def __init__(self, elf, rng):
        self.g = Game(elf)
        self.rng = rng
        self.m = P.ParticleSystem()
        self.args = []
        self.addrs = []
        self.models = []
        for _ in range(rng.choice([6, 12, 40])):
            a = random_def_args(rng, kind=rng.choice([0, 1, 2, 3]))
            a['life'] = rng.choice([0, 0, 1, 2, 3])
            self.args.append(a)
            self.addrs.append(self.g.make_def(a))
            self.models.append(def_from_args(a))
        self.cutscene = 0

    def model_state(self):
        m = self.m
        index = {id(d): i for i, d in enumerate(self.models)}
        s = {'clock': P.s16(m.clock), 'free': tuple(m.free_pages)}
        s['slots'] = tuple(x is not None for x in m.slots)
        s['defs'] = tuple((d.slot, d.live) for d in self.models)

        def lists(ls):
            out = []
            for lst in ls:
                if lst.pages:
                    cells = []
                    pages = lst.pages
                    pi, c = 0, lst.head
                    while not (pi == len(pages) - 1 and c == lst.tail):
                        p, d = lst.cells[(pages[pi], c)]
                        cells.append((pages[pi], c, tuple(p)))
                        c += 1
                        if c & 0x1F == 0x1F:
                            if c == 0xFF and pi != len(pages) - 1:
                                pi, c = pi + 1, 1
                            else:
                                c += 2
                    out.append((tuple(pages), lst.head, lst.tail, tuple(cells)))
                else:
                    out.append(((), None, None, ()))
            return out
        s['global'] = lists(m.global_set)
        groups = []
        for h in sorted(m.groups, key=lambda h: h & 0xFF):
            lsts, mat, idle = m.groups[h]
            groups.append((h, idle, tuple(fbits(v) for row in mat for v in row), lists(lsts)))
        s['groups'] = tuple(groups)
        return s

    def orig_state(self):
        s = self.g.state(self.addrs)
        s.pop('set')
        return s


IDENTITY_BITS = tuple(fbits(v) for v in (1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0))


def prop_pools(elf):
    if not wanted('pools'):
        return
    rng = random.Random(OPTIONS['seed'] * 31 + 4)
    fails, ex, ops_total = 0, [], 0
    n = scaled(60)
    for case in range(n):
        c = PoolCase(elf, rng)
        g, m = c.g, c.m
        mem = g.emu.mem
        if rng.random() < 0.3:                      # start just before the s16 wrap
            start = 0x7FFF - rng.randint(0, 120)
            mem.w16(G_CLOCK, start)
            m.clock = start
        handles = []
        current = None
        cut = find_cutscene_flag()
        steps = rng.choice([150, 400, 900])
        bad = None
        for step in range(steps):
            r = rng.random()
            if r < 0.55:
                i = rng.randrange(len(c.addrs))
                pos = tuple(float(rng.randint(-2000, 2000)) for _ in range(3))
                vel = tuple(float(rng.randint(-60, 60)) for _ in range(3))
                burst = rng.choice([1, 1, 1, 5, 40, 300, 300, 4000])
                for _ in range(burst):
                    g.spawn(c.addrs[i], pos, vel)
                    d = c.models[i]
                    no_slot = d.live == 0 and None not in m.slots
                    no_page = m.current[d.list_index].tail == P.CURSOR_FULL and not m.free_pages
                    orphan = m.current is not m.global_set and not any(
                        m.current is grp[0] for grp in m.groups.values())
                    if m.spawn(d, pos, vel) is None:
                        cover('pools: dropped, no free slot' if no_slot else 'pools: dropped, no free page')
                    elif orphan:
                        cover('pools: spawned into a freed group')
                what = 'spawn %d x%d' % (i, burst)
            elif r < 0.85:
                ticks = rng.choice([1, 1, 2, 12, 31, 61, 91])
                incut = rng.random() < 0.05
                mem.w8(cut, 1 if incut else 0)
                for _ in range(ticks):
                    g.call(UPDATE_TASK)
                    before = set(m.groups)
                    wrap = m.clock == 0x7FFF
                    m.update(in_cutscene=bool(incut))
                    cover('pools: groups freed idle', len(before - set(m.groups)))
                    cover('pools: clock wrap with live particles', wrap and any(True for _ in m.live()))
                mem.w8(cut, 0)
                what = 'update x%d%s' % (ticks, ' (cutscene)' if incut else '')
            elif r < 0.90:
                h = g.call(GROUP_CREATE) & M32
                hm = m.group_create()
                if h:
                    handles.append(h)
                what = 'group create %#x / %#x' % (h, hm)
                if h != hm:
                    bad = what
            elif r < 0.94 and handles:
                h = rng.choice(handles)
                g.call(GROUP_BEGIN, h)
                m.group_begin(h)
                current = h
                what = 'group begin %#x' % h
            elif r < 0.97 and current is not None:
                g.call(GROUP_END, current)
                m.group_end(current)
                what = 'group end %#x' % current
                current = None
            elif r < 0.985 and handles:
                h = rng.choice(handles)
                mat = tuple(fbits(rng.uniform(-2, 2)) for _ in range(12))
                p = g.scratch_mat = getattr(g, 'scratch_mat', None) or g.emu.alloc(0x30)
                for j, v in enumerate(mat):
                    mem.w32(p + 4 * j, v)
                g.call(GROUP_SET_MATRIX, h, p)
                m.group_set_matrix(h, [[bits_f(mat[3 * r + k]) for k in range(3)] for r in range(4)])
                what = 'group set matrix %#x' % h
            elif handles:
                h = rng.choice(handles)
                g.call(GROUP_FREE, h)
                m.group_free(h)
                what = 'group free %#x' % h
            else:
                continue
            ops_total += 1
            # the model loses groups the original frees on its own (idle): mirror handles
            handles = [h for h in handles if h in m.groups or any(
                mem.u32(G_GROUPS + i * GROUP_SIZE + 0x130) == h for i in range(16))]
            so, sm = c.orig_state(), c.model_state()
            if so != sm:
                keys = [k for k in so if so[k] != sm[k]]
                bad = 'step %d (%s): differs in %s' % (step, what, ','.join(keys))
            if bad:
                break
        if bad:
            fails += 1
            ex.append('case %d: %s' % (case, bad))
    report('pools', fails, n, '%d operations (spawn bursts to the page and slot limits, ticks, groups, '
           'cutscene ticks, the s16 clock wrap): every list, page, cell, slot, count, group, clock'
           % ops_total, ex)


def prop_emitter_definition(elf):
    if not wanted('emitter definition'):
        return
    rng = random.Random(OPTIONS['seed'] * 31 + 7)
    g = Game(elf)
    e, mem = g.emu, g.emu.mem
    fails, ex = 0, []
    n = scaled(2000)
    rec = e.alloc(0x48)
    for _ in range(n):
        r = P.EmitterRecord.new(start_rgba=tuple(rng.randint(0, 255) for _ in range(4)),
                                end_rgba=tuple(rng.randint(0, 255) for _ in range(4)),
                                size_start=rng.randint(-50, 300), size_end=rng.randint(-50, 300),
                                gravity=rng.randint(-2000, 2000), life_class=rng.randint(0, 6),
                                kind=rng.randint(0, 5), tile=rng.randint(0, 255))
        mem.write(rec, r.pack())
        idx = rng.randrange(16)
        addr = WORLD_EMITTER_DEFS + 0x98 * idx
        mem.write(addr, bytes(0x50))
        mem.w32(addr + 4, M32)
        e.r[18], e.r[17] = rec, idx
        e.r[31] = e.RETURN_ADDR
        e.run(start=FIXUP_DEF_LO, until=[FIXUP_DEF_HI])
        d = P.ParticleDef.from_emitter_record(r)
        d.slot = -1
        ok, w, _, _ = compare_def(mem.read(addr, 0x50), def_image(d, addr), d.kind)
        if not ok or w:
            fails += 1
            ex.append('%r' % (r.pack()[:0x11].hex(),))
    report('emitter definition', fails, n, 'world_fixup 0x1820d4-0x182164 (the level emitter type: '
           'the 17 record bytes to particleDef_set) vs ParticleDef.from_emitter_record, bit for bit', ex)


def prop_flipbook(elf):
    if not wanted('flipbook'):
        return
    rng = random.Random(OPTIONS['seed'] * 31 + 5)
    g = Game(elf)
    mem = g.emu.mem
    fails, ex = 0, []
    n = scaled(3000)
    for i in range(n):
        if i % 50 == 0:
            g.call(RESET_ALL)
            defs = []
            for _ in range(rng.randint(1, 31)):
                a = random_def_args(rng, kind=rng.choice([0, 1]))
                a['tile'] = rng.choice([rng.randint(0, 255), 0x10 + rng.randint(0, 15),
                                        0x20 + rng.randint(0, 15), 0x40 + rng.randint(0, 15)])
                addr = g.make_def(a)
                g.spawn(addr, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
                d = def_from_args(a)
                defs.append((addr, d))
        frame = rng.randint(0, 100000)
        mem.w32(G_SIM_FRAME, frame)
        g.frozen = 1 if rng.random() < 0.05 else 0
        g.emu.run(start=FLIP_LO, until=[FLIP_HI, FLIP_FROZEN])
        for addr, d in defs:
            slot = mem.s32(addr + 4)
            if not g.frozen:
                P.flipbook_step(d, frame)
            rec = mem.read(G_TYPES + 0x40 * slot, 0x40)
            u0, v0 = struct.unpack_from('<ii', rec, 0)
            u1, v1 = struct.unpack_from('<ii', rec, 0x10)
            if (u0, v0, u1, v1) != (d.u0, d.v0, d.u1, d.v1):
                fails += 1
                ex.append('frame %d tile %#x: original %r model %r' % (frame, d.tile, (u0, v0, u1, v1),
                                                                      (d.u0, d.v0, d.u1, d.v1)))
                d.u0, d.v0, d.u1, d.v1 = u0, v0, u1, v1
        g.frozen = 0
    report('flipbook', fails, n, 'particle_draw flipbook step on up to 31 resident records '
           '(rows 1, 2, 4 and others; even and odd g_simFrame; frozen) vs flipbook_step', ex)


def random_emitter(rng):
    def s16r(lo, hi):
        return rng.randint(lo, hi)
    rec = P.EmitterRecord.new(
        rate=rng.choice([1, 2, 5, -1, -3, -7, 0, rng.randint(-20, 20)]),
        off_x=rng.choice([0, s16r(-200, 200)]), off_y=rng.choice([0, s16r(-200, 200)]),
        off_z=rng.choice([0, s16r(-200, 200)]),
        vel=tuple(rng.choice([0, s16r(-60, 60)]) for _ in range(3)),
        yaw=rng.randint(0, 0xFFFF), pitch=rng.choice([0, rng.randint(0, 0xFFFF)]),
        box=tuple(rng.choice([0, rng.randint(0, 400)]) for _ in range(3)),
        spread=rng.choice([0, s16r(-40, 40)]), cone=rng.choice([0, s16r(-0x4000, 0x4000)]),
        on_time=rng.choice([0, 0, rng.randint(1, 200)]), off_time=rng.randint(0, 200),
        flags=rng.choice([0, 0, 1, 2, 3]), next=rng.choice([0, rng.randint(-50, 500)]),
        on=rng.choice([0, 1]), name='fx')
    return rec


def prop_emitter(elf):
    if not wanted('emitter'):
        return
    rng = random.Random(OPTIONS['seed'] * 31 + 6)
    g = Game(elf)
    emu, mem = g.emu, g.emu.mem
    got = []

    def spawn_stub(e):
        m = e.mem
        p = tuple(m.f32(e.r[5] + 4 * i) for i in range(3))
        v = tuple(m.f32(e.r[6] + 4 * i) for i in range(3))
        got.append((e.r[4] & M32, e.fget(12), p, v))
    emu.stub(SPAWN, function=spawn_stub)
    defaddr = g.make_def(random_def_args(rng, kind=1))
    fails, ex, worst, spawned = 0, [], 0.0, 0
    n = scaled(4000)
    recp = emu.alloc(0x48)
    posp = emu.alloc(0x10)
    for _ in range(n):
        rec = random_emitter(rng)
        mem.write(recp, rec.pack())
        pos = tuple(rng.uniform(-3000, 3000) for _ in range(3))
        for i in range(3):
            mem.wf32(posp + 4 * i, pos[i])
        now = rng.randint(0, 100000)
        yaw = rng.choice([0, rng.randint(-0x8000, 0x7FFF)])
        flips = (rng.random() < 0.2, rng.random() < 0.2, rng.random() < 0.2)
        wa, wo = rng.randint(0, 0xFFFF), rng.choice([0, 1])
        mem.w16(G_WEATHER_ANGLE, wa)
        mem.w32(G_WEATHER_ON, wo)
        seed = rng.getrandbits(32)
        mem.w32(G_COSMETIC_SEED, seed)
        got.clear()
        g.call(EMITTER_RUN, posp, defaddr, recp, now, yaw & 0xFFFF, *[int(f) for f in flips])
        after = P.EmitterRecord.parse(mem.read(recp, 0x48))
        r = P.CosmeticRng(seed)
        want = P.emitter_run(rec, pos, now, r, yaw=yaw, neg_x=flips[0], neg_y=flips[1],
                             swap_xy=flips[2], weather_angle=wa, weather_on=bool(wo))
        problem = None
        if (after.next, after.on) != (rec.next, rec.on):
            problem = 'next/on %r vs %r' % ((after.next, after.on), (rec.next, rec.on))
        elif mem.u32(G_COSMETIC_SEED) != r.seed:
            problem = 'seed'
        elif len(got) != len(want):
            problem = '%d spawns vs %d' % (len(got), len(want))
        else:
            for (d, back, p, v), (pm, vm) in zip(got, want):
                if d != defaddr or back != 0.0:
                    problem = 'definition or back-date'
                    break
                for a, b in zip(p + v, pm + vm):
                    err = abs(a - b)
                    tol = 2e-3 * (1.0 + abs(b)) + 0.01 * (abs(rec.off_x) + abs(rec.off_y)) / 100.0
                    worst = max(worst, err / (1.0 + abs(b)))
                    if err > tol + 1e-3 * (sum(abs(c) for c in rec.vel) + max(rec.box)):
                        problem = 'value %r vs %r' % (a, b)
                        break
                if problem:
                    break
            spawned += len(got)
        if problem:
            fails += 1
            ex.append('%s: rate %d flags %d yaw %d now %d' % (problem, rec.rate, rec.flags, yaw, now))
    report('emitter', fails, n, 'emitter_run: count, on/off timer and cosmetic seed exact; %d spawn '
           'positions and velocities within the cos16 tolerance (worst relative %.2g)'
           % (spawned, worst), ex)


# ---------------------------------------------------------------------------------------

def find_elf(positional):
    for p in positional + [os.path.join(ROOT, 'SLUS_209.73')]:
        if p and os.path.isfile(p):
            return p
    return None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    positional = []
    while argv:
        arg = argv.pop(0)
        if arg == '--quick':
            OPTIONS['quick'] = True
        elif arg == '-v':
            OPTIONS['verbose'] = True
        elif arg == '--seed':
            OPTIONS['seed'] = int(argv.pop(0), 0)
        elif arg == '-k':
            OPTIONS['filter'] = argv.pop(0)
        else:
            positional.append(arg)
    elf = find_elf(positional)
    if elf is None:
        print('SKIP  no SLUS_209.73 found (pass its path); nothing was tested')
        return 0
    with open(elf, 'rb') as handle:
        if hashlib.sha256(handle.read()).hexdigest() != EXPECTED_SHA256:
            print('SKIP  %s is not the US v2.00 executable this test was written for' % elf)
            return 0
    started = time.time()
    print('executable %s, seed %d' % (elf, OPTIONS['seed']))
    prop_definition(elf)
    prop_redefine(elf)
    prop_spawn_record(elf)
    prop_pools(elf)
    prop_emitter_definition(elf)
    prop_flipbook(elf)
    prop_emitter(elf)
    if COVER:
        print('reached: ' + '; '.join('%s %d' % kv for kv in sorted(COVER.items())))
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d failed, %.0f s' % (len(RESULTS), len(failed), time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
