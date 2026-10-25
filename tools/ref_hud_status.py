#!/usr/bin/env python3
"""Status-block draws of hud_drawPlayerStatus 0x1d9cd4 (SLUS-20973 v2.00).

Reference model of the clipped-sprite (0x17fb88) and flat-rectangle (0x17bd30)
submissions made by 0x1d9cd4, in call order: health bar, pending health
rectangle, pending mana rectangle, experience bar, mana bar, level-up glow,
status frame. Text, notices (0x17fb68) and the spell selector are not modelled
here (see ref_hud_dynamic). docs/spec/hud-status.md is the prose version and
tools/difftest_hud_status.py compares this module with the original code run
in tools/ee_emu.py.

Floats are raw 32-bit patterns and all arithmetic goes through ref_core (F),
which follows the R5900 rules of tools/ee_emu.py. Standard library only.

  python3 tools/ref_hud_status.py --vectors N [SEED]   print N TSV vector rows
"""
from collections import namedtuple
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ref_core as F
import ref_hud_dynamic as H
from ref_ui_layout import HUD_X, hud_origins   # noqa: F401  (re-exported for callers)

M32 = 0xFFFFFFFF

# ---- constants (address where the value is formed or compared) ----------------------
PLAYER_BASE = 0x4D8AF0          # 0x1d9de4; record = base + slot * PLAYER_SIZE
PLAYER_SIZE = 0x4C30            # 0x1d9da8
BAR_SPAN = 99                   # 0x1d9eac, converted to float at 0x1d9ecc
BAR_SPAN_F = 0x42C60000         # float(99)
BAR_INSET = 15                  # 0x1d9eb0: S = X + 15
BAR_CLIP_TOP = 24               # 0x1d9f70, 0x1da2a0, 0x1da368
BAR_CLIP_BOTTOM = 124           # 0x1d9f5c, 0x1da278, 0x1da344 (stack argument)
HEALTH_Y = 46                   # 0x1d9f64
XP_Y = 56                       # 0x1da284
MANA_Y = 63                     # 0x1da35c
HUD_LAYER = 6                   # 0x1d9f68, 0x1da0bc, 0x1da1d0, 0x1da360, 0x1da79c
HEALTH_GREY = 0x80              # 0x1d9eb4
HEALTH_FLASH = 0xFF             # 0x1d9ee0, when bit 0 of 0x41b930[slot] is set
FLASH_TABLE = 0x41B930          # 0x1d9ebc; bit 0 cleared by this function (0x1d9ee8)
XP_TINT = 0x80808080            # 0x1da298
MANA_RGB = 0x00ACACAC           # 0x1da34c..0x1da354
MANA_ALPHA = 0x80               # 0x1da2f4
MANA_ALPHA_COOLDOWN = 0x2A      # 0x1da308, when s16 object +0x4ae > 0
ANIM_FRAMES = 11                # 0x1d9ef0: frame = (sim_tick >> 2) % 11
HEALTH_RECT = (47, 51, 0x80000060)   # top, bottom, colour: 0x1da0b4, 0x1da0b8, 0x1da0c4
MANA_RECT = (66, 70, 0x805A4632)     # 0x1da1c8, 0x1da1cc, 0x1da1d8
PENDING_CAPS = (180, 605, 333)       # 0x1da058-0x1da060, 0x1da078-0x1da080, 0x1da094-0x1da09c
PENDING_CAP_OTHER = 447              # 0x1da090-0x1da0ac: every other slot value
DEAD_FLAG = 0x8                      # object +0xc, 0x1d9fac
FRAME_ORIGIN_DX, FRAME_Y = -4, 36    # 0x1da7d0 (X + 7 - 11), 0x1da7d4
FRAME_CLIP = (0, 0, 1000, 1000)      # 0x1da7e0..0x1da7ec
FRAME_TINT = 0x80808080              # 0x1da7dc
CAPACITY_MIN = 3000                  # 0x1d9e9c and 0x17bd6c: free display-list units
# 0x17bd30 packet: interlaced GS X = 32x + 0x5800, else 16x + 0x6c00; Y = 16y + 0x7200
# (0x17be38..0x17be74); XYZ2 Z field 0xa (0x17be9c..0x17bea0).
GS_X_INTERLACED, GS_X_PROGRESSIVE, GS_Y, GS_Z = 0x5800, 0x6C00, 0x7200, 0xA

ClipSprite = namedtuple('ClipSprite',
                        'resource x y layer tint left top right bottom flip_x flip_y')
Rect = namedtuple('Rect', 'x0 y0 x1 y1 layer colour')   # ui_drawRect: two corners

State = namedtuple('State', [
    'slot',            # raw slot (selects the pending cap and the record)
    'x',               # selected HUD origin X (promoted in a net game, see hud_origins)
    'local',           # 0x210(sp): not g_networkMode or net_isLocalSlot(slot)
    'obj_flags',       # player object +0xc (bit 0x8 = dead)
    'health', 'health_max', 'health_pending',   # record +0xac, +0xb0, +0xb4 (patterns)
    'mana', 'mana_max', 'mana_pending',         # record +0xc0, +0xc4, +0xc8 (patterns)
    'tick',            # g_simFrame 0x44fdcc
    'flash',           # word 0x41b930[slot]
    'cooldown',        # s16 player object +0x4ae
    'ack_level', 'level',                       # s8 record +0x58, +0x59
    'exp', 'exp_base', 'exp_next',              # s32 record +0x5c; 0x41b554/0x41b558[ack]
    'glow_alpha',      # 0x86aa50[slot]
])


def _s32(v):
    return F.s32(v)


def _cdiv_rem(a, b):
    """MIPS div remainder (truncating)."""
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return a - q * b


def anim_frame(tick):
    """(tick >> 2) % 11 with C semantics (negative for negative ticks): 0x1d9ef4..0x1d9f08."""
    return _cdiv_rem(_s32(tick) >> 2, ANIM_FRAMES)


def bar_name(colour, tick):
    return 'bar_%s%02d.tex' % (colour, anim_frame(tick))


def fill_right(start, current, maximum):
    """trunc(float(S) + (C / M) * 99): divide, multiply, add, then convert.
    Health 0x1d9f24..0x1d9f84, mana 0x1da318..0x1da37c."""
    return F.to_int(F.add(F.from_int(start), F.mul(F.div(current, maximum), BAR_SPAN_F)))


def xp_fill_right(start, exp, base, nxt):
    """0x1da244..0x1da2b4: float(exp - base) / float(next - base) * 99 + float(S)."""
    num = F.from_int(_s32(exp - base))
    den = F.from_int(_s32(nxt - base))
    return F.to_int(F.add(F.from_int(start), F.mul(F.div(num, den), BAR_SPAN_F)))


def pending_cap(slot):
    """By the raw slot, not the promoted origin: 0x1da050..0x1da0ac / 0x1da164..0x1da1c0."""
    return PENDING_CAPS[slot] if slot in (0, 1, 2) else PENDING_CAP_OTHER


def pending_span(start, current, maximum, pending):
    """Left and uncapped right of a pending rectangle (0x1d9fd8..0x1da04c).

    a = trunc((C / M) * 99); t = trunc(C + pending); if float(t) > M then
    t = trunc(M); b = trunc((float(t) / M) * 99). Left = S + a, right = S + b
    (formed as (X + 7) + (b - a) + (a + 8), 32-bit wrap)."""
    a = F.to_int(F.mul(F.div(current, maximum), BAR_SPAN_F))
    t = F.to_int(F.add(current, pending))
    if F.lt(maximum, F.from_int(t)):
        t = F.to_int(maximum)
    b = F.to_int(F.mul(F.div(F.from_int(t), maximum), BAR_SPAN_F))
    x7 = start - (BAR_INSET - 7)
    return _s32(start + a), _s32(x7 + _s32(b - a) + _s32(a + 8))


def pending_rect(slot, start, current, maximum, pending, spec):
    left, right = pending_span(start, current, maximum, pending)
    cap = pending_cap(slot)
    top, bottom, colour = spec
    return Rect(left, top, min(right, cap), bottom, HUD_LAYER, colour)


def local_flag(network, is_local_slot):
    """0x1d9d60..0x1d9d90: local unless a net game and net_isLocalSlot(slot) is 0."""
    return (not network) or bool(is_local_slot)


def visible(menu_open=0, hud_suppressed=0, shop_open=0, camera_mode=1, slot_active=True,
            has_object=True, vehicle=0, free_units=35000):
    """Every gate before the first draw, 0x1d9cdc..0x1d9ea4, in that order.
    menu_open 0x41b4f8, hud_suppressed s8 0x4f66a8, shop_open 0x41b50c, camera
    *0x4f8450 +0x34 must be 1, net_isSlotActive 0x13dd40, player object
    record +0x43d8, object +0x540 (vehicle) must be 0, and
    g_dlCapacity - (cursor - base) / 8 >= 3000."""
    return (not menu_open and not _s8(hud_suppressed) and not shop_open and camera_mode == 1
            and bool(slot_active) and bool(has_object) and not vehicle
            and free_units >= CAPACITY_MIN)


def _s8(v):
    v &= 0xFF
    return v - 0x100 if v & 0x80 else v


def _s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def status_draws(st):
    """Clipped sprites and rectangles of one visible call, in call order.

    Returns (draws, lookups, new_flash, new_glow_alpha). lookups lists the
    texture names asked of lump_findEntry 0x171de4 (and, for the glow,
    0x17365c) in call order."""
    x, slot = st.x, st.slot
    start = _s32(x + BAR_INSET)
    draws, lookups = [], []
    flash = st.flash & M32
    grey = HEALTH_GREY
    if flash & 1:
        grey = HEALTH_FLASH
        flash &= ~1 & M32
    name = bar_name('red', st.tick)
    lookups.append(name)
    tint = 0x80000000 | (grey << 16) | (grey << 8) | grey
    draws.append(ClipSprite(name, start, HEALTH_Y, HUD_LAYER, tint, start, BAR_CLIP_TOP,
                            fill_right(start, st.health, st.health_max), BAR_CLIP_BOTTOM, 0, 0))
    dead = bool(st.obj_flags & DEAD_FLAG)
    if not dead and st.local:
        if F.lt(F.ZERO, st.health_pending):
            draws.append(pending_rect(slot, start, st.health, st.health_max,
                                      st.health_pending, HEALTH_RECT))
        if F.lt(F.ZERO, st.mana_pending):
            draws.append(pending_rect(slot, start, st.mana, st.mana_max,
                                      st.mana_pending, MANA_RECT))
    ack = _s8(st.ack_level)
    if st.local:
        if ack > 0:
            name = bar_name('green', st.tick)
            lookups.append(name)
            draws.append(ClipSprite(name, start, XP_Y, HUD_LAYER, XP_TINT, start, BAR_CLIP_TOP,
                                    xp_fill_right(start, st.exp, st.exp_base, st.exp_next),
                                    BAR_CLIP_BOTTOM, 0, 0))
        name = bar_name('blue', st.tick)
        lookups.append(name)
        alpha = MANA_ALPHA_COOLDOWN if _s16(st.cooldown) > 0 else MANA_ALPHA
        draws.append(ClipSprite(name, start, MANA_Y, HUD_LAYER, (alpha << 24) | MANA_RGB,
                                start, BAR_CLIP_TOP, fill_right(start, st.mana, st.mana_max),
                                BAR_CLIP_BOTTOM, 0, 0))
    lookups += ['hud_statusbar00.tex', 'hud_multi.tex']
    glow = st.glow_alpha
    fx = _s32(x + FRAME_ORIGIN_DX)
    if st.local:
        if not dead and F.lt(F.ZERO, st.health) and ack < _s8(st.level):
            glow = H.glow_step(_s32(glow))          # +4, capped at 128: 0x1da6f8..0x1da71c
            lookups.append('hud_statusbar00glow.tex')
            tint = H.pulse_grey(H.pulse(st.tick), glow)
            draws.append(ClipSprite('hud_statusbar00glow.tex', fx, FRAME_Y, HUD_LAYER, tint,
                                    *FRAME_CLIP, 0, 0))
        draws.append(ClipSprite('hud_statusbar00.tex', fx, FRAME_Y, HUD_LAYER, FRAME_TINT,
                                *FRAME_CLIP, 0, 0))
    else:
        draws.append(ClipSprite('hud_multi.tex', fx, FRAME_Y, HUD_LAYER, FRAME_TINT,
                                *FRAME_CLIP, 0, 0))
    return draws, lookups, flash, glow


def rect_gs_corners(rect, interlaced=True):
    """GS XYZ2 (X, Y) in 1/16 pixel that 0x17bd30 writes for the two corners
    (0x17be38..0x17be74). The GS sprite rule then fills [X0, X1) x [Y0, Y1).
    Values are 32-bit two's complement; see rect_xyz2 for the stored words."""
    if interlaced:
        xs = [(32 * v + GS_X_INTERLACED) & M32 for v in (rect.x0, rect.x1)]
    else:
        xs = [(16 * v + GS_X_PROGRESSIVE) & M32 for v in (rect.x0, rect.x1)]
    ys = [(16 * v + GS_Y) & M32 for v in (rect.y0, rect.y1)]
    return (xs[0], ys[0]), (xs[1], ys[1])


M64 = (1 << 64) - 1


def rect_xyz2(rect, interlaced=True):
    """The two 64-bit XYZ2 words of the packet (offsets +0x60, +0x70): X | Y << 16 |
    0xa << 32, combined with OR on sign-extended registers (0x17be8c..0x17beb4).
    A negative X therefore sets every bit of the Y and Z fields: corners left of
    the GS origin are not clipped, they corrupt the word."""
    out = []
    for (gx, gy) in rect_gs_corners(rect, interlaced):
        sx = gx - (1 << 32) if gx & 0x80000000 else gx
        sy = gy - (1 << 32) if gy & 0x80000000 else gy
        out.append(((sx & M64) | ((sy << 16) & M64) | (GS_Z << 32)) & M64)
    return tuple(out)


RECT_PACKET_UNITS = 16   # 0x80 bytes per rectangle packet (0x17bda0..0x17bf30)


def rect_packets(free_units, count):
    """How many of `count` consecutive rectangle calls emit a packet when nothing
    else consumes the display list between them: each call checks free >= 3000
    itself (0x17bd6c) and uses RECT_PACKET_UNITS."""
    done = 0
    for _ in range(count):
        if free_units < CAPACITY_MIN:
            break
        free_units -= RECT_PACKET_UNITS
        done += 1
    return done


def seed_draws():
    """Draws per generator (shared 0x404464, cosmetic 0x404460, third 0x404468)
    made by one call of 0x1d9cd4 with the stubs of the difftest: none."""
    return {'shared': 0, 'cosmetic': 0, 'third': 0}


# ---- TSV vectors for the native client ----------------------------------------------
VECTOR_COLUMNS = (
    'slot', 'x', 'local', 'obj_flags', 'health', 'health_max', 'health_pending', 'mana',
    'mana_max', 'mana_pending', 'tick', 'flash', 'cooldown', 'ack_level', 'level', 'exp',
    'exp_base', 'exp_next', 'glow_alpha', 'new_flash', 'new_glow_alpha', 'count')
DRAW_COLUMNS = ('kind', 'resource', 'x0', 'y0', 'x1', 'y1', 'layer', 'tint',
                'clip_left', 'clip_top', 'clip_right', 'clip_bottom')


def vector_row(st):
    """One TSV line: the inputs, the two state effects, the draw count, then per
    draw the 12 DRAW_COLUMNS. Float inputs and tints are 0x-prefixed hex."""
    draws, _lookups, flash, glow = status_draws(st)
    h = lambda v: '0x%08x' % (v & M32)
    cells = [st.slot, st.x, int(bool(st.local)), h(st.obj_flags), h(st.health),
             h(st.health_max), h(st.health_pending), h(st.mana), h(st.mana_max),
             h(st.mana_pending), st.tick, h(st.flash), _s16(st.cooldown), _s8(st.ack_level),
             _s8(st.level), st.exp, st.exp_base, st.exp_next, st.glow_alpha, h(flash), glow,
             len(draws)]
    for d in draws:
        if isinstance(d, Rect):
            cells += ['R', '-', d.x0, d.y0, d.x1, d.y1, d.layer, h(d.colour), '-', '-', '-', '-']
        else:
            cells += ['S', d.resource, d.x, d.y, '-', '-', d.layer, h(d.tint),
                      d.left, d.top, d.right, d.bottom]
    return '\t'.join(str(c) for c in cells)


def random_state(rng, slot=None, x=None, local=None):
    """A state drawn from the ranges the difftest uses (also for vectors)."""
    def val(maximum):
        pick = rng.random()
        if pick < 0.12:
            return 0.0
        if pick < 0.2:
            return -rng.uniform(0.0, 50.0)
        if pick < 0.3:
            return maximum * rng.uniform(1.0, 1.6)
        if pick < 0.4:
            return float(rng.randrange(0, int(maximum) + 2))
        return rng.uniform(0.0, maximum)

    def maxi():
        return rng.choice([rng.uniform(0.5, 4.0), float(rng.randrange(1, 1200)),
                           rng.uniform(10.0, 900.0), 100.0])

    def pend(cur, maximum):
        pick = rng.random()
        if pick < 0.25:
            return 0.0
        if pick < 0.32:
            return -rng.uniform(0.0, 20.0)
        if pick < 0.5:
            return maximum - cur + rng.uniform(0.0, 40.0)
        return rng.uniform(0.0, maximum * 0.5 + 1.0)

    slot = rng.randrange(4) if slot is None else slot
    hm, mm = maxi(), maxi()
    h, m = val(hm), val(mm)
    base = rng.randrange(0, 5000)
    return State(
        slot=slot, x=HUD_X[slot] if x is None else x,
        local=(rng.random() < 0.8) if local is None else local,
        obj_flags=rng.choice([0, 0, 0, DEAD_FLAG, 0x1, DEAD_FLAG | 0x4]),
        health=F.f32(h), health_max=F.f32(hm), health_pending=F.f32(pend(h, hm)),
        mana=F.f32(m), mana_max=F.f32(mm), mana_pending=F.f32(pend(m, mm)),
        tick=rng.choice([rng.randrange(0, 100000), rng.randrange(-200, 0)]),
        flash=rng.choice([0, 1, 2, 3, 0xFFFFFFFF]),
        cooldown=rng.choice([0, 0, 1, 30, 0xFFFF, 0x8000]),
        ack_level=rng.choice([0, 1, 5, 20, 0xFF]), level=rng.choice([1, 2, 5, 21]),
        exp=base + rng.randrange(-100, 3000), exp_base=base,
        exp_next=base + rng.randrange(1, 3000),
        glow_alpha=rng.choice([0, 60, 124, 126, 128]))


def main(argv):
    if len(argv) >= 3 and argv[1] == '--vectors':
        n = int(argv[2])
        rng = random.Random('%d/vectors' % (int(argv[3]) if len(argv) > 3 else 20973))
        print('# ' + '\t'.join(VECTOR_COLUMNS) + '\t| per draw: ' + '\t'.join(DRAW_COLUMNS))
        for _ in range(n):
            print(vector_row(random_state(rng)))
        return 0
    print(__doc__)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
