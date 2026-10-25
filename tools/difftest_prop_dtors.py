#!/usr/bin/env python3
"""difftest_prop_dtors.py - compare tools/ref_prop_dtors.py with the game's own code:
PhProp_dtor 0x3c2fc8, GutChunk_dtor 0x3c4d48, Prop_dtor 0x3c2d30, ItemProp_dtor 0x3c2ed8,
Gold_dtor 0x3c31d8, anim_advanceUnitSpeed 0x1709d8.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_prop_dtors.py [path/to/SLUS_209.73] [--seed N] [--cases N] [-v]

Each case runs the original body in tools/ee_emu.py with its callees as recording stubs
(GameObject_dtor 0x14cf90, pool_free 0x150470, anim_advance 0x16d748, AnimState_dtor
0x171098: executed elsewhere,
see the model's docstring), each answering a value drawn from the case's own random
stream, and runs the model with the same answers.  Equal must be: the calls in order with
their integer arguments (and f12 for anim_advance), every byte stored outside the stack,
and the result.  The object block is filled with random words first, so a store the model
misses shows.  The instructions each body executed are counted against its length.
"""
import hashlib
import os
import random
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE                            # noqa: E402
import ref_prop_dtors as R                       # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M32 = 0xFFFFFFFF
OPTIONS = {'seed': 20973, 'cases': 3000, 'verbose': False}

BODIES = {'PhProp_dtor': (0x3C2FC8, 0x3C302C), 'GutChunk_dtor': (0x3C4D48, 0x3C4DAC),
          'Prop_dtor': (0x3C2D30, 0x3C2D94), 'ItemProp_dtor': (0x3C2ED8, 0x3C2F3C),
          'Gold_dtor': (0x3C31D8, 0x3C324C), 'anim_advanceUnitSpeed': (0x1709D8, 0x1709F4)}
STUBS = {R.GAMEOBJECT_DTOR: 'GameObject_dtor', R.POOL_FREE: 'pool_free', R.ANIM_ADVANCE: 'anim_advance',
         R.ANIMSTATE_DTOR: 'AnimState_dtor'}
BLOCK = 0x248


class Rig:
    def __init__(self, elf):
        emu = self.emu = EE(elf)
        self.answers, self.seen = [], []
        for addr, name in STUBS.items():
            emu.stub(addr, function=self._stub(name), name=name)
        self.block = emu.alloc(BLOCK)
        self.pcs = set()

    def _stub(self, name):
        def fn(e):
            args = tuple(e.r[4 + i] & M32 for i in range(4))
            self.seen.append((name, args, e.f[12] & M32 if name == 'anim_advance' else None))
            return self.answers.pop(0) if self.answers else 0
        return fn

    def run(self, key, args, answers):
        emu, mem = self.emu, self.emu.mem
        self.answers, self.seen = list(answers), []
        emu.reset_log()
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x100
        emu.f[12] = 0xDEADBEEF                  # the body must set it
        ret = emu.call(BODIES[key][0], *args, max_steps=10000) & M32
        self.pcs |= set(emu.trace)
        writes = {}
        for _pc, addr, size, value in emu.writes:
            for i in range(size):
                writes[addr + i] = (value >> (8 * i)) & 0xFF
        return self.seen, writes, ret


def model_side(key, args, answers):
    queue, seen, writes = list(answers), [], {}

    def w32(addr, value):
        for i in range(4):
            writes[addr + i] = (value >> (8 * i)) & 0xFF

    def call(name, *a, f12=None):
        a = tuple(x & M32 for x in a) + (None,) * (4 - len(a))
        seen.append((name, a, f12))
        return queue.pop(0) if queue else 0
    m = R.Model(w32, call)
    if key == 'anim_advanceUnitSpeed':
        ret = m.anim_advance_unit_speed(*args)
    elif key == 'Gold_dtor':
        ret = m.gold_dtor(*args)
    else:
        ret = m.prop_dtor(*args)
    return seen, writes, ret


def compare(rig, rng, key):
    mem = rig.emu.mem
    for off in range(0, BLOCK, 4):
        mem.w32(rig.block + off, rng.getrandbits(32))
    answers = [rng.getrandbits(32) for _ in range(3)]
    if key == 'anim_advanceUnitSpeed':
        args = (rig.block + 0x114, rng.choice((0, rig.block + 0x10)), rig.block + 0xBC, rig.block + 0xC4)
    else:
        args = (rig.block, rng.choice((0, 1, 2, 3, 0xFFFFFFFF, 0x10)))
    calls, writes, ret = rig.run(key, args, answers)
    m_calls, m_writes, m_ret = model_side(key, args, answers)
    problems = []
    # the stub sees all four argument registers; compare the ones the callee takes
    used = {'GameObject_dtor': 2, 'pool_free': 1, 'anim_advance': 4, 'AnimState_dtor': 2}
    got = [(n, a[:used[n]], f) for n, a, f in calls]
    want = [(n, a[:used[n]], f) for n, a, f in m_calls]
    if got != want:
        problems.append('calls %r != model %r' % (got, want))
    if writes != m_writes:
        problems.append('stores differ at %s' % sorted(set(writes) ^ set(m_writes) or
                                                       [a for a in writes if writes[a] != m_writes.get(a)])[:4])
    if key == 'anim_advanceUnitSpeed' and ret != m_ret & M32:
        problems.append('result %#x != model %#x' % (ret, m_ret))
    return problems


def main(argv):
    args = list(argv)
    elf = None
    while args:
        a = args.pop(0)
        if a == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif a == '--cases':
            OPTIONS['cases'] = int(args.pop(0), 0)
        elif a == '-v':
            OPTIONS['verbose'] = True
        else:
            elf = a
    if elf is None:
        for candidate in (os.path.join(ROOT, 'SLUS_209.73'), os.path.join(ROOT, 'local', 'SLUS_209.73')):
            if os.path.exists(candidate):
                elf = candidate
                break
    if elf is None or not os.path.exists(elf):
        print('difftest_prop_dtors: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    with open(elf, 'rb') as f:
        if hashlib.sha256(f.read()).hexdigest() != EXPECTED_SHA256:
            print('difftest_prop_dtors: %s is not SLUS_209.73 US v2.00 - skipped' % elf)
            return 0
    rig = Rig(elf)
    failed = 0
    for key in BODIES:
        rng = random.Random('%d/%s' % (OPTIONS['seed'], key))
        bad, shown = 0, []
        for n in range(OPTIONS['cases']):
            problems = compare(rig, rng, key)
            if problems:
                bad += 1
                if len(shown) < 3:
                    shown.append('case %d: %s' % (n, '; '.join(problems)))
        start, end = BODIES[key]
        ran = len([pc for pc in rig.pcs if start <= pc < end])
        print('%-4s %-22s %5d cases, %d mismatches; %d of %d instructions executed' % (
            'PASS' if not bad else 'FAIL', key, OPTIONS['cases'], bad, ran, (end - start) // 4))
        if OPTIONS['verbose']:
            for line in shown:
                print('      ' + line)
        failed += bad
    print('difftest_prop_dtors: seed %d, %d mismatches' % (OPTIONS['seed'], failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
