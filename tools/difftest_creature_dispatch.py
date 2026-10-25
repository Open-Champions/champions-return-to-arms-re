#!/usr/bin/env python3
"""Original setState bodies vs the committed dispatch table, one call at a time.

Usage: python3 tools/difftest_creature_dispatch.py local/SLUS_209.73 [Class ...]

For every class and recorded state of ref_creature_dispatch_data: the baseline request,
every residue of a random choice and every recorded field/callee condition is executed
again in tools/ee_emu.py (callees stubbed, Creature_filterState passing the request
through) and the ordered animation/virtual calls and the stored state are compared with
ref_creature_dispatch.select.  Stubbed callees; no rendered or running-game claim.
"""
import json
import sys
import ref_creature_dispatch as D
import ref_creature_dispatch_data as T
import scan_anim_dispatch as S


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    sc = S.Scanner(argv[1])
    only = set(argv[2:])
    checks = 0
    for name, info in sorted(T.DISPATCH.items()):
        if only and name not in only:
            continue
        fn = info['setState']
        if sc.slot(info['vtable'], 27) != fn:
            raise AssertionError('%s: vtable slot 27 is not %#x' % (name, fn))
        for st, case in sorted(info['states'].items()):
            runs = [((), {})]
            if 'rand' in case:
                runs = [((), {'rand': r}) for r in range(case['rand'][0])]
            elif 'rand_points' in case:
                runs = [((), {'rand': r}) for r, _, _ in case['rand_points']]
            for cond, _, _ in case.get('when', ()):
                runs.append((cond, {}))
            for cond, kw in runs:
                if cond and cond[0] == 'ret':
                    key = sc.one_state(fn, st, default=cond[1])[0]
                    want = D.select(case, ret=cond[1])
                elif cond:
                    addr = cond[0] + (S.OBJ if cond[0] < 0x10000 else 0)
                    size = 4 if addr % 4 == 0 else (2 if addr % 2 == 0 else 1)
                    reads = sc.one_state(fn, st)[1]
                    size = next((s for _, a, s, _ in reads if a == addr), size)
                    key = sc.one_state(fn, st, poke=(addr, size, cond[1]))[0]
                    want = D.select(case, field=cond)
                else:
                    key = sc.one_state(fn, st, rand=kw.get('rand', 0))[0]
                    want = D.select(case, **kw)
                calls, stored, status = json.loads(key)
                got = (S.to_ops(calls), stored)
                if got != (list(want[0]), want[1]):
                    raise AssertionError('%s state %#x %r: %r != %r'
                                         % (name, st, cond or kw, got, want))
                checks += 1
    print('PASS %d setState executions match the committed table (ops, order, stored)'
          % checks)
    print('Stubs: callees, Creature_filterState pass-through, GameObject_rand residues.')


if __name__ == '__main__':
    main(sys.argv)
