#!/usr/bin/env python3
"""ref_particles.py - reference contract of the particle system of Champions: Return to
Arms (SLUS_209.73, US v2.00): definitions, spawning, ageing, retirement, the page and slot
pools, the texture flipbook and the emitter record shared by level chunks and AddParticle
helpers.

A research tool, not game code.  Each function was written from the code at the address
in its docstring; docs/effects.md is the prose version.  Nothing here was executed against
the original (no difftest yet), so treat it as Observed-by-reading.  Standard library only;
no game data is embedded.

    import ref_particles as P
    d = P.ParticleDef.build(1.0, 3.0, -2.0, (0x80, 0x40, 0x20, 0x80), (0, 0, 0, 0),
                            life_class=2, kind=P.KIND_ADD, tile=0x12)
    sysm = P.ParticleSystem()
    sysm.spawn(d, (100.0, 200.0, 50.0), (0.0, 0.0, 16.0))
    for _ in range(10):
        sysm.update()
    for p, view in sysm.visible():
        print(view.pos, view.size, view.rgba)

Precision.  The effects are cosmetic, so this model uses Python floats rounded to 32 bits
where the original stores a float (f32()) and C truncation where it converts to an integer
(cvt.w.s).  It is meant to be exact for the integer fields (particle records, ticks, pool
behaviour, texture coordinates) and close for the float ones.  Angles use the host
cosine of the angle, not the original's math_cos16 0x166630 (docs/spec/core.md,
docs/spec/trig16.md).  The schedule fields do not read that cosine.  A yaw of 0 does:
the host sine is +0, and math_sin16(0) is +2^-22, so an x offset gains a y component.

What each part mirrors
    ParticleDef.build      particleDef_init 0x18ee70 (via particleDef_ctor 0x18f3d0 / _set 0x18f118)
    ParticleDef.from_emitter_record
                           the argument loads of world_fixup 0x1820d4-0x18215c and of
                           AddParticle_readEmitterProps 0x2403cc-0x24043c
    spawn_record           the record part of particle_spawn 0x18f3f8
    evaluate, line_endpoints
                           the vertex program entries 0x18 / 0x22 (VU 0x089, 0x0ac)
    ParticleSystem         lists, pages and slots: particle_spawn, 0x18f6e0 (retire),
                           particle_updateTask 0x18f970, 0x195b58 / 0x195bb0 (slots),
                           particleGroup_* 0x18e880-0x18eba8
    flipbook_step          particle_draw 0x194930-0x194980
    EmitterRecord, emitter_run
                           the 0x48-byte record and its runner 0x195400
    CosmeticRng            g_cosmeticSeed 0x404460 as 0x195400 draws it
"""
import math
import struct
from collections import namedtuple

M32 = 0xffffffff

# --- constants -------------------------------------------------------------------------

LIFE_TICKS = (11, 30, 60, 90)            # g_particleLifeTicks 0x44fa88 (read-only)

KIND_BLEND = 0      # sprite, ALPHA_1 0x44
KIND_ADD = 1        # sprite, ALPHA_1 0x48
KIND_LINE = 2       # line pos(age - lag) .. pos(age); ALPHA_1 left at 0x48 (Inferred)
KIND_HIDDEN = 3     # accepted by particleDef_init, never drawn by particle_emitLists 0x194450

ALPHA_REGISTER = {KIND_BLEND: 0x44, KIND_ADD: 0x48, KIND_LINE: 0x48}
TEST_REGISTER = 0x71001                  # depth greater, no depth write (particle_draw)

COLOUR_BIAS = 8388608.0                  # 2^23, added to the colours of kinds 0-2
SLOT_COUNT = 32                          # 0x82c408 / 0x82c490
SLOT0_DEFINITION = 0x7e1d00              # particle_init 0x18e648 claims slot 0 for it for good:
                                         # only slots 1-31 serve definitions (round-2 correction)
PAGE_COUNT = 64                          # 0x7ec300, 0x1000 bytes each
CELLS_PER_PAGE = 240                     # 8 blocks of 30
CURSOR_FULL = 0x101                      # list cursor value meaning "take a new page"
GROUP_COUNT = 16
GROUP_IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, 0.0))
GROUP_IDLE_FREE = 31                     # freed when the idle count read is > 30 (0x18fa58)
CLOCK_WRAP = -0x8000                     # g_particleClock 0x82cc90 is s16


def f32(x):
    """Round a Python float to the nearest IEEE single (what swc1 of a float stores)."""
    return struct.unpack('<f', struct.pack('<f', x))[0]


def trunc(x):
    """cvt.w.s: float to int, toward zero."""
    return int(x)


def rz(x):
    """A Python float cut to single precision toward zero, as the console's FPU rounds
    (a value below the smallest normal becomes zero).  For a product of two singles the
    double is exact, so rz(a * b) is the console's mul.s (round 2: executed, see
    tools/difftest_particles.py)."""
    if x == 0.0 or x != x:
        return 0.0
    b = struct.unpack('<Q', struct.pack('<d', x))[0]
    if (b >> 52) & 0x7ff < 1023 - 126:
        return 0.0
    b &= ~((1 << 29) - 1)
    v = struct.unpack('<d', struct.pack('<Q', b))[0]
    return f32(v) if abs(v) <= 3.4028234663852886e38 else math.copysign(3.4028234663852886e38, v)


def s16(v):
    v &= 0xffff
    return v - 0x10000 if v & 0x8000 else v


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


# --- the definition ----------------------------------------------------------------------

class ParticleDef:
    """A particle definition (0x50 bytes in the original).  Fields keep the original's
    names by offset; `record()` gives the four VU qwords (+0x10 .. +0x4f)."""

    __slots__ = ('list_index', 'slot', 'live', 'callback', 'u0', 'v0', 'gravity', 'size_rate',
                 'u1', 'v1', 'size0', 'c0', 'crate', 'kind', 'life_class', 'tile', 'life',
                 'line_gravity', 'line_lag')

    @classmethod
    def build(cls, size_start, size_end, gravity, start_rgba, end_rgba, life_class=3,
              kind=KIND_ADD, tile=1, callback=0, previous=None):
        """particleDef_init 0x18ee70.  `previous` stands for the bytes already in the
        object: kind 2 leaves +0x14, +0x20 and +0x24 as they were (0 for a fresh one)."""
        if callback:
            raise ValueError('particle.cc line 0x1f8: terminate callback must be 0')
        d = cls()
        life_class = clamp(int(life_class), 0, 3)
        kind = clamp(int(kind), 0, 3)
        d.kind, d.life_class, d.tile = kind, life_class, int(tile)
        d.life = LIFE_TICKS[life_class]
        # float work in the console's rounding (toward zero), in the code's order
        inv = rz(1.0 / d.life)
        d.list_index = kind * 4 + life_class
        d.slot, d.live, d.callback = -1, 0, 0
        g = rz(f32(gravity) * 0.00390625)
        d.gravity = g
        a = rz(f32(size_start) * 100.0)
        if kind == KIND_LINE:
            d.line_gravity = g                       # +0x10 as a float
            d.line_lag = rz(a * f32(0.01))           # +0x1c: sizeStart again
            d.u0 = None
            d.v0 = previous.v0 if previous else 0
            d.u1 = previous.u1 if previous else 0
            d.v1 = previous.v1 if previous else 0
            d.size_rate = d.line_lag
        else:
            d.line_gravity = None
            d.line_lag = None
            col, row = (d.tile & 0xf) * 32, (d.tile >> 4) * 32
            d.u0, d.v0 = (col + 1) * 16, (row + 1) * 16
            d.u1, d.v1 = (col + 31) * 16, (row + 31) * 16
            b = rz(f32(size_end) * 100.0)
            d.size_rate = rz(rz(b - a) * inv)
        d.size0 = a
        bias = 0.0 if kind == KIND_HIDDEN else COLOUR_BIAS
        start = [int(c) for c in start_rgba]
        end = [int(c) for c in end_rgba]
        d.c0 = tuple(rz(rz(float(c)) + bias) for c in start)
        d.crate = tuple(rz(rz(float(e - s)) * inv) for s, e in zip(start, end))
        return d

    @classmethod
    def reset_default(cls):
        """0x18f360: size 1 -> 1, gravity 0, colours 0, lifeClass 3, kind 1, tile 1."""
        return cls.build(1.0, 1.0, 0.0, (0, 0, 0, 0), (0, 0, 0, 0), 3, KIND_ADD, 1)

    @classmethod
    def from_emitter_record(cls, rec):
        """The 17 definition bytes of an emitter record (EmitterRecord or 0x48 bytes)."""
        if not isinstance(rec, EmitterRecord):
            rec = EmitterRecord.parse(rec)
        return cls.build(float(rec.size_start), float(rec.size_end), float(rec.gravity),
                         rec.start_rgba, rec.end_rgba, rec.life_class, rec.kind, rec.tile)

    def colour_at(self, age):
        """clamp(c0 + crate * age, 0, 255) per channel, as integers 0..255.  The sum is
        made in the vector unit's rounding (toward zero) on the 2^23-biased start, so a
        channel whose rate is inexact can end one short of its end value (round 2)."""
        bias = 0.0 if self.kind == KIND_HIDDEN else COLOUR_BIAS
        return tuple(int(clamp(rz(c + rz(r * age)) - bias, 0.0, 255.0))
                     for c, r in zip(self.c0, self.crate))

    def size_at(self, age):
        return rz(self.size0 + rz(self.size_rate * age))

    def record(self):
        """The 0x40-byte record the vertex program reads (+0x10..+0x4f), little-endian.
        +0x28 (the definition's own address) is written as 0 here."""
        if self.kind == KIND_LINE:
            q0 = struct.pack('<fiff', self.line_gravity, self.v0, self.gravity, self.line_lag)
        else:
            q0 = struct.pack('<iiff', self.u0, self.v0, self.gravity, self.size_rate)
        q1 = struct.pack('<iiif', self.u1, self.v1, 0, self.size0)
        return q0 + q1 + struct.pack('<4f', *self.c0) + struct.pack('<4f', *self.crate)


# --- one particle --------------------------------------------------------------------------

Particle = namedtuple('Particle', 'x y z birth vx vy vz type4')
View = namedtuple('View', 'pos size rgba age')


def spawn_record(d, pos, vel, clock, backdate=0.0, slot=0):
    """The 16-byte record particle_spawn 0x18f3f8 writes (all s16).  vel is in world units
    per 16 ticks.  backdate > 0 (seconds) back-dates the birth by trunc(60 * backdate) ticks
    and moves the start so that the particle is at pos with velocity vel now."""
    px, py, pz = pos
    vx, vy, vz = vel
    if backdate > 0.0:
        # the console's float operations, in the code's order (0x18f53c-0x18f63c)
        n = trunc(rz(f32(backdate) * 60.0))
        g = d.gravity
        nf = float(n)
        k = rz(nf * 0.0625)
        vz2 = rz(f32(vz) - rz(float(n << 5) * g))
        x = rz(f32(px) - rz(f32(vx) * k))
        y = rz(f32(py) - rz(f32(vy) * k))
        z = rz(rz(f32(pz) - rz(vz2 * k)) - rz(rz(g * nf) * nf))
        return Particle(s16(trunc(x)), s16(trunc(y)), s16(trunc(z)), s16(clock - n),
                        s16(trunc(rz(f32(vx) * 256.0))), s16(trunc(rz(f32(vy) * 256.0))),
                        s16(trunc(rz(vz2 * 256.0))), slot << 2)
    return Particle(s16(trunc(px)), s16(trunc(py)), s16(trunc(pz)), s16(clock),
                    s16(trunc(f32(vx * 256.0))), s16(trunc(f32(vy * 256.0))),
                    s16(trunc(f32(vz * 256.0))), slot << 2)


def position_at(p, d, age, gravity=None):
    """pos = p + v * age / 16, z += g * age^2 (VU: ITOF12 of 256 v, times age)."""
    g = d.gravity if gravity is None else gravity
    return (p.x + p.vx / 4096.0 * age,
            p.y + p.vy / 4096.0 * age,
            p.z + p.vz / 4096.0 * age + g * age * age)


def evaluate(p, d, clock):
    """What the sprite program draws for particle p at `clock` (kinds 0 and 1)."""
    age = clock - p.birth
    return View(position_at(p, d, age), d.size_at(age), d.colour_at(age), age)


def line_endpoints(p, d, clock):
    """Kind 2: (tail, head) = (pos(age - lag), pos(age)), gravity from +0x10."""
    age = clock - p.birth
    return (position_at(p, d, age - d.line_lag, d.line_gravity),
            position_at(p, d, age, d.line_gravity))


def screen_half_extent(size, w):
    """Half width and height in pixels of the 1280 x 448 draw buffer (VU vf9 = (2, 1)).
    w is the particle's camera-space depth."""
    return (2.0 * size / w, size / w)


def expired(p, d, clock):
    """0x18f8b4: retired when birth + life < clock (so drawn for ages 0..life)."""
    return p.birth + d.life < clock


# --- the pools ------------------------------------------------------------------------------

class _List:
    __slots__ = ('pages', 'head', 'tail', 'cells')

    def __init__(self):
        self.pages = []           # page ids in order, first .. last
        self.head = 1             # +0x8: next cell to examine in the first page
        self.tail = CURSOR_FULL   # +0xc: next free cell in the last page
        self.cells = {}           # (page, cell) -> (Particle, ParticleDef)


def _next_cell(c):
    c += 1
    if c & 0x1f == 0x1f:
        c += 2
    return c


class ParticleSystem:
    """Global list set plus 16 groups; 64 shared pages; 32 type slots.  Spawn order and
    retirement follow the original, including the silent drops."""

    def __init__(self):
        self.clock = 0
        self.free_pages = list(range(PAGE_COUNT))   # pop(0) = the head of 0x82c400
        self.slots = [None] * SLOT_COUNT
        self.slots[0] = SLOT0_DEFINITION         # held from particle_init on (round 2)
        self.global_set = [_List() for _ in range(16)]
        self.groups = {}                            # handle -> [lists, matrix, idle]
        # the 16 group slots own their lists for good (0x7e1d50 + i * 0x138): a slot's lists
        # are reset by group_free and by the level reset, not by group_create (round 2)
        self.group_lists = [[_List() for _ in range(16)] for _ in range(GROUP_COUNT)]
        self.group_seq = 1                          # 0x44fc9c
        self.current = self.global_set
        self.dropped = 0

    # groups: particleGroup_create / begin / end / free
    def group_create(self):
        used = {h & 0xff for h in self.groups}
        for i in range(GROUP_COUNT):
            if i not in used:
                h = (self.group_seq << 8) | i
                self.group_seq += 1
                self.groups[h] = [self.group_lists[i], GROUP_IDENTITY, 0]
                return h
        return 0

    def group_set_matrix(self, h, matrix):
        """particleGroup_setMatrix 0x18e9e8: copies the mat34 (four rows of x, y, z) into
        the group when the handle is live."""
        if h in self.groups:
            self.groups[h][1] = tuple(tuple(r) for r in matrix)

    def group_begin(self, h):
        if h in self.groups:
            self.current = self.groups[h][0]

    def group_end(self, h):
        if h in self.groups:
            self.current = self.global_set

    def group_free(self, h):
        """particleGroup_free 0x18ea90: the pages go back (each pushed in list order, so
        the list's last page ends on top) but the definitions' live counts are NOT lowered,
        so a group freed while it still has particles keeps their definitions' slots
        until the level reset 0x18ebb8."""
        g = self.groups.pop(h, None)
        if g:
            for lst in g[0]:
                for pg in lst.pages:
                    self.free_pages.insert(0, pg)
                lst.pages, lst.head, lst.tail, lst.cells = [], 1, CURSOR_FULL, {}

    def _dead(self, d):
        d.live -= 1
        if d.live == 0:
            self.slots[d.slot] = None
            d.slot = -1

    def spawn(self, d, pos, vel, backdate=0.0):
        """particle_spawn 0x18f3f8.  Returns the Particle or None when dropped."""
        lst = self.current[d.list_index]
        if d.live == 0 and None not in self.slots:
            self.dropped += 1
            return None
        if lst.tail == CURSOR_FULL:
            if not self.free_pages:
                self.dropped += 1
                return None
            lst.pages.append(self.free_pages.pop(0))
            lst.tail = 1
        if d.live == 0:
            s = self.slots.index(None)
            self.slots[s] = d
            d.slot = s
        cell = (lst.pages[-1], lst.tail)
        lst.tail = _next_cell(lst.tail)
        d.live += 1
        p = spawn_record(d, pos, vel, self.clock, backdate, d.slot)
        lst.cells[cell] = (p, d)
        return p

    def _retire(self, lst):
        """0x18f6e0 for one list; returns True when the list was not empty."""
        if not lst.pages:
            return False
        nonempty = False
        while lst.pages:
            page = lst.pages[0]
            last = lst.pages[-1]
            if page == last and lst.head == lst.tail:
                break
            nonempty = True
            p, d = lst.cells[(page, lst.head)]
            if not expired(p, d, self.clock):
                break
            del lst.cells[(page, lst.head)]
            self._dead(d)
            c = lst.head + 1
            if c & 0x1f == 0x1f:
                if c != 0xff or page == last:
                    c += 2
                else:
                    self.free_pages.insert(0, lst.pages.pop(0))
                    c = 1
            lst.head = c
        if lst.pages and len(lst.pages) == 1 and lst.head == lst.tail:
            self.free_pages.insert(0, lst.pages.pop())
            lst.head, lst.tail = 1, CURSOR_FULL
        return nonempty

    def update(self, in_cutscene=False):
        """particle_updateTask 0x18f970, one simulated tick."""
        self.clock += 1
        if self.clock == 0x8000:                # the s16 reached -0x8000
            self.clock = 0
            for lists in [self.global_set] + [g[0] for g in self.groups.values()]:
                for lst in lists:
                    for k, (p, d) in list(lst.cells.items()):
                        lst.cells[k] = (p._replace(birth=s16(p.birth - 0x8000)), d)
        for lst in self.global_set:
            self._retire(lst)
        for h in list(self.groups):
            lists = self.groups[h][0]
            busy = False
            for lst in lists:
                busy = self._retire(lst) or busy
            if in_cutscene or busy:
                self.groups[h][2] = 0
            else:
                idle = self.groups[h][2]
                self.groups[h][2] = idle + 1
                if idle >= GROUP_IDLE_FREE:
                    self.group_free(h)

    def live(self):
        sets = [self.global_set] + [g[0] for g in self.groups.values()]
        for lists in sets:
            for lst in lists:
                for p, d in lst.cells.values():
                    yield p, d

    def visible(self):
        """Drawn particles with their state (kinds 0-2; kind 3 is never drawn)."""
        for p, d in self.live():
            if d.kind != KIND_HIDDEN:
                yield p, evaluate(p, d, self.clock)


# --- texture flipbook ---------------------------------------------------------------------

def flipbook_step(d, sim_frame):
    """particle_draw 0x194930-0x194980: rows 1 and 2 step one cell on calls where
    g_simFrame is even, row 4 on every call; 16 cells then wrap.  Mutates d.u0 / d.u1 (the
    resident record; every particle of the definition shows the same cell).  Kind 2 is
    left out here: its +0x10 is a float and its +0x14 is whatever the object held (0 for
    the static definitions, so row 0 and no step)."""
    if d.kind == KIND_LINE:
        return False
    row = d.v0 >> 9
    if not ((row in (1, 2) and sim_frame & 1 == 0) or row == 4):
        return False
    u0, u1 = d.u0 + 0x200, d.u1 + 0x200
    if u0 > 0x1fff:
        u0 -= 0x2000
        u1 -= 0x2000
    d.u0, d.u1 = u0, u1
    return True


# --- emitters --------------------------------------------------------------------------------

_EMITTER = struct.Struct('<4B4BhhhBBBbhhhhhhHHHHHhhiiB3xiB11s')
assert _EMITTER.size == 0x48

_FIELDS = ('start_rgba', 'end_rgba', 'size_start', 'size_end', 'gravity', 'life_class', 'kind',
           'tile', 'rate', 'off_x', 'off_y', 'off_z', 'vel', 'yaw', 'pitch', 'box', 'spread',
           'cone', 'on_time', 'off_time', 'flags', 'next', 'on', 'name')


class EmitterRecord:
    """The 0x48-byte emitter record: level chunk data (flag 0x4000) and AddParticle
    helper +0x64.  docs/effects.md section 5 gives the offsets and property keys."""

    __slots__ = _FIELDS

    @classmethod
    def parse(cls, data):
        v = _EMITTER.unpack(bytes(data[:0x48]))
        r = cls()
        r.start_rgba, r.end_rgba = tuple(v[0:4]), tuple(v[4:8])
        (r.size_start, r.size_end, r.gravity, r.life_class, r.kind, r.tile, r.rate,
         r.off_x, r.off_y, r.off_z) = v[8:18]
        r.vel = tuple(v[18:21])
        r.yaw, r.pitch = v[21], v[22]
        r.box = tuple(v[23:26])
        r.spread, r.cone, r.on_time, r.off_time, r.flags, r.next, r.on = v[26:33]
        r.name = v[33].split(b'\0', 1)[0].decode('latin-1')
        return r

    def pack(self):
        name = self.name.encode('latin-1')[:10] if isinstance(self.name, str) else self.name
        return _EMITTER.pack(*self.start_rgba, *self.end_rgba, self.size_start, self.size_end,
                             self.gravity, self.life_class, self.kind, self.tile, self.rate,
                             self.off_x, self.off_y, self.off_z, *self.vel, self.yaw & 0xffff,
                             self.pitch & 0xffff, *self.box, self.spread, self.cone,
                             self.on_time, self.off_time, self.flags, self.next, self.on, name)

    def same_definition(self, other):
        """0x195318: two chunks share an emitter type when bytes 0..0x10 are equal."""
        return self.pack()[:0x11] == other.pack()[:0x11]

    @classmethod
    def new(cls, **kw):
        r = cls()
        defaults = dict(start_rgba=(0x80,) * 4, end_rgba=(0,) * 4, size_start=1, size_end=1,
                        gravity=0, life_class=1, kind=KIND_ADD, tile=0, rate=1, off_x=0, off_y=0,
                        off_z=0, vel=(0, 0, 0), yaw=0, pitch=0, box=(0, 0, 0), spread=0, cone=0,
                        on_time=0, off_time=0, flags=0, next=0, on=0, name='')
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(r, k, v)
        return r


class CosmeticRng:
    """seed = seed * 0x19660d + 0x3c6ef35f; r() = (seed >> 16) / 65536 (0x195400)."""

    def __init__(self, seed=0):
        self.seed = seed & M32

    def step(self):
        self.seed = (self.seed * 0x19660d + 0x3c6ef35f) & M32
        return self.seed

    def r(self):
        return (self.step() >> 16) * (1.0 / 65536)


def _cs(angle):
    a = s16(angle) * (2.0 * math.pi / 65536.0)
    return math.cos(a), math.sin(a)


def rotate_axis(m, axis, angle):
    """mat34_rotateAxis 0x163000 on a 3 x 3 list of rows (docs/spec/core.md)."""
    c, s = _cs(angle)
    r0, r1, r2 = m
    if axis == 0:
        return [r0, [c * a + s * b for a, b in zip(r1, r2)], [-s * a + c * b for a, b in zip(r1, r2)]]
    if axis == 1:
        return [[c * a - s * b for a, b in zip(r0, r2)], r1, [s * a + c * b for a, b in zip(r0, r2)]]
    if axis == 2:
        return [[c * a + s * b for a, b in zip(r0, r1)], [-s * a + c * b for a, b in zip(r0, r1)], r2]
    return m


def transform(m, v):
    """mat34_transformPoint without translation: v.x*row0 + v.y*row1 + v.z*row2."""
    return tuple(v[0] * m[0][i] + v[1] * m[1][i] + v[2] * m[2][i] for i in range(3))


IDENTITY = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def _flip(v, neg_x, neg_y, swap_xy):
    x, y, z = v
    if neg_x:
        x = -x
    if neg_y:
        y = -y
    if swap_xy:
        x, y = y, x
    return (x, y, z)


def emitter_run(rec, pos, now, rng, yaw=0, neg_x=False, neg_y=False, swap_xy=False,
                weather_angle=0, weather_on=False):
    """emitter_run 0x195400.  Updates rec.next / rec.on and returns the list of
    (position, velocity) pairs it would hand to particle_spawn (backdate 0)."""
    rate = rec.rate
    if rate > 0:
        count = rate
    elif rate == 0:
        count = 0
    else:
        if now % (-rate) != 0:
            return []
        count = 1
    if rec.next < now:
        if rec.on_time == 0:
            rec.on = 1
        else:
            d = rec.off_time if rec.on else rec.on_time
            rec.next = trunc(rz(rz(float(now + d)) + rz((rng.r() - 0.5) * d)))
            rec.on = 0 if rec.on else 1
    if not rec.on or count <= 0:
        return []
    out = []
    for _ in range(count):
        o = ((rng.r() - 0.5) * rec.box[0], (rng.r() - 0.5) * rec.box[1], (rng.r() - 0.5) * rec.box[2])
        m1 = rotate_axis(rotate_axis(IDENTITY, 2, s16(yaw + rec.yaw)), 1, rec.pitch)
        o = transform(m1, o)
        c, s = _cs(yaw)
        o = (o[0] + rec.off_x * c + rec.off_y * s, o[1] - rec.off_x * s + rec.off_y * c, o[2])
        o = _flip(o, neg_x, neg_y, swap_xy)
        p = (pos[0] + o[0], pos[1] + o[1], pos[2] + o[2] + rec.off_z)
        v = tuple(float(c) for c in rec.vel)
        n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
        j = rng.r() - 0.5
        if n > 0.0:
            v = tuple(c + c / n * j * rec.spread for c in v)
        spin = s16(rng.step() >> 16)
        tilt = s16(trunc(rng.r() * rec.cone))
        m2 = rotate_axis(rotate_axis(IDENTITY, 2, spin), 1, tilt)
        v = transform(m2, v)
        if rec.flags & 1:
            v = transform(rotate_axis(rotate_axis(IDENTITY, 2, weather_angle), 1, rec.pitch), v)
        elif rec.flags & 2:
            v = transform(rotate_axis(rotate_axis(IDENTITY, 2, rec.yaw), 1, rec.pitch), v)
        else:
            v = _flip(transform(m1, v), neg_x, neg_y, swap_xy)
        if not (rec.flags & 1) or weather_on:
            out.append((p, v))
    return out
