#!/usr/bin/env python3
"""rigvu.py - vector unit 0 on edge operands inside the emulator rig, infinities and NaNs
included, against rt/vu0.h as it is, as proposed, and against the written references.

  python3 tools/recomp/proof/rigvu.py [--state local/rig-out/states/04-hub.zip]

arith.py vu tests rt/vu0.h on finite operands against softf.py; what the emulator itself
computes was not measured, and operands with exponent 255 were not tried at all.  This
script does for the vector unit what rigarith.py does for the FPU:

  1. a small MIPS routine, a table of 128 edge patterns (zeroes, denormals, the smallest
     and largest exponents, exponent 255 with several mantissas: both infinities and NaNs
     of both signs) and one two-instruction microprogram per tested instruction are written
     into unused memory of a saved machine state; the routine copies the microprograms
     into the unit's program memory (0x11000000 + 0xc00, beyond the game's own program)
     with ordinary stores - the emulator discards its translation of what is overwritten;
  2. hooked into gfx_beginFrame once, it runs every instruction on all 128 x 128 pairs in
     the game's own thread: QMTC2 a -> vf1, QMTC2 b -> vf2, VCALLMS, QMFC2 vf3, store x;
  3. the results are dumped and compared, per instruction, with
       - rt/vu0.h of the snapshot (arith_main.cpp built against it), flush-to-zero set;
       - the same header as proposed in rt-proposed.patch (operands of exponent 255 and 0
         brought into the unit's range first);
       - vu0ref.py's two models ('host', 'console').

Nothing of the game is in this file: two instruction words of the executable are read at
run time so that they can be executed after the routine.
"""
import argparse
import array
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import arith                                    # noqa: E402
import rigarith as ra                           # noqa: E402
import vu0ref                                   # noqa: E402

ROOT = arith.ROOT
PROOF = os.path.join(ROOT, 'local', 'recomp-out', 'proof')
OUT = os.path.join(arith.OUT, 'rigvu')
CODE, FLAG, TABLE, RESULTS = ra.CODE, ra.FLAG, ra.TABLE, ra.RESULTS
MICRO_AT = 0x180                # instruction index of the first test program (the game's own ends at 76)
T0, T1, T2, T3, T4, T5, T6 = 8, 9, 10, 11, 12, 13, 14
NOP_LOWER, NOP_UPPER, E_BIT = 0x8000033C, 0x000002FF, 0x40000000


def forms():
    """(name, upper word, kind, argument) of the tested instructions: fs = vf1, ft = vf2,
    result in vf3, all four fields (arith.py's table)."""
    wanted = ('ADD', 'SUB', 'MUL', 'MAX', 'MINI', 'FTOI0', 'FTOI4', 'ITOF0', 'ITOF12', 'ABS', 'ADDx', 'MULx', 'MAXx', 'MINIx')
    table = {name: (name, upper, kind, arg) for name, upper, kind, arg in arith.vu_forms()}
    return [table[name] for name in wanted]


def qmtc2(rt, fd):
    return (0x12 << 26) | (5 << 21) | (rt << 16) | (fd << 11)


def qmfc2(rt, fd):
    return (0x12 << 26) | (1 << 21) | (rt << 16) | (fd << 11)


def vcallms(index):
    return (0x12 << 26) | (1 << 25) | (index << 6) | 0x38


def routine(displaced, count, ops):
    words = []
    at = lambda: CODE + 4 * len(words)
    end = TABLE + 4 * count
    words += [ra.lui(T4, FLAG >> 16), ra.mem(0x23, T5, T4, FLAG & 0xFFFF)]
    skip = len(words)
    words += [0, 0]                             # bne t5, zero, done ; nop
    words += [ra.addiu(T5, 0, 1), ra.mem(0x2B, T5, T4, FLAG & 0xFFFF)]
    # the microprograms: [tested instruction with the E bit, no lower] [nothing]
    base = 0x11000000 + MICRO_AT * 8
    words += [ra.lui(T3, base >> 16), ra.ori(T3, T3, base & 0xFFFF)]
    for n, (_name, upper, _kind, _arg) in enumerate(ops):
        for k, value in enumerate((NOP_LOWER, upper | E_BIT, NOP_LOWER, NOP_UPPER)):
            words += [ra.lui(T4, value >> 16), ra.ori(T4, T4, value & 0xFFFF), ra.mem(0x2B, T4, T3, n * 16 + k * 4)]
    words += [ra.lui(T2, RESULTS >> 16), ra.ori(T2, T2, RESULTS & 0xFFFF), ra.lui(T3, end >> 16), ra.ori(T3, T3, end & 0xFFFF)]
    for n in range(len(ops)):
        words += [ra.lui(T0, TABLE >> 16), ra.ori(T0, T0, TABLE & 0xFFFF)]
        outer = at()
        words += [ra.lui(T1, TABLE >> 16), ra.ori(T1, T1, TABLE & 0xFFFF)]
        inner = at()
        words += [ra.mem(0x23, T4, T0, 0), ra.mem(0x23, T5, T1, 0), qmtc2(T4, 1), qmtc2(T5, 2), vcallms(MICRO_AT + 2 * n),
                  qmfc2(T6, 3), ra.mem(0x2B, T6, T2, 0)]
        words += [ra.addiu(T1, T1, 4), ra.addiu(T2, T2, 4)]
        words += [ra.branch(0x05, T1, T3, at(), inner), 0]
        words += [ra.addiu(T0, T0, 4)]
        words += [ra.branch(0x05, T0, T3, at(), outer), 0]
    done = at()
    words[skip] = ra.branch(0x05, T5, 0, CODE + 4 * skip, done)
    words += [displaced[0], displaced[1], 0x08000000 | ((ra.HOOK + 8) >> 2), 0]
    return words


def build(include, name):
    """arith_main.cpp against one copy of the runtime's headers (its V mode runs rt/vu0.h)."""
    gen = os.path.join(arith.OUT, 'arith_gen.cpp')
    if not os.path.exists(gen):
        arith.build()
    flags = ['-std=c++17', '-fno-strict-aliasing', '-fwrapv', '-w', '-ffp-contract=off', '-frounding-math', '-O2', '-I', include]
    target = os.path.join(arith.OUT, name)
    done = subprocess.run(['nice', '-n', '15', 'clang++'] + flags + [os.path.join(HERE, 'arith_main.cpp'), gen, '-o', target],
                          capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(done.stderr[:3000])
    return name


def reference(model, kind, arg, a, b):
    """The x field of vf3 after one instruction, by vu0ref.py."""
    vu = vu0ref.Vu0(model)
    if kind in ('itof', 'ftoi', 'abs'):
        if kind == 'abs':
            return a & 0x7FFFFFFF
        return vu.itof(a, arg) if kind == 'itof' else vu.ftoi(a, arg)
    y = b                                               # ft's own field, or its x field: the same value here
    if kind == 'add':
        return vu.add(a, y)
    if kind == 'sub':
        return vu.sub(a, y)
    if kind == 'mul':
        return vu.mul(a, y)
    if kind == 'max':
        return a if vu.greater(a, y) else y
    if kind == 'mini':
        return a if vu.greater(y, a) else y
    raise KeyError(kind)


def classify(a, b, unary):
    """Which kind of operand pair: the worst of the operands."""
    def one(x):
        exp, man = (x >> 23) & 0xFF, x & 0x7FFFFF
        return 3 if exp == 255 and man else 2 if exp == 255 else 1 if exp == 0 and man else 0
    return max(one(a), 0 if unary else one(b))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--state', default=os.path.join(ROOT, 'local', 'rig-out', 'states', '04-hub.zip'))
    parser.add_argument('--frames', type=int, default=60)
    parser.add_argument('--current', default=os.path.join(PROOF, 'snap', 'recomp', 'rt.orig'), help='the runtime headers as they are')
    parser.add_argument('--proposed', default=os.path.join(PROOF, 'snap', 'vu-new'), help='the runtime headers with the proposed vu0.h')
    args = parser.parse_args()
    if not os.environ.get('RTA_DISC'):
        raise SystemExit('set RTA_DISC to the disc image')
    os.makedirs(OUT, exist_ok=True)
    image = arith.recomp.Image(os.path.join(ROOT, 'SLUS_209.73'))
    displaced = (image.word(ra.HOOK), image.word(ra.HOOK + 4))
    table = ra.edges()
    ops = forms()
    code = routine(displaced, len(table), ops)
    if CODE + 4 * len(code) > FLAG:
        raise SystemExit('the routine does not fit (%d words)' % len(code))
    patch = os.path.join(OUT, 'vu.pnach')
    with open(patch, 'w') as sink:
        sink.write('[VU]\n')
        for n, w in enumerate(table):
            sink.write('patch=1,EE,%08x,word,%08x\n' % (TABLE + 4 * n, w))
        sink.write('patch=1,EE,%08x,word,%08x\n' % (FLAG, 0))
        for n, w in enumerate(code):
            sink.write('patch=1,EE,%08x,word,%08x\n' % (CODE + 4 * n, w))
        sink.write('patch=1,EE,%08x,word,%08x\n' % (ra.HOOK + 4, 0))
        sink.write('patch=1,EE,%08x,word,%08x\n' % (ra.HOOK, 0x08000000 | (CODE >> 2)))
    n = len(table) ** 2
    size = 4 * len(ops) * n
    dump = os.path.join(OUT, 'results.bin')
    script = os.path.join(OUT, 'vu.rig')
    with open(script, 'w') as sink:
        sink.write('wait 5\npnach %s VU\nwait 30\nshow 0x%x:u32\ndump 0x%x 0x%x %s\n' % (patch, FLAG, RESULTS, size, dump))
    if os.path.exists(dump):
        os.remove(dump)
    done = subprocess.run(['nice', '-n', '15', sys.executable, '-I', '-B', os.path.join(ROOT, 'tools', 'rig', 'rig.py'),
                           '--data', os.path.join(OUT, 'data'), '--load', args.state, '--script', script,
                           '--frames', str(args.frames)], capture_output=True, text=True, errors='replace', cwd=ROOT)
    with open(os.path.join(OUT, 'rig.out'), 'w') as sink:
        sink.write(done.stdout + done.stderr)
    if not os.path.exists(dump) or os.path.getsize(dump) != size:
        print((done.stdout + done.stderr)[-1500:])
        raise SystemExit('the rig wrote no results')
    got = array.array('I')
    with open(dump, 'rb') as source:
        got.frombytes(source.read())
    binaries = [('vu0.h now', build(args.current, 'arith_vu_now')), ('vu0.h proposed', build(args.proposed, 'arith_vu_new'))]
    sets = array.array('I')
    for a in table:
        for b in table:
            sets.extend([a] * 4 + [b] * 4 + [0] * 5)
    kinds = ('finite', 'denormal', 'infinity', 'NaN')
    lines = ['Vector unit 0 in the rig (Play!, this machine) on %d operand pairs per instruction: results that differ from the rig' % n,
             'pairs by their worst operand: %s' % ', '.join(
                 '%s %d' % (kinds[c], sum(1 for a in table for b in table if classify(a, b, False) == c)) for c in range(4)),
             '%-8s %-16s %9s %9s %9s %9s' % ('', 'against', *kinds)]
    totals = {}
    for index, (name, upper, kind, arg) in enumerate(ops):
        rig = got[index * n:(index + 1) * n]
        unary = kind in ('itof', 'ftoi', 'abs')
        columns = []
        for label, binary in binaries:
            host = arith.run_bin(binary, 'V', '%x' % upper, sets, 'rigvu%d' % index, fz=True)
            columns.append((label, [host[8 * i] for i in range(n)]))
        for model in ('host', 'console'):
            columns.append(('vu0ref %s' % model, [reference(model, kind, arg, table[i // len(table)], table[i % len(table)]) for i in range(n)]))
        for label, values in columns:
            counts = [0, 0, 0, 0]
            example = None
            for i in range(n):
                if values[i] != rig[i]:
                    a, b = table[i // len(table)], table[i % len(table)]
                    c = classify(a, b, unary)
                    counts[c] += 1
                    if example is None or (c < example[0]):
                        example = (c, a, b, rig[i], values[i])
            lines.append('%-8s %-16s %9d %9d %9d %9d%s' % (name, label, *counts, '' if example is None else
                         '   e.g. %08x %08x: rig %08x, %s %08x' % (example[1], example[2], example[3], label, example[4])))
            key = totals.setdefault(label, [0, 0, 0, 0])
            for c in range(4):
                key[c] += counts[c]
    for label, counts in totals.items():
        lines.append('%-8s %-16s %9d %9d %9d %9d' % ('all', label, *counts))
    arith.report(lines, 'rigvu.txt')
    return 0


if __name__ == '__main__':
    sys.exit(main())
