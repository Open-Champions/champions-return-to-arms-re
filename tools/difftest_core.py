#!/usr/bin/env python3
"""difftest_core.py - compare tools/ref_core.py with the game's own machine code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_core.py [path/to/SLUS_209.73] [--quick] [--seed N] [-k TEXT] [-v]

    --quick   a tenth of the random samples (the exhaustive angle sweeps stay complete)
    --seed N  seed of the random inputs (default 20973); runs with one seed repeat exactly
    -k TEXT   run only the properties whose name contains TEXT
    -v        print up to three failing inputs per property

Every property prints one line: PASS or FAIL, the name, the number of cases compared and
what was compared.  Exit status 1 when any property fails.

How a property is tested
    The ORIGINAL function is executed by tools/ee_emu.py (an instruction interpreter, not a
    console) on inputs this script writes into the interpreter's memory; the same inputs
    go through the model; every output word must be equal.  Floating-point results are
    compared as 32-bit patterns, so "bit for bit" below means: identical under the
    interpreter's floating-point model.  The interpreter's default model ('ps2') gets the
    full sample; each property is then repeated on a smaller sample under the three other
    adder models and with the multiplier-bias and divide-rounding switches, with the model
    switched the same way.  Agreement under all six shows that the model performs the same
    operations in the same order; it does NOT show that either matches a real console in
    the last bit (docs/issues/dynamic-tests.md, "Floating point").

Inputs are a seeded mix: values of the size the game uses, random bit patterns (which
reach the overflow, underflow and exponent-255 paths), and a list of edge patterns.
"""
import hashlib
import os
import random
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError, M32            # noqa: E402
import ref_core as R                            # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (adder model, multiplier bias, divide to nearest): the first gets the full sample
FPU_CONFIGS = (('ps2', False, False), ('ps2g1', False, False), ('chop', False, False),
               ('nearest', False, False), ('ps2', True, False), ('ps2', False, True))

OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False}
RESULTS = []


def wanted(name):
    return OPTIONS['filter'] is None or OPTIONS['filter'].lower() in name.lower()


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-34s %7d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:3]:
            print('        ' + line)
    sys.stdout.flush()


def scaled(count):
    return max(count // 10, 20) if OPTIONS['quick'] else count


# ---------------------------------------------------------------------------------------
# Input generation
# ---------------------------------------------------------------------------------------
EDGE = [0x00000000, 0x80000000, 0x3F800000, 0xBF800000, 0x3F000000, 0x40000000, 0x7FFFFFFF,
        0xFFFFFFFF, 0x00800000, 0x80800000, 0x00000001, 0x007FFFFF, 0x7F800000, 0xFF800000,
        0x7FC00000, 0x3F7FFFFF, 0x3F800001, 0x4B000000, 0x4B800000, 0x4F000000, 0xCF000000,
        0x4EFFFFFF, 0x33800000, 0x38D1B717, 0x3A83126E, 0x3C23D70A, 0x40490FDA, 0x3FC90FDA]


def raw_uniform(rng, low, high):
    return R.f32(rng.uniform(low, high))


def gen_float(rng, profile):
    """One float pattern.  profile is the size of value the function normally sees."""
    roll = rng.random()
    if roll < 0.06:
        return rng.choice(EDGE)
    if roll < 0.22:
        return rng.getrandbits(32)                      # any pattern at all
    if profile == 'unit':
        return raw_uniform(rng, -1.0, 1.0)
    if profile == 'small':
        return raw_uniform(rng, -4.0, 4.0)
    if profile == 'world':
        return raw_uniform(rng, -4000.0, 4000.0)
    if profile == 'frac':
        return raw_uniform(rng, 0.0, 1.0)
    if profile == 'mixed':
        return R.f32(rng.uniform(-1.0, 1.0) * 10.0 ** rng.randrange(-6, 7))
    raise ValueError(profile)


def gen_angle(rng):
    """A 16-bit angle, sometimes with junk above bit 15 (the code must ignore it)."""
    value = rng.randrange(0x10000)
    roll = rng.random()
    if roll < 0.1:
        value = rng.choice((0, 1, 0x3FFF, 0x4000, 0x4001, 0x7FFF, 0x8000, 0x8001, 0xBFFF,
                            0xC000, 0xC001, 0xFFFF))
    if roll > 0.8:
        value |= rng.getrandbits(16) << 16
    return value


def gen_axis(rng):
    return rng.choice((0, 1, 2, 0, 1, 2, 0, 1, 2, 3, -1, 7))


# ---------------------------------------------------------------------------------------
# Running the original
# ---------------------------------------------------------------------------------------
class Rig:
    """One interpreter with a handful of scratch buffers for pointer arguments."""

    def __init__(self, elf, config=FPU_CONFIGS[0]):
        model, bias, nearest = config
        emu = self.emu = EE(elf, fpu_model=model)
        emu.fpu_mul_bias = bias
        emu.fpu_div_nearest = nearest
        emu.record_calls = False
        emu.record_writes = False
        self.sp = emu.r[29]
        self.buffers = [emu.alloc(0x60) for _ in range(8)]
        R.set_fpu(model, bias, nearest)

    def call(self, addr, ints=(), floats=(), max_steps=400000):
        emu = self.emu
        emu.r[29] = self.sp
        for index, raw in enumerate(floats):
            emu.f[12 + index] = raw & M32
        value = emu.call(addr, *ints, max_steps=max_steps)
        return value, emu.f[0]

    def put(self, addr, words):
        self.emu.mem.write(addr, struct.pack('<%dI' % len(words), *[w & M32 for w in words]))

    def get(self, addr, count):
        return list(struct.unpack('<%dI' % count, self.emu.mem.read(addr, count * 4)))


def hexlist(words):
    return '[' + ' '.join('%08x' % (w & M32) for w in words) + ']'


# ---------------------------------------------------------------------------------------
# The table of straight-line math functions
#
# args: ('f', profile)            float in the next of f12..
#       ('in', n, profile)        pointer to n floats, read only
#       ('io', n, profile)        pointer to n floats, read and written
#       ('out', n)                pointer to n floats, written (pre-filled with junk)
#       ('angle',) ('axis',)      integer argument
# ret:  'f0' float result, 's32' / 'u32' integer result, None
# model(*inputs) -> (list of expected contents of each io/out buffer in order, result)
#       an expected buffer of None means "must be left untouched"
# alias: pairs of argument positions that may be the same buffer in the original
# ---------------------------------------------------------------------------------------
def one(fn):
    return lambda *a: ([fn(*a)], None)


def ret(fn):
    return lambda *a: ([], fn(*a))


V3 = ('in', 3, 'world')
U3 = ('in', 3, 'unit')
M3 = ('in', 9, 'unit')
M34 = ('in', 12, 'small')
M4 = ('in', 16, 'small')
Q = ('in', 4, 'unit')
ANGLE = ('angle',)

CASES = [
    # name, address, args, ret, model, sample size, alias
    ('math_hermite', 0x1658F0, [('f', 'frac'), ('f', 'world'), ('f', 'world'), ('f', 'small'), ('f', 'small')],
     'f0', ret(R.hermite), 3000, ()),
    ('vec3_hermite', 0x162310, [('f', 'frac'), V3, V3, V3, V3, ('out', 3)], None,
     one(R.vec3_hermite), 2000, ((5, 1), (5, 4))),
    ('vec3_hermite_derivative', 0x162440, [('f', 'frac'), V3, V3, V3, V3, ('out', 3)], None,
     one(R.vec3_hermite_derivative), 1000, ()),
    ('vec3_dotDelta', 0x1667D8, [V3, U3, V3], 'f0', ret(R.vec3_dot_delta), 3000, ()),
    ('vec2_dotDelta', 0x166820, [('in', 2, 'world'), ('in', 2, 'unit'), ('in', 2, 'world')], 'f0',
     ret(R.vec2_dot_delta), 3000, ()),
    ('ray_plane_distance', 0x163658, [V3, U3, V3, U3], 'f0', ret(R.ray_plane_distance), 4000, ()),
    ('segment_hits_plane_near_edge', 0x163790, [V3, V3, U3, V3, V3, ('out', 3)], 's32',
     lambda a, b, n, p1, p0: (lambda r: ([r[1]], r[0]))(R.segment_hits_plane_near_edge(a, b, n, p1, p0)),
     4000, ()),
    ('bbox_setEmpty', 0x166EC0, [('out', 6)], None, one(R.bbox_set_empty), 20, ()),
    ('bbox_union', 0x166CC0, [('io', 6, 'world'), ('in', 6, 'world')], None, one(R.bbox_union), 2000, ()),
    ('bbox_addPoint', 0x166D40, [('io', 6, 'world'), V3], None, one(R.bbox_add_point), 1000, ()),
    ('bbox_containsPoint', 0x166DC0, [('in', 6, 'world'), V3], 's32', ret(R.bbox_contains_point), 2000, ()),
    ('bbox_overlaps', 0x166E38, [('in', 6, 'world'), ('in', 6, 'world')], 's32', ret(R.bbox_overlaps), 2000, ()),

    ('mat3_setIdentity', 0x165650, [('out', 9)], None, one(R.mat3_set_identity), 20, ()),
    ('mat34_setIdentity', 0x165680, [('out', 12)], None, one(R.mat34_set_identity), 20, ()),
    ('mat34_setTranslation', 0x166850, [('out', 12), V3], None, one(R.mat34_set_translation), 300, ()),
    ('mat3_mul', 0x165710, [('out', 9), M3, M3], None, one(R.mat3_mul), 2000, ((0, 1), (0, 2))),
    ('mat34_mulMat3', 0x162580, [('out', 12), M3, M34], None, one(R.mat34_mul_mat3), 1500, ((0, 2),)),
    ('mat34_mul', 0x162808, [('out', 12), M34, M34], None, one(R.mat34_mul), 2000, ((0, 1), (0, 2))),
    ('mat4_mulMat34', 0x162698, [('out', 16), M34, M4], None, one(R.mat4_mul_mat34), 1500, ((0, 2),)),
    ('mat4_mul', 0x1657E0, [('out', 16), M4, M4], None, one(R.mat4_mul), 1000, ((0, 1), (0, 2))),
    ('mat3_rotateAxis', 0x162960, [('io', 9, 'unit'), ('axis',), ANGLE], None,
     one(R.mat3_rotate_axis), 2500, ()),
    ('mat34_rotateAxis', 0x163000, [('io', 12, 'small'), ('axis',), ANGLE], None,
     one(R.mat34_rotate_axis), 2500, ()),
    ('mat4_rotateAxis', 0x163208, [('io', 16, 'small'), ('axis',), ANGLE], None,
     one(R.mat4_rotate_axis), 1000, ()),
    ('mat3_rotateAxisPost', 0x162DF0, [('io', 9, 'unit'), ('axis',), ANGLE], None,
     one(R.mat3_rotate_axis_post), 2000, ()),
    ('mat34_rotateAxisPost', 0x162B68, [('io', 12, 'small'), ('axis',), ANGLE], None,
     one(R.mat34_rotate_axis_post), 1000, ()),
    ('mat3_setRotZ', 0x1639D8, [('out', 9), ANGLE], None, one(R.mat3_set_rot_z), 4096, ()),
    ('mat34_setPosRotZ', 0x163B30, [('out', 12), V3, ANGLE], None, one(R.mat34_set_pos_rot_z), 4096, ((0, 1),)),
    ('mat34_setPosRotZScale', 0x163CB8, [('f', 'small'), ('out', 12), V3, ANGLE], None,
     one(R.mat34_set_pos_rot_z_scale), 4096, ((1, 2),)),
    ('mat34_setPosEulerScale', 0x163E48, [('f', 'small'), ('out', 12), V3, ANGLE, ANGLE, ANGLE], None,
     one(R.mat34_set_pos_euler_scale), 1500, ((1, 2),)),
    ('mat4_invert', 0x163F98, [('out', 16), M4], None, one(R.mat4_invert), 1200, ((0, 1),)),
    ('mat34_invert', 0x164288, [('out', 12), M34], None, one(R.mat34_invert), 1200, ((0, 1),)),
    ('mat3_transpose', 0x166298, [('out', 9), M3], None, one(R.mat3_transpose), 500, ((0, 1),)),
    ('mat3_scale', 0x165CC0, [('f', 'small'), ('io', 9, 'unit')], None, one(R.mat3_scale), 1500, ()),
    ('mat3_scaleXYZ', 0x165D30, [('f', 'small'), ('f', 'small'), ('f', 'small'), ('io', 9, 'unit')], None,
     one(R.mat3_scale_xyz), 1500, ()),
    ('mat4_scaleRotation', 0x165B98, [('f', 'small'), ('io', 16, 'small')], None,
     one(R.mat4_scale_rotation), 1000, ()),
    ('mat34_translateLocal', 0x165B10, [('f', 'world'), ('f', 'world'), ('f', 'world'), ('io', 12, 'small')],
     None, one(R.mat34_translate_local), 2000, ()),
    ('mat4_translateLocal', 0x165C08, [('f', 'world'), ('f', 'world'), ('f', 'world'), ('io', 16, 'small')],
     None, one(R.mat4_translate_local), 1000, ()),
    ('mat3_mulVec', 0x165E40, [('out', 3), M3, V3], None, one(R.mat3_mul_vec), 2500, ((0, 2),)),
    ('mat34_rotateVec', 0x166158, [('out', 3), M34, V3], None, one(R.mat34_rotate_vec), 2500, ((0, 2),)),
    ('mat3_mulVecTransposed', 0x165DA0, [('out', 3), M3, V3], None, one(R.mat3_mul_vec_transposed), 2500,
     ((0, 2),)),
    ('mat3_mulVecTransposed2', 0x1661F8, [('out', 3), M3, V3], None, one(R.mat3_mul_vec_transposed), 1500,
     ((0, 2),)),
    ('mat34_transformPoint', 0x1660A0, [('out', 3), M34, V3], None, one(R.mat34_transform_point), 3000,
     ((0, 2),)),
    ('mat4_transformPoint', 0x165EE0, [('out', 3), M4, V3], 'f0',
     lambda m, v: (lambda r: ([r[0]], r[1]))(R.mat4_transform_point(m, v)), 2000, ((0, 2),)),
    ('mat4_transformPointTransposed', 0x165FC0, [('out', 3), M4, V3], 'f0',
     lambda m, v: (lambda r: ([r[0]], r[1]))(R.mat4_transform_point_transposed(m, v)), 1500, ((0, 2),)),
    ('mat4_setProjection', 0x165950, [('f', 'small')] * 3 + [('f', 'frac')] * 2 + [('f', 'world')] * 2
     + [('out', 16)], None, one(R.mat4_set_projection), 1500, ()),
    ('mat4_setProjectionFixed', 0x1659D0, [('f', 'small')] * 3 + [('f', 'frac')] * 2 + [('f', 'world')] * 2
     + [('out', 16)], None, one(R.mat4_set_projection_fixed), 1000, ()),
    ('mat4_setProjectionFixed2', 0x165A70, [('f', 'small')] * 3 + [('f', 'frac')] * 2 + [('f', 'world')] * 2
     + [('out', 16)], None, one(R.mat4_set_projection_fixed), 1000, ()),
    ('mat4_fromMat3Pos', 0x166340, [('out', 16), M3, V3], None, one(R.mat4_from_mat3_pos), 300, ()),

    ('quat_fromAxisAngle', 0x1663C0, [('f', 'unit'), ('f', 'unit'), ('f', 'unit'), ('out', 4), ANGLE], None,
     one(R.quat_from_axis_angle), 2500, ()),
    ('quat_mul', 0x166480, [('out', 4), Q, Q], None, one(R.quat_mul), 2500, ((0, 1), (0, 2))),
    ('quat_normalize', 0x166550, [('io', 4, 'small')], None, one(R.quat_normalize), 2500, ()),
    ('quat_rotateVec', 0x163490, [('out', 3), Q, V3], None, one(R.quat_rotate_vec), 2500, ((0, 2),)),
    ('quat_fromMat3', 0x164330, [('out', 4), M3], None, one(R.quat_from_mat3), 4000, ()),
    ('mat3_fromQuat', 0x1668B8, [('out', 9), Q], None, one(R.mat3_from_quat), 2500, ()),
    ('mat34_fromQuat', 0x166988, [('out', 12), Q], None, one(R.mat34_from_quat), 1500, ()),
    ('mat4_fromQuat', 0x166A68, [('io', 16, 'small'), Q], None, one(lambda old, q: R.mat4_from_quat(q, old)),
     1000, ()),

    ('libm_fabsf', 0x3AA7E8, [('f', 'mixed')], 'f0', ret(R.fabs), 500, ()),
    ('libm_atanf', 0x3AA558, [('f', 'mixed')], 'f0', ret(R.atanf), 6000, ()),
    ('libm_atan2f', 0x3A5A80, [('f', 'mixed'), ('f', 'mixed')], 'f0', ret(R.atan2f), 6000, ()),
    ('libm_floorf', 0x3A57E8, [('f', 'mixed')], 'f0', ret(R.floorf), 5000, ()),
    ('libm_ceilf', 0x3A5710, [('f', 'mixed')], 'f0', ret(R.ceilf), 5000, ()),
    ('color_fromHSV', 0x164F10, [('f', 'frac'), ('f', 'frac'), ('f', 'frac')], 'u32',
     ret(R.color_from_hsv), 3000, ()),
]


def build_inputs(rng, rig, args, alias_pair=None, preset=None):
    """Lay out one call.  Returns (ints, floats, model inputs, [(addr, n, prefill)] of the
    buffers to check afterwards, in argument order).  alias_pair = (output position,
    input position) makes those two arguments the same buffer.  preset gives the argument
    values instead of drawing them (None for an output)."""
    values = []
    for arg in ([] if preset is not None else args):
        kind = arg[0]
        if kind == 'f':
            values.append(gen_float(rng, arg[1]))
        elif kind == 'angle':
            values.append(gen_angle(rng))
        elif kind == 'axis':
            values.append(gen_axis(rng))
        elif kind in ('in', 'io'):
            values.append([gen_float(rng, arg[2]) for _ in range(arg[1])])
        else:
            values.append(None)
    # ties: now and then make elements equal (or equal in magnitude), which random draws
    # never do - the cases that tell "less" from "less or equal"
    if preset is not None:
        values = [list(v) if isinstance(v, (list, tuple)) else v for v in preset]
    lists = [v for v in values if isinstance(v, list)]
    if preset is None and lists and rng.random() < 0.25:
        for _ in range(rng.randrange(1, 5)):
            source, target = rng.choice(lists), rng.choice(lists)
            i = rng.randrange(len(source))
            j = i if i < len(target) and rng.random() < 0.6 else rng.randrange(len(target))
            target[j] = source[i] ^ (0x80000000 if rng.random() < 0.2 else 0)
    addr_of = {}
    slot = 0
    for position, arg in enumerate(args):
        if arg[0] in ('in', 'io', 'out'):
            addr_of[position] = rig.buffers[slot]
            slot += 1
    if alias_pair:
        addr_of[alias_pair[0]] = addr_of[alias_pair[1]]
    ints, floats, inputs, checks = [], [], [], []
    for position, arg in enumerate(args):
        kind = arg[0]
        if kind == 'f':
            floats.append(values[position])
            inputs.append(values[position])
        elif kind in ('angle', 'axis'):
            ints.append(values[position])
            inputs.append(values[position])
        elif kind == 'out':
            addr, count = addr_of[position], arg[1]
            ints.append(addr)
            if alias_pair and position == alias_pair[0]:
                shared = list(values[alias_pair[1]])
                size = max(count, len(shared))
                rig.put(addr, (shared + [0] * size)[:size])
                prefill = (shared + [0] * count)[:count]
            else:
                prefill = [rng.getrandbits(32) for _ in range(count)]
                rig.put(addr, prefill)
            checks.append((addr, count, prefill))
        else:
            addr, count = addr_of[position], arg[1]
            ints.append(addr)
            if not (alias_pair and position == alias_pair[1]):
                rig.put(addr, values[position])
            inputs.append(values[position])
            if kind == 'io':
                checks.append((addr, count, values[position]))
    return ints, floats, inputs, checks


def run_case(elf, case, config, count, seed, alias_pair=None, presets=None):
    name, addr, args, ret_kind, model, _size, _alias = case
    rig = Rig(elf, config)
    rng = random.Random('%s/%s/%s/%s' % (seed, name, config, alias_pair))
    failures, examples = 0, []
    for index in range(count if presets is None else len(presets)):
        ints, floats, inputs, checks = build_inputs(rng, rig, args, alias_pair,
                                                    None if presets is None else presets[index])
        try:
            value, f0 = rig.call(addr, ints, floats)
        except EmuError as exc:
            failures += 1
            examples.append('interpreter stopped: %s' % exc)
            continue
        got_buffers = [rig.get(a, n) for a, n, _p in checks]
        want_buffers, want_ret = model(*inputs)
        want_buffers = [prefill if want is None else [w & M32 for w in want]
                        for want, (_a, _n, prefill) in zip(want_buffers, checks)]
        if ret_kind == 'f0':
            got_ret = f0
            want_ret &= M32
        elif ret_kind in ('s32', 'u32'):
            got_ret = value & M32
            want_ret &= M32
        else:
            got_ret = want_ret = None
        if got_buffers != want_buffers or got_ret != want_ret:
            failures += 1
            if len(examples) < 3:
                examples.append('in %s -> original %s %s, model %s %s' % (
                    ' '.join(hexlist(x) if isinstance(x, list) else '%x' % (x & M32) for x in inputs),
                    ' '.join(hexlist(b) for b in got_buffers), got_ret if got_ret is None else '%08x' % got_ret,
                    ' '.join(hexlist(b) for b in want_buffers), want_ret if want_ret is None else '%08x' % want_ret))
    return failures, examples


def test_math_table(elf):
    for case in CASES:
        name, addr, _args, _ret, _model, size, alias = case
        label = 'math.%s' % name
        if not wanted(label):
            continue
        total = failures = 0
        examples = []
        size = scaled(size)
        for index, config in enumerate(FPU_CONFIGS):
            count = size if index == 0 else max(size // 10, 10)
            bad, ex = run_case(elf, case, config, count, OPTIONS['seed'])
            total += count
            failures += bad
            examples += ['%s: %s' % (config, line) for line in ex]
        alias_text = ''
        for pair in alias:
            count = max(size // 5, 10)
            bad, ex = run_case(elf, case, FPU_CONFIGS[0], count, OPTIONS['seed'], pair)
            total += count
            failures += bad
            examples += ['alias %s: %s' % (pair, line) for line in ex]
        if alias:
            alias_text = '; output may overlap argument%s %s' % (
                's' if len(alias) > 1 else '', ', '.join(str(p[1]) for p in alias))
        report(label, failures, total, '0x%06x bit for bit under all six FPU settings%s' % (addr, alias_text),
               examples)
    R.set_fpu()


def around(raw, spread=1):
    """A pattern and its neighbours, with both signs."""
    out = []
    for delta in range(-spread, spread + 1):
        out += [(raw + delta) & M32, ((raw + delta) ^ 0x80000000) & M32]
    return out


def threshold_presets():
    """Hand-built inputs that sit exactly on, and one unit either side of, every constant a
    function compares against - the cases random input does not reach."""
    F = R.f32
    one, zero = R.ONE, 0
    presets = {}

    rows = []
    for pivot in around(R.K_SINGULAR) + [0, 0x80000000, 1, 0x007FFFFF]:
        for c in range(4):
            m = [one if i % 5 == 0 else zero for i in range(16)]
            m[5 * c] = pivot
            rows.append([None, m])
            m = list(m)
            m[4 * c + (c + 1) % 4] = pivot ^ 0x80000000        # an equal-magnitude rival in the row
            rows.append([None, m])
    presets['mat4_invert'] = rows
    rows = []
    for pivot in around(R.K_SINGULAR) + [0]:
        for c in range(3):
            m = [one, 0, 0, 0, one, 0, 0, 0, one, F(3.0), F(-2.0), F(5.0)]
            m[4 * c] = pivot
            rows.append([None, m])
    presets['mat34_invert'] = rows

    rows = []
    for d in around(R.K_0_001, 2) + [0, 0x80000000, F(1.0)]:
        for h in (one, F(2.0), 0, 0x80000000, F(-1.0), 1):
            rows.append([[h, 0, 0], [d ^ 0x80000000, 0, 0], [0, 0, 0], [one, 0, 0]])
    # heights other than a power of two whose product with the direction lands exactly on
    # the 0.001 limit: there the two formulas of the function give different bits
    for h in (F(3.0), F(5.0), F(7.0), F(1.7), F(0.3), F(11.0), F(0.013)):
        guess = R.div(R.K_0_001, h)
        for d in range(guess - 6, guess + 7):
            if abs(R.s32(R.mul(h, d)) - R.K_0_001) <= 1:
                rows.append([[h, 0, 0], [d ^ 0x80000000, 0, 0], [0, 0, 0], [one, 0, 0]])
    presets['ray_plane_distance'] = rows

    rows = []
    for d in around(R.K_0_01, 2) + [F(1.0), F(4.0), 0, 1]:
        for ax in (0, F(-0.5), F(-1.0), F(-1.0) + 1, F(-1.0) - 1, 1, 0x80000001):
            for py in around(R.QUARTER) + around(F(2.25)) + [0, F(1.0)]:
                p0 = [0, py, 0]
                p1 = [(d ^ 0x80000000) & M32, py, 0]
                a = [R.mul(ax, d) if ax not in (1, 0x80000001) else ax, F(2.0), 0]
                b = [a[0], 0, 0]
                rows.append([a, b, [one, 0, 0], p1, p0, None])
    presets['segment_hits_plane_near_edge'] = rows

    rows = []
    hues = [0, 0x80000000, one, one + 1, one - 1, F(-0.1), F(1.5)]
    for k in range(1, 6):
        hues += around(F(k / 6.0), 3)[::2]
    for h in hues:
        for sat in (0, 0x80000000, 1, one, one + 1, F(0.5), F(-0.5)):
            for v in (0, one, one + 1, one - 1, F(0.5), F(-1.0)):
                rows.append([h, sat, v])
    presets['color_fromHSV'] = rows

    rows = []
    for trace in (0, 0x80000000, 1, 0x80000001, 0x00800000, 0x80800000, F(1e-6), F(-1e-6)):
        m = [trace, F(0.3), F(-0.2), F(0.1), 0, F(0.4), F(0.7), F(-0.6), 0]
        rows.append([None, m])
        for a, b, c in ((0, 0, 0), (F(-1.0), F(-1.0), F(-1.0)), (F(-1.0), F(-1.0), F(2.0)),
                        (F(0.5), F(0.5), F(-1.0)), (F(-2.0), F(0.5), F(0.5))):
            m = list(m)
            m[0], m[4], m[8] = a, b, c
            rows.append([None, m])
    presets['quat_fromMat3'] = rows

    box = [F(-1.0), F(-2.0), F(-3.0), F(1.0), F(2.0), F(3.0)]
    presets['bbox_union'] = [[box, box], [box, [x ^ 0x80000000 for x in box]], [box, [0] * 6],
                             [[0] * 6, [0x80000000] * 6]]
    rows = []
    for axis in range(3):
        for value in around(box[axis]) + around(box[3 + axis]):
            point = [0, 0, 0]
            point[axis] = value
            rows.append([box, point])
    presets['bbox_containsPoint'] = rows
    zeros, minus_zeros = [0] * 6, [0x80000000] * 6      # +0 against -0: equal, but different bits
    presets['bbox_addPoint'] = rows + [[zeros, minus_zeros[:3]], [minus_zeros, zeros[:3]]]
    presets['bbox_union'] += [[zeros, minus_zeros], [minus_zeros, zeros]]
    rows = []
    for axis in range(3):
        for value in around(box[3 + axis]):
            other = [F(-9.0), F(-9.0), F(-9.0), F(9.0), F(9.0), F(9.0)]
            other[axis] = value                         # other.min against box.max
            rows.append([box, other])
            rows.append([other, box])
    presets['bbox_overlaps'] = rows

    atan_marks = [0x31000000, 0x3EE00000, 0x3F300000, 0x3F980000, 0x401C0000, 0x50800000, 0x00800000, 0]
    presets['libm_atanf'] = [[v] for mark in atan_marks for v in around(mark, 2)]
    rows = [[y, x] for y in (0, 0x80000000, 1, 0x007FFFFF, 0x80000001, 0x00800000, one, F(-1.0))
            for x in (0, 0x80000000, 1, 0x007FFFFF, 0x00800000, one, one + 1, one - 1, F(-1.0), F(2.0), F(-2.0))]
    for gap in (59, 60, 61, 62, -59, -60, -61, -62):
        for x in (F(1.5), F(-1.5), F(3.0)):
            y = R.scalbnf(x, gap)
            rows += [[y, x], [y ^ 0x80000000, x], [y + 1, x], [y - 1, x]]
    presets['libm_atan2f'] = rows
    whole = []
    for value in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 7.0, 255.0, 256.0, 1023.5, 4096.0, 8388607.0, 8388607.5,
                  8388608.0, 16777216.0, 1e9):
        whole += around(F(value))
    whole += [0x00800000, 0x80800000, 1, 0x80000001, 0x3F7FFFFF, 0xBF7FFFFF, 0x7FFFFFFF, 0xFFFFFFFF]
    presets['libm_floorf'] = [[v] for v in whole]
    presets['libm_ceilf'] = [[v] for v in whole]
    return presets


def test_thresholds(elf):
    presets = threshold_presets()
    by_name = {case[0]: case for case in CASES}
    for name in sorted(presets):
        label = 'edge.%s' % name
        if not wanted(label):
            continue
        failures, total, examples = 0, 0, []
        for config in FPU_CONFIGS:
            bad, ex = run_case(elf, by_name[name], config, 0, OPTIONS['seed'], None, presets[name])
            failures += bad
            total += len(presets[name])
            examples += ['%s: %s' % (config, line) for line in ex]
        report(label, failures, total, 'inputs built to sit on and one unit either side of each constant '
               'the function compares with, and on equal values', examples)
    R.set_fpu()


# ---------------------------------------------------------------------------------------
# Properties that need their own driver
# ---------------------------------------------------------------------------------------
def test_fpu_primitives():
    """ref_core's arithmetic against the interpreter's, operation by operation."""
    name = 'fpu.primitives'
    if not wanted(name):
        return
    rng = random.Random('%s/fpu' % OPTIONS['seed'])
    count = scaled(40000)
    failures, total, examples = 0, 0, []

    def near(a):
        """A second operand close to the first in size: sums then cancel or carry."""
        exp = ((a >> 23) & 0xFF) + rng.randrange(-30, 31)
        return (rng.getrandbits(1) << 31) | (max(0, min(255, exp)) << 23) | rng.getrandbits(23)

    for model, bias, nearest in FPU_CONFIGS:
        fpu = R.Fpu(model, bias, nearest)
        for index in range(count // len(FPU_CONFIGS)):
            a = rng.choice(EDGE) if index % 17 == 0 else rng.getrandbits(32)
            b = rng.choice(EDGE) if index % 19 == 0 else (near(a) if index % 2 else rng.getrandbits(32))
            pairs = (
                ('add', fpu.add(a, b), ee_emu.fp_add(a, b, model)),
                ('sub', fpu.sub(a, b), ee_emu.fp_sub(a, b, model)),
                ('mul', fpu.mul(a, b), ee_emu.fp_mul(a, b, model, None, bias)),
                ('div', fpu.div(a, b), ee_emu.fp_div(a, b, model, None, nearest)),
                ('sqrt', fpu.sqrt(a), ee_emu.fp_sqrt(a, model, None, nearest)),
                ('rsqrt', fpu.rsqrt(a, b), ee_emu.fp_rsqrt(a, b, model, None, nearest)),
                ('to_int', fpu.to_int(a) & M32, ee_emu.fp_to_int(a)),
                ('from_int', fpu.from_int(a), ee_emu.fp_from_int(a, model)),
                ('compare', fpu.compare(a, b), ee_emu.fp_cmp(a, b)),
            )
            for op, mine, theirs in pairs:
                total += 1
                if mine != theirs:
                    failures += 1
                    if len(examples) < 3:
                        examples.append('%s %s(%08x, %08x): model %x, interpreter %x' % (model, op, a, b, mine, theirs))
    # max.s and min.s have no helper in the interpreter: run the two instructions themselves
    emu = EE()
    emu.load_words(0x00200000, [0x460D6028, 0x03E00008, 0, 0x460D6029, 0x03E00008, 0])
    for index in range(scaled(4000)):
        a = rng.choice(EDGE) if index % 5 == 0 else rng.getrandbits(32)
        b = rng.choice((a, a ^ 0x80000000, rng.choice(EDGE), rng.getrandbits(32)))
        for addr, mine in ((0x00200000, R.fmax(a, b)), (0x0020000C, R.fmin(a, b))):
            emu.f[12], emu.f[13] = a, b
            emu.call(addr)
            total += 1
            if emu.f[0] != mine:
                failures += 1
                if len(examples) < 3:
                    examples.append('max/min(%08x, %08x): model %x, interpreter %x' % (a, b, mine, emu.f[0]))
    report(name, failures, total, 'add sub mul div sqrt rsqrt to_int from_int compare max min equal to '
           'tools/ee_emu.py under all six FPU settings', examples)


def test_const_rule(elf):
    """The C library's coefficient tables equal fdlibm's decimal constants truncated."""
    name = 'libm.tables'
    if not wanted(name):
        return
    emu = EE(elf)
    tables = ((0x562058, R.ATAN_HI, 'atanhi'), (0x562068, R.ATAN_LO, 'atanlo'), (0x562078, R.ATAN_T, 'aT'))
    tables += tuple(R.LIBM_TABLES)
    failures, total, examples, off_by_rounding = 0, 0, [], 0
    for base, values, label in tables:
        for index, value in enumerate(values):
            total += 1
            word = emu.mem.u32(base + 4 * index)
            if word != value:
                failures += 1
                examples.append('%s[%d] at 0x%x: executable %08x, model %08x' % (label, index, base + 4 * index, word, value))
    for text in R.LIBM_DECIMALS:
        if R.f32(float(text)) != R.const(text):
            off_by_rounding += 1
    report(name, failures, total, 'coefficient words in the executable equal the published decimal '
           'constants TRUNCATED to 24 bits (%d of %d would differ if rounded to nearest)'
           % (off_by_rounding, len(R.LIBM_DECIMALS)), examples)


def test_angles(elf):
    for name, addr, model in (('cos16', 0x166630, R.cos16), ('sin16', 0x1666E0, R.sin16)):
        label = 'angle.%s' % name
        if not wanted(label):
            continue
        failures, total, examples = 0, 0, []
        for index, config in enumerate(FPU_CONFIGS):
            rig = Rig(elf, config)
            if index == 0:
                angles = list(range(0x10000))                       # every 16-bit input
                angles += [a | 0xABCD0000 for a in range(0, 0x10000, 257)]     # junk above bit 15
                angles += [a - 0x10000 for a in range(0x8000, 0x10000, 263)]   # sign-extended
            else:
                angles = range(0, 0x10000, 1 if not OPTIONS['quick'] and index == 1 else 37)
            for angle in angles:
                _value, f0 = rig.call(addr, [angle])
                want = model(angle)
                total += 1
                if f0 != want:
                    failures += 1
                    if len(examples) < 3:
                        examples.append('%s angle %x: original %08x model %08x' % (config, angle, f0, want))
        report(label, failures, total, '0x%06x: all 65,536 angles bit for bit (default FPU model and '
               'ps2g1 in full, the other four on every 37th angle); junk above bit 15 ignored' % addr, examples)
    R.set_fpu()

    label = 'angle.atan2_16'
    if wanted(label):
        failures, total, examples = 0, 0, []
        rng = random.Random('%s/atan2' % OPTIONS['seed'])
        for index, config in enumerate(FPU_CONFIGS):
            rig = Rig(elf, config)
            pairs = []
            if index == 0:
                span = 12 if OPTIONS['quick'] else 48
                for dy in range(-span, span + 1):
                    for dx in range(-span, span + 1):
                        pairs.append((R.f32(float(dy)), R.f32(float(dx))))
                pairs += [(a, b) for a in EDGE for b in EDGE]
            for _ in range(scaled(6000) if index == 0 else scaled(600)):
                kind = rng.randrange(4)
                if kind == 0:
                    pairs.append((raw_uniform(rng, -3000, 3000), raw_uniform(rng, -3000, 3000)))
                elif kind == 1:
                    pairs.append((raw_uniform(rng, -1, 1), raw_uniform(rng, -1, 1)))
                elif kind == 2:
                    pairs.append((gen_float(rng, 'mixed'), gen_float(rng, 'mixed')))
                else:                                   # near the axes and diagonals
                    base = raw_uniform(rng, -500, 500)
                    other = rng.choice((0, 0x80000000, base, base ^ 0x80000000, base + 1, base - 1))
                    pairs.append((base, other & M32) if rng.random() < 0.5 else (other & M32, base))
            for y, x in pairs:
                value, _f0 = rig.call(0x166798, [], [y, x], max_steps=5000)
                want = R.atan2_16(y, x)
                total += 1
                if ee_emu.sx16(value) != want:
                    failures += 1
                    if len(examples) < 3:
                        examples.append('%s y %08x x %08x: original %d model %d' % (config, y, x, ee_emu.sx16(value), want))
        report(label, failures, total, '0x166798 through the C library atan2f and atanf run for real: '
               'integer offsets on a grid, world-sized, unit-sized and arbitrary patterns, bit for bit', examples)
    R.set_fpu()

    label = 'angle.turnDir'
    if wanted(label):
        rig = Rig(elf)
        rng = random.Random('%s/turn' % OPTIONS['seed'])
        failures, total, examples = 0, 0, []
        out = rig.buffers[0]
        special = (0, 1, 0x7FFF, 0x8000, 0x8001, 0xFFFF, 0x4000, 0xC000)
        cases = [(a, b) for a in special for b in special]
        cases += [(gen_angle(rng), gen_angle(rng)) for _ in range(scaled(20000))]
        for a, b in cases:
            rig.emu.mem.w32(out, 0xDEADBEEF)
            value, _ = rig.call(0x166BC8, [a, b, out])
            value_null, _ = rig.call(0x166BC8, [a, b, 0])
            want_dir, want_abs = R.angle_turn_dir(a, b)
            total += 1
            if (ee_emu.s32(value), ee_emu.s32(value_null), rig.emu.mem.u32(out)) != (want_dir, want_dir, want_abs):
                failures += 1
                if len(examples) < 3:
                    examples.append('a %x b %x: original %d/%d abs %d, model %d abs %d' % (
                        a, b, ee_emu.s32(value), ee_emu.s32(value_null), rig.emu.mem.u32(out), want_dir, want_abs))
        report(label, failures, total, '0x166bc8: direction with and without the output pointer, and the '
               'stored absolute difference (0x8000 for a half turn)', examples)

    label = 'angle.approach'
    if wanted(label):
        failures, total, examples = 0, 0, []
        rng = random.Random('%s/approach' % OPTIONS['seed'])
        for index, config in enumerate(FPU_CONFIGS):
            rig = Rig(elf, config)
            for _ in range(scaled(20000) if index == 0 else scaled(1500)):
                rate = rng.choice((raw_uniform(rng, 0.0, 1.0), raw_uniform(rng, 0.0, 1.0), gen_float(rng, 'small')))
                low = rng.choice((R.MINUS_ONE, raw_uniform(rng, 0, 3000), raw_uniform(rng, 0, 50), gen_float(rng, 'world')))
                high = rng.choice((R.MINUS_ONE, raw_uniform(rng, 0, 3000), raw_uniform(rng, 0, 40000), gen_float(rng, 'world')))
                current, target = gen_angle(rng), gen_angle(rng)
                if rng.random() < 0.1:
                    target = current + rng.randrange(-3, 4)
                value, _ = rig.call(0x166C18, [current, target], [rate, low, high])
                want = R.angle_approach(rate, low, high, current, target)
                total += 1
                if ee_emu.sx16(value) != want:
                    failures += 1
                    if len(examples) < 3:
                        examples.append('%s rate %08x min %08x max %08x cur %x tgt %x: original %d model %d' % (
                            config, rate, low, high, current, target, ee_emu.sx16(value), want))
        report(label, failures, total, '0x166c18: rate, limits (including the -1.0 "no limit" value) and '
               'both angles random, result bit for bit', examples)
    R.set_fpu()


def test_idioms(elf):
    """Conversions the compiler emitted inline; each is run as a stretch of the function
    it sits in, with the registers it reads prepared."""
    label = 'convert.idioms'
    if not wanted(label):
        return
    failures, total, examples = 0, 0, []
    rng = random.Random('%s/idioms' % OPTIONS['seed'])
    for index, config in enumerate(FPU_CONFIGS):
        rig = Rig(elf, config)
        emu = rig.emu
        for _ in range(scaled(3000) if index == 0 else scaled(300)):
            # 0x161610-0x161654: degrees * 0.5 * 182.04443, rounded half away from zero,
            # added to a base angle minus a quarter turn
            degrees = rng.choice((raw_uniform(rng, -720, 720), R.f32(float(rng.randrange(-360, 361))),
                                  R.f32(rng.randrange(-720, 721) / 2.0), gen_float(rng, 'world')))
            base = gen_angle(rng)
            emu.f[21], emu.f[20] = degrees, 0
            emu.r[17] = ee_emu.sx32(base)
            emu.run(start=0x161610, until={0x161654}, max_steps=100)
            want = R.s16(base + R.round_half_away(R.mul(R.mul(degrees, R.HALF), R.K_DEG_TO_ANGLE)) - 0x4000)
            total += 1
            if ee_emu.s32(emu.r[16]) != want:
                failures += 1
                if len(examples) < 3:
                    examples.append('%s 0x161610 degrees %08x base %x: original %d model %d'
                                    % (config, degrees, base, ee_emu.s32(emu.r[16]), want))
            # 0x1985b0-0x1985c4: value * 182.0, truncated, low 16 bits stored
            value = rng.choice((raw_uniform(rng, -360, 360), gen_float(rng, 'world')))
            emu.f[0] = value
            emu.run(start=0x1985B0, until={0x1985C4}, max_steps=100)
            want = R.to_int(R.mul(value, 0x43360000)) & 0xFFFF
            total += 1
            if emu.r[2] & 0xFFFF != want:
                failures += 1
                if len(examples) < 3:
                    examples.append('%s 0x1985b0 value %08x: original %x model %x' % (config, value, emu.r[2] & 0xFFFF, want))
            # 0x164f70-0x164fac: float to unsigned (value * 255.0 first)
            value = rng.choice((raw_uniform(rng, 0, 2), R.f32(rng.uniform(0, 4.0e7)), gen_float(rng, 'mixed'),
                                rng.choice((0x4B808081, 0x4B808080, 0x4B80807F, 0x4C808081, 0x4F000000))))
            emu.f[14] = value
            emu.run(start=0x164F70, until={0x164FAC}, max_steps=100)
            want = R.to_uint(R.mul(value, R.K_255))
            total += 1
            if emu.r[4] & M32 != want:
                failures += 1
                if len(examples) < 3:
                    examples.append('%s 0x164f70 value %08x: original %x model %x' % (config, value, emu.r[4] & M32, want))
    report(label, failures, total, 'three inline conversions run as stretches: degrees to angle with '
           'round-half-away (0x161610), truncating float to 16 bits (0x1985b0), float to unsigned around '
           '2**31 (0x164f70)', examples)
    R.set_fpu()


def test_small_integer(elf):
    label = 'math.log2Floor'
    if wanted(label):
        rig = Rig(elf)
        rng = random.Random('%s/log2' % OPTIONS['seed'])
        values = list(range(-4, 70)) + [1 << n for n in range(63)] + [(1 << n) - 1 for n in range(1, 63)]
        values += [(1 << n) + 1 for n in range(1, 62)] + [-1 << 31, -1, 0x7FFFFFFF]
        values += [rng.getrandbits(rng.randrange(1, 63)) for _ in range(scaled(3000))]
        failures, examples = 0, []
        for value in values:
            got, _ = rig.call(0x1665F0, [value])
            if ee_emu.s32(got) != R.log2_floor(value):
                failures += 1
                examples.append('%d: original %d model %d' % (value, ee_emu.s32(got), R.log2_floor(value)))
        report(label, failures, len(values), '0x1665f0: small numbers, powers of two and their neighbours '
               'up to 2**62, negative values', examples)

    label = 'math.color_scaleClamped'
    if wanted(label):
        failures, total, examples = 0, 0, []
        rng = random.Random('%s/colour' % OPTIONS['seed'])
        for index, config in enumerate(FPU_CONFIGS):
            rig = Rig(elf, config)
            for _ in range(scaled(4000) if index == 0 else scaled(400)):
                factor = rng.choice((raw_uniform(rng, 0, 2), raw_uniform(rng, -1, 4), gen_float(rng, 'mixed')))
                colour = rng.getrandbits(32)
                got, _ = rig.call(0x165428, [colour], [factor])
                want = R.color_scale_clamped(factor, colour)
                total += 1
                if got & M32 != want:
                    failures += 1
                    if len(examples) < 3:
                        examples.append('%s factor %08x colour %08x: original %08x model %08x' % (config, factor, colour, got & M32, want))
        report(label, failures, total, '0x165428: four bytes scaled, truncated and clamped', examples)
    R.set_fpu()


NOISE_TABLE = 0x6E0D90
COSMETIC_SEED = 0x404460


def test_noise(elf):
    label = 'noise.lookup'
    if wanted(label):
        failures, total, examples = 0, 0, []
        rng = random.Random('%s/noise' % OPTIONS['seed'])
        for index, config in enumerate(FPU_CONFIGS):
            rig = Rig(elf, config)
            table = [rng.randrange(-0x8000, 0x8000) for _ in range(256)]
            table[rng.randrange(256)] = -0x8000
            table[rng.randrange(256)] = 0x7FFF
            rig.emu.mem.write(NOISE_TABLE, struct.pack('<256h', *table))
            if index == 0:
                indexes = list(range(4096)) + [-1, -16, -17, -4096, 4096, 4097, 0x7FFFFFFF, -0x80000000]
                indexes += [rng.randrange(-1 << 31, 1 << 31) for _ in range(scaled(2000))]
            else:
                indexes = [rng.randrange(-70000, 70000) for _ in range(scaled(500))]
            for value in indexes:
                _v, f0 = rig.call(0x166B48, [value])
                want = R.noise(table, value)
                total += 1
                if f0 != want:
                    failures += 1
                    if len(examples) < 3:
                        examples.append('%s index %d: original %08x model %08x' % (config, value, f0, want))
            out = rig.buffers[0]
            for _ in range(scaled(300)):
                base, step = rng.randrange(-70000, 70000), rng.randrange(-5000, 5000)
                rig.call(0x164578, [out, base, step])
                total += 1
                if rig.get(out, 3) != R.noise3(table, base, step):
                    failures += 1
        report(label, failures, total, '0x166b48 with a random table written to 0x6e0d90: every index of '
               'one period (4,096), negative and huge indexes, bit for bit; 0x164578 (three samples) too',
               examples)
    R.set_fpu()

    label = 'noise.buildTable'
    if wanted(label):
        failures, total, examples = 0, 0, []
        rng = random.Random('%s/noisetable' % OPTIONS['seed'])
        weights_seen = None
        for index, config in enumerate(FPU_CONFIGS):
            rig = Rig(elf, config)
            emu = rig.emu
            for trial in range(scaled(40) if index == 0 else 3):
                seed = rng.getrandbits(32)
                stale = (0, 0, 0) if trial % 2 == 0 else tuple(raw_uniform(rng, -0.5, 0.5) for _ in range(3))
                frame = rig.sp - 0x60                   # the function's own stack frame
                emu.mem.write(frame, bytes([0xEE]) * 0x60)
                for k in range(3):
                    emu.mem.w32(frame + 4 + 4 * k, stale[k])
                emu.mem.w32(COSMETIC_SEED, seed)
                emu.mem.write(NOISE_TABLE, bytes(512))
                rig.call(0x1646C8, max_steps=2000000)
                got = list(struct.unpack('<256h', emu.mem.read(NOISE_TABLE, 512)))
                weights_seen = rig.get(frame + 0x20, 4)
                want, seed_after = R.build_noise_table(seed, stale)
                total += 1
                if got != want or emu.mem.u32(COSMETIC_SEED) != seed_after:
                    failures += 1
                    if len(examples) < 3:
                        bad = [i for i in range(256) if got[i] != want[i]]
                        examples.append('%s seed %08x stale %s: %d entries differ (first %s), seed after %08x / %08x'
                                        % (config, seed, hexlist(stale), len(bad), bad[:4], emu.mem.u32(COSMETIC_SEED), seed_after))
        report(label, failures, total, '0x1646c8 run for real (with the C library powf): all 256 entries and '
               'the seed afterwards, for random seeds, with zero and with non-zero stale stack words; '
               'octave weights from powf = %s' % hexlist(weights_seen or []), examples)
    R.set_fpu()


# ---------------------------------------------------------------------------------------
# Software double precision
# ---------------------------------------------------------------------------------------
D_EDGE = [0, 1 << 63, 0x3FF0000000000000, 0xBFF0000000000000, 0x7FF0000000000000, 0xFFF0000000000000,
          0x7FF8000000000000, 0x7FF0000000000001, 0xFFF8000000000123, 1, 0x000FFFFFFFFFFFFF,
          0x0010000000000000, 0x8010000000000000, 0x7FEFFFFFFFFFFFFF, 0xFFEFFFFFFFFFFFFF,
          0x3FF8000000000000, 0x4003333333333333, 0x3FECCCCCCCCCCCCC, 0x41DFFFFFFFC00000,
          0xC1E0000000000000, 0x41E0000000000000, 0x47EFFFFFE0000000, 0x47F0000000000000,
          0x3810000000000000, 0x380FFFFFFFFFFFFF, 0x4800000000000000, 0x4330000000000000]


def gen_double(rng, other=None):
    kind = rng.randrange(8)
    if kind == 0:
        return rng.choice(D_EDGE)
    if kind == 1:
        return rng.getrandbits(64)
    if kind == 2:
        return R.d64(rng.uniform(-1000.0, 1000.0))
    if kind == 3:
        return R.d64(float(rng.randrange(-100000, 100000)))
    if kind == 4:
        return R.d64(rng.uniform(-1, 1) * 10.0 ** rng.randrange(-300, 300))
    if kind == 5:
        return R.f2d(gen_float(rng, 'world'))           # a float widened, as game code does
    if other is not None:                               # an exponent near the other operand's,
        exp = ((other >> 52) & 0x7FF) + rng.choice((0, 0, 1, -1, 2, -2, 52, 53, 54, 60, 61, 62, 63, 64,
                                                    65, -53, -62, -63, -64, -65))   # or far below it
        exp = max(1, min(0x7FE, exp))
        return (rng.getrandbits(1) << 63) | (exp << 52) | rng.getrandbits(52)
    return R.d64(rng.uniform(0.0, 4.0))


def test_softdouble(elf):
    rig = Rig(elf)
    emu = rig.emu

    def call64(addr, *args):
        emu.r[29] = rig.sp
        return emu.call(addr, *args, max_steps=100000)

    binary = (('dadd', 0x3AF410, R.dadd, 'a + b'), ('dsub', 0x3AF468, R.dsub, 'a - b'),
              ('dmul', 0x3AF4D0, R.dmul, 'a * b'), ('ddiv', 0x3AF758, R.ddiv, 'a / b'),
              ('fmod', 0x3A5A38, R.fmod, 'C library fmod (denormals honoured)'))
    for name, addr, model, text in binary:
        label = 'double.%s' % name
        if not wanted(label):
            continue
        rng = random.Random('%s/%s' % (OPTIONS['seed'], label))
        failures, total, examples, off_ieee = 0, 0, [], 0
        pairs = [(a, b) for a in D_EDGE for b in D_EDGE]
        for _ in range(scaled(20000)):
            a = gen_double(rng)
            pairs.append((a, gen_double(rng, a)))
        for a, b in pairs:
            got = call64(addr, a, b)
            want = model(a, b)
            total += 1
            if got != want:
                failures += 1
                if len(examples) < 3:
                    examples.append('%016x, %016x: original %016x model %016x' % (a, b, got, want))
            if name != 'fmod':
                try:
                    x, y = R.to_double(a), R.to_double(b)
                    ieee = {'dadd': lambda: x + y, 'dsub': lambda: x - y, 'dmul': lambda: x * y,
                            'ddiv': lambda: x / y}[name]()
                    if ieee == ieee and R.d64(ieee) != got:
                        off_ieee += 1
                except (ZeroDivisionError, OverflowError):
                    pass
        extra = '' if name == 'fmod' else '; %d of them differ from IEEE round-to-nearest arithmetic' % off_ieee
        report(label, failures, total, '0x%06x %s: every pair of %d edge patterns plus random pairs '
               '(game-sized, whole numbers, any magnitude, any pattern, exponents 0-2 and 52-65 apart)%s'
               % (addr, text, len(D_EDGE), extra), examples)

    label = 'double.dcmp'
    if wanted(label):
        rng = random.Random('%s/%s' % (OPTIONS['seed'], label))
        failures, total, examples = 0, 0, []
        pairs = [(a, b) for a in D_EDGE for b in D_EDGE]
        for _ in range(scaled(8000)):
            a = gen_double(rng)
            b = gen_double(rng, a)
            if rng.random() < 0.2:
                b = rng.choice((a, a ^ (1 << 63), a + 1, a - 1)) & ee_emu.M64
            pairs.append((a, b))
        for a, b in pairs:
            got = ee_emu.s32(call64(0x3AF9B8, a, b))
            want = R.dcmp(a, b)
            total += 1
            if got != want:
                failures += 1
                if len(examples) < 3:
                    examples.append('%016x, %016x: original %d model %d' % (a, b, got, want))
        report(label, failures, total, '0x3af9b8 comparison: -1 / 0 / +1, +1 for a NaN', examples)

    label = 'double.convert'
    if wanted(label):
        rng = random.Random('%s/%s' % (OPTIONS['seed'], label))
        failures, total, examples, off_ieee = 0, 0, [], 0
        for value in [0, 1, -1, 0x7FFFFFFF, -0x80000000, -0x7FFFFFFF, 0x1000000, 0x1000001] + \
                [rng.randrange(-1 << 31, 1 << 31) for _ in range(scaled(3000))] + \
                [rng.randrange(-70000, 70000) for _ in range(scaled(2000))]:
            got = call64(0x3AFA08, value)
            total += 1
            if got != R.i2d(value):
                failures += 1
                examples.append('i2d(%d): original %016x model %016x' % (value, got, R.i2d(value)))
        doubles = list(D_EDGE) + [gen_double(rng) for _ in range(scaled(8000))]
        doubles += [R.d64(rng.uniform(-3e9, 3e9)) for _ in range(scaled(2000))]
        doubles += [R.d64(float(n) + d) for n in (-2147483649, -2147483648, -2147483647, 2147483646, 2147483647,
                                                  2147483648) for d in (-0.5, 0.0, 0.5)]
        for bits in doubles:
            got = ee_emu.s32(call64(0x3AFAC0, bits))
            total += 1
            if got != R.d2i(bits):
                failures += 1
                if len(examples) < 3:
                    examples.append('d2i(%016x): original %d model %d' % (bits, got, R.d2i(bits)))
            emu.r[29] = rig.sp
            emu.call(0x3AFB90, bits, max_steps=100000)
            got = emu.f[0]
            total += 1
            if got != R.d2f(bits):
                failures += 1
                if len(examples) < 3:
                    examples.append('d2f(%016x): original %08x model %08x' % (bits, got, R.d2f(bits)))
            value = R.to_double(bits)
            if value == value and abs(value) < 3e38 and abs(value) > 2e-38 and R.f32(value) != got:
                off_ieee += 1
        floats = list(EDGE) + [gen_float(rng, 'mixed') for _ in range(scaled(6000))]
        for raw in floats:
            emu.f[12] = raw
            got = call64(0x3AEF58)
            total += 1
            if got != R.f2d(raw):
                failures += 1
                if len(examples) < 3:
                    examples.append('f2d(%08x): original %016x model %016x' % (raw, got, R.f2d(raw)))
        report(label, failures, total, 'int -> double 0x3afa08, double -> int 0x3afac0, double -> float '
               '0x3afb90 (truncating: %d results differ from IEEE rounding), float -> double 0x3aef58 '
               '(exponent field 255 is a number)' % off_ieee, examples)

    label = 'double.literal'
    if wanted(label):
        # the idiom  f = f * 1.5  etc. as the compiler emits it: f2d, dmul by a constant, d2f
        rng = random.Random('%s/%s' % (OPTIONS['seed'], label))
        failures, total, off_single, off_ieee = 0, 0, 0, 0
        constants = ('1.5', '2.4', '1.4', '0.9', '0.3', '0.45', '0.7', '1.01', '0.02', '18.4', '6.28')
        for _ in range(scaled(6000)):
            raw = rng.choice((raw_uniform(rng, 0, 500), raw_uniform(rng, -5, 5), gen_float(rng, 'world')))
            text = rng.choice(constants)
            k = R.dconst(text)
            emu.f[12] = raw
            wide = call64(0x3AEF58)
            product = call64(0x3AF4D0, wide, k)
            emu.r[29] = rig.sp
            emu.call(0x3AFB90, product, max_steps=100000)
            got = emu.f[0]
            want = R.d2f(R.dmul(R.f2d(raw), k))
            total += 1
            if got != want:
                failures += 1
            if R.mul(raw, R.const(text)) != got:
                off_single += 1
            if (raw >> 23) & 0xFF not in (0, 255) and R.f32(R.to_float(raw) * float(text)) != got:
                off_ieee += 1
        report(label, failures, total, 'float * double literal -> float, as game code does it (f2d, dmul, '
               'd2f run in sequence): %d of the results differ from a single-precision multiply by the '
               'same literal, %d from IEEE double arithmetic rounded to float' % (off_single, off_ieee))

    label = 'double.constants'
    if wanted(label):
        known = ((0x520048, '2.4'), (0x52FC78, '1.4'), (0x5376A8, '0.3'), (0x5376B0, '0.45'), (0x5376B8, '0.7'),
                 (0x53D448, '0.9'), (0x53D460, '1.01'), (0x53E570, '0.02'), (0x53E658, '18.4'),
                 (0x53E680, '0.001'), (0x5477E0, '6.28'), (0x551B70, '4.4'), (0x545778, '14.9'),
                 (0x537D28, '162.313'), (0x53B0E8, '13.723'))
        failures, examples, off = 0, [], 0
        for addr, text in known:
            word = emu.mem.u64(addr)
            if word != R.dconst(text):
                failures += 1
                examples.append('0x%x: executable %016x, dconst(%s) %016x' % (addr, word, text, R.dconst(text)))
            if word != R.d64(float(text)):
                off += 1
        report(label, failures, len(known), 'double literals of game code (read at the addresses the code '
               'loads them from) equal the decimal value TRUNCATED to 53 bits; %d of %d would differ if '
               'rounded to nearest' % (off, len(known)), examples)


# ---------------------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------------------
SHARED_SEED = 0x404464


def test_generators(elf):
    rng = random.Random('%s/generators' % OPTIONS['seed'])
    seeds = [0, 1, 0xFFFFFFFF, 0x80000000, 0x3C6E, 0xFFFF] + [rng.getrandbits(32) for _ in range(6)]
    length = scaled(3000)

    label = 'rand.object'
    if wanted(label):
        rig = Rig(elf)
        obj = rig.emu.alloc(0x60)
        failures, total = 0, 0
        for seed in seeds:
            rig.emu.mem.w32(obj + 0x44, seed)
            model = R.Lcg(seed)
            for _ in range(length):
                got, _ = rig.call(0x1509D0, [obj])
                want = model.draw()
                total += 1
                if got != want or rig.emu.mem.u32(obj + 0x44) != model.state:
                    failures += 1
        report(label, failures, total, 'GameObject_rand 0x1509d0: draw and state at +0x44 over %d seeds, '
               '%d draws each' % (len(seeds), length))

    label = 'rand.spell'
    if wanted(label):
        rig = Rig(elf)
        spell = rig.emu.alloc(0x60)
        failures, total = 0, 0
        for seed in seeds:
            rig.emu.mem.w32(spell + 0x10, seed)
            model = R.Lcg(seed)
            for _ in range(length):
                got, _ = rig.call(0x16A964, [spell])
                want = model.draw()
                total += 1
                if got != want or rig.emu.mem.u32(spell + 0x10) != model.state:
                    failures += 1
        report(label, failures, total, 'Spell_rand 0x16a964: draw and state at +0x10')

    label = 'rand.shared'
    if wanted(label):
        rig = Rig(elf)
        failures, total = 0, 0
        for seed in seeds:
            rig.emu.mem.w32(SHARED_SEED, seed)
            model = R.SharedRandom(seed)
            for _ in range(length):
                got, _ = rig.call(0x146570)             # the inline update, as script getRand
                want = model.draw()
                total += 1
                if got != want or rig.emu.mem.u32(SHARED_SEED) != model.state:
                    failures += 1
        report(label, failures, total, 'the shared seed 0x404464 through script getRand 0x146570 (the three '
               'inlined instructions as a function)')

    label = 'rand.seeding'
    if wanted(label):
        rig = Rig(elf)
        emu = rig.emu
        obj = emu.alloc(0x60)
        failures, total = 0, 0
        for seed in seeds + [rng.getrandbits(32) for _ in range(scaled(300))]:
            # the tail of GameObject_ctor that draws the object's seed: 0x14cd4c .. 0x14cd84
            emu.mem.w32(SHARED_SEED, seed)
            emu.mem.w32(obj + 0x44, 0xEEEEEEEE)
            emu.r[17] = obj
            emu.r[20] = 0
            emu.run(start=0x14CD4C, until={0x14CD84}, max_steps=100)
            shared = R.SharedRandom(seed)
            model = R.ObjectRandom(shared)
            total += 1
            if emu.mem.u32(obj + 0x44) != model.state or emu.mem.u32(SHARED_SEED) != shared.state:
                failures += 1
            # the out-of-line Spell constructor 0x3d0bc4
            emu.mem.w32(SHARED_SEED, seed)
            emu.mem.w32(obj + 0x10, 0xEEEEEEEE)
            rig.call(0x3D0BC4, [obj, 0])
            shared = R.SharedRandom(seed)
            model = R.SpellRandom(shared)
            total += 1
            if emu.mem.u32(obj + 0x10) != model.state or emu.mem.u32(SHARED_SEED) != shared.state:
                failures += 1
        report(label, failures, total, 'an object (stretch 0x14cd4c-0x14cd84 of GameObject_ctor) and a spell '
               '(constructor 0x3d0bc4) take one draw of the shared seed, a 16-bit number, as their state')

    label = 'rand.floats'
    if wanted(label):
        failures, total = 0, 0
        for index, config in enumerate(FPU_CONFIGS):
            rig = Rig(elf, config)
            obj = rig.emu.alloc(0x60)
            out = rig.buffers[0]
            for seed in (seeds if index == 0 else seeds[:3]):
                rig.emu.mem.w32(obj + 0x44, seed)
                model = R.Lcg(seed)
                for _ in range(scaled(400)):
                    _v, f0 = rig.call(0x3C7F30, [obj])
                    total += 1
                    if f0 != model.unit() or rig.emu.mem.u32(obj + 0x44) != model.state:
                        failures += 1
                for _ in range(scaled(150)):
                    rig.call(0x3C7F60, [obj, out], max_steps=20000)
                    want = model.in_unit_sphere()
                    total += 1
                    if rig.get(out, 3) != want or rig.emu.mem.u32(obj + 0x44) != model.state:
                        failures += 1
                    rig.call(0x3C8030, [out, obj], max_steps=20000)
                    want = model.in_unit_sphere()
                    total += 1
                    if rig.get(out, 3) != want or rig.emu.mem.u32(obj + 0x44) != model.state:
                        failures += 1
        report(label, failures, total, 'the helpers 0x3c7f30 (draw * 2**-16) and 0x3c7f60 / 0x3c8030 (point '
               'in the unit sphere by rejection): values and number of draws consumed')
    R.set_fpu()

    label = 'rand.libc'
    if wanted(label):
        rig = Rig(elf)
        emu = rig.emu
        reent = emu.mem.u32(0x50C7E8)
        failures, total = 0, 0
        model = R.LibcRand()
        initial = emu.mem.u64(reent + 0xA8)
        if initial != model.state:
            failures += 1
        for seed in [None] + seeds:
            if seed is not None:
                rig.call(0x3B70D8, [seed])
                model.seed(seed)
            for _ in range(length):
                got, _ = rig.call(0x3B70F0)
                want = model.rand()
                total += 1
                if ee_emu.s32(got) != want or emu.mem.u64(reent + 0xA8) != model.state:
                    failures += 1
        report(label, failures, total, 'libc_rand 0x3b70f0 / libc_srand 0x3b70d8: value and 64-bit state, '
               'from the state in the executable (%d) and after each srand' % initial)


# ---------------------------------------------------------------------------------------
# Object pool
# ---------------------------------------------------------------------------------------
POOL_INIT, POOL_NEW, POOL_FREE, POOL_COUNT_FREE, POOL_DUMP = 0x14FCD8, 0x14FDB8, 0x150470, 0x150410, 0x150290
POOL_TABLE, POOL_LAST = 0x403A10, 0x4D8A24
POOL_SIZES = (0x148, 0x148, 0x100, 0x180, 0x181, 0x248, 0x268, 0x3C8, 0x4F8, 0x500, 0x501, 0x590,
              3000, 1, 0, 0x10, 0x200)


def test_pool(elf):
    label = 'pool.sequence'
    if not wanted(label):
        return
    emu = EE(elf)
    emu.record_calls = False
    emu.record_writes = False
    dumps = []
    emu.stub(POOL_DUMP, function=lambda e: dumps.append(1), name='mem_dumpHeap')
    sp = emu.r[29]
    rng = random.Random('%s/pool' % OPTIONS['seed'])
    model = R.Pool()

    def call(addr, *args):
        emu.r[29] = sp
        return emu.call(addr, *args, max_steps=2000000)

    call(POOL_INIT)
    failures, steps, examples = 0, 0, []
    counts = {'new': 0, 'free': 0, 'failed': 0, 'spilled': 0}
    live = []

    def table():
        return [emu.mem.u32(POOL_TABLE + 16 * c + 12) for c in range(3)]

    def bad(text):
        nonlocal failures
        failures += 1
        if len(examples) < 3:
            examples.append('step %d: %s' % (steps, text))

    def chains_equal():
        for c in range(3):
            want = model.free_list(c)
            addr, got = table()[c], []
            while addr and len(got) <= len(want):
                got.append(addr)
                addr = emu.mem.u32(addr)
            if got != want:
                return False
        return True

    if [emu.mem.u32(POOL_TABLE + 16 * c + 8) for c in range(3)] != model.base or not chains_equal():
        bad('state after pool_init differs')
    if emu.mem.u32(POOL_TABLE + 0x38) != model.end:
        bad('end of pool')

    def do_new(size):
        before = len(dumps)
        size = ee_emu.s32(size)                         # an int argument arrives sign-extended
        got = call(POOL_NEW, size) & M32
        want = model.new(size)
        counts['new'] += 1
        if got != want:
            bad('pool_new(%d): original 0x%x model 0x%x' % (size, got, want))
        if got == 0:
            counts['failed'] += 1
            if len(dumps) != before + 1:
                bad('a failed pool_new did not print the heap exactly once')
            return
        index = model.class_of(got)
        block = R.Pool.CLASSES[index][0]
        if index and size <= R.Pool.CLASSES[index - 1][0]:
            counts['spilled'] += 1
        if emu.mem.read(got, block) != bytes(block):
            bad('block 0x%x not zero over %d bytes' % (got, block))
        if emu.mem.u32(POOL_LAST) != model.last:
            bad('0x4d8a24 is not the block handed out')
        emu.mem.write(got, bytes([0xA5]) * block)       # dirty it, as an object would
        live.append(got)

    def do_free():
        addr = live.pop(rng.randrange(len(live)) if rng.random() < 0.7 else -1)
        call(POOL_FREE, addr)
        model.free(addr)
        counts['free'] += 1
        if emu.mem.u32(addr) != model.link[addr]:
            bad('link word of freed block 0x%x' % addr)

    def step(p_new, sizes=POOL_SIZES):
        nonlocal steps
        steps += 1
        if not live or rng.random() < p_new:
            do_new(rng.choice(sizes) if rng.random() < 0.9 else rng.randrange(-4, 3100))
        else:
            do_free()
        got = ee_emu.s32(call(POOL_COUNT_FREE))
        if got != model.count_free():
            bad('pool_countFree: original %d model %d' % (got, model.count_free()))
        if table() != model.head:
            bad('list heads differ')
        if steps % 64 == 0 and not chains_equal():
            bad('free lists differ')

    phases = ((scaled(400), 0.6, POOL_SIZES),                 # from an empty pool
              (scaled(1500), 0.9, POOL_SIZES),                # fill up: spill, then failures
              (scaled(4000), 0.5, POOL_SIZES),                # hover around full
              (scaled(1500), 0.5, (0x148, 0x100, 0x10)),      # small requests only: three-way spill
              (scaled(1500), 0.15, POOL_SIZES))               # drain in random order
    for length, p_new, sizes in phases:
        for _ in range(length):
            step(p_new, sizes)
    # exhaustion from wherever the sequence left the pool, then an oversized request
    while True:
        steps += 1
        before = counts['failed']
        do_new(0x10)
        if counts['failed'] != before:
            break
    for size in (3001, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF):
        steps += 1
        do_new(size)
    while live:
        steps += 1
        do_free()
    if ee_emu.s32(call(POOL_COUNT_FREE)) != 1056 or model.count_free() != 1056 or not chains_equal():
        bad('after freeing everything the lists differ or do not hold 1056 blocks')
    report(label, failures, steps, 'pool_init/new/free/countFree run for real: returned address, zero '
           'fill, list heads and free count after EVERY step, whole free lists every 64th and at the end '
           '(%d allocations, %d of them spilled into a larger class, %d refused, %d frees)'
           % (counts['new'], counts['spilled'], counts['failed'], counts['free']), examples)


# ---------------------------------------------------------------------------------------
# Handle lists
# ---------------------------------------------------------------------------------------
H_INIT, H_LINK, H_LINK_BOTH, H_ADD, H_INSERT, H_REMOVE, H_CLEAR = (
    0x1A17D0, 0x1A1738, 0x1A18F0, 0x1A1980, 0x1A19D0, 0x1A1868, 0x1A1698)
IT_BEGIN, IT_NEXT, IT_END = 0x1A1A48, 0x1A1B38, 0x1A1AE8
H_FREE_HEAD = 0x864EA8
OBJECT_FLAGS = (0, 0, 0x2, 0x8, 0x20, 0x20000, 0x200000, 0x20028, 0x40)
MASKS = (0, 0, 0x20000, 0x200000, 0x8, 0x220000, 0x2A, 0xFFFFFFFF)


class FakeObject:
    """What the handle code needs of an object: three list heads and the flag word."""

    def __init__(self, addr, flags):
        self.addr, self.flags = addr, flags
        self.heads = [R.Cell(addr), R.Cell(addr + 4), R.Cell(addr + 8)]


class HandleRig:
    """The original node pool in the interpreter and the model side by side: every
    operation is applied to both and the results compared."""

    def __init__(self, elf, lists=10, objects=28, seed=0):
        emu = self.emu = EE(elf)
        emu.record_calls = False
        emu.record_writes = False
        self.sp = emu.r[29]
        self.rng = random.Random(seed)
        self.model = R.HandlePool()
        self.call(H_INIT)
        self.lists = [R.Cell(emu.alloc(4)) for _ in range(lists)]
        self.objects = []
        for _ in range(objects):
            addr = emu.alloc(16)
            flags = self.rng.choice(OBJECT_FLAGS)
            emu.mem.w32(addr + 12, flags)
            self.objects.append(FakeObject(addr, flags))
        self.by_addr = {obj.addr: obj for obj in self.objects}
        self.iter_addr = {}                             # id(model iterator) -> address
        self.iters = []
        self.failures = 0
        self.examples = []
        self.steps = 0

    def call(self, addr, *args):
        self.emu.r[29] = self.sp
        return self.emu.call(addr, *args, max_steps=200000) & M32

    def bad(self, text):
        self.failures += 1
        if len(self.examples) < 3:
            self.examples.append('step %d: %s' % (self.steps, text))

    # -- address of a model thing
    def ptr(self, thing):
        if thing is None:
            return 0
        if isinstance(thing, R.Node):
            return R.HandlePool.NODE_BASE + R.HandlePool.NODE_SIZE * thing.index
        if isinstance(thing, R.Cell):
            return thing.name
        if isinstance(thing, R.Iterator):
            return self.iter_addr[id(thing)]
        return thing.addr

    def cells(self):
        out = list(self.lists)
        for obj in self.objects:
            out += obj.heads
        return out

    # -- mirrored operations
    def link(self, head, obj, which=0):
        got = self.call(H_LINK, self.ptr(head), self.ptr(obj.heads[which]), obj.addr)
        node = self.model.link(head, obj.heads[which], obj)
        if got != self.ptr(node):
            self.bad('handle_link returned 0x%x, model 0x%x' % (got, self.ptr(node)))
        return node

    def link_both(self, head_a, obj_b, head_b, obj_a):
        self.call(H_LINK_BOTH, self.ptr(head_a), obj_b.addr, self.ptr(head_b), obj_a.addr)
        self.model.link_both(head_a, obj_b, head_b, obj_a)

    def add(self, head, obj):
        got = self.call(H_ADD, self.ptr(head), obj.addr)
        node = self.model.add(head, obj)
        if got != self.ptr(node):
            self.bad('handle_addNode returned 0x%x, model 0x%x' % (got, self.ptr(node)))
        return node

    def insert(self, head, after, obj):
        got = self.call(H_INSERT, self.ptr(head), self.ptr(after), obj.addr)
        node = self.model.insert(head, after, obj)
        if got != self.ptr(node):
            self.bad('handle_insertNode returned 0x%x, model 0x%x' % (got, self.ptr(node)))
        return node

    def remove(self, node):
        got = self.call(H_REMOVE, self.ptr(node))
        obj = self.model.remove(node)
        if got != self.ptr(obj):
            self.bad('handle_removeNode returned 0x%x, model 0x%x' % (got, self.ptr(obj)))

    def clear(self, head):
        self.call(H_CLEAR, self.ptr(head))
        self.model.clear(head)

    def begin(self, head, mask):
        addr = self.emu.alloc(0x18)
        self.emu.mem.write(addr, bytes([0xEE]) * 0x18)
        self.call(IT_BEGIN, addr, self.ptr(head), mask)
        it = R.Iterator(head, mask)
        self.iter_addr[id(it)] = addr
        self.iters.append(it)
        self.check_iter(it, 'iter_begin')
        return it

    def advance(self, it):
        self.call(IT_NEXT, self.ptr(it))
        it.advance()
        self.check_iter(it, 'iter_next')

    def end(self, it):
        self.call(IT_END, self.ptr(it), 2)
        it.end()
        self.iters.remove(it)

    def current(self, it):
        """What the caller's loop reads: the object of the node before the iterator."""
        addr = self.ptr(it)
        prev = self.emu.mem.u32(addr + 4)
        got = self.emu.mem.u32(prev + 12) if prev else 0
        want = it.current
        if got != self.ptr(want):
            self.bad('current object 0x%x, model 0x%x' % (got, self.ptr(want)))
        return want

    def check_iter(self, it, what):
        addr = self.ptr(it)
        mem = self.emu.mem
        got = (mem.u32(addr), mem.u32(addr + 4), mem.u32(addr + 12), mem.u32(addr + 20))
        want = (self.ptr(it.next), self.ptr(it.prev), 0, it.mask)
        if got != want:
            self.bad('%s left the iterator as %s, model %s' % (what, hexlist(got), hexlist(want)))
        if (mem.u32(addr + 8), mem.u32(addr + 16)) != (0xEEEEEEEE, 0xEEEEEEEE):
            self.bad('%s wrote iterator words +8 or +0x10' % what)

    # -- comparing the structures
    def check(self, full=False):
        """Every list (the test's and each object's three): the chain of nodes and each
        node's four fields; the free list head and its first nodes; with full=True the
        whole node array and the whole free list."""
        mem = self.emu.mem
        base, size = R.HandlePool.NODE_BASE, R.HandlePool.NODE_SIZE
        for cell in self.cells():
            addr = mem.u32(cell.name)
            thing = cell.next
            guard = 0
            while (addr or thing is not None) and guard < 7000:
                guard += 1
                if addr != self.ptr(thing):
                    self.bad('list at 0x%x: node 0x%x, model 0x%x' % (cell.name, addr, self.ptr(thing)))
                    break
                if isinstance(thing, R.Node):
                    got = (mem.u32(addr + 4), mem.u32(addr + 8), mem.u32(addr + 12), mem.u16(addr + 16))
                    want = (self.ptr(thing.prev), self.ptr(thing.partner), self.ptr(thing.obj), thing.tag)
                else:
                    got = (mem.u32(addr + 4), mem.u32(addr + 12))
                    want = (self.ptr(thing.prev), 0)
                if got != want:
                    self.bad('node 0x%x fields %s, model %s' % (addr, hexlist(got), hexlist(want)))
                    break
                addr = mem.u32(addr)
                thing = thing.next
        addr, node = mem.u32(H_FREE_HEAD), self.model.free
        for _ in range(7000 if full else 12):
            if addr != self.ptr(node):
                self.bad('free list: 0x%x, model 0x%x' % (addr, self.ptr(node)))
                break
            if node is None:
                break
            addr, node = mem.u32(addr), node.next
        if full:
            blob = mem.read(base, size * len(self.model.nodes))
            for node in self.model.nodes:
                got = struct.unpack_from('<4IH', blob, node.index * size)
                want = (self.ptr(node.next), self.ptr(node.prev), self.ptr(node.partner),
                        self.ptr(node.obj), node.tag)
                if got != want:
                    self.bad('node %d memory %s, model %s' % (node.index, hexlist(got), hexlist(want)))
                    break

    def list_nodes(self, head):
        out, thing = [], head.next
        while thing is not None:
            if isinstance(thing, R.Node):
                out.append(thing)
            thing = thing.next
        return out

    def has_iterator(self, head):
        thing = head.next
        while thing is not None:
            if isinstance(thing, R.Iterator):
                return True
            thing = thing.next
        return False


def test_handles(elf):
    label = 'handles.pool'
    if wanted(label):
        rig = HandleRig(elf, seed='%s/hpool' % OPTIONS['seed'])
        mem = rig.emu.mem
        count = 0
        addr = mem.u32(H_FREE_HEAD)
        ascending = addr == R.HandlePool.NODE_BASE
        while addr:
            count += 1
            following = mem.u32(addr)
            if following and following != addr + 20:
                ascending = False
            addr = following
        if count != R.HandlePool.NODE_COUNT or not ascending:
            rig.bad('handle_initPool threads %d nodes (model %d), ascending %s' % (count, R.HandlePool.NODE_COUNT, ascending))
        rig.check(full=True)
        # use every node: 3,048 links; the next one has nothing to take
        obj = rig.objects[0]
        for index in range(R.HandlePool.NODE_COUNT // 2):
            rig.steps += 1
            rig.link(rig.lists[index % len(rig.lists)], obj, index % 3)
        rig.check(full=True)
        if mem.u32(H_FREE_HEAD) != 0 or rig.model.free is not None:
            rig.bad('free list not empty after 3,048 links')
        stopped = model_stopped = False
        try:
            rig.call(H_LINK, rig.ptr(rig.lists[0]), rig.ptr(obj.heads[0]), obj.addr)
        except EmuError:
            stopped = True
        try:
            rig.model.link(rig.lists[0], obj.heads[0], obj)
        except R.HandleError:
            model_stopped = True
        if not (stopped and model_stopped):
            rig.bad('exhausted pool: interpreter stopped %s, model stopped %s' % (stopped, model_stopped))
        report(label, rig.failures, rig.steps + 2, 'handle_initPool threads %d nodes in ascending order; '
               '3,048 links use them all (whole node array compared); the 3,049th handle_link stores '
               'through a null node (the interpreter stops on the access, the model raises)' % count, rig.examples)

    label = 'handles.sequence'
    if wanted(label):
        rig = HandleRig(elf, seed='%s/hseq' % OPTIONS['seed'])
        rng = rig.rng
        ops = {}

        def note(op):
            ops[op] = ops.get(op, 0) + 1

        for _ in range(scaled(30000)):
            rig.steps += 1
            roll = rng.random()
            head = rng.choice(rig.lists)
            obj = rng.choice(rig.objects)
            nodes = rig.list_nodes(head)
            used = R.HandlePool.NODE_COUNT - rig.model.count_free() if rig.steps % 50 == 0 else 0
            if used > 4000:
                roll = 0.99
            if roll < 0.30:
                rig.link(head, obj, rng.randrange(3))
                note('link')
            elif roll < 0.36:
                # the two nodes of one link must not share a list: clearing such a list
                # walks on into the free list (docs/spec/core.md, "Undefined")
                other = rng.choice([o for o in rig.objects if o is not obj])
                rig.link_both(obj.heads[rng.randrange(3)], obj, other.heads[rng.randrange(3)], other)
                note('linkBoth')
            elif roll < 0.44:
                rig.add(head, obj)
                note('addNode')
            elif roll < 0.52:
                rig.insert(head, rng.choice(nodes) if nodes and rng.random() < 0.8 else None, obj)
                note('insertNode')
            elif roll < 0.72:
                if nodes:
                    rig.remove(rng.choice(nodes))
                    note('removeNode')
            elif roll < 0.80:
                # an object is destroyed: its three heads are cleared
                if not any(rig.has_iterator(cell) for cell in obj.heads):
                    for cell in obj.heads:
                        rig.clear(cell)
                    note('clear (object heads)')
            elif roll < 0.84:
                if not rig.has_iterator(head):
                    rig.clear(head)
                    note('clear (list)')
            elif roll < 0.90:
                if len(rig.iters) < 4:
                    it = rig.begin(head, rng.choice(MASKS))
                    if not it.done:
                        rig.current(it)
                    note('iter_begin')
            elif roll < 0.97:
                if rig.iters:
                    it = rng.choice(rig.iters)
                    if not it.done:
                        rig.advance(it)
                        if not it.done:
                            rig.current(it)
                        note('iter_next')
            else:
                if rig.iters:
                    rig.end(rng.choice(rig.iters))
                    note('iter_end')
            rig.check(full=rig.steps % 1000 == 0)
        for it in list(rig.iters):
            rig.end(it)
        for cell in rig.cells():
            rig.clear(cell)
        rig.check(full=True)
        if rig.model.count_free() != R.HandlePool.NODE_COUNT:
            rig.bad('nodes lost: %d free after clearing every list' % rig.model.count_free())
        report(label, rig.failures, rig.steps, 'random operations on %d lists and %d objects, up to 4 live '
               'iterators standing in the lists while they change: return values, every list, the free '
               'list head and each iterator after EVERY step, the whole node array every 1,000th (%s)'
               % (len(rig.lists), len(rig.objects), ', '.join('%d %s' % (n, op) for op, n in sorted(ops.items()))),
               rig.examples)

    label = 'handles.iteration'
    if wanted(label):
        rig = HandleRig(elf, lists=4, objects=12, seed='%s/hiter' % OPTIONS['seed'])
        rng = rig.rng
        walks = 0
        seen_total = 0
        described = set()
        for trial in range(scaled(1500)):
            for cell in rig.cells():
                rig.clear(cell)
            head = rig.lists[0]
            members = [rng.choice(rig.objects) for _ in range(rng.randrange(0, 10))]
            for obj in members:
                if rng.random() < 0.8:
                    rig.link(head, obj, rng.randrange(3))
                else:
                    rig.add(head, obj)
            mask = rng.choice(MASKS)
            scenario = trial % 8
            # what a walk must yield if nothing changes: the model's plain reading of the list
            expected_static = [o for o in R.HandlePool.items(head) if not (o.flags & mask)]
            it = rig.begin(head, mask)
            other = None
            visited = []
            while not it.done:
                rig.steps += 1
                obj = rig.current(it)
                visited.append(obj)
                current_node = it.prev
                if scenario == 1:                       # the body removes the node it is on
                    rig.remove(current_node)
                    described.add('removing the current node')
                elif scenario == 2:                     # the body destroys the current object
                    for cell in obj.heads:
                        rig.clear(cell)
                    described.add('clearing the current object\'s own heads')
                elif scenario == 3:                     # the body removes the node after the iterator
                    following = it.next
                    if isinstance(following, R.Node):
                        rig.remove(following)
                    described.add('removing the following node')
                elif scenario == 4:                     # new members arrive at the front and behind the current node
                    rig.link(head, rng.choice(rig.objects), 0)
                    if rng.random() < 0.5:
                        rig.insert(head, current_node, rng.choice(rig.objects))
                    described.add('adding at the front and inserting behind the current node')
                elif scenario == 5:                     # a second iterator walks the same list
                    if other is None:
                        other = rig.begin(head, rng.choice(MASKS))
                    elif not other.done and rng.random() < 0.7:
                        rig.advance(other)
                    described.add('a second iterator in the same list')
                elif scenario == 6:                     # a random other object is destroyed
                    victim = rng.choice(rig.objects)
                    for cell in victim.heads:
                        rig.clear(cell)
                    described.add('destroying a random object')
                elif scenario == 7:                     # a random node of the list is removed
                    nodes = rig.list_nodes(head)
                    if nodes:
                        rig.remove(rng.choice(nodes))
                    described.add('removing a random node')
                rig.check()
                rig.advance(it)
                if len(visited) > 200:
                    rig.bad('walk does not end')
                    break
            if scenario in (0, 5) and visited != expected_static:
                rig.bad('undisturbed walk saw %d objects, the list holds %d' % (len(visited), len(expected_static)))
            if scenario in (1, 2) and len(visited) > len(expected_static):
                rig.bad('walk with removals saw more objects than the list held')
            rig.end(it)
            if other is not None:
                rig.end(other)
            rig.check(full=trial % 200 == 0)
            walks += 1
            seen_total += len(visited)
        report(label, rig.failures, rig.steps, '%d walks (%d objects yielded) with a random skip mask while '
               'the loop body changes the list: %s; the object yielded at every step and the list after it '
               'equal the model' % (walks, seen_total, '; '.join(sorted(described))), rig.examples)


# ---------------------------------------------------------------------------------------
def find_elf(argv):
    candidates = [a for a in argv if not a.startswith('-')]
    candidates += [os.path.join(ROOT, 'SLUS_209.73'), 'SLUS_209.73']
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = []
    while argv:
        item = argv.pop(0)
        if item == '--quick':
            OPTIONS['quick'] = True
        elif item == '-v':
            OPTIONS['verbose'] = True
        elif item == '--seed' and argv:
            OPTIONS['seed'] = int(argv.pop(0))
        elif item == '-k' and argv:
            OPTIONS['filter'] = argv.pop(0)
        else:
            args.append(item)
    elf = find_elf(args)
    if elf is None:
        print('SKIP  SLUS_209.73 not found (pass its path); nothing was compared')
        return 0
    with open(elf, 'rb') as source:
        digest = hashlib.sha256(source.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('SKIP  %s is not the US v2.00 executable (sha256 %s); nothing was compared' % (elf, digest))
        return 0
    started = time.time()
    test_fpu_primitives()
    test_const_rule(elf)
    test_angles(elf)
    test_small_integer(elf)
    test_idioms(elf)
    test_math_table(elf)
    test_thresholds(elf)
    test_libm_extra(elf)
    test_softdouble(elf)
    test_noise(elf)
    test_generators(elf)
    test_pool(elf)
    test_handles(elf)
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d PASS, %d FAIL (seed %d%s, %.0f s)' % (
        len(RESULTS), len(RESULTS) - len(failed), len(failed), OPTIONS['seed'],
        ', quick' if OPTIONS['quick'] else '', time.time() - started))
    return 1 if failed else 0


def decode_immediate(emu, address):
    """The 32-bit constant built by a lui (and the ori that follows it, if any)."""
    lui, following = emu.mem.u32(address), emu.mem.u32(address + 4)
    if lui >> 26 != 0x0F:
        return None
    value = (lui & 0xFFFF) << 16
    if following >> 26 == 0x0D and (following >> 21) & 31 == (lui >> 16) & 31:
        value |= following & 0xFFFF
    return value


def test_libm_extra(elf):
    label = 'libm.immediates'
    if wanted(label):
        emu = EE(elf)
        failures, examples = 0, []
        differ = 0
        for address, value, name in R.LIBM_IMMEDIATES:
            got = decode_immediate(emu, address)
            if got != value:
                failures += 1
                examples.append('%s at 0x%x: executable %s, model %08x' % (name, address, got, value))
        report(label, failures, len(R.LIBM_IMMEDIATES), 'float constants loaded by the C library\'s code equal '
               'the published decimal constants TRUNCATED to 24 bits', examples)

    label = 'code.constants'
    if wanted(label):
        emu = EE(elf)
        failures, examples = 0, []
        table = list(R.CODE_CONSTANTS) + [(0x1509D4, R.Lcg.MULTIPLIER, 'generator multiplier'),
                                          (0x1509E0, R.Lcg.INCREMENT, 'generator increment')]
        for address, value, name in table:
            got = decode_immediate(emu, address)
            if got != value:
                failures += 1
                examples.append('%s at 0x%x: executable %s, model %08x' % (name, address, got, value))
        report(label, failures, len(table), 'constants of the engine code read back from the instruction '
               'pairs that load them (including those too small to change any tested result)', examples)

    def sweep(label, addr, model, generator, count, text, ints=False):
        if not wanted(label):
            return
        failures, total, examples = 0, 0, []
        for index, config in enumerate(FPU_CONFIGS):
            rig = Rig(elf, config)
            rng = random.Random('%s/%s/%s' % (OPTIONS['seed'], label, config))
            for _ in range(scaled(count) if index == 0 else max(scaled(count) // 8, 20)):
                args = generator(rng)
                if ints:
                    _v, f0 = rig.call(addr, [args[1]], [args[0]], max_steps=20000)
                else:
                    _v, f0 = rig.call(addr, [], args, max_steps=20000)
                want = model(*args) & M32
                total += 1
                if f0 != want:
                    failures += 1
                    if len(examples) < 3:
                        examples.append('%s %s: original %08x model %08x' % (config, hexlist(args), f0, want))
        report(label, failures, total, text, examples)
        R.set_fpu()

    def pow_args(rng):
        kind = rng.randrange(12)
        if kind == 0:                                   # the way the game uses it: growth by level
            return [raw_uniform(rng, 1.0, 2.0), R.f32(float(rng.randrange(0, 100)))]
        if kind == 1:
            return [raw_uniform(rng, 0.0, 50.0), raw_uniform(rng, -4.0, 4.0)]
        if kind == 2:                                   # the shortcut exponents
            return [gen_float(rng, 'mixed'), rng.choice((R.ONE, R.MINUS_ONE, R.TWO, R.HALF, 0, 0x80000000,
                                                         0xBF000000, 0xC0000000, 0x40400000))]
        if kind == 3:                                   # negative base: integer and non-integer exponents
            return [raw_uniform(rng, -30.0, 0.0), rng.choice((R.f32(float(rng.randrange(-40, 40))),
                                                               raw_uniform(rng, -5, 5), R.f32(rng.randrange(1 << 24, 1 << 26) * 1.0)))]
        if kind == 4:                                   # base 0 or +/-1
            return [rng.choice((0, 0x80000000, R.ONE, R.MINUS_ONE, 0x00000001, 0x007FFFFF)), gen_float(rng, 'small')]
        if kind == 5:                                   # huge exponent, base a few units from 1.0
            return [(R.ONE + rng.randrange(-12, 13)) & M32, R.f32(rng.uniform(-1, 1) * 2.0 ** rng.randrange(27, 40))]
        if kind == 6:                                   # around the overflow and underflow limits
            base = raw_uniform(rng, 1.5, 4.0)
            return [base, raw_uniform(rng, -140.0, 140.0)]
        if kind == 7:
            return [R.TWO, R.f32(rng.choice((127.0, 128.0, 128.5, 129.0, -125.0, -126.0, -126.5, -127.0))
                                 + rng.uniform(-1e-3, 1e-3))]
        if kind == 8:                                   # powers of two to small integer powers
            return [R.f32(2.0 ** rng.randrange(-20, 21)), R.f32(float(rng.randrange(-6, 7)))]
        if kind == 9:
            return [gen_float(rng, 'mixed'), gen_float(rng, 'mixed')]
        if kind == 10:
            return [rng.getrandbits(32), rng.getrandbits(32)]
        if rng.random() < 0.5:                          # patterns on the branch limits of the code
            x = rng.choice((0x3F7FFFF7, 0x3F7FFFF8, 0x3F800007, 0x3F800008, 0x3F800000 + 0x1CC471,
                            0x3F800000 + 0x1CC472, 0x3F800000 + 0x5DB3D6, 0x3F800000 + 0x5DB3D7,
                            0x40000000 + 0x1CC471, 0x3E800000 + 0x5DB3D7))
            y = rng.choice((0x4D000000, 0x4D000001, 0x4CFFFFFF, 0x4B7FFFFF, 0x4B800000, 0x4B800001,
                            0x3F7FFFFF, 0x3F800001, 0x40400000, 0x00800000, 0x007FFFFF))
            return [x ^ (rng.getrandbits(1) << 31), y ^ (rng.getrandbits(1) << 31)]
        return [raw_uniform(rng, 0.5, 1.5), raw_uniform(rng, -60.0, 60.0)]

    sweep('libm.powf', 0x3A5AC8, R.powf, pow_args, 16000,
          '0x3a5ac8 with sqrtf, scalbnf and fabsf run for real: game-like bases and levels, the shortcut '
          'exponents, negative and zero bases, huge exponents, the overflow and underflow limits, '
          'arbitrary patterns, bit for bit under all six FPU settings')

    def fmod_args(rng):
        kind = rng.randrange(8)
        if kind == 0:
            return [raw_uniform(rng, -5000, 5000), raw_uniform(rng, -50, 50)]
        if kind == 1:
            return [R.f32(float(rng.randrange(-100000, 100000))), R.f32(float(rng.randrange(1, 4000)))]
        if kind == 2:
            return [gen_float(rng, 'mixed'), rng.choice((0, 0x80000000, 1, 0x007FFFFF, R.ONE, 0x00800000))]
        if kind == 3:
            value = gen_float(rng, 'world')
            return [value, rng.choice((value, value ^ 0x80000000))]
        if kind == 4:
            return [R.f32(rng.uniform(-1, 1) * 2.0 ** rng.randrange(-120, 120)),
                    R.f32(rng.uniform(-1, 1) * 2.0 ** rng.randrange(-126, 100))]
        if kind == 5:
            return [rng.getrandbits(32), rng.getrandbits(32)]
        if kind == 6:                                   # results that end below the normal range
            return [(0x00800000 + rng.getrandbits(22)) | (rng.getrandbits(1) << 31), 0x00800000 + rng.getrandbits(20)]
        return [gen_float(rng, 'mixed'), gen_float(rng, 'mixed')]

    sweep('libm.fmodf', 0x3A5AB0, R.fmodf, fmod_args, 8000,
          '0x3a5ab0: game-sized values, whole numbers, equal magnitudes, zero divisors, far-apart '
          'exponents, arbitrary patterns, bit for bit')
    sweep('libm.sqrtf', 0x3A84C0, R.sqrtf,
          lambda rng: [rng.choice((gen_float(rng, 'mixed'), raw_uniform(rng, 0, 100000), rng.getrandbits(31),
                                   R.f32(float(rng.randrange(0, 4000)) ** 2)))],
          8000, '0x3a84c0 (integer square root, rounds to nearest): positive, negative, zero, perfect squares, '
          'arbitrary patterns, bit for bit')
    sweep('libm.scalbnf', 0x3AA810, R.scalbnf,
          lambda rng: [gen_float(rng, 'mixed'), rng.choice((rng.randrange(-300, 300), rng.randrange(-70000, 70000),
                                                             rng.randrange(-5, 6)))],
          4000, '0x3aa810: in range, past both ends of the exponent range, n above 50000, zero patterns', ints=True)
    sweep('libm.copysignf', 0x3AA920, R.copysignf,
          lambda rng: [rng.getrandbits(32), rng.getrandbits(32)], 500, '0x3aa920: arbitrary patterns')


if __name__ == '__main__':
    sys.exit(main())
