#!/usr/bin/env python3
"""gxref.py ELF ADDRHEX [...] -- list instructions that load/store a global via lui+displacement
(or gp-less absolute addressing), marking reads (R), writes (W) and address-taken (&).

Each register's upper half is tracked from its lui to the end of the function (bodies from
ghidra_funcs.tsv), with addiu/ori/move followed, so an access any distance from its lui is
found. A hit ends in '?' when something else wrote the base register between the lui and the
access in listing order: the listing is not execution order, so those are possible, not
certain. Not followed: addresses built through a call, a load from memory or register
arithmetic (array bases indexed with addu are reported at the addiu as '&' only)."""
import sys, re, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ps2elf import Elf
import symtab
from textinput import text_lines

LOADS = {'lw', 'lh', 'lhu', 'lb', 'lbu', 'lwc1', 'ld', 'lwu', 'lq', 'lwl', 'lwr', 'ldl', 'ldr'}
STORES = {'sw', 'sh', 'sb', 'swc1', 'sd', 'sq', 'swl', 'swr', 'sdl', 'sdr'}
# First operand is not a general register being written.
NOWRITE = STORES | {'mtc1', 'dmtc1', 'ctc1', 'ctc2', 'qmtc2', 'mtc0', 'mthi', 'mtlo', 'mthi1',
                    'mtlo1', 'mtsa', 'jr', 'j', 'jal', 'teq', 'tge', 'tlt', 'tne', 'cache',
                    'pref', 'syscall', 'break', 'nop', 'sync'}
TWO_OP_HILO = {'mult', 'multu', 'div', 'divu', 'dmult', 'dmultu', 'ddiv', 'ddivu', 'mult1',
               'multu1', 'div1', 'divu1'}


def func_starts(root):
    path = os.path.join(root, 'ghidra_funcs.tsv')
    starts = set()
    if os.path.exists(path):
        for l in text_lines(path):
            try: starts.add(int(l.split('\t')[0], 16))
            except ValueError: pass
    return starts


def scan(lines, targets, starts):
    """Yield (target, instruction address, kind) for every access found."""
    pat = re.compile(r'^\s*([0-9a-f]+):\s+(\S+)\s*(.*)$')
    mem = re.compile(r'^(\$\w+), (-?0x[0-9a-f]+|-?\d+)\((\$\w+)\)$')
    sure = {}    # register -> value, dropped when anything else writes the register
    loose = {}   # register -> value from the last lui-derived write in this function
    for l in lines:
        m = pat.match(l)
        if not m: continue
        a = int(m.group(1), 16); op = m.group(2); args = m.group(3).split('<')[0].strip()
        if a in starts:
            sure.clear(); loose.clear()
        p = [x.strip() for x in args.split(',')] if args else []
        if op == 'lui' and len(p) == 2:
            try: v = (int(p[1], 0) << 16) & 0xffffffff
            except ValueError: continue
            sure[p[0]] = loose[p[0]] = v
            continue
        if op in ('addiu', 'ori', 'daddiu') and len(p) == 3:
            try: imm = int(p[2], 0)
            except ValueError: imm = None
            if imm is not None and (p[1] in sure or p[1] in loose):
                certain = p[1] in sure
                base = sure[p[1]] if certain else loose[p[1]]
                v = (base | imm) if op == 'ori' else (base + imm) & 0xffffffff
                if v in targets: yield v, a, '&' if certain else '&?'
                if certain: sure[p[0]] = v
                else: sure.pop(p[0], None)
                loose[p[0]] = v
                continue
        if op == 'move' and len(p) == 2 and p[1] in sure:
            sure[p[0]] = loose[p[0]] = sure[p[1]]
            continue
        mm = mem.match(args)
        if mm and (op in LOADS or op in STORES):
            base = mm.group(3); off = int(mm.group(2), 0)
            if base in sure or base in loose:
                certain = base in sure
                v = ((sure[base] if certain else loose[base]) + off) & 0xffffffff
                if v in targets:
                    yield v, a, ('W' if op in STORES else 'R') + ('' if certain else '?')
        if p and p[0].startswith('$') and not p[0].startswith('$f') and op not in NOWRITE \
                and not op.startswith('b') and not (op in TWO_OP_HILO and len(p) == 2):
            sure.pop(p[0], None)
        if op == 'jalr':
            sure.pop('$ra', None); sure.pop('$31', None)


def main():
    e = Elf(sys.argv[1]); e.analyze()
    targets = {int(x, 16) for x in sys.argv[2:]}
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    names = symtab.load(root)
    hits = collections.defaultdict(list)
    for v, a, kind in scan(text_lines(os.path.join(root, 'disasm/text.asm')), targets, func_starts(root)):
        f = e.func_of(a); f = f[0] if isinstance(f, tuple) else f
        hits[(v, f)].append('%x:%s' % (a, kind))
    for (v, f) in sorted(hits, key=lambda k: (k[0], k[1] or 0)):
        print('%08x %s %-26s %s' % (v, hex(f) if f else '?', names.get(f, ''), ' '.join(hits[(v, f)])))

if __name__ == '__main__':
    main()
