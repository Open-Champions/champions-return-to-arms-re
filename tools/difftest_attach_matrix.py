#!/usr/bin/env python3
"""difftest_attach_matrix.py - compare tools/ref_attach_matrix.py with the game's own code:
creature_getAttachMatrix0 0x287940, model_getAttachWorldMatrix 0x175330 under it,
model_getAttachMatrix 0x1795f8 and anim_getJointMatrix 0x16f720 under both; then the held
Soul's burst (Soul_run state 0x1d) with the two matrices real.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_attach_matrix.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                             [--cases N] [--ticks N] [-k TEXT] [-v]
                                             [--trace-first]

Part 1, the bodies alone
    Each entry runs in tools/ee_emu.py with these REAL: the four bodies above and
    tools/ref_core.py's mat34_setIdentity 0x165680, mat34_mul 0x162808, mat3_scale
    0x165cc0 and mat34_setPosRotZScale 0x163cb8 (executed by tools/difftest_core.py).
    anim_buildPose 0x16ed40 is the one recording stub: the script may attach a pose to the
    state it is given, or not.  The same inputs go through ref_attach_matrix.Model on a
    copy-on-write view; equal must be the calls with their arguments, the bytes stored
    outside the stack (the out matrix, what the stub attached), the shared seed 0x404464
    with its draw count (none), the cosmetic seed 0x404460.

    joint     anim_getJointMatrix: states with a pose or none (then anim_buildPose may
              attach one, or the default pose 0x7b8380 is read), joints below 0, inside,
              past the end, poses of 0 to 24 joints
    attach    model_getAttachMatrix: attach headers u8 +0x22 of 2-6, indexes 0-3 and -1,
              joint words of any size, with and without a state, scales 1, 0.5, 2, 0.01, -1, 0
    world     model_getAttachWorldMatrix: the same, plus positions and facings of every width
    creature  creature_getAttachMatrix0 on creatures whose class definition, scale,
              position, facing and anim state vary

Part 2, the held Soul
    tools/difftest_soul_run.py's world and rig, with the two call-outs of state 0x1d made
    REAL (and their bodies, the helpers and anim_buildPose's stub as in part 1): the owner
    (a Minion's place, world.others[1]) gets a class definition, a model with attach
    records, a scale, a facing and an anim state with or without a pose; the held model
    (Soul class definition +0x1c) gets attach records; the Soul's own anim state has a pose
    or none.  The driver keeps the soul in state 0x1d with its owner most of the time and
    answers the animation step with event bit 0 often, so the burst runs through the
    matrices.  ref_attach_matrix.SoulModel is ref_soul_run.Model with the two call-outs as
    bodies.  Compared as tools/difftest_soul_run.py compares.
"""
import hashlib
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError                 # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_ctors as CT                   # noqa: E402
import ref_attach_matrix as AT                  # noqa: E402
import difftest_combat_runtime as D             # noqa: E402
import difftest_creature as DC                  # noqa: E402
import difftest_monsters_1 as DM                # noqa: E402
import difftest_combat_ctors as DT              # noqa: E402
import difftest_soul_run as DSR                 # noqa: E402
from difftest_creature import Res, f32, M32     # noqa: E402

ROOT = D.ROOT
OPTIONS = DC.OPTIONS
OPTIONS.update({'seed': 20973, 'cases': 3000, 'ticks': 1500})
LIB_LO, LIB_HI = D.LIB_LO, D.LIB_HI
is_stack = D.is_stack
G_COSMETIC_SEED = 0x404460

BODIES = {
    'creature_getAttachMatrix0': (0x287940, 0x287998),
    'model_getAttachWorldMatrix': (0x175330, 0x1754A0),
    'model_getAttachMatrix': (0x1795F8, 0x1796DC),
    'anim_getJointMatrix': (0x16F720, 0x16F880),
}
REAL = set(AT.MODELLED.values())

ENTRIES = {
    # key -> (address, argument kinds, method); f: a float register, v: a vector pointer
    'joint': (AT.ANIM_GET_JOINT_MATRIX, 'iio', 'joint_matrix_entry'),
    'attach': (AT.MODEL_GET_ATTACH_MATRIX, 'iiiof', 'attach_matrix_entry'),
    'world': (AT.MODEL_GET_ATTACH_WORLD_MATRIX, 'iviiiof', 'world_matrix_entry'),
    'creature': (AT.CREATURE_GET_ATTACH_MATRIX0, 'io', 'creature_matrix_entry'),
}

SCALES = (1.0, 1.0, 1.0, 0.5, 1.3, 2.0, 0.01, -1.0, 0.0)
JOINT_WORDS = (0, 0, 1, 2, 3, 7, 19, 23, 24, 63, 0xFFFFFFFF, 0x7FFFFFFF, 0x80000000)
HEADERS = (3, 3, 4, 6, 2)


def _matrix(rng, identity=False):
    if identity:
        rot = [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0]
    else:
        rot = [rng.uniform(-1.5, 1.5) for _ in range(9)]
    return [f32(v) for v in rot + [rng.uniform(-120, 120) for _ in range(3)]]


class Geometry:
    """Models with attach records, pose buffers and anim states in the interpreter's
    memory (shared by both parts)."""

    POSE_JOINTS = 24

    def __init__(self, emu):
        self.emu, self.mem = emu, emu.mem
        self.models = [emu.alloc(0x400) for _ in range(3)]
        self.poses = [emu.alloc(0x10 + 0x18 * (self.POSE_JOINTS + 1)) for _ in range(3)]
        self.states = [emu.alloc(0x40) for _ in range(3)]
        self.defs = [emu.alloc(0x40) for _ in range(2)]

    def fill_model(self, model, rng):
        mem = self.mem
        for off in range(0, 0x400, 4):
            mem.w32(model + off, f32(rng.uniform(-2, 2)))
        header = rng.choice(HEADERS)
        for k in range(-1, 6):
            rec = model + 16 * header + 0x34 * k
            if rec < model:
                continue
            mem.w32(rec, rng.choice(JOINT_WORDS) if rng.random() < 0.85 else rng.getrandbits(32))
            for j, word in enumerate(_matrix(rng, rng.random() < 0.15)):
                mem.w32(rec + 4 + 4 * j, word)
        mem.w8(model + 0x22, header)            # last: with header 2 it is a byte of record 0's joint word

    def fill_pose(self, buf, rng, count=None):
        mem = self.mem
        for off in range(0, 0x10 + 0x18 * (self.POSE_JOINTS + 1), 2):
            mem.w16(buf + off, rng.randrange(0x10000) if rng.random() < 0.3 else rng.randrange(-5000, 5000) & 0xFFFF)
        if count is None:
            count = rng.choice((0, 1, 1, 4, 20, self.POSE_JOINTS, 0xFFFB))
        mem.w16(buf + 8, count)

    def fill_default_pose(self, rng):
        if rng.random() < 0.5:
            self.fill_pose(AT.DEFAULT_POSE, rng, rng.choice((0, 1, 6)))
        else:                                                       # what a fresh boot holds
            for off in range(0, 0x10 + 0x18 * 8, 4):
                self.mem.w32(AT.DEFAULT_POSE + off, 0)

    def state_word(self, rng):
        return rng.choice([0, 0] + self.poses)

    def refresh(self, rng):
        for m in self.models:
            self.fill_model(m, rng)
        for p in self.poses:
            self.fill_pose(p, rng)
        for s in self.states:
            self.mem.w32(s, self.state_word(rng))
        self.fill_default_pose(rng)

    def on_anim_buildPose(self, args, view, rng):
        """The pose builder may attach a pose (the state's first word) or leave none."""
        if rng.random() < 0.6:
            view.poke(args[0], 4, rng.choice(self.poses))
        return Res()


# ---------------------------------------------------------------------------------------
# Part 1: the bodies alone
# ---------------------------------------------------------------------------------------
class RealSet:
    def __contains__(self, target):
        return target in REAL or LIB_LO <= target < LIB_HI


class Rig:
    def __init__(self, elf):
        emu = self.emu = EE(elf, fpu_model='ps2')
        emu.div_zero = 'r5900'
        emu.follow = RealSet()
        self.geo = Geometry(emu)
        self.argbuf = emu.alloc(0x100)
        self.outbuf = emu.alloc(0x40)
        self.creatures = [emu.alloc(0x200) for _ in range(2)]
        self.names = {}
        for name, ext in AT.EXTERNALS.items():
            self.names[ext.addr] = name
            emu.stub(ext.addr, function=self.make_stub(name, ext), name=name)
        self.calls, self.unknown, self.pcs = [], {}, set()
        self.eview = D.View(emu.mem.load, self._epoke)
        self.touched = set()
        self.script_rng = None

    def _epoke(self, addr, size, value):
        self.emu.mem.store(addr, size, value & ((1 << (8 * size)) - 1))
        self.touched.update(range(addr, addr + size))

    def make_stub(self, name, ext):
        def stub(emu):
            args = tuple(emu.r[4 + k] & M32 for k in range(len(ext.ints)))
            self.calls.append((name, args))
            self.geo.on_anim_buildPose(args, self.eview, self.script_rng)
            return 0
        return stub

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                self.rig.geo.on_anim_buildPose(args, self.view, self.rng)
                return None
            return answer

    def compare(self, key, args, call_seed):
        addr, kinds, method = ENTRIES[key]
        emu, mem = self.emu, self.emu.mem
        seed_before, cosmetic_before = mem.u32(RC.G_RAND_SEED), mem.u32(G_COSMETIC_SEED)
        mview = D.ModelView(mem)
        model = AT.Model(mview, Rig.Callbacks(self, D.View(mview.load, mview.poke), random.Random(call_seed)))
        margs = [a for a, k in zip(args, kinds) if k != 'f'] + [a for a, k in zip(args, kinds) if k == 'f']
        out = {'fault': None, 'calls': None, 'writes': None, 'seed': None, 'model_calls': model.calls,
               'emu_calls': None}
        scratch = self.argbuf                    # the vector arguments are in place for both sides
        for value, kind in zip(args, kinds):
            if kind == 'v':
                for j in range(3):
                    mem.w32(scratch + 4 * j, value[j])
                scratch += 0x10
        model_error = None
        try:
            getattr(model, method)(*margs)
        except EmuError as exc:
            model_error = exc
        self.calls, self.touched = [], set()
        out['emu_calls'] = self.calls
        self.script_rng = random.Random(call_seed)
        emu.reset_log()
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x800
        regs, scratch, nfloat = [], self.argbuf, 0
        for value, kind in zip(args, kinds):
            if kind == 'v':
                for j in range(3):
                    mem.w32(scratch + 4 * j, value[j])
                regs.append(scratch)
                scratch += 0x10
            elif kind == 'f':
                emu.f[12 + nfloat] = value & M32
                nfloat += 1
            else:
                regs.append(ee_emu.s32(value & M32))
        emu_error = None
        try:
            emu.call(addr, *regs, max_steps=400000)
        except EmuError as exc:
            emu_error = exc
        self.pcs.update(emu.trace)
        for call in emu.calls:
            if call.target not in REAL and call.target not in self.names and not LIB_LO <= call.target < LIB_HI:
                self.unknown[call.target] = self.unknown.get(call.target, 0) + 1
        if model_error or emu_error:
            if (model_error is None) != (emu_error is None):
                out['fault'] = 'model %r / original %r' % (model_error, emu_error)
            return out
        if model.calls != self.calls:
            out['calls'] = DC.describe_calls(model.calls, self.calls)
        lo, hi = self.argbuf, self.argbuf + 0x100
        stored = set()
        for _pc, a, size, _v in emu.writes:
            if not is_stack(a) and not lo <= a < hi:
                stored.update(range(a, a + size))
        mstored = set()
        for a, size, _v in model.writes:
            if not is_stack(a):
                mstored.update(range(a, a + size))
        diff = [a for a in sorted(stored | mstored | self.touched | mview.touched)
                if mem.load(a, 1) != mview.load(a, 1)]
        if stored != mstored or diff:
            out['writes'] = 'only original %s; only model %s; values differ at %s' % (
                sorted('%x' % a for a in stored - mstored)[:8], sorted('%x' % a for a in mstored - stored)[:8],
                ['%x:%02x/%02x' % (a, mem.load(a, 1), mview.load(a, 1)) for a in diff[:8]])
        if model.draws or mem.u32(RC.G_RAND_SEED) != seed_before or mview.load(RC.G_RAND_SEED, 4) != seed_before \
                or mem.u32(G_COSMETIC_SEED) != cosmetic_before:
            out['seed'] = 'a generator moved: model draws %d' % model.draws
        return out


class Coverage(DC.Coverage):
    def __init__(self, mem):
        self.parts = {name: (start, end) + DC.analyse(mem, start, end) for name, (start, end) in BODIES.items()}
        self.pcs = set()


def _scale(rng):
    return f32(rng.choice(SCALES)) if rng.random() < 0.9 else f32(rng.uniform(-3, 3))


def _pos(rng):
    return tuple(f32(rng.uniform(-4000, 4000)) for _ in range(3))


def _facing(rng):
    return rng.choice((0, 0x4000, 0xC000, 0x8000, 0xFFFF, rng.randrange(0x10000), 0xFFFF8000 | rng.randrange(0x8000),
                       rng.getrandbits(32)))


def _index(rng):
    return rng.choice((0, 0, 0, 1, 2, 3, 0xFFFFFFFF))


def generate(rig, key, rng):
    geo, mem = rig.geo, rig.emu.mem
    mem.w32(RC.G_RAND_SEED, rng.getrandbits(32))
    mem.w32(G_COSMETIC_SEED, rng.getrandbits(32))
    if rng.random() < 0.25:
        geo.refresh(rng)
    for s in geo.states:
        if rng.random() < 0.3:
            mem.w32(s, geo.state_word(rng))
    state = rng.choice(geo.states) if rng.random() < 0.8 else 0
    model = rng.choice(geo.models)
    if key == 'joint':
        joint = rng.choice((0, 1, 3, 19, 23, 24, 25, 100, 0xFFFFFFFF, 0x80000000, 0x7FFFFFFF, rng.randrange(30)))
        return (rng.choice(geo.states), joint, rig.outbuf)
    if key == 'attach':
        return (model, state, _index(rng), rig.outbuf, _scale(rng))
    if key == 'world':
        return (model, _pos(rng), _facing(rng), state, _index(rng), rig.outbuf, _scale(rng))
    c = rng.choice(rig.creatures)
    d = rng.choice(geo.defs)
    mem.w32(d + 0xC, model)
    mem.w32(c + 0x24, d)
    mem.w32(c + 0xDC, _scale(rng))
    for j, v in enumerate(_pos(rng)):
        mem.w32(c + 0x10 + 4 * j, v)
    mem.w16(c + 0x38, rng.randrange(0x10000))
    mem.w32(c + 0x114, geo.state_word(rng))
    return (c, rig.outbuf)


def part1(elf, coverage):
    rig = Rig(elf)
    rng = random.Random(OPTIONS['seed'])
    rig.geo.refresh(rng)
    cases = max(OPTIONS['cases'] // 10, 1) if OPTIONS['quick'] else OPTIONS['cases']
    counts, total = {}, 0
    for key in ENTRIES:
        if OPTIONS['filter'] and OPTIONS['filter'] not in key:
            continue
        bad = {'fault': [], 'calls': [], 'writes': [], 'seed': []}
        for n in range(cases):
            call_seed = OPTIONS['seed'] * 1000003 + total
            case = generate(rig, key, rng)
            result = rig.compare(key, case, call_seed)
            total += 1
            failed = False
            for prop in bad:
                if result[prop]:
                    failed = True
                    bad[prop].append('case %d %s: %s' % (n, key, result[prop]))
            if failed and OPTIONS['trace_first']:
                print('first mismatch: %s case %d %s' % (key, n, case))
                for prop in bad:
                    if result[prop]:
                        print('  %s: %s' % (prop, result[prop]))
                print('  model calls:', [DC.fmt_call(c) for c in result['model_calls']])
                print('  original calls:', [DC.fmt_call(c) for c in result['emu_calls'] or ()])
                sys.exit(1)
        counts[key] = (cases, sum(len(v) for v in bad.values()))
        for prop, examples in bad.items():
            DC.report('attach/%s %s' % (key, prop), len(examples), cases, prop, examples)
    if rig.unknown:
        DC.report('attach unknown calls', len(rig.unknown), total, 'calls to neither real nor stubbed addresses',
                  ['%x x%d' % kv for kv in sorted(rig.unknown.items())])
    coverage.pcs |= rig.pcs
    return counts


# ---------------------------------------------------------------------------------------
# Part 2: the held Soul, state 0x1d, with the two matrices real
# ---------------------------------------------------------------------------------------
DSR.REAL.update(REAL)
SOUL_ENTRIES = dict(DSR.ENTRIES)
_SoulRunWorld = DSR.World


class SoulWorld(_SoulRunWorld):
    def build(self, rng):
        _SoulRunWorld.build(self, rng)
        self.geo = Geometry(self.emu)
        self.geo.refresh(rng)
        self.held_model = self.geo.models[2]
        self.mem.w32(CT.DEF_SOUL + 0x1C, self.held_model)     # a real block instead of the fake 0xc00080

    def setup_owner(self, rng, fresh):
        """The Minion's place: class definition -> model, scale, position, facing, pose."""
        geo, mem = self.geo, self.mem
        owner = self.others[1]
        if fresh:
            geo.refresh(rng)
        d = geo.defs[0]
        mem.w32(d + 0xC, rng.choice(geo.models[:2]))
        mem.w32(owner + 0x24, d)
        mem.w32(owner + 0xDC, f32(rng.choice((1.0, 1.0, 0.8, 1.2, 2.0))))
        mem.w16(owner + 0x38, rng.randrange(0x10000))
        mem.w32(owner + 0x114, geo.state_word(rng))
        mem.w32(self.C + 0x114, geo.state_word(rng))

    def on_anim_buildPose(self, args, view, rng):
        return self.geo.on_anim_buildPose(args, view, rng)

    def on_anim_advance(self, args, view, rng):
        res = _SoulRunWorld.on_anim_advance(self, args, view, rng)
        if rng.random() < 0.5:
            res.ret |= 1                                        # the burst's event bit
        return res


class SoulRig(DSR.Rig):
    def __init__(self, elf, seed, kind, machine, net):
        saved = DSR.World
        DSR.World = SoulWorld
        try:
            DSR.Rig.__init__(self, elf, seed, kind, machine, net)
        finally:
            DSR.World = saved
        ext = AT.EXTERNALS['anim_buildPose']
        self.names[ext.addr] = 'anim_buildPose'
        self.emu.stub(ext.addr, function=self.make_stub('anim_buildPose', ext), name='anim_buildPose')
        self.attach_calls = {AT.CREATURE_GET_ATTACH_MATRIX0: 0, AT.MODEL_GET_ATTACH_MATRIX: 0}
        for a in self.attach_calls:
            self.emu.hook(a, self.counter(a))

    def counter(self, a):
        def note(emu):
            self.attach_calls[a] += 1
        return note

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                if name == 'anim_buildPose':
                    return None
                ret = res.ret & (RC.M64 if AT.SOUL_EXTERNALS[name].ret == 'q' else M32)
                return DSR.SR.shape_result(name, args, ret, res.f & M32, res.outs)
            return answer

    def compare(self, key, args, call_seed, trace=None):
        saved = DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks
        DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks = SOUL_ENTRIES, AT.SoulModel, SoulRig.Callbacks
        try:
            return DM.Rig.compare(self, key, args, call_seed, trace)
        finally:
            DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks = saved


def part2(elf, coverage, seed, machine, ticks, stats):
    rig = SoulRig(elf, seed, 'soul', machine, 1)
    driver = DSR.Driver(rig)
    world, mem, rng = rig.world, rig.emu.mem, rig.rng
    info = DT.CLASSES['soul']
    c = world.C
    owner_node = world.nodes[world.others[1]]
    bad = {'calls': [], 'writes': [], 'seed': [], 'result': [], 'fault': []}
    serial = [0]
    tick = [0]

    def do(key, *args):
        serial[0] += 1
        state = mem.s16(c + 0x232)
        result = rig.compare(key, tuple(args), seed * 1000003 + serial[0], trace=coverage.pcs)
        row = stats.setdefault(key, [0, 0])
        row[0] += 1
        if key == 'Soul_run' and state == 0x1D:
            stats['_1d'] = stats.get('_1d', 0) + 1
        failed = False
        for prop in bad:
            if result[prop]:
                failed = True
                bad[prop].append('tick %d %s state %#x: %s' % (tick[0], key, state & 0xFFFF, result[prop]))
        if failed:
            row[1] += 1
            if OPTIONS['trace_first']:
                print('first mismatch, tick %d, %s state %#x' % (tick[0], key, state & 0xFFFF))
                for prop in bad:
                    if result[prop]:
                        print('  %s: %s' % (prop, result[prop]))
                print('  model calls:')
                for call in result['model_calls']:
                    print('    ' + DC.fmt_call(call))
                print('  original calls:')
                for call in result['emu_calls']:
                    print('    ' + DC.fmt_call(call))
                sys.exit(1)
        return result

    def construct():
        world.clear_creature()
        pos = (f32(2000.0 + rng.uniform(-50, 50)), f32(3000.0 + rng.uniform(-50, 50)), f32(10.0))
        facing = rng.randrange(0x10000)
        values = {'c': c, 't': rng.choice(world.type_names), 'v': pos, 'f': facing, 'p': world.props,
                  'x': world.others[1]}
        do('Soul_ctor', *[values[k] for k in info['order']])

    for t in range(ticks):
        tick[0] = t
        r = rng.random
        if driver.need_ctor:
            driver.need_ctor = False
            construct()
        driver.between()
        if driver.need_ctor:
            continue
        driver.between_class()
        world.setup_owner(rng, r() < 0.05)
        if r() < 0.8:                                            # held, bursting
            mem.w16(c + 0x232, 0x1D)
            mem.w32(c + 0x3C8, owner_node if r() < 0.9 else 0)
            mem.w32(c + 0xC, mem.u32(c + 0xC) & ~2)
        do('Soul_run', c)
        if mem.u32(c + 0xC) & 2 and r() < 0.5 or r() < 0.02:
            construct()
    for prop, examples in bad.items():
        DC.report('soul0x1d/%s %s' % ('B' if machine else 'A', prop), len(examples), serial[0], prop,
                  examples)
    if rig.unknown:
        DC.report('soul0x1d unknown calls', len(rig.unknown), serial[0], 'calls to neither real nor stubbed addresses',
                  ['%x x%d' % kv for kv in sorted(rig.unknown.items())])
    for a, n in rig.attach_calls.items():
        stats.setdefault('_attach', {})
        stats['_attach'][a] = stats['_attach'].get(a, 0) + n
    return serial[0]


def main(argv):
    args, elf = list(argv), None
    while args:
        item = args.pop(0)
        if item == '--quick':
            OPTIONS['quick'] = True
        elif item == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif item == '--cases':
            OPTIONS['cases'] = int(args.pop(0), 0)
        elif item == '--ticks':
            OPTIONS['ticks'] = int(args.pop(0), 0)
        elif item == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif item == '-v':
            OPTIONS['verbose'] = True
        elif item == '--trace-first':
            OPTIONS['trace_first'] = True
        else:
            elf = item
    if elf is None:
        for candidate in (os.path.join(ROOT, 'SLUS_209.73'), os.path.join(ROOT, 'local', 'SLUS_209.73')):
            if os.path.exists(candidate):
                elf = candidate
                break
    if elf is None or not os.path.exists(elf):
        print('difftest_attach_matrix: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != D.EXPECTED_SHA256:
        print('difftest_attach_matrix: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    RC.C.set_fpu('ps2')
    started = time.time()
    probe = EE(elf, fpu_model='ps2')
    coverage = Coverage(probe.mem)
    counts = part1(elf, coverage)
    ticks = max(OPTIONS['ticks'] // 10, 1) if OPTIONS['quick'] else OPTIONS['ticks']
    stats, total2 = {}, 0
    if not OPTIONS['filter'] or 'soul' in OPTIONS['filter']:
        for index, machine in enumerate((0, 1)):
            total2 += part2(elf, coverage, OPTIONS['seed'] + index, machine, ticks, stats)
    print()
    print('part 1: cases per entry / with any mismatch')
    for key, (n, bad_n) in counts.items():
        print('  %-10s %6d / %d' % (key, n, bad_n))
    attach = stats.pop('_attach', {})
    in_1d = stats.pop('_1d', 0)
    print('part 2: calls per entry / with any mismatch: %s' % ', '.join(
        '%s %d / %d' % (k, v[0], v[1]) for k, v in sorted(stats.items())))
    print('  Soul_run entered in state 0x1d: %d; creature_getAttachMatrix0 ran %d times, model_getAttachMatrix %d'
          % (in_1d, attach.get(AT.CREATURE_GET_ATTACH_MATRIX0, 0), attach.get(AT.MODEL_GET_ATTACH_MATRIX, 0)))
    print('coverage of the original as executed here (basic blocks, instructions):')
    for part in BODIES:
        b, bt, i, it = coverage.numbers(part)
        print('  %-28s blocks %4d of %4d  instructions %4d of %4d' % (part, b, bt, i, it))
        if OPTIONS['verbose'] and b != bt:
            print('      never entered: %s' % ' '.join('%06x' % a for a in coverage.missing(part)))
    print('%d + %d calls compared in %.0f s' % (sum(n for n, _b in counts.values()), total2, time.time() - started))
    return 0 if all(ok for _name, ok in DC.RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
