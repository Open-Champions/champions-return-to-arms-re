#!/usr/bin/env python3
"""Mission 1 level flow (strife, drundar, drunarm, drunare) in the original script host.

Runs the shipped level scripts in tools/ee_emu.py through the original loader
(0x13e8f8), native binder (0x141310), `script_runByName` (0x1ed694),
`script_runDeferred` (0x1ed5a0) and `script_runPostAction` (0x1edac0). Campaign
natives (quest variables, deferred calls, post actions, `newWorld`, scaled time,
pause, mission grant, item-count wrappers, quest removal) keep their original
bodies; each gets a recording hook at its first instruction. World, cutscene,
sound, HUD, dialog and monster natives are stubbed (STUB_NAMES) and record their
decoded arguments. Text-key arguments are recorded as "<text>" only. One run is
one sequence of frames; a frame is one `script_runDeferred` call. Object-record
links, cutscene files and the original factory/marker constructors are checked
against the private inputs and tools/ref_mission1_levels.py. Nothing here is a
played fight, a rendered cutscene or a loaded level.

The host design follows t3/research-mission-unlocks 2ab82b2
tools/difftest_mission1_complete.py (stub set, recording hooks, campaign reset).

Preload the stdlib dis module first (tools/dis.py shadows it):

  PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["difftest_mission1_levels.py","--elf","local/SLUS_209.73","--disc","local/disc","--seed","20973"]; sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_mission1_levels.py", run_name="__main__")'
"""
import argparse
from collections import Counter
import hashlib
import math
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError
from dump_tables import parse_objects
from gob import gob_entries, lmp_entries
import ref_mission1_levels as R
import ref_strife_drundar as RS
import scr

ELF_SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"

# Campaign state (same addresses as difftest_mission1_complete.py).
PLAYERS, REC, MISSION = 0x4D8AF0, 0x4C30, 0x4BBF
QUESTS, QUEST_COUNT, P_OBJECT = 0x41D0, 0x43D0, 0x43D8
EVIL, DECISION = 0x4C1A, 0x4C1B
SEED, NUM_PLAYERS, DIFFICULTY = 0x404464, 0x4D8AE0, 0x4F719C
PAUSED, CUTSCENE, JUMPGATE, NETWORK = 0x41B4F4, 0x44FCD0, 0x500AE8, 0x402791
MACHINE, DEFER_NAMES = 0x86B270, 0x86B278
DEFER_COUNT, DEFER_QUEUED, DEFER_FLIP = 0x86DA78, 0x86DA7C, 0x4F8690
QUEST_VARS, POST_ACTION, SELECTED = 0x86DA80, 0x86FA80, 0x4039F8
PENDING, ORIENT = 0x41B6D0, 0x41B720
NATIVE_TABLE = 0x403370
SCR_LOAD, SCR_REGISTER = 0x13E8F8, 0x141310
RUN_BY_NAME, RUN_DEFERRED, RUN_POST = 0x1ED694, 0x1ED5A0, 0x1EDAC0
VARS_SET = 0x1ED854
GET_HUB = 0x1EC300
COUNT_ITEM, FIND_ITEM, REMOVE_ITEM = 0x1C5880, 0x1C5A70, 0x1C1CB0
O_FLAGS, OF_CREATURE = 0x0C, 0x20
# Object factory and start marker.
FACTORY, POOL_NEW = 0x159C94, 0x14FDB8
PLAYER1_CTOR, FREE_SPOT = 0x158928, 0x14ACF8
G_PREV_LEVEL, G_GATE_TRAVEL, G_ENTRANCE, G_START_RANK = 0x41B7C2, 0x41B51E, 0x4F8468, 0x4F7108
G_WORLD = 0x44FDC8
CREATURE_ON_DEATH, OBJECT_CTOR, OBJ_GET_PROP_STR = 0x10BEB8, 0x14CB10, 0x14F4C0
LOOT_SPAWN_NAMED = 0x100BA0
# cut_setup 0x19a6cc actor search: box half-extents (lui 0x4370 / 0x47c3_5000 at
# 0x19b098-0x19b0ac), result capacity 0x40 (0x19b0f8), nearest-candidate start 600.0
# (lui 0x4416 at 0x19b0fc).
BIND_BOX = (240.0, 240.0, 100000.0)
BIND_FIRST = 600.0
# A second matching record is excluded when it lies outside the box grown by this much
# on x and y, i.e. for any object radius below it (world_collectObjectsInBox 0x14a928
# tests x/y against the radius; the default radius is 24).
BIND_MARGIN = 240.0

STUB_NAMES = {
    "hideMonster", "showMonster", "killMonster", "deleteMonster", "setMonsterVal",
    "autoPropSetState", "setCFlag", "setSaveInhibit", "cutScene", "soundSequence",
    "setInfo", "reapEnemies", "addHelpMessage", "playGotItemSound", "givePlayerItem",
    "startDialog", "showBust", "addParticleOnObject", "getHitPoints", "addQuest",
    "trigger", "preloadResource", "changeSwoop", "activateStore", "showCompass",
    "setParticle",
}
# Argument kinds per native: s identifier string, t text key (never recorded),
# i integer. Natives not listed record their integer cells.
SIG = {
    "getv": "s", "setv": "si", "hideMonster": "s", "showMonster": "s",
    "killMonster": "s", "deleteMonster": "s", "setMonsterVal": "sii",
    "setCFlag": "sii", "autoPropSetState": "si", "setSaveInhibit": "i",
    "cutScene": "s", "postAction": "s", "addDeferedCall": "s", "callScript": "s",
    "removeQuest": "t", "addQuest": "tt", "setInfo": "t", "addHelpMessage": "tt",
    "soundSequence": "ss", "playerHasItem": "s", "onePlayerHasItem": "is",
    "removePlayerItem": "is", "grantMission": "i", "newWorld": "s",
    "getHitPoints": "s", "getScaledTime": "i", "gamePaused": "", "demoRunning": "",
    "reapEnemies": "", "playGotItemSound": "", "startDialog": "sii",
    "showBust": "stii", "trigger": "si", "preloadResource": "s",
    "setParticle": "", "sin1000": "", "cos1000": "", "addParticleOnObject": "",
}


def level_lump(disc, level):
    gob = open(os.path.join(disc, level.upper() + ".GOB"), "rb").read()
    found = [(o, s) for name, o, s in gob_entries(gob) if name.lower() == level + ".lmp"]
    assert len(found) == 1, level
    lump = gob[found[0][0]:found[0][0] + found[0][1]]
    return {name.lower(): lump[o:o + s] for name, o, s in lmp_entries(lump)}


class Level:
    """Private inputs of one level, held in memory only."""

    def __init__(self, disc, level):
        self.name = level
        self.files = level_lump(disc, level)
        self.image = self.files["script.scr"]
        self.rows = parse_objects(self.files["objects.ob"], level)
        parsed = scr.parse(self.image)
        self.publics = [name for _off, name in parsed["internals"]]
        self.public_at = {name: off for off, name in parsed["internals"]}
        self.natives = [name for _off, name in parsed["externals"]]
        self.pool = dict(scr.strings(self.image, *parsed["strings"]))
        self.code = parsed["code"]

    def props(self, row):
        out = []
        for item in row["properties"].split(";"):
            if "=" in item:
                key, value = item.split("=", 1)
                out.append((key, value))
        return out

    def sites(self):
        """Every SYSREQ.C with its native and constant pushed cells."""
        start, end = self.code
        words = struct.unpack_from("<%dI" % ((end - start) // 4), self.image, start)
        out = []
        for i, word in enumerate(words):
            if word != 0x7B or i + 1 >= len(words) or i < 2:
                continue
            if words[i + 1] >= len(self.natives) or words[i - 2] != 0x27:
                continue
            argc = words[i - 1] // 4
            if words[i - 1] % 4 or argc > 8:
                continue
            cells = []
            for k in range(argc):
                at = i - 2 - 2 * (k + 1)
                cells.append(words[at + 1] if at >= 0 and words[at] == 0x27 else None)
            out.append((i * 4, self.natives[words[i + 1]], cells))
        return out

    def entry_of(self, offset):
        best = None
        for name, at in self.public_at.items():
            if at <= offset and (best is None or at > self.public_at[best]):
                best = name
        return best


class Host:
    def __init__(self, elf, seed):
        self.ee = EE(elf)
        self.ee.record_writes = False
        self.ee.record_calls = False
        self.seed = seed
        self.counts = [0, 0, 0, 0]
        self.hp = {}
        self.log = []          # (native, decoded args) in order, original and stubbed
        self.stubs = []
        self.scripts = []
        self.level = None
        self.base = self.ee.alloc(0x80000, align=16)
        self.names = self.ee.alloc(0x1000, align=16)
        self.player_body = self.ee.alloc(0x40, align=16)
        self._bind()
        self.reset()

    def _bind(self):
        ee, mem = self.ee, self.ee.mem
        handlers = {}
        for index in range(191):
            name_at = mem.u32(NATIVE_TABLE + 8 * index)
            handler = mem.u32(NATIVE_TABLE + 8 * index + 4)
            if name_at == 0 or handler == 0:
                break
            handlers[mem.cstr(name_at)] = handler
        self.handlers = handlers
        for name in STUB_NAMES:
            ee.stub(handlers[name], function=self._stub(name), name=name)
        by_addr = {}
        for name, handler in handlers.items():
            if name not in STUB_NAMES:
                by_addr.setdefault(handler, []).append(name)
        for handler, names in by_addr.items():
            ee.hook(handler, self._seen(names))
        ee.hook(RUN_BY_NAME, lambda e: self.scripts.append(e.mem.cstr(e.r[4] & 0xFFFFFFFF, 80)))
        ee.stub(COUNT_ITEM, function=lambda e: self.counts[e.r[5] & 3] if (e.r[5] & 0xFFFFFFFF) < 4 else 0,
                name="inventory_countItemByName")
        ee.stub(FIND_ITEM, function=self._find_item, name="inventory_findItemBySubstring")
        ee.stub(REMOVE_ITEM, function=lambda e: 0, name="inventory_removeItem")

    def _find_item(self, ee):
        ee.mem.w32(ee.r[6] & 0xFFFFFFFF, 0)
        ee.mem.w32(ee.r[7] & 0xFFFFFFFF, 0)
        return 0

    def _args(self, name, ee):
        params = ee.r[5] & 0xFFFFFFFF
        count = ee.mem.u32(params) // 4
        cells = [ee.mem.s32(params + 4 + 4 * k) for k in range(min(count, 8))]
        kinds = SIG.get(name, "i" * count)
        if name in SIG and len(SIG[name]) < len(cells):
            cells = cells[:len(SIG[name])]
        out = []
        for k, cell in enumerate(cells):
            kind = kinds[k] if k < len(kinds) else "i"
            if kind == "t":
                out.append("<text>")
            elif kind == "s":
                out.append(self.level.pool.get(cell & 0xFFFFFFFF, "?%x" % (cell & 0xFFFFFFFF)))
            else:
                out.append(cell)
        return tuple(out)

    def _stub(self, name):
        def run(ee):
            args = self._args(name, ee)
            self.log.append((name,) + args)
            self.stubs.append(name)
            if name == "getHitPoints":
                return self.hp.get(args[0].lower(), 0) & 0xFFFFFFFF
            return 0
        return run

    def _seen(self, names):
        def run(ee):
            # newWorld/newWorldAlways share one handler; pick the imported one.
            name = next((n for n in names if n in self.level.natives), names[0])
            self.log.append((name,) + self._args(name, ee))
        return run

    def reset(self):
        mem = self.ee.mem
        mem.w32(SEED, self.seed)
        mem.w32(NUM_PLAYERS, 1)
        mem.w32(DIFFICULTY, 0)
        mem.w32(PAUSED, 0)
        mem.w8(CUTSCENE, 0)
        mem.w32(JUMPGATE, 0)
        mem.w8(NETWORK, 0)
        mem.w32(SELECTED, 0)
        mem.w32(DEFER_COUNT, 0)
        mem.w32(DEFER_QUEUED, 0)
        mem.w32(DEFER_FLIP, 0)
        mem.write(POST_ACTION, b"\0" * 16)
        mem.write(PENDING, b"\0" * 80)
        mem.w8(ORIENT, 0)
        mem.write(QUEST_VARS, b"\0" * 0x800)
        mem.w32(self.player_body + O_FLAGS, OF_CREATURE)
        for slot in range(4):
            rec = PLAYERS + slot * REC
            mem.write(rec + MISSION, b"\0" * (5 * 13))
            mem.w32(rec + QUEST_COUNT, 0)
            mem.write(rec + QUESTS, b"\0" * (8 * 0x40))
            mem.w32(rec + P_OBJECT, self.player_body if slot == 0 else 0)
            mem.w8(rec + EVIL, 0)
            mem.w8(rec + DECISION, 0)
        mem.w8(PLAYERS + MISSION + 1, 1)          # mission 1 available, not complete
        self.counts[:] = (0, 0, 0, 0)
        self.hp.clear()
        self.log.clear()
        self.stubs.clear()
        self.scripts.clear()

    def place(self, level):
        self.level = level
        ee = self.ee
        ee.mem.write(self.base, level.image + bytes(0x200))
        ee.mem.w32(MACHINE, self.base)
        error = ee.call(SCR_LOAD, self.base, self.base + 0x60, max_steps=2000000)
        bound = ee.call(SCR_REGISTER, self.base, NATIVE_TABLE, 0xFFFFFFFF, max_steps=2000000)
        assert error == 0 and bound == 0, (level.name, error, bound)
        self.reset()

    def run(self, name):
        self.ee.mem.write(self.names, name.encode("latin1") + b"\0")
        try:
            return self.ee.call(RUN_BY_NAME, self.names, max_steps=4000000) & 0xFFFFFFFF
        except EmuError as exc:
            raise AssertionError("%s %s: %s" % (self.level.name, name, exc))

    def frame(self):
        try:
            self.ee.call(RUN_DEFERRED, max_steps=4000000)
        except EmuError as exc:
            raise AssertionError("%s deferred: %s" % (self.level.name, exc))

    def post(self):
        try:
            self.ee.call(RUN_POST, max_steps=4000000)
        except EmuError as exc:
            raise AssertionError("%s post: %s" % (self.level.name, exc))

    def mark(self):
        return len(self.log), len(self.scripts)

    def since(self, mark):
        return self.log[mark[0]:], self.scripts[mark[1]:]

    def set_var(self, name, value):
        self.ee.mem.write(self.names, name.encode("latin1") + b"\0")
        self.ee.call(VARS_SET, self.names, value, max_steps=100000)

    def vars(self):
        mem, out, at = self.ee.mem, {}, QUEST_VARS
        while mem.u8(at) != 0 and at < QUEST_VARS + 0x800:
            name = mem.cstr(at)
            at += len(name) + 1
            out[name] = mem.s8(at)
            at += 1
        return out

    def var(self, name):
        return self.vars().get(name.lower(), 0)

    def post_name(self):
        return self.ee.mem.cstr(POST_ACTION, 80)

    def pending(self):
        return self.ee.mem.cstr(PENDING, 80)

    def clear_pending(self):
        self.ee.mem.write(PENDING, b"\0" * 80)

    def _names(self, count_addr, half):
        mem = self.ee.mem
        return [mem.cstr(DEFER_NAMES + (half * 64 + k) * 0x50) for k in range(mem.u32(count_addr))]

    def queued(self):
        """Every name that will still run: front half (this frame's list) and back half."""
        flip = self.ee.mem.u32(DEFER_FLIP) & 1
        return sorted(self._names(DEFER_COUNT, flip) + self._names(DEFER_QUEUED, flip ^ 1))

    def data_base(self):
        dat = self.ee.mem.s32(self.base + 0x70)
        assert 0 < dat < 0x200000, dat
        return self.base + 0x60 + dat

    def global_cell(self, cell):
        return self.ee.mem.s32(self.data_base() + cell)

    def set_global(self, cell, value):
        self.ee.mem.w32(self.data_base() + cell, value & 0xFFFFFFFF)

    def mission1(self):
        return self.ee.mem.u8(PLAYERS + MISSION + 1)

    def hub_name(self, evil, decision, complete):
        mem = self.ee.mem
        mem.w8(PLAYERS + EVIL, evil)
        mem.w8(PLAYERS + DECISION, decision)
        mem.w8(PLAYERS + MISSION + 1, 3 if complete else 1)
        return mem.cstr(self.ee.call(GET_HUB, max_steps=100000) & 0xFFFFFFFF, 16)


def signed(value):
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value >= 1 << 31 else value


def calls(log, natives=None):
    """The recorded list without the always-present interpreter bookkeeping."""
    return [entry for entry in log if natives is None or entry[0] in natives]


def expect(actual, wanted, what):
    if list(actual) != list(wanted):
        raise AssertionError("%s:\n  got  %s\n  want %s" % (what, list(actual), list(wanted)))


# ------------------------------------------------------------------ scenarios
CELLS = {
    "drunarm": (0x0, 0x4, 0x8, 0xc, 0x10),
    "drunare": (0x0, 0x4),
    "strife": (0x140, 0x144, 0x148, 0x14c, 0x150, 0x154, 0x158, 0x15c),
    "drundar": (0x0, 0x28, 0x2c, 0x30) + tuple(range(0x8, 0x28, 4)),
}
WATCH = ("addDeferedCall", "cutScene", "newWorld", "grantMission", "postAction", "callScript", "killMonster",
         "showMonster", "setCFlag", "removeQuest", "addQuest", "trigger", "setSaveInhibit",
         "autoPropSetState", "startDialog")


class Pair:
    """One scenario run on the original host and on the model, compared after every step."""

    def __init__(self, host, level, plant=None):
        self.host, self.level = host, level
        host.place(level)
        self.model = R.Model(level.name)
        self.frame_no = 0
        self.steps = 0
        self.events = []              # (frame, native, args) for WATCH natives, from the host
        for cell, value in (plant or {}).items():
            host.set_global(cell, value)
            self.model.g[cell] = value
        for cell in CELLS[level.name]:
            self.model.g.setdefault(cell, host.global_cell(cell))

    def _compare(self, what, mark, result=None, want=None):
        host, model = self.host, self.model
        log, scripts = host.since(mark[0])
        mlog, mscripts = model.log[mark[1]:], model.scripts[mark[2]:]
        expect(log, mlog, "%s %s log" % (self.level.name, what))
        expect(scripts, mscripts, "%s %s entries" % (self.level.name, what))
        if want is not None:
            assert result == want, (self.level.name, what, result, want)
        state = (host.vars(), host.post_name(), host.pending(), host.queued(), host.mission1() & 3,
                 {c: host.global_cell(c) for c in CELLS[self.level.name]})
        mstate = (model.vars, model.post, model.pending, model.queued(), model.mission1 & 3,
                  {c: signed(model.gv(c)) for c in CELLS[self.level.name]})
        if state != mstate:
            raise AssertionError("%s %s state:\n  got  %s\n  want %s" % (self.level.name, what, state, mstate))
        for entry in log:
            if entry[0] in WATCH:
                self.events.append((self.frame_no,) + entry)
        self.steps += 1

    def _mark(self):
        return (self.host.mark(), len(self.model.log), len(self.model.scripts))

    def run(self, entry, want=None):
        mark = self._mark()
        result = self.host.run(entry)
        mres = self.model.run(entry)
        assert result == mres, (self.level.name, entry, result, mres)
        self._compare("run " + entry, mark, result, want)
        return result

    def frames(self, count):
        for _ in range(count):
            mark = self._mark()
            self.frame_no += 1
            self.host.frame()
            self.model.frame()
            self._compare("frame %d" % self.frame_no, mark)

    def post(self):
        mark = self._mark()
        self.host.post()
        self.model.run_post()
        self._compare("post", mark)

    def var(self, name, value):
        self.host.set_var(name, value)
        self.model.vars[name.lower()] = value

    def hp(self, name, value):
        self.host.hp[name] = value
        self.model.hp[name] = value

    def count(self, slot, value):
        self.host.counts[slot] = value
        self.model.counts[slot] = value

    def pause(self, on):
        self.host.ee.mem.w8(CUTSCENE, 1 if on else 0)
        self.model.paused = on

    def clear_pending(self):
        self.host.clear_pending()
        self.model.pending = ""

    def first(self, native, *args):
        for event in self.events:
            if event[1] == native and event[2:2 + len(args)] == args:
                return event[0]
        raise AssertionError("%s: no %s%s" % (self.level.name, native, args))


def scenario_drunarm(host, levels):
    """Good arena: load, Rallos trigger, fight, shard, grant, Rallos outro, exit."""
    lv = levels["drunarm"]
    out = {}
    marks = {c: 0x5A + c for c in CELLS["drunarm"]}
    p = Pair(host, lv)                       # globals as scr_load leaves them (all 0)
    assert all(host.global_cell(c) == 0 for c in CELLS["drunarm"])
    p.run("preStart", 0xFFFFFFFF)            # the loader's name; this level spells it prestart
    p.run("start")
    p.frames(20)
    p.run("if6896", 1)                       # gate usable before the trigger
    p.run("callScricb6b")                    # portal-message trigger: no message yet
    p.run("callScric1d7")                    # walk-in trigger
    p.pause(1)
    p.frames(40)                             # synthetic cutscene length
    p.pause(0)
    p.post()                                 # cutscene end: setFlag
    p.run("if6896", 0)
    p.run("callScricb6b")                    # now shows the message
    p.run("callScric1d7")                    # re-entry: setFlag only
    p.hp("rallos", 500)
    p.frames(30)
    p.hp("rallos", 0)                        # Rallos dies (the drop is his own death path)
    kill = p.frame_no
    p.frames(10)
    p.count(0, 1)                            # shard picked up
    pickup = p.frame_no
    p.frames(60)
    out["grant_after_pickup"] = p.first("grantMission", 1) - pickup
    p.frames(300)
    out["outro_after_kill"] = p.first("cutScene", "rallosruns") - kill
    out["outro_after_grant"] = p.first("cutScene", "rallosruns") - p.first("grantMission", 1)
    assert host.post_name() == "removeRallos"  # replaced the shard grant's endmission
    p.pause(1)
    p.frames(20)
    p.pause(0)
    p.post()
    p.run("if6896", 1)
    p.run("callScricb6b")
    p.run("newWorld1c57")
    assert host.pending() == "strife"
    out["frames"], out["steps"] = p.frame_no, p.steps
    # Same fight, endmission run (notice box) before the outro replaces the post action.
    q = Pair(host, lv, {0x4: marks[0x4], 0xc: marks[0xc], 0x10: marks[0x10]})
    q.run("start")
    q.run("callScric1d7")
    q.post()
    q.hp("rallos", 0)
    q.frames(5)
    q.count(0, 2)
    q.frames(30)
    q.post()                                 # endmission
    q.frames(300)
    q.post()                                 # removeRallos
    assert q.first("grantMission", 1) > 0
    out["steps"] += q.steps
    # The other order inside the grant frame: shardCheckLoop and rallosHPcheck both
    # queued before the first frame, death and pickup in the same step.
    x = Pair(host, lv)
    x.run("start")
    x.run("callScric1d7")
    x.post()
    x.frames(1)
    x.hp("rallos", 0)
    x.count(0, 1)
    x.frames(330)
    out["outro_after_grant_same_step"] = (x.first("cutScene", "rallosruns")
                                          - x.first("grantMission", 1))
    out["steps"] += x.steps
    # Control: no shard until after the outro, so nothing resets global 0x10.
    w = Pair(host, lv)
    w.run("start")
    w.run("callScric1d7")
    w.post()
    w.hp("rallos", 0)
    kill = w.frame_no
    w.frames(290)
    out["outro_after_kill_no_shard"] = w.first("cutScene", "rallosruns") - kill
    out["outro_after_queue"] = (w.first("cutScene", "rallosruns")
                                - w.first("addDeferedCall", "endDelay"))
    w.count(0, 1)
    w.frames(30)
    w.post()
    out["steps"] += w.steps
    # The prestart body, if it ran, and every start state.
    r = Pair(host, lv, marks)
    r.run("prestart")
    out["steps"] += r.steps
    for state in range(8):
        s = Pair(host, lv, marks)
        for bit, name in enumerate(("war_triggeredonce", "war_foundShard", "war_killedRallos")):
            if state >> bit & 1:
                s.var(name, 1)
        s.count(0, state & 1)
        s.run("start")
        s.frames(3)
        out["steps"] += s.steps
    return out


def scenario_drunare(host, levels):
    """Evil arena: load, knights, Cazic, avatar death, grant, hub2; exits; reload."""
    lv = levels["drunare"]
    out = {}
    marks = {c: 0x5A + c for c in CELLS["drunare"]}
    p = Pair(host, lv, marks)
    p.run("start")
    p.run("return9d74", 0)                   # exit push-trigger key: locked
    p.run("callScri8654")                    # arena trigger: knights cutscene
    p.pause(1)
    p.frames(30)
    p.pause(0)
    p.post()                                 # nosave
    p.run("callScri8654")                    # re-entry: setFlag
    p.frames(20)
    for entry in ("setv5138", "setv4d6b", "setvcccf"):
        p.run(entry)
        p.frames(15)
    p.run("setv772a")                        # fourth knight
    knights = p.frame_no
    p.frames(320)
    out["cazic_after_fourth_death"] = p.first("cutScene", "cazic") - knights
    p.pause(1)
    p.frames(30)
    p.pause(0)
    p.frames(10)
    p.run("callScria381")                    # avatar death script
    death = p.frame_no
    p.frames(900)
    out["end_after_death"] = p.first("cutScene", "bossdefeated") - death
    p.post()                                 # cutscene end: levelChange
    assert host.pending() == "hub2" and host.mission1() & 2
    p.clear_pending()
    p.run("return9d74", 1)
    p.run("newWorldbcf6")
    assert host.pending() == "drundar"
    out["frames"], out["steps"] = p.frame_no, p.steps
    for killed in (0, 1):
        s = Pair(host, lv, marks)
        if killed:
            s.var("killedAv", 1)
        s.run("start")
        s.run("return9d74", killed)
        out["steps"] += s.steps
    return out


def scenario_strife(host, levels):
    """Good story level: load with init scripts, three stages, bridges, exits, reload."""
    lv = levels["strife"]
    out = {}
    links = R.LINKS["strife"]
    marks = {c: 0x5A + c for c in CELLS["strife"]}
    p = Pair(host, lv, marks)               # sentinels: every zeroing store is visible
    p.run("preStart")
    for _ in range(links[("Orc2Archer", "initscript", "callScri52e")]
                   + links[("Orc2Soldier", "initscript", "callScri52e")]):
        p.run("callScri52e")
    for _ in range(links[("Orc2Shaman", "initscript", "callScri9f82")]):
        p.run("callScri9f82")
    p.run("start")
    assert host.global_cell(0x144) == 13 and host.global_cell(0x148) == 2
    for entry, want in (("returne210", 1), ("return1e8e", 1), ("returnadae", 1),
                        ("returnc3ef", 1), ("return8821", 1), ("return523c", 1)):
        p.run(entry, want)
    p.run("if9d85")
    p.run("if9d85")
    p.run("startDia8851")
    p.run("iff29", 0)
    p.run("if70a4", 1)
    p.run("setv176d")                        # scout 1 dialog action
    p.run("returne210", 0)
    p.frames(5)
    for k in range(13):
        p.run("callScria77e")
        p.frames(2)
    stage1 = p.frame_no
    p.frames(110)
    out["step1_after_queue"] = p.first("cutScene", "step1com") - p.first("addDeferedCall", "step1delay")
    p.pause(1)
    p.frames(20)
    p.pause(0)
    p.post()                                 # hideElf1
    p.run("startDia30cc")
    p.run("if3e90", 1)
    p.run("setv23a8")                        # bridge1, shaman counter
    p.frames(5)
    p.run("callScri4980")
    p.frames(3)
    p.run("callScri4980")
    stage2 = p.frame_no
    p.frames(110)
    out["step2_after_queue"] = p.first("cutScene", "step2complete") - p.first("addDeferedCall", "step2delay")
    p.pause(1)
    p.frames(20)
    p.pause(0)
    p.post()                                 # hideElf2
    p.run("startDiad2e3")
    p.run("if40b3", 1)
    p.run("setv8921")                        # bridge2, catapult counter
    p.frames(5)
    p.run("callScri8d4a")
    p.frames(3)
    p.run("callScri8d4a")
    stage3 = p.frame_no
    p.frames(110)
    out["step3_after_queue"] = p.first("cutScene", "step3complete") - p.first("addDeferedCall", "step3delay")
    p.pause(1)
    p.frames(20)
    p.pause(0)
    p.post()                                 # hide3
    p.run("return8821", 0)                   # bombs stop
    p.run("startDiab722")
    p.run("setv70e6")                        # bridge3
    p.run("callScri5a82")                    # exit push trigger
    assert host.pending() == "drunarm"
    p.clear_pending()
    p.run("newWorld5d32")
    assert host.pending() == "blood1"
    out["frames"], out["steps"] = p.frame_no, p.steps
    # Reload after all three stages.
    s = Pair(host, lv, marks)
    for name, value in (("sfe_step1Complete", 1), ("sfe_step2Complete", 1),
                        ("sfe_step3Complete", 1), ("sfe_step3counter", 2),
                        ("sfe_talkedtofirstscout", 1)):
        s.var(name, value)
    s.run("preStart")
    s.run("start")
    s.run("return8821", 0)
    s.frames(3)
    out["steps"] += s.steps
    return out


def scenario_drundar(host, levels):
    """Evil story level: arena message, eight switches, doors cutscene, exits, reload."""
    lv = levels["drundar"]
    out = {}
    marks = {c: 0x5A + c for c in CELLS["drundar"]}
    p = Pair(host, lv, marks)               # sentinels: every zeroing store is visible
    p.run("preStart")
    p.run("start")
    p.run("return56e0", 0)
    p.run("callScri28d3")
    p.run("callScri28d3")
    p.frames(3)
    order = (3, 1, 7, 5, 2, 8, 4, 6)
    for k in order:
        action, key, _ = R.Model.PILLAR[k - 1]
        p.run(key, 1)
        p.run(action)
        p.run(key, 0)
        p.frames(2)
    done = p.frame_no
    p.frames(110)
    out["doors_after_queue"] = p.first("cutScene", "doors") - p.first("addDeferedCall", "doorsdelay")
    p.pause(1)
    p.frames(5)                              # pillar loops stop requeueing while paused
    p.pause(0)
    p.frames(3)
    p.run("return56e0", 1)
    p.run("callScri5a82")
    assert host.pending() == "drunare"
    p.clear_pending()
    p.run("newWorld5d32")
    assert host.pending() == "blood1"
    out["frames"], out["steps"] = p.frame_no, p.steps
    s = Pair(host, lv, marks)
    s.var("drun_sawdoors", 1)
    s.var("drun_arenaMess", 1)
    for k in range(1, 9):
        s.var("pillar%don" % k, 1)
    s.run("preStart")
    s.run("start")
    s.run("return56e0", 1)
    s.frames(3)
    out["steps"] += s.steps
    return out


# ------------------------------------------------------------------ static checks
class FactoryFollow:
    def __contains__(self, addr):
        return addr in (FACTORY, 0x159C20, 0x14F730, 0x14F850) or 0x3A5000 <= addr < 0x3C0000


def put(ee, text):
    raw = text.encode("latin1") + b"\0"
    ptr = ee.alloc(len(raw))
    ee.mem.write(ptr, raw)
    return ptr


def props_ptr(ee, row):
    strings = [put(ee, x) for x in row["properties"].split(";") if x]
    table = ee.alloc((len(strings) + 1) * 4)
    for k, ptr in enumerate(strings):
        ee.mem.w32(table + 4 * k, ptr)
    return table


def census(elf, levels, seed):
    """Arena object counts, and the original factory's choice for every record."""
    made_total = 0
    for name in ("drunarm", "drunare"):
        rows = levels[name].rows
        assert Counter(row["class"] for row in rows) == Counter(R.COUNTS[name]), name
        ordered = list(rows)
        random.Random(seed).shuffle(ordered)
        made = 0
        for row in ordered:
            ee = EE(elf)
            ee.follow = FactoryFollow()
            block, world = ee.alloc(0x1000), ee.alloc(0x100)
            ee.mem.w32(G_WORLD, world)
            ee.stub(POOL_NEW, ret=block)
            cls = put(ee, row["class"])
            props, pos = props_ptr(ee, row), ee.alloc(12)
            ee.reset_log()
            result = ee.call(FACTORY, cls, pos, row["angle"], props, max_steps=500000)
            alloc = [c.args[0] for c in ee.calls if c.target == POOL_NEW]
            ctors = [c.target for c in ee.calls if c.target not in (POOL_NEW, 0x159C20, 0x14F730, 0x14F850)
                     and not 0x3A5000 <= c.target < 0x3C0000]
            key = row["class"].lower()
            if key in R.NO_OBJECT and not (key == "crate" and row["properties"]):
                assert result == 0 and not alloc, (name, row["index"])
                continue
            assert key in R.FACTORY, key
            assert alloc == [R.FACTORY[key][0]] and ctors[-1] == R.FACTORY[key][1], (name, key)
            assert result == block
            made += 1
        assert (len(rows), made) == R.ARENA_TOTALS[name], (name, len(rows), made)
        made_total += made
    return made_total


def links(levels):
    total = 0
    for name, lv in levels.items():
        found = Counter()
        for row in lv.rows:
            for key, value in lv.props(row):
                if value in lv.publics:
                    found[(row["class"], key, value)] += 1
        assert found == Counter(R.LINKS[name]), name
        called = set()
        for _off, native, cells in lv.sites():
            if native in ("callScript", "addDeferedCall", "postAction") and cells and cells[0] is not None:
                called.add(lv.pool.get(cells[0]))
        linked = {key[2] for key in found}
        dialog = R.DIALOG_ENTRIES.get(name, {})
        for resource, entries in dialog.items():
            data = lv.files[resource].lower()
            for entry in entries:
                assert entry.lower().encode() in data, (name, resource, entry)
        dialog_entries = {e for entries in dialog.values() for e in entries}
        loose = set(lv.publics) - linked - called - dialog_entries - {"dummyEntryPoint"}
        assert loose == set(R.LOAD_ENTRIES[name]), (name, sorted(loose))
        total += sum(found.values())
    return total


CTORS = dict(RS.FACTORY)
CTORS.update(R.FACTORY)


def makes_object(row):
    """The census rule: the factory returns 0 for these (asserted in census())."""
    key = row["class"].lower()
    if key in R.NO_OBJECT and not (key == "crate" and row["properties"]):
        return False
    assert key in CTORS, key
    return True


def type_names(elf, levels):
    """C++ type name of every constructor the four levels' records select.

    The factory runs with only its own code, the selected constructor and the
    GameObject constructor 0x14cb10; the constructor stores its virtual table at +0x48
    (base constructors are stubbed, so a later fault on missing level data is ignored).
    Entry 0 of the table is the type-info function; its result's first word is the
    mangled name, whose leading digits cut_setup skips (0x19b1e0-0x19b1f8)."""
    out = {}
    for name in sorted(levels):
        for row in levels[name].rows:
            if not makes_object(row):
                continue
            ctor = CTORS[row["class"].lower()][1]
            if ctor in out:
                continue
            ee = EE(elf)
            ee.syscall_handler = lambda e: e.r.__setitem__(2, 0)

            class Follow:
                def __contains__(self, addr, ctor=ctor):
                    return addr in FactoryFollow() or addr in (ctor, OBJECT_CTOR)
            ee.follow = Follow()
            block = ee.alloc(0x1000)
            ee.mem.w32(G_WORLD, ee.alloc(0x100))
            ee.stub(POOL_NEW, ret=block)
            try:
                ee.call(FACTORY, put(ee, row["class"]), ee.alloc(12), row["angle"], props_ptr(ee, row),
                        max_steps=3000000)
            except EmuError:
                pass
            table = ee.mem.u32(block + 0x48)
            if not 0x500000 <= table < 0x520000:
                continue                     # faulted before the store; another record of this ctor
            info = ee.call(ee.mem.u32(table + 4), max_steps=200000) & 0xFFFFFFFF
            out[ctor] = ee.mem.cstr(ee.mem.u32(info), 60).lstrip("0123456789")
    for name, lv in levels.items():
        for row in lv.rows:
            if makes_object(row):
                assert CTORS[row["class"].lower()][1] in out, (name, row["class"])
    return out


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def bind_actor(lv, types, cls, at, taken):
    """cut_setup's search for one placed actor (0x19b098-0x19b324), over the records.

    Candidates are objects in the box at +-BIND_BOX whose class string (+0x34, the
    factory's class name) or C++ type name equals the actor's class, skipping objects
    already bound (flag 0x80000). The pick is the nearest in 2-D below 600; once a
    class-string match is held, type-only matches are skipped. Returns the one record
    and asserts it is the only candidate even with a radius up to BIND_MARGIN."""
    lo = [f32(at[i] - BIND_BOX[i]) for i in range(3)]
    hi = [f32(at[i] + BIND_BOX[i]) for i in range(3)]
    inner, outer = [], []
    for row in lv.rows:
        if not makes_object(row) or id(row) in taken:
            continue
        by_name = row["class"] == cls
        by_type = types[CTORS[row["class"].lower()][1]] == cls
        assert by_name or not by_type, (lv.name, cls, row["class"])   # no type-only match here
        if not by_name:
            continue
        x, y, z = float(row["x"]), float(row["y"]), float(row["height"])
        assert lo[2] + 1000 < z < hi[2] - 1000, (lv.name, cls)
        if lo[0] <= x <= hi[0] and lo[1] <= y <= hi[1]:
            inner.append(row)
        if lo[0] - BIND_MARGIN <= x <= hi[0] + BIND_MARGIN and lo[1] - BIND_MARGIN <= y <= hi[1] + BIND_MARGIN:
            outer.append(row)
    assert len(inner) == 1 and outer == inner, (lv.name, cls, len(inner), len(outer))
    row = inner[0]
    assert math.hypot(float(row["x"]) - at[0], float(row["y"]) - at[1]) < BIND_FIRST, (lv.name, cls)
    return row


def cutscene_files(levels, types):
    """Requested cutscenes: call site, file in the level lump, header, actors, binding."""
    requested = {}
    for name, lv in levels.items():
        for off, native, cells in lv.sites():
            if native == "cutScene":
                requested.setdefault(name, []).append((lv.entry_of(off), off, lv.pool[cells[0]]))
    want = {}
    for row in R.CUTSCENES:
        want.setdefault(row[0], []).append(row[1:4])
    assert {k: sorted(v) for k, v in requested.items()} == {k: sorted(v) for k, v in want.items()}
    bindings = 0
    for level, entry, off, cut, flags, keys, actors, cast, shows in R.CUTSCENES:
        lv = levels[level]
        data = lv.files[cut + ".cut"]
        got_flags, key_off, key_count, actor_off, actor_count = struct.unpack_from("<5I", data, 0)
        assert (got_flags, key_count, actor_count) == (flags, keys, actors), (level, cut)
        bound, taken = [], set()
        for k in range(actor_count):
            rec = data[actor_off + 0x2C * k: actor_off + 0x2C * (k + 1)]
            cls = rec[8:0x1C].split(b"\0")[0].decode("latin1")
            at = struct.unpack_from("<3f", rec, 0x1C)
            if rec[0x2B]:
                bound.append((cls, "create"))
                continue
            row = bind_actor(lv, types, cls, at, taken)
            taken.add(id(row))
            bindings += 1
            names = [v for key, v in lv.props(row) if key == "name"]
            bound.append((cls, names[0] if names else ""))
        assert tuple(bound) == cast, (level, cut, bound)
        keyset = [struct.unpack_from("<fhh", data, key_off + 20 * k) for k in range(key_count)]
        got_shows = tuple(sorted(a for _t, a, kind in keyset if kind == 8 and a >= 0))
        assert got_shows == shows, (level, cut, got_shows)
        slot3 = Counter((a, kind) for _t, a, kind in keyset if kind in (3, 4) and a >= 0)
        assert sorted(slot3.items()) == sorted(R.SLOT3_KEYS[cut].items()), (level, cut, sorted(slot3.items()))
    for name, lv in levels.items():
        cuts = {f[:-4] for f in lv.files if f.endswith(".cut")}
        auto = {c for c in cuts if c.startswith("autosave")}
        asked = {row[3] for row in R.CUTSCENES if row[0] == name}
        assert len(auto) == R.AUTOSAVE[name], name
        assert cuts - auto - asked == set(R.UNREQUESTED[name]), (name, sorted(cuts - auto - asked))
        for cut in R.UNREQUESTED[name]:
            data = lv.files[cut + ".cut"]
            _f, _ko, _kc, actor_off, actor_count = struct.unpack_from("<5I", data, 0)
            classes = tuple(data[actor_off + 0x2C * k + 8: actor_off + 0x2C * k + 0x1C].split(b"\0")[0]
                            .decode("latin1") for k in range(actor_count))
            assert classes == R.UNREQUESTED_ACTORS[cut], (name, cut, classes)
    return len(R.CUTSCENES), bindings


def record_facts(levels):
    """Record properties the document relies on, by record name (R.RECORD_FACTS)."""
    checked = 0
    for (name, cls, record), (present, absent) in R.RECORD_FACTS.items():
        rows = [r for r in levels[name].rows if r["class"] == cls
                and dict(levels[name].props(r)).get("name", "") == record]
        assert len(rows) == 1, (name, cls, record, len(rows))
        keys = {k for k, _v in levels[name].props(rows[0])}
        props = dict(levels[name].props(rows[0]))
        for key, value in present:
            assert key in keys and (value is None or props[key] == value), (name, record, key)
        for key in absent:
            assert key not in keys, (name, record, key)
        checked += 1
    for (name, cls), want in R.CLASS_KEYS.items():
        got = Counter(tuple(k for k, _v in levels[name].props(r)) for r in levels[name].rows if r["class"] == cls)
        assert got == Counter(want), (name, cls, got)
        checked += 1
    for (name, cls, key), want in R.CLASS_VALUES.items():
        got = Counter(dict(levels[name].props(r)).get(key) for r in levels[name].rows if r["class"] == cls)
        assert got == Counter(want), (name, cls, key, got)
        checked += 1
    for name, lv in levels.items():
        drops = Counter(dict(lv.props(r)).get("dropitem") for r in lv.rows if "dropitem" in dict(lv.props(r)))
        assert drops == Counter(R.DROPS[name]), (name, drops)
        checked += 1
    return checked


def travel_sites(levels):
    got = []
    grants = []
    for name, lv in levels.items():
        for off, native, cells in lv.sites():
            if native == "newWorld":
                got.append((name, lv.entry_of(off), off, lv.pool[cells[0]]))
            if native == "grantMission":
                assert cells == [1], (name, off)
                grants.append((name, lv.entry_of(off), off))
    assert sorted(got) == sorted(R.NEWWORLD), sorted(got)
    assert sorted(grants) == sorted(R.GRANTS), sorted(grants)
    return len(got)


def loader_names(elf):
    ee = EE(elf)
    for call, string, text in R.LOADER_NAMES:
        hi, lo = ee.mem.u32(call - 4), ee.mem.u32(call + 4)
        assert hi >> 26 == 0x0F and lo >> 26 == 0x09 and (hi >> 16) & 31 == 4 and (lo >> 16) & 31 == 4
        addr = ((hi & 0xFFFF) << 16) + struct.unpack("<h", struct.pack("<H", lo & 0xFFFF))[0]
        assert ee.mem.u32(call) >> 26 == 0x03 and (ee.mem.u32(call) & 0x3FFFFFF) << 2 == RUN_BY_NAME
        assert addr == string and ee.mem.cstr(addr) == text, (hex(call), hex(addr))
    return len(R.LOADER_NAMES)


def markers(elf, levels):
    """Player1_ctor on each level's markers in record order, by previous level."""
    class Follow:
        def __contains__(self, addr):
            return addr in (PLAYER1_CTOR, OBJ_GET_PROP_STR, 0x14C880, OBJECT_CTOR) or 0x3A5000 <= addr < 0x3C0000
    out = {}
    for (name, prev), want in R.MARKERS.items():
        lv = levels[name]
        ee = EE(elf)
        ee.follow = Follow()
        ee.mem.w32(G_WORLD, ee.alloc(0x100))
        ee.mem.w8(G_START_RANK, 0)
        ee.mem.w8(G_GATE_TRAVEL, 0)
        ee.mem.write(G_PREV_LEVEL, prev.encode() + b"\0")
        ee.mem.write(G_ENTRANCE, b"\0")
        took, current = [], [None]

        def spot(e):
            took.append(current[0])
            out_ptr = e.r[4] & 0xFFFFFFFF
            e.mem.write(out_ptr, e.mem.read(e.r[5] & 0xFFFFFFFF, 12))
            return out_ptr
        ee.stub(FREE_SPOT, function=spot)
        for row in lv.rows:
            if row["class"] != "Player1":
                continue
            current[0] = dict(lv.props(row)).get("from", "")
            obj, pos = ee.alloc(0x100), ee.alloc(12)
            ee.mem.write(pos, struct.pack("<3f", float(row["x"]), float(row["y"]), float(row["height"])))
            ee.call(PLAYER1_CTOR, obj, pos, row["angle"], props_ptr(ee, row), max_steps=2000000)
        got = (ee.mem.s8(G_START_RANK), took[-1], len(took))
        assert got == want, (name, prev, got, want)
        out[(name, prev)] = got
    return len(out)


def deaths(elf, levels):
    """Creature_onDeath on the death-scripted and dropping arena records."""
    class Follow:
        def __contains__(self, addr):
            return addr in (CREATURE_ON_DEATH, OBJ_GET_PROP_STR, 0x14C880, OBJECT_CTOR) or 0x3A5000 <= addr < 0x3C0000
    count = 0
    for (name, cls), want in R.DEATHS.items():
        assert any(k[:2] == (name, cls) and v == want for k, v in R.DEATHS_BY_NAME.items()), (name, cls)
    for (name, cls, record), want in R.DEATHS_BY_NAME.items():
        rows = [r for r in levels[name].rows if r["class"] == cls
                and dict(levels[name].props(r)).get("name", "") == record]
        assert len(rows) == 1, (name, cls, record, len(rows))
        row = rows[0]
        for quiet in (0, 1):
            ee = EE(elf)
            ee.follow = Follow()
            ee.mem.w32(G_WORLD, ee.alloc(0x100))
            got = []
            obj, pos, definition = ee.alloc(0x480), ee.alloc(12), ee.alloc(0x100)
            ee.stub(RUN_BY_NAME, function=lambda e: got.append(
                ("script", e.mem.cstr(e.r[4] & 0xFFFFFFFF), e.mem.u32(SELECTED) == obj)) or 0)
            ee.stub(LOOT_SPAWN_NAMED, function=lambda e: got.append(
                ("drop", e.mem.cstr(e.r[5] & 0xFFFFFFFF))) or 0)
            ee.call(OBJECT_CTOR, obj, pos, definition, props_ptr(ee, row), max_steps=2000000)
            ee.call(CREATURE_ON_DEATH, obj, quiet, max_steps=2000000)
            expected = [x for x in want if not (quiet and x[0] == "drop")]
            assert got == expected and ee.mem.u32(SELECTED) == 0, (name, cls, record, quiet, got)
            count += 1
    return count


def mutated(level, offset, opcode, old, new):
    """A copy of the level whose script cell at code offset+4 changes old -> new."""
    clone = Level.__new__(Level)
    clone.__dict__.update(level.__dict__)
    start = level.code[0]
    assert struct.unpack_from("<2I", level.image, start + offset) == (opcode, old), hex(offset)
    image = bytearray(level.image)
    struct.pack_into("<I", image, start + offset + 4, new)
    clone.image = bytes(image)
    return clone


def controls(host, levels):
    """Each must make the original and the model disagree."""
    cases = []
    arm = mutated(levels["drunarm"], 0x560, 0x0B, 275, 276)       # endDelay threshold
    dar = mutated(levels["drundar"], 0x870, 0x69, 8, 7)           # showSwitchCount: A == 8
    cases.append(("drunarm endDelay 275->276", lambda: scenario_drunarm(host, dict(levels, drunarm=arm))))
    cases.append(("drundar switch count 8->7", lambda: scenario_drundar(host, dict(levels, drundar=dar))))
    saved = R.scaled_time
    def model_off_by_one():
        R.scaled_time = lambda n: n
        try:
            scenario_drunare(host, levels)
        finally:
            R.scaled_time = saved
    cases.append(("model getScaledTime n", model_off_by_one))

    def model_without(level_run, method, cell):
        """The model with one zeroing store removed: the sentinel must expose it."""
        def run():
            saved_body = getattr(R.Model, method)

            def body(self):
                before = self.g.get(cell)
                result = saved_body(self)
                if before is not None:
                    self.g[cell] = before
                return result
            setattr(R.Model, method, body)
            try:
                level_run(host, levels)
            finally:
                setattr(R.Model, method, saved_body)
        return run
    cases.append(("model strife step2pause keeps 0x154", model_without(scenario_strife, "strife_step2pause", 0x154)))
    cases.append(("model drundar preStart keeps 0x28", model_without(scenario_drundar, "drundar_preStart", 0x28)))
    for name, run in cases:
        try:
            run()
        except AssertionError as exc:
            if " log:" in str(exc) or " state:" in str(exc):
                continue
            raise
        raise AssertionError("control not detected: " + name)
    return len(cases)


def hub_names(host):
    out = {}
    for evil, decision, complete in ((0, 1, 1), (1, 1, 1), (0, 1, 0), (1, 1, 0)):
        out[(evil, decision, complete)] = host.hub_name(evil, decision, complete)
    assert out == R.HUB_NAMES, out
    return len(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--elf", required=True)
    ap.add_argument("--disc", required=True)
    ap.add_argument("--seed", type=int, default=20973)
    args = ap.parse_args()
    assert hashlib.sha256(open(args.elf, "rb").read()).hexdigest() == ELF_SHA256
    levels = {name: Level(args.disc, name) for name in ("strife", "drundar", "drunarm", "drunare")}
    made = census(args.elf, levels, args.seed)
    linked = links(levels)
    types = type_names(args.elf, levels)
    cuts, bindings = cutscene_files(levels, types)
    facts = record_facts(levels)
    travel = travel_sites(levels)
    names = loader_names(args.elf)
    arrivals = markers(args.elf, levels)
    died = deaths(args.elf, levels)
    host = Host(args.elf, args.seed)
    hubs = hub_names(host)
    results = {}
    for name, run in (("drunarm", scenario_drunarm), ("drunare", scenario_drunare),
                      ("strife", scenario_strife), ("drundar", scenario_drundar)):
        results[name] = run(host, levels)
    rejected = controls(host, levels)
    for name, want in R.MILESTONES.items():
        got = {k: v for k, v in results[name].items() if k in want}
        assert got == want, (name, got, want)
    steps = sum(r["steps"] for r in results.values())
    frames = sum(r["frames"] for r in results.values())
    milestones = " ".join("%s:%s" % (n, ",".join("%s=%s" % kv for kv in sorted(
        (k, v) for k, v in r.items() if k not in ("steps", "frames")))) for n, r in results.items())
    digest = hashlib.sha256(open(__file__, "rb").read()).hexdigest()[:16]
    print("PASS seed %d: %d arena objects made, %d record links, %d cutscenes (%d actor bindings by the "
          "cut_setup box search, %d type names), %d record facts, %d travel sites, "
          "%d loader names, %d marker cases, %d death cases, %d hub cases, %d controls rejected, %d compared steps "
          "(%d frames in the four main runs); milestones %s; tool %s"
          % (args.seed, made, linked, cuts, bindings, len(types), facts, travel, names, arrivals, died, hubs,
             rejected, steps, frames, milestones, digest))

if __name__ == "__main__":
    main()
