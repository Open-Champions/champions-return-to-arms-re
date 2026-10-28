#!/usr/bin/env python3
"""Counts-only comparisons of original gate lifecycle functions and authored rules.

Run from the repository root with python3 -m tools.difftest_exit_gate_lifecycle.
The original executable is opened read-only. No executable data is exported.
"""
import argparse
from collections import Counter
import hashlib
from pathlib import Path
import random
import struct
import sys
import unittest  # Preload stdlib dis before adding the tools directory.

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ee_emu import EE  # noqa: E402
import ref_exit_gate_lifecycle as R  # noqa: E402


SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
DESTS, COUNT = 0x8E3A50, 0x8E3C30
BASE, SUB, CARD = 0x41B721, 0x41B771, 0x4F8F28
STATE, CHOOSER, TRAVEL, FIXED = 0x8E3A3A, 0x8E3A3B, 0x500AE8, 0x8E3C34
TASKS, TASK_COUNT, TASK_CURSOR = 0x840100, 0x44FDB8, 0x44FDBC


def put_string(mem, address, value):
    mem.write(address, value.encode("ascii") + b"\0")


class Checks:
    def __init__(self):
        self.counts = Counter()
        self.executions = 0

    def equal(self, group, actual, expected):
        if actual != expected:
            raise AssertionError(f"{group} comparison={self.counts[group]} mismatch_count=1")
        self.counts[group] += 1

    def call(self, ee, address, *args):
        result = ee.call(address, *args, max_steps=100000)
        self.executions += 1
        return result


def fixture(rng, names):
    # Random inactive slots/tails catch accidental clearing and full-slot copies.
    storage = bytes(rng.randrange(1, 256) for _ in range(R.LIST_SIZE))
    state = R.Destinations(len(names), storage)
    for i, name in enumerate(names):
        state = state.replace_name(i, name)
    return state


def load_list(ee, state):
    ee.mem.write(DESTS, state.storage)
    ee.mem.w8(COUNT, state.count)


def read_list(ee):
    return R.Destinations(ee.mem.u8(COUNT), ee.mem.read(DESTS, R.LIST_SIZE))


def list_comparisons(elf, rng, checks):
    ee = EE(elf)
    mem = ee.mem
    hub_pointer = ee.alloc(32)
    # Use the original discriminator privately to build synthetic fixture names.
    # No shipped destination names are read, printed, or embedded in this source.
    discriminator = mem.cstr(0x547F28)
    hub = "SYN_" + discriminator + "_CURRENT"
    stale_a = "SYN_" + discriminator + "_OLD_A"
    stale_b = "SYN_" + discriminator + "_OLD_B"
    put_string(mem, hub_pointer, hub)
    hub_calls = []
    ee.stub(0x1EC300, function=lambda _e: hub_calls.append(1) or hub_pointer)
    guards = bytes(rng.randrange(256) for _ in range(16))
    mem.write(DESTS - 16, guards)
    mem.write(COUNT + 1, guards)

    def verify(group, expected):
        checks.equal(group, read_list(ee), expected)
        checks.equal("list_guards", (mem.read(DESTS - 16, 16), mem.read(COUNT + 1, 16)),
                     (guards, guards))

    for latch in (0, 1, 2, 255):
        for count in (0, 1, 7, 15):
            state = fixture(rng, [f"SYN_LEVEL_{i}" for i in range(count)])
            load_list(ee, state)
            mem.w8(CARD, latch)
            hub_calls.clear()
            checks.call(ee, 0x27DB00)
            verify("reset", state.reset(hub, latch))
            checks.equal("reset_hub_calls", len(hub_calls), int(latch == 0))

    cases = [
        ([], "SYN_A", ""), ([hub], "SYN_A", ""),
        ([hub, "SYN_A"], "SYN_A", ""),
        ([stale_a, "SYN_A"], "SYN_A", ""),  # Duplicate must skip cleanup.
        ([stale_a, "SYN_A"], "SYN_B", ""),
        (["SYN_A", stale_a, stale_b], "SYN_B", ""),
        ([hub, stale_a, stale_b], "SYN_B", ""),
        ([stale_a, stale_b], "SYN_B", ""),
        (["SYN_A", stale_a], "SYN_B", "SUB"),
        (["SYN_A_SUB"], "SYN_A", "SUB"),
        (["syn_a"], "SYN_A", ""),
        (["SYN_" + discriminator.upper() + "_OLD"], "SYN_B", ""),
        ([hub], stale_a, ""),  # Appended stale entry can remove itself.
        ([f"SYN_LEVEL_{i}" for i in range(14)], "SYN_NEW", ""),
        ([f"SYN_LEVEL_{i}" for i in range(15)], "SYN_LEVEL_14", ""),
    ]
    for _ in range(128):
        names = [f"SYN_LEVEL_{i}" for i in range(rng.randrange(0, 14))]
        for _ in range(rng.randrange(3)):
            if names:
                names[rng.randrange(len(names))] = rng.choice((hub, stale_a, stale_b))
        base = rng.choice(names) if names and rng.randrange(2) else f"SYN_NEW_{rng.randrange(20)}"
        sub = rng.choice(("", "", "SUB"))
        cases.append((names, base, sub))
    for names, base, sub in cases:
        state = fixture(rng, names)
        load_list(ee, state)
        put_string(mem, BASE, base)
        put_string(mem, SUB, sub)
        hub_calls.clear()
        expected = state.discover(base, sub, hub, discriminator)
        checks.call(ee, 0x27DB60)
        verify("discovery", expected)
        if R.qualified_name(base, sub) in names:
            checks.equal("duplicate_hub_calls", len(hub_calls), 0)

    packet = ee.alloc(R.LIST_SIZE + 36)
    for count in (0, 1, 7, 14, 15, 127, 128, 255):
        state = fixture(rng, [])
        state = R.Destinations(count, state.storage)
        load_list(ee, state)
        mem.write(packet, guards + bytes(R.LIST_SIZE + 4) + guards)
        result = checks.call(ee, 0x27DCF4, packet + 16)
        checks.equal("save", (result, mem.read(packet + 16, R.LIST_SIZE + 4)),
                     (R.LIST_SIZE + 4, state.save()))
        checks.equal("save_guards", (mem.read(packet, 16), mem.read(packet + R.LIST_SIZE + 20, 16)),
                     (guards, guards))
        load_list(ee, fixture(rng, ["SYN_OTHER"]))
        result = checks.call(ee, 0x27DD30, packet + 16)
        checks.equal("restore_size", result, R.LIST_SIZE + 4)
        verify("restore", state)
    # Restore truncates the count word and copies inactive slots verbatim.
    for word in (0x100, 0x101, 0x1234560F, 0xFFFFFFFF):
        data = word.to_bytes(4, "little") + fixture(rng, []).storage
        mem.write(packet + 16, data)
        checks.call(ee, 0x27DD30, packet + 16)
        verify("restore_count_width", R.Destinations.restore(data))

    # A connected history distinguishes logical names, stale tails and restore.
    for _ in range(24):
        state = fixture(rng, [stale_a, "SYN_RETAINED", stale_b])
        load_list(ee, state)
        for base in ("SYN_FIRST", "SYN_FIRST", "SYN_SECOND"):
            put_string(mem, BASE, base)
            put_string(mem, SUB, "")
            state = state.discover(base, "", hub, discriminator)
            checks.call(ee, 0x27DB60)
            verify("history_discovery", state)
        saved = state
        checks.call(ee, 0x27DCF4, packet + 16)
        checks.equal("history_save", mem.read(packet + 16, R.LIST_SIZE + 4), saved.save())
        mem.w8(CARD, 0)
        checks.call(ee, 0x27DB00)
        verify("history_reset", state.reset(hub, 0))
        checks.call(ee, 0x27DD30, packet + 16)
        verify("history_restore", saved)


def fields(mem):
    return mem.u8(STATE), mem.u8(CHOOSER), mem.u32(TRAVEL), mem.u32(FIXED)


def task_comparisons(elf, rng, checks):
    ee = EE(elf)
    mem = ee.mem
    registered, removed = [], []
    # Hooks observe arguments and execute the real scheduler underneath.
    ee.hook(0x19E4A0, lambda e: registered.append(tuple(x & 0xFFFFFFFF for x in e.r[4:8])))
    ee.hook(0x19E664, lambda e: removed.append(e.r[4] & 0xFFFFFFFF))
    for address in (0x1EB000, 0x17365C, 0x214230):
        ee.stub(address)
    mutex = [0]
    ee.stub(0x22FC2C, function=lambda _e: mutex[0])
    destinations = [0, ee.alloc(32), ee.alloc(32)]
    for pointer, name in zip(destinations[1:], ("SYN_FIXED_A", "SYN_FIXED_B")):
        put_string(mem, pointer, name)
    gate = ee.alloc(0x170)
    model = R.Tasks()

    def table_check():
        count = mem.u32(TASK_COUNT)
        checks.equal("task_count", count, len(model.records))
        records = [struct.unpack("<IiII", mem.read(TASKS + i * 16, 16)) for i in range(count)]
        checks.equal("task_records", records, model.records)
        checks.equal("task_cursor", mem.s32(TASK_CURSOR), model.cursor)

    def reset_tasks():
        model.records.clear()
        model.cursor = rng.choice((-1, 0, 1, 4))
        mem.w32(TASK_COUNT, 0)
        mem.w32(TASK_CURSOR, model.cursor)
        for i, priority in enumerate((-5, 20, 25)):
            fn = 0xF10000 + i * 16
            name = ee.alloc(24)
            put_string(mem, name, f"SYN_TASK_{i}")
            record = (fn, priority, name, rng.choice((0, 1, 2)))
            checks.call(ee, 0x19E4A0, *record)
            model.add(record)
        registered.clear()
        removed.clear()
        table_check()

    def open_and_check(pointer, slot):
        registered.clear()
        checks.call(ee, 0x27DA24, slot, pointer)
        checks.equal("open_fields", fields(mem), R.opened_fields(pointer, slot))
        checks.equal("registration_tuples", registered, list(R.GATE_TASKS))
        for record in R.GATE_TASKS:
            model.add(record)
        table_check()

    for slot in range(4):
        for pointer in destinations:
            reset_tasks()
            mem.w8(STATE, 7)
            mem.w8(CHOOSER, 9)
            mem.w32(TRAVEL, 123)
            mem.w32(FIXED, destinations[2] if pointer != destinations[2] else destinations[1])
            open_and_check(pointer, slot)
            # Duplicate registrations execute, but membership remains unique.
            open_and_check(destinations[1], (slot + 1) % 4)
            open_and_check(0, slot)
            for travel in (1, 181, 0xFFFFFFFF, 0, 0):
                mem.w32(TRAVEL, travel)
                before = fields(mem)
                removed.clear()
                checks.call(ee, 0x27DAC8)
                R.cleanup(model, travel)
                checks.equal("cleanup_calls", removed,
                             [r[0] for r in R.GATE_TASKS] if travel == 0 else [])
                checks.equal("cleanup_fields", fields(mem), before)
                table_check()

    for mutex_value in (0, 1):
        for network in (0, 1):
            for slot in range(4):
                reset_tasks()
                mutex[0] = mutex_value
                mem.w8(0x402791, network)
                mem.w8(STATE, 7)
                mem.w8(CHOOSER, 9)
                mem.w32(TRAVEL, 123)
                mem.w32(FIXED, destinations[2])
                before = fields(mem)
                checks.call(ee, 0x27D754, gate, slot)
                opened = R.interaction_opens(mutex_value, network)
                if opened:
                    for record in R.GATE_TASKS:
                        model.add(record)
                checks.equal("interact_fields", fields(mem), R.opened_fields(0, slot) if opened else before)
                checks.equal("interact_tuples", registered, list(R.GATE_TASKS) if opened else [])
                table_check()

    # Opener-to-request pointer handoff, with original copying and names.
    for pointer in destinations:
        for index in (0, 2, 14):
            reset_tasks()
            open_and_check(pointer, 0)
            put_string(mem, DESTS + index * 32, f"SYN_SELECTED_{index}")
            mem.w8(0x8E3A38, index)
            mem.w8(STATE, 5)
            mem.w32(TRAVEL, 181)
            mem.w8(0x41B720, 0)
            mem.write(0x41B6D0, bytes(80))
            source = pointer or DESTS + index * 32
            expected_name = mem.cstr(source)
            ee.reset_log()
            checks.call(ee, 0x27DD74)
            copies = [(c.args[0], c.args[1]) for c in ee.calls if c.target == 0x3B868C]
            checks.equal("request_pointer", copies, [(0x41B6D0, source)])
            checks.equal("request_contents", mem.cstr(0x41B6D0), expected_name)
            checks.equal("request_state", (mem.u8(STATE), mem.u32(TRAVEL), mem.u8(0x41B720)), (6, 181, 255))
            table_check()

    # Real dispatch executes states 6 and 7; the drawing body and unrelated
    # callbacks are external effects. Scheduler mutation remains original code.
    for _ in range(24):
        reset_tasks()
        open_and_check(rng.choice(destinations), rng.randrange(4))
        travel = rng.choice((0, 1, 181, 182))
        state = 6
        mem.w8(STATE, state)
        mem.w32(TRAVEL, travel)
        observed = []
        ee.hook(R.RUN_TASK[0], lambda _e: observed.append(R.RUN_TASK[0]))
        ee.stub(R.DRAW_TASK[0], function=lambda _e: observed.append(R.DRAW_TASK[0]) or 0)
        for fn, _priority, _name, _flags in model.records:
            if fn not in (R.RUN_TASK[0], R.DRAW_TASK[0]):
                ee.stub(fn, function=lambda _e, fn=fn: observed.append(fn) or 0)
        for exclude, include in ((0, 1), (1, -1), (1, -1), (0, 1), (1, -1)):
            expected_calls = []
            def invoke(fn):
                nonlocal state, travel
                expected_calls.append(fn)
                if fn == R.RUN_TASK[0]:
                    state, travel = R.terminal_tick(state, travel, model)
            model.dispatch(exclude, include, invoke)
            observed.clear()
            checks.call(ee, 0x19E798, exclude, include)
            checks.equal("dispatch_calls", observed, expected_calls)
            checks.equal("terminal_state", (mem.u8(STATE), mem.u32(TRAVEL)), (state, travel))
            table_check()
        ee.unhook(R.RUN_TASK[0])
        ee.unhook(R.DRAW_TASK[0])


def run(elf, seed):
    checks = Checks()
    rng = random.Random(seed)
    list_comparisons(elf, rng, checks)
    task_comparisons(elf, rng, checks)
    for group, count in sorted(checks.counts.items()):
        print(f"PASS gate_lifecycle seed={seed} group={group} comparisons={count}")
    print(f"PASS gate_lifecycle seed={seed} executions={checks.executions} comparisons={sum(checks.counts.values())}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", nargs="?", default="local/SLUS_209.73")
    parser.add_argument("--seed", type=int, default=20973)
    args = parser.parse_args()
    if hashlib.sha256(Path(args.elf).read_bytes()).hexdigest() != SHA256:
        print("FAIL gate_lifecycle executable_identity_mismatches=1")
        return 2
    try:
        run(args.elf, args.seed)
    except Exception as exc:
        # Avoid a traceback that could include original instruction values.
        print(f"FAIL gate_lifecycle seed={args.seed} error_type={type(exc).__name__} failures=1")
        if isinstance(exc, AssertionError):
            print(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
