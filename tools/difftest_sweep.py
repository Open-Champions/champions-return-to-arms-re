#!/usr/bin/env python3
"""difftest_sweep.py - compare tools/ref_sweep.py with the game's own code:
world_countLivingNonplayerCreaturesInBox 0x108970 and creature_objInArcRange 0x10c410,
the two callees of creature_allyInLineOfFire that tools/difftest_skeleton_run.py left as
recording stubs.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_sweep.py [path/to/SLUS_209.73] [--quick] [--seed N] [--ticks N]
                                     [-v] [--trace-first]

What is compared
    tools/difftest_skeleton_run.py's whole run (rig, world, driver, every entry), with the
    two bodies REAL inside Skeleton_run's line-of-fire sweep and ref_sweep.Model as the
    model.  Between ticks both bodies are also entered directly: the box count on the
    creature's or another object's position with half sizes 0 to 300, and the arc test
    on every other object with arcs 0, 0x4000, 0x7fff, 0x8000 and ranges 0 to 600.  The
    same properties as there must be equal: calls with their arguments, stores outside
    the stack, the shared seed with its draw count, the result.
"""
import os
import random
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_sweep as SW                          # noqa: E402
import difftest_creature as DC                  # noqa: E402
import difftest_skeleton_run as DS              # noqa: E402
from difftest_creature import f32               # noqa: E402

DS.REAL.update(SW.EXECUTED.values())
DS.BODIES.update({
    'world_countLivingNonplayerCreaturesInBox': (0x108970, 0x108A60),
    'creature_objInArcRange': (0x10C410, 0x10C5B8),
})
DS.ENTRIES.update({
    'world_countLivingNonplayerCreaturesInBox': (0x108970, 'vf', 'i', 'count_living_entry'),
    'creature_objInArcRange': (0x10C410, 'ciif', 'i', 'obj_in_arc_range_entry'),
})


class Model(DS.Model, SW.Model):
    """difftest_skeleton_run's model (the lead-point keeper) over ref_sweep's."""


DS.Model = Model
DIRECT = {'bad': [], 'counts': {}, 'cov': None}


class Driver(DS.Driver):
    """difftest_skeleton_run's driver; after its moves, the two bodies entered directly."""

    def between_class(self):
        super().between_class()
        rng, mem, world, rig = self.rng, self.mem, self.world, self.rig
        c, r = world.C, rng.random
        cov = DIRECT['cov'] if DIRECT['cov'] is not None else set()
        cases = []
        if r() < 0.1:                       # crowds: the sweep needs 3 or 4 living non-players
            for other in world.others:
                mem.w32(other + 0xC, (mem.u32(other + 0xC) & ~0x68 | rng.choice((0x20, 0x20, 0x20, 0x60, 0x28)))
                        & 0xFFFFFFFF)
        if r() < 0.12:
            where = rng.choice([c] + world.others[:4] + world.players[:2])
            centre = tuple(mem.u32(where + 0x10 + 4 * k) for k in range(3))
            if r() < 0.2:
                centre = tuple(f32(v) for v in (rng.uniform(-4000, 4000), rng.uniform(-4000, 4000), 0.0))
            half = f32(rng.choice((0.0, 12.0, 21.0, 31.5, 100.0, 300.0)))
            cases.append(('world_countLivingNonplayerCreaturesInBox', (centre, half)))
        if r() < 0.12:
            other = rng.choice([0] + world.others[:4] + world.players[:2])
            if other and r() < 0.5:
                heading = mem.s16(c + 0x38) + rng.choice((0, 2000, -2000, 0x3FFF, 0x4000, -0x4000,
                                                           rng.randrange(0x10000)))
                dist = rng.choice((10.0, 40.0, 54.0, 299.0, 301.0, 700.0))
                mem.w32(other + 0x10, C.add(mem.u32(c + 0x10), C.mul(C.cos16(heading), f32(dist))))
                mem.w32(other + 0x14, C.add(mem.u32(c + 0x14), C.mul(C.sin16(heading), f32(dist))))
            arc = rng.choice((0, 0x4000, 0x4000, 0x7FFF, 0x8000, 0xFFFF, 2000))
            reach = f32(rng.choice((0.0, 54.0, 300.0, 300.0, 600.0)))
            cases.append(('creature_objInArcRange', (c, other, arc, reach)))
        for key, args in cases:
            seed = rng.getrandbits(32)
            result = rig.compare(key, args, seed, trace=cov)
            row = DIRECT['counts'].setdefault(key, [0, 0])
            row[0] += 1
            problems = [(p, result[p]) for p in ('fault', 'calls', 'writes', 'seed', 'result') if result[p]]
            if problems:
                row[1] += 1
                DIRECT['bad'].append('%s(%s): %s' % (key, args, problems))
                if DS.OPTIONS['trace_first']:
                    print('first mismatch: %s %s' % (key, problems))
                    for call in result['model_calls']:
                        print('  model    ' + DC.fmt_call(call))
                    for call in result['emu_calls']:
                        print('  original ' + DC.fmt_call(call))
                    sys.exit(1)


DS.Driver = Driver


class Coverage(DS.Coverage):
    def __init__(self, mem):
        super().__init__(mem)
        DIRECT['cov'] = self.pcs


DS.Coverage = Coverage


def main(argv):
    status = DS.main(argv)
    if DIRECT['counts']:
        print('entered directly / with any mismatch:')
        for key, (n, bad) in sorted(DIRECT['counts'].items()):
            print('  %-42s %6d / %d' % (key, n, bad))
        total = sum(n for n, _b in DIRECT['counts'].values())
        DC.report('direct entries', len(DIRECT['bad']), total, 'the two bodies entered directly', DIRECT['bad'])
        if DIRECT['bad']:
            status = 1
    return status


if __name__ == '__main__':
    random.seed(0)
    sys.exit(main(sys.argv[1:]))
