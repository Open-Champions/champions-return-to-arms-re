#!/usr/bin/env python3
"""difftest_arrow_hit.py - compare tools/ref_arrow_hit.py with the game's own code, one call at
a time: Creature_setEffectTimer 0x118950 and LightEffect_ctor 0x201bd8.  (Their use inside the
arrows' chains is compared by tools/difftest_arrow_run.py, which runs them real as well.)

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_arrow_hit.py [path/to/SLUS_209.73] [--seed N] [--cases N] [-v]

World: tools/difftest_arrow_run.py's (GameObject_ctor, handle_link / handle_clear and the
handle-node pool real; every other callee a recording stub answered alike on both sides).
Entries
    timer   Creature_setEffectTimer on a victim block with `which` 0..4 and the values that
            skip the store (5, 6, 0x80000000, 0xffffffff), seconds of either sign, zero and
            huge, a source object or none, and an attacker list already linked or empty
    light   LightEffect_ctor with colours of either sign and past 16 bits, radius zero,
            negative and large, life zero, negative, tiny and huge, a follow object or none,
            on dirty blocks, with the simulation frame random
Equal must be the calls in order with their arguments, every byte stored outside the stack,
the shared seed 0x404464 with its draw count (ONE in LightEffect_ctor, none in the timer).
"""
import hashlib
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_arrow_run as A                       # noqa: E402
import difftest_creature as DC                  # noqa: E402
import difftest_arrow_run as DAR                # noqa: E402
from difftest_creature import f32               # noqa: E402

ROOT = DAR.ROOT
OPTIONS = DAR.OPTIONS
M32 = 0xFFFFFFFF
BODIES = {'Creature_setEffectTimer': A.BODIES['Creature_setEffectTimer'], 'LightEffect_ctor': A.BODIES['LightEffect_ctor']}


def rfloat(rng, kind):
    if kind == 'colour':
        return f32(rng.choice((0.0, 255.0, rng.uniform(-300, 700), rng.uniform(0, 255), 65535.0, 70000.0, -1.0, 1e10, -1e10)))
    if kind == 'radius':
        return f32(rng.choice((0.0, -5.0, rng.uniform(1, 500), rng.uniform(1, 500), 120.0, 1e-3, 1e5)))
    if kind == 'life':
        return f32(rng.choice((0.0, -1.0, 0.25, 0.01, rng.uniform(0, 5), rng.uniform(0, 5), 1e9, -1e9)))
    return f32(rng.uniform(-100, 100))


def clean(rig, mem, heads):
    for head in heads:
        if mem.u32(head):
            rig.emu.call(0x1A1698, head)
    rig.emu.reset_log()


def case_timer(rig, rng):
    w, mem = rig.world, rig.emu.mem
    victim, source = w.monsters[1], w.monsters[0]
    DAR.place(mem, victim, (rng.uniform(-500, 500), rng.uniform(-500, 500), 0.0))
    for off in range(0x340, 0x368, 4):
        mem.w32(victim + off, rng.getrandbits(32) if rng.random() < 0.5 else f32(rng.uniform(0, 30)))
    mem.w32(victim + 0x360, 0)
    if rng.random() < 0.5:                       # an attacker already linked
        mem.w32(victim + 0x360, 0)
        rig.emu.call(0x1A1738, victim + 0x360, w.monsters[2], w.monsters[2])
    which = rng.choice((0, 1, 2, 3, 4, 0, 1, 1, 5, 6, 0x80000000, 0xFFFFFFFF, 0xFFFFFFFE))
    seconds = f32(rng.choice((0.0, -0.0, rng.uniform(0.1, 20), rng.uniform(-5, 0), 1e-5, 1e9)))
    src = rng.choice((0, source, source))
    out = rig.compare('Creature_setEffectTimer', 'Creature_setEffectTimer', (victim, which, src), fargs=(seconds,))
    clean(rig, mem, [victim + 0x360, source, source + 4, source + 8, w.monsters[2], w.monsters[2] + 4,
                     w.monsters[2] + 8])
    return out


def case_light(rig, rng):
    w, mem = rig.world, rig.emu.mem
    block = rng.choice(w.blocks)
    for off in range(0, 0xC0, 4):
        mem.w32(block + off, rng.getrandbits(32) if rng.random() < 0.3 else 0)
    follow = rng.choice((0, 0, w.monsters[0], w.monsters[2]))
    if not hasattr(rig, 'pos_buffer'):
        rig.pos_buffer = rig.emu.alloc(0x20)
    pos = rig.pos_buffer
    for k in range(3):
        mem.w32(pos + 4 * k, f32(rng.uniform(-3000, 3000)))
    mem.w32(RC.G_SIM_FRAME, rng.choice((0, 5, 1000, rng.getrandbits(20), 0x7FFFFFF0)))
    mem.w32(RC.G_RAND_SEED, rng.getrandbits(32))
    tag = rng.choice((0, 1, 2, rng.getrandbits(32)))
    colours = [rfloat(rng, 'colour') for _ in range(8)]
    stack = [rfloat(rng, 'radius'), rfloat(rng, 'radius'), rfloat(rng, 'other'), rfloat(rng, 'life')]
    out = rig.compare('LightEffect_ctor', 'LightEffect_ctor_entry',
                      (block, pos, follow, tag, 0, 0, 0, 0) + tuple(stack), fargs=tuple(colours))
    clean(rig, mem, [block, block + 4, block + 8, block + 0x88, w.monsters[0], w.monsters[0] + 4,
                     w.monsters[0] + 8, w.monsters[2], w.monsters[2] + 4, w.monsters[2] + 8])
    return out


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
        elf = os.path.join(ROOT, 'SLUS_209.73')
        if not os.path.exists(elf):
            elf = os.path.join(ROOT, 'local', 'SLUS_209.73')
    if not os.path.exists(elf):
        print('difftest_arrow_hit: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    if hashlib.sha256(open(elf, 'rb').read()).hexdigest() != DC.EXPECTED_SHA256:
        print('difftest_arrow_hit: %s is not SLUS_209.73 US v2.00 - skipped' % elf)
        return 0
    C.set_fpu(OPTIONS['fpu'])
    started = time.time()
    rig = DAR.Rig(elf, OPTIONS['seed'])
    rng = random.Random(OPTIONS['seed'] * 31 + 5)
    cases = OPTIONS['cases'] if OPTIONS['cases'] != 600 else 3000
    failed = 0
    for key, fn in (('timer', case_timer), ('light', case_light)):
        bad, both, shown, draws = 0, 0, [], 0
        for n in range(cases):
            out = fn(rig, rng)
            draws += out['draws']
            if out['both_fault']:
                both += 1
            problems = [(k, out[k]) for k in ('fault', 'calls', 'writes', 'seed', 'result') if out[k]]
            if problems:
                bad += 1
                shown.append('case %d: %s' % (n, problems[0]))
        failed += bad
        print('%-4s %-6s %5d cases, %d mismatches, %d stopped on both sides, %d shared draws'
              % ('PASS' if not bad else 'FAIL', key, cases, bad, both, draws))
        if OPTIONS['verbose']:
            for line in shown[:3]:
                print('      ' + line)
    for name, (start, end) in BODIES.items():
        inside = {pc for pc in rig.cov if start <= pc < end}
        print('  %-26s %4d of %4d instructions executed' % (name, len(inside), (end - start) // 4))
        if OPTIONS['verbose'] and len(inside) != (end - start) // 4:
            print('      not executed: %s' % ' '.join('%x' % pc for pc in range(start, end, 4) if pc not in inside))
    if rig.unknown:
        print('calls to unknown addresses: %s' % {('%x' % k): v for k, v in rig.unknown.items()})
        failed += 1
    print('difftest_arrow_hit: seed %d, %d mismatches, %.0f s' % (OPTIONS['seed'], failed, time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
