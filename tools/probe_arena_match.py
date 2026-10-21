#!/usr/bin/env python3
"""Probe original mode-B recipe-0 wave builders with one offline player.

The wave plan, ring placement, arena_spawnMonster, world_createObject, class
factory, and stat scaling execute in ee_emu. The class constructors are
authored fixtures because their full object/resource fixture is separate.
The fighting variant executes class attacks and Player damage processing on
authored positions and fixed service answers. With --real-player the old player's
destructor, pool reuse, the whole Player constructor chain, original placement and
Player_run run for real (docs/spec/arena-player.md). This is not a live match; no
game bytes are saved.
"""
import argparse
from collections import Counter

import difftest_arena_modes as D
import difftest_player as DP
import ref_arena_player as RA
import ref_monster_build as B
import ref_player as RP
from ref_core import ZERO


WORLD_CREATE = 0x14F6C8
OBJECT_FACTORY = 0x159C94
FACTORY_POINTER = 0x5F76F4
POOL_NEW = 0x14FDB8
SCALE = 0x1185D8
ADD_SPELL = 0x11A838
VTABLES = {0: 0x50FE88, 1: 0x516E48, 3: 0x510260,
           4: 0x50FFD0, 25: 0x510F30}
CONSTRUCTORS = {0: 0x2A4D68, 1: 0x298418, 3: 0x26A624,
                4: 0x2A0954, 25: 0x244018}
SIZES = {0: 0x3D0, 1: 0x480, 3: 0x498, 4: 0x488, 25: 0x3D0}
DEFINITIONS = {0: 0x502238, 1: 0x501838, 3: 0x500298}
HOLDERS = {1: (0x3D0, 0x50CF40), 3: (0x3E8, 0x50CDA0)}
SET_STATES = {0: 0x2A55EC, 1: 0x29A6F4, 3: 0x26CCFC}
RUN_STATES = {0: 0x2A5068, 1: 0x298D18, 3: 0x26B27C}
TAKE_DAMAGE = 0x116638
PROCESS_DAMAGE = 0x110D30
PLAYER_TAKE_DAMAGE = 0x1B5330
PLAYER_PROCESS_DAMAGE = 0x1B2CC0
PLAYER_RUN = 0x1A5030
LIB = (0x3A5000, 0x3C0000)


class Follow(set):
    """A follow set that also runs the C library and software float range, as
    difftest_player does; arena_pickSpawnPoint needs it (arena-player.md section 3)."""

    def __contains__(self, target):
        return set.__contains__(self, target) or LIB[0] <= target < LIB[1]


def install_real_player(emu):
    """Run the slot loop's replacement for real: the old player's slot-1 destructor,
    pool_free / pool_new reuse of the same block, Player_ctor -> Creature_ctor ->
    GameObject_ctor, game_resetTimers4f84a8 and arena_pickSpawnPoint. Resource lookups
    answer with one authored part; the destructor's and constructor's other callees are
    recording stubs. Each replacement appends (block, seed before the constructor) to
    emu.replacements."""
    emu.follow = Follow(emu.follow)
    emu.follow.update({RA.PICK_SPAWN, RA.PLAYER_DTOR, RA.CTOR, RA.CREATURE_CTOR,
                       RA.GAMEOBJECT_CTOR, RA.RESET_TIMERS, 0x166798})
    part = emu.alloc(0x200)
    emu.stub(RA.RES_FIND, ret=part)
    emu.mem.write(D.PLAYERS + 0x20, b'\xff' * 4)
    emu.freed = []

    def pool_free(e):
        e.freed.append(e.r[4] & 0xFFFFFFFF)

    emu.stub(RA.POOL_FREE, function=pool_free)
    for slot in range(4):
        emu.mem.w32(RP.G_BTN_ATTACK + 4 * slot, DP.BTN['attack'])   # authored pad binding


def lcg_steps(before, after, limit=64):
    """How many documented shared draws turn ``before`` into ``after``."""
    for steps in range(limit + 1):
        if before == after:
            return steps
        before = RA.lcg(before)[0]
    raise AssertionError('seed moved by more than %d draws' % limit)


PICK_ATTACK_ANIM = 0x1BBA88


def install_player_tick(emu):
    """Player_run, the helpers its executed model covers, and Player_pickAttackAnim (one
    shared draw per combo swing, player-tick.md 9.10 and 10) run for real. Player_move
    stays a recording stub: its only shared draw is on entering water
    (combat-movement.md 3), which this dry fixture never answers."""
    emu.follow.update(set(DP.REAL_HELPERS.values()) | DP.REAL_OTHER | {PLAYER_RUN, PICK_ATTACK_ANIM})


class ConstructorBoundary(Exception):
    def __init__(self, index):
        super().__init__('class-table index %s at world_createObject' % index)
        self.index = index


def setup(path, wave, seed):
    emu = D.boot(path)
    D.modes(emu, mode_a=0, mode_b=1, network=0, seed=seed, players=1)
    player = emu.alloc(0x590)
    emu.mem.w32(player + 0xC, 0x40)
    emu.mem.w32(player + 0x3C8, 0)
    emu.mem.w32(player + 0x58C, 2)
    emu.mem.w32(player + 0x48, 0x511308)  # Player's already documented vtable
    D.bind_player(emu, 0, player)
    emu.arena_player = player
    D.put_slot(emu, 0, 0, 2, 2, 0x40000000)
    emu.mem.w32(D.PLAYERS + 0xAC, 0x41A00000)
    D.put_points(emu, [(ZERO, ZERO, ZERO, 0)])
    emu.mem.w16(D.WAVE, (wave - 1) & 0xFFFF)
    emu.mem.w16(D.LEFT, 3)
    emu.mem.w16(D.SAVED, 0)
    emu.default_ret = 0
    emu.stub(D.NET_COUNT, ret=1)
    emu.stub(D.ACTIVE, ret=1)
    return emu


def class_index(mem, pointer):
    for index in range(30):
        if mem.u32(D.CLASSES + 4 * index) == pointer:
            return index
    raise ValueError('spawned class pointer was not in the 30-entry table')


def dry_wave(path, wave, seed):
    emu = setup(path, wave, seed)
    emu.follow = {D.STEP}
    emu.stub(D.SPAWN, ret=0)
    emu.call(D.START, 1)
    indices = [class_index(emu.mem, call.args[0] & 0xFFFFFFFF)
               for call in D.calls(emu, D.SPAWN)]
    assert emu.mem.u16(D.WAVE) == wave
    return indices


def first_constructor_boundary(path, seed):
    emu = setup(path, 0, seed)
    emu.follow = {D.STEP, D.SPAWN, 0x166630, 0x1666E0, 0x3B75D0}

    def find_spot(e):
        out, point, _range, _radius, ok = [e.r[k] & 0xFFFFFFFF for k in range(4, 9)]
        for j in range(3):
            e.mem.w32(out + 4 * j, e.mem.u32(point + 4 * j))
        e.mem.w8(ok, 1)
        return 0

    def create(e):
        raise ConstructorBoundary(class_index(e.mem, e.r[4] & 0xFFFFFFFF))

    emu.stub(0x14ACF8, function=find_spot)
    emu.stub(WORLD_CREATE, function=create)
    try:
        emu.call(D.START, 1)
    except ConstructorBoundary as boundary:
        return boundary.index, len(D.calls(emu, D.SPAWN))
    raise AssertionError('first spawn did not reach world_createObject')


def install_factory_fixture(emu):
    """Follow original world_createObject/factory with constructor fixtures.

    The constructor fixture retains the original class vtable and gives scaling
    authored HP, damage, armour and experience values. Slot 34 and slot 27, which
    need class resources, are recording stubs. The factory row is also compared
    independently by difftest_monster_build.py for all 30 arena names.
    """
    created = []
    spells = []
    pending = {'index': None, 'block': None}

    def find_spot(e):
        out, point, _range, _radius, ok = [e.r[k] & 0xFFFFFFFF for k in range(4, 9)]
        for j in range(3):
            e.mem.w32(out + 4 * j, e.mem.u32(point + 4 * j))
        e.mem.w8(ok, 1)
        return 0

    def entering_world_create(e):
        pending['index'] = class_index(e.mem, e.r[4] & 0xFFFFFFFF)

    def pool_new(e):
        size = e.r[4] & 0xFFFFFFFF
        if size == 0x590 and e._fresh_call.site == 0x306030:
            if not getattr(e, 'freed', None):
                return 0  # without --real-player the replacement stays outside the fixture
            block = e.freed.pop()
            e.mem.write(block, bytes(0x590))       # pool_new zero-fills (object-system.md 2.1)
            e.arena_player = block
            e.replacements.append([block, e.mem.u32(RA.SEED)])
            return block
        if size == B.SPELL_SIZE and pending['index'] is None:
            block = e.alloc(size)
            spells.append((block, e.mem.u32(B.G_RAND_SEED)))
            return block
        if pending['index'] is None:
            raise ValueError('unexpected pool_new size 0x%x at 0x%x outside factory' %
                             (size, e._fresh_call.site))
        assert size == SIZES[pending['index']], (pending['index'], size)
        pending['block'] = e.alloc(size)
        return pending['block']

    def construct(e):
        index = pending['index']
        if index not in VTABLES:
            raise ValueError('no fixture for class-table index %d' % index)
        assert e._fresh_call.target == CONSTRUCTORS[index], index
        obj = e.r[4] & 0xFFFFFFFF
        assert obj == pending['block']
        e.mem.w32(obj + 0x48, VTABLES[index])
        if index in DEFINITIONS:
            e.mem.w32(obj + 0x24, DEFINITIONS[index])
        if index in HOLDERS:
            offset, table = HOLDERS[index]
            e.mem.w32(obj + 0x50, obj + offset)
            e.mem.w32(obj + offset, table)
        e.mem.w32(obj + 0xC, 0x20)
        e.mem.w16(obj + 0x312, 0)
        for field, value in ((0x228, 0x42C80000), (0x22C, 0x42C80000),
                             (0xD8, 0x41200000)):
            e.mem.w32(obj + field, value)
        for field, value in ((0xD0, 10), (0xD2, 20), (0xD4, 30), (0xE4, 40)):
            e.mem.w16(obj + field, value)
        for j in range(3):
            e.mem.w32(obj + 0x10 + 4 * j, e.mem.u32((e.r[5] & 0xFFFFFFFF) + 4 * j))
        e.mem.w16(obj + 0x38, e.r[6] & 0xFFFF)
        created.append((index, obj))
        pending['index'] = None
        pending['block'] = None
        return obj

    emu.mem.w32(FACTORY_POINTER, OBJECT_FACTORY)
    emu.follow.update({WORLD_CREATE, OBJECT_FACTORY, 0x159C20, 0x3B81A0})
    emu.stub(0x14ACF8, function=find_spot)
    emu.hook(WORLD_CREATE, entering_world_create)
    emu.stub(POOL_NEW, function=pool_new)
    for constructor in CONSTRUCTORS.values():
        emu.stub(constructor, function=construct)
    def add_spell(e):
        creature, spell = (e.r[4] & 0xFFFFFFFF, e.r[5] & 0xFFFFFFFF)
        assert spells and spell == spells[-1][0], (creature, spell, spells)
        block, old_seed = spells[-1]
        new_seed = (old_seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
        assert e.mem.u32(B.G_RAND_SEED) == new_seed
        assert all(e.mem.u32(block + offset) == 0 for offset in (0, 4, 8))
        assert e.mem.u32(block + 0xC) == creature
        assert e.mem.u32(block + 0x10) == new_seed >> 16
        assert e.mem.u32(block + 0x14) == B.VT_SPELL_ARENA
        return 0

    emu.stub(ADD_SPELL, function=add_spell)
    for table in VTABLES.values():
        for slot in (27, 34):
            emu.stub(emu.mem.u32(table + 8 * slot + 4), ret=0)
    return created


def build_wave(path, wave, seed, real_player=False):
    """Run the original wave builder through every spawn, with factory fixtures."""
    emu = setup(path, wave, seed)
    emu.follow = {D.STEP, D.SPAWN, 0x166630, 0x1666E0, 0x3B75D0, SCALE}
    emu.replacements = []
    if real_player:
        install_real_player(emu)
    created = install_factory_fixture(emu)
    emu.call(D.START, 1)
    indices = [i for i, _obj in created]
    assert indices == dry_wave(path, wave, seed), (wave, indices)
    assert len(D.calls(emu, SCALE)) == len(created), (wave, len(created))
    assert len(D.calls(emu, WORLD_CREATE)) == len(created)
    assert len(D.calls(emu, OBJECT_FACTORY)) == len(created)
    return emu, created


def run_match(path, seed, attacked, max_frames=2400, fighting=False,
              real_player=False):
    """Run original arena_runTask and nextWave on an authored object fixture.

    The driver injects a lethal player hit after each intro. Original base
    damage processing and the class death set-state execute on the fixture.
    The fighting variant first executes two class AI ticks per creature, with
    a close player at each creature's authored position, then ticks Player
    damage processing. It does not model input or world collision.
    The world walk is an authored service over those fixture objects. This
    establishes the arena flow's next boundary, not combat or a live match.
    """
    assert not fighting or attacked
    emu = setup(path, 0, seed)
    emu.follow = {D.TICK, D.NEXT, D.START, D.STEP, D.SPAWN, 0x3063FC,
                  0x166630, 0x1666E0, 0x3B75D0, SCALE}
    emu.replacements = []
    if real_player:
        install_real_player(emu)
        install_player_tick(emu)
    created = install_factory_fixture(emu)
    emu.player_ticks = emu.player_draws = 0
    emu.player_states = Counter()
    emu.mem.w32(D.PLAYERS + 0xAC, 0x41A00000)
    if fighting:
        emu.mem.w32(D.PLAYERS + 0xAC, 0x461C4000)  # 10,000 HP for three authored waves
        emu.mem.write(0x41B721, b'arena\0')
        emu.stub(0x10C0F0, ret=1)  # active creature
        emu.stub(0x1162B0, ret=1)  # melee animation event
        emu.stub(0x118D40, ret=1)  # close, visible player
        emu.follow.update(set(RUN_STATES.values()) |
                          {0x1196E8, 0x1E8230, PLAYER_TAKE_DAMAGE,
                           PLAYER_PROCESS_DAMAGE, 0x3B8534})
    emu.mem.w32(D.ENDF, 0)
    emu.mem.w32(D.BUDGET, 100)
    emu.mem.w16(D.INTER, 0)
    emu.stub(D.END, ret=0)

    def walk(e):
        callback = e.r[4] & 0xFFFFFFFF
        if callback in (0x3069E8, 0x306A28):
            alive = sum((e.mem.u32(obj + 0xC) & 0x68) == 0x20 and
                        e.mem.s16(obj + 0x312) >= 0 for _index, obj in created)
            e.mem.w16(0x8E733E, alive)
        return 0

    emu.stub(D.WALK, function=walk)
    if attacked:
        for set_state in SET_STATES.values():
            emu.unhook(set_state)
        emu.follow.update(set(SET_STATES.values()) |
                          {TAKE_DAMAGE, PROCESS_DAMAGE, 0x10A9C0,
                           0x1195E0, 0x1195F0, 0x119608})
        emu.mem.w32(D.WORD890, 0)
    emu.call(D.START, 1)
    waves = [(0, len(created))]
    killed_waves = set()
    combat_frames = {}
    hit_indices = []
    last_wave = 0
    for frame in range(max_frames):
        emu.mem.w32(D.FRAME, frame)
        wave = emu.mem.u16(D.WAVE)
        if fighting and wave not in killed_waves and emu.mem.u16(D.INTRO) == 0xFFFF:
            phase = combat_frames.get(wave, 0)
            if phase < 2:
                player = emu.arena_player
                D.bind_player(emu, 0, player)  # stand-in for the refused Player replacement
                for index, obj in created:
                    if (emu.mem.u32(obj + 0xC) & 0x68) != 0x20:
                        continue
                    if phase == 0:
                        node = emu.alloc(0x20)
                        emu.mem.w32(node + 0xC, player)
                        emu.mem.w32(obj + 0x234, node)
                        emu.call(SET_STATES[index], obj, 3)
                    for axis in range(3):
                        emu.mem.w32(player + 0x10 + 4 * axis,
                                    emu.mem.u32(obj + 0x10 + 4 * axis))
                    emu.call(RUN_STATES[index], obj)
                if phase == 1:
                    emu.call(PLAYER_PROCESS_DAMAGE, player)
                combat_frames[wave] = phase + 1
        if attacked and wave not in killed_waves and emu.mem.u16(D.INTRO) == 0xFFFF and \
                (not fighting or combat_frames.get(wave, 0) >= 2):
            player = emu.arena_player
            D.bind_player(emu, 0, player)
            for index, obj in created:
                if (emu.mem.u32(obj + 0xC) & 0x68) == 0x20:
                    emu.call(TAKE_DAMAGE, obj, player, 1, fargs=(1000.0,))
                    emu.call(PROCESS_DAMAGE, obj, 0)
                    assert emu.mem.u16(obj + 0x232) == 0x14
                    hit_indices.append(index)
            killed_waves.add(wave)
        if real_player:
            pad = RP.G_PADS
            press = DP.BTN['attack'] if fighting and frame % 30 == 0 else 0
            emu.mem.w32(pad + 8, press)
            emu.mem.w32(pad + 0xC, press)
            player = emu.mem.u32(D.PLAYERS + 0x43D8)
            assert player == emu.arena_player
            emu.player_states[emu.mem.u32(player + 0x58C)] += 1
            before = emu.mem.u32(RA.SEED)
            emu.call(PLAYER_RUN, player)
            emu.player_draws += lcg_steps(before, emu.mem.u32(RA.SEED))
            emu.player_ticks += 1
        emu.call(D.RUN)
        wave = emu.mem.u16(D.WAVE)
        if wave != last_wave:
            waves.append((wave, len(created)))
            last_wave = wave
            if wave == 2 and not attacked:
                break
        if wave == 2 and attacked and wave in killed_waves:
            break
    expected = [2, 3, 4]
    previous = 0
    for wave, cumulative in waves:
        if wave <= 2:
            made = cumulative - previous
            assert made == expected[wave], (wave, made)
            previous = cumulative
    if attacked:
        assert [wave for wave, _ in waves][:3] == [0, 1, 2], waves
        assert Counter(hit_indices) == {0: 1, 1: 2, 3: 6}, hit_indices
        if fighting:
            emu.fighting_player_hits = len(D.calls(emu, PLAYER_TAKE_DAMAGE))
            assert emu.fighting_player_hits == 9, emu.fighting_player_hits
            # docs/gameplay.md §2.5 steps 9–10: each of nine zero-armour hits
            # rolls within the authored 10..20 range. Exact HP is seed-specific.
            hp = emu.mem.f32(D.PLAYERS + 0xAC)
            assert 10000.0 - 20.0 * 9 <= hp <= 10000.0 - 10.0 * 9, hp
    else:
        assert waves == [(0, 2)], waves
    return emu, waves, frame + 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    parser.add_argument('--real-player', action='store_true',
                        help='real destructor, pool reuse, Player constructor chain, placement and Player_run')
    args = parser.parse_args()
    if args.real_player:
        return real_player_report(args.elf, args.seed)
    for wave in range(3):
        indices = dry_wave(args.elf, wave, args.seed)
        counts = Counter(indices)
        print('wave %d: %d spawn calls, indices %s' %
              (wave, len(indices), ', '.join('%d:%d' % pair for pair in sorted(counts.items()))))
    index, spawn_number = first_constructor_boundary(args.elf, args.seed)
    print('followed builder: wave 0 spawn %d reaches class-table index %d at world_createObject' %
          (spawn_number, index))
    for wave in range(3):
        emu, created = build_wave(args.elf, wave, args.seed)
        print('constructor fixtures: wave %d created %d objects; original factory/spawn/scale calls %d/%d/%d' %
              (wave, len(created), len(D.calls(emu, OBJECT_FACTORY)),
               len(D.calls(emu, D.SPAWN)), len(D.calls(emu, SCALE))))
    for attacked in (False, True):
        emu, waves, frames = run_match(args.elf, args.seed, attacked)
        print('%s: %d run-task frames; wave/cumulative factory count %s; final wave %d, '
              'intro %d, intermission %d' %
              ('attacked fixture' if attacked else 'idle fixture', frames, waves,
               emu.mem.u16(D.WAVE), emu.mem.u16(D.INTRO), emu.mem.u16(D.INTER)))
    emu, waves, frames = run_match(args.elf, args.seed, True, fighting=True)
    print('fighting fixture: %d frames; waves %s; Player_takeDamage calls %d; final player HP %.1f' %
          (frames, waves, emu.fighting_player_hits,
           emu.mem.f32(D.PLAYERS + 0xAC)))


def real_player_report(path, seed):
    """Recipe 0 (the first record), waves 0-2, idle and fighting, real Player."""
    for wave in range(3):
        emu, created = build_wave(path, wave, seed, real_player=True)
        (block, before), = emu.replacements
        print('wave %d builder: %d objects; player block %#x reused; ctor seed %#x -> spawn %s facing %#x'
              % (wave, len(created), block, before,
                 tuple('%#x' % emu.mem.u32(block + 0x3B4 + 4 * k) for k in range(3)),
                 emu.mem.u16(block + 0x38)))
    for label, attacked, fighting in (('idle', False, False), ('fighting', True, True)):
        emu, waves, frames = run_match(path, seed, attacked, fighting=fighting, real_player=True)
        print('%s: %d frames; waves %s; %d Player constructions, %d Player_run ticks (%d shared draws); '
              'states %s; final seed %#x; record HP %.1f'
              % (label, frames, waves, len(emu.replacements), emu.player_ticks, emu.player_draws,
                 dict(sorted(emu.player_states.items())), emu.mem.u32(RA.SEED),
                 emu.mem.f32(D.PLAYERS + 0xAC)))
        if fighting:
            print('    Player_takeDamage calls %d' % emu.fighting_player_hits)
    return 0


if __name__ == '__main__':
    main()
