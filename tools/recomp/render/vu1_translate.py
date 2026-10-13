#!/usr/bin/env python3
"""vu1_translate.py - the game's VU1 microprograms, translated ahead of time to C++.

  python3 tools/recomp/render/vu1_translate.py [--stream FILE.rtavs ...] [--elf SLUS_209.73] --out DIR/vu1_fast.cpp
          [--listing FILE] [--entry N,N,...] [--report]

Reads the microprograms out of recorded picture streams (render/stream.h; rta_app's
`app record FILE` writes one): every MPG upload in the VIF1 data, and the main program's
upload packet in a stream that starts with main memory.  Uploads that follow each other
without a gap are one program.  --elf takes the main program from the game's executable
instead (its upload packet at 0x3e5ec0); the two small programs the game loads behind it
are not in the executable as such, so give a stream of a fight as well (fire3 uses both).
A program that is not translated is interpreted, as before.  Writes one C++ function per
program (render/vu1_fast.h says how they are called), straight code
block by block:

  - registers are local variables for the length of a run; a float register is a vector
    of four (render/vu1_simd.h: NEON, SSE2, WebAssembly SIMD or plain C++);
  - the unit's numbers are kept exactly as the interpreter (render/vu1_step.h) keeps
    them: what an arithmetic instruction reads is brought into range (vu_in), what it
    writes is flushed (vu_out), MAX / MINI compare bit patterns; a value the analysis
    below proves to be the result of such an instruction is not brought into range again;
  - the MAC flags of an instruction are kept only where a flag-reading instruction can
    see them (found by walking back from every reader, and from every way out of the
    translated code); the divider's delay and the cycle counter are kept only where a
    read of Q, a divide or a flag reader needs them;
  - anything the translation does not follow (an instruction it does not know, a branch in
    a delay slot, an end bit in an unusual place, a computed jump to an unknown place)
    hands over to the interpreter at that pair, with the machine in the same state.

The output is DERIVED FROM THE GAME: it belongs under local/ (the build scripts look for
local/recomp-out/gen-vu/vu1_fast.cpp), never in the repository.  So does --listing.
Standard library only.
"""
import argparse
import hashlib
import os
import struct
import sys

# ---- instruction kinds (the names of render/vu1_step.h) ----------------------------------
U_NOP, U_ADD, U_SUB, U_MUL, U_MADD, U_MSUB, U_MAX, U_MINI, U_ITOF, U_FTOI, U_CLIP, U_ABS, U_BAD = range(13)
U_NAMES = ['nop', 'add', 'sub', 'mul', 'madd', 'msub', 'max', 'mini', 'itof', 'ftoi', 'clip', 'abs', '??']
S_VEC, S_BC, S_Q, S_I = range(4)
L_NAMES = ('NOP LQ SQ ILW ISW IADDIU ISUBIU FCEQ FCSET FCAND FCOR FSEQ FSSET FSAND FSOR FMEQ FMAND FMOR FCGET B BAL JR JALR IBEQ IBNE IBLTZ '
           'IBGTZ IBLEZ IBGEZ IADD ISUB IADDI IAND IOR MOVE MR32 LQI SQI LQD SQD DIV SQRT RSQRT WAITQ MTIR MFIR ILWR ISWR XTOP XITOP XGKICK BAD').split()
for _k, _n in enumerate(L_NAMES):
    globals()['L_' + _n] = _k
ARITH = (U_ADD, U_SUB, U_MUL, U_MADD, U_MSUB)
COND_BRANCH = (L_IBEQ, L_IBNE, L_IBLTZ, L_IBGTZ, L_IBLEZ, L_IBGEZ)
STATIC_BRANCH = (L_B, L_BAL) + COND_BRANCH
DYNAMIC_BRANCH = (L_JR, L_JALR)
BRANCH = STATIC_BRANCH + DYNAMIC_BRANCH
DIVIDER = (L_DIV, L_SQRT, L_RSQRT)
MAC_READERS = (L_FSAND, L_FSOR, L_FSEQ, L_FMAND, L_FMOR, L_FMEQ)
CLIP_READERS = (L_FCAND, L_FCOR, L_FCEQ, L_FCGET)


class Ins:
    __slots__ = ('n', 'upper', 'lower', 'uop', 'usrc', 'udst', 'udest', 'uft', 'ufs', 'ufd', 'ubc', 'lop', 'ldest', 'lt', 'ls', 'ld',
                 'fsf', 'ftf', 'ibit', 'ebit', 'imm11', 'imm15', 'imm24')


def decode(n, lo, up):
    """One instruction pair, as Vu1::decode (render/vu1.cpp) decodes it."""
    d = Ins()
    d.n, d.upper, d.lower = n, up, lo
    d.ibit, d.ebit = (up >> 31) & 1, (up >> 30) & 1
    d.udest, d.uft, d.ufs, d.ufd, d.ubc = (up >> 21) & 15, (up >> 16) & 31, (up >> 11) & 31, (up >> 6) & 31, up & 3
    op = up & 0x3F
    d.uop, d.usrc, d.udst = U_BAD, S_VEC, 0
    if op < 0x1C:
        d.uop, d.usrc = (U_ADD, U_SUB, U_MADD, U_MSUB, U_MAX, U_MINI, U_MUL)[op >> 2], S_BC
    elif op < 0x28:
        d.uop = (U_MUL, U_MAX, U_MUL, U_MINI, U_ADD, U_MADD, U_ADD, U_MADD, U_SUB, U_MSUB, U_SUB, U_MSUB)[op - 0x1C]
        d.usrc = (S_Q, S_I, S_I, S_I, S_Q, S_Q, S_I, S_I, S_Q, S_Q, S_I, S_I)[op - 0x1C]
    elif op < 0x30:
        d.uop, d.usrc = (U_ADD, U_MADD, U_MUL, U_MAX, U_SUB, U_MSUB, U_BAD, U_MINI)[op - 0x28], S_VEC
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
            d.uop = (U_ADD, U_MADD, U_ADD, U_MADD, U_SUB, U_MSUB, U_SUB, U_MSUB)[sp - 0x20]
            d.usrc = (S_Q, S_Q, S_I, S_I, S_Q, S_Q, S_I, S_I)[sp - 0x20]
        elif 0x28 <= sp < 0x2E and sp != 0x2B:
            d.uop, d.usrc = (U_ADD, U_MADD, U_MUL, U_BAD, U_SUB, U_MSUB)[sp - 0x28], S_VEC
        elif sp == 0x2F:
            d.uop = U_NOP
    d.ldest, d.lt, d.ls, d.ld = (lo >> 21) & 15, (lo >> 16) & 31, (lo >> 11) & 31, (lo >> 6) & 31
    d.fsf, d.ftf = (lo >> 21) & 3, (lo >> 23) & 3
    d.imm11 = (lo & 0x7FF) - (0x800 if lo & 0x400 else 0)
    d.imm15 = ((lo >> 10) & 0x7800) | (lo & 0x7FF)
    d.imm24 = lo & 0xFFFFFF
    lop = lo >> 25
    d.lop = L_BAD
    if d.ibit:
        d.lop = L_NOP
    else:
        table = {0x00: L_LQ, 0x01: L_SQ, 0x04: L_ILW, 0x05: L_ISW, 0x08: L_IADDIU, 0x09: L_ISUBIU, 0x10: L_FCEQ, 0x11: L_FCSET,
                 0x12: L_FCAND, 0x13: L_FCOR, 0x14: L_FSEQ, 0x15: L_FSSET, 0x16: L_FSAND, 0x17: L_FSOR, 0x18: L_FMEQ, 0x1A: L_FMAND,
                 0x1B: L_FMOR, 0x1C: L_FCGET, 0x20: L_B, 0x21: L_BAL, 0x24: L_JR, 0x25: L_JALR, 0x28: L_IBEQ, 0x29: L_IBNE,
                 0x2C: L_IBLTZ, 0x2D: L_IBGTZ, 0x2E: L_IBLEZ, 0x2F: L_IBGEZ}
        if lop in table:
            d.lop = table[lop]
        elif lop == 0x40:
            f = lo & 0x3F
            if f == 0x30:
                d.lop = L_IADD
            elif f == 0x31:
                d.lop = L_ISUB
            elif f == 0x32:
                d.lop = L_IADDI
            elif f == 0x34:
                d.lop = L_IAND
            elif f == 0x35:
                d.lop = L_IOR
            elif f >= 0x3C:
                sp = (d.ld << 2) | (lo & 3)
                d.lop = {0x30: L_MOVE, 0x31: L_MR32, 0x34: L_LQI, 0x35: L_SQI, 0x36: L_LQD, 0x37: L_SQD, 0x38: L_DIV, 0x39: L_SQRT,
                         0x3A: L_RSQRT, 0x3B: L_WAITQ, 0x3C: L_MTIR, 0x3D: L_MFIR, 0x3E: L_ILWR, 0x3F: L_ISWR, 0x68: L_XTOP,
                         0x69: L_XITOP, 0x6C: L_XGKICK}.get(sp, L_BAD)
            if lo == 0x8000033C:
                d.lop = L_NOP
    return d


# ---- where the upper half writes, what both halves read -----------------------------------
def upper_target(d):
    """('acc' | 'vf', register) the upper half writes, or None."""
    if d.uop in (U_NOP, U_CLIP, U_BAD):
        return None
    if d.udst and d.uop <= U_MSUB:
        return ('acc', 0)
    return ('vf', d.uft if d.uop in (U_ITOF, U_FTOI, U_ABS) else d.ufd)


FIELDS = 'xyzw'


def dest_text(mask):
    return ''.join(FIELDS[k] for k in range(4) if mask & (8 >> k))


def disassemble(d):
    up = U_NAMES[d.uop]
    if d.uop == U_NOP:
        text = 'nop'
    elif d.uop == U_BAD:
        text = '?? %08x' % d.upper
    elif d.uop == U_CLIP:
        text = 'clip vf%d, vf%d.w' % (d.ufs, d.uft)
    else:
        target = upper_target(d)
        tname = 'acc' if target[0] == 'acc' else 'vf%d' % target[1]
        if d.uop in (U_ITOF, U_FTOI):
            text = '%s%d.%s %s, vf%d' % (up, d.ubc, dest_text(d.udest), tname, d.ufs)
        elif d.uop == U_ABS:
            text = 'abs.%s %s, vf%d' % (dest_text(d.udest), tname, d.ufs)
        else:
            other = {S_VEC: 'vf%d' % d.uft, S_BC: 'vf%d.%s' % (d.uft, FIELDS[d.ubc]), S_Q: 'Q', S_I: 'I'}[d.usrc]
            text = '%s.%s %s, vf%d, %s' % (up, dest_text(d.udest), tname, d.ufs, other)
    if d.ibit:
        low = 'loi 0x%08x (%g)' % (d.lower, struct.unpack('<f', struct.pack('<I', d.lower))[0])
    else:
        name = L_NAMES[d.lop].lower()
        o = d.lop
        if o == L_NOP:
            low = 'nop'
        elif o in (L_LQ,):
            low = 'lq.%s vf%d, %d(vi%d)' % (dest_text(d.ldest), d.lt, d.imm11, d.ls)
        elif o == L_SQ:
            low = 'sq.%s vf%d, %d(vi%d)' % (dest_text(d.ldest), d.ls, d.imm11, d.lt)
        elif o in (L_LQI, L_LQD):
            low = '%s.%s vf%d, (vi%d)' % (name, dest_text(d.ldest), d.lt, d.ls)
        elif o in (L_SQI, L_SQD):
            low = '%s.%s vf%d, (vi%d)' % (name, dest_text(d.ldest), d.ls, d.lt)
        elif o in (L_ILW, L_ISW):
            low = '%s.%s vi%d, %d(vi%d)' % (name, dest_text(d.ldest), d.lt, d.imm11, d.ls)
        elif o in (L_ILWR, L_ISWR):
            low = '%s.%s vi%d, (vi%d)' % (name, dest_text(d.ldest), d.lt, d.ls)
        elif o in (L_IADDIU, L_ISUBIU):
            low = '%s vi%d, vi%d, %d' % (name, d.lt, d.ls, d.imm15)
        elif o in (L_IADD, L_ISUB, L_IAND, L_IOR):
            low = '%s vi%d, vi%d, vi%d' % (name, d.ld, d.ls, d.lt)
        elif o == L_IADDI:
            low = 'iaddi vi%d, vi%d, %d' % (d.lt, d.ls, d.ld - 32 if d.ld & 16 else d.ld)
        elif o in (L_FCSET, L_FCAND, L_FCOR, L_FCEQ):
            low = '%s 0x%06x' % (name, d.imm24)
        elif o == L_FCGET:
            low = 'fcget vi%d' % d.lt
        elif o in (L_FSAND, L_FSOR, L_FSEQ):
            low = '%s vi%d, 0x%03x' % (name, d.lt, ((d.lower >> 10) & 0x800) | (d.lower & 0x7FF))
        elif o in (L_FMAND, L_FMOR, L_FMEQ):
            low = '%s vi%d, vi%d' % (name, d.lt, d.ls)
        elif o in (L_B, L_BAL):
            low = '%s %s-> %03x' % (name, 'vi%d ' % d.lt if o == L_BAL else '', (d.n + 1 + d.imm11) & 2047)
        elif o in (L_JR, L_JALR):
            low = '%s %svi%d' % (name, 'vi%d, ' % d.lt if o == L_JALR else '', d.ls)
        elif o in (L_IBEQ, L_IBNE):
            low = '%s vi%d, vi%d -> %03x' % (name, d.lt, d.ls, (d.n + 1 + d.imm11) & 2047)
        elif o in COND_BRANCH:
            low = '%s vi%d -> %03x' % (name, d.ls, (d.n + 1 + d.imm11) & 2047)
        elif o in (L_MOVE, L_MR32):
            low = '%s.%s vf%d, vf%d' % (name, dest_text(d.ldest), d.lt, d.ls)
        elif o == L_MTIR:
            low = 'mtir vi%d, vf%d.%s' % (d.lt, d.ls, FIELDS[d.fsf])
        elif o == L_MFIR:
            low = 'mfir.%s vf%d, vi%d' % (dest_text(d.ldest), d.lt, d.ls)
        elif o in (L_XTOP, L_XITOP):
            low = '%s vi%d' % (name, d.lt)
        elif o == L_DIV:
            low = 'div Q, vf%d.%s, vf%d.%s' % (d.ls, FIELDS[d.fsf], d.lt, FIELDS[d.ftf])
        elif o == L_SQRT:
            low = 'sqrt Q, vf%d.%s' % (d.lt, FIELDS[d.ftf])
        elif o == L_RSQRT:
            low = 'rsqrt Q, vf%d.%s, vf%d.%s' % (d.ls, FIELDS[d.fsf], d.lt, FIELDS[d.ftf])
        elif o == L_WAITQ:
            low = 'waitq'
        elif o == L_XGKICK:
            low = 'xgkick vi%d' % d.ls
        else:
            low = '?? %08x' % d.lower
    return '%-34s | %s%s' % (text, low, '   [E]' if d.ebit else '')


# ---- the programs in a stream -------------------------------------------------------------
def unpack_words(code, cl, wl):
    cmd, num = (code >> 24) & 0x7F, (code >> 16) & 0xFF
    vn, vl = (cmd >> 2) & 3, cmd & 3
    vectors = num or 256
    if wl > cl and wl:
        vectors = cl * (vectors // wl) + min(vectors % wl, cl)
    nbytes = vectors * 2 if (vn == 3 and vl == 3) else vectors * (vn + 1) * (4 >> vl)
    return (nbytes + 3) // 4


class Programs:
    """Every microprogram upload seen (pair address -> bytes), joined where they touch, and
    the entries programs were started at."""

    def __init__(self):
        self.uploads = {}       # (address, bytes) -> times seen
        self.entries = {}       # MSCAL address -> times
        self.cl = self.wl = 1

    def vif(self, w):
        """VIF1 codes (Vif1::process, render/vif1.cpp); returns the words used."""
        i, n = 0, len(w)
        run_start, run = None, b''
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
                break
            if cmd == 0x01:
                self.cl, self.wl = imm & 0xFF, (imm >> 8) & 0xFF
            elif cmd in (0x14, 0x15):
                self.entries[imm] = self.entries.get(imm, 0) + 1
            if cmd == 0x4A:
                data = struct.pack('<%dI' % need, *w[i + 1:i + 1 + need])
                if run_start is not None and run_start + len(run) // 8 == imm:
                    run += data
                else:
                    if run_start is not None:
                        self.uploads[(run_start, run)] = self.uploads.get((run_start, run), 0) + 1
                    run_start, run = imm, data
            elif cmd != 0x00 and run_start is not None:
                self.uploads[(run_start, run)] = self.uploads.get((run_start, run), 0) + 1
                run_start, run = None, b''
            i += 1 + need
        if run_start is not None:
            self.uploads[(run_start, run)] = self.uploads.get((run_start, run), 0) + 1
        return i

    def stream(self, path):
        with open(path, 'rb') as f:
            if f.read(8) != b'RTAVS1\0\0':
                raise SystemExit('%s is not a recorded picture stream' % path)
            pending = []
            while True:
                head = f.read(20)
                if len(head) < 20:
                    break
                kind, a, _b0, _b1, count = struct.unpack('<5I', head)
                payload = f.read(count * 4)
                if kind == 9 and a <= 0x3E5EC0 and 0x3E5EC0 + 940 * 16 <= a + count * 4:
                    # main memory: the executable's upload packet of the main program (a DMA tag
                    # whose upper half already holds VIF codes: Renderer::load_program)
                    words = list(struct.unpack('<%dI' % (940 * 4), payload[0x3E5EC0 - a:0x3E5EC0 - a + 940 * 16]))
                    saved = (self.cl, self.wl)
                    self.vif(words[2:])
                    self.cl, self.wl = saved
                elif kind == 1:
                    words = pending + list(struct.unpack('<%dI' % count, payload))
                    used = self.vif(words)
                    pending = words[used:]

    def elf(self, path):
        """The main program's upload packet out of the executable (0x3e5ec0, 940 quadwords)."""
        data = open(path, 'rb').read()
        if data[:4] != b'\x7fELF':
            raise SystemExit('%s is not an ELF file' % path)
        phoff, = struct.unpack_from('<I', data, 28)
        phentsize, phnum = struct.unpack_from('<HH', data, 42)
        for k in range(phnum):
            p_type, offset, vaddr, _paddr, filesz, _memsz = struct.unpack_from('<6I', data, phoff + k * phentsize)
            if p_type == 1 and vaddr <= 0x3E5EC0 and 0x3E5EC0 + 940 * 16 <= vaddr + filesz:
                at = offset + 0x3E5EC0 - vaddr
                words = list(struct.unpack_from('<%dI' % (940 * 4), data, at))
                saved = (self.cl, self.wl)
                self.vif(words[2:])
                self.cl, self.wl = saved
                return
        raise SystemExit('%s: the upload packet of the VU1 main program is not where it is in SLUS-20973 v2.00' % path)

    def programs(self):
        """[(start pair, [Ins]), ...] sorted, one per distinct upload."""
        out = []
        for (start, data), _times in sorted(self.uploads.items()):
            words = struct.unpack('<%dI' % (len(data) // 4), data)
            out.append((start, [decode(start + k, words[2 * k], words[2 * k + 1]) for k in range(len(words) // 2)], data))
        return out


def fnv64(data):
    h = 0xCBF29CE484222325
    for byte in data:
        h = ((h ^ byte) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--stream', action='append', default=[], help='a recorded picture stream to take the programs from')
    parser.add_argument('--elf', help='the game\'s executable: the main program is taken from it')
    parser.add_argument('--entry', default='', help='more instruction indexes programs are started at, hexadecimal, comma-separated')
    parser.add_argument('--out', help='the C++ file to write (derived from the game: under local/)')
    parser.add_argument('--listing', help='write the programs as text (derived from the game: under local/)')
    parser.add_argument('--report', action='store_true', help='print what the analysis found')
    args = parser.parse_args()
    for path in (args.out, args.listing):
        if path and '/local/' not in os.path.abspath(path) + '/':
            raise SystemExit('%s: what is made from the game\'s programs must be written under local/' % path)
    found = Programs()
    if args.elf:
        found.elf(args.elf)
    for path in args.stream:
        found.stream(path)
    programs = found.programs()
    if not programs:
        raise SystemExit('no microprogram in the streams given')
    if args.listing:
        with open(args.listing, 'w') as f:
            for start, pairs, data in programs:
                f.write('; program at 0x%03x, %d pairs, hash %016x\n' % (start, len(pairs), fnv64(data)))
                for d in pairs:
                    f.write('%03x: %s\n' % (d.n, disassemble(d)))
                f.write('\n')
    if args.out:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))     # the second half is beside this file
        from vu1_translate_gen import generate
        extra = [int(x, 16) for x in args.entry.split(',') if x]
        text = generate(programs, found.entries, extra_entries=extra, report=args.report)
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, 'w') as f:
            f.write(text)
        print('wrote %s: %d programs' % (args.out, len(programs)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
