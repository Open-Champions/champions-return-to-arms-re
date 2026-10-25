"""Tests for fx_particle_defs.py on hand-assembled instruction words (no game file).

Run: python3 -m unittest discover -s tools -p test_fx_particle_defs.py
"""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import fx_particle_defs as X                    # noqa: E402

SP, RA = 29, 31


def i_type(op, rs, rt, imm):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xffff)


def lui(rt, imm):
    return i_type(0x0f, 0, rt, imm)


def ori(rt, rs, imm):
    return i_type(0x0d, rs, rt, imm)


def addiu(rt, rs, imm):
    return i_type(0x09, rs, rt, imm)


def sw(rt, off, base=SP):
    return i_type(0x2b, base, rt, off)


def ld(rt, off, base=SP):
    return i_type(0x37, base, rt, off)


def lwc1(ft, off, base):
    return i_type(0x31, base, ft, off)


def mtc1(rt, fs):
    return (0x11 << 26) | (0x04 << 21) | (rt << 16) | (fs << 11)


def jal(target):
    return (0x03 << 26) | ((target >> 2) & 0x3ffffff)


def bne(rs, rt, off):
    return i_type(0x05, rs, rt, off)


def bnel(rs, rt, off):
    return i_type(0x15, rs, rt, off)


NOP = 0


def float_bits(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def load_float(freg, x, tmp=1):
    b = float_bits(x)
    out = [lui(tmp, b >> 16)]
    if b & 0xffff:
        out.append(ori(tmp, tmp, b & 0xffff))
    return out + [mtc1(tmp, freg)]


def ctor_call(def_addr, sizes=(2.0, 5.0, -20.0), rgba0=(200, 150, 100, 255),
              rgba1=(10, 20, 30), a1=0, life=2, kind=1, tile=0x12, life_reg=None):
    w = []
    for freg, x in zip((12, 13, 14), sizes):
        w += load_float(freg, x)
    w += [lui(4, def_addr >> 16), addiu(4, 4, def_addr & 0xffff)]
    for reg, v in zip((5, 6, 7, 8, 9, 10, 11), list(rgba0) + list(rgba1)):
        w.append(addiu(reg, 0, v))
    w += [addiu(2, 0, kind), addiu(3, 0, tile), sw(0 if a1 == 0 else 12, 0x00)]
    if a1:
        w.insert(-1, addiu(12, 0, a1))
    w += [sw(life_reg if life_reg is not None else 13, 0x08)]
    if life_reg is None:
        w.insert(-1, addiu(13, 0, life))
    w += [sw(2, 0x10), sw(3, 0x18), jal(X.DEF_CTOR), sw(0, 0x20)]
    return w


class Scan(unittest.TestCase):
    def scan(self, words, base=0x100000, read_u32=None):
        return list(X.scan_words(words, base, read_u32))

    def test_simple_call(self):
        (r,) = self.scan(ctor_call(0x00870408))
        self.assertTrue(r['complete'])
        self.assertEqual(r['def'], 0x00870408)
        self.assertEqual((r['size_start'], r['size_end'], r['gravity']), (2.0, 5.0, -20.0))
        self.assertEqual(r['start_rgba'], [200, 150, 100, 255])
        self.assertEqual(r['end_rgba'], [10, 20, 30, 0])
        self.assertEqual((r['life_ticks'], r['kind_name'], r['tile']), (60, 'add', 0x12))

    def test_static_init_guard_gives_s0(self):
        # bne $16, $2, skip ; addiu $2, $zero, 1 (delay slot); then lifeClass from $16.
        w = [addiu(2, 0, 1), bne(16, 2, 0x40), addiu(2, 0, 1)] + ctor_call(0x00500000, life_reg=16)
        (r,) = self.scan(w)
        self.assertTrue(r['complete'])
        self.assertEqual(r['life_ticks'], 30)          # $16 = 1 on the fall-through path

    def test_likely_delay_slot_skipped(self):
        # bnel $16, $17, x ; ld $16, ... -- the ld runs only when taken.
        w = [addiu(16, 0, 3), addiu(17, 0, 3), bnel(16, 17, 0x40), ld(16, 0x30)]
        w += ctor_call(0x00500000, life_reg=16)
        (r,) = self.scan(w)
        self.assertEqual(r['life_ticks'], 90)

    def test_other_call_forgets_argument_registers(self):
        w = [addiu(13, 0, 2), addiu(17, 0, 2), jal(0x00123450), NOP]
        (r,) = self.scan(w + ctor_call(0x00500000, life_reg=13))
        self.assertNotIn('life_ticks', r)              # $13 (t5) is caller-saved
        (r,) = self.scan(w + ctor_call(0x00500000, life_reg=17))
        self.assertEqual(r['life_ticks'], 60)          # $17 (s1) survives the call

    def test_unknown_register_is_reported_not_guessed(self):
        w = ctor_call(0x00500000, life_reg=20)         # $20 never set
        (r,) = self.scan(w)
        self.assertFalse(r['complete'])
        self.assertNotIn('life_ticks', r)

    def test_float_from_constant_address(self):
        table = {0x00410000: float_bits(7.5)}
        w = ctor_call(0x00500000)
        w = [lui(1, 0x0041), lwc1(12, 0, 1)] + w[2:]   # 2.0 is lui + mtc1: replace both
        (r,) = self.scan(w, read_u32=table.get)
        self.assertEqual((r['size_start'], r['size_end']), (7.5, 5.0))

    def test_kind_and_life_clamped(self):
        (r,) = self.scan(ctor_call(0x00500000, life=9, kind=-2))
        self.assertEqual((r['life_class'], r['kind']), (3, 0))

    def test_fmt_line(self):
        (r,) = self.scan(ctor_call(0x00870408))
        line = X.fmt_line(r)
        self.assertTrue(line.startswith('%08x\tparticleDef_ctor\t870408\t2\t5\t-20' % r['site']))


if __name__ == '__main__':
    unittest.main()
