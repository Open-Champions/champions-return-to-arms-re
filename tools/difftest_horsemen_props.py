#!/usr/bin/env python3
"""Compare addressed Nightmare properties with original parser and constructors.

Run with PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_horsemen_props.py
<owner SLUS_209.73> --seed 20973 (and --seed 7).  The original parser,
GameObject_ctor, Creature_ctor, name registration and name lookup execute in ee_emu.
"""
import hashlib
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import difftest_objects as DO                 # noqa: E402
import ref_horsemen_props as HP               # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def compare(elf, seed):
    rig = DO.Rig(elf, seed)
    mem = rig.emu.mem
    failures = []

    def check(label, actual, expected):
        if actual != expected:
            failures.append('%s: got %r, expected %r' % (label, actual, expected))

    for expected in HP.MOUNT_PROPERTIES:
        v = expected.variant
        prefix = 'variant %d' % v
        check(prefix + ' list pointers',
              tuple(mem.u32(expected.list_addr + 4 * i) for i in range(3)),
              (expected.miniboss_text_addr, expected.name_text_addr, 0))
        entries = (mem.cstr(expected.miniboss_text_addr).encode('ascii'),
                   mem.cstr(expected.name_text_addr).encode('ascii'))
        check(prefix + ' decoded entries', entries,
              (b'miniboss=1', b'name=' + expected.name))

        # The real base constructor stores +0x2c, parses name= and registers it.
        # The real creature constructor calls that base, then parses MiniBoss.
        obj = rig.ecall(DO.POOL_NEW, 0x3D8)
        if obj == 0:
            failures.append(prefix + ' pool allocation failed')
            continue
        pos = rig.vec(0, (0, 0, 0))
        rig.ecall(0x109D68, obj, 0, pos, 0, 0x500680, expected.list_addr, 0)
        check(prefix + ' stored property list', mem.u32(obj + 0x2C), expected.list_addr)
        check(prefix + ' creature MiniBoss flag', mem.u64(obj + 0xA8) & 1,
              1 if expected.miniboss else 0)
        check(prefix + ' no ShowName pointer', mem.u32(obj + 0x368), 0)
        check(prefix + ' no ShowName object flag', mem.u32(obj + 0xC) & 0x100000, 0)

        for key, function, value in ((b'miniboss', 'obj_getPropInt', expected.miniboss),
                                     (b'name', 'obj_getPropStr', expected.name_text_addr + 5),
                                     (b'hide', 'obj_getPropInt', 0),
                                     (b'ShowName', 'obj_getPropStr', 0)):
            actual = rig.ecall(DO.A[function], obj, rig.cstring(key), 0)
            check(prefix + ' parser ' + key.decode('ascii'), actual, value)
        name_addr = expected.name_text_addr + 5
        check(prefix + ' registered name text', mem.cstr(name_addr).encode('ascii'), expected.name)
        check(prefix + ' name lookup', rig.ecall(0x14F498, name_addr), obj)

    failed_variants = {line.split(' ', 2)[1] for line in failures}
    print('mount property lists: %d/4 variants, seed %d, %d mismatches'
          % (4 - len(failed_variants), seed, len(failures)))
    for failure in failures:
        print('  FAIL ' + failure)
    return not failures


def main(args):
    elf = os.path.join(ROOT, 'SLUS_209.73')
    seed = 20973
    while args:
        arg = args.pop(0)
        if arg == '--seed':
            seed = int(args.pop(0), 0)
        else:
            elf = arg
    if not os.path.exists(elf):
        print('difftest_horsemen_props: %s not found - nothing to compare with' % elf)
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != DO.EXPECTED_SHA256:
        print('difftest_horsemen_props: wrong executable sha256 %s - skipped' % digest[:16])
        return 1
    return 0 if compare(elf, seed) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
