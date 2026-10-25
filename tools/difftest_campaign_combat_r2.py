#!/usr/bin/env python3
"""Bounded valor WarBoar research against SLUS-20973 US v2.00.

PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_campaign_combat_r2.py \
    /path/to/SLUS_209.73 /path/to/VALOR.GOB /path/to/BALANCE.LMP --seed 20973

The factory, constructor, setState, run and balance_lookup execute in ee_emu.
Base Creature, animation, terrain, AI and loot services are recording stubs;
therefore these assertions do not establish a whole fight or live gameplay.
"""
import argparse
import hashlib
import random
import struct

from dump_tables import balance_hash, find_in_lump, objects_from_file
from ee_emu import EE
from difftest_campaign_combat import EXPECTED_SHA256, RealCalls, original, put_string
from ref_campaign_combat import classify
import ref_campaign_combat_r2 as R
from ref_combat import Exe, Tables, level_scale

BALANCE_LOOKUP = 0x223A4C
BALANCE_HASH = 0x223914


def constructed(executable, name, angle=0):
    emu = EE(executable)
    emu.follow = {R.BOAR_CTOR, R.BOAR_RUN, R.BOAR_SET_STATE, 0x159C20}
    obj = emu.alloc(0x3D8)
    pos = emu.alloc(12)
    props = emu.alloc(4)
    type_name = put_string(emu, name)
    model = emu.alloc(0x100)
    emu.stub(0x109D68, function=lambda e: e.mem.w32(obj + 0x24, model),
             name="Creature_ctor recording stub")
    emu.reset_log()
    emu.call(R.BOAR_CTOR, obj, pos, angle, props, type_name, max_steps=100000)
    return emu, obj


def check_ctor(executable, row):
    name = row["class"]
    emu, obj = constructed(executable, name, row["angle"])
    actual_calls = [c.target for c in emu.calls]
    assert actual_calls == R.ctor_services(), (row["index"], name, actual_calls)
    assert emu.calls[0].args[4] == R.BOAR_DEF
    event_entries = [c.args[1] for c in emu.calls if c.target == 0x118378]
    assert event_entries == [4, 5, 6, 7, 10, 11, 12]
    # Only class-instruction writes are compared; Creature_ctor owns the base object.
    writes = {(addr - obj, size): value for pc, addr, size, value in emu.writes
              if R.BOAR_CTOR <= pc < R.BOAR_RUN and obj <= addr < obj + 0x3D8}
    for field, value in R.ctor_fields(name == "WarBoarSmall").items():
        assert writes.get(field) == value, (row["index"], name, field, writes.get(field), value)


def check_factory(executable, rows, rng):
    emu = EE(executable)
    emu.follow = RealCalls()
    block = emu.alloc(0x600)
    emu.stub(0x14FDB8, ret=block, name="pool_new")
    probes = list(rows)
    rng.shuffle(probes)
    for row in probes:
        result, actual = original(emu, row)
        assert actual == classify(row["class"], row["properties"].split(";"))[:2]
        assert result == block


def check_balance(executable, blob):
    count, = struct.unpack_from("<H", blob)
    assert count == 184 and len(blob) >= 2 + 12 * count
    emu = EE(executable)
    emu.follow = {BALANCE_LOOKUP, BALANCE_HASH, 0x3B8DC4}
    table = emu.alloc(len(blob))
    emu.mem.write(table, blob)
    # balance_load publishes a pointer to the first row, after the count word.
    emu.mem.w32(0x4FB5C4, table + 2)
    emu.mem.w32(0x4FB5C8, count)
    for name in ("WarBoar", "WarBoarSmall"):
        name_ptr = put_string(emu, name)
        out = [emu.alloc(4) for _ in range(5)]
        rows = [struct.unpack_from("<H5h", blob, 2 + i * 12) for i in range(count)]
        matching = [row for row in rows if row[0] == balance_hash(name)]
        assert len(matching) == 1, (name, matching)
        emu.reset_log()
        found = emu.call(BALANCE_LOOKUP, name_ptr, *out, max_steps=200000)
        actual = tuple(emu.mem.u32(ptr) for ptr in out)
        expected = R.balance_factors(matching[0][1:])
        assert found == 1 and actual == expected, (name, actual, expected)
        print("PASS balance %s hash %#06x percentages %s" %
              (name, balance_hash(name), matching[0][1:]))


def check_tick_and_death(executable, name):
    for state in (0, 3, 6, 20):
        for hit_event in ((False, True) if state == 6 else (False,)):
            emu, obj = constructed(executable, name)
            emu.mem.w16(obj + 0x232, state)
            emu.mem.wf32(obj + 0x228, 100)
            emu.mem.wf32(obj + 0x22C, 100)
            emu.stub(0x10C0F0, ret=1, name="active")
            emu.stub(0x1162B0, ret=int(hit_event), name="stepAnim")
            emu.follow = {R.BOAR_RUN}
            emu.reset_log()
            emu.call(R.BOAR_RUN, obj, max_steps=100000)
            actual = [c.target for c in emu.calls]
            assert actual == R.tick_services(state, hit_event), (name, state, hit_event, actual)
            if state == 6 and hit_event:
                assert emu.mem.u32(obj + 0x3C8) == 1
                hit = next(c for c in emu.calls if c.target == 0x119B58)
                assert hit.args[6] == 8
    for state, expected in ((6, [0x10A9C0, 0x16CEB0]),
                            (20, [0x10A9C0, 0x10F2C8, 0x1509D0,
                                  0x16CFE0, 0x10BEB8])):
        emu, obj = constructed(executable, name)
        emu.reset_log()
        emu.call(R.BOAR_SET_STATE, obj, state, max_steps=100000)
        assert [c.target for c in emu.calls] == expected, (name, state, emu.calls)
        assert emu.mem.u16(obj + 0x232) == state
        if state == 6:
            assert emu.mem.u32(obj + 0x3C8) == 0
            assert emu.mem.u32(obj + 0x3CC) == 6


def check_gold_touch(executable):
    for countdown in (41, 2, 1):
        emu = EE(executable)
        emu.follow = {R.GOLD_RUN}
        gold = emu.alloc(0xC0)
        emu.mem.w8(gold + 0x4C, countdown)
        emu.reset_log()
        emu.call(R.GOLD_RUN, gold, max_steps=100000)
        assert emu.mem.u8(gold + 0x4C) == R.gold_countdown(countdown)
        assert [c.target for c in emu.calls] == [0x1709D8]
    for flags, countdown, amount in ((0x40, 0, 42), (0x20040, 0, 42),
                                     (0x40, 1, 42), (0x20, 0, 42), (0x40, 0, 0)):
        emu = EE(executable)
        emu.follow = {R.GOLD_ON_TOUCH}
        gold = emu.alloc(0xC0)
        player = emu.alloc(0x500)
        emu.mem.w32(gold + 0x80, amount)
        emu.mem.w8(gold + 0x4C, countdown)
        emu.mem.w32(player + 0xC, flags)
        emu.reset_log()
        emu.call(R.GOLD_ON_TOUCH, gold, player, max_steps=100000)
        expected = R.gold_touch_services(flags, countdown, amount)
        actual = [c.target for c in emu.calls]
        assert actual == expected, (flags, countdown, amount, actual, expected)
        assert emu.mem.u32(gold + 0x80) == (0 if expected else amount)
        if expected:
            floater = next(c for c in emu.calls if c.target == 0x1DC268)
            assert floater.args[2] == amount


def check_valor_level(executable):
    exe = Exe(executable)
    tables = Tables.load(exe)
    row = 0x4F7210 + 50 * 0x30
    name = exe.cstr(exe.u32(row))
    level_byte = exe.u8(row + 4)
    assert name == "valor" and level_byte == 20, (name, level_byte)
    assert name not in tables.fixed_levels, (name, tables.fixed_levels)
    assert level_scale(tables, level_byte, 1, 0, name) == 0x41B00000
    return level_byte


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable")
    parser.add_argument("valor_gob")
    parser.add_argument("balance_lmp")
    parser.add_argument("--seed", type=int, default=20973)
    args = parser.parse_args()
    with open(args.executable, "rb") as stream:
        assert hashlib.sha256(stream.read()).hexdigest() == EXPECTED_SHA256
    with open(args.valor_gob, "rb") as stream:
        rows = objects_from_file(args.valor_gob, stream.read())
    boars = [row for row in rows if row["class"] in ("WarBoar", "WarBoarSmall")]
    assert len(rows) == 201 and sum(r["class"] == "WarBoar" for r in boars) == 34
    assert len(boars) == 78
    rng = random.Random(args.seed)
    check_factory(args.executable, boars, rng)
    rng.shuffle(boars)
    for row in boars:
        check_ctor(args.executable, row)
    with open(args.balance_lmp, "rb") as stream:
        blob = find_in_lump(stream.read(), "monsters.bal")
    assert blob is not None
    check_balance(args.executable, blob)
    for name in ("WarBoar", "WarBoarSmall"):
        check_tick_and_death(args.executable, name)
    check_gold_touch(args.executable)
    level_byte = check_valor_level(args.executable)
    print("PASS seed %d: 78 valor factory and constructor cases; 10 tick, 4 setState, 3 Gold run and 5 touch cases; ELF level byte %d, model scale 22" % (args.seed, level_byte))


if __name__ == "__main__":
    main()
