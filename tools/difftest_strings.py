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

    def cstr(self, addr, limit=4096):
        out = bytearray()
        while len(out) < limit:
            b = self.emu.mem.u8(addr + len(out))
            if b == 0:
                break
            out.append(b)
        return bytes(out)

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


# ---------------------------------------------------------------------------------------
# 3. The five commands, the four setters and the run-side timers
# ---------------------------------------------------------------------------------------
G_CAMERA_BLOCK_MODE = 0x34
RES_CHIME = 0x00ABC000


def pack_cells(key, packed):
    """A script string as the handlers receive it (scr_getString 0x141650)."""
    if packed:
        raw = key + b'\0'
        raw += b'\0' * (-len(raw) % 4)
        return [struct.unpack('>I', raw[i:i + 4])[0] for i in range(0, len(raw), 4)]
    return list(key) + [0]


class HudRig(Rig):
    """The interpreter with a registered synthetic table, a fake script machine for the
    handlers' string arguments, stubbed outward calls and the model beside it."""

    def __init__(self, elf, rng):
        Rig.__init__(self, elf)
        self.rng = rng
        emu = self.emu
        emu.record_calls = True
        # table
        self.pairs = []
        for i in range(60):
            n = rng.choice((0, 3, 12, 20, 31, 32, 40, 63, 64, 90, 99, 100, 101))
            self.pairs.append((b'k%02d_' % i + random_key(rng, 1, 8, high_bytes=0.0),
                               random_text(rng, n, n).replace('%', '#')))
        conv = ('%d', '%c', '%%', '%f', '%x', '%.2f', '%')
        for i in range(24):
            text = random_text(rng, 0, 30).replace('%', '#')
            at = rng.randint(0, len(text))
            text = text[:at] + rng.choice(conv) + text[at:]
            if rng.random() < 0.3:
                text += rng.choice(conv[:4])
            self.pairs.append((b'f%02d_' % i + random_key(rng, 1, 6, high_bytes=0.0), text))
        data = R.build_uni(self.pairs)
        self.table_base = emu.alloc(len(data) + 16)
        emu.mem.write(self.table_base, data)
        self.model_table = R.TextTable()
        self.call(TEXT_REGISTER, self.table_base, steps=20000000)
        self.model_table.register(data, self.table_base)
        self.keys = [k for k, _t in self.pairs]
        self.format_keys = [k for k, _t in self.pairs if k.startswith(b'f')]
        # fake script machine: scr_getAddr 0x1414a8 runs for real on it
        self.vm, hdr = emu.alloc(0x40), emu.alloc(0x40)
        self.data = emu.alloc(0x4000)
        emu.mem.w32(self.vm, hdr)
        emu.mem.w32(hdr + 0x10, (self.data - hdr) & M32)
        emu.mem.w32(self.vm + 0x14, 0x4000)
        emu.mem.w32(self.vm + 0x18, 0x8000)
        emu.mem.w32(self.vm + 0x1C, 0x10000)
        self.params = emu.alloc(0x40)
        # camera and objects
        self.camera = emu.alloc(0x40)
        self.objects = {}
        for i in range(4):
            addr = emu.alloc(0x40)
            words = tuple(rng.getrandbits(32) for _ in range(3))
            for j, word in enumerate(words):
                emu.mem.w32(addr + 0x10 + 4 * j, word)
            self.objects[b'obj%d' % i] = (addr, words)
        # model
        self.hud = R.Hud()
        self.hud.block = bytearray(emu.mem.read(R.BUST_TEXT, len(self.hud.block)))
        self.hud.help_f = bytearray(emu.mem.read(R.HELP_F_TITLE, len(self.hud.help_f)))
        self.hud.bust_texture = self.cstr(R.G_BUST_TEXTURE)
        self.locals = {0}
        self.hud.local = lambda slot: slot in self.locals
        self.cmd = R.Commands(self.model_table, self.hud,
                              find_object=lambda n: self.objects[n][1] if n in self.objects else None)
        # stubs
        emu.stub(NET_IS_LOCAL, function=lambda e: 1 if R.s32(e.r[4]) in self.locals else 0, name='net_isLocalSlot')
        emu.stub(RES_FIND, ret=RES_CHIME, name='res_find')
        emu.stub(SOUND_PLAY_ON_OBJECT, ret=0x8005, name='sound_playOnObject')
        emu.stub(SOUND_SET_FROZEN, ret=0, name='sound_setPlaysWhileFrozen')
        emu.stub(UI_START_PULSE, ret=0, name='ui_startPulse')
        emu.stub(HUDMSG_MENU_STATE, ret=0, name='hudmsg_sendMenuState')
        emu.stub(WORLD_FIND_OBJECT, function=self._find, name='world_findObjectByName')

    def _find(self, emu):
        name = self.cstr(emu.r[4] & M32)
        return self.objects[name][0] if name in self.objects else 0

    # -- inputs
    def randomise_inputs(self):
        rng, hud, mem = self.rng, self.hud, self.emu.mem
        hud.suppressed = 1 if rng.random() < 0.12 else 0
        hud.local_menu = 1 if rng.random() < 0.12 else 0
        hud.menu_open = 1 if rng.random() < 0.08 else 0
        hud.loadscreen = 1 if rng.random() < 0.05 else 0
        hud.camera_mode = rng.choice((1, 1, 1, 1, 0, 2))
        hud.warmup = rng.choice((0, 0, 0, 0, 7))
        hud.num_players = rng.choice((1, 2, 3, 4, 4))
        hud.network = 1 if rng.random() < 0.3 else 0
        hud.alive = rng.sample(range(4), rng.randint(0, 4))
        self.locals = set(rng.sample(range(4), rng.randint(0, 2)))
        mem.w8(R.G_HUD_SUPPRESSED, hud.suppressed)
        mem.w8(R.G_LOCAL_MENU, hud.local_menu)
        mem.w32(R.G_MENU_OPEN, hud.menu_open)
        mem.w8(R.G_LOADSCREEN, hud.loadscreen)
        mem.w32(R.G_LOCAL_CAMERA, self.camera)
        mem.w32(self.camera + G_CAMERA_BLOCK_MODE, hud.camera_mode)
        mem.w32(R.G_WARMUP, hud.warmup)
        mem.w32(R.G_NUM_PLAYERS, hud.num_players)
        mem.w8(R.G_NETWORK, hud.network)
        mem.w32(R.G_ALIVE_COUNT, len(hud.alive))
        for i, slot in enumerate(hud.alive):
            mem.w32(R.G_ALIVE_LIST + 4 * i, slot)

    def string_arg(self, key, at):
        cells = pack_cells(key, self.rng.random() < 0.5)
        for i, cell in enumerate(cells):
            self.emu.mem.w32(self.data + at + 4 * i, cell)
        return at

    def handler(self, addr, values):
        """values: ('s', key) or ('i', int)."""
        at, cells = 0, []
        for kind, value in values:
            if kind == 's':
                cells.append(self.string_arg(value, at))
                at += 4 * (len(value) + 2)
            else:
                cells.append(value & M32)
        self.emu.mem.w32(self.params, 4 * len(cells))
        for i, cell in enumerate(cells):
            self.emu.mem.w32(self.params + 4 + 4 * i, cell)
        return self.call(addr, self.vm, self.params)

    # -- comparing
    def emu_events(self):
        out = []
        for c in self.emu.calls:
            name = getattr(c, 'name', None)
            if not getattr(c, 'stubbed', False) or name in (None, 'net_isLocalSlot', 'world_findObjectByName'):
                continue
            if name == 'res_find':
                out.append(('res_find', self.cstr(c.args[0] & M32).decode('latin1'),
                            self.cstr(c.args[1] & M32).decode('latin1')))
            elif name == 'sound_playOnObject':
                ok = (c.args[0] & M32) == RES_CHIME and RC.to_float(c.fargs[0]) == 1.0
                out.append(('sound_playOnObject', 'chime' if ok else hex(c.args[0]), c.args[1] & M32, 1.0))
            elif name == 'sound_setPlaysWhileFrozen':
                if (c.args[0] & M32) != 0x8005:
                    out.append(('sound_setPlaysWhileFrozen wrong handle',))
                out.append(('sound_setPlaysWhileFrozen',))
            elif name == 'ui_startPulse':
                out.append(('ui_startPulse', c.args[0] & M32))
            elif name == 'hudmsg_sendMenuState':
                out.append(('hudmsg_sendMenuState', R.s32(c.args[0]) & 0xFF, c.args[1] & M32, c.args[2] & M32))
        return out

    def compare(self, chk, what):
        mem, hud = self.emu.mem, self.hud
        chk.eq(what + ': HUD text block 0x86aab0-0x86ac44', bytes(mem.read(R.BUST_TEXT, len(hud.block))), bytes(hud.block))
        chk.eq(what + ': help-F buffers', bytes(mem.read(R.HELP_F_TITLE, len(hud.help_f))), bytes(hud.help_f))
        got = (mem.u16(R.G_MSG_FRAMES), mem.u8(R.G_MSG_FORCE), mem.u8(R.G_HELP_OPEN),
               mem.u32(R.G_HELP_TITLE), mem.u32(R.G_HELP_BODY), mem.u32(R.G_HELP_CLOSE_DELAY),
               mem.u8(R.G_BUST_SHOWN), mem.u8(R.G_COMPASS_SHOWN), mem.u8(R.G_BUST_HIDE_LATCH),
               self.cstr(R.G_BUST_TEXTURE),
               tuple(mem.u32(R.G_COMPASS_TARGET + 4 * i) for i in range(3)))
        want = (hud.msg_frames, hud.msg_force, hud.help_open, hud.help_title, hud.help_body,
                hud.help_close_delay & M32, hud.bust_shown, hud.compass_shown, hud.latch,
                hud.bust_texture, tuple(hud.compass_target))
        chk.eq(what + ': HUD words', got, want)
        chk.eq(what + ': outward calls', self.emu_events(), hud.events)
        chk.eq(what + ': miss ring index', mem.u8(R.G_NF_INDEX), self.model_table.nf_index)
        got = [self.wstr(R.G_NF_RING + 40 * i, 20) for i in range(16)]
        want = [R.visible(e) for e in self.model_table.nf_ring]
        chk.eq(what + ': miss ring texts', got, want)


def random_key_choice(rig, rng, pool=None):
    roll = rng.random()
    if roll < 0.8:
        return rng.choice(pool or rig.keys)
    return b'miss_' + random_key(rng, 1, 20, high_bytes=0.0)


def test_hud(elf):
    label = 'hud.commands'
    if not wanted(label):
        return
    chk = Check()
    counts = {}
    edges = {'message > 99 units': 0, 'bust text > 31': 0, 'compass label > 31': 0,
             'help-F title > 31': 0, 'help-F read past a terminator': 0, 'lookup misses': 0}
    faults = 0
    for round_ in range(scaled(6)):
        rng = rng_for('hud/%d' % round_)
        rig = HudRig(elf, rng)
        for _ in range(scaled(1000)):
            rig.reset()
            rig.randomise_inputs()
            rig.emu.calls = []
            rig.hud.events = []
            ring_before = rig.model_table.nf_index
            chk.cases += 1
            action = rng.choice(('setInfo', 'addHelpMessage', 'addHelpMessageF', 'showBust',
                                 'showCompass', 'hud_showMessage', 'hud_showHelpMessage',
                                 'hud_setBust', 'hud_setCompassTarget', 'tick', 'tick', 'tick'))
            counts[action] = counts.get(action, 0) + 1
            model_error = emu_error = None
            try:
                if action == 'setInfo':
                    key = random_key_choice(rig, rng)
                    try:
                        rig.cmd.set_info(key)
                    except R.FormatError as error:
                        model_error = error
                    rig.handler(SCR_SET_INFO, [('s', key)])
                elif action == 'addHelpMessage':
                    k1, k2 = random_key_choice(rig, rng), random_key_choice(rig, rng)
                    rig.cmd.add_help_message(k1, k2)
                    rig.handler(SCR_ADD_HELP, [('s', k1), ('s', k2)])
                elif action == 'addHelpMessageF':
                    k1 = random_key_choice(rig, rng, rig.format_keys)
                    k2 = random_key_choice(rig, rng, rig.format_keys)
                    v1 = rng.choice((rng.randint(-99, 999), rng.randint(-(1 << 31), (1 << 31) - 1), 0x263A))
                    v2 = rng.randint(-5000, 5000)
                    try:
                        rig.cmd.add_help_message_f(k1, v1, k2, v2)
                    except R.FormatError as error:
                        model_error = error
                    rig.handler(SCR_ADD_HELP_F, [('s', k1), ('i', v1), ('s', k2), ('i', v2)])
                elif action == 'showBust':
                    tex = b'bust_' + random_key(rng, 1, 20, high_bytes=0.0)
                    key = random_key_choice(rig, rng)
                    a, b = rng.randint(-50, 300), rng.choice((-1, -1, 0, rng.randint(1, 300)))
                    try:
                        rig.cmd.show_bust(tex, key, a, b)
                    except R.FormatError as error:
                        model_error = error
                    rig.handler(SCR_SHOW_BUST, [('s', tex), ('s', key), ('i', a), ('i', b)])
                elif action == 'showCompass':
                    name = rng.choice(list(rig.objects)) if rng.random() < 0.9 else b'nothing'
                    key = random_key_choice(rig, rng)
                    try:
                        rig.cmd.show_compass(name, key)
                    except R.FormatError as error:
                        model_error = error
                    rig.handler(SCR_SHOW_COMPASS, [('s', name), ('s', key)])
                elif action == 'hud_showMessage':
                    units = [rng.randint(1, 0xFFFF) for _ in range(rng.randint(0, 101))]
                    text = rig.put_units(units + [0])
                    frames, slot, force = rng.randint(-5, 400), rng.choice((-1, 0, 1, 2, 3)), rng.choice((0, 0, 1, 0x80, 0x100))
                    rig.hud.show_message(units, frames, slot, force)
                    rig.call(HUD_SHOW_MESSAGE, text, frames, slot, force)   # 64-bit sign-extended, as a caller's registers
                elif action == 'hud_showHelpMessage':
                    slot = rng.choice((-1, 0, 1, 2, 3))
                    t, b = rng.getrandbits(32), rng.getrandbits(32)
                    rig.hud.show_help(slot, t, b)
                    rig.call(HUD_SHOW_HELP, slot, t, b)
                elif action == 'hud_setBust':
                    tex = random_key(rng, 0, 39, high_bytes=0.1)
                    units = [rng.randint(1, 0xFFFF) for _ in range(rng.randint(0, 70))]
                    a, b = rng.getrandbits(32), rng.getrandbits(32)
                    rig.hud.set_bust(tex, units, a, b)
                    rig.call(HUD_SET_BUST, rig.put(tex + b'\0'), rig.put_units(units + [0]), a, b)
                elif action == 'hud_setCompassTarget':
                    words = tuple(rng.getrandbits(32) for _ in range(3))
                    units = [rng.randint(1, 0xFFFF) for _ in range(rng.randint(0, 60))]
                    vec = rig.put(struct.pack('<3I', *words), align=rng.choice((4, 16)))
                    rig.hud.set_compass(words, units)
                    rig.call(HUD_SET_COMPASS, vec, rig.put_units(units + [0]))
                else:
                    rig.hud.tick_message()
                    rig.call(HUD_TICK_MESSAGE)
                    rig.hud.tick_widgets()
                    rig.emu.r[29] = rig.sp
                    rig.emu.run(start=HUD_RUN_COUNTDOWN[0], until=(HUD_RUN_COUNTDOWN[1],))
            except EmuError as error:
                emu_error = error
            if model_error or emu_error:
                faults += 1
                chk.eq('%s: both refuse (model %s, original %s)' % (action, model_error, emu_error),
                       bool(emu_error), bool(model_error))
                # the lookup before the fault happened on both sides; the rest is undefined
                chk.eq('ring after the fault', rig.emu.mem.u8(R.G_NF_INDEX), rig.model_table.nf_index)
                continue
            rig.compare(chk, action)
            hud = rig.hud
            if action in ('setInfo', 'hud_showMessage') and len(hud.read_units(R.MESSAGE_TEXT, 200)) > 99:
                edges['message > 99 units'] += 1
            if action in ('showBust', 'hud_setBust') and len(hud.read_units(R.BUST_TEXT, 200)) > 31:
                edges['bust text > 31'] += 1
            if action in ('showCompass', 'hud_setCompassTarget') and len(hud.read_units(R.COMPASS_LABEL, 200)) > 31:
                edges['compass label > 31'] += 1
            if action == 'addHelpMessageF' and rig.cmd.last_f:
                if len(R.visible(rig.cmd.last_f[0])) > 31:
                    edges['help-F title > 31'] += 1
                if any(len(o) > len(R.visible(o)) + 1 for o in rig.cmd.last_f):
                    edges['help-F read past a terminator'] += 1
            rig.cmd.last_f = None
            edges['lookup misses'] += (rig.model_table.nf_index - ring_before) & 0xF
    report(label, chk.failures, chk.cases,
           'random sequences of the five handlers (real scr_getAddr/scr_getString, text_lookup, '
           'wstr_format, wstr_copy, strcpy), the four setters and the two run-side timers (%s); after '
           'each: the HUD block 0x86aab0-0x86ac44 byte for byte (overruns included), the help-F '
           'buffers, 11 state words, the outward calls with their arguments, the miss ring; '
           '%d undefined cases (missing compass object), both sides refused; edges reached: %s'
           % (', '.join('%s %d' % kv for kv in sorted(counts.items())), faults,
              ', '.join('%s %d' % kv for kv in edges.items())), chk.examples)


# ---------------------------------------------------------------------------------------
# 4. sound_playOnObject and 5. Creature_setCharm, on the original handle pool
# ---------------------------------------------------------------------------------------
class PoolRig(Rig):
    """The original node pool (handle_initPool run for real) and ref_core's beside it."""

    def __init__(self, elf, rng):
        Rig.__init__(self, elf)
        self.rng = rng
        self.emu.record_calls = True
        self.call(H_INIT)
        self.pool = RC.HandlePool()
        self.cells = []

    def ptr(self, thing):
        if thing is None:
            return 0
        if isinstance(thing, RC.Node):
            return RC.HandlePool.NODE_BASE + RC.HandlePool.NODE_SIZE * thing.index
        if isinstance(thing, RC.Cell):
            return thing.name
        return thing.addr

    def new_object(self, flags=0x20, size=0x400):
        addr = self.emu.alloc(size)
        obj = R.Creature(addr, flags)
        obj.position = tuple(self.rng.getrandbits(32) for _ in range(3))
        self.emu.mem.w32(addr + 0xC, flags)
        for i, word in enumerate(obj.position):
            self.emu.mem.w32(addr + 0x10 + 4 * i, word)
        self.cells += obj.heads + [obj.target]
        return obj

    def link(self, head, obj):
        got = self.call(H_LINK, self.ptr(head), obj.heads[0].name, obj.addr)
        node = self.pool.link(head, obj.heads[0], obj)
        return got == self.ptr(node)

    def clear(self, head):
        self.call(H_CLEAR, self.ptr(head))
        self.pool.clear(head)

    def compare_pool(self, chk, what):
        mem = self.emu.mem
        for cell in self.cells:
            addr, thing, guard = mem.u32(cell.name), cell.next, 0
            while (addr or thing is not None) and guard < 7000:
                guard += 1
                if not chk.eq('%s: list 0x%x' % (what, cell.name), addr, self.ptr(thing)):
                    return
                got = (mem.u32(addr + 4), mem.u32(addr + 8), mem.u32(addr + 12))
                want = (self.ptr(thing.prev), self.ptr(thing.partner), self.ptr(thing.obj))
                if not chk.eq('%s: node 0x%x' % (what, addr), got, want):
                    return
                addr, thing = mem.u32(addr), thing.next
        addr, node = mem.u32(H_FREE_HEAD), self.pool.free
        for _ in range(16):
            if not chk.eq('%s: free list' % what, addr, self.ptr(node)) or node is None:
                return
            addr, node = mem.u32(addr), node.next


SLOT_FIELDS = ((0x04, 1, 'tracks'), (0x05, 1, 'capacity'), (0x06, 2, 'flags'), (0x08, 4, 'seq'),
               (0x0C, 4, 'track_link'), (0x20, 4, 'track_time'), (0x24, 2, 'track_flags'),
               (0x38, 2, 'serial'), (0x3A, 1, 'no_pos'), (0x3B, 1, 'frozen'), (0x3C, 1, 'released'),
               (0x40, 4, 'volume'), (0x44, 4, 'near'), (0x48, 4, 'far'))


def slot_state(mem, i):
    base = R.G_SOUND_SEQS + i * R.SEQ_STRIDE
    out = {}
    for off, size, name in SLOT_FIELDS:
        out[name] = {1: mem.u8, 2: mem.u16, 4: mem.u32}[size](base + off)
    out['track_words'] = tuple(mem.u32(base + 0x10 + 4 * k) for k in range(4))
    out['pos'] = tuple(mem.u32(base + 0x2C + 4 * k) for k in range(3))
    out['track_1e'] = mem.u16(base + 0x26)
    return out


def model_slot_state(slot):
    out = {name: getattr(slot, name) & ((1 << (8 * size)) - 1) for _off, size, name in SLOT_FIELDS}
    out['track_words'] = tuple(slot.track_words)
    out['pos'] = tuple(slot.pos)
    out['track_1e'] = 0
    return out


def test_sound(elf):
    label = 'sound.playOnObject'
    if not wanted(label):
        return
    chk = Check()
    stats = {'played': 0, 'no free slot': 0, 'category cap': 0, 'followed object': 0,
             'reused slot with a live object': 0, 'cut a track link': 0}
    for round_ in range(scaled(8)):
        rng = rng_for('sound/%d' % round_)
        rig = PoolRig(elf, rng)
        emu, mem = rig.emu, rig.emu.mem
        model = R.SoundSeqs(rig.pool)
        # categories and caps
        seqs = []
        for _ in range(12):
            addr = emu.alloc(0x40)
            group = rng.choice((0, 0, 1, 2, 3, 5))
            mem.w8(addr + 0x3C, group)
            model.groups[addr] = group
            seqs.append(addr)
        for g in range(1, 8):
            cap = rng.choice((0, 1, 2, 3, 6))
            mem.w8(R.G_SOUND_GROUP_LIMIT + g, cap)
            model.limits[g] = cap
        model.serial = rng.randrange(0x80)
        mem.w16(R.G_SOUND_SERIAL, model.serial)
        # slots: zero, then each busy or free with capacity 1 (one track)
        for i, slot in enumerate(model.slots):
            base = R.G_SOUND_SEQS + i * R.SEQ_STRIDE
            mem.write(base, bytes(R.SEQ_STRIDE))
            slot.capacity = rng.choice((1, 1, 1, 1, 0))
            mem.w8(base + 5, slot.capacity)
            if rng.random() < 0.6:
                slot.tracks, slot.seq = 1, rng.choice(seqs)
                mem.w8(base + 4, 1)
                mem.w32(base + 8, slot.seq)
            rig.cells.append(slot.handle_head)
        objects = [rig.new_object() for _ in range(10)]
        finish = rng.choice((0.02, 0.1, 0.25))
        for _ in range(scaled(1500)):
            chk.cases += 1
            roll = rng.random()
            # the world moves on: sounds finish (busy byte cleared, handle left), objects die
            if roll < finish:
                i = rng.randrange(R.SEQ_SLOTS)
                model.slots[i].tracks = 0
                mem.w8(R.G_SOUND_SEQS + i * R.SEQ_STRIDE + 4, 0)
                continue
            if roll < finish + 0.05:
                obj = rng.choice(objects)
                for cell in obj.heads:
                    rig.clear(cell)
                continue
            if roll < finish + 0.09:
                i = rng.randrange(R.SEQ_SLOTS)
                link = emu.alloc(0x20, fill=0x77)
                model.slots[i].track_link = link
                mem.w32(R.G_SOUND_SEQS + i * R.SEQ_STRIDE + 0xC, link)
                continue
            seq = rng.choice(seqs)
            obj = rng.choice(objects) if rng.random() < 0.7 else None
            frozen = rng.choice((0, 0, 1))
            volume = RC.f32(rng.uniform(0, 2))
            model.frozen = frozen
            busy_before = [s.tracks for s in model.slots]
            heads_before = [bool(s.handle_head.next) for s in model.slots]
            links_before = [s.track_link for s in model.slots]
            want, chosen = model.play_on_object(seq, obj, volume)
            emu.calls = []
            emu.stub(GAME_IS_FROZEN, ret=frozen, name='game_isFrozen')
            emu.reads = []
            emu.r[29] = rig.sp
            emu.f[12] = volume
            emu.r[4], emu.r[5], emu.r[31] = seq, obj.addr if obj else 0, emu.RETURN_ADDR
            emu.jump(SOUND_PLAY_ON_OBJECT)
            emu.run(max_steps=200000)
            got = emu.r[2] & M32
            seeds = [r for r in emu.reads if r[1] in (COSMETIC_SEED, SHARED_SEED)]
            emu.reads = None
            chk.eq('returned handle', got, want)
            chk.eq('seed reads', seeds, [])
            for i, slot in enumerate(model.slots):
                if not chk.eq('slot %d' % i, slot_state(mem, i), model_slot_state(slot)):
                    break
            chk.eq('serial', mem.u16(R.G_SOUND_SERIAL), model.serial)
            if chosen is not None and links_before[chosen] and not model.slots[chosen].track_link:
                chk.eq('cut track link +0x14', mem.u32(links_before[chosen] + 0x14), 0)
                stats['cut a track link'] += 1
            rig.compare_pool(chk, 'pool')
            if chosen is None:
                free = [i for i, b in enumerate(busy_before) if b == 0]
                stats['no free slot' if not free else 'category cap'] += 1
            else:
                stats['played'] += 1
                if obj is not None:
                    stats['followed object'] += 1
                    if heads_before[chosen]:
                        stats['reused slot with a live object'] += 1
    report(label, chk.failures, chk.cases,
           'sound_playOnObject with anim_push and the handle functions running for real '
           '(game_isFrozen stubbed): return value, 17 fields of all 32 slots, the serial, every '
           'handle list and the free list after each call; no read of either seed (%s)'
           % ', '.join('%s %d' % kv for kv in stats.items()), chk.examples)


def test_charm(elf):
    label = 'charm.liveTarget'
    if not wanted(label):
        return
    chk = Check()
    stats = {'stored': 0, 'refused (-1)': 0, 'refused (flag 0x20 clear)': 0, 'refused (player)': 0,
             'target still held by others': 0, 'target linked twice by this creature': 0}
    for round_ in range(scaled(8)):
        rng = rng_for('charm/%d' % round_)
        rig = PoolRig(elf, rng)
        mem = rig.emu.mem
        creatures = [rig.new_object(rng.choice((0x20, 0x20, 0x20, 0x60, 0x0, 0x28)))
                     for _ in range(16)]
        lists = [RC.Cell(rig.emu.alloc(4)) for _ in range(4)]
        rig.cells += lists
        for _ in range(scaled(1200)):
            chk.cases += 1
            roll = rng.random()
            c = rng.choice(creatures)
            if roll < 0.45:
                # creature c takes a target (as the AI does: clear, then link)
                target = rng.choice(creatures)
                if rng.random() < 0.85:
                    rig.clear(c.target)
                elif c.target.next is not None:
                    stats['target linked twice by this creature'] += 1
                chk.eq('handle_link return', rig.link(c.target, target), True)
            elif roll < 0.55:
                rig.link(rng.choice(lists), rng.choice(creatures))
            elif roll < 0.62:
                victim = rng.choice(creatures)
                for cell in victim.heads:
                    rig.clear(cell)
            else:
                charm = rng.choice((0, 0, 0xFFFF, 120, 5))
                c.charm = charm
                mem.w16(c.addr + 0x312, charm)
                frames, team = rng.choice((0xFFFF, 600, 1)), rng.choice((0, 1, 2, 0x81))
                held = c.target.next
                others = held is not None and held.obj is not None and any(
                    o is not c and RC.HandlePool.items(o.target).count(held.obj) for o in creatures)
                stored = R.set_charm(rig.pool, c, frames, team)
                rig.emu.calls = []
                rig.call(SET_CHARM, c.addr, frames, team)
                if stored:
                    stats['stored'] += 1
                    if others:
                        stats['target still held by others'] += 1
                elif charm == 0xFFFF:
                    stats['refused (-1)'] += 1
                elif not c.flags & 0x20:
                    stats['refused (flag 0x20 clear)'] += 1
                else:
                    stats['refused (player)'] += 1
                got = (mem.u8(c.addr + 0x310), mem.u16(c.addr + 0x312), mem.u32(c.addr + 0x234))
                want = (c.team, c.charm, rig.ptr(c.target.next))
                chk.eq('creature +0x310/+0x312/+0x234', got, want)
                if stored:
                    c.team = c.team  # stored byte already compared
            rig.compare_pool(chk, 'pool')
    report(label, chk.failures, chk.cases,
           'Creature_setCharm and handle_clear running for real on random targets, other '
           'creatures holding the same target, extra lists and destroyed objects: the three '
           'creature fields, every handle list and the free list after each step (%s)'
           % ', '.join('%s %d' % kv for kv in stats.items()), chk.examples)


TESTS = [test_hash, test_tables, test_wstr, test_format, test_format_ascii, test_hud,
         test_sound, test_charm]


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
