#!/usr/bin/env python3
"""Round-4 bounded valor probes, using the original code in ee_emu.

PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_campaign_combat_r4.py \
    local/SLUS_209.73 local/VALOR.GOB local/WARBOAR.LMP --seed 20973

The real resource manager, saved character, and native client are not run.
Resource bytes stay in local/ and are never printed or tracked.
"""
import argparse
import collections
import hashlib
import struct

from dump_tables import lmp_entries, objects_from_file
from ee_emu import EE
from difftest_anim import Rig as AnimRig, PUSH
from difftest_campaign_combat import EXPECTED_SHA256, put_string
from difftest_campaign_combat_r2 import constructed
from difftest_campaign_combat_r3 import cstr, position
from difftest_objects import Rig as ObjectRig, A as OBJECT_A, POOL_NEW, SET_FACTORY
from ref_combat import Exe
import difftest_items as I
import ref_anim as ANIM
import ref_campaign_combat_r4 as R4
import ref_items as ITEMS


def check_grants(executable):
    for model, class_id in enumerate(R4.MODEL_CLASS):
        emu = EE(executable)
        emu.follow = {0x1ACC78}
        emu.mem.w32(0x4D8AF0 + 0x50, class_id)
        emu.mem.w32(0x4D8AF0 + 0x54, model)
        for switch in range(0x41B550, 0x41B555):
            emu.mem.w8(switch, 0)
        emu.call(0x1ACC78, 0, max_steps=1000000)
        count = collections.Counter(call.target for call in emu.calls)
        assert (count[0x1069B8], count[0x1C1868], count[0x1C27C0]) == R4.MODEL_CALL_COUNTS[model]
        descriptors = [cstr(emu.mem, call.args[0]).split("+", 1)[0]
                       for call in emu.calls if call.target == 0x1069B8]
        weapons = R4.MODEL_WEAPONS[model]
        assert tuple(descriptors[3:3 + len(weapons)]) == weapons
        assert emu.mem.u32(0x4D8AF0 + 0x4434) == 0  # equip stub makes no active set
    return len(R4.MODEL_CLASS)


def check_clips(executable, archive):
    exe = Exe(executable)
    definition = 0x502F80
    entries = {name.lower(): archive[off:off + size]
               for name, off, size in lmp_entries(archive)}
    rig = AnimRig(executable)
    checked = 0
    clips = {}
    for index in range(3, 20):
        name = exe.cstr(exe.u32(definition + 8 + 8 * index))
        clip = rig.load_clip(entries[name.lower()], name)
        assert clip.joint_count > 0 and clip.length > 0
        clips[index] = clip
        rig.emu.mem.w32(definition + 12 + 8 * index, rig.ptr(clip))

    obj = rig.emu.alloc(0x3D8)
    rig.emu.mem.w32(obj + 0x24, definition)
    ctor, _ = constructed(executable, "WarBoar")
    configured = []
    for call in ctor.calls:
        if call.target != 0x118378:
            continue
        index = call.args[1]
        # Entry n is the resource pointer at classDef + 4 + 8*n.
        clip = clips[index - 1]
        rig.call(0x118378, obj, index, *call.args[2:6], floats=call.fargs[:4])
        for slot in range(4):
            offset = rig.ptr(clip) + 0x14 + 8 * slot
            actual = [rig.emu.mem.u32(offset), rig.emu.mem.u8(offset + 4)]
            assert actual == [call.fargs[slot], call.args[2 + slot]]
            clip.events[slot] = actual
        configured.append(index)
    assert configured == [4, 5, 6, 7, 10, 11, 12]

    for index in range(3, 20):
        clip = clips[index]
        state = rig.new_state()
        rig.call(PUSH, rig.ptr(state), rig.ptr(clip), 0)
        ANIM.anim_push(state, clip, 0)
        for _ in range(3):
            rig.advance(state, ANIM.ONE, sound=False)
        checked += 1
    attack = rig.new_state()
    clip = clips[3]
    rig.call(PUSH, rig.ptr(attack), rig.ptr(clip), 0)
    ANIM.anim_push(attack, clip, 0)
    events = []
    for frame in range(60):
        bits, _dx, _dy, _yaw = rig.advance(attack, ANIM.ONE, sound=False)
        if bits:
            events.append((frame, bits))
    assert tuple(events) == R4.ATTACK_EVENTS
    return checked, len(configured), len(events)


def check_binding(executable, seed):
    # The original world_createObject returns the factory's one world-owned
    # address. The factory body is a recording stub; native binding is untested.
    rig = ObjectRig(executable, seed)
    obj = rig.ecall(POOL_NEW, 0x3D8)
    pos = rig.vec(0, (0, 0, 0))
    rig.ecall(OBJECT_A["GameObject_ctor"], obj, pos, 0, 0)
    rig.ecall(SET_FACTORY, rig.STUB_FACTORY)
    rig.emu.stub(rig.STUB_FACTORY, ret=obj)
    got = rig.ecall(OBJECT_A["world_createObject"],
                    rig.cstring(b"WarBoar"), pos, 0, 0)
    assert got == obj
    return 1


def check_minotaur_source(executable, row, seed):
    # Execute original death routing with synthetic model/creature state.
    emu = EE(executable)
    obj, model = emu.alloc(0x470), emu.alloc(0x100)
    emu.mem.w32(obj + 0x24, model)
    emu.mem.w32(obj + 0x34, put_string(emu, "Minotaur"))
    emu.mem.w32(obj + 0x48, 0x5165F0)
    emu.mem.w32(0x404464, seed)
    emu.follow = {0x28A16C, 0x10F2C8, 0x10D940}
    emu.call(0x28A16C, obj, 0x14, max_steps=500000)
    death = [call for call in emu.calls if call.target == 0x10F2C8]
    generated = [call for call in emu.calls if call.target == I.F_LOOT]
    expected = R4.MINOTAUR_LOOT_BITS
    assert len(death) == len(generated) == 1
    assert death[0].fargs[:6] == generated[0].fargs[:6] == expected

    # A fresh synthetic shared seed, one player, difficulty 1 and level 22.
    # Spawn/terrain/pool/Gold constructors are recording stubs here.
    original = I.original(executable, fast=True)
    observed = []
    original.emu.stub(I.F_SPAWN_GOLD,
                      function=lambda e: observed.append(("gold", e.r[5])))
    original.emu.stub(I.F_POOL_NEW, ret=original.obj)
    original.emu.stub(I.F_PHPROP_CTOR,
                      function=lambda e: observed.append((
                          I.LOOT_SITES[(e.r[31] - 8) & 0xFFFFFFFF],
                          original.mem.read(e.r[11], 0x48))))
    original.emu.stub(I.F_PHPROP_PHYS)
    def cos16(e):
        observed.append(("throw", e.r[4]))
        e.f[0] = ITEMS.F_ONE

    original.emu.stub(I.F_COS16, function=cos16)
    original.emu.stub(I.F_SIN16,
                      function=lambda e: e.f.__setitem__(0, ITEMS.F_ZERO))
    game = ITEMS.Game(level=22.0)
    original.set_game(game, seed)
    original.mem.write(original.vec, struct.pack("<3I", *position(row)))
    original.call(I.F_LOOT, original.vec, row["angle"], 0, 0,
                  fregs=expected, max_steps=3000000)
    world = I.ScriptedWorld(0, set())
    rng = ITEMS.Rng(seed)
    outcome = ITEMS.loot_generate_drops(
        I.tables(executable), game, rng, world,
        expected[2], expected[3], expected[4], expected[5], row["angle"])
    want = [(kind, value if kind in ("gold", "throw") else value.pack(observed[index][1]))
            for index, (kind, value) in enumerate(world.drops)]
    assert observed == want, (seed, observed, want)
    assert original.mem.u32(I.G_SEED) == rng.seed
    return outcome, sum(kind == "gold" for kind, _ in observed), rng.draws


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable")
    parser.add_argument("valor_gob")
    parser.add_argument("warboar_lmp")
    parser.add_argument("--seed", type=int, default=20973)
    args = parser.parse_args()
    with open(args.executable, "rb") as stream:
        assert hashlib.sha256(stream.read()).hexdigest() == EXPECTED_SHA256
    with open(args.valor_gob, "rb") as stream:
        rows = objects_from_file(args.valor_gob, stream.read())
    with open(args.warboar_lmp, "rb") as stream:
        archive = stream.read()
    minotaurs = [row for row in rows if row["class"] == "Minotaur"]
    assert minotaurs
    grants = check_grants(args.executable)
    clips, configured, events = check_clips(args.executable, archive)
    binding = check_binding(args.executable, args.seed)
    outcome, gold, draws = check_minotaur_source(args.executable, minotaurs[0], args.seed)
    print("PASS seed %d: %d valid model/class grant routes; %d original clip relocations,"
          " %d event setups, %d attack markers; %d factory address pass-through;"
          " Minotaur death -> Gold-capable loot, %d synthetic-seed Gold rolls, %s in %d draws" %
          (args.seed, grants, clips, configured, events, binding, gold, outcome, draws))


if __name__ == "__main__":
    main()
