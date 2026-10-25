#!/usr/bin/env python3
"""Bounded round-3 valor probes; no whole-game or native fight is claimed.

PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_campaign_combat_r3.py \
    /path/to/SLUS_209.73 local/VALOR.GOB local/valor.world \
    local/WARBOAR.LMP --seed 20973

Original GameObject_ctor, player grant routing, terrain_height,
loot_generateDrops, HUD gold credit, object grid and runObjects execute in
ee_emu. Resource pointers, grant inventory services, item/Gold constructors,
and the two virtual runs are recording stubs, described at each probe.
"""
import argparse
import collections
import hashlib
import random
import struct

from dump_tables import lmp_entries, objects_from_file
from ee_emu import EE, s32
from difftest_campaign_combat import EXPECTED_SHA256
from difftest_campaign_combat import put_string
from difftest_campaign_combat_r2 import constructed
from difftest_objects import Rig as ObjectRig, A as OBJECT_A, POOL_NEW, RES_FIND
from difftest_world import Rig as TerrainRig, A_HEIGHT
import difftest_items as I
import ref_campaign_combat_r3 as R3
from ref_combat import Exe
import ref_items as IREF
import ref_world as W


def cstr(mem, address):
    data = bytearray()
    while mem.u8(address + len(data)):
        data.append(mem.u8(address + len(data)))
        assert len(data) < 128
    return data.decode("latin1")


def position(row):
    return tuple(W.f32(float(row[key])) for key in ("x", "y", "height"))


def check_resources(executable, archive, seed):
    entries = {name.lower() for name, _off, _size in lmp_entries(archive)}
    exe = Exe(executable)
    definition = 0x502F80
    assert exe.cstr(exe.u32(definition)) == "warboar.lmp"
    names = [exe.cstr(exe.u32(definition + 8 + 8 * i)) for i in range(20)]
    assert exe.u32(definition + 8 + 8 * 20) == 0
    assert len(set(names)) == 20 and all(name.lower() in entries for name in names)
    rig = ObjectRig(executable, seed)
    emu, mem = rig.emu, rig.emu.mem
    calls = []

    def resolve(e):
        assert cstr(e.mem, e.r[4]) == "warboar.lmp"
        name = cstr(e.mem, e.r[5])
        assert name in entries
        calls.append(name)
        return e.alloc(4)  # a synthetic nonzero resource handle, not the game's pointer

    emu.stub(RES_FIND, function=resolve)
    mem.w32(0x41BF78, 1)
    for index in range(3):
        obj = rig.ecall(POOL_NEW, 0x3D8)
        pos = rig.vec(0, (W.f32(index * 10.0), W.f32(0), W.f32(0)))
        if index == 2:
            mem.w32(0x41BF78, 2)
        rig.ecall(OBJECT_A["GameObject_ctor"], obj, pos, definition, 0)
        assert mem.u32(definition + 4) == (2 if index == 2 else 1)
        assert len(calls) == (40 if index == 2 else 20)
    assert calls == names + names
    assert all(mem.u32(definition + 12 + 8 * i) != 0 for i in range(20))
    return len(names)


def check_terrain(executable, world_data, rows, seed):
    model = W.Level(world_data)
    rig = TerrainRig(executable, world_data)
    boars = [row for row in rows if row["class"] in ("WarBoar", "WarBoarSmall")]
    random.Random(seed).shuffle(boars)
    results = []
    for row in boars:
        pos = position(row)
        rig.put(rig.buf[0], pos)
        for radius in (12.0, 30.0):
            raw_radius = W.f32(radius)
            _ret, got = rig.call(A_HEIGHT, (rig.base, rig.buf[0]), (raw_radius,))
            want = W.terrain_height(model, raw_radius, pos)
            assert got == want, (row["index"], radius, got, want)
            results.append(got)
    return len(boars), len(set(results))


def check_start_grants(executable):
    # The original grant router runs, but parser/inventory/equip are stubs.
    # Model index +0x54 and debug switches 0x41b550..54 stay zero.
    # This class-only probe includes impossible class/model pairs; it does not
    # establish portable grants or equipped item records.
    for class_id in range(7):
        emu = EE(executable)
        emu.follow = {0x1ACC78}
        emu.mem.w32(0x4D8AF0 + 0x50, class_id)
        emu.call(0x1ACC78, 0, max_steps=1000000)
        count = collections.Counter(call.target for call in emu.calls)
        assert (count[0x1069B8], count[0x1C1868], count[0x1C27C0]) == R3.START_CALL_COUNTS[class_id]
        descriptors = [cstr(emu.mem, call.args[0]).split("+", 1)[0]
                       for call in emu.calls if call.target == 0x1069B8]
        assert tuple(descriptors[3:3 + len(R3.START_WEAPONS[class_id])]) == R3.START_WEAPONS[class_id]
    return len(R3.START_WEAPONS)


def check_loot(executable, row, seed):
    # Actual boar setState passes these values to Creature_dropLoot. Here its
    # downstream loot_generateDrops runs with one player/class 0/level 22.
    original = I.original(executable, fast=True)
    emu, mem, tables = original.emu, original.mem, I.tables(executable)
    observed = []
    emu.stub(I.F_SPAWN_GOLD, function=lambda e: observed.append(("gold", e.r[5])))
    emu.stub(I.F_POOL_NEW, ret=original.obj)
    emu.stub(I.F_PHPROP_CTOR,
             function=lambda e: observed.append((
                 I.LOOT_SITES[(e.r[31] - 8) & 0xFFFFFFFF], mem.read(e.r[11], 0x48))))
    emu.stub(I.F_PHPROP_PHYS)
    def cos16(e):
        observed.append(("throw", s32(e.r[4])))
        e.f[0] = IREF.F_ONE

    emu.stub(I.F_COS16, function=cos16)
    emu.stub(I.F_SIN16, function=lambda e: e.f.__setitem__(0, IREF.F_ZERO))
    game = IREF.Game(level=22.0)
    original.set_game(game, seed)
    mem.write(original.vec, struct.pack("<3I", *position(row)))
    original.call(I.F_LOOT, original.vec, row["angle"], 0, 0,
                  fregs=(IREF.f_bits(36), IREF.f_bits(2), IREF.f_bits(2.8),
                         0, IREF.f_bits(3), IREF.f_bits(0.25)), max_steps=3000000)
    world = I.ScriptedWorld(0, set())
    rng = IREF.Rng(seed)
    outcome = IREF.loot_generate_drops(tables, game, rng, world,
                                       IREF.f_bits(2.8), 0, IREF.f_bits(3),
                                       IREF.f_bits(0.25), row["angle"])
    assert len(observed) == len(world.drops)
    expected = [(kind, value if kind in ("gold", "throw") else value.pack(observed[index][1]))
                for index, (kind, value) in enumerate(world.drops)]
    assert observed == expected, (seed, [k for k, _v in observed], [k for k, _v in expected])
    assert mem.u32(I.G_SEED) == rng.seed
    assert not any(kind == "gold" for kind, _value in observed)
    return outcome, [kind for kind, _value in observed], rng.draws


def check_drop_dispatch(executable):
    # Class setState's 0x10f2c8 call reaches the base drop dispatcher. The
    # object uses a synthetic base ctor and recording property service.
    emu, boar = constructed(executable, "WarBoar")
    emu.follow = {0x10F2C8, 0x10D940}
    emu.mem.w32(boar + 0x34, put_string(emu, "WarBoar"))
    pos = emu.alloc(12)
    emu.reset_log()
    emu.call(0x10F2C8, boar, pos, 0, 0,
             fargs=(36.0, 2.0, 2.8, 0.0, 3.0, 0.25), max_steps=1000000)
    loot_calls = [call for call in emu.calls if call.target == I.F_LOOT]
    rank_calls = [call for call in emu.calls if call.target == 0x10D940]
    assert len(rank_calls) == 2 and all(not call.stubbed for call in rank_calls)
    assert len(loot_calls) == 1 and loot_calls[0].fargs[3] == 0
    return len(loot_calls)


def check_gold_credit(executable, seed):
    # A synthetic already-touched Gold amount; independent of the boar drop.
    emu = EE(executable)
    emu.follow = {0x1DC268, 0x1DCB80}
    pos = emu.alloc(12)
    emu.mem.w32(0x404464, seed)
    emu.mem.w32(0x4D8AE0, 1)
    emu.mem.w32(0x44FDCC, 100)
    emu.call(0x1DC268, 0, pos, 42, max_steps=100000)
    floater, pending, credited = 42, 0, 0
    first_credit = None
    previous_observed_floater = emu.mem.u32(0x86A900 + 0x1C)
    for frame in range(101, 171):
        emu.mem.w32(0x44FDCC, frame)
        emu.call(0x1DCB80, max_steps=100000)
        floater, pending, credited = R3.gold_credit(frame, 100, floater, pending, credited)
        assert emu.mem.u32(0x86A900 + 0x1C) == floater, frame
        assert emu.mem.u32(0x86ACE8) == pending, frame
        assert emu.mem.u32(0x4D8AF0 + 0xE4) == credited, frame
        observed_floater = emu.mem.u32(0x86A900 + 0x1C)
        if first_credit is None and previous_observed_floater and not observed_floater:
            first_credit = frame - 100
        previous_observed_floater = observed_floater
    assert credited == 42 and pending == 0
    assert first_credit is not None
    return first_credit


def check_one_world(executable, seed):
    # Two synthetic base GameObjects, with original Player and WarBoar
    # vtables, in one original grid/run-list system. Virtual runs are stubs.
    rig = ObjectRig(executable, seed)
    emu, mem = rig.emu, rig.emu.mem
    boar = rig.ecall(POOL_NEW, 0x3D8)
    player = rig.ecall(POOL_NEW, 0x600)
    for obj, x, vtable, flags, radius in ((boar, -940, 0x517CF0, 0x20, 30),
                                          (player, -930, 0x511308, 0x40, 12)):
        pos = rig.vec(0, (W.f32(x), W.f32(4501), W.f32(6)))
        rig.ecall(OBJECT_A["GameObject_ctor"], obj, pos, 0, 0)
        mem.w32(obj + 0x48, vtable)
        mem.w32(obj + 0xC, flags)
        mem.wf32(obj + 0x1C, radius)
        rig.ecall(OBJECT_A["obj_runEveryFrame"], obj)
    assert mem.u32(0x511308 + 4 * 8 + 4) == 0x1A5030
    assert mem.u32(0x517CF0 + 4 * 8 + 4) == 0x2BA3A0
    low = rig.vec(1, (W.f32(-980), W.f32(4460), W.f32(-20)))
    high = rig.vec(2, (W.f32(-900), W.f32(4540), W.f32(100)))
    out = emu.alloc(256 * 4)
    rig.ecall(OBJECT_A["world_collectObjectsInBox"], low, high, out, 256)
    found = [mem.u32(out + 4 * i) for i in range(3)]
    assert set(found[:2]) == {player, boar} and found[2] == 0
    runs = []
    emu.stub(0x1A5030, function=lambda e: runs.append(("player", e.r[4])))
    emu.stub(0x2BA3A0, function=lambda e: runs.append(("boar", e.r[4])))
    mem.w32(0x403A04, 500)
    mem.w32(0x44FDCC, 1)
    rig.ecall(OBJECT_A["runObjects"], max_steps=1000000)
    assert runs == [("player", player), ("boar", boar)]
    return len(found) - 1, len(runs)


def check_target_and_melee(executable, row, seed):
    # The player and boar share the original grid. Target selection, melee,
    # damage_apply and Creature_takeDamage run for real. Their constructors,
    # equipment recalculation and line-of-sight terrain answer are bounded
    # synthetic inputs, so this is not a level-loaded combat session.
    rig = ObjectRig(executable, seed)
    emu, mem = rig.emu, rig.emu.mem
    mem.w32(0x404464, seed)
    boar = rig.ecall(POOL_NEW, 0x3D8)
    player = rig.ecall(POOL_NEW, 0x600)
    bx, by, bz = position(row)
    for obj, pos, vtable, flags, radius in (
        (boar, (bx, by, bz), 0x517CF0, 0x20, 30),
        (player, (W.f32(W.to_float(bx) + 10), by, bz), 0x511308, 0x40, 12),
    ):
        rig.ecall(OBJECT_A["GameObject_ctor"], obj, rig.vec(0, pos), 0, 0)
        mem.w32(obj + 0x48, vtable)
        mem.w32(obj + 0xC, flags)
        mem.wf32(obj + 0x1C, radius)
    mem.w32(player + 0x3C8, 0)
    mem.w32(0x4D8AF0 + 0x43D8, player)
    mem.w8(0x4D8AF0 + 0x4C24, 1)  # boar team remains zero-initialized
    mem.wf32(boar + 0x3C0, 1000)
    mem.write(boar + 0xF8, mem.read(boar + 0x10, 12))
    mem.w32(0x44FDCC, 1)
    emu.follow = {0x10DED0, OBJECT_A["world_collectObjectsInBox"], 0x119328,
                  0x1A1738, 0x1A1698, 0x1A1868, 0x3C3B18, 0x3C2730}
    emu.call(0x10DED0, boar, 1, max_steps=1000000)
    target = mem.u32(boar + 0x234)
    assert target and mem.u32(target + 0xC) == player
    low = rig.vec(1, (W.f32(W.to_float(bx) - 48), W.f32(W.to_float(by) - 48),
                      W.f32(W.to_float(bz) - 72)))
    high = rig.vec(2, (W.f32(W.to_float(bx) + 48), W.f32(W.to_float(by) + 48),
                       W.f32(W.to_float(bz) + 72)))
    out = emu.alloc(256 * 4)
    rig.ecall(OBJECT_A["world_collectObjectsInBox"], low, high, out, 256)
    assert boar in [mem.u32(out + 4 * i) for i in range(3)]
    mem.wf32(boar + 0x228, 100)
    mem.wf32(boar + 0x22C, 100)

    def recalc(_emu):
        # A fixed unarmed range isolates the target/damage path from the
        # still-unloaded class-specific starter item records.
        mem.w32(0x4D8AF0 + 0xCC, 200)
        mem.w32(0x4D8AF0 + 0xD0, 15)
        mem.w32(0x4D8AF0 + 0xD4, 15)

    emu.follow = {0x1B6A98, 0x1E8230, 0x116638,
                  0x1A1738, 0x1A1698, 0x1A1868}
    emu.record_calls = True
    emu.stub(0x1B7158, function=recalc)
    emu.stub(0x18A5C0, function=lambda e: e.f.__setitem__(0, W.f32(-1.0)))
    emu.reset_log()
    emu.call(0x1B6A98, player, boar, 0, 0, fargs=(0.0,), max_steps=1000000)
    calls = [call.target for call in emu.calls]
    assert calls.index(0x1B7158) < calls.index(0x1E8230) < calls.index(0x116638)
    damage = 100 - mem.f32(boar + 0x228)
    assert damage > 0 and mem.f32(boar + 0xC8) == damage
    assert mem.u32(boar + 0x2DC) & 1
    attacker = mem.u32(boar + 0x2E4)
    assert attacker and mem.u32(attacker + 0xC) == player
    mem.w32(player + 0xC, 0x20040)
    emu.call(0x1B6A98, player, boar, 0, 0, fargs=(0.0,), max_steps=1000000)
    assert mem.f32(boar + 0x228) == 100 - damage
    return damage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable")
    parser.add_argument("valor_gob")
    parser.add_argument("valor_world")
    parser.add_argument("warboar_lmp")
    parser.add_argument("--seed", type=int, default=20973)
    args = parser.parse_args()
    with open(args.executable, "rb") as stream:
        assert hashlib.sha256(stream.read()).hexdigest() == EXPECTED_SHA256
    with open(args.valor_gob, "rb") as stream:
        rows = objects_from_file(args.valor_gob, stream.read())
    with open(args.valor_world, "rb") as stream:
        world_data = stream.read()
    with open(args.warboar_lmp, "rb") as stream:
        archive = stream.read()
    boar = next(row for row in rows if row["class"] == "WarBoar")
    resources = check_resources(args.executable, archive, args.seed)
    terrain = check_terrain(args.executable, world_data, rows, args.seed)
    grants = check_start_grants(args.executable)
    assert not any(key in row["properties"].lower()
                   for row in rows if row["class"] in ("WarBoar", "WarBoarSmall")
                   for key in ("dropitem=", "miniboss=", "noloot="))
    drop_calls = check_drop_dispatch(args.executable)
    loot = check_loot(args.executable, boar, args.seed)
    delay = check_gold_credit(args.executable, args.seed)
    shared = check_one_world(args.executable, args.seed)
    damage = check_target_and_melee(args.executable, boar, args.seed)
    print("PASS seed %d: %d resource names; %d boar positions x 2 radii (%d heights); "
          "%d class-only grant probes; %d boar drop dispatch; loot %s %s in %d draws; gold first credit +%d frames; "
          "shared grid/run %d/%d; bounded melee damage %.0f" % (args.seed, resources, terrain[0], terrain[1],
                                      grants, drop_calls, loot[0], loot[1], loot[2], delay,
                                      shared[0], shared[1], damage))


if __name__ == "__main__":
    main()
