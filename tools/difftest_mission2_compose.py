#!/usr/bin/env python3
"""Original hub-list, final-portal request and pre-load boundary for mission 2.

The destination list is produced by jumpgate_resetDestinations and
jumpgate_addCurrentLevel. The harness does not plant the hub name.
Dialog admission and a same-session offer are separate from this list proof.
Run with unittest preloaded. Private inputs stay under local/.
"""
import argparse
import hashlib
import itertools
from pathlib import Path

import ref_mission2 as M
import ref_mission2_compose as C
import ref_mission2_travel as R
import difftest_mission2_travel as T
from difftest_mission2 import SHA256, ScriptCheck, props_for, put

LATCH = 0x4F8F28
RESET, ADD, RESOLVE = 0x27DB00, 0x27DB60, 0x1EC300
READERS = {0x1BF730, 0x1BF8D8, 0x1BF960}
FOUND = 0x8E3A40


class ComposeFollow:
    def __contains__(self, address):
        return address in T.Follow() or address in READERS


def text(rig, address, value):
    rig.text(address, value)


def plant(rig, difficulty, evil, decision, first, second, seed):
    mem = rig.m
    mem.write(T.PLAYERS, bytes(4 * 0x4C30))
    mem.w32(0x4F719C, difficulty)
    mem.w32(0x4D8AE0, 1)
    mem.w32(0x404464, seed)
    mem.w8(T.PLAYERS + 0x4C1A, (evil & 1) << difficulty)
    mem.w8(T.PLAYERS + 0x4C1B, (decision & 1) << difficulty)
    base = T.PLAYERS + 0x4BBF + difficulty * 13
    mem.w8(base + 1, first & 0xFF)
    mem.w8(base + 2, second & 0xFF)
    text(rig, T.SUB, '')


def listed(rig):
    return rig.destinations()


def saw(rig, address):
    return any(call.target == address and not call.stubbed for call in rig.e.calls)


def fresh(executable, image=None):
    rig = T.Rig(executable, image)
    rig.e.follow = ComposeFollow()
    return rig


def check_reset_and_insert(executable, seed):
    cases = 0
    for difficulty, evil, decision, complete1, complete2, latch in itertools.product(
            (0, 4), (0, 1), (0, 1), (0, 1), (0, 1), (0, 1)):
        rig = fresh(executable)
        first = 1 | (complete1 << 1)
        second = 1 | (complete2 << 1)
        plant(rig, difficulty, evil, decision, first, second, seed)
        before = rig.m.read(T.PLAYERS, 4 * 0x4C30)
        hub = C.resolver_hub(evil, decision, complete1)
        assert rig.m.cstr(rig.call(RESOLVE)) == hub
        previous = ['keep', 'also']
        rig.m.w8(LATCH, latch)
        rig.set_destinations(previous)
        rig.e.reset_log()
        rig.call(RESET)
        assert listed(rig) == C.reset_destinations(latch, previous, hub)
        assert saw(rig, RESOLVE) == (not latch)
        assert rig.m.read(T.PLAYERS, len(before)) == before
        assert rig.m.u32(0x404464) == seed
        cases += 1
    # Completion is bit 1, including a row that is not also marked available.
    for first in (0, 1, 2, 3):
        rig = fresh(executable)
        plant(rig, 0, 1, 1, first, 0, seed)
        hub = C.resolver_hub(1, 1, (first & 2) != 0)
        assert rig.m.cstr(rig.call(RESOLVE)) == hub
        rig.m.w8(LATCH, 0)
        rig.call(RESET)
        assert listed(rig) == [hub]
        cases += 1
    samples = (
        ('hub', [], 'hub2'),
        ('hub', [], 'innovat1'),
        ('hub', ['keep'], 'innovat1'),
        ('hub', ['hub', 'hub2'], 'innovat1'),
        ('hub', ['hub2', 'hub'], 'inmine1'),
        ('hub', ['innovat1', 'hub2', 'hub'], 'innovat2'),
        ('hub', ['hub2'], 'hub'),
        ('hub', ['hub2'], 'hub2'),
        ('hub', ['hub2', 'innovat1'], 'innovat1'),
        ('hub2', [], 'hub'),
        ('hub2', ['hub', 'hub2'], 'innovat1'),
        ('hub2', ['hub2', 'hub'], 'inmine1'),
        ('hub2', ['innovat2', 'hub'], 'hub2'),
        ('hub2', ['innovat1', 'hub2', 'hub'], 'innovat2'),
    )
    for hub, start, current in samples:
        evil = decision = complete1 = int(hub == 'hub2')
        rig = fresh(executable)
        plant(rig, 0, evil, decision, 1 | (complete1 << 1), 1, seed)
        assert rig.m.cstr(rig.call(RESOLVE)) == hub
        rig.set_destinations(start)
        text(rig, T.CURRENT, current)
        text(rig, T.SUB, '')
        rig.e.reset_log()
        rig.call(ADD)
        got = listed(rig)
        assert got == C.add_current(start, current, hub), (hub, start, current, got)
        # The resolver runs only when a new name is being considered and some
        # name involved is exactly one of the two hub names. A repeated current
        # level returns before that call.
        involved = current not in start and any(
            name in C.HUBS for name in (current, *start))
        called = sorted({hex(c.target) for c in rig.e.calls if not c.stubbed})
        assert saw(rig, RESOLVE) == involved, (hub, start, current, called)
        assert saw(rig, 0x1EC0F0)
        cases += 1
    for hub in C.HUBS:
        rig = fresh(executable)
        evil = decision = complete1 = int(hub == 'hub2')
        plant(rig, 0, evil, decision, 1 | (complete1 << 1), 1, seed)
        rig.m.w8(LATCH, 0)
        text(rig, T.CURRENT, hub)
        rig.call(RESET)
        for level in M.LEVELS:
            text(rig, T.CURRENT, level)
            rig.call(ADD)
        assert listed(rig) == C.route_list(hub, M.LEVELS)
        text(rig, T.CURRENT, M.LEVELS[-1])
        cases += 1
    return cases


def portal_return(executable, fixture, seed):
    image, check, rows = fixture
    row = rows[57]
    assert isinstance(check, ScriptCheck)
    assert M.FACTORY[row['class'].lower()][1] == 0x27C694
    gate_key = check.call_values(0x13C, 'getv', 1, (0,))[0]
    cases = snapshots = 0
    # Difficulty 0 covers both hubs; difficulty 4 covers the evil row only.
    plans = ((0, 0, 0, 1), (0, 1, 1, 1), (4, 1, 1, 1))
    for difficulty, evil, decision, complete1 in plans:
        for gate in (0, 1):
            rig = fresh(executable, image)
            for addr in (0x173C84, 0x1D92A0, 0x19E854, 0x1EB000, 0x17365C,
                         0x214230, 0x13E4E8, 0x13E150, 0x18CBFC):
                rig.stub(addr)
            plant(rig, difficulty, evil, decision, 1 | (complete1 << 1), 1, seed)
            hub = C.resolver_hub(evil, decision, complete1)
            rig.m.w8(LATCH, 0)
            text(rig, T.CURRENT, hub)
            rig.call(RESET)
            for level in M.LEVELS:
                text(rig, T.CURRENT, level)
                rig.call(ADD)
            built = listed(rig)
            assert built == C.route_list(hub, M.LEVELS)
            before = rig.m.read(T.PLAYERS, 4 * 0x4C30)
            text(rig, T.PENDING, '')
            rig.m.w32(0x4F8450, rig.e.alloc(0x80))
            rig.m.w32(T.ALIVE, 1)
            rig.m.w32(0x4F8440, 0)
            rig.m.w8(T.NETWORK, 0)
            rig.m.w32(0x4FE53C, 0)
            rig.m.w32(0x41BFB8, 1)
            rig.m.w32(0x41BFBC, 2)
            obj = rig.e.alloc(0x180)
            rig.m.w32(obj + 0x2C, props_for(rig.e, row))
            rig.call(0x1ED854, put(rig.e, gate_key), gate)
            ready = rig.call(0x27D7A0, obj, rig.e.alloc(0x200), 0)
            assert listed(rig) == built
            assert (ready, rig.m.u8(obj + 0x4D)) == (gate, gate)
            if not ready:
                assert rig.m.cstr(T.PENDING) == '' and rig.m.u32(T.TASK_COUNT) == 0
                cases += 1
                continue
            rig.call(0x27D754, obj, 0)
            rig.call(0x27DD74)
            for _ in range(16):
                rig.call(0x27DD74)
            assert rig.m.u8(T.STATE) == 2
            assert rig.m.u32(FOUND) == built.index(M.LEVELS[-1])
            # Explicit row selection, not a claim about pad navigation.
            rig.m.w8(T.CHOICE, 0)
            rig.m.w32(0x41BFE4, 2)
            rig.call(0x27DD74)
            assert (rig.m.u8(T.STATE), rig.m.u32(T.COUNTER)) == R.menu_choice(0, 1, False)
            rig.m.w32(0x41BFE4, 0)
            for _ in range(8):
                rig.call(0x27DD74)
            assert rig.m.u8(T.STATE) == 4
            rig.call(0x27DD74)
            for _ in range(181):
                expected = R.travel_counter(
                    rig.m.u32(T.COUNTER), rig.m.cstr(T.PENDING), hub, rig.m.u8(T.ORIENT))
                rig.call(0x27DD74)
                assert (rig.m.u8(T.STATE), rig.m.u32(T.COUNTER),
                        rig.m.cstr(T.PENDING), rig.m.u8(T.ORIENT)) == expected
                snapshots += 1
            assert rig.m.cstr(T.PENDING) == hub and rig.m.u8(T.ORIENT) == 255
            assert listed(rig) == built
            assert rig.m.read(T.PLAYERS, len(before)) == before
            assert rig.m.u32(0x404464) == seed
            boundary(rig, hub, M.LEVELS[-1])
            cases += 1
    return cases, snapshots


def boundary(rig, pending, current):
    """Same pre-load stop as the retained travel test. Act-change stays stubbed off."""
    for address in (0x19D9F8, 0x21777C, 0x217F70, 0x2247EC, 0x216588):
        rig.stub(address)

    def stop(emu):
        assert emu.mem.cstr(emu.r[4] & 0xFFFFFFFF) == pending
        raise T.Boundary()

    rig.e.hook(0x1E55C0, stop)
    try:
        rig.call(0x320EDC)
        raise AssertionError('load boundary was not reached')
    except T.Boundary:
        pass
    assert (rig.m.cstr(T.PENDING), rig.m.cstr(T.CURRENT), rig.m.cstr(T.SUB),
            rig.m.cstr(T.PREVIOUS), rig.m.u8(T.ORIENT), rig.m.u8(0x41B7C1)) == R.request_names(
                pending, current, '', 255)
    assert rig.e.pc == 0x1E55C0
    rig.e.unhook(0x1E55C0)


def run(executable, source, seed):
    assert hashlib.sha256(Path(executable).read_bytes()).hexdigest() == SHA256
    fixtures = T.inputs(Path(source))
    listed_cases = check_reset_and_insert(executable, seed)
    portal_cases, snapshots = portal_return(executable, fixtures[3], seed)
    print('PASS seed=%d route-list cases=%d portal returns=%d counter comparisons=%d' % (
        seed, listed_cases, portal_cases, snapshots))
    print('LIMIT same-session offer, menu-task admission, physical use, '
          'full loader and arrival remain open in this file')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('source')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    run(args.elf, args.source, args.seed)


if __name__ == '__main__':
    main()
