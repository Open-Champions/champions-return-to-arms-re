#!/usr/bin/env python3
"""Execute bounded arena enemy AI and melee paths against US v2.00.

Usage: PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_arena_match_combat.py
       local/SLUS_209.73 --seed 20973

The target is a player-shaped object behind a real target handle. Original
class run/set-state, hit-reach, damage-apply and Player_takeDamage bodies run.
Base activity, animation events, sight, weapon-holder, Creature_filterState
and world services have fixed answers. Rooted, stunned and cooldown rewrites
are unexercised. Orc run/set-state call lists are original-body regression pins
for seeds 20973 and 7. This is not a full Player tick or a live match.
"""
import argparse
import hashlib

from ee_emu import EE
import ref_arena_match_combat as R

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
PROCESS_DAMAGE = 0x110D30
SEED_SHARED = 0x404464
FRAME = 0x44FDCC


def fixture(path, kind, seed, state, with_player=True):
    run, set_state, table, definition, holder, holder_table = R.SPECS[kind]
    emu = EE(path)
    creature = emu.alloc(0x600)
    player = emu.alloc(0x590)
    target = emu.alloc(0x20)
    emu.mem.w32(target + 0xC, player)
    if with_player:
        emu.mem.w32(creature + 0x234, target)
    for offset, value in ((0x24, definition), (0x48, table),
                          (0xC, 0x20), (0x44, seed), (0x300, 10),
                          (0x228, 0x42C80000), (0x22C, 0x42C80000),
                          (0x478, 0)):
        emu.mem.w32(creature + offset, value)
    for offset, value in ((0xD0, 10), (0xD2, 20), (0xD4, 30),
                          (0x232, state), (0x312, 0)):
        emu.mem.w16(creature + offset, value)
    if holder:
        emu.mem.w32(creature + 0x50, creature + holder)
        emu.mem.w32(creature + holder, holder_table)
    emu.mem.w32(player + 0x48, 0x511308)
    emu.mem.w32(player + 0xC, 0x40)
    emu.mem.w32(player + 0x228, 0x42C80000)
    emu.mem.w32(player + 0x22C, 0x42C80000)
    emu.mem.w32(player + 0x58C, 2)  # neutral Player action state
    emu.mem.w32(0x4D8AF0 + 0xAC, 0x42C80000)  # 100 HP in player record
    emu.mem.w32(FRAME, 100)
    emu.mem.w32(SEED_SHARED, seed)
    emu.mem.write(0x41B721, b'arena\0')
    emu.default_ret = 0
    emu.follow = {R.RAND}
    emu.stub(R.FILTER, ret=0)
    emu.stub(0x10C0F0, ret=1)  # Creature_updateActive
    emu.stub(0x1162B0, ret=1)  # one melee animation event
    return emu, creature, player, run, set_state


def targets(emu):
    return tuple(call.target for call in emu.calls)


def check_orc_states(path, seed):
    count = 0
    for state in range(0x19):
        for mode in ('run', 'set'):
            emu, creature, _player, run, set_state = fixture(
                path, 'orc2', seed, state, with_player=False)
            emu.stub(0x1162B0, ret=0)  # neutral, no animation event
            emu.call(run if mode == 'run' else set_state,
                     creature, *((state,) if mode == 'set' else ()))
            want = R.orc_neutral_calls(mode, state)
            assert targets(emu) == want, (seed, mode, state, targets(emu), want)
            assert emu.mem.u16(creature + 0x232) == state, (seed, mode, state)
            count += 1
    return count


def check_chase(path, kind, seed, near):
    emu, creature, player, run, set_state = fixture(path, kind, seed, 3)
    emu.follow.add(set_state)
    emu.stub(0x118D40, ret=int(near))  # fixed answer to the range/arc tests
    emu.call(run, creature)
    request = [c for c in emu.calls if c.target == set_state]
    if not near:
        assert not request, (kind, seed, 'distant chase requests', request)
        assert 0x1143E8 in targets(emu), (kind, seed, 'move to player')
        assert emu.mem.u16(creature + 0x232) == R.chase_state(False)
        return 1
    assert len(request) == 1, (kind, seed, 'chase state requests', request)
    asked = request[0].args[1] & 0xFFFFFFFF
    assert asked == 6, (kind, seed, 'requested attack state', asked)
    actual = emu.mem.u16(creature + 0x232)
    if kind == 'scorpion':
        own = (seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
        want = 7 if (own >> 16) % 6 == 0 else 6
    else:
        want = R.chase_state(True)
    assert actual == want, (kind, seed, 'attack choice', actual, want)
    assert emu.mem.u32(creature + 0x234) != 0
    assert emu.mem.u32(player + 0xC) & 0x40
    return 1


def check_melee_hit(path, kind, seed):
    emu, creature, player, run, set_state = fixture(path, kind, seed, 6)
    emu.follow.update({set_state, R.HIT_REACH, R.DAMAGE_APPLY,
                       R.PLAYER_TAKE_DAMAGE, 0x3B8534})  # real level-name strcmp
    emu.call(run, creature)
    chain = R.melee_hit(kind, player, creature)
    for target, first_arg in chain:
        matching = [call for call in emu.calls if call.target == target]
        assert len(matching) == 1, (kind, seed, 'hit chain', hex(target), matching)
        assert matching[0].args[0] & 0xFFFFFFFF == first_arg, (kind, seed, hex(target))
    hit = next(call for call in emu.calls if call.target == R.HIT_REACH)
    assert tuple(arg & 0xFFFF for arg in hit.args[1:4]) == (10, 20, 30)
    # docs/gameplay.md §2.5 steps 9–10: zero armour leaves a 10..20 base roll.
    queued = emu.mem.f32(player + 0xC8)
    assert 10.0 <= queued <= 20.0, (kind, seed, 'queued melee damage', queued)
    assert emu.mem.u32(player + 0x2DC) & 8, (kind, seed, 'player damage flag')
    emu.follow.add(R.PLAYER_PROCESS_DAMAGE)
    emu.call(R.PLAYER_PROCESS_DAMAGE, player)
    hp = emu.mem.f32(0x4D8AF0 + 0xAC)
    assert hp == 100.0 - queued, (kind, seed, 'player HP', hp, queued)
    assert emu.mem.u32(player + 0xC8) == 0, (kind, seed, 'damage queue consumed')
    assert emu.mem.u16(creature + 0x232) == 3, (kind, seed, 'attack exit')
    return 1


def check_death(path, kind, seed):
    emu, creature, player, _run, set_state = fixture(path, kind, seed, 0)
    table = emu.mem.u32(creature + 0x48)
    take = emu.mem.u32(table + 8 * 2 + 4)
    want_take = R.ORC_TAKE_DAMAGE if kind == 'orc2' else R.CREATURE_TAKE_DAMAGE
    assert take == want_take, (kind, seed, 'takeDamage slot', hex(take))
    emu.follow.update({take, R.CREATURE_TAKE_DAMAGE,
                       PROCESS_DAMAGE, set_state})
    emu.call(take, creature, player, 1, fargs=(1000.0,))
    if kind == 'orc2':
        assert R.CREATURE_TAKE_DAMAGE in targets(emu), (seed, 'Orc tail call')
    emu.call(PROCESS_DAMAGE, creature, 0)
    assert emu.mem.u16(creature + 0x232) == 0x14, (kind, seed, 'death state')
    assert emu.mem.u32(creature + 0xC) & 8, (kind, seed, 'dead flag')
    assert 0x10BEB8 in targets(emu), (kind, seed, 'onDeath')
    return 1


def check_scorpion_sting(path, seed, difficulty):
    emu, creature, player, run, set_state = fixture(path, 'scorpion', seed, 7)
    emu.follow.update({set_state, R.HIT_REACH, R.DAMAGE_APPLY,
                       R.PLAYER_TAKE_DAMAGE, 0x3B8534})
    emu.mem.w32(0x4F719C, difficulty)
    emu.call(run, creature)
    want = R.scorpion_sting_damage(difficulty)
    assert (emu.mem.u16(creature + 0xD0), emu.mem.u16(creature + 0xD2)) == want
    for target, first_arg in R.melee_hit('scorpion', player, creature):
        matching = [call for call in emu.calls if call.target == target]
        assert len(matching) == 1 and matching[0].args[0] & 0xFFFFFFFF == first_arg
    assert emu.mem.u32(player + 0xC8) > 0, (seed, difficulty, 'queued sting damage')
    assert emu.mem.u32(player + 0x2DC) & 0x10004 == 0x10004
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    if args.seed not in (20973, 7):
        parser.error('regression call and chase pins are validated only for seeds 20973 and 7')
    with open(args.elf, 'rb') as source:
        assert hashlib.sha256(source.read()).hexdigest() == EXPECTED_SHA256
    count = check_orc_states(args.elf, args.seed)
    for kind in R.SPECS:
        count += check_chase(args.elf, kind, args.seed, False)
        count += check_chase(args.elf, kind, args.seed, True)
        count += check_melee_hit(args.elf, kind, args.seed)
        count += check_death(args.elf, kind, args.seed)
    for difficulty in (0, 2, 3):
        count += check_scorpion_sting(args.elf, args.seed, difficulty)
    print('%d Orc2 state, four-class chase, melee damage and death comparisons matched (seed %d)' %
          (count, args.seed))


if __name__ == '__main__':
    main()
