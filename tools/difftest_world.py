#!/usr/bin/env python3
"""difftest_world.py - compare tools/ref_world.py with the game's own machine code.

Needs your own SLUS_209.73 (US v2.00) and, for most properties, level files from your own
disc.  Without the executable the script says so and exits 0.

  python3 tools/difftest_world.py [SLUS_209.73] [LEVEL.world ...] [options]

    LEVEL.world  level files to test on (unpack them with tools/gob.py).  With none given,
                 the ones under extracted/*/*.lmp/ are used; with none there either, only
                 the generated level is tested and the rest is reported as skipped
    --quick      a tenth of the random samples
    --seed N     seed of the random inputs (default 20973); a seed repeats exactly
    -k TEXT      run only the properties whose name contains TEXT
    -v           print up to three failing inputs per property
    --no-alt     skip the reruns under the other floating-point models

Every property prints one line per level: PASS or FAIL, the name, the number of cases and
what was compared.  Exit status 1 when any property fails.

How a property is tested
    The level file is copied into the memory of tools/ee_emu.py (an instruction
    interpreter, not a console) and the game's own world_fixup 0x181d30 is run on it, with
    its disc, texture, light, emitter and automap callees stubbed; g_world is pointed at
    it.  The ORIGINAL query function is then executed on inputs this script writes into the
    interpreter's memory; the same inputs go through the model, which parsed the same file
    with tools/world_info.py; every output word must be equal.  Floats are compared as
    32-bit patterns, so "bit for bit" means: identical under the interpreter's
    floating-point model.  The default model ('ps2') gets the full sample; a tenth of it is
    repeated under the three other adder models and with the multiplier-bias and
    divide-rounding switches, the model switched the same way.  Agreement under all six
    shows the model does the same operations in the same order; it does not show that
    either matches a console in the last bit (docs/issues/dynamic-tests.md).

    A generated level (random rotated and mirrored elements, all four sample flag bits,
    moving pieces, a random path grid) is always tested as well: it needs no disc file and
    reaches cases the shipped levels do not have (flag bits 4 and 8, element flag 4 clear
    over flagged samples).
"""
import glob
import hashlib
import math
import os
import random
import struct
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
from ee_emu import EE, EmuError                 # noqa: E402
import ref_world as R                           # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(_HERE)
M32 = 0xFFFFFFFF

# (adder model, multiplier bias, divide to nearest): the first gets the full sample
FPU_CONFIGS = (('ps2', False, False), ('ps2g1', False, False), ('chop', False, False),
               ('nearest', False, False), ('ps2', True, False), ('ps2', False, True))

OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False, 'alt': True}
RESULTS = []

# addresses
A_FIXUP = 0x181D30
A_COLLECT = 0x183248
A_HEIGHT = 0x183820
A_HEIGHT_BELOW = 0x1834A8
A_HEIGHT_POINT = 0x182F28
A_TEST_FLAG1 = 0x183B48
A_SWEEP = 0x185A40
A_SLIDE = 0x14D238
A_RAYCAST = 0x18A5C0
A_WORLD_RAYCAST = 0x18AD94
A_COLLECT_OBJECTS = 0x14A928
A_OBJ_MOVE = 0x14D4B8
A_PROJECTILE = 0x1509F8
A_UPDATE_GRID = 0x14F028
A_SET_PIECE = 0x182B00
A_SET_PIECE_HEIGHT = 0x182BB4
A_GET_PIECE_HEIGHT = 0x182B74
A_FLOORF = 0x3A57E8
A_CEILF = 0x3A5710
A_PATH_SEARCH = 0x183E40
A_PATH_SERVICE = 0x184798
A_PATH_REQUEST = (0x184E38, 0x184FC8, 0x185148, 0x1852C8)
A_PATH_BLOCK = 0x18B6C0
A_PATH_UNBLOCK = 0x18B584
A_HANDLE_LINK = 0x1A1738
A_HANDLE_REMOVE = 0x1A1868
G_WORLD = 0x44FDC8
G_STAMP = 0x44F08C
G_PATH_ENABLED = 0x44F090
G_PATH_ITER = 0x44F094
G_PATH_PREV = 0x44F098
G_PATH_WRITE = 0x44F09C
G_PATH_READ = 0x44F0A0
G_PATH_BUSY = 0x44F0A4
G_PATH_QUEUE = 0x7D43A8
G_PATH_COUNTS = 0x7D89B0
G_PATH_ROUND = 0x7D89C0
G_PATH_RINGS = 0x7D69B0
T0_ADDR = 0x10000000


def wanted(name):
    return OPTIONS['filter'] is None or OPTIONS['filter'].lower() in name.lower()


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-40s %7d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:3]:
            print('        ' + line)
    sys.stdout.flush()


def scaled(count):
    return max(count // 10, 12) if OPTIONS['quick'] else count


def hx(values):
    return '(' + ' '.join('%08x' % (v & M32) for v in values) + ')'


def fl(values):
    return '(' + ', '.join('%.6g' % R.to_float(v) for v in values) + ')'


# ---------------------------------------------------------------------------------------
# The original, with a level loaded
# ---------------------------------------------------------------------------------------
class Rig:
    """One interpreter with one level set up the way the game sets it up."""

    def __init__(self, elf, data):
        emu = self.emu = EE(elf)
        emu.record_calls = False
        emu.record_writes = False
        self.sp = emu.r[29]
        for addr in (0x3B7EF0,          # sprintf: the "<level>.tex" name
                     0x14A4F0,          # light_unlink
                     0x195318, 0x18F118,    # emitter description compare / set-up
                     0x179E10,          # tex_relocate (automap tile texture)
                     0x168894):         # automap_loadGrid
            emu.stub(addr, ret=0)
        emu.stub(0x172AD0, function=lambda e: e.mem.write(e.r[5] & M32, bytes(0x40)) or 0)   # cd_readBlocking
        self.base = emu.alloc(len(data) + 0x40, align=0x40)
        emu.mem.write(self.base, data)
        self.call(A_FIXUP, (self.base,), max_steps=200000000)
        emu.mem.w32(G_WORLD, self.base)
        self.elements = emu.mem.u32(self.base + 0x20)
        self.cells = emu.mem.u32(self.base + 0x38)
        self.buf = [emu.alloc(0x40) for _ in range(8)]
        self.big = emu.alloc(0x1000)
        self.set_fpu(FPU_CONFIGS[0])

    def set_fpu(self, config):
        model, bias, nearest = config
        self.emu.fpu_model = model
        self.emu.fpu_mul_bias = bias
        self.emu.fpu_div_nearest = nearest
        R.set_fpu(model, bias, nearest)

    def call(self, addr, ints=(), floats=(), max_steps=40000000):
        emu = self.emu
        emu.r[29] = self.sp
        for index, raw in enumerate(floats):
            emu.f[12 + index] = raw & M32
        value = emu.call(addr, *ints, max_steps=max_steps)
        return value & M32, emu.f[0]

    def put(self, addr, words):
        self.emu.mem.write(addr, struct.pack('<%dI' % len(words), *[w & M32 for w in words]))

    def get(self, addr, count):
        return list(struct.unpack('<%dI' % count, self.emu.mem.read(addr, count * 4)))


# ---------------------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------------------
RADII = (0.0, 1.0, 4.0, 8.0, 12.0, 12.0, 12.0, 16.0, 24.0, 24.0, 30.0, 36.0, 48.0, 72.0)


def gen_radius(rng):
    if rng.random() < 0.75:
        return R.f32(rng.choice(RADII))
    return R.f32(rng.uniform(0.0, 60.0))


def gen_xy(rng, level):
    """A point on or near the terrain; a quarter of them on whole or 4-unit coordinates,
    where a sample lies exactly on the rim of a disc or on the line of a sweep."""
    e = rng.choice(level.elements)
    x = rng.uniform(e.min_x - 20, e.max_x + 20)
    y = rng.uniform(e.min_y - 20, e.max_y + 20)
    roll = rng.random()
    if roll < 0.12:
        x, y = float(round(x / 4.0) * 4), float(round(y / 4.0) * 4)
    elif roll < 0.22:
        x, y = float(round(x)), float(round(y))
    elif roll < 0.27:
        x = float(round(x / 160.0) * 160) + rng.choice((0.0, -0.001, 0.001))
    elif roll < 0.30:
        x, y = rng.uniform(-20000, 20000), rng.uniform(-20000, 20000)
    return R.f32(x), R.f32(y)


def gen_pos(rng, level, radius):
    """A position whose height is usually near the floor under it."""
    x, y = gen_xy(rng, level)
    floor = R.to_float(R.terrain_height(level, radius, (x, y, 0)))
    roll = rng.random()
    if floor < -99999.0:
        z = rng.uniform(-200.0, 300.0)
    elif roll < 0.35:
        z = floor
    elif roll < 0.6:
        z = floor + rng.choice((-12.0, -11.0, -1.0, 0.5, 1.0, 11.0, 12.0, 13.0, 0.25, -0.25))
    elif roll < 0.85:
        z = floor + rng.uniform(-20.0, 20.0)
    else:
        z = rng.uniform(-500.0, 800.0)
    return [x, y, R.f32(z)]


def gen_delta(rng):
    roll = rng.random()
    if roll < 0.04:
        dx = dy = 0.0
    else:
        length = rng.choice((0.001, 0.05, 0.6, 1.5, 4.0, 4.0, 12.0, 30.0, 60.0, 120.0, 300.0)) * rng.uniform(0.2, 1.0)
        angle = rng.choice((0.0, 0.5, 1.0, 1.5)) * math.pi if roll < 0.2 else rng.uniform(0.0, 2 * math.pi)
        dx, dy = length * math.cos(angle), length * math.sin(angle)
        if roll < 0.2:
            dx, dy = round(dx, 6) + 0.0, round(dy, 6) + 0.0
    roll = rng.random()
    dz = 0.0 if roll < 0.6 else rng.uniform(-3.0, 3.0) if roll < 0.9 else rng.uniform(-40.0, 40.0)
    return [R.f32(dx), R.f32(dy), R.f32(dz)]


MASKS = (1, 3, 5, 1, 3, 5, 0, 2, 4, 7, 8, 15)


# ---------------------------------------------------------------------------------------
# Properties.  Each takes (rig, level, rng, count) and returns (cases, failures, examples).
# ---------------------------------------------------------------------------------------
def prop_collect(rig, level, rng, count):
    fails, examples = 0, []
    for _ in range(count):
        x, y = gen_xy(rng, level)
        w = R.f32(rng.choice((0.0, 3.0, 12.0, 40.0, 150.0, 400.0)) * rng.random())
        h = R.f32(rng.choice((0.0, 3.0, 12.0, 40.0, 150.0, 400.0)) * rng.random())
        box = (R.fsub(x, w), R.fsub(y, h), R.fadd(x, w), R.fadd(y, h))
        limit = rng.choice((64, 256, 256, 2, 3, 5, 9))
        stamp = (rig.emu.mem.u32(G_STAMP) + 1) & M32
        rig.emu.mem.w32(G_STAMP, stamp)
        rig.put(rig.big, [0xDEADBEEF] * (limit + 1))
        rig.call(A_COLLECT, (rig.base, rig.big, limit), box)
        got = []
        for word in rig.get(rig.big, limit + 1):
            if word == 0:
                break
            got.append((word - rig.elements) // 0x24 if word != 0xDEADBEEF else -1)
        level.stamp = (level.stamp + 1) & M32
        want = [e.index for e in R.collect_elements(level, box[0], box[1], box[2], box[3], limit)]
        if got != want:
            fails += 1
            examples.append('box %s limit %d: original %s, model %s' % (fl(box), limit, got[:12], want[:12]))
    return count, fails, examples


def _prop_height(addr, model):
    def run(rig, level, rng, count):
        fails, examples = 0, []
        for _ in range(count):
            radius = gen_radius(rng)
            pos = gen_pos(rng, level, radius)
            rig.put(rig.buf[0], pos)
            _v0, got = rig.call(addr, (rig.base, rig.buf[0]), (radius,))
            want = model(level, radius, pos)
            if got != want:
                fails += 1
                examples.append('r %s pos %s: original %08x (%g), model %08x (%g)'
                                % (fl((radius,)), fl(pos), got, R.to_float(got), want, R.to_float(want)))
        return count, fails, examples
    return run


def prop_height_point(rig, level, rng, count):
    fails, examples = 0, []
    for _ in range(count):
        pos = gen_pos(rng, level, R.f32(4.0))
        rig.put(rig.buf[0], pos)
        _v0, got = rig.call(A_HEIGHT_POINT, (rig.base, rig.buf[0]))
        want = R.terrain_height_at_point(level, pos)
        if got != want:
            fails += 1
            examples.append('pos %s: original %08x, model %08x' % (fl(pos), got, want))
    return count, fails, examples


def prop_sweep(rig, level, rng, count):
    fails, examples = 0, []
    for _ in range(count):
        radius = gen_radius(rng)
        pos = gen_pos(rng, level, radius)
        delta = gen_delta(rng)
        mask = rng.choice(MASKS)
        want_normal = rng.random() < 0.85
        rig.put(rig.buf[0], pos)
        rig.put(rig.buf[1], delta)
        rig.put(rig.buf[2], [0x11111111, 0x22222222, 0x33333333])
        _v0, got_t = rig.call(A_SWEEP, (rig.base, rig.buf[0], rig.buf[1], mask,
                                        rig.buf[2] if want_normal else 0), (radius,))
        got_n = rig.get(rig.buf[2], 3)
        t, normal = R.terrain_sweep_circle(level, radius, pos, delta, mask, want_normal)
        want_n = list(normal) if normal is not None else [0x11111111, 0x22222222, 0x33333333]
        unchanged = rig.get(rig.buf[0], 3) == list(pos) and rig.get(rig.buf[1], 3) == list(delta)
        if got_t != t or got_n != want_n or not unchanged:
            fails += 1
            examples.append('r %s pos %s delta %s mask %d: original t %08x n %s, model t %08x n %s'
                            % (fl((radius,)), fl(pos), fl(delta), mask, got_t, hx(got_n), t, hx(want_n)))
    return count, fails, examples


def prop_slide(rig, level, rng, count):
    fails, examples = 0, []
    for _ in range(count):
        radius = gen_radius(rng)
        pos = gen_pos(rng, level, radius)
        delta = gen_delta(rng)
        mask = rng.choice(MASKS)
        rig.put(rig.buf[0], pos)
        rig.put(rig.buf[1], delta)
        got_hit, _f0 = rig.call(A_SLIDE, (rig.buf[0], rig.buf[1], mask, rig.buf[2]), (radius,))
        got_pos = rig.get(rig.buf[0], 3)
        got_n = rig.get(rig.buf[2], 3)
        hit, new_pos, normal = R.world_slide_move(level, radius, pos, delta, mask)
        bad = got_hit != hit or got_pos != list(new_pos)
        if normal is not None and got_n != list(normal):
            bad = True                  # with no blocked sweep the original copies stack junk
        if bad:
            fails += 1
            examples.append('r %s pos %s delta %s mask %d: original %d %s n %s, model %d %s n %s'
                            % (fl((radius,)), fl(pos), fl(delta), mask, got_hit, hx(got_pos), hx(got_n),
                               hit, hx(new_pos), hx(normal or ())))
    return count, fails, examples


def prop_test_flag1(rig, level, rng, count):
    fails, examples = 0, []
    for _ in range(count):
        radius = gen_radius(rng)
        pos = gen_pos(rng, level, radius)
        rig.put(rig.buf[0], pos)
        _v0, got = rig.call(A_TEST_FLAG1, (rig.base, rig.buf[0]), (radius,))
        want = R.terrain_test_flag1(level, radius, pos)
        if got != want:
            fails += 1
            examples.append('r %s pos %s: original %08x, model %08x' % (fl((radius,)), fl(pos), got, want))
    return count, fails, examples


def prop_pieces(rig, level, rng, count):
    """Doors: collision off and on, and the height offset, through the game's setters."""
    if not level.pieces:
        return 0, 0, []
    fails, examples, cases = 0, [], 0
    for _ in range(max(count // 8, 4)):
        piece = rng.randrange(len(level.pieces))
        e = level.elements[level.pieces[piece]]
        state = rng.choice((0, 1))
        rig.call(A_SET_PIECE, (rig.base, piece, state))
        level.set_piece_collision(piece, state)
        if rng.random() < 0.4:
            height = R.f32(rng.choice((float(e.z), e.z + 0.9, e.z - 20.5, e.z + 30.0)))
            rig.call(A_SET_PIECE_HEIGHT, (rig.base, piece), (height,))
            level.set_piece_height(piece, height)
        got_z, _f0 = rig.call(A_GET_PIECE_HEIGHT, (rig.base, piece))
        if R.s32(got_z) != level.get_piece_height(piece):
            fails += 1
            examples.append('piece %d height: original %d, model %d' % (piece, R.s32(got_z), e.z))
        for _ in range(8):
            cases += 1
            radius = gen_radius(rng)
            x = R.f32(rng.uniform(e.min_x - 10, e.max_x + 10))
            y = R.f32(rng.uniform(e.min_y - 10, e.max_y + 10))
            z = R.f32(R.to_float(R.terrain_height(level, radius, (x, y, 0))) + rng.uniform(-5, 5))
            pos, delta, mask = [x, y, z], gen_delta(rng), rng.choice((1, 3, 5))
            rig.put(rig.buf[0], pos)
            rig.put(rig.buf[1], delta)
            _v0, got_h = rig.call(A_HEIGHT, (rig.base, rig.buf[0]), (radius,))
            _v0, got_t = rig.call(A_SWEEP, (rig.base, rig.buf[0], rig.buf[1], mask, rig.buf[2]), (radius,))
            want_h = R.terrain_height(level, radius, pos)
            want_t, _n = R.terrain_sweep_circle(level, radius, pos, delta, mask)
            if got_h != want_h or got_t != want_t:
                fails += 1
                examples.append('piece %d collision %d pos %s delta %s: height %08x/%08x sweep %08x/%08x'
                                % (piece, state, fl(pos), fl(delta), got_h, want_h, got_t, want_t))
    for piece in range(len(level.pieces)):          # leave every door closed and solid
        rig.call(A_SET_PIECE, (rig.base, piece, 1))
        level.set_piece_collision(piece, 1)
    return cases, fails, examples


def prop_libm(rig, level, rng, count):
    fails, examples = 0, []
    edge = [0, 0x80000000, 0x3F800000, 0xBF800000, 0x3F7FFFFF, 0xBF7FFFFF, 0x3F000000, 0xBF000000,
            0x00000001, 0x80000001, 0x007FFFFF, 0x00800000, 0x4AFFFFFF, 0x4B000000, 0xCB000000,
            0x4B7FFFFF, 0x7F7FFFFF, 0x7F800000, 0xFF800000, 0x7FFFFFFF, 0xFFFFFFFF]
    for index in range(count):
        roll = rng.random()
        if index < len(edge):
            x = edge[index]
        elif roll < 0.3:
            x = rng.getrandbits(32)
        elif roll < 0.5:
            x = R.f32(float(rng.randrange(-5000, 5000)) + rng.choice((0.0, 0.5, -0.5, 0.25)))
        else:
            x = R.f32(rng.uniform(-5000.0, 5000.0))
        for addr, model, name in ((A_FLOORF, R.floorf, 'floorf'), (A_CEILF, R.ceilf, 'ceilf')):
            _v0, got = rig.call(addr, (), (x,))
            if got != model(x):
                fails += 1
                examples.append('%s(%08x): original %08x, model %08x' % (name, x, got, model(x)))
    return count * 2, fails, examples


PROPERTIES = [
    # name, function, sample size, what is compared, whether it is rerun under the other FPU models
    ('libm floorf/ceilf', prop_libm, 3000, 'result bit for bit', True),
    ('terrain_collectElements', prop_collect, 1500, 'the element list, in order, with its limit', True),
    ('terrain_height', _prop_height(A_HEIGHT, R.terrain_height), 4000, 'height bit for bit', True),
    ('terrain_heightBelow', _prop_height(A_HEIGHT_BELOW, R.terrain_height_below), 4000,
     'height bit for bit', True),
    ('terrain_heightAtPoint', prop_height_point, 2000, 'height bit for bit', True),
    ('terrain_testFlag1', prop_test_flag1, 3000, 'the float result bit for bit', True),
    ('terrain_sweepCircle', prop_sweep, 5000, 'time and normal bit for bit; inputs untouched', True),
    ('world_slideMove', prop_slide, 3000, 'hit flag, end position and normal bit for bit', True),
    ('moving pieces', prop_pieces, 400, 'height and sweep after the game\'s own setters', False),
]


# ---------------------------------------------------------------------------------------
# A generated level
# ---------------------------------------------------------------------------------------
def generated_level(seed):
    """Bytes of a small random level in the file format (ref_world.build_world_file)."""
    rng = random.Random(seed)
    fields = []
    for index in range(14):
        w, h = rng.randrange(6, 34), rng.randrange(6, 34)
        x0, y0 = rng.randrange(-20, 6), rng.randrange(-20, 6)
        level_h = rng.randrange(-30, 60)
        samples = []
        flag_rate = rng.choice((0.0, 0.05, 0.3))
        for _ in range(w * h):
            roll = rng.random()
            if roll < 0.08:
                height = -2000
            elif roll < 0.2:
                height = level_h + rng.randrange(-30, 40)
            else:
                height = level_h + rng.randrange(-3, 4)
            flags = 0
            if rng.random() < flag_rate:
                flags = rng.choice((1, 1, 1, 2, 2, 4, 8, 3, 5, 15))
            samples.append(height * 16 + flags)
        heights = [v >> 4 for v in samples]
        lo, hi = min(heights), max(heights)
        if index % 5 == 4:                              # a wrong +0x10/+0x12 pair now and then
            lo, hi = lo + rng.randrange(0, 20), hi - rng.randrange(0, 20)
        fields.append((x0, y0, w, h, samples, lo, hi))
    elements = []
    for _ in range(40):
        field = rng.randrange(len(fields))
        flagged = any(v & 15 for v in fields[field][4])
        flags = 4 if flagged and rng.random() < 0.8 else 0
        if rng.random() < 0.35:
            flags |= 1
        if rng.random() < 0.05:
            flags |= 2
        roll = rng.random()
        if roll < 0.4:
            cos, sin = rng.choice(((32767, 0), (0, 32767), (-32767, 0), (0, -32767)))
        else:
            angle = rng.uniform(0.0, 2 * math.pi)
            cos, sin = int(round(32767 * math.cos(angle))), int(round(32767 * math.sin(angle)))
        elements.append((field, flags, rng.randrange(-380, 380), rng.randrange(-380, 380),
                         rng.randrange(-40, 40), cos, sin))
    pw, ph = 36, 34
    open_node = [[rng.random() < 0.8 for _ in range(pw)] for _ in range(ph)]
    cells = []
    for row in range(ph):
        for col in range(pw):
            links = 0
            if open_node[row][col]:
                for bit, (dx, dy) in enumerate(((-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0))):
                    c2, r2 = col + dx, row + dy
                    if 0 <= c2 < pw and 0 <= r2 < ph and open_node[r2][c2] and rng.random() < 0.93:
                        links |= 1 << bit
            cells.append(links)
    return R.build_world_file((-3, -3), (6, 6), fields, elements, (-18, -17, pw, ph, cells), pieces=(3, 17))


# ---------------------------------------------------------------------------------------
def run_level(elf, name, data):
    try:
        level = R.Level(data)
    except Exception as error:                          # world_info refuses the file
        print('SKIP  %s: %s' % (name, error))
        return
    if not level.elements:
        print('SKIP  %s: no terrain elements' % name)
        return
    rig = Rig(elf, data)
    for prop_name, function, size, text, alt in PROPERTIES:
        full = '%s: %s' % (name, prop_name)
        if not wanted(full):
            continue
        seed = int(hashlib.sha256(('%d/%s' % (OPTIONS['seed'], full)).encode()).hexdigest()[:12], 16)
        rng = random.Random(seed)
        total = fails = 0
        examples = []
        configs = FPU_CONFIGS if (alt and OPTIONS['alt']) else FPU_CONFIGS[:1]
        try:
            for index, config in enumerate(configs):
                rig.set_fpu(config)
                count = scaled(size) if index == 0 else max(scaled(size) // 10, 6)
                cases, bad, lines = function(rig, level, rng, count)
                total += cases
                fails += bad
                examples += ['[%s%s%s] %s' % (config[0], ' mul-bias' if config[1] else '',
                                              ' div-nearest' if config[2] else '', line) for line in lines]
        except (EmuError, RuntimeError, IndexError) as error:
            fails += 1
            examples.append('stopped: %s' % error)
        finally:
            rig.set_fpu(FPU_CONFIGS[0])
        if total or fails:
            report(full, fails, total, text + (' (6 FPU models)' if len(configs) > 1 else ''), examples)


def main(argv):
    elf = None
    worlds = []
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == '--quick':
            OPTIONS['quick'] = True
        elif arg == '--no-alt':
            OPTIONS['alt'] = False
        elif arg == '-v':
            OPTIONS['verbose'] = True
        elif arg == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif arg == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif arg.lower().endswith('.world'):
            worlds.append(arg)
        else:
            elf = arg
    if elf is None:
        elf = os.path.join(ROOT, 'SLUS_209.73')
    if not os.path.isfile(elf):
        print('SKIP  no executable at %s (give the path to your own SLUS_209.73)' % elf)
        return 0
    with open(elf, 'rb') as source:
        digest = hashlib.sha256(source.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('SKIP  %s is not the US v2.00 executable this test was written for' % elf)
        return 0
    if not worlds:
        worlds = sorted(glob.glob(os.path.join(ROOT, 'extracted', '*', '*.lmp', '*.world')))
    started = time.time()
    run_level(elf, 'generated', generated_level(OPTIONS['seed']))
    if not worlds:
        print('SKIP  no level files (pass .world files unpacked from your own disc)')
    for path in worlds:
        if not os.path.isfile(path):
            print('SKIP  %s: no such file' % path)
            continue
        with open(path, 'rb') as source:
            data = source.read()
        run_level(elf, os.path.basename(path)[:-len('.world')], data)
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d failed, %.0f s' % (len(RESULTS), len(failed), time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
