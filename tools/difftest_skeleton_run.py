#!/usr/bin/env python3
"""difftest_skeleton_run.py - compare tools/ref_skeleton_run.py with the game's own code:
the whole of Skeleton_run (every state of its switch, the bow release included),
creature_allyInLineOfFire, Creature_leadTargetPoint, Skeleton_onNearbyEvent (slot 12) and
Skeleton_hasShield.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_skeleton_run.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                            [--ticks N] [-v] [--trace-first]

What is compared
    tools/difftest_combat_ctors2.py's rig and world for the Skeleton class, WITHOUT the
    switch patch: the original Skeleton_run runs to its end.  Real underneath: the
    creature base (ref_creature, ref_arena_monsters, ref_monsters_1), Skeleton_ctor,
    Skeleton_setState, Skeleton_isEnemy with the type-info getters (slot 20 inside the
    prologue's target scan), and the five bodies above.  Callbacks (recording stubs,
    answered by the scripted world): creature_canSeeObj, world_countLivingNonplayer-
    CreaturesInBox, creature_objInArcRange, world_raycast, Creature_hitTargetAtReach,
    Creature_deadUpdate, Creature_applyKnockback, the holder's slots 1, 15, 16, 17 and 21,
    libc_sprintf, res_find, sound_playOnObject, pool_new, the three arrow constructors,
    MissileWeapon_ctor, fx_spawn, the anim calls.  Each call runs through the model first
    on a copy-on-write view of the same memory, and these must be equal: the calls with
    their arguments (stack arguments and the hit descriptor decoded), the bytes stored
    outside the stack, the shared seed with its draw count, the result.

Scenarios
    machine A and B, 'seed' and 'seed + 1': constructions (every weapon kind), then ticks
    of the run in any state the driver puts the skeleton in (all 24 and out-of-range
    numbers), with +0xf4 near the clock and around 0, the weapon kind word +0x3d0 moved,
    clip flags, the frame (so the line-of-fire sweep's every-8th-frame test passes),
    targets present or not, sight answers biased all ways, elements and hand parts of
    every kind, pool blocks refused or given.  Set-state requests between ticks.  Direct
    calls of the sweep (targets, previous 0 / 1 / other), of the lead point (out pointer
    or 0), of slot 12 (event codes 0-4, states 3 and 5 often, others at every bearing) and
    of hasShield.
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
import ref_combat_ctors as CT                   # noqa: E402
import ref_combat_ctors2 as CT2                 # noqa: E402
import ref_skeleton_run as SR                   # noqa: E402
import ref_core as C                            # noqa: E402
import difftest_creature as DC                  # noqa: E402
import difftest_arena_monsters as DA            # noqa: E402
import difftest_monsters_1 as DM                # noqa: E402
import difftest_combat_ctors as DT              # noqa: E402
import difftest_combat_ctors2 as DT2            # noqa: E402
from difftest_creature import Res, f32, M32     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = DC.OPTIONS
OPTIONS.update({'seed': 20973, 'ticks': 3000})

BODIES = {
    'Skeleton_run': (0x2A6864, 0x2A7508),
    'creature_allyInLineOfFire': (0x10D5E8, 0x10D7FC),
    'Creature_leadTargetPoint': (0x11AAF8, 0x11ABD0),
    'Skeleton_onNearbyEvent': (0x2A7688, 0x2A774C),
    'Skeleton_hasShield': (0x2A7DA0, 0x2A7E04),
}

REAL = set(DT2.REAL) | set(SR.EXECUTED.values())

ENTRIES = dict(DT2.ENTRIES)
ENTRIES.update({
    'Skeleton_run': (0x2A6864, 'c', 'n', 'skeleton_run'),
    'creature_allyInLineOfFire': (0x10D5E8, 'ciiff', 'i', 'ally_in_line_of_fire'),
    'Creature_leadTargetPoint': (0x11AAF8, 'cif', 'i', 'lead_target_point_entry'),
    'Skeleton_onNearbyEvent': (0x2A7688, 'civi', 'n', 'skeleton_on_nearby_event'),
    'Skeleton_hasShield': (0x2A7DA0, 'c', 'i', 'skeleton_has_shield'),
})

STATES = list(range(0, 0x18)) + [0x18, 0x19, 0x40, 0x7FFF, 0x8000, 0xFFFF] + [3, 3, 5, 5, 6, 8, 8, 8, 0x10, 0x11]
REQUESTS = list(range(0, 0x18)) + [3, 3, 5, 5, 6, 8, 8, 8, 0x11, 0x12, 0x17]
ELEMENTS = (0, 0, 1, 2, 6, 3, 4, 5, 7, 0xFFFFFFFF)
PARTS = (0x60, 0x62, 0x60, 0x62, 0, 0x52, 0x54, 0x61, 0x5E)


class RealSet:
    def __contains__(self, target):
        return target in REAL or DC.LIB_LO <= target < DC.LIB_HI


class World(DT2.World):
    """The ctors-2 world for the Skeleton, plus holder slot 16, the arrow blocks and the
    answers of the release, the sweep and slot 12."""

    def build(self, rng):
        DT2.World.build(self, rng)
        emu, mem = self.emu, self.mem
        for table in DA.HOLDER_TABLES:
            for slot in (15, 16):
                fn = mem.u32(table + 8 * slot + 4)
                if fn not in REAL:
                    self.addr_name.setdefault(fn, 'Holder.v%d' % slot)
        for size in (0xB0, 0x74, SR.MISSILE_SIZE):
            blocks = [emu.alloc((size + 0xF) & ~0xF) for _ in range(2)]
            self.pool[size] = blocks
            for b in blocks:
                self.pool_size[b] = size
        # a descriptor block that holds what the hit code reads (eight zero halfwords, two
        # 0xff bytes, four slots), next to the world's zero-filled one
        self.good_descriptor = emu.alloc(0x40)
        mem.w8(self.good_descriptor + 0x20, 0xFF)
        mem.w8(self.good_descriptor + 0x21, 0xFF)
        for k, ident in enumerate((0x17, 0xFFFF, 3, 0xFFFF)):
            mem.w16(self.good_descriptor + 0x24 + 8 * k, ident)
            mem.w16(self.good_descriptor + 0x26 + 8 * k, 5 + k)
            mem.w16(self.good_descriptor + 0x28 + 8 * k, 9 + k)
        self.count_bias = 0.5

    def on_Holder_v15(self, args, view, rng):
        return Res(rng.choice(PARTS))

    def on_Holder_v16(self, args, view, rng):
        return Res(rng.choice(ELEMENTS))

    def on_Holder_v17(self, args, view, rng):
        return Res(rng.choice((0, self.descriptor, self.good_descriptor)))

    def on_world_countLivingNonplayerCreaturesInBox(self, args, view, rng):
        return Res(rng.choice((2, 3, 4, 5, 9)) if rng.random() < self.count_bias else rng.choice((0, 1, 2, 3)))

    def on_creature_objInArcRange(self, args, view, rng):
        rng.swept = args[1]                     # the sweep's target, kept on the per-call generator
        return Res(1 if rng.random() < 0.7 else 0)

    def on_world_raycast(self, args, view, rng):
        t = rng.choice([f32(v) for v in (-1.0, 0.0, 0.25, 0.6, 0.999, 1.0, 1.5)])
        swept = getattr(rng, 'swept', 0)
        return Res(f=t, outs=[rng.choice([0, 0, swept, swept] + self.others[:4] + self.players[:2])])

    def on_MissileWeapon_ctor(self, args, view, rng):
        return Res()


class Rig(DT2.Rig):
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

        for name, ext in SR.EXTERNALS.items():
            if name == 'cxx_throwBadTypeid':
                continue
            if ext.addr:
                add(ext.addr, name, ext)
            elif name in self.world.stub_addr:
                add(self.world.stub_addr[name], name, ext)
        for addr, name in list(self.world.stub_name.items()) + list(self.world.addr_name.items()):
            if addr not in self.names:
                add(addr, name, SR.EXTERNALS.get(name) or RC.Ext(0, 'p', 0, 'n'))

        def throw(emu):
            self.calls.append(('cxx_throwBadTypeid', ()))
            raise EmuError('__throw_bad_typeid')
        self.names[0x3B3338] = 'cxx_throwBadTypeid'
        emu.stub(0x3B3338, function=throw, name='cxx_throwBadTypeid')
        for entry, test, _method in CT.RUN_PROLOGUES.values():     # AntQueen and Soul only
            if entry != SR.SKELETON_RUN:
                emu.patch(test, DT.ADDIU_V0_ZERO)
        self.partial, self.partial_ops = [], {}
        for start, end in list(DC.BODIES.values()) + list(DA.BODIES.values()) + list(DM.BODIES.values()) + \
                list(DT.BODIES.values()) + list(DT2.BODIES.values()) + list(BODIES.values()):
            for pc in range(start, end, 4):
                w = emu.mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E) and pc not in self.partial_ops:
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                ret = res.ret & (RC.M64 if SR.EXTERNALS[name].ret == 'q' else M32)
                return SR.shape_result(name, args, ret, res.f & M32, res.outs)
            return answer

    def compare(self, key, args, call_seed, trace=None):
        saved = DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks
        DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks = ENTRIES, Model, Rig.Callbacks
        Model.last[0] = None
        try:
            out = DM.Rig.compare(self, key, args, call_seed, trace)
        finally:
            DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks = saved
        if key == 'Creature_leadTargetPoint' and not out['fault'] and out['both_fault'] is None and args[1]:
            mem = self.emu.mem
            got = tuple(mem.u32(args[1] + 4 * k) for k in range(3))
            want = Model.last[0] if Model.last[0] is not None else LEAD_FILL
            if got != want:
                out['result'] = 'out point: original %s model %s' % (got, want)
        return out


LEAD_FILL = (0x11111111, 0x22222222, 0x33333333)
TALLY = ('ColdArrowProjectile_ctor', 'FireArrowProjectile_ctor', 'ExplodeArrowProjectile_ctor', 'MissileWeapon_ctor',
         'world_raycast', 'Creature_hitTargetAtReach', 'sound_playOnObject', 'Creature_deadUpdate', 'fx_spawn')


class Model(SR.Model):
    """The model, keeping the lead point of the standalone entry."""
    last = [None]

    def lead_target_point_entry(self, c, out, speed):
        result = SR.Model.lead_target_point_entry(self, c, out, speed)
        Model.last[0] = self.dest
        return result


class Coverage(DC.Coverage):
    def __init__(self, mem):
        self.parts = {name: (start, end) + DC.analyse(mem, start, end) for name, (start, end) in BODIES.items()}
        self.pcs = set()


class Driver(DT.Driver):
    def between_class(self):
        DT.Driver.between_class(self)
        rng, mem, world = self.rng, self.mem, self.world
        c, r = world.C, rng.random
        clock = mem.u32(c + 0x300)
        if r() < 0.12:
            mem.w16(c + 0x232, rng.choice(STATES))
        if r() < 0.1:
            mem.w32(c + 0xF4, rng.choice(((clock + rng.choice((-5, -1, 0, 1, 2, 30, 300))) & M32,
                                          rng.choice((0, 1, 2, 3, 0xFFFFFFFF, 20)))))
        if r() < 0.06:
            mem.w32(c + 0x3D0, rng.choice((0, 1, 2, 3, 4, 4, 4, 5)))
        if r() < 0.1:
            mem.w16(c + 0x11A, rng.choice((0, 8, 0x10, 0x18, 0x80, 0x88)))
        if r() < 0.3:                                            # the frame: every 8th passes the sweep
            mem.w32(RC.G_SIM_FRAME, (mem.u32(RC.G_SIM_FRAME) + rng.choice((1, 1, 8, 3))) & M32)
        if r() < 0.25:
            mem.w32(RC.G_SIM_FRAME, (mem.s8(c + 0x230) & 7) | (rng.randrange(1 << 20) << 3))
        if r() < 0.05:
            world.count_bias = rng.choice((0.1, 0.5, 0.9))
        if r() < 0.04:                                           # stunned / rooted / attack cooldown
            mem.w16(c + rng.choice((0x314, 0x31C, 0x318)), rng.choice((0, 0, 3)))
        if r() < 0.04:
            mem.wf32(RC.G_LEVEL_MONSTER_LEVEL, rng.choice((1.0, 2.5, 7.9, 30.0)))
        if r() < 0.02:
            for k in (8, 0xC):
                mem.w32(SR.MISSILE_WORDS + k, rng.choice((0, 0, 3, 0x12345)))
        if r() < 0.03:                                           # target anywhere near or far, moving
            node = mem.u32(c + 0x234)
            if node:
                obj = mem.u32(node + 0xC)
                mem.wf32(obj + 0x10, mem.f32(c + 0x10) + rng.uniform(-500, 500))
                mem.wf32(obj + 0x14, mem.f32(c + 0x14) + rng.uniform(-500, 500))
                mem.wf32(obj + 0x308, rng.choice((0.0, 150.0, -200.0)))
                mem.wf32(obj + 0x30C, rng.choice((0.0, 80.0, -120.0)))
        if r() < 0.04:
            mem.w16(c + 0x38, rng.randrange(0x10000))
        if r() < 0.01:                                           # no weapon holder (until the next construction)
            mem.w32(c + 0x50, 0)


def run(elf, name, seed, machine, ticks, coverage, counts):
    kind = 'skeleton'
    rig = Rig(elf, seed, kind, machine, 1)
    driver = Driver(rig)
    world, mem, rng = rig.world, rig.emu.mem, rig.rng
    info = DT.CLASSES[kind]
    if coverage[0] is None:
        coverage[0] = Coverage(mem)
    cov = coverage[0]
    c = world.C
    bad = {'calls': [], 'writes': [], 'seed': [], 'result': [], 'fault': []}
    both = {}
    serial = [0]
    draws_by_entry = {}
    tick = [0]

    def do(key, *args):
        serial[0] += 1
        if key == 'Skeleton_run':
            state = mem.s16(c + 0x232)
            seen = counts.setdefault('_states', {})
            seen[state] = seen.get(state, 0) + 1
        result = rig.compare(key, tuple(args), seed * 1000003 + serial[0], trace=cov.pcs)
        row = counts.setdefault(key, [0, 0])
        row[0] += 1
        failed = False
        for prop in ('fault', 'calls', 'writes', 'seed', 'result'):
            if result[prop]:
                failed = True
                bad[prop].append('tick %d %s(%s) state %#x: %s' % (tick[0], key, ', '.join(
                    '%x' % a if isinstance(a, int) else str(a) for a in args), mem.u16(c + 0x232), result[prop]))
        if result['both_fault'] is not None:
            both[result['both_fault']] = both.get(result['both_fault'], 0) + 1
        if key == 'Skeleton_run' and not result['fault']:
            named = counts.setdefault('_callees', {})
            for call in result['emu_calls']:
                if call[0] in TALLY:
                    named[call[0]] = named.get(call[0], 0) + 1
        if result.get('draws'):
            draws_by_entry[key] = draws_by_entry.get(key, 0) + result['draws']
        if failed:
            row[1] += 1
            if OPTIONS['trace_first']:
                print('first mismatch in run %s, tick %d, %s' % (name, tick[0], key))
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
        extra = rng.choice(info.get('extra', (0,)))
        values = {'c': c, 't': rng.choice(world.type_names), 'v': pos, 'f': facing, 'p': world.props, 'x': extra}
        do('Skeleton_ctor', *[values[k] for k in info['order']])
        hp = rng.choice((300.0, 300.0, 1200.0))
        mem.wf32(c + 0x228, hp)
        mem.wf32(c + 0x22C, hp)
        mem.w8(c + 0x231, 0)
        mem.w32(c + 0xC8, 0)

    def some_other():
        return rng.choice(world.others[:4] + world.players[:2])

    for t in range(ticks):
        tick[0] = t
        r = rng.random
        if driver.need_ctor:
            driver.need_ctor = False
            construct()
        driver.between()
        if driver.need_ctor:
            continue
        driver.between_class()
        if r() < 0.3:                                           # the others: classes, sides, places
            other = some_other()
            DT2.plant(world, rng, other, rng.choice(list(DT2.PLANT_TABLES) + ['synthetic', 'Skeleton']))
            if r() < 0.5:
                mem.wf32(other + 0x10, mem.f32(c + 0x10) + rng.uniform(-300, 300))
                mem.wf32(other + 0x14, mem.f32(c + 0x14) + rng.uniform(-300, 300))
        if r() < 0.04:
            attacker = rng.choice(world.others + world.players + [0])
            do('Creature_takeDamage', c, attacker, rng.choice(DC.DAMAGE_FLAGS),
               f32(rng.choice((0.0, 3.0, 20.0, 60.0, 400.0))))
        do('Skeleton_run', c)
        if r() < 0.25:
            do('Skeleton_setState', c, rng.choice(REQUESTS))
        if r() < 0.08:                                          # the sweep on its own
            target = rng.choice([0] + world.others[:4] + world.players[:2])
            do('creature_allyInLineOfFire', c, target, rng.choice((0, 0, 1, 1, 7, 0xFFFFFFFF)),
               f32(rng.choice((300.0, 50.0))), f32(rng.choice((54.0, 30.0, 0.0))))
        if r() < 0.04:
            for k in range(3):
                mem.w32(world.argbuf + 0x80 + 4 * k, LEAD_FILL[k])
            do('Creature_leadTargetPoint', c, rng.choice((world.argbuf + 0x80, world.argbuf + 0x80, 0)),
               f32(rng.choice((400.0, 250.0, 1.0))))
        if r() < 0.1:                                           # slot 12
            if r() < 0.5:
                mem.w16(c + 0x232, rng.choice((3, 5)))
            other = rng.choice([0] + world.others[:4] + world.players[:2])
            if other and r() < 0.6:                             # near the facing, or anywhere
                heading = mem.s16(c + 0x38) + rng.choice((0, 3000, -3000, 9998, 9999, 10000, -9999, -10000,
                                                          rng.randrange(0x10000)))
                mem.w32(other + 0x10, C.add(mem.u32(c + 0x10), C.mul(C.cos16(heading), f32(100.0))))
                mem.w32(other + 0x14, C.add(mem.u32(c + 0x14), C.mul(C.sin16(heading), f32(100.0))))
            pos = tuple(f32(rng.uniform(-10, 10)) for _ in range(3))
            do('Skeleton_onNearbyEvent', c, rng.choice((2, 2, 2, 0, 1, 3, 4)), pos, other)
        if r() < 0.03:
            do('Skeleton_hasShield', c)
        if r() < 0.005:
            construct()
        if mem.s16(c + 0x232) == 0x14 and r() < 0.1 or mem.u32(c + 0xC) & 0x4000 and r() < 0.3:
            driver.respawn()
    if rig.unknown:
        bad['calls'].append('calls to addresses that are neither real nor known stubs: %s'
                            % {hex(a): n for a, n in rig.unknown.items()})
    text = 'Skeleton run, machine %s' % ('B' if machine else 'A')
    count = serial[0]
    DC.report(name + ' calls', len(bad['calls']), count, 'callbacks in order with arguments; ' + text, bad['calls'])
    DC.report(name + ' writes', len(bad['writes']), count, 'bytes stored and their final values', bad['writes'])
    DC.report(name + ' seed', len(bad['seed']), count, 'shared seed and number of draws', bad['seed'])
    DC.report(name + ' result', len(bad['result']), count, 'returned values', bad['result'])
    DC.report(name + ' faults', len(bad['fault']), count,
              'calls that stopped on one side only (%d stopped on both, the same way)' % sum(both.values()),
              bad['fault'])
    return count, draws_by_entry


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
        elif a == '-v':
            OPTIONS['verbose'] = True
        elif a == '--trace-first':
            OPTIONS['trace_first'] = True
        else:
            elf = a
    if elf is None:
        for candidate in (os.path.join(ROOT, 'SLUS_209.73'), os.path.join(ROOT, 'local', 'SLUS_209.73')):
            if os.path.exists(candidate):
                elf = candidate
                break
    if elf is None or not os.path.exists(elf):
        print('difftest_skeleton_run: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != DC.EXPECTED_SHA256:
        print('difftest_skeleton_run: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    ticks = max(OPTIONS['ticks'] // 10, 1) if OPTIONS['quick'] else OPTIONS['ticks']
    RC.C.set_fpu(OPTIONS['fpu'])
    started = time.time()
    coverage, counts, draws = [None], {}, {}
    total = 0
    for index, machine in enumerate((0, 1, 0, 1)):
        name = 'skeleton/%s%d' % ('B' if machine else 'A', index // 2)
        n, d = run(elf, name, OPTIONS['seed'] + index, machine, ticks, coverage, counts)
        total += n
        for key, value in d.items():
            draws[key] = draws.get(key, 0) + value
    print()
    print('Skeleton_run ticks by state at entry: %s' % ', '.join(
        '%#x: %d' % kv for kv in sorted(counts.pop('_states', {}).items())))
    print('Skeleton_run callees seen: %s' % ', '.join('%s %d' % kv for kv in sorted(counts.pop('_callees', {}).items())))
    print('calls compared per entry point / calls with any mismatch / shared draws seen')
    for key in sorted(counts):
        print('  %-28s %7d / %d / %d' % (key, counts[key][0], counts[key][1], draws.get(key, 0)))
    print('coverage of the original as executed here (basic blocks, instructions):')
    for part in BODIES:
        b, bt, i, it = coverage[0].numbers(part)
        print('  %-28s blocks %4d of %4d  instructions %4d of %4d' % (part, b, bt, i, it))
        if OPTIONS['verbose'] and b != bt:
            print('      never entered: %s' % ' '.join('%06x' % a for a in coverage[0].missing(part)))
    if OPTIONS['verbose']:
        for part, (start, end) in BODIES.items():
            unrun = [pc for pc in range(start, end, 4) if pc not in coverage[0].pcs]
            print('  %-28s instructions never executed: %s' % (part, ' '.join('%06x' % pc for pc in unrun)))
    print('%d calls compared in %.0f s' % (total, time.time() - started))
    return 0 if all(ok for _name, ok in DC.RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
