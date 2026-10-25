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
    for definition, count in R.DEFINITIONS.items():
        archive = elf.cstr(elf.u32(definition))
        assert archive and archive.lower().endswith(".lmp")
        names = tuple(elf.cstr(elf.u32(definition + 8 + 8 * i))
                      for i in range(count))
        assert len(set(names)) == count and all(names)
        assert elf.u32(definition + 8 + 8 * count) == 0
        expected[definition] = [(archive, name) for name in names]
        assert_requests_present(expected[definition], source_dir)
    assert sum(map(len, expected.values())) == 89
    return expected


def assert_requests_present(requests, source_dir):
    by_archive = {}
    for archive, entry in requests:
        assert archive and archive.lower().endswith(".lmp") and entry
        by_archive.setdefault(archive, set()).add(entry.lower())
    for archive, entries in by_archive.items():
        blob = open(os.path.join(source_dir, archive.upper()), "rb").read()
        present = {name.lower() for name, _off, _size in lmp_entries(blob)}
        assert entries <= present, archive


def paired_assets(requests, pairs):
    assert len(requests) == pairs * 2
    assert len({archive for archive, _name in requests}) == 1
    stems = []
    for model, texture in zip(requests[::2], requests[1::2]):
        assert model[0] == texture[0]
        assert model[1].lower().endswith(".vif")
        assert texture[1].lower().endswith(".tex")
        stem = model[1][:-4].lower()
        assert stem and texture[1][:-4].lower() == stem
        stems.append(stem)
    assert len(set(stems)) == pairs


def constructor(executable, row, definition, prefix, source_dir, seed):
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
    assert requests[:len(prefix)] == prefix, row["class"]
    assert len(requests) == R.HOSTILE_REQUESTS[row["class"]]
    tail = requests[len(prefix):]
    if row["class"].startswith("Orc2"):
        paired_assets(tail, 17)
    elif row["class"].startswith("Goblin"):
        paired_assets(tail, 7)
    else:
        assert not tail
    if tail:
        assert tail[0][0] != prefix[0][0]
    assert_requests_present(requests, source_dir)
    return len(requests)


def direct_requests(executable, rows_by_level, definitions, source_dir, seed):
    representatives = {row["class"]: row for rows in rows_by_level.values()
                       for row in rows if row["class"] in R.DIRECT_REQUEST_COUNTS}
    assert set(representatives) == set(R.DIRECT_REQUEST_COUNTS)
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
        assert len(requests) == R.DIRECT_REQUEST_COUNTS[name], name
        if name == "Catapult":
            assert requests[:2] == definitions[0x4ff240]
            assert requests[2][0] == requests[0][0]
            assert requests[2][1].lower().endswith(".anm")
            assert requests[2][1][:-4].lower() == requests[0][1][:-4].lower()
        elif name == "kelethinBomb":
            assert requests == definitions[0x4ffe08]
        elif name == "Barrel":
            paired_assets(requests, 1)
        assert_requests_present(requests, source_dir)
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

    def entry_at(self, offset):
        found = [name for name, at in self.entries.items() if at == offset]
        assert len(found) == 1, hex(offset)
        return found[0]

    def word(self, offset):
        assert offset % 4 == 0 and 0 <= offset < self.end - self.start
        return struct.unpack_from("<I", self.image, self.start + offset)[0]

    def arguments(self, offset, native, count, string_indices=()):
        assert self.word(offset) == 0x7b
        assert self.word(offset + 4) == self.natives.index(native)
        values = []
        for i in range(count + 1):
            at = offset - 8 * (count + 1 - i)
            assert self.word(at) == 0x27
            values.append(self.word(at + 4))
        assert values[-1] == count * 4
        actual = list(reversed(values[:-1]))
        for i in string_indices:
            actual[i] = self.strings[actual[i]]
        return tuple(actual)

    def call(self, offset, native, *args):
        actual = list(self.arguments(offset, native, len(args),
                                     [i for i, x in enumerate(args)
                                      if isinstance(x, str)]))
        for i, expected in enumerate(args):
            assert actual[i] == expected, (hex(offset), native, actual, args)
        assert tuple(actual) == args, (hex(offset), native, actual, args)


def props(rows, cls):
    return [dict(x.split("=", 1) for x in row["properties"].split(";")
                 if "=" in x) for row in rows if row["class"] == cls]


def stage_effects(strife, rows, bridges):
    # VM opcodes come from scr.OPS: 0x0f stores A in a local, 0x69
    # compares A to a literal, and 0x35 branches when A is zero.
    assert strife.entry_at(0x568) == strife.entry_for(0x594)
    assert strife.arguments(0x594, "preloadResource", 1, (0,))[0]
    counter = strife.arguments(0x5e8, "getv", 1, (0,))[0]
    assert strife.word(0x5f8) == 0x0f and strife.word(0x5fc) == 0x14c
    assert strife.word(0x15a0) == 0x14c and strife.word(0x15a4) == 0x27
    assert strife.strings[strife.word(0x15a8)] == counter
    assert strife.word(0x15b4) == 0x7b
    assert strife.word(0x15b8) == strife.natives.index("setv")

    scouts = [p.get("name") for p in props(rows, "NPC")]
    assert len(scouts) == len(set(scouts)) == 4 and all(scouts)
    stage_keys = [strife.arguments(at, "getv", 1, (0,))[0]
                  for at in (0x678, 0x760, 0x844, 0x928)]
    assert stage_keys[0] == stage_keys[1]
    assert len(set(stage_keys)) == 3
    assert strife.word(0x688) == 0x54  # first stage negates the saved flag
    for branch_at, skip_to in ((0x68c, 0x744), (0x770, 0x828),
                               (0x854, 0x90c), (0x938, 0x9f0)):
        assert [strife.word(branch_at), strife.word(branch_at + 4)] == [
            0x35, skip_to]
    for sites, visible in (
            ((0x6b0, 0x6dc, 0x708, 0x734), 0),
            ((0x794, 0x7c0, 0x7ec, 0x818), 1),
            ((0x878, 0x8a4, 0x8d0, 0x8fc), 2),
            ((0x95c, 0x988, 0x9b4, 0x9e0), 3)):
        targets = [strife.arguments(at, "showMonster" if i == visible
                    else "hideMonster", 1, (0,))[0]
                   for i, at in enumerate(sites)]
        assert targets == scouts

    assert strife.entry_at(0x200c) == strife.entry_for(0x2040)
    strife.call(0x2040, "setv",
                strife.arguments(0x1f44, "getv", 1, (0,))[0], 1)
    assert strife.arguments(0x20a4, "callScript", 1, (0,)) == (
        strife.entry_at(0xc94),)
    quest = strife.arguments(0x20d8, "addQuest", 2, (0, 1))
    assert all(quest)
    bridge_calls = [strife.arguments(at, "trigger", 2, (0,))[0]
                    for at in (0x1c90, 0x1df0, 0x1ed4)]
    assert len(set(bridge_calls)) == 3 and set(bridge_calls) == set(bridges)
    assert strife.arguments(0x1f00, "removeQuest", 1, (0,)) == (quest[0],)

    assert strife.entry_at(0x15cc) == strife.entry_for(0x1670)
    assert [strife.word(at) for at in (0x1668, 0x166c, 0x1670,
                                      0x1674, 0x1678)] == [0x01, 0x14c, 0x69, 2, 0x35]
    assert strife.word(0x167c) == 0x1690
    assert [strife.word(at) for at in (0x1694, 0x1698)] == [0x35, 0x1770]
    assert strife.arguments(0x16f4, "setv", 2, (0,)) == (stage_keys[3], 1)
    assert strife.arguments(0x1720, "callScript", 1, (0,)) == (
        strife.entry_at(0x17f8),)


def switch_effects(drundar, boss_name, doors, stairs):
    for at in (0x18c, 0x1c8, 0x204):
        assert drundar.arguments(at, "setMonsterVal", 3, (0,))[0] == boss_name
    assert drundar.arguments(0x374, "autoPropSetState", 2, (0,)) == (doors[0], 1)
    assert drundar.arguments(0x3a8, "autoPropSetState", 2, (0,)) == (stairs[0], 1)

    restore = {}
    for get_at, effect_at, skip_to in zip(
            (0x47c, 0x4f0, 0x564, 0x5d8, 0x64c, 0x6c0, 0x734, 0x7a8),
            (0x4b0, 0x524, 0x598, 0x60c, 0x680, 0x6f4, 0x768, 0x7dc),
            (0x4d4, 0x548, 0x5bc, 0x630, 0x6a4, 0x718, 0x78c, 0x800)):
        key = drundar.arguments(get_at, "getv", 1, (0,))[0]
        effect = drundar.arguments(effect_at, "callScript", 1, (0,))[0]
        assert [drundar.word(get_at + 0x10),
                drundar.word(get_at + 0x14)] == [0x35, skip_to]
        assert key and effect and effect in drundar.entries
        restore[key] = effect
    assert len(restore) == 8
    seen = set()
    for key_at, action_at in R.SWITCH_OFFSETS:
        key = drundar.arguments(key_at + 0x2c, "getv", 1, (0,))[0]
        assert drundar.word(key_at + 0x3c) == 0x54
        assert [drundar.word(at) for at in (action_at + 0x1c,
                                            action_at + 0x20)] == [0x6d, 0]
        assert drundar.arguments(action_at + 0x48, "setv", 2, (0,)) == (key, 1)
        assert drundar.arguments(action_at + 0x74, "callScript", 1, (0,)) == (
            restore[key],)
        seen.add(key)
    assert seen == set(restore)

    assert [drundar.word(at) for at in (0x868, 0x86c, 0x870,
                                       0x874, 0x878)] == [0x01, 0, 0x69, 8, 0x35]
    assert drundar.word(0x87c) == 0x900
    assert [drundar.word(at) for at in (0x1c54, 0x1c58, 0x1c5c,
                                       0x1c60)] == [0x01, 0, 0x69, 8]
    assert drundar.arguments(0x8dc, "addDeferedCall", 1, (0,)) == (
        drundar.entry_at(0x934),)
    assert drundar.arguments(0x9e4, "callScript", 1, (0,)) == (
        drundar.entry_at(0xa3c),)
    assert drundar.arguments(0xacc, "cutScene", 1, (0,))[0]
    flag = drundar.arguments(0x338, "getv", 1, (0,))[0]
    assert [drundar.word(at) for at in (0x348, 0x34c)] == [0x35, 0x3b8]
    assert drundar.arguments(0xa68, "getv", 1, (0,)) == (flag,)
    assert [drundar.word(at) for at in (0xa7c, 0xa80)] == [0x35, 0xb10]
    assert drundar.arguments(0xb00, "setv", 2, (0,)) == (flag, 1)


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
        assert script.entry_for(back) == script.entry_at(0x464 if level == "strife" else 0x1bf4)
        assert all(script.entry_for(site) == "exitzone"
                   for site in (grant, hub, arena))
    strife, drundar = s["strife"], s["drundar"]
    assert strife.entries["start"] == 0x638
    assert drundar.entries["start"] == 0x150
    scenes = [strife.arguments(site, "cutScene", 1, (0,))[0]
              for site in (0xffc, 0x14b0, 0x1900)]
    assert len(set(scenes)) == 3 and all(scenes)
    for site, wrapper_at, target_at in (
            (0x0b4, 0x88, 0xbbc), (0x0f8, 0xcc, 0xc20),
            (0x408, 0x3dc, 0x10b0), (0x44c, 0x420, 0x1114),
            (0x164, 0x138, 0x156c)):
        assert strife.entry_for(site) == strife.entry_at(wrapper_at)
        assert strife.arguments(site, "callScript", 1, (0,)) == (
            strife.entry_at(target_at),)
    assert [strife.entry_for(site) for site in (0xffc, 0x14b0, 0x1900)] == [
        strife.entry_at(at) for at in (0xf9c, 0x13cc, 0x1850)]
    assert drundar.arguments(0xacc, "cutScene", 1, (0,))[0]
    assert drundar.entry_for(0x1c94) == drundar.entry_at(0x1c68)
    assert drundar.entry_for(0x2358) == drundar.entry_at(0x232c)
    assert drundar.arguments(0x1c94, "callScript", 1, (0,)) == (
        drundar.entry_at(0x1918),)
    assert drundar.arguments(0x2358, "callScript", 1, (0,)) == (
        drundar.entry_at(0x1adc),)
    assert drundar.entry_for(0xacc) == drundar.entry_at(0xa3c)
    drundar.call(0x89c, "setSaveInhibit", 1)
    drundar.call(0xaa0, "setSaveInhibit", 0)
    assert [p.get("action") for p in props(rows_by_level["strife"], "PushTrigger")] == [
        strife.entry_at(at) for at in (0x0, 0x464)]
    assert [p.get("t") for p in props(rows_by_level["strife"], "Trigger")] == [
        strife.entry_at(at) for at in (0x4a8, 0x464)]
    assert [p.get("dialogscript") for p in props(rows_by_level["strife"], "NPC")] == [
        strife.entry_at(at) for at in (0x17c, 0x214, 0x2ac, 0x344)]
    bridges = [p.get("name") for p in props(rows_by_level["strife"], "dbridge")]
    assert len(bridges) == len(set(bridges)) == 3 and all(bridges)
    assert Counter(p.get("deathscript") for p in props(rows_by_level["strife"], "Catapult")) == {
        strife.entry_at(0x138): 2}
    for cls, tagged, init_at, death_at in (
            ("Orc2Archer", 8, 0x88, 0xcc),
            ("Orc2Soldier", 5, 0x88, 0xcc),
            ("Orc2Shaman", 2, 0x3dc, 0x420)):
        linked = [p for p in props(rows_by_level["strife"], cls)
                  if "initscript" in p or "deathscript" in p]
        assert len(linked) == tagged
        assert all((p.get("initscript"), p.get("deathscript")) ==
                   (strife.entry_at(init_at), strife.entry_at(death_at))
                   for p in linked)
    push = props(rows_by_level["drundar"], "PushTrigger")
    assert Counter((p.get("key"), p.get("action")) for p in push) == {
        (None, None): 8, (None, drundar.entry_at(0x1bf4)): 1,
        (drundar.entry_at(0x1c38), drundar.entry_at(0x1c68)): 4}
    assert Counter(p.get("t") for p in props(rows_by_level["drundar"], "Trigger")) == {
        drundar.entry_at(0x232c): 2, drundar.entry_at(0x1c68): 4}
    doors = [p.get("name") for p in props(rows_by_level["drundar"], "arenadoor")]
    assert len(doors) == 4 and len(set(doors)) == 1 and doors[0]
    stairs = [p.get("name") for p in props(rows_by_level["drundar"], "UWStair")]
    assert len(stairs) == 1 and stairs[0]
    boss = [(p.get("name"), p.get("miniboss"))
            for p in props(rows_by_level["drundar"], "Ogre")]
    assert boss.count((None, None)) == 13
    assert len(boss) == 14
    boss_name = next(name for name, flag in boss if name is not None and flag == "1")
    switches = props(rows_by_level["drundar"], "uwswitch")
    assert len(switches) == 8
    assert tuple((p["key"], p["action1"]) for p in switches) == tuple(
        (drundar.entry_at(key_at), drundar.entry_at(action_at))
        for key_at, action_at in R.SWITCH_OFFSETS)
    assert all(p["action1"] in drundar.entries and p["key"] in drundar.entries
               for p in switches)
    assert all(p["action"] in strife.entries for p in props(rows_by_level["strife"], "PushTrigger"))
    assert all(p.get("action") in drundar.entries for p in push if p.get("action"))
    for level in ("strife", "drundar"):
        for cls in R.PROPERTY_CLASSES[level]:
            values = [p.get("lump", p.get("lumpname"))
                      for p in props(rows_by_level[level], cls)]
            assert values and len(set(values)) == 1 and values[0], (level, cls)
    stage_effects(strife, rows_by_level["strife"], bridges)
    switch_effects(drundar, boss_name, doors, stairs)
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
            prefix = list(resources[definition])
            row = next(row for row in rows_by_level[level] if row["class"] == name)
            requests += constructor(args.executable, row, definition, prefix,
                                    args.source_dir, args.seed)
    assert requests == 527
    direct = direct_requests(args.executable, rows_by_level, resources,
                             args.source_dir, args.seed)
    script_contract(gobs, rows_by_level)
    print(f"PASS seed {args.seed}: {total_records} records/{total_bytes} loader bytes, "
          f"{total_selected} factory selections, 89 definition entries, "
          f"{requests} requests through nine hostile constructor chains, "
          f"{direct} bounded direct probes, two script/exit contracts; "
          "allocation, resource returns and downstream services stubbed")


if __name__ == "__main__":
    main()
