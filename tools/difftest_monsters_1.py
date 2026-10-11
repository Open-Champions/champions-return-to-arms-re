#!/usr/bin/env python3
"""difftest_monsters_1.py - compare tools/ref_monsters_1.py with the game's own code for
batch 1 of the ordinary monster classes (SmallSpider, Gnaw, Mosquito, Scorpion, Badger).

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_monsters_1.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                       [--ticks N] [-k TEXT] [-v] [--fpu MODEL]
                                       [--trace-first]

    --quick       a tenth of the ticks
    --seed N      seed of the random runs (default 7301); a seed repeats exactly
    --ticks N     ticks per run (default 1500; two runs per class)
    -k TEXT       only the runs whose name contains TEXT
    -v            print the first mismatches of every failing property, and the blocks
                  never entered
    --fpu MODEL   ps2 (default), ps2g1, chop or nearest: the adder model of BOTH sides
    --trace-first stop at the first mismatching call and print both sides

What is compared
    The ORIGINAL constructor, run function and set-state function of each class (and the
    other functions of ref_monsters_1.MODELLED) are executed by tools/ee_emu.py - an
    instruction interpreter, not a console - on an object the original constructor
    itself built, with the game's own virtual table.  The creature base class underneath
    runs for real too (everything in ref_creature.MODELLED and
    ref_arena_monsters.MODELLED), so one "run" call of this test is a whole monster tick:
    pending damage, Creature_run, activity, animation step, target pick, the class's
    switch, its set-state, and on a death the class's death branch.  Every such call is
    run through the model first, on a copy-on-write view of the same memory, and these
    must be equal:
      calls    the sequence of calls to everything outside the models, with arguments
      writes   the set of bytes stored outside the stack, and their final values
      seed     the shared seed 0x404464, and that it advanced exactly as many times as
               the model says it drew
      result   the value returned
    Floats are compared as 32-bit patterns under the interpreter's floating-point model.

What runs for real and what is a stub
    Real: ref_monsters_1.MODELLED, ref_arena_monsters.MODELLED, ref_creature.MODELLED,
    the three angle functions and the C library (the software doubles among it).
    Everything else is a recording stub answered by a seeded script (class World): the
    sight tests, the hit helpers, the animation functions, object construction,
    Creature_setStats, loot, effects.  A call to an address that is neither real nor a
    known stub is reported as a failure.

Scenarios (the run names)
    one per class, each on machine A and machine B.  Targets come and go through the real
    target pick and by the driver's hand, at ranges and angles the stubbed sight tests
    answer at random with a bias the driver moves (and, on a quarter of the ticks, with
    "no" to all but the n-th question, so that each test of a chain is reached); damage
    arrives through slot 2; the
    creature dies in whatever state it is in and is constructed again; the driver also
    asks for every state number, valid or not, and stores state numbers no set-state
    would store.

Per-machine inputs, set both ways (machine A / machine B of the run name)
    exactly those of tools/difftest_creature.py: activity by the camera, the local alive
    list, a status counter decremented by drawing, the decal option.
"""
import hashlib
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError                 # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_arena_monsters as AM                 # noqa: E402
import ref_monsters_1 as M1                     # noqa: E402
import difftest_creature as DC                  # noqa: E402
import difftest_arena_monsters as DA            # noqa: E402
from difftest_creature import Res, f32, fl, rd, M32      # noqa: E402,F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = DC.OPTIONS
OPTIONS.update({'seed': 7301, 'ticks': 1500})

# function bodies for the coverage count: name -> (start, end)
BODIES = {
    'SmallSpider_ctor': (0x2AB450, 0x2AB590), 'SmallSpider_run': (0x2AB5D8, 0x2AB704),
    'SmallSpider_setState': (0x2AB704, 0x2AB8E0), 'SmallSpider_onTouch': (0x2AB8E0, 0x2AB958),
    'Gnaw_ctor': (0x26741C, 0x267604), 'Gnaw_run': (0x267654, 0x267A0C), 'Gnaw_setState': (0x267A0C, 0x267CF4),
    'Mosquito_ctor': (0x297788, 0x297A14), 'Mosquito_run': (0x297B30, 0x297F54),
    'Mosquito_setState': (0x297F54, 0x2982CC), 'Mosquito_losePart': (0x2982CC, 0x298418),
    'Scorpion_ctor': (0x2A4D68, 0x2A5030), 'Scorpion_run': (0x2A5068, 0x2A55EC),
    'Scorpion_setState': (0x2A55EC, 0x2A59F0), 'Scorpion_severPart': (0x2A59F0, 0x2A5AF4),
    'Badger_ctor': (0x244018, 0x244320), 'Badger_run': (0x244380, 0x244A9C), 'Badger_slot11': (0x244A9C, 0x244AA4),
    'Badger_setState': (0x244AA4, 0x244E4C),
    'str_prefixDiffers': (0x159C20, 0x159C94),
}

REAL = set(RC.MODELLED.values()) | set(AM.MODELLED.values()) | set(M1.MODELLED.values()) | set(DC.REAL_OTHER)

ANIM_FLAGS = (0x08, 0x08, 0x08, 0x00, 0x00, 0x10, 0x18, 0x20, 0x28, 0x80, 0x80, 0x88, 0x90, 0x98, 0xA0)
EVENTS = (0, 0, 0, 0, 1, 1, 1, 2, 2, 3, 4, 4, 5, 6, 0x80, 0x81, 0x82, 0x84)

# the classes: kind -> what the driver needs to know
#   table    the game's own virtual table        defs     the class definitions the constructor can pick
#   ctor     entry key and how to order (c, type name, position, facing, property list)
#            ('x' = one more argument, drawn from `extra`)
#   states   what the driver asks set-state for (every number, valid or not, and the busy ones again)
CLASSES = {
    'smallspider': dict(name='SmallSpider', table=M1.VT_SMALLSPIDER, defs=(M1.DEF_SMALLSPIDER,), order='ctvfp',
                        types=(b'SmallSpider',), states=list(range(0, 0x16)) + [0x17, 0x40, 0xFFFFFFFF, 0, 0, 1, 1, 0x14]),
    'gnaw': dict(name='Gnaw', table=M1.VT_GNAW, defs=(M1.DEF_GNAW,), order='ctvfp', types=(b'Gnaw',),
                 states=list(range(0, 0x16)) + [0x17, 0x40, 0xFFFFFFFF, 3, 5, 5, 6, 6, 0x14, 0x12, 0x13, 0x10]),
    'mosquito': dict(name='Mosquito', table=M1.VT_MOSQUITO, defs=(M1.DEF_MOSQUITO,), order='cvfpt',
                     types=(b'Mosquito', b'MosquitoLarge', b'mosquitolarge2', b'mosquit', b'Mosquitolarg'),
                     states=list(range(0, 0x19)) + [0x40, 0xFFFFFFFF, 3, 5, 5, 6, 6, 0x14, 0x12, 0x12, 0x13, 0x10, 0x17]),
    'scorpion': dict(name='Scorpion', table=M1.VT_SCORPION, defs=(M1.DEF_SCORPION,), order='ctvfp', types=(b'Scorpion',),
                     states=list(range(0, 0x1A)) + [0x40, 0xFFFFFFFF, 3, 5, 5, 6, 6, 6, 6, 6, 0x14, 0x12, 0x12, 0x13, 0x10,
                                                    0x17, 0x18]),
    'badger': dict(name='Badger', table=M1.VT_BADGER, defs=(M1.DEF_BADGER, M1.DEF_BADGER + M1.DEF_BADGER_STEP),
                   order='ctvfpx', extra=(0, 0, 1, 1), types=(b'Badger', b'SnoBadge'),
                   states=list(range(0, 0x16)) + [0x40, 0xFFFFFFFF, 3, 3, 5, 5, 6, 6, 7, 7, 8, 9, 10, 10, 0x14, 0x12, 0x12,
                                                  0x13, 0x10]),
}

# entry points: key -> (address, argument kinds, result kind, model method); kinds as in
# tools/difftest_creature.py (c the creature under test, i integer, v vector by pointer,
# f float pattern in f12..)
ENTRIES = {
    'Creature_takeDamage': (0x116638, 'ciif', 'n', 'take_damage'),
    'Creature_slot7': (0x11A260, 'ci', 'n', 'slot7_path_done'),
    'SmallSpider_ctor': (0x2AB450, 'civii', 'n', 'smallspider_ctor'),
    'SmallSpider_run': (0x2AB5D8, 'c', 'n', 'smallspider_run'),
    'SmallSpider_setState': (0x2AB704, 'ci', 'n', 'smallspider_set_state'),
    'SmallSpider_onTouch': (0x2AB8E0, 'ci', 'n', 'smallspider_on_touch'),
    'Gnaw_ctor': (0x26741C, 'civii', 'n', 'gnaw_ctor'),
    'Gnaw_run': (0x267654, 'c', 'n', 'gnaw_run'),
    'Gnaw_setState': (0x267A0C, 'ci', 'n', 'gnaw_set_state'),
    'Mosquito_ctor': (0x297788, 'cviii', 'n', 'mosquito_ctor'),
    'Mosquito_run': (0x297B30, 'c', 'n', 'mosquito_run'),
    'Mosquito_setState': (0x297F54, 'ci', 'n', 'mosquito_set_state'),
    'Mosquito_losePart': (0x2982CC, 'ci', 'n', 'mosquito_lose_part'),
    'Scorpion_ctor': (0x2A4D68, 'civii', 'n', 'scorpion_ctor'),
    'Scorpion_run': (0x2A5068, 'c', 'n', 'scorpion_run'),
    'Scorpion_setState': (0x2A55EC, 'ci', 'n', 'scorpion_set_state'),
    'Scorpion_severPart': (0x2A59F0, 'ci', 'n', 'scorpion_sever_part'),
    'Badger_ctor': (0x244018, 'civiii', 'n', 'badger_ctor'),
    'Badger_run': (0x244380, 'c', 'n', 'badger_run'),
    'Badger_setState': (0x244AA4, 'ci', 'n', 'badger_set_state'),
    'str_prefixDiffers': (0x159C20, 'ii', 'i', 'str_prefix_differs'),
}


class RealSet:
    def __contains__(self, target):
        return target in REAL or DC.LIB_LO <= target < DC.LIB_HI


# ---------------------------------------------------------------------------------------
# The scripted world
# ---------------------------------------------------------------------------------------
class World(DA.World):
    """difftest_arena_monsters' world with the class definitions, tables and type names of
    this batch's classes on top."""

    def build(self, rng):
        DA.World.build(self, rng)
        emu, mem = self.emu, self.mem
        info = CLASSES[self.akind]
        self.def_entries = {}
        for d in info['defs']:                                  # entry k keeps its resolved pointer at +8k+4
            count = 3
            while 0x500000 <= mem.u32(d + 8 * count) < 0x5C0000 and count < 0x40:
                count += 1
            mem.w32(d + 0xC, self.model)
            mem.w32(d + 0x14, 0x00C00080)
            for k in range(3, count):
                rec = emu.alloc(0x40)
                mem.w32(d + 8 * k + 4, rec)
                self.anim_entries[rec] = (d, k)
            self.def_entries[d] = count
        for slot in range(1, 40):                               # the game's own table: what is not real is a named stub
            fn = mem.u32(info['table'] + 8 * slot + 4)
            if fn not in REAL:
                self.addr_name.setdefault(fn, 'Creature.v%d' % slot)
        self.type_names = []
        for text in info['types']:
            s = emu.alloc(32)
            mem.write(s, text + b'\0')
            self.type_names.append(s)
        self.item_name = emu.alloc(16)

    # ---- answers ------------------------------------------------------------------------
    see_nth = None          # when set: only the n-th sight question of a call is answered yes

    def _sight(self, rng):
        """Is the answer to this sight question yes?  Usually a coin with the driver's bias;
        on ticks the driver picks, exactly the n-th question of the call - so that every
        position of a class's chain of range and arc tests gets to be the first true one.
        (The count lives on the per-call generator, which each side has its own copy of.)"""
        n = getattr(rng, 'sight', 0)
        rng.sight = n + 1
        if self.see_nth is not None:
            return n == self.see_nth
        return rng.random() < self.see_bias

    def on_creature_canSeeObj(self, args, view, rng):
        return Res(rng.choice((1, 1, 0x100)) if self._sight(rng) else 0)

    def on_creature_findEnemyInCone(self, args, view, rng):
        return Res(rng.choice(self.others[:3] + self.players[:2]) if self._sight(rng) else 0)

    def on_GutChunk_ctorFromProp(self, args, view, rng):
        view.poke(args[0] + 0x1C4, 4, f32(rng.choice((0.0, 3.5, -1.25))))
        return Res()

    def on_Creature_hitTargetInArcEdge(self, args, view, rng):
        return Res(rng.choice((0, 1)))

    on_Creature_hitTargetAtReach = on_Creature_hitTargetInArcEdge

    def _clip_started(self, args, view, rng):
        view.poke(args[0] + 6, 2, rng.choice(ANIM_FLAGS))
        return Res()

    on_anim_start = on_anim_startBlendInOut = on_anim_push = _clip_started

    def on_anim_advance(self, args, view, rng):
        state, _sound, root, yaw = args[:4]
        view.poke(root, 4, rng.choice(DC.ROOTS))
        view.poke(root + 4, 4, rng.choice(DC.ROOTS))
        view.poke(yaw, 2, rng.choice((0, 0, 0, 300, 0xFF38, 4000)))
        if rng.random() < 0.3:
            view.poke(state + 6, 2, rng.choice(ANIM_FLAGS))
        return Res(rng.choice(EVENTS))


# ---------------------------------------------------------------------------------------
# The rig
# ---------------------------------------------------------------------------------------
class Rig(DA.Rig):
    def __init__(self, elf, seed, kind, machine, net):
        self.rng = random.Random(seed)
        emu = self.emu = EE(elf, fpu_model=OPTIONS['fpu'])
        self.world = World(emu, self.rng, kind, machine, net)
        emu.follow = self.real = RealSet()
        self.calls, self.buffers, self.unknown = [], {}, {}
        self.eview = DC.EmuView(emu)
        self.script_rng = None
        self.names = {}

        def add(addr, name, ext):
            if addr in REAL:
                return
            assert self.names.setdefault(addr, name) == name, (hex(addr), name, self.names[addr])
            emu.stub(addr, function=self.make_stub(name, ext), name=name)

        for name, ext in M1.EXTERNALS.items():
            if ext.addr:
                add(ext.addr, name, ext)
            elif name in self.world.stub_addr:
                add(self.world.stub_addr[name], name, ext)
        for addr, name in list(self.world.stub_name.items()) + list(self.world.addr_name.items()):
            if addr not in self.names:
                add(addr, name, M1.EXTERNALS.get(name) or RC.Ext(0, 'p', 0, 'n'))
        self.partial, self.partial_ops = [], {}
        for start, end in list(DC.BODIES.values()) + list(DA.BODIES.values()) + list(BODIES.values()):
            for pc in range(start, end, 4):
                w = emu.mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))

    # ---- interpreter side ---------------------------------------------------------------
    def decode(self, name, ext, emu):
        """As difftest_arena_monsters', plus the kind 'E': a damage descriptor the caller
        built on its stack, compared by what the code initialises - eight zero halfwords
        at +0x10, two 0xff bytes at +0x20, and four effect slots from +0x24 (id, three
        values; a free slot has id 0xffff and its values are not looked at)."""
        canon, outs = DA.Rig.decode(self, name, ext, emu)
        for i, kind in enumerate(ext.ints):
            if kind == 'E':
                index = sum(1 for k in ext.ints[:i] if k in 'ipvslSeOWE')
                canon.insert(index, self.decode_descriptor(emu.mem, emu.r[4 + i] & M32))
        return canon, outs

    @staticmethod
    def decode_descriptor(mem, v):
        if v == 0:
            return 0
        ok = all(mem.u16(v + 0x10 + 2 * k) == 0 for k in range(8)) and mem.u8(v + 0x20) == 0xFF \
            and mem.u8(v + 0x21) == 0xFF
        if not ok:
            return ('desc?', bytes(mem.read(v + 0x10, 0x34)).hex())
        slots = []
        for k in range(4):
            ident = mem.u16(v + 0x24 + 8 * k)
            slots.append(None if ident == 0xFFFF else
                         (ident, mem.u16(v + 0x26 + 8 * k), mem.u16(v + 0x28 + 8 * k), mem.u16(v + 0x2A + 8 * k)))
        return ('desc', tuple(slots))

    # ---- model side -----------------------------------------------------------------------
    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                ret = res.ret & (RC.M64 if M1.EXTERNALS[name].ret == 'q' else M32)
                return M1.shape_result(name, args, ret, res.f & M32, res.outs)
            return answer

    # ---- one call, both sides ---------------------------------------------------------------
    def compare(self, key, args, call_seed, trace=None):
        addr, kinds, ret_kind, method = ENTRIES[key]
        emu, world = self.emu, self.world
        mem = emu.mem
        seed_before = mem.u32(RC.G_RAND_SEED)
        mview = DC.ModelView(mem)
        model = M1.Model(mview, Rig.Callbacks(self, mview, random.Random(call_seed)))
        model_error = None
        try:
            mret = getattr(model, method)(*args)
        except EmuError as exc:
            model_error, mret = exc, None
        self.calls, self.buffers = [], {}
        self.eview.touched = set()
        self.script_rng = random.Random(call_seed)
        emu.reset_log()
        self.partial = []
        emu.trace = [] if trace is not None else None
        emu.r[29] = emu.stack_hi - 0x100
        ints, nfloat, scratch = [], 0, world.argbuf
        for a, k in zip(args, kinds):
            if k in 'ci':
                ints.append(ee_emu.s32(a & M32))        # a register holds a sign-extended 32-bit value
            elif k == 'v':
                for j in range(3):
                    mem.w32(scratch + 4 * j, a[j])
                ints.append(scratch)
                scratch += 0x10
            elif k == 'f':
                emu.f[12 + nfloat] = a & M32
                nfloat += 1
        emu_error = None
        try:
            eret = emu.call(addr, *ints, max_steps=4000000)
        except EmuError as exc:
            emu_error, eret = exc, None
        if trace is not None and emu.trace:
            trace.update(emu.trace)
        for c in emu.calls:
            if c.target not in self.real and c.target not in self.names:
                self.unknown[c.target] = self.unknown.get(c.target, 0) + 1
        out = {'key': key, 'fault': None, 'calls': None, 'writes': None, 'seed': None, 'result': None,
               'both_fault': None, 'draws': 0, 'model_calls': model.calls, 'emu_calls': self.calls}
        if model_error or emu_error:
            if model_error is None or emu_error is None:
                out['fault'] = 'model %r / original %r' % (model_error, emu_error)
            else:
                out['both_fault'] = getattr(emu_error, 'pc', 0)
            return out
        if model.calls != self.calls:
            out['calls'] = DC.describe_calls(model.calls, self.calls)
        lo, hi = world.argbuf, world.argbuf + 0x100
        ebytes = self.stored_bytes(lo, hi)
        mbytes = set()
        for a, size, _value in model.writes:
            mbytes.update(range(a, a + size))
        diff = []
        for a in sorted(ebytes | mbytes | self.eview.touched | mview.touched):
            x, y = mem.load(a, 1), mview.load(a, 1)
            if x != y:
                diff.append((a, x, y))
        if ebytes != mbytes or diff:
            text = ''
            if ebytes - mbytes:
                text += ' only original stores %s;' % sorted({where(world, a) for a in ebytes - mbytes})[:8]
            if mbytes - ebytes:
                text += ' only model stores %s;' % sorted({where(world, a) for a in mbytes - ebytes})[:8]
            if diff:
                text += ' values differ at %s' % [(where(world, a), '%02x' % x, '%02x' % y) for a, x, y in diff[:8]]
            out['writes'] = text
        s = seed_before
        for _ in range(model.draws):
            s = (s * 0x19660D + 0x3C6EF35F) & M32
        if not mem.u32(RC.G_RAND_SEED) == mview.load(RC.G_RAND_SEED, 4) == s:
            out['seed'] = 'model draws %d' % model.draws
        out['draws'] = model.draws
        if ret_kind == 'i' and (eret & M32) != ((mret or 0) & M32):
            out['result'] = 'original %08x model %08x' % (eret & M32, (mret or 0) & M32)
        out['ret'] = eret
        return out


def where(world, addr):
    for d in world.def_entries:
        if d <= addr < d + 0x140:
            return 'def+%x' % (addr - d)
    for size, blocks in world.pool.items():
        for b in blocks:
            if b <= addr < b + size:
                return 'pool%x+%x' % (size, addr - b)
    return DA.where(world, addr)


class Coverage(DC.Coverage):
    def __init__(self, mem):
        self.parts = {name: (start, end) + DC.analyse(mem, start, end) for name, (start, end) in BODIES.items()}
        self.pcs = set()


# ---------------------------------------------------------------------------------------
# The driver
# ---------------------------------------------------------------------------------------
class Driver(DC.Driver):
    """difftest_creature's driver (timers, counters, flags, activity, the per-machine
    inputs) plus what these classes look at."""

    def __init__(self, rig):
        DC.Driver.__init__(self, rig)
        self.need_ctor = True

    def respawn(self):
        self.dead_ticks = 0
        self.need_ctor = True

    def between_class(self):
        rng, mem, world = self.rng, self.mem, self.world
        c, r = world.C, rng.random
        if r() < 0.03:                                          # enemies in sight and reach: seldom, half, mostly
            world.see_bias = rng.choice((0.06, 0.5, 0.5, 0.94))
        world.see_nth = rng.randrange(10) if r() < 0.25 else None
        if r() < 0.03:                                          # any object as the target, or none
            mem.w32(c + 0x234, rng.choice([0] + [world.nodes[o] for o in world.others[:4] + world.players]))
        elif not mem.u32(c + 0x234) and mem.s16(c + 0x232) != 0x14 and r() < 0.3:
            player = rng.choice(world.players)                  # a live enemy: the usual case in a fight
            mem.w32(player + 0xC, 0x40)
            mem.w64(player + 0xA8, 0)
            mem.w32(c + 0x234, world.nodes[player])
        if r() < 0.03:
            target = mem.u32(c + 0x234)
            if target:
                obj = mem.u32(target + 0xC)
                mem.wf32(obj + 0x308, rng.choice((0.0, 150.0, -200.0, 99.0)))
                mem.wf32(obj + 0x30C, rng.choice((0.0, 80.0, -120.0)))
                mem.w16(obj + 0x38, rng.randrange(0x10000))
        if r() < 0.05:
            mem.w16(c + 0x11A, rng.choice(ANIM_FLAGS))
        if r() < 0.03:
            mem.w32(c + 0xF4, (mem.u32(c + 0x300) + rng.choice((-5, 0, 1, 40, 400))) & M32)
        if r() < 0.02:
            for off, values in ((0xD0, (7, 30, 31, 101, 0xFFFB)), (0xD2, (9, 45, 46, 150, 0xFFF9)), (0xD4, (50, 200))):
                mem.w16(c + off, rng.choice(values))
        if r() < 0.01:                                          # a state number no set-state would store
            mem.w16(c + 0x232, rng.choice((0x15, 0x16, 0x18, 0x24, 0x30, 0x7FFF, 0xFFF0, 2, 4, 7, 0x11, 0x12, 0x12,
                                           0x13, 0x10, 0x17, 8, 9, 10)))
        if r() < 0.02:                                          # hidden or not (what a death tests)
            mem.w32(c + 0xC, mem.u32(c + 0xC) ^ 2)
        elif r() < 0.1:
            mem.w32(c + 0xC, mem.u32(c + 0xC) & ~2)
        if r() < 0.02:
            mem.w32(c + 0xE8, rng.choice((0, 1, 0x10, 0x5F, 0x40)))
        if r() < 0.05:                                          # the difficulty setting (shared game state)
            mem.w32(M1.G_DIFFICULTY, rng.choice((0, 1, 2, 3)))
        kind = world.akind
        if kind == 'badger' and r() < 0.05:                     # "this attack has hit"
            mem.w32(c + 0x3C8, rng.choice((0, 0, 1)))
        if kind == 'scorpion' and mem.s16(c + 0x232) == 7 and r() < 0.5:      # a sting under each difficulty
            mem.w32(M1.G_DIFFICULTY, rng.choice((0, 2, 3)))
        if kind == 'badger' and mem.s16(c + 0x232) == 3 and r() < 0.3:        # each test of the chase chain
            world.see_nth = rng.randrange(8)


DEATHS = {}             # kind -> {AI state the creature was in when a tick killed it: count}


def run(elf, name, seed, kind, machine, net, ticks, coverage, counts):
    rig = Rig(elf, seed, kind, machine, net)
    driver = Driver(rig)
    world, mem, rng = rig.world, rig.emu.mem, rig.rng
    info = CLASSES[kind]
    if coverage[0] is None:
        coverage[0] = Coverage(mem)
    cov = coverage[0]
    c = world.C
    bad = {'calls': [], 'writes': [], 'seed': [], 'result': [], 'fault': []}
    both = {}
    serial = [0]
    draws_by_entry = {}
    tick = 0
    died_in = DEATHS.setdefault(kind, {})
    cls = info['name']
    run_key, set_key, ctor_key, states = cls + '_run', cls + '_setState', cls + '_ctor', info['states']

    def do(key, *args):
        serial[0] += 1
        result = rig.compare(key, tuple(args), seed * 1000003 + serial[0], trace=cov.pcs)
        row = counts.setdefault(key, [0, 0])
        row[0] += 1
        failed = False
        for prop in ('fault', 'calls', 'writes', 'seed', 'result'):
            if result[prop]:
                failed = True
                bad[prop].append('tick %d %s(%s): %s' % (tick, key, ', '.join(
                    '%x' % a if isinstance(a, int) else str(a) for a in args), result[prop]))
        if result['both_fault'] is not None:
            both[result['both_fault']] = both.get(result['both_fault'], 0) + 1
            DC.FAULTS[result['both_fault']] = DC.FAULTS.get(result['both_fault'], 0) + 1
        if result.get('draws'):
            draws_by_entry[key] = draws_by_entry.get(key, 0) + result['draws']
        if failed:
            row[1] += 1
            if OPTIONS['trace_first']:
                print('first mismatch in run %s, tick %d, %s' % (name, tick, key))
                for prop in ('fault', 'calls', 'writes', 'seed', 'result'):
                    if result[prop]:
                        print('  %s: %s' % (prop, result[prop]))
                print('  model calls:')
                for call in result['model_calls']:
                    print('    ' + DC.fmt_call(call))
                print('  original calls:')
                for call in result['emu_calls']:
                    print('    ' + DC.fmt_call(call))
                sys.exit(1)
        return result

    def construct():
        world.clear_creature()
        pos = (f32(2000.0 + rng.uniform(-50, 50)), f32(3000.0 + rng.uniform(-50, 50)), f32(10.0))
        facing = rng.choice((rng.randrange(0x10000), 0xFFFF8000 | rng.randrange(0x8000)))
        values = {'c': c, 't': rng.choice(world.type_names), 'v': pos, 'f': facing, 'p': world.props,
                  'x': rng.choice(info.get('extra', (0,)))}
        do(ctor_key, *[values[k] for k in info['order']])
        # what the stubbed callees would have left: sane statistics and an active creature
        hp = rng.choice((300.0, 300.0, 1200.0))
        mem.wf32(c + 0x228, hp)
        mem.wf32(c + 0x22C, hp)
        mem.w8(c + 0x231, 0)
        mem.w32(c + 0xC8, 0)

    for tick in range(ticks):
        r = rng.random
        if driver.need_ctor:
            driver.need_ctor = False
            construct()
        driver.between()
        if driver.need_ctor:
            continue
        driver.between_class()
        if driver.pending_slot7 is not None:
            do('Creature_slot7', c, driver.pending_slot7)
            driver.pending_slot7 = None
        # damage arrives through the class's slot 2 (the base body in every class of this batch)
        if r() < 0.08:
            for _ in range(rng.choice((1, 1, 2))):
                attacker = rng.choice(world.others + world.players + [0])
                flags = 0
                for _k in range(rng.choice((0, 1, 1, 2, 3))):
                    flags |= rng.choice(DC.DAMAGE_FLAGS)
                amount = rng.choice((0.0, 3.0, 20.0, 20.0, 20.0, 60.0, 150.0, 400.0))
                do('Creature_takeDamage', c, attacker, flags, f32(amount))
        elif r() < 0.03:
            mem.w32(c + 0x2DC, rng.choice((0x2000, 0x2000, 0x2000 | 0x80000, 0x40000, 0x200000, 0x100000)))
        if r() < 0.04 and mem.s16(c + 0x232) != 0x14:           # a killing blow in a state of the driver's choice
            do(set_key, c, rng.choice(states))
            mem.w8(c + 0x231, 0)
            do('Creature_takeDamage', c, rng.choice(world.others + world.players + [0]), rng.choice(DC.DAMAGE_FLAGS),
               f32(5000.0))
        before = mem.s16(c + 0x232)
        do(run_key, c)
        if before != 0x14 and mem.s16(c + 0x232) == 0x14:
            died_in[before] = died_in.get(before, 0) + 1
        # the rest of the game asks for a state (cutscenes, scripts, other classes); the
        # driver asks for every number, valid or not
        if r() < 0.10:
            do(set_key, c, rng.choice(states))
        if kind == 'smallspider' and r() < 0.05:
            do('SmallSpider_onTouch', c, rng.choice(world.others + world.players + [0]))
        if kind == 'mosquito':
            if r() < 0.03:
                do('Mosquito_losePart', c, rng.choice((0, 1, 2, 3, 4, 5, 6, 7, 8, 0xFFFFFFFF)))
            if r() < 0.03:
                do('str_prefixDiffers', rng.choice(world.type_names), rng.choice(world.type_names + [M1.S_MOSQUITO_LARGE]))
        if kind == 'scorpion' and r() < 0.03:
            do('Scorpion_severPart', c, rng.choice((0, 1, 2, 3, 4, 5, 6, 31, 33)))
    if rig.unknown:
        bad['calls'].append('calls to addresses that are neither real nor known stubs: %s'
                            % {hex(a): n for a, n in rig.unknown.items()})
    text = '%s, machine %s, %s' % (cls, 'B' if machine else 'A', 'net game' if net else 'offline')
    count = serial[0]
    DC.report(name + ' calls', len(bad['calls']), count, 'callbacks in order with arguments; ' + text, bad['calls'])
    DC.report(name + ' writes', len(bad['writes']), count, 'bytes stored and their final values', bad['writes'])
    DC.report(name + ' seed', len(bad['seed']), count, 'shared seed and number of draws', bad['seed'])
    DC.report(name + ' result', len(bad['result']), count, 'returned values', bad['result'])
    DC.report(name + ' faults', len(bad['fault']), count,
              'calls that stopped on one side only (%d stopped on both, the same way)' % sum(both.values()),
              bad['fault'])
    return count, draws_by_entry


RUNS = tuple((kind, machine, net) for kind in CLASSES for machine, net in ((0, 1), (1, 1)))


def main(argv):
    args = list(argv)
    elf = None
    while args:
        a = args.pop(0)
        if a == '--quick':
            OPTIONS['quick'] = True
        elif a == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif a == '--ticks':
            OPTIONS['ticks'] = int(args.pop(0), 0)
        elif a == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif a == '-v':
            OPTIONS['verbose'] = True
        elif a == '--trace-first':
            OPTIONS['trace_first'] = True
        elif a == '--fpu':
            OPTIONS['fpu'] = args.pop(0)
        else:
            elf = a
    if elf is None:
        elf = os.path.join(ROOT, 'SLUS_209.73')
    if not os.path.exists(elf):
        print('difftest_monsters_1: %s not found - nothing to compare with (this is not a failure)' % elf)
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != DC.EXPECTED_SHA256:
        print('difftest_monsters_1: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    ticks = max(OPTIONS['ticks'] // 10, 1) if OPTIONS['quick'] else OPTIONS['ticks']
    RC.C.set_fpu(OPTIONS['fpu'])
    started = time.time()
    coverage, counts, draws = [None], {}, {}
    total = 0
    for index, (kind, machine, net) in enumerate(RUNS):
        name = '%s/%s/%s' % (kind, 'B' if machine else 'A', 'net' if net else 'off')
        if OPTIONS['filter'] and OPTIONS['filter'].lower() not in name.lower():
            continue
        n, d = run(elf, name, OPTIONS['seed'] + index, kind, machine, net, ticks, coverage, counts)
        total += n
        for key, value in d.items():
            draws[key] = draws.get(key, 0) + value
    print()
    print('calls compared per entry point / calls with any mismatch / shared-seed draws seen')
    for key in sorted(counts):
        print('  %-32s %7d / %d / %d' % (key, counts[key][0], counts[key][1], draws.get(key, 0)))
    if coverage[0] is not None:
        print('coverage of the original as executed here (basic blocks, instructions):')
        tb = tbt = ti = tit = 0
        for part in BODIES:
            b, bt, i, it = coverage[0].numbers(part)
            if not i:
                continue                                 # a class this invocation did not run
            tb, tbt, ti, tit = tb + b, tbt + bt, ti + i, tit + it
            print('  %-32s blocks %4d of %4d (%5.1f%%)  instructions %4d of %4d (%5.1f%%)'
                  % (part, b, bt, 100.0 * b / bt, i, it, 100.0 * i / it))
            if OPTIONS['verbose'] and b != bt:
                print('      never entered: %s' % ' '.join('%06x' % a for a in coverage[0].missing(part)))
        if tbt:
            print('  %-32s blocks %4d of %4d (%5.1f%%)  instructions %4d of %4d (%5.1f%%)'
                  % ('all', tb, tbt, 100.0 * tb / tbt, ti, tit, 100.0 * ti / tit))
    print('AI state the creature was in on the tick that killed it (state: deaths):')
    for kind in sorted(DEATHS):
        print('  %-12s %s' % (kind, ' '.join('%x:%d' % (state & 0xFFFF, n) for state, n in sorted(DEATHS[kind].items()))))
    if DC.FAULTS:
        print('calls in which the original read or wrote unmapped memory, and the model did too: %s'
              % ', '.join('%d at 0x%x' % (n, pc) for pc, n in sorted(DC.FAULTS.items())))
    print('%d calls compared in %.0f s' % (total, time.time() - started))
    return 0 if all(ok for _name, ok in DC.RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
