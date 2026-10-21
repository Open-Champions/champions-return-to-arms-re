#!/usr/bin/env python3
"""ref_menus.py - menu decisions that are not already in ref_messages or ref_items.

US SLUS_209.73 v2.00. The equip, buy, sell, stat and skill handlers stay in
tools/ref_messages.py. This module is the screen in front of them: which button
sends which message, what the next skill rank costs, and how a save file names
an item. docs/menus.md is the write-up. tools/difftest_menus.py runs the
original functions; tools/test_ref_menus.py checks this file without an executable.

Nothing here is copied from the game. Addresses are the US v2.00 ones.
"""
import ref_items as RI

M32 = 0xFFFFFFFF

# skills_nextRankCost 0x1d436c loads this pattern into f13. It is one ulp under
# the usual encoding of 1.6 (0x3fcccccd).
RANK_EXPONENT = 0x3FCCCCCC

# save_itemPtrToIndex 0x216bf8 / save_itemIndexToPtr 0x216e10
BAGS = 3
BAG_STRIDE = 0x1208
ITEM_SIZE = 0x48
BAG_ITEMS = 0x130
BAG_COUNT = 0x1330
INDEX_BASE = 1000

# itemList_input 0x1cd988 grid. One column is 75 records; the next column is
# 0x1518 bytes later. The cursor test divides by 32 and 34.
GRID_COLS = 9
GRID_ROWS = 75
GRID_COL = 0x1518
GRID_ROW = 0x48
CURSOR_X_BIAS = 17
CURSOR_COL = 32
CURSOR_ROW = 34

# Masks game_initCamera 0x1e6b68 stores. The byte at 0x41b69c selects the set.
# 'shop' is the word at 0x41b970 (modes 0 and 1), 'equip' the word at 0x41b960,
# 'drop' the word at 0x41b968. Confirm and cancel are g_btnConfirmMask 0x41bfbc
# and g_btnCancelMask 0x41bfb8. A missing shop mask stays 0: that scheme's
# init function does not store 0x41b970.
CROSS_CONFIRM = {'shop': 0x80, 'equip': 0x40, 'drop': 0x10, 'confirm': 0x40, 'cancel': 0x20}
CIRCLE_CONFIRM = {'shop': 0x00, 'equip': 0x20, 'drop': 0x80, 'confirm': 0x20, 'cancel': 0x140}


def s8(x):
    x &= 0xFF
    return x - 0x100 if x & 0x80 else x


def s32(x):
    x &= M32
    return x - 0x100000000 if x & 0x80000000 else x


def rank_cost(param, level):
    """skills_nextRankCost(slot, row) once the row's param byte and the passive
    level are known. param is the signed byte at the skill row + 2. level is
    whatever player_getPassiveLevel returns for the mask at row + 8.

    param below 5: param * (level + 1). Otherwise param plus the truncation of
    level raised to RANK_EXPONENT. The multiply is the low 32 bits; the add wraps.
    """
    param = s8(param)
    level = s32(level)
    if param < 5:
        return s32(param * (level + 1))
    return s32(param + RI.ftrunc(RI.powf(RI.fint(level), RANK_EXPONENT)))


def _cell(record, bag, index):
    return (record + BAG_ITEMS + bag * BAG_STRIDE + index * ITEM_SIZE) & M32


def item_ptr_to_index(item, record, counts):
    """Bag * 1000 + index of the cell `item` points at, or -1.

    counts is the three bag counts (record + 0x1330, stride 0x1208). A null
    pointer, a non-positive count and a pointer that is not one of the counted
    cells are -1. The search stops at the count, so a cell past it is -1 even
    when it sits on the bag's stride.
    """
    item &= M32
    if item == 0:
        return -1
    for bag in range(BAGS):
        count = counts[bag]
        if count <= 0:
            continue
        for index in range(count):
            if _cell(record, bag, index) == item:
                return bag * INDEX_BASE + index
    return -1


def item_index_to_ptr(index, record, counts):
    """The cell whose bag * 1000 + index equals `index`, or 0.

    index -1 is 0. Any other index that no counted cell produces is 0.
    """
    index = s32(index)
    if index == -1:
        return 0
    for bag in range(BAGS):
        count = counts[bag]
        if count <= 0:
            continue
        for i in range(count):
            if bag * INDEX_BASE + i == index:
                return _cell(record, bag, i)
    return 0


def _trunc_div(value, divisor):
    if value < 0:
        return -((-value) // divisor)
    return value // divisor


def cursor_cell(panel_x, cursor_x, cursor_y, tex_height=0, scroll=0):
    """Column and row under the free cursor. The original does this with the
    FPU and truncates toward zero; these inputs are whole numbers, and the
    same truncation is used here.

    column = trunc((cursor_x - panel_x - 17) / 32)
    row = trunc((cursor_y + (-tex_height/2 + 0x8c) + scroll - 229) / 34)
    tex_height is the unsigned halfword at texture + 2. scroll is panel word +0x28.
    """
    column = _trunc_div(int(cursor_x) - int(panel_x) - CURSOR_X_BIAS, CURSOR_COL)
    half = int(tex_height) // 2
    row_top = int(cursor_y) + (-half + 0x8C) + int(scroll) - 229
    return column, _trunc_div(row_top, CURSOR_ROW)


def grid_address(base, column, row):
    """Cell address, or 0 when the column or row is outside the 9 by 75 grid."""
    if column < 0 or row < 0 or column >= GRID_COLS or row >= GRID_ROWS:
        return 0
    return (base + column * GRID_COL + row * GRID_ROW) & M32


def item_action(mode, edge, equipped=False, holdable=False, masks=None):
    """What itemList_input does once the cursor is on a filled cell.

    mode 0 is the shop stock, 1 the bag while the shop is open, 2 the inventory,
    3 the workshop. edge is the pad edge word (g_rawPads + 0xc, and for some
    slots + 0x10; the executed cases set both). equipped is inventory_isEquipped.
    holdable is bit 35 of the item flag qword at cell + 8.

    The masks are CROSS_CONFIRM unless the caller passes CIRCLE_CONFIRM.
    Returns buy, sell, confirm, equip, unequip, drop, drag, workshop, or None.
    On mode 1 the shop bit wins over the equip bit. On mode 2 the equip bit
    wins over the drop bit, and a holdable item is dragged instead of equipped.
    Mode 3 hands the cell to workshop_input without looking at the edge.
    """
    masks = CROSS_CONFIRM if masks is None else masks
    shop = edge & masks['shop']
    equip = edge & masks['equip']
    drop = edge & masks['drop']
    if mode == 3:
        return 'workshop'
    if mode == 0:
        return 'buy' if shop else None
    if mode == 1:
        if shop:
            return 'confirm' if equipped else 'sell'
        if equip:
            return 'unequip' if equipped else 'equip'
        return None
    if mode == 2:
        if equip:
            if holdable:
                return 'drag'
            return 'unequip' if equipped else 'equip'
        if drop:
            return 'drop'
        return None
    return None


def inventory_strip(panel_x):
    """First scrollbar rect of itemList_draw: (x0, y0, x1). y1 is y0 + 1, layer 4.
    The strip then walks upward one pixel at a time."""
    return panel_x + 15, 413, panel_x + 305


def shop_choice_rows():
    """Baseline y of the two centred shop choices (buy, then sell)."""
    return 203, 243


def stats_header():
    """(x, y) of the first centred line on stats_screen, and the small-font global."""
    return 160, 107, 0x4F7104
