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


# The draw above records a stubbed lookup return of 0 and therefore a fixed y.
# The page adds each text_drawWrapped return into y. FIELD layout matches the
# player record: eight 0x40-byte entries, title then body, 0x20 bytes each.
FIELD = 0x20
ENTRY = 0x40
SLOTS = 8
PLACEHOLDER = b"NoQuests\0"
TITLE_COLOUR = 0x80323C3C
BODY_COLOUR = 0x802D2D2D
FONT_WORD = 0x4F7104
EMPTY_DRAW = (160, 224, 1000000)
WRAP_TAIL = (288, 82, 418, 21)


def cstr(field):
    raw = bytes(field)
    end = raw.find(b"\0")
    if end < 0:
        return raw.decode("latin1")
    return raw[:end].decode("latin1")


def write_cstr(field, text):
    """strcpy into a 32-byte field. Bytes after the new terminator stay."""
    raw = text.encode("latin1").split(b"\0", 1)[0] + b"\0"
    if len(raw) > FIELD:
        raise ValueError("quest field overrun")
    out = bytearray(field)
    out[:len(raw)] = raw
    return bytes(out)


def overlay(field):
    out = bytearray(field)
    out[:len(PLACEHOLDER)] = PLACEHOLDER
    return bytes(out)


def blank_record():
    return {"count": 0, "titles": [bytes(FIELD) for _ in range(SLOTS)],
            "bodies": [bytes(FIELD) for _ in range(SLOTS)]}


def quest_add(records, num_players, title, text):
    """quest_add 0x1d386c. Stops the call at the first full list or duplicate title."""
    for slot in range(max(num_players, 0)):
        rec = records[slot]
        count = rec["count"]
        if count > 7:
            return records
        for index in range(max(count, 0)):
            if cstr(rec["titles"][index]) == title:
                return records
        rec["titles"][count] = write_cstr(rec["titles"][count], title)
        rec["bodies"][count] = write_cstr(rec["bodies"][count], text)
        rec["count"] = count + 1
    return records


def quest_remove(records, num_players, title):
    """quest_remove 0x1d3968. One slide from the last match; the count drops by one."""
    for slot in range(max(num_players, 0)):
        rec = records[slot]
        last = -1
        index = 0
        while index < rec["count"]:
            if cstr(rec["titles"][index]) == title:
                rec["titles"][index] = overlay(rec["titles"][index])
                rec["bodies"][index] = overlay(rec["bodies"][index])
                last = index
            index += 1
        if last != -1:
            while last < rec["count"] - 1:
                rec["titles"][last] = write_cstr(rec["titles"][last], cstr(rec["titles"][last + 1]))
                rec["bodies"][last] = write_cstr(rec["bodies"][last], cstr(rec["bodies"][last + 1]))
                last += 1
            rec["count"] -= 1
    return records


def quest_clear(records, num_players):
    """quest_clearAll 0x1d3adc. Overlay the used entries of the first num_players records."""
    for slot in range(max(num_players, 0)):
        rec = records[slot]
        for index in range(max(rec["count"], 0)):
            rec["titles"][index] = overlay(rec["titles"][index])
            rec["bodies"][index] = overlay(rec["bodies"][index])
        rec["count"] = 0
    return records


def row_positions(title_returns, body_returns):
    """Y of each title and body. The page adds the wrap return, then 22 after the body."""
    if len(title_returns) != len(body_returns):
        raise ValueError("one return pair per entry")
    y = ROW_TOP
    rows = []
    for title_return, body_return in zip(title_returns, body_returns):
        title_y = y
        y += title_return
        body_y = y
        y += body_return + ROW_STEP
        rows.append((title_y, body_y))
    return rows
