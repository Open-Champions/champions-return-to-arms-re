#!/usr/bin/env python3
"""difftest_combat_round5.py - compare the bodies tools/ref_combat_round5.py adds with the
game's own code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_combat_round5.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                             [--cases N] [-k TEXT]

For each entry the original runs in tools/ee_emu.py (an instruction interpreter, not a
console).  The same inputs go through ref_combat_round5.  Equal must be: calls outside
the model, in order, with arguments; bytes stored outside the stack; the result.  The
angle entries compare the register math_cos16 and math_sin16 receive.  Floats are
32-bit patterns.

Real: the entry, and — where the entry's own work is the subject — the sample-point
and joint-matrix calls, the two sine functions, and the two generators.  Everything
else is a recording stub answered the same way on both sides.  Round 1-4 modules are
not modified.
"""
import hashlib
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError                 # noqa: E402
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_round4 as R4                  # noqa: E402
import ref_combat_round5 as R5                  # noqa: E402
import difftest_combat_runtime as D             # noqa: E402
import difftest_creature as DC                  # noqa: E402

EXPECTED_SHA256 = D.EXPECTED_SHA256
M32 = 0xFFFFFFFF
LIB_LO, LIB_HI = 0x3A5000, 0x3C01A8
f32 = D.f32
is_stack = D.is_stack
Ext = RC.Ext

OPTIONS = {'quick': False, 'seed': 20973, 'cases': 8, 'filter': None}

COS, SIN, RAND = 0x166630, 0x1666E0, 0x1509D0
DAMAGE, SPARKS = 0x110D30, 0x1B9658
SAMPLE, COUNT, JOINT = 0x178E18, 0x1799C8, 0x16F720
BUILD_POSE = 0x16ED40
FN_MODEL, FN_STAT, FN_VIRT, FN_GET = 0x3E0100, 0x3E0120, 0x3E0200, 0x3E0300
BOX, RTTI = R5.BOX_QUERY, R5.RTTI_EQUALS

OFFSET = (0x110E60, 0x110E80)
METAL = (0x11110C, 0x11111C)
BLOCK = (0x1B97DC, 0x1B9800)

FADE, BANK = 0x2385DC, 0x238448
QUEEN, SKELETON, SOUL = 0x236F78, 0x2A6864, 0x2A9870
DEMON, VOLLEY, ABSORB = 0x2AB2B4, 0x2DA2BC, 0x2E8534

BODY = {
    'fadeBank': (FADE, 0x238654),
    'updateBank': (BANK, FADE),
    'holySample': (ABSORB, 0x2E886C),
    'multifire': (VOLLEY, 0x2DA550),
    'hitAngle': (DAMAGE, 0x1124DC),
    'metalAngle': (DAMAGE, 0x1124DC),
    'gibAngle': (DAMAGE, 0x1124DC),
    'blockAngle': (SPARKS, 0x1B9CB8),
    'demonNear': (DEMON, 0x2AB39C),
    'antQueen': (QUEEN, 0x2378F4),
    'skeleton': (SKELETON, 0x2A7508),
    'soulPhase': (SOUL, 0x2AA908),
}


def wanted(key):
    text = OPTIONS['filter']
    return not text or text.lower() in key.lower()


def zero(mem, addr, size):
    for off in range(0, size, 4):
        mem.w32(addr + off, 0)


def plant_pose(mem, pose, joints):
    zero(mem, pose, 0x10 + 24 * len(joints))
    mem.w16(pose + 8, len(joints))
    for joint, rows in enumerate(joints):
        for row, cols in enumerate(rows):
            for col, value in enumerate(cols):
                mem.w16(pose + 0x10 + joint * 24 + row * 8 + col * 2, value & 0xFFFF)


def ident(tx=0, tz=0):
    rows = [[0, 0, 0, 0] for _ in range(3)]
    for row in range(3):
        rows[row][row] = 0x1000
    rows[0][3] = tx
    rows[2][3] = tz
    return rows


def plant_points(mem, model, points):
    zero(mem, model, 0x100)
    mem.w8(model + 0x24, 6)
    mem.w32(model + 0x64, len(points))
    for index, point in enumerate(points):
        addr = model + 0x80 + 8 * index
        for col, value in enumerate(point):
            mem.w16(addr + 2 * col, value & 0xFFFF)


class Follow:
    def __init__(self, addrs):
        self.addrs = set(addrs)

    def __contains__(self, target):
        return target in self.addrs or LIB_LO <= target < LIB_HI


def load_spans(path):
    found = {}
    for line in open(path, encoding='latin1'):
        parts = line.rstrip('\n').split('\t')
        if len(parts) < 3:
            continue
        spans = []
        for piece in parts[2].split(','):
            lo, hi = piece.split('-')
            spans.append((int(lo, 16), int(hi, 16) + 1))
        found[int(parts[0], 16)] = spans
    return found


def jals_in(mem, spans):
    found = []
    for lo, hi in spans:
        pc = lo
        while pc + 4 <= hi:
            word = mem.load(pc, 4)
            if (word >> 26) == 3:
                found.append(((pc & 0xF0000000) | ((word & 0x03FFFFFF) << 2)) & M32)
            pc += 4
    return found


def closure(mem, roots, spans, stop):
    out, stack = set(), list(roots)
    while stack:
        addr = stack.pop() & M32
        if addr in out or addr in stop or not addr:
            continue
        out.add(addr)
        for target in jals_in(mem, spans.get(addr, ())):
            stack.append(target)
    return out


def shape(ext, res):
    if ext is None or ext.ret == 'n':
        return None
    if ext.ret == 'f':
        return res.f & M32
    return res.ret & M32


class Res:
    def __init__(self, ret=0, f=0, outs=()):
        self.ret, self.f, self.outs = ret, f, list(outs)


EXTS = {
    'particle_spawn': Ext(0x18F3F8, 'pvv', 1, 'n'),
    'obj_moveAndCollide': Ext(0x1509F8, 'pv', 0, 'i'),
    'trail_addPoint': Ext(0x192550, 'pv', 0, 'n'),
    'MultiFireProjectile_end': Ext(0x2DA928, 'pi', 0, 'n'),
    'pool_new': Ext(0x14FDB8, 'i', 0, 'i'),
    'Creature.v16': Ext(FN_MODEL, 'p', 0, 'i'),
    'Skill.v10': Ext(FN_STAT, 'pii', 0, 'i'),
    'particleGroup_begin': Ext(0x18E958, 'i', 0, 'n'),
    'particleGroup_end': Ext(0x18E9A0, 'i', 0, 'n'),
}
_LIGHT = Ext(0x201BD8, 'ivii', 8, 'n')
_LIGHT.stack = 4
EXTS['LightEffect_ctor'] = _LIGHT


class World:
    def __init__(self, emu):
        self.emu, self.mem = emu, emu.mem
        self.block = emu.alloc(0xC0)
        self.spell, self.caster = emu.alloc(0x40), emu.alloc(0x160)
        self.skill, self.model = emu.alloc(0x80), emu.alloc(0x100)
        self.pose = emu.alloc(0x80)
        self.vt_caster, self.vt_skill = emu.alloc(0x90), emu.alloc(0x60)
        self.mem.w32(self.vt_caster + 0x84, FN_MODEL)
        self.mem.w32(self.vt_skill + 0x54, FN_STAT)
        self.bolt = emu.alloc(0x100)
        self.queen = emu.alloc(0x420)
        self.classdef = emu.alloc(0x100)
        self.give = True
        self.stat = 0
        self.collide = 0

    def respond(self, name, args, _view, _rng):
        if name == 'obj_moveAndCollide':
            return Res(self.collide)
        if name == 'pool_new':
            return Res(self.block if self.give else 0)
        if name == 'Creature.v16':
            return Res(self.model)
        if name == 'Skill.v10':
            return Res(self.stat)
        return Res()


class Rig:
    def __init__(self, elf, spans):
        emu = self.emu = EE(elf, fpu_model='ps2')
        emu.div_zero = 'r5900'
        self.world = World(emu)
        stop = {BUILD_POSE} | {ext.addr for ext in EXTS.values() if ext.addr}
        roots = (SAMPLE, COUNT, JOINT, R4.SPELL_RAND, RAND)
        self.sample = closure(emu.mem, roots, spans, stop)
        self.names = {}
        for name, ext in EXTS.items():
            if not ext.addr or ext.addr in self.sample:
                continue
            self.names[ext.addr] = name
            emu.stub(ext.addr, function=self.make_stub(name, ext), name=name)
        self.calls, self.pcs = [], set()
        self.script_rng = None

    def stored_bytes(self):
        out = set()
        for pc, addr, size, _value in self.emu.writes:
            if LIB_LO <= pc < LIB_HI or is_stack(addr):
                continue
            out.update(range(addr, addr + size))
        return out

    def decode(self, ext, emu):
        mem, canon, outs = emu.mem, [], []
        for index, kind in enumerate(ext.ints):
            reg = emu.r[4 + index] & M32
            if kind == 'v':
                canon.append(tuple(mem.u32(reg + 4 * col) for col in range(3)))
            elif kind in 'OW':
                canon.append(1 if reg else 0)
                outs.append((kind, reg))
            else:
                canon.append(reg)
        for index in range(ext.floats):
            canon.append(emu.f[12 + index] & M32)
        sp = emu.r[29] & M32
        for index in range(getattr(ext, 'stack', 0)):
            canon.append(mem.u32(sp + 8 * index))
        return tuple(canon), outs

    def make_stub(self, name, ext):
        def stub(emu):
            canon, _outs = self.decode(ext, emu)
            self.calls.append((name, canon))
            res = self.world.respond(name, canon, None, self.script_rng)
            if ext.ret == 'f':
                emu.f[0] = res.f & M32
            return res.ret
        return stub

    class Callbacks:
        def __init__(self, rig):
            self.rig = rig

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, None, self.rig.script_rng)
                return shape(EXTS.get(name), res)
            return answer

    def compare(self, addr, method, args, follow, limit, ret_kind):
        emu, mem = self.emu, self.emu.mem
        mview = D.ModelView(mem)
        cls = {'holy_shield_sample': R5.ShieldPoints, 'multifire_run': R5.VolleyModel}.get(
            method, R5.QueenModel)
        model = cls(mview, Rig.Callbacks(self))
        try:
            mret = getattr(model, method)(*args)
        except EmuError as exc:
            return 'model stopped: %s' % exc
        self.calls = []
        emu.reset_log()
        emu.trace = []
        emu.follow = Follow(follow)
        emu.r[29] = emu.stack_hi - 0x8000
        try:
            eret = emu.call(addr, *(value & M32 for value in args), max_steps=limit)
        except EmuError as exc:
            return 'original stopped: %s' % exc
        self.pcs.update(emu.trace)
        unknown = {}
        for call in emu.calls:
            target = call.target
            if target in follow or target in self.names or LIB_LO <= target < LIB_HI:
                continue
            unknown[target] = unknown.get(target, 0) + 1
        problems = []
        if unknown:
            problems.append('unknown calls %s' % sorted('%x' % item for item in unknown))
        if BUILD_POSE in {call.target for call in emu.calls}:
            problems.append('sample built a pose; the caster had none')
        if model.calls != self.calls:
            problems.append(DC.describe_calls(model.calls, self.calls))
        stored = self.stored_bytes()
        mstored = set()
        for at, size, _value in model.writes:
            if not is_stack(at):
                mstored.update(range(at, at + size))
        diff = [at for at in sorted(stored | mstored | mview.touched)
                if mem.load(at, 1) != mview.load(at, 1)]
        if stored != mstored or diff:
            problems.append('writes: only original %s; only model %s; values differ at %s' % (
                sorted('%x' % at for at in stored - mstored)[:8],
                sorted('%x' % at for at in mstored - stored)[:8],
                ['%x:%02x/%02x' % (at, mem.load(at, 1), mview.load(at, 1)) for at in diff[:8]]))
        if ret_kind == 'f' and (emu.f[0] & M32) != ((mret or 0) & M32):
            problems.append('result %08x / %08x' % (emu.f[0] & M32, (mret or 0) & M32))
        if ret_kind == 'i' and (eret & M32) != ((mret or 0) & M32):
            problems.append('result %08x / %08x' % (eret & M32, (mret or 0) & M32))
        return problems


def cover(pcs, key):
    start, end = BODY[key]
    return len({pc for pc in pcs if start <= pc < end}), (end - start) // 4


class AngleRun:
    def __init__(self, elf):
        emu = self.emu = EE(elf, fpu_model='ps2')
        emu.div_zero = 'r5900'
        emu.follow = Follow({COS, SIN, RAND})
        self.vt = emu.alloc(0x200, fill=0)
        emu.stub(FN_VIRT, ret=0, name='v')
        for slot in range(48):
            emu.mem.w32(self.vt + 8 * slot + 4, FN_VIRT)
        self.block = emu.alloc(0x280, fill=0)
        emu.stub(0x14FDB8, function=lambda _emu: self.block, name='pool')
        self.creature = emu.alloc(0x500, fill=0)
        self.player = emu.alloc(0x600, fill=0)
        self.pcs = set()
        emu.mem.w32(RC.G_NUM_PLAYERS, 0)
        emu.mem.w32(RC.G_DECAL_DETAIL, 0)
        emu.mem.w8(RC.G_NETWORK_MODE, 0)

    def go(self, addr, args, limit=400000):
        emu = self.emu
        emu.reset_log()
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x4000
        try:
            emu.call(addr, *args, max_steps=limit)
        except EmuError as exc:
            return str(exc)
        self.pcs.update(emu.trace)
        return None

    def angles(self):
        return [(call.site, call.args[0] & M32) for call in self.emu.calls if call.target in (COS, SIN)]


def hit_cases(run):
    run.pcs.clear()
    problems = []
    mem, creature = run.emu.mem, run.creature
    for hit, radius in ((0, 0x42200000), (1, 0x42200000), (0x8000, 0x41C80000),
                        (0x7FFF, 0x41C80000), (0x4000, 0x42200000)):
        zero(mem, creature, 0x400)
        mem.w32(creature + 0x48, run.vt)
        mem.w32(creature + 0xC8, 0x3F800000)
        mem.w32(creature + 0x228, 0x3F800000)
        mem.w16(creature + 0x232, 0x12)
        mem.w32(creature + 0x2DC, 1)
        mem.w16(creature + 0x2E0, hit)
        mem.w32(creature + 0x1C, radius)
        stopped = run.go(DAMAGE, (creature, 0))
        got = [] if stopped else run.angles()
        expect = [(site, R5.hit_effect_angle(hit)) for site in OFFSET]
        if stopped or got != expect:
            problems.append('hit %04x: %s got %s' % (hit, stopped or '', got))
            if len(problems) >= 3:
                break
    return problems


def metal_cases(run):
    run.pcs.clear()
    problems = []
    mem, creature = run.emu.mem, run.creature
    facings = (0x1234, 0, 0x8000) if OPTIONS['quick'] else (0x1234, 0, 0x8000, 0xC000, 0x7FFF)
    for facing in facings:
        zero(mem, creature, 0x400)
        mem.w32(creature + 0x48, run.vt)
        mem.w32(creature + 0xC8, 0x3F800000)
        mem.w32(creature + 0x228, 0x3F800000)
        mem.w16(creature + 0x232, 0x12)
        mem.w32(creature + 0x2DC, 1)
        mem.w32(creature + 0xA8, 0x20000)
        mem.w16(creature + 0x38, facing)
        mem.w32(creature + 0x44, 1)
        stopped = run.go(DAMAGE, (creature, 0), 400000)
        got = [] if stopped else run.angles()
        expect = [(site, R5.facing_angle(facing)) for site in METAL]
        if stopped or got != expect:
            problems.append('facing %04x: %s got %s' % (facing, stopped or '', got))
    return problems


def gib_cases(run):
    run.pcs.clear()
    problems = []
    mem, creature = run.emu.mem, run.creature
    for seed, hit in ((0x12345678, 0x100), (1, 0), (0xABCDEF, 0x8000), (7, 0x7FFF)):
        zero(mem, creature, 0x400)
        mem.w32(creature + 0x48, run.vt)
        mem.w32(creature + 0xC8, 0x3F800000)
        mem.w32(creature + 0x228, 0)
        mem.w32(creature + 0x2DC, 0x40800)
        mem.w16(creature + 0x2E0, hit)
        mem.w32(creature + 0x44, seed)
        mem.w32(creature + 0xA8, 0x1000)
        mem.w32(creature + 0xAC, 1)
        stopped = run.go(DAMAGE, (creature, 0), 400000)
        expect, seed2 = R5.gib_angles(seed, hit)
        got_pairs = [] if stopped else run.angles()
        got = [value for site, value in got_pairs]
        expect_sites = [0x111B44, 0x111B64] * 2 + [0x111CE4, 0x111D04] * 4
        if not stopped and [site for site, _value in got_pairs] != expect_sites:
            problems.append('seed %08x sites %s' % (seed, [hex(site) for site, _value in got_pairs]))
            continue
        if stopped or got != expect or mem.u32(creature + 0x44) != seed2:
            problems.append('seed %08x hit %04x: %s n=%s seed %08x' % (
                seed, hit, stopped or '', len(got), mem.u32(creature + 0x44)))
    return problems


def block_cases(run):
    run.pcs.clear()
    problems = []
    mem, player = run.emu.mem, run.player
    facings = (0xC000, 0x8000) if OPTIONS['quick'] else (0, 0x1234, 0x8000, 0xC000, 0x7FFF)
    for facing in facings:
        zero(mem, player, 0x560)
        mem.w16(player + 0x38, facing)
        mem.w32(player + 0x44, 3)
        stopped = run.go(SPARKS, (player, 0), 400000)
        got = [] if stopped else run.angles()
        expect = [(site, R5.facing_angle(facing)) for site in BLOCK]
        if stopped or got != expect:
            problems.append('facing %04x: %s got %s' % (facing, stopped or '', got))
    return problems


def queen_plant(mem, creature, classdef, count, half, clips, vel=0, pos=0):
    zero(mem, creature, 0x420)
    zero(mem, classdef, 0x100)
    mem.w32(creature + 0x24, classdef)
    for off, word in zip(R5.BANK_CLIPS, (0x11, 0x22, 0x33, 0x44)):
        mem.w32(classdef + off, word)
    mem.w16(creature + 0x110, half & 0xFFFF)
    mem.w8(creature + 0x118, count & 0xFF)
    mem.w32(creature + 0x3E0, vel)
    mem.w32(creature + 0x3DC, pos)
    for index, clip in enumerate(clips):
        mem.w32(creature + 0x11C + 32 * index, clip)


def bank_cases(rig, rng):
    rig.pcs.clear()
    w = rig.world
    fixed = (
        (2, 0, (0x11, 0x33), 0, 0),
        (2, 100, (0x11, 0x33), 0, 0),
        (2, -100 & 0xFFFF, (0x11, 0x33), 0, 0),
        (2, 0x7FFF, (0x22, 0x44), 0, 0),
        (2, 0x8000, (0x11, 0x44), 0, 0),
        (0, 100, (), 0, 0),
        (0xFF, 50, (0x11,), 0, 0),
        (4, 200, (0x11, 0x22, 0x33, 0x44), 0x3F000000, 0xBF000000),
        (1, 100, (0x55,), 0, 0),          # both pairs alias; the first match wins
    )
    out = []
    for count, half, clips, vel, pos in fixed:
        if clips == (0x55,):
            w.mem.w32(w.classdef + 0xB4, 0x55)
            w.mem.w32(w.classdef + 0xBC, 0x55)
        queen_plant(w.mem, w.queen, w.classdef, count, half, clips, vel, pos)
        if clips == (0x55,):
            w.mem.w32(w.classdef + 0xB4, 0x55)
            w.mem.w32(w.classdef + 0xBC, 0x55)
            w.mem.w32(w.queen + 0x11C, 0x55)
        out.append(rig.compare(BANK, 'update_bank', (w.queen,), {BANK}, 20000, 'n'))
    extra = 0 if OPTIONS['quick'] else OPTIONS['cases']
    for _index in range(extra):
        count = rng.choice((0, 1, 2, 3, 4, 0xFF))
        half = rng.choice((0, 1, -1 & 0xFFFF, 100, -100 & 0xFFFF, 0x7FFF, 0x8000, rng.randrange(0x10000)))
        pool = (0x11, 0x22, 0x33, 0x44, 0x99)
        clips = tuple(rng.choice(pool) for _ in range(count if count < 0x80 else 0))
        vel = rng.choice((0, 0x3F800000, 0xBF800000, f32(rng.uniform(-1, 1))))
        pos = rng.choice((0, 0x3F800000, 0xBF800000, f32(rng.uniform(-1, 1))))
        queen_plant(w.mem, w.queen, w.classdef, count, half, clips, vel, pos)
        out.append(rig.compare(BANK, 'update_bank', (w.queen,), {BANK}, 20000, 'n'))
    return out


def fade_cases(rig):
    rig.pcs.clear()
    w = rig.world
    out = []
    for count, clips in ((2, (0x11, 0x99)), (1, (0x99,)), (0, ()), (0xFF, (0x11,)),
                         (4, (0x11, 0x22, 0x33, 0x44)), (3, (0x44, 0x11, 0x22))):
        queen_plant(w.mem, w.queen, w.classdef, count, 0, clips)
        out.append(rig.compare(FADE, 'fade_bank_tracks', (w.queen,), {FADE}, 20000, 'n'))
    return out


def shield_cases(rig):
    rig.pcs.clear()
    w, mem = rig.world, rig.world.mem
    spell, caster, skill = w.spell, w.caster, w.skill
    cases = (
        (1, ((32, -16, 8, 0),), (ident(tz=64),), 0, C.ONE, True, 100, 0),
        (3, ((16, 16, 0, 0), (0, 8, 4, 4), (-20, 4, 12, 0)),
         (ident(tz=64), ident(tx=32)), 0x1234, C.ONE, True, 0, 0),
        (1, ((8, 8, 8, 0),), (ident(tz=96),), 0x4000, C.ZERO, False, 10, 0),
        (2, ((4, -4, 2, 0), (1, 1, 1, 4)), (ident(tz=64), ident(tx=-16)),
         0xC000, C.ZERO, True, 1, 0),
        (4, ((12, 0, 0, 0), (0, 12, 0, 0), (0, 0, 12, 4), (6, 6, 6, 4)),
         (ident(tx=128, tz=32), ident()), 0x7FFF, C.ONE, True, 250, 5),
        (1, ((0, 0, 0, 0),), (ident(tz=64),), 0x8000, f32(0.26), True, 7, 9),
    )
    if OPTIONS['quick']:
        cases = cases[:2]
    out = []
    follow = set(rig.sample)
    for points, _count, joints, facing, cool, give, stat, level in (
            (item[1], item[0], item[2], item[3], item[4], item[5], item[6], item[7]) for item in cases):
        zero(mem, spell, 0x40)
        zero(mem, caster, 0x140)
        zero(mem, skill, 0x70)
        plant_points(mem, w.model, points)
        plant_pose(mem, w.pose, joints)
        mem.w32(spell + 0x8, skill)
        mem.w32(spell + 0xC, caster)
        mem.w32(spell + 0x10, 0x13579BDF)
        mem.w32(spell + 0x1C, cool)
        mem.w32(spell + 0x24, 0x00D00010)
        mem.w8(spell, level)
        mem.w32(caster + 0x48, w.vt_caster)
        mem.w32(caster + 0x114, w.pose)
        mem.w32(caster + 0x10, 0x41000000)
        mem.w32(caster + 0x14, 0xC0800000)
        mem.w32(caster + 0x18, 0x41A00000)
        mem.w16(caster + 0x38, facing)
        mem.w32(skill + 0x60, w.vt_skill)
        w.give, w.stat = give, stat
        out.append(rig.compare(ABSORB, 'holy_shield_sample', (spell,), follow, 8000000, 'f'))
    return out


def volley_cases(rig, rng):
    rig.pcs.clear()
    w, mem = rig.world, rig.world.mem
    bolt = w.bolt
    fixed = (
        (1, 5, 0, 1),
        (0, 600, 0, 0x12345678),
        (0, 0, 1, 3),
        (0, 0, 3, 9),
        (0, 0, 2, 0xABCDEF),
        (0, 0, 0, 1),
        (0, 0xFFFFFFFE, 0, 5),
    )
    out = []

    def one(ended, age, collide, seed, pos=None, vel=None):
        zero(mem, bolt, 0x100)
        mem.w32(bolt + 0x60, ended)
        mem.w32(bolt + 0x6C, age & M32)
        mem.w32(bolt + 0x44, seed)
        mem.w32(bolt + 0x74, 0x10)
        for col in range(3):
            mem.w32(bolt + 0x10 + 4 * col, (pos or (0x41000000, 0x41800000, 0x41C00000))[col])
            mem.w32(bolt + 0x54 + 4 * col, (vel or (0x3F800000, 0xBE800000, 0x3F000000))[col])
        w.collide = collide
        return rig.compare(VOLLEY, 'multifire_run', (bolt,), {RAND}, 2000000, 'n')

    for item in fixed[:2] if OPTIONS['quick'] else fixed:
        out.append(one(*item))
    if not OPTIONS['quick']:
        for _index in range(OPTIONS['cases']):
            out.append(one(0, rng.randrange(0, 500), rng.choice((0, 2, 4, 6)),
                           rng.getrandbits(32) or 1,
                           tuple(f32(rng.uniform(-50, 50)) for _ in range(3)),
                           tuple(f32(rng.uniform(-8, 8)) for _ in range(3))))
    return out


class SightRun:
    def __init__(self, elf):
        emu = self.emu = EE(elf, fpu_model='ps2')
        emu.div_zero = 'r5900'
        emu.follow = Follow(set())
        emu.stub(R5.UPDATE_ACTIVE, ret=1, name='active')
        self.vt = emu.alloc(0x200, fill=0)
        for slot in range(48):
            emu.mem.w32(self.vt + 8 * slot + 4, FN_VIRT)
        self.classdef = emu.alloc(0x20, fill=0)
        self.obj = emu.alloc(0x800, fill=0)
        self.pcs = set()
        self.by = {}

    def bind(self, hit_ra):
        def virt(emu):
            ra, arg = emu.r[31] & M32, emu.r[5] & M32
            self.seen.append((ra, arg))
            return 1 if ra == hit_ra else 0
        self.emu.stub(FN_VIRT, function=virt, name='virt')

    def go(self, entry, state, hit_ra, serial=0, frame=0, kind=0, tracks=0, active=1):
        mem, obj = self.emu.mem, self.obj
        zero(mem, obj, 0x800)
        mem.w32(obj + 0x24, self.classdef)
        mem.w32(obj + 0x48, self.vt)
        mem.w16(obj + 0x232, state)
        mem.w8(obj + 0x230, serial & 0xFF)
        mem.w32(obj + 0x44, 0)
        mem.w32(obj + 0x3D0, kind)
        mem.w8(obj + 0x118, tracks & 0xFF)
        mem.w32(RC.G_SIM_FRAME, frame & M32)
        self.seen = []
        self.bind(hit_ra)
        self.emu.stub(R5.UPDATE_ACTIVE, ret=active, name='active')
        emu = self.emu
        emu.reset_log()
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x4000
        try:
            emu.call(entry, obj, max_steps=200000)
        except EmuError as exc:
            return str(exc)
        self.pcs.update(emu.trace)
        self.by.setdefault(entry, set()).update(emu.trace)
        return None

    def forces(self, ras):
        return tuple(arg for ra, arg in self.seen if ra in ras)

    def targets(self, addr):
        return [call.site for call in self.emu.calls if call.target == addr]


def sight_cases(run):
    problems = []
    # (label, entry, state, kind, tracks, hit_ra, expect_forces, want3, fade, bank)
    rows = (
        ('aq0', QUEEN, 0, 0, 0, 0, (0, 0), False, True, False),
        ('aq0-hit', QUEEN, 0, 0, 0, 0x23704C, (0,), True, True, False),
        ('aq0-full', QUEEN, 0, 0, 4, 0x23704C, (0, 0), False, True, False),
        ('aq1', QUEEN, 1, 0, 0, 0, (0,), False, False, True),
        ('aq1-hit', QUEEN, 1, 0, 0, 0x2370E4, (0,), True, False, True),
        ('aq-idle', QUEEN, 0, 0, 0, 0, (0, 0), False, True, False),
        ('sk0', SKELETON, 0, 0, 0, 0, (0,), False, False, False),
        ('sk0-bow', SKELETON, 0, 4, 0, 0, (0, 1), False, False, False),
        ('sk0-hit', SKELETON, 0, 4, 0, 0x2A69D8, (0,), True, False, False),
        ('sk1', SKELETON, 1, 0, 0, 0, (0,), False, False, False),
        ('sk1-bow', SKELETON, 1, 4, 0, 0, (0, 1), False, False, False),
        ('sk1-hit', SKELETON, 1, 4, 0, 0x2A6A64, (0,), True, False, False),
        ('sk-idle', SKELETON, 0, 4, 0, 0, (), False, False, False),
    )
    for label, entry, state, kind, tracks, hit, expect, want3, fade, bank in rows:
        ras = R5.SIGHT_RA['antqueen%d' % state] if entry == QUEEN else R5.SIGHT_RA['skeleton%d' % state]
        stopped = run.go(entry, state, hit, kind=kind, tracks=tracks,
                         active=0 if label in ('sk-idle', 'aq-idle') else 1)
        got = () if stopped else run.forces(ras)
        asked = False if stopped else any(arg == 3 for _ra, arg in run.seen)
        fades = () if stopped else run.targets(FADE)
        banks = () if stopped else run.targets(BANK)
        bad = []
        if stopped:
            bad.append(stopped)
        if got != expect:
            bad.append('forces %s want %s seen %s' % (got, expect, run.seen[:8]))
        if asked != want3:
            bad.append('state3 %s' % asked)
        if fade != (R5.FADE_SITE in fades):
            bad.append('fade %s' % fades)
        if bank != (R5.BANK_SITE in banks):
            bad.append('bank %s' % banks)
        if bad:
            problems.append('%s: %s' % (label, '; '.join(bad)))
    return problems


def soul_cases(run):
    problems = []
    rows = (
        (0, 9, 9, True, 0x2A99DC),
        (0, 1, 0, False, None),
        (0, 0, 0, True, 0x2A99DC),
        (0, 16, 0, True, 0x2A99DC),
        (0, 16, 1, False, None),
        (0, 9, 0, False, None),
        (0x18, 0, 0, True, 0x2A9A38),
        (0x18, 1, 0, False, None),
    )
    # Creature_updateActive returning 0 leaves Soul_run before the phase test.
    stopped = run.go(SOUL, 0, 0, serial=0, frame=0, active=0)
    if stopped or run.targets(DEMON):
        problems.append('inactive soul: %s sites %s' % (stopped, [] if stopped else run.targets(DEMON)))
    # The word at +0x44 stays 0, so a hit on frame 9 cannot be that word.
    for state, frame, serial, due, site in rows:
        stopped = run.go(SOUL, state, 0, serial=serial, frame=frame)
        sites = [] if stopped else run.targets(DEMON)
        called = bool(sites)
        if stopped or called != due or (due and site not in sites):
            problems.append('state %x frame %s serial %s: %s sites %s' % (
                state, frame, serial, stopped or ('called' if called else 'absent'), sites))
        if due != R5.soul_demon_due(frame, serial):
            problems.append('helper disagrees with the case')
    # A matching low nibble in the generator word, and nowhere else, is not the gate.
    stopped = run.go(SOUL, 0, 0, serial=0, frame=9)
    if not stopped:
        run.emu.mem.w32(run.obj + 0x44, 9)
        # go() zeroes the object, so plant the word by a second call after patching go's plant.
    mem, obj = run.emu.mem, run.obj
    zero(mem, obj, 0x800)
    mem.w32(obj + 0x24, run.classdef)
    mem.w32(obj + 0x48, run.vt)
    mem.w16(obj + 0x232, 0)
    mem.w8(obj + 0x230, 0)
    mem.w32(obj + 0x44, 9)
    mem.w32(RC.G_SIM_FRAME, 9)
    run.seen = []
    run.bind(0)
    run.emu.reset_log()
    run.emu.r[29] = run.emu.stack_hi - 0x4000
    try:
        run.emu.call(SOUL, obj, max_steps=200000)
        run.by.setdefault(SOUL, set()).update(run.emu.trace)
        if run.targets(DEMON):
            problems.append('generator word +0x44 was treated as the phase byte')
    except EmuError as exc:
        problems.append('seed word case: %s' % exc)
    return problems


class DemonRun:
    def __init__(self, elf):
        emu = self.emu = EE(elf, fpu_model='ps2')
        emu.div_zero = 'r5900'
        emu.follow = Follow(set())
        self.creature = emu.alloc(0x40, fill=0)
        self.vt = emu.alloc(0x10, fill=0)
        emu.mem.w32(self.vt + 4, FN_GET)
        self.objects = [emu.alloc(0x20, fill=0) for _ in range(4)]
        for obj in self.objects:
            emu.mem.w32(obj + 0x48, self.vt)
        self.index = 0
        self.tokens = {}
        self.demons = set()
        self.listed = []

        def box(emu):
            dest = emu.r[6] & M32
            for index, obj in enumerate(self.listed):
                emu.mem.w32(dest + 4 * index, obj)
            emu.mem.w32(dest + 4 * len(self.listed), 0)
            return 0

        def getter(emu):
            token = self.tokens[self.listed[self.index]]
            self.index += 1
            return token

        def kind(emu):
            return 1 if (emu.r[4] & M32) in self.demons else 0

        emu.stub(BOX, function=box, name='box')
        emu.stub(FN_GET, function=getter, name='type')
        emu.stub(R5.DEMON_TYPEINFO, ret=0xD000, name='demon')
        emu.stub(RTTI, function=kind, name='rtti')
        self.pcs = set()

    def go(self, objects, tokens, demons, pos):
        mem, creature = self.emu.mem, self.creature
        zero(mem, creature, 0x40)
        for index, word in enumerate(pos):
            mem.w32(creature + 0x10 + 4 * index, word)
        for obj in self.objects:
            mem.w32(obj + 0xC, 0)
        for obj, flags in objects:
            mem.w32(obj + 0xC, flags)
        self.listed = [obj for obj, _flags in objects]
        self.tokens = tokens
        self.demons = demons
        self.index = 0
        view = D.ModelView(mem)
        model = R5.SoulModel(view, _ModelDemon(tokens, demons))
        mret = model.is_demon_near(creature, self.listed)
        emu = self.emu
        emu.reset_log()
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x4000
        try:
            eret = emu.call(DEMON, creature, max_steps=200000)
        except EmuError as exc:
            return ['original stopped: %s' % exc]
        self.pcs.update(emu.trace)
        problems = []
        if (eret & M32) != (mret & M32):
            problems.append('result %s / %s' % (eret & M32, mret))
        box_calls = [call for call in emu.calls if call.target == BOX]
        if len(box_calls) != 1:
            return problems + ['box calls %d' % len(box_calls)]
        box = box_calls[0]
        if (box.args[3] & M32) != R5.DEMON_LIMIT:
            problems.append('limit %s' % (box.args[3] & M32))
        if not is_stack(box.args[0] & M32) or not is_stack(box.args[1] & M32) or not is_stack(box.args[2] & M32):
            problems.append('box pointers leave the stack')
        low = tuple(mem.u32((box.args[0] & M32) + 4 * index) for index in range(3))
        high = tuple(mem.u32((box.args[1] & M32) + 4 * index) for index in range(3))
        want_low, want_high, _limit = model.calls[0][1]
        if low != want_low or high != want_high:
            problems.append('box %s %s / %s %s' % (low, high, want_low, want_high))
        getters = [call for call in emu.calls if call.target == FN_GET]
        for index, call in enumerate(getters):
            # The jalr does not load the object into a0.  The first call still holds
            # the box minimum.  Each later call holds the previous object's type word,
            # which the compare left in a0.
            if index == 0:
                expect_a0 = box.args[0] & M32
            else:
                expect_a0 = self.tokens[self.listed[index - 1]] & M32
            if (call.args[0] & M32) != expect_a0:
                problems.append('typeinfo a0 %08x want %08x' % (call.args[0] & M32, expect_a0))
                break
        orig = [(call.args[0] & M32, call.args[1] & M32)
                for call in emu.calls if call.target == RTTI]
        want = [args for name, args in model.calls if name == 'rtti_typeInfoEquals']
        if orig != want:
            problems.append('rtti %s / %s' % (orig, want))
        if len(getters) != len(want):
            problems.append('typeinfo calls %d / %d' % (len(getters), len(want)))
        stored = [addr for _pc, addr, _size, _value in emu.writes if not is_stack(addr)]
        if stored:
            problems.append('stores %s' % sorted('%x' % addr for addr in stored)[:6])
        return problems


class _ModelDemon:
    def __init__(self, tokens, demons):
        self.tokens, self.demons = tokens, demons

    def get(self, name):
        def answer(*args):
            if name == 'Creature.v0':
                return self.tokens[args[0]]
            if name == 'Demon_typeinfo':
                return 0xD000
            if name == 'rtti_typeInfoEquals':
                return 1 if args[0] in self.demons and args[1] == 0xD000 else 0
            return 0
        return answer


def demon_cases(run):
    objs = run.objects
    pos = (0x41000000, 0xC1800000, 0x41C00000)
    rows = (
        ((), {}, set(), pos),
        (((objs[0], 0),), {objs[0]: 0xA1}, {0xA1}, pos),
        (((objs[0], 8), (objs[1], 0)), {objs[0]: 0xA1, objs[1]: 0xA2}, {0xA1, 0xA2}, pos),
        (((objs[0], 0), (objs[1], 0)), {objs[0]: 0xA1, objs[1]: 0xA2}, set(), pos),
        (((objs[0], 8),), {objs[0]: 0xA1}, {0xA1}, (0, 0, 0)),
        (((objs[0], 0), (objs[1], 8), (objs[2], 0)),
         {objs[0]: 0xA1, objs[1]: 0xA2, objs[2]: 0xA3}, {0xA2, 0xA3},
         (0xC3160000, 0x43160000, 0x42C80000)),
    )
    problems = []
    for index, row in enumerate(rows):
        found = run.go(*row)
        if found:
            problems.append('case %d: %s' % (index, '; '.join(found)))
    return problems


def report(key, compared, failed, shown, pcs):
    hit, total = cover(pcs, key)
    print('%-22s %8d %8d  %d of %d instructions' % (key, compared, failed, hit, total))
    for line in shown:
        print('   ', line)
    return not failed


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
        elif item == '-k':
            OPTIONS['filter'] = args.pop(0)
        else:
            elf = item
    if elf is None:
        elf = os.path.join(D.ROOT, 'SLUS_209.73')
    if not os.path.exists(elf):
        alt = os.path.expanduser('~/champions-re/SLUS_209.73')
        elf = alt if os.path.exists(alt) else elf
    if not os.path.exists(elf):
        print('difftest_combat_round5: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('difftest_combat_round5: not SLUS_209.73 US v2.00 - skipped')
        return 0
    C.set_fpu('ps2')
    started = time.time()
    ok = True
    print('%-22s %8s %8s  first problem' % ('entry point', 'compared', 'failed'))
    if any(wanted(key) for key in ('hitAngle', 'metalAngle', 'gibAngle', 'blockAngle')):
        angles = AngleRun(elf)
        for key, fn in (('hitAngle', hit_cases), ('metalAngle', metal_cases),
                        ('gibAngle', gib_cases), ('blockAngle', block_cases)):
            if not wanted(key):
                continue
            found = fn(angles)
            counted = {'hitAngle': 5, 'metalAngle': 3 if OPTIONS['quick'] else 5,
                       'gibAngle': 4, 'blockAngle': 2 if OPTIONS['quick'] else 5}[key]
            ok = report(key, counted, len(found), found[:4], angles.pcs) and ok
    spans = load_spans(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ghidra_funcs.tsv'))
    need_rig = any(wanted(key) for key in ('fadeBank', 'updateBank', 'holySample', 'multifire'))
    if need_rig:
        rig = Rig(elf, spans)
        rng = random.Random(OPTIONS['seed'])
        if wanted('fadeBank'):
            found = fade_cases(rig)
            failed = [item for item in found if item]
            ok = report('fadeBank', len(found), len(failed),
                        ['case %d: %s' % (i, item if isinstance(item, str) else '; '.join(item))
                         for i, item in enumerate(found) if item][:4], rig.pcs) and ok
        if wanted('updateBank'):
            found = bank_cases(rig, rng)
            failed = [item for item in found if item]
            ok = report('updateBank', len(found), len(failed),
                        ['case %d: %s' % (i, item if isinstance(item, str) else '; '.join(item))
                         for i, item in enumerate(found) if item][:4], rig.pcs) and ok
        if wanted('holySample'):
            found = shield_cases(rig)
            failed = [item for item in found if item]
            ok = report('holySample', len(found), len(failed),
                        ['case %d: %s' % (i, item if isinstance(item, str) else '; '.join(item))
                         for i, item in enumerate(found) if item][:4], rig.pcs) and ok
        if wanted('multifire'):
            found = volley_cases(rig, rng)
            failed = [item for item in found if item]
            ok = report('multifire', len(found), len(failed),
                        ['case %d: %s' % (i, item if isinstance(item, str) else '; '.join(item))
                         for i, item in enumerate(found) if item][:4], rig.pcs) and ok
    if any(wanted(key) for key in ('antQueen', 'skeleton', 'soulPhase')):
        sight = SightRun(elf)
        if wanted('antQueen') or wanted('skeleton'):
            found = sight_cases(sight)
            queen = [item for item in found if item.startswith('aq')]
            skel = [item for item in found if item.startswith('sk')]
            if wanted('antQueen'):
                ok = report('antQueen', 6, len(queen), queen[:4], sight.by.get(QUEEN, ())) and ok
            if wanted('skeleton'):
                ok = report('skeleton', 7, len(skel), skel[:4], sight.by.get(SKELETON, ())) and ok
        if wanted('soulPhase'):
            found = soul_cases(sight)
            ok = report('soulPhase', 10, len(found), found[:4], sight.by.get(SOUL, ())) and ok
    if wanted('demonNear'):
        demon = DemonRun(elf)
        found = demon_cases(demon)
        ok = report('demonNear', 6, len(found), found[:4], demon.pcs) and ok
    print('total: %.1f s' % (time.time() - started))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
