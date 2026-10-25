#!/usr/bin/env python3
"""difftest_antqueen_run.py - compare tools/ref_antqueen_run.py with the game's own code:
the whole of AntQueen_run (every state of its switch) and AntQueen_pickFlyDest.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_antqueen_run.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                            [--ticks N] [-v] [--trace-first]

What is compared
    tools/difftest_combat_ctors.py's rig and world for the AntQueen class, WITHOUT the
    switch patch: the original AntQueen_run runs to its end.  Real underneath: the
    creature base (ref_creature, ref_arena_monsters, ref_monsters_1), AntQueen_ctor,
    AntQueen_setState with AntQueen_pickFlyDest REAL inside it,
    AntQueen_fadeBankTracks and AntQueen_updateBank.  Callbacks (recording stubs,
    answered by the scripted world): creature_canSeeObj, creature_findEnemyInCone,
    Creature_hitTargetAtReach, Creature_hitTargetOrPlayerInArc, Creature_applyKnockback,
    Creature_deadUpdate, terrain_height, pool_new, AntWave_ctor, the SkillPoisonWeapons
    slot 11, the anim calls.  Each call runs through the model first on a copy-on-write
    view of the same memory, and these must be equal: the calls with their arguments
    (the stack descriptor decoded), the bytes stored outside the stack, the shared seed
    with its draw count, the result.

Scenarios
    machine A and B, 'seed' and 'seed + 1': constructions, then ticks of the run, in any
    state the driver puts the queen in (all 26 and out-of-range numbers), with the
    timers +0xf4, +0x3d4 and +0x3d8 near the clock, the track count +0x118 around 4,
    clip flags, the stuck counter +0x2c4, the hit flag +0x3cc, targets present or not,
    sight answers biased all ways, and terrain heights inside and outside the
    flight-destination window.  Set-state requests between ticks, 0x17 often.
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
import ref_combat_ctors as CT                   # noqa: E402
import ref_antqueen_run as AQ                   # noqa: E402
import difftest_creature as DC                  # noqa: E402
import difftest_arena_monsters as DA            # noqa: E402
import difftest_monsters_1 as DM                # noqa: E402
import difftest_combat_ctors as DCT             # noqa: E402
from difftest_creature import Res, f32, M32     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = DC.OPTIONS
OPTIONS.update({'seed': 20973, 'ticks': 3000})

BODIES = {
    'AntQueen_run': (0x236F78, 0x2378F4),
    'AntQueen_pickFlyDest': (0x238150, 0x238360),
    'AntQueen_fadeBankTracks': (0x2385DC, 0x238654),
    'AntQueen_updateBank': (0x238448, 0x2385DC),
    'AntQueen_setState': (0x237918, 0x238150),
}

# The AntQueen run, its two bank helpers and pickFlyDest run for real here.
DCT.REAL.update({AQ.ANTQUEEN_RUN, AQ.PICK_FLY_DEST, AQ.FADE_BANK, AQ.UPDATE_BANK})
REAL = DCT.REAL

ENTRIES = dict(DCT.ENTRIES)
ENTRIES['AntQueen_run'] = (0x236F78, 'c', 'n', 'antqueen_run')
ENTRIES['AntQueen_pickFlyDest'] = (0x238150, 'ic', 'i', 'pick_fly_dest_entry')   # out = the argument buffer

STATES = list(range(0, 0x1A)) + [0x1A, 0x1B, 0x40, 0x7FFF, 0x8000, 0xFFFF]
REQUESTS = list(range(0, 0x1A)) + [0x17] * 6 + [8, 8, 9, 10, 3, 3, 0x18, 0x19, 0x19, 6, 7]


class World(DCT.World):
    """The ctors world for the AntQueen, plus the SkillPoisonWeapons pointer, the
    callbacks the switch reaches, and target positions that put pickFlyDest's probe
    anywhere."""

    def build(self, rng):
        DCT.World.build(self, rng)
        self.mem.w32(AQ.G_SKILL_POISONWEAPONS, self.skill)
        self.wave_blocks = [self.emu.alloc(AQ.WAVE_SIZE) for _ in range(2)]
        self.pool.setdefault(AQ.WAVE_SIZE, [])
        self.pool[AQ.WAVE_SIZE] = self.wave_blocks
        for b in self.wave_blocks:
            self.pool_size[b] = AQ.WAVE_SIZE
        self.heights = (0.0, 0.0, 0.0, 3.0, -8.0, 11.0, 11.9, 12.0, -11.9, -12.0, -13.0, 24.0, -30.0, 60.0)

    def on_terrain_height(self, args, view, rng):
        return Res(f=f32(DC.fl(args[1][2]) + rng.choice(self.heights)))

    def on_Creature_hitTargetOrPlayerInArc(self, args, view, rng):
        return Res(rng.choice((0, 1)))

    def on_AntWave_ctor(self, args, view, rng):
        view.poke(args[0] + 0x48, 4, 0x0050D298)
        return Res()

    def on_Skill_v11(self, args, view, rng):
        return Res(rng.choice((0, 3, 10, 40, 133, 0x12345)))


class Rig(DCT.Rig):
    def __init__(self, elf, seed, kind, machine, net):
        self.rng = random.Random(seed)
        emu = self.emu = EE(elf, fpu_model=OPTIONS['fpu'])
        self.world = World(emu, self.rng, kind, machine, net)
        emu.follow = self.real = DCT.RealSet()
        self.calls, self.buffers, self.unknown = [], {}, {}
        self.eview = DC.EmuView(emu)
        self.script_rng = None
        self.names = {}

        def add(addr, name, ext):
            if addr in REAL:
                return
            assert self.names.setdefault(addr, name) == name, (hex(addr), name, self.names[addr])
            emu.stub(addr, function=self.make_stub(name, ext), name=name)

        for name, ext in AQ.EXTERNALS.items():
            if ext.addr:
                add(ext.addr, name, ext)
            elif name in self.world.stub_addr:
                add(self.world.stub_addr[name], name, ext)
        for addr, name in list(self.world.stub_name.items()) + list(self.world.addr_name.items()):
            if addr not in self.names:
                add(addr, name, AQ.EXTERNALS.get(name) or RC.Ext(0, 'p', 0, 'n'))
        for _entry, test, _method in CT.RUN_PROLOGUES.values():     # Skeleton and Soul only
            if _entry != AQ.ANTQUEEN_RUN:
                emu.patch(test, DCT.ADDIU_V0_ZERO)
        self.partial, self.partial_ops = [], {}
        for start, end in list(DC.BODIES.values()) + list(DA.BODIES.values()) + list(DM.BODIES.values()) + \
                list(DCT.BODIES.values()) + list(BODIES.values()):
            for pc in range(start, end, 4):
                w = emu.mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E) and pc not in self.partial_ops:
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))

    def decode(self, name, ext, emu):
        """The stack descriptor of hitTargetOrPlayerInArc sits in t3, the eighth integer
        register: difftest_monsters_1's decoding handles any position."""
        return DM.Rig.decode(self, name, ext, emu)

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                ret = res.ret & (RC.M64 if AQ.EXTERNALS[name].ret == 'q' else M32)
                return AQ.shape_result(name, args, ret, res.f & M32, res.outs)
            return answer

    def compare(self, key, args, call_seed, trace=None):
        saved = DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks
        DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks = ENTRIES, Model, Rig.Callbacks
        try:
            out = DM.Rig.compare(self, key, args, call_seed, trace)
        finally:
            DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks = saved
        if key == 'AntQueen_pickFlyDest' and not out['fault'] and out['both_fault'] is None:
            mem = self.emu.mem
            got = tuple(mem.u32(args[0] + 4 * k) for k in range(3))
            if got != Model.last[0]:
                out['result'] = 'original %s model %s' % (got, Model.last[0])
        return out


class Model(AQ.Model):
    """The model, keeping the last flight destination for the standalone entry."""
    last = [None]

    def pick_fly_dest_entry(self, out, q):
        result = AQ.Model.pick_fly_dest_entry(self, out, q)
        Model.last[0] = self.dest
        return result


class Coverage(DC.Coverage):
    def __init__(self, mem):
        self.parts = {name: (start, end) + DC.analyse(mem, start, end) for name, (start, end) in BODIES.items()}
        self.pcs = set()


class Driver(DCT.Driver):
    def between_class(self):
        DCT.Driver.between_class(self)
        rng, mem, world = self.rng, self.mem, self.world
        c, r = world.C, rng.random
        clock = mem.u32(c + 0x300)
        if r() < 0.12:
            mem.w16(c + 0x232, rng.choice(STATES))
        for off, p in ((0xF4, 0.08), (0x3D4, 0.1), (0x3D8, 0.04)):
            if r() < p:
                mem.w32(c + off, (clock + rng.choice((-5, -1, 0, 1, 2, 30, 120, 121, 400))) & M32)
        if mem.s16(c + 0x232) == 0x19 and r() < 0.3:              # the wave frame: clock == +0xf4 - 120
            mem.w32(c + 0xF4, (clock + 120 + rng.choice((0, 0, 1))) & M32)
        if r() < 0.1:
            mem.w8(c + 0x118, rng.choice((0, 1, 2, 3, 3, 4, 4, 5, 0x80)))
        if r() < 0.08:                                           # track clips: the bank words or others
            definition = mem.u32(c + 0x24)
            words = [mem.u32(definition + off) for off in (0xB4, 0x44, 0xBC, 0x4C, 0x7C, 0x3C)]
            for k in range(5):
                mem.w32(c + 0x11C + 32 * k, rng.choice(words))
        if r() < 0.08:
            mem.w16(c + 0x11A, rng.choice(DM.ANIM_FLAGS))
        if r() < 0.06:
            mem.w32(c + 0x2C4, rng.choice((0, 5, 30, 31, 32, 0xFFFFFFFF)))
        if r() < 0.06:
            mem.w32(c + 0x3CC, rng.choice((0, 0, 1)))
        if r() < 0.05:
            mem.w32(RC.G_LEVEL_MONSTER_LEVEL, f32(rng.choice((1.0, 2.5, 7.9, 30.0))))
        if r() < 0.04:                                           # stunned / rooted
            mem.w16(c + rng.choice((0x314, 0x31C)), rng.choice((0, 0, 3)))
        if r() < 0.04:                                           # the queen's flight destination
            for k in range(3):
                mem.wf32(c + 0x104 + 4 * k, rng.uniform(1500, 2500) if k < 2 else 10.0)
        if r() < 0.03:                                           # target anywhere near or far
            node = mem.u32(c + 0x234)
            if node:
                obj = mem.u32(node + 0xC)
                mem.wf32(obj + 0x10, 2000.0 + rng.uniform(-900, 900))
                mem.wf32(obj + 0x14, 3000.0 + rng.uniform(-900, 900))
        if r() < 0.03:
            mem.w16(c + 0x38, rng.randrange(0x10000))


def run(elf, name, seed, machine, ticks, coverage, counts):
    kind = 'antqueen'
    rig = Rig(elf, seed, kind, machine, 1)
    driver = Driver(rig)
    world, mem, rng = rig.world, rig.emu.mem, rig.rng
    info = DCT.CLASSES[kind]
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
        values = {'c': c, 't': rng.choice(world.type_names), 'v': pos, 'f': facing, 'p': world.props, 'x': 0}
        do('AntQueen_ctor', *[values[k] for k in info['order']])
        hp = rng.choice((300.0, 300.0, 1200.0))
        mem.wf32(c + 0x228, hp)
        mem.wf32(c + 0x22C, hp)
        mem.w8(c + 0x231, 0)
        mem.w32(c + 0xC8, 0)

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
        if r() < 0.04:
            attacker = rng.choice(world.others + world.players + [0])
            do('Creature_takeDamage', c, attacker, rng.choice(DC.DAMAGE_FLAGS),
               f32(rng.choice((0.0, 3.0, 20.0, 60.0, 400.0))))
        do('AntQueen_run', c)
        if r() < 0.25:
            do('AntQueen_setState', c, rng.choice(REQUESTS))
        if r() < 0.04:                                          # the helper on its own
            do('AntQueen_pickFlyDest', world.argbuf, c)
        if r() < 0.005:
            construct()
        if mem.s16(c + 0x232) == 0x14 and r() < 0.1 or mem.u32(c + 0xC) & 0x4000 and r() < 0.3:
            driver.respawn()
    if rig.unknown:
        bad['calls'].append('calls to addresses that are neither real nor known stubs: %s'
                            % {hex(a): n for a, n in rig.unknown.items()})
    text = 'AntQueen run, machine %s' % ('B' if machine else 'A')
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
        print('difftest_antqueen_run: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != DC.EXPECTED_SHA256:
        print('difftest_antqueen_run: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    ticks = max(OPTIONS['ticks'] // 10, 1) if OPTIONS['quick'] else OPTIONS['ticks']
    RC.C.set_fpu(OPTIONS['fpu'])
    started = time.time()
    coverage, counts, draws = [None], {}, {}
    total = 0
    for index, machine in enumerate((0, 1, 0, 1)):
        name = 'antqueen/%s%d' % ('B' if machine else 'A', index // 2)
        n, d = run(elf, name, OPTIONS['seed'] + index, machine, ticks, coverage, counts)
        total += n
        for key, value in d.items():
            draws[key] = draws.get(key, 0) + value
    print()
    print('calls compared per entry point / calls with any mismatch / own and shared draws seen')
    for key in sorted(counts):
        print('  %-24s %7d / %d / %d' % (key, counts[key][0], counts[key][1], draws.get(key, 0)))
    print('coverage of the original as executed here (basic blocks, instructions):')
    for part in BODIES:
        b, bt, i, it = coverage[0].numbers(part)
        print('  %-24s blocks %4d of %4d  instructions %4d of %4d' % (part, b, bt, i, it))
        if OPTIONS['verbose'] and b != bt:
            print('      never entered: %s' % ' '.join('%06x' % a for a in coverage[0].missing(part)))
    print('%d calls compared in %.0f s' % (total, time.time() - started))
    return 0 if all(ok for _name, ok in DC.RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
