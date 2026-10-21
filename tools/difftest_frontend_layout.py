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
from ref_frontend_layout import TABLES, first_theme_queues, list_geometry  # noqa: E402

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
    print("PASS frontend list layout and theme gate: %d checks; seeds 20973, 7" % checks)


if __name__ == "__main__":
    main()
