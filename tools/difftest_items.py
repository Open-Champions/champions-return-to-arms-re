#!/usr/bin/env python3
"""difftest_items.py - differential test of tools/ref_items.py against the original code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_items.py [path/to/SLUS_209.73] [options]

    --quick          about a tenth of the default sample sizes
    --full           five times the default sample sizes
    --jobs N         worker processes (default: the processor count, at most 12)
    --seed N         base seed of the random samples (default 20973); runs repeat
    -k TEXT          run only the properties whose id or title contains TEXT
    -v               print every mismatch, not only the first three per property
    --text FILE      also test display names with the text of a GTEXT*.LMP or gtext.uni
    --iso FILE       take every GTEXT*.LMP from a disc image for the same purpose

Every line is PASS, FAIL, SKIP or INFO, a property id and one sentence with counts.  PASS
means: for every input of the sample, the ORIGINAL machine code executed in tools/ee_emu.py
and the model in tools/ref_items.py gave the same result, compared as the sentence says.
Exit status 1 when any property fails.

How the original is run.  One function at a time, on state this script builds: the item
tables are the executable's own; the globals a function reads (player count, classes,
difficulty, the two PvP flags, the level's monster level, the shared seed) are written
before the call.  Functions outside the item module that would need a world are replaced:
the pool allocator, the object constructors, the terrain query, the text lookup and the
two trigonometry calls of the throw.  Their replacements are part of the test set-up and
are named in each sentence.

"fast" properties additionally replace the C library's string routines (sscanf, strcmp,
strcpy, strcat, strchr, strstr, memset) by Python equivalents so that many more cases fit
in the time; the item module's own code still runs as machine code.  The same generators
are also run with the library's own code ("full") on a smaller sample, and the library's
sscanf is compared with the model's scanner directly.

Floating point is compared bit for bit under ee_emu's default FPU model ("ps2").  The
INFO line at the end says how many item values move under the other models.
"""
import hashlib
import os
import random
import struct
import sys
import time

# tools/ holds a dis.py; keep this directory behind the standard library on the path
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
import ee_emu
from ee_emu import EE, EmuError
import ref_items as R

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M64 = 0xFFFFFFFFFFFFFFFF

# functions of the item module
F_PARSE, F_RANDOMIZE, F_VALUE = 0x1069B8, 0x1046E0, 0x1024A8
F_WEIGHT, F_ARMOR, F_ATTACK, F_DAMAGE = 0x103E08, 0x103EC8, 0x103F88, 0x104100
F_GROUP0, F_GROUP1, F_RESOURCE = 0x104C04, 0x104C48, 0x1083F8
F_SAME, F_COPY, F_ENCODE, F_DECODE = 0x108924, 0x107CA8, 0x107EA4, 0x107EC0
F_PRESET, F_AFFIX, F_REAGENT, F_FIGURINE, F_CONSUMABLE = 0x104758, 0x104CA4, 0x106214, 0x106658, 0x108590
F_SHOP_APPEND, F_LOOT, F_SPAWN_GOLD, F_NAME = 0x107D54, 0x100D54, 0x100974, 0x101E48
F_LOAD_RESOURCES, F_SPAWN_NAMED, F_EQUIP_CHECK = 0x108434, 0x100BA0, 0x1C4948
# functions outside it that the test replaces
F_POOL_NEW, F_PHPROP_CTOR, F_PHPROP_PHYS, F_GOLD_CTOR = 0x14FDB8, 0x155A0C, 0x155110, 0x157668
F_COS16, F_SIN16, F_TERRAIN, F_TEXT_LOOKUP = 0x166630, 0x1666E0, 0x183820, 0x173C84
F_RES_FIND, F_FIND_FREE_SPOT = 0x17365C, 0x14ACF8
# library
F_POWF, F_SSCANF, F_STRCMP, F_STRCPY, F_STRCAT = 0x3A5AC8, 0x3B7F88, 0x3B8534, 0x3B868C, 0x3B8278
F_STRCHR, F_STRSTR, F_MEMSET = 0x3B83A4, 0x3B96A8, 0x3B60C0
F_EXTEND, F_MULDF, F_TRUNCDF = 0x3AEF58, 0x3AF4D0, 0x3AFB90
# globals
G_SEED, G_NUM_PLAYERS, G_PLAYERS, G_DIFFICULTY = 0x404464, 0x4D8AE0, 0x4D8AF0, 0x4F719C
G_PVP_A, G_PVP_B, G_LEVEL, G_LANGUAGE, G_NAME_BUFFER = 0x4F711C, 0x4F7120, 0x4F714C, 0x44FDDC, 0x564420
PLAYER_STRIDE, PLAYER_CLASS, PLAYER_LEVEL, PLAYER_STATS, PLAYER_SKILLS = 0x4C30, 0x50, 0x58, 0x90, 0x4B08
PARSER_FRAME, PARSER_RECORD = 0x170, 0xD0       # item_parseDescriptor's frame and its record


# ---------------------------------------------------------------------------------------
# The original, in the interpreter
# ---------------------------------------------------------------------------------------
def _cstr(mem, addr):
    out = bytearray()
    pages = mem.pages
    addr &= 0xFFFFFFFF
    while True:
        page = pages.get(addr >> 12)
        if page is None:
            raise EmuError('string at unmapped address 0x%08x' % addr)
        off = addr & 0xFFF
        end = page.find(0, off)
        if end >= 0:
            out += page[off:end]
            return bytes(out)
        out += page[off:]
        addr = ((addr >> 12) + 1) << 12


class Original:
    def __init__(self, elf, fast=False, fpu_model='ps2', mul_bias=False):
        emu = self.emu = EE(elf, fpu_model=fpu_model)
        emu.fpu_mul_bias = mul_bias
        emu.record_calls = False
        emu.record_writes = False
        self.mem = emu.mem
        self.sp = emu.r[29]
        self.rec, self.rec2 = emu.alloc(0x48), emu.alloc(0x48)
        self.text, self.text2 = emu.alloc(0x400), emu.alloc(0x100)
        self.ints = emu.alloc(0x20)
        self.vec = emu.alloc(0x20)
        self.obj = emu.alloc(0x400)
        self.stock = emu.alloc(0x1210)
        self.wide = [emu.alloc(0x800) for _ in range(8)]
        self.wide_next = 0
        self.log = []
        self.fast = fast
        if fast:
            self._library_hooks()
        self.base_hooks = dict(emu.hooks)

    def reset_hooks(self):
        """Drop the replacements a previous property installed on this instance."""
        self.emu.hooks = dict(self.base_hooks)
        self.emu.stub_names = {}

    # ---- replacements for the C library (fast mode) ------------------------------------
    def _library_hooks(self):
        emu, mem = self.emu, self.mem
        formats = {}

        def sscanf(e):
            text = _cstr(mem, e.r[4])
            fmt = formats.get(e.r[5])
            if fmt is None:
                fmt = formats[e.r[5]] = _cstr(mem, e.r[5])
            result, values = R.scan(fmt, text)
            for index, value in enumerate(values):
                mem.w32(e.r[6 + index], value)
            return result

        def strcmp(e):
            a, b = _cstr(mem, e.r[4]) + b'\0', _cstr(mem, e.r[5]) + b'\0'
            for x, y in zip(a, b):
                if x != y:
                    return x - y
            return 0

        def strcpy(e):
            mem.write(e.r[4], _cstr(mem, e.r[5]) + b'\0')
            return e.r[4]

        def strcat(e):
            mem.write((e.r[4] + len(_cstr(mem, e.r[4]))) & 0xFFFFFFFF, _cstr(mem, e.r[5]) + b'\0')
            return e.r[4]

        def strchr(e):
            text = _cstr(mem, e.r[4]) + b'\0'
            index = text.find(bytes([e.r[5] & 0xFF]))
            return e.r[4] + index if index >= 0 else 0

        def strstr(e):
            index = _cstr(mem, e.r[4]).find(_cstr(mem, e.r[5]))
            return e.r[4] + index if index >= 0 else 0

        def memset(e):
            mem.write(e.r[4], bytes([e.r[5] & 0xFF]) * (e.r[6] & 0xFFFFFFFF))
            return e.r[4]

        for addr, function in ((F_SSCANF, sscanf), (F_STRCMP, strcmp), (F_STRCPY, strcpy),
                               (F_STRCAT, strcat), (F_STRCHR, strchr), (F_STRSTR, strstr),
                               (F_MEMSET, memset)):
            emu.stub(addr, function=function)

    # ---- helpers -----------------------------------------------------------------------
    def call(self, addr, *args, fregs=(), max_steps=2000000000):
        emu = self.emu
        for index, raw in enumerate(fregs):
            emu.f[12 + index] = raw
        return emu.call(addr, *[a & M64 for a in args], sp=self.sp, max_steps=max_steps)

    def set_game(self, game, seed):
        mem = self.mem
        mem.w32(G_NUM_PLAYERS, game.num_players)
        for slot in range(4):
            mem.w32(G_PLAYERS + PLAYER_STRIDE * slot + PLAYER_CLASS, game.classes[slot])
        mem.w32(G_DIFFICULTY, game.difficulty)
        mem.w32(G_PVP_A, game.pvp_a)
        mem.w32(G_PVP_B, game.pvp_b)
        mem.w32(G_LEVEL, game.level)
        mem.w32(G_SEED, seed)

    def seed(self):
        return self.mem.u32(G_SEED)

    def put_text(self, text, where=None):
        where = self.text if where is None else where
        self.mem.write(where, text + b'\0')
        return where

    # ---- the item functions ------------------------------------------------------------
    def parse(self, text, variant, presets, seed, stale):
        mem = self.mem
        self.put_text(text)
        mem.write(self.rec, b'\xEE' * 0x48)
        mem.w32(G_SEED, seed)
        mem.write(self.sp - PARSER_FRAME + PARSER_RECORD, stale)
        self.call(F_PARSE, self.text, self.rec, variant, presets)
        return mem.read(self.rec, 0x48), mem.u32(G_SEED)

    def generator(self, addr, game, seed, args):
        mem = self.mem
        self.set_game(game, seed)
        mem.write(self.rec, b'\xEE' * 0x48)
        result = self.call(addr, self.rec, *args) & 0xFFFFFFFF
        return result, mem.read(self.rec, 0x48), mem.u32(G_SEED)


# ---------------------------------------------------------------------------------------
# Per-process state and sample generators
# ---------------------------------------------------------------------------------------
_CACHE = {}


def tables(elf):
    if ('tables', elf) not in _CACHE:
        _CACHE[('tables', elf)] = R.Tables(elf)
    return _CACHE[('tables', elf)]


def original(elf, fast=False, fpu_model='ps2', mul_bias=False):
    key = ('orig', elf, bool(fast), fpu_model, mul_bias)
    if key not in _CACHE:
        _CACHE[key] = Original(elf, bool(fast), fpu_model, mul_bias)
    _CACHE[key].reset_hooks()
    return _CACHE[key]


def random_float(rng):
    kind = rng.randrange(6)
    if kind == 0:
        return rng.getrandbits(32)
    if kind == 1:
        return R.f_bits(rng.uniform(-1000, 1000))
    if kind == 2:
        return R.f_bits(rng.randrange(-70000, 70000))
    if kind == 3:
        return rng.choice([0, 0x80000000, 0x7FFFFFFF, 0xFFFFFFFF, 0x3F800000, 0x00800000, 1, 0x7F7FFFFF])
    if kind == 4:
        return R.f_bits(rng.uniform(0, 1e-3))
    return R.f_bits(rng.uniform(-1e30, 1e30))


def random_game(rng):
    return R.Game(rng.choice([1, 1, 2, 3, 4]), [rng.choice([0, 1, 2, 3, 4, 4, 5, 6]) for _ in range(4)],
                  rng.choice([1, 1, 2, 3, 4, 5]), rng.choice([0, 0, 0, 1]), rng.choice([0, 0, 0, 1]),
                  level=rng.choice([1.0, 1.5, 2.0, 3.0, 4.75, 5.0, 6.0, 8.0, 10.0, 13.0, 17.0, 22.0,
                                    28.0, 35.0, 44.0, 54.0, 60.0, 75.0]))


def random_number_text(rng):
    kind = rng.randrange(12)
    if kind == 0:
        return b'-%d' % rng.randrange(0, 200)
    if kind == 1:
        return b'%d' % rng.randrange(0, 100000)
    if kind == 2:
        return b'%d' % rng.randrange(-2 ** 40, 2 ** 40)
    if kind == 3:
        return rng.choice([b' ', b'\t', b'  ']) + b'%d' % rng.randrange(0, 50)
    if kind == 4:
        return b'+%d' % rng.randrange(0, 50)
    if kind == 5:
        return b'0%d' % rng.randrange(0, 50)
    if kind == 6:
        return b'%d' % rng.randrange(-2 ** 70, 2 ** 70)
    return b'%d' % rng.randrange(0, 120)


def random_token(t, rng):
    kind = rng.randrange(22)
    word = rng.choice(t.token_words)
    if kind == 0:
        return b''
    if kind == 1:
        return word[:rng.randrange(len(word) + 1)]
    if kind == 2:
        return word
    if kind == 3:
        return word + rng.choice([b'-', b'+', b' ', b' -', b'x'])
    if kind == 4:
        return bytes(rng.choice(b'abcdefghijklmnopqrstuvwxyz0123456789-,% ') for _ in range(rng.randrange(1, 12)))
    text = word + random_number_text(rng)
    for _ in range(rng.randrange(0, 4)):
        text += rng.choice([b'-', b',', b'-', b',', b' ', b'x', b'']) + random_number_text(rng)
    if kind == 5:
        text += b'abc'
    if kind == 6:
        text = text.upper()
    return text


def random_descriptor(t, rng):
    while True:
        base = rng.choice(t.defs).name
        if rng.random() < 0.1:
            base = rng.choice([b'', b'no such item', rng.choice(t.presets).name.split(b'+')[0], base.upper()])
        tokens = [random_token(t, rng) for _ in range(rng.randrange(0, 7))]
        if rng.random() < 0.9:
            tokens = [token.replace(b'+', b'') for token in tokens]
        text = b'+'.join([base] + tokens)
        if len(text) < 200:
            return text


def random_item(t, rng):
    """An item record with arbitrary modifiers, including ones no descriptor can make
    (repeated codes, holes, code 0x29, out-of-range values)."""
    d = rng.choice(t.defs) if rng.random() < 0.8 else rng.choice(t.presets)
    item = R.Item(d)
    item.count = rng.choice([d.count, d.count, 1, 2, 5, 20, 40, 99, 0, -1, 32767])
    item.flags = d.flags ^ (rng.getrandbits(5) << 11 if rng.random() < 0.3 else 0)
    item.prefix = rng.choice([0xFF, rng.randrange(len(t.prefixes))])
    item.suffix = rng.choice([0xFF, rng.randrange(len(t.suffixes))])

    def value():
        kind = rng.randrange(10)
        if kind == 0:
            return rng.randrange(-100, 0)
        if kind == 1:
            return rng.randrange(-32768, 32768)
        if kind == 2:
            return 0
        return rng.randrange(0, 150)

    for _ in range(rng.randrange(0, 5)):
        mod = [rng.randrange(0, 0x2B), value(), value(), value() if rng.random() < 0.5 else 0]
        if rng.random() < 0.5 and mod[0] in (0x15, 0x16, 0x17, 0x18, 0x26, 0x19):
            mod[2], mod[3] = min(mod[1] + rng.randrange(0, 30), 32767), 0
        if rng.random() < 0.9:
            item.set_modifier(*mod)
        else:
            item.mods[rng.randrange(4)] = mod
    return item


def stale_bytes(rng):
    return bytes(rng.getrandbits(8) for _ in range(0x48))


def show_item(raw):
    return raw.hex()


def compare_generated(t, tag, info, result, raw, seed, item, model_seed, bad):
    """A generator's output: return value, every byte of the record that the original
    defines, and the seed."""
    ok = (item is None) == (result == 0) and seed == model_seed
    if ok and item is not None:
        ok = item.pack(raw) == raw
    if not ok:
        bad.append('%s %s: original returned %d, record %s, seed %08x; model %s, seed %08x'
                   % (tag, info, result, raw.hex(), seed, item.pack().hex() if item else None, model_seed))
    return ok


# ---------------------------------------------------------------------------------------
# Properties.  Each worker takes (elf, seed, count, extra) and returns (cases, mismatches,
# counters) where counters is a dict of things worth reporting.
# ---------------------------------------------------------------------------------------
def w_powf(elf, seed, count, extra):
    o, rng = original(elf), random.Random(seed)
    exponents = sorted(set(R._VALUE_EXPONENT.values()) | {0x3FF99999, 0x3F28F5C2})
    bad, done, skipped = [], 0, 0
    for _ in range(count):
        kind = rng.randrange(8)
        if kind == 0:
            x = R.fint(rng.randrange(0, 2000))
        elif kind == 1:
            x = R.f_bits(rng.uniform(0, 500))
        elif kind == 2:
            x = R.fint(rng.randrange(-300, 40000))
        elif kind == 3:
            x = random_float(rng)
        elif kind == 4:
            x = R.f_bits(rng.uniform(0.9, 1.1))
        elif kind == 5:
            x = R.f_bits(rng.uniform(0, 1e-2))
        elif kind == 6:
            x = R.f_bits(rng.uniform(0, 1e9))
        else:
            x = rng.choice([0, 0x3F800000, 0xBF800000, 0x80000000, 0x40000000, 0x7FFFFFFF, 0x00800000])
        y = rng.choice(exponents) if rng.random() < 0.8 else random_float(rng)
        try:
            got = R.powf(x, y)
        except NotImplementedError:
            skipped += 1
            continue
        o.call(F_POWF, fregs=(x, y))
        done += 1
        if o.emu.f[0] != got:
            bad.append('powf(%08x, %08x): original %08x, model %08x' % (x, y, o.emu.f[0], got))
    return done, bad, {'skipped': skipped}


def w_float_double(elf, seed, count, extra):
    o, t, rng = original(elf), tables(elf), random.Random(seed)
    bad = []
    for _ in range(count):
        kind = rng.randrange(5)
        if kind == 0:
            x = R.f_bits(rng.uniform(0, 4))
        elif kind == 1:
            x = R.f_bits(rng.randrange(0, 3000) / 100.0)
        elif kind == 2:
            x = R.f_bits(rng.uniform(-1e30, 1e30))
        elif kind == 3:
            x = rng.getrandbits(32)
        else:
            x = rng.choice([0, 0x80000000, 0x3F800000, 0x00800000, 0x7F7FFFFF, 0x7F800000, 0x7FFFFFFF, 1])
        factor = rng.choice([1.5, t.gold_scale_multiplayer, rng.uniform(0.1, 9.0)])
        wide = o.call(F_EXTEND, fregs=(x,))
        product = o.call(F_MULDF, wide, struct.unpack('<Q', struct.pack('<d', factor))[0])
        o.call(F_TRUNCDF, product)
        got = R.float_times_double(x, factor)
        if o.emu.f[0] != got:
            bad.append('(float)((double)%08x * %r): original %08x, model %08x' % (x, factor, o.emu.f[0], got))
    return count, bad, {}


def w_sscanf(elf, seed, count, extra):
    o, t, rng = original(elf), tables(elf), random.Random(seed)
    mem, bad, done = o.mem, [], 0
    for index, (fmt_addr, _code) in enumerate(R.TOKEN_FORMATS):
        fmt = t.formats[index][0]
        for _ in range(count):
            token = random_token(t, rng)
            if rng.random() < 0.6:                  # make the word match this format
                token = t.token_words[index] + token[len(rng.choice(t.token_words)):] \
                    if rng.random() < 0.3 else t.token_words[index] + random_number_text(rng) + \
                    rng.choice([b'', b'-', b',', b'-5', b',7', b',7-9', b'-4-3', b' ', b'x'])
            sentinels = [rng.getrandbits(32) for _ in range(3)]
            mem.write(o.ints, struct.pack('<3I', *sentinels))
            o.put_text(token)
            result = ee_emu.s32(o.call(F_SSCANF, o.text, fmt_addr, o.ints, o.ints + 4, o.ints + 8))
            got = list(struct.unpack('<3i', mem.read(o.ints, 12)))
            want_result, values = R.scan(fmt, token)
            want = values + [ee_emu.s32(s) for s in sentinels[len(values):]]
            done += 1
            if result != want_result or got != want:
                bad.append('sscanf(%r, %r): original %d %r, model %d %r' % (token, fmt, result, got, want_result, want))
    return done, bad, {}


def _parse_case(o, t, rng, text, variant, presets, bad):
    seed, stale = rng.getrandbits(32), stale_bytes(rng)
    raw, after = o.parse(text, variant, presets, seed, stale)
    model_rng = R.Rng(seed)
    item = R.parse_descriptor(t, text, variant, presets, model_rng)
    if raw != item.pack(stale) or after != model_rng.seed:
        bad.append('parse(%r, variant %d, presets %d, seed %08x): original %s seed %08x, model %s seed %08x'
                   % (text, variant, presets, seed, raw.hex(), after, item.pack(stale).hex(), model_rng.seed))
    return model_rng.draws


def w_parse_tables(elf, seed, count, extra):
    """extra = (first, last) slice of the list: base names, presets as presets, presets
    as plain descriptors."""
    o, t, rng = original(elf), tables(elf), random.Random(seed)
    cases = [(d.name, 0) for d in t.defs] + [(d.name, 1) for d in t.presets] + [(d.name, 0) for d in t.presets]
    bad, draws = [], 0
    for text, presets in cases[extra[0]:extra[1]]:
        draws += _parse_case(o, t, rng, text, -1, presets, bad)
    return len(cases[extra[0]:extra[1]]), bad, {'draws': draws}


def w_parse_random(elf, seed, count, extra):
    o, t, rng = original(elf), tables(elf), random.Random(seed)
    bad, draws = [], 0
    for _ in range(count):
        text = random_descriptor(t, rng)
        variant = rng.choice([-1, -1, -1, -1, 0, 1, 5, 31, 32, 100, -2, 0x7FFFFFFF, -0x80000000])
        presets = rng.choice([0, 0, 0, 1])
        if presets and rng.random() < 0.5:
            text = rng.choice(t.presets).name
        draws += _parse_case(o, t, rng, text, variant, presets, bad)
    return count, bad, {'draws': draws}


def _stat_case(o, t, item, stale, bad, what):
    mem = o.mem
    mem.write(o.rec, item.pack(stale))
    label = item.pack(stale).hex()
    if 'value' in what:
        got, want = ee_emu.s32(o.call(F_VALUE, o.rec)), R.item_value(t, item)
        if got != want:
            bad.append('value of %s: original %d, model %d' % (label, got, want))
    if 'stats' in what:
        o.call(F_WEIGHT, o.rec)
        if o.emu.f[0] != R.item_weight(item):
            bad.append('weight of %s: original %08x, model %08x' % (label, o.emu.f[0], R.item_weight(item)))
        got = ee_emu.s32(o.call(F_ARMOR, o.rec))
        if got != R.item_armor(item):
            bad.append('armour of %s: original %d, model %d' % (label, got, R.item_armor(item)))
        got = ee_emu.s32(o.call(F_ATTACK, o.rec))
        if got != R.item_attack_rating(item):
            bad.append('attack rating of %s: original %d, model %d' % (label, got, R.item_attack_rating(item)))
        for elemental in (0, 1):
            o.call(F_DAMAGE, o.rec, o.ints, o.ints + 4, elemental)
            got = (mem.s32(o.ints), mem.s32(o.ints + 4))
            want = R.item_damage_range(item, bool(elemental))
            if got != want:
                bad.append('damage(%d) of %s: original %r, model %r' % (elemental, label, got, want))
        got = ee_emu.s32(o.call(F_RESOURCE, o.rec))
        if got != R.resource_index(item):
            bad.append('model row of %s: original %d, model %d' % (label, got, R.resource_index(item)))


def w_stats_random(elf, seed, count, extra):
    o, t, rng = original(elf), tables(elf), random.Random(seed)
    bad = []
    for _ in range(count):
        _stat_case(o, t, random_item(t, rng), stale_bytes(rng), bad, extra)
    return count, bad, {}


def w_stats_tables(elf, seed, count, extra):
    """Every definition and preset as the parser builds it."""
    o, t, rng = original(elf), tables(elf), random.Random(seed)
    rows = ([(d, 0) for d in t.defs] + [(d, 1) for d in t.presets])[extra[0]:extra[1]]
    bad = []
    for d, presets in rows:
        item = R.parse_descriptor(t, d.name, -1, presets, R.Rng(rng.getrandbits(32)))
        _stat_case(o, t, item, stale_bytes(rng), bad, ('value', 'stats'))
    return len(rows), bad, {}


def w_small(elf, seed, count, extra):
    """Classification of every definition, and the record helpers on random pairs."""
    o, t, rng = original(elf), tables(elf), random.Random(seed)
    mem, bad, done = o.mem, [], 0
    for d in t.defs + t.presets:
        for addr, model in ((F_GROUP0, R.weapon_group), (F_GROUP1, R.armor_group)):
            got = ee_emu.s32(o.call(addr, d.addr))
            done += 1
            if got != model(d):
                bad.append('group function %x of %r: original %d, model %d' % (addr, d, got, model(d)))
    for _ in range(count):
        a, b = random_item(t, rng), random_item(t, rng)
        if rng.random() < 0.5:
            b = a.copy()
            if rng.random() < 0.5:
                b.suffix ^= rng.choice([0, 1])
        raw_a, raw_b = a.pack(stale_bytes(rng)), b.pack(stale_bytes(rng))
        if rng.random() < 0.7:                      # +0x22 is part of the compared word
            raw_b = raw_b[:0x22] + raw_a[0x22:0x24] + raw_b[0x24:]
        mem.write(o.rec, raw_a)
        mem.write(o.rec2, raw_b)
        got = o.call(F_SAME, o.rec, o.rec2) & 0xFFFFFFFF
        want = int(R.same_identity(a, b) and raw_a[0x22:0x24] == raw_b[0x22:0x24])
        done += 1
        if got != want:
            bad.append('same identity %s / %s: original %d, model %d' % (raw_a.hex(), raw_b.hex(), got, want))
        o.call(F_COPY, o.rec2, o.rec)
        got_raw = mem.read(o.rec2, 0x48)
        target = R.Item.unpack(t, raw_b)
        R.copy_mutable(target, a)
        want_raw = bytearray(raw_b)
        want_raw[4:6], want_raw[8:0x24], want_raw[0x24:0x44] = raw_a[4:6], target.pack()[8:0x24], raw_a[0x24:0x44]
        done += 1
        if got_raw != bytes(want_raw):
            bad.append('copy %s onto %s: original %s, model %s' % (raw_a.hex(), raw_b.hex(), got_raw.hex(), bytes(want_raw).hex()))
        o.call(F_ENCODE, o.rec)
        index = mem.s32(o.rec)
        o.call(F_DECODE, o.rec)
        done += 1
        if index != R.encode_definition_index(t, a) or mem.u32(o.rec) != a.definition.addr \
                or R.decode_definition_index(t, index) is not a.definition:
            bad.append('definition index of %r: original %d, model %d' % (a.definition, index, R.encode_definition_index(t, a)))
    return done, bad, {}


def w_preset(elf, seed, count, extra):
    o, t, rng = original(elf, extra), tables(elf), random.Random(seed)
    bad, made = [], 0
    for _ in range(count):
        game, start = random_game(rng), rng.getrandbits(32)
        budget = rng.choice([0, 50, 300, 1000, 5000, 20000, 100000, 1000000, rng.randrange(1, 60000)])
        category, level = rng.choice([-1, 0, 1, 1, 2]), rng.choice([0, 1, 2, 3, 5, 8, 20, 60])
        result, raw, seed_after = o.generator(F_PRESET, game, start, [budget, category, level])
        model_rng = R.Rng(start)
        item = R.generate_preset(t, game, model_rng, budget, category, level)
        made += item is not None
        compare_generated(t, 'preset', (budget, category, level, '%08x' % start), result, raw, seed_after,
                          item, model_rng.seed, bad)
    return count, bad, {'made': made}


def w_affix(elf, seed, count, extra):
    o, t, rng = original(elf, extra), tables(elf), random.Random(seed)
    bad, made, draws = [], 0, 0
    for _ in range(count):
        game, start = random_game(rng), rng.getrandbits(32)
        budget = rng.choice([0, 50, 300, 1000, 5000, 20000, 100000, 1000000, rng.randrange(1, 60000)])
        category, want_suffix = rng.choice([0, 0, 1, 1, 2, -1]), rng.choice([-1, -1, 0, 1, 2])
        level = rng.choice([1, 2, 3, 5, 8, 12, 20, 33, 47, 66, 80, 120])
        result, raw, seed_after = o.generator(F_AFFIX, game, start, [budget, category, want_suffix, level])
        model_rng = R.Rng(start)
        item = R.generate_with_affixes(t, game, model_rng, budget, category, want_suffix, level)
        made += item is not None
        draws += model_rng.draws
        compare_generated(t, 'affix', (budget, category, want_suffix, level, '%08x' % start), result, raw,
                          seed_after, item, model_rng.seed, bad)
    return count, bad, {'made': made, 'draws': draws}


def w_plain_generators(elf, seed, count, extra):
    """Reagent (with and without a picture filter), figurine and consumable."""
    o, t, rng = original(elf), tables(elf), random.Random(seed)
    pictures = sorted({d.picture for d in t.defs if d.flags & 0x800000000 and d.picture})
    bad, made = [], 0
    for _ in range(count):
        game, start = random_game(rng), rng.getrandbits(32)
        level = rng.choice([0, 1, 3, 5, 10, 17, 25, 30, 40, 55, 70, 107, 200, -5, 0x10003])
        kind = rng.randrange(4)
        model_rng = R.Rng(start)
        if kind == 0:
            result, raw, after = o.generator(F_REAGENT, game, start, [level, 0])
            item = R.generate_reagent(t, game, model_rng, level)
        elif kind == 1:
            picture = rng.choice(pictures) if rng.random() < 0.9 else b'no such picture'
            o.put_text(picture, o.text2)
            result, raw, after = o.generator(F_REAGENT, game, start, [level, o.text2])
            item = R.generate_reagent(t, game, model_rng, level, picture)
        elif kind == 2:
            result, raw, after = o.generator(F_FIGURINE, game, start, [level])
            item = R.generate_figurine(t, game, model_rng, level)
        else:
            if rng.random() < 0.3:
                game.level = R.f_bits(rng.uniform(0, 40))
            result, raw, after = o.generator(F_CONSUMABLE, game, start, [])
            item = R.generate_consumable(t, game, model_rng)
            result = 1
        made += item is not None
        compare_generated(t, ('reagent', 'reagent by picture', 'figurine', 'consumable')[kind],
                          (level, game.difficulty, '%08x' % start), result, raw, after, item, model_rng.seed, bad)
    return count, bad, {'made': made}


def w_shop(elf, seed, count, extra):
    o, t, rng = original(elf, True), tables(elf), random.Random(seed)
    mem, bad, done, skipped, appended = o.mem, [], 0, 0, 0
    for _ in range(count):
        game, start = random_game(rng), rng.getrandbits(32)
        budget, category = rng.choice([300, 2000, 20000, 500000]), rng.choice([0, 1, 2])
        stock = []
        model_rng = R.Rng(start)
        mem.write(o.stock, b'\xEE' * 0x1200 + bytes(16))
        o.set_game(game, start)
        ok = True
        for _round in range(rng.randrange(1, 5)):
            try:
                entry = R.shop_append_unique(t, game, model_rng, stock, budget, category)
            except NotImplementedError:
                skipped += 1
                ok = False
                break
            o.call(F_SHOP_APPEND, o.stock, budget, 0, category)
            appended += entry is not None
        if not ok:
            continue
        done += 1
        got_count = mem.s32(o.stock + 0x1200)
        got = [(mem.u32(o.stock + 0x48 * i), mem.s16(o.stock + 0x48 * i + 4), mem.u64(o.stock + 0x48 * i + 8))
               for i in range(min(max(got_count, 0), 64))]
        want = [(e.definition.addr, e.count, e.flags) for e in stock]
        if got_count != len(stock) or got != want or o.seed() != model_rng.seed:
            bad.append('shop stock (%d, %d, %08x): original %r seed %08x, model %r seed %08x'
                       % (budget, category, start, got, o.seed(), want, model_rng.seed))
    return done, bad, {'skipped': skipped, 'appended': appended}


class ScriptedWorld(R.World):
    """Model-side world that mirrors the replacements used on the original: every object
    made takes `ctor_draws` values from the shared generator, and the pool refuses the
    allocations listed in `refusals`."""

    def __init__(self, ctor_draws, refusals):
        R.World.__init__(self)
        self.ctor_draws, self.refusals, self.allocations = ctor_draws, refusals, 0

    def spawn_gold(self, amount, rng):
        self.drops.append(('gold', amount))

    def spawn_item(self, kind, item, rng):
        self.allocations += 1
        if self.allocations in self.refusals:
            return False
        self.drops.append((kind, item))
        for _ in range(self.ctor_draws):
            rng.next()
        return True


LOOT_SITES = {0x101230: 'consumable', 0x1013F4: 'reagent', 0x101560: 'figurine', 0x1018A8: 'equipment'}


def w_loot(elf, seed, count, extra):
    boost, fast = extra
    o, t, rng = original(elf, fast), tables(elf), random.Random(seed)
    emu, mem = o.emu, o.mem
    pictures = sorted({d.picture for d in t.defs if d.flags & 0x800000000 and d.picture})
    state = {}

    def spawn_gold(e):
        state['log'].append(('gold', ee_emu.s32(e.r[5])))

    def pool_new(e):
        state['allocations'] += 1
        return 0 if state['allocations'] in state['refusals'] else o.obj

    def phprop_ctor(e):
        site = (e.r[31] - 8) & 0xFFFFFFFF
        state['log'].append((LOOT_SITES.get(site, 'site %x' % site), mem.read(e.r[11], 0x48)))
        position = struct.unpack('<3I', mem.read(e.r[5], 12))
        state['positions'].append(position)
        for _ in range(state['ctor_draws']):
            mem.w32(G_SEED, (mem.u32(G_SEED) * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF)

    def cos16(e):
        state['log'].append(('throw', ee_emu.s32(e.r[4])))
        e.f[0] = 0x3F000000

    def sin16(e):
        e.f[0] = 0x3F400000

    for addr, function in ((F_SPAWN_GOLD, spawn_gold), (F_POOL_NEW, pool_new), (F_PHPROP_CTOR, phprop_ctor),
                           (F_COS16, cos16), (F_SIN16, sin16), (F_PHPROP_PHYS, None)):
        emu.stub(addr, function=function)
    bad = []
    counters = {'gold': 0, 'consumable': 0, 'reagent': 0, 'figurine': 0, 'equipment': 0, 'draws': 0,
                'early': 0, 'refused': 0}
    for _ in range(count):
        game, start = random_game(rng), rng.getrandbits(32)
        boosted = rng.random() < boost          # raise the rare chances so every branch is reached
        gold_scale = R.f_bits(rng.choice([0.5, 1.0, 1.8, 3.0, 6.0]))
        gold_chance = R.f_bits(rng.choice([0.0, 0.25, 0.6, 1.0]))
        quality = R.f_bits(rng.choice([0.0, 0.5, 1.0, 2.0, 2.75, 4.0, 6.5, 8.0, 9.0, 9.5, 12.0, -1.0, 36.0]))
        item_chance = R.f_bits(rng.choice([0.0, 0.05, 0.25, 0.5, 1.0]) if not boosted else 1.0)
        z_offset, speed = R.f_bits(rng.choice([0.0, 36.0])), R.f_bits(rng.choice([1.0, 2.0]))
        angle = rng.randrange(-0x8000, 0x10000)
        picture = rng.choice(pictures + [b'no such picture']) if rng.random() < 0.25 else None
        force = rng.random() < 0.2
        position = [R.f_bits(rng.uniform(-3000, 3000)) for _ in range(3)]
        ctor_draws = rng.choice([0, 1, 1])
        refusals = {rng.randrange(1, 4)} if rng.random() < 0.1 else set()
        if boosted:
            # the chances of the reagent and figurine rolls are constants in the code; a
            # start seed is searched instead so that those rolls succeed in some cases
            start = _seed_with_rare_rolls(t, game, rng, gold_scale, gold_chance, quality, item_chance,
                                          angle, picture, force, start)
        state.update(log=[], positions=[], allocations=0, refusals=refusals, ctor_draws=ctor_draws)
        o.set_game(game, start)
        mem.write(o.vec, struct.pack('<3I', *position))
        if picture is not None:
            o.put_text(picture, o.text2)
        o.call(F_LOOT, o.vec, angle, o.text2 if picture is not None else 0, int(force),
               fregs=(z_offset, speed, gold_scale, gold_chance, quality, item_chance))
        world = ScriptedWorld(ctor_draws, refusals)
        model_rng = R.Rng(start)
        ending = R.loot_generate_drops(t, game, model_rng, world, gold_scale, gold_chance, quality,
                                       item_chance, angle, picture, force)
        counters['early'] += ending in ('no reagent', 'no figurine')
        counters['refused'] += bool(refusals & set(range(1, world.allocations + 1)))
        ok = len(world.drops) == len(state['log']) and o.seed() == model_rng.seed
        if ok:
            for (kind, got), (model_kind, want) in zip(state['log'], world.drops):
                if kind != model_kind:
                    ok = False
                elif kind in ('gold', 'throw'):
                    ok = ok and got == want
                else:
                    ok = ok and want.pack(got) == got
        expected_position = (R.fadd(position[0], 0), position[1], R.fadd(position[2], z_offset))
        ok = ok and all(p == expected_position for p in state['positions'])
        for kind, _what in world.drops:
            if kind in counters:
                counters[kind] += 1
        counters['draws'] += model_rng.draws
        if not ok:
            bad.append('loot seed %08x players %d difficulty %d level %08x pvp %d/%d args %08x %08x %08x %08x '
                       'filter %r force %d: original %r seed %08x; model %r seed %08x'
                       % (start, game.num_players, game.difficulty, game.level, game.pvp_a, game.pvp_b,
                          gold_scale, gold_chance, quality, item_chance, picture, force,
                          [(k, v if isinstance(v, int) else v.hex()) for k, v in state['log']], o.seed(),
                          [(k, v if isinstance(v, int) else v.pack().hex()) for k, v in world.drops],
                          model_rng.seed))
    return count, bad, counters


def _seed_with_rare_rolls(t, game, rng, gold_scale, gold_chance, quality, item_chance, angle, picture,
                          force, start):
    """A start seed for which the reagent or the figurine roll succeeds.  Those chances
    are constants in the code, so seeds are tried with the model (with the equipment
    roll switched off, which comes later and does not change the earlier draws); the
    original is then run on the seed found."""
    for _ in range(600):
        world = R.World()
        ending = R.loot_generate_drops(t, game, R.Rng(start), world, gold_scale, gold_chance, quality,
                                       0, angle, picture, force)
        if ending != 'no equipment roll' or any(kind in ('reagent', 'figurine') for kind, _ in world.drops):
            return start
        start = rng.getrandbits(32)
    return start


def w_gold(elf, seed, count, extra):
    """loot_spawnGold with the terrain query, the allocator and the Gold constructor
    replaced; the terrain heights are scripted."""
    o, rng = original(elf), random.Random(seed)
    emu, mem = o.emu, o.mem
    state = {}

    def terrain(e):
        state['queries'].append(struct.unpack('<3I', mem.read(e.r[5], 12)) + (e.f[12],))
        e.f[0] = state['heights'][len(state['queries']) - 1]

    def gold_ctor(e):
        state['made'] = struct.unpack('<3I', mem.read(e.r[5], 12)) + (ee_emu.s32(e.r[6]),)

    emu.stub(F_TERRAIN, function=terrain)
    emu.stub(F_POOL_NEW, ret=o.obj)
    emu.stub(F_GOLD_CTOR, function=gold_ctor)
    bad = []
    for _ in range(count):
        start = rng.getrandbits(32)
        position = [R.f_bits(rng.uniform(-3000, 3000)) for _ in range(3)]
        amount = rng.choice([1, 5, 40, 300, 0, -3])
        near = rng.random()
        heights = [R.fadd(position[2], R.f_bits(rng.uniform(-5.9, 5.9) if rng.random() < near
                                                else rng.choice([6.0, -6.0, 7.5, -40.0, -1000000.0])))
                   for _ in range(10)]
        state.update(queries=[], heights=heights, made=None)
        mem.w32(G_SEED, start)
        mem.write(o.vec, struct.pack('<3I', *position))
        o.call(F_SPAWN_GOLD, o.vec, amount)
        model_rng, queries = R.Rng(start), []

        def ground(x, y, z):
            queries.append((x, y, z, 0x41400000))
            return heights[len(queries) - 1]

        want = None
        if amount > 0:
            want = R.gold_scatter(model_rng, ground, *position) + (amount,)
        if state['made'] != want or state['queries'] != queries or o.seed() != model_rng.seed:
            bad.append('gold scatter seed %08x amount %d: original %r after %d queries, seed %08x; model %r '
                       'after %d, seed %08x' % (start, amount, state['made'], len(state['queries']), o.seed(),
                                                want, len(queries), model_rng.seed))
    return count, bad, {}


def w_equip(elf, seed, count, extra):
    """inventory_checkEquipAllowed with a player record written into g_players."""
    o, t, rng = original(elf), tables(elf), random.Random(seed)
    mem, bad, reasons = o.mem, [], {}
    for _ in range(count):
        slot = rng.randrange(4)
        item = random_item(t, rng)
        if rng.random() < 0.5:                       # requirements near the player's numbers
            item.mods = [None] * 4
            for code in rng.sample([0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x27, 0x28], rng.randrange(0, 4)):
                item.set_modifier(code, rng.randrange(0, 9) if code in (0x13, 0x27, 0x28) else rng.randrange(0, 60))
        if rng.random() < 0.15:
            item.flags ^= rng.choice([0x80000, 0x1000000000, 0x80000000000, 0x20000000000])
        skills = {skill: rng.randrange(0, 6) for skill in rng.sample([0x3C, 0x3D, 0x5C, 0x21, 0x40], rng.randrange(0, 4))}
        player = R.Player(rng.randrange(0, 7), rng.choice([rng.randrange(1, 60), 1, 80, -3]),
                          *[rng.randrange(0, 70) for _ in range(4)], skills=skills)
        base = G_PLAYERS + PLAYER_STRIDE * slot
        mem.w32(base + PLAYER_CLASS, player.class_id)
        mem.w8(base + PLAYER_LEVEL, player.level & 0xFF)
        for index, value in enumerate((player.strength, player.intelligence, player.dexterity, player.stamina)):
            mem.w32(base + PLAYER_STATS + 4 * index, value)
        pairs = list(skills.items())
        rng.shuffle(pairs)
        mem.write(base + PLAYER_SKILLS, b''.join(struct.pack('<hh', k, v) for k, v in pairs) + struct.pack('<h', -1))
        mem.write(o.rec, item.pack(stale_bytes(rng)))
        got = o.call(F_EQUIP_CHECK, slot, o.rec) & 0xFF
        want = R.equip_restriction(t, player, item)
        reasons[want] = reasons.get(want, 0) + 1
        if got != want:
            bad.append('equip check class %d level %d stats %r skills %r item %s: original %d, model %d'
                       % (player.class_id, player.level, (player.strength, player.intelligence,
                                                           player.dexterity, player.stamina), skills,
                          item.pack().hex(), got, want))
    return count, bad, {'r%d' % reason: reasons.get(reason, 0) for reason in range(10)}


def w_load_resources(elf, seed, count, extra):
    """item_loadResources with res_find replaced: only its effect on the seed."""
    o, t, rng = original(elf, extra), tables(elf), random.Random(seed)
    o.emu.stub(F_RES_FIND, ret=o.obj)
    bad, draws = [], 0
    for _ in range(count):
        start = rng.getrandbits(32)
        o.mem.w32(G_SEED, start)
        o.call(F_LOAD_RESOURCES)
        model_rng = R.Rng(start)
        draws += R.load_resources(t, model_rng)
        if o.seed() != model_rng.seed:
            bad.append('load resources from seed %08x: original %08x, model %08x' % (start, o.seed(), model_rng.seed))
    return count, bad, {'draws': draws}


def w_named(elf, seed, count, extra):
    """loot_spawnNamedItem with world_findFreeSpot, pool_new and PhProp_ctor replaced."""
    o, t, rng = original(elf), tables(elf), random.Random(seed)
    emu, mem = o.emu, o.mem
    state = {}

    def ctor(e):
        state['made'] = mem.read(e.r[11], 0x48)

    emu.stub(F_FIND_FREE_SPOT)
    emu.stub(F_POOL_NEW, ret=o.obj)
    emu.stub(F_PHPROP_CTOR, function=ctor)
    bad = []
    for _ in range(count):
        text = random_descriptor(t, rng) if rng.random() < 0.5 else rng.choice(t.defs).name
        start = rng.getrandbits(32)
        state['made'] = None
        mem.w32(G_SEED, start)
        mem.write(o.vec, struct.pack('<3I', *[R.f_bits(rng.uniform(-900, 900)) for _ in range(3)]))
        o.put_text(text)
        o.call(F_SPAWN_NAMED, o.vec, o.text)
        world, model_rng = R.World(), R.Rng(start)
        item = R.spawn_named_item(t, model_rng, world, text)
        if state['made'] is None or item.pack(state['made']) != state['made'] or o.seed() != model_rng.seed:
            bad.append('named drop %r seed %08x: original %s seed %08x, model %s seed %08x'
                       % (text, start, state['made'] and state['made'].hex(), o.seed(), item.pack().hex(), model_rng.seed))
    return count, bad, {}


# ---- names ---------------------------------------------------------------------------
_LETTERS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZéüßœ€\'-'
_TAGS = {4: ['_m', '_f', '_n', '_p', '_M', '_F', '_N', '_P', '_x', ''],
         1: ['_ms', '_fs', '_mp', '_fp', '_MS', '_Fp', '_m', '_f', '_M', '_xy', '_xs', ''],
         3: ['_ms', '_fs', '_mp', '_fp', '_mS', '_FP', '_m', '_F', '_qq', '_p', '']}


def synthetic_text(seed, language):
    """An invented string table: every key gets a word, sometimes with a grammar tag,
    sometimes as four bar-separated alternatives.  No game text."""
    cache = {}

    def lookup(key):
        if key not in cache:
            rng = random.Random('%d/%d/%s' % (seed, language, key))

            def word(tagged):
                text = ''.join(rng.choice(_LETTERS) for _ in range(rng.randrange(3, 10)))
                if rng.random() < 0.2:
                    text += ' ' + ''.join(rng.choice(_LETTERS) for _ in range(rng.randrange(2, 6)))
                if tagged and rng.random() < 0.8:
                    text += rng.choice(_TAGS.get(language, ['_m', '_fs', '']))
                return text

            if rng.random() < 0.4:
                cache[key] = '|'.join(word(rng.random() < 0.8) for _ in range(4))
            else:
                cache[key] = word(rng.random() < 0.7)
        return cache[key]

    return lookup


def read_text_file(data):
    """key -> text of a GTEXT*.LMP or an extracted gtext.uni (first entry of a key wins)."""
    count = struct.unpack_from('<I', data, 0)[0]
    if count < 100000 and 4 + count * 12 <= len(data):
        for index in range(count):
            name_at, at, size = struct.unpack_from('<III', data, 4 + index * 12)
            if name_at < len(data) and data[name_at:data.index(b'\0', name_at)].lower() == b'gtext.uni':
                data = data[at:at + size]
                break
    table, pos = {}, 0
    while pos < len(data) and data[pos] != 0:
        end = data.index(b'\0', pos)
        key = data[pos:end].decode('latin-1')
        pos = (end + 2) & ~1
        start = pos
        while pos + 1 < len(data) and data[pos:pos + 2] != b'\0\0':
            pos += 2
        table.setdefault(key, data[start:pos].decode('utf-16-le', 'replace'))
        pos += 2
    return table


_TEXT_FILES = {}


def w_names(elf, seed, count, extra):
    """extra = (label, path or None, offset, size).  The text lookup of the original is
    replaced by one that serves the same table the model is given."""
    label, path, offset, size = extra
    o, t, rng = original(elf), tables(elf), random.Random(seed)
    emu, mem = o.emu, o.mem
    real = None
    if path is not None:
        if (path, offset) not in _TEXT_FILES:
            with open(path, 'rb') as source:
                source.seek(offset)
                _TEXT_FILES[(path, offset)] = read_text_file(source.read(size) if size else source.read())
        real = _TEXT_FILES[(path, offset)]
    state = {}

    def text_lookup(e):
        key = _cstr(mem, e.r[4]).replace(b'"', b'').decode('latin-1')
        where = o.wide[o.wide_next]
        o.wide_next = (o.wide_next + 1) % len(o.wide)
        mem.write(where, state['lookup'](key).encode('utf-16-le') + b'\0\0')
        return where

    emu.stub(F_TEXT_LOOKUP, function=text_lookup)
    bad, done, skipped = [], 0, 0
    for index in range(count):
        language = rng.choice([0, 0, 1, 2, 3, 4, 5, -1])
        if real is not None:
            state['lookup'] = lambda key: real.get(key, 'NF:' + key[:16])
        else:
            state['lookup'] = synthetic_text(seed * 1000003 + index, language)
        item = random_item(t, rng)
        if rng.random() < 0.6:
            item.flags &= ~0x200
        decorated = rng.random() < 0.85
        try:
            want = R.build_name(t, item, decorated, state['lookup'], language)
        except ValueError:
            skipped += 1
            continue
        mem.w8(G_LANGUAGE, language & 0xFF)
        mem.write(o.rec, item.pack(stale_bytes(rng)))
        mem.write(G_NAME_BUFFER, b'\xEE\xEE' * 100)
        where = o.call(F_NAME, o.rec, int(decorated)) & 0xFFFFFFFF
        got = bytearray()
        while mem.u16(where + len(got)):
            got += mem.read(where + len(got), 2)
        got = got.decode('utf-16-le', 'replace')
        done += 1
        if got != want or where != G_NAME_BUFFER:
            bad.append('name (%s, language %d, decorated %d) of %s: original %r, model %r'
                       % (label, language, decorated, item.pack().hex(), got, want))
    return done, bad, {'skipped': skipped}


def w_fpu_sensitivity(elf, seed, count, extra):
    """Not a comparison with the model: the original's item value under the other FPU
    models of the interpreter, counted against the default model.  Half the sample is
    table rows as parsed (values a game produces), half random records (many of them
    with values far above 2**24, where one unit in the last place is more than 1 gold)."""
    model, bias = extra
    base, other = original(elf), original(elf, False, model, bias)
    t, rng = tables(elf), random.Random(seed)
    counters = {'rows': 0, 'rows_moved': 0, 'records': 0, 'records_moved': 0, 'max_rows': 0}
    for index in range(count):
        if index % 2:
            d = rng.choice(t.defs + t.presets)
            item = R.parse_descriptor(t, d.name, -1, d.preset, R.Rng(rng.getrandbits(32)))
            kind = 'rows'
        else:
            item = random_item(t, rng)
            kind = 'records'
        raw = item.pack()
        base.mem.write(base.rec, raw)
        other.mem.write(other.rec, raw)
        counters[kind] += 1
        first, second = ee_emu.s32(base.call(F_VALUE, base.rec)), ee_emu.s32(other.call(F_VALUE, other.rec))
        counters[kind + '_moved'] += first != second
        if kind == 'rows':
            counters['max_rows'] = max(counters['max_rows'], abs(first - second))
    return count, [], counters


# ---------------------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------------------
def run_chunk(job):
    function, elf, seed, count, extra = job
    started = time.time()
    try:
        cases, bad, counters = globals()[function](elf, seed, count, extra)
    except EmuError as exc:
        return 0, ['the interpreter stopped: %s' % exc], {}, time.time() - started
    return cases, bad, counters, time.time() - started


def chunks(total, size):
    out = []
    while total > 0:
        out.append(min(size, total))
        total -= size
    return out


def find_elf(argv):
    for arg in argv:
        if os.path.isfile(arg):
            return arg
    for candidate in (os.environ.get('CHAMPIONS_ELF'), os.path.join(ROOT, 'SLUS_209.73'),
                      os.path.join(os.getcwd(), 'SLUS_209.73')):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def text_sources(options):
    """[(label, path, offset, size)] of the text files named on the command line."""
    sources = []
    if options.get('text'):
        sources.append((os.path.basename(options['text']), options['text'], 0, 0))
    if options.get('iso'):
        import dump_tables
        import mmap
        with open(options['iso'], 'rb') as image:
            mapped = mmap.mmap(image.fileno(), 0, access=mmap.ACCESS_READ)
            for path, offset, size in dump_tables.iso_files(mapped):
                name = path.rsplit('/', 1)[-1].upper()
                if name.startswith('GTEXT') and name.endswith('.LMP'):
                    sources.append((name, options['iso'], offset, size))
            mapped.close()
    return sorted(sources)


def plan(elf, scale, base_seed, options):
    """[(id, title, [jobs], sentence)] - a job is (worker, elf, seed, count, extra)."""
    t = R.Tables(elf)
    n_defs, n_presets = len(t.defs), len(t.presets)

    def size(default, least=1):
        return max(least, int(default * scale))

    def jobs(worker, total, per_chunk, extra=None, salt=0):
        return [(worker, elf, base_seed * 7919 + salt * 104729 + index, count, extra)
                for index, count in enumerate(chunks(total, per_chunk))]

    def slices(worker, total, per_chunk, salt):
        return [(worker, elf, base_seed * 7919 + salt * 104729 + start, 0, (start, min(start + per_chunk, total)))
                for start in range(0, total, per_chunk)]

    props = [
        ('powf', 'the C library powf 0x3a7930 through its wrapper 0x3a5ac8',
         jobs('w_powf', size(40000), 5000, salt=1),
         '{n} (x, y) pairs, four fifths with the exponents the item code uses: result bit for bit '
         '({skipped} with y = 0.5 not run: that path is the square-root routine, not modelled)'),
        ('fdouble', 'float * double constant, as loot_generateDrops does at 0x100dec-0x100e3c',
         jobs('w_float_double', size(20000), 5000, salt=2),
         '{n} values through the software double routines 0x3aef58, 0x3af4d0, 0x3afb90: result bit for bit'),
        ('sscanf', 'the C library sscanf 0x3b7f88 against the model\'s scanner',
         jobs('w_sscanf', size(140, 10), 20, salt=3),
         '{n} (token, format) pairs over all 43 formats: return value and the three integers'),
        ('parse-tables', 'item_parseDescriptor 0x1069b8 on every table name',
         slices('w_parse_tables', n_defs + 2 * n_presets, 150, 4),
         '%d base names, %d presets as presets and the same %d as plain descriptors, variant -1: all '
         '0x48 bytes of the record (unwritten bytes taken from a random stack) and the seed '
         '({draws} draws)' % (n_defs, n_presets, n_presets)),
        ('parse-random', 'item_parseDescriptor on random descriptors',
         jobs('w_parse_random', size(4000), 200, salt=5),
         '{n} random descriptors (0-6 tokens: every token word, truncated words, bare words, signs, '
         'spaces, huge numbers, garbage, empty tokens, unknown names, fixed and random variants, both '
         'tables): all 0x48 bytes and the seed ({draws} draws)'),
        ('value-random', 'item_getValue 0x1024a8 on random records',
         jobs('w_stats_random', size(40000), 2500, ('value',), salt=6),
         '{n} records with arbitrary modifiers on random definitions: the value'),
        ('stats-random', 'weight 0x103e08, armour 0x103ec8, attack rating 0x103f88, damage range 0x104100, model row 0x1083f8',
         jobs('w_stats_random', size(20000), 2500, ('stats',), salt=7),
         '{n} random records: weight bit for bit, armour, attack rating, damage range with and '
         'without elemental modifiers, model row'),
        ('stats-tables', 'value and statistics of every table row as parsed',
         slices('w_stats_tables', n_defs + n_presets, 200, 8),
         '{n} items (every base definition and every preset): value, weight, armour, attack rating, '
         'damage range, model row'),
        ('small', 'drop groups 0x104c04 / 0x104c48 and the record helpers 0x108924, 0x107ca8, 0x107ea4, 0x107ec0',
         jobs('w_small', size(3000), 3000, salt=9),
         '{n} checks: both group functions on every row of both tables; identity compare, field copy '
         'and index encode/decode on random records'),
        ('preset-full', 'item_generateFromSpecialTable 0x104758, library code original',
         jobs('w_preset', size(120), 12, False, salt=10),
         '{n} calls over random seeds, budgets, categories, level caps and player sets ({made} made '
         'an item): return value, every defined byte of the record, the seed'),
        ('preset-fast', 'item_generateFromSpecialTable, library string routines replaced',
         jobs('w_preset', size(1500), 100, True, salt=11),
         '{n} calls ({made} made an item): return value, every defined byte, the seed'),
        ('affix-full', 'item_generateWithAffixes 0x104ca4, library code original',
         jobs('w_affix', size(36), 2, False, salt=12),
         '{n} calls over random seeds, budgets, categories, suffix requests, level caps 1-120 and '
         'player sets ({made} made an item, {draws} draws): return value, every defined byte, the seed'),
        ('affix-fast', 'item_generateWithAffixes, library string routines replaced',
         jobs('w_affix', size(400), 20, True, salt=13),
         '{n} calls ({made} made an item, {draws} draws): return value, every defined byte, the seed'),
        ('plain', 'reagent 0x106214, figurine 0x106658 and consumable 0x108590 generators',
         jobs('w_plain_generators', size(6000), 300, salt=14),
         '{n} calls (a quarter each: reagent, reagent by picture name, figurine, consumable; {made} '
         'made an item): return value, every defined byte, the seed'),
        ('shop', 'item_appendGeneratedUnique 0x107d54, library string routines replaced',
         jobs('w_shop', size(60), 6, salt=15),
         '{n} stock lists of 1-4 appends ({appended} appended): the list entries and the seed '
         '({skipped} lists not run because a first try made nothing: see the specification)'),
        ('loot-full', 'loot_generateDrops 0x100d54, library code original',
         jobs('w_loot', size(40), 4, (0.25, False), salt=19),
         '{n} calls, set up as in the next line ({gold} gold, {consumable} consumable, {reagent} '
         'reagent, {figurine} figurine, {equipment} equipment drops; {early} early returns): drops in '
         'order, records, throw angle, position, seed ({draws} draws)'),
        ('loot', 'loot_generateDrops, library string routines replaced',
         jobs('w_loot', size(1500), 75, (0.25, True), salt=16),
         '{n} calls over random seeds, levels, difficulties, player sets, PvP flags and arguments, with '
         'loot_spawnGold, pool_new, PhProp_ctor, PhProp_initPhysics and the two trig calls replaced '
         '(constructors drawing 0 or 1 value, a tenth with a refused allocation): the drops in order '
         '({gold} gold, {consumable} consumable, {reagent} reagent, {figurine} figurine, {equipment} '
         'equipment; {early} calls ended early at a reagent or figurine roll with nothing to drop, '
         '{refused} had an allocation refused), each record\'s defined bytes, the throw angle, the '
         'position, the seed ({draws} draws)'),
        ('named', 'loot_spawnNamedItem 0x100ba0',
         jobs('w_named', size(600), 100, salt=21),
         '{n} descriptors (half table names, half random) with world_findFreeSpot, pool_new and '
         'PhProp_ctor replaced: the record handed to the constructor (defined bytes) and the seed'),
        ('load', 'the seed side of item_loadResources 0x108434',
         jobs('w_load_resources', size(8, 2), 2, True, salt=22) + jobs('w_load_resources', 1, 1, False, salt=23),
         '{n} start seeds with res_find replaced (one of them with the library\'s own string '
         'code): the seed after the function ({draws} draws in all)'),
        ('equip', 'inventory_checkEquipAllowed 0x1c4948 (the requirement test, outside the module)',
         jobs('w_equip', size(40000), 5000, salt=24),
         '{n} random player records (class, level, four statistics, skill ranks) against random '
         'items: the returned reason (reasons 0 to 9 came up {r0}, {r1}, {r2}, {r3}, {r4}, {r5}, {r6}, '
         '{r7}, {r8}, {r9} times)'),
        ('gold', 'the scatter loop of loot_spawnGold 0x100974',
         jobs('w_gold', size(4000), 1000, salt=17),
         '{n} calls with scripted terrain heights: the queried points, the final position and amount '
         'handed to the Gold constructor, the seed'),
        ('names', 'itemName_buildLocalizedName 0x101e48 with an invented string table',
         jobs('w_names', size(8000), 1000, ('invented text', None, 0, 0), salt=18),
         '{n} names over languages -1 to 5, decorated and plain, random prefix and suffix: the wide '
         'string ({skipped} cases outside what the model covers were not run)'),
    ]
    for index, source in enumerate(text_sources(options)):
        props.append(('names-' + source[0].lower(), 'itemName_buildLocalizedName with the text of %s' % source[0],
                      jobs('w_names', size(4000), 1000, source, salt=30 + index),
                      '{n} names with that file\'s text served to both sides, languages -1 to 5: the wide '
                      'string ({skipped} not run)'))
    moved = ('{rows_moved} of {rows} table rows as parsed (largest difference {max_rows} gold) and '
             '{records_moved} of {records} random records get a different value than under the default model')
    info = [
        ('fpu-ps2g1', 'INFO', jobs('w_fpu_sensitivity', size(4000), 1000, ('ps2g1', False), salt=20),
         'item_getValue under the interpreter\'s "ps2g1" adder: ' + moved),
        ('fpu-chop', 'INFO', jobs('w_fpu_sensitivity', size(4000), 1000, ('chop', False), salt=20),
         'item_getValue under plain truncation ("chop"): ' + moved),
        ('fpu-mulbias', 'INFO', jobs('w_fpu_sensitivity', size(4000), 1000, ('ps2', True), salt=20),
         'item_getValue with every inexact product one unit lower (worst case for the multiplier): ' + moved),
    ]
    return props, info


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    options, positional, index = {}, [], 0
    while index < len(argv):
        arg = argv[index]
        if arg in ('--jobs', '--seed', '-k', '--text', '--iso') and index + 1 < len(argv):
            options[arg.lstrip('-')] = argv[index + 1]
            index += 2
            continue
        if arg in ('--quick', '--full', '-v'):
            options[arg.lstrip('-')] = True
        elif arg in ('-h', '--help'):
            print(__doc__)
            return 0
        else:
            positional.append(arg)
        index += 1
    elf = find_elf(positional)
    if elf is None:
        print('SKIP  no SLUS_209.73 found (pass its path, or set CHAMPIONS_ELF); nothing was run')
        return 0
    with open(elf, 'rb') as source:
        digest = hashlib.sha256(source.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('SKIP  %s is not the US v2.00 executable these addresses belong to (SHA-256 %s); '
              'nothing was run' % (elf, digest))
        return 0
    for key in ('text', 'iso'):
        if options.get(key) and not os.path.isfile(options[key]):
            print('SKIP  --%s %s: no such file; the properties that need it are left out' % (key, options[key]))
            options.pop(key)
    scale = 0.1 if options.get('quick') else 5.0 if options.get('full') else 1.0
    base_seed = int(options.get('seed', 20973), 0) if isinstance(options.get('seed'), str) else 20973
    workers = int(options.get('jobs', min(os.cpu_count() or 1, 12)))
    only = options.get('k', '').lower()
    props, info = plan(elf, scale, base_seed, options)
    print('executable: %s  (SHA-256 matches US v2.00)' % elf)
    print('sample scale %g, base seed %d, %d worker process(es); floats compared bit for bit under '
          'ee_emu\'s default FPU model' % (scale, base_seed, workers))
    selected = [p for p in props + info if not only or only in p[0] or only in p[1].lower()]
    all_jobs = [(pid, job) for pid, _title, job_list, _sentence in selected for job in job_list]
    started = time.time()
    results = {}
    if workers > 1 and len(all_jobs) > 1:
        import multiprocessing
        with multiprocessing.get_context('spawn').Pool(workers) as pool:
            # longest jobs first keeps the workers evenly loaded
            order = sorted(range(len(all_jobs)), key=lambda i: -_weight(all_jobs[i][1]))
            for position, outcome in zip(order, pool.imap(run_chunk, [all_jobs[i][1] for i in order], 1)):
                results.setdefault(all_jobs[position][0], []).append(outcome)
    else:
        for pid, job in all_jobs:
            results.setdefault(pid, []).append(run_chunk(job))
    failed = 0
    for pid, title, _job_list, sentence in selected:
        cases = sum(r[0] for r in results[pid])
        bad = [message for r in results[pid] for message in r[1]]
        counters = {}
        for r in results[pid]:
            for key, value in r[2].items():
                counters[key] = max(counters.get(key, 0), value) if key.startswith('max_') \
                    else counters.get(key, 0) + value
        counters.setdefault('skipped', 0)
        seconds = sum(r[3] for r in results[pid])
        text = sentence.format(n=cases, **counters)
        if title == 'INFO':
            print('INFO  %-13s %s' % (pid, text))
            continue
        status = 'FAIL' if bad or cases == 0 else 'PASS'
        failed += status == 'FAIL'
        print('%s  %-13s %s. %s; %d mismatch(es)  [%.0f s of processor time]'
              % (status, pid, title, text, len(bad), seconds))
        for message in (bad if options.get('v') else bad[:3]):
            print('        ' + message)
        if len(bad) > 3 and not options.get('v'):
            print('        ... and %d more (use -v)' % (len(bad) - 3))
    checked = sum(1 for p in selected if p[1] != 'INFO')
    print('%d properties: %d PASS, %d FAIL  (%.0f s)' % (checked, checked - failed, failed, time.time() - started))
    return 1 if failed else 0


_COST = {'w_affix': 6.5, 'w_preset': 0.4, 'w_loot': 0.45, 'w_shop': 1.6, 'w_parse_random': 0.04,
         'w_parse_tables': 0.025, 'w_names': 0.004, 'w_stats_tables': 0.002}      # rough seconds per case


def _weight(job):
    worker, _elf, _seed, count, extra = job
    cost = _COST.get(worker, 0.0005)
    if worker == 'w_affix' and extra:
        cost /= 4.0
    if worker == 'w_preset' and extra:
        cost /= 2.5
    if worker == 'w_loot' and not extra[1]:
        cost *= 6.0
    if isinstance(extra, tuple) and len(extra) == 2 and isinstance(extra[0], int):
        count = extra[1] - extra[0]
    return cost * count


if __name__ == '__main__':
    sys.exit(main())
