"""Bounded reference for the original inventory quest page's draw submissions.

The strings here are synthetic localization keys, never game prose. Coordinates
are UI call arguments, not measured pixels or a rendered frame.
"""

MAX_QUESTS = 8
ROW_TOP = 114
ROW_STEP = 22
TEXT_BOX = (24, 0, 288, 82, 418, 21)
PARCHMENT = (320, 350)


def lookups(count):
    if not 0 <= count <= MAX_QUESTS:
        raise ValueError(count)
    if count == 0:
        return [(0x1D27DC, "NoQuests")]
    return [(site, "%s%d" % (kind, i))
            for i in range(count)
            for site, kind in ((0x1D2708, "Q"), (0x1D275C, "B"))]


def wrapped_calls(count):
    return [(site, (TEXT_BOX[0], ROW_TOP + ROW_STEP * i, *TEXT_BOX[1:]))
            for i in range(count)
            for site in (0x1D272C, 0x1D2784)]
