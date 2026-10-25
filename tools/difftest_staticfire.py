#!/usr/bin/env python3
"""difftest_staticfire.py - compare tools/ref_staticfire.py with the game's own code:
StaticFire_ctor 0x2c5240, StaticFire_initCommon 0x2c5814 and the particle push 0x2c6aa8, each
called on its own and run for real (the ctor runs the other two for real too).

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_staticfire.py [path/to/SLUS_209.73] [--seed N] [--cases N] [-v]

World: tools/difftest_arrow_run.py's (GameObject_ctor, GameObject_rand, math_cos16 / sin16,
rtti_typeInfoEquals, handle_link / handle_clear real; the callees below recording stubs
answered alike on both sides): light_link, light_unlink, obj_runEveryFrame, obj_addToAlwaysDraw
0x14edd8, path_blockNodes 0x18b6c0, mem_allocTagged 0x14ff88, StaticFire_typeinfo 0x3c7318,
world_collectObjectsInBox 0x14a928 and the slot-0 type-info getter of the objects it returns.
Entries
    ctor     StaticFire_ctor on dirty blocks, the position anywhere, life of either sign, owner
             or none, flag 0 or non-zero, size and scale of any sign, 0..6 objects in the box
             (the fire itself, creatures, other fires: the type answer is the fire descriptor or
             a creature's), in the ctor's own call sequence
    init     StaticFire_initCommon on dirty blocks with bytes +0x6f and +0x70 of every value
    push     the particle push with a ring (size 1..24, an index and a stop inside it) and any
             16-bit facing
Equal must be the calls in order with their arguments, every byte stored outside the stack, the
shared seed 0x404464 (ONE draw in the ctor's GameObject_ctor) and the object's own generator.
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
import ref_staticfire as SF                     # noqa: E402
import difftest_creature as DC                  # noqa: E402
import difftest_arrow_run as DAR                # noqa: E402
from difftest_creature import Res, f32          # noqa: E402

ROOT = DAR.ROOT
OPTIONS = DAR.OPTIONS
M32 = 0xFFFFFFFF
BODIES = {'StaticFire_ctor': (0x2C5240, 0x2C54F8), 'StaticFire_initCommon': (0x2C5814, 0x2C595C),
          'StaticFire_pushParticles': (0x2C6AA8, 0x2C6BC0)}
EXTRA_EXTERNALS = {
    'path_blockNodes': RC.Ext(0x18B6C0, 'iv', 1, 'n', '(world, position; radius)'),
    'obj_addToAlwaysDraw': RC.Ext(0x14EDD8, 'p', 0, 'n', '(object)'),
    'mem_allocTagged': RC.Ext(0x14FF88, 'ipp', 0, 'i', '(size, tag text, fallback)'),
    'StaticFire_typeinfo': RC.Ext(0x3C7318, '', 0, 'i', '-> descriptor'),
}
DAR.DESC['StaticFire'] = 0x9083C0
DAR.DESC_NAMES['StaticFire'] = b'10StaticFire'
A.EXTERNALS.update(EXTRA_EXTERNALS)


class Model(SF.FireMixin, A.Model):
    pass


class FireRig(DAR.Rig):
    model_class = Model

    def __init__(self, elf, seed):
        DAR.Rig.__init__(self, elf, seed)
        emu = self.emu
        for name, (start, end) in BODIES.items():
            DAR.FUNCTION_ADDR[name] = start
            self.real.addresses.add(start)
            emu.unhook(start)                    # StaticFire_ctor was a stub in the world
            for pc in range(start, end, 4):
                w = emu.mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E) and pc not in self.partial_ops:
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, DAR.ee_emu.sx16(w)))
        world = self.world
        world.fire = None
        world.on_path_blockNodes = lambda args, view, rng: Res()
        world.on_obj_addToAlwaysDraw = lambda args, view, rng: Res()
        world.on_mem_allocTagged = lambda args, view, rng: Res(rng.getrandbits(32))
        world.on_StaticFire_typeinfo = lambda args, view, rng: Res(DAR.DESC['StaticFire'])
        world.on_world_collectObjectsInBox = self.crowd
        self.block = emu.alloc(0x4C0)
        self.ring = emu.alloc(0x400)
        self.pos = emu.alloc(0x20)

    def crowd(self, args, view, rng):
        w = self.world
        pool = list(w.objects) + [w.fire]
        n = rng.choice((0, 0, 1, 2, 3, 3, 4, 5, 6))
        found = rng.sample(pool, min(n, len(pool)))
        return Res(outs=[found[:min(len(found), max(0x80 - 1, 0))]])


def dirty(rig, rng, block):
    mem = rig.emu.mem
    for off in range(0, 0x4C0, 4):
        mem.w32(block + off, rng.getrandbits(32) if rng.random() < 0.35 else 0)
    mem.w32(block + 0x4A4, 0)
    for k in range(3):
        mem.w32(block + 0x10 + 4 * k, f32(rng.uniform(-3000, 3000)))


def clean(rig, heads):
    mem = rig.emu.mem
    for head in heads:
        if mem.u32(head):
            rig.emu.call(0x1A1698, head)
    rig.emu.reset_log()


def case_ctor(rig, rng):
    w, mem = rig.world, rig.emu.mem
    fire = rig.block
    w.fire = fire
    dirty(rig, rng, fire)
    for k in range(3):
        mem.w32(rig.pos + 4 * k, f32(rng.uniform(-3000, 3000)) if rng.random() < 0.9 else f32(rng.choice((0.0, -0.0, 1e9))))
    w.type_answer = rng.choice((DAR.DESC['StaticFire'], DAR.DESC['StaticFire'], DAR.DESC['Creature']))
    mem.w32(RC.G_RAND_SEED, rng.getrandbits(32))
    life = rng.choice((0, 1, 60, 240, 360, 480, rng.getrandbits(32), rng.randrange(1, 3000), -5, 0x7FFFFFFF, 0xFFFFFFFF))
    owner = rng.choice((0, w.monsters[0], w.players[0]))
    flag = rng.choice((0, 0, 1, 1, 0xFF))
    size = f32(rng.choice((120.0, 240.0, 0.0, -3.0, rng.uniform(1, 400))))
    scale = f32(rng.choice((1.0, 0.5, 2.0, rng.uniform(0.1, 3), 0.0)))
    out = rig.compare('StaticFire_ctor', 'staticfire_ctor', (fire, rig.pos, life, owner, flag), fargs=(size, scale))
    clean(rig, [fire, fire + 4, fire + 8])
    return out


def case_init(rig, rng):
    w = rig.world
    fire = rig.block
    dirty(rig, rng, fire)
    mem = rig.emu.mem
    mem.w8(fire + 0x6F, rng.choice((0, 0, 1, 0xFF)))
    mem.w8(fire + 0x70, rng.choice((0, 0, 1, 0x80)))
    mem.w32(fire + 0x1C, rng.choice((0, f32(16.0), f32(rng.uniform(0, 100)))))
    mem.w32(RC.G_RAND_SEED, rng.getrandbits(32))
    return rig.compare('StaticFire_initCommon', 'staticfire_init_common', (fire,))


def case_push(rig, rng):
    fire = rig.block
    dirty(rig, rng, fire)
    mem = rig.emu.mem
    cap = rng.randrange(1, 25)
    mem.w32(fire + 0x4A4, rig.ring)
    for off in range(0, 10 * 25 + 8, 4):
        mem.w32(rig.ring + off, rng.getrandbits(32))
    mem.w16(fire + 0x76, cap)
    mem.w16(fire + 0x7A, rng.randrange(cap))
    mem.w16(fire + 0x78, rng.randrange(cap))
    facing = rng.choice((0, 0x4000, -0x4000, 0x7FFF, -0x8000, rng.randrange(-0x8000, 0x8000)))
    return rig.compare('StaticFire_pushParticles', 'staticfire_push', (fire, facing & M32))


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
        print('difftest_staticfire: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    if hashlib.sha256(open(elf, 'rb').read()).hexdigest() != DC.EXPECTED_SHA256:
        print('difftest_staticfire: %s is not SLUS_209.73 US v2.00 - skipped' % elf)
        return 0
    C.set_fpu(OPTIONS['fpu'])
    started = time.time()
    rig = FireRig(elf, OPTIONS['seed'])
    rng = random.Random(OPTIONS['seed'] * 37 + 11)
    cases = OPTIONS['cases'] if OPTIONS['cases'] != 600 else 3000
    failed = 0
    for key, fn in (('ctor', case_ctor), ('init', case_init), ('push', case_push)):
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
        print('%-4s %-5s %5d cases, %d mismatches, %d stopped on both sides, %d shared draws'
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
    print('difftest_staticfire: seed %d, %d mismatches, %.0f s' % (OPTIONS['seed'], failed, time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
