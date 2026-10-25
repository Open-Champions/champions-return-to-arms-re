#!/usr/bin/env python3
"""hud_drawPlayerStatus 0x1d9cd4 against tools/ref_hud_status.py.

Runs the original function in tools/ee_emu.py on constructed state. The flat
rectangle drawer ui_drawRect 0x17bd30 and math_sin16 0x1666e0 run as original
code; the clipped sprite 0x17fb88, lump/texture lookups, sprintf and the text,
notice and selector callees are stubs that record their arguments. Every
0x17fb88 and 0x17bd30 call (all register arguments and the stack arguments) is
compared with the reference in call order, with the texture lookups, the hit
flash word, the glow alpha, the GS corners of each rectangle packet and the
draws of the three random generators.

  python3 tools/difftest_hud_status.py [SLUS_209.73] [--seed N] [-k TEXT] [--vectors FILE]

Exits 0 with a message when the ELF is not found (argv, CHAMPIONS_ELF,
./SLUS_209.73, local/SLUS_209.73). Does not import unittest.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ref_core as F
import ref_hud_status as R
import ref_ui_layout as L
from ee_emu import EE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M32 = 0xFFFFFFFF
SEEDS = {'cosmetic': 0x404460, 'shared': 0x404464, 'third': 0x404468}
G_CAMERA, G_SIM_TICK, G_NUM_PLAYERS, G_NETWORK = 0x4F8450, 0x44FDCC, 0x4D8AE0, 0x402791
G_DL_CAP, G_DL_BASE, G_DL_CURSOR, G_INTERLACE = 0x44FDA4, 0x44FE0C, 0x44FE10, 0x44FDD4
G_MENU, G_HUD_OFF, G_SHOP = 0x41B4F8, 0x4F66A8, 0x41B50C
G_TIMERS, G_GLOW, G_ICON_LOADED = 0x41B828, 0x86AA50, 0x4F66F4
XP_TABLE = 0x41B554
HUD_X_TABLE = 0x53C408


def elf_path(args):
    if args:
        return args[0]
    env = os.environ.get('CHAMPIONS_ELF')
    if env:
        return env
    for cand in (os.path.join(os.getcwd(), 'SLUS_209.73'), os.path.join(ROOT, 'local', 'SLUS_209.73')):
        if os.path.isfile(cand):
            return cand
    return None


def s32(v):
    v &= M32
    return v - 0x100000000 if v & 0x80000000 else v


class Rig:
    def __init__(self, path):
        e = self.e = EE(path)
        e.follow = {0x1666E0, 0x17BD30}
        e.default_ret = 0
        self.records, self.names = {}, {}
        self.calls, self.lookups, self.packets = [], [], []
        self.local_slots, self.active = set(), True
        self.lump = e.alloc(16)
        e.stub(0x173558, ret=self.lump)
        e.stub(0x171DE4, function=self._lookup)
        e.stub(0x17365C, function=self._lookup_tex)
        e.stub(0x3B7EF0, function=self._sprintf)
        e.stub(0x17FB88, function=self._sprite)
        e.stub(0x13DD40, function=lambda em: int(self.active))
        e.stub(0x13E150, function=lambda em: int(s32(em.r[4]) in self.local_slots))
        e.stub(0x16B7F0, function=self._packet)
        e.hook(0x17BD30, self._rect)
        self.cam = e.alloc(0x100)
        e.mem.w32(G_CAMERA, self.cam)
        self.dl = e.alloc(0x4000)
        e.mem.w32(G_ICON_LOADED, 1)
        self.objs = [e.alloc(0x600) for _ in range(4)]

    def tex(self, name):
        if name not in self.names:
            a = self.e.alloc(64)
            self.names[name], self.names[a] = a, name
        return self.names[name]

    def _lookup(self, e):
        name = e.mem.cstr(e.r[5] & M32)
        if isinstance(name, bytes):
            name = name.decode('latin-1')
        self.lookups.append(name)
        if name not in self.records:
            r = e.alloc(16)
            e.mem.w32(r + 4, self.tex(name))
            self.records[name] = r
        return self.records[name]

    def _lookup_tex(self, e):
        name = e.mem.cstr(e.r[5] & M32)
        if isinstance(name, bytes):
            name = name.decode('latin-1')
        self.lookups.append(name)
        return self.tex(name)

    def _sprintf(self, e):
        fmt = e.mem.cstr(e.r[5] & M32)
        if isinstance(fmt, bytes):
            fmt = fmt.decode('latin-1')
        args, reg, i = [], 6, 0
        while i < len(fmt):
            if fmt[i] == '%':
                j = i + 1
                while fmt[j] in '0123456789-': j += 1
                if fmt[j] == 's':
                    a = e.mem.cstr(e.r[reg] & M32)
                    args.append(a.decode('latin-1') if isinstance(a, bytes) else a)
                    reg += 1
                elif fmt[j] != '%':
                    args.append(s32(e.r[reg]))
                    reg += 1
                i = j
            i += 1
        out = (fmt % tuple(args)).encode('latin-1')
        e.mem.write(e.r[4] & M32, out + b'\0')
        return len(out)

    def _sprite(self, e):
        sp = e.r[29] & M32
        tex = e.r[4] & M32
        self.calls.append(R.ClipSprite(self.names.get(tex, hex(tex)), s32(e.r[5]), s32(e.r[6]),
                                       s32(e.r[7]), e.r[8] & M32, s32(e.r[9]), s32(e.r[10]),
                                       s32(e.r[11]), s32(e.mem.u32(sp)), s32(e.mem.u32(sp + 8)),
                                       s32(e.mem.u32(sp + 16))))

    def _rect(self, e):
        self.calls.append(R.Rect(s32(e.r[4]), s32(e.r[5]), s32(e.r[6]), s32(e.r[7]),
                                 s32(e.r[8]), e.r[9] & M32))

    def _packet(self, e):
        p = e.r[4] & M32
        self.packets.append((p, s32(e.r[5]), e.mem.u64(p + 0x60), e.mem.u64(p + 0x70),
                             e.mem.u32(p + 0x20)))

    def setup(self, st, network=False, players=4, interlaced=1, free_units=35000, gates=None):
        e, m = self.e, self.e.mem
        g = dict(menu=0, hud=0, shop=0, camera=1, active=True, obj=True, vehicle=0)
        g.update(gates or {})
        m.w32(G_MENU, g['menu']); m.w8(G_HUD_OFF, g['hud']); m.w32(G_SHOP, g['shop'])
        m.w32(self.cam + 0x34, g['camera'])
        self.active = g['active']
        m.w32(G_SIM_TICK, st.tick & M32)
        m.w32(G_NUM_PLAYERS, players)
        m.w8(G_NETWORK, 1 if network else 0)
        m.w8(G_INTERLACE, interlaced)
        used = 64
        m.w32(G_DL_BASE, self.dl)
        m.w32(G_DL_CURSOR, self.dl + used * 8)
        m.w32(G_DL_CAP, free_units + used)
        rec = R.PLAYER_BASE + st.slot * R.PLAYER_SIZE
        obj = self.objs[st.slot]
        m.w32(rec + 0x43D8, obj if g['obj'] else 0)
        m.write(rec, b'SYNTH\0')
        for off, v in ((0xAC, st.health), (0xB0, st.health_max), (0xB4, st.health_pending),
                       (0xC0, st.mana), (0xC4, st.mana_max), (0xC8, st.mana_pending)):
            m.w32(rec + off, v)
        m.w8(rec + 0x58, st.ack_level); m.w8(rec + 0x59, st.level); m.w32(rec + 0x5C, st.exp & M32)
        ack = R._s8(st.ack_level)
        if ack > 0:
            m.w32(XP_TABLE + 4 * ack, st.exp_base & M32)
            m.w32(XP_TABLE + 4 * ack + 4, st.exp_next & M32)
        m.w32(obj + 0xC, st.obj_flags); m.w16(obj + 0x4AE, st.cooldown); m.w32(obj + 0x540, g['vehicle'])
        m.w32(R.FLASH_TABLE + 4 * st.slot, st.flash)
        m.w32(G_GLOW + 4 * st.slot, st.glow_alpha & M32)
        for i in range(8):
            m.w32(G_TIMERS + 4 * (st.slot * 8 + i), 0)
        return rec, obj

    def run(self, slot, rng):
        e = self.e
        seeds = {k: rng.getrandbits(32) for k in SEEDS}
        for k, a in SEEDS.items():
            e.mem.w32(a, seeds[k])
        self.calls, self.lookups, self.packets = [], [], []
        e.reset_log()
        e.call(0x1D9CD4, slot)
        draws = {}
        for k, a in SEEDS.items():
            draws[k] = sum(1 for _pc, addr, size, _v in e.writes if addr == a)
        return draws


class Stats:
    def __init__(self):
        self.cases = self.rects = self.sprites = self.packets = 0
        self.health_rects = self.mana_rects = 0
        self.inverted = self.empty = self.nonpositive = 0
        self.draws = {'shared': 0, 'cosmetic': 0, 'third': 0}
        self.fail = []


def compare(rig, st, stats, label, interlaced=1, free_units=35000):
    want, lookups, flash, glow = R.status_draws(st)
    got = rig.calls
    if got != want:
        stats.fail.append('%s: draws\n  got  %s\n  want %s\n  state %s' % (label, got, want, st))
        return
    if rig.lookups != lookups:
        stats.fail.append('%s: lookups got %s want %s' % (label, rig.lookups, lookups))
        return
    m = rig.e.mem
    if m.u32(R.FLASH_TABLE + 4 * st.slot) != flash:
        stats.fail.append('%s: flash' % label)
    if s32(m.u32(G_GLOW + 4 * st.slot)) != glow:
        stats.fail.append('%s: glow %d want %d' % (label, s32(m.u32(G_GLOW + 4 * st.slot)), glow))
    rects = [d for d in want if isinstance(d, R.Rect)]
    emitted = R.rect_packets(free_units, len(rects))
    if len(rig.packets) != emitted:
        stats.fail.append('%s: %d packets, want %d of %d rects' % (label, len(rig.packets), emitted, len(rects)))
        return
    for rect, (_p, layer, xyz0, xyz1, rgba) in zip(rects, rig.packets):
        if layer != rect.layer or rgba != rect.colour or (xyz0, xyz1) != R.rect_xyz2(rect, interlaced):
            stats.fail.append('%s: packet %s %x %x vs %s' % (label, rect, xyz0, xyz1,
                              ['%x' % w for w in R.rect_xyz2(rect, interlaced)]))
        stats.packets += 1
    stats.short_packets = getattr(stats, 'short_packets', 0) + len(rects) - emitted
    stats.inverted += sum(1 for r in rects if r.x1 < r.x0)
    stats.empty += sum(1 for r in rects if r.x1 == r.x0)
    if not F.lt(F.ZERO, st.health):
        stats.nonpositive += sum(1 for r in rects if r.colour == R.HEALTH_RECT[2])
    stats.cases += 1
    stats.rects += len(rects)
    stats.health_rects += sum(1 for r in rects if r.colour == R.HEALTH_RECT[2])
    stats.mana_rects += sum(1 for r in rects if r.colour == R.MANA_RECT[2])
    stats.sprites += len(want) - len(rects)


def base_layers(rig, st, stats):
    """Cross-check with ref_ui_layout.hud_base_layers inside its supported domain
    (tick >= 0, current >= 0, maximum > 0); glow and rectangles removed."""
    t = F.to_float
    ack = R._s8(st.ack_level)
    if st.tick < 0 or t(st.health) < 0 or t(st.health_max) <= 0 or t(st.mana) < 0 or \
            t(st.mana_max) <= 0 or st.exp < st.exp_base or st.exp_next <= st.exp_base:
        return
    try:
        want = L.hud_base_layers(st.x, st.tick, t(st.health), t(st.health_max), t(st.mana),
                                 t(st.mana_max), st.exp, st.exp_base, st.exp_next, ack,
                                 bool(st.local), R._s16(st.cooldown), bool(st.flash & 1))
    except ValueError:
        return
    got = [L.HudLayer(d.resource, d.x, d.y, (d.left, d.top, d.right, d.bottom), d.tint, d.layer)
           for d in rig.calls if isinstance(d, R.ClipSprite) and 'glow' not in d.resource]
    if got != want:
        stats.fail.append('hud_base_layers differs: %s vs %s' % (got, want))
    stats.base_layers = getattr(stats, 'base_layers', 0) + 1


def check_draws(stats, draws, label):
    want = R.seed_draws()
    for k in draws:
        stats.draws[k] += draws[k]
    if draws != want:
        stats.fail.append('%s: seed draws %s want %s' % (label, draws, want))


# ---- properties ---------------------------------------------------------------------
def prop_offline(rig, rng, n, stats, vectors):
    """Offline: every slot local, origin HUD_X[slot]; random C/M/pending/flags."""
    for i in range(n):
        st = R.random_state(rng, local=True)
        interlaced = rng.choice([0, 1])
        rig.setup(st, network=False, players=4, interlaced=interlaced)
        draws = rig.run(st.slot, rng)
        compare(rig, st, stats, 'offline %d' % i, interlaced)
        base_layers(rig, st, stats)
        check_draws(stats, draws, 'offline %d' % i)
        if vectors is not None and not stats.fail:
            vectors.append(R.vector_row(st))


def prop_network(rig, rng, n, stats, vectors):
    """Net game: random player count and local set; origin from hud_origins
    (promotion), local flag from net_isLocalSlot; cap stays by raw slot."""
    for i in range(n):
        players = rng.randrange(1, 5)
        local_slots = set(s for s in range(players) if rng.random() < 0.4)
        slot = rng.randrange(players)
        xs = R.hud_origins(True, local_slots, players)
        st = R.random_state(rng, slot=slot, x=xs[slot], local=R.local_flag(True, slot in local_slots))
        rig.local_slots = local_slots
        rig.setup(st, network=True, players=players)
        draws = rig.run(slot, rng)
        compare(rig, st, stats, 'network %d' % i)
        check_draws(stats, draws, 'network %d' % i)
        if vectors is not None and not stats.fail:
            vectors.append(R.vector_row(st))
    rig.local_slots = set()


def prop_edges(rig, rng, n, stats, vectors):
    """Hand-picked edges: C = 0, pending past M, fractional M, C > M, health <= 0
    with and without the dead bit, saturating sums."""
    f = F.f32
    edges = []
    for slot in range(4):
        for h, hm, hp in ((0.0, 100.0, 10.0), (50.0, 100.0, 80.0), (1.0, 3.0, 1.5),
                          (120.0, 100.0, 5.0), (-5.0, 100.0, 20.0), (0.0, 0.5, 0.25),
                          (99.9, 100.0, 0.05), (5.7, 10.0, 0.2), (1.0, 1e-30, 1.0),
                          (3e9, 4e9, 3e9), (10.0, 100.0, -1.0), (10.0, 100.0, 0.0)):
            for flags in (0, R.DEAD_FLAG):
                edges.append((slot, h, hm, hp, flags))
    for i, (slot, h, hm, hp, flags) in enumerate(edges):
        base = R.random_state(rng, slot=slot, local=True)
        st = base._replace(obj_flags=flags, health=f(h), health_max=f(hm), health_pending=f(hp),
                           mana=f(h), mana_max=f(hm), mana_pending=f(hp))
        rig.setup(st)
        draws = rig.run(slot, rng)
        compare(rig, st, stats, 'edge %d' % i)
        check_draws(stats, draws, 'edge %d' % i)
        if vectors is not None and not stats.fail:
            vectors.append(R.vector_row(st))


def prop_caps(rig, rng, n, stats, vectors):
    """Origin table 0x53c408 overwritten with arbitrary X so that S + b can pass
    the cap of the raw slot (with the shipped table and the promotion rule it
    never does; see the spec)."""
    table = [rig.e.mem.u32(HUD_X_TABLE + 4 * k) for k in range(4)]
    f = F.f32
    for i in range(n):
        xs = [rng.randrange(-40, 700) for _ in range(4)]
        for k in range(4):
            rig.e.mem.w32(HUD_X_TABLE + 4 * k, xs[k] & M32)
        slot = rng.randrange(4)
        hm = rng.choice([100.0, 37.5, 1000.0])
        h = hm * rng.uniform(0.0, 1.0)
        st = R.random_state(rng, slot=slot, x=xs[slot], local=True)._replace(
            obj_flags=0, health=f(h), health_max=f(hm), health_pending=f(hm),
            mana=f(h), mana_max=f(hm), mana_pending=f(rng.uniform(0.1, hm)))
        rig.setup(st)
        draws = rig.run(slot, rng)
        compare(rig, st, stats, 'caps %d' % i)
        check_draws(stats, draws, 'caps %d' % i)
        stats.capped = getattr(stats, 'capped', 0) + sum(
            1 for d in rig.calls if isinstance(d, R.Rect) and d.x1 == R.pending_cap(slot))
        if vectors is not None and not stats.fail:
            vectors.append(R.vector_row(st))
    for k in range(4):
        rig.e.mem.w32(HUD_X_TABLE + 4 * k, table[k])
    stats.extra = '%d rects ended at the cap' % stats.capped


def prop_gates(rig, rng, n, stats, vectors):
    """Each early gate alone suppresses every draw and leaves the flash bit."""
    gates = [('menu', 1), ('hud', 1), ('hud', 0x80), ('shop', 1), ('camera', 0), ('camera', 2),
             ('active', False), ('obj', False), ('vehicle', 1), ('free', 2999), ('free', 3000),
             ('free', 3008), ('free', 3015), ('free', 3016), ('free', 3017), ('none', 0)]
    for i in range(n):
        name, value = gates[i % len(gates)]
        st = R.random_state(rng, local=True)._replace(flash=1, obj_flags=0, health_pending=F.f32(5.0),
                                                     mana_pending=F.f32(5.0))
        free = value if name == 'free' else 35000
        kw = {} if name in ('free', 'none') else {name: value}
        rig.setup(st, free_units=free, gates=kw)
        draws = rig.run(st.slot, rng)
        g = dict(menu_open=0, hud_suppressed=0, shop_open=0, camera_mode=1, slot_active=True,
                 has_object=True, vehicle=0, free_units=free)
        key = {'menu': 'menu_open', 'hud': 'hud_suppressed', 'shop': 'shop_open',
               'camera': 'camera_mode', 'active': 'slot_active', 'obj': 'has_object',
               'vehicle': 'vehicle'}.get(name)
        if key:
            g[key] = value
        if R.visible(**g):
            compare(rig, st, stats, 'gate %s %d' % (name, i), free_units=free)
        else:
            if rig.calls or rig.lookups or rig.e.mem.u32(R.FLASH_TABLE + 4 * st.slot) != 1:
                stats.fail.append('gate %s: drew %s' % (name, rig.calls))
            stats.cases += 1
        check_draws(stats, draws, 'gate %d' % i)


def prop_fields(rig, rng, n, stats, vectors):
    """Which record and object offsets the function reads (reported)."""
    rig.e.reads = []
    seen_rec, seen_obj = set(), set()
    for i in range(n):
        st = R.random_state(rng, local=True)._replace(obj_flags=0, health=F.f32(5.0),
                                                     health_pending=F.f32(2.0),
                                                     mana_pending=F.f32(1.0), ack_level=1,
                                                     level=2)
        rec, obj = rig.setup(st)
        rig.e.reads = []
        draws = rig.run(st.slot, rng)
        compare(rig, st, stats, 'fields %d' % i)
        check_draws(stats, draws, 'fields %d' % i)
        for _pc, addr, size, _v in rig.e.reads:
            if rec <= addr < rec + R.PLAYER_SIZE:
                seen_rec.add((addr - rec, size))
            if obj <= addr < obj + 0x600:
                seen_obj.add((addr - obj, size))
    rig.e.reads = None
    stats.extra = 'record reads %s; object reads %s' % (
        ' '.join('+0x%x/%d' % k for k in sorted(seen_rec)),
        ' '.join('+0x%x/%d' % k for k in sorted(seen_obj)))


PROPERTIES = [('offline', prop_offline, 1500), ('network', prop_network, 800),
              ('edges', prop_edges, 0), ('caps', prop_caps, 300), ('gates', prop_gates, 170), ('fields', prop_fields, 8)]


def main(argv):
    args = list(argv[1:])
    seed, filt, vec_path, rest = 20973, None, None, []
    while args:
        a = args.pop(0)
        if a == '--seed':
            seed = int(args.pop(0))
        elif a == '-k':
            filt = args.pop(0)
        elif a == '--vectors':
            vec_path = args.pop(0)
        elif a in ('-h', '--help'):
            print(__doc__)
            return 0
        else:
            rest.append(a)
    path = elf_path(rest)
    if not path or not os.path.isfile(path):
        print('difftest_hud_status: no SLUS_209.73; skipped')
        return 0
    rig = Rig(path)
    vectors = [] if vec_path else None
    failed = False
    print('difftest_hud_status seed %d (%s)' % (seed, path))
    for name, function, n in PROPERTIES:
        if filt and filt not in name:
            continue
        rng = random.Random('%d/%s' % (seed, name))
        stats = Stats()
        function(rig, rng, n, stats, vectors)
        status = 'ok' if not stats.fail else 'FAIL'
        print('  %-8s %s: %d cases, %d sprites, %d pending rects (%d health, %d mana), '
              '%d rect packets checked; seed draws shared %d cosmetic %d third %d' % (
                  name, status, stats.cases, stats.sprites, stats.rects, stats.health_rects,
                  stats.mana_rects, stats.packets, stats.draws['shared'],
                  stats.draws['cosmetic'], stats.draws['third']))
        if stats.rects:
            print('           rects with right < left %d, right == left %d; health rects drawn with '
                  'health <= 0: %d' % (stats.inverted, stats.empty, stats.nonpositive))
        if getattr(stats, 'base_layers', 0):
            print('           %d cases also equal ref_ui_layout.hud_base_layers' % stats.base_layers)
        if getattr(stats, 'short_packets', 0):
            print('           %d rect calls made no packet (inner 3000-unit gate)' % stats.short_packets)
        if getattr(stats, 'extra', None):
            print('           ' + stats.extra)
        for msg in stats.fail[:3]:
            print('    ' + msg)
        failed = failed or bool(stats.fail)
    if vectors is not None:
        with open(vec_path, 'w') as out:
            out.write('# ' + '\t'.join(R.VECTOR_COLUMNS) + '\t| per draw: ' +
                      '\t'.join(R.DRAW_COLUMNS) + '\n')
            out.write('\n'.join(vectors) + '\n')
        print('  wrote %d vector rows to %s' % (len(vectors), vec_path))
    print('difftest_hud_status: %s' % ('FAIL' if failed else 'ok'))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
