#!/usr/bin/env python3
"""ee_emu.py - a function-level interpreter for the PS2 Emotion Engine CPU (MIPS R5900).

This is NOT a console emulator.  It has no timing, no IOP and no BIOS.  Hardware
registers, kernel calls and VU status exist only through the opt-in methods below,
and none of those is installed by default.  It loads the segments of an ELF into a
sparse memory, lets you prepare registers and memory, runs ONE function (or a stretch
of one) instruction by instruction, and reports what the code did: return value,
calls made, memory written.
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
has no defined result).  SYSCALL still stops unless the caller installed
syscall_handler.  install_deci2_kputs models only syscall 124 function 0x10,
the level-teardown diagnostic.  install_terminate_thread models only syscall 37
at the callers that do not read v0.  install_modelled_boot models the thread,
semaphore and boot callers listed on that method.  install_modelled_intc, also
opt-in, delivers one registered INTC handler when a modelled WaitSema would
block on a semaphore that handler signals, then retries.  It delivers only
while COP0 Status enables interrupts, unless installed with
while_disabled=True, which records Status at each delivery.  The delivery cadence
is modelled, not a vertical-blank interval.  install_ram_mirrors aliases the
uncached and uncached-accelerated windows 0x20000000 and 0x30000000 onto the
same main-RAM pages when the low 28 bits are below 32 MB.
install_modelled_main_ram creates heap pages from 0x0090a434 to 0x01fc0000
zeroed on first access.  install_modelled_dma_idle keeps three words of the
VIF1 and GIF channels and two status words, and returns the channel control
word with the start bit clear.  install_modelled_vpu_stat makes CFC2 of
register 29 return 0.  install_modelled_flush_cache and
install_modelled_end_of_heap accept FlushCache and EndOfHeap only at the
callers named on those methods.  install_modelled_gs_privileged accepts 8-byte
stores to the named GS privileged registers and reads CSR as 0; that is a
model, not a GS.  install_modelled_sif models the EE half of the SIF command
handshake read from 0x355608 and 0x355d68: the SIF syscalls at their read
callers, D_STAT and D5_CHCR as storage, and one modelled IOP command packet,
delivered through the game's own DMAC handler, where a poll waits for the
IOP.  It has no IOP.  Every value these handlers write in v0 is modelled, not a recovered kernel
result.  Every other number still raises CpuTrap.  The opt-ins compose; none
is installed by default.

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
        self.write_watch = None        # None, or ((address, size), ...): keep only overlaps
        self.reads = None               # set to [] to record (pc, address, size, value)
        self.trace = None               # set to [] to record every executed pc
        self.notes = []                 # things worth telling the reader (e.g. divide by 0)
        self.syscall_handler = None
        self._deci2_kputs = False
        self._terminate_thread = False
        self._modelled_boot = False
        self._modelled_intc = False
        self._ram_mirrors = False
        self._main_ram = False
        self._dma_idle = False
        self._vpu_stat = False
        self._flush_cache = False
        self._end_of_heap = False
        self._sif = False
        self._sif_while_disabled = False
        self._sif_regs = {}
        self._dmac = []
        self.sif_transfers = []         # (ra, src, dest, size, attr, packet bytes)
        self.sif_deliveries = []        # (channel, handler, command, index, value, Status)
        self.sif_reg_writes = []        # (ra, register, value)
        self._next_dma_id = 1
        self._gs_privileged = False
        self.gs_writes = []             # (pc, address, value) of modelled GS register stores
        self.gs_reads = []              # (pc, address, value) of modelled GS register loads
        self._hw_words = {}
        self._in_intc = False
        self._intc_while_disabled = False
        self.intc_delivery_status = []  # COP0 Status at each modelled INTC delivery
        self._threads = {}
        self._semas = {}
        self._intc = []
        self.intc_deliveries = []
        self._installed_syscalls = {}
        self._current_tid = 1
        self._next_tid = 2
        self._next_sid = 1
        self._next_handler = 1
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

    def install_deci2_kputs(self):
        """Opt in to the observed Deci2 function-0x10 contract.  Default runs are unchanged.

        Observed at 0x352e10–0x352e1c: Deci2Call loads v1 = 0x7c (124) and executes
        SYSCALL, then returns through jr ra.  The level-teardown diagnostic reaches
        that stub only as function 0x10, through dbg_printf 0x355490, the formatter
        0x354590, callback 0x355300, buffered putc 0x354240 and wrapper 0x35e428.
        Wrapper 0x35e428 stores its string pointer as the first parameter word and
        passes a0 = 0x10.  The branch at 0x354280 ignores v0, and 0x35531c overwrites
        v0 with 1, so this path does not observe the kernel result.  The retail
        result and the bytes of the string are therefore not part of the contract.
        This handler writes v0 = 0 and does not read guest memory.  Any other
        syscall number raises the same CpuTrap as an unhandled syscall, unless
        install_terminate_thread was also opted in, which adds only syscall 37
        at a caller that does not read v0.  Any other Deci2 function number,
        including 1, 3 and 4 at 0x35e218, 0x35e288 and 0x35e2b8, raises CpuTrap
        and names a0.  Assigning the bound method would pass the emulator twice;
        this stores the unbound dispatcher.
        """
        if self._deci2_kputs:
            raise EmuError('a syscall handler is already installed')
        self._deci2_kputs = True
        self.syscall_handler = EE._dispatch_opt_in_syscall

    def install_terminate_thread(self):
        """Opt in to TerminateThread where the caller does not read v0.

        Observed: wrapper 0x352830 loads v1 = 0x25 (37), executes SYSCALL at
        0x352834 and returns through jr ra.  Nine jal sites pass a thread id in
        a0.  Eight do not read v0.  Their return addresses are 0x17de0c and
        0x17e480 (the id word at 0x7cfd04, then 0x353b20 with that id), 0x17fe68
        (same id, then return), 0x31ef38 (the id word at 0x8eafe4, then
        0x361250), 0x36782c (then a tail call to DeleteThread), and 0x368e2c,
        0x3a02cc and 0x3a1270 (then DeleteThread of the same id).  The ninth
        return, 0x35f3bc, compares v0 with -1 and is rejected: the retail value
        is unknown.  This handler writes v0 = 0 and does not read or write
        guest memory.  That 0 is not a recovered kernel result, and the id word
        is left unchanged, so this does not claim the thread was stopped.  Any
        other syscall number, and syscall 37 with any other return address,
        still raises CpuTrap.  Composes with install_deci2_kputs.
        """
        if self._terminate_thread:
            raise EmuError('TerminateThread handler is already installed')
        self._terminate_thread = True
        self.syscall_handler = EE._dispatch_opt_in_syscall

    def install_modelled_boot(self):
        """Opt in to the boot thread and semaphore calls whose callers were read.

        Every v0 written here is modelled.  It is not a recovered kernel result.
        The current thread is id 1.  CreateThread ids start at 2.  Semaphore ids
        start at 1.  ReferThreadStatus word 0 is 0x10 because the callers at
        0x353b80 and 0x322504 compare with 16; that does not establish what the
        kernel calls that state.  A new semaphore's count is the word at param
        +8 and its max is the word at param +4: the fills at 0x16c67c, 0x19d2ac
        and 0x31ee9c put the large word at +4 and 0 or 1 at +8.  WaitSema with
        a zero count raises CpuTrap instead of succeeding.  StartThread does
        not enter the thread.  SetupThread is accepted only at 0x14fc48, where
        v0 is moved to sp.  SetupHeap is accepted only at 0x14fc64, where v0
        is not read.  SetGsCrt is accepted only for return address 0x19d36c,
        and GsPutIMR only for 0x34f79c; neither caller reads v0.  EnableIntc is
        accepted only for return address 0x353560, which saves v0; the modelled
        previous state is 1.  SetSyscall is accepted only for return addresses
        0x35c1d0 and 0x35c1dc.  A later syscall whose number was registered
        there, and whose next instructions are jr ra and nop, transfers to the
        registered address with ra unchanged.  AddIntcHandler records cause,
        handler and next.  EnableIntc marks that cause enabled.  Neither change
        delivers an interrupt.  FlushCache and EndOfHeap are not part of this
        opt-in; see install_modelled_flush_cache and
        install_modelled_end_of_heap.  Composes with the other opt-ins.
        """
        if self._modelled_boot:
            raise EmuError('modelled boot handler is already installed')
        self._modelled_boot = True
        self._threads = {1: {'priority': 0, 'status': 0x10, 'entry': 0,
                             'stack': 0, 'size': 0, 'gp': 0, 'started': False}}
        self._semas = {}
        self._intc = []
        self.intc_deliveries = []
        self._installed_syscalls = {}
        self._current_tid = 1
        self._next_tid = 2
        self._next_sid = 1
        self._next_handler = 1
        self.syscall_handler = EE._dispatch_opt_in_syscall

    def install_modelled_flush_cache(self):
        """Opt in to FlushCache (syscall 100) at the two callers that do not read v0.

        Accepted only for return addresses 0x19d628 and 0x355744.  The
        instruction at each is a lui that replaces the register it writes, and
        neither path reads v0 before that.  The modelled result is 0; this
        emulator has no cache to flush.  Any other caller still raises
        CpuTrap.  Composes with the other opt-ins.
        """
        if self._flush_cache:
            raise EmuError('modelled FlushCache is already installed')
        self._flush_cache = True
        self.syscall_handler = EE._dispatch_opt_in_syscall

    def install_modelled_end_of_heap(self):
        """Opt in to EndOfHeap (syscall 62) at the sbrk return 0x353138.

        0x353138 is the only return address of a jal to the wrapper 0x3529c0.
        That caller compares v0 with the requested break and, when v0 is not
        below the request, returns the previous break.  The modelled end is
        0x01fc0000.  Observed: SetupThread at 0x14fc48 is passed stack base
        0x01fc0000, and SetupHeap at 0x14fc64 is passed start 0x0090a434 and
        size -1.  Inferred: a heap of size -1 ends where that stack begins.
        It is not a recovered kernel limit.  Any other caller still raises
        CpuTrap.  Composes with the other opt-ins.
        """
        if self._end_of_heap:
            raise EmuError('modelled EndOfHeap is already installed')
        self._end_of_heap = True
        self.syscall_handler = EE._dispatch_opt_in_syscall

    # Privileged GS registers this boot stores to.  Names are the usual PS2
    # register map; they are labels here, not evidence from this image.
    GS_PRIVILEGED_STORES = {
        0x12000000: 'PMODE', 0x12000020: 'SMODE2', 0x12000070: 'DISPFB1',
        0x12000080: 'DISPLAY1', 0x12000090: 'DISPFB2', 0x120000A0: 'DISPLAY2',
        0x120000E0: 'BGCOLOR', 0x12001000: 'CSR',
    }
    GS_CSR = 0x12001000

    def install_modelled_gs_privileged(self):
        """Opt in to a GS privileged-register model.  It is a model, not a GS.

        Observed 8-byte stores, all executed by the round-5 to round-8 boots:
        engine_init 0x19d1dc and 0x19d39c-0x19d480 (0x12000000, 0x12000020,
        0x12000070-0x120000a0); 0x34f774 (0x200 to 0x12001000) and
        0x34fd90-0x34fdc8 in the graphics reset; the INTC handler 0x19b6e4
        stores 0 or 2 at 0x12000000 (0x19b6fc/0x19b710, chosen by the word at
        0x44fd6c) and, on its byte-0 path, at 0x12000020 and
        0x12000070-0x120000a0.  Observed 8-byte loads, all of 0x12001000:
        0x34f780 keeps bits 16-23 (stored as a halfword at 0x34f798); the
        handler's exits 0x19b730 and 0x19b8d8 keep bit 13 and store it as a
        byte at 0x44fd9c (0x19b750, 0x19b8f8).

        An 8-byte store to an address in GS_PRIVILEGED_STORES is accepted and
        recorded in gs_writes.  Nothing is kept: no store changes a later
        read.  An 8-byte load of 0x12001000 returns 0 and is recorded in
        gs_reads.  That 0 is modelled: bit 13 and bits 16-23 read 0 because
        the model says so, not because a GS reported them.  So the 0 the
        handler stores at 0x44fd9c is this model's output.  Any other access
        to 0x12000000-0x12001fff, or a load of any other GS register, still
        faults.  Do not also map that window.
        """
        if self._gs_privileged:
            raise EmuError('modelled GS registers are already installed')
        self._gs_privileged = True
        self.gs_writes = []
        self.gs_reads = []

    def _gs_access(self, addr, size, store):
        """True when the modelled GS registers accept this access."""
        if not self._gs_privileged or (addr & ~0x1FFF) != 0x12000000:
            return False
        if size != 8:
            return False
        if store:
            return addr in self.GS_PRIVILEGED_STORES
        return addr == self.GS_CSR

    # COP0 Status bits: IE (0), EXL (1), ERL (2), EIE (16).
    STATUS_IE, STATUS_EXL, STATUS_ERL, STATUS_EIE = 0x1, 0x2, 0x4, 0x10000

    def interrupts_enabled(self):
        """True when COP0 Status would take an interrupt: IE and EIE set, EXL and ERL clear.

        The interrupt mask bits are not modelled.  This emulator starts with
        Status 0; only EI, DI and MTC0 change it.  The kernel that would set a
        thread's Status is not modelled.
        """
        status = self.cop0[12] & M32
        need = self.STATUS_IE | self.STATUS_EIE
        return (status & need) == need and not status & (self.STATUS_EXL | self.STATUS_ERL)

    def install_modelled_intc(self, while_disabled=False):
        """Opt in to one modelled INTC delivery when WaitSema would block.

        Status gate (round 8, audit R7-2): a delivery runs only when
        interrupts_enabled() is true.  Otherwise the WaitSema raises CpuTrap
        and names Status.  while_disabled=True delivers anyway.  That is a
        modelled exception the CPU state does not allow: Status at each
        delivery is recorded in intc_delivery_status so a test can assert it.
        The boots in rounds 6 to 8 reach every delivery with Status 0, so they
        need while_disabled=True, and everything after a delivery depends on
        that model.  The handler's own EI (0x19b778, 0x19b920) is discarded
        by the register restore below.

        Observed registration, from engine_init 0x19d19c: AddIntcHandler
        0x3526c0 is syscall 0x10.  The call at 0x19d37c passes cause 2 in a0,
        handler 0x19b6e4 in a1 and 0 in a2.  EnableIntc 0x352720 is syscall
        0x14, reached through 0x353528 with that cause in a0; its return
        address is 0x353560.  The handler saves ra, returns through jr ra, and
        sets v0 to 0.  It does not read a0 before overwriting it.  Both of its
        exits jal iSignalSema 0x352a10.  That wrapper loads v1 = -0x43 and
        executes SYSCALL.  One delay slot loads the id at 0x8400f4; the other
        signal uses the id previously loaded from 0x8400f0.  The same exits
        increment the word at 0x44fd98.

        Inferred: a0 on entry is the registered cause, because that is the
        first AddIntcHandler argument and the handler is an ordinary function.
        This model passes that cause in a0.  When the handler returns, the
        interrupted general registers, COP0 and pc are restored, because the
        waiter at 0x19d05c continues with the registers it held.  The BIOS
        save mask is not in this image.  Restoring the whole register file is
        the model.  iSignalSema applies the same count increment as the
        modelled SignalSema (syscall 66).  That increment does not consult
        the max word, and it is not a recovered kernel result.

        Delivery runs only for an enabled handler whose body signals the
        waited id through 0x352a00 or 0x352a10, where the id is the current
        word at an address the jal's a0 load forms with lui plus lw.  One
        delivery per blocking WaitSema, in registration order.  That cadence
        is modelled.  It is not a vertical-blank interval.  A handler that
        does not return is left in place and the original exception
        propagates.  Composes with install_modelled_boot; WaitSema itself
        still requires that opt-in.  Without this method, a zero count still
        raises CpuTrap.
        """
        if self._modelled_intc:
            raise EmuError('modelled interrupt delivery is already installed')
        self._modelled_intc = True
        self._intc_while_disabled = bool(while_disabled)
        self.intc_delivery_status = []

    def install_ram_mirrors(self):
        """Opt in to the uncached and uncached-accelerated mirrors of main RAM.

        Observed at engine_init 0x19d3a8: register s4 is formed with lui of
        0x2000.  At 0x19d4ac the word loaded from 0x01800010 is ORed with that
        value, and 0x19d4b4 stores a halfword at offset 0x14 of the result.
        That word is 0x01800080, which is inside the 32 MB main-RAM window.
        The same OR and halfword store repeat at 0x19d514 and 0x19d520, and
        SYNC follows each store.  0x01800000 itself is formed with lui of
        0x180 and passed to tex_relocate 0x179e10.  It is a main-RAM address,
        not a register block at 0x10000000 or 0x12000000.

        Observed at 0x16bed0: a pointer built from 0x006f4140 is ORed with
        0x30000000 and kept.  Observed at 0x19d978-0x19d990: bit 0 of a word
        is multiplied by 0x445c0 (three-operand mult at 0x19d97c, constant
        formed at 0x19d928/0x19d934), added to 0x0044fe80, and the result,
        0x0044fe80 or 0x00494440, is ORed with 0x30000000 and stored.  Both
        bases are inside main RAM.  Inferred: those are the
        uncached-accelerated addresses of the same bytes, the form the DMA
        and GIF packets carry.

        An address in 0x20000000 or 0x30000000 whose low 28 bits are below
        0x02000000 uses the cached page.  A cached page that is not mapped
        still faults, and the fault names the address the instruction used.
        Hardware windows formed with lui of 0x1000 or 0x1200 are not aliased.
        This is not a cache and not a DMA completion model.
        """
        if self._ram_mirrors:
            raise EmuError('main-RAM mirrors are already installed')
        self._ram_mirrors = True

    def install_modelled_main_ram(self):
        """Opt in to the main-RAM heap the ELF did not load.

        Observed: SetupHeap at 0x14fc64 is passed start 0x0090a434 and size -1,
        and SetupThread at 0x14fc48 is passed stack base 0x01fc0000.  On the
        32 MB path engine_init 0x19d58c-0x19d5c8 asks mem_malloc for 0x16a5bcc
        bytes, and mem_initHeap 0x150598 fills the block it gets with 0xa5, one
        byte per iteration, at 0x1505c8.  A missing page from 0x0090a434 up to
        0x01fc0000 is created zeroed on access.  That zero is the absence of a
        store, not a measurement of retail RAM.  An access below 0x0090a434 or
        at or above 0x01fc0000 is unchanged, so a null-based access still
        faults.
        """
        if self._main_ram:
            raise EmuError('modelled main RAM is already installed')
        self._main_ram = True

    def install_modelled_dma_idle(self):
        """Opt in to the DMA words the GIF kick and the idle wait actually use.

        Observed: 0x350680, called from engine_init at 0x19d4c0 and 0x19d52c,
        waits through 0x350190 and then writes the channel at offsets 0x10,
        0x20 and 0x00.  0x350190 reads the word at offset 0 and proceeds when
        bit 0x100 is clear; otherwise it spins.  The caller's a0 is 0x1000a000.
        sceGsSyncPath 0x34fe78, called with a0 = 0 at 0x19d4cc, reads the same
        bit at 0x10009000 and 0x1000a000, the word at 0x10003c00 masked with
        0x1f000003, and the word at 0x10003020 masked with 0xc00.  Each wait
        ends when the tested bits are clear.

        The words at offsets 0x00, 0x10 and 0x20 of the two channels these
        callers name, 0x10009000 and 0x1000a000, are storage that starts at
        0.  Other channels are not modelled and still fault.  A 4-byte
        read of offset 0 returns that word with bit 0x100 clear.  That clear
        bit is modelled: it is the condition the spinners test, not a
        completed GIF transfer.  The two status words above are the same kind
        of storage and are not masked.  Any other address in the register
        window still faults.  Neighbours of an accepted word are not storage.
        """
        if self._dma_idle:
            raise EmuError('modelled DMA idle is already installed')
        self._dma_idle = True

    def install_modelled_vpu_stat(self):
        """Opt in to CFC2 of control register 29 returning 0.

        Observed in sceGsSyncPath at 0x34ff5c and 0x34ff7c: CFC2 into a GPR
        from register 29, then a test of bit 0x100.  The wait ends when that
        bit is clear.  This model writes 0.  That 0 is not a recovered VU
        status.  Every other COP2 encoding still stops as an unimplemented
        instruction.  Composes with the other opt-ins; without it, COP2 stops
        the same way as before.
        """
        if self._vpu_stat:
            raise EmuError('modelled VPU status is already installed')
        self._vpu_stat = True

    # The IOP buffer address returned by GetReg(2).  Unmapped, and outside the
    # main-RAM mirrors, so any EE load or store through it faults.
    SIF_SUBADDR_PLACEHOLDER = 0x0BAD0000

    # GetReg (syscall 0x7a) return addresses whose callers were read.
    _SIF_GETREG_RA = {
        0x3557b4: 0x80000000,   # sceSifInitCmd: v0 nonzero takes the re-init path
        0x355808: 4,            # sceSifInitCmd poll: v0 & 0x20000
        0x35581c: 2,            # sceSifInitCmd: stored at 0x8ef120, passed to SetReg
        0x355e90: 0x80000002,   # sceSifInitRpc: v0 nonzero returns at once
    }
    # SetReg (syscall 0x79) return addresses whose callers do not read v0.
    _SIF_SETREG_RA = {
        0x35582c: 0x80000000,
        0x35583c: 0x80000001,
        0x19bab0: 0x80000002,   # tail call from sceSifInitRpc 0x355ee8, caller iop_loadModules
    }

    def install_modelled_sif(self, while_disabled=False):
        """Opt in to the EE half of the SIF command handshake.  There is no IOP.

        Observed callers, in the order the boot reaches them from
        iop_loadModules 0x19ba98 -> sceSifInitRpc 0x355d68 (jal at 0x19baa8)
        -> sceSifInitCmd 0x355608 (jal at 0x355db0):

        * 0x35574c reads D_STAT 0x1000e010 and, when bit 0x20 is set, writes
          0x20 back at 0x355760.  0x35576c reads D5_CHCR 0x1000c000 and calls
          SetDChain 0x352dc0 (syscall 0x78) when bit 0x100 is clear.  Both
          words are storage that starts at 0 here: no pending channel-5
          status and channel 5 not running.  That 0 is modelled.
        * SetDChain at ra 0x355784 and iSetDChain (syscall -0x78) at ra
          0x355bec: neither caller reads v0.  v0 = 0.
        * AddDmacHandler (syscall 0x12) at ra 0x355798 with channel 5 and
          handler 0x355b70.  v0, stored at 0x8ef114, is a modelled id.
        * EnableDmac (syscall 0x16) at ra 0x353630, inside wrapper 0x3535f8
          called from 0x3557a0 (saved ra 0x3557a8, which does not read v0).
          v0 = 0.
        * GetReg (syscall 0x7a), accepted only at the four return addresses
          in _SIF_GETREG_RA.  Software registers 0x80000000 and 0x80000002
          return the last SetReg value, 0 before any.  Register 4 is the
          main-flag word: the loop at 0x355800-0x35580c repeats until bit
          0x20000 is set.  The model returns 0x20000, the one bit that loop
          tests.  That bit stands for the IOP side; it is not a recovered
          flag value.  Register 2 is the IOP's command buffer address.  The
          EE stores it at 0x8ef120, passes it to SetReg 0x80000000 and uses
          it as the destination word of every SetDma descriptor that
          _SifSendCmd 0x3559b8 builds (0x355a5c).  The model returns
          SIF_SUBADDR_PLACEHOLDER, an unmapped address, so an EE access
          through it would fault.  It is not an IOP address.
        * SetReg (syscall 0x79), accepted only at the return addresses in
          _SIF_SETREG_RA.  None of those callers reads v0.  v0 = 0.  The
          value is kept for GetReg and recorded in sif_reg_writes.
        * SetDma (syscall 0x77) at ra 0x355acc, the single call in
          _SifSendCmd.  a0 holds a1 descriptors of 16 bytes: source, IOP
          destination, size, attribute.  Each is recorded in sif_transfers
          with the source bytes.  Nothing is transferred.  v0 is a nonzero
          modelled id: sceSifBindRpc 0x356510 tests it at 0x3565cc and treats
          0 as a failed send.
        * After sceSifInitRpc sends command 0x80000002 with word +0xc = 1
          (0x355e98-0x355eb4), it polls sceSifGetSreg(0) 0x3555c0 at
          0x355ec0-0x355ec8 until the word at 0x8ef2c0 is nonzero.  Only
          the IOP's set-register command writes it, through the game's own
          handler: DMAC channel-5 handler 0x355b70 reads the packet pointer
          at 0x8ef118, takes the size byte at +0, copies the packet, clears
          the byte, and for a command word at +8 with bit 31 set calls system
          handler (word & 0x7fffffff); entry 1 is 0x355590, which stores
          word +0x14 at sregs[word +0x10].  The model writes one packet into
          that buffer when that send is recorded: size 0x18, command
          0x80000001, index 0, value 1, and runs the registered, enabled
          channel-5 handler once, as a nested call whose registers are then
          restored.  The packet, its value 1 and its timing are modelled;
          the layout is the one 0x355b70 and 0x355590 read.  Recorded in
          sif_deliveries.

        Status gate (as install_modelled_intc, audit R7-2): the packet is
        delivered only when interrupts_enabled() is true; otherwise the send
        raises CpuTrap naming Status.  while_disabled=True delivers anyway,
        a disclosed modelled exception.  The COP0 Status at the delivery is
        the last field of each sif_deliveries entry.  In the round-8 boot it
        is 0x10000: the game's EI at 0x355e7c set EIE, and IE was never set.

        Not modelled: the IOP, the bind and call replies (command 0x80000008,
        handled by 0x356068), any RPC result data, the reset and boot-end
        bits, and any other SIF caller.  Those still raise CpuTrap.
        Requires install_modelled_boot and install_ram_mirrors.
        """
        if self._sif:
            raise EmuError('modelled SIF handshake is already installed')
        if not self._modelled_boot or not self._ram_mirrors:
            raise EmuError('install_modelled_sif needs install_modelled_boot and install_ram_mirrors')
        self._sif = True
        self._sif_while_disabled = bool(while_disabled)
        self._sif_regs = {}
        self._dmac = []
        self.sif_transfers = []
        self.sif_deliveries = []
        self.sif_reg_writes = []
        self._next_dma_id = 1

    def _modelled_sif_syscall(self, number):
        """Handle one opted-in SIF syscall.  Return False if this caller is not in the model."""
        ra = self.r[31] & M32
        a0 = self.r[4] & M32
        a1 = self.r[5] & M32
        if number == 0x78:
            if ra != 0x355784:
                return False
            self._set_v0(0)
            return True
        if number == -0x78:
            if ra != 0x355bec or not self._in_intc:
                return False
            self._set_v0(0)
            return True
        if number == 0x12:
            if ra != 0x355798 or a0 != 5:
                return False
            handler_id = self._next_handler
            self._next_handler = handler_id + 1
            self._dmac.append({'id': handler_id, 'cause': a0, 'fn': a1,
                               'next': self.r[6] & M32, 'enabled': False})
            self._set_v0(handler_id)
            return True
        if number == 0x16:
            sp = self.r[29] & M32
            if ra != 0x353630 or a0 != 5 or self.mem.u32(sp + 0x20) != 0x3557a8:
                return False
            for handler in self._dmac:
                if handler['cause'] == a0:
                    handler['enabled'] = True
            self._set_v0(0)
            return True
        if number == 0x7a:
            reg = self._SIF_GETREG_RA.get(ra)
            if reg is None or reg != a0:
                return False
            if reg == 4:
                self._set_v0(0x20000)
            elif reg == 2:
                self._set_v0(self.SIF_SUBADDR_PLACEHOLDER)
            else:
                self._set_v0(self._sif_regs.get(reg, 0))
            return True
        if number == 0x79:
            reg = self._SIF_SETREG_RA.get(ra)
            if reg is None or reg != a0:
                return False
            self._sif_regs[reg] = a1
            self.sif_reg_writes.append((ra, reg, a1))
            self._set_v0(0)
            return True
        if number == 0x77:
            if ra != 0x355acc or not 1 <= a1 <= 2:
                return False
            reply = False
            for index in range(a1):
                src, dest, size, attr = (self.mem.u32(a0 + index * 16 + k) for k in (0, 4, 8, 12))
                phys = self._mirror_phys(src)
                data = self.mem.read(src if phys is None else phys, size)
                self.sif_transfers.append((ra, src, dest, size, attr, data))
                if (size >= 0x10 and struct.unpack_from('<I', data, 8)[0] == 0x80000002
                        and struct.unpack_from('<I', data, 12)[0] == 1):
                    reply = True
            dma_id = self._next_dma_id
            self._next_dma_id = dma_id + 1
            self._set_v0(dma_id)
            if reply:
                self._deliver_modelled_set_sreg(0, 1)
            return True
        return False

    def _deliver_modelled_set_sreg(self, index, value):
        handler = next((h for h in self._dmac if h['cause'] == 5 and h['enabled']), None)
        if handler is None:
            raise CpuTrap('modelled SIF reply has no enabled channel-5 DMAC handler')
        buf = self.mem.u32(0x8ef118)
        phys = self._mirror_phys(buf)
        target = buf if phys is None else phys
        status = self.cop0[12] & M32
        if not self.interrupts_enabled() and not self._sif_while_disabled:
            raise CpuTrap('modelled SIF reply refused at 0x%08x: Status 0x%08x disables the '
                          'channel-5 DMAC handler 0x%08x' % (self.cur, status, handler['fn']))
        packet = struct.pack('<IIIIII', 0x18, 0, 0x80000001, 0, index, value)
        self.mem.write(target, packet)
        self.sif_deliveries.append((5, handler['fn'], 0x80000001, index, value, status))
        self._run_intc_handler(handler)


    # FlushCache callers whose following instructions do not read v0.
    _FLUSH_IGNORED_RA = frozenset((0x19d628, 0x355744))

    # Return addresses of jal TerminateThread whose following instructions do not read v0.
    _TERMINATE_IGNORED_RA = frozenset((
        0x17de0c, 0x17e480, 0x17fe68, 0x31ef38,
        0x36782c, 0x368e2c, 0x3a02cc, 0x3a1270,
    ))

    def _dispatch_opt_in_syscall(self):
        number = s64(self.r[3])
        if number == 124 and self._deci2_kputs:
            self.deci2_kputs()
            return
        if number == 37 and self._terminate_thread:
            self.terminate_thread()
            return
        if self._sif and self._modelled_sif_syscall(number):
            return
        if number == 100 and self._flush_cache and (self.r[31] & M32) in self._FLUSH_IGNORED_RA:
            self._set_v0(0)
            return
        if number == 62 and self._end_of_heap and (self.r[31] & M32) == 0x353138:
            self._set_v0(0x01FC0000)
            return
        if self._modelled_boot and self._modelled_boot_syscall(number):
            return
        raise CpuTrap('SYSCALL at 0x%08x (v1 = %d); no kernel is modelled'
                      % (self.cur, number))

    def _set_v0(self, value):
        value &= M32
        self.r[2] = value | HIGH32 if value & SIGN32 else value

    def _modelled_boot_syscall(self, number):
        """Handle one opted-in boot syscall.  Return False if this number is not in the model."""
        ra = self.r[31] & M32
        a0 = self.r[4] & M32
        a1 = self.r[5] & M32
        a2 = self.r[6] & M32
        if number == 60:
            if self.cur != 0x14fc48:
                return False
            self._set_v0((a1 + a2 - 0x10) & M32)
            return True
        if number == 61:
            if self.cur != 0x14fc64:
                return False
            self._set_v0(0)
            return True
        if number == 2:
            if ra != 0x19d36c:
                return False
            self._set_v0(0)
            return True
        if number == 113:
            if ra != 0x34f79c:
                return False
            self._set_v0(0)
            return True
        if number == 20:
            if ra != 0x353560:
                return False
            for handler in self._intc:
                if handler['cause'] == a0:
                    handler['enabled'] = True
            self._set_v0(1)
            return True
        if number == 16:
            handler_id = self._next_handler
            self._next_handler = handler_id + 1
            self._intc.append({'id': handler_id, 'cause': a0, 'fn': a1,
                               'next': a2, 'enabled': False})
            self._set_v0(handler_id)
            return True
        if number == 116:
            if ra not in (0x35c1d0, 0x35c1dc):
                return False
            self._installed_syscalls[a0] = a1
            self._set_v0(0)
            return True
        if number == 32:
            entry = self.mem.u32(a0 + 4)
            stack = self.mem.u32(a0 + 8)
            size = self.mem.u32(a0 + 12)
            gp = self.mem.u32(a0 + 16)
            priority = self.mem.u32(a0 + 20)
            tid = self._next_tid
            self._next_tid = tid + 1
            self._threads[tid] = {'priority': priority, 'status': 0x10, 'entry': entry,
                                  'stack': stack, 'size': size, 'gp': gp, 'started': False}
            self._set_v0(tid)
            return True
        if number == 47:
            self._set_v0(self._current_tid)
            return True
        if number == 41:
            tid = a0 or self._current_tid
            thread = self._threads.get(tid)
            if thread is None:
                raise CpuTrap('SYSCALL at 0x%08x (v1 = 41, a0 = %d); '
                              'modelled thread was not created' % (self.cur, tid))
            self._set_v0(thread['priority'])
            thread['priority'] = a1
            return True
        if number == 48:
            tid = a0 or self._current_tid
            thread = self._threads.get(tid)
            if thread is None:
                self._set_v0(0xffffffff)
                return True
            if a1:
                self.mem.w32(a1, thread['status'])
                self.mem.w32(a1 + 4, thread['entry'])
                self.mem.w32(a1 + 8, thread['stack'])
                self.mem.w32(a1 + 12, thread['size'])
                self.mem.w32(a1 + 16, thread['gp'])
                self.mem.w32(a1 + 20, thread['priority'])
                self.mem.w32(a1 + 24, thread['priority'])
            self._set_v0(thread['status'])
            return True
        if number == 34:
            thread = self._threads.get(a0)
            if thread is None:
                raise CpuTrap('SYSCALL at 0x%08x (v1 = 34, a0 = %d); '
                              'modelled thread was not created' % (self.cur, a0))
            thread['started'] = True
            self._set_v0(a0)
            return True
        if number == 64:
            sid = self._next_sid
            self._next_sid = sid + 1
            self._semas[sid] = {'count': self.mem.u32(a0 + 8), 'max': self.mem.u32(a0 + 4)}
            self._set_v0(sid)
            return True
        if number in (65, 66, 68, 69) or number == -0x43:
            if number == -0x43 and not self._modelled_intc:
                return False
            sema = self._semas.get(a0)
            if sema is None:
                raise CpuTrap('SYSCALL at 0x%08x (v1 = %d, a0 = %d); '
                              'modelled semaphore was not created' % (self.cur, number, a0))
            if number == 65:
                del self._semas[a0]
                self._set_v0(a0)
                return True
            if number == 66 or number == -0x43:
                sema['count'] = (sema['count'] + 1) & M32
                self._set_v0(a0)
                return True
            if sema['count'] == 0:
                if number == 69:
                    self._set_v0(0xffffffff)
                    return True
                if (number == 68 and self._modelled_intc and not self._in_intc
                        and self._deliver_intc_for_sema(a0) and sema['count'] != 0):
                    pass
                else:
                    raise CpuTrap('SYSCALL at 0x%08x (v1 = 68, a0 = %d); '
                                  'modelled WaitSema count is 0' % (self.cur, a0))
            sema['count'] -= 1
            self._set_v0(a0)
            return True
        installed = self._installed_syscalls.get(number if number >= 0 else number & M32)
        if installed is None and number < 0:
            installed = self._installed_syscalls.get(number & M32)
        if installed:
            nxt = self.mem.u32(self.pc)
            delay = self.mem.u32((self.pc + 4) & M32)
            if nxt != 0x03e00008 or delay != 0:
                raise CpuTrap('SYSCALL at 0x%08x (v1 = %d); installed handler 0x%08x '
                              'but the wrapper is not jr ra / nop' % (self.cur, number, installed))
            self.jump(installed)
            return True
        return False

    def _gpr_written(self, word, reg):
        """True when this instruction writes reg.  Used only to resolve a signal id."""
        if reg == 0:
            return False
        op = word >> 26
        rt = (word >> 16) & 31
        rd = (word >> 11) & 31
        if op == 0:
            funct = word & 63
            # jr, syscall, break, sync, mthi, mtlo, and the hi/lo arithmetic.
            if funct in (8, 12, 13, 15, 17, 19, 24, 25, 26, 27):
                return False
            return rd == reg
        if op in (8, 9, 10, 11, 12, 13, 14, 15,
                  0x1A, 0x1B, 0x1E, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25,
                  0x26, 0x27, 0x37):
            return rt == reg
        if op == 3 or (op == 1 and ((word >> 16) & 31) in (0x10, 0x11, 0x12, 0x13)):
            return reg == 31
        if op == 0x10 and ((word >> 21) & 31) == 0:
            return rt == reg
        if op == 0x11 and ((word >> 21) & 31) == 0:
            return rt == reg
        return False

    def _lui_base(self, pc, reg, start):
        addr = (pc - 4) & M32
        while addr >= start:
            word = self.mem.u32(addr)
            if (word >> 26) == 0x0F and ((word >> 16) & 31) == reg:
                return (word & 0xFFFF) << 16
            if self._gpr_written(word, reg):
                return None
            if addr < 4:
                break
            addr -= 4
        return None

    def _lw_a0_address(self, lw_pc, start):
        word = self.mem.u32(lw_pc)
        if (word >> 26) != 0x23 or ((word >> 16) & 31) != 4:
            return None
        base = (word >> 21) & 31
        off = word & 0xFFFF
        if off & 0x8000:
            off -= 0x10000
        hi = self._lui_base(lw_pc, base, start)
        if hi is None:
            return None
        return (hi + off) & M32

    def _handler_signal_words(self, fn):
        """Addresses whose word is passed to SignalSema or iSignalSema.

        Linear scan from the handler until jr ra.  A jal to 0x352a00 or
        0x352a10 qualifies when its delay slot is lw $4, or the delay slot is
        nop and the nearest earlier write of $4 is such an lw.  The address
        must be formed by an earlier lui of the base.  Anything else is not
        treated as a signal of a known id.
        """
        found = []
        pc = fn & M32
        start = pc
        for _ in range(512):
            if not self.mem.is_mapped(pc, 8):
                break
            word = self.mem.u32(pc)
            if word == 0x03E00008:
                break
            if (word >> 26) == 3:
                target = ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
                if target in (0x352a00, 0x352a10):
                    delay = self.mem.u32((pc + 4) & M32)
                    addr = None
                    if (delay >> 26) == 0x23 and ((delay >> 16) & 31) == 4:
                        addr = self._lw_a0_address((pc + 4) & M32, start)
                    elif delay == 0:
                        scan = (pc - 4) & M32
                        while scan >= start:
                            earlier = self.mem.u32(scan)
                            if self._gpr_written(earlier, 4):
                                addr = self._lw_a0_address(scan, start)
                                break
                            if scan < 4:
                                break
                            scan -= 4
                    if addr is not None:
                        found.append(addr)
            pc = (pc + 4) & M32
        return found

    def _deliver_intc_for_sema(self, sid):
        """Run enabled handlers that signal sid.  Return True if one ran."""
        ran = False
        for handler in list(self._intc):
            if not handler['enabled'] or not handler['fn']:
                continue
            words = self._handler_signal_words(handler['fn'])
            if not any(self.mem.u32(addr) == sid for addr in words):
                continue
            status = self.cop0[12] & M32
            if not self.interrupts_enabled() and not self._intc_while_disabled:
                raise CpuTrap('SYSCALL at 0x%08x (v1 = 68, a0 = %d); modelled WaitSema count is 0 '
                              'and Status 0x%08x disables the INTC handler 0x%08x'
                              % (self.cur, sid, status, handler['fn']))
            self.intc_deliveries.append((handler['cause'], handler['fn'], sid))
            self.intc_delivery_status.append(status)
            self._run_intc_handler(handler)
            ran = True
        return ran

    def _run_intc_handler(self, handler):
        saved_r = self.r[:]
        saved_rh = self.rh[:]
        saved_f = self.f[:]
        saved_cop0 = self.cop0[:]
        saved = (self.pc, self.npc, self.cur, self.hi, self.lo, self.hi1, self.lo1,
                 self.sa, self.acc, self.fcr31, self._pending_call, self._fresh_call,
                 self._call_site)
        self._in_intc = True
        completed = False
        try:
            cause = handler['cause'] & M32
            self.r[4] = cause | HIGH32 if cause & SIGN32 else cause
            self.r[31] = self.RETURN_ADDR
            self.jump(handler['fn'])
            reason = self.run(max_steps=2000000)
            completed = reason == 'return'
            if not completed:
                raise CpuTrap('modelled INTC handler 0x%08x did not return (%s) at 0x%08x'
                              % (handler['fn'], reason, self.pc))
        finally:
            self._in_intc = False
            if completed:
                self.r[:] = saved_r
                self.rh[:] = saved_rh
                self.f[:] = saved_f
                self.cop0[:] = saved_cop0
                (self.pc, self.npc, self.cur, self.hi, self.lo, self.hi1, self.lo1,
                 self.sa, self.acc, self.fcr31, self._pending_call, self._fresh_call,
                 self._call_site) = saved

    def terminate_thread(self):
        ra = self.r[31] & M32
        if ra not in self._TERMINATE_IGNORED_RA:
            raise CpuTrap('SYSCALL at 0x%08x (v1 = 37, ra = 0x%08x); '
                          'caller reads v0 or is outside the observed TerminateThread contract'
                          % (self.cur, ra))
        self.r[2] = 0

    def deci2_kputs(self):
        number = s64(self.r[3])
        if number != 124:
            raise CpuTrap('SYSCALL at 0x%08x (v1 = %d); no kernel is modelled'
                          % (self.cur, number))
        function = s32(self.r[4])
        if function != 0x10:
            raise CpuTrap('SYSCALL at 0x%08x (v1 = 124, a0 = %d); '
                          'Deci2 function is outside the observed function-0x10 contract'
                          % (self.cur, function))
        self.r[2] = 0

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
    def _ensure_main_ram(self, addr, size):
        if not self._main_ram or addr < 0x0090A434 or addr + size > 0x01FC0000:
            return
        if not self.mem.is_mapped(addr, size):
            self.mem.map(addr, size)

    def _mirror_phys(self, addr):
        """Cached main-RAM address for an uncached mirror, or None."""
        if not self._ram_mirrors:
            return None
        top = addr >> 28
        if top != 2 and top != 3:
            return None
        phys = addr & 0x0FFFFFFF
        if phys >= 0x02000000:
            return None
        return phys

    def _dma_reg_off(self, addr):
        if addr & ~0xFFF not in (0x10009000, 0x1000A000):
            return None
        off = addr & 0xFFF
        if off in (0x00, 0x10, 0x20):
            return off
        return None

    def _hw_key(self, addr, size):
        """Modelled 4-byte hardware word, or None so the access uses memory."""
        if self._sif and size == 4 and addr in (0x1000e010, 0x1000c000):
            return addr
        if not self._dma_idle or size != 4 or addr & 3:
            return None
        if self._dma_reg_off(addr) is not None or addr in (0x10003c00, 0x10003020):
            return addr
        return None

    def _overlaps_watch(self, addr, size):
        end = addr + size
        for watch, width in self.write_watch:
            if addr < watch + width and watch < end:
                return True
        return False

    def _load(self, addr, size):
        if addr & (size - 1):
            raise CpuTrap('unaligned %d-byte load from 0x%08x at pc 0x%08x' % (size, addr, self.cur))
        phys = self._mirror_phys(addr)
        if phys is not None:
            self._ensure_main_ram(phys, size)
            if not self.mem.is_mapped(phys, size):
                raise MemoryFault(self.cur, addr, size, 'read')
            value = self.mem.load(phys, size)
        elif self._gs_access(addr, size, False):
            value = 0
            self.gs_reads.append((self.cur, addr, value))
        else:
            key = self._hw_key(addr, size)
            if key is not None:
                value = self._hw_words.get(key, 0)
                if self._dma_reg_off(addr) == 0:
                    value &= ~0x100
            else:
                self._ensure_main_ram(addr, size)
                value = self.mem.load(addr, size)
        if self.reads is not None:
            self.reads.append((self.cur, addr, size, value))
        return value

    def _store(self, addr, size, value):
        if addr & (size - 1):
            raise CpuTrap('unaligned %d-byte store to 0x%08x at pc 0x%08x' % (size, addr, self.cur))
        kept = value & ((1 << (size * 8)) - 1)
        phys = self._mirror_phys(addr)
        if phys is not None:
            self._ensure_main_ram(phys, size)
            if not self.mem.is_mapped(phys, size):
                raise MemoryFault(self.cur, addr, size, 'write')
            self.mem.store(phys, size, kept)
        elif self._gs_access(addr, size, True):
            self.gs_writes.append((self.cur, addr, kept))
        else:
            key = self._hw_key(addr, size)
            if key is not None:
                self._hw_words[key] = kept & M32
            else:
                self._ensure_main_ram(addr, size)
                self.mem.store(addr, size, kept)
        if self.record_writes and not self.stack_lo <= addr < self.stack_hi:
            if self.write_watch is None or self._overlaps_watch(addr, size) or (
                    phys is not None and self._overlaps_watch(phys, size)):
                self.writes.append((self.cur, addr, size, kept))

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
        ops[0x12] = self._cop2
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

    def _cop2(self, w):
        if not self._vpu_stat:
            self._unimplemented(w)
        rs = (w >> 21) & 31
        rd = (w >> 11) & 31
        if rs == 0x02 and rd == 29:     # CFC2 VPU_STAT.  The 0 is modelled.
            value = 0
            self.r[(w >> 16) & 31] = value
            return
        self._unimplemented(w, 'COP2')

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
