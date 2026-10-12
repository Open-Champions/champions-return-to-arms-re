#!/usr/bin/env python3
"""instrument.py - a copy of the generated translation with an entry hook in every function.

  python3 tools/recomp/proof/instrument.py [--gen local/recomp-out/gen-proof-src]
                                           [--out local/recomp-out/gen-proof]

Reads the C++ that tools/recomp/recomp.py wrote and writes the same code with one line
added per entry point: PROOF_ENTER(n), where n numbers the entries.  The hook (proof.h,
proof_rt.cpp) counts the entry and, when asked, records the machine state there.  Nothing
else in the translation is touched, so what the instrumented program computes is what the
plain one computes.

A function of the function table is counted where control reaches its first instruction:

  - a function with a C++ body of its own: at the top of fn_<address> (or orig_<address>
    when the runtime supplies the function and calls the translation);
  - a function that is a label inside another function's body (the merged clusters): at
    the label, so that jumps and local calls into it are counted too, and not in its
    fn_<address> wrapper, which jumps to that label.

Entries that are not function starts (resume points after a blocking system call, branch
targets reached from another unit) get a number too; the index says which function each
lies in.

Writes <out>/proof_index.tsv: number, address, kind (start | inner | mid | gap), the
function start the address belongs to (or - for code in no function range).
"""
import argparse
import bisect
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
OUT = os.path.join(ROOT, 'local', 'recomp-out')

DEF = re.compile(r'^void (fn|orig)_([0-9a-f]{8})\(Ctx\* c\) \{(.*)$')
WRAP = re.compile(r'^ body_([0-9a-f]{8})\(c, 0x([0-9a-f]+)u\); \}$')


def function_ranges(path):
    """[(start, [(lo, hi)...])] from ghidra_funcs.tsv."""
    funcs = []
    for line in open(path):
        if not line.strip() or line.startswith('#'):
            continue
        parts = line.rstrip('\n').split('\t')
        ranges = []
        for piece in parts[2].split(','):
            lo, hi = piece.strip().split('-')
            ranges.append((int(lo, 16), int(hi, 16) + 1))
        funcs.append((int(parts[0], 16), ranges))
    return funcs


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--gen', default=os.path.join(OUT, 'gen-proof-src'))
    parser.add_argument('--out', default=os.path.join(OUT, 'gen-proof'))
    parser.add_argument('--funcs', default=os.path.join(ROOT, 'ghidra_funcs.tsv'))
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    funcs = function_ranges(args.funcs)
    starts = {start for start, _ in funcs}
    spans = sorted((lo, hi, start) for start, ranges in funcs for lo, hi in ranges)
    span_lo = [s[0] for s in spans]

    def owner(addr):
        i = bisect.bisect_right(span_lo, addr) - 1
        if i >= 0 and spans[i][0] <= addr < spans[i][1]:
            return spans[i][2]
        return None

    sources = sorted(n for n in os.listdir(args.gen) if re.fullmatch(r'c_\d+\.cpp', n))
    # pass 1: which function starts are only a label inside another body
    inner = set()
    for name in sources:
        for line in open(os.path.join(args.gen, name)):
            m = DEF.match(line)
            if not m:
                continue
            addr = int(m.group(2), 16)
            w = WRAP.match(m.group(3))
            if w and int(w.group(1), 16) != addr and addr in starts:
                inner.add(addr)
    index = []                  # (address, kind)

    def number(addr, kind):
        index.append((addr, kind))
        return len(index) - 1

    labelled = set()
    for name in sources:
        out = []
        for line in open(os.path.join(args.gen, name)):
            m = DEF.match(line)
            if m:
                addr = int(m.group(2), 16)
                if addr in inner:
                    out.append(line)            # counted at its label instead
                    continue
                kind = 'start' if addr in starts else ('mid' if owner(addr) is not None else 'gap')
                n = number(addr, kind)
                out.append('void %s_%s(Ctx* c) { PROOF_ENTER(%du);%s\n' % (m.group(1), m.group(2), n, m.group(3)))
                continue
            if line.startswith('    L_') and line[14:15] == ':':
                addr = int(line[6:14], 16)
                if addr in inner and addr not in labelled:
                    labelled.add(addr)
                    n = number(addr, 'inner')
                    line = '%s PROOF_ENTER(%du);%s' % (line[:15], n, line[15:])
            elif line.startswith('#include "recomp.h"'):
                line += '#include "proof.h"\n'
            out.append(line)
        text = ''.join(out)
        target = os.path.join(args.out, name)
        if not os.path.exists(target) or open(target).read() != text:
            with open(target, 'w') as sink:
                sink.write(text)
    missing = inner - labelled
    if missing:
        print('no label found for: %s' % ', '.join('%x' % a for a in sorted(missing)))
        return 1
    for name in os.listdir(args.gen):
        if name not in sources and os.path.isfile(os.path.join(args.gen, name)):
            source, target = os.path.join(args.gen, name), os.path.join(args.out, name)
            if not os.path.exists(target) or open(target, 'rb').read() != open(source, 'rb').read():
                shutil.copyfile(source, target)
    header = os.path.join(args.out, 'proof.h')
    text = open(os.path.join(HERE, 'proof.h.in')).read().replace('@PROOF_ENTRIES@', str(len(index)))
    if not os.path.exists(header) or open(header).read() != text:
        with open(header, 'w') as sink:
            sink.write(text)
    with open(os.path.join(args.out, 'proof_index.tsv'), 'w') as sink:
        sink.write('# number\taddress\tkind\tfunction\n')
        for n, (addr, kind) in enumerate(index):
            own = owner(addr)
            sink.write('%d\t%08x\t%s\t%s\n' % (n, addr, kind, '%08x' % own if own is not None else '-'))
    with open(os.path.join(args.out, 'proof_index.cpp'), 'w') as sink:
        sink.write('// generated by tools/recomp/proof/instrument.py - do not commit\n#include "recomp.h"\n#include "proof.h"\n')
        sink.write('extern const u32 g_proof_addr[PROOF_ENTRIES] = {\n')
        for at in range(0, len(index), 8):
            sink.write('    ' + ' '.join('0x%xu,' % a for a, _ in index[at:at + 8]) + '\n')
        sink.write('};\n')
    counted = {a for a, k in index if k in ('start', 'inner')}
    print('%d entries numbered: %d function starts (%d of them at a label inside another body), %d other entries; '
          '%d functions of the table have no entry of their own' % (
              len(index), len(counted), len(inner), len(index) - len(counted), len(starts - counted)))
    if starts - counted:
        print('  without entry: ' + ' '.join('%x' % a for a in sorted(starts - counted)[:40]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
