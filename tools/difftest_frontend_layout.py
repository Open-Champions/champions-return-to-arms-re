#!/usr/bin/env python3
"""Compare list draw submissions and first-theme gate to SLUS-20973 v2.00.

Run with an owned executable path. No image, sound, text or game bytes are saved.
The list width callee is stubbed, so frames are their minimum-width calls.
"""
import hashlib
import os
import struct
import sys

sys.path.append(os.path.dirname(__file__))
from ee_emu import EE  # noqa: E402
from ref_frontend_layout import (MENU_SOUND_IDS, TABLES, first_theme_queues,  # noqa: E402
                                 list_geometry, pause_geometry, publisher_logo_sprites)

SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
SEEDS = (20973, 7)


def emulator(path, seed):
    e = EE(path)
    e.mem.auto_map = True
    e.mem.w32(0x404460, seed)
    return e


def draw_list(path, seed, table):
    e = emulator(path, seed)
    e.follow = set()
    e.call(0x1A07C4, 320, 309, table, 0x80446B6A, max_steps=100000)
    anchors = [(c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF)
               for c in e.calls if c.target == 0x181CA0]
    frames = [tuple(x & 0xFFFFFFFF for x in c.args[:6])
              for c in e.calls if c.target == 0x17FBB8]
    return anchors, frames


def theme_queue(path, seed, volume):
    e = emulator(path, seed)
    directory = e.alloc(0xB0)
    name = e.alloc(32)
    e.mem.write(name, b"test_theme.vag\0")
    e.mem.write(directory, b"test_theme.vag\0")
    e.mem.write(directory + 0x50, b"\0")
    e.mem.write(directory + 0x40, struct.pack("<IIHhI", 0x1000, 24000, 1, 0, 0))
    e.mem.write(directory + 0x90, struct.pack("<IIHhI", 0x3000, 0, 0, 0, 0))
    e.stub(0x17377C, ret=directory)  # resource directory lookup
    e.stub(0x1724FC, ret=1)  # CD file lookup
    e.stub(0x3566F0, ret=0)  # driver RPC
    e.stub(0x216690, ret=0)  # channel volume
    e.mem.w32(0x4F8944, volume)
    e.call(0x2110E0, name, 5, max_steps=100000)
    return e.mem.u32(0x876C10 + 2 * 0x1C4 + 0x1C0)


def pause_draw(path, seed):
    e = emulator(path, seed)
    e.follow = {0x1A07C4, 0x3B8534, 0x3B96A8}
    e.call(0x18E334, 0, max_steps=100000)  # open normal offline table
    e.stub(0x217550, ret=-1)  # card is idle; do not close the menu
    e.reset_log()
    e.call(0x18CC08, max_steps=100000)
    flags = tuple(e.mem.u32(0x44F3B8 + i * 16 + 12) for i in range(9))
    anchors = [(c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF)
               for c in e.calls if c.site == 0x1A0E5C and c.target == 0x181CA0]
    frames = [tuple(x & 0xFFFFFFFF for x in c.args[:6])
              for c in e.calls if c.site == 0x1A11BC and c.target == 0x17FBB8]
    colors = [(c.args[1] & 0xFFFFFFFF, c.args[2] & 0xFFFFFFFF)
              for c in e.calls if c.site == 0x18D5E8 and c.target == 0x1800B8]
    return flags, anchors, frames, colors


def logo_draw(path, seed):
    e = emulator(path, seed)
    e.follow = set()
    e.call(0x321640, max_steps=100000)
    lookups = [e.mem.cstr(c.args[1] & 0xFFFFFFFF)
               for c in e.calls if c.target == 0x17365C]
    sprites = [(lookups[i], *(v & 0xFFFFFFFF for v in c.args[1:5]))
               for i, c in enumerate(c for c in e.calls if c.target == 0x17FB68)]
    return sprites


def menu_action(path, seed, state, table, mask):
    e = emulator(path, seed)
    e.follow = {0x1A01D0}
    e.mem.w32(0x4F6B78, state)
    e.mem.w32(0x4F6B7C, table)
    for addr in (0x41BFE0, 0x41BFE4, 0x41BFE8):
        e.mem.w32(addr, mask)
    e.call(0x1E08F0, max_steps=100000)
    ids = [e.mem.cstr(c.args[1] & 0xFFFFFFFF)
           for c in e.calls if c.target == 0x17365C and
           c.site in (0x1A03E8, 0x1E15A4, 0x1E1D6C)]
    sound_calls = [c for c in e.calls if c.target == 0x214230 and
                   0x1A0000 <= c.site < 0x1E2000]
    return e.mem.u32(0x4F6B78), ids, len(sound_calls)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: difftest_frontend_layout.py path/to/SLUS_209.73")
    path = sys.argv[1]
    with open(path, "rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    if digest != SHA256:
        raise SystemExit("wrong executable SHA-256")
    checks = 0
    for seed in SEEDS:
        for name, (table, count, value_rows) in TABLES.items():
            expected_anchors, expected_frame = list_geometry(count, value_rows)
            anchors, frames = draw_list(path, seed, table)
            assert anchors == expected_anchors, (seed, name, anchors, expected_anchors)
            assert frames == [expected_frame], (seed, name, frames, expected_frame)
            checks += 2
        for volume in (0, 0x3D4CCCCC - 1, 0x3D4CCCCC, 0x3F000000):
            queued = theme_queue(path, seed, volume)
            assert queued == int(first_theme_queues(volume)), (seed, volume, queued)
            checks += 1
        flags, anchors, frames, colors = pause_draw(path, seed)
        want_anchors, want_frame = pause_geometry()
        assert flags == (0, 0, 0, 1, 1, 0, 1, 1, 0), (seed, flags)
        assert anchors == want_anchors, (seed, anchors)
        assert frames == [want_frame], (seed, frames)
        assert colors == [(7, 0x80464646)], (seed, colors)
        checks += 4
        assert logo_draw(path, seed) == list(publisher_logo_sprites()), seed
        checks += 1
        for kind, state, table, mask, next_state in (
                ("move", 0, 0x4F6B88, 0x4000, 0),
                ("select", 0, 0x4F6B88, 0x40, 1),
                ("back", 1, 0x4F6BF8, 0x20, 0),
                ("main_cancel", 0, 0x4F6B88, 0x20, 0)):
            actual_state, ids, sounds = menu_action(path, seed, state, table, mask)
            expected = [] if MENU_SOUND_IDS[kind] is None else [MENU_SOUND_IDS[kind]]
            assert (actual_state, ids, sounds) == (next_state, expected, len(expected)), (
                seed, kind, actual_state, ids, sounds)
            checks += 1
    print("PASS frontend list layout and theme gate: %d checks; seeds 20973, 7" % checks)


if __name__ == "__main__":
    main()
