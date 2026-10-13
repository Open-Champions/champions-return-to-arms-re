#!/usr/bin/env python3
"""vu0ref.py - vector unit 0 for the instruction interpreter (tools/ee_emu.py has none).

The game's main-processor code uses the unit through six COP2 forms - QMTC2, QMFC2, CTC2,
CFC2, LQC2, SQC2 - and VCALLMS, which runs a microprogram to its end; its one microprogram
(77 instructions, entered at 2 and 4 from anim_buildPose) uses a handful of upper
instructions and five lower ones.  The translation's side of this is tools/recomp/rt/vu0.h,
which computes with the host's floats.  This file is the other side for the function-by-
function proof: the same register moves and the same microprogram instructions written
down a second time, with the arithmetic done in exact integer arithmetic (softf.py: IEEE
single precision rounded toward zero, denormals flushed - the mode the runtime sets, and
what the Play! emulator does for the vector units).  No floating point is used.

Two models of an operand whose exponent field is 255 (infinity or NaN to a host):

  'host'     softf's: the pattern is read as the number its bits spell (an exponent like
             any other), a result too large becomes the largest finite number.  Agrees
             with rt/vu0.h on every finite operand (arith.py vu: 225 forms); on exponent-
             255 operands vu0.h hands the host's NaN or infinity on instead.
  'console'  the unit has no NaN and no infinity: an operand with exponent 255 counts as
             the largest number of its sign, one with exponent 0 as zero, before the
             operation (the rule tools/recomp/render/vu1_step.h follows for VU1, and the
             rule proposed for vu0.h in rt-proposed.patch); MAX and MINI compare the two
             patterns as sign and magnitude and hand one on unchanged.

Vu0.cop2(emu, word) executes one COP2 / LQC2 / SQC2 instruction of the main processor
against an ee_emu.EE; Vu0.run(pc) runs a microprogram.  An instruction the game's
program does not use raises Unimplemented - nothing is guessed.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import softf                                    # noqa: E402

M32, M64 = 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF
ONE = 0x3F800000
MICRO, MEM = 0x11000000, 0x11004000
STATE = struct.Struct('<128I16H4I2I32I4096s4096s')     # vf, vi, acc, q, i, control, micro, mem (proof_rt.cpp)


class Unimplemented(Exception):
    pass


def sx32(v):
    v &= M32
    return v | ~M32 & M64 if v & 0x80000000 else v


class Vu0:
    def __init__(self, model='host'):
        self.model = model
        self.vf = [[0, 0, 0, 0] for _ in range(32)]     # raw patterns: x y z w
        self.vf[0][3] = ONE
        self.vi = [0] * 16
        self.acc = [0, 0, 0, 0]
        self.q = self.i = 0
        self.control = [0] * 32
        self.micro = bytearray(0x1000)
        self.mem = bytearray(0x1000)
        self.instructions = 0

    # ---- state as proof_rt.cpp records it ------------------------------------------------
    def load(self, blob):
        v = STATE.unpack(blob)
        for n in range(32):
            self.vf[n] = list(v[4 * n:4 * n + 4])
        self.vi = list(v[128:144])
        self.acc = list(v[144:148])
        self.q, self.i = v[148], v[149]
        self.control = list(v[150:182])
        self.micro[:] = v[182]
        self.mem[:] = v[183]

    def dump(self):
        flat = [x for reg in self.vf for x in reg]
        return STATE.pack(*(flat + self.vi + self.acc + [self.q, self.i] + self.control + [bytes(self.micro), bytes(self.mem)]))

    # ---- arithmetic ----------------------------------------------------------------------
    def _in(self, raw):
        if self.model != 'console':
            return raw
        exp = raw & 0x7F800000
        if exp == 0x7F800000:
            return (raw & 0x80000000) | softf.FLT_MAX
        if exp == 0:
            return raw & 0x80000000
        return raw

    def add(self, a, b):
        return softf.rz_add(self._in(a), self._in(b), True)

    def sub(self, a, b):
        return softf.rz_sub(self._in(a), self._in(b), True)

    def mul(self, a, b):
        return softf.rz_mul(self._in(a), self._in(b), True)

    def greater(self, a, b):
        if self.model == 'console':
            # sign and magnitude: the patterns themselves (the two zeroes equal)
            ka = -(a & 0x7FFFFFFF) if a & 0x80000000 else a
            kb = -(b & 0x7FFFFFFF) if b & 0x80000000 else b
            return ka > kb
        return softf.order(softf.flush(a)) > softf.order(softf.flush(b))

    def ftoi(self, raw, shift):
        return softf.to_int(softf.rz_mul(self._in(raw), (127 + shift) << 23, True))

    def itof(self, word, shift):
        value = softf.from_int(word)
        return value if shift == 0 else softf.rz_mul(value, (127 - shift) << 23, True)

    # ---- the main processor's instructions -----------------------------------------------
    def cop2(self, emu, w):
        op, rs, rt, rd = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
        if op in (0x36, 0x3E):                          # LQC2 / SQC2 ft, offset(base)
            imm = (w & 0xFFFF) - 0x10000 if w & 0x8000 else w & 0xFFFF
            addr = (emu.r[rs] + imm) & M32
            if op == 0x36:
                value = emu._load16(addr)
                if rt:
                    self.vf[rt] = [(value >> (32 * k)) & M32 for k in range(4)]
            else:
                emu._store16(addr, sum(self.vf[rt][k] << (32 * k) for k in range(4)))
            return
        if rs == 1:                                     # QMFC2
            if rt:
                emu.r[rt] = self.vf[rd][0] | (self.vf[rd][1] << 32)
                emu.rh[rt] = self.vf[rd][2] | (self.vf[rd][3] << 32)
            return
        if rs == 2:                                     # CFC2
            if rt:
                emu.r[rt] = self.vi[rd] if rd < 16 else sx32(self.control[rd])
            return
        if rs == 5:                                     # QMTC2
            if rd:
                self.vf[rd] = [emu.r[rt] & M32, (emu.r[rt] >> 32) & M32, emu.rh[rt] & M32, (emu.rh[rt] >> 32) & M32]
            return
        if rs == 6:                                     # CTC2
            if rd == 0:
                return
            if rd < 16:
                self.vi[rd] = emu.r[rt] & 0xFFFF
            else:
                self.control[rd] = emu.r[rt] & M32
            return
        if rs >= 16 and (w & 63) == 0x38:               # VCALLMS
            self.run((w >> 6) & 0x7FFF)
            return
        raise Unimplemented('COP2 instruction %08x' % w)

    # ---- a microprogram ------------------------------------------------------------------
    def run(self, pc):
        vf, vi, acc, mem = self.vf, self.vi, self.acc, self.mem
        ending = in_delay = False
        branch_target = 0
        for _ in range(100000):
            pc &= 0x1FF
            lower, upper = struct.unpack_from('<II', self.micro, pc * 8)
            self.instructions += 1
            last = ending
            if upper & 0x40000000:
                ending = True
            old = [list(reg) for reg in vf]
            old_vi = list(vi)
            dest = (upper >> 21) & 15
            ft, fs, fd, bc, op = (upper >> 16) & 31, (upper >> 11) & 31, (upper >> 6) & 31, upper & 3, upper & 63
            lanes = [k for k in range(4) if (dest >> (3 - k)) & 1]

            def put(reg, k, value):
                if reg:
                    vf[reg][k] = value

            def arith(kind, a, b, k):
                if kind == 0:
                    return self.add(a, b)
                if kind == 1:
                    return self.sub(a, b)
                if kind == 2:
                    return self.add(acc[k], self.mul(a, b))
                if kind == 3:
                    return self.sub(acc[k], self.mul(a, b))
                return self.mul(a, b)

            if op >= 0x3C:
                idx = (((upper >> 6) & 31) << 2) | (upper & 3)
                if idx <= 0x0F or 0x18 <= idx <= 0x1B:              # ADDAbc SUBAbc MADDAbc MSUBAbc MULAbc
                    b = old[ft][idx & 3]
                    kind = idx >> 2 if idx <= 0x0F else 4
                    for k in lanes:
                        acc[k] = arith(kind, old[fs][k], b, k)
                elif 0x10 <= idx <= 0x13:                           # ITOF0/4/12/15
                    for k in lanes:
                        put(ft, k, self.itof(old[fs][k], (0, 4, 12, 15)[idx & 3]))
                elif 0x14 <= idx <= 0x17:                           # FTOI0/4/12/15
                    for k in lanes:
                        put(ft, k, self.ftoi(old[fs][k], (0, 4, 12, 15)[idx & 3]))
                elif idx == 0x1E:                                   # MULAi
                    for k in lanes:
                        acc[k] = self.mul(old[fs][k], self.i)
                elif idx in (0x28, 0x2A, 0x2C, 0x29, 0x2D):         # ADDA MULA SUBA MADDA MSUBA
                    kind = {0x28: 0, 0x2C: 1, 0x29: 2, 0x2D: 3, 0x2A: 4}[idx]
                    for k in lanes:
                        acc[k] = arith(kind, old[fs][k], old[ft][k], k)
                elif idx == 0x1D:                                   # ABS
                    for k in lanes:
                        put(ft, k, old[fs][k] & 0x7FFFFFFF)
                elif idx in (0x2F, 0x30):                           # NOP
                    pass
                else:
                    raise Unimplemented('upper special instruction %08x at micro address %03x' % (upper, pc))
            elif op <= 0x1B and not 0x10 <= op <= 0x17:             # ADDbc SUBbc MADDbc MSUBbc MULbc
                b = old[ft][bc]
                kind = op >> 2 if op <= 0x0F else 4
                for k in lanes:
                    put(fd, k, arith(kind, old[fs][k], b, k))
            elif 0x10 <= op <= 0x17:                                # MAXbc MINIbc
                b = old[ft][bc]
                for k in lanes:
                    a = old[fs][k]
                    put(fd, k, (a if self.greater(a, b) else b) if op <= 0x13 else (a if self.greater(b, a) else b))
            elif op in (0x1E, 0x22, 0x26, 0x23, 0x27):              # MULi ADDi SUBi MADDi MSUBi
                kind = {0x22: 0, 0x26: 1, 0x23: 2, 0x27: 3, 0x1E: 4}[op]
                for k in lanes:
                    put(fd, k, arith(kind, old[fs][k], self.i, k))
            elif op in (0x28, 0x2A, 0x2C, 0x29, 0x2D):              # ADD MUL SUB MADD MSUB
                kind = {0x28: 0, 0x2C: 1, 0x29: 2, 0x2D: 3, 0x2A: 4}[op]
                for k in lanes:
                    put(fd, k, arith(kind, old[fs][k], old[ft][k], k))
            elif op in (0x2B, 0x2F):                                # MAX MINI
                for k in lanes:
                    a, b = old[fs][k], old[ft][k]
                    put(fd, k, (a if self.greater(a, b) else b) if op == 0x2B else (a if self.greater(b, a) else b))
            else:
                raise Unimplemented('upper instruction %08x at micro address %03x' % (upper, pc))

            # the lower instruction reads the state from before the upper one
            branch, target = False, 0
            if upper & 0x80000000:
                self.i = lower                                      # I bit: the lower word is a constant
            elif lower != 0x8000033C:
                lop, lt, ls, ldest = lower >> 25, (lower >> 16) & 31, (lower >> 11) & 31, (lower >> 21) & 15
                imm11 = (lower & 0x7FF) - 0x800 if lower & 0x400 else lower & 0x7FF
                llanes = [k for k in range(4) if (ldest >> (3 - k)) & 1]
                if lop == 0x00:                                     # LQ ft, imm(is)
                    addr = ((old_vi[ls & 15] + imm11) * 16) & 0xFF0
                    for k in llanes:
                        if lt:
                            vf[lt][k] = struct.unpack_from('<I', mem, addr + 4 * k)[0]
                elif lop == 0x01:                                   # SQ fs, imm(it)
                    addr = ((old_vi[lt & 15] + imm11) * 16) & 0xFF0
                    for k in llanes:
                        struct.pack_into('<I', mem, addr + 4 * k, old[ls][k])
                elif lop == 0x20:                                   # B
                    branch, target = True, (pc + 1 + imm11) & 0x1FF
                elif lop == 0x40 and (lower & 63) == 0x3D and ((lower >> 6) & 31) == 0x0C:   # MR32
                    for k in llanes:
                        if lt:
                            vf[lt][k] = old[ls][(k + 1) & 3]
                elif lop == 0x40 and (lower & 63) == 0x3C and ((lower >> 6) & 31) == 0x0C:   # MOVE
                    for k in llanes:
                        if lt:
                            vf[lt][k] = old[ls][k]
                else:
                    raise Unimplemented('lower instruction %08x at micro address %03x' % (lower, pc))
            vf[0][:] = [0, 0, 0, ONE]
            vi[0] = 0
            if last:
                return
            if in_delay:
                pc, in_delay = branch_target, False
            else:
                pc += 1
            if branch:
                in_delay, branch_target = True, target
        raise Unimplemented('endless microprogram')
