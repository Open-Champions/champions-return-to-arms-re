#!/usr/bin/env python3
"""Probe original mode-B recipe-0 wave builders with one offline player.

The wave plan, ring placement, arena_spawnMonster, and stat scaling execute in
ee_emu. The world factory is a labelled synthetic service because the class
constructors require a separate object and resource fixture. This is a probe,
not a live match or a constructor comparison; no game bytes are saved.
"""
import argparse
from collections import Counter

import difftest_arena_modes as D
from ref_core import ZERO


FACTORY = 0x14F6C8
SCALE = 0x1185D8
ADD_SPELL = 0x11A838
VTABLES = {0: 0x50FE88, 1: 0x516E48, 3: 0x510260,
           4: 0x50FFD0, 25: 0x510F30}


class ConstructorBoundary(Exception):
    def __init__(self, index):
        super().__init__('class-table index %s at world_createObject' % index)
        self.index = index


def setup(path, wave, seed):
    emu = D.boot(path)
    D.modes(emu, mode_a=0, mode_b=1, network=0, seed=seed, players=1)
    player = D.put_obj(emu, 0x60)
    emu.mem.w32(player + 0x48, 0x511308)  # Player's already documented vtable
    D.bind_player(emu, 0, player)
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
    emu.stub(0x14F6C8, function=create)
    try:
        emu.call(D.START, 1)
    except ConstructorBoundary as boundary:
        return boundary.index, len(D.calls(emu, D.SPAWN))
    raise AssertionError('first spawn did not reach world_createObject')


def install_factory_fixture(emu):
    """Install the labelled factory fixture and return its created-object list.

    The fixture retains the original class vtable and gives scaling known HP,
    damage, armour and experience values. Slot 34 and slot 27, which need class
    resources, are recording stubs. The factory's class mapping was separately
    compared by difftest_monster_build.py for all 30 arena names.
    """
    created = []

    def find_spot(e):
        out, point, _range, _radius, ok = [e.r[k] & 0xFFFFFFFF for k in range(4, 9)]
        for j in range(3):
            e.mem.w32(out + 4 * j, e.mem.u32(point + 4 * j))
        e.mem.w8(ok, 1)
        return 0

    def create(e):
        index = class_index(e.mem, e.r[4] & 0xFFFFFFFF)
        if index not in VTABLES:
            raise ValueError('no fixture for class-table index %d' % index)
        obj = e.alloc(0x600)
        e.mem.w32(obj + 0x48, VTABLES[index])
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
        return obj

    emu.stub(0x14ACF8, function=find_spot)
    emu.stub(FACTORY, function=create)
    emu.stub(ADD_SPELL, ret=0)
    for table in VTABLES.values():
        for slot in (27, 34):
            emu.stub(emu.mem.u32(table + 8 * slot + 4), ret=0)
    return created


def build_wave(path, wave, seed):
    """Run the original wave builder through every spawn, with factory fixtures."""
    emu = setup(path, wave, seed)
    emu.follow = {D.STEP, D.SPAWN, 0x166630, 0x1666E0, 0x3B75D0, SCALE}
    created = install_factory_fixture(emu)
    emu.call(D.START, 1)
    indices = [i for i, _obj in created]
    assert indices == dry_wave(path, wave, seed), (wave, indices)
    assert len(D.calls(emu, SCALE)) == len(created), (wave, len(created))
    return emu, created


def run_match(path, seed, attacked, max_frames=2400):
    """Run original arena_runTask and nextWave on an authored object fixture.

    The player attack is a scripted lethal outcome after an intro, because the
    fixture has no class constructor, AI tick, collision, or damage simulation.
    The world walk is an authored service over those fixture objects. This
    establishes the arena flow's next boundary, not combat or a live match.
    """
    emu = setup(path, 0, seed)
    emu.follow = {D.TICK, D.NEXT, D.START, D.STEP, D.SPAWN, 0x3063FC,
                  0x166630, 0x1666E0, 0x3B75D0, SCALE}
    created = install_factory_fixture(emu)
    emu.mem.w32(D.PLAYERS + 0xAC, 0x41A00000)
    emu.mem.w32(D.ENDF, 0)
    emu.mem.w32(D.BUDGET, 100)
    emu.mem.w16(D.INTER, 0)
    emu.stub(D.END, ret=0)

    def walk(e):
        callback = e.r[4] & 0xFFFFFFFF
        if callback in (0x3069E8, 0x306A28):
            alive = sum(bool(e.mem.u32(obj + 0xC) & 0x20) and
                        e.mem.s16(obj + 0x312) >= 0 for _index, obj in created)
            e.mem.w16(0x8E733E, alive)
        return 0

    emu.stub(D.WALK, function=walk)
    emu.call(D.START, 1)
    waves = [(0, len(created))]
    killed_waves = set()
    last_wave = 0
    for frame in range(max_frames):
        emu.mem.w32(D.FRAME, frame)
        wave = emu.mem.u16(D.WAVE)
        if attacked and wave not in killed_waves and emu.mem.u16(D.INTRO) == 0xFFFF:
            for _index, obj in created:
                if emu.mem.s16(obj + 0x312) >= 0:
                    emu.mem.w16(obj + 0x312, 0xFFFF)
            killed_waves.add(wave)
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
    else:
        assert waves == [(0, 2)], waves
    return emu, waves, frame + 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
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
        print('factory fixture: wave %d created %d objects; original spawn and scale calls %d/%d' %
              (wave, len(created), len(D.calls(emu, D.SPAWN)), len(D.calls(emu, SCALE))))
    for attacked in (False, True):
        emu, waves, frames = run_match(args.elf, args.seed, attacked)
        print('%s: %d run-task frames; wave/cumulative factory count %s; final wave %d, '
              'intro %d, intermission %d' %
              ('attacked fixture' if attacked else 'idle fixture', frames, waves,
               emu.mem.u16(D.WAVE), emu.mem.u16(D.INTRO), emu.mem.u16(D.INTER)))


if __name__ == '__main__':
    main()
