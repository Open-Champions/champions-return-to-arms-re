#!/usr/bin/env python3
"""difftest_ui_text_gaps.py - compare tools/ref_ui_text_gaps.py with the original code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_ui_text_gaps.py [path/to/SLUS_209.73] [--quick] [--seed N] [-k TEXT] [-v]
  python3 tools/difftest_ui_text_gaps.py --quick --mutate NAME     (exit 0 when the mutation is caught)

Each property runs ORIGINAL functions (or one addressed slice) in tools/ee_emu.py on
synthetic state built here, runs the model on the same state and compares every word
the model claims.  No game file other than the executable is read; textures, clips,
tables and keys are generated.  docs/ui-text-gaps.md lists the properties.
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EmuError, M32              # noqa: E402
import difftest_strings as DS                 # noqa: E402  (Rig with heap and system calls)
import difftest_anim as DA                    # noqa: E402
import ref_anim as A                          # noqa: E402
import ref_core as F                          # noqa: E402
import ref_strings as RS                      # noqa: E402
import ref_ui_text_gaps as R                  # noqa: E402

OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False}
RESULTS = []
M64 = (1 << 64) - 1

TEXT_BEGIN, TEXT_SET_COLOR, TEXT_END = 0x1800B8, 0x1802E0, 0x180500
TEXT_WRAPPED, TEXT_WRAPPED_CENTERED = 0x181280, 0x181530
TEXT_ASCII, TEXT_ASCII_CENTERED = 0x181AA0, 0x181AF8
TEXT_WIDTH_WIDE, TEXT_WIDE, TEXT_WIDE_CENTERED = 0x181BF8, 0x181C10, 0x181CA0
TEXT_LOOKUP, RES_FIND = 0x173C84, 0x17365C
FRAME_IMPL = 0x17C118
SPRITE, SPRITE_CLIPPED = 0x17FB68, 0x17FB88
POST_ACTION, NET_IS_LOCAL, MENU_STATE = 0x1EDAC0, 0x13E150, 0x1DE0DC
DIALOG_IS_OPEN, MODEL_DRAW, LIGHT_RESET = 0x22FBC0, 0x1779B0, 0x148340
OBJ_GET_PROP, FREEZE_ALL, CLEAR_TEXT = 0x14F4C0, 0x11A450, 0x230FE4
G_NOTICE_OPEN = 0x41B518
G_MISS_INDEX = 0x41BFA8


def wanted(name):
    return OPTIONS['filter'] is None or OPTIONS['filter'].lower() in name.lower()


def scaled(count):
    return max(count // 10, 10) if OPTIONS['quick'] else count


def rng_for(tag):
    return random.Random('%s/%s' % (OPTIONS['seed'], tag))


def report(name, chk, text):
    ok = not chk.failures
    RESULTS.append((name, ok))
    print('%s  %-22s %7d cases  %s%s' % ('PASS' if ok else 'FAIL', name, chk.cases, text,
                                        '' if ok else '  [%d mismatches]' % chk.failures))
    if not ok and OPTIONS['verbose']:
        for line in chk.examples[:3]:
            print('        ' + line)
    sys.stdout.flush()


Check = DS.Check


def cbytes(mem, addr, limit=4096):
    out = bytearray()
    while len(out) < limit:
        b = mem.u8(addr + len(out))
        if b == 0:
            break
        out.append(b)
    return bytes(out)


def a32(e, i):
    return e.r[i] & M32


def rand_float(rng, lo, hi, edges=()):
    if edges and rng.random() < 0.08:
        return rng.choice(edges)
    return F.f32(rng.uniform(lo, hi))


SEED_WORDS = (0x404460, 0x40446C)      # g_cosmeticSeed, g_randSeed, 0x404468


class SeedWatch:
    """Records every load and store of the first `cases` calls and counts those that
    touched a seed word (docs/ui-text-gaps.md: which of these calls draw)."""

    def __init__(self, emu, cases=80):
        self.emu, self.left, self.watched, self.touched, self.on = emu, cases, 0, 0, False

    def before(self):
        self.on = self.left > 0
        if self.on:
            self.emu.reads, self.emu.writes, self.emu.record_writes = [], [], True

    def after(self):
        if not self.on:
            return
        lo, hi = SEED_WORDS
        hit = any(lo <= a < hi for _pc, a, _s, _v in self.emu.reads) or \
            any(lo <= a < hi for _pc, a, _s, _v in self.emu.writes)
        self.touched += hit
        self.watched += 1
        self.left -= 1
        self.emu.reads, self.emu.record_writes = None, False
        self.on = False

    def text(self):
        return '; seed words touched in %d of %d watched calls' % (self.touched, self.watched)


EDGE_FLOATS = (F.ZERO, F.ONE, 0x80000000, 0x3F7FFFFF, 0x3F800001, 0x7F7FFFFF, 0xFF7FFFFF,
               0x7F800000, 0x7FC00000, 0x00000001, 0x3F6B851F, 0x3F75C28F, F.TWO)


# =======================================================================================
# 1. UI ramps (fade step, pulse decay) and their two setters
# =======================================================================================
def test_ramps(elf):
    label = 'ui.ramps'
    if not wanted(label):
        return
    rig, rng, chk = DS.Rig(elf), rng_for('ramps'), Check()
    emu, mem = rig.emu, rig.emu.mem
    watch = SeedWatch(emu)

    def run_slice(pulse, fade):
        for i in range(4):
            mem.w32(R.G_UI_PULSE + 4 * i, pulse[i])
            mem.w32(R.G_UI_FADE_IN + 4 * i, fade[i])
        emu.r[30] = 0x500000            # $fp holds 0x500000 in the session loop
        watch.before()
        emu.run(start=R.UI_RAMPS[0], until=(R.UI_RAMPS[1],), max_steps=2000)
        watch.after()
        return ([mem.u32(R.G_UI_PULSE + 4 * i) for i in range(4)],
                [mem.u32(R.G_UI_FADE_IN + 4 * i) for i in range(4)])

    for _ in range(scaled(6000)):
        chk.cases += 1
        pulse = [rand_float(rng, -1.0, 3.0, EDGE_FLOATS) for _ in range(4)]
        fade = [rand_float(rng, -0.5, 1.5, EDGE_FLOATS) for _ in range(4)]
        if rng.random() < 0.05:
            pulse = [rng.getrandbits(32) for _ in range(4)]
            fade = [rng.getrandbits(32) for _ in range(4)]
        got = run_slice(pulse, fade)
        chk.eq('ramps %s %s' % ([hex(p) for p in pulse], [hex(f) for f in fade]),
               got, R.ui_ramps_step(pulse, fade))
    # the ramp from ui_restartFadeIn, frame by frame, and the pulse from ui_startPulse
    for slot in range(4):
        chk.cases += 1
        rig.call(R.UI_RESTART_FADE_IN, slot)
        rig.call(R.UI_START_PULSE, slot)
        chk.eq('setters slot %d' % slot, (mem.u32(R.G_UI_FADE_IN + 4 * slot),
                                          mem.u32(R.G_UI_PULSE + 4 * slot)), (F.ZERO, F.TWO))
        seq_f, seq_p = [], []
        for _ in range(len(R.fade_ramp())):
            p, f = run_slice([mem.u32(R.G_UI_PULSE + 4 * i) for i in range(4)],
                             [mem.u32(R.G_UI_FADE_IN + 4 * i) for i in range(4)])
            seq_f.append(f[slot])
            seq_p.append(p[slot])
        chk.eq('fade ramp slot %d' % slot, seq_f, R.fade_ramp())
        chk.eq('pulse ramp slot %d' % slot, seq_p, R.pulse_ramp(F.TWO, len(seq_p)))
    report(label, chk, 'mainloop step 13 slice 0x323448..0x3234d4 on random g_uiPulse / '
           'g_uiFadeIn, plus ui_restartFadeIn and ui_startPulse and the 9-frame ramp' + watch.text())


# =======================================================================================
# 2. Button layout words (the glyph at 0x41b978) and pad_buttonMaskToGlyph
# =======================================================================================
def test_layout(elf):
    label = 'layout.glyph'
    if not wanted(label):
        return
    rig, rng, chk = DS.Rig(elf), rng_for('layout'), Check()
    emu, mem = rig.emu, rig.emu.mem
    watch = SeedWatch(emu)
    data = {a: mem.u32(a) for a in R.LAYOUT_WORDS}
    chk.cases += 1
    chk.eq('data value of the layout byte', mem.u8(R.G_LAYOUT), 1)
    chk.eq('data value of the confirm mask', mem.u32(R.G_CONFIRM_MASK), 0x40)
    values = [0, 1, 2, 0x7F, 0x80, 0xFF] + [rng.randrange(256) for _ in range(scaled(400))]
    for value in values:
        chk.cases += 1
        sentinel = {a: rng.getrandbits(32) for a in R.LAYOUT_WORDS}
        for a, w in sentinel.items():
            mem.w32(a, w)
        mem.w8(R.G_LAYOUT, value)
        watch.before()
        emu.run(start=R.LAYOUT_SLICE[0], until=R.LAYOUT_SLICE[1:], max_steps=500)
        watch.after()
        want = dict(sentinel)
        want.update(R.button_layout(value))
        got = {a: mem.u32(a) for a in R.LAYOUT_WORDS}
        chk.eq('layout byte 0x%02x' % value, got, want)
    for mask in [1 << b for b in range(32)] + [0, 0x60, 0x140, M32] + \
            [rng.getrandbits(32) for _ in range(scaled(2000))]:
        chk.cases += 1
        chk.eq('pad mask 0x%x' % mask, rig.call(R.PAD_MASK_TO_GLYPH, mask) & M32,
               R.pad_mask_to_glyph(mask))
    for layout, words in R.LAYOUTS.items():
        chk.cases += 1
        chk.eq('layout %d: glyph of the confirm mask is the drawn glyph' % layout,
               R.pad_mask_to_glyph(words[R.G_CONFIRM_MASK]), words[R.G_GLYPH_CONFIRM])
    for a in R.LAYOUT_WORDS:
        mem.w32(a, data[a])
    report(label, chk, 'game_initCamera layout stores 0x1e6bb4..0x1e6ca8 for every layout '
           'byte, pad_buttonMaskToGlyph 0x1eacb8, data values' + watch.text())


# =======================================================================================
# 3. help_task 0x1dcc78
# =======================================================================================
def install_text_stubs(rig, log, label_ptrs, wrap=lambda: 0, width=lambda: 0):
    emu, mem = rig.emu, rig.emu.mem

    def text_name(p):
        return label_ptrs.get(p, p)
    emu.stub(TEXT_BEGIN, function=lambda e: log.append(('text_begin', a32(e, 4), a32(e, 5), a32(e, 6), a32(e, 7))) and 0)
    emu.stub(TEXT_SET_COLOR, function=lambda e: log.append(('text_setColor', a32(e, 4), a32(e, 5), a32(e, 6))) and 0)
    emu.stub(TEXT_END, function=lambda e: log.append(('text_end',)) and 0)
    emu.stub(TEXT_WIDE_CENTERED, function=lambda e: log.append(('text_drawWideCentered', a32(e, 4), a32(e, 5), a32(e, 6), a32(e, 7))) and 0)

    def wrapped(e):
        log.append(('text_drawWrapped',) + tuple(a32(e, i) for i in range(4, 11)))
        return wrap() & M32
    emu.stub(TEXT_WRAPPED, function=wrapped)
    emu.stub(TEXT_WRAPPED_CENTERED, function=lambda e: log.append(('text_drawWrappedCentered',) + tuple(a32(e, i) for i in range(4, 11))) and 0)
    emu.stub(TEXT_ASCII, function=lambda e: log.append(('text_drawAscii', a32(e, 4), a32(e, 5), cbytes(mem, a32(e, 6)), a32(e, 7))) and 0)
    emu.stub(TEXT_ASCII_CENTERED, function=lambda e: log.append(('text_drawAsciiCentered', a32(e, 4), a32(e, 5), cbytes(mem, a32(e, 6)), a32(e, 7))) and 0)

    def width_wide(e):
        log.append(('text_widthWide', a32(e, 4), text_name(a32(e, 5)), a32(e, 6)))
        return width() & M32
    emu.stub(TEXT_WIDTH_WIDE, function=width_wide)
    emu.stub(TEXT_WIDE, function=lambda e: log.append(('text_drawWide', a32(e, 4), a32(e, 5), text_name(a32(e, 6)), a32(e, 7))) and 0)


def test_help(elf):
    label = 'help.task'
    if not wanted(label):
        return
    rig, rng, chk = DS.Rig(elf), rng_for('help'), Check()
    emu, mem = rig.emu, rig.emu.mem
    watch = SeedWatch(emu)
    log, st_box = [], {}
    label_ptr = emu.alloc(0x40)
    install_text_stubs(rig, log, {label_ptr: 'label'}, wrap=lambda: st_box['wrap_height'],
                       width=lambda: st_box['label_width'])

    def lookup(e):
        log.append(('text_lookup', cbytes(mem, a32(e, 4))))
        return label_ptr
    emu.stub(TEXT_LOOKUP, function=lookup)
    emu.stub(FRAME_IMPL, function=lambda e: log.append(
        ('ui_drawFrameImpl',) + tuple(a32(e, i) for i in range(4, 12)) + (mem.u32(a32(e, 29)),)) and 0)
    emu.stub(POST_ACTION, function=lambda e: log.append(('script_runPostAction',)) and 0)

    def is_local(e):
        slot = s32(a32(e, 4))
        log.append(('net_isLocalSlot', slot))
        return 1 if slot in st_box['local'] else 0
    emu.stub(NET_IS_LOCAL, function=is_local)
    emu.stub(MENU_STATE, function=lambda e: log.append(('hudmsg_sendMenuState', R.s8(e.r[4]), a32(e, 5), a32(e, 6))) and 0)
    for slot in range(4):
        mem.w8(G_NOTICE_OPEN + slot, 0)
    for _ in range(scaled(5000)):
        chk.cases += 1
        st = {
            'delay': rng.choice([0, 0, 0, 1, 2, rng.randrange(-5, 100)]),
            'open': rng.choice([0, 1, 1, 1, 0xFF]),
            'net': rng.choice([0, 0, 1]),
            'paused': rng.randrange(3), 'pause_byte': rng.randrange(2),
            'local_menu': rng.choice([0, 0, 1]),
            'lockout': rng.randrange(100),
            'pulse': rand_float(rng, 0.8, 2.2, (F.ONE, F.TWO, 0x3F8CCCCC)),
            'title': rng.choice([0, emu.alloc(4)]),
            'body': rng.choice([0, emu.alloc(4), emu.alloc(4)]),
            'font_med': rng.getrandbits(32),
            'glyph_word': rng.choice([0x7E, 0x7B, 0, rng.getrandbits(32)]),
            'num_players': rng.randrange(0, 5),
            'confirm_mask': rng.choice([0x40, 0x20, rng.getrandbits(16)]),
            'wrap_height': rng.choice([0, 21, 42, 63, rng.randrange(-30, 400)]),
            'label_width': rng.choice([rng.randrange(0, 200), rng.randrange(-50, 50)]),
        }
        st['pads'] = [rng.choice([0, 0, st['confirm_mask'], rng.getrandbits(16)]) for _ in range(4)]
        st['alive'] = rng.sample(range(4), rng.randrange(0, 5))
        st['local'] = set(rng.sample(range(4), rng.randrange(0, 5)))
        big = rng.randrange(100000, 200000)
        used = rng.choice([big - 2999, big - 3000, big - 3001, rng.randrange(0, big)])
        st['dl_free'] = big - used
        base = rng.randrange(0x100000, 0x1000000) & ~7
        mem.w32(R.DL_FREE_WORDS[0], big)
        mem.w32(R.DL_FREE_WORDS[1], base + used * 8)
        mem.w32(R.DL_FREE_WORDS[2], base)
        mem.w32(R.G_HELP_CLOSE_DELAY, st['delay'] & M32)
        mem.w8(R.G_HELP_OPEN, st['open'])
        mem.w8(R.G_NET, st['net'])
        mem.w32(R.G_PAUSED, st['paused'])
        mem.w8(R.G_PAUSE_BYTE, st['pause_byte'])
        mem.w8(R.G_LOCAL_MENU, st['local_menu'])
        mem.w32(R.G_MENU_LOCKOUT, st['lockout'])
        mem.w32(R.G_UI_PULSE, st['pulse'])
        mem.w32(R.G_HELP_TITLE, st['title'])
        mem.w32(R.G_HELP_BODY, st['body'])
        mem.w32(R.G_FONT_MED, st['font_med'])
        mem.w32(R.G_GLYPH_CONFIRM, st['glyph_word'])
        mem.w32(R.G_NUM_PLAYERS, st['num_players'])
        mem.w32(R.G_CONFIRM_MASK, st['confirm_mask'])
        for pad in range(4):
            mem.w32(R.G_RAW_PADS + 0x58 * pad, st['pads'][pad])
        mem.w32(R.G_ALIVE_COUNT, len(st['alive']))
        for k, slot in enumerate(st['alive']):
            mem.w32(R.G_ALIVE_LIST + 4 * k, slot)
        st_box.clear()
        st_box.update(st)
        del log[:]
        try:
            watch.before()
            rig.call(R.HELP_TASK)
            watch.after()
        except EmuError as err:
            chk.eq('help_task ran', str(err), None)
            continue
        calls, after = R.help_task(st)
        chk.eq('help calls', log, calls)
        got = {'delay': s32(mem.u32(R.G_HELP_CLOSE_DELAY)), 'open': mem.u8(R.G_HELP_OPEN),
               'paused': mem.u32(R.G_PAUSED), 'pause_byte': mem.u8(R.G_PAUSE_BYTE),
               'lockout': mem.u32(R.G_MENU_LOCKOUT)}
        want = {'delay': s32(after['delay']), 'open': after['open'] & 0xFF, 'paused': after['paused'],
                'pause_byte': after['pause_byte'], 'lockout': after['lockout']}
        chk.eq('help state', got, want)
    report(label, chk, 'help_task 0x1dcc78: delay, pause, display-list gate, title/body/'
           'glyph/label calls and colours, outer and inner frame arguments, confirm loop' + watch.text())


def s32(x):
    return R.s32(x)


# =======================================================================================
# 4. hud_drawBust 0x1dfb6c
# =======================================================================================
def test_bust(elf):
    label = 'bust.draw'
    if not wanted(label):
        return
    rig, rng, chk = DS.Rig(elf), rng_for('bust'), Check()
    emu, mem = rig.emu, rig.emu.mem
    watch = SeedWatch(emu)
    log, texmap, names = [], {}, {}
    install_text_stubs(rig, log, {})

    def res_find(e):
        lump, entry = cbytes(mem, a32(e, 4)), a32(e, 5)
        name = b'<portrait>' if entry == R.G_BUST_TEXTURE else cbytes(mem, entry)
        log.append(('res_find', lump, name))
        if name not in texmap:
            raise EmuError('res_find of %r not prepared' % name)
        return texmap[name]
    emu.stub(RES_FIND, function=res_find)
    emu.stub(SPRITE, function=lambda e: log.append(
        ('sprite', names[a32(e, 4)], a32(e, 5), a32(e, 6), a32(e, 7), a32(e, 8))) and 0)

    def clipped(e):
        sp = a32(e, 29)
        log.append(('sprite_clipped', names[a32(e, 4)]) + tuple(a32(e, i) for i in range(5, 12)) +
                   (mem.u32(sp), mem.u32(sp + 8), mem.u32(sp + 0x10)))
        return 0
    emu.stub(SPRITE_CLIPPED, function=clipped)
    headers = {}
    for _ in range(scaled(5000)):
        chk.cases += 1
        st = {
            'shown': rng.choice([0, 1, 5, 0xFF, 3]),
            'latch': rng.choice([0, 0, 1, 0x80]),
            'fade': rand_float(rng, -0.3, 1.3, EDGE_FLOATS),
            'value': rng.choice([0, 7, -3, rng.randrange(-100, 1000), rng.randrange(-2 ** 31, 2 ** 31)]),
            'maximum': rng.choice([-1, -1, 0, 100, rng.randrange(-50, 2000), rng.randrange(-2 ** 31, 2 ** 31)]),
            'sim_frame': rng.choice([rng.randrange(0, 100000), rng.randrange(-20, 20)]),
            'font_small': rng.getrandbits(32),
        }
        tex = {}
        for name in [b'frame.tex', b'<portrait>', b'fieldmeter.tex', b'fieldnumber.tex'] + \
                [b'bar_yellow0%d.tex' % q for q in range(-3, 4)]:
            tex[name] = (rng.choice([rng.randrange(1, 300), rng.randrange(0, 0x10000)]),
                         rng.choice([rng.randrange(1, 300), rng.randrange(0, 0x10000)]))
        texmap.clear()
        names.clear()
        for name, (w, h) in tex.items():
            if name not in headers:
                headers[name] = emu.alloc(0x10)
            addr = headers[name]
            mem.w16(addr, w)
            mem.w16(addr + 2, h)
            texmap[name] = addr
            names[addr] = name
        st['tex'] = tex
        mem.w8(R.G_BUST_SHOWN, st['shown'])
        mem.w8(R.G_BUST_LATCH, st['latch'])
        mem.w32(R.G_BUST_FADE, st['fade'])
        mem.w32(R.G_BUST_VALUE, st['value'] & M32)
        mem.w32(R.G_BUST_MAX, st['maximum'] & M32)
        mem.w32(R.G_SIM_FRAME, st['sim_frame'] & M32)
        mem.w32(R.G_FONT_SMALL, st['font_small'])
        del log[:]
        try:
            watch.before()
            rig.call(R.HUD_DRAW_BUST)
            watch.after()
        except EmuError as err:
            chk.eq('hud_drawBust ran', str(err), None)
            continue
        calls, after = R.hud_draw_bust(st)
        chk.eq('bust calls (fade %08x value %d max %d)' % (st['fade'], st['value'], st['maximum']),
               log, calls)
        chk.eq('bust state', (mem.u32(R.G_BUST_FADE), mem.u8(R.G_BUST_LATCH), mem.u32(R.G_BUST_VALUE)),
               (after['fade'], after['latch'] & 0xFF, after['value'] & M32))
    report(label, chk, 'hud_drawBust 0x1dfb6c: fade and latch, value clamp, font word, '
           'text and number colours, both branches, meter clip, sprite tints and placement' + watch.text())


# =======================================================================================
# 5. ui_emitSpriteQuad 0x17ab50: the field rule
# =======================================================================================
def test_sprite(elf):
    label = 'sprite.fields'
    if not wanted(label):
        return
    rig, rng, chk = DS.Rig(elf), rng_for('sprite'), Check()
    emu, mem = rig.emu, rig.emu.mem
    watch = SeedWatch(emu)
    queue, asked = [], []

    def field(e):
        asked.append(1)
        return queue.pop(0) if queue else 0
    emu.stub(R.GFX_DISPLAY_FIELD, function=field)
    dl = emu.alloc(8)
    packet = emu.alloc(0x200)
    tex = emu.alloc(0x10)
    for _ in range(scaled(8000)):
        chk.cases += 1
        frame_mode = rng.choice([0, 0, 1])
        field_mode = rng.choice([1, 1, 0, 0x80])
        w, h = rng.randrange(1, 320), rng.randrange(1, 448)
        x = rng.randrange(-100, 700 - w)
        y = rng.randrange(-100, 500 - (h if h < 448 else 0))
        u0, v0 = rng.randrange(0, 64), rng.randrange(0, 64)
        u1, v1 = u0 + rng.randrange(0, 512), v0 + rng.randrange(0, 512)
        fields = (rng.getrandbits(32), rng.getrandbits(32))
        mem.w8(R.G_FRAME_MODE, 0)
        mem.w32(R.G_FRAME_MODE, frame_mode)
        mem.w8(R.G_FIELD_MODE, field_mode)
        mem.w16(tex, w)
        mem.w16(tex + 2, h)
        mem.w32(dl, packet)
        mem.write(packet, bytes(0x200))
        queue[:] = list(fields)
        del asked[:]
        watch.before()
        rig.call(R.SPRITE_QUAD, dl, tex, x & M64, y & M64, u0, v0, u1, v1)
        watch.after()
        want = R.sprite_quad(frame_mode, field_mode, w, h, x, y, u0, v0, u1, v1, fields)
        got = [(mem.u64(packet + 16 * k), mem.u64(packet + 16 * k + 8)) for k in range(len(want))]
        what = 'quad mode %d/%d x %d y %d w %d h %d fields %d %d' % (
            frame_mode, field_mode, x, y, w, h, fields[0] & 1, fields[1] & 1)
        chk.eq(what, got, want)
        chk.eq(what + ' packet end', mem.u32(dl), packet + 16 * len(want))
        chk.eq(what + ' field calls', len(asked), R.field_calls(frame_mode, field_mode, y))
    mem.w32(R.G_FRAME_MODE, 0)
    mem.w8(R.G_FIELD_MODE, 1)
    report(label, chk, 'ui_emitSpriteQuad 0x17ab50 in frame, field and progressive mode, '
           'even and odd tops, both gfx_displayField answers' + watch.text())


# =======================================================================================
# 6. hud_drawCompass 0x1df720
# =======================================================================================
def test_compass(elf):
    label = 'compass.draw'
    if not wanted(label):
        return
    rig, rng, chk = DS.Rig(elf), rng_for('compass'), Check()
    emu, mem = rig.emu, rig.emu.mem
    watch = SeedWatch(emu)
    log, box = [], {}
    install_text_stubs(rig, log, {})
    ptrs = {}

    def res_find(e):
        key = (cbytes(mem, a32(e, 4)), cbytes(mem, a32(e, 5)))
        box.setdefault('res', []).append(key)
        if key not in ptrs:
            ptrs[key] = emu.alloc(0x10)
        return ptrs[key]
    emu.stub(RES_FIND, function=res_find)

    def model_draw(e):
        m, v = a32(e, 8), a32(e, 7)
        box.setdefault('models', []).append((a32(e, 4), a32(e, 5)))
        log.append(('model_draw', a32(e, 6), tuple(mem.u32(v + 4 * k) for k in range(3)),
                    tuple(mem.u32(m + 4 * k) for k in range(12)), a32(e, 9), a32(e, 10),
                    a32(e, 11), mem.u32(a32(e, 29)), mem.u32(R.G_MODEL_FLAGS),
                    mem.u32(R.G_LIGHT_FLAG), mem.u32(R.G_LIGHT_DEPTH)))
        return 0
    emu.stub(MODEL_DRAW, function=model_draw)
    emu.stub(LIGHT_RESET, function=lambda e: log.append(('light_resetObjectLight',)) and 0)

    def dialog_open(e):
        log.append(('dialog_isOpen',))
        return box['dialog_open']
    emu.stub(DIALOG_IS_OPEN, function=dialog_open)
    obj = emu.alloc(0x40)
    for _ in range(scaled(3000)):
        chk.cases += 1
        st = {
            'gate': rng.choice([0, 1, 1, 1, 1]),
            'player': rng.choice([-1, 0, 1, 2, 3, 1, 0]),
            'object': rng.choice([0, obj, obj, obj, obj]),
            'dialog_open': rng.choice([0, 0, 0, 1]),
            'shown': rng.choice([0, 1, 3, 5, 5]),
            'view': [rand_float(rng, -2.0, 2.0) for _ in range(16)],
            'camera': [rand_float(rng, -5000.0, 5000.0) for _ in range(3)],
            'player_xy': [rand_float(rng, -3000.0, 3000.0) for _ in range(2)],
            'target_xy': [rand_float(rng, -3000.0, 3000.0) for _ in range(2)],
            'flags': rng.getrandbits(8),
            'light_flag': rng.randrange(2),
            'light_depth': rng.randrange(0, 40),
            'font_small': rng.getrandbits(32),
        }
        if rng.random() < 0.05:
            st['target_xy'] = list(st['player_xy'])
        mem.w32(R.G_COMPASS_GATE, st['gate'])
        mem.w32(R.G_COMPASS_PLAYER, st['player'] & M32)
        if st['player'] >= 0:
            mem.w32(R.G_PLAYERS + R.PLAYER_STRIDE * st['player'] + R.PLAYER_OBJECT, st['object'])
        mem.w32(obj + 0x10, st['player_xy'][0])
        mem.w32(obj + 0x14, st['player_xy'][1])
        mem.w8(R.G_COMPASS_SHOWN, st['shown'])
        for k in range(16):
            mem.w32(R.G_VIEW_PROJ + 4 * k, st['view'][k])
        for k in range(3):
            mem.w32(R.G_CAMERA_POS + 4 * k, st['camera'][k])
        mem.w32(R.G_COMPASS_TARGET, st['target_xy'][0])
        mem.w32(R.G_COMPASS_TARGET + 4, st['target_xy'][1])
        mem.w32(R.G_MODEL_FLAGS, st['flags'])
        mem.w32(R.G_LIGHT_FLAG, st['light_flag'])
        mem.w32(R.G_LIGHT_DEPTH, st['light_depth'])
        mem.w32(R.G_FONT_SMALL, st['font_small'])
        box.clear()
        box['dialog_open'] = st['dialog_open']
        del log[:]
        try:
            watch.before()
            rig.call(R.HUD_DRAW_COMPASS)
            watch.after()
        except EmuError as err:
            chk.eq('hud_drawCompass ran', str(err), None)
            continue
        calls, _after = R.hud_draw_compass(st)
        chk.eq('compass calls', log, calls)
        if any(c[0] == 'model_draw' for c in calls):
            vif = ptrs[(b'compass.lmp', b'compass.vif')]
            tex = ptrs[(b'compass.lmp', b'compass.tex')]
            chk.eq('compass resources', (box.get('res'), box.get('models')),
                   ([(b'compass.lmp', b'compass.vif'), (b'compass.lmp', b'compass.tex')] * 2,
                    [(vif, tex)] * 2))
    report(label, chk, 'hud_drawCompass 0x1df720 with the real matrix, atan2 and rotate '
           'functions: gates, world matrix, two passes (flag 0x20, light words), label' + watch.text())


# =======================================================================================
# 7. soundSeq_updateAll 0x2147c0
# =======================================================================================
def test_sound_seq(elf):
    label = 'sound.seqUpdate'
    if not wanted(label):
        return
    rng, chk = rng_for('soundseq'), Check()
    rig = DA.Rig(elf)
    emu, mem = rig.emu, rig.emu.mem
    watch = SeedWatch(emu, cases=20)
    fired = []

    def fire(e):
        fired.append((a32(e, 4), s32(e.r[5]), s32(e.r[6]), a32(e, 7),
                      mem.u32(R.G_CUR_SOUND_SLOT), mem.u32(R.G_CUR_SOUND_VOLUME)))
        return 0
    emu.stub(DA.FIRE_RANGE, function=fire)
    stops = []
    emu.stub(R.SOUND_STOP, function=lambda e: stops.append(s32(e.r[4])) and 0)
    frozen_box = [0]
    emu.stub(R.GAME_IS_FROZEN, function=lambda e: frozen_box[0])
    pose = ((0, 0, 0), (4096, 0, 0, 0))
    clips = []
    for k in range(10):
        length = rng.randrange(4, 50)
        if k == 0:
            sounds = None
        else:
            sounds = sorted(rng.randrange(0, length + 8) for _ in range(rng.randrange(0, 7)))
        clip = rig.load_clip(A.encode_clip([pose], length, sound_times=sounds,
                                           sound_group=rng.choice([0, 0, 1, 14, 50])), 'clip%d' % k)
        clips.append(clip)
    nodes = [emu.alloc(0x10) for _ in range(R.SEQ_COUNT)]
    objs = [emu.alloc(0x20) for _ in range(R.SEQ_COUNT)]
    runs = scaled(60)
    for run in range(runs):
        slots = []
        for i in range(R.SEQ_COUNT):
            slot = R.Slot()
            addr = R.G_SOUND_SEQS + R.SEQ_STRIDE * i
            mem.write(addr, bytes(R.SEQ_STRIDE))
            mem.w8(addr + 5, 1)
            rig.adopt(slot.state, addr)
            if rng.random() < 0.7:
                clip = rng.choice(clips)
                flags = rng.choice([A.REPORT_END, A.REPORT_END, A.LOOP, A.REPORT_END | 0x2000, 0])
                A.anim_push(slot.state, clip, flags)
                track = slot.state.tracks[0]
                if rng.random() < 0.3:
                    track.time = F.f32(rng.uniform(-3, 60))
                if clip.sound_times is not None:
                    track.sound_idx = rng.randrange(0, len(clip.sound_times))
                if rng.random() < 0.15:
                    slot.state.flags |= A.STATUS_ENDED
            slot.serial = rng.randrange(0, 0x80)
            slot.no_pos = rng.choice([0, 1])
            slot.while_frozen = rng.choice([0, 1])
            slot.released = rng.choice([0, 0, 0, 1])
            slot.volume = F.f32(rng.uniform(0, 2))
            slot.pos = tuple(F.f32(rng.uniform(-100, 100)) for _ in range(3))
            if rng.random() < 0.4:
                n = i
                slot.handle = nodes[n]
                mem.w32(nodes[n] + 0xC, objs[n])
                slot.handle_obj = tuple(F.f32(rng.uniform(-500, 500)) for _ in range(3))
                for k in range(3):
                    mem.w32(objs[n] + 0x10 + 4 * k, slot.handle_obj[k])
            for clip in clips:
                d = rng.choice([0, 5, 20, 60, rng.randrange(-5, 100)])
                slot.duration[id(clip)] = d
            mem.write(addr, rig.state_image(slot.state))
            mem.w32(addr + 0x28, slot.handle)
            for k in range(3):
                mem.w32(addr + 0x2C + 4 * k, slot.pos[k])
            mem.w16(addr + 0x38, slot.serial)
            mem.w8(addr + 0x3A, slot.no_pos)
            mem.w8(addr + 0x3B, slot.while_frozen)
            mem.w8(addr + 0x3C, slot.released)
            mem.w32(addr + 0x40, slot.volume)
            slots.append(slot)
        # one shared duration per clip for the released path (the word is in the clip)
        for clip in clips:
            d = rng.choice([0, 5, 20, 60, rng.randrange(-5, 100)])
            mem.w32(clip.addr + 0x40, d & M32)
            for slot in slots:
                slot.duration[id(clip)] = d
        voices = []
        for v in range(R.VOICE_COUNT):
            rec = [rng.choice([0, 4, 0x14, 0x10, 0x16]), rng.randrange(-1, 33), rng.randrange(0, 0x80)]
            if slots and rng.random() < 0.3:
                i = rng.randrange(R.SEQ_COUNT)
                rec = [0x14, i, slots[i].serial]
            voices.append(rec)
            base = R.G_VOICES + R.VOICE_STRIDE * v
            mem.w16(base + 4, rec[0])
            mem.w16(base + 6, rec[1] & 0xFFFF)
            mem.w16(base + 8, rec[2] & 0xFFFF)
        camera = tuple(F.f32(rng.uniform(-1000, 1000)) for _ in range(3))
        for k in range(3):
            mem.w32(R.G_CAMERA_POS + 4 * k, camera[k])
        for step in range(rng.randrange(5, 40)):
            chk.cases += 1
            frozen_box[0] = rng.choice([0, 0, 0, 1])
            rig.set_globals(draw=rng.randrange(0, 1 << 16))
            del fired[:], stops[:]
            del rig.sys.sound_log[:]
            try:
                watch.before()
                rig.call(R.SOUND_SEQ_UPDATE_ALL)
                watch.after()
            except EmuError as err:
                chk.eq('soundSeq_updateAll ran', str(err), None)
                break
            marks = []
            events = []
            for i, slot in enumerate(slots):
                before = len(rig.sys.sound_log)
                ev = R.sound_seq_update_all(rig.sys, [slot], voices, frozen_box[0], camera, i)
                for e in ev:
                    if e[0] == 'stop':
                        events.append(('stop', e[1]))
                    else:
                        events.append(('advance', i))
                        for clip, first, end in rig.sys.sound_log[before:]:
                            marks.append((rig.ptr(clip), first, end,
                                          R.G_SOUND_SEQS + R.SEQ_STRIDE * i + 0x2C, i, slot.volume))
            chk.eq('run %d step %d: stops' % (run, step), stops, [e[1] for e in events if e[0] == 'stop'])
            chk.eq('run %d step %d: fired ranges' % (run, step), fired, marks)
            for i, slot in enumerate(slots):
                addr = R.G_SOUND_SEQS + R.SEQ_STRIDE * i
                chk.eq('slot %d state' % i, mem.read(addr, 0x28), rig.state_image(slot.state))
                chk.eq('slot %d position' % i, tuple(mem.u32(addr + 0x2C + 4 * k) for k in range(3)),
                       tuple(slot.pos))
            chk.eq('current slot / volume after the loop',
                   (mem.u32(R.G_CUR_SOUND_SLOT), mem.u32(R.G_CUR_SOUND_VOLUME)), (M32, F.ONE))
            if chk.failures:
                break
        if chk.failures and not OPTIONS['verbose']:
            break
    report(label, chk, 'soundSeq_updateAll 0x2147c0 over all 32 slots with the real '
           'anim_advance: free rules, looping-voice stops, release restart, freeze, position' + watch.text())


# =======================================================================================
# 8. Dialog showName: lookup of a quoted key
# =======================================================================================
def test_show_name(elf):
    label = 'dialog.showName'
    if not wanted(label):
        return
    rig, rng, chk = DS.Rig(elf), rng_for('showname'), Check()
    emu, mem = rig.emu, rig.emu.mem
    watch = SeedWatch(emu)
    pairs, data = DS.make_table(rng, 300, collide=6, dup=10, quoted=0)
    base = emu.alloc(len(data) + 16)
    mem.write(base, data)
    rig.call(DS.TEXT_REGISTER, base)
    table = RS.TextTable()
    table.register(data, base)
    present = [k for k, _t in pairs]
    key_buf = emu.alloc(0x200)
    box = {}
    emu.stub(OBJ_GET_PROP, function=lambda e: box.__setitem__('prop', cbytes(mem, a32(e, 5))) or key_buf)
    emu.stub(FREEZE_ALL, ret=0)
    emu.stub(CLEAR_TEXT, ret=0)
    for _ in range(scaled(3000)):
        chk.cases += 1
        roll = rng.random()
        if roll < 0.3:
            key = rng.choice(present)
        else:
            key = DS.random_key(rng, 0, 40, high_bytes=0.0)
        if rng.random() < 0.8:
            pieces = bytearray(key)
            for _q in range(rng.randrange(1, 4)):
                pieces.insert(rng.randrange(len(pieces) + 1), 0x22)
            key = bytes(pieces)
        if len(RS.strip_quotes(key)) == 0 and rng.random() < 0.5:
            key = b'""'
        mem.write(key_buf, key + b'\0')
        emu.r[17] = emu.alloc(0x10)
        emu.r[29] = rig.sp
        watch.before()
        emu.run(start=R.NAME_SLICE[0], until=(R.NAME_SLICE[1],), max_steps=200000)
        watch.after()
        units, length, hit = R.show_name(table, key)
        got_len = s32(emu.r[2])
        got_units = rig.units(R.G_DIALOG_NAME, length + 1)
        chk.eq('showName %r' % key, (box.get('prop'), got_units, got_len, mem.u32(G_MISS_INDEX)),
               (b'showName', units + [0], length, table.nf_index))
    report(label, chk, 'dialog_onMsg 0x22f208..0x22f290 with the real text_lookup, wstr_copy '
           'and wstr_len on synthetic tables and quoted keys (hits and misses)' + watch.text())


# ---------------------------------------------------------------------------------------
# Mutations: each changes the model one way; the named property must then fail.
# ---------------------------------------------------------------------------------------
def _wrap(name, post):
    orig = getattr(R, name)
    setattr(R, name, lambda *a, **k: post(orig(*a, **k), *a, **k))


def _mut_inner_height():
    def post(res, st):
        calls, after = res
        return [c if c[:3] != ('ui_drawFrameImpl', 0x7C, 0x68) else
                c[:4] + ((c[4] - 0x4C) & M32,) + c[5:] for c in calls], after
    _wrap('help_task', post)


def _mut_compass_flag():
    def post(res, st):
        calls, after = res
        out = []
        for c in calls:
            if c[0] == 'model_draw' and c[8] & 0x20:
                c = c[:8] + (c[8] & ~0x20,) + c[9:]
            out.append(c)
        return out, after
    _wrap('hud_draw_compass', post)


def _mut_seq_end_status():
    orig = R.sound_seq_update_all

    def mutated(system, slots, *a, **k):
        for slot in slots:
            slot.state.flags &= ~A.STATUS_ENDED
        return orig(system, slots, *a, **k)
    R.sound_seq_update_all = mutated


def _mut_name_quotes():
    orig = R.show_name

    def mutated(table, key, stale=b''):
        keep = RS.strip_quotes
        RS.strip_quotes = lambda k: bytes(k)
        try:
            return orig(table, key, stale)
        finally:
            RS.strip_quotes = keep
    R.show_name = mutated


def _mut_sprite_field():
    orig = R.sprite_quad
    R.sprite_quad = lambda *a, **k: orig(*a[:10], fields=(1, 1))


MUTATIONS = {
    'fade-step-0.125': ('ui.ramps', lambda: setattr(R, 'FADE_STEP', 0x3E000000)),
    'pulse-decay-0.75': ('ui.ramps', lambda: setattr(R, 'PULSE_DECAY', 0x3F400000)),
    'glyph-circle-in-layout-1': ('layout.glyph', lambda: R.LAYOUTS[1].__setitem__(R.G_GLYPH_CONFIRM, 0x7B)),
    'inner-frame-wrap-height': ('help.task', _mut_inner_height),
    'bust-text-alpha-128': ('bust.draw', lambda: setattr(R, 'BUST_TEXT_ALPHA', 0x43000000)),
    'sprite-field-ignored': ('sprite.fields', _mut_sprite_field),
    'compass-no-depth-flag': ('compass.draw', _mut_compass_flag),
    'chime-ignores-end-status': ('sound.seqUpdate', _mut_seq_end_status),
    'showname-keeps-quotes': ('dialog.showName', _mut_name_quotes),
}


TESTS = [test_ramps, test_layout, test_help, test_bust, test_sprite, test_compass,
         test_sound_seq, test_show_name]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    rest = []
    while argv:
        item = argv.pop(0)
        if item == '--quick':
            OPTIONS['quick'] = True
        elif item == '-v':
            OPTIONS['verbose'] = True
        elif item == '--seed' and argv:
            OPTIONS['seed'] = int(argv.pop(0))
        elif item == '-k' and argv:
            OPTIONS['filter'] = argv.pop(0)
        elif item == '--mutate' and argv:
            name = argv.pop(0)
            prop, apply = MUTATIONS[name]
            apply()
            OPTIONS['filter'] = prop
            OPTIONS['mutation'] = name
        else:
            rest.append(item)
    DS.OPTIONS.update(OPTIONS)
    elf = DS.find_elf(rest)
    if elf is None:
        print('SKIP  SLUS_209.73 not found (pass its path); nothing was compared')
        return 0
    print('seed %d%s' % (OPTIONS['seed'], ' (quick)' if OPTIONS['quick'] else ''))
    for test in TESTS:
        test(elf)
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d passed, %d failed' % (len(RESULTS), len(RESULTS) - len(failed), len(failed)))
    if OPTIONS.get('mutation'):
        print('mutation %s: %s' % (OPTIONS['mutation'], 'CAUGHT' if failed else 'NOT CAUGHT'))
        return 0 if failed else 1
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
