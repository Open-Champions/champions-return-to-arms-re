"""Experience bar inputs and a new character's current health and mana; SLUS-20973 v2.00.

See docs/spec/hud-xp.md. Pure Python, standard library and tools/ref_core.py only.
No game data is embedded: the experience table and class constants are inputs.

Part A: the experience slice of hud_drawPlayerStatus 0x1d9cd4 (0x1da1dc-0x1da2bc), the
scissor the clipped drawer 0x17b8b0 builds from its clip (0x17baac-0x17bb7c), and the
measured shape of the eleven bar_green textures in HUD.LMP.

Part B: what player_initNewCharacter 0x1b1d70 leaves in record +0xac/+0xb0/+0xc0/+0xc4,
the clamp in player_recalcStats 0x1b6458 (0x1b6a24-0x1b6a48), and player_respawn
0x1bd040's health store.

Floats are raw 32-bit patterns, as in ref_core.
"""
from collections import namedtuple

import ref_core as F

M32 = 0xFFFFFFFF
M64 = 0xFFFFFFFFFFFFFFFF

# ---- Part A: experience bar -----------------------------------------------------------
XP_TABLE = 0x41B558          # g_expTable, s32[81]; upper = [ack] read at 0x1da238
XP_TABLE_LOWER = 0x41B554    # lower = word at 0x41b554 + 4*ack, i.e. [ack-1], read at 0x1da240
XP_TABLE_WORDS = 81          # docs/data-tables.md 4.4
XP_NAME_FORMAT = 'bar_green%02d.tex'   # string at 0x53c428, sprintf 0x3b7ef0 at 0x1da210
SIM_TICK = 0x44FDCC          # read at 0x1da1f4
FRAMES = 11                  # divisor at 0x1da1f8
FILL_SCALE = 99              # integer 0x63 at 0x1d9eac, converted at 0x1da24c
X_INSET = 15                 # bar origin S = X + 15 (0x1d9e68 adds 7, 0x1da254 adds 8)
XP_Y = 56                    # 0x38 at 0x1da284
CLIP_TOP = 24                # 0x18 at 0x1da2a0
CLIP_BOTTOM = 124            # 0x7c stored to the stack at 0x1da27c
LAYER = 6                    # 0x1da288
XP_TINT = 0x80808080         # 0x1da280 / 0x1da298
REC_ACK_LEVEL = 0x58         # s8, read at 0x1da1dc and 0x1da21c
REC_LEVEL = 0x59             # s8, the level earned (not read by this slice)
REC_XP = 0x5C                # s32, read at 0x1da244

XpLayer = namedtuple('XpLayer', 'resource x y clip tint layer')


def s32(value):
    value &= M32
    return value - 0x100000000 if value & 0x80000000 else value


def s8(value):
    value &= 0xFF
    return value - 0x100 if value & 0x80 else value


def xp_frame(tick):
    """(tick >> 2) % 11 with the C remainder (sign of the dividend); 0x1da204-0x1da20c.
    A negative tick gives a negative frame; ticks count up from 0, so that needs 2**31 frames."""
    q = s32(tick) >> 2
    r = abs(q) % FRAMES
    return -r if q < 0 else r


def xp_resource(tick):
    return XP_NAME_FORMAT % xp_frame(tick)


def xp_threshold_addresses(ack):
    """(lower, upper) word addresses for acknowledged level ack (signed byte).
    No bound check: ack 81..127 reads past the 81-word table."""
    ack = s8(ack)
    return (XP_TABLE_LOWER + 4 * ack) & M32, (XP_TABLE + 4 * ack) & M32


def xp_fill_right(origin, xp, lower, upper):
    """Clip right of the green bar, 0x1da244-0x1da2b4.

    Both differences are 32-bit integer subtractions (they wrap), each converted with
    cvt.s.w; then divide, multiply by 99.0, add float(origin), truncate. No clamp. A zero
    difference divides by zero: the R5900 gives +/-0x7fffffff, and the final conversion
    saturates to 0x7fffffff or -0x80000000."""
    num = F.from_int(s32(xp - lower))
    den = F.from_int(s32(upper - lower))
    ratio = F.div(num, den)
    scaled = F.mul(ratio, F.from_int(FILL_SCALE))
    return s32(F.to_int(F.add(F.from_int(s32(origin)), scaled)))


def resource_bar_right(origin, current, maximum):
    """Health/mana clip right with raw float inputs, 0x1d9f24-0x1d9f84 (mana 0x1da318-
    0x1da37c): trunc(float(origin) + (current / maximum) * 99.0)."""
    ratio = F.div(current, maximum)
    return s32(F.to_int(F.add(F.from_int(s32(origin)), F.mul(ratio, F.from_int(FILL_SCALE)))))


def xp_layer(x, tick, ack, xp, lower, upper, local=True):
    """The green bar submission (to 0x17fb88), or None when it is not drawn.

    x is the HUD slot origin (ref_ui_layout.HUD_X after promotion), not the bar origin.
    Not drawn when the slot is not local or the acknowledged level is <= 0 (0x1da1e0).
    lower/upper are the words at xp_threshold_addresses(ack)."""
    if not local or s8(ack) <= 0:
        return None
    start = s32(x + X_INSET)
    right = xp_fill_right(start, xp, lower, upper)
    return XpLayer(xp_resource(tick), start, XP_Y, (start, CLIP_TOP, right, CLIP_BOTTOM), XP_TINT, LAYER)


# ---- the clipped drawer's scissor (0x17b8b0) -------------------------------------------
SCISSOR_RIGHT_MAX = 640      # 0x280 when right >= 0x281, 0x17bac0-0x17bacc
SCISSOR_BOTTOM_MAX = 447     # 0x1bf when bottom >= 0x1c0, 0x17bab8-0x17bad0
LETTERBOX = 0x44FD70         # subtracted from top and bottom, 0x17b9f4-0x17b9fc
FIELD_FLAG = 0x44FDD4        # s8; nonzero selects the interlaced arm, 0x17bab4
BOTH_FIELDS = 0x44FDB4       # s32; nonzero: both fields, 0x17bae4
GS_SCISSOR_1 = 0x40          # register id stored after the value, 0x17bb7c


def _sx(value):
    """A 32-bit result held sign-extended in a 64-bit register."""
    return s32(value) & M64


def scissor(left, top, right, bottom, interlaced=True, both_fields=False, parity=0, letterbox=0):
    """The 64-bit SCISSOR_1 value 0x17b8b0 writes (0x17bab0-0x17bb78).

    Clamps: left and top below 0 become 0; right >= 641 becomes 640; bottom >= 448
    becomes 447. Top and bottom first lose the letterbox height. There is no lower clamp
    on right or bottom and no masking, so a negative right spills ones into the upper
    fields. Interlaced arm: x endpoints 2*left and 2*right-1 (half-open in logical
    pixels); bottom 2*((b>>1) + (b&1 & p)) - 1 with p = 1 for both fields, else the
    field parity from 0x19d9e4."""
    top, bottom = s32(top - letterbox), s32(bottom - letterbox)
    left, top = s32(left), top
    right = s32(right)
    if left < 0:
        left = 0
    if top < 0:
        top = 0
    if not right < 0x281:
        right = SCISSOR_RIGHT_MAX
    if not bottom < 0x1C0:
        bottom = SCISSOR_BOTTOM_MAX
    if interlaced:
        bit = (bottom & 1) if both_fields else ((parity & 1) * (bottom & 1))
        b = s32(2 * ((bottom >> 1) + bit) - 1)
        x0 = _sx(left << 1)
        x1 = (_sx(2 * right - 1) << 16) & M64
    else:
        b = bottom
        x0 = _sx(left)
        x1 = (_sx(right) << 16) & M64
    return x0 | x1 | ((_sx(top) << 32) & M64) | ((_sx(b) << 48) & M64)


def visible_columns(origin, right, width=100):
    """Columns of a width-wide sprite at origin that the interlaced scissor keeps, for the
    ordinary domain 0 <= origin and right <= 640 (the scissor is half-open in logical x).
    A full bar (right = origin + 99) shows 99 of the 100 columns; right = origin shows none."""
    right = min(s32(right), SCISSOR_RIGHT_MAX)
    return max(0, min(right, origin + width) - max(origin, 0))


# ---- measured bar_green shape (HUD.LMP; counts and shapes only) -------------------------
TexShape = namedtuple('TexShape', 'entry offset used psm surface tbw upload upload_psm clut clut_psm rows file_size')

BAR_GREEN_FIRST = 0x04D80    # lump offset of bar_green00.tex
BAR_GREEN_STRIDE = 0x680     # per frame


def bar_green_shapes():
    """Header shape of bar_green00..10.tex as measured in HUD.LMP (all eleven agree).
    used: header u16 +0/+2, the drawers' source rectangle (0, 0, 100, 6).
    surface: TEX0 TW/TH; upload: the GIF image rectangle (4-bit, buffer width 2);
    clut: the 16-entry palette upload; rows: one field (used height / 2)."""
    return tuple(TexShape('bar_green%02d.tex' % i, BAR_GREEN_FIRST + BAR_GREEN_STRIDE * i,
                          (100, 6), 'PSMT4', (128, 8), 2, (104, 8), 'PSMT4', (8, 2), 'PSMCT32', 3, 1616)
                 for i in range(FRAMES))


def source_rect(shape):
    w, h = shape.used
    return (0, 0, w, h)


# ---- Part B: current health and mana of a new character ---------------------------------
REC_HP, REC_HP_MAX = 0xAC, 0xB0
REC_MANA, REC_MANA_MAX = 0xC0, 0xC4
REC_OBJECT = 0x43D8
G_NUM_PLAYERS = 0x4D8AE0
G_PVP_A = 0x4F711C
INIT_MANA_MAX = 0x41200000   # 10.0, 0x1b2010; stored to +0xc4 and +0xc0 at 0x1b20a0/0x1b20a8
INIT_CURRENT = 0x4E6E6B27    # 999999936.0, 0x1b23ac-0x1b23b0; stored to +0xac/+0xc0 at 0x1b23e8/0x1b23ec
RESPAWN_FACTOR = 0x3F000000  # 0.5, 0x1bd118


def after_init():
    """Record fields after player_initNewCharacter 0x1b1d70 returns, whatever the class.

    Order inside: memset 0x3b60c0 (all zero); +0xc4 = +0xc0 = 10.0 (0x1b20a0, 0x1b20a8);
    +0x43d8 = 0 (0x1b21b0); +0xac = +0xb0 (= 0) and +0xc0 = +0xc4 (= 10.0)
    (0x1b22c4, 0x1b22d4); +0xac = +0xc0 = INIT_CURRENT (0x1b23e8, 0x1b23ec);
    player_recalcStats (0x1b23f8) skips this slot because +0x43d8 is 0; then
    player_giveStartingItems (0x1b2400) whose recalcs skip it for the same reason."""
    return {'hp': INIT_CURRENT, 'hp_max': 0, 'mana': INIT_CURRENT, 'mana_max': INIT_MANA_MAX, 'object': 0}


def class_maxima(formula, level, eff):
    """Maximum health and mana from player_recalcStats (op order as ref_combat.recalc_stats).
    formula = (mana_int_offset, mana_per_int, mana_per_level, hp_per_level, hp_per_stamina,
    hp_offset) float patterns from the class chain 0x1b6740-0x1b694c; eff = the four
    effective statistics; level = s8 record +0x59."""
    mana_int_offset, mana_per_int, mana_per_level, hp_per_level, hp_per_stamina, hp_offset = formula
    lv = F.from_int(s8(level))
    mana = F.add(F.mul(F.sub(F.from_int(s32(eff[1])), mana_int_offset), mana_per_int), F.mul(lv, mana_per_level))
    hp = F.sub(F.add(F.mul(lv, hp_per_level), F.mul(F.from_int(s32(eff[3])), hp_per_stamina)), hp_offset)
    return hp, mana


def clamp(current, maximum):
    """0x1b6a24-0x1b6a48: current = maximum only when maximum < current. Never raises."""
    return maximum if F.lt(maximum, current) else current


def recalc_clamps(slot, num_players, has_object):
    """Whether player_recalcStats reaches the clamp for this slot: the loop runs for
    slot < g_numPlayers (0x1b6464/0x1b6490) and skips a slot whose +0x43d8 is 0 (0x1b64d8)."""
    return 0 <= slot < s32(num_players) and bool(has_object)


def first_level_current(formula, level, eff, current=INIT_CURRENT):
    """Health and mana when the first level's HUD can draw: Player_ctor 0x1a1d28 stores the
    object at +0x43d8 (0x1a221c) and then calls player_recalcStats (0x1a2458), which
    computes the maxima and clamps INIT_CURRENT down to them. Returns
    (hp, hp_max, mana, mana_max); hp == hp_max and mana == mana_max."""
    hp_max, mana_max = class_maxima(formula, level, eff)
    return clamp(current, hp_max), hp_max, clamp(current, mana_max), mana_max


def respawn_hp(hp_max, pvp_a):
    """player_respawn 0x1bd040, store at 0x1bd134: health = max when g_pvpModeA 0x4f711c is
    nonzero, else max * 0.5. Mana is not written there."""
    return hp_max if pvp_a else F.mul(hp_max, RESPAWN_FACTOR)
