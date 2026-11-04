#!/usr/bin/env python3
"""Quest-list order, mission-complete separation, page text calls, and save/restore.

The original functions run in tools/ee_emu.py. Keys are synthetic. Disc checks
count script events and do not store quest title text.
"""
import argparse
import hashlib
import mmap
import os
import struct
import sys

# tools/dis.py shadows the stdlib module. Import the real one before this directory is searched.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [entry for entry in sys.path if os.path.abspath(entry or ".") != _HERE]
import dis  # noqa: E402,F401
sys.path.insert(0, _HERE)

from anim_audio_info import gob_entries, iso_files, lmp_entries
from ee_emu import EE
import difftest_quest_log as QLOG
import ref_quest_log as R
import scr

ELF_SHA256 = QLOG.ELF_SHA256
PLAYER = 0x4D8AF0
STRIDE = 0x4C30
QUEST = 0x41D0
COUNT = 0x43D0
SPAN = 0x204
MISSIONS = 0x4BBF
MEDALS = 0x4C0D
NUM = 0x4D8AE0
DIFF = 0x4F719C
SEED = 0x404464
COSMETIC = 0x404460
MEDAL_PLAYER = 0x4F7148
SAVED_FLAG = 0x4F85C0
ADD = 0x1D386C
REMOVE = 0x1D3968
CLEAR = 0x1D3ADC
COMPLETE = 0x1BF770
SAVE_PLAYER = 0x1EC720
RESTORE_PLAYER = 0x1EB6F8
COPY = 0x21837C
PAGE = 0x1D1DB8
LOOKUP = 0x173C84
BEGIN = 0x1800B8
CLIP = 0x1803E0
INK = 0x1802E0
WRAP = 0x181280
END = 0x180500
CENTER = 0x181CA0
SAVE_BUILD = 0x221914
SAVE_LOAD = 0x221D60
SAVE_IMAGE = 0x895580
SAVE_QUEST = 0x320 + 0x0E + QUEST
# Host services around the player-record copy. Snapshot 0x216c80 and fixup 0x216ea8 stay real.
SAVE_STUBS = (
    (0x203918, 0xC4), (0x203A20, 0xC4), (0x27DCF4, 0x1E4), (0x27DD30, 0x1E4),
    (0x21777C, 0), (0x217D30, 0), (0x217EDC, 0), (0x1EDA08, 0), (0x1ED728, 0),
    (0x2180A8, 0),
)


def field_bytes(mem, slot):
    base = PLAYER + slot * STRIDE + QUEST
    return mem.read(base, SPAN)


def read_record(mem, slot):
    rec = R.blank_record()
    rec["count"] = mem.s32(PLAYER + slot * STRIDE + COUNT)
    raw = field_bytes(mem, slot)
    for index in range(R.SLOTS):
        rec["titles"][index] = raw[index * R.ENTRY:index * R.ENTRY + R.FIELD]
        rec["bodies"][index] = raw[index * R.ENTRY + R.FIELD:(index + 1) * R.ENTRY]
    return rec


def plant(mem, slot, titles, bodies, tail=b"\xee"):
    rec = PLAYER + slot * STRIDE
    mem.w32(rec + COUNT, len(titles))
    for index, (title, body) in enumerate(zip(titles, bodies)):
        mem.write(rec + QUEST + index * R.ENTRY, R.write_cstr(tail * R.FIELD, title))
        mem.write(rec + QUEST + index * R.ENTRY + R.FIELD, R.write_cstr(tail * R.FIELD, body))


def put_string(ee, text):
    addr = ee.alloc(32)
    ee.mem.write(addr, text.encode("latin1") + b"\0")
    return addr


def fresh(elf, seed):
    ee = EE(elf)
    ee.mem.w32(SEED, seed)
    ee.mem.w32(COSMETIC, seed ^ 0x55555555)
    ee.mem.w32(NUM, 1)
    ee.mem.w32(DIFF, 1)
    return ee


def check(cond, text):
    if not cond:
        raise AssertionError(text)


def check_transitions(elf, seed):
    ee = fresh(elf, seed)
    records = [R.blank_record() for _ in range(4)]
    plant(ee.mem, 2, ["Z0", "Z1", "Z2"], ["z0", "z1", "z2"], tail=b"\xab")
    records[2] = read_record(ee.mem, 2)
    ee.mem.w32(NUM, 2)
    pairs = (("A", "a"), ("B", "b"), ("A", "again"), ("C", "c"))
    for title, body in pairs:
        ee.call(ADD, put_string(ee, title), put_string(ee, body))
        R.quest_add(records, 2, title, body)
    for slot in range(3):
        check(read_record(ee.mem, slot) == records[slot], "add slot %d" % slot)
    full = fresh(elf, seed)
    full.mem.w32(NUM, 2)
    plant(full.mem, 0, ["F%d" % i for i in range(8)], ["f%d" % i for i in range(8)])
    before = field_bytes(full.mem, 0)
    other = field_bytes(full.mem, 1)
    full.call(ADD, put_string(full, "Late"), put_string(full, "no"))
    check(field_bytes(full.mem, 0) == before and field_bytes(full.mem, 1) == other, "full list")

    ee.call(REMOVE, put_string(ee, "B"))
    R.quest_remove(records, 2, "B")
    for slot in range(3):
        check(read_record(ee.mem, slot) == records[slot], "remove slot %d" % slot)
    dup = fresh(elf, seed)
    dup.mem.w32(NUM, 1)
    plant(dup.mem, 0, ["A", "B", "A"], ["a", "b", "a2"])
    model = [read_record(dup.mem, 0)] + [R.blank_record() for _ in range(3)]
    dup.call(REMOVE, put_string(dup, "A"))
    R.quest_remove(model, 1, "A")
    check(read_record(dup.mem, 0) == model[0], "duplicate remove")

    span = field_bytes(ee.mem, 0)
    ee.call(COMPLETE, 1, 1, -1)
    check(field_bytes(ee.mem, 0) == span, "complete rewrote the list")
    for slot in range(4):
        byte = ee.mem.u8(PLAYER + slot * STRIDE + MISSIONS + 13 + 1)
        check(byte == 2, "complete bit slot %d is %d" % (slot, byte))
    ee.call(COMPLETE, 1, 1, 0)
    for slot in range(4):
        check(ee.mem.u8(PLAYER + slot * STRIDE + MISSIONS + 13 + 1) == 0, "clear complete")
    ee.call(COMPLETE, 1, 13, -1)
    check(all(ee.mem.u8(PLAYER + slot * STRIDE + MISSIONS + index) == 0
              for slot in range(4) for index in range(13 * 5)), "mission 13 wrote a byte")
    check(field_bytes(ee.mem, 0) == span, "mission 13 touched the list")

    ee.call(CLEAR)
    R.quest_clear(records, 2)
    for slot in range(3):
        check(read_record(ee.mem, slot) == records[slot], "clear slot %d" % slot)
    check(ee.mem.u32(SEED) == seed and ee.mem.u32(COSMETIC) == (seed ^ 0x55555555), "seed moved")
    return 4


def check_page(elf, seed):
    cases = 0
    for count, returns in ((0, []), (1, [0, 0]), (2, [1, 0, 3, 2])):
        ee = fresh(elf, seed)
        ee.follow = set()
        ee.mem.w32(R.FONT_WORD, 0x11111111)
        panel = ee.alloc(0x74)
        ee.mem.w32(panel + 0x50, 4)
        titles = ["Q%d" % i for i in range(count)]
        bodies = ["B%d" % i for i in range(count)]
        if count:
            plant(ee.mem, 0, titles, bodies)
        before = field_bytes(ee.mem, 0)
        pointers = {}
        sequence = iter(returns)

        def lookup(emu):
            key = emu.mem.cstr(emu.r[4] & 0xFFFFFFFF, 32)
            addr = pointers.get(key)
            if addr is None:
                addr = emu.alloc(8)
                emu.mem.w16(addr, 0x41)
                emu.mem.w16(addr + 2, 0)
                pointers[key] = addr
            return addr

        def wrap(emu):
            return next(sequence)

        ee.stub(LOOKUP, function=lookup, name="text_lookup")
        ee.stub(WRAP, function=wrap, name="text_drawWrapped")
        ee.call(PAGE, 0, 1, 0x34000000, panel, max_steps=200000)
        check(field_bytes(ee.mem, 0) == before, "page wrote the list")
        check(ee.mem.u32(R.FONT_WORD) == 0x11111111, "page wrote the font word")
        text = [(c.target, c.site & 0xFFFFFFFF, tuple(v & 0xFFFFFFFF for v in c.args[:8]))
                for c in ee.calls if c.target in (BEGIN, CLIP, INK, LOOKUP, WRAP, END, CENTER)]
        if count == 0:
            check([item[0] for item in text] == [BEGIN, LOOKUP, CENTER, END], "empty order")
            check(text[0][1] == 0x1D27D0 and text[0][2][:4] == (
                0x11111111, 6, R.TITLE_COLOUR, 0xFFFFFFFF), "empty begin")
            check(text[1][1] == 0x1D27DC and ee.mem.cstr(text[1][2][0], 16) == "NoQuests", "empty key")
            check(text[2][1] == 0x1D2800 and text[2][2][:4] == (
                160, 224, pointers["NoQuests"], 1000000), "empty draw")
            check(text[3][1] == 0x1D2808, "empty end")
        else:
            pairs = list(zip(returns[0::2], returns[1::2]))
            ys = R.row_positions([a for a, _b in pairs], [b for _a, b in pairs])
            expect = []
            for index, (title_y, body_y) in enumerate(ys):
                title = pointers["Q%d" % index]
                body = pointers["B%d" % index]
                expect.extend([
                    (BEGIN, 0x1D26AC, (0x11111111, 6, R.TITLE_COLOUR, 0xFFFFFFFF)),
                    (CLIP, 0x1D26D0, (0, 119, 320, 440)),
                    (INK, 0x1D26E8, (R.TITLE_COLOUR, 0xFFFFFFFF)),
                    (LOOKUP, 0x1D2708, ("Q%d" % index,)),
                    (WRAP, 0x1D272C, (24, title_y, title, 288, 82, 418, 21)),
                    (INK, 0x1D2744, (R.BODY_COLOUR, 0xFFFFFFFF)),
                    (LOOKUP, 0x1D275C, ("B%d" % index,)),
                    (WRAP, 0x1D2784, (24, body_y, body, 288, 82, 418, 21)),
                    (END, 0x1D278C, ()),
                ])
            got = []
            for target, site, args in text:
                if target == LOOKUP:
                    got.append((target, site, (ee.mem.cstr(args[0], 16),)))
                elif target == INK:
                    got.append((target, site, args[:2]))
                elif target == END:
                    got.append((target, site, ()))
                elif target == WRAP:
                    got.append((target, site, args[:7]))
                else:
                    got.append((target, site, args[:4]))
            check(got == expect, "page sequence %d %s" % (count, got))
        cases += 1
    return cases


def check_player_restore(elf, seed):
    ee = fresh(elf, seed)
    ee.mem.w32(NUM, 2)
    ee.mem.w8(MEDAL_PLAYER, 0)
    plant(ee.mem, 0, ["Keep"], ["Body"])
    plant(ee.mem, 1, ["Other"], ["Side"])
    ee.mem.w8(PLAYER + MEDALS, 9)
    copy = ee.call(COPY, 0) & 0xFFFFFFFF
    ee.call(SAVE_PLAYER)
    check(ee.mem.u32(SAVED_FLAG) == 1, "save flag")
    check(ee.mem.read(copy + QUEST, SPAN) == field_bytes(ee.mem, 0), "copy span")
    ee.mem.w32(PLAYER + COUNT, 0)
    ee.mem.write(PLAYER + QUEST, b"Live\0")
    ee.mem.w8(PLAYER + MEDALS, 4)
    other = field_bytes(ee.mem, 1)
    ee.call(RESTORE_PLAYER)
    check(ee.mem.s32(PLAYER + COUNT) == 1, "restored count")
    check(ee.mem.cstr(PLAYER + QUEST, 16) == "Keep", "restored title")
    check(ee.mem.cstr(PLAYER + QUEST + R.FIELD, 16) == "Body", "restored body")
    check(ee.mem.u8(PLAYER + MEDALS) == 4, "medal was restored")
    check(field_bytes(ee.mem, 1) == other, "other player")
    check(ee.mem.u32(SAVED_FLAG) == 0, "restore flag")
    check(ee.mem.u32(SEED) == seed, "restore seed")
    return 1


def check_card(elf, seed):
    """Original save_build/save_load. Camera, gates, act lookup and the level store are stubbed."""
    ee = fresh(elf, seed)
    ee.record_calls = False
    ee.record_writes = False
    obj = ee.alloc(0x80)
    ee.mem.w32(PLAYER + 0x43D8, obj)
    plant(ee.mem, 0, ["Q0"], ["B0"])
    ee.mem.w8(PLAYER + MISSIONS + 14, 2)
    ee.mem.write(0x41B721, b"crypt\0")
    ee.mem.w8(0x41B771, 0)
    ee.mem.w8(0x4F85C5, 0)
    ee.mem.w32(0x88D3D4, 0)
    ee.mem.write(SAVE_IMAGE, bytes(0x4BC78))
    for addr, ret in SAVE_STUBS:
        ee.stub(addr, ret=ret)
    live = field_bytes(ee.mem, 0)
    ee.call(SAVE_BUILD, 0, 0, max_steps=3000000)
    check(ee.mem.read(SAVE_IMAGE + SAVE_QUEST, SPAN) == live, "image quest span")
    check(ee.mem.u8(SAVE_IMAGE + 0x320 + 0x0E + MISSIONS + 14) == 2, "image mission byte")
    ee.mem.w32(PLAYER + COUNT, 4)
    ee.mem.write(PLAYER + QUEST, b"ZZ\0")
    ee.mem.w8(PLAYER + MISSIONS + 14, 0)
    ee.call(SAVE_LOAD, max_steps=3000000)
    check(field_bytes(ee.mem, 0) == live, "load quest span")
    check(ee.mem.u8(PLAYER + MISSIONS + 14) == 2, "load mission byte")
    check(ee.mem.u32(PLAYER + 0x43D8) == 0, "load object pointer")
    check(ee.mem.u32(SEED) == seed, "card seed")
    return 1


def walk_calls(image):
    parsed = scr.parse(image)
    start, end = parsed["code"]
    words = struct.unpack_from("<%dI" % ((end - start) // 4), image, start)
    natives = [name for _, name in parsed["externals"]]
    entry_at = {offset: name for offset, name in parsed["internals"]}
    entry = None
    calls = []
    index = 0
    while index < len(words):
        offset = index * 4
        if offset in entry_at:
            entry = entry_at[offset]
        op = words[index]
        if op == 0x7D:
            index += 3
            continue
        if op == 0x7B:
            calls.append((entry, offset, natives[words[index + 1]]))
            index += 2
            continue
        if op in (0x27, 0x28, 0x2C):
            index += 2
            continue
        if op in scr.OPS:
            index += 1 + scr.OPS[op][1]
            continue
        index += 1 if op in scr.NO_OPERAND else 2
    return calls


def level_script(disc, files, level):
    return QLOG.disc_script(disc, files, level)


def check_scripts(disc, files):
    counts = {}
    files_seen = set()
    for path, entry in files.items():
        if not path.upper().endswith(".GOB"):
            continue
        offset, size = entry[:2]
        gob = disc[offset:offset + size]
        for name, at, gob_size in gob_entries(gob):
            if not name.lower().endswith(".lmp"):
                continue
            lump = gob[at:at + gob_size]
            try:
                entries = lmp_entries(lump)
            except Exception:
                continue
            for fname, fat, fsize in entries:
                if fname.lower() != "script.scr":
                    continue
                level = name[:-4].lower()
                calls = walk_calls(lump[fat:fat + fsize])
                files_seen.add(level)
                for _entry, _off, native in calls:
                    if native in ("addQuest", "removeQuest"):
                        counts.setdefault(level, {"addQuest": 0, "removeQuest": 0})
                        counts[level][native] += 1
    add = sum(row["addQuest"] for row in counts.values())
    remove = sum(row["removeQuest"] for row in counts.values())
    check(add == 43 and remove == 30, "census %d %d" % (add, remove))
    check(sum(1 for row in counts.values() if row["addQuest"]) == 20, "add files")
    check(sum(1 for row in counts.values() if row["removeQuest"]) == 19, "remove files")

    hub_image = level_script(disc, files, "hub")
    hub = QLOG.ScriptCheck(hub_image)
    hub_calls = walk_calls(hub_image)
    by_offset = {}
    for name, offset in hub.entries.items():
        by_offset[offset] = name
    for entry, start in (("setMissic270", 0x07B0), ("setMissid125", 0x07FC)):
        natives = [native for owner, _off, native in hub_calls if owner == entry]
        check("setMissionAvailable" in natives and "addQuest" not in natives
              and "removeQuest" not in natives, entry)
        check(hub.entries[entry] == start, entry)

    def owner_at(offset):
        owner = None
        for start in sorted(by_offset):
            if start <= offset:
                owner = by_offset[start]
            else:
                break
        return owner

    for offset in (0x1E68, 0x1EE8):
        natives = [native for owner, _off, native in hub_calls if owner == owner_at(offset)]
        check("addQuest" in natives, "hub journal writer %x" % offset)

    for level in ("strife", "drundar"):
        calls = walk_calls(level_script(disc, files, level))
        natives = [native for owner, _off, native in calls if owner == "exitzone"]
        check("grantMission" in natives and "addQuest" not in natives and "removeQuest" not in natives, level)
    innovat = walk_calls(level_script(disc, files, "innovat1"))
    check(any(native == "removeQuest" for _o, _f, native in innovat), "innovat1 remove")
    check(any(native == "addQuest" for _o, _f, native in innovat), "innovat1 add")
    check(len(files_seen) >= 20, "scripts")
    return add + remove


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--elf", required=True)
    parser.add_argument("--iso", required=True)
    args = parser.parse_args()
    with open(args.elf, "rb") as handle:
        check(hashlib.file_digest(handle, "sha256").hexdigest() == ELF_SHA256, "elf")
    total = 0
    for seed in (20973, 7):
        total += check_transitions(args.elf, seed)
        total += check_page(args.elf, seed)
        total += check_player_restore(args.elf, seed)
        total += check_card(args.elf, seed)
    with open(args.iso, "rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as disc:
        files = iso_files(disc)
        scripts = check_scripts(disc, files)
    print("PASS quest-log-state: %d original cases across two seeds, %d journal script calls" % (total, scripts))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("FAIL", type(exc).__name__, exc)
        sys.exit(1)
