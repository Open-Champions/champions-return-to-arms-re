#!/usr/bin/env python3
"""Bounded post-intro recipe-0 engagement on the owner's disc, seeds 20973/7.

Original arena task, class AI, sight, terrain sweep, clips, player tick and damage
paths execute in ee_emu. No actors are ticked during the 181 intro-task visits:
SpellArena_run would need the full actor model/joint service at 0x1799c8. The
post-intro actor order and the controller input are authored. No wave kill is
authored; this is not a live match or a complete arena scheduler.
"""
import argparse
import math

import difftest_arena_modes as D
import difftest_player as DP
import probe_arena_match as P
import ref_arena_engagement as R
import ref_arena_match_core as MC
import ref_objects as O
import ref_player as RP
import ref_world as W


G_RUN_SPEED = 0x4F8418
PLAYER_MOVE = 0x1B4020
PLAYER_MELEE_HIT = 0x1B6A98
PLAYER_INIT_NEW = 0x1B1D70
PLAYER_RECALC_STATS = 0x1B6458
PLAYER_RECALC_DAMAGE = 0x1B7158
TERRAIN_SWEEP = 0x185A40
TERRAIN_HEIGHT_BELOW = 0x1834A8
TERRAIN_RAY = 0x18A5C0
WORLD_SLIDE = 0x14D238
WORLD_MOVE = 0x14D4B8
CREATURE_MOVE_SIMPLE = 0x1186D8
HIT_AT_REACH = 0x1196E8
DAMAGE_APPLY = 0x1E8230
LOCKS = (D.WORD890, D.LOCK_A, D.LOCK_B)


def f32_at(mem, address):
    return W.to_float(mem.u32(address))


def live_count(emu):
    """Original world walker and empty-wave callback on the current grid."""
    emu.unhook(D.WALK)
    emu.follow.update({D.WALK, MC.EMPTY_WAVE_VISIT})
    emu.mem.w16(MC.LIVE_COUNT, 0)
    emu.call(D.WALK, MC.EMPTY_WAVE_VISIT, max_steps=400_000_000)
    return emu.mem.u16(MC.LIVE_COUNT)


def prepare(elf, seed, world, clips, init_record=False):
    emu, creatures = P.build_wave(elf, 0, seed, real_creatures=True,
                                  world_data=world, clips=clips)
    P.install_player_tick(emu)
    emu.follow.update(set(P.RUN_STATES.values()) | {
        P.PICK_TARGET, 0x10C0F0, 0x14DB08, 0x10E658, 0x10C810,
        TERRAIN_RAY, 0x183248, WORLD_SLIDE, TERRAIN_SWEEP,
        TERRAIN_HEIGHT_BELOW, 0x183820, HIT_AT_REACH, DAMAGE_APPLY,
        P.PLAYER_TAKE_DAMAGE, P.PLAYER_PROCESS_DAMAGE, PLAYER_MOVE,
        PLAYER_MELEE_HIT, D.TICK, D.RESET, CREATURE_MOVE_SIMPLE,
        WORLD_MOVE, P.TAKE_DAMAGE, P.PROCESS_DAMAGE,
    })
    # arena_resetScores 0x307c80 is normally called by arena_begin, which the
    # isolated wave builder does not call. It sets the offline speed factor.
    emu.call(D.RESET)
    assert emu.mem.u32(D.PLAYERS + 0x4C20) == 0x3FE00000
    # game_clearLevel 0x1e4ff0 supplies this 1.0 before an arena session.
    emu.mem.w32(G_RUN_SPEED, 0x3F800000)
    player = emu.arena_player
    D.bind_player(emu, 0, player)
    emu.mem.w8(O.G_ACTIVITY_COUNT, 1)
    for axis in range(3):
        emu.mem.w32(O.G_ACTIVITY_CENTERS + 4 * axis,
                    emu.mem.u32(player + 0x10 + 4 * axis))
    # The task's prompt, next-wave and empty scan are not needed during intro.
    emu.stub(D.NEXT, ret=0)
    emu.stub(D.ACTIVE, ret=1)
    emu.stub(D.END, ret=0)
    emu.stub(D.SCAN, ret=0)
    emu.stub(D.WALK, ret=0)
    counter = 180
    seed_before = emu.mem.u32(P.RA.SEED)
    assert R.state_refused(1, 0, emu.mem.u32(D.WORD890), emu.mem.u32(D.ENDF))
    for frame in range(181):
        emu.mem.w32(D.FRAME, frame)
        emu.call(D.RUN, max_steps=400_000_000)
        counter, locks = R.intro_step(counter)
        assert emu.mem.u16(D.INTRO) == counter
        assert tuple(emu.mem.u32(address) for address in LOCKS) == locks
    assert not R.state_refused(1, 0, emu.mem.u32(D.WORD890), emu.mem.u32(D.ENDF))
    assert emu.mem.u32(P.RA.SEED) == seed_before
    if init_record:
        # The isolated wave builder has a zeroed record. The offline boot path
        # initializes it before arena entry; reproduce its class-0 defaults
        # with the original function, then rebuild unarmed stats and damage.
        name = emu.alloc(16)
        emu.mem.write(name, b'Arena\0')
        emu.follow.update({PLAYER_INIT_NEW, PLAYER_RECALC_STATS,
                           PLAYER_RECALC_DAMAGE})
        emu.mem.w32(emu.r[29] + 0x10, 0)  # ninth argument: normal character kind
        emu.mem.w32(emu.r[29] + 0x14, 0)  # tenth argument: team zero
        emu.call(PLAYER_INIT_NEW, 0, 0, name, 0, 0, 0, 0, 0,
                 max_steps=400_000_000)
        D.bind_player(emu, 0, player)
        emu.call(PLAYER_RECALC_STATS, 0, max_steps=400_000_000)
        emu.call(PLAYER_RECALC_DAMAGE, player, 0, 0,
                 max_steps=400_000_000)
        assert [emu.mem.u32(D.PLAYERS + off) for off in (0xCC, 0xD0, 0xD4)] == [28, 9, 10]
        # In the real boot sequence character creation precedes arena_begin.
        # Restore the arena's later offline speed override after this isolated
        # fixture initializes the record.
        emu.call(D.RESET)
        assert emu.mem.u32(D.PLAYERS + 0x4C20) == 0x3FE00000
    return emu, creatures, player


def creature_hit(elf, seed, world, clips):
    emu, creatures, player = prepare(elf, seed, world, clips)
    links = {obj: None for _, obj in creatures}
    serials = {obj: emu.mem.u8(obj + 0x230) for _, obj in creatures}
    first_hit = None
    amount = None
    hp_before = f32_at(emu.mem, D.PLAYERS + 0xAC)
    for frame in range(181, 450):
        emu.mem.w32(D.FRAME, frame)
        emu.call(P.PLAYER_RUN, player, max_steps=400_000_000)
        if first_hit is not None and frame == first_hit + 1:
            assert f32_at(emu.mem, D.PLAYERS + 0xAC) == R.health_after_pending(hp_before, amount)
            assert f32_at(emu.mem, player + 0xC8) == 0.0
            break
        for index, obj in creatures:
            calls_before = len(emu.calls)
            emu.call(P.RUN_STATES[index], obj, max_steps=400_000_000)
            if links[obj] is None and emu.mem.u32(obj + 0x234):
                links[obj] = frame
                assert frame == R.first_scan_from(181, serials[obj])
                assert emu.mem.u32(emu.mem.u32(obj + 0x234) + 0xC) == player
            segment = emu.calls[calls_before:]
            hits = [c for c in segment if c.target == P.PLAYER_TAKE_DAMAGE]
            if first_hit is None and hits:
                assert len(hits) == 1 and not hits[0].stubbed
                assert any(c.target == HIT_AT_REACH and not c.stubbed for c in segment)
                assert any(c.target == DAMAGE_APPLY and not c.stubbed for c in segment)
                first_hit = frame
                amount = W.to_float(hits[0].fargs[0] & 0xFFFFFFFF)
                assert amount > 0 and f32_at(emu.mem, player + 0xC8) == amount
                assert f32_at(emu.mem, D.PLAYERS + 0xAC) == hp_before
                assert emu.mem.u16(obj + 0x232) == 6
        if first_hit is not None:
            continue
    else:
        raise AssertionError('no natural creature hit and next-tick damage within bound')
    assert all(frame is not None for frame in links.values())
    assert live_count(emu) == 2
    assert emu.mem.u16(D.WAVE) == 0
    return dict(links=list(links.values()), attack=first_hit, processed=first_hit + 1,
                damage=amount, hp_before=hp_before,
                hp_after=f32_at(emu.mem, D.PLAYERS + 0xAC),
                seed=emu.mem.u32(P.RA.SEED), living=2)


def player_attack(elf, seed, world, clips):
    emu, creatures, player = prepare(elf, seed, world, clips, init_record=True)
    phase, turn_at, pressed = 'wait', None, None
    hit_frame = victim = None
    amount = None
    victim_hp_before = victim_hp_after = None
    for frame in range(181, 460):
        emu.mem.w32(D.FRAME, frame)
        px, py = (f32_at(emu.mem, player + 0x10), f32_at(emu.mem, player + 0x14))
        distance, nearest = min(
            (math.hypot(f32_at(emu.mem, obj + 0x10) - px,
                        f32_at(emu.mem, obj + 0x14) - py), obj)
            for _, obj in creatures)
        if phase == 'wait' and distance < 68:
            phase, turn_at = 'turn', frame
        press = 0
        lx = ly = 0.0
        if phase == 'turn':
            dx, dy = f32_at(emu.mem, nearest + 0x10) - px, f32_at(emu.mem, nearest + 0x14) - py
            facing = emu.mem.u16(player + 0x38) * 2 * math.pi / 65536
            dot = (dx * math.cos(facing) + dy * math.sin(facing)) / max(math.hypot(dx, dy), 1)
            if dot >= 0.6 or frame - turn_at >= 6:
                phase, pressed = 'press', frame
            else:
                # Normal controller stick: Player_move turns toward its angle.
                theta = math.atan2(dy, dx) + 0x41C2 * 2 * math.pi / 65536
                lx, ly = math.sin(theta) * 0.3, math.cos(theta) * 0.3
        if phase == 'press':
            press, phase = DP.BTN['attack'], 'swung'
        pad = RP.G_PADS
        emu.mem.w32(pad + 8, press)
        emu.mem.w32(pad + 0xC, press)
        emu.mem.w32(pad + 0x14, W.f32(lx))
        emu.mem.w32(pad + 0x18, W.f32(ly))
        hp_before = {obj: f32_at(emu.mem, obj + 0x228) for _, obj in creatures}
        calls_before = len(emu.calls)
        emu.call(P.PLAYER_RUN, player, max_steps=400_000_000)
        segment = emu.calls[calls_before:]
        melee = [c for c in segment if c.target == PLAYER_MELEE_HIT]
        if melee:
            assert len(melee) == 1 and not melee[0].stubbed
            hit_frame, victim = frame, melee[0].args[1] & 0xFFFFFFFF
            assert pressed is not None and hit_frame == R.unarmed_hit_frame(pressed)
            assert victim in {obj for _, obj in creatures}
            assert any(c.target == DAMAGE_APPLY and not c.stubbed for c in segment)
            taken = [c for c in segment if c.target == P.TAKE_DAMAGE]
            assert len(taken) == 1 and not taken[0].stubbed
            amount = W.to_float(taken[0].fargs[0] & 0xFFFFFFFF)
            assert amount > 0
            victim_hp_before = hp_before[victim]
            victim_hp_after = f32_at(emu.mem, victim + 0x228)
            assert math.isclose(victim_hp_after, R.health_after_pending(victim_hp_before, amount),
                                rel_tol=0, abs_tol=1e-5)
            assert f32_at(emu.mem, victim + 0xC8) == amount
            break
        for index, obj in creatures:
            emu.call(P.RUN_STATES[index], obj, max_steps=400_000_000)
    else:
        raise AssertionError('controller-driven Player_meleeHit did not run')
    emu.mem.w32(D.FRAME, hit_frame + 1)
    victim_index = next(index for index, obj in creatures if obj == victim)
    emu.call(P.RUN_STATES[victim_index], victim, max_steps=400_000_000)
    assert f32_at(emu.mem, victim + 0xC8) == 0.0
    assert f32_at(emu.mem, victim + 0x228) == victim_hp_after
    assert live_count(emu) == 2
    assert emu.mem.u16(D.WAVE) == 0
    return dict(turn=turn_at, press=pressed, hit=hit_frame, victim=victim,
                amount=amount, victim_hp_before=victim_hp_before,
                victim_hp_after=victim_hp_after,
                seed=emu.mem.u32(P.RA.SEED), living=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('iso')
    parser.add_argument('--seed', type=int, choices=(20973, 7), required=True)
    args = parser.parse_args()
    world = P.recipe0_world_from_disc(args.iso)
    clips = P.recipe0_clips_from_disc(args.iso)
    monster = creature_hit(args.elf, args.seed, world, clips)
    player = player_attack(args.elf, args.seed, world, clips)
    print('PASS seed %d: intro locks 181 ticks; links %s; creature hit frame %d, '
          'pending %.1f, player HP %.1f -> %.1f on frame %d; living %d, wave 0; seed %#x'
          % (args.seed, monster['links'], monster['attack'], monster['damage'],
             monster['hp_before'], monster['hp_after'], monster['processed'],
             monster['living'], monster['seed']))
    print('PASS seed %d: player stick frame %d, press %d, melee hit %d, victim %#x, '
          'damage %.1f, goblin HP %.1f -> %.1f, pending cleared next tick; '
          'living %d, wave 0; seed %#x'
          % (args.seed, player['turn'], player['press'], player['hit'], player['victim'],
             player['amount'], player['victim_hp_before'], player['victim_hp_after'],
             player['living'], player['seed']))


if __name__ == '__main__':
    main()
