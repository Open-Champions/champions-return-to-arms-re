#!/usr/bin/env python3
"""Additional bounded Minotaur execution, SLUS_209.73 US v2.00.

Execute with an owned ELF and --seed 20973 / 7. Original class instructions,
own RNG and designated base-constructor/state-filter/hit-forwarding bodies execute.
Animation, terrain, movement, base tick, holder effects and damage outcomes
are recording services. Authored pointers and branch answers are fixtures,
not captured game state. No whole-fight or PCSX2 result is claimed.
"""
import argparse
import hashlib
import itertools
import random
from pathlib import Path

from difftest_minotaur import definition_member, fixture, read_archives
from dump_tables import KNOWN_SHA256, find_in_lump
import ref_combat as combat
import ref_minotaur as contract

RAND, SEE, HIT = 0x1509D0, 0x118D40, 0x119938
FILTER, DAMAGE = 0x10A9C0, 0x1E8230
HOLDER_TABLE = 0x50CDA0


def s16(value):
    return (value + 0x8000) % 0x10000 - 0x8000


class Rig:
    def __init__(self, elf, seed):
        self.emu, self.actor = fixture(elf)
        self.mem = self.emu.mem
        self.seed = seed
        self.handle = self.emu.alloc(16)
        self.victim = self.emu.alloc(0x470)
        self.mem.w32(self.handle + 12, self.victim)
        self.reset()

    def slot(self, table, index):
        return self.mem.u32(table + index * 8 + 4)

    def reset(self, state=0, target=True, holder=True):
        self.mem.write(self.actor, bytes(0x470))
        for offset, word in ((0x24, contract.DEF), (0x48, contract.VTABLE),
                             (0x50, self.actor + 0x3C8 if holder else 0),
                             (0x3C8, HOLDER_TABLE), (0x44, self.seed),
                             (0x228, combat.f32(90.0)), (0x22C, combat.f32(100.0)),
                             (0x234, self.handle if target else 0), (0x300, 1000)):
            self.mem.w32(self.actor + offset, word)
        self.mem.w16(self.actor + 0x232, state)
        self.mem.w16(self.actor + 0x3AE, 500)
        self.mem.w32(0x404464, 0x12345678)
        self.emu.follow = {contract.TICK, RAND}
        self.emu.hooks.clear()
        self.emu.stub(0x10C0F0, ret=1)

    def sight(self, sites):
        self.emu.stub(SEE, function=lambda emu: int(emu.calls[-1].site in sites))

    def execute_tick(self):
        self.emu.reset_log()
        self.emu.call(contract.TICK, self.actor, max_steps=20000)
        assert self.mem.u32(0x404464) == 0x12345678
        return self.emu.calls

    def transitions(self):
        return [call.args[1] for call in self.emu.calls if call.target == contract.STATE]


def check_tick_order(elf, seed):
    rig, count = Rig(elf, seed), 0
    prefix = [0x3C2738, 0x110D30, 0x3C2738, 0x112948]
    for holder, stopped, active in itertools.product((False, True), repeat=3):
        rig.reset(23, holder=holder)
        rig.mem.w32(rig.actor + 0xF4, 2000)
        rig.emu.stub(0x3C2738, ret=0x730000)
        rig.emu.stub(0x112948, ret=int(stopped))
        rig.emu.stub(0x10C0F0, ret=int(active))
        calls = rig.execute_tick()
        expected = prefix[:]
        if not stopped:
            expected.append(0x10C0F0)
            if active:
                if holder:
                    expected.append(rig.slot(HOLDER_TABLE, 21))
                expected += [0x1162B0, 0x115EB8, 0x10DED0]
        assert [call.target for call in calls] == expected
        assert calls[1].args[:2] == (rig.actor, 0x730000)
        assert calls[3].args[:2] == (rig.actor, 0x730000)
        if not stopped and active:
            by_target = {call.target: call for call in calls}
            assert by_target[0x1162B0].fargs[0] == combat.ONE
            assert by_target[0x115EB8].fargs[0] == 0x3F333333
            assert by_target[0x10DED0].args[:2] == (rig.actor, 0)
            if holder:
                held = by_target[rig.slot(HOLDER_TABLE, 21)]
                assert held.args[:3] == (rig.actor + 0x3C8, contract.DEF, rig.actor)
                assert held.fargs[0] == 0x3F000000
        count += 1
    return count


def check_decision_edges(elf, seed):
    rig, count = Rig(elf, seed), 0
    # Each tuple names a service decision and its independently read outcome.
    for visible, away in itertools.product((0, 1), repeat=2):
        rig.reset(0)
        rig.mem.w32(rig.actor + 0x300, 100000)
        rig.emu.stub(0x10E658, ret=visible)
        rig.emu.stub(0x10EED8, ret=away)
        calls = rig.execute_tick()
        assert rig.transitions() == ([1] if visible or away else [])
        assert (0x10EED8 in [c.target for c in calls]) == (not visible)
        count += 1
    for visible, close in itertools.product((0, 1), repeat=2):
        rig.reset(1)
        rig.emu.stub(0x10E658, ret=visible)
        rig.sight({0x289660} if close else {})
        calls = rig.execute_tick()
        assert rig.transitions() == ([3] if visible and close else [])
        assert (0x119F38 in [c.target for c in calls]) == (not visible)
        cones = [c for c in calls if c.target == SEE]
        if visible:
            assert cones[0].fargs[:3] == (0, combat.f32(500.0), 0)
            assert cones[0].args[2:4] == (8000, 0)
        count += 1
    # Charge eligibility: the comparison is signed and strict at equality.
    for state, site, ranges in ((3, 0x2897AC, (60.0, 300.0)),
                                (5, 0x289B64, (300.0, 60.0))):
        for holder, hand, deadline in itertools.product((0, 1), (0, 1), (999, 1000, 1001)):
            rig.reset(state, holder=bool(holder))
            rig.mem.w32(rig.actor + 0x468, deadline)
            rig.emu.stub(rig.slot(HOLDER_TABLE, 14), ret=hand)
            rig.sight({site})
            calls = rig.execute_tick()
            eligible = not (holder and hand) and deadline < 1000
            assert rig.transitions() == ([12] if eligible else [])
            queried = [c for c in calls if c.target == SEE and c.site == site]
            assert bool(queried) == eligible
            if queried:
                assert queried[0].fargs[:3] == tuple(map(combat.f32, (*ranges, 0.0)))
            count += 1
    for draw in (0, 1):
        rig.reset(5)
        rig.emu.stub(rig.slot(HOLDER_TABLE, 14), ret=1)
        rig.emu.stub(RAND, ret=draw)
        rig.sight({0x28996C})
        rig.execute_tick()
        assert rig.transitions() == [7 + draw]
        count += 1
    # HP thresholds use PS2 multiplication; equality is outside the middle band.
    lower = combat.fmul(combat.f32(100.0), 0x3EA8F5C2)
    upper = combat.fmul(combat.f32(100.0), 0x3F28F5C2)
    for hp, middle in ((lower - 1, False), (lower, False), (lower + 1, True),
                       (upper - 1, True), (upper, False), (upper + 1, False)):
        for attacking, shield, draw in itertools.product((0, 1), (0, 1), (0, 1, 2)):
            rig.reset(5)
            rig.mem.w32(rig.actor + 0x228, hp)
            rig.emu.stub(rig.slot(HOLDER_TABLE, 14), function=lambda e: int(e.r[5] == 1 or shield))
            rig.emu.stub(0x118E90, ret=attacking)
            rig.emu.stub(RAND, ret=draw)
            rig.sight({0x289830, 0x28996C})
            rig.execute_tick()
            expected = 23 if middle and attacking and shield and draw % 3 else 6 if middle else 7 + (draw & 1)
            assert rig.transitions() == [expected], (hp, attacking, shield, draw)
            count += 1
    for state, flags, answer, expected in ((18, 0, 0, [3]), (18, 16, 0, []),
                                          (19, 0, 0, []), (19, 0, 1, [3]),
                                          (16, 0, 0, []), (16, 0, 1, [0])):
        rig.reset(state)
        rig.mem.w16(rig.actor + 0x11A, flags)
        rig.emu.stub(0x119608, ret=answer)
        rig.emu.stub(0x1195F0, ret=answer)
        calls = rig.execute_tick()
        assert rig.transitions() == expected
        assert (0x119F08 in [c.target for c in calls]) == (state == 16 and not answer)
        count += 1
    for deadline, age, expected in ((100, 100, []), (100, 101, [3]),
                                    (0xFFFFFFFF, 0, [3]), (0, 0x80000000, [])):
        rig.reset(23)
        rig.mem.w32(rig.actor + 0xF4, deadline)
        rig.mem.w32(rig.actor + 0x300, age)
        rig.execute_tick()
        assert rig.transitions() == expected
        count += 1
    return count


def check_charge(elf, seed):
    rig, rng, count = Rig(elf, seed), random.Random(seed), 0
    for moving, overlay_present, close, far, target, events, flags in itertools.product(
            (0, 1), (0, 1), (0, 1), (0, 1), (0, 1), (0, 1), (0, 8, 16, 24)):
        rig.reset(12, target=bool(target))
        own = rng.getrandbits(32)
        rig.mem.w32(rig.actor + 0x44, own)
        rig.mem.w32(rig.actor + 0x468, 777)
        rig.mem.w16(rig.actor + 0x11A, flags)
        rig.mem.w16(rig.actor + 0x38, 0xF123)
        for offset, value in ((0xD0, -7), (0xD2, 117), (0xD4, 311)):
            rig.mem.w16(rig.actor + offset, value & 0xFFFF)
        rig.emu.stub(0x1162B0, ret=events)
        rig.emu.stub(0x170D88, function=lambda e: moving if e.r[5] == 0x701000 else overlay_present)
        rig.sight(({0x289F18} if close else set()) | ({0x289FF0} if far else set()))
        calls = rig.execute_tick()
        present = [c.args[1] for c in calls if c.target == 0x170D88]
        assert present == ([0x701000, 0x700C00] if moving else [0x701000])
        animations = [c for c in calls if c.target in (contract.CHANGE, contract.BLEND)]
        overlay = bool(moving and not overlay_present and close)
        assert len(animations) == (2 if overlay else 0)
        if overlay:
            assert [(c.target, c.args[:3]) for c in animations] == [
                (contract.CHANGE, (rig.actor + 0x114, 0x700F00, 0x803)),
                (contract.BLEND, (rig.actor + 0x114, 0x700C00, 0x818))]
            assert animations[0].fargs[0] == contract.TENTH
            assert animations[1].fargs[:2] == (contract.TENTH, contract.TENTH)
        hits = [c for c in calls if c.target == HIT]
        assert len(hits) == int(bool(target and events))
        if hits:
            assert tuple(s16(x) for x in hits[0].args[1:6]) == (-3805, 8000, -7, 117, 311)
            assert hits[0].args[6:8] == (0x100041, 0)
            assert hits[0].fargs[:2] == (0, combat.f32(36.0))
        continues = bool(flags & 8 and (flags & 16 or far))
        assert rig.transitions() == ([] if continues else [3])
        expected = combat.Seed(own)
        deadline = 777 if continues else 1000 + expected.draw() % 180 + 300
        assert rig.mem.u32(rig.actor + 0x468) == deadline
        assert rig.mem.u32(rig.actor + 0x44) == expected.state
        count += 1
    return count


def check_hit_forwarding(elf, seed):
    rig, rng, count = Rig(elf, seed), random.Random(seed), 0
    for state, target, visible, holder in itertools.product(
            range(6, 12), (0, 1), (0, 1), (0, 1)):
        rig.reset(state, target=bool(target), holder=bool(holder))
        rig.emu.follow.add(HIT)
        rig.emu.follow.add(rig.slot(HOLDER_TABLE, 17))
        descriptor = rig.actor + 0x418
        rig.emu.stub(0x1162B0, ret=1)
        rig.emu.stub(0x10C810, ret=visible)
        rig.mem.w16(rig.actor + 0x11A, 8)
        facing = rng.randrange(-32768, 32768)
        values = [rng.randrange(-32768, 32768) for _ in range(3)]
        rig.mem.w16(rig.actor + 0x38, facing & 0xFFFF)
        for offset, value in zip((0xD0, 0xD2, 0xD4), values):
            rig.mem.w16(rig.actor + offset, value & 0xFFFF)
        calls = rig.execute_tick()
        damage = [c for c in calls if c.target == DAMAGE]
        assert len(damage) == int(bool(target and visible))
        if damage:
            expected_desc = descriptor if holder and state != 6 else 0
            assert tuple(x & 0xFFFFFFFF for x in damage[0].args) == (
                rig.victim, rig.actor, values[2] & 0xFFFFFFFF, 0, 0,
                contract.ATTACK_FLAGS[state], expected_desc, 0)
            assert damage[0].fargs[:2] == tuple(map(combat.itof, values[:2]))
        seen = [c for c in calls if c.target == 0x10C810]
        if target:
            assert tuple(x & 0xFFFFFFFF for x in seen[0].args[:5]) == (
                rig.actor, rig.victim, facing & 0xFFFFFFFF, 8000, 0)
            assert seen[0].fargs[:3] == (0, combat.f32(36.0), 0)
        assert len(seen) == target
        assert rig.transitions() == []
        count += 1
    return count


def check_filter_composition(elf, seed):
    rig, count = Rig(elf, seed), 0
    # requested, root, stun, cooldown, target, inert, accepted state
    cases = ((3, 0, 0, 0, 1, 0, 3), (3, 1, 0, 0, 1, 0, 5),
             (3, 1, 0, 0, 0, 0, 0), (3, 0, 1, 0, 1, 0, 19),
             (3, 0, 0, 1, 1, 0, 16), (3, 0, 0, 1, 0, 0, 3),
             (3, 1, 1, 1, 1, 0, 5), (6, 1, 1, 0, 1, 0, 19),
             (20, 1, 1, 1, 1, 0, 20), (0, 0, 0, 0, 1, 0, 0),
             (1, 0, 0, 0, 1, 1, None))
    for requested, root, stun, cooldown, target, inert, expected in cases:
        rig.reset(5, target=bool(target))
        rig.emu.follow = {contract.STATE, FILTER, 0x1195E0, 0x119608, 0x1195F0, RAND}
        rig.mem.w8(rig.actor + 0x231, inert)
        rig.mem.w64(rig.actor + 0xA8, 0x200)
        for offset, value in ((0x314, root), (0x31C, stun), (0x318, cooldown)):
            rig.mem.w16(rig.actor + offset, value)
        rig.emu.reset_log()
        rig.emu.call(contract.STATE, rig.actor, requested, max_steps=20000)
        assert rig.mem.u16(rig.actor + 0x232) == (5 if expected is None else expected), (
            requested, root, stun, cooldown, target, inert, expected,
            rig.mem.u16(rig.actor + 0x232))
        assert rig.mem.u64(rig.actor + 0xA8) == (0x200 if expected is None else 0)
        if expected == 20:
            assert [rig.mem.u16(rig.actor + offset) for offset in (0x314, 0x318, 0x31C)] == [0, 0, 0]
        if expected == 0:
            assert rig.mem.u32(rig.actor + 0x234) == 0
        assert rig.mem.u32(0x404464) == 0x12345678
        count += 1
    return count


def check_death_and_draw(elf, seed):
    rig, rng, count = Rig(elf, seed), random.Random(seed), 0
    for holder, own in itertools.product((False, True), (seed, seed ^ 0xFFFFFFFF)):
        rig.reset(5, holder=holder)
        rig.emu.follow = {contract.STATE, RAND}
        rig.mem.w32(rig.actor + 0x44, own)
        rig.mem.w64(rig.actor + 0xA8, 0x200)
        position = tuple(rng.getrandbits(32) for _ in range(3))
        for offset, word in zip((0x10, 0x14, 0x18), position):
            rig.mem.w32(rig.actor + offset, word)
        rig.mem.w16(rig.actor + 0x38, 0xFFEC)
        snapshots = []

        def observe(emu):
            record = emu.calls[-1]
            vector = tuple(emu.mem.u32(record.args[1] + 4 * i) for i in range(3)) if record.target == 0x10F2C8 else ()
            snapshots.append((record.target, emu.mem.u16(rig.actor + 0x232), vector))
            return 0

        for address in (0x10F2C8, 0x11BC90, contract.CHANGE, 0x10BEB8):
            rig.emu.stub(address, function=observe)
        rig.emu.reset_log()
        rig.emu.call(contract.STATE, rig.actor, 20, max_steps=20000)
        expected_order = [0x10F2C8] + ([0x11BC90] * 2 if holder else []) + [contract.CHANGE, 0x10BEB8]
        assert [s[0] for s in snapshots] == expected_order
        assert all(s[1] == 5 for s in snapshots)
        assert snapshots[0][2] == position
        calls = rig.emu.calls
        loot = next(c for c in calls if c.target == 0x10F2C8)
        assert tuple(x & 0xFFFFFFFF for x in loot.args[:4]) == (rig.actor, loot.args[1], 0xFFFFFFEC, 0)
        assert loot.fargs[:6] == (0x42100000, 0x40000000, 0x3FCCCCCC, 0x3F199999, 0x3FB33333, 0x3E800000)
        parts = [c for c in calls if c.target == 0x11BC90]
        expected_parts = [(rig.actor + 0x3C8, hand, rig.actor, 0, 0) for hand in (1, 2)] if holder else []
        assert [c.args[:5] for c in parts] == expected_parts
        expected_rng = combat.Seed(own)
        clip = 10 + (expected_rng.draw() & 1)
        change = next(c for c in calls if c.target == contract.CHANGE)
        assert change.args[:3] == (rig.actor + 0x114, 0x700000 + clip * 0x100, 0x806)
        assert rig.mem.u32(rig.actor + 0x44) == expected_rng.state
        assert rig.mem.u16(rig.actor + 0x232) == 20
        assert rig.mem.u64(rig.actor + 0xA8) == 0
        count += 1
    for holder, result in itertools.product((False, True), (0, 0x750000)):
        rig.reset(holder=holder)
        rig.emu.follow = {0x289400}
        rig.emu.stub(0x3C2738, ret=0x730000)
        rig.emu.stub(0x10B048, ret=result)
        rig.emu.reset_log()
        rig.emu.call(0x289400, rig.actor, max_steps=20000)
        calls = rig.emu.calls
        expected_order = [0x3C2738, 0x10B048, 0x3C2738]
        if holder:
            expected_order.append(rig.slot(HOLDER_TABLE, 18))
        assert [c.target for c in calls] == expected_order
        assert calls[1].args[:4] == (rig.actor, 0x730000, 0x700100, 0)
        if holder:
            assert calls[3].args[:4] == (rig.actor + 0x3C8, contract.DEF, 0x730000, result)
        count += 1
    # Hit-reaction equipment loss is strictly below the lower HP threshold.
    lower = combat.fmul(combat.f32(100.0), 0x3EA8F5C2)
    for hp, holder in itertools.product((lower - 1, lower, lower + 1), (False, True)):
        rig.reset(5, holder=holder)
        rig.emu.follow = {contract.STATE}
        rig.mem.w32(rig.actor + 0x228, hp)
        rig.emu.reset_log()
        rig.emu.call(contract.STATE, rig.actor, 18, max_steps=20000)
        parts = [c.args[1] for c in rig.emu.calls if c.target == 0x11BC90]
        assert parts == ([1, 2] if holder and hp < lower else [])
        count += 1
    # Corpse tick forwards its saved events, a zero offset and height 20.
    for events in (0, 1, 0x135):
        rig.reset(20)
        rig.emu.stub(0x1162B0, ret=events)
        calls = rig.execute_tick()
        corpse = next(c for c in calls if c.target == 0x1108A0)
        assert corpse.args[:2] == (rig.actor, events)
        assert corpse.args[3] == 0 and corpse.fargs[0] == combat.f32(20.0)
        assert [rig.mem.u32(corpse.args[2] + i * 4) for i in range(3)] == [0, 0, 0]
        assert rig.transitions() == []
        count += 1
    return count


def check_base_flags(elf, seed):
    rig, rng, count = Rig(elf, seed), random.Random(seed), 0
    name, position, properties = rig.emu.alloc(16), rig.emu.alloc(12), rig.emu.alloc(4)
    rig.mem.write(name, b'MiNoTaUr\0')
    for inherited, miniboss, ignore, light in itertools.product((0, rng.getrandbits(64)), (0, 1), (0, 1), (0, 1)):
        rig.reset()
        rig.emu.follow = {contract.CTOR, 0x109D68, 0x14CB10, contract.STATE,
                          0x3B81A0, 0x11BC18, RAND}
        rig.mem.w64(rig.actor + 0xA8, inherited)
        words = tuple(combat.f32(rng.uniform(-100.0, 100.0)) for _ in range(3))
        for index, word in enumerate(words):
            rig.mem.w32(position + 4 * index, word)
        facing = rng.getrandbits(32)
        overrides = {'miniboss': miniboss, 'ignoredamage': ignore, 'light1': light}

        def property_value(emu):
            address = emu.r[5]
            text = bytearray()
            while emu.mem.u8(address + len(text)):
                text.append(emu.mem.u8(address + len(text)))
                assert len(text) < 128
            return overrides.get(text.decode('ascii').lower(), 0)

        rig.emu.stub(0x14C880, function=property_value)
        rig.emu.stub(0x14F4C0, function=property_value)
        rig.emu.reset_log()
        rig.emu.call(contract.CTOR, rig.actor, name, position, facing, properties, max_steps=30000)
        want = inherited | 0x200040000 | miniboss
        if ignore:
            want |= 0x1000000000000
        if light:
            want |= 0x40000000
        assert rig.mem.u64(rig.actor + 0xA8) == want & ~0x200
        assert rig.mem.u16(rig.actor + 0x38) == facing & 0xFFFF
        assert tuple(rig.mem.u32(rig.actor + offset) for offset in (0x10, 0x14, 0x18)) == words
        assert rig.mem.u32(rig.actor + 0x2C) == properties
        assert rig.mem.u32(rig.actor + 0x24) == contract.DEF
        assert rig.mem.u16(rig.actor + 0x3AC) == 300
        assert rig.mem.u16(rig.actor + 0x3AE) == 500
        assert rig.mem.u16(rig.actor + 0x3B0) == 0x4000
        assert rig.mem.u32(rig.actor + 0x3C0) == combat.f32(1000.0)
        assert rig.mem.u32(rig.actor + 0xE8) in (1, 2)
        count += 1
    return count


def check_hide_masks(elf, archive):
    rig = Rig(elf, 0)
    exe = combat.Exe(str(elf))
    model = find_in_lump(archive, definition_member(exe, 0).casefold())
    assert model is not None and len(model) >= 0x30
    address = rig.emu.alloc(len(model))
    rig.mem.write(address, model)
    rig.emu.follow = {0x179550}
    base = ~rig.mem.u64(address + 8) & 0xFFFFFFFFFFFFFFFF
    enabled = rig.mem.u16(address + 0x10) & 2
    start = address + 16 * rig.mem.u8(address + 0x21)
    for variant in (0, 1, 2, 4):
        expected = base
        if enabled:
            for bit in range(variant.bit_length()):
                if variant & (1 << bit):
                    row = start + bit * 16
                    assert row + 16 <= address + len(model)
                    expected = (expected | rig.mem.u64(row)) & ~rig.mem.u64(row + 8)
        actual = rig.emu.call(0x179550, address, variant, max_steps=2000)
        assert actual == expected
        print(f'private definition index 0: selector {variant}, mask 0x{actual:016x}', flush=True)
    return 4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--iso', type=Path, help='also execute hide masks on the private Minotaur model')
    args = parser.parse_args()
    assert hashlib.sha256(args.elf.read_bytes()).hexdigest() == KNOWN_SHA256
    total = 0
    for check in (check_tick_order, check_decision_edges, check_charge,
                  check_hit_forwarding, check_filter_composition, check_death_and_draw,
                  check_base_flags):
        count = check(args.elf, args.seed)
        total += count
        print(f'seed {args.seed}: {check.__name__}: {count} cases, zero mismatches', flush=True)
    if args.iso:
        count = check_hide_masks(args.elf, read_archives(args.elf, args.iso)['actor'])
        total += count
        print(f'seed {args.seed}: check_hide_masks: {count} cases, zero mismatches', flush=True)
    print(f'seed {args.seed}: {total} added bounded cases, zero mismatches')


if __name__ == '__main__':
    main()
