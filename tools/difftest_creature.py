#!/usr/bin/env python3
"""difftest_creature.py - compare tools/ref_creature.py with the game's own creature base class.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_creature.py [path/to/SLUS_209.73] [--quick] [--seed N] [--ticks N]
                                     [-k TEXT] [-v] [--trace-first]

    --quick       a tenth of the ticks
    --seed N      seed of the random runs (default 20973); a seed repeats exactly
    --ticks N     ticks per run (default 1500; there are 8 runs)
    -k TEXT       only the runs whose name contains TEXT
    -v            print the first mismatches of every failing property, and the blocks
                  never entered
    --fpu MODEL   ps2 (default), ps2g1, chop or nearest: the adder model of BOTH sides
                  (tools/ee_emu.py and tools/ref_core.py), to see whether agreement depends on it
    --trace-first stop at the first mismatching call and print both sides

What is compared
    The ORIGINAL functions listed in ref_creature.MODELLED are executed by tools/ee_emu.py
    (an instruction interpreter, not a console) on a constructed creature.  One "tick" of
    the test is what a monster class's run function does with the base class, in the
    usual order: damage arrives through virtual slot 2, Creature_processDamage,
    Creature_run, Creature_updateActive, Creature_pickTarget, Creature_stepAnim, one
    movement helper (moveToTarget, moveToDest, moveTo, moveToDirect, moveBy, settle,
    turnToward, fleeFrom, moveToAlly), and now and then the small helpers on their own
    (ENTRIES below lists every entry point).  Every one of those calls is run through
    tools/ref_creature.py first, on a copy-on-write view of the same memory, and for
    every call these must be equal:
      calls    the sequence of calls to everything outside the model, with arguments
      writes   the set of bytes stored outside the stack, and their final values
      seed     the shared seed 0x404464, and that it advanced exactly as many times as the
               model says it drew
      result   the value returned (integer, float pattern or vector)
    Floats are compared as 32-bit patterns: "equal" means identical under the
    interpreter's floating-point model ('ps2', or the one given with --fpu), see
    docs/issues/dynamic-tests.md.  A call in which the original reads or writes unmapped
    memory is counted separately when the model stops the same way, and is a failure when
    only one side stops.

What runs for real and what is a stub
    Real: the functions in ref_creature.MODELLED, the three angle functions, the C
    library's powf and atan2f (0x3a5000-0x3c0000).  Everything else is a recording stub
    whose answer (return value, output arguments, and the fields a real callee would
    change: root motion, the position after a slide, the AI state after a set-state hook,
    handle words ...) comes from World.respond, a seeded script.  The model's callbacks
    are answered by the same script.  A call to an address that is neither real nor a
    known stub is reported as a failure, so nothing is stubbed by accident.

    The creature's virtual table is built per run: "base" runs point every slot the model
    has (ref_creature.BASE_BODIES) at the real base-class body; "hooks" runs point slots
    2, 6, 7, 10, 11, 17, 20, 26, 27 and 37 at stubs, as a subclass that overrides them.

Per-machine inputs, set both ways (machine A / machine B of the run name)
    the activity test    A: activity centres only.  B: g_cullByCamera goes on and off, with
                         the camera focus near or far (FINDINGS D6)
    the boss meter       A: the local alive list is empty or far away.  B: it holds
                         players in range (FINDINGS E11)
    a status counter     A: the driver decrements the first non-zero status counter every
                         tick, as Creature_draw does when the creature is drawn.  B: never
                         (FINDINGS D12)
    the decal option     A: 0.  B: 2 (docs/creatures.md C6)
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
import ref_creature as RC                       # noqa: E402
from ref_creature import EXTERNALS, G_PLAYERS, REC_SIZE, REC_OBJ, M32      # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LIB_LO, LIB_HI = 0x3A5000, 0x3C0000
REAL_OTHER = {0x166630, 0x1666E0, 0x166798}
STUB_BASE = 0x00F00000
STACK_LO, STACK_HI = EE.STACK_LO, EE.STACK_HI
CREATURE_VTABLE = 0x50CC58
HOOKED_SLOTS = (2, 6, 7, 10, 11, 17, 20, 26, 27, 37)

# function bodies for the coverage count: name -> (start, end)
BODIES = {
    'Creature_run': (0x112948, 0x113C48), 'Creature_processDamage': (0x110D30, 0x1124DC),
    'Creature_updateActive': (0x10C0F0, 0x10C234), 'obj_updateActive': (0x14DB08, 0x14DCC8),
    'isNearView': (0x1E77C0, 0x1E78D0), 'Creature_takeDamage': (0x116638, 0x116780),
    'Creature_pickTarget': (0x10DED0, 0x10E2BC), 'Creature_isEnemy': (0x119328, 0x1193FC),
    'Creature_turnToward': (0x10BB08, 0x10BCA4), 'Creature_stepAnim': (0x1162B0, 0x1164BC),
    'Creature_moveBy': (0x113C48, 0x1143E8), 'Creature_moveTo': (0x114510, 0x114D9C),
    'Creature_moveToTarget': (0x1143E8, 0x114510), 'Creature_moveToDest': (0x119F38, 0x11A020),
    'Creature_settle': (0x119E38, 0x119E98), 'Creature_isAwayFromHome': (0x10EED8, 0x10F008),
    'Creature_getWaypoint': (0x11A020, 0x11A090), 'Creature_getNextWaypoint': (0x11A090, 0x11A104),
    'Creature_advanceWaypoint': (0x11A108, 0x11A1E0), 'Creature_clearPath': (0x11A1E0, 0x11A260),
    'Creature_slot7': (0x11A260, 0x11A28C), 'Creature_requestPath': (0x1164C0, 0x116634),
    'Creature_updateSpells': (0x11A868, 0x11A91C), 'Creature_spawnScavenger': (0x1125E0, 0x112948),
    'players_findNearestOnTeam': (0x1124E0, 0x1125DC), 'Creature_pickWanderDest': (0x119618, 0x1196E8),
    'Creature_randomPointNearHome': (0x110B58, 0x110D30), 'creature_findClearHeading': (0x10EAA8, 0x10EED8),
    'Creature_slot6': (0x11A418, 0x11A444), 'Creature_stun': (0x118A58, 0x118AF4),
    'Creature_slot31': (0x118AF8, 0x118B54), 'Creature_slot35': (0x118C50, 0x118C78),
    'Creature_slot36': (0x118C78, 0x118CB0),
    'Creature_moveToDirect': (0x1155E0, 0x115910), 'Creature_computeAvoidanceOffset': (0x108A60, 0x108FD8),
    'Creature_probeThreeMovementRays': (0x108FD8, 0x109280), 'Creature_computeAvoidanceTarget': (0x109280, 0x1097F8),
    'Creature_fleeFrom': (0x115910, 0x115EB4), 'Creature_fleeFromTarget': (0x119F08, 0x119F38),
    'Creature_moveToAlly': (0x119E98, 0x119F08), 'Creature_filterState': (0x10A9C0, 0x10AB14),
}

FAULTS = {}
OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False, 'ticks': 1500, 'trace_first': False,
           'fpu': 'ps2'}
RESULTS = []


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-34s %7d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:6]:
            print('        ' + str(line)[:1200])
    sys.stdout.flush()


def f32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def fl(raw):
    return struct.unpack('<f', struct.pack('<I', raw & M32))[0]


class RealSet:
    """What the interpreter runs for real: the listed functions and the C library."""

    def __init__(self, addresses):
        self.addresses = set(addresses)

    def __contains__(self, target):
        return target in self.addresses or LIB_LO <= target < LIB_HI


class Res:
    def __init__(self, ret=0, f=0, outs=()):
        self.ret, self.f, self.outs = ret, f, list(outs)


class EmuView:
    def __init__(self, emu):
        self.emu, self.mem, self.touched = emu, emu.mem, set()
        self.iter_nodes = []

    def load(self, addr, size):
        return self.mem.load(addr, size)

    def poke(self, addr, size, value):
        self.mem.store(addr, size, value & ((1 << (8 * size)) - 1))
        self.touched.update(range(addr, addr + size))


class ModelView(RC.Memory):
    def __init__(self, under):
        RC.Memory.__init__(self, under)
        self.touched = set()
        self.iter_nodes = []

    def poke(self, addr, size, value):
        RC.Memory.poke(self, addr, size, value)
        self.touched.update(range(addr, addr + size))


def rd(view, addr, size=4, signed=False):
    v = view.load(addr, size)
    if signed and v >> (8 * size - 1):
        v -= 1 << (8 * size)
    return v


# ---------------------------------------------------------------------------------------
# The scripted world
# ---------------------------------------------------------------------------------------
RAY_ANSWERS = [f32(v) for v in (-1.0, -1.0, 0.25, 0.6, 0.999, 1.0, 1.0, 1.5, 3.0)]
ROOTS = [f32(v) for v in (0.0, 0.0, 0.4, -0.3, 1.25, 2.0)]


class World:
    """Builds the fake game in the interpreter's memory and answers every stubbed call."""

    def __init__(self, emu, rng, kind, hooks, machine, net):
        self.emu, self.mem = emu, emu.mem
        self.kind, self.hooks, self.machine, self.net = kind, hooks, machine, net
        self.stub_addr, self.stub_name = {}, {}
        self.crowded = False
        self.build(rng)

    # ---- construction ------------------------------------------------------------------
    def stub_for(self, name):
        if name not in self.stub_addr:
            addr = STUB_BASE + 16 * len(self.stub_addr)
            self.stub_addr[name], self.stub_name[addr] = addr, name
        return self.stub_addr[name]

    def creature_vtable(self, hooked):
        """A copy of the Creature table shape: every slot the model has points at the real
        body unless it is in `hooked`; every other slot is a named stub."""
        table = self.emu.alloc(8 * 48)
        for slot in range(48):
            base = RC.BASE_BODIES.get(slot)
            if base is not None and slot not in hooked:
                self.mem.w32(table + 8 * slot + 4, base[0])
            else:
                self.mem.w32(table + 8 * slot + 4, self.stub_for('Creature.v%d' % slot))
        return table

    def other_vtable(self, cls, slots):
        table = self.emu.alloc(8 * 48)
        for slot in slots:
            self.mem.w32(table + 8 * slot + 4, self.stub_for('%s.v%d' % (cls, slot)))
        return table

    def build(self, rng):
        emu, mem = self.emu, self.mem
        self.vt_creature = self.creature_vtable(HOOKED_SLOTS if self.hooks else ())
        self.vt_base = self.creature_vtable(())
        self.vt_hooked = self.creature_vtable((6, 37))
        self.vt_skill = self.other_vtable('Skill', (11,))
        self.vt_spell = self.other_vtable('Spell', (2,))
        self.model = 0x00C00040
        self.skill = emu.alloc(0x80)
        mem.w32(self.skill + 0x60, self.vt_skill)
        mem.w32(RC.G_SKILL_BURN, self.skill)
        mem.w32(RC.G_SKILL_ONKILL, 0x00C00100)
        self.nodes = {}
        self.C = emu.alloc(0x600)
        self.others = [emu.alloc(0x400) for _ in range(6)]
        self.players = [emu.alloc(0x600) for _ in range(4)]
        self.everything = [self.C] + self.others + self.players
        for obj in self.everything:
            node = emu.alloc(0x20)
            mem.w32(node + 0xC, obj)
            self.nodes[obj] = node
        self.owner_nodes = [emu.alloc(0x20) for _ in range(2)]
        self.spells = [emu.alloc(0x40) for _ in range(3)]
        for sp in self.spells:
            mem.w32(sp + 0x14, self.vt_spell)
        self.spell_nodes = [emu.alloc(0x20) for _ in range(3)]
        self.pool = {0x268: [emu.alloc(0x280) for _ in range(8)], 0xB8: [emu.alloc(0xC0)],
                     0x448: [emu.alloc(0x460)]}
        self.pool_next = 0
        self.points = [emu.alloc(0x40) for _ in range(6)]
        for i, p in enumerate(self.points):
            mem.w16(p + 0x3C, i)
        self.strings = {}
        for name in ('lost', 'found', 'path'):
            s = emu.alloc(16)
            mem.write(s, name.encode() + b'\0')
            self.strings[name] = s
        self.argbuf = emu.alloc(0x100)
        mem.w32(RC.G_SIM_FRAME, 1000 + rng.randrange(5000))
        mem.w8(RC.G_NETWORK_MODE, 1 if self.net else 0)
        mem.w32(RC.G_WORLD, emu.alloc(16))
        mem.wf32(RC.G_LEVEL_MONSTER_LEVEL, rng.choice((1.0, 7.5, 30.0)))
        mem.w32(RC.G_DECAL_DETAIL, 2 if self.machine else 0)
        mem.w32(RC.G_NUM_PLAYERS, 4)
        mem.w32(RC.G_EXCLUDE_MASK, 0x20000)
        for slot in range(4):
            mem.w32(G_PLAYERS + slot * REC_SIZE + REC_OBJ, self.players[slot])
        self.init_creature(rng)
        self.place(rng)

    def init_creature(self, rng):
        mem, c = self.mem, self.C
        for off in range(0, 0x600, 4):
            mem.w32(c + off, 0)
        player = self.kind == 'player'
        mem.w32(c + 0xC, 0x40 if player else 0x20)
        for i, v in enumerate((2000.0, 3000.0, 10.0)):
            mem.wf32(c + 0x10 + 4 * i, v + rng.uniform(-50, 50))
        mem.wf32(c + 0x1C, rng.choice((16.0, 24.0, 30.0)))
        mem.wf32(c + 0x20, rng.choice((72.0, 84.0)))
        mem.w8(c + 0x28, rng.randrange(4))
        mem.w16(c + 0x38, rng.randrange(0x10000))
        mem.wf32(c + 0x3C, mem.f32(c + 0x18))
        mem.w32(c + 0x44, rng.getrandbits(32))
        mem.w32(c + 0x48, self.vt_creature)
        mem.w64(c + 0xA8, (1 if self.kind == 'miniboss' else 0) | 0x40000)
        mem.wf32(c + 0xB0, rng.choice((1.0, 2.5, 6.0)))
        mem.wf32(c + 0xB8, rng.choice((90.0, 150.0)))
        mem.wf32(c + 0xD8, rng.choice((40.0, 250.0, 3000.0)))
        mem.wf32(c + 0xDC, rng.choice((1.0, 1.3)))
        mem.wf32(c + 0xE0, 4.0)
        mem.wf32(c + 0xF8, -1.0)
        mem.wf32(c + 0xFC, -1.0)
        mem.wf32(c + 0x22C, 300.0)
        mem.wf32(c + 0x228, 300.0)
        mem.w8(c + 0x230, rng.randrange(256))
        for i in range(16):
            mem.w32(c + 0x23C + 8 * i, M32)
            mem.w32(c + 0x240 + 8 * i, M32)
        mem.w8(c + 0x310, 0xFF)
        mem.w8(c + 0x5A, 0xFF)
        mem.w16(c + 0x58, 0xFFFF)
        mem.w16(c + 0x3AC, 300)
        mem.w16(c + 0x3AE, 500)
        mem.w16(c + 0x3B0, 0x4000)
        for i in range(3):
            mem.w32(c + 0x3B4 + 4 * i, mem.u32(c + 0x10 + 4 * i))
        mem.wf32(c + 0x3C0, rng.choice((1000.0, 1000.0, 400.0, 150.0)))
        mem.w16(c + 0x3C4, 600)

    def place(self, rng):
        """Other objects and players around the creature (again and again during a run)."""
        mem, c = self.mem, self.C
        cx, cy, cz = (mem.f32(c + 0x10 + 4 * i) for i in range(3))
        for i, obj in enumerate(self.others + self.players):
            is_player = obj in self.players
            near = rng.random() < 0.55
            spread = 60 if near else rng.choice((300, 900, 2500))
            mem.wf32(obj + 0x10, cx + rng.uniform(-spread, spread))
            mem.wf32(obj + 0x14, cy + rng.uniform(-spread, spread))
            mem.wf32(obj + 0x18, cz + rng.choice((0.0, 0.0, 0.0, -20.0, 30.0, 100.0)))
            mem.wf32(obj + 0x1C, rng.choice((8.0, 16.0, 30.0)))
            mem.wf32(obj + 0x20, rng.choice((40.0, 72.0, 3.0, 3.0, 4.5)))
            mem.w16(obj + 0x38, rng.randrange(0x10000))
            if is_player:
                flags = 0x40 | rng.choice((0, 0, 0, 8))
            else:
                flags = rng.choice((0x20, 0x20, 0x20, 0x28, 0x21, 0x0, 0x30, 0x30, 0x230, 0x220, 0x20020, 0xA0))
            mem.w32(obj + 0xC, flags)
            mem.w32(obj + 0x48, rng.choice((self.vt_base, self.vt_base, self.vt_hooked)))
            mem.w64(obj + 0xA8, rng.choice((0, 0, 0, 0x4000000, 0x800, 0x100000000000, 0x40000000000)))
            mem.w8(obj + 0x310, rng.choice((0xFF, 0xFF, 0, 1, 2)) if not is_player else rng.choice((0, 1)))
            mem.w32(obj + 0x4C, rng.choice((0, self.owner_nodes[0], self.owner_nodes[1])))
        for node in self.owner_nodes:
            mem.w32(node + 0xC, rng.choice(self.others + self.players))
        for slot in range(4):
            rec = G_PLAYERS + slot * REC_SIZE
            mem.w8(rec + 0x59, rng.choice((1, 5, 20, 79, 80)))
            mem.w32(rec + 0x50, rng.choice((0, 0, 1, 3)))
            mem.wf32(rec + 0xAC, rng.choice((100.0, 100.0, 0.0)))
            mem.wf32(rec + 0xC0, rng.choice((0.0, 50.0, 119.0)))
            mem.wf32(rec + 0xC4, 120.0)
            mem.w8(rec + 0x4C24, mem.u8(self.players[slot] + 0x310))
        for p in self.points:
            near = rng.random() < 0.4
            spread = 30 if near else 400
            mem.wf32(p, cx + rng.uniform(-spread, spread))
            mem.wf32(p + 4, cy + rng.uniform(-spread, spread))
            mem.wf32(p + 8, cz)

    # ---- answers ------------------------------------------------------------------------
    def respond(self, name, args, view, rng):
        handler = getattr(self, 'on_' + name.replace('.', '_'), None)
        if handler is not None:
            return handler(args, view, rng)
        return Res()

    def on_handle_clear(self, args, view, rng):
        if args[0] != 'stack':
            view.poke(args[0], 4, 0)
        return Res()

    def on_handle_link(self, args, view, rng):
        head, obj = args[0], args[2]
        if head == 'stack' or obj not in self.nodes:
            return Res()
        if RC.G_RUN_LIST_ACTIVE <= head < RC.G_RUN_LISTS_60 + 0x100:
            view.poke(args[1], 4, self.nodes[obj])      # a run list: the object's own node pointer at +4
        else:
            view.poke(head, 4, self.nodes[obj])
        return Res()

    def on_iter_begin(self, args, view, rng):
        count = rng.choice((0, 0, 1, 2, 3))
        view.iter_nodes = []
        for node, spell in list(zip(self.spell_nodes, self.spells))[:count]:
            view.poke(node + 0xC, 4, spell)
            view.iter_nodes.append(node)
        return self.on_iter_next(args, view, rng)

    def on_iter_next(self, args, view, rng):
        return Res(view.iter_nodes.pop(0) if view.iter_nodes else 0)

    def on_obj_getPropStr(self, args, view, rng):
        if args[1] == RC.S_PATHNAME:
            return Res(self.strings['path'] if rng.random() < 0.95 else 0)
        return Res(self.strings['lost'] if rng.random() < 0.6 else 0)

    def on_obj_getPropInt(self, args, view, rng):
        return Res(1 if rng.random() < 0.1 else 0)

    def on_paths_findByName(self, args, view, rng):
        return Res(0x00C00200)

    def on_pointList_snapToNearest(self, args, view, rng):
        return Res(rng.randrange(len(self.points) - 1))

    def on_pointList_getPoint(self, args, view, rng):
        index = args[1]
        if index >= len(self.points) or rng.random() < 0.08:
            return Res(self.points[0] if index >= len(self.points) and rng.random() < 0.8 else 0)
        return Res(self.points[index])

    def on_players_anyWithinRadius(self, args, view, rng):
        return Res(1 if self.crowded or rng.random() < 0.7 else 0)

    def on_net_objOrGhost(self, args, view, rng):
        return Res(args[0] if rng.random() < 0.8 else self.others[0])

    def on_player_speedScale(self, args, view, rng):
        return Res(f=rng.choice((f32(1.0), f32(1.25), f32(0.8))))

    def on_player_getSkillRank(self, args, view, rng):
        return Res(rng.randrange(0, 4))

    def on_SkillLifeTap_getStat0Fraction(self, args, view, rng):
        return Res(f=rng.choice((0, f32(0.3), f32(1.0))))

    def on_anim_advance(self, args, view, rng):
        state, _sound, root, yaw = args[:4]
        view.poke(root, 4, rng.choice(ROOTS))
        view.poke(root + 4, 4, rng.choice(ROOTS))
        view.poke(yaw, 2, rng.choice((0, 0, 0, 300, 0xFF38, 4000)))
        if rng.random() < 0.3:
            view.poke(state + 6, 2, rd(view, state + 6, 2) ^ 0x80)
        return Res(0 if rng.random() < 0.7 else rng.choice((1, 2, 4, 0x80, 3)))

    def on_model_getBounds(self, args, view, rng):
        low = rng.choice((0, -4, 10))
        top = rng.choice((20, 30, 40, 90, 5))
        return Res(outs=[rng.randrange(-20, 0) & M32, rng.randrange(-20, 0) & M32, low & M32,
                         rng.randrange(1, 20), rng.randrange(1, 20), top])

    def on_model_getAttachPoint(self, args, view, rng):
        pos = args[1]
        return Res(outs=[(f32(fl(pos[0]) + rng.uniform(-9, 9)), f32(fl(pos[1]) + rng.uniform(-9, 9)),
                          f32(fl(pos[2]) + rng.uniform(20, 60)))])

    def on_SpellDrowsy_typeinfo(self, args, view, rng):
        return Res(0x909200)

    def on_creature_findSpellByType(self, args, view, rng):
        return Res(self.spells[0] if rng.random() < 0.5 else 0)

    def on_SpellDrowsy_getStat3Fraction(self, args, view, rng):
        return Res(f=rng.choice((f32(0.5), f32(0.7))))

    def on_creature_bossRank(self, args, view, rng):
        c = args[0]
        if not rd(view, c + 0xC) & 0x20:
            return Res(0)
        if rd(view, c + 0xA8) & 1:
            return Res(2 if rng.random() < 0.3 else 1)
        return Res(0)

    def on_damage_apply(self, args, view, rng):
        target = args[0]
        amount = f32(rng.choice((1.0, 4.0, 25.0)))
        view.poke(target + 0x228, 4, RC.C.sub(rd(view, target + 0x228), amount))
        view.poke(target + 0xC8, 4, RC.C.add(rd(view, target + 0xC8), amount))
        view.poke(target + 0x2DC, 4, rd(view, target + 0x2DC) | (args[5] & 0x00FFFFFF))
        return Res(1)

    def on_pool_new(self, args, view, rng):
        blocks = self.pool.get(args[0])
        if blocks is None or rng.random() < 0.06:
            return Res(0)
        return Res(rng.choice(blocks))

    def on_GutChunk_ctor(self, args, view, rng):
        view.poke(args[0] + 0xFC, 4, f32(rng.uniform(-40, 40)))
        view.poke(args[0] + 0x100, 4, f32(rng.uniform(-40, 40)))
        return Res()

    def on_Critter_ctor(self, args, view, rng):
        block, pos = args[0], args[2]
        for i in range(3):
            view.poke(block + 0x10 + 4 * i, 4, pos[i])
        view.poke(block + 0x38, 2, args[3] & 0xFFFF)
        return Res()

    def on_libc_sprintf(self, args, view, rng):
        return Res(outs=[b'name%d' % rng.randrange(3)])

    def on_res_find(self, args, view, rng):
        return Res(0x00D00000 + rng.randrange(4) * 0x10)

    def on_terrain_raycast(self, args, view, rng):
        return Res(f=rng.choice(RAY_ANSWERS))

    def on_world_raycast(self, args, view, rng):
        return Res(f=rng.choice(RAY_ANSWERS), outs=[rng.choice([0, 0] + self.others[:3])])

    def on_terrain_heightBelow(self, args, view, rng):
        z = fl(args[1][2])
        return Res(f=f32(z + rng.choice((0.0, 0.0, -0.005, -0.5, -3.0, -40.0, 2.0, 11.0, 13.0, 60.0))))

    def on_world_collectObjectsInBox(self, args, view, rng):
        cap = args[2]
        pool = self.others + self.players + [self.C]
        if cap == 0x10:
            count = rng.choice((0, 0, 1, 2, 3, 6))
        else:
            count = rng.choice((0, 1, 2, 4, 7, 11))
        chosen = [rng.choice(pool) for _ in range(count)]
        return Res(outs=[chosen])

    def on_world_slideMove(self, args, view, rng):
        pos, delta = args[0], args[1]
        scale = rng.choice((1.0, 1.0, 1.0, 0.5, 0.0))
        for i in range(2):
            view.poke(pos + 4 * i, 4, f32(fl(rd(view, pos + 4 * i)) + fl(delta[i]) * scale))
        hit = 1 if scale != 1.0 or rng.random() < 0.1 else 0
        return Res(hit, outs=[(f32(rng.uniform(-1, 1)), f32(rng.uniform(-1, 1)), 0)])

    def on_world_findFreeSpot(self, args, view, rng):
        pos = args[0]
        spot = (f32(fl(pos[0]) + rng.uniform(-60, 60)), f32(fl(pos[1]) + rng.uniform(-60, 60)), pos[2])
        return Res(outs=[spot, 1 if rng.random() < 0.7 else 0])

    def on_water_test(self, args, view, rng):
        return Res(1 if rng.random() < 0.4 else 0)

    def on_water_disturb(self, args, view, rng):
        return Res(1 if rng.random() < 0.7 else 0)

    # virtual hooks of a subclass
    def on_Creature_v27(self, args, view, rng):
        this, state = args[0], args[1] & 0xFFFF
        view.poke(this + 0x232, 2, state)
        if state == 0:
            view.poke(this + 0x234, 4, 0)       # what Creature_filterState does for a result of 0
        if state == 0x14:
            for off in (0x314, 0x318, 0x31A, 0x31C):
                view.poke(this + off, 2, 0)
        return Res()

    def on_Creature_v20(self, args, view, rng):
        other = args[1]
        if other == args[0] or rd(view, other + 0xC) & 8:
            return Res(0)
        return Res(rng.choice((0, 1, 1, 1, 4)))

    def on_Creature_v26(self, args, view, rng):
        this = args[0]
        turn = rng.choice((0, 300, -700, 9000, -15000, 16001, -16000, 32000, -32768))
        view.poke(this + 0x38, 2, (rd(view, this + 0x38, 2) + turn // 8) & 0xFFFF)
        return Res(turn & M32)

    def on_Creature_v37(self, args, view, rng):
        return Res(rd(view, args[0] + 0x310, 1, True) & M32)

    def on_Creature_v2(self, args, view, rng):
        return Res()

    def on_Skill_v11(self, args, view, rng):
        return Res(rng.choice((10, 40, 133)))


# ---------------------------------------------------------------------------------------
# The rig: stubs on the interpreter side, callbacks on the model side
# ---------------------------------------------------------------------------------------
def is_stack(v):
    return STACK_LO <= v < STACK_HI


# entry points: key -> (address, argument kinds, result kind, model method)
#   argument kinds: c the creature, i integer, v vector (passed by pointer), f float
#   pattern (f12..), o output vector (pointer to scratch; compared with the model's result),
#   q a 32-bit word passed by pointer and rewritten (the model returns (result, word))
ENTRIES = {
    'run': (0x112948, 'ci', 'i', 'run'),
    'processDamage': (0x110D30, 'ci', 'n', 'process_damage'),
    'updateActive': (0x10C0F0, 'c', 'i', 'update_active'),
    'takeDamage': (0x116638, 'ciif', 'n', 'take_damage'),
    'pickTarget': (0x10DED0, 'ci', 'n', 'pick_target'),
    'isEnemy': (0x119328, 'ci', 'i', 'is_enemy'),
    'turnToward': (0x10BB08, 'civ', 'i', 'turn_toward'),
    'stepAnim': (0x1162B0, 'cf', 'i', 'step_anim'),
    'moveBy': (0x113C48, 'cv', 'i', 'move_by'),
    'moveTo': (0x114510, 'cv', 'i', 'move_to'),
    'moveToTarget': (0x1143E8, 'c', 'i', 'move_to_target'),
    'moveToDest': (0x119F38, 'c', 'i', 'move_to_dest'),
    'settle': (0x119E38, 'c', 'n', 'settle'),
    'isAwayFromHome': (0x10EED8, 'c', 'i', 'is_away_from_home'),
    'pickWanderDest': (0x119618, 'c', 'n', 'pick_wander_dest'),
    'randomPointNearHome': (0x110B58, 'oci', 'o', 'random_point_near_home'),
    'findClearHeading': (0x10EAA8, 'cviif', 'i', 'find_clear_heading'),
    'spawnScavenger': (0x1125E0, 'c', 'n', 'spawn_scavenger'),
    'slot7': (0x11A260, 'ci', 'n', 'slot7_path_done'),
    'stun': (0x118A58, 'cii', 'n', 'slot30_stun'),
    'slot31': (0x118AF8, 'ci', 'n', 'slot31_no_target'),
    'slot35': (0x118C50, 'c', 'i', 'slot35'),
    'slot36': (0x118C78, 'c', 'i', 'slot36'),
    'slot6': (0x11A418, 'ci', 'n', 'slot6_touched'),
    'clearPath': (0x11A1E0, 'c', 'n', 'clear_path'),
    'requestPath': (0x1164C0, 'cviff', 'n', 'request_path'),
    'findNearestOnTeam': (0x1124E0, 'vif', 'i', 'find_nearest_on_team'),
    'isNearView': (0x1E77C0, 'if', 'i', 'is_near_view'),
    'moveToDirect': (0x1155E0, 'cv', 'i', 'move_to_direct'),
    'avoidanceOffset': (0x108A60, 'ocif', 'o', 'compute_avoidance_offset'),
    'avoidanceTarget': (0x109280, 'ocv', 'o', 'compute_avoidance_target'),
    'probeThreeRays': (0x108FD8, 'cvi', 'f', 'probe_three_rays'),
    'fleeFrom': (0x115910, 'cii', 'n', 'flee_from'),
    'fleeFromTarget': (0x119F08, 'ci', 'n', 'flee_from_target'),
    'moveToAlly': (0x119E98, 'c', 'i', 'move_to_ally'),
    'filterState': (0x10A9C0, 'cq', 'q', 'filter_state'),
}


class Rig:
    def __init__(self, elf, seed, kind, hooks, machine, net):
        self.rng = random.Random(seed)
        emu = self.emu = EE(elf, fpu_model=OPTIONS['fpu'])
        self.world = World(emu, self.rng, kind, hooks, machine, net)
        real = set(REAL_OTHER) | set(RC.MODELLED.values())
        emu.follow = RealSet(real)
        self.real = emu.follow
        self.calls, self.buffers, self.unknown = [], {}, {}
        self.eview = EmuView(emu)
        self.script_rng = None
        self.names = {}
        for name, ext in EXTERNALS.items():
            addr = self.world.stub_for(name) if ext.addr == 0 else ext.addr
            self.names[addr] = name
            emu.stub(addr, function=self.make_stub(name, ext), name=name)
        for addr, name in self.world.stub_name.items():       # slots nobody modelled: plain named stubs
            if addr not in self.names:
                self.names[addr] = name
                emu.stub(addr, function=self.make_stub(name, RC.Ext(0, 'p', 0, 'n')), name=name)
        # tools/ee_emu.py logs an unaligned sdl / sdr / swl / swr as a store of the whole
        # aligned word, which over-reports the bytes written.  Record the real effective
        # address of every such instruction in the functions under test (see stored_bytes).
        self.partial, self.partial_ops = [], {}
        for start, end in BODIES.values():
            for pc in range(start, end, 4):
                w = emu.mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))

    def partial_hook(self, pc, base, offset):
        def note(emu):
            ea = (emu.r[base] + offset) & M32
            if not is_stack(ea):
                self.partial.append((pc, ea))
        return note

    def stored_bytes(self, lo, hi):
        """The set of bytes the original stored outside the stack and outside [lo, hi),
        exact for the partial-word stores."""
        out, partial = set(), list(self.partial)
        for pc, addr, size, _value in self.emu.writes:
            op = self.partial_ops.get(pc)
            if op is not None:
                ppc, ea = partial.pop(0)
                assert ppc == pc
                if op == 0x2C:
                    first, last = ea & ~7, ea
                elif op == 0x2D:
                    first, last = ea, ea | 7
                elif op == 0x2A:
                    first, last = ea & ~3, ea
                else:
                    first, last = ea, ea | 3
            else:
                first, last = addr, addr + size - 1
            if not lo <= first < hi:
                out.update(range(first, last + 1))
        return out

    # ---- interpreter side -----------------------------------------------------------------
    def decode(self, name, ext, emu):
        mem, canon, outs = emu.mem, [], []
        for i, kind in enumerate(ext.ints):
            v = emu.r[4 + i] & M32
            if kind == 'i':
                canon.append(v)
            elif kind == 'p':
                canon.append('stack' if is_stack(v) else v)
            elif kind == 'v':
                canon.append(tuple(mem.u32(v + 4 * j) for j in range(3)))
            elif kind == 's':
                canon.append(('buf', self.buffers.get(v, b'?')))
            elif kind == 'l':
                items = []
                while mem.u32(v + 4 * len(items)):
                    items.append(mem.u32(v + 4 * len(items)))
                canon.append(tuple(items))
            elif kind == 'e':
                canon.append(self.decode_elements(mem, v))
            elif kind in 'OW':
                canon.append(1 if v else 0)
                outs.append((kind, v))
            elif kind in 'onwb':
                outs.append((kind, v))
        for j in range(ext.floats):
            canon.append(emu.f[12 + j])
        return canon, outs

    @staticmethod
    def decode_elements(mem, v):
        """The record Creature_run builds on its stack for a burn tick: four eight-byte
        entries from +0x24 (id, min, max, 0), two bytes of 0xff at +0x20 and eight zero
        halfwords from +0x10.  Only what the code initialises is looked at: +0..+0xf,
        +0x22, +0x23 and the value fields of entries 1-3 are never written."""
        if v == 0:
            return 0
        ok = all(mem.u16(v + 0x10 + 2 * k) == 0 for k in range(8)) and mem.u8(v + 0x20) == 0xFF \
            and mem.u8(v + 0x21) == 0xFF and all(mem.u16(v + 0x24 + 8 * k) == 0xFFFF for k in (1, 2, 3)) \
            and mem.u16(v + 0x24) == 0x15 and mem.u16(v + 0x2A) == 0
        if not ok:
            return ('elem?', bytes(mem.read(v + 0x10, 0x34)).hex())
        return ('elem', mem.u16(v + 0x26), mem.u16(v + 0x28))

    def make_stub(self, name, ext):
        def stub(emu):
            mem = emu.mem
            if name == 'libc_sprintf':
                buf, fmt = emu.r[4] & M32, emu.r[5] & M32
                text = mem.cstr(fmt)
                text = text.encode() if isinstance(text, str) else text
                args = (fmt, emu.r[6] & M32 if b'%' in text else None)
                self.calls.append((name, args))
                token = self.world.respond(name, args, self.eview, self.script_rng).outs[0]
                mem.write(buf, token + b'\0')
                self.buffers[buf] = token
                return 0
            canon, outs = self.decode(name, ext, emu)
            args = tuple(canon)
            self.calls.append((name, args))
            res = self.world.respond(name, args, self.eview, self.script_rng)
            given = list(res.outs)
            for kind, ptr in outs:
                value = given.pop(0) if given else ((0, 0, 0) if kind in 'oO' else ([] if kind == 'n' else 0))
                if kind in 'oO':
                    if ptr:
                        for j in range(3):
                            mem.w32(ptr + 4 * j, value[j])
                elif kind in 'wW':
                    if ptr:
                        mem.w32(ptr, value)
                elif kind == 'b':
                    mem.w8(ptr, value)
                elif kind == 'n':
                    for j, obj in enumerate(value):
                        mem.w32(ptr + 4 * j, obj)
                    mem.w32(ptr + 4 * len(value), 0)
            if name in ('iter_begin', 'iter_next'):
                mem.w32((emu.r[4] & M32) + 4, res.ret)
            if name == 'pointList_snapToNearest':
                mem.w32((emu.r[4] & M32) + 0x20, res.ret)
            if ext.ret == 'f':
                emu.f[0] = res.f & M32
            return ee_emu.s32(res.ret)          # a 32-bit result, sign-extended as the callee would leave it
        return stub

    # ---- model side -------------------------------------------------------------------------
    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                return RC.shape_result(name, args, res.ret & M32, res.f & M32, res.outs)
            return answer

    # ---- one call, both sides ---------------------------------------------------------------
    def compare(self, key, args, call_seed, trace=None):
        """Run one entry point through the model and through the original; returns a dict
        describing every difference (empty lists = equal)."""
        addr, kinds, ret_kind, method = ENTRIES[key]
        emu, world = self.emu, self.world
        mem = emu.mem
        seed_before = mem.u32(RC.G_RAND_SEED)
        # the model first, on a copy-on-write view
        mview = ModelView(mem)
        model = RC.Model(mview, Rig.Callbacks(self, mview, random.Random(call_seed)))
        margs = [a for a, k in zip(args, kinds) if k != 'o']
        model_error = None
        try:
            mret = getattr(model, method)(*margs)
        except EmuError as exc:
            model_error, mret = exc, None
        # the original
        self.calls, self.buffers = [], {}
        self.eview.touched = set()
        self.script_rng = random.Random(call_seed)
        emu.reset_log()
        self.partial = []
        emu.trace = [] if trace is not None else None
        emu.r[29] = emu.stack_hi - 0x100
        ints, nfloat, scratch, out_ptr = [], 0, world.argbuf, None
        for a, k in zip(args, kinds):
            if k in 'ci':
                ints.append(a & M32)
            elif k == 'v':
                for j in range(3):
                    mem.w32(scratch + 4 * j, a[j])
                ints.append(scratch)
                scratch += 0x10
            elif k == 'o':
                out_ptr = scratch
                ints.append(scratch)
                scratch += 0x10
            elif k == 'q':
                out_ptr = scratch
                mem.w32(scratch, a)
                ints.append(scratch)
                scratch += 0x10
            elif k == 'f':
                emu.f[12 + nfloat] = a & M32
                nfloat += 1
        emu_error = None
        try:
            eret = emu.call(addr, *ints, max_steps=2000000)
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
            out['calls'] = describe_calls(model.calls, self.calls)
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
        if ret_kind == 'i':
            if (eret & M32) != ((mret or 0) & M32):
                out['result'] = 'original %08x model %08x' % (eret & M32, (mret or 0) & M32)
        elif ret_kind == 'f':
            if emu.f[0] & M32 != mret & M32:
                out['result'] = 'original %08x model %08x' % (emu.f[0] & M32, mret & M32)
        elif ret_kind == 'q':
            got = (eret & M32, mem.u32(out_ptr))
            if got != (mret[0] & M32, mret[1] & M32):
                out['result'] = 'original %s model %s' % (got, mret)
        elif ret_kind == 'o':
            got = tuple(mem.u32(out_ptr + 4 * j) for j in range(3))
            if got != tuple(mret):
                out['result'] = 'original %s model %s' % (got, mret)
        out['ret'] = eret
        return out


def describe_calls(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return 'call %d: model %s / original %s' % (i, fmt_call(x), fmt_call(y))
    if len(a) != len(b):
        longer = a if len(a) > len(b) else b
        return 'call %d: only the %s makes %s' % (min(len(a), len(b)), 'model' if len(a) > len(b) else 'original',
                                                  fmt_call(longer[min(len(a), len(b))]))
    return 'equal'


def fmt_call(c):
    name, args = c
    parts = []
    for a in args:
        if isinstance(a, int):
            parts.append('%x' % a)
        elif isinstance(a, tuple) and a and all(isinstance(x, int) for x in a):
            parts.append('(' + ' '.join('%x' % x for x in a) + ')')
        else:
            parts.append(repr(a))
    return '%s(%s)' % (name, ', '.join(parts))


def where(world, addr):
    if world.C <= addr < world.C + 0x600:
        return 'creature+%x' % (addr - world.C)
    for i, obj in enumerate(world.others):
        if obj <= addr < obj + 0x400:
            return 'other%d+%x' % (i, addr - obj)
    for i, obj in enumerate(world.players):
        if obj <= addr < obj + 0x600:
            return 'playerobj%d+%x' % (i, addr - obj)
    if G_PLAYERS <= addr < G_PLAYERS + 4 * REC_SIZE:
        return 'record%d+%x' % ((addr - G_PLAYERS) // REC_SIZE, (addr - G_PLAYERS) % REC_SIZE)
    return '%x' % addr


# ---------------------------------------------------------------------------------------
# Static shape of the functions, for coverage
# ---------------------------------------------------------------------------------------
def analyse(mem, start, end):
    """Basic-block leaders and conditional branch sites of one function body."""
    leaders, sites = {start}, {}
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
            leaders.add(((pc & 0xF0000000) | ((w & 0x3FFFFFF) << 2)))
            continue
        if cond is None:
            continue
        leaders.add(target)
        if cond:
            leaders.add(pc + 8)                 # the fall-through path; after an unconditional
            sites[pc] = target                  # branch the next word is padding unless targeted
    return {a for a in leaders if start <= a < end}, sites


class Coverage:
    """Which basic blocks and instructions of the functions that run for real were
    executed (from the interpreter's trace)."""

    def __init__(self, mem):
        self.parts = {name: (start, end) + analyse(mem, start, end) for name, (start, end) in BODIES.items()}
        self.pcs = set()

    def numbers(self, name):
        start, end, leaders, _sites = self.parts[name]
        inside = {pc for pc in self.pcs if start <= pc < end}
        return len(leaders & inside), len(leaders), len(inside), (end - start) // 4

    def missing(self, name):
        _start, _end, leaders, _sites = self.parts[name]
        return sorted(a for a in leaders if a not in self.pcs)


# ---------------------------------------------------------------------------------------
# The driver: what the rest of the game would do to the creature between calls
# ---------------------------------------------------------------------------------------
DAMAGE_FLAGS = (0, 1, 4, 8, 0x10, 0x20, 0x800, 0x2000, 0x40000, 0x80000, 0x100000, 0x200000, 0x400000,
                0x2000000, 0x4000000, 0x10000000, 0x180000, 0x40801, 0x80808, 0x100804, 0x200801, 0x40801)
BODY_FLAGS = (0x1000, 0x2000, 0x4000, 0x8000, 0x10000, 0x20000, 0x40000, 0x40000, 0x40000, 0)
SECONDS = [f32(v) for v in (0.01, 0.05, 0.5, 1.5, 4.0, 70.0)]


class Driver:
    def __init__(self, rig):
        self.rig, self.world, self.rng = rig, rig.world, rig.rng
        self.mem = rig.emu.mem
        self.dead_ticks = 0
        self.mode = 'target'
        self.mode_left = 0
        self.camera_on = 0
        self.follow_left = 0
        self.missing = None

    def cflag(self, mask, on):
        c = self.world.C
        cf = self.mem.u64(c + 0xA8)
        self.mem.w64(c + 0xA8, (cf | mask) if on else (cf & ~mask & RC.M64))

    def between(self):
        """Advance the frame and let the scripted rest of the game act."""
        rng, mem, world = self.rng, self.mem, self.world
        c = world.C
        mem.w32(RC.G_SIM_FRAME, mem.u32(RC.G_SIM_FRAME) + 1)
        r = rng.random
        if r() < 0.02:
            world.place(rng)
        if r() < 0.05:
            world.crowded = r() < 0.3
        # activity: centres for everybody; the camera only on machine B
        cx, cy, cz = (mem.f32(c + 0x10 + 4 * i) for i in range(3))
        if r() < 0.05:
            count = rng.choice((0, 1, 2, 4))
            mem.w8(RC.G_ACTIVITY_COUNT, count)
            for i in range(4):
                far = rng.choice((0.0, 0.0, 250.0, 590.0, 5000.0))
                mem.wf32(RC.G_ACTIVITY_CENTERS + 12 * i, cx + far)
                mem.wf32(RC.G_ACTIVITY_CENTERS + 12 * i + 4, cy + rng.choice((0.0, 100.0)))
                mem.wf32(RC.G_ACTIVITY_CENTERS + 12 * i + 8, cz)
        if world.machine and r() < 0.03:
            self.camera_on = 1 - self.camera_on
            mem.w8(RC.G_CULL_BY_CAMERA, self.camera_on)
        if r() < 0.05:
            far = rng.choice((0.0, 300.0, 900.0, 5000.0))
            mem.wf32(RC.G_CAMERA_FOCUS, cx + far)
            mem.wf32(RC.G_CAMERA_FOCUS + 4, cy - far / 3)
            mem.wf32(RC.G_CAMERA_FOCUS + 8, cz)
        # the local alive list (boss meter)
        if r() < 0.05:
            if world.machine:
                slots = [s for s in range(4) if r() < 0.6]
            else:
                slots = [s for s in range(4) if r() < 0.15 and
                         abs(mem.f32(world.players[s] + 0x10) - cx) > 2000]
            mem.w32(RC.G_LOCAL_ALIVE_COUNT, len(slots))
            for i, s in enumerate(slots):
                mem.w32(RC.G_LOCAL_ALIVE_LIST + 4 * i, s)
        if r() < 0.01:
            mem.w32(RC.G_NUM_PLAYERS, rng.choice((1, 1, 2, 3, 4, 4)))
        if r() < 0.01:
            mem.w32(RC.G_LEVEL_FLAGS, rng.choice((0, 0, 0, 0x100)))
        if r() < 0.02:
            mem.w8(RC.G_CUTSCENE_ACTIVE, rng.choice((0, 0, 0, 1)))
        if r() < 0.02:
            mem.w32(RC.G_SCAVENGER_KIND, rng.choice((0, 1, 2, 2, 3)))
        # a slot whose player object is missing for a while
        if self.missing is not None and r() < 0.15:
            mem.w32(G_PLAYERS + self.missing * REC_SIZE + REC_OBJ, world.players[self.missing])
            self.missing = None
        elif self.missing is None and r() < 0.015:
            self.missing = rng.randrange(4)
            mem.w32(G_PLAYERS + self.missing * REC_SIZE + REC_OBJ, 0)
        if r() < 0.02:
            mem.w32(RC.G_EXCLUDE_MASK, rng.choice((0x20000, 0x200000, 0)))
        if r() < 0.01:
            mem.w32(0x4F711C, rng.choice((0, 0, 1)))
        if r() < 0.02:
            mem.w32(0x4F7120, rng.choice((0, 0, 0, 1)))
            mem.w32(0x503890, rng.choice((0, 1)))
            mem.w32(0x503894, rng.choice((0, 1)))
        if r() < 0.02:
            mem.wf32(RC.G_FOLLOW_TELEPORT_DIST, rng.choice((500.0, 120.0)))
        # a status counter drawn or not drawn: Creature_draw's decrement
        if not world.machine and not mem.u8(c + 0x231) & 8:
            for i in range(16):
                v = mem.s32(c + 0x36C + 4 * i)
                if v != 0:
                    if i != 12:
                        mem.w32(c + 0x36C + 4 * i, v - 1)
                    break
        # the creature itself
        state = mem.s16(c + 0x232)
        if state == 0x14:
            self.dead_ticks += 1
            if r() < 0.3:
                mem.w16(c + 0x11A, mem.u16(c + 0x11A) | 0x80)
            if r() < 0.1:
                mem.w32(c + 0x238, rng.choice((0, world.nodes[world.others[0]], world.nodes[world.others[1]])))
            if self.dead_ticks > rng.choice((6, 20, 60)):
                self.respawn()
            return
        for off in (0x316, 0x318, 0x31A, 0x31C):
            if r() < 0.012:
                mem.w16(c + off, rng.choice((1, 2, 30, 200)))
        if r() < 0.012:
            mem.w16(c + 0x314, rng.choice((1, 20, 0xFFFF, 0)))
        if r() < 0.02:
            mem.w16(c + 0x312, rng.choice((0, 0, 1, 3, 400, 0xFFFF)))
        if r() < 0.01:
            mem.w8(c + 0x310, rng.choice((0xFF, 0, 1)))
        for off in (0x340, 0x344, 0x348, 0x34C, 0x350, 0x354):
            if r() < 0.012:
                mem.w32(c + off, rng.choice(SECONDS))
        if r() < 0.02:
            for off in (0x358, 0x35A, 0x35C, 0x35E):
                mem.w16(c + off, rng.choice((0, 10, 35, 400)))
        if r() < 0.012:
            which = rng.choice((7, 7, 7, 2, 12, 13))
            mem.w32(c + 0x36C + 4 * which, rng.choice((1, 20, 30, 31, 300, 0xFFFFFFFF, 0x12C)))
            mem.w32(c + 0xF0, mem.u32(RC.G_SIM_FRAME) - rng.choice((0, 0, 0, 5, 40, -97, -200)))
        if r() < 0.01:
            mem.w8(c + 0x2FC, rng.choice((0, 0, 1, 10, 29, 30, 31, 45, 59, 60, 61, 200)))
        if r() < 0.03:
            mem.wf32(c + 0x60, rng.choice((0.0, 0.0, 0.25, 0.9, 1.0)))
            mem.wf32(c + 0x6C, rng.choice((0.0, 0.0, 0.25, 0.9, 1.0)))
        if r() < 0.02:
            for k in range(8):
                mem.w16(c + 0x90 + 2 * k, rng.choice((0, 0, 1, 2, 3, 0x40, 0xFFFF, 0xFFFE, 0xFFC0)))
        if r() < 0.02:
            self.cflag(0x7F000, False)
            self.cflag(rng.choice(BODY_FLAGS), True)
        for mask, p_on, p_off in ((0x20000000, 0.005, 0.03), (0x400, 0.01, 0.02), (0x100000, 0.005, 0.03),
                                  (0x2000000, 0.01, 0.03), (0x100000000, 0.004, 0.03),
                                  (0x1000000000000, 0.003, 0.08), (0x4000000, 0.003, 0.1),
                                  (0x2000000000000, 0.01, 0.03), (0x800000000000000, 0.02, 0.02),
                                  (0x1000000, 0.01, 0.01)):
            if r() < p_on:
                self.cflag(mask, True)
            elif r() < p_off:
                self.cflag(mask, False)
        if r() < 0.01:
            mem.w8(c + 0x231, rng.choice((0, 0, 0, 0, 1, 8, 0x10)))
        elif mem.u8(c + 0x231) and r() < 0.2:
            mem.w8(c + 0x231, 0)
        if world.kind == 'player' and r() < 0.02:
            flags = mem.u32(c + 0xC) & ~0x4020000
            mem.w32(c + 0xC, flags | rng.choice((0, 0, 0x20000, 0x4000000)))
        if r() < 0.01:
            mem.wf32(c + 0x3C0, rng.choice((1000.0, 1000.0, 400.0, 150.0, 70.0)))
        if r() < 0.01:
            mem.wf32(c + 0xB8, rng.choice((0.0, 0.005, 90.0, 150.0)))
        if r() < 0.01:                                      # object flag bits the follow scripts test (C12)
            mem.w32(c + 0xC, mem.u32(c + 0xC) ^ rng.choice((0x400000, 0x800000)))
        elif r() < 0.05:
            mem.w32(c + 0xC, mem.u32(c + 0xC) & ~0xC00000)
        if r() < 0.01:
            mem.w32(c + 0x2C4, rng.choice((0, 3, 4, 9)))
        if r() < 0.02:                                      # object flags the collision step tests
            mem.w32(c + 0xC, mem.u32(c + 0xC) ^ rng.choice((0x10, 0x400, 0x1)))
        elif r() < 0.06:
            mem.w32(c + 0xC, mem.u32(c + 0xC) & ~0x411)
        if r() < 0.02:
            for i in range(2):
                mem.wf32(c + 0x3B4 + 4 * i, mem.f32(c + 0x10 + 4 * i) + rng.choice((0.0, 30.0, 200.0, 900.0)))
        if r() < 0.02:                                      # a destination within reach
            for i in range(3):
                mem.wf32(c + 0x104 + 4 * i, mem.f32(c + 0x10 + 4 * i) + rng.choice((0.0, 3.0, -6.0)))
        # followers
        if self.follow_left > 0:
            self.follow_left -= 1
            if self.follow_left == 0:
                self.cflag(0x8C00000, False)
                mem.w16(c + 0x3C4, 600)
        elif r() < 0.012:
            self.follow_left = rng.choice((30, 80, 200))
            if r() < 0.45:
                self.cflag(0x8000000, True)
                mem.w16(c + 0x58, rng.choice((0xFFFF, 0, 2)))
            else:
                self.cflag(rng.choice((0x400000, 0x800000)), True)
                mem.w16(c + 0x312, rng.choice((0xFFFF, 0xFFFF, 500)))
                mem.w8(c + 0x5A, rng.choice((0xFF, 0, 1, 3, 7)))
        # the path search answers
        if mem.s32(c + 0x2BC) == 16 and r() < 0.5:
            n = rng.choice((0, 0, 1, 3, 8, 16))
            px, py = cx, cy
            for i in range(16):
                if i < n:
                    px += rng.choice((24, 48, -24, 0))
                    py += rng.choice((24, 48, -24))
                    mem.w32(c + 0x23C + 8 * i, int(px) & M32)
                    mem.w32(c + 0x240 + 8 * i, int(py) & M32)
                else:
                    mem.w32(c + 0x23C + 8 * i, M32)
                    mem.w32(c + 0x240 + 8 * i, M32)
            self.pending_slot7 = 1 if n else 0
        if r() < 0.01:
            mem.w32(c + 0x2C0, mem.u32(RC.G_SIM_FRAME) + rng.choice((-5, 3, 30)))
        if r() < 0.02:                                      # stuck: a side-step that ends on the next clock tick
            mem.w32(c + 0x2D8, mem.u32(c + 0x300) + rng.choice((0, 1, 1, 1, 5)))
            mem.w32(c + 0x2D4, mem.u32(c + 0x300) - rng.choice((0, 290, 301, 400, 400)))
            for i in range(3):
                mem.w32(c + 0x2C8 + 4 * i, mem.u32(c + 0x10 + 4 * i))
        if r() < 0.01:
            mem.w32(c + 0x30, f32(rng.choice((0.0, 0.0, 120.0, -50.0))))

    def respawn(self):
        world, mem = self.world, self.mem
        self.dead_ticks = 0
        keep_seed = mem.u32(world.C + 0x44)
        world.init_creature(self.rng)
        mem.w32(world.C + 0x44, keep_seed)
        self.cflag(self.rng.choice(BODY_FLAGS), True)

    pending_slot7 = None


def run(elf, name, seed, kind, hooks, machine, net, ticks, coverage, counts):
    rig = Rig(elf, seed, kind, hooks, machine, net)
    driver = Driver(rig)
    world, mem, rng = rig.world, rig.emu.mem, rig.rng
    if coverage[0] is None:
        coverage[0] = Coverage(mem)
    cov = coverage[0]
    c = world.C
    bad = {'calls': [], 'writes': [], 'seed': [], 'result': [], 'fault': []}
    both = {}
    total = 0
    serial = [0]
    draws_by_entry = {}

    def do(key, *args):
        serial[0] += 1
        supplied, full = list(args), []
        for k in ENTRIES[key][1]:
            full.append(c if k == 'c' else None if k == 'o' else supplied.pop(0))
        result = rig.compare(key, tuple(full), seed * 1000003 + serial[0], trace=cov.pcs)
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
            FAULTS[result['both_fault']] = FAULTS.get(result['both_fault'], 0) + 1
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
                    print('    ' + fmt_call(call))
                print('  original calls:')
                for call in result['emu_calls']:
                    print('    ' + fmt_call(call))
                sys.exit(1)
        return result

    def vector(spread, base=None):
        base = base if base is not None else c + 0x10
        return (f32(mem.f32(base) + rng.uniform(-spread, spread)), f32(mem.f32(base + 4) + rng.uniform(-spread, spread)),
                mem.u32(base + 8))

    for tick in range(ticks):
        driver.between()
        total += 1
        r = rng.random
        state = mem.s16(c + 0x232)
        # damage arrives (virtual slot 2 of the base class)
        if r() < 0.10:
            for _ in range(rng.choice((1, 1, 2))):
                attacker = rng.choice(world.others + world.players + [0])
                flags = 0
                for _k in range(rng.choice((0, 1, 1, 2, 3))):
                    flags |= rng.choice(DAMAGE_FLAGS)
                amount = rng.choice((0.0, 3.0, 20.0, 20.0, 150.0, 400.0))
                if amount >= 150.0 and r() < 0.3:
                    mem.wf32(c + 0x344, rng.choice((3.0, 0.5)))    # frozen when the blow lands
                do('takeDamage', attacker, flags, f32(amount))
        elif r() < 0.03:
            mem.w32(c + 0x2DC, rng.choice((0x2000, 0x2000, 0x2000 | 0x80000, 0x40000, 0x200000, 0x100000)))
        do('processDamage', world.model if r() < 0.9 else 0)
        do('run', world.model)
        do('updateActive')
        if driver.pending_slot7 is not None:
            do('slot7', driver.pending_slot7)
            driver.pending_slot7 = None
        state = mem.s16(c + 0x232)
        if state != 0x14 or r() < 0.2:
            do('pickTarget', 1 if r() < 0.08 else 0)
            do('stepAnim', rng.choice((f32(1.0), f32(1.0), f32(0.5), f32(1.6))))
            # one movement helper, by "AI state": the driver plays the subclass's switch
            if driver.mode_left <= 0:
                driver.mode = rng.choice(('target', 'target', 'dest', 'dest', 'to', 'direct', 'by', 'settle', 'turn',
                                          'flee', 'flee', 'ally'))
                driver.mode_left = rng.choice((5, 20, 60))
                if r() < 0.5:
                    mem.w16(c + 0x232, rng.choice((0, 1, 3, 5, 0x10, 0x12)))
                if driver.mode == 'dest':
                    do('pickWanderDest')
            driver.mode_left -= 1
            mode = driver.mode
            if mode == 'target':
                do('moveToTarget')
            elif mode == 'dest':
                do('moveToDest')
            elif mode == 'to':
                do('moveTo', vector(rng.choice((10, 60, 500))))
            elif mode == 'direct':
                do('moveToDirect', vector(rng.choice((10, 60, 500))))
            elif mode == 'flee':
                if r() < 0.5:
                    do('fleeFromTarget', rng.choice((0, 1, 0x100)))
                else:
                    do('fleeFrom', rng.choice(world.others + [0]), rng.choice((0, 0, 1)))
            elif mode == 'ally':
                if r() < 0.3:
                    mem.w32(c + 0x238, rng.choice((0, world.nodes[world.others[2]], world.nodes[world.players[0]])))
                do('moveToAlly')
            elif mode == 'by':
                do('moveBy', (f32(rng.uniform(-150, 150)), f32(rng.uniform(-150, 150)), 0))
            elif mode == 'settle':
                do('settle')
            else:
                do('turnToward', rng.choice((0, 0, 1, 2)), vector(300))
        else:
            if r() < 0.5:                                   # active now, not active last tick
                cf = mem.u64(c + 0xA8)
                mem.w64(c + 0xA8, (cf | 0x8000000000000000) & ~0x4000000000000000 & RC.M64)
            do('spawnScavenger')
        # the small helpers on their own
        if r() < 0.10:
            do('isEnemy', rng.choice(world.everything + [0]))
        if r() < 0.05:
            do('isAwayFromHome')
        if r() < 0.04:
            do('randomPointNearHome', rng.choice((300, 120, 2000, 40)))
        if r() < 0.04:
            do('findClearHeading', vector(40), rng.randrange(0x10000), rng.choice((0, 1, 0x100, 0x101)),
               rng.choice((f32(2.0), f32(4.0))))
        if r() < 0.02:
            do('stun', rng.choice((30, 120)), rng.choice((0, 1)))
        if r() < 0.02:
            do('slot31', rng.choice((60, 300)))
        if r() < 0.02:
            do('slot35')
            do('slot36')
        if r() < 0.02:
            do('slot6', rng.choice(world.others + world.players))
        if r() < 0.01:
            do('clearPath')
        if r() < 0.02:
            do('requestPath', vector(300), rng.choice((0, 0, 1, 2, 3)), mem.u32(c + 0x1C),
               rng.choice((0, 0, f32(600.0))))
        if r() < 0.04:
            do('findNearestOnTeam', vector(100), rng.choice((0xFF, 0xFF, 0, 1, 0x1FF)), f32(rng.choice((500.0, 60.0))))
        if r() < 0.04:
            do('isNearView', rng.choice([c + 0x10] + [o + 0x10 for o in world.others[:2]]),
               f32(rng.choice((1000.0, 100.0))))
        if r() < 0.02:
            do('slot7', rng.choice((0, 1)))
        if r() < 0.04:
            if r() < 0.5:
                mem.w8(c + 0x2F8, rng.choice((0, 0, 0, 1, 2, 3)))
            do('avoidanceOffset', rng.choice([0, 0] + world.others[:3]), f32(rng.choice((40.0, 26.0))))
        if r() < 0.04:
            do('avoidanceTarget', vector(rng.choice((20, 300, 0.6))))
        if r() < 0.08:
            do('filterState', rng.choice((0, 1, 3, 5, 6, 9, 15, 16, 0x10, 0x12, 0x13, 0x14, 0x17)))
        if r() < 0.02:
            do('probeThreeRays', vector(200), 0)
        if r() < 0.03 and mem.u64(c + 0xA8) & 0xC00000:
            do('pickWanderDest')
    if rig.unknown:
        bad['calls'].append('calls to addresses that are neither real nor known stubs: %s'
                            % {hex(a): n for a, n in rig.unknown.items()})
    text = '%s, %s, machine %s, %s' % (kind, 'subclass hooks' if hooks else 'base slots', 'B' if machine else 'A',
                                       'net game' if net else 'offline')
    count = serial[0]
    report(name + ' calls', len(bad['calls']), count, 'callbacks in order with arguments; ' + text, bad['calls'])
    report(name + ' writes', len(bad['writes']), count, 'bytes stored and their final values', bad['writes'])
    report(name + ' seed', len(bad['seed']), count, 'shared seed and number of draws', bad['seed'])
    report(name + ' result', len(bad['result']), count, 'returned values', bad['result'])
    report(name + ' faults', len(bad['fault']), count,
           'calls that stopped on one side only (%d stopped on both, the same way)' % sum(both.values()), bad['fault'])
    return count, draws_by_entry


RUNS = (('monster', 0, 0, 0), ('monster', 0, 1, 1), ('monster', 1, 0, 1), ('monster', 1, 1, 0),
        ('miniboss', 0, 0, 1), ('miniboss', 1, 1, 1), ('player', 0, 0, 0), ('player', 1, 1, 1))


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
        print('difftest_creature: %s not found - nothing to compare with (this is not a failure)' % elf)
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('difftest_creature: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    ticks = max(OPTIONS['ticks'] // 10, 1) if OPTIONS['quick'] else OPTIONS['ticks']
    RC.C.set_fpu(OPTIONS['fpu'])
    started = time.time()
    coverage, counts, draws = [None], {}, {}
    total = 0
    for index, (kind, hooks, machine, net) in enumerate(RUNS):
        name = '%s/%s/%s/%s' % (kind, 'hooks' if hooks else 'base', 'B' if machine else 'A', 'net' if net else 'off')
        if OPTIONS['filter'] and OPTIONS['filter'].lower() not in name.lower():
            continue
        n, d = run(elf, name, OPTIONS['seed'] + index, kind, hooks, machine, net, ticks, coverage, counts)
        total += n
        for key, value in d.items():
            draws[key] = draws.get(key, 0) + value
    print()
    print('calls compared per entry point / calls with any mismatch / shared-seed draws seen')
    for key in sorted(counts):
        print('  %-20s %7d / %d / %d' % (key, counts[key][0], counts[key][1], draws.get(key, 0)))
    if coverage[0] is not None:
        print('coverage of the original as executed here (basic blocks, instructions):')
        for part in BODIES:
            b, bt, i, it = coverage[0].numbers(part)
            print('  %-30s blocks %4d of %4d (%5.1f%%)  instructions %4d of %4d (%5.1f%%)'
                  % (part, b, bt, 100.0 * b / bt, i, it, 100.0 * i / it))
            if OPTIONS['verbose'] and b != bt:
                print('      never entered: %s' % ' '.join('%06x' % a for a in coverage[0].missing(part)))
    if FAULTS:
        print('calls in which the original read or wrote unmapped memory, and the model did too: %s'
              % ', '.join('%d at 0x%x' % (n, pc) for pc, n in sorted(FAULTS.items())))
    print('%d calls compared in %.0f s' % (total, time.time() - started))
    return 0 if all(ok for _name, ok in RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
