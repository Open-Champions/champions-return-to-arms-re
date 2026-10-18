"""Addressed text layout contracts for SLUS-20973 v2.00; see docs/formats/ui-text.md.

Builds on Font/parse_font in ref_ui_layout.py. Strings are sequences of UTF-16
code units as the game's wide strings hold them (ASCII input is zero-extended,
0x19e884). Only 0x0a is special inside a string; there are no colour escapes.
Pen positions of drawn glyphs are returned in HALF logical pixels because the
draw path applies kerning as adjustment/2 (0x180bd8, 0x180c80).
"""
from collections import namedtuple

NEWLINE = 0x0a
NEWLINE_INDEX = 0x7ff          # sentinel index, 0x180b18 / 0x180714
ICON_FIRST, ICON_LAST = 0x5b, 0x68   # glyph INDICES given the neutral tint, 0x180ca0
ICON_RGB = 0x606060
BUDGET_DEFAULT = 100000        # 0x7d35d0 set by text_begin 0x180154 and 0x181a84
FORCED_BREAK = 1000000         # 0x181448 / 0x1816c0: a newline forces the next break
LANGUAGE_PER_CHARACTER = 5     # g_language 0x44fddc value that breaks after any unit


def glyph_index_wide(font, code):
    """Wide lookup shared by 0x180b18..180ba4 and 0x180710..18079c.

    Below 256: the signed map entry when >= 0 (0 included), else the RAW u16 of
    map entry 45 (FNT +0x6e). Above: first glyph whose u16 code matches, 0 when
    none. Newline returns NEWLINE_INDEX. Index <= 0 means "advance by glyph 0".
    """
    if code == NEWLINE:
        return NEWLINE_INDEX
    if code < 0x100:
        index = font.charmap[code]
        return index if index >= 0 else font.charmap[45] & 0xffff
    for i, glyph in enumerate(font.glyphs):
        if glyph[0] == code:
            return i
    return 0


def _kern(font, index, previous):
    """First matching row of index's kerning group, or None (bounded here)."""
    k = font.glyphs[index][7]
    while 0 <= k < len(font.kerns) and font.kerns[k][1] == index:
        if font.kerns[k][0] == previous:
            return font.kerns[k][2]
        k += 1
    return None


def _units(codes, count):
    """The units a counted loop visits: stops at NUL or after count units."""
    out = []
    for code in codes:
        if not code or (count is not None and len(out) >= count):
            break
        out.append(code)
    return out


def measure_wide(font, codes, interlaced=True, count=None):
    """font_measureWide 0x1806f0, logical pixels.

    count=0 returns 0; None means "until NUL". Kerning is adjustment*16 when
    interlaced else *8, in 1/16 units, then arithmetic >>4: interlaced
    measurement counts kerning as WHOLE pixels while drawing applies half.
    A newline adds nothing and does not become the previous glyph (0x1807a4).
    """
    pen, previous = 0, -1
    for code in _units(codes, count):
        index = glyph_index_wide(font, code)
        if index == NEWLINE_INDEX:
            continue
        if index <= 0:
            pen += font.glyphs[0][6] * 16
        else:
            amount = _kern(font, index, previous)
            if amount is not None:
                pen += amount * (16 if interlaced else 8)
            pen += font.glyphs[index][6] * 16
        previous = index
    return pen >> 4


GlyphDraw = namedtuple('GlyphDraw', 'index x_half y source tint')


class TextState:
    """Batch state: colour 0x7d35b8, icon alpha 0x44e020, stored alpha 0x44e024.

    text_begin(font, layer, colour, icon_alpha) sets colour and icon_alpha only
    (0x180164, 0x18015c); a non-temporary text_setColor 0x1802e0 sets all three.
    Both alphas are -1 in the executable's initial data.
    """
    def __init__(self, colour=0x80808080, icon_alpha=-1, stored_alpha=-1):
        self.colour, self.icon_alpha, self.stored_alpha = colour & 0xffffffff, icon_alpha, stored_alpha

    def set_colour(self, colour, alpha=-1):
        self.colour = colour & 0xffffffff
        self.stored_alpha = self.icon_alpha = alpha

    def icon_tint(self):
        """0x180cb0..180ce0: -1 takes the colour's alpha, else alpha = low byte."""
        alpha = (self.colour >> 24) if self.icon_alpha == -1 else self.icon_alpha & 0xff
        return (alpha << 24) | ICON_RGB


def glyph_run(font, x, y, codes, count=None, state=None):
    """Glyph loop 0x1809c0 (via text_drawWideImpl 0x180f80): (draws, end_x_half).

    Pen arithmetic is the same interlaced (1/32 units) and progressive (1/16).
    Nothing is drawn when count==0 or y is outside -100..800 (0x1809f8).
    Destination top = y + glyph y offset; source = (u0, v0, u1-u0, v1-v0) in
    woven logical texels. Indices 0x5b..0x68 are drawn with the icon tint; the
    first ordinary glyph after them, or the end of the run, restores the colour
    and copies the stored alpha into the icon alpha (0x180d00, 0x180f30).
    """
    state = state or TextState()
    if count == 0 or not -100 <= y <= 800:
        return [], 2 * x
    pen, previous, icons, draws = 2 * x, -1, False, []
    for code in _units(codes, count):
        index = glyph_index_wide(font, code)
        if index == NEWLINE_INDEX:
            previous = index
            continue
        if index <= 0:
            pen += 2 * font.glyphs[0][6]
            previous = index
            continue
        _, u0, u1, v0, v1, dy, advance, _ = font.glyphs[index]
        amount = _kern(font, index, previous)
        if amount is not None:
            pen += amount
        if ICON_FIRST <= index <= ICON_LAST:
            tint, icons = state.icon_tint(), True
        else:
            if icons:
                state.icon_alpha, icons = state.stored_alpha, False
            tint = state.colour
        draws.append(GlyphDraw(index, pen, y + dy, (u0, v0, u1 - u0, v1 - v0), tint))
        pen += 2 * advance
        previous = index
    if icons:
        state.icon_alpha = state.stored_alpha
    return draws, pen


Run = namedtuple('Run', 'x y start count')
Wrapped = namedtuple('Wrapped', 'runs height shown')


def _code(codes, i):
    return codes[i] if i < len(codes) else 0


def _word_end(font, codes, cur, max_width, interlaced, language, split):
    if language == LANGUAGE_PER_CHARACTER:
        return cur + (1 if _code(codes, cur) else 0)
    end = cur
    while True:
        c = _code(codes, end)
        if c in (0, 0x20, NEWLINE):
            break
        if split:
            if measure_wide(font, codes[cur:], interlaced, end - cur) < max_width:
                end += 1
                continue
            end -= 1
            c = _code(codes, end)
            break
        end += 1
    return end + 1 if c == 0x20 else end


def _wrap(font, x, y, codes, max_width, clip_top, clip_bottom, line_height,
          interlaced, language, budget, centered):
    if max_width <= 0:
        raise ValueError('nonpositive width is outside the reference domain')
    y0, line_w, cur, start, used, stop, shown, runs = y, 0, 0, 0, 0, False, 0, []
    def flush(y):
        nonlocal used, stop, shown
        n = cur - start if centered else min(cur - start, budget - used)
        if clip_top < y < clip_bottom and not stop:
            dx = x - (measure_wide(font, codes[start:], interlaced, n) >> 1) if centered else x
            runs.append(Run(dx, y, start, n))
            if not centered:
                shown = used + n
        if not centered:
            used += n
            stop = stop or used >= budget
    while _code(codes, cur):
        end = _word_end(font, codes, cur, max_width, interlaced, language, not centered)
        if end == cur and _code(codes, cur) != NEWLINE:
            raise ValueError('no progress: the original loops forever here')
        width = measure_wide(font, codes[cur:], interlaced, end - cur)
        if line_w + width < max_width:
            line_w += width
        else:
            flush(y)
            start, y, line_w = cur, y + line_height, width
        if _code(codes, end) == NEWLINE:
            line_w, end = FORCED_BREAK + line_w, end + 1
        cur = end
    if start < cur:
        flush(y)
        y += line_height
    return Wrapped(runs, y - y0, None if centered else shown)


def draw_wrapped(font, x, y, codes, max_width, clip_top, clip_bottom, line_height,
                 interlaced=True, language=0, budget=BUDGET_DEFAULT):
    """text_drawWrapped 0x181280 (x, y, wstr, width, top, bottom, lineHeight).

    Words end before NUL/newline and after one trailing space; a word is split
    where its prefix stops measuring below width. A line's width includes
    trailing spaces. Visibility is per line origin: top < y < bottom.
    Runs (x, y, start, count) are text_drawWideImpl calls; the newline
    unit stays inside the run (the glyph loop skips it). The character budget
    counts clipped lines too; `shown` is what 0x44e028 holds (0x1812d4 resets it).
    Returns height = y_end - y. A unit wider than the width loops forever in
    the original; this reference raises instead.
    """
    return _wrap(font, x, y, codes, max_width, clip_top, clip_bottom, line_height,
                 interlaced, language, budget, False)


def draw_wrapped_centered(font, x, y, codes, max_width, clip_top, clip_bottom, line_height,
                          interlaced=True, language=0):
    """text_drawWrappedCentered 0x181530: no word splitting and no budget.

    Each drawn run starts at x - (measure_wide(run) >> 1); the run's width
    includes its trailing space, so centring is biased left by half a space.
    """
    return _wrap(font, x, y, codes, max_width, clip_top, clip_bottom, line_height,
                 interlaced, language, BUDGET_DEFAULT, True)


def centered_x_wide(font, x, codes, count=None, interlaced=True):
    """text_drawWideCentered 0x181ca0: x - (width >> 1), arithmetic shift."""
    return x - (measure_wide(font, codes, interlaced, count) >> 1)


def centered_x_ascii(font, x, data, count=None, interlaced=True):
    """text_drawAsciiCentered 0x181af8: ASCII measure, but the WIDE draw.

    Bytes whose map entry is negative measure as glyph 0 (0x17ffb0) yet draw as
    map entry 45's glyph (0x180b54), so centring of such strings drifts.
    """
    return x - (font.width_ascii(data, interlaced, count) >> 1)


def fit_ascii(font, text, width, interlaced=True):
    """ui_fitText 0x1bdf60 / text_truncateToWidth 0x1ec1c0 shortening rule.

    font None (ui_fitText only): width counts characters; when longer, keep
    width-3 characters. Otherwise drop the last byte while width < measured
    width (no room reserved for the ellipsis). Any change appends three
    periods, so a result can exceed width by the ellipsis' width. The
    original copies into a 32-byte slot (0x4f3ec8 + index*32) without a bound.
    """
    text = bytes(text).split(b'\0', 1)[0]
    out = text
    if font is None:
        if width < len(out):
            while width < len(out) + 3 and out:
                out = out[:-1]
    else:
        while out and width < font.width_ascii(out, interlaced):
            out = out[:-1]
    return out + b'...' if len(out) != len(text) else out


def text_scissor(left, top, right, bottom):
    """text_setClip 0x1803e0: (GS SCISSOR inclusive, logical pixel half-open).

    Clamps left/top to >= 0, right to <= 640, bottom to <= 447. X is doubled
    with an inclusive 2*right-1 end; y is NOT field-adjusted and bottom is
    inclusive, unlike the sprite scissor of 0x17baac. text_end 0x180500
    restores (0, [0x44fd74], 640, [0x44fd78]) only if the batch set a clip.
    """
    left, top = max(left, 0), max(top, 0)
    right, bottom = min(right, 640), min(bottom, 447)
    return (2 * left, 2 * right - 1, top, bottom), (left, top, right, bottom + 1)
