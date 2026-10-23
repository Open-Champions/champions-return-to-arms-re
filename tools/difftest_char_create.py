#!/usr/bin/env python3
"""Bounded new-character keyboard and carousel checks against US v2.00.

Usage: python3 tools/difftest_char_create.py <SLUS_209.73>
The executable is read only. No rendered screen or full task is executed.
"""
import sys

from ee_emu import EE


def check(path, seed):
    emu = EE(path)
    emu.mem.auto_map = True
    scratch = emu.alloc(0x158c)
    emu.mem.w32(0x4fdb7c, scratch)
    emu.mem.w32(0x404464, seed)

    # Original playerSel_nameKeyboardInit builds its glyph table. The display
    # position updater is isolated when restoring lowercase presentation.
    emu.call(0x22bc9c)
    count = emu.mem.u32(0x8e2bac)
    columns = emu.mem.u32(0x8e2ba8)
    glyphs = emu.mem.read(scratch + 0x14b4, count)
    assert count == 64 and columns == 10
    assert glyphs[:26] == bytes(range(ord('a'), ord('z') + 1))
    assert glyphs[26:36] == bytes(range(ord('0'), ord('9') + 1))
    assert len(set(glyphs[36:])) == 28 and all(byte >= 0x80 for byte in glyphs[36:])
    emu.stub(0x22c704)
    emu.call(0x22bdb0)
    assert emu.mem.read(scratch + 0x14b4, count) == glyphs
    assert emu.mem.u32(0x8e2ba0) == 0xfffffffd

    # Static rows used by the 13-place carousel. One entry is a repeated
    # model for wraparound; the twelve selectable indices each occur once.
    rows = [emu.mem.u8(0x4fbc00 + i * 0x26c + 8) for i in range(13)]
    assert rows[0] == rows[3]
    assert sorted(rows[1:]) == list(range(12))


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: difftest_char_create.py <SLUS_209.73>')
    for seed in (20973, 7):
        check(sys.argv[1], seed)
    print('PASS char create: 2 keyboard executions; 2 carousel table checks; seeds 20973 and 7')


if __name__ == '__main__':
    main()
