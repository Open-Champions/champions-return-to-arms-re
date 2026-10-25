#!/usr/bin/env python3
"""The automap drawer 0x168cac and its helpers against the original SLUS-20973 v2.00 code.

Runs the original instructions in tools/ee_emu.py on constructed state and compares
with tools/ref_hud_minimap.py: every display-list byte written, the end cursor, the
calls (callback, vars_get, script_runByName, memcpy, gfx_addSortedPacket), the profiling
counters, stray stores and draws on the three random generators. Exits 0 when the ELF is
missing. Does not import unittest (tools/dis.py would shadow the stdlib name).

  python3 tools/difftest_hud_minimap.py [SLUS_209.73] [--seed N] [-k TEXT]
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ref_core as F
import ref_hud_dynamic as H
import ref_hud_minimap as R
from ee_emu import EE

FUNC, GATE, CELL = 0x168CAC, 0x16A838, 0x16A7DC
CALLBACK = 0x1E40A8
VARS_GET, SCRIPT_RUN, MEMCPY, ADD_PACKET = 0x1ED778, 0x1ED694, 0x3B5F0C, 0x16B7F0
SEEDS = {'shared': 0x404464, 'cosmetic': 0x404460, 'third': 0x404468}
DL_CURSOR, DL_BASE, DL_CAP = 0x44FE10, 0x44FE0C, 0x44FDA4
ICONS, ICON_COUNT = 0x6E0F90, 0x6E14D0
OBJ_LIST_PTR = 0x4F867C
FILL = 0xCD
DRAWS = {'shared': 0, 'cosmetic': 0, 'third': 0}


def elf_path(argv):
    rest = [a for a in argv[1:] if not a.startswith('-')]
    skip = set()
    for i, a in enumerate(argv):
        if a in ('--seed', '-k') and i + 1 < len(argv):
            skip.add(argv[i + 1])
    rest = [a for a in rest if a not in skip]
    if rest:
        return rest[0]
    env = os.environ.get('CHAMPIONS_ELF')
    if env:
        return env
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for cand in (os.path.join(os.getcwd(), 'SLUS_209.73'), os.path.join(here, 'SLUS_209.73'),
                 os.path.join(here, 'local', 'SLUS_209.73')):
        if os.path.isfile(cand):
            return cand
    return None


class Fail(Exception):
    pass


def check(name, got, want):
    if got != want:
        raise Fail('%s: got %r want %r' % (name, got, want))


def fpat(rng, lo, hi):
    return F.f32(rng.uniform(lo, hi))


def seed_draws(emu):
    return {k: sum(1 for _pc, a, size, _v in emu.writes if a == addr and size == 4)
            for k, addr in SEEDS.items()}


# ---- small helpers -------------------------------------------------------------------
def prop_libm(emu, rng):
    n = 0
    for _ in range(300):
        x = rng.choice([fpat(rng, -300, 300), F.f32(float(rng.randint(-50, 300))),
                        fpat(rng, -2, 2), 0x80000000, 0])
        for addr, want in ((0x3A53C0, R.r5900_floor(x)), (0x3A51B0, R.r5900_ceil(x))):
            emu.f[12] = x
            d = emu.call(0x3AEF58)
            d = emu.call(addr, d)
            got = F.s32(emu.call(0x3AFAC0, d))
            check('libm %x(%08x)' % (addr, x), got, want)
            n += 1
    return n


def prop_gate(emu, rng):
    n = 0
    for _ in range(300):
        tex = rng.choice([0, 0x1234560])
        base = 0x1000000
        cur = base + 8 * rng.randint(0, 40000)
        cap = rng.randint(0, 60000)
        hw = rng.choice([0, F.f32(1.99), F.f32(2.0), fpat(rng, -10, 400)])
        world = emu.alloc(0x80)
        emu.mem.w32(world + 0x6C, tex)
        emu.mem.w32(DL_CURSOR, cur)
        emu.mem.w32(DL_BASE, base)
        emu.mem.w32(DL_CAP, cap)
        emu.f[12] = hw
        got = emu.call(GATE, world) & 0xFFFFFFFF
        check('gate', got, R.gate(tex, cur, base, cap, hw))
        n += 1
    return n


def prop_cell(emu, rng):
    out = emu.alloc(16)
    pos = emu.alloc(16)
    n = 0
    for _ in range(300):
        origin = (fpat(rng, -50, 200), fpat(rng, -50, 200))
        x, y = fpat(rng, -30000, 30000), fpat(rng, -30000, 30000)
        emu.mem.w32(0x4044A8, origin[0])
        emu.mem.w32(0x4044AC, origin[1])
        emu.mem.w32(pos, x)
        emu.mem.w32(pos + 4, y)
        emu.call(CELL, pos, out, out + 4)
        got = (emu.mem.u32(out), emu.mem.u32(out + 4))
        check('cell', got, R.world_to_cell(x, y, origin))
        n += 1
    return n


# ---- the drawer ------------------------------------------------------------------------
MODES = (  # (scale, offx, offy, half_w, half_h, icon size f18, blip size f17), minimap_params
    (0x3F666666, 0, 0, 0x43A00000, 0x43600000, 0x41800000, 0x40C00000),
    (0x3F333333, 0x43480000, 0xC2F00000, 0x42F00000, 0x42C80000, 0x41200000, 0x40A00000),
    (0x3F333333, 0xC3700000, 0x430C0000, 0x42F00000, 0x42C80000, 0x41200000, 0x40A00000),
)


def make_state(emu, rng, world, centre, dl, cb_blips=None):
    scale, offx, offy, hw, hh, isz, bsz = rng.choice(MODES)
    if rng.random() < 0.3:
        offx, offy = fpat(rng, -250, 250), fpat(rng, -150, 150)
        hw, hh = fpat(rng, 1, 330), fpat(rng, 1, 230)
    stick = rng.choice([0x3F000000, 0x3F800000, 0x40000000, fpat(rng, 0.5, 2.0)])
    zoom = F.mul(scale, stick)
    if rng.random() < 0.1:
        zoom = fpat(rng, 0.05, 0.2)
    w, h = rng.randint(4, 216), rng.randint(4, 216)
    origin = (fpat(rng, 0, 40), fpat(rng, 0, 40))
    ccol, crow = rng.uniform(-8, w + 8), rng.uniform(-8, h + 8)
    cx = F.f32((ccol - F.to_float(origin[0])) * 120.0)
    cy = F.f32((crow - F.to_float(origin[1])) * 120.0)
    s = {'world_tex': 0x2345670, 'dl_cursor': dl, 'dl_base': dl, 'dl_capacity': 0x40000,
         'yaw': rng.randint(-0x8000, 0x7FFF), 'centre': (cx, cy), 'offx': offx, 'offy': offy,
         'zoom': zoom, 'half_w': hw, 'half_h': hh, 'blip_size': bsz, 'icon_size': isz,
         'origin': origin, 'width': w, 'height': h,
         'full_scissor': (rng.randint(0, 447), rng.randint(0, 447)),
         'zbuf': rng.getrandbits(64), 'timer': (rng.getrandbits(16), rng.getrandbits(16) + 70000),
         'counters': (rng.getrandbits(20), rng.getrandbits(8))}
    if rng.random() < 0.08:
        s['world_tex'] = 0

    def near():
        return (F.f32((ccol + rng.uniform(-60, 60) - F.to_float(origin[0])) * 120.0),
                F.f32((crow + rng.uniform(-60, 60) - F.to_float(origin[1])) * 120.0))
    blips = []
    if cb_blips is None:
        for _ in range(rng.randint(0, 6)):
            if rng.random() < 0.25:
                blips.append(None)
                continue
            x, y = near()
            blips.append({'x': x, 'y': y, 'angle': rng.getrandbits(16),
                          'r': rng.getrandbits(8), 'g': rng.getrandbits(8),
                          'b': rng.getrandbits(8), 'scale': rng.choice([F.ONE, F.HALF])})
    s['blips'] = blips
    icons = []
    for _ in range(rng.randint(0, 4)):
        x, y = near()
        icons.append({'x': x, 'y': y, 'tex': rng.choice([0, 0x2400000]),
                      'tex_w': rng.choice([16, 32, 64]), 'tex_h': rng.choice([16, 32]),
                      'rotate': rng.choice([0, 1]),
                      'var': rng.choice([0, 0x533000]), 'var_ok': rng.choice([0, 1, 1]),
                      'script': rng.choice([0, 0x533100]), 'script_ok': rng.choice([0, 1, 1])})
    s['icons'] = icons
    s['grid'] = bytes(rng.getrandbits(8) for _ in range(216 * 216 * 2))
    return s


def install(emu, s, world, centre, dl):
    emu.mem.write(dl, bytes([FILL]) * 0x40000)
    emu.mem.w32(world + 0x6C, s['world_tex'])
    emu.mem.w32(centre, s['centre'][0])
    emu.mem.w32(centre + 4, s['centre'][1])
    emu.mem.w32(DL_CURSOR, dl)
    emu.mem.w32(DL_BASE, s['dl_base'])
    emu.mem.w32(DL_CAP, s['dl_capacity'])
    emu.mem.w32(0x4044A8, s['origin'][0])
    emu.mem.w32(0x4044AC, s['origin'][1])
    emu.mem.w32(0x4044DC, s['width'])
    emu.mem.w32(0x4044E0, s['height'])
    emu.mem.write(0x4044F0, s['grid'])
    emu.mem.w32(0x44FD74, s['full_scissor'][0])
    emu.mem.w32(0x44FD78, s['full_scissor'][1])
    emu.mem.w64(0x44FD60, s['zbuf'])
    emu.mem.w32(0x4044D4, s['counters'][0])
    emu.mem.w32(0x4044D8, s['counters'][1])
    emu.mem.w32(0x10000000, s['timer'][0])
    emu.mem.w32(ICON_COUNT, len(s['icons']))
    for i, ic in enumerate(s['icons']):
        e = ICONS + i * 0x1C
        tex = ic['tex']
        if tex:
            emu.mem.w16(tex, ic['tex_w'])
            emu.mem.w16(tex + 2, ic['tex_h'])
        for off, v in ((0, ic['x']), (4, ic['y']), (8, tex), (0xC, ic['rotate']),
                       (0x14, ic['var']), (0x18, ic['script'])):
            emu.mem.w32(e + off, v)


def run_draw(emu, s, world, centre, dl, cb_addr):
    install(emu, s, world, centre, dl)
    emu.hook(0x16A424, lambda em: em.mem.w32(0x10000000, s['timer'][1]))
    # The icon stubs answer in table order; build the answer stream the way the code asks.
    answers = []
    for ic in s['icons']:
        if ic['var']:
            answers.append(ic['var_ok'])
            if not ic['var_ok']:
                continue
        if ic['script']:
            answers.append(ic['script_ok'])
    stream = iter(answers)
    emu.stub(VARS_GET, function=lambda em: next(stream), name='vars_get')
    emu.stub(SCRIPT_RUN, function=lambda em: next(stream), name='script_runByName')
    emu.stub(ADD_PACKET, ret=0, name='gfx_addSortedPacket')
    emu.reset_log()
    emu.f[12], emu.f[13], emu.f[14] = s['offx'], s['offy'], s['zoom']
    emu.f[15], emu.f[16], emu.f[17], emu.f[18] = s['half_w'], s['half_h'], s['blip_size'], s['icon_size']
    emu.call(FUNC, world, centre, cb_addr, s['yaw'] & 0xFFFF, max_steps=20000000)
    want = R.draw(s, FILL)
    end = emu.mem.u32(DL_CURSOR)
    check('end cursor', end, want['end'])
    got_bytes = emu.mem.read(dl, max(end - dl, 0))
    want_bytes = bytes(want['bytes'].get(dl + i, FILL) for i in range(end - dl))
    if got_bytes != want_bytes:
        i = next(i for i in range(len(got_bytes)) if got_bytes[i] != want_bytes[i])
        raise Fail('display list differs at +0x%x (qword at 0x%x): got %s want %s' % (
            i, dl + (i & ~15), got_bytes[i & ~15:(i & ~15) + 16].hex(),
            want_bytes[i & ~15:(i & ~15) + 16].hex()))
    names = {cb_addr: 'callback', VARS_GET: 'vars_get', SCRIPT_RUN: 'script_runByName',
             MEMCPY: 'memcpy', ADD_PACKET: 'gfx_addSortedPacket'}
    got_calls = []
    for c in emu.calls:
        if c.target not in names:
            continue
        nm, a = names[c.target], [x & 0xFFFFFFFF for x in c.args]
        got_calls.append({'callback': (nm, a[0]), 'vars_get': (nm, a[0]),
                          'script_runByName': (nm, a[0]), 'memcpy': (nm, a[0], a[1], a[2]),
                          'gfx_addSortedPacket': (nm, a[0], a[1], a[2], a[3], a[4])}[nm])
    want_calls = [c for c in want['calls'] if c[0] != 'ranges']
    check('calls', got_calls, want_calls)
    check('counters', (emu.mem.u32(0x4044D4), emu.mem.u32(0x4044D8)), want['counters'])
    allowed = [(dl, max(end - dl, 0)), (DL_CURSOR, 4), (0x4044D4, 8)]
    stray = [(hex(pc), hex(a)) for pc, a, size, _v in emu.writes
             if not any(b <= a and a + size <= b + n for b, n in allowed)]
    check('stray stores', stray, [])
    d = seed_draws(emu)
    for k in DRAWS:
        DRAWS[k] += d[k]
    check('seed draws', d, {'shared': 0, 'cosmetic': 0, 'third': 0})
    return want


def prop_draw(emu, rng, cases):
    world, centre = emu.alloc(0x80), emu.alloc(16)
    dl = emu.alloc(0x40000)
    texs = [emu.alloc(0x10) for _ in range(4)]
    cb_addr = emu.alloc(16)
    rec = {}

    def callback(em):
        i = em.r[4] & 0xFFFFFFFF
        blips = rec['s']['blips']
        if i >= len(blips):
            return -1
        b = blips[i]
        if b is None:
            return 0
        em.mem.w32(em.r[5] & 0xFFFFFFFF, b['x'])
        em.mem.w32((em.r[5] + 4) & 0xFFFFFFFF, b['y'])
        em.mem.w16(em.r[6] & 0xFFFFFFFF, b['angle'])
        em.mem.w32(em.r[7] & 0xFFFFFFFF, b['r'])
        em.mem.w32(em.r[8] & 0xFFFFFFFF, b['g'])
        em.mem.w32(em.r[9] & 0xFFFFFFFF, b['b'])
        em.mem.w32(em.r[10] & 0xFFFFFFFF, b['scale'])
        return 1
    emu.stub(cb_addr, function=callback, name='callback')
    drawn = blips = icons = strips = 0
    for _ in range(cases):
        s = make_state(emu, rng, world, centre, dl)
        for i, ic in enumerate(s['icons']):
            if ic['tex']:
                ic['tex'] = texs[i]
        rec['s'] = s
        want = run_draw(emu, s, world, centre, dl, cb_addr)
        drawn += want['drawn']
        blips += sum(1 for b in s['blips'] if b) if want['drawn'] and F.lt(R.K_BLIP_MIN_ZOOM, s['zoom']) else 0
        strips += sum(1 for c in want['calls'] if c[0] == 'gfx_addSortedPacket' and c[3] == s['world_tex'])
        icons += sum(1 for c in want['calls'] if c[0] == 'gfx_addSortedPacket' and c[3] not in (0, s['world_tex']))
    return '%d (%d drew; %d blips, %d textured icons, %d map strips)' % (cases, drawn, blips, icons, strips)


def prop_draw_blipcolor(emu, rng, cases):
    """0x168cac with the ORIGINAL minimap_blipColor 0x1e40a8 over an object list."""
    world, centre = emu.alloc(0x80), emu.alloc(16)
    dl = emu.alloc(0x40000)
    vt = emu.alloc(16)
    getcls = emu.alloc(16)
    lst = emu.alloc(4 * 16)
    objs = [emu.alloc(0x400) for _ in range(8)]
    emu.mem.w32(vt + 4, getcls)
    emu.stub(getcls, ret=0, name='vtable+4')
    emu.stub(0x3C3AB8, ret=0, name='0x3c3ab8')
    emu.stub(0x3B1250, function=lambda em: rec['isplayer'].pop(0), name='0x3b1250')
    rec = {}
    total = 0
    for _ in range(cases):
        s = make_state(emu, rng, world, centre, dl, cb_blips=True)
        s['icons'] = []
        sim = rng.getrandbits(8)
        emu.mem.w32(0x44FDCC, sim)
        n = rng.randint(0, 6)
        isplayer, blips = [], []
        healths = [rng.choice([F.f32(50.0), 0, F.f32(-1.0)]) for _k in range(4)]
        for k in range(4):
            emu.mem.w32(0x4D8AF0 + k * 0x4C30 + 0xAC, healths[k])
        for i in range(n):
            o = objs[i]
            emu.mem.w32(lst + 4 * i, o)
            emu.mem.w32(o + 0x48, vt)
            x = F.f32((rng.uniform(-40, 40) + F.to_float(s['centre'][0]) / 120.0) * 120.0)
            y = F.f32((rng.uniform(-40, 40) + F.to_float(s['centre'][1]) / 120.0) * 120.0)
            emu.mem.w32(o + 0x10, x)
            emu.mem.w32(o + 0x14, y)
            emu.mem.w32(o + 0x18, 0)
            ang = rng.getrandbits(16)
            emu.mem.w16(o + 0x38, ang)
            player = rng.random() < 0.5
            isplayer.append(1 if player else 0)
            if player:
                kind = rng.randint(0, 3)
                health = healths[kind]
                emu.mem.w32(o + 0x3C8, kind)
                hv = F.to_float(health)
                if not H.minimap_player_drawn(hv, sim):
                    blips.append(None)
                    continue
                r, g, b = H.minimap_player_blip(kind)
                blips.append({'x': x, 'y': y, 'angle': ang, 'r': r, 'g': g, 'b': b, 'scale': F.ONE})
            else:
                flags = rng.choice([0x20, 0x28, 0x00, 0x60])
                bits = rng.choice([0, 1 << 43, 3 << 42])
                emu.mem.w32(o + 0xC, flags)
                emu.mem.w64(o + 0xA8, bits)
                if (flags & 0x28) == 0x20 and bits & (1 << 43):
                    blips.append({'x': x, 'y': y, 'angle': ang, 'r': 0xE7, 'g': 0xC1, 'b': 0x52,
                                  'scale': F.ONE})
                elif flags & 0x20 and (bits & (3 << 42)) == (3 << 42) and (flags & 0x28) != 0x20:
                    blips.append({'x': x, 'y': y, 'angle': ang, 'r': 0xC8, 'g': 0xC8, 'b': 0xC8,
                                  'scale': F.HALF})
                else:
                    blips.append(None)
        emu.mem.w32(lst + 4 * n, 0)
        emu.mem.w32(OBJ_LIST_PTR, lst)
        rec['isplayer'] = list(isplayer)
        s['blips'] = blips
        run_draw(emu, s, world, centre, dl, CALLBACK)
        total += sum(1 for b in blips if b)
    return '%d (%d accepted blips)' % (cases, total)


PROPS = (('libm_floor_ceil', lambda e, r: prop_libm(e, r)),
         ('gate_16a838', lambda e, r: prop_gate(e, r)),
         ('cell_16a7dc', lambda e, r: prop_cell(e, r)),
         ('draw_168cac', lambda e, r: prop_draw(e, r, 200)),
         ('draw_with_blipColor', lambda e, r: prop_draw_blipcolor(e, r, 100)))


def main(argv):
    seed, filt = 20973, None
    if '--seed' in argv:
        seed = int(argv[argv.index('--seed') + 1])
    if '-k' in argv:
        filt = argv[argv.index('-k') + 1]
    path = elf_path(argv)
    if not path:
        print('no SLUS_209.73; difftest skipped')
        return 0
    emu = EE(path)
    emu.mem.map(0x10000000, 0x1000)       # EE timer 0 count, read at 0x168d58 / 0x16a424
    print('difftest_hud_minimap seed %d (%s)' % (seed, path))
    for name, fn in PROPS:
        if filt and filt not in name:
            continue
        rng = random.Random('%d/%s' % (seed, name))
        emu.reset_log()
        for k in DRAWS:
            DRAWS[k] = 0
        result = fn(emu, rng)
        d = seed_draws(emu)
        for k in DRAWS:
            DRAWS[k] += d[k]
        check('seed draws ' + name, DRAWS, {'shared': 0, 'cosmetic': 0, 'third': 0})
        print('  %-22s ok  cases %s  seed draws shared %d cosmetic %d third %d (model 0/0/0)'
              % (name, result, DRAWS['shared'], DRAWS['cosmetic'], DRAWS['third']))
    print('difftest_hud_minimap: ok')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv))
    except Fail as exc:
        print('FAIL', exc)
        sys.exit(1)
