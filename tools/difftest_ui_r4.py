#!/usr/bin/env python3
"""Round-4 font-page and HUD-sprite functions against SLUS-20973 v2.00.

Runs tex_relocate (0x179e10), the non-streaming DBP stores in gfx_dmaHandler
(0x16c048-0x16c090), ui_drawSpriteImpl (0x17b590) and the clipped drawer
(0x17b8b0). Compares them to ref_font_page and ref_ui_layout. Exits 0 when
the ELF is not on this machine. Does not import unittest (tools/dis.py would
shadow the stdlib).

  python3 tools/difftest_ui_r4.py [SLUS_209.73]
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ref_font_page as F
import ref_ui_layout as L
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
                 os.path.expanduser('~/champions-re/SLUS_209.73')):
        if os.path.isfile(cand):
            return cand
    return None


class Fail(Exception):
    pass


def check(name, got, want):
    if got != want:
        raise Fail('%s: got %s want %s' % (name, got, want))


def plant(emu, flags, offset, qwc=0x123):
    size = offset + 0x480
    addr = emu.alloc(size)
    raw = bytearray(size)
    struct.pack_into('<6HII', raw, 0, 16, 4, 8, qwc, flags, 0, 0, offset)
    emu.mem.write(addr, bytes(raw))
    return addr, bytes(raw)


def relocate(emu):
    for offset in (0x44, 0x80, 0xb4):
        addr, raw = plant(emu, 0x0044, offset)
        emu.call(0x179e10, addr)
        want = F.apply_tex_relocate_prefix(addr, raw)
        got = emu.mem.read(addr, 0x20)
        check('relocate 0x%x' % offset, got, want[:0x20])
        check('qwc 0x%x' % offset, emu.mem.u16(addr + 6), 0x123)
        emu.call(0x179e10, addr)
        check('relocate twice 0x%x' % offset, emu.mem.read(addr, 0x20), want[:0x20])


def patch(emu, flags, offset, block):
    addr, raw = plant(emu, flags, offset)
    emu.call(0x179e10, addr)
    check('patch relocate %x' % flags, emu.mem.read(addr, 0x20),
          F.apply_tex_relocate_prefix(addr, raw)[:0x20])
    emu.mem.w16(addr + 0x18, block)
    pkt = emu.mem.u32(addr + 0x10)
    alias = pkt | 0x20000000
    emu.mem.map(alias, 0x480)
    emu.r[16] = addr
    emu.r[23] = 0x20000000
    emu.run(0x16c048, until=(0x16c090,))
    check('palette dbp %x' % flags, emu.mem.u16(alias + F.PALETTE_DBP), block)
    check('cached palette untouched %x' % flags, emu.mem.u16(pkt + F.PALETTE_DBP), 0)
    image = F.dma_image_dbp(flags)
    if image is None:
        check('no 8-bit store %x' % flags, emu.mem.u16(alias + F.IMAGE_DBP_8), 0)
        check('no 4-bit store %x' % flags, emu.mem.u16(alias + F.IMAGE_DBP_4), 0)
    else:
        check('image dbp %x' % flags, emu.mem.u16(alias + image), (block + 4) & 0xffff)
        other = F.IMAGE_DBP_4 if image == F.IMAGE_DBP_8 else F.IMAGE_DBP_8
        check('other dbp %x' % flags, emu.mem.u16(alias + other), 0)


def arm(emu, seen):
    base = emu.alloc(0x2000)
    emu.mem.w32(0x44fe0c, base)
    emu.mem.w32(0x44fe10, base)
    emu.mem.w32(0x44fda4, 0x10000)
    emu.mem.w32(0x44fd70, 0)   # letterbox height; 0 keeps the destination unshifted
    emu.mem.w8(0x44fdd4, 0)    # field flag; the other arm adjusts destination y

    def quad(em):
        seen.append(tuple(em.r[i] & 0xffffffff for i in range(4, 12)))

    emu.stub(0x17ab50, function=quad)
    emu.stub(0x16b7f0, ret=0)
    emu.stub(0x19d9e4, ret=0)
    return base


def header(emu, width, height):
    addr = emu.alloc(0x80)
    emu.mem.w16(addr, width)
    emu.mem.w16(addr + 2, height)
    emu.mem.w32(addr + 0x10, 0x80)
    emu.call(0x179e10, addr)
    check('size %dx%d' % (width, height),
          (emu.mem.u16(addr), emu.mem.u16(addr + 2)), (width, height))
    check('pointer %dx%d' % (width, height), emu.mem.u32(addr + 0x10), addr + 0x80)
    return addr


def draw(emu, base, seen, tex, width, height):
    emu.mem.w32(0x44fe0c, base)
    emu.mem.w32(0x44fe10, base)
    x, y = 16, 20
    before = len(seen)
    emu.call(0x17b590, tex, x, y, 6, 0x80808080)
    check('plain call %dx%d' % (width, height), len(seen), before + 1)
    _a0, _a1, dx, dy, u, v, w, h = seen[-1]
    check('plain source %dx%d' % (width, height), (dx, dy, u, v, w, h),
          (x, y + 1, 0, 0, width, height))
    sp = 0x01fff000
    emu.mem.w32(sp, height)
    emu.mem.w32(sp + 8, 0)
    emu.mem.w32(sp + 16, 0)
    emu.call(0x17b8b0, tex, x, y, 6, 0x80808080, 0, 0, width, sp=sp)
    _a0, _a1, dx, dy, u, v, w, h = seen[-1]
    check('clipped source %dx%d' % (width, height), (dx, dy, u, v, w, h),
          (x, y, 0, 0, width, height))
    # A tighter destination clip does not change the source span.
    emu.mem.w32(sp, 2)
    emu.call(0x17b8b0, tex, x, y, 6, 0x80808080, 0, 0, 10, sp=sp)
    _a0, _a1, dx, dy, u, v, w, h = seen[-1]
    check('clipped tight %dx%d' % (width, height), (u, v, w, h), (0, 0, width, height))
    # Flip exchanges the endpoints and keeps the same span.
    emu.mem.w32(sp, height)
    emu.mem.w32(sp + 8, 1)
    emu.call(0x17b8b0, tex, x, y, 6, 0x80808080, 0, 0, width, sp=sp)
    _a0, _a1, dx, dy, u, v, w, h = seen[-1]
    check('flip x %dx%d' % (width, height), (u, v, w, h), (width, 0, 0, height))


def main(argv):
    path = elf_path(argv)
    if path is None:
        print('difftest_ui_r4: no ELF, skipped')
        return 0
    emu = EE(path)
    relocate(emu)
    patch(emu, 0x0044, 0xb4, 7)
    patch(emu, 0x2000, 0x80, 3)
    patch(emu, 0x0020, 0x44, 9)
    seen = []
    base = arm(emu, seen)
    sizes = sorted({art.used for art in L.hud_art_round4()})
    check('sizes', tuple(sizes), ((32, 32), (83, 38), (100, 8), (160, 46), (320, 224)))
    for width, height in sizes:
        draw(emu, base, seen, header(emu, width, height), width, height)
    print('difftest_ui_r4: ok (%s)' % path)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv))
    except Exception as exc:
        print('difftest_ui_r4: FAIL', exc)
        sys.exit(1)
