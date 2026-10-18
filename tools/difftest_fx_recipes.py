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

Properties
    fx_spawn id N         fx_spawn 0x1ef270 for every id 0..0x16 and two outside the table
    disintegrate          fx_disintegrateModel 0x1f4340
    ice shatter           fx_shatterToLooseIce 0x1fb240 (shared seed)
    lose part <class>     the eight callers of GutChunk_ctorFromProp 0x201ad0
    emit from model verts fx_emitFromModelVerts 0x1eb1e8
    model sparkle         fx_modelParticlesNearCamera_1f5210
    model arcs            fx_modelParticlesNearCamera_1f61c0
    model glow            fx_drawModelGlowNearCamera 0x1f5890
    weapon status         fx_modelStatusEffects 0x1f6ac8
    Models are synthetic: their sample points, attach matrices and blade segment are answered
    by the recorders from made-up tables, so the recipes are compared in terms of those
    queries (what a native client gets from its own model code).
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
BUILD_HIDE_MASK, GUT_FROM_PROP, ATTACH_POINT = 0x179550, 0x201AD0, 0x1754A0
EMIT_FROM_VERTS, SPARKLE, ARCS, MODEL_GLOW = 0x1EB1E8, 0x1F5210, 0x1F61C0, 0x1F5890
GLOW_ADD, BEAM_CREATE, BEAM_UPDATE = 0x18FC78, 0x193088, 0x1933C8
G_SIM_FRAME = 0x44FDCC
STATUS_FX, DIALOG_OPEN, ATTACH_MATRIX, EFFECT_SEGMENT = 0x1F6AC8, 0x22FBC0, 0x1795F8, 0x1791A0
TRAIL_CREATE, TRAIL_PAIR, TRANSFORM_SAMPLE, BEAM_ALIVE = 0x190FF8, 0x192650, 0x1799E8, 0x193360
G_LEVEL_FLAGS = 0x44FE08
TEXTURE_VALUE = 0x00ABC000                              # what *0x4f848c holds in the tests
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
        e.stub(BUILD_HIDE_MASK, function=self._mask)
        e.stub(GUT_FROM_PROP, function=self._gut)
        e.stub(ATTACH_POINT, function=self._attach)
        e.stub(GLOW_ADD, function=self._glow)
        e.stub(BEAM_CREATE, function=self._beam_create)
        e.stub(BEAM_UPDATE, function=lambda m: self.log.append(
            ('beam_update', m.r[4] & M32, vec(m, m.r[5]), vec(m, m.r[6]), C.s32(m.r[7]), m.r[8] & M32)))
        self.get_model = e.alloc(16)                     # the object's virtual "model" slot
        e.stub(self.get_model, function=lambda m: (self.log.append(('get_model',)), 0x01230000)[1])
        self.vtable = e.alloc(0x100)
        e.mem.w32(self.vtable + 0x84, self.get_model)
        e.mem.w16(self.vtable + 0x80, 0)
        e.mem.w32(R.GLOW_TEXTURE_HALO2, TEXTURE_VALUE)
        e.stub(DIALOG_OPEN, function=lambda m: (self.log.append(('dialog_open',)), self.dialog)[1])
        e.stub(ATTACH_MATRIX, function=self._attach_matrix)
        e.stub(EFFECT_SEGMENT, function=self._effect_segment)
        e.stub(TRAIL_CREATE, function=lambda m: (self.log.append(
            ('trail_create', m.f[12], m.r[4] & M32, m.r[5] & M32, m.r[6] & M32, m.r[7] & M32,
             m.r[8] & M32, m.r[9] & M32, m.r[10] & M32)), self.answers.get('trail_create', 0))[1])
        e.stub(TRAIL_PAIR, function=lambda m: self.log.append(
            ('trail_pair', m.f[12], m.r[4] & M32, vec(m, m.r[5]), vec(m, m.r[6]))))
        e.stub(TRANSFORM_SAMPLE, function=self._transform_sample)
        e.stub(BEAM_ALIVE, function=lambda m: (self.log.append(('beam_alive', m.r[4] & M32)),
                                               self.answers.get('beam_alive', 0))[1])
        self.dialog = 0
        self.answers = {}
        self.weapon = None
        self.holder = None
        self.beam_answer = 0
        self.gut_block = None
        self.pos = e.alloc(16)
        self.obj = e.alloc(0x500)
        self.cls = e.alloc(0x40)
        self.blocks = [e.alloc(0x300) for _ in range(8)]
        self.model = None
        self.last_block = None

    # ---- model queries answered from a synthetic model -------------------------------
    def _sample_count(self, m):
        self.flush_block()
        self.log.append(('sample_count',))
        if self.weapon is not None:
            return self.weapon.sample_count()
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

    @staticmethod
    def show_mask(model, variant):
        x = ((model * 0x2545F491) ^ (variant * 0x9E3779B97F4A7C15)) & 0xFFFFFFFFFFFFFFFF
        return (x ^ (x >> 29)) & 0xFFFFFFFFFFFFFFFF

    def _check_lift(self):
        if self.gut_block is not None:
            if self.emu.mem.u32(self.gut_block + 0x1C4) != 0x3F800000:
                self.log.append(('lift',))
            self.gut_block = None

    def _mask(self, m):
        self._check_lift()
        model, variant = m.r[4] & M32, m.r[5] & M32
        self.log.append(('mask', model, variant))
        v = self.show_mask(model, variant)
        m.r[3] = v >> 32                    # a 64-bit result: v0 holds all 64 bits
        return v

    def _gut(self, m):
        sp = m.r[29] & M32
        self.log.append(('gut', m.f[12], vec(m, m.r[5]), C.s16(m.r[6]), m.r[7] & M32,
                         m.r[8] & M32, m.r[9] & M32, m.r[10] & M32, m.r[11] & M32,
                         m.mem.u64(sp), m.mem.u32(sp + 8), m.mem.u32(sp + 16)))
        self.gut_block = m.r[4] & M32
        m.mem.w32(self.gut_block + 0x1C4, 0x3F800000)
        return 0

    def _glow(self, m):
        tex = m.r[9] & M32
        self.log.append(('glow', m.f[12], m.f[13], vec(m, m.r[4]),
                         [m.r[k] & M32 for k in (5, 6, 7, 8)],
                         R.GLOW_TEXTURE_HALO2 if tex == TEXTURE_VALUE else tex,
                         C.s32(m.r[10]), m.r[11] & M32))
        return 0

    def _beam_create(self, m):
        self.log.append(('beam_create', m.f[12], m.f[13], vec(m, m.r[4]), vec(m, m.r[5]),
                         m.r[6] & M32, m.r[7] & M32, m.r[8] & M32))
        return self.answers.get('beam_create', self.beam_answer)

    def _attach_matrix(self, m):
        self.log.append(('attach_matrix', m.f[12], m.r[5] & M32, C.s32(m.r[6])))
        mat = self.holder.attach_matrix(m.f[12], m.r[5] & M32, C.s32(m.r[6]))
        for k in range(12):
            m.mem.w32((m.r[7] + 4 * k) & M32, mat[k])
        return 0

    def _effect_segment(self, m):
        self.log.append(('effect_segment',))
        a, b = self.weapon.effect_segment()
        for k in range(3):
            m.mem.w32((m.r[5] + 4 * k) & M32, a[k])
            m.mem.w32((m.r[6] + 4 * k) & M32, b[k])
        return 1

    def _transform_sample(self, m):
        mat = [m.mem.u32((m.r[5] + 4 * k) & M32) for k in range(12)]
        index = C.s32(m.r[6])
        self.log.append(('transform_sample', mat, index))
        p, size = self.weapon.transform_sample_point(mat, index)
        for k in range(3):
            m.mem.w32((m.r[7] + 4 * k) & M32, p[k])
        m.mem.w32(m.r[8] & M32, size)
        return 0

    def _attach(self, m):
        self.log.append(('attach', m.f[12], m.r[4] & M32, vec(m, m.r[5]), C.s16(m.r[6]),
                         m.r[7] & M32, m.r[8] & M32))
        for k in range(3):
            m.mem.w32((m.r[9] + 4 * k) & M32, C.f32(1234.5 + k))
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

    def __init__(self, rng, count=None, big=False):
        self.n = rng.randint(0, 40) if count is None else count
        self.points = [[C.f32(rng.uniform(-3000, 3000)) for _ in range(3)] for _ in range(max(self.n, 1))]
        top = 45000 if big else 10000
        self.sizes = [C.f32(rng.choice((rng.uniform(0, top), rng.uniform(0, 800), 0.0, -50.0)))
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


def prop_lose_part(h):
    for name, row in R.LOSE_PART_CLASSES.items():
        prop = 'lose part %s' % name
        if not wanted(prop):
            continue
        rng = random.Random('%d/%s' % (OPTIONS['seed'], prop))
        count = scaled(2000)
        failures, examples, chunks = 0, [], 0
        e = h.emu
        for case in range(count):
            h.begin()
            h.model = None
            h.gut_block = None
            cls = [rng.getrandbits(32) for _ in range(8)]
            c = R.Creature(variant=rng.getrandbits(32) & rng.getrandbits(32), cls=cls,
                           pos=random_pos(rng), yaw=rng.getrandbits(16),
                           anim=h.obj + 0x114, colour=rng.choice((0, 1, 2)),
                           scale=C.f32(rng.uniform(0.5, 2)), kind=rng.choice((0, 0, 1)))
            part = rng.choice((rng.randint(-1, 13), rng.randint(0, 8), rng.getrandbits(32))) & M32
            h.pool_answer = 0 if rng.random() < 0.1 else 1
            for i, v in enumerate(cls):
                e.mem.w32(h.cls + 4 * i, v)
            e.mem.w32(h.obj + 0x24, h.cls)
            e.mem.w32(h.obj + 0xE8, c.variant)
            for k in range(3):
                e.mem.w32(h.obj + 0x10 + 4 * k, c.pos[k])
            e.mem.w16(h.obj + 0x38, c.yaw)
            e.mem.w8(h.obj + 0x3C8, c.colour)
            e.mem.w32(h.obj + 0xDC, c.scale)
            e.mem.w32(h.obj + 0x414, c.kind)
            e.mem.w64(h.obj + 0x220, 0)
            if name == 'Orc' and part in (6, 7):
                part = 5                      # never passed (see the reference)
            e.call(row[0], h.obj, part)
            h._check_lift()
            show = e.mem.u64(h.obj + 0x220)
            want = R.lose_body_part(name, c, part, h.show_mask, pool_new=lambda size: h.pool_answer)
            chunks += sum(1 for x in want if x[0] == 'gut')
            problem = diff_streams(h.log, want)
            if problem is None and e.mem.u32(h.obj + 0xE8) != c.variant:
                problem = 'variant %08x / %08x' % (e.mem.u32(h.obj + 0xE8), c.variant)
            if problem is None and show != c.show and want:
                problem = 'show mask'
            if problem:
                failures += 1
                examples.append('case %d part %d: %s' % (case, C.s32(part), problem))
        report(prop, failures, count, 'call stream (%d chunks: mesh mask, launch, blood bits, '
               'names, scale, lift), variant word, show mask' % chunks, examples)


def _setup(h, rng, count=None, big=False):
    h.begin()
    model = SyntheticModel(rng, count, big)
    h.model = model
    return model


def _check(name, h, want, seed_state, failures, examples, case):
    problem = diff_streams(h.log, want)
    if problem is None and h.emu.mem.u32(G_COSMETIC_SEED) != seed_state:
        problem = 'seed'
    if problem:
        examples.append('case %d: %s' % (case, problem))
        return failures + 1
    return failures


def prop_emit_from_verts(h):
    name = 'emit from model verts'
    if not wanted(name):
        return
    rng = random.Random('%d/%s' % (OPTIONS['seed'], name))
    count = scaled(3000)
    failures, examples, spawns = 0, [], 0
    e = h.emu
    for case in range(count):
        model = _setup(h, rng, rng.randint(1, 30))
        pos, yaw = random_pos(rng), rng.getrandbits(16)
        n = rng.choice((0, 1, 3, rng.randint(1, 40)))
        speed = C.f32(rng.uniform(-20, 20))
        direction = rng.choice((None, [C.f32(rng.uniform(-1, 1)) for _ in range(3)]))
        offset = rng.choice((None, [C.f32(rng.uniform(-50, 50)) for _ in range(3)]))
        defn = rng.getrandbits(24)
        seed = rng.getrandbits(32)
        e.mem.w32(h.obj + 0x48, h.vtable)
        for k in range(3):
            e.mem.w32(h.obj + 0x10 + 4 * k, pos[k])
        e.mem.w16(h.obj + 0x38, yaw)
        dptr, optr = h.blocks[0], h.blocks[1]
        if direction:
            for k in range(3):
                e.mem.w32(dptr + 4 * k, direction[k])
        if offset:
            for k in range(3):
                e.mem.w32(optr + 4 * k, offset[k])
        e.mem.w32(G_COSMETIC_SEED, seed)
        e.f[12] = speed
        e.call(EMIT_FROM_VERTS, h.obj, n, defn, dptr if direction else 0, optr if offset else 0)
        rng_ref = C.Lcg(seed)
        want = R.emit_from_model_verts(model, pos, yaw, h.obj + 0x114, n, defn, direction, offset,
                                       speed, rng_ref)
        spawns += sum(1 for c in want if c[0] == 'spawn')
        failures = _check(name, h, want, rng_ref.state, failures, examples, case)
    report(name, failures, count, 'call stream (%d particle_spawn calls), sample queries, seed'
           % spawns, examples)


def prop_sparkle(h):
    name = 'model sparkle'
    if not wanted(name):
        return
    rng = random.Random('%d/%s' % (OPTIONS['seed'], name))
    count = scaled(1500)
    failures, examples, spawns = 0, [], 0
    e = h.emu
    for case in range(count):
        model = _setup(h, rng, rng.choice((0, rng.randint(1, 30))), big=True)
        h.near_answer = 1 if rng.random() < 0.9 else 0
        pos, yaw = random_pos(rng), rng.getrandbits(16)
        amount = C.f32(rng.choice((rng.uniform(0, 1.5), rng.uniform(-0.2, 0.2), 0.0)))
        offset = C.f32(rng.choice((0.0, rng.uniform(-40, 40))))
        has_model = rng.random() < 0.95
        anim = rng.choice((0, 0x01234560))
        seed = rng.getrandbits(32)
        for k in range(3):
            e.mem.w32(h.pos + 4 * k, pos[k])
        e.mem.w32(G_COSMETIC_SEED, seed)
        e.f[12], e.f[13], e.f[14] = C.f32(5.0), amount, offset
        e.call(SPARKLE, 0x01230000 if has_model else 0, anim, h.pos, yaw)
        rng_ref = C.Lcg(seed)
        want = R.model_sparkle(model if has_model else None, pos, yaw, anim, amount, offset,
                               rng_ref, near=bool(h.near_answer))
        spawns += sum(1 for c in want if c[0] == 'spawn')
        failures = _check(name, h, want, rng_ref.state, failures, examples, case)
    h.near_answer = 1
    report(name, failures, count, 'call stream (%d particle_spawn calls, backdates), sample queries, '
           'seed' % spawns, examples)


def prop_arcs(h):
    name = 'model arcs'
    if not wanted(name):
        return
    rng = random.Random('%d/%s' % (OPTIONS['seed'], name))
    count = scaled(1500)
    failures, examples, spawns = 0, [], 0
    e = h.emu
    for case in range(count):
        model = _setup(h, rng, rng.choice((0, rng.randint(1, 30))))
        h.near_answer = 1 if rng.random() < 0.9 else 0
        pos, yaw = random_pos(rng), rng.getrandbits(16)
        alpha = C.f32(rng.uniform(0, 1.6))
        scale = C.f32(rng.uniform(0.5, 2))
        offset = C.f32(rng.choice((0.0, rng.uniform(-40, 40))))
        has_model = rng.random() < 0.95
        anim = rng.choice((0, 0x01234560))
        rgba = rng.getrandbits(32)
        arcs = [[rng.randint(0, 35), rng.randint(0, 35), rng.choice((0, rng.getrandbits(32)))]
                for _ in range(3)]
        state = h.blocks[2]
        for i, a in enumerate(arcs):
            e.mem.w16(state + 8 + 8 * i, a[0])
            e.mem.w16(state + 10 + 8 * i, a[1])
            e.mem.w32(state + 12 + 8 * i, a[2])
        h.beam_answer = rng.choice((0, rng.getrandbits(16)))
        seed = rng.getrandbits(32)
        for k in range(3):
            e.mem.w32(h.pos + 4 * k, pos[k])
        e.mem.w32(G_COSMETIC_SEED, seed)
        e.f[12], e.f[13], e.f[14] = alpha, scale, offset
        e.call(ARCS, 0x01230000 if has_model else 0, anim, h.pos, yaw, state, rgba)
        rng_ref = C.Lcg(seed)
        st = R.ArcState(arcs)
        want = R.model_arcs(model if has_model else None, pos, yaw, anim, alpha, scale, offset, st,
                            rgba, rng_ref, near=bool(h.near_answer),
                            beam_create=lambda a, b: h.beam_answer)
        spawns += sum(1 for c in want if c[0] == 'spawn')
        before = failures
        failures = _check(name, h, want, rng_ref.state, failures, examples, case)
        if failures == before and h.near_answer and has_model and model.n:
            got_state = [[C.s16(e.mem.u16(state + 8 + 8 * i)), C.s16(e.mem.u16(state + 10 + 8 * i)),
                          e.mem.u32(state + 12 + 8 * i)] for i in range(3)]
            if got_state != st.arcs:
                failures += 1
                examples.append('case %d: state %r / %r' % (case, got_state, st.arcs))
    h.near_answer = 1
    report(name, failures, count, 'call stream (%d sparks, beam create/update), arc state, seed'
           % spawns, examples)


def prop_model_glow(h):
    name = 'model glow'
    if not wanted(name):
        return
    rng = random.Random('%d/%s' % (OPTIONS['seed'], name))
    count = scaled(2000)
    failures, examples, glows = 0, [], 0
    e = h.emu
    for case in range(count):
        model = _setup(h, rng, rng.choice((0, rng.randint(1, 20))))
        h.near_answer = 1 if rng.random() < 0.9 else 0
        pos, yaw = random_pos(rng), rng.getrandbits(16)
        scale = C.f32(rng.uniform(0.5, 2))
        offset = C.f32(rng.choice((0.0, rng.uniform(-40, 40))))
        fade = C.f32(rng.choice((rng.uniform(0.1, 3), 1.0)))
        mode = rng.choice((0, 1, 2, 3))
        ta = [rng.randint(-300, 300) & 0xFFFF for _ in range(4)]
        tb = [rng.randint(0, 255) for _ in range(4)]
        ramp = R.GlowRamp([C.f32(rng.uniform(-10, 300)) for _ in range(4)],
                          [C.f32(rng.uniform(-10, 300)) for _ in range(4)])
        flags = rng.choice((0x20, 0x21, 0, 0x10))
        has_obj = rng.random() < 0.95
        has_model = rng.random() < 0.95
        size_add = rng.randint(-2000, 2000)
        frame = rng.getrandbits(31)
        anim = rng.choice((0, 0x01234560))
        obj = h.blocks[3]
        e.mem.w32(obj + 0xC, flags)
        for k in range(4):
            e.mem.w32(obj + 0x70 + 4 * k, ramp.a[k])
            e.mem.w32(obj + 0x80 + 4 * k, ramp.b[k])
            e.mem.w16(h.blocks[4] + 2 * k, ta[k])
            e.mem.w16(h.blocks[5] + 2 * k, tb[k])
        for k in range(3):
            e.mem.w32(h.pos + 4 * k, pos[k])
        e.mem.w32(G_SIM_FRAME, frame)
        e.f[12], e.f[13], e.f[14], e.f[15] = C.f32(7.0), scale, offset, fade
        sp = e.stack_hi - 0x200
        e.mem.w32(sp, mode)
        e.mem.w32(sp + 8, size_add & M32)
        e.call(MODEL_GLOW, obj if has_obj else 0, 0x01230000 if has_model else 0, anim, h.pos, yaw,
               0x5A5A5A5A, h.blocks[4], h.blocks[5], sp=sp)
        want = R.model_glow(model if has_model else None, flags if has_obj else None, ramp, pos,
                            yaw, anim, scale, offset, fade, ta, tb, mode, size_add, frame,
                            near=bool(h.near_answer))
        glows += sum(1 for c in want if c[0] == 'glow')
        before = failures
        failures = _check(name, h, want, e.mem.u32(G_COSMETIC_SEED), failures, examples, case)
        if failures == before:
            got = ([e.mem.u32(obj + 0x70 + 4 * k) for k in range(4)],
                   [e.mem.u32(obj + 0x80 + 4 * k) for k in range(4)])
            if got != (ramp.a, ramp.b):
                failures += 1
                examples.append('case %d: ramps %r / %r' % (case, got, (ramp.a, ramp.b)))
    h.near_answer = 1
    report(name, failures, count, 'call stream (%d glows: position, size, colour, texture, angle), '
           'colour ramps' % glows, examples)


class SyntheticWeapon:
    """A weapon model: sample points in model space, put through the caller's matrix the way
    model_transformSamplePoint does (here with mat34_transform_point), a blade segment, the
    attach base byte +0x13."""

    def __init__(self, rng):
        self.n = rng.randint(1, 24)
        self.points = [[C.f32(rng.uniform(-20, 20)) for _ in range(3)] for _ in range(self.n)]
        self.sizes = [C.f32(rng.uniform(0, 3000)) for _ in range(self.n)]
        self.attach_base = rng.randint(0, 255)
        self.segment = ([C.f32(rng.uniform(-5, 5)) for _ in range(3)],
                        [C.f32(rng.uniform(20, 60)) for _ in range(3)])
        self.n_samples = self.n

    def sample_count(self):
        return self.n

    def transform_sample_point(self, matrix, index):
        i = index % self.n
        return C.mat34_transform_point(matrix, self.points[i]), self.sizes[i]

    def effect_segment(self):
        return self.segment


class SyntheticHolder:
    def __init__(self, rng):
        self.base = [C.f32(rng.uniform(-1.2, 1.2)) for _ in range(9)] + \
                    [C.f32(rng.uniform(-60, 60)) for _ in range(3)]

    def attach_matrix(self, scale, anim, index):
        return [C.add(v, C.mul(C.from_int(index & 7), C.f32(0.125))) for v in self.base]


def random_matrix(rng, near=None):
    if near is not None and rng.random() < 0.8:
        return [C.add(v, C.f32(rng.uniform(-0.3, 0.3) if k < 9 else rng.uniform(-25, 25)))
                for k, v in enumerate(near)]
    return [C.f32(rng.uniform(-1.1, 1.1)) for _ in range(9)] + \
           [C.f32(rng.uniform(-3000, 3000)) for _ in range(3)]


def prop_weapon_status(h):
    name = 'weapon status'
    if not wanted(name):
        return
    rng = random.Random('%d/%s' % (OPTIONS['seed'], name))
    count = scaled(3000)
    failures, examples, spawns = 0, [], 0
    e = h.emu
    e.stub(FX_SPAWN, function=lambda m: h.log.append(('fx_spawn', m.r[4] & M32, vec(m, m.r[5]))))
    codes = (R.CODE_LIGHTNING, R.CODE_COLD, R.CODE_FIRE, R.CODE_POISON, R.CODE_DISEASE, 0x10, 0)
    for case in range(count):
        h.begin()
        weapon = SyntheticWeapon(rng)
        holder = SyntheticHolder(rng) if rng.random() < 0.8 else None
        h.weapon, h.holder, h.model = weapon, holder, None
        amount = C.f32(rng.choice((rng.uniform(0, 1.5), 1.0, 0.0, -0.5)))
        scale = C.f32(rng.uniform(0.6, 1.6))
        entries = [(rng.choice(codes), rng.choice((0, 1, 5, -3))) for _ in range(4)]
        item = R.WeaponItem([rng.choice((0, 0, rng.randint(-300, 300))) for _ in range(4)],
                            [rng.choice((0, rng.randint(-300, 300))) for _ in range(4)], entries)
        if rng.random() < 0.3:
            item.glow = [0, 0, 0, 0]
        pos, yaw = random_pos(rng), rng.getrandbits(16)
        swinging = rng.choice((0, 1, 1))
        joint_add = rng.randint(0, 3)
        guess = random_matrix(rng)
        prev = random_matrix(rng, guess)
        if rng.random() < 0.15:
            prev = [C.ONE, 0, 0, 0, C.ONE, 0, 0, 0, C.ONE] + [rng.choice((0, C.ONE)) for _ in range(3)]
        sim_frame = rng.getrandbits(20)
        state = R.WeaponFxState(prev, frame=rng.choice((sim_frame - 1, sim_frame - 3, 0)),
                                beam=rng.choice((0, rng.getrandbits(16))),
                                trail=rng.choice((0, rng.getrandbits(16))),
                                counter=rng.choice((0, rng.randint(0, 100), 100)),
                                spark_kind=rng.randint(0, 4), sparks=rng.choice((0, 0, rng.randint(1, 5))))
        override = random_matrix(rng) if rng.random() < 0.1 else None
        level_flags = rng.choice((0, 0, 0, 0x100, 0x10000000))
        gore = rng.choice((0, 1, 2))
        h.dialog = 1 if rng.random() < 0.03 else 0
        h.answers = {'trail_create': rng.getrandbits(16), 'beam_create': rng.getrandbits(16),
                     'beam_alive': rng.choice((0, 1))}
        has_model = rng.random() < 0.97
        seed = rng.getrandbits(32)
        # memory
        it, st, model_addr, ov, pp = h.blocks[0], h.blocks[1], h.blocks[2], h.blocks[3], h.pos
        for k in range(4):
            e.mem.w16(it + 0x10 + 2 * k, item.glow[k])
            e.mem.w16(it + 0x18 + 2 * k, item.colour2[k])
            e.mem.w16(it + 0x24 + 8 * k, entries[k][0])
            e.mem.w16(it + 0x26 + 8 * k, entries[k][1])
        for k in range(12):
            e.mem.w32(st + 4 * k, prev[k])
            if override:
                e.mem.w32(ov + 4 * k, override[k])
        e.mem.w32(st + 0x30, state.frame)
        e.mem.w32(st + 0x34, state.beam)
        e.mem.w32(st + 0x38, state.trail)
        e.mem.w8(st + 0x3C, state.counter)
        e.mem.w8(st + 0x3D, state.spark_kind)
        e.mem.w8(st + 0x3E, state.sparks)
        e.mem.w8(model_addr + 0x13, weapon.attach_base)
        for k in range(3):
            e.mem.w32(pp + 4 * k, pos[k])
        e.mem.w32(G_COSMETIC_SEED, seed)
        e.mem.w32(G_SIM_FRAME, sim_frame)
        e.mem.w32(G_LEVEL_FLAGS, level_flags)
        e.mem.w32(G_DECAL_DETAIL, gore)
        sp = e.stack_hi - 0x200
        e.mem.w32(sp, joint_add)
        e.mem.w32(sp + 8, ov if override else 0)
        e.f[12], e.f[13] = amount, scale
        try:
            e.call(STATUS_FX, it, model_addr if has_model else 0, st, pp, yaw,
                   0x01400000 if holder else 0, 0x01234560, swinging, sp=sp)
        except EmuError as exc:
            failures += 1
            examples.append('case %d: the original stopped: %s' % (case, exc))
            continue
        cos = C.Lcg(seed)
        want = R.model_status_effects(amount, scale, item, weapon if has_model else None, state,
                                      pos, yaw, holder, 0x01234560, swinging, joint_add, override,
                                      cos, level_flags=level_flags, gore=gore, sim_frame=sim_frame,
                                      dialog_open=bool(h.dialog), answers=h.answers)
        spawns += sum(1 for c in want if c[0] == 'spawn')
        problem = diff_streams(h.log, want)
        if problem is None and e.mem.u32(G_COSMETIC_SEED) != cos.state:
            problem = 'seed'
        if problem is None:
            got_state = ([e.mem.u32(st + 4 * k) for k in range(12)], e.mem.u32(st + 0x30),
                         e.mem.u32(st + 0x34), e.mem.u32(st + 0x38), e.mem.u8(st + 0x3C),
                         e.mem.u8(st + 0x3D), e.mem.u8(st + 0x3E))
            want_state = (state.matrix, state.frame, state.beam, state.trail, state.counter & 0xFF,
                          state.spark_kind & 0xFF, state.sparks & 0xFF)
            if got_state != want_state:
                problem = 'state %r / %r' % (got_state, want_state)
        if problem is None:
            got_item = ([C.s16(e.mem.u16(it + 0x10 + 2 * k)) for k in range(4)],
                        [C.s16(e.mem.u16(it + 0x18 + 2 * k)) for k in range(4)])
            if got_item != (item.glow, item.colour2):
                problem = 'item colours %r / %r' % (got_item, (item.glow, item.colour2))
        if problem:
            failures += 1
            examples.append('case %d: %s' % (case, problem))
    e.unhook(FX_SPAWN)
    h.weapon = None
    h.answers = {}
    report(name, failures, count, 'call stream (%d particle_spawn calls; trail, beam, glow, fx_spawn, '
           'matrix queries), state block, item colours, seed' % spawns, examples)


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
    prop_lose_part(h)
    prop_emit_from_verts(h)
    prop_sparkle(h)
    prop_arcs(h)
    prop_model_glow(h)
    prop_weapon_status(h)
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d failed, %.0f s' % (len(RESULTS), len(failed), time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
