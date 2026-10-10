#!/usr/bin/env python3
"""difftest_arena_monsters.py - compare tools/ref_arena_monsters.py with the game's own code
for the monsters of the Drundar arena (Horsemen, Skelight, Zek) and the two skill casts
their run functions reach.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_arena_monsters.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                           [--ticks N] [-k TEXT] [-v] [--fpu MODEL]
                                           [--trace-first]

    --quick       a tenth of the ticks
    --seed N      seed of the random runs (default 4177); a seed repeats exactly
    --ticks N     ticks per run (default 1500; there are 14 runs)
    -k TEXT       only the runs whose name contains TEXT
    -v            print the first mismatches of every failing property, and the blocks
                  never entered
    --fpu MODEL   ps2 (default), ps2g1, chop or nearest: the adder model of BOTH sides
    --trace-first stop at the first mismatching call and print both sides

What is compared
    The ORIGINAL constructors, run functions and set-state functions of the three classes
    (and the other functions of ref_arena_monsters.MODELLED) are executed by
    tools/ee_emu.py - an instruction interpreter, not a console - on an object the
    original constructor itself built.  The creature base class underneath runs for real
    too (everything in ref_creature.MODELLED), so one "run" call of this test is a whole
    monster tick: pending damage, Creature_run, activity, animation step, target pick,
    the class's switch, its set-state, and on a death the loot / on-death call-outs.
    Every such call is run through the model first, on a copy-on-write view of the same
    memory, and these must be equal:
      calls    the sequence of calls to everything outside the two models, with arguments
               (stack-passed arguments included where a callee takes them)
      writes   the set of bytes stored outside the stack, and their final values
      seed     the shared seed 0x404464, and that it advanced exactly as many times as
               the model says it drew
      result   the value returned
    Floats are compared as 32-bit patterns under the interpreter's floating-point model.

What runs for real and what is a stub
    Real: ref_arena_monsters.MODELLED, ref_creature.MODELLED, the three angle functions
    and the C library (string compares, atan2f, the soft-double routines).  Everything
    else is a recording stub answered by a seeded script (class World): the hit helpers,
    creature_canSeeObj, creature_findEnemyInCone, the animation functions, the weapon
    holder, object construction, Creature_setStats, loot, effects, sound.  The objects
    carry the game's own virtual tables; a slot whose function is not real is a named
    stub at that function's address, and a call to an address that is neither real nor a
    known stub is reported as a failure.

Scenarios (the run names)
    knight0..knight3   the four Horsemen variants on foot.  Targets come and go through
                       the real target pick, damage arrives through slot 2, the knight
                       dies in whatever state it is in and is constructed again; the
                       driver also asks for every state number, valid or not.
    rider              a mounted Horsemen (another level's object; same functions).
    skelight           the summoned skeleton, built by its constructor.
    zek                Rallos Zek.
    Each of them on machine A and machine B (see below); knight2 and knight3 run with
    the real cast functions of skills 87 and 11 behind the skill tables part of the time.

Per-machine inputs, set both ways (machine A / machine B of the run name)
    exactly those of tools/difftest_creature.py (activity by the camera, the local alive
    list, a status counter decremented by drawing, the decal option), plus the
    presentation generator 0x404460, which starts from a different seed on B.
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
import difftest_creature as DC                  # noqa: E402
from difftest_creature import Res, f32, fl, rd, M32, is_stack      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = DC.OPTIONS
OPTIONS.update({'seed': 4177, 'ticks': 1500})

# function bodies for the coverage count: name -> (start, end)
BODIES = {
    'Horsemen_ctor': (0x271C70, 0x2721F8), 'Horsemen_run': (0x27236C, 0x272F4C),
    'Horsemen_setState': (0x272F4C, 0x2735DC),
    'Skelight_ctor': (0x2A8770, 0x2A8A64), 'Skelight_run': (0x2A8B84, 0x2A8FDC),
    'Skelight_setState': (0x2A91B8, 0x2A946C), 'Skelight_shatter': (0x2A946C, 0x2A9478),
    'Zek_ctor': (0x2C1F94, 0x2C2378), 'Zek_run': (0x2C2440, 0x2C34E4),
    'Zek_takeDamage': (0x2C34E4, 0x2C382C), 'Zek_setState': (0x2C382C, 0x2C3C54),
    'Zek_slot35': (0x2C3C54, 0x2C3C68),
    'Creature_ctor': (0x109D68, 0x10A230), 'creature_setDefEntryParams': (0x118378, 0x1183D0),
    'Creature_turnToTarget': (0x1187E0, 0x118840), 'Creature_canSeeTargetIn': (0x118D40, 0x118D8C),
    'Creature_isTargetCharging': (0x118F90, 0x119038), 'Creature_countAlliesNearTarget': (0x119258, 0x1192A8),
    'Creature_isBlockedByTarget': (0x118F08, 0x118F34), 'Creature_canSeeTarget': (0x10E658, 0x10E71C),
    'Creature_onDeath': (0x10BEB8, 0x10BFC8), 'Creature_default_slot16': (0x3C2738, 0x3C2744),
    'Creature_default_slot34': (0x3C2708, 0x3C271C),
    'Creature_isNotRooted/isAttackReady/isNotStunned': (0x1195E0, 0x119614),
    'SkillSummonSkeleton_canUse': (0x2E2368, 0x2E23CC), 'SkillSummonSkeleton_cast': (0x2E18A4, 0x2E227C),
    'SpellSummonSkeleton_ctor': (0x2E16EC, 0x2E177C), 'SpellSummonSkeleton_run': (0x2E177C, 0x2E17D8),
    'SkillTagarsInsects_cast': (0x30C708, 0x30C7D0), 'SpellTagarsInsects_ctor': (0x30C95C, 0x30CAA4),
}
CLASS_FUNCTIONS = ('Horsemen_ctor', 'Horsemen_run', 'Horsemen_setState', 'Skelight_ctor', 'Skelight_run',
                   'Skelight_setState', 'Skelight_shatter', 'Zek_ctor', 'Zek_run', 'Zek_takeDamage', 'Zek_setState',
                   'Zek_slot35')

REAL = set(RC.MODELLED.values()) | set(AM.MODELLED.values()) | set(DC.REAL_OTHER)
CREATURE_TABLES = (AM.VT_CREATURE, AM.VT_HORSEMEN, AM.VT_SKELIGHT, AM.VT_ZEK)
HOLDER_TABLES = (AM.VT_WEAPON1, AM.VT_WEAPONSHIELD)
HOLDER_SLOTS = (1, 2, 4, 6, 11, 15, 17, 21, 22)
SKILL_STATICS = {'disease': 0x6E1610, 'firestorm': 0x6E1748, 'summon': 0x6E18E8, 'tagar': 0x6E37C8,
                 'groundpound': 0x6E23E0}
LEVEL_NAMES = (b'drunare', b'drunare', b'drunare', b'blomedal', b'BloMedal', b'drunarm', b'DRUNARM')
ANIM_FLAGS = (0x08, 0x08, 0x08, 0x00, 0x00, 0x10, 0x18, 0x80, 0x80, 0x88, 0x90, 0x98)
EVENTS = (0, 0, 0, 0, 1, 1, 1, 2, 2, 3, 0x80, 0x81, 0x82)

# entry points: key -> (address, argument kinds, result kind, model method); kinds as in
# tools/difftest_creature.py (c the creature under test, i integer, v vector by pointer,
# f float pattern in f12..)
ENTRIES = {
    'Horsemen_ctor': (0x271C70, 'civiiii', 'n', 'horsemen_ctor'),
    'Horsemen_run': (0x27236C, 'c', 'n', 'horsemen_run'),
    'Horsemen_setState': (0x272F4C, 'ci', 'n', 'horsemen_set_state'),
    'Skelight_ctor': (0x2A8770, 'cviii', 'n', 'skelight_ctor'),
    'Skelight_run': (0x2A8B84, 'c', 'n', 'skelight_run'),
    'Skelight_setState': (0x2A91B8, 'ci', 'n', 'skelight_set_state'),
    'Zek_ctor': (0x2C1F94, 'civii', 'n', 'zek_ctor'),
    'Zek_run': (0x2C2440, 'c', 'n', 'zek_run'),
    'Zek_setState': (0x2C382C, 'ci', 'n', 'zek_set_state'),
    'Zek_takeDamage': (0x2C34E4, 'ciif', 'n', 'zek_take_damage'),
    'Zek_slot35': (0x2C3C54, 'c', 'i', 'zek_slot35'),
    'Creature_takeDamage': (0x116638, 'ciif', 'n', 'take_damage'),
    'Creature_slot7': (0x11A260, 'ci', 'n', 'slot7_path_done'),
    'Creature_canSeeTargetIn': (0x118D40, 'ciiifff', 'i', 'can_see_target_in'),
    'Creature_turnToTarget': (0x1187E0, 'c', 'i', 'turn_to_target'),
    'Creature_isTargetCharging': (0x118F90, 'c', 'i', 'is_target_charging'),
    'Creature_countAlliesNearTarget': (0x119258, 'cf', 'i', 'count_allies_near_target'),
    'Creature_isBlockedByTarget': (0x118F08, 'c', 'i', 'is_blocked_by_target'),
    'Creature_canSeeTarget': (0x10E658, 'ci', 'i', 'slot25_can_see_target'),
    'Creature_onDeath': (0x10BEB8, 'ci', 'n', 'slot28_on_death'),
    'Creature_default_slot16': (0x3C2738, 'c', 'i', 'slot16_model'),
    'Creature_default_slot34': (0x3C2708, 'ci', 'n', 'slot34_set_home_range'),
    'Creature_isNotRooted': (0x1195E0, 'c', 'i', 'is_not_rooted'),
    'Creature_isAttackReady': (0x1195F0, 'c', 'i', 'is_attack_ready'),
    'Creature_isNotStunned': (0x119608, 'c', 'i', 'is_not_stunned'),
    'SkillSummonSkeleton_canUse': (0x2E2368, 'ii', 'i', 'summon_can_use'),
    'SkillSummonSkeleton_cast': (0x2E18A4, 'iiivi', 'i', 'summon_cast'),
    'SpellSummonSkeleton_run': (0x2E177C, 'ivi', 'n', 'summon_spell_run'),
    'SkillTagarsInsects_cast': (0x30C708, 'iiivi', 'i', 'tagar_cast'),
}


class RealSet:
    def __contains__(self, target):
        return target in REAL or DC.LIB_LO <= target < DC.LIB_HI


# ---------------------------------------------------------------------------------------
# The scripted world
# ---------------------------------------------------------------------------------------
class World(DC.World):
    """difftest_creature's world (one creature, six other objects, four players) with what
    the arena classes need on top: class definitions with animation entries, the game's
    own virtual tables, skill objects, a skeleton to kill, a mount to ride."""

    def __init__(self, emu, rng, kind, machine, net):
        self.akind = kind
        self.ready = False
        self.see_bias = 0.5                     # how often the stubbed sight tests say yes; the driver moves it
        self.addr_name = {}                     # function address -> stub name (virtual slots)
        DC.World.__init__(self, emu, rng, 'monster', 0, machine, net)

    def build(self, rng):
        DC.World.build(self, rng)
        emu, mem = self.emu, self.mem
        # class definitions: entry k keeps its resolved pointer at +8k+4
        self.anim_entries = {}
        for d in (AM.DEF_HORSEMEN, AM.DEF_SKELIGHT, AM.DEF_ZEK):
            mem.w32(d + 0xC, self.model)
            mem.w32(d + 0x14, 0x00C00080)
            for k in range(3, 0x1C):
                rec = emu.alloc(0x40)
                mem.w32(d + 8 * k + 4, rec)
                self.anim_entries[rec] = (d, k)
        # the game's own tables: a function that is not real becomes a named stub
        for table in CREATURE_TABLES:
            for slot in range(1, 40):
                fn = mem.u32(table + 8 * slot + 4)
                if fn not in REAL:
                    self.addr_name.setdefault(fn, 'Creature.v%d' % slot)
        for table in HOLDER_TABLES:
            for slot in HOLDER_SLOTS:
                fn = mem.u32(table + 8 * slot + 4)
                assert self.addr_name.setdefault(fn, 'Holder.v%d' % slot) == 'Holder.v%d' % slot
        for table, slots in ((AM.VT_SPELL_SUMMON, (1,)), (AM.VT_SPELL_TAGAR, (1,))):
            for slot in slots:
                self.addr_name.setdefault(mem.u32(table + 8 * slot + 4), 'Spell.v%d' % slot)
        # skill objects: the static ones the run functions reach through pointers
        self.skill_tables = {}
        for name, real in (('stub', {}), ('summon', {1: 0x2E2368, 2: 0x2E18A4}), ('tagar', {2: 0x30C708})):
            table = emu.alloc(8 * 20)
            for slot in (1, 2, 11, 12, 14):
                mem.w32(table + 8 * slot + 4, real.get(slot) or self.stub_for('Skill.v%d' % slot))
            self.skill_tables[name] = table
        for name, obj in SKILL_STATICS.items():
            mem.w32(obj + 0x60, self.skill_tables['stub'])
        # a skeleton for the fourth knight to kill, a mount, pool blocks
        self.pet = emu.alloc(0x600)
        self.blocks = [emu.alloc(0x600) for _ in range(3)]
        self.mount = self.blocks[0]
        self.pool.update({0x3D8: [self.blocks[0]], 0x468: self.blocks[1:], 0x1C: [emu.alloc(0x20) for _ in range(2)],
                          0x94: [emu.alloc(0xA0)], 0x9C: [emu.alloc(0xA0)], 0xBC: [emu.alloc(0xC0)]})
        self.pool_size = {}
        for size, blocks in self.pool.items():
            for b in blocks:
                self.pool_size[b] = size
        for obj in [self.pet] + self.blocks:
            node = emu.alloc(0x20)
            mem.w32(node + 0xC, obj)
            self.nodes[obj] = node
        self.strings['type'] = emu.alloc(16)
        mem.write(self.strings['type'], b'UndeadKnight4\0')
        self.props = emu.alloc(0x20)
        self.descriptor = emu.alloc(0x40)
        mem.w32(AM.G_COSMETIC_SEED, 0x1234567 if self.machine else 0x7654321)
        self.set_level(b'drunare')
        self.ready = True
        self.clear_creature()
        self.place(rng)

    def set_level(self, name):
        self.mem.write(AM.G_LEVEL_NAME, name + b'\0')

    def clear_creature(self):
        """What pool_new hands a constructor: a zero-filled block."""
        for off in range(0, 0x600, 4):
            self.mem.w32(self.C + off, 0)

    def init_creature(self, rng):
        if not self.ready:
            DC.World.init_creature(self, rng)

    def place(self, rng):
        DC.World.place(self, rng)
        if not self.ready:
            return
        mem, c = self.mem, self.C
        for obj in self.others + self.players:                 # a velocity, for "is the target charging"
            mem.wf32(obj + 0x308, rng.choice((0.0, 0.0, 30.0, 99.0, 150.0, -200.0)))
            mem.wf32(obj + 0x30C, rng.choice((0.0, 0.0, 80.0, -120.0)))
        for slot, obj in enumerate(self.players):
            mem.w32(obj + 0x3C8, rng.choice((slot, slot, slot, 4, 7)))
        pet = self.pet                                          # a minimal Skelight
        for off in range(0, 0x600, 4):
            mem.w32(pet + off, 0)
        mem.w32(pet + 0xC, rng.choice((0x20, 0x20, 0x20, 0x28, 0x0, 0x22)))
        for i in range(3):
            mem.w32(pet + 0x10 + 4 * i, mem.u32(c + 0x10 + 4 * i))
        mem.w32(pet + 0x24, AM.DEF_SKELIGHT)
        mem.w32(pet + 0x48, AM.VT_SKELIGHT)
        mem.w32(pet + 0x44, rng.getrandbits(32))
        mem.w16(pet + 0x232, rng.choice((0, 3, 6, 0x17, 0x14, 0x12)))
        mem.w32(pet + 0x234, rng.choice((0, self.nodes[self.players[0]])))
        for off in (0x314, 0x318, 0x31C):
            mem.w16(pet + off, rng.choice((0, 0, 0, 25)))
        mem.w32(pet + 0x50, pet + 0x3C8)
        mem.w32(pet + 0x3C8, AM.VT_WEAPON1)
        mem.w32(self.mount + 0x234, rng.choice([0, 0] + [self.nodes[o] for o in self.others[:3] + self.players[:2]]))

    # ---- answers ------------------------------------------------------------------------
    def on_pool_new(self, args, view, rng):
        blocks = self.pool.get(args[0])
        if blocks is None or rng.random() < 0.08:
            return Res(0)
        block = rng.choice(blocks)
        for off in range(0, (self.pool_size[block] + 3) & ~3, 4):   # the pool zero-fills
            view.poke(block + off, 4, 0)
        return Res(block)

    def on_GameObject_ctor(self, args, view, rng):
        obj, pos, class_def, props = args
        for i in range(3):
            view.poke(obj + 0x10 + 4 * i, 4, pos[i])
        view.poke(obj + 0xC, 4, rng.choice((0, 0, 0, 0x10000)))
        view.poke(obj + 0x20, 4, f32(rng.choice((72.0, 84.0))))
        view.poke(obj + 0x24, 4, class_def)
        view.poke(obj + 0x2C, 4, props)
        view.poke(obj + 0x44, 4, rng.getrandbits(32))
        return Res()

    def on_Creature_setStats(self, args, view, rng):
        c = args[0]
        hp = f32(rng.choice((40.0, 300.0, 300.0, 900.0)))
        view.poke(c + 0x228, 4, hp)
        view.poke(c + 0x22C, 4, hp)
        view.poke(c + 0xD0, 2, rng.choice((7, 30, 31, 101, 0xFFFB)))
        view.poke(c + 0xD2, 2, rng.choice((9, 45, 46, 150, 0xFFF9)))
        view.poke(c + 0xD4, 2, rng.choice((50, 200)))
        view.poke(c + 0xD8, 4, f32(rng.choice((40.0, 250.0, 3000.0))))
        return Res()

    def on_balance_lookup(self, args, view, rng):
        found = 1 if rng.random() < 0.6 else 0
        return Res(found, outs=[f32(rng.choice((1.0, 1.5, 0.8))) for _ in range(5)])

    def on_obj_getPropInt(self, args, view, rng):
        return Res(rng.choice((0, 0, 0, 0, 0, 0, 0, 1, 250, 3000, 0xFFFFFFF6)))

    def on_model_buildHideMask(self, args, view, rng):
        return Res(rng.getrandbits(64))

    def on_model_getSamplePointCount(self, args, view, rng):
        return Res(rng.choice((0, 0, 0, 1, 3, 7, 7, 0xFFFFFFFD)))

    def on_model_getSamplePoint(self, args, view, rng):
        pos = args[2]
        point = tuple(f32(fl(pos[i]) + rng.uniform(-30, 30)) for i in range(3))
        return Res(outs=[point, (f32(rng.uniform(-1, 1)), 0, f32(1.0))])

    def on_world_findObjectByName(self, args, view, rng):
        return Res(rng.choice((0, 0, self.pet, self.pet, self.pet, self.others[0], self.players[1])))

    def on_creature_canSeeObj(self, args, view, rng):
        return Res(rng.choice((1, 1, 0x100)) if rng.random() < self.see_bias else 0)

    def on_creature_findEnemyInCone(self, args, view, rng):
        return Res(rng.choice(self.others[:3] + self.players[:2]) if rng.random() < self.see_bias else 0)

    def on_creature_countAlliesNear(self, args, view, rng):
        return Res(rng.choice((0, 0, 0, 1, 3, 0xFFFFFFFF)))

    def on_creature_isBlockedBy(self, args, view, rng):
        return Res(rng.choice((0, 1)))

    def on_Creature_hitTargetInArc(self, args, view, rng):
        return Res(rng.choice((0, 1)))

    on_Creature_hitAllEnemiesInArc = on_Creature_hitTargetInArc

    def on_terrain_height(self, args, view, rng):
        return Res(f=f32(fl(args[1][2]) + rng.choice((0.0, 0.0, 0.0, 0.0, 0.0, 3.0, -8.0, 2.5, 11.0, 11.5, -13.0, -13.5,
                                                      23.0, 24.0, -24.0, 26.0, -30.0, 60.0))))

    def on_Holder_v15(self, args, view, rng):
        return Res(rng.choice((4, 4, 0, 0x15, 0x1B, 0x23)))

    def on_Holder_v17(self, args, view, rng):
        return Res(rng.choice((0, self.descriptor, self.descriptor)))

    def on_Skill_v1(self, args, view, rng):
        return Res(rng.choice((0, 0, 1)))

    def on_Skill_v2(self, args, view, rng):
        return Res(rng.choice((0, self.spells[0], self.spells[1])))

    def on_Skill_v12(self, args, view, rng):
        return Res(rng.choice((0, 3, 10, 40, 100, 0xFFFFFFFF)))

    def on_Skill_v14(self, args, view, rng):
        return Res(args[1] if rng.random() < 0.7 else 5)

    def on_Creature_v16(self, args, view, rng):
        return Res(self.model)

    def on_Creature_v37(self, args, view, rng):
        return Res(rd(view, args[0] + 0x310, 1, True) & M32)

    def on_Nightmare_ctor(self, args, view, rng):
        block, _name, pos, facing, _data = args
        for i in range(3):
            view.poke(block + 0x10 + 4 * i, 4, pos[i])
        view.poke(block + 0x38, 2, facing & 0xFFFF)
        view.poke(block + 0xC, 4, 0x20)
        view.poke(block + 0x48, 4, self.vt_base)
        return Res()

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
class Rig(DC.Rig):
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
            assert addr not in REAL, (hex(addr), name)
            assert self.names.setdefault(addr, name) == name, (hex(addr), name, self.names[addr])
            emu.stub(addr, function=self.make_stub(name, ext), name=name)

        for name, ext in AM.EXTERNALS.items():
            if ext.addr:
                add(ext.addr, name, ext)
            elif name in self.world.stub_addr:
                add(self.world.stub_addr[name], name, ext)
        for addr, name in list(self.world.stub_name.items()) + list(self.world.addr_name.items()):
            if addr not in self.names:
                add(addr, name, AM.EXTERNALS.get(name) or RC.Ext(0, 'p', 0, 'n'))
        self.partial, self.partial_ops = [], {}
        for start, end in list(DC.BODIES.values()) + list(BODIES.values()):
            for pc in range(start, end, 4):
                w = emu.mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))

    # ---- interpreter side ---------------------------------------------------------------
    def decode(self, name, ext, emu):
        """As difftest_creature's, plus the kind 'S' (a text libc_sprintf made in this call,
        else the address as it is) and the stack-passed arguments of the two callees that
        take them (one 32-bit word per 8-byte slot from the stack pointer)."""
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
            if ext.ret == 'q':
                return res.ret & RC.M64                 # a 64-bit result
            return ee_emu.s32(res.ret)                  # a 32-bit result, sign-extended
        return stub

    # ---- model side -----------------------------------------------------------------------
    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                ret = res.ret & (RC.M64 if AM.EXTERNALS[name].ret == 'q' else M32)
                return AM.shape_result(name, args, ret, res.f & M32, res.outs)
            return answer

    # ---- one call, both sides ---------------------------------------------------------------
    def compare(self, key, args, call_seed, trace=None):
        addr, kinds, ret_kind, method = ENTRIES[key]
        emu, world = self.emu, self.world
        mem = emu.mem
        seed_before = mem.u32(RC.G_RAND_SEED)
        mview = DC.ModelView(mem)
        model = AM.Model(mview, Rig.Callbacks(self, mview, random.Random(call_seed)))
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
    for name, base, size in (('creature', world.C, 0x600), ('pet', world.pet, 0x600), ('block0', world.blocks[0], 0x600),
                             ('block1', world.blocks[1], 0x600), ('block2', world.blocks[2], 0x600)):
        if base <= addr < base + size:
            return '%s+%x' % (name, addr - base)
    if addr in range(AM.DEF_HORSEMEN, AM.DEF_HORSEMEN + 0x100):
        return 'def+%x' % (addr - AM.DEF_HORSEMEN)
    for rec, (d, k) in world.anim_entries.items():
        if rec <= addr < rec + 0x40:
            return 'animentry%x+%x' % (k, addr - rec)
    return DC.where(world, addr)


class Coverage(DC.Coverage):
    def __init__(self, mem):
        self.parts = {name: (start, end) + DC.analyse(mem, start, end) for name, (start, end) in BODIES.items()}
        self.pcs = set()


# ---------------------------------------------------------------------------------------
# The driver
# ---------------------------------------------------------------------------------------
class Driver(DC.Driver):
    """difftest_creature's driver (timers, counters, flags, activity, the per-machine
    inputs) plus what the arena classes look at."""

    def __init__(self, rig):
        DC.Driver.__init__(self, rig)
        self.need_ctor = True
        self.real_skills = False

    def respawn(self):
        self.dead_ticks = 0
        self.need_ctor = True

    def between_arena(self):
        rng, mem, world = self.rng, self.mem, self.world
        c, r = world.C, rng.random
        kind = world.akind
        if r() < 0.02:
            world.set_level(rng.choice(LEVEL_NAMES))
        if r() < 0.03:                                          # enemies in sight and reach: seldom, half, mostly
            world.see_bias = rng.choice((0.06, 0.5, 0.5, 0.94))
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
        if r() < 0.03:                                          # the skill tables: real casts or stubs
            self.real_skills = r() < 0.6
            mem.w32(SKILL_STATICS['summon'] + 0x60, world.skill_tables['summon' if self.real_skills else 'stub'])
            mem.w32(SKILL_STATICS['tagar'] + 0x60, world.skill_tables['tagar' if self.real_skills else 'stub'])
        state = mem.s16(c + 0x232)
        if r() < 0.004:                                         # a state number no set-state would store
            mem.w16(c + 0x232, rng.choice((0x15, 0x18, 0x24, 0x30, 0x7FFF, 0xFFF0, 2, 4)))
        if kind.startswith('knight') or kind == 'rider':
            if state == 5 and r() < 0.2:                        # the 1-in-60 "give up and chase" draw
                while True:
                    seed = rng.getrandbits(32)
                    if (((seed * 0x19660D + 0x3C6EF35F) & M32) >> 16) % 60 == 0:
                        break
                mem.w32(c + 0x44, seed)
            if (state in (6, 7, 8, 10, 0xB) or 0x1F <= state <= 0x22) and r() < 0.1:
                mem.w32(c + 0x50, 0)
            if r() < 0.04:
                mem.w32(c + 0x474, (mem.u32(c + 0x300) + rng.choice((-10, -1, 0, 1, 300))) & M32)
            if r() < 0.01:
                mem.w16(c + 0x472, rng.choice((0, 1, 5, 0xFFFF)))
            if r() < 0.004:
                mem.w8(c + 0x470, rng.choice((0, 1, 2, 3, 4, 0xFF)))
            if r() < 0.01:                                      # a knight without a weapon holder
                mem.w32(c + 0x50, 0)
            elif r() < 0.1 and not mem.u32(c + 0x50):
                mem.w32(c + 0x50, c + 0x3D0)
        if kind == 'rider':
            mount = world.mount
            for i in range(3):
                mem.wf32(mount + 0x10 + 4 * i, mem.f32(c + 0x10 + 4 * i) + rng.choice((0.0, 2.5, -4.0)))
            mem.w16(mount + 0x38, (mem.u16(c + 0x38) + rng.choice((0, 0, 700, -900))) & 0xFFFF)
            if r() < 0.1:
                mem.w32(mount + 0x234, rng.choice([0] + [world.nodes[o] for o in world.others[:3] + world.players[:2]]))
            if r() < 0.02 and not mem.u32(c + 0x3C8):           # back on the mount
                mem.w32(c + 0x3C8, world.nodes[mount])
        if kind == 'zek':
            if r() < 0.04:
                mem.w32(c + 0x478, (mem.u32(c + 0x300) + rng.choice((-700, -181, -180, -179, -1, 0, 1, 300))) & M32)
            if r() < 0.02:
                mem.w32(c + 0x47C, rng.choice((6, 7, 8, 8, 8, 0xC)))
            if r() < 0.01:
                mem.w32(AM.G_ZEK_SPARK_READY, rng.choice((0, 1)))
            if mem.u32(c + 0x464) and r() < 0.3:               # the wave: far away, or its enemy near
                which = rng.choice(('far', 'near', 'none', 'link'))
                if which == 'far':
                    mem.wf32(c + 0x46C, mem.f32(c + 0x10) + rng.choice((790.0, 805.0, -900.0)))
                elif which == 'none':
                    mem.w32(c + 0x460, 0)
                else:
                    node = world.nodes[rng.choice(world.others[:3] + world.players[:2])]
                    mem.w32(c + 0x460, node)
                    if which == 'near':
                        enemy = mem.u32(node + 0xC)
                        mem.wf32(c + 0x46C, mem.f32(enemy + 0x10) + rng.choice((10.0, 30.0, 37.0)))
                        mem.wf32(c + 0x470, mem.f32(enemy + 0x14) + rng.choice((0.0, 20.0)))
            if r() < (0.3 if 6 <= state <= 0xC else 0.01):
                mem.w32(c + 0x50, 0)
            elif r() < 0.1 and not mem.u32(c + 0x50):
                mem.w32(c + 0x50, c + 0x3C8)
        if kind == 'skelight':
            if r() < 0.01:
                mem.w32(c + 0x50, 0)
            elif r() < 0.1 and not mem.u32(c + 0x50):
                mem.w32(c + 0x50, c + 0x3C8)


DEATHS = {}             # kind -> {AI state the creature was in when a tick killed it: count}

HORSEMEN_STATES = list(range(0, 0x24)) + [0x24, 0x30, 0x7FFF, 0xFFFFFFFB, 3, 5, 5, 6, 7, 8, 10, 0xB, 0x17, 0x17,
                                          0x14, 0x12, 0x12, 0x13, 0x10]
SKELIGHT_STATES = list(range(0, 0x18)) + [0x18, 0x40, 0xFFFFFFFF, 3, 5, 6, 6, 0x17, 0x14, 0x12, 0x13, 0x10]
ZEK_STATES = list(range(0, 0x15)) + [0x15, 0x17, 0x99, 0xFFFFFFF0, 3, 5, 5, 6, 7, 8, 9, 10, 0xB, 0xC, 0xD, 0xD, 0xE, 0xE,
                                     0x14, 0x12, 0x13, 0x10]


def run(elf, name, seed, kind, machine, net, ticks, coverage, counts):
    rig = Rig(elf, seed, kind, machine, net)
    driver = Driver(rig)
    world, mem, rng = rig.world, rig.emu.mem, rig.rng
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

    def vector(spread, base=None):
        base = base if base is not None else c + 0x10
        return (f32(mem.f32(base) + rng.uniform(-spread, spread)), f32(mem.f32(base + 4) + rng.uniform(-spread, spread)),
                mem.u32(base + 8))

    if kind == 'skelight':
        run_key, set_key, states, dmg_key = 'Skelight_run', 'Skelight_setState', SKELIGHT_STATES, 'Creature_takeDamage'
    elif kind == 'zek':
        run_key, set_key, states, dmg_key = 'Zek_run', 'Zek_setState', ZEK_STATES, 'Zek_takeDamage'
    else:
        run_key, set_key, states, dmg_key = 'Horsemen_run', 'Horsemen_setState', HORSEMEN_STATES, 'Creature_takeDamage'

    def construct():
        world.clear_creature()
        pos = (f32(2000.0 + rng.uniform(-50, 50)), f32(3000.0 + rng.uniform(-50, 50)), f32(10.0))
        facing = rng.choice((rng.randrange(0x10000), 0xFFFF8000 | rng.randrange(0x8000)))
        type_name = rng.choice((0, world.strings['type'], world.strings['type']))
        if kind == 'skelight':
            do('Skelight_ctor', c, pos, facing, world.props, rng.choice((1, 7, 30, 0xFFFFFFFF)))
        elif kind == 'zek':
            do('Zek_ctor', c, type_name, pos, facing, world.props)
        else:
            variant = 3 if kind == 'rider' and rng.random() < 0.3 else rng.randrange(4) if kind == 'rider' \
                else int(kind[-1])
            do('Horsemen_ctor', c, type_name, pos, facing, world.props, variant, 1 if kind == 'rider' else 0)
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
        driver.between_arena()
        if driver.pending_slot7 is not None:
            do('Creature_slot7', c, driver.pending_slot7)
            driver.pending_slot7 = None
        # damage arrives through the class's slot 2
        if r() < 0.08:
            for _ in range(rng.choice((1, 1, 2))):
                attacker = rng.choice(world.others + world.players + [0])
                flags = 0
                for _k in range(rng.choice((0, 1, 1, 2, 3))):
                    flags |= rng.choice(DC.DAMAGE_FLAGS)
                amount = rng.choice((0.0, 3.0, 20.0, 20.0, 20.0, 60.0, 150.0, 400.0))
                do(dmg_key, c, attacker, flags, f32(amount))
        elif r() < 0.03:
            mem.w32(c + 0x2DC, rng.choice((0x2000, 0x2000, 0x2000 | 0x80000, 0x40000, 0x200000, 0x100000)))
        if r() < 0.04 and mem.s16(c + 0x232) != 0x14:           # a killing blow in a state of the driver's choice
            do(set_key, c, rng.choice(states))
            mem.w8(c + 0x231, 0)
            do(dmg_key, c, rng.choice(world.others + world.players + [0]), rng.choice(DC.DAMAGE_FLAGS), f32(5000.0))
        before = mem.s16(c + 0x232)
        do(run_key, c)
        if before != 0x14 and mem.s16(c + 0x232) == 0x14:
            died_in[before] = died_in.get(before, 0) + 1
        # the rest of the game asks for a state (cutscenes, scripts, other classes); the
        # driver asks for every number, valid or not
        if r() < 0.10:
            do(set_key, c, rng.choice(states))
        # helpers on their own
        if r() < 0.03:
            do('Creature_canSeeTargetIn', c, rng.choice((0, 0x7FFF, 0x18000, 0xFFFF9000)), rng.choice((6000, 0x17FFF)),
               rng.choice((0, 1)), f32(0.0), f32(rng.choice((36.0, 400.0))), f32(0.0))
        if r() < 0.03:
            do('Creature_turnToTarget', c)
        if r() < 0.06:
            do('Creature_isTargetCharging', c)
        if r() < 0.02:
            do('Creature_countAlliesNearTarget', c, f32(36.0))
            do('Creature_isBlockedByTarget', c)
        if r() < 0.03:
            do('Creature_canSeeTarget', c, rng.choice((0, 0, 1, 0x100)))
        if r() < 0.01:
            do('Creature_onDeath', c, rng.choice((0, 0, 1)))
        if r() < 0.02:
            do('Creature_default_slot16', c)
            if r() < 0.3:
                do('Creature_default_slot34', c, rng.choice((500, 2000, 0x1F0FA, 0xFFFFFFFF)))
            do('Creature_isNotRooted', c)
            do('Creature_isAttackReady', c)
            do('Creature_isNotStunned', c)
        if kind == 'zek' and r() < 0.02:
            do('Zek_slot35', c)
        if kind in ('knight3', 'knight2', 'skelight') and r() < 0.05:
            caster = rng.choice([c, c] + world.players)
            do('SkillSummonSkeleton_canUse', SKILL_STATICS['summon'], caster)
            if r() < 0.5:
                mem.w32(SKILL_STATICS['summon'] + 0x60, world.skill_tables['summon'])
                do('SkillSummonSkeleton_cast', SKILL_STATICS['summon'], rng.choice((0, 1, 7, 0xFFFFFFFF)), caster,
                   vector(30, caster + 0x10), rng.choice((rng.randrange(0x10000), 0xFFFF8123)))
            if r() < 0.3:
                spell = world.pool[0x1C][0]
                mem.w32(spell + 0x14, AM.VT_SPELL_SUMMON)
                mem.w32(spell + 0x18, rng.choice((0, 0, world.nodes[world.pet])))
                do('SpellSummonSkeleton_run', spell, vector(5), 0)
        if kind in ('knight2', 'knight3') and r() < 0.04:
            mem.w32(SKILL_STATICS['tagar'] + 0x60, world.skill_tables['tagar'])
            do('SkillTagarsInsects_cast', SKILL_STATICS['tagar'], rng.choice((1, 4, 9)), rng.choice([c] + world.players),
               vector(5), rng.randrange(0x10000))
    if rig.unknown:
        bad['calls'].append('calls to addresses that are neither real nor known stubs: %s'
                            % {hex(a): n for a, n in rig.unknown.items()})
    text = '%s, machine %s, %s' % (kind, 'B' if machine else 'A', 'net game' if net else 'offline')
    count = serial[0]
    DC.report(name + ' calls', len(bad['calls']), count, 'callbacks in order with arguments; ' + text, bad['calls'])
    DC.report(name + ' writes', len(bad['writes']), count, 'bytes stored and their final values', bad['writes'])
    DC.report(name + ' seed', len(bad['seed']), count, 'shared seed and number of draws', bad['seed'])
    DC.report(name + ' result', len(bad['result']), count, 'returned values', bad['result'])
    DC.report(name + ' faults', len(bad['fault']), count,
              'calls that stopped on one side only (%d stopped on both, the same way)' % sum(both.values()),
              bad['fault'])
    return count, draws_by_entry


RUNS = (('knight0', 0, 1), ('knight0', 1, 1), ('knight1', 0, 1), ('knight1', 1, 0), ('knight2', 0, 1), ('knight2', 1, 1),
        ('knight3', 0, 1), ('knight3', 1, 1), ('rider', 0, 0), ('rider', 1, 1), ('skelight', 0, 1), ('skelight', 1, 1),
        ('zek', 0, 1), ('zek', 1, 1))


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
        print('difftest_arena_monsters: %s not found - nothing to compare with (this is not a failure)' % elf)
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != DC.EXPECTED_SHA256:
        print('difftest_arena_monsters: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
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
            tb, tbt, ti, tit = tb + b, tbt + bt, ti + i, tit + it
            print('  %-48s blocks %4d of %4d (%5.1f%%)  instructions %4d of %4d (%5.1f%%)'
                  % (part, b, bt, 100.0 * b / bt, i, it, 100.0 * i / it))
            if OPTIONS['verbose'] and b != bt:
                print('      never entered: %s' % ' '.join('%06x' % a for a in coverage[0].missing(part)))
        print('  %-48s blocks %4d of %4d (%5.1f%%)  instructions %4d of %4d (%5.1f%%)'
              % ('all', tb, tbt, 100.0 * tb / tbt, ti, tit, 100.0 * ti / tit))
    print('AI state the creature was in on the tick that killed it (state: deaths):')
    for kind in sorted(DEATHS):
        print('  %-9s %s' % (kind, ' '.join('%x:%d' % (s16 & 0xFFFF, n) for s16, n in sorted(DEATHS[kind].items()))))
    if DC.FAULTS:
        print('calls in which the original read or wrote unmapped memory, and the model did too: %s'
              % ', '.join('%d at 0x%x' % (n, pc) for pc, n in sorted(DC.FAULTS.items())))
    print('%d calls compared in %.0f s' % (total, time.time() - started))
    return 0 if all(ok for _name, ok in DC.RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
