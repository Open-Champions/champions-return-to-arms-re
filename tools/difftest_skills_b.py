#!/usr/bin/env python3
"""difftest_skills_b.py - compare tools/ref_skills_b.py with the game's own code for the
skills with ids 35-68: the Skill / Spell / projectile machinery they share, the statistics
of every id at every level, and each skill's can-use, cast, per-tick run and hit handling.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_skills_b.py [path/to/SLUS_209.73] [--quick] [--seed N] [-k TEXT]
                                     [-v] [--fpu MODEL] [--trace-first]

    --quick       a tenth of the random scenarios, a quarter of the statistic sweep
    --seed N      seed of the random scenarios (default 3568); a seed repeats exactly
    -k TEXT       only the sections whose name contains TEXT (stats, base, sb1, timers, or
                  a skill name such as cyclone)
    -v            print the first mismatches of every failing property and the basic
                  blocks never entered
    --fpu MODEL   ps2 (default), ps2g1, chop or nearest: the adder model of BOTH sides
    --trace-first stop at the first mismatching call and print both sides

What is compared
    The ORIGINAL functions listed in ref_skills_b.FUNCTIONS are executed by
    tools/ee_emu.py - an instruction interpreter, not a console - on objects the original
    constructors built, in a world this script constructs.  Every call is run through the
    model first, on a copy-on-write view of the same memory, and these must be equal:
      calls    the sequence of calls to everything outside the model, with arguments
      writes   the set of bytes stored outside the stack, and their final values (the
               spell's and the object's own generator state, the presentation generators
               0x404460 and 0x404468 and the handle-node pool are ordinary memory here)
      seed     the shared seed 0x404464, and that it advanced exactly as many times as the
               model says it drew
      result   the value returned
    Floats are compared as 32-bit patterns under the interpreter's floating-point model.

What runs for real and what is a stub
    Real: ref_skills_b.FUNCTIONS (which includes the handle-list functions, the list
    iterator, Spell_rand, GameObject_rand, Projectile_ctor and obj_moveAndCollide), the
    three angle functions and the C library.  The Skill objects are the executable's own:
    the script runs its static initialiser (0x16ac74) and the statistics set-up
    (0x1ebca0) first, so no statistic table is embedded here or in the model.
    Everything else is a recording stub answered by a seeded script (class World): every
    virtual call on a creature, player or prop, the damage function, world queries,
    animation, object construction (GameObject_ctor: its stub makes the shared draw the
    real one makes), the pool, particles, lights, sound, text.  A call to an address that
    is neither real nor a known stub is reported as a failure.

Second pass (sections appended after the first pass's, so that those keep their random
cases): charge, darkness, shock, groundpound, convertenemy, convertundead, ancestralcall
(with the prediction copy as a caster), shadowstep, canuse (slot 1 of every id of the
pass for a player, a monster and the copy) and sb3 - the ORIGINAL StaticFire constructor
and run function executed as they are, without a model, to see what they do with their
owner argument.  After the frame counts the test prints, per skill, the stores a cast made
outside its own new objects (the prediction-copy table of the companion document).

Third pass (appended after those): coneoffrost (with the DummyDamager object, also built
directly with every behaviour bit), shockoffire (Sparks), froststorm (the storm and its ice
shards), giantgrowth and planarwind - cast, constructors and every run to the natural end.
New stubs: voice_setPosition, world_damageInRadius; the two matrix functions these skills
call (mat3_rotateAxis, mat3_setRotZ) run for real, as tools/ref_core.py models them, and
so does the C library's double arithmetic the Frost Storm uses for a sign.
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
import ref_skills_b as SB                       # noqa: E402
import difftest_creature as DC                  # noqa: E402
from difftest_creature import Res, f32, fl, rd, M32, is_stack      # noqa: E402

C = RC.C
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = {'quick': False, 'seed': 3568, 'filter': None, 'verbose': False, 'trace_first': False, 'fpu': 'ps2'}
STUB_BASE = 0x00F00000
NODE_COUNT = 1200
ANIM_FLAGS = (0x00, 0x10, 0x10, 0x20, 0x30, 0x08, 0x18, 0x80, 0x90)
STEP = 0x19660D
INC = 0x3C6EF35F


def is_model_stack(v):
    return SB.MODEL_STACK <= v < SB.MODEL_STACK + SB.MODEL_STACK_SIZE


class RealSet:
    def __init__(self, addresses):
        self.addresses = set(addresses)

    def __contains__(self, target):
        return target in self.addresses or DC.LIB_LO <= target < DC.LIB_HI


class EmuView(DC.EmuView):
    def __init__(self, emu):
        DC.EmuView.__init__(self, emu)
        self.pool_cursor = 0


class ModelView(DC.ModelView):
    """The model's copy-on-write view.  A store to memory the interpreter has not mapped
    stops the model as it stops the original (a null pointer the code does not test)."""

    def __init__(self, under):
        DC.ModelView.__init__(self, under)
        self.pool_cursor = 0

    def store(self, addr, size, value):
        if not self.under.is_mapped(addr & M32, size):
            raise ee_emu.MemoryFault(0, addr & M32, size, 'write')
        DC.ModelView.store(self, addr, size, value)


# ---------------------------------------------------------------------------------------
# The scripted world
# ---------------------------------------------------------------------------------------
class World:
    """The fake game in the interpreter's memory, and the answers of every stubbed call.
    A handler gets (canonical arguments, view, rng) and must depend on nothing else that
    changes during a call: it runs once for the model and once for the original."""

    def __init__(self, emu, rng, machine=0, net=0):
        self.emu, self.mem = emu, emu.mem
        self.machine, self.net = machine, net
        self.stub_addr, self.stub_name = {}, {}
        self.res, self.texts = {}, {}
        self.live = set()                   # pool blocks in use between calls
        self.allocated = []                 # blocks the original's last call was given
        self.pool_fail = 0.05
        self.sample_counts = (0, 1, 3, 7, 7, 12)
        self.ground_up = 0.4                # how often the terrain is above the point asked about
        self.box_counts = (0, 0, 1, 2, 3, 5, 8)
        self.forced_events = None           # the next Player_animStep answers: event bits from a real anim_advance
        self.anim_end = 0.25                # how often a stubbed animation step changes the status bits
        self.build(rng)

    # ---- construction ------------------------------------------------------------------
    def stub_for(self, name):
        if name not in self.stub_addr:
            addr = STUB_BASE + 16 * len(self.stub_addr)
            self.stub_addr[name], self.stub_name[addr] = addr, name
        return self.stub_addr[name]

    def stub_table(self, cls, slots=48):
        table = self.emu.alloc(8 * slots)
        for slot in range(1, slots):
            self.mem.w32(table + 8 * slot + 4, self.stub_for('%s.v%d' % (cls, slot)))
        return table

    def build(self, rng):
        emu, mem = self.emu, self.mem
        # the executable's own start-up: every Skill object constructed, every table filled
        emu.call(0x16AC74, 1, 0xFFFF, max_steps=20000000)
        emu.call(0x1EBCA0, max_steps=20000000)
        emu.reset_log()
        mem.map(SB.MODEL_STACK, SB.MODEL_STACK_SIZE)
        nodes = emu.alloc(0x14 * NODE_COUNT)
        for i in range(NODE_COUNT):
            mem.w32(nodes + 0x14 * i, nodes + 0x14 * (i + 1) if i + 1 < NODE_COUNT else 0)
        mem.w32(SB.G_HANDLE_FREE, nodes)
        self.node_lo, self.node_hi = nodes, nodes + 0x14 * NODE_COUNT
        self.vt_obj = self.stub_table('Creature')
        self.vt_spell = self.stub_table('Spell', 8)
        self.model = emu.alloc(0x100)
        self.lump = emu.alloc(0x20)
        mem.write(self.lump, b'class.lmp\0')
        self.class_def = emu.alloc(0x200)
        mem.w32(self.class_def, self.lump)
        mem.w32(self.class_def + 0xC, self.model)
        self.players = [emu.alloc(0x600) for _ in range(4)]
        self.ghost = emu.alloc(0x600)               # the prediction copy of player 0
        self.monsters = [emu.alloc(0x600) for _ in range(3)]
        self.props = [emu.alloc(0x600) for _ in range(2)]
        self.objects = self.players + [self.ghost] + self.monsters + self.props
        self.blocks = [emu.alloc(0x400) for _ in range(40)]
        self.spells = [emu.alloc(0x40) for _ in range(3)]      # foreign spells: every slot a stub
        for sp in self.spells:
            mem.w32(sp + 0x14, self.vt_spell)
        self.scratch = emu.alloc(0x400)             # arguments passed by address: ordinary memory
        self.item = emu.alloc(0x100)
        self.item_def = emu.alloc(0x100)
        mem.w32(RC.G_WORLD, emu.alloc(16))
        mem.w8(RC.G_NETWORK_MODE, 1 if self.net else 0)
        mem.w32(RC.G_NUM_PLAYERS, 4)
        mem.w32(RC.G_EXCLUDE_MASK, 0x20000)
        mem.w32(SB.G_COSMETIC_SEED, 0x1234567 if self.machine else 0x7654321)
        mem.w32(SB.G_SEED3, 0x2468ACE if self.machine else 0x13579BD)
        mem.w32(RC.G_SIM_FRAME, 1000 + rng.randrange(5000))
        mem.w32(RC.G_RAND_SEED, rng.getrandbits(32))
        self.place(rng)

    def place(self, rng, centre=None):
        """(Re)build every world object: players 0-3, the prediction copy of player 0,
        monsters and props, scattered round a centre."""
        mem = self.mem
        cx, cy, cz = centre or (2000.0 + rng.uniform(-300, 300), 3000.0 + rng.uniform(-300, 300), 10.0)
        for obj in self.objects:
            for off in range(0, 0x600, 4):
                mem.w32(obj + off, 0)
            near = rng.random() < 0.6
            spread = 70 if near else rng.choice((200, 500, 1500))
            mem.wf32(obj + 0x10, cx + rng.uniform(-spread, spread))
            mem.wf32(obj + 0x14, cy + rng.uniform(-spread, spread))
            mem.wf32(obj + 0x18, cz + rng.choice((0.0, 0.0, 0.0, -20.0, 30.0, 100.0)))
            mem.wf32(obj + 0x1C, rng.choice((8.0, 16.0, 24.0, 30.0)))
            mem.wf32(obj + 0x20, rng.choice((40.0, 72.0, 72.0, 84.0)))
            mem.w32(obj + 0x24, self.class_def)
            mem.w16(obj + 0x38, rng.randrange(0x10000))
            mem.w32(obj + 0x44, rng.getrandbits(32))
            mem.w32(obj + 0x48, self.vt_obj)
            mem.wf32(obj + 0xDC, rng.choice((1.0, 1.0, 1.3)))
            mem.w16(obj + 0x11A, rng.choice(ANIM_FLAGS))
            mem.wf32(obj + 0x228, rng.choice((300.0, 300.0, 40.0, 0.0)))
            mem.wf32(obj + 0x22C, 300.0)
            mem.w8(obj + 0x310, rng.choice((0xFF, 0xFF, 0, 1)))
            mem.w32(obj + 0x544, self.model)
        for slot, obj in enumerate(self.players + [self.ghost]):
            slot &= 3 if obj != self.ghost else 0
            mem.w32(obj + 0xC, 0x40 | (0x20000 if obj == self.ghost else 0) | rng.choice((0, 0, 0, 0, 8)))
            mem.w32(obj + 0x3C8, slot)
            mem.w8(obj + 0x310, slot & 1)
            mem.w32(obj + 0x58C, 2)
        for obj in self.monsters:
            mem.w32(obj + 0xC, rng.choice((0x20, 0x20, 0x20, 0x20, 0x28, 0x21, 0x1000020)))
            mem.w64(obj + 0xA8, rng.choice((0, 0, 0, 0x4000000, 0x800, 0x10)))
            mem.w32(obj + 0x3C8, rng.choice((0, 0, 0x33)))
        for obj in self.props:
            mem.w32(obj + 0xC, rng.choice((0, 0x200, 0x1, 0x20000000)))
        for slot in range(4):
            rec = RC.G_PLAYERS + slot * RC.REC_SIZE
            mem.w32(rec + RC.REC_OBJ, self.players[slot])
            mem.w8(rec + 0x58, rng.choice((1, 5, 20, 50)))
            mem.wf32(rec + 0xAC, rng.choice((100.0, 100.0, 37.0, 0.0)))
            mem.wf32(rec + 0xB0, 120.0)
            mem.wf32(rec + 0xC0, rng.choice((0.0, 50.0, 119.0)))
            mem.wf32(rec + 0xC4, 120.0)
            mem.w32(rec + 0xCC, rng.choice((40, 200)))
            mem.w32(rec + 0xD0, rng.choice((3, 20, 55)))
            mem.w32(rec + 0xD4, rng.choice((9, 30, 80)))
            mem.w8(rec + 0x4A86, rng.choice((4, 4, 4, 0, 1, 2, 6)))
        for i, sp in enumerate(self.spells):
            mem.w32(sp + 4, 0)
        mem.w32(SB.G_ALIVE_COUNT, 0)

    def casters(self):
        return self.players + self.monsters

    # ---- answers ------------------------------------------------------------------------
    def respond(self, name, args, view, rng):
        handler = getattr(self, 'on_' + name.replace('.', '_'), None)
        if handler is not None:
            return handler(args, view, rng)
        if name in SB.OBJECT_CTORS:                     # the shared draw of the GameObject inside
            view.poke(RC.G_RAND_SEED, 4, (rd(view, RC.G_RAND_SEED) * STEP + INC) & M32)
        return Res()

    def on_pool_new(self, args, view, rng):
        while view.pool_cursor < len(self.blocks) and self.blocks[view.pool_cursor] in self.live:
            view.pool_cursor += 1
        if rng.random() < self.pool_fail or view.pool_cursor >= len(self.blocks):
            return Res(0)
        block = self.blocks[view.pool_cursor]
        view.pool_cursor += 1
        if isinstance(view, EmuView):
            self.allocated.append(block)
        for off in range(0, min((args[0] + 3) & ~3, 0x400), 4):     # the pool zero-fills
            view.poke(block + off, 4, 0)
        return Res(block)

    def on_GameObject_ctor(self, args, view, rng):
        """What GameObject_ctor 0x14cb10 leaves (docs/spec/skills-35-68.md Part 2), the
        shared draw for the object's own generator included; the grid link is left out."""
        obj, pos, class_def, props = args
        seed = (rd(view, RC.G_RAND_SEED) * STEP + INC) & M32
        view.poke(RC.G_RAND_SEED, 4, seed)
        for off in (0, 4, 8, 0xC, 0x34):
            view.poke(obj + off, 4, 0)
        for i in range(3):
            view.poke(obj + 0x10 + 4 * i, 4, pos[i])
        view.poke(obj + 0x1C, 4, f32(24.0))
        view.poke(obj + 0x20, 4, f32(72.0))
        view.poke(obj + 0x24, 4, class_def)
        view.poke(obj + 0x2C, 4, props)
        view.poke(obj + 0x28, 1, 0x19)
        view.poke(obj + 0x29, 1, 0x49)
        view.poke(obj + 0x44, 4, seed >> 16)
        view.poke(obj + 0x48, 4, SB.VT_GAMEOBJECT)
        return Res()

    def on_res_find(self, args, view, rng):
        key = args
        if key not in self.res:
            rec = self.emu.alloc(0x80)
            self.mem.w32(rec + 4, 20 + 7 * (len(self.res) % 9))     # a clip's length in ticks
            self.res[key] = rec
        return Res(self.res[key])

    def on_text_lookup(self, args, view, rng):
        if args[0] not in self.texts:
            self.texts[args[0]] = self.emu.alloc(0x10)
        return Res(self.texts[args[0]])

    def on_libc_sprintf(self, args, view, rng):
        return Res(outs=[b'name%d' % rng.randrange(3)])

    def on_terrain_height(self, args, view, rng):
        if rng.random() < self.ground_up:
            return Res(f=f32(fl(args[1][2]) + rng.choice((0.5, 3.0, 11.0, 60.0))))
        return Res(f=f32(fl(args[1][2]) + rng.choice((0.0, -1.0, -5.0, -40.0, -40.0, -40.0))))

    def on_water_test(self, args, view, rng):
        return Res(1 if rng.random() < 0.5 else 0)

    def on_world_collectObjectsInBox(self, args, view, rng):
        count = rng.choice(self.box_counts)
        return Res(outs=[[rng.choice(self.objects) for _ in range(count)]])

    def _some_objects(self, args, view, rng):
        return Res(outs=[[rng.choice(self.objects) for _ in range(rng.choice((0, 1, 1, 2, 3, 5)))]])

    on_world_collectInSphere = on_world_collectObjectsInArc = _some_objects

    def on_model_getAttachPoint(self, args, view, rng):
        pos = args[1]
        return Res(outs=[(f32(fl(pos[0]) + rng.uniform(-9, 9)), f32(fl(pos[1]) + rng.uniform(-9, 9)),
                          f32(fl(pos[2]) + rng.uniform(20, 60))), (f32(rng.uniform(-1, 1)), f32(rng.uniform(-1, 1)), 0)])

    def on_model_getSamplePointCount(self, args, view, rng):
        return Res(rng.choice(self.sample_counts))

    def on_creature_bossRank(self, args, view, rng):
        return Res(rng.choice((0, 0, 1, 1, 2, 3, 0xFFFFFFFF)))

    def on_model_getSamplePoint(self, args, view, rng):
        pos = args[2]
        point = tuple(f32(fl(pos[i]) + rng.uniform(-30, 30)) for i in range(3))
        return Res(outs=[point, (f32(rng.uniform(-1, 1)), 0, f32(1.0))])

    def on_damage_apply(self, args, view, rng):
        return Res(rng.choice((0, 1, 1, 1)))

    def on_net_objOrGhost(self, args, view, rng):
        return Res(self.ghost if args[0] == self.players[0] and self.machine else args[0])

    def on_net_isLocalSlot(self, args, view, rng):
        return Res(1 if args[0] == (1 if self.machine else 0) else 0)

    def on_net_getCamYaw(self, args, view, rng):
        return Res(rng.randrange(0x10000))

    def on_Player_animStep(self, args, view, rng):
        if self.forced_events is not None:
            return Res(self.forced_events)
        if rng.random() < self.anim_end:
            view.poke(args[0] + 0x11A, 2, rng.choice(ANIM_FLAGS))
        return Res(rng.choice((0, 0, 0, 1, 1, 2, 4, 5, 7, 0x80)))

    def on_Player_move(self, args, view, rng):
        player = args[0]
        for i in range(2):
            view.poke(player + 0x10 + 4 * i, 4, f32(fl(rd(view, player + 0x10 + 4 * i)) + rng.choice((0.0, 1.5, -2.25))))
        return Res(rng.choice((0, 0, 1, 2)))

    def on_Creature_v16(self, args, view, rng):
        return Res(self.model)

    def on_Creature_v20(self, args, view, rng):
        other = args[1]
        if other == args[0] or rd(view, other + 0xC) & 8:
            return Res(0)
        return Res(rng.choice((0, 1, 1, 1, 4)))

    def on_Creature_v35(self, args, view, rng):
        return Res(rng.choice((1, 3, 9)))

    def on_Creature_v36(self, args, view, rng):
        return Res(rng.choice((0, 1, 12)))

    def on_Creature_v37(self, args, view, rng):
        return Res(rd(view, args[0] + 0x310, 1, True) & M32)

    def on_Creature_v39(self, args, view, rng):
        return Res(rng.choice((0, 1, 5, 12, 20)))

    def on_SpellResurrect_typeinfo(self, args, view, rng):
        return Res(0x909760)

    def on_SpellCriticalHit_typeinfo(self, args, view, rng):
        return Res(0x909000)

    def on_creature_findSpellByType(self, args, view, rng):
        return Res(rng.choice((0, 0, 0, self.spells[0], self.spells[1])))

    def on_player_respawn(self, args, view, rng):
        """The slot gets a new Player object (here: another block made up as one)."""
        slot = args[0]
        fresh = self.props[1]
        view.poke(fresh + 0xC, 4, 0x40)
        view.poke(fresh + 0x3C8, 4, slot)
        view.poke(RC.G_PLAYERS + (slot & 3) * RC.REC_SIZE + RC.REC_OBJ, 4, fresh)
        return Res()

    def on_particleGroup_create(self, args, view, rng):
        return Res(rng.choice((0, 1, 5, 16)))

    def on_terrain_heightAtPoint(self, args, view, rng):
        return Res(f=f32(fl(args[1][2]) + rng.choice((0.0, 10.0, -30.0, 71.0, 72.0, 73.0, -72.0, -72.5, 300.0))))

    def on_Creature_v21(self, args, view, rng):
        return Res(rng.choice((0, 1, 1)))

    on_Creature_v22 = on_Creature_v21

    def on_item_getModifiedField1a(self, args, view, rng):
        return Res(rng.choice((0, 15, 240, 0xFFFFFFF0)))

    def on_player_getSkillRank(self, args, view, rng):
        return Res(rng.choice((0, 0, 1, 7, 20)))

    # ---- answers used by the second pass only ------------------------------------------------
    def on_trail_create(self, args, view, rng):
        return Res(rng.choice((0, 3, 17, 40)))

    def on_beam_create(self, args, view, rng):
        return Res(rng.choice((0, 2, 9)))

    def on_Player_clampToScreen(self, args, view, rng):
        if rng.random() < 0.3:
            return Res(outs=[(0, 0, 0)])
        return Res(outs=[(f32(rng.uniform(-370, 370)), f32(rng.uniform(-370, 370)), 0)])

    def on_obj_moveWithCollision(self, args, view, rng):
        obj, velocity = args[0], args[1]
        for i in range(3):
            view.poke(obj + 0x10 + 4 * i, 4, f32(fl(rd(view, obj + 0x10 + 4 * i)) + fl(velocity[i]) / 64.0))
        return Res(rng.choice((0, 0, 2, 4, 6, 0x10)))

    def on_isNearView(self, args, view, rng):
        return Res(1)

    def on_SpellAncestralCall_typeinfo(self, args, view, rng):
        return Res(0x909E90)


# ---------------------------------------------------------------------------------------
# The rig
# ---------------------------------------------------------------------------------------
class Rig:
    def __init__(self, elf, seed, machine=0, net=0):
        self.rng = random.Random(seed)
        emu = self.emu = EE(elf, fpu_model=OPTIONS['fpu'])
        self.world = World(emu, self.rng, machine, net)
        modelled = set(SB.MODELLED.values())
        self.real = emu.follow = RealSet(modelled | set(DC.REAL_OTHER) | set(SB.REAL_LIBRARY.values()))
        self.calls, self.buffers, self.unknown = [], {}, {}
        self.eview = EmuView(emu)
        self.script_rng = None
        self.names, self.addr_names = {}, {}
        for name, ext in SB.EXTERNALS.items():
            if ext.addr and ext.addr not in modelled:
                self.add_stub(ext.addr, name)
        for addr, name in list(self.world.stub_name.items()):
            self.add_stub(addr, name)
        # the class tables of the model: a slot whose function is not real is a named stub
        for table, cls, slots in SB.CLASS_TABLES:
            for slot in slots:
                fn = emu.mem.u32(table + 8 * slot + 4)
                if fn not in self.real and fn not in self.names:
                    self.add_stub(fn, '%s.v%d' % (cls, slot))
                    self.addr_names[fn] = '%s.v%d' % (cls, slot)
        self.partial, self.partial_ops = [], {}
        for start, end in SB.FUNCTIONS.values():
            for pc in range(start, end, 4):
                w = emu.mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))
        self.cov = set()
        self.serial = 0
        self.stats = {}                     # entry name -> [calls, calls with a mismatch, shared draws]
        self.bad = {}                       # section -> property -> [text]
        self.section = 'base'

    def add_stub(self, addr, name):
        assert self.names.setdefault(addr, name) == name, (hex(addr), name, self.names[addr])
        ext = SB.EXTERNALS.get(name) or RC.Ext(0, 'p', 0, 'n')
        self.emu.stub(addr, function=self.make_stub(name, ext), name=name)

    def partial_hook(self, pc, base, offset):
        def note(emu):
            ea = (emu.r[base] + offset) & M32
            if not is_stack(ea):
                self.partial.append((pc, ea))
        return note

    def stored_bytes(self):
        """The set of bytes the original stored outside the stack, exact for the
        partial-word stores (which tools/ee_emu.py logs as whole aligned words)."""
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
            out.update(range(first, last + 1))
        return out

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
            elif kind == 'V':
                canon.append(tuple(mem.u32(v + 4 * j) for j in range(3)) if v else 0)
            elif kind == 'D':
                canon.append(decode_descriptor(mem, v))
            elif kind == 'M':
                canon.append(tuple(mem.u32(v + 4 * j) for j in range(12)))
            elif kind == 's':
                canon.append(('buf', self.buffers.get(v, b'?')))
            elif kind == 'S':
                canon.append(('buf', self.buffers[v]) if v in self.buffers else v)
            elif kind == 'l':
                items = []
                while mem.u32(v + 4 * len(items)):
                    items.append(mem.u32(v + 4 * len(items)))
                canon.append(tuple(items))
            elif kind in 'OWQ':
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
                value = given.pop(0) if given else ((0, 0, 0) if kind in 'oO' else ([] if kind in 'nL' else 0))
                if kind == 'L':
                    SB.list_fill(mem.load, self.eview.poke, ptr, value)
                elif kind in 'oO':
                    if ptr:
                        for j in range(3):
                            mem.w32(ptr + 4 * j, value[j])
                elif kind in 'wW':
                    if ptr:
                        mem.w32(ptr, value)
                elif kind == 'b':
                    mem.w8(ptr, value)
                elif kind == 'Q':                       # an optional 3x3 matrix
                    if ptr:
                        for j in range(9):
                            mem.w32(ptr + 4 * j, (value or (0,) * 9)[j])
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
                ext = SB.EXTERNALS.get(name)
                if ext is None:
                    return None
                ret = res.ret & (RC.M64 if ext.ret == 'q' else M32)
                return SB.shape_result(name, args, ret, res.f & M32, res.outs)
            return answer

    # ---- one call, both sides ---------------------------------------------------------------
    def compare(self, name, method, args, fargs=(), ret='n'):
        """Run the original function `name` (ref_skills_b.FUNCTIONS) and the model method
        on the same state.  args: integers for a0..; fargs: float patterns for f12..; the
        model gets (args..., fargs...).  Returns a dict of differences."""
        addr = SB.FUNCTIONS[name][0]
        emu, world = self.emu, self.world
        mem = emu.mem
        self.serial += 1
        call_seed = OPTIONS['seed'] * 1000003 + self.serial
        seed_before = mem.u32(RC.G_RAND_SEED)
        mview = ModelView(mem)
        model = SB.Model(mview, Rig.Callbacks(self, mview, random.Random(call_seed)))
        model.addr_names = self.addr_names
        model_error = None
        try:
            mret = getattr(model, method)(*(tuple(args) + tuple(fargs)))
        except EmuError as exc:
            model_error, mret = exc, None
        self.calls, self.buffers = [], {}
        self.eview.touched = set()
        self.eview.pool_cursor = 0
        world.allocated = []
        self.script_rng = random.Random(call_seed)
        emu.reset_log()
        self.partial = []
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x100
        for j, value in enumerate(fargs):
            emu.f[12 + j] = value & M32
        emu_error = None
        try:
            eret = emu.call(addr, *[ee_emu.s32(a & M32) for a in args], max_steps=6000000)
        except EmuError as exc:
            emu_error, eret = exc, None
        self.cov.update(emu.trace)
        emu.trace = None
        for c in emu.calls:
            if c.target not in self.real and c.target not in self.names:
                self.unknown[c.target] = self.unknown.get(c.target, 0) + 1
        out = {'fault': None, 'calls': None, 'writes': None, 'seed': None, 'result': None, 'both_fault': None,
               'draws': model.draws, 'model_calls': model.calls, 'emu_calls': self.calls, 'ret': eret, 'mret': mret}
        if model_error or emu_error:
            if model_error is None or emu_error is None:
                out['fault'] = 'model %r / original %r' % (model_error, emu_error)
            else:
                out['both_fault'] = getattr(emu_error, 'pc', 0)
            return out
        if model.calls != self.calls:
            out['calls'] = DC.describe_calls(model.calls, self.calls)
        ebytes = self.stored_bytes()
        mbytes = set()
        for a, size, _value in model.writes:
            if not is_model_stack(a):
                mbytes.update(range(a, a + size))
        diff = []
        for a in sorted(ebytes | mbytes | self.eview.touched | mview.touched):
            if is_model_stack(a) or is_stack(a):
                continue
            x, y = mem.load(a, 1), mview.load(a, 1)
            if x != y:
                w = a & ~3              # a word holding a frame address on both sides is equal
                if is_stack(mem.load(w, 4)) and is_model_stack(mview.load(w, 4)):
                    continue
                diff.append((a, x, y))
        if ebytes != mbytes or diff:
            text = ''
            if ebytes - mbytes:
                text += ' only original stores %s;' % sorted({self.where(a) for a in ebytes - mbytes})[:8]
            if mbytes - ebytes:
                text += ' only model stores %s;' % sorted({self.where(a) for a in mbytes - ebytes})[:8]
            if diff:
                text += ' values differ at %s' % [(self.where(a), '%02x' % x, '%02x' % y) for a, x, y in diff[:8]]
            out['writes'] = text
        s = seed_before
        for _ in range(model.draws):
            s = (s * STEP + INC) & M32
        if not mem.u32(RC.G_RAND_SEED) == mview.load(RC.G_RAND_SEED, 4) == s:
            out['seed'] = 'model draws %d' % model.draws
        if ret == 'i' and (eret & M32) != ((mret or 0) & M32):
            out['result'] = 'original %08x model %08x' % (eret & M32, (mret or 0) & M32)
        elif ret == 'f' and emu.f[0] & M32 != (mret or 0) & M32:
            out['result'] = 'original %08x model %08x' % (emu.f[0] & M32, (mret or 0) & M32)
        return out

    def where(self, addr):
        world = self.world
        for label, group, size in (('player', world.players, 0x600), ('monster', world.monsters, 0x600),
                                   ('prop', world.props, 0x600), ('block', world.blocks, 0x400)):
            for i, obj in enumerate(group):
                if obj <= addr < obj + size:
                    return '%s%d+%x' % (label, i, (addr - obj) & ~3)
        if world.ghost <= addr < world.ghost + 0x600:
            return 'ghost+%x' % ((addr - world.ghost) & ~3)
        if world.node_lo <= addr < world.node_hi:
            return 'node%d+%x' % ((addr - world.node_lo) // 0x14, (addr - world.node_lo) % 0x14 & ~3)
        if RC.G_PLAYERS <= addr < RC.G_PLAYERS + 4 * RC.REC_SIZE:
            return 'record%d+%x' % ((addr - RC.G_PLAYERS) // RC.REC_SIZE, (addr - RC.G_PLAYERS) % RC.REC_SIZE & ~3)
        if world.scratch <= addr < world.scratch + 0x400:
            return 'scratch+%x' % ((addr - world.scratch) & ~3)
        for key, rec in world.res.items():
            if rec <= addr < rec + 0x80:
                return 'res%s+%x' % (key[1:], (addr - rec) & ~3)
        return '%x' % (addr & ~3)

    def do(self, name, method, args, fargs=(), ret='n', note=''):
        """compare() plus the bookkeeping: counts per entry, mismatches per section."""
        result = self.compare(name, method, args, fargs, ret)
        row = self.stats.setdefault(name, [0, 0, 0])
        row[0] += 1
        row[2] += result['draws']
        bad = self.bad.setdefault(self.section, {'calls': [], 'writes': [], 'seed': [], 'result': [], 'fault': [],
                                                 'count': 0, 'both': 0})
        bad['count'] += 1
        failed = False
        for prop in ('fault', 'calls', 'writes', 'seed', 'result'):
            if result[prop]:
                failed = True
                bad[prop].append('%s%s(%s): %s' % (note and note + ' ', name, ', '.join(
                    '%x' % (a & M32) for a in tuple(args) + tuple(fargs)), result[prop]))
        if result['both_fault'] is not None:
            bad['both'] += 1
        if failed:
            row[1] += 1
            if OPTIONS['trace_first']:
                print('first mismatch: section %s, %s %s' % (self.section, name, note))
                for prop in ('fault', 'calls', 'writes', 'seed', 'result'):
                    if result[prop]:
                        print('  %s: %s' % (prop, result[prop]))
                print('  model calls:')
                for call in result['model_calls'][:400]:
                    print('    ' + DC.fmt_call(call))
                print('  original calls:')
                for call in result['emu_calls'][:400]:
                    print('    ' + DC.fmt_call(call))
                sys.exit(1)
        return result

    def vskill(self, skill, slot, args=(), fargs=(), ret='i', note=''):
        """A virtual call on a Skill object: the function the table holds, and the model
        method registered for it."""
        fn = self.emu.mem.u32(self.emu.mem.u32(skill + 0x60) + 8 * slot + 4)
        name = FUNCTION_AT[fn]
        return self.do(name, SB.SKILL_BODIES[fn], (skill,) + tuple(args), fargs, ret, note)

    def report(self, section, text):
        bad = self.bad.get(section)
        if bad is None:
            return
        for prop, what in (('calls', 'call-outs in order with arguments'), ('writes', 'bytes stored and their final values'),
                           ('seed', 'shared seed and number of draws'), ('result', 'returned values'),
                           ('fault', 'calls that stopped on one side only (%d stopped on both, the same way)' % bad['both'])):
            DC.report('%s %s' % (section, prop), len(bad[prop]), bad['count'], what + ('; ' + text if prop == 'calls' else ''),
                      bad[prop])


FUNCTION_AT = {start: name for name, (start, _end) in SB.FUNCTIONS.items()}


def decode_descriptor(mem, v):
    """The damage descriptor a caller builds in its frame (docs/gameplay.md 2.2), as the
    model names it: ('desc', ((type, a, b, c), ...)) for the entries in use, or the
    raw bytes when the fixed part is not what every call site of this range writes."""
    if v == 0:
        return 0
    ok = all(mem.u16(v + 0x10 + 2 * k) == 0 for k in range(8)) and mem.u8(v + 0x20) == 0xFF and mem.u8(v + 0x21) == 0xFF
    if not ok:
        return ('desc?', bytes(mem.read(v + 0x10, 0x34)).hex())
    entries = []
    for k in range(4):
        kind = mem.u16(v + 0x24 + 8 * k)
        if kind != 0xFFFF:
            entries.append((kind, mem.u16(v + 0x26 + 8 * k), mem.u16(v + 0x28 + 8 * k), mem.u16(v + 0x2A + 8 * k)))
    return ('desc', tuple(entries))


# ---------------------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------------------
def skill_obj(mem, sid):
    return mem.u32(SB.G_SKILL_TABLE + 4 * sid)


def section_stats(rig):
    """Statistics getters of all 34 ids: slots 10, 11, 12, 13 for every statistic at every
    level 0-40 (and two levels outside), slots 5, 14, 15 per level, slot 8 with and
    without the random spread."""
    rig.section = 'stats'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    levels = list(range(0, 41)) + [41, 60, 0xFFFFFFFF]
    if OPTIONS['quick']:
        levels = levels[::4] + [40]
    handle = world.scratch + 0x100
    player, monster = world.players[1], world.monsters[0]
    mem.w32(player + 0xC, 0x40)
    mem.w32(monster + 0xC, 0x20)
    node_p, node_m = world.scratch + 0x120, world.scratch + 0x140
    mem.w32(node_p + 0xC, player)
    mem.w32(node_m + 0xC, monster)
    out = world.scratch + 0x160
    for sid in SB.SKILL_IDS:
        skill = skill_obj(mem, sid)
        note = 'id %d' % sid
        for level in levels:
            for stat in range(5):
                rig.vskill(skill, 10, (stat, level), note=note)
                for cap in (0, 10, 20, 0xFFFFFFFF):
                    rig.vskill(skill, 11, (stat, level, cap), note=note)
                for caster, cap in ((0, 0), (player, 10), (monster, 0), (monster, 10)):
                    rig.vskill(skill, 12, (stat, level, caster, cap), note=note)
                for node, cap in ((0, 10), (node_p, 0), (node_m, 10)):
                    mem.w32(handle, node)
                    rig.vskill(skill, 13, (stat, level, handle, cap), note=note)
                mem.w32(RC.G_RAND_SEED, rng.getrandbits(32))
                for randomise in (0, 1):
                    spread = f32(rng.choice((0.2, 0.2, 0.1, 0.5, 1.0, 1.5)))
                    mem.w32(out, 0)
                    mem.w32(out + 4, 0)
                    rig.vskill(skill, 8, (stat, level, randomise, out, out + 4), (spread,), ret='n', note=note)
            rig.vskill(skill, 14, (level, 20), note=note)
            rig.vskill(skill, 15, (level, 20), ret='f', note=note)
            rig.vskill(skill, 5, (level,), ret='f', note=note)
    rig.report('stats', 'ids 35-68, statistics 0-4, levels 0-40, 41, 60 and -1; slots 5, 8, 10-15')


def section_base(rig):
    """The shared machinery: handle lists and the iterator, attaching and running spells,
    the generators, Projectile_ctor, obj_moveAndCollide, and the Skill base on a
    synthetic Skill object whose tables hold every sign and both tiers."""
    rig.section = 'base'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    n = 60 if OPTIONS['quick'] else 600
    heads = [world.scratch + 0x200 + 4 * i for i in range(6)]
    it = world.scratch + 0x240
    pos = world.scratch + 0x260
    for round_ in range(n):
        r = rng.random
        world.place(rng)
        for h in heads:
            mem.w32(h, 0)
        objs = world.objects
        # --- lists: build, walk, take apart
        for _ in range(rng.randrange(1, 12)):
            op = rng.choice(('link', 'link', 'link', 'push', 'clear', 'remove'))
            head = rng.choice(heads)
            if op == 'link':
                obj = rng.choice(objs)
                rig.do('handle_link', 'handle_link', (head, obj, obj), ret='i')
            elif op == 'push':
                rig.do('list_push', 'list_push', (head, rng.choice(objs + [0])), ret='i')
            elif op == 'clear':
                rig.do('handle_clear', 'handle_clear', (head,))
            elif mem.u32(head):
                node = mem.u32(head)
                for _k in range(rng.randrange(3)):
                    node = mem.u32(node) or node
                rig.do('handle_removeNode', 'handle_removeNode', (node,), ret='i')
            if r() < 0.3:                               # an object dies: every handle to it goes empty
                rig.do('handle_clear', 'handle_clear', (rng.choice(objs),))
        head = rng.choice(heads)
        mask = rng.choice((0, 0, 8, 0x20000, 0x40))
        rig.do('iter_begin', 'iter_begin', (it, head, mask))
        for _ in range(rng.randrange(0, 6)):
            if not mem.u32(it + 4):
                break
            if r() < 0.3:                               # linked during the walk: in front of the iterator
                rig.do('handle_link', 'handle_link', (head, objs[0], objs[0]), ret='i')
            if r() < 0.2:                               # the node being visited is removed
                rig.do('handle_removeNode', 'handle_removeNode', (mem.u32(it + 4),), ret='i')
                if not mem.u32(it + 4):
                    break
            rig.do('iter_next', 'iter_next', (it,))
        rig.do('iter_end', 'iter_end', (it, 2))
        for h in heads:
            rig.do('handle_clear', 'handle_clear', (h,))
        for obj in objs:
            rig.do('handle_clear', 'handle_clear', (obj,))
        # --- spells: attach (newest first) and run through the owner
        owner = rng.choice(world.casters())
        for sp in rng.sample(world.spells, rng.randrange(0, 4)):
            rig.do('creature_addSpell', 'creature_add_spell', (owner, rng.choice((sp, sp, sp, 0))))
        for i in range(3):
            mem.wf32(pos + 4 * i, rng.uniform(-500, 500))
        rig.do('Creature_updateSpells', 'creature_update_spells', (owner, pos))
        rig.do('handle_clear', 'handle_clear', (owner + 0x364,))
        rig.do('Spell_rand', 'spell_rand', (world.spells[0],), ret='i')
        rig.do('GameObject_rand', 'obj_rand', (objs[0],), ret='i')
        # --- the projectile base
        block = world.blocks[-1]
        for off in range(0, 0x100, 4):
            mem.w32(block + off, 0)
        owner = rng.choice(objs + [0])
        rig.do('Projectile_ctor', 'projectile_ctor', (block, pos, owner, world.class_def))
        for step in range(rng.randrange(1, 5)):
            for i in range(3):
                mem.wf32(pos + 0x10 + 4 * i, rng.choice((0.0, 350.0, -1000.0, 40.0, -300.0)))
            if r() < 0.3:
                mem.wf32(block + 0x20, rng.choice((72.0, 12.0)))
            if r() < 0.5:                               # something to hit: on top of the projectile
                other = rng.choice(objs)
                for i in range(3):
                    mem.wf32(other + 0x10 + 4 * i, mem.f32(block + 0x10 + 4 * i) + rng.choice((0.0, 5.0, -11.0, 35.9, 80.0)))
            rig.do('obj_moveAndCollide', 'obj_move_and_collide', (block, pos + 0x10), ret='i')
        rig.do('handle_clear', 'handle_clear', (block + 0x4C,))
        # --- the Skill base on a synthetic object
        skill = world.scratch + 0x300
        mem.w32(skill + 0x60, SB.VT_SKILL)
        for i in range(5):
            mem.w16(skill + 0x0E + 2 * i, rng.choice((0, 1, 1, 5, 10, 0xFFFF)))
            mem.w16(skill + 0x18 + 2 * i, rng.choice((0, 1, 30, 120, 0xFFD8, 0xFF00)))
            mem.wf32(skill + 0x24 + 4 * i, rng.choice((0.0, 2.0, 0.1, 0.35, -0.5, -7.25, 9.99976, 3.5)))
            mem.w16(skill + 0x38 + 2 * i, rng.choice((0xFFFF, 0xFFFF, 0, 1, 3, 8)))
            mem.w16(skill + 0x42 + 2 * i, rng.choice((0, 5, 44, 0xFFF0)))
            mem.wf32(skill + 0x4C + 4 * i, rng.choice((0.0, 1.5, 0.1, 0.35, -2.5, -0.1)))
        caster = rng.choice(world.casters() + [0])
        handle = world.scratch + 0x380
        mem.w32(handle, 0)
        if caster:
            rig.do('handle_link', 'handle_link', (handle, caster, caster), ret='i')
        out = world.scratch + 0x390
        for _ in range(6):
            stat, level = rng.randrange(5), rng.choice((0, 1, 2, 5, 9, 10, 11, 20, 40, 0xFFFFFFFF))
            cap = rng.choice((0, 3, 10, 20, 0xFFFFFFFF))
            rig.vskill(skill, 10, (stat, level))
            rig.vskill(skill, 11, (stat, level, cap))
            rig.vskill(skill, 12, (stat, level, caster, cap))
            rig.vskill(skill, 13, (stat, level, handle, cap))
            rig.vskill(skill, 8, (stat, level, rng.choice((0, 1)), out, out + 4), (f32(rng.choice((0.2, 0.5, 2.0, 3.0))),), ret='n')
            rig.vskill(skill, 15, (level, 7), ret='f')
        rig.vskill(skill, 1, (caster,))
        rig.vskill(skill, 2, (3, caster, pos, 0x1234))
        rig.vskill(skill, 5, (3,), ret='f')
        rig.do('handle_clear', 'handle_clear', (handle,))
    rig.report('base', 'lists, iterator, spell walk, generators, Projectile_ctor, obj_moveAndCollide, Skill base')


def ended(result, spell):
    """Did the spell end itself in this call (its slot 1 with 3)?"""
    return ('Spell.v1', (spell, 3)) in result['emu_calls']


def put_vec(mem, addr, values):
    for i, v in enumerate(values):
        mem.wf32(addr + 4 * i, v)


def section_cyclone(rig):
    """Skill 41 (and 84): can-use, cast, the spell's constructor for a player, the
    prediction copy and a monster, and its run from the cast to its end - by the
    animation's status bits, by the owner's action state, or through the stop clip."""
    rig.section = 'cyclone'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    for round_ in range(12 if OPTIONS['quick'] else 120):
        r = rng.random
        world.place(rng)
        skill = skill_obj(mem, rng.choice((41, 41, 84)))
        caster = rng.choice(world.players * 2 + [world.ghost, world.monsters[0]])
        mem.w32(SB.G_LEVEL_FLAGS, rng.choice((0, 0, 0x100)))
        mem.w8(RC.G_NETWORK_MODE, rng.choice((0, 1)))
        frame = rng.choice((rng.randrange(1, 100000), 0xFFFFFF00, 0x7FFFFFF0))
        mem.w32(RC.G_SIM_FRAME, frame)
        rig.vskill(skill, 1, (caster,))
        put_vec(mem, pos, [mem.f32(caster + 0x10 + 4 * i) + (5.0, -3.0, 40.0)[i] for i in range(3)])
        level = rng.choice((1, 3, 8, 9, 12, 20, 40))
        spell = rig.vskill(skill, 2, (level, caster, pos, rng.randrange(0x10000)))['ret'] & M32
        if not spell:
            continue
        world.live.add(spell)
        world.anim_end = rng.choice((0.0, 0.0, 0.02, 0.3))
        mem.w16(caster + 0x11A, 0x10)
        mem.w8(caster + 0x118, rng.choice((1, 2, 3)))
        for tick in range(rng.choice((3, 30, 120))):
            frame = (frame + 1) & M32
            mem.w32(RC.G_SIM_FRAME, frame)
            pad = (SB.G_PADS + mem.s32(caster + 0x3C8) * 0x58) & M32
            if r() < 0.3:
                mem.wf32(pad + 0x14, rng.choice((0.0, 1.0, -1.0, 0.37)))
                mem.wf32(pad + 0x18, rng.choice((0.0, 1.0, -0.6)))
            if r() < 0.4:                               # a candidate steps into the blade
                node = mem.u32(spell + 0x18)
                for _ in range(rng.randrange(3)):
                    node = mem.u32(node) if node and mem.u32(node) else node
                if node and mem.u32(node + 0xC):
                    put_vec(mem, mem.u32(node + 0xC) + 0x10, [mem.f32(pos + 4 * i) + rng.choice((0.0, 20.0, -28.0, 45.0)) for i in range(3)])
            if r() < 0.05:
                mem.wf32(spell + 0x68, rng.choice((0.0, 0.07, 0.072, 0.1)))
            if r() < 0.03:
                mem.w32(caster + 0x58C, rng.choice((2, 4, 3)))      # staggered, dead
            if r() < 0.05:
                rig.do('handle_clear', 'handle_clear', (rng.choice(world.objects),))   # a candidate is destroyed
            if r() < 0.1:
                rig.do('SpellCyclone_updateFx', 'cyclone_update_fx', (spell, pos))
            if ended(rig.do('SpellCyclone_run', 'cyclone_run', (spell, pos, rng.randrange(0x10000))), spell):
                break
        rig.do('handle_clear', 'handle_clear', (spell + 0x18,))
        for obj in world.objects:
            rig.do('handle_clear', 'handle_clear', (obj,))
        world.live.discard(spell)
    world.anim_end = 0.25
    mem.w32(SB.G_LEVEL_FLAGS, 0)
    rig.report('cyclone', 'ids 41 and 84; player, prediction copy and monster casters; offline and net game')


TIMERS = {}             # what -> number of calls until the thing ended itself (interpreter's float model)


def arrow_section(sid, prefix, cname, level_off, age_off, skill_off, ctor2=True, hit_name='onHit', end_name='end',
                  end_method='end', text=''):
    """A section for one skill arrow: can-use, cast, both constructors, the run from the
    launch to the end (terrain, a hit, the owner destroyed in flight, natural expiry), and
    the hit and end handlers called on their own."""
    def section(rig):
        rig.section = prefix
        mem, world, rng = rig.emu.mem, rig.world, rig.rng
        pos, aim = world.scratch, world.scratch + 0x10
        skill = skill_obj(mem, sid)
        for round_ in range(10 if OPTIONS['quick'] else 100):
            r = rng.random
            world.place(rng)
            caster = rng.choice(world.players * 2 + world.monsters)
            if caster in world.players:
                mem.w32(caster + 0xC, 0x40)
                mem.w8(RC.G_PLAYERS + mem.u32(caster + 0x3C8) * RC.REC_SIZE + 0x4A86, rng.choice((4, 4, 4, 0, 6)))
            else:
                mem.w32(caster + 0xC, 0x20)
            mem.w32(SB.G_LEVEL_FLAGS, rng.choice((0, 0, 0x40000, 0x100)))
            rig.vskill(skill, 1, (caster,))
            put_vec(mem, pos, [mem.f32(caster + 0x10 + 4 * i) + (5.0, -3.0, 40.0)[i] for i in range(3)])
            level = rng.choice((1, 3, 5, 6, 10, 11, 12, 15, 16, 20, 40))
            rig.vskill(skill, 2, (level, caster, pos, rng.randrange(0x10000)))
            obj = world.allocated[0] if world.allocated else 0
            if ctor2 and (not obj or r() < 0.3):        # the way a monster builds one
                obj = world.blocks[-2]
                for off in range(0, 0x100, 4):
                    mem.w32(obj + off, 0)
                put_vec(mem, aim, [rng.uniform(-400, 400), rng.uniform(-400, 400), rng.choice((0.0, 0.0, 35.0, -80.0))])
                rig.do(cname + '_ctor2', prefix + '_ctor2', (obj, pos, aim, caster, level, skill))
            if not obj:
                continue
            world.live.add(obj)
            long_flight = round_ % 50 == 3
            world.ground_up = 0.0 if long_flight else 0.03
            world.box_counts = (0,) if long_flight else (0, 0, 0, 1, 2, 4)
            runs = 0
            for tick in range(700 if long_flight else rng.choice((2, 10, 40))):
                if not long_flight:
                    if r() < 0.5:                       # something in the way
                        other = rng.choice(world.objects)
                        put_vec(mem, other + 0x10, [mem.f32(obj + 0x10 + 4 * i) + mem.f32(obj + 0x54 + 4 * i) / 60.0
                                                    + rng.choice((0.0, 3.0, -9.0, 30.0)) for i in range(3)])
                    if r() < 0.03:                      # the owner is destroyed in flight
                        rig.do('handle_clear', 'handle_clear', (caster,))
                    if r() < 0.05:
                        world.ground_up = 1.0
                rig.do(cname + '_run', prefix + '_run', (obj,))
                runs += 1
                if mem.u32(obj + 0x60):
                    break
            if long_flight and mem.u32(obj + 0x60):
                TIMERS.setdefault('%s: runs of an unobstructed arrow until it ends itself' % prefix, set()).add(runs)
            world.ground_up, world.box_counts = 0.4, (0, 0, 1, 2, 3, 5, 8)
            for _ in range(3):                          # the handlers on their own, also on an arrow that has ended
                if r() < 0.5:
                    mem.w32(obj + 0x60, 0)
                if r() < 0.2:
                    mem.w32(obj + level_off, rng.choice((1, 5, 6, 10, 11, 15, 16, 30)))
                other = rng.choice(world.objects)
                if r() < 0.5:
                    mem.w32(other + 0xC, mem.u32(other + 0xC) | 0x20)
                rig.do(cname + '_' + hit_name, prefix + '_on_hit', (obj, other))
                if r() < 0.5:
                    mem.w32(obj + 0x60, 0)
                rig.do(cname + '_' + end_name, prefix + '_' + end_method, (obj, rng.choice((0, 1, 2))))
            rig.do('handle_clear', 'handle_clear', (obj + 0x4C,))
            for o in world.objects:
                rig.do('handle_clear', 'handle_clear', (o,))
            world.live.discard(obj)
        mem.w32(SB.G_LEVEL_FLAGS, 0)
        rig.report(prefix, 'id %d; player and monster owners, levels 1-40%s' % (sid, text))
    return section


def section_multifire(rig):
    """Skill 46: can-use and the cast - the light, the fan of MissileWeapon constructions
    with every argument, the shared draw per arrow, a player's and a monster's damage."""
    rig.section = 'multifire'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    skill = skill_obj(mem, 46)
    for round_ in range(30 if OPTIONS['quick'] else 400):
        world.place(rng)
        caster = rng.choice(world.players * 2 + world.monsters)
        if caster in world.players:
            rec = RC.G_PLAYERS + mem.u32(caster + 0x3C8) * RC.REC_SIZE
            mem.w8(rec + 0x4A86, rng.choice((4, 4, 4, 0, 6)))
            mem.w8(rec + 0x4A7C, rng.choice((0, 1)))
            for k in range(2):
                mem.w32(rec + 0x4434 + 4 * k, world.item + 0x40 * k)
                mem.w64(world.item + 0x40 * k + 8, rng.getrandbits(64))
            mem.w32(rec + 0xD0, rng.choice((0, 1, 3, 20, 55, 400, 0xFFFFFFF0)))
            mem.w32(rec + 0xD4, rng.choice((1, 9, 30, 80, 999)))
        world.pool_fail = rng.choice((0.0, 0.05, 0.3))
        rig.vskill(skill, 1, (caster,))
        put_vec(mem, pos, [mem.f32(caster + 0x10 + 4 * i) + (5.0, -3.0, 40.0)[i] for i in range(3)])
        level = rng.choice((1, 2, 3, 5, 6, 10, 11, 16, 20, 26, 36, 40))
        rig.vskill(skill, 2, (level, caster, pos, rng.choice((rng.randrange(0x10000), 0xFFFF8000 | rng.randrange(0x8000)))))
    world.pool_fail = 0.05
    rig.report('multifire', 'id 46; player and monster casters; the MissileWeapon objects themselves are call-outs')


def section_passives(rig):
    """Ids 48, 59, 60, 61, 62, 63, 64: the helper each passive is read through, at every
    level, and the two effect functions (StrongStance's trigger, StunningStrike's stun)."""
    rig.section = 'passives'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    put_vec(mem, pos, (1.0, 2.0, 3.0))
    for level in list(range(0, 41)) + [0xFFFFFFFF, 77]:
        rig.do('SkillArchery_getStat0Fraction', 'archery_fraction', (skill_obj(mem, 48), level), ret='f')
        rig.do('SkillLifeTap_getStat0Fraction', 'lifetap_fraction', (skill_obj(mem, 59), level), ret='f')
        rig.do('SkillLifeTap_getStat1', 'lifetap_stat1', (skill_obj(mem, 59), level), ret='i')
        rig.do('SkillStrongStance_getStat0', 'strongstance_stat0', (skill_obj(mem, 62), level), ret='i')
        rig.do('SkillNaturalResistance_getStat0Fraction', 'naturalresistance_fraction', (skill_obj(mem, 63), level), ret='f')
        for sid in (59, 60, 61, 62, 63, 64, 48):
            skill = skill_obj(mem, sid)
            rig.vskill(skill, 1, (world.players[0],))
            rig.vskill(skill, 2, (level, world.players[0], pos, 0))
    world.sample_counts = (1, 3, 7, 7, 12)
    for round_ in range(20 if OPTIONS['quick'] else 300):
        world.place(rng)
        target = rng.choice(world.objects + [0])
        mem.w32(SB.G_PVP_MODE_A, rng.choice((0, 0, 0, 1)))
        rig.do('SkillStunningStrike_getStat0ForTarget', 'stunningstrike_stat0_for',
               (skill_obj(mem, 64), target, rng.choice((0, 1, 2, 3, 5, 6, 7, 20, 40))), ret='i')
        rig.do('SkillStunningStrike_spawnEffect', 'stunningstrike_effect', (skill_obj(mem, 64), target))
        if round_ % 4 == 0:
            player = rng.choice(world.players)
            rig.do('SkillStrongStance_trigger', 'strongstance_trigger',
                   (skill_obj(mem, 62), player, rng.choice(world.objects), rng.choice((0, 0x40000, 0x80000))))
    world.sample_counts = (0, 1, 3, 7, 7, 12)
    mem.w32(SB.G_PVP_MODE_A, 0)
    rig.report('passives', 'ids 48, 59, 60, 61, 62, 63, 64')


def run_spell(rig, name, method, spell, pos, limit, between=None, timer=None):
    """Run a spell's slot 2 tick after tick until it ends itself or `limit` ticks passed;
    `between` may disturb the world before each tick (and returns True when it did, which
    keeps the tick count out of the timers).  Returns the number of runs."""
    mem = rig.emu.mem
    runs, clean = 0, True
    for tick in range(limit):
        mem.w32(RC.G_SIM_FRAME, (mem.u32(RC.G_SIM_FRAME) + 1) & M32)
        if between is not None and between(tick):
            clean = False
        result = rig.do(name, method, (spell, pos, rig.rng.randrange(0x10000)))
        runs += 1
        if ended(result, spell):
            if clean and timer:
                TIMERS.setdefault(timer, set()).add(runs)
            return runs
    return runs


def clear_handles(rig):
    for obj in rig.world.objects:
        rig.do('handle_clear', 'handle_clear', (obj,))


def section_harmtouch(rig):
    """Skill 42: can-use, cast, the countdown, and the hook Player_meleeHit calls."""
    rig.section = 'harmtouch'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos, out = world.scratch, world.scratch + 0x40
    skill = skill_obj(mem, 42)
    world.sample_counts = (1, 3, 7, 7, 12)
    for round_ in range(8 if OPTIONS['quick'] else 60):
        world.place(rng)
        caster = rng.choice(world.players * 2 + world.monsters)
        rig.vskill(skill, 1, (caster,))
        level = rng.choice((1, 5, 10, 11, 20, 40))
        spell = rig.vskill(skill, 2, (level, caster, pos, 0))['ret'] & M32
        if not spell:
            continue
        world.live.add(spell)
        if round_ % 3 == 0:
            run_spell(rig, 'SpellHarmTouch_run', 'harmtouch_run', spell, pos, 200,
                      timer='harmtouch: runs until the unused spell ends itself (0.661 s)')
        else:
            done = False
            for tick in range(rng.randrange(0, 45)):
                if ended(rig.do('SpellHarmTouch_run', 'harmtouch_run', (spell, pos, 0)), spell):
                    done = True
                    break
            if not done or rng.random() < 0.3:          # the swing lands (also on a spell that has ended)
                target = rng.choice(world.objects)
                mem.w32(out, 0xAAAA)
                mem.w32(out + 4, 0xBBBB)
                rig.do('SpellHarmTouch_applyToHit', 'harmtouch_apply_to_hit', (spell, target, out, out + 4))
        world.live.discard(spell)
    world.sample_counts = (0, 1, 3, 7, 7, 12)
    rig.report('harmtouch', 'id 42; player and monster casters')


def section_minorhealing(rig):
    """Skill 50: cast and the heal over its 1.5 seconds, at full and at low hit points."""
    rig.section = 'minorhealing'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    skill = skill_obj(mem, 50)
    for round_ in range(6 if OPTIONS['quick'] else 50):
        world.place(rng)
        caster = rng.choice(world.players * 3 + world.monsters[:1])
        if caster in world.monsters:
            mem.w32(caster + 0x3C8, 0)
        level = rng.choice((1, 5, 10, 20, 40))
        spell = rig.vskill(skill, 2, (level, caster, pos, 0))['ret'] & M32
        if not spell:
            continue
        world.live.add(spell)
        rec = RC.G_PLAYERS + mem.u32(caster + 0x3C8) * RC.REC_SIZE

        def between(tick):
            if rng.random() < 0.1:
                mem.wf32(rec + 0xAC, rng.choice((0.0, 5.0, 118.5, 119.0, 119.5, 120.0, 130.0)))
            return False
        run_spell(rig, 'SpellMinorHealing_run', 'minorhealing_run', spell, pos, 200, between,
                  timer='minorhealing: runs until the spell ends itself (clock above 1.499996 s)')
        world.live.discard(spell)
    rig.report('minorhealing', 'id 50')


def section_holyshield(rig):
    """Skill 54: cast, the shield's lifetime at each rank, and the absorb hook."""
    rig.section = 'holyshield'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    skill = skill_obj(mem, 54)
    world.sample_counts = (1, 3, 7, 7, 12)
    levels = (1, 20) if OPTIONS['quick'] else (1, 2, 3, 5, 10, 20)
    for index in range(len(levels) + (4 if OPTIONS['quick'] else 30)):
        world.place(rng)
        caster = rng.choice(world.players * 2 + world.monsters)
        timed = index < len(levels)
        level = levels[index] if timed else rng.choice((1, 3, 7, 20, 40))
        world.pool_fail = 0.0 if timed else 0.1
        spell = rig.vskill(skill, 2, (level, caster, pos, 0))['ret'] & M32
        if not spell:
            continue
        world.live.add(spell)
        if timed:
            seconds = int(mem.f32(spell + 0x20))
            run_spell(rig, 'SpellHolyShield_run', 'holyshield_run', spell, pos, 4000,
                      timer='holyshield: runs until the spell ends itself, duration %d s' % seconds)
        else:
            for tick in range(rng.randrange(1, 60)):
                if rng.random() < 0.3:
                    rig.do('SpellHolyShield_absorb', 'holyshield_absorb', (spell,), ret='f')
                if rng.random() < 0.05:
                    mem.wf32(spell + 0x18, mem.f32(spell + 0x20) - rng.choice((0.0, 0.01, 0.02, 0.05)))
                if ended(rig.do('SpellHolyShield_run', 'holyshield_run', (spell, pos, 0)), spell):
                    break
        world.live.discard(spell)
    world.sample_counts, world.pool_fail = (0, 1, 3, 7, 7, 12), 0.05
    rig.report('holyshield', 'id 54')


def section_healing(rig):
    """Skills 55 and 86: cast by a player and by a monster (for itself or an ally), the
    heal over its 1.13 seconds for both kinds of owner, with and without PvP mode A."""
    rig.section = 'healing'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    for round_ in range(8 if OPTIONS['quick'] else 80):
        world.place(rng)
        skill = skill_obj(mem, rng.choice((55, 55, 86)))
        caster = rng.choice(world.players * 2 + world.monsters)
        if caster in world.monsters:
            mem.w32(caster + 0xC, rng.choice((0x20, 0x20, 0x20, 0x28)))
        mem.w32(SB.G_PVP_MODE_A, rng.choice((0, 0, 1)))
        slots = rng.sample(range(4), rng.randrange(0, 5))
        mem.w32(SB.G_ALIVE_COUNT, len(slots))
        for i, slot in enumerate(slots):
            mem.w32(SB.G_ALIVE_LIST + 4 * i, slot)
        level = rng.choice((1, 2, 5, 10, 14, 20, 40))
        spell = rig.vskill(skill, 2, (level, caster, pos, 0))['ret'] & M32
        if not spell:
            continue
        world.live.add(spell)
        world.box_counts = (0, 1, 2, 4, 6)

        def between(tick):
            if rng.random() < 0.3:                      # friends come close, hit points move
                other = rng.choice(world.objects)
                put_vec(mem, other + 0x10, [mem.f32(caster + 0x10 + 4 * i) + rng.choice((0.0, 15.0, -40.0, 90.0)) for i in range(3)])
            if rng.random() < 0.1:
                rec = RC.G_PLAYERS + rng.randrange(4) * RC.REC_SIZE
                mem.wf32(rec + 0xAC, rng.choice((0.0, 5.0, 118.9, 119.0, 119.5, 120.0)))
            if rng.random() < 0.02:
                mem.w32(caster + 0xC, mem.u32(caster + 0xC) | 8)       # the owner dies
            return False
        run_spell(rig, 'SpellHealing_run', 'healing_run', spell, pos, 200, between,
                  timer='healing: runs until the spell ends itself (clock above 1.1299 s)')
        world.live.discard(spell)
    world.box_counts = (0, 0, 1, 2, 3, 5, 8)
    mem.w32(SB.G_PVP_MODE_A, 0)
    mem.w32(SB.G_ALIVE_COUNT, 0)
    rig.report('healing', 'ids 55 and 86; player and monster owners')


def section_resurrect(rig):
    """Skill 68: can-use, the target search, the cast and the spell in both modes (one
    player: the self-revive roll; several: raising a dead player), the countdown at each
    duration."""
    rig.section = 'resurrect'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    skill = skill_obj(mem, 68)
    rounds = 16 if OPTIONS['quick'] else 160
    for round_ in range(rounds):
        r = rng.random
        world.place(rng)
        timed = round_ % 8 == 0
        players = rng.choice((1, 1, 2, 3, 4))
        mem.w32(RC.G_NUM_PLAYERS, players)
        mem.w32(SB.G_PVP_MODE_A, 0 if timed else rng.choice((0, 0, 0, 1)))
        caster = rng.choice(world.players[:players] * 3 + world.monsters[:1])
        if caster in world.players:
            mem.w32(caster + 0xC, 0x40)
        for slot in range(4):                           # the dead lie in front of the caster, or do not
            mem.w16(SB.Model.G_DEAD_COUNTDOWN + 2 * slot, rng.choice((0, 0, 30, 60, 61, 240)))
            obj = world.players[slot]
            if r() < 0.1:
                mem.w32(RC.G_PLAYERS + slot * RC.REC_SIZE + RC.REC_OBJ, 0)
            elif r() < 0.7 or timed:
                angle = mem.s16(caster + 0x38) * 3.14159265 * 2 / 65536
                import math
                ahead, side = rng.choice((-13.0, -11.0, 5.0, 60.0, 135.0, 137.0)), rng.choice((-80.0, 0.0, 55.0, 57.0))
                if timed:
                    ahead, side = 20.0 + slot, 0.0
                    mem.w16(SB.Model.G_DEAD_COUNTDOWN + 2 * slot, 0)
                put_vec(mem, obj + 0x10, (mem.f32(caster + 0x10) + ahead * math.cos(angle) - side * math.sin(angle),
                                          mem.f32(caster + 0x14) + ahead * math.sin(angle) + side * math.cos(angle),
                                          mem.f32(caster + 0x18)))
        slots = rng.sample(range(4), rng.randrange(0, 5))
        mem.w32(SB.G_ALIVE_COUNT, len(slots))
        for i, slot in enumerate(slots):
            mem.w32(SB.G_ALIVE_LIST + 4 * i, slot)
        for sp in world.spells:                         # what a carried SpellResurrect points at
            mem.w32(sp + 0x18, rng.choice(world.players))
        rig.vskill(skill, 1, (caster,))
        rig.do('SkillResurrect_findTarget', 'resurrect_find_target', (skill, caster), ret='i')
        rig.do('SkillResurrect_isSlotBeingRaised', 'resurrect_is_being_raised', (skill, rng.randrange(4)), ret='i')
        level = rng.choice((1, 2, 5, 10, 20, 40))
        world.pool_fail = 0.0 if timed else 0.1
        spell = rig.vskill(skill, 2, (level, caster, pos, 0))['ret'] & M32
        if not spell:
            continue
        world.live.add(spell)
        seconds = int(mem.f32(spell + 0x60))

        def between(tick):
            if timed:
                return False
            if r() < 0.02:
                mem.w32(RC.G_NUM_PLAYERS, rng.choice((1, 2, 4)))    # a player joins or leaves under the spell
            if r() < 0.05:
                mem.wf32(spell + 0x60, rng.choice((0.3, 0.25, 0.24, 0.01)))
            if r() < 0.05:
                rig.do('SpellResurrect_onOwnerDeath', 'resurrect_on_owner_death', (spell,), ret='f')
            return True
        run_spell(rig, 'SpellResurrect_run', 'resurrect_run', spell, pos, 3000 if timed else rng.choice((5, 40, 200)), between,
                  timer='resurrect: runs until the spell ends itself, %d s%s' % (seconds, ' (one player)' if players == 1 else ''))
        world.live.discard(spell)
        for slot in range(4):
            mem.w32(RC.G_PLAYERS + slot * RC.REC_SIZE + RC.REC_OBJ, world.players[slot])
    mem.w32(RC.G_NUM_PLAYERS, 4)
    mem.w32(SB.G_PVP_MODE_A, 0)
    mem.w32(SB.G_ALIVE_COUNT, 0)
    world.pool_fail = 0.05
    rig.report('resurrect', 'id 68; one player and several, player and monster casters')


def section_bash(rig):
    """Skill 49: can-use, cast, the wind-up, the strike (several victims, the stun roll,
    the prop fallback) and the end by the animation's status bit."""
    rig.section = 'bash'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    skill = skill_obj(mem, 49)
    world.sample_counts = (1, 3, 7, 7, 12)
    for round_ in range(10 if OPTIONS['quick'] else 150):
        r = rng.random
        world.place(rng)
        caster = rng.choice(world.players * 3 + world.monsters[:1])
        if caster in world.players:
            rec = RC.G_PLAYERS + mem.u32(caster + 0x3C8) * RC.REC_SIZE
            mem.w32(rec + 0x43FC, rng.choice((0, world.item, world.item)))
        rig.vskill(skill, 1, (caster,))
        level = rng.choice((1, 3, 5, 6, 10, 15, 16, 20, 40))
        spell = rig.vskill(skill, 2, (level, caster, pos, 0))['ret'] & M32
        if not spell:
            continue
        world.live.add(spell)
        mem.w16(caster + 0x11A, 0x10)
        world.anim_end = rng.choice((0.0, 0.02, 0.2))

        def between(tick):
            if r() < 0.03:
                mem.w32(caster + 0x450, 1)
            if r() < 0.2:                               # the victim's hit points before the stun roll
                for obj in world.objects:
                    mem.wf32(obj + 0x228, rng.choice((300.0, 300.0, 0.0, -5.0)))
            if r() < 0.1:
                mem.w32(spell + 0x18, 0)                # strike again
            return False
        run_spell(rig, 'SpellBash_run', 'bash_run', spell, pos, rng.choice((3, 30, 80)), between)
        world.live.discard(spell)
        clear_handles(rig)
    world.sample_counts, world.anim_end = (0, 1, 3, 7, 7, 12), 0.25
    rig.report('bash', 'id 49; player and monster casters')


def section_criticalhit(rig):
    """Skill 53 (and the same class as ids 33 and 81): can-use, cast, the aura's run to
    its end, and the helper damage_apply asks for the bonus."""
    rig.section = 'criticalhit'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    for round_ in range(10 if OPTIONS['quick'] else 100):
        r = rng.random
        world.place(rng)
        skill = skill_obj(mem, rng.choice((53, 53, 33, 81)))
        caster = rng.choice(world.players * 3 + world.monsters[:1])
        mem.w32(SB.G_PVP_MODE_A, rng.choice((0, 0, 1)))
        slots = rng.sample(range(4), rng.randrange(0, 5))
        mem.w32(SB.G_ALIVE_COUNT, len(slots))
        for i, slot in enumerate(slots):
            mem.w32(SB.G_ALIVE_LIST + 4 * i, slot)
        for obj in world.players:                       # the party stands close together, or does not
            if r() < 0.7:
                put_vec(mem, obj + 0x10, [mem.f32(caster + 0x10 + 4 * i) + rng.choice((0.0, 15.0, -40.0, 110.0, 400.0)) for i in range(3)])
        rig.vskill(skill, 1, (caster,))
        for _ in range(4):
            rig.do('SkillCriticalHit_critBonusFor', 'criticalhit_bonus_for',
                   (skill, rng.choice(world.players), rng.choice((0, 0, 1, 7, 20))), ret='f')
        timed = round_ % 10 == 0
        level = rng.choice((1, 5, 10, 20, 40))
        world.pool_fail = 0.0 if timed else 0.05
        spell = rig.vskill(skill, 2, (level, caster, pos, 0))['ret'] & M32
        if not spell:
            continue
        world.live.add(spell)
        seconds = int(mem.f32(spell + 0x18))

        def between(tick):
            if timed:
                return False
            if r() < 0.05:
                mem.wf32(spell + 0x18, rng.choice((0.0, 0.01, 1.0, seconds - 1.5, seconds - 2.01)))
            return True
        run_spell(rig, 'SpellCriticalHit_run', 'criticalhit_run', spell, pos, 4000 if timed else rng.choice((5, 60)), between,
                  timer='criticalhit: runs until the spell ends itself, %d s' % seconds)
        world.live.discard(spell)
    mem.w32(SB.G_PVP_MODE_A, 0)
    mem.w32(SB.G_ALIVE_COUNT, 0)
    world.pool_fail = 0.05
    rig.report('criticalhit', 'ids 53, 33 and 81')


SECTION_1_8 = {(37, 1, 15), (37, 1, 25), (46, 2, 6), (46, 2, 16), (46, 2, 26), (46, 2, 36), (57, 2, 15), (57, 2, 25),
               (57, 2, 35), (58, 2, 11), (58, 2, 31)}


def section_float(rig):
    """docs/spec/skills-35-68.md section 1.8 by execution: the original statistics getters
    under the interpreter's console arithmetic and under round-to-nearest.  Tier 1 (slot
    10, levels 1-20) must not differ; tier 2 (slot 11, levels 1-40) must differ in exactly
    the eleven places the specification lists, the console value one lower."""
    emu, mem = rig.emu, rig.emu.mem

    def original(fn, skill, stat, level, model):
        emu.fpu_model = model
        emu.reset_log()
        emu.r[29] = emu.stack_hi - 0x100
        value = ee_emu.s32(emu.call(fn, skill, stat, level, 0) & M32)
        emu.fpu_model = OPTIONS['fpu']
        return value
    tier1, tier2, count = [], set(), 0
    for sid in SB.SKILL_IDS:
        skill = skill_obj(mem, sid)
        for stat in range(5):
            for level in range(1, 41):
                count += 1
                if level <= 20:
                    a, b = (original(0x3C85FC, skill, stat, level, m) for m in ('ps2', 'nearest'))
                    if a != b:
                        tier1.append((sid, stat, level, a, b))
                a, b = (original(0x3C8690, skill, stat, level, m) for m in ('ps2', 'nearest'))
                if a != b:
                    tier2.add((sid, stat, level))
                    if b - a != 1:
                        tier1.append((sid, stat, level, a, b))
    DC.report('float tier 1', len(tier1), count, 'ranks 1-20 of every statistic of ids 35-68: the same integer under the '
              'console arithmetic and under round-to-nearest', tier1)
    wrong = sorted(tier2 ^ SECTION_1_8)
    DC.report('float tier 2', len(wrong), count, 'levels 1-40: the two arithmetics differ in exactly the eleven places of '
              'section 1.8 (id, statistic, level), the console value one lower', wrong)


def section_timers(rig):
    """The whole-second timers of the matched spells, settled by execution: the number of
    run calls until the spell ends itself for every duration its statistics can give
    (docs/spec/skills-35-68.md section 1.8 says the quoted counts shift by one frame under
    the console's arithmetic)."""
    rig.section = 'timers'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    world.pool_fail, world.sample_counts = 0.0, (3,)
    spans = (1, 13) if OPTIONS['quick'] else range(1, 14)
    for seconds in spans:                               # Resurrect, several players: total and the respawn call
        world.place(rng)
        mem.w32(RC.G_NUM_PLAYERS, 2)
        mem.w32(SB.G_PVP_MODE_A, 0)
        mem.w32(SB.G_ALIVE_COUNT, 0)
        caster, body = world.players[0], world.players[1]
        mem.w32(caster + 0xC, 0x40)
        put_vec(mem, body + 0x10, (mem.f32(caster + 0x10), mem.f32(caster + 0x14), mem.f32(caster + 0x18)))
        mem.w16(SB.Model.G_DEAD_COUNTDOWN + 2, 0)
        mem.w16(SB.Model.G_DEAD_COUNTDOWN, 240)
        mem.w16(caster + 0x38, 0)
        put_vec(mem, body + 0x10, (mem.f32(caster + 0x10) + 20.0, mem.f32(caster + 0x14), mem.f32(caster + 0x18)))
        spell = rig.vskill(skill_obj(mem, 68), 2, (1, caster, pos, 0))['ret'] & M32
        assert spell
        world.live.add(spell)
        mem.wf32(spell + 0x60, float(seconds))
        runs, respawn = 0, None
        while runs < 2000:
            runs += 1
            result = rig.do('SpellResurrect_run', 'resurrect_run', (spell, pos, 0))
            if respawn is None and any(name == 'player_respawn' for name, _args in result['emu_calls']):
                respawn = runs
            if ended(result, spell):
                break
        TIMERS.setdefault('resurrect, %2d s: run calls in total / the call that respawns the target' % seconds,
                          set()).add('%d / %s' % (runs, respawn))
        world.live.discard(spell)
        mem.w32(RC.G_PLAYERS + RC.REC_SIZE + RC.REC_OBJ, world.players[1])
    mem.w32(RC.G_NUM_PLAYERS, 4)
    for sid, name, method, off, spans in ((54, 'SpellHolyShield_run', 'holyshield_run', 0x20, range(10, 21)),
                                          (53, 'SpellCriticalHit_run', 'criticalhit_run', 0x18, range(8, 14))):
        for seconds in ((spans[0], spans[-1]) if OPTIONS['quick'] else spans):
            world.place(rng)
            caster = world.players[0]
            spell = rig.vskill(skill_obj(mem, sid), 2, (1, caster, pos, 0))['ret'] & M32
            assert spell
            world.live.add(spell)
            mem.wf32(spell + off, float(seconds))
            run_spell(rig, name, method, spell, pos, 4000,
                      timer='%s, %2d s: run calls until the spell ends itself' % (SB.SKILL_NAMES[sid], seconds))
            world.live.discard(spell)
    world.pool_fail, world.sample_counts = 0.05, (0, 1, 3, 7, 7, 12)
    rig.report('timers', 'Resurrect 1-13 s, HolyShield 10-20 s, CriticalHit 8-13 s')


ANIM_ADVANCE = 0x16D748


def real_anim_advance(rig, state, record_reads=False):
    """Run the executable's anim_advance (tools/ref_anim.py models it) on an animation
    state: speed 1.0, no sound position, no root or yaw output.  Returns the event bits."""
    emu = rig.emu
    emu.reset_log()
    emu.reads = [] if record_reads else None
    emu.r[29] = emu.stack_hi - 0x100
    emu.f[12] = C.ONE
    stub = emu.hooks.pop(ANIM_ADVANCE)                  # a stub everywhere else in this script
    try:
        events = emu.call(ANIM_ADVANCE, state, 0, 0, 0) & 0xFF
    finally:
        emu.hooks[ANIM_ADVANCE] = stub
    assert not emu.calls, 'anim_advance made a call: %s' % [hex(c.target) for c in emu.calls]
    return events


def spin(rig, length, level, copy_at):
    """One Cyclone of player 1 from the cast to the tick its stop clip starts, with the
    executable's own anim_advance producing the event bits from the shared clip header.
    copy_at: the tick before which the prediction copy of player 0 (same class, so the
    same clip) casts Cyclone - on its owner's machine only - or None.  Returns the tick
    the spin ended on (None: not within 400 ticks)."""
    mem, world = rig.emu.mem, rig.world
    world.place(random.Random(77))
    world.pool_fail = 0.0
    skill = skill_obj(mem, 41)
    player, ghost = world.players[1], world.ghost
    for obj in (player, ghost):
        mem.w32(obj + 0xC, 0x40 | (0x20000 if obj == ghost else 0))
        mem.w32(obj + 0x24, world.class_def)
    clip = world.on_res_find((world.lump, SB.Model.S_CYCLONE_CLIP1), None, None).ret
    mem.w32(clip, 1)
    mem.w32(clip + 4, length)
    mem.w32(clip + 0x38, 0)
    pos = world.scratch
    put_vec(mem, pos, [mem.f32(player + 0x10 + 4 * i) for i in range(3)])
    spell = rig.vskill(skill, 2, (level, player, pos, 0))['ret'] & M32
    world.live.add(spell)
    state = player + 0x114                              # what the stubbed anim_push would have left
    mem.w32(state, 0)
    mem.w8(state + 4, 1)
    mem.w8(state + 5, 8)
    for off, value in ((0, clip), (4, 0), (8, C.ONE), (0xC, 0), (0x10, C.ONE), (0x14, 0), (0x18, 0), (0x1C, 0x23)):
        mem.w32(state + 8 + off, value)
    end = None
    for tick in range(1, 401):
        if copy_at == tick:
            other = rig.vskill(skill, 2, (level, ghost, pos, 0))['ret'] & M32     # Player_castSkill ends it at once
            assert other and other != spell
        world.forced_events = real_anim_advance(rig, state)
        result = rig.do('SpellCyclone_run', 'cyclone_run', (spell, pos, 0))
        world.forced_events = None
        if mem.u32(spell + 0x5C) or ended(result, spell):
            end = tick
            break
    world.live.discard(spell)
    world.pool_fail = 0.05
    for obj in world.objects:
        rig.do('handle_clear', 'handle_clear', (obj,))
    return end


def section_sb1(rig):
    """FINDINGS SB1 by execution: the stores of SpellCyclone_ctor into the shared clip
    header are made for a prediction-copy caster; anim_advance is the reader; and a copy's
    cast moves the end of another player's spin."""
    rig.section = 'sb1'
    mem, world, emu = rig.emu.mem, rig.world, rig.emu
    world.place(random.Random(5))
    world.pool_fail = 0.0
    ghost = world.ghost
    pos = world.scratch
    put_vec(mem, pos, (0.0, 0.0, 0.0))
    clip = world.on_res_find((world.lump, SB.Model.S_CYCLONE_CLIP1), None, None).ret
    mem.w32(clip + 0x14, 0x40A00000)
    mem.w8(clip + 0x18, 0)
    result = rig.vskill(skill_obj(mem, 41), 2, (5, ghost, pos, 0))
    stores = {pc: (addr - clip, value) for pc, addr, _size, value in emu.writes if clip <= addr < clip + 0x80}
    voiced = any(name == 'player_voice' for name, _args in result['emu_calls'])
    ok = stores == {0x2D1978: (0x18, 1), 0x2D197C: (0x14, 0x3D4CCCCC)} and not voiced and mem.u32(ghost + 0xC) & 0x20000
    DC.report('sb1 stores', 0 if ok else 1, 1, 'SpellCyclone_ctor for a caster with flag 0x20000: stores at 0x2d1978 (mask 1) '
              'and 0x2d197c (0.05 s) into the clip header, and the non-copy part (voice line) skipped', [str(stores)])
    # the reader
    state = world.scratch + 0x100
    for off in range(0, 0x108, 4):
        mem.w32(state + off, 0)
    mem.w8(state + 4, 1)
    mem.w8(state + 5, 8)
    mem.w32(clip, 1)
    mem.w32(clip + 4, 40)
    observed = []
    for time_ticks, slot_time in ((2.0, 0x3D4CCCCC), (3.0, 0x3D4CCCCC), (10.0, 0x3D4CCCCC), (10.0, f32(10.5 / 60))):
        for off, value in ((0, clip), (4, 0), (8, C.ONE), (0xC, 0), (0x10, C.ONE), (0x14, 0), (0x18, f32(time_ticks)), (0x1C, 0x23)):
            mem.w32(state + 8 + off, value)
        mem.w8(state + 4, 1)
        mem.w32(clip + 0x14, slot_time)
        events = real_anim_advance(rig, state, record_reads=True)
        readers = sorted({(pc, addr - clip) for pc, addr, _size, _value in emu.reads if clip + 0x14 <= addr < clip + 0x1C})
        observed.append((time_ticks, slot_time, events, readers))
    emu.reads = None
    ok = [o[2] for o in observed] == [0, 1, 0, 1] and all((0x16D874, 0x14) in o[3] for o in observed) \
        and all(((0x16D898, 0x18) in o[3]) == bool(o[2]) for o in observed)
    DC.report('sb1 reader', 0 if ok else 1, 4, 'anim_advance reads slot 0 of the clip header (time at 0x16d874, mask at '
              '0x16d898) and returns the mask only on the tick the slot time falls in', [str(observed)])
    world.pool_fail = 0.05
    # the consequence
    rows, moved = [], 0
    for length, level in ((20, 1), (30, 1), (30, 12)):
        if True:
            base = spin(rig, length, level, None)
            for copy_at in (5, 11, 12):
                other = spin(rig, length, level, copy_at)
                rows.append((length, level, copy_at, base, other))
                moved += base != other
    DC.report('sb1 consequence', 0 if moved else 1, len(rows), 'spin of one player with and without a prediction copy of '
              'the same class casting Cyclone in between: the tick the spin ends on moved in %d of %d cases' % (moved, len(rows)))
    print('      clip ticks / level / copy casts before tick / spin ends on tick without, with the copy: '
          + ', '.join('%d/%d/%d: %s, %s' % row for row in rows))
    rig.report('sb1', 'the calls made while establishing SB1')


SECTIONS = [('stats', section_stats), ('float', section_float), ('base', section_base), ('cyclone', section_cyclone), ('sb1', section_sb1),
            ('firearrow', arrow_section(43, 'firearrow', 'FireArrowProjectile', 0x6C, 0x68, 0xAC)),
            ('coldarrow', arrow_section(44, 'coldarrow', 'ColdArrowProjectile', 0x68, 0x6C, 0xAC)),
            ('poisonarrow', arrow_section(45, 'poisonarrow', 'PoisonArrowProjectile', 0x68, 0x6C, 0xAC)),
            ('multifire', section_multifire), ('passives', section_passives),
            ('harmtouch', section_harmtouch), ('minorhealing', section_minorhealing),
            ('holyshield', section_holyshield), ('healing', section_healing), ('resurrect', section_resurrect),
            ('bash', section_bash), ('criticalhit', section_criticalhit), ('timers', section_timers),
            ('explodearrow', arrow_section(47, 'explodearrow', 'ExplodeArrowProjectile', 0x68, 0x6C, 0x70,
                                           end_name='explode', end_method='explode'))]


# =========================================================================================
# The second pass: the casts and effects of ids 35-40, 51, 52, 56-58 and 65-67.  The
# sections are appended to SECTIONS, after the ones of the first pass, so that those draw
# the same random scenarios as before.
# =========================================================================================
COPY_ROWS = {}                  # skill id -> {what: [(pc, where), ...]}: the prediction-copy table


def note_stores(rig, sid, what, own=()):
    """After a call: the stores the original made outside the stack that are not into a
    block pool_new had just handed it and not the shared seed - what a cast leaves behind
    that destroying its spell would not undo.  The first one of every call is kept, and
    every distinct place, in order of first appearance.  `own` (third pass, for a run
    function): blocks of earlier calls that are the skill's own objects as well."""
    world = rig.world
    row = COPY_ROWS.setdefault(sid, {}).setdefault(what, {'first': set(), 'all': []})
    first = None
    mine = list(world.allocated) + list(own)
    for pc, addr, _size, _value in rig.emu.writes:
        if RC.G_RAND_SEED <= addr < RC.G_RAND_SEED + 4 or any(b <= addr < b + 0x400 for b in mine):
            continue
        if world.node_lo <= addr < world.node_hi or addr == SB.G_HANDLE_FREE:
            continue                                    # list nodes: freed with the spell
        entry = (pc, rig.where(addr))
        if first is None:
            first = entry
        if entry not in row['all']:
            row['all'].append(entry)
    row['first'].add(first)


def section_charge(rig):
    """Skill 35: cast (player, monster), the rush frame by frame, the contact handler with
    a creature, a prop, a wall and nothing in reach, the end by time and by contact."""
    rig.section = 'charge'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    skill = skill_obj(mem, 35)
    world.sample_counts = (1, 3, 7, 7, 12)
    for round_ in range(8 if OPTIONS['quick'] else 90):
        world.place(rng)
        caster = rng.choice(world.players * 3 + world.monsters[:1])
        rig.vskill(skill, 1, (caster,))
        level = rng.choice((1, 5, 8, 9, 10, 12, 20, 40))
        spell = rig.vskill(skill, 2, (level, caster, pos, 0))['ret'] & M32
        note_stores(rig, 35, 'cast')
        if not spell:
            continue
        world.live.add(spell)
        rig.do('SpellCharge_getStat3Scaled', 'charge_stat3_scaled', (spell,), ret='f')
        for tick in range(rng.choice((3, 20, 50))):
            mem.w32(RC.G_SIM_FRAME, (mem.u32(RC.G_SIM_FRAME) + 1) & M32)
            if rng.random() < 0.02:                     # the clock behind the cast: the difference is unsigned
                mem.w32(RC.G_SIM_FRAME, (mem.u32(spell + 0x44) - 1) & M32)
            if rng.random() < 0.1:
                rig.do('SpellCharge_onContact', 'charge_on_contact', (spell, rng.choice([0, 0] + world.objects)))
            if ended(rig.do('SpellCharge_run', 'charge_run', (spell, pos, 0)), spell):
                break
        world.live.discard(spell)
    world.sample_counts = (0, 1, 3, 7, 7, 12)
    rig.report('charge', 'id 35; player and monster casters')


SECTIONS.append(('charge', section_charge))


def run_object(rig, name, method, obj, limit, between=None):
    """Run an every-frame object until it deletes itself (obj_delete or its slot 1) or
    `limit` runs passed.  Returns the number of runs."""
    mem = rig.emu.mem
    for tick in range(limit):
        mem.w32(RC.G_SIM_FRAME, (mem.u32(RC.G_SIM_FRAME) + 1) & M32)
        if between is not None:
            between(tick)
        result = rig.do(name, method, (obj,))
        calls = result['emu_calls']
        if ('obj_delete', (obj,)) in calls or ('Creature.v1', (obj, 3)) in calls or result['fault'] \
                or result['both_fault'] is not None:
            return tick + 1
    return limit


def section_darkness(rig):
    """Skill 36: cast, and the cloud from its flight to its end: stopped by terrain,
    attaching to the first enemy in its box with the damage call for each, the blind roll
    every 30 frames, the caster gone."""
    rig.section = 'darkness'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    skill = skill_obj(mem, 36)
    for round_ in range(6 if OPTIONS['quick'] else 70):
        world.place(rng)
        caster = rng.choice(world.players * 2 + world.monsters)
        for i in range(4):
            mem.w8(SB.Model.G_AMBIENT_BYTES + i, rng.randrange(256))
        rig.vskill(skill, 1, (caster,))
        rig.vskill(skill, 2, (rng.choice((1, 2, 5, 10, 20, 40)), caster, pos, rng.randrange(0x10000)))
        note_stores(rig, 36, 'cast')
        if not world.allocated:
            continue
        cloud = world.allocated[0]
        world.live.add(cloud)
        world.box_counts = rng.choice(((0, 0, 0, 0, 0, 1, 2), (0, 1, 2, 3, 5)))
        world.ground_up = rng.choice((0.0, 0.05, 0.4))
        quiet = rng.random() < 0.3

        def between(tick):
            if tick < 3 and quiet:
                world.box_counts = (0,)
            elif quiet:
                world.box_counts = (0, 1, 2, 3, 5)
            if rng.random() < 0.5:                      # the blind roll happens on frames divisible by 30
                frame = mem.u32(RC.G_SIM_FRAME)
                mem.w32(RC.G_SIM_FRAME, frame + 30 - frame % 30)
            if rng.random() < 0.1:
                for obj in world.objects:
                    mem.wf32(obj + 0x228, rng.choice((300.0, 300.0, 0.0, -5.0)))
                    mem.w16(obj + 0x316, rng.choice((0, 0, 0, 40)))
            if rng.random() < 0.03 and mem.u32(cloud + 0xA8):
                rig.do('handle_clear', 'handle_clear', (cloud + 0xA8,))      # the caster is deleted
            if tick == 40 and rng.random() < 0.5:
                mem.w32(cloud + 0x94, rng.choice((0, 1, 2)))                 # the last frames
        run_object(rig, 'DarknessProjectile_run', 'darkness_run', cloud, 130, between)
        world.live.discard(cloud)
        clear_handles(rig)
    world.box_counts, world.ground_up = (0, 0, 1, 2, 3, 5, 8), 0.4
    rig.report('darkness', 'id 36; player and monster casters')


SECTIONS.append(('darkness', section_darkness))


def section_shock(rig):
    """Skill 37: cast (player, monster, no caster), the bolt's flight, the terrain stop,
    the hit test on every eighth frame with the chain it builds and the damage calls, the
    beams of the struck state, the caster deleted in flight, the end."""
    rig.section = 'shock'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    skill = skill_obj(mem, 37)
    for round_ in range(5 if OPTIONS['quick'] else 60):
        world.place(rng)
        caster = rng.choice(world.players * 2 + world.monsters + [0])
        near = rng.choice(world.objects)
        put_vec(mem, pos, (mem.f32(near + 0x10) + rng.uniform(-60, 60), mem.f32(near + 0x14) + rng.uniform(-60, 60),
                           mem.f32(near + 0x18) + 30.0))
        if caster:
            rig.vskill(skill, 1, (caster,))
        rig.vskill(skill, 2, (rng.choice((1, 2, 5, 9, 10, 11, 20, 40)), caster, pos, rng.randrange(0x10000)))
        note_stores(rig, 37, 'cast')
        if not world.allocated:
            continue
        bolt = world.allocated[0]
        world.live.add(bolt)
        world.box_counts = rng.choice(((0, 1, 2, 3), (2, 3, 5, 8), (0, 0, 0, 1)))
        world.ground_up = rng.choice((0.0, 0.0, 0.03))
        ending = rng.random() < 0.3

        def between(tick):
            frame = mem.u32(RC.G_SIM_FRAME)
            if rng.random() < 0.5:
                mem.w32(RC.G_SIM_FRAME, frame + 8 - frame % 8)       # the hit test runs on every eighth frame
            if rng.random() < 0.3 and mem.u8(bolt + 0x189) == 0:     # the bolt reaches something
                victim = rng.choice(world.objects)
                put_vec(mem, bolt + 0x10, (mem.f32(victim + 0x10) + rng.uniform(-20, 20),
                                           mem.f32(victim + 0x14) + rng.uniform(-20, 20), mem.f32(bolt + 0x18)))
            if rng.random() < 0.04 and mem.u32(bolt + 0x194):
                rig.do('handle_clear', 'handle_clear', (bolt + 0x194,))      # the caster is deleted
            if rng.random() < 0.05:
                victim = rng.choice(world.objects)
                mem.w32(victim + 0xC, mem.u32(victim + 0xC) | 8)             # somebody dies
            if ending and tick == 12:
                mem.w32(bolt + 0x58, (mem.u32(RC.G_SIM_FRAME) - rng.choice((262, 268, 297, 298))) & M32)
        run_object(rig, 'ShockProjectile_run', 'shock_run', bolt, 44, between)
        for off in (0x50, 0x54, 0x194):
            rig.do('handle_clear', 'handle_clear', (bolt + off,))
        world.live.discard(bolt)
        clear_handles(rig)
    world.box_counts, world.ground_up = (0, 0, 1, 2, 3, 5, 8), 0.4
    rig.report('shock', 'id 37; player, monster and absent casters')


SECTIONS.append(('shock', section_shock))


def section_shadowstep(rig):
    """Skill 67: cast at every rank (no fire, the centre fire, the ring), the enemies that
    lose their target and are pulled, and the 25 frames of the step, offline and in a net
    game."""
    rig.section = 'shadowstep'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    skill = skill_obj(mem, 67)
    world.sample_counts = (1, 3, 7, 7, 12)
    kept = mem.u8(RC.G_NETWORK_MODE)
    for round_ in range(6 if OPTIONS['quick'] else 70):
        world.place(rng)
        caster = rng.choice(world.players * 3 + world.monsters[:1])
        mem.w8(RC.G_NETWORK_MODE, rng.choice((0, 1)))
        for obj in world.monsters:                      # some creatures are after the caster
            target = rng.choice((caster, caster, world.players[1], 0))
            if target:
                rig.do('handle_link', 'handle_link', (obj + 0x234, target, target), ret='i')
        rig.vskill(skill, 1, (caster,))
        spell = rig.vskill(skill, 2, (rng.choice((1, 2, 4, 5, 6, 7, 12, 20, 40)), caster, pos, 0))['ret'] & M32
        note_stores(rig, 67, 'cast')
        if spell:
            world.live.add(spell)
            runs = run_spell(rig, 'SpellShadowStep_run', 'shadowstep_run', spell, pos, 40,
                             timer='shadowstep: runs until the spell ends itself')
            world.live.discard(spell)
        for obj in world.monsters:
            rig.do('handle_clear', 'handle_clear', (obj + 0x234,))
        clear_handles(rig)
    mem.w8(RC.G_NETWORK_MODE, kept)
    world.sample_counts = (0, 1, 3, 7, 7, 12)
    rig.report('shadowstep', 'id 67; player and monster casters; offline and net game')


STATIC_FIRE = {'ctor': 0x2C5240, 'initCommon': 0x2C5814, 'run': 0x2C595C}


def section_sb3(rig):
    """FINDINGS SB3: the ORIGINAL StaticFire constructor and run function, executed as they
    are (no model beside them; everything they call that this file does not run is a stub
    returning 0), to see what they do with the owner argument."""
    rig.section = 'sb3'
    emu, mem, world, rng = rig.emu, rig.emu.mem, rig.world, rig.rng
    hooks = {addr: emu.hooks.pop(addr) for addr in STATIC_FIRE.values() if addr in emu.hooks}
    rig.real.addresses.update(STATIC_FIRE.values())
    rounds = 6 if OPTIONS['quick'] else 40
    stored = linked = fresh = stale_creature = stale_other = faults = 0
    for round_ in range(rounds):
        world.place(rng)
        owner, victim = world.players[0], world.monsters[0]
        mem.w32(owner + 0xC, 0x60)                      # a player object carries the creature flag too
        mem.w32(victim + 0xC, 0x20)
        fire = world.blocks[0]
        for off in range(0, 0x400, 4):
            mem.w32(fire + off, 0)
        put_vec(mem, world.scratch, (mem.f32(victim + 0x10), mem.f32(victim + 0x14), mem.f32(victim + 0x18)))
        rig.calls, rig.buffers = [], {}
        rig.script_rng = random.Random(OPTIONS['seed'] + round_)
        rig.eview.pool_cursor = 1
        emu.reset_log()
        emu.r[29] = emu.stack_hi - 0x100
        emu.f[12], emu.f[13] = f32(120.0), f32(1.0)
        try:
            emu.call(STATIC_FIRE['ctor'], fire, world.scratch, 360, owner, round_ & 1, max_steps=6000000)
        except EmuError:
            faults += 1
            continue
        stored += any(addr == fire + 0x4A8 and value == owner for _pc, addr, _size, value in emu.writes)
        linked += any(c.target == SB.FUNCTIONS['handle_link'][0] and (c.args[0] & M32) == fire + 0x4A8 for c in emu.calls)
        mem.w32(fire + 0x7C, 300)                       # still burning
        mem.wf32(fire + 0x64, 1.0)
        for case in ('alive', 'reused as a creature', 'reused as something else'):
            if case == 'reused as a creature':          # the player object was destroyed, its memory handed out again
                for off in range(0, 0x600, 4):
                    mem.w32(owner + off, 0)
                mem.w32(owner + 0xC, 0x20)
                mem.w32(owner + 0x48, world.vt_obj)
            elif case == 'reused as something else':
                mem.w32(owner + 0xC, 0x4001)
            frame = mem.u32(RC.G_SIM_FRAME)
            mem.w32(RC.G_SIM_FRAME, frame + 12 - frame % 12)
            world.box_counts = (1,)
            rig.calls = []
            rig.script_rng = random.Random(OPTIONS['seed'] + 7 * round_)
            forced = world.on_world_collectObjectsInBox
            world.on_world_collectObjectsInBox = lambda args, view, rng_: Res(outs=[[victim]])
            emu.reset_log()
            emu.r[29] = emu.stack_hi - 0x100
            try:
                emu.call(STATIC_FIRE['run'], fire, max_steps=6000000)
            except EmuError:
                faults += 1
            world.on_world_collectObjectsInBox = forced
            asked = [args for name, args in rig.calls if name == 'Creature.v20']
            hits = [args for name, args in rig.calls if name == 'damage_apply']
            through = any(a[0] == owner and a[1] == victim for a in asked)
            if case == 'alive':
                fresh += through
            elif case == 'reused as a creature':
                stale_creature += through and all(h[1] == owner for h in hits)
            else:
                stale_other += not asked and bool(hits) and all(h[1] == fire for h in hits)
    world.box_counts = (0, 0, 1, 2, 3, 5, 8)
    rig.real.addresses.difference_update(STATIC_FIRE.values())
    emu.hooks.update(hooks)
    DC.report('sb3 the owner is a plain word', rounds - stored + linked + faults, rounds,
              'StaticFire_ctor stores its owner argument at +0x4a8 (%d of %d) and links no handle for it (%d linked)'
              % (stored, rounds, linked))
    DC.report('sb3 the fire uses it unchecked', (rounds - fresh) + (rounds - stale_creature) + (rounds - stale_other), 3 * rounds,
              'StaticFire_run on a damage frame: is-enemy asked through +0x4a8 with the owner alive (%d), with its memory '
              'reused by another creature (%d: slot 20 of whatever is there, which is then the attacker); reused by a '
              'non-creature the fire itself attacks every creature (%d)' % (fresh, stale_creature, stale_other))


SECTIONS.append(('shadowstep', section_shadowstep))
SECTIONS.append(('sb3', section_sb3))


def section_ancestralcall(rig):
    """Skill 51, the one id of this pass the prediction copy may cast: can-use, cast and
    constructor for a player, a monster and the copy (what the copy's cast leaves behind is
    collected for the prediction-copy table), the run through the cast animation and the
    aura to its end, and the query the damage and swing-speed code asks."""
    rig.section = 'ancestralcall'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos, out = world.scratch, world.scratch + 0x40
    skill = skill_obj(mem, 51)
    copy_calls, copy_casts = set(), 0
    # a sound handle for this section only (the sections of the first pass keep their answers)
    world.on_sound_playOnObject = lambda args, view, rng_: Res(rng_.choice((0xFFFFFFFF, 3, 0x41)))
    for round_ in range(8 if OPTIONS['quick'] else 110):
        world.place(rng)
        caster = rng.choice(world.players * 3 + world.monsters[:1] + [world.ghost] * 2)
        mem.w32(SB.G_PVP_MODE_A, rng.choice((0, 0, 1)))
        count = rng.choice((0, 1, 2, 4))
        mem.w32(SB.G_ALIVE_COUNT, count)
        for i, slot in enumerate(rng.sample(range(4), 4)):
            mem.w32(SB.G_ALIVE_LIST + 4 * i, slot)
        if rng.random() < 0.15:
            mem.w32(RC.G_PLAYERS + 3 * RC.REC_SIZE + RC.REC_OBJ, 0)      # a slot without an object
        put_vec(mem, pos, (mem.f32(caster + 0x10), mem.f32(caster + 0x14), mem.f32(caster + 0x18) + 40.0))
        mem.w32(caster + 0x4A8, rng.choice((0xFFFFFFFF, 0xFFFFFFFF, 5)))
        if caster in world.players:
            mem.w8(RC.G_PLAYERS + mem.u32(caster + 0x3C8) * RC.REC_SIZE + 0x4A86, rng.choice((0, 1, 2, 3, 4, 5, 7)))
        rig.vskill(skill, 1, (caster,))
        result = rig.vskill(skill, 2, (rng.choice((1, 2, 5, 9, 10, 11, 20, 40)), caster, pos, 0))
        spell = result['ret'] & M32
        if caster == world.ghost:
            note_stores(rig, 51, 'cast, prediction copy')
            if spell:
                copy_casts += 1
                copy_calls.update(name for name, _args in result['emu_calls'])
            continue                                    # Player_castSkill destroys the copy's spell at once
        note_stores(rig, 51, 'cast')
        if not spell:
            continue
        world.live.add(spell)
        mem.w16(caster + 0x11A, 0x20)
        world.anim_end = rng.choice((0.0, 0.05, 0.3))
        mode = rng.random()

        def between(tick):
            if tick == 2 and mode < 0.5:                # the beams appear 23 and 47 frames after the cast
                mem.w32(RC.G_SIM_FRAME, (mem.u32(spell + 0x28) + rng.choice((22, 22, 46))) & M32)
            if tick == 12 and mode < 0.5:
                mem.w32(RC.G_SIM_FRAME, (mem.u32(spell + 0x28) + 46) & M32)
            if tick == 30:
                mem.w16(caster + 0x11A, 0)              # the cast clip is over
            if tick == 36:
                mem.wf32(spell + 0x1C, mem.f32(spell + 0x20) - rng.choice((0.02, 0.04, 0.1)))
            if rng.random() < 0.3:
                target = rng.choice(world.objects + [0, caster])
                mem.w32(out, 0xAAAA)
                mem.w32(out + 4, 0xBBBB)
                rig.do('SpellAncestralCall_queryFor', 'ancestralcall_query_for',
                       (spell, target, rng.choice((0, out)), rng.choice((0, out + 4))), ret='i')
            return True
        run_spell(rig, 'SpellAncestralCall_run', 'ancestralcall_run', spell, pos, 44, between)
        world.live.discard(spell)
    mem.w32(SB.G_PVP_MODE_A, 0)
    mem.w32(SB.G_ALIVE_COUNT, 0)
    world.anim_end = 0.25
    del world.on_sound_playOnObject
    rig.report('ancestralcall', 'id 51; player, monster and prediction-copy casters')
    allowed = {'Skill.v14', 'pool_new', 'res_find', 'sound_playOnObject', 'libc_sprintf', 'anim_startBlendInOut'}
    DC.report('ancestralcall prediction copy', len(copy_calls - allowed), copy_casts,
              'the copy\'s cast calls only %s; no light, no state change, no statistic read' % ', '.join(sorted(copy_calls)),
              sorted(copy_calls - allowed))


SECTIONS.append(('ancestralcall', section_ancestralcall))


def section_canuse(rig):
    """Can-use (slot 1) of every id of this pass, for a player, a monster and the
    prediction copy.  The cast-start code asks can-use for the copy as well, so whatever a
    can-use stores would be a store the copy makes: the stores are collected for the
    prediction-copy table (there are none) together with the call-outs."""
    rig.section = 'canuse'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    callouts = {}
    world.on_SpellGiantGrowth_typeinfo = lambda args, view, rng_: Res(0x90A0B0)
    ids = [sid for sid in (35, 36, 37, 38, 39, 40, 51, 56, 57, 58, 65, 66, 67)
           if mem.u32(mem.u32(skill_obj(mem, sid) + 0x60) + 12) in FUNCTION_AT]
    for round_ in range(4 if OPTIONS['quick'] else 40):
        world.place(rng)
        mem.w32(SB.G_PVP_MODE_A, rng.choice((0, 0, 1)))
        mem.w32(world.item, world.item_def)
        mem.w32(world.item_def + 0x20, rng.choice((1, 1, 0, 2)))
        for slot in range(4):
            rec = RC.G_PLAYERS + slot * RC.REC_SIZE
            mem.w8(rec + 0x4A86, rng.choice((2, 2, 0, 4)))
            mem.w8(rec + 0x4A7C, rng.choice((0, 1)))
            for which in range(2):
                mem.w32(rec + 0x4434 + 4 * which, rng.choice((0, world.item)))
        for obj in world.monsters:
            mem.w8(obj + 0xB4, rng.choice((0, 0x10, 0x10, 3)))
        for sid in ids:
            for caster in (rng.choice(world.players), world.monsters[0], world.ghost):
                result = rig.vskill(skill_obj(mem, sid), 1, (caster,))
                if caster == world.ghost:
                    note_stores(rig, sid, 'can-use, prediction copy')
                    callouts.setdefault(sid, set()).update(name for name, _a in result['emu_calls'] if '.' not in name)
    mem.w32(SB.G_PVP_MODE_A, 0)
    del world.on_SpellGiantGrowth_typeinfo
    rig.report('canuse', 'ids %s; player, monster, prediction copy' % ', '.join(str(i) for i in ids))
    stores = sum(len(COPY_ROWS[sid]['can-use, prediction copy']['all']) for sid in ids)
    DC.report('canuse prediction copy', stores, len(ids), 'no can-use of this pass stores anything for the copy; call-outs: '
              + '; '.join('%d %s' % (sid, ', '.join(sorted(names)) or 'none') for sid, names in sorted(callouts.items())))


SECTIONS.append(('canuse', section_canuse))


def convert_section(sid, name, cls):
    def section(rig):
        rig.section = name
        mem, world, rng = rig.emu.mem, rig.world, rig.rng
        pos = world.scratch
        skill = skill_obj(mem, sid)
        world.on_creature_bossRank = lambda args, view, rng_: Res(rng_.choice((0, 0, 0, 0, 1)))
        for round_ in range(6 if OPTIONS['quick'] else 80):
            world.place(rng)
            caster = rng.choice(world.players * 2 + world.monsters[:1])
            for obj in world.objects:
                mem.w8(obj + 0xB4, rng.choice((0, 0x10, 0x10, 3)))
                mem.w16(obj + 0x312, rng.choice((0, 0, 0, 0, 200, 0xFFFF)))
                mem.wf32(obj + 0x354, rng.choice((0.0, 0.0, 0.0, 0.0, 3.5, -1.0)))
                mem.wf32(obj + 0x1C, rng.choice((8.0, 16.0, 20.0, 24.0, 30.0)))
            mem.w32(SB.G_PVP_MODE_A, rng.choice((0, 0, 1)))
            mem.w8(RC.G_PLAYERS + (mem.u32(caster + 0x3C8) & 3) * RC.REC_SIZE + 0x4C24, rng.choice((0, 1, 0xFF)))
            rig.vskill(skill, 1, (caster,))
            spell = rig.vskill(skill, 2, (rng.choice((1, 2, 5, 10, 20, 40)), caster, pos, 0))['ret'] & M32
            note_stores(rig, sid, 'cast')
            if spell:
                world.live.add(spell)

                def between(tick):
                    if rng.random() < 0.05:             # a target is deleted: its node stays, without an object
                        victim = rng.choice(world.monsters)
                        rig.do('handle_clear', 'handle_clear', (victim,))
                    return False
                run_spell(rig, 'Spell%s_run' % cls, name + '_run', spell, pos, 60, between,
                          timer='%s: runs until the spell rolls and ends itself' % name)
                rig.do('handle_clear', 'handle_clear', (spell + 0x18,))
                world.live.discard(spell)
            clear_handles(rig)
        mem.w32(SB.G_PVP_MODE_A, 0)
        del world.on_creature_bossRank
        rig.report(name, 'id %d; player and monster casters' % sid)
    section.__doc__ = 'Skill %d: can-use, cast with its target choice, the spiral, the roll for every target, the end.' % sid
    return section


SECTIONS.append(('convertenemy', convert_section(39, 'convertenemy', 'ConvertEnemy')))
SECTIONS.append(('convertundead', convert_section(40, 'convertundead', 'ConvertUndead')))


def section_groundpound(rig):
    """Skill 38: can-use, the cast (which only starts the clip and writes its event slots),
    and the effect object as Player_run and the monsters build it: constructor on dry
    ground, over water and at a ledge; the first run with its damage and stun rolls; the
    30 runs after it."""
    rig.section = 'groundpound'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    skill = skill_obj(mem, 38)
    for round_ in range(6 if OPTIONS['quick'] else 70):
        world.place(rng)
        caster = rng.choice(world.players * 2 + world.monsters[:1] + [0])
        if caster:
            rig.vskill(skill, 1, (caster,))
            rig.vskill(skill, 2, (rng.choice((1, 5, 10, 20)), caster, pos, 0))
            note_stores(rig, 38, 'cast')
        effect = world.blocks[0]
        for off in range(0, 0x400, 4):
            mem.w32(effect + off, 0)
        origin = caster or world.players[0]
        put_vec(mem, pos, (mem.f32(origin + 0x10), mem.f32(origin + 0x14), mem.f32(origin + 0x18)))
        world.ground_up = rng.choice((0.0, 0.4, 1.0))
        world.on_terrain_height = lambda args, view, rng_: Res(f=f32(fl(args[1][2]) + rng_.choice((0.0, -3.0, 20.0, 143.9, 144.0, -200.0))))
        world.live.add(effect)
        rig.do('GroundPoundEffect_ctor', 'groundpound_effect_ctor',
               (effect, pos, rng.randrange(0x10000), skill, rng.choice((0, 1, 5, 9, 10, 15, 20, 40)), caster))
        del world.on_terrain_height
        world.box_counts = rng.choice(((0, 1, 2, 3), (3, 5, 8)))
        for obj in world.objects:                       # victims round the centre, some far
            if rng.random() < 0.7:
                put_vec(mem, obj + 0x10, (mem.f32(effect + 0x10) + rng.uniform(-150, 150),
                                          mem.f32(effect + 0x14) + rng.uniform(-150, 150), mem.f32(effect + 0x18)))
            mem.wf32(obj + 0x228, rng.choice((300.0, 300.0, 0.0, -5.0)))
        gone = rng.random() < 0.15

        def between(tick):
            if tick == 0 and gone and mem.u32(effect + 0x98):
                rig.do('handle_clear', 'handle_clear', (effect + 0x98,))     # the owner is deleted before the first run
        runs = run_object(rig, 'GroundPoundEffect_run', 'groundpound_effect_run', effect, 40, between)
        TIMERS.setdefault('groundpound: runs of the effect object', set()).add(runs)
        rig.do('handle_clear', 'handle_clear', (effect + 0x98,))
        world.live.discard(effect)
        clear_handles(rig)
    world.box_counts, world.ground_up = (0, 0, 1, 2, 3, 5, 8), 0.4
    rig.report('groundpound', 'id 38; player and monster owners, and none')


SECTIONS.append(('groundpound', section_groundpound))


# =========================================================================================
# The third pass: the casts and effects of ids 56, 57, 58, 65 and 66, appended after the
# sections of the first two passes (which keep their random cases).
# =========================================================================================
def deleted(result, obj):
    """Did the object delete itself in this call (obj_delete or its slot 1 with 3), or did
    the call stop?"""
    calls = result['emu_calls']
    return ('obj_delete', (obj,)) in calls or ('Creature.v1', (obj, 3)) in calls or bool(result['fault']) \
        or result['both_fault'] is not None


def next_frame(mem, rng, multiple=0, chance=0.5):
    """The frame counter one on - or, with the given chance, on to the next multiple."""
    frame = (mem.u32(RC.G_SIM_FRAME) + 1) & M32
    if multiple and rng.random() < chance:
        frame += (multiple - frame % multiple) % multiple
    mem.w32(RC.G_SIM_FRAME, frame & M32)


def stack_word(rig, value, index=0):
    """A word an original function called directly finds on its caller's stack."""
    rig.emu.mem.w32(rig.emu.stack_hi - 0x100 + 8 * index, value & M32)


def section_coneoffrost(rig):
    """Skill 56: cast (player and monster), the channel frame by frame with its three
    particle fans and a DummyDamager on every eighth frame; every DummyDamager run to its
    end (45 frames, the terrain, objects touched every frame, the owner deleted); and the
    DummyDamager built directly with the behaviour bits the monsters use."""
    rig.section = 'coneoffrost'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos, vel = world.scratch, world.scratch + 0x10
    skill = skill_obj(mem, 56)
    world.on_sound_playAtPos = lambda args, view, rng_: Res(rng_.choice((0, 5, 77)))
    for round_ in range(4 if OPTIONS['quick'] else 40):
        world.place(rng)
        caster = rng.choice(world.players * 2 + world.monsters)
        rig.vskill(skill, 1, (caster,))
        spell = rig.vskill(skill, 2, (rng.choice((1, 2, 5, 10, 20, 40)), caster, pos, 0))['ret'] & M32
        note_stores(rig, 56, 'cast')
        if not spell:
            continue
        world.live.add(spell)
        world.box_counts = rng.choice(((0, 1, 2, 3), (0, 0, 0, 1), (2, 3, 5)))
        world.ground_up = rng.choice((0.0, 0.0, 0.03, 0.3))
        bolts = {}
        for tick in range(rng.choice((6, 20, 70))):
            next_frame(mem, rng, 8, 0.3)
            put_vec(mem, pos, (mem.f32(caster + 0x10) + rng.uniform(-9, 9), mem.f32(caster + 0x14) + rng.uniform(-9, 9),
                               mem.f32(caster + 0x18) + rng.uniform(20, 58)))
            rig.do('SpellConeOfFrost_run', 'coneoffrost_run', (spell, pos, rng.randrange(0x10000)))
            note_stores(rig, 56, 'run', own=(spell,))
            for block in world.allocated:
                bolts[block] = [0, rng.random() < 0.3]  # runs so far; left alone
                world.live.add(block)
            for bolt in list(bolts):
                if not bolts[bolt][1] and rng.random() < 0.2:       # something stands in the way
                    victim = rng.choice(world.objects)
                    put_vec(mem, bolt + 0x10, (mem.f32(victim + 0x10) + rng.uniform(-12, 12),
                                               mem.f32(victim + 0x14) + rng.uniform(-12, 12), mem.f32(victim + 0x18) + 20.0))
                if not bolts[bolt][1] and rng.random() < 0.01 and mem.u32(bolt + 0x4C):
                    rig.do('handle_clear', 'handle_clear', (bolt + 0x4C,))      # the caster is deleted
                result = rig.do('DummyDamager_run', 'dummydamager_run', (bolt,))
                bolts[bolt][0] += 1
                if any(name == 'terrain_height' for name, _a in result['emu_calls'][2:]):
                    bolts[bolt][1] = False              # met the terrain
                if deleted(result, bolt):
                    if bolts[bolt][1] and result['both_fault'] is None:
                        TIMERS.setdefault('coneoffrost: runs of a DummyDamager that meets no terrain', set()).add(bolts[bolt][0])
                    rig.do('handle_clear', 'handle_clear', (bolt + 0x4C,))
                    world.live.discard(bolt)
                    del bolts[bolt]
        for bolt in bolts:
            rig.do('handle_clear', 'handle_clear', (bolt + 0x4C,))
            world.live.discard(bolt)
        world.live.discard(spell)
        clear_handles(rig)
    # the object as other code builds it: every combination of the behaviour bits
    world.on_terrain_height = lambda args, view, rng_: Res(f=f32(fl(args[1][2]) + rng_.choice((-40.0, -40.0, -40.0, 3.0))))
    for round_ in range(4 if OPTIONS['quick'] else 40):
        world.place(rng)
        bolt = world.blocks[-1]
        for off in range(0, 0x400, 4):
            mem.w32(bolt + off, 0)
        world.live.add(bolt)
        owner = rng.choice(world.players + world.monsters + [0])
        near = rng.choice(world.objects)
        put_vec(mem, pos, (mem.f32(near + 0x10) + rng.uniform(-40, 40), mem.f32(near + 0x14) + rng.uniform(-40, 40),
                           mem.f32(near + 0x18) + 30.0))
        put_vec(mem, vel, (rng.uniform(-300, 300), rng.uniform(-300, 300), rng.choice((0.0, 0.0, -30.0))))
        stack_word(rig, 1)
        rig.do('DummyDamager_ctor', 'dummydamager_ctor',
               (bolt, pos, vel, rng.choice((1, 2, 9, 45)), rng.choice((6, 10, 24)),
                rng.choice((0, 1, 2, 3, 8, 0xA, 0xC, 0x10, 0x12, 0x18, 0x1F)), rng.choice((0, 0x40, 0x80C040)), owner),
               fargs=(f32(rng.choice((0.0, 46.5, 300.0, 40000.0))),))
        world.box_counts = rng.choice(((0, 1, 2), (2, 3, 5)))
        for tick in range(12):
            next_frame(mem, rng)
            if rng.random() < 0.3:
                victim = rng.choice(world.objects)
                put_vec(mem, bolt + 0x10, (mem.f32(victim + 0x10) + rng.uniform(-12, 12),
                                           mem.f32(victim + 0x14) + rng.uniform(-12, 12), mem.f32(victim + 0x18) + 20.0))
            if deleted(rig.do('DummyDamager_run', 'dummydamager_run', (bolt,)), bolt):
                break
        rig.do('handle_clear', 'handle_clear', (bolt + 0x4C,))
        world.live.discard(bolt)
        clear_handles(rig)
    del world.on_terrain_height
    del world.on_sound_playAtPos
    world.box_counts, world.ground_up = (0, 0, 1, 2, 3, 5, 8), 0.4
    rig.report('coneoffrost', 'id 56; player and monster casters; DummyDamager with every behaviour bit')


SECTIONS.append(('coneoffrost', section_coneoffrost))


def section_shockoffire(rig):
    """Skill 57: cast (player and monster, with and without splash), the spark's flight
    with its particles, the direct hit on the first enemy touched, the terrain, the time
    limit, the burst with its area damage, the owner deleted in flight."""
    rig.section = 'shockoffire'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    skill = skill_obj(mem, 57)
    rounds = 5 if OPTIONS['quick'] else 60
    for round_ in range(rounds):
        world.place(rng)
        caster = rng.choice(world.players * 2 + world.monsters)
        near = rng.choice(world.objects)
        put_vec(mem, pos, (mem.f32(near + 0x10) + rng.uniform(-60, 60), mem.f32(near + 0x14) + rng.uniform(-60, 60),
                           mem.f32(near + 0x18) + 30.0))
        rig.vskill(skill, 1, (caster,))
        rig.vskill(skill, 2, (rng.choice((1, 2, 4, 5, 9, 10, 11, 20, 40)), caster, pos, rng.randrange(0x10000)))
        note_stores(rig, 57, 'cast')
        if not world.allocated:
            continue
        spark = world.allocated[0]
        world.live.add(spark)
        quiet = round_ < 2                              # two sparks that meet nothing: the time limit
        world.box_counts = (0,) if quiet else rng.choice(((0, 1, 2, 3), (2, 3, 5, 8), (0, 0, 0, 1)))
        world.ground_up = 0.0 if quiet else rng.choice((0.0, 0.0, 0.03))
        ending = rng.random() < 0.3
        runs = 0
        for tick in range(700 if quiet else 40):
            next_frame(mem, rng)
            if not quiet:
                if rng.random() < 0.25:                 # the spark reaches something
                    victim = rng.choice(world.objects)
                    put_vec(mem, spark + 0x10, (mem.f32(victim + 0x10) + rng.uniform(-20, 20),
                                                mem.f32(victim + 0x14) + rng.uniform(-20, 20), mem.f32(victim + 0x18) + 20.0))
                if rng.random() < 0.03 and mem.u32(spark + 0x4C):
                    rig.do('handle_clear', 'handle_clear', (spark + 0x4C,))     # the caster is deleted
                if ending and tick == 12:
                    mem.w32(spark + 0x54, (mem.u32(RC.G_SIM_FRAME) + rng.choice((0, 1, 2))) & M32)
            runs += 1
            if deleted(rig.do('Sparks_run', 'sparks_run', (spark,)), spark):
                if quiet:
                    TIMERS.setdefault('shockoffire: runs of a spark that meets nothing', set()).add(runs)
                break
        rig.do('handle_clear', 'handle_clear', (spark + 0x4C,))
        world.live.discard(spark)
        clear_handles(rig)
    world.box_counts, world.ground_up = (0, 0, 1, 2, 3, 5, 8), 0.4
    rig.report('shockoffire', 'id 57; player and monster casters')


SECTIONS.append(('shockoffire', section_shockoffire))


def section_froststorm(rig):
    """Skill 58: cast (player: moved ahead, no wait; monster: the 40-frame wait and the
    warning light built in line), the storm frame by frame (snow, the shards of every
    tenth frame with the pool refusing some, the ground particles, the damage tick of
    every thirtieth frame with and without a caster, the shrinking end), and the shards
    it made run until they land or time out."""
    rig.section = 'froststorm'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    skill = skill_obj(mem, 58)
    world.on_terrain_height = lambda args, view, rng_: Res(f=f32(fl(args[1][2]) + rng_.choice((-90.0, -90.0, -90.0, -16.0, -15.9, 2.0))))
    for round_ in range(3 if OPTIONS['quick'] else 30):
        world.place(rng)
        caster = rng.choice(world.players * 2 + world.monsters)
        put_vec(mem, pos, (mem.f32(caster + 0x10) + rng.uniform(-9, 9), mem.f32(caster + 0x14) + rng.uniform(-9, 9),
                           mem.f32(caster + 0x18) + rng.uniform(20, 58)))
        rig.vskill(skill, 1, (caster,))
        level = rng.choice((1, 1, 2, 5, 10, 20, 40))
        rig.vskill(skill, 2, (level, caster, pos, rng.randrange(0x10000)))
        note_stores(rig, 58, 'cast')
        if not world.allocated:
            continue
        storm = world.allocated[0]
        world.live.add(storm)
        world.box_counts = rng.choice(((0, 1, 2, 3), (2, 3, 5, 8)))
        waited = mem.u32(storm + 0x50) != 0
        quiet = rng.random() < 0.4                      # left alone to its end: the frame counts
        if quiet:                                       # ... but not for the whole duration
            mem.w32(storm + 0x4C, (max(mem.u32(storm + 0x50), mem.u32(RC.G_SIM_FRAME)) + rng.choice((3, 12, 33))) & M32)
        radius, shrinking = int(mem.f32(storm + 0x54)), 0
        shards = []
        for tick in range(140):
            next_frame(mem, rng, rng.choice((10, 30)), 0.0 if quiet else 0.3)
            if not quiet:
                if rng.random() < 0.03 and mem.u32(storm + 0x6C):
                    rig.do('handle_clear', 'handle_clear', (storm + 0x6C,))     # the caster is deleted
                if tick == 20 + (40 if waited else 0):
                    mem.w32(storm + 0x4C, (mem.u32(RC.G_SIM_FRAME) + rng.choice((0, 5, 31))) & M32)
            if mem.u32(storm + 0x58) == f32(0.95):
                shrinking += 1
            result = rig.do('FrostStormSpell_run', 'froststorm_run', (storm,))
            for block in world.allocated:
                if len(shards) < 5:
                    shards.append(block)
                    world.live.add(block)
            for shard in list(shards):
                if rng.random() < 0.02:
                    mem.w32(shard + 0x60, mem.u32(RC.G_SIM_FRAME))              # its time is up
                if deleted(rig.do('FrostStormIceShard_run', 'iceshard_run', (shard,)), shard):
                    shards.remove(shard)
                    world.live.discard(shard)
            if deleted(result, storm):
                if quiet:
                    TIMERS.setdefault('froststorm: radius -> runs with the factor 0.95 before the storm deletes itself',
                                      set()).add('%d -> %d' % (radius, shrinking))
                break
        for shard in shards:
            world.live.discard(shard)
        rig.do('handle_clear', 'handle_clear', (storm + 0x6C,))
        world.live.discard(storm)
        clear_handles(rig)
    del world.on_terrain_height
    world.box_counts = (0, 0, 1, 2, 3, 5, 8)
    rig.report('froststorm', 'id 58; player and monster casters')


SECTIONS.append(('froststorm', section_froststorm))


def sample_point_with_matrix(args, view, rng):
    """model_getSamplePoint as SpellGiantGrowth_emitParticles asks it: a point near the
    position, a number, and a 3x3 matrix (when the caller wants one)."""
    pos = args[2]
    point = tuple(f32(fl(pos[i]) + rng.uniform(-30, 30)) for i in range(3))
    matrix = tuple(f32(rng.uniform(-1, 1)) for _ in range(9))
    return Res(outs=[point, (f32(rng.choice((0.0, 250.0, 1000.0, -40.0))), 0, f32(1.0)), matrix])


def section_giantgrowth(rig):
    """Skill 65: can-use, cast (a player; a monster gets nothing), the constructor, and
    the spell run to its end: growing, holding, shrinking, the thirty frames after; the
    owner deleted; the scale changed from outside; the speed factor in the player record."""
    rig.section = 'giantgrowth'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    skill = skill_obj(mem, 65)
    world.sample_counts = (1, 3, 7, 7, 12)
    world.on_SpellGiantGrowth_typeinfo = lambda args, view, rng_: Res(0x90A0B0)
    world.on_model_getSamplePoint = sample_point_with_matrix
    for round_ in range(4 if OPTIONS['quick'] else 24):
        world.place(rng)
        quiet = round_ < (1 if OPTIONS['quick'] else 3)                 # casts left alone: the frame counts
        caster = rng.choice(world.players * 4 + world.monsters[:1]) if not quiet else world.players[round_]
        level = (1, 2, 10)[round_] if quiet else rng.choice((1, 2, 5, 10, 20, 40))
        if quiet:
            mem.wf32(caster + 0xDC, 1.0)
        rig.vskill(skill, 1, (caster,))
        spell = rig.vskill(skill, 2, (level, caster, pos, 0))['ret'] & M32
        note_stores(rig, 65, 'cast')
        if not spell:
            clear_handles(rig)
            continue
        world.live.add(spell)
        rig.do('SpellGiantGrowth_getOwnerField0dc', 'giantgrowth_owner_scale', (spell,), ret='f')
        if not quiet:
            mem.w32(spell + 0x20, rng.choice((0, 29, 31, 33, 60)))      # a short hold
        runs = 0
        for tick in range(1400 if quiet else 200):
            next_frame(mem, rng)
            if not quiet:
                if rng.random() < 0.004 and mem.u32(spell + 0xF8):
                    rig.do('handle_clear', 'handle_clear', (spell + 0xF8,))     # the owner is deleted
                if rng.random() < 0.01:                 # something else set the owner's scale
                    mem.wf32(caster + 0xDC, rng.choice((1.0, 1.21, 0.4, mem.f32(spell + 0x1C))))
            runs += 1
            result = rig.do('SpellGiantGrowth_run', 'giantgrowth_run', (spell, pos, 0))
            note_stores(rig, 65, 'run', own=(spell,))
            if ended(result, spell):
                if quiet:
                    TIMERS.setdefault('giantgrowth: level -> runs until the spell ends itself (scale 1.0 at the cast)',
                                      set()).add('%d -> %d' % (level, runs))
                break
        rig.do('handle_clear', 'handle_clear', (spell + 0xF8,))
        world.live.discard(spell)
        clear_handles(rig)
    del world.on_SpellGiantGrowth_typeinfo
    del world.on_model_getSamplePoint
    world.sample_counts = (0, 1, 3, 7, 7, 12)
    rig.report('giantgrowth', 'id 65; player casters (a monster is refused)')


SECTIONS.append(('giantgrowth', section_giantgrowth))


def section_planarwind(rig):
    """Skill 66: cast (player and monster) with its one target query, and the front run
    to its end: the targets it passes struck in list order (the PvP roll, the burn roll,
    the hit particles with and without a model), targets deleted before it reaches them,
    the stream particles, the terrain, the 54th run."""
    rig.section = 'planarwind'
    mem, world, rng = rig.emu.mem, rig.world, rig.rng
    pos = world.scratch
    skill = skill_obj(mem, 66)
    world.sample_counts = (1, 3, 7, 7, 12)
    world.on_Creature_v16 = lambda args, view, rng_: Res(rng_.choice((world.model, world.model, world.model, 0)))
    for round_ in range(5 if OPTIONS['quick'] else 36):
        world.place(rng)
        quiet = round_ < 2                              # two fronts over flat ground: the run count
        caster = rng.choice(world.players * 2 + world.monsters)
        mem.w32(SB.G_PVP_MODE_A, rng.choice((0, 0, 1)))
        put_vec(mem, pos, (mem.f32(caster + 0x10), mem.f32(caster + 0x14), mem.f32(caster + 0x18)))
        rig.vskill(skill, 1, (caster,))
        level = (1, 10)[round_] if quiet else rng.choice((1, 2, 4, 5, 6, 9, 10, 11, 20, 40))
        spell = rig.vskill(skill, 2, (level, caster, pos, rng.randrange(0x10000)))['ret'] & M32
        note_stores(rig, 66, 'cast')
        if not spell:
            clear_handles(rig)
            continue
        world.live.add(spell)
        world.ground_up = 0.0 if quiet else 0.02
        if not quiet and mem.u32(spell + 0x5C) > 80 and rng.random() < 0.8:
            mem.w32(spell + 0x5C, rng.choice((0, 5, 39)))               # fewer stream particles: time
        runs = 0
        for tick in range(60):
            next_frame(mem, rng)
            if not quiet and rng.random() < 0.05:       # a target is deleted before the front reaches it
                rig.do('handle_clear', 'handle_clear', (rng.choice(world.objects),))
            runs += 1
            if ended(rig.do('SpellPlanarWind_run', 'planarwind_run', (spell, pos, 0)), spell):
                if quiet:
                    TIMERS.setdefault('planarwind: runs until the spell ends itself over flat ground', set()).add(runs)
                break
        rig.do('handle_clear', 'handle_clear', (spell + 0x6C,))
        world.live.discard(spell)
        clear_handles(rig)
    mem.w32(SB.G_PVP_MODE_A, 0)
    del world.on_Creature_v16
    world.sample_counts, world.ground_up = (0, 1, 3, 7, 7, 12), 0.4
    rig.report('planarwind', 'id 66; player and monster casters')


SECTIONS.append(('planarwind', section_planarwind))


def main(argv):
    args = list(argv)
    elf = None
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
        elif a == '--trace-first':
            OPTIONS['trace_first'] = True
        elif a == '--fpu':
            OPTIONS['fpu'] = args.pop(0)
        else:
            elf = a
    if elf is None:
        elf = os.path.join(ROOT, 'SLUS_209.73')
    if not os.path.exists(elf):
        print('difftest_skills_b: %s not found - nothing to compare with (this is not a failure)' % elf)
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != DC.EXPECTED_SHA256:
        print('difftest_skills_b: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    DC.OPTIONS['verbose'] = OPTIONS['verbose']
    C.set_fpu(OPTIONS['fpu'])
    started = time.time()
    rig = Rig(elf, OPTIONS['seed'])
    for name, function in SECTIONS:
        if OPTIONS['filter'] and OPTIONS['filter'].lower() not in name.lower():
            continue
        function(rig)
    if rig.unknown:
        DC.report('unknown call targets', len(rig.unknown), len(rig.unknown),
                  'calls to addresses that are neither real nor known stubs',
                  ['%x x%d' % (a, n) for a, n in sorted(rig.unknown.items())])
    print()
    print('calls compared per original function / with any mismatch / shared-seed draws')
    for name in sorted(rig.stats):
        print('  %-36s %7d / %d / %d' % ((name,) + tuple(rig.stats[name])))
    print('coverage of the original as executed here (basic blocks, instructions):')
    tb = tbt = ti = tit = 0
    blocks = {}
    for name, (start, end) in sorted(SB.FUNCTIONS.items(), key=lambda kv: kv[1]):
        leaders, _sites = DC.analyse(rig.emu.mem, start, end)
        inside = {pc for pc in rig.cov if start <= pc < end}
        b, bt, i, it = len(leaders & inside), len(leaders), len(inside), (end - start) // 4
        blocks[name] = (b, bt)
        if not inside and OPTIONS['filter']:
            continue
        tb, tbt, ti, tit = tb + b, tbt + bt, ti + i, tit + it
        print('  %-36s blocks %4d of %4d (%5.1f%%)  instructions %4d of %4d (%5.1f%%)'
              % (name, b, bt, 100.0 * b / bt, i, it, 100.0 * i / it))
        if OPTIONS['verbose'] and b != bt:
            print('      never entered: %s' % ' '.join('%06x' % a for a in sorted(leaders - inside)))
    if tbt:
        print('  %-36s blocks %4d of %4d (%5.1f%%)  instructions %4d of %4d (%5.1f%%)'
              % ('all', tb, tbt, 100.0 * tb / tbt, ti, tit, 100.0 * ti / tit))
    print('per skill: functions of its own executed / basic blocks covered of total / calls compared / with a mismatch')
    for sid in SB.SKILL_IDS:
        names = SB.SKILLS[sid]['functions']
        ran = [n for n in names if blocks[n][0]]
        if OPTIONS['filter'] and not ran:
            continue
        print('  %d %-18s %2d of %2d functions  blocks %4d of %4d  calls %6d  mismatches %d'
              % (sid, SB.SKILLS[sid]['name'], len(ran), len(names), sum(blocks[n][0] for n in names),
                 sum(blocks[n][1] for n in names), sum(rig.stats.get(n, [0])[0] for n in names),
                 sum(rig.stats.get(n, [0, 0])[1] for n in names)))
    if TIMERS:
        print('frame counts settled by execution (fpu model %s):' % OPTIONS['fpu'])
        for what in sorted(TIMERS):
            print('  %s: %s' % (what, ', '.join(str(v) for v in sorted(TIMERS[what], key=str))))
    if COPY_ROWS:
        print('stores outside the stack, the new objects, list nodes and the shared seed (pc -> where), per skill and call:')
        for sid in sorted(COPY_ROWS):
            for what, row in sorted(COPY_ROWS[sid].items()):
                text = ', '.join('%06x -> %s' % entry for entry in row['all'][:8]) or 'none'
                print('  %d %-14s %-22s %s%s' % (sid, SB.SKILLS[sid]['name'], what, text,
                                               '  (calls without any: yes)' if None in row['first'] and row['all'] else ''))
    print('%d calls compared in %.0f s' % (sum(row[0] for row in rig.stats.values()), time.time() - started))
    return 0 if all(ok for _name, ok in DC.RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
