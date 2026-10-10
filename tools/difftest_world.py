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
    --no-generated / --generated-only   leave out the generated level / test nothing else
    --jobs N     test N levels side by side (separate processes; the output stays in order)

The full sample takes roughly half an hour per level in the interpreter, --quick five to
ten minutes; use --jobs on a machine with several cores.

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
# tools/ goes to the END of the path: tools/dis.py must not shadow the standard library's dis
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
from ee_emu import EE, EmuError                 # noqa: E402
import ref_world as R                           # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(_HERE)
M32 = 0xFFFFFFFF

# (adder model, multiplier bias, divide to nearest): the first gets the full sample
FPU_CONFIGS = (('ps2', False, False), ('ps2g1', False, False), ('chop', False, False),
               ('nearest', False, False), ('ps2', True, False), ('ps2', False, True))

OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False, 'alt': True,
           'generated': True, 'levels': True, 'jobs': 1}
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
        # world_collectObjectsInBox is replaced: it hands back the fake objects of `scene`
        self.scene = []                 # [(address in the interpreter, the model's object)]
        self.fake = [emu.alloc(0x60) for _ in range(6)]
        emu.stub(A_COLLECT_OBJECTS, function=self._collect_objects)
        emu.stub(A_UPDATE_GRID, ret=0)
        self.mover = self._make_mover()
        self.path = None
        self.set_fpu(FPU_CONFIGS[0])

    def _collect_objects(self, emu):
        out = emu.r[6] & M32
        self.put(out, [addr for addr, _obj in self.scene] + [0])
        return len(self.scene)

    def _make_mover(self):
        """A stand-in game object: flags +0xc, position +0x10, radius +0x1c, height +0x20,
        vertical speed +0x30, and the grid link obj_moveWithCollision re-threads inline."""
        emu = self.emu
        obj, link, node, anchor = emu.alloc(0x400), emu.alloc(0x20), emu.alloc(0x10), emu.alloc(0x10)
        emu.mem.w32(obj + 8, link)
        emu.mem.w32(link + 8, node)
        emu.mem.w32(node + 4, anchor)
        return obj

    def set_scene(self, circles):
        """Write Circle objects as fake game objects; they are what the box query returns."""
        self.scene = []
        for addr, circle in zip(self.fake, circles):
            self.put(addr, [0] * 0x18)
            self.emu.mem.w32(addr + 0xC, circle.flags)
            self.put(addr + 0x10, [circle.x, circle.y])
            self.emu.mem.w32(addr + 0x1C, circle.radius)
            self.scene.append((addr, circle))

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
    elif roll < 0.36:
        # exactly on the element's origin (or a whole number of units from it on one axis):
        # the local position is then exact and samples lie exactly on the rim of a disc
        # whose radius is a multiple of 4 - the only inputs that tell "<" from "<="
        x, y = float(e.x), float(e.y)
        if rng.random() < 0.5:
            if rng.random() < 0.5:
                x -= float(rng.randrange(0, 40))
            else:
                y -= float(rng.randrange(0, 40))
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


RUNAWAY_STEP = 150.0


class Runaway(Exception):
    """A slide one of whose steps grew past RUNAWAY_STEP units.  A sweep that starts inside
    blocking samples returns a negative time, `remain` grows, and the next step is longer;
    with a zero-length step the time is -0x7fffffff and the step after it astronomic.  The
    original walks every sample index of the step's bounding box in every element near it
    (billions of them in the worst case), which the interpreter cannot sit through, so such
    inputs are counted and left out."""


SKIPPED = {'runaway': 0}


def prop_slide(rig, level, rng, count):
    fails, examples = 0, []
    done = 0
    for _ in range(count):
        radius = gen_radius(rng)
        pos = gen_pos(rng, level, radius)
        delta = gen_delta(rng)
        mask = rng.choice(MASKS)
        try:
            hit, new_pos, normal = guarded(R.world_slide_move, level, radius, pos, delta, mask)
        except Runaway:
            SKIPPED['runaway'] += 1
            continue
        done += 1
        rig.put(rig.buf[0], pos)
        rig.put(rig.buf[1], delta)
        got_hit, _f0 = rig.call(A_SLIDE, (rig.buf[0], rig.buf[1], mask, rig.buf[2]), (radius,))
        got_pos = rig.get(rig.buf[0], 3)
        got_n = rig.get(rig.buf[2], 3)
        bad = got_hit != hit or got_pos != list(new_pos)
        if normal is not None and got_n != list(normal):
            bad = True                  # with no blocked sweep the original copies stack junk
        if bad:
            fails += 1
            examples.append('r %s pos %s delta %s mask %d: original %d %s n %s, model %d %s n %s'
                            % (fl((radius,)), fl(pos), fl(delta), mask, got_hit, hx(got_pos), hx(got_n),
                               hit, hx(new_pos), hx(normal or ())))
    return done, fails, examples


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



def guarded(function, *args):
    """Run a model function, refusing inputs on which the original would not come back
    (see Runaway)."""
    sweep = R.terrain_sweep_circle

    def watched(lvl, r, p, d, m, want_normal=True):
        if not (abs(R.to_float(d[0])) < RUNAWAY_STEP and abs(R.to_float(d[1])) < RUNAWAY_STEP):
            raise Runaway()
        return sweep(lvl, r, p, d, m, want_normal)
    R.terrain_sweep_circle = watched
    try:
        return function(*args)
    finally:
        R.terrain_sweep_circle = sweep


def prop_object_move(rig, level, rng, count):
    """obj_moveWithCollision on a stand-in object with no other object near."""
    fails, examples, done = 0, [], 0
    obj = rig.mover
    rig.scene = []
    for _ in range(count):
        radius = gen_radius(rng)
        pos = gen_pos(rng, level, radius)
        delta = gen_delta(rng)
        vel = [R.f32(R.to_float(c) * 60.0) for c in delta]
        if rng.random() < 0.15:
            vel[2] = R.f32(rng.choice((0.0, -540.0, 300.0, 0.03)))
        vz = R.f32(rng.choice((0.0, 0.0, 9.0, -9.0, -200.0, 150.0, 8.999999)))
        flags = rng.choice((0, 0x20, 0x40, 0x60, 0x10, 0x400, 0x20020, 0x840))
        try:
            new_pos, new_vz, bits = guarded(R.object_move, level, radius, pos, vel, vz, flags)
        except Runaway:
            SKIPPED['runaway'] += 1
            continue
        done += 1
        rig.emu.mem.w32(obj + 0xC, flags)
        rig.put(obj + 0x10, pos)
        rig.emu.mem.w32(obj + 0x1C, radius)
        rig.emu.mem.w32(obj + 0x20, R.f32(72.0))
        rig.emu.mem.w32(obj + 0x30, vz)
        rig.put(rig.buf[1], vel)
        got_bits, _f0 = rig.call(A_OBJ_MOVE, (obj, rig.buf[1], 0, 0))
        got_pos = rig.get(obj + 0x10, 3)
        got_vz = rig.emu.mem.u32(obj + 0x30)
        if got_bits != bits or got_pos != list(new_pos) or got_vz != new_vz:
            fails += 1
            examples.append('r %s pos %s vel %s vz %s flags %x: original %d %s vz %08x, model %d %s vz %08x'
                            % (fl((radius,)), fl(pos), fl(vel), fl((vz,)), flags, got_bits, hx(got_pos),
                               got_vz, bits, hx(new_pos), new_vz))
    return done, fails, examples


def prop_projectile(rig, level, rng, count):
    """The terrain part of obj_moveAndCollide: run from its entry to the end of the back-off."""
    fails, examples = 0, []
    obj = rig.mover
    emu = rig.emu
    for _ in range(count):
        radius = R.f32(12.0) if rng.random() < 0.6 else gen_radius(rng)
        pos = gen_pos(rng, level, radius)
        if rng.random() < 0.7:                          # mostly a little above the floor
            pos[2] = R.fadd(pos[2], R.f32(rng.uniform(0.0, 30.0)))
        speed = rng.choice((60.0, 300.0, 600.0, 1500.0))
        angle = rng.uniform(0.0, 2 * math.pi)
        vel = [R.f32(speed * math.cos(angle)), R.f32(speed * math.sin(angle)),
               R.f32(rng.choice((0.0, -200.0, -900.0, 150.0, -3000.0)))]
        rig.put(obj + 0x10, pos)
        emu.mem.w32(obj + 0x1C, radius)
        emu.mem.w8(obj + 0x50, 1)
        rig.put(rig.buf[1], vel)
        emu.r[29] = rig.sp
        emu.r[4], emu.r[5], emu.r[31] = obj, rig.buf[1], EE.RETURN_ADDR
        emu.run(start=A_PROJECTILE, until=(0x150BC8, 0x150C98), max_steps=40000000)
        got_hit = 1 if emu.pc == 0x150BC8 else 0
        got_pos = rig.get(obj + 0x10, 3)
        new_pos, hit = R.projectile_step(level, radius, pos, vel)
        if got_hit != hit or got_pos != list(new_pos):
            fails += 1
            examples.append('r %s pos %s vel %s: original %d %s, model %d %s'
                            % (fl((radius,)), fl(pos), fl(vel), got_hit, hx(got_pos), hit, hx(new_pos)))
    return count, fails, examples


def gen_ray(rng, level):
    radius = R.f32(12.0)
    origin = gen_pos(rng, level, radius)
    roll = rng.random()
    if roll < 0.7:
        origin[2] = R.fadd(origin[2], R.f32(rng.choice((0.0, 11.0, 13.0, 36.0, 60.0, 150.0))))
    roll = rng.random()
    if roll < 0.06:
        direction = [0, 0, R.f32(rng.choice((-1.0, 1.0, -50.0, 0.0)))]
        if rng.random() < 0.5:
            direction[0] = R.f32(rng.choice((0.01, 0.03, 0.039, 0.041, -0.02)))
    else:
        length = rng.choice((1.0, 1.0, 20.0, 100.0, 300.0, 300.0, 700.0)) * rng.uniform(0.3, 1.0)
        angle = rng.choice((0.0, 0.5, 1.0, 1.5)) * math.pi if roll < 0.2 else rng.uniform(0.0, 2 * math.pi)
        dx, dy = length * math.cos(angle), length * math.sin(angle)
        if roll < 0.2:
            dx, dy = round(dx, 5) + 0.0, round(dy, 5) + 0.0
        slope = rng.choice((0.0, 0.0, 0.0, -0.05, 0.05, -0.3, 0.3, -1.5, 1.0))
        direction = [R.f32(dx), R.f32(dy), R.f32(slope * length)]
    reach = math.hypot(R.to_float(direction[0]), R.to_float(direction[1]))
    roll = rng.random()
    if roll < 0.04:
        max_t = R.f32(rng.choice((0.0, -1.0)))
    elif reach > 0.05:                                  # a few very long rays only
        max_t = R.f32(rng.choice((0.5, 1.0, 1.0, 1.1, 2.0, 400.0 / reach, 900.0 / reach)))
        if roll > 0.97:
            max_t = R.f32(1200.0)
    else:
        max_t = R.f32(rng.choice((1.0, 500.0)))
    return origin, direction, max_t


RAY_FLAGS = (0, 3, 0, 3, 0, 3, 1, 2, 4, 15)


def prop_raycast(rig, level, rng, count):
    fails, examples = 0, []
    for _ in range(count):
        origin, direction, max_t = gen_ray(rng, level)
        flags = rng.choice(RAY_FLAGS)
        rig.put(rig.buf[0], origin)
        rig.put(rig.buf[1], direction)
        _v0, got = rig.call(A_RAYCAST, (rig.base, rig.buf[0], rig.buf[1], flags), (max_t,),
                            max_steps=400000000)
        want = R.terrain_raycast(level, max_t, origin, direction, flags)
        if got != want:
            fails += 1
            examples.append('maxT %s origin %s dir %s flags %d: original %08x (%g), model %08x (%g)'
                            % (fl((max_t,)), fl(origin), fl(direction), flags, got, R.to_float(got),
                               want, R.to_float(want)))
    return count, fails, examples


def prop_world_raycast(rig, level, rng, count):
    """world_raycast with the box query replaced by a list of stand-in objects."""
    fails, examples = 0, []
    for _ in range(count):
        origin, direction, max_t = gen_ray(rng, level)
        flags = rng.choice(RAY_FLAGS)
        circles = []
        for _ in range(rng.choice((0, 0, 1, 2, 4))):
            along = rng.uniform(-0.3, 1.3)
            side = rng.uniform(-40.0, 40.0)
            dx, dy = R.to_float(direction[0]), R.to_float(direction[1])
            norm = math.hypot(dx, dy) or 1.0
            cx = R.to_float(origin[0]) + dx * along - dy / norm * side
            cy = R.to_float(origin[1]) + dy * along + dx / norm * side
            circles.append(R.Circle(rng.choice((0, 0, 0x20, 0x40, 1, 4, 0x40000, 0x40001, 0x40004)),
                                    R.f32(cx), R.f32(cy), R.f32(rng.choice((12.0, 24.0, 40.0, 0.0)))))
        rig.set_scene(circles)
        ignore = rng.randrange(len(circles)) if circles and rng.random() < 0.3 else None
        include = rng.choice((0, 0, 1))
        rig.put(rig.buf[0], origin)
        rig.put(rig.buf[1], direction)
        rig.put(rig.buf[2], [0x55555555])
        out = rig.buf[2] if rng.random() < 0.8 else 0
        _v0, got = rig.call(A_WORLD_RAYCAST, (rig.base, rig.buf[0], rig.buf[1],
                                              rig.scene[ignore][0] if ignore is not None else 0,
                                              out, flags, include), (max_t,), max_steps=400000000)
        got_obj = rig.emu.mem.u32(rig.buf[2])
        want, hit = R.world_raycast(level, max_t, origin, direction, flags,
                                    lambda lo, hi: circles,
                                    circles[ignore] if ignore is not None else None, bool(include))
        want_obj = 0x55555555
        if out and not R.fle(max_t, R.ZERO):
            want_obj = 0 if hit is None else [a for a, c in rig.scene if c is hit][0]
        if got != want or got_obj != want_obj:
            fails += 1
            examples.append('maxT %s origin %s dir %s flags %d, %d objects: original %08x obj %x, model %08x obj %x'
                            % (fl((max_t,)), fl(origin), fl(direction), flags, len(circles), got, got_obj,
                               want, want_obj))
    rig.scene = []
    return count, fails, examples


# ---------------------------------------------------------------------------------------
# Path finding
# ---------------------------------------------------------------------------------------
class Requester(R.Circle):
    """The model's requester: a stand-in object the result is delivered to."""

    def __init__(self, log, index):
        R.Circle.__init__(self, 0x20, 0, 0, R.f32(24.0), 'requester %d' % index)
        self.log, self.index = log, index

    def __call__(self, result):
        self.log.append((self.index, result))


class PathRig:
    """Path-finder state on both sides: the game's globals and queue, the model's PathFinder."""
    OUT_PAIRS = 48

    def __init__(self, rig, level):
        emu = rig.emu
        self.rig, self.level = rig, level
        self.model_log, self.game_log = [], []
        self.callback = emu.alloc(16)
        emu.stub(self.callback, function=self._on_result)
        vtable = emu.alloc(0x80)
        emu.mem.w32(vtable + 0x3C, self.callback)       # slot 7: {s16 this-adjust, function}
        self.objects, self.handles, self.requesters = [], {}, []
        for index in range(4):
            obj = emu.alloc(0x60)
            emu.mem.w32(obj + 0x48, vtable)
            emu.mem.w32(obj + 0xC, 0x20)
            emu.mem.w32(obj + 0x1C, R.f32(24.0))
            handle = emu.alloc(0x10)
            emu.mem.w32(handle + 0xC, obj)
            self.objects.append(obj)
            self.handles[obj] = handle
            self.requesters.append(Requester(self.model_log, index))
        emu.stub(A_HANDLE_LINK, function=lambda e: e.mem.w32(e.r[4] & M32, self.handles[e.r[5] & M32]) or 0)
        emu.stub(A_HANDLE_REMOVE, ret=0)
        self.out = [emu.alloc(8 * self.OUT_PAIRS) for _ in range(4)]
        emu.mem.map(T0_ADDR, 16)
        self.timer_values = None
        emu.hook(0x184324, self._feed_timer)            # T0 read in path_search
        emu.hook(0x184DF0, self._feed_timer)            # T0 read in path_service
        self.model_timer = None
        self.finder = R.PathFinder(level, objects=lambda lo, hi: [c for _a, c in rig.scene])
        for addr in (G_PATH_READ, G_PATH_WRITE, G_PATH_BUSY, G_PATH_PREV, G_PATH_ITER, G_PATH_ROUND):
            emu.mem.w32(addr, 0)
        emu.mem.w8(G_PATH_ENABLED, 1)
        self.nodes = [i for i, cell in enumerate(level.path_cells) if cell & 0xFF]

    def _on_result(self, emu):
        self.game_log.append((self.objects.index(emu.r[4] & M32), emu.r[5] & M32))
        return 0

    def _feed_timer(self, emu):
        emu.mem.w32(T0_ADDR, next(self.timer_values))

    def set_timer(self, values):
        """The same sequence of T0 readings for both sides."""
        values = list(values)
        self.timer_values = iter(values + [20000] * 100000)
        model = iter(values + [20000] * 100000)
        self.model_timer = lambda: next(model)

    def node_point(self, rng, node, spread=11.0):
        x, y = self.level.path_node_position(node)
        return [R.f32(x + rng.uniform(-spread, spread)), R.f32(y + rng.uniform(-spread, spread)), R.f32(0.0)]

    def request(self, kind, radius, start, goal, who, out_index, capacity):
        rig = self.rig
        rig.put(rig.buf[0], start)
        rig.put(rig.buf[1], goal)
        rig.put(self.out[out_index], [0xDEADBEEF] * (2 * self.OUT_PAIRS))
        write = rig.emu.mem.u32(G_PATH_WRITE)
        rig.call(A_PATH_REQUEST[kind], (rig.base, rig.buf[0], rig.buf[1], self.objects[who],
                                         self.out[out_index], capacity), (radius,))
        entry = self.finder.request(kind, radius, start, goal, self.requesters[who], capacity)
        return entry, write

    def state_matches(self):
        """The search globals and the queue indexes on both sides; '' when equal."""
        mem, finder = self.rig.emu.mem, self.finder
        got = [mem.u32(G_PATH_READ), mem.u32(G_PATH_WRITE), mem.u32(G_PATH_BUSY), mem.u32(G_PATH_PREV),
               mem.u32(G_PATH_ITER), mem.u32(G_PATH_ROUND)] + self.rig.get(G_PATH_COUNTS, 4)
        want = [finder.read, finder.write, int(finder.busy), finder.prev_start, finder.iterations,
                finder.round] + list(finder.counts)
        if got != want:
            return 'read/write/busy/prevStart/rounds/round/counts: original %s, model %s' % (got, want)
        if self.game_log != self.model_log:
            return 'results delivered: original %s, model %s' % (self.game_log[-4:], self.model_log[-4:])
        return ''

    def cells_match(self):
        cells = self.level.path_cells
        got = self.rig.get(self.rig.cells, len(cells))
        if got != cells:
            index = next(i for i in range(len(cells)) if got[i] != cells[i])
            return 'path grid differs at node %d: original %08x, model %08x' % (index, got[index], cells[index])
        return ''

    def out_matches(self, out_index, entry):
        got = self.rig.get(self.out[out_index], 2 * self.OUT_PAIRS)
        want = [0xDEADBEEF] * (2 * self.OUT_PAIRS)
        if entry is not None and entry.path is not None:
            flat = [c & M32 for point in entry.path for c in point]
            want[:len(flat)] = flat
        if got != want:
            pairs = [(R.s32(got[i]), R.s32(got[i + 1])) for i in range(0, 12, 2)]
            return 'path buffer: original %s..., model %s' % (pairs, entry.path if entry else None)
        return ''


def path_rig(rig, level):
    if rig.path is None:
        rig.path = PathRig(rig, level)
    return rig.path


def gen_path_case(ctx, rng, kind):
    level = ctx.level
    start_node = rng.choice(ctx.nodes)
    start = ctx.node_point(rng, start_node)
    start[2] = R.f32(R.to_float(R.terrain_height(level, R.f32(12.0), start)) if rng.random() < 0.8 else 0.0)
    if R.to_float(start[2]) < -99999.0:
        start[2] = R.f32(0.0)
    reach = rng.choice((3, 6, 12, 25, 45)) if kind == 0 else rng.choice((2, 4, 8))
    col, row = start_node % level.pg_w, start_node // level.pg_w
    for _ in range(30):
        c2, r2 = col + rng.randrange(-reach, reach + 1), row + rng.randrange(-reach, reach + 1)
        if 0 <= c2 < level.pg_w and 0 <= r2 < level.pg_h and (level.path_cells[r2 * level.pg_w + c2] & 0xFF
                                                              or rng.random() < 0.1):
            break
    else:
        c2, r2 = col, row
    goal = ctx.node_point(rng, r2 * level.pg_w + c2, 30.0)
    if kind == 0:
        radius = R.f32(rng.choice((0.0, 0.0, 12.0, 24.0, 30.0, 60.0, 100.0)))
    else:
        radius = R.f32(rng.choice((36.0, 60.0, 100.0, 150.0, 600.0)))
    return start, goal, radius


def prop_path_search(kinds, timed):
    def run(rig, level, rng, count):
        if not level.pg_w or not level.path_cells:
            return 0, 0, []
        ctx = path_rig(rig, level)
        if not ctx.nodes:
            return 0, 0, []
        fails, examples = 0, []
        rig.scene = []
        for case in range(count):
            kind = rng.choice(kinds)
            start, goal, radius = gen_path_case(ctx, rng, kind)
            capacity = rng.choice((16, 16, 16, 16, 2, 5, 1, 40))
            who = rng.randrange(4)
            special = rng.random()
            if special < 0.04:                           # a start off the grid
                start[0] = R.f32(R.to_float(start[0]) + rng.choice((-1, 1)) * 24.0 * (level.pg_w + 3))
            before = (list(level.path_cells), )
            entry, slot = ctx.request(kind, radius, start, goal, who, 0, capacity)
            if special > 0.97 and entry is not None:     # the requester is deleted while waiting
                rig.emu.mem.w32(G_PATH_QUEUE + slot * 0x30 + 0x28, 0)
                entry.requester = None
            problem = ''
            if timed:
                # T0 climbs by a random amount per reading; a service call ends at 9000,
                # a search suspends from 7513; the next call starts a new frame
                for _frame in range(4000):
                    base, step = rng.randrange(0, 7000), rng.choice((40, 150, 400, 900))
                    ctx.set_timer([base + step * i for i in range(400)])
                    rig.call(A_PATH_SERVICE, (0,), max_steps=400000000)
                    ctx.finder.service(False, ctx.model_timer)
                    problem = ctx.state_matches()
                    if problem or not ctx.finder.busy and ctx.finder.read == ctx.finder.write:
                        break
            else:
                rig.call(A_PATH_SERVICE, (1,), max_steps=2000000000)
                ctx.finder.service(True)
                problem = ctx.state_matches()
            problem = problem or ctx.out_matches(0, entry)
            if not problem and (len(level.path_cells) < 40000 or case % 8 == 0):
                problem = ctx.cells_match()
            if not problem and timed and entry is not None and entry.requester is not None:
                # the same request answered in one blocking call, from the same grid state
                twin_level = R.Level()
                twin_level.pg_x0, twin_level.pg_y0 = level.pg_x0, level.pg_y0
                twin_level.pg_w, twin_level.pg_h = level.pg_w, level.pg_h
                twin_level.path_cells = [c & 0xFFFF00FF for c in before[0]]
                twin = R.PathFinder(twin_level)
                log = []
                twin_entry = twin.request(kind, radius, start, goal, log.append, capacity)
                twin.service(True)
                if twin_entry.path != entry.path or twin_entry.result != entry.result:
                    problem = 'suspended search gave %s, the same search in one call %s' % (entry.path,
                                                                                         twin_entry.path)
            if problem:
                fails += 1
                examples.append('type %d radius %s start %s goal %s capacity %d: %s'
                                % (kind, fl((radius,)), fl(start), fl(goal), capacity, problem))
                if 'original' in problem and ('grid' in problem or 'read/write' in problem):
                    break                               # the two sides are out of step for good
        return count, fails, examples
    return run


def prop_path_queue(rig, level, rng, count):
    """Queue behaviour: many requests at once, a full queue, the disabled switch."""
    if not level.pg_w or not level.path_cells:
        return 0, 0, []
    ctx = path_rig(rig, level)
    if not ctx.nodes:
        return 0, 0, []
    fails, examples, cases = 0, [], 0
    for batch in (5, 140, 3):
        entries = []
        for index in range(batch):
            kind = 0
            start, goal, radius = gen_path_case(ctx, rng, kind)
            entry, slot = ctx.request(kind, radius, start, goal, index % 4, index % 4, 16)
            got = rig.get(G_PATH_QUEUE + slot * 0x30, 12)
            if entry is not None:
                want = [rig.base] + list(entry.start) + list(entry.goal) + [entry.radius, ctx.out[index % 4], 16,
                                                                           ctx.handles[ctx.objects[index % 4]], 0]
                if got != want:
                    fails += 1
                    examples.append('queue entry %d: original %s, model %s' % (slot, hx(got), hx(want)))
            entries.append(entry)
            cases += 1
        problem = ctx.state_matches()
        if batch == 3:                                   # with the path finder switched off
            rig.emu.mem.w8(G_PATH_ENABLED, 0)
            ctx.finder.enabled = False
        ctx.set_timer([20000] * 10)
        rig.call(A_PATH_SERVICE, (0 if batch == 3 else 1,), max_steps=2000000000)
        ctx.finder.service(batch != 3, ctx.model_timer)
        rig.emu.mem.w8(G_PATH_ENABLED, 1)
        ctx.finder.enabled = True
        problem = problem or ctx.state_matches() or ctx.cells_match()
        if problem:
            fails += 1
            examples.append('batch of %d: %s' % (batch, problem))
            break
    return cases, fails, examples


def prop_path_block(rig, level, rng, count):
    """The block counters: 0x18b6c0 and 0x18b584 over random rectangles."""
    if not level.pg_w or not level.path_cells or level.pg_w < 16 or level.pg_h < 16:
        return 0, 0, []
    ctx = path_rig(rig, level)
    fails, examples = 0, []
    placed = []
    for case in range(count):
        if placed and rng.random() < 0.45:
            radius, pos = placed.pop(rng.randrange(len(placed)))
            addr, model = A_PATH_UNBLOCK, R.path_unblock_nodes
        else:
            radius = R.f32(rng.choice((12.0, 24.0, 24.0, 40.0, 5.0, 0.0)))
            col = rng.randrange(6, level.pg_w - 6)
            row = rng.randrange(6, level.pg_h - 6)
            x, y = level.path_node_position(row * level.pg_w + col)
            pos = [R.f32(x + rng.uniform(-12, 12)), R.f32(y + rng.uniform(-12, 12)), R.f32(0.0)]
            if rng.random() < 0.2:
                pos = [R.f32(float(x)), R.f32(float(y)), R.f32(0.0)]
            addr, model = A_PATH_BLOCK, R.path_block_nodes
            placed.append((radius, pos))
            if rng.random() < 0.1:
                placed.append((radius, pos))            # one that will be released twice
        rig.put(rig.buf[0], pos)
        rig.call(addr, (rig.base, rig.buf[0]), (radius,))
        model(level, radius, pos)
        if case % 4 == 3 or len(level.path_cells) < 40000:
            problem = ctx.cells_match()
            if problem:
                fails += 1
                examples.append('r %s pos %s: %s' % (fl((radius,)), fl(pos), problem))
                break
    return count, fails, examples


PROPERTIES = [
    # name, function, sample size, what is compared, whether it is rerun under the other FPU models
    ('libm floorf/ceilf', prop_libm, 2000, 'result bit for bit', True),
    ('terrain_collectElements', prop_collect, 1000, 'the element list, in order, with its limit', True),
    ('terrain_height', _prop_height(A_HEIGHT, R.terrain_height), 3000, 'height bit for bit', True),
    ('terrain_heightBelow', _prop_height(A_HEIGHT_BELOW, R.terrain_height_below), 3000,
     'height bit for bit', True),
    ('terrain_heightAtPoint', prop_height_point, 1500, 'height bit for bit', True),
    ('terrain_testFlag1', prop_test_flag1, 2000, 'the float result bit for bit', True),
    ('terrain_sweepCircle', prop_sweep, 3000, 'time and normal bit for bit; inputs untouched', True),
    ('world_slideMove', prop_slide, 1200, 'hit flag, end position and normal bit for bit', True),
    ('moving pieces', prop_pieces, 400, 'height and sweep after the game\'s own setters', False),
    ('obj_moveWithCollision', prop_object_move, 1200,
     'result bits, position and vertical speed, no other object near', True),
    ('obj_moveAndCollide terrain part', prop_projectile, 1000, 'hit flag and position bit for bit', True),
    ('terrain_raycast', prop_raycast, 2000, 'hit parameter bit for bit', True),
    ('world_raycast', prop_world_raycast, 1000, 'hit parameter and hit object, stand-in objects', True),
    ('path block counters', prop_path_block, 120, 'the whole node grid after each call', False),
    ('path queue', prop_path_queue, 1, 'queue entries, a full queue, the disabled switch', False),
    ('path search type 0', prop_path_search((0,), False), 300,
     'result, path buffer, node marks, search globals', True),
    ('path search suspended', prop_path_search((0,), True), 60,
     'the same after every timed service call; equals the one-call search', False),
    ('path search types 1-3', prop_path_search((1, 2, 3), False), 24,
     'result, path buffer, node marks (ray goal tests)', False),
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


def read_level(path):
    if path is None:
        return generated_level(OPTIONS['seed'])
    with open(path, 'rb') as source:
        return source.read()


def level_job(job):
    """One level in a worker process: its output as text, its results, its skipped count."""
    import contextlib
    import io
    elf, name, path, options = job
    OPTIONS.update(options)
    del RESULTS[:]
    SKIPPED['runaway'] = 0
    text = io.StringIO()
    with contextlib.redirect_stdout(text):
        run_level(elf, name, read_level(path))
    return text.getvalue(), list(RESULTS), SKIPPED['runaway']


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
        elif arg == '--no-generated':
            OPTIONS['generated'] = False
        elif arg == '--generated-only':
            OPTIONS['levels'] = False
        elif arg == '--jobs':
            OPTIONS['jobs'] = max(int(args.pop(0)), 1)
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
    tasks = []
    if OPTIONS['generated']:
        tasks.append(('generated', None))
    if not OPTIONS['levels']:
        worlds = []
    elif not worlds:
        print('SKIP  no level files (pass .world files unpacked from your own disc)')
    for path in worlds:
        if not os.path.isfile(path):
            print('SKIP  %s: no such file' % path)
            continue
        tasks.append((os.path.basename(path)[:-len('.world')], path))
    jobs = [(elf, name, path, dict(OPTIONS)) for name, path in tasks]
    if OPTIONS['jobs'] > 1 and len(jobs) > 1:
        import concurrent.futures
        with concurrent.futures.ProcessPoolExecutor(max_workers=OPTIONS['jobs']) as pool:
            for text, results, skipped in pool.map(level_job, jobs):
                sys.stdout.write(text)
                sys.stdout.flush()
                RESULTS.extend(results)
                SKIPPED['runaway'] += skipped
    else:
        for elf_path, name, path, _options in jobs:
            run_level(elf_path, name, read_level(path))
    failed = [name for name, ok in RESULTS if not ok]
    if SKIPPED['runaway']:
        print('note  %d slide inputs left out: the step grows without bound and the original '
              'does not return (see Runaway)' % SKIPPED['runaway'])
    print('%d properties, %d failed, %.0f s' % (len(RESULTS), len(failed), time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
