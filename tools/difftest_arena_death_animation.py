#!/usr/bin/env python3
"""Run original Goblin death clip and corpse ticks on the user's disc clips.

The lethal hit is authored. Per-frame activity and the scheduler are authored;
Goblin_run, Creature_stepAnim, anim_advance and Creature_deadUpdate execute in
ee_emu. Compare the held death track and deletion condition on seeds 20973/7.
"""
import argparse

import difftest_arena_modes as D
import probe_arena_match as P
import ref_arena_death_animation as R
import ref_anim as A


STEP_ANIM = 0x1162B0
ADVANCE = 0x16D748
DEAD_UPDATE = 0x1108A0
FRAMES = 151


def run(path, iso_path, seed):
    clips = P.recipe0_clips_from_disc(iso_path)
    emu, created = P.build_wave(path, 1, seed, real_creatures=True, clips=clips)
    goblin = created[0][1]
    emu.follow.update({P.TAKE_DAMAGE, P.PROCESS_DAMAGE, P.SET_STATES[3],
                       P.RUN_STATES[3], STEP_ANIM, ADVANCE, DEAD_UPDATE,
                       0x115EB8, P.PICK_TARGET, 0x10A9C0,
                       0x1195E0, 0x1195F0, 0x119608})
    emu.mem.w32(D.WORD890, 0)
    emu.stub(0x10C0F0, ret=1)  # authored active answer; bit 63 set below
    D.bind_player(emu, 0, emu.arena_player)
    calls_before_hit = len(emu.calls)
    emu.call(P.TAKE_DAMAGE, goblin, emu.arena_player, 1, fargs=(1000.0,),
             max_steps=400_000_000)
    emu.call(P.PROCESS_DAMAGE, goblin, 0, max_steps=400_000_000)
    assert any(call.target == 0x170BC8 and not call.stubbed
               for call in emu.calls[calls_before_hit:])  # anim_jumpTopToEnd
    assert emu.mem.u16(goblin + 0x232) == 0x14
    assert emu.mem.u32(goblin + 0xC) == 0x612B
    seed_after_hit = emu.mem.u32(P.RA.SEED)
    state = goblin + 0x114
    top = state + 8 + 0x20 * (emu.mem.u8(state + 4) - 1)
    clip_pointer = emu.mem.u32(top)
    clip_keys = [key for key, ptr in emu.clip_addresses.items() if ptr == clip_pointer]
    assert len(clip_keys) == 1
    clip_key = clip_keys[0]
    expected_time, ended_mask = R.ended_track(clips[clip_key], emu.mem.u16(top + 0x1C))
    assert emu.mem.u32(top + 0x18) == expected_time
    calls_before = len(emu.calls)
    for frame in range(FRAMES):
        emu.mem.w32(D.FRAME, frame)
        # In this bounded tick, the original activity service is answered active.
        emu.mem.w64(goblin + 0xA8, emu.mem.u64(goblin + 0xA8) | (1 << 63))
        emu.call(P.RUN_STATES[3], goblin, max_steps=400_000_000)
        count = emu.mem.u8(state + 4)
        assert count >= 1
        death_tracks = [state + 8 + 0x20 * slot for slot in range(count)
                        if emu.mem.u32(state + 8 + 0x20 * slot) == clip_pointer]
        assert len(death_tracks) == 1
        assert emu.mem.u32(death_tracks[0] + 0x18) == expected_time
        assert emu.mem.u16(state + 6) & ended_mask == ended_mask
        assert emu.mem.u32(goblin + 0xC) == 0x612B
        assert emu.mem.u32(P.RA.SEED) == seed_after_hit
    segment = emu.calls[calls_before:]
    for target in (STEP_ANIM, ADVANCE, DEAD_UPDATE):
        calls = [call for call in segment if call.target == target]
        assert len(calls) == FRAMES and all(not call.stubbed for call in calls), (hex(target), len(calls))
    dead_calls = [call for call in segment if call.target == DEAD_UPDATE]
    assert all(call.args[1] == 0 and call.args[3] == 0 for call in dead_calls)
    assert not R.corpse_delete_requested(emu.mem.u64(goblin + 0xA8),
                                         emu.mem.u8(state + 4), emu.mem.u16(state + 6), 0)
    return (seed, clip_key, A.Clip(clips[clip_key]).length, emu.mem.u8(state + 4), seed_after_hit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('iso')
    parser.add_argument('--seed', type=int, choices=(20973, 7), required=True)
    args = parser.parse_args()
    seed, key, length, tracks, final_seed = run(args.elf, args.iso, args.seed)
    print('PASS seed %d: %s length %d, %d original corpse ticks, %d track(s), '
          'flags 0x612b, seed %#x' % (seed, key, length, FRAMES, tracks, final_seed))


if __name__ == '__main__':
    main()
