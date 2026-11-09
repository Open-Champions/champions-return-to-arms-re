"""Independent semantic reference for bounded character attachment probes.

Observed addresses: cover 0x1a3b90..0x1a3ccc; final gates and body hide-bit
updates 0x1a3e08..0x1a3f30; default/variant mask 0x179550; attachment selection
0x1760ec..0x17614c; mesh runs 0x178cbc..0x178d74. No executable or asset
content is embedded here. Token predicates are supplied by the caller.

Shield variant bits are the executed result of 0x1a3cfc–0x1a3d84. Shell
words are the executed result of 0x1068d8 and the magnitude clamp at
0x1a4cac–0x1a4d08. Starting slot numbers are the published round-4 map;
this module does not re-select item definitions or header metadata.

The body show mask is the argument saved from r10 at 0x1779e4 and walked
at 0x177e34. Creature_draw loads it from object +0x220 at 0x10ba84;
inventory_drawPlayerModel loads it at 0x1c0a28. Both loads happen before
the same caller's Player_drawEquipped. Shell packets are 0x174e78.
Animated joint matrices, renderer output, and live visual parity remain
unknown. Invalid indices are outside the authored 16-record
attachment-table boundary, not clamped.
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


# Creation-screen formats. The bytes are read from the executable at runtime;
# these are only the addresses. Standing restart is 0x2254bc–0x2255b4.
INTRO_STANDING = 0x53ff68
INTRO_STANDING_MARKED = 0x53ff58
INTRO_ONCE = 0x5400c8
INTRO_OTHER = 0x540330
IMPORT_LITERAL = 0x53fd38
# Jump index is the signed byte at 0x8e2c91 plus one, and only 0..12 are copied.
RACE_LITERALS = (
    0x53fdc0, 0x53fdc0, 0x53fdc8, 0x53fde0, 0x53fe10, 0x53fe18, 0x53fe40,
    0x53fe48, 0x53fe78, 0x53fe80, 0x53fea0, 0x53fd98, 0x53fd70,
)
# Model index -> inventory lump name. Class -> idle filename, with the
# leftover classes sharing the last address. Display-only play uses idled.
INVENTORY_LUMP = (
    0x538488, 0x538478, 0x538508, 0x5384d8, 0x5384f8, 0x5384c8,
    0x5384a8, 0x5384e8, 0x538498, 0x5384b8, 0x538518, 0x538528,
)
INVENTORY_IDLE = {1: 0x538538, 2: 0x538548, 3: 0x538558, 4: 0x538568,
                  5: 0x538578, 7: 0x538588}
INVENTORY_IDLE_DEFAULT = 0x538598
DISPLAY_IDLE = {1: 0x5375d8, 2: 0x5375e8, 3: 0x5375f8, 4: 0x537608, 7: 0x537618}
DISPLAY_IDLE_DEFAULT = 0x537628
K_STEP = 0x3f7fffff
BLEND_FORCED = 0x3f800000


def race_literal(index_byte):
    """Address copied when the descriptor name matches 0x53fd38. None keeps the input."""
    slot = index_byte + 1
    if not 0 <= slot < len(RACE_LITERALS):
        return None
    return RACE_LITERALS[slot]


def creation_clip_name(race, format_bytes):
    """The four creation formats are a leading %s plus a fixed suffix."""
    if not format_bytes.startswith(b'%s'):
        raise ValueError('creation format is not a single leading substitution')
    return race + format_bytes[2:]


def inventory_idle_address(weapon_class):
    return INVENTORY_IDLE.get(weapon_class, INVENTORY_IDLE_DEFAULT)


def display_idle_address(weapon_class):
    return DISPLAY_IDLE.get(weapon_class, DISPLAY_IDLE_DEFAULT)


def play_idle_offsets(weapon_class):
    """Clip pointers filled into cells 0..3 by 0x1b2470. Row stride is 0x68."""
    base = weapon_class * 0x68
    return tuple(base + off for off in (0x44, 0x4c, 0x54, 0x5c))


def unit_advance(flags, time_bits, weight_bits, rate_bits, speed_bits, length):
    """One anim_advance step for a non-root track that does not end.

    Time adds the fixed step when flag 0x40 is set, otherwise speed times that
    step. Weight adds the rate; flag 0x40 does not scale that add by speed.
    The caller guarantees the result stays below the clip length.
    """
    step = K_STEP if flags & 0x40 else _f_mul(speed_bits, K_STEP)
    scale = BLEND_FORCED if flags & 0x40 else speed_bits
    return _f_add(time_bits, step), _f_add(weight_bits, _f_mul(rate_bits, scale))


def _sra(value, shift):
    value &= 0xffffffff
    if value & 0x80000000:
        value -= 0x100000000
    return value >> shift


def shell_directory(model):
    """First boundary word read by 0x174e78. The walked table index is 0."""
    return model + 0x28


def shell_packet(start, model, mode, records, boundaries, alpha_bits, fill=0xa5):
    """Bytes 0x174e78 writes for a model whose flag 0x20 is already known set.

    `records` is a sequence of (rgba word, float bits). `boundaries` is the
    table-0 fence, one past the mesh count. `alpha_bits` is the qword at
    model+0x18, copied into the trailer. The image is prefilled so unwritten
    bytes stay distinguishable. Returns (final cursor, image).
    """
    count = len(boundaries) - 1
    if not 1 <= count <= 63:
        raise ValueError('shell mesh count is outside the walked range')
    image = bytearray([fill]) * 0x2000
    base = start

    def sb(addr, value):
        image[addr - base] = value & 0xff

    def sw(addr, value):
        for i in range(4):
            sb(addr + i, (value >> (8 * i)) & 0xff)

    def sd(addr, value):
        for i in range(8):
            sb(addr + i, (value >> (8 * i)) & 0xff)

    def ld(addr):
        return sum(image[addr - base + i] << (8 * i) for i in range(8))

    def lw(addr):
        return sum(image[addr - base + i] << (8 * i) for i in range(4))

    cursor = [start]
    saved = [0, 0, 0]

    def set_cursor(value):
        cursor[0] = value

    p = start
    saved[0] = p
    p += 8
    while p & 0xf != 0xc:
        sb(p, 0)
        p += 1
    block = p
    sd(block + 4, 0x1000000000008000)
    sd(block + 12, 0xe)
    sw(block, 0x50000000)
    sd(block + 0x14, 0)
    sd(block + 0x1c, 0x1a)
    saved[1] = block + 4
    sd(block + 0x2c, 0x1b)
    saved[2] = block
    sd(block + 0x24, 0x48)
    if (mode << 24) >> 24:
        sd(block + 0x34, 0x48)
    else:
        sd(block + 0x34, 0x44)
    sd(block + 0x3c, 0x42)
    p = block + 0x44
    end = p + 0x10
    sd(p + 8, 0x47)
    sd(p, 0x71001)
    first = _sra(_sra(end - saved[1], 3) - 2, 1) & 0xffffffff
    second = _sra((end - saved[2]) - 4, 4) & 0xffffffff
    third = _sra(_sra(end - saved[0], 3) - 2, 1) & 0xffffffff
    sd(saved[1], ld(saved[1]) | first)
    sw(saved[2], lw(saved[2]) | second)
    sd(saved[0], third | 0x10000000)
    set_cursor(end)
    if len(records) <= 0:
        packet = end
    else:
        packet = end
        for rgba, float_bits in records:
            sw(packet + 0x14, float_bits)
            sw(packet + 8, 0x13000000)
            sw(packet + 0xc, 0x6002c000)
            sw(packet + 0x10, 1)
            sw(packet + 0x18, 0x6e01c002)
            for i in range(4):
                sb(packet + 0x1c + i, (rgba >> (8 * i)) & 0xff)
            sw(packet + 0x20, 0x1400002a)
            cursor_slot = packet
            aligned = packet + 0x24
            set_cursor(aligned)
            while aligned & 0xf:
                sb(aligned, 0)
                aligned += 1
            set_cursor(aligned)
            patched = _sra(_sra(aligned - cursor_slot, 3) - 2, 1) & 0xffffffff
            sd(cursor_slot, patched | 0x10000000)
            mask = (~(1 << count)) & U64
            for origin, size in mesh_runs(tuple(boundaries), mask):
                word = (origin << 32) | ((size >> 4) & 0xffff) | 0x30000000
                sd(aligned, word)
                sd(aligned + 8, 0)
                aligned += 0x10
            packet = aligned
            set_cursor(packet)
    trailer = packet
    sw(trailer + 8, 0x13000000)
    sw(trailer + 0xc, 0x6001c000)
    sw(trailer + 0x14, 0x1400002a)
    sw(trailer + 0x10, 0)
    aligned = trailer + 0x18
    if aligned & 0xf != 0xc:
        while aligned & 0xf != 0xc:
            sb(aligned, 0)
            aligned += 1
    restore = aligned
    sd(restore + 4, 0x1000000000008000)
    sd(restore + 12, 0xe)
    sd(restore + 0x14, 1)
    sd(restore + 0x1c, 0x1a)
    sd(restore + 0x2c, 0x42)
    sd(restore + 0x24, alpha_bits & U64)
    sd(restore + 0x3c, 0x47)
    sd(restore + 0x34, 0x507f5)
    final = restore + 0x44
    span = _sra(_sra(final - (restore + 4), 3) - 2, 1) & 0xffffffff
    head = _sra((final - restore) - 4, 4) & 0xffffffff
    sd(restore + 4, ld(restore + 4) | span)
    sw(restore, head | 0x50000000)
    # 0x175314 stores a fresh qword: the qword count of the trailer, with 0x10000000.
    sd(trailer, (_sra(_sra(final - trailer, 3) - 2, 1) & 0xffffffff) | 0x10000000)
    return final, bytes(image[:final - start])


# ---------------------------------------------------------------------------
# Round 5 additions: float bits, the preview body mask, VU1 joint and attach
# matrices. Nothing above this line changed.
# ---------------------------------------------------------------------------
import struct as _struct


def f32(bits):
    return _struct.unpack('<f', _struct.pack('<I', bits & 0xffffffff))[0]


def f32_bits(value):
    return _struct.unpack('<I', _struct.pack('<f', value))[0]


def preview_body_mask(hair_hide, beard_hide, item_hides):
    """0x224d80: all 64 bits, minus the chosen hair's hide qword, the chosen
    beard's, then each loaded preview item's, in that order. None means the
    choice is -1 or its pointer slot is empty."""
    mask = U64
    for hide in (hair_hide, beard_hide):
        if hide is not None:
            mask &= ~hide
    for hide in item_hides:
        mask &= ~hide
    return mask & U64


def _vu_ops():
    """VU1 adds and multiplies as tools/vu1_emu.py models them ('chop')."""
    import ee_emu
    from vu1_emu import vu_in, vu_out

    def add(a, b):
        return vu_out(ee_emu.fp_add(vu_in(a), vu_in(b), 'chop'))

    def mul(a, b):
        return vu_out(ee_emu.fp_mul(vu_in(a), vu_in(b), 'chop'))

    def itof(word, shift):
        scale = ee_emu.float_to_raw(1.0 / (1 << shift))
        return mul(ee_emu.fp_from_int(word & 0xffffffff, 'chop'), scale)
    return add, mul, itof


def pose_qwords(rows):
    """Entry 0x3a: one joint's three pose-buffer rows of s16 (r0, r1, r2, t)
    become three float qwords: xyz / 4096 (ITOF12), w / 16 then * 0.25."""
    add, mul, itof = _vu_ops()
    out = []
    for row in rows:
        lanes = [itof(v, 12) for v in row[:3]]
        lanes.append(mul(itof(row[3], 4), 0x3e800000))
        out.append(lanes)
    return out


def _combine(add, mul, rows, coefficients, last=None):
    """MULA, MADDA..., MADD in order: sum_k rows[k] * coefficients[k], plus an
    optional fourth row times 1 (vf0.w)."""
    acc = [mul(rows[0][i], coefficients[0]) for i in range(4)]
    terms = list(zip(rows[1:], coefficients[1:]))
    if last is not None:
        terms.append((last, 0x3f800000))
    for row, c in terms:
        acc = [add(acc[i], mul(row[i], c)) for i in range(4)]
    return acc


def vu_joint(pose, transform):
    """Entry 0x0c for one joint. pose: the three qwords of pose_qwords.
    transform: the four rows vf1..vf4 loaded by entry 0x02. Row c of the
    joint matrix is T0*p0[c] + T1*p1[c] + T2*p2[c], and row 3 adds T3."""
    add, mul, _itof = _vu_ops()
    rows = []
    for c in range(4):
        coefficients = [pose[0][c], pose[1][c], pose[2][c]]
        rows.append(_combine(add, mul, transform[:3], coefficients,
                             transform[3] if c == 3 else None))
    return rows


def attach_qwords(values, mirrored=False):
    """The three V4-32 rows model_emitPartSetup uploads after the joint word:
    row k is (v[k], v[3+k], v[6+k], v[9+k]); mirroring negates v[0..2]."""
    v = list(values)
    if mirrored:
        for i in range(3):
            v[i] ^= 0x80000000
    return [[v[k], v[3 + k], v[6 + k], v[9 + k]] for k in range(3)]


def vu_attach(joint, attach):
    """Entry 0x1a: slot 0 row c = J0*A0[c] + J1*A1[c] + J2*A2[c], and row 3
    adds J3. joint: the four rows at qword joint*4. attach: attach_qwords."""
    add, mul, _itof = _vu_ops()
    rows = []
    for c in range(4):
        coefficients = [attach[0][c], attach[1][c], attach[2][c]]
        rows.append(_combine(add, mul, joint[:3], coefficients,
                             joint[3] if c == 3 else None))
    return rows
