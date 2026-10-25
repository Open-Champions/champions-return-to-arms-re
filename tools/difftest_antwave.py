#!/usr/bin/env python3
"""difftest_antwave.py - compare tools/ref_antwave.py with the game's own code: the AntWave
an AntQueen in state 0x19 builds, its constructor and its own slots (run, draw, destructor),
run frame after frame from the queen's spawn to the wave's deletion.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_antwave.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                       [--ticks N] [-v] [--trace-first]

What is compared
    tools/difftest_antqueen_run.py's rig and world (AntQueen_run real to its end, the
    creature base real underneath), with AntWave_ctor 0x238654 REAL inside the queen's
    state 0x19 instead of a stub, and the AntWave's slots REAL: AntWave_run 0x238938,
    AntWave_draw 0x2387d0, AntWave_dtor 0x238750 with Creature_dtor 0x117128 and
    GameObject_dtor 0x14cf90 underneath (tools/ref_combat_monsters.py's bodies).  Under the
    wave's run, Creature_run, Creature_moveTo with Creature_moveBy and its touch slots
    (6, 7, 11: base bodies of the AntWave table) and the target's Creature_takeDamage
    (slot 2 of the base table) are real; a target carrying the Player table answers slot 2
    through a recording stub.  Each call runs through ref_antwave.Model first on a
    copy-on-write view; equal must be the calls to everything outside the models with their
    arguments, the bytes stored outside the stack, the shared seed 0x404464 with its draw
    count, the result.

Scenarios
    machine A and B, 'seed' and 'seed + 1'.  The queen is built by AntQueen_ctor and runs
    every tick; the driver puts her in state 0x19 with a target and the wave frame
    (+0xf4 = clock + 121) often, so she spawns waves through pool_new (blocks of 0x3d8,
    refused sometimes).  Every live wave then runs each tick (and draws on some ticks)
    until its run deletes it: its lifetime +0x3cc passes, or its target handle +0x3d0 is
    gone (the driver drops it sometimes, as the target's death would).  The driver moves
    targets onto waves and wave clocks onto multiples of 60, so the damage test fires,
    changes the target's table (base or Player), and enters AntWave_ctor directly
    (lifetimes 0-600, any facing, targets of any radius) and AntWave_dtor with flags 0-3.
"""
import hashlib
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_ctors2 as CT2                 # noqa: E402
import ref_antwave as AW                        # noqa: E402
import difftest_creature as DC                  # noqa: E402
import difftest_monsters_1 as DM                # noqa: E402
import difftest_combat_ctors as DCT             # noqa: E402
import difftest_antqueen_run as DAQ             # noqa: E402  (adds the AntQueen run bodies to DCT.REAL)
from difftest_creature import Res, f32, M32     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = DC.OPTIONS
OPTIONS.update({'seed': 20973, 'ticks': 3000})

DCT.REAL.update(set(CT2.MODELLED.values()) | set(AW.EXECUTED.values()))
REAL = DCT.REAL

BODIES = {
    'AntWave_ctor': (0x238654, 0x238750),
    'AntWave_dtor': (0x238750, 0x2387D0),
    'AntWave_draw': (0x2387D0, 0x238938),
    'AntWave_run': (0x238938, 0x238A8C),
    'AntQueen_run': DAQ.BODIES['AntQueen_run'],
}
SITE_HIT, SITE_LOST, SITE_EXPIRED = 0x238A18, 0x238A74, 0x238A4C     # the three virtual calls of the run

OWN_DRAW_CALLERS = {'AntWave_draw': BODIES['AntWave_draw'], 'Creature_moveTo': (0x114510, 0x114D9C)}
ENTRIES = dict(DAQ.ENTRIES)
ENTRIES.update({
    'AntWave_ctor': (AW.ANTWAVE_CTOR, 'civii', 'n', 'antwave_ctor'),
    'AntWave_run': (AW.ANTWAVE_RUN, 'c', 'n', 'antwave_run'),
    'AntWave_draw': (AW.ANTWAVE_DRAW, 'c', 'n', 'antwave_draw'),
    'AntWave_dtor': (AW.ANTWAVE_DTOR, 'ci', 'n', 'antwave_dtor'),
})
_QueenWorld = DAQ.World


class World(_QueenWorld):
    """The AntQueen world, with wave blocks handed out only when free, the Player table's
    own slots as named stubs, and the spell table's slot 1 for Creature_dtor."""

    def build(self, rng):
        _QueenWorld.build(self, rng)
        mem = self.mem
        self.wave_blocks = [self.emu.alloc(AW.WAVE_SIZE) for _ in range(4)]
        self.pool[AW.WAVE_SIZE] = self.wave_blocks
        for b in self.wave_blocks:
            self.pool_size[b] = AW.WAVE_SIZE
        self.live = set()
        self.handed = []
        for slot in range(1, 40):
            fn = mem.u32(CT2.VT_PLAYER + 8 * slot + 4)
            if fn not in REAL:
                self.addr_name.setdefault(fn, 'Creature.v%d' % slot)
        mem.w32(self.vt_spell + 8 * 1 + 4, self.stub_for('Spell.v1'))

    def on_pool_new(self, args, view, rng):
        if args[0] != AW.WAVE_SIZE:
            return _QueenWorld.on_pool_new(self, args, view, rng)
        free = [b for b in self.wave_blocks if b not in self.live]
        if not free or rng.random() < 0.08:
            return Res(0)
        block = rng.choice(free)
        for off in range(0, AW.WAVE_SIZE, 4):                       # the pool zero-fills
            view.poke(block + off, 4, 0)
        self.handed.append(block)
        return Res(block)


class Rig(DAQ.Rig):
    def __init__(self, elf, seed, kind, machine, net):
        DAQ.World = World
        try:
            DAQ.Rig.__init__(self, elf, seed, kind, machine, net)
        finally:
            DAQ.World = _QueenWorld
        emu = self.emu
        for name, ext in AW.EXTERNALS.items():                      # the destructor chain's call-outs
            addr = ext.addr or self.world.stub_addr.get(name)
            if not addr or addr in REAL:
                continue
            if self.names.get(addr) not in (None, name):
                continue
            self.names[addr] = name
            emu.stub(addr, function=self.make_stub(name, ext), name=name)
        assert emu.mem.u32(AW.VT_ANTWAVE + 8 * 4 + 4) == AW.ANTWAVE_RUN
        assert emu.mem.u32(AW.VT_ANTWAVE + 8 * 5 + 4) == AW.ANTWAVE_DRAW
        assert emu.mem.u32(AW.VT_ANTWAVE + 8 * 1 + 4) == AW.ANTWAVE_DTOR
        self.sites = {SITE_HIT: 0, SITE_LOST: 0, SITE_EXPIRED: 0}
        for pc in self.sites:
            emu.hook(pc, self.counter(pc))
        self.own_draws = {}                                         # GameObject_rand by the caller's body
        emu.hook(RC.MODELLED['GameObject_rand'], self.own_draw)

    def own_draw(self, emu):
        ra = emu.r[31] & M32
        for name, (lo, hi) in OWN_DRAW_CALLERS.items():
            if lo <= ra < hi:
                self.own_draws[name] = self.own_draws.get(name, 0) + 1
                return
        self.own_draws['other'] = self.own_draws.get('other', 0) + 1

    def counter(self, pc):
        def note(emu):
            self.sites[pc] += 1
        return note

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                ret = res.ret & (RC.M64 if AW.EXTERNALS[name].ret == 'q' else M32)
                return AW.shape_result(name, args, ret, res.f & M32, res.outs)
            return answer

    def compare(self, key, args, call_seed, trace=None):
        saved = DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks
        DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks = ENTRIES, AW.Model, Rig.Callbacks
        try:
            return DM.Rig.compare(self, key, args, call_seed, trace)
        finally:
            DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks = saved


class Coverage(DC.Coverage):
    def __init__(self, mem):
        self.parts = {name: (start, end) + DC.analyse(mem, start, end) for name, (start, end) in BODIES.items()}
        self.pcs = set()


def run(elf, name, seed, machine, ticks, coverage, counts, lives):
    rig = Rig(elf, seed, 'antqueen', machine, 1)
    driver = DAQ.Driver(rig)
    world, mem, rng = rig.world, rig.emu.mem, rig.rng
    info = DCT.CLASSES['antqueen']
    if coverage[0] is None:
        coverage[0] = Coverage(mem)
    cov = coverage[0]
    c = world.C
    bad = {'calls': [], 'writes': [], 'seed': [], 'result': [], 'fault': []}
    both = {}
    serial = [0]
    draws_by_entry = {}
    tick = [0]
    born, natural = {}, {}

    def do(key, *args):
        serial[0] += 1
        result = rig.compare(key, tuple(args), seed * 1000003 + serial[0], trace=cov.pcs)
        row = counts.setdefault(key, [0, 0])
        row[0] += 1
        failed = False
        for prop in ('fault', 'calls', 'writes', 'seed', 'result'):
            if result[prop]:
                failed = True
                bad[prop].append('tick %d %s(%s): %s' % (tick[0], key, ', '.join(
                    '%x' % a if isinstance(a, int) else str(a) for a in args), result[prop]))
        if result['both_fault'] is not None:
            both[result['both_fault']] = both.get(result['both_fault'], 0) + 1
        if result.get('draws'):
            draws_by_entry[key] = draws_by_entry.get(key, 0) + result['draws']
        if key.startswith('AntWave'):
            callees = counts.setdefault('_callees', {}).setdefault(key, {})
            for n, _a in result['emu_calls']:
                callees[n] = callees.get(n, 0) + 1
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

    def freed(result):
        return {args[0] for n, args in result['emu_calls'] if n == 'pool_free'}

    def construct():
        world.clear_creature()
        pos = (f32(2000.0 + rng.uniform(-50, 50)), f32(3000.0 + rng.uniform(-50, 50)), f32(10.0))
        facing = rng.choice((rng.randrange(0x10000), 0xFFFF8000 | rng.randrange(0x8000)))
        values = {'c': c, 't': rng.choice(world.type_names), 'v': pos, 'f': facing, 'p': world.props, 'x': 0}
        do('AntQueen_ctor', *[values[k] for k in info['order']])
        mem.wf32(c + 0x228, 300.0)
        mem.wf32(c + 0x22C, 300.0)
        mem.w8(c + 0x231, 0)
        mem.w32(c + 0xC8, 0)

    def bury(w, how):
        world.live.discard(w)
        if w in born:
            lives.append((born.pop(w), how))

    def targets():
        return world.others[:4] + world.players

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
        # the queen: the wave frame of state 0x19 with a target, often
        clock = mem.u32(c + 0x300)
        if r() < 0.25:
            mem.w16(c + 0x232, 0x19)
            mem.w32(c + 0xF4, (clock + 121) & M32)
            mem.w32(c + 0x234, world.nodes[rng.choice(targets())])
            mem.w8(c + 0x231, 0)
        world.handed = []
        before = set(world.live)
        do('AntQueen_run', c)
        for b in set(world.handed):
            if mem.u32(b + 0x48) == AW.VT_ANTWAVE and b not in before:
                world.live.add(b)
                born[b] = 0
                natural[b] = r() < 0.5                                  # left alone to the end of its life
                counts['_spawned'] = counts.get('_spawned', 0) + 1
        # a wave built directly: any target, lifetime, facing
        free = [b for b in world.wave_blocks if b not in world.live]
        if free and r() < 0.03:
            w = rng.choice(free)
            for off in range(0, AW.WAVE_SIZE, 4):
                mem.w32(w + off, rng.getrandbits(32) if r() < 0.1 else 0)
            target = rng.choice(targets())
            mem.wf32(target + 0x1C, rng.choice((0.0, 8.0, 16.0, 30.0, 45.0)))
            pos = tuple(mem.u32(c + 0x10 + 4 * k) for k in range(3))
            do('AntWave_ctor', w, target, pos, rng.choice((0, 0x4000, 0xFFFF8000, rng.randrange(0x10000), 0x12345)),
               rng.choice((0, 1, 59, 60, 120, 600, 600, 0xFFFFFFFF)))
            world.live.add(w)
            born[w] = 0
            natural[w] = False
        # every live wave: the rest of the game, then draw and run
        for w in sorted(world.live):
            wclock = mem.u32(w + 0x300)
            node = mem.u32(w + 0x3D0)
            tamper = not natural.get(w)
            if tamper and node and r() < 0.004:                         # its target died: the handle is gone
                mem.w32(w + 0x3D0, 0)
            elif node and r() < 0.1:                                    # the target walks into the wave
                obj = mem.u32(node + 0xC)
                reach = mem.f32(w + 0x1C) * rng.choice((0.2, 0.9, 0.99, 1.0, 1.01, 1.5))
                for k, d in enumerate((reach * 0.6, reach * 0.8, 0.0)):
                    mem.wf32(obj + 0x10 + 4 * k, mem.f32(w + 0x10 + 4 * k) + d * rng.choice((1, -1)))
            if node and r() < 0.05:
                obj = mem.u32(node + 0xC)
                mem.w32(obj + 0x48, rng.choice((world.vt_base, world.vt_base, world.vt_hooked, CT2.VT_PLAYER)))
            if tamper and r() < 0.08:                                   # the next tick is a damage tick
                mem.w32(w + 0x300, (wclock - wclock % 60 + 59) & M32)
            if tamper and r() < 0.01:                                   # the lifetime runs out soon
                mem.w32(w + 0x3CC, (wclock + rng.choice((-1, 0, 1, 2))) & M32)
            if r() < 0.5:
                do('AntWave_draw', w)
            if tamper and r() < 0.01:                                   # destroyed from outside
                do('AntWave_dtor', w, rng.choice((0, 1, 2, 3)))
                bury(w, 'outside')
                continue
            node = mem.u32(w + 0x3D0)
            result = do('AntWave_run', w)
            born[w] += 1
            if w in freed(result):
                bury(w, 'lost' if not node else ('expired, left alone' if natural.get(w) else 'expired'))
        if r() < 0.005:
            construct()
        if mem.s16(c + 0x232) == 0x14 and r() < 0.1 or mem.u32(c + 0xC) & 0x4000 and r() < 0.3:
            driver.respawn()
    if rig.unknown:
        bad['calls'].append('calls to addresses that are neither real nor known stubs: %s'
                            % {hex(a): n for a, n in rig.unknown.items()})
    text = 'AntQueen and AntWave, machine %s' % ('B' if machine else 'A')
    count = serial[0]
    DC.report(name + ' calls', len(bad['calls']), count, 'callbacks in order with arguments; ' + text, bad['calls'])
    DC.report(name + ' writes', len(bad['writes']), count, 'bytes stored and their final values', bad['writes'])
    DC.report(name + ' seed', len(bad['seed']), count, 'shared seed and number of draws', bad['seed'])
    DC.report(name + ' result', len(bad['result']), count, 'returned values', bad['result'])
    DC.report(name + ' faults', len(bad['fault']), count,
              'calls that stopped on one side only (%d stopped on both, the same way)' % sum(both.values()),
              bad['fault'])
    for k, n in rig.own_draws.items():
        counts.setdefault('_own', {})
        counts['_own'][k] = counts['_own'].get(k, 0) + n
    for pc, n in rig.sites.items():
        counts.setdefault('_sites', {})
        counts['_sites'][pc] = counts['_sites'].get(pc, 0) + n
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
        print('difftest_antwave: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != DC.EXPECTED_SHA256:
        print('difftest_antwave: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    ticks = max(OPTIONS['ticks'] // 10, 1) if OPTIONS['quick'] else OPTIONS['ticks']
    RC.C.set_fpu(OPTIONS['fpu'])
    started = time.time()
    coverage, counts, draws, lives = [None], {}, {}, []
    total = 0
    for index, machine in enumerate((0, 1, 0, 1)):
        name = 'antwave/%s%d' % ('B' if machine else 'A', index // 2)
        n, d = run(elf, name, OPTIONS['seed'] + index, machine, ticks, coverage, counts, lives)
        total += n
        for key, value in d.items():
            draws[key] = draws.get(key, 0) + value
    sites = counts.pop('_sites', {})
    own = counts.pop('_own', {})
    callees = counts.pop('_callees', {})
    spawned = counts.pop('_spawned', 0)
    print()
    print('calls compared per entry point / calls with any mismatch / shared draws seen')
    for key in sorted(counts):
        print('  %-24s %7d / %d / %d' % (key, counts[key][0], counts[key][1], draws.get(key, 0)))
    print('waves the queen spawned: %d; target hits (slot 2 at 0x238a18): %d; deletions for a lost target: %d, '
          'for the lifetime: %d' % (spawned, sites.get(SITE_HIT, 0), sites.get(SITE_LOST, 0), sites.get(SITE_EXPIRED, 0)))
    print('own-generator draws (GameObject_rand) by caller: %s' % ', '.join('%s %d' % kv for kv in sorted(own.items())))
    for key in sorted(callees):
        print('  call-outs of %s (original side): %s' % (key, ', '.join('%s %d' % kv for kv in sorted(callees[key].items()))))
    if lives:
        print('wave lives seen to their end: %d; runs of each from its constructor to its deletion, by end:' % len(lives))
        for how in sorted({x for _n, x in lives}):
            spans = sorted(n for n, x in lives if x == how)
            print('  %-20s %4d waves, runs min %d, median %d, max %d' % (how, len(spans), spans[0],
                                                                       spans[len(spans) // 2], spans[-1]))
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
