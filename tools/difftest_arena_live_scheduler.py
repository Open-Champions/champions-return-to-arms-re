#!/usr/bin/env python3
"""Bounded mode-B scheduler/recipe executions; no combat or successful load claim.

Read private tables at runtime and print counts only. Factory, grid population,
player construction, UI, audio and level loader remain explicit fixture services.
Run with stdlib unittest preloaded to avoid tools/dis.py shadowing stdlib dis.
"""
import argparse

import difftest_arena_modes as D
import ref_arena_modes as R
from ref_core import TWO, from_int, s16

BEGIN = 0x304F5C
PRELOAD = 0x306440
FACTORY = 0x14F6C8
PREPARE = 0x3063FC
EMPTY = 0x3069E8
LIVE = 0x8E733E


def fixture(path, seed, network, players):
    e = D.boot(path)
    D.modes(e, mode_a=0, mode_b=1, network=network, players=players, seed=seed)
    e.follow = {D.START, D.STEP, D.NEXT, PREPARE, D.TICK, D.END,
                D.RANK, D.CMP, PRELOAD}
    # Explicit reduced services: populated grid/constructors/load/UI are absent.
    e.default_ret = 0
    e.stub(D.ACTIVE, ret=1)
    e.stub(D.NET_COUNT, ret=players)
    e.stub(D.WALK, ret=0)
    e.stub(D.SPAWN, ret=0)
    e.stub(FACTORY, ret=0)
    for slot in range(players):
        D.put_slot(e, slot, 0, 2, 0, TWO)
        e.mem.w32(D.PLAYERS + D.REC * slot + 0xAC, from_int(10))
        e.mem.w32(D.PLAYERS + D.REC * slot + 0xB0, from_int(10))
    return e


def tables(e):
    count = e.mem.u16(D.NREC)
    assert count > 0
    records = [bytes(e.mem.u8(D.RECIPES + 6 * i + j) for j in range(6))
               for i in range(count)]
    names = D.names(e, D.NAMES_B)
    classes = [e.mem.u32(D.CLASSES + i * 4)
               for i in range((D.RECIPES - D.CLASSES) // 4)]
    for record in records:
        groups = R.high_nibble(record[0])
        assert 2 <= groups <= 5
        assert 0 <= R.low_nibble(record[0]) < len(names)
        assert all(0 <= R._signed_byte(index) < len(classes)
                   and classes[index] != 0 for index in record[1:1 + groups])
    return records, names, classes


def run(path, seed, network, players):
    e = fixture(path, seed, network, players)
    records, names, classes = tables(e)
    n = len(records)
    total_spawns = total_preloads = level_requests = 0
    # Two complete recipe rotations. Each case reconstructs its current wave;
    # this is not a continuous match crossing a real level-load boundary.
    for wave in range(6 * n):
        e = fixture(path, seed, network, players)
        e.mem.w16(D.WAVE, wave - 1)
        e.mem.w16(D.LEFT, 3 - wave % 3)
        e.mem.w16(D.SAVED, 0)
        expected, expected_seed, steps = R.wave_plan(wave, players, n, records, seed)
        before = len(e.calls)
        if wave % 3 == 0:
            e.call(BEGIN)
            preloads = D.calls(e, FACTORY)
            rec = records[(wave // 3) % n]
            wanted = list(dict.fromkeys(rec[1:1 + R.high_nibble(rec[0])]))
            assert [c.args[0] for c in preloads] == [classes[i] for i in wanted]
            assert all(not c.stubbed for c in D.calls(e, PRELOAD))
            total_preloads += len(preloads)
        else:
            e.call(D.START, 1)
        assert e.mem.u16(D.WAVE) == wave
        assert e.mem.u16(D.LEFT) == 2 - wave % 3
        assert e.mem.u32(D.LEVEL) == R.monster_level(wave)
        assert e.mem.u32(D.SEED) == expected_seed
        assert [c.args[0] for c in D.calls(e, D.SPAWN)] == [classes[i] for i in expected]
        assert len(D.calls(e, D.STEP)) == len(steps)
        assert all(not c.stubbed for c in e.calls[before:]
                   if c.target in (D.START, D.STEP))
        total_spawns += len(expected)
        # Execute every intro visit and every intermission visit, including the
        # one-frame equality boundary; advancing frame is the driver's clock.
        frame = 1
        for _ in range(R.INTRO_FRAMES + 1):
            e.mem.w32(D.FRAME, frame)
            e.call(D.RUN)
            frame += 1
        assert s16(e.mem.u16(D.INTRO)) == -1
        assert e.mem.u16(D.INTER) == 0
        # At a non-128 boundary the deliberately empty walker is not consulted.
        e.mem.w32(D.FRAME, 255)
        before = len(D.calls(e, D.WALK))
        e.call(D.RUN)
        assert len(D.calls(e, D.WALK)) == before and e.mem.u16(D.INTER) == 0
        e.mem.w32(D.FRAME, 256)
        before_end = len(D.calls(e, D.END))
        e.call(D.RUN)
        assert e.mem.u16(D.INTER) == 1 and e.mem.u32(D.ENDF) == 0
        assert len(D.calls(e, D.END)) == before_end + 1
        assert not D.calls(e, D.END)[-1].stubbed
        assert D.calls(e, D.WALK)[-1].args[0] == EMPTY
        before_next = len(D.calls(e, D.NEXT))
        before_copy = len(D.calls(e, D.STRCPY))
        limit = R.intermission_limit(network)
        for tick in range(1, limit):
            e.mem.w32(D.FRAME, 256 + tick)
            e.call(D.RUN)
        assert e.mem.u16(D.INTER) == limit
        assert len(D.calls(e, D.NEXT)) == before_next
        assert len(D.calls(e, D.STRCPY)) == before_copy
        e.mem.w32(D.FRAME, 256 + limit)
        e.call(D.RUN)
        if wave % 3 == 2:
            copies = D.calls(e, D.STRCPY)[before_copy:]
            assert len(copies) == 1
            index = R.level_record_index(wave, n)
            assert copies[0].args[:2] == (D.PENDING, names[R.low_nibble(records[index][0])])
            assert e.mem.s8(D.PENDING + 0x50) == -1
            assert len(D.calls(e, D.NEXT)) == before_next
            assert e.mem.u16(D.WAVE) == wave
            level_requests += 1
        else:
            calls = D.calls(e, D.NEXT)[before_next:]
            assert len(calls) == 1 and calls[0].args[0] == 1 and not calls[0].stubbed
            assert e.mem.u16(D.WAVE) == wave + 1
            assert len(D.calls(e, D.STRCPY)) == before_copy
        assert e.mem.u32(D.ENDF) == 0 and e.mem.u32(D.MODE_B) == 1
        assert e.mem.u32(D.EXIT) == 0
    return dict(waves=6*n, recipes=n, names=len(names), spawn_requests=total_spawns,
                preload_requests=total_preloads, level_requests=level_requests)


def occupied_control(path, seed):
    e = fixture(path, seed, 0, 1)
    e.mem.w16(D.INTRO, 0xFFFF)
    e.mem.w16(D.INTER, 0)
    e.mem.w32(D.ENDF, 0)
    e.mem.w32(D.FRAME, 128)
    # Mode B must ignore even the largest positive kill score/low PvP limit.
    D.put_slot(e, 0, 0x7FFF, 2, 2, TWO)
    e.mem.w8(D.LIMIT, 1)
    def occupied(cpu):
        cpu.mem.w16(LIVE, 1)
        return 0
    e.stub(D.WALK, function=occupied)
    e.call(D.RUN)
    assert e.mem.u16(D.INTER) == 0 and not D.calls(e, D.END)
    assert e.mem.u32(D.ENDF) == 0
    e.stub(D.WALK, ret=0)
    e.mem.w32(D.FRAME, 256)
    e.call(D.RUN)
    assert e.mem.u16(D.INTER) == 1 and len(D.calls(e, D.END)) == 1
    assert e.mem.u32(D.ENDF) == 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf')
    p.add_argument('--seed', type=int, choices=(20973, 7), required=True)
    args = p.parse_args()
    occupied_control(args.elf, args.seed)
    for network in (0, 1):
        for players in range(1, 5):
            print('PASS seed=%d network=%d players=%d %s' %
                  (args.seed, network, players,
                   run(args.elf, args.seed, network, players)), flush=True)


if __name__ == '__main__':
    main()
