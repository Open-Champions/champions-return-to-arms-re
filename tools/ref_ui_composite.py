"""Reference 2D compositor and comparators for UI parity; see docs/ui-parity.md.

Pure Python, no game data. Turns the API-level draw records of ref_ui_layout
(Draw, HudLayer) plus untextured rectangles and text batches into a 640 x 448
logical RGBA picture with the GS state the original's 2D path sets, then
compares pictures or record streams.

Evidence (SLUS-20973 v2.00, EE addresses):
  O  sprite template 0x17a49c..0x17a4f8 (built into 0x7d3140, used by 0x17b658,
     0x17b97c): TEX1_1 = 1 (point), ALPHA_1 = 0x44, PRIM = 0x156, TEST_1 = 0x3001d.
  O  text batch 0x1801ac..0x1801f8: the same TEX1/ALPHA/PRIM/TEST values.
  O  ui_drawRect 0x17bdd0..0x17be1c: ALPHA_1 = 0x44, PRIM = 0x46 (untextured,
     blended), TEST_1 = 0x31001, colour in RGBAQ; corners 0x17be38..0x17be74.
  O  2D packets are prepended per layer (0x16b7f0, queue flag 1); layers 0..7.
  I  GS arithmetic: modulate C = (Ct*Cf) >> 7; blend 0x44 is
     ((Cs - Cd) * As >> 7) + Cd; COLCLAMP = 1 (per-frame default 0x19c86c)
     clamps to 0..255. These follow the GS definition of the register values.
What is NOT modelled by composite(): the 16-bit draw buffer, field selection
and the present pass's 2x2 box filter. dimx_matrix() / dither5() and
present_colour() describe the dither matrix and the present gain; composite()
does not apply them. Those are why raster comparison against a captured
original needs a tolerance (compare()).
"""
from collections import namedtuple
import difflib

import ref_core as F

WIDTH, HEIGHT = 640, 448
NEUTRAL = 0x80808080          # RGBAQ word: R bits 0-7, G 8-15, B 16-23, A 24-31

Texture = namedtuple('Texture', 'width height rgba')     # progressive (woven) rows, GS alpha
Rect = namedtuple('Rect', 'x0 y0 x1 y1 layer color')      # ui_drawRect 0x17bd30: two corners
Blit = namedtuple('Blit', 'resource x y src clip tint layer flip_x flip_y',
                  defaults=(None, NEUTRAL, 6, False, False))
TextBatch = namedtuple('TextBatch', 'glyphs layer')         # text_begin..text_end, one packet
Report = namedtuple('Report', 'max_delta over total bbox first')


def _clamp_clip(clip):
    """Scissor clamp 0x17baac..0x17bb7c / text_setClip 0x1803e0 (O): left and top
    at least 0, right at most 640, bottom at most 447. The result is used as a
    half-open progressive rectangle [L,R) x [T,B): an approximation of the GS
    field scissor (docs/hud-layout.md) - odd bottoms are not raster-exact (I)."""
    if clip is None:
        return (0, 0, WIDTH, HEIGHT)          # per-frame default scissor (0x19c86c), I for plain sprites
    left, top, right, bottom = clip
    return (max(left, 0), max(top, 0), min(right, WIDTH), min(bottom, 447))


def normalize(record, textures, layer=6):
    """One API record -> list of Blit/Rect units in submission order.

    ref_ui_layout.Draw: clip None is a plain ui_drawSpriteImpl call, which adds
    one to y (0x17b6f8, O); with a clip it is the clipped variant 0x17b8b0 that
    does not. HudLayer is always the clipped variant (0x17fb88). Source is the
    whole texture (0x17b79c..0x17b7c4, 0x17bb84..0x17bbf0, O); destination size
    equals source size - clipping cuts, it never stretches.
    """
    if isinstance(record, TextBatch):
        return [TextBatch(tuple(record.glyphs), record.layer)]
    if isinstance(record, (Blit, Rect)):
        return [record]
    fields = getattr(record, '_fields', None)
    if fields == ('resource', 'x', 'y', 'clip', 'tint', 'layer'):
        t = textures[record.resource]
        return [Blit(record.resource, record.x, record.y, (0, 0, t.width, t.height),
                     record.clip, record.tint, record.layer)]
    if fields == ('resource', 'x', 'y', 'clip'):
        t = textures[record.resource]
        y = record.y + 1 if record.clip is None else record.y
        return [Blit(record.resource, record.x, y, (0, 0, t.width, t.height), record.clip,
                     NEUTRAL, layer)]
    raise TypeError('unsupported draw record %r' % (record,))


def painter_order(records, textures, layer=6):
    """Submission order -> GS order. Layers ascend 0..7; inside a layer every 2D
    packet is prepended (0x16b7f0, O), so units come out in reverse submission
    order. A TextBatch is one packet: its glyphs keep their own forward order."""
    units = [u for r in records for u in normalize(r, textures, layer)]
    if any(not 0 <= u.layer <= 7 for u in units):
        raise ValueError('sort layer outside 0..7')
    out = []
    for lay in range(8):
        out.extend(reversed([u for u in units if u.layer == lay]))
    return out


def _unpack(word):
    return (word & 0xff, (word >> 8) & 0xff, (word >> 16) & 0xff, (word >> 24) & 0xff)


def _blend(fb, i, r, g, b, a):
    """ALPHA 0x44 with COLCLAMP: ((Cs-Cd)*As >> 7) + Cd, arithmetic shift (I).
    Destination alpha is replaced by the source alpha (alpha is not blended, I)."""
    for k, cs in enumerate((r, g, b)):
        cd = fb[i + k]
        v = (((cs - cd) * a) >> 7) + cd
        fb[i + k] = 0 if v < 0 else 255 if v > 255 else v
    fb[i + 3] = a if a < 256 else 255


def _draw_blit(fb, u, textures):
    t = textures[u.resource]
    sx, sy, sw, sh = u.src
    if sx < 0 or sy < 0 or sx + sw > t.width or sy + sh > t.height:
        raise ValueError('source rectangle outside texture %s' % u.resource)
    L, T, R, B = _clamp_clip(u.clip)
    tr, tg, tb, ta = _unpack(u.tint)
    for dy in range(sh):
        y = u.y + dy
        if not T <= y < B:
            continue
        ty = sy + (sh - 1 - dy if u.flip_y else dy)
        for dx in range(sw):
            x = u.x + dx
            if not L <= x < R:
                continue
            tx = sx + (sw - 1 - dx if u.flip_x else dx)
            j = 4 * (ty * t.width + tx)
            # TFX modulate, TCC 1 (TEX0 from the texture header, model-texture.md)
            a = min(255, (t.rgba[j + 3] * ta) >> 7)
            if a <= 1:                       # TEST 0x3001d: pass alpha > 1, AFAIL keep
                continue
            _blend(fb, 4 * (y * WIDTH + x), min(255, (t.rgba[j] * tr) >> 7),
                   min(255, (t.rgba[j + 1] * tg) >> 7), min(255, (t.rgba[j + 2] * tb) >> 7), a)


def _draw_rect(fb, u, clip=None):
    """Corners, not corner + size (0x17be38..0x17be74, O). A GS sprite covers
    [x0,x1) x [y0,y1) (I). TEST 0x31001 = alpha test never with AFAIL frame
    buffer only: colour is always blended in, nothing else is tested (O/I)."""
    L, T, R, B = _clamp_clip(clip)
    r, g, b, a = _unpack(u.color)
    for y in range(max(u.y0, T), min(u.y1, B)):
        for x in range(max(u.x0, L), min(u.x1, R)):
            _blend(fb, 4 * (y * WIDTH + x), r, g, b, a)


def composite(records, textures, background=(0, 0, 0, 0x80), layer=6):
    """Records in SUBMISSION order -> bytearray 640*448*4, rows top to bottom,
    GS alpha (0x80 = 1.0). textures maps resource -> Texture (woven, progressive)."""
    fb = bytearray(bytes(background) * (WIDTH * HEIGHT))
    for u in painter_order(records, textures, layer):
        if isinstance(u, Rect):
            _draw_rect(fb, u)
        elif isinstance(u, TextBatch):
            for g in u.glyphs:
                _draw_blit(fb, g, textures)
        else:
            _draw_blit(fb, u, textures)
    return fb


def compare(a, b, width=WIDTH, height=HEIGHT, tolerance=0, mask=(), slack=0):
    """Pixel comparison of two RGBA buffers (alpha ignored: the original's
    16-bit display has none worth comparing). A pixel counts as different when
    any of R,G,B differs by more than tolerance and, with slack > 0, no pixel of
    b within slack rows above or below matches it (field/box-filter edges).
    mask: half-open rectangles (x0,y0,x1,y1) left out, e.g. the 3-D scene.
    Returns Report(max_delta, over, total, bbox (x0,y0,x1,y1) or None, first)."""
    if len(a) != len(b) or len(a) != width * height * 4:
        raise ValueError('buffers differ in size')
    def masked(x, y):
        return any(x0 <= x < x1 and y0 <= y < y1 for x0, y0, x1, y1 in mask)
    def delta(i, j):
        return max(abs(a[i] - b[j]), abs(a[i + 1] - b[j + 1]), abs(a[i + 2] - b[j + 2]))
    worst = over = total = 0
    box = None
    first = None
    for y in range(height):
        for x in range(width):
            if mask and masked(x, y):
                continue
            total += 1
            i = 4 * (y * width + x)
            d = delta(i, i)
            if d > tolerance and slack:
                for s in range(1, slack + 1):
                    if any(0 <= yy < height and delta(i, 4 * (yy * width + x)) <= tolerance
                           for yy in (y - s, y + s)):
                        d = min(d, tolerance)
                        break
            worst = max(worst, d)
            if d > tolerance:
                over += 1
                first = first or (x, y)
                box = (x, y, x + 1, y + 1) if box is None else (
                    min(box[0], x), min(box[1], y), max(box[2], x + 1), max(box[3], y + 1))
    return Report(worst, over, total, box, first)


def diff_records(original, native, textures, layer=6):
    """Draw-record parity: both streams normalised to painter order, aligned,
    and returned as a list of (op, original_units, native_units) for every
    non-equal region ('replace', 'delete', 'insert'). Empty list = parity."""
    a = painter_order(original, textures, layer)
    b = painter_order(native, textures, layer)
    out = []
    for op, i0, i1, j0, j1 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op != 'equal':
            out.append((op, a[i0:i1], b[j0:j1]))
    return out


# Dither and present gain. Not applied by composite(); see docs/ui-parity.md.
# DIMX register id 0x44, DTHE 0x45. The 64-bit matrix is built at 0x19c46c
# (and the same way at 0x17b210, 0x177fcc, 0x190664) and stored as GS data
# with register id 0x44. Per-frame gfx_emitFrameSetup 0x19c9a4 writes DTHE = 1
# and COLCLAMP (0x46) = 1 and does not rewrite DIMX.
DIMX_WORD = 0x3131757531317575
DIMX_REGISTER = 0x44
DTHE_REGISTER = 0x45
BRIGHTNESS_DEFAULT = 0x3f000000      # 0.5, stored by 0x1e6260 when the reset argument is -1
PRESENT_GAIN_HI = 0x3f4ccccc         # 0.8
PRESENT_GAIN_LO = 0x3e4ccccc         # 0.2


def dimx_matrix():
    """4x4 GS DIMX entries, low nibble first. Each nibble's low 3 bits are a
    signed offset in -4..+3 (bit 2 is the sign)."""
    rows = []
    for row in range(4):
        cells = []
        for col in range(4):
            nibble = (DIMX_WORD >> (4 * (row * 4 + col))) & 7
            cells.append(nibble - 8 if nibble & 4 else nibble)
        rows.append(tuple(cells))
    return tuple(rows)


def dither5(channel, x, y):
    """Inferred GS reduction for PSMCT16 with COLCLAMP on: add the matrix
    entry for (x & 3, y & 3), clamp to 0..255, keep the top 5 bits."""
    v = channel + dimx_matrix()[y & 3][x & 3]
    if v < 0:
        v = 0
    if v > 255:
        v = 255
    return v >> 3


def scale_rgb(colour, factor):
    """color_scale 0x19ecac: trunc(channel * factor) clamped to 0..255 for R, G
    and B. The alpha byte is copied unchanged."""
    out = colour & 0xff000000
    for shift in (0, 8, 16):
        value = F.to_int(F.mul(F.from_int((colour >> shift) & 0xff), factor))
        if value < 0:
            value = 0
        if value > 255:
            value = 255
        out |= value << shift
    return out


def present_gain(brightness):
    """0x19ce70..0x19ce94: brightness * 0.8 + 0.2."""
    return F.add(F.mul(brightness, PRESENT_GAIN_HI), PRESENT_GAIN_LO)


def present_channel(value, brightness):
    """0x19ce98..0x19cef4: clamp(trunc(2 * value * gain), 0, 255).

    The double is an add of the product with itself, matching the three
    add.s pairs in gfx_present. value is the integer channel (0x44fd8c / 90 / 94,
    or 128 when gfx_present's third argument is nonzero).
    """
    scaled = F.mul(F.from_int(value), present_gain(brightness))
    n = F.to_int(F.add(scaled, scaled))
    if n < 0:
        n = 0
    if n > 255:
        n = 255
    return n


def present_colour(r, g, b, brightness):
    """Packed word at 0x19cef8: R in bits 0-7 (from f22 / 0x44fd8c), G in 8-15
    (f21 / 0x44fd90), B in 16-23 (f20 / 0x44fd94). No alpha."""
    return (present_channel(r, brightness)
            | (present_channel(g, brightness) << 8)
            | (present_channel(b, brightness) << 16))


def present_channel_step(value):
    """One present moves each of 0x44fd8c/90/94 toward 128 (0x19cf0c..0x19cf94).

    133 and above steps down by 4, below 124 steps up by 4, and 124..132 snaps
    to 128.
    """
    if value >= 0x85:
        return value - 4
    if value >= 0x7c:
        return 0x80
    return value + 4
