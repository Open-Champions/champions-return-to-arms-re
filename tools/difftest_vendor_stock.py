#!/usr/bin/env python3
"""Count-only stock difftest; executable input must be privately supplied.

Default: bounded original orchestration with synthetic item services. --real
also executes every item generator/parser/value function for complete stock
passes. Fast C string hooks are inherited from difftest_items; --real does not
replace item functions, RNG, powf, comparison, or sorting. Every defined item
byte and shared seed is compared to unchanged ref_items. Undefined record bytes
are taken from executed outputs, never silently zeroed by the reference plan.
"""
import argparse
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != HERE] + [HERE]
import unittest  # tools/ is now behind the standard library.
from difftest_items import Original, EXPECTED_SHA256, _cstr
import ref_items as I
import ref_vendor_stock as S

F_STOCK, F_VARS, F_RESOURCE = 0x1c7af8, 0x1ed778, 0x173558
FUNCTIONS = {'parse': 0x1069b8, 'affix': 0x104ca4, 'preset': 0x104758}
RETURNS = {0x1c7cdc, 0x1c7d1c, 0x1c7d4c, 0x1c7d7c,
           0x1c827c, 0x1c82b0, 0x1c8300, 0x1c8334, 0x1c8370,
           0x1c7dec, 0x1c8034, 0x1c83f0, 0x1c7f78, 0x1c818c, 0x1c8564}


def synthetic_record(identity, suffix=0, flags=0, residue=0):
    raw = bytearray(0x48)
    struct.pack_into('<Ih', raw, 0, 0x10000 + identity * 0x40, 1)
    struct.pack_into('<Q', raw, 8, flags)
    struct.pack_into('<i', raw, 0x10, (identity % 7) * 13)
    raw[0x21] = suffix
    struct.pack_into('<H', raw, 0x22, residue)
    return bytes(raw)


def run_case(path, level, difficulty, seed, mode=1, real=False, classes=(0,0,0,0),
             players=1, second=None, adversarial=False, stack_fill=0,
             cosmetic=None, tables=None, player_level=1, monster_level=1.0):
    o = Original(path, fast=True)
    e, m = o.emu, o.mem
    game = I.Game(num_players=players, classes=classes, difficulty=difficulty,
                  level=monster_level)
    o.set_game(game, seed)
    for slot in range(4):
        m.w8(0x4d8af0 + slot * 0x4c30 + 0x58, player_level)
    cosmetic = seed if cosmetic is None else cosmetic
    m.w32(S.COSMETIC, cosmetic)
    m.write(o.sp - 0x8000, bytes([stack_fill]) * 0x8000)
    # Model comparison memory includes both old stock and the non-stock scan region.
    if adversarial:
        for base in (S.STOCK, S.STOCK + 2 * S.LIST_STRIDE,
                     S.STOCK + 4 * S.LIST_STRIDE):
            for n in range(32):
                m.write(base + n * S.ITEM_SIZE, synthetic_record(77))
    memory = bytearray(m.read(S.STOCK, 0x6000))
    contract = S.budget_contract(level, difficulty, second)
    plan = S.stock_plan(contract, cosmetic, memory, m.u32)
    expected = [next(plan)]
    pending = [None]
    comparisons = [0, 0]
    operations = [0, 0, 0]
    attempts = [0, 0, 0]
    variables = []
    resources = []
    generated = [0]
    predictions = [None]
    reference_rng = I.Rng(seed)
    destination_before = [None]

    def get_variable(machine):
        assert machine.r[4] == 0x538750, 'variable selector'
        variables.append(machine.r[31] - 8)
        return level if len(variables) == 1 or second is None else second

    e.stub(F_VARS, function=get_variable)
    e.stub(F_RESOURCE, function=lambda machine: resources.append(machine.r[4]) or 0)

    def enter(kind, machine):
        if machine.r[31] not in RETURNS:
            return False
        assert comparisons[0] == comparisons[1], 'duplicate scan count'
        request = expected[0]
        assert request is not None and request[0] == kind, 'dispatch kind'
        _, dest, args = request
        got_dest = machine.r[5] if kind == 'parse' else machine.r[4]
        got = ((machine.r[4], I.s32(machine.r[6]), I.s32(machine.r[7]))
               if kind == 'parse' else tuple(I.s32(x) for x in
                   machine.r[5:5 + len(args)]))
        assert got_dest == dest and got == args, 'dispatch arguments'
        operations[('parse','affix','preset').index(kind)] += 1
        pending[0] = request
        if real:
            destination_before[0] = m.read(dest, S.ITEM_SIZE)
            assert m.u32(S.SHARED) == reference_rng.seed, 'inter-call RNG mismatch'
            rng = reference_rng
            if kind == 'parse':
                item = I.parse_descriptor(tables, _cstr(m, args[0]), args[1], bool(args[2]), rng)
            elif kind == 'affix':
                item = I.generate_with_affixes(tables, game, rng, *args)
            else:
                item = I.generate_preset(tables, game, rng, *args)
            predictions[0] = (item, rng.seed)
        return True

    def synthetic(kind, machine):
        assert enter(kind, machine)
        _, dest, args = pending[0]
        generated[0] += 1
        raw = synthetic_record(generated[0])
        ok = 1
        if kind == 'affix':
            category = args[1]
            attempts[category] += 1
            n = attempts[category]
            if adversarial:
                if category == 0:
                    # Failed generation; forbidden flag; then six duplicate retries.
                    if n == 1:
                        ok = 0
                    elif n == 2:
                        raw = synthetic_record(31, flags=1 << 40)
                    elif n <= 9:
                        raw = m.read(S.STOCK, S.ITEM_SIZE)
                elif category == 1 and n <= 8:
                    raw = synthetic_record(77)
                elif category == 2:
                    raw = synthetic_record(77) if n <= 2 else raw
                    if n == 3:
                        ok = 0
                    if n == 4:
                        raw = synthetic_record(80, suffix=0xff)
        if kind == 'preset' and adversarial:
            # Prove stock uses the record pointer, not generator return value.
            ok = 0
            if args[1] == 1:
                raw = bytes(S.ITEM_SIZE)
                ok = 1
        m.write(dest, raw)
        return ok

    def returned(machine):
        request = pending[0]
        assert request is not None, 'unmatched generator return'
        kind, dest, args = request
        raw = m.read(dest, S.ITEM_SIZE)
        ok = machine.r[2] & 0xffffffff
        if real:
            item, next_seed = predictions[0]
            assert m.u32(S.SHARED) == next_seed, 'item RNG mismatch'
            if kind != 'parse':
                assert ok == int(item is not None), 'item return mismatch'
            if item is not None:
                assert item.pack(raw) == raw, 'defined item bytes mismatch'
            else:
                assert raw == destination_before[0], 'failed generator modified destination'
        comparisons[:] = [0, 0]
        if kind == 'affix' and ok:
            category = args[1]
            comparisons[1] = (dest - S.STOCK - category * S.LIST_STRIDE) // S.ITEM_SIZE
        try:
            expected[0] = plan.send((ok, raw))
        except StopIteration:
            expected[0] = None

    def compare_enter(machine):
        if machine.r[31] not in (0x1c7e30,0x1c8078,0x1c8430):
            return
        kind, dest, args = pending[0]
        category = args[1]
        want = S.STOCK + 2 * category * S.LIST_STRIDE + comparisons[0] * S.ITEM_SIZE
        assert machine.r[4] == want and machine.r[5] == dest, 'duplicate scan address'
        comparisons[0] += 1

    for kind, address in FUNCTIONS.items():
        if real:
            e.hook(address, lambda machine, kind=kind: enter(kind, machine))
        else:
            e.stub(address, function=lambda machine, kind=kind: synthetic(kind, machine))
    for address in RETURNS:
        e.hook(address, returned)
    e.hook(0x108924, compare_enter)
    if not real:
        e.stub(0x1024a8, function=lambda machine: m.s32(machine.r[4] + 0x10))
    o.call(F_STOCK, 0, mode, 1, max_steps=800000000)
    assert expected[0] is None, 'unfinished stock plan'
    assert comparisons[0] == comparisons[1], 'final duplicate count'
    assert variables == [0x1c7b40, 0x1c7bc0] and resources == [0x538678]
    assert m.u32(S.COSMETIC) == S.special_rolls(cosmetic)[0], 'cosmetic RNG'
    if real:
        assert m.u32(S.SHARED) == reference_rng.seed, 'final shared RNG'
    else:
        assert m.u32(S.SHARED) == seed, 'outer routine changed shared RNG'
    value = ((lambda raw: I.item_value(tables, I.Item.unpack(tables, raw))) if real
             else (lambda raw: struct.unpack_from('<i', raw, 0x10)[0]))
    wanted = S.sorted_records(memory, value)
    counts = []
    for category, rows in enumerate(wanted):
        base = S.STOCK + category * S.LIST_STRIDE
        count = m.u32(base + 0x1200)
        assert count == len(rows), 'final count'
        assert m.read(base, count * S.ITEM_SIZE) == b''.join(rows), 'sorted stock bytes'
        counts.append(count)
    assert operations[0] == 7, 'fixed descriptor count'
    return counts, operations, m.u32(S.SHARED)


def identity_controls(path):
    o = Original(path)
    a, b = o.rec, o.rec2
    cases = 0
    for change in ('same', 'definition', 'flags', 'prefix', 'suffix', 'residue', 'count', 'null'):
        left = synthetic_record(1)
        right = bytearray(left)
        if change == 'definition':
            right[0] ^= 1
        elif change == 'flags':
            right[8] ^= 1
        elif change == 'prefix':
            right[0x20] ^= 1
        elif change == 'suffix':
            right[0x21] ^= 1
        elif change == 'residue':
            right[0x22] ^= 1
        elif change == 'count':
            right[4] ^= 1
        elif change == 'null':
            right[:4] = bytes(4)
        o.mem.write(a, left)
        o.mem.write(b, right)
        want = change in ('same', 'count')
        assert bool(o.call(0x108924, a, b)) == S.same_raw(left, right) == want
        cases += 1
    return cases


def mutation_controls(path):
    """Reject wrong budgets, duplicate handling, fixed count, specials and order."""
    original_budget = S.budget_contract
    original_rolls = S.special_rolls
    original_sort = S.sorted_records

    def shifted_budget(*args):
        contract = original_budget(*args)
        contract['low'] += 1
        return contract

    mutations = (
        ('budget_contract', shifted_budget),
        ('same_raw', lambda a, b: False),
        ('FIXED_WEAPONS', S.FIXED_WEAPONS[:-1]),
        ('special_rolls', lambda seed: (original_rolls(seed)[0], (False,False,False))),
        ('sorted_records', lambda memory, value: [list(reversed(rows))
                                                 for rows in original_sort(memory, value)]),
    )
    rejected = 0
    for name, replacement in mutations:
        saved = getattr(S, name)
        setattr(S, name, replacement)
        try:
            try:
                run_case(path, 2, 2, 7, cosmetic=2026, adversarial=True)
            except AssertionError:
                rejected += 1
            else:
                raise RuntimeError('stock mutation was not rejected')
        finally:
            setattr(S, name, saved)
    return rejected


def failed_outputs(path, tables):
    """Both zero-eligible and no-budget-fit exits must preserve all bytes."""
    o = Original(path, fast=True)
    game = I.Game()
    cases = 0
    for kind in ('affix', 'preset'):
        for budget, cap in ((10000, -1), (-1, 6)):
            rng = I.Rng(7)
            args = (budget, 0, -1, cap) if kind == 'affix' else (budget, 0, cap)
            model = I.generate_with_affixes if kind == 'affix' else I.generate_preset
            item = model(tables, game, rng, *args)
            assert item is None, 'failure control must produce nothing'
            before = synthetic_record(19, residue=0xa55a)
            o.set_game(game, 7)
            o.mem.write(o.rec, before)
            got = o.call(FUNCTIONS[kind], o.rec, *args)
            assert got == 0 and o.seed() == rng.seed, 'failure control return or seed'
            assert o.mem.read(o.rec, S.ITEM_SIZE) == before, 'failure control destination'
            cases += 1
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--real', action='store_true')
    parser.add_argument('--extended', action='store_true', help='add high difficulty and mixed-party passes')
    parser.add_argument('--special-only', action='store_true', help='execute a complete pass with all three special rolls')
    args = parser.parse_args()
    with open(args.elf, 'rb') as source:
        assert hashlib.sha256(source.read()).hexdigest() == EXPECTED_SHA256, 'executable digest'
    if args.special_only:
        cosmetic = next(seed for seed in range(100000) if all(S.special_rolls(seed)[1]))
        counts, operations, _ = run_case(args.elf, 8, 2, 20973, real=True,
                tables=I.Tables(args.elf), cosmetic=cosmetic)
        assert operations[2] == 3
        print('PASS original special stock lists=%d records=%d candidate_calls=%d preset_calls=%d' %
              (len(counts),sum(counts),sum(operations),operations[2]), flush=True)
        return
    cases = 0
    for difficulty in (1,2,3,4,5):
        for level in range(13):
            run_case(args.elf, level, difficulty, 20973, mode=1 + cases % 3)
            cases += 1
    for first, second in ((-2,0),(-1,0),(12,2),(0,11)):
        run_case(args.elf, first, 1, 7, second=second)
        cases += 1
    # Independent cosmetic seeds exercise all eight optional-special combinations.
    seeds = {}
    for seed in range(100000):
        seeds.setdefault(S.special_rolls(seed)[1], seed)
        if len(seeds) == 8:
            break
    assert len(seeds) == 8
    for seed in seeds.values():
        run_case(args.elf, 2, 2, 7, cosmetic=seed, adversarial=True)
        cases += 1
    print('PASS stock orchestration cases=%d special_patterns=%d' % (cases,len(seeds)), flush=True)
    print('PASS raw identity controls=%d' % identity_controls(args.elf), flush=True)
    print('PASS stock mutations rejected=%d' % mutation_controls(args.elf), flush=True)
    if args.real:
        tables = I.Tables(args.elf)
        print('PASS failed-generator preservation cases=%d' % failed_outputs(args.elf, tables), flush=True)
        fixtures = [(20973,0,1,(0,0,0,0),1,0,1), (7,2,1,(4,0,0,0),1,0xa5,1)]
        if args.extended:
            fixtures += [(20973,8,2,(0,4,1,6),4,0,2),
                         (7,11,3,(4,4,0,0),2,0x5a,3),
                         (20973,0,4,(0,0,0,0),1,0,1),
                         (7,11,5,(0,0,0,0),1,0,1)]
        for seed, level, difficulty, classes, players, fill, mode in fixtures:
            counts, operations, _ = run_case(args.elf, level, difficulty, seed,
                    real=True, tables=tables, classes=classes, players=players, stack_fill=fill, mode=mode)
            print('PASS original stock lists=%d records=%d candidate_calls=%d' %
                  (len(counts),sum(counts),sum(operations)), flush=True)


if __name__ == '__main__':
    main()
