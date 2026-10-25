#!/usr/bin/env python3
"""difftest_combat_round6.py - compare tools/ref_combat_round6.py with the game's own code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_combat_round6.py [path/to/SLUS_209.73] [--seed N] [-k TEXT]

For each entry the original runs in tools/ee_emu.py (an instruction interpreter, not a
console).  The same inputs go through ref_combat_round6.  Equal must be: calls outside
the model, in order, with arguments; bytes stored outside the stack; the shared seed.
Floats are 32-bit patterns.

Real: the entry, and GameObject_rand where the entry draws.  MultiFireProjectile_onHit
also runs MultiFireProjectile_end, whose own entry is compared separately.
DiseaseCloud_ctor stays the round-3 callback.  Round 1-5 modules are not modified.
"""
import hashlib
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError, sx16          # noqa: E402
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_skills_a as SA                       # noqa: E402
import ref_combat_round6 as R6                  # noqa: E402
import difftest_combat_runtime as D             # noqa: E402
import difftest_creature as DC                  # noqa: E402

EXPECTED_SHA256 = D.EXPECTED_SHA256
M32 = 0xFFFFFFFF
LIB_LO, LIB_HI = 0x3A5000, 0x3C01A8
f32 = D.f32
is_stack = D.is_stack
Ext = RC.Ext

OPTIONS = {'seed': 20973, 'filter': None}

RAND, END = 0x1509D0, 0x2DA928
COS, SIN = 0x166630, 0x1666E0
SPELL_RAND, MAT34 = 0x16A964, 0x163B30
FN_DTOR, FN_ENEMY = 0x3E0100, 0x3E0120
FN_STAT10, FN_STAT13 = 0x3E0140, 0x3E0160
FN_SPELL, FN_MODEL = 0x3E0180, 0x3E01A0

ENTRIES = {
    'poisonGas': (0x1FD0F0, 'i', 'poison_gas_run', ((0x1FD0F0, 0x1FD54C), (0x1FD550, 0x1FD5B0))),
    'diseaseCorpse': (0x2CE4A4, 'i', 'disease_corpse_run', ((0x2CE4A4, 0x2CE610),)),
    'multifireHit': (0x2DA610, 'ii', 'multifire_on_hit', ((0x2DA610, 0x2DA928),)),
    'multifireEnd': (0x2DA928, 'ii', 'multifire_end', ((0x2DA928, 0x2DAA4C),)),
    'smokeGen': (0x31C898, 'i', 'smoke_gen_run', ((0x31C898, 0x31CAC4),)),
    'pustule': (0x30BDE0, 'i', 'pustule_run', ((0x30BDE0, 0x30C4AC),)),
    'arena': (0x305BBC, 'iv', 'arena_run', ((0x305BBC, 0x305E9C),)),
    'hornomen': (0x2FC684, 'iv', 'hornomen_run', ((0x2FC684, 0x2FCE8C),)),
    'hornCtor': (0x2FC574, 'iiii', 'hornomen_ctor', ((0x2FC574, 0x2FC610),)),
    'planarsteel': (0x2FB9B4, 'iv', 'planarsteel_run', ((0x2FB9B4, 0x2FC3AC),)),
    'planarCtor': (0x2FB728, 'iiii', 'planarsteel_ctor', ((0x2FB728, 0x2FB924),)),
}
ANGLES = {COS, SIN, SPELL_RAND}
FOLLOW = {
    'poisonGas': {RAND},
    'diseaseCorpse': set(),
    'multifireHit': {RAND, END},
    'multifireEnd': {RAND},
    'smokeGen': set(),
    'pustule': {RAND, COS, SIN},
    'arena': set(ANGLES),
    'hornomen': set(ANGLES) | {MAT34},
    'hornCtor': set(),
    'planarsteel': set(ANGLES),
    'planarCtor': set(),
}
EXTS = {
    'particle_spawn': Ext(0x18F3F8, 'pvv', 1, 'n'),
    'world_collectObjectsInBox': Ext(0x14A928, 'vvni', 0, 'n'),
    'damage_apply': Ext(0x1E8230, 'ppiiiiDi', 2, 'i'),
    'pool_new': Ext(0x14FDB8, 'i', 0, 'i'),
    'DiseaseCloud_ctor': Ext(0x2CE610, 'pvii', 0, 'n'),
    'obj_delete': Ext(0x14F200, 'p', 0, 'n'),
    'fx_spawn': Ext(0x1EF270, 'iv', 0, 'n'),
    'trail_release': Ext(0x192800, 'p', 0, 'n'),
    'res_find': Ext(0x17365C, 'ps', 0, 'i'),
    'sound_playOnObject': Ext(0x214230, 'pp', 1, 'n'),
    'sound_playAtPos': Ext(0x214428, 'pv', 1, 'n'),
    'terrain_height': Ext(0x183820, 'pv', 1, 'f'),
    'terrain_heightAtPoint': Ext(0x182F28, 'pv', 0, 'f'),
    'model_getSamplePointCount': Ext(0x1799C8, 'p', 0, 'i'),
    'model_getSamplePoint': Ext(0x178E18, 'ppviioOi', 1, 'n'),
    'particleGroup_create': Ext(0x18E880, '', 0, 'i'),
    'particleGroup_setMatrix': Ext(0x18E9E8, 'ip', 0, 'n'),
    'light_link': Ext(0x148AF8, 'p', 0, 'n'),
    'particleGroup_begin': Ext(0x18E958, 'i', 0, 'n'),
    'particleGroup_end': Ext(0x18E9A0, 'i', 0, 'n'),
    'light_relink': Ext(0x14A528, 'p', 0, 'n'),
    'glow_add': Ext(0x18FC78, 'viiiiiii', 2, 'n'),
    'Creature.v16': Ext(FN_MODEL, 'p', 0, 'i'),
    'Spell.v1': Ext(FN_SPELL, 'pi', 0, 'n'),
    'isNearView': Ext(0x1E77C0, 'p', 1, 'i'),
    'SmokeGen_stepParticles': Ext(0x31CAC8, 'p', 0, 'n'),
    'Creature.v1': Ext(FN_DTOR, 'ii', 0, 'n'),
    'Creature.v20': Ext(FN_ENEMY, 'ii', 0, 'i'),
    'Skill.v10': Ext(FN_STAT10, 'iii', 0, 'i'),
    'Skill.v13': Ext(FN_STAT13, 'iiiii', 0, 'i'),
    'libc_sprintf': Ext(0x3B7EF0, '-pi', 0, 's'),
}


def wanted(key):
    text = OPTIONS['filter']
    return not text or text.lower() in key.lower()


def desc_canon(mem, addr):
    """Same reading as tools/difftest_combat_round3.py."""
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
        self.ret, self.f, self.outs = ret, f, list(outs)


class World:
    def __init__(self, emu):
        self.emu, self.mem = emu, emu.mem
        mem = emu.mem
        mem.map(0x4D0000, 0x20000)
        self.argbuf = emu.alloc(0x100)
        self.gas = emu.alloc(0x80)
        self.corpse = emu.alloc(0x80)
        self.bolt = emu.alloc(0x90)
        self.smoke = emu.alloc(0x500)
        self.pustule = emu.alloc(0x180)
        self.world_word = emu.alloc(0x10)
        self.spell = emu.alloc(0x80)
        self.spell_vt = emu.alloc(0x20)
        self.creature_vt = emu.alloc(0x90)
        mem.map(0x503000, 0x1000)
        mem.map(0x4F8000, 0x1000)
        self._plant(mem, self.spell_vt, 1, FN_SPELL)
        self._plant(mem, self.creature_vt, 16, FN_MODEL)
        self.sample = (f32(3.0), f32(4.0), f32(5.0))
        self.sample_extra = (f32(0.0), f32(0.0), f32(1.0))
        self.samples = 4
        self.model_id = 0xD000
        self.skill = emu.alloc(0x80)
        self.skill_vt = emu.alloc(0x80)
        self.obj_vt = emu.alloc(0x20)
        self.owner_vt = emu.alloc(0xC0)
        self.owner = emu.alloc(0x400)
        self.node = emu.alloc(0x20)
        self.trail = emu.alloc(0x10)
        self.block = emu.alloc(0x80)
        self.victims = [emu.alloc(0xC0) for _ in range(6)]
        self._plant(mem, self.obj_vt, 1, FN_DTOR)
        self._plant(mem, self.owner_vt, 20, FN_ENEMY)
        self._plant(mem, self.skill_vt, 10, FN_STAT10)
        self._plant(mem, self.skill_vt, 13, FN_STAT13)
        mem.w32(self.skill + 0x60, self.skill_vt)
        mem.w32(self.node + 0xC, self.owner)
        self.found = ()
        self.enemies = set()
        self.stat0, self.stat2 = 10, 4
        self.give_block = True
        self.near = True
        self.entry = 0xA10000
        self.ground = f32(0.0)

    @staticmethod
    def _plant(mem, table, slot, fn):
        mem.w16(table + 8 * slot, 0)
        mem.w32(table + 8 * slot + 4, fn)

    def respond(self, name, args, view, rng):
        if name == 'libc_sprintf':
            fmt, number = args
            token = ('f%08x:%d' % (fmt & M32, int(number) & M32)).encode()
            return Res(outs=[token])
        if name == 'world_collectObjectsInBox':
            return Res(outs=[tuple(self.found)])
        if name == 'pool_new':
            return Res(self.block if self.give_block else 0)
        if name == 'Skill.v13':
            return Res(self.stat0)
        if name == 'Skill.v10':
            return Res(self.stat2)
        if name == 'Creature.v20':
            return Res(1 if args[1] in self.enemies else 0)
        if name == 'isNearView':
            return Res(1 if self.near else 0)
        if name == 'res_find':
            return Res(self.entry)
        if name in ('terrain_height', 'terrain_heightAtPoint'):
            return Res(f=self.ground)
        if name == 'model_getSamplePointCount':
            return Res(self.samples)
        if name == 'model_getSamplePoint':
            return Res(outs=[self.sample, self.sample_extra])
        if name == 'Creature.v16':
            return Res(self.model_id)
        if name == 'particleGroup_create':
            return Res(0xB100)
        return Res(0)


class Rig:
    def __init__(self, elf):
        emu = self.emu = EE(elf, fpu_model='ps2')
        emu.div_zero = 'r5900'
        self.world = World(emu)
        self.names = {}
        for name, ext in EXTS.items():
            self.names[ext.addr] = name
            emu.stub(ext.addr, function=self.make_stub(name, ext), name=name)
        self.calls, self.pcs = [], set()
        self.partial, self.partial_ops = [], {}
        spans = [pair for entry in ENTRIES.values() for pair in entry[3]]
        spans.append((END, 0x2DAA4C))
        for start, end in spans:
            for pc in range(start, end, 4):
                word = emu.mem.u32(pc)
                if word >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = word >> 26
                    emu.hook(pc, self.partial_hook(pc, (word >> 21) & 31, sx16(word)))
        self.buffers = {}
        self.touched = set()
        self.real = set()

    def partial_hook(self, pc, base, offset):
        def note(emu):
            ea = (emu.r[base] + offset) & M32
            if not is_stack(ea):
                self.partial.append((pc, ea))
        return note

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

    def decode(self, name, ext, emu):
        mem, canon, outs = emu.mem, [], []
        index = 0
        for kind in ext.ints:
            if kind == '-':
                continue
            reg = emu.r[4 + index] & M32
            index += 1
            if kind == 'v':
                canon.append(tuple(mem.u32(reg + 4 * j) for j in range(3)))
            elif kind == 'D':
                canon.append(desc_canon(mem, reg))
            elif kind == 's':
                canon.append(('buf', self.buffers[reg]) if reg in self.buffers else reg)
            elif kind == 'p':
                canon.append('stack' if is_stack(reg) else reg)
            elif kind in ('n', 'o'):
                outs.append(reg)
            elif kind == 'O':
                canon.append(1 if reg else 0)
                outs.append(reg)
            else:
                canon.append(reg)
        for j in range(ext.floats):
            canon.append(emu.f[12 + j] & M32)
        return tuple(canon), outs

    def make_stub(self, name, ext):
        def stub(emu):
            if name == 'libc_sprintf':
                buf, fmt, number = emu.r[4] & M32, emu.r[5] & M32, emu.r[6] & M32
                args = (fmt, number)
                self.calls.append((name, args))
                token = self.world.respond(name, args, None, None).outs[0]
                emu.mem.write(buf, token + b'\0')
                self.buffers[buf] = token
                return 0
            canon, outs = self.decode(name, ext, emu)
            self.calls.append((name, canon))
            res = self.world.respond(name, canon, None, None)
            if name == 'world_collectObjectsInBox':
                ptr = outs[0]
                objects = res.outs[0] if res.outs else ()
                for j, obj in enumerate(objects):
                    emu.mem.w32(ptr + 4 * j, obj)
                emu.mem.w32(ptr + 4 * len(objects), 0)
            elif name == 'model_getSamplePoint':
                for ptr, value in zip(outs, res.outs):
                    if ptr:
                        for j in range(3):
                            emu.mem.w32(ptr + 4 * j, value[j])
            if ext.ret == 'f':
                emu.f[0] = res.f & M32
            return res.ret
        return stub

    class Callbacks:
        def __init__(self, rig):
            self.rig = rig

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, None, None)
                if name == 'libc_sprintf':
                    return ('buf', res.outs[0])
                if name in ('terrain_height', 'terrain_heightAtPoint'):
                    return res.f & M32
                if name == 'model_getSamplePoint':
                    point, extra = res.outs
                    return (point, extra) if args[5] else point
                if res.outs:
                    return res.outs[0]
                return res.ret & M32
            return answer

    def compare(self, key, args):
        addr, kinds, method, _spans = ENTRIES[key]
        emu, mem = self.emu, self.emu.mem
        self.real = set(FOLLOW[key])
        emu.follow = self.real
        seed_before = mem.u32(RC.G_RAND_SEED)
        mview = D.ModelView(mem)
        model = R6.Model(mview, Rig.Callbacks(self))
        try:
            getattr(model, method)(*args)
        except EmuError as exc:
            return ['model stopped: %s' % exc]
        self.calls, self.buffers, self.partial = [], {}, []
        emu.reset_log()
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x1000
        regs, scratch = [], self.world.argbuf
        for value, kind in zip(args, kinds):
            if kind == 'v':
                for j in range(3):
                    mem.w32(scratch + 4 * j, value[j])
                regs.append(scratch)
                scratch += 0x10
            else:
                regs.append(value & M32)
        try:
            emu.call(addr, *regs, max_steps=4000000)
        except EmuError as exc:
            return ['original stopped: %s' % exc]
        self.pcs.update(emu.trace)
        unknown = {}
        for call in emu.calls:
            if call.target not in self.real and call.target not in self.names and not LIB_LO <= call.target < LIB_HI:
                unknown[call.target] = unknown.get(call.target, 0) + 1
        problems = []
        if unknown:
            problems.append('unknown calls %s' % sorted('%x' % a for a in unknown))
        if model.calls != self.calls:
            problems.append(DC.describe_calls(model.calls, self.calls))
        lo, hi = self.world.argbuf, self.world.argbuf + 0x100
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
        return problems


def _zero(mem, addr, size):
    for off in range(0, size, 4):
        mem.w32(addr + off, 0)


def _pos(rng, scale=80):
    return tuple(f32(rng.uniform(-scale, scale)) for _ in range(3))


def _put(mem, addr, xyz):
    for i in range(3):
        mem.w32(addr + 4 * i, xyz[i])


def _ball_seed(reject):
    """An object-generator seed whose first unit-ball sample is inside, or not."""
    seed = 1
    while seed < 100000:
        state, coords = seed, []
        for _ in range(3):
            state = (state * 0x19660D + 0x3C6EF35F) & M32
            coords.append(SA.unit(state >> 16))
        length = C.add(C.add(C.mul(coords[0], coords[0]), C.mul(coords[1], coords[1])),
                       C.mul(coords[2], coords[2]))
        if C.lt(C.ONE, length) == reject:
            return seed
        seed += 1
    raise RuntimeError('no ball seed')


def _arm_common(mem, obj, rng, pos=None):
    _zero(mem, obj, 0x80)
    mem.w32(obj + 0x44, rng.getrandbits(32) or 1)
    _put(mem, obj + 0x10, pos if pos is not None else _pos(rng))


def _link(w, mem, obj):
    mem.w32(obj + 0x4C, w.node)
    mem.w32(w.node + 0xC, w.owner)
    mem.w32(w.owner + 0x48, w.owner_vt)


def generate(rig, key, rng, kind):
    w, mem = rig.world, rig.emu.mem
    mem.w32(SA.G_SIM_FRAME, 30)
    mem.w32(RC.G_RAND_SEED, rng.getrandbits(32) or 1)
    mem.w32(RC.G_LEVEL_FLAGS, 0)
    w.found, w.enemies = (), set()
    w.stat0, w.stat2, w.give_block, w.near = 10, 4, True, True
    _zero(mem, w.owner, 0x40)
    mem.w32(w.owner + 0x48, w.owner_vt)
    if key == 'poisonGas':
        return _gas(w, mem, rng, kind)
    if key == 'diseaseCorpse':
        return _corpse(w, mem, rng, kind)
    if key == 'multifireHit':
        return _hit(w, mem, rng, kind)
    if key == 'multifireEnd':
        return _end(w, mem, rng, kind)
    if key == 'pustule':
        return _pustule(w, mem, rng, kind)
    if key == 'arena':
        return _arena(w, mem, rng, kind)
    if key == 'hornomen':
        return _horn(w, mem, rng, kind)
    if key == 'planarsteel':
        return _planar(w, mem, rng, kind)
    if key == 'hornCtor':
        return _horn_ctor(w, mem, rng, kind)
    if key == 'planarCtor':
        return _planar_ctor(w, mem, rng, kind)
    return _smoke(w, mem, rng, kind)


def _gas(w, mem, rng, kind):
    obj = w.gas
    _arm_common(mem, obj, rng)
    mem.w32(obj + 0x48, w.obj_vt)
    mem.w32(obj + 0x5C, 90)
    mem.w32(obj + 0x60, 0)
    mem.w32(obj + 0x64, f32(0.0))
    mem.w32(obj + 0x6C, 5)
    _link(w, mem, obj)
    if kind == 'expire':
        mem.w32(SA.G_SIM_FRAME, 90)
    elif kind == 'idle':
        mem.w32(SA.G_SIM_FRAME, 1)
    elif kind == 'grow':
        mem.w32(SA.G_SIM_FRAME, 1)
        mem.w32(obj + 0x60, 10)
        mem.w32(obj + 0x44, _ball_seed(False))
    elif kind == 'reject':
        mem.w32(SA.G_SIM_FRAME, 1)
        mem.w32(obj + 0x60, 20)
        mem.w32(obj + 0x44, _ball_seed(True))
    elif kind == 'above':
        mem.w32(SA.G_SIM_FRAME, 1)
        mem.w32(obj + 0x60, 10)
        mem.w32(obj + 0x64, f32(20.0))
    elif kind == 'negative':
        mem.w32(SA.G_SIM_FRAME, 1)
        mem.w32(obj + 0x60, M32 - 9)               # -10
    elif kind == 'no-owner':
        mem.w32(obj + 0x4C, 0)
        mem.w32(obj + 0x60, 10)
        mem.w32(obj + 0x64, f32(9.0))
    elif kind == 'empty':
        mem.w32(obj + 0x60, 10)
        mem.w32(obj + 0x64, f32(9.0))
    elif kind == 'skip':
        mem.w32(obj + 0x60, 10)
        mem.w32(obj + 0x64, f32(9.0))
        _place(mem, w.victims[0], 0, rng)
        _place(mem, w.victims[1], 0x28, rng)
        w.found = (w.victims[0], w.victims[1])
        w.enemies = {w.victims[1]}
        mem.w32(obj + 0x6C, 0x10005)
    elif kind == 'two':
        mem.w32(obj + 0x60, 0)
        mem.w32(obj + 0x64, f32(4.0))
        for victim in w.victims[:2]:
            _place(mem, victim, 0, rng)
        w.found = tuple(w.victims[:2])
        w.enemies = set(w.found)
    return (obj,)


def _place(mem, victim, flags, rng):
    _zero(mem, victim, 0x40)
    mem.w32(victim + 0xC, flags)
    _put(mem, victim + 0x10, _pos(rng, 20))


def _corpse(w, mem, rng, kind):
    obj = w.corpse
    _arm_common(mem, obj, rng)
    mem.w32(obj + 0x48, w.obj_vt)
    mem.w32(obj + 0x54, 16)
    mem.w32(obj + 0x50, 4)
    _link(w, mem, obj)
    if kind == 'empty':
        w.found = ()
    elif kind == 'half':
        mem.w32(obj + 0x50, 1)
        _place(mem, w.victims[0], 0x28, rng)
        w.found = (w.victims[0],)
    elif kind == 'flags':
        _place(mem, w.victims[0], 0x20, rng)
        _place(mem, w.victims[1], 0x8, rng)
        _place(mem, w.victims[2], 0x2C, rng)
        w.found = tuple(w.victims[:3])
        mem.w32(obj + 0x50, 2)                     # half 1: skips do not consume it, so the third spawns
    elif kind == 'spawn-then-stop':
        _place(mem, w.victims[0], 0x28, rng)
        _place(mem, w.victims[1], 0x28, rng)
        w.found = tuple(w.victims[:2])
        mem.w32(obj + 0x50, 2)                     # half 1: first spawns, second remains
    elif kind == 'no-handle':
        mem.w32(obj + 0x4C, 0)
        _place(mem, w.victims[0], 0x28, rng)
        w.found = (w.victims[0],)
    elif kind == 'pool-empty':
        w.give_block = False
        _place(mem, w.victims[0], 0x28, rng)
        w.found = (w.victims[0],)
    elif kind == 'owner-missing':
        mem.w32(w.node + 0xC, 0)
        _place(mem, w.victims[0], 0x28, rng)
        _place(mem, w.victims[1], 0x28, rng)
        w.found = tuple(w.victims[:2])
    elif kind == 'negative-half':
        mem.w32(obj + 0x50, M32)                   # -1, half 0
        _place(mem, w.victims[0], 0x28, rng)
        w.found = (w.victims[0],)
    return (obj,)


def _arm_bolt(w, mem, rng):
    obj = w.bolt
    _arm_common(mem, obj, rng)
    mem.w32(obj + 0x70, w.skill)
    mem.w32(obj + 0x68, 3)
    mem.w32(obj + 0x74, w.trail)
    _link(w, mem, obj)
    return obj


def _weapon(mem, slot, low, high):
    rec = (RC.G_PLAYERS + slot * RC.REC_SIZE) & M32
    mem.w32(rec + 0xD0, low & M32)
    mem.w32(rec + 0xD4, high & M32)


def _hit(w, mem, rng, kind):
    obj = _arm_bolt(w, mem, rng)
    other = w.victims[0]
    _place(mem, other, 0, rng)
    mem.w32(w.owner + 0xC, 0)
    mem.w32(w.owner + 0x3C8, 0)
    w.stat0, w.stat2 = 100, 4
    _weapon(mem, 0, 40, 80)
    if kind == 'empty':
        mem.w32(obj + 0x4C, 0)
    elif kind == 'player-flag':
        mem.w32(w.owner + 0xC, 0x40)
        mem.w32(other + 0xC, 0x40)
    elif kind == 'player-mark':
        mem.w32(w.owner + 0xC, 0x40)
        mem.w32(other + 0xC, 0x01000000)
    elif kind == 'player-bit':
        mem.w32(w.owner + 0xC, 0x40)
        mem.w32(other + 0xC, 0x20)
        mem.w32(other + 0xA8, CREATURE_BIT)
    elif kind == 'player-creature-clear':
        mem.w32(w.owner + 0xC, 0x40)
        mem.w32(other + 0xC, 0x20)
        mem.w32(other + 0xA8, 0)
        _weapon(mem, 0, M32 - 39, M32 - 79)        # -40 and -80: both negative rounding sides
    elif kind == 'player-slot':
        mem.w32(w.owner + 0xC, 0x40)
        mem.w32(w.owner + 0x3C8, 1)
        mem.w32(RC.G_LEVEL_FLAGS, R6.LEVEL_ICE)
        _weapon(mem, 1, 10, 10)
        w.stat0, w.stat2 = 0, 1
    elif kind == 'monster-no':
        w.enemies = set()
    elif kind == 'monster-yes':
        w.enemies = {other}
        w.stat0 = 12
    elif kind == 'monster-negative':
        w.enemies = {other}
        w.stat0 = -8
    elif kind == 'already':
        w.enemies = {other}
        mem.w32(obj + 0x60, 1)
    return (obj, other)


CREATURE_BIT = R6.CREATURE_SKIP


def _end(w, mem, rng, kind):
    obj = _arm_bolt(w, mem, rng)
    reason = 2
    if kind == 'already':
        mem.w32(obj + 0x60, 1)
        reason = 2
    elif kind == 'quiet':
        reason = 0
    elif kind == 'ice':
        mem.w32(RC.G_LEVEL_FLAGS, R6.LEVEL_ICE)
    elif kind == 'stone':
        mem.w32(obj + 0x74, 0)
    return (obj, reason)


def _smoke(w, mem, rng, kind):
    obj = w.smoke
    _zero(mem, obj, 0x500)
    mem.w32(obj + 0x44, rng.getrandbits(32) or 1)
    _put(mem, obj + 0x10, _pos(rng))
    mem.w32(obj + 0x478, f32(4.0))
    mem.w32(obj + 0x48C, 5)
    mem.w32(SA.G_SIM_FRAME, 8)
    w.near = True
    if kind == 'far':
        w.near = False
    elif kind == 'spent':
        mem.w32(obj + 0x48C, 0)
    elif kind == 'negative':
        mem.w32(obj + 0x48C, M32)
    elif kind == 'off-frame':
        mem.w32(SA.G_SIM_FRAME, 1)
    elif kind == 'empty':
        mem.w32(SA.G_SIM_FRAME, 0)
        w.found = ()
    elif kind == 'mixed':
        _place(mem, w.victims[0], 0x20, rng)
        _place(mem, w.victims[1], 0x21, rng)
        _place(mem, w.victims[2], 0, rng)
        _place(mem, w.victims[3], 0x20, rng)
        w.found = (obj, w.victims[0], w.victims[1], w.victims[2], w.victims[3])
    return (obj,)


def _pustule(w, mem, rng, kind):
    obj = w.pustule
    _zero(mem, obj, 0x180)
    mem.w32(obj + 0x48, w.obj_vt)
    mem.w32(obj + 0x44, rng.getrandbits(32) or 1)
    mem.w32(obj + 0x10, f32(1.0))
    mem.w32(obj + 0x14, f32(2.0))
    mem.w32(obj + 0x18, f32(10.0))
    mem.w32(obj + 0x58, f32(0.25))
    mem.w32(obj + 0x5C, f32(-0.25))
    mem.w32(obj + 0x60, f32(-1.0))
    mem.w32(obj + 0x54, f32(-100.0))
    mem.w32(RC.G_WORLD, w.world_word)
    w.ground = f32(1.5)
    if kind == 'old':
        mem.w32(obj + 0x64, 301)
    elif kind == 'burst-done':
        mem.w32(obj + 0x6C, 1)
        mem.w32(obj + 0x64, 40)
    elif kind == 'drops':
        mem.w32(obj + 0x6C, 1)
        mem.w32(obj + 0x64, 2)
    elif kind == 'fall':
        mem.w32(obj + 0x64, 4)
    elif kind == 'land':
        mem.w32(obj + 0x54, f32(100.0))
        mem.w32(obj + 0x64, 1)
    return (obj,)


def _spell(w, mem, rng):
    spell, creature = w.spell, w.owner
    _zero(mem, spell, 0x80)
    _zero(mem, creature, 0x180)
    mem.w32(spell + 0x14, w.spell_vt)
    mem.w32(spell + 0xC, creature)
    mem.w32(spell + 0x10, rng.getrandbits(32) or 1)
    mem.w32(creature + 0x48, w.creature_vt)
    mem.w32(creature + 0xC, 0)
    _put(mem, creature + 0x10, (f32(1.0), f32(2.0), f32(3.0)))
    mem.w16(creature + 0x38, 0x1000)
    mem.w32(R6.G_GLOW_TEX_C, 0x00D30000)
    mem.w32(RC.G_WORLD, w.world_word)
    w.ground = f32(0.5)
    w.samples = 4
    return spell, (f32(8.0), f32(9.0), f32(10.0))


def _horn_ctor(w, mem, rng, kind):
    spell, _pos = _spell(w, mem, rng)
    kind_byte = 1 if kind == 'plain' else 4
    return (spell, kind_byte, w.owner, 0x11 if kind == 'plain' else 0x22)


def _planar_ctor(w, mem, rng, kind):
    spell, _pos = _spell(w, mem, rng)
    mem.w32(w.owner + 0x20, f32(10.0 if kind == 'plain' else -2.5))
    return (spell, 2 if kind == 'plain' else 9, w.owner, 0x33)


def _arena(w, mem, rng, kind):
    spell, pos = _spell(w, mem, rng)
    counter = {'quiet': 0, 'start': 30, 'fading': 61, 'spent': 200}[kind]
    mem.w16(R6.G_ARENA_COUNTER, counter)
    return (spell, pos)


def _horn(w, mem, rng, kind):
    spell, pos = _spell(w, mem, rng)
    mem.w32(spell + 0x1C, 7)
    if kind == 'ended':
        mem.w32(SA.G_SIM_FRAME, 100)
        mem.w32(spell + 0x18, 100)
    elif kind == 'early':
        mem.w32(SA.G_SIM_FRAME, 5)
        mem.w32(spell + 0x18, 600)
    elif kind == 'late':
        mem.w32(SA.G_SIM_FRAME, 140)
        mem.w32(spell + 0x18, 600)
    elif kind == 'empty':
        mem.w32(SA.G_SIM_FRAME, 5)
        mem.w32(spell + 0x18, 600)
        w.samples = 0
    return (spell, pos)


def _planar(w, mem, rng, kind):
    spell, pos = _spell(w, mem, rng)
    mem.w8(spell, 1)
    mem.w16(spell + 0x18, 0x2000)
    mem.w16(spell + 0x1A, 0x3000)
    mem.w16(spell + 0x1C, 40)
    if kind == 'ended':
        mem.w32(SA.G_SIM_FRAME, 80)
        mem.w32(spell + 0x24, 80)
    elif kind == 'steady':
        mem.w32(SA.G_SIM_FRAME, 10)
        mem.w32(spell + 0x24, 400)
        mem.w32(spell + 0x20, 1)
    elif kind == 'burst':
        mem.w32(SA.G_SIM_FRAME, 10)
        mem.w32(spell + 0x24, 400)
        mem.w16(spell + 0x1C, 0)
    return (spell, pos)


SCENARIOS = {
    'poisonGas': ('expire', 'idle', 'grow', 'reject', 'above', 'negative', 'no-owner', 'empty', 'skip', 'two'),
    'diseaseCorpse': ('empty', 'half', 'flags', 'spawn-then-stop', 'no-handle', 'pool-empty',
                      'owner-missing', 'negative-half'),
    'multifireHit': ('empty', 'player-flag', 'player-mark', 'player-bit', 'player-creature-clear',
                     'player-slot', 'monster-no', 'monster-yes', 'monster-negative', 'already'),
    'multifireEnd': ('already', 'quiet', 'ice', 'stone'),
    'smokeGen': ('far', 'spent', 'negative', 'off-frame', 'empty', 'mixed'),
    'pustule': ('old', 'burst-done', 'drops', 'fall', 'land'),
    'arena': ('quiet', 'start', 'fading', 'spent'),
    'hornomen': ('ended', 'early', 'late', 'empty'),
    'hornCtor': ('plain', 'other'),
    'planarsteel': ('ended', 'steady', 'burst'),
    'planarCtor': ('plain', 'high'),
}


def coverage(pcs, spans):
    total = hit = 0
    for start, end in spans:
        total += (end - start) // 4
        hit += sum(1 for pc in range(start, end, 4) if pc in pcs)
    return hit, total


def main(argv):
    args, elf = list(argv), None
    while args:
        item = args.pop(0)
        if item == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
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
        print('difftest_combat_round6: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('difftest_combat_round6: not SLUS_209.73 US v2.00 - skipped')
        return 0
    C.set_fpu('ps2')
    started = time.time()
    rig = Rig(elf)
    rng = random.Random(OPTIONS['seed'])
    print('%-16s %8s %8s  first problem' % ('entry point', 'compared', 'failed'))
    ok = True
    for key, (_addr, _kinds, _method, spans) in ENTRIES.items():
        if not wanted(key):
            continue
        compared = failed = 0
        shown = []
        for kind in SCENARIOS[key]:
            call = generate(rig, key, rng, kind)
            problems = rig.compare(key, call)
            compared += 1
            if problems:
                failed += 1
                if len(shown) < 4:
                    shown.append('%s: %s' % (kind, problems[0][:300]))
        hit, total = coverage(rig.pcs, spans)
        print('%-16s %8d %8d  %d of %d instructions' % (key, compared, failed, hit, total))
        for line in shown:
            print('   ', line)
        ok = ok and not failed
    print('total: %.1f s' % (time.time() - started))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
