#!/usr/bin/env python3
"""difftest_natives.py - the game's own script built-ins against tools/ref_natives.py.

Needs your own SLUS_209.73 (US v2.00); the properties about shipped scripts also need the
level scripts unpacked as scripts_raw/*.scr.  Without the executable nothing is run and the
exit status is 0; without the scripts those properties are skipped.

  python3 tools/difftest_natives.py [SLUS_209.73] [--scripts DIR] [--cases N] [--seeds N]
                                    [--quick] [--seed N] [-k TEXT] [-v]

    --scripts DIR  directory of *.scr files (default scripts_raw, or $CHAMPIONS_SCRIPTS)
    --cases N      random cases per built-in (default 60)
    --seeds N      random game states per shipped entry point (default 2)
    --quick        a sixth of the cases, one state per entry point, every fourth script
    --seed N       seed of everything random (default 20973); a seed repeats exactly
    -k TEXT        only the groups (machinery, builtins, scripts) or built-ins whose name
                   contains TEXT
    -v             print the first mismatches of every failing property, and the basic
                   blocks that were never entered

What is compared
    The ORIGINAL machine code runs in tools/ee_emu.py (an instruction interpreter, not a
    console): a built-in is entered through the real dispatcher scr_callNative 0x141050 on
    a script machine that the real scr_load and scr_registerNatives prepared from the real
    table 0x403370.  The model gets the same script image and a copy-on-write view of the
    same memory.  For every case these must be equal:
      result   the cell the dispatcher stores for the script (PRI), and its error word
      calls    every call-out, in order, with its arguments (strings and vectors by
               content, floats as 32-bit patterns, stack-passed words included)
      writes   the set of bytes stored outside the stack and the script image, and their
               final values
      seed     the shared seed 0x404464, and that it moved by exactly the model's draws
      script   the machine structure and the script's data, heap and stack (nested runs)
      faults   a case in which the original leaves mapped memory (it follows a null
               pointer) must be one in which the model raises HostFault, and vice versa
    Floats are compared as patterns: "equal" means identical under the interpreter's
    floating-point model ('ps2'), see docs/issues/dynamic-tests.md.

What runs for real and what is a stub
    Real: the 190 handlers and their helpers (0x1416d4-0x147a84), the script machine,
    script_runByName, the deferred queue, the post action, the quest- and profile-variable
    functions, the mission / medal / evil / flag / quest-list functions, the two player
    record copies, dialog_start, world_findObjectsByName and its first-match wrapper,
    obj_getPropStr, the three angle functions, the C library, the software floats, RTTI.
    Stubs: every entry of ref_natives.EXT and every virtual call (recording stubs; a
    seeded script decides what each returns and what it stores through its output
    pointers, the same script on both sides).  A call to an address that is neither real
    nor a known stub is reported as a failure, so nothing is stubbed by accident.

    Game state is constructed, not loaded: random player records, globals, quest
    variables, queue contents, and objects with random flags and fields that are entered
    in the real name table (several objects per name, removed entries, mixed case).
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
import ref_amx                                  # noqa: E402
import ref_core as C                            # noqa: E402
import ref_objects as O                         # noqa: E402
import ref_natives as N                         # noqa: E402
from ref_natives import EXT, VIRTUAL, M32, s32  # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False, 'cases': 60, 'seeds': 2,
           'scripts': os.environ.get('CHAMPIONS_SCRIPTS') or os.path.join(ROOT, 'scripts_raw')}
RESULTS = []

SCR_LOAD, SCR_INTERPRET, SCR_CALL_NATIVE, SCR_REGISTER = 0x13E8F8, 0x13ECF8, 0x141050, 0x141310
SCR_GET_ADDR = 0x1414A8
SCRIPT_LO, SCRIPT_HI = 0x13E6D0, 0x147AA8       # script machine, built-ins, helpers
RUNTIME_LO, RUNTIME_HI = 0x3A5000, 0x3CC000     # C library, software floats, RTTI, type-info getters
HELPERS = {'newWorld_netGate': 0x143D04, 'script_newWorldNoGate': 0x143E30, 'script_checkMonstersLeft_cb': 0x144198,
           'script_applyMonsterVal': 0x144494, 'script_applyCFlag': 0x1445FC, 'script_applyOFlag': 0x1447C4,
           'script_setNextWorld': 0x1472C4}
NATIVES_END = 0x147A84
MACHINERY = [                                   # real functions outside the script range: name, start, end
    ('script_queueDeferred', 0x1ED52C, 0x1ED5A0), ('script_runDeferred', 0x1ED5A0, 0x1ED650),
    ('script_runByName', 0x1ED694, 0x1ED728), ('vars_clearAll', 0x1ED728, 0x1ED778),
    ('vars_get', 0x1ED778, 0x1ED854), ('vars_set', 0x1ED854, 0x1ED974), ('vars_getByIndex', 0x1ED974, 0x1EDA08),
    ('script_clearDeferred', 0x1EDA08, 0x1EDA24), ('script_resetState', 0x1EDA78, 0x1EDA9C),
    ('script_setPostAction', 0x1EDA9C, 0x1EDAC0), ('script_runPostAction', 0x1EDAC0, 0x1EDB18),
    ('mission_isAvailable', 0x1BF698, 0x1BF6D0), ('mission_setAvailable', 0x1BF6D0, 0x1BF730),
    ('mission_isComplete', 0x1BF730, 0x1BF770), ('mission_setComplete', 0x1BF770, 0x1BF7E8),
    ('mission_getMedal', 0x1BF838, 0x1BF8D8), ('game_getEvil', 0x1BF8D8, 0x1BF8F8),
    ('game_setEvil', 0x1BF8F8, 0x1BF960), ('game_getMadeDecision', 0x1BF960, 0x1BF980),
    ('game_setMadeDecision', 0x1BF980, 0x1BF9E8), ('mission_grantMedal', 0x1BDB80, 0x1BDC98),
    ('player_setFlag', 0x1BE398, 0x1BE468), ('player_getFlag', 0x1BFB80, 0x1BFBA4),
    ('quest_add', 0x1D386C, 0x1D3968), ('quest_remove', 0x1D3968, 0x1D3ADC),
    ('game_countPlayersWithHp', 0x1EBEC8, 0x1EBF1C), ('jumpgate_getTravelState', 0x27DD68, 0x27DD74),
    ('profile_setVar', 0x22274C, 0x22289C), ('profile_getVar', 0x22289C, 0x222964),
    ('profile_append', 0x222A44, 0x222A84), ('game_savePlayerRecord', 0x1EC720, 0x1EC830),
    ('game_restorePlayerRecord', 0x1EB6F8, 0x1EB950), ('dialog_start', 0x22FA50, 0x22FBC0),
]
REAL_OTHER = {0x14BF58, 0x14F498, 0x14F4C0, 0x166630, 0x1666E0, 0x166798} | {start for _n, start, _e in MACHINERY}
A = {name: start for name, start, _end in MACHINERY}
TYPEINFO = {b'10GameObject': 0x3C7E10, N.TYPE_SCRIPT_GENERATOR: 0x3C7CD0, N.TYPE_MONSTER_TRIGGER: 0x3C8E40,
            N.TYPE_AUTO_CONTAINER: 0x3C9558, N.TYPE_TRIGGER: 0x3C3840}
STACK_LO, STACK_HI = EE.STACK_LO, EE.STACK_HI
SP = STACK_HI - 0x8000
VSLOTS = 40
LIBC_SCRATCH = (0x50C530, 0x50C800)     # the C library's own state (sprintf's reentrancy block and streams)

NAME_POOL = [b'gob', b'Gate1', b'boss', b'door_a', b'npc', b'chest', b'gen1', b'trig', b'cart', b'x']
VAR_POOL = [b'qa', b'qb', b'door', b'talked', b'stage', b'kills', b'q_long_name_1', b'z']
ENTRY_POOL = [b'alpha', b'beta', b'gamma', b'delta', b'firstBronze', b'firstSilver', b'firstGold', b'missing', b'']
TEXT_POOL = [b'hint1', b'hint2', b'title', b'body text', b'sword of testing', b'potion', b'', b'k']
LEVEL_POOL = [b'hub', b'cave1', b'town_2', b'', b'a_rather_long_level_name_for_the_buffer']
CLASS_POOL = [b'Goblin', b'Skeleton', b'Rat', b'Chest', b'Wisp']
QUEST_POOL = [b'Find it', b'Slay them', b'Return', b'q4', b'A', b'Escort the cart']
PROP_POOL = [b'orientation=3', b'orientation=-2', b'Orientation=9', b'orientation=77x', b'level=cave1',
             b'level=', b'levels=no', b'lump=fx.lmp', b'hide=1', b'script=alpha', b'orientation=']


def report(name, failures, count, text, examples=()):
    ok = not failures and count > 0
    RESULTS.append((name, ok))
    print('%s  %-30s %6d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in list(examples)[:6]:
            print('        ' + str(line)[:1500])
    sys.stdout.flush()


def f32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


class RealSet:
    def __init__(self, addresses):
        self.addresses = set(addresses)

    def __contains__(self, target):
        return (SCRIPT_LO <= target < SCRIPT_HI or RUNTIME_LO <= target < RUNTIME_HI or target in self.addresses)


class Under:
    """What a model Mem is laid over: the interpreter's memory; unmapped pages read as zero."""

    def __init__(self, mem):
        self.mem = mem

    def read(self, addr, size):
        if not self.mem.is_mapped(addr, size):
            return bytes(size)
        return self.mem.read(addr, size)


# ---------------------------------------------------------------------------------------
# The seeded script that answers call-outs, the same on both sides
# ---------------------------------------------------------------------------------------
class Responder:
    def __init__(self, seed, scene):
        self.rng = random.Random(seed)
        self.scene = scene
        self.blocks = 0

    def answer(self, name, args):
        rng, scene = self.rng, self.scene
        if name == 'virtual':
            slot = args[0]
            if slot == N.V_CONTAINS:
                return rng.choice((0, 0, 1))
            if slot == N.V_SEAT:
                return (tuple(f32(rng.uniform(-500, 500)) for _ in range(3)), rng.randrange(0x10000))
            return 0
        kind = EXT[name].ret
        if name in ('net_isLocalSlot', 'dialog_isOpen', 'memcard_isBusy', 'playerSel_isRunning'):
            return 1 if rng.random() < scene.bias.get(name, 0.4) else 0
        if name == 'net_getLocalPlayerSlot':
            return scene.medal_player if rng.random() < 0.5 else rng.randrange(4)
        if name == 'net_firstActiveSlot':
            return rng.randrange(4)
        if name == 'memcard_getState':
            return -1 if rng.random() < 0.5 else rng.randrange(7)
        if name in ('text_lookup', 'res_find', 'sound_playOnObject'):
            if name != 'text_lookup' and rng.random() < 0.25:
                return 0 if name == 'res_find' else -1
            return scene.token_base + 4 * rng.randrange(64)
        if name in ('hud_stepFade', 'text_drawWrappedCentered'):
            return rng.randrange(0, 129)
        if name == 'inventory_countItemByName':
            return rng.choice((0, 0, 1, 2, 7))
        if name == 'inventory_findItemBySubstring':
            return (-1, 0) if rng.random() < 0.4 else (rng.randrange(6), rng.randrange(3))
        if name == 'inventory_giveItem':
            return rng.randrange(12)
        if name == 'item_parseDescriptor':
            return scene.item_defs + 0x40 * rng.randrange(3)
        if name == 'player_itemWeight':
            return 0 if rng.random() < 0.3 else f32(rng.choice((0.5, 3.0, 12.0, 40.0, 500.0)))
        if name == 'pool_new':
            if rng.random() < 0.2 or self.blocks >= 8:
                return 0
            self.blocks += 1
            return scene.pool_base + 0x200 * (self.blocks - 1)
        if name == 'save_playerCopy':
            return scene.copy_buf + scene.copy_skew
        if name in ('world_collectObjectsInBox', 'world_forEachGridObject'):
            pool = [o['addr'] for o in scene.objects]
            rng.shuffle(pool)
            count = rng.randrange(len(pool) + 1)
            if name == 'world_collectObjectsInBox':
                count = min(count, max(args[2] - 1, 0))
            return pool[:count]
        if name == 'world_findObjectsByClass':
            return [o['addr'] for o in scene.objects if o['type'] == args[0]][:max(args[1] - 1, 0)]
        if name == 'MonsterTrigger_count':
            return rng.randrange(6)
        if name in ('Camera_getYaw', 'Camera_getPitch'):
            return rng.randrange(0x10000)
        if kind == 'i':
            return rng.randrange(4)
        return 0


class TestHost:
    """The model's call-outs in a compared case: recorded, answered by the Responder."""

    def __init__(self, responder, world):
        self.responder, self.world, self.log, self.game = responder, world, [], None

    def call(self, name, *args):
        self.log.append((name, args))
        value = self.responder.answer(name, args)
        kind = VIRTUAL[args[0]][2] if name == 'virtual' else EXT[name].ret
        if kind == 'L':
            return [self.world.objects[addr] for addr in value]
        return value if kind in 'ifP' else 0


# ---------------------------------------------------------------------------------------
# The original, in the interpreter
# ---------------------------------------------------------------------------------------
class Rig:
    def __init__(self, elf):
        emu = self.emu = EE(elf)
        mem = emu.mem
        self.slot = emu.alloc(0x40000, align=16)            # the script image
        self.cells = emu.alloc(0x400, align=16)             # result cells
        self.obj_base = emu.alloc(0x1000 * 200, align=16)   # objects
        self.aux_base = emu.alloc(0x100 * 64, align=16)     # weapon objects and vehicle paths
        self.strings = emu.alloc(0x20000, align=16)         # name keys, property strings, C strings
        self.tables = emu.alloc(0x8000, align=16)           # property pointer arrays
        self.vtables = emu.alloc(0x200 * 8, align=16)
        self.vstub = emu.alloc(8 * VSLOTS, align=8)
        self.pool_base = emu.alloc(0x200 * 8, align=16)
        self.copy_buf = emu.alloc(N.REC_SIZE + 0x10, align=16)
        self.item_defs = emu.alloc(0x40 * 3, align=16)
        self.token_base = emu.alloc(0x200, align=16)
        self.scratch = emu.alloc(0x400, align=16)
        for addr in (N.G_QUEST_VARS, N.G_POST_ACTION, N.G_DEFER_NAMES, N.G_DIALOG_DATA, N.G_DIALOG_MSG_ID,
                     N.G_GEN_NAMES, N.G_PLAYERS + 4 * N.REC_SIZE, N.G_PROFILE_VARS, O.G_NAME_KEYS, O.G_NAME_OBJS):
            if not mem.is_mapped(addr, 0x2000):
                mem.map(addr, 0x2000)
        self.real = RealSet(REAL_OTHER)
        emu.follow = self.real
        self.stub_addrs = set()
        self.calls = []
        self.responder = None
        self.dirty = set()
        for name, x in EXT.items():
            emu.stub(x.addr, function=self.make_stub(name, x), name=name)
            self.stub_addrs.add(x.addr)
        for slot in range(VSLOTS):
            addr = self.vstub + 8 * slot
            mem.w32(addr, 0x03E00008)                       # jr ra
            mem.w32(addr + 4, 0)
            emu.stub(addr, function=self.make_virtual(slot), name='virtual %d' % slot)
            self.stub_addrs.add(addr)
        emu.hook(SCR_INTERPRET, self.on_interpret)
        self.addr_log = []                                  # scr_getAddr calls: (return address, address, out)
        emu.hook(SCR_GET_ADDR, lambda e: self.addr_log.append((e.r[31] & M32, s32(e.r[5]), e.r[6] & M32)))
        # one table of virtual functions per class: slot 0 is the real type-info getter
        self.vtable_of, self.type_names = {}, {}
        for index, (type_name, getter) in enumerate(sorted(TYPEINFO.items())):
            table = self.vtables + 0x200 * index
            for slot in range(VSLOTS):
                mem.w32(table + 8 * slot, 0)
                mem.w32(table + 8 * slot + 4, self.vstub + 8 * slot)
            mem.w32(table + 4, getter)
            info = self.call(getter)                        # also builds the type-info object now
            assert mem.cstr(mem.u32(info)).encode('latin-1') == type_name, type_name
            self.vtable_of[type_name] = table
        for getter in N.POINTER_TYPES + (0x3C3788,):
            self.call(getter)
        self.weapon_vtable = self.vtables + 0x200 * len(TYPEINFO)
        for slot in range(VSLOTS):
            mem.w32(self.weapon_vtable + 8 * slot, 0)
            mem.w32(self.weapon_vtable + 8 * slot + 4, self.vstub + 8 * slot)
        self.unknown = {}
        self.pcs = set()
        self.base = self.slot
        self.image_size = 0
        self.snap = None
        self.script_bytes = None

    # ---- calling ------------------------------------------------------------------------
    def call(self, address, *args, max_steps=3000000):
        emu = self.emu
        emu._pending_call = emu._fresh_call = None
        emu.r[29] = SP
        return emu.call(address, *args, max_steps=max_steps)

    def nested(self, address, *args):
        """Call a routine from inside a stub, on the stack below the caller."""
        emu = self.emu
        saved = (emu.r[:], emu.rh[:], emu.hi, emu.lo, emu.hi1, emu.lo1, emu.pc, emu.npc, emu.cur,
                 emu._pending_call, emu._fresh_call, emu._call_site, emu.f[:])
        emu.r[29] = ((emu.r[29] & M32) - 0x400) & ~0xF
        try:
            return emu.call(address, *args)
        finally:
            emu.r[:], emu.rh[:] = saved[0], saved[1]
            (emu.hi, emu.lo, emu.hi1, emu.lo1, emu.pc, emu.npc, emu.cur,
             emu._pending_call, emu._fresh_call, emu._call_site) = saved[2:12]
            emu.f[:] = saved[12]

    def on_interpret(self, emu):
        # PRI is uninitialised at the start of a run (docs/spec/script-machine.md 4.1): give
        # the slot of the frame scr_interpret is about to make the value the model starts with
        emu.mem.w32((emu.r[29] & M32) - 0x80 + 4, 0)

    # ---- memory journal -----------------------------------------------------------------
    def checkpoint(self):
        self.snap = {index: bytes(page) for index, page in self.emu.mem.pages.items()
                     if not STACK_LO <= index << 12 < STACK_HI}
        self.dirty = set()

    def poke(self, addr, data):
        self.emu.mem.write(addr, data)
        self.dirty.update(range(addr >> 12, ((addr + max(len(data), 1) - 1) >> 12) + 1))

    def w32(self, addr, value):
        self.poke(addr, struct.pack('<I', value & M32))

    def restore(self):
        pages = self.emu.mem.pages
        for _pc, addr, size, _value in self.emu.writes:
            self.dirty.add(addr >> 12)
            self.dirty.add((addr + size - 1) >> 12)
        for index in self.dirty:
            saved = self.snap.get(index)
            if saved is not None:
                pages[index][:] = saved
        self.dirty = set()
        self.emu.reset_log()
        if self.script_bytes is not None:
            self.emu.mem.write(self.base, self.script_bytes)
            self.emu.mem.w32(N.G_SCRIPT_MACHINE, self.base)

    # ---- stubs --------------------------------------------------------------------------
    def decode(self, x_ints, x_floats, x_stack, emu, reg=4):
        mem, out = emu.mem, []
        for kind in x_ints:
            value = emu.r[reg] & M32
            reg += 1
            if kind == 'i':
                out.append(value)
            elif kind == 's':
                out.append(mem.cstr(value).encode('latin-1'))
            elif kind == 'v':
                out.append(tuple(mem.u32(value + 4 * j) for j in range(3)))
            elif kind == 'p':
                out.append('stack' if STACK_LO <= value < STACK_HI else value)
            elif kind == 'T':
                out.append((mem.read(value + 0x10, 0x12),) + tuple(mem.u16(value + o) for o in (0x24, 0x2C, 0x34, 0x3C)))
            elif kind == 'B':
                out.append(mem.read(value, emu.r[reg] & M32))
                reg += 1
        for j in range(x_floats):
            out.append(emu.f[12 + j])
        sp = emu.r[29] & M32
        for j in range(x_stack):
            out.append(mem.u32(sp + 8 * j))
        return tuple(out)

    def make_stub(self, name, x):
        def stub(emu):
            args = self.decode(x.ints, x.floats, x.stack, emu)
            self.calls.append((name, args))
            value = self.responder.answer(name, args)
            a0, a1, a2, a3 = (emu.r[4 + k] & M32 for k in range(4))
            if name == 'item_parseDescriptor':
                self.w32(a1, value)
                return 0
            if name == 'inventory_findItemBySubstring':
                self.w32(a2, value[0])
                if value[0] != -1:
                    self.w32(a3, value[1])
                return 0
            if name in ('world_collectObjectsInBox', 'world_findObjectsByClass'):
                out = a2 if name == 'world_collectObjectsInBox' else a1
                self.poke(out, b''.join(struct.pack('<I', addr) for addr in value) + bytes(4))
                return len(value)
            if name == 'world_forEachGridObject':
                for addr in value:
                    self.nested(a0, addr)
                return 0
            if x.ret == 'f':
                emu.f[0] = value & M32
                return 0
            return s32(value) if x.ret == 'i' else 0
        return stub

    def make_virtual(self, slot):
        def stub(emu):
            if slot not in VIRTUAL:
                self.calls.append(('virtual', (slot, emu.r[4] & M32, 'unexpected slot')))
                return 0
            ints, floats, kind = VIRTUAL[slot]
            args = (slot, emu.r[4] & M32) + self.decode(ints, floats, 0, emu, reg=5)
            self.calls.append(('virtual', args))
            value = self.responder.answer('virtual', args)
            if slot == N.V_SEAT:
                self.poke(emu.r[6] & M32, struct.pack('<3I', *value[0]))
                self.poke(emu.r[7] & M32, struct.pack('<H', value[1]))
                return 0
            return s32(value) if kind == 'i' else 0
        return stub

    # ---- the script image -----------------------------------------------------------------
    def place(self, image):
        """Put a script image into memory, run the real scr_load and scr_registerNatives
        (with the real table), and make that the state every case starts from."""
        self.script_bytes = None
        self.restore()
        self.image_size = len(image)
        self.emu.mem.write(self.base, bytes(image) + bytes(0x200))
        self.emu.mem.w32(N.G_SCRIPT_MACHINE, self.base)
        error = s32(self.call(SCR_LOAD, self.base, self.base + 0x60))
        bound = s32(self.call(SCR_REGISTER, self.base, N.NATIVE_TABLE, -1))
        self.script_bytes = self.emu.mem.read(self.base, len(image) + 0x200)
        self.dirty.add(N.G_SCRIPT_MACHINE >> 12)
        return error, bound


# ---------------------------------------------------------------------------------------
# A random game state, written into the interpreter's memory
# ---------------------------------------------------------------------------------------
def rand_float(rng, spread=400.0):
    roll = rng.random()
    if roll < 0.1:
        return 0
    if roll < 0.15:
        return 0x80000000
    return f32(rng.uniform(-spread, spread))


class Scene:
    def __init__(self, rig, rng, names=None, variables=None, entries=None, objects=None):
        self.rig, self.rng = rig, rng
        self.names = list(names if names is not None else NAME_POOL)
        self.variables = list(variables if variables is not None else VAR_POOL)
        self.entries = list(entries if entries is not None else ENTRY_POOL)
        self.token_base, self.pool_base = rig.token_base, rig.pool_base
        self.copy_buf, self.item_defs = rig.copy_buf, rig.item_defs
        self.objects = []
        self.strings_at = rig.strings
        self.tables_at = rig.tables
        self.bias = {}
        self.medal_player = 0
        self.copy_skew = rng.choice((0, 0, 4))      # an unaligned copy buffer takes the other copy loop
        self.prefer = None
        self.table = O.NameTable()
        self.build(objects)

    # ---- helpers --------------------------------------------------------------------------
    def cstring(self, text):
        addr = self.strings_at
        self.rig.poke(addr, bytes(text) + b'\0')
        self.strings_at += len(text) + 1
        return addr

    def w(self, addr, size, value):
        self.rig.poke(addr, (value & ((1 << (8 * size)) - 1)).to_bytes(size, 'little'))

    def vary_case(self, name):
        rng = self.rng
        roll = rng.random()
        if roll < 0.6:
            return name
        if roll < 0.8:
            return name.upper()
        return bytes(c ^ 0x20 if (65 <= c <= 90 or 97 <= c <= 122) and rng.random() < 0.5 else c for c in name)

    # ---- objects --------------------------------------------------------------------------
    def add_object(self, kind=None):
        rng, rig = self.rng, self.rig
        index = len(self.objects)
        addr = rig.obj_base + 0x1000 * index
        if kind is None:
            kind = rng.choice(('plain', 'creature', 'creature', 'creature', 'generator', 'mtrigger', 'container',
                               'trigger', 'autoprop', 'vehicle'))
        type_name = {'generator': N.TYPE_SCRIPT_GENERATOR, 'mtrigger': N.TYPE_MONSTER_TRIGGER,
                     'container': N.TYPE_AUTO_CONTAINER, 'trigger': N.TYPE_TRIGGER}.get(kind, b'10GameObject')
        blob = bytearray(rng.randbytes(0x940))
        flags = rng.getrandbits(32) & ~0x10000068
        if kind in ('creature', 'player') or rng.random() < 0.15:
            flags |= N.OF_CREATURE
        if kind == 'player':
            flags |= N.OF_PLAYER
        elif rng.random() < 0.08:
            flags |= N.OF_PLAYER
        if rng.random() < 0.3:
            flags |= N.OF_DEAD
        if kind == 'autoprop' or rng.random() < 0.15:
            flags |= N.OF_AUTOPROP
        struct.pack_into('<I', blob, N.O_FLAGS, flags)
        struct.pack_into('<3I', blob, N.O_POS, *[rand_float(rng) for _ in range(3)])
        struct.pack_into('<I', blob, N.O_VTABLE, rig.vtable_of[type_name])
        props = None
        if rng.random() < 0.75:
            props = [rng.choice(PROP_POOL) for _ in range(rng.randrange(5))]
        prop_ptr = 0
        if props is not None:
            prop_ptr = self.tables_at
            words = [self.cstring(entry) for entry in props] + [0]
            rig.poke(prop_ptr, struct.pack('<%dI' % len(words), *words))
            self.tables_at += 4 * len(words)
        struct.pack_into('<I', blob, N.O_PROPS, prop_ptr)
        weapon = 0
        if rng.random() < 0.7:
            weapon = rig.aux_base + 0x100 * (index % 64)
            rig.poke(weapon, struct.pack('<I', rig.weapon_vtable))
        struct.pack_into('<I', blob, N.C_WEAPON_OBJ, weapon)
        cflags = rng.getrandbits(64)
        for bit in (N.CF_FOLLOW_PATH, N.CF_BOSS_METER, N.CF_BOSS, N.CF_FRIENDLY):
            cflags = cflags | bit if rng.random() < 0.5 else cflags & ~bit
        struct.pack_into('<Q', blob, N.C_FLAGS, cflags)
        struct.pack_into('<I', blob, N.C_HP, rand_float(rng, 2000.0))
        struct.pack_into('<h', blob, N.C_AI_STATE, 0x14 if rng.random() < 0.3 else rng.randrange(0x30))
        struct.pack_into('<i', blob, 0x68, rng.choice((-1, -1, 0, 1, 2)))
        struct.pack_into('<I', blob, N.PLAYER_VEHICLE, 0)
        for offset in (0x90C, 0x34C, 0x348, 0x468, 0x46C, 0x470):
            struct.pack_into('<I', blob, offset, rand_float(rng, 8.0))
        path = rig.aux_base + 0x100 * (index % 64) + 0x80
        rig.poke(path, struct.pack('<6I', *[rand_float(rng, 2.0) for _ in range(6)]))
        struct.pack_into('<I', blob, 0x910, path)
        rig.poke(addr, bytes(blob))
        entry = {'addr': addr, 'type': type_name, 'props': props, 'kind': kind}
        self.objects.append(entry)
        return entry

    def build(self, object_count):
        rng, rig, w = self.rng, self.rig, self.w
        mem = rig.emu.mem
        # ---- objects and the name table
        count = rng.randrange(3, 11) if object_count is None else object_count
        for _ in range(count):
            self.add_object()
        for entry in self.objects:
            for _ in range(rng.choice((0, 1, 1, 1, 2))):
                self.table.add(self.vary_case(rng.choice(self.names)), entry)
        for _ in range(rng.randrange(3)):                   # removed entries: the key stays behind
            held = [(i, o) for i, o in enumerate(self.table.objs) if o is not None]
            if held:
                slot, entry = rng.choice(held)
                self.table.remove(self.table.keys[slot], entry)
        # ---- players
        self.num_players = rng.choice((1, 1, 2, 2, 3, 4, 4, 0))
        players = []
        for slot in range(4):
            rec = N.G_PLAYERS + slot * N.REC_SIZE
            blob = bytearray(rng.randbytes(N.REC_SIZE))
            obj = 0
            if rng.random() < (0.85 if slot < self.num_players else 0.3):
                entry = self.add_object('player')
                obj = entry['addr']
                if rng.random() < 0.4:
                    self.table.add(self.vary_case(rng.choice(self.names)), entry)
            players.append(obj)
            struct.pack_into('<I', blob, N.P_OBJECT, obj)
            hp_max = f32(rng.choice((1.0, 55.0, 120.5, 3000.0)))
            struct.pack_into('<2I', blob, N.P_HP, rng.choice((0, 0x80000000, f32(-3.0), f32(1.0), f32(77.25), hp_max)),
                             hp_max)
            struct.pack_into('<2I', blob, N.P_MANA, rand_float(rng, 300.0), f32(rng.uniform(0, 500)))
            struct.pack_into('<i', blob, N.P_GOLD, rng.choice((0, 5, 1234, 99999990, 99999999, -7, rng.randrange(10 ** 8))))
            struct.pack_into('<2i', blob, N.P_CLASS, rng.randrange(6), rng.randrange(3))
            struct.pack_into('<2I', blob, N.P_WEIGHT, f32(rng.uniform(0, 60)), f32(rng.uniform(20, 80)))
            for bag in range(3):
                struct.pack_into('<i', blob, N.P_BAGS + bag * N.BAG_SIZE + N.BAG_COUNT, rng.choice((0, 0, 1, 2, 5)))
                struct.pack_into('<I', blob, N.P_BAGS + bag * N.BAG_SIZE, rng.choice((0, rig.item_defs)))
            quests = rng.choice((0, 0, 1, 2, 3, 7, 8, 8))
            struct.pack_into('<i', blob, N.P_QUEST_COUNT, quests)
            for k in range(8):
                for part in (0, 0x20):
                    text = rng.choice(QUEST_POOL) if k < quests or rng.random() < 0.5 else b''
                    at = N.P_QUESTS + k * N.QUEST_SIZE + part
                    blob[at:at + 0x20] = text.ljust(0x20, b'\0')
            for mission in range(13):
                blob[N.P_MEDALS + mission] = rng.choice((0, 0, 1, 2, 3))
            struct.pack_into('<h', blob, N.P_NEWWORLD_COOLDOWN, rng.choice((0, 0, 1, 599, -1)))
            struct.pack_into('<I', blob, N.P_STATUS, rng.getrandbits(32) & ~0x1F | rng.choice((0, 1, 1, 1, 2, 3)))
            rig.poke(rec, bytes(blob))
        living = [slot for slot in range(self.num_players)
                  if players[slot] and not mem.u32(players[slot] + N.O_FLAGS) & N.OF_DEAD]
        if rng.random() < 0.15:
            living = [rng.randrange(4) for _ in range(rng.randrange(5))]
        w(N.G_ALIVE_COUNT, 4, len(living))
        for index in range(4):
            w(N.G_ALIVE_LIST + 4 * index, 4, living[index] if index < len(living) else rng.randrange(4))
        vehicles = [o['addr'] for o in self.objects if o['kind'] == 'vehicle']
        for obj in players:
            if obj and vehicles and rng.random() < 0.6:
                w(obj + N.PLAYER_VEHICLE, 4, rng.choice(vehicles))
        # ---- the name table, as the original keeps it
        keys, objs = [], []
        for slot in range(512):
            key = self.table.keys[slot]
            keys.append(0 if key is None else self.cstring(key))
            objs.append(0 if self.table.objs[slot] is None else self.table.objs[slot]['addr'])
        rig.poke(O.G_NAME_KEYS, struct.pack('<512I', *keys))
        rig.poke(O.G_NAME_OBJS, struct.pack('<512I', *objs))
        # ---- globals
        net = rng.random() < 0.5
        w(N.G_NETWORK_MODE, 1, 1 if net else 0)
        w(N.G_NUM_PLAYERS, 4, self.num_players)
        roll = rng.random()
        active = rng.randrange(max(self.num_players, 1)) if roll < 0.8 else rng.choice((-1, 2, 3, 0))
        w(N.G_ACTIVE_PLAYER, 4, active)
        with_selected = [o for o in self.objects]
        w(N.G_SELECTED_OBJ, 4, rng.choice(with_selected)['addr'] if with_selected and rng.random() < 0.8 else 0)
        w(N.G_RAND_SEED, 4, rng.getrandbits(32))
        w(N.G_DIFFICULTY, 4, rng.randrange(5))
        w(N.G_PAUSED, 4, rng.choice((0, 0, 0, 1)))
        w(N.G_CUTSCENE_ACTIVE, 1, rng.choice((0, 0, 0, 1)))
        w(N.G_JUMPGATE_TRAVEL, 4, rng.choice((0, 0, 0, 2)))
        w(N.G_DRAW_FRAME, 4, rng.randrange(100000))
        w(N.G_MISSING_STAMP, 4, rng.choice((0, 50000, 200000)))
        w(N.G_IN_POST_ACTION, 1, rng.choice((0, 0, 0, 1)))
        w(N.G_PENDING_LEVEL, 0x50, 0)
        w(N.G_PENDING_ORIENT, 1, rng.randrange(256))
        rig.poke(N.G_LEVEL_NAME, rng.choice((b'hub', b'cave1', b'orccave1x', b'')) + b'\0')
        w(N.G_RECALL_COUNTDOWN, 1, rng.choice((0, 0, 0, 3)))
        w(N.G_MEDAL_TICKS, 4, rng.choice((0, 0, 2)))
        w(N.G_MEDAL_MISSION, 4, rng.choice((0, 0, 1)))
        w(N.G_MEDAL_ACK, 4, rng.choice((0, 1, 1)))
        self.medal_player = rng.randrange(4)
        w(N.G_MEDAL_PLAYER, 1, self.medal_player)
        w(N.G_REWARD_PLAYER, 1, rng.randrange(4))
        w(N.G_RESPAWN_COUNTDOWN, 4, rng.choice((0, -1, 5, 240)))
        w(N.G_LEVEL_LOADING, 4, rng.choice((0, 1)))
        w(N.G_LIGHT_SCALE, 4, rand_float(rng, 3.0))
        w(N.G_LEVEL_TIMER, 4, rng.choice((0, 59, 60, 3600, 0x7FFFFFFF, 0x80000001, 0xFFFFFFFF, rng.getrandbits(32))))
        w(N.G_MANA_USED, 2, rng.getrandbits(16))
        w(N.G_HEALTH_USED, 2, rng.getrandbits(16))
        w(N.G_SAVED_CONFIG, 4, rng.getrandbits(32))
        w(N.G_SAVE_INHIBIT, 4, rng.choice((0, 1, 77)))
        w(N.G_SHOP_OPEN, 4, rng.choice((0, 1)))
        w(N.G_HELP_OPEN, 1, rng.choice((0, 1, 200)))
        w(N.G_DIALOG_DATA, 4, rng.choice((0, 0, 0x1234560)))
        w(N.G_DIALOG_MSG_ID, 4, rng.randrange(16))
        w(N.G_LOCAL_CAMERA, 4, rig.scratch)
        rig.poke(N.G_CAMERA_POS, struct.pack('<3I', *[rand_float(rng) for _ in range(3)]))
        w(N.G_HUD_FONT, 4, rig.scratch + 0x100)
        w(N.G_BTN_NAME_A, 4, rng.randrange(16))
        w(N.G_BTN_NAME_B, 4, rng.randrange(16))
        confirm, cancel = rng.sample((0x10, 0x20, 0x40, 0x4000), 2)
        w(N.G_BTN_CONFIRM, 4, confirm)
        w(N.G_BTN_CANCEL, 4, cancel)
        for slot in range(4):
            w(N.G_PADS + slot * N.PAD_SIZE + 0xC, 4, rng.choice((0, 0, confirm, cancel, confirm | cancel, 0x8000)))
        w(N.SKILL_PTR_HORN, 4, rig.scratch + 0x200)
        # ---- quest and profile variables
        for table in (N.G_QUEST_VARS, N.G_PROFILE_VARS):
            blob = bytearray()
            for name in rng.sample(self.variables, rng.randrange(min(len(self.variables), 12) + 1)):
                blob += name.lower() + b'\0' + bytes([rng.getrandbits(8)])
            rig.poke(table, bytes(blob) + bytes(0x200))
        # ---- deferred calls and post action
        w(N.G_DEFER_FLIP, 4, rng.getrandbits(8))
        w(N.G_DEFER_QUEUED, 4, rng.choice((0, 0, 1, 5, 63, 64, 64)))
        running = rng.choice((0, 0, 1, 2, 3))
        w(N.G_DEFER_COUNT, 4, running)
        half = mem.u32(N.G_DEFER_FLIP) & 1
        for index in range(4):
            rig.poke(N.G_DEFER_NAMES + half * 0x1400 + 0x50 * index, rng.choice(self.entries) + b'\0')
        rig.poke(N.G_POST_ACTION, (rng.choice(self.entries) if rng.random() < 0.6 else b'') + b'\0')
        # ---- the class-name table of generateMonster
        known = rng.sample(CLASS_POOL, rng.randrange(4))
        w(N.G_GEN_COUNT, 1, len(known))
        for index, name in enumerate(known):
            rig.poke(N.G_GEN_NAMES + 24 * index, name + b'\0')
        # ---- what the stubs hand out
        for index in range(3):
            w(rig.item_defs + 0x40 * index + 0x1D, 1, index)
        rig.poke(rig.copy_buf, rng.randbytes(N.REC_SIZE))
        rig.poke(rig.pool_base, bytes(0x200 * 8))

    # ---- the model's side of the same state ---------------------------------------------------
    def model(self, responder):
        mem = N.Mem(Under(self.rig.emu.mem))
        world = O.World()
        objs = {}
        for entry in self.objects:
            obj = N.Obj(mem, entry['addr'], entry['type'])
            obj.props = list(entry['props']) if entry['props'] is not None else None
            world.objects[entry['addr']] = obj
            objs[entry['addr']] = obj
        world.names.keys = list(self.table.keys)
        world.names.objs = [None if entry is None else objs[entry['addr']] for entry in self.table.objs]
        host = TestHost(responder, world)
        game = N.Game(mem, world, host)
        return game, host


# ---------------------------------------------------------------------------------------
# One compared run
# ---------------------------------------------------------------------------------------
STRUCT_FIELDS = (('cip', 0x0C), ('frm', 0x10), ('hea', 0x14), ('stk', 0x18), ('stp', 0x1C), ('flags', 0x20),
                 ('curline', 0x24), ('curfile', 0x28), ('error', 0x5C))


class Outcome:
    def __init__(self):
        self.problems = []
        self.fault = None           # None, 'both', 'model', 'emu'
        self.calls = 0


def compare(rig, machine, game, host, model_run, emu_run, check_script=True):
    """Run the model (first, on its copy-on-write view), then the original, and compare.
    model_run() -> result; emu_run() -> result."""
    emu, mem = rig.emu, rig.emu.mem
    out = Outcome()
    seed_before = mem.u32(N.G_RAND_SEED)
    model_error = model_result = None
    try:
        model_result = model_run()
    except N.StackGarbage:
        out.fault = 'garbage'       # the original reads a stack word the model cannot know
        return out
    except (ref_amx.HostFault, O.ObjectError) as stop:
        model_error = stop
    except ref_amx.Limit:
        out.fault = 'limit'
        return out
    rig.calls = []
    rig.addr_log = []
    emu.reset_log()
    emu.trace = []
    emu_error = emu_result = None
    try:
        emu_result = emu_run()
    except EmuError as stop:
        emu_error = stop
    rig.pcs.update(emu.trace)
    emu.trace = None
    for record in emu.calls:
        if record.target not in rig.real and record.target not in rig.stub_addrs:
            rig.unknown[record.target] = rig.unknown.get(record.target, 0) + 1
            out.problems.append('call to 0x%x, which is neither real nor a known stub' % record.target)
    out.calls = len(rig.calls)
    if model_error is not None or emu_error is not None:
        if model_error is not None and emu_error is not None:
            out.fault = 'both'
        else:
            out.fault = 'model' if model_error is not None else 'emu'
            out.problems.append('only the %s stops: %s' % ('model' if model_error is not None else 'original',
                                                           model_error or emu_error))
        return out
    if emu_result != model_result:
        out.problems.append('result %r, model %r' % (emu_result, model_result))
    if rig.calls != host.log:
        at = next((i for i, (a, b) in enumerate(zip(rig.calls, host.log)) if a != b), min(len(rig.calls), len(host.log)))
        out.problems.append('call-out #%d of %d/%d: original %r, model %r' % (
            at, len(rig.calls), len(host.log), rig.calls[at] if at < len(rig.calls) else None,
            host.log[at] if at < len(host.log) else None))
    lo, hi = rig.base, rig.base + rig.image_size + 0x200
    ebytes, maybe = set(), set()
    for pc, addr, size, _value in emu.writes:
        if lo <= addr < hi or rig.cells <= addr < rig.cells + 0x400 or LIBC_SCRATCH[0] <= addr < LIBC_SCRATCH[1]:
            continue
        # the interpreter logs an unaligned store pair (swl/swr, sdl/sdr) as the whole aligned
        # words: those bytes may or may not have been stored; their values are compared below
        (maybe if mem.u32(pc) >> 26 in (0x2A, 0x2E, 0x2C, 0x2D) else ebytes).update(range(addr, addr + size))
    mbytes = set()
    for addr, size in game.mem.writes:
        mbytes.update(range(addr, addr + size))
    maybe -= ebytes
    if not (ebytes <= mbytes and mbytes <= ebytes | maybe):
        only_e, only_m = sorted(ebytes - mbytes), sorted(mbytes - ebytes - maybe)
        out.problems.append('bytes written: only the original %s, only the model %s' % (
            ['0x%x' % a for a in only_e[:6]] + ['(%d)' % len(only_e)], ['0x%x' % a for a in only_m[:6]] + ['(%d)' % len(only_m)]))
    under = game.mem
    diff = [(addr, mem.load(addr, 1), under.load(addr, 1)) for addr in sorted(ebytes | mbytes | maybe)
            if mem.load(addr, 1) != under.load(addr, 1)]
    if diff:
        out.problems.append('values written differ: ' + ', '.join('0x%x: %02x model %02x' % d for d in diff[:6])
                            + ' (%d)' % len(diff))
    seed = seed_before
    for _ in range(game.draws):
        seed = (seed * 0x19660D + 0x3C6EF35F) & M32
    if not mem.u32(N.G_RAND_SEED) == game.seed == seed:
        out.problems.append('seed 0x%08x, model 0x%08x after %d draws from 0x%08x' % (
            mem.u32(N.G_RAND_SEED), game.seed, game.draws, seed_before))
    if check_script and machine is not None:
        base = rig.base
        for name, offset in STRUCT_FIELDS:
            a, b = mem.u32(base + offset), getattr(machine, name) & M32
            if a != b:
                out.problems.append('machine %s is 0x%x, model 0x%x' % (name, a, b))
        block = mem.read(base + machine.data_offset, rig.image_size - machine.data_offset)
        mine = machine.memory()[:len(block)]
        if block != mine:
            at = next(i for i in range(0, len(mine), 4) if block[i:i + 4] != mine[i:i + 4])
            out.problems.append('script memory differs first at 0x%x: %s, model %s' % (
                at, block[at:at + 4].hex(), mine[at:at + 4].hex()))
    return out


class Tally:
    def __init__(self):
        self.cases = self.bad = self.faults = self.calls = self.limit = self.garbage = 0
        self.examples = []

    def add(self, outcome, label):
        if outcome.fault == 'limit':
            self.limit += 1
            return
        if outcome.fault == 'garbage':
            self.garbage += 1
            return
        self.cases += 1
        self.calls += outcome.calls
        if outcome.fault == 'both':
            self.faults += 1
        if outcome.problems:
            self.bad += 1
            if len(self.examples) < 8:
                self.examples.append('%s: %s' % (label, '; '.join(outcome.problems[:3])))


# ---------------------------------------------------------------------------------------
# The synthetic script used for the per-built-in cases
# ---------------------------------------------------------------------------------------
STRING_CELLS = 0x400            # room for the string arguments of a case
BAD_ADDRESS = 0x7FFF0000
STALE_ENTRIES = ('staleA', 'staleB', 'staleC', 'staleD', 'staleE', 'staleF')
INDEX = {name: index for index, name in enumerate(N.NATIVE_NAMES)}


def pack_string(text, packed):
    """Cells of a script string: packed (four characters per cell, first in the top byte)
    or unpacked (one per cell)."""
    if packed and text:
        text = text + b'\0' * (4 - len(text) % 4)
        return [int.from_bytes(text[i:i + 4], 'big') for i in range(0, len(text), 4)]
    return list(text) + [0]


def synthetic_image():
    """Six entry points that call built-ins themselves, so that nested runs do something."""
    literals, data = {}, []

    def lit(text):
        if text not in literals:
            literals[text] = 4 * (STRING_CELLS + len(data))
            data.extend(pack_string(text, True))
        return literals[text]

    def call(name, *args):
        code = []
        for arg in reversed(args):
            code.append(('PUSH.C', arg))
        return code + [('PUSH.C', 4 * len(args)), ('SYSREQ.C', INDEX[name]), ('STACK', 4 * len(args) + 4)]

    def function(label, body, result):
        return [label + ':', ('PROC',)] + body + ([] if result is None else [('CONST.pri', result)]) + [('RETN',)]

    program = []
    program += function('alpha', call('setv', lit(b'qa'), 5) + call('getRand'), 7)
    program += function('beta', [], 0x1234)
    program += function('gamma', call('addDeferedCall', lit(b'alpha')) + call('postAction', lit(b'beta')), -3)
    program += function('delta', call('callScript', lit(b'beta')) + call('setv', lit(b'stage'), 2), 0)
    program += function('firstBronze', call('setv', lit(b'kills'), 1), 1)
    program += function('firstSilver', call('getRand') + call('playerAdjustStat', -1, 5, 2), 2)
    program += function('firstGold', call('grantMission', 3), 3)
    # string arguments whose address scr_getAddr refuses (BAD_ADDRESS is beyond the stack top)
    bad = BAD_ADDRESS
    program += function('staleA', call('rootMonster', lit(b'gob')) + call('setCFlag', bad, 26, 1)
                        + call('rootMonster', bad) + call('hideMonster', bad), 0)
    program += function('staleB', call('setv', lit(b'qa'), 3) + call('addDeferedCall', bad) + call('getv', bad), None)
    program += function('staleC', call('addQuest', lit(b'Find it'), bad) + call('removeQuest', bad), 0)
    program += function('staleD', call('getv', lit(b'qa')) + call('getRand') + call('getv', bad), None)
    program += function('staleE', call('hideMonster', lit(b'gob')) + call('setMonsterVal', bad, 5, 300)
                        + call('getHitPoints', bad), None)
    program += function('staleF', call('callScript', lit(b'alpha')) + call('getv', bad), None)
    cells, labels = ref_amx.assemble(program)
    publics = [(name, labels[name]) for name in ('alpha', 'beta', 'gamma', 'delta', 'firstBronze', 'firstSilver',
                                                 'firstGold') + STALE_ENTRIES]
    return ref_amx.build_image(cells, [0] * STRING_CELLS + data, publics, N.NATIVE_NAMES, stack_cells=1024)


class Case:
    """One call of one built-in: argument cells and the strings they point at, written
    into the script memory of both sides."""

    def __init__(self, rig, machine, rng):
        self.rig, self.machine, self.rng = rig, machine, rng
        self.cursor = 0
        self.cells = []

    def string(self, text):
        cells = pack_string(text, self.rng.random() < 0.7)
        address = 4 * self.cursor
        self.cursor += len(cells) + self.rng.randrange(2)
        self.cells.append((address, cells))
        return address

    def commit(self, args):
        """Write strings and the argument block; returns the params address."""
        machine, rig = self.machine, self.rig
        params = machine.stp - 0x100
        self.cells.append((params, [4 * len(args)] + list(args) + [self.rng.getrandbits(32) for _ in range(4)]))
        for address, cells in self.cells:
            blob = b''.join(struct.pack('<I', c & M32) for c in cells)
            position = machine.data_offset + address
            machine.image[position:position + len(blob)] = blob
            rig.poke(rig.base + position, blob)
        machine.stk = params
        rig.w32(rig.base + 0x18, params)
        return params


def any_int(rng):
    roll = rng.random()
    if roll < 0.35:
        return rng.randrange(-3, 12)
    if roll < 0.7:
        return rng.randrange(-400, 2000)
    if roll < 0.85:
        return rng.choice((0x7FFFFFFF, -0x80000000, 65536, -65536, 100000000, 44000))
    return s32(rng.getrandbits(32))


def make_args(spec, scene, case, rng):
    args = []
    for kind in spec.split():
        if kind == 'obj':
            name = rng.choice(scene.names) if rng.random() < 0.9 else rng.choice((b'nobody', b''))
            liked = [key for key, entry in zip(scene.table.keys, scene.table.objs)
                     if entry is not None and entry['kind'] == scene.prefer]
            if liked and rng.random() < 0.6:
                name = rng.choice(liked)
            args.append(case.string(scene.vary_case(name)))
        elif kind == 'var':
            name = rng.choice(scene.variables) if rng.random() < 0.85 else rng.choice((b'new_one', b'Fresh', b''))
            args.append(case.string(scene.vary_case(name)))
        elif kind == 'entry':
            args.append(case.string(rng.choice(scene.entries)))
        elif kind == 'lvl':
            args.append(case.string(rng.choice(LEVEL_POOL)))
        elif kind == 'key':
            args.append(case.string(rng.choice(TEXT_POOL)))
        elif kind == 'cls':
            args.append(case.string(rng.choice(CLASS_POOL)))
        elif kind == 'quest':
            args.append(case.string(rng.choice(QUEST_POOL)))
        elif kind == 'i':
            args.append(any_int(rng))
        elif kind == 'i8':
            args.append(rng.choice((0, 1, -1, 5, 127, 128, -128, -129, 300, -300, rng.randrange(-140, 140))))
        elif kind == 'b':
            args.append(rng.choice((0, 0, 1, 1, 2, -1)))
        elif kind == 'm':
            args.append(rng.choice(list(range(13)) + [13, 14, 100, 0, 1, 2]))
        elif kind == 'p':
            args.append(rng.choice((-1, -1, 0, 0, 1, 2, 3, 4, 7)))
        elif kind == 'p0':
            args.append(rng.randrange(4))
        elif kind == 'small':
            args.append(rng.choice((0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 33, -1)))
        elif kind == 'stat':
            args.append(rng.randrange(2, 11))
        elif kind == 'which':
            args.append(rng.randrange(0, 7))
        elif kind == 'bit':
            args.append(rng.choice((0, 0, 26, 26, 1, 31, 27)))
        elif kind == 'of':
            args.append(rng.choice((14, 14, 0, 13)))
        elif kind == 'slot3':
            args.append(rng.randrange(3))
        elif kind == 'slotm':
            args.append(rng.randrange(-1, 3))
        elif kind == 'mode':
            args.append(rng.choice((-1, -1, 0, 1, 6)))
        elif kind == 'store':
            args.append(rng.choice((0, 3, 20, 21, 500, -1)))
        elif kind == 'radius':
            args.append(rng.choice((0, 50, 300, 1000, 100000)))
        elif kind == 'c100':
            args.append(rng.randrange(-300, 301))
        elif kind == 'ref':
            address = 4 * case.cursor
            case.cells.append((address, [any_int(rng) for _ in range(3)]))
            case.cursor += 3
            args.append(address)
        else:
            raise ValueError(kind)
    return args


SPEC = {
    'callScript': 'entry', 'addDeferedCall': 'entry', 'postAction': 'entry', 'print': 'key', 'printVal': 'i',
    'getRand': '', 'getScaledTime': 'i', 'sin1000': 'i', 'cos1000': 'i', 'gamePaused': '', 'demoRunning': '',
    'networkMode': '', 'levelLoading': '', 'getLevelTimer': '',
    'getv': 'var', 'setv': 'var i8', 'addv': 'var i8', 'getpv': 'var', 'setpv': 'var i8', 'getEvil': '',
    'setEvil': 'b', 'getMadeDecision': '', 'setMadeDecision': '', 'grantMission': 'm', 'getMissionComplete': 'm',
    'setMissionAvailable': 'm b', 'getMissionAvailable': 'm', 'grantGold': 'm', 'grantSilver': 'm',
    'grantBronze': 'm', 'getMedal': 'm', 'addQuest': 'quest quest', 'removeQuest': 'quest',
    'newWorld': 'lvl', 'newWorldAlways': 'lvl', 'simpleNewWorld': 'lvl', 'newWorldPost': 'lvl',
    'newWorldParameter': '', 'setEntrance': 'key', 'cutScene': 'key', 'startDialog': 'key i i',
    'dialogRunning': '', 'forceMutexRelease': '', 'changeSwoop': 'i', 'startWithSwoopDone': '', 'leaveGame': 'b',
    'endGame': '', 'exitToMainMenu': '', 'saveGame': '', 'saveEndConfig': '', 'saveDone': '', 'saveCheckPoint': '',
    'loadCheckPoint': '', 'setSaveInhibit': 'i', 'getSaveInhibit': '', 'setAlternateDeath': '',
    'preloadResource': 'key', 'clearRecall': '', 'playersLoaded': '', 'pauseGameControl': 'i',
    'activateMissionMenu': '', 'activateStore': 'store', 'storeRunning': '', 'setInfo': 'key',
    'addHelpMessage': 'key key', 'addHelpMessageF': 'key i key i', 'helpMessageActive': '', 'showCompass': 'obj key',
    'showBust': 'key key i i', 'hudResetFadeScreen': 'i', 'hudFadeScreen': 'i', 'revealMap': '', 'showOnMap': 'obj b',
    'runMedalSuccess': 'm small key key key key', 'runMedalFail': 'key', 'setupPlayerSel': '', 'startPlayerSel': '',
    'playerSelRunning': '',
    'getNumPlayers': '', 'countPlayersAlive': '', 'checkPlayerAlive': 'b', 'setBestActivePlayer': '',
    'activePlayerIsDwarf': '', 'activePlayerIsElf': '', 'isClericOrWizard': 'p', 'getMaxPlayerHP': 'p',
    'healPlayer': '', 'giveFullHealth': '', 'zeroPlayerMana': '', 'refillPlayerMana': '',
    'hitPlayers': 'obj radius i i', 'closestPlayerDist': 'obj', 'givePlayerExp': 'i', 'givePlayerGold': 'i',
    'takePlayerGold': 'i', 'checkPlayerGold': '', 'checkPlayerMinGold': '', 'playerAdjustStat': 'p stat small',
    'setPlayerFlag': 'p small b', 'getPlayerFlag': 'p0 small', 'piercePlayerEar': 'p', 'clearAllSkills': '',
    'savePlayer': '', 'restorePlayer': '', 'hidePlayers': 'i', 'decayPlayerLights': 'c100 c100 c100', 'hornOmen': '',
    'planarSteel': '', 'getManaUsed': '', 'getHealthUsed': '', 'playGotItemSound': '', 'explodePotionsOnly': '',
    'playerHasItem': 'key', 'onePlayerHasItem': 'p key', 'countQuestItems': 'key', 'removePlayerItem': 'p key',
    'removeAllItems': '', 'removeAllWeapons': '', 'givePlayerItem': 'key b i', 'giveOnePlayerItem': 'p key b i',
    'dropItem': 'obj key', 'selectDropItem': 'key',
    'increaseEnemyRank': 'obj', 'charmMonster': 'obj', 'rootMonster': 'obj', 'unRootMonster': 'obj',
    'selectSetMonsterVal': 'which i', 'setMonsterVal': 'obj which i', 'selectSetCFlag': 'bit b',
    'setCFlag': 'obj bit b', 'selectSetOFlag': 'of b', 'setOFlag': 'obj of b', 'setWeaponType': 'obj i',
    'setMonsterRange': 'obj i', 'killMonster': 'obj', 'deleteMonster': 'obj', 'hideMonster': 'obj',
    'showMonster': 'obj', 'moveMonster': 'obj obj', 'followPlayer': 'obj', 'stopFollowingPlayer': 'obj',
    'followPath': 'obj', 'selectFollowPath': '', 'stopFollowingPath': 'obj', 'selectStopPath': '', 'friendly': 'obj',
    'unFriendly': 'obj', 'reapEnemies': '', 'checkMonstersLeft': '', 'getHitPoints': 'obj', 'setHitPoints': 'obj i',
    'generateMonster': 'obj cls', 'monstersInTrigger': 'obj', 'initScriptSetParams': 'i i i i i',
    'setCreatureParams': 'obj i i i i i', 'startNPCAnim': 'obj key key mode', 'NPCAnimAtEnd': 'obj',
    'countLiveObjects': 'obj',
    'trigger': 'obj i', 'autoPropSetState': 'obj i', 'autoPropGetState': 'obj', 'startPropAnim': 'obj key mode',
    'stopPropAnim': 'obj', 'propAnimAtEnd': 'obj', 'deleteObjects': 'obj', 'setNoCollide': 'obj b',
    'objInPlayerTrig': 'obj', 'findDistance': 'obj obj', 'setContainerProps': 'obj slot3 b',
    'lightEffect': 'ref i i i i i i i i i i i', 'addExpandingPool': 'obj i i', 'particleMorph': 'obj obj',
    'setParticle': 'slot3 i i i i i i i i i i i i i i', 'addParticleOnObject': 'slotm obj i i i i i i',
    'shakeCamera': 'i', 'setFarClip': 'i', 'setWaveDetail': 'b',
    'sound': 'key key', 'soundSequence': 'key key', 'startMusic': 'key', 'startAudio': 'key', 'endMusic': '',
    'putNPCInVehicle': 'obj obj', 'putPlayersInVehicle': 'obj', 'entityRideVehicle': 'obj obj i i i i',
    'controlVehicle': 'obj i i', 'holdVehicle': 'obj b', 'getPlayerVPosition': '', 'getVPosition': 'obj',
    'getPlayerVDir': '',
}


# the kind of object a built-in is about: its name argument is then more often one of those
PREFER = {'setContainerProps': 'container', 'generateMonster': 'generator', 'monstersInTrigger': 'mtrigger',
          'particleMorph': 'creature', 'autoPropSetState': 'autoprop', 'autoPropGetState': 'autoprop',
          'getVPosition': 'vehicle', 'entityRideVehicle': 'vehicle', 'setCFlag': 'creature'}


# ---------------------------------------------------------------------------------------
# Coverage: basic blocks of every function that ran for real
# ---------------------------------------------------------------------------------------
def analyse(mem, start, end, table=()):
    leaders = {start}
    leaders.update(table)
    for pc in range(start, end, 4):
        word = mem.u32(pc)
        op, rs, rt = word >> 26, (word >> 21) & 31, (word >> 16) & 31
        target = (pc + 4 + (ee_emu.sx16(word) << 2)) & M32
        conditional = None
        if op in (4, 5, 20, 21):
            conditional = not (op in (4, 20) and rs == 0 and rt == 0)
        elif op in (6, 7, 22, 23):
            conditional = True
        elif op == 1 and rt in (0, 1, 2, 3):
            conditional = True
        elif op == 17 and rs == 8:
            conditional = True
        elif op == 2:
            leaders.add((pc & 0xF0000000) | ((word & 0x3FFFFFF) << 2))
            continue
        if conditional is None:
            continue
        leaders.add(target)
        if conditional:
            leaders.add(pc + 8)
    return {a for a in leaders if start <= a < end}


class Coverage:
    def __init__(self, rig):
        mem = rig.emu.mem
        handlers = {}
        for index, name in enumerate(N.NATIVE_NAMES):
            handlers.setdefault(mem.u32(N.NATIVE_TABLE + 8 * index + 4), name)
        starts = sorted(set(handlers) | set(HELPERS.values()) | {NATIVES_END})
        self.functions = {}
        for position, start in enumerate(starts[:-1]):
            name = handlers.get(start) or next(n for n, a in HELPERS.items() if a == start)
            table = [mem.u32(0x531290 + 4 * k) for k in range(5)] if start == HELPERS['script_applyMonsterVal'] else ()
            self.functions[name] = (start, starts[position + 1], analyse(mem, start, starts[position + 1], table))
        for name, start, end in MACHINERY:
            self.functions[name] = (start, end, analyse(mem, start, end))
        self.handlers = handlers

    def numbers(self, pcs, name):
        start, end, leaders = self.functions[name]
        return len(leaders & pcs), len(leaders)

    def missing(self, pcs, name):
        return sorted(self.functions[name][2] - pcs)


# ---------------------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------------------
def wanted(text):
    chosen = OPTIONS['filter']
    return not chosen or chosen in ('machinery', 'builtins', 'scripts') or chosen.lower() in text.lower()


def scaled(count):
    return max(4, count // 6) if OPTIONS['quick'] else count


def new_machine(image):
    machine = ref_amx.Machine(image)
    assert machine.load() == 0
    return machine


def setup_model(scene, seed, machine):
    game, host = scene.model(Responder(seed, scene))
    game.machine = machine
    machine._bound = None
    machine.register(game.natives())
    return game, host


def group_builtins(rig, coverage, stats):
    image = synthetic_image()
    error, bound = rig.place(image)
    machine = new_machine(image)
    saved = machine.snapshot()
    report('load', int(error != 0 or bound != 0), 1,
           'scr_load and scr_registerNatives bind all 191 names of the synthetic script from the table 0x403370')
    master = random.Random(OPTIONS['seed'])
    executed = set()
    slot_checks, slot_bad, slot_examples = 0, 0, []
    for name in N.NATIVE_NAMES:
        seeds = [master.getrandbits(32) for _ in range(scaled(OPTIONS['cases']))]
        if name in N.NOT_MODELLED or not wanted(name):
            continue
        tally = Tally()
        for seed in seeds:
            rng = random.Random(seed)
            rig.restore()
            machine.restore(saved)
            scene = Scene(rig, rng)
            scene.prefer = PREFER.get(name)
            case = Case(rig, machine, rng)
            params = case.commit(make_args(SPEC[name], scene, case, rng))
            game, host = setup_model(scene, seed, machine)
            rig.responder = Responder(seed, scene)
            index = INDEX[name]

            def model_run():
                error, result = machine._call_native(index, params)
                return error, result

            def emu_run():
                rig.w32(rig.cells, 0x55555555)
                error = s32(rig.call(SCR_CALL_NATIVE, rig.base, index, rig.cells, rig.base + machine.data_offset + params))
                return error, rig.emu.mem.s32(rig.cells)

            outcome = compare(rig, machine, game, host, model_run, emu_run)
            tally.add(outcome, '%s seed %d' % (name, seed))
            # where the handler keeps the pointer of each string argument (ref_natives.STRING_SLOT)
            start, end, _leaders = coverage.functions[name if name != 'newWorldAlways' else 'newWorld']
            cells = [machine.cell(params + 4 + 4 * k) for k in range(len(SPEC[name].split()))]
            for ra, address, out in rig.addr_log:
                where = [k for k, cell in enumerate(cells) if cell == address]
                if start <= ra < end and len(where) == 1 and 0 < SP - 0x20 - out < 0x2000:
                    known = N.STRING_SLOT.get(name, {})
                    slot_checks += 1
                    if known.get(where[0], known.get(None)) != SP - 0x20 - out:
                        slot_bad += 1
                        slot_examples.append('%s argument %d: slot 0x%x' % (name, where[0], SP - 0x20 - out))
        hit, total = coverage.numbers(rig.pcs, name if name != 'newWorldAlways' else 'newWorld')
        executed.add(name)
        stats['cases'] += tally.cases
        stats['faults'] += tally.faults
        report(name, tally.bad, tally.cases, 'result, call-outs, bytes written, seed, script memory; %d call-outs, '
               '%d null-pointer cases agreed, %d/%d basic blocks' % (tally.calls, tally.faults, hit, total),
               tally.examples)
    stats['executed'] = executed
    if not OPTIONS['filter'] or OPTIONS['filter'] == 'builtins':
        report('string pointer slots', slot_bad, slot_checks, 'the stack word each handler passes to scr_getAddr '
               'is where ref_natives.STRING_SLOT says (bytes below the handler\'s entry stack pointer)',
               sorted(set(slot_examples)))


def group_machinery(rig, coverage, stats):
    """The host side of the script machine, called directly (not through a built-in)."""
    image = synthetic_image()
    rig.place(image)
    machine = new_machine(image)
    saved = machine.snapshot()
    master = random.Random(OPTIONS['seed'] ^ 0x5EED)
    mem = rig.emu.mem

    def run(label, count, body):
        """body(scene, game, rng) -> (model_run, emu_run)."""
        tally = Tally()
        for _ in range(scaled(count)):
            seed = master.getrandbits(32)
            rng = random.Random(seed)
            rig.restore()
            machine.restore(saved)
            scene = Scene(rig, rng)
            game, host = setup_model(scene, seed, machine)
            rig.responder = Responder(seed, scene)
            model_run, emu_run = body(scene, game, rng)
            tally.add(compare(rig, machine, game, host, model_run, emu_run), '%s seed %d' % (label, seed))
        return tally

    def text(scene, value):
        return scene.cstring(value)

    def queue_body(scene, game, rng):
        names = [rng.choice(scene.entries) for _ in range(rng.randrange(1, 5))]
        pointers = [text(scene, name) for name in names]

        def model_run():
            for name in names:
                game.queue_deferred(name)
            return 0

        def emu_run():
            for pointer in pointers:
                rig.call(A['script_queueDeferred'], pointer)
            return 0
        return model_run, emu_run

    tally = run('queue', 150, queue_body)
    report('script_queueDeferred', tally.bad, tally.cases, 'names land in the half that is not being run; the 65th '
           'is dropped', tally.examples)

    def deferred_body(scene, game, rng):
        ticks = rng.randrange(1, 4)

        def model_run():
            for _ in range(ticks):
                game.run_deferred()
            return 0

        def emu_run():
            for _ in range(ticks):
                rig.call(A['script_runDeferred'])
            return 0
        return model_run, emu_run

    tally = run('deferred', 250, deferred_body)
    report('script_runDeferred', tally.bad, tally.cases, '1-3 ticks of the Script task: runs in order, nested '
           'built-ins, the swap; %d call-outs' % tally.calls, tally.examples)

    def post_body(scene, game, rng):
        name = rng.choice(scene.entries)
        pointer = text(scene, name)
        set_first = rng.random() < 0.5

        def model_run():
            if set_first:
                game.set_post_action(name)
            game.run_post_action()
            game.run_post_action()
            return 0

        def emu_run():
            if set_first:
                rig.call(A['script_setPostAction'], pointer)
            rig.call(A['script_runPostAction'])
            rig.call(A['script_runPostAction'])
            return 0
        return model_run, emu_run

    tally = run('post', 200, post_body)
    report('post action', tally.bad, tally.cases, 'script_setPostAction, script_runPostAction twice (the second finds '
           'nothing unless the script set a new one)', tally.examples)

    def by_name_body(scene, game, rng):
        name = rng.choice(scene.entries + [b'Alpha', b'alphabet'])
        pointer = text(scene, name)
        return (lambda: game.run_script(name)), (lambda: s32(rig.call(A['script_runByName'], pointer)))

    tally = run('byname', 200, by_name_body)
    report('script_runByName', tally.bad, tally.cases, 'result, the missing-entry stamp, nested effects',
           tally.examples)

    def vars_body(scene, game, rng):
        steps = []
        for _ in range(rng.randrange(1, 12)):
            name = scene.vary_case(rng.choice(scene.variables + [b'brand_new', b'Another1']))
            steps.append((rng.choice('ggsscI'), name, text(scene, name), any_int(rng) if rng.random() < 0.5
                          else rng.randrange(-200, 200), rng.randrange(14)))

        def model_run():
            out = []
            for kind, name, _pointer, value, index in steps:
                if kind == 'g':
                    out.append(game.var_get(name))
                elif kind == 's':
                    game.var_set(name, value)
                elif kind == 'c':
                    game.vars_clear_all()
                else:
                    entry = game.var_by_index(index)
                    out.append(None if entry is None else entry)
            return out

        def emu_run():
            out = []
            for kind, _name, pointer, value, index in steps:
                if kind == 'g':
                    out.append(s32(rig.call(A['vars_get'], pointer)))
                elif kind == 's':
                    rig.call(A['vars_set'], pointer, value)
                elif kind == 'c':
                    rig.call(A['vars_clearAll'])
                else:
                    where = rig.call(A['vars_getByIndex'], index, rig.cells + 0x40) & M32
                    out.append(None if where == 0 else (mem.cstr(where).encode('latin-1'), mem.s32(rig.cells + 0x40)))
            return out
        return model_run, emu_run

    tally = run('vars', 300, vars_body)
    report('quest variables', tally.bad, tally.cases, 'random sequences of vars_get / vars_set / vars_clearAll / '
           'vars_getByIndex: results and every byte of the table', tally.examples)

    def reset_body(scene, game, rng):
        which = rng.choice(('clear', 'reset'))

        def model_run():
            game.clear_deferred() if which == 'clear' else game.reset_script_state()
            return 0

        def emu_run():
            rig.call(A['script_clearDeferred' if which == 'clear' else 'script_resetState'])
            return 0
        return model_run, emu_run

    tally = run('reset', 40, reset_body)
    report('queue reset', tally.bad, tally.cases, 'script_clearDeferred and script_resetState', tally.examples)

    garbage = [0]

    def stale_body(scene, game, rng):
        name = rng.choice(STALE_ENTRIES).encode()
        pointer = text(scene, name)
        return (lambda: game.run_script(name)), (lambda: s32(rig.call(A['script_runByName'], pointer)))

    tally = run('stale', 240, stale_body)
    report('refused string address', tally.bad, tally.cases, 'entry points that pass an address scr_getAddr refuses: '
           'the handler uses the pointer the last call with the same stack slot left; %d further runs not '
           'compared, where the model cannot know the stack word (StackGarbage)' % tally.garbage, tally.examples)
    del garbage

    def state_body(scene, game, rng):
        steps = []
        for _ in range(rng.randrange(1, 8)):
            kind = rng.choice(('avail', 'complete', 'medal', 'evil', 'decision', 'flag', 'hp'))
            steps.append((kind, rng.randrange(5), rng.choice(list(range(13)) + [13, 40]), rng.choice((-1, 0, 1, 2, 3)),
                          rng.choice((0, 1)), rng.choice((-1, 0, 1, 2, 3)), rng.randrange(8)))

        def model_run():
            out = []
            for kind, diff, mission, value, flag, slot, bit in steps:
                if kind == 'avail':
                    game.mission_set_available(diff, mission, value)
                    out.append(game.mission_is_available(diff, mission))
                elif kind == 'complete':
                    game.mission_set_complete(diff, mission, value)
                    out.append(game.mission_is_complete(diff, mission))
                elif kind == 'medal':
                    out.append(game.mission_get_medal(mission, value, flag))
                elif kind == 'evil':
                    game.set_evil(flag)
                    out.append(game.get_evil())
                elif kind == 'decision':
                    game.set_made_decision(flag)
                    out.append(game.get_made_decision())
                elif kind == 'flag':
                    game.player_set_flag(slot, bit, flag)
                    out.append(game.player_get_flag(max(slot, 0), bit))
                else:
                    out.append(game.count_players_with_hp())
            return out

        def emu_run():
            out = []
            call = lambda name, *args: s32(rig.call(A[name], *args))
            for kind, diff, mission, value, flag, slot, bit in steps:
                if kind == 'avail':
                    call('mission_setAvailable', diff, mission, value)
                    out.append(call('mission_isAvailable', diff, mission))
                elif kind == 'complete':
                    call('mission_setComplete', diff, mission, value)
                    out.append(call('mission_isComplete', diff, mission))
                elif kind == 'medal':
                    out.append(call('mission_getMedal', mission, value, flag))
                elif kind == 'evil':
                    call('game_setEvil', flag)
                    out.append(call('game_getEvil'))
                elif kind == 'decision':
                    call('game_setMadeDecision', flag)
                    out.append(call('game_getMadeDecision'))
                elif kind == 'flag':
                    call('player_setFlag', slot, bit, flag)
                    out.append(call('player_getFlag', max(slot, 0), bit))
                else:
                    out.append(call('game_countPlayersWithHp'))
            return out
        return model_run, emu_run

    tally = run('state', 300, state_body)
    report('campaign state functions', tally.bad, tally.cases, 'mission available / complete, medals, evil, decision, '
           'player flags called directly with arguments the built-ins never pass', tally.examples)

    # which object a name means: the real lookup against ref_objects.NameTable on the same table
    tally = Tally()
    for _ in range(scaled(400)):
        seed = master.getrandbits(32)
        rng = random.Random(seed)
        rig.restore()
        scene = Scene(rig, rng)
        game, host = scene.model(Responder(seed, scene))
        name = scene.vary_case(rng.choice(scene.names + [b'nobody']))
        limit = rng.choice((2, 3, 100, 0x200))
        pointer = scene.cstring(name)
        out = rig.scratch + 0x300
        rig.emu.reset_log()
        rig.call(0x14BF58, pointer, rig.obj_base + 0x1000 * 190, limit)
        found = []
        while mem.u32(rig.obj_base + 0x1000 * 190 + 4 * len(found)) != 0:
            found.append(mem.u32(rig.obj_base + 0x1000 * 190 + 4 * len(found)))
        first = rig.call(0x14F498, pointer) & M32
        mine = [obj.addr for obj in game.find(name, limit)]
        mine_first = game.find_first(name)
        outcome = Outcome()
        if found != mine or first != (mine_first.addr if mine_first else 0):
            outcome.problems.append('%r limit %d: %r / 0x%x, model %r' % (name, limit, found, first, mine))
        tally.add(outcome, 'lookup seed %d' % seed)
        del out
    report('name lookup', tally.bad, tally.cases, 'world_findObjectsByName / world_findObjectByName against '
           'ref_objects.NameTable: the same objects in the same order', tally.examples)


def script_strings(machine):
    """The string literals a script passes around: every PUSH.C operand that is the address
    of a packed string in the initialised data."""
    found = []
    seen = set()
    for _offset, (op, operand, _next) in sorted(machine._decoded.items()):
        if op == 0x27 and isinstance(operand, int) and 0 <= operand < machine.hea and not operand & 3 \
                and operand not in seen:
            seen.add(operand)
            try:
                text = machine.get_string(operand)
            except ref_amx.HostFault:
                continue
            if 0 < len(text) < 24 and all(32 < c < 127 for c in text):
                found.append(text)
    return sorted(set(found))


def dry_run(rig, machine, saved, entry, names, seed):
    """Names the model asks the name table and the variable table for when it runs an entry
    point on a throw-away state."""
    rng = random.Random(seed ^ 0xD27)
    scene = Scene(rig, rng, names=rng.sample(names, min(len(names), 12)), objects=4)
    game, _host = setup_model(scene, seed, machine)
    asked = []
    find, find_first, var_get = game.find, game.find_first, game.var_get

    def note(function):
        def wrapped(name, *rest):
            if name and name not in asked and len(name) < 24 and all(32 < c < 127 for c in name):
                asked.append(bytes(name))
            return function(name, *rest)
        return wrapped
    game.find, game.find_first, game.var_get = note(find), note(find_first), note(var_get)
    machine.budget = 100000
    try:
        game.run_script(entry)
    except (ref_amx.HostFault, ref_amx.Limit, O.ObjectError):
        pass
    machine.budget = None
    return asked


def group_scripts(rig, coverage, stats):
    directory = OPTIONS['scripts']
    files = sorted(f for f in os.listdir(directory) if f.lower().endswith('.scr')) if os.path.isdir(directory) else []
    if not files:
        print('SKIP  scripts    no *.scr files in %s (unpack the level scripts there, or pass --scripts DIR)'
              % directory)
        return
    if OPTIONS['quick']:
        files = files[::4]
    master = random.Random(OPTIONS['seed'] ^ 0xC0DE)
    seeds = 1 if OPTIONS['quick'] else OPTIONS['seeds']
    tally = Tally()
    entries = finished = scripts = 0
    calls_by_native = {}
    started = time.time()
    for filename in files:
        if OPTIONS['filter'] not in (None, 'scripts') and not wanted(filename):
            continue
        scripts += 1
        with open(os.path.join(directory, filename), 'rb') as source:
            image = source.read() + bytes(256)
        error, bound = rig.place(image)
        machine = new_machine(image)
        if error != 0 or bound != 0:
            outcome = Outcome()
            outcome.problems.append('scr_load %d, scr_registerNatives %d' % (error, bound))
            tally.add(outcome, filename)
            continue
        saved = machine.snapshot()
        strings = script_strings(machine)
        publics = [name for name, _address in machine.publics()]
        names = [s for s in strings if s not in publics][:400] or NAME_POOL
        for name in publics:
            entries += 1
            done = False
            for _ in range(seeds):
                seed = master.getrandbits(32)
                rng = random.Random(seed)
                rig.restore()
                machine.restore(saved)
                # a dry run of the model tells which names this entry point looks up; the
                # compared run then gets objects and variables under those names
                used = dry_run(rig, machine, saved, name, names, seed)
                rig.restore()
                machine.restore(saved)
                pool = (used + rng.sample(names, min(len(names), 8)))[:40]
                scene = Scene(rig, rng, names=pool, variables=pool + rng.sample(names, min(len(names), 20)),
                              entries=[p for p in publics[:6]] + [b''], objects=rng.randrange(8, 30))
                scene.bias = {'dialog_isOpen': 0.2, 'memcard_isBusy': 0.2}
                game, host = setup_model(scene, seed, machine)
                machine.budget = 300000
                rig.responder = Responder(seed, scene)
                pointer = scene.cstring(name)

                def model_run():
                    return game.run_script(name)

                def emu_run():
                    return s32(rig.call(A['script_runByName'], pointer, max_steps=40000000))

                outcome = compare(rig, machine, game, host, model_run, emu_run)
                machine.budget = None
                tally.add(outcome, '%s %s seed %d' % (filename, name.decode('latin-1'), seed))
                if outcome.fault is None:
                    done = True
                    for called, _args in host.log:
                        calls_by_native[called] = calls_by_native.get(called, 0) + 1
            finished += done
    report('shipped entry points', tally.bad, tally.cases,
           'whole entry points of %d scripts with the original built-ins against the model\'s: result, call-outs, '
           'bytes written, seed, script memory; %d call-outs, %d runs in which both sides stop at a null object, '
           '%d not compared (%d endless under random answers, %d where the original reads a stack word the model '
           'cannot know); %d of %d entry points ran to their end; %.0f s'
           % (scripts, tally.calls, tally.faults, tally.limit + tally.garbage, tally.limit, tally.garbage, finished,
              entries, time.time() - started),
           tally.examples)
    stats['entries'] = (finished, entries)


GROUPS = [('machinery', group_machinery), ('builtins', group_builtins), ('scripts', group_scripts)]


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
    argv = sys.argv[1:] if argv is None else list(argv)
    positional, index = [], 0
    while index < len(argv):
        arg = argv[index]
        if arg == '-v':
            OPTIONS['verbose'] = True
        elif arg == '--quick':
            OPTIONS['quick'] = True
        elif arg in ('--scripts', '--cases', '--seeds', '--seed', '-k') and index + 1 < len(argv):
            index += 1
            key = {'-k': 'filter'}.get(arg, arg[2:])
            OPTIONS[key] = argv[index] if arg in ('-k', '--scripts') else int(argv[index])
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
        print('SKIP  %s is not the US v2.00 executable these addresses belong to (SHA-256 %s); nothing was run'
              % (elf, digest))
        return 0
    print('executable: %s  (SHA-256 matches US v2.00)' % elf)
    sys.setrecursionlimit(20000)
    rig = Rig(elf)
    rig.checkpoint()
    coverage = Coverage(rig)
    stats = {'cases': 0, 'faults': 0, 'executed': set()}
    group_filter = OPTIONS['filter']
    for name, function in GROUPS:
        if group_filter and group_filter in [g for g, _f in GROUPS] and group_filter != name:
            continue
        if group_filter and group_filter not in [g for g, _f in GROUPS] and name != 'builtins' \
                and not (name == 'scripts' and group_filter.lower().endswith('.scr')):
            continue
        print('--- %s' % name)
        function(rig, coverage, stats)
    # ---- coverage
    names = [n for n in dict.fromkeys(coverage.handlers.values())]
    entered = [n for n in names if coverage.numbers(rig.pcs, n)[0] > 0]
    hit = sum(coverage.numbers(rig.pcs, n)[0] for n in coverage.functions)
    total = sum(coverage.numbers(rig.pcs, n)[1] for n in coverage.functions)
    full = sum(1 for n in coverage.functions if coverage.numbers(rig.pcs, n)[0] == coverage.numbers(rig.pcs, n)[1])
    print('--- coverage')
    print('      built-in handlers entered: %d of %d distinct (%d table names); not modelled: %s'
          % (len(entered), len(names), len(N.NATIVE_NAMES), ', '.join(N.NOT_MODELLED) or 'none'))
    print('      basic blocks executed: %d of %d in %d functions (handlers, helpers, host machinery); '
          '%d functions fully covered' % (hit, total, len(coverage.functions), full))
    partial = [(n, coverage.numbers(rig.pcs, n)) for n in coverage.functions
               if 0 < coverage.numbers(rig.pcs, n)[0] < coverage.numbers(rig.pcs, n)[1]]
    never = [n for n in coverage.functions if coverage.numbers(rig.pcs, n)[0] == 0]
    if partial:
        print('      partly covered: ' + ', '.join('%s %d/%d' % (n, a, b) for n, (a, b) in sorted(partial)))
    if never:
        print('      never entered: ' + ', '.join(sorted(never)))
    if OPTIONS['verbose']:
        for n, _numbers in sorted(partial):
            print('        %s misses blocks at %s' % (n, ' '.join('0x%x' % a for a in coverage.missing(rig.pcs, n))))
    if rig.unknown:
        print('      calls to addresses that are neither real nor stubs: '
              + ', '.join('0x%x x%d' % item for item in sorted(rig.unknown.items())))
    if 'entries' in stats:
        print('      shipped entry points run end to end: %d of %d' % stats['entries'])
    passed = sum(1 for _, ok in RESULTS if ok)
    print('%d properties: %d PASS, %d FAIL' % (len(RESULTS), passed, len(RESULTS) - passed))
    return 0 if passed == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
