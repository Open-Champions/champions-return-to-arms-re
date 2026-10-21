#!/usr/bin/env python3
"""difftest_strings.py - compare tools/ref_strings.py with the game's own machine code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_strings.py [path/to/SLUS_209.73] [--quick] [--seed N] [-k TEXT] [-v]

    --quick   a tenth of the random samples
    --seed N  seed of the random inputs (default 20973); one seed repeats exactly
    -k TEXT   run only the properties whose name contains TEXT
    -v        print up to three failing cases per property

Each property runs the ORIGINAL functions in tools/ee_emu.py (an instruction interpreter,
not a console) on synthetic inputs this script builds, runs the same inputs through the
model and compares every word the model claims to describe.  All string tables, keys and
texts here are generated: no game text is read.  docs/strings.md lists the properties.
"""
import hashlib
import os
import random
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError, M32            # noqa: E402
import ref_core as RC                           # noqa: E402
import ref_strings as R                         # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False}
RESULTS = []

TEXT_HASH, TEXT_REGISTER, TEXT_UNREGISTER = 0x173A74, 0x173BAC, 0x173AC0
TEXT_LOOKUP, TEXT_FIND = 0x173C84, 0x173DE0
WSTR_COPY, WSTR_FROM_ASCII, WSTR_TO_ASCII, WSTR_LEN = 0x19E854, 0x19E884, 0x19E8B4, 0x19E994
WSTR_FORMAT_ASCII, WSTR_FORMAT = 0x19E9C4, 0x19EA78
SCR_SET_INFO, SCR_ADD_HELP, SCR_ADD_HELP_F = 0x14318C, 0x1431D8, 0x143270
SCR_SHOW_BUST, SCR_SHOW_COMPASS = 0x142864, 0x1427B4
HUD_SHOW_MESSAGE, HUD_SHOW_HELP, HUD_SET_BUST, HUD_SET_COMPASS = 0x1D92A0, 0x1D9830, 0x1DFAA0, 0x1DF668
HUD_TICK_MESSAGE = 0x1D934C
HUD_RUN_COUNTDOWN = (0x1DBBEC, 0x1DBC24)
NET_IS_LOCAL, RES_FIND, SOUND_PLAY_ON_OBJECT = 0x13E150, 0x17365C, 0x214230
SOUND_SET_FROZEN, UI_START_PULSE, HUDMSG_MENU_STATE = 0x216AD0, 0x320EA4, 0x1DE0DC
WORLD_FIND_OBJECT = 0x14F498
GAME_IS_FROZEN, ANIM_PUSH = 0x1EBDF8, 0x170838
H_INIT, H_LINK, H_CLEAR = 0x1A17D0, 0x1A1738, 0x1A1698
H_FREE_HEAD = 0x864EA8
SET_CHARM = 0x1189F0
COSMETIC_SEED, SHARED_SEED = 0x404460, 0x404464


def wanted(name):
    return OPTIONS['filter'] is None or OPTIONS['filter'].lower() in name.lower()


def scaled(count):
    return max(count // 10, 10) if OPTIONS['quick'] else count


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-28s %7d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:3]:
            print('        ' + line)
    sys.stdout.flush()


class Check:
    def __init__(self):
        self.failures = 0
        self.examples = []
        self.cases = 0

    def eq(self, what, got, want):
        if got != want:
            self.failures += 1
            if len(self.examples) < 3:
                self.examples.append('case %d: %s: got %r, model %r' % (self.cases, what, got, want))
            return False
        return True


def rng_for(tag):
    return random.Random('%s/%s' % (OPTIONS['seed'], tag))


# ---------------------------------------------------------------------------------------
# Interpreter helpers
# ---------------------------------------------------------------------------------------
SYS_GET_THREAD_ID, SYS_END_OF_HEAP, SYS_SIGNAL_SEMA, SYS_WAIT_SEMA = 0x2F, 0x3E, 0x42, 0x44
LIBC_BREAK = 0x5074FC           # newlib's current break, read by the sbrk at 0x3530e0


class Rig:
    """One interpreter.  sprintf's %f path reaches newlib malloc (Balloc in _dtoa_r),
    which asks the kernel for a thread id, a semaphore and the end of the heap; those
    four system calls are answered here and the heap is a block the test owns."""

    def __init__(self, elf):
        self.emu = EE(elf)
        self.emu.record_writes = False
        self.sp = self.emu.r[29]
        self.elf = elf
        heap = self.emu.alloc(0x100000)
        self.emu.mem.w32(LIBC_BREAK, heap)
        self.heap_end = heap + 0x100000
        self.emu.syscall_handler = self._syscall
        self.scratch = self.emu.alloc(0x80000)
        self.scratch_end = self.scratch + 0x80000
        self.reset()

    def reset(self):
        """Forget everything put() placed (the memory is reused by the next case)."""
        self.top = self.scratch

    def take(self, size, align=16, fill=0):
        addr = (self.top + align - 1) & -align
        if addr + size > self.scratch_end:
            raise EmuError('test scratch exhausted')
        self.top = addr + size
        self.emu.mem.write(addr, bytes([fill]) * size)
        return addr

    def _syscall(self, emu):
        number = emu.r[3] & 0xFF
        if number == SYS_GET_THREAD_ID:
            emu.r[2] = 1
        elif number == SYS_END_OF_HEAP:
            emu.r[2] = self.heap_end
        elif number in (SYS_SIGNAL_SEMA, SYS_WAIT_SEMA):
            emu.r[2] = 0
        else:
            raise EmuError('system call 0x%x is not answered by this test' % number)

    def call(self, addr, *args, fargs=(), steps=3000000):
        self.emu.r[29] = self.sp
        return self.emu.call(addr, *args, fargs=fargs, max_steps=steps) & M32

    def put(self, data, align=16):
        addr = self.take(len(data) + 8, align=align)
        self.emu.mem.write(addr, bytes(data))
        return addr

    def put_units(self, units):
        return self.put(struct.pack('<%dH' % len(units), *[u & 0xFFFF for u in units]))

    def units(self, addr, count):
        return list(struct.unpack('<%dH' % count, self.emu.mem.read(addr, 2 * count)))

    def cstr(self, addr):
        return self.emu.mem.cstr(addr)

    def wstr(self, addr, limit=4096):
        out = []
        while len(out) < limit:
            u = self.emu.mem.u16(addr + 2 * len(out))
            if u == 0:
                break
            out.append(u)
        return out

    def slots(self):
        return list(struct.unpack('<8192I', self.emu.mem.read(R.G_TEXT_HASH, 4 * R.TEXT_SLOTS)))


def random_key(rng, lo=1, hi=24, high_bytes=0.1, quotes=0.0):
    n = rng.randint(lo, hi)
    out = bytearray()
    for _ in range(n):
        roll = rng.random()
        if roll < high_bytes:
            out.append(rng.randint(0x80, 0xFF))
        elif roll < high_bytes + quotes:
            out.append(0x22)
        else:
            out.append(rng.choice(b'abcdefghijklmnopqrstuvwxyz_0123456789ABCDEFXYZ'))
    return bytes(out)


def random_text(rng, lo=0, hi=40, alphabet=None):
    n = rng.randint(lo, hi)
    if alphabet:
        return ''.join(rng.choice(alphabet) for _ in range(n))
    chars = []
    for _ in range(n):
        roll = rng.random()
        if roll < 0.75:
            chars.append(chr(rng.randint(0x20, 0x7E)))
        elif roll < 0.95:
            chars.append(chr(rng.randint(0xA0, 0x17F)))
        else:
            chars.append(chr(rng.randint(0x3000, 0x30FF)))
    return ''.join(chars).replace('\0', ' ')


def colliding_keys(rng, count, want_hash=None):
    """Keys that share one 13-bit hash (brute force over short random keys)."""
    target = want_hash if want_hash is not None else rng.randrange(0x2000)
    found = []
    while len(found) < count:
        key = random_key(rng, 3, 8, high_bytes=0.0)
        if R.text_hash(key) == target and key not in found:
            found.append(key)
    return found


# ---------------------------------------------------------------------------------------
# 1. Hash, registration, lookup
# ---------------------------------------------------------------------------------------
def test_hash(elf):
    label = 'text.hash'
    if not wanted(label):
        return
    rig, rng, chk = Rig(elf), rng_for('hash'), Check()
    buf = rig.take(0x200)
    for _ in range(scaled(20000)):
        chk.cases += 1
        key = random_key(rng, 0, 60, high_bytes=0.3)
        rig.emu.mem.write(buf, key + b'\0')
        chk.eq('hash of %r' % key, rig.call(TEXT_HASH, buf, len(key)), R.text_hash(key))
    report(label, chk.failures, chk.cases, 'text_hash 0x173a74 on keys of 0..60 bytes, '
           'a third of the bytes >= 0x80 (signed lb)', chk.examples)


def make_table(rng, entries, collide=0, dup=0, quoted=0, pad=0):
    """Synthetic (key, text) pairs: random keys, some sharing one hash, some repeated,
    some with a double quote inside (never found by a lookup)."""
    pairs, keys = [], set()
    groups = colliding_keys(rng, collide) if collide else []
    for key in groups:
        pairs.append((key, random_text(rng)))
        keys.add(key)
    while len(pairs) < entries:
        key = random_key(rng, 1, 30, high_bytes=0.05)
        if key in keys:
            continue
        keys.add(key)
        pairs.append((key, random_text(rng)))
    for _ in range(dup):
        key = rng.choice(list(keys))
        pairs.insert(rng.randrange(len(pairs) + 1), (key, random_text(rng)))
    for _ in range(quoted):
        key = random_key(rng, 2, 12, high_bytes=0.0)
        key = key[:1] + b'"' + key[1:]
        pairs.append((key, random_text(rng)))
    rng.shuffle(pairs)
    return pairs, R.build_uni(pairs, pad=pad)


def test_tables(elf):
    label = 'text.register+lookup'
    if not wanted(label):
        return
    chk = Check()
    lookups = finds = misses = shadowed = 0
    rng = rng_for('tables')
    for round_ in range(scaled(12)):
        rig = Rig(elf)
        model = R.TextTable()
        tables = []
        for t in range(rng.randint(1, 3)):
            pairs, data = make_table(rng, rng.randint(20, 400), collide=rng.randint(0, 12),
                                     dup=rng.randint(0, 6), quoted=rng.randint(0, 3),
                                     pad=rng.choice((0, 0, 0x41)))
            base = rig.put(data, align=rng.choice((2, 4, 16)))
            if base & 1:
                raise AssertionError('tables are 2-aligned')
            rig.call(TEXT_REGISTER, base, steps=20000000)
            model.register(data, base)
            tables.append((pairs, data, base))
            chk.cases += 1
            chk.eq('slots after registering table %d' % t, rig.slots(), model.slots)
        # unregister one table (only when several), which can shadow keys of the others
        if len(tables) > 1 and rng.random() < 0.7:
            pairs, data, base = tables.pop(rng.randrange(len(tables)))
            rig.call(TEXT_UNREGISTER, base, steps=20000000)
            model.unregister(data, base)
            chk.cases += 1
            chk.eq('slots after unregistering', rig.slots(), model.slots)
        known = [k for pairs, _d, _b in tables for k, _t in pairs]
        for _ in range(scaled(600)):
            chk.cases += 1
            roll = rng.random()
            if roll < 0.55 and known:
                key = rng.choice(known)
            elif roll < 0.70 and known:
                key = rng.choice(known)
                at = rng.randrange(len(key) + 1)
                key = key[:at] + b'"' * rng.randint(1, 3) + key[at:]
            else:
                key = random_key(rng, 1, 40, high_bytes=0.2, quotes=0.05)
            req = rig.put(key + b'\0')
            # text_find
            got = rig.call(TEXT_FIND, req)
            want = model.find(key)
            chk.eq('text_find %r' % key, got, want)
            finds += 1
            # text_lookup, with a known pattern on the stack below the caller
            frame = rig.sp - 0x220
            stale = bytes(rng.getrandbits(8) for _ in range(0x40))
            rig.emu.mem.write(frame, stale)
            got = rig.call(TEXT_LOOKUP, req)
            key_s = R.strip_quotes(key)
            want_addr, want_units, hit = model.lookup(key, stale=stale[len(key_s) + 1:])
            lookups += 1
            chk.eq('text_lookup address %r' % key, got, want_addr)
            if hit:
                chk.eq('text %r' % key, rig.wstr(got), want_units)
            else:
                misses += 1
                chk.eq('ring index', rig.emu.mem.u8(R.G_NF_INDEX), model.nf_index)
                chk.eq('ring entry', rig.units(got, R.NF_UNITS), model.nf_ring[model.nf_index])
                chk.eq('miss text', rig.wstr(got), R.nf_text(key))
                if key_s in [k for pairs, _d, _b in tables for k, _t in pairs]:
                    shadowed += 1
    report(label, chk.failures, chk.cases,
           'text_registerTable / text_unregisterTable: all 8,192 slots after every call; '
           '%d text_find and %d text_lookup (%d misses: ring index, all 40 bytes of the ring '
           'entry including stale stack bytes; %d of them keys present but shadowed by an '
           'unregistration) on synthetic tables with collisions, duplicates and quoted keys'
           % (finds, lookups, misses, shadowed), chk.examples)


# ---------------------------------------------------------------------------------------
# 2. Wide strings and the formatter
# ---------------------------------------------------------------------------------------
# exponent 255 (an infinity or NaN once widened), denormals, zeros, the largest values
FLOAT_EDGE = (0x7F800000, 0xFF800000, 0x7FC00000, 0x7F800001, 0xFFFFFFFF, 0x7FFFFFFF,
              0x00000001, 0x80000001, 0x007FFFFF, 0x00000000, 0x80000000, 0x7F7FFFFF,
              0x4B000000, 0xCF000000, 0x3C23D70A, 0x3BA3D70A)


def float_arg(rng, kind):
    if kind == 'int':
        v = rng.choice((rng.randint(-1000, 1000), rng.randint(-(1 << 24), 1 << 24),
                        rng.randint(-(1 << 31), (1 << 31) - 1)))
        return R.cvt_s_w(v)
    if kind == 'float':
        roll = rng.random()
        if roll < 0.4:
            return RC.f32(rng.uniform(-1000, 1000))
        if roll < 0.6:
            return RC.f32(rng.choice((0.125, 0.375, -0.125, 2.675, 1.005, 0.005, -0.0, 0.0, 1e-3, -1e-3)))
        if roll < 0.75:
            return RC.f32(rng.uniform(-1e9, 1e9))
        if roll < 0.85:
            return rng.choice(FLOAT_EDGE)
        return rng.getrandbits(32) & 0x7F7FFFFF | (rng.getrandbits(1) << 31)
    return rng.getrandbits(32)


def test_wstr(elf):
    label = 'wstr.helpers'
    if not wanted(label):
        return
    rig, rng, chk = Rig(elf), rng_for('wstr'), Check()
    for _ in range(scaled(3000)):
        rig.reset()
        chk.cases += 1
        units = [rng.randint(1, 0xFFFF) for _ in range(rng.randint(0, 60))]
        src = rig.put_units(units + [0])
        dst = rig.take(2 * len(units) + 16, fill=0xEE)
        rig.call(WSTR_COPY, dst, src)
        chk.eq('wstr_copy', rig.units(dst, len(units) + 2), R.wstr_copy(units) + [0xEEEE])
        chk.eq('wstr_len', rig.call(WSTR_LEN, src), len(units))
        raw = bytes(rng.randint(1, 255) for _ in range(rng.randint(0, 60)))
        src8 = rig.put(raw + b'\0')
        dst = rig.take(2 * len(raw) + 16, fill=0xEE)
        rig.call(WSTR_FROM_ASCII, dst, src8)
        chk.eq('wstr_fromAscii', rig.units(dst, len(raw) + 2), R.wstr_from_ascii(raw) + [0xEEEE])
        dst = rig.take(len(units) + 16, fill=0xEE)
        rig.call(WSTR_TO_ASCII, dst, src)
        chk.eq('wstr_toAscii', rig.emu.mem.read(dst, len(units) + 2), R.wstr_to_ascii(units) + b'\xee')
    report(label, chk.failures, chk.cases, 'wstr_copy, wstr_len, wstr_fromAscii (zero-extends), '
           'wstr_toAscii (low byte): output and the first unit after it', chk.examples)


CONVERSIONS = ('%', 'd', 'c', 's', 'u', 'f', 'x', '.', 'l', 'i')


def random_format(rng, tail_ok=True):
    """A random format and the arguments its conversions take."""
    parts, args, kinds = [], [], []
    for _ in range(rng.randint(0, 10)):
        roll = rng.random()
        if roll < 0.5:
            parts += [ord(c) for c in random_text(rng, 1, 6).replace('%', '#')]
        else:
            conv = rng.choice(CONVERSIONS)
            parts += [0x25, ord(conv)]
            if conv in 'dcsuf':
                kinds.append(conv)
    return parts, kinds


def test_format(elf):
    label = 'wstr.format'
    if not wanted(label):
        return
    rig, rng, chk = Rig(elf), rng_for('format'), Check()
    overruns = skipped = 0
    counts = {}
    for _ in range(scaled(4000)):
        rig.reset()
        units, kinds = random_format(rng)
        if len(kinds) > 8:
            skipped += 1
            continue
        ending = rng.random()
        if ending < 0.15:
            units = units + [0x25, ord(rng.choice('dcf%x'))]
            if chr(units[-1]) in 'dcf':
                kinds.append(chr(units[-1]))
        elif ending < 0.22:
            units = units + [0x25]
        if len(kinds) > 8:
            skipped += 1
            continue
        tail = [ord(c) for c in random_text(rng, 0, 6, alphabet='abcXYZ09 ')] + [0x41, 0, 0]
        if ending < 0.22:
            overruns += 1
        args, strings = [], {}
        for kind in kinds:
            counts[kind] = counts.get(kind, 0) + 1
            if kind == 's':
                text = random_text(rng, 0, 20, alphabet='abcdefgh XYZ\xe9\xff').encode('latin1')
                addr = rig.put(text + b'\0')
                strings[addr] = ('8', text)
                args.append(R.cvt_s_w(addr))
            elif kind == 'u':
                wide = [rng.randint(1, 0xFFFF) for _ in range(rng.randint(0, 12))]
                addr = rig.put_units(wide + [0])
                strings[addr] = ('16', wide)
                args.append(R.cvt_s_w(addr))
            elif kind in 'dc':
                args.append(float_arg(rng, 'int' if rng.random() < 0.8 else 'raw'))
            else:
                args.append(float_arg(rng, 'float'))
        args += [float_arg(rng, 'raw') for _ in range(8 - len(args))]
        fmt = rig.put_units(units + [0] + tail)
        out = rig.take(0x1000, fill=0xEE)
        chk.cases += 1
        try:
            want, used = R.wstr_format(units + [0] + tail, args,
                                       cstr=lambda a: strings[a][1] + b'\0',
                                       wstr=lambda a: strings[a][1] + [0])
        except R.FormatError as error:
            chk.eq('model refused', str(error), None)
            continue
        # load the exact float patterns (call()'s fargs would go through a Python float)
        rig.emu.r[29] = rig.sp
        for i, a in enumerate(args):
            rig.emu.f[12 + i] = a
        rig.emu.mem.write(out, b'\xee' * 0x1000)
        rig.emu.r[4], rig.emu.r[5] = out, fmt
        rig.emu.r[31] = rig.emu.RETURN_ADDR
        rig.emu.jump(WSTR_FORMAT)
        rig.emu.run(max_steps=3000000)
        chk.eq('format %r' % units, rig.units(out, len(want) + 1), want + [0xEEEE])
    report(label, chk.failures, chk.cases,
           'wstr_format on random formats (%s) with up to 8 float arguments; %d formats end in a '
           'conversion or a lone %% and read past their terminator; output units and the unit '
           'after them (%d formats with > 8 conversions not run)'
           % (', '.join('%s %d' % kv for kv in sorted(counts.items())), overruns, skipped), chk.examples)


def test_format_ascii(elf):
    label = 'wstr.formatAscii'
    if not wanted(label):
        return
    rig, rng, chk = Rig(elf), rng_for('format8'), Check()
    for _ in range(scaled(1500)):
        rig.reset()
        units, kinds = random_format(rng)
        units = [u & 0x7F or 0x20 for u in units]
        kinds = []
        i = 0
        while i < len(units):
            if units[i] == 0x25 and i + 1 < len(units):
                if chr(units[i + 1]) in 'dcf':
                    kinds.append(chr(units[i + 1]))
                elif chr(units[i + 1]) in 'su':
                    units[i + 1] = ord('d')
                    kinds.append('d')
                i += 2
            else:
                i += 1
        units.append(0x5A)          # end inside the text: the widened buffer's tail is stack data
        if len(kinds) > 8:
            continue
        fmt8 = bytes(units)
        args = [float_arg(rng, 'int' if k in 'dc' else 'float') for k in kinds]
        args += [0] * (8 - len(args))
        src = rig.put(fmt8 + b'\0')
        out = rig.take(0x800, fill=0xEE)
        chk.cases += 1
        want, _used = R.wstr_format_ascii(fmt8, args)
        rig.emu.r[29] = rig.sp
        for i, a in enumerate(args):
            rig.emu.f[12 + i] = a
        rig.emu.r[4], rig.emu.r[5] = out, src
        rig.emu.r[31] = rig.emu.RETURN_ADDR
        rig.emu.jump(WSTR_FORMAT_ASCII)
        rig.emu.run(max_steps=3000000)
        chk.eq('formatAscii %r' % fmt8, rig.units(out, len(want) + 1), want + [0xEEEE])
    report(label, chk.failures, chk.cases, 'wstr_formatAscii: 8-bit formats widened, then '
           'formatted (formats that end inside the text only)', chk.examples)


TESTS = [test_hash, test_tables, test_wstr, test_format, test_format_ascii]


def find_elf(argv):
    candidates = [a for a in argv if not a.startswith('-')]
    candidates += [os.path.join(ROOT, 'local', 'SLUS_209.73'), os.path.join(ROOT, 'SLUS_209.73'),
                   'SLUS_209.73']
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
    for test in TESTS:
        test(elf)
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d PASS, %d FAIL (seed %d%s, %.0f s)' % (
        len(RESULTS), len(RESULTS) - len(failed), len(failed), OPTIONS['seed'],
        ', quick' if OPTIONS['quick'] else '', time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
