#!/usr/bin/env python3
"""Bounded new-character keyboard and carousel checks against US v2.00.

Usage: python3 tools/difftest_char_create.py <SLUS_209.73>
The executable is read only. No rendered screen or full task is executed.
"""
import hashlib
import sys

from ee_emu import EE

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
MODEL_ORDER = (0, 11, 10, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9)
MODEL_CLASS = (0, 0, 3, 3, 1, 1, 4, 4, 2, 2, 5, 6)
CLASS_STATS = (
    (35, 20, 25, 35), (26, 36, 27, 26), (28, 30, 27, 30),
    (28, 25, 35, 27), (23, 39, 25, 28), (32, 22, 31, 30),
    (26, 37, 24, 28),
)


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

    # Exact model order, class byte, and seven starting-stat rows in the ELF.
    rows = [(emu.mem.u8(0x4fbc00 + i * 0x26c + 8),
             emu.mem.u8(0x4fbc00 + i * 0x26c + 9)) for i in range(13)]
    assert rows == [(model, MODEL_CLASS[model]) for model in MODEL_ORDER]
    stats = tuple(tuple(emu.mem.u32(0x4ef400 + i * 16 + j * 4)
                        for j in range(4)) for i in range(7))
    assert stats == CLASS_STATS


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: difftest_char_create.py <SLUS_209.73>')
    with open(sys.argv[1], 'rb') as source:
        digest = hashlib.sha256(source.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit('REFUSED char create: executable SHA-256 does not match US v2.00')
    for seed in (20973, 7):
        check(sys.argv[1], seed)
    print('PASS char create: pinned US v2.00; 2 keyboard executions; 2 carousel and class-stat table checks; seeds 20973 and 7')


if __name__ == '__main__':
    main()
