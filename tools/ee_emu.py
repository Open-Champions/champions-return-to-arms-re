#!/usr/bin/env python3
"""ee_emu.py - a function-level interpreter for the PS2 Emotion Engine CPU (MIPS R5900).

This is NOT a console emulator.  It has no timing, no hardware registers, no kernel, no
IOP, no VU units and no BIOS.  It loads the segments of an ELF into a sparse memory, lets
you prepare registers and memory, runs ONE function (or a stretch of one) instruction by
instruction, and reports what the code did: return value, calls made, memory written.
Callees can be run for real, replaced by Python functions, or stubbed wholesale.

Command line:

  python3 ee_emu.py <elf> call <hexaddr> [args...] [options]
  python3 ee_emu.py <elf> run  <hexstart> <hexstop> [options]

  args       integers (decimal or 0x hex) go to a0..a3,t0..t3; f:<number> goes to f12..
  --stub A[=V]     replace the function at hex address A by "return V" (default 0)
  --stub-all       stub every call the code makes (they are still listed)
  --follow A       with --stub-all: let the function at A run for real (repeatable)
  --patch A=W      overwrite the instruction word at A with W before the run (hex)
  --pnach FILE[:SECTION]   apply the word patches of a PCSX2 .pnach file (optionally only
                   the sections whose title contains SECTION)
  --set A=W        store the 32-bit word W at address A before the run (hex)
  --reg NAME=V     set a register (v0, a0, s3, sp, ... or f0..f31 with a float)
  --alloc N        allocate N zeroed bytes; the address is printed and can be used in
                   args as @0, @1, ... in order of allocation
  --max-steps N    stop with an error after N instructions (default 5,000,000)
  --fpu MODEL      ps2 (default), ps2g1, chop or nearest - see "Floating point" below
  --auto-map       map untouched memory as zeroes instead of stopping (each page listed)
  --trace          print every executed address

What is implemented
  * MIPS III integer instructions with 64-bit registers and 32-bit addresses, little
    endian; delay slots; "likely" branches; HI/LO; unaligned load/store pairs.
  * R5900 additions: three-operand MULT/MULTU, MOVZ/MOVN, the second HI1/LO1 pair
    (MULT1, DIV1, MFHI1 ...), MADD/MADDU, 128-bit LQ/SQ, the shift-amount register, and
    the multimedia (MMI) instructions listed in MMI_IMPLEMENTED.
  * COP1 single precision: arithmetic, compares, min/max, conversions, the accumulator.
  * COP0: MFC0/MTC0 as a plain register file, EI/DI as a status bit.  Nothing else.

An instruction that is not implemented stops the run with UnimplementedInstruction, which
names the address and the word.  Nothing is guessed.  The same goes for a load or store
that touches memory nobody mapped (MemoryFault), an unaligned access, an integer overflow
trap, BREAK, SYSCALL and an integer division by zero (which does not trap on this CPU but
has no defined result).

Floating point (where this is an approximation)
  The R5900 FPU is not IEEE 754.  There are no NaNs, infinities or denormals: an exponent
  field of 255 is just a large number, an exponent field of 0 is zero, a result that is
  too large becomes +/-0x7fffffff and one that is too small becomes zero.  Results are
  rounded toward zero.  Those rules are implemented exactly, in integer arithmetic.
  What is NOT certain is the last bit of some results, because the hardware adder and
  multiplier keep fewer bits than an exact computation would.  No console was available
  to check against; the models below were written from memory of how emulator authors
  describe the hardware, and they do not all agree:
    add/subtract, selected by fpu_model:
      "ps2"     the smaller operand is aligned keeping six extra bits (the rest dropped
                toward minus infinity) and ignored when the exponents differ by 25 or
                more; the sum is then truncated.  (Software-float description.)  Default.
      "ps2g1"   the smaller operand keeps one extra bit (the rest of its magnitude is
                cleared) and is ignored at a difference of 25 or more; then the exact sum
                is truncated.  (Recompiler-style correction, as far as I recall it.)
      "chop"    the exact sum truncated toward zero - plain IEEE arithmetic in
                round-toward-zero mode, with no correction for the console's adder.
      "nearest" exact sum rounded to nearest even - only to measure how much a result
                depends on the rounding rule.
      The four differ by at most one unit in the last place, and only when the operands
      are far apart in size.
    multiply: the exact product truncated.  The hardware multiplier drops some low
      partial-product bits and is occasionally one unit lower; that is not modelled.
      fpu_mul_bias = True subtracts one unit from every inexact product, as a
      worst-case bound for sensitivity tests.
    divide, square root, reciprocal square root: the exact result truncated, or rounded
      to nearest when fpu_div_nearest = True (which of the two the console does is not
      established here).
    The exception flags in FCR31 are set in the obvious way and were not verified.
  When a result matters, run it under more than one model and see whether it moves;
  tools/ee_tests.py does that for the stick codec and for pad_apply.

Python use:

    from ee_emu import EE
    emu = EE('SLUS_209.73')
    emu.stub(0x216480, ret=0)                 # replace a callee
    emu.patch(0x199448, 0x10000060)           # apply a test patch
    v0 = emu.call(0x1e72f8)                   # run a function
    for w in emu.writes: ...                  # (pc, address, size, value) outside the stack
    for c in emu.calls: ...                   # CallRecord(site, target, args, ...)
"""
import math
import struct
import sys

M32 = 0xFFFFFFFF
M64 = 0xFFFFFFFFFFFFFFFF
SIGN32 = 0x80000000
SIGN64 = 0x8000000000000000
HIGH32 = 0xFFFFFFFF00000000

REG_NAMES = ('zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3',
             't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
             's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7',
             't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra')
REG = {name: number for number, name in enumerate(REG_NAMES)}
REG.update({'a4': 8, 'a5': 9, 'a6': 10, 'a7': 11, 's8': 30})
REG.update({'r%d' % n: n for n in range(32)})
REG.update({'$%d' % n: n for n in range(32)})

# MMI instructions that are implemented (everything else in that opcode space stops).
MMI_IMPLEMENTED = (
    'MADD MADDU PLZCW MFHI1 MTHI1 MFLO1 MTLO1 MULT1 MULTU1 DIV1 DIVU1 '
    'PSLLH PSRLH PSRAH PSLLW PSRLW PSRAW '
    'PADDW PSUBW PCGTW PMAXW PADDH PSUBH PCGTH PMAXH PADDB PSUBB PCGTB '
    'PADDSW PSUBSW PADDSH PSUBSH PADDSB PSUBSB PEXTLW PEXTLH PEXTLB PPACW PPACH PPACB '
    'PCEQW PMINW PCEQH PMINH PCEQB PADDUW PSUBUW PADDUH PSUBUH PADDUB PSUBUB '
    'PEXTUW PEXTUH PEXTUB QFSRV PCPYLD PAND PXOR PCPYUD POR PNOR PCPYH').split()


class EmuError(Exception):
    """Base class: the run stopped because continuing would mean guessing."""


class UnimplementedInstruction(EmuError):
    def __init__(self, pc, word, what=''):
        self.pc, self.word, self.what = pc, word, what
        EmuError.__init__(self, 'unimplemented instruction at 0x%08x: word 0x%08x%s'
                          % (pc, word, ' (%s)' % what if what else ''))


class MemoryFault(EmuError):
    def __init__(self, pc, addr, size, kind):
        self.pc, self.addr, self.size, self.kind = pc, addr, size, kind
        EmuError.__init__(self, '%s of %d byte(s) at unmapped address 0x%08x (pc 0x%08x)'
                          % (kind, size, addr, pc))


class CpuTrap(EmuError):
    """Something the real CPU would raise an exception for."""


class StepLimit(EmuError):
    pass


def s32(x):
    x &= M32
    return x - 0x100000000 if x & SIGN32 else x


def s64(x):
    x &= M64
    return x - 0x10000000000000000 if x & SIGN64 else x


def sx32(x):
    """Low 32 bits of x sign-extended to an unsigned 64-bit pattern."""
    x &= M32
    return x | HIGH32 if x & SIGN32 else x


def sx16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def float_to_raw(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def raw_to_float(raw):
    """IEEE reading of a raw single (an R5900 exponent-255 value shows as inf/nan)."""
    return struct.unpack('<f', struct.pack('<I', raw & M32))[0]


# ---------------------------------------------------------------------------------------
# R5900 single-precision arithmetic on raw 32-bit patterns.
# value = mantissa * 2**(exponent - 150); exponent field 0 is zero, 255 is ordinary.
# ---------------------------------------------------------------------------------------

FPU_MODELS = ('ps2', 'ps2g1', 'chop', 'nearest')
FMAX = 0x7FFFFFFF
FLAG_O, FLAG_U, FLAG_D, FLAG_I = 1, 2, 4, 8


def _unpack(raw):
    exp = (raw >> 23) & 0xFF
    if exp == 0:
        return raw >> 31, 0, 0
    return raw >> 31, (raw & 0x7FFFFF) | 0x800000, exp


def _pack(sign, mag, e2, nearest, flags):
    """Raw single for (-1)**sign * mag * 2**e2 (mag an exact non-negative integer)."""
    if mag == 0:
        return sign << 31
    shift = mag.bit_length() - 24
    if shift > 0:
        m = mag >> shift
        if nearest:
            rem = mag & ((1 << shift) - 1)
            half = 1 << (shift - 1)
            if rem > half or (rem == half and (m & 1)):
                m += 1
                if m == 0x1000000:
                    m >>= 1
                    shift += 1
    else:
        m = mag << -shift
    exp = e2 + shift + 150
    if exp > 255:
        flags.append(FLAG_O)
        return (sign << 31) | FMAX
    if exp < 1:
        flags.append(FLAG_U)
        return sign << 31
    return (sign << 31) | (exp << 23) | (m & 0x7FFFFF)


def fp_add(a, b, model='ps2', flags=None):
    """a + b.  flags, when given, is a list that receives FLAG_O / FLAG_U."""
    if flags is None:
        flags = []
    sa, ma, ea = _unpack(a)
    sb, mb, eb = _unpack(b)
    if ma == 0 and mb == 0:
        return (sa & sb) << 31
    if ma == 0:
        return b & M32
    if mb == 0:
        return a & M32
    if model == 'ps2':
        if ea < eb:
            a, b, sa, sb, ma, mb, ea, eb = b, a, sb, sa, mb, ma, eb, ea
        diff = ea - eb
        if diff >= 25:
            return a & M32
        big = -ma if sa else ma
        small = -mb if sb else mb
        man = (big << 6) + ((small << 6) >> diff)   # >> floors, as an arithmetic shift does
        if man == 0:
            return 0
        mag = -man if man < 0 else man
        exp = ea - 6
        shift = mag.bit_length() - 24
        if shift > 0:
            mag >>= shift
        else:
            mag <<= -shift
        exp += shift
        sign = 1 if man < 0 else 0
        if exp > 255:
            flags.append(FLAG_O)
            return (sign << 31) | FMAX
        if exp < 1:
            flags.append(FLAG_U)
            return sign << 31
        return (sign << 31) | (exp << 23) | (mag & 0x7FFFFF)
    if model == 'ps2g1':
        diff = ea - eb
        if diff >= 25:
            return a & M32
        if diff <= -25:
            return b & M32
        if diff > 1:
            mb &= -1 << (diff - 1)
        elif diff < -1:
            ma &= -1 << (-diff - 1)
    e = ea if ea < eb else eb
    total = ((-ma if sa else ma) << (ea - e)) + ((-mb if sb else mb) << (eb - e))
    if total == 0:
        return 0
    if total < 0:
        return _pack(1, -total, e - 150, model == 'nearest', flags)
    return _pack(0, total, e - 150, model == 'nearest', flags)


def fp_sub(a, b, model='ps2', flags=None):
    return fp_add(a, (b ^ SIGN32) & M32, model, flags)


def fp_mul(a, b, model='ps2', flags=None, bias=False):
    if flags is None:
        flags = []
    sa, ma, ea = _unpack(a)
    sb, mb, eb = _unpack(b)
    sign = sa ^ sb
    if ma == 0 or mb == 0:
        return sign << 31
    product = ma * mb
    raw = _pack(sign, product, ea + eb - 300, model == 'nearest', flags)
    if bias and not flags:
        shift = product.bit_length() - 24
        if shift > 0 and product & ((1 << shift) - 1) and (raw & 0x7FFFFFFF) > 0x00800000:
            raw -= 1
    return raw


def fp_div(a, b, model='ps2', flags=None, nearest=False):
    if flags is None:
        flags = []
    nearest = nearest or model == 'nearest'
    sa, ma, ea = _unpack(a)
    sb, mb, eb = _unpack(b)
    sign = sa ^ sb
    if mb == 0:
        flags.append(FLAG_I if ma == 0 else FLAG_D)
        return (sign << 31) | FMAX
    if ma == 0:
        return sign << 31
    quotient, remainder = divmod(ma << 40, mb)
    quotient = (quotient << 1) | (1 if remainder else 0)       # sticky bit
    return _pack(sign, quotient, ea - eb - 41, nearest, flags)


def fp_sqrt(a, model='ps2', flags=None, nearest=False):
    """Square root of |a|; FLAG_I when a is negative and not zero."""
    if flags is None:
        flags = []
    nearest = nearest or model == 'nearest'
    sa, ma, ea = _unpack(a)
    if ma == 0:
        return sa << 31
    if sa:
        flags.append(FLAG_I)
    e = ea - 150
    if e & 1:
        ma <<= 1
        e -= 1
    wide = ma << 48
    root = math.isqrt(wide)
    root = (root << 1) | (1 if root * root != wide else 0)       # sticky bit
    return _pack(0, root, e // 2 - 25, nearest, flags)


def fp_rsqrt(a, b, model='ps2', flags=None, nearest=False):
    """a / sqrt(b), computed as the hardware instruction is usually described: two steps."""
    if flags is None:
        flags = []
    return fp_div(a, fp_sqrt(b, model, flags, nearest), model, flags, nearest)


def fp_to_int(a):
    """CVT.W.S: truncate toward zero, saturate."""
    sign, man, exp = _unpack(a)
    if man == 0:
        return 0
    if exp >= 158:
        return 0x80000000 if sign else 0x7FFFFFFF
    shift = exp - 150
    mag = man << shift if shift >= 0 else man >> -shift
    return (-mag) & M32 if sign else mag


def fp_from_int(word, model='ps2'):
    """CVT.S.W of a signed 32-bit integer."""
    value = s32(word)
    if value == 0:
        return 0
    if value < 0:
        return _pack(1, -value, 0, model == 'nearest', [])
    return _pack(0, value, 0, model == 'nearest', [])


def fp_cmp(a, b):
    """-1, 0 or 1; +0 equals -0; ordering is by sign and magnitude of the raw pattern."""
    x = -(a & 0x7FFFFFFF) if a & SIGN32 else a & 0x7FFFFFFF
    y = -(b & 0x7FFFFFFF) if b & SIGN32 else b & 0x7FFFFFFF
    return (x > y) - (x < y)


# ---------------------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------------------

PAGE = 4096


class Memory:
    """Sparse little-endian memory in 4 KiB pages.  Unmapped access is an error unless
    auto_map is set, in which case the page is created zeroed and noted in auto_mapped."""

    def __init__(self):
        self.pages = {}
        self.auto_map = False
        self.auto_mapped = []
        self.pc_source = None           # object with .cur for fault messages

    def map(self, addr, size):
        first, last = addr >> 12, (addr + max(size, 1) - 1) >> 12
        pages = self.pages
        for index in range(first, last + 1):
            if index not in pages:
                pages[index] = bytearray(PAGE)

    def is_mapped(self, addr, size=1):
        return all(i in self.pages for i in range(addr >> 12, ((addr + size - 1) >> 12) + 1))

    def _missing(self, addr, size, kind):
        if self.auto_map:
            page = self.pages[addr >> 12] = bytearray(PAGE)
            self.auto_mapped.append((addr >> 12) << 12)
            return page
        pc = self.pc_source.cur if self.pc_source is not None else 0
        raise MemoryFault(pc, addr, size, kind)

    def read(self, addr, size):
        addr &= M32
        out = bytearray()
        while size > 0:
            page = self.pages.get(addr >> 12)
            if page is None:
                page = self._missing(addr, size, 'read')
            off = addr & 0xFFF
            take = min(size, PAGE - off)
            out += page[off:off + take]
            addr = (addr + take) & M32
            size -= take
        return bytes(out)

    def write(self, addr, data):
        addr &= M32
        pos, size = 0, len(data)
        while pos < size:
            page = self.pages.get(addr >> 12)
            if page is None:
                page = self._missing(addr, size - pos, 'write')
            off = addr & 0xFFF
            take = min(size - pos, PAGE - off)
            page[off:off + take] = data[pos:pos + take]
            addr = (addr + take) & M32
            pos += take

    def load(self, addr, size):
        """Unsigned little-endian integer of size bytes."""
        page = self.pages.get(addr >> 12)
        off = addr & 0xFFF
        if page is not None and off + size <= PAGE:
            return int.from_bytes(page[off:off + size], 'little')
        return int.from_bytes(self.read(addr, size), 'little')

    def store(self, addr, size, value):
        page = self.pages.get(addr >> 12)
        off = addr & 0xFFF
        if page is not None and off + size <= PAGE:
            page[off:off + size] = (value & ((1 << (size * 8)) - 1)).to_bytes(size, 'little')
        else:
            self.write(addr, (value & ((1 << (size * 8)) - 1)).to_bytes(size, 'little'))

    # convenience accessors for test code
    def u8(self, addr):
        return self.load(addr & M32, 1)

    def u16(self, addr):
        return self.load(addr & M32, 2)

    def u32(self, addr):
        return self.load(addr & M32, 4)

    def u64(self, addr):
        return self.load(addr & M32, 8)

    def s8(self, addr):
        value = self.load(addr & M32, 1)
        return value - 0x100 if value & 0x80 else value

    def s16(self, addr):
        return sx16(self.load(addr & M32, 2))

    def s32(self, addr):
        return s32(self.load(addr & M32, 4))

    def f32(self, addr):
        return raw_to_float(self.load(addr & M32, 4))

    def w8(self, addr, value):
        self.store(addr & M32, 1, value)

    def w16(self, addr, value):
        self.store(addr & M32, 2, value)

    def w32(self, addr, value):
        self.store(addr & M32, 4, value)

    def w64(self, addr, value):
        self.store(addr & M32, 8, value)

    def wf32(self, addr, value):
        self.store(addr & M32, 4, float_to_raw(value))

    def cstr(self, addr, limit=4096):
        out = bytearray()
        while len(out) < limit:
            byte = self.load(addr & M32, 1)
            if byte == 0:
                break
            out.append(byte)
            addr += 1
        return out.decode('latin1')


class CallRecord:
    """One call made by the code under test."""
    __slots__ = ('site', 'target', 'args', 'fargs', 'stubbed', 'ret', 'name')

    def __init__(self, site, target, args, fargs):
        self.site, self.target, self.args, self.fargs = site, target, args, fargs
        self.stubbed, self.ret, self.name = False, None, None

    def __repr__(self):
        return 'call 0x%08x from 0x%08x (%s)%s' % (
            self.target, self.site, ', '.join('0x%x' % (a & M32) for a in self.args[:4]),
            ' [stubbed]' if self.stubbed else '')


def parse_pnach(path):
    """[(section title, [(address, size in bytes, value), ...]), ...] from a PCSX2 .pnach."""
    sizes = {'byte': 1, 'short': 2, 'word': 4, 'double': 8}
    sections, current = [], None
    with open(path, encoding='utf-8-sig') as source:
        for line in source:
            line = line.strip()
            if line.startswith('[') and line.endswith(']'):
                current = (line[1:-1], [])
                sections.append(current)
            elif line.startswith('patch='):
                parts = line[len('patch='):].split(',')
                if len(parts) != 5 or parts[1].strip().upper() != 'EE' or parts[3].strip() not in sizes:
                    raise ValueError('%s: unsupported patch line %r' % (path, line))
                if current is None:
                    current = ('', [])
                    sections.append(current)
                current[1].append((int(parts[2], 16), sizes[parts[3].strip()], int(parts[4], 16)))
    return sections


def load_elf_segments(path):
    """[(vaddr, file bytes, memory size)] for every PT_LOAD of a 32-bit little-endian ELF,
    and the entry point."""
    with open(path, 'rb') as source:
        data = source.read()
    if data[:4] != b'\x7fELF' or data[4] != 1 or data[5] != 1:
        raise ValueError('%s: not a 32-bit little-endian ELF' % path)
    entry, phoff = struct.unpack_from('<II', data, 24)
    phentsize, phnum = struct.unpack_from('<HH', data, 42)
    segments = []
    for index in range(phnum):
        kind, offset, vaddr, _paddr, filesz, memsz = struct.unpack_from('<6I', data, phoff + index * phentsize)
        if kind == 1:
            segments.append((vaddr, data[offset:offset + filesz], memsz))
    return segments, entry


# ---------------------------------------------------------------------------------------
# The CPU
# ---------------------------------------------------------------------------------------

class EE:
    RETURN_ADDR = 0x00000FF0        # never mapped; reaching it ends call()
    STACK_LO, STACK_HI = 0x01F00000, 0x02000000
    HEAP_LO, HEAP_HI = 0x01000000, 0x01700000

    def __init__(self, elf_path=None, fpu_model='ps2'):
        if fpu_model not in FPU_MODELS:
            raise ValueError('fpu_model must be one of %s' % (FPU_MODELS,))
        self.mem = Memory()
        self.mem.pc_source = self
        self.r = [0] * 32               # low 64 bits of each general register
        self.rh = [0] * 32              # high 64 bits (MMI and LQ/SQ only)
        self.hi = self.lo = self.hi1 = self.lo1 = 0
        self.sa = 0
        self.f = [0] * 32               # raw single-precision patterns
        self.acc = 0
        self.fcr31 = 0x01000001
        self.cop0 = [0] * 32
        self.pc, self.npc, self.cur = 0, 4, 0
        self.fpu_model = fpu_model
        self.fpu_mul_bias = False
        self.fpu_div_nearest = False
        self.steps = 0
        self.hooks = {}                 # address -> function(emu)
        self.stub_names = {}
        self.breakpoints = set()
        self.follow = None              # None: run every callee; a set: stub all others
        self.default_ret = 0
        self.calls = []
        self.record_calls = True
        self.writes = []                # (pc, address, size, value) outside the stack
        self.record_writes = True
        self.reads = None               # set to [] to record (pc, address, size, value)
        self.trace = None               # set to [] to record every executed pc
        self.notes = []                 # things worth telling the reader (e.g. divide by 0)
        self.syscall_handler = None
        self.div_zero = 'stop'          # or 'r5900': continue with the reported HI/LO values
        self.patches = {}               # address -> original word
        self.stack_lo, self.stack_hi = self.STACK_LO, self.STACK_HI
        self.mem.map(self.stack_lo, self.stack_hi - self.stack_lo)
        self.r[29] = self.stack_hi - 0x100
        self._heap = self.HEAP_LO
        self._pending_call = None
        self._fresh_call = None
        self._call_site = 0
        self.entry = None
        self._build_tables()
        if elf_path is not None:
            self.load_elf(elf_path)

    # ---- set-up ------------------------------------------------------------------------
    def load_elf(self, path):
        segments, self.entry = load_elf_segments(path)
        for vaddr, blob, memsz in segments:
            self.mem.map(vaddr, max(memsz, len(blob)))
            self.mem.write(vaddr, blob)

    def load_words(self, addr, words):
        """Map memory at addr and store a list of 32-bit instruction or data words."""
        self.mem.map(addr, len(words) * 4)
        self.mem.write(addr, struct.pack('<%dI' % len(words), *[w & M32 for w in words]))

    def alloc(self, size, align=16, fill=0):
        """Zeroed (or filled) block from a bump heap that the game does not know about."""
        self._heap = (self._heap + align - 1) & -align
        addr = self._heap
        if addr + size > self.HEAP_HI:
            raise EmuError('test heap exhausted')
        self.mem.map(addr, size)
        if fill:
            self.mem.write(addr, bytes([fill & 0xFF]) * size)
        self._heap += max(size, 1)
        return addr

    def patch(self, addr, word):
        """Overwrite one instruction word, remembering the original."""
        if addr not in self.patches:
            self.patches[addr] = self.mem.u32(addr)
        self.mem.w32(addr, word)

    def unpatch(self):
        for addr, word in self.patches.items():
            self.mem.w32(addr, word)
        self.patches = {}

    def apply_pnach(self, path, section=None):
        """Apply the word patches of a .pnach file; returns the number of words applied.
        section, when given, selects the sections whose title contains that text."""
        count = 0
        for title, entries in parse_pnach(path):
            if section is not None and section.lower() not in title.lower():
                continue
            for addr, size, value in entries:
                if size != 4:
                    raise ValueError('only word patches are supported (%s)' % title)
                self.patch(addr, value)
                count += 1
        return count

    def hook(self, addr, function):
        """Call function(emu) whenever execution reaches addr.  The instruction at addr
        then runs normally unless the function moved the pc (see jump)."""
        self.hooks[addr] = function

    def unhook(self, addr):
        self.hooks.pop(addr, None)
        self.stub_names.pop(addr, None)

    def stub(self, addr, ret=0, function=None, name=None):
        """Replace the function at addr: record the call, optionally call
        function(emu) (its integer result, if any, becomes the return value), set v0 and
        return to the caller.  ret=None leaves v0 alone."""
        def run_stub(emu):
            value = function(emu) if function is not None else None
            if value is None:
                value = ret
            if value is not None:
                emu.r[2] = int(value) & M64
            rec = emu._fresh_call
            if rec is None and emu.record_calls:
                # reached by a plain jump (tail call): the caller's caller is in ra
                rec = CallRecord((emu.r[31] - 8) & M32, addr, tuple(emu.r[4:12]),
                                 tuple(emu.f[12:20]))
                rec.name = name
                emu.calls.append(rec)
            if rec is not None:
                rec.stubbed, rec.ret = True, value
            emu.jump(emu.r[31] & M32)
        self.hooks[addr] = run_stub
        if name:
            self.stub_names[addr] = name

    def jump(self, addr):
        self.pc = addr & M32
        self.npc = (addr + 4) & M32

    def reg(self, name):
        return self.r[REG[name]]

    def set_reg(self, name, value):
        self.r[REG[name]] = int(value) & M64

    def fget(self, index):
        return raw_to_float(self.f[index])

    def fset(self, index, value):
        self.f[index] = float_to_raw(value)

    def reset_log(self):
        self.calls, self.writes, self.notes, self.steps = [], [], [], 0
        if self.reads is not None:
            self.reads = []
        if self.trace is not None:
            self.trace = []

    # ---- running -----------------------------------------------------------------------
    def call(self, addr, *args, fargs=(), max_steps=5000000, sp=None):
        """Run the function at addr with integer args in a0-a3,t0-t3 and float args in
        f12.. ; returns v0 as an unsigned 64-bit value (see also f[0])."""
        if len(args) > 8:
            raise ValueError('at most 8 register arguments')
        for index, value in enumerate(args):
            self.r[4 + index] = int(value) & M64
        for index, value in enumerate(fargs):
            self.f[12 + index] = float_to_raw(value)
        if sp is not None:
            self.r[29] = sp & M64
        self.r[31] = self.RETURN_ADDR
        self.jump(addr)
        reason = self.run(max_steps=max_steps)
        if reason != 'return':
            raise EmuError('call to 0x%08x stopped at 0x%08x: %s' % (addr, self.pc, reason))
        return self.r[2]

    def run(self, start=None, until=(), max_steps=5000000):
        """Execute from start (or the current pc) until the pc reaches an address in
        until or a breakpoint ('stop'), or the call() return address ('return').  The
        first instruction always executes.  Raises StepLimit after max_steps."""
        if start is not None:
            self.jump(start)
        stops = set(until) | self.breakpoints
        mem = self.mem
        pages = mem.pages
        hooks = self.hooks
        ops = self._ops
        r, rh = self.r, self.rh
        ret_addr = self.RETURN_ADDR
        first = True
        budget = max_steps
        while True:
            pc = self.pc
            if pc == ret_addr:
                return 'return'
            if not first and pc in stops:
                return 'stop'
            first = False
            if pc == self._pending_call:
                self._pending_call = None
                if self._enter_call(pc):
                    continue
                function = hooks.get(pc)
                if function is not None:
                    function(self)
                self._fresh_call = None
                if self.pc != pc:
                    continue
            elif hooks:
                function = hooks.get(pc)
                if function is not None:
                    function(self)
                    if self.pc != pc:
                        continue
            if budget <= 0:
                raise StepLimit('step limit of %d reached at 0x%08x' % (max_steps, pc))
            budget -= 1
            if pc & 3:
                raise CpuTrap('pc 0x%08x is not word aligned' % pc)
            page = pages.get(pc >> 12)
            if page is None:
                self.cur = pc
                raise MemoryFault(pc, pc, 4, 'instruction fetch')
            off = pc & 0xFFF
            word = int.from_bytes(page[off:off + 4], 'little')
            self.cur = pc
            self.pc = self.npc
            self.npc = (self.npc + 4) & M32
            self.steps += 1
            if self.trace is not None:
                self.trace.append(pc)
            ops[word >> 26](word)
            r[0] = 0
            rh[0] = 0

    def _enter_call(self, target):
        """Control has arrived at the target of a linking jump.  Returns True when the
        call was auto-stubbed."""
        rec = None
        if self.record_calls:
            r = self.r
            rec = CallRecord(self._call_site, target, tuple(r[4:12]),
                             tuple(self.f[12:20]))
            rec.name = self.stub_names.get(target)
            self.calls.append(rec)
        if self.follow is not None and target not in self.follow and target not in self.hooks:
            if self.default_ret is not None:
                self.r[2] = self.default_ret & M64
            if rec is not None:
                rec.stubbed, rec.ret = True, self.default_ret
            self.jump(self.r[31] & M32)
            return True
        self._fresh_call = rec
        return False

    # ---- memory access from instructions -----------------------------------------------
    def _load(self, addr, size):
        if addr & (size - 1):
            raise CpuTrap('unaligned %d-byte load from 0x%08x at pc 0x%08x' % (size, addr, self.cur))
        value = self.mem.load(addr, size)
        if self.reads is not None:
            self.reads.append((self.cur, addr, size, value))
        return value

    def _store(self, addr, size, value):
        if addr & (size - 1):
            raise CpuTrap('unaligned %d-byte store to 0x%08x at pc 0x%08x' % (size, addr, self.cur))
        self.mem.store(addr, size, value)
        if self.record_writes and not self.stack_lo <= addr < self.stack_hi:
            self.writes.append((self.cur, addr, size, value & ((1 << (size * 8)) - 1)))

    def _unimplemented(self, word, what=''):
        raise UnimplementedInstruction(self.cur, word, what)

    def _branch(self, taken, word, likely=False):
        if self.pc != ((self.cur + 4) & M32):
            raise CpuTrap('branch in a delay slot at 0x%08x' % self.cur)
        if taken:
            self.npc = (self.cur + 4 + (sx16(word) << 2)) & M32
        elif likely:
            self.pc = self.npc
            self.npc = (self.npc + 4) & M32

    def _link(self, target):
        self._pending_call = target
        self._call_site = self.cur

    # ---- decode tables -----------------------------------------------------------------
    def _build_tables(self):
        bad = self._unimplemented
        ops = [bad] * 64
        ops[0x00] = self._special
        ops[0x01] = self._regimm
        ops[0x02] = self._j
        ops[0x03] = self._jal
        ops[0x04] = self._beq
        ops[0x05] = self._bne
        ops[0x06] = self._blez
        ops[0x07] = self._bgtz
        ops[0x08] = self._addi
        ops[0x09] = self._addiu
        ops[0x0A] = self._slti
        ops[0x0B] = self._sltiu
        ops[0x0C] = self._andi
        ops[0x0D] = self._ori
        ops[0x0E] = self._xori
        ops[0x0F] = self._lui
        ops[0x10] = self._cop0
        ops[0x11] = self._cop1
        ops[0x14] = self._beql
        ops[0x15] = self._bnel
        ops[0x16] = self._blezl
        ops[0x17] = self._bgtzl
        ops[0x18] = self._daddi
        ops[0x19] = self._daddiu
        ops[0x1A] = self._ldl
        ops[0x1B] = self._ldr
        ops[0x1C] = self._mmi
        ops[0x1E] = self._lq
        ops[0x1F] = self._sq
        ops[0x20] = self._lb
        ops[0x21] = self._lh
        ops[0x22] = self._lwl
        ops[0x23] = self._lw
        ops[0x24] = self._lbu
        ops[0x25] = self._lhu
        ops[0x26] = self._lwr
        ops[0x27] = self._lwu
        ops[0x28] = self._sb
        ops[0x29] = self._sh
        ops[0x2A] = self._swl
        ops[0x2B] = self._sw
        ops[0x2C] = self._sdl
        ops[0x2D] = self._sdr
        ops[0x2E] = self._swr
        ops[0x2F] = self._nop          # CACHE: no cache is modelled
        ops[0x31] = self._lwc1
        ops[0x33] = self._nop          # PREF
        ops[0x37] = self._ld
        ops[0x39] = self._swc1
        ops[0x3F] = self._sd
        self._ops = ops

        sp = [bad] * 64
        sp[0x00] = self._sll
        sp[0x02] = self._srl
        sp[0x03] = self._sra
        sp[0x04] = self._sllv
        sp[0x06] = self._srlv
        sp[0x07] = self._srav
        sp[0x08] = self._jr
        sp[0x09] = self._jalr
        sp[0x0A] = self._movz
        sp[0x0B] = self._movn
        sp[0x0C] = self._syscall
        sp[0x0D] = self._break
        sp[0x0F] = self._nop           # SYNC
        sp[0x10] = self._mfhi
        sp[0x11] = self._mthi
        sp[0x12] = self._mflo
        sp[0x13] = self._mtlo
        sp[0x14] = self._dsllv
        sp[0x16] = self._dsrlv
        sp[0x17] = self._dsrav
        sp[0x18] = self._mult
        sp[0x19] = self._multu
        sp[0x1A] = self._div
        sp[0x1B] = self._divu
        sp[0x20] = self._add
        sp[0x21] = self._addu
        sp[0x22] = self._sub
        sp[0x23] = self._subu
        sp[0x24] = self._and
        sp[0x25] = self._or
        sp[0x26] = self._xor
        sp[0x27] = self._nor
        sp[0x28] = self._mfsa
        sp[0x29] = self._mtsa
        sp[0x2A] = self._slt
        sp[0x2B] = self._sltu
        sp[0x2C] = self._dadd
        sp[0x2D] = self._daddu
        sp[0x2E] = self._dsub
        sp[0x2F] = self._dsubu
        sp[0x38] = self._dsll
        sp[0x3A] = self._dsrl
        sp[0x3B] = self._dsra
        sp[0x3C] = self._dsll32
        sp[0x3E] = self._dsrl32
        sp[0x3F] = self._dsra32
        self._sp = sp

        fs = [bad] * 64                # COP1, format S
        fs[0x00] = self._f_add
        fs[0x01] = self._f_sub
        fs[0x02] = self._f_mul
        fs[0x03] = self._f_div
        fs[0x04] = self._f_sqrt
        fs[0x05] = self._f_abs
        fs[0x06] = self._f_mov
        fs[0x07] = self._f_neg
        fs[0x16] = self._f_rsqrt
        fs[0x18] = self._f_adda
        fs[0x19] = self._f_suba
        fs[0x1A] = self._f_mula
        fs[0x1C] = self._f_madd
        fs[0x1D] = self._f_msub
        fs[0x1E] = self._f_madda
        fs[0x1F] = self._f_msuba
        fs[0x24] = self._f_cvtw
        fs[0x28] = self._f_max
        fs[0x29] = self._f_min
        fs[0x30] = self._f_cf
        fs[0x32] = self._f_ceq
        fs[0x34] = self._f_clt
        fs[0x36] = self._f_cle
        self._fs = fs

    # ---- primary opcodes ---------------------------------------------------------------
    def _nop(self, w):
        pass

    def _special(self, w):
        self._sp[w & 63](w)

    def _regimm(self, w):
        code = (w >> 16) & 31
        value = self.r[(w >> 21) & 31]
        negative = value >> 63
        if code == 0x00:      # BLTZ
            self._branch(negative, w)
        elif code == 0x01:    # BGEZ
            self._branch(not negative, w)
        elif code == 0x02:    # BLTZL
            self._branch(negative, w, True)
        elif code == 0x03:    # BGEZL
            self._branch(not negative, w, True)
        elif code in (0x10, 0x11, 0x12, 0x13):   # BLTZAL BGEZAL BLTZALL BGEZALL
            taken = bool(negative) if code in (0x10, 0x12) else not negative
            self.r[31] = (self.cur + 8) & M32
            self._branch(taken, w, code >= 0x12)
            if taken:
                self._link(self.npc)
        elif code == 0x18:    # MTSAB: shift amount in bytes
            self.sa = (value ^ w) & 15
        elif code == 0x19:    # MTSAH: halfwords, kept as bytes
            self.sa = ((value ^ w) & 7) * 2
        else:
            self._unimplemented(w, 'REGIMM %#x' % code)

    def _j(self, w):
        if self.pc != ((self.cur + 4) & M32):
            raise CpuTrap('jump in a delay slot at 0x%08x' % self.cur)
        self.npc = ((self.cur + 4) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)

    def _jal(self, w):
        self._j(w)
        self.r[31] = (self.cur + 8) & M32
        self._link(self.npc)

    def _beq(self, w):
        r = self.r
        self._branch(r[(w >> 21) & 31] == r[(w >> 16) & 31], w)

    def _bne(self, w):
        r = self.r
        self._branch(r[(w >> 21) & 31] != r[(w >> 16) & 31], w)

    def _blez(self, w):
        value = self.r[(w >> 21) & 31]
        self._branch(value == 0 or value >> 63, w)

    def _bgtz(self, w):
        value = self.r[(w >> 21) & 31]
        self._branch(value != 0 and not value >> 63, w)

    def _beql(self, w):
        r = self.r
        self._branch(r[(w >> 21) & 31] == r[(w >> 16) & 31], w, True)

    def _bnel(self, w):
        r = self.r
        self._branch(r[(w >> 21) & 31] != r[(w >> 16) & 31], w, True)

    def _blezl(self, w):
        value = self.r[(w >> 21) & 31]
        self._branch(value == 0 or value >> 63, w, True)

    def _bgtzl(self, w):
        value = self.r[(w >> 21) & 31]
        self._branch(value != 0 and not value >> 63, w, True)

    def _addi(self, w):
        total = s32(self.r[(w >> 21) & 31]) + sx16(w)
        if not -0x80000000 <= total <= 0x7FFFFFFF:
            raise CpuTrap('integer overflow (ADDI) at 0x%08x' % self.cur)
        self.r[(w >> 16) & 31] = total & M64

    def _addiu(self, w):
        value = (self.r[(w >> 21) & 31] + sx16(w)) & M32
        self.r[(w >> 16) & 31] = value | HIGH32 if value & SIGN32 else value

    def _daddi(self, w):
        total = s64(self.r[(w >> 21) & 31]) + sx16(w)
        if not -SIGN64 <= total < SIGN64:
            raise CpuTrap('integer overflow (DADDI) at 0x%08x' % self.cur)
        self.r[(w >> 16) & 31] = total & M64

    def _daddiu(self, w):
        self.r[(w >> 16) & 31] = (self.r[(w >> 21) & 31] + sx16(w)) & M64

    def _slti(self, w):
        self.r[(w >> 16) & 31] = 1 if s64(self.r[(w >> 21) & 31]) < sx16(w) else 0

    def _sltiu(self, w):
        self.r[(w >> 16) & 31] = 1 if self.r[(w >> 21) & 31] < (sx16(w) & M64) else 0

    def _andi(self, w):
        self.r[(w >> 16) & 31] = self.r[(w >> 21) & 31] & (w & 0xFFFF)

    def _ori(self, w):
        self.r[(w >> 16) & 31] = self.r[(w >> 21) & 31] | (w & 0xFFFF)

    def _xori(self, w):
        self.r[(w >> 16) & 31] = self.r[(w >> 21) & 31] ^ (w & 0xFFFF)

    def _lui(self, w):
        self.r[(w >> 16) & 31] = sx32((w & 0xFFFF) << 16)

    # ---- loads and stores --------------------------------------------------------------
    def _ea(self, w):
        return (self.r[(w >> 21) & 31] + sx16(w)) & M32

    def _lb(self, w):
        value = self._load(self._ea(w), 1)
        self.r[(w >> 16) & 31] = value | 0xFFFFFFFFFFFFFF00 if value & 0x80 else value

    def _lbu(self, w):
        self.r[(w >> 16) & 31] = self._load(self._ea(w), 1)

    def _lh(self, w):
        value = self._load(self._ea(w), 2)
        self.r[(w >> 16) & 31] = value | 0xFFFFFFFFFFFF0000 if value & 0x8000 else value

    def _lhu(self, w):
        self.r[(w >> 16) & 31] = self._load(self._ea(w), 2)

    def _lw(self, w):
        value = self._load(self._ea(w), 4)
        self.r[(w >> 16) & 31] = value | HIGH32 if value & SIGN32 else value

    def _lwu(self, w):
        self.r[(w >> 16) & 31] = self._load(self._ea(w), 4)

    def _ld(self, w):
        self.r[(w >> 16) & 31] = self._load(self._ea(w), 8)

    def _lq(self, w):
        addr = self._ea(w) & ~15       # the R5900 ignores the low four address bits
        value = self._load(addr, 16)
        rt = (w >> 16) & 31
        self.r[rt] = value & M64
        self.rh[rt] = value >> 64

    def _sb(self, w):
        self._store(self._ea(w), 1, self.r[(w >> 16) & 31])

    def _sh(self, w):
        self._store(self._ea(w), 2, self.r[(w >> 16) & 31])

    def _sw(self, w):
        self._store(self._ea(w), 4, self.r[(w >> 16) & 31])

    def _sd(self, w):
        self._store(self._ea(w), 8, self.r[(w >> 16) & 31])

    def _sq(self, w):
        rt = (w >> 16) & 31
        self._store(self._ea(w) & ~15, 16, (self.rh[rt] << 64) | self.r[rt])

    def _lwl(self, w):
        addr = self._ea(w)
        shift = (addr & 3) * 8
        mem = self._load(addr & ~3, 4)
        rt = (w >> 16) & 31
        self.r[rt] = sx32((self.r[rt] & (0x00FFFFFF >> shift)) | (mem << (24 - shift)))

    def _lwr(self, w):
        addr = self._ea(w)
        shift = (addr & 3) * 8
        mem = self._load(addr & ~3, 4)
        rt = (w >> 16) & 31
        if shift == 0:
            self.r[rt] = sx32(mem)
        else:                           # only the low bytes change; bits 32-63 are kept
            keep = (0xFFFFFFFF << (32 - shift)) & M32
            self.r[rt] = (self.r[rt] & (HIGH32 | keep)) | (mem >> shift)

    def _swl(self, w):
        addr = self._ea(w)
        shift = (addr & 3) * 8
        base = addr & ~3
        mem = self.mem.load(base, 4)
        value = self.r[(w >> 16) & 31] & M32
        self._store(base, 4, (value >> (24 - shift)) | (mem & ((0xFFFFFF00 << shift) & M32)))

    def _swr(self, w):
        addr = self._ea(w)
        shift = (addr & 3) * 8
        base = addr & ~3
        mem = self.mem.load(base, 4)
        value = self.r[(w >> 16) & 31] & M32
        self._store(base, 4, ((value << shift) & M32) | (mem & ((1 << shift) - 1)))

    def _ldl(self, w):
        addr = self._ea(w)
        shift = (addr & 7) * 8
        mem = self._load(addr & ~7, 8)
        rt = (w >> 16) & 31
        self.r[rt] = ((self.r[rt] & (0x00FFFFFFFFFFFFFF >> shift)) | (mem << (56 - shift))) & M64

    def _ldr(self, w):
        addr = self._ea(w)
        shift = (addr & 7) * 8
        mem = self._load(addr & ~7, 8)
        rt = (w >> 16) & 31
        keep = (M64 << (64 - shift)) & M64 if shift else 0
        self.r[rt] = (self.r[rt] & keep) | (mem >> shift)

    def _sdl(self, w):
        addr = self._ea(w)
        shift = (addr & 7) * 8
        base = addr & ~7
        mem = self.mem.load(base, 8)
        value = self.r[(w >> 16) & 31]
        self._store(base, 8, (value >> (56 - shift)) | (mem & ((0xFFFFFFFFFFFFFF00 << shift) & M64)))

    def _sdr(self, w):
        addr = self._ea(w)
        shift = (addr & 7) * 8
        base = addr & ~7
        mem = self.mem.load(base, 8)
        value = self.r[(w >> 16) & 31]
        self._store(base, 8, ((value << shift) & M64) | (mem & ((1 << shift) - 1)))

    def _lwc1(self, w):
        self.f[(w >> 16) & 31] = self._load(self._ea(w), 4)

    def _swc1(self, w):
        self._store(self._ea(w), 4, self.f[(w >> 16) & 31])

    # ---- SPECIAL -----------------------------------------------------------------------
    def _sll(self, w):
        self.r[(w >> 11) & 31] = sx32(self.r[(w >> 16) & 31] << ((w >> 6) & 31))

    def _srl(self, w):
        self.r[(w >> 11) & 31] = sx32((self.r[(w >> 16) & 31] & M32) >> ((w >> 6) & 31))

    def _sra(self, w):
        self.r[(w >> 11) & 31] = (s32(self.r[(w >> 16) & 31]) >> ((w >> 6) & 31)) & M64

    def _sllv(self, w):
        r = self.r
        r[(w >> 11) & 31] = sx32(r[(w >> 16) & 31] << (r[(w >> 21) & 31] & 31))

    def _srlv(self, w):
        r = self.r
        r[(w >> 11) & 31] = sx32((r[(w >> 16) & 31] & M32) >> (r[(w >> 21) & 31] & 31))

    def _srav(self, w):
        r = self.r
        r[(w >> 11) & 31] = (s32(r[(w >> 16) & 31]) >> (r[(w >> 21) & 31] & 31)) & M64

    def _dsllv(self, w):
        r = self.r
        r[(w >> 11) & 31] = (r[(w >> 16) & 31] << (r[(w >> 21) & 31] & 63)) & M64

    def _dsrlv(self, w):
        r = self.r
        r[(w >> 11) & 31] = r[(w >> 16) & 31] >> (r[(w >> 21) & 31] & 63)

    def _dsrav(self, w):
        r = self.r
        r[(w >> 11) & 31] = (s64(r[(w >> 16) & 31]) >> (r[(w >> 21) & 31] & 63)) & M64

    def _dsll(self, w):
        self.r[(w >> 11) & 31] = (self.r[(w >> 16) & 31] << ((w >> 6) & 31)) & M64

    def _dsrl(self, w):
        self.r[(w >> 11) & 31] = self.r[(w >> 16) & 31] >> ((w >> 6) & 31)

    def _dsra(self, w):
        self.r[(w >> 11) & 31] = (s64(self.r[(w >> 16) & 31]) >> ((w >> 6) & 31)) & M64

    def _dsll32(self, w):
        self.r[(w >> 11) & 31] = (self.r[(w >> 16) & 31] << (((w >> 6) & 31) + 32)) & M64

    def _dsrl32(self, w):
        self.r[(w >> 11) & 31] = self.r[(w >> 16) & 31] >> (((w >> 6) & 31) + 32)

    def _dsra32(self, w):
        self.r[(w >> 11) & 31] = (s64(self.r[(w >> 16) & 31]) >> (((w >> 6) & 31) + 32)) & M64

    def _jr(self, w):
        if self.pc != ((self.cur + 4) & M32):
            raise CpuTrap('jump in a delay slot at 0x%08x' % self.cur)
        self.npc = self.r[(w >> 21) & 31] & M32

    def _jalr(self, w):
        target = self.r[(w >> 21) & 31] & M32
        self._jr(w)
        rd = (w >> 11) & 31
        self.r[rd] = (self.cur + 8) & M32
        if rd:
            self._link(target)

    def _movz(self, w):
        r = self.r
        if r[(w >> 16) & 31] == 0:
            r[(w >> 11) & 31] = r[(w >> 21) & 31]

    def _movn(self, w):
        r = self.r
        if r[(w >> 16) & 31] != 0:
            r[(w >> 11) & 31] = r[(w >> 21) & 31]

    def _syscall(self, w):
        if self.syscall_handler is None:
            raise CpuTrap('SYSCALL at 0x%08x (v1 = %d); no kernel is modelled'
                          % (self.cur, s64(self.r[3])))
        self.syscall_handler(self)

    def _break(self, w):
        raise CpuTrap('BREAK code %d at 0x%08x' % ((w >> 16) & 0x3FF, self.cur))

    def _mfhi(self, w):
        self.r[(w >> 11) & 31] = self.hi

    def _mthi(self, w):
        self.hi = self.r[(w >> 21) & 31]

    def _mflo(self, w):
        self.r[(w >> 11) & 31] = self.lo

    def _mtlo(self, w):
        self.lo = self.r[(w >> 21) & 31]

    def _mfsa(self, w):
        self.r[(w >> 11) & 31] = self.sa

    def _mtsa(self, w):
        self.sa = self.r[(w >> 21) & 31] & M32

    def _mult(self, w):
        product = s32(self.r[(w >> 21) & 31]) * s32(self.r[(w >> 16) & 31])
        self.lo = sx32(product)
        self.hi = sx32(product >> 32)
        self.r[(w >> 11) & 31] = self.lo           # R5900: rd also receives LO

    def _multu(self, w):
        product = (self.r[(w >> 21) & 31] & M32) * (self.r[(w >> 16) & 31] & M32)
        self.lo = sx32(product)
        self.hi = sx32(product >> 32)
        self.r[(w >> 11) & 31] = self.lo

    def _divide(self, w, signed):
        """(quotient, remainder) as sign-extended 32-bit results."""
        if signed:
            a, b = s32(self.r[(w >> 21) & 31]), s32(self.r[(w >> 16) & 31])
            if b == 0:
                self._divide_by_zero()
                return (sx32(1 if a < 0 else -1), sx32(a))
            if a == -0x80000000 and b == -1:
                return (sx32(0x80000000), 0)
            quotient = abs(a) // abs(b)
            if (a < 0) != (b < 0):
                quotient = -quotient
            return (sx32(quotient), sx32(a - quotient * b))
        a, b = self.r[(w >> 21) & 31] & M32, self.r[(w >> 16) & 31] & M32
        if b == 0:
            self._divide_by_zero()
            return (M64, sx32(a))
        return (sx32(a // b), sx32(a % b))

    def _divide_by_zero(self):
        """The CPU does not trap and the architecture does not define the result.  Stop,
        unless the caller asked for the values the R5900 is reported to leave."""
        if self.div_zero != 'r5900':
            raise CpuTrap('integer division by zero at 0x%08x: the result is not defined; set '
                          'div_zero = "r5900" to continue with the values the hardware is '
                          'reported to leave' % self.cur)
        self.notes.append('divide by zero at 0x%08x: HI/LO set as the R5900 is reported to '
                          'leave them' % self.cur)

    def _div(self, w):
        self.lo, self.hi = self._divide(w, True)

    def _divu(self, w):
        self.lo, self.hi = self._divide(w, False)

    def _add(self, w):
        total = s32(self.r[(w >> 21) & 31]) + s32(self.r[(w >> 16) & 31])
        if not -0x80000000 <= total <= 0x7FFFFFFF:
            raise CpuTrap('integer overflow (ADD) at 0x%08x' % self.cur)
        self.r[(w >> 11) & 31] = total & M64

    def _addu(self, w):
        r = self.r
        value = (r[(w >> 21) & 31] + r[(w >> 16) & 31]) & M32
        r[(w >> 11) & 31] = value | HIGH32 if value & SIGN32 else value

    def _sub(self, w):
        total = s32(self.r[(w >> 21) & 31]) - s32(self.r[(w >> 16) & 31])
        if not -0x80000000 <= total <= 0x7FFFFFFF:
            raise CpuTrap('integer overflow (SUB) at 0x%08x' % self.cur)
        self.r[(w >> 11) & 31] = total & M64

    def _subu(self, w):
        r = self.r
        value = (r[(w >> 21) & 31] - r[(w >> 16) & 31]) & M32
        r[(w >> 11) & 31] = value | HIGH32 if value & SIGN32 else value

    def _dadd(self, w):
        total = s64(self.r[(w >> 21) & 31]) + s64(self.r[(w >> 16) & 31])
        if not -SIGN64 <= total < SIGN64:
            raise CpuTrap('integer overflow (DADD) at 0x%08x' % self.cur)
        self.r[(w >> 11) & 31] = total & M64

    def _daddu(self, w):
        r = self.r
        r[(w >> 11) & 31] = (r[(w >> 21) & 31] + r[(w >> 16) & 31]) & M64

    def _dsub(self, w):
        total = s64(self.r[(w >> 21) & 31]) - s64(self.r[(w >> 16) & 31])
        if not -SIGN64 <= total < SIGN64:
            raise CpuTrap('integer overflow (DSUB) at 0x%08x' % self.cur)
        self.r[(w >> 11) & 31] = total & M64

    def _dsubu(self, w):
        r = self.r
        r[(w >> 11) & 31] = (r[(w >> 21) & 31] - r[(w >> 16) & 31]) & M64

    def _and(self, w):
        r = self.r
        r[(w >> 11) & 31] = r[(w >> 21) & 31] & r[(w >> 16) & 31]

    def _or(self, w):
        r = self.r
        r[(w >> 11) & 31] = r[(w >> 21) & 31] | r[(w >> 16) & 31]

    def _xor(self, w):
        r = self.r
        r[(w >> 11) & 31] = r[(w >> 21) & 31] ^ r[(w >> 16) & 31]

    def _nor(self, w):
        r = self.r
        r[(w >> 11) & 31] = (r[(w >> 21) & 31] | r[(w >> 16) & 31]) ^ M64

    def _slt(self, w):
        r = self.r
        r[(w >> 11) & 31] = 1 if s64(r[(w >> 21) & 31]) < s64(r[(w >> 16) & 31]) else 0

    def _sltu(self, w):
        r = self.r
        r[(w >> 11) & 31] = 1 if r[(w >> 21) & 31] < r[(w >> 16) & 31] else 0

    # ---- COP0 --------------------------------------------------------------------------
    def _cop0(self, w):
        rs = (w >> 21) & 31
        if rs == 0x00:                  # MFC0: plain register file, no side effects
            self.r[(w >> 16) & 31] = sx32(self.cop0[(w >> 11) & 31])
        elif rs == 0x04:                # MTC0
            self.cop0[(w >> 11) & 31] = self.r[(w >> 16) & 31] & M32
        elif rs == 0x10 and (w & 63) == 0x38:   # EI
            self.cop0[12] |= 0x10000
        elif rs == 0x10 and (w & 63) == 0x39:   # DI
            self.cop0[12] &= ~0x10000
        else:
            self._unimplemented(w, 'COP0')

    # ---- COP1 --------------------------------------------------------------------------
    def _cop1(self, w):
        rs = (w >> 21) & 31
        if rs == 0x10:                  # format S
            self._fs[w & 63](w)
        elif rs == 0x00:                # MFC1
            self.r[(w >> 16) & 31] = sx32(self.f[(w >> 11) & 31])
        elif rs == 0x04:                # MTC1
            self.f[(w >> 11) & 31] = self.r[(w >> 16) & 31] & M32
        elif rs == 0x02:                # CFC1
            fs = (w >> 11) & 31
            if fs == 31:
                self.r[(w >> 16) & 31] = sx32(self.fcr31)
            elif fs == 0:
                self.r[(w >> 16) & 31] = 0x2E00
            else:
                self._unimplemented(w, 'CFC1 from control register %d' % fs)
        elif rs == 0x06:                # CTC1
            if (w >> 11) & 31 != 31:
                self._unimplemented(w, 'CTC1 to control register %d' % ((w >> 11) & 31))
            self.fcr31 = (self.r[(w >> 16) & 31] & 0x0083C078) | 0x01000001
        elif rs == 0x08:                # BC1F BC1T BC1FL BC1TL
            code = (w >> 16) & 31
            cond = bool(self.fcr31 & 0x00800000)
            if code == 0:
                self._branch(not cond, w)
            elif code == 1:
                self._branch(cond, w)
            elif code == 2:
                self._branch(not cond, w, True)
            elif code == 3:
                self._branch(cond, w, True)
            else:
                self._unimplemented(w, 'BC1')
        elif rs == 0x14:                # format W
            if (w & 63) == 0x20:        # CVT.S.W
                self.f[(w >> 6) & 31] = fp_from_int(self.f[(w >> 11) & 31], self.fpu_model)
            else:
                self._unimplemented(w, 'COP1 format W')
        else:
            self._unimplemented(w, 'COP1')

    def _fflags(self, flags, divide=False):
        fcr = self.fcr31 & (~0x0003C000 if divide else ~0x0000C000)
        for flag in flags:
            if flag == FLAG_O:
                fcr |= 0x8010
            elif flag == FLAG_U:
                fcr |= 0x4008
            elif flag == FLAG_D:
                fcr |= 0x10020
            elif flag == FLAG_I:
                fcr |= 0x20040
        self.fcr31 = fcr

    def _f_add(self, w):
        flags = []
        self.f[(w >> 6) & 31] = fp_add(self.f[(w >> 11) & 31], self.f[(w >> 16) & 31], self.fpu_model, flags)
        self._fflags(flags)

    def _f_sub(self, w):
        flags = []
        self.f[(w >> 6) & 31] = fp_sub(self.f[(w >> 11) & 31], self.f[(w >> 16) & 31], self.fpu_model, flags)
        self._fflags(flags)

    def _f_mul(self, w):
        flags = []
        self.f[(w >> 6) & 31] = fp_mul(self.f[(w >> 11) & 31], self.f[(w >> 16) & 31],
                                       self.fpu_model, flags, self.fpu_mul_bias)
        self._fflags(flags)

    def _f_div(self, w):
        flags = []
        self.f[(w >> 6) & 31] = fp_div(self.f[(w >> 11) & 31], self.f[(w >> 16) & 31], self.fpu_model,
                                       flags, self.fpu_div_nearest)
        self._fflags(flags, True)

    def _f_sqrt(self, w):
        flags = []
        self.f[(w >> 6) & 31] = fp_sqrt(self.f[(w >> 16) & 31], self.fpu_model, flags, self.fpu_div_nearest)
        self._fflags(flags, True)

    def _f_rsqrt(self, w):
        flags = []
        self.f[(w >> 6) & 31] = fp_rsqrt(self.f[(w >> 11) & 31], self.f[(w >> 16) & 31], self.fpu_model,
                                         flags, self.fpu_div_nearest)
        self._fflags(flags, True)

    def _f_abs(self, w):
        self.f[(w >> 6) & 31] = self.f[(w >> 11) & 31] & 0x7FFFFFFF
        self.fcr31 &= ~0x0000C000

    def _f_mov(self, w):
        self.f[(w >> 6) & 31] = self.f[(w >> 11) & 31]

    def _f_neg(self, w):
        self.f[(w >> 6) & 31] = self.f[(w >> 11) & 31] ^ SIGN32
        self.fcr31 &= ~0x0000C000

    def _f_adda(self, w):
        flags = []
        self.acc = fp_add(self.f[(w >> 11) & 31], self.f[(w >> 16) & 31], self.fpu_model, flags)
        self._fflags(flags)

    def _f_suba(self, w):
        flags = []
        self.acc = fp_sub(self.f[(w >> 11) & 31], self.f[(w >> 16) & 31], self.fpu_model, flags)
        self._fflags(flags)

    def _f_mula(self, w):
        flags = []
        self.acc = fp_mul(self.f[(w >> 11) & 31], self.f[(w >> 16) & 31], self.fpu_model, flags, self.fpu_mul_bias)
        self._fflags(flags)

    def _f_muladd(self, w, subtract, to_acc):
        flags = []
        product = fp_mul(self.f[(w >> 11) & 31], self.f[(w >> 16) & 31], self.fpu_model, flags, self.fpu_mul_bias)
        if subtract:
            value = fp_sub(self.acc, product, self.fpu_model, flags)
        else:
            value = fp_add(self.acc, product, self.fpu_model, flags)
        if to_acc:
            self.acc = value
        else:
            self.f[(w >> 6) & 31] = value
        self._fflags(flags)

    def _f_madd(self, w):
        self._f_muladd(w, False, False)

    def _f_msub(self, w):
        self._f_muladd(w, True, False)

    def _f_madda(self, w):
        self._f_muladd(w, False, True)

    def _f_msuba(self, w):
        self._f_muladd(w, True, True)

    def _f_cvtw(self, w):
        self.f[(w >> 6) & 31] = fp_to_int(self.f[(w >> 11) & 31])

    def _f_max(self, w):
        a, b = self.f[(w >> 11) & 31], self.f[(w >> 16) & 31]
        self.f[(w >> 6) & 31] = a if fp_cmp(a, b) >= 0 else b
        self.fcr31 &= ~0x0000C000

    def _f_min(self, w):
        a, b = self.f[(w >> 11) & 31], self.f[(w >> 16) & 31]
        self.f[(w >> 6) & 31] = a if fp_cmp(a, b) <= 0 else b
        self.fcr31 &= ~0x0000C000

    def _f_setc(self, cond):
        if cond:
            self.fcr31 |= 0x00800000
        else:
            self.fcr31 &= ~0x00800000

    def _f_cf(self, w):
        self._f_setc(False)

    def _f_ceq(self, w):
        self._f_setc(fp_cmp(self.f[(w >> 11) & 31], self.f[(w >> 16) & 31]) == 0)

    def _f_clt(self, w):
        self._f_setc(fp_cmp(self.f[(w >> 11) & 31], self.f[(w >> 16) & 31]) < 0)

    def _f_cle(self, w):
        self._f_setc(fp_cmp(self.f[(w >> 11) & 31], self.f[(w >> 16) & 31]) <= 0)

    # ---- MMI ---------------------------------------------------------------------------
    def _q(self, index):
        return (self.rh[index] << 64) | self.r[index]

    def _setq(self, index, value):
        self.r[index] = value & M64
        self.rh[index] = (value >> 64) & M64

    def _mmi(self, w):
        funct = w & 63
        rs, rt, rd, sa = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31, (w >> 6) & 31
        r = self.r
        if funct == 0x00 or funct == 0x01:      # MADD / MADDU
            if funct == 0x00:
                product = s32(r[rs]) * s32(r[rt])
            else:
                product = (r[rs] & M32) * (r[rt] & M32)
            total = (((self.hi & M32) << 32) | (self.lo & M32)) + product
            self.lo = sx32(total)
            self.hi = sx32(total >> 32)
            r[rd] = self.lo
        elif funct == 0x04:                     # PLZCW
            out = 0
            for half in (0, 1):
                value = (r[rs] >> (32 * half)) & M32
                if value & SIGN32:
                    value ^= M32
                out |= (32 - value.bit_length() - 1) << (32 * half)
            r[rd] = out
        elif funct == 0x10:                     # MFHI1
            r[rd] = self.hi1
        elif funct == 0x11:                     # MTHI1
            self.hi1 = r[rs]
        elif funct == 0x12:                     # MFLO1
            r[rd] = self.lo1
        elif funct == 0x13:                     # MTLO1
            self.lo1 = r[rs]
        elif funct == 0x18:                     # MULT1
            product = s32(r[rs]) * s32(r[rt])
            self.lo1 = sx32(product)
            self.hi1 = sx32(product >> 32)
            r[rd] = self.lo1
        elif funct == 0x19:                     # MULTU1
            product = (r[rs] & M32) * (r[rt] & M32)
            self.lo1 = sx32(product)
            self.hi1 = sx32(product >> 32)
            r[rd] = self.lo1
        elif funct == 0x1A:                     # DIV1
            self.lo1, self.hi1 = self._divide(w, True)
        elif funct == 0x1B:                     # DIVU1
            self.lo1, self.hi1 = self._divide(w, False)
        elif funct in (0x34, 0x36, 0x37):       # PSLLH PSRLH PSRAH
            self._setq(rd, _lanes_shift(self._q(rt), 16, sa & 15, funct))
        elif funct in (0x3C, 0x3E, 0x3F):       # PSLLW PSRLW PSRAW
            self._setq(rd, _lanes_shift(self._q(rt), 32, sa, funct - 8))
        elif funct == 0x08:
            self._mmi0(w, rs, rt, rd, sa)
        elif funct == 0x28:
            self._mmi1(w, rs, rt, rd, sa)
        elif funct == 0x09:
            self._mmi2(w, rs, rt, rd, sa)
        elif funct == 0x29:
            self._mmi3(w, rs, rt, rd, sa)
        else:
            self._unimplemented(w, 'MMI function %#x' % funct)

    def _mmi0(self, w, rs, rt, rd, sa):
        a, b = self._q(rs), self._q(rt)
        entry = _MMI0.get(sa)
        if entry is not None:
            self._setq(rd, _lanes(a, b, entry[0], entry[1]))
        elif sa == 0x12:                        # PEXTLW
            self._setq(rd, _interleave(a, b, 32, 0))
        elif sa == 0x16:                        # PEXTLH
            self._setq(rd, _interleave(a, b, 16, 0))
        elif sa == 0x1A:                        # PEXTLB
            self._setq(rd, _interleave(a, b, 8, 0))
        elif sa == 0x13:                        # PPACW
            self._setq(rd, _pack_lanes(a, b, 32))
        elif sa == 0x17:                        # PPACH
            self._setq(rd, _pack_lanes(a, b, 16))
        elif sa == 0x1B:                        # PPACB
            self._setq(rd, _pack_lanes(a, b, 8))
        else:
            self._unimplemented(w, 'MMI0 function %#x' % sa)

    def _mmi1(self, w, rs, rt, rd, sa):
        a, b = self._q(rs), self._q(rt)
        entry = _MMI1.get(sa)
        if entry is not None:
            self._setq(rd, _lanes(a, b, entry[0], entry[1]))
        elif sa == 0x12:                        # PEXTUW
            self._setq(rd, _interleave(a, b, 32, 64))
        elif sa == 0x16:                        # PEXTUH
            self._setq(rd, _interleave(a, b, 16, 64))
        elif sa == 0x1A:                        # PEXTUB
            self._setq(rd, _interleave(a, b, 8, 64))
        elif sa == 0x1B:                        # QFSRV
            self._setq(rd, (((a << 128) | b) >> ((self.sa & 15) * 8)) & ((1 << 128) - 1))
        else:
            self._unimplemented(w, 'MMI1 function %#x' % sa)

    def _mmi2(self, w, rs, rt, rd, sa):
        if sa == 0x0E:                          # PCPYLD
            self._setq(rd, (self.r[rs] << 64) | self.r[rt])
        elif sa == 0x12:                        # PAND
            self._setq(rd, self._q(rs) & self._q(rt))
        elif sa == 0x13:                        # PXOR
            self._setq(rd, self._q(rs) ^ self._q(rt))
        else:
            self._unimplemented(w, 'MMI2 function %#x' % sa)

    def _mmi3(self, w, rs, rt, rd, sa):
        if sa == 0x0E:                          # PCPYUD
            self._setq(rd, (self.rh[rt] << 64) | self.rh[rs])
        elif sa == 0x12:                        # POR
            self._setq(rd, self._q(rs) | self._q(rt))
        elif sa == 0x13:                        # PNOR
            self._setq(rd, (self._q(rs) | self._q(rt)) ^ ((1 << 128) - 1))
        elif sa == 0x1B:                        # PCPYH
            value = self._q(rt)
            low, high = value & 0xFFFF, (value >> 64) & 0xFFFF
            self._setq(rd, (high * 0x0001000100010001 << 64) | low * 0x0001000100010001)
        else:
            self._unimplemented(w, 'MMI3 function %#x' % sa)

    # ---- reporting ---------------------------------------------------------------------
    def write_summary(self):
        """Last value written to each (address, size), in address order."""
        last = {}
        for pc, addr, size, value in self.writes:
            last[(addr, size)] = (value, pc)
        return [(addr, size, value, pc) for (addr, size), (value, pc) in sorted(last.items())]

    def report(self, limit=200):
        lines = ['steps: %d' % self.steps,
                 'v0 = 0x%016x  v1 = 0x%016x  f0 = %r (raw 0x%08x)'
                 % (self.r[2], self.r[3], self.fget(0), self.f[0])]
        lines.append('calls: %d' % len(self.calls))
        for rec in self.calls[:limit]:
            lines.append('  ' + repr(rec))
        summary = self.write_summary()
        lines.append('memory written outside the stack: %d location(s), %d store(s)'
                     % (len(summary), len(self.writes)))
        for addr, size, value, pc in summary[:limit]:
            lines.append('  0x%08x  %2d byte(s)  = 0x%0*x   (last by pc 0x%08x)'
                         % (addr, size, size * 2, value, pc))
        if len(summary) > limit:
            lines.append('  ... %d more' % (len(summary) - limit))
        for page in self.mem.auto_mapped:
            lines.append('auto-mapped page 0x%08x' % page)
        for note in self.notes:
            lines.append('note: ' + note)
        return '\n'.join(lines)


# ---- MMI helpers (128-bit values as Python integers) ----------------------------------

def _signed(value, bits):
    return value - (1 << bits) if value >> (bits - 1) else value


def _lanes(a, b, bits, function):
    mask = (1 << bits) - 1
    out = 0
    for shift in range(0, 128, bits):
        out |= (function((a >> shift) & mask, (b >> shift) & mask, bits) & mask) << shift
    return out


def _sat_signed(value, bits):
    top = (1 << (bits - 1)) - 1
    return top if value > top else (-top - 1 if value < -top - 1 else value)


def _sat_unsigned(value, bits):
    top = (1 << bits) - 1
    return top if value > top else (0 if value < 0 else value)


_MMI0 = {
    0x00: (32, lambda a, b, n: a + b),                                             # PADDW
    0x01: (32, lambda a, b, n: a - b),                                             # PSUBW
    0x02: (32, lambda a, b, n: -1 if _signed(a, n) > _signed(b, n) else 0),        # PCGTW
    0x03: (32, lambda a, b, n: a if _signed(a, n) > _signed(b, n) else b),         # PMAXW
    0x04: (16, lambda a, b, n: a + b),                                             # PADDH
    0x05: (16, lambda a, b, n: a - b),                                             # PSUBH
    0x06: (16, lambda a, b, n: -1 if _signed(a, n) > _signed(b, n) else 0),        # PCGTH
    0x07: (16, lambda a, b, n: a if _signed(a, n) > _signed(b, n) else b),         # PMAXH
    0x08: (8, lambda a, b, n: a + b),                                              # PADDB
    0x09: (8, lambda a, b, n: a - b),                                              # PSUBB
    0x0A: (8, lambda a, b, n: -1 if _signed(a, n) > _signed(b, n) else 0),         # PCGTB
    0x10: (32, lambda a, b, n: _sat_signed(_signed(a, n) + _signed(b, n), n)),     # PADDSW
    0x11: (32, lambda a, b, n: _sat_signed(_signed(a, n) - _signed(b, n), n)),     # PSUBSW
    0x14: (16, lambda a, b, n: _sat_signed(_signed(a, n) + _signed(b, n), n)),     # PADDSH
    0x15: (16, lambda a, b, n: _sat_signed(_signed(a, n) - _signed(b, n), n)),     # PSUBSH
    0x18: (8, lambda a, b, n: _sat_signed(_signed(a, n) + _signed(b, n), n)),      # PADDSB
    0x19: (8, lambda a, b, n: _sat_signed(_signed(a, n) - _signed(b, n), n)),      # PSUBSB
}

_MMI1 = {
    0x02: (32, lambda a, b, n: -1 if a == b else 0),                               # PCEQW
    0x03: (32, lambda a, b, n: a if _signed(a, n) < _signed(b, n) else b),         # PMINW
    0x06: (16, lambda a, b, n: -1 if a == b else 0),                               # PCEQH
    0x07: (16, lambda a, b, n: a if _signed(a, n) < _signed(b, n) else b),         # PMINH
    0x0A: (8, lambda a, b, n: -1 if a == b else 0),                                # PCEQB
    0x10: (32, lambda a, b, n: _sat_unsigned(a + b, n)),                           # PADDUW
    0x11: (32, lambda a, b, n: _sat_unsigned(a - b, n)),                           # PSUBUW
    0x14: (16, lambda a, b, n: _sat_unsigned(a + b, n)),                           # PADDUH
    0x15: (16, lambda a, b, n: _sat_unsigned(a - b, n)),                           # PSUBUH
    0x18: (8, lambda a, b, n: _sat_unsigned(a + b, n)),                            # PADDUB
    0x19: (8, lambda a, b, n: _sat_unsigned(a - b, n)),                            # PSUBUB
}


def _lanes_shift(value, bits, amount, kind):
    """kind: 0x34 shift left, 0x36 logical right, 0x37 arithmetic right."""
    mask = (1 << bits) - 1
    out = 0
    for shift in range(0, 128, bits):
        lane = (value >> shift) & mask
        if kind == 0x34:
            lane = (lane << amount) & mask
        elif kind == 0x36:
            lane >>= amount
        else:
            lane = (_signed(lane, bits) >> amount) & mask
        out |= lane << shift
    return out


def _interleave(a, b, bits, base):
    """PEXTL*/PEXTU*: lanes of rt (b) and rs (a) from the 64 bits starting at base,
    interleaved with rt in the even positions."""
    mask = (1 << bits) - 1
    out = 0
    for index in range(64 // bits):
        low = (b >> (base + index * bits)) & mask
        high = (a >> (base + index * bits)) & mask
        out |= (low | (high << bits)) << (index * 2 * bits)
    return out


def _pack_lanes(a, b, bits):
    """PPAC*: the low half of every double-width lane; rt (b) fills the low 64 bits."""
    mask = (1 << bits) - 1
    out = 0
    count = 64 // bits
    for index in range(count):
        out |= ((b >> (index * 2 * bits)) & mask) << (index * bits)
        out |= ((a >> (index * 2 * bits)) & mask) << (64 + index * bits)
    return out


# ---------------------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------------------

def _number(text):
    text = text.strip()
    return int(text, 16) if text.lower().startswith(('0x', '-0x')) else int(text, 10)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description='Run one function of a PS2 executable in a function-level interpreter '
                    '(not a console emulator).')
    parser.add_argument('elf')
    parser.add_argument('command', choices=('call', 'run'))
    parser.add_argument('address', help='hex address of the function (call) or first instruction (run)')
    parser.add_argument('rest', nargs='*', help='call: arguments; run: hex stop address')
    parser.add_argument('--stub', action='append', default=[], metavar='ADDR[=VALUE]')
    parser.add_argument('--stub-all', action='store_true')
    parser.add_argument('--follow', action='append', default=[], metavar='ADDR')
    parser.add_argument('--patch', action='append', default=[], metavar='ADDR=WORD')
    parser.add_argument('--pnach', action='append', default=[], metavar='FILE[:SECTION]')
    parser.add_argument('--set', action='append', default=[], metavar='ADDR=WORD', dest='sets')
    parser.add_argument('--reg', action='append', default=[], metavar='NAME=VALUE')
    parser.add_argument('--alloc', action='append', default=[], type=int, metavar='BYTES')
    parser.add_argument('--max-steps', type=int, default=5000000)
    parser.add_argument('--fpu', choices=FPU_MODELS, default='ps2')
    parser.add_argument('--auto-map', action='store_true')
    parser.add_argument('--trace', action='store_true')
    args = parser.parse_args(argv)

    emu = EE(args.elf, fpu_model=args.fpu)
    emu.mem.auto_map = args.auto_map
    blocks = []
    for size in args.alloc:
        blocks.append(emu.alloc(size))
        print('allocated @%d = 0x%08x (%d bytes)' % (len(blocks) - 1, blocks[-1], size))
    for item in args.pnach:
        path, _, section = item.partition(':')
        print('applied %d patch word(s) from %s' % (emu.apply_pnach(path, section or None), path))
    for item in args.patch:
        addr, _, word = item.partition('=')
        emu.patch(int(addr, 16), int(word, 16))
    for item in args.sets:
        addr, _, word = item.partition('=')
        emu.mem.w32(int(addr, 16), int(word, 16))
    for item in args.stub:
        addr, _, value = item.partition('=')
        emu.stub(int(addr, 16), ret=_number(value) if value else 0)
    if args.stub_all:
        emu.follow = {int(a, 16) for a in args.follow}
    for item in args.reg:
        name, _, value = item.partition('=')
        name = name.strip().lower()
        if name.startswith('f') and name[1:].isdigit():
            emu.fset(int(name[1:]), float(value))
        else:
            emu.set_reg(name, _number(value))
    if args.trace:
        emu.trace = []

    start = int(args.address, 16)
    try:
        if args.command == 'call':
            ints, floats = [], []
            for text in args.rest:
                if text.startswith('f:'):
                    floats.append(float(text[2:]))
                elif text.startswith('@'):
                    ints.append(blocks[int(text[1:])])
                else:
                    ints.append(_number(text))
            emu.call(start, *ints, fargs=floats, max_steps=args.max_steps)
            print('returned from 0x%08x' % start)
        else:
            if len(args.rest) != 1:
                parser.error('run needs exactly one stop address')
            reason = emu.run(start=start, until={int(args.rest[0], 16)}, max_steps=args.max_steps)
            print('stopped at 0x%08x (%s)' % (emu.pc, reason))
    except EmuError as exc:
        print('STOPPED: %s' % exc)
        print(emu.report())
        return 1
    finally:
        if args.trace and emu.trace:
            print('trace: ' + ' '.join('%x' % pc for pc in emu.trace))
    print(emu.report())
    return 0


if __name__ == '__main__':
    sys.exit(main())
