#!/usr/bin/env python3
"""Bounded v2.00 loader, factory, resource and script checks for mission 1 exits.

PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_strife_drundar.py \
  local/SLUS_209.73 local/BG/DATA --seed 20973

Reads owner-supplied ignored inputs. ee_emu executes original functions on
synthetic state; allocation, resource results and downstream services are
stubbed. No level, combat or mission is run end to end.
"""
import argparse
from collections import Counter
import hashlib
import os
import random
import struct

from dump_tables import Elf, find_in_lump, gob_entries, lmp_entries, objects_from_file
from ee_emu import EE
import ref_strife_drundar as R
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


def props_for(emu, row):
    strings = [put(emu, x) for x in row["properties"].split(";") if x]
    props = emu.alloc((len(strings) + 1) * 4)
    for i, ptr in enumerate(strings):
        emu.mem.w32(props + i * 4, ptr)
    return props


def lump(gob, wanted):
    found = [data for _name, off, size in gob_entries(gob)
             if (data := find_in_lump(gob[off:off + size], wanted)) is not None]
    assert len(found) == 1, wanted
    return found[0]


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
                raise AssertionError("unterminated property list")
        seen.append((cstr(e.mem, e.r[4]), e.r[6] & 0xffff, tuple(props)))
        return 0

    callback = emu.alloc(8)
    emu.stub(callback, function=record)
    emu.call(SET_FACTORY, callback)
    consumed = emu.call(LOAD, source, 0, max_steps=10000000)
    assert len(seen) == len(rows)
    for actual, row in zip(seen, rows):
        # The generic table reader joins properties with ';'; customVars can
        # itself contain semicolons, so compare the lossless joined text.
        assert actual[:2] == (row["class"], row["angle"]), row["index"]
        assert ";".join(actual[2]) == row["properties"], row["index"]
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
        expected = None if key == "crate" and not row["properties"] else R.FACTORY.get(key)
        if expected is None:
            assert not alloc and result == 0, row["index"]
        else:
            assert len(alloc) == 1 and alloc[0].args[0] == expected[0]
            assert ctors and ctors[-1].target == expected[1], row["index"]
            assert result == block, row["index"]
            selected += 1
    return selected


def resource_definitions(executable, source_dir):
    elf = Elf(open(executable, "rb").read())
    expected = {}
    for definition, (archive, count) in R.DEFINITIONS.items():
        assert elf.cstr(elf.u32(definition)) == archive
        names = tuple(elf.cstr(elf.u32(definition + 8 + 8 * i))
                      for i in range(count))
        assert len(set(names)) == count and all(names)
        assert elf.u32(definition + 8 + 8 * count) == 0
        blob = open(os.path.join(source_dir, archive.upper()), "rb").read()
        present = {name.lower() for name, _off, _size in lmp_entries(blob)}
        assert all(name.lower() in present for name in names), archive
        expected[definition] = [(archive, name) for name in names]
    for archive, stems in (("orc_wep2.lmp", R.ORC_WEAPONS),
                           ("goblin_z.lmp", R.GOBLIN_WEAPONS)):
        blob = open(os.path.join(source_dir, archive.upper()), "rb").read()
        present = {name.lower() for name, _off, _size in lmp_entries(blob)}
        assert all(stem + suffix in present for stem in stems
                   for suffix in (".vif", ".tex")), archive
    for requests in R.DIRECT_REQUESTS.values():
        for archive, entry in requests:
            blob = open(os.path.join(source_dir, archive.upper()), "rb").read()
            assert entry.lower() in {name.lower() for name, _off, _size
                                     in lmp_entries(blob)}, (archive, entry)
    assert sum(map(len, expected.values())) == 89
    return expected


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
    assert requests == expected_requests, row["class"]
    return len(requests)


def direct_requests(executable, rows_by_level, seed):
    representatives = {row["class"]: row for rows in rows_by_level.values()
                       for row in rows if row["class"] in R.DIRECT_REQUESTS}
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
        assert tuple(requests) == R.DIRECT_REQUESTS[name], name
    return len(representatives)


class ScriptCheck:
    def __init__(self, image):
        self.image = image
        parsed = scr.parse(image)
        self.start, self.end = parsed["code"]
        self.entries = {name: offset for offset, name in parsed["internals"]}
        self.natives = [name for _off, name in parsed["externals"]]
        self.strings = dict(scr.strings(image, *parsed["strings"]))

    def entry_for(self, offset):
        ordered = sorted((at, name) for name, at in self.entries.items())
        found = [name for i, (at, name) in enumerate(ordered)
                 if at <= offset < (ordered[i + 1][0] if i + 1 < len(ordered)
                                   else self.end - self.start)]
        assert len(found) == 1, hex(offset)
        return found[0]

    def word(self, offset):
        assert offset % 4 == 0 and 0 <= offset < self.end - self.start
        return struct.unpack_from("<I", self.image, self.start + offset)[0]

    def call(self, offset, native, *args):
        assert self.word(offset) == 0x7b
        assert self.word(offset + 4) == self.natives.index(native)
        values = []
        for i in range(len(args) + 1):
            at = offset - 8 * (len(args) + 1 - i)
            assert self.word(at) == 0x27
            values.append(self.word(at + 4))
        assert values[-1] == len(args) * 4
        actual = list(reversed(values[:-1]))
        for i, expected in enumerate(args):
            if isinstance(expected, str):
                actual[i] = self.strings[actual[i]]
        assert tuple(actual) == args, (hex(offset), native, actual, args)


def props(rows, cls):
    return [dict(x.split("=", 1) for x in row["properties"].split(";")
                 if "=" in x) for row in rows if row["class"] == cls]


def script_contract(gobs, rows_by_level):
    s = {level: ScriptCheck(lump(gob, "script.scr"))
         for level, gob in gobs.items()}
    assert (len(s["strife"].entries), len(s["drundar"].entries)) == (47, 36)
    assert (len(s["strife"].natives), len(s["drundar"].natives)) == (21, 20)
    for level, back, onward, grant, hub, arena in (
            ("strife", 0x490, 0x19e8, 0x1abc, 0x1ae8, 0x1b94),
            ("drundar", 0x1c20, 0x1918, 0x19ec, 0x1a18, 0x1ac4)):
        script = s[level]
        assert script.entries["exitzone"] == onward
        script.call(back, "newWorld", "blood1")
        script.call(grant, "grantMission", 1)
        script.call(hub, "newWorld", "hub")
        script.call(arena, "newWorld", "drunarm" if level == "strife" else "drunare")
        assert script.entry_for(back) == "newWorld5d32"
        assert all(script.entry_for(site) == "exitzone"
                   for site in (grant, hub, arena))
        assert script.entries["newWorld5d32"] == (0x464 if level == "strife" else 0x1bf4)
    strife, drundar = s["strife"], s["drundar"]
    assert strife.entries["start"] == 0x638
    assert drundar.entries["start"] == 0x150
    for site, scene in ((0xffc, "step1com"), (0x14b0, "step2complete"),
                        (0x1900, "step3complete")):
        strife.call(site, "cutScene", scene)
    for site, wrapper, target in (
            (0x0b4, "callScri52e", "step1InitScript"),
            (0x0f8, "callScria77e", "step1DeathScript"),
            (0x408, "callScri9f82", "step2InitScript"),
            (0x44c, "callScri4980", "step2DeathScript"),
            (0x164, "callScri8d4a", "step3DeathScript")):
        assert strife.entry_for(site) == wrapper
        strife.call(site, "callScript", target)
    assert [strife.entry_for(site) for site in (0xffc, 0x14b0, 0x1900)] == [
        "step1scene", "step2delay", "step3delay"]
    drundar.call(0xacc, "cutScene", "doors")
    assert drundar.entry_for(0x1c94) == "callScri5a82"
    assert drundar.entry_for(0x2358) == "callScri28d3"
    drundar.call(0x1c94, "callScript", "exitzone")
    drundar.call(0x2358, "callScript", "arenaMessage")
    assert drundar.entry_for(0xacc) == "doors"
    drundar.call(0x89c, "setSaveInhibit", 1)
    drundar.call(0xaa0, "setSaveInhibit", 0)
    assert [p.get("action") for p in props(rows_by_level["strife"], "PushTrigger")] == [
        "callScri5a82", "newWorld5d32"]
    assert [p.get("t") for p in props(rows_by_level["strife"], "Trigger")] == [
        "if9d85", "newWorld5d32"]
    assert [p.get("dialogscript") for p in props(rows_by_level["strife"], "NPC")] == [
        "startDia8851", "startDia30cc", "startDiad2e3", "startDiab722"]
    assert {p.get("name") for p in props(rows_by_level["strife"], "dbridge")} == {
        "bridge1", "bridge2", "bridge3"}
    assert Counter(p.get("deathscript") for p in props(rows_by_level["strife"], "Catapult")) == {
        "callScri8d4a": 2}
    for cls, tagged, init, death in (
            ("Orc2Archer", 8, "callScri52e", "callScria77e"),
            ("Orc2Soldier", 5, "callScri52e", "callScria77e"),
            ("Orc2Shaman", 2, "callScri9f82", "callScri4980")):
        linked = [p for p in props(rows_by_level["strife"], cls)
                  if "initscript" in p or "deathscript" in p]
        assert len(linked) == tagged
        assert all((p.get("initscript"), p.get("deathscript")) == (init, death)
                   for p in linked)
        assert init in strife.entries and death in strife.entries
    push = props(rows_by_level["drundar"], "PushTrigger")
    assert Counter((p.get("key"), p.get("action")) for p in push) == {
        (None, None): 8, (None, "newWorld5d32"): 1,
        ("return56e0", "callScri5a82"): 4}
    assert Counter(p.get("t") for p in props(rows_by_level["drundar"], "Trigger")) == {
        "callScri28d3": 2, "callScri5a82": 4}
    assert Counter(p.get("name") for p in props(rows_by_level["drundar"], "arenadoor")) == {
        "door": 4}
    assert [p.get("name") for p in props(rows_by_level["drundar"], "UWStair")] == ["stairs"]
    assert Counter((p.get("name"), p.get("miniboss"))
                   for p in props(rows_by_level["drundar"], "Ogre")) == {
        (None, None): 13, ("ogreminiboss", "1"): 1}
    switches = props(rows_by_level["drundar"], "uwswitch")
    assert len(switches) == 8
    assert tuple((p["key"], p["action1"]) for p in switches) == R.SWITCH_LINKS
    assert all(p["action1"] in drundar.entries and p["key"] in drundar.entries
               for p in switches)
    assert all(p["action"] in strife.entries for p in props(rows_by_level["strife"], "PushTrigger"))
    assert all(p.get("action") in drundar.entries for p in push if p.get("action"))
    for level in ("strife", "drundar"):
        for cls, wanted in R.PROPERTY_LUMPS[level].items():
            values = [p.get("lump", p.get("lumpname"))
                      for p in props(rows_by_level[level], cls)]
            assert values and set(values) == {wanted}, (level, cls)
    assert Counter(bool(p) for p in props(rows_by_level["drundar"], "Crate")) == {
        True: 70, False: 1}
    return 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("executable")
    ap.add_argument("source_dir", help="ignored directory with extracted GOB/LMP inputs")
    ap.add_argument("--seed", type=int, default=20973)
    args = ap.parse_args()
    assert hashlib.sha256(open(args.executable, "rb").read()).hexdigest() == SHA256
    gobs, rows_by_level = {}, {}
    total_records = total_selected = total_bytes = 0
    for level in ("strife", "drundar"):
        path = os.path.join(args.source_dir, level.upper() + ".GOB")
        gob = open(path, "rb").read()
        rows = objects_from_file(path, gob)
        assert Counter(row["class"] for row in rows) == Counter(R.COUNTS[level])
        gobs[level], rows_by_level[level] = gob, rows
        total_records += len(rows)
        total_bytes += loader(args.executable, lump(gob, "objects.ob"), rows)
        total_selected += factory(args.executable, rows, args.seed)
    assert (total_records, total_selected, total_bytes) == (553, 521, 21740)
    resources = resource_definitions(args.executable, args.source_dir)
    requests = 0
    for level in ("strife", "drundar"):
        for name in sorted(R.HOSTILES[level]):
            definition = R.HOSTILE_DEF[name]
            expected = list(resources[definition])
            if level == "strife":
                expected += [("orc_wep2.lmp", stem + suffix)
                             for stem in R.ORC_WEAPONS for suffix in (".vif", ".tex")]
            elif name != "Ogre":
                expected += [("goblin_z.lmp", stem + suffix)
                             for stem in R.GOBLIN_WEAPONS for suffix in (".vif", ".tex")]
            row = next(row for row in rows_by_level[level] if row["class"] == name)
            assert len(expected) == R.HOSTILE_REQUESTS[name]
            requests += constructor(args.executable, row, definition, expected, args.seed)
    assert requests == 527
    direct = direct_requests(args.executable, rows_by_level, args.seed)
    script_contract(gobs, rows_by_level)
    print(f"PASS seed {args.seed}: {total_records} records/{total_bytes} loader bytes, "
          f"{total_selected} factory selections, 89 definition entries, "
          f"{requests} requests through nine hostile constructor chains, "
          f"{direct} bounded direct probes, two script/exit contracts; "
          "allocation, resource returns and downstream services stubbed")


if __name__ == "__main__":
    main()
