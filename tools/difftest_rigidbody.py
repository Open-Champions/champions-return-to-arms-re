#!/usr/bin/env python3
"""difftest_rigidbody.py - compare tools/ref_rigidbody.py with the game's own code:
rigidbody_init 0x1682f0, rigidbody_updateDerived 0x167a58, and under PhProp_initPhysics
0x155110 the chain quat_fromMat3 0x164330 -> quat_normalize 0x166550 -> updateDerived, all
four running for real (difftest_phprop stubs them).

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_rigidbody.py [path/to/SLUS_209.73] [--seed N] [--cases N] [-v]

Entries
    init      rigidbody_init on a block of random words, mass 0.25-8, factor 0.5-2, box sizes
              of both signs, now and then zero (the inverse inertia then divides by zero)
    derived   rigidbody_updateDerived on random blocks: orientation unnormalised, small, huge,
              zero; inertia and momentum of both signs
    physics   PhProp_initPhysics on the difftest_phprop blocks with the four bodies above
              real instead of stubs, and +0x110 holding a rotation matrix, a perturbed one or
              random floats.  Equal must be: the calls to everything still stubbed, every byte
              stored outside the stack (the body included), and both seeds.
Each case compares the bytes stored (by either side) and both seeds' final words.
"""
import hashlib
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE                            # noqa: E402
import ref_core as C                             # noqa: E402
import ref_creature as RC                        # noqa: E402
import ref_phprop as PP                          # noqa: E402
import ref_rigidbody as RB                       # noqa: E402
import difftest_combat_runtime as D              # noqa: E402
import difftest_creature as DC                   # noqa: E402
import difftest_phprop as DP                     # noqa: E402

EXPECTED_SHA256 = D.EXPECTED_SHA256
ROOT = D.ROOT
M32 = 0xFFFFFFFF
f32 = D.f32
OPTIONS = {'seed': 20973, 'cases': 3000, 'verbose': False}
BODIES = {'rigidbody_init': (0x1682F0, 0x168520), 'rigidbody_updateDerived': (0x167A58, 0x167C14),
          'quat_fromMat3': (0x164330, 0x164578), 'quat_normalize': (0x166550, 0x1665B4)}
BLOCK = 0x280


BASE_MODEL = PP.Model                   # DP.PP is this module: keep the original before it is replaced


class Model(RB.RigidMixin, BASE_MODEL):
    """difftest_phprop's model of the prop chain with the four bodies done, not recorded."""

    def call(self, name, *args):
        done, result = self.rigid_call(name, args)
        if done:
            return result
        return BASE_MODEL.call(self, name, *args)


class Bare(RB.RigidMixin):
    def __init__(self, mem):
        self.mem = mem
        self.writes = []

    def u32(self, a):
        return self.mem.load(a, 4)

    def w32(self, a, v):
        self.writes.append((a, 4, v & M32))
        self.mem.store(a, 4, v & M32)


def rf(rng, lo, hi):
    return f32(rng.uniform(lo, hi))


def quaternion(rng):
    r = rng.random()
    if r < 0.5:
        return [rf(rng, -1, 1) for _ in range(4)]
    if r < 0.7:
        return [rf(rng, -1e-3, 1e-3) for _ in range(4)]
    if r < 0.85:
        return [rf(rng, -1e4, 1e4) for _ in range(4)]
    if r < 0.9:
        return [0, 0, 0, C.ONE]
    return [f32(0.0)] * 4 if r < 0.92 else [rf(rng, -2, 2), 0, 0, rf(rng, -2, 2)]


class Direct:
    def __init__(self, elf):
        emu = self.emu = EE(elf, fpu_model='ps2')
        emu.div_zero = 'r5900'
        self.block = emu.alloc(BLOCK)
        self.pcs = set()

    def case(self, key, rng):
        emu, mem = self.emu, self.emu.mem
        body = self.block
        for off in range(0, BLOCK, 4):
            mem.w32(body + off, rng.getrandbits(32) if rng.random() < 0.3 else f32(rng.uniform(-50, 50)))
        mem.w32(RB.G_COSMETIC_SEED, rng.getrandbits(32))
        args = (body,)
        if key == 'init':
            size = lambda: rng.choice((0.0, rf(rng, -40, 40), rf(rng, 0.5, 200), rf(rng, 0.5, 200)))  # noqa: E731
            vals = (rng.choice((0.25, 0.5, 1.0, 1.0, 2.0, 8.0, rf(rng, 0.1, 9))),
                    rng.choice((0.5, 1.0, 1.0, 2.0, rf(rng, 0.1, 3))), size(), size(), size())
            vals = tuple(f32(v) for v in vals)
            for k, v in enumerate(vals):
                emu.f[12 + k] = v
        else:
            q = quaternion(rng)
            for k in range(4):
                mem.w32(body + 0x1C + 4 * k, q[k])
            for off in (4, 8, 0xC):
                mem.w32(body + off, f32(rng.choice((0.0, rng.uniform(-3, 3), rng.uniform(0.001, 2)))))
            vals = ()
        mview = D.ModelView(mem)
        model = Bare(mview)
        if key == 'init':
            model.rb_init(body, *vals)
        else:
            model.rb_update_derived(body)
        emu.reset_log()
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x200
        emu.call(RB.NAMES['rigidbody_init' if key == 'init' else 'rigidbody_updateDerived'], *args,
                 max_steps=200000)
        self.pcs |= set(emu.trace)
        stored = {a + i for _pc, a, size, _v in emu.writes for i in range(size) if not D.is_stack(a)}
        mstored = {a + i for a, size, _v in model.writes for i in range(size)}
        diff = [a for a in sorted(stored | mstored | mview.touched) if mem.load(a, 1) != mview.load(a, 1)]
        problems = []
        if stored != mstored or diff:
            problems.append('only original %s; only model %s; differ %s' % (
                sorted('%x' % a for a in stored - mstored)[:6], sorted('%x' % a for a in mstored - stored)[:6],
                ['%x:%02x/%02x' % (a, mem.load(a, 1), mview.load(a, 1)) for a in diff[:6]]))
        return problems


class Composed:
    def __init__(self, elf):
        self.rig = DP.Rig(elf)
        for name, addr in RB.NAMES.items():
            self.rig.emu.unhook(addr)
        DP.REAL.update(RB.NAMES.values())
        DP.REAL.update(RB.UNDER.values())
        DP.PP.Model = Model                      # the model of the chain with the four bodies done
        self.rng = None

    def generate(self, rng):
        rig = self.rig
        mem = rig.emu.mem
        case = DP.generate(rig, 'physics', rng)
        obj = case[0]
        mem.w32(RB.G_COSMETIC_SEED, rng.getrandbits(32))
        r = rng.random()
        if r < 0.45:
            m = C.mat3_from_quat(C.quat_normalize([rf(rng, -1, 1) for _ in range(4)]))
        elif r < 0.65:
            c, s = f32(0.8), f32(0.6)
            m = [c, s, 0, f32(-0.6), c, 0, 0, 0, C.ONE]
            m = [f32(C.to_float(x) + rng.uniform(-0.01, 0.01)) for x in m]
        elif r < 0.8:
            a = rng.getrandbits(32)
            m = [C.ONE if i % 4 == 0 else 0 for i in range(9)] if a & 1 else [f32(rng.uniform(-3, 3)) for _ in range(9)]
        else:
            m = [f32(rng.uniform(-1, 1)) for _ in range(9)]
        for k in range(9):
            mem.w32(obj + 0x110 + 4 * k, m[k])
        return case


def report(label, bad, n, shown):
    print('%-4s %-26s %5d cases, %d mismatches' % ('PASS' if not bad else 'FAIL', label, n, bad))
    if OPTIONS['verbose']:
        for line in shown[:3]:
            print('      ' + line)


def main(argv):
    args, elf = list(argv), None
    while args:
        item = args.pop(0)
        if item == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif item == '--cases':
            OPTIONS['cases'] = int(args.pop(0), 0)
        elif item == '-v':
            OPTIONS['verbose'] = True
        else:
            elf = item
    if elf is None:
        for candidate in (os.path.join(ROOT, 'SLUS_209.73'), os.path.join(ROOT, 'local', 'SLUS_209.73')):
            if os.path.exists(candidate):
                elf = candidate
                break
    if elf is None or not os.path.exists(elf):
        print('difftest_rigidbody: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    if hashlib.sha256(open(elf, 'rb').read()).hexdigest() != EXPECTED_SHA256:
        print('difftest_rigidbody: %s is not SLUS_209.73 US v2.00 - skipped' % elf)
        return 0
    RC.C.set_fpu('ps2')
    started, failed, pcs = time.time(), 0, set()
    direct = Direct(elf)
    for key in ('init', 'derived'):
        rng = random.Random('%d/%s' % (OPTIONS['seed'], key))
        bad, shown = 0, []
        for n in range(OPTIONS['cases']):
            problems = direct.case(key, rng)
            if problems:
                bad += 1
                shown.append('case %d: %s' % (n, problems[0]))
        report(key, bad, OPTIONS['cases'], shown)
        failed += bad
    pcs |= direct.pcs
    comp = Composed(elf)
    rng = random.Random('%d/physics' % OPTIONS['seed'])
    bad, shown, total_draw = 0, [], 0
    cases = max(OPTIONS['cases'] // 3, 1)
    for n in range(cases):
        case = comp.generate(rng)
        result = comp.rig.compare('physics', case, OPTIONS['seed'] * 1000003 + n)
        total_draw += result['draws']
        problems = [v for k, v in result.items() if k in ('fault', 'calls', 'writes', 'seed', 'result') and v]
        if problems:
            bad += 1
            shown.append('case %d: %s' % (n, problems[0]))
    report('physics (composed)', bad, cases, shown)
    failed += bad
    pcs |= comp.rig.pcs
    for name, (start, end) in BODIES.items():
        ran = len([pc for pc in pcs if start <= pc < end])
        print('  %-24s %4d of %4d instructions executed' % (name, ran, (end - start) // 4))
    if comp.rig.unknown:
        print('unknown calls: %s' % sorted('%x' % a for a in comp.rig.unknown))
    print('difftest_rigidbody: seed %d, %d mismatches, %.0f s' % (OPTIONS['seed'], failed, time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
