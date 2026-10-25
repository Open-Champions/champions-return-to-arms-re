#!/usr/bin/env python3
"""Bounded blood1 hostile constructor, balance, tick and death comparisons.

PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_blood1_enemies.py \
  local/SLUS_209.73 local/BLOOD1.GOB local/BALANCE.LMP --seed 20973

The original class, Creature and GameObject constructors execute. Resource
returns and downstream model, AI, animation and loot services are stubs. Tick
inputs are synthetic, so this is not a level run or a native combat test.
"""
import argparse
from collections import Counter
import hashlib
import random
import struct

from dump_tables import balance_hash, find_in_lump, objects_from_file
from ee_emu import EE, float_to_raw
from difftest_blood1 import SHA256, cstr, put
import ref_blood1 as B
import ref_blood1_enemies as R

BASE = 0x109D68
OBJECT = 0x14CB10
RES_FIND = 0x17365C
BALANCE_LOOKUP = 0x223A4C


def make(exe, name, seed, *, base=True):
    count, size, ctor, definition, vtable, variant = R.CLASSES[name]
    emu = EE(exe)
    emu.mem.w32(0x404464, seed)
    emu.mem.w32(0x41BF78, 1)
    obj, pos, props = emu.alloc(size), emu.alloc(12), emu.alloc(4)
    type_name = put(emu, name)
    emu.follow = {ctor, 0x159C20, 0x3B81A0, 0x3B8DC4, 0x3B8F30}
    if name == "WarWraith":
        emu.follow.add(0x1509D0)  # original own-object draw, before and after base ctor
    if base:
        emu.follow |= {BASE, OBJECT, 0x14C880}
    else:
        model = emu.alloc(0x100)
        emu.stub(BASE, function=lambda e: e.mem.w32(obj + 0x24, model))
    requests = []
    emu.stub(RES_FIND, function=lambda e: requests.append(
        (cstr(e.mem, e.r[4]), cstr(e.mem, e.r[5]))) or 0)
    args = ((obj, type_name, pos, 0, props) if name == "WarWraith"
            else (obj, pos, 0, props, type_name))
    emu.call(ctor, *args, max_steps=1000000)
    return emu, obj, requests


def check_constructor(exe, name, seed):
    emu, obj, requests = make(exe, name, seed)
    _count, size, ctor, definition, _vtable, _variant = R.CLASSES[name]
    base = [c for c in emu.calls if c.target == BASE]
    objects = [c for c in emu.calls if c.target == OBJECT]
    assert len(base) == len(objects) == 1
    assert base[0].args[0] == objects[0].args[0] == obj
    assert base[0].args[4] == objects[0].args[2] == definition
    assert base[0].fargs[0] == float_to_raw(4. if name == "WarWraith" else 10.)
    archive, names = B.RESOURCE_DEFS[definition]
    assert requests == [(archive, entry) for entry in names]
    assert emu.mem.u32(obj + 0x24) == definition
    assert any(c.target == BALANCE_LOOKUP for c in emu.calls)
    fields = R.class_fields(name)
    for (offset, width), expected in fields.items():
        observed = {1: emu.mem.u8, 4: emu.mem.u32}[width](obj + offset)
        if expected is None:
            expected = obj + 0x3D0
        assert observed == expected, (name, hex(offset), observed, expected)
    events = tuple(c.args[1] for c in emu.calls if c.target == 0x118378)
    assert events == (R.WRAITH_EVENTS if name == "WarWraith"
                      else R.KOBOLD_EVENTS)
    if name == "WarWraith":
        assert emu.mem.u32(obj + 0x3D0) == 0x50CF40
        holder = [c for c in emu.calls if c.target == 0x11AFB0]
        assert len(holder) == 1 and holder[0].args[0] == obj + 0x3D0
        assert holder[0].args[1] == 1
        assert holder[0].args[2] in (13, 15, 17)
        if seed in R.WRAITH_WEAPON_PROBE:
            assert holder[0].args[2] == R.WRAITH_WEAPON_PROBE[seed]
    return len(requests), len(events)


def check_balance(exe, blob):
    count, = struct.unpack_from("<H", blob)
    assert count == 184
    emu = EE(exe)
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
    return len(R.BALANCE)


def check_tick(exe, name, seed, state, event):
    emu, obj, _requests = make(exe, name, seed, base=False)
    family = "WarWraith" if name == "WarWraith" else "Kobold"
    emu.follow = {R.RUN[family]}
    emu.stub(0x10C0F0, ret=1)
    emu.stub(0x1162B0, ret=event)
    emu.mem.w16(obj + 0x232, state)
    emu.mem.wf32(obj + 0x228, 100.)
    emu.mem.wf32(obj + 0x22C, 100.)
    emu.reset_log()
    emu.call(R.RUN[family], obj, max_steps=200000)
    got = tuple(c.target for c in emu.calls)
    assert got == R.tick_calls(family, state, event), (name, state, got)
    return len(got)


def check_death(exe, name, seed):
    emu, obj, _requests = make(exe, name, seed, base=False)
    family = "WarWraith" if name == "WarWraith" else "Kobold"
    emu.follow = {R.SET_STATE[family]}
    emu.reset_log()
    emu.call(R.SET_STATE[family], obj, 20, max_steps=200000)
    got = tuple(c.target for c in emu.calls)
    assert got == R.death_calls(family), (name, got)
    drop = next(c for c in emu.calls if c.target ==
                (0x100D54 if name == "WarWraith" else 0x10F2C8))
    assert drop.fargs[:6] == R.DEATH_FLOATS[family]
    assert emu.mem.u16(obj + 0x232) == 20
    return drop.target


def check_targeted_attack(exe, name, seed):
    # Synthetic handle and target. The hit service is a recording stub: only
    # attack dispatch and arguments are established, never landed damage.
    emu, obj, _requests = make(exe, name, seed, base=False)
    family = "WarWraith" if name == "WarWraith" else "Kobold"
    emu.follow = {R.RUN[family]}
    emu.stub(0x10C0F0, ret=1)
    emu.stub(0x1162B0, ret=1)
    target, node = emu.alloc(0x500), emu.alloc(20)
    emu.mem.w32(node + 0xC, target)
    emu.mem.w32(obj + 0x234, node)
    emu.mem.w16(obj + 0x232, 6)
    emu.mem.wf32(obj + 0x228, 100.)
    emu.mem.wf32(obj + 0x22C, 100.)
    emu.reset_log()
    emu.call(R.RUN[family], obj, max_steps=200000)
    got = tuple(c.target for c in emu.calls)
    assert got == R.TICK_PREFIX + R.TARGETED_ATTACK[family], (name, got)
    hit = next(c for c in emu.calls if c.target ==
               (0x1196E8 if family == "WarWraith" else 0x119938))
    assert hit.args[0] == obj
    assert hit.args[4 if family == "WarWraith" else 6] == (
        8 if family == "WarWraith" else R.KOBOLD_HIT_FLAGS[name])
    return hit.target


def check_damage(exe):
    emu = EE(exe)
    emu.follow = {0x116638}
    obj = emu.alloc(0x468)
    emu.mem.wf32(obj + 0x228, 100.)
    emu.call(0x116638, obj, 0, 8, fargs=(25.,), max_steps=100000)
    assert emu.mem.u32(obj + 0x228) == float_to_raw(75.)
    assert emu.mem.u32(obj + 0xC8) == float_to_raw(25.)
    assert emu.mem.u32(obj + 0x2DC) == 8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("executable")
    ap.add_argument("gob")
    ap.add_argument("balance_lmp")
    ap.add_argument("--seed", type=int, default=20973)
    args = ap.parse_args()
    assert hashlib.sha256(open(args.executable, "rb").read()).hexdigest() == SHA256
    gob = open(args.gob, "rb").read()
    rows = objects_from_file(args.gob, gob)
    assert Counter(row["class"] for row in rows if row["class"] in R.CLASSES) == {
        name: data[0] for name, data in R.CLASSES.items()}
    names = list(R.CLASSES)
    random.Random(args.seed).shuffle(names)
    resources = events = ticks = 0
    for name in names:
        n, e = check_constructor(args.executable, name, args.seed)
        resources += n
        events += e
        for state, event in ((0, 0), (3, 0), (6, 1), (7, 1), (20, 0)):
            ticks += check_tick(args.executable, name, args.seed, state, event)
        check_targeted_attack(args.executable, name, args.seed)
        check_death(args.executable, name, args.seed)
    blob = find_in_lump(open(args.balance_lmp, "rb").read(), "monsters.bal")
    assert blob is not None
    check_balance(args.executable, blob)
    check_damage(args.executable)
    print(f"PASS seed {args.seed}: 140 placements/4 class selections; "
          f"{resources} constructor resource requests, {events} event setups; "
          f"4 balance rows, 20 no-target ticks/{ticks} calls, "
          "4 targeted attack dispatches, 4 death routes, "
          "1 base damage probe; downstream services stubbed")


if __name__ == "__main__":
    main()
