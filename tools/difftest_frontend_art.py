#!/usr/bin/env python3
"""Exercise frontend art paths on an owned SLUS-20973 v2.00 executable.

No game bytes, images, text, or disassembly are written. Resource lookup and
text rendering callees are stubbed; claims apply to these explicit fixtures.
"""
import hashlib
import sys
from pathlib import Path

from anim_audio_info import lmp_entries, open_source
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
    # Only the call to ui_drawFrameImpl is recorded. Its formatting code is
    # not followed, so return the literal format strings without a prefix.
    lump = e.mem.cstr(0x534090)
    pieces = tuple(e.mem.cstr(addr)
                   for addr in range(0x5340B8, 0x534139, 0x10))
    return calls, lump, pieces


def slot_draw(path, seed, count, selected, other_selection=0, nonzero_record=True):
    e = emu(path, seed)
    e.mem.w32(0x88D3DC, 4)
    e.mem.w32(0x4F9238, count)
    e.mem.w32(0x879E24, other_selection)
    e.mem.w32(0x879E28, selected)
    e.mem.w32(0x879E34, 0x3F800000)
    # Distinct authored 16-byte records make reads visible in both fixtures.
    # A zero record is a control; its real card-file validity is unknown.
    for row in range(5):
        e.mem.write(0x88D300 + 16 * row,
                    bytes([row + 1 if nonzero_record else 0]) * 16)
    reads = []
    original_load = e.mem.load

    def record_load(addr, size):
        value = original_load(addr, size)
        if 0x88D300 <= addr < 0x88D350:
            reads.append((addr, size, value))
        return value

    e.mem.load = record_load
    e.call(0x21C3A4, max_steps=300000)
    rows = tuple((c.site, c.target, c.args[0] & 0xFFFFFFFF,
                  c.args[1] & 0xFFFFFFFF) for c in e.calls
                 if 0x21D930 <= c.site < 0x21DC70 and
                 c.target in (0x181C10, 0x181AA0))
    rects = tuple((c.site, *(x & 0xFFFFFFFF for x in c.args[:6]))
                  for c in e.calls if c.target == 0x17BD30)
    clips = tuple(c.site for c in e.calls if c.target == 0x1803E0)
    return rows, rects, clips, tuple(reads)


def credit_draw(path, seed, line_count, bold=False, scroll_y=224):
    e = emu(path, seed)
    e.call(0x223C64, max_steps=100000)
    lump = tuple(e.mem.cstr(c.args[0] & 0xFFFFFFFF) for c in e.calls
                 if c.site == 0x223D10 and c.target == 0x173558)
    pointers = []
    for i in range(line_count):
        ptr = e.alloc(32)
        pointers.append(ptr)
        # Authored UTF-16 test tokens only; none come from the disc.
        e.mem.write(ptr, (b"\\\x00b\x00" if bold and i == 0 else b"") +
                    b"A\x00\x00\x00")
        e.mem.w32(0x4FB5E8 + 4 * i, ptr)
    e.mem.w32(0x4FB5E8 + 4 * line_count, 0)
    e.mem.w32(0x4FB5D8, scroll_y)
    e.reset_log()
    e.call(0x223D3C, max_steps=100000)
    positions = tuple((c.site, c.args[0] & 0xFFFFFFFF,
                       c.args[1] & 0xFFFFFFFF) for c in e.calls
                      if c.target == 0x181CA0)
    colours = tuple((c.site, c.args[0] & 0xFFFFFFFF) for c in e.calls
                    if c.target == 0x1802E0)
    text_pointers = tuple((c.site, c.args[2] & 0xFFFFFFFF)
                          for c in e.calls if c.target == 0x181CA0)
    expected_pointers = tuple((site, ptr + (4 if bold and row == 0 else 0))
                              for row, ptr in enumerate(pointers)
                              for site in (0x22401C, 0x224044))
    return positions, colours, e.mem.u32(0x4FB5D8), lump, text_pointers, expected_pointers


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


def utf16_line_count(data):
    """Count CRLF-terminated lines and a possible final unterminated line."""
    assert data.startswith(b"\xff\xfe") and len(data) % 2 == 0
    assert data.count(b"\r\x00\n\x00") == data.count(b"\n\x00")
    return data.count(b"\n\x00") + int(len(data) > 2 and not data.endswith(b"\n\x00"))


def disc_structure(root):
    """Read only container/header structure, never return resource content."""
    root = Path(root)
    if root.is_file() and root.suffix.lower() == ".iso":
        credits_data = open_source(f"{root}::/BG/DATA/CREDITS.LMP").bytes()
        movie_data = open_source(f"{root}::/BG/DATA/PORKO.LMP").bytes()
    else:
        credits_data = (root / "CREDITS.LMP").read_bytes()
        movie_data = (root / "PORKO.LMP").read_bytes()
    credits = {}
    for name, off, size in lmp_entries(credits_data):
        data = credits_data[off:off + size]
        credits[name] = utf16_line_count(data)
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
        for count in range(7):
            rows, rects, clips, reads = slot_draw(path, seed, count, 0)
            assert rows == slot_rows(count), (seed, count, rows)
            assert rects == (slot_highlight(0),) and clips == (), (seed, count, rects, clips)
            expected_read_rows = range(min(count, 5))
            for row in expected_read_rows:
                for off in (2, 3, 5, 6, 7):
                    assert (0x88D300 + 16 * row + off, 1, row + 1) in reads, (seed, count, row, off, reads)
            if count == 0:
                assert reads == (), (seed, count, reads)
            checks += 3
        rows, rects, clips, reads = slot_draw(path, seed, 1, 0, nonzero_record=False)
        assert rows == slot_rows(1) and rects == (slot_highlight(0),) and clips == (), seed
        assert (0x88D302, 1, 0) in reads, (seed, reads)
        checks += 2
        for selected in range(6):
            _, rects, clips, _ = slot_draw(path, seed, 1, selected)
            assert rects == (slot_highlight(selected),) and clips == (), (seed, selected)
            checks += 1
        _, rects, _, _ = slot_draw(path, seed, 5, 0, other_selection=3)
        assert rects == (slot_highlight(0),), (seed, rects)
        checks += 1
        for count in (1, 2, 3):
            positions, colours, next_y, lump, pointers, expected_pointers = credit_draw(path, seed, count)
            assert positions == credits_lines(224, count), (seed, count, positions)
            assert colours == ((0x224004, 0x20000000),
                               (0x22402C, 0x5E405E5E)) * count, (seed, count, colours)
            assert next_y == 223, (seed, count, next_y)
            assert lump == ("credits.lmp",), (seed, count, lump)
            assert pointers == expected_pointers, (seed, count, pointers)
            checks += 5
        positions, colours, _, lump, pointers, expected_pointers = credit_draw(path, seed, 1, bold=True)
        assert positions == credits_lines(224, 1) and colours == (
            (0x224004, 0x20000000), (0x22402C, 0x5B1A444C)) and lump == ("credits.lmp",), seed
        assert pointers == expected_pointers, (seed, pointers)
        checks += 2
        positions, colours, next_y, _, pointers, expected_pointers = credit_draw(
            path, seed, 2, scroll_y=400)
        assert positions == credits_lines(400, 2) and colours == (
            (0x224004, 0x07000000), (0x22402C, 0x14405E5E),
            (0x224004, 0x02000000), (0x22402C, 0x06405E5E)), (seed, positions, colours)
        assert next_y == 399 and pointers == expected_pointers, seed
        checks += 3
        assert utf16_line_count(b"\xff\xfeA\x00\r\x00\n\x00B\x00") == 2, seed
        assert utf16_line_count(b"\xff\xfeA\x00\r\x00\n\x00") == 1, seed
        checks += 2
        intro, resources, movie, ui = intro_draw(path, seed)
        assert intro == ((0x321790, 0x19DD48), (0x3217BC, 0x215C20),
                         (0x3217C8, 0x173558), (0x3217D0, 0x211C18),
                         (0x32180C, 0x320498)), seed
        assert resources == INTRO_RESOURCES, (seed, resources)
        assert movie == MOVIE_DRAW_CALLS and ui == (), (seed, movie, ui)
        assert all(target not in (0x3202C0, 0x320238) for _, target in intro), (seed, intro)
        checks += 4
    if len(sys.argv) == 3:
        assert disc_structure(sys.argv[2]) == (CREDITS_LINE_COUNTS, MOVIE_SEQUENCE_SIZES)
        checks += 1
    print("PASS frontend art fixtures: %d checks; seeds 20973, 7" % checks)


if __name__ == "__main__":
    main()
