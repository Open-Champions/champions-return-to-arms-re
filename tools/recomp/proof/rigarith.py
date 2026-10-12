#!/usr/bin/env python3
"""rigarith.py - the FPU instructions on edge operands inside the emulator rig, against the
runtime's arithmetic.

  python3 tools/recomp/proof/rigarith.py [--state local/rig-out/states/04-hub.zip]

tools/recomp/rt/fpu.h has a 'host' model that claims to be what the Play! emulator computes
for the game's FPU instructions on this machine.  arith.py checks that model against a
written-down reference (softf.py); this script checks it against the emulator itself:

  1. a small MIPS routine and a table of 128 edge patterns (zeroes, denormals, the smallest
     and largest exponents, exponent 255 with several mantissas) are written into unused
     memory of a saved machine state, and the first two instructions of gfx_beginFrame are
     replaced by a jump to the routine (the rig's `pnach` command; a patch file is written
     for it under local/);
  2. the routine runs once, in the game's own thread, with the emulator's own translation
     of each instruction: for every instruction it stores the result for all 128 x 128
     operand pairs, then runs the two displaced instructions and returns into the game;
  3. the results are dumped and compared with arith_host (arith.py build) on the same
     pairs, with the CPU's flush-to-zero mode set and without.

Nothing of the game is in this file: two instruction words of the executable are read at
run time so that they can be executed after the routine.
"""
import argparse
import array
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import arith                                    # noqa: E402

ROOT = arith.ROOT
OUT = os.path.join(arith.OUT, 'rig')
HOOK = 0x19D8B0                 # gfx_beginFrame: once per displayed frame
CODE, FLAG, TABLE, RESULTS = 0xE0000, 0xE0FF0, 0xE1000, 0xC00000
T0, T1, T2, T3, T4, T5 = 8, 9, 10, 11, 12, 13

OPS = ['add.s', 'sub.s', 'mul.s', 'div.s', 'sqrt.s', 'rsqrt.s', 'max.s', 'min.s', 'abs.s', 'neg.s', 'cvt.w.s',
       'cvt.s.w', 'c.eq.s', 'c.lt.s', 'c.le.s']


def edges():
    values = []
    for sign in (0, 0x80000000):
        for exp in (0, 1, 2, 24, 100, 126, 127, 128, 150, 158, 200, 253, 254, 255):
            for man in (0, 1, 0x400000, 0x7FFFFF):
                values.append(sign | (exp << 23) | man)
    values += [0x00000100, 0x80000100, 0x007FFFFE, 0x807FFFFE, 0x3EAAAAAB, 0xBEAAAAAB, 0x4F000000, 0xCF000000,
               0x4EFFFFFF, 0xCF000001, 0x7FC00000, 0xFFC00000, 0x7FA00000, 0x7F7FFFFE, 0x00800002, 0x3F800001]
    assert len(values) == 128
    return values


def lui(rt, imm):
    return 0x3C000000 | (rt << 16) | (imm & 0xFFFF)


def ori(rt, rs, imm):
    return 0x34000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def addiu(rt, rs, imm):
    return 0x24000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def mem(op, rt, rs, off):
    return (op << 26) | (rs << 21) | (rt << 16) | (off & 0xFFFF)


def branch(op, rs, rt, here, target):
    return (op << 26) | (rs << 21) | (rt << 16) | (((target - (here + 4)) >> 2) & 0xFFFF)


def routine(displaced, count):
    words = []
    at = lambda: CODE + 4 * len(words)
    fpu = dict(arith.FPU)
    end = TABLE + 4 * count
    words += [lui(T4, FLAG >> 16), mem(0x23, T5, T4, FLAG & 0xFFFF)]
    skip = len(words)
    words += [0, 0]                             # bne t5, zero, done ; nop  (filled in below)
    words += [addiu(T5, 0, 1), mem(0x2B, T5, T4, FLAG & 0xFFFF)]
    words += [lui(T2, RESULTS >> 16), ori(T2, T2, RESULTS & 0xFFFF), lui(T3, end >> 16), ori(T3, T3, end & 0xFFFF)]
    for name in OPS:
        words += [lui(T0, TABLE >> 16), ori(T0, T0, TABLE & 0xFFFF)]
        outer = at()
        words += [lui(T1, TABLE >> 16), ori(T1, T1, TABLE & 0xFFFF)]
        inner = at()
        words += [mem(0x31, 1, T0, 0), mem(0x31, 2, T1, 0), fpu[name]]
        if name.startswith('c.'):
            words += [addiu(T4, 0, 0)]
            words += [0x45000000 | 2, 0, addiu(T4, 0, 1), mem(0x2B, T4, T2, 0)]     # bc1f over the next instruction
        else:
            words += [mem(0x39, 3, T2, 0)]
        words += [addiu(T1, T1, 4), addiu(T2, T2, 4)]
        words += [branch(0x05, T1, T3, at(), inner), 0]
        words += [addiu(T0, T0, 4)]
        words += [branch(0x05, T0, T3, at(), outer), 0]
    done = at()
    words[skip] = branch(0x05, T5, 0, CODE + 4 * skip, done)
    words += [displaced[0], displaced[1], 0x08000000 | ((HOOK + 8) >> 2), 0]
    return words


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--state', default=os.path.join(ROOT, 'local', 'rig-out', 'states', '04-hub.zip'))
    parser.add_argument('--frames', type=int, default=40)
    args = parser.parse_args()
    if not os.environ.get('RTA_DISC'):
        raise SystemExit('set RTA_DISC to the disc image')
    os.makedirs(OUT, exist_ok=True)
    image = arith.recomp.Image(os.path.join(ROOT, 'SLUS_209.73'))
    displaced = (image.word(HOOK), image.word(HOOK + 4))
    table = edges()
    code = routine(displaced, len(table))
    if CODE + 4 * len(code) > FLAG:
        raise SystemExit('the routine does not fit')
    patch = os.path.join(OUT, 'arith.pnach')
    with open(patch, 'w') as sink:
        sink.write('[ARITH]\n')
        for n, w in enumerate(table):
            sink.write('patch=1,EE,%08x,word,%08x\n' % (TABLE + 4 * n, w))
        sink.write('patch=1,EE,%08x,word,%08x\n' % (FLAG, 0))
        for n, w in enumerate(code):
            sink.write('patch=1,EE,%08x,word,%08x\n' % (CODE + 4 * n, w))
        sink.write('patch=1,EE,%08x,word,%08x\n' % (HOOK + 4, 0))
        sink.write('patch=1,EE,%08x,word,%08x\n' % (HOOK, 0x08000000 | (CODE >> 2)))
    size = 4 * len(OPS) * len(table) ** 2
    dump = os.path.join(OUT, 'results.bin')
    script = os.path.join(OUT, 'arith.rig')
    with open(script, 'w') as sink:
        sink.write('wait 5\npnach %s ARITH\nwait 20\nshow 0x%x:u32\ndump 0x%x 0x%x %s\n' % (patch, FLAG, RESULTS, size, dump))
    if os.path.exists(dump):
        os.remove(dump)
    done = subprocess.run(['nice', '-n', '19', sys.executable, '-I', '-B', os.path.join(ROOT, 'tools', 'rig', 'rig.py'),
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
    pairs = array.array('I')
    for a in table:
        for b in table:
            pairs.extend((a, b, 0))
    n = len(table) ** 2
    lines = ['FPU instructions in the rig (Play!, this machine) against rt/fpu.h, %d operand pairs each' % n,
             '%-9s %14s %14s' % ('', 'host + fz', 'host, no fz')]
    worst = 0
    for index, name in enumerate(OPS):
        word = dict(arith.FPU)[name]
        rig = got[index * n:(index + 1) * n]
        row = []
        for fz in (True, False):
            host = arith.run_bin('arith_host', 'F', arith.op_index(word), pairs, 'rig%d' % index, fz=fz)
            column = 2 if name.startswith('c.') else 0
            differ = [i for i in range(n) if host[3 * i + column] != rig[i]]
            row.append(differ)
        worst = max(worst, len(row[0]))
        lines.append('%-9s %14d %14d' % (name, len(row[0]), len(row[1])))
        for label, differ in (('fz', row[0]), ('no fz', row[1])):
            for i in differ[:2]:
                host = arith.run_bin('arith_host', 'F', arith.op_index(word), pairs[3 * i:3 * i + 3], 'one', fz=label == 'fz')
                lines.append('    %-5s %08x %08x: rig %08x, fpu.h %08x' % (label, pairs[3 * i], pairs[3 * i + 1], rig[i],
                                                                         host[2 if name.startswith('c.') else 0]))
    arith.report(lines, 'rig.txt')
    return 1 if worst else 0


if __name__ == '__main__':
    sys.exit(main())
