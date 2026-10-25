#!/usr/bin/env python3
"""Compare original world walk and saved-creature reuse on recipe-0 wave 1.

The three class objects are constructed by the original executable. Their
death flags are authored to reproduce round 7's observed 0x612b boundary;
this is a bounded lifecycle transition, not natural death animation or AI.
"""
import argparse

import difftest_arena_modes as D
import probe_arena_match as P
import ref_arena_lifecycle as R
import ref_arena_match_core as MC


def run(path, seed):
    emu, created = P.build_wave(path, 1, seed, real_creatures=True)
    assert [index for index, _ptr in created] == [3, 3, 1]
    saved = created[0][1]
    table = emu.alloc(0x100)
    emu.mem.w32(0x50388C, table)
    for _index, ptr in created:
        emu.mem.w32(ptr + 0xC, 0x612B if ptr == saved else 0x6129)
    objects = [(ptr, emu.mem.u32(ptr + 0xC), emu.mem.u16(ptr + 0x312))
               for _index, ptr in created]
    emu.follow.update({D.WALK, MC.EMPTY_WAVE_VISIT, MC.SAVE_WAVE_VISIT})
    empty_seen, save_seen = [], []
    emu.hook(MC.EMPTY_WAVE_VISIT, lambda e: empty_seen.append(e.r[4] & 0xFFFFFFFF))
    emu.hook(MC.SAVE_WAVE_VISIT, lambda e: save_seen.append(e.r[4] & 0xFFFFFFFF))
    before_walk = emu.mem.u32(P.RA.SEED)
    emu.mem.w16(MC.LIVE_COUNT, 0)
    emu.call(D.WALK, MC.EMPTY_WAVE_VISIT, max_steps=400_000_000)
    assert set(ptr for _index, ptr in created).issubset(empty_seen)
    assert emu.mem.u16(MC.LIVE_COUNT) == R.empty_count(objects) == 0
    emu.mem.w16(MC.LIVE_COUNT, 0)
    destroy_targets = {ptr: emu.mem.u32(emu.mem.u32(ptr + 0x48) + 0xC)
                       for _index, ptr in created if ptr != saved}
    calls_before_save = len(emu.calls)
    emu.call(D.WALK, MC.SAVE_WAVE_VISIT, max_steps=400_000_000)
    assert set(ptr for _index, ptr in created).issubset(save_seen)
    actions = R.save_actions(objects)
    assert sorted(action for _ptr, action in actions) == ['destroy', 'destroy', 'save']
    assert emu.mem.u16(MC.LIVE_COUNT) == 1
    assert emu.mem.u32(table) == saved
    assert emu.mem.u8(saved + 0x231) == 0xFF
    for ptr, target in destroy_targets.items():
        assert any(call.target == target and call.args[0] & 0xFFFFFFFF == ptr
                   for call in emu.calls[calls_before_save:])
    assert emu.mem.u32(P.RA.SEED) == before_walk

    # arena_prepareWave 0x3063fc copies this count to 0x8e7340 before startWave.
    emu.mem.w16(D.SAVED, emu.mem.u16(MC.LIVE_COUNT))
    before_start = emu.mem.u32(P.RA.SEED)
    spots_before = len(emu.free_spot_calls)
    factories_before = len(D.calls(emu, P.WORLD_CREATE))
    ring_entries, spawn_entries = [], []
    emu.hook(D.STEP, lambda e: ring_entries.append(e.mem.u32(P.RA.SEED)))
    emu.hook(D.SPAWN, lambda e: spawn_entries.append(
        (e.r[4] & 0xFFFFFFFF, e.r[5] & 0xFFFFFFFF, e.mem.u32(P.RA.SEED),
         e.mem.u32(D.ANGLE_W), e.mem.u16(D.ANGLE_H))))
    emu.call(D.START, 1, max_steps=400_000_000)
    assert emu.mem.u16(D.WAVE) == 2
    assert len(created) == 3 and len(D.calls(emu, P.WORLD_CREATE)) == factories_before
    assert len(ring_entries) == len(spawn_entries) == 1
    ring_seed, angle, draw = R.reuse_ring(ring_entries[0], 1)
    assert spawn_entries == [(0, saved, ring_seed, angle, draw)], spawn_entries
    spots = emu.free_spot_calls[spots_before:]
    assert len(spots) == 2 and all(call['ok'] for call in spots)
    assert emu.mem.u32(P.RA.SEED) == R.reuse_seed(before_start, spots[0]['draws'], spots[1]['draws'])
    assert any(call.target == 0x14F028 and call.args[0] & 0xFFFFFFFF == saved
               for call in emu.calls)
    return dict(seed=seed, wave=emu.mem.u16(D.WAVE), saved=emu.mem.u16(D.SAVED),
                seed_before=before_start, seed_after=emu.mem.u32(P.RA.SEED),
                spot_draws=[call['draws'] for call in spots],
                placement=tuple(emu.mem.u32(saved + 0x10 + 4 * axis) for axis in range(3)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, choices=(20973, 7), required=True)
    args = parser.parse_args()
    result = run(args.elf, args.seed)
    print('PASS seed %(seed)d: wave %(wave)d, saved %(saved)d, shared seed %(seed_before)#x -> '
          '%(seed_after)#x, spot draws %(spot_draws)s, placement %(placement)s' % result)


if __name__ == '__main__':
    main()
