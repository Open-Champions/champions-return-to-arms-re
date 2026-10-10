#!/usr/bin/env python3
"""ref_amx.py - reference model of the level-script machine (script.scr).

Every level's logic is a compiled program for the Small "abstract machine" (AMX).  This
module is a readable re-implementation of the copy of that machine inside SLUS_209.73, for
people who have to write an interpreter that behaves like the original.  It contains no game
code and no game data; you give it your own script.scr image.

    from ref_amx import Machine
    m = Machine(open('script.scr', 'rb').read())
    assert m.load() == 0                               # scr_load
    m.register({'getv': lambda m, args: 0, ...})       # scr_registerNatives, 19 if a name is missing
    error, index = m.find_public('start')              # scr_findEntry
    error, result = m.execute(index)                   # scr_interpret
    result = m.call('start')                           # what the game does (script_runByName)

A native is a Python callable  f(machine, args) -> cell.  args is the list of argument cells
(signed 32-bit integers) in source order; machine.params is the address of the cell in front of
them, which holds their size in bytes.  A string argument is an address:
machine.get_string(address) reads it, in either of the machine's two string formats.  A native
may run another entry point on the same machine (machine.execute / machine.call) and may stop
the caller with machine.raise_error(code).

What each part mirrors (addresses in SLUS_209.73, US v2.00):

    Machine.load          scr_load 0x13e8f8, with the compact-code expansion at 0x13e96c-0x13ea08
    Machine._relocate     scr_relocate 0x13e6d0 and its jump table 0x530fd0
    Machine.find_public   scr_findEntry 0x13eac8
    Machine.register      scr_registerNatives 0x141310
    Machine.execute       scr_interpret 0x13ecf8-0x140f10; one handler per opcode, table 0x403150
    Machine._call_native  scr_callNative 0x141050
    Machine.call          script_runByName 0x1ed694
    get_addr, get_string, set_string, str_len, allot, release, raise_error
                          0x1414a8, 0x141650, 0x140f10, 0x141568, 0x1414f8, 0x141550, 0x141498
    MOVS and CMPS         libc_memcpy 0x3b5f0c and libc_memcmp 0x3b5e78 as the handlers use them

Where the model stops.  The original checks very little: a script can read and write any
address, jump anywhere and call a native that was never bound.  Whenever the original would
touch memory outside the script's own block (the bytes from the start of its data to the end of
the image), use a word as a machine address that the loader did not prepare, or take a CPU
exception (an unaligned word access), the result depends on the rest of the console's memory.
The model does not guess: it raises HostFault and says what the original would have done.
Limit is raised when the optional instruction budget (Machine.budget) runs out; the original
has no budget, and a script that loops forever hangs the game.

tools/difftest_amx.py runs the original machine code and this model side by side;
docs/spec/script-machine.md is the written specification and says what that test covers.

Command line:

    python3 tools/ref_amx.py info <script.scr>            header, entry points, natives
    python3 tools/ref_amx.py run <script.scr> <entry>     run one entry point, every native
                                                          prints its arguments and returns 0
"""
import struct
import sys

M32 = 0xFFFFFFFF
STRUCT_SIZE = 0x60          # machine structure in front of the header, zero on disc
HEADER_SIZE = 0x40
RECORD_SIZE = 24            # name-table record: one cell and a 20-byte name
MAGIC = 0xF1E0
STKMARGIN = 0x40            # bytes that must stay free between heap and stack

FLAG_LOADED = 0x2000        # machine structure +0x20: scr_load has run
FLAG_BROWSE = 0x4000        # cleared at the start of every run
FLAG_RELOC = 0x8000         # code relocated; required to run

# error numbers (the AMX ones)
ERR_NONE, ERR_STACKERR, ERR_BOUNDS, ERR_MEMACCESS, ERR_INVINSTR = 0, 3, 4, 5, 6
ERR_STACKLOW, ERR_HEAPLOW, ERR_CALLBACK, ERR_DIVIDE = 7, 8, 9, 11
ERR_MEMORY, ERR_FORMAT, ERR_VERSION, ERR_NOTFOUND, ERR_INDEX = 16, 17, 18, 19, 20
ERR_DEBUG, ERR_INIT, ERR_USERDATA, ERR_INIT_JIT = 21, 22, 23, 24

EXEC_MAIN = -1              # entry index for the header's start address
NOT_FOUND_INDEX = 0x7FFFFFFF

# operand classes, as the relocator's jump table 0x530fd0 sorts the opcodes
N, V, C = 'none', 'value', 'code'
FILE, LINE, SYMBOL, SRANGE, CASETBL = 'file', 'line', 'symbol', 'srange', 'casetbl'

# opcode number -> (mnemonic, operand class, handler address in scr_interpret)
OPCODES = (
    ('NONE', N, 0x13eea8),
    ('LOAD.pri', V, 0x13eeb8),
    ('LOAD.alt', V, 0x13eef0),
    ('LOAD.S.pri', V, 0x13ef28),
    ('LOAD.S.alt', V, 0x13ef60),
    ('LREF.pri', V, 0x13ef98),
    ('LREF.alt', V, 0x13efd8),
    ('LREF.S.pri', V, 0x13f018),
    ('LREF.S.alt', V, 0x13f058),
    ('LOAD.I', N, 0x13f098),
    ('LODB.I', V, 0x13f0f0),
    ('CONST.pri', V, 0x13f1a0),
    ('CONST.alt', V, 0x13f1d0),
    ('ADDR.pri', V, 0x13f200),
    ('ADDR.alt', V, 0x13f238),
    ('STOR.pri', V, 0x13f270),
    ('STOR.alt', V, 0x13f2a8),
    ('STOR.S.pri', V, 0x13f2e0),
    ('STOR.S.alt', V, 0x13f318),
    ('SREF.pri', V, 0x13f350),
    ('SREF.alt', V, 0x13f390),
    ('SREF.S.pri', V, 0x13f3d0),
    ('SREF.S.alt', V, 0x13f410),
    ('STOR.I', N, 0x13f450),
    ('STRB.I', V, 0x13f4a0),
    ('LIDX', N, 0x13f550),
    ('LIDX.B', V, 0x13f5b0),
    ('IDXADDR', N, 0x13f620),
    ('IDXADDR.B', V, 0x13f650),
    ('ALIGN.pri', V, 0x13f688),
    ('ALIGN.alt', V, 0x13f6e8),
    ('LCTRL', V, 0x13f740),
    ('SCTRL', V, 0x13f7d8),
    ('MOVE.pri', N, 0x13f848),
    ('MOVE.alt', N, 0x13f878),
    ('XCHG', N, 0x13f8a0),
    ('PUSH.pri', N, 0x13f8d8),
    ('PUSH.alt', N, 0x13f908),
    ('PUSH.R', V, 0x13f970),
    ('PUSH.C', V, 0x13f938),
    ('PUSH', V, 0x13f9d0),
    ('PUSH.S', V, 0x13fa10),
    ('POP.pri', N, 0x13fa50),
    ('POP.alt', N, 0x13fa80),
    ('STACK', V, 0x13fab0),
    ('HEAP', V, 0x13fb08),
    ('PROC', N, 0x13fb58),
    ('RET', N, 0x13fb90),
    ('RETN', N, 0x13fbf8),
    ('CALL', C, 0x13fc68),
    ('CALL.pri', N, 0x13fca8),
    ('JUMP', C, 0x13fce0),
    ('JREL', V, 0x13fd10),
    ('JZER', C, 0x13fd40),
    ('JNZ', C, 0x13fd70),
    ('JEQ', C, 0x13fda0),
    ('JNEQ', C, 0x13fdd0),
    ('JLESS', C, 0x13fe00),
    ('JLEQ', C, 0x13fe38),
    ('JGRTR', C, 0x13fe70),
    ('JGEQ', C, 0x13fea8),
    ('JSLESS', C, 0x13fee0),
    ('JSLEQ', C, 0x13ff18),
    ('JSGRTR', C, 0x13ff50),
    ('JSGEQ', C, 0x13ff88),
    ('SHL', N, 0x13ffc0),
    ('SHR', N, 0x13fff0),
    ('SSHR', N, 0x140020),
    ('SHL.C.pri', V, 0x140050),
    ('SHL.C.alt', V, 0x140088),
    ('SHR.C.pri', V, 0x1400c0),
    ('SHR.C.alt', V, 0x1400f8),
    ('SMUL', N, 0x140130),
    ('SDIV', N, 0x140160),
    ('SDIV.alt', N, 0x1401b8),
    ('UMUL', N, 0x140208),
    ('UDIV', N, 0x140238),
    ('UDIV.alt', N, 0x140278),
    ('ADD', N, 0x1402c8),
    ('SUB', N, 0x1402f8),
    ('SUB.alt', N, 0x140328),
    ('AND', N, 0x140358),
    ('OR', N, 0x140388),
    ('XOR', N, 0x1403b8),
    ('NOT', N, 0x1403e8),
    ('NEG', N, 0x140418),
    ('INVERT', N, 0x140448),
    ('ADD.C', V, 0x140478),
    ('SMUL.C', V, 0x1404b0),
    ('ZERO.pri', N, 0x1404e8),
    ('ZERO.alt', N, 0x140518),
    ('ZERO', V, 0x140548),
    ('ZERO.S', V, 0x140580),
    ('SIGN.pri', N, 0x1405b8),
    ('SIGN.alt', N, 0x140600),
    ('EQ', N, 0x140640),
    ('NEQ', N, 0x140670),
    ('LESS', N, 0x1406a0),
    ('LEQ', N, 0x1406d0),
    ('GRTR', N, 0x140700),
    ('GEQ', N, 0x140730),
    ('SLESS', N, 0x140760),
    ('SLEQ', N, 0x140790),
    ('SGRTR', N, 0x1407c0),
    ('SGEQ', N, 0x1407f0),
    ('EQ.C.pri', V, 0x140820),
    ('EQ.C.alt', V, 0x140858),
    ('INC.pri', N, 0x140890),
    ('INC.alt', N, 0x1408c0),
    ('INC', V, 0x1408f0),
    ('INC.S', V, 0x140930),
    ('INC.I', N, 0x140970),
    ('DEC.pri', N, 0x1409a8),
    ('DEC.alt', N, 0x1409d8),
    ('DEC', V, 0x140a08),
    ('DEC.S', V, 0x140a48),
    ('DEC.I', N, 0x140a88),
    ('MOVS', V, 0x140ac0),
    ('CMPS', V, 0x140b08),
    ('FILL', V, 0x140b58),
    ('HALT', V, 0x140bb8),
    ('BOUNDS', V, 0x140be0),
    ('SYSREQ.pri', N, 0x140c28),
    ('SYSREQ.C', V, 0x140c88),
    ('FILE', FILE, 0x140d00),
    ('LINE', LINE, 0x140d38),
    ('SYMBOL', SYMBOL, 0x140d78),
    ('SRANGE', SRANGE, 0x140dc8),
    ('JUMP.pri', N, 0x140e08),
    ('SWITCH', C, 0x140e30),
    ('CASETBL', CASETBL, 0x140eb8),
)
NUM_OPCODES = len(OPCODES)                       # 0x83
OP = {name: number for number, (name, _kind, _handler) in enumerate(OPCODES)}


class HostFault(Exception):
    """The original would leave the script's own memory or its prepared code here (see the
    module text).  What it does next depends on the host, so the model stops."""


class Limit(Exception):
    """The instruction budget (Machine.budget) ran out."""


def s32(value):
    """Low 32 bits of value as a signed cell."""
    value &= M32
    return value - 0x100000000 if value & 0x80000000 else value


def _trunc_div(a, b):
    """Quotient and remainder of the CPU's signed 32-bit divide (b != 0): the quotient is
    rounded toward zero, the remainder has the sign of a, and -2**31 / -1 gives -2**31, 0."""
    if a == -0x80000000 and b == -1:
        return a, 0
    quotient = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        quotient = -quotient
    return quotient, a - quotient * b


def floored_div(dividend, divisor):
    """SDIV / SDIV.alt (0x140160, 0x1401b8): three machine divides with 32-bit wrap-around
    in between.  Returns (quotient, remainder); for ordinary operands that is division
    rounded toward minus infinity with a remainder of the divisor's sign."""
    remainder = s32(_trunc_div(dividend, divisor)[1] + divisor)
    remainder = _trunc_div(remainder, divisor)[1]
    quotient = _trunc_div(s32(dividend - remainder), divisor)[0]
    return quotient, remainder


def expand_compact(image, start, coded_size, expanded_size):
    """In-place expansion of compact code, 0x13e96c-0x13ea08.  The coded bytes are at
    image[start:start+coded_size]; cells are written from start+expanded_size downward.
    Each cell is a run of bytes holding 7 bits each, most significant first; every byte but
    the last of a run has bit 7 set; bit 6 of the first byte is the sign."""
    while coded_size > 0:
        value, shift = 0, 0
        while True:
            coded_size -= 1
            byte = image[start + coded_size]
            value |= ((byte & 0x7F) << (shift & 31)) & M32      # the CPU shifts by shift mod 32
            shift += 7
            if coded_size <= 0 or not image[start + coded_size - 1] & 0x80:
                break
        if byte & 0x40:
            while shift < 32:
                value |= (0xFF << shift) & M32
                shift += 8
        expanded_size -= 4
        if expanded_size < 0 or expanded_size & 3:
            raise HostFault('compact code expands below the start of the code block')
        struct.pack_into('<I', image, start + expanded_size, value)


def encode_compact(cells):
    """The inverse of expand_compact for a list of cells (shortest form of each)."""
    out = bytearray()
    for cell in cells:
        cell = s32(cell)
        groups = 1
        while not -(1 << (7 * groups - 1)) <= cell < (1 << (7 * groups - 1)):
            groups += 1
        for index in range(groups - 1, -1, -1):
            out.append(((cell >> (7 * index)) & 0x7F) | (0x80 if index else 0))
    return bytes(out)


class Machine:
    """One script machine.  image is the whole script.scr file: 0x60 bytes of machine
    structure (zero on disc), the header, the name tables, code, data, and room for the heap
    and the stack.  The machine works on its own copy (self.image).

    Registers of the structure, as the original keeps them between runs:
      cip frm hea stk   written before every native call (and stk by every RETN)
      stp               stack top, data-relative
      flags, curline, curfile, dbgcode, dbgaddr, dbgparam, dbgname, error
    All script addresses are relative to the start of the data block.
    """

    def __init__(self, image, natives=None):
        """natives, when given, is registered by load() (see register)."""
        self.image = bytearray(image)
        if len(self.image) < STRUCT_SIZE + HEADER_SIZE:
            raise ValueError('image is shorter than the machine structure and the header')
        (self.cip, self.frm, self.hea, self.stk, self.stp) = struct.unpack_from('<5i', self.image, 0x0C)
        self.flags, = struct.unpack_from('<I', self.image, 0x20)
        (self.curline, self.curfile, self.dbgcode, self.dbgaddr, self.dbgparam) = struct.unpack_from(
            '<5i', self.image, 0x24)
        self.dbgname = None                 # code offset of the last debug name, or None
        self.error, = struct.unpack_from('<i', self.image, 0x5C)
        # The native dispatcher: f(index, params address) -> (error, result).  None stands for
        # a null pointer; load() installs _call_native then.  A word that is not zero in the
        # file is kept by the original, and is a machine address the model cannot follow.
        self.callback = None
        if struct.unpack_from('<I', self.image, 0x04)[0] != 0:
            self.callback = self._foreign_callback
        self.params = 0                     # address of the argument block of the current native
        self.profile = None                 # set to a dict to count executed opcodes
        self.budget = None                  # set to a number: Limit after that many instructions
        self._decoded = None                # code offset -> (opcode, operand, next offset)
        self._bound = None                  # one callable (or None, or _FOREIGN) per native record
        self._parsed = False
        self._pending_natives = dict(natives or {})

    # ---- header -----------------------------------------------------------------------------
    def _parse_header(self):
        image, h = self.image, STRUCT_SIZE
        self.size, = struct.unpack_from('<i', image, h)
        self.cod, self.dat, self.hea0, self.hdr_stp, self.start = struct.unpack_from('<5i', image, h + 0x0C)
        self.num_publics, = struct.unpack_from('<h', image, h + 0x20)
        self.publics_off, = struct.unpack_from('<i', image, h + 0x24)
        self.num_natives, = struct.unpack_from('<h', image, h + 0x28)
        self.natives_off, = struct.unpack_from('<i', image, h + 0x2C)
        self.num_libraries, = struct.unpack_from('<h', image, h + 0x30)
        self.num_pubvars, = struct.unpack_from('<h', image, h + 0x38)
        self.data_offset = h + self.dat      # offset in self.image of script address 0

    def _header_cell(self, offset):
        """Signed cell at offset bytes from the header (name tables and header fields)."""
        if not self._parsed:
            raise HostFault('the machine was not loaded: its base pointer is null')
        position = STRUCT_SIZE + offset
        if position < 0 or position + 4 > len(self.image):
            raise HostFault('read of header offset %d, outside the image' % offset)
        return struct.unpack_from('<i', self.image, position)[0]

    def _header_name(self, offset):
        """Zero-terminated name at a header offset (the original copies it with strcpy, so a
        name without a terminator runs on into what follows)."""
        if not self._parsed:
            raise HostFault('the machine was not loaded: its base pointer is null')
        position = STRUCT_SIZE + offset
        end = self.image.find(b'\0', position) if 0 <= position < len(self.image) else -1
        if end < 0:
            raise HostFault('name at header offset %d has no terminator inside the image' % offset)
        return bytes(self.image[position:end])

    def public(self, index):
        """(name bytes, code offset) of entry point index."""
        record = self.publics_off + index * RECORD_SIZE
        return self._header_name(record + 4), self._header_cell(record)

    def publics(self):
        return [self.public(index) for index in range(max(self.num_publics, 0))]

    def native_name(self, index):
        return self._header_name(self.natives_off + index * RECORD_SIZE + 4)

    def native_names(self):
        return [self.native_name(index) for index in range(max(self.num_natives, 0))]

    # ---- loading ----------------------------------------------------------------------------
    def load(self):
        """scr_load 0x13e8f8.  Returns 0, 17 (not a script of this format) or 18 (needs a
        newer machine).  A relocation failure is not reported here: the code is then left
        unusable and every execute() returns 22."""
        image, h = self.image, STRUCT_SIZE
        magic, = struct.unpack_from('<H', image, h + 4)
        record_size, = struct.unpack_from('<H', image, h + 0x0A)
        if magic != MAGIC or record_size != RECORD_SIZE:
            return ERR_FORMAT
        if struct.unpack_from('<b', image, h + 7)[0] >= 4:        # required machine version
            return ERR_VERSION
        stp, = struct.unpack_from('<i', image, h + 0x18)
        if not 1 <= stp <= 0x7FFFFFFE:
            return ERR_FORMAT
        flags, = struct.unpack_from('<H', image, h + 8)
        if flags & 1:                                             # 16-bit characters
            return ERR_FORMAT
        self._parse_header()
        if flags & 4:                                             # compact encoding
            if self.flags & FLAG_LOADED:
                raise HostFault('second load of a compact image: the original expands the code again')
            self._check_block(h + self.cod, self.hea0 - self.cod, 'compact code')
            expand_compact(image, h + self.cod, self.size - self.cod, self.hea0 - self.cod)
        if self.flags & FLAG_LOADED:
            return ERR_NONE                                       # second load: nothing else happens
        self.flags |= FLAG_LOADED
        self._parsed = True                                       # the base pointer is set from here on
        self.hdr_stp -= 4                                         # the header field itself is lowered
        struct.pack_into('<i', image, h + 0x18, self.hdr_stp)
        self._check_block(h + self.hdr_stp, 4, 'the sentinel cell at the stack top')
        struct.pack_into('<I', image, h + self.hdr_stp, 0)        # zero cell: string sentinel
        self.hea = self.hea0 - self.dat
        self.stk = self.stp = self.hdr_stp - self.dat
        if self.callback is None:
            self.callback = self._call_native
        self.curline = self.curfile = 0
        self._relocate()                                          # its result is ignored
        if self._pending_natives:
            self.register(self._pending_natives)
        return ERR_NONE

    def _check_block(self, position, size, what):
        if position < 0 or size < 0 or position + size > len(self.image):
            raise HostFault('%s lies outside the image' % what)

    def _relocate(self):
        """scr_relocate 0x13e6d0: one linear pass over the code block.  The original replaces
        every opcode by its handler's address and turns every code-address operand into a
        machine address.  The model keeps the file's values and records which cells are
        instructions: only those can be executed.  Returns 0, or 6 at the first cell that is
        not an opcode (the code is then not marked relocated)."""
        base = STRUCT_SIZE + self.cod
        size = self.dat - self.cod
        image = self.image

        decoded = {}
        seen = {}                 # code offset -> True when the loader changed that cell

        def cell(offset, changed=False):
            if offset < 0 or offset & 3 or offset + 4 > size or base + offset + 4 > len(image):
                raise HostFault('the loader reads code offset 0x%x, outside the code block or '
                                'not on a cell boundary' % offset)
            # A cell the loader already changed holds a machine address.  Reading one as an
            # operand, or changing a cell it has read before, only happens when a debug record
            # or a case table with a negative size sends the pass backwards.
            if seen.get(offset) or (changed and offset in seen):
                raise HostFault('the loader comes back to code offset 0x%x after using it' % offset)
            seen[offset] = changed
            return struct.unpack_from('<i', image, base + offset)[0]

        cip = 0
        while cip < size:
            start = cip
            if seen.get(cip):
                return ERR_INVINSTR   # a changed cell is a machine address: never below 0x100
            opcode = cell(cip, True)
            if opcode >= 0x100 or not 1 <= opcode < NUM_OPCODES:
                return ERR_INVINSTR
            kind = OPCODES[opcode][1]
            cip += 4
            operand = None
            if kind == V or kind == C:
                operand = cell(cip, kind == C)
                cip += 4
            elif kind == FILE:                    # size, file number, name
                size_bytes, self.curfile = cell(cip), cell(cip + 4)
                self.dbgcode, self.dbgname = 1, cip + 8
                cip += 4 + size_bytes
            elif kind == LINE:                    # line, file number
                self.dbgcode = 2
                self.curline, self.curfile = cell(cip), cell(cip + 4)
                operand = (self.curline, self.curfile)
                cip += 8
            elif kind == SYMBOL:                  # size, address, flags, name
                size_bytes, self.dbgaddr, self.dbgparam = cell(cip), cell(cip + 4), cell(cip + 8)
                self.dbgname, self.dbgcode = cip + 12, 3
                operand = (self.dbgaddr, self.dbgparam, self.dbgname)
                cip += 4 + size_bytes
            elif kind == SRANGE:                  # two values
                self.dbgaddr, self.dbgparam = cell(cip), cell(cip + 4)
                self.dbgcode = 8
                operand = (self.dbgaddr, self.dbgparam)
                cip += 8
            elif kind == CASETBL:                 # count, default address, count x (value, address)
                count = cell(cip)
                default = cell(cip + 4, True) if count >= 0 else None
                cases = [(cell(cip + 8 * i), cell(cip + 8 * i + 4, True)) for i in range(1, count + 1)]
                operand = (count, default, cases)
                cip += 4 + (8 * count + 4)
            decoded[start] = (opcode, operand, cip)
        self.flags |= FLAG_RELOC
        self._decoded = decoded
        return ERR_NONE

    def _natives(self):
        """The bindings of the native records.  A record whose first word is not zero in the
        file counts as bound by the original, to a machine address the model cannot follow."""
        if self._bound is None:
            self._bound = [None if self._header_cell(self.natives_off + i * RECORD_SIZE) == 0 else _FOREIGN
                           for i in range(max(self.num_natives, 0))]
        return self._bound

    def register(self, natives):
        """scr_registerNatives 0x141310 with a name -> callable table: binds every native
        record that is not bound yet.  Returns 0, or 19 when a name is missing (the others
        are still bound)."""
        result = ERR_NONE
        for index in range(len(self._natives())):
            if self._bound[index] is None:
                name = self.native_name(index)
                function = natives.get(name)
                if function is None:
                    function = natives.get(name.decode('latin-1'))
                if function is None:
                    result = ERR_NOTFOUND
                else:
                    self._bound[index] = function
        return result

    def find_public(self, name):
        """scr_findEntry 0x13eac8: binary search of the entry-point table, which the compiler
        sorted by name (bytes compared as unsigned values).  Returns (0, index) or
        (19, 0x7fffffff)."""
        if not self._parsed:
            raise HostFault('the machine was not loaded: its base pointer is null')
        if isinstance(name, str):
            name = name.encode('latin-1')
        name = bytes(name).split(b'\0')[0]
        first, last = 0, self.num_publics - 1
        while first <= last:
            middle = (first + last) // 2
            entry = self._header_name(self.publics_off + middle * RECORD_SIZE + 4)
            if entry > name:
                last = middle - 1
            elif entry < name:
                first = middle + 1
            else:
                return ERR_NONE, middle
        return ERR_NOTFOUND, NOT_FOUND_INDEX

    # ---- script memory ----------------------------------------------------------------------
    def _position(self, address, size):
        if address < 0 or address & (size - 1) or self.data_offset + address + size > len(self.image):
            raise HostFault('%d-byte access at script address %d (0x%x): outside the script\'s memory '
                            'or not aligned' % (size, address, address & M32))
        return self.data_offset + address

    def cell(self, address):
        """Signed cell at a script address."""
        return struct.unpack_from('<i', self.image, self._position(address, 4))[0]

    def set_cell(self, address, value):
        struct.pack_into('<I', self.image, self._position(address, 4), value & M32)

    def memory(self):
        """The script's own block: data, heap, stack and the sentinel cell."""
        return bytes(self.image[self.data_offset:])

    def get_addr(self, address):
        """scr_getAddr 0x1414a8: 0 when address is a legal data, heap or stack address by the
        registers saved at the last native call, else 5."""
        if (self.hea <= address < self.stk) or address >= self.stp:
            return ERR_MEMACCESS
        return ERR_NONE

    def get_string(self, address):
        """scr_getString 0x141650: the bytes of the string at address, without terminator.
        First cell above 0xff (as a signed number): packed, four characters per cell, the first
        in the most significant byte, ended by a zero byte.  Otherwise unpacked: the low byte
        of each cell, ended by a zero cell."""
        out = bytearray()
        first = self.cell(address)
        if first < 0x100:
            if first == 0:
                return b''
            while True:
                out.append(self.cell(address) & 0xFF)
                address += 4
                if self.cell(address) == 0:
                    return bytes(out)
        while True:
            value = self.cell(address)
            address += 4
            for shift in (24, 16, 8, 0):
                char = (value >> shift) & 0xFF
                if char == 0:
                    return bytes(out)
                out.append(char)

    def set_string(self, address, text, pack):
        """scr_setString 0x140f10: stores text (bytes, cut at the first zero) packed or
        unpacked.  Unpacked characters are sign-extended bytes."""
        text = bytes(text).split(b'\0')[0]
        length = len(text)
        if pack:
            self.set_cell(address + (length // 4) * 4, 0)
            for index, char in enumerate(text):          # raw copy, then every cell byte-swapped
                self.image[self._position(address + index, 1)] = char
            for index in range(length // 4, -1, -1):
                position = self._position(address + 4 * index, 4)
                self.image[position:position + 4] = self.image[position:position + 4][::-1]
        else:
            for index, char in enumerate(text):
                self.set_cell(address + 4 * index, char - 0x100 if char & 0x80 else char)
            self.set_cell(address + 4 * length, 0)
        return ERR_NONE

    def str_len(self, address):
        """scr_strLen 0x141568: length in characters of a packed or unpacked string."""
        first = self.cell(address)
        if first < 0x100:
            length = 0
            if first != 0:
                while True:
                    length += 1
                    if self.cell(address + 4 * length) == 0:
                        break
            return length
        length = 0                                        # first zero byte in memory order
        while self.image[self._position(address + length, 1)] != 0:
            length += 1
        value = self.cell(address + (length & ~3)) & M32
        length &= ~3
        while value & 0xFF000000:
            length += 1
            value = (value << 8) & M32
        return length

    def allot(self, cells):
        """scr_allot 0x1414f8: reserve cells on the heap.  Returns (0, address) or (16, None).
        The room test is an unsigned compare of stk - hea - size with 0x40, as in the
        original, so a request larger than the free room is granted."""
        size = s32(cells << 2)
        if ((self.stk - self.hea - size) & M32) < STKMARGIN:
            return ERR_MEMORY, None
        address = self.hea
        self.hea = s32(self.hea + size)
        return ERR_NONE, address

    def release(self, address):
        """scr_release 0x141550: lower the heap top to address (never raises it)."""
        if address < self.hea:
            self.hea = address
        return ERR_NONE

    def raise_error(self, code):
        """scr_raiseError 0x141498: the run that called the current native stops with code."""
        self.error = code
        return ERR_NONE

    # ---- natives ----------------------------------------------------------------------------
    def _foreign_callback(self, index, params):
        raise HostFault('the callback word of the image was not zero when it was loaded')

    def _call_native(self, index, params):
        """scr_callNative 0x141050: clears the error word, calls the handler bound to native
        record index with (machine, params), and returns (error word, handler result)."""
        if not 0 <= index < len(self._natives()):
            raise HostFault('native index %d is outside the script\'s native table' % index)
        function = self._bound[index]
        if function is None or function is _FOREIGN:
            raise HostFault('native %r is not bound: the original would jump to the address in its record'
                            % self.native_name(index))
        self.error = 0
        self.params = params
        count = self.cell(params)
        args = [self.cell(params + 4 + 4 * k) for k in range(max(count, 0) // 4)]
        result = function(self, args)
        return self.error, s32(result or 0)

    # ---- running ----------------------------------------------------------------------------
    def call(self, name, pri=0):
        """script_runByName 0x1ed694: -1 when there is no such entry point; otherwise the
        value the run returned, or 0 when it ended with an error (the error is dropped)."""
        error, index = self.find_public(name)
        if error:
            return -1
        error, result = self.execute(index, pri=pri)
        return 0 if result is None else result

    def execute(self, index, params=(), pri=0):
        """scr_interpret 0x13ecf8: run entry point index (EXEC_MAIN for the header's start
        address) to its end.  Returns (error, result); result is None when the original does
        not store one (every error return except HALT).

        params are cells pushed for the entry point.  pri is the initial PRI: the original
        leaves it uninitialised (whatever its own stack held), so a caller that cares must
        say what it was.  When self.budget is a number it is counted down by every
        instruction, nested runs included, and Limit is raised at zero."""
        if self.callback is None:
            return ERR_CALLBACK, None
        self.flags &= ~FLAG_BROWSE
        if not self.flags & FLAG_RELOC:
            return ERR_INIT, None
        if not self._parsed or self._decoded is None:
            raise HostFault('the image came flagged as loaded or relocated: the original would use '
                            'machine words that scr_load never set')
        stk = reset_stk = self.stk
        hea = self.hea
        if self.hdr_stp < stk:                # sic: the header's field, not the data-relative top
            return ERR_STACKLOW, None
        if hea < 0:
            return ERR_HEAPLOW, None
        if index == EXEC_MAIN:
            cip = self.start
            if cip < 0:
                return ERR_INDEX, None
        else:
            if (index < 0 and index != -2) or not index < self.num_publics:
                return ERR_INDEX, None
            cip = self._header_cell(self.publics_off + index * RECORD_SIZE)    # -2 is not refused
        cell, put = self.cell, self.set_cell
        stk = s32(stk - 4 * len(params))
        for position, value in enumerate(params):
            put(stk + 4 * position, value)
        stk = s32(stk - 4)
        put(stk, 4 * len(params))             # argument size in bytes
        stk = s32(stk - 4)
        put(stk, 0)                           # return address 0: "back to the host"
        if stk < s32(hea + STKMARGIN):
            return ERR_STACKERR, None         # after both cells were written
        pri, alt, frm = s32(pri), 0, 0
        decoded, profile = self._decoded, self.profile
        stp = self.stp

        def abort(code):                      # the error exits that restore the stack pointer
            self.stk = reset_stk
            return code, None

        while True:
            instruction = decoded.get(cip)
            if instruction is None:
                raise HostFault('execution reaches code offset %d (0x%x), which the loader did not '
                                'prepare as an instruction' % (cip, cip & M32))
            if self.budget is not None:
                if self.budget <= 0:
                    raise Limit('instruction budget used up at code offset 0x%x' % cip)
                self.budget -= 1
            op, v, cip = instruction          # cip is now the offset of the next instruction
            if profile is not None:
                profile[op] = profile.get(op, 0) + 1

            # ---- loads --------------------------------------------------------------------
            if op == 0x01:                    # LOAD.pri
                pri = cell(v)
            elif op == 0x02:                  # LOAD.alt
                alt = cell(v)
            elif op == 0x03:                  # LOAD.S.pri
                pri = cell(s32(frm + v))
            elif op == 0x04:                  # LOAD.S.alt
                alt = cell(s32(frm + v))
            elif op == 0x05:                  # LREF.pri
                pri = cell(cell(v))
            elif op == 0x06:                  # LREF.alt
                alt = cell(cell(v))
            elif op == 0x07:                  # LREF.S.pri
                pri = cell(cell(s32(frm + v)))
            elif op == 0x08:                  # LREF.S.alt
                alt = cell(cell(s32(frm + v)))
            elif op == 0x09:                  # LOAD.I
                if hea <= pri < stk or pri >= stp:
                    return abort(ERR_MEMACCESS)
                pri = cell(pri)
            elif op == 0x0A:                  # LODB.I: 1, 2 or 4 bytes, zero-extended
                if hea <= pri < stk or pri >= stp:
                    return abort(ERR_MEMACCESS)
                if v == 1 or v == 2:
                    position = self._position(pri, v)
                    pri = int.from_bytes(self.image[position:position + v], 'little')
                elif v == 4:
                    pri = cell(pri)
            elif op == 0x0B:                  # CONST.pri
                pri = v
            elif op == 0x0C:                  # CONST.alt
                alt = v
            elif op == 0x0D:                  # ADDR.pri
                pri = s32(frm + v)
            elif op == 0x0E:                  # ADDR.alt
                alt = s32(frm + v)

            # ---- stores -------------------------------------------------------------------
            elif op == 0x0F:                  # STOR.pri
                put(v, pri)
            elif op == 0x10:                  # STOR.alt
                put(v, alt)
            elif op == 0x11:                  # STOR.S.pri
                put(s32(frm + v), pri)
            elif op == 0x12:                  # STOR.S.alt
                put(s32(frm + v), alt)
            elif op == 0x13:                  # SREF.pri
                put(cell(v), pri)
            elif op == 0x14:                  # SREF.alt
                put(cell(v), alt)
            elif op == 0x15:                  # SREF.S.pri
                put(cell(s32(frm + v)), pri)
            elif op == 0x16:                  # SREF.S.alt
                put(cell(s32(frm + v)), alt)
            elif op == 0x17:                  # STOR.I
                if hea <= alt < stk or alt >= stp:
                    return abort(ERR_MEMACCESS)
                put(alt, pri)
            elif op == 0x18:                  # STRB.I: low 1, 2 or 4 bytes of PRI
                if hea <= alt < stk or alt >= stp:
                    return abort(ERR_MEMACCESS)
                if v == 1 or v == 2 or v == 4:
                    position = self._position(alt, v)
                    self.image[position:position + v] = (pri & M32).to_bytes(4, 'little')[:v]

            # ---- indexing -----------------------------------------------------------------
            elif op == 0x19 or op == 0x1A:    # LIDX, LIDX.B
                address = s32((pri << (2 if op == 0x19 else v & 31)) + alt)
                if hea <= address < stk or address >= stp:
                    return abort(ERR_MEMACCESS)
                pri = cell(address)
            elif op == 0x1B:                  # IDXADDR
                pri = s32((pri << 2) + alt)
            elif op == 0x1C:                  # IDXADDR.B
                pri = s32((pri << (v & 31)) + alt)
            elif op == 0x1D:                  # ALIGN.pri (little-endian host)
                if 0 <= v < 4:
                    pri ^= 4 - v
            elif op == 0x1E:                  # ALIGN.alt
                if 0 <= v < 4:
                    alt ^= 4 - v

            # ---- control registers ----------------------------------------------------------
            elif op == 0x1F:                  # LCTRL
                if v == 0:
                    pri = self.cod
                elif v == 1:
                    pri = self.dat
                elif v == 2:
                    pri = hea
                elif v == 3:
                    pri = stp
                elif v == 4:
                    pri = stk
                elif v == 5:
                    pri = frm
                elif v == 6:
                    pri = cip
            elif op == 0x20:                  # SCTRL
                if v == 2:
                    hea = pri
                elif v == 4:
                    stk = pri
                elif v == 5:
                    frm = pri
                elif v == 6:
                    cip = pri
            elif op == 0x21:                  # MOVE.pri
                pri = alt
            elif op == 0x22:                  # MOVE.alt
                alt = pri
            elif op == 0x23:                  # XCHG
                pri, alt = alt, pri

            # ---- stack and heap -------------------------------------------------------------
            elif op == 0x24:                  # PUSH.pri
                stk = s32(stk - 4)
                put(stk, pri)
            elif op == 0x25:                  # PUSH.alt
                stk = s32(stk - 4)
                put(stk, alt)
            elif op == 0x26:                  # PUSH.R: count taken as unsigned
                for _ in range(v & M32):
                    stk = s32(stk - 4)
                    put(stk, pri)
            elif op == 0x27:                  # PUSH.C
                stk = s32(stk - 4)
                put(stk, v)
            elif op == 0x28:                  # PUSH
                value = cell(v)
                stk = s32(stk - 4)
                put(stk, value)
            elif op == 0x29:                  # PUSH.S
                value = cell(s32(frm + v))
                stk = s32(stk - 4)
                put(stk, value)
            elif op == 0x2A:                  # POP.pri
                pri = cell(stk)
                stk = s32(stk + 4)
            elif op == 0x2B:                  # POP.alt
                alt = cell(stk)
                stk = s32(stk + 4)
            elif op == 0x2C:                  # STACK: errors leave the saved stack pointer alone
                alt = stk
                stk = s32(stk + v)
                if stk < s32(hea + STKMARGIN):
                    return ERR_STACKERR, None
                if self.hdr_stp < stk:
                    return ERR_STACKLOW, None
            elif op == 0x2D:                  # HEAP
                alt = hea
                hea = s32(hea + v)
                if stk < s32(hea + STKMARGIN):
                    return ERR_STACKERR, None
                if hea < 0:
                    return ERR_HEAPLOW, None

            # ---- calls --------------------------------------------------------------------
            elif op == 0x2E:                  # PROC
                stk = s32(stk - 4)
                put(stk, frm)
                frm = stk
            elif op == 0x2F:                  # RET
                frm = cell(stk)
                target = cell(s32(stk + 4))
                stk = s32(stk + 8)
                if target == 0:
                    self.stk = reset_stk
                    return ERR_NONE, pri
                cip = target
            elif op == 0x30:                  # RETN: also drops the arguments
                frm = cell(stk)
                target = cell(s32(stk + 4))
                stk = s32(stk + 8)
                stk = s32(stk + cell(stk) + 4)
                self.stk = stk                # every RETN stores the stack pointer
                if target == 0:
                    return ERR_NONE, pri
                cip = target
            elif op == 0x31:                  # CALL
                stk = s32(stk - 4)
                put(stk, cip)
                cip = v
            elif op == 0x32:                  # CALL.pri
                stk = s32(stk - 4)
                put(stk, cip)
                cip = pri

            # ---- jumps --------------------------------------------------------------------
            elif op == 0x33:                  # JUMP
                cip = v
            elif op == 0x34:                  # JREL: relative to the next instruction
                cip = s32(cip + v)
            elif op == 0x35:                  # JZER
                if pri == 0:
                    cip = v
            elif op == 0x36:                  # JNZ
                if pri != 0:
                    cip = v
            elif op == 0x37:                  # JEQ
                if pri == alt:
                    cip = v
            elif op == 0x38:                  # JNEQ
                if pri != alt:
                    cip = v
            elif op == 0x39:                  # JLESS (unsigned)
                if pri & M32 < alt & M32:
                    cip = v
            elif op == 0x3A:                  # JLEQ
                if pri & M32 <= alt & M32:
                    cip = v
            elif op == 0x3B:                  # JGRTR
                if pri & M32 > alt & M32:
                    cip = v
            elif op == 0x3C:                  # JGEQ
                if pri & M32 >= alt & M32:
                    cip = v
            elif op == 0x3D:                  # JSLESS (signed)
                if pri < alt:
                    cip = v
            elif op == 0x3E:                  # JSLEQ
                if pri <= alt:
                    cip = v
            elif op == 0x3F:                  # JSGRTR
                if pri > alt:
                    cip = v
            elif op == 0x40:                  # JSGEQ
                if pri >= alt:
                    cip = v

            # ---- arithmetic: shift counts are taken modulo 32 ---------------------------------
            elif op == 0x41:                  # SHL
                pri = s32(pri << (alt & 31))
            elif op == 0x42:                  # SHR (logical)
                pri = s32((pri & M32) >> (alt & 31))
            elif op == 0x43:                  # SSHR (arithmetic)
                pri >>= alt & 31
            elif op == 0x44:                  # SHL.C.pri
                pri = s32(pri << (v & 31))
            elif op == 0x45:                  # SHL.C.alt
                alt = s32(alt << (v & 31))
            elif op == 0x46:                  # SHR.C.pri (logical)
                pri = s32((pri & M32) >> (v & 31))
            elif op == 0x47:                  # SHR.C.alt (logical)
                alt = s32((alt & M32) >> (v & 31))
            elif op == 0x48 or op == 0x4B:    # SMUL, UMUL: low 32 bits of the product
                pri = s32(pri * alt)
            elif op == 0x49:                  # SDIV: PRI / ALT
                if alt == 0:
                    return abort(ERR_DIVIDE)
                pri, alt = floored_div(pri, alt)
            elif op == 0x4A:                  # SDIV.alt: ALT / PRI
                if pri == 0:
                    return abort(ERR_DIVIDE)
                pri, alt = floored_div(alt, pri)
            elif op == 0x4C:                  # UDIV: PRI / ALT, unsigned
                if alt == 0:
                    return abort(ERR_DIVIDE)
                pri, alt = s32((pri & M32) // (alt & M32)), s32((pri & M32) % (alt & M32))
            elif op == 0x4D:                  # UDIV.alt: ALT / PRI, unsigned
                if pri == 0:
                    return abort(ERR_DIVIDE)
                pri, alt = s32((alt & M32) // (pri & M32)), s32((alt & M32) % (pri & M32))
            elif op == 0x4E:                  # ADD
                pri = s32(pri + alt)
            elif op == 0x4F:                  # SUB
                pri = s32(pri - alt)
            elif op == 0x50:                  # SUB.alt
                pri = s32(alt - pri)
            elif op == 0x51:                  # AND
                pri &= alt
            elif op == 0x52:                  # OR
                pri |= alt
            elif op == 0x53:                  # XOR
                pri ^= alt
            elif op == 0x54:                  # NOT
                pri = 1 if pri == 0 else 0
            elif op == 0x55:                  # NEG
                pri = s32(-pri)
            elif op == 0x56:                  # INVERT
                pri = ~pri
            elif op == 0x57:                  # ADD.C
                pri = s32(pri + v)
            elif op == 0x58:                  # SMUL.C
                pri = s32(pri * v)
            elif op == 0x59:                  # ZERO.pri
                pri = 0
            elif op == 0x5A:                  # ZERO.alt
                alt = 0
            elif op == 0x5B:                  # ZERO
                put(v, 0)
            elif op == 0x5C:                  # ZERO.S
                put(s32(frm + v), 0)
            elif op == 0x5D:                  # SIGN.pri: only sets the upper bits, never clears them
                if pri & 0x80:
                    pri = s32(pri | 0xFFFFFF00)
            elif op == 0x5E:                  # SIGN.alt
                if alt & 0x80:
                    alt = s32(alt | 0xFFFFFF00)

            # ---- comparisons ----------------------------------------------------------------
            elif op == 0x5F:                  # EQ
                pri = 1 if pri == alt else 0
            elif op == 0x60:                  # NEQ
                pri = 1 if pri != alt else 0
            elif op == 0x61:                  # LESS (unsigned)
                pri = 1 if pri & M32 < alt & M32 else 0
            elif op == 0x62:                  # LEQ
                pri = 1 if pri & M32 <= alt & M32 else 0
            elif op == 0x63:                  # GRTR
                pri = 1 if pri & M32 > alt & M32 else 0
            elif op == 0x64:                  # GEQ
                pri = 1 if pri & M32 >= alt & M32 else 0
            elif op == 0x65:                  # SLESS (signed)
                pri = 1 if pri < alt else 0
            elif op == 0x66:                  # SLEQ
                pri = 1 if pri <= alt else 0
            elif op == 0x67:                  # SGRTR
                pri = 1 if pri > alt else 0
            elif op == 0x68:                  # SGEQ
                pri = 1 if pri >= alt else 0
            elif op == 0x69:                  # EQ.C.pri
                pri = 1 if pri == v else 0
            elif op == 0x6A:                  # EQ.C.alt
                pri = 1 if alt == v else 0

            # ---- increments -----------------------------------------------------------------
            elif op == 0x6B:                  # INC.pri
                pri = s32(pri + 1)
            elif op == 0x6C:                  # INC.alt
                alt = s32(alt + 1)
            elif op == 0x6D:                  # INC
                put(v, cell(v) + 1)
            elif op == 0x6E:                  # INC.S
                put(s32(frm + v), cell(s32(frm + v)) + 1)
            elif op == 0x6F:                  # INC.I (address not checked)
                put(pri, cell(pri) + 1)
            elif op == 0x70:                  # DEC.pri
                pri = s32(pri - 1)
            elif op == 0x71:                  # DEC.alt
                alt = s32(alt - 1)
            elif op == 0x72:                  # DEC
                put(v, cell(v) - 1)
            elif op == 0x73:                  # DEC.S
                put(s32(frm + v), cell(s32(frm + v)) - 1)
            elif op == 0x74:                  # DEC.I
                put(pri, cell(pri) - 1)

            # ---- blocks: no address checks; the count is unsigned ---------------------------
            elif op == 0x75:                  # MOVS: v bytes from [PRI] to [ALT], lowest address first
                count = v & M32
                source, target = self._block(pri, count), self._block(alt, count)
                for offset in range(count):
                    self.image[target + offset] = self.image[source + offset]
            elif op == 0x76:                  # CMPS: difference of the first bytes that differ
                count = v & M32
                first, second = self._block(alt, 0), self._block(pri, 0)
                room = len(self.image) - max(first, second)
                difference = 0
                for offset in range(min(count, room)):
                    difference = self.image[first + offset] - self.image[second + offset]
                    if difference:
                        break
                if not difference and count > room:
                    raise HostFault('CMPS of %d bytes runs past the end of the script\'s memory' % count)
                pri = difference
            elif op == 0x77:                  # FILL: whole cells only
                count, address = v & M32, alt
                while count >= 4:
                    put(address, pri)
                    address = s32(address + 4)
                    count -= 4

            # ---- ending, checking, natives --------------------------------------------------
            elif op == 0x78:                  # HALT: the operand is the error code returned
                self.stk = reset_stk
                return v, pri
            elif op == 0x79:                  # BOUNDS
                if pri > v or pri < 0:
                    return abort(ERR_BOUNDS)
            elif op == 0x7A or op == 0x7B:    # SYSREQ.pri, SYSREQ.C
                if self.callback is None:
                    raise HostFault('native call with no callback: the original would jump to address 0')
                self.cip, self.frm, self.hea, self.stk = cip, frm, hea, stk
                error, pri = self.callback(pri if op == 0x7A else v, stk)
                pri = s32(pri)
                if error:
                    return abort(error)

            # ---- debug records --------------------------------------------------------------
            elif op == 0x7C:                  # FILE: skipped
                pass
            elif op == 0x7D:                  # LINE
                self.curline, self.curfile = v
            elif op == 0x7E:                  # SYMBOL
                self.dbgaddr, self.dbgparam, self.dbgname = v
            elif op == 0x7F:                  # SRANGE
                self.dbgaddr, self.dbgparam = v

            elif op == 0x80:                  # JUMP.pri
                cip = pri
            elif op == 0x81:                  # SWITCH: first matching record wins
                table = decoded.get(v)
                if table is None or table[0] != OP['CASETBL'] or table[1][0] < 0:
                    raise HostFault('SWITCH operand 0x%x is not a case table the loader relocated' % (v & M32))
                count, cip, cases = table[1]
                for value, target in cases:
                    if value == pri:
                        cip = target
                        break
            elif op == 0x82:                  # CASETBL: its handler goes on to run the record count
                raise HostFault('CASETBL executed: the original runs the record count as an instruction')
            else:                             # NONE (0): the loader never lets it into the code
                return abort(ERR_INVINSTR)

    def _block(self, address, count):
        """Position in the image of count bytes at a script address, for MOVS and CMPS."""
        if address < 0 or self.data_offset + address + count > len(self.image):
            raise HostFault('%d-byte block at script address %d: outside the script\'s memory' % (count, address))
        return self.data_offset + address

    # ---- save and restore (a convenience of the model) --------------------------------------
    _STATE = ('cip', 'frm', 'hea', 'stk', 'stp', 'flags', 'curline', 'curfile', 'dbgcode', 'dbgaddr',
              'dbgparam', 'dbgname', 'error', 'hdr_stp')

    def snapshot(self):
        return bytes(self.image), tuple(getattr(self, name, None) for name in self._STATE)

    def restore(self, saved):
        self.image[:] = saved[0]
        for name, value in zip(self._STATE, saved[1]):
            setattr(self, name, value)


_FOREIGN = object()        # a native record whose address word was not zero in the file


# ---------------------------------------------------------------------------------------------
# Building images (for tests and experiments; the game's files come from the Small compiler)
# ---------------------------------------------------------------------------------------------

def assemble(program):
    """Turn a list into code cells.  Items:
         'name:'                               a label
         ('MNEMONIC',) or ('MNEMONIC', x)      x is a number or a label name
         ('CASETBL', default, [(value, target), ...])
         ('LINE', line, file)   ('SRANGE', a, b)
         ('FILE', number, name bytes)   ('SYMBOL', address, flags, name bytes)
         ('cell', x)                           one raw cell
       Returns (cells, {label: code offset})."""
    labels, offset = {}, 0
    sized = []
    for item in program:
        if isinstance(item, str):
            if not item.endswith(':'):
                raise ValueError('label %r must end with a colon' % item)
            labels[item[:-1]] = offset
            continue
        name = item[0]
        if name == 'cell':
            cells = [item[1]]
        elif name == 'CASETBL':
            cells = [OP[name], len(item[2]), item[1]]
            for value, target in item[2]:
                cells += [value, target]
        elif name in ('FILE', 'SYMBOL'):
            text = bytes(item[-1]) + b'\0'
            text += b'\0' * (-len(text) % 4)
            words = list(struct.unpack('<%di' % (len(text) // 4), text))
            head = list(item[1:-1])
            cells = [OP[name], 4 * (len(head) + len(words))] + head + words
        else:
            cells = [OP[name]] + list(item[1:])
        sized.append(cells)
        offset += 4 * len(cells)
    out = []
    for cells in sized:
        for value in cells:
            out.append(labels[value] if isinstance(value, str) else value)
    return out, labels


def build_image(code, data=(), publics=(), natives=(), stack_cells=2048, start=-1, flags=0,
                file_version=3, amx_version=1, compact=False, sort_publics=True):
    """A script.scr image: 0x60 zero bytes, header, entry-point table, native table, code,
    data, then stack_cells zero cells for heap and stack.  code and data are lists of cells
    (data may also be bytes); publics is a list of (name, code offset); natives a list of
    names.  compact=True stores code and data in the compact encoding and sets flag 4."""
    def name_bytes(name):
        name = name.encode('latin-1') if isinstance(name, str) else bytes(name)
        if len(name) > 19:
            raise ValueError('name %r is longer than 19 characters' % name)
        return name.ljust(20, b'\0')

    publics = [(name_bytes(name), address) for name, address in publics]
    if sort_publics:
        publics.sort()
    code_bytes = b''.join(struct.pack('<I', value & M32) for value in code)
    data_bytes = bytes(data) if isinstance(data, (bytes, bytearray)) else b''.join(
        struct.pack('<I', value & M32) for value in data)
    if len(data_bytes) % 4:
        raise ValueError('data must be whole cells')
    cod = HEADER_SIZE + RECORD_SIZE * (len(publics) + len(natives))
    dat = cod + len(code_bytes)
    hea = dat + len(data_bytes)
    stp = hea + 4 * stack_cells
    body = code_bytes + data_bytes
    size = hea
    if compact:
        cells = struct.unpack('<%di' % (len(body) // 4), body)
        for count in range(1, len(cells) + 1):            # the loader expands in place, from the end
            if len(encode_compact(cells[:count])) > 4 * count:
                raise ValueError('the first %d cells take more than 4 bytes each: not expandable in place' % count)
        coded = encode_compact(cells)
        size = cod + len(coded)
        body = coded.ljust(len(body), b'\0')
        flags |= 4
    header = struct.pack('<iHbbHH5i', size, MAGIC, file_version, amx_version, flags, RECORD_SIZE,
                         cod, dat, hea, stp, start)
    header += struct.pack('<hxxihxxihxxihxxi', len(publics), HEADER_SIZE, len(natives),
                          HEADER_SIZE + RECORD_SIZE * len(publics), 0, cod, 0, cod)
    tables = b''.join(struct.pack('<i', address) + name for name, address in publics)
    tables += b''.join(struct.pack('<i', 0) + name_bytes(name) for name in natives)
    return bytes(STRUCT_SIZE) + header + tables + body + bytes(4 * stack_cells)


# ---------------------------------------------------------------------------------------------

def _main(argv):
    if len(argv) < 2 or argv[0] not in ('info', 'run') or (argv[0] == 'run' and len(argv) < 3):
        print(__doc__)
        return 2
    with open(argv[1], 'rb') as source:
        machine = Machine(source.read())
    error = machine.load()
    if error:
        print('load failed with error %d' % error)
        return 1
    if argv[0] == 'info':
        print('code %d bytes, data %d bytes, heap+stack %d bytes, %d entry points, %d natives, relocated: %s'
              % (machine.dat - machine.cod, machine.hea, machine.stp - machine.hea, machine.num_publics,
                 machine.num_natives, bool(machine.flags & FLAG_RELOC)))
        for name, address in machine.publics():
            print('  entry 0x%05x %s' % (address, name.decode('latin-1')))
        print('  natives: ' + ' '.join(name.decode('latin-1') for name in machine.native_names()))
        return 0

    def stub(name):
        def native(m, args):
            print('  %s(%s)' % (name, ', '.join(str(a) for a in args)))
            return 0
        return native

    machine.register({name: stub(name.decode('latin-1')) for name in machine.native_names()})
    error, index = machine.find_public(argv[2])
    if error:
        print('no entry point %r' % argv[2])
        return 1
    machine.budget = 1000000
    error, result = machine.execute(index)
    print('error %d, result %r' % (error, result))
    return 0


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
