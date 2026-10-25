#!/usr/bin/env python3
"""Bounded mission-2 hostile constructor, balance, tick and death comparisons.

PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_mission2_enemies.py \
  local/SLUS_209.73 local --seed 20973

The original factory, class, Creature and GameObject constructors execute.
Resource returns and lower AI, animation, damage, effects and loot services
are stubs. Synthetic ticks and hits are dispatch checks, not landed combat.
"""
import argparse
import hashlib
import os
import struct

from dump_tables import Elf, balance_hash, find_in_lump, lmp_entries
from ee_emu import EE, float_to_raw
from difftest_mission2 import (SHA256, FACTORY, POOL_NEW, CREATURE, OBJECT,
                               RES_FIND, ConstructorFollow, cstr, put)
import ref_mission2 as M2
import ref_mission2_enemies as R

BALANCE_LOOKUP = 0x223A4C
SET_EVENTS = 0x118378


def make(executable, name, seed):
    _count, size, ctor, _definition, _vtable, _variant = R.CLASSES[name]
    emu = EE(executable)
    emu.follow = ConstructorFollow(ctor)
    emu.mem.w32(0x41BF78, 1)
    emu.mem.w32(0x404464, seed)
    emu.mem.w32(0x44FDC8, emu.alloc(0x100))
    block = emu.alloc(size)
    emu.stub(POOL_NEW, ret=block)
    requests = []
    emu.stub(RES_FIND, function=lambda e: requests.append(
        (cstr(e.mem, e.r[4]), cstr(e.mem, e.r[5]))) or 0)
    result = emu.call(FACTORY, put(emu, name), emu.alloc(12), 0,
                      emu.alloc(4), max_steps=1000000)
    assert result == block
    return emu, block, requests


def resource_names(executable, source_dir):
    elf = Elf(open(executable, "rb").read())
    expected = {}
    for definition, (archive, count) in M2.RESOURCE_DEFS.items():
        assert elf.cstr(elf.u32(definition)) == archive
        names = tuple(elf.cstr(elf.u32(definition + 8 + 8 * i))
                      for i in range(count))
        assert len(set(names)) == count and all(names)
        assert elf.u32(definition + 8 + 8 * count) == 0
        blob = open(os.path.join(source_dir, archive.upper()), "rb").read()
        present = {entry.lower() for entry, _off, _size in lmp_entries(blob)}
        assert all(entry.lower() in present for entry in names)
        expected[definition] = [(archive, entry) for entry in names]
    return expected


def check_constructor(executable, name, seed, resources):
    emu, obj, requests = make(executable, name, seed)
    _count, _size, ctor, definition, vtable, _variant = R.CLASSES[name]
    base = [call for call in emu.calls if call.target == CREATURE]
    objects = [call for call in emu.calls if call.target == OBJECT]
    assert len(base) == len(objects) == 1
    assert base[0].args[0] == objects[0].args[0] == obj
    assert base[0].args[4] == objects[0].args[2] == definition
    assert base[0].fargs[0] == float_to_raw(10.)
    assert any(call.target == ctor for call in emu.calls)
    assert any(call.target == BALANCE_LOOKUP for call in emu.calls)
    assert requests == resources[definition]
    assert emu.mem.u32(obj + 0x24) == definition
    for (offset, width), expected in R.class_fields(name).items():
        actual = {1: emu.mem.u8, 4: emu.mem.u32}[width](obj + offset)
        assert actual == (obj + 0x3D0 if expected is None else expected), (name, hex(offset), hex(actual))
    assert tuple(call.args[1] for call in emu.calls if call.target == SET_EVENTS) == R.EVENTS[name]
    assert emu.mem.u32(vtable + 8 * 2 + 4) == 0x116638
    assert emu.mem.u32(vtable + 8 * 4 + 4) == R.RUN[name]
    assert emu.mem.u32(vtable + 8 * 27 + 4) == R.SET_STATE[name]
    if name == "IronGuardian":
        assert any(call.target == 0x173558 and cstr(emu.mem, call.args[0]) == "droid.lmp"
                   for call in emu.calls)
    return len(requests), len(R.EVENTS[name])


def check_balance(executable, source_dir):
    blob = find_in_lump(open(os.path.join(source_dir, "BALANCE.LMP"), "rb").read(),
                        "monsters.bal")
    assert blob is not None
    count, = struct.unpack_from("<H", blob)
    assert count == 184
    emu = EE(executable)
    emu.follow = {BALANCE_LOOKUP, 0x223914, 0x3B8DC4}
    table = emu.alloc(len(blob))
    emu.mem.write(table, blob)
    emu.mem.w32(0x4FB5C4, table + 2)
    emu.mem.w32(0x4FB5C8, count)
    for name, percentages in R.BALANCE.items():
        matches = [struct.unpack_from("<H5h", blob, 2 + i * 12)
                   for i in range(count)
                   if struct.unpack_from("<H", blob, 2 + i * 12)[0] == balance_hash(name)]
        assert len(matches) == 1 and matches[0][1:] == percentages
        out = [emu.alloc(4) for _ in range(5)]
        assert emu.call(BALANCE_LOOKUP, put(emu, name), *out,
                        max_steps=200000) == 1
        assert tuple(emu.mem.u32(ptr) for ptr in out) == R.balance_factors(name)


def check_tick(executable, name, seed, state, event):
    emu, obj, _requests = make(executable, name, seed)
    emu.follow = {R.RUN[name]}
    emu.stub(0x10C0F0, ret=1)
    emu.stub(0x1162B0, ret=event)
    emu.mem.w16(obj + 0x232, state)
    emu.mem.wf32(obj + 0x228, 100.)
    emu.mem.wf32(obj + 0x22C, 100.)
    emu.reset_log()
    emu.call(R.RUN[name], obj, max_steps=300000)
    actual = tuple(call.target for call in emu.calls)
    assert actual == R.tick_calls(name, state), (name, state, actual)
    return len(actual)


def check_targeted_attack(executable, name, seed):
    if name == "Droid":
        return None  # Its attack is the separate fuse/explosion state.
    emu, obj, _requests = make(executable, name, seed)
    emu.follow = {R.RUN[name]}
    emu.stub(0x10C0F0, ret=1)
    emu.stub(0x1162B0, ret=1)
    target, node = emu.alloc(0x500), emu.alloc(20)
    emu.mem.w32(node + 0xC, target)
    emu.mem.w32(obj + 0x234, node)
    emu.mem.w16(obj + 0x232, 6)
    emu.mem.wf32(obj + 0x228, 100.)
    emu.mem.wf32(obj + 0x22C, 100.)
    emu.reset_log()
    emu.call(R.RUN[name], obj, max_steps=300000)
    hit_addr, flags = R.TARGETED_HIT[name]
    hits = [call for call in emu.calls if call.target == hit_addr]
    assert len(hits) == 1 and hits[0].args[0] == obj
    assert hits[0].args[6] == flags, (name, hits[0].args)
    return hit_addr


def check_death(executable, name, seed):
    emu, obj, _requests = make(executable, name, seed)
    emu.follow = {R.SET_STATE[name]}
    emu.reset_log()
    emu.call(R.SET_STATE[name], obj, 20, max_steps=300000)
    actual = tuple(call.target for call in emu.calls)
    assert actual == R.death_calls(name), (name, actual)
    drops = [call for call in emu.calls if call.target == 0x10F2C8]
    assert len(drops) == (0 if name == "Droid" else 1)
    if drops:
        assert drops[0].fargs[:6] == R.DROP_FLOATS
    assert emu.mem.u16(obj + 0x232) == 20


def check_droid_explosion(executable, seed):
    emu, obj, _requests = make(executable, "Droid", seed)
    emu.follow = {R.RUN["Droid"]}
    emu.stub(0x10C0F0, ret=1)
    emu.stub(0x1162B0, ret=0)
    emu.mem.w16(obj + 0x232, 0x17)
    emu.mem.w16(obj + 0x11A, 0x80)
    emu.mem.w16(obj + 0xD2, 123)
    emu.reset_log()
    emu.call(R.RUN["Droid"], obj, max_steps=300000)
    assert tuple(call.target for call in emu.calls) == R.EXPLOSION_CALLS
    radius = [call for call in emu.calls if call.target == 0x161270]
    assert len(radius) == 1
    assert radius[0].args[0] == obj
    assert radius[0].args[2:4] == (123, 0x40840)
    assert radius[0].fargs[:2] == (float_to_raw(60.), float_to_raw(144.))
    assert emu.mem.u32(obj + 0xC) & 0xA == 0xA


def check_damage(executable):
    # All four vtables use Creature_takeDamage; isolated damage arithmetic.
    emu = EE(executable)
    emu.follow = {0x116638}
    obj = emu.alloc(0x500)
    emu.mem.wf32(obj + 0x228, 100.)
    emu.call(0x116638, obj, 0, 8, fargs=(25.,), max_steps=100000)
    assert emu.mem.u32(obj + 0x228) == float_to_raw(75.)
    assert emu.mem.u32(obj + 0xC8) == float_to_raw(25.)
    assert emu.mem.u32(obj + 0x2DC) == 8


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable")
    parser.add_argument("source_dir")
    parser.add_argument("--seed", type=int, default=20973)
    parser.add_argument("--resource-manifest", help="write ordered names to an ignored local file")
    args = parser.parse_args()
    assert hashlib.sha256(open(args.executable, "rb").read()).hexdigest() == SHA256
    assert {name: sum(level.get(name, 0) for level in M2.COUNTS.values())
            for name in R.CLASSES} == {name: row[0] for name, row in R.CLASSES.items()}
    resources = resource_names(args.executable, args.source_dir)
    if args.resource_manifest:
        with open(args.resource_manifest, "w", encoding="utf-8") as manifest:
            for definition, (archive, _count) in M2.RESOURCE_DEFS.items():
                manifest.write(f"{definition:#x} {archive}\n")
                for index, (_archive, entry) in enumerate(resources[definition]):
                    manifest.write(f"  {index:02d} {entry}\n")
    requests = events = ticks = 0
    for name in R.CLASSES:
        n, e = check_constructor(args.executable, name, args.seed, resources)
        requests += n
        events += e
        for state, event in ((0, 0), (3, 0), (6, 1), (20, 0)):
            ticks += check_tick(args.executable, name, args.seed, state, event)
        check_targeted_attack(args.executable, name, args.seed)
        check_death(args.executable, name, args.seed)
    check_balance(args.executable, args.source_dir)
    check_droid_explosion(args.executable, args.seed)
    check_damage(args.executable)
    print(f"PASS seed {args.seed}: 163 placements/4 class selections; "
          f"{requests} constructor resource requests, {events} event setups; "
          f"4 balance rows, 16 synthetic ticks/{ticks} calls, "
          "3 targeted hit dispatches, 1 Droid explosion dispatch, "
          "4 death routes, 1 base damage probe; "
          "downstream services stubbed")


if __name__ == "__main__":
    main()
