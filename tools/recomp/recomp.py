#!/usr/bin/env python3
"""recomp.py - translate the functions of a PS2 executable (MIPS R5900) to C++.

  python3 tools/recomp/recomp.py [--elf SLUS_209.73] [--funcs ghidra_funcs.tsv]
                                 [--out local/recomp-out/gen] [--hle FILE] [--chunk BYTES]

One C++ function `void fn_<address>(Ctx*)` per game function, written against
tools/recomp/rt/recomp.h.  The output is derived from the game's code: it goes under
local/ and never into the repository.

How the code is cut up
    A *unit* is a stretch of .text translated into one C++ function body.  Every row of
    the function table gives one unit (first start to last end; rows with several ranges
    are one unit).  Whatever non-zero words of .text are left over become "gap" units, so
    that all of .text is translated.
    An *entry* is an address something may call or jump to from outside its unit: the unit
    start, every `jal` target, every branch or jump that leaves its unit, the address a
    unit falls through to, every aligned data word that holds a .text address (function
    pointers, virtual tables, jump tables), every address a `lui`/`addiu` pair forms, and
    inside gap units every address that follows an unconditional return.  Each entry gets
    a `fn_<address>` and a slot in the table used for calls through a pointer.

Control flow
    Branches inside a unit are `goto`s; the delay slot is emitted with its branch (before
    the jump, after the condition is computed; inside the taken arm for "likely" branches).
    `jal` is a direct C++ call, `jalr` a call through the table.  `jr $ra` returns.  Any
    other `jr` loads a program counter and goes to the unit's dispatch `switch`, which has
    a case for every label of the unit (jump-table targets are labels because the tables
    are data words that hold .text addresses); a target outside the unit is a tail call
    through the table.  Units with more than one entry use the same switch to start in the
    middle.

Instruction semantics follow tools/ee_emu.py one for one; tools/recomp/difftest.py checks
the result against that interpreter.
"""
import argparse
import reloc
import bisect
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def sx16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


class Image:
    """The loaded segments of the ELF; .text as a list of words."""

    def __init__(self, path):
        with open(path, 'rb') as source:
            data = source.read()
        self.data = data
        self.entry, phoff = struct.unpack_from('<II', data, 24)
        phentsize, phnum = struct.unpack_from('<HH', data, 42)
        self.segments = []
        for index in range(phnum):
            kind, offset, vaddr, _p, filesz, memsz = struct.unpack_from('<6I', data, phoff + index * phentsize)
            if kind == 1:
                self.segments.append((vaddr, offset, filesz, memsz))
        shoff, = struct.unpack_from('<I', data, 32)
        shentsize, shnum, shstrndx = struct.unpack_from('<HHH', data, 46)
        heads = [struct.unpack_from('<10I', data, shoff + i * shentsize) for i in range(shnum)]
        names = heads[shstrndx][4]
        self.sections = {}
        for head in heads:
            name = data[names + head[0]:data.index(b'\0', names + head[0])].decode('latin1')
            self.sections[name] = (head[3], head[4], head[5])
        self.text_lo, text_off, text_size = self.sections['.text']
        self.text_hi = self.text_lo + text_size
        self.words = struct.unpack_from('<%dI' % (text_size // 4), data, text_off)

    def word(self, addr):
        if self.text_lo <= addr < self.text_hi:
            return self.words[(addr - self.text_lo) >> 2]
        return None

    def patch(self, words):
        """Write (address, value) words into the image as a patch file would write them
        into memory before the game starts."""
        data = bytearray(self.data)
        text = list(self.words)
        for address, value in words:
            if self.text_lo <= address < self.text_hi:
                text[(address - self.text_lo) >> 2] = value
            for vaddr, offset, filesz, _m in self.segments:
                if vaddr <= address and address + 4 <= vaddr + filesz:
                    struct.pack_into('<I', data, offset + address - vaddr, value)
                    break
            else:
                raise SystemExit('patch word at 0x%x is not in the executable file' % address)
        self.data = bytes(data)
        self.words = tuple(text)

    def data_words(self):
        """Every aligned word of the loaded file data outside .text: (address, value)."""
        for vaddr, offset, filesz, _m in self.segments:
            lo, hi = vaddr, vaddr + filesz
            if lo < self.text_hi and hi > self.text_lo:         # the segment that holds .text
                lo = max(lo, (self.text_hi + 3) & ~3)
            if lo >= hi:
                continue
            start = (lo + 3) & ~3
            count = (hi - start) // 4
            values = struct.unpack_from('<%dI' % count, self.data, offset + (start - vaddr))
            for index, value in enumerate(values):
                yield start + index * 4, value


def read_pnach(path, sections):
    """[(address, value)] of the `patch=1,EE,<address>,word,<value>` lines under the named
    sections of a PCSX2 patch file (sections None: every line of the file)."""
    everything = sections is None
    wanted = set(sections or ())
    found, words, section = set(), [], None
    with open(path, errors='replace') as source:
        for line in source:
            line = line.strip()
            match = re.match(r'\[(.*)\]$', line)
            if match:
                section = match.group(1)
                continue
            match = re.match(r'patch=1,EE,([0-9a-fA-F]+),(\w+),([0-9a-fA-F]+)', line)
            if not match or not (everything or section in wanted):
                continue
            if match.group(2) != 'word':
                raise SystemExit('pnach: only word patches are handled (%s)' % line)
            found.add(section)
            words.append((int(match.group(1), 16) & 0x1FFFFFFF, int(match.group(3), 16)))
    missing = wanted - found
    if missing:
        raise SystemExit('pnach: no such section: %s' % '; '.join(sorted(missing)))
    return words


# ---------------------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------------------

def control_kind(w):
    """None, or one of: 'j', 'jal', 'jr', 'jalr', 'b' (conditional or not), 'bl' (likely)."""
    op = w >> 26
    if op == 2:
        return 'j'
    if op == 3:
        return 'jal'
    if op == 0:
        fn = w & 63
        if fn == 8:
            return 'jr'
        if fn == 9:
            return 'jalr'
        return None
    if op in (4, 5, 6, 7):
        return 'b'
    if op in (0x14, 0x15, 0x16, 0x17):
        return 'bl'
    if op == 1:
        code = (w >> 16) & 31
        if code in (0, 1):
            return 'b'
        if code in (2, 3):
            return 'bl'
        if code in (0x10, 0x11, 0x12, 0x13):
            return 'bal'
        return None
    if op == 0x11 and ((w >> 21) & 31) == 8:
        code = (w >> 16) & 31
        if code in (0, 1):
            return 'b'
        if code in (2, 3):
            return 'bl'
    return None


def branch_target(pc, w):
    return (pc + 4 + (sx16(w) << 2)) & 0xFFFFFFFF


def jump_target(pc, w):
    return ((pc + 4) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)


def always_taken(w):
    """A conditional branch that is in fact unconditional."""
    op, rs, rt = w >> 26, (w >> 21) & 31, (w >> 16) & 31
    if op == 4 and rs == rt:                   # beq x, x
        return True
    if op == 1 and rt == 1 and rs == 0:        # bgez $zero
        return True
    if op == 6 and rs == 0:                    # blez $zero
        return True
    return False


def R(n):
    return 'c->r[%d]' % n if n else '0ull'


def setr(n, expr):
    if n == 0:
        return '(void)(%s);' % expr
    return 'c->r[%d] = %s;' % (n, expr)


def ea(w):
    rs, imm = (w >> 21) & 31, sx16(w)
    if rs == 0:
        return '0x%xu' % (imm & 0xFFFFFFFF)
    if imm == 0:
        return '(u32)c->r[%d]' % rs
    return '((u32)c->r[%d] + 0x%xu)' % (rs, imm & 0xFFFFFFFF)


MMI0 = {0x00: 'paddw', 0x01: 'psubw', 0x02: 'pcgtw', 0x03: 'pmaxw', 0x04: 'paddh', 0x05: 'psubh',
        0x06: 'pcgth', 0x07: 'pmaxh', 0x08: 'paddb', 0x09: 'psubb', 0x0A: 'pcgtb', 0x10: 'paddsw',
        0x11: 'psubsw', 0x12: 'pextlw', 0x13: 'ppacw', 0x14: 'paddsh', 0x15: 'psubsh',
        0x16: 'pextlh', 0x17: 'ppach', 0x18: 'paddsb', 0x19: 'psubsb', 0x1A: 'pextlb',
        0x1B: 'ppacb'}
MMI1 = {0x02: 'pceqw', 0x03: 'pminw', 0x06: 'pceqh', 0x07: 'pminh', 0x0A: 'pceqb', 0x10: 'padduw',
        0x11: 'psubuw', 0x12: 'pextuw', 0x14: 'padduh', 0x15: 'psubuh', 0x16: 'pextuh',
        0x18: 'paddub', 0x19: 'psubub', 0x1A: 'pextub', 0x1B: 'qfsrv'}
MMI2 = {0x0E: 'pcpyld', 0x12: 'pand', 0x13: 'pxor'}
MMI3 = {0x0E: 'pcpyud', 0x12: 'por', 0x13: 'pnor', 0x1B: 'pcpyh'}


def simple(pc, w):
    """C++ statement(s) for one instruction that is not a branch or jump."""
    if w == 0:
        return ';'
    op = w >> 26
    rs, rt, rd, sa = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31, (w >> 6) & 31
    imm = sx16(w)
    uimm = w & 0xFFFF
    bad = 'rt_unimpl(c, 0x%xu, 0x%08xu);' % (pc, w)

    if op == 0:
        fn = w & 63
        if fn == 0x00:
            return setr(rd, 'SX32((u32)%s << %d)' % (R(rt), sa))
        if fn == 0x02:
            return setr(rd, 'SX32((u32)%s >> %d)' % (R(rt), sa))
        if fn == 0x03:
            return setr(rd, 'SX32((s32)%s >> %d)' % (R(rt), sa))
        if fn == 0x04:
            return setr(rd, 'SX32((u32)%s << (%s & 31))' % (R(rt), R(rs)))
        if fn == 0x06:
            return setr(rd, 'SX32((u32)%s >> (%s & 31))' % (R(rt), R(rs)))
        if fn == 0x07:
            return setr(rd, 'SX32((s32)%s >> (%s & 31))' % (R(rt), R(rs)))
        if fn == 0x0A:
            return 'if (%s == 0) { %s }' % (R(rt), setr(rd, R(rs)))
        if fn == 0x0B:
            return 'if (%s != 0) { %s }' % (R(rt), setr(rd, R(rs)))
        if fn == 0x0C:
            return 'rt_syscall(c, 0x%xu);' % pc
        if fn == 0x0D:
            return 'rt_break(c, 0x%xu, %du);' % (pc, (w >> 16) & 0x3FF)
        if fn == 0x0F:
            return ';'
        if fn == 0x10:
            return setr(rd, 'c->hi')
        if fn == 0x11:
            return 'c->hi = %s;' % R(rs)
        if fn == 0x12:
            return setr(rd, 'c->lo')
        if fn == 0x13:
            return 'c->lo = %s;' % R(rs)
        if fn == 0x14:
            return setr(rd, '%s << (%s & 63)' % (R(rt), R(rs)))
        if fn == 0x16:
            return setr(rd, '%s >> (%s & 63)' % (R(rt), R(rs)))
        if fn == 0x17:
            return setr(rd, '(u64)((s64)%s >> (%s & 63))' % (R(rt), R(rs)))
        if fn == 0x18:
            return 'op_mult(c, %d, %s, %s, false);' % (rd, R(rs), R(rt))
        if fn == 0x19:
            return 'op_multu(c, %d, %s, %s, false);' % (rd, R(rs), R(rt))
        if fn == 0x1A:
            return 'op_div(c, %s, %s, false);' % (R(rs), R(rt))
        if fn == 0x1B:
            return 'op_divu(c, %s, %s, false);' % (R(rs), R(rt))
        if fn in (0x20, 0x22):
            sign = '+' if fn == 0x20 else '-'
            return ('{ s64 t = (s64)(s32)%s %s (s64)(s32)%s; if (t != (s32)t) rt_trap(c, 0x%xu, "integer overflow"); %s }'
                    % (R(rs), sign, R(rt), pc, setr(rd, '(u64)t')))
        if fn == 0x21:
            if rt == 0:
                return setr(rd, 'SX32((u32)%s)' % R(rs))
            if rs == 0:
                return setr(rd, 'SX32((u32)%s)' % R(rt))
            return setr(rd, 'SX32((u32)%s + (u32)%s)' % (R(rs), R(rt)))
        if fn == 0x23:
            return setr(rd, 'SX32((u32)%s - (u32)%s)' % (R(rs), R(rt)))
        if fn == 0x24:
            return setr(rd, '%s & %s' % (R(rs), R(rt)))
        if fn == 0x25:
            if rt == 0:
                return setr(rd, R(rs))
            if rs == 0:
                return setr(rd, R(rt))
            return setr(rd, '%s | %s' % (R(rs), R(rt)))
        if fn == 0x26:
            return setr(rd, '%s ^ %s' % (R(rs), R(rt)))
        if fn == 0x27:
            return setr(rd, '~(%s | %s)' % (R(rs), R(rt)))
        if fn == 0x28:
            return setr(rd, '(u64)c->sa')
        if fn == 0x29:
            return 'c->sa = (u32)%s;' % R(rs)
        if fn == 0x2A:
            return setr(rd, '(u64)((s64)%s < (s64)%s)' % (R(rs), R(rt)))
        if fn == 0x2B:
            return setr(rd, '(u64)(%s < %s)' % (R(rs), R(rt)))
        if fn in (0x2C, 0x2E):
            builtin = '__builtin_add_overflow' if fn == 0x2C else '__builtin_sub_overflow'
            return ('{ s64 t; if (%s((s64)%s, (s64)%s, &t)) rt_trap(c, 0x%xu, "integer overflow"); %s }'
                    % (builtin, R(rs), R(rt), pc, setr(rd, '(u64)t')))
        if fn == 0x2D:
            if rt == 0:
                return setr(rd, R(rs))
            if rs == 0:
                return setr(rd, R(rt))
            return setr(rd, '%s + %s' % (R(rs), R(rt)))
        if fn == 0x2F:
            return setr(rd, '%s - %s' % (R(rs), R(rt)))
        if fn == 0x38:
            return setr(rd, '%s << %d' % (R(rt), sa))
        if fn == 0x3A:
            return setr(rd, '%s >> %d' % (R(rt), sa))
        if fn == 0x3B:
            return setr(rd, '(u64)((s64)%s >> %d)' % (R(rt), sa))
        if fn == 0x3C:
            return setr(rd, '%s << %d' % (R(rt), sa + 32))
        if fn == 0x3E:
            return setr(rd, '%s >> %d' % (R(rt), sa + 32))
        if fn == 0x3F:
            return setr(rd, '(u64)((s64)%s >> %d)' % (R(rt), sa + 32))
        return bad

    if op == 1:
        if rt == 0x18:
            return 'c->sa = ((u32)%s ^ 0x%xu) & 15;' % (R(rs), uimm)
        if rt == 0x19:
            return 'c->sa = (((u32)%s ^ 0x%xu) & 7) * 2;' % (R(rs), uimm)
        return bad

    if op == 0x08:
        return ('{ s64 t = (s64)(s32)%s + (%d); if (t != (s32)t) rt_trap(c, 0x%xu, "integer overflow"); %s }'
                % (R(rs), imm, pc, setr(rt, '(u64)t')))
    if op == 0x09:
        if rs == 0:
            return setr(rt, '0x%xull' % (imm & 0xFFFFFFFFFFFFFFFF))
        return setr(rt, 'SX32((u32)%s + 0x%xu)' % (R(rs), imm & 0xFFFFFFFF))
    if op == 0x0A:
        return setr(rt, '(u64)((s64)%s < (s64)%d)' % (R(rs), imm))
    if op == 0x0B:
        return setr(rt, '(u64)(%s < 0x%xull)' % (R(rs), imm & 0xFFFFFFFFFFFFFFFF))
    if op == 0x0C:
        return setr(rt, '%s & 0x%xull' % (R(rs), uimm))
    if op == 0x0D:
        return setr(rt, '%s | 0x%xull' % (R(rs), uimm))
    if op == 0x0E:
        return setr(rt, '%s ^ 0x%xull' % (R(rs), uimm))
    if op == 0x0F:
        value = (uimm << 16) & 0xFFFFFFFF
        if value & 0x80000000:
            value |= 0xFFFFFFFF00000000
        return setr(rt, '0x%xull' % value)
    if op == 0x18:
        return ('{ s64 t; if (__builtin_add_overflow((s64)%s, (s64)%d, &t)) rt_trap(c, 0x%xu, "integer overflow"); %s }'
                % (R(rs), imm, pc, setr(rt, '(u64)t')))
    if op == 0x19:
        return setr(rt, '%s + 0x%xull' % (R(rs), imm & 0xFFFFFFFFFFFFFFFF))

    if op == 0x10:
        if rs == 0x00:
            return setr(rt, 'SX32(rt_mfc0(c, 0x%xu, %d))' % (pc, rd))
        if rs == 0x04:
            return 'rt_mtc0(c, 0x%xu, %d, (u32)%s);' % (pc, rd, R(rt))
        if rs == 0x10 and (w & 63) == 0x38:
            return 'rt_mtc0(c, 0x%xu, 12, c->cop0[12] | 0x10000u);' % pc
        if rs == 0x10 and (w & 63) == 0x39:
            return 'rt_mtc0(c, 0x%xu, 12, c->cop0[12] & ~0x10000u);' % pc
        if rs == 0x10 and (w & 63) == 0x18:
            # ERET (no delay slot).  The SDK's kernel-mode helpers put $ra into the
            # exception return register and "return from exception" to their caller; the
            # runtime checks that this is what happens and the function returns.
            return 'rt_eret(c, 0x%xu); return;' % pc
        return bad

    if op == 0x11:
        fs, ft, fd = rd, rt, sa
        if rs == 0x00:
            return setr(rt, 'SX32(c->f[%d])' % fs)
        if rs == 0x04:
            return 'c->f[%d] = (u32)%s;' % (fs, R(rt))
        if rs == 0x02:
            if fs == 31:
                return setr(rt, 'SX32(c->fcr31)')
            if fs == 0:
                return setr(rt, '0x2e00ull')
            return bad
        if rs == 0x06:
            if fs != 31:
                return bad
            return 'c->fcr31 = ((u32)%s & 0x0083C078u) | 0x01000001u;' % R(rt)
        if rs == 0x14:
            if (w & 63) == 0x20:
                return 'c->f[%d] = fp_from_int(c->f[%d]);' % (fd, fs)
            return bad
        if rs == 0x10:
            fn = w & 63
            S, T, D = 'c->f[%d]' % fs, 'c->f[%d]' % ft, 'c->f[%d]' % fd
            two = {0x00: 'fp_add', 0x01: 'fp_sub', 0x02: 'fp_mul', 0x03: 'fp_div'}
            if fn in two:
                return '%s = %s(%s, %s);' % (D, two[fn], S, T)
            if fn == 0x04:
                return '%s = fp_sqrt(%s);' % (D, T)
            if fn == 0x05:
                return '%s = %s & 0x7FFFFFFFu;' % (D, S)
            if fn == 0x06:
                return '%s = %s;' % (D, S)
            if fn == 0x07:
                return '%s = %s ^ 0x80000000u;' % (D, S)
            if fn == 0x16:
                return '%s = fp_rsqrt(%s, %s);' % (D, S, T)
            acc = {0x18: 'fp_add', 0x19: 'fp_sub', 0x1A: 'fp_mul'}
            if fn in acc:
                return 'c->acc = %s(%s, %s);' % (acc[fn], S, T)
            if fn in (0x1C, 0x1D, 0x1E, 0x1F):
                dest = D if fn in (0x1C, 0x1D) else 'c->acc'
                oper = 'fp_add' if fn in (0x1C, 0x1E) else 'fp_sub'
                return '%s = %s(c->acc, fp_mul(%s, %s));' % (dest, oper, S, T)
            if fn == 0x24:
                return '%s = fp_to_int(%s);' % (D, S)
            if fn == 0x28:
                return '%s = fp_max(%s, %s);' % (D, S, T)
            if fn == 0x29:
                return '%s = fp_min(%s, %s);' % (D, S, T)
            if fn == 0x30:
                return 'fp_setc(c, false);'
            if fn == 0x32:
                return 'fp_setc(c, fp_eq(%s, %s));' % (S, T)
            if fn == 0x34:
                return 'fp_setc(c, fp_lt(%s, %s));' % (S, T)
            if fn == 0x36:
                return 'fp_setc(c, fp_le(%s, %s));' % (S, T)
            return bad
        return bad

    if op in (0x12, 0x36, 0x3E):
        return 'rt_cop2(c, 0x%xu, 0x%08xu);' % (pc, w)

    if op == 0x1A:
        return 'op_ldl(c, %d, %s);' % (rt, ea(w))
    if op == 0x1B:
        return 'op_ldr(c, %d, %s);' % (rt, ea(w))

    if op == 0x1C:
        fn = w & 63
        if fn in (0x00, 0x01):
            return 'op_madd(c, %d, %s, %s, %s);' % (rd, R(rs), R(rt), 'true' if fn else 'false')
        if fn == 0x04:
            return 'mmi_plzcw(c, %d, %d);' % (rd, rs)
        if fn == 0x10:
            return setr(rd, 'c->hi1')
        if fn == 0x11:
            return 'c->hi1 = %s;' % R(rs)
        if fn == 0x12:
            return setr(rd, 'c->lo1')
        if fn == 0x13:
            return 'c->lo1 = %s;' % R(rs)
        if fn == 0x18:
            return 'op_mult(c, %d, %s, %s, true);' % (rd, R(rs), R(rt))
        if fn == 0x19:
            return 'op_multu(c, %d, %s, %s, true);' % (rd, R(rs), R(rt))
        if fn == 0x1A:
            return 'op_div(c, %s, %s, true);' % (R(rs), R(rt))
        if fn == 0x1B:
            return 'op_divu(c, %s, %s, true);' % (R(rs), R(rt))
        if fn in (0x34, 0x36, 0x37):
            return 'mmi_shift_h(c, %d, %d, %d, %d);' % (rd, rt, sa, {0x34: 0, 0x36: 1, 0x37: 2}[fn])
        if fn in (0x3C, 0x3E, 0x3F):
            return 'mmi_shift_w(c, %d, %d, %d, %d);' % (rd, rt, sa, {0x3C: 0, 0x3E: 1, 0x3F: 2}[fn])
        table = {0x08: MMI0, 0x28: MMI1, 0x09: MMI2, 0x29: MMI3}.get(fn)
        if table is not None and sa in table:
            return 'mmi_%s(c, %d, %d, %d);' % (table[sa], rd, rs, rt)
        return bad

    if op == 0x1E:
        return 'op_lq(c, %d, %s);' % (rt, ea(w))
    if op == 0x1F:
        return 'op_sq(c, %d, %s);' % (rt, ea(w))
    if op == 0x20:
        return setr(rt, '(u64)(s64)(s8)LD8(%s)' % ea(w))
    if op == 0x21:
        return setr(rt, '(u64)(s64)(s16)LD16(%s)' % ea(w))
    if op == 0x22:
        return 'op_lwl(c, %d, %s);' % (rt, ea(w))
    if op == 0x23:
        return setr(rt, 'SX32(LD32(%s))' % ea(w))
    if op == 0x24:
        return setr(rt, '(u64)LD8(%s)' % ea(w))
    if op == 0x25:
        return setr(rt, '(u64)LD16(%s)' % ea(w))
    if op == 0x26:
        return 'op_lwr(c, %d, %s);' % (rt, ea(w))
    if op == 0x27:
        return setr(rt, '(u64)LD32(%s)' % ea(w))
    if op == 0x28:
        return 'ST8(%s, (u8)%s);' % (ea(w), R(rt))
    if op == 0x29:
        return 'ST16(%s, (u16)%s);' % (ea(w), R(rt))
    if op == 0x2A:
        return 'op_swl(c, %d, %s);' % (rt, ea(w))
    if op == 0x2B:
        return 'ST32(%s, (u32)%s);' % (ea(w), R(rt))
    if op == 0x2C:
        return 'op_sdl(c, %d, %s);' % (rt, ea(w))
    if op == 0x2D:
        return 'op_sdr(c, %d, %s);' % (rt, ea(w))
    if op == 0x2E:
        return 'op_swr(c, %d, %s);' % (rt, ea(w))
    if op in (0x2F, 0x33):
        return ';'
    if op == 0x31:
        return 'c->f[%d] = LD32(%s);' % (rt, ea(w))
    if op == 0x37:
        return setr(rt, 'LD64(%s)' % ea(w))
    if op == 0x39:
        return 'ST32(%s, c->f[%d]);' % (ea(w), rt)
    if op == 0x3F:
        return 'ST64(%s, %s);' % (ea(w), R(rt))
    return bad


# Relocatable tables (--reloc FILE, reloc.py): the decisions of the unit being emitted, {pc: k}; the statements of
# those instructions get g_reloc[k] added to the address they form.
RELOC_DECIDE = {}
RELOC_MISSED = []
_simple_plain = simple


RELOC_SITES = {}         # --reloc-sites: instructions whose immediate 4 is the number of player slots {pc: kind}
RELOC_SITES_DONE = set()


def simple(pc, w):  # noqa: F811 (the plain one wrapped)
    text = _simple_plain(pc, w)
    if pc in RELOC_SITES:
        moved = reloc.slots(pc, w, text, RELOC_SITES[pc])
        if moved is None:
            RELOC_MISSED.append(pc)
        else:
            RELOC_SITES_DONE.add(pc)
            text = moved
    k = RELOC_DECIDE.get(pc)
    if k is None:
        return text
    moved = reloc.apply(pc, w, text, k, ea)
    if moved is None:
        RELOC_MISSED.append(pc)
        return text
    return moved


def branch_condition(w):
    op, rs, rt = w >> 26, (w >> 21) & 31, (w >> 16) & 31
    if op in (4, 0x14):
        if rs == rt:
            return 'true'
        return '%s == %s' % (R(rs), R(rt))
    if op in (5, 0x15):
        if rs == rt:
            return 'false'
        return '%s != %s' % (R(rs), R(rt))
    if op in (6, 0x16):
        return '(s64)%s <= 0' % R(rs)
    if op in (7, 0x17):
        return '(s64)%s > 0' % R(rs)
    if op == 1:
        if rt in (0, 2):
            return '(s64)%s < 0' % R(rs)
        return '(s64)%s >= 0' % R(rs)
    if op == 0x11:
        if rt in (0, 2):
            return '!(c->fcr31 & FCR31_C)'
        return '(c->fcr31 & FCR31_C) != 0'
    raise ValueError('not a branch: %08x' % w)


# ---------------------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------------------

class Unit:
    __slots__ = ('start', 'end', 'labels', 'entries', 'computed', 'gap', 'next_pc', 'hle', 'local', 'pieces', 'runoff')

    def __init__(self, start, end, gap=False, pieces=None):
        self.start, self.end, self.gap = start, end, gap
        self.labels = set()
        self.entries = {start}
        self.computed = False
        self.next_pc = None
        self.hle = False
        self.local = False      # merged cluster: calls inside the unit are jumps
        # A merged cluster whose members lie far apart is not one address range but
        # several: [(start, end), ...] in address order (None: the one range start-end).
        # `start` is then the first piece's start and `end` the last piece's end.
        self.pieces = pieces
        self.runoff = {}        # end of a piece that is not the last -> where execution runs on to (or None)

    def ranges(self):
        return self.pieces if self.pieces else [(self.start, self.end)]

    def contains(self, addr):
        if not self.pieces:
            return self.start <= addr < self.end
        return any(lo <= addr < hi for lo, hi in self.pieces)

    def size(self):
        return sum(hi - lo for lo, hi in self.ranges())


def walk(image, unit):
    """Yield (pc, word, kind, delay_pc, delay_word) for every instruction slot of the unit
    in emission order; a branch consumes its delay slot.  After the walk unit.next_pc is
    the address execution reaches when it runs off the end (None when it cannot)."""
    ranges = unit.ranges()
    for number, (lo, hi) in enumerate(ranges):
        pc = lo
        open_end = True
        while pc < hi:
            w = image.word(pc)
            kind = control_kind(w)
            if kind is None:
                yield pc, w, None, None, None
                open_end = True
                pc += 4
                continue
            dpc = pc + 4
            dw = image.word(dpc)
            if dw is None:
                dw = 0
            yield pc, w, kind, dpc, dw
            open_end = not (kind in ('j', 'jr') or (kind == 'b' and always_taken(w))
                            or (kind == 'jalr' and ((w >> 11) & 31) == 0))
            pc += 8
        if number + 1 < len(ranges):
            unit.runoff[hi] = pc if open_end else None
        else:
            unit.next_pc = pc if open_end else None


def build_units(image, funcs_path):
    """Units from the function table.  A row may list several ranges; ranges of one function
    that are separated only by padding words are joined, a range that lies elsewhere (other
    functions in between) becomes a unit of its own, entered by the branches that lead to
    it."""
    ranges = []
    rows = 0
    with open(funcs_path) as source:
        for line in source:
            parts = line.rstrip('\n').split('\t')
            if len(parts) < 3 or line.startswith('#'):
                continue
            rows += 1
            owner = int(parts[0], 16)
            for item in parts[2].split(','):
                lo, hi = (int(x, 16) for x in item.split('-'))
                ranges.append((lo, (hi + 4) & ~3, owner))
    ranges.sort()
    units = []
    cursor = image.text_lo
    clipped = 0
    owners = {}

    def add_gap(lo, hi):
        while lo < hi and image.word(lo) == 0:
            lo += 4
        while hi > lo and image.word(hi - 4) == 0:
            hi -= 4
        if lo < hi:
            units.append(Unit(lo, hi, gap=True))

    for lo, hi, owner in ranges:
        if lo < cursor:                 # overlaps the previous range: keep the remainder
            clipped += 1
            lo = cursor
            if lo >= hi:
                continue
        previous = units[-1] if units else None
        if (previous is not None and not previous.gap and owners.get(previous.start) == owner
                and lo >= cursor and all(image.word(a) == 0 for a in range(cursor, lo, 4))):
            previous.end = hi
            cursor = hi
            continue
        if lo > cursor:
            add_gap(cursor, lo)
        units.append(Unit(lo, hi))
        owners[lo] = owner
        cursor = hi
    if cursor < image.text_hi:
        add_gap(cursor, image.text_hi)
    # a row whose address is not the start of its first range still names an entry
    starts = [u.start for u in units]
    for owner in set(owners.values()):
        index = bisect.bisect_right(starts, owner) - 1
        if index >= 0 and units[index].start <= owner < units[index].end:
            units[index].entries.add(owner)
    return units, rows, clipped


def analyse(image, units, extra=()):
    spans = sorted((lo, hi, unit) for unit in units for lo, hi in unit.ranges())
    starts = [span[0] for span in spans]

    def unit_of(addr):
        index = bisect.bisect_right(starts, addr) - 1
        if index >= 0 and spans[index][0] <= addr < spans[index][1]:
            return spans[index][2]
        return None

    outside = set()          # addresses something outside their unit transfers to
    stats = {'jal': 0, 'computed_units': 0, 'data_refs': 0, 'code_refs': 0, 'no_unit': 0}

    for unit in units:
        after_return = False
        for pc, w, kind, dpc, dw in walk(image, unit):
            if unit.gap and after_return and w != 0:
                unit.entries.add(pc)
                after_return = False
            if kind is None:
                continue
            if kind in ('b', 'bl'):
                target = branch_target(pc, w)
                if unit.contains(target):
                    unit.labels.add(target)
                else:
                    outside.add(target)
            elif kind == 'j':
                target = jump_target(pc, w)
                if unit.contains(target):
                    unit.labels.add(target)
                else:
                    outside.add(target)
            elif kind == 'jal':
                target = jump_target(pc, w)
                if unit.local and unit.contains(target):
                    unit.labels.add(target)
                    unit.labels.add(pc + 8)
                else:
                    outside.add(target)
                stats['jal'] += 1
            elif kind == 'jr':
                if ((w >> 21) & 31) != 31 or unit.local:
                    unit.computed = True
                else:
                    after_return = True
            elif kind == 'jalr':
                if ((w >> 11) & 31) == 0:
                    unit.computed = True
        if unit.next_pc is not None:
            outside.add(unit.next_pc)
        for target in unit.runoff.values():         # a piece that runs off its end
            if target is not None:
                if unit.contains(target):
                    unit.labels.add(target)
                else:
                    outside.add(target)

    # addresses held in data words, and addresses formed by lui + addiu/ori in code
    refs = set()
    for _addr, value in image.data_words():
        if image.text_lo <= value < image.text_hi and not value & 3:
            refs.add(value)
    stats['data_refs'] = len(refs)
    code_refs = set()
    for unit in units:
        upper = {}
        for pc in (a for lo, hi in unit.ranges() for a in range(lo, hi, 4)):
            w = image.word(pc)
            op, rs, rt = w >> 26, (w >> 21) & 31, (w >> 16) & 31
            if op == 0x0F:
                upper[rt] = (w & 0xFFFF) << 16
            elif op in (0x09, 0x0D) and rs in upper:
                value = (upper[rs] + sx16(w)) & 0xFFFFFFFF if op == 0x09 else upper[rs] | (w & 0xFFFF)
                if image.text_lo <= value < image.text_hi and not value & 3:
                    code_refs.add(value)
            if control_kind(w) in ('jal', 'jalr'):
                upper = {}
    stats['code_refs'] = len(code_refs)

    for addr in outside | refs | code_refs | set(extra):
        unit = unit_of(addr)
        if unit is None:
            stats['no_unit'] += 1
            continue
        unit.entries.add(addr)
        unit.labels.add(addr)
    for unit in units:
        unit.labels |= unit.entries
        if unit.computed:
            stats['computed_units'] += 1
    stats['outside'] = outside
    return unit_of, stats


MERGE_SLACK = 16        # units between the members of a cluster that are taken along (see merge_entangled)


def merge_entangled(image, units):
    """Functions that jump into the middle of one another (hand-written assembly with
    private calling conventions; a body shared by several functions) cannot be separate C++
    functions: a branch from A into B's middle would run the rest of B in a nested call
    and then come back to A.  Such clusters are merged into one unit each, in which calls
    between the members are plain jumps and every return goes through the unit's dispatch
    switch - a small interpreter loop for control flow only.  Returns the new unit list
    and the merged spans."""
    starts = [u.start for u in units]

    def index_of(addr):
        index = bisect.bisect_right(starts, addr) - 1
        if index >= 0 and units[index].start <= addr < units[index].end:
            return index
        return None

    parent = list(range(len(units)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for index, unit in enumerate(units):
        for pc, w, kind, dpc, dw in walk(image, unit):
            if kind in ('b', 'bl'):
                target = branch_target(pc, w)
            elif kind == 'j':
                target = jump_target(pc, w)
            else:
                continue
            if unit.start <= target < unit.end:
                continue
            other = index_of(target)
            if other is not None and units[other].start != target:
                parent[find(index)] = find(other)
    groups = {}
    for index in range(len(units)):
        root = find(index)
        groups.setdefault(root, []).append(index)
    # A cluster whose members lie close together takes the units between them along (the
    # few that lie there are padding and bodies shared with the members): one address
    # range.  A cluster whose members lie far apart - a patch that jumps to a routine
    # written into the body of a function elsewhere, and back - takes its members only:
    # several ranges in one unit.  (Taking the whole span made one C++ function of every
    # function between the two.)
    clusters = []                            # sets of unit indices
    for members in groups.values():
        if len(members) < 2:
            continue
        lo, hi = min(members), max(members)
        if (hi - lo + 1) - len(members) <= MERGE_SLACK:
            clusters.append(set(range(lo, hi + 1)))
        else:
            clusters.append(set(members))
    changed = True
    while changed:                           # clusters that share a unit join
        changed = False
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                if clusters[a] & clusters[b]:
                    clusters[a] |= clusters[b]
                    del clusters[b]
                    changed = True
                    break
            if changed:
                break
    taken = {}
    report = []
    for cluster in clusters:
        indices = sorted(cluster)
        runs = []                            # consecutive indices: one address range
        for index in indices:
            if runs and index == runs[-1][1] + 1:
                runs[-1][1] = index
            else:
                runs.append([index, index])
        pieces = [(units[lo].start, units[hi].end) for lo, hi in runs]
        unit = Unit(pieces[0][0], pieces[-1][1], pieces=pieces if len(pieces) > 1 else None)
        unit.local = True
        for index in indices:
            unit.entries |= units[index].entries
            taken[index] = None
        taken[indices[0]] = unit
        report.append((unit.start, unit.end, len(indices)) if len(pieces) == 1
                      else (unit.start, unit.end, len(indices), len(pieces)))
    out = []
    for index, unit in enumerate(units):
        if index in taken:
            if taken[index] is not None:
                out.append(taken[index])
        else:
            out.append(unit)
    report.sort()
    return out, report


# ---------------------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------------------

def emit_unit(image, unit, unit_of, known_entries):
    out = []
    dispatch = unit.computed or len(unit.entries) > 1
    name = 'fn_%08x' % unit.start

    def go(target, backward_from=None):
        """Transfer to a static target."""
        if unit.contains(target):
            if backward_from is not None and target <= backward_from:
                return 'BUDGET(); goto L_%08x;' % target
            return 'goto L_%08x;' % target
        if target in known_entries:
            return '{ fn_%08x(c); return; }' % target
        return '{ rt_call(c, 0x%xu); return; }' % target

    def call(target, site):
        if target in known_entries:
            return 'CALL(fn_%08x, 0x%xu, 0x%xu);' % (target, target, site)
        return 'CALLR(0x%xu, 0x%xu);' % (target, site)

    piece_starts = {lo: number for number, (lo, hi) in enumerate(unit.ranges()) if number}
    for pc, w, kind, dpc, dw in walk(image, unit):
        if pc in piece_starts:
            # the piece before this one ended: where it runs on to is not the next line
            before = unit.ranges()[piece_starts[pc] - 1][1]
            target = unit.runoff.get(before)
            if target is not None:
                out.append('    %s' % go(target))
        label = 'L_%08x: ' % pc if pc in unit.labels else ''
        if kind is None:
            out.append('    %s%s' % (label, simple(pc, w)))
            continue
        if control_kind(dw) is not None:
            delay = 'rt_trap(c, 0x%xu, "branch in a delay slot");' % dpc
        else:
            delay = simple(dpc, dw)
        rs, rd = (w >> 21) & 31, (w >> 11) & 31
        if kind == 'j':
            text = '%s %s' % (delay, go(jump_target(pc, w), pc))
        elif kind == 'jal' and unit.local and unit.contains(jump_target(pc, w)):
            target = jump_target(pc, w)
            text = 'c->r[31] = 0x%xull; %s LOCALCALL(L_%08x, 0x%xu, 0x%xu);' % (pc + 8, delay, target, target, pc)
        elif kind == 'jal':
            text = 'c->r[31] = 0x%xull; %s %s' % (pc + 8, delay, call(jump_target(pc, w), pc))
        elif kind == 'jr' and rs == 31 and not unit.local:
            text = '%s return;' % delay
        elif kind == 'jr' or (kind == 'jalr' and rd == 0):
            # in a merged unit a return may lead to a call site inside the unit
            text = '{ u32 t = (u32)%s; %s pc = t; ret = %s; goto dispatch; }' % (
                R(rs), delay, 'true' if (kind == 'jr' and rs == 31) else 'false')
        elif kind == 'jalr':
            text = '{ u32 t = (u32)%s; c->r[%d] = 0x%xull; %s CALLR(t, 0x%xu); }' % (R(rs), rd, pc + 8, delay, pc)
        elif kind == 'bal':
            text = 'rt_unimpl(c, 0x%xu, 0x%08xu);' % (pc, w)
        else:
            cond = branch_condition(w)
            target = go(branch_target(pc, w), pc)
            if cond == 'true':
                text = '%s %s' % (delay, target)
            elif cond == 'false':
                text = delay if kind == 'b' else ';'
            elif kind == 'bl':
                text = 'if (%s) { %s %s }' % (cond, delay, target)
            else:
                text = '{ bool t = %s; %s if (t) { %s } }' % (cond, delay, target)
        out.append('    %s%s' % (label, text))
        if dpc in unit.labels and unit.contains(dpc):
            # something jumps straight to the delay slot: a second copy, reached only by label
            out.append('    goto S_%08x; L_%08x: %s S_%08x:;' % (dpc, dpc, delay, dpc))
    if unit.next_pc is not None:
        target = unit.next_pc
        if target in known_entries:
            out.append('    fn_%08x(c); return;' % target)
        else:
            out.append('    rt_call(c, 0x%xu); return;' % target)

    lines = []
    if dispatch:
        lines.append('static void body_%08x(Ctx* c, u32 pc) {' % unit.start)
        lines.append('    const u32 ra_in = (u32)c->r[31];')
        lines.append('    bool ret = false;')
        lines.append('dispatch:')
        lines.append('    switch (pc) {')
        for target in sorted(unit.labels):
            lines.append('    case 0x%xu: goto L_%08x;' % (target, target))
        # a jump to the address this body was called from is a return made through
        # another register; anything else outside the unit is a tail call
        lines.append('    default: if (ret || pc == ra_in) return; rt_call(c, pc); return;')
        lines.append('    }')
        lines.extend(out)
        lines.append('}')
        for entry in sorted(unit.entries):
            prefix = 'orig_' if (unit.hle and entry == unit.start) else 'fn_'
            lines.append('void %s%08x(Ctx* c) { body_%08x(c, 0x%xu); }' % (prefix, entry, unit.start, entry))
    else:
        prefix = 'orig_' if unit.hle else 'fn_'
        lines.append('void %s%08x(Ctx* c) {' % (prefix, unit.start))
        lines.extend(out)
        lines.append('}')
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description='Translate the game executable to C++.')
    parser.add_argument('--elf', default=os.path.join(ROOT, 'SLUS_209.73'))
    parser.add_argument('--funcs', default=os.path.join(ROOT, 'ghidra_funcs.tsv'))
    parser.add_argument('--out', default=os.path.join(ROOT, 'local', 'recomp-out', 'gen'))
    parser.add_argument('--hle', default=os.path.join(HERE, 'hle.txt'),
                        help='file of hex addresses whose fn_ is supplied by the runtime; the '
                             'translation is still emitted, as orig_<address>')
    parser.add_argument('--entries', default=os.path.join(HERE, 'entries.txt'),
                        help='file of extra hex addresses to make entries (a loop head the runtime '
                             'enters when it resumes a memory image, for example)')
    parser.add_argument('--chunk', type=int, default=0x10000, help='bytes of game code per C++ file')
    parser.add_argument('--pnach', help='a PCSX2 patch file: the word patches of the named sections are written into '
                        'the image before it is translated (translated code is fixed when it is built, so a code '
                        'patch has to be there), and into <out>/patches.cpp for the runtime to write into memory')
    parser.add_argument('--sections', help='with --pnach: a file of section names, one per line (# comments)')
    parser.add_argument('--section', action='append', default=[], help='with --pnach: one section name; repeatable')
    parser.add_argument('--extra-pnach', action='append', default=[],
                        help='one more patch file, applied whole after --pnach (repeatable): a patch kept outside the '
                        'repository, such as the local sign-in skip.  Its words go into the image and into patches.cpp '
                        'after the words of --pnach, and are not counted in recomp_patch_set_words()')
    parser.add_argument('--reloc', help='a file of table ranges (reloc.py) whose addresses the translation forms '
                        'with g_reloc[k] added: 0 unless a mode has moved the table at run time')
    parser.add_argument('--reloc-sites', help='with --reloc: a file of instruction addresses (reloc.read_sites) whose '
                        'immediate 4 is the number of player slots; emitted as g_party8_slots (4, or 8 in a game of five to eight)')
    parser.add_argument('--hle-add', action='append', default=[],
                        help='one more file of addresses supplied by whoever links the translation (repeatable), '
                        'added to --hle: a module such as tools/recomp/net keeps its own list')
    args = parser.parse_args(argv)

    if not os.path.isfile(args.elf):
        print('no executable at %s (bring your own SLUS_209.73)' % args.elf)
        return 0
    image = Image(args.elf)
    patch_words = []
    if args.pnach:
        sections = list(args.section)
        if args.sections:
            with open(args.sections) as source:
                sections += [line.strip() for line in source if line.strip() and not line.startswith('#')]
        patch_words = read_pnach(args.pnach, sections)
        image.patch(patch_words)
        print('patched: %d words of %d sections' % (len(patch_words), len(sections)))
    set_words = len(patch_words)        # the words every player has to have the same
    for path in args.extra_pnach:
        extra_words = read_pnach(path, None)
        image.patch(extra_words)
        patch_words += extra_words
        print('patched: %d more words from a local patch file' % len(extra_words))
    units, rows, clipped = build_units(image, args.funcs)
    table_units = sum(1 for u in units if not u.gap)
    gap_units = [u for u in units if u.gap]
    units, merged = merge_entangled(image, units)
    extra = set()
    if args.entries and os.path.isfile(args.entries):
        after = set()
        with open(args.entries) as source:
            for line in source:
                fields = line.split('#')[0].split()
                if len(fields) == 2 and fields[0] == 'after':
                    after.add(int(fields[1], 16))
                elif fields:
                    extra.add(int(fields[0], 16))
        if after:           # the return address of every call to these functions
            for index, w in enumerate(image.words):
                if w >> 26 == 3 and ((w & 0x03FFFFFF) << 2) in after:
                    extra.add(image.text_lo + index * 4 + 8)
    unit_of, stats = analyse(image, units, extra)

    hle = set()
    for path in [args.hle] + args.hle_add:
        if not (path and os.path.isfile(path)):
            continue
        with open(path) as source:
            for line in source:
                line = line.split('#')[0].strip()
                if line:
                    hle.add(int(line.split()[0], 16))
    for unit in units:
        if unit.start in hle:
            unit.hle = True
    missing_hle = hle - {u.start for u in units}
    if missing_hle:
        print('warning: HLE addresses that are not unit starts: %s' % ', '.join('%x' % a for a in sorted(missing_hle)))

    known = set()
    for unit in units:
        known |= unit.entries

    os.makedirs(args.out, exist_ok=True)
    stale = {name for name in os.listdir(args.out) if name.endswith(('.cpp', '.h'))}

    def write_if_changed(path, text):
        stale.discard(os.path.basename(path))
        if os.path.isfile(path):
            with open(path) as source:
                if source.read() == text:
                    return
        with open(path, 'w') as sink:
            sink.write(text)

    files = []
    current, current_size, bad = [], 0, 0
    total_ins = 0

    def flush():
        nonlocal current, current_size
        if not current:
            return
        path = os.path.join(args.out, 'c_%03d.cpp' % len(files))
        write_if_changed(path, '// generated by tools/recomp/recomp.py from the game executable - do not commit\n'
                         '#include "recomp.h"\n#include "funcs.h"\n' + '\n'.join(current) + '\n')
        files.append(path)
        current, current_size = [], 0

    reloc_ranges = reloc.read_ranges(args.reloc) if args.reloc else []
    if reloc_ranges and args.reloc_sites:
        RELOC_SITES.update(reloc.read_sites(args.reloc_sites))
    reloc_count, reloc_units = {}, 0
    for unit in units:
        RELOC_DECIDE.clear()
        if reloc_ranges:
            RELOC_DECIDE.update(reloc.analyse_unit(image, unit, walk, control_kind, branch_target, jump_target,
                                                   always_taken, reloc_ranges, set(stats['outside']) | extra))
            if RELOC_DECIDE:
                reloc_units += 1
            for k in RELOC_DECIDE.values():
                reloc_count[k] = reloc_count.get(k, 0) + 1
        lines = emit_unit(image, unit, unit_of, known)
        bad += sum(line.count('rt_unimpl(') for line in lines)
        total_ins += unit.size() // 4
        current.extend(lines)
        current_size += unit.size()
        if current_size >= args.chunk:
            flush()
    flush()

    text = ['// generated - do not commit', '#pragma once']
    text += ['void fn_%08x(Ctx*);' % addr for addr in sorted(known)]
    text += ['void orig_%08x(Ctx*);' % addr for addr in sorted(hle & {u.start for u in units})]
    if reloc_ranges:
        text += ['extern u32 g_reloc[%d];' % reloc.TABLES + '   // reloc.py: added to the addresses of the moved tables; 0 = where the game has them',
                 'extern u32 g_party8_slots;    // reloc.py: the number of player slots at the hard-coded fours (4, or 8)']
    write_if_changed(os.path.join(args.out, 'funcs.h'), '\n'.join(text) + '\n')
    text = ['// generated - do not commit', '#include "recomp.h"', '#include "funcs.h"',
            'const RecompEntry g_recomp_entries[] = {']
    text += ['    {0x%xu, fn_%08x},' % (addr, addr) for addr in sorted(known)]
    text += ['};', 'const unsigned g_recomp_entry_count = %d;' % len(known)]
    if reloc_ranges:
        # the moved tables: what reloc.py relocates, for the module that moves them (app/party8.cpp; weak there)
        text += ['u32 g_reloc[%d];' % reloc.TABLES, 'u32 g_reloc_spans[%d][2] = {' % reloc.TABLES]
        text += ['    {0x%xu, 0x%xu},' % (lo, hi) if any(r[0] == k for r in reloc_ranges) else '    {0u, 0u},'
                 for k in range(reloc.TABLES) for (lo, hi) in [next(((r[1], r[2]) for r in reloc_ranges if r[0] == k), (0, 0))]]
        text += ['};', 'unsigned g_reloc_count = %d;' % len(reloc_ranges), 'u32 g_party8_slots = 4;']
    write_if_changed(os.path.join(args.out, 'table.cpp'), '\n'.join(text) + '\n')
    # a program that does not replace a function on the HLE list gets the translation
    text = ['// generated - do not commit', '#include "recomp.h"', '#include "funcs.h"']
    text += ['__attribute__((weak)) void fn_%08x(Ctx* c) { orig_%08x(c); }' % (addr, addr)
             for addr in sorted(hle & {u.start for u in units})]
    write_if_changed(os.path.join(args.out, 'hle_weak.cpp'), '\n'.join(text) + '\n')
    if patch_words:
        # the same words for memory: the runtime loads the unpatched executable and writes
        # these over it (data words; and code words, so that memory reads as it does on a
        # machine that was patched)
        text = ['// generated - do not commit', '#include "recomp.h"', 'unsigned recomp_patches(const u32 (**words)[2]) {',
                '    static const u32 table[][2] = {']
        text += ['        {0x%xu, 0x%08xu},' % word for word in patch_words]
        text += ['    };', '    *words = table;', '    return %d;' % len(patch_words), '}',
                 '// the first so many are the fix set (--pnach); the rest came from --extra-pnach',
                 'unsigned recomp_patch_set_words() { return %d; }' % set_words]
        write_if_changed(os.path.join(args.out, 'patches.cpp'), '\n'.join(text) + '\n')
    for name in stale:
        os.remove(os.path.join(args.out, name))
    with open(os.path.join(args.out, 'units.tsv'), 'w') as sink:
        sink.write('# start\tend\tkind\tentries\tlabels\tdispatch\n')
        for unit in units:
            sink.write('%08x\t%08x\t%s\t%d\t%d\t%d\n' % (
                unit.start, unit.end, 'gap' if unit.gap else 'func', len(unit.entries), len(unit.labels),
                1 if (unit.computed or len(unit.entries) > 1) else 0))

    print('function-table rows: %d (clipped for overlap: %d)' % (rows, clipped))
    print('units before merging: %d from the table, %d gap units holding %d bytes' % (
        table_units, len(gap_units), sum(u.end - u.start for u in gap_units)))
    print('entangled clusters merged into one unit each: %d (%s)' % (
        len(merged), ', '.join('%x-%x: %d units' % m if len(m) == 3 else '%x-%x: %d units in %d separate ranges' % m
                               for m in merged)))
    print('units: %d' % len(units))
    print('instruction slots translated: %d' % total_ins)
    print('entries (fn_ symbols, table slots): %d' % len(known))
    print('units with a computed jump: %d; units with a dispatch switch: %d' % (
        stats['computed_units'], sum(1 for u in units if u.computed or len(u.entries) > 1)))
    print('data words holding a .text address: %d distinct; lui/addiu addresses: %d' % (
        stats['data_refs'], stats['code_refs']))
    print('transfer targets outside every unit: %d' % stats['no_unit'])
    print('instructions emitted as rt_unimpl: %d' % bad)
    if reloc_ranges:
        print('relocated: %d instructions in %d units (%s); not rewritten: %d%s' % (
            sum(reloc_count.values()), reloc_units, ', '.join('table %d: %d' % kv for kv in sorted(reloc_count.items())),
            len(RELOC_MISSED), (' (' + ' '.join('%x' % a for a in RELOC_MISSED[:20]) + ')') if RELOC_MISSED else ''))
    if reloc_ranges:
        # accesses through a pointer into a moved table that land outside it (reloc.CROSSES): such tables must move as
        # one group, or the access is a field next to the table
        with open(os.path.join(args.out, 'reloc-crosses.txt'), 'w') as out:
            for pc in sorted(reloc.CROSSES):
                k, address, other = reloc.CROSSES[pc]
                out.write('%x table %d reaches %x (%s)\n' % (pc, k, address, 'table %d' % other if other is not None else 'no table'))
        print('reached from a pointer into another table: %d accesses (%s)' % (len(reloc.CROSSES), os.path.join(args.out, 'reloc-crosses.txt')))
    if RELOC_SITES:
        print('player-slot fours: %d of %d sites emitted as g_party8_slots%s' % (
            len(RELOC_SITES_DONE), len(RELOC_SITES), ('; not found: ' + ' '.join('%x' % a for a in sorted(set(RELOC_SITES) - RELOC_SITES_DONE)))
            if set(RELOC_SITES) - RELOC_SITES_DONE else ''))
    print('C++ files: %d (+ funcs.h, table.cpp) in %s' % (len(files), args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
