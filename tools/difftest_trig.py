#!/usr/bin/env python3
"""difftest_trig.py - math_cos16 and math_sin16 against the executable.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_trig.py [path/to/SLUS_209.73] [--quick] [-v]

    --quick   the default FPU model only (still every 16-bit angle)
    -v        print up to three failing inputs per property

The original functions are run by tools/ee_emu.py.  A mismatch is a different 32-bit
pattern.  The default property uses the interpreter's 'ps2' adder.  The other adder
models are repeated in full so a port can see that the last bit of the adds moves
with the model, and that the reference moves with it.
"""
import hashlib
import math
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE                          # noqa: E402
import ref_core as R                           # noqa: E402
import ref_trig as T                           # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COS16, SIN16 = 0x166630, 0x1666E0
PARTICLE_INIT, STATIC_INIT = 0x18E648, 0x195D30
TASK_ADD, ASSERT_FAIL, RESOURCE_REF_CTOR = 0x19E4A0, 0x17FD48, 0x173768

OPTIONS = {'quick': False, 'verbose': False}
RESULTS = []


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-18s %7d cases  %s%s' % (
        'PASS' if ok else 'FAIL', name, count, text,
        '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:3]:
            print('        ' + line)
    sys.stdout.flush()


def find_elf(argv):
    candidates = [a for a in argv if not a.startswith('-')]
    candidates += [os.path.join(ROOT, 'local', 'SLUS_209.73'),
                   os.path.join(ROOT, 'SLUS_209.73'), 'SLUS_209.73']
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def host_diff_count():
    """Angles whose host math.cos or math.sin, packed to float32, is not the polynomial."""
    changed = 0
    for angle in range(0x10000):
        turned = R.s16(angle) * (2.0 * math.pi / 65536.0)
        cosine = struct.unpack('<I', struct.pack('<f', math.cos(turned)))[0]
        sine = struct.unpack('<I', struct.pack('<f', math.sin(turned)))[0]
        if cosine != T.cos16(angle) or sine != T.sin16(angle):
            changed += 1
    return changed


def sweep(elf, model):
    R.set_fpu(model)
    emu = EE(elf, fpu_model=model)
    emu.record_calls = False
    emu.record_writes = False
    failures = 0
    examples = []
    total = 0
    for name, addr, model_fn in (('cos16', COS16, T.cos16), ('sin16', SIN16, T.sin16)):
        for angle in range(0x10000):
            emu.call(addr, angle)
            total += 1
            got = emu.f[0]
            want = model_fn(angle)
            if got != want:
                failures += 1
                if len(examples) < 3:
                    examples.append('%s %s angle %x: original %08x model %08x' % (
                        model, name, angle, got, want))
    return failures, total, examples


def test_angles(elf):
    models = ('ps2',) if OPTIONS['quick'] else ('ps2', 'ps2g1', 'chop', 'nearest')
    for model in models:
        failures, total, examples = sweep(elf, model)
        extra = ''
        if model == 'ps2':
            extra = '; host libm float32 differs on %d of 65536 angles (not compared)' % host_diff_count()
        report('angle.' + model, failures, total,
               '0x166630 and 0x1666e0, every 16-bit angle, bit for bit under the %s adder%s' % (model, extra),
               examples)
    R.set_fpu()


def test_high_bits(elf):
    """Bits above the low 16 do not change the result.  The machine sign-extends first."""
    emu = EE(elf)
    emu.record_calls = False
    emu.record_writes = False
    R.set_fpu()
    failures, total, examples = 0, 0, []
    for angle in range(0, 0x10000, 64):
        for wider in (angle | 0xABCD0000, (angle - 0x10000) & 0xFFFFFFFF):
            for addr, fn in ((COS16, T.cos16), (SIN16, T.sin16)):
                emu.call(addr, wider)
                total += 1
                if emu.f[0] != fn(wider):
                    failures += 1
                    if len(examples) < 3:
                        examples.append('%x -> %08x model %08x' % (wider, emu.f[0], fn(wider)))
    report('angle.high-bits', failures, total,
           'junk above bit 15 and a sign-extended negative, every 64th angle, both routines',
           examples)


def test_haze_circle(elf):
    """particle_init writes the 64 pairs.  They are not constants in the executable."""
    emu = EE(elf)
    emu.record_calls = False
    emu.record_writes = False
    def fail_assert(e):
        raise RuntimeError('particle assertion at %#x' % e.pc)

    emu.stub(TASK_ADD, ret=0)
    emu.stub(ASSERT_FAIL, function=fail_assert)
    emu.stub(RESOURCE_REF_CTOR, ret=0)
    R.set_fpu()
    emu.call(STATIC_INIT, 1, 0xFFFF)
    emu.call(PARTICLE_INIT)
    failures, examples = 0, []
    for index in range(T.HAZE_COUNT):
        got = (emu.mem.u32(T.HAZE_CIRCLE + index * 8),
               emu.mem.u32(T.HAZE_CIRCLE + index * 8 + 4))
        want = T.haze_circle(index)
        if got != want:
            failures += 1
            if len(examples) < 3:
                examples.append('index %d: original %08x %08x model %08x %08x' % (
                    index, got[0], got[1], want[0], want[1]))
    report('haze.circle', failures, T.HAZE_COUNT,
           'particle_init 0x18e648: trunc(sin16(i<<10)*5), trunc(cos16(i<<10)*5) at 0x7ec0e0',
           examples)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = []
    while argv:
        item = argv.pop(0)
        if item == '--quick':
            OPTIONS['quick'] = True
        elif item == '-v':
            OPTIONS['verbose'] = True
        else:
            args.append(item)
    elf = find_elf(args)
    if elf is None:
        print('SKIP  SLUS_209.73 not found (pass its path); nothing was compared')
        return 0
    with open(elf, 'rb') as source:
        digest = hashlib.sha256(source.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('SKIP  %s is not the US v2.00 executable; nothing was compared' % elf)
        return 0
    started = time.time()
    test_angles(elf)
    test_high_bits(elf)
    test_haze_circle(elf)
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d PASS, %d FAIL (%.0f s)' % (
        len(RESULTS), len(RESULTS) - len(failed), len(failed), time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
