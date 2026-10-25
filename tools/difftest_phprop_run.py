#!/usr/bin/env python3
"""difftest_phprop_run.py - compare tools/ref_phprop_run.py with the game's own code: the
per-frame run of a physics prop (PhProp_run) and of a gut chunk (GutChunk_run), with the
rigid-body bodies under them and the resting prop's constructors.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_phprop_run.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                          [--cases N] [--lives N] [--frames N] [-k TEXT] [-v]
                                          [--trace-first]

What is compared
    Each run of a body happens in tools/ee_emu.py with these bodies REAL: GutChunk_run
    0x1edb18, PhProp_run 0x155fcc, rigidbody_pointVelocity 0x167008,
    rigidbody_applyCollisionImpulse 0x167408, rigidbody_integrate 0x167730,
    rigidbody_addForceAtPoint 0x167c18, model_getHullPoints 0x179320, Prop_ctorNamed
    0x153ac0, Prop_ctorRes 0x153c88, ItemProp_ctor3 0x1592bc, and under them GameObject_ctor,
    GameObject_rand, item_getResourceIndex, the matrix and quaternion bodies of
    tools/ref_core.py (quat_mul, quat_normalize, mat3_transpose, mat3_mul,
    mat3_mulVecTransposed, mat3_scale, mat34_translateLocal) and the C library.  Every other
    callee is a recording stub (ref_phprop_run.EXTERNALS) answered by the same script on both
    sides.  The same inputs go through ref_phprop_run.Model on a copy-on-write view; equal
    must be the calls with their arguments, the bytes stored outside the stack, the shared
    seed 0x404464 with its draw count, and the cosmetic seed 0x404460 (untouched).

Entries
    phrun     PhProp_run once, on a prop whose every field the body reads is set by the
              generator (dirty or plausible), with random answers from the services
    gutrun    GutChunk_run once, likewise (the chunk fields +0x248..+0x260 too)
    gutLife   a gut chunk BUILT by the real GutChunk_ctor chain (rigidbody_init and the
              quaternion bodies real as well; not compared, difftest_phprop compares it),
              then run frame after frame by GutChunk_run in both, state compared every
              frame, until it deletes itself or --frames is reached.  The services answer
              from a deterministic world (ground plane or steps or a pit, a wall, water)
    boneLife  the same for a bone prop built by PhProp_ctor2 (the shatter's launch 0x107)
              and run by PhProp_run
    propLife  the same for a prop built by PhProp_ctor (launch mixes, with and without an
              item record), run by PhProp_run
"""
import hashlib
import math
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError                 # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_phprop as PP                         # noqa: E402
import ref_phprop_run as PR                     # noqa: E402
import difftest_combat_runtime as D             # noqa: E402
import difftest_creature as DC                  # noqa: E402

EXPECTED_SHA256 = D.EXPECTED_SHA256
ROOT = D.ROOT
M32, M64 = 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF
LIB_LO, LIB_HI = 0x3A5000, 0x3C0000
G_COSMETIC_SEED = 0x404460
f32 = D.f32
is_stack = D.is_stack

OPTIONS = {'quick': False, 'seed': 20973, 'cases': 3000, 'lives': 60, 'frames': 450, 'filter': None,
           'verbose': False, 'trace_first': False}

# the bodies whose coverage is reported: name -> list of (start, end)
BODIES = {
    'GutChunk_run': [(0x1EDB18, 0x1EDBFC), (0x1EDC00, 0x1EE050)],     # 0x1edbfc: an unreachable nop
    'PhProp_run': [(0x155FCC, 0x156DB4)],
    'rigidbody_pointVelocity': [(0x167008, 0x167120)],
    'rigidbody_applyCollisionImpulse': [(0x167408, 0x167730)],
    'rigidbody_integrate': [(0x167730, 0x167A58)],
    'rigidbody_addForceAtPoint': [(0x167C18, 0x167D10)],
    'model_getHullPoints': [(0x179320, 0x179354)],
    'Prop_ctorNamed': [(0x153AC0, 0x153C88)],
    'Prop_ctorRes': [(0x153C88, 0x153DE8)],
    'ItemProp_ctor3': [(0x1592BC, 0x159458)],
}
BORROWED_SPANS = {
    'GameObject_ctor': (0x14CB10, 0x14CF84), 'GameObject_rand': (0x1509D0, 0x1509F8),
    'item_getResourceIndex': (0x1083F8, 0x108434), 'quat_mul': (0x166480, 0x166550),
    'quat_normalize': (0x166550, 0x1665B4), 'mat3_transpose': (0x166298, 0x166340),
    'mat3_mul': (0x165710, 0x1657DC), 'mat3_mulVecTransposed': (0x165DA0, 0x165E40),
    'mat3_scale': (0x165CC0, 0x165D30), 'mat34_translateLocal': (0x165B10, 0x165B98),
}
REAL = set(PR.EXECUTED.values()) | set(PR.BORROWED.values())
# bodies that run for real only while a life's object is built (not compared here)
BUILD_REAL = set(PP.MODELLED.values()) | {0x1682F0, 0x164330, 0x167A58}

ENTRIES = {
    # key -> (address, method)
    'phrun': (PR.PHPROP_RUN, 'phprop_run'),
    'gutrun': (PR.GUTCHUNK_RUN, 'gutchunk_run'),
}
LIVES = {
    # key -> (run address, run method, builder)
    'gutLife': (PR.GUTCHUNK_RUN, 'gutchunk_run', 'build_gut'),
    'boneLife': (PR.PHPROP_RUN, 'phprop_run', 'build_bone'),
    'propLife': (PR.PHPROP_RUN, 'phprop_run', 'build_prop'),
}
STUBS = dict(PP.EXTERNALS)
for _name in ('rigidbody_init', 'quat_fromMat3', 'quat_normalize', 'rigidbody_updateDerived'):
    del STUBS[_name]                            # these run for real (the build needs them)
STUBS.update(PR.EXTERNALS)


def to_float(raw):
    return RC.C.to_float(raw & M32)


class RealSet:
    def __init__(self):
        self.extra = set()

    def __contains__(self, target):
        return target in REAL or target in self.extra or LIB_LO <= target < LIB_HI


class Terrain:
    """A deterministic world for the lives: a ground plane (with steps, or none at all: a
    pit), an optional wall at x = wall, an optional water level."""

    def __init__(self, rng, base):
        self.base = base
        self.kind = rng.choice(('flat', 'flat', 'slope', 'steps', 'pit'))
        self.sx = rng.uniform(-0.3, 0.3) if self.kind == 'slope' else 0.0
        self.sy = rng.uniform(-0.3, 0.3) if self.kind == 'slope' else 0.0
        self.step = rng.uniform(4, 30)
        self.wall = None
        self.water = None
        self.origin = (0.0, 0.0)

    def ground(self, pos):
        x, y = to_float(pos[0]), to_float(pos[1])
        if self.kind == 'pit':
            return f32(-1000000.0)
        h = self.base + self.sx * (x - self.origin[0]) + self.sy * (y - self.origin[1])
        if self.kind == 'steps':
            h += self.step * math.floor((x - self.origin[0]) / 40.0)
        return f32(h)

    def sweep(self, pos, delta):
        x, dx = to_float(pos[0]), to_float(delta[0])
        if self.wall is not None and dx > 0 and x <= self.wall < x + dx:
            return f32(max(0.0, min(1.0, (self.wall - x) / dx))), f32(-1.0), 0
        return RC.ONE, 0, 0

    def in_water(self, pos):
        return 1 if self.water is not None and to_float(pos[2]) < self.water else 0


class World:
    def __init__(self, emu):
        self.emu, self.mem = emu, emu.mem
        self.argbuf = emu.alloc(0x200)
        self.blocks = [emu.alloc(0x280, align=16) for _ in range(3)]
        self.fresh = [emu.alloc(0x4C0, align=16) for _ in range(3)]     # what pool_new hands out
        self.items = [emu.alloc(0x50, align=16) for _ in range(2)]
        self.defs = [emu.alloc(0x40, align=16) for _ in range(2)]
        self.players = [emu.alloc(0x40, align=16) for _ in range(2)]
        self.models = [emu.alloc(0x1800, align=16) for _ in range(2)]
        self.hulls = {}
        self.names = []
        for text in (b'fx.lmp', b'gutchunks.vif', b'gutchunks.tex', b'model_b', b''):
            s = emu.alloc(0x48)
            self.mem.write(s, text + b'\0')
            self.names.append(s)
        self.terrain = None
        self.pool = 'random'
        self.fresh_used = 0
        rng = random.Random(1)
        for model in self.models:
            self.make_model(model, rng)

    def make_model(self, model, rng):
        """A model header whose byte +0x25 says where the hull table is, and 64 meshes of
        eight s8 points around a centre."""
        k = rng.choice((2, 4, 9))
        self.mem.w8(model + 0x25, k)
        hull = []
        for mesh in range(64):
            cx, cy, cz = rng.randrange(-20, 20), rng.randrange(-20, 20), rng.randrange(-5, 30)
            hx, hy, hz = rng.randrange(2, 9), rng.randrange(2, 9), rng.randrange(2, 9)
            pts = []
            for j in range(8):
                p = (cx + (hx if j & 1 else -hx), cy + (hy if j & 2 else -hy), cz + (hz if j & 4 else -hz))
                pts.append(p)
                for i in range(3):
                    self.mem.w8(model + k * 16 + mesh * 24 + 3 * j + i, p[i] & 0xFF)
            hull.append(pts)
        self.hulls[model] = hull

    def bounds(self, model, mask):
        hull = self.hulls.get(model)
        pts = [p for mesh in range(64) if hull and mask >> mesh & 1 for p in hull[mesh]]
        if not pts:
            return (0,) * 6
        return tuple(min(p[i] for p in pts) for i in range(3)) + tuple(max(p[i] for p in pts) for i in range(3))

    def zero_fresh(self):
        for block in self.fresh:
            self.mem.write(block, bytes(0x4C0))
        self.fresh_used = 0

    def respond(self, name, args, view, rng):
        handler = getattr(self, 'on_' + name, None)
        return handler(args, view, rng) if handler is not None else D.Res()

    # ---- services -----------------------------------------------------------------------
    def _near(self, args, rng):
        z = to_float(args[1][2])
        r = rng.random()
        if r < 0.08:
            return f32(-1000000.0)
        if r < 0.12:
            return f32(-10000.0)
        if r < 0.2:
            return args[1][2]
        return f32(z + rng.choice((-40.0, -12.0, -3.0, -0.005, 0.0, 0.5, 2.0, 11.0, rng.uniform(-30, 10))))

    def on_water_test(self, args, view, rng):
        if self.terrain is not None:
            return D.Res(self.terrain.in_water(args[1]))
        return D.Res(rng.choice((0, 0, 0, 1, 7)))

    def on_terrain_heightBelow(self, args, view, rng):
        if self.terrain is not None:
            return D.Res(f=self.terrain.ground(args[1]))
        return D.Res(f=self._near(args, rng))

    def on_terrain_height(self, args, view, rng):
        if self.terrain is not None:
            return D.Res(f=self.terrain.ground(args[1]))
        return D.Res(f=self._near(args, rng))

    def on_terrain_sweepCircle(self, args, view, rng):
        if self.terrain is not None:
            t, nx, ny = self.terrain.sweep(args[1], args[2])
            return D.Res(f=t, outs=[nx, ny])
        t = rng.choice((RC.ONE, RC.ONE, 0, f32(0.3), f32(0.75), f32(rng.random())))
        angle = rng.uniform(0, 2 * math.pi)
        return D.Res(f=t, outs=[f32(math.cos(angle)), f32(math.sin(angle))])

    def on_pool_new(self, args, view, rng):
        if self.pool == 'none':
            return D.Res(0)
        if self.pool == 'random' and rng.random() < 0.25:
            return D.Res(0)
        block = self.fresh[self.fresh_used % len(self.fresh)]
        self.fresh_used += 1
        return D.Res(block)

    def on_res_find(self, args, view, rng):
        name = args[1]
        if isinstance(name, tuple):
            text = name[1]
        else:
            text = bytearray()
            while len(text) < 64 and view.load(name + len(text), 1):
                text.append(view.load(name + len(text), 1))
            text = bytes(text)
        if text.endswith(b'.vif'):
            return D.Res(self.models[1] if text.startswith(b'skel') else self.models[0])
        if self.terrain is not None:
            return D.Res(0x00A10040)
        return D.Res(rng.choice((0, 0x00A10000, 0x00A10040)))

    def on_obj_getPropInt(self, args, view, rng):
        return D.Res(0)

    def on_sound_playOnObject(self, args, view, rng):
        return D.Res(rng.choice((0xFFFFFFFF, 3)))

    def on_model_getBounds(self, args, view, rng):
        return D.Res(outs=[v & M32 for v in self.bounds(args[0], args[1])])

    def on_model_getMeshJoint(self, args, view, rng):
        return D.Res(rng.choice((0, 1, 5)))

    def on_anim_getJointMatrix(self, args, view, rng):
        m = [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, rng.uniform(-15, 15), rng.uniform(-15, 15), rng.uniform(0, 40)]
        return D.Res(outs=[[f32(v) for v in m]])


class Rig:
    def __init__(self, elf):
        emu = self.emu = EE(elf, fpu_model='ps2')
        emu.div_zero = 'r5900'
        self.world = World(emu)
        self.follow = emu.follow = RealSet()
        self.names = {}
        for name, ext in STUBS.items():
            self.names[ext.addr] = name
            stub = self.sprintf_stub if name == 'libc_sprintf' else self.make_stub(name, ext)
            emu.stub(ext.addr, function=stub, name=name)
        self.calls, self.unknown, self.pcs = [], {}, set()
        self.partial, self.partial_ops = [], {}
        spans = [span for spans in BODIES.values() for span in spans] + list(BORROWED_SPANS.values())
        for start, end in spans:
            for pc in range(start, end, 4):
                word = emu.mem.u32(pc)
                if word >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = word >> 26
                    emu.hook(pc, self.partial_hook(pc, (word >> 21) & 31, ee_emu.sx16(word)))
        self.eview = D.View(emu.mem.load, self._epoke)
        self.touched = set()
        self.script_rng = None
        self.own_draws = 0

    def partial_hook(self, pc, base, offset):
        def note(emu):
            ea = (emu.r[base] + offset) & M32
            if not is_stack(ea):
                self.partial.append((pc, ea))
        return note

    def _epoke(self, addr, size, value):
        self.emu.mem.store(addr, size, value & ((1 << (8 * size)) - 1))
        self.touched.update(range(addr, addr + size))

    def stored_bytes(self, lo, hi):
        out, pending = set(), list(self.partial)
        for pc, addr, size, _value in self.emu.writes:
            op = self.partial_ops.get(pc)
            if op is not None:
                _ppc, ea = pending.pop(0)
                if op == 0x2C:
                    first, last = ea & ~7, ea
                elif op == 0x2D:
                    first, last = ea, ea | 7
                elif op == 0x2A:
                    first, last = ea & ~3, ea
                else:
                    first, last = ea, ea | 3
            else:
                first, last = addr, addr + size - 1
            if not lo <= first < hi and not is_stack(first):
                out.update(range(first, last + 1))
        return out

    def decode(self, ext, emu):
        mem, canon, outs = emu.mem, [], []
        for index, kind in enumerate(ext.ints):
            reg = emu.r[4 + index]
            if kind == 'q':
                canon.append(reg & M64)
            elif kind == 'v':
                canon.append(tuple(mem.u32((reg & M32) + 4 * j) for j in range(3)))
            elif kind == 'S':
                ptr = reg & M32
                if is_stack(ptr):
                    text = bytearray()
                    while mem.u8(ptr + len(text)):
                        text.append(mem.u8(ptr + len(text)))
                    canon.append(('buf', bytes(text)))
                else:
                    canon.append(ptr)
            elif kind == 'w':
                outs.append(reg & M32)
            elif kind == 'N':
                outs.append(('N', reg & M32))
            elif kind == 'M':
                outs.append(('M', reg & M32))
            else:
                canon.append(reg & M32)
        for j in range(ext.floats):
            canon.append(emu.f[12 + j] & M32)
        return tuple(canon), outs

    def make_stub(self, name, ext):
        def stub(emu):
            canon, outs = self.decode(ext, emu)
            self.calls.append((name, canon))
            res = self.world.respond(name, canon, self.eview, self.script_rng)
            given = list(res.outs)
            for ptr in outs:
                if isinstance(ptr, tuple) and ptr[0] == 'M':
                    words = given.pop(0) if given else [0] * 12
                    for k, word in enumerate(words):
                        emu.mem.w32(ptr[1] + 4 * k, word)
                elif isinstance(ptr, tuple):            # two floats
                    for k in range(2):
                        emu.mem.w32(ptr[1] + 4 * k, given.pop(0) if given else 0)
                else:
                    emu.mem.w32(ptr, given.pop(0) if given else 0)
            if ext.ret == 'f':
                emu.f[0] = res.f & M32
            return res.ret
        return stub

    def sprintf_stub(self, emu):
        buf, fmt, value = emu.r[4] & M32, emu.r[5] & M32, emu.r[6] & M32
        self.calls.append(('libc_sprintf', (fmt, value)))
        text = bytearray()
        while emu.mem.u8(fmt + len(text)):
            text.append(emu.mem.u8(fmt + len(text)))
        emu.mem.write(buf, PP.render(bytes(text), value) + b'\0')
        return 0

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                ext = STUBS[name]
                if 'M' in ext.ints:
                    return list(res.outs[0]) if res.outs else [0] * 12
                if 'N' in ext.ints:
                    given = list(res.outs) + [0, 0]
                    return (res.f & M32, given[0], given[1])
                if 'w' in ext.ints:
                    n = ext.ints.count('w')
                    given = list(res.outs) + [0] * n
                    return tuple(given[:n])
                if ext.ret == 'n':
                    return None
                if ext.ret == 'f':
                    return res.f & M32
                return res.ret & M32
            return answer

    def model(self, mview, call_seed):
        rig = self

        class Counting(PR.Model):
            def obj_rand(self, obj):
                rig.own_draws += 1
                return PR.Model.obj_rand(self, obj)
        return Counting(mview, Rig.Callbacks(self, D.View(mview.load, mview.poke), random.Random(call_seed)))

    def compare(self, addr, method, args, call_seed):
        emu, mem = self.emu, self.emu.mem
        seed_before = mem.u32(RC.G_RAND_SEED)
        cosmetic_before = mem.u32(G_COSMETIC_SEED)
        mview = D.ModelView(mem)
        model = self.model(mview, call_seed)
        out = {'fault': None, 'calls': None, 'writes': None, 'seed': None, 'draws': 0,
               'model_calls': model.calls, 'emu_calls': None}
        fresh_before = self.world.fresh_used
        model_error = None
        try:
            getattr(model, method)(*args)
        except EmuError as exc:
            model_error = exc
        self.world.fresh_used = fresh_before
        self.calls, self.touched, self.partial = [], set(), []
        out['emu_calls'] = self.calls
        self.script_rng = random.Random(call_seed)
        emu.reset_log()
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x800
        emu_error = None
        try:
            emu.call(addr, *args, max_steps=4000000)
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
        lo, hi = self.world.argbuf, self.world.argbuf + 0x200
        stored = self.stored_bytes(lo, hi)
        mstored = set()
        for a, size, _v in model.writes:
            if not is_stack(a):
                mstored.update(range(a, a + size))
        diff = [a for a in sorted(stored | mstored | self.touched | mview.touched)
                if mem.load(a, 1) != mview.load(a, 1)]
        if stored != mstored or diff:
            out['writes'] = 'only original %s; only model %s; values differ at %s' % (
                sorted('%x' % a for a in stored - mstored)[:8],
                sorted('%x' % a for a in mstored - stored)[:8],
                ['%x:%02x/%02x' % (a, mem.load(a, 1), mview.load(a, 1)) for a in diff[:8]])
        expect = seed_before
        for _ in range(model.draws):
            expect = (expect * 0x19660D + 0x3C6EF35F) & M32
        if not mem.u32(RC.G_RAND_SEED) == mview.load(RC.G_RAND_SEED, 4) == expect:
            out['seed'] = 'model draws %d original %08x model %08x' % (
                model.draws, mem.u32(RC.G_RAND_SEED), mview.load(RC.G_RAND_SEED, 4))
        elif not mem.u32(G_COSMETIC_SEED) == mview.load(G_COSMETIC_SEED, 4) == cosmetic_before:
            out['seed'] = 'cosmetic seed moved: original %08x model %08x' % (
                mem.u32(G_COSMETIC_SEED), mview.load(G_COSMETIC_SEED, 4))
        out['draws'] = model.draws
        return out

    def build(self, addr, regs, fregs=(), stack=()):
        """Run a constructor in the interpreter only (rigidbody_init and the quaternion
        bodies real too)."""
        emu = self.emu
        self.follow.extra = BUILD_REAL
        self.script_rng = random.Random(0)
        emu.reset_log()
        emu.trace = None
        emu.r[29] = emu.stack_hi - 0x800
        for k, value in enumerate(stack):
            emu.mem.w64((emu.r[29] & M32) + 8 * k, value & M64)
        try:
            emu.call(addr, *regs, fargs=fregs, max_steps=4000000)
        finally:
            self.follow.extra = set()
            emu.trace = []


class Coverage:
    def __init__(self, mem):
        self.parts = {}
        for name, spans in BODIES.items():
            leaders, total = set(), 0
            for start, end in spans:
                lead, _sites = DC.analyse(mem, start, end)
                leaders |= lead
                total += (end - start) // 4
            self.parts[name] = (spans, leaders, total)
        self.pcs = set()

    def numbers(self, name):
        spans, leaders, total = self.parts[name]
        inside = {pc for pc in self.pcs if any(s <= pc < e for s, e in spans)}
        return len(leaders & inside), len(leaders), len(inside), total

    def missing(self, name):
        spans, leaders, _total = self.parts[name]
        return sorted(leaders - self.pcs)


# ---------------------------------------------------------------------------------------
# Single-run scenarios
# ---------------------------------------------------------------------------------------
def _pos(rng):
    return [f32(rng.uniform(-4000, 4000)) for _ in range(2)] + [f32(rng.uniform(-50, 300))]


def _quat(rng):
    q = [rng.gauss(0, 1) for _ in range(4)]
    n = math.sqrt(sum(v * v for v in q)) or 1.0
    return [v / n for v in q]


def _rot(q):
    """The rotation the body keeps for q (transpose of the usual matrix)."""
    x, y, z, w = q
    m = [1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y),
         2 * (x * y - w * z), 1 - 2 * (x * x + z * z), 2 * (y * z + w * x),
         2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)]
    return [m[0], m[3], m[6], m[1], m[4], m[7], m[2], m[5], m[8]]


def _wf(mem, addr, values):
    for k, v in enumerate(values):
        mem.w32(addr + 4 * k, f32(v) if isinstance(v, float) else v)


def _globals(rig, rng, sim_frame=None):
    w, mem = rig.world, rig.emu.mem
    mem.w32(RC.G_RAND_SEED, rng.getrandbits(32))
    mem.w32(G_COSMETIC_SEED, rng.getrandbits(32))
    mem.w32(PR.G_SIM_FRAME, sim_frame if sim_frame is not None else
            rng.choice((0, 8, 16, rng.getrandbits(32))))
    mem.w32(PR.G_WORLD, rng.choice((0x00C00000, 0x00C00040)))
    mem.w32(PR.G_PROP_OPTIONS, rng.choice((0, 0, 0x100, rng.getrandbits(32))))
    mem.w32(PR.G_DECAL_DETAIL, rng.choice((0, 1, 2, 2)))
    mem.w32(PR.G_NUM_PLAYERS, rng.choice((0, 1, 2, 4, 0xFFFFFFFF)))
    mem.w32(PR.G_ALIVE_PLAYERS, rng.choice((0, 0, 1, 0xFFFFFFFF)))
    for slot in range(2):
        mem.w32(PR.G_PLAYER_OBJ + PR.REC_SIZE * slot, rng.choice((w.players[slot], w.players[slot], 0)))


def _item(rig, rng):
    """An item record (+0 definition, +8 flags) with a fake definition."""
    w, mem = rig.world, rig.emu.mem
    item, definition = rng.choice(w.items), rng.choice(w.defs)
    for off in range(0, 0x50, 4):
        mem.w32(item + off, rng.getrandbits(32))
    mem.w32(item, definition)
    flags = rng.choice((0, 0x800000, 0x40000, 0x200000, 0x100000, 0x80000, 0x1000000, 0x4000000, 0x2000000,
                        0x10000000, 0x20000, 0x8000000000, rng.getrandbits(40) & ~0x1000000000))
    mem.w64(item + 8, flags)
    for off in range(0, 0x40, 4):
        mem.w32(definition + off, rng.getrandbits(32))
    mem.w8(definition + 0x1C, rng.choice((3, 3, 1, 0)))
    mem.w8(definition + 0x1D, rng.choice((0, 0, 1)))
    mem.w16(definition + 0x34, rng.randrange(0, 12))
    return item


def _prop(rig, rng, obj, vtable):
    """A prop in mid flight or at rest: every field PhProp_run and GutChunk_run read."""
    w, mem = rig.world, rig.emu.mem
    for off in range(0, 0x280, 4):
        mem.w32(obj + off, rng.getrandbits(32))
    pos = _pos(rng)
    still = rng.random() < 0.35
    near = rng.random() < 0.6
    z = to_float(pos[2])
    _wf(mem, obj + 0x10, pos)
    mem.w32(obj + 0x1C, rng.choice((f32(4.0), f32(4.0), f32(24.0))))
    mem.w32(obj + 0x48, vtable)
    mem.w32(obj + 0x4C, rng.choice(w.models))
    mem.w8(obj + 0x54, rng.choice((0, 0x66, 0x66)))
    for off in (0x55, 0x74, 0xB4):
        mem.w8(obj + off, 0)
    mem.w64(obj + 0xE8, rng.choice((0, 1, 2, 3, 6, 0x80000000, 1 << 63, 0xFFFFFFFFFFFFFFFF, rng.getrandbits(64),
                                     rng.getrandbits(8), 0xFFFFFFFFFFFFFFFE)))
    _wf(mem, obj + 0xF0, [float(rng.randrange(-20, 20)) for _ in range(3)])
    mem.w16(obj + 0x10E, rng.choice((180, 1, 0, 0xFFFF, 0xFF24, 0xFF23, 0xFF00, 0x7FFF, rng.getrandbits(16))))
    mem.w16(obj + 0x140, rng.choice((0, 2, 8, 0x10, 0x20, 0x22, 0x26, rng.getrandbits(16))))
    if rng.random() < 0.4:
        item = _item(rig, rng)
        for off in range(0, 0x48, 4):
            mem.w32(obj + 0x148 + off, mem.u32(item + off))
        mem.w8(obj + 0x238, rng.choice((1, 1, 0x80)))
    else:
        mem.w8(obj + 0x238, 0)
    mem.w8(obj + 0x239, rng.choice((0, 0, 1)))
    mem.w8(obj + 0x23A, rng.choice((0, 0, 0, 1, 1, 2)))
    mem.w32(obj + 0x23C, rng.choice((f32(-0.4), f32(-0.1), f32(rng.uniform(-1, 1)))))
    mem.w32(obj + 0x240, rng.choice((f32(1.0), f32(1.0), f32(0.5), f32(2.5))))
    # the body
    mem.w32(obj + 0x190, rng.choice((f32(1.0), f32(1.0), f32(1.0), f32(0.5), f32(2.0), 0)))
    _wf(mem, obj + 0x194, [rng.choice((rng.uniform(0.0005, 0.05), rng.uniform(0.05, 2.0))) for _ in range(3)])
    body = [to_float(pos[0]) + rng.uniform(-3, 3), to_float(pos[1]) + rng.uniform(-3, 3), z + rng.uniform(-3, 3)]
    if rng.random() < 0.5:
        body = [to_float(pos[0]), to_float(pos[1]), z]
    _wf(mem, obj + 0x1A0, body)
    q = _quat(rng)
    _wf(mem, obj + 0x1AC, q)
    scale = 0.1 if still else rng.choice((1.0, 4.0, 15.0))
    _wf(mem, obj + 0x1BC, [rng.uniform(-scale, scale) for _ in range(3)])
    _wf(mem, obj + 0x1C8, [rng.uniform(-scale, scale) for _ in range(3)])
    if not still and rng.random() < 0.3:
        mem.w32(obj + 0x1C4, rng.choice((f32(-1.0), f32(-2.0), f32(0.0), f32(1.0), f32(-0.95))))
    r = _rot(q) if rng.random() < 0.85 else [rng.uniform(-1.2, 1.2) for _ in range(9)]
    _wf(mem, obj + 0x1D4, r)
    _wf(mem, obj + 0x1F8, [rng.uniform(-0.05, 0.05) if k % 4 else rng.uniform(0.001, 0.1) for k in range(9)])
    _wf(mem, obj + 0x21C, [rng.uniform(-0.3, 0.3) for _ in range(3)])
    ground = z - rng.choice((rng.uniform(-10, 60), 25.0, 2.0, 0.0)) if near else rng.uniform(-500, 500)
    mem.w32(obj + 0x228, f32(ground))
    mem.w32(obj + 0x234, rng.choice((0, 0, 0, 0, 1, 3, 40)))
    mem.w32(obj + 0x22C, rng.getrandbits(32))
    for slot in range(2):
        mem.w32(w.players[slot] + 0x18, f32(z + rng.choice((-200.0, 0.0, 119.0, 121.0, 300.0))))
    return obj


def generate(rig, key, rng):
    _globals(rig, rng)
    rig.world.terrain = None
    rig.world.pool = 'random'
    rig.world.zero_fresh()
    obj = rng.choice(rig.world.blocks)
    if key == 'gutrun':
        _prop(rig, rng, obj, 0x50F3B8)
        mem = rig.emu.mem
        mem.w32(obj + 0x248, rng.choice((0, 1, 2, 4, 8, 9, 3, 5, 6, rng.getrandbits(32))))
        mem.w32(obj + 0x24C, rng.choice((f32(-0.5), f32(-1.5), f32(-2.5), f32(-1.0), f32(-2.0), f32(0.0),
                                         f32(0.5), f32(rng.uniform(-4, 4)))))
        mem.w32(obj + 0x25C, rng.choice((0, 1, 2, 2, 5)))
        mem.w8(obj + 0x260, rng.choice((0, 0, 1)))
        return (obj,)
    _prop(rig, rng, obj, 0x511BA8)
    return (obj,)


# ---------------------------------------------------------------------------------------
# Lives: a real constructor builds the object, then frames
# ---------------------------------------------------------------------------------------
def _life_world(rig, rng):
    w, mem = rig.world, rig.emu.mem
    _globals(rig, rng, sim_frame=rng.randrange(0, 1 << 20))
    mem.w32(PR.G_NUM_PLAYERS, rng.choice((1, 2)))
    mem.w32(PR.G_ALIVE_PLAYERS, 0)
    mem.w32(PR.G_PLAYER_OBJ, w.players[0])
    base = rng.uniform(-100, 100)
    terrain = Terrain(rng, base)
    origin = (rng.uniform(-3000, 3000), rng.uniform(-3000, 3000))
    terrain.origin = origin
    if rng.random() < 0.3:
        terrain.wall = origin[0] + rng.uniform(2, 20)
    if rng.random() < 0.2:
        terrain.water = base + rng.uniform(-5, 15)
    w.terrain = terrain
    w.pool = rng.choice(('fresh', 'fresh', 'fresh', 'none'))
    w.zero_fresh()
    mem.w32(w.players[0] + 0x18, f32(base + rng.choice((0.0, 50.0, 50.0, 150.0))))
    pos = [f32(origin[0]), f32(origin[1]), f32(base + rng.uniform(10, 60))]
    return pos


def build_gut(rig, rng, obj):
    mem = rig.emu.mem
    mem.write(obj, bytes(0x280))
    pos = _life_world(rig, rng)
    mem.w32(PP.R3.G_GORE, rng.choice((0, 1, 2, 2)))
    for j in range(3):
        mem.w32(rig.world.argbuf + 4 * j, pos[j])
    kind = rng.choice((0, 1, 2, 3, 2, 7))
    bits = rng.choice((0, 1, 2, 3, 4, 8, 9))
    rig.build(PP.GUTCHUNK_CTOR, (obj, rig.world.argbuf, kind, bits), fregs=(1.0,))
    if rng.random() < 0.15:
        mem.w8(obj + 0x23A, 1)
    return obj


def build_bone(rig, rng, obj):
    w, mem = rig.world, rig.emu.mem
    mem.write(obj, bytes(0x280))
    pos = _life_world(rig, rng)
    for j in range(3):
        mem.w32(w.argbuf + 4 * j, pos[j])
    bits = rng.choice((1, 2, 0x80, 0x400, 1 << 40, rng.getrandbits(64)))
    launch = 0x107 if rng.random() < 0.7 else rng.choice((0x216, 0x19, 0x8107, 0x2107))
    regs = (obj, w.argbuf, rng.randrange(0x10000), 0x00A40000, w.blocks[0] + 0x114, w.names[0], w.names[3],
            w.names[2])
    rig.build(PP.PHPROP_CTOR2, regs, fregs=(1.0,), stack=(bits, launch, 0))
    if rng.random() < 0.15:
        mem.w8(obj + 0x23A, 1)
    return obj


def build_prop(rig, rng, obj):
    w, mem = rig.world, rig.emu.mem
    mem.write(obj, bytes(0x280))
    pos = _life_world(rig, rng)
    for j in range(3):
        mem.w32(w.argbuf + 4 * j, pos[j])
    item = _item(rig, rng) if rng.random() < 0.4 else 0
    launch = rng.choice((0xB41, 0x19, 0x9, 0x11, 0x216, 0x107, 0x2041, 0x4011, 0x10021, 0x8001, 0x1))
    mask = rng.choice((1, 2, 3, 0x30, 0x80000000))
    lump = rng.choice((w.names[0], w.names[0], w.names[4]))
    regs = (obj, w.argbuf, lump, w.names[1], w.names[2], mask, launch, item)
    rig.build(PP.PHPROP_CTOR, regs, fregs=(rng.choice((1.0, 1.0, 0.5, 2.0)),))
    if rng.random() < 0.2:
        mem.w8(obj + 0x23A, 1)
    return obj


def run_life(rig, key, rng, life_seed):
    addr, method, builder = LIVES[key]
    obj = rig.world.blocks[1]
    globals()[builder](rig, rng, obj)
    mem = rig.emu.mem
    frame0 = mem.u32(PR.G_SIM_FRAME)
    frames, bad, end, draws = 0, [], 'frames', 0
    for f in range(OPTIONS['frames']):
        mem.w32(PR.G_SIM_FRAME, (frame0 + f) & M32)
        result = rig.compare(addr, method, (obj,), life_seed * 1009 + f)
        frames += 1
        draws += result['draws']
        problems = [(prop, result[prop]) for prop in ('fault', 'calls', 'writes', 'seed') if result[prop]]
        if problems:
            bad.append((f, problems, result))
            break
        names = [name for name, args in rig.calls]
        if 'obj_delete' in names:
            rest = any(name == 'pool_new' and args[0] in (0x148, 0x190) for name, args in rig.calls)
            end = 'rest' if rest else 'below player'
            break
        if 'GutChunk_dtor' in names or 'PhProp_dtor' in names:
            end = 'destroyed'
            break
    return frames, bad, end, draws


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
        elif item == '--lives':
            OPTIONS['lives'] = int(args.pop(0), 0)
        elif item == '--frames':
            OPTIONS['frames'] = int(args.pop(0), 0)
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
        print('difftest_phprop_run: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('difftest_phprop_run: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    RC.C.set_fpu('ps2')
    DC.OPTIONS['verbose'] = OPTIONS['verbose']
    cases = max(OPTIONS['cases'] // 10, 1) if OPTIONS['quick'] else OPTIONS['cases']
    lives = max(OPTIONS['lives'] // 6, 1) if OPTIONS['quick'] else OPTIONS['lives']
    started = time.time()
    rig = Rig(elf)
    coverage = Coverage(rig.emu.mem)
    rng = random.Random(OPTIONS['seed'])
    counts, total = {}, 0
    for key, (addr, method) in ENTRIES.items():
        if OPTIONS['filter'] and OPTIONS['filter'] not in key:
            continue
        bad = {'fault': [], 'calls': [], 'writes': [], 'seed': []}
        draws, own = 0, rig.own_draws
        for n in range(cases):
            call_seed = OPTIONS['seed'] * 1000003 + total
            case = generate(rig, key, rng)
            result = rig.compare(addr, method, case, call_seed)
            total += 1
            draws += result['draws']
            failed = False
            for prop in bad:
                if result[prop]:
                    failed = True
                    bad[prop].append('case %d %s: %s' % (n, key, result[prop]))
            if failed and OPTIONS['trace_first']:
                print('first mismatch: %s case %d' % (key, n))
                for prop in bad:
                    if result[prop]:
                        print('  %s: %s' % (prop, result[prop]))
                print('  model calls:')
                for call in result['model_calls']:
                    print('    ' + DC.fmt_call(call))
                print('  original calls:')
                for call in result['emu_calls'] or ():
                    print('    ' + DC.fmt_call(call))
                return 1
        counts[key] = (cases, sum(len(v) for v in bad.values()), draws, rig.own_draws - own, '')
        for prop, examples in bad.items():
            DC.report('%s %s' % (key, prop), len(examples), cases, prop, examples)
    for key in LIVES:
        if OPTIONS['filter'] and OPTIONS['filter'] not in key:
            continue
        draws_before, own = 0, rig.own_draws
        examples, frames, ends = [], 0, {}
        for n in range(lives):
            life_seed = OPTIONS['seed'] * 7919 + total
            total += 1
            got, bad, end, drawn = run_life(rig, key, rng, life_seed)
            frames += got
            draws_before += drawn
            ends.setdefault(end, []).append(got)
            for f, problems, result in bad:
                examples.append('life %d frame %d: %s' % (n, f, problems))
                if OPTIONS['trace_first']:
                    print('first mismatch: %s life %d frame %d %s' % (key, n, f, problems))
                    print('  model calls:')
                    for call in result['model_calls']:
                        print('    ' + DC.fmt_call(call))
                    print('  original calls:')
                    for call in result['emu_calls'] or ():
                        print('    ' + DC.fmt_call(call))
                    return 1
        counts[key] = (lives, len(examples), draws_before, rig.own_draws - own,
                       '%d frames; ends %s' % (frames, ', '.join(
                           '%s %d (frames %d-%d, median %d)' % (end, len(f), min(f), max(f), sorted(f)[len(f) // 2])
                           for end, f in sorted(ends.items()))))
        DC.report('%s frames' % key, len(examples), lives, 'lives, state compared every frame', examples)
    if rig.unknown:
        DC.report('unknown calls', len(rig.unknown), total, 'calls to neither real nor stubbed addresses',
                  ['%x x%d' % kv for kv in sorted(rig.unknown.items())])
    coverage.pcs = rig.pcs
    print()
    print('cases (lives) per entry / with any mismatch / shared draws / own draws (model)')
    for key, (n, bad_n, draws, own, note) in counts.items():
        print('  %-9s %6d / %d / %d / %d  %s' % (key, n, bad_n, draws, own, note))
    print('coverage of the original as executed here (basic blocks, instructions):')
    for part in BODIES:
        b, bt, i, it = coverage.numbers(part)
        print('  %-32s blocks %4d of %4d  instructions %4d of %4d' % (part, b, bt, i, it))
        if OPTIONS['verbose'] and b != bt:
            print('      never entered: %s' % ' '.join('%06x' % a for a in coverage.missing(part)))
        if OPTIONS['verbose'] and i != it:
            spans = coverage.parts[part][0]
            idle = [pc for s, e in spans for pc in range(s, e, 4) if pc not in coverage.pcs]
            print('      instructions never executed: %s' % ' '.join('%06x' % a for a in idle[:12]))
    print('%d cases and lives in %.0f s' % (total, time.time() - started))
    return 0 if all(ok for _name, ok in DC.RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
