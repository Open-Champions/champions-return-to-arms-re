#!/usr/bin/env python3
"""difftest_hud_gold.py - the HUD gold counter end to end against the original code.

Runs the ORIGINAL functions in tools/ee_emu.py on constructed state and compares them with
tools/ref_hud_gold.py (docs/spec/hud-gold.md). Exits 0 with a SKIP line when the ELF is not
on this machine. Does not import unittest (tools/dis.py shadows the stdlib name).

  python3 tools/difftest_hud_gold.py [SLUS_209.73] [--seed N] [-k TEXT] [-v]

Real: hud_addGoldFloater 0x1dc268, hud_tickGold 0x1dcb80, hud_flushGold 0x1dc5f4,
hud_drawGold 0x1dc708, ui_insertThousandsSeparators 0x1c7128, 0x307ee0 (arena bonus life),
mat4_transformPoint 0x165ee0 and the C library (sprintf, strlen). Recording stubs: the text
and sprite calls, net_isLocalSlot, res_find, the sound calls. Any other call is an error.

Every case snapshots the three generators (g_randSeed 0x404464 shared, g_cosmeticSeed
0x404460 and 0x404468 per machine), counts their draws from the stores, and compares the
count with the model's prediction.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ref_core as F
import ref_hud_gold as G
from ee_emu import EE, EmuError

M32 = 0xFFFFFFFF
LIB_LO, LIB_HI = 0x3A5000, 0x3C1740   # newlib, up to libc_ungetc and its neighbours
SPRINTF, STRLEN, MAT4_XFORM = 0x3B7EF0, 0x3B8DC4, 0x165EE0
ADD, TICK, FLUSH, DRAW, SEP, BONUS = 0x1DC268, 0x1DCB80, 0x1DC5F4, 0x1DC708, 0x1C7128, 0x307EE0
REAL = {ADD, TICK, FLUSH, DRAW, SEP, BONUS, MAT4_XFORM}
STUBS = {
    0x13E150: 'net_isLocalSlot', 0x1800B8: 'text_begin', 0x1802E0: 'text_setColor',
    0x181AA0: 'text_drawAscii', 0x181A60: 'text_widthAscii', 0x180500: 'text_end',
    0x17365C: 'res_find', 0x17FB68: 'ui_drawSprite', 0x2134E8: 'sound_playSample',
}
SEEDS = (G.G_RAND_SEED, G.G_COSMETIC_SEED, G.G_THIRD_SEED)
FONT, TEX = 0x00C0FFEE, 0x01650000
OPTIONS = {'seed': 20973, 'filter': None, 'verbose': False}
RESULTS = []


def elf_path(args):
    for a in args:
        if os.path.isfile(a):
            return a
    env = os.environ.get('CHAMPIONS_ELF')
    if env and os.path.isfile(env):
        return env
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for cand in (os.path.join(os.getcwd(), 'SLUS_209.73'), os.path.join(here, 'SLUS_209.73'),
                 os.path.join(here, 'local', 'SLUS_209.73')):
        if os.path.isfile(cand):
            return cand
    return None


def cstr(mem, addr):
    return mem.cstr(addr).encode('latin1')


class Unexpected(Exception):
    pass


class Follow(object):
    """emu.follow: real functions and the C library run, anything else is an error."""

    def __contains__(self, addr):
        if addr in REAL or addr in STUBS or LIB_LO <= addr < LIB_HI:
            return True
        raise Unexpected('unexpected call to 0x%08x' % addr)


class Rig(object):
    def __init__(self, elf):
        self.emu = emu = EE(elf)
        emu.follow = Follow()
        self.log = []
        self.local = 0xF
        self.width = lambda text: 0
        self.buf = emu.alloc(64)
        for addr, name in STUBS.items():
            emu.stub(addr, function=self._stub(name), name=name)
        emu.mem.w32(G.G_FONT, FONT)
        self.stray = []

    def allowed(self):
        out = [(G.FLOATERS, G.FLOATERS + G.FLOATER_SIZE * 8), (G.G_GOLD_PENDING, G.G_GOLD_PENDING + 16),
               (G.G_GOLD_HOLD, G.G_GOLD_HOLD + 16), (G.G_GOLD_ALPHA, G.G_GOLD_ALPHA + 16),
               (G.G_COSMETIC_SEED, G.G_COSMETIC_SEED + 4), (self.buf, self.buf + 64),
               (0x503898, 0x503898 + 48),
               (0x50C000, 0x50D000)]   # newlib's reent/stream area, written inside libc_sprintf
        out += [(G.G_PLAYERS + G.REC_SIZE * i + G.REC_GOLD, G.G_PLAYERS + G.REC_SIZE * i + G.REC_GOLD + 4)
                for i in range(4)]
        return out

    def _stub(self, name):
        def run(em):
            r = em.r
            a = [r[i] & M32 for i in range(4, 12)]
            if name == 'net_isLocalSlot':
                slot = G.s32(a[0])
                self.log.append((name, slot))
                return 1 if 0 <= slot < 4 and self.local >> slot & 1 else 0
            if name == 'text_begin':
                self.log.append((name, 'font' if a[0] == FONT else a[0], a[1], a[2], G.s32(a[3])))
            elif name == 'text_setColor':
                self.log.append((name, a[0], G.s32(a[1]), a[2]))
            elif name == 'text_drawAscii':
                self.log.append((name, a[0], a[1], cstr(em.mem, a[2]), a[3]))
            elif name == 'text_widthAscii':
                text = cstr(em.mem, a[1])
                self.log.append((name, 'font' if a[0] == FONT else a[0], text, a[2]))
                return self.width(text) & M32
            elif name == 'text_end':
                self.log.append((name,))
            elif name == 'res_find':
                self.log.append((name, em.mem.cstr(a[0]), em.mem.cstr(a[1])))
                return TEX
            elif name == 'ui_drawSprite':
                self.log.append((name, 'coin' if a[0] == TEX else a[0], a[1], a[2], a[3], a[4]))
            else:
                self.log.append((name,) + tuple(a[:2]))
            return 0
        return run

    # ---- state transfer ------------------------------------------------------------------
    def put(self, st):
        m = self.emu.mem
        for k, f in enumerate(st.floaters):
            e = G.FLOATERS + G.FLOATER_SIZE * k
            for j in range(3):
                m.w32(e + 4 * j, f.pos[j])
                m.w32(e + 0xC + 4 * j, f.vel[j])
            m.w32(e + 0x18, f.start)
            m.w32(e + 0x1C, f.amount)
            m.w8(e + 0x20, f.slot)
            m.w8(e + 0x21, f.offscreen)
        for i in range(4):
            m.w32(G.G_GOLD_PENDING + 4 * i, st.pending[i])
            m.w32(G.G_PLAYERS + G.REC_SIZE * i + G.REC_GOLD, st.gold[i])
            m.w32(G.G_GOLD_HOLD + 4 * i, st.hold[i])
            m.w32(G.G_GOLD_ALPHA + 4 * i, st.alpha[i])
        m.w32(G.G_SIM_FRAME, st.frame)
        m.w32(G.G_COSMETIC_SEED, st.cosmetic)

    def get(self):
        m = self.emu.mem
        out = []
        for k in range(G.FLOATER_COUNT):
            e = G.FLOATERS + G.FLOATER_SIZE * k
            out.append(tuple(m.u32(e + 4 * j) for j in range(8)) + (m.u8(e + 0x20), m.u8(e + 0x21)))
        for base in (G.G_GOLD_PENDING, G.G_GOLD_HOLD, G.G_GOLD_ALPHA):
            out.append(tuple(m.u32(base + 4 * i) for i in range(4)))
        out.append(tuple(m.u32(G.G_PLAYERS + G.REC_SIZE * i + G.REC_GOLD) for i in range(4)))
        out.append(m.u32(G.G_COSMETIC_SEED))
        return out

    @staticmethod
    def expect(st):
        out = []
        for f in st.floaters:
            out.append(tuple(v & M32 for v in f.pos + f.vel) + (f.start & M32, f.amount & M32,
                                                                  f.slot & 0xFF, f.offscreen & 0xFF))
        for arr in (st.pending, st.hold, st.alpha, st.gold):
            out.append(tuple(v & M32 for v in arr))
        out.append(st.cosmetic & M32)
        return out

    # ---- running ---------------------------------------------------------------------------
    def run(self, addr, *args):
        """Calls addr; returns (draws per generator, stray writes)."""
        emu = self.emu
        before = [emu.mem.u32(a) for a in SEEDS]
        emu.reset_log()
        self.log = []
        emu.call(addr, *args)
        for pc, wa, size, _v in emu.writes:
            if not any(lo <= wa and wa + size <= hi for lo, hi in self.allowed()):
                self.stray.append('0x%08x (%d) by 0x%08x' % (wa, size, pc))
        draws = []
        for a, b in zip(SEEDS, before):
            n = sum(1 for _pc, wa, size, _v in emu.writes if wa == a and size == 4)
            draws.append(n)
        return draws


def seed_state(rng, rig):
    m = rig.emu.mem
    for a in SEEDS:
        m.w32(a, rng.getrandbits(32))


class Prop(object):
    def __init__(self, name):
        self.name, self.cases, self.bad, self.examples = name, 0, 0, []
        self.draws = [0, 0, 0]
        self.notes = {}

    def check(self, ok, example):
        self.cases += 1
        if not ok:
            self.bad += 1
            if len(self.examples) < 3:
                self.examples.append(example() if callable(example) else example)

    def note(self, key, n=1):
        self.notes[key] = self.notes.get(key, 0) + n

    def done(self, text='', rig=None):
        if rig is not None and rig.stray:
            self.bad += len(rig.stray)
            self.examples += rig.stray[:3]
            self.note('stray writes', len(rig.stray))
        ok = not self.bad
        RESULTS.append((self.name, ok))
        extra = ', '.join('%s %d' % kv for kv in sorted(self.notes.items()))
        print('%s  %-8s %6d cases  draws shared/cosmetic/third %d/%d/%d  %s%s%s' % (
            'PASS' if ok else 'FAIL', self.name, self.cases, self.draws[0], self.draws[1], self.draws[2],
            text, ('; ' + extra) if extra else '', '' if ok else '  [%d mismatches]' % self.bad))
        if not ok and OPTIONS['verbose']:
            for e in self.examples:
                print('        ' + str(e)[:800])
        sys.stdout.flush()


def check_draws(p, got, want):
    p.draws = [a + b for a, b in zip(p.draws, got)]
    return list(got) == list(want)


def rnd_float(rng, lo, hi):
    return F.f32(rng.uniform(lo, hi))


def rnd_gold(rng):
    c = rng.random()
    if c < 0.15:
        return G.GOLD_CAP - rng.randrange(0, 200)
    if c < 0.2:
        return rng.getrandbits(32)
    return rng.randrange(0, 2000000)


def rnd_state(rng, busy=0.4):
    st = G.GoldState()
    st.frame = rng.randrange(100, 1 << 20)
    st.cosmetic = rng.getrandbits(32)
    for f in st.floaters:
        if rng.random() < busy:
            f.amount = rng.choice((rng.randrange(1, 500), rng.randrange(1, 1 << 31), (-rng.randrange(1, 99)) & M32))
        f.start = (st.frame - rng.randrange(-3, 60)) & M32
        f.slot = rng.randrange(4)
        f.offscreen = rng.randrange(2)
        f.pos = [rnd_float(rng, -200, 800), rnd_float(rng, -200, 600), 0]
        f.vel = [rnd_float(rng, -12, 12), rnd_float(rng, -12, 12), 0]
    st.pending = [rng.choice((0, 0, rng.randrange(1, 5000), -rng.randrange(1, 50), rng.randrange(1, 1 << 30)))
                  for _ in range(4)]
    st.gold = [rnd_gold(rng) for _ in range(4)]
    st.hold = [rng.choice((0, 0, rng.randrange(1, 61))) for _ in range(4)]
    st.alpha = [rng.choice((0, 0, 128, rng.randrange(-8, 133))) for _ in range(4)]
    return st


def rnd_viewproj(rng):
    m = [rnd_float(rng, -2, 2) for _ in range(16)]
    m[3], m[7], m[11] = rnd_float(rng, -0.5, 0.5), rnd_float(rng, -0.5, 0.5), rnd_float(rng, -1, 1)
    m[15] = rnd_float(rng, -10, 400)
    return m


# ---- properties -------------------------------------------------------------------------
def prop_sep(rig, rng):
    """sprintf("%d") then ui_insertThousandsSeparators, every language byte."""
    p = Prop('sep')
    m = rig.emu.mem
    edges = [0, 1, 9, 10, 99, 100, 999, 1000, 9999, 10000, 99999, 100000, 999999, 1000000,
             9999999, 10000000, G.GOLD_CAP, G.GOLD_CAP + 1, 999999999, -1, -12, -123, -1234,
             -12345, -123456, -1234567, 0x7FFFFFFF, -0x80000000]
    cases = [(v, lang) for v in edges for lang in (0, 1, 2, 0x7F, 0x80, 0xFF)]
    cases += [(rng.randrange(0, G.GOLD_CAP + 1), rng.randrange(256)) for _ in range(3000)]
    cases += [(1234567, lang) for lang in range(256)]
    raw = [(None, rng.randrange(256)) for _ in range(256)]
    for v, lang in cases + raw:
        junk = bytes(rng.randrange(1, 256) for _ in range(40))
        m.write(rig.buf, junk)
        m.w8(G.G_LANGUAGE, lang)
        seed_state(rng, rig)
        if v is not None:
            d1 = rig.run(SPRINTF, rig.buf, G.S_FORMAT, v & M32)
            p.check(cstr(m, rig.buf) == b'%d' % G.s32(v), ('sprintf', v, cstr(m, rig.buf)))
        else:
            digits = bytes(rng.choice(b'0123456789') for _ in range(rng.randrange(0, 16)))
            m.write(rig.buf, digits + b'\0')
            d1 = [0, 0, 0]
        before = bytearray(m.read(rig.buf, 40))
        d2 = rig.run(SEP, rig.buf)
        got = bytes(m.read(rig.buf, 40))
        want = bytes(G.insert_separators(bytearray(before), lang)[:40])
        ok = check_draws(p, [a + b for a, b in zip(d1, d2)], [0, 0, 0])
        p.check(ok and got == want, lambda: (v, lang, bytes(before[:20]), got[:20], want[:20]))
        n = before.index(0)
        if n == 9 and not got.startswith(b'-'):
            p.note('9-digit double separator')
        if v is not None and lang == 0 and 0 <= G.s32(v) <= G.GOLD_CAP:
            p.check(cstr(m, rig.buf) == ('{:,}'.format(G.s32(v))).encode(), ('python format', v))
    p.done('buffer bytes 0..39 after sprintf+separators; random amounts 0..99,999,999, edges, all 256 language bytes, raw digit strings 0..15', rig)


def prop_add(rig, rng):
    p = Prop('add')
    m = rig.emu.mem
    for _ in range(3000):
        st = rnd_state(rng, busy=rng.choice((0.0, 0.5, 0.9, 1.0)))
        slot = rng.randrange(4)
        amount = rng.choice((rng.randrange(1, 300), rng.randrange(1, 1 << 31), (-rng.randrange(1, 9)) & M32))
        vp = rnd_viewproj(rng)
        pos = [rnd_float(rng, -500, 500) for _ in range(3)]
        rig.put(st)
        seed_state(rng, rig)
        m.w32(G.G_COSMETIC_SEED, st.cosmetic)
        for j in range(16):
            m.w32(G.G_VIEW_PROJ + 4 * j, vp[j])
        pa = rig.emu.alloc(16)
        for j in range(3):
            m.w32(pa + 4 * j, pos[j])
        want = st.copy()
        k = G.add_gold_floater(want, slot, pos, amount, vp)
        draws = rig.run(ADD, slot, pa, amount)
        got = rig.get()
        ok = check_draws(p, draws, [0, 1 if k >= 0 else 0, 0])
        p.check(ok and got == Rig.expect(want), lambda: (slot, amount, k, draws, got, Rig.expect(want)))
        p.note('direct credit' if k < 0 else 'floater %d' % k)
        if k >= 0 and want.floaters[k].offscreen:
            p.note('off-screen byte')
    p.done('floaters, pending, hold, alpha, gold, cosmetic seed', rig)


def prop_tick(rig, rng):
    p = Prop('tick')
    for _ in range(3000):
        st = rnd_state(rng)
        rig.put(st)
        seed_state(rng, rig)
        rig.emu.mem.w32(G.G_COSMETIC_SEED, st.cosmetic)
        want = st.copy()
        G.tick_gold(want)
        draws = rig.run(TICK)
        got = rig.get()
        p.check(check_draws(p, draws, [0, 0, 0]) and got == Rig.expect(want), lambda: (got, Rig.expect(want)))
        p.note('moved', sum(1 for a, b in zip(st.floaters, want.floaters) if a.amount and not b.amount))
        p.note('capped', sum(1 for g in want.gold if g == G.GOLD_CAP))
    p.done('floaters, pending, gold', rig)


def prop_flush(rig, rng):
    p = Prop('flush')
    for _ in range(1000):
        st = rnd_state(rng)
        rig.put(st)
        seed_state(rng, rig)
        rig.emu.mem.w32(G.G_COSMETIC_SEED, st.cosmetic)
        want = st.copy()
        G.flush_gold(want)
        draws = rig.run(FLUSH)
        got = rig.get()
        p.check(check_draws(p, draws, [0, 0, 0]) and got == Rig.expect(want), lambda: (got, Rig.expect(want)))
    p.done('floaters, pending, hold, alpha, gold', rig)


def prop_draw(rig, rng):
    p = Prop('draw')
    m = rig.emu.mem
    for _ in range(3000):
        st = rnd_state(rng, busy=rng.choice((0.0, 0.3, 0.8)))
        rig.local = rng.choice((0xF, 0x1, 0x3, rng.randrange(16)))
        a, b = rng.randrange(5, 12), rng.randrange(0, 4)
        rig.width = lambda text, a=a, b=b: a * len(text) + b
        lang = rng.choice((0, 0, 1, rng.randrange(256)))
        off_a = rng.random() < 0.05
        off_b = rng.random() < 0.05
        rig.put(st)
        seed_state(rng, rig)
        m.w32(G.G_COSMETIC_SEED, st.cosmetic)
        m.w8(G.G_LANGUAGE, lang)
        m.w32(G.G_HUD_OFF_A, rng.randrange(1, 9) if off_a else 0)
        m.w8(G.G_HUD_OFF_B, rng.randrange(1, 9) if off_b else 0)
        want = st.copy()
        calls = G.draw_gold(want, lambda s: 0 <= s < 4 and rig.local >> s & 1, rig.width, lang,
                            hud_off=off_a or off_b)
        draws = rig.run(DRAW)
        got = rig.get()
        ok = check_draws(p, draws, [0, 0, 0])
        p.check(ok and got == Rig.expect(want) and rig.log == calls,
                lambda: (rig.log[:12], calls[:12], got == Rig.expect(want)))
        p.note('counters drawn', sum(1 for c in calls if c[0] == 'ui_drawSprite'))
        p.note('right-aligned', sum(1 for c in calls if c[0] == 'text_widthAscii'))
    p.done('call list with arguments and texts, floaters, hold, alpha', rig)


def prop_bonus(rig, rng):
    """0x307ee0: the arena bonus life sets the counter alpha to 128."""
    p = Prop('bonus')
    m = rig.emu.mem
    for _ in range(400):
        st = rnd_state(rng)
        slot = rng.randrange(4)
        rig.put(st)
        seed_state(rng, rig)
        m.w32(G.G_COSMETIC_SEED, st.cosmetic)
        rec = 0x503898 + 12 * slot
        lives = rng.randrange(0, 0x10000)
        m.w16(rec + 2, lives)
        m.w32(rec + 8, rng.getrandbits(32))
        want = st.copy()
        G.arena_bonus_life(want, slot)
        draws = rig.run(BONUS, slot)
        got = rig.get()
        names = [c[0] for c in rig.log]
        ok = (got == Rig.expect(want) and m.u16(rec + 2) == (lives + 1) & 0xFFFF and m.u32(rec + 8) == 0
              and names == ['res_find', 'sound_playSample'] and rig.log[0][1:] == ('arena.lmp', 'bonuslife.vag'))
        p.check(check_draws(p, draws, [0, 0, 0]) and ok, lambda: (slot, rig.log, got))
    p.done('alpha[slot]=128 (hold untouched), lives halfword +1, word +8 = 0, sound call', rig)


def prop_life(rig, rng):
    """Sequences: pickups, ticks (run task) and 0-2 displayed frames per tick, flushes."""
    p = Prop('life')
    m = rig.emu.mem
    vis = []
    for case in range(400):
        st = G.GoldState()
        st.frame = rng.randrange(0, 1 << 20)
        st.cosmetic = rng.getrandbits(32)
        st.gold = [rng.choice((0, 500, rng.randrange(0, 1 << 20), G.GOLD_CAP - rng.randrange(0, 300))) for _ in range(4)]
        rig.local = rng.choice((0x1, 0xF, 0x5))
        rig.width = lambda text: 8 * len(text)
        vp = rnd_viewproj(rng)
        for j in range(16):
            m.w32(G.G_VIEW_PROJ + 4 * j, vp[j])
        m.w8(G.G_LANGUAGE, 0)
        m.w32(G.G_HUD_OFF_A, 0)
        m.w8(G.G_HUD_OFF_B, 0)
        rig.put(st)
        seed_state(rng, rig)
        m.w32(G.G_COSMETIC_SEED, st.cosmetic)
        single = case < 100
        pickups = {0: (0, rng.randrange(1, 2000))} if single else \
            {rng.randrange(0, 150): (rng.randrange(4), rng.randrange(1, 5000)) for _ in range(rng.randrange(1, 12))}
        flush_at = None if single or rng.random() < 0.8 else rng.randrange(20, 200)
        dpt = 1 if single else None
        ok = True
        shown = 0
        pa = rig.emu.alloc(16)
        for t in range(220):
            st.frame = (st.frame + 1) & M32
            m.w32(G.G_SIM_FRAME, st.frame)
            G.tick_gold(st)
            ok &= check_draws(p, rig.run(TICK), [0, 0, 0])
            if t in pickups:
                slot, amount = pickups[t]
                pos = [rnd_float(rng, -300, 300) for _ in range(3)]
                for j in range(3):
                    m.w32(pa + 4 * j, pos[j])
                k = G.add_gold_floater(st, slot, pos, amount, vp)
                ok &= check_draws(p, rig.run(ADD, slot, pa, amount), [0, 1 if k >= 0 else 0, 0])
            if t == flush_at:
                G.flush_gold(st)
                ok &= check_draws(p, rig.run(FLUSH), [0, 0, 0])
            for _ in range(dpt if dpt is not None else rng.choice((0, 1, 1, 1, 2))):
                calls = G.draw_gold(st, lambda s: 0 <= s < 4 and rig.local >> s & 1, rig.width, 0)
                ok &= check_draws(p, rig.run(DRAW), [0, 0, 0])
                ok &= rig.log == calls
            ok &= rig.get() == Rig.expect(st)
            if single and st.alpha[0] > 0:
                shown += 1
        if single:
            vis.append(shown)
        p.check(ok, ('case', case))
    p.note('single-pickup visible frames min', min(vis))
    p.note('max', max(vis))
    p.done('220 ticks each; state compared after every tick', rig)


PROPS = (('sep', prop_sep), ('add', prop_add), ('tick', prop_tick), ('flush', prop_flush),
         ('draw', prop_draw), ('bonus', prop_bonus), ('life', prop_life))


def main(argv):
    args = list(argv)
    rest = []
    while args:
        a = args.pop(0)
        if a == '--seed':
            OPTIONS['seed'] = int(args.pop(0))
        elif a == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif a == '-v':
            OPTIONS['verbose'] = True
        else:
            rest.append(a)
    elf = elf_path(rest)
    if not elf:
        print('SKIP  difftest_hud_gold: SLUS_209.73 not found (argv, CHAMPIONS_ELF, ./, local/)')
        return 0
    print('difftest_hud_gold seed %d' % OPTIONS['seed'])
    for name, fn in PROPS:
        if OPTIONS['filter'] and OPTIONS['filter'].lower() not in name:
            continue
        rng = random.Random('%d/%s' % (OPTIONS['seed'], name))
        rig = Rig(elf)
        try:
            fn(rig, rng)
        except (EmuError, Unexpected) as e:
            RESULTS.append((name, False))
            print('FAIL  %-8s %s' % (name, e))
    failed = [n for n, ok in RESULTS if not ok]
    print('%d properties, %d failed' % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
