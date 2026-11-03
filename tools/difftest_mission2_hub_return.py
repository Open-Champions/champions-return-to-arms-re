#!/usr/bin/env python3
"""Original final-portal -> hub request, constructed state only; no loaded return.

Use unittest preloading as in difftest_mission2_travel. Hub destination is
explicitly registered by the fixture; discovering it in gameplay is Unknown.
"""
import argparse
import hashlib
import itertools
from pathlib import Path

import ref_mission2_travel as R
import difftest_mission2_travel as T
from difftest_mission2 import SHA256, props_for, put


class HubFollow:
    def __contains__(self, address):
        return address in (0x1bf8d8, 0x1bf960, 0x1bf730) or address in T.Follow()


def run(executable, source, seed):
    assert hashlib.sha256(Path(executable).read_bytes()).hexdigest() == SHA256
    image, check, rows = T.inputs(Path(source))[3]
    row = rows[57]
    assert T.M.FACTORY[row['class'].lower()][1] == 0x27c694
    gate_key = check.call_values(0x13c, 'getv', 1, (0,))[0]
    cases = snapshots = 0
    for difficulty, evil, decision, complete1, complete2, gate in itertools.product(
            (0, 4), range(2), range(2), range(2), range(2), range(2)):
        p = T.Rig(executable, image)
        p.e.follow = HubFollow()
        # Explicit lower UI/local-admission services, as in the retained travel harness.
        for addr in (0x173c84, 0x1d92a0, 0x19e854, 0x1eb000, 0x17365c,
                     0x214230, 0x13e4e8, 0x13e150, 0x18cbfc):
            p.stub(addr)
        p.m.write(T.PLAYERS, bytes(4 * 0x4c30))
        p.m.w32(0x4f719c, difficulty)
        p.m.w32(0x404464, seed)
        p.m.w32(0x4d8ae0, 1)
        p.m.w8(T.PLAYERS + 0x4c1a, evil << difficulty)
        p.m.w8(T.PLAYERS + 0x4c1b, decision << difficulty)
        base = T.PLAYERS + 0x4bbf + difficulty * 13
        p.m.w8(base + 1, 1 | (complete1 << 1))
        p.m.w8(base + 2, 1 | (complete2 << 1))
        before = p.m.read(T.PLAYERS, 4 * 0x4c30)
        hub = p.m.cstr(p.call(0x1ec300))
        assert hub == ('hub2' if evil and decision and complete1 else 'hub')
        p.text(T.CURRENT, T.M.LEVELS[3])
        p.text(T.SUB, '')
        p.text(T.PENDING, '')
        p.set_destinations([hub, T.M.LEVELS[3]])
        p.m.w32(0x4f8450, p.e.alloc(0x80))
        p.m.w32(T.ALIVE, 1)
        p.m.w32(0x4f8440, 0)
        p.m.w8(T.NETWORK, 0)
        p.m.w32(0x4fe53c, 0)
        p.m.w32(0x41bfb8, 1)
        p.m.w32(0x41bfbc, 2)
        obj = p.e.alloc(0x180)
        p.m.w32(obj + 0x2c, props_for(p.e, row))
        p.call(0x1ed854, put(p.e, gate_key), gate)
        expected = R.prompt(gate, 0, 0, 0, [hub, T.M.LEVELS[3]], T.M.LEVELS[3], [])
        ready = p.call(0x27d7a0, obj, p.e.alloc(0x200), 0)
        assert (ready, p.m.u8(obj + 0x4d), p.destinations()) == expected
        if ready:
            p.call(0x27d754, obj, 0)
            p.call(0x27dd74)
            for _ in range(16):
                p.call(0x27dd74)
            assert p.m.u8(T.STATE) == 2
            assert p.m.u32(0x8e3a40) == 1
            # Explicit cursor selection, not a claim about physical pad navigation.
            p.m.w8(T.CHOICE, 0)
            p.m.w32(0x41bfe4, 2)
            p.call(0x27dd74)
            assert (p.m.u8(T.STATE), p.m.u32(T.COUNTER)) == R.menu_choice(0, 1, False)
            p.m.w32(0x41bfe4, 0)
            for _ in range(8):
                p.call(0x27dd74)
            assert p.m.u8(T.STATE) == 4
            p.call(0x27dd74)
            for _ in range(181):
                expected = R.travel_counter(p.m.u32(T.COUNTER), p.m.cstr(T.PENDING), hub, p.m.u8(T.ORIENT))
                p.call(0x27dd74)
                assert (p.m.u8(T.STATE), p.m.u32(T.COUNTER), p.m.cstr(T.PENDING), p.m.u8(T.ORIENT)) == expected
                snapshots += 1
            assert p.m.cstr(T.PENDING) == hub and p.m.u8(T.ORIENT) == 255
            p.call(0x27dd74)
            p.call(0x27dd74)
        else:
            assert p.m.cstr(T.PENDING) == ''
        assert p.m.u32(T.TASK_COUNT) == 0
        assert p.m.read(T.PLAYERS, len(before)) == before
        assert p.m.u32(0x404464) == seed
        cases += 1
    print('PASS seed=%d hub-return controls=%d travel-counter comparisons=%d' % (seed, cases, snapshots))
    print('LIMIT destination-list registration controlled; physical interaction, hub arrival/save and hub2 dialog Unknown')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('source')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    run(args.elf, args.source, args.seed)


if __name__ == '__main__':
    main()
