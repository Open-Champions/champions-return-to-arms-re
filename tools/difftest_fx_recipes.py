#!/usr/bin/env python3
"""difftest_fx_recipes.py - compare tools/ref_fx_recipes.py with the game's own machine code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_fx_recipes.py [path/to/SLUS_209.73] [--quick] [--seed N] [-k TEXT] [-v]

    --quick   a tenth of the samples
    --seed N  seed of the random choices (default 20973); one seed repeats exactly
    -k TEXT   run only the properties whose name contains TEXT
    -v        print up to three failing cases per property

Every property prints one line: PASS or FAIL, the name, the number of cases compared and
what was compared.  Exit status 1 when any property fails.

How a property is tested
    The ORIGINAL function is executed by tools/ee_emu.py (an instruction interpreter, not a
    console) on memory this script prepares (random positions, generator seeds, option
    values, synthetic objects and models).  The primitives it calls - particle_spawn,
    particleDef_ctor, isNearCameraFocus480, the sound calls, pool_new, Fire_ctor, glow_add,
    trail_*, fx_spawn where a recipe calls it, GutChunk and LightEffect constructors - are
    replaced by recorders, and the recorded stream (every argument, floats as 32-bit
    patterns) is compared with the stream the reference produces, together with the final
    generator states and the stores the function makes to the memory it owns.  "Bit for
    bit" means identical under the interpreter's floating-point model (its default "ps2"
    adder); the effects are cosmetic, so the other adder models are not repeated here.
"""
import hashlib
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError, M32                    # noqa: E402
import ref_core as C                                    # noqa: E402
import ref_fx_recipes as R                              # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False}
RESULTS = []

# ---- addresses in SLUS_209.73 -----------------------------------------------------------
FX_SPAWN = 0x1EF270
PARTICLE_SPAWN, PARTICLE_DEF_CTOR = 0x18F3F8, 0x18F3D0
NEAR_CAMERA, SPRINTF, RES_FIND, SOUND_AT_POS = 0x1EBD90, 0x3B7EF0, 0x17365C, 0x214428
POOL_NEW, FIRE_CTOR = 0x14FDB8, 0x2020E0
DISINTEGRATE, SHATTER = 0x1F4340, 0x1FB240
SAMPLE_POINT, SAMPLE_COUNT, PHPROP_CTOR = 0x178E18, 0x1799C8, 0x155A0C
MATH_COS16 = 0x166630
G_COSMETIC_SEED, G_RAND_SEED, G_DECAL_DETAIL = 0x404460, 0x404464, 0x44FDC0
RES_ENTRY = 0x00C0FFE0                                  # what the res_find stub answers


def wanted(name):
    return OPTIONS['filter'] is None or OPTIONS['filter'].lower() in name.lower()


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-30s %7d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:3]:
            print('        ' + line)
    sys.stdout.flush()


def scaled(count):
    return max(count // 10, 4) if OPTIONS['quick'] else count


def vec(emu, addr):
    return [emu.mem.u32((addr + 4 * k) & M32) for k in range(3)]


class Harness:
    """One interpreter with the recorders installed; reused across cases."""

    def __init__(self, elf):
        self.emu = EE(elf)
        self.log = []
        self.pool_answer = 1
        self.near_answer = 1
        self.emu.mem.map(0x01800000, 0x1000)            # where pool_new's block lives
        e = self.emu
        e.stub(PARTICLE_SPAWN, function=lambda m: self.log.append(
            ('spawn', m.f[12], m.r[4] & M32, vec(m, m.r[5]), vec(m, m.r[6]))))
        e.stub(PARTICLE_DEF_CTOR, function=lambda m: self.log.append(('ctor', m.r[4] & M32)))
        e.stub(NEAR_CAMERA, function=self._near)
        e.stub(SPRINTF, function=lambda m: self.log.append(('sound_name', m.r[6] & M32)))
        e.stub(RES_FIND, function=self._res_find)
        e.stub(SOUND_AT_POS, function=self._sound)
        e.stub(POOL_NEW, function=self._pool_new)
        e.stub(FIRE_CTOR, function=lambda m: self.log.append(('fire', vec(m, m.r[5]))))
        e.stub(SAMPLE_COUNT, function=self._sample_count)
        e.stub(SAMPLE_POINT, function=self._sample_point)
        e.stub(PHPROP_CTOR, function=self._phprop)
        self.pos = e.alloc(16)
        self.obj = e.alloc(0x300)
        self.blocks = [e.alloc(0x300) for _ in range(8)]
        self.model = None
        self.last_block = None

    # ---- model queries answered from a synthetic model -------------------------------
    def _sample_count(self, m):
        self.flush_block()
        self.log.append(('sample_count',))
        return self.model.sample_count()

    def _sample_point(self, m):
        self.flush_block()
        if m.r[11] & M32:
            self.log.append(('sample t3?', m.r[11] & M32))
        yaw = C.s16(m.r[7])
        self.log.append(('sample', m.f[12], m.r[5] & M32, vec(m, m.r[6]), yaw, C.s32(m.r[8])))
        point, size = self.model.sample_point(m.f[12], m.r[5] & M32, vec(m, m.r[6]), yaw,
                                              C.s32(m.r[8]))
        for k in range(3):
            m.mem.w32((m.r[9] + 4 * k) & M32, point[k])
        m.mem.w32(m.r[10] & M32, size)
        return 0

    def _phprop(self, m):
        def name(a):
            a &= M32
            return m.mem.cstr(a) if a else 0
        self.log.append(('phprop', m.f[12], vec(m, m.r[5]), name(m.r[6]), name(m.r[7]),
                         name(m.r[8]), m.r[9] & M32, m.r[10] & M32, m.r[11] & M32))
        return 0

    def flush_block(self):
        if self.last_block is not None:
            v = self.emu.mem.u32(self.last_block + 0x48)
            if v:
                self.log.append(('vtable', v))
            self.last_block = None

    def begin(self):
        self.emu.reset_log()
        self.log = []
        self.last_block = None
        for b in self.blocks:
            self.emu.mem.write(b, bytes(0x300))
        self.block_index = 0

    def _near(self, m):
        self.log.append(('near', vec(m, m.r[4])))
        return self.near_answer

    def _res_find(self, m):
        a1 = m.r[5] & M32
        if a1 == 0 or a1 >= 0x01000000:          # a name formatted on the stack (stubbed sprintf)
            self.log.append(('res_find', m.mem.cstr(m.r[4] & M32)))
        else:
            self.log.append(('res_find', m.mem.cstr(m.r[4] & M32), m.mem.cstr(a1)))
        return RES_ENTRY

    def _sound(self, m):
        if m.r[4] & M32 != RES_ENTRY:
            self.log.append(('sound?', m.r[4] & M32))
        self.log.append(('sound', m.f[12], vec(m, m.r[5])))
        return 0

    def _pool_new(self, m):
        self.flush_block()
        self.log.append(('pool_new', m.r[4] & M32))
        if not self.pool_answer:
            return 0
        if self.model is None:
            return 0x01800000
        self.last_block = self.blocks[self.block_index % len(self.blocks)]
        self.block_index += 1
        return self.last_block

    def fx_spawn(self, fx_id, pos, cosmetic, shared, near, gore, made):
        e = self.emu
        e.reset_log()
        self.log = []
        self.near_answer = 1 if near else 0
        for k in range(3):
            e.mem.w32(self.pos + 4 * k, pos[k])
        e.mem.w32(G_COSMETIC_SEED, cosmetic)
        e.mem.w32(G_RAND_SEED, shared)
        e.mem.w32(G_DECAL_DETAIL, gore)
        for i, d in enumerate(R.FX_SPAWN_DEFS):
            e.mem.w32(R.FX_SPAWN_MADE_FLAGS + 4 * i, 1 if d in made else 0)
        e.fset(12, 777.0)                                # a stale backdate argument
        e.call(FX_SPAWN, fx_id, self.pos)
        flags = set(d for i, d in enumerate(R.FX_SPAWN_DEFS)
                    if e.mem.u32(R.FX_SPAWN_MADE_FLAGS + 4 * i))
        return self.log, e.mem.u32(G_COSMETIC_SEED), e.mem.u32(G_RAND_SEED), flags


def random_pos(rng):
    kind = rng.random()
    if kind < 0.6:
        return [C.f32(rng.uniform(-4000, 4000)) for _ in range(3)]
    if kind < 0.9:
        return [C.f32(float(rng.randint(-3000, 3000)) + rng.choice((0, 0.5, 0.25))) for _ in range(3)]
    return [C.f32(rng.uniform(-30000, 30000)) for _ in range(3)]


def diff_streams(got, want):
    if len(got) != len(want):
        for i, (a, b) in enumerate(zip(got, want)):
            if a != b:
                return 'call %d: original %r, reference %r (lengths %d / %d)' % (i, a, b, len(got), len(want))
        return 'lengths %d / %d' % (len(got), len(want))
    for i, (a, b) in enumerate(zip(got, want)):
        if a != b:
            return 'call %d: original %r, reference %r' % (i, a, b)
    return None


def prop_fx_spawn(h):
    for fx_id in list(range(0, 0x17)) + [0x17, -1]:
        name = 'fx_spawn id %d' % fx_id
        if not wanted(name):
            continue
        rng = random.Random('%d/%s' % (OPTIONS['seed'], name))
        heavy = fx_id in (0, 1, 2, 3, 4, 6, 8, 9, 10, 11, 12)
        count = scaled(300 if heavy else 3000)
        failures, examples, spawns = 0, [], 0
        for case in range(count):
            pos = random_pos(rng)
            cos_seed, shr_seed = rng.getrandbits(32), rng.getrandbits(32)
            near = rng.random() < 0.85
            gore = rng.choice((0, 1, 2))
            made = set(d for d in R.FX_SPAWN_DEFS if rng.random() < (0.9 if case % 4 else 0.3))
            h.pool_answer = 0 if rng.random() < 0.2 else 1
            got, got_c, got_s, got_flags = h.fx_spawn(fx_id, pos, cos_seed, shr_seed, near, gore, made)
            cos, shr = C.Lcg(cos_seed), C.Lcg(shr_seed)
            ref_made = set(made)
            want = R.fx_spawn(fx_id, pos, cos, shr, near=near, gore=gore, made=ref_made,
                              pool_new=lambda size: h.pool_answer)
            spawns += sum(1 for c in got if c[0] == 'spawn')
            problem = diff_streams(got, want)
            if problem is None and (got_c, got_s) != (cos.state, shr.state):
                problem = 'seeds %08x %08x / %08x %08x' % (got_c, got_s, cos.state, shr.state)
            if problem is None and got_flags != ref_made:
                problem = 'made flags differ'
            if problem:
                failures += 1
                examples.append('case %d (seed %08x, near %s, gore %d): %s' % (case, cos_seed, near, gore, problem))
        report(name, failures, count, 'call stream (%d particle_spawn calls), both seeds, made flags'
               % spawns, examples)


class SyntheticModel:
    """Sample points answered from a table: points scattered around the position, sizes
    in a range that makes 0-12 particles per point for the size-cubed recipes."""

    def __init__(self, rng, count=None):
        self.n = rng.randint(0, 40) if count is None else count
        self.points = [[C.f32(rng.uniform(-3000, 3000)) for _ in range(3)] for _ in range(max(self.n, 1))]
        self.sizes = [C.f32(rng.choice((rng.uniform(0, 10000), rng.uniform(0, 800), 0.0, -50.0)))
                      for _ in range(max(self.n, 1))]

    def sample_count(self):
        return self.n

    def sample_point(self, scale, anim, pos, yaw, index):
        i = index % len(self.points)
        p = [C.add(self.points[i][k], C.mul(scale, pos[k])) for k in range(3)]
        return p, self.sizes[i]


def prop_disintegrate(h):
    name = 'disintegrate'
    if not wanted(name):
        return
    rng = random.Random('%d/%s' % (OPTIONS['seed'], name))
    count = scaled(1500)
    failures, examples, spawns = 0, [], 0
    for case in range(count):
        h.begin()
        model = SyntheticModel(rng)
        h.model = model
        pos = random_pos(rng)
        yaw = rng.getrandbits(16)
        scale = C.f32(rng.choice((1.0, rng.uniform(0.5, 2.0))))
        offset = C.f32(rng.choice((0.0, 0.0, -0.0, rng.uniform(-40, 40))))
        alternate = rng.choice((0, 1))
        anim = rng.choice((0, 0x01234560))
        seed = rng.getrandbits(32)
        e = h.emu
        for k in range(3):
            e.mem.w32(h.pos + 4 * k, pos[k])
        e.mem.w32(h.obj + 0xC, 0x10)
        e.mem.w32(G_COSMETIC_SEED, seed)
        e.fset(12, C.to_float(scale))
        e.f[13] = offset
        e.call(DISINTEGRATE, h.obj, 0x01230000, anim, h.pos, yaw, alternate)
        got = h.log
        if e.mem.u32(h.obj + 0xC) == 0x12:
            got = [('hide',)] + got
        cos = C.Lcg(seed)
        want = R.disintegrate_model(model, pos, yaw, scale, offset, alternate, anim, cos)
        spawns += sum(1 for c in want if c[0] == 'spawn')
        problem = diff_streams(got, want)
        if problem is None and e.mem.u32(G_COSMETIC_SEED) != cos.state:
            problem = 'seed'
        if problem:
            failures += 1
            examples.append('case %d: %s' % (case, problem))
    report(name, failures, count, 'call stream (%d particle_spawn calls, backdates), sample queries, '
           'hide flag, seed' % spawns, examples)


def prop_shatter(h):
    name = 'ice shatter'
    if not wanted(name):
        return
    rng = random.Random('%d/%s' % (OPTIONS['seed'], name))
    count = scaled(3000)
    failures, examples, chunks = 0, [], 0
    for case in range(count):
        h.begin()
        model = SyntheticModel(rng)
        h.model = model
        pos = random_pos(rng)
        yaw = rng.getrandbits(16)
        n = C.f32(rng.choice((rng.randint(1, 12), rng.uniform(0.6, 15.0))))
        if C.s32(C.to_int(n)) == 0:
            n = C.f32(1.0)                       # the original divides by the count
        scale = C.f32(rng.uniform(0.5, 2.0))
        offset = C.f32(rng.choice((0.0, rng.uniform(-40, 40))))
        anim = rng.choice((0, 0x01234560))
        seed = rng.getrandbits(32)
        h.pool_answer = 0 if rng.random() < 0.1 else 1
        e = h.emu
        for k in range(3):
            e.mem.w32(h.pos + 4 * k, pos[k])
        e.mem.w32(G_RAND_SEED, seed)
        e.f[12], e.f[13], e.f[14] = n, scale, offset
        e.call(SHATTER, 0x01230000, anim, h.pos, yaw)
        h.flush_block()
        shared = C.Lcg(seed)
        want = R.shatter_to_loose_ice(model, pos, yaw, n, scale, offset, anim, shared,
                                      pool_new=lambda size: h.pool_answer)
        chunks += sum(1 for c in want if c[0] == 'phprop')
        problem = diff_streams(h.log, want)
        if problem is None and e.mem.u32(G_RAND_SEED) != shared.state:
            problem = 'seed'
        if problem:
            failures += 1
            examples.append('case %d: %s' % (case, problem))
    report(name, failures, count, 'call stream (%d chunks: position, part mask, names, flags, table), '
           'sample queries, shared seed' % chunks, examples)


def find_inputs(positional):
    for item in positional:
        if os.path.isfile(item):
            return item
    for candidate in (os.path.join(ROOT, 'SLUS_209.73'), 'SLUS_209.73'):
        if os.path.isfile(candidate):
            return candidate
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
    elf = find_inputs(positional)
    if elf is None:
        print('SKIP  no SLUS_209.73 found (pass its path); nothing was tested')
        return 0
    with open(elf, 'rb') as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('SKIP  %s is not the US v2.00 executable this test was written for' % elf)
        return 0
    started = time.time()
    print('executable %s, seed %d' % (elf, OPTIONS['seed']))
    h = Harness(elf)
    prop_fx_spawn(h)
    prop_disintegrate(h)
    prop_shatter(h)
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d failed, %.0f s' % (len(RESULTS), len(failed), time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
