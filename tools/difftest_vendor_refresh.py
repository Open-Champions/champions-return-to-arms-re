#!/usr/bin/env python3
"""Bounded refresh/control-flow research; output is counts only.

Original EE instructions execute. Resource I/O, item generation, valuation,
task registration, and pow are controlled stubs; this is not stock parity.
No existing reference module or vector is used.
"""
import hashlib
import itertools
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:] = [p for p in sys.path if Path(p or '.').resolve() != HERE] + [str(HERE)]
import unittest  # Keep stdlib dis ahead of tools/dis.py.
from ee_emu import EE, s32
from ps2elf import Elf

ELF = sys.argv[1] if len(sys.argv) > 1 else None
PIN = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
STRINGS = {0x3B8534, 0x3B868C, 0x3B8DC4}
VARS = STRINGS | {0x1ED778, 0x1ED854}
COUNTS = (0x868078, 0x869280, 0x86A488)
STORES = ((0x554678, 1), (0x554680, 1), (0x554688, 2), (0x554698, 3), (None, None))


def static_xrefs():
    elf = Elf(ELF)
    base, _, size = elf.text
    calls, jumps = [], []
    for pc in range(base, base + size, 4):
        word = elf.u32(pc)
        target = ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        if target == 0x1C7AF8:
            if word >> 26 == 3:
                calls.append(pc)
            elif word >> 26 == 2:
                jumps.append(pc)
    assert calls == [0x116C58, 0x144074, 0x1440C4, 0x18DBB4, 0x22F850, 0x22F86C, 0x3230C4, 0x3230F0]
    assert jumps == [0x1ECCF0]
    assert not elf.ptrs_to(0x1C7AF8)
    return 3


def machine():
    e = EE(ELF)
    e.follow = set(STRINGS)
    return e


def quest(e, value):
    e.follow |= VARS
    e.call(0x1ED854, 0x538750, value)
    assert s32(e.call(0x1ED778, 0x538750)) == value
    e.reset_log()


def name(e, address):
    return e.mem.cstr(address) if address else 'synthetic_nonstore'


def dispatch():
    cases = 0
    for (address, mode), players, act in itertools.product(STORES, (1, 2, 3, 4), (0, 1, 7)):
        e = machine()
        e.mem.write(0x41B721, name(e, address).encode() + b'\0')
        e.mem.w32(0x4D8AE0, players)
        e.mem.w32(0x88D3D4, act)
        # Same destination twice: caller has no previous-stock freshness cache.
        for repeat in range(2):
            e.reset_log()
            assert e.run(0x323064, until=(0x32310C,), max_steps=10000) == 'stop'
            stock = [c for c in e.calls if c.target == 0x1C7AF8]
            assert len(stock) == int(mode is not None)
            if stock:
                assert stock[0].args[:3] == (0, mode, 1)
                assert e.calls.index(stock[0]) < next(i for i, c in enumerate(e.calls) if c.target == 0x3224D8)
            cases += 1
    # Case-sensitive comparisons; a changed case or suffix is not an exact match.
    for address, _ in STORES[:-1]:
        for transform in (str.upper, lambda n: n + '_synthetic'):
            e = machine()
            e.mem.write(0x41B721, transform(name(e, address)).encode() + b'\0')
            e.run(0x323064, until=(0x32310C,), max_steps=10000)
            assert not any(c.target == 0x1C7AF8 for c in e.calls)
            cases += 1
    return cases


def timing():
    cases = 0
    for (address, mode), online, pending in itertools.product(STORES, (0, 1), (False, True)):
        e = machine()
        e.follow.add(0x322934)  # Real 10-frame warm-up initialization.
        e.mem.map(0x10000000, 4096)
        e.r[16], e.r[19], e.r[20] = 0x5541F0, 0x400000, 0x550000
        e.mem.w8(0x402791, online)
        e.mem.w32(0x4D8AE0, 1)
        e.mem.w32(0x4DCEC8, e.alloc(0x400))
        e.mem.write(0x41B721, name(e, address).encode() + b'\0')
        terrain_calls = []
        equipment_calls = []
        readiness = []
        e.stub(0x17FE88, function=lambda m: terrain_calls.append(1) or 0)
        e.stub(0x1A30B0, function=lambda m: equipment_calls.append(1) or int(pending and len(equipment_calls) <= 11))
        e.stub(0x13E008, function=lambda m: readiness.append(1) or int(len(readiness) == 2))
        assert e.run(0x322E30, until=(0x32310C,), max_steps=30000) == 'stop'
        targets = [c.target for c in e.calls]
        assert targets.index(0x320EDC) < targets.index(0x1EDA24) < targets.index(0x17FE88)
        assert len(terrain_calls) == (14 if pending else 10)
        assert len(readiness) == (2 if online else 0)
        stock = [c for c in e.calls if c.target == 0x1C7AF8]
        assert len(stock) == int(mode is not None)
        if stock:
            idx = e.calls.index(stock[0])
            assert idx > max(i for i, c in enumerate(e.calls) if c.target == 0x1A30B0)
            if online:
                assert idx > max(i for i, c in enumerate(e.calls) if c.target == 0x13E008)
            assert idx < targets.index(0x3224D8)
        cases += 1
    return cases


def act_clear():
    cases = 0
    for front, changed, latch, task, players in itertools.product((0, 1), (0, 1), (0, 1), (0, 1), (1, 4)):
        e = machine()
        e.follow.add(0x1ED728)
        quest(e, 9)
        e.r[19] = 0x420000
        e.mem.w32(0x41B510, front)
        e.mem.w8(0x4F8F28, latch)
        e.mem.w32(0x4D8AE0, players)
        e.stub(0x217F70, ret=changed)
        e.stub(0x19E5E8, ret=task)
        assert e.run(0x320F8C, until=(0x321024,), max_steps=10000) == 'stop'
        cleared = not front and changed and not latch and not task
        assert sum(c.target == 0x1ED728 for c in e.calls) == int(cleared)
        assert sum(c.target == 0x1BE1D8 for c in e.calls) == (players if cleared else 0)
        assert not any(c.target == 0x1C7AF8 for c in e.calls)
        assert s32(e.call(0x1ED778, 0x538750)) == (0 if cleared else 9)
        cases += 1
    return cases


def act_compare():
    cases = 0
    for old, found in itertools.product((0, 1, 7), (-1, 0, 1, 7)):
        e = machine()
        e.follow.add(0x2180A8)
        e.mem.w32(0x88D3D4, old)
        e.stub(0x217D30, ret=found)
        changed = found != -1 and found != old
        assert e.call(0x217F70, 0) == int(changed)
        assert e.mem.u32(0x88D3D4) == (found if changed else old)
        cases += 1
    return cases


def stock_machine(level=5, difficulty=2):
    e = machine()
    quest(e, level)
    e.mem.w32(0x4F719C, difficulty)
    e.stub(0x3A5AC8, function=lambda m: m.fset(0, 10000.0) or 0)
    e.stub(0x104CA4, ret=1)  # Controlled generation success; blank synthetic record.
    e.stub(0x108924, ret=0)  # Controlled nonduplicate.
    e.stub(0x1024A8, ret=0)  # Equal controlled values; no swap.
    e.stub(0x104758, ret=0)  # Blank optional result; no extra append.
    return e


def stock_refresh():
    cases = 0
    baseline = None
    # Vary caller slot, mode, third argument, players, act, monster scale and levels.
    variants = [(slot, mode, third, players, act) for slot, mode, third, players, act in
                itertools.product((0, 3), (1, 2, 3), (0, 1), (1, 4), (0, 7))]
    for slot, mode, third, players, act in variants:
        e = stock_machine()
        e.mem.w32(0x4D8AE0, players)
        e.mem.w32(0x88D3D4, act)
        e.mem.w32(0x4F714C, 0x3F800000 if players == 1 else 0x42C80000)
        for p in range(4):
            e.mem.w8(0x4D8AF0 + p * 0x4C30 + 0x58, 1 if players == 1 else 80)
            e.mem.w8(0x4D8AF0 + p * 0x4C30 + 0x59, 1 if players == 1 else 80)
        # Existing populated counts do not inhibit either invocation.
        for count in COUNTS:
            e.mem.w32(count, 42)
        for repeat in range(2):
            e.mem.w32(0x404460, 20973)
            e.reset_log()
            e.reads = []
            e.call(0x1C7AF8, slot, mode, third, max_steps=150000)
            counts = tuple(e.mem.u32(c) for c in COUNTS)
            targets = [c.target for c in e.calls]
            signature = (counts, tuple((c.site, c.target, c.args[:8], c.fargs) for c in e.calls if c.target in (0x104CA4, 0x104758, 0x1069B8)))
            if baseline is None:
                baseline = signature
            assert signature == baseline
            assert counts == (26, 17, 9)
            assert targets.count(0x104CA4) == 45
            assert targets.count(0x1069B8) == 7
            assert targets.count(0x1ED778) == 2
            assert 0x19E4A0 not in targets
            direct_reads = [a for pc, a, size, value in e.reads if 0x1C7AF8 <= pc < 0x1C8A00]
            assert 0x4D8AE0 not in direct_reads and 0x88D3D4 not in direct_reads and 0x4F714C not in direct_reads
            assert not any(0x4D8AF0 <= a < 0x4D8AF0 + 4 * 0x4C30 for a in direct_reads)
            cases += 1
    return cases


def menu_preserves_stock():
    cases = 0
    for slot, online, local, guarded in itertools.product((0, 3), (0, 1), (0, 1), (0, 1)):
        e = machine()
        quest(e, 9)
        e.mem.w8(0x402791, online)
        e.stub(0x13E150, ret=local)
        e.stub(0x1BF478, ret=guarded)
        e.mem.write(0x866E78, bytes([0xA5]) * (3 * 0x1208))
        before = e.mem.read(0x866E78, 3 * 0x1208)
        e.call(0x1C7AF8, slot, 0, 1, max_steps=10000)
        assert e.mem.read(0x866E78, 3 * 0x1208) == before
        targets = [c.target for c in e.calls]
        assert targets.count(0x1ED778) == 1
        assert not any(t in targets for t in (0x104CA4, 0x104758, 0x1069B8, 0x3A5AC8))
        assert targets.count(0x19E4A0) == int(not (online and guarded))
        cases += 1
    return cases


def progression_prefix():
    cases = 0
    signatures = {}
    for level, difficulty in itertools.product((0, 1, 5, 11, 12, 127, -1), (1, 2, 3)):
        e = machine()
        quest(e, level)
        e.mem.w32(0x4F719C, difficulty)
        e.r[4:7] = [0, 1, 1]
        assert e.run(0x1C7AF8, until=(0x1C7C34,), max_steps=10000) == 'stop'
        # f12 receives f20 only in the pending call's delay slot at 0x1c7c38.
        assert e.fget(20) == 1600.0 * (level + 11 * (difficulty - 1))
        if level == 0 or level < 0 or level > 11:
            assert e.fget(23) == 1.0
        else:
            assert 1 + level / 3 - 0.00001 < e.fget(23) <= 1 + level / 3
        assert sum(c.target == 0x1ED778 for c in e.calls) == 2
        signatures[level, difficulty] = (e.f[20], e.f[23])
        cases += 1
    assert signatures[0, 1] != signatures[1, 1]
    assert signatures[0, 1] != signatures[0, 2]
    return cases


def player_class_bias():
    cases = 0
    next_seed = lambda seed: (seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
    for entry, stop in ((0x104CA4, 0x104E04), (0x104758, 0x104860)):
        for players in (1, 2, 3, 4):
            for cloth in range(players + 1):
                for seed in (7, 20973):
                    e = machine()
                    e.mem.w32(0x4D8AE0, players)
                    for p in range(4):
                        e.mem.w32(0x4D8AF0 + p * 0x4C30 + 0x50, 4 if p < cloth else 0)
                    e.mem.w32(0x404464, seed)
                    e.r[4:9] = [e.alloc(0x48), 10000, 1, -1 & 0xFFFFFFFFFFFFFFFF, 20]
                    assert e.run(entry, until=(stop,), max_steps=3000) == 'stop'
                    threshold = int((cloth / players) * 65536)
                    step1 = next_seed(seed)
                    exclude = threshold < ((step1 >> 16) % 0xFFFF)
                    if entry == 0x104CA4:
                        prefer = not exclude and cloth > 0 and ((next_seed(step1) >> 16) % 0xFFFF) <= 0xBFFF
                        assert e.mem.u32(e.r[29] + 0x264) == int(exclude)
                        assert e.mem.u32(e.r[29] + 0x268) == int(prefer)
                        assert e.mem.u32(0x404464) == (next_seed(step1) if not exclude and cloth > 0 else step1)
                    else:
                        assert e.r[22] == int(exclude)
                        assert e.mem.u32(0x404464) == step1
                    cases += 1
    return cases


def dormant_daemon_boundary():
    cases = 0
    for previous, current in ((100, 99), (100, 100), (100, 220), (100, 221),
                              (100, 222), (0xFFFFFFF0, 105), (0, 0x80000000)):
        e = machine()
        obj = e.alloc(0x50)
        e.mem.w32(obj + 0x4C, previous)
        e.mem.w32(0x44FDD0, current)
        e.call(0x1D1490, obj)
        refresh = s32(current - previous) >= 121
        assert sum(c.target == 0x1C8A00 for c in e.calls) == int(refresh)
        assert e.mem.u32(obj + 0x4C) == (current if refresh else previous)
        assert not any(c.target == 0x1C7AF8 for c in e.calls)
        cases += 1
    return cases


if __name__ == '__main__':
    if ELF is None:
        raise SystemExit('usage: difftest_vendor_refresh.py PRIVATE_EXECUTABLE')
    assert hashlib.sha256(Path(ELF).read_bytes()).hexdigest() == PIN
    total = 0
    for check in (static_xrefs, dispatch, timing, act_clear, act_compare, stock_refresh,
                  menu_preserves_stock, progression_prefix, player_class_bias,
                  dormant_daemon_boundary):
        count = check()
        total += count
        print('PASS %s cases=%d' % (check.__name__, count), flush=True)
    print('PASS total=%d mismatches=0' % total)
