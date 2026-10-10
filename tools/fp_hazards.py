#!/usr/bin/env python3
"""fp_hazards.py - first-pass scan for floating-point operations whose result depends on
the PS2's non-IEEE behaviour.

  python3 -I -B tools/fp_hazards.py                      # counts per area
  python3 -I -B tools/fp_hazards.py --list [filters]     # one line per site
  python3 -I -B tools/fp_hazards.py --reach 27236c,2d470c --list --open
  python3 -I -B tools/fp_hazards.py --selftest

Filters (combine freely):
  --area NAME[,NAME]      areas as in docs/STATUS.md
  --func HEX[,HEX]        functions by entry address
  --range LO:HI           address range, end exclusive
  --reach HEX[,HEX]       the named functions plus everything they reach through direct
                          calls (jal / j); virtual calls are not followed.  --depth N limits it
  --kind div,sqrt,rsqrt,cvt,big,cmp
  --open                  only sites the scan could not close (no constant, guard or clamp)
  --tsv                   tab-separated output
  --summary               print the count tables as well as the list
  --ops                   add a census of every single-precision operation per area

It reads disasm/text.asm for the instruction stream, ghidra_funcs.tsv for function bodies,
names.tsv + symbols/*.tsv for names and docs/STATUS.md for the area table.  When the
executable (SLUS_209.73) is next to them it is used for two things only: decoding the
R5900-only encodings the generic disassembler prints as <unknown> (sqrt.s / rsqrt.s with a
non-zero ft field, max.s, min.s, adda.s) and reading constants from .rodata.  Without it
those sites are missed and the tool says how many lines it could not decode.

What is reported
  div    div.s    fd = fs / ft.  Hazard: ft == 0 (console: signed maximum; IEEE: inf or NaN).
  rsqrt  rsqrt.s  fd = fs / sqrt(ft).  Hazard: ft == 0 (as div) or ft < 0 (console uses |ft|).
  sqrt   sqrt.s   fd = sqrt(ft).  Hazard: ft < 0 (console uses |ft|; IEEE: NaN).
  cvt    cvt.w.s  float to int, always truncating on the R5900.  Hazard: |value| >= 2^31
                  (console saturates by sign; an x86 host conversion returns 0x80000000 for
                  both signs unless the emulator corrects it).
  big    a float constant of magnitude >= 1e18 (or with exponent 0xff) materialised in a
         register: the usual seed of an add/multiply overflow.  "arith" in the reach column
         means the register is used in arithmetic within a few instructions.
  cmp    a compare whose operand was reached, in the forward scan, from a div / rsqrt / sqrt
         site left open - the compares that would see a NaN on an IEEE machine.

Classification (column "class")
  const        operand is a non-zero constant (immediate, or a .rodata word), or a plainly
               non-negative value plus a positive constant.  For sqrt the detail column shows
               the operand's bits and its correctly rounded root; two roots separated by "|"
               mean that rounding toward zero and rounding to nearest give different bits
  nonneg       sqrt only: operand is a sum of squares / abs / non-negative constant
  zero-const   (shown as open:zero-const) the divisor is the constant 0.0
  guard-zero   a compare-and-branch against 0.0 on the same register (or on the same memory
               slot, or an integer test of the register it was converted from) precedes the op
  guard-bound  the same against a non-zero constant or another register
  clamp        operand comes straight out of max.s / min.s
  open:<how>   none of the above; <how> is where the operand came from: sub add mul div sqrt
               rsqrt load (memory) int (converted integer) bits (raw integer bits) call
               (function result) arg flow (arrives over a branch) ?
               The scan looks through mov.s / abs.s / neg.s and through a multiplication by
               a non-zero constant, since those keep "is zero" unchanged.
  A trailing "~" marks a guard found on the far side of a branch target or by the wider,
  weaker search over the earlier part of the function, i.e. it may not be on every path.

"reach" is a forward scan of the result along the fall-through path only:
  arith  used in add/sub/mul/div        cmp@ADDR  compared (and then branched on)
  int    converted with cvt.w.s         store OFF(REG)  written to memory (not the stack)
  arg>F  passed in $f12..$f19 to F      ret  left in $f0 at the function's return

This is a pattern scan, not a proof.  The window is short (see WINDOW), only a block's single
entering branch is followed and a guard two basic blocks away is usually invisible.  "open"
means "read this by hand", not "this divides by zero"; "guard" means "there is a test", not
"the test is the right one".  Constants loaded from writable memory are not recognised.
"""
import bisect, glob, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WINDOW = 48      # instructions scanned backwards for the operand's origin and guards
FWD = 40         # instructions scanned forwards for what the result reaches
BIG = 1e18

AREAS_FALLBACK = [
    ('startup', 0x100000, 0x109d68), ('creatures', 0x109d68, 0x131d88),
    ('netcode', 0x131d88, 0x13ecf8), ('script', 0x13ecf8, 0x147300),
    ('objects', 0x147300, 0x160000), ('engine', 0x160000, 0x1a0000),
    ('player', 0x1a0000, 0x1c0000), ('ui', 0x1c0000, 0x1e8000),
    ('gameplay', 0x1e8000, 0x210000), ('audio-save', 0x210000, 0x232000),
    ('monsters', 0x232000, 0x2c3cd4), ('skills', 0x2c3cd4, 0x320000),
    ('mainloop', 0x320000, 0x323dcc), ('netlib', 0x323dcc, 0x3b0000),
    ('runtime', 0x3b0000, 0x3e6000),
]


def text_lines(path):
    with open(path, 'rb') as raw:
        head = raw.read(2)
    enc = 'utf-16' if head in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig'
    with open(path, encoding=enc, errors='replace') as f:
        for line in f:
            yield line


# ---------------------------------------------------------------------------------------
# inputs

class Image:
    """Just enough ELF reading to fetch a word by address and to know where .rodata is."""

    def __init__(self, path):
        d = self.d = open(path, 'rb').read()
        phoff, = struct.unpack_from('<I', d, 28)
        phentsize, phnum = struct.unpack_from('<HH', d, 42)
        self.segs = []
        for i in range(phnum):
            t, off, va, pa, fsz, msz, fl, al = struct.unpack_from('<8I', d, phoff + i * phentsize)
            if t == 1:
                self.segs.append((va, off, fsz))
        shoff, = struct.unpack_from('<I', d, 32)
        shentsize, shnum, shstrndx = struct.unpack_from('<HHH', d, 46)
        secs = [struct.unpack_from('<10I', d, shoff + i * shentsize) for i in range(shnum)]
        stro = secs[shstrndx][4]
        self.ro = (0, 0)
        for s in secs:
            nm = d[stro + s[0]:d.index(b'\0', stro + s[0])]
            if nm == b'.rodata':
                self.ro = (s[3], s[3] + s[5])

    def u32(self, va):
        for sva, soff, fsz in self.segs:
            if sva <= va < sva + fsz:
                return struct.unpack_from('<I', self.d, soff + va - sva)[0]
        return None

    def is_ro(self, va):
        return self.ro[0] <= va < self.ro[1]


def load_areas(root):
    path = os.path.join(root, 'docs', 'STATUS.md')
    out = []
    if os.path.exists(path):
        pat = re.compile(r'^\|\s*([a-z][a-z-]*)\s*\|\s*([0-9a-f]+)\D+([0-9a-f]+)\s*\|')
        for line in text_lines(path):
            m = pat.match(line)
            if m:
                out.append((m.group(1), int(m.group(2), 16), int(m.group(3), 16)))
    return out or AREAS_FALLBACK


def load_names(root):
    names = {}
    files = [os.path.join(root, 'names.tsv')] + sorted(glob.glob(os.path.join(root, 'symbols', '*.tsv')))
    for f in files:
        if not os.path.exists(f):
            continue
        for line in text_lines(f):
            p = line.rstrip('\n').split('\t')
            if len(p) >= 2 and re.fullmatch(r'[0-9a-fA-F]{1,8}', p[0]) and p[1].strip():
                names.setdefault(int(p[0], 16), p[1].strip())
    return names


def load_funcs(root):
    """-> sorted list of (lo, hi_inclusive, entry) over every body range."""
    ranges = []
    path = os.path.join(root, 'ghidra_funcs.tsv')
    for line in text_lines(path):
        p = line.rstrip('\n').split('\t')
        if len(p) != 3 or line.startswith('#'):
            continue
        ent = int(p[0], 16)
        for part in p[2].split(','):
            if part:
                lo, hi = (int(x, 16) for x in part.split('-'))
                ranges.append((lo, hi, ent))
    ranges.sort()
    return ranges


# ---------------------------------------------------------------------------------------
# instruction model
#
# Every instruction becomes a tuple (kind, a, b, c):
#   fp3   (name, fd, fs, ft)      add sub mul div max min
#   sqrt  (fd, ft)                rsqrt (fd, fs, ft)
#   fp2   (name, fd, fs)          mov abs neg
#   cvtw  (fd, fs)   cvts (fd, fs)
#   cmp   (name, fs, ft)
#   mtc1  (gpr, fs)  mfc1 (gpr, fs)
#   lwc1  (ft, off, base)  swc1 (ft, off, base)
#   bc1   branch on the FP condition
#   call  (target or None)   jump (unconditional b / j)   ret   cbr (conditional, regs)
#   gpr   (mnemonic, [operands])   anything else that matters only as an integer def/use
#   nop / other

FP3 = {'add.s': 'add', 'sub.s': 'sub', 'mul.s': 'mul', 'div.s': 'div'}
FP2 = {'mov.s': 'mov', 'abs.s': 'abs', 'neg.s': 'neg'}
CMP = {'c.eq.s': 'eq', 'c.olt.s': 'lt', 'c.ole.s': 'le', 'c.f.s': 'f',
       'c.lt.s': 'lt', 'c.le.s': 'le'}
BC1 = ('bc1t', 'bc1f', 'bc1tl', 'bc1fl')
CBR = ('beqz', 'bnez', 'beq', 'bne', 'blez', 'bgtz', 'bltz', 'bgez', 'beqzl', 'bnezl',
       'beql', 'bnel', 'blezl', 'bgtzl', 'bltzl', 'bgezl')
MEM = re.compile(r'^(-?0x[0-9a-f]+|-?\d+)\((\$\w+)\)$')
# what a generic MIPS decoder calls the R5900's COP2 / lqc2 / sqc2 words
COP2_TEXT = ('dmfc2', 'dmtc2', 'bbit032', 'bbit132', 'qmfc2', 'qmtc2', 'cfc2', 'ctc2', 'lqc2', 'sqc2')


def freg(s):
    return int(s[2:])


def decode_word(w):
    """COP1 single-precision decode of a raw word, R5900 flavour. None if not COP1.S."""
    if w is None or (w >> 26) != 0x11 or ((w >> 21) & 31) != 0x10:
        return None
    ft, fs, fd, fn = (w >> 16) & 31, (w >> 11) & 31, (w >> 6) & 31, w & 63
    if fn in (0, 1, 2, 3):
        return ('fp3', ('add', 'sub', 'mul', 'div')[fn], fd, fs, ft)
    if fn == 4:
        return ('sqrt', fd, ft)
    if fn == 0x16:
        return ('rsqrt', fd, fs, ft)
    if fn == 0x28:
        return ('fp3', 'max', fd, fs, ft)
    if fn == 0x29:
        return ('fp3', 'min', fd, fs, ft)
    if fn in (0x18, 0x19, 0x1a, 0x1c, 0x1d, 0x1e, 0x1f):
        return ('acc', fn, fd, fs, ft)
    return None


class Program:
    def __init__(self, root):
        self.root = root
        self.addr, self.mn, self.ops = [], [], []
        pat = re.compile(r'^\s*([0-9a-f]+):\s+(\S+)\s*(.*)$')
        for line in text_lines(os.path.join(root, 'disasm', 'text.asm')):
            m = pat.match(line)
            if m:
                self.addr.append(int(m.group(1), 16))
                self.mn.append(m.group(2))
                self.ops.append(m.group(3).split('<')[0].strip())
        self.index = {a: i for i, a in enumerate(self.addr)}
        self.n = len(self.addr)
        elf = os.path.join(root, 'SLUS_209.73')
        self.img = Image(elf) if os.path.exists(elf) else None
        self.undecoded = 0
        self.last_bits = None
        self.cache = {}
        self.funcs = load_funcs(root)
        self.flo = [r[0] for r in self.funcs]
        self.names = load_names(root)
        self.areas = load_areas(root)
        self.sources = {}        # branch target address -> indices of the branches to it
        tpat = re.compile(r'0x([0-9a-f]+)$')
        for i in range(self.n):
            mn = self.mn[i]
            if mn[0] == 'b' and (mn in CBR or mn in BC1 or mn == 'b') or mn == 'j':
                m = tpat.search(self.ops[i])
                if m:
                    self.sources.setdefault(int(m.group(1), 16), []).append(i)
        self.targets = set(self.sources)

    # -- lookups
    def func_of(self, a):
        i = bisect.bisect_right(self.flo, a) - 1
        while i >= 0:
            lo, hi, ent = self.funcs[i]
            if lo <= a <= hi:
                return ent, lo, hi
            if a - lo > 0x20000:
                break
            i -= 1
        return None, a, a

    def fname(self, ent):
        if ent is None:
            return '?'
        return self.names.get(ent, 'FUN_%08x' % ent)

    def area_of(self, a):
        for nm, lo, hi in self.areas:
            if lo <= a < hi:
                return nm
        return '-'

    # -- decode
    def d(self, i):
        r = self.cache.get(i)
        if r is None:
            r = self.cache[i] = self._decode(i)
        return r

    def _decode(self, i):
        mn, ops = self.mn[i], self.ops[i]
        o = [x.strip() for x in ops.split(',')] if ops else []
        if mn in ('sqrt.s', 'rsqrt.s', '<unknown>'):
            if self.img is not None:
                r = decode_word(self.img.u32(self.addr[i]))
                if r:
                    return r
                if mn == '<unknown>':
                    return ('other',)
            elif mn == '<unknown>':
                self.undecoded += 1
                return ('other',)
            # text only: the generic decoder shows fd, fs and the real operand is ft = $f0
            if mn == 'sqrt.s':
                return ('sqrt', freg(o[0]), 0)
            return ('rsqrt', freg(o[0]), freg(o[1]), 0)
        if mn in FP3:
            return ('fp3', FP3[mn], freg(o[0]), freg(o[1]), freg(o[2]))
        if mn in FP2:
            return ('fp2', FP2[mn], freg(o[0]), freg(o[1]))
        if mn == 'cvt.w.s' or mn == 'trunc.w.s':
            return ('cvtw', freg(o[0]), freg(o[1]))
        if mn == 'cvt.s.w':
            return ('cvts', freg(o[0]), freg(o[1]))
        if mn in CMP:
            return ('cmp', CMP[mn], freg(o[0]), freg(o[1]))
        if mn == 'mtc1':
            return ('mtc1', o[0], freg(o[1]))
        if mn == 'mfc1':
            return ('mfc1', o[0], freg(o[1]))
        if mn in ('lwc1', 'swc1'):
            m = MEM.match(o[1])
            return (mn, freg(o[0]), int(m.group(1), 0), m.group(2))
        if mn in BC1:
            return ('bc1',)
        if mn in ('jal', 'jalr'):
            t = None
            if mn == 'jal':
                t = int(o[0], 16)
            return ('call', t)
        if mn in ('b', 'j'):
            return ('jump', int(o[0], 16) if o and o[0].startswith('0x') else None)
        if mn == 'jr':
            return ('ret',) if o and o[0] == '$ra' else ('jump', None)
        if mn in CBR:
            return ('cbr', tuple(x for x in o if x.startswith('$')))
        if mn == 'nop' or mn == '...':
            return ('nop',)
        return ('gpr', mn, o)

    # -- small helpers used by the scans
    def gpr_const(self, i, reg, depth=6):
        """Value loaded into GPR `reg` by lui / ori / addiu just before index i, or None."""
        if reg == '$zero':
            return 0
        val, have_lo = None, 0
        j = i - 1
        while j >= 0 and i - j <= depth:
            k = self.d(j)
            if k[0] == 'gpr':
                mn, o = k[1], k[2]
                if o and o[0] == reg:
                    if mn == 'lui' and len(o) == 2:
                        return ((int(o[1], 0) & 0xffff) << 16) | have_lo
                    if mn == 'ori' and len(o) == 3 and o[1] == reg and val is None:
                        have_lo = int(o[2], 0) & 0xffff
                    elif mn in ('addiu', 'ori') and len(o) == 3 and o[1] == '$zero':
                        return int(o[2], 0) & 0xffffffff
                    else:
                        return None
            elif k[0] in ('call', 'jump', 'ret'):
                return None
            j -= 1
        return None

    def fp_const(self, i, reg, depth=10):
        """Float constant held in FP register `reg` just before index i, or None.
        Follows mov.s, an immediate mtc1 and a load from .rodata through lui+lwc1."""
        j = i - 1
        while j >= 0 and i - j <= depth:
            k = self.d(j)
            if k[0] == 'mtc1' and k[2] == reg:
                v = self.gpr_const(j, k[1])
                return None if v is None else struct.unpack('<f', struct.pack('<I', v))[0]
            if k[0] == 'lwc1' and k[1] == reg:
                return self.ro_float(j)
            if k[0] == 'fp2' and k[2] == reg:
                if k[1] == 'mov':
                    reg = k[3]
                    j -= 1
                    continue
                return None
            if k[0] in ('fp3', 'acc') and k[2] == reg or k[0] in ('sqrt', 'rsqrt', 'cvts', 'cvtw') and k[1] == reg:
                return None
            if k[0] in ('call', 'jump', 'ret'):
                return None
            j -= 1
        return None

    def fp_const_bits(self, i, reg, depth=24):
        """Bit pattern of an immediate constant in FP register `reg` before index i, or None."""
        j = i - 1
        while j >= 0 and i - j <= depth:
            k = self.d(j)
            if k[0] == 'mtc1' and k[2] == reg:
                return self.gpr_const(j, k[1])
            if k[0] == 'fp2' and k[2] == reg:
                if k[1] != 'mov':
                    return None
                reg = k[3]
            elif k[0] in ('fp3', 'acc') and k[2] == reg or k[0] in ('sqrt', 'rsqrt', 'cvts', 'cvtw', 'lwc1') and k[1] == reg:
                return None
            elif k[0] in ('call', 'jump', 'ret'):
                return None
            j -= 1
        return None

    def abs_addr(self, j):
        """Absolute address of the lwc1/swc1 at index j when its base was set by lui just before."""
        k = self.d(j)
        hi = self.gpr_const(j, k[3], 4)
        if hi is None or hi & 0xffff:
            return None
        return (hi + k[2]) & 0xffffffff

    def ro_float(self, j):
        a = self.abs_addr(j)
        if a is None or self.img is None or not self.img.is_ro(a):
            return None
        w = self.img.u32(a)
        return None if w is None else struct.unpack('<f', struct.pack('<I', w))[0]

    def branches_next(self, j):
        """True when the condition set by the compare at j is consumed by a bc1x: the
        condition bit lives until the next compare, so intervening integer code is fine."""
        for k in range(j + 1, min(self.n, j + 33)):
            kind = self.d(k)[0]
            if kind == 'bc1':
                return True
            if kind in ('cmp', 'call', 'ret'):
                return False
        return False

    def sole_entry(self, j):
        """Index j starts a block that cannot be reached by falling through (the two
        instructions before it are an unconditional jump and its delay slot).  When exactly
        one branch targets it, return that branch's index, else None."""
        src = self.sources.get(self.addr[j])
        if src is None or len(src) != 1:
            return None
        return src[0]

    def nonneg(self, i, reg, depth=14, level=0):
        """Is the FP register `reg`, as it stands before index i, plainly non-negative?"""
        j = i - 1
        while j >= 0 and i - j <= depth and level < 6:
            k = self.d(j)
            if k[0] == 'fp3' and k[2] == reg:
                if k[1] == 'mul':
                    return k[3] == k[4]
                if k[1] == 'add':
                    return self.nonneg(j, k[3], depth, level + 1) and self.nonneg(j, k[4], depth, level + 1)
                if k[1] == 'max':
                    for r in (k[3], k[4]):
                        c = self.fp_const(j, r)
                        if c is not None and c >= 0:
                            return True
                return False
            if k[0] == 'fp2' and k[2] == reg:
                if k[1] == 'abs':
                    return True
                if k[1] == 'mov':
                    return self.nonneg(j, k[3], depth, level + 1)
                return False
            if k[0] == 'sqrt' and k[1] == reg:
                return True
            if k[0] == 'mtc1' and k[2] == reg:
                v = self.gpr_const(j, k[1])
                return v is not None and not v & 0x80000000
            if k[0] == 'lwc1' and k[1] == reg:
                c = self.ro_float(j)
                return c is not None and c >= 0
            if k[0] in ('rsqrt', 'cvts', 'cvtw') and k[1] == reg or k[0] == 'acc' and k[2] == reg:
                return False
            if k[0] in ('call', 'jump', 'ret'):
                return False
            j -= 1
        return False

    # -- the backward scan
    def origin(self, i, reg, flo):
        """How did FP register `reg` get its value before index i, and was it tested?
        -> (class string, origin detail)"""
        watch = {reg}            # FP registers that hold the operand
        gwatch = set()           # GPRs that hold it (before mtc1 / cvt.s.w)
        slot = None              # (off, base) it was loaded from
        how = None               # origin tag once the definition is found
        isint = False
        join = False
        came_from = -1           # index of a branch we stepped back through
        hops = 0
        j = i - 1
        steps = 0
        while j >= 0 and self.addr[j] >= flo and steps < WINDOW:
            if self.addr[j + 1] in self.targets:
                join = True
            k = self.d(j)
            kind = k[0]
            tilde = '~' if join else ''
            if kind == 'cmp' and self.branches_next(j):
                hit = k[2] in watch or k[3] in watch
                other = k[3] if k[2] in watch else k[2]
                if not hit and how is None:
                    # a compare on abs / mov / neg of the operand counts too
                    for a_, b_ in ((k[2], k[3]), (k[3], k[2])):
                        if self.copy_of(j, a_) in watch:
                            hit, other = True, b_
                            break
                if hit:
                    c = self.fp_const(j, other, 40)
                    return ('guard-zero' if c == 0.0 else 'guard-bound') + tilde, how or 'reg'
            if kind == 'cbr' and gwatch and any(r in gwatch for r in k[1]):
                return 'guard-zero' + tilde, how or 'int'
            if kind == 'gpr' and gwatch and k[1] in ('slt', 'slti', 'sltu', 'sltiu') \
                    and any(r in gwatch for r in k[2][1:]):
                return 'guard-bound' + tilde, how or 'int'
            if how is None:
                if kind == 'fp2' and k[2] in watch:
                    watch.discard(k[2])
                    watch.add(k[3])
                elif kind == 'cvts' and k[1] in watch:
                    watch.discard(k[1])
                    watch.add(k[2])
                    isint = True
                elif kind == 'mtc1' and k[2] in watch:
                    v = self.gpr_const(j, k[1])
                    if v is not None:
                        if isint:
                            return ('const' if v else 'open:zero-const'), 'int %d' % v
                        if v & 0x7f800000 == 0:
                            return 'open:zero-const', '0.0'
                        self.last_bits = v
                        return 'const', '%g' % struct.unpack('<f', struct.pack('<I', v))[0]
                    how = 'int' if isint else 'bits'
                    watch.discard(k[2])
                    gwatch.add(k[1])
                elif kind == 'lwc1' and k[1] in watch:
                    c = self.ro_float(j)
                    if c is not None and not isint:
                        if c == 0.0:
                            return 'open:zero-const', '0.0'
                        return 'const', '%g' % c
                    a = self.abs_addr(j)
                    how = ('int' if isint else 'load') + (' %s(%s)' % (hex(k[2]), k[3]) if a is None else ' @%x' % a)
                    slot = (k[2], k[3])
                    watch.discard(k[1])
                elif kind == 'fp3' and k[2] in watch:
                    if k[1] in ('max', 'min'):
                        for r in (k[3], k[4]):
                            c = self.fp_const(j, r)
                            if c is not None:
                                return 'clamp' + tilde, '%s %g' % (k[1], c)
                    if k[1] == 'add':
                        for r, o in ((k[3], k[4]), (k[4], k[3])):
                            c = self.fp_const(j, r)
                            if c is not None and c > 0 and self.nonneg(j, o):
                                return 'const', 'nonneg + %g' % c
                    if k[1] == 'mul':
                        # x * (non-zero constant) is zero exactly when x is: keep following x
                        follow = None
                        for r, o in ((k[3], k[4]), (k[4], k[3])):
                            c = self.fp_const(j, r)
                            if c is not None and c != 0.0:
                                follow = o
                                break
                        if follow is not None:
                            watch.discard(k[2])
                            watch.add(follow)
                            j -= 1
                            steps += 1
                            continue
                    return 'open:' + k[1], ''
                elif kind == 'sqrt' and k[1] in watch:
                    return 'open:sqrt', 'nonneg' if self.nonneg(j, k[2]) else ''
                elif kind == 'rsqrt' and k[1] in watch:
                    return 'open:rsqrt', ''
                elif kind == 'acc' and k[2] in watch:
                    return 'open:acc', ''
                elif kind == 'cvtw' and k[1] in watch:
                    return 'open:bits', ''
                elif kind == 'call':
                    if 0 in watch:
                        return 'open:call', self.fname(k[1]) if k[1] else 'virtual'
                    if any(r < 20 for r in watch):
                        return 'open:?', 'lost at a call'
            else:
                # definition found: keep looking for a test of the same memory slot or of the
                # integer register the value was converted from
                if slot and kind == 'lwc1' and (k[2], k[3]) == slot:
                    g = self.slot_tested(j, k[1])
                    if g:
                        return g + '~', how
                if gwatch and kind == 'gpr' and k[2] and k[2][0] in gwatch \
                        and k[1] not in ('sw', 'sh', 'sb', 'sd'):
                    gwatch.discard(k[2][0])
                    if k[1] == 'move':
                        gwatch.add(k[2][1])
                    elif k[1] in ('lw', 'lh', 'lhu', 'lb', 'lbu') and slot is None:
                        m = MEM.match(k[2][1]) if len(k[2]) > 1 else None
                        if m:
                            slot = (int(m.group(1), 0), m.group(2))
            if kind in ('jump', 'ret') and j != came_from:
                # what follows this jump's delay slot is entered by branches only
                src = self.sole_entry(j + 2) if j + 2 < self.n else None
                if src is None or hops >= 3 or not flo <= self.addr[src]:
                    if how is None:
                        return 'open:flow', ''
                    break
                hops += 1
                ks = self.d(src)
                if ks[0] == 'cbr' and gwatch and any(r in gwatch for r in ks[1]):
                    return 'guard-zero~', how or 'int'
                came_from = src
                join = True
                j = src + 1 if src + 1 < self.n else src
                steps += 1
                continue
            j -= 1
            steps += 1
        if how:
            # wider, weaker search over the earlier part of the function
            lim = max(0, i - 600)
            if slot:
                for m in range(i - 1, lim, -1):
                    if self.addr[m] < flo:
                        break
                    km = self.d(m)
                    if km[0] == 'lwc1' and (km[2], km[3]) == slot:
                        g = self.slot_tested(m, km[1])
                        if g:
                            return g + '~', how
                    elif km[0] == 'gpr' and km[1] in ('lw', 'lh', 'lhu', 'lb', 'lbu') and len(km[2]) > 1:
                        mm = MEM.match(km[2][1])
                        if mm and (int(mm.group(1), 0), mm.group(2)) == slot and self.gpr_tested(m, km[2][0]):
                            return 'guard-zero~', how
            saved = {r for r in gwatch if r in ('$16', '$17', '$18', '$19', '$20', '$21', '$22', '$23', '$fp')}
            if saved:
                for m in range(i - 1, lim, -1):
                    if self.addr[m] < flo:
                        break
                    km = self.d(m)
                    if km[0] == 'cbr' and any(r in saved for r in km[1]):
                        return 'guard-zero~', how
                    if km[0] == 'gpr' and km[2] and km[2][0] in saved and km[1] not in ('sw', 'sh', 'sb', 'sd'):
                        break
            return 'open:' + how.split()[0], how
        if j < 0 or self.addr[j] < flo:
            if any(12 <= r <= 19 for r in watch):
                return 'open:arg', ''
        return 'open:?', ''

    def copy_of(self, j, reg):
        """Register that `reg` was made from by abs.s / mov.s / neg.s just before index j."""
        for q in range(j - 1, max(-1, j - 7), -1):
            kq = self.d(q)
            if kq[0] == 'fp2' and kq[2] == reg:
                return kq[3]
            if kq[0] in ('call', 'ret', 'jump'):
                break
            if kq[0] in ('fp3', 'acc') and kq[2] == reg or kq[0] in ('lwc1', 'sqrt', 'rsqrt', 'cvts', 'cvtw') and kq[1] == reg \
                    or kq[0] == 'mtc1' and kq[2] == reg:
                break
        return None

    def slot_tested(self, m, freg_):
        """The lwc1 at index m loaded `freg_`; is that register compared and branched on
        within the next few instructions?  -> 'guard-zero' / 'guard-bound' / None"""
        for q in range(m + 1, min(self.n, m + 10)):
            kq = self.d(q)
            if kq[0] == 'cmp' and freg_ in (kq[2], kq[3]):
                if not self.branches_next(q):
                    return None
                other = kq[3] if kq[2] == freg_ else kq[2]
                return 'guard-zero' if self.fp_const(q, other, 40) == 0.0 else 'guard-bound'
            if kq[0] in ('call', 'ret', 'jump'):
                return None
            if kq[0] in ('fp3', 'fp2', 'acc') and kq[2] == freg_ or kq[0] in ('lwc1', 'sqrt', 'rsqrt', 'cvts', 'cvtw') and kq[1] == freg_:
                return None
        return None

    def gpr_tested(self, m, reg):
        """Is GPR `reg`, loaded at index m, branched on within the next few instructions?"""
        for q in range(m + 1, min(self.n, m + 6)):
            kq = self.d(q)
            if kq[0] == 'cbr' and reg in kq[1]:
                return True
            if kq[0] in ('call', 'ret', 'jump'):
                return False
        return False

    # -- the forward scan
    def reach(self, i, reg, fhi):
        taint, slots, out, cmps = {reg}, set(), [], []
        pending = None
        j = i + 1
        steps = 0

        def add(x):
            if x not in out:
                out.append(x)

        while j < self.n and self.addr[j] <= fhi and steps < FWD and (taint or slots):
            k = self.d(j)
            kind = k[0]
            if kind == 'fp3':
                if k[3] in taint or k[4] in taint:
                    if k[1] in ('max', 'min'):
                        add('clamped')
                    else:
                        add('arith')
                    taint.add(k[2])
                else:
                    taint.discard(k[2])
            elif kind == 'acc':
                if k[3] in taint or k[4] in taint:
                    add('arith')
            elif kind == 'fp2':
                if k[3] in taint:
                    taint.add(k[2])
                else:
                    taint.discard(k[2])
            elif kind == 'sqrt':
                if k[2] in taint:
                    add('arith')
                    taint.add(k[1])
                else:
                    taint.discard(k[1])
            elif kind == 'rsqrt':
                if k[2] in taint or k[3] in taint:
                    add('arith')
                    taint.add(k[1])
                else:
                    taint.discard(k[1])
            elif kind == 'cmp':
                if k[2] in taint or k[3] in taint:
                    add('cmp@%x' % self.addr[j])
                    cmps.append(j)
            elif kind == 'cvtw':
                if k[2] in taint:
                    add('int')
                taint.discard(k[1])
            elif kind == 'cvts':
                taint.discard(k[1])
            elif kind == 'mfc1':
                if k[2] in taint:
                    add('bits')
            elif kind == 'mtc1':
                taint.discard(k[2])
            elif kind == 'swc1':
                if k[1] in taint:
                    if k[3] == '$sp':
                        slots.add(k[2])
                    else:
                        add('store %s(%s)' % (hex(k[2]), k[3]))
                elif k[3] == '$sp':
                    slots.discard(k[2])
            elif kind == 'lwc1':
                if k[3] == '$sp' and k[2] in slots:
                    taint.add(k[1])
                else:
                    taint.discard(k[1])
            if pending:
                what, tgt = pending
                pending = None
                if what == 'call':
                    if any(12 <= r <= 19 for r in taint):
                        add('arg>' + (self.fname(tgt) if tgt else 'virtual'))
                    taint = {r for r in taint if r >= 20}
                elif what == 'ret':
                    if 0 in taint:
                        add('ret')
                    break
                else:
                    break
            if kind == 'call':
                pending = ('call', k[1])
            elif kind == 'ret':
                pending = ('ret', None)
            elif kind == 'jump':
                pending = ('jump', None)
            j += 1
            steps += 1
        return out, cmps

    def int_use(self, i, fd):
        """What happens to the integer produced by cvt.w.s at index i (short look ahead)."""
        g, out = None, []
        for j in range(i + 1, min(self.n, i + 10)):
            k = self.d(j)
            if g is None:
                if k[0] == 'mfc1' and k[2] == fd:
                    g = k[1]
                elif k[0] == 'swc1' and k[1] == fd:
                    return 'store %s(%s)' % (hex(k[2]), k[3])
                elif k[0] == 'cvts' and k[2] == fd:
                    return 'floor/round-trip'
                elif k[0] in ('call', 'ret', 'jump'):
                    break
                continue
            if k[0] == 'gpr' and g in k[2]:
                mn = k[1]
                if mn in ('sll', 'addu', 'sllv') and k[2][0] != g or mn in ('lw', 'lh', 'lhu', 'lb', 'lbu', 'lwc1'):
                    out.append('index')
                elif mn in ('sb', 'sh', 'sw'):
                    out.append(mn)
                elif mn in ('andi', 'slt', 'slti', 'sltu', 'sltiu', 'move', 'addiu', 'subu', 'sll', 'sra', 'srl', 'addu'):
                    out.append(mn)
                else:
                    out.append(mn)
                if len(out) >= 2:
                    break
            elif k[0] == 'cbr' and g in k[1]:
                out.append('branch')
                break
            elif k[0] in ('call', 'ret', 'jump'):
                break
        return ','.join(dict.fromkeys(out)) if out else ('gpr' if g else '')


# ---------------------------------------------------------------------------------------
# site collection

def collect(P, wanted_funcs=None, lo=None, hi=None):
    """-> list of dicts: addr kind func area operand cls detail reach"""
    sites = []
    nan_cmp = {}
    for i in range(P.n):
        mn = P.mn[i]
        if mn not in ('div.s', 'sqrt.s', 'rsqrt.s', 'cvt.w.s', 'trunc.w.s', 'mtc1', '<unknown>'):
            continue
        a = P.addr[i]
        if lo is not None and not lo <= a < hi:
            continue
        k = P.d(i)
        kind = k[0]
        if kind not in ('fp3', 'sqrt', 'rsqrt', 'cvtw', 'mtc1') or (kind == 'fp3' and k[1] != 'div'):
            continue
        ent, flo, fhi = P.func_of(a)
        if wanted_funcs is not None and ent not in wanted_funcs:
            continue
        rec = {'addr': a, 'func': ent, 'area': P.area_of(a), 'detail': '', 'reach': ''}
        if kind == 'mtc1':
            v = P.gpr_const(i, k[1], 3)
            if v is None or v == 0:
                continue
            f = struct.unpack('<f', struct.pack('<I', v))[0]
            if not ((v >> 23) & 0xff == 0xff or abs(f) >= BIG):
                continue
            # an integer on its way through cvt.s.w is not a float constant
            if any(P.d(q)[0] == 'cvts' and P.d(q)[2] == k[2] for q in range(i + 1, min(P.n, i + 4))):
                continue
            r, _ = P.reach(i, k[2], fhi)
            rec.update(kind='big', operand='f%d' % k[2], cls='sentinel' if 'arith' not in r else 'open:arith',
                       detail='%08x %.3g' % (v, f), reach=' '.join(r))
            sites.append(rec)
            continue
        if kind == 'fp3':
            fd, opnd, name = k[2], k[4], 'div'
            cls, det = P.origin(i, opnd, flo)
        elif kind == 'rsqrt':
            fd, opnd, name = k[1], k[3], 'rsqrt'
            cls, det = P.origin(i, opnd, flo)
            if cls.startswith('open') and P.nonneg(i, opnd):
                det = (det + ' nonneg').strip()
        elif kind == 'sqrt':
            fd, opnd, name = k[1], k[2], 'sqrt'
            cb = P.fp_const_bits(i, opnd)
            if cb is not None and not cb & 0x80000000 and cb & 0x7f800000:
                rz, rn = sqrt_roundings(cb)
                cls = 'const'
                det = '%08x -> %08x' % (cb, rn) if rz == rn else '%08x -> %08x|%08x' % (cb, rz, rn)
            elif P.nonneg(i, opnd):
                cls, det = 'nonneg', ''
            else:
                P.last_bits = None
                cls, det = P.origin(i, opnd, flo)
                if cls == 'open:zero-const':
                    cls = 'const'
                cb = P.last_bits
                if cls == 'const' and cb and not cb & 0x80000000:
                    rz, rn = sqrt_roundings(cb)
                    det = '%08x -> %08x' % (cb, rn) if rz == rn else '%08x -> %08x|%08x' % (cb, rz, rn)
        else:
            fd, opnd, name = k[1], k[2], 'cvt'
            cls, det = P.origin(i, opnd, flo)
            if cls in ('const', 'open:zero-const'):
                cls = 'const'
            rec['reach'] = P.int_use(i, fd)
        rec.update(kind=name, operand='f%d' % opnd, cls=cls, detail=det)
        if name != 'cvt':
            r, cmps = P.reach(i, fd, fhi)
            rec['reach'] = ' '.join(r)
            if cls.startswith('open'):
                for c in cmps:
                    nan_cmp.setdefault(c, a)
        sites.append(rec)
    for c, src in sorted(nan_cmp.items()):
        a = P.addr[c]
        ent, flo, fhi = P.func_of(a)
        if wanted_funcs is not None and ent not in wanted_funcs:
            continue
        k = P.d(c)
        sites.append({'addr': a, 'func': ent, 'area': P.area_of(a), 'kind': 'cmp',
                      'operand': 'f%d,f%d' % (k[2], k[3]), 'cls': 'open:from-%x' % src,
                      'detail': k[1], 'reach': 'branch'})
    sites.sort(key=lambda r: (r['addr'], r['kind']))
    return sites


OPS_COLS = ['add', 'sub', 'mul', 'div', 'sqrt', 'rsqrt', 'min/max', 'compare', 'to-int', 'from-int', 'cop2']


def census(P, wanted_funcs=None, lo=None, hi=None):
    """Every single-precision operation per area: all of these round, so all of them are
    exposed to a rounding-mode or host difference whether or not they are 'hazards'."""
    rows = {}
    for i in range(P.n):
        mn = P.mn[i]
        key = None
        if mn in ('add.s', 'sub.s', 'mul.s', 'div.s'):
            key = mn[:3]
        elif mn in CMP:
            key = 'compare'
        elif mn in ('cvt.w.s', 'trunc.w.s'):
            key = 'to-int'
        elif mn == 'cvt.s.w':
            key = 'from-int'
        elif mn in ('sqrt.s', 'rsqrt.s', '<unknown>') or mn in COP2_TEXT:
            k = P.d(i)
            if k[0] == 'sqrt' or k[0] == 'rsqrt':
                key = k[0]
            elif k[0] == 'fp3' and k[1] in ('max', 'min'):
                key = 'min/max'
            elif k[0] == 'acc':
                key = 'add'
            elif P.img is not None:
                w = P.img.u32(P.addr[i])
                if w is not None and (w >> 26) in (0x12, 0x36, 0x3e):
                    key = 'cop2'
        if key is None:
            continue
        a = P.addr[i]
        if lo is not None and not lo <= a < hi:
            continue
        if wanted_funcs is not None and P.func_of(a)[0] not in wanted_funcs:
            continue
        r = rows.setdefault(P.area_of(a), {})
        r[key] = r.get(key, 0) + 1
    lines = ['%-11s' % 'area' + ''.join('%9s' % h for h in OPS_COLS)]
    tot = {}
    for a in [x[0] for x in P.areas] + ['-']:
        if a not in rows:
            continue
        lines.append('%-11s' % a + ''.join('%9d' % rows[a].get(k, 0) for k in OPS_COLS))
        for k in OPS_COLS:
            tot[k] = tot.get(k, 0) + rows[a].get(k, 0)
    lines.append('%-11s' % 'all' + ''.join('%9d' % tot.get(k, 0) for k in OPS_COLS))
    return lines


def reachable(P, roots, depth):
    """Entries of the roots and of everything they reach through jal / j."""
    by_entry = {}
    for lo, hi, ent in P.funcs:
        by_entry.setdefault(ent, []).append((lo, hi))
    seen, todo = set(), [(r, 0) for r in roots]
    while todo:
        ent, dep = todo.pop()
        if ent in seen or ent not in by_entry:
            continue
        seen.add(ent)
        if dep >= depth:
            continue
        for lo, hi in by_entry[ent]:
            i = P.index.get(lo)
            if i is None:
                i = bisect.bisect_left(P.addr, lo)
            while i < P.n and P.addr[i] <= hi:
                mn = P.mn[i]
                if mn == 'jal' or mn == 'j':
                    t = int(P.ops[i].split()[0], 16)
                    te = P.func_of(t)[0]
                    if te is not None and (mn == 'jal' or te != ent):
                        todo.append((te, dep + 1))
                i += 1
    return seen


SUMMARY_COLS = [
    ('div', 'div.s'), ('div-open', ' open'), ('rsqrt', 'rsqrt.s'), ('rsqrt-open', ' open'),
    ('sqrt', 'sqrt.s'), ('sqrt-open', ' open'), ('cvt', 'cvt.w.s'), ('cvt-open', ' open'),
    ('big', 'big const'), ('big-open', ' arith'), ('cmp', 'NaN-cmp'),
]


def summarise(P, sites):
    rows = {}
    for s in sites:
        r = rows.setdefault(s['area'], {})
        r[s['kind']] = r.get(s['kind'], 0) + 1
        if s['cls'].startswith('open') and s['kind'] != 'cmp':
            r[s['kind'] + '-open'] = r.get(s['kind'] + '-open', 0) + 1
    order = [a[0] for a in P.areas] + ['-']
    lines = ['%-11s' % 'area' + ''.join('%10s' % h for _, h in SUMMARY_COLS)]
    tot = {}
    for a in order:
        if a not in rows:
            continue
        lines.append('%-11s' % a + ''.join('%10d' % rows[a].get(k, 0) for k, _ in SUMMARY_COLS))
        for k, _ in SUMMARY_COLS:
            tot[k] = tot.get(k, 0) + rows[a].get(k, 0)
    lines.append('%-11s' % 'all' + ''.join('%10d' % tot.get(k, 0) for k, _ in SUMMARY_COLS))
    return lines


def class_table(sites):
    t = {}
    for s in sites:
        c = s['cls'].rstrip('~')
        if s['kind'] == 'cmp':
            c = 'open'
        t.setdefault(s['kind'], {})
        t[s['kind']][c] = t[s['kind']].get(c, 0) + 1
    out = []
    for kind in ('div', 'rsqrt', 'sqrt', 'cvt', 'big', 'cmp'):
        if kind in t:
            parts = ', '.join('%s %d' % kv for kv in sorted(t[kind].items(), key=lambda kv: -kv[1]))
            out.append('%-6s %s' % (kind, parts))
    return out


def sqrt_roundings(bits):
    """Single-precision square root of the positive float with these bits, correctly rounded
    two ways: (toward zero, to nearest).  Returned as bit patterns."""
    import math
    e = (bits >> 23) & 0xff
    m = (bits & 0x7fffff) | 0x800000
    # value = m * 2^(e - 150).  Scale so the integer root has 26+ bits.
    sh = 28 if (e - 150 + 28) % 2 == 0 else 29
    n = m << sh
    r = math.isqrt(n)                  # r = floor(sqrt(m) * 2^(sh/2)), 26 or 27 bits
    exact = r * r == n
    ex2 = (e - 150 + sh) // 2 - sh     # root = r * 2^(ex2)
    top = r.bit_length() - 24          # bits to drop
    rz = r >> top
    rem = r & ((1 << top) - 1)
    half = 1 << (top - 1)
    rn = rz + 1 if (rem > half or (rem == half and (not exact or rz & 1))) else rz
    out = []
    for v in (rz, rn):
        t = top
        if v >> 24:
            v >>= 1
            t += 1
        out.append(((ex2 + t + 150) << 23) | (v & 0x7fffff))
    return out[0], out[1]


def selftest():
    w = lambda fn, fd, fs, ft: (0x11 << 26) | (0x10 << 21) | (ft << 16) | (fs << 11) | (fd << 6) | fn
    assert decode_word(w(3, 1, 0, 1)) == ('fp3', 'div', 1, 0, 1)
    assert decode_word(w(4, 1, 0, 2)) == ('sqrt', 1, 2)
    assert decode_word(w(0x16, 4, 2, 1)) == ('rsqrt', 4, 2, 1)
    assert decode_word(w(0x28, 0, 0, 3)) == ('fp3', 'max', 0, 0, 3)
    assert decode_word(w(0x29, 0, 23, 21)) == ('fp3', 'min', 0, 23, 21)
    assert decode_word(0x00000000) is None
    assert decode_word(0x46010044) == ('sqrt', 1, 1)
    assert sqrt_roundings(0x40800000) == (0x40000000, 0x40000000)      # sqrt(4) = 2
    assert sqrt_roundings(0x40000000) == (0x3fb504f3, 0x3fb504f3)      # sqrt(2), rounds down
    assert sqrt_roundings(0x3e4ccccc) == (0x3ee4f92d, 0x3ee4f92e)      # the game's 0.2
    print('selftest ok')
    return 0


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if '-h' in args or '--help' in args:
        print(__doc__)
        return 0
    if '--selftest' in args:
        return selftest()

    def opt(name):
        if name in args:
            i = args.index(name)
            if i + 1 >= len(args):
                raise SystemExit('%s needs a value' % name)
            return args[i + 1]
        return None

    try:
        P = Program(ROOT)
    except FileNotFoundError as exc:
        print('fp_hazards: %s' % exc, file=sys.stderr)
        return 2
    wanted, lo, hi = None, None, None
    if opt('--func'):
        wanted = {int(x, 16) for x in opt('--func').split(',')}
    if opt('--reach'):
        depth = int(opt('--depth')) if opt('--depth') else 99
        roots = [P.func_of(int(x, 16))[0] or int(x, 16) for x in opt('--reach').split(',')]
        got = reachable(P, roots, depth)
        wanted = got if wanted is None else wanted | got
    if opt('--range'):
        lo, hi = (int(x, 16) for x in opt('--range').split(':'))
    sites = collect(P, wanted, lo, hi)
    if opt('--area'):
        keep = set(opt('--area').split(','))
        sites = [s for s in sites if s['area'] in keep]
    if opt('--kind'):
        keep = set(opt('--kind').split(','))
        sites = [s for s in sites if s['kind'] in keep]
    if '--open' in args:
        sites = [s for s in sites if s['cls'].startswith('open')]
    if P.img is None:
        print('# executable not found: R5900-only encodings were not decoded (%d <unknown> lines seen)'
              % P.undecoded, file=sys.stderr)
    if '--list' in args or '--tsv' in args:
        if '--tsv' in args:
            print('addr\tkind\tarea\tfunc\tname\toperand\tclass\tdetail\treach')
        for s in sites:
            name = P.fname(s['func'])
            if '--tsv' in args:
                print('%08x\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s' % (
                    s['addr'], s['kind'], s['area'], '%08x' % s['func'] if s['func'] else '',
                    name, s['operand'], s['cls'], s['detail'], s['reach']))
            else:
                print('%08x %-5s %-10s %-34s %-7s %-16s %-30s %s' % (
                    s['addr'], s['kind'], s['area'], name[:34], s['operand'], s['cls'],
                    s['detail'][:30], s['reach']))
        print('# %d sites' % len(sites), file=sys.stderr)
    if '--list' not in args and '--tsv' not in args or '--summary' in args:
        if wanted is not None:
            print('# %d functions selected' % len(wanted))
        print('Sites by area ("open" = not closed by the scan, read by hand)')
        for line in summarise(P, sites):
            print(line)
        print()
        print('Classes')
        for line in class_table(sites):
            print(line)
        if '--ops' in args:
            print()
            print('Every single-precision operation by area')
            for line in census(P, wanted, lo, hi):
                print(line)
    return 0


if __name__ == '__main__':
    sys.exit(main())
