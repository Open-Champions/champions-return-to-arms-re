#!/usr/bin/env python3
"""Address-only US v2.00 probes for loot construction and pickup boundaries.

The EE executes the named bodies; external resource, terrain and animation
services are explicitly synthetic. No assets or decoded descriptor text are
written. This is not an integrated physics or retail gameplay test.
"""
import argparse
import hashlib
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, float_to_raw as bits, raw_to_float as number  # noqa: E402

SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
PLAYERS, STRIDE, SHARED = 0x4d8af0, 0x4c30, 0x404464


def calls(machine, address):
    return [call for call in machine.calls if call.target == address]


def machine(elf, seed, follow=()):
    emu = EE(elf)
    emu.follow = set(follow)
    emu.mem.w32(SHARED, seed)
    return emu


def vector(emu, address, values):
    for index, value in enumerate(values):
        emu.mem.w32(address + 4 * index, bits(value))


def floats(emu, address, count=3):
    return tuple(number(emu.mem.u32(address + 4 * i)) for i in range(count))


def gold_cases(elf, seed):
    count = 0
    # Gold retains the real base object's radius/height, not a guessed sphere.
    emu = machine(elf, seed, (0x14cb10,))
    obj, pos = emu.alloc(0xc0), emu.alloc(12)
    vector(emu, pos, (10, 20, 30))
    emu.mem.w32(0x44fdcc, 100)
    emu.call(0x157668, obj, pos, 9)
    assert floats(emu, obj + 0x10) == (10, 20, 30)
    assert floats(emu, obj + 0x1c, 2) == (24, 72)
    assert emu.mem.u32(obj + 0xc) == 0x220c
    assert emu.mem.u32(obj + 0x48) == 0x511a88
    assert emu.mem.u8(obj + 0x4c) == 41
    assert emu.mem.u32(obj + 0x50) == 100
    assert emu.mem.u32(obj + 0x80) == 9
    assert emu.mem.u32(SHARED) == (seed * 0x19660d + 0x3c6ef35f) & 0xffffffff
    assert calls(emu, 0x170838)[0].args[:3] == (obj + 0x58, 0, 0x204)
    assert len(calls(emu, 0x14f248)) == 1
    count += 1
    player = emu.alloc(0x500)
    emu.mem.w32(player + 0x3c8, 1)
    for flags, amount, delay, accepted in ((0x40, 9, 1, False),
                                            (0x20040, 9, 0, False),
                                            (0, 9, 0, False),
                                            (0x40, 0, 0, False),
                                            (0x40, 9, 0, True)):
        emu.reset_log()
        emu.mem.w32(player + 0xc, flags)
        emu.mem.w32(obj + 0x80, amount)
        emu.mem.w8(obj + 0x4c, delay)
        emu.call(0x157a9c, obj, player)
        assert len(calls(emu, 0x1dc268)) == int(accepted)
        assert len(calls(emu, 0x14f200)) == int(accepted)
        assert emu.mem.u32(obj + 0x80) == (0 if accepted else amount)
        if accepted:
            assert calls(emu, 0x1dc268)[0].args[0::2][:2] == (1, amount)
        count += 1
    for delay, done, expected in ((41, False, 40), (1, False, 0),
                                  (41, True, 0), (0, False, 0)):
        emu.reset_log()
        emu.mem.w8(obj + 0x4c, delay)
        emu.mem.w16(obj + 0x5e, 0x80 if done else 0)
        emu.call(0x157b58, obj)
        assert emu.mem.u8(obj + 0x4c) == expected
        assert len(calls(emu, 0x14f290)) == int(done and delay != 0)
        count += 1
    # A full eight-floater queue credits immediately, with the original cap.
    for balance, amount, expected in ((500, 9, 509), (99999995, 9, 99999999)):
        emu = machine(elf, seed)
        pos = emu.alloc(12)
        emu.mem.map(0x86a000, 0x2000)
        for slot in range(8):
            emu.mem.w32(0x86a91c + slot * 0x24, 1)
        emu.mem.w32(PLAYERS + 0xe4, balance)
        emu.call(0x1dc268, 0, pos, amount)
        assert emu.mem.u32(PLAYERS + 0xe4) == expected
        assert not calls(emu, 0x165ee0)
        count += 1
    return count


def contact_cases(elf, seed):
    count = 0
    # Only the broad-phase candidate service is supplied. Actual movement calls
    # Gold's real virtual slot 6, which requests the real HUD floater and credit.
    for radius, entry in ((12, 0x113c48), (24, 0x113c48),
                          (12, 0x14d4b8), (24, 0x14d4b8)):
        for distance, delay, ghost in ((radius + 23.99, 0, False),
                                       (radius + 24, 0, False),
                                       (0, 0, False),
                                       (1, 1, False), (1, 0, True)):
            emu = machine(elf, seed, (0x157668, 0x14cb10, 0x157a9c, 0x1dc268))
            gold, player = emu.alloc(0xc0), emu.alloc(0x600)
            pos, velocity = emu.alloc(12), emu.alloc(12)
            emu.mem.map(0x86a000, 0x2000)
            emu.call(0x157668, gold, pos, 9)
            emu.mem.w32(gold + 0x10, bits(distance))
            emu.mem.w8(gold + 0x4c, delay)
            emu.mem.w32(player + 0xc, 0x20040 if ghost else 0x40)
            emu.mem.w32(player + 0x48, 0x511308)
            emu.mem.w32(player + 0x1c, bits(radius))
            emu.mem.w32(player + 0x20, bits(72))
            emu.mem.w32(PLAYERS + 0xe4, 500)

            def query(m):
                m.mem.w32(m.r[6], gold)
                m.mem.w32(m.r[6] + 4, 0)

            def project(m):
                vector(m, m.r[4], (1, 1, 1))
                m.f[0] = bits(100)

            emu.stub(0x14a928, function=query)
            emu.stub(0x165ee0, function=project)
            emu.reset_log()
            emu.mem.w32(0x44fdcc, 100)
            emu.call(entry, player, velocity, 0, 0)
            touched = distance + number(0x3a83126e) < radius + 24
            accepted = touched and not delay and not ghost
            assert len(calls(emu, 0x157a9c)) == int(touched and
                not (ghost and entry == 0x14d4b8))
            assert len(calls(emu, 0x1dc268)) == int(accepted)
            assert emu.mem.u32(PLAYERS + 0xe4) == 500
            if accepted:
                # 3 * age >= 128: pending transfer starts at age 43. Each
                # subsequent tick credits ceil(pending / 8), not the whole sum.
                for age in range(43):
                    emu.mem.w32(0x44fdcc, 100 + age)
                    emu.call(0x1dcb80)
                    assert emu.mem.u32(PLAYERS + 0xe4) == 500
                emu.mem.w32(0x44fdcc, 143)
                emu.call(0x1dcb80)
                assert emu.mem.u32(PLAYERS + 0xe4) == 502
                assert emu.mem.u32(0x86ace8) == 7
                for age in range(144, 151):
                    emu.mem.w32(0x44fdcc, age)
                    emu.call(0x1dcb80)
                assert emu.mem.u32(PLAYERS + 0xe4) == 509
                assert emu.mem.u32(0x86ace8) == 0
            count += 1
    return count


def contact_grid_cases(elf, seed):
    # Run the actual grid/handle services as well as the ordinary movement
    # dispatch. Ground and projected screen position are authored fixtures.
    for distance, height, ghost, accepted in ((35.99, 0, False, True),
                                             (36, 0, False, False),
                                             (0, 0, False, True),
                                             (1, 0, True, False),
                                             (1, 500, False, True),
                                             (1, 1001, False, False)):
        emu = EE(elf)
        for address in (0x1707b0, 0x17377c, 0x170838, 0x214230, 0x17365c):
            emu.stub(address)
        emu.stub(0x1834a8, function=lambda m: m.f.__setitem__(0, bits(0)))

        def project(m):
            vector(m, m.r[4], (1, 1, 1))
            m.f[0] = bits(100)

        emu.stub(0x165ee0, function=project)
        emu.mem.map(0x86a000, 0x2000)
        emu.mem.w32(SHARED, seed)
        emu.call(0x1a17d0)  # original handle-node pool initialization
        player, gold = emu.alloc(0x500), emu.alloc(0xc0)
        pos, gold_pos, velocity = emu.alloc(12), emu.alloc(12), emu.alloc(12)
        vector(emu, gold_pos, (distance, 0, height))
        emu.call(0x14cb10, player, pos, 0, 0)
        emu.call(0x157668, gold, gold_pos, 9)
        emu.mem.w32(player + 0xc, 0x20040 if ghost else 0x40)
        emu.mem.w32(player + 0x1c, bits(12))  # Player_ctor store at 0x1a2244
        emu.mem.w8(gold + 0x4c, 0)  # ready state; countdown is tested separately
        emu.reset_log()
        emu.call(0x14d4b8, player, velocity, 0, 0)
        assert len(calls(emu, 0x1dc268)) == int(accepted)
        assert emu.mem.u32(gold + 0x80) == (0 if accepted else 9)
        assert calls(emu, 0x14a928) and not calls(emu, 0x14a928)[0].stubbed
        assert len(calls(emu, 0x14f200)) == int(accepted)
        assert all(not call.stubbed for call in calls(emu, 0x14f200))
        if accepted:
            emu.reset_log()
            emu.call(0x14d4b8, player, velocity, 0, 0)
            assert not calls(emu, 0x1dc268)  # deferred deletion cannot award twice
    return 6


def interaction_cases(elf, seed):
    scenarios = ((0, 0, 0, 0x20, False), (0, 0x20, 0, 0x20, False),
                 (0x20, 0, 0, 0x20, True), (0x20, 0, 1, 0x20, False),
                 (0x20, 0, 0, 0x8000, False), (0x8000, 0, 0, 0x8000, True))
    for pressed, held, display, binding, activated in scenarios:
        emu = machine(elf, seed)
        player, obj, pad, table = (emu.alloc(n) for n in (0x600, 0x190, 0x80, 0x80))
        emu.mem.w32(PLAYERS + 0x43d8, player)
        emu.mem.w32(PLAYERS + 0xac, bits(1))
        emu.mem.w32(0x4d8ae0, 1)
        emu.mem.w32(obj + 0xc, 0x100000)
        emu.mem.w32(obj + 0x48, table)
        emu.mem.w32(table + 0x6c, 0xf00000)
        emu.mem.w32(table + 0x74, 0xf00010)
        emu.mem.w32(pad + 12, pressed)
        emu.mem.w32(pad + 8, held)
        emu.mem.w32(0x41b9c0, binding)

        def query(m):
            assert floats(m, m.r[4]) == (-48, -48, 0)
            assert floats(m, m.r[5]) == (48, 48, 60)
            assert m.r[7] == 256
            m.mem.w32(m.r[6], obj)
            m.mem.w32(m.r[6] + 4, 0)

        def prompt(m):
            m.mem.w16(m.r[5], 63)  # synthetic nonempty prompt, not game text
            return 1

        emu.stub(0x14a928, function=query)
        emu.stub(0xf00000, function=prompt)
        emu.call(0x1b2640, player, pad, display)
        assert len(calls(emu, 0xf00000)) == 1
        assert len(calls(emu, 0xf00010)) == int(activated)
    return len(scenarios)


def constructor_cases(elf, seed):
    count = 0
    for entry in (0x155a0c, 0x1590ec, 0x1592bc):
        emu = machine(elf, seed, (0x14cb10, 0x153e54, 0x153ac0,
                                  0x1541a0, 0x155110, 0x1509d0, 0x3b868c,
                                  0x1083f8))
        obj, pos, item, definition = (emu.alloc(n) for n in (0x248, 12, 0x48, 0x40))
        matrix = emu.alloc(0x30)
        vector(emu, pos, (10, 20, 30))
        vector(emu, matrix, (1, 0, 0, 0, 1, 0, 0, 0, 1, 10, 20, 30))
        emu.mem.w32(item, definition)
        emu.mem.w16(definition + 0x34, 2)
        # Synthetic resource handles, with actual item-to-index lookup and
        # table addressing. A real archive's bytes are not embedded here.
        handles = iter((0x710000, 0x720000))
        emu.stub(0x17365c, function=lambda m: next(handles, 0))

        def bounds(m):
            for pointer, value in zip(m.r[6:12], (-2, -3, -4, 4, 5, 8)):
                m.mem.w32(pointer, value)

        emu.stub(0x179400, function=bounds)
        if entry == 0x155a0c:
            emu.call(entry, obj, pos, 0x520030, emu.mem.u32(0x3e9d00),
                     emu.mem.u32(0x3e9d04), 1, 0x441, item, fargs=(1,))
        else:
            emu.call(entry, obj, pos, item, 0 if entry == 0x1590ec else matrix)
        assert emu.mem.read(obj + 0x148, 0x48) == emu.mem.read(item, 0x48)
        assert emu.mem.u32(obj + 0x4c) == 0x710000
        assert emu.mem.u32(obj + 0x50) == 0x720000
        assert emu.mem.u32(SHARED) == (seed * 0x19660d + 0x3c6ef35f) & 0xffffffff
        resource_calls = calls(emu, 0x17365c)
        assert len(resource_calls) >= 2
        assert emu.mem.cstr(resource_calls[0].args[0]) == emu.mem.cstr(
            0x520030 if entry == 0x155a0c else 0x5326b0)
        assert emu.mem.cstr(resource_calls[0].args[1]) == emu.mem.cstr(emu.mem.u32(0x3e9d00))
        assert emu.mem.cstr(resource_calls[1].args[1]) == emu.mem.cstr(emu.mem.u32(0x3e9d04))
        assert emu.mem.u32(obj + 0xc) & 0x100000
        assert not (emu.mem.u32(obj + 0xc) & 0x800)
        if entry == 0x155a0c:
            assert emu.mem.u64(obj + 0xe8) == 1
            assert emu.mem.u8(obj + 0x238) == 1
            assert emu.mem.u32(obj + 0x240) == bits(1)
            assert emu.mem.u16(obj + 0x10e) == 180
            assert len(calls(emu, 0x1509d0)) == 8
            assert len(calls(emu, 0x1682f0)) == 1
            assert len(calls(emu, 0x14f248)) == 1
        elif entry == 0x1590ec:
            assert len(calls(emu, 0x1541a0)) == 1
            assert len(calls(emu, 0x163b30)) == 1
            assert len(calls(emu, 0x1682f0)) == 0
        else:
            assert emu.mem.read(obj + 0x110, 0x30) == emu.mem.read(matrix, 0x30)
            assert not calls(emu, 0x179400)  # settled transform is supplied
            assert not calls(emu, 0x14f248)
        count += 1
    # Model bounds: signed-byte mesh bounds; one bit per included mesh.
    for mask, expected in ((1, (-2, -3, -4, 4, 5, 8)),
                            (2, (-10, -11, -12, 13, 14, 15)),
                            (3, (-10, -11, -12, 13, 14, 15))):
        emu = machine(elf, seed)
        model, outputs = emu.alloc(0x80), [emu.alloc(4) for _ in range(6)]
        emu.mem.w8(model + 0x12, 2)
        emu.mem.w8(model + 0x26, 0)
        emu.mem.write(model + 0x28, bytes(v & 255 for v in (-2, -3, -4, 4, 5, 8)))
        emu.mem.write(model + 0x32, bytes(v & 255 for v in (-10, -11, -12, 13, 14, 15)))
        emu.call(0x179400, model, mask, *outputs)
        assert tuple(emu.mem.s32(pointer) for pointer in outputs) == expected
        count += 1
    return count


def loot_argument_cases(elf, seed):
    emu = machine(elf, seed, (0x1083f8,))
    obj, pos, definition = emu.alloc(0x248), emu.alloc(12), emu.alloc(0x40)
    emu.mem.w16(definition + 0x34, 2)
    emu.mem.w32(0x4d8ae0, 1)
    vector(emu, pos, (10, 20, 30))
    observed = set()

    def generated(m, pointer):
        m.mem.write(pointer, bytes(0x48))
        m.mem.w32(pointer, definition)
        m.mem.w16(pointer + 4, 1)
        return 1

    for address in (0x104758, 0x104ca4, 0x106214, 0x106658, 0x108590):
        emu.stub(address, function=lambda m: generated(m, m.r[4]))
    emu.stub(0x1069b8, function=lambda m: generated(m, m.r[5]))
    emu.stub(0x14fdb8, ret=obj)

    def ctor(m):
        call = m._fresh_call
        observed.add(call.site)
        assert m.r[4] == obj
        assert floats(m, m.r[5]) == (10, 20, 66)
        assert m.r[6:11] == [0x520030, m.mem.u32(0x3e9d00),
                             m.mem.u32(0x3e9d04), 1, 0x441]
        assert m.f[12] == bits(1)
        assert m.mem.u32(m.r[11]) == definition
        # The separately executed base constructor establishes this one draw.
        m.mem.w32(SHARED, (m.mem.u32(SHARED) * 0x19660d + 0x3c6ef35f) & 0xffffffff)

    def cosine(m):
        m.f[0] = bits(0.5)

    def sine(m):
        m.f[0] = bits(0.75)

    def level(m):
        m.f[0] = bits(12)

    emu.stub(0x155a0c, function=ctor)
    emu.stub(0x166630, function=cosine)
    emu.stub(0x1666e0, function=sine)
    emu.stub(0x1ebf20, function=level)
    emu.stub(0x1ebf70, function=level)
    for index in range(1024):
        emu.reset_log()
        emu.mem.w32(SHARED, (seed + index) & 0xffffffff)
        emu.call(0x100d54, pos, 123, 0, 0, fargs=(36, 2, 0, 0, 5, 2))
        extra = calls(emu, 0x155110)
        assert len(extra) == 1
        assert extra[0].site == 0x101948
        assert extra[0].args[:2] == (obj, 0x441)
        assert floats(emu, obj + 0xfc, 2) == (24, 36)
    assert observed == {0x101230, 0x1013f4, 0x101560, 0x1018a8}, observed
    return 1024


def chest_constructor_cases(elf, seed):
    count = 0
    for kind in range(5):
        emu = machine(elf, seed, (0x14cb10, 0x1707b0))
        obj, pos = emu.alloc(0x88), emu.alloc(12)
        descriptor = emu.mem.u32(0x501698 + 4 * kind)
        model, texture, clip = 0x710000, 0x720000, 0x730000
        emu.mem.w32(descriptor + 4, emu.mem.u32(0x41bf78))
        emu.mem.w32(descriptor + 0xc, model)
        emu.mem.w32(descriptor + 0x14, texture)
        emu.mem.w32(descriptor + 0x1c, clip)
        emu.stub(0x3b8534, ret=1)
        emu.stub(0x1509d0, ret=10000)
        emu.stub(0x179550, ret=7)
        emu.stub(0x1ebf20, function=lambda m: m.f.__setitem__(0, bits(0)))
        emu.call(0x292030, obj, pos, 123, 0, kind)
        assert emu.mem.u32(obj + 0x24) == descriptor
        assert emu.mem.u32(obj + 0x48) == 0x5118d8
        assert emu.mem.u16(obj + 0x38) == 123
        assert emu.mem.u8(obj + 0x59) == kind
        assert floats(emu, obj + 0x1c, 2) == (22, 25)
        assert emu.mem.u32(obj + 0xc) == 0x100018
        assert calls(emu, 0x179550)[0].args[:2] == (model, 2)  # synthetic level helper gives 50 gold
        emu.reset_log()
        emu.call(0x292a2c, obj, 0)
        assert calls(emu, 0x170838)[0].args[:3] == (obj + 0x5c, clip, 0x204)
        loot = calls(emu, 0x100d54)
        assert len(loot) == 1
        assert loot[0].fargs[:6] == tuple(map(bits, (36, 2, 0, 0, 5, number(0x3f733333))))
        emu.reset_log()
        emu.mem.w8(obj + 0x60, 1)
        emu.call(0x29288c, obj)
        drawn = calls(emu, 0x1779b0)[0]
        assert drawn.args[:3] == (model, texture, 1)
        assert drawn.args[5] == obj + 0x5c
        count += 1
    return count


def chest_factory_cases(elf, seed):
    for address, kind in ((0x532f70, 0), (0x532f78, 0), (0x532f80, 0),
                           (0x532f88, 0), (0x533130, 4)):
        emu = machine(elf, seed, (0x159c20, 0x3b81a0))
        obj, pos = emu.alloc(0x88), emu.alloc(12)
        emu.stub(0x14fdb8, ret=obj)
        emu.call(0x159c94, address, pos, 123, 0)
        constructors = calls(emu, 0x292030)
        assert len(constructors) == 1
        assert constructors[0].args[4] == kind
        assert calls(emu, 0x14fdb8)[0].args[0] == 0x88
    return 5


def chest_placed_cases(elf, seed):
    for refuse in (False, True):
        emu = machine(elf, seed, (0x1083f8,))
        obj, prop, definition = emu.alloc(0x88), emu.alloc(0x248), emu.alloc(0x40)
        emu.mem.w32(obj + 0x24, emu.alloc(0x40))
        vector(emu, obj + 0x10, (10, 20, 30))
        emu.mem.w16(definition + 0x34, 2)

        def property_string(m):
            return 0x537430 if m.r[5] in (0x549828, 0x549348) and m.r[6] == 0 else 0

        def generated(m, output):
            m.mem.write(output, bytes(0x48))
            m.mem.w32(output, definition)
            return 1

        emu.stub(0x14f4c0, function=property_string)
        emu.stub(0x14c880, function=lambda m: int(m.r[5] == 0x549830))
        emu.stub(0x14c9c0, function=lambda m: m.f.__setitem__(0, bits(1)))
        emu.stub(0x1ebf70, function=lambda m: m.f.__setitem__(0, bits(12)))
        emu.stub(0x1069b8, function=lambda m: generated(m, m.r[5]))
        emu.stub(0x108590, function=lambda m: generated(m, m.r[4]))
        emu.stub(0x104ca4, function=lambda m: generated(m, m.r[4]))
        emu.stub(0x1509d0, ret=32768)
        emu.stub(0x14fdb8, ret=0 if refuse else prop)
        emu.stub(0x166630, function=lambda m: m.f.__setitem__(0, bits(0.5)))
        emu.stub(0x1666e0, function=lambda m: m.f.__setitem__(0, bits(0.75)))
        constructors = []

        def ctor(m):
            constructors.append(m._fresh_call.site)
            assert floats(m, m.r[5]) == (10, 20, 42)
            assert m.r[6:11] == [0x549528, m.mem.u32(0x3e9d00),
                                 m.mem.u32(0x3e9d04), 1, 0x441]
            assert m.f[12] == bits(1)

        emu.stub(0x155a0c, function=ctor)
        emu.call(0x292a2c, obj, 0)
        assert constructors == ([] if refuse else [0x292bfc, 0x292dac, 0x293028])
        assert len(calls(emu, 0x155110)) == (0 if refuse else 3)
        assert len(calls(emu, 0x100d54)) == 1
        if not refuse:
            assert floats(emu, prop + 0xfc, 2) == (12, 18)
    return 2


def container_gold_cases(elf, seed):
    count, spawned = 0, 0
    for refuse in (False, True):
        for index in range(32):
            emu = machine(elf, seed, (0x1509d0, 0x1ebf20))
            obj = emu.alloc(0x140)
            emu.mem.w32(obj + 0x13c, 1)
            emu.mem.w32(obj + 0x124, 1)
            emu.mem.w32(obj + 0x48, 0x513330)
            emu.mem.w32(obj + 0x44, seed + index)
            emu.mem.w32(obj + 0x1c, bits(24))
            emu.mem.w32(obj + 0x20, bits(72))
            emu.mem.w32(0x4f714c, bits(22))
            draws = {}

            def record_draw(m):
                draws[(m.r[31] - 8) & 0xffffffff] = m.r[2] >> 16

            emu.hooks[0x1509f0] = record_draw  # observation only; no jump or register change
            emu.stub(0x14fdb8, function=lambda m: m.alloc(0xc0)
                     if m.r[4] == 0xc0 and not refuse else 0)
            emu.call(0x23e430, obj)
            gold = calls(emu, 0x157668)
            eligible = draws[0x23f3ac] < 24000
            assert len(gold) == int(eligible and not refuse)
            if gold:
                amount = int((draws[0x23f3d4] & 3) * number(bits(22 * number(0x3ecccccc)))) + 1
                assert gold[0].args[2] == amount
                assert gold[0].site == 0x23f420
                assert floats(emu, gold[0].args[1]) == floats(emu, obj + 0x10)
                spawned += 1
            assert emu.mem.u32(SHARED) == seed  # this path uses the container's own RNG
            count += 1
    assert spawned > 0
    return count


def lifetime_cases(elf, seed):
    count = 0
    for timer, refuse, below in ((180, False, False), (0, False, False),
                                  (0, True, False), (-221, True, False),
                                  (180, True, True)):
        emu = machine(elf, seed)
        obj, block, player = emu.alloc(0x248), emu.alloc(0x190), emu.alloc(0x500)
        emu.mem.w8(obj + 0x238, 1)
        emu.mem.w32(obj + 0x190, bits(1))
        emu.mem.w32(obj + 0x240, bits(1))
        emu.mem.w16(obj + 0x10e, timer)
        if below:
            emu.mem.w32(0x4d8ae0, 1)
            emu.mem.w32(0x4f8440, 0)
            emu.mem.w32(PLAYERS + 0x43d8, player)
            emu.mem.w32(obj + 0x1a8, bits(-121))
        emu.stub(0x14fdb8, ret=0 if refuse else block)
        emu.stub(0x1834a8, function=lambda m: m.f.__setitem__(0, bits(-1000)))
        emu.call(0x155fcc, obj)
        settled = timer <= 0
        assert len(calls(emu, 0x14fdb8)) == int(settled)
        assert len(calls(emu, 0x1592bc)) == int(settled and not refuse)
        assert len(calls(emu, 0x14f200)) == int(settled or below)
        if settled:
            assert calls(emu, 0x14fdb8)[0].args[0] == 0x190
        assert emu.mem.u32(SHARED) == seed  # resting constructor is recorded here
        count += 1
    return count


def starting_record_cases(elf, seed):
    # The actual parser and bag insertion now execute as well. Equipment/stat
    # and skill services remain recordings; no runtime character is claimed.
    import difftest_items as items
    for cls in range(7):
        original = items.Original(elf, fast=True)
        emu = original.emu
        emu.record_calls = True
        for address in (0x1c27c0, 0x1bec10, 0x1d32e4, 0x1bf3a0):
            emu.stub(address)
        emu.mem.w32(SHARED, seed)
        emu.mem.w32(0x4d8ae0, 1)
        emu.mem.w32(PLAYERS + 0x50, cls)
        emu.mem.w32(0x41bfe0, 0)
        emu.mem.w8(0x4f8ee0, 0)
        emu.call(0x1acc78, 0)
        counts = tuple(emu.mem.u32(PLAYERS + 0x1330 + 0x1208 * bag) for bag in range(3))
        assert counts == (3 if cls == 3 else 2 if cls == 5 else 1, 3, 3), (cls, counts)
        if cls == 3:
            assert emu.mem.s16(PLAYERS + 0x130 + 2 * 0x48 + 4) == 40
        for bag in (1, 2):
            quantities = tuple(emu.mem.s16(PLAYERS + 0x130 + bag * 0x1208 + i * 0x48 + 4)
                               for i in range(counts[bag]))
            assert quantities == ((1, 1, 1) if bag == 1 else (2, 2, 2)), (cls, quantities)
        assert all(not call.stubbed for call in calls(emu, 0x1069b8) + calls(emu, 0x1c1868))
    return 7


def starting_cases(elf, seed):
    # Independently transcribed addresses from 0x1b14a0..0x1b1a58. Text stays private.
    common = (0x537310, 0x537340, 0x537370)
    cloth = (0x5373a0, 0x5373d0, 0x537400)
    weapons = ((0x537430,), (0x5374b8,), (0x5374e0,),
               (0x537458, 0x537488, 0x536ac8, 0x536ac8),
               (0x537510,), (0x537540, 0x537430), (0x537570,))
    consumables = (0x537598,) * 2 + (0x5375a8,) * 2 + (0x5375c0,) * 2
    for cls in range(7):
        emu = machine(elf, seed)
        emu.mem.w32(PLAYERS + 0x50, cls)
        emu.mem.w32(0x41bfe0, 0)
        emu.mem.w8(0x4f8ee0, 0)
        state, granted = {}, []

        def parse(m):
            state['descriptor'] = m.r[4]
            m.mem.write(m.r[5], bytes(0x48))
            m.mem.w16(m.r[5] + 4, 1)

        def give(m):
            granted.append((state['descriptor'], m.r[6]))
            return len(granted) - 1

        emu.stub(0x1069b8, function=parse)
        emu.stub(0x1c1868, function=give)
        emu.call(0x1acc78, 0)
        expected = (cloth if cls == 4 else common) + weapons[cls] + consumables
        assert tuple(address for address, _ in granted) == expected, cls
        assert tuple(flag for _, flag in granted[-6:]) == (0, 0, 1, 1, 1, 1)
        assert len(calls(emu, 0x1c27c0)) == (5 if cls in (3, 5) else 4)
        assert len(calls(emu, 0x1bec10)) == 1
        assert emu.mem.u32(SHARED) == seed  # parser is stubbed in this probe
    return 7


def physics_cases(elf, seed):
    count = 0
    for flags, item_flags in ((0x441, 0), (0x441, 1 << 17), (0x841, 0)):
        emu = machine(elf, seed, (0x1682f0, 0x3b60c0, 0x164330,
                                  0x166550, 0x167a58, 0x1668b8))
        obj = emu.alloc(0x248)
        emu.mem.w8(obj + 0x238, 1)
        emu.mem.w64(obj + 0x150, item_flags)
        emu.mem.w64(obj + 0xe8, 1)
        emu.mem.w32(obj + 0x240, bits(2))
        vector(emu, obj + 0x10, (10, 20, 30))
        vector(emu, obj + 0xfc, (60, -120))
        vector(emu, obj + 0x110, (1, 0, 0, 0, 1, 0, 0, 0, 1))
        emu.mem.w32(obj + 0x30, bits(240))

        def bounds(m):
            for pointer, value in zip(m.r[6:12], (-2, -3, -4, 5, 7, 9)):
                m.mem.w32(pointer, value)

        own = iter((0, 32768, 65535))
        emu.stub(0x179400, function=bounds)
        emu.stub(0x1509d0, function=lambda m: next(own))
        emu.call(0x155110, obj, flags)
        init = calls(emu, 0x1682f0)
        assert len(init) == 1 and init[0].args[0] == obj + 0x190
        assert init[0].fargs[:5] == tuple(map(bits, (1, 1, 14, 20, 26)))
        assert floats(emu, obj + 0x1a0) == (10, 20, 30)
        factor = number(0x3c888888)
        assert tuple(emu.mem.u32(obj + 0x1bc + i * 4) for i in range(3)) == tuple(
            bits(value * factor) for value in (60, -120, 240))
        spin = 10 if flags & (0x10 | 0x400) else 2
        assert floats(emu, obj + 0x1c8) == (-spin, 0, (65535 / 32768 - 1) * spin)
        assert emu.mem.u32(obj + 0x23c) == (0xbdcccccc if flags & 0x800 else 0xbecccccc)
        assert emu.mem.u32(obj + 0x22c) == 0
        assert len(calls(emu, 0x1509d0)) == 3
        assert emu.mem.u32(SHARED) == seed
        if item_flags:
            assert all(emu.mem.u32(obj + offset) == 0 for offset in (0x194, 0x198, 0x19c))
        else:
            assert all(emu.mem.u32(obj + offset) != 0 for offset in (0x194, 0x198, 0x19c))
        assert floats(emu, obj + 0x1ac, 4) == (0, 0, 0, 1)
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    with open(args.elf, 'rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != SHA256:
            parser.error('expected pinned US v2.00 executable')
    total = 0
    for title, test in (('Gold', gold_cases), ('movement and credit', contact_cases),
                        ('Gold original grid dispatch', contact_grid_cases),
                        ('manual interaction input', interaction_cases),
                        ('constructors and bounds', constructor_cases),
                        ('loot call arguments', loot_argument_cases),
                        ('Chest bindings', chest_constructor_cases),
                        ('Chest factory precedence', chest_factory_cases),
                        ('Chest placed loot', chest_placed_cases),
                        ('AutoContainer Gold', container_gold_cases),
                        ('flight lifetime', lifetime_cases),
                        ('starting grants', starting_cases),
                        ('starting records', starting_record_cases),
                        ('physics inputs', physics_cases)):
        count = test(args.elf, args.seed)
        total += count
        print('PASS %s: %d cases; seed %d' % (title, count, args.seed), flush=True)
    print('PASS %d bounded original-code cases' % total)


if __name__ == '__main__':
    main()
