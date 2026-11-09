#!/usr/bin/env python3
"""Stock-slot contents before the first pass, and the unwritten record bytes the
duplicate compare reads. Original functions run in tools/ee_emu.py.

Groups (seeds 20973 and 7 where a pass runs):
  boot     ELF entry 0x14fa88 with the lists pre-filled with a sentinel; then main's
           run-once static-constructor walker 0x3ad310 and the stock constructor 0x1d1988
  census   every instruction that forms an address inside the lists; other writers
  compare  0x108924 on planted pairs: which record bytes it reads
  residue  real stock passes with differential stack / slot sentinels, and two passes
           in a row from the boot state
Output is counts and addresses only. Pass the private executable.
"""
import argparse
import bisect
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != HERE] + [HERE]
import unittest  # noqa: E402,F401  tools/dis.py must not shadow stdlib dis.
from ee_emu import EE  # noqa: E402
from ps2elf import Elf  # noqa: E402
from difftest_items import Original, EXPECTED_SHA256  # noqa: E402
from difftest_vendor_close import control_sites, formed_refs  # noqa: E402
import ref_items as I  # noqa: E402
import ref_vendor_stock as S  # noqa: E402

SEEDS = (20973, 7)
LISTS = (S.STOCK, S.STOCK + 3 * S.LIST_STRIDE)          # three lists with their counts
SCAN_END = S.STOCK + 4 * S.LIST_STRIDE + 0x48 * 64        # through the category-2 scan window
ENTRY, MAIN, BSS_STORE, BSS = 0x14FA88, 0x323DCC, 0x14FBE0, (0x564300, 0x90A430)
SAME, STOCK_FN, VARS, RESOURCE = 0x108924, 0x1C7AF8, 0x1ED778, 0x173558
SHOP_BUY, GIVE, VALUE = 0x1D1240, 0x1C1868, 0x1024A8
# Every instruction that forms an address inside the lists (lui pairing, loads/stores too).
CENSUS = {0x1C5F94: 0x1C5F78, 0x1C7C08: 0x1C7AF8, 0x1C7FC8: 0x1C7AF8, 0x1C81C0: 0x1C7AF8,
          0x1C8598: 0x1C7AF8, 0x1C8A1C: 0x1C8A00, 0x1C8AD0: 0x1C8A00, 0x1C8B60: 0x1C8A00,
          0x1CBC94: 0x1CBBE8, 0x1CC070: 0x1CBBE8, 0x1CC898: 0x1CC7E0, 0x1D1168: 0x1D10B0,
          0x1D1438: 0x1D13C8}
RETURNS = {0x1C7E30: 0, 0x1C8078: 1, 0x1C8430: 2}       # 0x108924 returns, by category
CONTEXTS = ((0, 1),)                                     # (storeLevel, difficulty)
FILLS = ((0x5C, 0xA5), (0x3D, 0xA5), (0x5C, 0x96))       # (stack, slot) sentinels
SLOT_STORES = {0x106A68, 0x105AE0, 0x105744, 0x1C8660, 0x1C86A8}
WALKER, WALK_SITE, STOCK_CTOR, ITEM_ARRAY_CTOR = 0x3AD310, 0x323E10, 0x1D1988, 0x1D10B0
CTOR_STORES = {0x1D1194, 0x1D11AC, 0x1D11B4, 0x1D11CC, 0x1D11D8}
BOOT_CONTEXT = (8, 2)


def constructed():
    """The record the item constructor leaves on zeroed memory: prefix and suffix 0xff,
    the four modifier codes -1, everything else 0 (built here, not copied)."""
    raw = bytearray(S.ITEM_SIZE)
    raw[0x20] = raw[0x21] = 0xFF
    for code in range(4):
        struct.pack_into('<h', raw, 0x24 + 8 * code, -1)
    return bytes(raw)


def sha(path):
    with open(path, 'rb') as source:
        return hashlib.sha256(source.read()).hexdigest()


class Reached(Exception):
    pass


def boot_cases(path):
    """The entry runs with kernel calls answered 0 and every callee stubbed, to main."""
    e = EE(path)
    e.mem.auto_map = True
    e.follow = set()
    lo, hi = LISTS[0], SCAN_END
    e.mem.write(lo, b'\xa5' * (hi - lo))
    kernel = []
    e.syscall_handler = lambda emu: (kernel.append(emu.r[3] & 0xFF), emu.r.__setitem__(2, 0))
    seen = {}

    def at_main(emu):
        seen['bytes'] = emu.mem.read(lo, hi - lo)
        raise Reached()
    e.hook(MAIN, at_main)
    try:
        e.call(ENTRY, max_steps=5000000)
        raise AssertionError('the entry returned before main')
    except Reached:
        pass
    assert kernel == [0x3C, 0x3D], kernel
    assert seen['bytes'] == bytes(hi - lo), 'a list byte survived the entry'
    inside = {pc for pc, a, _size, _value in e.writes if lo <= a < hi}
    assert inside == {BSS_STORE}, sorted(inside)
    span = [a for pc, a, _size, _value in e.writes if pc == BSS_STORE]
    assert min(span) == BSS[0] and max(span) + 16 == BSS[1], (hex(min(span)), hex(max(span)))
    assert all(size == 16 for pc, _a, size, _v in e.writes if pc == BSS_STORE)
    print('PASS boot entry 0x%x: lists and scan window 0x%x..0x%x (%d sentinel bytes) are 0 at main 0x%x; '
          'only writer the 16-byte store at 0x%x over 0x%x..0x%x (kernel calls 0x3c, 0x3d answered 0)' % (
              ENTRY, lo, hi, hi - lo, MAIN, BSS_STORE, BSS[0], BSS[1]), flush=True)
    cases = 1
    # main's first call is the run-once walker; on the zeroed lists it runs the stock constructor.
    e = EE(path)
    e.mem.auto_map = True
    e.follow = set()
    try:
        e.call(MAIN, max_steps=3000)
    except Exception:            # every callee is stubbed; main runs on into its loop
        pass
    assert (e.calls[0].target, e.calls[0].site) == (WALKER, WALK_SITE), e.calls[:1]
    e = EE(path)
    e.mem.auto_map = True
    e.follow = {STOCK_CTOR, ITEM_ARRAY_CTOR}
    e.mem.write(LISTS[0], bytes(LISTS[1] - LISTS[0]))
    e.call(WALKER, max_steps=20000000)
    walked = [c for c in e.calls if c.target == STOCK_CTOR]
    assert len(walked) == 1 and walked[0].site == 0x3AD2E4, walked
    ctors = len(e.calls)
    pattern = constructed()
    for category in range(3):
        base = LISTS[0] + category * S.LIST_STRIDE
        assert all(e.mem.read(base + n * S.ITEM_SIZE, S.ITEM_SIZE) == pattern for n in range(64)), category
        assert e.mem.read(base + 0x1200, 8) == bytes(8), 'count'
    e.reset_log()
    e.call(WALKER, max_steps=20000000)
    assert not e.calls, 'the walker runs once'
    cases += 3
    # The stock constructor alone on sentinel lists: which record bytes it writes.
    e = EE(path)
    e.mem.auto_map = True
    e.mem.write(LISTS[0], b'\xa5' * (LISTS[1] - LISTS[0]))
    e.call(STOCK_CTOR, max_steps=5000000)
    array = [c for c in e.calls if c.target == ITEM_ARRAY_CTOR]
    assert len(array) == 1 and tuple(x & 0xFFFFFFFF for x in array[0].args[:2]) == (1, 0xFFFF), array
    written = set()
    pcs = set()
    for pc, address, size, _value in e.writes:
        if LISTS[0] <= address < LISTS[1]:
            inner = (address - LISTS[0]) % S.LIST_STRIDE
            assert inner < 0x1200, 'the constructor wrote a count'
            pcs.add(pc)
            written.update((inner % S.ITEM_SIZE) + k for k in range(size))
    want = set(range(0x10, 0x22)) | {0x24 + 8 * code + k for code in range(4) for k in range(2)}
    assert pcs == CTOR_STORES and written == want, (sorted(hex(p) for p in pcs), sorted(written))
    for category in range(3):
        base = LISTS[0] + category * S.LIST_STRIDE
        for n in range(64):
            raw = e.mem.read(base + n * S.ITEM_SIZE, S.ITEM_SIZE)
            assert all(raw[k] == 0xA5 for k in range(S.ITEM_SIZE) if k not in want), (category, n)
    cases += 1
    print('PASS boot main@0x%x first calls walker 0x%x (%d constructors, once); constructor 0x%x -> 0x%x(1, 0xffff) '
          'writes +0x10..+0x21 and the four codes of all 192 records (stores %s), not +0x00..+0x0f, +0x22, '
          'the slot values, +0x44 or the counts; after boot every record is the constructed pattern, counts 0' % (
              MAIN, WALKER, ctors, STOCK_CTOR, ITEM_ARRAY_CTOR, ','.join('0x%x' % p for p in sorted(pcs))), flush=True)
    return cases


def function_starts(elf, words):
    """jal targets and post-return prologues, as difftest_vendor_close.formed_refs uses."""
    text = elf.text[0]
    starts = set()
    for index, word in enumerate(words):
        if word >> 26 == 3:
            dest = ((text + index * 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
            if elf.in_text(dest):
                starts.add(dest)
    for index in range(len(words) - 2):
        if words[index] != 0x03E00008:
            continue
        follow = index + 2
        while follow < len(words) and words[follow] == 0:
            follow += 1
        if follow < len(words) and (words[follow] & 0xFFFF8000) == 0x27BD8000:
            starts.add(text + follow * 4)
    return sorted(starts)


def list_census(elf):
    """{pc: containing start} of every addiu/daddiu or load/store whose lui-paired base lands
    in the lists. The high half resets at every function start."""
    text, off, size = elf.text
    words = struct.unpack_from('<%dI' % (size // 4), elf.d, off)
    starts = function_starts(elf, words)
    begins = set(starts)
    memory_ops = set(range(0x1A, 0x40)) - {0x1C, 0x1D}
    hits, high = {}, {}
    for index, word in enumerate(words):
        pc = text + index * 4
        if pc in begins:
            high = {}
        op, rs, rt = word >> 26, (word >> 21) & 31, (word >> 16) & 31
        simm = (word & 0xFFFF) - 0x10000 if word & 0x8000 else word & 0xFFFF
        if op == 0x0F:
            high[rt] = (word & 0xFFFF) << 16
            continue
        if rs in high and (op in (0x09, 0x19) or op in memory_ops):
            value = (high[rs] + simm) & 0xFFFFFFFF
            if LISTS[0] <= value < LISTS[1]:
                hits[pc] = starts[bisect.bisect_right(starts, pc) - 1]
            if op in (0x09, 0x19) and rt == rs:
                high.pop(rs, None)
    return hits


def data_pointers(elf, lo, hi):
    found = []
    for name in ('.data', '.rodata', '.sdata', '.ctors', '.dtors'):
        if name not in elf.sections:
            continue
        address, offset, size = elf.sections[name]
        for index in range(0, size - 3, 4):
            value, = struct.unpack_from('<I', elf.d, offset + index)
            if lo <= value < hi:
                found.append((name, address + index))
    return found


def census_cases(path):
    elf = Elf(path)
    hits = list_census(elf)
    sites = set(hits)
    assert hits == CENSUS, sorted((hex(pc), hex(f)) for pc, f in hits.items())
    assert data_pointers(elf, *LISTS) == [], 'a data word points into the lists'
    cases = 2
    # 0x1d10b0 is called only from the static constructor and destructor of the lists:
    # 0x1d1988 is a .ctors entry and 0x1d19a8 a .dtors entry, and nothing else names them.
    flow = control_sites(elf, [ITEM_ARRAY_CTOR, 0x1C8A00, STOCK_CTOR, 0x1D19A8])
    assert flow[ITEM_ARRAY_CTOR] == ((), (0x1D1994, 0x1D19B4)), flow[ITEM_ARRAY_CTOR]
    assert flow[0x1C8A00] == ((), (0x1D1474, 0x1D14B4)), flow[0x1C8A00]
    refs = formed_refs(elf, [STOCK_CTOR, 0x1D19A8])
    for function, table in ((STOCK_CTOR, '.ctors'), (0x1D19A8, '.dtors')):
        assert flow[function] == ((), ()) and not refs[function], hex(function)
        pointers = data_pointers(elf, function, function + 1)
        assert [name for name, _address in pointers] == [table], (hex(function), pointers)
    cases += 3
    # The stock grid build itemGrid_build(slot, panel, 1) stamps +0x22 of every populated
    # record (n < count) of all three lists with n, at 0x1cbd78, and writes nothing else
    # there; the bag grid and a buy over a stock cell write no list byte. Shop rig of
    # difftest_vendor_progress (stubs named there).
    import difftest_vendor_progress as P
    for seed in SEEDS:
        for counts in ((3, 3, 3), (5, 0, 2), (64, 17, 9)):
            shop = P.Shop(path, seed)
            m = shop.m
            for category in range(3):
                base = LISTS[0] + category * S.LIST_STRIDE
                for n in range(64):
                    if n < counts[category]:
                        m.w32(base + n * S.ITEM_SIZE, shop.definition)
                        m.w16(base + n * S.ITEM_SIZE + 4, 1)
                    m.w16(base + n * S.ITEM_SIZE + 0x22, 0x7777)
                m.w32(base + 0x1200, counts[category])
            shop.tick()
            shop.tick(press=shop.confirm)
            before = m.read(LISTS[0], LISTS[1] - LISTS[0])
            shop.e.reset_log()
            shop.build(0, 0, 1)
            stamps = {pc for pc, a, _s, _v in shop.e.writes if LISTS[0] <= a < LISTS[1]}
            assert stamps == {0x1CBD78}, sorted(hex(pc) for pc in stamps)
            after = m.read(LISTS[0], LISTS[1] - LISTS[0])
            for category in range(3):
                for n in range(64):
                    at = category * S.LIST_STRIDE + n * S.ITEM_SIZE
                    want = struct.pack('<H', n) if n < counts[category] else b'\x77\x77'
                    assert after[at + 0x22:at + 0x24] == want, (counts, category, n)
            changed = {k for k in range(len(after)) if after[k] != before[k]}
            assert all((k % S.LIST_STRIDE) % S.ITEM_SIZE in (0x22, 0x23) for k in changed)
            shop.e.reset_log()
            shop.build(0, 0, 0)
            writes = list(shop.e.writes)
            shop.build(0, 0, 1)
            shop.m.wf32(S.PANELS + 0x44, 48.0)
            shop.m.wf32(S.PANELS + 0x48, 96.0)
            calls = shop.tick(press=0x80)
            writes += shop.e.writes
            assert P.SEND_BUY in shop.targets(calls), 'the buy reached the sender'
            assert not [w for w in writes if LISTS[0] <= w[1] < LISTS[1]], 'bag grid or buy wrote the stock'
            cases += 1
        # The tick on which resources become ready (0x17306c: 0 at 0x1c6088, 1 at 0x1c60a0)
        # jumps to itemGrid_build(0, 0, 1) at 0x1c6110, which stamps the lists.
        shop = P.Shop(path, seed)
        m = shop.m
        for category in range(3):
            base = LISTS[0] + category * S.LIST_STRIDE
            for n in range(4):
                m.w32(base + n * S.ITEM_SIZE, shop.definition)
                m.w16(base + n * S.ITEM_SIZE + 0x22, 0x7777)
            m.w32(base + 0x1200, 3)
        ready = [0, 1]
        shop.e.stub(0x17306C, function=lambda emu: ready.pop(0) if ready else 1)
        entries = []
        shop.e.hook(P.GRID, lambda emu: entries.append((emu.cur, tuple(emu.r[k] & 0xFFFFFFFF for k in (4, 5, 6)))))
        shop.e.follow = set(shop.e.follow) | {P.GRID}
        shop.tick()
        ready_sites = [c.site for c in shop.e.calls if c.target == 0x17306C]
        assert ready_sites == [0x1C6088, 0x1C60A0] and entries == [(0x1C6114, (0, 0, 1))], (ready_sites, entries)
        assert all(m.u16(LISTS[0] + c * S.LIST_STRIDE + n * S.ITEM_SIZE + 0x22) == (n if n < 3 else 0x7777)
                   for c in range(3) for n in range(4))
        cases += 1
    # shop_buy with inventory_giveItem live: the stock record is read, not written; the
    # bag cell gets the copy and the +0x22 stamp at 0x1c1c64.
    for seed in SEEDS:
        o = Original(path, fast=True)
        e, m = o.emu, o.mem
        o.set_game(I.Game(), seed)
        m.write(LISTS[0], b'\xa5' * (LISTS[1] - LISTS[0]))
        definition, name = e.alloc(0x80), e.alloc(0x40)
        raw = bytearray(0x40)
        struct.pack_into('<Ii', raw, 0, name, 0)
        struct.pack_into('<i', raw, 0x14, 50)
        raw[0x1D] = 2
        m.write(definition, bytes(raw))
        m.write(name, b'plain\0')
        record = S.STOCK + 2 * S.LIST_STRIDE + 5 * S.ITEM_SIZE    # the third list
        m.w32(record, definition)
        m.w16(record + 4, 1)
        m.w64(record + 8, 0)
        m.w32(S.PLAYERS + S.PLAYER_GOLD, 1000)
        e.stub(VALUE, ret=100)
        e.record_writes = e.record_calls = True
        e.reset_log()
        o.call(SHOP_BUY, 0, record, max_steps=2000000)
        assert any(c.target == GIVE for c in e.calls) and m.s32(S.PLAYERS + S.PLAYER_GOLD) == 941
        assert not [w for w in e.writes if LISTS[0] <= w[1] < LISTS[1]], 'the buy wrote the stock'
        cell = S.PLAYERS + 0x2540
        assert any(pc == 0x1C1C64 and a == cell + 0x22 for pc, a, _s, _v in e.writes)
        assert m.read(cell, 4) == m.read(record, 4)
        cases += 1
    print('PASS census %d sites form list addresses, in %s; no data pointer; 0x1d10b0 only from the '
          '.ctors entry 0x1d1988 and the .dtors entry 0x1d19a8; 0x1c8a00 only from 0x1d1474/0x1d14b4; '
          'stock grid build stamps +0x22 = index (0x1cbd78) for n < count in all three lists, reached by '
          'shop_task at 0x1c6110 on the resource-ready tick; bag grid, menu buy and shop_buy+giveItem '
          'write no list byte' % (
              len(sites), ','.join('0x%x' % f for f in sorted(set(CENSUS.values())))), flush=True)
    return cases


def compare_cases(path):
    """0x108924(list entry, candidate): which bytes decide it."""
    e = EE(path)
    e.follow = set()
    a, b = e.alloc(0x48), e.alloc(0x48)
    base = bytearray(range(0x10, 0x58))
    struct.pack_into('<I', base, 0, 0x10000)
    cases = 0
    for offset in range(0x48):
        other = bytearray(base)
        other[offset] ^= 0x5A
        e.mem.write(a, bytes(base))
        e.mem.write(b, bytes(other))
        got = e.call(SAME, a, b) & 0xFFFFFFFF
        decides = offset < 4 or 8 <= offset < 0x10 or 0x20 <= offset < 0x24
        assert got == int(not decides) == int(S.same_raw(bytes(base), bytes(other))), hex(offset)
        cases += 1
    e.mem.write(a, bytes(base))
    e.mem.write(b, bytes(base))
    assert e.call(SAME, a, b) & 0xFFFFFFFF == 1
    print('PASS compare 0x%x reads +0x00..+0x03, +0x08..+0x0f and +0x20..+0x23 only (72 single-byte '
          'flips): +0x22/+0x23 decide; +0x06, +0x44..+0x47 and the slot values do not' % SAME, flush=True)
    return cases + 1


def stock_pass(path, seed, level, difficulty, stack_fill, slot_fill):
    """A real mode-1 pass: every item function live; vars and resource stubbed (named)."""
    o = Original(path, fast=True)
    e, m = o.emu, o.mem
    o.set_game(I.Game(num_players=1, difficulty=difficulty), seed)
    for slot in range(4):
        m.w8(S.PLAYERS + slot * S.PLAYER_STRIDE + 0x58, 1)
    m.w32(S.COSMETIC, seed)
    m.write(o.sp - 0x8000, bytes([stack_fill]) * 0x8000)
    m.write(LISTS[0], bytes([slot_fill]) * (LISTS[1] - LISTS[0]))
    e.stub(VARS, ret=level)            # storeLevel read
    e.stub(RESOURCE, ret=0)            # resource request
    events = []

    def enter(machine):
        if machine.r[31] in RETURNS:
            entry, candidate = machine.r[4] & 0xFFFFFFFF, machine.r[5] & 0xFFFFFFFF
            events.append([RETURNS[machine.r[31]], entry, candidate,
                           m.read(entry, 0x48), m.read(candidate, 0x48), None])

    def leave(machine):
        events[-1][5] = machine.r[2] & 0xFFFFFFFF
    e.hook(SAME, enter)
    for address in RETURNS:
        e.hook(address, leave)
    e.record_writes = True
    o.call(STOCK_FN, 0, 1, 1, max_steps=800000000)
    stores = set()
    for pc, address, size, _value in e.writes:
        if LISTS[0] <= address < LISTS[1]:
            inner = (address - LISTS[0]) % S.LIST_STRIDE
            if inner < 0x1200 and inner % 0x48 <= 0x22 < inner % 0x48 + size:
                stores.add(pc)
    counts = tuple(m.u32(LISTS[0] + c * S.LIST_STRIDE + 0x1200) for c in range(3))
    return events, stores, counts, m.u32(S.SHARED)


def boot_state_passes(path, seed, stack_fill):
    """Zeroed lists, the stock constructor, then two mode-1 passes in a row on one machine."""
    o = Original(path, fast=True)
    e, m = o.emu, o.mem
    m.write(LISTS[0], bytes(LISTS[1] - LISTS[0]))
    e.call(STOCK_CTOR, max_steps=5000000)
    level, difficulty = BOOT_CONTEXT
    o.set_game(I.Game(num_players=1, difficulty=difficulty), seed)
    for slot in range(4):
        m.w8(S.PLAYERS + slot * S.PLAYER_STRIDE + 0x58, 1)
    m.w32(S.COSMETIC, seed)
    m.write(o.sp - 0x8000, bytes([stack_fill]) * 0x8000)
    e.stub(VARS, ret=level)            # storeLevel read
    e.stub(RESOURCE, ret=0)            # resource request
    events = []

    def enter(machine):
        if machine.r[31] in RETURNS:
            entry, candidate = machine.r[4] & 0xFFFFFFFF, machine.r[5] & 0xFFFFFFFF
            events.append([RETURNS[machine.r[31]], entry, candidate,
                           m.read(entry, 0x48), m.read(candidate, 0x48), None])

    def leave(machine):
        events[-1][5] = machine.r[2] & 0xFFFFFFFF
    e.hook(SAME, enter)
    for address in RETURNS:
        e.hook(address, leave)
    passes = []
    for _ in range(2):
        del events[:]
        o.call(STOCK_FN, 0, 1, 1, max_steps=800000000)
        passes.append((list(events), m.read(LISTS[0] + 2 * S.LIST_STRIDE, S.LIST_STRIDE)))
    return passes


_TABLES = {}


def definition_category(path, definition):
    """Category byte +0x1d of a definition in the executable's static table."""
    exe = _TABLES.setdefault(path, I.Exe(path))
    return exe.u8(definition + 0x1D)


def residue_cases(path):
    cases = 0
    fixed = {S.STOCK + n * S.ITEM_SIZE for n in range(4)}
    totals = {}
    for (level, difficulty), seed in [(c, s) for c in CONTEXTS for s in SEEDS]:
        runs = [stock_pass(path, seed, level, difficulty, *fill) for fill in FILLS]
        (ea, sa, ca, ra), (eb, sb, cb, rb), (ec, sc, cc, rc) = runs
        assert ca == cb == cc and ra == rb == rc, 'a sentinel changed the pass'
        assert [x[:3] + [x[5]] for x in ea] == [x[:3] + [x[5]] for x in eb] == [x[:3] + [x[5]] for x in ec]
        assert sa | sb | sc <= SLOT_STORES, sorted(hex(pc) for pc in sa | sb | sc)
        for xa, xb, xc in zip(ea, eb, ec):
            category, entry = xa[0], xa[1]
            for side in (3, 4):
                va, vb, vc = (x[side][0x22:0x24] for x in (xa, xb, xc))
                if side == 4:
                    kind = 'candidate'
                    assert va == vb == vc, 'candidate +0x22 depends on a sentinel'
                elif category == 0 and entry in fixed:
                    kind = 'fixed'
                    assert (va, vb, vc) == (b'\x5c\x5c', b'\x3d\x3d', b'\x5c\x5c'), (va, vb, vc)
                elif category == 0:
                    kind = 'accepted'
                    assert va == vb == vc
                elif category == 1:
                    kind = 'old-third'
                    assert (va, vb, vc) == (b'\xa5\xa5', b'\xa5\xa5', b'\x96\x96'), (va, vb, vc)
                else:
                    kind = 'name-window'
                    assert va == vb == vc
                totals[kind] = totals.get(kind, 0) + 1
            a, b = xa[3], xa[4]
            fields = b[:4] != bytes(4) and a[:4] == b[:4] and a[8:16] == b[8:16] and a[0x20:0x22] == b[0x20:0x22]
            key = 'fields-equal' if fields else 'fields-differ'
            totals[key] = totals.get(key, 0) + 1
            totals['matched'] = totals.get('matched', 0) + int(xa[5] == 1)
        cases += 1
        print('PASS residue storeLevel=%d difficulty=%d seed=%d counts=%s compares=%d slot+0x22 stores=%s' % (
            level, difficulty, seed, ','.join(map(str, ca)), len(ea),
            ','.join('0x%x' % pc for pc in sorted(sa))), flush=True)
    # Boot state: the first pass scans the constructed third list, the second the first's.
    pattern = constructed()
    second = {'stack': 0, 'pass': 0, 'matched': 0}
    for seed in SEEDS:
        (first_a, third_a), (second_a, _) = boot_state_passes(path, seed, 0x5C)
        (first_b, third_b), (second_b, _) = boot_state_passes(path, seed, 0x3D)
        for xa, xb in zip(first_a, first_b):
            if xa[0] == 1:
                assert xa[3] == xb[3] == pattern and xa[5] == 0, 'first pass: constructed old record'
        assert [x[:3] + [x[5]] for x in first_a] == [x[:3] + [x[5]] for x in first_b]
        assert [x[:3] + [x[5]] for x in second_a] == [x[:3] + [x[5]] for x in second_b]
        old = [(xa, xb) for xa, xb in zip(second_a, second_b) if xa[0] == 1]
        assert old and all(xa[3] == third_a[xa[1] - S.STOCK - 2 * S.LIST_STRIDE:][:S.ITEM_SIZE] for xa, _ in old)
        for xa, xb in old:
            second['stack' if xa[3][0x22:0x24] != xb[3][0x22:0x24] else 'pass'] += 1
            second['matched'] += int(xa[5] == 1)
            entry_def, candidate_def = (struct.unpack_from('<I', raw)[0] for raw in (xa[3], xa[4]))
            if entry_def:
                classes = [definition_category(path, d) for d in (entry_def, candidate_def)]
                assert classes[0] != classes[1], 'an old third-list definition shares the armour category'
                second['other'] = second.get('other', 0) + 1
        cases += 2
        print('PASS residue boot state seed=%d storeLevel=%d difficulty=%d: pass 1 scans %d constructed '
              'third-list records (definition 0, +0x22 0, no match); pass 2 scans pass 1\'s third list' % (
                  seed, BOOT_CONTEXT[0], BOOT_CONTEXT[1], len([x for x in first_a if x[0] == 1])), flush=True)
    print('PASS residue pass-2 old third list +0x22: %(stack)d from the stack before pass 1, %(pass)d '
          'pass-internal; matched %(matched)d; %(other)d non-null entries all of another definition category '
          'than the armour candidate' % dict({'other': 0}, **second), flush=True)
    print('PASS residue +0x22 at the compare: candidate %(candidate)d (pass-internal), accepted %(accepted)d '
          '(pass-internal), fixed %(fixed)d (pre-pass stack), old third list %(old-third)d (previous '
          'occupant), name window %(name-window)d; fields-equal %(fields-equal)d, matched %(matched)d' % dict(
              {'candidate': 0, 'accepted': 0, 'fixed': 0, 'old-third': 0, 'name-window': 0,
               'fields-equal': 0, 'matched': 0}, **totals), flush=True)
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--only', choices=('boot', 'census', 'compare', 'residue'))
    args = parser.parse_args()
    assert sha(args.elf) == EXPECTED_SHA256, 'executable digest'
    groups = (('boot', boot_cases), ('census', census_cases), ('compare', compare_cases),
              ('residue', residue_cases))
    total = 0
    for name, run in groups:
        if args.only and name != args.only:
            continue
        count = run(args.elf)
        total += count
        print('PASS %s cases=%d' % (name, count), flush=True)
    print('PASS total=%d mismatches=0' % total)


if __name__ == '__main__':
    main()
