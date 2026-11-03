#!/usr/bin/env python3
"""Counts-only original Trigger construction, first lookup and edge comparisons.

python3 -m tools.difftest_exit_walkin --seed 20973
Script entry bodies alone are callbacks on the tested run path. Original grid,
RTTI, property access, action dispatcher, shape and save/load bodies execute.
"""
import argparse
from collections import Counter
import hashlib
from itertools import product
from pathlib import Path
import random
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from difftest_objects import Rig, POOL_NEW, EXPECTED_SHA256
from ee_emu import float_to_raw as f32


def run(elf, seed):
    rng = random.Random(seed)
    rig = Rig(elf, seed)
    e, m, world = rig.emu, rig.emu.mem, rig.model
    counts = Counter()
    def equal(got, want):
        assert got == want, 'comparison mismatch_count=1'
        counts['assertions'] += 1
    def call(addr, *args):
        counts['entry_calls'] += 1
        return rig.ecall(addr, *args, max_steps=100000)
    # Actual Trigger constructor: t (not script) is the serialized entry property.
    props = [b'w=10', b'h=10', b't=SYN_EXIT', b'script=SYN_WRONG']
    pk = rig.add_props(props)
    trigger = world.pool.new(0x70)
    obj = world.construct(trigger, (f32(0), f32(0), f32(0)), props=props)
    obj.flags = 3
    equal(call(POOL_NEW, 0x70), trigger)
    call(0x1ECDF4, trigger, rig.vec(0, (0, 0, 0)), rig.props[pk][0])
    equal(tuple(m.u32(trigger + x) for x in (0x4C, 0x50, 0x54, 0x58)),
          tuple(f32(x) for x in (0, -10, 10, 0)))
    equal(m.cstr(m.u32(trigger + 0x5C)), 'SYN_EXIT')
    equal((m.u32(trigger + 0x48), m.u32(trigger + 0x0C), m.s32(trigger + 0x68)),
          (0x511600, 3, -1))
    params = []
    for i in range(3):
        pk = rig.add_props([b'action=SYN_LINK', b'ononly=0', b'offonly=0'])
        args = (0x80, (f32(5), f32(-5), f32(0)), pk, 0, 'none', 0x100003, 0)
        want, got = rig.m_new(*args), rig.e_new(*args)
        equal(want, got)
        params.append(got)
    # These candidate objects use original base construction and original
    # TriggerParams RTTI tables, not claimed full derived construction.
    players = [e.alloc(0x50) for _ in range(4)]
    m.w32(0x4D8AE0, 4)
    for i, player in enumerate(players):
        m.w32(0x4DCEC8 + 0x4C30*i, player)
        m.w32(player + 0x10, f32(100))
    events, queries = [], []
    e.stub(0x1ED694, function=lambda ee: events.append(
        (m.cstr(ee.r[4]), m.u32(0x4039F8), m.s32(0x4D8AE4))) or 1)
    def query(ee):
        lo = tuple(m.u32(ee.r[4] + i*4) for i in range(3))
        hi = tuple(m.u32(ee.r[5] + i*4) for i in range(3))
        equal((lo, hi, ee.r[7]), ((f32(0), f32(-10), f32(-12000)),
                                 (f32(10), f32(0), f32(12000)), 128))
        queries.append(ee.r[6])
    e.hook(0x14A928, query)
    for mask in range(8):
        for i, addr in enumerate(params):
            m.w32(addr + 0x48, 0x511698 if mask & (1 << i) else 0x511600)
            m.w32(addr + 0x4C, 0)
        m.w8(trigger + 0x61, 0)
        m.w32(trigger + 0x6C, 0)
        m.w32(trigger + 0x64, 0)
        m.w8(trigger + 0x60, 0)
        queries.clear()
        order = world.collect_in_box(tuple(f32(x) for x in (0, -10, -12000)),
                                     tuple(f32(x) for x in (10, 0, 12000)), 128)
        addresses = [o.addr for o in order]
        expected = next((a for a in addresses if a in params and mask & (1 << params.index(a))), 0)
        call(0x1ECF3C, trigger)
        equal(len(queries), 1)
        equal([m.u32(queries[0] + 4*i) for i in range(len(addresses) + 1)], addresses + [0])
        equal((m.u8(trigger + 0x61), m.u32(trigger + 0x6C)), (1, expected))
        equal([m.u32(a + 0x4C) for a in params], [trigger if a == expected else 0 for a in params])
        call(0x1ECF3C, trigger)
        equal(len(queries), 1)  # Link search is one-shot even if no match was found.
        counts['lookup_cases'] += 1
    # Original property/action path, both occupants and no occupant, both overrides.
    linked = params[0]
    for inside, occupied, recall, on, off in product((0, 1), (0, 1), (0, 1), (0, 1), (0, 1)):
        props = [b'action=SYN_LINK', b'ononly=%d' % on, b'offonly=%d' % off,
                 b'timeout=2']
        pk = rig.add_props(props)
        m.w32(linked + 0x2C, rig.props[pk][0])
        m.w32(trigger + 0x6C, linked)
        m.w32(trigger + 0x64, 0)
        m.w32(trigger + 0x68, 99)
        m.w8(trigger + 0x60, inside)
        m.w8(0x41B51D, recall)
        m.w32(0x4039F8, 0x123456)
        active = rng.randrange(4)
        m.w32(0x4D8AE4, active)
        for i, player in enumerate(players):
            m.w32(player + 0x10, f32(5 if occupied and i in (1, 2) else 100))
            m.w32(player + 0x14, f32(-5))
            m.w32(player + 0x18, f32(rng.choice((-50000, 50000))))
        suppressed = occupied and recall
        edge = not suppressed and inside != occupied
        selected = 0 if off else 1 if on else occupied
        expected_events = []
        if edge:
            expected_events.append(('SYN_LINK' if selected else 'notSYN_LINK', linked, active))
            if selected:
                active = 1 if occupied else 0
            expected_events.append(('SYN_EXIT' if selected else 'notSYN_EXIT', trigger, active))
        events.clear()
        call(0x1ECF3C, trigger)
        equal(events, expected_events)
        equal(m.s32(trigger + 0x68), -1 if suppressed or not occupied else 1)
        equal(m.u8(trigger + 0x60), inside if suppressed else 0 if edge and (on or off) else occupied)
        equal(m.s32(trigger + 0x64), 8 if edge and (on or off) else 0)
        equal(m.u32(0x4039F8), 0 if edge else 0x123456)
        equal(m.s32(0x4D8AE4), active)
        counts['edge_cases'] += 1
    # Save/load must carry exactly five bytes, not cached link/slot context.
    buffer = e.alloc(16)
    for delay, inside in product((-2, -1, 0, 1, 8), (0, 1)):
        m.w32(trigger + 0x64, delay)
        m.w8(trigger + 0x60, inside)
        m.write(buffer, b'Z'*16)
        expected = struct.pack('<iB', delay, inside)
        equal(call(0x1ECF18, trigger, buffer), 5)
        equal(m.read(buffer, 16), expected + b'Z'*11)
        m.write(buffer, expected)  # independent load input
        m.w32(trigger + 0x64, 77)
        m.w8(trigger + 0x60, 7)
        equal(call(0x1ECEF4, trigger, buffer), 5)
        equal((m.s32(trigger + 0x64), m.u8(trigger + 0x60)), (delay, inside))
        for enabled in (0, 1):
            m.w32(linked + 0x4C, trigger)
            call(0x1ECDCC, linked, enabled)
            equal(m.s32(trigger + 0x64), 0 if enabled else -1)
        counts['save_rearm_cases'] += 1
    equal(len(e.patches), 0)
    equal(len(m.auto_mapped), 0)
    print('PASS exit_walkin seed=%d ' % seed +
          ' '.join('%s=%d' % x for x in sorted(counts.items())) + ' failures=0')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    elf = 'local/SLUS_209.73'
    assert hashlib.sha256(Path(elf).read_bytes()).hexdigest() == EXPECTED_SHA256
    run(elf, args.seed)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('FAIL exit_walkin failures=1')
        raise SystemExit(1)
