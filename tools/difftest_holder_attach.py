#!/usr/bin/env python3
"""Execute the two holder slot-1 bodies against an authored byte model."""
import argparse
import random
from pathlib import Path
from ee_emu import EE

BODIES = (0x11afb0, 0x11bc18)

def reference(body, before, hand, entry):
    after = bytearray(before)
    slot = 8 if hand == 1 else 0x98 if body == 0x11bc18 and hand == 2 else None
    if slot is None:
        return after, 1
    after[slot] = entry & 0xff
    bit = 1 if hand == 1 else 2
    after[4] = (before[4] | bit) if (entry & 0xff) else (before[4] & ~bit)
    return after, after[4]

def run(elf, seed):
    rng = random.Random(seed)
    ee = EE(str(elf))
    at = ee.alloc(256)
    for body in BODIES:
        for i in range(300):
            before = bytes(rng.getrandbits(8) for _ in range(256))
            hand, entry = rng.randrange(0, 5), rng.randrange(0, 256)
            ee.mem.write(at, before)
            got_result = ee.call(body, at, hand, entry)
            got = ee.mem.read(at, 256)
            want, want_result = reference(body, before, hand, entry)
            if got_result != want_result or got != want:
                print('FAIL', seed, hex(body), i, hex(got_result),
                      hex(hand), hex(entry),
                      [(j, hex(got[j]), hex(want[j])) for j in range(256) if got[j] != want[j]])
                return False
        print('seed %d body %x: 300/300 cases' % (seed, body))
    return True

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('elf', type=Path)
    p.add_argument('--seed', type=int, required=True)
    a = p.parse_args()
    raise SystemExit(0 if run(a.elf, a.seed) else 1)
