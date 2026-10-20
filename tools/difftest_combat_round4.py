#!/usr/bin/env python3
"""difftest_combat_round4.py - compare the bodies tools/ref_combat_round4.py adds with the
game's own code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_combat_round4.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                          [--cases N] [-k TEXT] [-v]

For each entry the original runs in tools/ee_emu.py (an instruction interpreter, not a
console).  The same inputs go through ref_combat_round4 on a copy-on-write view.  Equal
must be: calls outside the model, in order, with arguments; bytes stored outside the
stack; the shared seed and its draw count; the result.  Floats are 32-bit patterns.

Real: the entry, and the C library (sprintf, strcasecmp, the soft-double helpers).
Everything else is a recording stub answered by the same script on both sides.
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
import ref_combat_ranged as RR                  # noqa: E402
import ref_combat_round4 as R4                  # noqa: E402
import difftest_combat_runtime as D             # noqa: E402
import difftest_creature as DC                  # noqa: E402

EXPECTED_SHA256 = D.EXPECTED_SHA256
M32 = 0xFFFFFFFF
LIB_LO, LIB_HI = 0x3A5000, 0x3C01A8          # through libc_mbtowc_r, which sprintf calls
f32 = D.f32
is_stack = D.is_stack
Ext = RC.Ext

OPTIONS = {'quick': False, 'seed': 20973, 'cases': 40, 'filter': None, 'verbose': False}

BODY = (0x1BA940, 0x1BB3C8)
SHIELD = (0x2E8534, 0x2E886C)
ENTRIES = {
    'potionKind1': (0x1BA940, 'i', 0, 'n', 'thrown_run', BODY),
    'potionKind2': (0x1BA940, 'i', 0, 'n', 'thrown_run', BODY),
    'potionKind3': (0x1BA940, 'i', 0, 'n', 'thrown_run', BODY),
    'holyShield': (0x2E8534, 'i', 0, 'f', 'holy_shield_absorb', SHIELD),
    'blockSparks': (0x1B9658, 'ii', 0, 'n', 'block_sparks', (0x1B9658, 0x1B9CB8)),
}
FN_MODEL, FN_STAT = 0x3E0100, 0x3E0120
KINDS = {'potionKind1': 1, 'potionKind2': 2, 'potionKind3': 3}

EXTS = {
    'particle_spawn': Ext(0x18F3F8, 'pvv', 1, 'n'),
    'obj_moveAndCollide': Ext(0x1509F8, 'pv', 0, 'i'),
    'res_find': Ext(0x17365C, 'SS', 0, 'i'),
    'sound_playOnObject': Ext(0x214230, 'pp', 1, 'n'),
    'terrain_height': Ext(0x183820, 'pv', 1, 'f'),
    'pool_new': Ext(0x14FDB8, 'i', 0, 'i'),
    'LooseFire_ctor': Ext(0x202B70, 'pvi', 0, 'n'),
    'decal_add': Ext(0x19F110, 'viii', 1, 'n'),
    'poisonGasSpell_ctor': Ext(0x202DE8, 'pviiipi', 0, 'n'),
    'fx_ringBurst': Ext(0x1F3D00, 'v', 1, 'n'),
    'world_damageInRadius': Ext(0x161270, 'iviiii', 2, 'n'),
    'Creature.v1': Ext(0, 'pi', 0, 'n'),
    'Creature.v16': Ext(FN_MODEL, 'p', 0, 'i'),
    'Skill.v10': Ext(FN_STAT, 'pii', 0, 'i'),
    'model_getSamplePointCount': Ext(0x1799C8, 'p', 0, 'i'),
    'model_getSamplePoint': Ext(0x178E18, 'ppviiOWO', 1, 'n'),
    'particleGroup_begin': Ext(0x18E958, 'i', 0, 'n'),
    'particleGroup_end': Ext(0x18E9A0, 'i', 0, 'n'),
    'model_getAttachPoint': Ext(0x1754A0, 'pvipioO', 1, 'n'),
}
_LIGHT = Ext(0x201BD8, 'ivii', 8, 'n')
_LIGHT.stack = 4
EXTS['LightEffect_ctor'] = _LIGHT


def shape(ext, res):
    if ext is None or ext.ret == 'n':
        return None
    if ext.ret == 'f':
        return res.f & M32
    return res.ret & M32


class Res:
    def __init__(self, ret=0, f=0, outs=()):
        self.ret, self.f, self.outs = ret, f, list(outs)


class World:
    def __init__(self, emu):
        self.emu, self.mem = emu, emu.mem
        self.thrown = [emu.alloc(0x200) for _ in range(2)]
        self.owners = [emu.alloc(0x40) for _ in range(2)]
        self.nodes = {}
        for obj in self.owners:
            node = emu.alloc(0x10)
            self.mem.w32(node + 0xC, obj)
            self.nodes[obj] = node
        self.blocks = {0x54: emu.alloc(0x60), 0x70: emu.alloc(0x80), 0xBC: emu.alloc(0xC0)}
        self.world = emu.alloc(0x10)
        self.mem.w32(RR.G_WORLD, self.world)
        self.spell, self.caster, self.skill = emu.alloc(0x40), emu.alloc(0x140), emu.alloc(0x80)
        self.anim = emu.alloc(0x20)
        self.model_ptr = emu.alloc(0x10)
        self.vt_caster, self.vt_skill = emu.alloc(0x90), emu.alloc(0x60)
        self.mem.w32(self.vt_caster + 0x84, FN_MODEL)
        self.mem.w32(self.vt_skill + 0x54, FN_STAT)
        self.collide = 0
        self.height = 0
        self.give = True
        self.points = 4
        self.stat = 0
        self.player = emu.alloc(0x560)
        self.body = emu.alloc(0x20)
        self.rec_obj = emu.alloc(0x120)
        self.dtor = 0x3C6468

    def respond(self, name, args, view, rng):
        if name == 'obj_moveAndCollide':
            return Res(self.collide)
        if name == 'terrain_height':
            return Res(0, self.height)
        if name == 'pool_new':
            return Res(self.blocks.get(args[0], 0) if self.give else 0)
        if name == 'res_find':
            return Res(0x00A10000)
        if name == 'Creature.v16':
            return Res(self.model_ptr)
        if name == 'model_getSamplePointCount':
            return Res(self.points)
        if name == 'model_getSamplePoint':
            base, index = args[2], args[4]
            point = (C.add(base[0], C.from_int(index & 3)), base[1],
                     C.add(base[2], C.from_int(index & 1)))
            return Res(0, 0, [point, C.ZERO])
        if name == 'model_getAttachPoint':
            pos = args[1]
            hand = tuple(C.add(pos[i], C.from_int(args[4])) for i in range(3))
            return Res(0, 0, [hand])
        if name == 'Skill.v10':
            return Res(self.stat)
        return Res()


class Rig:
    def __init__(self, elf):
        emu = self.emu = EE(elf, fpu_model='ps2')
        emu.div_zero = 'r5900'
        self.world = World(emu)
        self.real = {0x1BA940, 0x2E8534, 0x1B9658, R4.SPELL_RAND}
        emu.follow = type('Follow', (), {'__contains__': lambda _s, t: t in self.real or LIB_LO <= t < LIB_HI})()
        self.names = {}
        for name, ext in EXTS.items():
            addr = self.world.dtor if name == 'Creature.v1' else ext.addr
            if not addr or addr in self.real:
                continue
            self.names[addr] = name
            emu.stub(addr, function=self.make_stub(name, ext), name=name)
        self.calls, self.unknown, self.pcs = [], {}, set()
        self.eview = D.View(emu.mem.load, self._epoke)
        self.touched = set()
        self.script_rng = None

    def _epoke(self, addr, size, value):
        self.emu.mem.store(addr, size, value & ((1 << (8 * size)) - 1))
        self.touched.update(range(addr, addr + size))

    def stored_bytes(self):
        """Bytes stored outside the stack.  Stores whose instruction is in the C library
        (sprintf's reentrancy block, the soft-double helpers) are not game state."""
        out = set()
        for pc, addr, size, _value in self.emu.writes:
            if LIB_LO <= pc < LIB_HI:
                continue
            if is_stack(addr):
                continue
            out.update(range(addr, addr + size))
        return out

    def decode(self, ext, emu):
        mem, canon, outs = emu.mem, [], []
        for i, kind in enumerate(ext.ints):
            reg = emu.r[4 + i] & M32
            if kind == 'v':
                canon.append(tuple(mem.u32(reg + 4 * j) for j in range(3)))
            elif kind == 'S':
                canon.append(('str', mem.cstr(reg, 64).encode('latin1')))
            elif kind in 'OW':
                canon.append(1 if reg else 0)
                outs.append((kind, reg))
            elif kind in 'ow':
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
                value = given.pop(0) if given else ((0, 0, 0) if kind in 'oO' else 0)
                if kind in 'oO' and ptr:
                    for j in range(3):
                        emu.mem.w32(ptr + 4 * j, value[j])
                elif kind in 'wW' and ptr:
                    emu.mem.w32(ptr, value)
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
                if res.outs:
                    return tuple(res.outs) if len(res.outs) > 1 else res.outs[0]
                return shape(EXTS.get(name), res)
            return answer

    def compare(self, key, args):
        addr, kinds, _nfloat, ret_kind, method, _body = ENTRIES[key]
        emu, mem = self.emu, self.emu.mem
        seed_before = mem.u32(RC.G_RAND_SEED)
        mview = D.ModelView(mem)
        cls = {'holy_shield_absorb': R4.ShieldModel, 'block_sparks': R4.SparkModel}.get(
            method, R4.PotionModel)
        model = cls(mview, Rig.Callbacks(self))
        try:
            mret = getattr(model, method)(*args)
        except EmuError as exc:
            return 'model stopped: %s' % exc
        self.calls, self.touched = [], set()
        emu.reset_log()
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x800
        regs = []
        for value, kind in zip(args, kinds):
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
        stored = self.stored_bytes()
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
        if ret_kind == 'f' and (emu.f[0] & M32) != ((mret or 0) & M32):
            problems.append('result %08x / %08x' % (emu.f[0] & M32, (mret or 0) & M32))
        for a, byte in mview.bytes.items():
            mem.store(a, 1, byte)
        return problems


def _zero(mem, addr, size):
    for off in range(0, size, 4):
        mem.w32(addr + off, 0)


def _cstr(mem, addr, text):
    raw = text.encode('ascii') + b'\0'
    for i, byte in enumerate(raw):
        mem.w8(addr + i, byte)
    for i in range(len(raw), 32):
        mem.w8(addr + i, 0)


def generate(rig, key, rng, n=0):
    if key == 'holyShield':
        return _shield(rig, rng, n)
    if key == 'blockSparks':
        return _sparks(rig, rng, n)
    w, mem = rig.world, rig.emu.mem
    frame = rng.randrange(1, 1 << 20)
    mem.w32(RC.G_SIM_FRAME, frame)
    mem.w32(RC.G_RAND_SEED, rng.getrandbits(32) or 1)
    obj = w.thrown[n & 1]
    _zero(mem, obj, 0x1E0)
    z = f32(rng.choice((0.0, 10.0, 36.0, 100.0, -20.0)))
    for i, word in enumerate((f32(rng.uniform(-200, 200)), f32(rng.uniform(-200, 200)), z)):
        mem.w32(obj + 0x10 + 4 * i, word)
        mem.w32(obj + 0x1B0 + 4 * i, f32(rng.uniform(-400, 400)))
    mem.w32(obj + 0x48, RR.VT_THROWN)
    mem.w8(obj + 0x1CE, KINDS[key])
    mem.w16(obj + 0x1CC, rng.choice((0, 2000, 0x1388, 0xEC78, 0xFFFF)))
    mem.w32(obj + 0x1C, f32(12.0))
    mem.w32(obj + 0xEC, (frame + 80) & M32)
    mem.w8(obj + 0xCC, 0)
    owner = rng.choice((0, 0, w.owners[0]))
    if owner:
        mem.w32(obj + 0x1C8, w.nodes[owner])
    w.collide, w.give = 0, True
    w.height = z
    _cstr(mem, R4.G_LEVEL_TEXT, 'town')
    # The first cases are fixed so flight, each result, a refused pool, the innpit
    # skip and both sides of the 4-unit decal gate are not left to the draw.
    if n == 0:
        w.collide = 0
        mem.w32(obj + 0xEC, (frame + 50) & M32)
    elif n == 1:
        w.collide = 1
    elif n == 2:
        w.collide = 2
    elif n == 3:
        w.collide = 3
    elif n == 4:
        w.collide = 2
        mem.w8(obj + 0xCC, 1)
    elif n == 5:
        w.collide = 0
        mem.w32(obj + 0xEC, 0)
        w.give = False
    elif n == 6:
        w.collide = 1
        w.height = C.add(z, f32(4.0))
        _cstr(mem, R4.G_LEVEL_TEXT, 'InNpIt')
    elif n == 7:
        w.collide = 1
        w.height = C.add(z, f32(-1.0))
        w.give = key != 'potionKind2'
    else:
        w.collide = rng.choice((0, 0, 1, 2, 3))
        w.give = rng.choice((True, True, False))
        w.height = C.add(z, f32(rng.choice((0.0, -3.0, 3.9, 4.0, 10.0, -10.0))))
        if rng.random() < 0.25:
            mem.w8(obj + 0xCC, rng.choice((1, 0x80)))
        if rng.random() < 0.2:
            mem.w32(obj + 0xEC, 0 if frame else 1)
        if rng.random() < 0.15:
            _cstr(mem, R4.G_LEVEL_TEXT, rng.choice(('innpit', 'INNPIT', 'innpitx', '')))
    return (obj,)


def _shield(rig, rng, n):
    w, mem = rig.world, rig.emu.mem
    spell, caster, skill = w.spell, w.caster, w.skill
    _zero(mem, spell, 0x40)
    _zero(mem, caster, 0x130)
    _zero(mem, skill, 0x70)
    mem.w32(spell + 0x8, skill)
    mem.w32(spell + 0xC, caster)
    mem.w32(spell + 0x10, rng.getrandbits(32) or 1)
    mem.w32(spell + 0x24, 0x00D00010)
    mem.w32(caster + 0x48, w.vt_caster)
    mem.w32(caster + 0x114, w.anim)
    mem.w32(skill + 0x60, w.vt_skill)
    for i in range(3):
        mem.w32(caster + 0x10 + 4 * i, f32(rng.uniform(-80, 80)))
    mem.w16(caster + 0x38, rng.choice((0, 0x4000, 0x1234, 0xFFFF)))
    w.points, w.stat, w.give = 4, 0, True
    cool = C.ZERO
    if n == 0:
        w.stat = 100
    elif n == 1:
        cool = C.ONE
        w.stat = 0
        w.points = 1
    elif n == 2:
        cool = 0xBF800000
        w.give = False
        w.stat = 10
        w.points = 7
    elif n == 3:
        w.stat = 1
        w.points = 3
        mem.w8(spell, 5)
    else:
        cool = rng.choice((C.ZERO, C.ZERO, C.ONE, 0xBF800000, f32(0.26)))
        w.give = rng.choice((True, True, False))
        w.points = rng.choice((1, 3, 7, 12))
        w.stat = rng.choice((0, 1, 10, 100, 250))
        mem.w8(spell, rng.choice((0, 1, 4, 9)))
    mem.w32(spell + 0x1C, cool)
    return (spell,)


def _sparks(rig, rng, n):
    w, mem = rig.world, rig.emu.mem
    P = w.player
    _zero(mem, P, 0x560)
    slot = 0
    silent, count = 1, 1
    if n == 0:
        silent, count = 1, 1
    elif n == 1:
        silent, count = 2, 2
    elif n == 2:
        silent, count = 1, 0
    elif n == 3:
        silent, count = 3, 1
    elif n == 4:
        silent, count, slot = 2, 1, 1
    else:
        silent = rng.choice((1, 1, 2, 2, 3, 5))
        count = rng.choice((0, 1, 2, 4))
        slot = rng.choice((0, 0, 1))
    for i in range(3):
        mem.w32(P + 0x10 + 4 * i, f32(rng.uniform(-40, 40)))
    mem.w16(P + 0x38, rng.choice((0, 0x1000, 0x4000, 0xC000)))
    mem.w32(P + 0x3C8, slot)
    mem.w32(P + 0x544, w.body)
    rec = (RC.G_PLAYERS + slot * RC.REC_SIZE) & M32
    mem.w32(rec + RC.REC_OBJ, w.rec_obj)
    w.points = count
    return (P, silent)


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
        elf = os.path.join(D.ROOT, 'SLUS_209.73')
    if not os.path.exists(elf):
        alt = os.path.expanduser('~/champions-re/SLUS_209.73')
        elf = alt if os.path.exists(alt) else elf
    if not os.path.exists(elf):
        print('difftest_combat_round4: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('difftest_combat_round4: not SLUS_209.73 US v2.00 - skipped')
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
            problems = rig.compare(key, call)
            compared += 1
            if problems:
                failed += 1
                if len(shown) < 4:
                    shown.append('case %d: %s' % (n, problems if isinstance(problems, str) else '; '.join(problems)))
        start, end = ENTRIES[key][5]
        hit = len({pc for pc in rig.pcs if start <= pc < end})
        print('%-22s %8d %8d  %d of %d instructions' % (key, compared, failed, hit, (end - start) // 4))
        for line in shown:
            print('   ', line)
        if rig.unknown:
            ok_all = False
        ok_all = ok_all and not failed
    print('total: %.1f s' % (time.time() - started))
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
