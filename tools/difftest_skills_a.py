#!/usr/bin/env python3
"""difftest_skills_a.py - compare tools/ref_skills_a.py with the game's own code for the
skills with ids 1-34.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_skills_a.py [path/to/SLUS_209.73] [--quick] [--seed N] [--rounds N]
                                     [-k TEXT] [-v] [--fpu MODEL] [--trace-first]

    --quick       a tenth of the rounds (the statistics sweep stays exhaustive)
    --seed N      seed of the random scenarios (default 3411); a seed repeats exactly
    --rounds N    rounds per scenario (default 80)
    -k TEXT       only the scenarios whose name contains TEXT (e.g. -k stats, -k s04)
    -v            print the first mismatches of every failing property and the blocks
                  never entered
    --fpu MODEL   ps2 (default), ps2g1, chop or nearest: the adder model of BOTH sides
    --trace-first stop at the first mismatching call and print both sides

What is compared
    The ORIGINAL code is executed by tools/ee_emu.py - an instruction interpreter, not a
    console.  The 101 Skill objects are built by the game's own static initialiser
    (0x16ac74) and statistics pass (0x1ebca0), run once at start.  Then, per skill, its
    can-use, cast, constructors, per-tick run and hit handlers are called on a constructed
    world; every such call is run through the model first, on a copy-on-write view of the
    same memory, and these must be equal:
      calls    the sequence of calls to everything outside the model, with arguments
      writes   the set of bytes stored outside the stack, and their final values (this
               includes every object and spell field and the own generators)
      seed     the shared seed 0x404464, and that it advanced exactly as many times as the
               model says it drew
      result   the value returned
    Floats are compared as 32-bit patterns under the interpreter's floating-point model.

What runs for real and what is a stub
    Real: ref_skills_a.MODELLED, the creature-base functions of ref_creature.MODELLED and
    ref_arena_monsters.MODELLED that a call reaches, the three angle functions, the C
    library (powf, sqrtf, strcmp ...) and the type-info getters.  Everything else is a
    recording stub answered by a seeded script (class World): damage_apply, the world
    queries, terrain, pool_new, handle lists, effects, particles, sound, the visual
    constructors.  The objects carry the game's own virtual tables; a slot whose function
    is not real is a named stub at that function's address, and a call to an address that
    is neither real nor a known stub is reported as a failure.

The world
    A player caster (slot 0, with its record), its prediction copy, a monster caster, three
    more players, six other creatures (alive, dead, friendly, blocking, undead ...) and two
    objects that are not creatures, placed around the caster again and again.  A player's
    is-enemy and same-team answers are scripted behind the documented entry conditions of
    Player_isEnemy (which is not modelled); a monster's are the real Creature_isEnemy.  Box
    queries answer with the objects that really are inside, arc queries with the creatures
    ahead, nearest first - plus now and then some that are not, and now and then shuffled.
    pool_new refuses now and then.

Scenarios (-k matches the name)
    stats                    the exhaustive statistics sweep (ids 1-34, levels 0-40 and five
                             outside, every slot), made-up tables, and the tables against
                             tools/dump_tables.py and against docs/spec/skills-01-34.md
    s00 machinery            GameObject_ctor, Projectile_ctor, obj_moveAndCollide,
                             creature_addSpell, creature_findSpellByType
    s02 passives and tables  ids 2, 3, 9, 19, 25, 27, 28, 30: can-use, cast, the helpers
    s04, s07, s09, s11, s12, s14, s15, s16, s20, s21, s23, s24, s26, s29, s31, s33
                             one skill each: player and monster casters, levels 0-40, pool
                             failures, targets in and out of reach, the effect run to its
                             natural end and cut short (owner dead, owner deleted, target
                             gone), the hit handlers on every kind of object
    s05 can-use of the rest  ids 1, 5, 6, 8, 10, 13, 17, 18, 22: can-use only, the prediction
                             copy among the casters (the name is kept: it seeds the cases)
    second pass (appended, so that the scenarios above keep their random cases):
    s13 fireweapons          the fourth weapon buff, with its light
    s18 coneoffire           cast, the Mummy's constructor call, the run; the SA4 property:
                             the descriptor handed to damage_apply
    s17 hammerofwrath        cast, the hammer in states 0, 3, 4, its spell; item_parseDescriptor
                             runs for real (the bytes it leaves undefined are masked)
    s34 shieldbash           can-use, cast, run; the SA3 property (the raw turn target)
    s22 dismissundead        cast, flight, hit; the SA2 property and the target-loop order
    s01 wizardbeam           cast and the held channel (the point arrays handed to the trail
                             functions are stack data and are not compared)
    third pass (appended after those, for the same reason):
    s05 diseaseshield        cast, the Mummy's constructor call, the run at every radius (the
                             particle counts follow it), the tick; the "maximum below minimum"
                             property of its damage calls
    s06 diseasetrail         cast, the spell while the caster walks, a segment on its own
    s08 fireflares           cast, the spell and its flares frame by frame, hit, explosion,
                             burst (40 burst frames in full, the others taken to the burst's
                             end), the spell's destructor for real
    s10 blessed              cast (also refused), the run, the destructor, the statistic
                             Player_regenMana asks for; and the flag word of ids 5, 6, 8, 10
    Each of the four also casts with the prediction copy as the caster now and then, for
    the store table only: the game never lets the copy reach these casts.
    After the coverage the test prints, per skill, the stores a cast made outside its own
    new objects, in order (the prediction-copy table of the companion document).

Not compared: describeRank (slot 4, menu text), the draw functions, and states 1 and 2 of
HammerOfWrath_run.
"""
import hashlib
import math
import os
import random
import re
import sys
import time
import zlib

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError                 # noqa: E402
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_arena_monsters as AM                 # noqa: E402
import ref_skills_a as SA                       # noqa: E402
import difftest_creature as DC                  # noqa: E402
from difftest_creature import Res, f32, fl, rd, M32, is_stack      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = {'quick': False, 'seed': 3411, 'rounds': 80, 'filter': None, 'verbose': False, 'trace_first': False,
           'fpu': 'ps2'}
RESULTS = []
STUB_BASE = 0x00F00000
G_PLAYERS, REC_SIZE, REC_OBJ = RC.G_PLAYERS, RC.REC_SIZE, RC.REC_OBJ
SKILL_STATIC_INIT, SKILL_INIT_STATS_ALL = 0x16AC74, 0x1EBCA0

# function bodies for the coverage count: name -> (start, end, skill id or 0 for shared)
BODIES = {
    'Skill_getStatRange': (0x3C82E4, 0x3C85B0, 0), 'Skill_initStats_base': (0x3C85B0, 0x3C85FC, 0),
    'Skill_getStat': (0x3C85FC, 0x3C8690, 0), 'Skill_getStatTier2': (0x3C8690, 0x3C87F0, 0),
    'Skill_getStatFor': (0x3C87F0, 0x3C8864, 0), 'Skill_getStatForHandle': (0x3C8864, 0x3C88DC, 0),
    'Skill_manaFromStat4': (0x3C88E4, 0x3C8944, 0),
    'creature_addSpell': (0x11A838, 0x11A868, 0), 'creature_findSpellByType': (0x11A710, 0x11A788, 0),
    'GameObject_ctor': (0x14CB10, 0x14CF84, 0), 'Projectile_ctor': (0x150E48, 0x150EE4, 0),
    'obj_moveAndCollide': (0x1509F8, 0x150E48, 0),
}
# entry points: key -> (address, argument kinds, result kind, model method)
#   argument kinds: i integer, v vector by pointer, f float pattern (f12..)
#   result kinds: i integer, f float pattern in f0, n nothing
ENTRIES = {
    'obj_moveAndCollide': (0x1509F8, 'iv', 'i', 'move_and_collide'),
    'GameObject_ctor': (0x14CB10, 'ivii', 'n', 'gameobject_ctor'),
    'Projectile_ctor': (0x150E48, 'ivii', 'n', 'projectile_ctor'),
    'creature_addSpell': (0x11A838, 'ii', 'n', 'add_spell'),
    'creature_findSpellByType': (0x11A710, 'ii', 'i', 'find_spell_by_type'),
}
SKILL_NAMES = {}                # id -> short name, filled by the scenario table
EXTRA_PARTIAL = []              # bodies run for real but not counted for coverage (their partial-word stores are tracked)
OBJECT_TABLES = []              # class tables of GameObject-derived effects (slot 1 becomes 'Creature.v1')
SPELL_TABLES = [AM.VT_SPELL_SUMMON]


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-34s %7d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:6]:
            print('        ' + str(line)[:1500])
    sys.stdout.flush()


class RealSet:
    def __init__(self, addresses):
        self.addresses = set(addresses)

    def __contains__(self, target):
        return target in self.addresses or DC.LIB_LO <= target < DC.LIB_HI


# ---------------------------------------------------------------------------------------
# The scripted world
# ---------------------------------------------------------------------------------------
CREATURE_FLAGS = (0x20, 0x20, 0x20, 0x20, 0x20, 0x28, 0x21, 0x24, 0x20020, 0x1000020)
CREATURE_BITS = (0, 0, 0, 0, 0, 0x200, 0x4000000, 0x800, 0x100000000000, 0x200000000000)
KINDS = (0, 0, 0x10, 0x10, 0x10, 3, 1)


class World:
    """Builds the fake game in the interpreter's memory and answers every stubbed call."""

    def __init__(self, emu, rng, real):
        self.emu, self.mem, self.real = emu, emu.mem, real
        self.stub_addr, self.stub_name = {}, {}
        self.enemy_bias = 0.7
        self.kill_bias = 0.15
        self.fail_alloc = 0.03
        self.ground_bias = 0.08
        self.extra_bias = 0.25
        self.clips = {}                 # entry-name address -> a writable stand-in for what res_find returns
        self.append_lists = False       # a query on a list head that is not empty adds in front (as the real ones do)
        self.build(rng)

    # ---- construction ------------------------------------------------------------------
    def stub_for(self, name):
        if name not in self.stub_addr:
            addr = STUB_BASE + 16 * len(self.stub_addr)
            self.stub_addr[name], self.stub_name[addr] = addr, name
        return self.stub_addr[name]

    def vtable(self, real_slots):
        table = self.emu.alloc(8 * 48)
        for slot in range(48):
            fn = real_slots.get(slot) or self.stub_for('Creature.v%d' % slot)
            self.mem.w32(table + 8 * slot + 4, fn)
        return table

    def build(self, rng):
        emu, mem = self.emu, self.mem
        base = {slot: RC.BASE_BODIES[slot][0] for slot in (20, 30, 31, 35, 36, 37)}
        self.vt_mon = self.vtable(base)
        self.vt_ply = self.vtable({37: RC.BASE_BODIES[37][0]})
        self.vt_prop = self.vtable({})
        self.holder = emu.alloc(0x40)                           # a weapon holder whose slots are stubs
        holder_table = emu.alloc(8 * 24)
        for slot in (1, 2, 4, 5, 6, 8, 11, 15, 17):
            mem.w32(holder_table + 8 * slot + 4, self.stub_for('Holder.v%d' % slot))
        mem.w32(self.holder, holder_table)
        self.model = 0x00C00040
        self.nodes, self.names = {}, {}
        self.players = [emu.alloc(0x600) for _ in range(4)]
        self.player = self.players[0]
        self.copy = emu.alloc(0x600)
        self.monster = emu.alloc(0x600)
        self.mobs = [emu.alloc(0x600) for _ in range(6)]
        self.props = [emu.alloc(0x600) for _ in range(2)]
        self.everything = self.players + [self.copy, self.monster] + self.mobs + self.props
        for i, obj in enumerate(self.players):
            self.names[obj] = 'player%d' % i
        self.names[self.copy], self.names[self.monster] = 'copy', 'monster'
        for i, obj in enumerate(self.mobs):
            self.names[obj] = 'mob%d' % i
        for i, obj in enumerate(self.props):
            self.names[obj] = 'prop%d' % i
        for obj in self.everything:
            self.add_node(obj)
        self.pool, self.pool_size = {}, {}
        self.chains = {}
        self.stack_chain = [emu.alloc(0x10) for _ in range(40)]
        self.argbuf = emu.alloc(0x100)
        self.items = [emu.alloc(0x80) for _ in range(8)]
        self.world_obj = emu.alloc(16)
        mem.w32(RC.G_WORLD, self.world_obj)
        mem.w32(RC.G_NUM_PLAYERS, 4)
        mem.w32(RC.G_EXCLUDE_MASK, 0x20000)
        mem.w32(SA.G_LUMP_GENERATION, 7)
        mem.w32(RC.G_RAND_SEED, rng.getrandbits(32))
        mem.w32(SA.G_COSMETIC_SEED, rng.getrandbits(32))
        mem.w32(RC.G_SIM_FRAME, 600 + rng.randrange(5000))
        for slot in range(4):
            mem.w32(G_PLAYERS + slot * REC_SIZE + REC_OBJ, self.players[slot])
        self.place(rng)

    def add_node(self, obj):
        node = self.emu.alloc(0x20)
        self.mem.w32(node + 0xC, obj)
        self.nodes[obj] = node
        return node

    def add_pool(self, size, count=3, name=None):
        """Blocks pool_new can hand out for one size (zero-filled on each hand-out)."""
        if size in self.pool:
            return self.pool[size]
        blocks = [self.emu.alloc((size + 0x1F) & ~0xF) for _ in range(count)]
        self.pool[size] = blocks
        for i, b in enumerate(blocks):
            self.pool_size[b] = size
            self.names[b] = '%s%d' % (name or 'block%x_' % size, i)
            self.add_node(b)
        return blocks

    def place(self, rng, centre=None, spread=140.0):
        """All objects around the player caster, with fresh flags (again and again)."""
        mem = self.mem
        cx, cy, cz = centre or (rng.uniform(-9000, 9000), rng.uniform(-9000, 9000), rng.choice((0.0, 10.0, 250.0)))
        self.centre = (cx, cy, cz)
        for obj in self.everything:
            for off in range(0, 0x600, 4):
                mem.w32(obj + off, 0)
            near = rng.random() < 0.7
            r = spread if near else rng.choice((400.0, 1200.0))
            mem.wf32(obj + 0x10, cx + rng.uniform(-r, r))
            mem.wf32(obj + 0x14, cy + rng.uniform(-r, r))
            mem.wf32(obj + 0x18, cz + rng.choice((0.0, 0.0, 0.0, 0.0, -20.0, 30.0, 100.0)))
            mem.wf32(obj + 0x1C, rng.choice((8.0, 16.0, 24.0, 30.0)))
            mem.wf32(obj + 0x20, rng.choice((40.0, 72.0, 72.0, 96.0)))
            mem.w16(obj + 0x38, rng.randrange(0x10000))
            mem.w32(obj + 0x44, rng.getrandbits(32))
            mem.wf32(obj + 0x228, rng.choice((40.0, 300.0, 300.0, 0.0)))
            mem.wf32(obj + 0x22C, 300.0)
            mem.wf32(obj + 0x68, rng.choice((0.0, 0.0, 0.25, 0.5, 1.0)))
        for slot, obj in enumerate(self.players):
            mem.w32(obj + 0xC, 0x60 | rng.choice((0, 0, 0, 0, 8)))
            mem.w32(obj + 0x48, self.vt_ply)
            mem.w32(obj + 0x3C8, slot)
            mem.w8(obj + 0x310, rng.choice((0, 0, 1)))
            mem.w8(G_PLAYERS + slot * REC_SIZE + 0x4C24, mem.u8(obj + 0x310))
        mem.w32(self.player + 0xC, 0x60)
        for off in (0x10, 0x14, 0x18):
            mem.w32(self.copy + off, mem.u32(self.player + off))
        mem.w32(self.copy + 0xC, 0x20060)
        mem.w32(self.copy + 0x48, self.vt_ply)
        mem.w32(self.copy + 0x3C8, 0)
        for obj in [self.monster] + self.mobs:
            mem.w32(obj + 0xC, rng.choice(CREATURE_FLAGS))
            mem.w32(obj + 0x48, self.vt_mon)
            mem.w64(obj + 0xA8, rng.choice(CREATURE_BITS))
            mem.w8(obj + 0xB4, rng.choice(KINDS))
            mem.w8(obj + 0x310, rng.choice((0xFF, 0xFF, 0xFF, 0, 1, 2)))
            mem.w16(obj + 0x314, rng.choice((0, 0, 0, 40)))
            mem.w16(obj + 0x232, rng.choice((3, 5, 6, 0x14)))
        mem.w32(self.monster + 0xC, 0x20)
        mem.w8(self.monster + 0x310, 0xFF)
        for obj in self.props:
            mem.w32(obj + 0xC, rng.choice((0, 0, 0x1000000, 0x200, 1, 0x20000000)))
            mem.w32(obj + 0x48, self.vt_prop)
        mem.wf32(RC.G_LEVEL_MONSTER_LEVEL, rng.choice((1.0, 2.0, 3.5, 7.5, 30.0, 60.0)))
        mem.w32(SA.G_PVP_MODE_A, rng.choice((0, 0, 0, 1)))
        mem.w8(RC.G_CUTSCENE_ACTIVE, 0)

    def put(self, obj, pos, dx=0.0, dy=0.0, dz=0.0):
        """Place an object at a position (patterns) plus an offset."""
        self.mem.wf32(obj + 0x10, fl(pos[0]) + dx)
        self.mem.wf32(obj + 0x14, fl(pos[1]) + dy)
        self.mem.wf32(obj + 0x18, fl(pos[2]) + dz)

    def enemy(self, obj, kind=None):
        """Make a creature a plain living enemy of everybody (optionally of a kind)."""
        mem = self.mem
        mem.w32(obj + 0xC, 0x20)
        mem.w64(obj + 0xA8, 0)
        mem.w8(obj + 0x310, 3)
        mem.wf32(obj + 0x228, 300.0)
        if kind is not None:
            mem.w8(obj + 0xB4, kind)

    def spell_list(self, creature, spells):
        """Give a creature an attached-spell list (+0x364): the spells' own nodes, chained."""
        mem = self.mem
        nodes = [self.nodes[s] for s in spells]
        for i, node in enumerate(nodes):
            mem.w32(node, nodes[i + 1] if i + 1 < len(nodes) else 0)
        mem.w32(creature + 0x364, nodes[0] if nodes else 0)

    def name_of(self, addr):
        for base, name in self.names.items():
            size = self.pool_size.get(base, 0x600)
            if base <= addr < base + max(size, 4):
                return '%s+%x' % (name, addr - base)
        if G_PLAYERS <= addr < G_PLAYERS + 4 * REC_SIZE:
            return 'record%d+%x' % ((addr - G_PLAYERS) // REC_SIZE, (addr - G_PLAYERS) % REC_SIZE)
        for node_owner, node in self.nodes.items():
            if node <= addr < node + 0x20:
                return 'node(%s)+%x' % (self.names.get(node_owner, hex(node_owner)), addr - node)
        return '%x' % addr

    # ---- answers ------------------------------------------------------------------------
    def respond(self, name, args, view, rng):
        handler = getattr(self, 'on_' + name.replace('.', '_'), None)
        if handler is not None:
            return handler(args, view, rng)
        return Res()

    def on_pool_new(self, args, view, rng):
        blocks = self.pool.get(args[0])
        if blocks is None:
            raise AssertionError('pool_new(0x%x): the scenario has no blocks of this size' % args[0])
        used = view.state.setdefault('pool', {})
        index = used.get(args[0], 0)
        if index >= len(blocks) or rng.random() < self.fail_alloc:
            return Res(0)
        used[args[0]] = index + 1
        block = blocks[index]
        for off in range(0, (args[0] + 3) & ~3, 4):
            view.poke(block + off, 4, 0)
        return Res(block)

    def on_handle_clear(self, args, view, rng):
        if args[0] != 'stack':
            view.poke(args[0], 4, 0)
        return Res()

    def on_handle_link(self, args, view, rng):
        head, back, obj = args
        if head == 'stack' or obj not in self.nodes:
            return Res()
        node = self.nodes[obj]
        if SA.G_GRID_A <= head <= SA.G_OFF_GRID or RC.G_RUN_LIST_ACTIVE <= head < RC.G_RUN_LISTS_60 + 0x100:
            if back != 'stack':
                view.poke(back, 4, node)                # a grid cell or a run list: the object's own word
        elif obj in self.pool_size and head != obj + 0x4C:
            view.poke(node, 4, rd(view, head))          # a list that grows at the front
            view.poke(head, 4, node)
        else:
            view.poke(head, 4, node)
        return Res()

    def geometry(self, view, obj):
        return (fl(rd(view, obj + 0x10)), fl(rd(view, obj + 0x14)), fl(rd(view, obj + 0x18)),
                fl(rd(view, obj + 0x1C)), fl(rd(view, obj + 0x20)))

    def candidates(self, view):
        live = [b for b in self.pool_size if rd(view, b + 0x48) and b in view.state.get('alive', ())]
        return self.everything + live

    def on_world_collectObjectsInBox(self, args, view, rng):
        low, high, cap = [fl(v) for v in args[0]], [fl(v) for v in args[1]], args[2]
        found = []
        for obj in self.candidates(view):
            if obj == self.copy:
                continue
            x, y, z, r, h = self.geometry(view, obj)
            if low[0] - r <= x <= high[0] + r and low[1] - r <= y <= high[1] + r and z <= high[2] and low[2] <= z + h:
                found.append(obj)
        if rng.random() < self.extra_bias:
            found.insert(rng.randrange(len(found) + 1), rng.choice(self.everything))
        if rng.random() < 0.3:
            rng.shuffle(found)
        return Res(outs=[found[:max(cap - 1, 0)]])

    def on_world_collectObjectsInArc(self, args, view, rng):
        centre, facing, _head, _filter, radius, arc, _half = args
        cx, cy, cz = (fl(v) for v in centre)
        reach = fl(radius)
        found = []
        for obj in self.everything:
            if obj == self.copy:
                continue
            flags = rd(view, obj + 0xC)
            x, y, z, r, h = self.geometry(view, obj)
            if not flags & 0x20 and not flags & 0x40 or flags & 0xD:
                continue
            if abs(x - cx) > reach + r or abs(y - cy) > reach + r:
                continue
            heading = C.s16(facing) * math.pi / 32768.0
            ahead = (x - cx) * math.cos(heading) + (y - cy) * math.sin(heading)
            if ahead <= 0.0:                                    # only what lies ahead (the arc itself is the
                continue                                        # real function's business, not this script's)
            if fl(arc) > 0.0:
                side = abs(-(x - cx) * math.sin(heading) + (y - cy) * math.cos(heading))
                if side > ahead * math.tan(min(fl(arc), 170.0) * math.pi / 360.0):
                    continue
            found.append(((x - cx) ** 2 + (y - cy) ** 2, obj))
        found.sort()
        found = [obj for _d, obj in found]
        if rng.random() < self.extra_bias:
            found.insert(rng.randrange(len(found) + 1), rng.choice(self.everything))
        if rng.random() < 0.2:
            rng.shuffle(found)
        if rng.random() < 0.1:
            found = []
        return Res(outs=[found[:30]])

    def on_world_collectInSphere(self, args, view, rng):
        centre, _facing, _head, radius = args
        cx, cy, _cz = (fl(v) for v in centre)
        found = []
        for obj in self.everything:
            if obj == self.copy:
                continue
            x, y, _z, r, _h = self.geometry(view, obj)
            if (x - cx) ** 2 + (y - cy) ** 2 <= (fl(radius) + r) ** 2:
                found.append(obj)
        if rng.random() < self.extra_bias:
            found.insert(rng.randrange(len(found) + 1), rng.choice(self.everything))
        rng.shuffle(found)
        if rng.random() < 0.15:
            found = []
        return Res(outs=[found[:30]])

    def on_damage_apply(self, args, view, rng):
        victim = args[0]
        if victim in self.names and rng.random() < self.kill_bias:
            view.poke(victim + 0x228, 4, f32(rng.choice((0.0, -5.0))))
            view.poke(victim + 0xC, 4, rd(view, victim + 0xC) | 8)
        return Res(rng.choice((0, 1, 1, 7)))

    def on_terrain_height(self, args, view, rng):
        z = fl(args[1][2])
        if rng.random() < self.ground_bias:
            return Res(f=f32(z + rng.choice((0.5, 3.0, 11.0, 40.0))))
        return Res(f=f32(z - rng.choice((0.0, 0.5, 6.0, 10.0, 30.0, 200.0))))

    def on_terrain_raycast(self, args, view, rng):
        return Res(f=rng.choice(DC.RAY_ANSWERS))

    def on_water_test(self, args, view, rng):
        return Res(rng.choice((0, 0, 1)))

    def on_libc_sprintf(self, args, view, rng):
        return Res(outs=[b'name%d' % rng.randrange(3)])

    def on_res_find(self, args, view, rng):
        if args[1] in self.clips:
            return Res(self.clips[args[1]])
        return Res(0x00D00000 + rng.randrange(4) * 0x10)

    def on_Player_animStep(self, args, view, rng):
        return Res(rng.choice((0, 0, 0, 0, 1, 2, 2, 3, 6)))

    def on_Player_move(self, args, view, rng):
        return Res(rng.choice((0, 0, 4)))

    def on_net_isLocalSlot(self, args, view, rng):
        return Res(rng.choice((0, 1)))

    def on_Creature_v26(self, args, view, rng):
        return Res(rng.randrange(0x10000))

    def on_obj_getPropInt(self, args, view, rng):
        return Res(0)

    def on_Creature_v20(self, args, view, rng):
        other = args[1]                                         # the documented entry conditions of Player_isEnemy
        if not other or other == args[0]:                       # 0x1b5ea8; its team logic is the scripted part
            return Res(0)
        flags = rd(view, other + 0xC)
        if not flags & 0x20 or flags & 0x1000008 or rd(view, other + 0xA8, 8) & 0x4000800:
            return Res(0)
        return Res(1 if rng.random() < self.enemy_bias else 0)

    def on_Creature_v22(self, args, view, rng):
        return Res(rng.choice((0, 1, 1)))

    def on_Creature_v16(self, args, view, rng):
        return Res(self.model)

    def on_creature_bossRank(self, args, view, rng):
        return Res(rng.choice((0, 0, 0, 0, 1, 2)))

    def on_model_getSamplePointCount(self, args, view, rng):
        return Res(rng.choice((0, 0, 1, 3, 7, 7, 12)))

    def on_model_getSamplePoint(self, args, view, rng):
        pos = args[2]
        point = tuple(f32(fl(pos[i]) + rng.uniform(-30, 30)) for i in range(3))
        return Res(outs=[point, (f32(rng.uniform(-1, 1)), 0, f32(1.0))])

    def on_model_getAttachPoint(self, args, view, rng):
        pos = args[1]
        point = tuple(f32(fl(pos[i]) + rng.uniform(-20, 20)) for i in range(3))
        return Res(outs=[point, (f32(1.0), 0, 0)])

    def on_player_getSkillRank(self, args, view, rng):
        return Res(rng.choice((0, 0, 1, 3, 9, 20)))

    def on_net_objOrGhost(self, args, view, rng):
        return Res(self.copy if args[0] == self.player and rng.random() < 0.5 else args[0])

    def on_world_findObjectByName(self, args, view, rng):
        return Res(rng.choice((0, 0, self.mobs[0])))

    def on_world_findFreeSpot(self, args, view, rng):
        pos = args[0]
        return Res(outs=[(f32(fl(pos[0]) + rng.uniform(-70, 70)), f32(fl(pos[1]) + rng.uniform(-70, 70)), pos[2]),
                         rng.choice((0, 1, 1))])

    def on_Skill_v12(self, args, view, rng):
        return Res(rng.choice((0, 3, 10, 40, 100)))

    def on_PhProp_ctor(self, args, view, rng):
        block = args[0]
        for off in (0x30, 0xFC, 0x100):                        # what the prop's constructor leaves there
            view.poke(block + off, 4, f32(rng.uniform(-90.0, 90.0)))
        return Res()

    def on_trail_create(self, args, view, rng):
        return Res(rng.choice((0, 3, 17)))

    def on_sound_playOnObject(self, args, view, rng):
        return Res(rng.choice((0xFFFFFFFF, 0x8105, 9)))

    on_sound_playAtPos = on_sound_playOnObject

    def on_terrain_heightAtPoint(self, args, view, rng):
        return Res(f=f32(fl(args[1][2]) - rng.choice((0.0, 4.0, 12.5))))

    def on_particleGroup_create(self, args, view, rng):
        return Res(rng.choice((0, 2, 9)))

    def on_Skelight_ctor(self, args, view, rng):
        block = args[0]
        view.poke(block + 0xC, 4, 0x20)
        view.poke(block + 0x48, 4, self.vt_mon)
        view.poke(block + 0x50, 4, rng.choice((0, self.holder, self.holder)))
        for i in range(3):
            view.poke(block + 0x10 + 4 * i, 4, args[1][i])
        return Res()

    def on_text_lookup(self, args, view, rng):
        return Res(0x00D10000 + (args[0] & 0xFF0))

    def on_Creature_getVisualPos(self, args, view, rng):
        obj = args[0]
        return Res(outs=[tuple(f32(fl(rd(view, obj + 0x10 + 4 * i)) + rng.uniform(-3, 3)) for i in range(3))])

    def on_model_transformSamplePoint(self, args, view, rng):
        matrix = args[1]
        point = tuple(f32(fl(matrix[9 + i]) + rng.uniform(-15, 15)) for i in range(3))
        return Res(outs=[point, (f32(rng.choice((0.0, 1.0, 40.0, 900.0))), 0, 0)])


# ---------------------------------------------------------------------------------------
# The rig: stubs on the interpreter side, callbacks on the model side
# ---------------------------------------------------------------------------------------
def desc_canon(mem, v):
    """A damage descriptor as the model names it: 0, an address outside the stack, or the
    record on the stack read back - only the fields an empty record has: the eight
    halfwords at +0x10, the bytes +0x20 / +0x21 and the four effect slots at +0x24."""
    if v == 0 or not is_stack(v):
        return v
    ok = all(mem.u16(v + 0x10 + 2 * k) == 0 for k in range(8)) and mem.u8(v + 0x20) == 0xFF and mem.u8(v + 0x21) == 0xFF
    slots = []
    for k in range(4):
        base = v + 0x24 + 8 * k
        slots.append(None if mem.u16(base) == 0xFFFF else tuple(mem.u16(base + 2 * j) for j in range(4)))
    if not ok:
        return ('desc?', bytes(mem.read(v + 0x10, 0x34)).hex())
    return ('desc',) + tuple(slots)


class Rig:
    def __init__(self, elf, seed):
        self.rng = random.Random(seed)
        emu = self.emu = EE(elf, fpu_model=OPTIONS['fpu'])
        emu.div_zero = 'r5900'
        mem = emu.mem
        # the game's own construction of the 101 Skill objects and of their statistics
        emu.record_calls = emu.record_writes = False
        emu.call(SKILL_STATIC_INIT, 1, 0xFFFF, max_steps=20000000)
        emu.call(SKILL_INIT_STATS_ALL, max_steps=20000000)
        # type-info getters fill their descriptor on the first call: make that call now
        self.type_info = {}
        for table in SPELL_TABLES:
            getter = mem.u32(table + 4)
            self.type_info[getter] = emu.call(getter) & M32
        self.carry = {}                                         # skill id -> the getter its can-use asks for
        for sid in range(1, 35):
            fn = mem.u32(mem.u32(mem.u32(SA.G_SKILL_TABLE + 4 * sid) + 0x60) + 0xC)
            getter = SA.carries_getter(mem.u32, fn)
            if getter is not None:
                self.carry[sid] = getter
                if getter not in self.type_info:
                    self.type_info[getter] = emu.call(getter) & M32
        emu.record_calls = emu.record_writes = True
        SA.Model.type_info = self.type_info
        real = set(SA.MODELLED.values()) | set(RC.MODELLED.values()) | set(AM.MODELLED.values()) | set(DC.REAL_OTHER)
        real |= set(SA.MATH.values())
        real |= set(self.type_info)
        real -= UNREAL
        self.real = emu.follow = RealSet(real)
        self.world = World(emu, self.rng, self.real)
        self.calls, self.buffers, self.unknown = [], {}, {}
        self.eview = DC.EmuView(emu)
        self.eview.state = {}
        self.script_rng = None
        self.names = {}

        def add(addr, name, ext):
            assert addr not in real, (hex(addr), name)
            assert self.names.setdefault(addr, name) == name, (hex(addr), name, self.names[addr])
            emu.stub(addr, function=self.make_stub(name, ext), name=name)

        for name, ext in SA.EXTERNALS.items():
            if ext.addr and ext.addr not in real:
                add(ext.addr, name, ext)
        # the game's own tables: a slot function that is not real becomes a named stub
        for tables, prefix, slots in ((OBJECT_TABLES, 'Creature', range(1, 12)), (SPELL_TABLES, 'Spell', range(1, 5))):
            for table in tables:
                for slot in slots:
                    fn = mem.u32(table + 8 * slot + 4)
                    name = '%s.v%d' % (prefix, slot)
                    if fn and fn not in real and fn not in self.names:
                        add(fn, name, SA.EXTERNALS.get(name) or RC.Ext(0, 'p', 0, 'n'))
        for sid in range(1, 102):
            table = mem.u32(mem.u32(SA.G_SKILL_TABLE + 4 * sid) + 0x60)
            for slot in (1, 2, 4):
                fn = mem.u32(table + 8 * slot + 4)
                name = 'Skill.v%d' % slot
                if slot == 1 and sid < 35 and (sid in self.carry or mem.u32(fn) == 0x03E00008):
                    real.add(fn)                                # a can-use of the generic shapes
                    self.real.addresses.add(fn)
                if fn not in real and fn not in self.names:
                    add(fn, name, SA.EXTERNALS.get(name) or RC.Ext(0, 'p', 0, 'n'))
        for name, addr in list(self.world.stub_addr.items()):
            if addr not in self.names:
                add(addr, name, SA.EXTERNALS.get(name) or RC.Ext(0, 'p', 0, 'n'))
        self.masked = set()                                     # bytes a scenario declares undefined (not compared)
        # the C library's sscanf sets its stream tables up on the first call: make that call now, on scratch memory
        emu.record_calls = emu.record_writes = False
        kept = mem.u32(RC.G_RAND_SEED)
        emu.call(SA.MODELLED['item_parseDescriptor'], 0x5508D0, self.world.argbuf, -1, 0, max_steps=20000000)
        mem.w32(RC.G_RAND_SEED, kept)
        for off in range(0, 0x48, 4):
            mem.w32(self.world.argbuf + off, 0)
        emu.record_calls = emu.record_writes = True
        self.partial, self.partial_ops = [], {}
        bodies = [(s, e) for s, e, _sid in BODIES.values()] + list(DC.BODIES.values()) + EXTRA_PARTIAL
        for start, end in bodies:
            for pc in range(start, end, 4):
                w = mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E) and pc not in self.partial_ops:
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))

    def partial_hook(self, pc, base, offset):
        def note(emu):
            ea = (emu.r[base] + offset) & M32
            if not is_stack(ea):
                self.partial.append((pc, ea))
        return note

    def stored_bytes(self, lo, hi):
        """The bytes the original stored outside the stack and outside [lo, hi), exact for
        the partial-word stores (tools/ee_emu.py logs those as whole aligned words)."""
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

    def chain(self, head, count):
        """The list nodes a query hands back for a list head: scratch nodes for a head on
        the caller's stack, nodes kept per head otherwise (the list outlives the call)."""
        if head == 'stack':
            return self.world.stack_chain[:count]
        nodes = self.world.chains.setdefault(head, [])
        while len(nodes) < count:
            nodes.append(self.emu.alloc(0x10))
        return nodes[:count]

    def write_chain(self, view, head, ptr, objects):
        nodes = self.chain(head, len(objects))
        for j, (node, obj) in enumerate(zip(nodes, objects)):
            view.poke(node, 4, nodes[j + 1] if j + 1 < len(nodes) else 0)
            view.poke(node + 0xC, 4, obj)
        if ptr is not None:
            view.poke(ptr, 4, nodes[0] if nodes else 0)

    # ---- interpreter side ---------------------------------------------------------------
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
            elif kind == 'S':
                canon.append(('buf', self.buffers[v]) if v in self.buffers else v)
            elif kind == 'D':
                canon.append(desc_canon(mem, v))
            elif kind == 'm':
                canon.append(tuple(mem.u32(v + 4 * j) for j in range(12)))
            elif kind == 'H':
                canon.append('stack' if is_stack(v) else v)
                outs.append((kind, v))
            elif kind in 'OW':
                canon.append(1 if v else 0)
                outs.append((kind, v))
            elif kind in 'onwbL':
                outs.append((kind, v))
        for j in range(ext.floats):
            canon.append(emu.f[12 + j])
        sp = emu.r[29] & M32
        for j in range(getattr(ext, 'stack', 0)):
            canon.append(mem.u32(sp + 8 * j))
        return canon, outs

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
                value = given.pop(0) if given else ((0, 0, 0) if kind in 'oO' else ([] if kind in 'nLH' else 0))
                if kind == 'H':
                    if self.world.append_lists and is_stack(ptr):       # the entries already there stay, behind the new ones
                        node, old = mem.u32(ptr), []
                        while node:
                            old.append(mem.u32(node + 0xC))
                            node = mem.u32(node)
                        value = list(value) + old
                    self.write_chain(self.eview, 'stack' if is_stack(ptr) else ptr, None, value)
                    nodes = self.chain('stack' if is_stack(ptr) else ptr, len(value))
                    if is_stack(ptr):
                        mem.w32(ptr, nodes[0] if nodes else 0)
                    else:
                        self.eview.poke(ptr, 4, nodes[0] if nodes else 0)
                elif kind in 'oO':
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
            if ext.ret == 'f':
                emu.f[0] = res.f & M32
            if ext.ret == 'q':
                return res.ret & RC.M64
            return ee_emu.s32(res.ret)
        return stub

    # ---- model side -----------------------------------------------------------------------
    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                ext = SA.EXTERNALS[name]
                position = 0
                given = list(res.outs)
                for kind in ext.ints:                       # a list head outside the stack is memory too
                    if kind == 'H':
                        value = given[0] if given else []
                        head = args[position]
                        if self.rig.world.append_lists and head == 'stack':     # the scratch nodes as the stub leaves them
                            value = list(value) + self.view.state.get('stack list', [])
                            self.view.state['stack list'] = value
                        self.rig.write_chain(self.view, head, None if head == 'stack' else head, value)
                    if kind in 'oOwWbnLH' and given:
                        given.pop(0)
                    if kind in 'ipvelsSOWHDm':
                        position += 1
                ret = res.ret & (RC.M64 if ext.ret == 'q' else M32)
                return SA.shape_result(name, args, ret, res.f & M32, res.outs)
            return answer

    # ---- one call, both sides ---------------------------------------------------------------
    def compare(self, key, args, call_seed, trace=None):
        addr, kinds, ret_kind, method = ENTRIES[key]
        emu, world = self.emu, self.world
        mem = emu.mem
        seed_before = mem.u32(RC.G_RAND_SEED)
        mview = DC.ModelView(mem)
        mview.state = {'alive': self.eview.state.get('alive', set())}
        model = SA.Model(mview, Rig.Callbacks(self, mview, random.Random(call_seed)))
        model_error = None
        try:
            mret = getattr(model, method)(*args)
        except EmuError as exc:
            model_error, mret = exc, None
        self.calls, self.buffers = [], {}
        self.eview.touched = set()
        self.eview.state = {'alive': self.eview.state.get('alive', set())}
        self.script_rng = random.Random(call_seed)
        emu.reset_log()
        self.partial = []
        emu.trace = [] if trace is not None else None
        emu.r[29] = emu.stack_hi - 0x100
        ints, nfloat, scratch = [], 0, world.argbuf
        for a, k in zip(args, kinds):
            if k == 'i':
                ints.append(ee_emu.s32(a & M32))
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
            eret = emu.call(addr, *ints, max_steps=6000000)
        except EmuError as exc:
            emu_error, eret = exc, None
        if trace is not None and emu.trace:
            trace.update(emu.trace)
        for c in emu.calls:
            if c.target not in self.real and c.target not in self.names:
                self.unknown[c.target] = self.unknown.get(c.target, 0) + 1
        out = {'key': key, 'fault': None, 'calls': None, 'writes': None, 'seed': None, 'result': None,
               'both_fault': None, 'draws': 0, 'model_calls': model.calls, 'emu_calls': self.calls, 'ret': eret}
        if model_error or emu_error:
            if model_error is None or emu_error is None:
                out['fault'] = 'model %r / original %r' % (model_error, emu_error)
            else:
                out['both_fault'] = getattr(emu_error, 'pc', 0)
            return out
        if model.calls != self.calls:
            out['calls'] = DC.describe_calls(model.calls, self.calls)
        lo, hi = world.argbuf, world.argbuf + 0x100
        ebytes = self.stored_bytes(lo, hi) - self.masked
        mbytes = set()
        for a, size, _value in model.writes:
            mbytes.update(range(a, a + size))
        mbytes -= self.masked
        diff = []
        for a in sorted((ebytes | mbytes | self.eview.touched | mview.touched) - self.masked):
            x, y = mem.load(a, 1), mview.load(a, 1)
            if x != y:
                diff.append((a, x, y))
        if ebytes != mbytes or diff:
            text = ''
            if ebytes - mbytes:
                text += ' only original stores %s;' % sorted({world.name_of(a) for a in ebytes - mbytes})[:10]
            if mbytes - ebytes:
                text += ' only model stores %s;' % sorted({world.name_of(a) for a in mbytes - ebytes})[:10]
            if diff:
                text += ' values differ at %s' % [(world.name_of(a), '%02x' % x, '%02x' % y) for a, x, y in diff[:10]]
            out['writes'] = text
        s = seed_before
        for _ in range(model.draws):
            s = SA.lcg(s)
        if not mem.u32(RC.G_RAND_SEED) == mview.load(RC.G_RAND_SEED, 4) == s:
            out['seed'] = 'model draws %d' % model.draws
        out['draws'] = model.draws
        if ret_kind == 'i' and (eret & M32) != ((mret or 0) & M32):
            out['result'] = 'original %08x model %08x' % (eret & M32, (mret or 0) & M32)
        elif ret_kind == 'f' and emu.f[0] & M32 != (mret or 0) & M32:
            out['result'] = 'original %08x model %08x' % (emu.f[0] & M32, (mret or 0) & M32)
        return out


UNREAL = {0x2A8770, 0x109D68}  # functions of the imported models that stay stubs here (the skeleton's constructors)


class Coverage:
    def __init__(self, mem):
        self.parts = {name: (start, end) + DC.analyse(mem, start, end) for name, (start, end, _sid) in BODIES.items()}
        self.pcs = set()

    def numbers(self, name):
        start, end, leaders, _sites = self.parts[name]
        inside = {pc for pc in self.pcs if start <= pc < end}
        return len(leaders & inside), len(leaders), len(inside), (end - start) // 4

    def missing(self, name):
        _start, _end, leaders, _sites = self.parts[name]
        return sorted(a for a in leaders if a not in self.pcs)


# ---------------------------------------------------------------------------------------
# The scenarios
# ---------------------------------------------------------------------------------------
class Env:
    """One scenario's run: the rig, the counters, and `do`, which compares one call."""

    def __init__(self, rig, name, cov, counts, draws):
        self.rig, self.name, self.cov, self.counts, self.draws = rig, name, cov, counts, draws
        self.world, self.mem, self.rng = rig.world, rig.emu.mem, rig.rng
        self.bad = {'calls': [], 'writes': [], 'seed': [], 'result': [], 'fault': []}
        self.both = {}
        self.serial = 0
        self.round = 0

    def do(self, key, *args):
        self.serial += 1
        result = self.rig.compare(key, tuple(args), OPTIONS['seed'] * 1000003 + zlib.crc32(self.name.encode()) % 1000 * 7919 + self.serial,
                                  trace=self.cov.pcs)
        row = self.counts.setdefault(key, [0, 0])
        row[0] += 1
        failed = False
        for prop in ('fault', 'calls', 'writes', 'seed', 'result'):
            if result[prop]:
                failed = True
                self.bad[prop].append('round %d %s(%s): %s' % (self.round, key, ', '.join(
                    '%x' % a if isinstance(a, int) else str(a) for a in args), result[prop]))
        if result['both_fault'] is not None:
            self.both[result['both_fault']] = self.both.get(result['both_fault'], 0) + 1
        if result.get('draws'):
            self.draws[key] = self.draws.get(key, 0) + result['draws']
        if failed:
            row[1] += 1
            if OPTIONS['trace_first']:
                print('first mismatch in scenario %s, round %d, %s' % (self.name, self.round, key))
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

    def finish(self):
        if self.rig.unknown:
            self.bad['calls'].append('calls to addresses that are neither real nor known stubs: %s'
                                     % {hex(a): n for a, n in self.rig.unknown.items()})
            self.rig.unknown = {}
        n = self.serial
        name = self.name
        report(name + ' calls', len(self.bad['calls']), n, 'callbacks in order with arguments', self.bad['calls'])
        report(name + ' writes', len(self.bad['writes']), n, 'bytes stored and their final values', self.bad['writes'])
        report(name + ' seed', len(self.bad['seed']), n, 'shared seed and number of draws', self.bad['seed'])
        report(name + ' result', len(self.bad['result']), n, 'returned values', self.bad['result'])
        report(name + ' faults', len(self.bad['fault']), n,
               'calls that stopped on one side only (%d stopped on both, the same way)' % sum(self.both.values()),
               self.bad['fault'])
        return n

    # ---- helpers for scenario code ------------------------------------------------------
    def skill(self, sid):
        return self.mem.u32(SA.G_SKILL_TABLE + 4 * sid)

    def caster(self, kinds=('player', 'player', 'monster')):
        kind = self.rng.choice(kinds)
        return {'player': self.world.player, 'monster': self.world.monster, 'copy': self.world.copy, 'none': 0}[kind]

    def pos_of(self, obj, spread=0.0, dz=0.0):
        mem, rng = self.mem, self.rng
        return (f32(mem.f32(obj + 0x10) + rng.uniform(-spread, spread)),
                f32(mem.f32(obj + 0x14) + rng.uniform(-spread, spread)), f32(mem.f32(obj + 0x18) + dz))

    def level(self):
        return self.rng.choice((0, 1, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 15, 16, 20, 21, 30, 40))

    def advance(self, frames=1):
        self.mem.w32(RC.G_SIM_FRAME, (self.mem.u32(RC.G_SIM_FRAME) + frames) & M32)

    def alive(self, *objs):
        self.rig.eview.state.setdefault('alive', set()).update(objs)

    def deleted(self, result, obj, name='Creature.v1'):
        """Did this call end the object (its own slot 1 with 3)?"""
        return any(c[0] == name and c[1][0] == obj for c in result['emu_calls'])


def stats_sweep(elf, cov):
    """Exhaustive: every statistic getter of ids 1-34 at levels 0-40 (and a few outside),
    all five statistics, the three casters of slot 12, the three handles of slot 13, caps
    0 / 1 / 10 / 20, the range slot with and without randomising, and the mana cost."""
    rig = Rig(elf, OPTIONS['seed'])
    emu, mem, world = rig.emu, rig.emu.mem, rig.world
    rng = random.Random(OPTIONS['seed'])
    counts = {'stat': 0, 'tier2': 0, 'for': 0, 'handle': 0, 'range': 0, 'mana': 0, 'adjust': 0, 'stat4': 0}
    bad = {k: [] for k in counts}
    empty, node_p, node_m = emu.alloc(8), world.nodes[world.player], world.nodes[world.monster]
    hp, hm = emu.alloc(8), emu.alloc(8)
    mem.w32(hp, node_p)
    mem.w32(hm, node_m)
    lo_ptr, hi_ptr = world.argbuf, world.argbuf + 4
    emu.trace = []

    def original(addr, *ints, fargs=()):
        emu.reset_log()
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x100
        for i, fa in enumerate(fargs):
            emu.f[12 + i] = fa
        ret = emu.call(addr, *[ee_emu.s32(a & M32) for a in ints])
        cov.pcs.update(emu.trace)
        return ret & M32, [w for w in emu.writes if not world.argbuf <= w[1] < world.argbuf + 0x100]

    levels = list(range(0, 41)) + [41, 60, 100, 0xFFFFFFFF, 0xFFFFFFF0]
    for sid in range(1, 35):
        skill = mem.u32(SA.G_SKILL_TABLE + 4 * sid)
        table = mem.u32(skill + 0x60)
        fn = {slot: mem.u32(table + 8 * slot + 4) for slot in range(1, 16)}
        for level in levels:
            for stat in range(5):
                mview = DC.ModelView(mem)
                model = SA.Model(mview)
                got, writes = original(fn[10], skill, stat, level)
                counts['stat'] += 1
                if got != model.skill_call(skill, 10, stat, level) & M32 or writes or model.writes:
                    bad['stat'].append('id %d stat %d level %d: original %d' % (sid, stat, s32(level), s32(got)))
                for cap in (0, 1, 10, 20, 0xFFFFFFFF):
                    got, writes = original(fn[11], skill, stat, level, cap)
                    counts['tier2'] += 1
                    if got != model.skill_call(skill, 11, stat, level, cap) & M32 or writes:
                        bad['tier2'].append('id %d stat %d level %d cap %d: original %d' % (sid, stat, s32(level), s32(cap), s32(got)))
                for caster in (world.player, world.monster, 0, world.copy):
                    cap = rng.choice((0, 0, 10, 20))
                    got, writes = original(fn[12], skill, stat, level, caster, cap)
                    counts['for'] += 1
                    if got != model.skill_call(skill, 12, stat, level, caster, cap) & M32 or writes:
                        bad['for'].append('id %d stat %d level %d caster %s: original %d' % (sid, stat, s32(level), world.name_of(caster), s32(got)))
                for handle in (hp, hm, empty):
                    cap = rng.choice((0, 0, 10, 20))
                    got, writes = original(fn[13], skill, stat, level, handle, cap)
                    counts['handle'] += 1
                    if got != model.skill_call(skill, 13, stat, level, handle, cap) & M32 or writes:
                        bad['handle'].append('id %d stat %d level %d: original %d' % (sid, stat, s32(level), s32(got)))
                for randomise in (0, 1):
                    spread = rng.choice((f32(0.2), f32(0.2), f32(0.0), f32(0.5), f32(1.5), f32(-0.3)))
                    seed = rng.getrandbits(32)
                    mem.w32(RC.G_RAND_SEED, seed)
                    mview = DC.ModelView(mem)
                    model = SA.Model(mview)
                    low, high = model.skill_call(skill, 8, stat, level, randomise, spread)
                    _got, writes = original(fn[8], skill, stat, level, randomise, lo_ptr, hi_ptr, fargs=(spread,))
                    counts['range'] += 1
                    same_seed = mem.u32(RC.G_RAND_SEED) == mview.load(RC.G_RAND_SEED, 4)
                    if (mem.u32(lo_ptr), mem.u32(hi_ptr)) != (low & M32, high & M32) or not same_seed \
                            or {w[1] for w in writes} - {RC.G_RAND_SEED} or model.draws != (4 if randomise else 0):
                        bad['range'].append('id %d stat %d level %d randomise %d spread %08x seed %08x: original %d %d model %d %d'
                                            % (sid, stat, s32(level), randomise, spread, seed, mem.s32(lo_ptr), mem.s32(hi_ptr), s32(low), s32(high)))
            mview = DC.ModelView(mem)
            model = SA.Model(mview)
            _got, writes = original(fn[5], skill, level)
            counts['mana'] += 1
            if emu.f[0] & M32 != model.mana_cost(skill, level) & M32 or writes:
                bad['mana'].append('id %d level %d: original %08x' % (sid, s32(level), emu.f[0]))
            n = rng.choice((1, 2, 10, 20))
            got, writes = original(fn[14], skill, level, n)
            counts['adjust'] += 1
            if got != model.skill_call(skill, 14, level, n) & M32 or writes:
                bad['adjust'].append('id %d level %d' % (sid, s32(level)))
            _got, writes = original(fn[15], skill, level, n)
            counts['stat4'] += 1
            if emu.f[0] & M32 != model.skill_call(skill, 15, level, n) & M32 or writes:
                bad['stat4'].append('id %d level %d: original %08x' % (sid, s32(level), emu.f[0]))
    # made-up tables on a Skill with the base class's slots: negative values and steps, late
    # first levels, tier 2 present or not - what no real id has - and the base initStats
    fake = emu.alloc(0x70)
    table = mem.u32(mem.u32(SA.G_SKILL_TABLE + 4 * 3) + 0x60)
    mem.w32(fake + 0x60, table)
    fn = {slot: mem.u32(table + 8 * slot + 4) for slot in range(1, 16)}
    counts['synthetic'], bad['synthetic'] = 0, []
    for _ in range(4000):
        for i in range(5):
            mem.w16(fake + 0xE + 2 * i, rng.choice((0, 1, 1, 5, 10, 0xFFFE)))
            mem.w16(fake + 0x18 + 2 * i, rng.choice((0, 1, 30, 400, 0xFFF0, 0xFF00)))
            mem.w32(fake + 0x24 + 4 * i, f32(rng.choice((0.0, 0.333, 2.0, 9.008915, -1.5, -40.0, 0.5))))
            mem.w16(fake + 0x38 + 2 * i, rng.choice((0xFFFF, 0xFFFF, 1, 10, 0x8000, 0)))
            mem.w16(fake + 0x42 + 2 * i, rng.choice((0, 2, 15, 0xFFE0)))
            mem.w32(fake + 0x4C + 4 * i, f32(rng.choice((0.0, 0.1, 2.0, -3.0, 0.5))))
        stat, level, cap = rng.randrange(5), rng.choice(levels), rng.choice((0, 0, 1, 10, 20, 0xFFFFFFFF))
        model = SA.Model(DC.ModelView(mem))
        counts['synthetic'] += 3
        got, _w = original(fn[10], fake, stat, level)
        if got != model.skill_call(fake, 10, stat, level) & M32:
            bad['synthetic'].append('slot 10 stat %d level %d: original %d' % (stat, s32(level), s32(got)))
        got, _w = original(fn[11], fake, stat, level, cap)
        if got != model.skill_call(fake, 11, stat, level, cap) & M32:
            bad['synthetic'].append('slot 11 stat %d level %d cap %d: original %d' % (stat, s32(level), s32(cap), s32(got)))
        spread = rng.choice((f32(0.2), f32(1.5), f32(-0.3)))
        low, high = model.skill_call(fake, 8, stat, level, 0, spread)
        original(fn[8], fake, stat, level, 0, lo_ptr, hi_ptr, fargs=(spread,))
        if (mem.u32(lo_ptr), mem.u32(hi_ptr)) != (low & M32, high & M32):
            bad['synthetic'].append('slot 8 stat %d level %d: original %d %d' % (stat, s32(level), mem.s32(lo_ptr), mem.s32(hi_ptr)))
    mview = DC.ModelView(mem)
    model = SA.Model(mview)
    model.skill_call(fake, 9)
    _got, writes = original(fn[9], fake)
    counts['synthetic'] += 1
    if any(mem.load(a, 1) != mview.load(a, 1) for a in range(fake, fake + 0x68)) \
            or {a for _pc, a, size, _v in writes for a in range(a, a + size)} != {a for a, size, _v in model.writes for a in range(a, a + size)}:
        bad['synthetic'].append('base initStats 0x3c85b0')
    emu.trace = None
    report('stats on made-up tables', len(bad['synthetic']), counts['synthetic'],
           'slots 8, 10, 11 on 4000 random tables (negative values, tier 2 or not) and the base initStats', bad['synthetic'])
    tables_check(elf, mem)
    text = 'ids 1-34 x levels 0-40 and five outside x statistics 0-4'
    report('stats slot 10 (tier 1)', len(bad['stat']), counts['stat'], text, bad['stat'])
    report('stats slot 11 (tier 2, caps)', len(bad['tier2']), counts['tier2'], text + ' x caps 0, 1, 10, 20, -1', bad['tier2'])
    report('stats slot 12 (by caster)', len(bad['for']), counts['for'], text + ' x player, monster, none, copy', bad['for'])
    report('stats slot 13 (by handle)', len(bad['handle']), counts['handle'], text + ' x three handles', bad['handle'])
    report('stats slot 8 (range)', len(bad['range']), counts['range'], text + ' x plain / randomised, with the seed', bad['range'])
    report('mana cost (slot 5)', len(bad['mana']), counts['mana'], 'ids 1-34 x the same levels, float patterns', bad['mana'])
    report('slot 14 / slot 15', len(bad['adjust']) + len(bad['stat4']), counts['adjust'] + counts['stat4'],
           'level pass-through and (float) statistic 4', bad['adjust'] + bad['stat4'])
    return sum(counts.values())


def s32(x):
    return ee_emu.s32(x & M32)


SPEC_TABLE_IDS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 82, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25,
                  (27, 28, 30), 26, 29, 31, 32, 33, 34)       # the statistic tables of the specification, in order


def executed_tables(mem, sid):
    """(tier, statistic) -> (first level, base, step bits) as the game's own code left them."""
    skill = mem.u32(SA.G_SKILL_TABLE + 4 * sid)
    out = {}
    for stat in range(5):
        out[1, stat] = (mem.s16(skill + 0xE + 2 * stat), mem.s16(skill + 0x18 + 2 * stat), mem.u32(skill + 0x24 + 4 * stat))
        out[2, stat] = (mem.s16(skill + 0x38 + 2 * stat), mem.s16(skill + 0x42 + 2 * stat), mem.u32(skill + 0x4C + 4 * stat))
    return out


def tables_check(elf, mem):
    """The statistic tables three ways: as executed (the game's constructors and initStats
    under the interpreter), as tools/dump_tables.py reads them from the instructions
    without running them, and as docs/spec/skills-01-34.md prints them."""
    import types
    import dump_tables
    ctx = dump_tables.Ctx(types.SimpleNamespace(iso=None, executable=elf, force=False, balance=None, text=None, objects=None))
    rows = {row['id']: row for row in dump_tables.t_skills(ctx)}
    bad, count = [], 0
    for sid in list(range(1, 35)) + [82, 83, 52, 53, 81, 85]:
        table, row = executed_tables(mem, sid), rows[sid]
        skill = mem.u32(SA.G_SKILL_TABLE + 4 * sid)
        head = (int(row['kind']), int(row['recast_frames']), int(row['flags'], 16))
        if head != (mem.u32(skill + 8), mem.s16(skill + 0xC), mem.u32(skill + 4)):
            bad.append('id %d kind / recast / flags: read %s' % (sid, head))
        for tier, names in ((1, ('t1_first_level', 't1_base', 't1_step')), (2, ('t2_first_level', 't2_base', 't2_step'))):
            cells = [row[name].split('/') for name in names]
            for stat in range(5):
                count += 1
                first, base, step = table[tier, stat]
                read = (cells[0][stat], cells[1][stat], cells[2][stat])
                if read == ('', '', ''):                        # not written by the functions read: zero-filled, or -1 from the constructor
                    expect = ('', '', '') if (first, base, step) in ((0, 0, 0), (-1, 0, 0)) else None
                else:
                    expect = (str(first) if read[0] else '', str(base) if read[1] else '', dump_tables.ffmt(step) if read[2] else '')
                    if (read[0] == '' and first not in (0, -1)) or (read[1] == '' and base) or (read[2] == '' and step):
                        expect = None
                if read != expect:
                    bad.append('id %d tier %d statistic %d: executed %d / %d / %08x, read %s' % (sid, tier, stat, first, base, step, read))
    report('tables: dump_tables.py reading', len(bad), count, 'the static reading of the tables against the executed objects', bad)
    path = os.path.join(ROOT, 'docs', 'spec', 'skills-01-34.md')
    if not os.path.exists(path):
        return
    blocks, cur = [], None
    for line in open(path, encoding='utf-8').read().split('\n'):
        m = re.match(r'^\| s([0-4]) \| ([12]) \([a-z]+\) \| (-?\d+) \| (-?\d+) \| [-0-9.e]+ \| 0x([0-9a-f]{8}) \|', line)
        if m:
            if cur is None:
                cur = []
                blocks.append(cur)
            cur.append((int(m.group(2)), int(m.group(1)), int(m.group(3)), int(m.group(4)), int(m.group(5), 16)))
        else:
            cur = None
    bad, count = [], 0
    if len(blocks) != len(SPEC_TABLE_IDS):
        bad.append('the document has %d statistic tables, %d expected' % (len(blocks), len(SPEC_TABLE_IDS)))
    for ids, block in zip(SPEC_TABLE_IDS, blocks):
        for sid in ids if isinstance(ids, tuple) else (ids,):
            table = executed_tables(mem, sid)
            listed = set()
            for tier, stat, first, base, step in block:
                count += 1
                listed.add((tier, stat))
                if table[tier, stat] != (first, base, step):
                    bad.append('id %d tier %d statistic %d: the document has %d / %d / %08x, executed %d / %d / %08x'
                               % ((sid, tier, stat, first, base, step) + table[tier, stat]))
            for (tier, stat), value in sorted(table.items()):   # what the document leaves out must be unset
                count += 1
                unset = value[0] < 0 if tier == 2 else value == (0, 0, 0)
                if (tier, stat) not in listed and not unset:
                    bad.append('id %d tier %d statistic %d is not in the document: executed %d / %d / %08x' % ((sid, tier, stat) + value))
    report('tables: the specification', len(bad), count, 'every table row of docs/spec/skills-01-34.md against the executed objects', bad)


SCENARIOS = []                  # (name, skill id, function(env, rounds))
COPY_ROWS = {}                  # skill id -> {what: set of (pc, where)}: the prediction-copy table (see note_stores)


def note_stores(env, sid, what, skip=()):
    """After a call: the first store the original made outside the stack that is not into a block it had just
    been handed by pool_new, not the shared seed and not in `skip` (address ranges) - the first thing a cast leaves
    behind that destroying its spell would not undo.  Collected per skill for the prediction-copy table."""
    world = env.world
    row = COPY_ROWS.setdefault(sid, {}).setdefault(what, [])
    for pc, addr, _size, _value in env.rig.emu.writes:
        if RC.G_RAND_SEED <= addr < RC.G_RAND_SEED + 4:
            continue
        if any(b <= addr < b + n for b, n in world.pool_size.items()) or any(lo <= addr < hi for lo, hi in skip):
            continue
        entry = (pc, re.sub(r'^(player|mob|prop)\d', r'\1', world.name_of(addr & ~3)))
        if entry[1].startswith('weapon item'):
            entry = (pc & ~0xFFF, 'weapon item (entry slots)')
        if entry not in row:
            row.append(entry)


def scenario(name, sid):
    def register(fn):
        SCENARIOS.append((name, sid, fn))
        return fn
    return register



# ---- shared machinery ----------------------------------------------------------------------
@scenario('s00 machinery', 0)
def machinery(env, rounds):
    """The object constructors, the projectile step on a plain projectile, attaching spells
    and finding them by class."""
    world, mem, rng = env.world, env.mem, env.rng
    blocks = world.add_pool(0x60, 3, 'object')
    spells = world.add_pool(0x1C, 3, 'spell')
    class_def = env.rig.emu.alloc(0x60)
    for env.round in range(rounds * 3):
        world.place(rng)
        obj = rng.choice(blocks)
        for off in range(0, 0x60, 4):
            mem.w32(obj + off, 0)
        pos = env.pos_of(world.player, spread=rng.choice((50.0, 50.0, 40000.0)))
        definition = 0
        if rng.random() < 0.4:                                  # a class definition: lump, generation, names
            definition = class_def
            mem.w32(class_def, 0x00D20000)
            mem.w32(class_def + 4, rng.choice((7, 7, 3)))
            names = rng.choice((0, 1, 3))
            for k in range(4):
                mem.w32(class_def + 8 + 8 * k, 0x00D20100 + 16 * k if k < names else 0)
                mem.w32(class_def + 12 + 8 * k, 0)
        if rng.random() < 0.5:
            env.do('GameObject_ctor', obj, pos, definition, 0)
        else:
            owner = rng.choice((0, world.player, world.monster, world.mobs[0]))
            env.do('Projectile_ctor', obj, pos, owner, definition)
            mem.w32(obj + 0x48, world.vt_prop)                 # a projectile whose slot 6 is a stub
            mem.wf32(obj + 0x20, rng.choice((72.0, 12.0)))
            for mob in world.mobs[:3]:
                world.put(mob, pos, rng.uniform(-30, 30), rng.uniform(-30, 30), rng.choice((0.0, 0.0, 60.0, -90.0)))
            world.ground_bias = rng.choice((0.0, 0.3, 0.9))
            for _ in range(rng.choice((1, 2, 4))):
                mem.w8(obj + 0x50, rng.choice((0, 0, 1)))
                velocity = (f32(rng.uniform(-600, 600)), f32(rng.uniform(-600, 600)), f32(rng.choice((0.0, -50.0, 50.0))))
                env.do('obj_moveAndCollide', obj, velocity)
            world.ground_bias = 0.08
        # spells on a creature: the real classes' tables, so that their getters run
        creature = rng.choice(world.mobs + world.players)
        known = SPELL_TABLES[:FIRST_PASS_SPELL_TABLES]          # the classes of the first pass: its choices stay as they were
        tables = [rng.choice(known) for _ in spells]
        for spell, table in zip(spells, tables):
            mem.w32(spell + 0x14, table)
        world.spell_list(creature, spells[:rng.choice((0, 1, 2, 3))])
        if rng.random() < 0.2:
            mem.w32(world.nodes[spells[0]] + 0xC, 0)            # a node whose spell is gone
        getter = mem.u32(rng.choice(known) + 4)
        env.do('creature_findSpellByType', creature, env.rig.type_info[getter])
        mem.w32(world.nodes[spells[0]] + 0xC, spells[0])
        env.do('creature_addSpell', creature, rng.choice((0, spells[2])))


# ---- skill 4 ---------------------------------------------------------------------------
def add_skill(sid, name, bodies, entries, object_tables=(), spell_tables=()):
    SKILL_NAMES[sid] = name
    for key, (start, end) in bodies.items():
        BODIES[key] = (start, end, sid)
    ENTRIES.update(entries)
    OBJECT_TABLES.extend(object_tables)
    SPELL_TABLES.extend(spell_tables)


add_skill(4, 'diseasebolt', {
    'SkillDiseaseBolt_cast': (0x2CB1C0, 0x2CB264), 'DiseaseBolt_ctor': (0x2C9EB0, 0x2CA09C),
    'DiseaseBolt_run': (0x2CA1A8, 0x2CAEC8), 'DiseaseBolt_onHit': (0x2CAEC8, 0x2CB0E0),
    'SkillDiseaseBolt_manaCost': (0x2CB33C, 0x2CB368),
}, {
    'SkillDiseaseBolt_canUse': (0x2CB368, 'ii', 'i', 'diseasebolt_can_use'),
    'SkillDiseaseBolt_manaCost': (0x2CB33C, 'ii', 'f', 'diseasebolt_mana_cost'),
    'SkillDiseaseBolt_cast': (0x2CB1C0, 'iiivi', 'i', 'diseasebolt_cast'),
    'DiseaseBolt_run': (0x2CA1A8, 'i', 'n', 'diseasebolt_run'),
    'DiseaseBolt_onHit': (0x2CAEC8, 'ii', 'n', 'diseasebolt_hit'),
}, object_tables=[0x5183D8])


def line_up(env, caster, facing, objs, near=40.0, far=330.0):
    """Put some objects on (or near) the line the caster faces along."""
    world, mem, rng = env.world, env.mem, env.rng
    cos, sin = fl(C.cos16(C.s16(facing))), fl(C.sin16(C.s16(facing)))
    for obj in objs:
        d = rng.uniform(near, far)
        side = rng.choice((0.0, 0.0, 5.0, -8.0, 30.0, -60.0))
        mem.wf32(obj + 0x10, mem.f32(caster + 0x10) + cos * d - sin * side)
        mem.wf32(obj + 0x14, mem.f32(caster + 0x14) + sin * d + cos * side)
        mem.wf32(obj + 0x18, mem.f32(caster + 0x18) + rng.choice((0.0, 0.0, 0.0, 20.0, -30.0)))


def facing_arg(rng):
    return rng.choice((rng.randrange(0x10000), rng.randrange(0x10000), 0xFFFF8000 | rng.randrange(0x8000)))


def fly(env, key, obj, frames, on_tick=None):
    """Run a projectile (or any every-frame object) until it deletes itself."""
    for tick in range(frames):
        env.advance()
        if on_tick is not None:
            on_tick(tick)
        result = env.do(key, obj)
        if env.deleted(result, obj) or result['fault'] or result['both_fault'] is not None:
            return tick
    return frames


@scenario('s04 diseasebolt', 4)
def s04(env, rounds):
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(4)
    bolt = world.add_pool(0x7C, 1, 'bolt')[0]
    for level in (1, 2, 3, 4, 5, 10, 20, 21, 30, 40):
        env.do('SkillDiseaseBolt_manaCost', skill, level)
    for env.round in range(rounds):
        world.place(rng)
        caster = env.caster()
        facing = facing_arg(rng)
        line_up(env, caster, facing, rng.sample(world.mobs, 3) + [world.players[1], world.props[0]])
        for mob in rng.sample(world.mobs, 2):
            world.enemy(mob)
        world.enemy_bias = rng.choice((0.2, 0.8, 1.0))
        env.do('SkillDiseaseBolt_canUse', skill, caster)
        mem.w32(bolt + 0x48, 0)
        world.fail_alloc = 0.05
        env.do('SkillDiseaseBolt_cast', skill, env.level(), caster, env.pos_of(caster, 4.0, 40.0), facing)
        world.fail_alloc = 0.0
        if not mem.u32(bolt + 0x48):
            continue
        env.alive(bolt)
        mode = rng.choice(('fly', 'fly', 'fly', 'expire', 'orphan', 'hits'))
        world.ground_bias = 0.0 if mode == 'expire' else rng.choice((0.0, 0.02, 0.1))

        def tick(n):
            if mode == 'expire' and n == 12:
                env.advance(rng.choice((270, 286, 287, 288, 289)))       # near the natural end
            if mode == 'orphan' and n == 3:                               # the owner is deleted: handles empty
                mem.w32(bolt + 0x4C, 0)
                mem.w32(bolt + 0x54, 0)
            if n == 5 and rng.random() < 0.3:                             # the owner dies
                mem.w32(caster + 0xC, mem.u32(caster + 0xC) | 8)
            if n == 8 and rng.random() < 0.3:                             # the target is re-made or goes away
                mem.w32(bolt + 0x58, rng.choice((0, world.nodes[rng.choice(world.mobs)])))

        if mode == 'hits':                                               # the hit handler on its own
            for _ in range(12):
                mem.w32(bolt + 0x78, rng.choice((0, 0, 0, 1)))
                if rng.random() < 0.3:
                    mem.w32(bolt + 0x54, rng.choice((0, world.nodes[caster])))
                    mem.w32(bolt + 0x4C, rng.choice((0, world.nodes[caster], world.nodes[world.monster])))
                env.do('DiseaseBolt_onHit', bolt, rng.choice(world.everything))
        else:
            fly(env, 'DiseaseBolt_run', bolt, 60, tick)
    world.ground_bias, world.enemy_bias = 0.08, 0.7


@scenario('s04 diseasebolt expiry boundaries', 4)
def s04_expiry(env, _rounds):
    """Keep movement collision-free, then compare the last live and first expired frame."""
    world, mem = env.world, env.mem
    skill = env.skill(4)
    bolts = world.add_pool(0x7C, 1, 'expiry bolt')
    world.place(env.rng)
    world.fail_alloc = world.ground_bias = world.extra_bias = 0.0
    caster = world.player
    mem.w32(SA.G_SIM_FRAME, 1000)
    env.do('SkillDiseaseBolt_cast', skill, 20, caster, env.pos_of(caster, 0.0, 40.0), 0)
    bolt = bolts[0]
    assert mem.u32(bolt + 0x70) == 1300
    assert mem.s16(bolt + 0x60) == 20
    env.alive(bolt)
    mem.w32(bolt + 0x58, 0)
    for obj in world.everything:
        mem.wf32(obj + 0x10, 100000.0)
        mem.wf32(obj + 0x14, 100000.0)
    mem.w32(SA.G_SIM_FRAME, 1299)
    assert not env.deleted(env.do('DiseaseBolt_run', bolt), bolt)
    mem.w32(SA.G_SIM_FRAME, 1300)
    assert env.deleted(env.do('DiseaseBolt_run', bolt), bolt)

    # A ground contact ends a bolt with a future timer.
    mem.w32(SA.G_SIM_FRAME, 2000)
    env.do('SkillDiseaseBolt_cast', skill, 2, caster, env.pos_of(caster, 0.0, 40.0), 0)
    bolt = bolts[0]
    assert mem.u32(bolt + 0x70) == 2300
    env.alive(bolt)
    mem.w32(bolt + 0x58, 0)
    world.ground_bias = 1.0
    assert env.deleted(env.do('DiseaseBolt_run', bolt), bolt)

    # Contact with bit 1 from moveAndCollide ends only after the hit latch is set.
    world.ground_bias = 0.0
    mem.w32(SA.G_SIM_FRAME, 3000)
    env.do('SkillDiseaseBolt_cast', skill, 5, caster, env.pos_of(caster, 0.0, 40.0), 0)
    bolt = bolts[0]
    env.alive(bolt)
    mem.w32(bolt + 0x58, 0)
    world.enemy_bias = 0.0
    prop = world.props[0]
    mem.w32(prop + 0xC, 0)
    for off in (0x10, 0x14, 0x18):
        mem.w32(prop + off, mem.u32(bolt + off))
    assert not env.deleted(env.do('DiseaseBolt_run', bolt), bolt)
    mem.w32(bolt + 0x78, 1)
    assert env.deleted(env.do('DiseaseBolt_run', bolt), bolt)



# ---- skill 7 ---------------------------------------------------------------------------
add_skill(7, 'firestorm', {
    'SkillFireStorm_canUse': (0x2D532C, 0x2D542C), 'SkillFireStorm_cast': (0x2D4F7C, 0x2D510C),
    'FireStorm_ctor': (0x2D41F8, 0x2D4480), 'FireStorm_ctor2': (0x2D4048, 0x2D41F8),
    'FireStorm_initCommon': (0x2D4480, 0x2D4664), 'FireStorm_run': (0x2D470C, 0x2D4E88),
}, {
    'SkillFireStorm_canUse': (0x2D532C, 'ii', 'i', 'firestorm_can_use'),
    'SkillFireStorm_cast': (0x2D4F7C, 'iiivi', 'i', 'firestorm_cast'),
    'FireStorm_ctor2': (0x2D4048, 'iiviiiif', 'n', 'firestorm_ctor2'),
    'FireStorm_run': (0x2D470C, 'i', 'n', 'firestorm_run'),
}, object_tables=[0x518C98])


def step_frames(env, obj, key, calls, end_at=None, multiple=15, on_tick=None):
    """Run an every-frame object with the frame counter moving in uneven steps that land
    on multiples of `multiple` often, and (with end_at) jumping to just before its end."""
    mem, rng = env.mem, env.rng
    for n in range(calls):
        frame = mem.u32(RC.G_SIM_FRAME)
        choice = rng.random()
        if end_at is not None and n == calls // 2:
            frame = (end_at() - rng.choice((62, 61, 60, 31, 30, 16, 2, 1, 0))) & M32
        elif choice < 0.45:
            frame += multiple - frame % multiple
        elif choice < 0.6:
            frame += 2 * multiple - frame % (2 * multiple)
        else:
            frame += rng.choice((1, 1, 2, 7))
        mem.w32(RC.G_SIM_FRAME, frame & M32)
        if on_tick is not None:
            on_tick(n)
        result = env.do(key, obj)
        if env.deleted(result, obj) or result['fault'] or result['both_fault'] is not None:
            return n
    return calls


@scenario('s07 firestorm', 7)
def s07(env, rounds):
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(7)
    storm = world.add_pool(0xB4, 1, 'storm')[0]
    world.add_pool(0xBC, 2, 'light')
    world.add_pool(0x6C, 1, 'flare')
    for env.round in range(rounds):
        world.place(rng)
        caster = env.caster()
        env.do('SkillFireStorm_canUse', skill, caster)
        mem.w32(storm + 0x48, 0)
        world.fail_alloc = 0.05
        facing = facing_arg(rng)
        if rng.random() < 0.75:
            pos = env.pos_of(caster, 4.0, 40.0)
            env.do('SkillFireStorm_cast', skill, env.level(), caster, pos, facing)
        else:
            for off in range(0, 0xB4, 4):
                mem.w32(storm + off, 0)
            env.do('FireStorm_ctor2', storm, rng.choice((caster, world.mobs[0])), env.pos_of(caster, 60.0),
                   rng.choice((24, 96, 200, 0)), rng.choice((0, 7, 40, 0xFFFFFFF7)), rng.choice((60, 240)),
                   rng.choice((15, 15, 7, 0)), f32(rng.choice((0.3, 0.8))))
        if not mem.u32(storm + 0x48):
            continue
        env.alive(storm)
        for mob in rng.sample(world.mobs, 3):
            world.enemy(mob)
            world.put(mob, world.geometry(env.rig.eview, storm)[:3] and tuple(mem.u32(storm + 0x10 + 4 * i) for i in range(3)),
                      rng.uniform(-40, 40), rng.uniform(-40, 40), rng.choice((0.0, -6.0, 20.0)))
        world.enemy_bias = rng.choice((0.3, 0.9, 1.0))

        def tick(n):
            if n == 20 and rng.random() < 0.3:                  # the owner is deleted
                mem.w32(storm + 0x4C, 0)
            if n == 9 and rng.random() < 0.3:                   # the owner dies (and stays)
                mem.w32(caster + 0xC, mem.u32(caster + 0xC) | 8)

        step_frames(env, storm, 'FireStorm_run', 40, end_at=lambda: mem.u32(storm + 0x90), on_tick=tick)
    world.fail_alloc, world.enemy_bias = 0.0, 0.7



# ---- skill 23 --------------------------------------------------------------------------
add_skill(23, 'shockoffrost', {
    'SkillShockOfFrost_cast': (0x2F8840, 0x2F88D0), 'ShockOfFrost_ctor': (0x2F7404, 0x2F7604),
    'ShockOfFrost_run': (0x2F77C0, 0x2F84E4), 'ShockOfFrost_onHit': (0x2F84E4, 0x2F8730),
    'FrostShard_ctor': (0x2F68E0, 0x2F6A18), 'FrostShard_run': (0x2F6B3C, 0x2F71AC),
    'FrostShard_onHit': (0x2F71AC, 0x2F7404),
}, {
    'SkillShockOfFrost_canUse': (0x2F8B24, 'ii', 'i', 'shockoffrost_can_use'),
    'SkillShockOfFrost_cast': (0x2F8840, 'iiivi', 'i', 'shockoffrost_cast'),
    'ShockOfFrost_run': (0x2F77C0, 'i', 'n', 'shockoffrost_run'),
    'ShockOfFrost_onHit': (0x2F84E4, 'ii', 'n', 'shockoffrost_hit'),
    'FrostShard_run': (0x2F6B3C, 'i', 'n', 'frostshard_run'),
    'FrostShard_onHit': (0x2F71AC, 'ii', 'n', 'frostshard_hit'),
}, object_tables=[0x51A838, 0x51A8C8])


@scenario('s23 shockoffrost', 23)
def s23(env, rounds):
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(23)
    bolt = world.add_pool(0xD0, 1, 'frost')[0]
    shards = world.add_pool(0x7C, 4, 'shard')
    world.add_pool(0x248, 4, 'debris')
    for env.round in range(max(rounds // 2, 2)):                 # the slowest functions of the range
        world.place(rng)
        caster = env.caster()
        facing = facing_arg(rng)
        line_up(env, caster, facing, rng.sample(world.mobs, 3) + [world.players[1], world.props[0]])
        for mob in rng.sample(world.mobs, 2):
            world.enemy(mob)
        world.enemy_bias = rng.choice((0.2, 0.8, 1.0))
        env.do('SkillShockOfFrost_canUse', skill, caster)
        mem.w32(bolt + 0x48, 0)
        for shard in shards:
            mem.w32(shard + 0x48, 0)
        world.fail_alloc = 0.04
        env.do('SkillShockOfFrost_cast', skill, env.level(), caster, env.pos_of(caster, 4.0, 40.0), facing)
        if not mem.u32(bolt + 0x48):
            continue
        env.alive(bolt)
        mode = rng.choice(('fly', 'fly', 'fly', 'expire', 'orphan', 'hits'))
        world.ground_bias = 0.0 if mode == 'expire' else rng.choice((0.0, 0.02, 0.1))

        def tick(n):
            if mode == 'expire' and n == 6:
                env.advance(rng.choice((110, 111, 112, 113)))
            if mode == 'orphan' and n == 2:                       # the owner is deleted: the first handle empties
                mem.w32(bolt + 0x4C, 0)                           # (the second is read without a test when shards are made)
            if n == 4 and rng.random() < 0.3:
                mem.w32(caster + 0xC, mem.u32(caster + 0xC) | 8)

        if mode == 'hits':
            for _ in range(12):
                if rng.random() < 0.3:
                    mem.w32(bolt + 0x4C, rng.choice((0, world.nodes[caster], world.nodes[world.monster])))
                env.do('ShockOfFrost_onHit', bolt, rng.choice(world.everything))
        else:
            fly(env, 'ShockOfFrost_run', bolt, 30, tick)
        # the shards the bolt left (or one made by hand)
        live = [s for s in shards if mem.u32(s + 0x48) == 0x51A8C8]
        for shard in live[:2]:
            env.alive(shard)
            if rng.random() < 0.4:
                for _ in range(8):
                    mem.w32(shard + 0x70, rng.choice((0, 0, 0, 1)))
                    mem.w32(shard + 0x78, rng.choice((0, world.mobs[0], world.mobs[1])))
                    if rng.random() < 0.3:
                        mem.w32(shard + 0x4C, rng.choice((0, world.nodes[caster])))
                    env.do('FrostShard_onHit', shard, rng.choice(world.everything))
            else:
                grown = rng.random() < 0.3

                def shard_tick(n):
                    if grown and n == 3:
                        env.advance(rng.choice((52, 53, 54, 55)))
                fly(env, 'FrostShard_run', shard, 20, shard_tick)
    world.ground_bias, world.enemy_bias, world.fail_alloc = 0.08, 0.7, 0.0



# ---- skill 16 --------------------------------------------------------------------------
add_skill(16, 'holystrike', {
    'SkillHolyStrike_cast': (0x2ECFCC, 0x2ED08C), 'HolyStrike_ctor': (0x2EBA48, 0x2EBC50),
    'HolyStrike_run': (0x2EBC50, 0x2ECAE8), 'HolyStrike_onHit': (0x2ECAE8, 0x2ECD90),
}, {
    'SkillHolyStrike_canUse': (0x2ED20C, 'ii', 'i', 'holystrike_can_use'),
    'SkillHolyStrike_cast': (0x2ECFCC, 'iiivi', 'i', 'holystrike_cast'),
    'HolyStrike_run': (0x2EBC50, 'i', 'n', 'holystrike_run'),
    'HolyStrike_onHit': (0x2ECAE8, 'ii', 'n', 'holystrike_hit'),
}, object_tables=[0x51A078])


@scenario('s16 holystrike', 16)
def s16(env, rounds):
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(16)
    bolt = world.add_pool(0x80, 1, 'strike')[0]
    world.add_pool(0xBC, 1, 'light')
    for env.round in range(rounds):
        world.place(rng)
        caster = env.caster()
        facing = facing_arg(rng)
        line_up(env, caster, facing, rng.sample(world.mobs, 3) + [world.players[1], world.props[0]])
        for mob in rng.sample(world.mobs, 2):
            world.enemy(mob, rng.choice((0x10, 0x10, 0)))
        world.enemy_bias = rng.choice((0.2, 0.8, 1.0))
        env.do('SkillHolyStrike_canUse', skill, caster)
        mem.w32(bolt + 0x48, 0)
        world.fail_alloc = 0.04
        env.do('SkillHolyStrike_cast', skill, env.level(), caster, env.pos_of(caster, 4.0, 40.0), facing)
        if not mem.u32(bolt + 0x48):
            continue
        env.alive(bolt)
        mode = rng.choice(('fly', 'fly', 'fly', 'expire', 'orphan', 'hits'))
        world.ground_bias = 0.0 if mode == 'expire' else rng.choice((0.0, 0.02, 0.1))

        def tick(n):
            if mode == 'expire' and n == 17:
                env.advance(rng.choice((160, 161, 162, 163)))
            if mode == 'orphan' and n == 2:
                mem.w32(bolt + 0x4C, 0)
                mem.w32(bolt + 0x54, 0)
            if n == 4 and rng.random() < 0.3:
                mem.w32(caster + 0xC, mem.u32(caster + 0xC) | 8)

        if mode == 'hits':
            for _ in range(12):
                mem.w32(bolt + 0x78, rng.choice((0, 0, 0, 1)))
                if rng.random() < 0.3:
                    mem.w32(bolt + 0x54, rng.choice((0, world.nodes[caster])))
                env.do('HolyStrike_onHit', bolt, rng.choice(world.everything))
        else:
            fly(env, 'HolyStrike_run', bolt, 40, tick)
    world.ground_bias, world.enemy_bias, world.fail_alloc = 0.08, 0.7, 0.0


# ---- skill 24 --------------------------------------------------------------------------
add_skill(24, 'poisonrain', {
    'SkillPoisonRain_cast': (0x2F9A3C, 0x2F9BD0), 'PoisonRain_ctor': (0x2F8F48, 0x2F9254),
    'PoisonRain_run': (0x2F9254, 0x2F9958),
}, {
    'SkillPoisonRain_canUse': (0x2F9DEC, 'ii', 'i', 'poisonrain_can_use'),
    'SkillPoisonRain_cast': (0x2F9A3C, 'iiivi', 'i', 'poisonrain_cast'),
    'PoisonRain_ctor': (0x2F8F48, 'iiivii', 'n', 'poisonrain_ctor'),
    'PoisonRain_run': (0x2F9254, 'i', 'n', 'poisonrain_run'),
}, object_tables=[0x51AA68])


@scenario('s24 poisonrain', 24)
def s24(env, rounds):
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(24)
    rain = world.add_pool(0x6C, 1, 'rain')[0]
    world.add_pool(0xBC, 2, 'light')
    for env.round in range(rounds):
        world.place(rng)
        caster = env.caster(('monster', 'monster', 'player'))
        env.do('SkillPoisonRain_canUse', skill, caster)
        mem.w32(rain + 0x48, 0)
        world.fail_alloc = 0.04
        if rng.random() < 0.7:
            env.do('SkillPoisonRain_cast', skill, env.level(), caster, env.pos_of(caster, 4.0, 40.0), facing_arg(rng))
        else:                                                    # as the monsters that build it themselves do
            for off in range(0, 0x6C, 4):
                mem.w32(rain + off, 0)
            env.do('PoisonRain_ctor', rain, env.level(), caster, env.pos_of(caster, 60.0), skill, rng.choice((0, 0x00D00020)))
        if not mem.u32(rain + 0x48):
            continue
        env.alive(rain)
        if caster == world.player:                               # tier 1 is zero: give the test something to run
            mem.wf32(rain + 0x54, rng.choice((0.0, 24.0, 36.5)))
            mem.w32(rain + 0x4C, mem.u32(RC.G_SIM_FRAME) + 90)
        centre = tuple(mem.u32(rain + 0x10 + 4 * i) for i in range(3))
        for mob in rng.sample(world.mobs, 3) + [world.players[1]]:
            world.enemy(mob) if mob in world.mobs else None
            world.put(mob, centre, rng.uniform(-30, 30), rng.uniform(-30, 30), rng.choice((0.0, -6.0, 20.0)))
        mem.w8(world.players[1] + 0x310, 0)

        def tick(n):
            if n == 20 and rng.random() < 0.3:
                mem.w32(rain + 0x64, 0)

        step_frames(env, rain, 'PoisonRain_run', 30, end_at=lambda: mem.u32(rain + 0x4C), multiple=30, on_tick=tick)
    world.fail_alloc = 0.0



# ---- the number-only skills: 2, 3, 19, 25, 27, 28, 30 ----------------------------------------
for _sid, _name in ((2, 'dodge'), (3, 'resistpoison'), (19, 'regeneration'), (25, 'diseaseweapons'), (27, 'hatebeam'),
                    (28, 'ballofhate'), (30, 'hateeffect')):
    SKILL_NAMES[_sid] = _name
BODIES.update({'SkillDodge_getStat0Fraction': (0x2E8AC0, 0x2E8B3C, 2), 'SkillDodge_manaCost': (0x2E8A88, 0x2E8AC0, 2),
               'SkillRegeneration_getStat0': (0x2F14F0, 0x2F1528, 19), 'SkillRegeneration_cast': (0x2F1440, 0x2F1468, 19),
               'Skill_cast_base (ids 2, 3, 25, 27, 28, 30)': (0x3C8220, 0x3C8248, 3),
               'Skill_canUse_base': (0x3C8218, 0x3C8220, 3), 'Skill_manaCost_base': (0x3C82A8, 0x3C82B8, 3)})
ENTRIES.update({
    'SkillDodge_getStat0Fraction': (0x2E8AC0, 'ii', 'f', 'dodge_fraction'),
    'SkillRegeneration_getStat0': (0x2F14F0, 'ii', 'i', 'regeneration_stat0'),
    'Skill_canUse (slot 1)': (None, 'ii', 'i', None),
    'Skill_cast (slot 2)': (None, 'iiivi', 'i', None),
})


class SlotEntry:
    """Calls through a Skill's own table: the address and the model method are looked up
    per skill (used for the slots every id has)."""

    def __init__(self, env, skill, slot):
        mem = env.mem
        table = mem.u32(skill + 0x60)
        self.fn = mem.u32(table + 8 * slot + 4)
        self.method = SA.SKILL_BODIES.get(self.fn)


@scenario('s02 passives and tables', 2)
def s_passive(env, rounds):
    """Ids 2, 3, 19, 25, 27, 28, 30 (and 9's cast): can-use, cast and the two helpers other
    code calls.  Their statistics and mana cost are in the exhaustive sweep."""
    world, mem, rng = env.world, env.mem, env.rng
    for env.round in range(rounds):
        world.place(rng)
        for sid in (2, 3, 9, 19, 25, 27, 28, 30):
            skill = env.skill(sid)
            caster = env.caster(('player', 'monster', 'copy', 'none'))
            for slot, key in ((1, 'Skill_canUse (slot 1)'), (2, 'Skill_cast (slot 2)')):
                entry = SlotEntry(env, skill, slot)
                ENTRIES[key] = (entry.fn, ENTRIES[key][1], 'i', entry.method)
                if slot == 1:
                    env.do(key, skill, caster)
                else:
                    env.do(key, skill, env.level(), caster, env.pos_of(world.player), facing_arg(rng))
        for sid in (2, 83):
            env.do('SkillDodge_getStat0Fraction', env.skill(sid), rng.choice((0, 0, 1, 2, 5, 12, 14, 20, 40)))
        env.do('SkillRegeneration_getStat0', env.skill(19), env.level())


# ---- skill 9 ---------------------------------------------------------------------------
add_skill(9, 'riposte', {
    'SkillRiposte_cast': (0x2DDB90, 0x2DDBB8), 'SkillRiposte_counterAttack': (0x2DDCCC, 0x2DE138),
}, {
    'SkillRiposte_counterAttack': (0x2DDCCC, 'iiii', 'n', 'riposte_counter_attack'),
})


@scenario('s09 riposte', 9)
def s09(env, rounds):
    world, mem, rng = env.world, env.mem, env.rng
    for env.round in range(rounds * 3):
        world.place(rng)
        defender = rng.choice((world.player, world.players[1], world.monster, world.mobs[0]))
        attacker = rng.choice(world.mobs + world.players)
        level = rng.choice((0, 1, 1, 3, 9, 10, 11, 20, 40))
        env.do('SkillRiposte_counterAttack', env.skill(rng.choice((9, 9, 82))), defender, attacker, level)


# ---- skill 21 --------------------------------------------------------------------------
add_skill(21, 'repulseundead', {
    'SkillRepulseUndead_cast': (0x2F4D34, 0x2F4FE4), 'damage_radial': (0x1EAD58, 0x1EB000),
}, {
    'SkillRepulseUndead_cast': (0x2F4D34, 'iiivi', 'i', 'repulse_cast'),
    'damage_radial': (0x1EAD58, 'iviiiiff', 'n', 'damage_radial'),
})


@scenario('s21 repulseundead', 21)
def s21(env, rounds):
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(21)
    world.add_pool(0xB0, 44, 'soul')
    world.add_pool(0xBC, 1, 'light')
    for env.round in range(rounds):
        world.place(rng)
        caster = env.caster(('player', 'player', 'monster', 'none'))
        origin = caster or world.player
        pos = env.pos_of(origin, 4.0, 40.0)
        for mob in rng.sample(world.mobs, 4):
            world.enemy(mob, rng.choice((0x10, 0x10, 0x10, 0)))
            world.put(mob, pos, rng.uniform(-150, 150), rng.uniform(-150, 150), rng.choice((0.0, -40.0, 20.0)))
        world.fail_alloc = rng.choice((0.0, 0.0, 0.05))
        env.do('SkillRepulseUndead_cast', skill, env.level(), caster, pos, facing_arg(rng))
        world.fail_alloc = 0.0
        # the radial damage on its own, with other flag words, minimums and attackers
        for _ in range(3):
            inner = rng.choice((0.0, 24.0, 72.0, 100.0))
            outer = inner + rng.choice((0.0, 0.5, 1.0, 40.0, 144.0))
            env.do('damage_radial', rng.choice((0, caster, world.mobs[0], world.props[0])), pos,
                   rng.choice((0, 30, 200, 0xFFFFFFFB)), rng.choice((0xA100900, 0x100900, 0x8000000, 0)),
                   rng.choice((0, 0, 5, 50)), rng.choice((0x40, 0, 0x20, 8)), f32(inner), f32(outer))



# ---- skills 31, 32 -----------------------------------------------------------------------
add_skill(31, 'clericroot (and 32 rangerroot)', {
    'SkillRoot_canUse': (0x2E6534, 0x2E6598), 'SkillRoot_cast': (0x2E6598, 0x2E6790),
    'SpellRoot_ctor': (0x2E68C8, 0x2E699C), 'SpellRoot_run': (0x2E699C, 0x2E7034),
}, {
    'SkillRoot_canUse': (0x2E6534, 'ii', 'i', 'root_can_use'),
    'SkillRoot_cast': (0x2E6598, 'iiivi', 'i', 'root_cast'),
    'SpellRoot_run': (0x2E699C, 'ivi', 'n', 'root_spell_run'),
}, spell_tables=[0x519B70])
SKILL_NAMES[32] = 'rangerroot (see 31)'


def spell_gone(result, spell):
    return any(c[0] == 'Spell.v1' and c[1][0] == spell for c in result['emu_calls'])


@scenario('s31 root (31, 32, 52, 85)', 31)
def s31(env, rounds):
    world, mem, rng = env.world, env.mem, env.rng
    spells = world.add_pool(0x34, 4, 'root')
    for env.round in range(rounds):
        world.place(rng)
        skill = env.skill(rng.choice((31, 31, 32, 32, 52, 85)))
        caster = env.caster(('player', 'player', 'monster', 'copy', 'none'))
        origin = caster or world.player
        facing = facing_arg(rng)
        line_up(env, origin, facing, world.mobs[:4] + [world.players[1]], 30.0, 200.0)
        for mob in rng.sample(world.mobs, 3):
            world.enemy(mob)
            mem.w16(mob + 0x314, rng.choice((0, 0, 0, 30, 0xFFF0)))
        world.enemy_bias = rng.choice((0.3, 0.9, 1.0))
        if caster:
            env.do('SkillRoot_canUse', skill, caster)
        for spell in spells:
            mem.w32(spell + 0x14, 0)
        for obj in world.everything:
            mem.w32(obj + 0x364, 0)
        world.fail_alloc = rng.choice((0.0, 0.0, 0.1))
        env.do('SkillRoot_cast', skill, env.level(), caster, env.pos_of(origin, 4.0, 40.0), facing)
        world.fail_alloc = 0.0
        live = [s for s in spells if mem.u32(s + 0x14) == 0x519B70]
        for spell in live[:2]:
            victim = mem.u32(spell + 0xC)
            if rng.random() < 0.3:                              # a player victim: the push-back branch
                victim = world.players[1]
                mem.w32(spell + 0xC, victim)
            jump = rng.choice((0, 0, 1))
            for n in range(60):
                if n == 3 and jump:
                    mem.wf32(spell + 0x18, rng.choice((0.48, 0.5, 0.502)))      # just before the roll
                if n == 40:
                    mem.wf32(spell + 0x18, mem.s32(spell + 0x20) + rng.choice((0.4, 0.5, 0.51)))    # near the end
                if rng.random() < 0.1:
                    world.put(victim, tuple(mem.u32(spell + 0x28 + 4 * i) for i in range(3)), rng.uniform(-20, 20), rng.uniform(-20, 20))
                result = env.do('SpellRoot_run', spell, env.pos_of(victim, 0.0, 36.0), mem.u16(victim + 0x38))
                if spell_gone(result, spell):
                    break
    world.enemy_bias = 0.7


# ---- skill 33 --------------------------------------------------------------------------
add_skill(33, 'rangercriticalhit', {
    'SkillCriticalHit_canUse': (0x2E7224, 0x2E7258), 'SkillCriticalHit_cast': (0x2E74B0, 0x2E7534),
    'SpellCriticalHit_ctor': (0x2E7988, 0x2E7ACC), 'SpellCriticalHit_run': (0x2E7ACC, 0x2E7F58),
    'SpellCriticalHit_setTint': (0x2E7F58, 0x2E7F7C), 'SkillCriticalHit_critBonusFor': (0x2E76C4, 0x2E7988),
}, {
    'SkillCriticalHit_canUse': (0x2E7224, 'ii', 'i', 'crit_can_use'),
    'SkillCriticalHit_cast': (0x2E74B0, 'iiivi', 'i', 'crit_cast'),
    'SpellCriticalHit_run': (0x2E7ACC, 'ivi', 'n', 'crit_spell_run'),
    'SkillCriticalHit_critBonusFor': (0x2E76C4, 'iii', 'f', 'crit_bonus_for'),
}, spell_tables=[0x519C28])


def set_alive(env, slots):
    env.mem.w32(SA.G_ALIVE_COUNT, len(slots))
    for i, slot in enumerate(slots):
        env.mem.w32(SA.G_ALIVE_LIST + 4 * i, slot)


@scenario('s33 criticalhit (33, 53, 81)', 33)
def s33(env, rounds):
    world, mem, rng = env.world, env.mem, env.rng
    spell = world.add_pool(0x5C, 1, 'crit')[0]
    other_spells = world.add_pool(0x1C, 3, 'spell')
    for env.round in range(rounds):
        world.place(rng, spread=rng.choice((60.0, 140.0, 500.0)))
        skill = env.skill(rng.choice((33, 33, 53, 81)))
        caster = env.caster(('player', 'player', 'monster'))
        set_alive(env, rng.choice(([0, 1, 2, 3], [0, 1, 2, 3], [1, 2, 3], [3, 0, 1], [0], [], [2, 2, 0])))
        # who carries the buff already
        for obj in world.everything:
            mem.w32(obj + 0x364, 0)
        carried = []
        for s in other_spells:
            mem.w32(s + 0x14, rng.choice((0x519C28, 0x519C28, AM.VT_SPELL_SUMMON)))
        for obj, s in zip(rng.sample(world.players, 3), other_spells):
            if rng.random() < 0.6:
                world.spell_list(obj, [s])
                carried.append(obj)
        env.do('SkillCriticalHit_canUse', skill, caster)
        for attacker in rng.sample(world.players, 2):
            env.do('SkillCriticalHit_critBonusFor', skill, attacker, rng.choice((0, 0, 1, 5, 12, 20)))
        mem.w32(spell + 0x14, 0)
        world.fail_alloc = 0.05
        result = env.do('SkillCriticalHit_cast', skill, env.level(), caster, env.pos_of(caster), 0)
        world.fail_alloc = 0.0
        if not mem.u32(spell + 0x14):
            continue
        for n in range(25):
            if n == 6:
                mem.wf32(spell + 0x18, rng.choice((2.5, 2.02, 1.99, 1.5, 1.01)))
            if n == 14:
                mem.wf32(spell + 0x18, rng.choice((1.0, 0.9, 0.05, 0.02)))
            result = env.do('SpellCriticalHit_run', spell, env.pos_of(caster, 0.0, 36.0), mem.u16(caster + 0x38))
            if spell_gone(result, spell):
                break



# ---- skills 12, 14, 26 (the weapon buffs) ------------------------------------------------------
add_skill(12, 'lightningweapons', {
    'SkillLightningWeapons_canUse': (0x2E34AC, 0x2E34E0), 'SkillLightningWeapons_cast': (0x2E3184, 0x2E3208),
    'SpellLightningWeapons_ctor': (0x2E24D8, 0x2E2AC4), 'SpellLightningWeapons_run': (0x2E2AC4, 0x2E3070),
}, {
    'SkillLightningWeapons_canUse': (0x2E34AC, 'ii', 'i', 'lightningweapons_can_use'),
    'SkillLightningWeapons_cast': (0x2E3184, 'iiivi', 'i', 'lightningweapons_cast'),
    'SpellLightningWeapons_run': (0x2E2AC4, 'ivi', 'n', 'lightningweapons_run'),
}, spell_tables=[0x5199D0])
add_skill(14, 'coldweapons', {
    'SkillColdWeapons_canUse': (0x2E616C, 0x2E61A0), 'SkillColdWeapons_cast': (0x2E5E44, 0x2E5EC8),
    'SpellColdWeapons_ctor': (0x2E4F94, 0x2E5578), 'SpellColdWeapons_run': (0x2E5578, 0x2E5D2C),
}, {
    'SkillColdWeapons_canUse': (0x2E616C, 'ii', 'i', 'coldweapons_can_use'),
    'SkillColdWeapons_cast': (0x2E5E44, 'iiivi', 'i', 'coldweapons_cast'),
    'SpellColdWeapons_run': (0x2E5578, 'ivi', 'n', 'coldweapons_run'),
}, spell_tables=[0x519B40])
add_skill(26, 'poisonweapons', {
    'SkillPoisonWeapons_canUse': (0x315BB0, 0x315BE4), 'SkillPoisonWeapons_cast': (0x315BE4, 0x315C84),
    'SpellPoisonWeapons_ctor': (0x315F54, 0x3164FC), 'SpellPoisonWeapons_run': (0x3164FC, 0x316A24),
}, {
    'SkillPoisonWeapons_canUse': (0x315BB0, 'ii', 'i', 'poisonweapons_can_use'),
    'SkillPoisonWeapons_cast': (0x315BE4, 'iiivi', 'i', 'poisonweapons_cast'),
    'SpellPoisonWeapons_run': (0x3164FC, 'ivi', 'n', 'poisonweapons_run'),
}, spell_tables=[0x51C278])


def give_weapons(env):
    """Items in every player's two weapon slots: entries of every type, thrown or not."""
    world, mem, rng = env.world, env.mem, env.rng
    for slot in range(4):
        rec = G_PLAYERS + slot * REC_SIZE
        active = rng.choice((0, 0, 1))
        mem.w8(rec + SA.REC_ACTIVE_SET, active)
        for which in range(3):
            item = world.items[2 * slot + (which & 1)] if rng.random() < 0.85 else 0
            addr = rec + (SA.REC_OFF_HAND if which == 2 else SA.REC_WEAPON_SETS + 4 * which)
            if which == 2 and item:
                item = world.items[2 * slot + 1]
            mem.w32(addr, item)
        for item in world.items[2 * slot:2 * slot + 2]:
            mem.w64(item + 8, rng.choice((0, 0, 0, 0x1000000, 0x40)))
            for k in range(4):
                kind = rng.choice((0xFFFF, 0xFFFF, 0xFFFF, 0x15, 0x16, 0x17, 0x18, 0x18, 0x16, 0x17, 3))
                mem.w16(item + 0x24 + 8 * k, kind)
                mem.w16(item + 0x26 + 8 * k, rng.choice((0, 5, 20, 30, 31, 45, 200, 2000, 0xFFFB)))
                mem.w16(item + 0x28 + 8 * k, rng.choice((0, 9, 60)))
                mem.w16(item + 0x2A + 8 * k, rng.choice((0, 12, 600)))


def weapon_buff(env, rounds, sid, name, table, size=0x24):
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(sid)
    spell = world.add_pool(size, 1, 'buff')[0]
    world.add_pool(0xBC, 1, 'light')
    other_spells = world.add_pool(0x1C, 2, 'spell')
    holder = world.holder
    for env.round in range(rounds):
        world.place(rng, spread=60.0)
        give_weapons(env)
        caster = env.caster(('player', 'player', 'monster'))
        mem.w32(world.monster + 0x50, rng.choice((0, holder, holder)))
        for obj in world.everything:
            mem.w32(obj + 0x364, 0)
        for s in other_spells:
            mem.w32(s + 0x14, rng.choice((table, AM.VT_SPELL_SUMMON)))
        if rng.random() < 0.3:
            world.spell_list(caster, other_spells[:rng.choice((1, 2))])
        env.do(name % 'Skill' + '_canUse', skill, caster)
        mem.w32(spell + 0x14, 0)
        world.fail_alloc = 0.05
        env.do(name % 'Skill' + '_cast', skill, rng.choice((0, 1, 3, 5, 6, 7, 12, 16, 20, 30)), caster, env.pos_of(caster), 0)
        if sid == 13:
            for item in world.items:
                world.names.setdefault(item, 'weapon item')
            note_stores(env, sid, 'cast')
        world.fail_alloc = 0.0
        if not mem.u32(spell + 0x14):
            continue
        end = mem.u32(spell + 0x18)
        for n in range(26):
            frame = mem.u32(RC.G_SIM_FRAME)
            if n == 20:
                frame = end - rng.choice((31, 30, 2, 1, 0))
            elif rng.random() < 0.5:
                frame += 30 - frame % 30
            else:
                frame += rng.choice((1, 1, 3, 11))
            mem.w32(RC.G_SIM_FRAME, frame & M32)
            if rng.random() < 0.2:
                give_weapons(env)
            if n == 12 and rng.random() < 0.3:
                mem.w32(caster + 0xC, mem.u32(caster + 0xC) | 8)       # the owner dies; the spell stays
            result = env.do(name % 'Spell' + '_run', spell, env.pos_of(caster, 0.0, 36.0), mem.u16(caster + 0x38))
            if spell_gone(result, spell):
                break


@scenario('s12 lightningweapons', 12)
def s12(env, rounds):
    weapon_buff(env, rounds, 12, '%sLightningWeapons', 0x5199D0)


@scenario('s14 coldweapons', 14)
def s14(env, rounds):
    weapon_buff(env, rounds, 14, '%sColdWeapons', 0x519B40)


@scenario('s26 poisonweapons', 26)
def s26(env, rounds):
    weapon_buff(env, rounds, 26, '%sPoisonWeapons', 0x51C278)



# ---- skill 29 --------------------------------------------------------------------------
add_skill(29, 'diseaseeffect', {
    'SpellDiseaseEffect_ctor': (0x2D5594, 0x2D5854), 'SpellDiseaseEffect_run': (0x2D5854, 0x2D5EC0),
}, {
    'SpellDiseaseEffect_ctor': (0x2D5594, 'iiiiii', 'n', 'disease_spell_ctor'),
    'SpellDiseaseEffect_run': (0x2D5854, 'ivi', 'n', 'disease_spell_run'),
}, spell_tables=[0x518DB0])


@scenario('s29 diseaseeffect', 29)
def s29(env, rounds):
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(29)
    spells = world.add_pool(0x1B0, 3, 'disease')
    held = world.add_pool(0x1C, 2, 'spell')
    for env.round in range(rounds):
        world.place(rng, spread=40.0)
        victim = rng.choice(world.mobs + world.players[1:])
        attacker = rng.choice((world.player, world.monster, world.mobs[1], world.props[0], 0))
        level = rng.choice((0, 0, 0, 3, 9, 30))
        seconds = rng.choice((5, 5, 4, 2, 1, 0, 0xFFFFFFFD))
        for obj in world.everything:
            mem.w32(obj + 0x364, 0)
        for s in held:                                          # some neighbours are diseased already
            mem.w32(s + 0x14, rng.choice((0x518DB0, AM.VT_SPELL_SUMMON)))
        for obj, s in zip(rng.sample(world.mobs, 2), held):
            if rng.random() < 0.5:
                world.spell_list(obj, [s])
        spell = spells[0]
        for off in range(0, 0x1B0, 4):
            mem.w32(spell + off, 0)
        env.do('SpellDiseaseEffect_ctor', spell, seconds, level, victim, attacker, skill)
        world.enemy_bias = rng.choice((0.3, 0.9, 1.0))
        for n in range(18):
            frame = mem.u32(RC.G_SIM_FRAME)
            if n == 12:
                frame = mem.u32(spell + 0x1A0) - rng.choice((31, 30, 2, 1, 0))
            elif rng.random() < 0.5:
                frame += 30 - frame % 30
            else:
                frame += rng.choice((1, 1, 3, 11))
            mem.w32(RC.G_SIM_FRAME, frame & M32)
            if n == 7 and rng.random() < 0.3:                   # the source is deleted: the handle empties
                mem.w32(spell + 0x18, 0)
            # pool_new starts again at the first block on every call: keep the running spell out of its way
            world.pool[0x1B0] = spells[1:]
            result = env.do('SpellDiseaseEffect_run', spell, env.pos_of(victim, 0.0, 36.0), mem.u16(victim + 0x38))
            world.pool[0x1B0] = spells
            if spell_gone(result, spell):
                break
    world.enemy_bias = 0.7



# ---- skill 11 (imported from tools/ref_arena_monsters.py) --------------------------------------
add_skill(11, 'summonskeleton', {
    'SkillSummonSkeleton_canUse': (0x2E2368, 0x2E23CC), 'SkillSummonSkeleton_cast': (0x2E18A4, 0x2E227C),
    'SpellSummonSkeleton_ctor': (0x2E16EC, 0x2E177C), 'SpellSummonSkeleton_run': (0x2E177C, 0x2E17D8),
}, {
    'SkillSummonSkeleton_canUse': (0x2E2368, 'ii', 'i', 'summon_can_use'),
    'SkillSummonSkeleton_cast': (0x2E18A4, 'iiivi', 'i', 'summon_cast'),
    'SpellSummonSkeleton_run': (0x2E177C, 'ivi', 'n', 'summon_spell_run'),
})


@scenario('s11 summonskeleton', 11)
def s11(env, rounds):
    """The cast and the spell as tools/ref_arena_monsters.py models them, with this file's
    real statistics underneath and the skeleton's constructor as a stub."""
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(11)
    world.add_pool(0x468, 1, 'skeleton')
    spell = world.add_pool(0x1C, 1, 'spell')[0]
    for env.round in range(rounds):
        world.place(rng)
        caster = env.caster(('player', 'player', 'monster'))
        if rng.random() < 0.2:
            mem.w32(world.player + 0x3C8, rng.choice((1, 3, 4, 7)))
        env.do('SkillSummonSkeleton_canUse', skill, caster)
        mem.w32(spell + 0x14, 0)
        world.fail_alloc = 0.06
        world.ground_bias = rng.choice((0.0, 0.5))
        env.do('SkillSummonSkeleton_cast', skill, rng.choice((0, 1, 4, 10, 11, 20, 0xFFFFFFFF)), caster,
               env.pos_of(caster, 4.0, 40.0), facing_arg(rng))
        world.fail_alloc, world.ground_bias = 0.0, 0.08
        mem.w32(world.player + 0x3C8, 0)
        if mem.u32(spell + 0x14):
            for _ in range(3):
                if rng.random() < 0.4:
                    mem.w32(spell + 0x18, 0)                    # the skeleton is gone
                env.do('SpellSummonSkeleton_run', spell, env.pos_of(caster), 0)



# ---- skill 20 --------------------------------------------------------------------------
add_skill(20, 'blindinglight', {
    'SkillBlindingLight_cast': (0x2F47DC, 0x2F4970), 'BlindingLightEffect_ctor': (0x2F3F38, 0x2F42E4),
    'BlindingLightEffect_run': (0x2F42E4, 0x2F4474), 'SpellBlindingLight_ctor': (0x2F4474, 0x2F4538),
    'SpellBlindingLight_run': (0x2F4538, 0x2F46F0),
}, {
    'SkillBlindingLight_canUse': (0x2F4B10, 'ii', 'i', 'blindinglight_can_use'),
    'SkillBlindingLight_cast': (0x2F47DC, 'iiivi', 'i', 'blindinglight_cast'),
    'BlindingLightEffect_run': (0x2F42E4, 'i', 'n', 'blindinglight_effect_run'),
    'SpellBlindingLight_run': (0x2F4538, 'ivi', 'n', 'blindinglight_spell_run'),
}, object_tables=[0x51A5E0], spell_tables=[0x51A6F8])


@scenario('s20 blindinglight', 20)
def s20(env, rounds):
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(20)
    effect = world.add_pool(0x54, 1, 'blind')[0]
    spells = world.add_pool(0x20, 4, 'blinded')
    world.add_pool(0xBC, 1, 'light')
    world.add_pool(0x5C, 1, 'shaft')
    for env.round in range(rounds):
        world.place(rng, spread=70.0)
        caster = env.caster(('player', 'player', 'monster', 'none'))
        origin = caster or world.player
        facing = facing_arg(rng)
        line_up(env, origin, facing, world.mobs[:4], 30.0, 120.0)
        for mob in rng.sample(world.mobs, 4):
            world.enemy(mob)
        world.enemy_bias = rng.choice((0.3, 0.9, 1.0))
        if caster:
            env.do('SkillBlindingLight_canUse', skill, caster)
        mem.w32(effect + 0x48, 0)
        for spell in spells:
            mem.w32(spell + 0x14, 0)
        for obj in world.everything:
            mem.w32(obj + 0x364, 0)
        world.fail_alloc = rng.choice((0.0, 0.0, 0.08))
        if caster:
            env.do('SkillBlindingLight_cast', skill, env.level(), caster, env.pos_of(origin, 4.0, 40.0), facing)
        world.fail_alloc = 0.0
        if mem.u32(effect + 0x48):
            env.alive(effect)
            for n in range(8):
                env.advance(rng.choice((1, 1, 20, 40)))
                result = env.do('BlindingLightEffect_run', effect)
                if env.deleted(result, effect):
                    break
        for spell in [s for s in spells if mem.u32(s + 0x14) == 0x51A6F8][:2]:
            victim = mem.u32(spell + 0xC)
            for n in range(14):
                frame = mem.u32(RC.G_SIM_FRAME)
                if n == 10:
                    frame = mem.u32(spell + 0x18) - rng.choice((30, 1, 0))
                elif rng.random() < 0.6:
                    frame += 30 - frame % 30
                else:
                    frame += rng.choice((1, 7))
                mem.w32(RC.G_SIM_FRAME, frame & M32)
                if rng.random() < 0.15:
                    mem.wf32(victim + 0x228, rng.choice((0.0, -3.0, 50.0)))
                result = env.do('SpellBlindingLight_run', spell, env.pos_of(victim), 0)
                if spell_gone(result, spell):
                    break
    world.enemy_bias = 0.7



# ---- skill 15 --------------------------------------------------------------------------
add_skill(15, 'undeadshield', {
    'SkillUndeadShield_canUse': (0x2EB970, 0x2EB9A4), 'SkillUndeadShield_cast': (0x2EB7CC, 0x2EB850),
    'SpellUndeadShield_ctor': (0x2EA4D8, 0x2EA6A4), 'SpellUndeadShield_run': (0x2EA74C, 0x2EAEC0),
    'SpellUndeadShield_damageAttacker': (0x2EAEC0, 0x2EB050), 'SpellSecondaryUndeadShield_ctor': (0x2EB050, 0x2EB0FC),
    'SpellSecondaryUndeadShield_run': (0x2EB170, 0x2EB5B4), 'SpellSecondaryUndeadShield_damageAttacker': (0x2EB5B4, 0x2EB704),
}, {
    'SkillUndeadShield_canUse': (0x2EB970, 'ii', 'i', 'undeadshield_can_use'),
    'SkillUndeadShield_cast': (0x2EB7CC, 'iiivi', 'i', 'undeadshield_cast'),
    'SpellUndeadShield_run': (0x2EA74C, 'ivi', 'n', 'undeadshield_run'),
    'SpellUndeadShield_damageAttacker': (0x2EAEC0, 'iiii', 'n', 'undeadshield_damage_attacker'),
    'SpellSecondaryUndeadShield_run': (0x2EB170, 'ivi', 'n', 'secondary_shield_run'),
    'SpellSecondaryUndeadShield_damageAttacker': (0x2EB5B4, 'iiii', 'n', 'secondary_shield_damage_attacker'),
}, spell_tables=[0x51A048, 0x51A018])


@scenario('s15 undeadshield', 15)
def s15(env, rounds):
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(15)
    shield = world.add_pool(0x64, 1, 'shield')[0]
    seconds = world.add_pool(0x24, 3, 'secondary')
    held = world.add_pool(0x1C, 2, 'spell')
    for env.round in range(rounds):
        world.place(rng, spread=60.0)
        caster = env.caster(('player', 'player', 'monster'))
        for obj in world.everything:
            mem.w32(obj + 0x364, 0)
        for s in held:
            mem.w32(s + 0x14, rng.choice((0x51A048, 0x51A018, AM.VT_SPELL_SUMMON)))
        for obj, s in zip(rng.sample(world.players, 2), held):
            if rng.random() < 0.5:
                world.spell_list(obj, [s])
        env.do('SkillUndeadShield_canUse', skill, caster)
        mem.w32(shield + 0x14, 0)
        for s in seconds:
            mem.w32(s + 0x14, 0)
        world.fail_alloc = 0.05
        env.do('SkillUndeadShield_cast', skill, rng.choice((0, 1, 3, 9, 20)), caster, env.pos_of(caster), 0)
        if not mem.u32(shield + 0x14):
            world.fail_alloc = 0.0
            continue
        end = mem.u32(shield + 0x18)
        for n in range(22):
            frame = mem.u32(RC.G_SIM_FRAME)
            if n == 16:
                frame = end - rng.choice((16, 15, 2, 1, 0))
            elif rng.random() < 0.5:
                frame += 15 - frame % 15
            else:
                frame += rng.choice((1, 1, 3, 11, 40))
            mem.w32(RC.G_SIM_FRAME, frame & M32)
            if rng.random() < 0.3:
                attacker = rng.choice(world.mobs)
                env.do('SpellUndeadShield_damageAttacker', shield, caster, attacker, rng.choice((0, 1, 7, 40, 333, 0xFFFFFFF0)))
            result = env.do('SpellUndeadShield_run', shield, env.pos_of(caster, 0.0, 36.0), mem.u16(caster + 0x38))
            if spell_gone(result, shield):
                break
        world.fail_alloc = 0.0
        for second in [s for s in seconds if mem.u32(s + 0x14) == 0x51A018][:2]:
            victim = mem.u32(second + 0xC)
            for n in range(6):
                env.advance(rng.choice((1, 5, 12, 29)))
                if rng.random() < 0.4:
                    env.do('SpellSecondaryUndeadShield_damageAttacker', second, victim, rng.choice(world.mobs),
                           rng.choice((0, 9, 120)))
                result = env.do('SpellSecondaryUndeadShield_run', second, env.pos_of(victim), 0)
                if spell_gone(result, second):
                    break



# ---- can-use of the ids whose casts came in later passes: 1, 5, 6, 8, 10, 13, 17, 18, 22 --------------
for _sid, _name in ((1, 'wizardbeam'), (5, 'diseaseshield'), (6, 'diseasetrail'), (8, 'fireflares'), (10, 'blessed'),
                    (13, 'fireweapons'), (17, 'hammerofwrath'), (18, 'coneoffire'), (22, 'dismissundead'), (34, 'shieldbash')):
    SKILL_NAMES[_sid] = _name
BODIES.update({'SkillDiseaseShield_canUse': (0x2CE2B0, 0x2CE2E4, 5), 'SkillDiseaseTrail_canUse': (0x2CCE28, 0x2CCE5C, 6),
               'SkillFireFlares_canUse': (0x2DD8B8, 0x2DD8EC, 8), 'SkillBlessed_canUse': (0x2E000C, 0x2E0040, 10),
               'SkillFireWeapons_canUse': (0x2E4DF8, 0x2E4E2C, 13), 'SkillHammerOfWrath_canUse': (0x2EFEF8, 0x2EFF2C, 17),
               'SkillConeOfFire_canUse': (0x2F123C, 0x2F1244, 18)})


@scenario('s05 can-use of the rest', 5)
def s_canuse(env, rounds):
    """Ids 1, 5, 6, 8, 10, 13, 17, 18 and 22: can-use only, the prediction copy among the
    casters (their statistics and mana cost are in the sweep; their casts and effects have
    their own scenarios further down, from the second and third pass)."""
    world, mem, rng = env.world, env.mem, env.rng
    held = world.add_pool(0x1C, 3, 'spell')
    tables = {}
    for sid, getter in env.rig.carry.items():                  # a stand-in spell of each class: only slot 0 matters
        table = env.rig.emu.alloc(0x40)
        mem.w32(table + 4, getter)
        tables[sid] = table
    for env.round in range(rounds):
        world.place(rng)
        for sid in (1, 5, 6, 8, 10, 13, 17, 18, 22):
            skill = env.skill(sid)
            caster = env.caster(('player', 'monster', 'copy'))
            mem.w32(caster + 0x364, 0)
            for spell in held:
                mem.w32(spell + 0x14, tables[rng.choice([sid] if sid in tables else list(tables)) if rng.random() < 0.5
                                             else rng.choice(list(tables))])
            world.spell_list(caster, held[:rng.choice((0, 0, 1, 2, 3))])
            entry = SlotEntry(env, skill, 1)
            ENTRIES['Skill_canUse (slot 1)'] = (entry.fn, 'ii', 'i', 'can_use_slot')
            env.do('Skill_canUse (slot 1)', skill, caster)
            if caster == world.copy:
                note_stores(env, sid, 'can-use, copy')
            mem.w32(caster + 0x364, 0)


# ==== the second pass: the casts and effects of ids 1, 5, 6, 8, 10, 13, 17, 18, 22, 34 =================
FIRST_PASS_SPELL_TABLES = len(SPELL_TABLES)


# ---- skill 13 (the fourth weapon buff) ---------------------------------------------------------
add_skill(13, 'fireweapons', {
    'SkillFireWeapons_cast': (0x2E4AD0, 0x2E4B54),
    'SpellFireWeapons_ctor': (0x2E34E0, 0x2E3A98), 'SpellFireWeapons_run': (0x2E3B28, 0x2E49C0),
}, {
    'SkillFireWeapons_canUse': (0x2E4DF8, 'ii', 'i', 'fireweapons_can_use'),
    'SkillFireWeapons_cast': (0x2E4AD0, 'iiivi', 'i', 'fireweapons_cast'),
    'SpellFireWeapons_run': (0x2E3B28, 'ivi', 'n', 'fireweapons_run'),
}, spell_tables=[0x519A88])


@scenario('s13 fireweapons', 13)
def s13(env, rounds):
    weapon_buff(env, rounds, 13, '%sFireWeapons', 0x519A88, size=0x60)


# ---- skill 18 --------------------------------------------------------------------------
add_skill(18, 'coneoffire', {
    'SkillConeOfFire_cast': (0x2F1078, 0x2F10FC), 'SpellConeOfFire_ctor': (0x2F00AC, 0x2F0224),
    'SpellConeOfFire_run': (0x2F02FC, 0x2F0F94),
}, {
    'SkillConeOfFire_canUse': (0x2F123C, 'ii', 'i', 'coneoffire_can_use'),
    'SkillConeOfFire_cast': (0x2F1078, 'iiivi', 'i', 'coneoffire_cast'),
    'SpellConeOfFire_ctor': (0x2F00AC, 'iiii', 'n', 'coneoffire_ctor'),
    'SpellConeOfFire_run': (0x2F02FC, 'ivi', 'n', 'coneoffire_run'),
}, spell_tables=[0x51A470])


@scenario('s18 coneoffire', 18)
def s18(env, rounds):
    """Cast (and the constructor as the Mummy calls it), then the channel held for a
    number of frames, most of them damage ticks.  The descriptors handed to damage_apply
    are collected for the SA4 property."""
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(18)
    spell = world.add_pool(0x58, 1, 'cone')[0]
    seen = {}                                                   # (player owner, level) -> descriptors
    for env.round in range(rounds):
        world.place(rng, spread=70.0)
        caster = env.caster(('player', 'player', 'monster', 'monster'))
        facing = facing_arg(rng)
        line_up(env, caster, facing, world.mobs[:4] + [world.players[1]], 20.0, 110.0)
        for mob in rng.sample(world.mobs, 4):
            world.enemy(mob)
        world.enemy_bias = rng.choice((0.3, 0.9, 1.0))
        env.do('SkillConeOfFire_canUse', skill, caster)
        mem.w32(spell + 0x14, 0)
        world.fail_alloc = 0.05
        level = rng.choice((0, 1, 2, 2, 3, 3, 4, 5, 10, 11, 20, 40))
        if rng.random() < 0.7:
            env.do('SkillConeOfFire_cast', skill, level, caster, env.pos_of(caster), facing)
        else:                                                   # as the Mummy builds it (0x299c68)
            for off in range(0, 0x58, 4):
                mem.w32(spell + off, 0)
            env.do('SpellConeOfFire_ctor', spell, level, caster, skill)
        note_stores(env, 18, 'cast')
        world.fail_alloc = 0.0
        if not mem.u32(spell + 0x14):
            continue
        for n in range(14):
            frame = mem.u32(RC.G_SIM_FRAME)
            frame += 15 - frame % 15 if rng.random() < 0.6 else rng.choice((1, 1, 2, 7))
            mem.w32(RC.G_SIM_FRAME, frame & M32)
            if n == 9 and rng.random() < 0.3:
                mem.w32(caster + 0xC, mem.u32(caster + 0xC) | 8)       # the owner dies; the channel is still run
            if rng.random() < 0.3:
                facing = (facing + rng.choice((300, -700, 0x4000))) & 0xFFFF
            result = env.do('SpellConeOfFire_run', spell, env.pos_of(caster, 0.0, 36.0), facing)
            for name, args in result['emu_calls']:
                if name == 'damage_apply':
                    seen.setdefault((caster == world.player, level), set()).add(args[6])
    world.enemy_bias = 0.7
    # SA4: what Cone of Fire hands to damage_apply
    bad, count, zero_divisor = [], 0, 0
    for (is_player, level), descs in sorted(seen.items()):
        for desc in descs:
            count += 1
            entry = desc[1] if desc[0] == 'desc' else None
            if entry is None or desc[2:] != (None, None, None) or entry[0] != 0x15 or entry[3] != 0:
                bad.append('level %d: %r' % (level, desc))
                continue
            v1, v2 = C.s16(entry[1]), C.s16(entry[2])
            if v1 > 0 and not v2 < v1 or not v1 * 0.25 - 1 < v2 <= v1 * 0.3:
                bad.append('level %d: v1 %d v2 %d' % (level, v1, v2))
            if v2 - v1 + 1 == 0:
                zero_divisor += 1
                if is_player or level not in (2, 3):
                    bad.append('level %d (%s): divisor 0' % (level, 'player' if is_player else 'monster'))
            elif not is_player and level in (2, 3):
                bad.append('monster level %d: %r' % (level, entry))
    report('s18 coneoffire SA4 descriptor', len(bad), count,
           'fire entry (0x15, v1, v2, 0) with v2 = (v1 + spread) x 0.25 < v1; v2 - v1 + 1 = 0 in %d (monster owner, level 2 or 3)'
           % zero_divisor, bad)


# ---- skill 17 --------------------------------------------------------------------------
add_skill(17, 'hammerofwrath', {
    'SkillHammerOfWrath_cast': (0x2EFB20, 0x2EFD44), 'HammerOfWrath_ctor': (0x2EDD78, 0x2EDFD0),
    'HammerOfWrath_run': (0x2EE068, 0x2EF78C), 'SpellHammerOfWrath_ctor': (0x2EF974, 0x2EFA04),
    'SpellHammerOfWrath_run': (0x2EFA04, 0x2EFA60),
}, {
    'SkillHammerOfWrath_canUse': (0x2EFEF8, 'ii', 'i', 'hammer_can_use'),
    'SkillHammerOfWrath_cast': (0x2EFB20, 'iiivi', 'i', 'hammer_cast'),
    'HammerOfWrath_run': (0x2EE068, 'i', 'n', 'hammer_run'),
    'SpellHammerOfWrath_run': (0x2EFA04, 'ivi', 'n', 'hammer_spell_run'),
}, object_tables=[0x51A2A0], spell_tables=[0x51A3B8])
# item_parseDescriptor, item_randomizeVariant and item_getResourceIndex run for real (the model side is tools/ref_items.py)
EXTRA_PARTIAL.extend([(0x1069B8, 0x107CA8), (0x1046E0, 0x104758), (0x1083F8, 0x108434)])


@scenario('s17 hammerofwrath', 17)
def s17(env, rounds):
    """Cast (shaft, light, hammer with its parsed item record, spell), the spell's run, and
    the hammer's run through its states: following, the strike (blow at c = 47), the spin
    (blows at c = 80, 100, 120), cutscenes, a blocking owner, targets dying or deleted, the
    owner far away or deleted, and the last frames with their rising particle count."""
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(17)
    hammer = world.add_pool(0xE8, 1, 'hammer')[0]
    spell = world.add_pool(0x1C, 1, 'hammerspell')[0]
    world.add_pool(0x5C, 1, 'shaft')
    world.add_pool(0xBC, 1, 'light')
    held = [env.rig.emu.alloc(0x20) for _ in range(2)]
    for s in held:
        world.names[s] = 'held'
        world.add_node(s)
    seen = {}                                                   # level argument -> (stored level, shared draws of the cast)
    # item_parseDescriptor builds the record in its own frame and copies all 0x48 bytes out: the bytes it never sets
    # (+6, +0x22, the values of the three empty slots, +0x44) are whatever its stack held - not compared
    env.rig.masked = {hammer + 0x58 + off for off in [6, 7, 0x22, 0x23, 0x44, 0x45, 0x46, 0x47]
                      + [0x26 + 8 * k + i for k in (1, 2, 3) for i in range(6)]}
    for env.round in range(rounds):
        world.place(rng, spread=120.0)
        caster = env.caster(('player', 'player', 'player', 'monster'))
        for obj in world.everything:
            mem.w32(obj + 0x364, 0)
        for s in held:
            mem.w32(s + 0x14, rng.choice((0x51A3B8, AM.VT_SPELL_SUMMON)))
        if rng.random() < 0.3:
            world.spell_list(caster, held[:rng.choice((1, 2))])
        env.do('SkillHammerOfWrath_canUse', skill, caster)
        mem.w32(caster + 0x364, 0)
        mem.w32(hammer + 0x48, 0)
        mem.w32(spell + 0x14, 0)
        mem.w8(SA.G_HAMMER_COUNT, rng.choice((0, 1, 0xFF)))
        world.fail_alloc = 0.05
        level = rng.choice((0, 1, 2, 3, 4, 5, 9, 10, 19, 20, 40, 0xFFFFFFFF))
        facing = facing_arg(rng)
        result = env.do('SkillHammerOfWrath_cast', skill, level, caster, env.pos_of(caster, 4.0), facing)
        note_stores(env, 17, 'cast')
        world.fail_alloc = 0.0
        if mem.u32(hammer + 0x48):
            seen.setdefault(level, set()).add((mem.u32(hammer + 0xA4), result['draws'], bool(mem.u32(spell + 0x14))))
        if mem.u32(spell + 0x14):
            env.do('SpellHammerOfWrath_run', spell, env.pos_of(caster), 0)
            if rng.random() < 0.5:
                mem.w32(spell + 0x18, 0)                        # the hammer is gone
                env.do('SpellHammerOfWrath_run', spell, env.pos_of(caster), 0)
        if not mem.u32(hammer + 0x48):
            continue
        env.alive(hammer)
        for mob in rng.sample(world.mobs, 4):
            world.enemy(mob)
            world.put(mob, tuple(mem.u32(caster + 0x10 + 4 * i) for i in range(3)), rng.uniform(-150, 150),
                      rng.uniform(-150, 150), rng.choice((0.0, 0.0, 30.0)))
        world.enemy_bias = rng.choice((0.3, 0.9, 1.0))
        mode = rng.choice(('strike', 'spin', 'free', 'free', 'end'))
        if mode == 'end':
            mem.w32(hammer + 0xA8, rng.choice((125, 121, 90, 40, 8)))
        for n in range(44):
            env.advance(rng.choice((1, 1, 1, 3)))
            state, c = mem.u32(hammer + 0xC8), mem.u32(hammer + 0xA0)
            if n == 4 and mode in ('strike', 'spin'):
                mem.w32(hammer + 0x50, world.nodes[rng.choice(world.mobs)])
                mem.w32(hammer + 0xC8, 3 if mode == 'strike' else 4)
                mem.w32(hammer + 0xA0, rng.choice((28, 39, 44)) if mode == 'strike' else rng.choice((57, 76, 96)))
            if mode == 'spin' and state == 4 and c in (82, 102) and rng.random() < 0.7:
                mem.w32(hammer + 0xA0, c + 15)
            if mode == 'spin' and state == 4 and n == 12 and rng.random() < 0.4:
                mem.w32(hammer + 0x50, 0)                       # the target is deleted: the hammer circles its owner
            if mode == 'strike' and state == 3 and c == 50 and rng.random() < 0.7:
                mem.w32(hammer + 0xA0, 58)
            if rng.random() < 0.03:
                mem.w8(RC.G_CUTSCENE_ACTIVE, 1)
            elif rng.random() < 0.3:
                mem.w8(RC.G_CUTSCENE_ACTIVE, 0)
            if caster == world.player:
                mem.w32(caster + 0x58C, 8 if rng.random() < 0.04 else rng.choice((0, 2, 6)))
            if rng.random() < 0.05 and mem.u32(hammer + 0x50):
                victim = mem.u32(mem.u32(hammer + 0x50) + 0xC)
                mem.w32(victim + 0xC, mem.u32(victim + 0xC) | 8)       # the target dies
            if rng.random() < 0.03:
                mem.w32(hammer + 0x50, 0)                       # the target is deleted
            if rng.random() < 0.02:                             # the owner is carried far away (and back)
                world.put(caster, tuple(mem.u32(hammer + 0x10 + 4 * i) for i in range(3)), rng.choice((700.0, -650.0)), 0.0)
            elif rng.random() < 0.1:
                world.put(caster, tuple(mem.u32(hammer + 0x10 + 4 * i) for i in range(3)), rng.uniform(-90, 90),
                          rng.uniform(-90, 90), -60.0)
            if n == 40 and rng.random() < 0.3:
                mem.w32(hammer + 0x4C, 0)                       # the owner is deleted
            if n == 30 and mode != 'end' and rng.random() < 0.25:
                mem.w32(hammer + 0xA8, rng.choice((2, 3, 14)))  # the last frames (3000 particles on the last)
            result = env.do('HammerOfWrath_run', hammer)
            if env.deleted(result, hammer) or result['fault'] or result['both_fault'] is not None:
                break
        mem.w8(RC.G_CUTSCENE_ACTIVE, 0)
    world.enemy_bias = 0.7
    # the level the object keeps, and the shared draws of a complete cast: shaft and light make theirs inside stubs,
    # so what is executed here is GameObject_ctor (1) + item_randomizeVariant (1) + the spell's seed (1)
    bad = []
    for level, rows in sorted(seen.items()):
        for stored, draws, has_spell in rows:
            if stored != (level + 1) & M32 or draws != (3 if has_spell else 2):
                bad.append('level %x: stored %x, %d shared draws, spell %s' % (level, stored, draws, has_spell))
    env.rig.masked = set()
    report('s17 hammerofwrath level and draws', len(bad), sum(len(r) for r in seen.values()),
           'stored level = level + 1; executed shared draws of the cast: object, item variant, spell', bad)


# ---- skill 34 --------------------------------------------------------------------------
add_skill(34, 'shieldbash', {
    'SkillShieldBash_canUse': (0x2FAA00, 0x2FAA88), 'SkillShieldBash_cast': (0x2FAA88, 0x2FAB28),
    'SpellShieldBash_ctor': (0x2FACE4, 0x2FAE80), 'SpellShieldBash_run': (0x2FAE80, 0x2FB49C),
    'SpellShieldBash_windupFx': (0x2FB49C, 0x2FB67C), 'SpellShieldBash_isDone': (0x2FB67C, 0x2FB684),
}, {
    'SkillShieldBash_canUse': (0x2FAA00, 'ii', 'i', 'shieldbash_can_use'),
    'SkillShieldBash_cast': (0x2FAA88, 'iiivi', 'i', 'shieldbash_cast'),
    'SpellShieldBash_run': (0x2FAE80, 'ivi', 'n', 'shieldbash_run'),
    'SpellShieldBash_isDone': (0x2FB67C, 'i', 'i', 'shieldbash_done'),
}, spell_tables=[0x51AD70])


def class_def(env, obj, key='classdef'):
    """Give an object a class definition whose first word is a lump (what the bash and charge constructors read)."""
    world, mem = env.world, env.mem
    if not hasattr(world, key):
        setattr(world, key, env.rig.emu.alloc(0x20))
        mem.w32(getattr(world, key), 0x00D20000)
    mem.w32(obj + 0x24, getattr(world, key))


@scenario('s34 shieldbash', 34)
def s34(env, rounds):
    """Can-use (shield, weapon class, the copy), cast, and the spell run through the
    wind-up, the blow (enemies, the stun roll, the prop fallback) and its end.  SA3: the
    turn target is sometimes destroyed under the spell (its memory scribbled over)."""
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(34)
    spell = world.add_pool(0x28, 1, 'bash')[0]
    world.add_pool(0xBC, 1, 'light')
    clip = env.rig.emu.alloc(0x40)
    world.names[clip] = 'clip'
    world.clips[0x551298] = clip
    world.append_lists = True
    stale = [0, 0]                                              # runs with a destroyed target / of them still read
    for env.round in range(rounds):
        world.place(rng, spread=60.0)
        caster = env.caster(('player', 'player', 'player', 'monster'))
        for slot in range(4):
            rec = G_PLAYERS + slot * REC_SIZE
            mem.w32(rec + 0x43FC, rng.choice((0, world.items[0], world.items[0], world.items[0])))
            mem.w8(rec + 0x4A86, rng.choice((0, 1, 2, 4, 0xFF)))
        asker = env.caster(('player', 'player', 'monster', 'copy'))
        env.do('SkillShieldBash_canUse', skill, asker)
        if asker == world.copy:
            note_stores(env, 34, 'can-use, copy')
        for obj in (world.player, world.monster, world.copy):
            class_def(env, obj)
            mem.w32(obj + 0x544, world.model)
        for off in range(0, 0x40, 4):
            mem.w32(clip + off, rng.getrandbits(32))
        facing = mem.u16(caster + 0x38)
        line_up(env, caster, facing, world.mobs[:4] + [world.props[0]], 15.0, 70.0)
        for mob in rng.sample(world.mobs, 4):
            world.enemy(mob)
        if rng.random() < 0.3:
            for obj in world.mobs:
                mem.w32(obj + 0xC, mem.u32(obj + 0xC) | 0x1000000)
            mem.w32(rng.choice(world.mobs) + 0xC, 0x20)
        world.enemy_bias = rng.choice((0.3, 0.9, 1.0))
        mem.w32(spell + 0x14, 0)
        world.fail_alloc = 0.05
        env.do('SkillShieldBash_cast', skill, env.level(), caster, env.pos_of(caster), facing)
        note_stores(env, 34, 'cast')
        world.fail_alloc = 0.0
        if not mem.u32(spell + 0x14):
            continue
        mem.w16(caster + 0x11A, 0x10 | rng.choice((0, 1, 0x40)))
        target = mem.u32(spell + 0x24)
        destroyed = False
        for n in range(16):
            if n == 12:
                if rng.random() < 0.5:
                    mem.w16(caster + 0x11A, 0)                  # the clip has ended
                else:
                    mem.w32(caster + 0x450, 1)
            if target and n == 2 and rng.random() < 0.4:       # the turn target's object is destroyed and its memory reused
                destroyed = True
                for off in range(0, 0x60, 4):
                    mem.w32(target + off, rng.getrandbits(32))
            if rng.random() < 0.2:
                world.fail_alloc = 0.3
            result = env.do('SpellShieldBash_run', spell, env.pos_of(caster, 0.0, 36.0), mem.u16(caster + 0x38))
            world.fail_alloc = 0.0
            if destroyed:
                stale[0] += 1
                want = tuple(mem.u32(target + 0x10 + 4 * i) for i in range(3))
                stale[1] += any(name == 'Creature.v26' and args[2] == want for name, args in result['emu_calls'])
            env.do('SpellShieldBash_isDone', spell)
            if spell_gone(result, spell):
                break
    world.enemy_bias, world.append_lists = 0.7, False
    del world.clips[0x551298]
    report('s34 shieldbash SA3 raw pointer', stale[0] - stale[1], stale[0],
           'runs after the turn target was overwritten: slot 26 still got the three words at (+0x24) + 0x10')


# ---- skill 22 --------------------------------------------------------------------------
add_skill(22, 'dismissundead', {
    'SkillDismissUndead_cast': (0x2F645C, 0x2F64EC), 'HolyBolt_ctor': (0x2F5248, 0x2F57B0),
    'HolyBolt_run': (0x2F57B0, 0x2F5DDC), 'HolyBolt_onHit': (0x2F5FB4, 0x2F6398),
}, {
    'SkillDismissUndead_cast': (0x2F645C, 'iiivi', 'i', 'dismissundead_cast'),
    'HolyBolt_run': (0x2F57B0, 'i', 'n', 'holybolt_run'),
    'HolyBolt_onHit': (0x2F5FB4, 'ii', 'n', 'holybolt_hit'),
}, object_tables=[0x50E908])


@scenario('s22 dismissundead', 22)
def s22(env, rounds):
    """Cast with its target choice, the bolt's flight (homing, terrain bounces, expiry), the
    hit handler on every kind of object.  SA2: the target is sometimes destroyed under the
    bolt.  A third of the rounds put every mob in front of the caster as an undead enemy,
    to show which one the constructor's loop keeps."""
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(22)
    bolt = world.add_pool(0xC0, 1, 'holybolt')[0]
    world.add_pool(0xBC, 1, 'light')
    world.add_pool(0xB0, 1, 'soul')
    boxes = []
    plain = world.on_world_collectObjectsInBox

    def recording(args, view, rng_):
        res = plain(args, view, rng_)
        boxes.append(list(res.outs[0]))
        return res
    world.on_world_collectObjectsInBox = recording
    order = [0, 0, 0]                                           # staged casts / target is the last undead in box order / and not the nearest
    stale = [0, 0]
    linked = 0
    for env.round in range(rounds):
        world.place(rng)
        staged = rng.random() < 0.34
        caster = world.player if staged else env.caster()
        facing = facing_arg(rng)
        if staged:
            facing = mem.u16(caster + 0x38)
            line_up(env, caster, facing, world.mobs, 60.0, 300.0)
            for mob in world.mobs:
                world.enemy(mob, 0x10)
            mem.w8(world.monster + 0xB4, 0)
            world.enemy_bias = 1.0
        else:
            line_up(env, caster, facing, rng.sample(world.mobs, 3) + [world.players[1], world.props[0]])
            for mob in rng.sample(world.mobs, 3):
                world.enemy(mob, rng.choice((0x10, 0x10, 0)))
            world.enemy_bias = rng.choice((0.2, 0.8, 1.0))
        mem.w32(bolt + 0x48, 0)
        world.fail_alloc = 0.0 if staged else 0.04
        del boxes[:]
        result = env.do('SkillDismissUndead_cast', skill, env.level(), caster, env.pos_of(caster, 4.0, 40.0), facing)
        note_stores(env, 22, 'cast')
        world.fail_alloc = 0.0
        if not mem.u32(bolt + 0x48):
            continue
        linked += any(name == 'handle_link' and args[0] == bolt + 0x64 for name, args in result['emu_calls'])
        target = mem.u32(bolt + 0x64)
        if staged and boxes:
            undead = [o for o in boxes[-1] if o in world.mobs]
            order[0] += 1
            if undead and target == undead[-1]:
                order[1] += 1
                here = [mem.f32(bolt + 0x10 + 4 * i) for i in range(3)]
                nearest = min(undead, key=lambda o: sum((mem.f32(o + 0x10 + 4 * i) - here[i]) ** 2 for i in range(3)))
                order[2] += nearest != target
        env.alive(bolt)
        mode = rng.choice(('fly', 'fly', 'fly', 'expire', 'orphan', 'hits'))
        world.ground_bias = 0.0 if mode == 'expire' else rng.choice((0.0, 0.05, 0.3))
        destroyed = [False]

        def tick(n):
            if mode == 'expire' and n == 8:
                mem.w32(RC.G_SIM_FRAME, (mem.u32(bolt + 0x54) - rng.choice((3, 2, 1, 0))) & M32)
            if mode == 'orphan' and n == 2:
                mem.w32(bolt + 0x4C, 0)
            if n == 4 and rng.random() < 0.3:
                mem.w32(caster + 0xC, mem.u32(caster + 0xC) | 8)
            if n == 3 and target and mem.u32(bolt + 0x64) and rng.random() < 0.4:
                destroyed[0] = True                             # the target object is destroyed and its memory reused
                for off in range(0, 0x60, 4):
                    mem.w32(target + off, rng.getrandbits(32) & ~8 if off == 0xC else rng.getrandbits(32))
                for i in range(3):
                    mem.wf32(target + 0x10 + 4 * i, mem.f32(bolt + 0x10 + 4 * i) + rng.uniform(-400, 400))
            if n == 9 and rng.random() < 0.3 and mem.u32(bolt + 0x64):
                victim = mem.u32(bolt + 0x64)
                mem.w32(victim + 0xC, mem.u32(victim + 0xC) | 8)       # the target dies: the pointer is dropped

        if mode == 'hits':
            for _ in range(12):
                mem.w32(bolt + 0x54, rng.choice((0, 5, mem.u32(RC.G_SIM_FRAME) + 50)))
                if rng.random() < 0.3:
                    mem.w32(bolt + 0x4C, rng.choice((0, world.nodes[caster], world.nodes[world.monster])))
                env.do('HolyBolt_onHit', bolt, rng.choice(world.everything))
        else:
            for n in range(40):
                env.advance()
                tick(n)
                had = mem.u32(bolt + 0x64)
                result = env.do('HolyBolt_run', bolt)
                if destroyed[0] and had == target:
                    stale[0] += 1
                    stale[1] += mem.u32(bolt + 0x68) == mem.u32(target + 0x10) and mem.u32(bolt + 0x6C) == mem.u32(target + 0x14)
                if env.deleted(result, bolt) or result['fault'] or result['both_fault'] is not None:
                    break
    world.on_world_collectObjectsInBox = plain
    world.ground_bias, world.enemy_bias, world.fail_alloc = 0.08, 0.7, 0.0
    report('s22 dismissundead SA2 raw pointer', (stale[0] - stale[1]) + linked, stale[0],
           'runs after the target was overwritten: the aim was still read through +0x64; no handle is linked for it')
    report('s22 dismissundead target order', order[0] - order[1], order[0],
           'all undead in front: the target is the LAST of them in box order (not the nearest in %d)' % order[2])


# ---- skill 1 ---------------------------------------------------------------------------
add_skill(1, 'wizardbeam', {
    'SkillWizardBeam_cast': (0x2F3B0C, 0x2F3B90), 'SpellWizardBeam_ctor': (0x2F1528, 0x2F1A44),
    'SpellWizardBeam_run': (0x2F1A44, 0x2F3928),
}, {
    'SkillWizardBeam_cast': (0x2F3B0C, 'iiivi', 'i', 'wizardbeam_cast'),
    'SpellWizardBeam_run': (0x2F1A44, 'ivi', 'n', 'wizardbeam_run'),
}, spell_tables=[0x51A5B0])


@scenario('s01 wizardbeam', 1)
def s01(env, rounds):
    """Cast, then the channel held for a number of frames: no target, a target coming into
    reach of the chain's tip, side targets, the damage frames (every twentieth), targets
    dying, the facing swinging round."""
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(1)
    spell = world.add_pool(0x380, 1, 'beam')[0]
    for env.round in range(rounds):
        world.place(rng, spread=90.0)
        caster = env.caster(('player', 'player', 'player', 'monster'))
        facing = facing_arg(rng) & 0xFFFF
        mem.w32(spell + 0x14, 0)
        world.fail_alloc = 0.05
        env.do('SkillWizardBeam_cast', skill, rng.choice((0, 1, 3, 5, 6, 8, 12, 20, 30, 40)), caster, env.pos_of(caster), facing)
        note_stores(env, 1, 'cast')
        world.fail_alloc = 0.0
        if not mem.u32(spell + 0x14):
            continue
        crowd = rng.random() < 0.7
        for n in range(22):
            frame = mem.u32(RC.G_SIM_FRAME)
            pick = rng.random()
            frame += 20 - frame % 20 if pick < 0.3 else 8 - frame % 8 if pick < 0.5 else rng.choice((1, 1, 3))
            mem.w32(RC.G_SIM_FRAME, frame & M32)
            if crowd and n in (3, 9, 15):               # enemies near where the chain's tip is
                reach = mem.f32(spell + 0x348) * rng.choice((3.0, 5.0, 5.0, 7.0))
                line_up(env, caster, facing, world.mobs[:5] + [world.players[1]], reach * 0.6, reach * 1.3)
                for mob in rng.sample(world.mobs, 4):
                    world.enemy(mob)
                world.enemy_bias = rng.choice((0.5, 0.9, 1.0))
            if rng.random() < 0.1:
                victim = rng.choice(world.mobs)
                mem.w32(victim + 0xC, mem.u32(victim + 0xC) | 8)
            if rng.random() < 0.15:
                facing = (facing + rng.choice((500, -900, 0x2000))) & 0xFFFF
            env.do('SpellWizardBeam_run', spell, env.pos_of(caster, 0.0, 36.0), facing)
    world.enemy_bias = 0.7


# ==== the third pass: the casts and effects of ids 5, 6, 8 and 10 =============================================
def spell_freed(result, spell):
    """Did this call run the spell's own (real) destructor to the end: pool_free of its block?"""
    return any(c[0] == 'pool_free' and c[1][0] == spell for c in result['emu_calls'])


def set_list(env, head, objs):
    """A handle list as the scripted handle_link leaves it: the objects' own nodes, chained from the head."""
    mem, nodes = env.mem, [env.world.nodes[o] for o in objs]
    for i, node in enumerate(nodes):
        mem.w32(node, nodes[i + 1] if i + 1 < len(nodes) else 0)
    mem.w32(head, nodes[0] if nodes else 0)


def carried(env, caster, held, own_table, chance=0.3):
    """Now and then the caster already carries spells: of the skill's own class or of others."""
    world, mem, rng = env.world, env.mem, env.rng
    for obj in world.everything:
        mem.w32(obj + 0x364, 0)
    for s in held:
        mem.w32(s + 0x14, rng.choice((own_table, own_table, 0x518DB0, AM.VT_SPELL_SUMMON)))
    attached = held[:rng.choice((1, 2))] if rng.random() < chance else []
    world.spell_list(caster, attached)
    return attached


def cast_by_copy(env, sid, key, skill, level, pos, facing):
    """The cast with the prediction copy as the caster, for the store table: Player_castSkill never lets the copy
    get here (flag bit 0 of Skill +4 is clear); this shows what the cast itself would do - it has no test of its own."""
    world, mem = env.world, env.mem
    mem.w32(world.copy + 0x364, 0)
    env.do(key, skill, level, world.copy, pos, facing)
    note_stores(env, sid, 'cast, copy')


# ---- skill 5 ---------------------------------------------------------------------------
add_skill(5, 'diseaseshield', {
    'SkillDiseaseShield_cast': (0x2CDFF8, 0x2CE090), 'SpellDiseaseShield_ctor': (0x2CCFC8, 0x2CD318),
    'SpellDiseaseShield_run': (0x2CD318, 0x2CDEF8),
}, {
    'SkillDiseaseShield_canUse': (0x2CE2B0, 'ii', 'i', 'diseaseshield_can_use'),
    'SkillDiseaseShield_cast': (0x2CDFF8, 'iiivi', 'i', 'diseaseshield_cast'),
    'SpellDiseaseShield_ctor': (0x2CCFC8, 'iiii', 'n', 'diseaseshield_ctor'),
    'SpellDiseaseShield_run': (0x2CD318, 'ivi', 'n', 'diseaseshield_run'),
}, spell_tables=[0x5186C0])


@scenario('s05 diseaseshield', 5)
def s05(env, rounds):
    """Cast (and the constructor as the Mummy calls it), then the shield run at every stage of its growth: the two
    particle clouds whose counts follow the radius, the swarm, the owner walking, the tick and the end.  The damage
    calls are collected for the "maximum below minimum" property."""
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(5)
    spell = world.add_pool(0x1B0, 1, 'dshield')[0]
    held = world.add_pool(0x1C, 2, 'spell')
    ticks = [0, 0]
    for env.round in range(rounds):
        world.place(rng, spread=70.0)
        caster = env.caster(('player', 'player', 'monster', 'monster'))
        carried(env, caster, held, 0x5186C0)
        env.do('SkillDiseaseShield_canUse', skill, caster)
        mem.w32(caster + 0x364, 0)
        for mob in rng.sample(world.mobs, 4):
            world.enemy(mob)
            world.put(mob, env.pos_of(caster), rng.uniform(-90, 90), rng.uniform(-90, 90), rng.choice((0.0, -10.0, 30.0)))
        world.enemy_bias = rng.choice((0.3, 0.9, 1.0))
        mem.w32(spell + 0x14, 0)
        world.fail_alloc = 0.05
        level = env.level()
        pos, facing = env.pos_of(caster), facing_arg(rng)
        if rng.random() < 0.7:
            env.do('SkillDiseaseShield_cast', skill, level, caster, pos, facing)
            note_stores(env, 5, 'cast')
        else:                                                   # as the Mummy builds it (0x299ee8)
            for off in range(0, 0x1B0, 4):
                mem.w32(spell + off, 0)
            env.do('SpellDiseaseShield_ctor', spell, rng.choice((level, level, 0x85, 0x103)), caster, skill)
        world.fail_alloc = 0.0
        if mem.u32(spell + 0x14) == 0x5186C0:
            full = float(mem.s32(spell + 0x1A8))
            for n in range(12):
                frame = mem.u32(RC.G_SIM_FRAME)
                if n == 9:
                    frame = mem.u32(spell + 0x1A4) - rng.choice((31, 30, 2, 1, 0))
                elif rng.random() < 0.5:
                    frame += 30 - frame % 30
                else:
                    frame += rng.choice((1, 1, 3, 11))
                mem.w32(RC.G_SIM_FRAME, frame & M32)
                if n in (1, 4, 7):                              # the radius after any number of frames (it grows by 0.5 a frame)
                    mem.wf32(spell + 0x1AC, rng.choice((0.0, 19.0, 19.5, 27.5, 28.0, 45.0, full - 1.0, full - 0.25, full, full + 30.0)))
                if rng.random() < 0.3:                          # the owner walks
                    for off in (0x10, 0x14, 0x18):
                        mem.wf32(caster + off, mem.f32(caster + off) + rng.uniform(-7, 7))
                result = env.do('SpellDiseaseShield_run', spell, env.pos_of(caster, 0.0, 36.0), mem.u16(caster + 0x38))
                for name, args in result['emu_calls']:
                    if name == 'damage_apply' and fl(args[8]) > 0.0:
                        ticks[0] += 1
                        ticks[1] += fl(args[9]) < fl(args[8]) and args[5] == 0x40
                if spell_gone(result, spell):
                    break
        if rng.random() < 0.25:
            cast_by_copy(env, 5, 'SkillDiseaseShield_cast', skill, level, pos, facing)
    world.enemy_bias = 0.7
    report('s05 diseaseshield halved maximum', ticks[0] - ticks[1], ticks[0],
           'damage calls with d > 0: the maximum handed over is (d + spread) x 0.5, below the minimum d; flags 0x40')


# ---- skill 6 ---------------------------------------------------------------------------
add_skill(6, 'diseasetrail', {
    'SkillDiseaseTrail_cast': (0x2CCBA0, 0x2CCC3C), 'SpellDiseaseTrail_ctor': (0x2CC080, 0x2CC248),
    'SpellDiseaseTrail_run': (0x2CC248, 0x2CCAF8), 'DiseaseTrail_ctor': (0x2CB4E8, 0x2CB65C),
    'DiseaseTrail_run': (0x2CB65C, 0x2CC080),
}, {
    'SkillDiseaseTrail_canUse': (0x2CCE28, 'ii', 'i', 'diseasetrail_can_use'),
    'SkillDiseaseTrail_cast': (0x2CCBA0, 'iiivi', 'i', 'diseasetrail_cast'),
    'SpellDiseaseTrail_run': (0x2CC248, 'ivi', 'n', 'diseasetrail_spell_run'),
    'DiseaseTrail_ctor': (0x2CB4E8, 'iivvii', 'n', 'diseasetrail_ctor'),
    'DiseaseTrail_run': (0x2CB65C, 'i', 'n', 'diseasetrail_run'),
}, object_tables=[0x5184F0], spell_tables=[0x518608])


@scenario('s06 diseasetrail', 6)
def s06(env, rounds):
    """Cast; the spell while the caster walks (steps on both sides of the two drop distances, pool failures, the
    end); then one segment on its own: with and without an owner, creatures of every kind in its box, the tick, the
    one-shot end and the expiry."""
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(6)
    spell = world.add_pool(0x30, 1, 'dtrail')[0]
    segment = world.add_pool(0x68, 1, 'segment')[0]
    held = world.add_pool(0x1C, 2, 'spell')
    drops = [0, 0]                                              # runs that dropped a segment / spell runs
    for env.round in range(rounds):
        world.place(rng, spread=60.0)
        caster = env.caster(('player', 'player', 'monster'))
        carried(env, caster, held, 0x518608)
        env.do('SkillDiseaseTrail_canUse', skill, caster)
        mem.w32(caster + 0x364, 0)
        mem.w32(spell + 0x14, 0)
        mem.w32(segment + 0x48, 0)
        world.fail_alloc = 0.06
        level = env.level()
        pos, facing = env.pos_of(caster, 2.0), facing_arg(rng)
        env.do('SkillDiseaseTrail_cast', skill, level, caster, pos, facing)
        note_stores(env, 6, 'cast')
        if mem.u32(spell + 0x14) == 0x518608:
            here = [fl(v) for v in pos]
            for n in range(12):
                frame = mem.u32(RC.G_SIM_FRAME)
                if n == 9:
                    frame = int(mem.f32(spell + 0x2C)) - rng.choice((2, 1, 0))
                else:
                    frame += rng.choice((1, 1, 1, 5))
                mem.w32(RC.G_SIM_FRAME, frame & M32)
                step, turn = rng.choice((0.0, 5.0, 20.0, 31.9, 32.1, 35.9, 36.1, 37.0, 60.0)), rng.uniform(0, 2 * math.pi)
                here[0] += step * math.cos(turn)
                here[1] += step * math.sin(turn)
                here[2] += rng.choice((0.0, 0.0, 0.0, 17.0, -40.0))
                result = env.do('SpellDiseaseTrail_run', spell, tuple(f32(v) for v in here), mem.u16(caster + 0x38))
                drops[1] += 1
                drops[0] += any(name == 'handle_clear' for name, _args in result['emu_calls'])
                if spell_gone(result, spell):
                    break
        world.fail_alloc = 0.0
        # one segment: the one the spell dropped last, or one built here (also without an owner)
        if rng.random() < 0.6 or mem.u32(segment + 0x48) != 0x5184F0:
            for off in range(0, 0x68, 4):
                mem.w32(segment + off, 0)
            env.do('DiseaseTrail_ctor', segment, rng.choice((level, level, 0, 0xFFFFFFFB)), env.pos_of(caster, 40.0),
                   env.pos_of(caster, 80.0), rng.choice((caster, caster, 0, world.mobs[0])), skill)
        at = tuple(mem.u32(segment + 0x10 + 4 * i) for i in range(3))
        for mob in rng.sample(world.mobs, 4):
            world.enemy(mob)
        for obj in rng.sample(world.mobs, 4) + [world.players[1], world.props[0]]:
            world.put(obj, at, rng.uniform(-30, 30), rng.uniform(-30, 30), rng.choice((0.0, 0.0, -15.0, 25.0)))
        world.enemy_bias = rng.choice((0.0, 0.3, 0.9, 1.0))
        for n in range(10):
            frame = mem.u32(RC.G_SIM_FRAME)
            if n == 7:
                frame = mem.u32(segment + 0x58) - rng.choice((16, 15, 1, 0))
            elif rng.random() < 0.4:
                frame += 15 - frame % 15
            else:
                frame += rng.choice((1, 1, 4))
            mem.w32(RC.G_SIM_FRAME, frame & M32)
            if n == 2 and rng.random() < 0.3:                   # the owner is deleted: the handle empties
                mem.w32(segment + 0x5C, 0)
            result = env.do('DiseaseTrail_run', segment)
            if env.deleted(result, segment) or result['fault'] or result['both_fault'] is not None:
                break
        if rng.random() < 0.25:
            cast_by_copy(env, 6, 'SkillDiseaseTrail_cast', skill, level, pos, facing)
    world.enemy_bias = 0.7
    report('s06 diseasetrail drops', 0 if drops[0] else 1, drops[1], 'spell runs; a segment was dropped in %d of them' % drops[0])


# ---- skill 8 ---------------------------------------------------------------------------
add_skill(8, 'fireflares', {
    'SkillFireFlares_cast': (0x2DD4E8, 0x2DD570), 'SpellFireFlares_ctor': (0x2DCD40, 0x2DD0C8),
    'SpellFireFlares_dtor': (0x2DD0C8, 0x2DD1AC), 'SpellFireFlares_run': (0x2DD1AC, 0x2DD404),
    'FireFlare_ctor': (0x2DBD20, 0x2DBE00), 'FireFlare_run': (0x2DBF10, 0x2DCD40),
}, {
    'SkillFireFlares_canUse': (0x2DD8B8, 'ii', 'i', 'fireflares_can_use'),
    'SkillFireFlares_cast': (0x2DD4E8, 'iiivi', 'i', 'fireflares_cast'),
    'SpellFireFlares_run': (0x2DD1AC, 'ivi', 'n', 'fireflares_run'),
    'SpellFireFlares_dtor': (0x2DD0C8, 'ii', 'n', 'fireflares_dtor'),
    'FireFlare_run': (0x2DBF10, 'i', 'n', 'fireflare_run'),
}, object_tables=[0x5193E0], spell_tables=[0x5194F8])


@scenario('s08 fireflares', 8)
def s08(env, rounds):
    """Cast (1 to 16 flares, pool failures, the division by zero of levels without flares); then frame by frame the
    spell, which moves the flares, and some of the flares: orbiting, the hit on frames divisible by 10, the explosion
    from level 7, the burst and the end.  A flare that deletes itself is taken out of the spell's list, as the object
    destructor's handle clearing would.  The spell's destructor runs for real."""
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(8)
    spell = world.add_pool(0x78, 1, 'flares')[0]
    flares = world.add_pool(0x6C, 16, 'flare')
    held = world.add_pool(0x1C, 2, 'spell')
    seen = [0, 0, 0]                                            # hits / with an explosion / the first victim hit again by it
    bursts = [40]                                               # burst frames still to be run in full
    for env.round in range(rounds):
        world.place(rng, spread=80.0)
        caster = env.caster(('player', 'player', 'player', 'monster'))
        carried(env, caster, held, 0x5194F8)
        env.do('SkillFireFlares_canUse', skill, caster)
        mem.w32(caster + 0x364, 0)
        mem.w32(spell + 0x14, 0)
        for flare in flares:
            mem.w32(flare + 0x48, 0)
        world.fail_alloc = rng.choice((0.0, 0.0, 0.1))
        level = rng.choice((0, 1, 2, 4, 6, 7, 7, 8, 12, 20, 30, 40, 46, 130, 0xFFFFFFE0))
        pos, facing = env.pos_of(caster, 0.0, 36.0), facing_arg(rng)
        env.do('SkillFireFlares_cast', skill, level, caster, pos, facing)
        note_stores(env, 8, 'cast')
        world.fail_alloc = 0.0
        if mem.u32(spell + 0x14) == 0x5194F8:
            live, node = [], mem.u32(spell + 0x18)
            while node:
                live.append(mem.u32(node + 0xC))
                node = mem.u32(node)
            for mob in rng.sample(world.mobs, 5):
                world.enemy(mob)
            world.enemy_bias = rng.choice((0.5, 0.9, 1.0))
            mode = rng.choice(('end', 'end', 'destroyed'))
            for n in range(10):
                frame = mem.u32(RC.G_SIM_FRAME)
                if mode == 'end' and n == 7:
                    frame = mem.u32(spell + 0x28) - rng.choice((2, 1, 0))
                elif rng.random() < 0.5:
                    frame += 10 - frame % 10
                else:
                    frame += rng.choice((1, 1, 3))
                mem.w32(RC.G_SIM_FRAME, frame & M32)
                if rng.random() < 0.2:
                    for off in (0x10, 0x14):
                        mem.wf32(caster + off, mem.f32(caster + off) + rng.uniform(-9, 9))
                result = env.do('SpellFireFlares_run', spell, env.pos_of(caster, 0.0, 36.0), mem.u16(caster + 0x38))
                if spell_freed(result, spell):
                    break
                bursting = [f for f in live if mem.u32(f + 0x58)]
                orbiting = [f for f in live if f not in bursting]
                for flare in bursting + rng.sample(orbiting, min(rng.choice((1, 1, 2)), len(orbiting))):
                    if mem.u32(flare + 0x58):                   # a burst frame is 110 rounds of its loop: a few dozen are run
                        if bursts[0] <= 0:                      # in full, the others are taken straight to the burst's end
                            mem.w16(flare + 0x5E, 77)
                        elif mem.u16(flare + 0x5E) >= 14:
                            mem.w16(flare + 0x5E, rng.choice((63, 70, 70, 77)))
                        bursts[0] -= 1
                    elif rng.random() < 0.5:                    # somebody stands where the flare is
                        at = tuple(mem.u32(flare + 0x10 + 4 * i) for i in range(3))
                        for mob in rng.sample(world.mobs, 2):
                            world.put(mob, at, rng.uniform(-20, 20), rng.uniform(-20, 20), rng.choice((0.0, -30.0)))
                    result = env.do('FireFlare_run', flare)
                    hits = [args[0] for name, args in result['emu_calls'] if name == 'damage_apply']
                    if hits:
                        seen[0] += 1
                        seen[1] += len(hits) > 1
                        seen[2] += hits[0] in hits[1:]
                    if env.deleted(result, flare):
                        live.remove(flare)
                        set_list(env, spell + 0x18, live)
            if mem.u32(spell + 0x14) == 0x5194F8:               # the destructor on its own (the owner died, say)
                if live and rng.random() < 0.4:
                    mem.w32(world.nodes[live[0]] + 0xC, 0)      # a node whose object is gone
                env.do('SpellFireFlares_dtor', spell, rng.choice((0, 1, 2, 3)))
                if live:
                    mem.w32(world.nodes[live[0]] + 0xC, live[0])
        if rng.random() < 0.25:
            cast_by_copy(env, 8, 'SkillFireFlares_cast', skill, level, pos, facing)
    world.enemy_bias = 0.7
    report('s08 fireflares hits', 0 if seen[0] and seen[1] else 1, seen[0],
           'flare hits; %d with an explosion, which hit the first victim a second time in %d' % (seen[1], seen[2]))


# ---- skill 10 --------------------------------------------------------------------------
add_skill(10, 'blessed', {
    'SkillBlessed_cast': (0x2DFEB8, 0x2DFF84), 'SpellBlessed_ctor': (0x2DF078, 0x2DF42C),
    'SpellBlessed_dtor': (0x2DF42C, 0x2DF4BC), 'SpellBlessed_run': (0x2DF4BC, 0x2DFDB8),
    'SpellBlessed_getStat0': (0x2DFDB8, 0x2DFDF0),
}, {
    'SkillBlessed_canUse': (0x2E000C, 'ii', 'i', 'blessed_can_use'),
    'SkillBlessed_cast': (0x2DFEB8, 'iiivi', 'i', 'blessed_cast'),
    'SpellBlessed_run': (0x2DF4BC, 'ivi', 'n', 'blessed_run'),
    'SpellBlessed_dtor': (0x2DF42C, 'ii', 'n', 'blessed_dtor'),
    'SpellBlessed_getStat0': (0x2DFDB8, 'i', 'i', 'blessed_stat0'),
}, spell_tables=[0x5196F0])


@scenario('s10 blessed', 10)
def s10(env, rounds):
    """Cast (also refused: the caster carries the spell already), the statistic Player_regenMana asks for, the run
    with 0 to 6 sparkles and every clamp of their distance and height, the end through the real destructor."""
    world, mem, rng = env.world, env.mem, env.rng
    skill = env.skill(10)
    spell = world.add_pool(0xFC, 1, 'blessed')[0]
    held = world.add_pool(0x1C, 2, 'spell')
    refused = [0, 0]
    for env.round in range(rounds):
        world.place(rng)
        caster = env.caster(('player', 'player', 'player', 'monster'))
        attached = carried(env, caster, held, 0x5196F0)
        env.do('SkillBlessed_canUse', skill, caster)
        mem.w32(spell + 0x14, 0)
        world.fail_alloc = 0.05
        level = rng.choice((0, 1, 2, 3, 4, 7, 10, 13, 16, 20, 40, 0x85))
        pos, facing = env.pos_of(caster), facing_arg(rng)
        result = env.do('SkillBlessed_cast', skill, level, caster, pos, facing)
        note_stores(env, 10, 'cast')
        if any(mem.u32(s + 0x14) == 0x5196F0 for s in attached):
            refused[0] += 1
            refused[1] += result['ret'] == 0 and not any(name == 'pool_new' for name, _args in result['emu_calls']) \
                and not any(not is_stack(addr) for _pc, addr, _size, _value in env.rig.emu.writes)
        world.fail_alloc = 0.0
        mem.w32(caster + 0x364, 0)
        if mem.u32(spell + 0x14) == 0x5196F0:
            env.do('SpellBlessed_getStat0', spell)
            mode = rng.choice(('end', 'end', 'destroyed'))
            for n in range(8):
                frame = mem.u32(RC.G_SIM_FRAME)
                if mode == 'end' and n == 6:
                    frame = mem.u32(spell + 0xB4) - rng.choice((2, 1, 0))
                else:
                    frame += rng.choice((1, 1, 2, 17, 60))
                mem.w32(RC.G_SIM_FRAME, frame & M32)
                if rng.random() < 0.3:                          # a sparkle is put outside its limits
                    i = rng.randrange(6)
                    mem.wf32(spell + 0x1C + 12 * i, rng.choice((-5.0, 0.0, 300.0)))
                    mem.wf32(spell + 0x20 + 12 * i, rng.choice((-5.0, 500.0)))
                if rng.random() < 0.2:                          # the owner moves and changes size
                    mem.wf32(caster + 0x10, mem.f32(caster + 0x10) + rng.uniform(-9, 9))
                    mem.wf32(caster + 0x1C, rng.choice((8.0, 24.0)))
                    mem.wf32(caster + 0x20, rng.choice((40.0, 96.0)))
                result = env.do('SpellBlessed_run', spell, env.pos_of(caster, 0.0, 36.0), mem.u16(caster + 0x38))
                if spell_freed(result, spell):
                    break
            if mem.u32(spell + 0x14) == 0x5196F0:               # the destructor on its own (the owner died, say)
                env.do('SpellBlessed_dtor', spell, rng.choice((0, 1, 2, 3)))
        if rng.random() < 0.25:
            cast_by_copy(env, 10, 'SkillBlessed_cast', skill, level, pos, facing)
    report('s10 blessed refused', refused[0] - refused[1], refused[0],
           'casts by a caster that already carries a SpellBlessed: 0 returned, nothing allocated, nothing stored')
    bits = [sid for sid in (5, 6, 8, 10) if mem.u32(env.skill(sid) + 4) & 1]
    report('copy flag of ids 5, 6, 8, 10', len(bits), 4,
           'Skill +4 bit 0 is clear in the executed objects: Player_castSkill turns the prediction copy away (0x1a4320)', bits)


def main(argv):
    args = list(argv)
    elf = None
    while args:
        a = args.pop(0)
        if a == '--quick':
            OPTIONS['quick'] = True
        elif a == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif a == '--rounds':
            OPTIONS['rounds'] = int(args.pop(0), 0)
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
        print('difftest_skills_a: %s not found - nothing to compare with (this is not a failure)' % elf)
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != DC.EXPECTED_SHA256:
        print('difftest_skills_a: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    rounds = max(OPTIONS['rounds'] // 10, 2) if OPTIONS['quick'] else OPTIONS['rounds']
    C.set_fpu(OPTIONS['fpu'])
    started = time.time()
    wanted = (OPTIONS['filter'] or '').lower()
    probe = EE(elf)
    cov = Coverage(probe.mem)
    counts, draws, total = {}, {}, 0
    if wanted in 'stats':
        total += stats_sweep(elf, cov)
    for index, (name, sid, fn) in enumerate(SCENARIOS):
        if wanted and wanted not in name.lower():
            continue
        rig = Rig(elf, OPTIONS['seed'] + 17 * index)
        env = Env(rig, name, cov, counts, draws)
        fn(env, rounds)
        total += env.finish()
    print()
    print('calls compared per entry point / calls with any mismatch / shared-seed draws seen')
    for key in sorted(counts):
        print('  %-36s %7d / %d / %d' % (key, counts[key][0], counts[key][1], draws.get(key, 0)))
    print('coverage of the original as executed here (basic blocks, instructions), by skill:')
    by_skill = {}
    for part, (_s, _e, sid) in BODIES.items():
        by_skill.setdefault(sid, []).append(part)
    tb = tbt = 0
    for sid in sorted(by_skill):
        sb = sbt = 0
        lines = []
        for part in by_skill[sid]:
            b, bt, i, it = cov.numbers(part)
            sb, sbt = sb + b, sbt + bt
            lines.append('      %-40s blocks %4d of %4d (%5.1f%%)  instructions %4d of %4d' % (part, b, bt, 100.0 * b / bt, i, it))
            if OPTIONS['verbose'] and b != bt:
                lines.append('          never entered: %s' % ' '.join('%06x' % a for a in cov.missing(part)))
        tb, tbt = tb + sb, tbt + sbt
        title = 'shared machinery' if sid == 0 else 'skill %d %s' % (sid, SKILL_NAMES.get(sid, ''))
        print('  %-34s %2d functions  blocks %4d of %4d (%5.1f%%)' % (title, len(by_skill[sid]), sb, sbt, 100.0 * sb / max(sbt, 1)))
        if not wanted or OPTIONS['verbose']:
            for line in lines:
                print(line)
    print('  %-34s                blocks %4d of %4d (%5.1f%%)' % ('all', tb, tbt, 100.0 * tb / max(tbt, 1)))
    if COPY_ROWS:
        print('stores outside the stack, the new objects and the shared seed (pc -> where), in order, per skill and call:')
        for sid in sorted(COPY_ROWS):
            for what, rows in sorted(COPY_ROWS[sid].items()):
                text = ', '.join('%06x -> %s' % r for r in rows[:8]) or 'none'
                print('  %3d %-14s %-22s %s' % (sid, SKILL_NAMES.get(sid, ''), what, text))
    print('%d calls compared in %.0f s' % (total, time.time() - started))
    return 0 if all(ok for _name, ok in RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
