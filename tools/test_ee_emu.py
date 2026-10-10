"""Tests for ee_emu.py using hand-assembled instruction words only; no game file needed.

Run: python3 -m unittest discover -s tools -p test_ee_emu.py

The expected values were worked out by hand from the MIPS III / R5900 instruction
definitions, not copied from the interpreter's output.
"""
import contextlib
import io
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ee_emu
from ee_emu import EE, CpuTrap, EmuError, MemoryFault, StepLimit, UnimplementedInstruction

BASE = 0x00010000
DATA = 0x00020000
M64 = 0xFFFFFFFFFFFFFFFF

ZERO, AT, V0, V1, A0, A1, A2, A3 = range(8)
T0, T1, T2, T3, T4, T5, T6, T7 = range(8, 16)
S0, S1 = 16, 17
T9, SP, RA = 25, 29, 31


# ---- a very small assembler ------------------------------------------------------------
def R(funct, rd=0, rs=0, rt=0, sa=0):
    return (rs << 21) | (rt << 16) | (rd << 11) | (sa << 6) | funct


def I(op, rt, rs, imm):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def J(op, target):
    return (op << 26) | ((target >> 2) & 0x03FFFFFF)


def REGIMM(code, rs, offset):
    return (1 << 26) | (rs << 21) | (code << 16) | (offset & 0xFFFF)


def MMI(funct, rd=0, rs=0, rt=0, sa=0):
    return (0x1C << 26) | R(funct, rd, rs, rt, sa)


def FS(funct, fd=0, fs=0, ft=0):
    return (0x11 << 26) | (0x10 << 21) | (ft << 16) | (fs << 11) | (fd << 6) | funct


def BC1(code, offset):
    return (0x11 << 26) | (8 << 21) | (code << 16) | (offset & 0xFFFF)


NOP = 0
JR_RA = R(0x08, rs=RA)


def addiu(rt, rs, imm):
    return I(0x09, rt, rs, imm)


def ori(rt, rs, imm):
    return I(0x0D, rt, rs, imm)


def mtc1(rt, fs):
    return (0x11 << 26) | (4 << 21) | (rt << 16) | (fs << 11)


def mfc1(rt, fs):
    return (0x11 << 26) | (rt << 16) | (fs << 11)


def f32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def machine(words, regs=None, fregs=None, data=None, fpu_model='ps2', run=True):
    """Load words at BASE followed by 'jr ra; nop', optionally map DATA, and call it."""
    emu = EE(fpu_model=fpu_model)
    emu.load_words(BASE, list(words) + [JR_RA, NOP])
    emu.mem.map(DATA, 0x1000)
    if data:
        emu.mem.write(DATA, bytes(data))
    for number, value in (regs or {}).items():
        emu.r[number] = value & M64
    for number, raw in (fregs or {}).items():
        emu.f[number] = raw
    if run:
        emu.call(BASE)
    return emu


class IntegerTests(unittest.TestCase):
    def one(self, word, regs, dest=V0):
        return machine([word], regs).r[dest]

    def test_addiu_and_addu_are_32_bit_and_sign_extend(self):
        self.assertEqual(self.one(addiu(V0, A0, 1), {A0: 0x7FFFFFFF}), 0xFFFFFFFF80000000)
        self.assertEqual(self.one(addiu(V0, A0, -1), {A0: 0}), M64)
        self.assertEqual(self.one(R(0x21, V0, A0, A1), {A0: 0xFFFFFFFF, A1: 1}), 0)
        self.assertEqual(self.one(R(0x21, V0, A0, A1), {A0: 0x7FFFFFFF, A1: 1}), 0xFFFFFFFF80000000)
        self.assertEqual(self.one(R(0x23, V0, A0, A1), {A0: 0, A1: 1}), M64)

    def test_doubleword_arithmetic_keeps_64_bits(self):
        self.assertEqual(self.one(R(0x2D, V0, A0, A1), {A0: 0x7FFFFFFF, A1: 1}), 0x80000000)
        self.assertEqual(self.one(R(0x2D, V0, A0, A1), {A0: M64, A1: 2}), 1)
        self.assertEqual(self.one(R(0x2F, V0, A0, A1), {A0: 0x100000000, A1: 1}), 0xFFFFFFFF)
        self.assertEqual(self.one(I(0x19, V0, A0, -1), {A0: 0x100000000}), 0xFFFFFFFF)

    def test_trapping_adds_raise(self):
        for word in (R(0x20, V0, A0, A1), I(0x08, V0, A0, 1)):
            with self.assertRaises(CpuTrap):
                machine([word], {A0: 0x7FFFFFFF, A1: 1})
        with self.assertRaises(CpuTrap):
            machine([R(0x2C, V0, A0, A1)], {A0: 0x7FFFFFFFFFFFFFFF, A1: 1})
        with self.assertRaises(CpuTrap):
            machine([R(0x22, V0, A0, A1)], {A0: 0x80000000 | 0xFFFFFFFF00000000, A1: 1})
        self.assertEqual(self.one(R(0x20, V0, A0, A1), {A0: 5, A1: 6}), 11)
        self.assertEqual(self.one(I(0x18, V0, A0, -2), {A0: 1}), M64)

    def test_logic_and_immediates(self):
        self.assertEqual(self.one(I(0x0C, V0, A0, 0xFF00), {A0: M64}), 0xFF00)
        self.assertEqual(self.one(I(0x0D, V0, A0, 0x8000), {A0: 0}), 0x8000)
        self.assertEqual(self.one(I(0x0E, V0, A0, 0xFFFF), {A0: 0xFFFF0000}), 0xFFFFFFFF)
        self.assertEqual(self.one(I(0x0F, V0, 0, 0x8000), {}), 0xFFFFFFFF80000000)
        self.assertEqual(self.one(I(0x0F, V0, 0, 0x1234), {}), 0x12340000)
        self.assertEqual(self.one(R(0x27, V0, A0, A1), {A0: 0, A1: 0}), M64)
        self.assertEqual(self.one(R(0x24, V0, A0, A1), {A0: 0xF0F0, A1: 0xFF00}), 0xF000)
        self.assertEqual(self.one(R(0x25, V0, A0, A1), {A0: 0xF0F0, A1: 0xFF00}), 0xFFF0)
        self.assertEqual(self.one(R(0x26, V0, A0, A1), {A0: 0xF0F0, A1: 0xFF00}), 0x0FF0)

    def test_comparisons_use_all_64_bits(self):
        self.assertEqual(self.one(R(0x2A, V0, A0, A1), {A0: M64, A1: 1}), 1)
        self.assertEqual(self.one(R(0x2B, V0, A0, A1), {A0: M64, A1: 1}), 0)
        # 0x1_0000_0000 is larger than 1, although its low word is 0
        self.assertEqual(self.one(R(0x2A, V0, A0, A1), {A0: 0x100000000, A1: 1}), 0)
        self.assertEqual(self.one(I(0x0A, V0, A0, -4), {A0: -5}), 1)
        self.assertEqual(self.one(I(0x0B, V0, A0, -1), {A0: 5}), 1)
        self.assertEqual(self.one(I(0x0B, V0, A0, 5), {A0: 5}), 0)

    def test_word_shifts(self):
        self.assertEqual(self.one(R(0x00, V0, rt=A0, sa=1), {A0: 0x40000000}), 0xFFFFFFFF80000000)
        self.assertEqual(self.one(R(0x00, V0, rt=A0, sa=0), {A0: 0x180000000}), 0xFFFFFFFF80000000)
        self.assertEqual(self.one(R(0x02, V0, rt=A0, sa=4), {A0: 0xFFFFFFFF80000000}), 0x08000000)
        self.assertEqual(self.one(R(0x03, V0, rt=A0, sa=4), {A0: 0xFFFFFFFF80000000}), 0xFFFFFFFFF8000000)
        # variable shifts use the low five bits of rs
        self.assertEqual(self.one(R(0x04, V0, rs=A1, rt=A0), {A0: 3, A1: 33}), 6)
        self.assertEqual(self.one(R(0x06, V0, rs=A1, rt=A0), {A0: 0x80000000, A1: 31}), 1)
        self.assertEqual(self.one(R(0x07, V0, rs=A1, rt=A0), {A0: 0x80000000, A1: 31}), M64)

    def test_doubleword_shifts(self):
        self.assertEqual(self.one(R(0x38, V0, rt=A0, sa=31), {A0: 1}), 0x80000000)
        self.assertEqual(self.one(R(0x3C, V0, rt=A0, sa=4), {A0: 1}), 0x1000000000)
        self.assertEqual(self.one(R(0x3A, V0, rt=A0, sa=4), {A0: 1 << 63}), 0x0800000000000000)
        self.assertEqual(self.one(R(0x3B, V0, rt=A0, sa=4), {A0: 1 << 63}), 0xF800000000000000)
        self.assertEqual(self.one(R(0x3E, V0, rt=A0, sa=0), {A0: 0xABCDEF0012345678}), 0xABCDEF00)
        self.assertEqual(self.one(R(0x3F, V0, rt=A0, sa=0), {A0: 0xABCDEF0012345678}), 0xFFFFFFFFABCDEF00)
        self.assertEqual(self.one(R(0x14, V0, rs=A1, rt=A0), {A0: 1, A1: 63}), 1 << 63)
        self.assertEqual(self.one(R(0x16, V0, rs=A1, rt=A0), {A0: 1 << 63, A1: 63}), 1)
        self.assertEqual(self.one(R(0x17, V0, rs=A1, rt=A0), {A0: 1 << 63, A1: 63}), M64)

    def test_multiply_writes_hi_lo_and_rd(self):
        emu = machine([R(0x18, V0, A0, A1)], {A0: -3, A1: 5})
        self.assertEqual((emu.r[V0], emu.lo, emu.hi), (0xFFFFFFFFFFFFFFF1, 0xFFFFFFFFFFFFFFF1, M64))
        emu = machine([R(0x18, V0, A0, A1)], {A0: 0x10000, A1: 0x10000})
        self.assertEqual((emu.r[V0], emu.lo, emu.hi), (0, 0, 1))
        emu = machine([R(0x19, V0, A0, A1)], {A0: M64, A1: 2})      # MULTU 0xffffffff * 2
        self.assertEqual((emu.r[V0], emu.lo, emu.hi), (0xFFFFFFFFFFFFFFFE, 0xFFFFFFFFFFFFFFFE, 1))

    def test_divide_and_hi_lo_moves(self):
        emu = machine([R(0x1A, rs=A0, rt=A1), R(0x12, V0), R(0x10, V1)], {A0: -7, A1: 2})
        self.assertEqual((emu.r[V0], emu.r[V1]), ((-3) & M64, M64))
        emu = machine([R(0x1B, rs=A0, rt=A1), R(0x12, V0), R(0x10, V1)], {A0: 7, A1: 2})
        self.assertEqual((emu.r[V0], emu.r[V1]), (3, 1))
        emu = machine([R(0x11, rs=A0), R(0x13, rs=A1), R(0x10, V0), R(0x12, V1)], {A0: 77, A1: 88})
        self.assertEqual((emu.r[V0], emu.r[V1]), (77, 88))
        with self.assertRaises(CpuTrap):                    # no defined result: stop
            machine([R(0x1A, rs=A0, rt=A1)], {A0: 9, A1: 0})
        emu = machine([R(0x1A, rs=A0, rt=A1)], {A0: 9, A1: 0}, run=False)
        emu.div_zero = 'r5900'                              # opt in to the reported values
        emu.call(BASE)
        self.assertTrue(emu.notes and 'divide by zero' in emu.notes[0])
        self.assertEqual((emu.lo, emu.hi), (M64, 9))

    def test_second_hi_lo_pair_and_madd(self):
        emu = machine([MMI(0x18, V0, A0, A1), MMI(0x12, V1), R(0x12, T0)], {A0: 6, A1: 7})
        self.assertEqual((emu.r[V0], emu.r[V1], emu.r[T0]), (42, 42, 0))   # LO untouched
        emu = machine([MMI(0x1A, rs=A0, rt=A1), MMI(0x12, V0), MMI(0x10, V1)], {A0: 17, A1: 5})
        self.assertEqual((emu.r[V0], emu.r[V1]), (3, 2))
        emu = machine([R(0x13, rs=A2), MMI(0x00, V0, A0, A1)], {A0: 3, A1: 4, A2: 10})
        self.assertEqual((emu.r[V0], emu.lo), (22, 22))

    def test_conditional_moves(self):
        self.assertEqual(self.one(R(0x0A, V0, A0, A1), {A0: 9, A1: 0, V0: 1}), 9)
        self.assertEqual(self.one(R(0x0A, V0, A0, A1), {A0: 9, A1: 2, V0: 1}), 1)
        self.assertEqual(self.one(R(0x0B, V0, A0, A1), {A0: 9, A1: 2, V0: 1}), 9)
        self.assertEqual(self.one(R(0x0B, V0, A0, A1), {A0: 9, A1: 0, V0: 1}), 1)

    def test_register_zero_stays_zero(self):
        emu = machine([addiu(ZERO, ZERO, 5), addiu(V0, ZERO, 1)])
        self.assertEqual((emu.r[0], emu.r[V0]), (0, 1))


class BranchTests(unittest.TestCase):
    def flow(self, branch, regs=None):
        """t0 = 1; <branch +2>; t0 += 10 (delay slot); t0 += 100 (skipped if taken)."""
        emu = machine([addiu(T0, ZERO, 1), branch, addiu(T0, T0, 10), addiu(T0, T0, 100)], regs)
        return emu.r[T0]

    def test_delay_slot_runs_whether_or_not_the_branch_is_taken(self):
        self.assertEqual(self.flow(I(0x04, ZERO, ZERO, 2)), 11)          # BEQ taken
        self.assertEqual(self.flow(I(0x05, ZERO, ZERO, 2)), 111)         # BNE not taken

    def test_likely_branch_skips_the_delay_slot_when_not_taken(self):
        self.assertEqual(self.flow(I(0x14, ZERO, ZERO, 2)), 11)          # BEQL taken
        self.assertEqual(self.flow(I(0x15, ZERO, ZERO, 2)), 101)         # BNEL not taken
        self.assertEqual(self.flow(I(0x16, ZERO, A0, 2), {A0: 1}), 101)  # BLEZL not taken
        self.assertEqual(self.flow(I(0x17, ZERO, A0, 2), {A0: 1}), 11)   # BGTZL taken
        self.assertEqual(self.flow(REGIMM(2, A0, 2), {A0: 1}), 101)      # BLTZL not taken
        self.assertEqual(self.flow(REGIMM(3, A0, 2), {A0: 1}), 11)       # BGEZL taken

    def test_conditions_compare_64_bit_values(self):
        big = 0x0000000080000000      # positive as 64 bits, negative if only 32 were used
        self.assertEqual(self.flow(REGIMM(0, A0, 2), {A0: big}), 111)    # BLTZ not taken
        self.assertEqual(self.flow(REGIMM(1, A0, 2), {A0: big}), 11)     # BGEZ taken
        self.assertEqual(self.flow(I(0x06, ZERO, A0, 2), {A0: big}), 111)   # BLEZ not taken
        self.assertEqual(self.flow(I(0x07, ZERO, A0, 2), {A0: big}), 11)    # BGTZ taken
        self.assertEqual(self.flow(I(0x06, ZERO, A0, 2), {A0: 0}), 11)      # BLEZ taken on 0
        self.assertEqual(self.flow(I(0x07, ZERO, A0, 2), {A0: -1}), 111)    # BGTZ not taken
        self.assertEqual(self.flow(I(0x04, A1, A0, 2), {A0: 0x100000001, A1: 1}), 111)   # BEQ differs
        self.assertEqual(self.flow(I(0x05, A1, A0, 2), {A0: 0x100000001, A1: 1}), 11)

    def test_backward_branch_loop(self):
        # v0 = 0; t0 = 5; do { v0 += t0; t0 -= 1 } while (t0 != 0)
        emu = machine([addiu(V0, ZERO, 0), addiu(T0, ZERO, 5),
                       R(0x21, V0, V0, T0), I(0x05, ZERO, T0, -2), addiu(T0, T0, -1)])
        self.assertEqual(emu.r[V0], 5 + 4 + 3 + 2 + 1 + 0)
        self.assertEqual(emu.r[T0], M64)

    def test_jal_links_past_the_delay_slot_and_is_recorded(self):
        words = [R(0x25, S0, RA, ZERO),           # 0: s0 = ra
                 J(3, BASE + 5 * 4),              # 1: jal 5
                 addiu(T0, ZERO, 5),              # 2: delay slot
                 R(0x08, rs=S0),                  # 3: jr s0
                 addiu(T0, T0, 1000),             # 4: delay slot
                 R(0x25, T1, RA, ZERO),           # 5: t1 = ra
                 JR_RA,                           # 6
                 addiu(T0, T0, 50)]               # 7: delay slot
        emu = machine(words)
        self.assertEqual(emu.r[T0], 1055)
        self.assertEqual(emu.r[T1], BASE + 12)
        self.assertEqual([(c.site, c.target) for c in emu.calls], [(BASE + 4, BASE + 20)])

    def test_jalr_and_plain_jump(self):
        words = [R(0x25, S0, RA, ZERO),
                 R(0x09, RA, rs=T9),              # 1: jalr t9
                 NOP,
                 R(0x08, rs=S0),                  # 3: jr s0
                 NOP,
                 J(2, BASE + 8 * 4),              # 5: j 8
                 addiu(V0, ZERO, 7),              # 6: delay slot
                 addiu(V0, V0, 100),              # 7: skipped
                 JR_RA,                           # 8
                 NOP]
        emu = machine(words, {T9: BASE + 20})
        self.assertEqual(emu.r[V0], 7)
        self.assertEqual(emu.calls[0].target, BASE + 20)

    def test_branch_in_delay_slot_is_refused(self):
        with self.assertRaises(CpuTrap):
            machine([I(0x04, ZERO, ZERO, 2), I(0x04, ZERO, ZERO, 2), NOP, NOP])


class MemoryTests(unittest.TestCase):
    BYTES = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88,
             0x99, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x80]

    def load(self, op, offset):
        return machine([I(op, V0, A0, offset)], {A0: DATA}, data=self.BYTES).r[V0]

    def test_loads_are_little_endian_with_correct_extension(self):
        self.assertEqual(self.load(0x23, 0), 0x44332211)                  # LW
        self.assertEqual(self.load(0x23, 4), 0xFFFFFFFF88776655)          # LW sign-extends
        self.assertEqual(self.load(0x27, 4), 0x88776655)                  # LWU
        self.assertEqual(self.load(0x20, 15), 0xFFFFFFFFFFFFFF80)         # LB
        self.assertEqual(self.load(0x24, 15), 0x80)                       # LBU
        self.assertEqual(self.load(0x21, 6), 0xFFFFFFFFFFFF8877)          # LH
        self.assertEqual(self.load(0x25, 6), 0x8877)                      # LHU
        self.assertEqual(self.load(0x37, 0), 0x8877665544332211)          # LD

    def test_stores(self):
        emu = machine([I(0x28, A1, A0, 0), I(0x29, A1, A0, 2), I(0x2B, A1, A0, 4), I(0x3F, A1, A0, 8)],
                      {A0: DATA, A1: 0x0102030405060708})
        self.assertEqual(emu.mem.read(DATA, 16),
                         bytes([8, 0, 8, 7, 8, 7, 6, 5, 8, 7, 6, 5, 4, 3, 2, 1]))

    def test_unaligned_word_pair(self):
        emu = machine([I(0x22, V0, A0, 4), I(0x26, V0, A0, 1)], {A0: DATA}, data=self.BYTES)   # LWL, LWR
        self.assertEqual(emu.r[V0], 0x55443322)
        emu = machine([I(0x22, V0, A0, 7), I(0x26, V0, A0, 4)], {A0: DATA}, data=self.BYTES)
        self.assertEqual(emu.r[V0], 0xFFFFFFFF88776655)
        emu = machine([I(0x2A, A1, A0, 4), I(0x2E, A1, A0, 1)], {A0: DATA, A1: 0xAABBCCDD},
                      data=self.BYTES)                                                         # SWL, SWR
        self.assertEqual(emu.mem.read(DATA, 6), bytes([0x11, 0xDD, 0xCC, 0xBB, 0xAA, 0x66]))

    def test_unaligned_doubleword_pair(self):
        emu = machine([I(0x1A, V0, A0, 8), I(0x1B, V0, A0, 1)], {A0: DATA}, data=self.BYTES)   # LDL, LDR
        self.assertEqual(emu.r[V0], 0x9988776655443322)
        emu = machine([I(0x2C, A1, A0, 8), I(0x2D, A1, A0, 1)], {A0: DATA, A1: 0x0102030405060708},
                      data=self.BYTES)                                                         # SDL, SDR
        self.assertEqual(emu.mem.read(DATA, 10), bytes([0x11, 8, 7, 6, 5, 4, 3, 2, 1, 0xAA]))

    def test_128_bit_load_and_store(self):
        emu = machine([I(0x1E, T0, A0, 0), I(0x1F, T0, A0, 0x20)], {A0: DATA}, data=self.BYTES)
        self.assertEqual(emu.r[T0], 0x8877665544332211)
        self.assertEqual(emu.rh[T0], 0x80FFEEDDCCBBAA99)
        self.assertEqual(emu.mem.read(DATA + 0x20, 16), bytes(self.BYTES))
        # ordinary instructions leave the upper half alone
        emu = machine([I(0x1E, T0, A0, 0), addiu(T0, ZERO, 1)], {A0: DATA}, data=self.BYTES)
        self.assertEqual((emu.r[T0], emu.rh[T0]), (1, 0x80FFEEDDCCBBAA99))
        # LQ ignores the low four address bits
        emu = machine([I(0x1E, T0, A0, 4)], {A0: DATA}, data=self.BYTES)
        self.assertEqual(emu.r[T0], 0x8877665544332211)

    def test_unaligned_and_unmapped_access_stop_the_run(self):
        with self.assertRaises(CpuTrap):
            machine([I(0x23, V0, A0, 1)], {A0: DATA})
        with self.assertRaises(CpuTrap):
            machine([I(0x29, V0, A0, 1)], {A0: DATA})
        with self.assertRaises(MemoryFault) as caught:
            machine([I(0x23, V0, A0, 0)], {A0: 0x00500000})
        self.assertEqual((caught.exception.addr, caught.exception.pc), (0x00500000, BASE))
        self.assertIn('0x00500000', str(caught.exception))

    def test_auto_map_notes_the_pages_it_creates(self):
        emu = machine([I(0x23, V0, A0, 0)], {A0: 0x00500010}, run=False)
        emu.mem.auto_map = True
        emu.call(BASE)
        self.assertEqual((emu.r[V0], emu.mem.auto_mapped), (0, [0x00500000]))


class FpuTests(unittest.TestCase):
    def op(self, funct, a, b=0, model='ps2'):
        emu = machine([FS(funct, fd=2, fs=0, ft=1)], fregs={0: a, 1: b}, fpu_model=model)
        return emu.f[2]

    def test_exact_arithmetic(self):
        self.assertEqual(self.op(0, f32(1.5), f32(2.25)), f32(3.75))        # ADD
        self.assertEqual(self.op(1, f32(1.5), f32(2.25)), f32(-0.75))       # SUB
        self.assertEqual(self.op(2, f32(1.5), f32(2.5)), f32(3.75))         # MUL
        self.assertEqual(self.op(3, f32(7.0), f32(2.0)), f32(3.5))          # DIV
        self.assertEqual(self.op(0, f32(5.0), f32(-5.0)), 0)                # x - x = +0
        self.assertEqual(self.op(2, f32(0.0), f32(-3.0)), 0x80000000)       # sign of a zero product
        emu = machine([FS(4, fd=2, ft=1)], fregs={1: f32(9.0)})             # SQRT uses ft
        self.assertEqual(emu.f[2], f32(3.0))
        emu = machine([FS(4, fd=2, ft=1)], fregs={1: f32(2.0)})
        self.assertEqual(emu.f[2], 0x3FB504F3)
        self.assertEqual(self.op(0x16, f32(1.0), f32(4.0)), f32(0.5))       # RSQRT = fs / sqrt(ft)

    def test_results_are_truncated_not_rounded(self):
        self.assertEqual(self.op(3, f32(1.0), f32(3.0)), 0x3EAAAAAA)
        self.assertEqual(self.op(3, f32(1.0), f32(3.0), 'nearest'), 0x3EAAAAAB)
        # (1 + 2^-23) * 1.5 = 1.5 + 2^-23 + 2^-24: exactly half way between two singles
        self.assertEqual(self.op(2, 0x3F800001, f32(1.5)), 0x3FC00001)
        self.assertEqual(self.op(2, 0x3F800001, f32(1.5), 'nearest'), 0x3FC00002)
        # 1 + 1.5 * 2^-24
        self.assertEqual(self.op(0, f32(1.0), 0x33C00000), 0x3F800000)
        self.assertEqual(self.op(0, f32(1.0), 0x33C00000, 'chop'), 0x3F800000)
        self.assertEqual(self.op(0, f32(1.0), 0x33C00000, 'nearest'), 0x3F800001)
        # 1 - 2^-24 is representable in every model
        for model in ee_emu.FPU_MODELS:
            self.assertEqual(self.op(1, f32(1.0), 0x33800000, model), 0x3F7FFFFF)

    def test_adder_models_differ_only_for_far_apart_operands(self):
        tiny = 0x31000000                                   # 2^-30
        self.assertEqual(self.op(1, f32(1.0), tiny, 'ps2'), 0x3F800000)    # operand ignored
        self.assertEqual(self.op(1, f32(1.0), tiny, 'ps2g1'), 0x3F800000)  # operand ignored
        self.assertEqual(self.op(1, tiny, f32(1.0), 'ps2g1'), 0xBF800000)  # either order
        self.assertEqual(self.op(1, f32(1.0), tiny, 'chop'), 0x3F7FFFFF)   # exact, truncated
        self.assertEqual(self.op(1, f32(1.0), tiny, 'nearest'), 0x3F800000)
        self.assertEqual(self.op(0, f32(1.0), tiny, 'ps2'), 0x3F800000)
        self.assertEqual(self.op(0, f32(1.0), tiny, 'chop'), 0x3F800000)
        # 1 - 1.5 * 2^-24 lies between two singles below 1.  Exactly, or with six extra
        # bits, it truncates to 1 - 2 * 2^-24; with one extra bit the subtrahend has lost
        # its lowest bit and the result is 1 - 2^-24.
        b = 0x33C00000
        self.assertEqual(self.op(1, f32(1.0), b, 'chop'), 0x3F7FFFFE)
        self.assertEqual(self.op(1, f32(1.0), b, 'ps2'), 0x3F7FFFFE)
        self.assertEqual(self.op(1, f32(1.0), b, 'ps2g1'), 0x3F7FFFFF)
        # close operands: every model agrees
        for model in ee_emu.FPU_MODELS:
            self.assertEqual(self.op(0, f32(1.5), f32(2.25), model), f32(3.75))
            self.assertEqual(self.op(1, f32(100.0), f32(99.5), model), f32(0.5))

    def test_division_rounding_switch(self):
        emu = machine([FS(3, 2, 0, 1), FS(4, 3, ft=4)], fregs={0: f32(1.0), 1: f32(3.0), 4: f32(3.0)},
                      run=False)
        emu.fpu_div_nearest = True
        emu.call(BASE)
        self.assertEqual(emu.f[2], 0x3EAAAAAB)              # 1/3 rounded to nearest
        self.assertEqual(emu.f[3], 0x3FDDB3D7)              # sqrt(3) = 1.7320508, bit after is 0
        emu.fpu_div_nearest = False
        emu.call(BASE)
        self.assertEqual(emu.f[2], 0x3EAAAAAA)
        self.assertEqual(emu.f[3], 0x3FDDB3D7)

    def test_no_infinity_nan_or_denormals(self):
        fmax = 0x7FFFFFFF
        self.assertEqual(self.op(0, 0x7F7FFFFF, 0x7F7FFFFF), fmax)          # exponent 255 is a number
        emu = machine([FS(0, 2, 0, 1)], fregs={0: fmax, 1: fmax})
        self.assertEqual(emu.f[2], fmax)                                    # overflow clamps
        self.assertTrue(emu.fcr31 & 0x8000 and emu.fcr31 & 0x10)
        self.assertEqual(self.op(2, 0x7F000000, f32(2.0)), 0x7F800000)      # 2^128, not infinity
        self.assertEqual(self.op(2, 0x7F000000, f32(4.0)), fmax)
        self.assertEqual(self.op(2, 0xFF000000, f32(4.0)), 0xFFFFFFFF)
        self.assertEqual(self.op(2, 0x7F800000, f32(0.5)), 0x7F000000)      # usable as an operand
        emu = machine([FS(2, 2, 0, 1)], fregs={0: 0x00800000, 1: f32(0.5)})
        self.assertEqual(emu.f[2], 0)                                       # underflow gives zero
        self.assertTrue(emu.fcr31 & 0x4000 and emu.fcr31 & 0x8)
        self.assertEqual(self.op(0, 0x00400000, f32(1.0)), f32(1.0))        # denormal operand is zero
        self.assertEqual(self.op(2, 0x00400000, 0x7F000000), 0)

    def test_divide_by_zero_gives_the_largest_number_and_a_flag(self):
        emu = machine([FS(3, 2, 0, 1)], fregs={0: f32(1.0), 1: 0})
        self.assertEqual(emu.f[2], 0x7FFFFFFF)
        self.assertTrue(emu.fcr31 & 0x10000 and emu.fcr31 & 0x20)
        emu = machine([FS(3, 2, 0, 1)], fregs={0: f32(-1.0), 1: 0})
        self.assertEqual(emu.f[2], 0xFFFFFFFF)
        emu = machine([FS(3, 2, 0, 1)], fregs={0: 0, 1: 0})
        self.assertEqual(emu.f[2], 0x7FFFFFFF)
        self.assertTrue(emu.fcr31 & 0x20000 and emu.fcr31 & 0x40)

    def test_sign_operations_and_moves(self):
        emu = machine([FS(5, 2, 0), FS(7, 3, 0), FS(6, 4, 0)], fregs={0: f32(-2.5)})
        self.assertEqual((emu.f[2], emu.f[3], emu.f[4]), (f32(2.5), f32(2.5), f32(-2.5)))
        emu = machine([mtc1(A0, 5), mfc1(V0, 5)], {A0: 0xC0000000})
        self.assertEqual((emu.f[5], emu.r[V0]), (0xC0000000, 0xFFFFFFFFC0000000))

    def test_conversions(self):
        def to_int(raw):
            return machine([FS(0x24, 2, 0)], fregs={0: raw}).f[2]
        self.assertEqual(to_int(f32(2.9)), 2)
        self.assertEqual(to_int(f32(-2.9)), 0xFFFFFFFE)
        self.assertEqual(to_int(f32(0.99)), 0)
        self.assertEqual(to_int(0x4F000000), 0x7FFFFFFF)            # 2^31 saturates
        self.assertEqual(to_int(0xCF800000), 0x80000000)            # -2^32 saturates
        self.assertEqual(to_int(0xCF000000), 0x80000000)            # -2^31

        def from_int(value, model='ps2'):
            word = (0x11 << 26) | (0x14 << 21) | (0 << 11) | (2 << 6) | 0x20   # CVT.S.W f2, f0
            return machine([word], fregs={0: value & 0xFFFFFFFF}, fpu_model=model).f[2]
        self.assertEqual(from_int(7), f32(7.0))
        self.assertEqual(from_int(-1), f32(-1.0))
        self.assertEqual(from_int(0), 0)
        self.assertEqual(from_int(16777219), 0x4B800001)            # 2^24 + 3 truncates to 2^24 + 2
        self.assertEqual(from_int(16777219, 'nearest'), 0x4B800002)

    def test_compare_and_branch(self):
        def taken(compare, a, b, code):
            words = [addiu(T0, ZERO, 1), FS(compare, fs=0, ft=1), BC1(code, 2),
                     addiu(T0, T0, 10), addiu(T0, T0, 100)]
            return machine(words, fregs={0: a, 1: b}).r[T0]
        one, two, nzero = f32(1.0), f32(2.0), 0x80000000
        self.assertEqual(taken(0x34, one, two, 1), 11)       # C.LT true, BC1T taken
        self.assertEqual(taken(0x34, two, one, 1), 111)
        self.assertEqual(taken(0x34, two, one, 0), 11)       # BC1F taken
        self.assertEqual(taken(0x36, one, one, 1), 11)       # C.LE
        self.assertEqual(taken(0x32, nzero, 0, 1), 11)       # -0 == +0
        self.assertEqual(taken(0x34, nzero, 0, 1), 111)      # -0 < +0 is false
        self.assertEqual(taken(0x34, f32(-2.0), f32(-1.0), 1), 11)
        self.assertEqual(taken(0x32, one, two, 3), 101)      # BC1TL not taken: slot skipped
        self.assertEqual(taken(0x32, one, two, 2), 11)       # BC1FL taken
        self.assertEqual(taken(0x30, one, one, 0), 11)       # C.F always false

    def test_min_max_and_accumulator(self):
        self.assertEqual(self.op(0x28, f32(-1.0), f32(2.0)), f32(2.0))
        self.assertEqual(self.op(0x29, f32(-1.0), f32(2.0)), f32(-1.0))
        # ADDA acc = 1 + 2; MADD f2 = acc + 2 * 4; MSUB f3 = acc - 2 * 4
        emu = machine([FS(0x18, fs=0, ft=1), FS(0x1C, 2, 1, 3), FS(0x1D, 4, 1, 3)],
                      fregs={0: f32(1.0), 1: f32(2.0), 3: f32(4.0)})
        self.assertEqual((emu.acc, emu.f[2], emu.f[4]), (f32(3.0), f32(11.0), f32(-5.0)))

    def test_float_load_store_and_arguments(self):
        emu = machine([I(0x31, 1, A0, 0), I(0x39, 1, A0, 8)], {A0: DATA},
                      data=struct.pack('<f', 6.5))                          # LWC1, SWC1
        self.assertEqual(emu.mem.f32(DATA + 8), 6.5)
        emu = EE()
        emu.load_words(BASE, [FS(0, 0, 12, 13), JR_RA, NOP])                # f0 = f12 + f13
        emu.call(BASE, fargs=(1.25, 2.5))
        self.assertEqual(emu.fget(0), 3.75)

    def test_multiplier_worst_case_bias(self):
        emu = machine([FS(2, 2, 0, 1)], fregs={0: 0x3F800001, 1: f32(1.5)}, run=False)
        emu.fpu_mul_bias = True
        emu.call(BASE)
        self.assertEqual(emu.f[2], 0x3FC00000)
        emu = machine([FS(2, 2, 0, 1)], fregs={0: f32(1.5), 1: f32(2.5)}, run=False)
        emu.fpu_mul_bias = True
        emu.call(BASE)
        self.assertEqual(emu.f[2], f32(3.75))            # an exact product is left alone


class MmiTests(unittest.TestCase):
    A = 0x0011223344556677_8899AABBCCDDEEFF
    B = 0x0102030405060708_090A0B0C0D0E0F10

    def q(self, word, a=None, b=None, sa_reg=None):
        emu = machine([word], run=False)
        a = self.A if a is None else a
        b = self.B if b is None else b
        emu.r[A0], emu.rh[A0] = a & M64, a >> 64
        emu.r[A1], emu.rh[A1] = b & M64, b >> 64
        if sa_reg is not None:
            emu.sa = sa_reg
        emu.call(BASE)
        return (emu.rh[V0] << 64) | emu.r[V0]

    def test_lane_arithmetic(self):
        self.assertEqual(self.q(MMI(0x08, V0, A0, A1, 0x04), 0x0001FFFF, 0x00010001), 0x00020000)   # PADDH wraps
        self.assertEqual(self.q(MMI(0x08, V0, A0, A1, 0x01), 0x0000000100000000, 0x1), 0x00000001FFFFFFFF)  # PSUBW
        self.assertEqual(self.q(MMI(0x08, V0, A0, A1, 0x09), 0x0100, 0x0001), 0x01FF)               # PSUBB
        self.assertEqual(self.q(MMI(0x08, V0, A0, A1, 0x14), 0x7FFF8000, 0x0001FFFF), 0x7FFF8000)   # PADDSH saturates
        self.assertEqual(self.q(MMI(0x08, V0, A0, A1, 0x15), 0x80007FFF, 0x0001FFFF), 0x80007FFF)   # PSUBSH saturates
        self.assertEqual(self.q(MMI(0x28, V0, A0, A1, 0x10), 0xFFFFFFFF00000005, 0x0000000200000006),
                         0xFFFFFFFF0000000B)                                                         # PADDUW
        self.assertEqual(self.q(MMI(0x08, V0, A0, A1, 0x07), 0x8000_0005, 0x0001_0003), 0x0001_0005)  # PMAXH signed
        self.assertEqual(self.q(MMI(0x28, V0, A0, A1, 0x07), 0x8000_0005, 0x0001_0003), 0x8000_0003)  # PMINH signed
        self.assertEqual(self.q(MMI(0x08, V0, A0, A1, 0x02), 0x00000002_FFFFFFFF, 0x00000001_00000000),
                         0xFFFFFFFF_00000000)                                                        # PCGTW signed
        self.assertEqual(self.q(MMI(0x08, V0, A0, A1, 0x06), 0x0002_FFFF, 0x0001_0000), 0xFFFF_0000)  # PCGTH
        # PCEQH: the six upper lanes are 0 == 0, so they are all ones too
        self.assertEqual(self.q(MMI(0x28, V0, A0, A1, 0x06), 0x0002_0007, 0x0001_0007),
                         ((1 << 128) - 1) ^ 0xFFFF_0000)

    def test_logic_and_copies(self):
        ones = (1 << 128) - 1
        self.assertEqual(self.q(MMI(0x09, V0, A0, A1, 0x12)), self.A & self.B)             # PAND
        self.assertEqual(self.q(MMI(0x29, V0, A0, A1, 0x12)), self.A | self.B)             # POR
        self.assertEqual(self.q(MMI(0x09, V0, A0, A1, 0x13)), self.A ^ self.B)             # PXOR
        self.assertEqual(self.q(MMI(0x29, V0, A0, A1, 0x13)), (self.A | self.B) ^ ones)    # PNOR
        # PCPYLD: rd = rs.low : rt.low      PCPYUD: rd = rt.high : rs.high
        self.assertEqual(self.q(MMI(0x09, V0, A0, A1, 0x0E)), 0x8899AABBCCDDEEFF_090A0B0C0D0E0F10)
        self.assertEqual(self.q(MMI(0x29, V0, A0, A1, 0x0E)), 0x0102030405060708_0011223344556677)
        self.assertEqual(self.q(MMI(0x29, V0, A0, A1, 0x1B)), 0x0708070807080708_0F100F100F100F10)  # PCPYH

    def test_interleave_and_pack(self):
        self.assertEqual(self.q(MMI(0x08, V0, A0, A1, 0x12)), 0x8899AABB_090A0B0C_CCDDEEFF_0D0E0F10)   # PEXTLW
        self.assertEqual(self.q(MMI(0x08, V0, A0, A1, 0x16)), 0x8899_090A_AABB_0B0C_CCDD_0D0E_EEFF_0F10)  # PEXTLH
        self.assertEqual(self.q(MMI(0x08, V0, A0, A1, 0x1A)),
                         0x8809_990A_AA0B_BB0C_CC0D_DD0E_EE0F_FF10)                                    # PEXTLB
        self.assertEqual(self.q(MMI(0x28, V0, A0, A1, 0x1A)),
                         0x0001_1102_2203_3304_4405_5506_6607_7708)                                    # PEXTUB
        self.assertEqual(self.q(MMI(0x08, V0, A0, A1, 0x17)), 0x2233_6677_AABB_EEFF_0304_0708_0B0C_0F10)  # PPACH
        self.assertEqual(self.q(MMI(0x08, V0, A0, A1, 0x1B)),
                         0x11_33_55_77_99_BB_DD_FF_02_04_06_08_0A_0C_0E_10)                            # PPACB

    def test_lane_shifts(self):
        value = 0x8001_0002_0004_0008_8001_0002_0004_0008
        self.assertEqual(self.q(MMI(0x34, V0, rt=A1, sa=1), b=value),
                         0x0002_0004_0008_0010_0002_0004_0008_0010)                 # PSLLH
        self.assertEqual(self.q(MMI(0x36, V0, rt=A1, sa=1), b=value),
                         0x4000_0001_0002_0004_4000_0001_0002_0004)                 # PSRLH
        self.assertEqual(self.q(MMI(0x37, V0, rt=A1, sa=1), b=value),
                         0xC000_0001_0002_0004_C000_0001_0002_0004)                 # PSRAH
        self.assertEqual(self.q(MMI(0x3F, V0, rt=A1, sa=4), b=0x80000000_00000010),
                         0xF8000000_00000001)                                       # PSRAW

    def test_funnel_shift_and_leading_bits(self):
        # QFSRV: (rs:rt) >> SA, low 128 bits; SA is set in bytes by MTSAB
        emu = machine([REGIMM(0x18, ZERO, 3), MMI(0x28, V0, A0, A1, 0x1B)], run=False)
        emu.r[A0], emu.rh[A0] = self.A & M64, self.A >> 64
        emu.r[A1], emu.rh[A1] = self.B & M64, self.B >> 64
        emu.call(BASE)
        expected = (((self.A << 128) | self.B) >> 24) & ((1 << 128) - 1)
        self.assertEqual((emu.rh[V0] << 64) | emu.r[V0], expected)
        # PLZCW: number of leading sign bits minus one, per 32-bit word
        emu = machine([MMI(0x04, V0, rs=A0)], {A0: 0xFFFF0000_00000001})
        self.assertEqual(emu.r[V0], 0x0000000F_0000001E)

    def test_remaining_lane_operations(self):
        ones = (1 << 128) - 1
        cases = [
            # (word, rs value, rt value, expected rd), all worked out by hand
            (MMI(0x08, V0, A0, A1, 0x00), 0xFFFFFFFF_00000001, 0x00000001_00000002, 0x00000000_00000003),  # PADDW
            (MMI(0x08, V0, A0, A1, 0x05), 0x0000_0005, 0x0001_0007, 0xFFFF_FFFE),                          # PSUBH
            (MMI(0x08, V0, A0, A1, 0x08), 0xFF_10, 0x02_F0, 0x01_00),                                      # PADDB
            (MMI(0x08, V0, A0, A1, 0x0A), 0x7F_80_01, 0x00_7F_01, 0xFF_00_00),                             # PCGTB
            (MMI(0x08, V0, A0, A1, 0x03), 0xFFFFFFFF_00000005, 0x00000000_00000007, 0x00000000_00000007),  # PMAXW
            (MMI(0x28, V0, A0, A1, 0x03), 0xFFFFFFFF_00000005, 0x00000000_00000007, 0xFFFFFFFF_00000005),  # PMINW
            (MMI(0x08, V0, A0, A1, 0x10), 0x7FFFFFFF_80000000, 0x00000001_FFFFFFFF, 0x7FFFFFFF_80000000),  # PADDSW
            (MMI(0x08, V0, A0, A1, 0x11), 0x80000000_7FFFFFFF, 0x00000001_FFFFFFFF, 0x80000000_7FFFFFFF),  # PSUBSW
            (MMI(0x08, V0, A0, A1, 0x18), 0x7F_80, 0x01_FF, 0x7F_80),                                      # PADDSB
            (MMI(0x08, V0, A0, A1, 0x19), 0x80_7F, 0x01_FF, 0x80_7F),                                      # PSUBSB
            (MMI(0x08, V0, A0, A1, 0x13), self.A, self.B, 0x44556677_CCDDEEFF_05060708_0D0E0F10),          # PPACW
            (MMI(0x28, V0, A0, A1, 0x02), 0x00000005_00000007, 0x00000005_00000008,
             ones ^ 0xFFFFFFFF),                                                                           # PCEQW
            (MMI(0x28, V0, A0, A1, 0x0A), 0x11_22, 0x11_23, ones ^ 0xFF),                                  # PCEQB
            (MMI(0x28, V0, A0, A1, 0x11), 0x00000001_00000005, 0x00000002_00000003, 0x00000000_00000002),  # PSUBUW
            (MMI(0x28, V0, A0, A1, 0x14), 0xFFFF_0001, 0x0001_0001, 0xFFFF_0002),                          # PADDUH
            (MMI(0x28, V0, A0, A1, 0x15), 0x0001_0005, 0x0002_0003, 0x0000_0002),                          # PSUBUH
            (MMI(0x28, V0, A0, A1, 0x18), 0xFF_01, 0x01_01, 0xFF_02),                                      # PADDUB
            (MMI(0x28, V0, A0, A1, 0x19), 0x01_05, 0x02_03, 0x00_02),                                      # PSUBUB
            (MMI(0x28, V0, A0, A1, 0x12), self.A, self.B, 0x00112233_01020304_44556677_05060708),          # PEXTUW
            (MMI(0x28, V0, A0, A1, 0x16), self.A, self.B, 0x0011_0102_2233_0304_4455_0506_6677_0708),      # PEXTUH
            (MMI(0x3C, V0, rt=A1, sa=4), 0, 0x80000001_00000003, 0x00000010_00000030),                     # PSLLW
            (MMI(0x3E, V0, rt=A1, sa=4), 0, 0x80000000_00000010, 0x08000000_00000001),                     # PSRLW
        ]
        for word, a, b, expected in cases:
            with self.subTest(word='%08x' % word):
                self.assertEqual(self.q(word, a, b), expected)

    def test_remaining_hi_lo_operations(self):
        # MADDU: (HI:LO) = 5 + 0xffffffff * 2 = 0x2_00000003
        emu = machine([R(0x13, rs=A2), MMI(0x01, V0, A0, A1)], {A0: 0xFFFFFFFF, A1: 2, A2: 5})
        self.assertEqual((emu.r[V0], emu.lo, emu.hi), (3, 3, 2))
        emu = machine([MMI(0x19, V0, A0, A1)], {A0: M64, A1: 2})                 # MULTU1
        self.assertEqual((emu.r[V0], emu.lo1, emu.hi1, emu.lo), (0xFFFFFFFFFFFFFFFE, 0xFFFFFFFFFFFFFFFE, 1, 0))
        emu = machine([MMI(0x1B, rs=A0, rt=A1), MMI(0x12, V0), MMI(0x10, V1)], {A0: 0xFFFFFFFF, A1: 2})   # DIVU1
        self.assertEqual((emu.r[V0], emu.r[V1]), (0x7FFFFFFF, 1))
        emu = machine([MMI(0x11, rs=A0), MMI(0x13, rs=A1), MMI(0x10, V0), MMI(0x12, V1), R(0x10, T0)],
                      {A0: 77, A1: 88})                                          # MTHI1, MTLO1
        self.assertEqual((emu.r[V0], emu.r[V1], emu.r[T0]), (77, 88, 0))

    def test_every_listed_mmi_instruction_is_decoded(self):
        self.assertEqual(len(ee_emu.MMI_IMPLEMENTED), len(set(ee_emu.MMI_IMPLEMENTED)))
        self.assertEqual(len(ee_emu.MMI_IMPLEMENTED), 62)

    def test_unlisted_mmi_instruction_stops(self):
        with self.assertRaises(UnimplementedInstruction):
            machine([MMI(0x09, V0, A0, A1, 0x1C)])                    # PMULTH


class ControlTests(unittest.TestCase):
    def test_unimplemented_instruction_names_address_and_word(self):
        word = 0x4A000000 | 0x123                                   # a COP2 operation
        with self.assertRaises(UnimplementedInstruction) as caught:
            machine([NOP, word])
        self.assertEqual((caught.exception.pc, caught.exception.word), (BASE + 4, word))
        self.assertIn('0x%08x' % (BASE + 4), str(caught.exception))
        self.assertIn('0x%08x' % word, str(caught.exception))
        with self.assertRaises(UnimplementedInstruction):
            machine([0x42000018])                                   # ERET

    def test_syscall_and_break_stop_unless_handled(self):
        with self.assertRaises(CpuTrap):
            machine([R(0x0C)])
        with self.assertRaises(CpuTrap):
            machine([R(0x0D)])
        emu = machine([addiu(V1, ZERO, 60), R(0x0C)], run=False)
        seen = []
        emu.syscall_handler = lambda e: seen.append(e.r[V1])
        emu.call(BASE)
        self.assertEqual(seen, [60])

    def callee_program(self):
        """v0 = callee(a0 + 1) + 1000, where callee(x) = x * 2 and stores x at DATA."""
        return [R(0x25, S0, RA, ZERO),          # 0: s0 = ra
                J(3, BASE + 6 * 4),             # 1: jal callee
                addiu(A0, A0, 1),               # 2: delay slot sets the argument
                R(0x08, rs=S0),                 # 3: jr s0
                addiu(V0, V0, 1000),            # 4
                NOP,                            # 5
                I(0x0F, T0, 0, DATA >> 16),     # 6: callee: t0 = DATA
                I(0x2B, A0, T0, 0),             # 7: sw a0, 0(t0)
                JR_RA,                          # 8
                R(0x21, V0, A0, A0)]            # 9: v0 = a0 + a0

    def test_call_runs_callee_for_real_by_default(self):
        emu = machine(self.callee_program(), {A0: 20})
        self.assertEqual(emu.r[V0], 1042)
        self.assertEqual(emu.mem.u32(DATA), 21)
        self.assertEqual(emu.writes, [(BASE + 28, DATA, 4, 21)])
        self.assertEqual(emu.calls[0].args[0], 21)          # the argument as set by the delay slot
        self.assertFalse(emu.calls[0].stubbed)

    def test_stub_replaces_a_callee_and_sees_its_arguments(self):
        emu = machine(self.callee_program(), {A0: 20}, run=False)
        seen = []
        emu.stub(BASE + 24, ret=7, function=lambda e: seen.append(e.r[A0]), name='callee')
        emu.call(BASE)
        self.assertEqual((emu.r[V0], seen, emu.writes), (1007, [21], []))
        self.assertEqual((emu.calls[0].stubbed, emu.calls[0].ret, emu.calls[0].name), (True, 7, 'callee'))
        emu.stub(BASE + 24, function=lambda e: e.r[A0] * 3)     # the function's result is returned
        emu.r[A0] = 1
        emu.call(BASE)
        self.assertEqual(emu.r[V0], 1006)

    def test_follow_set_stubs_every_other_call(self):
        emu = machine(self.callee_program(), {A0: 20}, run=False)
        emu.follow = set()
        emu.default_ret = 5
        emu.call(BASE)
        self.assertEqual((emu.r[V0], emu.writes), (1005, []))
        self.assertTrue(emu.calls[0].stubbed)
        emu.follow = {BASE + 24}
        emu.reset_log()
        emu.r[A0] = 20
        emu.call(BASE)
        self.assertEqual(emu.r[V0], 1042)
        self.assertFalse(emu.calls[0].stubbed)

    def test_hook_probe_and_redirect(self):
        emu = machine(self.callee_program(), {A0: 20}, run=False)
        visits = []
        emu.hook(BASE + 28, lambda e: visits.append(e.r[A0]))       # probe: execution continues
        emu.call(BASE)
        self.assertEqual((visits, emu.r[V0]), ([21], 1042))
        emu.hook(BASE + 28, lambda e: e.jump(BASE + 32))            # skip the store
        emu.mem.w32(DATA, 0)
        emu.r[A0] = 20
        emu.call(BASE)
        self.assertEqual((emu.mem.u32(DATA), emu.r[V0]), (0, 1042))

    def test_patch_and_unpatch(self):
        emu = machine(self.callee_program(), {A0: 20}, run=False)
        emu.patch(BASE + 4, NOP)                                    # remove the call
        emu.r[V0] = 3
        emu.call(BASE)
        self.assertEqual((emu.r[V0], emu.calls), (1003, []))
        emu.unpatch()
        self.assertEqual(emu.mem.u32(BASE + 4), J(3, BASE + 24))

    def test_pnach_sections(self):
        text = ('gametitle=test\n\n[First: remove call]\n// was: something\n'
                'patch=1,EE,%08X,word,00000000\n\n[Second]\npatch=1,EE,%08X,word,24020063\n'
                % (BASE + 4, BASE + 16))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'test.pnach')
            with open(path, 'w', encoding='utf-8') as out:
                out.write(text)
            sections = ee_emu.parse_pnach(path)
            self.assertEqual([title for title, _ in sections], ['First: remove call', 'Second'])
            emu = machine(self.callee_program(), {A0: 20, V0: 3}, run=False)
            self.assertEqual(emu.apply_pnach(path, 'remove call'), 1)
            emu.call(BASE)
            self.assertEqual(emu.r[V0], 1003)
            self.assertEqual(emu.apply_pnach(path), 2)
            emu.call(BASE)
            self.assertEqual(emu.r[V0], 99)                         # delay slot is now li v0, 99

    def test_run_until_and_breakpoints(self):
        emu = machine([addiu(V0, ZERO, 1), addiu(V0, V0, 1), addiu(V0, V0, 1), addiu(V0, V0, 1)],
                      run=False)
        self.assertEqual(emu.run(start=BASE + 4, until={BASE + 12}), 'stop')
        self.assertEqual((emu.pc, emu.r[V0]), (BASE + 12, 2))       # started at the second word
        emu.breakpoints.add(BASE + 8)
        emu.r[31] = emu.RETURN_ADDR
        self.assertEqual(emu.run(start=BASE), 'stop')
        self.assertEqual(emu.pc, BASE + 8)
        emu.breakpoints.clear()
        self.assertEqual(emu.run(), 'return')
        self.assertEqual(emu.r[V0], 4)

    def test_stack_writes_are_not_recorded(self):
        emu = machine([addiu(SP, SP, -16), I(0x3F, A0, SP, 0), I(0x37, V0, SP, 0),
                       I(0x0F, T0, 0, DATA >> 16), I(0x28, A0, T0, 3), addiu(SP, SP, 16)], {A0: 0x55})
        self.assertEqual(emu.r[V0], 0x55)
        self.assertEqual(emu.writes, [(BASE + 16, DATA + 3, 1, 0x55)])
        self.assertEqual(emu.write_summary(), [(DATA + 3, 1, 0x55, BASE + 16)])

    def test_step_limit(self):
        with self.assertRaises(StepLimit):
            emu = machine([I(0x04, ZERO, ZERO, -1), NOP], run=False)
            emu.call(BASE, max_steps=1000)

    def test_cop0_register_file_and_interrupt_bit(self):
        mtc0 = (0x10 << 26) | (4 << 21) | (A0 << 16) | (12 << 11)
        mfc0 = (0x10 << 26) | (V0 << 16) | (12 << 11)
        emu = machine([mtc0, 0x42000038, mfc0, 0x42000039, (0x10 << 26) | (V1 << 16) | (12 << 11)],
                      {A0: 1})
        self.assertEqual((emu.r[V0], emu.r[V1]), (0x10001, 1))

    def test_report_mentions_calls_and_writes(self):
        emu = machine(self.callee_program(), {A0: 20})
        text = emu.report()
        self.assertIn('calls: 1', text)
        self.assertIn('0x%08x' % DATA, text)


def synthetic_elf(code_words, vaddr=0x00100000, bss=0x100):
    """A minimal 32-bit little-endian MIPS ELF with one loadable segment."""
    code = struct.pack('<%dI' % len(code_words), *code_words)
    header = bytearray(52)
    header[:7] = b'\x7fELF\x01\x01\x01'
    struct.pack_into('<HHIIIIIHHHHHH', header, 16, 2, 8, 1, vaddr, 52, 0, 0, 52, 32, 1, 0, 0, 0)
    program = struct.pack('<8I', 1, 52 + 32, vaddr, vaddr, len(code), len(code) + bss, 7, 16)
    return bytes(header) + program + code


class ElfAndCommandLineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = os.path.join(self.directory.name, 'synthetic.elf')
        # v0 = a0 + a1; store it in the zero-filled area behind the code
        words = [R(0x21, V0, A0, A1), I(0x0F, T0, 0, 0x0010), JR_RA, I(0x2B, V0, T0, 0x40)]
        with open(self.path, 'wb') as out:
            out.write(synthetic_elf(words))

    def test_load_and_call(self):
        emu = EE(self.path)
        self.assertEqual(emu.entry, 0x00100000)
        self.assertEqual(emu.call(0x00100000, 3, 4), 7)
        self.assertEqual(emu.mem.u32(0x00100040), 7)

    def test_rejects_a_file_that_is_not_an_elf(self):
        bad = os.path.join(self.directory.name, 'bad.bin')
        with open(bad, 'wb') as out:
            out.write(b'not an elf at all')
        with self.assertRaises(ValueError):
            EE(bad)

    def run_cli(self, *argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = ee_emu.main([self.path] + list(argv))
        return code, buffer.getvalue()

    def test_command_line_call(self):
        code, text = self.run_cli('call', '100000', '0x10', '5')
        self.assertEqual(code, 0)
        self.assertIn('v0 = 0x0000000000000015', text)
        self.assertIn('0x00100040', text)

    def test_command_line_patch_and_run(self):
        code, text = self.run_cli('run', '100000', '100008', '--reg', 'a0=2', '--reg', 'a1=3',
                                  '--patch', '100000=00851023')        # subu v0, a0, a1
        self.assertEqual(code, 0)
        self.assertIn('stopped at 0x00100008', text)
        self.assertIn('v0 = 0xffffffffffffffff', text)

    def test_command_line_reports_a_stop(self):
        code, text = self.run_cli('call', '100000', '--patch', '100004=4a000000')
        self.assertEqual(code, 1)
        self.assertIn('STOPPED: unimplemented instruction at 0x00100004', text)


if __name__ == '__main__':
    unittest.main()
