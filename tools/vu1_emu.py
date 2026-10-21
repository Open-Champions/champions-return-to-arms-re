#!/usr/bin/env python3
"""vu1_emu.py - vector unit 1, VIF1, a DMA chain walker and a GIF packet reader, enough of
them to run this game's particle, trail and glow packets and see what they draw.

A research tool, not a console emulator.  It contains no game data: the microprograms are
the ones the game's own packets load (MPG codes read from your executable or from memory
the EE interpreter prepared), never words copied into this file.

    from vu1_emu import Vu1, Vif1, dma_chain_words, GifReader
    gs = GifReader()
    vif = Vif1(Vu1(), kick=gs.path1)            # XGKICK packets go to gs
    vif.direct = gs.path2                       # DIRECT data too
    vif.feed(dma_chain_words(read, packet_addr))
    for v in gs.vertices: ...

Where it comes from
    A Python port of the C++ interpreter tools/recomp/render/vu1.cpp + vu1_step.h and of
    the VIF decoder vif1.cpp (the renderer of the recompiled build, which draws this game's
    frames with it), with the same model of the machine:
      * one instruction pair per cycle; both halves read the registers as they were before
        the pair (the I register too: a pair with the I bit loads its constant after its
        own upper half used the old one); the upper half's result is committed after the
        lower half, so it wins when both write the same register; branch delay slots; the
        E bit (stop after the next pair);
      * the divider: Q takes the new value 7 cycles after DIV or SQRT and 13 after RSQRT,
        the old value is read until then; WAITQ and a second divide wait for the first.
        One difference from vu1.cpp: a pair whose lower half waits for the divider (WAITQ,
        or a divide while one is in flight) waits BEFORE its upper half reads Q, so
        `MULq ... | WAITQ` uses the new Q (waitq_first=True, the default; the machine
        stalls a whole pair, as emulators that model the stall do - Inferred).  vu1.cpp
        lets the upper half read the old Q (waitq_first=False).  The particle line
        program depends on it (docs/effects.md, kind 2);
      * MAC, status and clip flags as an instruction 4 or more cycles later sees them;
      * NOT modelled: FMAC data stalls (a result is visible to the very next pair; on the
        machine the pair would stall until it is ready, which gives the same values but
        more cycles, so Q and the flags could be seen sooner than here), the EFU (P),
        the random-number unit, the M/D/T bits, integer-register branch hazards;
      * numbers: the unit has no infinities, NaNs or denormals.  An operand with exponent
        255 is read as the largest finite number of its sign, an exponent of 0 as zero,
        and results are rounded toward zero.  The arithmetic is ee_emu's integer model
        (fp_add / fp_mul / fp_div ...), "chop" by default = IEEE round-toward-zero, which
        is what the C++ port computes with; other ee_emu models can be chosen.
      * VIF: a program started by MSCAL runs when the VIF reaches a code that would wait
        for it or might write what it reads (STCYCL and an UNPACK with the FLG bit into
        the output part, +0x80 and up, are carried out first), as vif1.cpp does.
    Nothing here was checked on a console.

GIF reader
    PACKED (with A+D), REGLIST and IMAGE tags on PATH1 (XGKICK from VU1 data memory) and
    PATH2 (VIF DIRECT).  It keeps PRIM, RGBAQ, ST/Q, UV and records every vertex kick
    (XYZ2 / XYZF2 / XYZ3 / XYZF3, with the ADC bit) and every other register write.
"""
import struct
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                               # noqa: E402

M32 = 0xFFFFFFFF
SIGN = 0x80000000
BIGGEST = 0x7F7FFFFF

# ---- operations ------------------------------------------------------------------------
(U_NOP, U_ADD, U_SUB, U_MUL, U_MADD, U_MSUB, U_MAX, U_MINI, U_ITOF, U_FTOI, U_CLIP,
 U_ABS, U_BAD) = range(13)
S_VEC, S_BC, S_Q, S_I = range(4)
_LOWER = ('NOP LQ SQ ILW ISW IADDIU ISUBIU FCEQ FCSET FCAND FCOR FSEQ FSSET FSAND FSOR FMEQ '
          'FMAND FMOR FCGET B BAL JR JALR IBEQ IBNE IBLTZ IBGTZ IBLEZ IBGEZ IADD ISUB IADDI '
          'IAND IOR MOVE MR32 LQI SQI LQD SQD DIV SQRT RSQRT WAITQ MTIR MFIR ILWR ISWR XTOP '
          'XITOP XGKICK BAD').split()
L = {name: n for n, name in enumerate(_LOWER)}
_BRANCHES = {L[n] for n in 'B BAL JR JALR IBEQ IBNE IBLTZ IBGTZ IBLEZ IBGEZ'.split()}
_WAITS = {L[n] for n in 'WAITQ DIV SQRT RSQRT'.split()}


class VuUnimplemented(Exception):
    pass


def vu_in(u):
    """An operand as the unit reads it: exponent 255 is the largest number, 0 is zero."""
    e = u & 0x7F800000
    if e == 0x7F800000:
        return (u & SIGN) | BIGGEST
    if e == 0:
        return u & SIGN
    return u & M32


def vu_out(u):
    """A result: too small is zero (ee_emu already does), too large the largest."""
    if (u & 0x7F800000) == 0x7F800000:
        return (u & SIGN) | BIGGEST
    if (u & 0x7F800000) == 0:
        return u & SIGN
    return u & M32


def _key(u):
    return -(u & 0x7FFFFFFF) if u & SIGN else u


class Ins:
    __slots__ = ('uop', 'usrc', 'udst', 'udest', 'uft', 'ufs', 'ufd', 'ubc', 'umask', 'lop',
                 'ldest', 'lt', 'ls', 'ld', 'fsf', 'ftf', 'ibit', 'ebit', 'imm11', 'imm15',
                 'imm24', 'lower', 'upper')


def decode(lo, up):
    d = Ins()
    d.lower, d.upper = lo, up
    d.ibit = (up >> 31) & 1
    d.ebit = (up >> 30) & 1
    d.udest = (up >> 21) & 15
    d.uft = (up >> 16) & 31
    d.ufs = (up >> 11) & 31
    d.ufd = (up >> 6) & 31
    d.ubc = up & 3
    d.umask = [M32 if d.udest & (8 >> k) else 0 for k in range(4)]
    op = up & 0x3F
    group = (U_ADD, U_SUB, U_MADD, U_MSUB, U_MAX, U_MINI, U_MUL)
    d.uop, d.usrc, d.udst = U_BAD, S_VEC, 0
    if op < 0x1C:
        d.uop, d.usrc = group[op >> 2], S_BC
    elif op < 0x28:
        ops = (U_MUL, U_MAX, U_MUL, U_MINI, U_ADD, U_MADD, U_ADD, U_MADD, U_SUB, U_MSUB, U_SUB, U_MSUB)
        src = (S_Q, S_I, S_I, S_I, S_Q, S_Q, S_I, S_I, S_Q, S_Q, S_I, S_I)
        d.uop, d.usrc = ops[op - 0x1C], src[op - 0x1C]
    elif op < 0x30:
        ops = (U_ADD, U_MADD, U_MUL, U_MAX, U_SUB, U_MSUB, U_BAD, U_MINI)
        d.uop, d.usrc = ops[op - 0x28], S_VEC
    elif op >= 0x3C:
        sp = (d.ufd << 2) | (up & 3)
        d.udst = 1
        if sp < 0x10:
            d.uop, d.usrc = (U_ADD, U_SUB, U_MADD, U_MSUB)[sp >> 2], S_BC
        elif 0x18 <= sp < 0x1C:
            d.uop, d.usrc = U_MUL, S_BC
        elif 0x10 <= sp < 0x14:
            d.uop, d.ubc = U_ITOF, (0, 4, 12, 15)[sp & 3]
        elif 0x14 <= sp < 0x18:
            d.uop, d.ubc = U_FTOI, (0, 4, 12, 15)[sp & 3]
        elif sp == 0x1C:
            d.uop, d.usrc = U_MUL, S_Q
        elif sp == 0x1D:
            d.uop = U_ABS
        elif sp == 0x1E:
            d.uop, d.usrc = U_MUL, S_I
        elif sp == 0x1F:
            d.uop = U_CLIP
        elif 0x20 <= sp < 0x28:
            ops = (U_ADD, U_MADD, U_ADD, U_MADD, U_SUB, U_MSUB, U_SUB, U_MSUB)
            src = (S_Q, S_Q, S_I, S_I, S_Q, S_Q, S_I, S_I)
            d.uop, d.usrc = ops[sp - 0x20], src[sp - 0x20]
        elif 0x28 <= sp < 0x2E and sp != 0x2B:
            d.uop, d.usrc = (U_ADD, U_MADD, U_MUL, U_BAD, U_SUB, U_MSUB)[sp - 0x28], S_VEC
        elif sp == 0x2F:
            d.uop = U_NOP
    # lower half
    d.ldest = (lo >> 21) & 15
    d.lt = (lo >> 16) & 31
    d.ls = (lo >> 11) & 31
    d.ld = (lo >> 6) & 31
    d.fsf = (lo >> 21) & 3
    d.ftf = (lo >> 23) & 3
    imm = lo & 0x7FF
    d.imm11 = imm - 0x800 if imm & 0x400 else imm
    d.imm15 = ((lo >> 10) & 0x7800) | (lo & 0x7FF)
    d.imm24 = lo & 0xFFFFFF
    lop = lo >> 25
    d.lop = L['BAD']
    simple = {0x00: 'LQ', 0x01: 'SQ', 0x04: 'ILW', 0x05: 'ISW', 0x08: 'IADDIU', 0x09: 'ISUBIU',
              0x10: 'FCEQ', 0x11: 'FCSET', 0x12: 'FCAND', 0x13: 'FCOR', 0x14: 'FSEQ',
              0x15: 'FSSET', 0x16: 'FSAND', 0x17: 'FSOR', 0x18: 'FMEQ', 0x1A: 'FMAND',
              0x1B: 'FMOR', 0x1C: 'FCGET', 0x20: 'B', 0x21: 'BAL', 0x24: 'JR', 0x25: 'JALR',
              0x28: 'IBEQ', 0x29: 'IBNE', 0x2C: 'IBLTZ', 0x2D: 'IBGTZ', 0x2E: 'IBLEZ',
              0x2F: 'IBGEZ'}
    if d.ibit:
        d.lop = L['NOP']
    elif lop in simple:
        d.lop = L[simple[lop]]
    elif lop == 0x40:
        f = lo & 0x3F
        if f in (0x30, 0x31, 0x32, 0x34, 0x35):
            d.lop = L[{0x30: 'IADD', 0x31: 'ISUB', 0x32: 'IADDI', 0x34: 'IAND', 0x35: 'IOR'}[f]]
        elif f >= 0x3C:
            sp = (d.ld << 2) | (lo & 3)
            special = {0x30: 'MOVE', 0x31: 'MR32', 0x34: 'LQI', 0x35: 'SQI', 0x36: 'LQD',
                       0x37: 'SQD', 0x38: 'DIV', 0x39: 'SQRT', 0x3A: 'RSQRT', 0x3B: 'WAITQ',
                       0x3C: 'MTIR', 0x3D: 'MFIR', 0x3E: 'ILWR', 0x3F: 'ISWR', 0x68: 'XTOP',
                       0x69: 'XITOP', 0x6C: 'XGKICK'}
            if sp in special:
                d.lop = L[special[sp]]
        if lo == 0x8000033C:
            d.lop = L['NOP']
    return d


class Vu1:
    """VU1 state: 32 vf registers (four raw 32-bit lanes), 16 vi, ACC, Q, I, 16 KB of
    instruction memory (2048 pairs) and 16 KB of data memory (1024 qwords, as 4096 words)."""

    def __init__(self, fpu_model='chop', waitq_first=True):
        self.model = fpu_model
        self.waitq_first = waitq_first
        self.vf = [[0, 0, 0, 0] for _ in range(32)]
        self.vf[0] = [0, 0, 0, 0x3F800000]
        self.acc = [0, 0, 0, 0]
        self.vi = [0] * 16
        self.q = self.q_next = self.i_reg = 0
        self.cyc, self.q_ready, self.q_busy = 16, 0, False
        self.flag_ring = []             # (cycle, result lanes, dest mask)
        self.clip_ring = []             # (cycle, clip value)
        self.clip_now = 0
        self.top = self.itop = 0
        self.pc = 0
        self.micro = bytearray(0x4000)
        self.data = [0] * 4096          # words
        self.kick = None                # kick(vu, qword)
        self.decoded = [None] * 2048
        self.instructions = 0
        self.runs = 0
        self.trace = None               # a list to receive (pc, cycle) of every pair

    # -- memory --
    def micro_changed(self, first=0, count=2048):
        for n in range(first, min(2048, first + count)):
            self.decoded[n] = None

    def load_micro(self, at, blob):
        at = (at * 8) & 0x3FFF
        n = min(len(blob), 0x4000 - at)
        self.micro[at:at + n] = blob[:n]
        self.micro_changed(at // 8, (n + 7) // 8)

    def qword(self, q):
        q &= 0x3FF
        return self.data[q * 4:q * 4 + 4]

    def set_qword(self, q, lanes):
        q &= 0x3FF
        self.data[q * 4:q * 4 + 4] = [x & M32 for x in lanes]

    # -- arithmetic --
    def _add(self, a, b):
        return vu_out(ee_emu.fp_add(a, b, self.model))

    def _sub(self, a, b):
        return vu_out(ee_emu.fp_add(a, b ^ SIGN, self.model))

    def _mul(self, a, b):
        return vu_out(ee_emu.fp_mul(a, b, self.model))

    def _div(self, a, b):
        return vu_out(ee_emu.fp_div(a, b, self.model))

    def _sqrt(self, a):
        return vu_out(ee_emu.fp_sqrt(a & 0x7FFFFFFF, self.model))

    # -- flags --
    def mac_seen(self):
        for cyc, value, dest in reversed(self.flag_ring[-8:]):
            if cyc + 4 > self.cyc:
                continue
            mac = 0
            for k in range(4):
                if not dest & (8 >> k):
                    continue
                if (value[k] & 0x7FFFFFFF) == 0:
                    mac |= 0x0008 >> k
                if value[k] & SIGN:
                    mac |= 0x0080 >> k
            return mac
        return 0

    def clip_seen(self):
        for cyc, value in reversed(self.clip_ring[-8:]):
            if cyc + 4 <= self.cyc:
                return value
        return 0

    # -- one pair --
    def step(self, d, at):
        if self.q_busy and self.cyc >= self.q_ready:
            self.q, self.q_busy = self.q_next, False
        if self.waitq_first and d.lop in _WAITS and self.q_busy:
            # the pair waits for the divider before it issues, so its upper half reads
            # the new Q (vu1.cpp lets the upper half read the old one: waitq_first=False)
            if self.q_ready > self.cyc:
                self.cyc = self.q_ready
            self.q, self.q_busy = self.q_next, False
        vf, vi = self.vf, self.vi
        write, target, result = 0, 0, None
        if d.uop != U_NOP:
            fs, ft = vf[d.ufs], vf[d.uft]
            if d.usrc == S_VEC:
                bb = ft
            elif d.usrc == S_BC:
                bb = [ft[d.ubc]] * 4
            elif d.usrc == S_Q:
                bb = [self.q] * 4
            else:
                bb = [self.i_reg] * 4
            uop = d.uop
            arithmetic = uop <= U_MSUB
            if arithmetic:
                a = [vu_in(x) for x in fs]
                b = [vu_in(x) for x in bb]
            if uop == U_ADD:
                r = [self._add(a[k], b[k]) for k in range(4)]
            elif uop == U_SUB:
                r = [self._sub(a[k], b[k]) for k in range(4)]
            elif uop == U_MUL:
                r = [self._mul(a[k], b[k]) for k in range(4)]
            elif uop == U_MADD:
                p = [self._mul(a[k], b[k]) for k in range(4)]
                r = [self._add(vu_in(self.acc[k]), p[k]) for k in range(4)]
            elif uop == U_MSUB:
                p = [self._mul(a[k], b[k]) for k in range(4)]
                r = [self._sub(vu_in(self.acc[k]), p[k]) for k in range(4)]
            elif uop == U_MAX:
                r = [fs[k] if _key(fs[k]) > _key(bb[k]) else bb[k] for k in range(4)]
            elif uop == U_MINI:
                r = [fs[k] if _key(fs[k]) < _key(bb[k]) else bb[k] for k in range(4)]
            elif uop == U_ITOF:
                scale = ee_emu.float_to_raw(1.0 / (1 << d.ubc))
                r = [self._mul(ee_emu.fp_from_int(fs[k], self.model), scale) for k in range(4)]
            elif uop == U_FTOI:
                scale = ee_emu.float_to_raw(float(1 << d.ubc))
                r = [ee_emu.fp_to_int(self._mul(vu_in(fs[k]), scale)) for k in range(4)]
            elif uop == U_ABS:
                r = [x & 0x7FFFFFFF for x in fs]
            elif uop == U_CLIP:
                w = vu_in(ft[3]) & 0x7FFFFFFF
                c = 0
                for bit, lane in ((1, 0), (4, 1), (16, 2)):
                    x = vu_in(fs[lane])
                    if ee_emu.fp_cmp(x, w) > 0:
                        c |= bit
                    if ee_emu.fp_cmp(x, w | SIGN) < 0:
                        c |= bit << 1
                self.clip_now = ((self.clip_now << 6) | c) & 0xFFFFFF
                self.clip_ring.append((self.cyc, self.clip_now))
                del self.clip_ring[:-8]
                r = None
            else:
                raise VuUnimplemented('upper word 0x%08x at 0x%03x' % (d.upper, at))
            if r is not None:
                to_acc = d.udst and uop <= U_MSUB
                target = d.uft if uop in (U_ITOF, U_FTOI, U_ABS) else d.ufd
                old = self.acc if to_acc else vf[target]
                result = [(r[k] & d.umask[k]) | (old[k] & ~d.umask[k] & M32) for k in range(4)]
                write = 2 if to_acc else 1
                if arithmetic:
                    self.flag_ring.append((self.cyc, r, d.udest))
                    del self.flag_ring[:-8]
        taken, dest = self._lower(d, at)
        if d.ibit:
            self.i_reg = d.lower
        if write == 2:
            self.acc = result
        elif write == 1 and target:
            vf[target] = result
        self.cyc += 1
        self.instructions += 1
        return taken, dest

    def _lower(self, d, at):
        lop, vf, vi, mem = d.lop, self.vf, self.vi, self.data
        dest = 0
        name = _LOWER[lop]
        if name == 'NOP':
            return False, 0
        if name in ('LQ', 'LQI', 'LQD'):
            if name == 'LQD' and d.ls:
                vi[d.ls] = (vi[d.ls] - 1) & 0xFFFF
            q = (vi[d.ls] + (d.imm11 if name == 'LQ' else 0)) & 0x3FF
            if d.lt:
                for k in range(4):
                    if d.ldest & (8 >> k):
                        vf[d.lt][k] = mem[q * 4 + k]
            if name == 'LQI' and d.ls:
                vi[d.ls] = (vi[d.ls] + 1) & 0xFFFF
            return False, 0
        if name in ('SQ', 'SQI', 'SQD'):
            if name == 'SQD' and d.lt:
                vi[d.lt] = (vi[d.lt] - 1) & 0xFFFF
            q = (vi[d.lt] + (d.imm11 if name == 'SQ' else 0)) & 0x3FF
            src = vf[d.ls]
            for k in range(4):
                if d.ldest & (8 >> k):
                    mem[q * 4 + k] = src[k]
            if name == 'SQI' and d.lt:
                vi[d.lt] = (vi[d.lt] + 1) & 0xFFFF
            return False, 0
        if name in ('ILW', 'ILWR'):
            q = (vi[d.ls] + (d.imm11 if name == 'ILW' else 0)) & 0x3FF
            for k in range(4):
                if d.ldest & (8 >> k):
                    if d.lt:
                        vi[d.lt] = mem[q * 4 + k] & 0xFFFF
                    break
            return False, 0
        if name in ('ISW', 'ISWR'):
            q = (vi[d.ls] + (d.imm11 if name == 'ISW' else 0)) & 0x3FF
            for k in range(4):
                if d.ldest & (8 >> k):
                    mem[q * 4 + k] = vi[d.lt]
            return False, 0
        if name == 'IADDIU':
            if d.lt:
                vi[d.lt] = (vi[d.ls] + d.imm15) & 0xFFFF
        elif name == 'ISUBIU':
            if d.lt:
                vi[d.lt] = (vi[d.ls] - d.imm15) & 0xFFFF
        elif name == 'IADD':
            if d.ld:
                vi[d.ld] = (vi[d.ls] + vi[d.lt]) & 0xFFFF
        elif name == 'ISUB':
            if d.ld:
                vi[d.ld] = (vi[d.ls] - vi[d.lt]) & 0xFFFF
        elif name == 'IAND':
            if d.ld:
                vi[d.ld] = vi[d.ls] & vi[d.lt]
        elif name == 'IOR':
            if d.ld:
                vi[d.ld] = vi[d.ls] | vi[d.lt]
        elif name == 'IADDI':
            imm5 = d.ld - 32 if d.ld & 16 else d.ld
            if d.lt:
                vi[d.lt] = (vi[d.ls] + imm5) & 0xFFFF
        elif name == 'FCSET':
            self.clip_now = d.imm24
            self.clip_ring.append((self.cyc, self.clip_now))
            del self.clip_ring[:-8]
        elif name == 'FCAND':
            vi[1] = 1 if self.clip_seen() & d.imm24 else 0
        elif name == 'FCOR':
            vi[1] = 1 if ((self.clip_seen() | d.imm24) & 0xFFFFFF) == 0xFFFFFF else 0
        elif name == 'FCEQ':
            vi[1] = 1 if (self.clip_seen() & 0xFFFFFF) == d.imm24 else 0
        elif name == 'FCGET':
            if d.lt:
                vi[d.lt] = self.clip_seen() & 0xFFF
        elif name in ('FSAND', 'FSOR', 'FSEQ'):
            mac = self.mac_seen()
            status = (1 if mac & 0x000F else 0) | (2 if mac & 0x00F0 else 0)
            imm = ((d.lower >> 10) & 0x800) | (d.lower & 0x7FF)
            if d.lt:
                vi[d.lt] = (status & imm if name == 'FSAND' else (status | imm) & 0xFFF
                            if name == 'FSOR' else int(status == imm))
        elif name == 'FSSET':
            pass
        elif name == 'FMAND':
            if d.lt:
                vi[d.lt] = self.mac_seen() & vi[d.ls]
        elif name == 'FMOR':
            if d.lt:
                vi[d.lt] = (self.mac_seen() | vi[d.ls]) & 0xFFFF
        elif name == 'FMEQ':
            if d.lt:
                vi[d.lt] = int((self.mac_seen() & 0xFFFF) == vi[d.ls])
        elif name in ('B', 'BAL'):
            if name == 'BAL' and d.lt:
                vi[d.lt] = (at + 2) & 0xFFFF
            return True, at + 1 + d.imm11
        elif name in ('JR', 'JALR'):
            dest = vi[d.ls]
            if name == 'JALR' and d.lt:
                vi[d.lt] = (at + 2) & 0xFFFF
            return True, dest
        elif name in ('IBEQ', 'IBNE', 'IBLTZ', 'IBGTZ', 'IBLEZ', 'IBGEZ'):
            s = vi[d.ls] - 0x10000 if vi[d.ls] & 0x8000 else vi[d.ls]
            taken = {'IBEQ': vi[d.lt] == vi[d.ls], 'IBNE': vi[d.lt] != vi[d.ls],
                     'IBLTZ': s < 0, 'IBGTZ': s > 0, 'IBLEZ': s <= 0, 'IBGEZ': s >= 0}[name]
            return taken, at + 1 + d.imm11
        elif name == 'MOVE':
            if d.lt:
                src = list(vf[d.ls])
                for k in range(4):
                    if d.ldest & (8 >> k):
                        vf[d.lt][k] = src[k]
        elif name == 'MR32':
            if d.lt:
                s = list(vf[d.ls])
                for k in range(4):
                    if d.ldest & (8 >> k):
                        vf[d.lt][k] = s[(k + 1) & 3]
        elif name == 'MTIR':
            if d.lt:
                vi[d.lt] = vf[d.ls][d.fsf] & 0xFFFF
        elif name == 'MFIR':
            if d.lt:
                v = vi[d.ls]
                v = (v - 0x10000 if v & 0x8000 else v) & M32
                for k in range(4):
                    if d.ldest & (8 >> k):
                        vf[d.lt][k] = v
        elif name == 'XTOP':
            if d.lt:
                vi[d.lt] = self.top & 0xFFFF
        elif name == 'XITOP':
            if d.lt:
                vi[d.lt] = self.itop & 0x3FF
        elif name in ('DIV', 'SQRT', 'RSQRT'):
            if self.q_busy:
                if self.q_ready > self.cyc:
                    self.cyc = self.q_ready
                self.q, self.q_busy = self.q_next, False
            a = vu_in(vf[d.ls][d.fsf])
            b = vu_in(vf[d.lt][d.ftf])
            if name == 'DIV':
                r = (((a ^ b) & SIGN) | BIGGEST) if (b & 0x7FFFFFFF) == 0 else self._div(a, b)
            elif name == 'SQRT':
                r = self._sqrt(b)
            else:
                r = ((a & SIGN) | BIGGEST) if (b & 0x7FFFFFFF) == 0 else self._div(a, self._sqrt(b))
            self.q_next = vu_out(r)
            self.q_ready = self.cyc + (13 if name == 'RSQRT' else 7)
            self.q_busy = True
        elif name == 'WAITQ':
            if self.q_busy:
                if self.q_ready > self.cyc:
                    self.cyc = self.q_ready
                self.q, self.q_busy = self.q_next, False
        elif name == 'XGKICK':
            if self.kick:
                self.kick(self, vi[d.ls] & 0x3FF)
        else:
            raise VuUnimplemented('lower word 0x%08x at 0x%03x' % (d.lower, at))
        return False, dest

    def run(self, start, max_pairs=4000000):
        self.runs += 1
        at = start & 2047
        stop_in, branch_in, branch_to = -1, -1, 0
        for _ in range(max_pairs):
            d = self.decoded[at]
            if d is None:
                lo, up = struct.unpack_from('<II', self.micro, at * 8)
                d = self.decoded[at] = decode(lo, up)
            if self.trace is not None:
                self.trace.append((at, self.cyc))
            taken, dest = self.step(d, at)
            at = (at + 1) & 2047
            if branch_in == 0:
                at, branch_in = branch_to & 2047, -1
            elif branch_in > 0:
                branch_in -= 1
            if taken and branch_in < 0:
                branch_in, branch_to = 0, dest
            if stop_in == 0:
                break
            if stop_in > 0:
                stop_in -= 1
            if d.ebit and stop_in < 0:
                stop_in = 0
        else:
            raise VuUnimplemented('program from 0x%03x did not end' % start)
        self.pc = at
        if self.q_busy:
            self.q, self.q_busy = self.q_next, False


# ---------------------------------------------------------------------------------------
# VIF1
# ---------------------------------------------------------------------------------------

def unpack_words(code, cl, wl):
    cmd, num = (code >> 24) & 0x7F, (code >> 16) & 0xFF
    vn, vl = (cmd >> 2) & 3, cmd & 3
    vectors = num or 256
    if wl > cl and wl:
        vectors = cl * (vectors // wl) + min(vectors % wl, cl)
    nbytes = vectors * 2 if (vn == 3 and vl == 3) else vectors * (vn + 1) * (4 >> vl)
    return (nbytes + 3) // 4


class Vif1:
    """Decodes the VIF1 word stream: STCYCL, OFFSET, BASE, ITOP, STMOD, STMASK, STROW,
    STCOL, MPG, MSCAL/MSCALF/MSCNT, DIRECT/DIRECTHL, UNPACK (all formats, masks, modes)."""

    def __init__(self, vu, kick=None, direct=None):
        self.vu = vu
        if kick is not None:
            vu.kick = kick
        self.direct = direct            # direct(list of words) for DIRECT data
        self.cl = self.wl = 1
        self.mode = self.mask = 0
        self.row = [0, 0, 0, 0]
        self.col = [0, 0, 0, 0]
        self.base = self.ofst = self.tops = self.itops = 0
        self.dbf = False
        self.waiting, self.waiting_from_pc, self.waiting_at = False, False, 0
        self.programs = []              # entries started, in order (-1: MSCNT)
        self.on_program = None          # called (vif, entry) before a program runs

    def run_waiting(self):
        if not self.waiting:
            return
        self.waiting = False
        entry = -1 if self.waiting_from_pc else self.waiting_at
        if self.on_program:
            self.on_program(self, entry)
        self.vu.run(self.vu.pc if self.waiting_from_pc else self.waiting_at)

    def start_program(self, at, from_pc):
        self.run_waiting()
        vu = self.vu
        vu.top = self.tops & 0x3FF
        if self.dbf:
            self.tops, self.dbf = self.base, False
        else:
            self.tops, self.dbf = self.base + self.ofst, True
        vu.itop = self.itops
        self.programs.append(-1 if from_pc else at)
        self.waiting, self.waiting_at, self.waiting_from_pc = True, at, from_pc

    def feed(self, w):
        i, n = 0, len(w)
        while i < n:
            code = w[i]
            cmd, num, imm = (code >> 24) & 0x7F, (code >> 16) & 0xFF, code & 0xFFFF
            need = 0
            if cmd == 0x20:
                need = 1
            elif cmd in (0x30, 0x31):
                need = 4
            elif cmd == 0x4A:
                need = (num or 256) * 2
            elif cmd in (0x50, 0x51):
                need = (imm or 65536) * 4
            elif cmd >= 0x60:
                need = unpack_words(code, self.cl, self.wl)
            if i + 1 + need > n:
                raise ValueError('VIF code 0x%08x at word %d runs past the stream' % (code, i))
            data = w[i + 1:i + 1 + need]
            if self.waiting:
                harmless = cmd in (0, 1) or (cmd >= 0x60 and (imm & 0x8000) and (imm & 0x3FF) >= 0x80)
                if not harmless:
                    self.run_waiting()
            if cmd == 0x01:
                self.cl, self.wl = imm & 0xFF, (imm >> 8) & 0xFF
            elif cmd == 0x02:
                self.ofst, self.dbf, self.tops = imm & 0x3FF, False, self.base
            elif cmd == 0x03:
                self.base = imm & 0x3FF
            elif cmd == 0x04:
                self.itops = imm & 0x3FF
            elif cmd == 0x05:
                self.mode = imm & 3
            elif cmd in (0x14, 0x15):
                self.start_program(imm, False)
            elif cmd == 0x17:
                self.start_program(0, True)
            elif cmd == 0x20:
                self.mask = data[0]
            elif cmd == 0x30:
                self.row = list(data)
            elif cmd == 0x31:
                self.col = list(data)
            elif cmd == 0x4A:
                self.vu.load_micro(imm, struct.pack('<%dI' % need, *data))
            elif cmd in (0x50, 0x51):
                if self.direct:
                    self.direct(data)
            elif cmd >= 0x60:
                self.unpack(code, data)
            i += 1 + need
        self.run_waiting()

    def unpack(self, code, data):
        cmd, num, imm = (code >> 24) & 0x7F, (code >> 16) & 0xFF, code & 0xFFFF
        vn, vl = (cmd >> 2) & 3, cmd & 3
        masked, usn, flg = cmd & 0x10, imm & 0x4000, imm & 0x8000
        address = (imm & 0x3FF) + (self.tops if flg else 0)
        total = num or 256
        src = struct.pack('<%dI' % len(data), *data)
        pos = 0
        wcl, wwl = self.cl or 1, self.wl or 1
        cycle = 0
        size = 4 >> vl

        def element(index):
            off = pos + index * size
            if off + size > len(src):
                return 0
            if vl == 0:
                return struct.unpack_from('<I', src, off)[0]
            if vl == 1:
                v = struct.unpack_from('<H', src, off)[0]
                return v if usn else (v - 0x10000 if v & 0x8000 else v) & M32
            v = src[off]
            return v if usn else (v - 0x100 if v & 0x80 else v) & M32
        written = 0
        mem = self.vu.data
        while written < total:
            has_data = True if wwl <= wcl else cycle < wcl
            writes = cycle < wwl if wwl <= wcl else True
            if writes:
                inp = [0, 0, 0, 0]
                if has_data:
                    if vn == 3 and vl == 3:
                        v = struct.unpack_from('<H', src, pos)[0]
                        inp = [(v & 31) << 3, ((v >> 5) & 31) << 3, ((v >> 10) & 31) << 3, (v >> 15) << 7]
                        pos += 2
                    else:
                        if vn == 0:
                            inp = [element(0)] * 4
                        else:
                            for f in range(vn + 1):
                                inp[f] = element(f)
                        pos += (vn + 1) * size
                q = address & 0x3FF
                mrow = min(cycle, 3)
                for f in range(4):
                    m = (self.mask >> (mrow * 8 + f * 2)) & 3 if masked else 0
                    if m == 0:
                        v = inp[f]
                        if not (vn == 3 and vl == 3):
                            if self.mode == 1:
                                v = (v + self.row[f]) & M32
                            elif self.mode == 2:
                                v = (v + self.row[f]) & M32
                                self.row[f] = v
                    elif m == 1:
                        v = self.row[f]
                    elif m == 2:
                        v = self.col[mrow]
                    else:
                        continue
                    mem[q * 4 + f] = v & M32
                written += 1
            address += 1
            cycle += 1
            if (cycle >= wcl) if wwl <= wcl else (cycle >= wwl):
                cycle = 0


# ---------------------------------------------------------------------------------------
# DMA (VIF1 channel, source chain mode, tag transfer on)
# ---------------------------------------------------------------------------------------

DMA_REFE, DMA_CNT, DMA_NEXT, DMA_REF, DMA_REFS, DMA_CALL, DMA_RET, DMA_END = range(8)


def dma_chain_words(read, addr, max_tags=100000, log=None):
    """The VIF word stream of a DMA chain starting with the tag at addr, as the VIF1
    channel sends it with TTE set: the upper 64 bits of every tag, then its data.  read(a,
    n) returns n bytes of EE memory.  A RET with an empty stack ends the chain (the game's
    sorted packets are subroutines that end that way).  log, a list, receives (tag
    address, id, qwc, data address)."""
    words = []
    stack = []
    tadr = addr
    for _ in range(max_tags):
        tag = read(tadr & 0x0FFFFFFF, 16)
        lo, hi, w2, w3 = struct.unpack('<IIII', tag)
        qwc, tid, daddr = lo & 0xFFFF, (lo >> 28) & 7, hi & 0x7FFFFFF0
        if log is not None:
            log.append((tadr, tid, qwc, daddr))
        words += [w2, w3]
        follow = tadr + 16
        if tid in (DMA_REFE, DMA_REF, DMA_REFS):
            src = daddr
        else:
            src = follow
        if qwc:
            words += list(struct.unpack('<%dI' % (qwc * 4), read(src & 0x0FFFFFFF, qwc * 16)))
        after = src + qwc * 16
        if tid == DMA_REFE or tid == DMA_END:
            return words
        if tid == DMA_CNT:
            tadr = after
        elif tid == DMA_NEXT:
            tadr = daddr
        elif tid in (DMA_REF, DMA_REFS):
            tadr = follow
        elif tid == DMA_CALL:
            stack.append(after)
            tadr = daddr
        elif tid == DMA_RET:
            if not stack:
                return words
            tadr = stack.pop()
    raise ValueError('DMA chain at 0x%x did not end' % addr)


# ---------------------------------------------------------------------------------------
# GIF packets
# ---------------------------------------------------------------------------------------

REG_NAMES = {0x00: 'PRIM', 0x01: 'RGBAQ', 0x02: 'ST', 0x03: 'UV', 0x04: 'XYZF2', 0x05: 'XYZ2',
             0x06: 'TEX0_1', 0x08: 'CLAMP_1', 0x0A: 'FOG', 0x0C: 'XYZF3', 0x0D: 'XYZ3',
             0x14: 'TEX1_1', 0x3F: 'TEXFLUSH', 0x42: 'ALPHA_1', 0x44: 'DIMX', 0x45: 'DTHE',
             0x47: 'TEST_1', 0x49: 'PABE'}


class Vertex:
    __slots__ = ('x', 'y', 'z', 'f', 'adc', 'reg', 'rgba', 'q', 'uv', 'st', 'prim', 'path')

    def key(self):
        """Everything the GS would use, as integers / raw float patterns."""
        return (self.x, self.y, self.z, self.f, self.adc, self.reg, self.rgba, self.q,
                self.uv, self.st, self.prim)

    def __repr__(self):
        return ('Vertex(xy=(%d,%d) z=%d adc=%d rgba=%s uv=%s st=%s prim=0x%x)'
                % (self.x, self.y, self.z, self.adc, self.rgba, self.uv,
                   tuple('%08x' % s for s in self.st) if self.st else None, self.prim))


class GifReader:
    """Reads GIF packets and keeps the drawing state.  events: ('reg', name/addr, value)
    and ('vtx', Vertex) in the order the GS receives them."""

    def __init__(self):
        self.prim = 0
        self.rgba = (0, 0, 0, 0)
        self.q = 0x3F800000
        self.st = None
        self.uv = None
        self.events = []
        self.vertices = []
        self.tags = []
        self.raw = []                   # (register address, 64-bit value) of REGLIST / A+D writes

    def path1(self, vu, qword):
        """XGKICK: a packet in VU1 data memory starting at qword."""
        words = []
        q = qword
        while True:
            tag = vu.qword(q)
            nloop, eop, flg, nreg = tag[0] & 0x7FFF, (tag[0] >> 15) & 1, (tag[1] >> 26) & 3, tag[1] >> 28
            nreg = nreg or 16
            if flg == 0:
                length = nloop * nreg
            elif flg == 1:
                length = (nloop * nreg + 1) // 2
            else:
                length = nloop
            for k in range(1 + length):
                words += vu.qword(q + k)
            q += 1 + length
            if eop:
                break
            if q - qword > 1024:
                raise ValueError('XGKICK packet without end')
        self.read_words(words, path=1)

    def path2(self, words):
        self.read_words(list(words), path=2)

    def _write(self, addr, lo, hi, packed, w=None, path=0):
        """One register write.  packed: the 128-bit packed form w (four words) is given."""
        if packed:
            if addr == 0x00:
                self.prim = w[0] & 0x7FF
                self.events.append(('reg', 'PRIM', self.prim))
                return
            if addr == 0x01:
                self.rgba = (w[0] & 0xFF, w[1] & 0xFF, w[2] & 0xFF, w[3] & 0xFF)
                return
            if addr == 0x02:
                self.st = (w[0], w[1])
                self.q = w[2]
                return
            if addr == 0x03:
                self.uv = (w[0] & 0x3FFF, w[1] & 0x3FFF)
                return
            if addr in (0x04, 0x05, 0x0C, 0x0D):
                v = Vertex()
                v.x, v.y = w[0] & 0xFFFF, w[1] & 0xFFFF
                if addr in (0x04, 0x0C):
                    v.z, v.f = (w[2] >> 4) & 0xFFFFFF, (w[3] >> 4) & 0xFF
                else:
                    v.z, v.f = w[2], None
                v.adc = (w[3] >> 15) & 1
                v.reg = {0x04: 'XYZF2', 0x05: 'XYZ2', 0x0C: 'XYZF3', 0x0D: 'XYZ3'}[addr]
                self._kick(v, path)
                return
            if addr == 0x0E:                            # A+D
                self._write(w[2] & 0xFF, w[0], w[1], False, path=path)
                return
            if addr == 0x0F:
                return
            self._write(addr, w[0], w[1], False, path=path)
            return
        value = lo | (hi << 32)
        self.raw.append((addr, value))
        if addr == 0x00:
            self.prim = value & 0x7FF
        elif addr == 0x01:
            self.rgba = (lo & 0xFF, (lo >> 8) & 0xFF, (lo >> 16) & 0xFF, lo >> 24)
            self.q = hi
        elif addr == 0x02:
            self.st = (lo, hi)
        elif addr == 0x03:
            self.uv = (lo & 0x3FFF, (lo >> 16) & 0x3FFF)
        elif addr in (0x04, 0x05, 0x0C, 0x0D):
            v = Vertex()
            v.x, v.y = lo & 0xFFFF, lo >> 16
            if addr in (0x04, 0x0C):
                v.z, v.f = hi & 0xFFFFFF, hi >> 24
            else:
                v.z, v.f = hi, None
            v.adc = 0
            v.reg = {0x04: 'XYZF2', 0x05: 'XYZ2', 0x0C: 'XYZF3', 0x0D: 'XYZ3'}[addr]
            self._kick(v, path)
            return
        self.events.append(('reg', REG_NAMES.get(addr, addr), value))

    def _kick(self, v, path):
        v.rgba, v.q, v.uv, v.st, v.prim, v.path = self.rgba, self.q, self.uv, self.st, self.prim, path
        self.events.append(('vtx', v))
        self.vertices.append(v)

    def read_words(self, words, path=0):
        i, n = 0, len(words)
        while i + 4 <= n:
            t = words[i:i + 4]
            i += 4
            nloop, eop = t[0] & 0x7FFF, (t[0] >> 15) & 1
            pre, prim, flg = (t[1] >> 14) & 1, (t[1] >> 15) & 0x7FF, (t[1] >> 26) & 3
            nreg = (t[1] >> 28) or 16
            regs = [((t[2] | (t[3] << 32)) >> (4 * k)) & 15 for k in range(nreg)]
            self.tags.append((nloop, eop, pre, prim, flg, tuple(regs), path))
            if pre and flg != 2:
                self.prim = prim
                self.events.append(('reg', 'PRIM', prim))
            if flg == 0:
                for _ in range(nloop):
                    for r in regs:
                        self._write(r, 0, 0, True, words[i:i + 4], path)
                        i += 4
            elif flg == 1:
                k = 0
                for _ in range(nloop):
                    for r in regs:
                        lo, hi = words[i + 2 * (k & 1)], words[i + 2 * (k & 1) + 1]
                        if r == 0x0E or r == 0x0F:
                            pass
                        else:
                            self._write(r, lo, hi, False, path=path)
                        k += 1
                        if not k & 1:
                            i += 4
                if k & 1:
                    i += 4
            else:
                i += 4 * nloop
            if eop and path == 1:
                break
