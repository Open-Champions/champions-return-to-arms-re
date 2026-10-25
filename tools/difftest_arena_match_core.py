#!/usr/bin/env python3
"""Compare bounded arena helper models with the owner's US v2.00 executable.

Usage: python3 tools/difftest_arena_match_core.py path/to/SLUS_209.73 --seed 20973
"""
import argparse
import os
import random

from ee_emu import EE, float_to_raw
import ref_arena_match_core as R
import difftest_arena_modes as D
from ref_core import ONE, ZERO

M32 = 0xFFFFFFFF
FIELDS = (0xE4, 0x228, 0x22C, 0xD0, 0xD2, 0xD4, 0xD8)
HALVES = {0xE4, 0xD0, 0xD2, 0xD4}


def writes(emu, wanted):
    return {address: value for _, address, _, value in emu.writes if address in wanted}


def test_scale(path, rng):
    checked = 0
    for _ in range(100):
        emu = EE(path)
        creature = emu.alloc(0x500)
        fields = {}
        for offset in FIELDS:
            if offset in HALVES:
                value = rng.randrange(0, 1000)
                emu.mem.w16(creature + offset, value)
            else:
                value = float_to_raw(rng.uniform(1, 500))
                emu.mem.w32(creature + offset, value)
            fields[offset] = value
        factors_f = tuple(rng.choice((0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0))
                          for _ in range(5))
        expected = R.scale_stats(fields, tuple(map(float_to_raw, factors_f)))
        emu.call(R.SCALE_STATS, creature, fargs=factors_f)
        actual = {offset: (emu.mem.u16(creature + offset) if offset in HALVES
                           else emu.mem.u32(creature + offset)) for offset in FIELDS}
        assert actual == expected, ('scaleStats', fields, factors_f, actual, expected)
        assert not emu.calls, ('scaleStats made unexpected calls', emu.calls)
        checked += 1
    return checked


def test_empty_visit(path):
    checked = 0
    for flags in (0, 0x20, 0x21, 0x22, 0x28, 0x40, 0x60, 0x68, 0x40020):
        for state in (0, 1, 0x7FFF, 0xFFFF):
            for count in (0, 7, 0xFFFF):
                emu = EE(path)
                creature = emu.alloc(0x500)
                emu.mem.w32(creature + 0xC, flags)
                emu.mem.w16(creature + 0x312, state)
                emu.mem.w16(R.LIVE_COUNT, count)
                expected = R.empty_wave_visit(flags, state, count)
                emu.call(R.EMPTY_WAVE_VISIT, creature)
                actual = emu.mem.u16(R.LIVE_COUNT)
                assert actual == (count if expected is None else expected), (flags, state, count, actual, expected)
                actual_writes = writes(emu, {R.LIVE_COUNT})
                assert actual_writes == ({} if expected is None else {R.LIVE_COUNT: expected})
                assert not emu.calls
                checked += 1
    return checked


def test_next(path):
    checked = 0
    for increment, live in ((0, 0), (1, 3), (2, 7), (0xFFFF, 0)):
        emu = EE(path)
        emu.follow = {R.PREPARE_WAVE}
        emu.default_ret = 0
        emu.mem.w16(R.LIVE_COUNT, 7)
        emu.mem.w16(R.SAVED_COUNT, 9)
        def walker(e):
            e.mem.w16(R.LIVE_COUNT, live)
            return 0
        emu.stub(0x14A610, function=walker)
        emu.call(R.NEXT_WAVE, increment)
        expected_calls = [(0x322954, 15), (R.PREPARE_WAVE, None),
                          (0x19F018, None), (0x14A610, R.SAVE_WAVE_VISIT),
                          (0x305ED4, increment)]
        actual_calls = [(call.target, call.args[0] & M32 if want is not None else None)
                        for call, (_, want) in zip(emu.calls, expected_calls)]
        assert actual_calls == expected_calls and len(emu.calls) == len(expected_calls), (actual_calls, expected_calls)
        assert emu.mem.u16(R.LIVE_COUNT) == live
        assert emu.mem.u16(R.SAVED_COUNT) == live
        checked += 1
    return checked


def test_saved_record(path):
    checked = 0
    for flags in (0, 0x20, 0x21, 0x22, 0x28, 0x2A, 0x2B, 0x612B,
                  0x40, 0x60, 0x40020):
        for state in (0, 0xFFFF):
            for count in (0, 3):
                emu = EE(path)
                creature = emu.alloc(0x500)
                table = emu.alloc(0x100)
                vtable = emu.alloc(0x20)
                dead_fn = 0xF00004
                emu.mem.w32(creature + 0xC, flags)
                emu.mem.w16(creature + 0x312, state)
                emu.mem.w32(creature + 0x48, vtable)
                emu.mem.w32(vtable + 0xC, dead_fn)
                emu.mem.w32(0x50388C, table)
                emu.mem.w16(R.LIVE_COUNT, count)
                emu.follow = set()
                emu.default_ret = 0
                kind, new_count = R.save_wave_visit(flags, state, count)
                emu.call(R.SAVE_WAVE_VISIT, creature)
                assert emu.mem.u16(R.LIVE_COUNT) == new_count
                assert emu.mem.u32(table + 4 * count) == (creature if kind == 'save' else 0)
                assert emu.mem.u8(creature + 0x231) == (0xFF if kind == 'save' else 0)
                targets = [call.target for call in emu.calls]
                assert targets == ({'skip': [], 'save': [0x14EF48],
                                    'destroy': [dead_fn]}[kind]), (flags, state, targets, kind)
                checked += 1
    return checked


def test_shutdown(path):
    checked = 0
    for found in (0, 1):
        for spawn_ptr, monster_ptr in ((0, 0), (0x100001, 0x100002)):
            emu = EE(path)
            emu.follow = set()
            emu.default_ret = 0
            emu.stub(0x19E5E8, ret=found)
            for address, value in ((0x503888, spawn_ptr), (0x50388C, monster_ptr),
                                   (0x503890, 3), (0x41B500, 4), (0x41B4FC, 5)):
                emu.mem.w32(address, value)
            expected_calls, expected_writes = R.shutdown(found, spawn_ptr, monster_ptr)
            emu.call(R.SHUTDOWN)
            actual_calls = [(call.target, call.args[0] & M32) for call in emu.calls]
            assert actual_calls == expected_calls, (actual_calls, expected_calls)
            assert writes(emu, set(expected_writes)) == expected_writes
            if not found:
                assert not emu.writes
            checked += 1
    return checked


def test_player_record(path, rng):
    """Exercise the confirm branch with four independent saved player records."""
    emu = D.boot(path)
    D.modes(emu, mode_b=1, players=4)
    for address, value in ((D.INTRO, 0xFFFF), (D.INTER, 0), (D.ENDF, 1),
                           (D.FADE_W, ONE), (D.FRAME, 1), (D.PAUSED, 0),
                           (D.CONFIRM, 0x100), (D.CANCEL, 0),
                           (D.PAD0 + 0xC, 0x100)):
        (emu.mem.w16 if address in (D.INTRO, D.INTER) else emu.mem.w32)(address, value)
    saved = []
    for slot in range(4):
        record = R.PLAYER_RECORD_BASE + slot * R.PLAYER_RECORD_SIZE
        emu.mem.write(record, rng.randbytes(R.PLAYER_RECORD_SIZE))
        emu.mem.w32(record + 0xAC, ZERO)
        D.put_slot(emu, slot, 0, 0xFFFF, 0, ZERO)
        emu.mem.w16(D.COUNTDOWN + 2 * slot, 0)
        block = emu.alloc(R.PLAYER_RECORD_SIZE)
        data = rng.randbytes(R.PLAYER_RECORD_SIZE)
        emu.mem.write(block, data)
        saved.append((block, data))
    emu.follow = set()
    emu.default_ret = 0
    emu.stub(D.ACTIVE, ret=1)
    emu.stub(0x21837C, function=lambda e: saved[e.r[4]][0])
    emu.stub(R.SHUTDOWN, ret=0)
    emu.stub(D.PICKER, ret=0x503798)
    emu.stub(D.STRCPY, ret=0)
    emu.call(D.RUN)
    slots = [call.args[0] & M32 for call in emu.calls if call.target == 0x21837C]
    assert slots == list(range(4)), slots
    for slot, (_block, data) in enumerate(saved):
        record = R.PLAYER_RECORD_BASE + slot * R.PLAYER_RECORD_SIZE
        assert emu.mem.read(record, R.PLAYER_RECORD_SIZE) == R.restore_saved_player_record(data)
    return 4


def test_player_respawn(path, seed):
    checked = 0
    for local in (0, 1):
        for network in (0, 1):
            for pvp_a in (0, 1):
                for placement in ((-1, -1), (2, 3)):
                    emu = EE(path)
                    old = emu.alloc(0x590)
                    new = emu.alloc(0x590)
                    pos = emu.alloc(0x10)
                    vtable = emu.alloc(0x20)
                    record = R.PLAYER_RECORD_BASE
                    emu.mem.w32(old + 0x48, vtable)
                    emu.mem.w32(vtable + 0xC, 0xF00004)
                    emu.mem.w32(record + 0x43D8, old)
                    emu.mem.w32(record + 0xB0, float_to_raw(100.0))
                    emu.mem.w32(record + 0xAC, 0)
                    emu.mem.w32(D.MODE_A, pvp_a)
                    emu.mem.w32(D.MODE_B, 1)
                    emu.mem.w32(D.NUM, 1)
                    emu.mem.w8(D.NET, network)
                    emu.mem.w32(D.SEED, seed)
                    for j, value in enumerate((10.0, 20.0, 0.0)):
                        emu.mem.wf32(pos + 4 * j, value)
                    emu.follow = set()
                    emu.default_ret = 0
                    emu.stub(0x13E150, ret=local)
                    emu.stub(0x14FDB8, ret=new)
                    def ctor(e):
                        e.mem.w32(record + 0x43D8, new)
                        return new
                    emu.stub(0x1A1D28, function=ctor)
                    def find(e):
                        for j in range(3):
                            e.mem.w32(e.r[4] + 4 * j, e.mem.u32(e.r[5] + 4 * j))
                        return 1
                    emu.stub(0x14ACF8, function=find)
                    expected_calls, expected_stores, expected_find = R.player_respawn_body(
                        local, network, pvp_a, *placement, old, new,
                        # Read the fixture's authored death slot, not an ELF target.
                        float_to_raw(100.0), emu.mem.u32(vtable + 0xC))
                    emu.call(R.PLAYER_RESPAWN, 0, pos, 0, *placement)
                    targets = [call.target for call in emu.calls]
                    assert targets == expected_calls, (local, network, pvp_a, placement,
                                                       targets, expected_calls)
                    for address, value in expected_stores.items():
                        actual = emu.mem.u16(address) if address == 0x4F84A8 else \
                            emu.mem.u8(address) if address == 0x402797 else emu.mem.u32(address)
                        assert actual == value, (hex(address), actual, value)
                    finds = [call for call in emu.calls if call.target == 0x14ACF8]
                    assert len(finds) == (0 if expected_find is None else 1)
                    if finds:
                        assert (finds[0].args[2] & M32, finds[0].args[3] & M32) == expected_find
                    assert [call.args[0] & M32 for call in emu.calls
                            if call.target == 0x322954] == ([4] if local and network else [])
                    assert emu.mem.u32(D.SEED) == seed
                    checked += 1
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    if not os.path.isfile(args.elf):
        raise SystemExit('executable missing')
    rng = random.Random(args.seed)
    for name, fn in (('scaleStats', lambda: test_scale(args.elf, rng)),
                     ('empty-wave visit', lambda: test_empty_visit(args.elf)),
                     ('nextWave', lambda: test_next(args.elf)),
                     ('saved pointer record', lambda: test_saved_record(args.elf)),
                     ('saved player record', lambda: test_player_record(args.elf, rng)),
                     ('player_respawn', lambda: test_player_respawn(args.elf, args.seed)),
                     ('shutdown', lambda: test_shutdown(args.elf))):
        print('%s: %d matched' % (name, fn()))


if __name__ == '__main__':
    main()
