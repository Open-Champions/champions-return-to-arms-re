#!/usr/bin/env python3
"""Bounded assisted arena kill, wave and end-task execution on v2.00 inputs.

The first part uses disc terrain/clips and controller input, then schedules
original Player_meleeHit directly when controller hits alone do not finish.
No creature HP, state, score or seed is written by the driver. The second part
constructs isolated score/end-task states; it is not a running results screen.
"""
import argparse
import math

import difftest_arena_engagement as A
import difftest_arena_modes as D
import difftest_player as DP
import probe_arena_match as P
import ref_arena_match_core as MC
import ref_arena_modes as R
import ref_player as RP
import ref_world as W


DROP = 0x10F2C8
GENERATE_DROPS = 0x100D54
ON_DEATH = 0x10BEB8


def run_kill_wave(elf, iso, seed):
    emu, created, player = A.prepare(
        elf, seed, P.recipe0_world_from_disc(iso),
        P.recipe0_clips_from_disc(iso), init_record=True)
    # The isolated player has no normal offline inventory/health setup. Keep
    # enough HP to observe both kills; this is an assisted player fixture.
    emu.mem.w32(D.PLAYERS + 0xAC, W.f32(10000.0))
    emu.mem.w32(D.PLAYERS + 0xB0, W.f32(10000.0))
    assert [index for index, _ in created] == [3, 3]
    prior_hp = {obj: A.f32_at(emu.mem, obj + 0x228) for _, obj in created}
    last_press = -100
    controller_hits, scheduled_hits, death_frames = [], [], {}
    death_calls = {}
    for frame in range(181, 2000):
        emu.mem.w32(D.FRAME, frame)
        px, py = [A.f32_at(emu.mem, player + address) for address in (0x10, 0x14)]
        live = [(index, obj) for index, obj in created
                if emu.mem.u16(obj + 0x232) != 0x14]
        assert live, 'no living Goblin before death assertion'
        distance, target = min(
            (math.hypot(A.f32_at(emu.mem, obj + 0x10) - px,
                        A.f32_at(emu.mem, obj + 0x14) - py), obj)
            for _index, obj in live)
        dx = A.f32_at(emu.mem, target + 0x10) - px
        dy = A.f32_at(emu.mem, target + 0x14) - py
        facing = emu.mem.u16(player + 0x38) * 2 * math.pi / 65536
        dot = (dx * math.cos(facing) + dy * math.sin(facing)) / max(math.hypot(dx, dy), 1)
        theta = math.atan2(dy, dx) + 0x41C2 * 2 * math.pi / 65536
        lx = math.sin(theta) * 0.7 if distance > 58 or dot < 0.6 else 0.0
        ly = math.cos(theta) * 0.7 if distance > 58 or dot < 0.6 else 0.0
        press = 0
        if distance < 65 and dot >= 0.6 and frame - last_press >= 36:
            press = DP.BTN['attack']
            last_press = frame
        pad = RP.G_PADS
        for offset, value in ((8, press), (0xC, press),
                              (0x14, W.f32(lx)), (0x18, W.f32(ly))):
            emu.mem.w32(pad + offset, value)
        calls_before = len(emu.calls)
        emu.call(P.PLAYER_RUN, player, max_steps=400_000_000)
        segment = emu.calls[calls_before:]
        for call in segment:
            if call.target == A.PLAYER_MELEE_HIT:
                assert not call.stubbed
                controller_hits.append((frame, call.args[1] & 0xFFFFFFFF))
        # After the first controller hits, this reduced fixture can cease
        # launching swings. Schedule the *original* melee body; it still
        # performs its target, collision, attack roll and damage decisions.
        if frame >= 940 and frame % 36 == 4:
            victim = min((A.f32_at(emu.mem, obj + 0x228), obj)
                         for _index, obj in live)[1]
            before = A.f32_at(emu.mem, victim + 0x228)
            calls_before = len(emu.calls)
            emu.call(A.PLAYER_MELEE_HIT, player, victim, max_steps=400_000_000)
            segment = emu.calls[calls_before:]
            assert any(call.target == A.DAMAGE_APPLY and not call.stubbed
                       for call in segment), 'scheduled melee bypassed damage_apply'
            after = A.f32_at(emu.mem, victim + 0x228)
            scheduled_hits.append((frame, victim, before, after))
        for index, obj in created:
            calls_before = len(emu.calls)
            emu.call(P.RUN_STATES[index], obj, max_steps=400_000_000)
            segment = emu.calls[calls_before:]
            hp = A.f32_at(emu.mem, obj + 0x228)
            assert hp <= prior_hp[obj] + 1e-4, 'Goblin HP increased'
            prior_hp[obj] = hp
            if emu.mem.u16(obj + 0x232) == 0x14 and obj not in death_frames:
                death_frames[obj] = frame
                assert hp <= 0 and emu.mem.u32(obj + 0xC) & 0x8
                death_calls[obj] = {
                    address: sum(c.target == address and not c.stubbed for c in segment)
                    for address in (P.PROCESS_DAMAGE, DROP, GENERATE_DROPS,
                                    ON_DEATH, D.ADDK)}
                assert all(death_calls[obj].values()), death_calls[obj]
        if len(death_frames) == 2:
            break
    assert len(death_frames) == 2 and controller_hits and scheduled_hits
    assert A.live_count(emu) == 0
    assert all(MC.empty_wave_visit(emu.mem.u32(obj + 0xC),
                                   emu.mem.u16(obj + 0x312), 0) is None
               for _index, obj in created[:2])
    assert D.read_slot(emu, 0)[0] == 2, 'arena_addKill did not credit two kills'
    assert emu.mem.u16(D.WAVE) == 0
    before_wave = len(created)
    emu.unhook(D.NEXT)
    emu.follow.update({D.NEXT, D.START, D.STEP, D.SPAWN, MC.PREPARE_WAVE})
    first_inter = None
    for task_frame in range(frame, frame + 600):
        emu.mem.w32(D.FRAME, task_frame)
        emu.call(D.RUN, max_steps=400_000_000)
        if first_inter is None and emu.mem.u16(D.INTER):
            first_inter = task_frame
            assert task_frame % 128 == 0
        if emu.mem.u16(D.WAVE) == 1:
            advance = task_frame
            break
    else:
        raise AssertionError('empty wave never advanced')
    assert advance == first_inter + R.INTERMISSION_OFFLINE
    assert R.intermission_done(R.INTERMISSION_OFFLINE, False)
    assert R.round_expired(emu.mem.u16(D.LEFT), False) == 'wave'
    assert emu.mem.u16(D.LEFT) == 1
    assert [index for index, _ in created[before_wave:]] == [3, 3, 1]
    assert D.read_slot(emu, 0)[:3] == (2, 2, 2)
    return dict(seed=seed, controller_hits=len(controller_hits),
                scheduled=len(scheduled_hits), deaths=sorted(death_frames.values()),
                death_calls=death_calls, first_inter=first_inter,
                advance=advance, created=len(created),
                loot=len(emu.loot), score=D.read_slot(emu, 0)[0])


def end_case(elf, mode_a, kills, lives, snapshot, hp, limit=5):
    emu = D.boot(elf)
    D.modes(emu, mode_a=mode_a, mode_b=1, seed=7, players=1)
    emu.mem.w16(D.INTRO, 0xFFFF)
    emu.mem.w16(D.INTER, 0)
    emu.mem.w32(D.ENDF, 0)
    emu.mem.w32(D.FRAME, 1)
    emu.mem.w8(D.LIMIT, limit)
    emu.mem.w32(D.BUDGET, 100)
    D.put_slot(emu, 0, kills, lives, snapshot, 0x40000000)
    emu.mem.w32(D.PLAYERS + 0xAC, W.f32(hp))
    emu.mem.w16(D.COUNTDOWN, 0)
    emu.follow = {D.TICK, D.END, D.RANK, D.CMP}
    emu.stub(D.ACTIVE, ret=1)
    emu.stub(D.SCAN, ret=0)
    emu.stub(D.WALK, ret=0)
    emu.stub(D.STRCPY, ret=0)
    emu.stub(D.CLOSE, ret=0)
    emu.stub(D.PICKER, ret=emu.mem.u32(D.NAMES_B))
    emu.stub(0x21837C, ret=0)
    emu.stub(0x13E5A0, ret=0)
    emu.stub(0x17365C, ret=0)
    emu.stub(0x2134E8, ret=0)
    emu.stub(D.NEXT, ret=0)
    emu.call(D.RUN, max_steps=5_000_000)
    return emu


def run_end_paths(elf):
    below = end_case(elf, 1, 4, 2, 2, 20)
    won = end_case(elf, 1, 5, 2, 2, 20)
    assert below.mem.u16(D.INTER) == 0 and not D.calls(below, D.END)
    assert won.mem.u16(D.INTER) == 1 and len(D.calls(won, D.END)) == 1
    assert not D.calls(won, D.END)[0].stubbed
    assert R.kill_limit_reached(5, 5) and not R.kill_limit_reached(4, 5)
    assert won.mem.u32(D.FADE_W) == 0 and won.mem.u8(D.RANK_B) == 0

    retry = end_case(elf, 0, 0, 0xFFFF, 2, 0)
    defeat = end_case(elf, 0, 0, 0xFFFF, 0, 0)
    assert [call.args[0] for call in D.calls(retry, D.NEXT)] == [0]
    assert retry.mem.u32(D.ENDF) == 0
    assert not R.still_in(True, -1, 0, 0)
    assert defeat.mem.u32(D.ENDF) == 1
    assert len(D.calls(defeat, D.END)) == 1 and not D.calls(defeat, D.END)[0].stubbed
    assert not D.calls(defeat, D.NEXT)

    # Full-fade result prompt: confirm requests the arena picker; cancel exits.
    confirm = end_case(elf, 0, 2, 0xFFFF, 0, 0)
    confirm.mem.w32(D.FADE_W, W.f32(1.0))
    confirm.mem.w32(D.CONFIRM, 0x100)
    confirm.mem.w32(D.PAD0 + 0xC, 0x100)
    saved = confirm.alloc(MC.PLAYER_RECORD_SIZE)
    confirm.mem.write(saved, bytes([0x5A]) * MC.PLAYER_RECORD_SIZE)
    confirm.stub(0x21837C, ret=saved)
    confirm.stub(0x304FB0, ret=0)
    confirm.call(D.RUN, max_steps=5_000_000)
    assert len(D.calls(confirm, 0x304FB0)) == 1
    assert len(D.calls(confirm, D.STRCPY)) == 1
    assert all(confirm.mem.u8(D.PLAYERS + offset) == 0x5A
               for offset in range(MC.PLAYER_RECORD_SIZE))
    assert confirm.mem.u32(D.MODE_B) == 1
    cancel = end_case(elf, 0, 2, 0xFFFF, 0, 0)
    cancel.mem.w32(D.FADE_W, W.f32(1.0))
    cancel.mem.w32(D.CANCEL, 0x100)
    cancel.mem.w32(D.PAD0 + 0xC, 0x100)
    cancel.call(D.RUN, max_steps=5_000_000)
    assert cancel.mem.u32(D.MODE_B) == 0
    assert cancel.mem.u32(D.EXIT) == 1
    assert not D.calls(cancel, D.STRCPY)
    return dict(win_limit=5, retry=[call.args[0] for call in D.calls(retry, D.NEXT)],
                confirm_shutdown=len(D.calls(confirm, 0x304FB0)),
                confirm_picker=len(D.calls(confirm, D.STRCPY)),
                cancel_exit=cancel.mem.u32(D.EXIT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('iso')
    parser.add_argument('--seed', type=int, choices=(20973, 7), required=True)
    args = parser.parse_args()
    kill = run_kill_wave(args.elf, args.iso, args.seed)
    end = run_end_paths(args.elf)
    print('PASS seed %d: controller hits %d, scheduled original melee %d, deaths %s, '
          'loot blocks %d, kills %d, intermission %d, wave 1 at %d, built %d'
          % (kill['seed'], kill['controller_hits'], kill['scheduled'],
             kill['deaths'], kill['loot'], kill['score'], kill['first_inter'],
             kill['advance'], kill['created']))
    print('PASS seed %d: end paths %s; death calls %s' %
          (args.seed, end, kill['death_calls']))


if __name__ == '__main__':
    main()
