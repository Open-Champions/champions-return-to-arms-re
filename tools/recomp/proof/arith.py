#!/usr/bin/env python3
"""arith.py - corner cases of the translated code's arithmetic, operation by operation.

  python3 tools/recomp/proof/arith.py build
  python3 tools/recomp/proof/arith.py fpu  [--chunk N] [--jobs N] [--only NAME,...]
  python3 tools/recomp/proof/arith.py int  [--chunk N] [--jobs N]
  python3 tools/recomp/proof/arith.py vu   [--chunk N] [--jobs N]

Every instruction is compiled from the C++ text tools/recomp/recomp.py emits for it
(arith_gen.cpp, one function per instruction word), so the translator's choice of helper
and argument order is part of what is tested, not only rt/fpu.h and rt/mmi.h.

fpu   every FPU instruction of the executable, on directed operand sets (below):
        A  the -DFPU_PS2 build against the interpreter (tools/ee_emu.py, model 'ps2'):
           the two must agree bit for bit - this is the arithmetic of the function-by-
           function proof;
        B  the runtime build (the 'host' model) against softf.py: IEEE single precision,
           rounding toward zero, operands clamped - once with denormals kept (how the
           runtime's threads run today) and once with the CPU's flush-to-zero mode set
           (how the Play! emulator runs the game);
        C  counted, not required to be zero: where the host model and the interpreter's
           model give different results, by cause; and where flush-to-zero changes the
           host model's result.
int   the multimedia instructions (rt/mmi.h), multiply/divide (rt/recomp.h) and the
      integer instructions with edge operands, against the interpreter.
vu    every upper-instruction form rt/vu0.h implements, one instruction per run, against
      softf.py (the interpreter has no vector unit), with and without flush-to-zero.

Operand sets per instruction: the product of an edge list with itself (zeroes, denormals,
the smallest and largest exponents, exponent 255 with every kind of mantissa, powers of
two and their neighbours), then seeded sets of --chunk each: uniform bit patterns, close
exponents, cancelling pairs, products and quotients at the overflow and underflow
boundaries, denormal operands, infinity/NaN patterns, integer-valued numbers.

Writes local/recomp-out/proof/arith/<name>.txt and prints the tables.
"""
import argparse
import array
import multiprocessing
import os
import random
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RECOMP = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(RECOMP))
sys.path.insert(0, RECOMP)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, HERE)
import recomp                                   # noqa: E402
import ee_emu                                   # noqa: E402
import softf                                    # noqa: E402

OUT = os.path.join(ROOT, 'local', 'recomp-out', 'proof', 'arith')
M32, M64 = 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF
R3_LO, R3_HI, F3 = 0x0123456789ABCDEF, 0xFEDCBA9876543210, 0xDEADBEEF


# ---- the instructions ---------------------------------------------------------------------

def cop1(funct, fmt=0x10):
    return (0x11 << 26) | (fmt << 21) | (2 << 16) | (1 << 11) | (3 << 6) | funct


def special(funct, sa=0, rd=3):
    return (1 << 21) | (2 << 16) | (rd << 11) | (sa << 6) | funct


def mmi(funct, sa=0, rd=3):
    return (0x1C << 26) | (1 << 21) | (2 << 16) | (rd << 11) | (sa << 6) | funct


FPU = [('add.s', cop1(0x00)), ('sub.s', cop1(0x01)), ('mul.s', cop1(0x02)), ('div.s', cop1(0x03)),
       ('sqrt.s', cop1(0x04)), ('abs.s', cop1(0x05)), ('mov.s', cop1(0x06)), ('neg.s', cop1(0x07)),
       ('rsqrt.s', cop1(0x16)), ('adda.s', cop1(0x18)), ('suba.s', cop1(0x19)), ('mula.s', cop1(0x1A)),
       ('madd.s', cop1(0x1C)), ('msub.s', cop1(0x1D)), ('madda.s', cop1(0x1E)), ('msuba.s', cop1(0x1F)),
       ('cvt.w.s', cop1(0x24)), ('max.s', cop1(0x28)), ('min.s', cop1(0x29)), ('c.f.s', cop1(0x30)),
       ('c.eq.s', cop1(0x32)), ('c.lt.s', cop1(0x34)), ('c.le.s', cop1(0x36)), ('cvt.s.w', cop1(0x20, 0x14))]


def int_instructions():
    out = []
    for name, funct in (('sll', 0x00), ('srl', 0x02), ('sra', 0x03), ('dsll', 0x38), ('dsrl', 0x3A), ('dsra', 0x3B),
                        ('dsll32', 0x3C), ('dsrl32', 0x3E), ('dsra32', 0x3F)):
        for sa in (0, 1, 13, 31):
            out.append(('%s %d' % (name, sa), special(funct, sa)))
    for name, funct in (('sllv', 0x04), ('srlv', 0x06), ('srav', 0x07), ('dsllv', 0x14), ('dsrlv', 0x16),
                        ('dsrav', 0x17), ('movz', 0x0A), ('movn', 0x0B), ('mfhi', 0x10), ('mthi', 0x11),
                        ('mflo', 0x12), ('mtlo', 0x13), ('mult', 0x18), ('multu', 0x19), ('addu', 0x21),
                        ('subu', 0x23), ('and', 0x24), ('or', 0x25), ('xor', 0x26), ('nor', 0x27), ('mfsa', 0x28),
                        ('slt', 0x2A), ('sltu', 0x2B), ('daddu', 0x2D), ('dsubu', 0x2F)):
        out.append((name, special(funct)))
    out += [('mult (no rd)', special(0x18, rd=0)), ('div', special(0x1A, rd=0)), ('divu', special(0x1B, rd=0))]
    out += [('madd', mmi(0x00)), ('maddu', mmi(0x01)), ('plzcw', mmi(0x04)), ('mfhi1', mmi(0x10)), ('mthi1', mmi(0x11)),
            ('mflo1', mmi(0x12)), ('mtlo1', mmi(0x13)), ('mult1', mmi(0x18)), ('multu1', mmi(0x19)),
            ('div1', mmi(0x1A, rd=0)), ('divu1', mmi(0x1B, rd=0))]
    for name, funct in (('psllh', 0x34), ('psrlh', 0x36), ('psrah', 0x37), ('psllw', 0x3C), ('psrlw', 0x3E), ('psraw', 0x3F)):
        for sa in (0, 1, 7, 15, 16, 31):
            out.append(('%s %d' % (name, sa), mmi(funct, sa)))
    for funct, table in ((0x08, recomp.MMI0), (0x28, recomp.MMI1), (0x09, recomp.MMI2), (0x29, recomp.MMI3)):
        for sa in sorted(table):
            out.append((table[sa], mmi(funct, sa)))
    return out


def vu_forms():
    """(name, upper word, kind, argument) for every upper form vu0.h implements; fs = vf1,
    ft = vf2, fd = vf3 (ft = vf3 where the form writes ft)."""
    forms = []

    def word(op, dest, ft=2, fs=1, fd=3):
        return (dest << 21) | (ft << 16) | (fs << 11) | (fd << 6) | op

    def sp(idx, dest, ft=2, fs=1):
        return (dest << 21) | (ft << 16) | (fs << 11) | ((idx >> 2) << 6) | 0x3C | (idx & 3)

    for dest in (0xF, 0x9, 0x4):
        tag = {0xF: '', 0x9: '.xw', 0x4: '.y'}[dest]
        for base, kind in ((0x00, 'add'), (0x04, 'sub'), (0x08, 'madd'), (0x0C, 'msub'), (0x18, 'mul'),
                           (0x10, 'max'), (0x14, 'mini')):
            for bc in range(4):
                forms.append(('%s%s%s' % (kind.upper(), 'xyzw'[bc], tag), word(base + bc, dest), kind, ('bc', bc)))
        for op, kind in ((0x1E, 'mul'), (0x22, 'add'), (0x26, 'sub'), (0x23, 'madd'), (0x27, 'msub')):
            forms.append(('%si%s' % (kind.upper(), tag), word(op, dest), kind, ('i', 0)))
        for op, kind in ((0x28, 'add'), (0x2C, 'sub'), (0x2A, 'mul'), (0x29, 'madd'), (0x2D, 'msub'), (0x2B, 'max'), (0x2F, 'mini')):
            forms.append(('%s%s' % (kind.upper(), tag), word(op, dest), kind, ('ft', 0)))
        for base, kind in ((0x00, 'add'), (0x04, 'sub'), (0x08, 'madd'), (0x0C, 'msub'), (0x18, 'mul')):
            for bc in range(4):
                forms.append(('%sA%s%s' % (kind.upper(), 'xyzw'[bc], tag), sp(base + bc, dest), kind + 'a', ('bc', bc)))
        for n, scale in enumerate((0, 4, 12, 15)):
            forms.append(('ITOF%d%s' % (scale, tag), sp(0x10 + n, dest, ft=3), 'itof', scale))
            forms.append(('FTOI%d%s' % (scale, tag), sp(0x14 + n, dest, ft=3), 'ftoi', scale))
        forms.append(('MULAi%s' % tag, sp(0x1E, dest), 'mula', ('i', 0)))
        for idx, kind in ((0x28, 'adda'), (0x2C, 'suba'), (0x2A, 'mula'), (0x29, 'madda'), (0x2D, 'msuba')):
            forms.append(('%s%s' % (kind.upper(), tag), sp(idx, dest), kind, ('ft', 0)))
        forms.append(('ABS%s' % tag, sp(0x1D, dest, ft=3), 'abs', 0))
    return forms


# ---- build --------------------------------------------------------------------------------

def build(_args=None):
    os.makedirs(OUT, exist_ok=True)
    words = [w for _, w in FPU] + [w for _, w in int_instructions()]
    lines = ['// generated by tools/recomp/proof/arith.py - do not commit', '#include "recomp.h"']
    for n, w in enumerate(words):
        text = recomp.simple(0x100000, w)
        if 'rt_unimpl' in text:
            raise SystemExit('the translator has no translation for %08x' % w)
        lines.append('static void op_%d(Ctx* c) { %s }' % (n, text))
    lines.append('extern void (*const g_arith_ops[])(Ctx*) = { %s };' % ', '.join('op_%d' % n for n in range(len(words))))
    lines.append('extern const unsigned g_arith_count = %d;' % len(words))
    gen = os.path.join(OUT, 'arith_gen.cpp')
    with open(gen, 'w') as sink:
        sink.write('\n'.join(lines) + '\n')
    flags = ['-std=c++17', '-fno-strict-aliasing', '-fwrapv', '-w', '-ffp-contract=off', '-frounding-math',
             '-I', os.path.join(RECOMP, 'rt')]
    for name, extra in (('arith_ps2', ['-O1', '-DFPU_PS2']), ('arith_host', ['-O2'])):
        done = subprocess.run(['nice', '-n', '19', 'clang++'] + flags + extra + [os.path.join(HERE, 'arith_main.cpp'), gen,
                               '-o', os.path.join(OUT, name)], capture_output=True, text=True)
        if done.returncode:
            raise SystemExit(done.stderr[:3000])
    print('built %s/arith_ps2 and arith_host: %d instructions' % (OUT, len(words)))
    return 0


def op_index(word):
    words = [w for _, w in FPU] + [w for _, w in int_instructions()]
    return words.index(word)


def run_bin(binary, kind, op, data, tag, fz=False, typecode='I'):
    src = os.path.join(OUT, 'in-%s.bin' % tag)
    dst = os.path.join(OUT, 'out-%s.bin' % tag)
    with open(src, 'wb') as sink:
        sink.write(data.tobytes())
    command = ['nice', '-n', '19', os.path.join(OUT, binary), kind, str(op), src, dst] + (['fz'] if fz else [])
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError('%s failed: %s' % (' '.join(command), done.stderr[:300]))
    out = array.array(typecode)
    with open(dst, 'rb') as source:
        out.frombytes(source.read())
    os.remove(src)
    os.remove(dst)
    return out


# ---- operand sets -------------------------------------------------------------------------

def fp_edges():
    values = set()
    for sign in (0, 0x80000000):
        for exp in (0, 1, 2, 23, 24, 25, 64, 100, 103, 126, 127, 128, 129, 150, 151, 157, 158, 159, 190, 200, 230,
                    253, 254, 255):
            for man in (0, 1, 2, 0x400000, 0x7FFFFF, 0x7FFFFE, 0x555555, 0x2AAAAA, 0x000100, 0x400001):
                values.add(sign | (exp << 23) | man)
    return sorted(values)


SPECIALS = (0x7F800000, 0xFF800000, 0x7F800001, 0x7FC00000, 0xFFC00000, 0x7FFFFFFF, 0xFFFFFFFF, 0x7FA00000,
            0x7F7FFFFF, 0xFF7FFFFF, 0x7FBFFFFF, 0xFFC00001)
INT_EDGES = (0, 1, 2, 3, 0x7FFFFFFF, 0x80000000, 0x80000001, 0xFFFFFFFF, 0xFFFFFFFE, 0x00FFFFFF, 0x01000000,
             0x01000001, 0x007FFFFF, 0x00800000, 0x00800001, 0x7FFFFF80, 0x7FFFFFC0, 0x7FFFFF7F, 0xFF000000,
             0xFEFFFFFF, 0x40000000, 0xC0000000, 0x0000FFFF, 0x00010000, 0xFFFF0000, 0x55555555, 0xAAAAAAAA)


def mantissa(rng):
    kind = rng.random()
    if kind < 0.6:
        return rng.getrandbits(23)
    if kind < 0.7:
        return 0
    if kind < 0.8:
        return 0x7FFFFF
    if kind < 0.9:
        return 1 << rng.randrange(23)
    return 0x7FFFFF ^ (1 << rng.randrange(23))


def fl(rng, exp):
    return (rng.getrandbits(1) << 31) | (max(0, min(255, exp)) << 23) | mantissa(rng)


FP_RECIPES = ('edges', 'uniform', 'close', 'cancel', 'boundary', 'denormal', 'special', 'integer')


def fp_sets(recipe, seed, count):
    """array('I') of (a, b, acc) triples."""
    rng = random.Random('%s/%d' % (recipe, seed))
    out = array.array('I')
    if recipe == 'edges':
        edges = fp_edges()
        n = 0
        for a in edges:
            for b in edges:
                out.extend((a, b, edges[(n * 7919) % len(edges)]))
                n += 1
        return out
    for _ in range(count):
        if recipe == 'uniform':
            a, b, acc = rng.getrandbits(32), rng.getrandbits(32), rng.getrandbits(32)
        elif recipe == 'close':
            ea = rng.randrange(1, 255)
            a, b = fl(rng, ea), fl(rng, ea + rng.randrange(-30, 31))
            acc = fl(rng, ea + ((b >> 23) & 0xFF) - 127 + rng.randrange(-30, 31))
        elif recipe == 'cancel':
            a = fl(rng, rng.randrange(1, 255))
            b = ((a ^ 0x80000000) + rng.randrange(-3, 4)) & M32
            if rng.random() < 0.3:
                b = (b + (rng.choice((-1, 1)) << 23)) & M32
            acc = fl(rng, ((a >> 23) & 0xFF) * 2 - 127 + rng.randrange(-3, 4))
        elif recipe == 'boundary':
            kind = rng.randrange(4)
            ea = rng.randrange(1, 255)
            if kind == 0:                       # product at the overflow boundary
                eb = 382 - ea + rng.randrange(-3, 4)
            elif kind == 1:                     # product at the underflow boundary
                eb = 128 - ea + rng.randrange(-3, 4)
            elif kind == 2:                     # quotient at the overflow boundary
                eb = ea - 127 + rng.randrange(-3, 4)
            else:                               # quotient at the underflow boundary
                eb = ea + 127 + rng.randrange(-3, 4)
            a, b = fl(rng, ea), fl(rng, eb)
            acc = fl(rng, rng.choice((1, 2, 253, 254, 255, rng.randrange(256))))
        elif recipe == 'denormal':
            a, b, acc = fl(rng, rng.randrange(256)), fl(rng, rng.randrange(256)), fl(rng, rng.randrange(256))
            which = rng.randrange(7) + 1
            if which & 1:
                a = fl(rng, rng.choice((0, 0, 1, 2)))
            if which & 2:
                b = fl(rng, rng.choice((0, 0, 1, 2)))
            if which & 4:
                acc = fl(rng, rng.choice((0, 0, 1)))
        elif recipe == 'special':
            a, b, acc = fl(rng, rng.randrange(256)), fl(rng, rng.randrange(256)), fl(rng, rng.randrange(256))
            which = rng.randrange(7) + 1
            pick = lambda: rng.choice(SPECIALS) if rng.random() < 0.5 else fl(rng, rng.choice((254, 255, 255)))
            if which & 1:
                a = pick()
            if which & 2:
                b = pick()
            if which & 4:
                acc = pick()
        else:                                   # integer: whole numbers, and patterns read as integers
            if rng.random() < 0.5:
                a = rng.choice(INT_EDGES) if rng.random() < 0.3 else rng.getrandbits(rng.randrange(1, 33))
                b = rng.choice(INT_EDGES) if rng.random() < 0.3 else rng.getrandbits(rng.randrange(1, 33))
                acc = rng.getrandbits(32)
            else:
                a = fl(rng, rng.randrange(120, 162))
                b = fl(rng, rng.randrange(120, 162))
                acc = fl(rng, rng.randrange(120, 162))
        out.extend((a, b, acc))
    return out


# ---- references ---------------------------------------------------------------------------

class Interp:
    def __init__(self, model='ps2'):
        self.emu = ee_emu.EE(None, fpu_model=model)
        self.emu.div_zero = 'r5900'
        self.ops = self.emu._ops

    def fpu(self, word, a, b, acc):
        emu = self.emu
        f = emu.f
        f[1], f[2], f[3] = a, b, F3
        emu.acc = acc
        emu.fcr31 = 0x01000001
        self.ops[word >> 26](word)
        return f[3], emu.acc, (emu.fcr31 >> 23) & 1


def soft_fpu(name, a, b, acc, fz):
    """(f3, acc, compare bit) of the host model."""
    s = softf
    if name == 'add.s':
        return s.host_add(a, b, fz), acc, 0
    if name == 'sub.s':
        return s.host_sub(a, b, fz), acc, 0
    if name == 'mul.s':
        return s.host_mul(a, b, fz), acc, 0
    if name == 'div.s':
        return s.host_div(a, b, fz), acc, 0
    if name == 'sqrt.s':
        return s.host_sqrt(b, fz), acc, 0
    if name == 'abs.s':
        return a & 0x7FFFFFFF, acc, 0
    if name == 'mov.s':
        return a, acc, 0
    if name == 'neg.s':
        return a ^ 0x80000000, acc, 0
    if name == 'rsqrt.s':
        return s.host_rsqrt(a, b, fz), acc, 0
    if name == 'adda.s':
        return F3, s.host_add(a, b, fz), 0
    if name == 'suba.s':
        return F3, s.host_sub(a, b, fz), 0
    if name == 'mula.s':
        return F3, s.host_mul(a, b, fz), 0
    if name == 'madd.s':
        return s.host_add(acc, s.host_mul(a, b, fz), fz), acc, 0
    if name == 'msub.s':
        return s.host_sub(acc, s.host_mul(a, b, fz), fz), acc, 0
    if name == 'madda.s':
        return F3, s.host_add(acc, s.host_mul(a, b, fz), fz), 0
    if name == 'msuba.s':
        return F3, s.host_sub(acc, s.host_mul(a, b, fz), fz), 0
    if name == 'cvt.w.s':
        return s.host_to_int(a), acc, 0
    if name == 'max.s':
        return s.host_max(a, b, fz), acc, 0
    if name == 'min.s':
        return s.host_min(a, b, fz), acc, 0
    if name == 'c.f.s':
        return F3, acc, 0
    if name == 'c.eq.s':
        return F3, acc, 1 if s.host_cmp(a, b, fz) == 0 else 0
    if name == 'c.lt.s':
        return F3, acc, 1 if s.host_cmp(a, b, fz) < 0 else 0
    if name == 'c.le.s':
        return F3, acc, 1 if s.host_cmp(a, b, fz) <= 0 else 0
    if name == 'cvt.s.w':
        return s.host_from_int(a), acc, 0
    raise KeyError(name)


USES = {'sqrt.s': 'b', 'abs.s': 'a', 'mov.s': 'a', 'neg.s': 'a', 'cvt.w.s': 'a', 'cvt.s.w': '', 'c.f.s': '',
        'madd.s': 'abc', 'msub.s': 'abc', 'madda.s': 'abc', 'msuba.s': 'abc'}


def cause(name, a, b, acc, host, ps2):
    """Why the host model and the interpreter's model differ on one operand set."""
    used = USES.get(name, 'ab')
    ops = [v for k, v in (('a', a), ('b', b), ('c', acc)) if k in used]
    if any((v & 0x7F800000) == 0x7F800000 for v in ops):
        return 'operand with exponent 255 (clamped to FLT_MAX by the host model)'
    if any((v & 0x7F800000) == 0 and (v & 0x7FFFFF) for v in ops):
        return 'denormal operand (zero on the console, a number for a host without flush-to-zero)'
    h, p = host[0] if host[0] != F3 else host[1], ps2[0] if ps2[0] != F3 else ps2[1]
    if (p & 0x7FFFFFFF) == 0x7FFFFFFF or (h & 0x7F800000) == 0x7F800000 or (h & 0x7FFFFFFF) == 0x7F7FFFFF:
        return 'overflow (console: 0x7fffffff, host: FLT_MAX)'
    if (h & 0x7F800000) == 0 or (p & 0x7F800000) == 0:
        return 'underflow (console: zero below the smallest normal, host: denormal or zero)'
    if abs((h & 0x7FFFFFFF) - (p & 0x7FFFFFFF)) <= 1 and (h ^ p) < 0x80000000:
        return 'last bit (the console adder keeps fewer bits than IEEE truncation)'
    return 'other'


def fpu_job(job):
    index, name, word, recipe, seed, count = job
    sets = fp_sets(recipe, seed, count)
    n = len(sets) // 3
    op = op_index(word)
    tag = 'f%d-%s-%d-%d' % (index, recipe, seed, os.getpid())
    got_ps2 = run_bin('arith_ps2', 'F', op, sets, tag)
    got_host = run_bin('arith_host', 'F', op, sets, tag)
    got_fz = run_bin('arith_host', 'F', op, sets, tag, fz=True)
    interp = Interp('ps2')
    bad = {'A': 0, 'B': 0, 'Bfz': 0}
    first = {}
    causes = {}
    fz_changes = 0
    for i in range(n):
        a, b, acc = sets[3 * i], sets[3 * i + 1], sets[3 * i + 2]
        ps2 = tuple(got_ps2[3 * i:3 * i + 3])
        host = tuple(got_host[3 * i:3 * i + 3])
        fz = tuple(got_fz[3 * i:3 * i + 3])
        ref = interp.fpu(word, a, b, acc)
        if ps2 != ref:
            bad['A'] += 1
            first.setdefault('A', (a, b, acc, ps2, ref))
        soft = soft_fpu(name, a, b, acc, False)
        if host != soft:
            bad['B'] += 1
            first.setdefault('B', (a, b, acc, host, soft))
        soft = soft_fpu(name, a, b, acc, True)
        if fz != soft:
            bad['Bfz'] += 1
            first.setdefault('Bfz', (a, b, acc, fz, soft))
        if host != ps2:
            why = cause(name, a, b, acc, host, ps2)
            causes[why] = causes.get(why, 0) + 1
            first.setdefault('C ' + why, (a, b, acc, host, ps2))
        if host != fz:
            fz_changes += 1
            first.setdefault('fz', (a, b, acc, host, fz))
    return name, recipe, n, bad, causes, fz_changes, first


def report(lines, name):
    text = '\n'.join(lines)
    print(text)
    with open(os.path.join(OUT, name), 'w') as sink:
        sink.write(text + '\n')


def fpu(args):
    wanted = set(args.only.split(',')) if args.only else None
    jobs = []
    for index, (name, word) in enumerate(FPU):
        if wanted and name not in wanted:
            continue
        for recipe in FP_RECIPES:
            jobs.append((index, name, word, recipe, 1, args.chunk))
    start = time.time()
    per = {}
    with multiprocessing.Pool(args.jobs) as pool:
        for done, result in enumerate(pool.imap_unordered(fpu_job, jobs)):
            name, recipe, n, bad, causes, fz_changes, first = result
            row = per.setdefault(name, {'n': 0, 'A': 0, 'B': 0, 'Bfz': 0, 'causes': {}, 'fz': 0, 'first': {}})
            row['n'] += n
            row['fz'] += fz_changes
            for key in ('A', 'B', 'Bfz'):
                row[key] += bad[key]
            for key, value in causes.items():
                row['causes'][key] = row['causes'].get(key, 0) + value
            for key, value in first.items():
                row['first'].setdefault(key, value)
            if (done + 1) % 16 == 0:
                print('  %d/%d jobs, %.0f s' % (done + 1, len(jobs), time.time() - start), flush=True)
    lines = ['FPU instructions: operand sets per instruction, and results that differ',
             '%-9s %9s | %8s %8s %8s | %9s %9s' % ('', 'sets', 'A ps2', 'B host', 'B host+fz', 'host!=ps2', 'fz changes')]
    total = {}
    for name, _ in FPU:
        row = per.get(name)
        if not row:
            continue
        lines.append('%-9s %9d | %8d %8d %8d | %9d %9d' % (name, row['n'], row['A'], row['B'], row['Bfz'],
                                                        sum(row['causes'].values()), row['fz']))
        for key, value in row['causes'].items():
            total[key] = total.get(key, 0) + value
    lines.append('A: FPU_PS2 build against the interpreter; B: runtime build against softf.py without and with flush-to-zero')
    lines.append('host != ps2 by cause:')
    for key, value in sorted(total.items(), key=lambda kv: -kv[1]):
        lines.append('  %9d  %s' % (value, key))
    lines.append('first examples (a, b, acc -> f3, acc, compare bit):')
    for name, _ in FPU:
        row = per.get(name)
        if not row:
            continue
        for key, (a, b, acc, x, y) in sorted(row['first'].items()):
            if key in ('A', 'B', 'Bfz') or key == 'fz' or key.startswith('C other'):
                lines.append('  %-9s %-10s %08x %08x %08x -> %s | %s' % (name, key[:10], a, b, acc,
                             ' '.join('%08x' % v for v in x), ' '.join('%08x' % v for v in y)))
    report(lines, 'fpu.txt')
    return 1 if any(row['A'] or row['B'] or row['Bfz'] for row in per.values()) else 0


# ---- integer and multimedia instructions -----------------------------------------------------

LANE_EDGES = {8: (0, 1, 0x7F, 0x80, 0x81, 0xFF, 0xFE), 16: (0, 1, 0x7FFF, 0x8000, 0x8001, 0xFFFF, 0xFFFE, 0xFF, 0x100),
              32: INT_EDGES, 64: (0, 1, M64, 1 << 63, (1 << 63) - 1, 0xFFFFFFFF, 0x100000000, 0x7FFFFFFF, 0x80000000,
                                  0xFFFFFFFF80000000, 0xFFFFFFFF7FFFFFFF)}


def quad(rng):
    bits = rng.choice((8, 16, 32, 32, 64))
    value = 0
    for lane in range(128 // bits):
        v = rng.choice(LANE_EDGES[bits]) if rng.random() < 0.5 else rng.getrandbits(bits)
        value |= v << (lane * bits)
    return value


def word64(rng):
    kind = rng.random()
    v = rng.choice(INT_EDGES) if kind < 0.4 else rng.getrandbits(rng.randrange(1, 33))
    if kind > 0.9:
        return rng.getrandbits(64)              # not a sign-extended 32-bit value
    return v | 0xFFFFFFFF00000000 if v & 0x80000000 else v


def int_sets(seed, count):
    rng = random.Random('int/%d' % seed)
    out = array.array('Q')
    for _ in range(count):
        if rng.random() < 0.5:
            a, b = quad(rng), quad(rng)
        else:
            a, b = word64(rng) | (rng.getrandbits(64) << 64), word64(rng) | (rng.getrandbits(64) << 64)
        if rng.random() < 0.1:
            b = a
        out.extend((a & M64, a >> 64, b & M64, b >> 64, word64(rng), word64(rng), word64(rng), word64(rng),
                    rng.choice((rng.randrange(16), rng.randrange(256), rng.getrandbits(32)))))
    return out


def int_job(job):
    index, name, word, seed, count = job
    sets = int_sets(seed, count)
    n = len(sets) // 9
    got = run_bin('arith_ps2', 'M', op_index(word), sets, 'm%d-%d-%d' % (index, seed, os.getpid()), typecode='Q')
    interp = Interp('ps2')
    emu = interp.emu
    r, rh = emu.r, emu.rh
    handler = interp.ops[word >> 26]
    bad, first = 0, None
    for i in range(n):
        q = sets[9 * i:9 * i + 9]
        r[1], rh[1], r[2], rh[2] = q[0], q[1], q[2], q[3]
        emu.hi, emu.lo, emu.hi1, emu.lo1, emu.sa = q[4], q[5], q[6], q[7], q[8] & M32
        r[3], rh[3] = R3_LO, R3_HI
        handler(word)
        r[0] = rh[0] = 0
        ref = (r[3], rh[3], emu.hi, emu.lo, emu.hi1, emu.lo1)
        if tuple(got[6 * i:6 * i + 6]) != ref:
            bad += 1
            if first is None:
                first = (tuple(q), tuple(got[6 * i:6 * i + 6]), ref)
    return name, n, bad, first


def integer(args):
    jobs = [(index, name, word, seed, args.chunk) for index, (name, word) in enumerate(int_instructions())
            for seed in range(args.seeds)]
    per = {}
    start = time.time()
    with multiprocessing.Pool(args.jobs) as pool:
        for done, (name, n, bad, first) in enumerate(pool.imap_unordered(int_job, jobs)):
            row = per.setdefault(name, [0, 0, None])
            row[0] += n
            row[1] += bad
            row[2] = row[2] or first
            if (done + 1) % 40 == 0:
                print('  %d/%d jobs, %.0f s' % (done + 1, len(jobs), time.time() - start), flush=True)
    lines = ['integer, multiply/divide and multimedia instructions against the interpreter',
             '%d instruction words, %d operand sets, %d different' % (
                 len(per), sum(row[0] for row in per.values()), sum(row[1] for row in per.values()))]
    for name, _ in int_instructions():
        row = per[name]
        lines.append('%-14s %9d sets %8d different' % (name, row[0], row[1]))
        if row[2]:
            q, got, ref = row[2]
            lines.append('    r1=%016x:%016x r2=%016x:%016x hi=%x lo=%x hi1=%x lo1=%x sa=%x' % (q[1], q[0], q[3], q[2], q[4], q[5], q[6], q[7], q[8]))
            lines.append('    translation %s' % ' '.join('%x' % v for v in got))
            lines.append('    interpreter %s' % ' '.join('%x' % v for v in ref))
    report(lines, 'int.txt')
    return 1 if any(row[1] for row in per.values()) else 0


# ---- vector unit 0 ------------------------------------------------------------------------------

def finite(rng):
    kind = rng.random()
    if kind < 0.15:
        return fl(rng, rng.choice((0, 0, 0, 1, 2)))
    if kind < 0.25:
        return fl(rng, rng.choice((253, 254, 254)))
    if kind < 0.6:
        return fl(rng, rng.randrange(100, 160))
    return fl(rng, rng.randrange(0, 255))


def vu_sets(seed, count, kind):
    rng = random.Random('vu/%s/%d' % (kind, seed))
    out = array.array('I')
    for _ in range(count):
        row = [finite(rng) for _ in range(13)]
        if kind == 'itof':
            row[:4] = [rng.choice(INT_EDGES) if rng.random() < 0.3 else rng.getrandbits(rng.randrange(1, 33)) for _ in range(4)]
        if rng.random() < 0.2:                  # near cancellation in one lane
            lane = rng.randrange(4)
            row[4 + lane] = ((row[lane] ^ 0x80000000) + rng.randrange(-2, 3)) & M32
            if (row[4 + lane] & 0x7F800000) == 0x7F800000:
                row[4 + lane] = row[lane]
        out.extend(row)
    return out


def vu_reference(kind, arg, dest, q, fz):
    """(vf3 x4, acc x4) after one upper instruction."""
    s = softf
    a, b, acc, i = q[0:4], q[4:8], list(q[8:12]), q[12]
    out = [F3] * 4

    def select(x, y, want_max):
        kx, ky = s.order(s.flush(x) if fz else x), s.order(s.flush(y) if fz else y)
        return x if (kx > ky if want_max else kx < ky) else y

    for k in range(4):
        if not (dest >> (3 - k)) & 1:
            continue
        x = a[k]
        if kind in ('itof', 'ftoi', 'abs'):
            if kind == 'abs':
                out[k] = x & 0x7FFFFFFF
            elif kind == 'itof':
                value = s.from_int(x)
                out[k] = value if arg == 0 else s.rz_mul(value, (127 - arg) << 23, fz)
            else:
                out[k] = s.to_int(s.rz_mul(x, (127 + arg) << 23, fz))
            continue
        y = i if arg[0] == 'i' else (b[arg[1]] if arg[0] == 'bc' else b[k])
        to_acc = kind in ('adda', 'suba', 'mula', 'madda', 'msuba')
        base = kind[:-1] if to_acc else kind
        if base == 'add':
            value = s.rz_add(x, y, fz)
        elif base == 'sub':
            value = s.rz_sub(x, y, fz)
        elif base == 'mul':
            value = s.rz_mul(x, y, fz)
        elif base == 'madd':
            value = s.rz_add(acc[k], s.rz_mul(x, y, fz), fz)
        elif base == 'msub':
            value = s.rz_sub(acc[k], s.rz_mul(x, y, fz), fz)
        elif base == 'max':
            value = select(x, y, True)
        elif base == 'mini':
            value = select(x, y, False)
        else:
            raise KeyError(kind)
        if to_acc:
            acc[k] = value
        else:
            out[k] = value
    return tuple(out) + tuple(acc)


def vu_job(job):
    index, name, upper, kind, arg, seed, count = job
    dest = (upper >> 21) & 15
    sets = vu_sets(seed, count, kind)
    n = len(sets) // 13
    result = [name, n * bin(dest).count('1'), 0, 0, None]
    for fz in (False, True):
        got = run_bin('arith_host', 'V', '%x' % upper, sets, 'v%d-%d-%d' % (index, seed, os.getpid()), fz=fz)
        for i in range(n):
            q = sets[13 * i:13 * i + 13]
            ref = vu_reference(kind, arg, dest, q, fz)
            if tuple(got[8 * i:8 * i + 8]) != ref:
                result[3 if fz else 2] += 1
                if result[4] is None:
                    result[4] = (fz, tuple(q), tuple(got[8 * i:8 * i + 8]), ref)
    return result


def vu(args):
    jobs = [(index, name, upper, kind, arg, seed, args.chunk) for index, (name, upper, kind, arg) in enumerate(vu_forms())
            for seed in range(args.seeds)]
    per = {}
    start = time.time()
    with multiprocessing.Pool(args.jobs) as pool:
        for done, (name, n, bad, bad_fz, first) in enumerate(pool.imap_unordered(vu_job, jobs)):
            row = per.setdefault(name, [0, 0, 0, None])
            row[0] += n
            row[1] += bad
            row[2] += bad_fz
            row[3] = row[3] or first
            if (done + 1) % 40 == 0:
                print('  %d/%d jobs, %.0f s' % (done + 1, len(jobs), time.time() - start), flush=True)
    lines = ['vector unit 0 (rt/vu0.h), one upper instruction per run, against softf.py',
             '%d instruction forms, %d lane results without and %d with flush-to-zero; different: %d and %d' % (
                 len(per), sum(r[0] for r in per.values()), sum(r[0] for r in per.values()),
                 sum(r[1] for r in per.values()), sum(r[2] for r in per.values()))]
    groups = {}
    for name, upper, kind, arg in vu_forms():
        row = per[name]
        g = groups.setdefault(kind, [0, 0, 0, 0])
        g[0] += 1
        g[1] += row[0]
        g[2] += row[1]
        g[3] += row[2]
        if row[3]:
            fz, q, got, ref = row[3]
            lines.append('  %s%s: in %s' % (name, ' (fz)' if fz else '', ' '.join('%08x' % v for v in q)))
            lines.append('      vu0.h  %s' % ' '.join('%08x' % v for v in got))
            lines.append('      softf  %s' % ' '.join('%08x' % v for v in ref))
    lines.append('%-8s %6s %12s %10s %10s' % ('kind', 'forms', 'lane results', 'different', 'with fz'))
    for kind, g in groups.items():
        lines.append('%-8s %6d %12d %10d %10d' % (kind, g[0], g[1], g[2], g[3]))
    report(lines, 'vu.txt')
    return 1 if any(r[1] or r[2] for r in per.values()) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('build')
    for name in ('fpu', 'int', 'vu'):
        p = sub.add_parser(name)
        p.add_argument('--chunk', type=int, default={'fpu': 250000, 'int': 250000, 'vu': 25000}[name])
        p.add_argument('--seeds', type=int, default=4)
        p.add_argument('--jobs', type=int, default=3)
        p.add_argument('--only')
    args = parser.parse_args()
    os.makedirs(OUT, exist_ok=True)
    return {'build': build, 'fpu': fpu, 'int': integer, 'vu': vu}[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
