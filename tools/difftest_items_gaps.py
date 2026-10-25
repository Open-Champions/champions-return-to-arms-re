#!/usr/bin/env python3
"""difftest_items_gaps.py - tools/ref_items_gaps.py against the original code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_items_gaps.py [SLUS_209.73] [--cases N] [--seed N] [-k TEXT]

The original machine code runs in tools/ee_emu.py.  Suites (each a stretch of a function,
entered with the registers the function holds there):

  lobby      lobby_task 0x3276a4-0x327728: own number, count, host bit, kind bits
  menu       frontend_run 0x1e1b6c-0x1e1b90 (menu path) and 0x1e0d2c-0x1e0d5c (kind bits)
  record     net_launchPrepare 0x1351d8-0x13520c: the record address for own numbers
  fill       net_launchPrepare 0x1353f4-0x135430: +0xa0..+0xa3, +0xf4 under the host bit,
             game_scanCm1Vars stubbed (seeded answer, call and argument compared)
  receive    net_launchUpdate 0x137464 to 0x137518 / 0x137554: record 0 -> difficulty,
             kill limit, mode flags, game_set4f7110 (stubbed, call and argument compared)
  bonus      0x4d8ae8: every loaded segment is scanned for an instruction whose 16-bit
             immediate forms the address with a load, store or addiu, and every data word
             for the address of the word, of g_numPlayers or of g_players; the only hit
             must be the reader 0x1b69e0 (and one unrelated addiu of another high half)

Every case compares, over every byte either side wrote, the final memory, plus the calls.
A call to any address other than the listed stub fails the case.
"""
import os
import random
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError     # noqa: E402
import ref_items_gaps as R          # noqa: E402

ELF_SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = [os.path.join(ROOT, 'local', 'elf', 'SLUS_209.73'), os.path.join(ROOT, 'SLUS_209.73')]
OPTIONS = {'cases': 200, 'seed': 20973, 'filter': None}
RESULTS = []
SCRATCH = 0x01FF0000
M32 = 0xFFFFFFFF


def report(name, ok, detail=''):
    RESULTS.append((name, ok))
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, detail))


class RefMem:
    """Copy-on-write bytes over the emulator's pristine image; records written bytes."""

    def __init__(self, base):
        self.base, self.bytes, self.written = base, {}, set()

    def _get(self, a):
        if a in self.bytes:
            return self.bytes[a]
        return self.base.mem.u8(a) if self.base.mem.is_mapped(a) else 0

    def load(self, a, n):
        return int.from_bytes(bytes(self._get(a + i) for i in range(n)), 'little')

    def store(self, a, n, v, track=True):
        for i, b in enumerate((v & ((1 << (8 * n)) - 1)).to_bytes(n, 'little')):
            self.bytes[a + i] = b
            if track:
                self.written.add(a + i)

    def u8(self, a): return self.load(a, 1)
    def u32(self, a): return self.load(a, 4)
    def w8(self, a, v): self.store(a, 1, v)
    def w32(self, a, v): self.store(a, 4, v)


class Case:
    def __init__(self, elf, base):
        self.emu = EE(elf)
        self.ref = RefMem(base)
        self.emu.mem.map(SCRATCH, 0x10000)

    def w(self, a, n, v):
        self.emu.mem.store(a, n, v & ((1 << (8 * n)) - 1))
        self.ref.store(a, n, v, track=False)

    def run(self, start, stops, regs=(), stubs=None):
        emu = self.emu
        allowed = set(stubs or {})
        for addr, fn in (stubs or {}).items():
            emu.stub(addr, function=fn)
        for name, v in regs:
            emu.set_reg(name, v)
        emu.reset_log()
        emu.run(start, until=stops, max_steps=10000)
        bad = [c for c in emu.calls if c.target not in allowed]
        return [(c.target, c.args[0] & M32) for c in emu.calls], bad

    def compare(self, ref_calls, emu_calls):
        addrs = set(self.ref.written)
        for (_pc, a, n, _v) in self.emu.writes:
            addrs.update(range(a, a + n))
        diffs = [hex(a) for a in sorted(addrs)
                 if a < self.emu.stack_lo or a >= self.emu.stack_hi
                 if self.emu.mem.u8(a) != self.ref.u8(a)]
        return not diffs and list(ref_calls) == list(emu_calls), diffs


def byte_choice(rng):
    return rng.choice([0, 1, 2, 3, 4, 5, 0x7F, 0x80, 0xFF, rng.randrange(256)])


def suite_lobby(elf, base, rng):
    bad = 0
    for _ in range(OPTIONS['cases']):
        c = Case(elf, base)
        ctx = SCRATCH + 0x100
        c.w(R.G_LOBBY_CTX, 4, ctx)
        c.w(ctx + R.LOBBY_OWN, 1, rng.choice([0, 0, 1, 2, 3, 4, 0xFF, 0x80, byte_choice(rng)]))
        for off in (R.ROOM_DIFFICULTY, R.ROOM_MODE, R.ROOM_KILL_LIMIT, R.ROOM_MISSION):
            c.w(ctx + R.LOBBY_ROOM + off, 1, byte_choice(rng))
        for off in range(0x10):
            c.w(R.SETTINGS + off, 1, byte_choice(rng))
        c.w(R.G_CHAR_KIND, 1, byte_choice(rng))
        ref_calls = R.lobby_set_host(c.ref)
        emu_calls, extra = c.run(0x3276A4, {0x327728},
                                 [('a1', ctx + R.LOBBY_OWN), ('a2', ctx), ('a3', R.SETTINGS)])
        ok, diffs = c.compare(ref_calls, emu_calls)
        if not ok or extra:
            bad += 1
            if bad <= 3:
                print('   lobby mismatch', diffs[:8], extra[:2])
    report('lobby', bad == 0, '%d cases, %d mismatches' % (OPTIONS['cases'], bad))


def suite_menu(elf, base, rng):
    bad = 0
    for _ in range(OPTIONS['cases']):
        c = Case(elf, base)
        for off in range(0x10):
            c.w(R.SETTINGS + off, 1, byte_choice(rng))
        c.w(R.G_CHAR_KIND, 1, byte_choice(rng))
        sel = rng.choice([0, 1, 2, -1, rng.getrandbits(32)])
        ref_calls = R.frontend_set_host(c.ref, sel)
        emu_calls, extra = c.run(0x1E1B6C, {0x1E1B90}, [('s4', sel & 0xFFFFFFFFFFFFFFFF)])
        ok1, d1 = c.compare(ref_calls, emu_calls)
        ref_calls = R.frontend_set_kind(c.ref)
        emu_calls2, extra2 = c.run(0x1E0D2C, {0x1E0D5C}, [('v0', 0x500000)])   # lui in the delay slot at 0x1e0d28
        ok2, d2 = c.compare(ref_calls, emu_calls2)
        if not (ok1 and ok2) or extra or extra2:
            bad += 1
            if bad <= 3:
                print('   menu mismatch', d1[:6], d2[:6])
    report('menu', bad == 0, '%d cases, %d mismatches' % (OPTIONS['cases'], bad))


def suite_record(elf, base, rng):
    bad = 0
    owns = list(range(-128, 128))
    for own in owns:
        c = Case(elf, base)
        c.w(R.SETTINGS + R.S_OWN, 1, own)
        c.w(R.SETTINGS + R.S_FLAGS, 1, rng.randrange(256))
        _calls, extra = c.run(0x1351D8, {0x13520C, 0x1352F0}, [('fp', 0x400000)])
        if (c.emu.reg('s0') & M32) != R.own_record(own) or extra:
            bad += 1
    report('record', bad == 0, '%d own numbers, %d mismatches' % (len(owns), bad))


def suite_fill(elf, base, rng):
    bad = hosts = 0
    for _ in range(OPTIONS['cases']):
        c = Case(elf, base)
        for off in range(0x10):
            c.w(R.SETTINGS + off, 1, byte_choice(rng))
        own = rng.randrange(4)
        record = R.own_record(own)
        for off in range(0x9C, 0x100, 4):
            c.w(record + off, 4, rng.getrandbits(32))
        scan = rng.choice([0, 1, 8, 9, -1, rng.getrandbits(32)]) & M32
        hosts += c.ref.u8(R.SETTINGS) & 1
        ref_calls = R.launch_fill_host_fields(c.ref, record, scan)
        emu_calls, extra = c.run(0x1353F4, {0x135430}, [('fp', 0x400000), ('s0', record)],
                                 stubs={R.GAME_SCAN_CM1: lambda emu, s=scan: s})
        ok, diffs = c.compare(ref_calls, emu_calls)
        if not ok or extra:
            bad += 1
            if bad <= 3:
                print('   fill mismatch', diffs[:8], emu_calls, ref_calls)
    report('fill', bad == 0, '%d cases (%d with the host bit), %d mismatches'
           % (OPTIONS['cases'], hosts, bad))


def suite_receive(elf, base, rng):
    bad = calls = 0
    for _ in range(OPTIONS['cases']):
        c = Case(elf, base)
        rec = R.LAUNCH_RECS
        c.w(rec + R.R_DIFFICULTY, 1, byte_choice(rng))
        c.w(rec + R.R_MODE, 1, rng.choice([0, 1, 2, 3, 4, 0xFF, 0x83, byte_choice(rng)]))
        c.w(rec + R.R_KILL_LIMIT, 1, byte_choice(rng))
        c.w(rec + R.R_CM1, 4, rng.choice([0, 3, 9, M32, rng.getrandbits(32)]))
        for a in (R.G_DIFFICULTY, R.G_PVP_MODE_A, R.G_PVP_MODE_B, R.G_MODE_3):
            c.w(a, 4, rng.getrandbits(32))
        ref_calls = R.launch_receive(c.ref)
        calls += len(ref_calls)
        emu_calls, extra = c.run(0x137464, {0x137518, 0x137554},
                                 stubs={R.GAME_SET_CM1: lambda emu: 0})
        ok, diffs = c.compare(ref_calls, emu_calls)
        if not ok or extra:
            bad += 1
            if bad <= 3:
                print('   receive mismatch', diffs[:8], emu_calls, ref_calls)
    report('receive', bad == 0, '%d cases (%d with game_set4f7110), %d mismatches'
           % (OPTIONS['cases'], calls, bad))


LOADSTORE = {0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x2B, 0x2C,
             0x2D, 0x2E, 0x2F, 0x1A, 0x1B, 0x1E, 0x1F, 0x31, 0x37, 0x39, 0x3F, 0x09}


def suite_bonus(elf_path):
    data = open(elf_path, 'rb').read()
    phoff, = struct.unpack_from('<I', data, 28)
    phentsize, phnum = struct.unpack_from('<HH', data, 42)
    segs = []
    for i in range(phnum):
        t, off, va, _pa, fsz, _msz, _fl, _al = struct.unpack_from('<8I', data, phoff + i * phentsize)
        if t == 1:
            segs.append((va, off, fsz))
    lo = R.G_LOAD_BONUS & 0xFFFF
    imm_hits, ptr_hits = [], []
    targets = {R.G_LOAD_BONUS, 0x4D8AE0, 0x4D8AF0}
    for va, off, fsz in segs:
        for i in range(0, fsz - 3, 4):
            w, = struct.unpack_from('<I', data, off + i)
            if (w & 0xFFFF) == lo and (w >> 26) in LOADSTORE:
                imm_hits.append(va + i)
            if w in targets:
                ptr_hits.append(va + i)
    # each immediate hit: is the base register's high half 0x4e (0x4d8ae8 = 0x4e0000 - 0x7518)?
    emu = EE(elf_path)
    formed = []
    for a in imm_hits:
        w = emu.mem.u32(a)
        base = (w >> 21) & 31
        high = None
        for back in range(1, 40):
            p = emu.mem.u32(a - 4 * back)
            if (p >> 26) == 0x0F and ((p >> 16) & 31) == base:
                high = p & 0xFFFF
                break
        if high == 0x4E:
            formed.append(a)
    ok = formed == [R.LOAD_BONUS_READER] and not ptr_hits
    report('bonus', ok, 'immediate 0x8ae8 in %d instructions, %d with high half 0x4e: %s; '
           'data words holding the three addresses: %d'
           % (len(imm_hits), len(formed), ' '.join(hex(a) for a in formed), len(ptr_hits)))


def main(argv):
    args, i = [], 0
    while i < len(argv):
        a = argv[i]
        if a == '--cases':
            OPTIONS['cases'] = int(argv[i + 1]); i += 2
        elif a == '--seed':
            OPTIONS['seed'] = int(argv[i + 1]); i += 2
        elif a == '-k':
            OPTIONS['filter'] = argv[i + 1]; i += 2
        else:
            args.append(a); i += 1
    path = args[0] if args else next((p for p in CANDIDATES if os.path.exists(p)), None)
    if not path or not os.path.exists(path):
        print('SKIP: no SLUS_209.73 (pass its path)')
        return 0
    import hashlib
    if hashlib.sha256(open(path, 'rb').read()).hexdigest() != ELF_SHA:
        print('SKIP: not the US v2.00 executable')
        return 0
    base = EE(path)
    rng = random.Random(OPTIONS['seed'])
    suites = [('lobby', lambda: suite_lobby(path, base, rng)),
              ('menu', lambda: suite_menu(path, base, rng)),
              ('record', lambda: suite_record(path, base, rng)),
              ('fill', lambda: suite_fill(path, base, rng)),
              ('receive', lambda: suite_receive(path, base, rng)),
              ('bonus', lambda: suite_bonus(path))]
    for name, fn in suites:
        if OPTIONS['filter'] is None or OPTIONS['filter'] in name:
            try:
                fn()
            except EmuError as e:
                report(name, False, 'emulator stopped: %s' % e)
    failed = sum(1 for _n, ok in RESULTS if not ok)
    print('%d suites, %d failed (seed %d, %d cases)' % (len(RESULTS), failed, OPTIONS['seed'],
                                                         OPTIONS['cases']))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
