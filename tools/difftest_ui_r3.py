#!/usr/bin/env python3
"""Round-3 UI functions against the original SLUS-20973 v2.00 code.

Runs the original instructions in tools/ee_emu.py and compares them to
ref_hud_dynamic / ref_ui_composite. Exits 0 when the ELF is not on this
machine. Does not import unittest (tools/dis.py would shadow the stdlib).

  python3 tools/difftest_ui_r3.py [SLUS_209.73]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ref_core as F
import ref_hud_dynamic as H
import ref_ui_composite as C
from ee_emu import EE


def elf_path(argv):
    if len(argv) > 1:
        return argv[1]
    env = os.environ.get('CHAMPIONS_ELF')
    if env:
        return env
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for cand in (os.path.join(here, 'SLUS_209.73'),
                 os.path.join(os.getcwd(), 'SLUS_209.73'),
                 os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'SLUS_209.73')):
        if os.path.isfile(cand):
            return cand
    return None


class Fail(Exception):
    pass


def check(name, got, want):
    if got != want:
        raise Fail('%s: got %s want %s' % (name, got, want))


def minimap(emu):
    emu.stub(0x168990, ret=0)
    for mode in (0, 1, 2):
        for players in (1, 4):
            emu.mem.w32(0x4f8400, mode)
            emu.mem.w32(0x4d8ae0, players)
            emu.call(0x1e3ff0)
            got = tuple(emu.mem.u32(a) for a in
                        (0x86af58, 0x86af5c, 0x86af60, 0x86af64, 0x86af68))
            check('minimap %d/%d' % (mode, players), got, H.minimap_params(mode, players))


def flying_run(emu):
    obj = emu.alloc(0xa0)
    vt = emu.alloc(16)
    dtor = emu.alloc(8)
    emu.mem.w32(dtor, 0x03e00008)          # jr ra
    emu.mem.w32(dtor + 4, 0)
    emu.mem.w16(vt + 8, 0)
    emu.mem.w32(vt + 12, dtor)
    emu.mem.w32(obj + 0x48, vt)
    for start, ticks in ((30, 30), (180, 180)):
        emu.mem.w16(obj + 0x96, start)
        emu.mem.w16(obj + 0x94, 0x80)
        life, alpha, delete = start, 0x80, False
        for n in range(ticks):
            emu.call(0x2022a8, obj)
            life, alpha, delete = H.flying_text_step(life, alpha)
            check('fly life %d/%d' % (start, n), emu.mem.u16(obj + 0x96), life)
            check('fly alpha %d/%d' % (start, n), emu.mem.u16(obj + 0x94), alpha)
        check('fly deleted %d' % start, delete, True)


def flying_draw(emu):
    obj = emu.alloc(0xa0)
    cam = emu.alloc(0x40)
    emu.mem.w32(cam + 0x34, 1)
    emu.mem.w32(0x4f8450, cam)
    emu.mem.w32(0x44fcf8, 1)
    emu.mem.w32(0x44fdd8, 0x1111)
    emu.mem.wf32(obj + 0x10, 1.0)
    emu.mem.wf32(obj + 0x14, 2.0)
    emu.mem.wf32(obj + 0x18, 3.0)
    emu.mem.w32(obj + 0x7c, (-4) & 0xffffffff)
    emu.mem.w16(obj + 0x94, 0x40)
    seen = {}

    def begin(em):
        seen['colour'] = em.r[6] & 0xffffffff
        seen['layer'] = em.r[5] & 0xffffffff

    def xform(em):
        out = em.r[4] & 0xffffffff
        src = em.r[6] & 0xffffffff
        seen['z'] = em.mem.u32(src + 8)
        em.mem.w32(out, 0x43000000)            # x = 128
        em.mem.w32(out + 4, 0x42800000)        # y = 64
        em.mem.w32(out + 8, 0)
        em.f[0] = 0x40000000                   # w = 2

    def draw(em):
        seen['x'] = em.r[4] & 0xffffffff
        seen['y'] = em.r[5] & 0xffffffff

    emu.stub(0x1800b8, function=begin)
    emu.stub(0x165ee0, function=xform)
    emu.stub(0x181b78, function=draw)
    emu.stub(0x181c30, function=draw)
    emu.stub(0x180500, ret=0)
    cases = ((1, 1), (2, 0), (2, 1), (0, 0))
    for kind, crit in cases:
        seen.clear()
        emu.mem.w32(obj + 0x8c, kind)
        emu.mem.w32(obj + 0x84, crit)
        emu.mem.w32(obj + 0x90, 0)
        emu.mem.w32(obj + 0x78, 9)
        emu.call(0x1f3830, obj)
        colour, force, lift = H.flying_text_style(kind, crit, 0x40)
        check('fly colour %d' % kind, seen['colour'], colour)
        check('fly layer', seen['layer'], 5)
        z = H.flying_text_anchor_z(F.from_int(3), lift)
        check('fly z %d/%d' % (kind, crit), seen['z'], z)
        xoff = 5 if force else 9
        want = H.flying_text_screen(xoff, (-4) & 0xffffffff, 0x43000000, 0x42800000, 0x40000000)
        check('fly xy %d' % kind, (seen['x'], seen['y']), want)


def compass_xform(emu):
    out = emu.alloc(16)
    mat = emu.alloc(64)
    pt = emu.alloc(16)
    # a non-identity matrix: row0 = (1, 2, 3, 4) and zeros elsewhere, plus translation
    words = [0x3f800000, 0x40000000, 0x40400000, 0x40800000] + [0] * 12
    for i, w in enumerate(words):
        emu.mem.w32(mat + 4 * i, w)
    for i, w in enumerate(H.COMPASS_OFFSET):
        emu.mem.w32(pt + 4 * i, w)
    emu.call(0x165fc0, out, mat, pt)
    got = tuple(emu.mem.u32(out + 4 * i) for i in range(3))
    check('mat4_xyz', got, H.mat4_xyz(words, H.COMPASS_OFFSET))


def present(emu):
    dest = emu.alloc(16)
    # 0x8400dc is read as a pointer; map the page if the ELF left it unmapped.
    try:
        emu.mem.w32(0x8400dc, dest)
    except Exception:
        emu.mem.map(0x840000, 0x1000)
        emu.mem.w32(0x8400dc, dest)
    emu.mem.w32(0x44fd88, 10)
    scratch = emu.alloc(4)
    emu.set_reg('a2', scratch)             # $6, a byte the prologue stores
    emu.set_reg('v0', 0x80)                # $2, clamped to >= 0 by 0x19ce58
    emu.set_reg('s5', 0x00450000)          # $21, base of the channel words
    emu.set_reg('s6', 0x00450000)          # $22; 0x19ce5c makes $7 = 0x44fd88
    emu.f[22] = F.from_int(128)
    emu.f[21] = F.from_int(0)
    emu.f[20] = F.from_int(255)
    emu.mem.w32(0x44fd80, C.BRIGHTNESS_DEFAULT)
    # 0x19ce3c loads the 0.8 and 0.2 constants; the colour word is stored at 0x19cf08.
    emu.run(0x19ce3c, until=(0x19cf0c,))
    check('present colour', emu.mem.u32(dest),
          C.present_colour(128, 0, 255, C.BRIGHTNESS_DEFAULT))
    check('darken step', emu.mem.u32(0x44fd88), 13)


def colour(emu):
    emu.f[12] = F.ONE
    got = emu.call(0x19ecac, 0x80aabbcc) & 0xffffffff
    check('scale 1', got, C.scale_rgb(0x80aabbcc, F.ONE))
    emu.f[12] = 0x3f000000
    got = emu.call(0x19ecac, 0x80404040) & 0xffffffff
    check('scale half', got, C.scale_rgb(0x80404040, 0x3f000000))


def main(argv):
    path = elf_path(argv)
    if not path:
        print('no SLUS_209.73; difftest skipped')
        return 0
    emu = EE(path)
    minimap(emu)
    flying_run(emu)
    flying_draw(emu)
    compass_xform(emu)
    present(emu)
    colour(emu)
    print('difftest_ui_r3: ok (%s)' % path)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv))
    except Fail as exc:
        print('FAIL', exc)
        sys.exit(1)
