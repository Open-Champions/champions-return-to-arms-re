#!/usr/bin/env python3
"""Synthetic tests of tools/vu1_emu.py: microprograms written here (no game words), packets
built here.  python3 -m unittest discover -s tools -p 'test_*.py'"""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import vu1_emu as V                                          # noqa: E402

F = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]   # noqa: E731
UNOP = 0x000002FF
LNOP = 0x8000033C
E_BIT = 1 << 30
I_BIT = 1 << 31
XYZW = 15


def upper(op, fd=0, fs=0, ft=0, dest=XYZW):
    return (dest << 21) | (ft << 16) | (fs << 11) | (fd << 6) | op


def add(fd, fs, ft, dest=XYZW):
    return upper(0x28, fd, fs, ft, dest)


def sub(fd, fs, ft, dest=XYZW):
    return upper(0x2C, fd, fs, ft, dest)


def mulq(fd, fs, dest=XYZW):
    return upper(0x1C, fd, fs, 0, dest)


def clipw(fs, ft):                       # CLIPw.xyz
    return (0xE << 21) | (ft << 16) | (fs << 11) | (0x7 << 6) | 0x3F


def iaddiu(it, is_, imm):
    return (0x08 << 25) | (it << 16) | (is_ << 11) | ((imm & 0x7800) << 10) | (imm & 0x7FF)


def isubiu(it, is_, imm):
    return (0x09 << 25) | (it << 16) | (is_ << 11) | ((imm & 0x7800) << 10) | (imm & 0x7FF)


def sq(fs, it, imm, dest=XYZW):
    return (0x01 << 25) | (dest << 21) | (it << 16) | (fs << 11) | (imm & 0x7FF)


def lq(ft, is_, imm, dest=XYZW):
    return (0x00 << 25) | (dest << 21) | (ft << 16) | (is_ << 11) | (imm & 0x7FF)


def div(fs, fsf, ft, ftf):
    return (0x40 << 25) | (ftf << 23) | (fsf << 21) | (ft << 16) | (fs << 11) | (0xE << 6) | 0x3C


WAITQ = (0x40 << 25) | (0xE << 6) | 0x3F
FCAND1 = (0x12 << 25) | 1                # FCAND vi1, 0x000001


def ibne(it, is_, off):
    return (0x29 << 25) | (it << 16) | (is_ << 11) | (off & 0x7FF)


def xgkick(is_):
    return (0x40 << 25) | (is_ << 11) | (0x1B << 6) | 0x3C


def program(pairs):
    return b''.join(struct.pack('<II', lo, up) for up, lo in pairs)


def run(pairs, setup=None, **kw):
    vu = V.Vu1(**kw)
    vu.load_micro(0, program(pairs))
    if setup:
        setup(vu)
    vu.run(0)
    return vu


class Arithmetic(unittest.TestCase):
    def test_add_and_end_bit(self):
        def setup(vu):
            vu.vf[1] = [F(1.5), F(2.0), F(-3.0), F(0.25)]
            vu.vf[2] = [F(1.0), F(1.0), F(1.0), F(1.0)]
        vu = run([(add(3, 1, 2) | E_BIT, LNOP), (UNOP, LNOP), (add(4, 1, 1), LNOP)], setup)
        self.assertEqual(vu.vf[3], [F(2.5), F(3.0), F(-2.0), F(1.25)])
        self.assertEqual(vu.vf[4], [0, 0, 0, 0])          # after the pair behind the E bit
        self.assertEqual(vu.instructions, 2)

    def test_round_toward_zero(self):
        def setup(vu):
            vu.vf[1] = [F(1.0), 0, 0, 0]
            vu.vf[2] = [F(2.0 ** -24 * 3), 0, 0, 0]      # 1 + 1.5 ulp
        vu = run([(add(3, 1, 2, 8) | E_BIT, LNOP), (UNOP, LNOP)], setup)
        self.assertEqual(vu.vf[3][0], F(1.0) + 1)        # cut, not rounded up

    def test_exponent_255_is_a_number(self):
        def setup(vu):
            vu.vf[1] = [0x7F800000, 0, 0, 0]             # an infinity to IEEE
            vu.vf[2] = [F(-1.0), 0, 0, 0]
        vu = run([(add(3, 1, 2, 8) | E_BIT, LNOP), (UNOP, LNOP)], setup)
        self.assertEqual(vu.vf[3][0], 0x7F7FFFFE)        # read as the largest, minus 1, cut

    def test_mask_keeps_other_lanes(self):
        def setup(vu):
            vu.vf[1] = [F(1.0)] * 4
            vu.vf[3] = [1, 2, 3, 4]
        vu = run([(add(3, 1, 1, 0b0010) | E_BIT, LNOP), (UNOP, LNOP)], setup)   # .z only
        self.assertEqual(vu.vf[3], [1, 2, F(2.0), 4])


class PairSemantics(unittest.TestCase):
    def test_lower_reads_before_upper_writes(self):
        def setup(vu):
            vu.vf[1] = [F(1.0)] * 4
        # SUB.w vf1 = vf1 - vf1 with SQ vf1 in the same pair: the store sees w = 1.0;
        # a store in the next pair sees 0
        vu = run([(sub(1, 1, 1, 1), sq(1, 0, 10)), (UNOP, sq(1, 0, 11)) , (UNOP | E_BIT, LNOP),
                  (UNOP, LNOP)], setup)
        self.assertEqual(vu.qword(10)[3], F(1.0))
        self.assertEqual(vu.qword(11)[3], 0)

    def test_upper_wins_over_lower(self):
        def setup(vu):
            vu.vf[1] = [F(1.0)] * 4
            vu.set_qword(5, [7, 7, 7, 7])
        vu = run([(add(2, 1, 1), lq(2, 0, 5)), (UNOP | E_BIT, LNOP), (UNOP, LNOP)], setup)
        self.assertEqual(vu.vf[2], [F(2.0)] * 4)

    def test_branch_delay_slot(self):
        # vi1 = 3; loop: vi1 -= 1 (IADDIU with 0xffff wraps), vi2 += 1 in the delay slot
        pairs = [(UNOP, iaddiu(1, 0, 3)),
                 (UNOP, isubiu(1, 1, 1)),               # 1: vi1 -= 1
                 (UNOP, ibne(1, 0, -2)),                # 2: back to 1 while vi1 != 0
                 (UNOP, iaddiu(2, 2, 1)),               # 3: delay slot, always runs
                 (UNOP | E_BIT, LNOP), (UNOP, LNOP)]
        vu = run(pairs)
        self.assertEqual(vu.vi[1], 0)
        self.assertEqual(vu.vi[2], 3)


class Divider(unittest.TestCase):
    def _prog(self, gap, waitq_pair):
        pairs = [(UNOP, div(0, 3, 1, 0))]                # Q = vf0.w / vf1.x
        pairs += [(UNOP, LNOP)] * gap
        pairs += [(mulq(2, 3), WAITQ if waitq_pair else LNOP), (UNOP | E_BIT, LNOP), (UNOP, LNOP)]
        return pairs

    def setup(self, vu):
        vu.vf[1] = [F(4.0), 0, 0, 0]
        vu.vf[3] = [F(1.0)] * 4
        vu.q = F(10.0)

    def test_old_q_until_seven_cycles(self):
        vu = run(self._prog(2, False), self.setup)
        self.assertEqual(vu.vf[2][0], F(10.0))
        vu = run(self._prog(6, False), self.setup)
        self.assertEqual(vu.vf[2][0], F(0.25))

    def test_waitq_in_the_same_pair(self):
        vu = run(self._prog(0, True), self.setup, waitq_first=True)
        self.assertEqual(vu.vf[2][0], F(0.25))
        vu = run(self._prog(0, True), self.setup, waitq_first=False)
        self.assertEqual(vu.vf[2][0], F(10.0))           # what tools/recomp/render/vu1.cpp does


class Flags(unittest.TestCase):
    def test_clip_seen_four_cycles_later(self):
        def setup(vu):
            vu.vf[1] = [F(5.0), 0, 0, F(1.0)]            # x > w
        early = [(clipw(1, 1), LNOP), (UNOP, FCAND1), (UNOP | E_BIT, LNOP), (UNOP, LNOP)]
        self.assertEqual(run(early, setup).vi[1], 0)
        late = [(clipw(1, 1), LNOP)] + [(UNOP, LNOP)] * 3 + [(UNOP, FCAND1), (UNOP | E_BIT, LNOP),
                                                              (UNOP, LNOP)]
        self.assertEqual(run(late, setup).vi[1], 1)


class Gif(unittest.TestCase):
    def test_xgkick_packed_sprite(self):
        gs = V.GifReader()

        def setup(vu):
            vu.kick = gs.path1
            # tag: NLOOP 1, EOP, PRE, PRIM 6, FLG packed, NREG 3: RGBAQ, UV, XYZF2
            vu.set_qword(0x10, [0x8001, (3 << 28) | (6 << 15) | (1 << 14), 0x431, 0])
            vu.set_qword(0x11, [10, 20, 30, 40])
            vu.set_qword(0x12, [0x123, 0x456, 0, 0])
            vu.set_qword(0x13, [0x1234, 0x5678, 0x99 << 4, 1 << 15])
            vu.vi[5] = 0x10
        run([(UNOP, xgkick(5)), (UNOP | E_BIT, LNOP), (UNOP, LNOP)], setup)
        v = gs.vertices[0]
        self.assertEqual((v.x, v.y, v.z, v.adc, v.rgba, v.uv, v.prim),
                         (0x1234, 0x5678, 0x99, 1, (10, 20, 30, 40), (0x123, 0x456), 6))

    def test_ad_and_reglist(self):
        gs = V.GifReader()
        tag_ad = [0x8002, (1 << 28), 0xE, 0]                    # A+D, two qwords, EOP
        words = tag_ad + [0x48, 0, 0x42, 0] + [0x00050007, 3, 0x05, 0]
        gs.read_words(words)
        self.assertEqual(gs.raw, [(0x42, 0x48), (0x05, 0x00050007 | (3 << 32))])
        self.assertEqual((gs.vertices[0].x, gs.vertices[0].y, gs.vertices[0].z), (7, 5, 3))
        gs = V.GifReader()
        tag_rl = [0x8001, (1 << 26) | (3 << 28), 0x035, 0]      # REGLIST: XYZ2, UV, XYZ2? (5, 3, 0)
        gs.read_words(tag_rl + [0x10002, 0, 0x30004, 0] + [6, 0, 0, 0])
        self.assertEqual([r for r, _ in gs.raw], [5, 3, 0])


class Vif(unittest.TestCase):
    def test_unpack_v4_16_signed_and_mscal(self):
        vu = V.Vu1()
        vu.load_micro(0, program([(UNOP, lq(1, 0, 0x20)), (UNOP | E_BIT, sq(1, 0, 0x30)),
                                  (UNOP, LNOP)]))
        vif = V.Vif1(vu)
        data = struct.pack('<4h', -1, 2, -3, 4)
        words = list(struct.unpack('<2I', data))
        vif.feed([0x01000101, 0x6D010020] + words + [0x14000000])    # STCYCL 1,1; UNPACK; MSCAL 0
        self.assertEqual(vu.qword(0x20), [0xFFFFFFFF, 2, 0xFFFFFFFD, 4])
        self.assertEqual(vu.qword(0x30), vu.qword(0x20))
        self.assertEqual(vif.programs, [0])

    def test_mpg_and_direct(self):
        vu = V.Vu1()
        got = []
        vif = V.Vif1(vu, direct=got.extend)
        code = program([(UNOP | E_BIT, iaddiu(3, 0, 77)), (UNOP, LNOP)])
        words = list(struct.unpack('<%dI' % (len(code) // 4), code))
        vif.feed([0x4A020010] + words + [0x14000010, 0x50000001, 1, 2, 3, 4])
        self.assertEqual(vu.vi[3], 77)
        self.assertEqual(got, [1, 2, 3, 4])

    def test_stcycl_skip(self):
        vu = V.Vu1()
        vif = V.Vif1(vu)
        vif.feed([0x01000104, 0x6C020000] + [1, 2, 3, 4, 5, 6, 7, 8])   # CL 4 WL 1: every 4th qword
        self.assertEqual(vu.qword(0), [1, 2, 3, 4])
        self.assertEqual(vu.qword(4), [5, 6, 7, 8])
        self.assertEqual(vu.qword(1), [0, 0, 0, 0])


class Dma(unittest.TestCase):
    def test_chain(self):
        mem = bytearray(0x400)

        def put(a, words):
            struct.pack_into('<%dI' % len(words), mem, a, *words)
        put(0x000, [0x10000001, 0, 0xAAAA, 0xBBBB])      # cnt 1, VIF words in the tag
        put(0x010, [1, 2, 3, 4])
        put(0x020, [0x30000001, 0x200, 0, 0])            # ref 1 qword at 0x200
        put(0x200, [9, 9, 9, 9])
        put(0x030, [0x50000000, 0x300, 0, 0])            # call 0x300
        put(0x300, [0x60000001, 0, 5, 5])                # ret with one qword
        put(0x310, [6, 6, 6, 6])
        put(0x040, [0x60000000, 0, 0, 0])                # ret, empty stack: the end
        log = []
        words = V.dma_chain_words(lambda a, n: bytes(mem[a:a + n]), 0, log=log)
        self.assertEqual(words, [0xAAAA, 0xBBBB, 1, 2, 3, 4, 0, 0, 9, 9, 9, 9, 0, 0, 5, 5, 6, 6, 6, 6,
                                 0, 0])
        self.assertEqual([t[1] for t in log], [1, 3, 5, 6, 6])


if __name__ == '__main__':
    unittest.main()
