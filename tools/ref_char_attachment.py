"""Independent semantic reference for bounded character attachment probes.

Observed addresses: cover 0x1a3b90..0x1a3ccc; final gates and body hide-bit
updates 0x1a3e08..0x1a3f30; default/variant mask 0x179550; attachment selection
0x1760ec..0x17614c; mesh runs 0x178cbc..0x178d74. No executable or asset
content is embedded here. Token predicates are supplied by the caller.

Shield variant bits are the executed result of 0x1a3cfc–0x1a3d84. Shell
words are the executed result of 0x1068d8 and the magnitude clamp at
0x1a4cac–0x1a4d08. Starting slot numbers are the published round-4 map;
this module does not re-select item definitions or header metadata.

Unknown: native-frame body-mask consumption, animated matrix evaluation,
the shell primitive at 0x174e78, renderer output, and live visual parity.
Invalid indices are outside the authored 16-record attachment-table
boundary, not clamped.
"""

U64 = (1 << 64) - 1


def cover_flag(model, slot, prior, paired, hits):
    """Five semantic substring predicates, in pinned-address order in harness."""
    if not paired:
        return bool(prior)
    n0, p1, p2, n3, p4 = hits
    head_cover = slot == 11 and not n0 and (model != 7 or not p1)
    body_cover = slot == 4 and ((model == 7 and p2) or
                               (model == 9 and (n3 or p4)))
    return bool(prior or head_cover or body_cover)


def appearance_gates(model, skin, covered, head_present, head_exception):
    hair = not covered or model == 11 or (model == 10 and skin == 4)
    beard = not covered or model == 11 or (head_present and
                                         (head_exception or model == 6))
    return hair, beard


def appearance_draws(model, skin, covered, head_present, head_exception, handles):
    """Return part ordinals; each pair is (mesh present, texture present)."""
    allowed = appearance_gates(model, skin, covered, head_present, head_exception)
    return tuple(i for i in range(2) if allowed[i] and all(handles[i]))


def clear_drawn_hide_bits(show, drawn_hide_masks):
    for hide in drawn_hide_masks:
        show &= ~hide
    return show & U64


def variant_show_mask(default_hidden, enabled, selection, records):
    """0x179550: ascending selected bits; each record's hide wins its show."""
    show = ~default_hidden & U64
    if enabled:
        for index, (add, hide) in enumerate(records):
            if (selection & 0xffffffff) & (1 << index):
                show = (show | add) & ~hide & U64
    return show


def initial_body_mask(counter, default_hidden, enabled, records):
    signed = (counter & 0xffffffff)
    if signed >= 0x80000000:
        signed -= 1 << 32
    return (U64 if signed < 0x111 else
            variant_show_mask(default_hidden, enabled, 1, records))


def attachment_index(header_index, override):
    """Header -1 disables attachment before override is considered."""
    if header_index == -1:
        return None
    index = header_index if override == -1 else override
    if not 0 <= index < 16:
        raise ValueError('outside authored attachment table')
    return index


def attachment_matrix(values, mirrored=False):
    """Nine row-major rotation values then origin -> packet's 3x4 matrix."""
    return tuple((-values[col] if mirrored else values[col]) if row == 0
                 else values[3 * row + col]
                 for col in range(3) for row in range(4))


def mesh_table_index(requested, count):
    if count < 1:
        raise ValueError('unrelocated or invalid table count')
    return min(max(requested, 0), count - 1)


def mesh_runs(boundaries, show_mask):
    """Visible adjacent mesh ranges coalesce, empty spans emit no reference."""
    count = len(boundaries) - 1
    if not 1 <= count <= 64:
        raise ValueError('outside authored mesh-count boundary')
    show_mask &= U64
    # Observed EE boundary: a variable 64-bit shift by 64 clears bit zero;
    # arithmetic right shifts repeat bit 63, so a final shown run never flushes.
    # This is original packet selection, not a correction of that behavior.
    if count == 64:
        show_mask &= ~1
        if show_mask & (1 << 63):
            tail = 63
            while tail > 0 and show_mask & (1 << (tail - 1)):
                tail -= 1
            show_mask &= (1 << tail) - 1
    result = []
    start = None
    for i in range(len(boundaries)):
        shown = i < len(boundaries) - 1 and bool(show_mask & (1 << i))
        if shown and start is None:
            start = boundaries[i]
        if not shown and start is not None:
            if boundaries[i] != start:
                result.append((start, boundaries[i] - start))
            start = None
    return tuple(result)


# Body model 0..11 -> shield variant bit. Models that fail the unsigned
# `< 12` test at 0x1a3d00 use bit 0. Pairs that share a class do not share
# a bit; the client indexes this by body model, not by class.
_SHIELD_VARIANT_BIT = (1, 0, 9, 8, 7, 6, 5, 4, 3, 2, 1, 9)

# Published by starting-equipment round 4, not re-derived here.
# Body -> (class index, weapon pointer slot). Armor pointers are 4, 10, 12.
_STARTING_CLASS_WEAPON = (
    (0, 0), (0, 0), (3, 2), (3, 2), (1, 0), (1, 0),
    (4, 2), (4, 2), (2, 0), (2, 0), (5, 0), (6, 0),
)
ARMOR_POINTER_SLOTS = (4, 10, 12)
SHELL_BLOCK = 0x3e9cd0
SHELL_POINTER = 0x41c160
SHELL_COUNT = 0x41c164


def shield_variant_bit(model):
    model &= 0xffffffff
    if model >= 12:
        return 0
    return _SHIELD_VARIANT_BIT[model]


def shield_selection(model):
    """Low 32 bits passed to 0x179550. Bits 0..9 only; no sign extension."""
    return 1 << shield_variant_bit(model)


def starting_visual_slots(body):
    """Class index plus the four equipped pointer slots for that body."""
    if not 0 <= body < 12:
        raise ValueError('outside the published 12-body map')
    class_index, weapon = _STARTING_CLASS_WEAPON[body]
    return class_index, (weapon,) + ARMOR_POINTER_SLOTS


def equipped_override(pointer_slot):
    """Second equipment pointer only. Definition slot is not this test."""
    return 1 if pointer_slot == 1 else -1


def _f_unpack(raw):
    raw &= 0xffffffff
    exp = (raw >> 23) & 0xff
    if exp == 0:
        return raw >> 31, 0, 0
    return raw >> 31, (raw & 0x7fffff) | 0x800000, exp


def _f_pack(sign, mag, e2):
    if mag == 0:
        return sign << 31
    shift = mag.bit_length() - 24
    if shift > 0:
        mantissa = mag >> shift
    else:
        mantissa = mag << -shift
    exp = e2 + shift + 150
    if exp > 255:
        return (sign << 31) | 0x7fffffff
    if exp < 1:
        return sign << 31
    return (sign << 31) | (exp << 23) | (mantissa & 0x7fffff)


def _f_add(a, b):
    """R5900 add: six extra mantissa bits, then truncate toward zero."""
    sa, ma, ea = _f_unpack(a)
    sb, mb, eb = _f_unpack(b)
    if ma == 0 and mb == 0:
        return (sa & sb) << 31
    if ma == 0:
        return b & 0xffffffff
    if mb == 0:
        return a & 0xffffffff
    if ea < eb:
        sa, sb, ma, mb, ea, eb = sb, sa, mb, ma, eb, ea
        a = b
    diff = ea - eb
    if diff >= 25:
        return a & 0xffffffff
    big = -ma if sa else ma
    small = -mb if sb else mb
    man = (big << 6) + ((small << 6) >> diff)
    if man == 0:
        return 0
    mag = -man if man < 0 else man
    exp = ea - 6
    shift = mag.bit_length() - 24
    if shift > 0:
        mag >>= shift
    else:
        mag <<= -shift
    exp += shift
    sign = 1 if man < 0 else 0
    if exp > 255:
        return (sign << 31) | 0x7fffffff
    if exp < 1:
        return sign << 31
    return (sign << 31) | (exp << 23) | (mag & 0x7fffff)


def _f_sub(a, b):
    return _f_add(a, (b ^ 0x80000000) & 0xffffffff)


def _f_mul(a, b):
    sa, ma, ea = _f_unpack(a)
    sb, mb, eb = _f_unpack(b)
    sign = sa ^ sb
    if ma == 0 or mb == 0:
        return sign << 31
    return _f_pack(sign, ma * mb, ea + eb - 300)


def _f_from_int(word):
    value = word & 0xffffffff
    if value >= 0x80000000:
        value -= 0x100000000
    if value == 0:
        return 0
    if value < 0:
        return _f_pack(1, -value, 0)
    return _f_pack(0, value, 0)


def _f_cmp(a, b):
    def key(raw):
        raw &= 0xffffffff
        mag = raw & 0x7fffffff
        return -mag if raw & 0x80000000 else mag
    left, right = key(a), key(b)
    return (left > right) - (left < right)


def _f_trunc(raw):
    sign, man, exp = _f_unpack(raw)
    if man == 0:
        return 0
    if exp >= 158:
        return -0x80000000 if sign else 0x7fffffff
    shift = exp - 150
    mag = man << shift if shift >= 0 else man >> -shift
    return -mag if sign else mag


def equipped_draw_argument(projection_bits):
    """f12 at the 0x1a3580 call from 0x1a4d08.

    The value already in f0 is a projection. This is its absolute value,
    then 5, or 5 minus (360 - magnitude) * the constant at 0x1a4cdc, and
    at least 1 while magnitude is below 360. The three factors that produce
    the projection are not named here.
    """
    magnitude = projection_bits & 0x7fffffff
    argument = 0x40a00000
    if _f_cmp(magnitude, 0x43b40000) < 0:
        span = _f_sub(0x43b40000, magnitude)
        argument = _f_sub(0x40a00000, _f_mul(span, 0x3c93e93e))
        if _f_cmp(argument, 0x3f800000) < 0:
            argument = 0x3f800000
    return argument


def inventory_draw_argument():
    """Constant f12 loaded at 0x1c0c64 before the other 0x1a3580 caller."""
    return 0x3fc00000


def shell_fields(flag33, argument_bits):
    """0x1068d8. Bit 33 clear leaves the block bytes alone and stores count 0.

    Bit 33 set always scales from the constant 7 returned by 0x1046c4, not
    from an item level. Bytes +3 and +11 are that scale times 64 and 72.
    Floats +4 and +12 are the draw argument times 200 and 100. The pointer
    stored at 0x41c160 is the block itself in both cases. Other block bytes
    are not written.
    """
    if not flag33:
        return SHELL_BLOCK, 0, None
    scale = _f_add(_f_mul(_f_from_int(7), 0x3ccccccc), 0x3f199999)
    if _f_cmp(0x3f800000, scale) < 0:
        scale = 0x3f800000
    fields = {
        3: _f_trunc(_f_mul(scale, 0x42800000)) & 0xff,
        11: _f_trunc(_f_mul(scale, 0x42900000)) & 0xff,
        4: _f_mul(argument_bits & 0xffffffff, 0x43480000),
        12: _f_mul(argument_bits & 0xffffffff, 0x42c80000),
    }
    return SHELL_BLOCK, 2, fields
