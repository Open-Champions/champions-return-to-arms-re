#!/usr/bin/env python3
"""Probe neutral Player_move, spawned Gold_run, and disc-backed PhProp_run.

The arena fighting run remains scripted; this compares a bounded first prop
tick and its original hull accessor on a model loaded from the owner's disc.
"""
import argparse

import difftest_arena_modes as D
import probe_arena_match as P
import ref_arena_services as R


PLAYER_MOVE = 0x1B4020
GOLD_RUN = 0x157B58
PHPROP_RUN = 0x155FCC
FRAMES = 200


def run(path, seed, iso_path):
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

    models = P.recipe0_models_from_disc(iso_path)
    emu, waves, frames = P.run_match(path, seed, True, fighting=True,
                                    real_creatures=True, disc_models=models)
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
    lump = P.CH.cstr(emu.mem.u8, prop + 0x54).decode('latin1').lower()
    name = P.CH.cstr(emu.mem.u8, prop + 0x64).decode('latin1').lower()
    key = (lump, name)
    model = emu.mem.u32(prop + 0x4C)
    assert model == emu.model_addresses[key], (key, model)
    mesh = next(i for i in range(64) if emu.mem.u64(prop + 0xE8) >> i & 1)
    offset, hull = R.model_hull(models[key], mesh)
    emu.follow.update({PHPROP_RUN, 0x179320})
    assert emu.call(0x179320, model, mesh) == model + offset
    assert emu.mem.read(model + offset, 24) == hull
    seed_before = emu.mem.u32(P.RA.SEED)
    emu.call(PHPROP_RUN, prop, max_steps=400_000_000)
    assert emu.mem.u32(P.RA.SEED) == seed_before
    assert any(call.target == 0x179320 and not call.stubbed for call in emu.calls)
    return (seed, player_seed, before, emu.mem.u8(gold + 0x4C), gold_seed,
            key, mesh, len(hull), seed_before)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--iso', required=True, help='owner disc image, read at run time')
    parser.add_argument('--seed', type=int, choices=(20973, 7), required=True)
    args = parser.parse_args()
    seed, player_seed, before, after, gold_seed, key, mesh, hull_len, prop_seed = run(
        args.elf, args.seed, args.iso)
    print('PASS seed %d: %d original neutral Player_move ticks, seed %#x; Gold_run '
          'countdown %d -> %d, seed %#x' % (seed, FRAMES, player_seed, before, after, gold_seed))
    print('PASS seed %d: original PhProp_run once; %s::%s mesh %d hull %d bytes, '
          'shared seed %#x' % (seed, key[0], key[1], mesh, hull_len, prop_seed))


if __name__ == '__main__':
    main()
