"""Frontend art draw contracts for SLUS-20973 v2.00.

Only authored fixture data and numeric draw submissions live here.  Class art and
the movie are not ordinary UI sprites in the executed paths; see the evidence
limits in docs/frontend-layout.md.
"""

SEEDS = (20973, 7)

# playerSel_task 0x225478, phase 1, with 0x22a968 and 0x22a83c followed.
CLASS_HELPERS = ((0x2257AC, 0x22A968), (0x2258C8, 0x22A83C))
CLASS_FRAMES = ((0x2297B8, 21, 18, 0, 355, 6, 0x08000000, 1),
                (0x229958, 300, 402, 40, 32, 6, 0x08000000, 0))

# menuList_draw 0x1a07c4: the zero-width-text main-list fixture, selected row 0.
# Each call is (site, x, y, width, height, layer, tint, style).
MENU_CURSOR = (0x1A1104, 300, 259, 40, 33, 7, 0x300000FF, 0)
CURSOR_LUMP = "interfac.lmp"
# Format strings read at 0x5340b8–0x534138. The style-0 prefix is not executed here.
CURSOR_PIECES = ("%stopleft.tex", "%stopright.tex",
                 "%sbotleft.tex", "%sbotright.tex",
                 "%sleft.tex", "%sright.tex", "%sbot.tex",
                 "%stop.tex", "%scenter.tex")


def slot_rows(count):
    """At most five rows from memcard_slotList 0x21c3a4, state 4.

    `count` is the planted list count; record validity is not established.
    For rows past a nonzero count only the first column's marker is submitted.
    """
    out = []
    if count == 0:
        return ()
    for row in range(5):
        y = 128 + 17 * row
        out.append((0x21D99C, 0x181AA0, 77, y))
        if row < count:
            out.extend(((0x21DA8C, 0x181C10, 100, y),
                        (0x21DB24, 0x181AA0, 365, y),
                        (0x21DBE8, 0x181AA0, 487, y)))
    return tuple(out)


def slot_highlight(row):
    """Rectangle at 0x21e508 driven by word 0x879e28; x2/y2 are endpoints."""
    y = 133 + 17 * row
    return (0x21E508, 66, y, 574, y + 19, 6, 0x366876)


def credits_lines(scroll_y, count):
    """Two text submissions for each of `count` UTF-16 line pointers, 19 apart."""
    return tuple(item for row in range(count) for item in (
        (0x22401C, 322, scroll_y + 19 * row + 2),
        (0x224044, 320, scroll_y + 19 * row)))


# movie_update 0x3205ec, zeroed decode fixture. 0x352c60 is FlushCache,
# 0x34fe78 is sceGsSyncPath, and 0x3201b0 starts a GIF DMA chain. The
# 0x80808080 second argument at 0x320d44 is stale, not a colour. Targets
# 0x3502e8 and 0x350618 and argument 0x8eb0e0 remain unknown here.
MOVIE_DRAW_CALLS = ((0x320D44, 0x352C60, 0, 0x80808080),
                    (0x320D4C, 0x3502E8, 2, 0x80808080),
                    (0x320D5C, 0x34FE78, 0, 0),
                    (0x320D68, 0x3201B0, 0, 0),
                    (0x320D74, 0x34FE78, 0, 0),
                    (0x320D84, 0x350618, 0, 0x8EB0E0),
                    (0x320D90, 0x34FE78, 0, 0))
INTRO_RESOURCES = ((0x3217BC, "porko_l.vag"),
                   (0x3217C8, "porko.lmp"))

# Read-only structural counts from the private disc; no content is retained.
CREDITS_LINE_COUNTS = {"credits.txt": 360, "credits_de.txt": 360,
                       "credits_fr.txt": 362, "credits_sp.txt": 361}
MOVIE_SEQUENCE_SIZES = {"porko0.m2v": (640, 448),
                        "porko000.m2v": (640, 480)}
