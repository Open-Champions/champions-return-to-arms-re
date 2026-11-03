#!/usr/bin/env python3
"""Close the vendor gates a client still needs: prices, gold restock, residue, storeLevel.

Original functions run in tools/ee_emu.py. Output is counts and addresses only.
Pass the private executable and --disc DIR (the extracted disc, read-only).
Seeds 20973 and 7 are both applied wherever a function reads the shared generator
or the caller asked for both. Price arithmetic does not draw a seed; those cases
still run twice and require the seed word to stay put.
"""
import argparse
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != HERE] + [HERE]
import unittest  # tools/dis.py must not shadow stdlib dis.
from difftest_items import Original, EXPECTED_SHA256, _cstr
from ee_emu import EE, s32
from gob import gob_entries, lmp_entries
from ps2elf import Elf
from scr import parse, strings
import ref_amx
import ref_items as I
import ref_vendor_stock as S

SEEDS = (20973, 7)
PLAYERS = 0x4D8AF0
GOLD = PLAYERS + 0xE4
GIVE, DROP, VALUE, APPEND, GENERATE = 0x1C1868, 0x1C4310, 0x1024A8, 0x107D54, 0x104CA4
BUY, SELL_MSG, PARSE = 0x1D1240, 0x1C5D28, 0x1069B8
QUEUE = 0x1ED52C
FLIP, QUEUED = 0x4F8690, 0x86DA7C
VAR_GET, VAR_NAME = 0x1ED778, 0x538750
STORE_LEVEL = b'storelevel'
FIXED = (0x538760, 0x5388E8)


def sha(path):
    with open(path, 'rb') as source:
        return hashlib.sha256(source.read()).hexdigest()


def form_sites(elf, hi, simm):
    """PCs of addiu whose source register was loaded with hi in the previous 64 words."""
    base, _, size = elf.text
    words = [elf.u32(base + offset) for offset in range(0, size, 4)]
    found = []
    for index, word in enumerate(words):
        if word >> 26 != 9:
            continue
        imm = word & 0xFFFF
        if imm >= 0x8000:
            imm -= 0x10000
        if imm != simm:
            continue
        rs = (word >> 21) & 31
        for older in range(max(0, index - 64), index):
            prev = words[older]
            if prev >> 26 == 0x0F and (prev >> 16) & 31 == rs and (prev & 0xFFFF) == hi:
                found.append(base + 4 * index)
                break
    return tuple(found)


def jal_sites(elf, target):
    base, _, size = elf.text
    sites = []
    for pc in range(base, base + size, 4):
        word = elf.u32(pc)
        dest = ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        if dest == target and word >> 26 == 3:
            sites.append(pc)
    return tuple(sites)


def price_cases(path):
    """shop_buy and the sell arm of shop_onMsg, both seeds, stubbed and real values."""
    tables = I.Tables(path)
    stem = tables.thrown_stem
    del tables
    cases = 0
    for seed in SEEDS:
        o = Original(path, fast=True)
        e, m = o.emu, o.mem
        o.set_game(I.Game(), seed)
        m.w32(S.SHARED, seed)
        definition = o.emu.alloc(0x80)
        name = o.emu.alloc(0x40)
        record = o.rec
        message = o.emu.alloc(0x20)
        gives, drops = [], []
        e.stub(GIVE, function=lambda machine: gives.append(machine.r[4] & 0xFFFFFFFF) or 0)
        e.stub(DROP, function=lambda machine: drops.append(1) or 0)

        def plant(category, slot, record_flags, def_flags, text, count, value, gold, stub_value):
            raw = bytearray(0x40)
            struct.pack_into('<I', raw, 0, name)
            struct.pack_into('<i', raw, 0x14, 50)
            raw[0x1C] = slot & 0xFF
            raw[0x1D] = category & 0xFF
            struct.pack_into('<Q', raw, 0x28, def_flags)
            m.write(definition, bytes(raw))
            m.write(name, text + b'\0')
            item = bytearray(0x48)
            struct.pack_into('<Ih', item, 0, definition, I.s16(count))
            struct.pack_into('<Q', item, 8, record_flags)
            m.write(record, bytes(item))
            m.w32(GOLD, gold & 0xFFFFFFFF)
            if stub_value:
                e.stub(VALUE, ret=value & 0xFFFFFFFF)
            else:
                e.unhook(VALUE)
            return value if stub_value else I.s32(50 * I.s16(count))

        # Controlled value isolates the factor. Real value uses the copied definition's price.
        matrix = []
        for category, slot, flags, text, count, value, gold in (
                (0, 0, 0, b'plain', 1, 100, 1000),
                (1, 0, 0, b'plain', 1, 100, 1000),
                (2, 0, 0, b'plain', 1, 100, 10),          # short gold
                (0, 0, S.BUY_FULL_FLAGS, b'plain', 1, 100, 100),
                (0, 8, 0, b'plain', 1, 100, 100),
                (0, 0, 0, b'plain', 1, -100, 0),
                (0, 0, 0, stem + b'-x', 1, 100, 0),
                (0, 0, S.SELL_STACK_FLAGS, b'plain', 4, 80, 10),
                (0, 8, 0, b'plain', 1, 100, 10),
                (0, 0, S.SELL_ZERO_FLAGS, b'plain', 1, 100, 10),
                (0, 0, 0, b'plain', 1, 100, S.GOLD_CAP - 1),
                (0, 0, 0, b'plain', 0, 100, 10),
                (2, 0, 0, b'plain', 1, 100, 1000)):
            matrix.append((category, slot, flags, text, count, value, gold))

        for category, slot, flags, text, count, value, gold in matrix:
            for stub_value in (True, False):
                if not stub_value and (flags or slot or category or count != 1 or value != 100):
                    continue
                gives.clear()
                drops.clear()
                m.w32(S.SHARED, seed)
                used = plant(category, slot, flags if category == 0 else 0, flags,
                             text, count, value, gold, stub_value)
                price = S.buy_price(used, category, flags if category == 0 else 0, slot)
                e.call(BUY, 0, record, max_steps=20000)
                want_gold, paid = S.buy_gold(gold, price)
                got_gold = s32(m.u32(GOLD))
                if got_gold != want_gold:
                    raise AssertionError('buy gold got=%s want=%s price=%s value=%s cat=%s slot=%s flags=%s gives=%s' % (
                        got_gold, want_gold, price, used, category, slot, flags, len(gives)))
                assert len(gives) == int(paid)
                assert m.u32(S.SHARED) == seed
                if paid:
                    assert gives[-1] == 0
                cases += 1

                # Sell the same record from bag 0 slot 0. Credit uses definition flags.
                gives.clear()
                bag = PLAYERS + 0x130
                m.write(bag, m.read(record, 0x48))
                m.w32(GOLD, gold & 0xFFFFFFFF)
                payload = bytes([1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1])
                m.write(message, payload)
                has_stem = stem in text
                credit = S.sell_credit(used, count, slot, has_stem, flags)
                e.call(SELL_MSG, message, max_steps=20000)
                assert s32(m.u32(GOLD)) == S.sell_gold(gold, credit), 'sell gold'
                assert len(drops) == 1 and not gives
                assert m.u32(S.SHARED) == seed
                cases += 1

        # Type 2 is ignored. Type 0 reaches shop_buy.
        m.w32(GOLD, 1000)
        m.write(message, bytes([2, 0, 0, 0, 0, 0, 0, 0]))
        e.call(SELL_MSG, message, max_steps=20000)
        assert m.u32(GOLD) == 1000
        gives.clear()
        plant(0, 0, 0, 0, b'plain', 1, 100, 1000, True)
        payload = bytes([0, 0, 0, 0]) + struct.pack('<I', record)
        m.write(message, payload)
        e.call(SELL_MSG, message, max_steps=20000)
        assert len(gives) == 1
        assert s32(m.u32(GOLD)) == S.buy_gold(1000, S.buy_price(100, 0, 0, 0))[0]
        cases += 2
    return cases


def restock_cases(path):
    cases = 0
    sites = jal_sites(Elf(path), S.RESTOCK)
    assert sites == (0x1D1474, 0x1D14B4), 'restock callers'
    cases += 1
    for seed in SEEDS:
        for gold in (0, 1, 2, 100, 1600, -1, -3, 0x7FFFFFFF, -2147483648):
            o = Original(path, fast=True)
            e, m = o.emu, o.mem
            o.set_game(I.Game(num_players=1), seed)
            m.w32(S.SHARED, seed)
            m.w32(GOLD, gold & 0xFFFFFFFF)
            seen = []

            def record(machine):
                seen.append((machine.r[4] & 0xFFFFFFFF,
                             s32(machine.r[5]),
                             s32(machine.r[6]),
                             s32(machine.r[7])))
                return 0

            e.stub(APPEND, function=record)
            e.call(S.RESTOCK, max_steps=20000)
            want = [(base, budget, attempt, category)
                    for base, budget, attempt, category in S.restock_calls(gold)]
            assert seen == want, 'restock arguments'
            assert tuple(m.u32(base + 0x1200) for base in S.RESTOCK_LISTS) == S.RESTOCK_SEED_COUNTS
            assert m.u32(S.SHARED) == seed
            cases += 1
    # The append itself ignores its third argument and asks for level 1.
    for seed in SEEDS:
        for category in (0, 1):
            o = Original(path, fast=True)
            e, m = o.emu, o.mem
            game = I.Game(num_players=1)
            o.set_game(game, seed)
            levels = []

            def level(machine):
                levels.append((s32(machine.r[5]), s32(machine.r[6]), s32(machine.r[7]),
                               s32(machine.r[8])))
                return 0

            e.stub(GENERATE, function=level)
            m.w32(S.STOCK + 0x1200, 0)
            e.call(APPEND, S.STOCK, 40, 99, category, max_steps=20000)
            assert levels and all(row[2] == -1 and row[3] == 1 and row[1] == category for row in levels)
            assert len(levels) <= 2
            cases += 1
    return cases


def _filled_call(path, seed, fill, call):
    o = Original(path, fast=True)
    o.set_game(I.Game(num_players=1), seed)
    o.mem.write(o.rec, bytes([fill]) * S.ITEM_SIZE)
    call(o)
    return o.mem.read(o.rec, S.ITEM_SIZE), o.seed()


def residue_cases(path):
    """Parser and affix outputs do not keep the previous destination bytes."""
    tables = I.Tables(path)
    cases = 0
    for seed in SEEDS:
        for descriptor in FIXED:
            rng = I.Rng(seed)
            item = I.parse_descriptor(tables, _cstr(Original(path, fast=True).mem, descriptor), -1, False, rng)
            blank = item.pack(bytes(S.ITEM_SIZE))
            outputs = []
            for fill in (0x00, 0xA5):
                def run(o, descriptor=descriptor, seed=seed):
                    o.mem.w32(S.SHARED, seed)
                    o.call(PARSE, descriptor, o.rec, -1 & 0xFFFFFFFFFFFFFFFF, 0)
                raw, got_seed = _filled_call(path, seed, fill, run)
                assert raw == blank, 'parser depends on the old destination'
                assert got_seed == rng.seed
                outputs.append(raw)
                cases += 1
            assert outputs[0] == outputs[1]
    return cases


def name_cases(path, disc):
    """Deferred names are the only bytes stored at the category-2 scan, and they do not identify items."""
    tables = I.Tables(path)
    defs = set(tables.by_addr)
    elf = Elf(path)
    assert form_sites(elf, 0x0087, -0x4D88) == (0x1ED584, 0x1ED5EC)
    assert form_sites(elf, 0x0054, -0x78B0) == (0x1C7B0C, 0x1C7BC4)
    windows = 0
    hits = 0
    scripts = 0
    other = 0
    literals = []
    archives = []
    dynamic = 0
    gets = 0
    adds = 0
    for dirpath, _dirs, files in os.walk(disc):
        for filename in files:
            if not filename.upper().endswith('.GOB'):
                continue
            data = open(os.path.join(dirpath, filename), 'rb').read()
            try:
                lumps = gob_entries(data)
            except (OSError, ValueError, IndexError, struct.error):
                continue
            for _lname, loff, lsize in lumps:
                if loff < 0 or lsize < 0 or loff + lsize > len(data):
                    continue
                lump = data[loff:loff + lsize]
                try:
                    entries = lmp_entries(lump)
                except (OSError, ValueError, IndexError, struct.error):
                    continue
                for fname, foff, fsize in entries:
                    if foff < 0 or fsize < 0 or foff + fsize > len(lump):
                        continue
                    blob = lump[foff:foff + fsize]
                    if fname != 'script.scr':
                        swapped = b''.join(blob[i:i + 4][::-1] for i in range(0, len(blob) - 3, 4))
                        if STORE_LEVEL in blob.lower() or STORE_LEVEL in swapped.lower():
                            other += 1
                        continue
                    image_hits, image_lits, image_dyn, image_gets, image_adds = _script_level(blob)
                    scripts += 1
                    hits += image_hits
                    literals.extend(image_lits)
                    if image_lits or image_gets or image_dyn or image_adds:
                        archives.append((os.path.splitext(filename)[0].lower(), tuple(image_lits), image_dyn))
                    dynamic += image_dyn
                    gets += image_gets
                    adds += image_adds
                    windows += _name_windows(blob, defs)
    print('PASS storeLevel progress hits=%d dynamic=%d gets=%d adds=%d other=%d literals=%s' % (
        hits, dynamic, gets, adds, other, literals), flush=True)
    print('PASS storeLevel archives=%s' % ' '.join(
        '%s:%s/dyn=%d' % (name, ','.join(str(v) for v in values) or '-', dyn)
        for name, values, dyn in archives), flush=True)
    assert archives == [
        ('hub2', (0, 8, 7, 6, 5, 7, 6), 1),
        ('stobonus', (7,), 0),
        ('hub', (0, 8, 7, 6, 5, 7, 6), 1),
        ('islgnome', (3,), 0),
    ]
    assert other == 0, 'storeLevel outside level scripts'
    assert literals == [0, 8, 7, 6, 5, 7, 6, 7, 0, 8, 7, 6, 5, 7, 6, 3]
    assert dynamic == 2 and gets == 0 and adds == 0
    # A queued name of every length that occurs still does not land on a definition.
    o = Original(path, fast=True)
    e, m = o.emu, o.mem
    m.w32(FLIP, 1)
    m.w32(QUEUED, 13)
    sample = o.emu.alloc(0x50)
    m.write(sample, b'entry-point-name-long')
    e.call(QUEUE, sample, max_steps=5000)
    word = m.u32(S.SCAN_BASE)
    assert word not in defs
    assert not S.same_raw(struct.pack('<I', next(iter(defs))) + bytes(0x44),
                          m.read(S.SCAN_BASE, S.ITEM_SIZE))
    # Missing variable: the stock prefix creates it at 0. Library calls stay stubbed.
    for seed in SEEDS:
        e = EE(path)
        e.follow = {0x3B8534, 0x3B868C, 0x3B8DC4, VAR_GET, 0x1ED854}
        e.mem.w32(S.SHARED, seed)
        e.mem.w8(0x86DA80, 0)
        e.mem.w32(0x4F719C, 1)
        e.r[4:7] = [0, 1, 1]
        assert e.run(0x1C7AF8, until=(0x1C7C34,), max_steps=20000) == 'stop'
        assert e.fget(23) == 1.0
        name = []
        while e.mem.u8(VAR_NAME + len(name)) != 0:
            byte = e.mem.u8(VAR_NAME + len(name))
            name.append(byte + 0x20 if 65 <= byte <= 90 else byte)
        for index, byte in enumerate(name):
            assert e.mem.u8(0x86DA80 + index) == byte
        assert e.mem.u8(0x86DA80 + len(name)) == 0
        assert e.mem.s8(0x86DA80 + len(name) + 1) == 0
        assert e.mem.u32(S.SHARED) == seed
    print('PASS name_windows=%d definition_hits=0 other_files=%d' % (windows, other), flush=True)
    return len(literals) + windows + 4


def _script_level(blob):
    """Return (name hits, literal set values, dynamic sets, gets, adds)."""
    parsed = parse(blob)
    pool = dict(strings(blob, *parsed['strings']))
    names = {off for off, text in pool.items() if text.lower() == 'storelevel'}
    machine = ref_amx.Machine(blob)
    if machine.load() != 0 or not names:
        return 0, [], 0, 0, 0
    ext = [machine.native_name(i).decode('latin1') for i in range(max(machine.num_natives, 0))]
    pending, hits, dyn, gets, adds, literals = [], 0, 0, 0, 0, []
    for start in sorted(machine._decoded):
        opcode, operand, _end = machine._decoded[start]
        if opcode == 0x7B:
            args = pending[:-1][::-1] if pending else []
            label = ext[operand] if isinstance(operand, int) and 0 <= operand < len(ext) else ''
            if args and args[0][0] == 'c' and args[0][1] in names:
                hits += 1
                if label == 'setv':
                    if len(args) > 1 and args[1][0] == 'c':
                        literals.append(int(args[1][1]))
                    else:
                        dyn += 1
                elif label == 'getv':
                    gets += 1
                elif label == 'addv':
                    adds += 1
            pending = []
        elif opcode == 0x27:
            pending.append(('c', operand))
        elif opcode == 0x28:
            pending.append(('var', operand))
        else:
            pending = []
    return hits, literals, dyn, gets, adds


def _name_windows(blob, defs):
    parsed = parse(blob)
    pool = dict(strings(blob, *parsed['strings']))
    checked = 0
    for _off, text in pool.items():
        raw = text.encode('latin1', 'replace') + b'\0'
        for start in range(len(raw) - 3):
            word = int.from_bytes(raw[start:start + 4], 'little')
            checked += 1
            assert word not in defs or word == 0
    for name, _value in ((n, v) for v, n in parsed['internals']):
        raw = name.encode('latin1', 'replace') + b'\0'
        for start in range(max(0, len(raw) - 3)):
            word = int.from_bytes(raw[start:start + 4], 'little')
            checked += 1
            assert word not in defs or word == 0
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--disc', required=True)
    args = parser.parse_args()
    assert sha(args.elf) == EXPECTED_SHA256, 'executable digest'
    total = 0
    for check in (price_cases, restock_cases, residue_cases):
        count = check(args.elf)
        total += count
        print('PASS %s cases=%d' % (check.__name__, count), flush=True)
    count = name_cases(args.elf, args.disc)
    total += count
    print('PASS total=%d mismatches=0' % total)


if __name__ == '__main__':
    main()
