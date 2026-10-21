#!/usr/bin/env python3
"""Execute Nightmare_ctor with base/cosmetic services delegated.

The constructor and its direct state-0 body run in ee_emu. Creature_ctor,
animation, object random, event setup, run registration and Creature_init are
recorded call-outs; their bodies have separate research contracts.
"""
import argparse
import random
from pathlib import Path
from ee_emu import EE

CTOR = 0x270968
SET_STATE = 0x27155c
SIZE = 0x3d8

def put(out, offset, value, size):
    out[offset:offset + size] = value.to_bytes(size, 'little')

def reference(before, frame):
    out = bytearray(before)
    for off, value, size in (
        (0x48, 0x5155e8, 4), (0xb0, 0x3f199999, 4),
        (0x1c, 0x41f00000, 4), (0x28, 0x32, 1),
        (0xb8, 0, 4), (0x3c8, 0, 4), (0x5c, 0x3f800000, 4),
        (0xe0, 0xc1a00000, 4), (0xb4, 10, 1), (0xec, frame, 4),
        (0x3c0, 0x45160000, 4), (0x3ae, 2400, 2),
        (0xdc, 0x3f999999, 4), (0x3cc, 0, 2),
        (0xf4, int.from_bytes(before[0x300:0x304], 'little'), 4), (0x232, 0, 2)):
        put(out, off, value, size)
    flags = int.from_bytes(before[0xa8:0xb0], 'little') | 0x20200040000
    put(out, 0xa8, flags, 8)
    return out

def run(elf, seed):
    rng = random.Random(seed)
    ee = EE(str(elf))
    ee.follow = {SET_STATE}
    ee.mem.auto_map = True
    c = ee.alloc(SIZE)
    pos = ee.alloc(12)
    call_targets = (0x109d68, 0x1707b0, 0x170838, SET_STATE,
                    0x10a9c0, 0x1509d0, 0x16cfe0,
                    0x118378, 0x118378, 0x14f2b8, 0x10a230)
    for i in range(100):
        before = bytearray(SIZE)
        # The modelled constructor starts from a fresh pool block. The base
        # constructor is delegated, so its model pointer stays zero here.
        put(before, 0xa8, rng.getrandbits(64), 8)
        put(before, 0x44, rng.getrandbits(32), 4)
        ee.mem.write(c, before)
        frame = rng.randrange(0, 10000)
        ee.mem.w32(0x44fdcc, frame)
        ee.reset_log()
        ee.call(CTOR, c, 0x547380, pos, 0, 0x500848)
        got = ee.mem.read(c, SIZE)
        want = reference(before, frame)
        targets = tuple(x.target for x in ee.calls)
        if got != want or targets != call_targets:
            diffs = [hex(j) for j in range(SIZE) if got[j] != want[j]]
            print('FAIL', seed, i, 'offsets', diffs[:12], 'calls', targets == call_targets)
            return False
    print('seed %d: Nightmare_ctor plus state 0, 100/100 authored cases' % seed)
    return True

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('elf', type=Path)
    p.add_argument('--seed', type=int, required=True)
    a = p.parse_args()
    raise SystemExit(0 if run(a.elf, a.seed) else 1)
