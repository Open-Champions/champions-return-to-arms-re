#!/usr/bin/env python3
"""difftest_combat_ctors.py - compare tools/ref_combat_ctors.py with the game's own code:
the AntQueen, Skeleton and Soul constructors, their set-state functions, and their run
functions up to the state switch.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_combat_ctors.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                            [--ticks N] [-k TEXT] [-v] [--trace-first]

    --quick       a tenth of the ticks
    --seed N      seed of the random runs (default 20973); a seed repeats exactly
    --ticks N     steps per run (default 600; two runs per class, machine A and B)
    -k TEXT       only the runs whose name contains TEXT
    -v            print the blocks never entered
    --trace-first stop at the first mismatching call and print both sides

What is compared
    tools/difftest_monsters_1.py's rig and scripted world.  The ORIGINAL constructor and
    set-state function of each class, Soul's slot 16, anm_setEventSlots, and the creature
    base underneath (ref_creature.MODELLED, ref_arena_monsters.MODELLED, the batch-1
    monster functions) run in tools/ee_emu.py on an object the original constructor built,
    with the game's own virtual table.  Each call runs through the model first on a
    copy-on-write view of the same memory, and these must be equal: the calls to
    everything outside the models with their arguments, the bytes stored outside the
    stack, the shared seed, the result.

    The run functions run for real up to their state switch.  To stop there, the switch's
    range test (ref_combat_ctors.RUN_PROLOGUES) is replaced, in the interpreter only, by
    'addiu v0, zero, 0', so the original takes its own "state out of range" exit.  What
    is compared is therefore exactly the prologue: damage, Creature_run, activity, the
    holder, the animation step, knockback, slot 23 and (Soul) the zero-vector move.

Scenarios
    per class, machine A and machine B: construct (type names of every prefix, all four
    Skeleton model sets, Souls with and without an owner, on "airhub" and elsewhere,
    the skelcom block resolved or not), then ticks of: the prologue; set-state for every
    state number, valid or not, and again for the fight states; the filter's timers,
    targets, clip flags, hit directions and owner handles moved by the driver.  A dead
    creature is constructed again.
"""
import hashlib
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_arena_monsters as AM                 # noqa: E402
import ref_monsters_1 as M1                     # noqa: E402
import ref_combat_ctors as CT                   # noqa: E402
import difftest_creature as DC                  # noqa: E402
import difftest_arena_monsters as DA            # noqa: E402
import difftest_monsters_1 as DM                # noqa: E402
from difftest_creature import Res, f32, M32     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = DC.OPTIONS
OPTIONS.update({'seed': 20973, 'ticks': 600})

ADDIU_V0_ZERO = 0x24020000                      # addiu v0, zero, 0 (authored, not from the game)

BODIES = {
    'AntQueen_ctor': (0x236C70, 0x236F10), 'AntQueen_setState': (0x237918, 0x238150),
    'AntQueen_run prologue': (0x236F78, 0x237010),
    'Skeleton_ctor': (0x2A5AF4, 0x2A67C4), 'Skeleton_setState': (0x2A7768, 0x2A7DA0),
    'Skeleton_run prologue': (0x2A6864, 0x2A6960),
    'Soul_ctor': (0x2A9478, 0x2A9678), 'Soul_setState': (0x2AAC38, 0x2AB298),
    'Soul_run prologue': (0x2A9870, 0x2A9988),
    'Soul_getModel': (0x2AB298, 0x2AB2B4), 'anm_setEventSlots': (0x1183D0, 0x11840C),
}

REAL = set(RC.MODELLED.values()) | set(AM.MODELLED.values()) | set(M1.MODELLED.values()) | \
    set(CT.MODELLED.values()) | set(DC.REAL_OTHER) | {a for a, _t, _m in CT.RUN_PROLOGUES.values()}

SKEL_TYPES = (b'Skeleton', b'Skeleton2', b'WatSkel', b'SkeletonRed', b'skeletonblue', b'SkeletonSwordOHWRed',
              b'SkeletonSwordOHWBlue', b'SkeletonSwordDHWRed', b'skeletonsworddhwblue', b'SkeletonAxeRed',
              b'SkeletonAxeBlue', b'SkeletonSpearRed', b'SkeletonSpearBlue', b'SkeletonBowRed', b'SkeletonBowBlue',
              b'SkeletonSwordOHW', b'SkeletonSwordDHW', b'SkeletonAxe', b'SkeletonSpear', b'SkeletonBow',
              b'skeletonbow3', b'SkelRed')
CLASSES = {
    'antqueen': dict(name='AntQueen', table=CT.VT_ANTQUEEN, defs=((CT.DEF_ANTQUEEN, 1, 25),), order='ctvfp',
                     types=(b'AntQueen', b'antqueen', b'AntQueen2'),
                     states=list(range(0, 0x1C)) + [0x40, 0xFFFFFFFF, 0, 1, 3, 3, 6, 7, 7, 8, 9, 0x12, 0x12, 0x17,
                                                    0x17, 0x18, 0x14]),
    'skeleton': dict(name='Skeleton', table=CT.VT_SKELETON,
                     defs=tuple((CT.DEF_SKELETON + CT.DEF_SKELETON_STEP * n, 1, 2) for n in range(4)),
                     order='cvfptx', extra=(0, 0, 0, 1, 1, 2, 3), types=SKEL_TYPES,
                     states=list(range(0, 0x1A)) + [0x40, 0xFFFFFFFF, 0, 1, 3, 3, 5, 6, 6, 7, 8, 8, 0x11, 0x12,
                                                    0x12, 0x17, 0x14]),
    'soul': dict(name='Soul', table=CT.VT_SOUL, defs=((CT.DEF_SOUL, 1, 19),), order='ctvfpx', types=(b'Soul', b'soul'),
                 states=list(range(0, 0x24)) + [0x40, 0xFFFFFFFF, 0, 1, 0x12, 0x12, 0x18, 0x19, 0x1A, 0x1B, 0x1D,
                                                0x21, 0x21, 0x22, 0x14]),
}

ENTRIES = {
    'AntQueen_ctor': (0x236C70, 'civii', 'n', 'antqueen_ctor'),
    'AntQueen_setState': (0x237918, 'ci', 'n', 'antqueen_set_state'),
    'AntQueen_run': (0x236F78, 'c', 'n', 'antqueen_run_prologue'),
    'Skeleton_ctor': (0x2A5AF4, 'cviiii', 'n', 'skeleton_ctor'),
    'Skeleton_setState': (0x2A7768, 'ci', 'n', 'skeleton_set_state'),
    'Skeleton_run': (0x2A6864, 'c', 'n', 'skeleton_run_prologue'),
    'Soul_ctor': (0x2A9478, 'civiii', 'n', 'soul_ctor'),
    'Soul_setState': (0x2AAC38, 'ci', 'n', 'soul_set_state'),
    'Soul_run': (0x2A9870, 'c', 'n', 'soul_run_prologue'),
    'Creature_takeDamage': (0x116638, 'ciif', 'n', 'take_damage'),
}
LEVELS = (b'drunare', b'drunare', b'airhub', b'AirHub', b'airhub2', b'blomedal')


class RealSet:
    def __contains__(self, target):
        return target in REAL or DC.LIB_LO <= target < DC.LIB_HI


# ---------------------------------------------------------------------------------------
# The scripted world
# ---------------------------------------------------------------------------------------
class World(DM.World):
    """difftest_monsters_1's world with these classes' definitions, the skelcom block,
    the level name the Soul class compares, and the answers of the new callbacks."""

    def build(self, rng):
        DA.World.build(self, rng)
        emu, mem = self.emu, self.mem
        info = CLASSES[self.akind]
        self.def_entries = {}
        for d, first, end in info['defs']:
            mem.w32(d + 0xC, self.model)
            for k in range(first + 1, end):
                rec = emu.alloc(0x40)
                mem.w32(d + 8 * k + 4, rec)
                self.anim_entries[rec] = (d, k)
            self.def_entries[d] = end
        if self.akind == 'soul':
            mem.w32(CT.DEF_SOUL + 0x1C, 0x00C00080)     # the held / flying shape: another model
        self.common = {}
        if self.akind == 'skeleton':                    # skelcom: an entry per weapon-kind clip
            k = 1
            while mem.u32(CT.SKEL_COMMON + 8 * k) and k < 0x50:
                rec = emu.alloc(0x40)
                mem.w32(CT.SKEL_COMMON + 8 * k + 4, rec)
                self.common[mem.u32(CT.SKEL_COMMON + 8 * k)] = rec
                k += 1
            self.common_entries = k
        for slot in range(1, 40):
            fn = mem.u32(info['table'] + 8 * slot + 4)
            if fn not in REAL:
                self.addr_name.setdefault(fn, 'Creature.v%d' % slot)
        holder_slot3 = mem.u32(AM.VT_WEAPONSHIELD + 8 * 3 + 4)
        self.addr_name.setdefault(holder_slot3, 'Holder.v3')
        self.type_names = []
        for text in info['types']:
            s = emu.alloc(32)
            mem.write(s, text + b'\0')
            self.type_names.append(s)
        self.set_level(rng.choice(LEVELS))

    def set_level(self, name):
        DA.World.set_level(self, name)
        self.mem.write(CT.G_LEVEL_NAME, name + b'\0')

    # ---- answers ------------------------------------------------------------------------
    def on_res_find(self, args, view, rng):
        return Res(self.common.get(args[1], self.model))

    def on_AntQueen_pickFlyDest(self, args, view, rng):
        return Res(outs=[tuple(f32(rng.uniform(-600, 600) + 2000) for _ in range(2)) + (f32(10.0),)])

    def on_anim_findTrack(self, args, view, rng):
        return Res(rng.choice((0, 0, 0x00C00100)))


# ---------------------------------------------------------------------------------------
# The rig
# ---------------------------------------------------------------------------------------
class Rig(DM.Rig):
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

        for name, ext in CT.EXTERNALS.items():
            if ext.addr:
                add(ext.addr, name, ext)
            elif name in self.world.stub_addr:
                add(self.world.stub_addr[name], name, ext)
        for addr, name in list(self.world.stub_name.items()) + list(self.world.addr_name.items()):
            if addr not in self.names:
                add(addr, name, CT.EXTERNALS.get(name) or RC.Ext(0, 'p', 0, 'n'))
        for _entry, test, _method in CT.RUN_PROLOGUES.values():
            emu.patch(test, ADDIU_V0_ZERO)
        self.partial, self.partial_ops = [], {}
        for start, end in list(DC.BODIES.values()) + list(DA.BODIES.values()) + list(DM.BODIES.values()) + \
                list(BODIES.values()):
            for pc in range(start, end, 4):
                w = emu.mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                ret = res.ret & (RC.M64 if CT.EXTERNALS[name].ret == 'q' else M32)
                return CT.shape_result(name, args, ret, res.f & M32, res.outs)
            return answer

    def compare(self, key, args, call_seed, trace=None):
        """difftest_monsters_1's compare with this module's entries and model."""
        saved = DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks
        DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks = ENTRIES, CT.Model, Rig.Callbacks
        try:
            return DM.Rig.compare(self, key, args, call_seed, trace)
        finally:
            DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks = saved


class Coverage(DC.Coverage):
    def __init__(self, mem):
        self.parts = {name: (start, end) + DC.analyse(mem, start, end) for name, (start, end) in BODIES.items()}
        self.pcs = set()


# ---------------------------------------------------------------------------------------
# The driver
# ---------------------------------------------------------------------------------------
class Driver(DM.Driver):
    def between_class(self):
        DM.Driver.between_class(self)
        rng, mem, world = self.rng, self.mem, self.world
        c, r = world.C, rng.random
        kind = world.akind
        if r() < 0.04:                                          # filter timers: root, cooldown, stun
            mem.w16(c + rng.choice((0x314, 0x318, 0x31C)), rng.choice((0, 0, 0, 1, 25)))
        if r() < 0.05:
            mem.w16(c + 0x2E0, rng.randrange(0x10000))           # the last hit's direction
        if r() < 0.02:
            mem.w8(c + 0x231, rng.choice((0, 0, 1)))             # inert
        if r() < 0.02:                                          # no loot
            self.cflag(0x1000000, r() < 0.3)
        if r() < 0.02:
            world.set_level(rng.choice(LEVELS))
        if kind == 'soul':
            if r() < 0.04:                                      # a Minion holding it, or not
                mem.w32(c + 0x3C8, rng.choice((0, 0, world.nodes[world.others[1]])))
            if r() < 0.02:
                mem.w16(c + 0x232, rng.choice((0x18, 0x1B, 0x1A, 0x22, 0x14)))
        if kind == 'antqueen' and r() < 0.03:
            mem.w16(c + 0x232, rng.choice((6, 7, 8, 9, 0x12, 0x17)))
        if kind == 'skeleton' and r() < 0.03:
            mem.w16(c + 0x232, rng.choice((0x17, 0x12, 6, 3)))


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
        if kind == 'skeleton' and rng.random() < 0.3:          # skelcom not resolved for this generation
            mem.w32(CT.SKEL_COMMON + 4, mem.u32(CT.G_LUMP_GENERATION) ^ rng.choice((1, 0x100)))
        if rng.random() < 0.3:
            world.set_level(rng.choice(LEVELS))
        pos = (f32(2000.0 + rng.uniform(-50, 50)), f32(3000.0 + rng.uniform(-50, 50)), f32(10.0))
        facing = rng.choice((rng.randrange(0x10000), 0xFFFF8000 | rng.randrange(0x8000)))
        extra = rng.choice(info.get('extra', (0,)))
        if kind == 'soul':
            extra = rng.choice((0, 0, 0, world.others[1]))
        values = {'c': c, 't': rng.choice(world.type_names), 'v': pos, 'f': facing, 'p': world.props, 'x': extra}
        do(ctor_key, *[values[k] for k in info['order']])
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
        if r() < 0.06:
            attacker = rng.choice(world.others + world.players + [0])
            amount = rng.choice((0.0, 3.0, 20.0, 60.0, 400.0, 5000.0))
            if kind != 'soul':                                  # Soul's slot 2 is its own (not modelled)
                do('Creature_takeDamage', c, attacker, rng.choice(DC.DAMAGE_FLAGS), f32(amount))
        do(run_key, c)
        for _ in range(rng.choice((0, 1, 1, 2))):
            do(set_key, c, rng.choice(states))
        if kind == 'soul' and r() < 0.06:                       # a flinch or alarm while alarmed
            mem.w16(c + 0x232, 0x18)
            if r() < 0.7:
                mem.w32(c + 0x3C8, 0)
            do(set_key, c, rng.choice((0x19, 0x12)))
        if kind == 'antqueen' and r() < 0.04:                   # hit while biting, clip flag 8 or not
            mem.w16(c + 0x232, 6)
            mem.w16(c + 0x11A, rng.choice((0, 8, 0x18)))
            do(set_key, c, 0x12)
        if r() < 0.03:                                          # constructed again, alive or not
            construct()
        if tick == 0:                                           # a burst of constructions: every
            for _ in range(60):                                 # prefix, set, owner and element roll
                construct()
        if mem.s16(c + 0x232) == 0x14 and r() < 0.2 or mem.u32(c + 0xC) & 0x4000 and r() < 0.3:
            driver.respawn()
    if rig.unknown:
        bad['calls'].append('calls to addresses that are neither real nor known stubs: %s'
                            % {hex(a): n for a, n in rig.unknown.items()})
    text = '%s, machine %s' % (cls, 'B' if machine else 'A')
    count = serial[0]
    DC.report(name + ' calls', len(bad['calls']), count, 'callbacks in order with arguments; ' + text, bad['calls'])
    DC.report(name + ' writes', len(bad['writes']), count, 'bytes stored and their final values', bad['writes'])
    DC.report(name + ' seed', len(bad['seed']), count, 'shared seed and number of draws', bad['seed'])
    DC.report(name + ' result', len(bad['result']), count, 'returned values', bad['result'])
    DC.report(name + ' faults', len(bad['fault']), count,
              'calls that stopped on one side only (%d stopped on both, the same way)' % sum(both.values()),
              bad['fault'])
    return count, draws_by_entry


RUNS = tuple((kind, machine, 1) for kind in CLASSES for machine in (0, 1))


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
        else:
            elf = a
    if elf is None:
        for candidate in (os.path.join(ROOT, 'SLUS_209.73'), os.path.join(ROOT, 'local', 'SLUS_209.73')):
            if os.path.exists(candidate):
                elf = candidate
                break
    if elf is None or not os.path.exists(elf):
        print('difftest_combat_ctors: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != DC.EXPECTED_SHA256:
        print('difftest_combat_ctors: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    ticks = max(OPTIONS['ticks'] // 10, 1) if OPTIONS['quick'] else OPTIONS['ticks']
    RC.C.set_fpu(OPTIONS['fpu'])
    started = time.time()
    coverage, counts, draws = [None], {}, {}
    total = 0
    for index, (kind, machine, net) in enumerate(RUNS):
        name = '%s/%s' % (kind, 'B' if machine else 'A')
        if OPTIONS['filter'] and OPTIONS['filter'].lower() not in name.lower():
            continue
        n, d = run(elf, name, OPTIONS['seed'] + index, kind, machine, net, ticks, coverage, counts)
        total += n
        for key, value in d.items():
            draws[key] = draws.get(key, 0) + value
    print()
    print('calls compared per entry point / calls with any mismatch / own and shared draws seen')
    for key in sorted(counts):
        print('  %-24s %7d / %d / %d' % (key, counts[key][0], counts[key][1], draws.get(key, 0)))
    if coverage[0] is not None:
        print('coverage of the original as executed here (basic blocks, instructions):')
        for part in BODIES:
            b, bt, i, it = coverage[0].numbers(part)
            if not i:
                continue
            print('  %-24s blocks %4d of %4d  instructions %4d of %4d' % (part, b, bt, i, it))
            if OPTIONS['verbose'] and b != bt:
                print('      never entered: %s' % ' '.join('%06x' % a for a in coverage[0].missing(part)))
    print('%d calls compared in %.0f s' % (total, time.time() - started))
    return 0 if all(ok for _name, ok in DC.RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
