#!/usr/bin/env python3
"""Run the original valor object-record loader and bounded class constructors.

PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_campaign_combat_r5.py \
    local/SLUS_209.73 local/VALOR.GOB local/WARBOAR.LMP \
    local/MINOTAUR.LMP --seed 20973

The loader reads the private objects.ob bytes in ee_emu and visits all 201
records in file order. Its factory is a recording stub. The 84 hostile class
constructors receive those records' real position, angle and properties, but
Creature_ctor and all resource/combat services are stubs. No stub return is
reported as an observed game value; no game data is printed or tracked.
"""
import argparse
import collections
import hashlib
import struct

from dump_tables import find_in_lump, gob_entries, lmp_entries, objects_from_file
from ee_emu import EE
from difftest_campaign_combat import EXPECTED_SHA256, POOL_NEW, RealCalls, original, put_string
from difftest_campaign_combat_r3 import cstr, position
from difftest_objects import A, SET_FACTORY
from ref_combat import Exe
import ref_campaign_combat_r5 as R


def valor_object_blob(gob):
    blobs = [find_in_lump(gob[off:off + size], "objects.ob")
             for _name, off, size in gob_entries(gob)]
    blobs = [blob for blob in blobs if blob is not None]
    assert len(blobs) == 1
    return blobs[0]


def load_records(executable, blob, rows):
    emu = EE(executable)
    emu.follow = {A["world_loadRecords"], SET_FACTORY, 0x3B8DC4, 0x3B8F30}
    base = emu.alloc(len(blob) + 16)
    emu.mem.write(base, blob)
    seen = []

    def record(e):
        mem = e.mem
        props = []
        at = e.r[7] & 0xFFFFFFFF
        if at:
            for index in range(256):
                ptr = mem.u32(at + 4 * index)
                if ptr == 0:
                    break
                props.append(cstr(mem, ptr))
            else:
                raise AssertionError("unterminated property list")
        pos = e.r[5] & 0xFFFFFFFF
        seen.append((cstr(mem, e.r[4] & 0xFFFFFFFF),
                     tuple(mem.u32(pos + 4 * i) for i in range(3)),
                     e.r[6] & 0xFFFF, tuple(props)))
        return 0  # No object is produced; constructor/list effects are not claimed.

    callback = emu.alloc(8)
    emu.stub(callback, function=record)
    emu.call(SET_FACTORY, callback)
    consumed = emu.call(A["world_loadRecords"], base, 0, max_steps=10000000)
    assert len(seen) == len(rows) == 201
    for actual, row in zip(seen, rows):
        expected = (row["class"], position(row), row["angle"],
                    tuple(p for p in row["properties"].split(";") if p))
        assert actual == expected, row["index"]
    expected_end = 8
    for _ in rows:
        expected_end += struct.unpack_from("<h", blob, expected_end + 4)[0]
    assert consumed == expected_end
    return seen, consumed


def check_definitions(executable, archives, rows):
    exe = Exe(executable)
    for definition, (archive, count) in archives.items():
        lump = exe.cstr(exe.u32(definition))
        names = []
        for i in range(count):
            names.append(exe.cstr(exe.u32(definition + 8 + 8 * i)))
        assert exe.u32(definition + 8 + 8 * count) == 0
        assert len(set(names)) == count
        available = {name.lower() for name, _off, _size in lmp_entries(archive)}
        assert all(name.lower() in available for name in names)
        assert R.DEFINITION_SLOTS[lump] == count
        row = next(row for row in rows if
                   (row["class"] == "Minotaur") == (definition == 0x501200)
                   and row["class"] in R.CONSTRUCTORS)
        emu = EE(executable)
        emu.follow = {0x14CB10, 0x14C880, 0x3B8DC4, 0x3B8F30}
        emu.mem.w32(0x41BF78, 1)
        pos = emu.alloc(12)
        for i, word in enumerate(position(row)):
            emu.mem.w32(pos + 4 * i, word)
        observed = []
        emu.stub(0x17365C, function=lambda e: observed.append(
            (cstr(e.mem, e.r[4] & 0xFFFFFFFF),
             cstr(e.mem, e.r[5] & 0xFFFFFFFF))) or 0)
        for generation, expected_count in ((1, count), (1, count), (2, 2 * count)):
            emu.mem.w32(0x41BF78, generation)
            obj = emu.alloc(R.CONSTRUCTORS[row["class"]][1])
            emu.call(0x14CB10, obj, pos, definition, 0, max_steps=500000)
            assert len(observed) == expected_count
            assert observed[-count:] == [(lump, name) for name in names]
            assert emu.mem.u32(definition + 4) == generation
    return sum(count for _archive, count in archives.values())


def check_factory(executable, rows):
    emu = EE(executable)
    emu.follow = RealCalls()
    block = emu.alloc(0x600)
    emu.stub(POOL_NEW, ret=block)
    for row in rows:
        got, selected = original(emu, row)
        ctor, size, _definition = R.CONSTRUCTORS[row["class"]]
        assert got == block and selected == (size, ctor), row["index"]


def trace_constructor(executable, row, seed):
    name = row["class"]
    ctor, size, definition = R.CONSTRUCTORS[name]
    emu = EE(executable)
    emu.follow = {ctor, 0x159C20, 0x3B81A0, 0x3B8DC4, 0x3B8F30}
    emu.mem.w32(0x404464, seed)
    obj = emu.alloc(size)
    pos = emu.alloc(12)
    for i, word in enumerate(position(row)):
        emu.mem.w32(pos + 4 * i, word)
    props = [put_string(emu, p) for p in row["properties"].split(";") if p]
    prop_list = emu.alloc(4 * (len(props) + 1))
    for i, ptr in enumerate(props):
        emu.mem.w32(prop_list + 4 * i, ptr)
    type_name = put_string(emu, name)

    def base_stub(e):
        e.mem.w32(obj + 0x24, definition)
        return 0

    emu.stub(0x109D68, function=base_stub, name="Creature_ctor refused")
    emu.reset_log()
    if name == "Minotaur":
        emu.call(ctor, obj, type_name, pos, row["angle"], prop_list,
                 type_name, max_steps=500000)
        expected_calls = R.MINOTAUR_CALLS
    else:
        emu.call(ctor, obj, pos, row["angle"], prop_list, type_name,
                 max_steps=500000)
        expected_calls = R.BOAR_CALLS
    assert tuple((c.site, c.target) for c in emu.calls) == expected_calls, row["index"]
    base = emu.calls[0]
    assert base.args[0] == obj and base.args[1] == type_name
    assert tuple(emu.mem.u32(base.args[2] + 4 * i) for i in range(3)) == position(row)
    assert base.args[3] & 0xFFFF == row["angle"]
    assert base.args[4] == definition and base.args[5] == prop_list
    events = [c.args[1] for c in emu.calls if c.target == 0x118378]
    assert tuple(events) == R.EVENT_ENTRIES[name]
    event_args = tuple((c.args[1], c.args[2:6], c.fargs[:4])
                       for c in emu.calls if c.target == 0x118378)
    assert event_args == R.EVENT_ARGUMENTS[name], row["index"]
    mask = next(c for c in emu.calls if c.target == 0x179550)
    assert mask.args[1] == (1 if name == "Minotaur" else 0)
    assert next(c for c in emu.calls if c.target == 0x1707B0).args[0] == obj + 0x114
    if name == "Minotaur":
        shared = [c for c in emu.calls if c.target == 0x11BC18]
        assert tuple(c.args[:4] for c in shared) == (
            (obj + 0x3C8, 1, 0x15, 0x20),
            (obj + 0x3C8, 2, 0x19, 0x20))
        assert next(c for c in emu.calls if c.target == 0x28A16C).args[:2] == (obj, 0)
    else:
        push = next(c for c in emu.calls if c.target == 0x170838)
        assert push.args[0] == obj + 0x114 and push.args[2] == 1
    # Every service whose output could make this actor live was auto-stubbed.
    assert all(c.stubbed for c in emu.calls if c.target not in
               (0x159C20, 0x3B81A0))
    return len(emu.calls)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable")
    parser.add_argument("valor_gob")
    parser.add_argument("warboar_lmp")
    parser.add_argument("minotaur_lmp")
    parser.add_argument("--seed", type=int, default=20973)
    args = parser.parse_args()
    with open(args.executable, "rb") as stream:
        assert hashlib.sha256(stream.read()).hexdigest() == EXPECTED_SHA256
    with open(args.valor_gob, "rb") as stream:
        gob = stream.read()
    rows = objects_from_file(args.valor_gob, gob)
    selected = [row for row in rows if row["class"] in R.CONSTRUCTORS]
    assert collections.Counter(row["class"] for row in selected) == {
        "WarBoar": 34, "WarBoarSmall": 44, "Minotaur": 6}
    seen, consumed = load_records(args.executable, valor_object_blob(gob), rows)
    check_factory(args.executable, selected)
    with open(args.warboar_lmp, "rb") as stream:
        boar = stream.read()
    with open(args.minotaur_lmp, "rb") as stream:
        minotaur = stream.read()
    slots = check_definitions(args.executable, {
        0x502F80: (boar, 20), 0x501200: (minotaur, 26)}, selected)
    calls = sum(trace_constructor(args.executable, row, args.seed) for row in selected)
    assert len(seen) == 201 and len(selected) == 84
    print("PASS seed %d: original valor loader %d records/%d bytes;"
          " %d hostile ctor call sequences/%d direct calls; %d original resource"
          " lookups with archive slots present;"
          " resource and combat returns refused" %
          (args.seed, len(seen), consumed, len(selected), calls, slots))


if __name__ == "__main__":
    main()
