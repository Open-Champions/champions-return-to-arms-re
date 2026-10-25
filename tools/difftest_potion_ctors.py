#!/usr/bin/env python3
"""difftest_potion_ctors.py - compare tools/ref_potion_ctors.py with the game's own
LooseFire, Fire (fx_spawn id 5) and poisonGasSpell code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_potion_ctors.py [path/to/SLUS_209.73] [--seed N] [--cases N]
                                         [--quick] [-k TEXT] [-v]

    --seed N    seed of the random cases (default 20973); a seed repeats exactly
    --cases N   cases per entry point (default 200)
    --quick     a tenth of the cases
    -k TEXT     only the entry points whose name contains TEXT
    -v          print the pcs of the bodies never executed

What is compared
    For each case the original entry point runs in tools/ee_emu.py (an instruction
    interpreter, not a console) on memory this script prepares.  The same call goes
    through ref_potion_ctors.Model first, on a copy-on-write view of the same memory.
    Equal must be: the calls outside the model, in order, with their arguments; the set of
    bytes stored outside the stack and their values; the shared seed 0x404464 and that it
    advanced exactly as many times as the model drew; the result.  Floats are 32-bit
    patterns under the interpreter's 'ps2' floating-point model.

Real: ref_potion_ctors.MODELLED, GameObject_ctor 0x14cb10 and GameObject_rand 0x1509d0
(both executed by tools/difftest_skills_a.py and reused by the model), math_sin16 0x1666e0
and math_cos16 0x166630 (executed by tools/difftest_core.py).  Recording stubs answered
by the same script on both sides: handle_link, handle_removeNode, obj_getPropInt (never
hidden), pool_new (a fresh zeroed block, or 0 when the case refuses), particle_spawn,
glow_add, damage_apply, the slot-1 destructors of LooseFire 0x3c6778 and Fire 0x3c5050,
and an owner's slot 20.  Any other call fails the case.

Precondition of every fx_spawn case: the 24 particle definitions of fx_spawn are made
(words 0x4f87bc + 4i set), as after the first effect of a level.  A particleDef_ctor call
would be a recorded call the model does not make, so the case would fail.
"""
import hashlib
import os
import random
import struct
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError                 # noqa: E402
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_potion_ctors as PC                   # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M32 = 0xFFFFFFFF
LIB_LO, LIB_HI = 0x3A5000, 0x3C0000
STACK_LO, STACK_HI = EE.STACK_LO, EE.STACK_HI
OPTIONS = {'quick': False, 'seed': 20973, 'cases': 200, 'filter': None, 'verbose': False}

GAMEOBJECT_CTOR, GAMEOBJECT_RAND = 0x14CB10, 0x1509D0
MATH_SIN16, MATH_COS16 = 0x1666E0, 0x166630
DTOR_LOOSEFIRE, DTOR_FIRE = 0x3C6778, 0x3C5050
FN_V20 = 0x00F00010                             # an owner's slot 20 (unmapped; a stub)
REAL = set(PC.MODELLED.values()) | {GAMEOBJECT_CTOR, GAMEOBJECT_RAND, MATH_SIN16, MATH_COS16}

STUBS = {                                       # address -> name (a row of PC.EXTERNALS)
    0x1A1738: 'handle_link', 0x1A1868: 'handle_removeNode', 0x14C880: 'obj_getPropInt',
    0x17365C: 'res_find', 0x14FDB8: 'pool_new', 0x18F3D0: 'particleDef_ctor',
    0x18F3F8: 'particle_spawn', 0x18FC78: 'glow_add', 0x1E8230: 'damage_apply',
    DTOR_LOOSEFIRE: 'Creature.v1', DTOR_FIRE: 'Creature.v1', FN_V20: 'Creature.v20',
}

# entry points: key -> (address, argument kinds, result kind, model method)
#   i integer, v vector passed by pointer; results: n nothing
ENTRIES = {
    'obj_runEveryFrame': (0x14F248, 'i', 'n', 'obj_run_every_frame'),
    'fx_spawn5': (0x1EF270, 'iv', 'n', 'fx_spawn'),
    'Fire_ctor': (0x2020E0, 'iv', 'n', 'fire_ctor'),
    'Fire_run': (0x1F34E0, 'i', 'n', 'fire_run'),
    'LooseFire_ctor': (0x202B70, 'ivi', 'n', 'loosefire_ctor'),
    'LooseFire_five': (0x202B70, 'ivi', 'n', 'loosefire_ctor'),
    'LooseFire_run': (0x202C48, 'i', 'n', 'loosefire_run'),
    'LooseFire_onTouch': (0x1FCB70, 'ii', 'n', 'loosefire_on_touch'),
    'poisonGasSpell_ctor': (0x202DE8, 'iviiiii', 'n', 'poison_gas_ctor'),
    'poisonGas_potion': (0x202DE8, 'iviiiii', 'n', 'poison_gas_ctor'),
}

# bodies for the coverage count: name -> (start, end exclusive)
BODIES = {
    'LooseFire_ctor': (0x202B70, 0x202C48),
    'LooseFire_run': (0x202C48, 0x202C98),
    'LooseFire_onTouch': (0x1FCB70, 0x1FCEF0),
    'poisonGasSpell_ctor': (0x202DE8, 0x202F00),
    'fx_spawn id-5 arm': (0x1F0AE0, 0x1F0C00),
    'Fire_ctor': (0x2020E0, 0x202158),
    'Fire_run': (0x1F34E0, 0x1F3830),
    'obj_runEveryFrame': (0x14F248, 0x14F290),
    'GameObject_ctor (reused)': (0x14CB10, 0x14CF8C),
}


def f32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def is_stack(addr):
    return STACK_LO <= addr < STACK_HI


def desc_canon(mem, v):
    """A damage descriptor on the stack as ref_skills_a.descriptor() names it: the eight
    halfwords at +0x10 must be 0 and the bytes +0x20 / +0x21 0xff; each effect slot at
    +0x24 is None when its type is -1, else its four halfwords."""
    if v == 0 or not is_stack(v):
        return v
    ok = all(mem.u16(v + 0x10 + 2 * k) == 0 for k in range(8)) and mem.u8(v + 0x20) == 0xFF \
        and mem.u8(v + 0x21) == 0xFF
    if not ok:
        return ('desc?', bytes(mem.read(v + 0x10, 0x34)).hex())
    slots = []
    for k in range(4):
        base = v + 0x24 + 8 * k
        slots.append(None if mem.u16(base) == 0xFFFF else tuple(mem.u16(base + 2 * j) for j in range(4)))
    return ('desc',) + tuple(slots)


def describe_calls(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return 'call %d: model %r / original %r' % (i, x, y)
    if len(a) != len(b):
        longer = a if len(a) > len(b) else b
        return 'call %d: only the %s makes %r' % (min(len(a), len(b)), 'model' if len(a) > len(b) else 'original',
                                                  longer[min(len(a), len(b))])
    return 'equal'


class ModelView(RC.Memory):
    """The model's copy-on-write view of the interpreter's memory."""


class Script:
    """The answers of the stubs, the same on both sides: reset() before each side."""

    def __init__(self):
        self.pool, self.enemy, self.damage = [], 1, 0
        self._pool = 0

    def reset(self):
        self._pool = 0

    def respond(self, name, args):
        if name == 'pool_new':
            answer = self.pool[self._pool] if self._pool < len(self.pool) else 0
            self._pool += 1
            return answer
        if name == 'Creature.v20':
            return self.enemy
        if name == 'damage_apply':
            return self.damage
        if name == 'handle_removeNode':
            return 0
        return None


class Rig:
    def __init__(self, elf):
        emu = self.emu = EE(elf, fpu_model='ps2')
        emu.div_zero = 'r5900'
        emu.trace = []
        self.script = Script()
        self.calls = []
        emu.follow = type('Follow', (), {'__contains__': lambda _s, t: t in REAL or LIB_LO <= t < LIB_HI})()
        for addr, name in STUBS.items():
            emu.stub(addr, function=self.make_stub(name, PC.EXTERNALS[name]), name=name)
        mem = emu.mem
        for i in range(PC.FX_DEF_COUNT):
            mem.w32(PC.FX_DEF_FLAGS + 4 * i, 1)
        self.vec_arg = emu.alloc(0x10)
        self.blocks = [emu.alloc(0x80) for _ in range(48)]
        self.next_block = 0
        self.objs = [emu.alloc(0x80) for _ in range(4)]
        self.nodes = [emu.alloc(0x10) for _ in range(4)]
        self.others = [emu.alloc(0x60) for _ in range(4)]
        self.owner_table = emu.alloc(0x100)
        mem.w32(self.owner_table + 8 * 20 + 4, FN_V20)
        self.pcs = set()
        self.unknown = {}

    def block(self):
        b = self.blocks[self.next_block % len(self.blocks)]
        self.next_block += 1
        for off in range(0, 0x80, 4):
            self.emu.mem.w32(b + off, 0)
        return b

    def decode(self, ext, emu):
        mem, canon = emu.mem, []
        for i, kind in enumerate(ext.ints):
            v = emu.r[4 + i] & M32
            if kind == 'p':
                canon.append('stack' if is_stack(v) else v)
            elif kind == 'v':
                canon.append(tuple(mem.u32(v + 4 * j) for j in range(3)))
            elif kind == 'D':
                canon.append(desc_canon(mem, v))
            else:
                canon.append(v)
        for j in range(ext.floats):
            canon.append(emu.f[12 + j] & M32)
        return tuple(canon)

    def make_stub(self, name, ext):
        def stub(emu):
            args = self.decode(ext, emu)
            self.calls.append((name, args))
            answer = self.script.respond(name, args)
            return 0 if answer is None else answer
        return stub

    def callbacks(self):
        script = self.script

        class Callbacks:
            def get(self, name):
                def answer(*args):
                    return script.respond(name, args)
                return answer
        return Callbacks()

    def stored_bytes(self):
        out = set()
        for pc, addr, size, _value in self.emu.writes:
            if LIB_LO <= pc < LIB_HI or is_stack(addr):
                continue
            out.update(range(addr, addr + size))
        return out

    def compare(self, key, args):
        addr, kinds, ret_kind, method = ENTRIES[key]
        emu, mem = self.emu, self.emu.mem
        seed_before = mem.u32(RC.G_RAND_SEED)
        margs, regs = [], []
        for value, kind in zip(args, kinds):
            if kind == 'v':
                for j in range(3):
                    mem.w32(self.vec_arg + 4 * j, value[j])
                regs.append(self.vec_arg)
                margs.append(tuple(value))
            else:
                regs.append(value & M32)
                margs.append(value & M32)
        mview = ModelView(mem)
        model = PC.Model(mview, self.callbacks())
        self.script.reset()
        try:
            mret = getattr(model, method)(*margs)
        except (EmuError, NotImplementedError) as exc:
            return ['model stopped: %s' % exc]
        self.calls = []
        emu.reset_log()
        emu.r[29] = emu.stack_hi - 0x800
        self.script.reset()
        try:
            eret = emu.call(addr, *regs, max_steps=2000000)
        except EmuError as exc:
            return ['original stopped: %s' % exc]
        self.pcs.update(emu.trace)
        problems = []
        for call in emu.calls:
            t = call.target
            if t not in REAL and t not in STUBS and not LIB_LO <= t < LIB_HI:
                self.unknown[t] = self.unknown.get(t, 0) + 1
                problems.append('unknown call to %x' % t)
        if model.calls != self.calls:
            problems.append(describe_calls(model.calls, self.calls))
        stored = self.stored_bytes()
        mstored = set()
        for a, size, _v in model.writes:
            if not is_stack(a):
                mstored.update(range(a, a + size))
        diff = [a for a in sorted(stored | mstored) if mem.load(a, 1) != mview.load(a, 1)]
        if stored != mstored or diff:
            problems.append('writes: only original %s; only model %s; values differ at %s' % (
                sorted('%x' % a for a in stored - mstored)[:8],
                sorted('%x' % a for a in mstored - stored)[:8],
                ['%x:%02x/%02x' % (a, mem.load(a, 1), mview.load(a, 1)) for a in diff[:8]]))
        expect = seed_before
        for _ in range(model.draws):
            expect = (expect * 0x19660D + 0x3C6EF35F) & M32
        if not mem.u32(RC.G_RAND_SEED) == mview.load(RC.G_RAND_SEED, 4) == expect:
            problems.append('seed: model draws %d, original %08x model %08x' % (
                model.draws, mem.u32(RC.G_RAND_SEED), mview.load(RC.G_RAND_SEED, 4)))
        if ret_kind == 'i' and (eret & M32) != ((mret or 0) & M32):
            problems.append('result %08x / %08x' % (eret & M32, (mret or 0) & M32))
        self.draws = model.draws
        if method == 'loosefire_ctor':
            # the Inferred count of ref_potion_ctors.loosefire_draws, against the original
            used = self.script.pool[:sum(1 for name, _a in self.calls if name == 'pool_new')]
            if PC.loosefire_draws(used) != model.draws:
                problems.append('loosefire_draws %d / drawn %d' % (PC.loosefire_draws(used), model.draws))
        return problems


# ---------------------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------------------
def rand_pos(rng):
    pick = rng.random()
    if pick < 0.1:
        return tuple(f32(v) for v in (rng.uniform(-40000, 40000), rng.uniform(-40000, 40000), rng.uniform(-50, 50)))
    if pick < 0.15:
        return (C.ZERO, 0x80000000, f32(-0.0))
    return tuple(f32(rng.uniform(-15000, 15000)) for _ in range(2)) + (f32(rng.uniform(-200, 400)),)


def rand_frame(rng, n):
    special = (0, 1, 20, 40, 19, -20, -1, 0x7FFFFFFF, 0x7FFFFF88, 0x80000000)
    if n < len(special):
        return special[n] & M32
    return rng.choice((rng.randrange(0, 1 << 20), rng.randrange(0, 1 << 31), 20 * rng.randrange(0, 50000)))


def pool_plan(rig, rng, n, count=4):
    """What pool_new answers in order: fresh blocks, now and then 0."""
    mode = n % 4 if n < 8 else rng.choice((0, 0, 0, 1, 2, 3))
    plan = []
    for i in range(count):
        if mode == 1:
            plan.append(0)
        elif mode == 2:
            plan.append(rig.block() if i % 2 else 0)
        elif mode == 3:
            plan.append(rig.block() if rng.random() < 0.7 else 0)
        else:
            plan.append(rig.block())
    return plan


def generate(rig, key, rng, n):
    mem, script = rig.emu.mem, rig.script
    script.pool, script.enemy, script.damage = [], 1, rng.getrandbits(32)
    if key != 'LooseFire_five' or n % 5 == 0:
        mem.w32(RC.G_RAND_SEED, rng.getrandbits(32))
        mem.w32(RC.G_SIM_FRAME, rand_frame(rng, n))
    if key == 'obj_runEveryFrame':
        obj = rig.block()
        if n % 2:
            mem.w32(obj + 4, rig.nodes[n % 4])
        return (obj,)
    if key == 'fx_spawn5':
        script.pool = pool_plan(rig, rng, n)
        return (5, rand_pos(rng))
    if key == 'Fire_ctor':
        obj = rig.block()
        if n % 3 == 1:
            mem.w32(obj + 0xC, rng.getrandbits(32))
            mem.w8(obj + 0x28, rng.getrandbits(8))
        return (obj, rand_pos(rng))
    if key == 'Fire_run':
        obj = rig.block()
        for i, word in enumerate(rand_pos(rng)):
            mem.w32(obj + 0x10 + 4 * i, word)
        mem.w32(obj + 0x48, PC.VT_FIRE)
        mem.w32(obj + 0x44, rng.getrandbits(32))
        lives = (100, 99, 81, 80, 50, 21, 20, 19, 2, 1, 0, -1, -300, 0x7FFF, 0x8000, 0x8001)
        life = lives[n] if n < len(lives) else rng.choice((rng.randrange(1, 101), rng.randrange(-0x8000, 0x8000)))
        mem.w16(obj + 0x4C, life & 0xFFFF)
        mem.w32(PC.G_GLOW_TEXTURE, rng.choice((0, 0x00A12340, rng.getrandbits(32))))
        return (obj,)
    if key in ('LooseFire_ctor', 'LooseFire_five'):
        obj = rig.block()
        script.pool = pool_plan(rig, rng, n)
        owner = rng.choice((0, rig.others[0], rig.others[1])) if n >= 2 else (0, rig.others[0])[n]
        return (obj, rand_pos(rng), owner)
    if key == 'LooseFire_run':
        obj = rig.block()
        mem.w32(obj + 0x48, PC.VT_LOOSEFIRE)
        frame = RC.s32(mem.u32(RC.G_SIM_FRAME))
        end = frame + rng.choice((-121, -1, 0, 1, 120, -5000, 5000))
        if rng.random() < 0.1:
            end = rng.choice((0x7FFFFFFF, -0x80000000))
        mem.w32(obj + 0x50, end & M32)
        return (obj,)
    if key == 'LooseFire_onTouch':
        obj, other = rig.block(), rig.others[2]
        mem.w32(obj + 0x48, PC.VT_LOOSEFIRE)
        if n >= 10 and rng.random() < 0.7:
            mem.w32(RC.G_SIM_FRAME, (20 * rng.randrange(-100000, 100000)) & M32)
        owner_kind = n % 4 if n < 40 else rng.choice((0, 1, 2, 2, 3))
        if owner_kind:
            node, owner = rig.nodes[0], rig.others[3]
            for off in range(0, 0x60, 4):
                mem.w32(owner + off, 0)
            mem.w32(obj + 0x4C, node)
            mem.w32(node + 0xC, owner)
            mem.w32(owner + 0x48, rig.owner_table)
            # 1: an owner that is not a creature; 2: a creature owner that says enemy;
            # 3: a creature owner that says no
            flags = rng.choice((0, 0x40000, 0x4081)) if owner_kind == 1 else rng.choice((0x20, 0x28, 0x60))
            mem.w32(owner + 0xC, flags)
            script.enemy = 0 if owner_kind == 3 else rng.choice((1, 4, 0x100))
        for off in range(0, 0x60, 4):
            mem.w32(other + off, 0)
        toucher = (n // 4) % 5 if n < 40 else rng.randrange(5)
        mem.w32(other + 0xC, (0, 0x20, 0x40, 0x60, 0x4081)[toucher] | rng.choice((0, 0x1000, 0x20000)))
        mem.w32(PC.G_DIFFICULTY, rng.choice((0, 1, 2, 3, 4, 5, 6, -1, 0x7FFFFFFF)) & M32)
        return (obj, other)
    if key in ('poisonGasSpell_ctor', 'poisonGas_potion'):
        obj = rig.block()
        owner = rng.choice((0, rig.others[0])) if n >= 2 else (0, rig.others[0])[n]
        if key == 'poisonGas_potion':
            return (obj, rand_pos(rng), 0x12C, 0x14, 0, owner, 5)
        radii = (0, 9, 10, 11, -1, -0x80000000, 0x7FFFFFFF, 20, 0x28)
        radius = radii[n] if n < len(radii) else rng.choice((rng.randrange(-20, 200), rng.getrandbits(32)))
        life = rng.choice((0x12C, 0, 1, 600, -1, rng.getrandbits(32)))
        return (obj, rand_pos(rng), life & M32, radius & M32, rng.choice((0, 1, rng.getrandbits(32))),
                owner, rng.choice((5, 25, 0, 0x12345, rng.getrandbits(32))))
    raise KeyError(key)


def find_elf(path):
    """The path given, else SLUS_209.73 at the top of the checkout or in local/."""
    candidates = [path] if path else [os.path.join(ROOT, 'SLUS_209.73'), os.path.join(ROOT, 'local', 'SLUS_209.73')]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


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
    elf = find_elf(elf)
    if elf is None:
        print('difftest_potion_ctors: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('difftest_potion_ctors: %s is not SLUS_209.73 US v2.00 - skipped' % elf)
        return 0
    C.set_fpu('ps2')
    cases = max(OPTIONS['cases'] // 10, 5) if OPTIONS['quick'] else OPTIONS['cases']
    started = time.time()
    rig = Rig(elf)
    total = failed_total = 0
    draws = {}
    print('%-22s %8s %8s %8s  first problem' % ('entry point', 'cases', 'failed', 'draws'))
    for index, key in enumerate(ENTRIES):
        if OPTIONS['filter'] and OPTIONS['filter'].lower() not in key.lower():
            continue
        rng = random.Random('%d/%s' % (OPTIONS['seed'], key))
        failed, shown, drawn = 0, [], 0
        for n in range(cases):
            call = generate(rig, key, rng, n)
            rig.draws = 0
            problems = rig.compare(key, call)
            drawn += rig.draws
            if problems:
                failed += 1
                if len(shown) < 3:
                    shown.append('case %d: %s' % (n, '; '.join(problems)))
        total += cases
        failed_total += failed
        draws[key] = drawn
        print('%-22s %8d %8d %8d' % (key, cases, failed, drawn))
        for line in shown:
            print('    ' + line[:600])
    print('coverage of the original (instructions executed / in the body):')
    for name, (start, end) in BODIES.items():
        hit = sorted(pc for pc in rig.pcs if start <= pc < end)
        size = (end - start) // 4
        print('  %-28s %4d of %4d' % (name, len(hit), size))
        if OPTIONS['verbose'] and len(hit) != size:
            missing = [a for a in range(start, end, 4) if a not in rig.pcs]
            print('      not executed: %s' % ' '.join('%06x' % a for a in missing))
    if rig.unknown:
        print('unknown calls: %s' % ', '.join('%x x%d' % kv for kv in sorted(rig.unknown.items())))
    print('summary: %d cases, %d mismatches, seed %d, %.1f s' % (total, failed_total, OPTIONS['seed'],
                                                                time.time() - started))
    return 0 if failed_total == 0 and not rig.unknown else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
