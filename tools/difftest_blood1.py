#!/usr/bin/env python3
"""Compare blood1 factory/loader and hostile resource contracts with EE code.

PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_blood1.py \
  local/SLUS_209.73 local/BLOOD1.GOB local/KOBOLD.LMP local/WWRAITH.LMP \
  --seed 20973

The original loader, factory and base resource-list traversal execute in
ee_emu.  Constructors, allocation, res_find results and combat are stubbed;
this does not establish live object or resource loading in the native client.
"""
import argparse
from collections import Counter
import hashlib
import random
import struct

from dump_tables import (Elf, find_in_lump, gob_entries, lmp_entries,
                         objects_from_file)
from ee_emu import EE
import ref_blood1 as R
import scr

SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
FACTORY, POOL_NEW, SET_FACTORY, LOAD = 0x159C94, 0x14FDB8, 0x14F6A8, 0x14E808


class FactoryFollow:
    def __contains__(self, addr):
        return addr in (FACTORY, 0x159C20, 0x14F730, 0x14F850) or 0x3A5000 <= addr < 0x3C0000


def cstr(mem, addr):
    return mem.cstr(addr & 0xFFFFFFFF, 128)


def put(emu, value):
    raw = value.encode("latin1") + b"\0"
    ptr = emu.alloc(len(raw))
    emu.mem.write(ptr, raw)
    return ptr


def lump(gob, wanted):
    found = []
    for _name, off, size in gob_entries(gob):
        data = find_in_lump(gob[off:off + size], wanted)
        if data is not None:
            found.append(data)
    assert len(found) == 1, wanted
    return found[0]


def loader(executable, blob, rows):
    emu = EE(executable)
    emu.follow = {LOAD, SET_FACTORY, 0x3B8DC4, 0x3B8F30}
    source = emu.alloc(len(blob) + 16)
    emu.mem.write(source, blob)
    seen = []

    def record(e):
        ptr = e.r[7] & 0xFFFFFFFF
        props = []
        if ptr:
            for i in range(256):
                value = e.mem.u32(ptr + i * 4)
                if not value:
                    break
                props.append(cstr(e.mem, value))
            else:
                raise AssertionError("unterminated properties")
        seen.append((cstr(e.mem, e.r[4]), e.r[6] & 0xFFFF, tuple(props)))
        return 0

    callback = emu.alloc(8)
    emu.stub(callback, function=record)
    emu.call(SET_FACTORY, callback)
    consumed = emu.call(LOAD, source, 0, max_steps=10000000)
    assert len(seen) == len(rows) == 363
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
    block = emu.alloc(0x1000)
    world = emu.alloc(0x100)
    emu.mem.w32(0x44FDC8, world)  # PushTrigger reads world+0x70.
    emu.stub(POOL_NEW, ret=block)
    ordered = list(rows)
    random.Random(seed).shuffle(ordered)
    constructed = 0
    for row in ordered:
        key = row["class"].lower()
        assert key in R.FACTORY or key in R.NO_OBJECT, (row["index"], key)
        name = put(emu, row["class"])
        strings = [put(emu, x) for x in row["properties"].split(";") if x]
        props = emu.alloc((len(strings) + 1) * 4)
        for i, ptr in enumerate(strings):
            emu.mem.w32(props + i * 4, ptr)
        pos = emu.alloc(12)
        emu.reset_log()
        result = emu.call(FACTORY, name, pos, row["angle"], props, max_steps=500000)
        alloc = [c for c in emu.calls if c.target == POOL_NEW]
        ctors = [c for c in emu.calls if c.target not in
                 (POOL_NEW, 0x159C20, 0x14F730, 0x14F850)
                 and not 0x3A5000 <= c.target < 0x3C0000]
        expected = R.FACTORY.get(key)
        if expected is None:
            assert not alloc and result == 0, row["index"]
        else:
            assert len(alloc) == 1 and alloc[0].args[0] == expected[0]
            assert ctors and ctors[-1].target == expected[1], row["index"]
            assert result == block, row["index"]
            constructed += 1
    assert constructed == 351
    return constructed


def resources(executable, archives):
    elf = Elf(open(executable, "rb").read())
    checked = 0
    for definition, (archive_name, names) in R.RESOURCE_DEFS.items():
        assert elf.cstr(elf.u32(definition)) == archive_name
        assert tuple(elf.cstr(elf.u32(definition + 8 + i * 8))
                     for i in range(len(names))) == names
        assert elf.u32(definition + 8 + len(names) * 8) == 0
        present = {name.lower() for name, _off, _size in lmp_entries(archives[archive_name])}
        assert all(name.lower() in present for name in names)
        emu = EE(executable)
        emu.follow = {0x14CB10, 0x14C880, 0x3B8DC4, 0x3B8F30}
        emu.mem.w32(0x41BF78, 1)
        obj, pos = emu.alloc(0x100), emu.alloc(12)
        requests = []
        emu.stub(0x17365C, function=lambda e: requests.append(
            (cstr(e.mem, e.r[4]), cstr(e.mem, e.r[5]))) or 0)
        emu.call(0x14CB10, obj, pos, definition, 0, max_steps=500000)
        assert requests == [(archive_name, name) for name in names]
        checked += len(requests)
    return checked


def direct_requests(executable, rows, seed):
    # Execute four selected derived constructors through the real factory.
    # Every deeper service is stubbed, so only the direct res_find call names
    # are a contract; no model pointer or effect result is claimed.
    chosen = [next(row for row in rows if row["class"] == name)
              for name in R.DIRECT_REQUESTS]
    random.Random(seed).shuffle(chosen)
    for row in chosen:
        ctor = R.FACTORY[row["class"].lower()][1]
        emu = EE(executable)

        class Follow(FactoryFollow):
            def __contains__(self, addr):
                return addr == ctor or super().__contains__(addr)

        emu.follow = Follow()
        block = emu.alloc(0x1000)
        emu.stub(POOL_NEW, ret=block)
        name = put(emu, row["class"])
        strings = [put(emu, x) for x in row["properties"].split(";") if x]
        props = emu.alloc((len(strings) + 1) * 4)
        for i, ptr in enumerate(strings):
            emu.mem.w32(props + i * 4, ptr)
        pos = emu.alloc(12)
        assert emu.call(FACTORY, name, pos, row["angle"], props,
                        max_steps=1000000) == block
        actual = tuple((cstr(emu.mem, call.args[0]), cstr(emu.mem, call.args[1]))
                       for call in emu.calls if call.target == 0x17365C)
        assert actual == R.DIRECT_REQUESTS[row["class"]], row["class"]
    return len(chosen)


def script_contract(gob, rows):
    image = lump(gob, "script.scr")
    parsed = scr.parse(image)
    imports = {name for _off, name in parsed["externals"]}
    entries = {name for _off, name in parsed["internals"]}
    assert len(entries) == 21
    assert {"cutScene", "addQuest", "removeQuest", "setMissionAvailable",
            "givePlayerItem", "startDialog", "newWorld", "setEvil",
            "autoPropSetState"} <= imports
    assert {"start", "absorb", "gooddoor", "evildoor", "giveshard",
            "checkShardCount", "startDia1ce", "newWorld1c57",
            "newWorldbcf6", "setEvil3024", "setEvil1037"} <= entries
    linked = {r["class"]: r["properties"].split(";") for r in rows
              if r["class"] in ("NPC", "Portal", "Trigger")}
    assert "dialogscript=startDia1ce" in linked["NPC"]
    assert "t=ifdcc4" in linked["Trigger"]
    assert "lump=jumpgate" in linked["Portal"]
    exits = [r["properties"].split(";") for r in rows if r["class"] == "PushTrigger"]
    assert len(exits) == 2
    assert {"action=newWorld1c57", "action=newWorldbcf6"} == {
        value for props in exits for value in props if value.startswith("action=")}
    return len(entries)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("executable")
    ap.add_argument("gob")
    ap.add_argument("kobold_lmp")
    ap.add_argument("wwraith_lmp")
    ap.add_argument("--seed", type=int, default=20973)
    args = ap.parse_args()
    assert hashlib.sha256(open(args.executable, "rb").read()).hexdigest() == SHA256
    gob = open(args.gob, "rb").read()
    rows = objects_from_file(args.gob, gob)
    assert Counter(r["class"] for r in rows) == Counter(R.CLASS_COUNTS)
    assert len(R.FACTORY) == 20
    assert all(any(row["class"].lower() == key for row in rows)
               for key in R.FACTORY)
    assert sum(r["class"] in {"Kobold", "Koboldtough", "koboldshaman", "WarWraith"}
               for r in rows) == 140
    consumed = loader(args.executable, lump(gob, "objects.ob"), rows)
    built = factory(args.executable, rows, args.seed)
    slots = resources(args.executable, {
        "kobold.lmp": open(args.kobold_lmp, "rb").read(),
        "wwraith.lmp": open(args.wwraith_lmp, "rb").read(),
    })
    direct = direct_requests(args.executable, rows, args.seed)
    entries = script_contract(gob, rows)
    print("PASS seed %d: 363 original records/%d bytes, %d factory objects, "
          "140 hostile records, %d resource requests, %d direct ctor probes, "
          "%d script entries; "
          "constructors and resource returns stubbed" %
          (args.seed, consumed, built, slots, direct, entries))


if __name__ == "__main__":
    main()
