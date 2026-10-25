#!/usr/bin/env python3
"""difftest_arrow_run.py - compare tools/ref_arrow_run.py with the game's own code: the four
arrows a SkeletonBow releases (MissileWeapon, FireArrowProjectile, ColdArrowProjectile,
ExplodeArrowProjectile), each built with its REAL constructor on the Skeleton's arguments
and then run frame after frame until it ends: flight, the touch, the stick (or not), expiry
and the destructor.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_arrow_run.py [path/to/SLUS_209.73] [--seed N] [--cases N]
                                         [--quick] [-v] [--trace-first]

What is compared
    tools/difftest_skills_b.py's world (the executable's own Skill objects, built by its
    static initialisers 0x16ac74 and 0x1ebca0; a handle-node pool; players, monsters and
    props with stub tables) and its stub machinery.  Every call of a case - the
    constructor, each run, the destructor - runs the original in tools/ee_emu.py with these
    bodies REAL: everything in ref_arrow_run.EXECUTED (the arrow bodies, Projectile_ctor,
    GameObject_ctor with its shared draw, obj_moveAndCollide), ref_skills_b's machinery
    (handle lists, GameObject_rand, the Skill statistic slots) and the C library.  The
    same call goes through ref_arrow_run.Model first on a copy-on-write view of the same
    memory; equal must be the call-outs in order with their arguments, every byte stored
    outside the stack, the shared seed 0x404464 with its draw count, the result.  The
    state then carries over to the next call, so a case is a chain of compared calls on
    the original's own state.

The world of a case (scripted, the same answers on both sides)
    The Skeleton (the owner) stands at a random point; the arrow leaves from the
    release origin (x, y, z + height / 2 + 18) towards a lead point (the target's
    mid-height), with the release's scatter for the MissileWeapon.  The target is the idle
    player (object flags 0x60), a creature, a prop, a container, an ally creature (the
    owner's slot 20 says no), nothing (expiry), a ramp of terrain (ground hit) or a wall
    of terrain; in some cases the owner is destroyed in flight (handle_clear of its back
    list, compared as well).  terrain_height answers from the scene (flat ground, the
    ramp, the wall); world_collectObjectsInBox answers the scene's objects whose extent
    meets the box, in a scripted order.  A control group of player-owned MissileWeapons
    shows the stick and the stuck-follow path the Skeleton's arrows never reach.
"""
import hashlib
import math
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError                 # noqa: E402
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_skills_b as SB                       # noqa: E402
import ref_arrow_run as A                       # noqa: E402
import difftest_creature as DC                  # noqa: E402
import difftest_skills_b as DSB                 # noqa: E402
from difftest_creature import Res, f32, fl, rd, M32, is_stack      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = DSB.OPTIONS
OPTIONS.update({'seed': 20973, 'cases': 600, 'quick': False, 'verbose': False, 'trace_first': False})
STEP, INC = 0x19660D, 0x3C6EF35F
FAR = 60000.0

TARGETS = ('player', 'player', 'player', 'creature', 'creature', 'ramp', 'wall', 'nothing', 'ally', 'prop',
           'container', 'orphan', 'orphan', 'crowd', 'crowd')
ELEMENTS = (0, 0, 0, 1, 2, 6)
SKILL_IDS = {1: 43, 2: 44, 6: 47}

# type-info descriptors (addresses of the executable's own; their names are written by the test)
DESC = {'Creature': 0x908130, 'AutoContainer': 0x9089E0, 'Container': 0x908140, 'Skeleton': 0x908E20,
        'PushPhysicsProp': 0x908560, 'Player': 0x908150}
DESC_NAMES = {'Creature': b'8Creature', 'AutoContainer': b'13AutoContainer', 'Container': b'9Container',
              'Skeleton': b'8Skeleton', 'PushPhysicsProp': b'15PushPhysicsProp', 'Player': b'6Player'}


def lcg_steps(before, after, limit=20000):
    """How many draws of the 0x19660d / 0x3c6ef35f generator lead from before to after
    (None when more than `limit`)."""
    s, n = before & M32, 0
    while s != after & M32:
        s = (s * STEP + INC) & M32
        n += 1
        if n > limit:
            return None
    return n


class RealSet:
    def __init__(self, addresses):
        self.addresses = set(addresses)

    def __contains__(self, target):
        return target in self.addresses or DC.LIB_LO <= target < DC.LIB_HI


# ---------------------------------------------------------------------------------------
# The world
# ---------------------------------------------------------------------------------------
class World(DSB.World):
    """difftest_skills_b's world with a scene: the Skeleton, the target and the terrain
    of one case, and deterministic answers for the arrow's call-outs."""

    def build(self, rng):
        DSB.World.build(self, rng)
        emu, mem = self.emu, self.mem
        mem.w32(self.vt_obj + 4, self.stub_for('Creature.v0'))      # slot 0: the type-info getter
        names = emu.alloc(0x100)
        at = names
        for key, desc in DESC.items():
            mem.write(at, DESC_NAMES[key] + b'\0')
            mem.w32(desc, at)
            at += 0x20
        # the pool's size classes (pool_free's walk; the blocks of this world in classes 0 and 1)
        self.small = self.blocks[:20]
        self.large = self.blocks[20:]
        mem.w32(A.G_POOL_CLASSES + 0x18, self.blocks[0])
        mem.w32(A.G_POOL_CLASSES + 0x28, self.blocks[20])
        mem.w32(A.G_POOL_CLASSES + 0x38, 0x7FF00000)
        self.scene = None
        self.types = {}
        self.boss = {}
        self.models = {}
        self.dodge_rank = 0
        self.enemy = set()
        self.box_rotate = 0
        self.damage_ok = 0.85
        self.water = 0.0

    # ---- the scene ---------------------------------------------------------------------
    def ground(self, x, y):
        """Terrain height at (x, y) for the current scene (Python float)."""
        sc = self.scene
        if sc is None:
            return 0.0
        along = (x - sc['sx']) * sc['ux'] + (y - sc['sy']) * sc['uy']
        z = sc['z0']
        if sc['ramp'] is not None and along > sc['ramp']:
            z += (along - sc['ramp']) * sc['slope']
        if sc['wall'] is not None and along > sc['wall']:
            z += 400.0
        return z

    def on_terrain_height(self, args, view, rng):
        p = args[1]
        ground = f32(self.ground(fl(p[0]), fl(p[1])))
        if isinstance(view, DSB.EmuView) and C.lt(p[2], ground):
            self.under = True                   # the original asked about a point under the ground
        return Res(f=ground)

    def on_water_test(self, args, view, rng):
        return Res(1 if rng.random() < self.water else 0)

    def on_world_collectObjectsInBox(self, args, view, rng):
        lo, hi = [fl(v) for v in args[0]], [fl(v) for v in args[1]]
        found = []
        for obj in self.objects:
            x, y, z = (fl(rd(view, obj + 0x10 + 4 * i)) for i in range(3))
            r, h = fl(rd(view, obj + 0x1C)), fl(rd(view, obj + 0x20))
            if lo[0] - r <= x <= hi[0] + r and lo[1] - r <= y <= hi[1] + r and z <= hi[2] and z + h >= lo[2]:
                found.append(obj)
        if found:
            k = self.box_rotate % len(found)
            found = found[k:] + found[:k]
        return Res(outs=[found[:min(len(found), max(args[2] - 1, 0))]])

    # ---- the answers of the touch ------------------------------------------------------------
    def on_Creature_v20(self, args, view, rng):
        return Res(1 if args[1] in self.enemy else 0)

    def on_Creature_v0(self, args, view, rng):
        # a type-info getter gets no arguments: the answer is the class of the one object of
        # the scene whose type the arrow asks (the prop, or the creature it would stick to)
        return Res(self.type_answer)

    def on_Creature_v16(self, args, view, rng):
        return Res(self.models.get(args[0], self.model))

    def on_Creature_v36(self, args, view, rng):
        return Res(self.boss.get(args[0], 0))

    def on_damage_apply(self, args, view, rng):
        return Res(1 if rng.random() < self.damage_ok else 0)

    def on_obj_updateActive(self, args, view, rng):
        return Res(1)

    def on_player_getSkillRank(self, args, view, rng):
        return Res(self.dodge_rank)

    def on_SkillDodge_getStat0Fraction(self, args, view, rng):
        first = args[0] == view.load(SB.G_SKILL_TABLE + 8, 4)                     # skill 2, else skill 0x53
        if not first and rng.random() < 0.3:
            # aim at the deflection roll's boundary: the roll the next shared draw makes is
            # known (the draw follows this call), so the chance is set to it or to it + 1
            roll = (((rd(view, RC.G_RAND_SEED) * STEP + INC) & M32) >> 16) % 100 + 1
            return Res(f=f32((roll + rng.choice((0, 1))) / 100.0 + 0.0001))
        step = 0.03 if first else 0.04
        return Res(f=f32(step * (args[1] & 0xFF) + (0.02 if args[1] & 1 else 0.0)))

    def on_SkillPenetratingArrows_getStats01Fraction(self, args, view, rng):
        rank = args[1] & 0xFF
        return Res(outs=[f32(0.05 * rank), f32(0.1 * rank)])

    def on_item_getResourceIndex(self, args, view, rng):
        return Res(rng.choice((0, 1, 2, 3)))

    def on_model_getSamplePoint(self, args, view, rng):
        host_pos = args[2]
        point = tuple(f32(fl(host_pos[i]) + rng.uniform(-20, 20) + (40.0 if i == 2 else 0.0)) for i in range(3))
        weight = f32(rng.choice((0.25, 0.5, 0.75, 1.0)))
        matrix = tuple(f32(rng.uniform(-1, 1)) for _ in range(9))
        return Res(outs=[point, weight, matrix])

    def on_model_getSamplePointCount(self, args, view, rng):
        return Res(rng.choice((0, 1, 4, 6, 6, 6)))

    def on_AutoContainer_typeinfo(self, args, view, rng):
        return Res(DESC['AutoContainer'])

    def on_Container_typeinfo(self, args, view, rng):
        return Res(DESC['Container'])

    def on_Skeleton_typeinfo(self, args, view, rng):
        return Res(DESC['Skeleton'])

    def on_PushPhysicsProp_typeinfo(self, args, view, rng):
        return Res(DESC['PushPhysicsProp'])

    def on_sound_playSample(self, args, view, rng):
        return Res(3)


# ---------------------------------------------------------------------------------------
# The rig: difftest_skills_b's, with ref_arrow_run's model, externals and bodies
# ---------------------------------------------------------------------------------------
FUNCTION_ADDR = {name: start for name, (start, _end) in list(SB.FUNCTIONS.items()) + list(A.BODIES.items())}


class Rig(DSB.Rig):
    model_class = A.Model                       # difftest_staticfire.py puts its own model here

    def __init__(self, elf, seed):
        self.rng = random.Random(seed)
        emu = self.emu = EE(elf, fpu_model=OPTIONS['fpu'])
        self.world = World(emu, self.rng, 0, 0)
        real = set(SB.MODELLED.values()) | set(A.EXECUTED.values()) | set(DC.REAL_OTHER)
        real -= set(SB.REAL_LIBRARY.values())
        self.real = emu.follow = RealSet(real)
        self.calls, self.buffers, self.unknown = [], {}, {}
        self.eview = DSB.EmuView(emu)
        self.script_rng = None
        self.names, self.addr_names = {}, {}
        for name, ext in A.EXTERNALS.items():
            if ext.addr and ext.addr not in real:
                self.add_stub(ext.addr, name)
        for addr, name in list(self.world.stub_name.items()):
            self.add_stub(addr, name)
        self.partial, self.partial_ops = [], {}
        ranges = set(SB.FUNCTIONS.values()) | set(A.BODIES.values())
        for start, end in ranges:
            for pc in range(start, end, 4):
                if pc in self.partial_ops:
                    continue
                w = emu.mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))
        self.cov = set()
        self.serial = 0
        self.stats = {}
        self.bad = {}
        self.section = 'arrows'
        self.last = None

    def add_stub(self, addr, name):
        assert self.names.setdefault(addr, name) == name, (hex(addr), name, self.names[addr])
        ext = A.EXTERNALS.get(name) or RC.Ext(0, 'p', 0, 'n')
        self.emu.stub(addr, function=self.make_stub(name, ext), name=name)

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                ext = A.EXTERNALS.get(name)
                if ext is None:
                    return None
                ret = res.ret & (RC.M64 if ext.ret == 'q' else M32)
                return A.shape_result(name, args, ret, res.f & M32, res.outs)
            return answer

    def compare(self, name, method, args, fargs=(), ret='n'):
        """One call of the original `name` (A.BODIES or ref_skills_b.FUNCTIONS) beside the
        model method; integer arguments beyond eight go to the caller's stack area (64-bit
        slots from the stack pointer), as the constructors' callers pass them."""
        addr = FUNCTION_ADDR[name]
        emu, world = self.emu, self.world
        mem = emu.mem
        self.serial += 1
        call_seed = OPTIONS['seed'] * 1000003 + self.serial
        seed_before = mem.u32(RC.G_RAND_SEED)
        mview = DSB.ModelView(mem)
        model = self.model_class(mview, Rig.Callbacks(self, mview, random.Random(call_seed)))
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
        sp = emu.stack_hi - 0x200
        emu.r[29] = sp
        for i, value in enumerate(args[8:]):
            mem.w64(sp + 8 * i, value & M32)
        for j, value in enumerate(fargs):
            emu.f[12 + j] = value & M32
        emu_error = None
        try:
            eret = emu.call(addr, *[ee_emu.s32(a & M32) for a in args[:8]], max_steps=20000000)
        except EmuError as exc:
            emu_error, eret = exc, None
        self.cov.update(emu.trace)
        emu.trace = None
        for c in emu.calls:
            if c.target not in self.real and c.target not in self.names:
                self.unknown[c.target] = self.unknown.get(c.target, 0) + 1
        out = {'fault': None, 'calls': None, 'writes': None, 'seed': None, 'result': None, 'both_fault': None,
               'draws': model.draws, 'model_calls': model.calls, 'emu_calls': self.calls, 'ret': eret, 'mret': mret}
        self.last = out
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
            if not DSB.is_model_stack(a):
                mbytes.update(range(a, a + size))
        diff = []
        for a in sorted(ebytes | mbytes | self.eview.touched | mview.touched):
            if DSB.is_model_stack(a) or is_stack(a):
                continue
            x, y = mem.load(a, 1), mview.load(a, 1)
            if x != y:
                w = a & ~3
                if is_stack(mem.load(w, 4)) and DSB.is_model_stack(mview.load(w, 4)):
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
        return out


# ---------------------------------------------------------------------------------------
# One case: build, run until the end, destroy
# ---------------------------------------------------------------------------------------
def put_vec(mem, addr, values):
    for i, v in enumerate(values):
        mem.w32(addr + 4 * i, v if isinstance(v, int) else f32(v))


def zero(mem, addr, size):
    for off in range(0, size, 4):
        mem.w32(addr + off, 0)


def place(mem, obj, pos, radius=12.0, height=72.0, flags=0x20):
    zero(mem, obj, 0x600)
    put_vec(mem, obj + 0x10, pos)
    mem.wf32(obj + 0x1C, radius)
    mem.wf32(obj + 0x20, height)
    mem.w32(obj + 0xC, flags)


class Tally:
    def __init__(self):
        self.outcomes = {}
        self.cases = 0
        self.calls = 0
        self.mismatches = 0
        self.both = 0
        self.draws = {}          # (element, what) -> [shared, own, cosmetic, cases]
        self.examples = []
        self.stuck_monster = 0
        self.stuck_control = 0


def run_case(rig, rng, tally):
    w, mem = rig.world, rig.emu.mem
    element = rng.choice(ELEMENTS)
    target = rng.choice(TARGETS)
    control = element == 0 and rng.random() < 0.2           # a player-owned MissileWeapon
    if control:
        target = rng.choice(('creature', 'creature', 'creature', 'player', 'ramp'))
    skeleton, victim, other_c = w.monsters[0], w.monsters[1], w.monsters[2]
    player, prop = w.players[0], w.props[0]
    owner = w.players[1] if control else skeleton
    # every world object far away first
    for i, obj in enumerate(w.objects):
        place(mem, obj, (FAR + 300.0 * i, FAR, 0.0), flags=mem.u32(obj + 0xC) & 0x40)
        mem.w32(obj + 0x48, w.vt_obj)
        mem.w32(obj + 0x24, w.class_def)
        mem.wf32(obj + 0xDC, 1.0)
    for slot, obj in enumerate(w.players[:4]):
        mem.w32(obj + 0xC, 0x60)
        mem.w32(obj + 0x3C8, slot)
    sx, sy = 2000.0 + rng.uniform(-300, 300), 3000.0 + rng.uniform(-300, 300)
    z0 = rng.choice((0.0, 10.0, -35.0))
    theta = rng.uniform(0, 2 * math.pi)
    ux, uy = math.cos(theta), math.sin(theta)
    dist = rng.choice((30.0, 45.0, 60.0, 120.0, 200.0, 350.0, 600.0, 900.0, rng.uniform(40, 1200)))
    w.scene = {'sx': sx, 'sy': sy, 'z0': z0, 'ux': ux, 'uy': uy, 'ramp': None, 'slope': 0.0, 'wall': None}
    if target == 'ramp':
        w.scene['ramp'], w.scene['slope'] = rng.uniform(30, 500), rng.choice((0.05, 0.2, 1.0))
    if target == 'wall':
        w.scene['wall'] = rng.uniform(30, 900)
    place(mem, owner, (sx, sy, z0), flags=0x60 if control else 0x20)
    mem.w32(owner + 0x48, w.vt_obj)
    mem.w32(owner + 0x24, w.class_def)
    mem.w16(owner + 0x38, int(theta / (2 * math.pi) * 65536) & 0xFFFF)
    mem.w64(owner + 0xA8, 0)
    if control:
        mem.w32(owner + 0x3C8, 1)
    mem.w32(owner + 0x44, rng.getrandbits(32))
    tx, ty = sx + ux * dist, sy + uy * dist
    who = {'player': player, 'creature': victim, 'ally': other_c, 'prop': prop, 'container': prop,
           'orphan': rng.choice((player, victim)), 'crowd': player}.get(target)
    w.enemy = {player, victim} if not control else {victim, skeleton, other_c}
    if control and target == 'player' and rng.random() < 0.5:
        w.enemy.add(player)                                 # PvP: the owner's slot 20 accepts a player
    w.boss = {victim: rng.choice((0, 0, 0, 4, 10)), other_c: 0, skeleton: 0}
    w.type_answer = DESC['Creature']
    w.dodge_rank = rng.choice((0, 0, 1, 5, 20))
    w.damage_ok = rng.choice((1.0, 1.0, 0.8, 0.0))
    w.water = rng.choice((0.0, 0.0, 0.0, 0.5))
    w.box_rotate = rng.randrange(4)
    if who is not None:
        flags = {player: 0x60, victim: rng.choice((0x20,) * 9 + (0x1000020,)), other_c: 0x20,
                 prop: rng.choice((0, 0, 0x1000000, 0x4000))}[who]
        place(mem, who, (tx + rng.uniform(-6, 6), ty + rng.uniform(-6, 6), z0),
              radius=rng.choice((8.0, 12.0, 16.0, 24.0)), height=rng.choice((40.0, 72.0, 84.0)), flags=flags)
        mem.w32(who + 0x48, w.vt_obj)
        mem.w32(who + 0x24, w.class_def)
        if who == player:
            mem.w32(who + 0x3C8, 0)
        if who in (victim, other_c) and rng.random() < (0.3 if control else 0.15):
            mem.w64(who + 0xA8, 1 << 41)                 # creature flag bit 41 (the stuck-host delete test)
        kind = 'Player' if who == player else 'Creature'
        if who == prop:
            kind = {'container': rng.choice(('AutoContainer', 'Container')), 'prop': 'PushPhysicsProp'}[target]
            if rng.random() < 0.3:
                kind = 'Creature'                        # any other class
        if who == victim and control and rng.random() < 0.15:
            kind = 'Skeleton'
        w.type_answer = DESC[kind]
    if target == 'crowd':                                   # a creature right beside the player
        place(mem, victim, (tx + rng.uniform(-10, 10), ty + rng.uniform(-10, 10), z0), radius=12.0, height=72.0)
        mem.w32(victim + 0x48, w.vt_obj)
        mem.w32(victim + 0x24, w.class_def)
    if target in ('ramp', 'wall', 'nothing'):
        if rng.random() < 0.5:                           # a bystander off the line
            place(mem, victim, (tx - uy * 300.0, ty + ux * 300.0, z0))
            mem.w32(victim + 0x48, w.vt_obj)
    # the release (ref_skeleton_run.skeleton_release): origin, lead point, angle, velocity
    height = mem.u32(owner + 0x20)
    origin = (mem.u32(owner + 0x10), mem.u32(owner + 0x14),
              C.add(C.add(mem.u32(owner + 0x18), C.mul(height, RC.HALF)), 0x41900000))
    lz = C.add(f32(z0), C.mul(f32(72.0), RC.HALF))
    if who is not None:
        lz = C.add(mem.u32(who + 0x18), C.mul(mem.u32(who + 0x20), RC.HALF))
    lead = (f32(tx), f32(ty), lz)
    dx, dy, dz = C.sub(lead[0], origin[0]), C.sub(lead[1], origin[1]), C.sub(lead[2], origin[2])
    angle = C.atan2_16(dy, dx)
    inv = C.rsqrt(RC.ONE, C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz)))
    while True:
        v = [rng.uniform(-1, 1) for _ in range(3)]
        if sum(c * c for c in v) <= 1.0:
            break
    velocity = tuple(C.add(C.mul(C.mul(d, inv), 0x43C80000), C.mul(f32(c), 0x42400000)) for d, c in zip((dx, dy, dz), v))
    pos_arg, vel_arg = w.scratch, w.scratch + 0x10
    put_vec(mem, pos_arg, origin)
    put_vec(mem, vel_arg, velocity)
    mem.wf32(RC.G_LEVEL_MONSTER_LEVEL, rng.choice((1.0, 3.5, 6.0, 10.0, 12.0, 16.0, 25.0, 40.0)))
    mem.w32(A.G_LEVEL_FLAGS, rng.choice((0, 0, 0, 0x100, 0x40000)))
    mem.w32(A.G_PVP_MODE_A, rng.choice((0, 0, 1)))
    words = (rng.choice((0, 0x00B10000, 0x00B10000)), rng.choice((0, 0x00B20000, 0x00B20000)))
    put_vec(mem, A.G_MODEL_TABLE + 8, words + (0,))
    name, table, size, ctor, run, _touch, _end, dtor = A.CLASSES[element]
    block = rng.choice(w.small if size < 0x100 else w.large)
    zero(mem, block, 0x400)
    level = C.to_int(mem.u32(RC.G_LEVEL_MONSTER_LEVEL))
    key = (name + (' (player owner)' if control else ''), target)
    rows = []
    case_calls = []

    def call(fname, method, args):
        before = (mem.u32(RC.G_RAND_SEED), mem.u32(block + 0x44), mem.u32(A.G_COSMETIC_SEED))
        res = rig.do(fname, method, args, note=name)
        tally.calls += 1
        failed = any(res[p] for p in ('fault', 'calls', 'writes', 'seed', 'result'))
        if failed:
            tally.mismatches += 1
            if len(tally.examples) < 5:
                tally.examples.append((key, fname, {p: res[p] for p in ('fault', 'calls', 'writes', 'seed', 'result')
                                                    if res[p]}))
        if res['both_fault'] is not None:
            tally.both += 1
        case_calls.extend(res['emu_calls'])
        after = (mem.u32(RC.G_RAND_SEED), mem.u32(block + 0x44), mem.u32(A.G_COSMETIC_SEED))
        rows.append((fname, res['draws'], lcg_steps(before[1], after[1]) if fname != name + '_ctor' else 0,
                     lcg_steps(before[2], after[2])))
        return res

    if element == 0:
        call(name + '_ctor', 'missile_ctor',
             (block, 0, words[0], words[1], pos_arg, vel_arg, (angle - 0x4000) & 0xFFFF, owner,
              0, 0, rng.choice((2, 5, 9)), rng.choice((3, 6, 7)), 0, 0, rng.choice((40, 200, 1000)), 4, 0))
    else:
        skill = mem.u32(SB.G_SKILL_TABLE + 4 * SKILL_IDS[element])
        call(name + '_ctor', A.METHODS[ctor], (block, pos_arg, angle & 0xFFFF, owner, level, skill))
    w.live.add(block)
    if element == 6 and target == 'wall' and rng.random() < 0.4:
        # the Skeleton has walked under its own arrow's path, up on the wall's foot: an
        # explosion there knocks the owner too (the arrow passes through its owner)
        wall = w.scene['wall']
        put_vec(mem, owner + 0x10, (sx + ux * (wall - 4.0), sy + uy * (wall - 4.0),
                                    fl(origin[2]) - rng.choice((5.0, 15.0))))
    ended, frames, outcome, stuck_frames = None, 0, None, 0
    host_gone_after = rng.choice((3, 30, None))
    w.under = False
    orphan_at = rng.randrange(1, 6) if target == 'orphan' else None
    for frame in range(1, 720):
        mem.w32(RC.G_SIM_FRAME, (mem.u32(RC.G_SIM_FRAME) + 1) & M32)
        if stuck_frames == host_gone_after and mem.u32(block + 0x128):   # the stuck arrow's host is destroyed
            host_gone_after = None
            call('handle_clear', 'handle_clear', (mem.u32(mem.u32(block + 0x128) + 0xC),))
        if frame == orphan_at:                          # the owner is destroyed: its handles read 0
            call('handle_clear', 'handle_clear', (owner,))
            put_vec(mem, owner + 0x10, (FAR, FAR + 900.0, 0.0))     # and it is no longer in the world
        res = call(name + '_run', A.METHODS[run], (block,))
        frames = frame
        calls = res['emu_calls']
        if res['fault'] or res['both_fault'] is not None:
            outcome = 'stopped'
            break
        if element == 0 and mem.u32(block + 0x128):
            if control:
                stuck_frames += 1
            else:
                tally.stuck_monster += 1
        if ('GameObject_dtor', (block, 0)) in calls:
            ended = 'destroyed in its run'
            break
        if ('obj_delete', (block,)) in calls:
            ended = 'obj_delete'
            if element and rng.random() < 0.2:          # not in the game (obj_delete took it off the run
                call(name + '_run', A.METHODS[run], (block,))     # list): the guard +0x60 of an ended arrow
            call(name + '_dtor', A.METHODS[dtor], (block, 3))     # the next flush: slot 1 with 3
            break
    roles = {player: 'player', victim: 'creature', other_c: 'ally creature', prop: 'prop', skeleton: 'owner'}
    if outcome is None:
        outcome = classify(case_calls, ended, roles, w.under, stuck_frames, frames)
    if stuck_frames:
        tally.stuck_control += 1
    # bookkeeping: draws by kind for this case
    k = (key[0], outcome)
    t = tally.outcomes.setdefault(k, [0, 0])
    t[0] += 1
    t[1] += frames
    d = tally.draws.setdefault(key[0], [0, 0, 0, 0])
    d[0] += sum(r[1] for r in rows)
    d[1] += sum(r[2] or 0 for r in rows)
    d[2] += sum(r[3] or 0 for r in rows)
    d[3] += 1
    # clean up the handle lists (not compared): the arrow's and every object's
    for head in (block, block + 4, block + 8, block + 0x4C, block + 0x124, block + 0x128):
        if mem.u32(head) and w.node_lo <= mem.u32(head) < w.node_hi:
            rig.emu.call(0x1A1698, head)
    for obj in w.objects:
        for head in (obj, obj + 4, obj + 8):
            if mem.u32(head):
                rig.emu.call(0x1A1698, head)
    rig.emu.reset_log()
    w.live.discard(block)
    w.scene = None
    tally.cases += 1


def classify(calls, ended, roles, under, stuck_frames, frames):
    """What ended the arrow, from the original's calls of the case."""
    if ended is None:
        if stuck_frames:
            return 'stuck, following the host for %d runs (no expiry while stuck)' % stuck_frames
        return 'still flying after %d runs' % frames
    victims = []
    for name, args in calls:
        if name == 'damage_apply' and args[0] not in [v for v in victims]:
            victims.append(args[0])
    parts = []
    if any(c[0] == 'item_parseDescriptor' for c in calls):
        parts.append('deflected by ' + ('player' if any(c[0] == 'Player_blockSparks' for c in calls) else 'creature'))
    if victims:
        parts.append('damage to ' + '+'.join(sorted({roles.get(v, 'other') for v in victims})))
    if any(c[0] == 'Creature.v2' for c in calls):
        parts.append('container hit')
    if stuck_frames:
        parts.append('stuck %d runs' % stuck_frames)
    if not parts and any(c[0] == 'Creature.v6' for c in calls):
        parts.append('touched, no damage')
    if under:
        parts.append('terrain')
    if not parts:
        parts.append('expiry')
    return ', '.join(parts) + ' (' + ended + ')'


def main(argv):
    args = list(argv)
    elf = None
    while args:
        a = args.pop(0)
        if a == '--quick':
            OPTIONS['quick'] = True
        elif a == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif a == '--cases':
            OPTIONS['cases'] = int(args.pop(0), 0)
        elif a == '-v':
            OPTIONS['verbose'] = True
        elif a == '--trace-first':
            OPTIONS['trace_first'] = True
        else:
            elf = a
    if elf is None:
        elf = os.path.join(ROOT, 'SLUS_209.73')
        if not os.path.exists(elf):
            elf = os.path.join(ROOT, 'local', 'SLUS_209.73')
    if not os.path.exists(elf):
        print('difftest_arrow_run: %s not found - nothing to compare with (this is not a failure)' % elf)
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != DC.EXPECTED_SHA256:
        print('difftest_arrow_run: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    C.set_fpu(OPTIONS['fpu'])
    started = time.time()
    rig = Rig(elf, OPTIONS['seed'])
    rng = random.Random(OPTIONS['seed'] * 7919 + 1)
    tally = Tally()
    cases = max(OPTIONS['cases'] // 10, 1) if OPTIONS['quick'] else OPTIONS['cases']
    for _ in range(cases):
        run_case(rig, rng, tally)
    print('seed %d: %d cases, %d calls compared, %d with a mismatch, %d stopped on both sides; %.0f s'
          % (OPTIONS['seed'], tally.cases, tally.calls, tally.mismatches, tally.both, time.time() - started))
    for key, fname, problems in tally.examples:
        print('  mismatch %s %s: %s' % (key, fname, problems))
    print('outcomes (class, what ended it: cases, mean runs):')
    for (cls, outcome), (n, runs) in sorted(tally.outcomes.items()):
        print('  %-38s %-58s %5d  %6.1f' % (cls, outcome, n, runs / n))
    print('draws per case (class: shared 0x404464 / the arrow\'s own +0x44 / cosmetic 0x404460, means):')
    for cls, (shared, own, cosmetic, n) in sorted(tally.draws.items()):
        print('  %-38s %8.2f %8.2f %8.2f   (%d cases)' % (cls, shared / n, own / n, cosmetic / n, n))
    print('monster-owned MissileWeapon runs with a stuck host +0x128: %d; player-owned cases that stuck: %d'
          % (tally.stuck_monster, tally.stuck_control))
    print('calls compared per original function / with any mismatch / shared-seed draws:')
    for fname in sorted(rig.stats):
        print('  %-36s %7d / %d / %d' % ((fname,) + tuple(rig.stats[fname])))
    print('coverage of the original as executed here (instructions):')
    for fname, (start, end) in sorted(A.BODIES.items(), key=lambda kv: kv[1]):
        inside = {pc for pc in rig.cov if start <= pc < end}
        total = (end - start) // 4
        print('  %-36s %5d of %5d' % (fname, len(inside), total))
        if OPTIONS['verbose'] and len(inside) != total:
            missed = [pc for pc in range(start, end, 4) if pc not in inside]
            spans, first = [], None
            for i, pc in enumerate(missed):
                if first is None:
                    first = pc
                if i + 1 == len(missed) or missed[i + 1] != pc + 4:
                    spans.append('%x-%x' % (first, pc + 4))
                    first = None
            print('      not executed: %s' % ', '.join(spans))
    if rig.unknown:
        print('calls to unknown addresses: %s' % {('%x' % k): v for k, v in rig.unknown.items()})
    return 0 if not tally.mismatches and not rig.unknown and not tally.stuck_monster else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
