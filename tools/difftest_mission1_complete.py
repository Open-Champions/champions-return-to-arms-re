#!/usr/bin/env python3
"""Ordinary mission-1 completion against the original script host.

Runs the shipped arena and exit entries in tools/ee_emu.py. Campaign natives
(grant, quest variables, quest remove, newWorld, scaled time, pause, item
count wrappers) are the original functions. World, cutscene, sound, HUD and
bag-walk callees are stubbed. Both register seeds are accepted; this path
does not draw the seed.

Preload the stdlib dis module first. tools/dis.py shadows it, and this
interpreter imports dis while building argparse:

  PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["difftest_mission1_complete.py","--elf","local/SLUS_209.73","--disc","local/disc"]; runpy.run_path("tools/difftest_mission1_complete.py", run_name="__main__")'
"""
import argparse
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError
from gob import gob_entries, lmp_entries
import ref_mission1_complete as M
import scr

ELF_SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
PLAYERS = 0x4D8AF0
REC = 0x4C30
MISSION = 0x4BBF
QUESTS = 0x41D0
QUEST_COUNT = 0x43D0
P_OBJECT = 0x43D8
EVIL = 0x4C1A
DECISION = 0x4C1B
MEDAL = 0x4C0D
GOLD = 0xE4
EXP = 0x5C
SEED = 0x404464
NUM_PLAYERS = 0x4D8AE0
DIFFICULTY = 0x4F719C
PAUSED = 0x41B4F4
CUTSCENE = 0x44FCD0
JUMPGATE = 0x500AE8
NETWORK = 0x402791
MACHINE = 0x86B270
DEFER_NAMES = 0x86B278
DEFER_COUNT = 0x86DA78
DEFER_QUEUED = 0x86DA7C
DEFER_FLIP = 0x4F8690
QUEST_VARS = 0x86DA80
POST_ACTION = 0x86FA80
SELECTED = 0x4039F8
PENDING = 0x41B6D0
ORIENT = 0x41B720
NATIVE_TABLE = 0x403370
SCR_LOAD, SCR_REGISTER = 0x13E8F8, 0x141310
RUN_BY_NAME = 0x1ED694
RUN_DEFERRED = 0x1ED5A0
RUN_POST = 0x1EDAC0
CLEAR_DEFERRED = 0x1EDA08
GET_SCALED = 0x14412C
GET_HUB = 0x1EC300
ROW_AVAILABLE = 0x231078
COUNT_ITEM = 0x1C5880
FIND_ITEM = 0x1C5A70
REMOVE_ITEM = 0x1C1CB0
O_FLAGS = 0x0C
OF_CREATURE = 0x20
STUB_NAMES = {
    "hideMonster", "showMonster", "killMonster", "deleteMonster", "setMonsterVal",
    "autoPropSetState", "setCFlag", "setSaveInhibit", "cutScene", "soundSequence",
    "setInfo", "reapEnemies", "addHelpMessage", "playGotItemSound", "givePlayerItem",
    "activateMissionMenu", "startDialog", "showBust", "addParticleOnObject",
    "changeSwoop", "activateStore", "getHitPoints", "addQuest", "showCompass",
    "setInfo",
}
LEVELS = ("drunare", "drunarm", "strife", "drundar", "hub")
SCAN_LEVELS = LEVELS + ("blood1",)
MARK_GOLD = 0x01020304
MARK_EXP = 0x05060708
MARK_EVIL = 0x2A
MARK_DECISION = 0x3C
MARK_MEDAL = 0x21
MARK_ROW = 0x50
MARK_MISSION2 = 0x40
MARK_GLOBAL = 0x5A
COMPLETION = (
    ("drunare", "levelChange"),
    ("drunarm", "shardCheckLoop"),
    ("strife", "exitzone"),
    ("drundar", "exitzone"),
)
ABSENT_FROM_COMPLETION = (
    "grantBronze", "grantSilver", "grantGold", "givePlayerExp", "setMissionAvailable",
)


def mission_addr(slot, difficulty, mission):
    return PLAYERS + slot * REC + MISSION + difficulty * 13 + mission


def load_level(disc, level):
    gob = open(os.path.join(disc, level.upper() + ".GOB"), "rb").read()
    off, size = next((o, s) for name, o, s in gob_entries(gob) if name.lower() == level + ".lmp")
    lump = gob[off:off + size]
    scripts = [(o, s) for name, o, s in lmp_entries(lump) if name.lower() == "script.scr"]
    objects = [(o, s) for name, o, s in lmp_entries(lump) if name.lower() == "objects.ob"]
    assert len(scripts) == 1 and len(objects) == 1
    return lump[scripts[0][0]:scripts[0][0] + scripts[0][1]], lump[objects[0][0]:objects[0][0] + objects[0][1]]


def push_arg(image, call_off, index):
    """Integer or string cell pushed as argument `index` of the SYSREQ at call_off."""
    parsed = scr.parse(image)
    start = parsed["code"][0]
    pool = dict(scr.strings(image, *parsed["strings"]))
    # pushes are 8 bytes, right to left, then the byte count, immediately before SYSREQ.C
    externals = [name for _, name in parsed["externals"]]
    native = externals[struct.unpack_from("<I", image, start + call_off + 4)[0]]
    argc = struct.unpack_from("<I", image, start + call_off - 4)[0] // 4
    assert 0 <= index < argc
    assert struct.unpack_from("<I", image, start + call_off)[0] == 0x7B
    assert struct.unpack_from("<I", image, start + call_off - 8)[0] == 0x27
    cell = struct.unpack_from("<I", image, start + call_off - 8 * (index + 1) - 4)[0]
    assert struct.unpack_from("<I", image, start + call_off - 8 * (index + 1))[0] == 0x27
    if cell in pool and cell >= 8:
        return native, pool[cell]
    return native, cell


def death_links(blob):
    count, _flags, strtab = struct.unpack_from("<hHi", blob, 0)

    def text(off):
        at = strtab + off
        return blob[at:blob.index(b"\0", at)].decode("latin1")

    rows, at = [], 8
    for _ in range(count):
        cls, size, _angle = struct.unpack_from("<ihH", blob, at)
        props, cursor = [], at + 20
        while cursor < at + size:
            raw, = struct.unpack_from("<i", blob, cursor)
            if raw == 0:
                break
            props.append(text(raw))
            cursor += 4
        kept = {}
        for item in props:
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            if key in ("deathscript", "name", "action", "t"):
                kept.setdefault(key, []).append(value)
        rows.append((text(cls), kept))
        at += size
    return rows


class Host:
    def __init__(self, elf, seed):
        self.ee = EE(elf)
        self.ee.record_writes = False
        self.ee.record_calls = False
        self.seed = seed
        self.counts = [0, 0, 0, 0]
        self.removes = []
        self.stubs = []
        self.entered = []
        self.scripts = []
        self.hp = 0
        self.base = self.ee.alloc(0x80000, align=16)
        self.names = self.ee.alloc(0x1000, align=16)
        self.player_body = self.ee.alloc(0x40, align=16)
        self._bind_services()
        self.reset_campaign()

    def _bind_services(self):
        ee = self.ee
        mem = ee.mem
        handlers = {}
        for index in range(191):
            name_at = mem.u32(NATIVE_TABLE + 8 * index)
            handler = mem.u32(NATIVE_TABLE + 8 * index + 4)
            if name_at == 0 or handler == 0:
                break
            handlers[mem.cstr(name_at)] = handler
        self.handlers = handlers
        for name in STUB_NAMES:
            handler = handlers[name]
            ee.stub(handler, function=self._native_stub(name), name=name)
        # Oracle for "which natives ran": every other handler keeps its original body
        # and only gets a recording hook at its first instruction.
        by_addr = {}
        for name, handler in handlers.items():
            if name not in STUB_NAMES:
                by_addr.setdefault(handler, []).append(name)
        for handler, names in by_addr.items():
            ee.hook(handler, self._native_seen("|".join(sorted(names))))
        ee.hook(RUN_BY_NAME, self._script_seen)
        ee.stub(COUNT_ITEM, function=self._count_item, name="inventory_countItemByName")
        ee.stub(FIND_ITEM, function=self._find_item, name="inventory_findItemBySubstring")
        ee.stub(REMOVE_ITEM, function=self._remove_item, name="inventory_removeItem")

    def _native_stub(self, name):
        def run(_ee):
            self.stubs.append(name)
            self.entered.append(name)
            if name == "getHitPoints":
                return self.hp
            return 0
        return run

    def _native_seen(self, name):
        def run(_ee):
            self.entered.append(name)
        return run

    def _script_seen(self, ee):
        self.scripts.append(ee.mem.cstr(ee.r[4] & 0xFFFFFFFF, 80))

    def mark(self):
        """Positions in the native and script-entry logs, for `since`."""
        return len(self.entered), len(self.scripts), len(self.stubs)

    def since(self, mark):
        """Natives entered (original and stubbed, in order), script entries started
        through script_runByName, and stubs entered after `mark`."""
        return (self.entered[mark[0]:], self.scripts[mark[1]:], self.stubs[mark[2]:])

    def _count_item(self, ee):
        slot = ee.r[5] & 0xFFFFFFFF
        if slot > 3:
            return 0
        return self.counts[slot]

    def _find_item(self, ee):
        mem = ee.mem
        mem.w32(ee.r[6] & 0xFFFFFFFF, 0)
        mem.w32(ee.r[7] & 0xFFFFFFFF, 0)
        return 0

    def _remove_item(self, ee):
        self.removes.append((ee.r[4] & 0xFFFFFFFF, ee.r[5] & 0xFFFFFFFF, ee.r[6] & 0xFFFFFFFF))
        return 0

    def reset_campaign(self):
        ee = self.ee
        mem = ee.mem
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
            mem.write(rec + MEDAL, b"\0" * 13)
            mem.w32(rec + GOLD, 0)
            mem.w32(rec + EXP, 0)
        self.counts[:] = (0, 0, 0, 0)
        self.removes.clear()
        self.stubs.clear()
        self.entered.clear()
        self.scripts.clear()
        self.hp = 0
        self.set_mission(0, 1, 0, 1)

    def set_mission(self, slot, mission, difficulty, value):
        self.ee.mem.w8(mission_addr(slot, difficulty, mission), value)

    def mission(self, slot, mission, difficulty=0):
        return self.ee.mem.u8(mission_addr(slot, difficulty, mission))

    def place(self, image):
        ee = self.ee
        ee.mem.write(self.base, image + bytes(0x200))
        ee.mem.w32(MACHINE, self.base)
        error = ee.call(SCR_LOAD, self.base, self.base + 0x60, max_steps=2000000)
        bound = ee.call(SCR_REGISTER, self.base, NATIVE_TABLE, 0xFFFFFFFF, max_steps=2000000)
        assert error == 0 and bound == 0, (error, bound)
        ee.mem.w32(DEFER_COUNT, 0)
        ee.mem.w32(DEFER_QUEUED, 0)
        ee.mem.w32(DEFER_FLIP, 0)
        ee.mem.write(POST_ACTION, b"\0")

    def run(self, name):
        ee = self.ee
        ee.mem.write(self.names, name.encode("latin1") + b"\0")
        try:
            return ee.call(RUN_BY_NAME, self.names, max_steps=2000000) & 0xFFFFFFFF
        except EmuError as exc:
            raise AssertionError("%s: %s" % (name, exc))

    def deferred(self):
        try:
            self.ee.call(RUN_DEFERRED, max_steps=2000000)
        except EmuError as exc:
            raise AssertionError("deferred: %s" % exc)

    def post(self):
        try:
            self.ee.call(RUN_POST, max_steps=2000000)
        except EmuError as exc:
            raise AssertionError("post: %s" % exc)

    def clear_queue(self):
        self.ee.call(CLEAR_DEFERRED, max_steps=100000)

    def scaled(self, count):
        # Script natives take (amx, params). params[0] is the byte count.
        mem = self.ee.mem
        mem.w32(self.names, 4)
        mem.w32(self.names + 4, count & 0xFFFFFFFF)
        return self.ee.call(GET_SCALED, self.base, self.names, max_steps=100000) & 0xFFFFFFFF

    def cstr(self, addr, limit=80):
        return self.ee.mem.cstr(addr, limit)

    def post_name(self):
        return self.cstr(POST_ACTION)

    def pending(self):
        return self.cstr(PENDING)

    def vars(self):
        mem = self.ee.mem
        out, at = {}, QUEST_VARS
        while mem.u8(at) != 0 and at < QUEST_VARS + 0x800:
            name = mem.cstr(at)
            at += len(name) + 1
            out[name] = mem.s8(at)
            at += 1
        return out

    def _defer_names(self, count_addr, half):
        mem = self.ee.mem
        names = []
        for index in range(mem.u32(count_addr)):
            names.append(mem.cstr(DEFER_NAMES + (half * 64 + index) * 0x50))
        return names

    def queued_names(self):
        """Back half. `addDeferedCall` writes here; `script_runDeferred` has not promoted it."""
        half = (self.ee.mem.u32(DEFER_FLIP) & 1) ^ 1
        return self._defer_names(DEFER_QUEUED, half)

    def front_names(self):
        """Front half. After `script_runDeferred` these are the next frame's entries."""
        half = self.ee.mem.u32(DEFER_FLIP) & 1
        return self._defer_names(DEFER_COUNT, half)

    def seed_now(self):
        return self.ee.mem.u32(SEED)

    def plant_quest(self, title):
        mem = self.ee.mem
        mem.write(PLAYERS + QUESTS, title.encode("latin1") + b"\0")
        mem.write(PLAYERS + QUESTS + 0x20, b"body\0")
        mem.write(PLAYERS + QUESTS + 0x40, b"Keep\0")
        mem.write(PLAYERS + QUESTS + 0x60, b"body\0")
        mem.w32(PLAYERS + QUEST_COUNT, 2)

    def data_base(self):
        dat = self.ee.mem.s32(self.base + 0x70)
        if not 0 < dat < 0x200000:
            raise AssertionError("script dat %s" % dat)
        return self.base + 0x60 + dat

    def global_cell(self, cell):
        return self.ee.mem.s32(self.data_base() + cell)

    def set_global(self, cell, value):
        self.ee.mem.w32(self.data_base() + cell, value & 0xFFFFFFFF)

    def plant_untouched(self):
        """Nonzero sentinels in fields a completion entry is claimed to leave alone.

        Difficulty 0's mission-1 bytes stay the reset pattern: slot 0 is 1 and
        slots 1-3 are 0. Those four are the bytes the grant is expected to change.
        """
        mem = self.ee.mem
        for slot in range(4):
            rec = PLAYERS + slot * REC
            mem.w32(rec + GOLD, MARK_GOLD)
            mem.w32(rec + EXP, MARK_EXP)
            mem.w8(rec + EVIL, MARK_EVIL)
            mem.w8(rec + DECISION, MARK_DECISION)
            for mission in range(13):
                mem.w8(rec + MEDAL + mission, MARK_MEDAL + mission)
                for difficulty in range(5):
                    if difficulty == 0 and mission == 1:
                        continue
                    value = MARK_MISSION2 if mission == 2 else MARK_ROW
                    mem.w8(mission_addr(slot, difficulty, mission), value)

    def untouched_mismatches(self, skip=()):
        mem = self.ee.mem
        bad = []
        for slot in range(4):
            rec = PLAYERS + slot * REC
            for label, got, expect in (
                    ("gold", mem.u32(rec + GOLD), MARK_GOLD),
                    ("exp", mem.u32(rec + EXP), MARK_EXP),
                    ("evil", mem.u8(rec + EVIL), MARK_EVIL),
                    ("decision", mem.u8(rec + DECISION), MARK_DECISION)):
                if got != expect:
                    bad.append((slot, label, got, expect))
            for mission in range(13):
                medal = mem.u8(rec + MEDAL + mission)
                if medal != MARK_MEDAL + mission:
                    bad.append((slot, "medal", mission, medal, MARK_MEDAL + mission))
                for difficulty in range(5):
                    if (difficulty, mission) in skip or (difficulty == 0 and mission == 1):
                        continue
                    expect = MARK_MISSION2 if mission == 2 else MARK_ROW
                    got = self.mission(slot, mission, difficulty)
                    if got != expect:
                        bad.append((slot, "mission", difficulty, mission, got, expect))
        return bad

    def assert_untouched(self, skip=()):
        bad = self.untouched_mismatches(skip)
        if bad:
            raise AssertionError(bad[:12])


def walk_sysreqs(image):
    parsed = scr.parse(image)
    cs, ce = parsed["code"]
    externals = [name for _, name in parsed["externals"]]
    words = struct.unpack_from("<%dI" % ((ce - cs) // 4), image, cs)
    i = 0
    while i < len(words):
        off, op = i * 4, words[i]
        if op == 0x7D:
            i += 3
            continue
        if op == 0x7B:
            idx = words[i + 1]
            yield off, externals[idx] if idx < len(externals) else "?"
            i += 2
            continue
        if op in scr.OPS:
            i += 1 + scr.OPS[op][1]
        elif op in scr.NO_OPERAND:
            i += 1
        else:
            i += 2


def public_rows(image):
    return sorted(scr.parse(image)["internals"])


def public_at(image, off):
    name = None
    for val, pub in public_rows(image):
        if val <= off:
            name = pub
        else:
            break
    return name


def grant_sites(image):
    found = []
    for off, native in walk_sysreqs(image):
        if native != "grantMission":
            continue
        native, arg = push_arg(image, off, 0)
        found.append((off, public_at(image, off), arg))
    return found


def entry_natives(image, entry):
    rows = public_rows(image)
    for index, (val, name) in enumerate(rows):
        if name != entry:
            continue
        end = rows[index + 1][0] if index + 1 < len(rows) else 1 << 30
        return [native for off, native in walk_sysreqs(image) if val <= off < end]
    raise AssertionError(entry)


def entry_span(image, entry):
    rows = public_rows(image)
    for index, (val, name) in enumerate(rows):
        if name == entry:
            return val, (rows[index + 1][0] if index + 1 < len(rows) else 1 << 30)
    raise AssertionError(entry)


def entry_internal_calls(image, entry):
    """Script-to-script `call` ops (0x31) inside one public entry."""
    start, end = entry_span(image, entry)
    parsed = scr.parse(image)
    cs, ce = parsed["code"]
    words = struct.unpack_from("<%dI" % ((ce - cs) // 4), image, cs)
    found, i = [], 0
    while i < len(words):
        off, op = i * 4, words[i]
        if op == 0x31 and start <= off < end:
            found.append((off, words[i + 1]))
        if op == 0x7D:
            i += 3
        elif op == 0x7B:
            i += 2
        elif op in scr.OPS:
            i += 1 + scr.OPS[op][1]
        elif op in scr.NO_OPERAND:
            i += 1
        else:
            i += 2
    return found


def entry_string_args(image, entry):
    """Constant string arguments pushed to the natives of one entry, plus the
    (offset, index) pairs whose push is not a constant cell."""
    start, end = entry_span(image, entry)
    parsed = scr.parse(image)
    cs = parsed["code"][0]
    texts, unresolved = [], []
    for off, _native in walk_sysreqs(image):
        if not start <= off < end:
            continue
        argc = struct.unpack_from("<I", image, cs + off - 4)[0] // 4
        for index in range(argc):
            try:
                _n, arg = push_arg(image, off, index)
            except AssertionError:
                unresolved.append((off, index))
                continue
            if isinstance(arg, str):
                texts.append(arg)
    return texts, unresolved


KNIGHT_VARS = ("knight1", "knight2", "knight3", "knight4")
KNIGHT_ENTRIES = (
    ("setv4d6b", 0xB3C, 0xB68, "knight1"),
    ("setv772a", 0xBB4, 0xBE0, "knight2"),
    ("setv5138", 0xC2C, 0xC58, "knight3"),
    ("setvcccf", 0xCA4, 0xCD0, "knight4"),
)
RALLOS_REMOVE = (
    (0x72C, "killMonster", "rallos"),
    (0x758, "hideMonster", "rallos"),
    (0x784, "deleteMonster", "rallos"),
    (0x7B0, "hideMonster", "rallos2"),
    (0x7DC, "deleteMonster", "rallos2"),
)
SHARD_GRANT_NATIVES = [
    "gamePaused", "playerHasItem", "playGotItemSound", "addHelpMessage", "setv",
    "grantMission", "setv", "postAction"]


def s32(value):
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def check_static(images, objects):
    checks = 0
    for level, call, entry in (
            ("drunare", 0xAC4, "levelChange"),
            ("drunarm", 0x97C, "shardCheckLoop"),
            ("strife", 0x1ABC, "exitzone"),
            ("drundar", 0x19EC, "exitzone")):
        native, arg = push_arg(images[level], call, 0)
        assert native == "grantMission" and arg == 1, (level, native, arg)
        checks += 1
    native, arg = push_arg(images["drunare"], 0xAF0, 0)
    assert native == "newWorld" and arg == "hub2"
    native, arg = push_arg(images["drunarm"], 0xC90, 0)
    assert native == "newWorld" and arg == "strife"
    native, arg = push_arg(images["strife"], 0x1B94, 0)
    assert native == "newWorld" and arg == "drunarm"
    native, arg = push_arg(images["drundar"], 0x1AC4, 0)
    assert native == "newWorld" and arg == "drunare"
    native, arg = push_arg(images["drunarm"], 0x89C, 0)
    assert native == "playerHasItem" and arg == "shardofwar"
    checks += 5
    expected_grants = {
        "drunare": [(0xAC4, "levelChange", 1)],
        "drunarm": [(0x97C, "shardCheckLoop", 1)],
        "strife": [(0x1ABC, "exitzone", 1)],
        "drundar": [(0x19EC, "exitzone", 1)],
        "blood1": [],
        "hub": [(0x28C4, "start", 0)],
    }
    for level, rows in expected_grants.items():
        assert grant_sites(images[level]) == rows, (level, grant_sites(images[level]))
        checks += 1
    for level, entry in COMPLETION:
        natives = entry_natives(images[level], entry)
        for banned in ABSENT_FROM_COMPLETION:
            assert banned not in natives, (level, entry, banned)
        checks += 1
    for entry in ("endDelay", "playRallosRuns", "removeRallos"):
        assert "grantMission" not in entry_natives(images["drunarm"], entry), entry
        checks += 1
    assert entry_natives(images["drunarm"], "endDelay") == [
        "gamePaused", "getScaledTime", "callScript", "addDeferedCall"]
    native, arg = push_arg(images["drunarm"], 0x58C, 0)
    assert native == "callScript" and arg == "playRallosRuns"
    native, arg = push_arg(images["drunarm"], 0x5C0, 0)
    assert native == "addDeferedCall" and arg == "endDelay"
    native, arg = push_arg(images["drunarm"], 0x6BC, 0)
    assert native == "postAction" and arg == "removeRallos"
    checks += 4
    assert entry_natives(images["hub"], "setMissic270") == ["setMissionAvailable"]
    assert entry_natives(images["hub"], "setMissid125") == [
        "setMissionAvailable", "changeSwoop", "activateStore"]
    assert entry_natives(images["hub"], "setMissi3c49") == [
        "setMissionAvailable", "changeSwoop", "activateStore"]
    checks += 3
    hub_publics = dict(public_rows(images["hub"]))
    assert hub_publics[0x11C] == "if99a5"
    assert hub_publics[0x198] == "if441a"
    assert hub_publics[0x7B0] == "setMissic270"
    assert hub_publics[0x7FC] == "setMissid125"
    assert hub_publics[0x2064] == "setMissi3c49"
    checks += 5
    links = death_links(objects["drunare"])
    by_class = {}
    for cls, kept in links:
        by_class.setdefault(cls, []).append(kept)
    assert [row.get("deathscript") for row in by_class["UndeadKnight1"]] == [["setv4d6b"]]
    assert [row.get("deathscript") for row in by_class["UndeadKnight2"]] == [["setv772a"]]
    assert [row.get("deathscript") for row in by_class["UndeadKnight3"]] == [["setv5138"]]
    assert [row.get("deathscript") for row in by_class["UndeadKnight4"]] == [["setvcccf"]]
    assert [row.get("deathscript") for row in by_class["CazicAvatar"]] == [["callScria381"]]
    assert all(row.get("name") == ["knight"] for row in by_class["UndeadKnight1"])
    assert by_class["CazicAvatar"][0].get("name") == ["avatar"]
    checks += 6
    are = images["drunare"]
    assert entry_natives(are, "callScria381") == ["callScript"]
    assert push_arg(are, 0xD14, 0) == ("callScript", "bossDefeatedPause")
    assert entry_natives(are, "bossDefeatedPause") == ["addDeferedCall"]
    assert push_arg(are, 0x6EC, 0) == ("addDeferedCall", "bossDefeatedDelay")
    checks += 4
    for entry, set_at, call_at, var in KNIGHT_ENTRIES:
        assert entry_natives(are, entry) == ["setv", "callScript"], entry
        assert push_arg(are, set_at, 0) == ("setv", var) and push_arg(are, set_at, 1) == ("setv", 1)
        assert push_arg(are, call_at, 0) == ("callScript", "knightDefeatedPause")
        checks += 3
    assert entry_natives(are, "knightDefeatedPause") == ["getv"] * 4 + ["addDeferedCall"]
    for off, var in zip((0x3F0, 0x418, 0x440, 0x468), KNIGHT_VARS):
        assert push_arg(are, off, 0) == ("getv", var)
    assert push_arg(are, 0x4CC, 0) == ("addDeferedCall", "knightDefeatedDelay")
    checks += 6
    for level, entry in (("drunare", "callScria381"), ("drunare", "bossDefeatedPause"),
                         ("drunarm", "removeRallos")) + tuple(
                             ("drunare", row[0]) for row in KNIGHT_ENTRIES):
        assert entry_internal_calls(images[level], entry) == [], (level, entry)
        checks += 1
    unresolved_expected = {
        "levelChange": [], "shardCheckLoop": [(0xA54, 1), (0xA9C, 1)], "exitzone": []}
    for level, entry in COMPLETION:
        natives = entry_natives(images[level], entry)
        assert "getv" not in natives and "callScript" not in natives, (level, entry)
        assert entry_internal_calls(images[level], entry) == [], (level, entry)
        texts, unresolved = entry_string_args(images[level], entry)
        assert not set(texts) & set(KNIGHT_VARS), (level, entry)
        assert unresolved == unresolved_expected[entry], (level, entry, unresolved)
        checks += 4
    arm = images["drunarm"]
    assert entry_natives(arm, "removeRallos") == [row[1] for row in RALLOS_REMOVE]
    for off, native, target in RALLOS_REMOVE:
        assert push_arg(arm, off, 0) == (native, target)
        checks += 1
    checks += 1
    return checks


def run_evil(host, image):
    host.reset_campaign()
    host.place(image)
    host.plant_untouched()
    host.set_global(0, MARK_GLOBAL)
    _native, title = push_arg(image, 0xA4C, 0)
    host.plant_quest(title)
    mark = host.mark()
    assert host.run("callScria381") == 0
    # Recorded, not inferred: the only natives entered are callScript and the nested
    # entry's addDeferedCall, and the only script entry started is bossDefeatedPause.
    assert host.since(mark) == (
        ["callScript", "addDeferedCall"], ["callScria381", "bossDefeatedPause"], [])
    assert host.global_cell(0) == 0
    assert host.queued_names() == ["bossDefeatedDelay"]
    assert host.mission(0, 1) == 1
    assert not host.untouched_mismatches()
    host.ee.mem.w32(host.names, 0)
    paused = host.ee.call(host.handlers["gamePaused"], host.base, host.names, max_steps=100000) & 0xFFFFFFFF
    expected = M.evil_end_frame(lambda n: s32(host.scaled(n)))
    noticed = None
    ended = None
    assert expected["notice_frame"] == 252 and expected["frame"] == 877, expected
    for frame in range(expected["frame"] + 8):
        host.deferred()
        if frame == 0:
            assert host.global_cell(0) == 0, host.global_cell(0)
        if frame == 1:
            assert host.global_cell(0) == 1, host.global_cell(0)
        variables = host.vars()
        if noticed is None and variables.get("endsound") == 1:
            noticed = frame
        if ended is None and host.post_name() == "levelChange":
            ended = frame
            break
    if noticed != 252 or ended != 877:
        raise AssertionError("pause %s notice %s/252 end %s/877 vars %s" % (
            paused, noticed, ended, sorted(host.vars())))
    assert host.post_name() == "levelChange"
    assert host.vars().get("killedav") == 1
    assert host.vars().get("endsound") == 1
    assert host.vars().get("firstmissionever") == 1
    assert host.ee.mem.u32(PLAYERS + QUEST_COUNT) == 1
    assert host.cstr(PLAYERS + QUESTS) == "Keep"
    assert "cutScene" in host.stubs and "reapEnemies" in host.stubs
    assert host.pending() == ""
    assert [host.mission(slot, 1) for slot in range(4)] == [1, 0, 0, 0]
    host.assert_untouched()
    host.post()
    assert [host.mission(slot, 1) for slot in range(4)] == [3, 2, 2, 2]
    assert host.pending() == "hub2"
    assert host.ee.mem.u8(ORIENT) == 0xFF
    assert host.post_name() == ""
    host.assert_untouched()
    return expected["frame"], expected["notice_frame"]


def run_evil_gates(host, image):
    host.reset_campaign()
    host.place(image)
    host.ee.mem.w32(PAUSED, 1)
    host.run("callScria381")
    for _ in range(8):
        host.deferred()
    assert host.post_name() == ""
    assert host.mission(0, 1) == 1
    host.ee.mem.w32(PAUSED, 0)
    host.clear_queue()
    host.run("endmission")
    assert host.post_name() == "levelChange"
    assert host.mission(0, 1) == 1
    host.vars()  # killedAv is now 1; a second endmission must not grant or replace the post
    host.ee.mem.write(POST_ACTION, b"\0")
    host.run("endmission")
    assert host.post_name() == ""
    assert host.mission(0, 1) == 1
    host.plant_untouched()
    for slot in range(4):
        host.set_mission(slot, 1, 1, 0)
    host.ee.mem.w32(DIFFICULTY, 1)
    host.run("levelChange")
    assert host.mission(0, 1, 0) == 1
    assert [host.mission(slot, 1, 1) for slot in range(4)] == [2, 2, 2, 2]
    assert host.pending() == "hub2"
    host.assert_untouched(skip=((1, 1),))


def run_good(host, image):
    host.reset_campaign()
    host.place(image)
    host.plant_untouched()
    host.set_global(0xC, MARK_GLOBAL)
    host.set_global(8, MARK_GLOBAL + 1)
    host.set_global(0, MARK_GLOBAL + 2)
    host.counts[0] = 0
    assert host.run("start") == 0
    assert host.global_cell(0xC) == 0
    assert host.global_cell(8) == MARK_GLOBAL + 1
    assert host.global_cell(0) == MARK_GLOBAL + 2
    assert host.queued_names() == ["shardCheckLoop"]
    assert host.mission(0, 1) == 1
    # The file's counter cell is 0. Restore that after proving start left the sentinel,
    # so the 25-call schedule is the one already compared with getScaledTime.
    host.set_global(8, 0)
    host.counts[0] = 1
    grant = M.shard_grant_frame(lambda _frame: 1)
    assert grant == M.shard_check_frame(1) == 25
    for frame in range(grant):
        host.deferred()
        assert host.mission(0, 1) == 1
    assert host.global_cell(8) == 24, host.global_cell(8)
    assert host.global_cell(0xC) == 0
    assert host.global_cell(0) == MARK_GLOBAL + 2
    assert host.queued_names() == [], host.queued_names()
    assert host.front_names() == ["shardCheckLoop"], host.front_names()
    mark = host.mark()
    host.deferred()
    entered, scripts, stubs = host.since(mark)
    # Count 1: onePlayerHasItem is asked once per player slot and nothing is removed.
    assert entered == SHARD_GRANT_NATIVES + ["onePlayerHasItem"] * 4, entered
    assert scripts == ["shardCheckLoop"] and stubs == ["playGotItemSound", "addHelpMessage"], stubs
    assert [host.mission(slot, 1) for slot in range(4)] == [3, 2, 2, 2]
    assert host.global_cell(8) == 0
    assert host.global_cell(0xC) == 0
    assert host.global_cell(0) == MARK_GLOBAL + 2
    assert host.queued_names() == [], host.queued_names()
    assert host.front_names() == [], host.front_names()
    host.assert_untouched()
    raised = [name for name, value in host.vars().items() if value == 1]
    assert "firstmissionever" in raised, sorted((len(name), value) for name, value in host.vars().items())
    others = [name for name in raised if name != "firstmissionever"]
    assert len(others) == 1 and len(others[0]) == 14 and others[0].isascii(), (
        [(len(name), value) for name, value in host.vars().items()])
    assert host.post_name() == "endmission"
    assert host.pending() == ""
    assert host.removes == []
    mark = host.mark()
    host.post()
    assert host.since(mark) == (
        ["addHelpMessage", "soundSequence"], ["endmission"], ["addHelpMessage", "soundSequence"])
    assert host.mission(0, 1) == 3
    assert host.pending() == ""
    assert host.post_name() == ""
    assert "addHelpMessage" in host.stubs and "soundSequence" in host.stubs
    assert "grantBronze" not in host.stubs

    host.reset_campaign()
    host.place(image)
    host.plant_untouched()
    host.set_global(0xC, MARK_GLOBAL)
    host.set_global(0, MARK_GLOBAL + 2)
    host.counts[0] = 1
    host.run("start")
    assert host.global_cell(0xC) == 1
    assert host.queued_names() == ["shardCheckLoop"]
    first = M.shard_check_frame(1)
    for _frame in range(first + 1):
        host.deferred()
    assert host.mission(0, 1) == 1
    assert host.global_cell(8) == 0
    assert host.global_cell(0xC) == 1
    assert host.queued_names() == [], host.queued_names()
    assert host.front_names() == ["shardCheckLoop"], host.front_names()
    host.counts[0] = 2
    second = M.shard_grant_frame(lambda frame, mark=first: 2 if frame > mark else 1, snapshot=1)
    assert second == M.shard_check_frame(2)
    for _frame in range(first + 1, second):
        host.deferred()
        assert host.mission(0, 1) == 1
    mark = host.mark()
    host.deferred()
    entered, scripts, stubs = host.since(mark)
    # Count 2 in slot 0: one removePlayerItem after slot 0's query, then slots 1-3.
    assert entered == SHARD_GRANT_NATIVES + [
        "onePlayerHasItem", "removePlayerItem"] + ["onePlayerHasItem"] * 3, entered
    assert scripts == ["shardCheckLoop"] and stubs == ["playGotItemSound", "addHelpMessage"], stubs
    assert [host.mission(slot, 1) for slot in range(4)] == [3, 2, 2, 2]
    assert host.global_cell(0) == MARK_GLOBAL + 2
    assert host.global_cell(0xC) == 1
    assert host.global_cell(8) == 0
    assert host.queued_names() == [], host.queued_names()
    assert host.front_names() == [], host.front_names()
    assert host.removes == [(0, 0, 0)]
    host.assert_untouched()

    host.reset_campaign()
    host.place(image)
    host.ee.mem.w32(PAUSED, 1)
    host.set_global(8, MARK_GLOBAL + 1)
    host.set_global(0xC, MARK_GLOBAL)
    host.counts[0] = 1
    host.run("start")
    assert host.global_cell(0xC) == 1
    assert host.global_cell(8) == MARK_GLOBAL + 1
    for _ in range(25):
        host.deferred()
    assert host.mission(0, 1) == 1
    assert host.global_cell(8) == MARK_GLOBAL + 1
    assert host.global_cell(0xC) == 1


def set_var(host, name, value):
    host.ee.mem.write(host.names, name.encode("latin1") + b"\0")
    host.ee.call(0x1ED854, host.names, value, max_steps=100000)


def run_knights(host, image):
    """Each knight death entry with the other three knight variables planted."""
    checks = 0
    for position, (entry, _set_at, _call_at, var) in enumerate(KNIGHT_ENTRIES):
        for others_set in (True, False):
            host.reset_campaign()
            host.place(image)
            host.plant_untouched()
            for cell in (0, 8, 0xC, 0x10):
                host.set_global(cell, MARK_GLOBAL + cell)
            planted = {}
            for index, name in enumerate(KNIGHT_VARS):
                planted[name] = MARK_GLOBAL + index if others_set else 0
                set_var(host, name, planted[name])
            mark = host.mark()
            assert host.run(entry) == 0
            entered, scripts, stubs = host.since(mark)
            expect = dict(planted, **{var: 1})
            assert {name: host.vars().get(name) for name in KNIGHT_VARS} == expect, host.vars()
            assert scripts == [entry, "knightDefeatedPause"] and stubs == []
            if others_set:
                assert entered == ["setv", "callScript"] + ["getv"] * 4 + ["addDeferedCall"]
                assert host.queued_names() == ["knightDefeatedDelay"]
            else:
                # The four reads stop at the first clear variable.
                reads = 2 if position == 0 else 1
                assert entered == ["setv", "callScript"] + ["getv"] * reads, entered
                assert host.queued_names() == []
            assert [host.global_cell(cell) for cell in (0, 8, 0xC, 0x10)] == [
                MARK_GLOBAL + cell for cell in (0, 8, 0xC, 0x10)]
            assert [host.mission(slot, 1) for slot in range(4)] == [1, 0, 0, 0]
            assert host.post_name() == "" and host.pending() == ""
            host.assert_untouched()
            checks += 1
    return checks


def hp_boundary(host, image):
    taken = []
    for hp in (-100, -1, 0, 1, 50, 99, 100, 101, 500, 1000, 5000, 100000):
        host.reset_campaign()
        host.place(image)
        host.hp = hp
        host.run("rallosHPcheck")
        taken.append((hp, host.queued_names()))
    end = [hp for hp, names in taken if names == ["endDelay"]]
    watch = [hp for hp, names in taken if names == ["rallosHPcheck"]]
    assert end and watch and max(end) < min(watch), (end, watch)
    assert (max(end), min(watch)) == (0, 1), (end, watch)
    return max(end), min(watch)


def run_rallos(host, image):
    """Follow the queued name into the later entries and record what they change."""
    native, title = push_arg(image, 0x6E8, 0)
    assert native == "removeQuest" and isinstance(title, str) and title
    host.reset_campaign()
    host.place(image)
    host.plant_untouched()
    host.set_global(0x10, MARK_GLOBAL)
    host.hp = 1
    host.run("rallosHPcheck")
    assert host.queued_names() == ["rallosHPcheck"]
    assert host.global_cell(0x10) == MARK_GLOBAL
    host.reset_campaign()
    host.place(image)
    host.plant_untouched()
    host.plant_quest(title)
    host.set_global(0x10, MARK_GLOBAL)
    host.hp = 0
    assert host.run("rallosHPcheck") == 0
    assert host.queued_names() == ["endDelay"]
    assert host.global_cell(0x10) == 0
    assert host.mission(0, 1) == 1
    fired = None
    last = None
    for frame in range(2000):
        host.deferred()
        last = (frame, host.post_name(), host.queued_names(), host.global_cell(0x10),
                host.ee.mem.u32(PLAYERS + QUEST_COUNT))
        if host.post_name() == "removeRallos":
            fired = frame
            break
    if fired is None:
        raise AssertionError("rallos chain did not post: %s stubs %s" % (last, host.stubs))
    assert fired == 277, last
    assert host.front_names() == [], (host.front_names(), host.queued_names())
    assert host.queued_names() == []
    assert host.ee.mem.u32(PLAYERS + QUEST_COUNT) == 1
    assert host.cstr(PLAYERS + QUESTS) == "Keep"
    assert host.mission(0, 1) == 1
    assert host.pending() == ""
    assert "showMonster" in host.stubs and "cutScene" in host.stubs and "setSaveInhibit" in host.stubs
    assert "grantBronze" not in host.stubs
    host.assert_untouched()
    mark = host.mark()
    host.post()
    # Every native entered during the post action, original or stubbed, in order.
    removal = [row[1] for row in RALLOS_REMOVE]
    assert host.since(mark) == (removal, ["removeRallos"], removal), host.since(mark)
    assert host.post_name() == ""
    assert host.mission(0, 1) == 1
    assert host.ee.mem.u32(PLAYERS + QUEST_COUNT) == 1
    host.assert_untouched()
    return fired


def run_exits(host, images):
    for level, onward in (("strife", "drunarm"), ("drundar", "drunare")):
        host.reset_campaign()
        host.place(images[level])
        assert host.handlers["demoRunning"]
        returned = host.ee.call(host.handlers["demoRunning"], max_steps=100000) & 0xFFFFFFFF
        assert returned == 0
        assert host.run("exitzone") == 0
        assert host.pending() == onward
        assert host.mission(0, 1) == 1
        assert host.post_name() == ""
        assert host.queued_names() == []
        assert host.front_names() == []


def run_hub_view(host, images):
    host.reset_campaign()
    host.place(images["drunare"])
    host.plant_untouched()
    host.ee.mem.w32(DIFFICULTY, 0)
    host.run("levelChange")
    assert host.mission(0, 1) == 3
    host.assert_untouched()
    # The hub-name reads below are this probe's stores, after the grant.
    host.ee.mem.w8(PLAYERS + EVIL, 0)
    host.ee.mem.w8(PLAYERS + DECISION, 0)
    plain = host.ee.call(GET_HUB, max_steps=100000) & 0xFFFFFFFF
    assert host.cstr(plain) == "hub"
    host.ee.mem.w8(PLAYERS + EVIL, 1)
    host.ee.mem.w8(PLAYERS + DECISION, 1)
    evil = host.ee.call(GET_HUB, max_steps=100000) & 0xFFFFFFFF
    assert host.cstr(evil) == "hub2"
    host.place(images["hub"])
    for slot in range(4):
        host.set_mission(slot, 2, 0, 0)
    assert host.run("if441a") == 0
    assert host.run("if7b2c") == 1
    before = host.ee.call(ROW_AVAILABLE, 0, max_steps=1000000) & 0xFFFFFFFF
    other = host.ee.call(ROW_AVAILABLE, 1, max_steps=1000000) & 0xFFFFFFFF
    assert s32(before) == 1 and s32(other) == 0
    assert host.run("setMissic270") == 0
    assert host.mission(0, 2) == 1
    assert host.mission(0, 1) == 3
    assert host.run("if7b2c") == 0
    assert s32(host.ee.call(ROW_AVAILABLE, 1, max_steps=1000000) & 0xFFFFFFFF) == 1
    host.set_mission(0, 2, 0, 0)
    host.stubs.clear()
    assert host.run("setMissid125") == 0
    assert host.mission(0, 2) == 1
    assert host.mission(0, 1) == 3
    assert "activateStore" in host.stubs and "changeSwoop" in host.stubs
    host.set_mission(0, 2, 0, 0)
    host.stubs.clear()
    assert host.run("setMissi3c49") == 0
    assert host.mission(0, 2) == 1
    assert host.mission(0, 1) == 3
    assert "activateStore" in host.stubs and "changeSwoop" in host.stubs

    host.reset_campaign()
    host.place(images["hub"])
    host.set_mission(0, 1, 0, 1)
    assert host.run("if441a") == 1
    host.ee.mem.write(host.names, b"startedMission1\0")
    host.ee.call(0x1ED854, host.names, 1, max_steps=100000)
    assert host.run("if441a") == 0
    host.set_mission(0, 1, 0, 0)
    assert host.run("if441a") == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--elf", required=True)
    parser.add_argument("--disc", required=True)
    parser.add_argument("--seed", type=int, default=20973)
    args = parser.parse_args()
    digest = hashlib.sha256(open(args.elf, "rb").read()).hexdigest()
    assert digest == ELF_SHA256, digest
    images, objects = {}, {}
    for level in SCAN_LEVELS:
        images[level], objects[level] = load_level(args.disc, level)
    checks = check_static(images, objects)
    host = Host(args.elf, args.seed)
    end_call, notice_call = run_evil(host, images["drunare"])
    run_evil_gates(host, images["drunare"])
    checks += run_knights(host, images["drunare"])
    run_good(host, images["drunarm"])
    low, high = hp_boundary(host, images["drunarm"])
    rallos_call = run_rallos(host, images["drunarm"])
    run_exits(host, images)
    run_hub_view(host, images)
    assert host.seed_now() == args.seed
    assert notice_call == 252 and end_call == 877
    checks += end_call + notice_call + low + high
    print("PASS seed %d checks %d notice-call %d end-call %d hp %d/%d rallos-call %d" % (
        args.seed, checks, notice_call, end_call, low, high, rallos_call))


if __name__ == "__main__":
    main()
