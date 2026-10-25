#!/usr/bin/env python3
"""ref_ui_text_gaps.py - reference models for the UI text gaps of SLUS-20973 v2.00.

The native strings and dialog rounds left these drawn-but-unverified or refused:
the help box's inner frame, button glyph and label; the bust panel's meter, font,
sprite colour and art layout; the compass mesh; the help chime's slot; the dialog
UI fade step; the dialog cursor / "more" glyph byte; the miss text for a quoted
showName key.  docs/ui-text-gaps.md is the contract; tools/difftest_ui_text_gaps.py
runs the original functions in tools/ee_emu.py against every model below.

Floats are raw single-precision patterns and use ref_core's R5900 arithmetic.
No game data is in this file: every number is an instruction operand or a data
word of the executable, given with its address.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_core as F                    # noqa: E402
import ref_ui_composite as UC           # noqa: E402
import ref_ui_layout as UL              # noqa: E402
import ref_anim as A                    # noqa: E402
import ref_strings as RS                # noqa: E402

M32 = 0xFFFFFFFF


def s8(x):
    x &= 0xFF
    return x - 0x100 if x & 0x80 else x


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def s32(x):
    x &= M32
    return x - 0x100000000 if x & 0x80000000 else x


def half_toward_zero(v):
    """(v + (v >> 31)) >> 1 on a signed word: C division by two."""
    v = s32(v)
    return (v + (1 if v < 0 else 0)) >> 1


# =======================================================================================
# 1. The UI ramps: g_uiPulse decay and the dialog fade step (mainloop step 13)
# =======================================================================================
G_UI_PULSE = 0x506060           # float[4]
G_UI_FADE_IN = 0x506070         # float[4]
UI_RAMPS = (0x323448, 0x3234D4)  # the slice after gfx_endFrame, once per displayed frame
PULSE_DECAY = 0x3F4CCCCC        # 0.8 (operand at 0x323484/0x323488)
FADE_STEP = 0x3DF5C28F          # 0.12 (operand at 0x3234ac/0x3234b0)
UI_START_PULSE = 0x320EA4       # g_uiPulse[i] = 2.0
UI_RESTART_FADE_IN = 0x320EC4   # g_uiFadeIn[i] = 0


def ui_ramps_step(pulse, fade):
    """0x323448..0x3234d0, for i = 0..3:
         if 1.0 < pulse[i]: pulse[i] = (pulse[i] - 1.0) * 0.8 + 1.0
         if fade[i] < 1.0:  fade[i] += 0.12; if 1.0 < fade[i]: fade[i] = 1.0
    The fade store happens before the clamp test (0x3234c4 then 0x3234c8)."""
    pulse, fade = list(pulse), list(fade)
    for i in range(4):
        p = pulse[i]
        if F.lt(F.ONE, p):
            pulse[i] = F.add(F.mul(F.sub(p, F.ONE), PULSE_DECAY), F.ONE)
        f = fade[i]
        if F.lt(f, F.ONE):
            n = F.add(f, FADE_STEP)
            fade[i] = F.ONE if F.lt(F.ONE, n) else n
    return pulse, fade


def fade_ramp(start=F.ZERO, limit=64):
    """The values g_uiFadeIn[0] takes on successive displayed frames after
    ui_restartFadeIn, ending with the first frame at exactly 1.0."""
    out, f = [], start
    for _ in range(limit):
        _, fs = ui_ramps_step([F.ONE] * 4, [f] * 4)
        f = fs[0]
        out.append(f)
        if f == F.ONE:
            return out
    raise ValueError('fade did not reach 1.0 in %d frames' % limit)


def pulse_ramp(start=F.TWO, frames=32):
    out, p = [], start
    for _ in range(frames):
        ps, _ = ui_ramps_step([p] * 4, [F.ONE] * 4)
        p = ps[0]
        out.append(p)
    return out


# =======================================================================================
# 2. The button layout words, including the glyph byte at 0x41b978
# =======================================================================================
G_LAYOUT = 0x41B69C             # s8, data-initialised; no store to it was found
G_GLYPH_CONFIRM = 0x41B978      # word: the glyph code drawn with "%c"
G_GLYPH_OTHER = 0x41B97C
G_CONFIRM_MASK = 0x41BFBC       # g_btnConfirmMask
G_CANCEL_MASK = 0x41BFB8
LAYOUT_SLICE = (0x1E6BB4, 0x1E6CA8, 0x1E6CAC)  # game_initCamera 0x1e6b68: start, two exits
PAD_MASK_TO_GLYPH = 0x1EACB8

# game_initCamera 0x1e6bd4..0x1e6ca4: what each layout value stores (address: word).
LAYOUTS = {
    1: {0x41B968: 0x10, 0x41B970: 0x80, 0x41B96C: 0x7C, 0x41B974: 0x7D,
        0x41B978: 0x7E, 0x41B97C: 0x7B, 0x41BFBC: 0x40, 0x41BFB8: 0x20,
        0x41B960: 0x40, 0x41B964: 0x7E},
    0: {0x41B968: 0x80, 0x41B96C: 0x7C, 0x41B978: 0x7B, 0x41B97C: 0x7E,
        0x41BFBC: 0x20, 0x41BFB8: 0x140, 0x41B960: 0x20, 0x41B964: 0x7B},
}
LAYOUT_WORDS = sorted({a for v in LAYOUTS.values() for a in v})


def button_layout(layout_byte):
    """The words game_initCamera stores for the s8 at 0x41b69c; other values store
    nothing (the words keep their data values)."""
    return dict(LAYOUTS.get(s8(layout_byte), {}))


def pad_mask_to_glyph(mask):
    """pad_buttonMaskToGlyph 0x1eacb8 (docs/formats/ui-text.md names the buttons)."""
    table = {0x80: 0x7D, 0x20: 0x7B, 0x10: 0x7C, 0x40: 0x7E, 0x8000: 0x7F, 0x2000: 0x80,
             0x1000: 0x81, 0x4000: 0x82, 0x4: 0x83, 0x1: 0x84, 0x8: 0x85, 0x2: 0x86}
    return table.get(mask & M32, -1 & M32)


def glyph_text(word):
    """sprintf("%c", word) at 0x1dcdd8 / 0x230a14: the low byte, then NUL."""
    b = word & 0xFF
    return bytes([b]) if b else b''


# =======================================================================================
# 3. help_task 0x1dcc78: the help box, its inner frame, button glyph and label
# =======================================================================================
HELP_TASK = 0x1DCC78
G_HELP_OPEN = 0x41B928
G_HELP_CLOSE_DELAY = 0x4F66CC
G_HELP_TITLE, G_HELP_BODY = 0x86AA64, 0x86AA68
G_PAUSED, G_PAUSE_BYTE = 0x41B4F4, 0x44FA80
G_NET = 0x402791                # s8, non-zero in a network game
G_LOCAL_MENU = 0x41B69D
G_MENU_LOCKOUT = 0x41B4FC
G_NUM_PLAYERS = 0x4D8AE0
G_RAW_PADS = 0x4028DC           # + 0x58 * pad
G_ALIVE_COUNT, G_ALIVE_LIST = 0x4F8420, 0x4F8440
G_FONT_MED, G_FONT_SMALL = 0x4F7100, 0x4F7104   # gamefontmed / gamefontsmall words
DL_FREE_WORDS = (0x44FDA4, 0x44FE10, 0x44FE0C)  # free = [0] - (([1] - [2]) >> 3)
DL_MIN_FREE = 3000
HELP_STR_GLYPH, HELP_STR_LABEL = 0x53C768, 0x53C770   # "%c", "Affirmation"
HELP_TITLE_COLOUR, HELP_BODY_COLOUR = 0x8028444E, 0x80464646
HELP_BUTTON_RGB, HELP_FRAME_COLOUR, HELP_INNER_TINT = 0x464646, 0x80808080, 0x3F000000
HELP_CLOSE_DELAY = 60


def help_button_alpha(delay):
    a = 0x80 - s32(delay) * 10
    a = 0 if a < 0 else a
    return 0x80 if a >= 0x81 else a


def help_task(st):
    """One call of help_task while no notice box is open (0x41b518[slot] all 0).

    st: dict with delay, open, net, paused, pause_byte, local_menu, dl_free, pulse
    (raw), title, body (pointers), font_med, glyph_word, num_players, pads (list of
    raw pad words), confirm_mask, alive (list of slots), local (set of slots),
    wrap_height (what text_drawWrapped returns), label_width (text_widthWide).
    Returns (calls, state).  Calls are (name, args...) in order."""
    st = dict(st)
    calls = []
    if s32(st['delay']) > 0:
        st['delay'] = s32(st['delay']) - 1
    if not s8(st['open']):
        return calls, st
    if not s8(st['net']):
        st['paused'] = 1
        st['pause_byte'] = 1
    if s32(st['dl_free']) >= DL_MIN_FREE:
        pulse = st['pulse']
        c1 = UC.scale_rgb(HELP_TITLE_COLOUR, pulse)
        calls.append(('text_begin', st['font_med'], 6, c1, M32))
        if st['title']:
            calls.append(('text_drawWideCentered', 0x144, 0x64, st['title'], 1000000))
        c2 = UC.scale_rgb(HELP_BODY_COLOUR, pulse)
        calls.append(('text_setColor', c2, M32, 0))
        h = 0
        if st['body']:
            calls.append(('text_drawWrapped', 0x84, 0x82, st['body'], 0x194, 0, 0x1C0, 0x15))
            h = s32(st['wrap_height'])
        glyph = glyph_text(st['glyph_word'])
        calls.append(('text_lookup', b'Affirmation'))
        calls.append(('text_widthWide', st['font_med'], 'label', 1000000))
        half = half_toward_zero(st['label_width'])
        c3 = UC.scale_rgb((help_button_alpha(st['delay']) << 24) | HELP_BUTTON_RGB, pulse)
        calls.append(('text_setColor', c3, M32, 0))
        calls.append(('text_drawAscii', (0x144 - half - 0x19) & M32, (h + 0x8B) & M32, glyph, 100000))
        calls.append(('text_lookup', b'Affirmation'))
        calls.append(('text_drawWide', (0x144 - half) & M32, (h + 0x8B) & M32, 'label', 1000000))
        calls.append(('text_end',))
        c4 = UC.scale_rgb(HELP_FRAME_COLOUR, pulse)
        # 0x17fbb8 (x-1, y-4, w+2, h+8, style forced to 2), then the inner ctile frame
        calls.append(('ui_drawFrameImpl', 0x74 - 1, 0x5E - 4, 0x1A0 + 2, (h + 0x4C + 8) & M32,
                      6, c4, 2, 0, 0))
        calls.append(('ui_drawFrameImpl', 0x7C, 0x68, 0x1A0, (h + 0x4C) & M32, 6,
                      HELP_INNER_TINT, 0, 0, 0))
    if s32(st['delay']) != 0:
        return calls, st
    for pad in range(max(s32(st['num_players']), 0)):
        if not (st['pads'][pad] & st['confirm_mask'] & M32):
            continue
        # no break: every pressing pad closes again (post action, messages)
        st['open'] = 0
        st['lockout'] = HELP_CLOSE_DELAY
        if not s8(st['net']):
            calls.append(('script_runPostAction',))
        st['delay'] = HELP_CLOSE_DELAY
        st['pause_byte'] = 0
        if not s8(st['local_menu']):
            st['paused'] = 0
        for slot in st['alive']:
            calls.append(('net_isLocalSlot', slot))
            if slot in st['local']:
                calls.append(('hudmsg_sendMenuState', s8(slot), 0, 0))
    return calls, st


def help_inner_frame(wrap_height):
    """What the inner frame call builds: research-ui's menu_frame with style 0 (ctile),
    the same height as the outer frame's argument (wrap height + 0x4c)."""
    return UL.menu_frame(0x7C, 0x68, 0x1A0, wrap_height + 0x4C, style=0)


# =======================================================================================
# 4. hud_drawBust 0x1dfb6c: meter, font, sprite colour
# =======================================================================================
HUD_DRAW_BUST = 0x1DFB6C
G_BUST_SHOWN, G_BUST_LATCH, G_BUST_FADE = 0x4F66D4, 0x4F66A9, 0x4F66D0
G_BUST_VALUE, G_BUST_MAX = 0x86AB30, 0x86AB34
G_BUST_TEXT, G_BUST_TEXTURE = 0x86AAB0, 0x4F6B48
G_SIM_FRAME = 0x44FDCC
BUST_FADE_STEP = 0x3DACF3DF     # 0.08445 (0x1dfbac)
BUST_TEXT_ALPHA = 0x42DC0000    # 110.0 (0x1dfc38)
BUST_SPRITE_ALPHA = 0x43000000  # 128.0 (0x1dfcd0 and each sprite)
BUST_TEXT_RGB = 0x395F6B
BUST_SPRITE_RGB = 0x808080


def bust_alpha(fade, factor):
    return F.to_uint(F.mul(fade, factor)) & 0xFF


def hud_draw_bust(st):
    """st: shown, latch, fade (raw), value, maximum, sim_frame, font_small, tex
    (dict name -> (w, h) of every res_find result).  Returns (calls, state)."""
    st = dict(st)
    calls = []
    if not s8(st['shown']):
        return calls, st
    f = st['fade']
    f = F.sub(f, BUST_FADE_STEP) if s8(st['latch']) else F.add(f, BUST_FADE_STEP)
    if F.lt(F.ONE, f):
        f = F.ONE
    if F.lt(f, F.ZERO):
        f = F.ZERO
    st['fade'] = f
    st['latch'] = 0
    if s32(st['value']) < 0:
        st['value'] = 0
    value, maximum = s32(st['value']), s32(st['maximum'])
    calls.append(('text_begin', st['font_small'], 6,
                  (bust_alpha(f, BUST_TEXT_ALPHA) << 24) | BUST_TEXT_RGB, M32))
    if maximum == -1:
        calls.append(('text_drawWrapped', 0x20B, 0x187, G_BUST_TEXT, 0x70, -100 & M32, 0x1F4, 0xE))
        calls.append(('text_setColor', (bust_alpha(f, BUST_SPRITE_ALPHA) << 24) | BUST_TEXT_RGB, M32, 0))
        calls.append(('text_drawAsciiCentered', 0x21E, 0x173, b'%d' % value, 0x2710))
    else:
        calls.append(('text_drawWrapped', 0x20F, 0x185, G_BUST_TEXT, 0x70, -100 & M32, 0x1F4, 0xE))
    calls.append(('text_end',))
    tint = (bust_alpha(f, BUST_SPRITE_ALPHA) << 24) | BUST_SPRITE_RGB
    tex = st['tex']
    calls.append(('res_find', b'bust.lmp', b'frame.tex'))
    calls.append(('res_find', b'bust.lmp', b'<portrait>'))
    if maximum != -1:
        calls.append(('res_find', b'bust.lmp', b'fieldmeter.tex'))
        half = half_toward_zero(st['sim_frame'])
        q = abs(half) % 4 * (-1 if half < 0 else 1)          # C remainder
        bar = b'bar_yellow0%d.tex' % q
        calls.append(('res_find', b'bust.lmp', bar))
        bw, bh = tex[bar]
        ratio = F.div(F.from_int(value), F.from_int(maximum))
        fill = F.round_half_away(F.mul(ratio, F.from_int(s16(bw))))
        calls.append(('sprite_clipped', bar, 0x209, 0x179, 6, tint, 0x209, 0x179,
                      (0x209 + fill - 2) & M32, (0x179 + s16(bh)) & M32, 0, 0))
        calls.append(('sprite', b'fieldmeter.tex', 0x1FF, 0x173, 6, tint))
    else:
        calls.append(('res_find', b'bust.lmp', b'fieldnumber.tex'))
        calls.append(('sprite', b'fieldnumber.tex', 0x1FE, 0x172, 6, tint))
    pw, ph = tex[b'<portrait>']
    fw, fh = tex[b'frame.tex']
    calls.append(('sprite', b'<portrait>', (0x1F3 - half_toward_zero(s16(pw))) & M32,
                  (s16(fh) - s16(ph) + 0x16E) & M32, 6, tint))
    calls.append(('sprite', b'frame.tex', (0x1F3 - half_toward_zero(s16(fw))) & M32, 0x171, 6, tint))
    return calls, st


# =======================================================================================
# 5. ui_emitSpriteQuad 0x17ab50: how a sprite uses the two stored fields
# =======================================================================================
SPRITE_QUAD = 0x17AB50
GFX_DISPLAY_FIELD = 0x19D9E4
G_FRAME_MODE = 0x44FDB4         # set: both halves under SCANMSK (gfx_setDisplayRateMode)
G_FIELD_MODE = 0x44FDD4         # s8: data value 1; the session start stores 1
REG_UV, REG_XYZ2, REG_SCANMSK = 0x03, 0x05, 0x22
Z_WORD = 0xA000 << 20           # Z = 10 in bits 32..63 (0x17ac30..0x17ac34: 0xa000 dsll 20)


def _uv(u, v):
    return (u & 0xFFFF) | ((v & 0xFFFF) << 16)


def _xyz(x, y):
    return (x & 0xFFFF) | ((y & 0xFFFF) << 16) | Z_WORD


def sprite_quad(frame_mode, field_mode, tex_w, tex_h, x, y, u0, v0, u1, v1, fields=(0, 0)):
    """The (value, register) qwords ui_emitSpriteQuad appends.  tex_w / tex_h are the
    s16 words +0/+2 of the texture header (h is read as lhu then sign-extended);
    fields are bit 0 of the gfx_displayField results, in call order."""
    w, h = s16(tex_w), s16(tex_h)
    half = h >> 1
    if frame_mode:
        Y = (y * 16 + 0x7200) & M32
        X = (x * 32 + 0x5800) & M32
        X1, Y1 = X + w * 32, Y + h * 16
        odd = Y & 0x10
        return [(2 if odd else 3, REG_SCANMSK),
                (_uv(u0 * 16 + 4, v0 * 8 + 4), REG_UV), (_xyz(X, Y), REG_XYZ2),
                (_uv(u1 * 16 + 4, v1 * 8 + 4), REG_UV), (_xyz(X1, Y1), REG_XYZ2),
                (3 if odd else 2, REG_SCANMSK),
                (_uv(u0 * 16 + 4, half * 16 + v0 * 8), REG_UV), (_xyz(X, Y), REG_XYZ2),
                (_uv(u1 * 16 + 4, half * 16 + v1 * 8), REG_UV), (_xyz(X1, Y1), REG_XYZ2),
                (0, REG_SCANMSK)]
    if s8(field_mode):
        Y = (y * 16 + 0x7200) & M32
        X = (x * 32 + 0x5800) & M32
        if Y & 0x10:
            Y = Y + 0x10 if fields[0] & 1 else Y - 0x10
            base = half * 16 if fields[1] & 1 else -4
        else:
            base = 0 if fields[0] & 1 else half * 16 - 4
        return [(_uv(u0 * 16 + 4, v0 * 8 + base + 4), REG_UV), (_xyz(X, Y), REG_XYZ2),
                (_uv(u1 * 16 + 4, v1 * 8 + base + 4), REG_UV),
                (_xyz(X + w * 32, Y + h * 16), REG_XYZ2)]
    Y = (y * 16 + 0x7200) & M32
    X = (x * 16 + 0x6C00) & M32
    return [(_uv(u0 * 16 + 8, v0 * 16 + 8), REG_UV), (_xyz(X, Y), REG_XYZ2),
            (_uv(u1 * 16 + 8, v1 * 16 + 8), REG_UV), (_xyz(X + w * 16, Y + h * 16), REG_XYZ2)]


def field_calls(frame_mode, field_mode, y):
    """How many times the quad builder asks gfx_displayField."""
    if frame_mode or not s8(field_mode):
        return 0
    return 2 if ((y * 16 + 0x7200) & 0x10) else 1


def woven_line(screen_line, y, h):
    """Inferred progressive equivalent (docs/ui-text-gaps.md 4.4): with field 1 shown on
    the even frame lines, the line `screen_line` of a sprite whose top is y shows the
    picture line screen_line - y of the woven art, for even and odd y alike.  Returns
    (stored row, picture line)."""
    k = screen_line - y
    if not 0 <= k < h:
        return None
    return (k // 2 + (h // 2 if k & 1 else 0), k)


# =======================================================================================
# 6. hud_drawCompass 0x1df720: world matrix, two passes, label
# =======================================================================================
HUD_DRAW_COMPASS = 0x1DF720
G_COMPASS_GATE = 0x4F8424       # word, must be non-zero
G_COMPASS_PLAYER = 0x4F841C     # slot, -1 = none
G_PLAYERS, PLAYER_STRIDE, PLAYER_OBJECT = 0x4D8AF0, 0x4C30, 0x43D8
G_COMPASS_SHOWN = 0x4F66D5
G_COMPASS_TARGET, G_COMPASS_LABEL = 0x86A8F0, 0x86AAF0
G_VIEW_PROJ, G_CAMERA_POS = 0x44F140, 0x44F038
G_MODEL_FLAGS = 0x41C168        # model draw flags; 0x20 = depth test ALWAYS (0x177b54)
G_LIGHT_FLAG, G_LIGHT_DEPTH = 0x4039A0, 0x4039A4
COMPASS_OFFSET = (0xBDE977C8, 0x3E20C38F, 0xC0B8273D)   # 0x1df728..0x1df748
COMPASS_LABEL_COLOUR = 0x632F6159


def compass_world(view, camera, player_xy, target_xy):
    """The mat34 passed to both model_draw calls, and the s16 angle."""
    m = list(view)
    m = F.mat4_translate_local(F.ZERO, F.ZERO, F.ZERO, m)
    (vx, vy, vz), _w = F.mat4_transform_point_transposed(m, COMPASS_OFFSET)
    origin = (F.add(vx, camera[0]), F.add(vy, camera[1]), F.add(vz, camera[2]))
    world = F.mat34_set_identity()
    world = F.mat34_translate_local(origin[0], origin[1], origin[2], world)
    dx = F.sub(player_xy[0], target_xy[0])
    dy = F.sub(player_xy[1], target_xy[1])
    angle = s16(F.atan2_16(dy, dx) - 0x8000)
    world = F.mat34_rotate_axis(world, 2, angle)     # touches only the first nine floats
    return world, angle


def hud_draw_compass(st):
    """st: gate, player (slot), object (pointer or 0), dialog_open, shown, view (16
    raw), camera (3 raw), player_xy, target_xy, flags (0x41c168 before), light_flag,
    light_depth, font_small.  Returns (calls, state)."""
    st = dict(st)
    calls = []
    if not st['gate'] or s32(st['player']) == -1 or not st['object']:
        return calls, st
    calls.append(('dialog_isOpen',))
    if st['dialog_open'] or not s8(st['shown']):
        return calls, st
    world, angle = compass_world(st['view'], st['camera'], st['player_xy'], st['target_xy'])
    st['angle'] = angle
    up = (F.ZERO, F.ZERO, F.ONE)
    calls.append(('model_draw', 5, up, tuple(world), 0, M32, 0, 0,
                  (st['flags'] | 0x20) & M32, st['light_flag'], st['light_depth']))
    st['flags'] = 0
    st['light_flag'] = 1
    st['light_depth'] = (st['light_depth'] + 10) & M32
    calls.append(('model_draw', 5, up, tuple(world), 0, M32, 0, 0,
                  0, st['light_flag'], st['light_depth']))
    calls.append(('light_resetObjectLight',))
    calls.append(('text_begin', st['font_small'], 5, COMPASS_LABEL_COLOUR, M32))
    calls.append(('text_drawWrappedCentered', 0x41, 0x18A, G_COMPASS_LABEL, 0x83, -100 & M32, 0x1F4, 0x12))
    calls.append(('text_end',))
    return calls, st


# =======================================================================================
# 7. soundSeq_updateAll 0x2147c0: the life of the help chime's slot
# =======================================================================================
SOUND_SEQ_UPDATE_ALL = 0x2147C0
G_SOUND_SEQS, SEQ_STRIDE, SEQ_COUNT = 0x871A68, 0x4C, 32
G_VOICES, VOICE_STRIDE, VOICE_COUNT = 0x872880, 0x14, 43
G_CUR_SOUND_SLOT, G_CUR_SOUND_VOLUME = 0x4F8A00, 0x4F8A04
GAME_IS_FROZEN, SOUND_STOP, ANIM_ADVANCE_UNIT = 0x1EBDF8, 0x213EA0, 0x1709D8
EVENT_END = 0x7FFFFFFF


class Slot:
    """One g_soundSeqs entry: an animation state of one track (+0x00..+0x27), then
    +0x28 object handle (pointer to a link node whose +0x0c is the object), +0x2c
    position, +0x38 serial (u16), +0x3a no position, +0x3b plays while frozen,
    +0x3c released, +0x40 volume.  seq.duration is the clip's run-time word +0x40."""

    def __init__(self):
        self.state = A.AnimState(1)
        self.handle_obj = None        # (object position) when +0x28 links an object
        self.handle = 0
        self.pos = (F.ZERO, F.ZERO, F.ZERO)
        self.serial = 0
        self.no_pos = 0
        self.while_frozen = 0
        self.released = 0
        self.volume = F.ONE
        self.duration = {}            # clip id -> s32 at clip +0x40


def sound_seq_update_all(system, slots, voices, frozen, camera, first_index=0):
    """One call.  voices: list of [flags, owner slot, generation].  Returns the list of
    events: ('stop', voice), ('advance', slot, volume) with the system's sound_log
    filled by ref_anim.anim_advance for each advanced slot."""
    events = []
    for i, slot in enumerate(slots, first_index):
        st = slot.state
        if s8(st.count) == 0:
            continue
        track = st.tracks[0]
        if not slot.released:
            clip = track.clip
            free = False
            if clip.sound_times is None:
                free = True
            else:
                idx = s16(track.sound_idx)
                if not 0 <= idx < len(clip.sound_times):
                    raise A.HostFault('sound cursor %d outside the event table' % idx)
                tick = clip.sound_times[idx]
                free = tick == EVENT_END or bool(st.flags & A.STATUS_ENDED)
            if free:
                st.count = 0
                for v, (flags, owner, gen) in enumerate(voices):
                    if flags & 4 and flags & 0x10 and s16(owner) == i and s16(gen) == s16(slot.serial):
                        events.append(('stop', v))
                continue
        else:
            dur = F.from_int(s32(slot.duration.get(id(track.clip), 0)))
            if F.lt(dur, track.time):
                track.time = F.ZERO
        if frozen and not slot.while_frozen:
            continue
        if slot.handle and slot.handle_obj is not None:
            slot.pos = slot.handle_obj          # the linked object's +0x10..+0x1b
        if slot.no_pos:                         # tested after the object copy too
            slot.pos = tuple(camera)
        events.append(('advance', i, slot.volume))
        A.anim_advance(system, F.ONE, st, True, False, False)
    return events


def chime_frames(event_ticks, length):
    """How many sound_update calls a REPORT_END sequence started by sound_playOnObject
    (time 0, cursor 0, flags 4) stays in its slot when nothing is frozen and nothing
    else plays: synthetic helper over ref_anim, for docs/ui-text-gaps.md 6."""
    clip = A.Clip(A.encode_clip([((0, 0, 0), (4096, 0, 0, 0))], length, sound_times=event_ticks), 'chime')
    system = A.AnimSystem(group_limits=[127] * 256)
    slot = Slot()
    A.anim_push(slot.state, clip, A.REPORT_END)
    slot.while_frozen = 1
    frames = 0
    while slot.state.count:
        frames += 1
        sound_seq_update_all(system, [slot], [], False, (F.ZERO,) * 3)
        if frames > 100000:
            return None
    return frames


# =======================================================================================
# 8. The dialog's showName text: the miss text for a quoted key
# =======================================================================================
NAME_SLICE = (0x22F208, 0x22F290)   # obj_getProp, text_lookup, wstr_copy, wstr_len
G_DIALOG_NAME, G_DIALOG_NAME_LEN = 0x8E2D68, 0x8E2CDC


def show_name(table, key, stale=b''):
    """(units copied to 0x8e2d68 without the terminator, length stored to 0x8e2cdc,
    hit).  Quotes are dropped from the request before hashing; a miss shows NF: and the
    first 16 bytes of the stripped key."""
    _addr, units, hit = table.lookup(key, stale)
    return list(units), len(units), hit
