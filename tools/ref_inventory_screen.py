"""Bounded US v2.00 inventory-screen decisions and draw submissions.

The caller supplies fixture state.  No game files or rendered assets are stored here.
See docs/spec/inventory-screen.md for addressed evidence and scope.
"""

SMALL_FONT_WORD = 0x4F7104
PANEL_BASE = 0x4F4040
PLAYER_BASE = 0x4D8AF0
ITEM_SIZE = 0x48
GRID_COL_STRIDE = 0x1518
GRID_PAGE_STRIDE = 0xBDD8
BAG_PAGE_STRIDE = 0x1208
GRID_COLS = 9
VISIBLE_ROWS = 10
TEXT_LAYER = 6
GRID_LAYER = 5

CROSS = {"equip": 0x40, "drop": 0x10}
CIRCLE = {"equip": 0x20, "drop": 0x80}


def strip_rects(panel_x):
    """65 layer-4 one-pixel scrollbar strips, including the saturated last one."""
    return [(panel_x + 15, 413 + n, panel_x + 305, 414 + n, 4,
             min(((2 * n + 1) * 127 + 64) // 128, 127) << 24)
            for n in range(65)]


def box_placements(panel_x):
    """Three numbered horizontal box pieces and one end piece per visible pair."""
    return [(panel_x + 15 + 96 * col, 116 + 68 * row, 'numbered')
            for row in range(5) for col in range(3)] + [
            (panel_x + 303, 116 + 68 * row, 'end') for row in range(5)]


BOX_ZERO_STATE_VARIANTS = (3, 3, 2, 2, 1, 3, 3, 2, 1, 1, 1, 1, 3, 3, 2)
BOX_ZERO_STATE_FINAL = 0xEEF6843F


def box_variants():
    """Executed sequence for the standard panel after its cosmetic-seed reset.

    The function at 0x1cd79c zeroes 0x86a6a4 before drawing the boxes. The
    recurrence at 0x1ccaa0-0x1ccaf8 contains additional arithmetic; this
    bounded reference records the observed 15 submissions, not a guessed RNG.
    """
    return ['inventrybox%d.tex' % n for n in BOX_ZERO_STATE_VARIANTS]


def grid_cell(base, column, row, page=0):
    if not (0 <= page < 3 and 0 <= column < GRID_COLS and 0 <= row < 75):
        return None
    return base + page * GRID_PAGE_STRIDE + column * GRID_COL_STRIDE + row * ITEM_SIZE


def bag_page_base(base, page):
    """Selected bag base used by the bounded first-cell action fixture."""
    if not 0 <= page < 3:
        return None
    return base + page * BAG_PAGE_STRIDE


def cursor_cell(panel_x, cursor_x, cursor_y, texture_height=0, scroll=0):
    """Truncating grid hit test; see itemList_input 0x1cdd40-0x1cdf70."""
    return (int((cursor_x - panel_x - 17) / 32),
            int((cursor_y - texture_height // 2 + 140 + scroll - 229) / 34))


def action(edge, *, equipped=False, holdable=False, scheme=CROSS):
    """Mode-2 matched-cell action; the equip bit precedes the drop bit."""
    if edge & scheme['equip']:
        if holdable:
            return 'drag'
        return 'unequip' if equipped else 'equip'
    if edge & scheme['drop']:
        return 'drop'
    return None


def grid_tint(*, equipped=False, blocked=False, flag41=False):
    if equipped:
        return 0x20008000
    if blocked and not flag41:
        return 0x20000080
    return 0x20445558


def item_stat_kind(category):
    """The primary computed stat requested by itemList_drawItemInfo."""
    return {0: 'damage', 1: 'armour'}.get(category, 'other')


def item_info_frame(info_x, info_y, category):
    """ui_drawFrameImpl arguments for the selected item's detail panel."""
    return (info_x - 109, info_y, 223, 77 if category == 0 else 57,
            6, 0x80000000)
