#!/usr/bin/env python3
"""Experience bar and new-character health/mana against SLUS-20973 v2.00 (see docs/spec/hud-xp.md).

Runs, in tools/ee_emu.py: hud_drawPlayerStatus 0x1d9cd4 (all callees but the sprite sink,
lump lookups and sprintf auto-stubbed), tex_relocate 0x179e10 with the clipped-sprite
wrapper 0x17fb88 -> 0x17b8b0 on the bar_green header shape, player_initNewCharacter
0x1b1d70 (with player_giveStartingItems 0x1acc78 run for real or stubbed),
player_recalcStats 0x1b6458 after the object is attached, and player_respawn 0x1bd040.
Compares with ref_hud_xp. Counts draws of the three generators around every call.

  python3 tools/difftest_hud_xp.py [SLUS_209.73] [--seed N] [-k TEXT]

Exits 0 with a skip line when the ELF is not found. Does not import unittest
(tools/dis.py would shadow the stdlib name).
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ref_core as F
import ref_hud_xp as X
import ref_ui_layout as L
from ee_emu import EE

G_SEEDS = (('shared', 0x404464), ('cosmetic', 0x404460), ('third', 0x404468))
G_PLAYERS, REC = 0x4D8AF0, 0x4C30
NET_BYTE = 0x402791          # nonzero in a network game (0x1d9d70)


def elf_path(argv):
    if argv:
        return argv[0]
    env = os.environ.get('CHAMPIONS_ELF')
    if env:
        return env
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for cand in (os.path.join(os.getcwd(), 'SLUS_209.73'), os.path.join(here, 'SLUS_209.73'),
                 os.path.join(here, 'local', 'SLUS_209.73')):
        if os.path.isfile(cand):
            return cand
    return None


class Tally:
    def __init__(self):
        self.cases, self.fails, self.draws = {}, [], {}

    def check(self, prop, ok, detail=''):
        self.cases[prop] = self.cases.get(prop, 0) + 1
        if not ok and len(self.fails) < 20:
            self.fails.append('%s: %s' % (prop, detail() if callable(detail) else detail))
        return ok

    def seeds(self, prop, counts):
        total = self.draws.setdefault(prop, {name: 0 for name, _ in G_SEEDS})
        for name, n in counts.items():
            total[name] += n


def seed_draws(emu):
    return {name: sum(1 for _pc, a, size, _v in emu.writes if a == addr and size == 4)
            for name, addr in G_SEEDS}


def run(emu, addr, *args, **kw):
    """Call addr with a fresh write log; return (v0, seed draws during the call)."""
    emu.reset_log()
    v0 = emu.call(addr, *args, **kw)
    return v0, seed_draws(emu)


def s32(v):
    return X.s32(v)


# ---------------------------------------------------------------------------------------
# hud_drawPlayerStatus 0x1d9cd4
# ---------------------------------------------------------------------------------------
class Hud:
    def __init__(self, emu):
        self.emu = emu
        self.textures, self.draws, self.local = {}, [], {}
        emu.follow = set()                    # every callee without a hook returns 0
        emu.stub(0x173558, ret=1)             # lump_load('hud.lmp')
        emu.stub(0x171de4, function=self.lookup)
        emu.stub(0x3b7ef0, function=self.sprintf)
        emu.stub(0x17fb88, function=self.draw)
        emu.stub(0x13dd40, ret=1)             # net_isSlotActive
        emu.stub(0x13e150, function=lambda e: self.local.get(e.r[4] & 0xFFFFFFFF, 1))
        cam = emu.alloc(0x100)
        emu.mem.w32(0x4F8450, cam)
        emu.mem.w32(cam + 0x34, 1)
        for addr in (0x41B4F8, 0x41B50C):
            emu.mem.w32(addr, 0)
        emu.mem.w8(0x4F66A8, 0)
        emu.mem.w32(0x44FE0C, 0)
        emu.mem.w32(0x44FE10, 0)
        emu.mem.w32(0x44FDA4, 35000)
        emu.mem.write(0x41B930, bytes(16))    # health flash bits
        self.objects = [emu.alloc(0x600) for _ in range(4)]

    def lookup(self, e):
        name = e.mem.cstr(e.r[5])
        if name not in self.textures:
            rec, tex = e.alloc(16), e.alloc(64)
            e.mem.w32(rec + 4, tex)
            self.textures[name] = (rec, tex)
        return self.textures[name][0]

    def sprintf(self, e):
        fmt = e.mem.cstr(e.r[5])
        if '%s' in fmt:
            text = fmt.replace('%s', e.mem.cstr(e.r[6]))
        elif '%' in fmt:
            text = fmt % s32(e.r[6])
        else:
            text = fmt
        e.mem.write(e.r[4], text.encode('latin1') + b'\0')
        return len(text)

    def draw(self, e):
        name = next((k for k, v in self.textures.items() if v[1] == e.r[4] & 0xFFFFFFFF), '?')
        clip = (s32(e.r[9]), s32(e.r[10]), s32(e.r[11]), s32(e.mem.u32(e.r[29])))
        self.draws.append(X.XpLayer(name, s32(e.r[5]), s32(e.r[6]), clip, e.r[8] & 0xFFFFFFFF, s32(e.r[7])))

    def setup_slot(self, slot, ack, level, xp, hp=(1.0, 4.0), mana=(2.0, 4.0), dead=False):
        mem, p = self.emu.mem, G_PLAYERS + slot * REC
        obj = self.objects[slot]
        mem.w32(p + 0x43D8, obj)
        mem.w32(obj + 0x540, 0)
        mem.w32(obj + 0x0C, 8 if dead else 0)
        mem.w16(obj + 0x4AE, 0)
        mem.write(p, b'SYNTH\0')
        mem.w8(p + 0x58, ack)
        mem.w8(p + 0x59, level)
        mem.w32(p + 0x5C, xp)
        for off, val in ((0xAC, hp[0]), (0xB0, hp[1]), (0xC0, mana[0]), (0xC4, mana[1])):
            if isinstance(val, float):
                mem.wf32(p + off, val)
            else:
                mem.w32(p + off, val)
        mem.w32(p + 0xB4, 0)
        mem.w32(p + 0xC8, 0)

    def call(self, slot):
        self.draws = []
        _v0, draws = run(self.emu, 0x1D9CD4, slot)
        return list(self.draws), draws


def table_words(emu, ack):
    lo, hi = X.xp_threshold_addresses(ack)
    return s32(emu.mem.u32(lo)), s32(emu.mem.u32(hi))


def check_xp(t, prop, hud, slot, x, tick, ack, xp, local):
    emu = hud.emu
    emu.mem.w32(X.SIM_TICK, tick)
    lower, upper = table_words(emu, ack)
    draws, seeds = hud.call(slot)
    t.seeds(prop, seeds)
    want = X.xp_layer(x, tick, ack, xp, lower, upper, local)
    green = [d for d in draws if d.resource.startswith('bar_green')]
    names = [d.resource[:7] for d in draws]
    ok = green == ([want] if want else [])
    if want and ok:
        ok = names.index('bar_gre') == names.index('bar_red') + 1 and names[names.index('bar_gre') + 1] == 'bar_blu'
    t.check(prop, ok, lambda: (slot, x, tick, ack, xp, lower, upper, local, green, want))
    t.check(prop + ': no seed draw', not any(seeds.values()), seeds)
    t.check(prop + (': drawn' if want else ': not drawn'), True)
    return want


def prop_xp_draw(elf, seed, t):
    prop = 'xp-draw'
    rng = random.Random('%d/%s' % (seed, prop))
    hud = Hud(EE(elf))
    emu = hud.emu
    for case in range(400):
        network = rng.random() < 0.25
        players = rng.randint(1, 4)
        slot = rng.randrange(players)
        hud.local = {s: (rng.random() < 0.6) for s in range(4)}
        emu.mem.w8(NET_BYTE, 1 if network else 0)
        emu.mem.w32(0x4D8AE0, players)
        local_slots = [s for s in range(players) if hud.local[s]]
        x = L.hud_origins(network, local_slots, players)[slot]
        local = (not network) or hud.local[slot]
        kind = rng.random()
        if kind < 0.08:
            ack = rng.choice((0, -1, -128))
        elif kind < 0.12:
            ack = rng.randint(81, 127)
        else:
            ack = rng.randint(1, 80)
        level = max(-128, min(127, ack + rng.choice((0, 0, 0, 1, 2, 5))))
        lower, upper = table_words(emu, ack)
        regime = rng.random()
        if regime < 0.6:
            xp = rng.randint(min(lower, upper), max(lower, upper)) if ack > 0 else rng.randint(0, 10**6)
        elif regime < 0.75:
            xp = lower - rng.randint(1, 5000)
        elif regime < 0.9:
            xp = upper + rng.randint(0, 10**6)
        else:
            xp = rng.randint(-2**31, 2**31 - 1)
        saved = None
        if ack > 0 and rng.random() < 0.1:       # synthetic equal or reversed thresholds
            lo_addr, hi_addr = X.xp_threshold_addresses(ack)
            saved = (lo_addr, emu.mem.u32(lo_addr), hi_addr, emu.mem.u32(hi_addr))
            a = rng.randint(0, 10**7)
            emu.mem.w32(lo_addr, a)
            emu.mem.w32(hi_addr, a if rng.random() < 0.6 else a - rng.randint(1, 1000))
        tick = rng.choice((rng.randint(0, 2**31 - 1), rng.randint(0, 5000)))
        hud.setup_slot(slot, ack & 0xFF, level & 0xFF, xp & 0xFFFFFFFF, dead=rng.random() < 0.3)
        check_xp(t, prop, hud, slot, x, tick, ack, xp, local)
        if saved:
            emu.mem.w32(saved[0], saved[1])
            emu.mem.w32(saved[2], saved[3])


def prop_xp_edges(elf, seed, t):
    prop = 'xp-edges'
    hud = Hud(EE(elf))
    emu = hud.emu
    emu.mem.w8(NET_BYTE, 0)
    emu.mem.w32(0x4D8AE0, 1)
    T = [s32(emu.mem.u32(X.XP_TABLE + 4 * i)) for i in range(X.XP_TABLE_WORDS)]
    cases = [
        ('ack 0, not drawn', 0, 1, 500), ('ack -1, not drawn', -1, 1, 500),
        ('fresh character', 1, 1, 0), ('one below level 2', 1, 1, T[1] - 1),
        ('pending: ack 1, level 2', 1, 2, T[1] + 300), ('pending: ack 1, level 9', 1, 9, T[8]),
        ('below lower', 5, 5, T[4] - 1000), ('above upper', 5, 5, T[5] + 7),
        ('last entry, capped xp', 80, 80, T[80] - 1), ('last entry, xp at T[79]', 80, 80, T[79]),
        ('past the table, ack 81', 81, 81, T[80]), ('past the table, ack 127', 127, 127, 0),
        ('wrapping difference', 3, 3, -2**31), ('large xp', 2, 2, 2**31 - 1),
    ]
    for name, ack, level, xp in cases:
        hud.setup_slot(0, ack & 0xFF, level & 0xFF, xp & 0xFFFFFFFF)
        got = check_xp(t, prop, hud, 0, L.HUD_X[0], 4 * 7, ack, xp, True)
        if '-v' in sys.argv:
            print('  %-28s right=%s' % (name, None if got is None else got.clip[2]))
    lo_addr, hi_addr = X.xp_threshold_addresses(3)
    saved = (emu.mem.u32(lo_addr), emu.mem.u32(hi_addr))
    for a, b, xp in ((500, 500, 500), (500, 500, 900), (500, 500, 100), (900, 500, 700)):
        emu.mem.w32(lo_addr, a)
        emu.mem.w32(hi_addr, b)
        hud.setup_slot(0, 3, 3, xp)
        check_xp(t, prop, hud, 0, L.HUD_X[0], 0, 3, xp, True)
    emu.mem.w32(lo_addr, saved[0])
    emu.mem.w32(hi_addr, saved[1])
    t.check(prop + ': real table strictly increasing', all(T[i] < T[i + 1] for i in range(80)), T[:4])


# ---------------------------------------------------------------------------------------
# bar_green header shape through tex_relocate and the clipped drawer
# ---------------------------------------------------------------------------------------
def prop_drawer(elf, seed, t):
    prop = 'bar-green-drawer'
    rng = random.Random('%d/%s' % (seed, prop))
    emu = EE(elf)
    base = emu.alloc(0x4000)
    quads = []
    parity = [0]
    emu.stub(0x17ab50, function=lambda e: quads.append(tuple(s32(e.r[i]) for i in range(6, 12))))
    emu.stub(0x16b7f0, ret=0)
    emu.stub(0x19d9e4, function=lambda e: parity[0])
    emu.mem.w32(0x44FDA4, 0x10000)
    for shape in X.bar_green_shapes()[:1]:
        w, h = shape.used
        tex = emu.alloc(0x80)
        emu.mem.w16(tex, w)
        emu.mem.w16(tex + 2, h)
        emu.mem.w32(tex + 0x10, 0x80)
        _v, seeds = run(emu, 0x179E10, tex)
        t.seeds(prop, seeds)
        t.check(prop + ': relocate keeps used size', (emu.mem.u16(tex), emu.mem.u16(tex + 2)) == (w, h))
    sp = 0x01FFF000
    S = L.HUD_X[0] + X.X_INSET
    rights = [S - 5, S, S + 1, S + 49, S + 98, S + 99, S + 100, S + 500, 700, 640, 641,
              0x7FFFFFFF, -0x80000000, -1]
    rights += [rng.randint(-2000, 2000) for _ in range(60)]
    for right in rights:
        for interlaced, both, par in ((0, 0, 0), (1, 1, 0), (1, 0, 0), (1, 0, 1)):
            letterbox = rng.choice((0, 0, 16, 32))
            emu.mem.w32(0x44FE0C, base)
            emu.mem.w32(0x44FE10, base)
            emu.mem.w8(X.FIELD_FLAG, interlaced)
            emu.mem.w32(X.BOTH_FIELDS, both)
            emu.mem.w32(X.LETTERBOX, letterbox)
            parity[0] = par
            emu.mem.w32(sp, X.CLIP_BOTTOM)
            emu.mem.w32(sp + 8, 0)
            emu.mem.w32(sp + 16, 0)
            del quads[:]
            _v, seeds = run(emu, 0x17FB88, tex, S, X.XP_Y, X.LAYER, X.XP_TINT, S, X.CLIP_TOP,
                            right, sp=sp)      # sign-extended, as mfc1 leaves it
            t.seeds(prop, seeds)
            regs = [(a - 8) for pc, a, size, v in emu.writes if size == 8 and v == X.GS_SCISSOR_1 and pc == 0x17BB7C]
            got = emu.mem.u64(regs[0]) if len(regs) == 1 else None
            want = X.scissor(S, X.CLIP_TOP, right, X.CLIP_BOTTOM, bool(interlaced), bool(both), par, letterbox)
            t.check(prop, got == want and quads == [(S, X.XP_Y, 0, 0, w, h)],
                    lambda: (right, interlaced, both, par, letterbox, hex(got or 0), hex(want), quads))


# ---------------------------------------------------------------------------------------
# new character: player_initNewCharacter, then the Player_ctor recalc, then the HUD
# ---------------------------------------------------------------------------------------
def class_formulas(emu):
    import ref_combat as R

    class Exe:
        def u32(self, a):
            return emu.mem.u32(a)
    return [R.read_class_formula(Exe(), c) for c in range(7)]


def new_character(elf, rng, model, slot, items, stats, kind, players, t, prop, formulas, hud_check):
    emu = EE(elf)
    emu.mem.w32(0x4D8AE0, players)
    emu.mem.w32(X.G_PVP_A, 0)
    name = emu.alloc(32)
    emu.mem.write(name, b'SYNTH\0')
    sp = 0x01FFF000
    emu.mem.w32(sp, kind & 0xFFFFFFFF)
    emu.mem.w32(sp + 8, 0xFFFFFFFF)
    ptr = 0
    if stats is not None:
        ptr = emu.alloc(16)
        emu.mem.write(ptr, bytes(v & 0xFF for v in stats))
    if not items:
        emu.stub(0x1ACC78)
    appearance = [rng.randint(-1, 3) for _ in range(4)]
    _v, seeds = run(emu, 0x1B1D70, slot, model, name, *[a & 0xFFFFFFFF for a in appearance], ptr,
                    sp=sp, max_steps=20000000)
    t.seeds(prop + ' (init)', seeds)
    t.check(prop + ': init draws no seed', not any(seeds.values()), seeds)
    p = G_PLAYERS + slot * REC
    m = emu.mem
    got = {'hp': m.u32(p + 0xAC), 'hp_max': m.u32(p + 0xB0), 'mana': m.u32(p + 0xC0),
           'mana_max': m.u32(p + 0xC4), 'object': m.u32(p + 0x43D8)}
    t.check(prop + ': after init', got == X.after_init(), lambda: (model, slot, got))
    t.check(prop + ': levels and xp', (m.s8(p + 0x58), m.s8(p + 0x59), m.s32(p + 0x5C)) == (1, 1, 0))
    cls = m.s32(p + 0x50)
    base = [m.s32(p + 0x78 + 4 * i) for i in range(4)]
    if stats is not None:
        t.check(prop + ': stats from the four bytes', base == [X.s8(v) for v in stats], (base, stats))
    # Player_ctor stores the object (0x1a221c) and then calls player_recalcStats (0x1a2458).
    obj = emu.alloc(0x600)
    m.w32(p + 0x43D8, obj)
    m.w32(obj + 0x3C8, slot)
    emu.stub(0x308A7C, function=lambda e: e.f.__setitem__(0, 0))   # resistance statistic only
    _v, seeds = run(emu, 0x1B6458)
    t.seeds(prop + ' (recalc)', seeds)
    eff = [m.s32(p + 0x90 + 4 * i) for i in range(4)]
    hp, hp_max, mana, mana_max = (m.u32(p + o) for o in (0xAC, 0xB0, 0xC0, 0xC4))
    if X.recalc_clamps(slot, players, True):
        want = X.first_level_current(formulas[cls], 1, eff)
        ok = (hp, hp_max, mana, mana_max) == want and hp == hp_max and mana == mana_max
        t.check(prop + ': first recalc gives current = max', ok,
                lambda: (model, cls, [F.to_float(v) for v in (hp, hp_max, mana, mana_max)]))
        if items:
            t.check(prop + ': starting items leave eff = base', eff == base, (model, eff, base))
        if items and stats is None:
            t.results.append((model, cls, F.to_float(hp), F.to_float(mana)))
    else:
        t.check(prop + ': no clamp when slot >= g_numPlayers', (hp, mana) == (X.INIT_CURRENT, X.INIT_CURRENT))
        return
    if not hud_check:
        return
    hud = Hud(emu)
    emu.mem.w8(NET_BYTE, 0)
    emu.mem.w32(X.SIM_TICK, 0)
    m.w32(obj + 0x540, 0)
    m.w32(obj + 0x0C, 0)
    m.w16(obj + 0x4AE, 0)
    draws, seeds = hud.call(slot)
    t.seeds(prop + ' (hud)', seeds)
    x = L.HUD_X[slot]
    S = x + X.X_INSET
    lower, upper = table_words(emu, 1)
    rights = {d.resource[:-6]: d.clip[2] for d in draws if d.resource.startswith('bar_')}
    want = {'bar_red': X.resource_bar_right(S, hp, hp_max), 'bar_blue': X.resource_bar_right(S, mana, mana_max),
            'bar_green': X.xp_layer(x, 0, 1, 0, lower, upper).clip[2]}
    t.check(prop + ': first HUD frame', rights == want and want['bar_red'] == S + 99 and want['bar_blue'] == S + 99
            and want['bar_green'] == S, lambda: (rights, want))


def prop_new_character(elf, seed, t):
    prop = 'new-character'
    rng = random.Random('%d/%s' % (seed, prop))
    formulas = class_formulas(EE(elf))
    t.results = []
    for model in range(12):                      # every model, real starting items
        new_character(elf, rng, model, rng.randrange(4), True, None, -1, 4, t, prop, formulas, True)
    for _ in range(24):
        model = rng.randrange(12)
        items = rng.random() < 0.3
        # With real starting items a negative statistic (strength or stamina -20 tried)
        # reaches a SYSCALL at 0x352e14 that ee_emu does not model; not traced further.
        low = 15 if items else -20
        stats = [rng.randint(low, 120) for _ in range(4)] if rng.random() < 0.5 else None
        players = rng.randint(1, 4)
        new_character(elf, rng, model, rng.randrange(4), items, stats, rng.choice((-1, 1, 2)),
                      players, t, prop, formulas, rng.random() < 0.3)


def prop_respawn(elf, seed, t):
    prop = 'respawn'
    rng = random.Random('%d/%s' % (seed, prop))
    emu = EE(elf)
    emu.follow = set()                           # Player_ctor, net and camera callees stubbed
    pos = emu.alloc(16)
    for _ in range(60):
        slot = rng.randrange(4)
        p = G_PLAYERS + slot * REC
        hp_max = F.f32(rng.uniform(1.0, 900.0))
        hp, mana = F.f32(rng.uniform(-50.0, 900.0)), F.f32(rng.uniform(0.0, 900.0))
        pvp = rng.choice((0, 0, 1))
        emu.mem.w32(p + 0x43D8, 0)
        emu.mem.w32(p + 0xB0, hp_max)
        emu.mem.w32(p + 0xAC, hp)
        emu.mem.w32(p + 0xC0, mana)
        emu.mem.w32(X.G_PVP_A, pvp)
        _v, seeds = run(emu, 0x1BD040, slot, pos, 0, 0xFFFFFFFF, 0)
        t.seeds(prop, seeds)
        got = (emu.mem.u32(p + 0xAC), emu.mem.u32(p + 0xC0), emu.mem.u32(p + 0xB0))
        t.check(prop, got == (X.respawn_hp(hp_max, pvp), mana, hp_max), lambda: (slot, pvp, got))


PROPS = (('xp-draw', prop_xp_draw), ('xp-edges', prop_xp_edges), ('bar-green-drawer', prop_drawer),
         ('new-character', prop_new_character), ('respawn', prop_respawn))


def main(argv):
    seed, filt, pos = 20973, None, []
    it = iter(argv)
    for a in it:
        if a == '--seed':
            seed = int(next(it))
        elif a == '-k':
            filt = next(it)
        elif a != '-v':
            pos.append(a)
    path = elf_path(pos)
    if path is None or not os.path.isfile(path):
        print('difftest_hud_xp: no ELF, skipped')
        return 0
    t = Tally()
    t.results = []
    for name, fn in PROPS:
        if filt and filt not in name:
            continue
        fn(path, seed, t)
    print('difftest_hud_xp seed %d (%s)' % (seed, path))
    for prop in sorted(t.cases):
        print('  %-58s %5d cases' % (prop, t.cases[prop]))
    for prop in sorted(t.draws):
        print('  seed draws %-40s %s' % (prop, ' '.join('%s=%d' % kv for kv in t.draws[prop].items())))
    seen = sorted(set((m, c, round(h, 4), round(n, 4)) for m, c, h, n in t.results))
    for m, c, h, n in seen[:12]:
        print('  first level: model %2d class %d hp %.4f mana %.4f (current = max)' % (m, c, h, n))
    if t.fails:
        print('FAIL %d' % len(t.fails))
        for f in t.fails:
            print('  ' + f)
        return 1
    print('ok')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
