"""Bounded save/load screen draw and input model for SLUS-20973 v2.00.

Only numeric submissions and authored fixture state are modeled.  No game text,
texture bytes, card files, or raw disassembly belong in this module.
"""

SEEDS = (20973, 7)
SLOT_Y = 128
SLOT_PITCH = 17
SLOT_VISIBLE = 5
SLOT_FRAME = (0x21D814, 61, 126, 519, 97, 6, 0x7F616369, 0, 1)
SLOT_FRAME_OVERLAY = (0x21E548, 61, 126, 519, 97, 6, 0x7F616369, 0, 0)
FRAME_IMPL = ((0x17FBD8, 60, 122, 521, 105, 6, 0x7F616369, 2, 1),
              (0x17FBD8, 60, 122, 521, 105, 6, 0x7F616369, 2, 0))
TILE_PIECES = (
    "tiletopleft.tex", "tiletopright.tex", "tilebotleft.tex",
    "tilebotright.tex", "tileleft.tex", "tileright.tex",
    "tilebot.tex", "tiletop.tex", "tilecenter.tex",
)
SYNTHETIC_ROW_FIELDS = {
    "level_header": 0x8E1200,
    "date": (8, 10, 2026),
    "clock": (10, 25),
    "preview_reads": ((0x8E1264, 4), (0x8E126A, 2), (0x8E126C, 1)),
}
CLOCK_BOUNDARIES = (
    (0x00, 0x05, ("%d:%s%d%s", 12, "0", 5, "am")),
    (0x11, 0x10, ("%d:%s%d%s", 11, "", 10, "am")),
    (0x12, 0x00, ("%d:%s%d%s", 12, "0", 0, "pm")),
    (0x13, 0x25, ("%d:%s%d%s", 1, "", 25, "pm")),
    (0x23, 0x59, ("%d:%s%d%s", 11, "", 59, "pm")),
)


def frame_tile_anchors():
    """First frame's source-tile submission anchors with disc header sizes.

    These are calls to 0x17b590/0x17b8b0, before their GPU work.  The second
    wrapper has its final stack flag set and makes no such calls in this fixture.
    """
    anchors = [(0x17C310, 60, 194), (0x17C348, 549, 194),
               (0x17C37C, 60, 121), (0x17C3A4, 549, 121)]
    for column in range(15):
        x = 92 + 32 * column
        anchors.extend(((0x17C418, x, 122), (0x17C45C, x, 195)))
    for y in (154, 186):
        anchors.extend(((0x17C4E0, 60, y), (0x17C524, 549, y)))
    anchors.extend(((0x17C61C, 67, 128), (0x17C61C, 387, 128)))
    return tuple(anchors)
PROMPT_KEYS = {
    5: ((0x21CEDC, "MemcardConfirmOverwrite"),
        (0x21CF54, "MemcardContinueBack")),
    9: ((0x21D234, "MemcardConfirmDelete"),
        (0x21D258, "MemcardDeleteSlot"),
        (0x21D2D4, "MemcardYesBack")),
    15: ((0x21D4F0, "MemcardContinueBack"),
         (0x21D5E8, "MemcardError"),
         (0x21D658, "MemcardMissingError2")),
}
PROMPT_ANCHORS = {
    5: ((0x21CF34, 320, 264), (0x21CFA4, 320, 320)),
    9: ((0x21D24C, 320, 247), (0x21D2B4, 320, 264),
        (0x21D328, 320, 320)),
    15: ((0x21D548, 320, 320), (0x21D638, 320, 196),
         (0x21D6BC, 320, 230)),
}


def slot_rows(count, save=True):
    """Text draw sites for a synthetic slot list with ``count`` cached entries."""
    if count <= 0 and not save:
        return ()
    rows = []
    for row in range(SLOT_VISIBLE):
        y = SLOT_Y + SLOT_PITCH * row
        rows.append((0x21D99C, 0x181AA0, 77, y))
        if row < count:
            rows.extend(((0x21DA8C, 0x181C10, 100, y),
                         (0x21DB24, 0x181AA0, 365, y),
                         (0x21DBE8, 0x181AA0, 487, y)))
        elif save and row == count:
            rows.append((0x21D9F4, 0x181C10, 100, y))  # new save
    return tuple(rows)


def slot_highlight(row):
    y = 133 + SLOT_PITCH * row
    return (0x21E508, 66, y, 574, y + 19, 6, 0x3F366876)


def preview_labels(debug):
    """Localized-key lookup sites of the selected-slot summary."""
    labels = ((0x21DCE4, "MemcardSavePlayers"),
              (0x21DD10, "MemcardDifficulty"))
    if debug:
        labels += ((0x21DD48, "MemcardSaveTime"),)
    return labels


def preview_text(debug):
    """Text anchors of the selected-slot summary, before width shaping."""
    sites = ((0x21DD00, 220, 247), (0x21DD28, 220, 264),
             (0x21E208, 320, 247), (0x21E2C0, 320, 264))
    if debug:
        sites += ((0x21DD60, 100, 281), (0x21E0F0, 320, 281))
    return sites


def slot_action(state, edge, *, selected=0, count=2):
    """One direct-call result under the settled synthetic fixture.

    State 4 is the list, 5 overwrite confirmation, 9 delete confirmation.
    The post-confirm fade and queued card operation are separate steps.
    """
    if state == 4:
        if edge & 0x204000:
            return (4, selected + 1 if selected + 1 < count else selected, 0)
        if edge & 0x40:
            return (5, selected, 0)
        if edge & 0x80:
            return (9, selected, 0)
        return (4, selected, 0)
    if state == 5:
        if edge & 0x20:
            return (4, selected, 0)
        if edge & 0x80:
            return (11, selected, 1)
        return (5, selected, 0)
    if state == 9:
        if edge & 0x20:
            return (4, selected, 0)
        return (9, selected, 0)
    raise ValueError(state)
