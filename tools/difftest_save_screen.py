#!/usr/bin/env python3
"""Run bounded save/load screen fixtures in ee_emu on the pinned v2.00 ELF.

Usage: python3 tools/difftest_save_screen.py path/to/SLUS_209.73 [path/to/disc.iso]
       [--completed-slot path/to/BASLUS-20973_slot0]
No original file, card record, text, texture, or capture is written.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from ee_emu import EE  # noqa: E402
import ref_save_screen as R  # noqa: E402

SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
SLOT_SHA256 = "c969195418643f79e31ddc493ad30c3cd5c24802be0aa34614fb584299027796"


def fixture(path, seed, state=4, count=2, selected=0, edge=0, debug=0, mode=3):
    e = EE(path)
    e.mem.auto_map = True
    e.follow = set()
    e.mem.w32(0x404460, seed)
    e.mem.w32(0x88D3DC, state)
    e.mem.w32(0x88D3A0, mode)         # 3 save, 4 load
    e.mem.w32(0x4F9238, count)
    e.mem.w32(0x88D3C4, 10)           # no card-op completion in this call
    e.mem.w32(0x8E11F8, 0x7F)
    e.mem.w32(0x8E11FC, 8)            # list has finished fading in
    e.mem.w32(0x879E28, selected)
    e.mem.w32(0x4028DC, edge)        # raw-pad edge
    e.mem.w32(0x4028E0, edge)        # raw-pad repeat
    e.mem.w32(0x41BFB8, 0x20)        # cancel mask
    e.mem.w32(0x41BFBC, 0x40)        # confirm mask
    e.mem.w32(0x4F7104, 0xF1F1F1F1) # small-font pointer sentinel
    e.mem.w8(0x4F8EE0, debug)
    for row in range(5):
        e.mem.write(0x88D300 + 16 * row,
                    bytes((0x12, 0, 0x25, 0x10, 0, 0x10, 0x08, 0x26)) + bytes(8))
        header = 0x8E1200 + 112 * row
        e.mem.w16(header + 0x6A, 2)
        e.mem.w32(header + 0x64, 3661)
        e.mem.w8(header + 0x6C, 2)
    return e


def u32s(call, count):
    return tuple(arg & 0xFFFFFFFF for arg in call.args[:count])


def layout(path, seed, count, selected, debug, mode=3):
    e = fixture(path, seed, count=count, selected=selected, debug=debug, mode=mode)
    e.call(0x21C3A4, max_steps=300000)
    rows = tuple((c.site, c.target, *u32s(c, 2)) for c in e.calls
                 if 0x21D930 <= c.site < 0x21DC70 and
                 c.target in (0x181AA0, 0x181C10))
    rects = tuple((c.site, *u32s(c, 6)) for c in e.calls if c.target == 0x17BD30)
    frames = tuple((c.site, *u32s(c, 8)) for c in e.calls if c.target == 0x17FBB8)
    fonts = tuple((c.site, *u32s(c, 3)) for c in e.calls if c.target == 0x1800B8)
    labels = tuple((c.site, e.mem.cstr(c.args[0] & 0xFFFFFFFF))
                   for c in e.calls if c.target == 0x173C84 and
                   c.site in (0x21DCE4, 0x21DD10, 0x21DD48))
    preview = tuple((c.site, *u32s(c, 2)) for c in e.calls
                    if c.site in (0x21DD00, 0x21DD28, 0x21DD60,
                                  0x21E0F0, 0x21E208, 0x21E2C0))
    return e, rows, rects, frames, fonts, labels, preview


def action(path, seed, state, edge):
    e = fixture(path, seed, state=state, edge=edge)
    e.call(0x21C3A4, max_steps=300000)
    return (e.mem.u32(0x88D3DC), e.mem.u32(0x879E24), e.mem.u32(0x88D400)), e


def outer_route(path, seed, entry, browser_ret=None, slot_ret=None):
    e = EE(path)
    e.mem.auto_map = True
    e.follow = set()
    e.mem.w32(0x404460, seed)
    if browser_ret is not None:
        e.stub(0x219B90, ret=browser_ret)
    if slot_ret is not None:
        e.stub(0x21C3A4, ret=slot_ret)
    e.call(entry, max_steps=300000)
    return tuple((c.site, c.target) for c in e.calls
                 if c.target in (0x219B90, 0x21C3A4))


def disc_tiles(iso):
    from anim_audio_info import lmp_entries, open_source
    data = open_source(iso + "::/BG/DATA/INTERFAC.LMP").bytes()
    return {name: struct.unpack_from("<2H", data, off)
            for name, off, _ in lmp_entries(data) if name.startswith("tile")}


def frame_expansion(path, seed):
    e = fixture(path, seed, count=1)
    e.follow = {0x17FBB8}  # follow the wrapper, stop before asset lookup/GPU work
    e.call(0x21C3A4, max_steps=300000)
    calls = tuple((c.site, *u32s(c, 8)) for c in e.calls if c.target == 0x17C118)
    names = tuple(e.mem.cstr(addr) for addr in (0x534090, 0x5340A0, 0x5340A8,
                                                0x5340B0))
    return calls, names


def frame_tiles(path, seed):
    e = fixture(path, seed, count=1)
    e.follow = {0x17FBB8, 0x17C118}
    lump = e.alloc(16)
    e.stub(0x173558, ret=lump)
    objects = {}
    for width, height in ((32, 32), (320, 224)):
        header = e.alloc(16)
        e.mem.w16(header, width)
        e.mem.w16(header + 2, height)
        obj = e.alloc(16)
        e.mem.w32(obj + 4, header)
        objects[width] = obj

    def format_name(emu):
        dst, pattern, prefix = (emu.r[i] & 0xFFFFFFFF for i in (4, 5, 6))
        fmt = emu.mem.cstr(pattern)
        if fmt.startswith("%s") and fmt.endswith(".tex"):
            name = fmt % emu.mem.cstr(prefix)
            emu.mem.write(dst, name.encode("ascii") + b"\0")
            return len(name)
        return 0

    names = []

    def lookup(emu):
        name = emu.mem.cstr(emu.r[5] & 0xFFFFFFFF)
        names.append(name)
        return objects[320 if name == "tilecenter.tex" else 32]

    e.stub(0x3B7EF0, function=format_name)
    e.stub(0x171DE4, function=lookup)
    e.call(0x21C3A4, max_steps=1000000)
    anchors = tuple((c.site, *u32s(c, 3)[1:3]) for c in e.calls
                    if c.target in (0x17B590, 0x17B8B0))
    return anchors, tuple(names)


def prompt(path, seed, state):
    e = fixture(path, seed, state=state)
    e.call(0x21C3A4, max_steps=300000)
    keys = tuple((c.site, e.mem.cstr(c.args[0] & 0xFFFFFFFF)) for c in e.calls
                 if c.target == 0x173C84 and c.site in
                 {site for site, _ in R.PROMPT_KEYS[state]})
    anchors = tuple((c.site, *u32s(c, 2)) for c in e.calls
                    if c.target in (0x181CA0, 0x181530) and c.site in
                    {site for site, _, _ in R.PROMPT_ANCHORS[state]})
    return keys, anchors


def row_fields(path, seed):
    e = fixture(path, seed, count=1, debug=1)
    reads = set()
    original_load = e.mem.load

    def tracked_load(addr, size):
        value = original_load(addr, size)
        if 0x8E1200 <= addr < 0x8E1270:
            reads.add((addr, size))
        return value

    e.mem.load = tracked_load
    e.call(0x21C3A4, max_steps=300000)
    by_site = {c.site: c for c in e.calls}
    return (by_site[0x21DA74].args[0] & 0xFFFFFFFF,
            u32s(by_site[0x21DB0C], 5)[2:5],
            (by_site[0x21DBCC].args[2] & 0xFFFFFFFF,
             by_site[0x21DBCC].args[4] & 0xFFFFFFFF),
            reads)


def indexed_rows(path, seed):
    """Keep both scroll words settled and distinguish every cached row."""
    e = fixture(path, seed, count=8, selected=2)
    e.mem.w32(0x879E2C, 2)
    e.mem.w32(0x879E30, 2)
    for index in range(8):
        e.mem.write(0x88D300 + 16 * index,
                    bytes((0, 0, 0x20 + index, 0x01 + index, 0,
                           0x10 + index, 0x11, 0x26)) + bytes(8))
        e.mem.w16(0x8E1200 + 112 * index + 0x6A, index + 1)
    e.call(0x21C3A4, max_steps=300000)
    numbers = tuple((e.mem.cstr(c.args[1] & 0xFFFFFFFF),
                     c.args[2] & 0xFFFFFFFF, c.args[0] & 0xFFFFFFFF)
                    for c in e.calls if c.site == 0x21D94C)
    number_draws = tuple((c.args[0] & 0xFFFFFFFF,
                          c.args[1] & 0xFFFFFFFF, c.args[2] & 0xFFFFFFFF)
                         for c in e.calls if c.site == 0x21D99C)
    headers = tuple(c.args[0] & 0xFFFFFFFF for c in e.calls if c.site == 0x21DA74)
    dates = tuple(u32s(c, 5)[2:5] for c in e.calls if c.site == 0x21DB0C)
    clocks = tuple((c.args[2] & 0xFFFFFFFF, c.args[4] & 0xFFFFFFFF,
                    c.args[5] & 0xFFFFFFFF)
                   for c in e.calls if c.site == 0x21DBCC)
    return e.mem.u32(0x879E2C), numbers, number_draws, headers, dates, clocks


def date_boundary(path, seed):
    """Single-digit BCD fields expose the original date format and padding."""
    e = fixture(path, seed, count=1)
    e.mem.w8(0x88D306, 0x01)
    e.mem.w8(0x88D305, 0x09)
    e.call(0x21C3A4, max_steps=300000)
    c = next(c for c in e.calls if c.site == 0x21DB0C)
    return e.mem.cstr(c.args[1] & 0xFFFFFFFF), u32s(c, 5)[2:5]


def completed_slot_header(path):
    """Read only a hash-pinned existing card record; never write its bytes."""
    with open(path, "rb") as source:
        record = source.read()
    assert len(record) == 310392, (path, len(record))
    assert hashlib.sha256(record).hexdigest() == SLOT_SHA256, path
    header = record[:0x70]
    assert (struct.unpack_from("<I", header, 0x64)[0],
            struct.unpack_from("<H", header, 0x6A)[0],
            header[0x6C]) == (59, 1, 1), path
    return header


def completed_preview(path, seed, header, debug):
    e = fixture(path, seed, count=1, debug=debug)
    e.mem.write(0x8E1200, header)
    e.call(0x21C3A4, max_steps=300000)
    by_site = {c.site: c for c in e.calls}
    keys = {c.site: e.mem.cstr(c.args[0] & 0xFFFFFFFF)
            for c in e.calls if c.target == 0x173C84 and
            c.site in (0x21DD48, 0x21DFA8, 0x21E258)}
    return by_site, keys


def clock_boundary(path, seed, hour, minute):
    e = fixture(path, seed, count=1)
    e.mem.w8(0x88D303, hour)
    e.mem.w8(0x88D302, minute)
    e.call(0x21C3A4, max_steps=300000)
    c = next(c for c in e.calls if c.site == 0x21DBCC)
    return (e.mem.cstr(c.args[1] & 0xFFFFFFFF),
            c.args[2] & 0xFFFFFFFF,
            e.mem.cstr(c.args[3] & 0xFFFFFFFF),
            c.args[4] & 0xFFFFFFFF,
            e.mem.cstr(c.args[5] & 0xFFFFFFFF))


def main(argv):
    args = argv[1:]
    slot_path = None
    if "--completed-slot" in args:
        assert args.index("--completed-slot") == len(args) - 2, __doc__
        slot_path = args[-1]
        args = args[:-2]
    if len(args) not in (1, 2):
        raise SystemExit(__doc__)
    path = args[0]
    with open(path, "rb") as source:
        assert hashlib.file_digest(source, "sha256").hexdigest() == SHA256
    checks = 0
    slot_header = completed_slot_header(slot_path) if slot_path else None
    for seed in R.SEEDS:
        scroll, numbers, number_draws, headers, dates, clocks = indexed_rows(path, seed)
        assert scroll == 2, (seed, scroll)
        assert numbers == tuple(("%d.", i, 0x1FFFB80) for i in range(3, 8)), (seed, numbers)
        assert number_draws == tuple((77, 128 + 17 * i, numbers[i][2])
                                     for i in range(5)), (seed, number_draws)
        assert headers == tuple(0x8E1200 + 112 * i for i in range(2, 7)), (seed, headers)
        assert dates == tuple((11, 10 + i, 2026) for i in range(2, 7)), (seed, dates)
        assert clocks == tuple((1 + i, 20 + i, 0x53F660) for i in range(2, 7)), (seed, clocks)
        checks += 6
        assert date_boundary(path, seed) == ("%d/%d/%d", (1, 9, 2026)), seed
        checks += 1
        if slot_header is not None:
            for debug in (0, 1):
                by_site, keys = completed_preview(path, seed, slot_header, debug)
                assert u32s(by_site[0x21DA74], 1) == (0x8E1200,), (seed, debug)
                assert 0x21E1A0 in by_site and 0x21E184 not in by_site, (seed, debug)
                assert keys[0x21E258] == "memcardDifficulty1", (seed, debug)
                if debug:
                    assert keys[0x21DD48] == "MemcardSaveTime", seed
                    assert keys[0x21DFA8] == "MemcardBrowseMinutes", seed
                    assert by_site[0x21E088].fargs[0] == 0x3F800000, seed
                    assert 0x21E0F0 in by_site, seed
                else:
                    assert not ({0x21DD48, 0x21DFA8, 0x21E088, 0x21E0F0} &
                                by_site.keys()), seed
                checks += 4 if debug else 2
        for hour, minute, expected in R.CLOCK_BOUNDARIES:
            got = clock_boundary(path, seed, hour, minute)
            assert got == expected, (seed, hour, minute, got)
            checks += 1
        header, date, clock, reads = row_fields(path, seed)
        assert header == R.SYNTHETIC_ROW_FIELDS["level_header"], (seed, header)
        assert date == R.SYNTHETIC_ROW_FIELDS["date"], (seed, date)
        assert clock == R.SYNTHETIC_ROW_FIELDS["clock"], (seed, clock)
        assert set(R.SYNTHETIC_ROW_FIELDS["preview_reads"]) <= reads, (seed, reads)
        checks += 4
        expanded, names = frame_expansion(path, seed)
        assert expanded == R.FRAME_IMPL, (seed, expanded)
        assert names == ("interfac.lmp", "tile", "btile", "ctile"), (seed, names)
        checks += 2
        anchors, names = frame_tiles(path, seed)
        assert anchors == R.frame_tile_anchors(), (seed, anchors)
        assert len(names) == 42 and set(names) == set(R.TILE_PIECES), (seed, names)
        checks += 2
        for mode in (3, 4):
            for count in (0, 1, 2, 5, 6):
                e, rows, rects, frames, fonts, _, _ = layout(path, seed, count, 0, 0,
                                                               mode=mode)
                assert rows == R.slot_rows(count, save=mode == 3), (seed, mode, count, rows)
                assert rects == (R.slot_highlight(0),), (seed, mode, count, rects)
                assert frames == (R.SLOT_FRAME, R.SLOT_FRAME_OVERLAY), (seed, mode, count, frames)
                assert fonts == ((0x21C404, 0xF1F1F1F1, 6, 0x7F1E6464),
                                 (0x21D830, 0xF1F1F1F1, 6, 0x801E6464)), (seed, mode, count, fonts)
                checks += 4
        for selected in range(5):
            _, _, rects, _, _, _, _ = layout(path, seed, 5, selected, 0)
            assert rects == (R.slot_highlight(selected),), (seed, selected, rects)
            checks += 1
        for debug in (0, 1):
            _, _, _, _, _, labels, preview = layout(path, seed, 1, 0, debug)
            assert labels == R.preview_labels(debug), (seed, debug, labels)
            assert set(preview) == set(R.preview_text(debug)), (seed, debug, preview)
            checks += 2
        for state in (5, 9, 15):
            keys, anchors = prompt(path, seed, state)
            assert keys == R.PROMPT_KEYS[state], (seed, state, keys)
            assert anchors == R.PROMPT_ANCHORS[state], (seed, state, anchors)
            checks += 2
        for state, edge in ((4, 0), (4, 0x40), (4, 0x80), (4, 0x204000),
                            (5, 0), (5, 0x20), (5, 0x80), (9, 0), (9, 0x20)):
            got, _ = action(path, seed, state, edge)
            assert got == R.slot_action(state, edge), (seed, state, edge, got)
            checks += 1
        for entry, browser_site, slot_site in ((0x218AFC, 0x218B44, 0x218BCC),
                                               (0x219360, 0x2193AC, 0x2193F8)):
            browser = outer_route(path, seed, entry, browser_ret=0)
            assert (browser_site, 0x219B90) in browser, (seed, entry, browser)
            # Set the shared browser stage to completed for the slot-list route.
            e = EE(path)
            e.mem.auto_map = True
            e.follow = set()
            e.mem.w32(0x88D3E4, 1)
            e.stub(0x21C3A4, ret=0)
            e.call(entry, max_steps=300000)
            assert (slot_site, 0x21C3A4) in ((c.site, c.target) for c in e.calls)
            checks += 2
    if len(args) == 2:
        expected = {name: (320, 224) if name == "tilecenter.tex" else (32, 32)
                    for name in R.TILE_PIECES}
        assert disc_tiles(args[1]) == expected
        checks += 1
    print("PASS save-screen fixtures: %d checks; seeds 20973, 7" % checks)


if __name__ == "__main__":
    main(sys.argv)
