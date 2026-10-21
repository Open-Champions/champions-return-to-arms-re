#!/usr/bin/env python3
"""Execute Player_ctor on the owner's US v2.00 executable (two seed pins).

The model definition and absent appearance resources are authored fixtures.
The test compares every direct non-stack byte written by the constructor, all
external call targets in order, the record link, and the shared seed.
"""
import argparse
import os

from ee_emu import EE
import ref_arena_player as R


def flatten(fields):
    return {address + i: (value >> (8 * i)) & 0xFF
            for address, (size, value) in fields.items() for i in range(size)}


def one(path, seed):
    e = EE(path)
    player = e.alloc(0x590)
    pos = e.alloc(16)
    definition = e.alloc(0x400)
    part = e.alloc(0x200)
    for offset in range(0, 0x400, 4):
        e.mem.w32(definition + offset, part)
    e.mem.w32(R.RECORDS + 0x54, 0)
    e.mem.write(R.RECORDS + 0x20, b'\xff' * 4)
    e.mem.w32(R.SEED, seed)
    e.follow = {0x1509D0}

    def base(x):
        x.mem.w32(player + 0x24, definition)
        return player

    e.stub(0x109D68, function=base)
    e.call(R.CTOR, player, pos, 0, 0)
    actual = {}
    for pc, address, size, value in e.writes:
        if R.CTOR <= pc <= 0x1A24B4:
            actual.update(flatten({address: (size, value)}))
    expected = flatten(R.constructor_fields(player, 0, part))
    expected.update(flatten({0x4EBBB4: (4, 0x5353E0)}))
    assert actual == expected, (seed,
        {'missing': sorted(set(expected) - set(actual)),
         'extra': sorted(set(actual) - set(expected)),
         'different': [(hex(a), actual[a], expected[a]) for a in actual.keys() & expected.keys()
                       if actual[a] != expected[a]][:20]})
    calls = tuple(c.target for c in e.calls)
    assert calls == R.CALLS, (seed, calls)
    assert e.mem.u32(R.SEED) == seed, (seed, e.mem.u32(R.SEED))
    assert e.mem.u32(R.RECORDS + 0x43D8) == player
    return len(actual), len(calls)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('elf')
    args = ap.parse_args()
    if not os.path.isfile(args.elf):
        raise SystemExit('executable missing')
    for seed in (20973, 7):
        writes, calls = one(args.elf, seed)
        print('seed %d: Player_ctor %d direct bytes, %d calls, 0 shared draws matched' %
              (seed, writes, calls))


if __name__ == '__main__':
    main()
