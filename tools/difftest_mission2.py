#!/usr/bin/env python3
"""Compare mission-2 records, route cells and new constructors with v2.00.

PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_mission2.py \
  local/SLUS_209.73 local --seed 20973

The owner-supplied GOB/LMP files stay ignored under local/. The original
loader, factory and bounded constructor chain run in ee_emu. Allocation,
resource returns and lower model/combat services are stubs. This is not a
level load or a native combat test.
"""
import argparse
from collections import Counter
import hashlib
import os
import random
import struct

from dump_tables import Elf, find_in_lump, gob_entries, lmp_entries, objects_from_file
from ee_emu import EE
import ref_mission2 as R
import scr

SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
FACTORY, POOL_NEW, SET_FACTORY, LOAD = 0x159c94, 0x14fdb8, 0x14f6a8, 0x14e808
CREATURE, OBJECT, RES_FIND = 0x109d68, 0x14cb10, 0x17365c


class FactoryFollow:
    def __contains__(self, addr):
        return (addr in (FACTORY, 0x159c20, 0x14f730, 0x14f850)
                or 0x3a5000 <= addr < 0x3c0000)


class ConstructorFollow(FactoryFollow):
    def __init__(self, ctor):
        self.ctor = ctor

    def __contains__(self, addr):
        return (addr in (self.ctor, CREATURE, OBJECT, 0x14c880, 0x14f4c0)
                or super().__contains__(addr))


def cstr(mem, addr):
    return mem.cstr(addr & 0xffffffff, 128)


def put(emu, value):
    raw = value.encode("latin1") + b"\0"
    ptr = emu.alloc(len(raw))
    emu.mem.write(ptr, raw)
    return ptr


def lump(gob, wanted):
    found = [data for _name, off, size in gob_entries(gob)
             if (data := find_in_lump(gob[off:off + size], wanted)) is not None]
    assert len(found) == 1, wanted
    return found[0]


def props_for(emu, row):
    strings = [put(emu, x) for x in row["properties"].split(";") if x]
    props = emu.alloc((len(strings) + 1) * 4)
    for i, ptr in enumerate(strings):
        emu.mem.w32(props + i * 4, ptr)
    return props


def loader(executable, blob, rows):
    emu = EE(executable)
    emu.follow = {LOAD, SET_FACTORY, 0x3b8dc4, 0x3b8f30}
    source = emu.alloc(len(blob) + 16)
    emu.mem.write(source, blob)
    seen = []

    def record(e):
        ptr = e.r[7] & 0xffffffff
        props = []
        if ptr:
            for i in range(256):
                value = e.mem.u32(ptr + i * 4)
                if not value:
                    break
                props.append(cstr(e.mem, value))
            else:
                raise AssertionError("unterminated properties")
        seen.append((cstr(e.mem, e.r[4]), e.r[6] & 0xffff, tuple(props)))
        return 0

    callback = emu.alloc(8)
    emu.stub(callback, function=record)
    emu.call(SET_FACTORY, callback)
    consumed = emu.call(LOAD, source, 0, max_steps=10000000)
    assert len(seen) == len(rows)
    for actual, row in zip(seen, rows):
        assert actual == (row["class"], row["angle"],
                          tuple(x for x in row["properties"].split(";") if x))
    end = 8
    for _row in rows:
        end += struct.unpack_from("<h", blob, end + 4)[0]
    assert consumed == end
    return consumed


def factory(executable, rows, seed):
    emu = EE(executable)
    emu.follow = FactoryFollow()
    block, world = emu.alloc(0x1000), emu.alloc(0x100)
    emu.mem.w32(0x44fdc8, world)
    emu.stub(POOL_NEW, ret=block)
    ordered = list(rows)
    random.Random(seed).shuffle(ordered)
    selected = 0
    for row in ordered:
        key = row["class"].lower()
        assert key in R.FACTORY or key in R.NO_OBJECT, (row["index"], key)
        name, props, pos = put(emu, row["class"]), props_for(emu, row), emu.alloc(12)
        emu.reset_log()
        result = emu.call(FACTORY, name, pos, row["angle"], props,
                          max_steps=500000)
        alloc = [c for c in emu.calls if c.target == POOL_NEW]
        ctors = [c for c in emu.calls if c.target not in
                 (POOL_NEW, 0x159c20, 0x14f730, 0x14f850)
                 and not 0x3a5000 <= c.target < 0x3c0000]
        expected = R.FACTORY.get(key)
        if expected is None:
            assert not alloc and result == 0, row["index"]
        else:
            assert len(alloc) == 1 and alloc[0].args[0] == expected[0]
            assert ctors and ctors[-1].target == expected[1], row["index"]
            assert result == block, row["index"]
            selected += 1
    assert selected == sum(count for name, count in Counter(r["class"] for r in rows).items()
                           if name.lower() in R.FACTORY)
    return selected


def constructor(executable, row, definition, expected_requests, seed):
    ctor = R.FACTORY[row["class"].lower()][1]
    emu = EE(executable)
    emu.follow = ConstructorFollow(ctor)
    emu.mem.w32(0x41bf78, 1)
    emu.mem.w32(0x404464, seed)
    block, world = emu.alloc(0x1000), emu.alloc(0x100)
    emu.mem.w32(0x44fdc8, world)
    emu.stub(POOL_NEW, ret=block)
    requests = []
    emu.stub(RES_FIND, function=lambda e: requests.append(
        (cstr(e.mem, e.r[4]), cstr(e.mem, e.r[5]))) or 0)
    name, props, pos = put(emu, row["class"]), props_for(emu, row), emu.alloc(12)
    assert emu.call(FACTORY, name, pos, row["angle"], props,
                    max_steps=1000000) == block
    base = [c for c in emu.calls if c.target == CREATURE]
    obj = [c for c in emu.calls if c.target == OBJECT]
    assert len(base) == len(obj) == 1
    assert base[0].args[4] == obj[0].args[2] == definition
    assert base[0].args[0] == obj[0].args[0] == block
    assert requests == expected_requests
    return len(requests)


def resource_tables(executable, source_dir):
    elf = Elf(open(executable, "rb").read())
    expected = {}
    for definition, (archive, count) in R.RESOURCE_DEFS.items():
        assert elf.cstr(elf.u32(definition)) == archive
        names = tuple(elf.cstr(elf.u32(definition + 8 + 8 * i))
                      for i in range(count))
        assert len(set(names)) == count and all(names)
        assert elf.u32(definition + 8 + 8 * count) == 0
        blob = open(os.path.join(source_dir, archive.upper()), "rb").read()
        present = {name.lower() for name, _off, _size in lmp_entries(blob)}
        assert all(name.lower() in present for name in names)
        expected[definition] = [(archive, name) for name in names]
    assert sum(map(len, expected.values())) == 70
    return expected


def direct_requests(executable, rows_by_level, seed):
    representatives = {row["class"]: row for level in R.LEVELS
                       for row in rows_by_level[level]
                       if row["class"] in R.DIRECT_REQUESTS}
    assert set(representatives) == set(R.DIRECT_REQUESTS)
    for name, row in representatives.items():
        ctor = R.FACTORY[name.lower()][1]
        emu = EE(executable)
        emu.follow = ConstructorFollow(ctor)
        emu.mem.w32(0x404464, seed)
        emu.mem.w32(0x41bf78, 1)
        block, world = emu.alloc(0x1000), emu.alloc(0x100)
        emu.mem.w32(0x44fdc8, world)
        emu.stub(POOL_NEW, ret=block)
        requests = []
        emu.stub(RES_FIND, function=lambda e: requests.append(
            (cstr(e.mem, e.r[4]), cstr(e.mem, e.r[5]))) or 0)
        type_name = put(emu, name)
        props, pos = props_for(emu, row), emu.alloc(12)
        assert emu.call(FACTORY, type_name, pos, row["angle"], props,
                        max_steps=1000000) == block
        assert len(requests) == R.DIRECT_REQUESTS[name], name
    return len(representatives)


class ScriptCheck:
    def __init__(self, image):
        self.image = image
        parsed = scr.parse(image)
        self.start, self.end = parsed["code"]
        self.entries = {name: offset for offset, name in parsed["internals"]}
        self.natives = [name for _off, name in parsed["externals"]]
        self.strings = dict(scr.strings(image, *parsed["strings"]))

    def word(self, offset):
        assert offset % 4 == 0 and 0 <= offset < self.end - self.start
        return struct.unpack_from("<I", self.image, self.start + offset)[0]

    def words(self, offset, *expected):
        assert tuple(self.word(offset + 4 * i) for i in range(len(expected))) == expected

    def entry_at(self, offset):
        found = [name for name, at in self.entries.items() if at == offset]
        assert len(found) == 1, hex(offset)
        return found[0]

    def call_values(self, offset, native, count, strings=()):
        self.words(offset, 0x7b, self.natives.index(native))
        values = []
        for i in range(count + 1):
            at = offset - 8 * (count + 1 - i)
            assert self.word(at) == 0x27
            value = self.word(at + 4)
            values.append(value)
        assert values[-1] == count * 4
        args = list(reversed(values[:-1]))
        for i in strings:
            assert args[i] in self.strings
            args[i] = self.strings[args[i]]
        return tuple(args)

    def call(self, offset, native, *args):
        string_args = tuple(i for i, arg in enumerate(args) if isinstance(arg, str))
        assert self.call_values(offset, native, len(args), string_args) == args, (hex(offset), native)


def script_contract(gobs, rows_by_level):
    scripts = {level: ScriptCheck(lump(gobs[level], "script.scr"))
               for level in R.LEVELS}
    assert tuple(len(scripts[level].entries) for level in R.LEVELS) == (28, 3, 3, 14)
    calls = (
        ("innovat1", 0x128, 0x154, "inmine1"),
        ("inmine1", 0x000, 0x02c, 0),
        ("inmine1", 0x044, 0x070, "inmine2"),
        ("inmine2", 0x000, 0x02c, 0),
        ("inmine2", 0x044, 0x070, "innovat2"),
        ("innovat2", 0x044, 0x070, "inmine2"),
    )
    for level, start, site, dest in calls:
        script = scripts[level]
        script.entry_at(start)
        script.words(start, 0x2e)
        script.call(site, "newWorld", dest)
    first = scripts["innovat1"]
    assert first.entries["start"] == 0xb00
    first.call(0xb34, "setMissionAvailable", 2, 1)
    started = first.call_values(0xb68, "setv", 2, (0,))
    current = first.call_values(0xb9c, "setv", 2, (0,))
    assert started[1] == 1 and current[1] == 2 and started[0] != current[0]
    first.call(0xbc8, "postAction", first.entry_at(0xbe0))
    first.call(0xc4c, "cutScene", "innovat1")
    branches = (first.call_values(0x314, "addQuest", 2, (0, 1)),
                first.call_values(0x944, "addQuest", 2, (0, 1)))
    assert branches[0][0] == branches[1][0] and branches[0][1] != branches[1][1]
    assert first.call_values(0x4ac, "removeQuest", 1, (0,)) == (branches[0][0],)
    assert first.call_values(0x480, "removePlayerItem", 2, (1,))[1] == "coppersprocket"
    first.call(0x4d8, "addDeferedCall", first.entry_at(0xc98))
    given = first.call_values(0xcd4, "givePlayerItem", 3, (0,))
    assert given[0] != "coppersprocket" and given[1:] == (0, 0)
    first.call(0xd00, "grantMission", 2)
    last = scripts["innovat2"]
    last.entry_at(0x46c)
    gate = last.call_values(0x13c, "getv", 1, (0,))
    assert last.call_values(0x4a0, "setv", 2, (0,)) == (gate[0], 1)
    last.call(0x4cc, "setSaveInhibit", 0)
    last.call(0x280, "cutScene", "iron")
    last.call(0x358, "setSaveInhibit", 1)
    last.call(0x70, "newWorld", "inmine2")

    def properties(level, cls):
        return [set(x for x in row["properties"].split(";") if x)
                for row in rows_by_level[level] if row["class"] == cls]

    for level, offsets in (("innovat1", (0x128,)), ("inmine1", (0x0, 0x44)),
                           ("inmine2", (0x0, 0x44)), ("innovat2", (0x44,))):
        expected = {"action=" + scripts[level].entry_at(off) for off in offsets}
        assert expected == {x for p in properties(level, "PushTrigger")
                            for x in p if x.startswith("action=")}
    assert {"dialogscript=" + first.entry_at(off) for off in (0x0, 0x94)} == {
        x for p in properties("innovat1", "NPC") for x in p if x.startswith("dialogscript=")}
    assert any("deathscript=" + last.entry_at(0x0) in p
               for p in properties("innovat2", "IronGuardian"))
    assert any("dropitem=coppersprocket" in p for p in properties("innovat2", "IronGuardian"))
    assert {"t=" + last.entry_at(off) for off in (0x150, 0x194)} == {
        x for p in properties("innovat2", "Trigger") for x in p if x.startswith("t=")}
    last.call(0x17c, "callScript", last.entry_at(0x21c))
    last.call(0x1c0, "callScript", last.entry_at(0x3f0))
    assert any("script=" + last.entry_at(0x110) in p
               for p in properties("innovat2", "Portal"))
    assert last.call_values(0x13c, "getv", 1, (0,)) == gate
    return len(calls)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("executable")
    ap.add_argument("source_dir", help="ignored directory holding the four GOBs and three LMPs")
    ap.add_argument("--seed", type=int, default=20973)
    args = ap.parse_args()
    assert hashlib.sha256(open(args.executable, "rb").read()).hexdigest() == SHA256
    gobs, rows_by_level = {}, {}
    total_records = total_selected = total_bytes = 0
    for level in R.LEVELS:
        path = os.path.join(args.source_dir, level.upper() + ".GOB")
        gob = open(path, "rb").read()
        rows = objects_from_file(path, gob)
        assert Counter(row["class"] for row in rows) == Counter(R.COUNTS[level])
        gobs[level], rows_by_level[level] = gob, rows
        total_records += len(rows)
        total_bytes += loader(args.executable, lump(gob, "objects.ob"), rows)
        total_selected += factory(args.executable, rows, args.seed)
    assert total_records == 699 and total_selected == 660
    resource_requests = resource_tables(args.executable, args.source_dir)
    requests = sum(constructor(args.executable,
                               next(row for row in rows_by_level[level]
                                    if row["class"] == name), definition,
                               resource_requests[definition], args.seed)
                   for level, name, definition in (
                       ("innovat1", "clockworkcutter", 0x4ff260),
                       ("innovat1", "clockworkhammer", 0x4ff260),
                       ("inmine1", "Droid", 0x500a88),
                       ("innovat2", "IronGuardian", 0x500960)))
    assert requests == 96 and total_bytes == 22156
    direct = direct_requests(args.executable, rows_by_level, args.seed)
    exits = script_contract(gobs, rows_by_level)
    print(f"PASS seed {args.seed}: {total_records} records/{total_bytes} consumed bytes, "
          f"{total_selected} factory objects, 70 class-definition entries, "
          f"{requests} requests through four constructor chains, {direct} direct probes, "
          f"{exits} addressed exits; "
          "allocation/resource returns and downstream services stubbed")


if __name__ == "__main__":
    main()
