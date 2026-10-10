#!/usr/bin/env python3
"""difftest_amx.py - the original script machine against the model in tools/ref_amx.py.

Needs your own SLUS_209.73 (US v2.00); the properties about shipped scripts also need the
level scripts unpacked as scripts_raw/*.scr (tools/gob.py extracts script.scr from a level
lump).  Without the executable nothing is run and the exit status is 0; without the scripts
those properties are skipped.

  python3 tools/difftest_amx.py [SLUS_209.73] [--scripts DIR] [--seeds N] [--scale X] [-k TEXT] [-v]

    --scripts DIR  directory of *.scr files (default scripts_raw, or $CHAMPIONS_SCRIPTS)
    --seeds N      random native-result sequences per entry point, besides the two fixed
                   ones (all natives return 0, all return 1); default 3
    --scale X      multiplies the number of synthetic programs (default 1.0)
    -k TEXT        run only the groups whose name contains TEXT
    -v             list every mismatch and every entry point that could not be compared

How a comparison works.  The original machine code runs in tools/ee_emu.py: scr_load,
scr_registerNatives, scr_findEntry, scr_interpret, scr_callNative and the string routines are
executed instruction by instruction on a copy of the script image placed in emulator memory.
The model gets the same image.  Natives are replaced on both sides by the same stub: it
records its name, its argument cells and, for every argument that is a legal script address,
the string the machine's own string reader produces there; then it returns the next value of
a seeded sequence.  After each run the test compares the native trace, the error code, the
result cell, the machine structure (cip, frm, hea, stk, stp, flags, line, file, debug words,
error word) and every byte of the script's data, heap and stack.

The built-in callScript is not stubbed: the original handler (0x143158) runs, which reads its
string argument, looks the entry point up and starts a nested run on the same machine; the
model side does the same through Machine.get_string / find_public / execute.

One PASS or FAIL line per property, with counts; exit status 1 when anything failed.
Cases in which the model raises HostFault (the original would leave the script's own memory;
see tools/ref_amx.py) are counted and not compared, because there the original's result is a
property of the emulator's memory and not of the script machine.
"""
import hashlib
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError, M32, sx32
import ref_amx
from ref_amx import (HostFault, Limit, Machine, OP, OPCODES, assemble, build_image, encode_compact,
                     s32)

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# the original's routines and data
SCR_LOAD, SCR_FIND_ENTRY, SCR_INTERPRET = 0x13E8F8, 0x13EAC8, 0x13ECF8
SCR_SET_STRING, SCR_CALL_NATIVE, SCR_DEBUG_HOOK = 0x140F10, 0x141050, 0x1410B0
SCR_REGISTER, SCR_RAISE_ERROR, SCR_GET_ADDR = 0x141310, 0x141498, 0x1414A8
SCR_ALLOT, SCR_RELEASE, SCR_STR_LEN, SCR_GET_STRING = 0x1414F8, 0x141550, 0x141568, 0x141650
SCRIPT_CALL_SCRIPT, SCRIPT_RUN_BY_NAME = 0x143158, 0x1ED694
G_SCRIPT_MACHINE = 0x86B270
HANDLER_TABLE, RELOC_TABLE = 0x403150, 0x530FD0
RELOC_CLASS = {0x13E770: ref_amx.V, 0x13E778: ref_amx.C, 0x13E790: ref_amx.FILE, 0x13E7C8: ref_amx.LINE,
               0x13E7F8: ref_amx.SYMBOL, 0x13E840: ref_amx.SRANGE, 0x13E870: ref_amx.CASETBL,
               0x13E8C0: ref_amx.N}

SLOT_SIZE = 0x100000
MAX_NATIVES = 256
MAX_DEPTH = 6                   # nesting limit of the synthetic "nest" native (both sides)
BUDGET = 200000                 # model instructions per run before it is called endless
STRUCT_FIELDS = (('cip', 0x0C), ('frm', 0x10), ('hea', 0x14), ('stk', 0x18), ('stp', 0x1C),
                 ('flags', 0x20), ('curline', 0x24), ('curfile', 0x28), ('dbgcode', 0x2C),
                 ('dbgaddr', 0x30), ('dbgparam', 0x34), ('error', 0x5C))

VERBOSE = False
RESULTS = []


def check(ident, ok, text):
    RESULTS.append((ident, bool(ok)))
    print('%s  %-4s %s' % ('PASS' if ok else 'FAIL', ident, text))
    return bool(ok)


def note(text):
    print('      ' + text)


class Tally:
    """Counts cases and keeps the first few mismatches of one property."""

    def __init__(self):
        self.cases = self.bad = self.host = self.endless = 0
        self.examples = []

    def add(self, problems, label):
        self.cases += 1
        if problems:
            self.bad += 1
            if len(self.examples) < (50 if VERBOSE else 3):
                self.examples.append('%s: %s' % (label, '; '.join(problems[:4])))

    def report(self, ident, text):
        ok = check(ident, self.cases > 0 and self.bad == 0, text % {'n': self.cases, 'bad': self.bad,
                                                                   'host': self.host, 'endless': self.endless})
        for line in self.examples:
            note(line)
        return ok


# ---------------------------------------------------------------------------------------------
# The original, in the emulator
# ---------------------------------------------------------------------------------------------

class Original:
    SP = EE.STACK_HI - 0x4000

    def __init__(self, elf):
        self.emu = emu = EE(elf)
        emu.record_calls = emu.record_writes = False
        self.slot = emu.alloc(SLOT_SIZE + 0x1000, align=16)
        self.cells = emu.alloc(0x1000, align=16)        # result cells and argument arrays, per depth
        self.buffer = emu.alloc(0x40000, align=16)      # names and native tables
        self.text = emu.alloc(0x80000, align=16)        # C strings read back from the machine
        self.stubs = emu.alloc(8 * MAX_NATIVES, align=8)
        for slot in range(MAX_NATIVES):
            emu.mem.w32(self.stubs + 8 * slot, 0x03E00008)          # jr ra
            emu.hook(self.stubs + 8 * slot, lambda _emu, slot=slot: self._native(slot))
        emu.hook(SCRIPT_CALL_SCRIPT, self._call_script)
        self.handlers = [emu.mem.u32(HANDLER_TABLE + 4 * op) for op in range(len(OPCODES))]
        self.base = 0
        self.on_native = None           # f(slot, args, params address) -> cell
        self.on_call_script = None      # f(args) -> initial PRI of the nested run
        self.depth = 0

    # ---- calling ----------------------------------------------------------------------------
    def call(self, address, *args, max_steps=5000000):
        emu = self.emu
        emu._pending_call = emu._fresh_call = None
        emu.r[29] = self.SP
        self.depth = 0
        return s32(emu.call(address, *args, max_steps=max_steps))

    def nested(self, address, *args, pri=None):
        """Call a routine from inside a native stub, on the stack below the caller."""
        emu = self.emu
        saved = (emu.r[:], emu.rh[:], emu.hi, emu.lo, emu.hi1, emu.lo1, emu.pc, emu.npc, emu.cur,
                 emu._pending_call, emu._fresh_call, emu._call_site)
        emu.r[29] = ((emu.r[29] & M32) - 0x400) & ~0xF
        if pri is not None:                 # the uninitialised PRI slot of scr_interpret's frame
            emu.mem.w32(emu.r[29] - 0x80 + 4, pri & M32)
        self.depth += 1
        try:
            return s32(emu.call(address, *args))
        finally:
            self.depth -= 1
            emu.r[:], emu.rh[:] = saved[0], saved[1]
            (emu.hi, emu.lo, emu.hi1, emu.lo1, emu.pc, emu.npc, emu.cur,
             emu._pending_call, emu._fresh_call, emu._call_site) = saved[2:]

    def _args(self):
        mem, params = self.emu.mem, self.emu.r[5] & M32
        count = mem.s32(params)
        return params, [mem.s32(params + 4 + 4 * k) for k in range(max(count, 0) // 4)]

    def _native(self, slot):
        emu = self.emu
        params, args = self._args()
        value = self.on_native(slot, args, params)
        emu.r[2] = sx32(value)
        emu.jump(emu.r[31] & M32)

    def _call_script(self, emu):
        # entry of script_callScript: note the call, set the PRI slot of the scr_interpret
        # frame it will create (0xc0 + 0x20 + 0x80 below this stack pointer), then let it run
        _params, args = self._args()
        pri = self.on_call_script(args)
        emu.mem.w32((emu.r[29] & M32) - 0x160 + 4, pri & M32)

    # ---- the machine's routines ---------------------------------------------------------------
    def place(self, image, shift=0):
        mem = self.emu.mem
        self.base = self.slot + shift
        mem.write(self.slot, bytes(shift) + bytes(image) + bytes(0x200))
        mem.w32(G_SCRIPT_MACHINE, self.base)
        return self.base

    def load(self):
        return self.call(SCR_LOAD, self.base, self.base + 0x60)

    def register(self, table, count=-1):
        """scr_registerNatives with a list of (name bytes, handler address)."""
        mem = self.emu.mem
        position = self.buffer + 8 * (len(table) + 1)
        for k, (name, address) in enumerate(table):
            mem.write(position, name + b'\0')
            mem.w32(self.buffer + 8 * k, position)
            mem.w32(self.buffer + 8 * k + 4, address)
            position += len(name) + 1
        mem.w64(self.buffer + 8 * len(table), 0)
        return self.call(SCR_REGISTER, self.base, self.buffer, count)

    def find(self, name):
        mem = self.emu.mem
        mem.write(self.buffer, name + bytes(32))
        mem.w32(self.cells + 0x20, 0x55555555)
        error = self.call(SCR_FIND_ENTRY, self.base, self.buffer, self.cells + 0x20)
        return error, mem.s32(self.cells + 0x20)

    def interpret(self, index, params, pri, sentinel, nested=False, max_steps=5000000):
        """scr_interpret(machine, &result, index, count, arguments): returns (error, result
        cell).  The result cell is pre-set to sentinel; pri goes to the frame's PRI slot."""
        mem = self.emu.mem
        cells = self.cells + 0x100 * (self.depth + 1 if nested else 0)
        mem.w32(cells, sentinel)
        for k, value in enumerate(params):
            mem.w64(cells + 0x40 + 8 * k, value & M32)
        if nested:
            error = self.nested(SCR_INTERPRET, self.base, cells, index, len(params), cells + 0x40, pri=pri)
        else:
            mem.w32(self.SP - 0x80 + 4, pri & M32)
            error = self.call(SCR_INTERPRET, self.base, cells, index, len(params), cells + 0x40,
                              max_steps=max_steps)
        return error, mem.u32(cells)

    def string_at(self, address, limit):
        """The bytes the original's handlers get for a string argument (scr_getAddr, then
        scr_getString into a buffer), or None when the address is negative (scr_getAddr lets
        those through, to memory below the script's data), not on a cell boundary, or refused
        by scr_getAddr.  limit bounds the length (the script's memory size).  The
        buffer is pre-filled so that the terminator, the last byte written, can be found even
        when the copy contains zero bytes."""
        mem = self.emu.mem
        pointer = self.cells + 0xF00
        if address < 0 or address & 3 or self.nested(SCR_GET_ADDR, self.base, address, pointer) != 0:
            return None
        return self.get_string(mem.u32(pointer), limit, self.nested)

    def get_string(self, pointer, limit, call=None):
        """scr_getString(buffer, pointer): the bytes it stores, without the terminator."""
        mem = self.emu.mem
        mem.write(self.text, b'\xA5' * (limit + 8))
        (call or self.call)(SCR_GET_STRING, self.text, pointer)
        return mem.read(self.text, limit + 8).rstrip(b'\xA5')[:-1]

    def host(self, model, address):
        """Machine address of a script address."""
        return self.base + model.data_offset + address

    # ---- state --------------------------------------------------------------------------------
    def save(self, size):
        return self.emu.mem.read(self.base, size)

    def restore(self, saved):
        self.emu.mem.write(self.base, saved)


def model_string(machine, address):
    if address < 0 or address & 3 or machine.get_addr(address) != 0:
        return None
    return machine.get_string(address)


def differences(orig, model, image_size):
    """Everything that differs between the original's machine and the model after a call."""
    mem, base, out = orig.emu.mem, orig.base, []
    for name, offset in STRUCT_FIELDS:
        a, b = mem.u32(base + offset), getattr(model, name) & M32
        if a != b:
            out.append('%s is 0x%x, model 0x%x' % (name, a, b))
    if not model._parsed:           # refused by the loader: nothing may have changed
        if mem.read(base, image_size) != bytes(model.image):
            out.append('image changed by a refused load')
        return out
    name = mem.u32(base + 0x38)
    expected = 0 if model.dbgname is None else (base + 0x60 + model.cod + model.dbgname) & M32
    if name != expected:
        out.append('dbgname is 0x%x, model 0x%x' % (name, expected))
    if mem.s32(base + 0x60 + 0x18) != model.hdr_stp:
        out.append('header stack top is 0x%x, model 0x%x' % (mem.u32(base + 0x78), model.hdr_stp))
    block, mine = mem.read(base + model.data_offset, image_size - model.data_offset), model.memory()
    if block != mine:
        at = next(i for i in range(0, len(mine), 4) if block[i:i + 4] != mine[i:i + 4])
        out.append('memory differs first at script address 0x%x: 0x%08x, model 0x%08x'
                   % (at, struct.unpack_from('<I', block, at)[0], struct.unpack_from('<I', mine, at)[0]))
    return out


def expected_code(orig, model, decoded=None, below=None):
    """The code block the original must hold after scr_load if the model's reading of the
    relocator is right: handler addresses for opcodes, machine addresses for code operands.
    decoded / below: only the instructions of that map that start below that offset (for a
    pass that stopped early)."""
    start = 0x60 + model.cod
    code = bytearray(model.image[start:0x60 + model.dat])
    code_base = orig.base + start

    def add_base(offset):
        struct.pack_into('<I', code, offset, (struct.unpack_from('<I', code, offset)[0] + code_base) & M32)

    for offset, (op, operand, _next) in (model._decoded if decoded is None else decoded).items():
        if below is not None and offset >= below:
            continue
        struct.pack_into('<I', code, offset, orig.handlers[op])
        kind = OPCODES[op][1]
        if kind == ref_amx.C:
            add_base(offset + 4)
        elif kind == ref_amx.CASETBL:
            for record in range(operand[0] + 1):
                add_base(offset + 8 + 8 * record)
    return bytes(code)


class Returns:
    """The seeded sequence of native results, identical on both sides."""

    def __init__(self, seed):
        self.fixed = {'zero': 0, 'one': 1}.get(seed)
        self.rng = random.Random(seed)

    def next(self):
        if self.fixed is not None:
            return self.fixed
        roll = self.rng.random()
        if roll < 0.35:
            return 0
        if roll < 0.60:
            return 1
        if roll < 0.80:
            return self.rng.randint(2, 12)
        if roll < 0.90:
            return self.rng.randint(-8, -1)
        return s32(self.rng.getrandbits(32))


class Side:
    """What the stubs of one side (original or model) need during a run."""

    def __init__(self):
        self.trace, self.returns, self.nested_runs = [], None, 0

    def begin(self, seed):
        self.trace, self.returns, self.nested_runs = [], Returns(seed), 0


def nested_pri(trace):
    return 0x5EED0000 + len(trace)


# ---------------------------------------------------------------------------------------------
# T. Tables
# ---------------------------------------------------------------------------------------------

def group_tables(orig, options):
    mem = orig.emu.mem
    wrong = [number for number, (_name, _kind, handler) in enumerate(OPCODES) if orig.handlers[number] != handler]
    check('T1', not wrong, 'handler table 0x403150: the %d addresses in ref_amx.OPCODES are the '
          'executable\'s%s' % (len(OPCODES), '' if not wrong else ' - wrong for %s' % wrong))
    wrong = [number for number in range(1, len(OPCODES))
             if RELOC_CLASS.get(mem.u32(RELOC_TABLE + 4 * (number - 1))) != OPCODES[number][1]]
    check('T2', not wrong, 'relocator jump table 0x530fd0: the operand class of each of the %d opcodes '
          '1..0x82 in ref_amx.OPCODES is the relocator\'s%s' % (len(OPCODES) - 1, '' if not wrong else
                                                                ' - wrong for %s' % wrong))
    orig.call(SCR_INTERPRET, 0, orig.cells, 0, 0, 0)
    check('T3', mem.u32(orig.cells) == HANDLER_TABLE,
          'scr_interpret called without a machine stores the handler table address and returns')


# ---------------------------------------------------------------------------------------------
# A. Shipped scripts
# ---------------------------------------------------------------------------------------------

class ScriptPair:
    """One shipped script loaded on both sides with matching stubs."""

    def __init__(self, orig, image, name):
        self.orig, self.image, self.name = orig, image, name
        self.model = Machine(image)
        orig.place(image)
        self.o, self.m = Side(), Side()

    def bind(self, rng):
        """Registers the natives on both sides; returns the list of problems."""
        orig, model, problems = self.orig, self.model, []
        names = model.native_names()
        self.names = names
        table = [(name, SCRIPT_CALL_SCRIPT if name == b'callScript' else orig.stubs + 8 * slot)
                 for slot, name in enumerate(names)]
        natives = {name: (self._model_call_script if name == b'callScript' else self._model_stub(name))
                   for name in names}
        mem = orig.emu.mem
        if len(names) > 1:                               # one name missing: 19, the rest is bound
            missing = rng.randrange(len(names))
            if names.count(names[missing]) == 1:
                a = orig.register([entry for entry in table if entry[0] != names[missing]])
                b = model.register({name: f for name, f in natives.items() if name != names[missing]})
                if (a, b) != (19, 19):
                    problems.append('registration without %r returns %d, model %d' % (names[missing], a, b))
                for slot, name in enumerate(names):      # every other record is bound all the same
                    bound = mem.u32(orig.base + 0x60 + model.natives_off + 24 * slot) != 0
                    if bound != (name != names[missing]) or bound != (model._natives()[slot] is not None):
                        problems.append('after it, record %r bound: %s' % (name, bound))
        shuffled = table[:]
        rng.shuffle(shuffled)
        a, b = orig.register(shuffled), model.register(natives)
        if (a, b) != (0, 0):
            problems.append('registration returns %d, model %d' % (a, b))
        for slot, (name, address) in enumerate(table):
            record = orig.base + 0x60 + model.natives_off + 24 * slot
            if mem.u32(record) != address:
                problems.append('native %r bound to 0x%x' % (name, mem.u32(record)))
        orig.on_native = self._orig_stub
        orig.on_call_script = self._orig_call_script
        return problems

    # the stub, original side
    def _orig_stub(self, slot, args, _params):
        side = self.o
        side.trace.append((self.names[slot], tuple(args), tuple(self.orig.string_at(a, len(self.image)) for a in args)))
        return side.returns.next()

    def _orig_call_script(self, args):
        side = self.o
        side.trace.append((b'callScript', tuple(args), tuple(self.orig.string_at(a, len(self.image)) for a in args)))
        side.nested_runs += 1
        return nested_pri(side.trace)

    # the stub, model side
    def _model_stub(self, name):
        def native(machine, args):
            side = self.m
            side.trace.append((name, tuple(args), tuple(model_string(machine, a) for a in args)))
            return side.returns.next()
        return native

    def _model_call_script(self, machine, args):
        """script_callScript 0x143158 followed by script_runByName 0x1ed694."""
        side = self.m
        side.trace.append((b'callScript', tuple(args), tuple(model_string(machine, a) for a in args)))
        side.nested_runs += 1
        address = machine.cell(machine.params + 4)
        if machine.get_addr(address) != 0:
            raise HostFault('callScript: scr_getAddr refuses the address and the handler reads an '
                            'uninitialised pointer')
        return machine.call(machine.get_string(address), pri=nested_pri(side.trace))

    def run(self, index, seed, pri, label, tally, stats):
        """Runs one entry point on both sides and compares.  Returns 'ok', 'bad', 'host' or
        'endless'."""
        orig, model = self.orig, self.model
        self.m.begin(seed)
        model.budget = BUDGET
        stk_before = model.stk
        try:
            m_error, m_result = model.execute(index, pri=pri)
        except Limit:
            tally.endless += 1
            return 'endless'
        except HostFault as fault:
            tally.host += 1
            stats['host'].append('%s: %s' % (label, fault))
            return 'host'
        used = BUDGET - model.budget
        self.o.begin(seed)
        sentinel = 0xA5A50000 | (index & 0xFFFF)
        problems = []
        try:
            o_error, o_cell = orig.interpret(index, (), pri, sentinel, max_steps=200 * used + 2000000)
        except EmuError as stop:
            tally.add(['the emulator stopped: %s' % stop], label)
            return 'bad'
        if self.o.trace != self.m.trace:
            at = next((i for i, (a, b) in enumerate(zip(self.o.trace, self.m.trace)) if a != b),
                      min(len(self.o.trace), len(self.m.trace)))
            problems.append('native trace differs at call %d of %d/%d: %r, model %r' % (
                at, len(self.o.trace), len(self.m.trace),
                self.o.trace[at] if at < len(self.o.trace) else None,
                self.m.trace[at] if at < len(self.m.trace) else None))
        if o_error != m_error:
            problems.append('error %d, model %d' % (o_error, m_error))
        if o_cell != (sentinel if m_result is None else m_result & M32):
            problems.append('result cell 0x%x, model %r' % (o_cell, m_result))
        problems += differences(orig, model, len(self.image))
        tally.add(problems, label)
        stats['runs'] += 1
        stats['instructions'] += used
        stats['calls'] += len(self.m.trace)
        stats['strings'] += sum(1 for entry in self.m.trace for text in entry[2] if text is not None)
        stats['nested'] += self.m.nested_runs
        if m_error:
            stats['errors'][m_error] = stats['errors'].get(m_error, 0) + 1
        elif model.stk != stk_before:
            stats['moved'][self.name + ' ' + model.public(index)[0].decode('latin-1')] = model.stk - stk_before
        return 'bad' if problems else 'ok'


def group_scripts(orig, options):
    directory = options['scripts']
    files = sorted(f for f in os.listdir(directory) if f.lower().endswith('.scr')) if os.path.isdir(directory) else []
    if not files:
        print('SKIP  A    no *.scr files in %s (unpack the level scripts there, or pass --scripts DIR); '
              'the shipped-script properties were not run' % directory)
        return
    rng = random.Random(20973)
    seeds = ['zero', 'one'] + [1000 + k for k in range(options['seeds'])]
    load, reloc, bind, find, fresh, chain = Tally(), Tally(), Tally(), Tally(), Tally(), Tally()
    stats = {'runs': 0, 'instructions': 0, 'calls': 0, 'strings': 0, 'nested': 0, 'errors': {}, 'host': [],
             'moved': {}}
    profile = {}
    entries = finished = 0
    never = []
    for filename in files:
        with open(os.path.join(directory, filename), 'rb') as source:
            image = source.read()
        # 256 zero bytes after the file stand for whatever follows the level lump in memory, so
        # that both sides can be followed when a script reads past its own stack top (A6)
        image += bytes(256)
        pair = ScriptPair(orig, image, filename)
        model = pair.model
        a, b = orig.load(), model.load()
        problems = ['scr_load returns %d, model %d' % (a, b)] if a != b else []
        mem = orig.emu.mem
        if mem.u32(orig.base) != orig.base + 0x60 or mem.u32(orig.base + 4) != SCR_CALL_NATIVE \
                or mem.u32(orig.base + 8) != SCR_DEBUG_HOOK:
            problems.append('base, callback or debug word is not the header, 0x141050, 0x1410b0')
        load.add(problems + differences(orig, model, len(image)), filename)
        if a != 0 or b != 0 or model._decoded is None:
            continue
        code = mem.read(orig.base + 0x60 + model.cod, model.dat - model.cod)
        reloc.add([] if code == expected_code(orig, model) else ['relocated code block differs'], filename)
        bind.add(pair.bind(rng), filename)
        publics = model.publics()
        for index, (name, _address) in enumerate(publics):
            for probe in (name, name + b'x', name[:-1], name.upper(), b''):
                a, b = orig.find(probe), model.find_public(probe)
                find.add([] if a == b else ['%r: %r, model %r' % (probe, a, b)], filename)
        saved, saved_model = orig.save(len(image)), model.snapshot()
        model.profile = profile
        for index, (name, _address) in enumerate(publics):
            entries += 1
            done = False
            for seed in seeds:
                orig.restore(saved)
                model.restore(saved_model)
                label = '%s %s seed %s' % (filename, name.decode('latin-1'), seed)
                outcome = pair.run(index, seed, s32(rng.getrandbits(32)), label, fresh, stats)
                done = done or outcome in ('ok', 'bad')
            finished += done
            if not done:
                never.append('%s %s' % (filename, name.decode('latin-1')))
        # one pass over all entry points in random order without restoring anything in between
        orig.restore(saved)
        model.restore(saved_model)
        order = list(range(len(publics)))
        rng.shuffle(order)
        for position, index in enumerate(order):
            label = '%s chained #%d %s' % (filename, position, publics[index][0].decode('latin-1'))
            if pair.run(index, 5000 + position, s32(rng.getrandbits(32)), label, chain, stats) != 'ok':
                break
        model.profile = None
    load.report('A1', 'scr_load on %(n)d shipped scripts: return value, machine structure, header stack '
                'top and the whole data/heap/stack block equal the model\'s (%(bad)d differ)')
    reloc.report('A2', 'relocated code block of %(n)d scripts is byte for byte what the model predicts '
                 '(handler address per opcode, code base added to code operands) (%(bad)d differ)')
    bind.report('A3', 'scr_registerNatives on %(n)d scripts: 19 with one name missing (all other records bound), 0 '
                'with all, every record bound to the listed address (%(bad)d differ)')
    find.report('A4', 'scr_findEntry: %(n)d lookups (every entry-point name and four near misses of '
                'each) give the model\'s error and index (%(bad)d differ)')
    fresh.report('A5', 'scr_interpret from the freshly loaded state: %(n)d runs of ' + str(entries) +
                 ' entry points x ' + str(len(seeds)) + ' result sequences agree in native trace, error, '
                 'result, machine structure and memory (%(bad)d differ; %(endless)d not ended by the '
                 'model within ' + str(BUDGET) + ' instructions, %(host)d host faults)')
    chain.report('A6', 'the same without reloading between entry points (globals and machine words '
                 'carried over, one random order per script): %(n)d runs agree (%(bad)d differ, '
                 '%(endless)d endless, %(host)d host faults)')
    used = sorted(profile)
    print('      coverage: %d scripts, %d entry points (%d compared to the end under at least one '
          'sequence), %d runs, %d model instructions, %d native calls, %d string arguments read on both '
          'sides, %d nested runs through callScript' % (len(files), entries, finished, stats['runs'],
                                                          stats['instructions'], stats['calls'],
                                                          stats['strings'], stats['nested']))
    print('      runs that ended with an error (code: runs): %s' % (', '.join(
        '%d: %d' % item for item in sorted(stats['errors'].items())) or 'none'))
    print('      opcodes executed by the shipped scripts (%d): %s' % (len(used), ' '.join(
        '%02x' % op for op in used)))
    if never:
        print('      entry points that were never compared to the end (%d): the model did not finish them '
              'within the budget under any sequence, or declared a host fault' % len(never))
        for line in never[:None if VERBOSE else 10]:
            note(line)
    if stats['host']:
        print('      host faults declared by the model (%d)%s' % (len(stats['host']), ':' if VERBOSE else
                                                                 ' (-v lists them)'))
        if VERBOSE:
            for line in stats['host']:
                note(line)
    moved = sorted(stats['moved'])
    if moved:
        print('      runs that returned 0 but left the saved stack pointer changed (both sides agree): '
              '%d entry points in %d scripts%s' % (len(moved), len({key.split()[0] for key in moved}),
                                                  ':' if VERBOSE else ' (-v lists them)'))
        if VERBOSE:
            for key in moved:
                note('%s: %+d' % (key, stats['moved'][key]))
    options['script_profile'] = profile


# ---------------------------------------------------------------------------------------------
# Synthetic programs
# ---------------------------------------------------------------------------------------------

DATA_CELLS = 64
STACK_CELLS = 96
NATIVES = (b'trace', b'fail', b'nest')
DATA_END = 4 * DATA_CELLS                     # first heap address
STP = DATA_END + 4 * STACK_CELLS - 4          # stack top after loading
FRAME = STP - 12                              # FRM after the PROC of an entry point without arguments
SLACK = 1024                                  # bytes after the image, the same on both sides: what
#                                               lies behind the script in memory (more than `dat`,
#                                               so the header's stack top can be reached inside it)
WILD = [False]                                # set by a generator that knowingly leaves the machine
INTERESTING = (0, 1, -1, 2, 3, 4, 5, 7, 8, 31, 32, 33, 0x7F, 0x80, 0xFF, 0x100, 0x7FFF, 0x8000, 0xFFFF,
               0x10000, 0x7FFFFFFF, -0x80000000, 0x40000000, -0x40000000, 0x55555555, -0x55555556, -2, -128)


def value(rng):
    roll = rng.random()
    if roll < 0.6:
        return rng.choice(INTERESTING)
    if roll < 0.8:
        return rng.randint(-40, 40)
    return s32(rng.getrandbits(32))


def data_address(rng):
    return 4 * rng.randrange(DATA_CELLS)


def checked_address(rng):
    """An address for the opcodes that test it: mostly legal, sometimes in the gap between heap
    and stack or at/above the stack top (error 5), rarely negative (outside the machine)."""
    roll = rng.random()
    if roll < 0.45:
        return data_address(rng)
    if roll < 0.60:
        return rng.randrange(FRAME - 32, STP, 4)                 # stack
    if roll < 0.80:
        return rng.randrange(DATA_END, FRAME - 64, 4)            # free gap
    if roll < 0.95:
        return rng.choice((STP, STP + 4, STP + 64, 0x7FFFFFFC, DATA_END - 4, DATA_END))
    WILD[0] = True
    return rng.choice((-4, -64, -0x80000000))


def dump(tag):
    """Shows PRI and ALT to the trace native and ends the run."""
    return [('PUSH.alt',), ('PUSH.pri',), ('PUSH.C', tag), ('PUSH.C', 12), ('SYSREQ.C', 0), ('HALT', 0)]


DUMP_BYTES = 4 * 10


def registers(rng):
    return [('CONST.pri', value(rng)), ('CONST.alt', value(rng))]


def directed(name, rng):
    """A program that exercises opcode name with random operands.  Returns the item list for
    ref_amx.assemble; every program starts at offset 0 with PROC."""
    WILD[0] = False
    head = [('PROC',), ('PUSH.C', value(rng)), ('PUSH.C', data_address(rng)), ('PUSH.C', value(rng)),
            ('PUSH.C', data_address(rng))]
    stack = FRAME - 16                                  # STK after the head
    if rng.random() < 0.3:
        head.append(('HEAP', rng.choice((4, 8, 16, 64))))
    if name in ('STACK', 'HEAP') and rng.random() < 0.5:
        # a native call first, left on the stack: the saved stack pointer now differs from the
        # entry value, which shows whether an error exit restores it
        head += [('PUSH.C', 0), ('SYSREQ.C', 0)]
        stack -= 4
    simple_none = ('MOVE.pri MOVE.alt XCHG SHL SHR SSHR SMUL SDIV SDIV.alt UMUL UDIV UDIV.alt ADD SUB SUB.alt '
                   'AND OR XOR NOT NEG INVERT ZERO.pri ZERO.alt SIGN.pri SIGN.alt EQ NEQ LESS LEQ GRTR GEQ '
                   'SLESS SLEQ SGRTR SGEQ INC.pri INC.alt DEC.pri DEC.alt IDXADDR PUSH.pri PUSH.alt POP.pri '
                   'POP.alt PROC').split()
    simple_value = ('CONST.pri CONST.alt SHL.C.pri SHL.C.alt SHR.C.pri SHR.C.alt ADD.C SMUL.C EQ.C.pri '
                    'EQ.C.alt IDXADDR.B ALIGN.pri ALIGN.alt BOUNDS PUSH.C ADDR.pri ADDR.alt').split()
    data_operand = 'LOAD.pri LOAD.alt STOR.pri STOR.alt PUSH ZERO INC DEC'.split()
    data_reference = 'LREF.pri LREF.alt SREF.pri SREF.alt'.split()
    frame_operand = 'LOAD.S.pri LOAD.S.alt STOR.S.pri STOR.S.alt PUSH.S ZERO.S INC.S DEC.S'.split()
    frame_reference = 'LREF.S.pri LREF.S.alt SREF.S.pri SREF.S.alt'.split()
    jumps = 'JUMP JZER JNZ JEQ JNEQ JLESS JLEQ JGRTR JGEQ JSLESS JSLEQ JSGRTR JSGEQ'.split()

    if name in simple_none:
        if name in ('SHL', 'SHR', 'SSHR') and rng.random() < 0.7:
            body = [('CONST.pri', value(rng)), ('CONST.alt', rng.randint(-3, 70))]
        elif rng.random() < 0.3:                        # equal operands
            same = value(rng)
            body = [('CONST.pri', same), ('CONST.alt', same)]
        else:
            body = registers(rng)
        return head + body + [(name,)] + dump(1)
    if name in simple_value:
        operand = value(rng)
        if 'SH' in name or name == 'IDXADDR.B':
            operand = rng.choice((0, 1, 2, 3, 7, 8, 31, 32, 33, 34, 63, -1, value(rng)))
        if name.startswith('ALIGN'):
            operand = rng.choice((0, 1, 2, 3, 4, 5, -1, value(rng)))
        if name == 'BOUNDS' and rng.random() < 0.5:
            return head + [('CONST.pri', rng.randint(-2, 12)), ('CONST.alt', value(rng)),
                           (name, rng.randint(-1, 10))] + dump(1)
        return head + registers(rng) + [(name, operand)] + dump(1)
    if name in data_operand:
        return head + registers(rng) + [(name, data_address(rng))] + dump(1)
    if name in data_reference:
        pointer, target = data_address(rng), data_address(rng)
        return head + [('CONST.pri', target), ('STOR.pri', pointer)] + registers(rng) + [(name, pointer)] + dump(1)
    if name in frame_operand:
        return head + registers(rng) + [(name, rng.randrange(-16, 16, 4))] + dump(1)
    if name in frame_reference:
        offset, target = rng.randrange(-16, 16, 4), data_address(rng)
        return (head + [('CONST.pri', target), ('STOR.S.pri', offset)] + registers(rng) + [(name, offset)]
                + dump(1))
    if name in ('LOAD.I', 'INC.I', 'DEC.I'):
        address = checked_address(rng) if name == 'LOAD.I' else data_address(rng)
        return head + [('CONST.alt', value(rng)), ('CONST.pri', address), (name,)] + dump(1)
    if name == 'STOR.I':
        return head + [('CONST.pri', value(rng)), ('CONST.alt', checked_address(rng)), (name,)] + dump(1)
    if name in ('LODB.I', 'STRB.I'):
        size = rng.choice((1, 1, 2, 2, 4, 4, 0, 3, 8, -1))
        address = checked_address(rng)
        if size in (1, 2) and address >= 0 and rng.random() < 0.7:
            address += rng.randrange(0, 4, size)
        if name == 'LODB.I':
            return head + [('CONST.alt', value(rng)), ('CONST.pri', address), (name, size)] + dump(1)
        return head + [('CONST.pri', value(rng)), ('CONST.alt', address), (name, size)] + dump(1)
    if name in ('LIDX', 'LIDX.B'):
        shift = 2 if name == 'LIDX' else rng.choice((0, 1, 2, 3, 34, 2, 2))
        base, target = data_address(rng), checked_address(rng)
        index = (target - base) >> (shift & 31)
        if base + (index << (shift & 31)) < 0:
            WILD[0] = True
        if rng.random() < 0.25:                           # an index whose shifted value wraps
            index = s32(index + (1 << (32 - (shift & 31))) * rng.randint(1, 3))
        body = [('CONST.pri', index), ('CONST.alt', base)]
        return head + body + ([(name,)] if name == 'LIDX' else [(name, shift)]) + dump(1)
    if name in ('LCTRL', 'SCTRL'):
        index = rng.choice((0, 1, 2, 3, 4, 5, 6, 7, 8, -1, 100))
        if name == 'LCTRL':
            return head + registers(rng) + [(name, index)] + dump(1)
        new = value(rng)
        if index == 2:
            new = rng.choice((DATA_END, DATA_END + 16, 0, 4, -4, FRAME - 100, value(rng)))
        elif index == 4:
            new = rng.randrange(FRAME - 80, FRAME, 4)
        elif index == 5:
            new = rng.choice((0, FRAME, FRAME - 16, data_address(rng), value(rng)))
        elif index == 6:
            new = 'there'
        return (head + [('CONST.alt', value(rng)), ('CONST.pri', new), (name, index)] + dump(1)
                + ['there:'] + dump(2))
    if name == 'PUSH.R':
        return head + registers(rng) + [(name, rng.choice((0, 1, 2, 3, 6)))] + dump(1)
    if name == 'STACK':
        amount = rng.choice((0, 4, 8, 12, 16, -4, -8, -64, -200, -280, -284, -288, -292, -400, 0x1000,
                             0x10000, 0x7FFFFFF0, -0x80000000, 'stp', 'stp', 'top', 'top', 'top'))
        if isinstance(amount, str):
            # to the stack top of the machine (stp) or of the header (stp + dat), give or take
            size = 4 * len(assemble(head + registers(rng) + [(name, 0)] + dump(1))[0])
            dat = 0x40 + 24 * (1 + len(NATIVES)) + size
            amount = (STP if amount == 'stp' else STP + dat) - stack + rng.choice((-4, 0, 4, 8))
        return head + registers(rng) + [(name, amount)] + dump(1)
    if name == 'HEAP':
        amount = rng.choice((0, 4, 8, 64, 200, 240, 244, 248, 252, 256, 400, -4, -DATA_END, -DATA_END - 4,
                             -DATA_END + 4, 0x7FFFFF00, -0x80000000))
        return head + registers(rng) + [(name, amount)] + dump(1)
    if name in jumps:
        if rng.random() < 0.4:
            same = value(rng)
            body = [('CONST.pri', same), ('CONST.alt', same)]
        else:
            body = registers(rng)
        return head + body + [(name, 'there')] + dump(1) + ['there:'] + dump(2)
    if name == 'JREL':
        return head + registers(rng) + [(name, rng.choice((0, DUMP_BYTES)))] + dump(1) + dump(2)
    if name in ('JUMP.pri', 'CALL.pri'):
        return (head + [('CONST.alt', value(rng)), ('CONST.pri', 'there'), (name,)] + dump(1)
                + ['there:'] + dump(2))
    if name in ('CALL', 'RET', 'RETN'):
        # a function call with two arguments; the callee returns with RETN or RET
        callee = [('PROC',), ('LOAD.S.pri', 12), ('LOAD.S.alt', 16), ('ADD',)]
        if name == 'RET' or (name == 'CALL' and rng.random() < 0.5):
            callee.append(('RET',))
        else:
            callee.append(('RETN',))
        program = head + [('PUSH.C', value(rng)), ('PUSH.C', value(rng)), ('PUSH.C', 8), ('CALL', 'function')]
        ending = rng.random()
        if ending < 0.4:
            program += dump(1)
        elif ending < 0.7:                                # the entry point itself returns
            program += [('LCTRL', 5), ('SCTRL', 4), ('CONST.pri', value(rng)), (rng.choice(('RET', 'RETN')),)]
        else:                                             # hand-made frame: frame, return address, size
            target = rng.choice((0, 'there'))
            program += [('PUSH.C', rng.choice((0, 4, 8))), ('PUSH.C', target), ('PUSH.C', value(rng)),
                        ('CONST.pri', value(rng)), (rng.choice(('RET', 'RETN')),)] + dump(3)
            program += ['there:'] + dump(4)
        return program + ['function:'] + callee
    if name in ('SYSREQ.pri', 'SYSREQ.C'):
        index = rng.randrange(len(NATIVES))
        arguments = [value(rng) for _ in range(rng.randint(0, 3))]
        if index == 2:                                    # nest(entry index, arguments...)
            arguments = [rng.choice((0, 1, 1, 2, 3, -1, -3, 7))] + arguments[:2]
        elif index == 1:                                  # fail(error code)
            arguments = [rng.choice((0, 0, 1, 5, 27, -1, value(rng)))]
        elif rng.random() < 0.5:                          # trace(a string address, ...)
            arguments = [rng.choice((0, 16, 32, 48, 64, 96, 128, data_address(rng)))] + arguments[:1]
        body = [('PUSH.C', a) for a in reversed(arguments)] + [('PUSH.C', 4 * len(arguments))]
        if name == 'SYSREQ.pri':
            body += [('CONST.alt', value(rng)), ('CONST.pri', index), (name,)]
        else:
            body += registers(rng) + [(name, index)]
        return head + body + [('STACK', 4 * len(arguments) + 4)] + dump(1)
    if name in ('SWITCH', 'CASETBL'):
        count = rng.choice((0, 1, 2, 3, 5))
        values = [rng.choice((0, 1, 2, 3, -1, 100, 0x7FFFFFFF)) for _ in range(count)]
        selector = rng.choice(values + [0, 1, 2, 9])
        targets = ['case%d' % rng.randrange(4) for _ in range(count)]
        program = head + [('CONST.alt', value(rng)), ('CONST.pri', selector), ('SWITCH', 'table')] + dump(9)
        program += ['table:', ('CASETBL', 'case%d' % rng.randrange(4), list(zip(values, targets)))]
        for case in range(4):
            program += ['case%d:' % case] + dump(10 + case)
        return program
    if name in ('FILE', 'LINE', 'SYMBOL', 'SRANGE'):
        text = bytes(rng.choice(b'abcxyz_09') for _ in range(rng.randint(0, 9)))
        record = {'FILE': ('FILE', value(rng), text), 'LINE': ('LINE', value(rng), value(rng)),
                  'SYMBOL': ('SYMBOL', value(rng), value(rng), text),
                  'SRANGE': ('SRANGE', value(rng), value(rng))}[name]
        extra = [('LINE', value(rng), value(rng))] if rng.random() < 0.3 else []
        return head + registers(rng) + [record] + dump(1) + extra
    if name in ('MOVS', 'CMPS', 'FILL'):
        count = rng.choice((0, 1, 2, 3, 4, 5, 8, 15, 16, 17, 31, 32, 33, 40, 64, 96, 100))
        limit = 4 * DATA_CELLS - count
        if name == 'FILL':
            return head + [('CONST.pri', value(rng)), ('CONST.alt', rng.randrange(0, limit + 1, 4)),
                           (name, count)] + dump(1)
        step = rng.choice((1, 4, 16))
        source, target = rng.randrange(0, limit + 1, step), rng.randrange(0, limit + 1, step)
        if rng.random() < 0.3:                            # overlapping or identical blocks
            target = min(limit - limit % step, max(0, source + step * rng.randint(-3, 3)))
        body = [('CONST.pri', source), ('CONST.alt', target)]
        if name == 'CMPS' and rng.random() < 0.5:         # make the blocks equal first
            body += [('MOVS', count)]
        return head + body + [(name, count)] + dump(1)
    if name == 'HALT':
        return head + registers(rng) + [(name, rng.choice((0, 1, 5, 12, 27, -1, value(rng))))]
    raise KeyError(name)


def fuzz(rng):
    """A straight-line program of random instructions that mostly stay inside the machine,
    with forward jumps, calls of the trace native and a normal return or HALT at the end."""
    program = [('PROC',)] + [('PUSH.C', value(rng)) for _ in range(4)]
    depth, labels = 4, 0
    pending = []
    plain = ('MOVE.pri MOVE.alt XCHG SHL SHR SSHR SMUL SDIV SDIV.alt UMUL UDIV UDIV.alt ADD SUB SUB.alt AND OR '
             'XOR NOT NEG INVERT ZERO.pri ZERO.alt SIGN.pri SIGN.alt EQ NEQ LESS LEQ GRTR GEQ SLESS SLEQ SGRTR '
             'SGEQ INC.pri INC.alt DEC.pri DEC.alt').split()
    immediate = 'CONST.pri CONST.alt ADD.C SMUL.C EQ.C.pri EQ.C.alt ADDR.pri ADDR.alt'.split()
    shifts = 'SHL.C.pri SHL.C.alt SHR.C.pri SHR.C.alt'.split()
    memory = 'LOAD.pri LOAD.alt STOR.pri STOR.alt ZERO INC DEC'.split()
    frame = 'LOAD.S.pri LOAD.S.alt STOR.S.pri STOR.S.alt ZERO.S INC.S DEC.S'.split()
    jumps = 'JUMP JZER JNZ JEQ JNEQ JLESS JLEQ JGRTR JGEQ JSLESS JSLEQ JSGRTR JSGEQ'.split()
    for _ in range(rng.randint(4, 40)):
        roll = rng.random()
        if roll < 0.30:
            program.append((rng.choice(plain),))
        elif roll < 0.45:
            program.append((rng.choice(immediate), value(rng)))
        elif roll < 0.50:
            program.append((rng.choice(shifts), rng.randint(0, 40)))
        elif roll < 0.62:
            program.append((rng.choice(memory), data_address(rng)))
        elif roll < 0.72:
            program.append((rng.choice(frame), rng.randrange(-16, 0, 4)))
        elif roll < 0.78 and depth < 24:
            program.append(rng.choice((('PUSH.pri',), ('PUSH.alt',), ('PUSH.C', value(rng)),
                                       ('PUSH', data_address(rng)), ('PUSH.S', rng.randrange(-16, 0, 4)))))
            depth += 1
        elif roll < 0.82 and depth > 4:
            program.append((rng.choice(('POP.pri', 'POP.alt')),))
            depth -= 1
        elif roll < 0.87:
            program += [('CONST.pri', checked_address(rng)), ('LOAD.I',)]
        elif roll < 0.90:
            program += [('CONST.alt', checked_address(rng)), ('STOR.I',)]
        elif roll < 0.93:
            program += [('CONST.alt', data_address(rng)), ('CONST.pri', rng.randint(-2, 6)),
                        (rng.choice(('LIDX', 'IDXADDR')),)]
        elif roll < 0.96:
            program += [('PUSH.alt',), ('PUSH.pri',), ('PUSH.C', 8), ('SYSREQ.C', 0), ('STACK', 12)]
        elif roll < 0.98:
            program.append(('BOUNDS', rng.choice((0, 1, 5, 100, 0x7FFFFFFF))))
        else:
            label = 'skip%d' % labels
            labels += 1
            program.append((rng.choice(jumps), label))
            pending.append((label, rng.randint(1, 6)))
        for entry in pending[:]:
            if rng.random() < 0.35:
                program.append(entry[0] + ':')
                pending.remove(entry)
    program += [label + ':' for label, _ in pending]
    if rng.random() < 0.5:
        program += dump(1)
    else:
        program += [('PUSH.alt',), ('PUSH.pri',), ('PUSH.C', 8), ('SYSREQ.C', 0), ('MOVE.pri',),
                    ('LCTRL', 5), ('SCTRL', 4), ('MOVE.pri',), ('RETN',)]
    return program


def synthetic_data(rng):
    """Initial data: packed and unpacked strings, legal addresses, and arbitrary cells."""
    cells = []
    while len(cells) < DATA_CELLS:
        roll = rng.random()
        if roll < 0.25:
            cells.append(data_address(rng))
        elif roll < 0.40:                                 # packed string
            text = bytes(rng.randrange(1, 256) for _ in range(rng.randint(1, 9))) + b'\0'
            text += b'\0' * (-len(text) % 4)
            cells += [int.from_bytes(text[i:i + 4], 'big') for i in range(0, len(text), 4)]
        elif roll < 0.50:                                 # unpacked string
            cells += [rng.randrange(1, 256) for _ in range(rng.randint(1, 5))] + [0]
        else:
            cells.append(value(rng))
    return cells[:DATA_CELLS]


class SyntheticPair:
    """A synthetic image on both sides, with the natives trace, fail and nest."""

    def __init__(self, orig, image, shift=0):
        self.orig, self.image = orig, image
        self.model = Machine(image)
        orig.place(image, shift)
        self.o, self.m = Side(), Side()
        self.depth = 0
        orig.on_native = self._orig_native

    def load(self):
        """Loads and binds on both sides.  Returns the list of problems (the model may raise
        HostFault)."""
        orig, model = self.orig, self.model
        a = orig.load()
        try:
            b = model.load()
        except HostFault as fault:
            if a != 0:
                return ['scr_load returns %d, the model raises HostFault: %s' % (a, fault)]
            raise
        problems = ['scr_load returns %d, model %d' % (a, b)] if a != b else []
        problems += differences(orig, model, len(self.image))
        if model._parsed and not problems:
            names = model.native_names()
            a = orig.register([(name, orig.stubs + 8 * NATIVES.index(name)) for name in names if name in NATIVES])
            b = model.register({b'trace': self._model_trace, b'fail': self._model_fail, b'nest': self._model_nest})
            if a != b:
                problems.append('scr_registerNatives returns %d, model %d' % (a, b))
            if model._decoded is not None:
                code = orig.emu.mem.read(orig.base + 0x60 + model.cod, model.dat - model.cod)
                if code != expected_code(orig, model):
                    problems.append('relocated code block differs from the model\'s prediction')
        return problems

    # original side: slot 0 trace, 1 fail, 2 nest
    def _orig_native(self, slot, args, _params):
        side, orig = self.o, self.orig
        if slot == 0:
            side.trace.append((b'trace', tuple(args), tuple(orig.string_at(a, len(self.image)) for a in args)))
            return side.returns.next()
        if slot == 1:
            side.trace.append((b'fail', tuple(args)))
            orig.nested(SCR_RAISE_ERROR, orig.base, args[0] if args else 0)
            return side.returns.next()
        side.trace.append((b'nest', tuple(args)))
        if orig.depth >= MAX_DEPTH or not args:
            return side.returns.next()
        sentinel = 0xC3C30000 + len(side.trace)
        error, cell = orig.interpret(args[0], args[1:], nested_pri(side.trace), sentinel, nested=True)
        side.trace.append((b'nested result', error, cell == sentinel, cell))
        return 0 if cell == sentinel else s32(cell)

    # model side
    def _model_trace(self, machine, args):
        side = self.m
        side.trace.append((b'trace', tuple(args), tuple(model_string(machine, a) for a in args)))
        return side.returns.next()

    def _model_fail(self, machine, args):
        side = self.m
        side.trace.append((b'fail', tuple(args)))
        machine.raise_error(args[0] if args else 0)
        return side.returns.next()

    def _model_nest(self, machine, args):
        side = self.m
        side.trace.append((b'nest', tuple(args)))
        if self.depth >= MAX_DEPTH or not args:
            return side.returns.next()
        sentinel = 0xC3C30000 + len(side.trace)
        self.depth += 1
        try:
            error, result = machine.execute(args[0], args[1:], pri=nested_pri(side.trace))
        finally:
            self.depth -= 1
        side.trace.append((b'nested result', error, result is None, sentinel if result is None else result & M32))
        return 0 if result is None else result

    def run(self, index, params, pri, seed):
        """Runs on both sides.  Returns ('ok' | 'bad' | 'host' | 'endless', problems)."""
        orig, model = self.orig, self.model
        self.m.begin(seed)
        self.depth = 0
        model.budget = 20000
        try:
            m_error, m_result = model.execute(index, params, pri=pri)
        except HostFault as fault:
            return 'host', [str(fault)]
        except Limit:
            return 'endless', []
        except RecursionError:
            return 'endless', []
        self.o.begin(seed)
        sentinel = 0xA5A5A5A5
        try:
            o_error, o_cell = orig.interpret(index, params, pri, sentinel, max_steps=4000000)
        except EmuError as stop:
            return 'bad', ['the emulator stopped: %s' % stop]
        problems = []
        if self.o.trace != self.m.trace:
            problems.append('native trace %r, model %r' % (self.o.trace[-3:], self.m.trace[-3:]))
        if o_error != m_error:
            problems.append('error %d, model %d' % (o_error, m_error))
        if o_cell != (sentinel if m_result is None else m_result & M32):
            problems.append('result cell 0x%x, model %r' % (o_cell, m_result))
        problems += differences(orig, model, len(self.image))
        return ('bad' if problems else 'ok'), problems


def synthetic_image(rng, program, extra_publics=(), **keywords):
    """The image of a program with entry point main, followed by SLACK bytes.  Half of the
    images have random words in the heap and stack room and in the slack (the file has
    zeroes there, but nothing in the machine relies on that), except for a zero tail that
    ends any string read."""
    cells, labels = assemble(program)
    publics = [('main', 0)] + [(name, labels[label]) for name, label in extra_publics]
    image = bytearray(build_image(cells, synthetic_data(rng), publics, NATIVES, STACK_CELLS, **keywords))
    room = len(image) - 4 * STACK_CELLS
    image += bytes(SLACK)
    if rng.random() < 0.5:
        image[room:len(image) - 16] = bytes(rng.getrandbits(8) for _ in range(len(image) - 16 - room))
    return bytes(image), labels


def run_program(orig, rng, program, tally, label, profile=None, runs=None, shift=None, strict=False,
                **keywords):
    """Assembles, loads and runs a synthetic program on both sides; adds the outcome to tally.
    strict: the program stays inside the machine by construction, so a HostFault from the
    model is a failure and not a skipped case."""
    image, _labels = synthetic_image(rng, program, **keywords)
    pair = SyntheticPair(orig, image, rng.choice((0, 4, 8, 12)) if shift is None else shift)
    try:
        problems = pair.load()
    except HostFault as fault:
        if strict:
            tally.add(['the model raises HostFault at load: %s' % fault], label)
            return 'bad'
        tally.host += 1
        return 'host'
    if problems:
        tally.add(problems, label + ' (load)')
        return 'bad'
    pair.model.profile = profile
    outcome = 'ok'
    for index, params in (runs or [(0, ())]):
        outcome, problems = pair.run(index, params, value(rng), rng.getrandbits(32))
        if outcome == 'host' and strict:
            tally.add(['the model raises HostFault: %s' % problems[0]], label)
            return 'bad'
        if outcome == 'host':
            tally.host += 1
            break
        if outcome == 'endless':
            tally.endless += 1
            break
        tally.add(problems, label)
        if outcome == 'bad':
            break
    return outcome


def group_opcodes(orig, options):
    rng = random.Random(0xA3)
    profile = {}
    per_opcode = max(1, int(60 * options['scale']))
    total, weak = Tally(), []
    for number in range(1, len(OPCODES)):
        name = OPCODES[number][0]
        tally = Tally()
        for case in range(per_opcode):
            program = directed(name, rng)
            outcome = run_program(orig, rng, program, tally, '%s #%d' % (name, case), profile,
                                  strict=not WILD[0])
            if VERBOSE and outcome == 'bad':
                note('program: %r' % (program,))
        total.cases += tally.cases
        total.bad += tally.bad
        total.host += tally.host
        total.endless += tally.endless
        total.examples += tally.examples[:1]
        if tally.cases < per_opcode // 3:
            weak.append('%s (%d of %d)' % (name, tally.cases, per_opcode))
    total.report('B1', 'directed programs, ' + str(per_opcode) + ' per opcode for the 130 opcodes 0x01-0x82 '
                 'with random operands: %(n)d compared runs agree in trace, error, result, machine '
                 'structure and memory (%(bad)d differ; %(host)d host faults, all in programs made to '
                 'leave the machine; %(endless)d endless)')
    if weak:
        note('opcodes with fewer than a third of their programs compared: ' + ', '.join(weak))
    # opcode 0 cannot be loaded; put its handler into a relocated cell by hand
    tally = Tally()
    for case in range(max(1, int(8 * options['scale']))):
        program = [('PROC',), ('PUSH.C', value(rng)), ('CONST.pri', value(rng)), ('ZERO.alt',)] + dump(1)
        image, _ = synthetic_image(rng, program)
        pair = SyntheticPair(orig, image)
        problems = pair.load()
        offset = 4 * 5                                   # the ZERO.alt cell
        orig.emu.mem.w32(orig.base + 0x60 + pair.model.cod + offset, orig.handlers[0])
        pair.model._decoded[offset] = (0, None, offset + 4)
        pair.model.profile = profile
        outcome, more = pair.run(0, (), 0, case)
        tally.add(problems + more + ([] if pair.model.error == 0 and outcome == 'ok' else [outcome]), 'NONE #%d' % case)
    tally.report('B2', 'opcode 0 (handler 0x13eea8, reachable only by putting its address into loaded '
                 'code): %(n)d runs return 6 and restore the stack pointer as the model does (%(bad)d differ)')
    # the address check is signed: a negative address is not refused.  The value read comes
    # from the script's own relocated code, so only the absence of error 5 is compared.
    tally = Tally()
    for name, operand in (('LOAD.I', None), ('LODB.I', 4), ('LODB.I', 1), ('LIDX', None), ('LIDX.B', 1)):
        for address in (-4, -8, -16, -64):
            body = [('CONST.alt', 0), ('CONST.pri', address >> 2 if name == 'LIDX' else
                                       address >> 1 if name == 'LIDX.B' else address)]
            program = [('PROC',)] + body + [(name,) if operand is None else (name, operand), ('HALT', 0)]
            image, _ = synthetic_image(rng, program)
            pair = SyntheticPair(orig, image)
            problems = pair.load()
            try:
                pair.model.execute(0)
                problems.append('the model does not raise HostFault')
            except HostFault:
                pass
            error, _cell = orig.interpret(0, (), 0, 1)
            if error != 0:
                problems.append('the original returns %d' % error)
            tally.add(problems, '%s at %d' % (name, address))
    tally.report('B3', 'a negative address passes the address check of LOAD.I, LODB.I, LIDX and LIDX.B: '
                 '%(n)d runs of the original go on to HALT instead of returning 5; the model raises '
                 'HostFault (%(bad)d differ)')
    tally = Tally()
    for case in range(max(1, int(3000 * options['scale']))):
        program = fuzz(rng)
        outcome = run_program(orig, rng, program, tally, 'random program #%d' % case, profile)
        if VERBOSE and outcome == 'bad':
            note('program: %r' % (program,))
    tally.report('B4', 'random straight-line programs with forward jumps (4 to 40 instructions): %(n)d '
                 'compared runs agree (%(bad)d differ; %(host)d host faults, %(endless)d endless)')
    executed = sorted(profile)
    missing = [OPCODES[number][0] for number in range(len(OPCODES)) if number not in profile]
    print('      opcodes executed by the synthetic programs in compared or attempted runs: %d of %d%s'
          % (len(executed), len(OPCODES), '' if not missing else '; not executed here: ' + ' '.join(missing)
             + (' (C8 does)' if missing == ['CASETBL'] else '')))
    options['synthetic_profile'] = profile


def group_entry(orig, options):
    rng = random.Random(0xE7)
    scale = options['scale']
    # arguments
    tally = Tally()
    for case in range(max(1, int(150 * scale))):
        count = rng.randint(0, 5)
        program = [('PROC',)]
        for k in range(count + 1):                        # the size cell and every argument
            program += [('LOAD.S.pri', 8 + 4 * k), ('PUSH.pri',)]
        program += [('PUSH.C', 4 * (count + 1)), ('SYSREQ.C', 0), ('STACK', 4 * (count + 2)),
                    ('LOAD.S.pri', 12 if count else 8), (rng.choice(('RETN', 'RET')),)]
        first, second = (tuple(value(rng) for _ in range(count)) for _ in range(2))
        run_program(orig, rng, program, tally, 'arguments #%d' % case, runs=[(0, first), (0, second)])
    tally.report('C1', 'entry with 0 to 5 arguments (pushed above an argument size and a zero return '
                 'address) and return by RETN or RET: %(n)d runs agree (%(bad)d differ, %(host)d host faults)')
    # initial PRI
    tally = Tally()
    for case in range(max(1, int(60 * scale))):
        program = rng.choice(([('HALT', 0)], [('PROC',), ('RETN',)], [('PROC',)] + dump(1)))
        run_program(orig, rng, program, tally, 'initial PRI #%d' % case)
    tally.report('C2', 'PRI is not initialised on entry: with a chosen word in the frame slot the '
                 'original reads it from, %(n)d runs return or show that word as the model does with '
                 'pri= (%(bad)d differ); ALT and FRM start at 0')
    # entry index
    tally = Tally()
    for case in range(max(1, int(120 * scale))):
        program = [('PROC',), ('CONST.pri', 'second'), ('CONST.pri', 1)] + dump(1) + ['second:', ('PROC',),
                                                                                       ('CONST.pri', 2)] + dump(2)
        start = rng.choice((-1, -1, 0, 'second', -7))
        cells, labels = assemble(program)
        image = build_image(cells, synthetic_data(rng), [('main', 0), ('second', labels['second'])], NATIVES,
                            STACK_CELLS, start=labels.get(start, start))
        if rng.random() < 0.3:
            # entry index -2 is not refused: the address is read two records before the table.
            # Point the table 48 bytes past the operand cell of CONST.pri second (code offset 8).
            image = bytearray(image)
            cod, = struct.unpack_from('<i', image, 0x60 + 0x0C)
            struct.pack_into('<i', image, 0x60 + 0x24, cod + 8 + 48)
            image = bytes(image)
            indexes = [-2]
        else:
            indexes = [rng.choice((-1, 0, 1, 2, 3, 100, -3, -4, -100, 0x7FFF, -0x8000, 0x10000, -0x80000000))
                       for _ in range(3)]
        pair = SyntheticPair(orig, image)
        problems = pair.load()
        for index in indexes:
            outcome, more = pair.run(index, (), value(rng), case)
            if outcome == 'host':
                tally.host += 1
                continue
            tally.add(problems + more, 'entry index %d #%d' % (index, case))
    tally.report('C3', 'entry index: -1 runs the header\'s start address or gives 20 when that is negative, '
                 '0..count-1 run, others give 20, and -2 is taken as a table index: %(n)d runs agree '
                 '(%(bad)d differ, %(host)d host faults)')
    # machine words changed before the run
    tally = Tally()
    for case in range(max(1, int(200 * scale))):
        program = [('PROC',), ('PUSH.C', value(rng)), ('HEAP', rng.choice((0, 8, 64)))] + registers(rng) + dump(1)
        image, _ = synthetic_image(rng, program)
        pair = SyntheticPair(orig, image)
        problems = pair.load()
        mem, base, model = orig.emu.mem, orig.base, pair.model
        what = rng.choice(('callback', 'reloc', 'browse', 'stk', 'stk', 'stk', 'hea', 'hea', 'both'))
        if what == 'callback':
            mem.w32(base + 4, 0)
            model.callback = None
        elif what == 'reloc':
            mem.w32(base + 0x20, mem.u32(base + 0x20) & ~0x8000 | 0x4000)
            model.flags = model.flags & ~0x8000 | 0x4000
        elif what == 'browse':
            mem.w32(base + 0x20, mem.u32(base + 0x20) | 0x4000 | 0x10000)
            model.flags |= 0x4000 | 0x10000
        if what in ('stk', 'both'):
            new = rng.choice((DATA_END + 0x40 + 8, DATA_END + 0x40 + 4, DATA_END + 0x40, DATA_END + 0x48 + 4,
                              DATA_END + 0x4C + 4, STP - 4, STP - 64, model.hdr_stp, model.hdr_stp + 4,
                              model.hdr_stp + 400, 0x7FFFFFFC, STP))
            mem.w32(base + 0x18, new)
            model.stk = new
        if what in ('hea', 'both'):
            new = rng.choice((0, 4, -4, -0x80000000, DATA_END + 8, STP - 0x40 - 8, STP - 0x40 - 4,
                              STP - 0x40 - 12, STP, 0x7FFFFFC0))
            mem.w32(base + 0x14, new & M32)
            model.hea = new
        params = tuple(value(rng) for _ in range(rng.randint(0, 2)))
        outcome, more = pair.run(0, params, value(rng), case)
        if outcome == 'host':
            tally.host += 1
            continue
        tally.add(problems + more, 'changed %s #%d' % (what, case))
    tally.report('C4', 'entry checks with changed machine words (no callback: 9; not relocated: 22; stack '
                 'pointer above the header\'s stack top: 7; heap top negative: 8; less than 0x40 bytes '
                 'free: 3 after the arguments and the two entry cells were written), in memory that is '
                 'not zero: %(n)d runs agree (%(bad)d differ, %(host)d host faults)')
    # nested runs and errors raised by natives
    tally = Tally()
    for case in range(max(1, int(250 * scale))):
        program = [('PROC',)]
        for _ in range(rng.randint(1, 3)):
            arguments = [rng.choice((0, 1, 1, 2, 2, 5, -2))] + [value(rng) for _ in range(rng.randint(0, 2))]
            program += [('PUSH.C', a) for a in reversed(arguments)] + [('PUSH.C', 4 * len(arguments)),
                                                                      ('SYSREQ.C', 2),
                                                                      ('STACK', 4 * len(arguments) + 4)]
        program += [('PUSH.pri',), ('PUSH.C', 4), ('SYSREQ.C', 0), ('STACK', 8), ('RETN',)]
        program += ['one:', ('PROC',), ('LOAD.S.pri', 8), ('PUSH.pri',), ('PUSH.C', 4), ('SYSREQ.C', 0),
                    ('STACK', 8), ('INC', 0), ('LOAD.pri', 0), ('RETN',)]
        program += ['two:', ('PROC',), ('PUSH.C', rng.choice((0, 0, 3, 27))), ('PUSH.C', 4), ('SYSREQ.C', 1),
                    ('STACK', 8), ('CONST.pri', value(rng)), rng.choice((('RETN',), ('HALT', value(rng)),
                                                                        ('HEAP', 0x10000)))]
        if rng.random() < 0.3:                            # self-recursion until the stack check stops it
            program += ['deep:', ('PROC',), ('PUSH.C', 3), ('PUSH.C', 4), ('SYSREQ.C', 2), ('STACK', 8), ('RETN',)]
            extra = [('a', 'one'), ('b', 'two'), ('c', 'deep')]
        else:
            extra = [('a', 'one'), ('b', 'two')]
        run_program(orig, rng, program, tally, 'nested #%d' % case, extra_publics=extra,
                    runs=[(0, ()), (rng.randrange(len(extra) + 1), (value(rng),))])
    tally.report('C5', 'natives that start a nested run on the same machine (down to ' + str(MAX_DEPTH) +
                 ' levels) or set the error word: %(n)d runs agree, including the words the nested run '
                 'leaves in the machine structure (%(bad)d differ, %(host)d host faults, %(endless)d endless)')
    # the game's way in
    tally = Tally()
    for case in range(max(1, int(80 * scale))):
        program = [('PROC',), ('CONST.pri', value(rng)), ('RETN',),
                   'halt:', ('PROC',), ('CONST.pri', value(rng)), ('HALT', rng.choice((0, 4, 27, -1))),
                   'fail:', ('PROC',), ('CONST.pri', value(rng)), ('ZERO.alt',), ('SDIV',), ('RETN',),
                   'keep:', ('PROC',), ('RETN',)]
        image, _ = synthetic_image(rng, program, extra_publics=[('halt', 'halt'), ('fail', 'fail'),
                                                               ('keep', 'keep')])
        pair = SyntheticPair(orig, image)
        problems = pair.load()
        mem = orig.emu.mem
        for name in (b'main', b'halt', b'fail', b'keep', b'nobody', b'Main', b''):
            pri = value(rng)
            mem.write(orig.buffer, name + bytes(32))
            mem.w32(orig.SP - 0x20 - 0x80 + 4, pri & M32)     # PRI slot of the frame below script_runByName's
            a = orig.call(SCRIPT_RUN_BY_NAME, orig.buffer)
            b = pair.model.call(name, pri=pri)
            if a != b:
                problems.append('%r returns %d, model %d' % (name, a, b))
            problems += differences(orig, pair.model, len(image))
        tally.add(problems, 'script_runByName #%d' % case)
    tally.report('C6', 'script_runByName 0x1ed694 against Machine.call: -1 for an unknown name, the result '
                 'of RETN or HALT, 0 after an error, the uninitialised PRI for a function that sets '
                 'none: %(n)d images, seven names each, agree (%(bad)d differ)')
    # the claim behind HostFault for an unbound native
    program = [('PROC',), ('PUSH.C', 0), ('SYSREQ.C', 0), ('RETN',)]
    cells, _ = assemble(program)
    image = build_image(cells, [0] * 8, [('main', 0)], [b'nobody'], STACK_CELLS)
    pair = SyntheticPair(orig, image)
    pair.load()
    stopped = None
    try:
        orig.interpret(0, (), 0, 1)
    except EmuError as stop:
        stopped = str(stop)
    try:
        pair.model.execute(0)
        fault = False
    except HostFault:
        fault = True
    check('C7', fault and stopped is not None and '0x00000000' in stopped,
          'a native that was never bound: the original jumps to address 0 (the emulator stops there), '
          'the model raises HostFault')
    # the claim behind HostFault for an executed case table
    program = [('PROC',), ('CASETBL', 'end', [(1, 'end'), (2, 'end'), (3, 'end'), (4, 'end')]), 'end:', ('HALT', 0)]
    image, _ = synthetic_image(rng, program)
    pair = SyntheticPair(orig, image)
    pair.load()
    stopped = None
    try:
        orig.interpret(0, (), 0, 1)
    except EmuError as stop:
        stopped = str(stop)
    pair.model.profile = options.setdefault('synthetic_profile', {})
    try:
        pair.model.execute(0)
        fault = False
    except HostFault:
        fault = True
    check('C8', fault and stopped is not None and '0x00000004' in stopped,
          'CASETBL reached by execution: its handler goes on to use the record count (here 4) as a '
          'handler address (the emulator stops at address 4), the model raises HostFault')


def group_loader(orig, options):
    rng = random.Random(0x10AD)
    scale = options['scale']

    def program_cells():
        return assemble(rng.choice((fuzz(rng), directed(rng.choice(('SWITCH', 'CALL', 'JSLESS', 'LINE',
                                                                 'SYMBOL', 'FILE', 'SYSREQ.C')), rng))))[0]

    # header checks
    tally = Tally()
    for case in range(max(1, int(300 * scale))):
        image = bytearray(build_image(program_cells(), synthetic_data(rng), [('main', 0)], NATIVES, STACK_CELLS))
        if rng.random() < 0.5:                            # heap and stack room not zero in the file
            image[-4 * STACK_CELLS:] = bytes(rng.getrandbits(8) for _ in range(4 * STACK_CELLS))
        field = rng.choice(('magic', 'record', 'version', 'file version', 'stp', 'flags', 'none', 'struct'))
        if field == 'magic':
            struct.pack_into('<H', image, 0x64, rng.choice((0xF1E1, 0xE0F1, 0, 0xF1E0)))
        elif field == 'record':
            struct.pack_into('<H', image, 0x6A, rng.choice((0x14, 0x19, 0, 0x18)))
        elif field == 'version':
            image[0x67] = rng.choice((0, 1, 2, 3, 4, 5, 0x7F, 0x80, 0xFF))
        elif field == 'file version':
            image[0x66] = rng.choice((0, 1, 2, 4, 5, 0xFF))
        elif field == 'stp':
            struct.pack_into('<i', image, 0x78, rng.choice((0, -1, -4, 0x7FFFFFFF, -0x80000000)))
        elif field == 'flags':
            struct.pack_into('<H', image, 0x68, rng.choice((1, 2, 3, 8, 0x10, 0x8000, 0xFFFB, 0xFFFA)))
        elif field == 'struct':                           # words of the machine structure not zero in the file
            struct.pack_into('<I', image, 0x20, rng.choice((0x2000, 0x8000, 0x4000, 1)))
        pair = SyntheticPair(orig, bytes(image))
        try:
            problems = pair.load()
            a, b = orig.load(), pair.model.load()         # loading twice changes nothing more
            problems += ['second scr_load returns %d, model %d' % (a, b)] if a != b else []
            problems += differences(orig, pair.model, len(image))
            outcome, more = pair.run(0, (), value(rng), case)
        except HostFault:
            tally.host += 1
            continue
        if outcome == 'host':
            tally.host += 1
            continue
        tally.add(problems + more, 'header %s #%d' % (field, case))
    tally.report('D1', 'header checks of scr_load (magic, record size, required version, stack top, flag '
                 'bit 0, a second load) and the run that follows: %(n)d images agree (%(bad)d differ, '
                 '%(host)d host faults)')
    # code the relocator refuses
    tally = Tally()
    for case in range(max(1, int(300 * scale))):
        cells = program_cells()
        model = Machine(build_image(cells, [0] * DATA_CELLS, [('main', 0)], NATIVES, STACK_CELLS))
        model.load()
        opcode_cells = sorted(model._decoded)
        victim = rng.choice(opcode_cells) // 4
        cells[victim] = rng.choice((0, 0x83, 0x84, 0xFF, 0x100, 0x101, 0x7FFFFFFF, -1, -2, -0x40, 0x1000))
        image = build_image(cells, synthetic_data(rng), [('main', 0)], NATIVES, STACK_CELLS)
        pair = SyntheticPair(orig, image)
        try:
            problems = pair.load()
        except HostFault:
            tally.host += 1
            continue
        mem = orig.emu.mem
        relocated = bool(mem.u32(orig.base + 0x20) & 0x8000)
        # the code block: relocated up to the bad cell, which holds the word found at its
        # place in the handler table when it is below 0x100, and is untouched otherwise
        expected = bytearray(expected_code(orig, pair.model, model._decoded, 4 * victim))
        if cells[victim] < 0x100:
            struct.pack_into('<I', expected, 4 * victim, mem.u32((HANDLER_TABLE + 4 * cells[victim]) & M32))
        if mem.read(orig.base + 0x60 + pair.model.cod, len(expected)) != bytes(expected):
            problems.append('code block after the refused pass is not as described')
        outcome, more = pair.run(0, (), value(rng), case)
        tally.add(problems + more + ([] if not relocated and pair.model.flags & 0x8000 == 0 else ['relocated']),
                  'bad opcode %d #%d' % (cells[victim], case))
    tally.report('D2', 'a cell that is not an opcode 1..0x82 where the relocator expects one: scr_load '
                 'still returns 0, the code is not marked relocated, the cells before it are relocated, '
                 'the cell itself holds a handler-table word if it was below 0x100, the debug words '
                 'keep what the pass had stored, and scr_interpret returns 22: %(n)d images agree '
                 '(%(bad)d differ, %(host)d host faults)')
    # compact encoding
    tally = Tally()
    for case in range(max(1, int(300 * scale))):
        program = rng.choice((fuzz(rng), directed(rng.choice(('SWITCH', 'CALL', 'SMUL', 'LIDX')), rng)))
        image, _ = synthetic_image(rng, program, compact=True)
        plain = Machine(build_image(assemble(program)[0], [0] * DATA_CELLS, [('main', 0)], NATIVES, STACK_CELLS))
        plain.load()
        pair = SyntheticPair(orig, image, rng.choice((0, 4, 8, 12)))
        try:
            problems = pair.load()
        except HostFault:
            tally.host += 1
            continue
        if sorted(pair.model._decoded or ()) != sorted(plain._decoded):
            problems.append('compact image does not expand to the same instructions')
        outcome, more = pair.run(0, (), value(rng), case)
        if outcome == 'host':
            tally.host += 1
            continue
        tally.add(problems + more, 'compact #%d' % case)
    tally.report('D3', 'compact encoding (header flag 4) expanded in place by scr_load, then relocated '
                 'and run: %(n)d images agree (%(bad)d differ, %(host)d host faults)')
    # the expansion on arbitrary byte strings
    tally = Tally()
    for case in range(max(1, int(400 * scale))):
        # The first cell is made 0x100 or more, so that the relocator stops at once with
        # error 6 and leaves the expanded cells as they are.
        coded = bytearray(encode_compact([rng.randrange(0x100, 0x4000)]))
        cells = 1
        for _ in range(rng.randint(1, 16)):               # redundant and over-long forms included
            # The expansion works in place from the end; it only stays clear of its own input
            # while no prefix of the stream is longer than four bytes per cell.
            longest = min(7, 4 * (cells + 1) - len(coded))
            body = [rng.getrandbits(7) for _ in range(rng.randint(1, longest))]
            coded += bytes([group | 0x80 for group in body[:-1]] + [body[-1]])
            cells += 1
        count = sum(1 for byte in coded if not byte & 0x80)
        image = bytearray(build_image([0] * (count + 4), [], [('main', 0)], (), 32))
        cod, = struct.unpack_from('<i', image, 0x6C)
        image[0x60 + cod:0x60 + cod + len(coded)] = coded
        struct.pack_into('<i', image, 0x60, cod + len(coded))               # size of the coded part
        struct.pack_into('<i', image, 0x74, cod + 4 * count)                # heap start = expanded end
        struct.pack_into('<H', image, 0x68, 4)
        model = Machine(bytes(image))
        orig.place(bytes(image))
        a, b = orig.load(), model.load()
        problems = ['scr_load returns %d, model %d' % (a, b)] if a != b else []
        theirs = orig.emu.mem.read(orig.base + 0x60 + cod, 4 * count + 16)
        if theirs != bytes(model.image[0x60 + cod:0x60 + cod + 4 * count + 16]):
            problems.append('expanded cells differ')
        tally.add(problems + differences(orig, model, len(image)), 'expansion of %s' % coded.hex())
    tally.report('D4', 'the expansion alone on random byte strings, with over-long forms (6 and 7 bytes '
                 'for one cell, where the shift count wraps): %(n)d strings expand to the model\'s cells '
                 '(%(bad)d differ)')


def group_library(orig, options):
    rng = random.Random(0x57)
    scale = options['scale']
    mem = orig.emu.mem
    image = build_image([OP['HALT'], 0], [0] * 512, [('main', 0)], NATIVES, 256)
    pair = SyntheticPair(orig, image)
    pair.load()
    model = pair.model
    room = 4 * 512

    def text(length):
        kind = rng.random()
        if kind < 0.5:
            return bytes(rng.choice(b'abcdefghijklmnopqrstuvwxyz_0123456789 ') for _ in range(length))
        return bytes(rng.randrange(1, 256) for _ in range(length))

    # writing and reading back
    tally = Tally()
    for case in range(max(1, int(600 * scale))):
        string = text(rng.choice((0, 1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17, rng.randint(0, 60))))
        pack = rng.choice((0, 1, 1, 7))
        address = rng.randrange(0, room - 4 * len(string) - 8, 4)
        for position in range(0, room, 4):                # same arbitrary memory on both sides
            word = rng.getrandbits(32) if rng.random() < 0.9 else 0
            mem.w32(orig.host(model, position), word)
            model.set_cell(position, word)
        mem.write(orig.buffer, string + b'\0')
        a = orig.call(SCR_SET_STRING, orig.host(model, address), orig.buffer, pack)
        b = model.set_string(address, string, pack)
        problems = ['scr_setString returns %d, model %d' % (a, b)] if a != b else []
        problems += differences(orig, model, len(image))
        orig.call(SCR_STR_LEN, orig.host(model, address), orig.cells + 0x30)
        a, b = mem.s32(orig.cells + 0x30), model.str_len(address)
        if a != b:
            problems.append('scr_strLen gives %d, model %d' % (a, b))
        a, b = orig.get_string(orig.host(model, address), room), model.get_string(address)
        if a != b:
            problems.append('scr_getString gives %r, model %r' % (a, b))
        if pack and string and string[0] < 0x80 and b != string:
            problems.append('packed string does not read back: %r -> %r' % (string, b))
        if not pack and all(c < 0x80 for c in string) and b != string:
            problems.append('unpacked string does not read back: %r -> %r' % (string, b))
        tally.add(problems, 'string %r pack %d' % (string, pack))
    tally.report('E1', 'scr_setString (packed and unpacked), then scr_strLen and scr_getString on the '
                 'result, in memory filled with random words: %(n)d strings agree with set_string, '
                 'str_len and get_string, memory included (%(bad)d differ)')
    # reading arbitrary cells as strings
    tally = Tally()
    for case in range(max(1, int(600 * scale))):
        length = rng.randint(1, 12)
        cells = []
        for _ in range(length):
            kind = rng.random()
            cells.append(rng.getrandbits(32) if kind < 0.4 else rng.randrange(1, 256) if kind < 0.7 else
                         rng.getrandbits(32) & rng.choice((0xFFFFFF00, 0xFFFF00FF, 0xFF00FFFF, 0x00FFFFFF,
                                                            0xFFFF0000, 0xFF000000, 0x000000FF)))
        cells.append(rng.choice((0, 0, rng.getrandbits(24))))
        cells.append(0)
        address = rng.randrange(0, room - 4 * len(cells), 4)
        for position, word in enumerate(cells):
            mem.w32(orig.host(model, address + 4 * position), word)
            model.set_cell(address + 4 * position, word)
        a = orig.get_string(orig.host(model, address), room)
        problems = []
        try:
            b = model.get_string(address)
            if a != b:
                problems.append('scr_getString gives %r, model %r' % (a, b))
            orig.call(SCR_STR_LEN, orig.host(model, address), orig.cells + 0x30)
            a, b = mem.s32(orig.cells + 0x30), model.str_len(address)
            if a != b:
                problems.append('scr_strLen gives %d, model %d' % (a, b))
        except HostFault:
            tally.host += 1
            continue
        tally.add(problems, 'cells %r' % ([hex(c) for c in cells],))
    tally.report('E2', 'scr_getString and scr_strLen on arbitrary cells (first cell negative, zero bytes '
                 'inside packed cells, characters above 0x7f): %(n)d readings agree (%(bad)d differ)')
    # address check, heap allocation
    tally = Tally()
    for case in range(max(1, int(600 * scale))):
        hea = rng.choice((room, room + 64, 0, -4, value(rng)))
        stk = rng.choice((model.stp, model.stp - 64, room + 64, room, value(rng)))
        mem.w32(orig.base + 0x14, hea & M32)
        mem.w32(orig.base + 0x18, stk & M32)
        model.hea, model.stk = hea, stk
        address = rng.choice((0, 4, room - 4, room, room + 4, room + 60, room + 64, model.stp - 4, model.stp,
                              model.stp + 4, -4, value(rng)))
        mem.w32(orig.cells + 0x30, 0x77777777)
        a = orig.call(SCR_GET_ADDR, orig.base, address, orig.cells + 0x30)
        b = model.get_addr(address)
        problems = ['scr_getAddr(%d) returns %d, model %d' % (address, a, b)] if a != b else []
        pointer = mem.u32(orig.cells + 0x30)
        if a == 0 and pointer != orig.host(model, address) & M32:
            problems.append('scr_getAddr pointer 0x%x' % pointer)
        if a != 0 and pointer != 0x77777777:
            problems.append('scr_getAddr stored a pointer on failure')
        cells = rng.choice((0, 1, 2, 16, 64, 256, 1000, 0x10000, -1, -16, 0x3FFFFFFF, 0x40000000))
        mem.w32(orig.cells + 0x34, 0x66666666)
        a = orig.call(SCR_ALLOT, orig.base, cells, orig.cells + 0x34, orig.cells + 0x38)
        b, where = model.allot(cells)
        if a != b or (a == 0 and mem.s32(orig.cells + 0x34) != where):
            problems.append('scr_allot(%d) returns %d at %d, model %d at %r' % (cells, a, mem.s32(orig.cells + 0x34),
                                                                              b, where))
        back = rng.choice((room, hea, 0, value(rng)))
        a, b = orig.call(SCR_RELEASE, orig.base, back), model.release(back)
        problems += ['scr_release returns %d, model %d' % (a, b)] if a != b else []
        problems += [text for text in differences(orig, model, len(image))]
        tally.add(problems, 'hea %d stk %d address %d cells %d' % (hea, stk, address, cells))
    tally.report('E3', 'scr_getAddr, scr_allot and scr_release with random heap and stack words: %(n)d '
                 'cases agree with get_addr, allot and release (%(bad)d differ)')
    # entry-point lookup on synthetic tables
    tally = Tally()
    for case in range(max(1, int(150 * scale))):
        count = rng.randint(0, 12)
        alphabet = rng.choice((b'ab', b'abcXYZ_09', bytes(range(1, 256))))
        names = set()
        while len(names) < count:
            names.add(bytes(rng.choice(alphabet) for _ in range(rng.randint(1, rng.choice((2, 6, 19))))))
        names = list(names)
        ordered = rng.random() < 0.8
        if not ordered:
            rng.shuffle(names)
        table_image = build_image([OP['HALT'], 0], [0] * 8, [(name, 0) for name in names], (), 32,
                                  sort_publics=ordered)
        lookup = SyntheticPair(orig, table_image)
        problems = lookup.load()
        for probe in names + [bytes(rng.choice(alphabet) for _ in range(rng.randint(0, 20))) for _ in range(6)]:
            a, b = orig.find(probe), lookup.model.find_public(probe)
            if a != b:
                problems.append('%r: %r, model %r' % (probe, a, b))
        tally.add(problems, 'table %r' % (names,))
    tally.report('E4', 'scr_findEntry on synthetic tables (0 to 12 names, bytes up to 0xff, one in five '
                 'tables not sorted): %(n)d tables, every name and six other strings each, agree with '
                 'find_public (%(bad)d differ)')


GROUPS = (('tables', group_tables), ('scripts', group_scripts), ('opcodes', group_opcodes),
          ('entry', group_entry), ('loader', group_loader), ('library', group_library))


def find_elf(positional):
    for arg in positional:
        if os.path.isfile(arg):
            return arg
    for candidate in (os.environ.get('CHAMPIONS_ELF'), os.path.join(ROOT, 'SLUS_209.73'),
                      os.path.join(os.getcwd(), 'SLUS_209.73')):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def main(argv=None):
    global VERBOSE
    argv = sys.argv[1:] if argv is None else list(argv)
    options = {'scripts': os.environ.get('CHAMPIONS_SCRIPTS') or os.path.join(ROOT, 'scripts_raw'),
               'seeds': 3, 'scale': 1.0}
    positional, only, index = [], None, 0
    while index < len(argv):
        arg = argv[index]
        if arg == '-v':
            VERBOSE = True
        elif arg in ('--scripts', '--seeds', '--scale', '-k') and index + 1 < len(argv):
            index += 1
            if arg == '-k':
                only = argv[index].lower()
            else:
                options[arg[2:]] = {'--scripts': str, '--seeds': int, '--scale': float}[arg](argv[index])
        elif arg.startswith('-'):
            print(__doc__)
            return 2
        else:
            positional.append(arg)
        index += 1
    elf = find_elf(positional)
    if elf is None:
        print('SKIP  no SLUS_209.73 found (pass its path, or set CHAMPIONS_ELF); nothing was run')
        return 0
    with open(elf, 'rb') as source:
        digest = hashlib.sha256(source.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('SKIP  %s is not the US v2.00 executable these addresses belong to (SHA-256 %s); '
              'nothing was run' % (elf, digest))
        return 0
    print('executable: %s  (SHA-256 matches US v2.00)' % elf)
    sys.setrecursionlimit(20000)
    orig = Original(elf)
    for name, function in GROUPS:
        if only and only not in name:
            continue
        print('--- %s' % name)
        try:
            function(orig, options)
        except EmuError as stop:
            check(name + '!', False, 'the emulator stopped outside a compared run: %s' % stop)
    passed = sum(1 for _, ok in RESULTS if ok)
    print('%d properties: %d PASS, %d FAIL' % (len(RESULTS), passed, len(RESULTS) - passed))
    return 0 if passed == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
