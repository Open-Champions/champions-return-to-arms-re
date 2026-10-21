"""Dynamic HUD composition contracts for SLUS-20973 v2.00; see docs/hud-dynamic.md.

Authored from addressed instruction sequences; no game data or code is embedded.
Coordinates are the original 640 x 448 API arguments. Plain sprites (0x17fb68)
receive one extra row inside the callee; clipped sprites, rectangles and text do
not. All HUD 2D packets are prepended in their sort layer, so a painter renderer
reverses submission order within each layer (docs/hud-layout.md).

Floats are raw 32-bit patterns handled by ref_core (PS2 FPU model); integer
results use the same truncation as cvt.w.s.
"""
from collections import namedtuple

import ref_core as F


Sprite = namedtuple('Sprite', 'resource x y layer tint')
Rect = namedtuple('Rect', 'x0 y0 x1 y1 layer colour')
Text = namedtuple('Text', 'kind x y layer colour text')
Frame = namedtuple('Frame', 'x y width height layer tint style')

# Draw-task composition, 0x1dbc48 ("HUD Draw", draw priority 51, hud_addTasks 0x1dc1d0).
HUD_DRAW_SEQUENCE = (
    (0x1dc708, 'hud_drawGold', 'floaters then counters then coin icons'),
    (0x1d9cd4, 'hud_drawPlayerStatus', 'for slot 0 .. g_numPlayers-1, in slot order'),
    (0x305904, 'arena_drawHud', 'arena modes'),
    (0x1d93b0, 'hud_drawBossMeter', 'one-line message, then boss meter'),
    (0x1dfb6c, 'hud_drawBust', 'script portrait panel'),
    (0x1df720, 'hud_drawCompass', '3D compass model and label'),
    (0x1e01b8, 'hud_drawNetCamPrompt', ''),
    (0x1db3c8, 'hud_drawControllerOut', 'only when warm-up 0x506048 and cutscene 0x44fcd0 are zero'),
    (0x1e0698, 'hud_drawMedalPrompt', ''),
    (0x1dbcec, 'net status text', 'net game: checksum line, out-of-sync lines, exit/disconnect boxes'),
)

# Per-slot sub-order inside 0x1d9cd4 (submission order).
STATUS_SEQUENCE = (
    'health bar', 'pending health rect', 'pending mana rect', 'experience bar', 'mana bar',
    'name text', 'level text', 'level-up glow', 'status frame', 'notice lines 0..7',
    'spell selector (0x1dd270 via 0x1dacb8)',
)

STATUS_TEXT = 0x80323c3c          # 0x1da3b8, 0x1da5ec
PULSE_SCALE = 0x41c80000          # 25.0, 0x1da39c / 0x1da850


def _s32(v):
    v &= 0xffffffff
    return v - 0x100000000 if v & 0x80000000 else v


def _tdiv(a, b):
    """C integer division (truncates toward zero), as the srl/addu/sra idiom does."""
    q = abs(a) // b
    return q if a >= 0 else -q


def pulse(tick):
    """trunc(math_sin16(tick << 10) * 25.0): 0x1da390..0x1da3c4 and 0x1da844..0x1da860.

    tick is g_simFrame 0x44fdcc; one cycle per 64 ticks; range -25..25."""
    return F.to_int(F.mul(F.sin16(_s32(tick << 10)), PULSE_SCALE))


def pending_level_colour(p):
    """Colour set when acknowledged level < level (0x1da40c..0x1da43c): h = p/2 (C);
    R=G=h+60, B=h+50, alpha 0x80. Only the LEVEL number keeps it: the name batch
    sets its own colour afterwards (0x1da598)."""
    h = _tdiv(p, 2)
    return 0x80000000 | ((h + 50) << 16) | ((h + 60) << 8) | (h + 60)


def name_colour(slot, tick, arena_colour=0, player_colour=None, blink_mask=0):
    """Name text colour, 0x1da4f4..0x1da598.

    arena_colour is the result of 0x3054c4 (0 = none); player_colour is
    player_slotColor(slot, 0x80) and applies whenever g_numPlayers >= 2 (it replaces
    the arena colour). Bit `slot` of 0x505b04 halves RGB while (tick/32) is odd."""
    c = STATUS_TEXT
    if arena_colour:
        c = arena_colour & 0xffffffff
    if player_colour is not None:
        c = player_colour & 0xffffffff
    if (blink_mask >> slot) & 1 and _tdiv(tick, 32) & 1:
        c = (c & 0xff000000) | ((((c >> 16) & 0xff) >> 1) << 16) | ((c >> 1) & 0x7f00) | ((c & 0xff) >> 1)
    return c


def name_width_budget(pvp_a, pvp_b, counter_width):
    """Width given to ui_fitText for the name (0x1da484..0x1da4d0): 131, less the
    width of the 'x 000' sample when g_pvpModeB is set and g_pvpModeA is not."""
    return 131 - counter_width if pvp_b and not pvp_a else 131


def pulse_grey(p, alpha):
    """alpha<<24 | (p+103) in R, G and B: glow tint (0x1da76c) and notice icons."""
    v = p + 0x67
    return ((alpha & 0xff) << 24) | (v << 16) | (v << 8) | v


def glow_step(alpha):
    """Level-up glow alpha 0x86aa50[slot]: +4 per drawn frame, capped at 128
    (0x1da6f8..0x1da71c). Reset to 0 only by hud_run when it opens the menu with a
    pending level (0x1dbaec)."""
    return min(alpha + 4, 0x80)


def glow_sprite(x, alpha, p):
    """hud_statusbar00glow.tex, clipped sprite, layer 6, origin (X-4, 36)."""
    return Sprite('hud_statusbar00glow.tex', x - 4, 36, 6, pulse_grey(p, alpha))


# Notice lines: index -> (resource, column dx, fixed row, counted). 0x1da900..0x1da9a0,
# icon table 0x4f85e0 filled by hud_loadIcons 0x1e7068.
NOTICE_LINES = (
    ('nocamera.tex', 0x33, 1, False),
    ('nohealth.tex', -0x11, 0, False),
    ('nomana.tex', -0x11, 1, False),
    ('noarrows.tex', 0x33, 0, False),
    ('counthealth.tex', -0x11, 0, True),
    ('countmana.tex', -0x11, 1, True),
    ('countarrows.tex', 0x33, 0, True),
    ('countthrown.tex', 0x33, 0, True),
)
NOTICE_X = (0, 477, 162, 321)      # table 0x53c4d8; base = value + 37
NOTICE_TEXT = 0x004080e4           # 0x1daa80


def notice_base_x(slot, network=False):
    """0x1da864..0x1da8b8: in a net game every slot uses slot 0's column."""
    return NOTICE_X[0 if network else slot] + 0x25


def notice_alpha_step(timer, alpha):
    """Counted lines only (0x1da9d0..0x1daa64): +4 while timer > 81, -4 while timer < 38,
    clamped to 0..128. Done before the timer is decremented."""
    if timer > 0x51:
        alpha += 4
    if timer < 0x26:
        alpha -= 4
    return 0 if alpha < 0 else min(alpha, 0x80)


def notice_frame(slot, timers, alphas, counts, tick, network=False, hide_counts=False):
    """One drawn frame of the eight notice lines for a LOCAL slot, 0x1da864..0x1daca0.

    timers/alphas are the slot's eight entries of 0x41b828 / 0x86ac3c; counts[i] is
    the count for lines 4..7 (-1 = not shown; line 7 is -1 unless weapon class 6).
    hide_counts models the 'stomedal' level-name test (strstr, 0x1dab4c).
    Returns (submissions, timers, alphas, cleared) where cleared lists lines whose
    row word 0x41b8a8 is zeroed. Rows stored by the starters are NOT read: each line
    has a fixed row. Non-local slots are skipped entirely (no timer decrement)."""
    timers, alphas = list(timers), list(alphas)
    p = pulse(tick)
    base = notice_base_x(slot, network)
    out, cleared = [], []
    for i, (res, dx, row, counted) in enumerate(NOTICE_LINES):
        if not timers[i]:
            continue
        x, y = base + dx, 27 * row + 0x52
        if counted:
            alphas[i] = notice_alpha_step(timers[i], alphas[i])
            if counts[i] >= 0 and not hide_counts:
                out.append(Text('ascii', x + 0x1f, 27 * row + 0x51, 4,
                                ((alphas[i] & 0xff) << 24) | NOTICE_TEXT, 'x %d' % counts[i]))
                out.append(Sprite(res, x, y, 4, pulse_grey(p, alphas[i])))
        else:
            out.append(Sprite(res, x, y, 4, pulse_grey(p, 0x80)))
        timers[i] -= 1
        if timers[i] <= 0:
            cleared.append(i)
    return out, timers, alphas, cleared


def count_active_notices(timers, except_index):
    """hud_countActiveNotices 0x1dacf4 over one slot's eight timers.

    Counts running lines other than except_index; a count line is not counted while
    its 'no' line runs (5 with 2, 4 with 1, 6 and 7 with 3). Its result is stored as
    the row (0x41b8a8) but the draw ignores that row."""
    hidden_by = {5: 2, 4: 1, 6: 3, 7: 3}
    n = 0
    for i in range(8):
        if not timers[i]:
            continue
        if i in hidden_by and timers[hidden_by[i]]:
            continue
        if i != except_index:
            n += 1
    return n


# One-line message and boss meter, 0x1d93b0.
MESSAGE_TINT = 0x001e6464


def message_alpha_step(timer, alpha):
    """0x1d93fc..0x1d9448: alpha = 4*timer when timer < 32, else alpha + 3; max 128."""
    alpha = timer * 4 if timer < 0x20 else alpha + 3
    return min(alpha, 0x80)


def message_frame(timer, alpha, force, suppressed, text_width):
    """Message part of 0x1d93b0 for one displayed frame. Returns (submissions, alpha).

    text_width is text_widthWide of the message in the default font (0x44fdd8).
    The timer itself is decremented by hud_tickMessage 0x1d934c in the run task."""
    if timer <= 0 or (suppressed and not force):
        return [], alpha
    alpha = message_alpha_step(timer, alpha)
    layer = 7 if force else 6
    w = max(300, text_width)
    return [Text('wide-centered', 320, 78, layer, ((alpha & 0xff) << 24) | MESSAGE_TINT, None),
            Frame(300 - _tdiv(w, 2), 76, w + 40, 32, layer, (_tdiv(alpha, 2) & 0xff) << 24, 0)], alpha


BossState = namedtuple('BossState', 'hp maximum alpha visible previous')
BOSS_FILL = 0x43420000            # 194.0
BOSS_FILL_WIDE = 0x439d8000       # 315.0


def boss_meter_frame(state, language=0):
    """Boss part of 0x1d93b0 (0x1d9568..0x1d9804); caller applies the gates
    (g_hudSuppressed, g_localMenuOpen 0x41b69d, camera +0x34 == 1).

    Returns (submissions, new_state). Maximum follows the largest hp seen; the bar
    fades by 3 per frame only after hp reaches 0; the frame sprite never fades."""
    hp, maximum, alpha, visible, previous = state
    if hp > maximum:
        maximum = hp
    if not (hp > 0 and maximum > 0) and alpha <= 0:
        return [], BossState(hp, maximum, alpha, 0, previous)
    if hp <= 0:
        hp, alpha = 0, alpha - 3
    if maximum <= 0:
        raise ValueError('maximum <= 0 is outside the reference domain')
    out = [Text('wide-centered', 320, 408, 5, ((alpha & 0xff) << 24) | 0x464646, None)]
    frac = F.div(F.from_int(hp), F.from_int(maximum))
    wide = language in (3, 4)
    left = 0xa2 if wide else 0xda
    fill = F.to_int(F.mul(frac, BOSS_FILL_WIDE if wide else BOSS_FILL))
    if visible:
        prev = previous - 0x10000 if previous & 0x8000 else previous
        colour = ((alpha & 0xff) << 24) | (0x808080 if hp < prev else 0x181850)
    else:
        alpha, colour = 0x4e, 0x4e181850
    out.append(Rect(left, 0x19e, left + fill, 0x1ae, 5, colour))
    out.append(Sprite('bossmeter_pal.tex' if wide else 'bossmeter.tex', 0x9e if wide else 0xd1,
                      0x199, 6, 0x80808080))
    return out, BossState(hp, maximum, alpha, 1, hp & 0xffff)


# Gold, 0x1dc708. Initialised tables; no writer found in this pass.
GOLD_TEXT_X = (50, 590, 50, 590)   # 0x4f6730; slots 1 and 3 right-aligned
GOLD_Y = (200, 200, 250, 250)      # 0x4f6710
GOLD_ICON_X = (16, 593, 16, 593)   # 0x4f6720
GOLD_TEXT = 0x004080e4
GOLD_PULL = 0x3bd099e0             # 0.0063659
GOLD_DAMP = 0x3db3be9b             # 0.0877665


def gold_floater_step(pos, vel, slot):
    """Per displayed frame (0x1dc7cc..0x1dc8fc): pos += vel (old velocity), then
    w = vel + (target - pos) * PULL, vel = w - w * DAMP; target z is 0.
    pos, vel: three raw float patterns each. Returns new (pos, vel)."""
    px, py, pz = (F.add(pos[i], vel[i]) for i in range(3))
    dx = F.sub(F.from_int(GOLD_TEXT_X[slot]), px)
    dy = F.sub(F.from_int(GOLD_Y[slot]), py)
    dz = F.neg(pz)
    nv = []
    for v, d in zip(vel, (dx, dy, dz)):
        w = F.add(v, F.mul(d, GOLD_PULL))
        nv.append(F.sub(w, F.mul(w, GOLD_DAMP)))
    return [px, py, pz], nv


def gold_floater_alpha(tick, start):
    """0x1dc900..0x1dc920: 128 - 3*(tick - start), at most 128, at least 0."""
    a = 0x80 - 3 * (tick - start)
    return 0 if a < 0 else min(a, 0x80)


def gold_counter_step(hold, alpha):
    """0x1dc980..0x1dc9dc: with hold > 0, hold -= 1 and alpha += 4 while below 128;
    otherwise alpha -= 4 while positive. A visible floater sets hold to 60."""
    if hold:
        return hold - 1, alpha + 4 if alpha < 0x80 else alpha
    return 0, alpha - 4 if alpha > 0 else alpha


def gold_counter(slot, alpha, text_width):
    """Counter text and coin icon (0x1dc9f0..0x1dcb44); text_width is the default-font
    width of the separator-formatted gold. Not promoted in net games: raw slot."""
    if alpha <= 0:
        return []
    x = GOLD_TEXT_X[slot] - text_width if slot in (1, 3) else GOLD_TEXT_X[slot]
    return [Text('ascii', x, GOLD_Y[slot], 6, ((alpha & 0xff) << 24) | GOLD_TEXT, None),
            Sprite('gold03.tex', GOLD_ICON_X[slot], GOLD_Y[slot] - 10, 6, ((alpha & 0xff) << 24) | 0x808080)]


# Quick-cast selector, hud_spellSelect 0x1dd270 (called with page 0 from the HUD).
SELECTOR_X = (0, 471, 156, 316)    # table 0x53c790; centre x = value + 67
SELECTOR_STEP = 0x2000


def selector_centre(slot, network=False, menu_mode=False):
    """0x1dd2f8..0x1dd370: (table+67, 145), slot 0's column in a net game;
    character-sheet mode (third argument) uses (141, 249)."""
    if menu_mode:
        return 0x8d, 0xf9
    return SELECTOR_X[0 if network else slot] + 0x43, 0x91


def selector_direction(dx, dy):
    """D-pad to direction 0..7 clockwise from up; -1 none (0x1dd5f0..0x1dd688).
    dx: +1 right (0x2000), -1 left (0x8000); dy: -1 up (0x1000), +1 down (0x4000)."""
    table = {(0, -1): 0, (1, -1): 1, (1, 0): 2, (1, 1): 3, (0, 1): 4, (-1, 1): 5, (-1, 0): 6, (-1, -1): 7}
    return table.get((dx, dy), -1)


def selector_fade_step(alpha, timer, speed, active):
    """0x1dd4c0..0x1dd57c. timer is the float at player record +0x4a74, speed the int
    at +0x4a78. active = a direction is held or menu mode. Returns (alpha, timer, speed).
    Fade in +16/frame; 29 frames after release the speed becomes -1 (-4/frame)."""
    if active:
        timer, speed = F.f32(30.0), 4
    if F.eq(timer, F.ZERO):
        speed = -1
    timer = F.sub(timer, F.ONE)
    alpha += speed * 4
    alpha = 0x80 if alpha > 0x80 else 0 if alpha < 0 else alpha
    return alpha, timer, speed


def selector_radii(alpha):
    """smoothstep(alpha/128) via math_hermite, times 60 and 32, truncated (0x1dd7cc..0x1dd81c)."""
    s = F.hermite(F.mul(F.from_int(alpha), 0x3c000000), F.ZERO, F.ONE, F.ZERO, F.ZERO)
    return F.to_int(F.mul(s, 0x42700000)), F.to_int(F.mul(s, 0x42000000))


def selector_ring(cx, cy, alpha, page=0):
    """Icon origins for ability records 0..7 at angles -0x4000 + 0x2000*k
    (0x1dd820..0x1dd8a8): record k sits in direction k. Returns [(k, x, y)]."""
    r = F.from_int(selector_radii(alpha)[0])
    out = []
    for k in range(8):
        a = -0x4000 + SELECTOR_STEP * k
        out.append((k, cx + F.to_int(F.mul(r, F.cos16(a))) + 320 * page,
                    cy + F.to_int(F.mul(r, F.sin16(a)))))
    return out


def selector_highlight(tick, alpha):
    """Corona alpha and icon grey for the selected direction (0x1dd98c..0x1dda78):
    trunc(sin*16 + 128) and trunc(sin*16 + 239) with the sin of tick<<10, where tick
    is g_drawFrame 0x44fdd0 (displayed frames), not g_simFrame."""
    s = F.mul(F.sin16(_s32(tick << 10)), 0x41800000)
    corona = F.to_int(F.add(s, 0x43000000))
    grey = F.to_int(F.add(s, 0x436f0000))
    return (((corona & 0xff) << 24) | 0x808080), (((alpha & 0xff) << 24) | (grey << 16) | (grey << 8) | grey)


# Bust panel, 0x1dfb6c (partial).
BUST_FADE = 0x3dacf3df             # 0.08445


def bust_fade_step(fade, hide):
    """0x1dfb9c..0x1dfc1c: minus BUST_FADE when the hide latch 0x4f66a9 is set,
    plus otherwise; clamped to 0..1. The latch is cleared after use."""
    fade = F.sub(fade, BUST_FADE) if hide else F.add(fade, BUST_FADE)
    if F.lt(F.ONE, fade):
        fade = F.ONE
    if F.lt(fade, F.ZERO):
        fade = F.ZERO
    return fade


def bust_alphas(fade):
    """(text alpha, sprite alpha) = (fade*110, fade*128), unsigned conversions."""
    return F.to_uint(F.mul(fade, 0x42dc0000)), F.to_uint(F.mul(fade, 0x43000000))


def bust_meter(value, maximum, width, tick):
    """bar_yellow0N.tex frame N = (tick/2) % 4 (C), clip right = 521 + round(value/max*width) - 2
    (0x1dfdd8..0x1dfef0); origin (521, 377); returns (resource, clip_right)."""
    q = _tdiv(tick, 2)
    n = q - _tdiv(q, 4) * 4
    fill = F.round_half_away(F.mul(F.div(F.from_int(value), F.from_int(maximum)), F.from_int(width)))
    return 'bar_yellow0%d.tex' % n, 521 + fill - 2


# --- round 3 (2026-10-20). Existing names above are unchanged. ---

def _sx16(v):
    v &= 0xffff
    return v - 0x10000 if v & 0x8000 else v


def _addu(a, b):
    return (a + b) & 0xffffffff


# Flying numbers. Constructor 0x202158, run 0x2022a8, draw 0x1f3830.
FLY_LIFE_PLAIN = 0x1e          # kind == 0
FLY_LIFE_OTHER = 0xb4          # any other kind
FLY_ALPHA0 = 0x80


def flying_text_life(kind):
    """0x202264..0x202274: 180 ticks when kind != 0, else 30."""
    return FLY_LIFE_OTHER if kind else FLY_LIFE_PLAIN


def flying_text_drift(rand_word):
    """0x20222c..0x202258: (GameObject_rand % 60) - 30, stored at +0x78 and +0x7c."""
    return (rand_word % 60) - 30


def flying_text_step(life, alpha):
    """One sim tick of FlyingText_run (0x2022a8).

    life and alpha are the u16 fields +0x96 and +0x94. Alpha drops by 3 only while
    the incoming signed life is below 31, and a negative result is stored as 0.
    Life always drops by 1. The object deletes itself (vtable + 8) when the new
    signed life is <= 0. Returns (life, alpha, delete).
    """
    life_s = _sx16(life)
    alpha &= 0xffff
    if life_s < 31:
        alpha = (alpha - 3) & 0xffff
        if _sx16(alpha) < 0:
            alpha = 0
    life_s -= 1
    return life_s & 0xffff, alpha, life_s <= 0


def flying_text_style(kind, crit, alpha):
    """Colour word, whether +0x78 is forced to 5, and the extra world-z lift.

    Kind 1 (0x1f3890) is 0x602060, forces x to 5 and adds 60 over the +72 head
    offset. Kind 2 with +0x84 clear (0x1f38ec) is 0x406e40, also forces x to 5,
    and adds 12. Any other kind with +0x84 set, and kind 2 with it set, is
    alpha<<24 | 0x008080 with no lift (0x1f394c). Otherwise 0x323c3c (0x1f3968).
    Kind 1 does not look at +0x84.
    """
    a = (alpha & 0xff) << 24
    if kind == 1:
        return a | 0x602060, True, 0x42700000
    if kind == 2 and not crit:
        return a | 0x406e40, True, 0x41400000
    if crit:
        return a | 0x008080, False, 0
    return a | 0x323c3c, False, 0


def flying_text_anchor_z(world_z, extra):
    """Head offset 72 (0x42900000 at 0x1f3870) plus the style's extra lift."""
    return F.add(F.add(world_z, 0x42900000), extra)


def flying_text_screen(x_off, y_off, clip_x, clip_y, w):
    """Screen point after mat4_transformPoint (0x1f3990..0x1f3a70).

    clip_x/clip_y/w are the transformed point; w is the value left in f0.
    x = x_off + trunc(0.5 * x/w) + 320, y = y_off + trunc(y/w) + 224.
    """
    inv = F.div(F.ONE, w)
    x = F.to_int(F.mul(F.mul(clip_x, inv), 0x3f000000))
    y = F.to_int(F.mul(clip_y, inv))
    return _addu(_addu(x_off, x), 0x140), _addu(_addu(y_off, y), 0xe0)


# Minimap mode tables, executed from minimap_applyMode 0x1e3ff0.
# Byte offset -> raw float. 0x53e1b8 holds the offsets; its bytes +0x30 are the
# scales (also addressed as 0x53e1e8). 0x53e218 holds the second pair.
_MINIMAP_A = {
    0: 0, 4: 0, 8: 0x43480000, 12: 0xc2f00000, 16: 0x43340000, 20: 0xc2f00000,
    24: 0, 28: 0, 32: 0xc3700000, 36: 0x430c0000, 40: 0xc3700000, 44: 0x430c0000,
    0x30: 0x3f666666, 0x34: 0x3f333333, 0x38: 0, 0x3c: 0,
}
_MINIMAP_B = {
    0: 0x43a00000, 4: 0x43600000, 8: 0x42f00000, 12: 0x42c80000,
    16: 0, 20: 0, 24: 0x43a00000, 28: 0x43600000, 32: 0x42f00000, 36: 0x42c80000,
    40: 0, 44: 0,
}
_MINIMAP_F18 = {0: 0x41800000, 4: 0x41200000, 8: 0x41200000, 12: 0}   # 0x53e1f8
_MINIMAP_F17 = {0: 0x40c00000, 4: 0x40a00000, 8: 0x40a00000, 12: 0}   # 0x53e208
MINIMAP_APPROACH = 0x3e800000     # 0.25, 0x1e4698
MINIMAP_SNAP = 0x3ba3d70a         # 0.005, 0x1e4674


def minimap_params(mode, players):
    """The five floats 0x1e3ff0 stores, as raw patterns.

    Order is 0x86af58, 0x86af5c, 0x86af60, 0x86af64, 0x86af68
    (scale, then the A-table pair, then the B-table pair). players < 2 uses
    byte offsets (mode<<3) and (mode<<3)+4; two or more players use
    (mode<<3)+0x18 and (mode<<3)+0x1c. Mode 0's two columns happen to match.
    """
    single = players < 2
    off_lo = (mode << 3) + (0 if single else 0x18)
    off_hi = (mode << 3) + (4 if single else 0x1c)
    return (_MINIMAP_A[0x30 + (mode << 2)], _MINIMAP_A[off_lo], _MINIMAP_A[off_hi],
            _MINIMAP_B[off_lo], _MINIMAP_B[off_hi])


def minimap_extra(mode):
    """The two floats 0x1e4cf0 passes to 0x168cac (f18 from 0x53e1f8, f17 from 0x53e208)."""
    return _MINIMAP_F18[mode << 2], _MINIMAP_F17[mode << 2]


def minimap_approach(current, target):
    """One frame of the offset chase in minimap_draw (0x1e4664..0x1e46a8).

    Equal values stay. A gap below 0.005 snaps to the target. Otherwise
    current += 0.25 * (target - current). The same step is applied to each
    of the four offset floats.
    """
    if F.eq(current, target):
        return current
    diff = F.sub(target, current)
    if F.lt(diff & 0x7fffffff, MINIMAP_SNAP):
        return target
    return F.add(current, F.mul(diff, MINIMAP_APPROACH))


def minimap_zoom(scale, stick):
    """0x1e4ca0: the scale float times the stick zoom at 0x4f71a0, passed as f14."""
    return F.mul(scale, stick)


def minimap_player_blip(kind):
    """Three bytes written for a player blip, or None when kind is not 0..3.

    minimap_blipColor 0x1e40a8. The word at the object +0x3c8 is both this index
    and the player-record index whose health (+0xac) gates the blink. Order is
    the three out-pointers a3, t0, t1.
    """
    return {0: (0xb6, 0x2f, 0x3a), 1: (0x00, 0xbf, 0x00),
            2: (0xb4, 0xb2, 0x00), 3: (0x1d, 0x20, 0xa1)}.get(kind)


def minimap_player_drawn(health, sim_frame):
    """0x1e4154: health <= 0 draws only on g_simFrame bit 0x20."""
    if health <= 0 and (sim_frame & 0x20) == 0:
        return False
    return True


# Compass. Label arguments are the text call; the model anchor is separate.
COMPASS_OFFSET = (0xbde977c8, 0x3e20c38f, 0xc0b8273d)   # 0x1df728
COMPASS_LABEL = (0x41, 0x18a, 0x83, -0x64, 0x1f4, 0x12)  # x, y, width, top, bottom, line
COMPASS_LABEL_COLOUR = 0x632f6159


def _row(m, row, v):
    s = F.mul(m[row], v[0])
    s = F.add(s, F.mul(m[row + 1], v[1]))
    s = F.add(s, F.mul(m[row + 2], v[2]))
    return F.add(s, m[row + 3])


def mat4_xyz(m, v):
    """0x165fc0: xyz of a point through a 4x4 stored as 16 consecutive floats.

    Row i is m[4i:4i+4]. The w it computes is left in f0 and not stored.
    """
    return _row(m, 0, v), _row(m, 4, v), _row(m, 8, v)


def compass_anchor(view, camera):
    """World origin of the compass model (0x1df7dc..0x1df8e0).

    view is g_viewProj (16 raw floats). The offset is transformed by 0x165fc0
    and added to g_cameraPos 0x44f038. Mesh extents are not in this function.
    """
    x, y, z = mat4_xyz(view, COMPASS_OFFSET)
    return F.add(x, camera[0]), F.add(y, camera[1]), F.add(z, camera[2])


# Help box 0x1dcd1c and notice box 0x1dd014. wrap_height is text_drawWrapped's
# return (end y - start y). Colours below are before color_scale.
HELP_TITLE = (0x144, 0x64)
HELP_BODY = (0x84, 0x82, 0x194, 0, 0x1c0, 0x15)     # x, y, width, top, bottom, line
HELP_TITLE_COLOUR = 0x8028444e
HELP_BODY_COLOUR = 0x80464646
HELP_FRAME = (0x74, 0x5e, 0x1a0)                    # x, y, width
HELP_INNER = (0x7c, 0x68, 0x1a0)
HELP_INNER_TINT = 0x3f000000
HELP_CLOSE_DELAY = 0x3c


def help_button_alpha(close_delay):
    """0x1dce04..0x1dce40: clamp(128 - delay*10, 0, 128)."""
    a = 0x80 - close_delay * 10
    if a < 0:
        a = 0
    if a >= 0x81:
        a = 0x80
    return a


def help_button_colour(close_delay):
    return (help_button_alpha(close_delay) << 24) | 0x464646


def _half_toward_zero(width):
    """0x1dce5c: (width + (width >> 31)) >> 1."""
    return (width + (width >> 31)) >> 1


def help_box(wrap_height, label_width):
    """Geometry that does not depend on the pulse. Button and label share y.

    The affirmation string is left-aligned at 324 - half its width; the '%c'
    glyph sits 0x19 to its left (0x1dce6c). Frame height is the wrap height
    plus 0x4c, and so is the inner frame's: both calls take $20 after the
    addiu at 0x1dce00 (corrected 2026-10-21, executed by
    tools/difftest_ui_text_gaps.py help.task; the inner frame is style 0, ctile).
    """
    half = _half_toward_zero(label_width)
    y = wrap_height + 0x8b
    return {
        'button': (0x144 - half - 0x19, y),
        'label': (0x144 - half, y),
        'frame_height': wrap_height + 0x4c,
        'inner_height': wrap_height + 0x4c,
    }


def notice_column(word):
    """0x1dd044: the per-slot word at 0x86aa98, times 320."""
    return word * 320


def notice_box(column, wrap_height):
    """Notice geometry. column is notice_column's result. No inner frame;
    a rectangle uses colour word 0x3f000000 (0x1dd178)."""
    base = column
    return {
        'title': (base + 0xa0, 0x64),
        'body': (base + 0x24, 0x82, 0x100, 0, 0x1c0, 0x15),
        'button': (base + 0x87, wrap_height + 0x87),
        'label': (base + 0xa0, wrap_height + 0x87),
        'frame': (base + 0x1a, 0x5e, 0x10c, wrap_height + 0x4c),
        'rect': (base + 0x22, 0x66, base + 0x12e, wrap_height + 0xb2),
    }


def message_box_placement(t0, t2, t3, stack0):
    """Prologue of hud_drawMessageBox 0x1df248..0x1df2e0.

    width is t0, or 0x208 when t0 is 0. x = t2 + 320. y = stack0 + 0xdc.
    layer is 6 when t3 is -1, otherwise t3.
    """
    width = t0 if t0 else 0x208
    layer = 6 if (t3 & 0xffffffff) == 0xffffffff else t3
    return _addu(t2, 0x140), _addu(stack0, 0xdc), width, layer


def medal_prompt(pause_menu, armed, mission_menu, network, first_active):
    """hud_drawMedalPrompt 0x1e0698.

    Nothing while pauseMenu is running or 0x4f66b0 is clear. The message box
    is only while missionmenudraw is running; its body key is MedalRoundPickNet
    when this machine is networked and not the first active peer. The list at
    (320, 220) is drawn whenever the prompt is armed.
    """
    if pause_menu or not armed:
        return None
    body = None
    if mission_menu:
        body = 'MedalRoundPickNet' if network and not first_active else 'MedalRoundPick'
    return {
        'title_key': 'MedalRound' if mission_menu else None,
        'body_key': body,
        'box': message_box_placement(0, 0, -1, -0x1c),
        'list': (0x140, 0xdc),
    }


def net_cam_show(network, other_slot, health_zero, has_object, countdown, alive):
    """Whether hud_drawNetCamPrompt 0x1e01b8 calls Camera_cycleSpectated.

    Offline never does. other_slot is the nonzero result of 0x1ec580. A dead
    local player (health +0xac == 0) whose object is missing or whose dead
    countdown is 0 forces the call when any player is alive.
    """
    if not network:
        return False
    show = bool(other_slot)
    if health_zero and (not has_object or countdown == 0) and alive != 0:
        show = True
    return show


NET_CAM_NAME = (0x140, 0x160)       # text_drawAsciiCentered, layer 6
NET_CAM_PROMPT = (0x140, 0x174)     # text_drawWideCentered of 'netCamToggle'
NET_CAM_PROMPT_COLOUR = 0x804d4d4d


def net_cam_pad(slot):
    """Byte offset from 0x4028dc of this slot's raw pad word (0x1e0290)."""
    return slot * 0x58


# Arena overlay 0x305904. A player is considered while the float at
# 0x5038a0 + slot*12 is below 2. Each of five steps draws when
# max(0, timer - step*0.03) <= 1.
ARENA_STEP = 0x3cf5c28f


def arena_player_active(timer):
    return F.lt(timer, 0x40000000)


def arena_step_shown(timer, step):
    t = F.sub(timer, F.mul(F.from_int(step), ARENA_STEP))
    if F.lt(t, F.ZERO):
        t = F.ZERO
    return F.le(t, F.ONE)


def arena_pulse_args(step):
    """Arguments of fx_pulseColor for step 0..4 (0x305aec)."""
    return 0x80 - step * 0x10, 0x7d0 - step * 0xc8


# item_getPicture 0x108358 is reached only through these direct calls.
# itemList_drawGrid is called from itemList_draw; itemList_draw is called from
# itemList_update 0x1d14c8. Live jal chains: inventory_runTask -> inventory_runPanel,
# and shop_task -> shop_run. 0x1c7908 also calls itemList_update and has no jal caller.
PICTURE_SITES = (0x1cc8ec, 0x1cd4b0)
PICTURE_DIMENSION_SITES = (0x1cbd2c, 0x1cc904)
