#!/usr/bin/env python3
"""difftest_minion.py - compare tools/ref_minion.py with the game's own code: Minion_run 0x2862c0
from its entry to the state dispatch, which includes the placement of a held Soul
(0x286364-0x2863e0): model_getAttachPoint's point into the held object's position, its facing
copied, obj_updateGridCell.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_minion.py [path/to/SLUS_209.73] [--seed N] [--cases N] [-v]

The original runs in tools/ee_emu.py with every callee a recording stub (Creature_processDamage
0x110d30, Creature_run 0x112948, Creature_updateActive 0x10c0f0, Creature_stepAnim 0x1162b0,
Creature_applyKnockback 0x115eb8, the virtual slot at table +0xb8, model_getAttachPoint 0x1754a0
(executed by tools/difftest_anim.py, docs/spec/animation.md 8.5), obj_updateGridCell 0x14f028)
answered from a script that is the same on both sides.  The Minion block and the held object are
filled with random words first, so a store the model misses shows.  Equal must be the calls in
order with their arguments (the position through its pointer; stack out-pointers as `stack`),
every byte stored outside the stack, and the result.  Cases: a held handle or none, Creature_run
returning 0 or non-zero, the held node's object a random block, a state of 0x18 or more (the
only states modelled), facings and scales of any value.
"""
import hashlib
import os
import random
import struct
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE                            # noqa: E402
import ref_core as C                             # noqa: E402
import ref_minion as R                           # noqa: E402
import difftest_combat_runtime as D              # noqa: E402

EXPECTED_SHA256 = D.EXPECTED_SHA256
ROOT = D.ROOT
M32 = 0xFFFFFFFF
f32 = D.f32
OPTIONS = {'seed': 20973, 'cases': 3000, 'verbose': False}
BODY = (0x2862C0, 0x287432)
SLOT_FN = 0x00F00100                            # an unmapped address: the virtual slot's stub
# name -> (address, integer args compared, float args compared)
CALLS = {
    'Creature_processDamage': (0x110D30, 2, 0), 'Creature_run': (0x112948, 2, 0),
    'Creature_updateActive': (0x10C0F0, 1, 0), 'Creature_stepAnim': (0x1162B0, 1, 1),
    'Creature_applyKnockback': (0x115EB8, 1, 1), 'Minion.slot23': (SLOT_FN, 2, 0),
    'model_getAttachPoint': (0x1754A0, 5, 1), 'obj_updateGridCell': (0x14F028, 1, 0),
}


class Script:
    """The answers of one case, drawn in call order from one stream."""

    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.run_result = self.rng.choice((0, 0, 0, 1, 2))
        self.point = tuple(f32(self.rng.uniform(-2000, 2000)) for _ in range(3))
        self.dir = tuple(f32(self.rng.uniform(-1, 1)) for _ in range(3))


class Rig:
    def __init__(self, elf):
        emu = self.emu = EE(elf, fpu_model='ps2')
        emu.div_zero = 'r5900'
        emu.follow = set()                       # every callee that is not hooked is an automatic stub
        self.names = {addr: name for name, (addr, _i, _f) in CALLS.items()}
        for name, (addr, _i, _f) in CALLS.items():
            emu.stub(addr, function=self._stub(name), name=name)
        self.calls, self.script, self.pcs = [], None, set()
        self.minion = emu.alloc(0x500)
        self.held = emu.alloc(0x100)
        self.node = emu.alloc(0x20)
        self.classdef = emu.alloc(0x40)
        self.model = emu.alloc(0x40)
        self.table = emu.alloc(0x400)
        self.vtable = emu.alloc(0x400)

    def _stub(self, name):
        def fn(emu):
            mem = emu.mem
            addr, nint, nfloat = CALLS[name]
            r = [emu.r[4 + i] & M32 for i in range(8)]
            args = []
            for i in range(nint):
                if name == 'model_getAttachPoint' and i == 1:
                    args.append(tuple(mem.u32(r[1] + 4 * k) for k in range(3)))
                elif name == 'model_getAttachPoint' and i == 2:
                    args.append(r[2])
                else:
                    args.append(r[i])
            args += [emu.f[12 + k] & M32 for k in range(nfloat)]
            self.calls.append((name, tuple(args)))
            if name == 'Creature_run':
                return self.script.run_result
            if name == 'model_getAttachPoint':
                for k in range(3):
                    mem.w32(r[5] + 4 * k, self.script.point[k])       # t1: the point out
                    mem.w32(r[6] + 4 * k, self.script.dir[k])         # t2: the direction out
            return 0
        return fn


def case(rig, rng, case_seed):
    emu, mem = rig.emu, rig.emu.mem
    for base, size in ((rig.minion, 0x500), (rig.held, 0x100), (rig.node, 0x20)):
        for off in range(0, size, 4):
            mem.w32(base + off, rng.getrandbits(32) if rng.random() < 0.4 else 0)
    this = rig.minion
    mem.w32(this + 0x24, rig.classdef)
    mem.w32(rig.classdef + 0xC, rig.model)
    mem.w32(this + 0x48, rig.vtable)
    mem.w16(rig.vtable + R.VTABLE_SLOT_ADJUST, rng.choice((0, 0x10, 0x20, 0xFFF0)))
    mem.w32(rig.vtable + R.VTABLE_SLOT_ADJUST + 4, SLOT_FN)
    held = rng.random() < 0.7
    mem.w32(this + R.OFFSET_HELD, rig.node if held else 0)
    mem.w32(rig.node + 0xC, rig.held)
    mem.w16(this + R.OFFSET_STATE, rng.choice((0x18, 0x19, 0x1D, 0x20, 0x7FFF, 0x8000, 0xFFFF, rng.randrange(0x18, 0x10000))))
    mem.w16(this + 0x38, rng.getrandbits(16))
    mem.w32(this + R.OFFSET_SCALE, f32(rng.choice((1.0, 0.5, 2.0, rng.uniform(0.1, 4)))))
    script = rig.script = Script(case_seed)

    # model side on a copy-on-write view
    mview = D.ModelView(mem)
    answers = {name: (lambda *a: 0) for name in CALLS}
    answers.update({'Creature_run': lambda *a: script.run_result,
               'model_getAttachPoint': lambda *a: (script.point, script.dir)})
    model = R.Model(mview, answers)
    mres = model.minion_run_prefix(this)

    rig.calls = []
    emu.reset_log()
    emu.trace = []
    emu.r[29] = emu.stack_hi - 0x400
    emu.call(R.MINION_RUN, this, max_steps=200000)
    rig.pcs |= set(emu.trace)
    problems = []
    got = [(n, a) for n, a in rig.calls]
    want = []
    for name, args in model.calls:
        _addr, nint, nfloat = CALLS[name]
        args = list(args)
        if name == 'model_getAttachPoint':
            # (model, position tuple, facing, anim, index, scale): the real call passes the facing in a2 as
            # a sign-extended halfword, a stack out-pointer in t1/t2 (not compared)
            args = [args[0], args[1], args[2] & M32, args[3], args[4], args[5]]
            args[1] = tuple(args[1])
        want.append((name, tuple(args)))
    # the stub reports r[2] raw (the facing as the register held it); both are the same low 32 bits
    if [(n, tuple(a)) for n, a in got] != want:
        problems.append('calls differ: original %r / model %r' % (got[:3], want[:3]))
    stored = {a + i for _pc, a, size, _v in emu.writes for i in range(size) if not D.is_stack(a)}
    mstored = {a + i for a, size, _v in model.writes for i in range(size)}
    diff = [a for a in sorted(stored | mstored | mview.touched) if mem.load(a, 1) != mview.load(a, 1)]
    if stored != mstored or diff:
        problems.append('stores: only original %s; only model %s; differ %s' % (
            sorted('%x' % a for a in stored - mstored)[:6], sorted('%x' % a for a in mstored - stored)[:6],
            ['%x:%02x/%02x' % (a, mem.load(a, 1), mview.load(a, 1)) for a in diff[:6]]))
    return problems, held and mres == 'done'


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
        print('difftest_minion: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    if hashlib.sha256(open(elf, 'rb').read()).hexdigest() != EXPECTED_SHA256:
        print('difftest_minion: %s is not SLUS_209.73 US v2.00 - skipped' % elf)
        return 0
    C.set_fpu('ps2')
    started = time.time()
    rig = Rig(elf)
    rng = random.Random(OPTIONS['seed'] * 13 + 3)
    bad, shown, placed = 0, [], 0
    for n in range(OPTIONS['cases']):
        problems, did_place = case(rig, rng, OPTIONS['seed'] * 1000003 + n)
        placed += 1 if did_place else 0
        if problems:
            bad += 1
            shown.append('case %d: %s' % (n, problems[0]))
    print('%-4s Minion_run prefix %5d cases (%d placed a held object), %d mismatches'
          % ('PASS' if not bad else 'FAIL', OPTIONS['cases'], placed, bad))
    if OPTIONS['verbose']:
        for line in shown[:3]:
            print('      ' + line)
    start, end = BODY
    ran = sorted(pc for pc in rig.pcs if start <= pc < end)
    placement = [pc for pc in range(0x286364, 0x2863E4, 4) if pc in rig.pcs]
    print('  Minion_run: %d of %d instructions executed; placement span 0x286364-0x2863e0: %d of %d'
          % (len(ran), (end - start) // 4, len(placement), (0x2863E4 - 0x286364) // 4))
    print('difftest_minion: seed %d, %d mismatches, %.0f s' % (OPTIONS['seed'], bad, time.time() - started))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
