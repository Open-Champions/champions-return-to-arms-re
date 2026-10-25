#!/usr/bin/env python3
"""Execute balance_hashName and balance_lookup on authored rows, two selectable seeds.

Only the executable is private input. No game table rows are read or written.
"""
import argparse
import random
import struct
from pathlib import Path

from ee_emu import EE
from ref_combat import ONE, fmul, itof

BALANCE_RECORDS = 0x4FB5C4
BALANCE_COUNT = 0x4FB5C8
HASH = 0x223914
LOOKUP = 0x223A4C
PERCENT = 0x3C23D70A


def hash_name(name):
    h = 0
    for ch in name:
        c = ch - 256 if ch > 127 else ch
        if 65 <= ch <= 90:
            c += 32
        h = ((h + c) & 0xFFFF) * 0x401 & 0xFFFF
        h ^= h >> 6
    h = h * 9 & 0xFFFF
    return ((h >> 11) ^ h) * 0x8001 & 0xFFFF


def run(elf, seed, cases):
    rng = random.Random(seed)
    emu = EE(str(elf))
    mem = emu.mem
    name_at = emu.alloc(80)
    rows_at = emu.alloc(12 * 16)
    outs = [emu.alloc(4) for _ in range(5)]
    failures = []
    for i in range(cases):
        name = bytes(rng.choice(b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_')
                     for _ in range(rng.randrange(1, 25)))
        mem.write(name_at, name + b'\0')
        want_hash = hash_name(name)
        got_hash = emu.call(HASH, name_at, len(name)) & 0xFFFF
        if got_hash != want_hash:
            failures.append((i, 'hash', hex(got_hash), hex(want_hash)))
        n = rng.randrange(0, 16)
        match = rng.randrange(n + 1)
        expected = None
        for j in range(n):
            h = want_hash if j == match or (j > match and rng.randrange(4) == 0) else rng.getrandbits(16)
            vals = [rng.randrange(-200, 501) for _ in range(5)]
            mem.write(rows_at + 12 * j, struct.pack('<H5h', h, *vals))
            if h == want_hash and expected is None:
                expected = vals
        mem.w32(BALANCE_RECORDS, rows_at)
        mem.w32(BALANCE_COUNT, n)
        got_found = emu.call(LOOKUP, name_at, *outs)
        got = [mem.u32(a) for a in outs]
        # The lookup uses unsigned halfword loads, including on rows whose
        # stored bits would be negative if interpreted as s16.
        want = [fmul(itof(v & 0xFFFF), PERCENT) for v in expected] if expected else [ONE] * 5
        if (got_found, got) != (int(expected is not None), want):
            failures.append((i, 'lookup', got_found, [hex(x) for x in got], [hex(x) for x in want]))
        if len(failures) >= 3:
            break
    print('seed %d: %d authored hash and lookup cases, %d mismatches' % (seed, cases, len(failures)))
    for failure in failures:
        print('FAIL', failure)
    return not failures


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('elf', type=Path)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--cases', type=int, default=300)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.elf, args.seed, args.cases) else 1)
