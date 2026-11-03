#!/usr/bin/env python3
"""Execute original mission-2 exit, portal and pre-load boundaries in ee_emu.

Run from the repository root, preloading unittest before adding tools to sys.path:
  PYTHONDONTWRITEBYTECODE=1 python3 -c 'import unittest,runpy,sys; \
  sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_mission2_travel.py", \
  run_name="__main__")' local/SLUS_209.73 local --seed 20973

Private destinations/properties are read in memory. Output is counts and addresses.
No network, emulator patch, scheduler loop, resource load or completed travel.
Every substituted call is explicitly registered; unexpected auto-stubs fail.
"""
import argparse
import hashlib
from pathlib import Path
import random

from ee_emu import EE, float_to_raw, raw_to_float
from difftest_mission2 import SHA256, ScriptCheck, lump, props_for, put
from dump_tables import objects_from_file
import ref_mission2 as M
import ref_mission2_travel as R

PENDING, ORIENT, CURRENT, SUB, PREVIOUS = (
    0x41b6d0, 0x41b720, 0x41b721, 0x41b771, 0x41b7c2)
NETWORK, ACTIVE, ALIVE, PLAYERS = 0x402791, 0x4d8ae4, 0x4f8420, 0x4d8af0
STATE, COUNTER, DESTINATIONS, COUNT = 0x8e3a3a, 0x500ae8, 0x8e3a50, 0x8e3c30
EXPLICIT, CHOICE, TASK_COUNT, TASKS = 0x8e3c34, 0x8e3a38, 0x44fdb8, 0x840100
REAL = {
    0x13dd40, 0x14dcc8, 0x14f4c0, 0x150850, 0x18df90, 0x19e4a0, 0x19e5e8, 0x19e664, 0x19e760,
    0x1ec0f0, 0x1ec300, 0x1ed694, 0x1ed778, 0x1ed854,
    0x207478, 0x22fc2c,
    0x27d7a0, 0x27d754, 0x27da24, 0x27db00, 0x27db60,
    0x27dcf4, 0x27dd30, 0x27dd74, 0x27e6a8, 0x320edc,
}


class Follow:
    def __contains__(self, address):
        return (address in REAL or 0x13e6d0 <= address < 0x147aa8
                or 0x3a5000 <= address < 0x3cc000)


class Boundary(Exception):
    """Intentional stop before an unmodeled environment operation."""


class Rig:
    def __init__(self, executable, image=None):
        self.e = EE(executable)
        self.e.follow = Follow()
        self.allowed = set()
        self.stub_log = []
        self.sp = self.e.r[29]
        if image is not None:
            base = self.e.alloc(len(image) + 0x1000)
            self.e.mem.write(base, image)
            self.e.mem.w32(0x86b270, base)
            assert self.call(0x13e8f8, base, base + 0x60) == 0
            assert self.call(0x141310, base, 0x403370, -1) == 0

    @property
    def m(self):
        return self.e.mem

    def text(self, address, value):
        self.m.write(address, value.encode("latin1") + b"\0")

    def stub(self, address, value=0, callback=None):
        self.allowed.add(address)

        def record(e):
            self.stub_log.append((address, tuple(x & 0xffffffff for x in e.r[4:8])))
            return callback(e) if callback else value

        self.e.stub(address, function=record)

    def call(self, address, *args):
        start = len(self.e.calls)
        self.e.r[29] = self.sp
        try:
            return self.e.call(address, *args, max_steps=1000000) & 0xffffffff
        finally:
            unexpected = {c.target for c in self.e.calls[start:]
                          if c.stubbed and c.target not in self.allowed}
            assert not unexpected, "unexpected stubs " + ",".join(map(hex, sorted(unexpected)))

    def destinations(self):
        return [self.m.cstr(DESTINATIONS + i * 32) for i in range(self.m.u8(COUNT))]

    def set_destinations(self, values):
        self.m.w8(COUNT, len(values))
        for i, value in enumerate(values):
            assert len(value) < 32
            self.text(DESTINATIONS + i * 32, value)

    def run_entry(self, check, offset):
        return self.call(0x1ed694, put(self.e, check.entry_at(offset)))


def inputs(source):
    result = []
    for level in M.LEVELS:
        path = source / (level.upper() + ".GOB")
        data = path.read_bytes()
        image = lump(data, "script.scr")
        result.append((image, ScriptCheck(image), objects_from_file(str(path), data)))
    return result


def exits(executable, fixtures, rng):
    # Source index, entry, native-call cell, destination index; text stays private.
    routes = ((0, 0x128, 0x154, 1), (1, 0, 0x2c, 0),
              (1, 0x44, 0x70, 2), (2, 0, 0x2c, 1),
              (2, 0x44, 0x70, 3), (3, 0x44, 0x70, 2))
    cases = 0
    controls = ((0, 0, 0, 2, 0), (1, 0, 0, 2, 0), (1, 0, 1, 2, 0),
                (1, 0, 1, 1, 0), (1, -1, 1, 2, 0), (1, 0, 1, 2, 1),
                (1, 2, 599, 4, 0))
    for source, entry, site, destination in routes:
        image, check, rows = fixtures[source]
        offset = check.call_values(site, "newWorld", 1)[0]
        assert check.strings[offset] == M.LEVELS[destination]
        if entry == 0:
            assert offset == 0  # An AMX data offset, not a C null pointer.
        action = "=" + check.entry_at(entry)
        linked = [row for row in rows if M.FACTORY.get(row["class"].lower(), (0, 0))[1] == 0x1ec900
                  and any(p.endswith(action) for p in row["properties"].split(";"))]
        assert len(linked) == 1
        for network, active, cooldown, alive, post in controls:
            rig = Rig(executable, image)
            rig.stub(0x1eb000)
            rig.stub(0x13e150)  # Remote ownership suppresses only refusal presentation.
            obj = rig.e.alloc(0x50)
            rig.m.w32(obj + 0x2c, props_for(rig.e, linked[0]))
            rig.m.w32(0x4039f8, obj)
            rig.m.w8(NETWORK, network)
            rig.m.w32(ACTIVE, active & 0xffffffff)
            rig.m.w32(ALIVE, alive)
            rig.m.w8(0x4f8698, post)
            slot = max(active, 0)
            cd = PLAYERS + slot * 0x4c30 + 0x4bca
            rig.m.w16(cd, cooldown)
            before = "pending_" + str(rng.randrange(100000))
            rig.text(PENDING, before)
            rig.m.w8(ORIENT, 77)
            expected, next_cd = R.command(network, active, cooldown, alive, post)
            key = rig.m.cstr(0x5313c8)
            orientations = [int(p[len(key):]) & 255 for p in linked[0]["properties"].split(";")
                            if p.startswith(key)]
            orientation = orientations[-1] if orientations else 255
            rig.call(0x14dcc8, obj, 1)
            assert rig.m.cstr(PENDING) == (M.LEVELS[destination] if expected else before)
            assert rig.m.u8(ORIENT) == (orientation if expected else 77)
            assert rig.m.u16(cd) == next_cd
            assert sum(a == 0x1eb000 for a, _ in rig.stub_log) == int(expected)
            handlers = [c for c in rig.e.calls if c.target == 0x143dd0]
            addresses = [c for c in rig.e.calls if c.target == 0x1414a8]
            assert len(handlers) == len(addresses) == 1
            assert not handlers[0].stubbed and not addresses[0].stubbed
            assert addresses[0].args[1] & 0xffffffff == offset
            cases += 1
    return cases


def portal_prompt(executable, fixture):
    image, check, rows = fixture
    row, = [r for r in rows if M.FACTORY.get(r["class"].lower(), (0, 0))[1] == 0x27c694]
    variable = check.call_values(0x13c, "getv", 1, (0,))[0]
    cases = 0
    below = raw_to_float(float_to_raw(96.0) - 1)
    above = raw_to_float(float_to_raw(96.0) + 1)
    controls = ((0, 0, 0, 0, 1, 0), (1, 0, 0, 0, 1, 0),
                (1, 0, 1, 0, 1, 0), (1, 1, 0, 0, 1, 0),
                (1, 0, 0, 1, 1, 0), (1, 0, 0, 1, 2, 96),
                (1, 0, 0, 1, 2, 97), (1, 0, 0, 1, 2, 100),
                (1, 0, 0, 0, 1, 101), (1, 0, 0, 1, 2, below),
                (1, 0, 0, 1, 2, above))
    for predicate, hurt, busy, discovered, count, distance in controls:
        for display in (0, 1):
            rig = Rig(executable, image)
            for address in (0x173c84, 0x1d92a0, 0x19e854):
                rig.stub(address)
            rig.text(CURRENT, M.LEVELS[3])
            rig.text(SUB, "")
            destinations = list(M.LEVELS[:count])
            rig.set_destinations(destinations)
            obj = rig.e.alloc(0x180)
            rig.m.w32(obj + 0x2c, props_for(rig.e, row))
            rig.m.w8(obj + 0x4d, discovered)
            rig.m.w8(obj + 0x4f, hurt)
            rig.call(0x1ed854, put(rig.e, variable), predicate)
            if busy:
                rig.call(0x19e4a0, 0x27dd74, 20, 0x547e10, 0)
            rig.m.w32(ALIVE, 2)
            rig.m.w32(0x4f8440, 0)
            rig.m.w32(0x4f8444, 1)
            other = rig.e.alloc(0x80)
            rig.m.w32(PLAYERS + 0x4c30 + 0x43d8, other)
            rig.m.w32(other + 0x10, float_to_raw(float(distance)))
            thresholds = []
            rig.e.hook(0x27d920, lambda e: thresholds.append(raw_to_float(e.f[5])))
            before = "not_requested"
            rig.text(PENDING, before)
            rig.e.r[23] = display
            result = rig.call(0x27d7a0, obj, rig.e.alloc(0x200), 0)
            expected = R.prompt(predicate, hurt, busy, discovered, destinations,
                                M.LEVELS[3], [distance * distance])
            assert (result, rig.m.u8(obj + 0x4d), rig.destinations()) == expected, (
                predicate, hurt, busy, discovered, count, distance, display,
                result, rig.m.u8(obj + 0x4d), len(rig.destinations()),
                expected[0], expected[1], len(expected[2]))
            assert rig.m.cstr(PENDING) == before
            if predicate and not hurt and not busy and len(expected[2]) != 1:
                assert thresholds == [9216.0]
            else:
                assert thresholds == []
            ran_predicate = any(c.target == 0x1ed694 and not c.stubbed for c in rig.e.calls)
            assert ran_predicate == (not hurt and not busy)
            cases += 1
    return cases


def menu(executable):
    cases = 0
    # Execute the interaction and real scheduler registration, with dialog busy control.
    for network, dialog, expected in ((0, 0, 2), (0, 1, 0), (1, 1, 2)):
        rig = Rig(executable)
        for address in (0x1eb000, 0x17365c, 0x214230):
            rig.stub(address)
        rig.m.w32(0x4fe53c, dialog)
        rig.m.w8(NETWORK, network)
        rig.call(0x27d754, rig.e.alloc(0x180), 2)
        assert rig.m.u32(TASK_COUNT) == expected
        if expected:
            tasks = [(rig.m.u32(TASKS + i * 16), rig.m.u32(TASKS + i * 16 + 4),
                      rig.m.u32(TASKS + i * 16 + 12)) for i in range(expected)]
            assert tasks == [(0x27dd74, 20, 0), (0x27e2d0, 20, 1)]
            assert rig.m.u8(0x8e3a3b) == 2
            assert rig.m.u32(EXPLICIT) == 0
        cases += 1
    # State 5 copies either the selected list slot or an explicit runtime pointer.
    for explicit in (False, True):
        for counter in (0, 178, 179, 180, 181, 182):
            rig = Rig(executable)
            rig.m.w8(STATE, 5)
            rig.m.w32(COUNTER, counter)
            rig.m.w8(ORIENT, 77)
            rig.set_destinations(list(M.LEVELS[:3]))
            rig.m.w8(CHOICE, 1)
            destination = M.LEVELS[2 if explicit else 1]
            rig.m.w32(EXPLICIT, put(rig.e, destination) if explicit else 0)
            rig.text(PENDING, "pending_control")
            rig.call(0x27dd74)
            expected = R.travel_counter(counter, "pending_control", destination, 77)
            assert (rig.m.u8(STATE), rig.m.u32(COUNTER), rig.m.cstr(PENDING), rig.m.u8(ORIENT)) == expected
            cases += 1
    return cases


def portal_sequence(executable, fixture):
    """Actual predicate -> prompt -> action -> menu -> pending name, no loader."""
    image, check, rows = fixture
    row, = [r for r in rows if M.FACTORY.get(r["class"].lower(), (0, 0))[1] == 0x27c694]
    variable = check.call_values(0x13c, "getv", 1, (0,))[0]
    cases = 0
    # False gate; idle input; cancel; same-level confirm; valid confirm; cancel precedence.
    controls = ((0, 0, 1, 0, 0), (1, 0, 0, 0, 0), (1, 1, 0, 0, 0),
                (1, 0, 1, 1, 0), (1, 0, 1, 0, 0), (1, 1, 1, 0, 0),
                (1, 0, 1, 0, 1), (1, 0, 1, 0, 2))
    for predicate, cancel, confirm, current_selected, pause_guard in controls:
        rig = Rig(executable, image)
        for address in (0x173c84, 0x1d92a0, 0x19e854, 0x1eb000, 0x17365c, 0x214230,
                        0x13e4e8):
            rig.stub(address)
        rig.stub(0x13e150, int(pause_guard != 0))
        rig.stub(0x18cbfc, int(pause_guard == 1))
        rig.text(CURRENT, M.LEVELS[3])
        rig.text(SUB, "")
        rig.text(PENDING, "")
        rig.set_destinations([M.LEVELS[0], M.LEVELS[3]])
        rig.m.w32(0x4f8450, rig.e.alloc(0x80))  # Synthetic camera for original vector copy.
        rig.m.w32(ALIVE, 1)
        rig.m.w32(0x4f8440, 0)
        rig.m.w8(NETWORK, 0)
        rig.m.w32(0x4fe53c, 0)
        rig.m.w32(0x41bfb8, 1)  # Generated cancel/confirm masks; original code consumes them.
        rig.m.w32(0x41bfbc, 2)
        obj = rig.e.alloc(0x180)
        rig.m.w32(obj + 0x2c, props_for(rig.e, row))
        rig.call(0x1ed854, put(rig.e, variable), predicate)
        ready = rig.call(0x27d7a0, obj, rig.e.alloc(0x200), 0)
        assert ready == predicate
        if not ready:
            assert rig.m.u32(TASK_COUNT) == 0 and rig.m.cstr(PENDING) == ""
            cases += 1
            continue
        # Caller orchestration is explicit: the player/collision loop is not executed.
        rig.call(0x27d754, obj, 0)
        assert rig.m.u32(TASK_COUNT) == 2 and rig.m.u8(STATE) == 0
        rig.call(0x27dd74)
        assert rig.m.u8(STATE) == 1 and rig.m.u32(0x41b4f4) == 1
        assert rig.m.u32(0x8e3a40) == 1  # Current-level row found by original comparison.
        for _ in range(16):
            rig.call(0x27dd74)
        assert rig.m.u8(STATE) == 2
        rig.m.w8(CHOICE, int(current_selected))
        rig.m.w32(0x41bfe4, int(cancel) | (int(confirm) << 1))
        rig.call(0x27dd74)
        expected_state, expected_counter = R.menu_choice(
            cancel, confirm, current_selected, local_pause_requested=pause_guard == 1)
        assert (rig.m.u8(STATE), rig.m.u32(COUNTER)) == (expected_state, expected_counter)
        assert [(args[0], args[1]) for address, args in rig.stub_log
                if address == 0x13e4e8] == ([(0, 4)] if pause_guard == 1 else [])
        assert rig.m.cstr(PENDING) == ""
        if expected_state == 3:
            rig.m.w32(0x41bfe4, 0)
            for _ in range(8):
                rig.call(0x27dd74)
            assert rig.m.u32(0x41b4f4) == 0  # Offline pause cleared on both branches.
            if not expected_counter:
                assert rig.m.u32(TASK_COUNT) == 0
                assert rig.m.cstr(PENDING) == ""
            else:
                assert rig.m.u8(STATE) == 4
                rig.call(0x27dd74)
                assert rig.m.u8(STATE) == 5
                for _ in range(180):
                    rig.call(0x27dd74)
                    assert rig.m.cstr(PENDING) == ""
                assert rig.m.u32(COUNTER) == 181
                rig.call(0x27dd74)
                assert rig.m.cstr(PENDING) == M.LEVELS[0]
                assert rig.m.u8(ORIENT) == 255 and rig.m.u8(STATE) == 6
                rig.call(0x27dd74)
                assert rig.m.u8(STATE) == 7
                rig.call(0x27dd74)
                assert rig.m.u32(TASK_COUNT) == 0 and rig.m.u32(COUNTER) == 0
        cases += 1
    return cases


def transitions(executable):
    cases = 0
    for suffix, sub in (("", ""), ("_test_entrance", ""),
                        ("", "old_entrance"), ("_test_entrance", "old_entrance")):
        rig = Rig(executable)
        # Explicit state boundaries: stack diagnostic, saved-object serializer,
        # act lookup, pending character selection, audio fade. No load success stub.
        for address in (0x19d9f8, 0x21777c, 0x217f70, 0x2247ec, 0x216588):
            rig.stub(address)

        def stop(e):
            assert e.mem.cstr(e.r[4] & 0xffffffff) == M.LEVELS[1]
            raise Boundary()

        rig.e.hook(0x1e55c0, stop)
        request, current = M.LEVELS[1] + suffix, M.LEVELS[0]
        rig.text(PENDING, request)
        rig.text(CURRENT, current)
        rig.text(SUB, sub)
        rig.m.w8(ORIENT, 77)
        try:
            rig.call(0x320edc)
            raise AssertionError("load boundary was not reached")
        except Boundary:
            pass
        expected = R.request_names(request, current, sub, 77)
        assert (rig.m.cstr(PENDING), rig.m.cstr(CURRENT), rig.m.cstr(SUB),
                rig.m.cstr(PREVIOUS), rig.m.u8(ORIENT), rig.m.u8(0x41b7c1)) == expected
        assert rig.e.pc == 0x1e55c0
        cases += 1
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable")
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("--seed", type=int, default=20973)
    args = parser.parse_args()
    assert hashlib.sha256(Path(args.executable).read_bytes()).hexdigest() == SHA256
    fixtures = inputs(args.source_dir)
    for label, count in (
        ("original exit commands and cooldown controls", exits(args.executable, fixtures, random.Random(args.seed))),
        ("original portal predicate and prompt controls", portal_prompt(args.executable, fixtures[3])),
        ("original interaction scheduler and travel-counter controls", menu(args.executable)),
        ("original portal confirmation and cancellation sequences", portal_sequence(args.executable, fixtures[3])),
        ("original pre-load transitions stopped at 0x1e55c0", transitions(args.executable)),
    ):
        print("PASS", label, count, "cases")
    print("LIMIT: original loader 0x1e55c0 not executed; no completed travel or running-game claim")


if __name__ == "__main__":
    main()
