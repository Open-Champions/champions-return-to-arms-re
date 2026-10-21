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
from ref_frontend_layout import (BOOT_CARD_CALLS, BOOT_STEP_CALLS,  # noqa: E402
                                 CARD_DRAW_DISPATCH, FRONTEND_STATES,
                                 INTRO_CALLS, MAIN_MENU_ACCEPT, MENU_SOUND_IDS, TABLES,
                                 CREDITS_EXIT_FINISHED, CREDITS_EXIT_RUNNING, FONT_USES,
                                 credits_one_line_geometry, first_theme_queues, list_frame_calls,
                                 list_geometry, pause_geometry, publisher_logo_sprites)

SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
SEEDS = (20973, 7)


def emulator(path, seed):
    e = EE(path)
    e.mem.auto_map = True
    e.mem.w32(0x404460, seed)
    return e


def draw_list(path, seed, table, origin_y=309):
    e = emulator(path, seed)
    e.follow = {0x17FBB8}
    e.call(0x1A07C4, 320, origin_y, table, 0x80446B6A, max_steps=100000)
    anchors = [(c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF)
               for c in e.calls if c.target == 0x181CA0]
    frames = [tuple(x & 0xFFFFFFFF for x in c.args[:6])
              for c in e.calls if c.target == 0x17FBB8]
    assembled = [tuple(x & 0xFFFFFFFF for x in c.args[:7])
                 for c in e.calls if c.target == 0x17C118]
    return anchors, frames, assembled


def frontend_draw(path, seed, state, table):
    e = emulator(path, seed)
    e.follow = {0x1A07C4}
    e.mem.w32(0x4F6B78, state)
    e.mem.w32(0x4F6B7C, table)
    e.call(0x1E08F0, max_steps=100000)
    list_calls = [c for c in e.calls if c.target == 0x1A07C4]
    anchors = [(c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF)
               for c in e.calls if c.site == 0x1A0E5C and c.target == 0x181CA0]
    frames = [tuple(v & 0xFFFFFFFF for v in c.args[:6])
              for c in e.calls if c.site == 0x1A11BC and c.target == 0x17FBB8]
    return [c.args[1] & 0xFFFFFFFF for c in list_calls], anchors, frames


def frontend_details(path, seed, state, table):
    """Read parent submissions at their exact call sites; no resource data saved."""
    e = emulator(path, seed)
    e.follow = {0x1A07C4}
    e.mem.w32(0x4F6B78, state)
    e.mem.w32(0x4F6B7C, table)
    e.call(0x1E08F0, max_steps=100000)
    title_ids = [e.mem.cstr(c.args[1] & 0xFFFFFFFF) for c in e.calls
                 if c.site == 0x1E0AAC and c.target == 0x17365C]
    sprites = [tuple(v & 0xFFFFFFFF for v in c.args[1:5]) for c in e.calls
               if c.site == 0x1E0AC8 and c.target == 0x17FB68]
    parent_fonts = [(c.args[1] & 0xFFFFFFFF, c.args[2] & 0xFFFFFFFF)
                    for c in e.calls if c.site == 0x1E0DCC and c.target == 0x1800B8]
    extra_fonts = [(c.args[1] & 0xFFFFFFFF, c.args[2] & 0xFFFFFFFF)
                   for c in e.calls if c.site == 0x1E13C8 and c.target == 0x1800B8]
    extra_text = [(c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF)
                  for c in e.calls if c.site == 0x1E13E0 and c.target == 0x181CA0]
    return title_ids, sprites, parent_fonts, extra_fonts, extra_text


def name_entry_details(path, seed):
    e = emulator(path, seed)
    e.follow = set()
    e.call(0x22C920, max_steps=100000)
    fonts = [(c.site, c.args[1] & 0xFFFFFFFF, c.args[2] & 0xFFFFFFFF)
             for c in e.calls if c.target == 0x1800B8]
    text = [(c.site, c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF)
            for c in e.calls if c.target == 0x181CA0]
    rects = [(c.site, *(v & 0xFFFFFFFF for v in c.args[:6]))
             for c in e.calls if c.target == 0x17BD30]
    clips = [(c.site, *(v & 0xFFFFFFFF for v in c.args[:4]))
             for c in e.calls if c.target == 0x1803E0]
    detail_text = [(c.site, c.target, c.args[0] & 0xFFFFFFFF,
                    c.args[1] & 0xFFFFFFFF)
                   for c in e.calls if c.target in (0x181C10, 0x181280, 0x181AA0)]
    return fonts, text, rects, clips, detail_text


def credits_details(path, seed):
    e = emulator(path, seed)
    e.follow = set()
    e.call(0x223C64, max_steps=100000)
    e.reset_log()
    e.call(0x223D3C, max_steps=100000)
    return [(c.site, c.args[1] & 0xFFFFFFFF, c.args[2] & 0xFFFFFFFF)
            for c in e.calls if c.target == 0x1800B8]


def credits_authored_line(path, seed, scroll_y):
    """Supply one original-code wide-string pointer using authored test data."""
    e = emulator(path, seed)
    e.follow = set()
    line = e.alloc(32)
    e.mem.write(line, b"A\x00\x00\x00")
    e.call(0x223C64, max_steps=100000)
    e.mem.w32(0x4FB5E8, line)
    e.mem.w32(0x4FB5D8, scroll_y)
    e.reset_log()
    e.call(0x223D3C, max_steps=100000)
    positions = [(c.site, c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF)
                 for c in e.calls if c.target == 0x181CA0]
    colours = [(c.site, c.args[0] & 0xFFFFFFFF) for c in e.calls
               if c.target == 0x1802E0]
    return positions, colours, e.mem.u32(0x4FB5D8)


def shallow_screen_calls(path, seed, entry, card_state=None):
    """Capture a direct entry path, with deeper callees explicitly stubbed."""
    e = emulator(path, seed)
    e.follow = set()
    if card_state is not None:
        e.mem.w32(0x88D3A0, card_state)
    e.call(entry, max_steps=150000)
    return [(c.site, c.target) for c in e.calls]


def selection_path(path, seed):
    e = emulator(path, seed)
    e.follow = set()
    e.call(0x2245B8, max_steps=150000)
    start = [(c.site, c.target) for c in e.calls]
    e.reset_log()
    e.call(0x225478, max_steps=150000)
    task = [(c.site, c.target) for c in e.calls]
    return start, task


def card_slot_font(path, seed):
    e = emulator(path, seed)
    e.follow = set()
    e.call(0x21C3A4, max_steps=150000)
    return [(c.site, c.args[1] & 0xFFFFFFFF, c.args[2] & 0xFFFFFFFF)
            for c in e.calls if c.target == 0x1800B8]


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
    # g_streams[2] is music; +0x1c0 is the eight-entry queue count
    # (docs/audio-save.md, Streams).
    return e.mem.u32(0x876C10 + 2 * 0x1C4 + 0x1C0)


def pause_draw(path, seed):
    e = emulator(path, seed)
    e.follow = {0x1A07C4, 0x3B8534, 0x3B96A8, 0x17FBB8}
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
    assembled = [tuple(x & 0xFFFFFFFF for x in c.args[:7])
                 for c in e.calls if c.target == 0x17C118]
    return flags, anchors, frames, colors, assembled


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
    # The lockstep pad's held/pressed/repeat words (0x41BFE0/E4/E8, from
    # docs/spec/player-tick.md:76). Bit layout per docs/netcode.md:138: 0x4000
    # is d-pad down; 0x40 is cross and 0x20 is circle (face buttons Inferred
    # there). The transitions asserted below are the observed use as
    # move / accept / cancel.
    for addr in (0x41BFE0, 0x41BFE4, 0x41BFE8):
        e.mem.w32(addr, mask)
    e.call(0x1E08F0, max_steps=100000)
    ids = [e.mem.cstr(c.args[1] & 0xFFFFFFFF)
           for c in e.calls if c.target == 0x17365C and
           c.site in (0x1A03E8, 0x1E15A4, 0x1E1D6C)]
    sound_calls = [c for c in e.calls if c.target == 0x214230 and
                   c.site in (0x1A03FC, 0x1E15B8, 0x1E1D80)]
    return e.mem.u32(0x4F6B78), ids, len(sound_calls)


def main_accept(path, seed, row):
    """Accept main-list row `row` with the original string compare followed."""
    e = emulator(path, seed)
    e.follow = {0x1A01D0, 0x3B8534, 0x3B96A8}
    e.mem.w32(0x4F6B78, 0)
    e.mem.w32(0x4F6B7C, 0x4F6B88)
    e.mem.w32(0x4F6B88 + 4 * 16 + 4, row)  # selected index: terminator entry +4
    for addr in (0x41BFE0, 0x41BFE4, 0x41BFE8):  # lockstep pad held/pressed/repeat
        e.mem.w32(addr, 0x40)  # accept bit, as in menu_action
    e.call(0x1E08F0, max_steps=100000)
    sites = {0x1E15B8, 0x1E166C, 0x1E16A0, 0x1E16E4, 0x1E16F4, 0x1E16FC}
    calls = tuple((c.site, c.target) for c in e.calls if c.site in sites)
    music = [(e.mem.cstr(c.args[0] & 0xFFFFFFFF), c.args[1] & 0xFFFFFFFF)
             for c in e.calls if c.site == 0x1E16F4]
    return (e.mem.u32(0x4F6B78), e.mem.u32(0x4F6B7C), calls,
            music[0] if music else None)


def credits_exit(path, seed, credits_run_result):
    """frontend_run in state 15 with credits_run stubbed to a chosen result."""
    e = emulator(path, seed)
    e.follow = {0x1A01D0, 0x3B8534, 0x1E318C}  # 0x1e318c returns the main table
    e.mem.w32(0x4F6B78, 15)
    e.mem.w32(0x4F6B7C, 0x4F6FB8)
    e.stub(0x223D3C, ret=credits_run_result)
    e.call(0x1E08F0, max_steps=100000)
    sites = {0x1E113C, 0x1E114C}
    calls = tuple((c.site, c.target) for c in e.calls if c.site in sites)
    music = [(e.mem.cstr(c.args[0] & 0xFFFFFFFF), c.args[1] & 0xFFFFFFFF)
             for c in e.calls if c.site == 0x1E114C]
    return (e.mem.u32(0x4F6B78), e.mem.u32(0x4F6B7C), calls,
            music[0] if music else None)


FONT_NAMES = {0xF0F0F0F0: "medium", 0xF1F1F1F1: "small"}


def font_uses(path, seed):
    """text_begin (site, font, layer, colour) per fixture, with sentinel font words."""
    def plant(e):
        e.mem.w32(0x4F7100, 0xF0F0F0F0)  # medium font pointer word
        e.mem.w32(0x4F7104, 0xF1F1F1F1)  # small font pointer word

    def begins(e, sites=None):
        return tuple((c.site, FONT_NAMES.get(c.args[0] & 0xFFFFFFFF, c.args[0] & 0xFFFFFFFF),
                      c.args[1] & 0xFFFFFFFF, c.args[2] & 0xFFFFFFFF)
                     for c in e.calls if c.target == 0x1800B8 and
                     (sites is None or c.site in sites))
    out = {}
    for name, state, table in (("frontend_list_state0", 0, 0x4F6B88),
                               ("frontend_difficulty_extra", 3, 0x4F6E38)):
        e = emulator(path, seed)
        plant(e)
        e.follow = {0x1A07C4}
        e.mem.w32(0x4F6B78, state)
        e.mem.w32(0x4F6B7C, table)
        e.call(0x1E08F0, max_steps=100000)
        out[name] = begins(e) if state == 0 else begins(e, {0x1E13C8})
    e = emulator(path, seed)
    plant(e)
    e.follow = set()
    e.call(0x22C920, max_steps=100000)
    out["name_entry"] = begins(e)
    e = emulator(path, seed)
    plant(e)
    e.follow = set()
    e.call(0x223C64, max_steps=100000)
    e.reset_log()
    e.call(0x223D3C, max_steps=100000)
    out["credits"] = begins(e)
    e = emulator(path, seed)
    plant(e)
    e.follow = {0x1A07C4, 0x3B8534, 0x3B96A8, 0x17FBB8}
    e.call(0x18E334, 0, max_steps=100000)
    e.stub(0x217550, ret=-1)
    e.reset_log()
    e.call(0x18CC08, max_steps=100000)
    out["pause"] = begins(e, {0x18D5E8})
    return out


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
            anchors, frames, assembled = draw_list(path, seed, table)
            assert anchors == expected_anchors, (seed, name, anchors, expected_anchors)
            assert frames == [expected_frame], (seed, name, frames, expected_frame)
            assert assembled == list_frame_calls(count, value_rows), (
                seed, name, assembled)
            checks += 3
        for volume in (0, 0x3D4CCCCC - 1, 0x3D4CCCCC, 0x3F000000,
                       0xBF800000):
            queued = theme_queue(path, seed, volume)
            assert queued == int(first_theme_queues(volume)), (seed, volume, queued)
            checks += 1
        for state, (name, _origin_y) in FRONTEND_STATES.items():
            table = TABLES[name][0]
            title_ids, sprites, parent_fonts, extra_fonts, extra_text = frontend_details(
                path, seed, state, table)
            if state in (0, 1, 2, 3, 4):
                assert title_ids == ["title.tex"], (seed, state, title_ids)
                assert sprites == [(141, 15, 5, 0x80808080)], (seed, state, sprites)
            else:
                assert title_ids == sprites == [], (seed, state)
            assert parent_fonts == [(7, 0x64464646)], (seed, state, parent_fonts)
            if state == 3:
                assert len(extra_fonts) == 1 and extra_fonts[0][0] == 6
                assert extra_text == [(320, 366)], (seed, extra_text)
            else:
                assert extra_fonts == extra_text == [], (seed, state)
            checks += 4
        fonts, text, rects, clips, detail_text = name_entry_details(path, seed)
        assert [(site, x, y) for site, x, y in text] == [
            (0x22CBA4, 163, 98), (0x22CCEC, 233, 98)], (seed, text)
        assert (0x22D084, 0, 0xFFFFFFF7, 0, 11, 6, 0x1E3053) in rects, (seed, rects)
        assert (0x22D20C, 41, 0, 640, 480) in clips, (seed, clips)
        assert fonts == [(0x22C9C0, 6, 0x585E5D),
                         (0x22D0E4, 6, 0x316864),
                         (0x22D198, 6, 0x585E5D)], (seed, fonts)
        assert detail_text == [(0x22CE4C, 0x181C10, 81, 138),
                               (0x22CEB0, 0x181C10, 81, 158),
                               (0x22CF14, 0x181C10, 81, 178),
                               (0x22D12C, 0x181280, 41, 38),
                               (0x22D26C, 0x181AA0, 41, 72)], (seed, detail_text)
        checks += 5
        assert credits_details(path, seed) == [(0x223E40, 7, 0x80000000)], seed
        checks += 1
        for scroll_y, wanted_colours in (
                (448, [(0x224004, 0), (0x22402C, 0x00405E5E)]),
                (400, [(0x224004, 0x07000000), (0x22402C, 0x14405E5E)]),
                (224, [(0x224004, 0x20000000), (0x22402C, 0x5E405E5E)])):
            positions, colours, next_y = credits_authored_line(path, seed, scroll_y)
            assert positions == list(credits_one_line_geometry(scroll_y)), (
                seed, scroll_y, positions)
            assert colours == wanted_colours, (seed, scroll_y, colours)
            assert next_y == scroll_y - 1, (seed, scroll_y, next_y)
            checks += 3
        assert shallow_screen_calls(path, seed, 0x32396C) == list(BOOT_CARD_CALLS)
        assert shallow_screen_calls(path, seed, 0x3238F4) == list(BOOT_STEP_CALLS)
        assert shallow_screen_calls(path, seed, 0x321788) == list(INTRO_CALLS)
        checks += 3
        for card_state, dispatch in CARD_DRAW_DISPATCH.items():
            calls = shallow_screen_calls(path, seed, 0x2189E0, card_state)
            assert calls == [(0x218A14, 0x223064), *dispatch], (seed, card_state, calls)
            checks += 1
        assert card_slot_font(path, seed) == [(0x21C404, 6, 0x001E6464)], seed
        checks += 1
        start, task = selection_path(path, seed)
        assert (0x2247AC, 0x19E4A0) in start, (seed, start)
        assert task == [(0x2256C0, 0x3A58C0), (0x2257AC, 0x22A968),
                        (0x2258C8, 0x22A83C)], (seed, task)
        checks += 2
        for state, (name, origin_y) in FRONTEND_STATES.items():
            table, count, value_rows = TABLES[name]
            origins, anchors, frames = frontend_draw(path, seed, state, table)
            wanted_anchors, wanted_frame = list_geometry(
                count, value_rows, origin=(320, origin_y))
            assert (origins, anchors, frames) == (
                [origin_y], wanted_anchors, [wanted_frame]), (
                    seed, state, origins, anchors, frames)
            checks += 1
        flags, anchors, frames, colors, assembled = pause_draw(path, seed)
        want_anchors, want_frame = pause_geometry()
        assert flags == (0, 0, 0, 1, 1, 0, 1, 1, 0), (seed, flags)
        assert anchors == want_anchors, (seed, anchors)
        assert frames == [want_frame], (seed, frames)
        assert colors == [(7, 0x80464646)], (seed, colors)
        assert assembled == list_frame_calls(5, origin=(320, 240)), (
            seed, assembled)
        checks += 5
        assert logo_draw(path, seed) == list(publisher_logo_sprites()), seed
        checks += 1
        assert font_uses(path, seed) == FONT_USES, (seed, font_uses(path, seed))
        checks += 1
        assert credits_exit(path, seed, 0) == CREDITS_EXIT_FINISHED, (
            seed, credits_exit(path, seed, 0))
        assert credits_exit(path, seed, 1) == CREDITS_EXIT_RUNNING, (
            seed, credits_exit(path, seed, 1))
        checks += 2
        for row, wanted in MAIN_MENU_ACCEPT.items():
            assert main_accept(path, seed, row) == wanted, (
                seed, row, main_accept(path, seed, row))
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
