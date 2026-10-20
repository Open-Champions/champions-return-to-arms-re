#!/usr/bin/env python3
"""Original setState vs ref_field_precedence, for values of two fields at once.

Usage: python3 tools/difftest_field_precedence.py local/SLUS_209.73

Uses the same Scanner as the round-3 dispatch difftest (one function, stubbed
callees, synthetic definition). Does not change that difftest's vectors.
"""
import sys
import scan_anim_dispatch as S
import ref_creature_dispatch_data as T
import ref_field_precedence as P

OBJ = S.OBJ
AGONY_FLAGS = (
    0, 1, 0x40000, 0x80000, 0x100000, 0x200000, 0x380000,
    0x40000 | 0x80000, 0x40000 | 0x100000, 0x40000 | 0x200000,
    0x40000 | 0x380000, 0x40001, 0x380001, 0xffffffff,
)


def fingerprint(sc, fn, state, pokes):
    sc.reset()
    sc.ee.default_ret = 0
    sc.rand = 0
    for off, value in pokes:
        sc.ee.mem.store(OBJ + off, 4, value & 0xffffffff)
    status, calls, _reads = sc.execute(fn, (OBJ, state), {fn})
    stored = sc.ee.mem.load(OBJ + 0x232, 2)
    ops = []
    for rec in sc.describe(calls, own={S.FILTER}):
        if 'fn' in rec:
            flags = rec.get('flags')
            ops.append((rec['fn'], rec.get('entry'),
                        int(flags, 16) if flags else None))
        elif 'vslot' in rec:
            ops.append(('vslot', rec['vslot'], None))
    return status, stored, tuple(ops)


def main():
    sc = S.Scanner(sys.argv[1])
    failed = 0
    n = 0
    agony = T.DISPATCH['Agony']['setState']
    for flags in AGONY_FLAGS:
        status, stored, ops = fingerprint(sc, agony, 0x12, [(0x2dc, flags)])
        expect = P.agony_hit_entry(flags)
        n += 1
        ok = (status == 'ok' and stored == 0x12 and len(ops) == 1
              and ops[0][0] == 'anim_startBlendInOut' and ops[0][1] == expect)
        if not ok:
            failed += 1
            print('FAIL agony %#x' % flags, status, stored, ops, 'want', expect)
    clock = T.DISPATCH['Clockwork']['setState']
    for form in range(0, 7):
        status, stored, ops = fingerprint(sc, clock, 0, [(0x3c8, form)])
        expect = P.clockwork_idle_entry(form)
        n += 1
        got = ops[0][1] if ops and ops[0][0] == 'anim_start' else None
        if not (status == 'ok' and got == expect):
            failed += 1
            print('FAIL clockwork form', form, status, ops, 'want', expect)
    for row in P.COMBINED:
        fn = T.DISPATCH[row['cls']]['setState']
        status, stored, ops = fingerprint(sc, fn, row['state'], row['fields'])
        n += 1
        if not (status == 'ok' and stored == row['stored'] and ops == row['ops']):
            failed += 1
            print('FAIL', row['cls'], hex(row['state']), status, stored, ops)
    print('%d checks, %d failed' % (n, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
