#!/usr/bin/env python3
"""difftest_menus.py - compare tools/ref_menus.py with the original menu functions.

Needs your own SLUS_209.73 (US v2.00). Without it the script says so and exits 0.

  python3 tools/difftest_menus.py [path/to/SLUS_209.73]

The original functions run in tools/ee_emu.py. Existing models are not modified.
Rank cost stubs player_getPassiveLevel so the level is an input, and runs the
game's own powf. The save-index functions have no callees. Item input stubs
everything it calls and records which sender runs.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError, MemoryFault, CpuTrap, UnimplementedInstruction  # noqa: E402
import ref_menus as M  # noqa: E402

ELF_SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
HOME_ELF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'SLUS_209.73')

RANK = 0x1D436C
PASSIVE = 0x1BED48
PTR_TO_INDEX = 0x216BF8
INDEX_TO_PTR = 0x216E10
ITEM_INPUT = 0x1CD988
ITEM_DRAW = 0x1CD208
SHOP_MENU = 0x1C6BB8
STATS = 0x1D1DB8
SKILLS = 0x1D4660
INIT_CAMERA = 0x1E6B68
DRAW_RECT = 0x17BD30
TEXT_BEGIN = 0x1800B8
TEXT_CENTER = 0x181AF8
TEXT_WIDE_CENTER = 0x181CA0
SPRITE_CLIP = 0x17FB88

SENDERS = {
    0x1CE1AC: 'buy',
    0x1CE520: 'sell',
    0x1CE444: 'confirm',
    0x1CE868: 'unequip',
    0x1CE87C: 'equip',
    0x1CEB1C: 'drop',
    0x1CEB50: 'workshop',
}

# Words game_initCamera writes. Byte 0 leaves 0x41b970 alone.
MASK_WORDS = (0x41B960, 0x41B964, 0x41B968, 0x41B96C, 0x41B970, 0x41B974,
              0x41B978, 0x41B97C, 0x41BFB8, 0x41BFBC)
MASK_BYTE1 = {
    0x41B960: 0x40, 0x41B964: 0x7E, 0x41B968: 0x10, 0x41B96C: 0x7C,
    0x41B970: 0x80, 0x41B974: 0x7D, 0x41B978: 0x7E, 0x41B97C: 0x7B,
    0x41BFB8: 0x20, 0x41BFBC: 0x40,
}
MASK_BYTE0 = {
    0x41B960: 0x20, 0x41B964: 0x7B, 0x41B968: 0x80, 0x41B96C: 0x7C,
    0x41B978: 0x7B, 0x41B97C: 0x7E, 0x41BFB8: 0x140, 0x41BFBC: 0x20,
}

RESULTS = []


def report(name, ok, detail):
    RESULTS.append((name, ok))
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, detail))


def new_emu(follow):
    elf = new_emu.elf
    emu = EE(elf, fpu_model='ps2')
    emu.follow = follow
    emu.default_ret = 0
    emu.mem.auto_map = True
    return emu


def check_rank(cases):
    bad = []
    for param, level in cases:
        emu = new_emu(None)
        emu.mem.map(0x4D8AF0, 0x4C30)
        emu.mem.w32(0x4D8AF0 + 0x50, 0)
        emu.mem.w8(0x4EF530 + 2, param & 0xFF)
        emu.stub(PASSIVE, ret=level & 0xFFFFFFFF)
        try:
            got = M.s32(emu.call(RANK, 0, 0))
        except (EmuError, MemoryFault, CpuTrap, UnimplementedInstruction) as exc:
            bad.append((param, level, type(exc).__name__))
            continue
        want = M.rank_cost(param, level)
        if got != want:
            bad.append((param, level, got, want))
    report('rank cost', not bad, '%d cases%s' % (len(cases), '' if not bad else ' ' + str(bad[:4])))


def check_save_index():
    record = 0x4D8AF0
    counts = (3, 2, 1)
    bad = []
    probes = [(0, 0), (0, 2), (1, 1), (2, 0)]
    extra = [0, record + M.BAG_ITEMS + 5 * M.ITEM_SIZE, -1, 5, 1000, 2000]
    emu = new_emu(set())
    emu.mem.map(record, 0x4C30)
    for bag, count in enumerate(counts):
        emu.mem.w32(record + M.BAG_COUNT + bag * M.BAG_STRIDE, count)
    n = 0
    for bag, index in probes:
        cell = M._cell(record, bag, index)
        got = M.s32(emu.call(PTR_TO_INDEX, cell, record))
        want = M.item_ptr_to_index(cell, record, counts)
        back = emu.call(INDEX_TO_PTR, want & 0xFFFFFFFF, record) & 0xFFFFFFFF
        n += 1
        if got != want or back != cell:
            bad.append((bag, index, got, want, hex(back)))
    for item in (0, record + M.BAG_ITEMS + 4 * M.ITEM_SIZE):
        got = M.s32(emu.call(PTR_TO_INDEX, item & 0xFFFFFFFF, record))
        want = M.item_ptr_to_index(item, record, counts)
        n += 1
        if got != want:
            bad.append(('ptr', item, got, want))
    for index in extra:
        got = emu.call(INDEX_TO_PTR, index & 0xFFFFFFFF, record) & 0xFFFFFFFF
        want = M.item_index_to_ptr(index, record, counts)
        n += 1
        if got != want:
            bad.append(('idx', index, hex(got), hex(want)))
    report('save index', not bad, '%d cases%s' % (n, '' if not bad else ' ' + str(bad[:4])))


def install_masks(emu, masks):
    for addr, value in masks.items():
        emu.mem.w32(addr, value)


def run_input(mode, edge, equipped=False, holdable=False, masks=None):
    masks = M.CROSS_CONFIRM if masks is None else masks
    written = {
        0x41B960: masks['equip'], 0x41B968: masks['drop'], 0x41B970: masks['shop'],
        0x41BFBC: masks['confirm'], 0x41BFB8: masks['cancel'],
    }
    emu = new_emu(set())
    empty = emu.alloc(64)
    definition = emu.alloc(0x40)
    name = emu.alloc(8)
    emu.mem.write(name, b'item\0')
    emu.mem.w32(definition, name)
    grid = emu.alloc(0x200)
    emu.mem.w32(grid, definition)
    emu.mem.w16(grid + 4, 1)
    if holdable:
        emu.mem.w64(grid + 8, 1 << 35)
    record = 0x4D8AF0
    emu.mem.map(record, 0x4C30)
    emu.mem.w32(record + 0x130, definition)
    emu.mem.w16(record + 0x134, 1)
    emu.mem.w32(record + 0x1330, 1)
    emu.mem.w32(record + 0xE4, 100000)
    emu.mem.w32(record + 0x43D8, emu.alloc(0x200))
    emu.mem.w32(0x4F4228, grid)
    emu.mem.w32(0x4EBBB0, grid)
    install_masks(emu, written)
    emu.mem.map(0x4028D0, 0x80)
    emu.mem.w32(0x4028D8, edge)
    emu.mem.w32(0x4028DC, edge)
    emu.mem.w32(0x4028E0, edge)
    panel = 0x4F4040
    emu.mem.map(panel, 0x80)
    emu.mem.wf32(panel + 0x44, 17.0)
    emu.mem.wf32(panel + 0x48, 100.0)
    emu.stub(0x173C84, ret=empty)
    emu.stub(0x17365C, ret=empty)
    emu.stub(0x13E150, ret=1)
    emu.stub(0x1024A8, ret=100)
    emu.stub(0x1C41D8, ret=1 if equipped else 0)
    emu.call(ITEM_INPUT, 0, mode, 0, panel, max_steps=2000000)
    found = []
    for call in emu.calls:
        if call.site in SENDERS:
            found.append(SENDERS[call.site])
    if not found and emu.mem.u32(panel + 0x58) == 1:
        return 'drag'
    return found[0] if found else None


def check_input():
    cases = [
        (0, 0x80, False, False, M.CROSS_CONFIRM, 'buy'),
        (0, 0x40, False, False, M.CROSS_CONFIRM, None),
        (1, 0x80, False, False, M.CROSS_CONFIRM, 'sell'),
        (1, 0x80, True, False, M.CROSS_CONFIRM, 'confirm'),
        (1, 0x40, False, False, M.CROSS_CONFIRM, 'equip'),
        (1, 0x40, True, False, M.CROSS_CONFIRM, 'unequip'),
        (1, 0x10, False, False, M.CROSS_CONFIRM, None),
        (2, 0x40, False, False, M.CROSS_CONFIRM, 'equip'),
        (2, 0x40, True, False, M.CROSS_CONFIRM, 'unequip'),
        (2, 0x40, False, True, M.CROSS_CONFIRM, 'drag'),
        (2, 0x10, False, False, M.CROSS_CONFIRM, 'drop'),
        (2, 0x50, False, False, M.CROSS_CONFIRM, 'equip'),
        (2, 0x80, False, False, M.CROSS_CONFIRM, None),
        (2, 0x00, False, False, M.CROSS_CONFIRM, None),
        (3, 0x00, False, False, M.CROSS_CONFIRM, 'workshop'),
        (2, 0x20, False, False, M.CIRCLE_CONFIRM, 'equip'),
        (2, 0x80, False, False, M.CIRCLE_CONFIRM, 'drop'),
        (2, 0x40, False, False, M.CIRCLE_CONFIRM, None),
    ]
    bad = []
    for mode, edge, equipped, holdable, masks, _want in cases:
        try:
            got = run_input(mode, edge, equipped, holdable, masks)
        except (EmuError, MemoryFault, CpuTrap, UnimplementedInstruction) as exc:
            got = type(exc).__name__
        want = M.item_action(mode, edge, equipped, holdable, masks)
        if got != want:
            bad.append((mode, hex(edge), got, want))
    report('item input', not bad, '%d cases%s' % (len(cases), '' if not bad else ' ' + str(bad[:6])))


def check_cursor_column():
    emu = new_emu(set())
    empty = emu.alloc(32)
    definition = emu.alloc(0x40)
    grid = emu.alloc(0x1600)
    emu.mem.w32(grid + M.GRID_COL, definition)
    emu.mem.w32(0x4F4228, grid)
    emu.mem.w32(0x4EBBB0, grid)
    emu.mem.w32(0x41B960, 0x40)
    emu.mem.w32(0x41BFBC, 0x40)
    emu.mem.map(0x4D8AF0, 0x200)
    emu.mem.w32(0x4D8AF0 + 0x43D8, emu.alloc(0x40))
    emu.mem.map(0x4028D0, 0x40)
    emu.mem.w32(0x4028DC, 0x40)
    panel = 0x4F4040
    emu.mem.map(panel, 0x80)
    emu.mem.wf32(panel + 0x44, 49.0)
    emu.mem.wf32(panel + 0x48, 100.0)
    emu.stub(0x173C84, ret=empty)
    emu.stub(0x13E150, ret=1)
    emu.call(ITEM_INPUT, 0, 2, 0, panel, max_steps=2000000)
    got = emu.mem.u32(panel + 0x60)
    column, row = M.cursor_cell(0, 49, 100, 0, 0)
    want = M.grid_address(grid, column, row)
    report('cursor column', got == want, 'hover %s grid %s' % (hex(got), hex(want)))


def first_call(emu, target):
    for call in emu.calls:
        if call.target == target:
            return call
    return None


def check_layout():
    bad = []
    emu = new_emu(set())
    empty = emu.alloc(32)
    emu.mem.w16(empty, 32)
    emu.mem.w16(empty + 2, 32)
    emu.stub(0x173C84, ret=empty)
    emu.stub(0x17365C, ret=empty)
    emu.stub(0x13E150, ret=1)
    panel = 0x4F4040
    emu.mem.map(panel, 0x80)
    emu.mem.w32(panel, 80)
    emu.call(ITEM_DRAW, 0, 0, 0, panel, max_steps=2000000)
    rect = first_call(emu, DRAW_RECT)
    x0, y0, x1 = M.inventory_strip(80)
    if rect is None or [a & 0xFFFFFFFF for a in rect.args[:5]] != [x0, y0, x1, y0 + 1, 4]:
        bad.append(('strip', None if rect is None else rect.args[:5]))

    emu = new_emu(set())
    empty = emu.alloc(32)
    emu.stub(0x173C84, ret=empty)
    emu.stub(0x17365C, ret=empty)
    emu.mem.map(0x86A4B0, 0x80)
    emu.call(SHOP_MENU, 0, max_steps=500000)
    rows = [c.args[1] & 0xFFFFFFFF for c in emu.calls if c.target == TEXT_WIDE_CENTER]
    if tuple(rows[:2]) != M.shop_choice_rows():
        bad.append(('shop', rows[:2]))

    font = 0x01000000
    emu = new_emu(set())
    emu.mem.map(font, 16)
    emu.mem.w32(0x4F7104, font)
    empty = emu.alloc(32)
    emu.stub(0x173C84, ret=empty)
    emu.stub(0x17365C, ret=empty)
    emu.stub(0x13E150, ret=1)
    emu.mem.map(0x4D8AF0, 0x4C30)
    emu.mem.w32(0x4D8AF0 + 0x43D8, emu.alloc(0x40))
    emu.call(STATS, 0, max_steps=3000000)
    begin = first_call(emu, TEXT_BEGIN)
    center = first_call(emu, TEXT_CENTER)
    hx, hy, font_at = M.stats_header()
    if begin is None or (begin.args[0] & 0xFFFFFFFF) != font or (begin.args[1] & 0xFFFFFFFF) != 5:
        bad.append(('stats font', None if begin is None else begin.args[:2]))
    if center is None or (center.args[0] & 0xFFFFFFFF, center.args[1] & 0xFFFFFFFF) != (hx, hy):
        bad.append(('stats header', None if center is None else center.args[:2]))
    if font_at != 0x4F7104:
        bad.append(('font global', font_at))

    emu = new_emu(set())
    emu.mem.w32(0x4F7104, font)
    empty = emu.alloc(32)
    emu.stub(0x173C84, ret=empty)
    emu.stub(0x17365C, ret=empty)
    emu.stub(0x13E150, ret=1)
    emu.mem.map(0x4D8AF0, 0x4C30)
    emu.mem.w32(0x4D8AF0 + 0x43D8, emu.alloc(0x40))
    panel = 0x4F4040
    emu.mem.map(panel, 0x80)
    emu.mem.w32(panel, 40)
    emu.call(SKILLS, 0, 0, 0, panel, max_steps=3000000)
    clip = first_call(emu, SPRITE_CLIP)
    if clip is None or (clip.args[1] & 0xFFFFFFFF, clip.args[2] & 0xFFFFFFFF) != (40, 98):
        bad.append(('skill clip', None if clip is None else clip.args[:3]))
    report('layout', not bad, 'strip, shop rows, stats header, skill clip%s' % (
        '' if not bad else ' ' + str(bad)))


def check_masks():
    bad = []
    for byte, expect in ((1, MASK_BYTE1), (0, MASK_BYTE0)):
        emu = new_emu(set())
        emu.mem.w8(0x41B69C, byte)
        for addr in MASK_WORDS:
            emu.mem.w32(addr, 0x11111111)
        try:
            emu.call(INIT_CAMERA, max_steps=200000)
        except (EmuError, MemoryFault, CpuTrap, UnimplementedInstruction) as exc:
            bad.append((byte, type(exc).__name__))
            continue
        for addr in MASK_WORDS:
            got = emu.mem.u32(addr)
            want = expect.get(addr, 0x11111111)
            if got != want:
                bad.append((byte, hex(addr), hex(got), hex(want)))
    report('button masks', not bad, 'byte 0 and byte 1%s' % ('' if not bad else ' ' + str(bad[:4])))


def main(argv):
    elf = argv[1] if len(argv) > 1 else HOME_ELF
    if not os.path.exists(elf):
        print('SKIP: %s not found (the differential test needs your own copy of the executable)' % elf)
        return 0
    new_emu.elf = elf
    rank_cases = [(p, level) for p in (0, 1, 4, 5, 8, -1, 20) for level in (0, 1, 2, 3, 10)]
    check_rank(rank_cases)
    check_save_index()
    check_input()
    check_cursor_column()
    check_layout()
    check_masks()
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d failed' % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
