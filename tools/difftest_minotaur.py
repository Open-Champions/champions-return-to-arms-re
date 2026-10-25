#!/usr/bin/env python3
"""Execute bounded Minotaur contracts; no game bytes are emitted or embedded.

python3 tools/difftest_minotaur.py /path/SLUS_209.73 --seed 20973

Class code executes in ee_emu. All un-followed calls are recording stubs.
State filter, animations, damage, activity and movement are explicitly stubbed;
this is NOT a full AI/fight verification. --iso enables private stats/clip CSVs.
"""
import argparse
import csv
import hashlib
import json
import mmap
import random
import struct
from pathlib import Path

from ee_emu import EE
from dump_tables import KNOWN_SHA256, balance_hash, find_in_lump, iso_files, lmp_entries
from difftest_combat import Rig as CombatRig
from difftest_anim import Rig as AnimRig
import ref_combat as combat
import ref_minotaur as contract
import ref_anim as animation


def fixture(elf):
    emulator = EE(str(elf))
    emulator.follow = {contract.STATE, contract.TICK}
    actor = emulator.alloc(0x470)
    memory = emulator.mem
    memory.w32(actor + 0x24, contract.DEF)
    memory.w32(actor + 0x48, contract.VTABLE)
    memory.w32(actor + 0x50, actor + 0x3C8)
    memory.w32(actor + 0x3C8, 0x50CDA0)
    memory.w32(actor + 0x228, combat.f32(100.0))
    memory.w32(actor + 0x22C, combat.f32(100.0))
    for index in range(26):
        memory.w32(contract.DEF + 12 + 8 * index, 0x700000 + index * 0x100)
    return emulator, actor


def check_states(elf, seed):
    rng = random.Random(seed)
    emulator, actor = fixture(elf)
    count = 0
    for state in list(range(26)) + [-1, 0x10000]:
        for band, hp in enumerate((20.0, 50.0, 90.0)):
            for first in (False, True):
                draw, age, flags = rng.getrandbits(32), rng.randrange(10000), rng.getrandbits(64)
                memory = emulator.mem
                memory.w32(actor + 0x228, combat.f32(hp))
                memory.w32(actor + 0x300, age)
                memory.w32(actor + 0x46C, 0 if first else 1)
                memory.w64(actor + 0xA8, flags)
                emulator.stub(0x1509D0, ret=draw)
                emulator.reset_log()
                emulator.call(contract.STATE, actor, state)
                animations = []
                for call in emulator.calls:
                    if call.target in (contract.CHANGE, contract.BLEND):
                        resource = (call.args[1] - 0x700000) // 0x100
                        floats = call.fargs[:1 if call.target == contract.CHANGE else 2]
                        animations.append((call.target, resource, call.args[2], floats))
                assert animations == contract.state_animation(state, band, first, draw), (state, band, animations)
                assert memory.u16(actor + 0x232) == contract.stored_state(state), state
                want_flags = flags & ~0x200
                if state == 23:
                    want_flags |= 0x200
                    assert memory.u32(actor + 0xF4) == (age + draw % 120 + 60) & 0xFFFFFFFF
                assert memory.u64(actor + 0xA8) == want_flags, state
                if state == 12:
                    assert memory.u32(actor + 0x46C) == 1
                if state == 16:
                    assert memory.u16(actor + 0x318) == 60
                drops = [call for call in emulator.calls if call.target == 0x10F2C8]
                assert len(drops) == int(state == 20)
                if drops:
                    assert drops[0].fargs[:6] == (0x42100000, 0x40000000, 0x3FCCCCCC,
                                                0x3F199999, 0x3FB33333, 0x3E800000)
                    detached = [call.args[1] for call in emulator.calls if call.target == 0x11BC90]
                    assert detached == [1, 2], detached
                count += 1
    print(f'seed {seed}: {count} state/health/charge cases, zero mismatches')
    return count


def check_attacks(elf, seed):
    rng = random.Random(seed)
    emulator, actor = fixture(elf)
    emulator.follow = {contract.TICK}
    emulator.stub(0x10C0F0, ret=1)
    count = 0
    for state in contract.ATTACK_CLIPS:
        for event in (0, 1, 4, 5):
            for anim_flags in (0, 8, 16, 24):
                memory = emulator.mem
                memory.w16(actor + 0x232, state)
                memory.w16(actor + 0x11A, anim_flags)
                facing = rng.randrange(-32768, 32768)
                damage = tuple(rng.randrange(1, 1000) for _ in range(3))
                memory.w16(actor + 0x38, facing & 0xFFFF)
                for offset, value in zip((0xD0, 0xD2, 0xD4), damage):
                    memory.w16(actor + offset, value)
                emulator.stub(0x1162B0, ret=event)
                emulator.reset_log()
                emulator.call(contract.TICK, actor)
                calls = emulator.calls
                hits = [call for call in calls if call.target == 0x119938]
                assert len(hits) == (event & 1 != 0), (state, event)
                if hits:
                    hit = hits[0]
                    assert tuple(value & 0xFFFFFFFF for value in hit.args[:7]) == (
                        actor, facing & 0xFFFFFFFF, 8000, *damage,
                        contract.ATTACK_FLAGS[state]), hit.args
                    assert hit.fargs[:2] == (0, 0x42100000)
                transitions = [call.args[1] for call in calls if call.target == contract.STATE]
                assert transitions == ([] if anim_flags & 8 else [5]), (state, transitions)
                count += 1
    print(f'seed {seed}: {count} attack event/animation cases, zero mismatches')
    return count


def check_constructor(elf, seed):
    rng = random.Random(seed)
    emulator, actor = fixture(elf)
    emulator.follow |= {contract.CTOR, 0x3B81A0, 0x11BC18, 0x1509D0}
    position = emulator.alloc(12)
    name = emulator.alloc(32)
    props = emulator.alloc(4)
    for index in range(100):
        boss = index % 2 == 0
        type_name = 'MinotaurBoss' if boss else 'Minotaur'
        memory = emulator.mem
        memory.write(name, type_name.encode() + b'\0')
        own, flags, frame = rng.getrandbits(32), rng.getrandbits(64), rng.getrandbits(31)
        memory.w32(actor + 0x44, own)
        memory.w64(actor + 0xA8, flags)
        memory.w32(0x44FDCC, frame)
        emulator.reset_log()
        emulator.call(contract.CTOR, actor, name, position, 0, props)
        expected_seed = combat.Seed(own)
        variant = 4 if boss else 1 << (expected_seed.draw() & 1)
        assert memory.u32(actor + 0x44) == expected_seed.state
        assert memory.u32(actor + 0x48) == contract.VTABLE
        assert memory.u32(actor + 0x50) == actor + 0x3C8
        assert memory.u32(actor + 0x3C8) == 0x50CDA0
        assert memory.u8(actor + 0x3D0) == 21
        assert memory.u8(actor + 0x460) == (23 if boss else 25)
        assert memory.u8(actor + 0x3CC) == 3
        assert memory.u64(actor + 0xA8) == (flags | 0x200040000) & ~0x200
        for offset, expected in ((0x1C, 0x41C80000), (0xB0, 0x3F999999),
                                 (0xB8, 0), (0xEC, frame), (0xF4, frame + 300),
                                 (0x46C, 0), (0xE8, variant)):
            assert memory.u32(actor + offset) == expected & 0xFFFFFFFF, hex(offset)
        assert memory.u8(actor + 0xB4) == 11
        events = tuple((call.args[1], call.args[2:6], call.fargs[:4])
                       for call in emulator.calls if call.target == 0x118378)
        assert events == contract.EVENTS
        assert [call.args[1] for call in emulator.calls if call.target == 0x179550] == [variant]
    print(f'seed {seed}: 100 constructor/holder/variant cases, zero mismatches (base ctor stubbed)')


def check_decisions(elf, seed):
    emulator, actor = fixture(elf)
    emulator.follow = {contract.TICK}
    emulator.stub(0x10C0F0, ret=1)
    has_target = emulator.mem.u32(contract.VTABLE + 0xCC)
    cases = (
        (0, 90, (), 0, 0, 0, None),
        (0, 90, (), 0, 0, 1, 1),
        (1, 90, (0x289660,), 0, 0, 1, 3),
        (3, 90, (), 0, 0, 0, 0),
        (3, 90, (0x2896B0,), 0, 0, 1, 5),
        (3, 90, (0x2896F0,), 0, 0, 1, 5),
        (3, 90, (0x289734,), 0, 0, 1, None),
        (3, 90, (0x2897AC,), 0, 0, 1, 12),
        (5, 90, (0x289904,), 0, 0, 1, 6),
        (5, 90, (0x28996C,), 1, 0, 1, 7),
        (5, 90, (0x2899FC,), 1, 0, 1, 9),
        (5, 90, (0x289A70,), 1, 0, 1, 10),
        (5, 90, (0x289AE4,), 1, 0, 1, 11),
        (5, 90, (0x289B64,), 0, 0, 1, 12),
        (5, 50, (0x289830,), 0, 0, 1, 6),
        (5, 50, (0x289830,), 0, 1, 1, 23),
        (5, 50, (0x289830,), 0, 1, 0, 6),
    )
    for state, hp, sight_sites, hand, attacking, target, expected in cases:
        emulator.mem.w16(actor + 0x232, state)
        emulator.mem.w32(actor + 0x228, combat.f32(float(hp)))
        emulator.mem.w32(actor + 0x234, 0x720000 if target else 0)
        emulator.mem.w32(actor + 0x468, 0)
        emulator.mem.w32(actor + 0x300, 1000)
        emulator.stub(has_target, ret=int(target != 0))
        emulator.stub(0x11BDE0, function=lambda current: int(
            (current.r[5] == 1 and hand != 0) or (current.r[5] == 2 and target != 0)))
        emulator.stub(0x118E90, ret=attacking)
        emulator.stub(0x1509D0, ret=1 if attacking else 0)
        emulator.stub(0x118D40, function=lambda current: int(current.calls[-1].site in sight_sites))
        emulator.reset_log()
        emulator.call(contract.TICK, actor)
        actual = [call.args[1] for call in emulator.calls if call.target == contract.STATE]
        assert actual == ([] if expected is None else [expected]), (state, sight_sites, actual)
    for state in (23,):
        for age, expected in ((99, []), (100, []), (101, [3])):
            emulator.mem.w16(actor + 0x232, state)
            emulator.mem.w32(actor + 0x300, age)
            emulator.mem.w32(actor + 0xF4, 100)
            emulator.reset_log()
            emulator.call(contract.TICK, actor)
            actual = [call.args[1] for call in emulator.calls if call.target == contract.STATE]
            assert actual == expected
    print(f'seed {seed}: {len(cases) + 3} AI decision/timer cases, zero mismatches (sight/holder services stubbed)')


def check_clips(elf, archive, output):
    exe = combat.Exe(str(elf))
    rig = AnimRig(str(elf))
    entries = {name.lower(): archive[offset:offset + size]
               for name, offset, size in lmp_entries(archive)}
    actor = rig.emu.alloc(0x470)
    rig.emu.mem.w32(actor + 0x24, contract.DEF)
    clips = {}
    for index in range(2, 20):
        name = definition_member(exe, index)
        clip = rig.load_clip(entries[name.lower()], name)
        clips[index] = clip
        rig.emu.mem.w32(contract.DEF + 12 + 8 * index, rig.ptr(clip))
    for entry, masks, times in contract.EVENTS:
        clip = clips[entry - 1]
        rig.call(0x118378, actor, entry, *masks, floats=times)
        for index, (time, mask) in enumerate(zip(times, masks)):
            assert rig.emu.mem.u32(rig.ptr(clip) + 0x14 + 8 * index) == time
            assert rig.emu.mem.u8(rig.ptr(clip) + 0x18 + 8 * index) == mask
            clip.events[index] = [time, mask]
    with output.open('w') as stream:
        writer = csv.writer(stream)
        writer.writerow(('index', 'clip', 'length', 'tick', 'events'))
        for index, clip in clips.items():
            state = rig.new_state()
            rig.call(0x170838, rig.ptr(state), rig.ptr(clip), 0)
            animation.anim_push(state, clip, 0)
            writer.writerow((index, clip.name, clip.length, '', ''))
            for tick in range(clip.length + 3):
                events, *_ = rig.advance(state, animation.ONE, sound=False)
                if events:
                    writer.writerow((index, clip.name, clip.length, tick, hex(events)))
    print('18 private Minotaur clips: original relocate/configure/advance vs existing animation model, zero mismatches')


def definition_member(exe, index):
    """Resolve a private resource identifier from its owned definition entry."""
    assert 0 <= index < 26
    return exe.cstr(exe.u32(contract.DEF + 8 + 8 * index))


def read_archives(elf, iso, output=None):
    # balance_load 0x223998 uses these two executable string addresses.
    # Class archive identity is the string pointer at definition +0.
    exe = combat.Exe(str(elf))
    wanted = {'balance': exe.cstr(0x53FC78),
              'actor': exe.cstr(exe.u32(contract.DEF))}
    roles = {name.casefold(): role for role, name in wanted.items()}
    assert len(roles) == len(wanted)
    result = {}
    with iso.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as image:
        for name, offset, size in iso_files(image):
            role = roles.get(name.rsplit('/', 1)[-1].casefold())
            if role is not None:
                assert role not in result
                result[role] = image[offset:offset + size]
    assert result.keys() == wanted.keys()
    if output is not None:
        private_root = Path(__file__).resolve().parents[1] / 'local'
        assert private_root in output.resolve().parents
        mapping = {
            'archive_roles': wanted,
            'balance_member': exe.cstr(0x53FC88),
            'definition': hex(contract.DEF),
            'resources': [{'index': index, 'name': definition_member(exe, index)}
                          for index in range(26)],
            'archive_members': {role: [name for name, _, _ in lmp_entries(blob)]
                                for role, blob in result.items()},
        }
        (output / 'private-members.json').write_text(json.dumps(mapping, indent=2) + '\n')
    return result


def check_stats(elf, seed, balance, output):
    exe = combat.Exe(str(elf))
    blob = find_in_lump(balance, exe.cstr(0x53FC88).casefold())
    assert blob is not None
    rows = struct.unpack_from('<H', blob)[0]
    matching = [struct.unpack_from('<5H', blob, 4 + index * 12)
                for index in range(rows)
                if struct.unpack_from('<H', blob, 2 + index * 12)[0] == balance_hash('Minotaur')]
    assert len(matching) == 1
    factors = tuple(combat.fmul(combat.itof(value), 0x3C23D70A) for value in matching[0])
    tables, rig = combat.Tables.load(str(elf)), CombatRig(str(elf))
    rng, count = random.Random(seed), 0
    rig.emu.stub(0x10D940, ret=0)
    with output.open('w') as stream:
        writer = csv.writer(stream)
        writer.writerow(('level', 'difficulty', 'own_seed', 'hp_raw', 'armor', 'low', 'high', 'attack', 'xp_raw'))
        levels = [combat.f32(float(level)) for level in range(1, 161)]
        levels.extend(combat.level_scale(tables, 20, difficulty, 0, 'valor')
                      for difficulty in range(1, 6))
        for level_word in levels:
            for difficulty in range(1, 6):
                for hp_roll in range(5):
                    world = combat.World(seed=seed)
                    world.monster_level = level_word
                    world.num_players, world.difficulty, world.level_name = 1, difficulty, 'valor'
                    own = rng.getrandbits(32)
                    while combat.Seed(own).draw() % 5 != hp_roll:
                        own = rng.getrandbits(32)
                    actor = combat.Obj(tag='monster', flags=0x20, own_seed=own)
                    rig.begin({'world': world, 'rank': 0, 'props': {}})
                    rig.put_world(world)
                    rig.put_objects([actor])
                    address = rig.addr[id(actor)]
                    rig.mem.w32(address + 0x34, rig.cstring('Minotaur'))
                    rig.call(0x10A620, address, 1, fargs=factors)
                    draw = combat.Seed(own)
                    expected = combat.monster_stats(tables, world, factors, 0, 'Minotaur', True, draw.draw())
                    actual = (rig.mem.u32(address + 0x228), rig.mem.s16(address + 0xE4),
                              rig.mem.s16(address + 0xD0), rig.mem.s16(address + 0xD2),
                              rig.mem.s16(address + 0xD4), rig.mem.u32(address + 0xD8))
                    assert actual == tuple(expected[key] for key in ('hp', 'armor', 'dmg_low', 'dmg_high', 'attack', 'exp_value'))
                    assert rig.mem.u32(address + 0x22C) == expected['max_hp']
                    assert rig.mem.u32(address + 0x44) == draw.state
                    level = struct.unpack('<f', struct.pack('<I', level_word))[0]
                    writer.writerow((level, difficulty, own, *actual))
                    count += 1
    print(f'seed {seed}: {count} Minotaur statistics cases (L=1..160 plus Valor scales; 5 difficulties; all 5 HP rolls), zero mismatches')
    return factors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--iso', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    assert hashlib.sha256(args.elf.read_bytes()).hexdigest() == KNOWN_SHA256
    check_states(args.elf, args.seed)
    check_attacks(args.elf, args.seed)
    check_constructor(args.elf, args.seed)
    check_decisions(args.elf, args.seed)
    if args.iso:
        if args.out is None or 'local' not in args.out.resolve().parts:
            parser.error('--iso requires a private --out under local/')
        args.out.mkdir(parents=True, exist_ok=True)
        archives = read_archives(args.elf, args.iso, args.out)
        check_stats(args.elf, args.seed, archives['balance'], args.out / f'stats-{args.seed}.csv')
        check_clips(args.elf, archives['actor'], args.out / f'clips-{args.seed}.csv')


if __name__ == '__main__':
    main()
