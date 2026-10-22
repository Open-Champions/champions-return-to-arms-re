#!/usr/bin/env python3
"""Probe original neutral Player_move and a spawned Gold_run; report prop boundary.

The arena fighting run remains scripted. The PhProp check deliberately stops
at its missing runtime model hull and reports the original interpreter fault;
it is not a successful PhProp-run comparison.
"""
import argparse

from ee_emu import MemoryFault
import difftest_arena_modes as D
import probe_arena_match as P
import ref_arena_services as R


PLAYER_MOVE = 0x1B4020
GOLD_RUN = 0x157B58
PHPROP_RUN = 0x155FCC
FRAMES = 200


def run(path, seed):
    player_emu, _created = P.build_wave(path, 0, seed, real_creatures=True)
    P.install_player_tick(player_emu)
    player_emu.follow.add(PLAYER_MOVE)
    player = player_emu.arena_player
    D.bind_player(player_emu, 0, player)
    player_seed = player_emu.mem.u32(P.RA.SEED)
    calls_before = len(player_emu.calls)
    for frame in range(FRAMES):
        player_emu.mem.w32(D.FRAME, frame)
        player_emu.call(P.PLAYER_RUN, player, max_steps=400_000_000)
        assert player_emu.mem.u32(player + 0x58C) == 2
    moves = [call for call in player_emu.calls[calls_before:] if call.target == PLAYER_MOVE]
    assert len(moves) == FRAMES and all(not call.stubbed for call in moves)
    assert player_emu.mem.u32(P.RA.SEED) == R.neutral_player_seed(player_seed, FRAMES)

    emu, waves, frames = P.run_match(path, seed, True, fighting=True, real_creatures=True)
    assert waves[:3] == [(0, 2), (1, 5), (2, 9)] and frames == 1688
    gold = next((block for size, block in emu.loot if size == 0xC0), None)
    assert gold is not None
    before = emu.mem.u8(gold + 0x4C)
    gold_seed = emu.mem.u32(P.RA.SEED)
    emu.follow.add(GOLD_RUN)
    emu.call(GOLD_RUN, gold, max_steps=400_000_000)
    ended = bool(emu.mem.u16(gold + 0x5E) & 0x80)
    assert emu.mem.u8(gold + 0x4C) == R.gold_countdown(before, ended)
    assert emu.mem.u32(P.RA.SEED) == gold_seed

    prop = emu.other_blocks[0][2]
    emu.follow.add(PHPROP_RUN)
    try:
        emu.call(PHPROP_RUN, prop, max_steps=400_000_000)
    except MemoryFault as fault:
        assert 'unmapped address 0x00000000' in str(fault) and 'pc 0x001561bc' in str(fault), fault
        boundary = str(fault)
    else:
        raise AssertionError('expected missing-hull boundary to be reported')
    return (seed, player_seed, before, emu.mem.u8(gold + 0x4C), gold_seed, boundary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, choices=(20973, 7), required=True)
    args = parser.parse_args()
    seed, player_seed, before, after, gold_seed, boundary = run(args.elf, args.seed)
    print('PASS seed %d: %d original neutral Player_move ticks, seed %#x; Gold_run '
          'countdown %d -> %d, seed %#x' % (seed, FRAMES, player_seed, before, after, gold_seed))
    print('BOUNDARY seed %d: original PhProp_run: %s' % (seed, boundary))


if __name__ == '__main__':
    main()
