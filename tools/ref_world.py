#!/usr/bin/env python3
"""ref_world.py - reference model of the level queries of Champions: Return to Arms
(SLUS_209.73): floor height, the blocked test, the swept circle and the slide move, the
terrain ray, and the path search.

A research tool, not game code.  Every function was written from the instruction sequence
at the address in its docstring and is compared with that code, executed under
tools/ee_emu.py on real level files, by tools/difftest_world.py.  docs/spec/world-queries.md
is the prose version and says what the comparison covers.  Standard library only, plus the
level parser tools/world_info.py; no game data is embedded.

Floats are raw 32-bit patterns
    Movement is part of the lockstep simulation, so the last bit matters, and the console's
    FPU is not IEEE 754 (no NaN, infinity or denormal; results truncated).  Every float in
    this module is an int holding the 32-bit pattern and all arithmetic goes through the
    functions of section 1, which follow the rules of the interpreter in tools/ee_emu.py
    (same four adder models, same switches).  f32() turns a Python float into a pattern,
    to_float() turns one back.  A point or vector is a sequence of three patterns (x, y, z).

Use
    level = Level.load('some.world')                 # or Level(bytes)
    h = terrain_height(level, f32(12.0), pos)        # pattern; NO_FLOOR when nothing is there
    t, n = terrain_sweep_circle(level, f32(12.0), pos, step, MASK_PLAYER)
    hit, pos, n = world_slide_move(level, f32(12.0), pos, step, MASK_CREATURE)
    paths = PathFinder(level)
    req = paths.request(0, f32(0.0), start, goal, callback)
    paths.service(blocking=True)                     # callback(1 or 0); req.path

The Level object carries the run-time state the queries share: the visit stamps of
terrain_collectElements, the "ignored" flag and height offset of terrain elements, and the
search marks and block counters in the path grid.

Sections: 1 arithmetic, 2 level data, 3 terrain elements, 4 floor height, 5 the blocked
test, 6 swept circle and slide, 7 movers, 8 rays, 9 path grid.
"""
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)          # appended: tools/dis.py must not shadow the standard dis
import world_info                                   # noqa: E402

M32 = 0xFFFFFFFF
SIGN = 0x80000000
FMAX = 0x7FFFFFFF           # what the R5900 gives on overflow and on division by zero


# =======================================================================================
# 1. Arithmetic: R5900 single precision on raw patterns
# =======================================================================================

FPU_MODELS = ('ps2', 'ps2g1', 'chop', 'nearest')
_model = 'ps2'
_mul_bias = False
_div_nearest = False
_nearest = False


def set_fpu(model='ps2', mul_bias=False, div_nearest=False):
    """Choose the arithmetic (see tools/ee_emu.py, "Floating point"): the adder model, the
    worst-case multiplier switch and the rounding of divide and square root."""
    global _model, _mul_bias, _div_nearest, _nearest
    if model not in FPU_MODELS:
        raise ValueError('model must be one of %s' % (FPU_MODELS,))
    _model, _mul_bias, _div_nearest = model, bool(mul_bias), bool(div_nearest)
    _nearest = model == 'nearest'


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def s32(x):
    x &= M32
    return x - 0x100000000 if x & SIGN else x


def f32(value):
    """Pattern of the IEEE single nearest to a Python float (for inputs; the game's own
    constants are given as patterns below)."""
    return struct.unpack('<I', struct.pack('<f', value))[0]


def to_float(raw):
    return struct.unpack('<f', struct.pack('<I', raw & M32))[0]


def _split(raw):
    exp = (raw >> 23) & 0xFF
    if exp == 0:
        return raw >> 31, 0, 0
    return raw >> 31, (raw & 0x7FFFFF) | 0x800000, exp


def _pack(sign, mag, e2, nearest):
    """Pattern of (-1)**sign * mag * 2**e2: truncated (or rounded to nearest even),
    +/-FMAX on overflow, signed zero on underflow."""
    if mag == 0:
        return sign << 31
    shift = mag.bit_length() - 24
    if shift > 0:
        m = mag >> shift
        if nearest:
            rest = mag & ((1 << shift) - 1)
            half = 1 << (shift - 1)
            if rest > half or (rest == half and m & 1):
                m += 1
                if m == 0x1000000:
                    m >>= 1
                    shift += 1
    else:
        m = mag << -shift
    exp = e2 + shift + 150
    if exp > 255:
        return (sign << 31) | FMAX
    if exp < 1:
        return sign << 31
    return (sign << 31) | (exp << 23) | (m & 0x7FFFFF)


def fadd(a, b):
    """add.s"""
    sa, ma, ea = _split(a)
    sb, mb, eb = _split(b)
    if ma == 0:
        if mb == 0:
            return (sa & sb) << 31
        return b & M32
    if mb == 0:
        return a & M32
    if _model == 'ps2':
        if ea < eb:
            a, sa, ma, ea, sb, mb, eb = b, sb, mb, eb, sa, ma, ea
        gap = ea - eb
        if gap >= 25:
            return a & M32
        total = ((-ma if sa else ma) << 6) + (((-mb if sb else mb) << 6) >> gap)
        if total == 0:
            return 0
        sign = 1 if total < 0 else 0
        mag = -total if sign else total
        shift = mag.bit_length() - 24
        if shift > 0:
            mag >>= shift
        else:
            mag <<= -shift
        exp = ea - 6 + shift
        if exp > 255:
            return (sign << 31) | FMAX
        if exp < 1:
            return sign << 31
        return (sign << 31) | (exp << 23) | (mag & 0x7FFFFF)
    if _model == 'ps2g1':
        gap = ea - eb
        if gap >= 25:
            return a & M32
        if gap <= -25:
            return b & M32
        if gap > 1:
            mb &= -1 << (gap - 1)
        elif gap < -1:
            ma &= -1 << (-gap - 1)
    low = ea if ea < eb else eb
    total = ((-ma if sa else ma) << (ea - low)) + ((-mb if sb else mb) << (eb - low))
    if total == 0:
        return 0
    if total < 0:
        return _pack(1, -total, low - 150, _nearest)
    return _pack(0, total, low - 150, _nearest)


def fsub(a, b):
    """sub.s"""
    return fadd(a, b ^ SIGN)


def fmul(a, b):
    """mul.s"""
    ea = (a >> 23) & 0xFF
    eb = (b >> 23) & 0xFF
    sign = ((a ^ b) >> 31) & 1
    if ea == 0 or eb == 0:
        return sign << 31
    product = ((a & 0x7FFFFF) | 0x800000) * ((b & 0x7FFFFF) | 0x800000)
    shift = product.bit_length() - 24               # 23 or 24
    m = product >> shift
    rest = product & ((1 << shift) - 1)
    if _nearest:
        half = 1 << (shift - 1)
        if rest > half or (rest == half and m & 1):
            m += 1
            if m == 0x1000000:
                m >>= 1
                shift += 1
    exp = ea + eb - 150 + shift
    if exp > 255:
        return (sign << 31) | FMAX
    if exp < 1:
        return sign << 31
    raw = (sign << 31) | (exp << 23) | (m & 0x7FFFFF)
    if _mul_bias and rest and (raw & FMAX) > 0x00800000:
        raw -= 1
    return raw


def fdiv(a, b):
    """div.s; a divisor of zero gives +/-FMAX"""
    sa, ma, ea = _split(a)
    sb, mb, eb = _split(b)
    sign = sa ^ sb
    if mb == 0:
        return (sign << 31) | FMAX
    if ma == 0:
        return sign << 31
    quotient, rest = divmod(ma << 40, mb)
    quotient = (quotient << 1) | (1 if rest else 0)
    return _pack(sign, quotient, ea - eb - 41, _nearest or _div_nearest)


def _isqrt(n):
    if n < 2:
        return n
    x = 1 << ((n.bit_length() + 1) // 2)
    while True:
        y = (x + n // x) >> 1
        if y >= x:
            return x
        x = y


def fsqrt(a):
    """sqrt.s: root of the magnitude"""
    sa, ma, ea = _split(a)
    if ma == 0:
        return sa << 31
    e2 = ea - 150
    if e2 & 1:
        ma <<= 1
        e2 -= 1
    wide = ma << 48
    root = _isqrt(wide)
    root = (root << 1) | (1 if root * root != wide else 0)
    return _pack(0, root, e2 // 2 - 25, _nearest or _div_nearest)


def frsqrt(a, b):
    """rsqrt.s: a / sqrt(b), as a square root followed by a division"""
    return fdiv(a, fsqrt(b))


def fneg(a):
    """neg.s: the sign bit only"""
    return (a ^ SIGN) & M32


def fabs_(a):
    """abs.s"""
    return a & FMAX


def i2f(value):
    """cvt.s.w of a signed 32-bit integer"""
    value = s32(value)
    if value == 0:
        return 0
    if value < 0:
        return _pack(1, -value, 0, _nearest)
    return _pack(0, value, 0, _nearest)


def f2i(a):
    """cvt.w.s: toward zero, saturating; returns a signed int"""
    exp = (a >> 23) & 0xFF
    if exp == 0:
        return 0
    if exp >= 158:
        return -0x80000000 if a & SIGN else 0x7FFFFFFF
    man = (a & 0x7FFFFF) | 0x800000
    mag = man << (exp - 150) if exp >= 150 else man >> (150 - exp)
    return -mag if a & SIGN else mag


def _key(a):
    return -(a & FMAX) if a & SIGN else a & FMAX


def flt(a, b):
    """c.olt.s (sign and magnitude of the patterns; +0 equals -0)"""
    return _key(a) < _key(b)


def fle(a, b):
    """c.ole.s"""
    return _key(a) <= _key(b)


def fmin(a, b):
    """min.s fd, fs=a, ft=b: a unless b is smaller"""
    return a if _key(a) <= _key(b) else b


def fmax(a, b):
    """max.s fd, fs=a, ft=b: a unless b is larger"""
    return a if _key(a) >= _key(b) else b


def floorf(x):
    """libm_floorf 0x3a57e8.  On the bits; its one FPU test ("huge + x > 0") is true for
    every value below 2**23 in size, the only ones that reach it."""
    i0 = s32(x)
    ix = x & FMAX
    j0 = (ix >> 23) - 0x7F
    if j0 >= 23:
        return x & M32
    if j0 < 0:
        if i0 >= 0:
            return 0
        if ix > 0x007FFFFF:
            return MINUS_ONE
        return x & M32
    mask = 0x007FFFFF >> j0
    if i0 & mask == 0:
        return x & M32
    if i0 < 0:
        i0 += 0x00800000 >> j0
    return (i0 & ~mask) & M32


def ceilf(x):
    """libm_ceilf 0x3a5710"""
    i0 = s32(x)
    ix = x & FMAX
    j0 = (ix >> 23) - 0x7F
    if j0 >= 23:
        return x & M32
    if j0 < 0:
        if i0 < 0:
            return SIGN
        if ix > 0x007FFFFF:
            return ONE
        return x & M32
    mask = 0x007FFFFF >> j0
    if i0 & mask == 0:
        return x & M32
    if i0 > 0:
        i0 += 0x00800000 >> j0
    return (i0 & ~mask) & M32


# Constants, as the patterns the code loads
ZERO = 0x00000000
HALF = 0x3F000000
ONE = 0x3F800000
MINUS_ONE = 0xBF800000
QUARTER = 0x3E800000            # world units -> sample units
K_INV_160 = 0x3BCCCCCC          # 1/160 truncated: world units -> terrain grid cells
K_INV_32767 = 0x38000100        # s16 cosine or sine -> float
K_INV_24 = 0x3D2AAAAA           # 1/24 truncated: world units -> path nodes
K_INV_240 = 0x3B888888          # 1/240 truncated
K_0_01 = 0x3C23D70A             # 0.01
K_MINUS_0_01 = 0xBC23D70A
K_0_001 = 0x3A83126E            # 0.001 truncated
K_0_1 = 0x3DCCCCCC              # 0.1 truncated
K_0_75 = 0x3F400000
K_0_98 = 0x3F7AE147
K_TWO = 0x40000000
K_5 = 0x40A00000
K_12 = 0x41400000               # the step height
K_24 = 0x41C00000
K_60 = 0x42700000
K_240 = 0x43700000              # ray segment length
K_1200 = 0x44960000
K_14400 = 0x46610000            # 120 squared
K_10000 = 0x461C4000
K_MINUS_10000 = 0xC61C4000
K_MINUS_100000 = 0xC7C35000     # "no object to stand on"
K_MINUS_1E7 = 0xCB189680
K_1E10 = 0x501502F9
K_1E11 = 0x51BA43B7
K_DT = 0x3C888888               # the frame time, 1/60 truncated
K_GRAVITY_STEP = 0x410FFFFF     # 8.999999: taken off the vertical speed every frame

NO_FLOOR_INT = -1000000
NO_FLOOR = 0xC9742400           # float of NO_FLOOR_INT: terrain_height when nothing is there
BLOCK_HEIGHT = 32000            # height a masked sample counts as in the sweep
STEP_HEIGHT = 12                # a sample this much above the mover's base is a wall

MASK_OBJECT = 1                 # props, push-out slides, vehicles
MASK_CREATURE = 3               # Creature_moveBy: monsters, knocked-back players
MASK_PLAYER = 5                 # a player's own step in obj_moveWithCollision
RAY_SIGHT = 0                   # terrain_raycast flags: heights only
RAY_MOVEMENT = 3                # terrain_raycast flags of the monster movement probes


# =======================================================================================
# 2. Level data
# =======================================================================================

class HeightField:
    """Shared grid of samples: sample = height * 16 + flags."""
    __slots__ = ('x0', 'y0', 'w', 'h', 'lo', 'hi', 'samples', 'offset')

    def __init__(self, x0, y0, w, h, lo, hi, samples, offset=0):
        self.x0, self.y0, self.w, self.h, self.lo, self.hi = x0, y0, w, h, lo, hi
        self.samples = list(samples)
        self.offset = offset


class Element:
    """A placed height field (0x24 bytes in the file)."""
    __slots__ = ('index', 'min_x', 'min_y', 'max_x', 'max_y', 'flags', 'hf', 'x', 'y', 'z',
                 'cos', 'sin', 'stamp', 'f_min_x', 'f_min_y', 'f_max_x', 'f_max_y')

    def __init__(self, index, min_x, min_y, max_x, max_y, hf, flags, x, y, z, cos, sin):
        self.index = index
        self.min_x, self.min_y, self.max_x, self.max_y = min_x, min_y, max_x, max_y
        self.hf, self.flags = hf, flags
        self.x, self.y, self.z, self.cos, self.sin = x, y, z, cos, sin
        self.stamp = 0                      # +8: visit stamp
        # the rectangle as floats (16-bit values convert exactly under every model)
        self.f_min_x, self.f_min_y = i2f(min_x), i2f(min_y)
        self.f_max_x, self.f_max_y = i2f(max_x), i2f(max_y)


class Level:
    """The parts of a .world file the queries read, after world_fixup (0x181d30).

    world_fixup, besides turning offsets into pointers, rewrites the height field of every
    moving piece's terrain element (0x181e2c-0x181ec0): a sample with flag bit 0 becomes
    height 2000 keeping its four flag bits, and the field's maximum (+0x12) becomes 2000.
    """

    def __init__(self, data=None):
        self.stamp = 0                      # g_terrainStamp 0x44f08c
        self.tg_x0 = self.tg_y0 = self.tg_w = self.tg_h = 0
        self.grid = []                      # per terrain cell: element indices in file order
        self.elements = []
        self.heightfields = []
        self.pieces = []                    # terrain element index of each moving piece
        self.pg_x0 = self.pg_y0 = self.pg_w = self.pg_h = 0
        self.path_cells = []
        if data is not None:
            self._parse(data)

    @classmethod
    def load(cls, path):
        with open(path, 'rb') as source:
            return cls(source.read())

    def _parse(self, data):
        w = world_info.World(data)
        self.tg_x0, self.tg_y0, self.tg_w, self.tg_h = w.tg_x0, w.tg_y0, w.tg_w, w.tg_h
        fields = {}
        for offset, hf in w.heightfields.items():
            fields[offset] = HeightField(hf.x0, hf.y0, hf.w, hf.h, hf.lo, hf.hi, w.samples(hf), offset)
        self.heightfields = [fields[key] for key in sorted(fields)]
        self.elements = [Element(e.index, e.minx, e.miny, e.maxx, e.maxy, fields[e.hf], e.flags & 0xFFFF,
                                 e.x, e.y, e.z, e.cos, e.sin) for e in w.elements]
        self.grid = []
        if w.tg_off:
            for j in range(w.tg_h):
                for i in range(w.tg_w):
                    self.grid.append(w.terrain_cell_list(i, j)[0])
        self.pg_x0, self.pg_y0, self.pg_w, self.pg_h = w.pg_x0, w.pg_y0, w.pg_w, w.pg_h
        self.path_cells = list(w.path_cells())
        self.pieces = [p.element for p in w.pieces]
        for index in self.pieces:                       # 0x181e2c-0x181ec0, in piece order
            hf = self.elements[index].hf
            hf.samples = [(v & 0xF) + 0x7D00 if v & 1 else v for v in hf.samples]
            hf.hi = 2000

    # ---- run-time changes made by moving pieces -----------------------------------------
    def set_piece_collision(self, piece, on):
        """world_setPieceCollision 0x182b00: clears (on) or sets flag 2 of the piece's
        terrain element; flag 2 makes terrain_collectElements skip it."""
        if piece >= 0:
            e = self.elements[self.pieces[piece]]
            e.flags = (e.flags & 0xFFFD) if on else (e.flags | 2)

    def set_piece_height(self, piece, height):
        """world_setPieceHeight 0x182bb4: element z = int(height) (height a float pattern)."""
        if piece >= 0:
            self.elements[self.pieces[piece]].z = f2i(height)

    def get_piece_height(self, piece):
        """world_getPieceHeight 0x182b74 (returns the integer; 0 for a negative index)."""
        return self.elements[self.pieces[piece]].z if piece >= 0 else 0

    def path_node_position(self, node):
        """(x, y) integers of a path node index: ((column + originX) * 24, (row + originY) * 24)."""
        return ((node % self.pg_w + self.pg_x0) * 24, (node // self.pg_w + self.pg_y0) * 24)


def build_world_file(grid_origin, grid_size, heightfields, elements, path=None, pieces=()):
    """Bytes of a minimal .world file for tests (no geometry, one inert chunk).

    grid_origin, grid_size   terrain grid origin and size in 160-unit cells
    heightfields             [(x0, y0, w, h, [samples row by row])], optionally followed by
                             (lowest, highest) for +0x10/+0x12; otherwise they are the
                             extremes of all samples
    elements                 [(field index, flags, x, y, z, cos, sin)] or with an explicit
                             rectangle appended: (..., min_x, min_y, max_x, max_y)
    path                     None or (originX, originY, w, h, [cells])
    pieces                   element indices that are moving pieces
    The rectangle of an element, when not given, is the bounding box of its samples'
    positions padded by 8 units, and it is listed in every terrain cell that touches it.
    """
    import math
    header_size = 0x84
    out = bytearray(header_size)

    def pad(align=16):
        while len(out) % align:
            out.append(0)

    pad()
    if path is not None:
        pox, poy, pw, ph, cells = path
        path_off = len(out)
        out += struct.pack('<%dI' % (pw * ph), *cells)
    else:
        pox = poy = pw = ph = path_off = 0
    pad()
    field_offsets = []
    for field in heightfields:
        x0, y0, w, h, samples = field[:5]
        field_offsets.append(len(out))
        heights = [v >> 4 for v in samples]
        lo, hi = field[5:7] if len(field) > 5 else (min(heights), max(heights))
        out += struct.pack('<iiIIhh', x0, y0, w, h, lo, hi)
        out += struct.pack('<%dh' % (w * h), *samples)
        pad(4)
    pad()
    piece_off = len(out)
    for element in pieces:
        out += struct.pack('<ihHiiihhhh', 0, 1, 0, 0, 0, 0, 32767, 0, element, 0)
    pad()
    textable_off = len(out)
    out += struct.pack('<II', 0, 0x40)
    pad()
    records = []
    for spec in elements:
        field, flags, x, y, z, cos, sin = spec[:7]
        x0, y0, w, h = heightfields[field][:4]
        if len(spec) > 7:
            box = spec[7:11]
        else:
            c, s = cos / 32767.0, sin / 32767.0
            xs, ys = [], []
            for lx in (x0 * 4, (x0 + w - 1) * 4):
                for ly in (y0 * 4, (y0 + h - 1) * 4):
                    if flags & 1:
                        xs.append(lx * c + ly * s + x)
                        ys.append(lx * s - ly * c + y)
                    else:
                        xs.append(lx * c - ly * s + x)
                        ys.append(lx * s + ly * c + y)
            box = (int(math.floor(min(xs))) - 8, int(math.floor(min(ys))) - 8,
                   int(math.ceil(max(xs))) + 8, int(math.ceil(max(ys))) + 8)
        records.append((box, field_offsets[field], flags, x, y, z, cos, sin))
    gx0, gy0 = grid_origin
    gw, gh = grid_size
    tail_off = len(out)
    lists = []
    for j in range(gh):
        for i in range(gw):
            cx0, cy0 = (gx0 + i) * 160, (gy0 + j) * 160
            lists.append(len(out) - tail_off)
            for index, (box, _f, _fl, _x, _y, _z, _c, _s) in enumerate(records):
                if box[0] <= cx0 + 160 and cx0 <= box[2] and box[1] <= cy0 + 160 and cy0 <= box[3]:
                    out += struct.pack('<h', index)
            out += struct.pack('<h', -1)
    pad(4)
    grid_off = len(out)
    out += struct.pack('<%dI' % len(lists), *lists)
    pad()
    elem_off = len(out)
    for box, field_off, flags, x, y, z, cos, sin in records:
        out += struct.pack('<4hIIIiiihh', box[0], box[1], box[2], box[3], 0, field_off, flags, x, y, z,
                           cos, sin)
    pad()
    chunk_off = len(out)
    out += struct.pack('<II6fIIiiihhhh', textable_off, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    pad()
    struct.pack_into('<2I2i2I4I2i2I1I2i2I1I2I2iiIfI5I', out, 0,
                     1, 0, gx0, gy0, gw, gh, grid_off, len(records), elem_off, chunk_off,
                     pox, poy, pw, ph, path_off, 0, 0, 0, 0, 0,
                     len(pieces), piece_off if pieces else 0, 0, 0, -1, textable_off, 720.0, 0,
                     0, 0, tail_off, 0, 0)
    return bytes(out)


# =======================================================================================
# 3. Terrain elements
# =======================================================================================

def collect_elements(level, min_x, min_y, max_x, max_y, limit):
    """terrain_collectElements 0x183248 (f12-f15 = box, a0 world, a1 out, a2 limit).

    Cell range per axis: int(floorf(coordinate * 1/160)) - grid origin, clamped to the grid.
    Rows (y) outer, columns inner, each cell's list in file order.  An element is taken when
    its stamp differs from level.stamp, its flag 2 is clear and its rectangle touches the
    box; it is then stamped.  The walk stops dead once limit - 1 elements are held.
    The CALLER advances level.stamp; terrain_raycast does so once for several calls."""
    col0 = s32(f2i(floorf(fmul(min_x, K_INV_160))) - level.tg_x0)
    row0 = s32(f2i(floorf(fmul(min_y, K_INV_160))) - level.tg_y0)
    col1 = s32(f2i(floorf(fmul(max_x, K_INV_160))) - level.tg_x0)
    row1 = s32(f2i(floorf(fmul(max_y, K_INV_160))) - level.tg_y0)
    if row0 < 0:
        row0 = 0
    if level.tg_h - 1 < row1:
        row1 = level.tg_h - 1
    if level.tg_w - 1 < col1:
        col1 = level.tg_w - 1
    if col0 < 0:
        col0 = 0
    out = []
    stamp = level.stamp
    elements = level.elements
    width = level.tg_w
    for row in range(row0, row1 + 1):
        for col in range(col0, col1 + 1):
            for index in level.grid[row * width + col]:
                e = elements[index]
                if e.stamp == stamp or e.flags & 2:
                    continue
                if (flt(max_x, e.f_min_x) or flt(max_y, e.f_min_y)
                        or flt(e.f_max_x, min_x) or flt(e.f_max_y, min_y)):
                    continue
                e.stamp = stamp
                out.append(e)
                if len(out) == limit - 1:
                    return out
    return out


def _next_stamp(level):
    level.stamp = (level.stamp + 1) & M32


def _rotation(e):
    """(cos, sin) of an element as floats: s16 * 0x38000100."""
    return fmul(i2f(e.cos), K_INV_32767), fmul(i2f(e.sin), K_INV_32767)


def _to_samples(e, c, s, px, py):
    """A world point in the element's sample units (4 world units), not yet floored.
    The same instruction sequence appears in every query (e.g. 0x18390c-0x1839c0)."""
    ux = fsub(px, i2f(e.x))
    uy = fsub(py, i2f(e.y))
    if e.flags & 1:                                     # mirrored
        ly = fsub(fmul(ux, s), fmul(uy, c))
        lx = fadd(fmul(ux, c), fmul(uy, s))
    else:
        lx = fadd(fmul(ux, c), fmul(uy, s))
        ly = fadd(fmul(fneg(ux), s), fmul(uy, c))
    return fmul(lx, QUARTER), fmul(ly, QUARTER)


def _span(lo, hi, first, size):
    """range(lo, hi + 1) cut down to the indices first .. first + size - 1.  The original
    walks the whole range and skips what lies outside the field one by one; the result is
    the same, and a step that went wild cannot make the model spin."""
    return range(lo if lo > first else first, (hi if hi < first + size - 1 else first + size - 1) + 1)


def _dir_to_samples(e, c, s, dx, dy):
    """A direction in the element's axes (no scaling)."""
    if e.flags & 1:
        return fadd(fmul(dx, c), fmul(dy, s)), fsub(fmul(dx, s), fmul(dy, c))
    return fadd(fmul(dx, c), fmul(dy, s)), fadd(fmul(fneg(dx), s), fmul(dy, c))


# =======================================================================================
# 4. Floor height
# =======================================================================================

def _height_under_disc(level, radius, pos, step_limit):
    px, py, pz = pos[0], pos[1], pos[2]
    _next_stamp(level)
    elements = collect_elements(level, fsub(px, radius), fsub(py, radius),
                                fadd(px, radius), fadd(py, radius), 64)
    r4 = fmul(radius, QUARTER)
    reach = f2i(ceilf(r4))
    r4sq = fmul(r4, r4)
    best = NO_FLOOR_INT
    for e in elements:
        hf = e.hf
        top = hf.hi + e.z
        if not best < top:
            continue
        if step_limit and flt(fadd(pz, K_12), i2f(hf.lo + e.z)):
            continue
        c, s = _rotation(e)
        lx, ly = _to_samples(e, c, s, px, py)
        i0 = f2i(floorf(lx))
        j0 = f2i(floorf(ly))
        samples, width, x0 = hf.samples, hf.w, hf.x0
        done = False
        columns = _span(i0 - reach, i0 + reach + 1, x0, width)
        for j in _span(j0 - reach, j0 + reach + 1, hf.y0, hf.h):
            row = j - hf.y0
            for i in columns:
                col = i - x0
                h = (samples[row * width + col] >> 4) + e.z
                if not best < h:
                    continue
                if step_limit and flt(fadd(pz, K_12), i2f(h)):
                    continue
                a = fsub(i2f(i), lx)
                b = fsub(i2f(j), ly)
                if not flt(fadd(fmul(a, a), fmul(b, b)), r4sq):
                    continue
                best = h
                if not best < top:
                    done = True
                    break
            if done:
                break
    return i2f(best)


def terrain_height(level, radius, pos):
    """terrain_height 0x183820 (f12 radius, a0 world, a1 pos) -> float pattern.

    The highest ground height (sample >> 4, plus the element's z) among the samples whose
    grid point lies strictly inside the disc; -1000000.0 when there is none.  Flags are not
    looked at.  At most 63 elements, 4-unit samples, rows outer; the search of an element
    ends as soon as a sample reaches the element's maximum."""
    return _height_under_disc(level, radius, pos, False)


def terrain_height_below(level, radius, pos):
    """terrain_heightBelow 0x1834a8: as terrain_height, but an element whose lowest height
    (+0x10) plus z is more than 12 above pos.z is skipped, and so is every sample more than
    12 above pos.z (float compares: (pos.z + 12.0) < float(height))."""
    return _height_under_disc(level, radius, pos, True)


def terrain_height_at_point(level, pos):
    """terrain_heightAtPoint 0x182f28 (a0 world, a1 pos) -> float pattern.

    Only the terrain cell that contains the point is looked at; of its elements (flag 2
    clear, rectangle containing the point) the sample at (floor, floor) of the local
    position; the highest of those.  0.0 when the point is off the grid or the best is
    below -100000.  No stamp is used and none is advanced."""
    px, py = pos[0], pos[1]
    col = s32(f2i(floorf(fmul(px, K_INV_160))) - level.tg_x0)
    row = s32(f2i(floorf(fmul(py, K_INV_160))) - level.tg_y0)
    if col < 0 or row < 0 or not col < level.tg_w or not row < level.tg_h:
        return ZERO
    best = NO_FLOOR_INT
    for index in level.grid[row * level.tg_w + col]:
        e = level.elements[index]
        if e.flags & 2:
            continue
        if flt(px, e.f_min_x) or flt(py, e.f_min_y) or flt(e.f_max_x, px) or flt(e.f_max_y, py):
            continue
        c, s = _rotation(e)
        lx, ly = _to_samples(e, c, s, px, py)
        i = f2i(floorf(lx))
        j = f2i(floorf(ly))
        hf = e.hf
        row_i = j - hf.y0
        if row_i < 0 or hf.h - 1 < row_i:
            continue
        col_i = i - hf.x0
        if col_i < 0 or hf.w - 1 < col_i:
            continue
        h = (hf.samples[row_i * hf.w + col_i] >> 4) + e.z
        if best < h:
            best = h
    if best < -100000:
        return ZERO
    return i2f(best)


# =======================================================================================
# 5. The blocked test
# =======================================================================================

def terrain_test_flag1(level, radius, pos):
    """terrain_testFlag1 0x183b48 (f12 radius, a0 world, a1 pos) -> float pattern 1.0 or 0.0.

    1.0 when any sample strictly inside the disc has flag bit 0.  Heights play no part.
    The result is a float in f0: both callers compare it with a float constant."""
    px, py = pos[0], pos[1]
    _next_stamp(level)
    elements = collect_elements(level, fsub(px, radius), fsub(py, radius),
                                fadd(px, radius), fadd(py, radius), 64)
    r4 = fmul(radius, QUARTER)
    reach = f2i(ceilf(r4))
    r4sq = fmul(r4, r4)
    for e in elements:
        hf = e.hf
        if not NO_FLOOR_INT < hf.hi + e.z:
            continue
        c, s = _rotation(e)
        lx, ly = _to_samples(e, c, s, px, py)
        i0 = f2i(floorf(lx))
        j0 = f2i(floorf(ly))
        columns = _span(i0 - reach, i0 + reach + 1, hf.x0, hf.w)
        for j in _span(j0 - reach, j0 + reach + 1, hf.y0, hf.h):
            row = j - hf.y0
            for i in columns:
                col = i - hf.x0
                if not hf.samples[row * hf.w + col] & 1:
                    continue
                a = fsub(i2f(i), lx)
                b = fsub(i2f(j), ly)
                if flt(fadd(fmul(a, a), fmul(b, b)), r4sq):
                    return ONE
    return ZERO


# =======================================================================================
# 6. Swept circle and slide
# =======================================================================================

def terrain_sweep_circle(level, radius, pos, delta, mask, want_normal=True):
    """terrain_sweepCircle 0x185a40 (f12 radius, a0 world, a1 pos, a2 delta, a3 mask,
    t0 normal out or 0) -> (t, normal).

    A circle at pos tries to move by delta.  t is the fraction of delta it can go: exactly
    1.0 when nothing is in the way, otherwise best / length with both in sample units (it
    can be negative when the circle already overlaps a blocking sample).  normal is None
    unless the move is blocked and want_normal is set; then (nx, ny, 0), computed from the
    circle centre at  pos + direction * best  -- best in SAMPLE units used as world units,
    a quarter of the distance travelled (0x186088-0x1860c4).

    A sample blocks when one of its flag bits is in mask (it then counts as height 32000)
    or its ground is 12 or more above the mover: tested in integers against
    floor(min(z, z + delta.z)) + 12 and in floats against (z + along * dz) + 12.0."""
    px, py, pz = pos[0], pos[1], pos[2]
    ex = fadd(px, delta[0])
    ey = fadd(py, delta[1])
    _next_stamp(level)
    elements = collect_elements(level, fsub(fmin(px, ex), radius), fsub(fmin(py, ey), radius),
                                fadd(fmax(px, ex), radius), fadd(fmax(py, ey), radius), 256)
    sx = fmul(delta[0], QUARTER)
    r4 = fmul(radius, QUARTER)
    r4sq = fmul(r4, r4)
    sy = fmul(delta[1], QUARTER)
    length = fsqrt(fadd(fmul(sx, sx), fmul(sy, sy)))
    inv = fdiv(ONE, length)
    dir_x = fmul(sx, inv)
    dir_y = fmul(sy, inv)
    dz_per = fmul(delta[2], inv)                        # delta.z is NOT scaled by 1/4
    reach = f2i(ceilf(r4))
    base = f2i(floorf(fmin(pz, fadd(pz, delta[2])))) + STEP_HEIGHT
    best = length
    hit_x = hit_y = ZERO
    r4_margin = fadd(r4, K_0_01)
    for e in elements:
        hf = e.hf
        if not e.flags & 4 and hf.hi + e.z < base:
            continue
        c, s = _rotation(e)
        lx, ly = _to_samples(e, c, s, px, py)
        dlx, dly = _dir_to_samples(e, c, s, dir_x, dir_y)
        i0 = f2i(floorf(lx))
        j0 = f2i(floorf(ly))
        i1 = f2i(floorf(fadd(lx, fmul(dlx, length))))
        j1 = f2i(floorf(fadd(ly, fmul(dly, length))))
        i_lo, i_hi = (i0, i1) if i0 < i1 else (i1, i0)
        j_lo, j_hi = (j0, j1) if j0 < j1 else (j1, j0)
        samples, width, x0, ez = hf.samples, hf.w, hf.x0, e.z
        columns = _span(i_lo - reach, i_hi + reach + 1, x0, width)
        for j in _span(j_lo - reach, j_hi + reach + 1, hf.y0, hf.h):     # rows outer
            row = j - hf.y0
            b = None
            for i in columns:
                col = i - x0
                v = samples[row * width + col]
                h = BLOCK_HEIGHT if v & mask else (v >> 4) + ez
                if h < base:
                    continue
                a = fsub(i2f(i), lx)
                if b is None:
                    b = fsub(i2f(j), ly)
                perp = fsub(fmul(a, dly), fmul(b, dlx))
                if flt(r4_margin, fabs_(perp)):
                    continue
                along = fadd(fmul(a, dlx), fmul(b, dly))
                if flt(along, ZERO):
                    continue
                if flt(i2f(h), fadd(fadd(pz, fmul(along, dz_per)), K_12)):
                    continue
                q = fsub(r4sq, fmul(perp, perp))
                t = fsub(along, fsqrt(q)) if flt(ZERO, q) else fsub(along, ZERO)
                if not flt(t, best):
                    continue
                best = t
                wx = i2f(i << 2)
                wy = i2f(j << 2)
                if e.flags & 1:
                    hit_y = fadd(fsub(fmul(wx, s), fmul(wy, c)), i2f(e.y))
                    hit_x = fadd(fadd(fmul(wx, c), fmul(wy, s)), i2f(e.x))
                else:
                    hit_y = fadd(fadd(fmul(wx, s), fmul(wy, c)), i2f(e.y))
                    hit_x = fadd(fsub(fmul(wx, c), fmul(wy, s)), i2f(e.x))
    if fle(length, best):
        return ONE, None
    normal = None
    if want_normal:
        nx = fsub(fadd(px, fmul(dir_x, best)), hit_x)
        ny = fsub(fadd(py, fmul(dir_y, best)), hit_y)
        k = frsqrt(ONE, fadd(fmul(nx, nx), fmul(ny, ny)))
        normal = (fmul(nx, k), fmul(ny, k), ZERO)
    return fmul(best, inv), normal


def world_slide_move(level, radius, pos, delta, mask):
    """world_slideMove 0x14d238 (f12 radius, a0 pos in/out, a1 delta, a2 mask, a3 normal
    out or 0) -> (hit, new_pos, normal).

    Up to 11 sweeps.  After each: remain -= t, the position advances by step * t, and while
    more than 0.001 of the move remains the delta loses its part going into the contact
    normal (plus 0.001 outward) and the rest is tried again.  hit is 1 when any sweep left
    more than 0.001.  normal is the last one a sweep wrote (None if none did: the original
    then copies an uninitialised stack slot)."""
    d = [delta[0], delta[1], delta[2]]
    p = [pos[0], pos[1], pos[2]]
    remain = ONE
    hit = 0
    normal = None
    for _ in range(11):
        step = (fmul(d[0], remain), fmul(d[1], remain), fmul(d[2], remain))
        t, n = terrain_sweep_circle(level, radius, p, step, mask, True)
        if n is not None:
            normal = n
        remain = fsub(remain, t)
        p = [fadd(p[0], fmul(step[0], t)), fadd(p[1], fmul(step[1], t)), fadd(p[2], fmul(step[2], t))]
        if not flt(K_0_001, remain):
            break
        hit = 1
        if normal is None:
            raise RuntimeError('slide: more than 0.001 remains but no sweep was blocked')
        k = fsub(K_0_001, fadd(fadd(fmul(normal[0], d[0]), fmul(normal[1], d[1])), fmul(normal[2], d[2])))
        if flt(ZERO, k):
            d = [fadd(d[0], fmul(normal[0], k)), fadd(d[1], fmul(normal[1], k)),
                 fadd(d[2], fmul(normal[2], k))]
    return hit, p, normal


# =======================================================================================
# 7. Movers: who uses which mask, the ground step, the projectile step
# =======================================================================================

OBJ_CREATURE = 0x20
OBJ_PLAYER = 0x40


def mover_mask(object_flags):
    """The mask obj_moveWithCollision passes for the object's own step (0x14d57c-0x14d59c):
    1; 3 for a creature (flag 0x20); 5 for a player (flag 0x40: (mask | 4) & 5).
    Creature_moveBy always passes 3 (0x113ff0, 0x1141cc); the push-out slide of
    obj_moveWithCollision always 1 (0x14d8a0)."""
    mask = 3 if object_flags & OBJ_CREATURE else 1
    if object_flags & OBJ_PLAYER:
        mask = (mask | 4) & 5
    return mask


def ground_step(level, radius, pos, vz, stand=K_MINUS_100000):
    """The end of obj_moveWithCollision, 0x14da20-0x14dac4 -> (new_pos, new_vz, landed).

    ground = terrain_heightBelow(radius, pos), or stand (the top of an object underfoot) if
    that is higher.  vz loses 8.999999, z gains vz * (1/60).  When z - 0.01 <= ground the
    mover is put on the ground, and if vz was negative it becomes 0 and landed is set."""
    ground = terrain_height_below(level, radius, pos)
    if flt(ground, stand):
        ground = stand
    vz = fsub(vz, K_GRAVITY_STEP)
    z = fadd(pos[2], fmul(vz, K_DT))
    landed = 0
    if fle(fsub(z, K_0_01), ground):
        z = ground
        if flt(vz, ZERO):
            vz = ZERO
            landed = 1
    return [pos[0], pos[1], z], vz, landed


def object_move(level, radius, pos, velocity, vz, object_flags):
    """obj_moveWithCollision 0x14d4b8 for an object with nothing else near it
    -> (new_pos, new_vz, bits).  bits: 1 the slide was blocked, 4 landed.

    The step is velocity * (1/60); it is tried only when its squared length (three
    components) exceeds 0.001.  Push-out from other objects, the touch calls and standing
    on objects (0x14d6b0-0x14da1c) are not modelled."""
    d = (fmul(velocity[0], K_DT), fmul(velocity[1], K_DT), fmul(velocity[2], K_DT))
    bits = 0
    p = [pos[0], pos[1], pos[2]]
    if flt(K_0_001, fadd(fadd(fmul(d[0], d[0]), fmul(d[1], d[1])), fmul(d[2], d[2]))):
        hit, p, _normal = world_slide_move(level, radius, p, d, mover_mask(object_flags))
        bits = 1 if hit else 0
    p, vz, landed = ground_step(level, radius, p, vz)
    if landed:
        bits |= 4
    return p, vz, bits


def projectile_step(level, radius, pos, velocity):
    """The terrain part of obj_moveAndCollide, 0x1509f8-0x150bc8 -> (new_pos, hit).

    No sweep: the position jumps by velocity * (1/60).  If terrain_height there is above
    the new z the projectile hit the ground; it is then moved back along the step by
    0.1, 0.2, ... of it until terrain_height is not above it, and is left at the last point
    tried (k reaches 2.0 after 19 tries) even when none was clear."""
    d = (fmul(velocity[0], K_DT), fmul(velocity[1], K_DT), fmul(velocity[2], K_DT))
    p = [fadd(pos[0], d[0]), fadd(pos[1], d[1]), fadd(pos[2], d[2])]
    if not flt(p[2], terrain_height(level, radius, p)):
        return p, 0
    k = K_0_1
    while True:
        attempt = [fsub(p[0], fmul(d[0], k)), fsub(p[1], fmul(d[1], k)), fsub(p[2], fmul(d[2], k))]
        if fle(terrain_height(level, radius, attempt), attempt[2]):
            break
        k = fadd(k, K_0_1)
        if not flt(k, K_TWO):
            break
    return attempt, 1


# =======================================================================================
# 8. Rays
# =======================================================================================

def terrain_raycast(level, max_t, origin, direction, flags):
    """terrain_raycast 0x18a5c0 (f12 max_t, a0 world, a1 origin, a2 direction, a3 flags)
    -> float pattern: the parameter t of the first hit (origin + direction * t), or -1.0.

    The ray is marched in the horizontal plane, one sample (4 units) per step, inside each
    element it meets; a sample is hit when the ray's height is below the sample's height,
    and a sample with a flag bit in `flags` counts as 65536 * (those bits) higher.
    Elements are collected for 240-unit segments of the ray, each element once per call
    (one stamp for the whole call), and each is marched for up to 1001 steps from the start
    of the segment that found it.  The first segment with a hit decides.

    Kept as the code has them:
      * between segments the origin's height advances by 240 steps' worth of slope although
        the segment is 60 steps long (0x18a738-0x18a788);
      * the sample index is the truncation, not the floor, of the local position;
      * a vertical ray (horizontal length * 1/4 below 0.01) returns
        origin.z - terrain_heightAtPoint when it points down (a distance, not a parameter)
        and -1.0 otherwise."""
    ox, oy, oz = origin[0], origin[1], origin[2]
    dx = fmul(direction[0], QUARTER)
    dy = fmul(direction[1], QUARTER)
    dz = direction[2]
    length = fsqrt(fadd(fmul(dx, dx), fmul(dy, dy)))
    if flt(length, K_0_01):
        if not flt(dz, ZERO):
            return MINUS_ONE
        return fsub(oz, terrain_height_at_point(level, origin))
    limit = fmul(max_t, length)                         # the reach, in sample units
    inv = fdiv(ONE, length)
    _next_stamp(level)
    marched = ZERO                                      # world units done in earlier segments
    flag_bits = (flags & 0xFFFF) << 16
    dx = fmul(dx, inv)                                  # unit direction
    dy = fmul(dy, inv)
    dz = fmul(dz, inv)                                  # rise per sample step
    if not flt(ZERO, limit):
        return MINUS_ONE
    for _ in range(1001):
        ex = fadd(ox, fmul(dx, K_240))
        ey = fadd(oy, fmul(dy, K_240))
        ez = fadd(oz, fmul(dz, K_240))
        elements = collect_elements(level, fmin(ox, ex), fmin(oy, ey), fmax(ox, ex), fmax(oy, ey), 256)
        best = K_1E11
        low_z = K_MINUS_1E7 if flt(dz, ZERO) else oz
        for e in elements:
            hf = e.hf
            if not (flag_bits and e.flags & 4):
                if flt(i2f(hf.hi + e.z), low_z):
                    continue
            c, s = _rotation(e)
            lx, ly = _to_samples(e, c, s, ox, oy)
            z = fsub(oz, i2f(e.z))
            dlx, dly = _dir_to_samples(e, c, s, dx, dy)
            t = ZERO
            # clip the start of the march to the field's rectangle, one side at a time
            edge = i2f(hf.x0)
            if flt(lx, edge):
                if fle(dlx, K_0_01):
                    continue
                k = fdiv(fsub(edge, lx), dlx)
                t = k
                lx, ly, z = fadd(lx, fmul(dlx, k)), fadd(ly, fmul(dly, k)), fadd(z, fmul(dz, k))
            edge = i2f(hf.x0 + hf.w)
            if flt(edge, lx):
                if fle(K_MINUS_0_01, dlx):
                    continue
                k = fdiv(fsub(edge, lx), dlx)
                t = fadd(t, k)
                lx, ly, z = fadd(lx, fmul(dlx, k)), fadd(ly, fmul(dly, k)), fadd(z, fmul(dz, k))
            edge = i2f(hf.y0)
            if flt(ly, edge):
                if fle(dly, K_0_01):
                    continue
                k = fdiv(fsub(edge, ly), dly)
                t = fadd(t, k)
                lx, ly, z = fadd(lx, fmul(dlx, k)), fadd(ly, fmul(dly, k)), fadd(z, fmul(dz, k))
            edge = i2f(hf.y0 + hf.h)
            if flt(edge, ly):
                if fle(K_MINUS_0_01, dly):
                    continue
                k = fdiv(fsub(edge, ly), dly)
                t = fadd(t, k)
                lx, ly, z = fadd(lx, fmul(dlx, k)), fadd(ly, fmul(dly, k)), fadd(z, fmul(dz, k))
            col = s32(f2i(lx) - hf.x0)
            row = s32(f2i(ly) - hf.y0)
            outside = 0
            steps = 1
            while True:
                if col < 0 or row < 0 or not col < hf.w or not row < hf.h:
                    if not outside < 4:
                        break
                    outside += 1
                else:
                    word = (hf.samples[row * hf.w + col] << 16) & M32
                    height = s32((s32(word) >> 20) + (word & flag_bits))
                    if flt(z, i2f(height)):
                        if flt(t, best):
                            best = t
                        break
                t = fadd(t, ONE)
                more = steps < 1001
                steps += 1
                lx = fadd(lx, dlx)
                ly = fadd(ly, dly)
                col = s32(f2i(lx) - hf.x0)
                row = s32(f2i(ly) - hf.y0)
                z = fadd(z, dz)
                if not more:
                    break
        if flt(best, K_1E10):
            total = fadd(best, fmul(marched, QUARTER))
            if flt(total, limit):
                return fmul(total, inv)
            return MINUS_ONE
        marched = fadd(marched, K_240)
        ox, oy, oz = ex, ey, ez
        if not flt(fmul(marched, QUARTER), limit):
            return MINUS_ONE
    return MINUS_ONE


class Circle:
    """What world_raycast reads of a game object: flags (+0xc), x, y (+0x10, +0x14),
    radius (+0x1c).  Floats as patterns."""
    __slots__ = ('flags', 'x', 'y', 'radius', 'name')

    def __init__(self, flags, x, y, radius, name=None):
        self.flags, self.x, self.y, self.radius, self.name = flags, x, y, radius, name


def world_raycast(level, max_t, origin, direction, flags, objects=None, ignore=None,
                  include_40000=False):
    """world_raycast 0x18ad94 (f12 max_t, a0 world, a1 origin, a2 direction, a3 object to
    ignore, t0 hit-object out, t1 terrain flags, t2 include-0x40000) -> (t, hit object).

    terrain_raycast first, then circles of game objects in 240-unit segments up to the
    terrain hit (or max_t).  objects(box_min, box_max) stands for world_collectObjectsInBox
    0x14a928 and returns Circle-like objects in the order that function would list them;
    None means no objects.  Returns -1.0 when max_t <= 0, when the direction is vertical
    (horizontal length below 0.01) whatever terrain_raycast found, or when neither terrain
    nor an object is hit."""
    if fle(max_t, ZERO):
        return MINUS_ONE, None
    t_terrain = terrain_raycast(level, max_t, origin, direction, flags)
    dx, dy, dz = direction[0], direction[1], direction[2]
    length = fsqrt(fadd(fmul(dx, dx), fmul(dy, dy)))
    if flt(length, K_0_01):
        return MINUS_ONE, None
    best = max_t if flt(t_terrain, ZERO) else t_terrain
    inv = fdiv(ONE, length)
    unit_x, unit_y = fmul(dx, inv), fmul(dy, inv)
    k = fmul(inv, K_240)
    seg = (fmul(dx, k), fmul(dy, k), fmul(dz, k))
    cur = [origin[0], origin[1], origin[2]]
    count = s32(f2i(fmul(fmul(best, length), K_INV_240)) + 1)
    hit = None
    for _ in range(max(count, 0)):
        nxt = [fadd(cur[0], seg[0]), fadd(cur[1], seg[1]), fadd(cur[2], seg[2])]
        found = ()
        if objects is not None:
            found = objects((fmin(nxt[0], cur[0]), fmin(nxt[1], cur[1]), K_MINUS_10000),
                            (fmax(nxt[0], cur[0]), fmax(nxt[1], cur[1]), K_10000))
        for o in found:
            if o.flags & 5 and not (include_40000 and o.flags & 0x40000):
                continue
            if o is ignore:
                continue
            reach = K_60 if o.flags & 0x40000 else o.radius
            to_x = fsub(o.x, origin[0])
            to_y = fsub(o.y, origin[1])
            perp = fabs_(fsub(fmul(unit_y, to_x), fmul(unit_x, to_y)))
            if flt(reach, perp):
                continue
            t = fsub(fadd(fmul(unit_x, to_x), fmul(unit_y, to_y)),
                     fsqrt(fsub(fmul(reach, reach), fmul(perp, perp))))
            if o.flags & 0x40000 and flt(t, ZERO):
                t = K_0_01
            if flt(t, ZERO):
                continue
            t = fmul(t, inv)
            if flt(t, best):
                best = t
                hit = o
        cur = nxt
    if flt(t_terrain, ZERO) and hit is None:
        return MINUS_ONE, None
    return best, hit


# =======================================================================================
# 9. Path grid
# =======================================================================================

def _path_rect(level, radius, pos):
    margin = fadd(radius, K_5)
    x_hi = fadd(fadd(pos[0], radius), K_5)
    y_hi = fadd(fadd(pos[1], radius), K_5)
    x_lo = fsub(pos[0], margin)
    y_lo = fsub(pos[1], margin)
    col0 = s32(f2i(fsub(fmul(x_lo, K_INV_24), ONE)) - level.pg_x0)
    col1 = s32(f2i(fadd(fmul(x_hi, K_INV_24), ONE)) - level.pg_x0)
    row1 = s32(f2i(fadd(fmul(y_hi, K_INV_24), ONE)) - level.pg_y0)
    row0 = s32(f2i(fsub(fmul(y_lo, K_INV_24), ONE)) - level.pg_y0)
    return col0, col1, row0, row1


def _path_count(level, radius, pos, block):
    col0, col1, row0, row1 = _path_rect(level, radius, pos)
    cells, width = level.path_cells, level.pg_w
    for col in range(col0, col1):
        for row in range(row0, row1):
            index = row * width + col
            if col < 0 or not col < width or index < 0 or not index < len(cells):
                raise IndexError('path node (%d, %d) is outside the grid; the original does not check'
                                 % (col, row))
            cell = cells[index]
            count = s32(cell) >> 16
            if block:
                if count < 16:
                    count = s16(count + 1)
            elif count > 0:
                count = s16(count - 1)
            cells[index] = (cell & 0xFFFF) | ((count << 16) & M32)


def path_block_nodes(level, radius, pos):
    """0x18b6c0 (f12 radius, a0 world, a1 pos): adds 1 (up to 16) to the block counter in
    the upper 16 bits of every path node in a rectangle around pos.  Columns from
    int((x - (r + 5)) * 1/24 - 1) - originX up to but not including
    int(((x + r) + 5) * 1/24 + 1) - originX, rows likewise.  A node with a non-zero counter
    is never entered by the search.  Called by Torch_ctor 0x2b1e80 and
    StaticFire_initCommon 0x2c5814.  No bounds check in the original."""
    _path_count(level, radius, pos, True)


def path_unblock_nodes(level, radius, pos):
    """0x18b584: the reverse (a counter above 0 loses 1); called by StaticFire_dtor."""
    _path_count(level, radius, pos, False)


class PathRequest:
    """One entry of g_pathQueue 0x7d43a8 (0x30 bytes): +0 world, +4 start, +0x10 goal,
    +0x1c radius, +0x20 out buffer, +0x24 max points, +0x28 requester handle, +0x2c type."""
    __slots__ = ('level', 'start', 'goal', 'radius', 'max_points', 'requester', 'kind', 'path',
                 'result')

    def __init__(self, level, start, goal, radius, max_points, requester, kind):
        self.level, self.start, self.goal, self.radius = level, tuple(start), tuple(goal), radius
        self.max_points, self.requester, self.kind = max_points, requester, kind
        self.path = None        # [(x, y), ..., (-1, -1)] once a search wrote the buffer
        self.result = None      # 1 found, 0 not found, once delivered


class PathFinder:
    """The path queue and search: path_request* 0x184e38-0x185447, path_service 0x184798,
    path_search 0x183e40 and the four goal tests 0x1844a4-0x184797.

    requester is a callable taking the result (1 or 0); it stands for virtual slot 7 of the
    requesting object.  Setting request.requester = None stands for the object having been
    deleted (the handle at +0x28 is then 0).  The same value is the "object to ignore" of
    the goal tests that cast rays against objects; `objects` is passed to world_raycast.

    timer() stands for a read of hardware timer T0 (0x10000000); it is consulted only when
    service is called with blocking = False."""
    QUEUE = 128
    RING = 512
    MAX_ROUNDS = 80

    def __init__(self, level, objects=None):
        self.level = level
        self.objects = objects
        self.enabled = True                 # g_pathEnabled 0x44f090
        self.queue = [None] * self.QUEUE
        self.write = 0                      # g_pathQueueWrite 0x44f09c
        self.read = 0                       # g_pathQueueRead 0x44f0a0
        self.busy = False                   # g_pathBusy 0x44f0a4
        self.prev_start = 0                 # 0x44f098: start node of the last search
        self.iterations = 0                 # 0x44f094: rounds of the current search
        self.round = 0                      # 0x7d89c0
        self.counts = [0, 0, 0, 0]          # 0x7d89b0
        self.rings = [[0] * self.RING for _ in range(4)]    # 0x7d69b0, 4 x 512 node indices
        self.goal_kind = None               # which test 0x7d35e0 points at
        self.goal = (ZERO, ZERO, ZERO)      # 0x7d5ba8 (type 0) / 0x7d5bb0 (types 1-3)
        self.goal_radius_sq = ZERO          # 0x7d89c4 / 0x7d89d4
        self.goal_start_z = ZERO            # 0x7d89cc
        self.goal_ignore = None             # 0x7d89c8
        self.goal_level = level             # 0x7d89d0

    # ---- requests -----------------------------------------------------------------------
    def request(self, kind, radius, start, goal, requester, max_points=16, level=None):
        """path_requestToPoint 0x184e38 (kind 0), path_requestType1/2/3 0x184fc8, 0x185148,
        0x1852c8.  A full queue (127 waiting) answers requester(0) at once and returns None.
        Kind 0 raises a radius below 24 to 24; the others store it as given."""
        if ((self.write + 1) & 0x7F) == self.read:
            requester(0)
            return None
        if kind == 0 and flt(radius, K_24):
            radius = K_24
        entry = PathRequest(level or self.level, start, goal, radius, max_points, requester, kind)
        self.queue[self.write] = entry
        self.write = (self.write + 1) & 0x7F
        return entry

    def reset(self):
        """The path part of world_resetRuntime 0x18b1b8 (level start)."""
        self.enabled = True
        self.read = self.write = 0
        self.prev_start = 0

    # ---- the service loop ---------------------------------------------------------------
    def service(self, blocking=True, timer=None):
        """path_service 0x184798 (a0 blocking).

        Loop: when not blocking, return once T0 >= 9000.  If a search is in progress, run
        path_search; -1 (suspended) goes round the loop again, anything else is delivered
        to the requester and the queue advances.  Otherwise take the oldest request: none
        -> return; requester gone -> drop it; start off the grid -> answer 0; else clear
        the marks of the previous search, seed the new one and choose the goal test.
        While g_pathEnabled is 0 the call is always blocking and every search answers 0."""
        if timer is None:
            timer = lambda: 0                           # noqa: E731
        if not self.enabled:
            blocking = True
        while True:
            if not blocking and not timer() < 9000:
                return
            if self.busy:
                entry = self.queue[self.read]
                result = self.search(entry, blocking, timer)
                if result == -1:
                    continue
                entry.result = result
                if entry.requester is not None:
                    entry.requester(result)
                self.busy = False
                self.read = (self.read + 1) & 0x7F
                continue
            if self.write == self.read:
                return
            entry = self.queue[self.read]
            if entry.requester is None:
                self.read = (self.read + 1) & 0x7F
                continue
            level = entry.level
            col = f2i(fadd(fsub(fmul(entry.start[0], K_INV_24), i2f(level.pg_x0)), HALF))
            row = f2i(fadd(fsub(fmul(entry.start[1], K_INV_24), i2f(level.pg_y0)), HALF))
            if col < 0 or row < 0 or not col < level.pg_w or not row < level.pg_h:
                entry.result = 0
                entry.requester(0)
                self.read = (self.read + 1) & 0x7F
                continue
            self._clear_marks(level)
            self.counts = [0, 0, 0, 0]
            node = row * level.pg_w + col
            self.iterations = 0
            self.counts[0] = 1
            self.prev_start = node
            self.rings[0][0] = node
            level.path_cells[node] |= 0xF00             # mark 15: the end of the trace back
            self.round = 0
            self.busy = True
            if entry.kind == 0:
                self.goal_kind = 0
                self.goal = (entry.goal[0], entry.goal[1], ZERO)
                self.goal_radius_sq = fmul(entry.radius, entry.radius)
            elif entry.kind in (1, 2, 3):
                self.goal_kind = entry.kind
                self.goal = entry.goal
                self.goal_radius_sq = fmul(entry.radius, entry.radius)
                self.goal_ignore = entry.requester
                self.goal_start_z = entry.start[2]
                self.goal_level = level

    def _offsets(self, width):
        # link bit k leads to node + offsets[k]: (-1,-1) (0,-1) (+1,-1) (+1,0) (+1,+1) (0,+1) (-1,+1) (-1,0)
        return (-1 - width, -width, 1 - width, 1, width + 1, width, width - 1, -1)

    def _clear_marks(self, level):
        """0x184a04-0x184b88: wipe the marks (bits 8-15) of the previous search by a flood
        from its start node along link bits, two buffers taking turns.  A wave stops
        feeding the next one once that holds 497 nodes; marks beyond are left behind.
        Nothing is done when the previous start node had index 0."""
        if self.prev_start == 0:
            return
        cells = level.path_cells
        offsets = self._offsets(level.pg_w)
        self.counts[0] = 1
        self.rings[0][0] = self.prev_start
        self.counts[1] = 0
        cells[self.prev_start] &= 0xFFFF00FF
        cur = 0
        while True:
            other = cur ^ 1
            source, target = self.rings[cur], self.rings[other]
            produced = 0
            for i in range(self.counts[cur]):
                node = source[i]
                links = cells[node]
                for k in range(8):
                    if not (links >> k) & 1:
                        continue
                    neighbour = node + offsets[k]
                    cell = cells[neighbour]
                    if not cell & 0xFF00:
                        continue
                    cells[neighbour] = cell & 0xFFFF00FF
                    target[produced] = neighbour
                    produced += 1
                if not produced < 0x1F1:
                    break
            self.counts[other] = produced
            cur = other
            if produced == 0:
                break

    # ---- goal tests ---------------------------------------------------------------------
    def _goal_reached(self, level, node):
        """The function 0x7d35e0 points at, called with the node's position as two floats."""
        px = i2f(s32((node % level.pg_w + level.pg_x0) * 24))
        py = i2f(s32((node // level.pg_w + level.pg_y0) * 24))
        gx, gy = self.goal[0], self.goal[1]
        dy = fsub(py, gy)
        dx = fsub(px, gx)
        dist_sq = fadd(fmul(dx, dx), fmul(dy, dy))
        kind = self.goal_kind
        if kind == 0:                                   # 0x1844a4
            return flt(dist_sq, self.goal_radius_sq)
        origin = (px, py, self.goal_start_z)
        toward = (fsub(gx, px), fsub(gy, py), ZERO)
        if kind == 1:                                   # path_goalTestClearLine 0x1844f0
            if flt(self.goal_radius_sq, dist_sq):
                return False
            t, _hit = world_raycast(self.goal_level, K_1200, origin, toward, 0, self.objects,
                                    self.goal_ignore, False)
            return flt(K_0_98, t)
        if flt(self.goal_radius_sq, dist_sq):           # 0x1845bc, 0x1846a4: outside -> reached
            return True
        if flt(K_14400, self.goal_radius_sq) and flt(dist_sq, K_14400):
            return False
        if kind == 2:                                   # path_goalTestRanged 0x1845bc
            return flt(terrain_raycast(self.goal_level, K_1200, origin, toward, 0), K_0_98)
        t, _hit = world_raycast(self.goal_level, K_1200, origin, toward, 0, self.objects,
                                self.goal_ignore, False)                # path_goalTest3 0x1846a4
        return flt(t, K_0_75)

    # ---- the search ---------------------------------------------------------------------
    def search(self, entry, blocking=True, timer=None):
        """path_search 0x183e40 (a0 world, a1 goal test, a2 out buffer, a3 max points,
        t0 blocking) -> 1 found, 0 not found, -1 suspended (call again to go on).

        A wave over the node grid kept in four ring buffers of 512 nodes, one per round
        modulo 4.  Each round takes the nodes of ring `round % 4`:
          pass 1  a node that was entered by a straight move (even mark) and has the link
                  in that same direction enters its neighbour into ring round + 2;
          pass 2  every node tries its eight links in bit order; the neighbours go into
                  ring round + 3.
        A neighbour is entered only when it has no mark and no block counter; it is marked
        (direction bit + 1) even when its ring is full, in which case it is neither queued
        nor tested.  Each queued node is put to the goal test at once; in pass 1 a hit ends
        the pass, in pass 2 it ends that node's links, and the last hit of the round wins.
        The search fails after five empty rounds in a row or once 80 rounds were counted.
        When not blocking, a round that found nothing returns -1 if T0 >= 7513.

        On success the marks are followed back from the goal node to the start node (mark
        15) and the node positions are written start first as integer pairs, at most
        max_points - 1 of them, then (-1, -1)."""
        if timer is None:
            timer = lambda: 0                           # noqa: E731
        if not self.enabled:
            return 0
        level = entry.level
        cells = level.path_cells
        width = level.pg_w
        offsets = self._offsets(width)
        ring_size = self.RING
        found = 0
        empty = 0
        while True:
            rnd = self.round
            self.iterations += 1
            current = self.rings[rnd % 4]
            count = self.counts[rnd % 4] if self.iterations < self.MAX_ROUNDS + 1 else 0
            self.counts[rnd % 4] = 0
            if count == 0:
                empty += 1
                if not empty < 5:
                    break
                self.round = rnd + 1
                continue
            empty = 0
            ring = self.rings[(rnd + 2) % 4]
            fill = self.counts[(rnd + 2) % 4]
            for i in range(count):
                node = current[i]
                cell = s32(cells[node])
                mark = cell >> 8
                if mark & 1:
                    continue
                if not (cell >> ((mark - 1) & 31)) & 1:
                    continue
                neighbour = node + offsets[mark - 1]
                other = cells[neighbour]
                if other & 0xFF00 or other & 0xFFFF0000:
                    continue
                cells[neighbour] = (other | (mark << 8)) & M32
                if not fill < ring_size:
                    continue
                ring[fill] = neighbour
                fill += 1
                if self._goal_reached(level, neighbour):
                    found = neighbour + 1
                    break
            self.counts[(rnd + 2) % 4] = fill
            ring = self.rings[(rnd + 3) % 4]
            fill = self.counts[(rnd + 3) % 4]
            for i in range(count):
                node = current[i]
                links = cells[node]
                for k in range(8):
                    if not (links >> k) & 1:
                        continue
                    neighbour = node + offsets[k]
                    other = cells[neighbour]
                    if other & 0xFF00 or other & 0xFFFF0000:
                        continue
                    cells[neighbour] = other | ((k + 1) << 8)
                    if not fill < ring_size:
                        continue
                    ring[fill] = neighbour
                    fill += 1
                    if self._goal_reached(level, neighbour):
                        found = neighbour + 1
                        break
            self.counts[(rnd + 3) % 4] = fill
            self.round = rnd + 1
            if found:
                break
            if not blocking and not timer() < 7513:
                return -1
        if not found:
            if entry.max_points > 0:
                entry.path = [(-1, -1)]
            return 0
        # follow the marks back (0x184348-0x1843e4); positions pass through 16-bit storage
        node = found - 1
        trail = []
        while True:
            if len(trail) == 256:
                raise RuntimeError('path longer than the 256-entry scratch array')
            trail.append((s16((node % width + level.pg_x0) * 24), s16((node // width + level.pg_y0) * 24)))
            direction = (s32(cells[node]) >> 8) - 1
            if not direction < 8:
                break
            if direction < 0:
                raise RuntimeError('trace reached an unmarked node')
            node -= offsets[direction]
        path = []
        remaining = len(trail)
        while len(path) < entry.max_points - 1:
            remaining -= 1
            if remaining == -1:
                break
            path.append(trail[remaining])
        path.append((-1, -1))
        entry.path = path
        return 1
