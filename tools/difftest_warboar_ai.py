#!/usr/bin/env python3
"""Bounded WarBoar branch/ABI difftests, SLUS_209.73 US v2.00.

Run with an owned executable and --seed 20973 or --seed 7. The original
WarBoar constructor/run/setState and object RNG execute in ee_emu. Base tick,
activity, animation, target selection, geometric queries, movement and damage are
recording stubs, except in check_geometry where the original sight body runs
with a scripted angle and terrain-ray result. Constructor base/resource/event
services are recording stubs; its type-prefix test runs. This is not live
gameplay.
"""
import argparse
import hashlib
import random
import struct
from pathlib import Path

from dump_tables import lmp_entries, objects_from_file
from ee_emu import EE, float_to_raw
from ref_core import Lcg


EXPECTED_SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
RUN, SET_STATE, RAND = 0x2BA3A0, 0x2BAC60, 0x1509D0
SEE, CONE, HIT = 0x118D40, 0x10CF78, 0x119B58
PREFIX = [0x110D30, 0x112948, 0x10C0F0, 0x1162B0, 0x115EB8, 0x10DED0]


class Rig:
    def __init__(self, executable, seed, state=0, target=True, events=0):
        self.emu = EE(executable)
        self.emu.follow = {RUN, SET_STATE, RAND}
        self.obj = self.emu.alloc(0x3D8)
        self.definition = self.emu.alloc(0x100)
        self.target = self.emu.alloc(0x400)
        self.handle = self.emu.alloc(0x10)
        self.emu.mem.w32(self.handle + 0xC, self.target)
        self.emu.mem.w32(self.obj + 0x48, 0x517CF0)
        self.emu.mem.w32(self.obj + 0x24, self.definition)
        self.emu.mem.w32(self.obj + 0x44, seed)
        self.emu.mem.w32(self.obj + 0x234, self.handle if target else 0)
        self.emu.mem.w16(self.obj + 0x232, state)
        self.emu.mem.w32(0x404464, 0x12345678)
        for offset in range(0, 0x100, 4):
            self.emu.mem.w32(self.definition + offset, 0x700000 + offset)
        self.emu.stub(0x10C0F0, ret=1)
        self.emu.stub(0x1162B0, ret=events)

    def run(self):
        self.emu.follow = {RUN, RAND}
        self.emu.reset_log()
        self.emu.call(RUN, self.obj, max_steps=20000)
        assert [call.target for call in self.emu.calls[:6]] == PREFIX
        assert self.emu.calls[5].args[:2] == (self.obj, 0)
        assert self.emu.mem.u32(0x404464) == 0x12345678
        for call in self.emu.calls:
            if call.target in (SEE, CONE):
                assert call.args[0] == self.obj
                assert call.args[2] in (3000, 8000, 0x7FFF)
                assert call.fargs[:2] in tuple(
                    (float_to_raw(near), float_to_raw(far))
                    for near, far in ((0, 25), (25, 100), (0, 20), (0, 10)))
            if call.target == SEE:
                assert call.args[3] == 0
        return [call.args[1] for call in self.emu.calls if call.target == SET_STATE]

    def first_true(self, address, ordinal):
        count = [0]

        def answer(emu):
            count[0] += 1
            return int(count[0] == ordinal)

        self.emu.stub(address, function=answer)


def check_idle(executable, seed):
    count = 0
    for state in (0, 1):
        for visible in (0, 1):
            rig = Rig(executable, seed, state)
            rig.emu.stub(0x10E658, ret=visible)
            assert rig.run() == ([3 if state == 0 else 0] if visible else [])
            sight = next(call for call in rig.emu.calls if call.target == 0x10E658)
            assert sight.args[:2] == (rig.obj, 0)
            assert (0x119F38 in [call.target for call in rig.emu.calls]) == (state == 1 and not visible)
            count += 1
    for age, deadline, away, expected in ((180, 180, 0, []), (181, 180, 0, [1]),
                                          (0, 180, 1, [1])):
        rig = Rig(executable, seed)
        rig.emu.mem.w32(rig.obj + 0x300, age)
        rig.emu.mem.w32(rig.obj + 0xF4, deadline)
        rig.emu.stub(0x10EED8, ret=away)
        assert rig.run() == expected
        count += 1
    return count


def check_base_defaults(executable, seed):
    rig = Rig(executable, seed)
    rig.emu.follow = {0x109D68}
    position = rig.emu.alloc(12)
    rig.emu.call(0x109D68, rig.obj, 0, position, 0, rig.definition, 0,
                  fargs=(10,), max_steps=20000)
    assert rig.emu.mem.u32(rig.obj + 0xF4) == 0
    assert rig.emu.mem.u32(rig.obj + 0x300) == 0
    assert rig.emu.mem.u16(rig.obj + 0x3AC) == 300
    assert rig.emu.mem.u16(rig.obj + 0x3AE) == 500
    assert rig.emu.mem.u16(rig.obj + 0x3B0) == 0x4000
    assert rig.emu.mem.u32(rig.obj + 0x3C0) == float_to_raw(1000)
    return 1


def check_constructor_events(executable, seed):
    # Call-site contracts from ctor 0x2ba03c, also pinned by
    # research-campaign-combat 328b072 tools/ref_campaign_combat_r5.py.
    # Tuple: call site, definition entry, four masks, four raw f32 times.
    expected = (
        (0x2BA1F8, 4, (1, 2, 0, 0), (0x3E999999, 0x3F333333, 0, 0)),
        (0x2BA224, 5, (1, 2, 0, 0), (0x3E999999, 0x3F000000, 0, 0)),
        (0x2BA250, 6, (1, 2, 0, 0), (0x3E999999, 0x3F333333, 0, 0)),
        (0x2BA27C, 7, (1, 2, 0, 0), (0x3E999999, 0x3F000000, 0, 0)),
        (0x2BA2B0, 10, (1, 2, 0, 0), (0x3F000000, 0x3F666666, 0, 0)),
        (0x2BA2DC, 11, (0x84, 0, 0, 0), (0x3F800000, 0, 0, 0)),
        (0x2BA308, 12, (0x84, 0, 0, 0), (0x3F800000, 0, 0, 0)),
    )
    for small, name in enumerate(("WarBoar", "WarBoarSmall")):
        rig = Rig(executable, seed)
        rig.emu.follow = {0x2BA03C, 0x159C20}
        position = rig.emu.alloc(12)
        type_data = name.encode("ascii") + b"\0"
        type_name = rig.emu.alloc(len(type_data))
        rig.emu.mem.write(type_name, type_data)
        rig.emu.call(0x2BA03C, rig.obj, position, 0, 0, type_name,
                     max_steps=20000)
        assert rig.emu.mem.u8(rig.obj + 0x3D0) == small
        events = [call for call in rig.emu.calls if call.target == 0x118378]
        assert all(call.args[0] == rig.obj for call in events)
        actual = tuple((call.site, call.args[1], call.args[2:6], call.fargs[:4])
                       for call in events)
        assert actual == expected, (name, actual)
    return 2


def check_choices(executable, seed):
    count = 0
    rng = random.Random(seed)
    for state in (3, 5):
        for ordinal in range(1, 9 if state == 3 else 7):
            for last in (6, 8):
                for _trial in range(12):
                    own_seed = rng.getrandbits(32)
                    rig = Rig(executable, own_seed, state)
                    rig.emu.mem.w32(rig.obj + 0x3CC, last)
                    target_tests = 5 if state == 3 else 3
                    if ordinal <= target_tests:
                        rig.first_true(SEE, ordinal)
                    else:
                        rig.first_true(CONE, ordinal - target_tests)
                    model = Lcg(own_seed)
                    if state == 3:
                        if ordinal in (1, 5 + 1):
                            expected = [8, 9, 6, 6, 6][model.draw() % 5]
                        elif ordinal == 2:
                            expected = 10
                        elif ordinal in (3, 7):
                            expected = 8
                        elif ordinal in (4, 8):
                            expected = 9
                        else:
                            expected = None
                    else:
                        expected = (6, 8, 9, 6, 8, 9)[ordinal - 1]
                        if ordinal == 1 and last == 6 and model.draw() % 3 == 0:
                            expected = (10, 8, 9)[model.draw() % 3]
                    got = rig.run()
                    if expected is None:
                        assert got == []
                        assert 0x1187E0 in [call.target for call in rig.emu.calls]
                    else:
                        assert got == [expected], (state, ordinal, last, got, expected)
                    assert rig.emu.mem.u32(rig.obj + 0x44) == model.state
                    count += 1
    for state, rooted, target, expected in ((3, 0, False, [0]),
                                             (5, 0, False, [3]), (5, 1, False, []),
                                             (3, 0, True, []), (5, 0, True, [3])):
        rig = Rig(executable, seed, state, target)
        rig.emu.stub(0x1195E0, ret=int(not rooted))
        assert rig.run() == expected
        if state == 3 and target:
            assert 0x1143E8 in [call.target for call in rig.emu.calls]
        count += 1
    return count


def check_attack(executable, seed):
    count = 0
    for state in range(6, 11):
        for small in (0, 1):
            for events in (0, 1, 2, 3):
                rig = Rig(executable, seed, state, events=events)
                rig.emu.mem.w8(rig.obj + 0x3D0, small)
                for offset, value in ((0xD0, 11), (0xD2, 22), (0xD4, 333)):
                    rig.emu.mem.w16(rig.obj + offset, value)
                model = Lcg(seed)
                flags = 8
                if events & 1 and (state == 7 or state == 10 and not small):
                    flags = 0x80008 if model.draw() % 3 == 0 else 0x40008
                assert rig.run() == [3]
                hits = [call for call in rig.emu.calls if call.target == HIT]
                assert len(hits) == int(bool(events & 1))
                if hits:
                    assert hits[0].args[:8] == (rig.obj, 0, 3000, 11, 22, 333, flags, 0)
                    assert hits[0].fargs[:2] == (float_to_raw(0), float_to_raw(25))
                assert rig.emu.mem.u32(rig.obj + 0x3C8) == int(bool(events & 1))
                assert rig.emu.mem.u32(rig.obj + 0x44) == model.state
                count += 1
    for events, playing, visible, expected in ((2, 1, 1, [5]), (0, 1, 1, []),
                                                (0, 0, 1, [3]), (2, 1, 0, [])):
        rig = Rig(executable, seed, 6, events=events)
        rig.emu.mem.w16(rig.obj + 0x11A, 8 if playing else 0)
        rig.emu.stub(SEE, ret=visible)
        assert rig.run() == expected
        count += 1
    return count


def check_set_state(executable, seed):
    count = 0
    for old in (0, 3, 5, 6, 7, 10, 15, 16, 18, 19):
        for requested in (0, 1, 3, 5, 6, 7, 8, 9, 10, 18, 19):
            rig = Rig(executable, seed, old)
            rig.emu.mem.w32(rig.obj + 0x300, 900)
            rig.emu.mem.w32(rig.obj + 0x3C8, 99)
            rig.emu.call(SET_STATE, rig.obj, requested, max_steps=20000)
            expected = old if requested == 18 and 6 <= old < 16 else requested
            assert rig.emu.mem.u16(rig.obj + 0x232) == expected
            calls = [call.target for call in rig.emu.calls]
            if requested == 0:
                assert rig.emu.mem.u32(rig.obj + 0xF4) == 1080
            if requested == 1:
                assert calls[:3] == [0x10A9C0, 0x11A1E0, 0x119618]
            if 6 <= requested <= 10:
                assert rig.emu.mem.u32(rig.obj + 0x3C8) == 0
                assert rig.emu.mem.u32(rig.obj + 0x3CC) == requested
            count += 1
    return count


def check_recovery(executable, seed):
    count = 0
    for state, address in ((16, 0x1195F0), (19, 0x119608)):
        for ready in (0, 1):
            rig = Rig(executable, seed, state)
            rig.emu.stub(address, ret=ready)
            assert rig.run() == ([0 if state == 16 else 3] if ready else [])
            if state == 16 and not ready:
                flee = next(call for call in rig.emu.calls if call.target == 0x119F08)
                assert flee.args[:2] == (rig.obj, 0)
            count += 1
    for playing in (0, 1):
        rig = Rig(executable, seed, 18)
        rig.emu.mem.w16(rig.obj + 0x11A, 0x10 if playing else 0)
        assert rig.run() == ([] if playing else [3])
        count += 1
    return count


def check_geometry(executable, seed):
    count = 0
    for distance, bearing, near, far, ray, mode, expected in (
        (54, 0, 0, 25, -1, 0, 1), (55, 0, 0, 25, -1, 0, 0),
        (55, 0, 25, 100, -1, 0, 1), (130, 0, 25, 100, -1, 0, 0),
        (54, 2999, 0, 25, -1, 0, 1), (54, 3000, 0, 25, -1, 0, 0),
        (54, 0, 0, 25, 0.5, 0, 0), (54, 0, 0, 25, 0.5, 1, 0),
        (54, 0, 0, 25, 1, 0, 0), (54, 0, 0, 25, 1.1, 1, 1),
    ):
        rig = Rig(executable, seed)
        rig.emu.follow = {0x10C810}
        rig.emu.mem.wf32(rig.obj + 0x1C, 30)
        rig.emu.mem.wf32(rig.target + 0x1C, 0)
        rig.emu.mem.wf32(rig.target + 0x10, distance)
        rig.emu.stub(0x166798, ret=bearing)

        def terrain(emu):
            emu.f[0] = float_to_raw(ray)
            return 0

        rig.emu.stub(0x18A5C0, function=terrain)
        got = rig.emu.call(0x10C810, rig.obj, rig.target, 0, 3000, mode,
                           fargs=(near, far, 0), max_steps=20000)
        assert got == expected, (distance, bearing, near, far, ray, mode, got)
        rays = [call for call in rig.emu.calls if call.target == 0x18A5C0]
        for call in rays:
            assert call.args[3] == (0 if mode else 3)
        count += 1
    return count


def check_sight_wrapper(executable, seed):
    count = 0
    for force in (0, 1):
        for arc in (0x4000, 0x7FFF):
            for pointblank in (0, 1):
                rig = Rig(executable, seed)
                rig.emu.follow = {0x10E658}
                rig.emu.mem.w16(rig.obj + 0x3AC, 300)
                rig.emu.mem.w16(rig.obj + 0x3AE, 500)
                rig.emu.mem.w16(rig.obj + 0x3B0, arc)
                rig.first_true(0x10C810, 1 if pointblank else 2)
                assert rig.emu.call(0x10E658, rig.obj, force) == 1
                queries = [call for call in rig.emu.calls if call.target == 0x10C810]
                assert len(queries) == (1 if pointblank else 2)
                assert queries[0].args[:5] == (rig.obj, rig.target, 0, 0x7FFF,
                                               int(force != 0 or arc == 0x7FFF))
                assert queries[0].fargs[:3] == (0, float_to_raw(300), 0)
                if not pointblank:
                    assert queries[1].args[3] == arc
                    assert queries[1].fargs[:3] == (0, float_to_raw(500), 0)
                count += 1
    return count


def check_multi_hit(executable, seed):
    rig = Rig(executable, seed)
    rig.emu.follow = {HIT}
    victims = [rig.emu.alloc(0x400) for _index in range(3)]

    def collect(emu):
        for index, victim in enumerate(victims + [0]):
            emu.mem.w32(emu.r[6] + index * 4, victim)
        assert emu.r[7] == 0x80
        return len(victims)

    rig.emu.stub(0x14A928, function=collect)
    rig.emu.stub(0x119328, ret=1)
    rig.emu.stub(0x10C810, ret=1)
    rig.emu.stub(0x1E8230, ret=1)
    assert rig.emu.call(HIT, rig.obj, 0, 3000, 11, 22, 333, 8, 0,
                        fargs=(0, 25), max_steps=20000) == 1
    hits = [call for call in rig.emu.calls if call.target == 0x1E8230]
    assert [call.args[0] for call in hits] == victims
    for call in hits:
        assert call.args[1:8] == (rig.obj, 333, 0, 0, 8, 0, 0)
        assert call.fargs[:2] == (float_to_raw(11), float_to_raw(22))
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--seed", type=int, default=20973)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--valor", type=Path)
    args = parser.parse_args()
    digest = hashlib.sha256(args.executable.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit("wrong executable SHA-256: " + digest)
    for check in (check_base_defaults, check_constructor_events, check_idle, check_choices,
                  check_attack, check_set_state, check_recovery,
                  check_geometry, check_sight_wrapper, check_multi_hit):
        print("PASS %s seed=%d cases=%d" %
              (check.__name__, args.seed, check(args.executable, args.seed)))
    if args.archive:
        data = args.archive.read_bytes()
        print("OBSERVED archive sha256=" + hashlib.sha256(data).hexdigest())
        for name, offset, size in lmp_entries(data):
            if name.lower().endswith(".anm"):
                assert size >= 0x70
                assert data[offset + 0x14:offset + 0x34] == bytes(0x20)
                print("OBSERVED clip=%s length_ticks=%d" %
                      (name, struct.unpack_from("<I", data, offset + 4)[0]))
    if args.valor:
        data = args.valor.read_bytes()
        print("OBSERVED valor sha256=" + hashlib.sha256(data).hexdigest())
        rows = objects_from_file(str(args.valor), data)
        boars = [row for row in rows if row["class"] in ("WarBoar", "WarBoarSmall")]
        print("OBSERVED boar_placements=%d" % len(boars))
        for key in ("HomeRange", "pointblankrange", "visualrange", "visualarc", "PathName"):
            values = sorted({part for row in boars for part in row["properties"].split(";")
                             if part.split("=", 1)[0].lower() == key.lower()})
            print("OBSERVED property=%s placement_values=%r" % (key, values))


if __name__ == "__main__":
    main()
