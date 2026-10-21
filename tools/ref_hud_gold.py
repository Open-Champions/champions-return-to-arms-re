"""HUD gold counter, end to end, for SLUS-20973 v2.00; see docs/spec/hud-gold.md.

Written from addressed instruction sequences; no game data or code is embedded. Executed
against the original by tools/difftest_hud_gold.py (tools/ee_emu.py).

    hud_addGoldFloater          0x1dc268  (slot, world position, amount)
    hud_tickGold                0x1dcb80  run task (first call of hud_run 0x1db870)
    hud_flushGold               0x1dc5f4  game_clearLevel 0x1e4e88
    hud_drawGold                0x1dc708  draw task (first call of HUD Draw 0x1dbc48)
    ui_insertThousandsSeparators 0x1c7128 in place, after sprintf("%d")
    arena_giveBonusLife         0x307ee0  (slot): sets the counter alpha to 128

Floats are raw 32-bit patterns through ref_core (the PS2 FPU model). The floater physics and
the counter fade reuse ref_hud_dynamic.gold_* unchanged.
"""
import ref_core as F
import ref_hud_dynamic as H

M32 = 0xFFFFFFFF

# ---- globals (addresses) ---------------------------------------------------------------
G_SIM_FRAME = 0x44FDCC            # g_simFrame, the run-task tick
G_VIEW_PROJ = 0x44F140            # this machine's camera x projection (mat4)
G_COSMETIC_SEED = 0x404460        # per-machine generator, one draw per filled floater
G_RAND_SEED = 0x404464            # shared generator (never drawn here)
G_THIRD_SEED = 0x404468           # per-machine generator (never drawn here)
G_PLAYERS, REC_SIZE, REC_GOLD = 0x4D8AF0, 0x4C30, 0xE4
FLOATERS, FLOATER_SIZE, FLOATER_COUNT = 0x86A900, 0x24, 8   # g_goldFloaters
G_GOLD_PENDING = 0x86ACE8         # s32[4]
G_GOLD_HOLD = 0x86ACD8            # s32[4], frames
G_GOLD_ALPHA = 0x4F6950           # s32[4], 0..128 (bonus life writes 128 directly)
G_GOLD_Y, G_GOLD_ICON_X, G_GOLD_TEXT_X = 0x4F6710, 0x4F6720, 0x4F6730   # s32[4] each
G_FONT = 0x44FDD8                 # default font handle, read at 0x1dc754 and 0x1dca58
G_LANGUAGE = 0x44FDDC             # s8: 0 -> ',' else '.' (0x1c71d4)
G_HUD_OFF_A = 0x41B4F8            # s32, non-zero skips hud_drawGold (0x1dc710)
G_HUD_OFF_B = 0x4F66A8            # s8, non-zero skips hud_drawGold (0x1dc740)
S_FORMAT = 0x53C488               # "%d" (0x1dc7b0, 0x1dca1c)
S_HUD_LUMP, S_COIN = 0x53C388, 0x53C758   # "hud.lmp", "gold03.tex" (0x1dcb00, 0x1dcb08)

# ---- constants -------------------------------------------------------------------------
GOLD_CAP = 99999999               # 0x5f5e0ff, 0x1dc2f4/0x1dc2fc, 0x1dcc30/0x1dcc34
CREDIT_DELAY = 0x80               # (frame - start) * 3 >= 128 -> 43 ticks (0x1dcbc0)
HOLD_FRAMES = 0x3C                # 60, 0x1dc7ac
ALPHA_STEP, ALPHA_MAX = 4, 0x80   # 0x1dc9b4 / 0x1dc9d4, 0x1dc9ac
FLOATER_FADE = 3                  # alpha 128 - 3 * age, 0x1dc908
TEXT_COLOUR = 0x004080E4          # 0x1dc75c (batch 0x804080e4), 0x1dc868, 0x1dc9f8
COIN_TINT = 0x00808080            # 0x1dcb20
COIN_DY = -10                     # 0x1dcb3c
LAYER = 6                         # 0x1dc758, 0x1dcb44
TEXT_LIMIT = 100000               # 0x186a0, length argument of text_drawAscii / text_widthAscii
BONUS_ALPHA = 0x80                # 0x307f1c, stored at 0x307f34
SEP_COMMA, SEP_PERIOD = 0x2C, 0x2E  # 0x1c716c, 0x1c7170
F_ONE, F_HALF, F_ZERO = 0x3F800000, 0x3F000000, 0
F_NEAR = 0x41A00000               # 20.0, 0x1dc380: w below this -> off-screen byte
F_EDGE_X = 0x442F0000             # 700.0, 0x1dc398
F_EDGE_Y = 0x43960000             # 300.0, 0x1dc3b8
F_CENTRE_X = 0x43A00000           # 320.0, 0x1dc424
F_CENTRE_Y = 0x43700000           # 240.0, 0x1dc418
F_2M16 = 0x37800000               # 2^-16, 0x1dc480
F_SPREAD = 0x41100000             # 9.0, 0x1dc494
GOLD_TEXT_X, GOLD_Y, GOLD_ICON_X = H.GOLD_TEXT_X, H.GOLD_Y, H.GOLD_ICON_X
LCG_MUL, LCG_ADD = 0x0019660D, 0x3C6EF35F


def s32(v):
    v &= M32
    return v - 0x100000000 if v & 0x80000000 else v


def s8(v):
    v &= 0xFF
    return v - 0x100 if v & 0x80 else v


def lcg(seed):
    return (seed * LCG_MUL + LCG_ADD) & M32


class Floater(object):
    """One g_goldFloaters entry: +0 pos[3], +0xc vel[3], +0x18 start, +0x1c amount
    (0 = free), +0x20 s8 slot, +0x21 off-screen byte (written, never read)."""
    __slots__ = ('pos', 'vel', 'start', 'amount', 'slot', 'offscreen')

    def __init__(self, pos=(0, 0, 0), vel=(0, 0, 0), start=0, amount=0, slot=0, offscreen=0):
        self.pos, self.vel = list(pos), list(vel)
        self.start, self.amount, self.slot, self.offscreen = start & M32, amount & M32, slot & 0xFF, offscreen

    def copy(self):
        return Floater(self.pos, self.vel, self.start, self.amount, self.slot, self.offscreen)


class GoldState(object):
    """Everything the gold functions read or write. gold[] is record +0xe4 of slots 0..3
    (u32 words); pending/hold/alpha are s32[4]."""

    def __init__(self):
        self.floaters = [Floater() for _ in range(FLOATER_COUNT)]
        self.pending = [0] * 4
        self.gold = [0] * 4
        self.hold = [0] * 4
        self.alpha = [0] * 4
        self.frame = 0
        self.cosmetic = 0                     # generator word 0x404460
        self.cosmetic_draws = 0
        self.text_x = list(GOLD_TEXT_X)
        self.text_y = list(GOLD_Y)
        self.icon_x = list(GOLD_ICON_X)

    def copy(self):
        o = GoldState()
        o.floaters = [f.copy() for f in self.floaters]
        for name in ('pending', 'gold', 'hold', 'alpha', 'text_x', 'text_y', 'icon_x'):
            setattr(o, name, list(getattr(self, name)))
        o.frame, o.cosmetic, o.cosmetic_draws = self.frame, self.cosmetic, self.cosmetic_draws
        return o


def credit(word, amount):
    """The credit idiom of all three bodies: the 32-bit sum is stored, then the cap over it
    when the signed sum is above 99,999,999. A wrapped negative sum stays."""
    total = (word + amount) & M32
    return GOLD_CAP if s32(total) > GOLD_CAP else total


# ---- producer ---------------------------------------------------------------------------
def floater_screen(viewproj, pos, slot, text_x, text_y, cosmetic):
    """Presentation part of hud_addGoldFloater (0x1dc374..0x1dc5d0). Returns
    (pos, vel, offscreen, new cosmetic seed). One cosmetic draw."""
    p, w = F.mat4_transform_point(viewproj, list(pos))
    off = 1 if (F.lt(w, F_NEAR) or F.lt(F.mul(w, F_EDGE_X), F.fabs(p[0]))
                or F.lt(F.mul(w, F_EDGE_Y), F.fabs(p[1]))) else 0
    inv = F.div(F_ONE, w)
    sx = F.add(F.mul(F.mul(p[0], inv), F_HALF), F_CENTRE_X)
    sy = F.add(F.mul(p[1], inv), F_CENTRE_Y)
    tx = F.from_int(text_x[slot & 3] if 0 <= s32(slot) < 4 else 0)
    ty = F.from_int(text_y[slot & 3] if 0 <= s32(slot) < 4 else 0)
    dx, dy, dz = F.sub(tx, sx), F.sub(ty, sy), F.neg(F_ZERO)
    r = F.rsqrt(F_ONE, F.add(F.add(F.mul(dx, dx), F.mul(dy, dy)), F.mul(dz, dz)))
    dx, dy = F.mul(dx, r), F.mul(dy, r)
    seed = lcg(cosmetic)
    k = F.mul(F.sub(F.mul(F.from_int(seed >> 16), F_2M16), F_HALF), F_SPREAD)
    return [sx, sy, F_ZERO], [F.mul(dy, k), F.mul(F.neg(dx), k), F_ZERO], off, seed


def add_gold_floater(st, slot, pos, amount, viewproj):
    """hud_addGoldFloater 0x1dc268. Returns the floater index taken, or -1 when all eight
    were busy and the amount went straight into record(slot) +0xe4 (no draw).
    Callers (O): Gold_onTouch 0x157b30, AutoChest_interact 0x23ba1c, Chest_interact
    0x293180. slot must be 0..3 for the presentation table reads."""
    k = next((i for i, f in enumerate(st.floaters) if not f.amount), -1)
    if k < 0:
        st.gold[slot] = credit(st.gold[slot], amount)
        return -1
    f = st.floaters[k]
    f.amount, f.slot, f.start, f.offscreen = amount & M32, slot & 0xFF, st.frame & M32, 0
    f.pos, f.vel, off, st.cosmetic = floater_screen(viewproj, pos, slot, st.text_x, st.text_y, st.cosmetic)
    f.offscreen = off
    st.cosmetic_draws += 1
    return k


def tick_gold(st):
    """hud_tickGold 0x1dcb80, once per run-task tick, on every machine. A busy floater
    whose (frame - start) * 3 (s32) reaches 128 moves its amount to pending[s8 slot] and is
    freed; then each slot with pending p > 0 is paid (p + 7) >> 3 (capped)."""
    for f in st.floaters:
        if not f.amount:
            continue
        if s32(3 * ((st.frame - f.start) & M32)) < CREDIT_DELAY:
            continue
        i = s8(f.slot)
        st.pending[i] = s32(st.pending[i] + f.amount)
        f.amount = 0
    for i in range(4):
        p = st.pending[i]
        if p <= 0:
            continue
        step = s32(p + 7) >> 3
        st.gold[i] = credit(st.gold[i], step)
        st.pending[i] = s32(p - step)


def flush_gold(st):
    """hud_flushGold 0x1dc5f4: busy floaters, then positive pending sums, straight into
    the records (capped); then hold[] and alpha[] are zeroed (0x1dc6e4, 0x1dc6f0)."""
    for f in st.floaters:
        if f.amount:
            i = s8(f.slot)
            st.gold[i] = credit(st.gold[i], f.amount)
            f.amount = 0
    for i in range(4):
        if st.pending[i] > 0:
            st.gold[i] = credit(st.gold[i], st.pending[i])
            st.pending[i] = 0
    st.hold = [0] * 4
    st.alpha = [0] * 4


def arena_bonus_life(st, slot):
    """0x307ee0 (slot), called by arena_runTask 0x3071d4 after it takes the bonus-life
    price from record +0xe4 (price starts at 100, arena_init 0x304e70, doubles each time).
    Gold-relevant effect only: alpha[slot] = 128 with hold untouched -> the counter shows
    at full alpha and fades 4 per displayed frame."""
    st.alpha[slot] = BONUS_ALPHA


# ---- separators ---------------------------------------------------------------------------
def insert_separators(buf, language):
    """ui_insertThousandsSeparators 0x1c7128 on a bytearray holding a C string (modified in
    place, returned). n = strlen, g = (n-1)/3 (C division). Each of g passes inserts one
    separator: the first at n%3 (or n/2 when n%3 == 0), every later one at (previous
    position % 3, or previous/2 when that is 0) + 4*pass. Each pass shifts bytes
    [pos, n+g] right by one, so byte n+g+1 is written too. Right for n <= 8 digits;
    n = 9 gives '1234,,56789' (never reached by capped gold). language s8 0 -> ',' else '.'."""
    n = buf.index(0)
    g = int((n - 1) / 3) if n > 0 else 0
    sep = SEP_COMMA if s8(language) == 0 else SEP_PERIOD
    end = n + g + 1
    need = end + 1
    if len(buf) < need:
        buf.extend(b'\0' * (need - len(buf)))
    cur = n
    for i in range(g):
        rem = cur % 3
        cur = rem if rem else cur // 2
        pos = cur + 4 * i
        k = end
        while k >= pos:
            buf[k] = buf[k - 1]
            k -= 1
        buf[pos] = sep
    return buf


def format_gold(value, language):
    """sprintf(buf, "%d", value) (0x53c488) then the separators: the counter text."""
    buf = bytearray(b'%d' % s32(value) + b'\0')
    insert_separators(buf, language)
    return bytes(buf[:buf.index(0)])


def floater_alpha(frame, start):
    """0x1dc900..0x1dc920 in 32-bit arithmetic: 128 - 3 * (frame - start), at most 128
    (slti 0x81), at least 0. Equals ref_hud_dynamic.gold_floater_alpha without wrap."""
    a = s32(ALPHA_MAX - s32(FLOATER_FADE * ((frame - start) & M32)))
    a = a if a < ALPHA_MAX + 1 else ALPHA_MAX
    return 0 if a < 0 else a


# ---- draw -----------------------------------------------------------------------------------
def draw_gold(st, is_local, width, language, hud_off=False):
    """hud_drawGold 0x1dc708, once per displayed frame. is_local(slot) -> bool is
    net_isLocalSlot 0x13e150; width(text) -> int is text_widthAscii 0x181a60. Returns the
    call list (names as in the spec) and steps floaters, hold and alpha in st."""
    calls = []
    if hud_off:
        return calls
    calls.append(('text_begin', 'font', LAYER, 0x80000000 | TEXT_COLOUR, -1))
    for f in st.floaters:
        i = s8(f.slot)
        calls.append(('net_isLocalSlot', i))
        if not is_local(i) or not f.amount:
            continue
        st.hold[i] = HOLD_FRAMES
        text = b'%d' % s32(f.amount)
        f.pos, f.vel = H.gold_floater_step(f.pos, f.vel, i)
        a = floater_alpha(st.frame, f.start)
        calls.append(('text_setColor', ((a << 24) | TEXT_COLOUR) & M32, -1, 0))
        calls.append(('text_drawAscii', F.to_int(f.pos[0]) & M32, F.to_int(f.pos[1]) & M32, text, TEXT_LIMIT))
    for i in range(4):
        calls.append(('net_isLocalSlot', i))
        if not is_local(i):
            continue
        st.hold[i], st.alpha[i] = H.gold_counter_step(st.hold[i], st.alpha[i])
        if st.alpha[i] <= 0:
            continue
        calls.append(('text_setColor', ((st.alpha[i] << 24) | TEXT_COLOUR) & M32, -1, 0))
        text = format_gold(st.gold[i], language)
        x = st.text_x[i]
        if i in (1, 3):
            w = width(text)
            calls.append(('text_widthAscii', 'font', text, TEXT_LIMIT))
            x = x - w
        calls.append(('text_drawAscii', x & M32, st.text_y[i] & M32, text, TEXT_LIMIT))
    calls.append(('text_end',))
    for i in range(4):
        if st.alpha[i] > 0:
            calls.append(('res_find', 'hud.lmp', 'gold03.tex'))
            calls.append(('ui_drawSprite', 'coin', st.icon_x[i] & M32, (st.text_y[i] + COIN_DY) & M32,
                          LAYER, ((st.alpha[i] << 24) | COIN_TINT) & M32))
    return calls


def counter_timeline(amount, start_gold=0, draws_per_tick=1, ticks=200):
    """Offline single-player replay of one pickup (slot 0, all floaters free, nothing
    pending): per tick t (pickup in tick 0, before that tick's draws), run task first
    (hud_tickGold) then draws_per_tick displayed frames. Returns a list of
    (tick, gold, pending, hold, alpha) after the tick's last draw. The floater screen
    path is irrelevant to the counter and is left at the origin."""
    st = GoldState()
    st.gold[0] = start_gold
    f = st.floaters[0]
    f.amount, f.slot, f.start = amount & M32, 0, 0
    out = []
    for t in range(ticks):
        st.frame = t
        tick_gold(st)
        for _ in range(draws_per_tick):
            draw_gold(st, lambda s: s == 0, len, 0)
        out.append((t, st.gold[0], st.pending[0], st.hold[0], st.alpha[0]))
    return out
