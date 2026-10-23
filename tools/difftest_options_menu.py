#!/usr/bin/env python3
"""Execute options tables and handlers in ee_emu; no private bytes are written."""

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from ee_emu import EE  # noqa: E402
from ref_options_menu import GEOMETRY, ROWS, SLIDER_STEPS, TOGGLE_STEPS  # noqa: E402

SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
SEEDS = (20973, 7)
FRONT = 0x4F6E88
PAUSE = 0x44F218


def fresh(path, seed):
    ee = EE(path)
    ee.mem.auto_map = True
    ee.follow = set()
    ee.mem.w32(0x404460, seed)
    return ee


def list_input(ee, table, row, mask, offset):
    pad = 0x41BFD8
    ee.mem.w32(table + (13 if table == FRONT else 14) * 16 + 4, row)
    ee.mem.w32(pad + offset, mask)
    return ee.call(0x1A01D0, table, pad, 0x1FFFDE0, 0, max_steps=100000)


def check(path, seed):
    count = 0
    for table in (FRONT, PAUSE):
        ee = fresh(path, seed)
        for index, (key, kind, address) in enumerate(ROWS):
            record = table + 16 * index
            assert ee.mem.cstr(ee.mem.u32(record)) == key, (hex(record), key)
            assert ee.mem.u32(record + 4) == kind, (hex(record), kind)
            assert ee.mem.u32(record + 8) == address, (hex(record), address)
            count += 1
        if table == PAUSE:
            record = table + 16 * len(ROWS)
            assert ee.mem.cstr(ee.mem.u32(record)) == "menu_comm"
            assert ee.mem.u32(record + 4) == 0  # action kind
            assert ee.mem.u32(record + 8) == 0  # no direct live value
            count += 1

        ee = fresh(path, seed)
        ee.follow = {0x17FBB8}
        ee.call(0x1A07C4, 320, 238 if table == FRONT else 240,
                table, 0x80446B6A, max_steps=100000)
        anchors = [(c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF)
                   for c in ee.calls if c.target == 0x181CA0]
        frames = [tuple(v & 0xFFFFFFFF for v in c.args[:7])
                  for c in ee.calls if c.target == 0x17C118]
        expected_anchors, expected_frames = GEOMETRY[table]
        assert tuple(anchors) == expected_anchors
        assert tuple(frames) == expected_frames
        count += 2

    for table in (FRONT, PAUSE):
        for row in (0, 1, 2):
            address = ROWS[row][2]
            for start, mask, expected in SLIDER_STEPS:
                ee = fresh(path, seed)
                ee.mem.w32(address, start)
                list_input(ee, table, row, mask, 8)  # pad repeat: left/right
                assert ee.mem.u32(address) == expected, (hex(table), row, hex(start), hex(mask))
                count += 1
        for row in range(4, 13):
            address = ROWS[row][2]
            for start, expected in TOGGLE_STEPS:
                ee = fresh(path, seed)
                ee.mem.w32(address, start)
                list_input(ee, table, row, 0x40, 16)  # pad press: accept
                assert ee.mem.u32(address) == expected, (hex(table), row, start)
                count += 1
        for mask, offset in ((0x2000, 16), (0x8000, 16)):
            ee = fresh(path, seed)
            ee.mem.w32(ROWS[4][2], 0)
            list_input(ee, table, 4, mask, offset)
            assert ee.mem.u32(ROWS[4][2]) == 1
            count += 1

    for row, mask, target in ((3, 0x40, 12), (1, 0x20, 14)):
        ee = fresh(path, seed)
        ee.follow = {0x1A01D0, 0x3B8534, 0x3B96A8}
        ee.mem.w32(0x4F6B78, 11)
        ee.mem.w32(0x4F6B7C, FRONT)
        ee.mem.w32(FRONT + 13 * 16 + 4, row)
        for offset in (8, 12, 16):
            ee.mem.w32(0x41BFD8 + offset, mask)
        ee.call(0x1E08F0, max_steps=100000)
        assert ee.mem.u32(0x4F6B78) == target, (row, hex(mask))
        count += 1

    # The exit choice asks whether to write the option image to card.
    for mask, no_card_save in ((0x40, 0), (0x20, 1)):
        ee = fresh(path, seed)
        ee.follow = {0x1E6650}
        ee.mem.w32(0x4F6B78, 14)
        for offset in (8, 12, 16):
            ee.mem.w32(0x41BFD8 + offset, mask)
        ee.call(0x1E08F0, max_steps=100000)
        commits = [(c.site, tuple(c.args[:3])) for c in ee.calls
                   if c.target == 0x1E6650]
        choice_site = 0x1E0CA4 if mask == 0x40 else 0x1E0CBC
        assert commits == [(0x1E0BAC, (0, 1, 0)),
                           (choice_site, (0, 0, no_card_save))], (hex(mask), commits)
        assert ee.mem.u32(0x4F6B78) == 0, hex(mask)
        saves = [c for c in ee.calls if c.target == 0x217BDC]
        assert len(saves) == (0 if no_card_save else 1), hex(mask)
        count += 3

    # Query has no image side effect; commit copies the changed music scalar.
    ee = fresh(path, seed)
    ee.stub(0x215E78, ret=0)
    ee.mem.w8(0x41B69C, 1)
    ee.call(0x1E6238, -1, max_steps=200000)
    ee.mem.w32(0x4F8944, 0x3F400000)
    before = ee.mem.read(0x4F8F38, 0x2F8)
    queried = ee.call(0x1E6650, 0, 1, 0, max_steps=200000)
    assert queried > 0 and ee.mem.read(0x4F8F38, 0x2F8) == before
    committed = ee.call(0x1E6650, 0, 0, 1, max_steps=200000)
    assert committed == queried and ee.mem.u32(0x4F8F40) == 0x3F400000
    assert ee.call(0x1E6650, 0, 1, 0, max_steps=200000) == 0
    count += 3

    # Every direct option, including chat, participates in config query.
    for row in (*range(3), *range(4, 13)):
        ee = fresh(path, seed)
        ee.stub(0x215E78, ret=0)
        ee.mem.w8(0x41B69C, 1)
        ee.call(0x1E6238, -1, max_steps=200000)
        baseline = ee.call(0x1E6650, 0, 1, 0, max_steps=200000)
        _, kind, address = ROWS[row]
        current = ee.mem.u32(address)
        ee.mem.w32(address, 0x3F400000 if kind == 4 else int(current == 0))
        changed = ee.call(0x1E6650, 0, 1, 0, max_steps=200000)
        assert changed - baseline == 1, row
        count += 1
        if row == 11:
            ee.call(0x1E6650, 0, 0, 1, max_steps=200000)
            assert ee.mem.u32(0x4F8F38 + 0xC4) == 0
            count += 1

    # Pair the five-word config tail with the addressed live globals.
    for address, image_offset in ((0x50391C, 0xC4), (0x505AF0, 0xC8),
                                  (0x505AF4, 0xCC), (0x505B00, 0xD0),
                                  (0x505AFC, 0xD4)):
        ee = fresh(path, seed)
        ee.stub(0x215E78, ret=0)
        ee.mem.w8(0x41B69C, 1)
        ee.call(0x1E6238, -1, max_steps=200000)
        initial = ee.mem.u32(address)
        ee.mem.w32(address, 0 if initial else 1)
        ee.call(0x1E6650, 0, 0, 1, max_steps=200000)
        assert ee.mem.u32(0x4F8F38 + image_offset) == ee.mem.u32(address)
        count += 1
    return count


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: difftest_options_menu.py path/to/SLUS_209.73")
    path = sys.argv[1]
    with open(path, "rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == SHA256
    for seed in SEEDS:
        print("seed %d: %d options checks passed" % (seed, check(path, seed)))


if __name__ == "__main__":
    main()
