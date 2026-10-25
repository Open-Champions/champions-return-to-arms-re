#!/usr/bin/env python3
"""difftest_combat_round3.py - compare the bodies tools/ref_combat_round3.py adds with the
game's own code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_combat_round3.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                          [--cases N] [-k TEXT] [-v]

For each entry the original runs in tools/ee_emu.py (an instruction interpreter, not a
console).  The same inputs go through ref_combat_round3.Model on a copy-on-write view.
Equal must be: calls outside the model, in order, with arguments; bytes stored outside
the stack; the shared seed and the draw count; the result.  Floats are 32-bit patterns.

Real: the entry, GameObject_ctor 0x14cb10 (inside DiseaseCloud_ctor) and GameObject_rand
0x1509d0 (inside DiseaseCloud_run).  Everything else is a recording stub answered by the
same seeded script on both sides.  PhProp_ctor and Creature_ctor stay stubs: this round
executes the bytes GutChunk and the phantom store around those calls, not those
constructors again.
"""
import hashlib
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError                 # noqa: E402
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_skills_a as SA                       # noqa: E402
import ref_combat_ranged as RR                  # noqa: E402
import ref_combat_round3 as R3                  # noqa: E402
import difftest_combat_runtime as D             # noqa: E402
import difftest_creature as DC                  # noqa: E402

EXPECTED_SHA256 = D.EXPECTED_SHA256
ROOT = D.ROOT
M32 = 0xFFFFFFFF
LIB_LO, LIB_HI = 0x3A5000, 0x3C0000
f32 = D.f32
is_stack = D.is_stack
Ext = RC.Ext

OPTIONS = {'quick': False, 'seed': 20973, 'cases': 40, 'filter': None, 'verbose': False}

ENTRIES = {
    # key -> (address, argument kinds, float count, result kind, method, body)
    'diseaseCloudCtor': (0x2CE610, 'ivii', 0, 'n', 'diseasecloud_ctor', (0x2CE610, 0x2CE6E0)),
    'diseaseCloudRun': (0x2CE6E0, 'i', 0, 'n', 'diseasecloud_run', (0x2CE6E0, 0x2CEF7C)),
    'gutChunkCtor': (0x201958, 'ivii', 0, 'n', 'gutchunk_ctor', (0x201958, 0x201A2C)),
    'stancePhantomCtor': (0x1618D4, 'iiiii', 0, 'n', 'strongstance_phantom_ctor', (0x1618D4, 0x161A50)),
    'stancePhantomRun': (0x161A54, 'i', 0, 'n', 'strongstance_phantom_run', (0x161A54, 0x161AD8)),
    'missileKind1': (0x15153C, 'i', 0, 'n', 'missile_run', (0x15153C, 0x15253C)),
    'missileKind2': (0x15153C, 'i', 0, 'n', 'missile_run', (0x15153C, 0x15253C)),
    'missileKind5': (0x15153C, 'i', 0, 'n', 'missile_run', (0x15153C, 0x15253C)),
    'missileKind6': (0x15153C, 'i', 0, 'n', 'missile_run', (0x15153C, 0x15253C)),
}
REAL = {0x14CB10, 0x1509D0}
REAL_SPANS = ((0x14CB10, 0x14CF84),)

EXTS = {
    'handle_link': Ext(0x1A1738, 'ppp', 0, 'n'),
    'obj_getPropInt': Ext(0x14C880, 'ppi', 0, 'i'),
    'obj_runEveryFrame': Ext(0x14F248, 'p', 0, 'n'),
    'particle_spawn': Ext(0x18F3F8, 'pvv', 1, 'n'),
    'world_collectObjectsInBox': Ext(0x14A928, 'vvni', 0, 'n'),
    'damage_apply': Ext(0x1E8230, 'ppiiiiDi', 2, 'i'),
    'PhProp_ctor': Ext(0x155A0C, 'pvpppiii', 1, 'n'),
    'Creature_ctor': Ext(0x109D68, 'iiviii', 1, 'n'),
    'anim_clear': Ext(0x1707B0, 'p', 0, 'n'),
    'res_find': Ext(0x17365C, 'pp', 0, 'i'),
    'anim_startBlendInOut': Ext(0x16CEB0, 'ppi', 2, 'n'),
    'Creature_stepAnim': Ext(0x1162B0, 'p', 1, 'n'),
    'Creature_applyKnockback': Ext(0x115EB8, 'p', 1, 'n'),
    'Creature_moveBy': Ext(0x113C48, 'pv', 0, 'n'),
    'obj_delete': Ext(0x14F200, 'p', 0, 'n'),
    'Creature.v1': Ext(0, 'ii', 0, 'n'),
    'obj_moveAndCollide': Ext(0x1509F8, 'iv', 0, 'i'),
    'fx_spawn': Ext(0x1EF270, 'iv', 0, 'n'),
    'ParticleProp_ctor': Ext(0x1549E8, 'ivi', 0, 'n'),
    'player_getPassiveLevel': Ext(0x1BED48, 'ii', 0, 'i'),
    'fx_ringBurst': Ext(0x1F3D00, 'v', 1, 'n'),
    'pool_new': Ext(0x14FDB8, 'i', 0, 'i'),
    'sound_playOnObject': Ext(0x214230, 'pp', 1, 'n'),
    'sound_playSample': Ext(0x2134E8, 'iv', 3, 'i'),
    'light_relink': Ext(0x14A528, 'p', 0, 'n'),
    'world_damageInRadius': Ext(0x161270, 'iviiii', 2, 'n'),
}
_LIGHT = Ext(0x201BD8, 'ivii', 8, 'n')
_LIGHT.stack = 4
EXTS['LightEffect_ctor'] = _LIGHT


def desc_canon(mem, addr):
    """Same reading as tools/difftest_skills_a.py: an empty item record with four slots."""
    if addr == 0 or not is_stack(addr):
        return addr
    ok = (all(mem.u16(addr + 0x10 + 2 * k) == 0 for k in range(8))
          and mem.u8(addr + 0x20) == 0xFF and mem.u8(addr + 0x21) == 0xFF)
    slots = []
    for k in range(4):
        base = addr + 0x24 + 8 * k
        slots.append(None if mem.u16(base) == 0xFFFF else tuple(mem.u16(base + 2 * j) for j in range(4)))
    if not ok:
        return ('desc?', bytes(mem.read(addr + 0x10, 0x34)).hex())
    return ('desc',) + tuple(slots)


class Res:
    def __init__(self, ret=0, f=0, outs=()):
        self.ret, self.f, self.outs = list(outs) and ret, f, list(outs)
        self.ret = ret


class World:
    def __init__(self, emu):
        self.emu, self.mem = emu, emu.mem
        self.argbuf = emu.alloc(0x200)
        self.clouds = [emu.alloc(0x80) for _ in range(2)]
        self.guts = [emu.alloc(0x280) for _ in range(2)]
        self.phantoms = [emu.alloc(0x400) for _ in range(2)]
        self.targets = [emu.alloc(0x40) for _ in range(2)]
        self.class_def = emu.alloc(0x20)
        self.victims = [emu.alloc(0x30) for _ in range(4)]
        self.missiles = [emu.alloc(0x200) for _ in range(2)]
        self.light = emu.alloc(0xC0)
        self.owners = [emu.alloc(0x400) for _ in range(2)]
        self.collide = 0
        self.give_light = 0
        self.nodes = {}
        for obj in self.clouds + self.guts + self.phantoms + self.targets + self.victims + self.owners:
            node = emu.alloc(0x10)
            self.mem.w32(node + 0xC, obj)
            self.nodes[obj] = node
        self.case_pool = list(self.victims)
        dtor = emu.mem.u32(R3.DC_VT + 0xC)
        self.dtor = dtor
        self.missile_dtor = emu.mem.u32(RR.VT_MISSILE + 0xC)
        self.link_node = emu.alloc(0x10)

    def respond(self, name, args, view, rng):
        handler = getattr(self, 'on_' + name.replace('.', '_'), None)
        return handler(args, view, rng) if handler is not None else Res()

    def on_obj_getPropInt(self, args, view, rng):
        return Res(0)

    def on_res_find(self, args, view, rng):
        return Res(0x00A10000)

    def on_world_collectObjectsInBox(self, args, view, rng):
        pool = list(self.case_pool)
        rng.shuffle(pool)
        cap = args[2] if len(args) > 2 else 0x40
        n = rng.randrange(0, min(len(pool), max(cap - 1, 0)) + 1)
        return Res(outs=[pool[:n]])

    def on_Creature_ctor(self, args, view, rng):
        """Leaves the class word the phantom then reads.  The constructor itself stays
        a callback (executed by tools/difftest_arena_monsters.py)."""
        obj, _name, _pos, _facing, class_def, _props = args[:6]
        view.poke(obj + 0x24, 4, class_def)
        return Res()

    def on_obj_moveAndCollide(self, args, view, rng):
        return Res(self.collide)

    def on_pool_new(self, args, view, rng):
        return Res(self.light if self.give_light else 0)


class Rig:
    def __init__(self, elf):
        emu = self.emu = EE(elf, fpu_model='ps2')
        emu.div_zero = 'r5900'
        self.world = World(emu)
        self.real = set(REAL)
        emu.follow = self.real
        self.names = {}
        for name, ext in EXTS.items():
            addr = ext.addr
            if name == 'Creature.v1':
                addr = self.world.dtor
            if not addr or addr in self.real:
                continue
            self.names[addr] = name
            emu.stub(addr, function=self.make_stub(name, ext), name=name)
        missile = self.world.missile_dtor
        if missile and missile not in self.names and missile not in self.real:
            self.names[missile] = 'Creature.v1'
            emu.stub(missile, function=self.make_stub('Creature.v1', EXTS['Creature.v1']), name='Creature.v1')
        self.calls, self.unknown, self.pcs = [], {}, set()
        self.partial, self.partial_ops = [], {}
        spans = list(REAL_SPANS) + [entry[5] for entry in ENTRIES.values()]
        for start, end in spans:
            for pc in range(start, end, 4):
                word = emu.mem.u32(pc)
                if word >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = word >> 26
                    emu.hook(pc, self.partial_hook(pc, (word >> 21) & 31, ee_emu.sx16(word)))
        self.eview = D.View(emu.mem.load, self._epoke)
        self.touched = set()
        self.script_rng = None

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
        for kind in ext.ints:
            if kind == '-':
                continue
            index = len(canon) + len(outs)
            # integer registers are consumed even by out-kinds
            reg = emu.r[4 + index] & M32
            if kind in 'ipe':
                canon.append(reg)
            elif kind == 'v':
                canon.append(tuple(mem.u32(reg + 4 * j) for j in range(3)))
            elif kind == 'D':
                canon.append(desc_canon(mem, reg))
            elif kind == 'n':
                outs.append((kind, reg))
            else:
                canon.append(reg)
        for j in range(ext.floats):
            canon.append(emu.f[12 + j] & M32)
        sp = emu.r[29] & M32
        for j in range(getattr(ext, 'stack', 0)):
            canon.append(mem.u32(sp + 8 * j))
        return tuple(canon), outs

    def make_stub(self, name, ext):
        def stub(emu):
            canon, outs = self.decode(ext, emu)
            self.calls.append((name, canon))
            res = self.world.respond(name, canon, self.eview, self.script_rng)
            given = list(res.outs)
            for kind, ptr in outs:
                value = given.pop(0) if given else []
                if kind == 'n' and ptr:
                    for j, obj in enumerate(value):
                        emu.mem.w32(ptr + 4 * j, obj)
                    emu.mem.w32(ptr + 4 * len(value), 0)
            return res.ret
        return stub

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                ext = EXTS.get(name)
                if res.outs:
                    return res.outs[0]
                if ext is not None and ext.ret == 'n':
                    return None
                return res.ret & M32
            return answer

    def compare(self, key, args, call_seed):
        addr, kinds, _nfloat, ret_kind, method, _body = ENTRIES[key]
        emu, mem = self.emu, self.emu.mem
        seed_before = mem.u32(SA.G_SIM_FRAME) and mem.u32(RC.G_RAND_SEED)
        seed_before = mem.u32(RC.G_RAND_SEED)
        mview = D.ModelView(mem)
        cls = R3.ArrowModel if key.startswith('missileKind') else R3.Model
        model = cls(mview, Rig.Callbacks(self, D.View(mview.load, mview.poke), random.Random(call_seed)))
        try:
            mret = getattr(model, method)(*args)
        except EmuError as exc:
            return 'model stopped: %s' % exc
        self.calls, self.touched, self.partial = [], set(), []
        self.script_rng = random.Random(call_seed)
        emu.reset_log()
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x800
        regs, scratch, nfloat = [], self.world.argbuf, 0
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
                regs.append(value & M32)
        try:
            eret = emu.call(addr, *regs, max_steps=4000000)
        except EmuError as exc:
            return 'original stopped: %s' % exc
        self.pcs.update(emu.trace)
        for call in emu.calls:
            if call.target not in self.real and call.target not in self.names and not LIB_LO <= call.target < LIB_HI:
                self.unknown[call.target] = self.unknown.get(call.target, 0) + 1
        problems = []
        if self.unknown:
            problems.append('unknown calls %s' % sorted('%x' % a for a in self.unknown))
        if model.calls != self.calls:
            problems.append(DC.describe_calls(model.calls, self.calls))
        lo, hi = self.world.argbuf, self.world.argbuf + 0x200
        stored = self.stored_bytes(lo, hi)
        mstored = set()
        for a, size, _v in model.writes:
            if not is_stack(a):
                mstored.update(range(a, a + size))
        diff = [a for a in sorted(stored | mstored | self.touched | mview.touched)
                if mem.load(a, 1) != mview.load(a, 1)]
        if stored != mstored or diff:
            problems.append('writes: only original %s; only model %s; values differ at %s' % (
                sorted('%x' % a for a in stored - mstored)[:8],
                sorted('%x' % a for a in mstored - stored)[:8],
                ['%x:%02x/%02x' % (a, mem.load(a, 1), mview.load(a, 1)) for a in diff[:8]]))
        expect = seed_before
        for _ in range(model.draws):
            expect = (expect * 0x19660D + 0x3C6EF35F) & M32
        if not mem.u32(RC.G_RAND_SEED) == mview.load(RC.G_RAND_SEED, 4) == expect:
            problems.append('seed: model draws %d original %08x model %08x' % (
                model.draws, mem.u32(RC.G_RAND_SEED), mview.load(RC.G_RAND_SEED, 4)))
        if ret_kind == 'i' and (eret & M32) != ((mret or 0) & M32):
            problems.append('result %08x / %08x' % (eret & M32, (mret or 0) & M32))
        for a, byte in mview.bytes.items():
            mem.store(a, 1, byte)
        return problems


def _pos(rng):
    return tuple(f32(rng.uniform(-400, 400)) for _ in range(3))


def _zero(mem, addr, size):
    for off in range(0, size, 4):
        mem.w32(addr + off, 0)


def generate(rig, key, rng, n=0):
    w, mem = rig.world, rig.emu.mem
    mem.w32(SA.G_SIM_FRAME, rng.randrange(1, 1 << 20))
    mem.w32(RC.G_RAND_SEED, rng.getrandbits(32))
    if key == 'diseaseCloudCtor':
        obj = rng.choice(w.clouds)
        _zero(mem, obj, 0x70)
        owner = rng.choice((0, 0, rng.choice(w.victims)))
        return (obj, _pos(rng), rng.randrange(0, 8), owner)
    if key == 'diseaseCloudRun':
        obj = w.clouds[0]
        _zero(mem, obj, 0x70)
        mem.w32(obj + 0x48, R3.DC_VT)
        pos = _pos(rng)
        for i in range(3):
            mem.w32(obj + 0x10 + 4 * i, pos[i])
        mem.w32(obj + 0x44, rng.getrandbits(32))
        cap = rng.choice((0, 0, 10, 10, 20, 48))
        mem.w32(obj + 0x58, cap)
        radius = rng.choice((0.0, 4.0, 9.5, 10.0, 20.0, 47.5))
        mem.w32(obj + 0x5C, f32(radius))
        mem.w32(obj + 0x60, rng.choice((1, 20, 20, 100)))
        frame = mem.u32(SA.G_SIM_FRAME)
        # The first cases are fixed so the damage walk, the empty-owner skip, growth and
        # expiry are not left to the draw.  Later cases vary.
        if n == 0:
            frame = 60
            mem.w32(SA.G_SIM_FRAME, frame)
            end, cap, radius = frame - 1, 10, 10.0
        elif n == 1:
            frame = 60
            mem.w32(SA.G_SIM_FRAME, frame)
            end, cap, radius = frame + 100, 0, 10.0
        elif n == 2:
            frame = 30
            mem.w32(SA.G_SIM_FRAME, frame)
            end, cap, radius = frame + 100, 10, 9.0
        elif n == 3:
            frame = 31
            mem.w32(SA.G_SIM_FRAME, frame)
            end, cap, radius = frame + 50, 20, 40.0
        else:
            end = rng.choice((frame, frame + 1, frame + 240, frame + 10))
            if rng.random() < 0.15:
                end = frame - 1 if frame else 0
        mem.w32(obj + 0x54, end & M32)
        mem.w32(obj + 0x58, cap)
        mem.w32(obj + 0x5C, f32(radius))
        owner = rng.choice(w.victims)
        node = w.nodes[owner]
        if n == 2:
            mem.w32(obj + 0x4C, node)
            mem.w32(node + 0xC, owner)
            mem.w32(owner + 0xC, 0x20)
            for victim in w.victims:
                mem.w32(victim + 0xC, 0x20 if victim != owner else 0x40)
            w.case_pool = list(w.victims)
            return (obj,)
        if rng.random() < 0.2:
            mem.w32(obj + 0x4C, 0)
        else:
            mem.w32(obj + 0x4C, node)
            mem.w32(node + 0xC, owner)
        flags = (0x20, 0x40, 0x60, 0x28, 0)
        mem.w32(owner + 0xC, rng.choice(flags))
        for victim in w.victims:
            mem.w32(victim + 0xC, rng.choice(flags))
        w.case_pool = list(w.victims)
        if rng.random() < 0.3:
            w.case_pool.append(owner)
        return (obj,)
    if key == 'gutChunkCtor':
        obj = rng.choice(w.guts)
        _zero(mem, obj, 0x270)
        pos = _pos(rng)
        for i in range(3):
            mem.w32(obj + 0x10 + 4 * i, pos[i])
        mem.w32(R3.G_GORE, rng.choice((0, 1, 2, 3)))
        return (obj, pos, rng.randrange(0, 4), rng.choice((0, 1, 2, 3, 5)))
    if key == 'stancePhantomCtor':
        obj = rng.choice(w.phantoms)
        target = rng.choice(w.targets)
        _zero(mem, obj, 0x3E0)
        _zero(mem, target, 0x40)
        pos = _pos(rng)
        for i in range(3):
            mem.w32(target + 0x10 + 4 * i, pos[i])
        mem.w16(target + 0x38, rng.randrange(0x10000))
        mem.w32(target + 0x24, w.class_def)
        mem.w32(w.class_def, rng.choice((0, 0x550200)))
        mem.w16(target + 0x2E0, rng.randrange(0x10000))
        mem.w32(obj + 0xC, rng.choice((0, 0x20)))
        mem.w64(obj + 0xA8, rng.choice((0, 1)))
        return (obj, target, 0x550100, rng.choice((0, 1, 4, -2 & M32)), rng.choice((0, 0, 1)))
    if key.startswith('missileKind'):
        obj = rng.choice(w.missiles)
        _zero(mem, obj, 0x1E0)
        frame = mem.u32(SA.G_SIM_FRAME) or 1
        mem.w32(SA.G_SIM_FRAME, frame)
        mem.w32(RC.G_LEVEL_FLAGS, 0)
        pos = _pos(rng)
        vel = _pos(rng)
        for i in range(3):
            mem.w32(obj + 0x10 + 4 * i, pos[i])
            mem.w32(obj + 0x1B0 + 4 * i, vel[i])
        mem.w32(obj + 0x48, RR.VT_MISSILE)
        mem.w32(obj + 0xD0, {'missileKind1': 1, 'missileKind5': 5, 'missileKind6': 6}.get(key, 2))
        mem.w32(obj + 0x44, rng.getrandbits(32))
        mem.w32(obj + 0xD8, rng.choice((1, 12, 40, 100)))
        mem.w32(obj + 0xEC, (frame + 80) & M32)
        mem.w16(obj + 0xFA, 0)
        mem.w16(obj + 0xFC, rng.randrange(0x10000))
        mem.w32(obj + 0x1BC, 0)
        mem.w32(obj + 0x4C, 0)
        w.collide = 0
        w.give_light = 0
        if n == 0:
            return (obj,)
        if n == 1:
            w.collide, w.give_light = 1, 1
            return (obj,)
        if n == 2:
            owner = w.owners[0]
            w.collide, w.give_light = 1, 0
            mem.w32(obj + 0x4C, w.nodes[owner])
            mem.w32(obj + 0x1BC, 0x11)
            mem.w16(obj + 0xFA, 0x100)
            if key == 'missileKind6':
                mem.w32(owner + 0xC, 0x40)
                mem.w32(owner + 0x3C8, 3)
            return (obj,)
        if n == 3:
            w.collide, w.give_light = 1, 1
            mem.w32(obj + 0x4C, w.nodes[w.owners[1]])
            return (obj,)
        w.collide = rng.choice((0, 0, 1, 1, 1, 3))
        w.give_light = rng.choice((0, 1))
        if rng.random() < 0.5:
            mem.w32(obj + 0x4C, w.nodes[rng.choice(w.owners)])
        if rng.random() < 0.4:
            mem.w32(obj + 0x1BC, rng.choice((1, 7, 0x11)))
        if rng.random() < 0.3:
            mem.w16(obj + 0xFA, rng.choice((1, 0x100, 0x7FFF, 0x8000)))
        if rng.random() < 0.1:
            mem.w8(obj + 0xCC, 1)
        return (obj,)
    obj = rng.choice(w.phantoms)
    _zero(mem, obj, 0x3E0)
    mem.w32(obj + 0x3CC, f32(rng.choice((0.0, 0.5, 1.0, 1.5, 2.0, 75.0, 240.0))))
    return (obj,)


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
        elif item == '-v':
            OPTIONS['verbose'] = True
        else:
            elf = item
    if elf is None:
        elf = os.path.join(ROOT, 'SLUS_209.73')
    if not os.path.exists(elf):
        alt = os.path.expanduser('~/champions-re/SLUS_209.73')
        elf = alt if os.path.exists(alt) else elf
    if not os.path.exists(elf):
        print('difftest_combat_round3: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('difftest_combat_round3: not SLUS_209.73 US v2.00 - skipped')
        return 0
    C.set_fpu('ps2')
    cases = max(OPTIONS['cases'] // 10, 2) if OPTIONS['quick'] else OPTIONS['cases']
    started = time.time()
    ok_all = True
    print('%-22s %8s %8s  first problem' % ('entry point', 'compared', 'failed'))
    for index, key in enumerate(ENTRIES):
        if OPTIONS['filter'] and OPTIONS['filter'].lower() not in key.lower():
            continue
        rig = Rig(elf)
        rng = random.Random(OPTIONS['seed'] * 31 + index)
        compared = failed = 0
        shown = []
        for n in range(cases):
            call = generate(rig, key, rng, n)
            problems = rig.compare(key, call, OPTIONS['seed'] * 1000003 + index * 7919 + n)
            if isinstance(problems, str):
                failed += 1
                compared += 1
                if len(shown) < 4:
                    shown.append(problems)
                continue
            compared += 1
            if problems:
                failed += 1
                if len(shown) < 4:
                    shown.append(problems[0][:500])
        ok_all = ok_all and not failed
        body = ENTRIES[key][5]
        covered = sum(1 for pc in rig.pcs if body[0] <= pc < body[1])
        size = (body[1] - body[0]) // 4
        print('%-22s %8d %8d  %s' % (key, compared, failed, '' if not shown else shown[0][:120]))
        missed = [pc for pc in range(body[0], body[1], 4) if pc not in rig.pcs]
        shown_miss = ' '.join('%x' % pc for pc in missed[:16])
        if len(missed) > 16:
            shown_miss += ' +%d' % (len(missed) - 16)
        print('%-22s %s' % ('', 'instructions %d/%d%s' % (
            covered, size, '' if not missed else '  missed %s' % shown_miss)))
        if OPTIONS['verbose']:
            for line in shown:
                print('   ', line[:400])
        if rig.unknown and OPTIONS['verbose']:
            print('    unknown', sorted('%x:%d' % item for item in rig.unknown.items()))
    print('round3 difftest %s in %.1fs' % ('PASS' if ok_all else 'FAIL', time.time() - started))
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
