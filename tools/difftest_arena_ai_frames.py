#!/usr/bin/env python3
"""Run 256 original idle class-AI ticks per recipe-0 wave on disc terrain/clips.

The surrounding scheduler and player activity centre are authored. The class
run body, target scan, activity, and animation advance execute in ee_emu.
This is an idle reference comparison, not a natural fighting match.
"""
import argparse

import difftest_arena_modes as D
import probe_arena_match as P
import ref_arena_ai_frames as R
import ref_objects as O


FRAMES = 256
ACTIVE = 0x10C0F0
OBJ_ACTIVE = 0x14DB08
CAN_SEE_TARGET = 0x118D40
STEP_ANIM = 0x1162B0
ADVANCE = 0x16D748


def run(path, iso_path, seed):
    clips = P.recipe0_clips_from_disc(iso_path)
    world = P.recipe0_world_from_disc(iso_path)
    results = []
    for wave in range(3):
        emu, created = P.build_wave(path, wave, seed, real_creatures=True,
                                    world_data=world, clips=clips)
        emu.follow.update(set(P.RUN_STATES.values()) |
                          {P.PICK_TARGET, ACTIVE, OBJ_ACTIVE, CAN_SEE_TARGET})
        player = emu.arena_player
        D.bind_player(emu, 0, player)
        emu.mem.w8(O.G_ACTIVITY_COUNT, 1)
        for axis in range(3):
            emu.mem.w32(O.G_ACTIVITY_CENTERS + 4 * axis,
                        emu.mem.u32(player + 0x10 + 4 * axis))
        serials = {obj: emu.mem.u8(obj + 0x230) for _index, obj in created}
        positions = {obj: tuple(emu.mem.u32(obj + 0x10 + 4 * k) for k in range(3))
                     for _index, obj in created}
        links = {obj: [] for _index, obj in created}
        seed_before = emu.mem.u32(P.RA.SEED)
        calls_before = len(emu.calls)
        for frame in range(FRAMES):
            emu.mem.w32(D.FRAME, frame)
            for index, obj in created:
                emu.call(P.RUN_STATES[index], obj, max_steps=400_000_000)
                node = emu.mem.u32(obj + 0x234)
                got = bool(node)
                if got and (frame == 0 or not R.target_present(frame - 1, serials[obj], FRAMES)):
                    links[obj].append(frame)
                assert got == R.target_present(frame, serials[obj], FRAMES), (
                    wave, index, frame, serials[obj], got)
                if node:
                    assert emu.mem.u32(node + 0xC) == player
                assert emu.mem.u16(obj + 0x232) == 0
                assert tuple(emu.mem.u32(obj + 0x10 + 4 * k) for k in range(3)) == positions[obj]
            assert emu.mem.u32(P.RA.SEED) == seed_before
        for _index, obj in created:
            assert links[obj] == R.target_link_frames(serials[obj], FRAMES)
        segment = emu.calls[calls_before:]
        for target in (P.PICK_TARGET, ACTIVE, STEP_ANIM, ADVANCE):
            calls = [call for call in segment if call.target == target]
            assert len(calls) == FRAMES * len(created)
            assert all(not call.stubbed for call in calls)
        scans = [R.first_scan(serials[obj], FRAMES) for _index, obj in created]
        results.append((wave, [index for index, _obj in created], scans, seed_before))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('iso')
    parser.add_argument('--seed', type=int, choices=(20973, 7), required=True)
    args = parser.parse_args()
    for wave, classes, scans, shared in run(args.elf, args.iso, args.seed):
        print('PASS seed %d wave %d: classes %s, first target scans %s, '
              '256 ticks each, shared seed %#x' % (args.seed, wave, classes, scans, shared))


if __name__ == '__main__':
    main()
