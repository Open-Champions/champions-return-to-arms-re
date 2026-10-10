#!/usr/bin/env python3
"""difftest_skills_c.py - compare tools/ref_skills_c.py with the game's own code for the
skills with ids 69-101.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_skills_c.py [path/to/SLUS_209.73] [--quick] [--seed N] [-k TEXT]
                                     [-v] [--fpu MODEL] [--trace-first]

    --quick       a fifth of the random scenarios (the statistics sweep stays complete)
    --seed N      seed of the random scenarios (default 6911); a seed repeats exactly
    -k TEXT       only the skills whose name or id contains TEXT ("stats" for the sweep)
    -v            print the first mismatches of every failing property and the basic
                  blocks never entered
    --fpu MODEL   ps2 (default), ps2g1, chop or nearest: the adder model of BOTH sides
    --trace-first stop at the first mismatching call and print both call lists

What is compared
    The ORIGINAL functions listed in ref_skills_c.MODELLED - the Skill object's statistic
    getters, each skill's can-use, mana-cost and cast, the constructors of its spell or
    object, the per-tick run and the hit handlers - are executed by tools/ee_emu.py (an
    instruction interpreter, not a console) on skill objects the original constructors
    and statistics initialisers built.  Every such call is first run through the model on
    a copy-on-write view of the same memory, and these must be equal:
      calls    the sequence of calls to everything outside the model, with arguments
               (stack-passed arguments where a callee takes them)
      writes   the set of bytes stored outside the stack, and their final values - which
               includes the spell's own generator (+0x10) and an object's (+0x44)
      seed     the shared seed 0x404464, and that it advanced exactly as often as the
               model says it drew
      result   the value returned
    Floats are compared as 32-bit patterns under the interpreter's floating-point model
    (docs/issues/dynamic-tests.md says what that model can and cannot promise).

What runs for real and what is a stub
    Real: everything in ref_skills_c.MODELLED, the handle-list functions on lists that
    live in objects, the three angle functions and the C library.  Everything else is a
    recording stub answered by a seeded script (class World): the damage function, the
    world queries, the pool, object and effect constructors, sound, particles, animation,
    the inventory, creature virtual slots (is-enemy, stun, team).  A call to an address
    that is neither real nor a known stub is reported as a failure.

Scenarios
    Each skill is cast by players and by monsters at every relevant level, with targets in
    and out of range, the pool sometimes empty, and its spell or object is then run tick
    by tick to its natural end or until the driver ends it early (the owner's death).
    The statistics getters are compared exhaustively: 33 ids x levels 0-40 x statistics
    0-4 for slots 10, 11, 12, 13 and 8, and the mana cost.
"""
import hashlib
import os
import random
import sys
import time
import traceback

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError                 # noqa: E402
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_skills_c as SK                       # noqa: E402
import difftest_creature as DC                  # noqa: E402
from difftest_creature import Res, f32, fl, rd, is_stack      # noqa: E402

M32 = 0xFFFFFFFF
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = {'quick': False, 'seed': 6911, 'filter': None, 'verbose': False, 'trace_first': False, 'fpu': 'ps2'}
RESULTS = []
STUB_BASE = 0x00F40000
G_PLAYERS, REC_SIZE, REC_OBJ = RC.G_PLAYERS, RC.REC_SIZE, RC.REC_OBJ

# code that runs for real besides ref_skills_c.MODELLED: the angle functions and the C
# library (soft float, atan2f, string compares)
REAL_OTHER = {0x166630, 0x1666E0, 0x166798}
LIB_LO, LIB_HI = DC.LIB_LO, DC.LIB_HI
LIB_STUBBED = {0x3B7EF0}                        # sprintf: a call-out (the text it makes is a token)

# function bodies: name -> (start, end); the names are ref_skills_c.MODELLED's
BODIES = {
    'Skill_canUse_default': (0x3C8218, 0x3C8220), 'Skill_cast_default': (0x3C8220, 0x3C8248),
    'Skill_manaCost_default': (0x3C82A8, 0x3C82B8),
    'Skill_getStatRange': (0x3C82E4, 0x3C85B0), 'Skill_getStat': (0x3C85FC, 0x3C8690),
    'Skill_getStatTier2': (0x3C8690, 0x3C87F0), 'Skill_getStatFor': (0x3C87F0, 0x3C8864),
    'Skill_getStatForHandle': (0x3C8864, 0x3C88DC), 'Skill_adjustLevel': (0x3C88DC, 0x3C88E4),
    'Skill_manaFromStat4': (0x3C88E4, 0x3C8944),
    'Spell_rand': (0x16A964, 0x16A98C), 'GameObject_rand': (0x1509D0, 0x1509F8),
    'Creature_getVisualPos': (0x118738, 0x1187E0),
    'handle_link': (0x1A1738, 0x1A17CC), 'handle_clear': (0x1A1698, 0x1A1734),
    'handle_removeNode': (0x1A1868, 0x1A18F0),
}
# which functions belong to which report line: skill key -> names
GROUPS = {'stats': ['Skill_canUse_default', 'Skill_cast_default', 'Skill_manaCost_default', 'Skill_getStatRange',
                    'Skill_getStat', 'Skill_getStatTier2', 'Skill_getStatFor', 'Skill_getStatForHandle',
                    'Skill_adjustLevel', 'Skill_manaFromStat4'],
          'shared': ['Spell_rand', 'GameObject_rand', 'Creature_getVisualPos', 'handle_link', 'handle_clear',
                     'handle_removeNode']}

# entry points: key -> (address, argument kinds, result kind, model method)
#   argument kinds: i integer, v vector passed by pointer, f float (f12..), W a word the
#   callee fills;  result kinds: i integer, f float, n nothing, w2 the two filled words
ENTRIES = {
    'Skill_getStat': (0x3C85FC, 'iii', 'i', 'skill_get_stat'),
    'Skill_getStatTier2': (0x3C8690, 'iiii', 'i', 'skill_get_stat_tier2'),
    'Skill_getStatFor': (0x3C87F0, 'iiiii', 'i', 'skill_stat_for'),
    'Skill_getStatForHandle': (0x3C8864, 'iiiii', 'i', 'skill_stat_for_handle'),
    'Skill_getStatRange': (0x3C82E4, 'iiiiWWf', 'w2', 'skill_stat_range'),
    'Skill_adjustLevel': (0x3C88DC, 'iii', 'i', 'skill_adjust_level'),
    'Skill_manaFromStat4': (0x3C88E4, 'iii', 'f', 'skill_mana_from_stat4'),
    'Skill_canUse_default': (0x3C8218, 'ii', 'i', 'skill_can_use_default'),
    'Skill_manaCost_default': (0x3C82A8, 'ii', 'f', 'skill_mana_default'),
    'Skill_cast_default': (0x3C8220, 'iiivi', 'i', 'skill_cast_default'),
}
SCENARIOS = []                                  # (skill key, title, function(test))


def entry(key, addr, end, kinds, ret, method, group):
    """Register one original function: its body for the coverage count, how to call it,
    the model method, and the report line it belongs to."""
    BODIES[key] = (addr, end)
    ENTRIES[key] = (addr, kinds, ret, method)
    GROUPS.setdefault(group, []).append(key)


def body(key, addr, end, group):
    """A function that runs for real underneath an entry point (a constructor, a helper)."""
    BODIES[key] = (addr, end)
    GROUPS.setdefault(group, []).append(key)


class RealSet:
    def __init__(self):
        self.addresses = set(REAL_OTHER) | set(SK.MODELLED.values()) | {s for s, _e in BODIES.values()}

    def __contains__(self, target):
        return target in self.addresses or (LIB_LO <= target < LIB_HI and target not in LIB_STUBBED)


class EmuView(DC.EmuView):
    def __init__(self, emu):
        DC.EmuView.__init__(self, emu)
        self.state = {}


class ModelView(DC.ModelView):
    def __init__(self, under):
        DC.ModelView.__init__(self, under)
        self.state = {}


# ---------------------------------------------------------------------------------------
# The scripted world
# ---------------------------------------------------------------------------------------
class World:
    """Builds the fake game in the interpreter's memory and answers every stubbed call.
    An answer may depend only on the arguments, on memory read through `view` and on the
    seeded generator it is handed, so the model and the original get the same answers as
    long as they make the same calls."""

    CREATURE_SLOTS = 48

    def __init__(self, emu, rng):
        self.emu, self.mem = emu, emu.mem
        self.stub_addr, self.stub_name = {}, {}
        mem = self.mem
        self.vt_creature = emu.alloc(8 * self.CREATURE_SLOTS)
        for slot in range(self.CREATURE_SLOTS):
            mem.w32(self.vt_creature + 8 * slot + 4, self.stub_for('Creature.v%d' % slot))
        self.monsters = [emu.alloc(0x600) for _ in range(8)]
        self.players = [emu.alloc(0x600) for _ in range(4)]
        self.objects = self.monsters + self.players
        self.list_nodes = [emu.alloc(0x20) for _ in range(64)]
        self.argbuf = emu.alloc(0x100)
        self.model_ptr = 0x00C00040
        self.pool, self.busy, self.block_size = {}, set(), {}
        self.pool_fail = 0.05                   # how often pool_new has no block
        self.enemy_bias = 0.7                   # how often slot 20 says "enemy"
        self.carried = {}                       # (creature, class token) -> spell
        self.anim_files = [emu.alloc(0x80) for _ in range(3)]
        self.anim_end, self.anim_event = 0.01, None
        self.class_def = emu.alloc(0x40)
        mem.w32(self.class_def, 0x00D10000)     # the lump name of an animation lump
        self.query = None                       # objects a world query returns; None = a random pick
        mem.w32(RC.G_SIM_FRAME, 1000 + rng.randrange(5000))
        mem.w32(RC.G_WORLD, emu.alloc(16))
        mem.w32(RC.G_NUM_PLAYERS, 4)
        for slot in range(4):
            mem.w32(G_PLAYERS + slot * REC_SIZE + REC_OBJ, self.players[slot])
        emu.call(0x1A17D0)                      # handle_initPool: thread the node pool
        self.reset_objects(rng)

    def stub_for(self, name):
        if name not in self.stub_addr:
            addr = STUB_BASE + 16 * len(self.stub_addr)
            self.stub_addr[name], self.stub_name[addr] = addr, name
        return self.stub_addr[name]

    # ---- objects --------------------------------------------------------------------------
    def reset_objects(self, rng, centre=(2000.0, 3000.0, 10.0), spread=None):
        """Fresh creatures and players around a point: zeroed, with positions, sizes, flags,
        hit points and the stub table."""
        mem = self.mem
        for index, obj in enumerate(self.objects):
            player = obj in self.players
            for off in range(0, 0x600, 4):
                mem.w32(obj + off, 0)
            reach = spread if spread is not None else rng.choice((40, 90, 90, 200, 400, 1200))
            mem.wf32(obj + 0x10, centre[0] + rng.uniform(-reach, reach))
            mem.wf32(obj + 0x14, centre[1] + rng.uniform(-reach, reach))
            mem.wf32(obj + 0x18, centre[2] + rng.choice((0.0, 0.0, 0.0, -20.0, 30.0)))
            mem.wf32(obj + 0x1C, rng.choice((8.0, 16.0, 24.0, 30.0)))
            mem.wf32(obj + 0x20, rng.choice((40.0, 72.0, 84.0)))
            mem.w16(obj + 0x38, rng.randrange(0x10000))
            mem.wf32(obj + 0x3C, mem.f32(obj + 0x18))
            mem.w32(obj + 0x44, rng.getrandbits(32))
            mem.w32(obj + 0x48, self.vt_creature)
            mem.w32(obj + 0x24, self.class_def)
            mem.w32(obj + 0x544, self.model_ptr + 0x40)
            mem.wf32(obj + 0xE0, rng.choice((0.0, 0.0, 4.0)))
            if player:
                slot = self.players.index(obj)
                mem.w32(obj + 0xC, 0x40 | 0x20)
                mem.w32(obj + 0x3C8, slot)
                mem.w8(obj + 0x310, rng.choice((0, 1)))
                rec = G_PLAYERS + slot * REC_SIZE
                mem.wf32(rec + 0xAC, rng.choice((100.0, 100.0, 37.5, 0.0)))
                mem.wf32(rec + 0xB0, 120.0)
                mem.wf32(rec + 0xC0, rng.choice((0.0, 50.0, 119.0)))
                mem.wf32(rec + 0xC4, 120.0)
            else:
                mem.w32(obj + 0xC, rng.choice((0x20, 0x20, 0x20, 0x20, 0x28, 0x21, 0x0, 0x10, 0x24)))
                mem.w8(obj + 0x310, rng.choice((0xFF, 0xFF, 0, 1, 2)))
            hp = rng.choice((300.0, 300.0, 40.0, 5.0))
            mem.wf32(obj + 0x228, hp)
            mem.wf32(obj + 0x22C, hp)

    def creature(self, rng, player=None):
        """A caster: a player object or a monster, alive and plain."""
        if player is None:
            player = rng.random() < 0.6
        obj = rng.choice(self.players if player else self.monsters)
        self.mem.w32(obj + 0xC, 0x60 if player else 0x20)
        return obj

    # ---- answers --------------------------------------------------------------------------
    def respond(self, name, args, view, rng):
        handler = getattr(self, 'on_' + name.replace('.', '_'), None)
        if handler is not None:
            return handler(args, view, rng)
        return Res()

    def on_pool_new(self, args, view, rng):
        size = args[0]
        blocks = self.pool.get(size)
        if blocks is None:
            blocks = self.pool[size] = [self.emu.alloc((size + 0x1F) & ~0xF) for _ in range(6)]
            for b in blocks:
                self.block_size[b] = size
        taken = view.state.setdefault('taken', set())
        if rng.random() < self.pool_fail:
            return Res(0)
        for block in blocks:
            if block not in self.busy and block not in taken:
                taken.add(block)
                for off in range(0, (size + 3) & ~3, 4):   # the pool zero-fills
                    view.poke(block + off, 4, 0)
                return Res(block)
        return Res(0)

    def on_res_find(self, args, view, rng):
        if isinstance(args[1], tuple):                  # a file named by sprintf: an animation header
            return Res(rng.choice(self.anim_files))
        return Res(0x00D00000 + rng.randrange(4) * 0x10)

    def on_libc_sprintf(self, args, view, rng):
        return Res(outs=[b'file%d' % rng.randrange(3)])

    def on_anim_startBlendInOut(self, args, view, rng):
        view.poke(args[0] + 6, 2, rd(view, args[0] + 6, 2) | 0x20)     # the track is there
        return Res()

    def on_Player_animStep(self, args, view, rng):
        """One animation step of a player: the event bits, and now and then the end of the
        track (flag 0x20 of the animation state's flag word goes)."""
        if rng.random() < self.anim_end:
            view.poke(args[0] + 0x11A, 2, rd(view, args[0] + 0x11A, 2) & ~0x20)
        if self.anim_event is not None:                 # what the scenario scripted for this frame
            return Res(self.anim_event)
        return Res(rng.choice((0,) * 12 + (1, 2, 4, 8, 6)))

    def on_typeinfo(self, args, view, rng):
        return Res(args[0])

    def on_creature_findSpellByType(self, args, view, rng):
        return Res(self.carried.get((args[0], args[1]), 0))

    def on_Spell_v1(self, args, view, rng):
        view.state.setdefault('destroyed', []).append(args[0])
        return Res()

    def on_particleGroup_create(self, args, view, rng):
        return Res(rng.choice((0, 1, 2, 5, 15)))

    def on_Creature_v20(self, args, view, rng):
        return Res(rng.choice((1, 1, 1, 4)) if rng.random() < self.enemy_bias else 0)

    def on_Creature_v21(self, args, view, rng):
        return Res(1 if rng.random() < 0.5 else 0)

    def on_Creature_v22(self, args, view, rng):
        return Res(1 if rng.random() < 0.5 else 0)

    def on_Creature_v37(self, args, view, rng):
        return Res(rd(view, args[0] + 0x310, 1, True) & M32)

    def on_damage_apply(self, args, view, rng):
        """A hit lands: hit points go down, and now and then the victim dies."""
        target = args[0]
        amount = f32(rng.choice((1.0, 4.0, 25.0, 400.0)))
        view.poke(target + 0x228, 4, C.sub(rd(view, target + 0x228), amount))
        if rng.random() < 0.15:
            view.poke(target + 0xC, 4, rd(view, target + 0xC) | 8)
        return Res(1)

    def _some_objects(self, args, view, rng):
        if self.query is not None:
            return Res(outs=[list(self.query)])
        count = rng.choice((0, 1, 2, 3, 5, 8, 11))
        return Res(outs=[[rng.choice(self.objects) for _ in range(count)]])

    on_world_collectInSphere = on_world_collectObjectsInArc = on_world_collectObjectsInBox = _some_objects

    def on_terrain_height(self, args, view, rng):
        return Res(f=f32(fl(args[1][2]) + rng.choice((0.0, 0.0, 0.0, 3.0, -8.0, 11.5, -13.0, 23.0, 24.5, -30.0, 60.0))))

    def on_water_test(self, args, view, rng):
        return Res(1 if rng.random() < 0.4 else 0)

    def on_net_isLocalSlot(self, args, view, rng):
        return Res(1 if rng.random() < 0.5 else 0)

    def on_net_objOrGhost(self, args, view, rng):
        return Res(args[0])

    def on_model_getSamplePointCount(self, args, view, rng):
        return Res(rng.choice((1, 3, 7, 7, 12)))

    def on_model_getSamplePoint(self, args, view, rng):
        pos = args[2]
        point = tuple(f32(fl(pos[i]) + rng.uniform(-30, 30)) for i in range(3))
        return Res(outs=[point, (f32(rng.uniform(-1, 1)), f32(rng.uniform(-1, 1)), f32(rng.uniform(-1, 1)))])

    def on_model_getAttachPoint(self, args, view, rng):
        pos = args[1]
        point = tuple(f32(fl(pos[i]) + rng.uniform(-20, 20)) for i in range(3))
        return Res(outs=[point, (f32(rng.uniform(-1, 1)), f32(rng.uniform(-1, 1)), f32(rng.uniform(-1, 1)))])


# ---------------------------------------------------------------------------------------
# The rig: one interpreter, the stubs, and the comparison of one call
# ---------------------------------------------------------------------------------------
class Rig:
    def __init__(self, elf, seed):
        self.rng = random.Random(seed)
        emu = self.emu = EE(elf, fpu_model=OPTIONS['fpu'])
        emu.div_zero = 'r5900'                          # a division by zero goes on, as on the console
        C.set_fpu(OPTIONS['fpu'])
        emu.follow = self.real = RealSet()
        self.world = World(emu, self.rng)
        self.calls, self.buffers, self.unknown = [], {}, {}
        self.eview = EmuView(emu)
        self.script_rng = None
        self.names = {}
        self.pcs = set()
        self.notes = {}
        mem = emu.mem

        def add(addr, name, ext):
            assert addr not in self.real, (hex(addr), name)
            assert self.names.setdefault(addr, name) == name, (hex(addr), name, self.names[addr])
            emu.stub(addr, function=self.make_stub(name, ext), name=name)

        for name, ext in SK.EXTERNALS.items():
            if ext.addr and ext.addr not in self.real:
                add(ext.addr, name, ext)
            elif name in self.world.stub_addr:
                add(self.world.stub_addr[name], name, ext)
        for addr, name in self.world.stub_name.items():
            if addr not in self.names:
                add(addr, name, RC.Ext(0, 'p', 0, 'n'))
        for getter in SK.TYPEINFO.values():             # class tokens: the getter's own address
            self.names[getter] = 'typeinfo'
            emu.stub(getter, function=self.typeinfo_stub(getter), name='typeinfo')
        # the skill objects, built by the game's own constructors and statistics functions
        self.skills = build_skills(emu)
        # destructors (slot 1) of the spell classes: recorded, not run
        for table in sorted(SK.SPELL_TABLES):
            fn = mem.u32(table + 8 * 1 + 4)
            if fn not in self.names:
                add(fn, 'Spell.v1', SK.EXTERNALS['Spell.v1'])
        for table in sorted(SK.OBJECT_TABLES):         # and of the object classes
            fn = mem.u32(table + 8 * 1 + 4)
            if fn not in self.names:
                add(fn, 'Creature.v1', SK.EXTERNALS['Creature.v1'])
        # handle lists whose head is on the stack stay call-outs (the model has no stack)
        emu.hook(0x1A1698, self.stack_list_hook('handle_clear', 'p'))
        emu.hook(0x1A1738, self.stack_list_hook('handle_link', 'ppp'))
        # tools/ee_emu.py logs an unaligned sdl / sdr / swl / swr as a store of the whole
        # aligned word; record the real effective address of every such instruction
        self.partial, self.partial_ops = [], {}
        for start, end in BODIES.values():
            for pc in range(start, end, 4):
                w = mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))
        self.parts = {name: (start, end) + DC.analyse(mem, start, end) for name, (start, end) in BODIES.items()}

    # ---- interpreter side -----------------------------------------------------------------
    def partial_hook(self, pc, base, offset):
        def note(emu):
            ea = (emu.r[base] + offset) & M32
            if not is_stack(ea):
                self.partial.append((pc, ea))
        return note

    def stored_bytes(self, lo, hi):
        """The bytes the original stored outside the stack and outside [lo, hi), exact for
        the partial-word stores."""
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

    def typeinfo_stub(self, getter):
        def stub(emu):
            self.calls.append(('typeinfo', (getter,)))
            return getter
        return stub

    def stack_list_hook(self, name, kinds):
        def hook(emu):
            if not is_stack(emu.r[4] & M32):
                return                                  # a list inside an object: runs for real
            args = tuple('stack' if is_stack(emu.r[4 + i] & M32) else emu.r[4 + i] & M32 for i in range(len(kinds)))
            self.calls.append((name, args))
            rec = emu._fresh_call
            if rec is not None:
                rec.stubbed, rec.ret = True, 0
            emu.r[2] = 0
            emu.jump(emu.r[31] & M32)
        return hook

    @staticmethod
    def decode_desc(mem, v):
        """A damage descriptor: an item record whose four effect slots sit at +0x24."""
        if v == 0:
            return 0
        if not is_stack(v):
            return v
        slots = []
        for k in range(4):
            ident = mem.u16(v + 0x24 + 8 * k)
            slots.append((ident,) if ident == 0xFFFF else tuple(mem.u16(v + 0x24 + 8 * k + 2 * j) for j in range(4)))
        return ('desc', bytes(mem.read(v + 0x10, 0x12)).hex()) + tuple(slots)

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
            elif kind == 'S':
                canon.append(('buf', self.buffers[v]) if v in self.buffers else v)
            elif kind == 'd':
                canon.append(self.decode_desc(mem, v))
            elif kind == 'T':                           # ten points
                canon.append(tuple(mem.u32(v + 4 * j) for j in range(30)))
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
                args = (fmt, emu.r[6] & M32 if b'%' in bytes(mem.read(fmt, 48)).split(b'\0')[0] else None)
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
                value = given.pop(0) if given else ((0, 0, 0) if kind in 'oO' else ([] if kind in 'nL' else 0))
                if kind == 'L':                         # a chain of list nodes: +0 next, +0xc the object
                    nodes = self.world.list_nodes[:len(value)]
                    for j, (node, obj) in enumerate(zip(nodes, value)):
                        mem.w32(node, nodes[j + 1] if j + 1 < len(nodes) else 0)
                        mem.w32(node + 0xC, obj)
                    mem.w32(ptr, nodes[0] if nodes else 0)
                elif kind in 'oO':
                    if ptr and not is_stack(ptr):       # an output inside an object: the callee's store
                        for j in range(3):
                            self.eview.poke(ptr + 4 * j, 4, value[j])
                    elif ptr:
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
            if ext.ret == 'f':
                emu.f[0] = res.f & M32
            if ext.ret == 'q':
                return res.ret & RC.M64
            return ee_emu.s32(res.ret)                  # a 32-bit result, sign-extended
        return stub

    # ---- model side -----------------------------------------------------------------------
    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                ret = res.ret & (RC.M64 if SK.EXTERNALS[name].ret == 'q' else M32)
                return SK.shape_result(name, args, ret, res.f & M32, res.outs)
            return answer

    # ---- one call, both sides ---------------------------------------------------------------
    def compare(self, key, args, call_seed):
        addr, kinds, ret_kind, method = ENTRIES[key]
        emu, world = self.emu, self.world
        mem = emu.mem
        seed_before = mem.u32(RC.G_RAND_SEED)
        mview = ModelView(mem)
        model = SK.Model(mview, Rig.Callbacks(self, mview, random.Random(call_seed)))
        margs = [a for a, k in zip(args, kinds) if k != 'W']
        model_error = None
        try:
            mret = getattr(model, method)(*margs)
        except Exception as exc:                        # noqa: BLE001 - a model fault is a result
            model_error, mret = exc, None
            if OPTIONS['verbose']:
                traceback.print_exc()
        self.calls, self.buffers = [], {}
        self.eview.touched, self.eview.state = set(), {}
        self.script_rng = random.Random(call_seed)
        emu.reset_log()
        self.partial = []
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x100
        ints, nfloat, scratch, outs = [], 0, world.argbuf, []
        for a, k in zip(args, kinds):
            if k == 'i':
                ints.append(ee_emu.s32(a & M32))        # a register holds a sign-extended 32-bit value
            elif k == 'v':
                for j in range(3):
                    mem.w32(scratch + 4 * j, a[j])
                ints.append(scratch)
                scratch += 0x10
            elif k == 'W':
                outs.append(scratch)
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
        self.pcs.update(emu.trace)
        emu.trace = None
        for note in emu.notes:                          # divisions by zero the code went through
            self.notes[note[:32]] = self.notes.get(note[:32], 0) + 1
        for c in emu.calls:
            if c.target not in self.real and c.target not in self.names:
                self.unknown[c.target] = self.unknown.get(c.target, 0) + 1
        out = {'key': key, 'fault': None, 'calls': None, 'writes': None, 'seed': None, 'result': None,
               'model_calls': model.calls, 'emu_calls': self.calls, 'ret': eret, 'state': self.eview.state}
        if model_error or emu_error:
            out['fault'] = 'model %r / original %r' % (model_error, emu_error)
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
                text += ' only original stores %s;' % compact(self, ebytes - mbytes)
            if mbytes - ebytes:
                text += ' only model stores %s;' % compact(self, mbytes - ebytes)
            if diff:
                text += ' values differ at %s' % [(self.where(a), '%02x' % x, '%02x' % y) for a, x, y in diff[:12]]
            out['writes'] = text
        s = seed_before
        for _ in range(model.draws):
            s = (s * 0x19660D + 0x3C6EF35F) & M32
        if not mem.u32(RC.G_RAND_SEED) == mview.load(RC.G_RAND_SEED, 4) == s:
            out['seed'] = 'model draws %d' % model.draws
        if ret_kind == 'i' and (eret & M32) != ((mret or 0) & M32):
            out['result'] = 'original %08x model %08x' % (eret & M32, (mret or 0) & M32)
        elif ret_kind == 'f' and emu.f[0] & M32 != (mret or 0) & M32:
            out['result'] = 'original %08x model %08x' % (emu.f[0] & M32, (mret or 0) & M32)
        elif ret_kind == 'w2':
            got = tuple(mem.u32(p) for p in outs)
            if got != tuple(v & M32 for v in mret):
                out['result'] = 'original %s model %s' % (got, mret)
            out['ret'] = got
        elif ret_kind == 'iw':                          # an integer and one filled word
            got = (eret & M32, mem.u32(outs[0]))
            if got != tuple(v & M32 for v in mret):
                out['result'] = 'original %s model %s' % (got, mret)
        if ret_kind == 'f':
            out['ret'] = emu.f[0] & M32
        return out

    def where(self, addr):
        world = self.world
        for i, obj in enumerate(world.monsters):
            if obj <= addr < obj + 0x600:
                return 'monster%d+%x' % (i, addr - obj)
        for i, obj in enumerate(world.players):
            if obj <= addr < obj + 0x600:
                return 'playerobj%d+%x' % (i, addr - obj)
        if G_PLAYERS <= addr < G_PLAYERS + 4 * REC_SIZE:
            return 'record%d+%x' % ((addr - G_PLAYERS) // REC_SIZE, (addr - G_PLAYERS) % REC_SIZE)
        for block, size in world.block_size.items():
            if block <= addr < block + size + 0x10:
                return 'block%x+%x' % (size, addr - block)
        if SK.G_HANDLE_NODES <= addr < SK.G_HANDLE_FREE:
            return 'node%d+%x' % ((addr - SK.G_HANDLE_NODES) // 20, (addr - SK.G_HANDLE_NODES) % 20)
        for ident, obj in self.skills.items():
            if obj <= addr < obj + 0x188:
                return 'skill%d+%x' % (ident, addr - obj)
        return '%x' % addr

    # ---- coverage -----------------------------------------------------------------------------
    def coverage(self, name):
        start, end, leaders, _sites = self.parts[name]
        inside = {pc for pc in self.pcs if start <= pc < end}
        return len(leaders & inside), len(leaders), sorted(a for a in leaders if a not in self.pcs)


def compact(rig, addresses):
    names = sorted({rig.where(a) for a in addresses})
    return names[:10] + (['...'] if len(names) > 10 else [])


def build_skills(emu):
    """Construct the 33 skill objects with the game's own code: the class constructor the
    static initialiser 0x16ac74 would call on the object, then statistics slot 9.  The
    constructor addresses are not stored anywhere as data, so they are taken the way
    tools/dump_tables.py takes them: from the calls of that initialiser."""
    mem = emu.mem
    ctors = {}
    import dump_tables as DT
    elf = DT.Elf(open(OPTIONS['elf'], 'rb').read())

    def on_call(pc, target, state):
        a0 = state.get(4)
        if target and isinstance(a0, int):
            ctors[a0 & M32] = (target, state.get(5) if isinstance(state.get(5), int) else None)

    start, end = elf.func_range(DT.A['fn_skill_static_init'])
    DT.Scan(elf, on_call=on_call).run(start, end, {4: 1, 5: 0xFFFF}, follow=True)
    skills = {}
    saved = emu.follow
    emu.follow = set()                                  # the constructors' own call-outs: all stubbed
    for ident in SK.SKILL_IDS:
        obj = mem.u32(SK.G_SKILL_TABLE + 4 * ident)
        ctor, a1 = ctors[obj]
        emu.call(ctor, obj, a1 if a1 is not None else 0)
        table = mem.u32(obj + 0x60)
        emu.call(mem.u32(table + 8 * 9 + 4), obj)       # slot 9: the statistic tables
        skills[ident] = obj
    emu.follow = saved
    emu.reset_log()
    return skills


# ---------------------------------------------------------------------------------------
# Running scenarios and collecting what they find
# ---------------------------------------------------------------------------------------
class Test:
    """What a scenario function is handed: the rig, a seeded generator, and `do`, which
    runs one entry point on both sides and files the outcome under its key."""

    def __init__(self, rig, rng, tally):
        self.rig, self.world, self.rng, self.tally = rig, rig.world, rng, tally
        self.mem, self.skills = rig.emu.mem, rig.skills
        self.state = {}

    def do(self, key, *args):
        out = self.rig.compare(key, args, self.rng.getrandbits(32))
        count, bad, examples = self.tally.setdefault(key, [0, 0, []])
        self.tally[key][0] = count + 1
        problems = [k for k in ('fault', 'calls', 'writes', 'seed', 'result') if out[k]]
        if problems:
            self.tally[key][1] = bad + 1
            if len(examples) < 6:
                examples.append('; '.join('%s: %s' % (k, out[k]) for k in problems))
            if OPTIONS['trace_first']:
                print('first mismatch in %s%r' % (key, args))
                for k in problems:
                    print('   %s: %s' % (k, out[k]))
                print('   model calls:    ' + ' | '.join(DC.fmt_call(c) for c in out['model_calls'][:60]))
                print('   original calls: ' + ' | '.join(DC.fmt_call(c) for c in out['emu_calls'][:60]))
                sys.exit(1)
        self.state = out['state']
        return out['ret']

    def destroyed(self, obj):
        return obj in self.state.get('destroyed', ())

    def reps(self, count):
        return max(2, count // 5) if OPTIONS['quick'] else count

    def tick(self, frames=1):
        self.mem.w32(RC.G_SIM_FRAME, (self.mem.u32(RC.G_SIM_FRAME) + frames) & M32)

    def vec(self, addr):
        return tuple(self.mem.u32(addr + 4 * i) for i in range(3))


def report(name, bad, count, text, examples=()):
    ok = not bad
    RESULTS.append((name, ok))
    print('%s  %-40s %7d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % bad))
    if not ok and OPTIONS['verbose']:
        for line in examples[:6]:
            print('        ' + str(line)[:1500])
    sys.stdout.flush()


# ---------------------------------------------------------------------------------------
# Scenario: the statistics getters, exhaustively
# ---------------------------------------------------------------------------------------
def scenario_stats(t):
    """Slots 10, 11, 12, 13, 8, 14, 15 and the mana cost for all 33 ids, levels 0-40 (and
    a few beyond and below), statistics 0-4."""
    mem, world = t.mem, t.world
    player, monster = world.players[0], world.monsters[0]
    mem.w32(player + 0xC, 0x60)
    mem.w32(monster + 0xC, 0x20)
    handles = []
    for obj in (player, monster):
        node = t.rig.emu.alloc(0x20)
        cell = t.rig.emu.alloc(0x10)
        mem.w32(node + 0xC, obj)
        mem.w32(cell, node)
        handles.append(cell)
    handles.append(t.rig.emu.alloc(0x10))               # an empty handle
    spread = SK.F_0_2
    levels = list(range(0, 41)) + [41, 42, 60, 100, 127, -1, -3]
    for ident in SK.SKILL_IDS:
        skill = t.skills[ident]
        for level in levels:
            for stat in range(5):
                t.do('Skill_getStat', skill, stat, level)
                for cap in (0, 10, 20, 25):
                    t.do('Skill_getStatTier2', skill, stat, level, cap)
                for caster in (player, monster, 0):
                    t.do('Skill_getStatFor', skill, stat, level, caster, t.rng.choice((0, 10, 20, 25)))
                for handle in handles:
                    t.do('Skill_getStatForHandle', skill, stat, level, handle, t.rng.choice((0, 10, 20, 25)))
                t.do('Skill_getStatRange', skill, stat, level, 0, 0, 0, spread)
                t.do('Skill_getStatRange', skill, stat, level, 1, 0, 0, t.rng.choice((spread, f32(0.5), f32(1.5))))
            t.do('Skill_adjustLevel', skill, level, t.rng.choice((1, 2, 5, 10, 14, 20)))
            t.do('Skill_manaFromStat4', skill, level, 0x14)
            key = MANA_KEYS.get(mem.u32(mem.u32(skill + 0x60) + 8 * 5 + 4))
            if key:
                t.do(key, skill, level)
        t.do('Skill_canUse_default', skill, player)
        t.do('Skill_cast_default', skill, 3, player, t.vec(player + 0x10), 0)
    # made-up tables on the base class's own table: negative values, late first levels
    fake = t.rig.emu.alloc(0x70)
    mem.w32(fake + 0x60, SK.VT_SKILL)
    for _ in range(t.reps(400)):
        for stat in range(5):
            mem.w16(fake + 0x0E + 2 * stat, t.rng.choice((0, 1, 1, 5, 12)))
            mem.w16(fake + 0x18 + 2 * stat, t.rng.choice((0, 1, 7, 300, 0xFFFF, 0xFFD8, 0xFE00)))
            mem.w32(fake + 0x24 + 4 * stat, f32(t.rng.choice((0.0, 0.25, 1.0, 2.5, -0.75, -3.0, 0.3333))))
            mem.w16(fake + 0x38 + 2 * stat, t.rng.choice((0xFFFF, 0xFFFF, 0, 1, 3)))
            mem.w16(fake + 0x42 + 2 * stat, t.rng.choice((0, 2, 50, 0xFFF0)))
            mem.w32(fake + 0x4C + 4 * stat, f32(t.rng.choice((0.0, 1.0, 2.0, -1.5, 0.3299))))
        for level in (0, 1, 2, 7, 13, 40):
            for stat in range(5):
                t.do('Skill_getStat', fake, stat, level)
                t.do('Skill_getStatTier2', fake, stat, level, t.rng.choice((0, 5, 10)))
                t.do('Skill_getStatFor', fake, stat, level, t.rng.choice((player, monster, 0)), 10)
                t.do('Skill_getStatRange', fake, stat, level, t.rng.choice((0, 1)), 0, 0, spread)


MANA_KEYS = {0x3C82A8: 'Skill_manaCost_default'}       # mana-cost function -> entry key
SCENARIOS.append(('stats', 'statistics getters, 33 ids x levels x statistics', scenario_stats))


# ---------------------------------------------------------------------------------------
# 69 Retribution
# ---------------------------------------------------------------------------------------
entry('SkillRetribution_canUse', 0x3142BC, 0x3142F0, 'ii', 'i', 'retribution_can_use', '69 retribution')
entry('SkillRetribution_cast', 0x3142F0, 0x314390, 'iiivi', 'i', 'retribution_cast', '69 retribution')
entry('SkillRetribution_manaCost', 0x314454, 0x314488, 'ii', 'f', 'skill_mana_cost', '69 retribution')
body('SpellRetribution_ctor', 0x314488, 0x314618, '69 retribution')
entry('SpellRetribution_run', 0x314618, 0x314790, 'ivi', 'n', 'retribution_spell_run', '69 retribution')
entry('SpellRetribution_healOwner', 0x314790, 0x314888, 'if', 'f', 'retribution_heal_owner', '69 retribution')
MANA_KEYS[0x314454] = 'SkillRetribution_manaCost'


def cast_setup(t, ident, token=None, levels=None):
    """What most scenarios start with: fresh objects, a caster (player or monster), a
    level, the cast position and facing, and whether the caster already carries the
    skill's spell."""
    rng, world, mem = t.rng, t.world, t.mem
    world.reset_objects(rng)
    caster = world.creature(rng)
    level = rng.choice(levels or (1, 1, 2, 3, 5, 8, 10, 11, 15, 16, 20, 20, 30, 40))
    world.carried = {}
    if token is not None and rng.random() < 0.3:
        world.carried[(caster, token)] = world.monsters[7] + 0x400
    pos = t.vec(caster + 0x10)
    pos = (pos[0], pos[1], f32(fl(pos[2]) + rng.choice((0.0, 36.0, 42.0))))
    return t.skills[ident], caster, level, pos, mem.u16(caster + 0x38)


def scenario_retribution(t):
    rng, world = t.rng, t.world
    for _ in range(t.reps(40)):
        skill, caster, level, pos, facing = cast_setup(t, 69, SK.TYPEINFO['Retribution'])
        t.do('SkillRetribution_canUse', skill, caster)
        t.do('SkillRetribution_manaCost', skill, level)
        spell = t.do('SkillRetribution_cast', skill, level, caster, pos, facing)
        if not spell:
            continue
        world.busy.add(spell)
        cut = rng.random() < 0.3                        # the owner dies before the spell ends
        for frame in range(900):
            t.tick()
            if rng.random() < 0.08:
                t.do('SpellRetribution_healOwner', spell, f32(rng.choice((0.0, 1.0, 17.5, 250.0))))
                if rng.random() < 0.3:
                    t.mem.wf32(G_PLAYERS + rng.randrange(4) * REC_SIZE + 0xAC, rng.choice((0.0, 60.0, 119.5)))
            here = (f32(fl(pos[0]) + rng.uniform(-9, 9)), pos[1], pos[2])
            t.do('SpellRetribution_run', spell, here, facing)
            if t.destroyed(spell) or (cut and rng.random() < 0.01):
                break
        world.busy.discard(spell)


SCENARIOS.append(('69 retribution', 'cast, run to the end, heal', scenario_retribution))


# ---------------------------------------------------------------------------------------
# 94 Spirit Shield
# ---------------------------------------------------------------------------------------
entry('SkillSpiritShield_canUse', 0x314E1C, 0x314E50, 'ii', 'i', 'spiritshield_can_use', '94 spiritshield')
entry('SkillSpiritShield_cast', 0x314E50, 0x314EF0, 'iiivi', 'i', 'spiritshield_cast', '94 spiritshield')
entry('SkillSpiritShield_manaCost', 0x314FD8, 0x31500C, 'ii', 'f', 'skill_mana_cost', '94 spiritshield')
body('SpellSpiritShield_ctor', 0x31500C, 0x3151B4, '94 spiritshield')
entry('SpellSpiritShield_run', 0x3151B4, 0x31539C, 'ivi', 'n', 'spiritshield_spell_run', '94 spiritshield')
body('SpellSpiritShield_dissolveParticles', 0x31539C, 0x315610, '94 spiritshield')
body('SpellSpiritShield_reformParticles', 0x315610, 0x315888, '94 spiritshield')
entry('SpellSpiritShield_rollAbsorb', 0x315888, 0x3159D8, 'i', 'i', 'spiritshield_roll_absorb', '94 spiritshield')
MANA_KEYS[0x314FD8] = 'SkillSpiritShield_manaCost'


def _on_creature_v16(self, args, view, rng):
    return Res(self.model_ptr)


World.on_Creature_v16 = _on_creature_v16


def scenario_spiritshield(t):
    rng, world = t.rng, t.world
    for _ in range(t.reps(25)):
        skill, caster, level, pos, facing = cast_setup(t, 94, SK.TYPEINFO['SpiritShield'])
        t.do('SkillSpiritShield_canUse', skill, caster)
        t.do('SkillSpiritShield_manaCost', skill, level)
        spell = t.do('SkillSpiritShield_cast', skill, level, caster, pos, facing)
        if not spell:
            continue
        world.busy.add(spell)
        cut = rng.random() < 0.5
        hits = rng.choice((0.01, 0.05, 0.3))            # how often something hits the owner
        for frame in range(rng.choice((120, 700, 1300))):
            t.tick()
            if rng.random() < hits:
                t.do('SpellSpiritShield_rollAbsorb', spell)
            t.do('SpellSpiritShield_run', spell, pos, facing)
            if t.destroyed(spell) or (cut and rng.random() < 0.01):
                break
        world.busy.discard(spell)


SCENARIOS.append(('94 spiritshield', 'cast, run through the four phases, absorb rolls', scenario_spiritshield))


# ---------------------------------------------------------------------------------------
# 96 Frost Armor
# ---------------------------------------------------------------------------------------
entry('SkillFrostArmor_canUse', 0x317AFC, 0x317B30, 'ii', 'i', 'frostarmor_can_use', '96 frostarmor')
entry('SkillFrostArmor_cast', 0x317B30, 0x317BD0, 'iiivi', 'i', 'frostarmor_cast', '96 frostarmor')
entry('SkillFrostArmor_manaCost', 0x317CE8, 0x317D1C, 'ii', 'f', 'skill_mana_cost', '96 frostarmor')
body('SpellFrostArmor_ctor', 0x317D1C, 0x317EC0, '96 frostarmor')
entry('SpellFrostArmor_run', 0x317EC0, 0x318264, 'ivi', 'n', 'frostarmor_spell_run', '96 frostarmor')
entry('SpellFrostArmor_onHit', 0x318264, 0x3184EC, 'iif', 'f', 'frostarmor_on_hit', '96 frostarmor')
MANA_KEYS[0x317CE8] = 'SkillFrostArmor_manaCost'


def scenario_frostarmor(t):
    rng, world = t.rng, t.world
    for _ in range(t.reps(30)):
        # Cazic casts it with the whole monster level: statistic 1 passes 100 percent there
        skill, caster, level, pos, facing = cast_setup(t, 96, SK.TYPEINFO['FrostArmor'],
                                                       (1, 1, 2, 3, 5, 9, 14, 20, 36, 71, 81, 100, 127))
        t.do('SkillFrostArmor_canUse', skill, caster)
        t.do('SkillFrostArmor_manaCost', skill, level)
        spell = t.do('SkillFrostArmor_cast', skill, level, caster, pos, facing)
        if not spell:
            continue
        world.busy.add(spell)
        cut = rng.random() < 0.5
        hits = rng.choice((0.02, 0.1, 0.5))
        for frame in range(rng.choice((60, 300, 1300))):
            t.tick()
            if rng.random() < hits:
                attacker = rng.choice([0] + world.objects)
                t.do('SpellFrostArmor_onHit', spell, attacker, f32(rng.choice((0.0, 0.4, 1.0, 17.5, 250.0, 40000.0))))
            t.do('SpellFrostArmor_run', spell, pos, facing)
            if t.destroyed(spell) or (cut and rng.random() < 0.01):
                break
        world.busy.discard(spell)


SCENARIOS.append(('96 frostarmor', 'cast, run to the end, hits with and without an attacker', scenario_frostarmor))


# ---------------------------------------------------------------------------------------
# 95 Wave of Flame
# ---------------------------------------------------------------------------------------
entry('SkillWaveOfFlame_canUse', 0x316B1C, 0x316B24, 'ii', 'i', 'waveofflame_can_use', '95 waveofflame')
entry('SkillWaveOfFlame_cast', 0x316B24, 0x316BDC, 'iiivi', 'i', 'waveofflame_cast', '95 waveofflame')
entry('SkillWaveOfFlame_manaCost', 0x316CDC, 0x316D10, 'ii', 'f', 'skill_mana_cost', '95 waveofflame')
body('SpellWaveOfFlame_ctor', 0x316D10, 0x317000, '95 waveofflame')
entry('SpellWaveOfFlame_run', 0x317000, 0x317570, 'ivi', 'n', 'waveofflame_spell_run', '95 waveofflame')
entry('SpellWaveOfFlame_hitTest', 0x317570, 0x317868, 'if', 'n', 'waveofflame_hit_test', '95 waveofflame')
MANA_KEYS[0x316CDC] = 'SkillWaveOfFlame_manaCost'


def churn(t, chance=0.05):
    """What the rest of the game does to the bystanders between two ticks: one moves, one
    dies, one changes its mind about being solid."""
    rng, world, mem = t.rng, t.world, t.mem
    if rng.random() < chance:
        obj = rng.choice(world.objects)
        mem.wf32(obj + 0x10, mem.f32(obj + 0x10) + rng.uniform(-40, 40))
        mem.wf32(obj + 0x14, mem.f32(obj + 0x14) + rng.uniform(-40, 40))
    if rng.random() < chance:
        obj = rng.choice(world.objects)
        mem.w32(obj + 0xC, mem.u32(obj + 0xC) ^ rng.choice((1, 8, 8)))


def scenario_waveofflame(t):
    rng, world = t.rng, t.world
    for _ in range(t.reps(12)):
        skill, caster, level, pos, facing = cast_setup(t, 95)
        t.do('SkillWaveOfFlame_canUse', skill, caster)
        t.do('SkillWaveOfFlame_manaCost', skill, level)
        spell = t.do('SkillWaveOfFlame_cast', skill, level, caster, pos, facing)
        if not spell:
            continue
        world.busy.add(spell)
        cut = rng.random() < 0.3
        for frame in range(200):
            t.tick()
            churn(t)
            t.do('SpellWaveOfFlame_run', spell, pos, facing)
            if t.destroyed(spell) or (cut and rng.random() < 0.03):
                break
        t.rig.emu.call(0x1A1698, spell + 0x18)          # what the destructor does to the list
        world.busy.discard(spell)


SCENARIOS.append(('95 waveofflame', 'cast, the ring to its end, hits on creatures and props', scenario_waveofflame))


# ---------------------------------------------------------------------------------------
# 70 Unspoken Word
# ---------------------------------------------------------------------------------------
entry('SkillUnspokenWord_cast', 0x2FD030, 0x2FD1DC, 'iiivi', 'i', 'unspokenword_cast', '70 unspokenword')
entry('SkillUnspokenWord_manaCost', 0x2FD334, 0x2FD368, 'ii', 'f', 'skill_mana_cost', '70 unspokenword')
body('SpellUnspokenWord_ctor', 0x2FD368, 0x2FD550, '70 unspokenword')
entry('SpellUnspokenWord_run', 0x2FD5D4, 0x2FDDF0, 'ivi', 'n', 'unspokenword_spell_run', '70 unspokenword')
entry('SpellUnspokenWord_hitRing', 0x2FDDF0, 0x2FE068, 'if', 'n', 'unspokenword_hit_ring', '70 unspokenword')
MANA_KEYS[0x2FD334] = 'SkillUnspokenWord_manaCost'


def _on_trail_create(self, args, view, rng):
    return Res(rng.choice((0, 1, 2, 3, 0xFFFFFFFF)))


World.on_trail_create = _on_trail_create


def scenario_unspokenword(t):
    rng, world, mem = t.rng, t.world, t.mem
    for _ in range(t.reps(24)):
        skill, caster, level, pos, facing = cast_setup(t, 70)
        t.do('SkillUnspokenWord_manaCost', skill, level)
        spell = t.do('SkillUnspokenWord_cast', skill, level, caster, pos, facing)
        if not spell:
            continue
        world.busy.add(spell)
        cut = rng.random() < 0.25
        for frame in range(40):
            t.tick(rng.choice((1, 1, 1, 1, 2)))
            churn(t)
            if rng.random() < 0.1:                      # the ring anywhere, on its own
                t.do('SpellUnspokenWord_hitRing', spell, f32(rng.choice((0.0, 30.0, 90.0, 400.0))))
            t.do('SpellUnspokenWord_run', spell, pos, facing)
            if t.destroyed(spell) or (cut and rng.random() < 0.05):
                break
        t.rig.emu.call(0x1A1698, spell + 0x1C)
        world.busy.discard(spell)


SCENARIOS.append(('70 unspokenword', 'cast, the ring through 30 frames, stun rolls behind particle draws',
                  scenario_unspokenword))


# ---------------------------------------------------------------------------------------
# 100 Lightning Strike and 80 Pus Storm
# ---------------------------------------------------------------------------------------
entry('SkillLightningStrike_cast', 0x31A920, 0x31ACA8, 'iiivi', 'i', 'lightningstrike_cast', '100 lightningstrike')
entry('SkillLightningStrike_manaCost', 0x31AE14, 0x31AE48, 'ii', 'f', 'skill_mana_cost', '100 lightningstrike')
body('LightningStrikeSpell_ctor', 0x31AE48, 0x31B1CC, '100 lightningstrike')
entry('LightningStrikeSpell_run', 0x31B25C, 0x31B7F4, 'i', 'n', 'lightningstrike_run', '100 lightningstrike')
entry('SkillPusStorm_cast', 0x30AAA8, 0x30ADF8, 'iiivi', 'i', 'pusstorm_cast', '80 pusstorm')
entry('SkillPusStorm_manaCost', 0x30AF38, 0x30AF6C, 'ii', 'f', 'skill_mana_cost', '80 pusstorm')
body('PusStorm_ctor', 0x30AF6C, 0x30B398, '80 pusstorm')
entry('PusStorm_run', 0x30B428, 0x30BB38, 'i', 'n', 'pusstorm_run', '80 pusstorm')
body('Pustule_ctor', 0x30BB38, 0x30BC88, '80 pusstorm')
MANA_KEYS[0x31AE14] = 'SkillLightningStrike_manaCost'
MANA_KEYS[0x30AF38] = 'SkillPusStorm_manaCost'


def _on_gameobject_ctor(self, args, view, rng):
    """What the base constructor leaves: the position, an own generator, zero flags."""
    obj, pos = args[0], args[1]
    for i in range(3):
        view.poke(obj + 0x10 + 4 * i, 4, pos[i])
    view.poke(obj + 0xC, 4, rng.choice((0, 0, 0x10000)))
    view.poke(obj + 0x1C, 4, f32(12.0))
    view.poke(obj + 0x44, 4, rng.getrandbits(32))
    return Res()


def _on_creature_v1(self, args, view, rng):
    view.state.setdefault('destroyed', []).append(args[0])
    return Res()


World.on_GameObject_ctor = _on_gameobject_ctor
World.on_Creature_v1 = _on_creature_v1


def scenario_storm(ident, cast_key, run_key, handle):
    def scenario(t):
        rng, world, mem = t.rng, t.world, t.mem
        size = 0xBC if ident == 100 else 0xC0
        for index in range(t.reps(22)):
            # levels 40 and 41 make the decoration interval 0, 42 and up make it negative
            levels = (1, 2, 5, 9, 10, 14, 20, 20, 26, 39, 40, 41, 42, 60)
            skill, caster, level, pos, facing = cast_setup(t, ident, None, levels)
            world.pool_fail = 0.0 if index % 4 else 0.3
            t.do('Skill%s_manaCost' % cast_key, skill, level)
            before = {b for b in world.pool.get(size, ())}
            t.do('Skill%s_cast' % cast_key, skill, level, caster, pos, rng.choice((facing, facing | 0xFFFF0000)))
            taken = [b for b in t.state.get('taken', ()) if world.block_size.get(b) == size and mem.u32(b + 0x48)]
            world.pool_fail = 0.05
            if not taken:
                continue
            storm = taken[0]
            world.busy.add(storm)
            cut = rng.random() < 0.3
            for frame in range(1200):
                t.tick()
                churn(t, 0.02)
                if cut and rng.random() < 0.004:        # the owner is destroyed: its handles empty
                    t.rig.emu.call(0x1A1698, storm + handle)
                t.do(run_key, storm)
                if t.destroyed(storm):
                    break
            t.rig.emu.call(0x1A1698, storm + handle)
            world.busy.discard(storm)
    return scenario


SCENARIOS.append(('100 lightningstrike', 'cast by players and monsters, the storm to its last frame',
                  scenario_storm(100, 'LightningStrike', 'LightningStrikeSpell_run', 0x7C)))
SCENARIOS.append(('80 pusstorm', 'cast by players and monsters, the storm to its last frame',
                  scenario_storm(80, 'PusStorm', 'PusStorm_run', 0x80)))


# ---------------------------------------------------------------------------------------
# 101 Cone of Shock
# ---------------------------------------------------------------------------------------
entry('SkillConeOfShock_cast', 0x31B8F0, 0x31B990, 'iiivi', 'i', 'coneofshock_cast', '101 coneofshock')
entry('SkillConeOfShock_manaCost', 0x31BA94, 0x31BAC8, 'ii', 'f', 'skill_mana_cost', '101 coneofshock')
body('SpellConeOfShock_ctor', 0x31BAC8, 0x31BC50, '101 coneofshock')
entry('SpellConeOfShock_run', 0x31BCD0, 0x31C2A0, 'ivi', 'n', 'coneofshock_spell_run', '101 coneofshock')
MANA_KEYS[0x31BA94] = 'SkillConeOfShock_manaCost'


def _on_sound_at(self, args, view, rng):
    return Res(rng.choice((0, 3, 17, 0xFFFFFFFF)))


World.on_sound_playAtPos = _on_sound_at


def scenario_coneofshock(t):
    rng, world, mem = t.rng, t.world, t.mem
    for _ in range(t.reps(30)):
        # the Hag passes its slot 35, trunc(monster level x 0.3): 0 for the first levels
        skill, caster, level, pos, facing = cast_setup(t, 101, None, (0, 1, 1, 2, 3, 4, 7, 8, 12, 16, 20, 25, 26, 40))
        t.do('SkillConeOfShock_manaCost', skill, level)
        spell = t.do('SkillConeOfShock_cast', skill, level, caster, pos, facing)
        if not spell:
            continue
        world.busy.add(spell)
        for frame in range(rng.choice((20, 60, 200))):  # until the Hag's next state change removes it
            t.tick(rng.choice((1, 1, 1, 2)))
            churn(t)
            if rng.random() < 0.1:
                facing = rng.randrange(0x10000)
            here = (pos[0], pos[1], f32(fl(pos[2]) + rng.choice((0.0, 36.0))))
            t.do('SpellConeOfShock_run', spell, here, rng.choice((facing, facing | 0xFFFF0000)))
        world.busy.discard(spell)


SCENARIOS.append(('101 coneofshock', 'cast, the cone tick by tick, the range draws behind the decoration draw',
                  scenario_coneofshock))


# ---------------------------------------------------------------------------------------
# 88 Drowsy
# ---------------------------------------------------------------------------------------
entry('SkillDrowsy_cast', 0x30E1F0, 0x30E4C4, 'iiivi', 'i', 'drowsy_cast', '88 drowsy')
entry('SkillDrowsy_manaCost', 0x30E5EC, 0x30E620, 'ii', 'f', 'skill_mana_cost', '88 drowsy')
body('SpellDrowsy_ctor', 0x30E620, 0x30E6F0, '88 drowsy')
entry('SpellDrowsy_run', 0x30E6F0, 0x30ED24, 'ivi', 'n', 'drowsy_spell_run', '88 drowsy')
entry('SpellDrowsy_getStat3Fraction', 0x30EF08, 0x30EF58, 'i', 'f', 'drowsy_fraction', '88 drowsy')
MANA_KEYS[0x30E5EC] = 'SkillDrowsy_manaCost'


def _on_boss_rank(self, args, view, rng):
    return Res(rng.choice((0, 0, 0, 0, 0, 1, 2)))


def _on_add_spell(self, args, view, rng):
    view.state.setdefault('added', []).append((args[0], args[1]))
    return Res()


World.on_creature_bossRank = _on_boss_rank
World.on_creature_addSpell = _on_add_spell


def scenario_drowsy(t):
    rng, world, mem = t.rng, t.world, t.mem
    for index in range(t.reps(16)):
        skill, caster, level, pos, facing = cast_setup(t, 88)
        for obj in world.objects:                       # some already slowed, some friendly to players
            mem.w16(obj + 0x31A, rng.choice((0, 0, 0, 0, 1, 250, 0xFFFF)))
            if rng.random() < 0.1:
                mem.w32(obj + 0xC, mem.u32(obj + 0xC) | 0x1000000)
        t.do('SkillDrowsy_manaCost', skill, level)
        t.do('SkillDrowsy_cast', skill, level, caster, pos, rng.choice((facing, facing | 0xFFFF0000)))
        victims = [(obj, spell) for obj, spell in t.state.get('added', ()) if spell]
        mem.w8(SK.G_NETWORK_MODE, rng.choice((0, 1)))
        for obj, spell in victims[:3]:
            world.busy.add(spell)
        for obj, spell in victims[:3]:
            cut = rng.random() < 0.2
            for frame in range(700):
                t.tick()
                if cut and rng.random() < 0.02:         # the victim dies
                    mem.w32(obj + 0xC, mem.u32(obj + 0xC) | 8)
                t.do('SpellDrowsy_run', spell, pos, facing)
                if rng.random() < 0.02:
                    t.do('SpellDrowsy_getStat3Fraction', spell)
                if t.destroyed(spell):
                    break
            world.busy.discard(spell)
    mem.w8(SK.G_NETWORK_MODE, 0)


SCENARIOS.append(('88 drowsy', 'cast on a crowd, each victim spell through wind-up, roll and effect', scenario_drowsy))


# ---------------------------------------------------------------------------------------
# 89 Poison Bolt
# ---------------------------------------------------------------------------------------
entry('SkillPoisonBolt_cast', 0x30F168, 0x30F23C, 'iiivi', 'i', 'poisonbolt_cast', '89 poisonbolt')
entry('SkillPoisonBolt_manaCost', 0x30F364, 0x30F398, 'ii', 'f', 'skill_mana_cost', '89 poisonbolt')
entry('PoisonBolt_ctor', 0x30F398, 0x30F608, 'iviiii', 'n', 'poisonbolt_ctor', '89 poisonbolt')
entry('PoisonBolt_run', 0x30F800, 0x310028, 'i', 'n', 'poisonbolt_run', '89 poisonbolt')
entry('PoisonBolt_onHit', 0x310028, 0x3101CC, 'ii', 'n', 'poisonbolt_on_hit', '89 poisonbolt')
entry('PoisonBolt_burst', 0x3101CC, 0x310440, 'i', 'n', 'poisonbolt_burst', '89 poisonbolt')
MANA_KEYS[0x30F364] = 'SkillPoisonBolt_manaCost'


def _on_projectile_ctor(self, args, view, rng):
    """The base constructor: position, flags, radius, own generator, and the owner handle
    at +0x4c (a node whose object is the owner, or nothing)."""
    obj, pos, owner = args[0], args[1], args[2]
    for i in range(3):
        view.poke(obj + 0x10 + 4 * i, 4, pos[i])
    view.poke(obj + 0xC, 4, 0x4081)
    view.poke(obj + 0x1C, 4, f32(12.0))
    view.poke(obj + 0x44, 4, rng.getrandbits(32))
    if owner:
        view.poke(self.owner_node + 0xC, 4, owner)
        view.poke(obj + 0x4C, 4, self.owner_node)
    return Res()


def _on_move_and_collide(self, args, view, rng):
    """One step: the object moves, and now and then hits the ground or touches something
    (the touch handler itself is exercised on its own)."""
    obj, vel = args[0], args[1]
    for i in range(3):
        view.poke(obj + 0x10 + 4 * i, 4, f32(fl(rd(view, obj + 0x10 + 4 * i)) + fl(vel[i]) / 60.0))
    result = rng.choice((0,) * 70 + (1, 2, 2, 2, 3))
    if result & 2 and rng.random() < 0.5:
        view.poke(obj + 0xB4, 4, 1)
    return Res(result)


World.on_Projectile_ctor = _on_projectile_ctor
World.on_obj_moveAndCollide = _on_move_and_collide


def scenario_poisonbolt(t):
    rng, world, mem = t.rng, t.world, t.mem
    if not hasattr(world, 'owner_node'):
        world.owner_node = t.rig.emu.alloc(0x20)
    for index in range(t.reps(10)):
        skill, caster, level, pos, facing = cast_setup(t, 89)
        world.pool_fail = 0.0
        t.do('SkillPoisonBolt_manaCost', skill, level)
        if index % 3 == 2:                              # a bolt nobody owns, and one aimed nowhere
            bolt = world.on_pool_new((0xB8,), t.rig.eview, rng).ret
            t.rig.eview.state = {}
            world.query = [] if rng.random() < 0.5 else None
            t.do('PoisonBolt_ctor', bolt, pos, facing, level, rng.choice((0, caster)), skill)
        else:
            t.do('SkillPoisonBolt_cast', skill, level, caster, pos, rng.choice((facing, facing | 0xFFFF0000)))
            taken = [b for b in t.state.get('taken', ()) if world.block_size.get(b) == 0xB8]
            if not taken:
                continue
            bolt = taken[0]
        world.query = None
        world.busy.add(bolt)
        for frame in range(120):
            t.tick()
            churn(t, 0.1)
            if rng.random() < 0.08:                     # something touches the bolt
                t.do('PoisonBolt_onHit', bolt, rng.choice(world.objects))
            if rng.random() < 0.05:
                mem.w32(bolt + 0xB4, 0)
            t.do('PoisonBolt_run', bolt)
            if t.destroyed(bolt):
                break
        for head in (0x90, 0x94):
            t.rig.emu.call(0x1A1698, bolt + head)
        world.busy.discard(bolt)
        world.pool_fail = 0.05
    # the burst on its own: with and without an owner, with and without a pool block
    for _ in range(t.reps(8)):
        skill, caster, level, pos, facing = cast_setup(t, 89, None, (0, 1, 3, 20))
        bolt = world.on_pool_new((0xB8,), t.rig.eview, rng).ret
        if not bolt:
            continue
        t.rig.eview.state = {}
        t.do('PoisonBolt_ctor', bolt, pos, facing, level, rng.choice((0, caster, caster)), skill)
        world.busy.add(bolt)
        world.pool_fail = 0.5
        for _hit in range(4):
            mem.w32(bolt + 0xB4, rng.choice((0, 0, 0, 1)))
            t.do('PoisonBolt_onHit', bolt, rng.choice(world.objects))
        t.do('PoisonBolt_burst', bolt)
        world.pool_fail = 0.05
        for head in (0x90, 0x94):
            t.rig.emu.call(0x1A1698, bolt + head)
        world.busy.discard(bolt)


SCENARIOS.append(('89 poisonbolt', 'cast, flight with homing, touches, the burst', scenario_poisonbolt))


# ---------------------------------------------------------------------------------------
# 76 Roar
# ---------------------------------------------------------------------------------------
entry('SkillRoar_canUse', 0x2FFF64, 0x2FFF98, 'ii', 'i', 'roar_can_use', '76 roar')
entry('SkillRoar_cast', 0x2FFF98, 0x300038, 'iiivi', 'i', 'roar_cast', '76 roar')
entry('SkillRoar_manaCost', 0x300138, 0x30016C, 'ii', 'f', 'skill_mana_cost', '76 roar')
body('SpellRoar_ctor', 0x30016C, 0x3003D8, '76 roar')
entry('SpellRoar_run', 0x3003D8, 0x300F54, 'ivi', 'n', 'roar_spell_run', '76 roar')
entry('SpellRoar_hitRing', 0x300F54, 0x3010F4, 'if', 'n', 'roar_hit_ring', '76 roar')
MANA_KEYS[0x300138] = 'SkillRoar_manaCost'


def shout_setup(t, ident, token, levels=None):
    """A player about to shout: any weapon style, some mana, the record of its slot."""
    rng, world, mem = t.rng, t.world, t.mem
    world.reset_objects(rng, spread=rng.choice((50, 50, 120, 400)))
    caster = rng.choice(world.players)
    mem.w32(caster + 0xC, 0x60)
    level = rng.choice(levels or (1, 2, 4, 5, 9, 10, 14, 20, 20, 40))
    rec = G_PLAYERS + mem.u32(caster + 0x3C8) * REC_SIZE
    mem.w8(rec + 0x4A86, rng.choice((0, 1, 2, 3, 4, 5, 6, 7, 9, 0xFF)))
    mem.wf32(rec + 0xC0, rng.choice((0.0, 50.0, 119.0, 120.0)))
    mem.wf32(rec + 0xC4, 120.0)
    mem.w8(SK.G_NETWORK_MODE, rng.choice((0, 0, 1)))
    world.carried = {}
    if rng.random() < 0.3:
        world.carried[(caster, token)] = world.monsters[7] + 0x400
    return t.skills[ident], caster, level, t.vec(caster + 0x10), mem.u16(caster + 0x38)


def scenario_roar(t):
    rng, world, mem = t.rng, t.world, t.mem
    for index in range(t.reps(12)):
        skill, caster, level, pos, facing = shout_setup(t, 76, SK.TYPEINFO['Roar'])
        t.do('SkillRoar_canUse', skill, caster)
        t.do('SkillRoar_manaCost', skill, level)
        spell = t.do('SkillRoar_cast', skill, level, caster, pos, facing)
        if not spell:
            continue
        world.busy.add(spell)
        plan = index % 4                                # 0, 1: the shout runs; 2: interrupted; 3: never ends
        shout_at = rng.randrange(2, 12)
        quiet_at = shout_at + rng.randrange(8, 40)
        interrupt = rng.choice((1, shout_at + 3, shout_at + 20)) if plan == 2 else None
        for frame in range(420):
            t.tick()
            churn(t, 0.1)
            world.anim_event = 2 if frame == shout_at else 4 if frame == quiet_at else \
                rng.choice((0, 0, 0, 0, 1, 6, 8))
            world.anim_end = 0.2 if frame > quiet_at + 8 and plan != 3 else 0.0
            if frame == interrupt:
                mem.w32(caster + 0x58C, rng.choice((2, 3, 5)))
            t.do('SpellRoar_run', spell, pos, rng.choice((facing, facing | 0xFFFF0000)))
            if t.destroyed(spell):
                break
        t.rig.emu.call(0x1A1698, spell + 0x1C)
        world.busy.discard(spell)
    world.anim_end, world.anim_event = 0.01, None
    mem.w8(SK.G_NETWORK_MODE, 0)


SCENARIOS.append(('76 roar', 'cast, the shout animation with its events, the wave, interruption and refund',
                  scenario_roar))


# ---------------------------------------------------------------------------------------
# 77 Battle Cry
# ---------------------------------------------------------------------------------------
entry('SkillBattleCry_canUse', 0x301464, 0x301498, 'ii', 'i', 'battlecry_can_use', '77 battlecry')
entry('SkillBattleCry_cast', 0x301498, 0x301538, 'iiivi', 'i', 'battlecry_cast', '77 battlecry')
entry('SkillBattleCry_manaCost', 0x3016E0, 0x301714, 'ii', 'f', 'skill_mana_cost', '77 battlecry')
body('SpellBattleCry_ctor', 0x301714, 0x301A34, '77 battlecry')
entry('SpellBattleCry_run', 0x301A34, 0x302BD0, 'ivi', 'n', 'battlecry_spell_run', '77 battlecry')
entry('SpellBattleCry_setTint', 0x302BD0, 0x302C04, 'ii', 'n', 'battlecry_set_tint', '77 battlecry')
entry('SpellBattleCry_affects', 0x302C04, 0x302D3C, 'iiW', 'iw', 'battlecry_affects', '77 battlecry')
body('mat34_setPosRotZ', 0x163B30, 0x163CB8, 'shared')
body('mat34_transformPoint', 0x1660A0, 0x166160, 'shared')
MANA_KEYS[0x3016E0] = 'SkillBattleCry_manaCost'


def _on_height_at_point(self, args, view, rng):
    return Res(f=f32(fl(args[1][2]) + rng.choice((0.0, 3.0, -8.0, 40.0, 71.9, 72.5, -72.0, -90.0, 200.0))))


World.on_terrain_heightAtPoint = _on_height_at_point


def alive_players(t):
    """The alive-player list (slots) and PvP mode A, any way round."""
    rng, mem, world = t.rng, t.mem, t.world
    slots = [s for s in range(4) if rng.random() < 0.8]
    rng.shuffle(slots)
    mem.w32(SK.G_ALIVE_COUNT, len(slots))
    for i, slot in enumerate(slots):
        mem.w32(SK.G_ALIVE_LIST + 4 * i, slot)
    mem.w32(SK.G_PVP_MODE_A, rng.choice((0, 0, 1)))
    if rng.random() < 0.1:                              # a slot whose player object is gone
        mem.w32(G_PLAYERS + rng.randrange(4) * REC_SIZE + REC_OBJ, 0)


def restore_players(t):
    for slot in range(4):
        t.mem.w32(G_PLAYERS + slot * REC_SIZE + REC_OBJ, t.world.players[slot])
    t.mem.w32(SK.G_PVP_MODE_A, 0)


def scenario_battlecry(t):
    rng, world, mem = t.rng, t.world, t.mem
    for index in range(t.reps(10)):
        levels = (1,) if index == 0 else None
        skill, caster, level, pos, facing = shout_setup(t, 77, SK.TYPEINFO['BattleCry'], levels)
        alive_players(t)
        t.do('SkillBattleCry_canUse', skill, caster)
        t.do('SkillBattleCry_manaCost', skill, level)
        spell = t.do('SkillBattleCry_cast', skill, level, caster, pos, facing)
        if not spell:
            restore_players(t)
            continue
        world.busy.add(spell)
        plan = index % 4                                # 0: to its natural end; 1, 3: cut short; 2: interrupted
        on_at = rng.randrange(1, 6)
        cry_at = on_at + rng.randrange(3, 30)
        off_at = cry_at + rng.randrange(-2, 30)
        interrupt = rng.choice((0, cry_at - 1, cry_at + 5)) if plan == 2 else None
        last = 1600 if plan == 0 else rng.randrange(cry_at + 2, cry_at + 70)
        for frame in range(last):
            t.tick()
            churn(t, 0.1)
            world.anim_event = 2 if frame == on_at else 8 if frame == cry_at else 4 if frame == off_at else \
                rng.choice((0, 0, 0, 0, 1, 6, 10))
            world.anim_end = 0.1 if frame > off_at + 5 else 0.0
            if frame == interrupt:
                mem.w32(caster + 0x58C, rng.choice((2, 3, 5)))
            here = (f32(fl(pos[0]) + rng.uniform(-3, 3)), pos[1], f32(fl(pos[2]) + 40.0))
            t.do('SpellBattleCry_run', spell, here, facing)
            if rng.random() < 0.05:                     # what Player_run asks for a swinging player
                t.do('SpellBattleCry_affects', spell, rng.choice([0, caster] + world.players), 0)
            if t.destroyed(spell):
                break
        t.do('SpellBattleCry_setTint', spell, rng.choice(world.objects))
        world.busy.discard(spell)
        restore_players(t)
    world.anim_end, world.anim_event = 0.01, None
    mem.w8(SK.G_NETWORK_MODE, 0)


SCENARIOS.append(('77 battlecry', 'cast, the three events, streamers, the cry with its stun rolls, the aura',
                  scenario_battlecry))


# @@SECTIONS@@


# ---------------------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------------------
def main(argv):
    args = [a for a in argv[1:]]
    path = None
    while args:
        a = args.pop(0)
        if a == '--quick':
            OPTIONS['quick'] = True
        elif a == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif a == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif a == '-v':
            OPTIONS['verbose'] = True
        elif a == '--fpu':
            OPTIONS['fpu'] = args.pop(0)
        elif a == '--trace-first':
            OPTIONS['trace_first'] = True
        elif a in ('-h', '--help'):
            print(__doc__)
            return 0
        else:
            path = a
    if path is None:
        path = os.path.join(ROOT, 'SLUS_209.73')
    if not os.path.exists(path):
        print('SKIP  no executable at %s: nothing compared (give the path to your own SLUS_209.73)' % path)
        return 0
    digest = hashlib.sha256(open(path, 'rb').read()).hexdigest()
    if digest != DC.EXPECTED_SHA256:
        print('SKIP  %s is not SLUS_209.73 US v2.00 (sha256 %s): the addresses would not fit' % (path, digest))
        return 0
    OPTIONS['elf'] = path
    started = time.time()
    rig = Rig(path, OPTIONS['seed'])
    tally = {}
    ran = []
    for index, (group, title, function) in enumerate(SCENARIOS):
        wanted = OPTIONS['filter']
        if wanted and wanted not in group and wanted not in title:
            continue
        test = Test(rig, random.Random(OPTIONS['seed'] * 1000 + index), tally)
        function(test)
        if group not in ran:
            ran.append(group)
    for group in ran + [g for g in ('shared',) if ran]:
        names = GROUPS.get(group, [])
        covered = total = 0
        for name in names:
            got, of, missing = rig.coverage(name)
            covered, total = covered + got, total + of
            if name in tally:
                count, bad, examples = tally[name]
                report('%s %s' % (group, name), bad, count, 'blocks %d/%d' % (got, of), examples)
            elif got == 0 and name in ENTRIES:
                report('%s %s' % (group, name), 1, 0, 'never executed')
            if OPTIONS['verbose'] and missing and got:
                print('        %s: blocks never entered: %s' % (name, ' '.join('%x' % a for a in missing[:40])))
        executed = sum(1 for name in names if rig.coverage(name)[0])
        print('      %-12s functions executed %d/%d, basic blocks covered %d/%d' % (group, executed, len(names),
                                                                                   covered, total))
    for note, count in sorted(rig.notes.items()):
        print('      note: %s, %d times (the remainder left is the interpreter\'s rule, not a console\'s)' % (note, count))
    if rig.unknown:
        report('calls to unknown addresses', len(rig.unknown), sum(rig.unknown.values()),
               ' '.join('%x' % a for a in sorted(rig.unknown)))
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d failed, %.0f s' % (len(RESULTS), len(failed), time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
