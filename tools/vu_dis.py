#!/usr/bin/env python3
"""Disassembler for PlayStation 2 vector unit (VU0 / VU1) microcode.

A VU instruction is 64 bits: the *lower* instruction word comes first in memory, the
*upper* instruction word second.  The upper word also carries the flag bits
I (the lower word is a 32-bit float constant, loaded into the I register), E (the
microprogram ends after the next instruction), M, D and T.

The tool reads the bytes from a file you supply (normally your own copy of the game
executable); it contains no game data.  Standard library only.

  vu_dis.py <file> exe <hexaddr> <count> [options]
        disassemble <count> instructions starting at a virtual address of an ELF
        executable (the address is mapped through the program headers)
  vu_dis.py <file> raw <hexoffset> <count> [options]
        the same for a plain file offset (any file)
  vu_dis.py <file> vif <hexaddr> <hexlength> [options]
        walk a VIF packet: list every VIF code and disassemble the microcode carried
        by its MPG commands at the VU address each MPG loads it to
  vu_dis.py <file> sections
        list the sections of an ELF (microcode normally sits in .vutext)

options
  --origin N     VU address (instruction index) of the first instruction, for exe/raw
  --vu0          4 KB of micro memory (512 instructions) instead of VU1's 16 KB (2048);
                 only affects how branch targets wrap
  --file-offset  for vif: <hexaddr> is a file offset, not an ELF virtual address
  --dmatag       for vif: the packet starts with a 16-byte DMA tag; skip its first 8 bytes
                 (the tag's upper 8 bytes are VIF codes and are walked)
  --entry A=NAME label VU address A (hex) with NAME; may be repeated
  --notes FILE   tab-separated "hex VU address <tab> text" lines, shown as comments
  --no-labels    do not invent L_xxx labels for branch targets
  --jumptable N  note that the first N instructions are a jump table of 2-instruction
                 entries (MSCAL n enters at instruction n) and label their targets

Anything the tables below do not cover is printed as "???" with the raw word, counted,
reported on stderr at the end, and makes the exit status 3.  Bits that should be zero for
the decoded instruction but are not are reported the same way ("reserved bits").
"""
import struct
import sys

# --------------------------------------------------------------------------- file access


class Image:
    """A file, with ELF program-header mapping when it is an ELF."""

    def __init__(self, path):
        with open(path, "rb") as f:
            self.d = f.read()
        self.segs = []
        self.sections = []
        d = self.d
        if d[:4] == b"\x7fELF" and len(d) >= 52 and d[4] == 1 and d[5] == 1:
            phoff, shoff = struct.unpack_from("<II", d, 28)
            phentsize, phnum, shentsize, shnum, shstrndx = struct.unpack_from("<5H", d, 42)
            for i in range(phnum):
                t, off, va, pa, fsz, msz, fl, al = struct.unpack_from("<8I", d, phoff + i * phentsize)
                if t == 1:
                    self.segs.append((va, off, fsz))
            try:
                secs = [struct.unpack_from("<10I", d, shoff + i * shentsize) for i in range(shnum)]
                stro = secs[shstrndx][4]
                for s in secs:
                    end = d.index(b"\0", stro + s[0])
                    self.sections.append((d[stro + s[0]:end].decode("latin1"), s[3], s[4], s[5]))
            except (struct.error, ValueError, IndexError):
                self.sections = []

    def is_elf(self):
        return bool(self.segs)

    def va_to_off(self, va):
        for sva, soff, fsz in self.segs:
            if sva <= va < sva + fsz:
                return soff + (va - sva)
        raise SystemExit("address 0x%x is not in a loaded segment of the file" % va)

    def read(self, off, n):
        if off < 0 or off + n > len(self.d):
            raise SystemExit("0x%x bytes at file offset 0x%x run past the end of the file" % (n, off))
        return self.d[off:off + n]


# --------------------------------------------------------------------------- decoding

DEST = ["", "w", "z", "zw", "y", "yw", "yz", "yzw", "x", "xw", "xz", "xzw", "xy", "xyw", "xyz", "xyzw"]
BC = "xyzw"

F_DEST = 0x01E00000
F_FT = 0x001F0000
F_FS = 0x0000F800
F_FD = 0x000007C0
F_OP6 = 0x0000003F
F_IMM11 = 0x000007FF
F_UPPERFLAGS = 0xF8000000   # I E M D T
F_UPPERRSVD = 0x06000000


class Unknown(Exception):
    pass


def _dest(w):
    return DEST[(w >> 21) & 15]


def _ft(w):
    return (w >> 16) & 31


def _fs(w):
    return (w >> 11) & 31


def _fd(w):
    return (w >> 6) & 31


def _s11(w):
    v = w & 0x7FF
    return v - 0x800 if v & 0x400 else v


def _dot(name, w):
    d = _dest(w)
    return name + ("." + d if d else ".(none)")


# Upper instruction tables -----------------------------------------------------------

UP_BC = {0x00: "ADD", 0x04: "SUB", 0x08: "MADD", 0x0C: "MSUB", 0x10: "MAX", 0x14: "MINI", 0x18: "MUL"}
UP_QI = {0x1C: ("MULq", "Q"), 0x1D: ("MAXi", "I"), 0x1E: ("MULi", "I"), 0x1F: ("MINIi", "I"),
         0x20: ("ADDq", "Q"), 0x21: ("MADDq", "Q"), 0x22: ("ADDi", "I"), 0x23: ("MADDi", "I"),
         0x24: ("SUBq", "Q"), 0x25: ("MSUBq", "Q"), 0x26: ("SUBi", "I"), 0x27: ("MSUBi", "I")}
UP_3 = {0x28: "ADD", 0x29: "MADD", 0x2A: "MUL", 0x2B: "MAX", 0x2C: "SUB", 0x2D: "MSUB", 0x2E: "OPMSUB",
        0x2F: "MINI"}
# "special" group, index = fd field * 4 + low two bits of the word (opcode field 0x3c..0x3f)
UPS_BC = {0x00: "ADDA", 0x04: "SUBA", 0x08: "MADDA", 0x0C: "MSUBA", 0x18: "MULA"}
UPS_CONV = {0x10: "ITOF0", 0x11: "ITOF4", 0x12: "ITOF12", 0x13: "ITOF15",
            0x14: "FTOI0", 0x15: "FTOI4", 0x16: "FTOI12", 0x17: "FTOI15", 0x1D: "ABS"}
UPS_QI = {0x1C: ("MULAq", "Q"), 0x1E: ("MULAi", "I"), 0x20: ("ADDAq", "Q"), 0x21: ("MADDAq", "Q"),
          0x22: ("ADDAi", "I"), 0x23: ("MADDAi", "I"), 0x24: ("SUBAq", "Q"), 0x25: ("MSUBAq", "Q"),
          0x26: ("SUBAi", "I"), 0x27: ("MSUBAi", "I")}
UPS_3 = {0x28: "ADDA", 0x29: "MADDA", 0x2A: "MULA", 0x2C: "SUBA", 0x2D: "MSUBA", 0x2E: "OPMULA"}


def decode_upper(w):
    """Return (text, used_mask).  Raises Unknown for an encoding not in the tables."""
    op = w & 0x3F
    used = F_UPPERFLAGS | F_OP6
    if op < 0x1C:
        name = UP_BC[op & 0x3C] + BC[op & 3]
        return ("%s vf%d, vf%d, vf%d%s" % (_dot(name, w), _fd(w), _fs(w), _ft(w), BC[op & 3]),
                used | F_DEST | F_FT | F_FS | F_FD)
    if op in UP_QI:
        name, reg = UP_QI[op]
        return "%s vf%d, vf%d, %s" % (_dot(name, w), _fd(w), _fs(w), reg), used | F_DEST | F_FS | F_FD
    if op in UP_3:
        return ("%s vf%d, vf%d, vf%d" % (_dot(UP_3[op], w), _fd(w), _fs(w), _ft(w)),
                used | F_DEST | F_FT | F_FS | F_FD)
    if op >= 0x3C:
        sp = (_fd(w) << 2) | (w & 3)
        used |= F_FD
        if sp < 0x10 or 0x18 <= sp < 0x1C:
            name = UPS_BC[sp & 0x3C] + BC[sp & 3]
            return ("%s ACC, vf%d, vf%d%s" % (_dot(name, w), _fs(w), _ft(w), BC[sp & 3]),
                    used | F_DEST | F_FT | F_FS)
        if sp in UPS_CONV:
            return "%s vf%d, vf%d" % (_dot(UPS_CONV[sp], w), _ft(w), _fs(w)), used | F_DEST | F_FT | F_FS
        if sp in UPS_QI:
            name, reg = UPS_QI[sp]
            return "%s ACC, vf%d, %s" % (_dot(name, w), _fs(w), reg), used | F_DEST | F_FS
        if sp in UPS_3:
            return "%s ACC, vf%d, vf%d" % (_dot(UPS_3[sp], w), _fs(w), _ft(w)), used | F_DEST | F_FT | F_FS
        if sp == 0x1F:
            return "%s vf%d, vf%dw" % (_dot("CLIPw", w), _fs(w), _ft(w)), used | F_DEST | F_FT | F_FS
        if sp == 0x2F:
            return "NOP", used
        raise Unknown("upper special 0x%02x" % sp)
    raise Unknown("upper opcode 0x%02x" % op)


# Lower instruction tables -----------------------------------------------------------

LO_FLAG24 = {0x10: "FCEQ", 0x11: "FCSET", 0x12: "FCAND", 0x13: "FCOR"}
LO_FLAG12 = {0x14: "FSEQ", 0x16: "FSAND", 0x17: "FSOR"}
LO_FM = {0x18: "FMEQ", 0x1A: "FMAND", 0x1B: "FMOR"}
LO_BR2 = {0x28: "IBEQ", 0x29: "IBNE"}
LO_BR1 = {0x2C: "IBLTZ", 0x2D: "IBGTZ", 0x2E: "IBLEZ", 0x2F: "IBGEZ"}
LO_INT3 = {0x30: "IADD", 0x31: "ISUB", 0x34: "IAND", 0x35: "IOR"}
LOS_EFU1 = {0x70: "ESADD", 0x71: "ERSADD", 0x72: "ELENG", 0x73: "ERLENG", 0x74: "EATANxy", 0x75: "EATANxz",
            0x76: "ESUM"}
LOS_EFU2 = {0x78: "ESQRT", 0x79: "ERSQRT", 0x7A: "ERCPR", 0x7C: "ESIN", 0x7D: "EATAN", 0x7E: "EEXP"}


def decode_lower(w, pc, wrap, label):
    """Return (text, used_mask, branch_target or None, kind).

    kind is '' or one of 'b' (unconditional), 'bc' (conditional), 'call', 'jr'.
    """
    op = w >> 25
    used = 0xFE000000
    it, is_, imm = _ft(w), _fs(w), _s11(w)

    def target():
        return (pc + 1 + imm) % wrap

    if op == 0x00:
        return "%s vf%d, %d(vi%d)" % (_dot("LQ", w), it, imm, is_), used | F_DEST | F_FT | F_FS | F_IMM11, None, ""
    if op == 0x01:
        return "%s vf%d, %d(vi%d)" % (_dot("SQ", w), is_, imm, it), used | F_DEST | F_FT | F_FS | F_IMM11, None, ""
    if op == 0x04:
        return "%s vi%d, %d(vi%d)" % (_dot("ILW", w), it, imm, is_), used | F_DEST | F_FT | F_FS | F_IMM11, None, ""
    if op == 0x05:
        return "%s vi%d, %d(vi%d)" % (_dot("ISW", w), it, imm, is_), used | F_DEST | F_FT | F_FS | F_IMM11, None, ""
    if op in (0x08, 0x09):
        imm15 = ((w >> 10) & 0x7800) | (w & 0x7FF)
        return ("%s vi%d, vi%d, 0x%x" % ("IADDIU" if op == 8 else "ISUBIU", it, is_, imm15),
                used | F_DEST | F_FT | F_FS | F_IMM11, None, "")
    if op in LO_FLAG24:
        if op == 0x11:
            return "FCSET 0x%06x" % (w & 0xFFFFFF), used | 0xFFFFFF, None, ""
        return "%s vi1, 0x%06x" % (LO_FLAG24[op], w & 0xFFFFFF), used | 0xFFFFFF, None, ""
    if op in LO_FLAG12 or op == 0x15:
        imm12 = ((w >> 10) & 0x800) | (w & 0x7FF)
        if op == 0x15:
            return "FSSET 0x%03x" % imm12, used | 0x00200000 | F_IMM11, None, ""
        return "%s vi%d, 0x%03x" % (LO_FLAG12[op], it, imm12), used | 0x00200000 | F_FT | F_IMM11, None, ""
    if op in LO_FM:
        return "%s vi%d, vi%d" % (LO_FM[op], it, is_), used | F_FT | F_FS, None, ""
    if op == 0x1C:
        return "FCGET vi%d" % it, used | F_FT, None, ""
    if op == 0x20:
        t = target()
        return "B %s" % label(t), used | F_IMM11, t, "b"
    if op == 0x21:
        t = target()
        return "BAL vi%d, %s" % (it, label(t)), used | F_FT | F_IMM11, t, "call"
    if op == 0x24:
        return "JR vi%d" % is_, used | F_FS, None, "jr"
    if op == 0x25:
        return "JALR vi%d, vi%d" % (it, is_), used | F_FT | F_FS, None, "call"
    if op in LO_BR2:
        t = target()
        return "%s vi%d, vi%d, %s" % (LO_BR2[op], it, is_, label(t)), used | F_FT | F_FS | F_IMM11, t, "bc"
    if op in LO_BR1:
        t = target()
        return "%s vi%d, %s" % (LO_BR1[op], is_, label(t)), used | F_FS | F_IMM11, t, "bc"
    if op == 0x40:
        lo = w & 0x3F
        if lo in LO_INT3:
            return ("%s vi%d, vi%d, vi%d" % (LO_INT3[lo], _fd(w), is_, it),
                    used | F_OP6 | F_FT | F_FS | F_FD, None, "")
        if lo == 0x32:
            v = _fd(w)
            v = v - 32 if v & 16 else v
            return "IADDI vi%d, vi%d, %d" % (it, is_, v), used | F_OP6 | F_FT | F_FS | F_FD, None, ""
        if lo >= 0x3C:
            sp = (_fd(w) << 2) | (w & 3)
            used |= F_OP6 | F_FD
            fsf = BC[(w >> 21) & 3]
            ftf = BC[(w >> 23) & 3]
            if sp == 0x30:
                return "%s vf%d, vf%d" % (_dot("MOVE", w), it, is_), used | F_DEST | F_FT | F_FS, None, ""
            if sp == 0x31:
                return "%s vf%d, vf%d" % (_dot("MR32", w), it, is_), used | F_DEST | F_FT | F_FS, None, ""
            if sp == 0x34:
                return "%s vf%d, (vi%d++)" % (_dot("LQI", w), it, is_), used | F_DEST | F_FT | F_FS, None, ""
            if sp == 0x35:
                return "%s vf%d, (vi%d++)" % (_dot("SQI", w), is_, it), used | F_DEST | F_FT | F_FS, None, ""
            if sp == 0x36:
                return "%s vf%d, (--vi%d)" % (_dot("LQD", w), it, is_), used | F_DEST | F_FT | F_FS, None, ""
            if sp == 0x37:
                return "%s vf%d, (--vi%d)" % (_dot("SQD", w), is_, it), used | F_DEST | F_FT | F_FS, None, ""
            if sp == 0x38:
                return "DIV Q, vf%d%s, vf%d%s" % (is_, fsf, it, ftf), used | F_DEST | F_FT | F_FS, None, ""
            if sp == 0x39:
                return "SQRT Q, vf%d%s" % (it, ftf), used | 0x01800000 | F_FT, None, ""
            if sp == 0x3A:
                return "RSQRT Q, vf%d%s, vf%d%s" % (is_, fsf, it, ftf), used | F_DEST | F_FT | F_FS, None, ""
            if sp == 0x3B:
                return "WAITQ", used, None, ""
            if sp == 0x3C:
                return "MTIR vi%d, vf%d%s" % (it, is_, fsf), used | 0x00600000 | F_FT | F_FS, None, ""
            if sp == 0x3D:
                return "%s vf%d, vi%d" % (_dot("MFIR", w), it, is_), used | F_DEST | F_FT | F_FS, None, ""
            if sp == 0x3E:
                return "%s vi%d, (vi%d)" % (_dot("ILWR", w), it, is_), used | F_DEST | F_FT | F_FS, None, ""
            if sp == 0x3F:
                return "%s vi%d, (vi%d)" % (_dot("ISWR", w), it, is_), used | F_DEST | F_FT | F_FS, None, ""
            if sp == 0x40:
                return "%s vf%d, R" % (_dot("RNEXT", w), it), used | F_DEST | F_FT, None, ""
            if sp == 0x41:
                return "%s vf%d, R" % (_dot("RGET", w), it), used | F_DEST | F_FT, None, ""
            if sp == 0x42:
                return "RINIT R, vf%d%s" % (is_, fsf), used | 0x00600000 | F_FS, None, ""
            if sp == 0x43:
                return "RXOR R, vf%d%s" % (is_, fsf), used | 0x00600000 | F_FS, None, ""
            if sp == 0x64:
                return "%s vf%d, P" % (_dot("MFP", w), it), used | F_DEST | F_FT, None, ""
            if sp == 0x68:
                return "XTOP vi%d" % it, used | F_FT, None, ""
            if sp == 0x69:
                return "XITOP vi%d" % it, used | F_FT, None, ""
            if sp == 0x6C:
                return "XGKICK vi%d" % is_, used | F_FS, None, ""
            if sp in LOS_EFU1:
                return "%s P, vf%d" % (LOS_EFU1[sp], is_), used | F_FS, None, ""
            if sp in LOS_EFU2:
                return "%s P, vf%d%s" % (LOS_EFU2[sp], is_, fsf), used | 0x00600000 | F_FS, None, ""
            if sp == 0x7B:
                return "WAITP", used, None, ""
            raise Unknown("lower special 0x%02x" % sp)
        raise Unknown("lower function 0x%02x" % lo)
    raise Unknown("lower opcode 0x%02x" % op)


def _float(w):
    return struct.unpack("<f", struct.pack("<I", w))[0]


class Listing:
    def __init__(self, wrap=2048, entries=None, notes=None, labels=True, jumptable=0):
        self.wrap = wrap
        self.entries = dict(entries or {})
        self.notes = dict(notes or {})
        self.auto = labels
        self.jumptable = jumptable
        self.unknown = []      # (vu address, where, text)
        self.reserved = []

    def disassemble(self, words, origin, where):
        """words: list of (lower, upper); where(i) -> source address text for instruction i."""
        targets = {}

        def nolabel(t):
            return "0x%03x" % t

        # pass 1: branch targets
        for i, (lo, up) in enumerate(words):
            pc = origin + i
            if up & 0x80000000:
                continue
            try:
                _, _, t, kind = decode_lower(lo, pc, self.wrap, nolabel)
            except Unknown:
                continue
            if t is not None:
                targets.setdefault(t, set()).add(pc)

        def label(t):
            if t in self.entries:
                return self.entries[t]
            if self.auto:
                return "L_%03x" % t
            return "0x%03x" % t

        out = []
        for i, (lo, up) in enumerate(words):
            pc = origin + i
            if pc in self.entries:
                out.append("")
                out.append("%s:" % self.entries[pc])
            elif pc in targets and self.auto:
                out.append("L_%03x:" % pc)
            flags = "".join(c if up & b else "-" for c, b in
                            (("I", 0x80000000), ("E", 0x40000000), ("M", 0x20000000),
                             ("D", 0x10000000), ("T", 0x08000000)))
            problems = []
            try:
                utext, umask = decode_upper(up)
                if up & ~umask & 0xFFFFFFFF:
                    problems.append("upper reserved bits 0x%08x" % (up & ~umask & 0xFFFFFFFF))
                    self.reserved.append((pc, where(i), "upper 0x%08x" % up))
            except Unknown as e:
                utext = "??? 0x%08x" % up
                problems.append("UNKNOWN %s" % e)
                self.unknown.append((pc, where(i), "%s (word 0x%08x)" % (e, up)))
            if up & 0x80000000:
                ltext = "LOI %.9g  (0x%08x)" % (_float(lo), lo)
            else:
                try:
                    ltext, lmask, t, kind = decode_lower(lo, pc, self.wrap, label)
                    if lo & ~lmask & 0xFFFFFFFF:
                        problems.append("lower reserved bits 0x%08x" % (lo & ~lmask & 0xFFFFFFFF))
                        self.reserved.append((pc, where(i), "lower 0x%08x" % lo))
                    if lo == 0x8000033C:
                        ltext = "NOP"       # MOVE vf0, vf0 with no destination: the usual lower no-op
                except Unknown as e:
                    ltext = "??? 0x%08x" % lo
                    problems.append("UNKNOWN %s" % e)
                    self.unknown.append((pc, where(i), "%s (word 0x%08x)" % (e, lo)))
            line = "  %03x  %s  %s  %-34s | %s" % (pc, where(i), flags, utext, ltext)
            com = []
            if self.jumptable and pc < self.jumptable and pc % 2 == 0:
                com.append("entry 0x%02x" % pc)
            if problems:
                com.append("; ".join(problems))
            if pc in self.notes:
                com.append(self.notes[pc])
            if com:
                line += "   ; " + " -- ".join(com)
            out.append(line)
            if up & 0x40000000:
                out.append("        (E: the program stops after the next instruction)")
        return out

    def report(self):
        for pc, w, t in self.unknown:
            sys.stderr.write("UNKNOWN ENCODING at VU 0x%03x (%s): %s\n" % (pc, w, t))
        for pc, w, t in self.reserved:
            sys.stderr.write("reserved bits set at VU 0x%03x (%s): %s\n" % (pc, w, t))
        if self.unknown or self.reserved:
            sys.stderr.write("%d unknown encodings, %d instructions with reserved bits set\n"
                             % (len(self.unknown), len(self.reserved)))
            return 3
        return 0


def words_from(data):
    n = len(data) // 8
    v = struct.unpack_from("<%dI" % (2 * n), data, 0)
    return [(v[2 * i], v[2 * i + 1]) for i in range(n)]


# --------------------------------------------------------------------------- VIF packets

VIF_NAMES = {0x00: "NOP", 0x01: "STCYCL", 0x02: "OFFSET", 0x03: "BASE", 0x04: "ITOP", 0x05: "STMOD",
             0x06: "MSKPATH3", 0x07: "MARK", 0x10: "FLUSHE", 0x11: "FLUSH", 0x13: "FLUSHA", 0x14: "MSCAL",
             0x15: "MSCALF", 0x17: "MSCNT", 0x20: "STMASK", 0x30: "STROW", 0x31: "STCOL", 0x4A: "MPG",
             0x50: "DIRECT", 0x51: "DIRECTHL"}
UNPACK_FMT = {0: "S-32", 1: "S-16", 2: "S-8", 4: "V2-32", 5: "V2-16", 6: "V2-8", 8: "V3-32", 9: "V3-16",
              10: "V3-8", 12: "V4-32", 13: "V4-16", 14: "V4-8", 15: "V4-5"}


def walk_vif(data, base, emit, mpg):
    """Walk VIF codes in data.  emit(text) prints a line; mpg(load_addr, bytes, addr) gets microcode.

    base is the address of data[0] for display.  Returns the number of unknown VIF codes.
    """
    cl, wl = 1, 1
    p = 0
    bad = 0
    n = len(data) & ~3
    while p < n:
        w, = struct.unpack_from("<I", data, p)
        cmd = (w >> 24) & 0x7F
        irq = " +irq" if w & 0x80000000 else ""
        num = (w >> 16) & 0xFF
        imm = w & 0xFFFF
        here = base + p
        if w == 0:
            q = p
            while q < n and struct.unpack_from("<I", data, q)[0] == 0:
                q += 4
            emit("%08x  NOP x%d" % (here, (q - p) // 4))
            p = q
            continue
        if cmd & 0x60 == 0x60:
            vnvl = cmd & 15
            if vnvl not in UNPACK_FMT:
                emit("%08x  ??? unknown UNPACK format, word 0x%08x -- cannot continue" % (here, w))
                return bad + 1
            cnt = num or 256
            vn, vl = (vnvl >> 2) + 1, vnvl & 3
            bits = 16 if vnvl == 15 else (32 >> vl) * vn
            if wl <= cl or wl == 0:
                items = cnt
            else:
                items = cl * (cnt // wl) + min(cnt % wl, cl)
            size = (items * bits // 8 + 3) & ~3
            emit("%08x  UNPACK %s%s num=%d addr=0x%03x%s%s%s  (%d data bytes)" % (
                here, UNPACK_FMT[vnvl], " masked" if cmd & 0x10 else "", cnt, imm & 0x3FF,
                " +TOPS" if imm & 0x8000 else "", " unsigned" if imm & 0x4000 else "", irq, size))
            p += 4 + size
            continue
        name = VIF_NAMES.get(cmd)
        if name is None:
            emit("%08x  ??? unknown VIF code 0x%02x, word 0x%08x" % (here, cmd, w))
            bad += 1
            p += 4
            continue
        if cmd == 0x4A:
            cnt = num or 256
            body = data[p + 4:p + 4 + cnt * 8]
            emit("%08x  MPG load at VU 0x%03x, %d instructions%s" % (here, imm, cnt, irq))
            if len(body) < cnt * 8:
                emit("          (packet ends inside the microcode: %d of %d bytes present)" % (len(body), cnt * 8))
            mpg(imm, body, here + 4)
            p += 4 + cnt * 8
        elif cmd == 0x01:
            cl, wl = imm & 0xFF, imm >> 8
            emit("%08x  STCYCL cl=%d wl=%d%s" % (here, cl, wl, irq))
            p += 4
        elif cmd == 0x20:
            emit("%08x  STMASK 0x%08x%s" % (here, struct.unpack_from("<I", data, p + 4)[0] if p + 8 <= n else 0, irq))
            p += 8
        elif cmd in (0x30, 0x31):
            vals = struct.unpack_from("<4I", data, p + 4) if p + 20 <= n else ()
            emit("%08x  %s %s%s" % (here, name, " ".join("0x%08x" % v for v in vals), irq))
            p += 20
        elif cmd in (0x50, 0x51):
            q = imm or 65536
            emit("%08x  %s %d qwords of GIF data%s" % (here, name, q, irq))
            p += 4 + q * 16
        elif cmd in (0x14, 0x15):
            emit("%08x  %s 0x%x  (run the microprogram from instruction 0x%x)%s" % (here, name, imm, imm, irq))
            p += 4
        else:
            emit("%08x  %s 0x%x%s" % (here, name, imm, irq))
            p += 4
    return bad


# --------------------------------------------------------------------------- command line


def _hex(s):
    return int(s, 16)


def main(argv):
    if len(argv) < 3 or argv[1] in ("-h", "--help"):
        sys.stdout.write(__doc__)
        return 0 if len(argv) > 1 else 2
    path, mode = argv[1], argv[2]
    pos, opts = [], {"entries": {}, "notes": {}}
    it = iter(argv[3:])
    for a in it:
        if a == "--origin":
            opts["origin"] = int(next(it), 0)
        elif a == "--vu0":
            opts["vu0"] = True
        elif a == "--file-offset":
            opts["fileoff"] = True
        elif a == "--dmatag":
            opts["dmatag"] = True
        elif a == "--no-labels":
            opts["nolabels"] = True
        elif a == "--jumptable":
            opts["jumptable"] = int(next(it), 0)
        elif a == "--entry":
            k, _, v = next(it).partition("=")
            opts["entries"][_hex(k)] = v
        elif a == "--notes":
            with open(next(it), encoding="utf-8") as f:
                for ln in f:
                    ln = ln.rstrip("\n")
                    if not ln or ln.startswith("#"):
                        continue
                    k, _, v = ln.partition("\t")
                    opts["notes"][_hex(k)] = v
        elif a.startswith("--"):
            raise SystemExit("unknown option " + a)
        else:
            pos.append(a)
    img = Image(path)
    wrap = 512 if opts.get("vu0") else 2048
    lst = Listing(wrap, opts["entries"], opts["notes"], not opts.get("nolabels"), opts.get("jumptable", 0))

    if mode == "sections":
        if not img.sections:
            raise SystemExit("not an ELF file, or it has no section table")
        for name, va, off, size in img.sections:
            print("%-40s addr 0x%08x  file 0x%08x  size 0x%x" % (name, va, off, size))
        return 0

    if mode in ("exe", "raw"):
        if len(pos) != 2:
            raise SystemExit("usage: vu_dis.py <file> %s <hexaddr> <count>" % mode)
        addr, count = _hex(pos[0]), int(pos[1], 0)
        if mode == "exe":
            if not img.is_elf():
                raise SystemExit("%s is not an ELF executable; use 'raw' with a file offset" % path)
            off = img.va_to_off(addr)
        else:
            off = addr
        words = words_from(img.read(off, count * 8))
        origin = opts.get("origin", 0)
        for ln in lst.disassemble(words, origin, lambda i: "%08x" % (addr + i * 8)):
            print(ln)
        return lst.report()

    if mode == "vif":
        if len(pos) != 2:
            raise SystemExit("usage: vu_dis.py <file> vif <hexaddr> <hexlength>")
        addr, length = _hex(pos[0]), _hex(pos[1])
        off = addr if (opts.get("fileoff") or not img.is_elf()) else img.va_to_off(addr)
        data = img.read(off, length)
        if opts.get("dmatag"):
            tag, = struct.unpack_from("<Q", data, 0)
            print("%08x  DMA tag: id %d, %d qwords follow" % (addr, (tag >> 28) & 7, tag & 0xFFFF))
            data = data[8:]
            addr += 8
        blocks = []
        bad = walk_vif(data, addr, print, lambda load, body, a: blocks.append((load, body, a)))
        # consecutive MPG blocks that continue each other are listed as one program
        merged = []
        for load, body, a in blocks:
            if merged and merged[-1][0] + len(merged[-1][1]) == load:
                merged[-1][1].extend((a + 8 * i) for i in range(len(body) // 8))
                merged[-1][2].extend(words_from(body))
            else:
                merged.append([load, [(a + 8 * i) for i in range(len(body) // 8)], words_from(body)])
        for load, addrs, words in merged:
            print("")
            print("; microcode loaded at VU 0x%03x, %d instructions" % (load, len(words)))
            for ln in lst.disassemble(words, load, lambda i, addrs=addrs: "%08x" % addrs[i]):
                print(ln)
        rc = lst.report()
        if bad:
            sys.stderr.write("%d unknown VIF codes\n" % bad)
            rc = 3
        return rc

    raise SystemExit("unknown mode %r (exe, raw, vif, sections)" % mode)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except BrokenPipeError:
        sys.exit(0)
