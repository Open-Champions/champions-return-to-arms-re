#!/usr/bin/env python3
"""Bounded blood1 script-host and authored-link checks (US v2.00).

PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_blood1_scripts.py \
  local/SLUS_209.73 local/BLOOD1.GOB --seed 20973

The original script loader, native binder and interpreter execute in ee_emu.
Built-in effects are recorded and answered by controlled stubs. This checks
branch order and arguments, not the effects of a whole level playthrough.
"""
import argparse
import hashlib
import random
import struct

from difftest_amx import Original, SCRIPT_RUN_BY_NAME
from dump_tables import find_in_lump, gob_entries, lmp_entries, objects_from_file
import scr

ELF_SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"


def payload(gob, wanted):
    hits = []
    for _name, off, size in gob_entries(gob):
        item = find_in_lump(gob[off:off + size], wanted)
        if item is not None:
            hits.append(item)
    assert len(hits) == 1, (wanted, len(hits))
    return hits[0]


def authored(gob):
    image = payload(gob, "script.scr")
    parsed = scr.parse(image)
    entries = {name: off for off, name in parsed["internals"]}
    imports = {name for _off, name in parsed["externals"]}
    assert entries == {
        "start": 0x0000, "gooddoor": 0x027c, "evildoor": 0x02c0,
        "giveshard": 0x0330, "absorb": 0x03b0, "removeActors": 0x048c,
        "checkShardCount": 0x04d0, "startDia1ce": 0x05e4,
        "returnab41": 0x0638, "newWorld1c57": 0x0674,
        "returnc2d4": 0x06b8, "newWorldbcf6": 0x06f0,
        "ifdcc4": 0x0734, "ifb5cc": 0x07f4,
        "setEvil3024": 0x0868, "setEvil1037": 0x08fc,
        "ifb7fd": 0x0a24, "if3877": 0x0a98,
        "ifa824": 0x0b4c, "setva4d6": 0x0c04,
        "dummyEntryPoint": 0x0c50,
    }
    assert len(imports) == 21
    # Assert the addressed built-in calls reported in the flow table against
    # the authored image, not only against traces from entry dispatch.
    code_start, code_end = parsed["code"]
    external_names = [name for _off, name in parsed["externals"]]
    for offset, name in {
        0x002c: "getMissionComplete", 0x005c: "getEvil",
        0x0098: "addQuest", 0x00d4: "addQuest",
        0x0108: "setMissionAvailable", 0x013c: "setv",
        0x0170: "setv", 0x019c: "postAction",
        0x01c0: "getMadeDecision", 0x01ec: "getEvil",
        0x0228: "autoPropSetState", 0x0264: "autoPropSetState",
        0x02a8: "cutScene", 0x03dc: "getv",
        0x0414: "cutScene", 0x0448: "setv",
        0x0474: "postAction", 0x04b8: "deleteMonster",
        0x0620: "startDialog", 0x08e4: "postAction",
        0x0a0c: "postAction",
    }.items():
        assert code_start + offset + 8 <= code_end, (offset, name)
        opcode, import_index = struct.unpack_from("<II", image, code_start + offset)
        assert opcode == 0x7b and external_names[import_index] == name, (offset, name)
    # No script-owned spawn, kill gate, mission grant, or direct hub request.
    assert not ({"generateMonster", "showMonster", "trigger", "killMonster",
                 "grantMission", "newWorldPost"} & imports)
    rows = objects_from_file("BLOOD1.GOB", gob)
    named = [(r["class"], r["properties"].split(";")) for r in rows]
    assert sum(cls == "NPC" and "dialogscript=startDia1ce" in props for cls, props in named) == 1
    assert sum(cls == "Trigger" and "t=ifdcc4" in props for cls, props in named) == 1
    assert [(next(p for p in props if p.startswith("key=")),
             next(p for p in props if p.startswith("action=")))
            for cls, props in named if cls == "PushTrigger"] == [
                ("key=returnab41", "action=newWorld1c57"),
                ("key=returnc2d4", "action=newWorldbcf6")]
    assert [(cls, props) for cls, props in named if cls == "Player1"] == [
        ("Player1", ["default=1"]), ("Player1", ["from=strife"]),
        ("Player1", ["from=drundar"])]
    staged = [cls for cls, props in named if "name=actor" in props]
    assert sorted(staged) == sorted(["Kobold"] * 8 + ["Koboldtough"] * 2 +
                                    ["koboldshaman"])
    for name in ("gooddoor", "evildoor"):
        assert sum(cls in ("BFhappydoor", "BFfiredoor") and "name=" + name in props
                   for cls, props in named) == 1

    dbin = payload(gob, "natasla.dbin")
    assert len(dbin) == 9 * 0x448 and dbin[0] == 9
    nodes = []
    for index in range(9):
        node = dbin[index * 0x448:(index + 1) * 0x448]
        condition = node[1:0x21].split(b"\0")[0].decode("ascii")
        count = struct.unpack_from("<i", node, 0x54)[0]
        assert 0 <= count <= 12
        choices = []
        for choice in range(count):
            row = node[0x58 + choice * 0x54:0x58 + (choice + 1) * 0x54]
            action = row[0x30:0x50].split(b"\0")[0].decode("ascii")
            nxt = struct.unpack_from("<i", row, 0x50)[0]
            choices.append((action, nxt))
        nodes.append((condition, tuple(choices)))
    assert [condition for condition, _ in nodes] == [
        "ifb5cc", "ifb5cc", "ifb5cc", "ifb5cc", "ifb5cc", "ifb5cc",
        "ifb7fd", "if3877", "ifa824"]
    assert [tuple(next for _act, next in choices) for _cond, choices in nodes] == [
        (1, 3), (2, 3), (-1,), (2, 4), (5, 2), (-1,), (-1,), (-1,), (-1,)]
    assert [(i, action) for i, (_condition, choices) in enumerate(nodes)
            for action, _nxt in choices if action] == [
                (2, "setEvil3024"), (5, "setEvil1037"), (8, "setva4d6")]

    cuts = {}
    camera_types = {}
    for name in ("blood1", "gooddoor", "evildoor"):
        data = payload(gob, name + ".cut")
        flags, key_off, key_count, actor_off, actor_count = struct.unpack_from("<IIIII", data)
        keys = [struct.unpack_from("<fhhiii", data, key_off + 20 * i)
                for i in range(key_count)]
        cuts[name] = (flags, key_count, actor_count,
                      sum(key[1] == -100 for key in keys),
                      round(keys[-1][0], 2))
        camera_types[name] = tuple(sorted((kind, sum(key[1] == -100 and key[2] == kind
                                                      for key in keys))
                                           for kind in {key[2] for key in keys
                                                        if key[1] == -100}))
    assert cuts == {"blood1": (8, 143, 12, 32, 31.30),
                    "gooddoor": (8, 13, 2, 12, 8.47),
                    "evildoor": (8, 12, 2, 11, 7.59)}
    assert camera_types == {
        "blood1": ((0, 7), (1, 6), (2, 6), (4, 2), (5, 1),
                   (6, 2), (7, 3), (9, 5)),
        "gooddoor": ((0, 2), (1, 2), (2, 2), (4, 2), (7, 2), (9, 2)),
        "evildoor": ((0, 2), (1, 2), (2, 2), (4, 1), (7, 2), (9, 2)),
    }
    opening = payload(gob, "blood1.cut")
    _flags, _key_off, _key_count, actor_off, actor_count = struct.unpack_from(
        "<IIIII", opening)
    opening_actors = tuple((opening[actor_off + i * 0x2C + 8:actor_off + i * 0x2C + 0x1C]
                            .split(b"\0")[0].decode("ascii"),
                            opening[actor_off + i * 0x2C + 0x2B])
                           for i in range(actor_count))
    assert opening_actors == (("Kobold", 0),) * 9 + (("koboldshaman", 0),) + \
           (("Koboldtough", 0),) * 2
    for name, target, when in (("gooddoor", 0, 3.93), ("evildoor", 1, 4.91)):
        data = payload(gob, name + ".cut")
        _flags, key_off, key_count, actor_off, actor_count = struct.unpack_from("<IIIII", data)
        assert actor_count == 2
        actors = tuple((data[actor_off + i * 0x2C + 8:actor_off + i * 0x2C + 0x1C]
                        .split(b"\0")[0].decode("ascii"),
                        data[actor_off + i * 0x2C + 0x2B]) for i in range(2))
        assert actors == (("BFhappydoor", 0), ("BFfiredoor", 0))
        key3 = [(round(time, 2), actor, kind) for time, actor, kind, _a, _b, _c
                in (struct.unpack_from("<fhhiii", data, key_off + 20 * i)
                    for i in range(key_count)) if kind == 3]
        assert key3 == [(when, target, 3)]
    return image, parsed


def C(name, *args):
    return name, args


def cases():
    start_common = [C("setMissionAvailable", 1, 1), C("setv", "startedMission1", 1),
                    C("setv", "currentMission", 1), C("postAction", "absorb"),
                    C("getMadeDecision")]
    base = {
        "start": (0, [C("getMissionComplete", 1), C("getEvil"),
                      C("addQuest", "finishtfc", "travelt8f45"), *start_common]),
        "absorb": (0, [C("getv", "bl_sawBlood1"), C("cutScene", "blood1"),
                       C("setv", "bl_sawBlood1", 1), C("postAction", "removeActors")]),
        "removeActors": (0, [C("deleteMonster", "actor")]),
        "gooddoor": (0, [C("cutScene", "gooddoor")]),
        "evildoor": (0, [C("cutScene", "evildoor"), C("postAction", "giveshard")]),
        "giveshard": (0, [C("givePlayerItem", "shardofwar", 0, 0),
                          C("addDeferedCall", "checkShardCount")]),
        "checkShardCount": (0, [C("addHelpMessage", "yourece9678", "thislar4a25"),
                                *(C("onePlayerHasItem", i, "shardofwar") for i in range(4))]),
        "startDia1ce": (0, [C("startDialog", "natasla", 1, 0)]),
        "ifdcc4": (0, [C("getv", "metNatasla"), C("startDialog", "natasla", 1, 0),
                       C("setv", "metNatasla", 1)]),
        "ifb5cc": (1, [C("getMadeDecision")]),
        "ifb7fd": (1, [C("getEvil")]),
        "if3877": (0, [C("getEvil")]),
        "ifa824": (0, [C("getEvil")]),
        "returnab41": (1, [C("getEvil")]),
        "returnc2d4": (0, [C("getEvil")]),
        "newWorld1c57": (0, [C("newWorld", "strife")]),
        "newWorldbcf6": (0, [C("newWorld", "drundar")]),
        "setEvil3024": (0, [C("setEvil", 0), C("setMadeDecision"),
                            C("postAction", "gooddoor")]),
        "setEvil1037": (0, [C("setEvil", 1), C("setMadeDecision"),
                            C("setv", "talkedToNatasla", 1), C("removeQuest", "finishtfc"),
                            C("addQuest", "deliver2b0", "bringth4d82"),
                            C("postAction", "evildoor")]),
        "setva4d6": (0, [C("setv", "talkedToNatasla", 1)]),
        "dummyEntryPoint": (0, []),
    }
    assert len(base) == 21
    out = [(name, {}, result, trace) for name, (result, trace) in base.items()]
    out += [
        ("start", {"getMissionComplete": 1}, 0,
         [C("getMissionComplete", 1), *start_common]),
        ("start", {"getEvil": 1}, 0,
         [C("getMissionComplete", 1), C("getEvil"),
          C("addQuest", "deliver2b0", "bringth4d82"), *start_common]),
        ("start", {"getMadeDecision": 1}, 0,
         [*base["start"][1], C("getEvil"), C("autoPropSetState", "gooddoor", 1)]),
        ("start", {"getMadeDecision": 1, "getEvil": 1}, 0,
         [C("getMissionComplete", 1), C("getEvil"),
          C("addQuest", "deliver2b0", "bringth4d82"), *start_common,
          C("getEvil"), C("autoPropSetState", "evildoor", 1)]),
        ("absorb", {"getv": 1}, 0, [C("getv", "bl_sawBlood1")]),
        ("ifdcc4", {"getv": 1}, 0, [C("getv", "metNatasla")]),
        ("ifb5cc", {"getMadeDecision": 1}, 0, [C("getMadeDecision")]),
        ("ifb7fd", {"getEvil": 1}, 0, [C("getEvil")]),
        ("if3877", {"getEvil": 1}, 0,
         [C("getEvil"), C("getv", "talkedToNatasla")]),
        ("if3877", {"getEvil": 1, "getv": 1}, 1,
         [C("getEvil"), C("getv", "talkedToNatasla")]),
        ("ifa824", {"getEvil": 1}, 1,
         [C("getEvil"), C("getv", "talkedToNatasla")]),
        ("ifa824", {"getEvil": 1, "getv": 1}, 0,
         [C("getEvil"), C("getv", "talkedToNatasla")]),
        ("returnab41", {"getEvil": 1}, 0, [C("getEvil")]),
        ("returnc2d4", {"getEvil": 1}, 1, [C("getEvil")]),
        ("checkShardCount", {"onePlayerHasItem": 2}, 0,
         [C("addHelpMessage", "yourece9678", "thislar4a25"),
          *(call for i in range(4) for call in
            (C("onePlayerHasItem", i, "shardofwar"),
             C("removePlayerItem", i, "shardofwar")))]),
    ]
    return out


def execute(executable, image, parsed, seed):
    orig = Original(executable)
    orig.place(image)
    assert orig.load() == 0
    names = [name.encode("ascii") for _off, name in parsed["externals"]]
    assert orig.register([(name, orig.stubs + 8 * slot)
                          for slot, name in enumerate(names)]) == 0
    saved = orig.save(len(image) + 0x200)
    orig.emu.mem.w32(0x404464, seed)
    orig.emu.mem.w32(0x404460, 0x11111111)
    jobs = cases()
    random.Random(seed).shuffle(jobs)
    for entry, answers, result, expected in jobs:
        orig.restore(saved)
        trace = []

        def native(slot, args, _params):
            name = names[slot].decode("ascii")
            values = []
            for value in args:
                string = orig.string_at(value, len(image))
                values.append(string.decode("latin1") if string else value)
            trace.append(C(name, *values))
            return answers.get(name, 0)

        orig.on_native = native
        orig.on_call_script = lambda _args: 0
        error, index = orig.find(entry.encode("ascii"))
        assert error == 0, entry
        code, cell = orig.interpret(index, (), 0, 0xDEADBEEF)
        assert (code, cell, trace) == (0, result, expected), (
            seed, entry, answers, code, cell, trace, expected)
        # The game dispatches by name, so exercise its wrapper too, from the
        # same fresh script state. This checks lookup and returned value.
        orig.restore(saved)
        trace.clear()
        orig.emu.mem.write(orig.buffer, entry.encode("ascii") + b"\0")
        wrapped = orig.call(SCRIPT_RUN_BY_NAME, orig.buffer)
        assert (wrapped, trace) == (result, expected), (
            seed, entry, answers, wrapped, trace, expected)
        assert orig.emu.mem.u32(0x404464) == seed
        assert orig.emu.mem.u32(0x404460) == 0x11111111
    orig.restore(saved)
    orig.emu.mem.write(orig.buffer, b"notInBlood1\0")
    assert orig.call(SCRIPT_RUN_BY_NAME, orig.buffer) == -1
    return len(jobs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable")
    parser.add_argument("gob")
    parser.add_argument("--seed", type=int, default=20973)
    args = parser.parse_args()
    assert hashlib.sha256(open(args.executable, "rb").read()).hexdigest() == ELF_SHA256
    gob = open(args.gob, "rb").read()
    image, parsed = authored(gob)
    count = execute(args.executable, image, parsed, args.seed)
    print("PASS seed %d: 21 entries, 9 dialog nodes, 3 cutscenes, "
          "%d original script-host branch probes; built-in effects stubbed" %
          (args.seed, count))


if __name__ == "__main__":
    main()
