#!/usr/bin/env python3
"""Bounded original-code probe for the level-up stat-point input gate.

PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_levelup.py /path/to/SLUS_209.73

The screen runs in ee_emu with constructed menu state and stubbed draw/audio
callees. This verifies sender calls, not rendered pixels or console behavior.
"""
import hashlib
import os
import sys

from ee_emu import EE


EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
SCREEN = 0x1D1DB8
SENDER = 0x1C5780
RECORD = 0x4D8AF0


def original_sends(elf, seed, *, slot=0, page=2, edge=0x40, cursor=0, panel_state=0,
                   half=0, points=3, elapsed=3000):
    ee = EE(elf)
    ee.mem.auto_map = True
    ee.follow = set()  # run the screen, stub unrelated presentation callees
    ee.default_ret = 0
    ee.mem.w32(0x404464, seed)
    ee.mem.w32(0x44FDA4, elapsed)
    ee.mem.w32(0x4F65EC, slot)    # owner pad index and sender slot
    ee.mem.w32(0x4F65CC, panel_state)
    ee.mem.w32(0x4F65D0, cursor)
    ee.mem.w32(0x41BFE8 + 88 * slot, edge)  # indexed pad edge word
    ee.mem.w8(RECORD + 0x4C30 * slot + 0xEE, half)
    ee.mem.w8(RECORD + 0x4C30 * slot + 0xEC, points)
    ee.call(SCREEN, 0, page, 0, 0x4F4040, max_steps=1_000_000)
    assert ee.mem.u32(0x404464) == seed
    return [(c.site, c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF)
            for c in ee.calls if c.target == SENDER]


def main(argv):
    elf = argv[1] if len(argv) > 1 else os.path.expanduser('~/champions-re/SLUS_209.73')
    with open(elf, 'rb') as f:
        assert hashlib.sha256(f.read()).hexdigest() == EXPECTED_SHA256, 'wrong executable'
    cases = [(dict(cursor=i), [(site, 0, i)]) for i, site in enumerate(
        (0x1D24D4, 0x1D24F4, 0x1D2510, 0x1D252C))]
    cases += [
        (dict(cursor=4), []), (dict(page=0), []), (dict(page=3), []),
        (dict(edge=0), []), (dict(edge=0x10), []),
        (dict(panel_state=1), []), (dict(half=1), []),
        (dict(elapsed=2999), []),
        (dict(elapsed=3000), [(0x1D24D4, 0, 0)]),
        (dict(points=0), [(0x1D24D4, 0, 0)]),
        (dict(slot=1, cursor=2), [(0x1D2510, 1, 2)]),
    ]
    for seed in (20973, 7):
        for options, want in cases:
            got = original_sends(elf, seed, **options)
            assert got == want, (seed, options, got, want)
        print('PASS seed %d: %d stat-point sender gates' % (seed, len(cases)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
