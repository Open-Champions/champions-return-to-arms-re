#!/usr/bin/env python3
"""Exercise frontend art paths on an owned SLUS-20973 v2.00 executable.

No game bytes, images, text, or disassembly are written. Resource lookup and
text rendering callees are stubbed; claims apply to these explicit fixtures.
"""
import hashlib
import sys
from pathlib import Path

from anim_audio_info import lmp_entries
from ee_emu import EE
from ref_frontend_art import (CLASS_FRAMES, CLASS_HELPERS, CREDITS_LINE_COUNTS,
                              CURSOR_LUMP, CURSOR_PIECES, INTRO_RESOURCES,
                              MENU_CURSOR, MOVIE_DRAW_CALLS, MOVIE_SEQUENCE_SIZES,
                              SEEDS, credits_lines, slot_highlight, slot_rows)

SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
UI_IMAGE_TARGETS = {0x17FB68, 0x17365C, 0x1803E0}


def emu(path, seed, follow=()):
    e = EE(path)
    e.mem.auto_map = True
    e.mem.w32(0x404460, seed)
    e.follow = set(follow)
    return e


def class_draw(path, seed, klass):
    e = emu(path, seed, (0x22A968, 0x22A83C))
    e.mem.w8(0x8E2C02, 1)
    e.mem.w32(0x8E2C44, 0x3F800000)
    e.mem.w8(0x4FDBA0, klass)
    e.call(0x225478, max_steps=300000)
    helpers = tuple((c.site, c.target) for c in e.calls
                    if c.target in (0x22A968, 0x22A83C))
    frames = tuple((c.site, *(x & 0xFFFFFFFF for x in c.args[:7]))
                   for c in e.calls if c.target == 0x17C118)
    images = tuple((c.site, c.target) for c in e.calls
                   if c.target in UI_IMAGE_TARGETS)
    return helpers, frames, images


def menu_cursor(path, seed):
    e = emu(path, seed, (0x17FBB8,))
    e.call(0x1A07C4, 320, 309, 0x4F6B88, 0x80446B6A, max_steps=100000)
    calls = tuple((c.site, *(x & 0xFFFFFFFF for x in c.args[:7]))
                  for c in e.calls if c.site == 0x1A1104 and c.target == 0x17C118)
    # ui_drawFrameImpl 0x17c198 names the lump, 0x17c1e8–0x17c2a8
    # format these nine pieces with the style-0 ctile prefix.
    lump = e.mem.cstr(0x534090)
    pieces = tuple(e.mem.cstr(addr).replace("%s", "ctile")
                   for addr in range(0x5340B8, 0x534139, 0x10))
    return calls, lump, pieces


def slot_draw(path, seed, count, selected):
    e = emu(path, seed)
    e.mem.w32(0x88D3DC, 4)
    e.mem.w32(0x4F9238, count)
    e.mem.w32(0x879E24, selected)
    e.mem.w32(0x879E28, selected)
    e.mem.w32(0x879E34, 0x3F800000)
    e.call(0x21C3A4, max_steps=300000)
    rows = tuple((c.site, c.target, c.args[0] & 0xFFFFFFFF,
                  c.args[1] & 0xFFFFFFFF) for c in e.calls
                 if 0x21D930 <= c.site < 0x21DC70 and
                 c.target in (0x181C10, 0x181AA0))
    rects = tuple((c.site, *(x & 0xFFFFFFFF for x in c.args[:6]))
                  for c in e.calls if c.target == 0x17BD30)
    clips = tuple(c.site for c in e.calls if c.target == 0x1803E0)
    return rows, rects, clips


def credit_draw(path, seed, line_count, bold=False):
    e = emu(path, seed)
    e.call(0x223C64, max_steps=100000)
    lump = tuple(e.mem.cstr(c.args[0] & 0xFFFFFFFF) for c in e.calls
                 if c.site == 0x223D10 and c.target == 0x173558)
    for i in range(line_count):
        ptr = e.alloc(32)
        # Authored UTF-16 test tokens only; none come from the disc.
        e.mem.write(ptr, (b"\\\x00b\x00" if bold and i == 0 else b"") +
                    b"A\x00\x00\x00")
        e.mem.w32(0x4FB5E8 + 4 * i, ptr)
    e.mem.w32(0x4FB5E8 + 4 * line_count, 0)
    e.mem.w32(0x4FB5D8, 224)
    e.reset_log()
    e.call(0x223D3C, max_steps=100000)
    positions = tuple((c.site, c.args[0] & 0xFFFFFFFF,
                       c.args[1] & 0xFFFFFFFF) for c in e.calls
                      if c.target == 0x181CA0)
    colours = tuple((c.site, c.args[0] & 0xFFFFFFFF) for c in e.calls
                    if c.target == 0x1802E0)
    return positions, colours, e.mem.u32(0x4FB5D8), lump


def intro_draw(path, seed):
    e = emu(path, seed)
    e.call(0x321788, max_steps=100000)
    intro_calls = tuple((c.site, c.target) for c in e.calls)
    resources = tuple((c.site, e.mem.cstr(c.args[1 if c.site == 0x3217BC else 0]
                                          & 0xFFFFFFFF)) for c in e.calls
                      if c.site in (0x3217BC, 0x3217C8))
    e.reset_log()
    e.call(0x3205EC, max_steps=300000)
    draw = tuple((c.site, c.target, c.args[0] & 0xFFFFFFFF,
                  c.args[1] & 0xFFFFFFFF) for c in e.calls
                 if 0x320D44 <= c.site <= 0x320D90)
    ui = tuple((c.site, c.target) for c in e.calls if c.target in UI_IMAGE_TARGETS)
    return intro_calls, resources, draw, ui


def disc_structure(root):
    """Read only container/header structure, never return resource content."""
    root = Path(root)
    credits_data = (root / "CREDITS.LMP").read_bytes()
    credits = {}
    for name, off, size in lmp_entries(credits_data):
        data = credits_data[off:off + size]
        assert data.startswith(b"\xff\xfe") and data.count(b"\r\x00\n\x00") == data.count(b"\n\x00")
        credits[name] = data.count(b"\n\x00")
    movie_data = (root / "PORKO.LMP").read_bytes()
    sizes = {}
    for name, off, size in lmp_entries(movie_data):
        if name.endswith(".m2v"):
            data = movie_data[off:off + size]
            assert data[:4] == b"\x00\x00\x01\xb3"
            header = int.from_bytes(data[4:7], "big")
            sizes[name] = (header >> 12, header & 0xFFF)
    return credits, sizes


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: difftest_frontend_art.py path/to/SLUS_209.73 [BG/DATA]")
    path = sys.argv[1]
    with open(path, "rb") as f:
        if hashlib.file_digest(f, "sha256").hexdigest() != SHA256:
            raise SystemExit("wrong executable SHA-256")
    checks = 0
    for seed in SEEDS:
        for klass in (0, 1, 2, 5, 11):
            assert class_draw(path, seed, klass) == (CLASS_HELPERS, CLASS_FRAMES, ()), (seed, klass)
            checks += 1
        assert menu_cursor(path, seed) == ((MENU_CURSOR,), CURSOR_LUMP, CURSOR_PIECES), seed
        checks += 1
        for count in (0, 1, 2, 5):
            rows, rects, clips = slot_draw(path, seed, count, 0)
            assert rows == slot_rows(count), (seed, count, rows)
            assert rects == (slot_highlight(0),) and clips == (), (seed, count, rects, clips)
            checks += 2
        for selected in range(5):
            _, rects, clips = slot_draw(path, seed, 5, selected)
            assert rects == (slot_highlight(selected),) and clips == (), (seed, selected)
            checks += 1
        for count in (1, 2, 3):
            positions, colours, next_y, lump = credit_draw(path, seed, count)
            assert positions == credits_lines(224, count), (seed, count, positions)
            assert colours == ((0x224004, 0x20000000),
                               (0x22402C, 0x5E405E5E)) * count, (seed, count, colours)
            assert next_y == 223, (seed, count, next_y)
            assert lump == ("credits.lmp",), (seed, count, lump)
            checks += 4
        positions, colours, _, lump = credit_draw(path, seed, 1, bold=True)
        assert positions == credits_lines(224, 1) and colours == (
            (0x224004, 0x20000000), (0x22402C, 0x5B1A444C)) and lump == ("credits.lmp",), seed
        checks += 1
        intro, resources, movie, ui = intro_draw(path, seed)
        assert intro == ((0x321790, 0x19DD48), (0x3217BC, 0x215C20),
                         (0x3217C8, 0x173558), (0x3217D0, 0x211C18),
                         (0x32180C, 0x320498)), seed
        assert resources == INTRO_RESOURCES, (seed, resources)
        assert movie == MOVIE_DRAW_CALLS and ui == (), (seed, movie, ui)
        checks += 3
    if len(sys.argv) == 3:
        assert disc_structure(sys.argv[2]) == (CREDITS_LINE_COUNTS, MOVIE_SEQUENCE_SIZES)
        checks += 1
    print("PASS frontend art fixtures: %d checks; seeds 20973, 7" % checks)


if __name__ == "__main__":
    main()
