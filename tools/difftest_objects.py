#!/usr/bin/env python3
"""difftest_objects.py - compare tools/ref_objects.py with the game's own object system.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_objects.py [path/to/SLUS_209.73] [--quick] [--seed N] [-k TEXT] [-v]

    --quick   a tenth of the steps of every scenario
    --seed N  seed of the random scenarios (default 20973); a seed repeats exactly
    -k TEXT   run only the properties whose name contains TEXT
    -v        print the first mismatches of a failing property and the basic blocks that
              were never entered

Every property prints one line: PASS or FAIL, its name, the number of steps compared and
what was compared.  Exit status 1 when any property fails.

How a property is tested
    The ORIGINAL functions are executed by tools/ee_emu.py (an instruction interpreter,
    not a console) on a world built in the interpreter's memory by the original
    constructors; tools/ref_objects.py holds the same world as Python objects.  A scenario
    is a long seeded random sequence of operations.  Each operation is applied to the model
    first and then to the original, and after EVERY operation these must be equal:

      results      what the operation returns (addresses, query result lists in order,
                   0/1 answers)
      callbacks    the order in which the original calls back - each object's virtual
                   run (slot 4), each destructor (slot 1), walker callbacks, tasks, the
                   object factory - with their arguments
      lists        every list head and every node of every list: the delete list, the
                   always-draw list, the off-grid list, the every-frame list, the 15 and
                   60 slow lists, and all 28,800 cells of the two grids
      objects      the 19 words of every live object
      allocators   the three pool free-list heads and the handle-node free list (heads
                   after every step, whole chains and the whole node array every 32nd)
      globals      the shared seed, both round-robin cursors, the sampled pool count, the
                   name table (all 512 slots)

    Callbacks are recording stubs.  What a stub does - create objects, delete or destroy
    others or itself, move, change run list, query - is decided by a seeded script while
    the MODEL runs; the original's stub then replays the same operations through the
    original functions (calls nested inside the running function) and must be called in
    the same order with the same objects.

What runs for real and what is a stub
    Real: everything in FUNCS below (the coverage table), pool_new/free/countFree, the
    handle-list and iterator functions, the C library.  Stubs: virtual slots 1, 4 and 8 of
    the GameObject table (slot 1 records and then runs the real GameObject_dtor),
    res_find, mem_dumpHeap, game_isFrozen, the three end-of-tick calls of tasks_run,
    dialog_objIfOpen, net_isLocalSlot, the two terrain queries of world_findFreeSpot, the
    object factory and the save filter.  No derived class is constructed except Player1.

Floats are compared as 32-bit patterns: "equal" means identical under the interpreter's
floating-point model ('ps2'); the box queries, the activity test and the free-spot search
are repeated under the other adder models (docs/issues/dynamic-tests.md).
"""
import hashlib
import os
import random
import struct
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError                 # noqa: E402
import ref_core as R                            # noqa: E402
import ref_objects as O                         # noqa: E402

M32 = 0xFFFFFFFF
EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False, 'scale': 1.0}
RESULTS = []

# ---------------------------------------------------------------------------------------
# The original's functions
# ---------------------------------------------------------------------------------------
FUNCS = [                                       # name, start, end: run for real, coverage counted
    ('GameObject_ctor', 0x14CB10, 0x14CF90), ('GameObject_dtor', 0x14CF90, 0x14D238),
    ('obj_linkToGrid', 0x14F120, 0x14F200), ('obj_updateGridCell', 0x14F028, 0x14F120),
    ('obj_moveOffGrid', 0x14EF48, 0x14EFA0), ('obj_isOffGrid', 0x14EFA0, 0x14F028),
    ('obj_delete', 0x14F200, 0x14F248), ('obj_runEveryFrame', 0x14F248, 0x14F290),
    ('obj_stopRunning', 0x14F290, 0x14F2B8), ('obj_runEvery60', 0x14F2B8, 0x14F330),
    ('obj_runEvery15', 0x14F330, 0x14F3A8), ('world_flushDeleteList', 0x14F3A8, 0x14F428),
    ('obj_addToAlwaysDraw', 0x14EDD8, 0x14EE18), ('obj_addToAlwaysDrawOnce', 0x14EE18, 0x14EEC0),
    ('world_clearAlwaysDraw', 0x14EEC0, 0x14EF48),
    ('world_collectObjectsInBox', 0x14A928, 0x14AB80), ('world_collectInSphere', 0x14AB80, 0x14ACF8),
    ('obj_updateActive', 0x14DB08, 0x14DCC8), ('runObjects', 0x14B910, 0x14BCE0),
    ('world_forEachGridObject', 0x14A610, 0x14A7C8), ('world_forEachRunObject', 0x14A7C8, 0x14A928),
    ('objNames_add', 0x14BCE0, 0x14BE58), ('objNames_remove', 0x14BE58, 0x14BF58),
    ('world_findObjectsByName', 0x14BF58, 0x14C0B8), ('world_findObjectsByClass', 0x14C0B8, 0x14C370),
    ('world_init', 0x14C370, 0x14C460), ('world_deleteAllObjects', 0x14C460, 0x14C730),
    ('world_loadRecords', 0x14E808, 0x14EA98), ('world_createObject', 0x14F6C8, 0x14F730),
    ('world_findFreeSpot', 0x14ACF8, 0x14B168), ('Player1_ctor', 0x158928, 0x158BCC),
    ('obj_getPropInt', 0x14C880, 0x14C9C0), ('obj_getPropStr', 0x14F4C0, 0x14F5F0),
    ('task_add', 0x19E4A0, 0x19E5E8), ('task_isRunning', 0x19E5E8, 0x19E664),
    ('task_remove', 0x19E664, 0x19E760), ('tasks_call', 0x19E798, 0x19E854),
    ('tasks_run', 0x3226E4, 0x322934), ('gameSetObjectVis', 0x1E4D48, 0x1E4E88),
    ('isNearView', 0x1E77C0, 0x1E78D0), ('game_rebuildAlivePlayers', 0x1E72F8, 0x1E7438),
]
A = {name: start for name, start, _end in FUNCS}
POOL_INIT, POOL_NEW, POOL_FREE, POOL_COUNT_FREE, MEM_DUMP_HEAP = 0x14FCD8, 0x14FDB8, 0x150470, 0x150410, 0x150290
POOL_TABLE = 0x403A10
H_INIT, H_CLEAR, H_FREE_HEAD = 0x1A17D0, 0x1A1698, 0x864EA8
RES_FIND, GAME_IS_FROZEN = 0x17365C, 0x1EBDF8
REBUILD_ALIVE, CHECK_ALL_DEAD, UPDATE_RUMBLE = 0x1E72F8, 0x1E7438, 0x17474C
DIALOG_OBJ, NET_IS_LOCAL = 0x231050, 0x13E150
TERRAIN_BLOCKED, TERRAIN_HEIGHT = 0x183B48, 0x183820
SET_FACTORY, SET_FILTER = 0x14F6A8, 0x14F6B8
VT = O.VT_GAMEOBJECT
NODE_BASE, NODE_SIZE = R.HandlePool.NODE_BASE, R.HandlePool.NODE_SIZE
G_PLAYERS, PLAYER_REC, PLAYER_OBJ = 0x4D8AF0, 0x4C30, 0x43D8
G_NUM_PLAYERS, G_LOCAL_CAMERA, G_CUTSCENE = 0x4D8AE0, 0x4F8450, 0x44FCD0
G_PADS, G_LOCKOUT, G_LOCKOUT_HOLD, G_WARMUP = 0x41BFD8, 0x41B4FC, 0x41B500, 0x506048
G_ALIVE_COUNT, G_ALIVE, G_LOCAL_COUNT, G_LOCAL_ALIVE, G_LOCAL_FIRST = 0x4F8420, 0x4F8440, 0x4F8424, 0x4F8430, 0x4F841C
G_PREV_LEVEL, G_GATE_TRAVEL, G_ENTRANCE, G_WORLD = 0x41B7C2, 0x41B51E, 0x4F8468, 0x44FDC8


def wanted(name):
    return OPTIONS['filter'] is None or OPTIONS['filter'].lower() in name.lower()


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-22s %7d steps  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:4]:
            print('        ' + line)
    sys.stdout.flush()


def scaled(count):
    count = int(count * OPTIONS['scale'])
    return max(count // 10, 12) if OPTIONS['quick'] else max(count, 12)


def f32(value):
    return R.f32(value)


# ---------------------------------------------------------------------------------------
# Coverage: basic blocks of the functions that ran for real
# ---------------------------------------------------------------------------------------
def analyse(mem, start, end):
    """Basic-block leaders of one function body: its entry, every branch target inside it
    and the instruction after every conditional branch's delay slot."""
    leaders = {start}
    for pc in range(start, end, 4):
        w = mem.u32(pc)
        op, rs, rt = w >> 26, (w >> 21) & 31, (w >> 16) & 31
        target = (pc + 4 + (ee_emu.sx16(w) << 2)) & M32
        cond = None
        if op in (4, 5, 20, 21):
            cond = not (op in (4, 20) and rs == 0 and rt == 0)
        elif op in (6, 7, 22, 23):
            cond = True
        elif op == 1 and rt in (0, 1, 2, 3):
            cond = True
        elif op == 17 and rs == 8:
            cond = True
        elif op == 2:
            leaders.add((pc & 0xF0000000) | ((w & 0x3FFFFFF) << 2))
            continue
        if cond is None:
            continue
        leaders.add(target)
        if cond:
            leaders.add(pc + 8)
    return {a for a in leaders if start <= a < end}


class Coverage:
    def __init__(self, mem):
        self.parts = [(name, start, end, analyse(mem, start, end)) for name, start, end in FUNCS]
        self.pcs = set()

    def rows(self):
        for name, start, end, leaders in self.parts:
            hit = leaders & self.pcs
            yield name, len(hit), len(leaders), sorted(leaders - self.pcs)


COVERAGE = [None]


# ---------------------------------------------------------------------------------------
# The rig: the original world in the interpreter and the model, side by side
# ---------------------------------------------------------------------------------------
class Diverged(Exception):
    pass


class Rig:
    SP = EE.STACK_HI - 0x8000

    def __init__(self, elf, seed, fpu='ps2'):
        emu = self.emu = EE(elf, fpu_model=fpu)
        R.set_fpu(fpu)
        emu.record_calls = False
        emu.record_writes = False
        if COVERAGE[0] is None:
            COVERAGE[0] = Coverage(emu.mem)
        emu.trace = []
        self.rng = random.Random(seed)
        self.model = O.World()
        self.depth = 0
        self.failures, self.examples, self.steps = 0, [], 0
        self.log, self.pos, self.diverged = [], 0, False
        self.dying = set()
        self.frozen = 0
        self.dumps = 0
        self.stats = {}
        self.script_run = lambda obj: None
        self.script_dtor = lambda obj: None
        self.script_walk = lambda obj: None
        self.script_task = lambda fn: None
        self.script_factory = None
        mem = emu.mem
        # stub entry points: "jr ra; nop" each, hooked
        base = emu.alloc(0x400)
        for i in range(0x80):
            mem.w32(base + 8 * i, 0x03E00008)
            mem.w32(base + 8 * i + 4, 0)
        (self.STUB_RUN, self.STUB_DTOR, self.STUB_WALK, self.STUB_LOAD, self.STUB_FACTORY,
         self.STUB_FILTER) = [base + 8 * i for i in range(6)]
        self.STUB_TASKS = [base + 8 * i for i in range(8, 40)]
        emu.stub(self.STUB_RUN, function=self.e_run)
        emu.stub(self.STUB_DTOR, function=self.e_dtor)
        emu.stub(self.STUB_WALK, function=self.e_walk)
        emu.stub(self.STUB_LOAD, function=self.e_load)
        emu.stub(self.STUB_FACTORY, function=self.e_factory)
        emu.stub(self.STUB_FILTER, function=self.e_filter)
        for addr in self.STUB_TASKS:
            emu.stub(addr, function=lambda e, addr=addr: self.e_task(addr))
        mem.w32(VT + 8 * 1 + 4, self.STUB_DTOR)
        mem.w32(VT + 8 * 4 + 4, self.STUB_RUN)
        mem.w32(VT + 8 * 8 + 4, self.STUB_LOAD)
        emu.stub(MEM_DUMP_HEAP, function=self.e_dump)
        emu.stub(RES_FIND, function=lambda e: self.res_value(e.r[4] & M32, e.r[5] & M32))
        emu.stub(GAME_IS_FROZEN, function=lambda e: self.e_call('frozen', ()))
        self.scratch = emu.alloc(0x400)
        self.outbuf = emu.alloc(0x2000)
        self.strings = {}
        self.ecall(POOL_INIT, max_steps=3000000)
        self.ecall(H_INIT)
        self.ecall(A['world_init'])
        self.model.init()
        self.model.on_run = self.m_run
        self.model.on_destroy = self.m_dtor
        self.model.is_frozen = lambda: self.m_call('frozen', (), self.frozen)
        self.model.res_find = self.res_value
        self.props = [None]                     # (address, model list) pairs; index 0 = no list
        self.defs = [None]
        self.def_by_id = {}

    # ---- bookkeeping ----------------------------------------------------------------------
    def bad(self, text):
        self.failures += 1
        if len(self.examples) < 6:
            self.examples.append('step %d: %s' % (self.steps, text))

    def count(self, key, amount=1):
        self.stats[key] = self.stats.get(key, 0) + amount

    def ptr(self, thing):
        if thing is None:
            return 0
        if isinstance(thing, R.Node):
            return NODE_BASE + NODE_SIZE * thing.index
        if isinstance(thing, R.Cell):
            return thing.name
        return thing.addr

    def cstring(self, text):
        """Address of a C string in the interpreter's memory (one copy per text)."""
        text = bytes(text)
        if text not in self.strings:
            addr = self.emu.alloc(len(text) + 1, align=4)
            self.emu.mem.write(addr, text + b'\0')
            self.strings[text] = addr
        return self.strings[text]

    def read_cstr(self, addr):
        out = bytearray()
        while True:
            byte = self.emu.mem.u8(addr + len(out))
            if byte == 0:
                return bytes(out)
            out.append(byte)

    def add_props(self, entries):
        """A property list: null-terminated pointer array, each string its own copy (the
        constructor edits quoted names in place)."""
        mem = self.emu.mem
        array = self.emu.alloc(4 * (len(entries) + 1), align=4)
        for index, text in enumerate(entries):
            addr = self.emu.alloc(len(text) + 1, align=4)
            mem.write(addr, bytes(text) + b'\0')
            mem.w32(array + 4 * index, addr)
        self.props.append((array, [bytes(e) for e in entries]))
        return len(self.props) - 1

    def add_def(self, names, generation):
        mem = self.emu.mem
        lump = self.cstring(b'lump%d' % len(self.defs))
        addr = self.emu.alloc(8 + 8 * (len(names) + 1), align=8)
        mem.w32(addr, lump)
        mem.w32(addr + 4, generation)
        pointers = []
        for index, name in enumerate(names):
            pointers.append(self.cstring(name))
            mem.w32(addr + 8 + 8 * index, pointers[-1])
        definition = O.ClassDef(lump, pointers, generation)
        definition.addr = addr
        self.defs.append(definition)
        return len(self.defs) - 1

    @staticmethod
    def res_value(lump, name):
        return (lump * 31 + name * 7 + 0x1234) & 0x7FFFFFF

    # ---- calling the original ---------------------------------------------------------------
    def ecall(self, addr, *args, f12=None, f13=None, max_steps=4000000):
        emu = self.emu
        if self.depth == 0:
            emu.r[29] = self.SP
            emu._pending_call = emu._fresh_call = None
            if f12 is not None:
                emu.f[12] = f12 & M32
            if f13 is not None:
                emu.f[13] = f13 & M32
            self.depth = 1
            try:
                value = emu.call(addr, *args, max_steps=max_steps)
            finally:
                self.depth = 0
                COVERAGE[0].pcs.update(emu.trace)
                del emu.trace[:]
            return value & M32
        saved = (emu.r[:], emu.rh[:], emu.f[:], emu.hi, emu.lo, emu.hi1, emu.lo1, emu.acc, emu.fcr31,
                 emu.pc, emu.npc, emu.cur, emu._pending_call, emu._fresh_call, emu._call_site)
        emu.r[29] = ((emu.r[29] & M32) - 0x400) & ~0xF
        emu._pending_call = emu._fresh_call = None
        if f12 is not None:
            emu.f[12] = f12 & M32
        if f13 is not None:
            emu.f[13] = f13 & M32
        self.depth += 1
        try:
            value = emu.call(addr, *args, max_steps=max_steps)
        finally:
            self.depth -= 1
            emu.r[:], emu.rh[:], emu.f[:] = saved[0], saved[1], saved[2]
            (emu.hi, emu.lo, emu.hi1, emu.lo1, emu.acc, emu.fcr31, emu.pc, emu.npc, emu.cur,
             emu._pending_call, emu._fresh_call, emu._call_site) = saved[3:]
        return value & M32

    def vec(self, slot, triple):
        addr = self.scratch + 16 * slot
        self.emu.mem.write(addr, struct.pack('<3I', *[v & M32 for v in triple]))
        return addr

    def e_dump(self, emu):
        self.dumps += 1
        return 0

    # ---- the log: what the model did, replayed on the original -------------------------------
    def do(self, *op):
        """One top-level operation on both sides, then a full comparison."""
        self.steps += 1
        self.count(op[0])
        self.log, self.pos, self.diverged = [], 1, False
        want = self.do_model(op)
        try:
            got = self.do_emu(op)
        except EmuError as exc:
            self.bad('%r: the original stopped: %s' % (op[:2], exc))
            raise Diverged()
        if got != want:
            self.bad('%s: original %s, model %s' % (self.show(op), self.show(got), self.show(want)))
        if not self.diverged and self.pos != len(self.log):
            self.bad('%s: the original made fewer callbacks than the model (%d of %d log entries)'
                     % (self.show(op), self.pos, len(self.log)))
            self.diverged = True
        self.check(full=self.steps % 32 == 0)
        if self.diverged:
            raise Diverged()
        return want

    @staticmethod
    def show(value):
        if isinstance(value, int):
            return '0x%x' % (value & M32)
        if isinstance(value, (tuple, list)):
            return '(' + ' '.join(Rig.show(v) for v in value[:12]) + (' ...' if len(value) > 12 else '') + ')'
        return repr(value)

    def do_model(self, op):
        entry = ['op', op, None]
        self.log.append(entry)
        entry[2] = getattr(self, 'm_' + op[0])(*op[1:])
        return entry[2]

    def do_emu(self, op):
        return getattr(self, 'e_' + op[0])(*op[1:])

    def expect(self, entry):
        if self.diverged:
            return False
        if self.pos < len(self.log) and tuple(self.log[self.pos]) == entry:
            self.pos += 1
            return True
        have = self.log[self.pos] if self.pos < len(self.log) else 'nothing more'
        self.bad('callback order: the original calls %s where the model has %s' % (self.show(entry), self.show(have)))
        self.diverged = True
        return False

    def replay(self):
        """Replay the operations the model's callback made, up to its end marker; returns
        the value the callback handed back."""
        while not self.diverged:
            if self.pos >= len(self.log):
                self.bad('the log ended inside a callback')
                self.diverged = True
                break
            entry = self.log[self.pos]
            self.pos += 1
            if entry[0] == 'end':
                return entry[1]
            if entry[0] != 'op':
                self.bad('callback order: the model has %s where the original returns' % self.show(entry))
                self.diverged = True
                break
            got = self.do_emu(entry[1])
            if got != entry[2]:
                self.bad('%s inside a callback: original %s, model %s'
                         % (self.show(entry[1]), self.show(got), self.show(entry[2])))
        return 0

    def m_call(self, name, args, answer):
        """A call the code under test makes to something that is scripted: the model logs
        the arguments and the answer it was given."""
        self.log.append(('call', name, args, answer))
        return answer

    def e_call(self, name, args):
        """...and the original's stub must make the same call; it gets the same answer."""
        if self.diverged:
            return 0
        if self.pos < len(self.log):
            entry = self.log[self.pos]
            if entry[0] == 'call' and entry[1] == name and entry[2] == args:
                self.pos += 1
                return entry[3]
        have = self.log[self.pos] if self.pos < len(self.log) else 'nothing more'
        self.bad('call order: the original calls %s%s where the model has %s' % (name, self.show(args), self.show(have)))
        self.diverged = True
        return 0

    # ---- callbacks: model side ------------------------------------------------------------------
    def m_run(self, obj):
        if obj.vtable == O.VT_PLAYER1:          # the class's own slot 4 (an empty function) runs for real
            return
        self.log.append(('run', obj.addr))
        self.count('run calls')
        self.script_run(obj)
        self.log.append(('end', 0))

    def m_dtor(self, obj, flags):
        if obj.vtable == O.VT_PLAYER1:          # Player1_dtor 0x3c2a00 runs for real: base part, then the free
            self.model.destroy(obj, flags)
            return
        self.log.append(('dtor', obj.addr, flags))
        self.count('destructor calls')
        self.dying.add(obj.addr)
        self.script_dtor(obj)
        self.dying.discard(obj.addr)
        self.log.append(('end', 0))
        self.model.destroy(obj, flags)

    def m_walk(self, obj):
        self.count('walk calls')
        self.log.append(('walk', obj.addr))
        self.script_walk(obj)
        self.log.append(('end', 0))

    def m_task(self, fn):
        if fn == A['runObjects']:
            self.model.run_objects()
            return
        self.log.append(('task', fn))
        self.count('task calls')
        self.script_task(fn)
        self.log.append(('end', 0))

    # ---- callbacks: the original's stubs ------------------------------------------------------------
    def e_run(self, emu):
        if self.expect(('run', emu.r[4] & M32)):
            self.replay()
        return 0

    def e_dtor(self, emu):
        addr, flags = emu.r[4] & M32, emu.r[5] & M32
        if self.expect(('dtor', addr, flags)):
            self.replay()
        self.ecall(A['GameObject_dtor'], addr, flags)
        return 0

    def e_walk(self, emu):
        if self.expect(('walk', emu.r[4] & M32)):
            self.replay()
        return 0

    def e_task(self, addr):
        if self.expect(('task', addr)):
            self.replay()
        return 0

    def e_load(self, emu):
        addr, state = emu.r[4] & M32, emu.r[5] & M32
        if not self.diverged and self.pos < len(self.log) and self.log[self.pos][0] == 'load':
            entry = self.log[self.pos]
            got = (addr, self.emu.mem.read(state, len(entry[2])), state & 7)
            if got != (entry[1], entry[2], 0):
                self.bad('slot 8: original %r, model %r' % (got, entry[1:]))
            self.pos += 1
            return len(entry[2])
        self.bad('slot 8 called where the model has none')
        self.diverged = True
        return 0

    def e_factory(self, emu):
        mem = emu.mem
        name = emu.r[4] & M32
        pos = struct.unpack('<3I', mem.read(emu.r[5] & M32, 12))
        angle = ee_emu.s32(emu.r[6])
        props = emu.r[7] & M32
        texts = []
        while props and mem.u32(props + 4 * len(texts)):
            texts.append(self.read_cstr(mem.u32(props + 4 * len(texts))))
        entry = ('factory', self.read_cstr(name) if name else None, pos, angle, tuple(texts), props)
        if self.expect(entry):
            return self.replay()
        return 0

    def e_filter(self, emu):
        name = emu.r[4] & M32
        return self.e_call('filter', (self.read_cstr(name) if name else None,))

    # ---- operations: (model, original) pairs ----------------------------------------------------------
    def obj(self, addr):
        return self.model.objects[addr]

    def m_new(self, size, pos, pkey, dkey, then, flags, stale):
        m = self.model
        addr = m.pool.new(size)
        if addr == 0:
            return 0
        props = self.props[pkey][1] if pkey else None
        obj = m.construct(addr, pos, self.defs[dkey] if dkey else None, props,
                          stale_props=self.props[stale][1] if stale else None)
        obj.tag = {'props': self.props[pkey][0] if pkey else 0, 'active': 0, 'cname': 0}
        if flags:
            obj.flags |= flags
            m.update_grid_cell(obj)
        if then == 'frame':
            m.run_every_frame(obj)
        elif then == 'r15':
            m.run_every_15(obj)
        elif then == 'r60':
            m.run_every_60(obj)
        return addr

    def e_new(self, size, pos, pkey, dkey, then, flags, stale):
        mem = self.emu.mem
        addr = self.ecall(POOL_NEW, ee_emu.s32(size))
        if addr == 0:
            return 0
        if mem.read(addr, O.OBJECT_SIZE) != bytes(O.OBJECT_SIZE):
            self.bad('pool_new block 0x%x not zeroed' % addr)
        if stale:
            mem.w32(addr + 0x2C, self.props[stale][0])
        self.ecall(A['GameObject_ctor'], addr, self.vec(0, pos), self.defs[dkey].addr if dkey else 0,
                   self.props[pkey][0] if pkey else 0)
        if flags:
            mem.w32(addr + 0xC, mem.u32(addr + 0xC) | flags)
            self.ecall(A['obj_updateGridCell'], addr)
        if then != 'none':
            self.ecall(A[{'frame': 'obj_runEveryFrame', 'r15': 'obj_runEvery15', 'r60': 'obj_runEvery60'}[then]], addr)
        return addr

    def m_flags(self, addr, value):
        self.obj(addr).flags = value & M32
        return 0

    def e_flags(self, addr, value):
        self.emu.mem.w32(addr + 0xC, value)
        return 0

    def m_move(self, addr, x, y, z):
        obj = self.obj(addr)
        obj.pos = [x, y, z]
        self.model.update_grid_cell(obj)
        return 0

    def e_move(self, addr, x, y, z):
        self.emu.mem.write(addr + 0x10, struct.pack('<3I', x, y, z))
        self.ecall(A['obj_updateGridCell'], addr)
        return 0

    def _simple(name, method):                  # noqa: N805
        def model(self, addr):
            value = getattr(self.model, method)(self.obj(addr))
            return int(value) if value is not None else 0

        def original(self, addr):
            value = self.ecall(A[name], addr)
            return value if name == 'obj_isOffGrid' else 0
        return model, original

    m_offgrid, e_offgrid = _simple('obj_moveOffGrid', 'move_off_grid')
    m_isoff, e_isoff = _simple('obj_isOffGrid', 'is_off_grid')
    m_frame, e_frame = _simple('obj_runEveryFrame', 'run_every_frame')
    m_r15, e_r15 = _simple('obj_runEvery15', 'run_every_15')
    m_r60, e_r60 = _simple('obj_runEvery60', 'run_every_60')
    m_stop, e_stop = _simple('obj_stopRunning', 'stop_running')
    m_delete, e_delete = _simple('obj_delete', 'delete')
    m_adraw, e_adraw = _simple('obj_addToAlwaysDraw', 'add_to_always_draw')
    m_adraw1, e_adraw1 = _simple('obj_addToAlwaysDrawOnce', 'add_to_always_draw_once')
    del _simple

    def m_cleardraw(self):
        self.model.clear_always_draw()
        return 0

    def e_cleardraw(self):
        self.ecall(A['world_clearAlwaysDraw'])
        return 0

    def m_destroy(self, addr):
        self.model.on_destroy(self.obj(addr), 3)
        return 0

    def e_destroy(self, addr):
        mem = self.emu.mem
        table = mem.u32(addr + 0x48)
        self.ecall(mem.u32(table + 8 + 4), addr + mem.s16(table + 8), 3)
        return 0

    def m_active(self, addr, was, radius):
        return self.model.update_active(self.obj(addr), was, radius)

    def e_active(self, addr, was, radius):
        return self.ecall(A['obj_updateActive'], addr, was, radius)

    def m_box(self, lo, hi, limit, mask):
        m = self.model
        saved = m.exclude_mask
        if mask is not None:
            m.exclude_mask = mask
        out = tuple(o.addr for o in m.collect_in_box(lo, hi, limit))
        m.exclude_mask = saved
        return out

    def e_box(self, lo, hi, limit, mask):
        mem = self.emu.mem
        saved = mem.u32(O.G_EXCLUDE_MASK)
        if mask is not None:
            mem.w32(O.G_EXCLUDE_MASK, mask)
        room = max(ee_emu.s32(limit), 1) + 2
        mem.write(self.outbuf, b'\xEE' * (4 * room))
        end = self.ecall(A['world_collectObjectsInBox'], self.vec(1, lo), self.vec(2, hi), self.outbuf, limit)
        mem.w32(O.G_EXCLUDE_MASK, saved)
        words = struct.unpack('<%dI' % room, mem.read(self.outbuf, 4 * room))
        count = words.index(0) if 0 in words else -1
        if count < 0 or end != self.outbuf + 4 * count or any(w != 0xEEEEEEEE for w in words[count + 1:]):
            self.bad('box query: terminator, return value or a write past the limit (count %d, limit %d)' % (count, limit))
            return ()
        return tuple(words[:count])

    def m_sphere(self, radius, centre):
        m = self.model
        head = R.Cell(self.scratch + 0x100)
        m.collect_in_sphere(radius, centre, head)
        out = tuple(o.addr for o in R.HandlePool.items(head))
        m.handles.clear(head)
        return out

    def e_sphere(self, radius, centre):
        mem = self.emu.mem
        head = self.scratch + 0x100
        mem.w32(head, 0)
        self.ecall(A['world_collectInSphere'], self.vec(1, centre), 0x5A5A5A5A, head, f12=radius)
        out, node = [], mem.u32(head)
        while node:
            out.append(mem.u32(node + 0xC))
            node = mem.u32(node)
        self.ecall(H_CLEAR, head)
        return tuple(out)

    def m_byname(self, name, limit):
        return tuple(o.addr for o in self.model.names.find(name, limit))

    def e_byname(self, name, limit):
        mem = self.emu.mem
        mem.write(self.outbuf, b'\xEE' * (4 * (limit + 2)))
        end = self.ecall(A['world_findObjectsByName'], self.cstring(name), self.outbuf, limit)
        words = struct.unpack('<%dI' % (limit + 2), mem.read(self.outbuf, 4 * (limit + 2)))
        count = words.index(0)
        if end != self.outbuf + 4 * count or words[count + 1] != 0xEEEEEEEE:
            self.bad('name query: return value or a write past the limit')
        return tuple(words[:count])

    def m_byclass(self, name, limit):
        return tuple(o.addr for o in self.model.find_by_class(name, limit))

    def e_byclass(self, name, limit):
        mem = self.emu.mem
        mem.write(self.outbuf, b'\xEE' * (4 * (limit + 2)))
        self.ecall(A['world_findObjectsByClass'], self.cstring(name), self.outbuf, limit)
        words = struct.unpack('<%dI' % (limit + 2), mem.read(self.outbuf, 4 * (limit + 2)))
        return tuple(words[:words.index(0)])

    def m_retype(self, addr):
        """Make the object a Player1 by its table pointer, as a derived constructor does:
        another type name, the real Player1_dtor in slot 1, an empty slot 4."""
        obj = self.obj(addr)
        obj.vtable, obj.type_name = O.VT_PLAYER1, b'7Player1'
        return 0

    def e_retype(self, addr):
        self.emu.mem.w32(addr + 0x48, O.VT_PLAYER1)
        return 0

    def m_set(self, what, value):
        m = self.model
        if what == 'mask':
            m.exclude_mask = value
        elif what == 'frame':
            m.frame = value
        elif what == 'net':
            m.network_mode = value
        elif what == 'cull':
            m.cull_by_camera = value
        elif what == 'focus':
            m.camera_focus = list(value)
        elif what == 'centres':
            m.centres = [list(c) for c in value]
        elif what == 'frozen':
            self.frozen = value
        elif what == 'generation':
            m.lump_generation = value
        return 0

    def e_set(self, what, value):
        mem = self.emu.mem
        if what == 'mask':
            mem.w32(O.G_EXCLUDE_MASK, value)
        elif what == 'frame':
            mem.w32(O.G_SIM_FRAME, value)
        elif what == 'net':
            mem.w8(O.G_NETWORK_MODE, value)
        elif what == 'cull':
            mem.w8(O.G_CULL_BY_CAMERA, value)
        elif what == 'focus':
            mem.write(O.G_CAMERA_FOCUS, struct.pack('<3I', *value))
        elif what == 'centres':
            mem.w8(O.G_ACTIVITY_COUNT, len(value))
            for index, centre in enumerate(value):
                mem.write(O.G_ACTIVITY_CENTERS + 12 * index, struct.pack('<3I', *centre))
        elif what == 'generation':
            mem.w32(O.G_LUMP_GENERATION, value)
        return 0

    def m_runobjects(self):
        self.model.run_objects()
        return 0

    def e_runobjects(self):
        self.ecall(A['runObjects'], max_steps=30000000)
        return 0

    def m_flush(self):
        self.model.flush_delete_list()
        return 0

    def e_flush(self):
        self.ecall(A['world_flushDeleteList'])
        return 0

    def m_deleteall(self):
        self.model.delete_all_objects()
        return 0

    def e_deleteall(self):
        self.ecall(A['world_deleteAllObjects'], max_steps=60000000)
        return self.emu.mem.u32(O.G_TEARING_DOWN)

    def m_foreach(self, which):
        if which == 'grid':
            self.model.for_each_grid_object(self.m_walk)
        else:
            self.model.for_each_run_object(self.m_walk)
        return 0

    def e_foreach(self, which):
        self.ecall(A['world_forEachGridObject' if which == 'grid' else 'world_forEachRunObject'], self.STUB_WALK,
                   max_steps=60000000)
        return 0

    # ---- tasks ---------------------------------------------------------------------------------------------
    def m_tadd(self, fn, priority, name, flags):
        self.model.tasks.add(fn, priority, name, flags)
        return 0

    def e_tadd(self, fn, priority, name, flags):
        self.ecall(A['task_add'], fn, priority, self.cstring(name), flags)
        return 0

    def m_tremove(self, fn):
        self.model.tasks.remove(fn)
        return 0

    def e_tremove(self, fn):
        self.ecall(A['task_remove'], fn)
        return 0

    def m_trunning(self, name):
        return int(self.model.tasks.is_running(name))

    def e_trunning(self, name):
        return self.ecall(A['task_isRunning'], self.cstring(name))

    def m_tcall(self, exclude, include):
        self.model.tasks.call(exclude, include, self.m_task)
        return 0

    def e_tcall(self, exclude, include):
        self.ecall(A['tasks_call'], exclude, include, max_steps=30000000)
        return 0

    def m_trun(self, count):
        self.model.tasks_run(count, self.m_task)
        return 0

    def e_trun(self, count):
        self.ecall(A['tasks_run'], count, 0x77, max_steps=60000000)
        return 0

    # ---- the comparison --------------------------------------------------------------------------------------
    def check_chain(self, cell):
        mem = self.emu.mem
        addr, thing, count = mem.u32(cell.name), cell.next, 0
        while addr or thing is not None:
            if addr != self.ptr(thing) or isinstance(thing, R.Iterator):
                self.bad('list 0x%x: node 0x%x, model 0x%x' % (cell.name, addr, self.ptr(thing)))
                return
            got = struct.unpack('<4I', mem.read(addr, 16))
            want = (self.ptr(thing.next), self.ptr(thing.prev), self.ptr(thing.partner), self.ptr(thing.obj))
            if got != want:
                self.bad('list 0x%x node 0x%x: %s, model %s' % (cell.name, addr, self.show(got), self.show(want)))
                return
            addr, thing = got[0], thing.next
            count += 1
            if count > 7000:
                self.bad('list 0x%x does not end' % cell.name)
                return

    def model_grid_heads(self):
        """Non-empty grid lists of the model, found from the live objects: {address: cell}."""
        heads = {}
        for obj in self.model.objects.values():
            back = obj.heads[2].next
            if back is None:
                continue
            thing = back.partner
            while not isinstance(thing, R.Cell):
                thing = thing.prev
            heads[thing.name] = thing
        return heads

    def check(self, full=False):
        mem, m = self.emu.mem, self.model
        scalars = (('shared seed', mem.u32(O.G_RAND_SEED), m.shared.state),
                   ('60-list cursor', mem.u32(O.G_CURSOR_60), m.cursor60),
                   ('15-list cursor', mem.u32(O.G_CURSOR_15), m.cursor15),
                   ('sampled pool count', mem.u32(O.G_POOL_FREE_COUNT), m.pool_free_count),
                   ('frame', mem.u32(O.G_SIM_FRAME), m.frame & M32),
                   ('exclude mask', mem.u32(O.G_EXCLUDE_MASK), m.exclude_mask),
                   ('name count', mem.u32(O.G_NAME_COUNT), m.names.count & M32),
                   ('pool heads', tuple(mem.u32(POOL_TABLE + 16 * c + 12) for c in range(3)), tuple(m.pool.head)),
                   ('node free head', mem.u32(H_FREE_HEAD), self.ptr(m.handles.free)),
                   ('task count', mem.u32(O.G_TASK_COUNT), len(m.tasks.tasks)))
        for name, got, want in scalars:
            if got != want:
                self.bad('%s: original %s, model %s' % (name, self.show(got), self.show(want)))
        # the node free list: its first nodes, or all of it
        addr, node = mem.u32(H_FREE_HEAD), m.handles.free
        for _ in range(7000 if full else 16):
            if addr != self.ptr(node):
                self.bad('node free list: 0x%x, model 0x%x' % (addr, self.ptr(node)))
                break
            if node is None:
                break
            addr, node = mem.u32(addr), node.next
        # fixed lists
        for cell in [m.delete_list, m.always_draw, m.off_grid, m.run_active] + m.run15 + m.run60:
            self.check_chain(cell)
        # the grids: the same cells are non-empty, and each list is equal node by node
        blob = struct.unpack('<28800I', mem.read(O.G_GRID, 4 * 28800))
        mine = self.model_grid_heads()
        mine.pop(O.G_OFF_GRID, None)
        theirs = {O.G_GRID + 4 * i for i, head in enumerate(blob) if head}
        if theirs != set(mine):
            odd = sorted(theirs ^ set(mine))[:4]
            self.bad('non-empty grid cells differ: %s' % ' '.join('0x%x' % a for a in odd))
        for cell in mine.values():
            self.check_chain(cell)
        # objects
        for obj in m.objects.values():
            got = struct.unpack('<19I', mem.read(obj.addr, 0x4C))
            tag = obj.tag or {}
            want = (self.ptr(obj.heads[0].next), self.ptr(obj.heads[1].next), self.ptr(obj.heads[2].next),
                    obj.flags, obj.pos[0], obj.pos[1], obj.pos[2], obj.radius, obj.height,
                    obj.class_def.addr if obj.class_def is not None else 0,
                    obj.draw_half_width | obj.draw_height << 8, tag.get('props', 0), obj.vz,
                    tag.get('cname', 0), obj.angle, 0, 0, obj.seed, obj.vtable)
            if got != want:
                word = [i for i in range(19) if got[i] != want[i]][0]
                self.bad('object 0x%x word +0x%x: original 0x%x, model 0x%x' % (obj.addr, 4 * word, got[word], want[word]))
        # the name table
        keys = struct.unpack('<512I', mem.read(O.G_NAME_KEYS, 2048))
        objs = struct.unpack('<512I', mem.read(O.G_NAME_OBJS, 2048))
        for slot in range(512):
            key = m.names.keys[slot]
            if (keys[slot] == 0) != (key is None) or objs[slot] != self.ptr(m.names.objs[slot]):
                self.bad('name slot %d: original key 0x%x object 0x%x, model %r 0x%x'
                         % (slot, keys[slot], objs[slot], key, self.ptr(m.names.objs[slot])))
                break
            if key is not None and (full or m.names.objs[slot] is not None) and self.read_cstr(keys[slot]) != bytes(key):
                self.bad('name slot %d: original %r, model %r' % (slot, self.read_cstr(keys[slot]), bytes(key)))
                break
        # class definitions
        for definition in self.defs[1:]:
            count = len(definition.entries)
            got = struct.unpack('<%dI' % (2 + 2 * count), mem.read(definition.addr, 8 + 8 * count))
            want = [definition.lump, definition.generation]
            for name, resolved in definition.entries:
                want += [name, resolved]
            if got != tuple(want):
                self.bad('class definition 0x%x: %s, model %s' % (definition.addr, self.show(got), self.show(want)))
        # tasks
        for index, task in enumerate(m.tasks.tasks):
            got = struct.unpack('<IiII', mem.read(O.G_TASKS + 16 * index, 16))
            if got[:2] != (task.fn, task.priority) or got[3] != task.flags or self.read_cstr(got[2]) != task.name:
                self.bad('task %d: original %s, model %r' % (index, self.show(got), task))
        if not full:
            return
        for index in range(3):
            want = m.pool.free_list(index)
            addr, got = mem.u32(POOL_TABLE + 16 * index + 12), []
            while addr and len(got) <= len(want):
                got.append(addr)
                addr = mem.u32(addr)
            if got != want:
                self.bad('pool free list of class %d differs' % index)
        blob = mem.read(NODE_BASE, NODE_SIZE * len(m.handles.nodes))
        for node in m.handles.nodes:
            got = struct.unpack_from('<4I', blob, node.index * NODE_SIZE)
            stale = [isinstance(v, R.Iterator) for v in (node.next, node.prev, node.partner, node.obj)]
            want = [0 if s else self.ptr(v) for s, v in zip(stale, (node.next, node.prev, node.partner, node.obj))]
            if any(g != w for g, w, s in zip(got, want, stale) if not s):
                self.bad('node %d memory %s, model %s' % (node.index, self.show(got), self.show(want)))
                break


# ---------------------------------------------------------------------------------------
# Random material
# ---------------------------------------------------------------------------------------
SIZES = (0x4C, 0x4C, 0x148, 0x148, 0x180, 0x248, 0x3C8, 0x500, 0x590)
EDGE_COORDS = (0.0, -0.0, -0.5, -0.99, -1.0, -1.5, 0.5, 255.0, 255.99, 256.0, 256.5, -255.0, -256.0, -256.5,
               -257.0, 511.9, 512.0, 15103.0, 15104.0, 15359.9, 15360.0, 15361.0, -15360.0, -15360.9,
               -15361.0, -15616.0, 20000.0, -20000.0, 3.0e9, -3.0e9, 1.0e20)
NAMES = (b'alpha', b'ALPHA', b'Alpha', b'beta', b'gamma', b'knight', b'door1', b'door2', b'x', b'',
         b'a longer name with spaces', b'Zz', b'zz', b'boss', b'k1', b'k2', b'k3', b'k4', b'k5', b'k6')
PROP_LISTS = ([b'speed=3'], [b'name=alpha'], [b'name="beta"', b'hide=1'], [b'name=alpha', b'name=gamma', b'x=1'],
              [b'hide=1'], [b'Name=upper', b'NAME=x'], [b'name=ALPHA'], [b'name="unterminated'],
              [b'names=x', b'name', b'name='], [b'name=knight'], [b'name=knight', b'default=1'],
              [b'name="door1"', b'name="door2"'], [b'hide=0', b'name=Zz'],
              [b'name=zz', b'hide=7'], [b'name=boss'], [b'name=k1'], [b'name=k2'], [b'name=k3'], [b'name=k4'],
              [b'name=k5', b'name=k6', b'name=k1'], [b'name=""'], [b'name="a longer name with spaces" trailing'], [])


def rand_coord(rng, near=None, spread=300.0):
    roll = rng.random()
    if near is not None and roll < 0.62:
        return f32(max(min(R.to_float(near), 1e6), -1e6) + rng.uniform(-spread, spread))
    if roll < 0.80:
        return f32(rng.choice((-1500.0, -300.0, 0.0, 280.0, 900.0, 2400.0)) + rng.uniform(-140.0, 140.0))
    if roll < 0.92:
        return f32(rng.uniform(-3000.0, 3000.0))
    if roll < 0.985:
        return f32(rng.choice(EDGE_COORDS) + rng.choice((0.0, 0.0, 256.0 * rng.randrange(-8, 9))))
    return rng.getrandbits(32)


def rand_pos(rng, near=None, spread=300.0):
    near = near or (None, None, None)
    return (rand_coord(rng, near[0], spread), rand_coord(rng, near[1], spread),
            f32(rng.choice((0.0, 0.0, 10.0, -40.0, 200.0)) + rng.uniform(-30.0, 30.0)))


def rand_box(rng, around):
    if rng.random() < 0.02:
        return (tuple(rng.getrandbits(32) for _ in range(3)), tuple(rng.getrandbits(32) for _ in range(3)))
    centre = [R.to_float(v) for v in rand_pos(rng, around, 200.0)]
    centre = [max(min(c, 1e7), -1e7) for c in centre]
    half = rng.choice(HALF_SIZES)
    half_z = rng.choice((half, 72.0, 1000.0, 100000.0))
    lo = (f32(centre[0] - half), f32(centre[1] - half * rng.choice((1.0, 1.0, 0.3))), f32(centre[2] - half_z))
    hi = (f32(centre[0] + half), f32(centre[1] + half), f32(centre[2] + half_z))
    if rng.random() < 0.04:
        lo, hi = hi, lo
    if rng.random() < 0.02:
        hi = (hi[0], f32(rng.choice((1.0e12, 2147460000.0, 2147400000.0))), hi[2])
    return lo, hi


HALF_SIZES = ((0.0, 10.0, 24.0, 24.0, 48.0, 48.0, 96.0, 100.0, 100.0, 300.0, 300.0, 300.0, 700.0) * 5 +
              (1200.0,) * 6 + (6000.0, 40000.0))
LIMITS = (256, 256, 64, 16, 128, 512, 4, 2, 1, 0, 3)
MASKS = (None, None, None, 0x20000, 0x200000, 8, 0x8009)


class Driver:
    """The seeded script: which operations happen, at top level and inside callbacks."""

    def __init__(self, rig, cap=260):
        self.rig = rig
        self.rng = rig.rng
        self.cap = cap
        self.props = [rig.add_props(entries) for entries in PROP_LISTS]
        self.defs = [rig.add_def([b'model', b'tex'], 0), rig.add_def([], 0), rig.add_def([b'a', b'b', b'c'], 5)]
        self.p_new = 0.16
        self.dtor_ops = 0.15
        rig.script_run = self.in_run
        rig.script_dtor = self.in_dtor

    def live(self):
        return list(self.rig.model.objects.values())

    def pick(self, exclude_dying=True):
        objs = [o for o in self.rig.model.objects.values() if not (exclude_dying and o.addr in self.rig.dying)]
        return self.rng.choice(objs) if objs else None

    def alive(self, obj):
        return obj is not None and self.rig.model.objects.get(obj.addr) is obj and obj.addr not in self.rig.dying

    def new_op(self, near=None, flags=None):
        rng = self.rng
        if flags is None:
            flags = rng.choice((0, 0, 0, 0, 0x1809, 0x1809, 0x800, 0x2, 0x1000, 0x20, 0x8000, 0x20000, 0x200000))
        return ('new', rng.choice(SIZES), rand_pos(rng, near.pos if near else None),
                rng.choice(self.props) if rng.random() < 0.45 else 0,
                rng.choice(self.defs) if rng.random() < 0.15 else 0,
                rng.choice(('frame', 'frame', 'frame', 'frame', 'frame', 'r60', 'r60', 'r15', 'none')), flags,
                rng.choice(self.props) if rng.random() < 0.04 else 0)

    def random_op(self, me=None, inside=False):
        """One operation, chosen from the state of the MODEL (never from the original)."""
        rng, rig = self.rng, self.rig
        m = rig.model
        roll = rng.random()
        other = self.pick()
        target = me if self.alive(me) and rng.random() < 0.6 else other
        p_new = self.p_new if len(m.objects) > self.cap // 2 else max(self.p_new, 0.42)
        if target is None or (roll < p_new and len(m.objects) < self.cap):
            return self.new_op(target)
        roll = rng.random()
        addr = target.addr
        if roll < 0.24:
            return ('move', addr) + rand_pos(rng, target.pos, rng.choice((20.0, 60.0, 300.0, 300.0)))
        if roll < 0.36:
            was = rng.choice((target.tag['active'], target.tag['active'], 0, 1))
            return ('active', addr, was, rng.choice((480, 480, 1600, 600, 44000, 100, 0, 46341, 70000, 3000)))
        if roll < 0.50:
            lo, hi = rand_box(rng, target.pos)
            return ('box', lo, hi, rng.choice(LIMITS), rng.choice(MASKS))
        if roll < 0.54:
            return ('sphere', f32(rng.choice((30.0, 100.0, 400.0, 2000.0))), tuple(target.pos))
        if roll < 0.60:
            return (rng.choice(('frame', 'frame', 'r60', 'r15', 'stop')), addr)
        if roll < 0.66:
            return ('delete', addr)
        if roll < 0.70:
            return ('destroy', addr)
        if roll < 0.78:
            bit = rng.choice((0x8000, 0x8000, 0x8, 0x1, 0x800, 0x2, 0x80000, 0x20000, 0x200000, 0x1000, 0x4))
            return ('flags', addr, target.flags ^ bit)
        if roll < 0.81:
            return ('offgrid', addr)
        if roll < 0.84:
            return ('isoff', addr)
        if roll < 0.90:
            return ('byname', rng.choice(NAMES), rng.choice((2, 2, 3, 8, 64)))
        if roll < 0.92:
            return (rng.choice(('adraw', 'adraw1')), addr)
        if roll < 0.93 and not inside:
            return ('cleardraw',)
        return ('move', addr) + rand_pos(rng, target.pos, 40.0)

    def apply_inside(self, op):
        """Apply an operation chosen inside a callback to the model (it is logged and the
        original's stub replays it), and keep the script's own notes."""
        rig = self.rig
        result = rig.do_model(op)
        rig.count('in callback: ' + op[0])
        if op[0] == 'active' and op[1] in rig.model.objects:
            rig.obj(op[1]).tag['active'] = result
        return result

    def in_run(self, obj):
        rng = self.rng
        for _ in range(rng.choice((0, 0, 0, 1, 1, 1, 2, 3))):
            self.apply_inside(self.random_op(obj, inside=True))

    def in_dtor(self, obj):
        rng = self.rng
        if rng.random() >= self.dtor_ops:
            return
        for _ in range(rng.choice((1, 1, 2))):
            other = self.pick()
            if other is None:
                return
            roll = rng.random()
            if roll < 0.45:
                op = ('delete', other.addr)
            elif roll < 0.75:
                op = ('destroy', other.addr)
            elif roll < 0.85:
                op = ('stop', other.addr)
            else:
                lo, hi = rand_box(rng, obj.pos)
                op = ('box', lo, hi, 64, None)
            self.apply_inside(op)

    def top(self, op):
        result = self.rig.do(*op)
        if op[0] == 'active' and op[1] in self.rig.model.objects:
            self.rig.obj(op[1]).tag['active'] = result
        return result

    def environment(self):
        """What changes between ticks besides the objects: the mask, the frame number, the
        activity centres or the camera, a frozen game."""
        rng, rig = self.rng, self.rig
        m = rig.model
        if rng.random() < 0.10:
            self.top(('set', 'mask', rng.choice((0, 0x20000, 0x20000, 0x200000, 0x8000, 8))))
        if rng.random() < 0.30:
            objs = self.live()
            centres = tuple(tuple(o.pos) for o in rng.sample(objs, min(len(objs), rng.randrange(0, 5))))
            self.top(('set', 'centres', centres))
        if rng.random() < 0.08:
            self.top(('set', 'cull', rng.choice((0, 0, 1))))
        if rng.random() < 0.15:
            self.top(('set', 'focus', rand_pos(rng)))
        if rig.frozen or rng.random() < 0.03:
            self.top(('set', 'frozen', rng.choice((0, 0, 1))))
        if rng.random() < 0.03:
            self.top(('set', 'generation', rng.choice((0, 5, 9))))
        frame = m.frame + 1 if rng.random() < 0.93 else rng.choice((0, 59, 60, 14, 15, 899, 0x7FFFFFFF, 123456, m.frame))
        self.top(('set', 'frame', frame & 0x7FFFFFFF))


def run_scenario(name, text, body, elf, seed, fpu='ps2'):
    if not wanted(name):
        return None
    started = time.time()
    rig = Rig(elf, '%s/%s' % (OPTIONS['seed'], seed), fpu)
    try:
        extra = body(rig) or ''
    except Diverged:
        extra = 'stopped at the first divergence'
    except (EmuError, O.ObjectError, R.HandleError, R.PoolError) as exc:
        rig.bad('scenario stopped: %s: %s' % (type(exc).__name__, exc))
        extra = 'stopped by an error'
    report(name, rig.failures, rig.steps, text + (' (%s)' % extra if extra else ''), rig.examples)
    if OPTIONS['verbose']:
        print('        %.0f s' % (time.time() - started))
    return rig


# ---------------------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------------------
def scenario_create(rig):
    """Construction: every field, the seed draw, the grid list, the name table."""
    driver = Driver(rig, cap=420)
    rng = rig.rng
    made = refused = 0
    for step in range(scaled(1500)):
        if step % 97 == 0:
            driver.top(('set', 'generation', rng.choice((0, 5, 9, 9))))
        if len(rig.model.objects) > 400 or (rig.model.objects and rng.random() < 0.18):
            driver.top((rng.choice(('destroy', 'destroy', 'delete')), driver.pick().addr))
            if rng.random() < 0.3:
                driver.top(('flush',))
            continue
        result = driver.top(driver.new_op(driver.pick() if rng.random() < 0.5 else None))
        made += 1 if result else 0
        refused += 0 if result else 1
    hidden = sum(1 for o in rig.model.objects.values() if rig.model.is_off_grid(o))
    return '%d objects constructed, %d refused, %d of the survivors off the grid' % (made, refused, hidden)


def scenario_grid(rig):
    """Movement between cells, grid B, the off-grid list, the always-draw list."""
    driver = Driver(rig, cap=160)
    rng = rig.rng
    for _ in range(120):
        driver.top(driver.new_op(None, rng.choice((0, 0, 0x800, 0x1809, 0x2))))
    for _ in range(scaled(3000)):
        obj = driver.pick()
        roll = rng.random()
        if roll < 0.55:
            driver.top(('move', obj.addr) + rand_pos(rng, obj.pos, rng.choice((5.0, 80.0, 400.0))))
        elif roll < 0.65:
            driver.top(('flags', obj.addr, obj.flags ^ rng.choice((0x800, 0x800, 0x2, 0x1000))))
        elif roll < 0.72:
            driver.top(('offgrid', obj.addr))
        elif roll < 0.80:
            driver.top(('isoff', obj.addr))
        elif roll < 0.86:
            driver.top((rng.choice(('adraw', 'adraw1')), obj.addr))
        elif roll < 0.88:
            driver.top(('cleardraw',))
        elif roll < 0.92:
            driver.top(('set', 'mask', rng.choice((0, 0x2, 0x800, 0x20000))))
        elif roll < 0.96 and len(rig.model.objects) > 60:
            driver.top(('destroy', obj.addr))
        else:
            driver.top(driver.new_op(obj))
    # obj_linkToGrid: a block that was not built by the constructor (the prediction copy's case)
    linked = 0
    for flags in (0, 0x800, 0x2, 0x802, 0x20000):
        for pos in ((f32(10.0), f32(10.0), 0), (f32(-0.5), f32(-300.0), 0), (f32(20000.0), 0, 0), (0, f32(-15361.0), 0),
                    (f32(15359.0), f32(15359.0), 0), (rig.rng.getrandbits(32), rig.rng.getrandbits(32), 0)):
            rig.steps += 1
            addr = rig.ecall(POOL_NEW, 0x4C)
            want = rig.model.pool.new(0x4C)
            obj = O.GameObject(want)
            obj.flags, obj.pos, obj.radius, obj.height, obj.draw_half_width, obj.draw_height = flags, list(pos), 0, 0, 0, 0
            obj.vtable, obj.tag = 0, {}
            rig.emu.mem.w32(addr + 0xC, flags)
            rig.emu.mem.write(addr + 0x10, struct.pack('<3I', *pos))
            rig.ecall(A['obj_linkToGrid'], addr)
            rig.model.link_to_grid(obj)
            rig.model.objects[want] = obj
            if addr != want:
                rig.bad('pool address')
            rig.check()
            linked += 1
    return '%d first links through obj_linkToGrid' % linked


def scenario_query(rig):
    """The box and sphere queries: which objects, in which order, and where they stop."""
    driver = Driver(rig, cap=400)
    rng = rig.rng
    for _ in range(330):
        driver.top(driver.new_op(driver.pick() if rng.random() < 0.7 else None,
                                 rng.choice((0, 0, 0, 0x1, 0x8, 0x4, 0x800, 0x20000, 0x200000, 0x8000, 0x9))))
    counts = {'box': 0, 'results': 0, 'cut': 0, 'sphere': 0, 'name': 0}
    for step in range(scaled(4000)):
        roll = rng.random()
        obj = driver.pick()
        if roll < 0.62:
            lo, hi = rand_box(rng, obj.pos if rng.random() < 0.8 else None)
            limit = rng.choice(LIMITS)
            found = driver.top(('box', lo, hi, limit, rng.choice(MASKS)))
            counts['box'] += 1
            counts['results'] += len(found)
            counts['cut'] += 1 if limit >= 2 and len(found) == limit - 1 else 0
        elif roll < 0.72:
            driver.top(('sphere', f32(rng.choice((0.0, 30.0, 100.0, 400.0, 2000.0, -5.0))), tuple(obj.pos)))
            counts['sphere'] += 1
        elif roll < 0.80:
            driver.top(('byname', rng.choice(NAMES), rng.choice((2, 2, 3, 8, 64))))
            counts['name'] += 1
        elif roll < 0.93:
            driver.top(('move', obj.addr) + rand_pos(rng, obj.pos, rng.choice((5.0, 40.0, 300.0))))
        elif roll < 0.96:
            driver.top(('flags', obj.addr, obj.flags ^ rng.choice((0x1, 0x8, 0x4, 0x20000, 0x200000, 0x800))))
        elif roll < 0.98:
            driver.top(('offgrid', obj.addr))
        else:
            driver.top(('destroy', obj.addr))
            driver.top(driver.new_op(driver.pick()))
        if step % 500 == 0:
            radius = rng.choice((f32(24.0), f32(130.0), f32(0.0), f32(-10.0), f32(400.0)))
            height = rng.choice((f32(72.0), f32(0.0), f32(500.0)))
            for target in rng.sample(driver.live(), 12):
                target.radius, target.height = radius, height
                rig.emu.mem.w32(target.addr + 0x1C, radius)
                rig.emu.mem.w32(target.addr + 0x20, height)
    return ('%(box)d box queries returning %(results)d objects, %(cut)d of them cut off by the limit; '
            '%(sphere)d sphere queries; %(name)d name lookups' % counts)


def scenario_active(rig):
    """obj_updateActive: the answer, and the run list the object is on afterwards."""
    driver = Driver(rig, cap=220)
    rng = rig.rng
    for _ in range(200):
        driver.top(driver.new_op(driver.pick() if rng.random() < 0.6 else None, rng.choice((0, 0, 0, 0x80000, 0x8000))))
    changes = 0
    for step in range(scaled(3000)):
        obj = driver.pick()
        roll = rng.random()
        if roll < 0.70:
            radius = rng.choice((480, 480, 1600, 600, 44000, 100, 0, 46340, 46341, 70000, 3000, -480, 1 << 20))
            was = rng.choice((obj.tag['active'], obj.tag['active'], obj.tag['active'], 0, 1, 2))
            before = obj.heads[1].next
            driver.top(('active', obj.addr, was, radius))
            changes += 1 if obj.heads[1].next is not before else 0
        elif roll < 0.80:
            driver.top(('move', obj.addr) + rand_pos(rng, obj.pos, 500.0))
        elif roll < 0.84:
            driver.top(('flags', obj.addr, obj.flags ^ 0x80000))
        elif roll < 0.88:
            driver.top((rng.choice(('frame', 'r60', 'r15', 'stop')), obj.addr))
        else:
            if rng.random() < 0.5:
                objs = driver.live()
                driver.top(('set', 'centres', tuple(tuple(o.pos) for o in rng.sample(objs, rng.randrange(0, 5)))))
            if rng.random() < 0.3:
                driver.top(('set', 'cull', rng.choice((0, 1))))
            if rng.random() < 0.5:
                driver.top(('set', 'focus', rand_pos(rng, obj.pos, 700.0)))
    return '%d calls changed the run list' % changes


def scenario_run(rig, ticks=2000, cap=260, net=0):
    """runObjects with every virtual run and destructor scripted."""
    driver = Driver(rig, cap=cap)
    rng = rig.rng
    if net:
        driver.top(('set', 'net', 1))
    for _ in range(120):
        driver.top(driver.new_op(driver.pick() if rng.random() < 0.6 else None))
    twice = same_tick = 0
    low, high, total = 1 << 30, 0, 0
    for _ in range(scaled(ticks)):
        driver.environment()
        while len(rig.model.objects) < 70:
            driver.top(driver.new_op(driver.pick() if rng.random() < 0.6 else None))
        low, high, total = min(low, len(rig.model.objects)), max(high, len(rig.model.objects)), total + len(rig.model.objects)
        for _ in range(rng.choice((0, 0, 1, 2))):
            driver.top(driver.random_op())
        rig.steps += 1
        rig.count('runobjects')
        rig.log, rig.pos, rig.diverged = [], 1, False
        born = set(rig.model.objects)
        rig.do_model(('runobjects',))
        runs = [entry[1] for entry in rig.log if entry[0] == 'run']
        twice += len(runs) - len(set(runs))
        same_tick += sum(1 for addr in set(runs) if addr not in born)
        try:
            rig.do_emu(('runobjects',))
        except EmuError as exc:
            rig.bad('runObjects stopped: %s' % exc)
            raise Diverged()
        if not rig.diverged and rig.pos != len(rig.log):
            rig.bad('runObjects: the original made fewer callbacks than the model')
            rig.diverged = True
        rig.check(full=rig.steps % 32 == 0)
        if rig.diverged:
            raise Diverged()
    stats = rig.stats
    inside = sum(v for k, v in stats.items() if k.startswith('in callback'))
    return ('%d ticks on %d to %d live objects (mean %d), %d run calls and %d destructor calls in the same order; '
            '%d operations made inside them '
            '(%d creations, %d deferred deletes, %d direct destroys, %d moves, %d run-list changes, %d queries); '
            'one address was run twice in one tick %d times; an address that held no object when the tick began '
            'was run in that tick %d times'
            % (stats.get('runobjects', 0), low, high, total // max(stats.get('runobjects', 0), 1),
               stats.get('run calls', 0), stats.get('destructor calls', 0), inside,
               stats.get('in callback: new', 0), stats.get('in callback: delete', 0), stats.get('in callback: destroy', 0),
               stats.get('in callback: move', 0),
               sum(stats.get('in callback: ' + k, 0) for k in ('frame', 'r15', 'r60', 'stop', 'active')),
               sum(stats.get('in callback: ' + k, 0) for k in ('box', 'sphere', 'byname')), twice, same_tick))


def scenario_order_cases(rig):
    """Hand-made cases of the ordering rules, each compared with the original."""
    m = rig.model
    origin = (0, 0, 0)
    facts = []

    def new(then='frame', pos=origin):
        return rig.do('new', 0x4C, pos, 0, 0, then, 0, 0)

    def tick(script=None):
        rig.script_run = script or (lambda obj: None)
        rig.steps += 1
        rig.log, rig.pos, rig.diverged = [], 1, False
        rig.do_model(('runobjects',))
        rig.do_emu(('runobjects',))
        if rig.pos != len(rig.log):
            rig.bad('fewer callbacks than the model')
        rig.check(full=True)
        return [entry[1] for entry in rig.log if entry[0] == 'run']

    # 1. last linked runs first
    a, b, c = new(), new(), new()
    facts.append(('every-frame list is last in, first out', tick() == [c, b, a]))
    # 2. the every-frame list, then the 15-list, then the 60-list
    rig.do('set', 'frame', 61)                  # 61 % 15 == 1, 61 % 60 == 1: the first slow lists handed out
    s60, s15 = new('r60'), new('r15')
    facts.append(('order of the three lists', tick() == [c, b, a, s15, s60]))
    # 3. a new every-frame object first runs in the next tick, and then first of all
    made = []

    def create_once(obj):
        if obj.addr == b and not made:
            made.append(rig.do_model(('new', 0x4C, origin, 0, 0, 'frame', 0, 0)))
    first = tick(create_once)
    second = tick()
    facts.append(('created in the every-frame walk: not run in that tick', made[0] not in first))
    facts.append(('...and first in the next', second[0] == made[0]))
    # 4. created in the every-frame walk and handed to the slow list of this very frame: runs in this tick
    rig.do('set', 'frame', m.cursor60 + 1 + 60 * 7)
    made60 = []

    def create_slow(obj):
        if obj.addr == a and not made60:
            made60.append(rig.do_model(('new', 0x4C, origin, 0, 0, 'r60', 0, 0)))
    order = tick(create_slow)
    facts.append(('created during the tick on the 60-list of this frame: runs in the SAME tick', made60[0] in order))
    # 5. an object that goes inactive during its run can run twice in one tick
    rig.do('set', 'cull', 0)
    rig.do('set', 'centres', ())
    rig.do('set', 'frame', m.cursor60 + 1 + 60 * 9)

    def go_inactive(obj):
        if obj.addr == c and obj.heads[1].next.partner.prev is not None and rig.log.count(('run', c)) == 1:
            rig.do_model(('active', c, 1, 480))
    order = tick(go_inactive)
    facts.append(('leaving the every-frame list for the 60-list of this frame: runs TWICE in the tick', order.count(c) == 2))
    # 6. obj_runEveryFrame on an object that is already there moves it to the front
    rig.do('frame', a)
    order = tick()
    facts.append(('relinking moves an object to the front', order[0] == a))
    # 7. deleted objects do not run, stay in the grid for queries, and are destroyed at the next tick
    rig.do('delete', b)
    lo, hi = (f32(-5.0),) * 3, (f32(5.0),) * 3
    seen = rig.do('box', lo, hi, 256, None)
    facts.append(('a deleted object is still returned by the box query', b in seen))
    order = tick()
    facts.append(('...does not run, and is gone after the next tick', b not in order and b not in m.objects))
    # 8. flag 0x8000 skips the run but not the walk; the exclude mask skips both
    rig.do('flags', a, 0x8000)
    order = tick()
    facts.append(('flag 0x8000 is not run', a not in order))
    rig.do('flags', a, 0x20000)
    rig.do('set', 'mask', 0x20000)
    order = tick()
    facts.append(('an object the exclude mask names is not run', a not in order))
    seen = rig.do('box', lo, hi, 256, 0)
    facts.append(('flag 0x20000 is never returned by the box query, whatever the mask', a not in seen))
    rig.do('set', 'mask', 0)
    order = tick()
    facts.append(('...and runs again without the mask', a in order))
    # 9. the box query: rows ascend in y, columns in x, a cell is newest first
    p = [new('none', (f32(x), f32(y), 0)) for x, y in ((1300.0, 1300.0), (1010.0, 1300.0), (1300.0, 1010.0),
                                                      (1010.0, 1010.0), (1011.0, 1011.0))]
    box = ((f32(1005.0), f32(1005.0), f32(-1.0)), (f32(1305.0), f32(1305.0), f32(1.0)))
    seen = rig.do('box', box[0], box[1], 256, None)
    facts.append(('box query order: y cell, then x cell, then newest first', list(seen) == [p[4], p[3], p[2], p[1], p[0]]))
    rig.do('move', p[3], f32(1010.0), f32(1010.0), 0)
    seen = rig.do('box', box[0], box[1], 256, None)
    facts.append(('a move call puts the object first in its cell, even without leaving it', list(seen)[:2] == [p[3], p[4]]))
    seen = rig.do('box', box[0], box[1], 3, None)
    facts.append(('the limit keeps the first limit - 1 in walk order', list(seen) == [p[3], p[4]]))
    # 10. the constructor reads 'hide' before it stores the property list
    hide = rig.add_props([b'hide=1'])
    h = rig.do('new', 0x4C, origin, hide, 0, 'none', 0, 0)
    facts.append(('a hide property does NOT take a pooled object off the grid in the base constructor',
                  not m.is_off_grid(m.objects[h])))
    h2 = rig.do('new', 0x4C, origin, 0, 0, 'none', 0, hide)
    facts.append(('...only a stale list in an unzeroed block does', m.is_off_grid(m.objects[h2])))
    # 11. the seed: one draw per constructed object, none for a refused allocation
    before = m.shared.state
    n = new('none')
    one = R.Lcg(before)
    one.draw()
    facts.append(('one shared draw per constructor', m.shared.state == one.state and m.objects[n].seed == one.state >> 16))
    rig.script_run = lambda obj: None
    for name, ok in facts:
        if not ok:
            rig.bad('the model does not show: ' + name)
    return '%d ordering facts hold in the model and every step matched the original' % len(facts)


def scenario_reaper(rig, net=0):
    """The low-memory reaper: a nearly full pool, expendable objects in grid B."""
    driver = Driver(rig, cap=1200)
    driver.p_new = 0.05
    driver.dtor_ops = 0.12
    rng = rig.rng
    m = rig.model
    if net:
        driver.top(('set', 'net', 1))
    driver.top(('set', 'cull', 0))
    # the sweep visits cells 16f+1 .. 16f+16: put the props in rows 60..63 so that frames 450..480 cross them
    def prop_pos():
        return (f32(rng.uniform(-15360.0, 15359.0) if rng.random() < 0.5 else rng.uniform(-3000.0, 3000.0)),
                f32(rng.uniform(0.0, 1023.0)), f32(rng.uniform(-20.0, 20.0)))

    def fill(target_free):
        while m.pool.count_free() > target_free:
            flags = rng.choice((0x1809, 0x1809, 0x1809, 0x809, 0x1000, 0x1800, 0))
            op = ('new', 0x148, prop_pos(), 0, 0, rng.choice(('none', 'none', 'frame', 'r60')), flags, 0)
            rig.do(*op)

    reaped, low, refused = 0, 1056, 0
    phases = ((320, 0, 28), (290, 0, 30), (250, 1, 30), (190, 0, 30), (150, 1, 28), (60, 0, 26), (0, 0, 24))
    for target_free, focus_near, ticks in phases:
        fill(target_free)
        if target_free == 0:
            for _ in range(6):                  # nothing is free: no object, no seed draw
                seed = m.shared.state
                made = rig.do('new', rng.choice((0x4C, 0x148, 0x590)), prop_pos(), 0, 0, 'frame', 0, 0)
                refused += 1 if made == 0 and m.shared.state == seed else 0
        driver.top(('set', 'focus', (f32(rng.uniform(-2000.0, 2000.0)), f32(500.0), 0) if focus_near else
                    (f32(9.0e6), f32(9.0e6), 0)))
        frame = 448 + 14400 * rng.randrange(0, 3)       # a multiple of 64: the pool is sampled at once
        for _ in range(max(ticks // 4, 6) if OPTIONS['quick'] else ticks):
            driver.top(('set', 'frame', frame))
            frame += 1
            if rng.random() < 0.4:
                driver.top(driver.random_op())
            rig.steps += 1
            rig.count('runobjects')
            rig.log, rig.pos, rig.diverged = [], 1, False
            rig.do_model(('runobjects',))
            first_run = next((i for i, e in enumerate(rig.log) if e[0] == 'run'), len(rig.log))
            reaped += sum(1 for e in rig.log[:first_run] if e[0] == 'dtor')
            low = min(low, m.pool.count_free())
            rig.do_emu(('runobjects',))
            if not rig.diverged and rig.pos != len(rig.log):
                rig.bad('runObjects: the original made fewer callbacks than the model')
                rig.diverged = True
            rig.check(full=rig.steps % 16 == 0)
            if rig.diverged:
                raise Diverged()
    return ('%d ticks with the pool between %d and 320 free blocks; %d destructor calls before the run walks '
            '(reaper victims, their cascades and the delete list); %d allocations refused by the full pool, %d '
            'of them checked to leave the shared seed alone'
            % (rig.stats.get('runobjects', 0), low, reaped, rig.dumps, refused))


def scenario_walkers(rig):
    """The whole-world walkers, the class lookup, the delete-list flush and level teardown."""
    driver = Driver(rig, cap=300)
    rng = rig.rng
    rig.script_walk = lambda obj: [driver.apply_inside(driver.random_op(obj, inside=True))
                                   for _ in range(rng.choice((0, 0, 0, 1)))]
    rounds = 4 if OPTIONS['quick'] else 16
    found = 0
    for round_no in range(rounds):
        for _ in range(140):
            driver.top(driver.new_op(driver.pick() if rng.random() < 0.6 else None))
        for obj in rng.sample(driver.live(), 14):
            driver.top(('retype', obj.addr))
        for _ in range(30):
            driver.top(driver.random_op())
        driver.top(('set', 'mask', rng.choice((0, 0, 0x20000, 0x800))))
        driver.top(('foreach', 'grid'))
        driver.top(('foreach', 'run'))
        for name in (b'10GameObject', b'7Player1', b'GameObject', b'8Creature'):
            for limit in (rng.choice((2, 3, 5)), rng.choice((9, 40)), 512):
                found += len(driver.top(('byclass', name, limit)))
        for _ in range(12):
            target = driver.pick()
            if target is not None:
                driver.top(('delete', target.addr))
        driver.top(('flush',))
        for _ in range(8):
            target = driver.pick()
            if target is not None:
                driver.top(('delete', target.addr))
        driver.top(('set', 'mask', rng.choice((0, 0x20000, 0x8))))
        driver.top(('deleteall',))
        if rig.model.objects:
            rig.bad('objects left after teardown')
        if rig.model.pool.count_free() != 1056:
            rig.bad('pool not empty after teardown')
        driver.top(('set', 'mask', 0))
    return ('%d rounds of build, walk, flush and teardown; %d walker callbacks; the class lookups returned %d objects'
            % (rounds, rig.stats.get('walk calls', 0), found))


def scenario_tasks(rig):
    """The task list: sorted insertion, removal, the cursor under changes, tasks_run."""
    rng = rig.rng
    m = rig.model
    mem = rig.emu.mem
    rig.do('tremove', 0x14B168)                 # the draw task would call the real renderer
    names = [b'task%d' % i for i in range(len(rig.STUB_TASKS))] + [b'runObjects', b'drawObjects', b'Task3', b'']
    order = []

    def in_task(fn):
        order.append(fn)
        for _ in range(rng.choice((0, 0, 0, 1, 1, 2))):
            roll = rng.random()
            stub = rng.choice(rig.STUB_TASKS)
            if roll < 0.40 and len(m.tasks.tasks) < 24:
                op = ('tadd', stub, rng.choice((0, 1, 10, 10, 11, 20, 25, 50, 125, 300, 1000, -1)),
                      names[rig.STUB_TASKS.index(stub)], rng.choice((0, 0, 1, 2)))
            elif roll < 0.75:
                op = ('tremove', fn if rng.random() < 0.4 else stub)
            elif roll < 0.85:
                op = ('trunning', rng.choice(names))
            else:
                op = ('tremove', A['runObjects']) if rng.random() < 0.2 else ('trunning', b'runObjects')
            rig.do_model(op)
            rig.count('in callback: ' + op[0])
    # a hand-made case first: the running task removes itself, something takes its place in
    # the table, something else is added in front of the cursor
    ta, tb, tc, slot, early = rig.STUB_TASKS[:5]
    rig.do('tadd', ta, 0, b'ta', 0)
    rig.do('tadd', tb, 0, b'tb', 0)
    rig.do('tadd', tc, 20, b'tc', 0)
    seen = []

    def case(fn):
        seen.append(fn)
        if fn == tb:
            rig.do_model(('tremove', tb))
            rig.do_model(('tadd', slot, 0, b'slot', 0))
            rig.do_model(('tadd', early, -5, b'early', 0))
    rig.script_task = case
    rig.do('tcall', 1, -1)
    if seen != [ta, tb, slot, tc]:
        rig.bad('the model does not show: a task that takes the place of the running task is called in the same pass')
    for fn in (ta, tc, slot, early):
        rig.do('tremove', fn)
    rig.script_task = in_task
    driver = Driver(rig, cap=80)
    for _ in range(40):
        driver.top(driver.new_op(None, 0))
    m.end_of_tick = lambda: [rig.m_call(name, (), 0) for name in ('rebuildAlive', 'checkAllDead', 'updateRumble')]
    rig.emu.stub(REBUILD_ALIVE, function=lambda e: rig.e_call('rebuildAlive', ()))
    rig.emu.stub(CHECK_ALL_DEAD, function=lambda e: rig.e_call('checkAllDead', ()))
    rig.emu.stub(UPDATE_RUMBLE, function=lambda e: rig.e_call('updateRumble', ()))

    def sync_pads():
        for index, pad in enumerate(m.pads):
            got = struct.unpack('<3I', mem.read(G_PADS + 0x58 * index + 8, 12))
            if got != (pad.held, pad.pressed, pad.edge2):
                rig.bad('pad %d words: %s, model %s' % (index, rig.show(got), rig.show((pad.held, pad.pressed, pad.edge2))))
        if ee_emu.s32(mem.u32(G_LOCKOUT)) != m.menu_lockout:
            rig.bad('menu lock-out: %d, model %d' % (ee_emu.s32(mem.u32(G_LOCKOUT)), m.menu_lockout))

    passes = 0
    for step in range(scaled(2500)):
        roll = rng.random()
        stub = rng.choice(rig.STUB_TASKS)
        if roll < 0.30 and len(m.tasks.tasks) < 24:
            rig.do('tadd', stub, rng.choice((0, 0, 1, 10, 10, 11, 20, 20, 25, 50, 125, 300, 1000, -1, 9)),
                   names[rig.STUB_TASKS.index(stub)], rng.choice((0, 0, 0, 1, 1, 2)))
        elif roll < 0.42:
            rig.do('tremove', stub if rng.random() < 0.9 else 0x12345678)
        elif roll < 0.50:
            rig.do('trunning', rng.choice(names))
        elif roll < 0.53:
            rig.do('tadd', A['runObjects'], 10, b'runObjects', 0)
        elif roll < 0.75:
            rig.do('tcall', *rng.choice(((1, -1), (1, -1), (0, 1), (0, -1), (2, -1), (0, 2), (3, -1), (1, 2))))
            passes += 1
        else:
            net = rng.choice((0, 0, 1))
            rig.do('set', 'net', net)
            rig.do('set', 'frozen', rng.choice((0, 0, 0, 1)))
            mem.w32(0x4F85B0, rng.choice((0, 1, 1)))        # g_gameLevelLoaded, g_inFrontend, g_numPlayers:
            mem.w32(0x41B510, rng.choice((0, 0, 1)))        # read by an empty loop only
            mem.w32(G_NUM_PLAYERS, rng.choice((0, 1, 4)))
            m.warmup_frames = rng.choice((0, 0, 0, 3))
            mem.w32(G_WARMUP, m.warmup_frames)
            m.menu_lockout = rng.choice((0, 0, 5, 1, -2))
            mem.w32(G_LOCKOUT, m.menu_lockout & M32)
            m.menu_lockout_hold = rng.choice((0, 0, 0, 1))
            mem.w32(G_LOCKOUT_HOLD, m.menu_lockout_hold)
            for index, pad in enumerate(m.pads):
                pad.held = rng.choice((0, 0, 0, 0x00100000, 0x40, 0x00F00000, 0x80000000))
                pad.pressed, pad.edge2 = rng.getrandbits(32), rng.getrandbits(32)
                mem.write(G_PADS + 0x58 * index + 8, struct.pack('<3I', pad.held, pad.pressed, pad.edge2))
            rig.do('trun', rng.choice((1, 1, 2, 2, 3, 0, -1)))
            sync_pads()
            passes += 1
    return ('%d passes of the table, %d task calls in the same order, %d additions and %d removals made by '
            'running tasks' % (passes, rig.stats.get('task calls', 0), rig.stats.get('in callback: tadd', 0),
                               rig.stats.get('in callback: tremove', 0)))


def scenario_vis(rig):
    """gameSetObjectVis, isNearView, game_rebuildAlivePlayers on a made-up player table."""
    driver = Driver(rig, cap=60)
    rng = rig.rng
    m = rig.model
    mem = rig.emu.mem
    for _ in range(40):
        driver.top(driver.new_op(driver.pick() if rng.random() < 0.6 else None, rng.choice((0, 0, 8))))
    camera = rig.emu.alloc(0x40)
    mem.w32(G_LOCAL_CAMERA, camera)
    answers = {'dialog': 0, 'local': 0}
    rig.emu.stub(DIALOG_OBJ, function=lambda e: answers['dialog'])
    rig.emu.stub(NET_IS_LOCAL, function=lambda e: (answers['local'] >> (e.r[4] & 3)) & 1)
    near = 0
    for step in range(scaled(3000)):
        rig.steps += 1
        objs = driver.live()
        count = rng.randrange(0, 5)
        players = [rng.choice(objs) if rng.random() < 0.8 else None for _ in range(count)]
        mem.w32(G_NUM_PLAYERS, count)
        for slot in range(4):
            mem.w32(G_PLAYERS + PLAYER_REC * slot + PLAYER_OBJ, players[slot].addr if slot < count and players[slot] else 0)
        dialog = rng.choice(objs) if rng.random() < 0.15 else None
        answers['dialog'] = dialog.addr if dialog else 0
        mode = rng.choice((0, 1, 1, 2, 5))
        cutscene = rng.choice((0, 0, 1))
        net = rng.choice((0, 1))
        mem.w32(camera + 0x34, mode)
        mem.w8(G_CUTSCENE, cutscene)
        rig.m_set('net', net)
        rig.e_set('net', net)
        focus = rand_pos(rng, rng.choice(objs).pos, 600.0)
        rig.m_set('focus', focus)
        rig.e_set('focus', focus)
        m.set_object_vis(dialog, mode, cutscene, players)
        rig.ecall(A['gameSetObjectVis'])
        got = (mem.s8(O.G_CULL_BY_CAMERA), tuple(struct.unpack('<3I', mem.read(O.G_ACTIVITY_CENTERS + 12 * i, 12))
                                                 for i in range(mem.s8(O.G_ACTIVITY_COUNT))))
        want = (m.cull_by_camera, tuple(tuple(c) for c in m.centres))
        if got != want:
            rig.bad('gameSetObjectVis: %s, model %s' % (rig.show(got), rig.show(want)))
        # the activity test and the near-view test under exactly this state
        for _ in range(3):
            target = rng.choice(objs)
            driver.top(('active', target.addr, rng.choice((0, 1)), rng.choice((480, 1600, 100, 44000))))
            pos = rand_pos(rng, rng.choice(objs).pos, 900.0)
            reach = f32(rng.choice((480.0, 503.0, 960.0, 1000.0, 0.0, 50.0)))
            want = m.is_near_view(pos, reach, players)
            got = rig.ecall(A['isNearView'], rig.vec(3, pos), f12=reach)
            near += want
            if got != want:
                rig.bad('isNearView: %d, model %d' % (got, want))
        answers['local'] = rng.randrange(16)
        alive, local, first = m.alive_players(players, lambda slot: (answers['local'] >> slot) & 1)
        mem.w32(G_LOCAL_COUNT, 0x33)
        rig.ecall(A['game_rebuildAlivePlayers'])
        got = (tuple(mem.u32(G_ALIVE + 4 * i) for i in range(mem.u32(G_ALIVE_COUNT))),
               tuple(mem.u32(G_LOCAL_ALIVE + 4 * i) for i in range(mem.u32(G_LOCAL_COUNT))),
               ee_emu.s32(mem.u32(G_LOCAL_FIRST)), mem.u32(0x4F8428))
        if got != (tuple(alive), tuple(local), first, 0x33):
            rig.bad('alive players: %s, model %s' % (rig.show(got), rig.show((alive, local, first))))
        if rng.random() < 0.3:
            target = rng.choice(objs)
            driver.top(('flags', target.addr, target.flags ^ 8))
        if rng.random() < 0.3:
            target = rng.choice(objs)
            driver.top(('move', target.addr) + rand_pos(rng, target.pos, 500.0))
    return '%d states; isNearView answered 1 in %d of %d calls' % (scaled(3000), near, 3 * scaled(3000))


def scenario_load(rig):
    """world_loadRecords and world_createObject with a recording factory."""
    driver = Driver(rig, cap=600)
    rng = rig.rng
    m = rig.model
    mem = rig.emu.mem
    rig.ecall(SET_FACTORY, rig.STUB_FACTORY)
    classes = (b'Prop', b'Torch', b'Skeleton', b'Player1', b'Line', b'Blocker', b'nothing', None)
    info = {}
    created = [0, 0]

    def factory(class_name, pos, angle, props):
        """The stand-in for world_objectFactory: build a base object (or none), link it,
        sometimes delete it at once as a constructor that gives up does."""
        rig.log.append(('factory', class_name, tuple(pos), angle, tuple(bytes(p) for p in (props or [])), info['props']))
        result = 0
        if class_name not in (b'nothing', None) or rng.random() < 0.3:
            op = ('new', rng.choice(SIZES), tuple(pos), info['key'], 0, rng.choice(('frame', 'r60', 'r60', 'r15', 'none')),
                  rng.choice((0, 0, 0x1809, 0x2)), 0)
            result = rig.do_model(op)
            if result and rng.random() < 0.08:
                rig.do_model(('delete', result))
            if result and rng.random() < 0.3:
                made = m.objects[result]
                rig.do_model(rng.choice((('move', result) + rand_pos(rng, made.pos, 300.0), ('r60', result),
                                         ('offgrid', result), ('box',) + rand_box(rng, made.pos) + (64, None))))
        rig.log.append(('end', result))
        created[1 if result else 0] += 1
        return m.objects.get(result) if result else None

    def load_state(obj, state):
        rig.log.append(('load', obj.addr, bytes(state)))

    loads = 0
    for round_no in range(scaled(120)):
        has_state = rng.random() < 0.5
        records = []
        for _ in range(rng.randrange(0, 40)):
            props = [bytes(p) for p in rng.choice(PROP_LISTS)] if rng.random() < 0.7 else []
            records.append(O.Record(rng.choice(classes), rng.randrange(-0x8000, 0x8000), rand_pos(rng), props,
                                    bytes(rng.getrandbits(8) for _ in range(8 * rng.randrange(0, 4)))))
        blob = O.RecordBlob(records, has_state)
        data = blob.build()
        base = rig.emu.alloc(len(data) + 16, align=8)
        mem.write(base, data)
        # where each record's property array lies, to give the objects their +0x2c
        offsets, at = [], 8
        for record in records:
            offsets.append(at)
            at += struct.unpack_from('<h', data, at + 4)[0]
        strings = base + blob.size
        for filter_only in ((0, 1) if rng.random() < 0.3 else (0,)):
            keep = {name for name in classes if rng.random() < 0.5}
            rig.ecall(SET_FILTER, rig.STUB_FILTER if rng.random() < 0.9 else 0)
            use_filter = mem.u32(O.G_SAVE_FILTER) != 0
            rig.steps += 1
            rig.log, rig.pos, rig.diverged = [], 0, False
            index = [0]

            def wrapped(class_name, pos, angle, props):
                while records[index[0]].props is not props:
                    index[0] += 1
                rec_at = base + offsets[index[0]]
                info['props'] = rec_at + 0x14
                rig.props.append((rec_at + 0x14, props))
                info['key'] = len(rig.props) - 1
                obj = factory(class_name, pos, angle, props)
                if obj is not None:
                    name_off = struct.unpack_from('<i', data, offsets[index[0]])[0]
                    obj.tag['cname'] = strings + name_off if name_off >= 0 else 0
                index[0] += 1
                return obj

            def save_filter(class_name):
                return rig.m_call('filter', (class_name,), 1 if class_name in keep else 0)
            consumed = m.load_records(blob, wrapped, bool(filter_only), save_filter if use_filter else None, load_state)
            got = rig.ecall(A['world_loadRecords'], base, filter_only, max_steps=30000000)
            if got != consumed:
                rig.bad('world_loadRecords returned %d, model %d' % (got, consumed))
            if not rig.diverged and rig.pos != len(rig.log):
                rig.bad('world_loadRecords: fewer callbacks than the model')
                rig.diverged = True
            if mem.u16(base + 2) & 2 == 0 or mem.u32(O.G_LOAD_STR_BASE) != strings:
                rig.bad('blob not marked as relocated, or the string base')
            rig.check(full=rig.steps % 8 == 0)
            if rig.diverged:
                raise Diverged()
            loads += 1
        # world_createObject: the fourth argument goes through to the factory
        for _ in range(3):
            rig.steps += 1
            key = rng.choice(driver.props)
            name = rng.choice(classes[:-1])
            pos, angle = rand_pos(rng), rng.randrange(0, 0x10000)
            rig.log, rig.pos, rig.diverged = [], 0, False
            info['props'], info['key'] = rig.props[key][0], key
            obj = O.create_object(name, pos, angle, rig.props[key][1], factory)
            if obj is not None:
                obj.tag['cname'] = rig.cstring(name)
            got = rig.ecall(A['world_createObject'], rig.cstring(name), rig.vec(0, pos), angle, rig.props[key][0])
            if got != (obj.addr if obj is not None else 0):
                rig.bad('world_createObject returned 0x%x, model %r' % (got, obj))
            rig.check()
            if rig.diverged:
                raise Diverged()
        if len(m.objects) > 420:
            rig.do('deleteall')
    return ('%d loads; the factory was called for %d records and made an object for %d of them'
            % (loads, created[0] + created[1], created[1]))


def scenario_marker(rig):
    """Player1_ctor and world_findFreeSpot with scripted terrain."""
    driver = Driver(rig, cap=200)
    rng = rig.rng
    m = rig.model
    mem = rig.emu.mem
    mem.w32(G_WORLD, 0x00ABC000)
    state = {'p_blocked': 0.2, 'p_high': 0.2}

    def terrain_blocked(radius, pos):
        answer = 0 if rng.random() >= state['p_blocked'] else rng.choice((R.ONE, 0x80000000, 1))
        return rig.m_call('blocked', (radius, tuple(pos)), answer)

    def terrain_height(radius, pos):
        centre_z = R.to_float(pos[2])
        value = centre_z + (rng.uniform(-30.0, 5.9) if rng.random() >= state['p_high'] else rng.choice((6.0, 6.5, 40.0)))
        return rig.m_call('height', (radius, tuple(pos)), f32(value))

    def e_blocked(emu):
        emu.f[0] = rig.e_call('blocked', (emu.f[12], struct.unpack('<3I', mem.read(emu.r[5] & M32, 12)))) & M32
        if emu.r[4] & M32 != 0x00ABC000:
            rig.bad('terrain test: world argument')
        return 0

    def e_height(emu):
        emu.f[0] = rig.e_call('height', (emu.f[12], struct.unpack('<3I', mem.read(emu.r[5] & M32, 12)))) & M32
        return 0
    rig.emu.stub(TERRAIN_BLOCKED, function=e_blocked)
    rig.emu.stub(TERRAIN_HEIGHT, function=e_height)
    for _ in range(150):
        driver.top(driver.new_op(driver.pick() if rng.random() < 0.8 else None, rng.choice((0, 0, 0, 1, 0x20000))))
    marker_props = [rig.add_props(entries) for entries in (
        [], [b'default=1'], [b'from=town'], [b'from=gate'], [b'name=east'], [b'from=town', b'name=east', b'default=1'],
        [b'from=cave', b'default=0'], [b'name=west'], [b'from=gate', b'name=east'])]
    spots = takes = fails = 0
    for step in range(scaled(1500)):
        rig.steps += 1
        state['p_blocked'] = rng.choice((0.0, 0.2, 0.2, 0.6, 1.0))
        state['p_high'] = rng.choice((0.0, 0.2, 0.5))
        anchor = driver.pick()
        if rng.random() < 0.6:
            # world_findFreeSpot alone
            centre = rand_pos(rng, anchor.pos, 60.0)
            spread, radius = rng.choice((36, 36, 0, 100, 400)), rng.choice((24, 14, 0, 60))
            any_height = rng.choice((0, 0, 1))
            rig.log, rig.pos, rig.diverged = [], 0, False
            want, ok = m.find_free_spot(centre, spread, radius, any_height, terrain_blocked, terrain_height)
            out, flag = rig.scratch + 0x200, rig.scratch + 0x210
            mem.w32(flag, 0x55555555)
            got_ptr = rig.ecall(A['world_findFreeSpot'], out, rig.vec(4, centre), spread, radius, flag, any_height)
            got = struct.unpack('<3I', mem.read(out, 12))
            if got_ptr != out or got != tuple(want) or mem.u32(flag) != (0x55555500 | ok):
                rig.bad('findFreeSpot: %s ok 0x%x, model %s ok %d' % (rig.show(got), mem.u32(flag), rig.show(want), ok))
            spots += 1
            fails += 0 if ok else 1
        else:
            # the marker constructor
            rank = rng.choice((0, 0, 1, 1, 2, 3, -1))
            gate = rng.choice((0, 0, 1))
            prev, entrance = rng.choice((b'town', b'cave', b'')), rng.choice((b'east', b'west', b''))
            key = rng.choice(marker_props)
            pos, angle = rand_pos(rng, anchor.pos, 80.0), rng.randrange(0, 0x10000)
            mem.w8(O.G_PLAYER_START_RANK, rank & 0xFF)
            mem.w8(G_GATE_TRAVEL, gate)
            mem.write(G_PREV_LEVEL, prev + b'\0')
            mem.write(G_ENTRANCE, entrance + b'\0')
            m.start_rank = rank
            before = (m.start_rank, [list(p) for p in m.spawn_pos], list(m.spawn_facing))
            rig.log, rig.pos, rig.diverged = [], 0, False
            addr = m.pool.new(0x4C)
            obj = m.player1_marker(addr, pos, angle, rig.props[key][1], prev, entrance, gate, terrain_blocked, terrain_height)
            obj.tag = {'props': rig.props[key][0], 'active': 0, 'cname': 0}
            got_addr = rig.ecall(POOL_NEW, 0x4C)
            rig.ecall(A['Player1_ctor'], got_addr, rig.vec(4, pos), angle, rig.props[key][0])
            got = (ee_emu.s32(mem.s8(O.G_PLAYER_START_RANK)),
                   [list(struct.unpack('<3I', mem.read(O.G_SPAWN_POS + 12 * i, 12))) for i in range(4)],
                   [mem.u16(O.G_SPAWN_FACING + 2 * i) for i in range(4)])
            want = (m.start_rank, [list(p) for p in m.spawn_pos], list(m.spawn_facing))
            if got_addr != addr or got != want:
                rig.bad('Player1_ctor: rank %d spawn %s, model rank %d %s'
                        % (got[0], rig.show(got[1][0]), want[0], rig.show(want[1][0])))
            takes += 1 if want != before or m.start_rank != rank else 0
            driver.top(('destroy', addr) if rng.random() < 0.7 else ('move', addr) + tuple(obj.pos))
        if not rig.diverged and rig.pos != len(rig.log):
            rig.bad('fewer terrain calls than the model')
            rig.diverged = True
        rig.check()
        if rig.diverged:
            raise Diverged()
        if rng.random() < 0.2:
            target = driver.pick()
            driver.top(('move', target.addr) + rand_pos(rng, anchor.pos, 50.0))
    return ('%d free-spot searches (%d ended without a spot), %d markers of which %d took the spawn slots'
            % (spots, fails, scaled(1500) - spots, takes))


# ---------------------------------------------------------------------------------------
def find_elf(args):
    for candidate in list(args) + [os.path.join(ROOT, 'SLUS_209.73'), 'SLUS_209.73']:
        if os.path.isfile(candidate):
            return candidate
    return None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = []
    while argv:
        item = argv.pop(0)
        if item == '--quick':
            OPTIONS['quick'] = True
        elif item == '-v':
            OPTIONS['verbose'] = True
        elif item == '--seed' and argv:
            OPTIONS['seed'] = int(argv.pop(0), 0)
        elif item == '-k' and argv:
            OPTIONS['filter'] = argv.pop(0)
        else:
            args.append(item)
    elf = find_elf(args)
    if elf is None:
        print('SKIP  SLUS_209.73 not found (pass its path); nothing was compared')
        return 0
    with open(elf, 'rb') as source:
        digest = hashlib.sha256(source.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('SKIP  %s is not the US v2.00 executable (sha256 %s); nothing was compared' % (elf, digest))
        return 0
    started = time.time()
    run_scenario('create', 'GameObject_ctor/dtor: all fields, the seed draw, grid list, name table, class definitions',
                 scenario_create, elf, 'create')
    run_scenario('order.cases', 'the ordering rules one by one', scenario_order_cases, elf, 'cases')
    run_scenario('run.offline', 'runObjects with scripted virtual runs and destructors', scenario_run, elf, 'run')
    run_scenario('run.net', 'the same in a net game', lambda rig: scenario_run(rig, 1000, 200, 1), elf, 'runnet')
    run_scenario('query', 'box, sphere and name queries on a moving world', scenario_query, elf, 'query')
    run_scenario('grid', 'cell moves, grid B, off-grid and always-draw lists', scenario_grid, elf, 'grid')
    run_scenario('active', 'obj_updateActive against centres and camera', scenario_active, elf, 'active')
    run_scenario('reaper.offline', 'the pool reaper', scenario_reaper, elf, 'reap')
    run_scenario('reaper.net', 'the pool reaper in a net game', lambda rig: scenario_reaper(rig, 1), elf, 'reapnet')
    run_scenario('walkers', 'forEach walkers, class lookup, flush, world_deleteAllObjects', scenario_walkers, elf, 'walk')
    run_scenario('tasks', 'task_add/remove/isRunning, tasks_call, tasks_run', scenario_tasks, elf, 'tasks')
    run_scenario('vis', 'gameSetObjectVis, isNearView, game_rebuildAlivePlayers', scenario_vis, elf, 'vis')
    run_scenario('load.records', 'world_loadRecords, world_createObject', scenario_load, elf, 'load')
    run_scenario('load.marker', 'Player1_ctor, world_findFreeSpot', scenario_marker, elf, 'marker')
    OPTIONS['scale'] = 0.2
    for fpu in ('ps2g1', 'chop', 'nearest'):
        run_scenario('query.' + fpu, 'the queries under adder model %s' % fpu,
                     lambda rig: scenario_query(rig), elf, 'query-' + fpu, fpu)
        run_scenario('active.' + fpu, 'the activity test under adder model %s' % fpu, scenario_active, elf,
                     'active-' + fpu, fpu)
        run_scenario('load.marker.' + fpu, 'the free-spot search under adder model %s' % fpu, scenario_marker, elf,
                     'marker-' + fpu, fpu)
    R.set_fpu('ps2')
    OPTIONS['scale'] = 1.0
    if COVERAGE[0] is not None and OPTIONS['filter'] is None:
        print('coverage of the original as executed here (basic blocks entered / basic blocks):')
        total_hit = total = 0
        for name, hit, count, missing in COVERAGE[0].rows():
            total_hit, total = total_hit + hit, total + count
            print('  %-28s %3d / %3d%s' % (name, hit, count, '' if hit == count or not OPTIONS['verbose'] else
                                           '   never entered: ' + ' '.join('%06x' % a for a in missing)))
        print('  %-28s %3d / %3d' % ('all', total_hit, total))
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d PASS, %d FAIL (seed %d%s, %.0f s)' % (
        len(RESULTS), len(RESULTS) - len(failed), len(failed), OPTIONS['seed'],
        ', quick' if OPTIONS['quick'] else '', time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
