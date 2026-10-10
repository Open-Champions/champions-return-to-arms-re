#!/usr/bin/env python3
"""rawptr.py -- find object pointers that are kept without a handle, and code whose result
depends on the numeric value of an object address.

Background: game objects live in a fixed pool and are normally referenced through handle
lists (handle_link 0x1a1738), which are emptied when the object is destroyed. A field that
holds a plain pointer to another object goes stale when that object is destroyed, and what
is then read through it depends on what the pool put there. See docs/issues/stale-pointers.md.

  python3 -I -B tools/rawptr.py SLUS_209.73 fields [Class] [--all]
                                                             raw-pointer field candidates,
                                                             grouped by class; --all adds
                                                             every other word of `this` that
                                                             is used as a base and is not a
                                                             handle
  python3 -I -B tools/rawptr.py SLUS_209.73 stores           stores of a value the function
                                                             treats as an object into a field
                                                             or a global (no handle call on
                                                             that field in the function)
  python3 -I -B tools/rawptr.py SLUS_209.73 globals          globals loaded and then used as
                                                             an object (virtual call, flags,
                                                             position)
  python3 -I -B tools/rawptr.py SLUS_209.73 ptrmath          ordering compares, shifts, masks
                                                             and divisions applied to a value
                                                             that the same function also
                                                             dereferences as an object
  python3 -I -B tools/rawptr.py SLUS_209.73 keeps <hexentry> stores of an argument or of a
                                                             call result into memory that
                                                             outlives the call, in everything
                                                             reachable by direct calls
  python3 -I -B tools/rawptr.py SLUS_209.73 func <hexentry>  the raw events of one function

Needs ghidra_funcs.tsv (function bodies) next to the executable. Reads instruction words
from the executable itself; no disassembly file is needed.

How it works. Each function is walked once in address order with a small value tracker
(no control flow: a register keeps the last value written above it, caller-saved registers
are forgotten at a call). A tracked value is one of
  A n        incoming argument n ($a0-$a3 = 0-3, $t0-$t3 = 4-7)
  F b off    the word loaded from off(b), b tracked
  G addr     the word loaded from a global
  R callee   the result of a call
  P b off    the address b + off
  X b        b plus an untracked index
  T addr     a global table plus an untracked index (a load through it is G addr, indexed)
  K value    a constant
The events recorded are word stores, loads and stores through a tracked base ("deref"),
calls with their argument values, and arithmetic on tracked values.

"fields" then answers, for every class with a virtual table: which offsets of `this` hold a
word that some member function loads and uses as an object (it calls through +0x48, or reads
both the flag word +0xc and a position word), and which of those offsets never appear as the
first argument of a handle function. `this` is followed through direct calls: if a member
passes its `this` as argument j of a callee, the callee's argument j is `this` as well.

It is a triage tool. It over-reports (a register that is reused on another path, a pointer
to something that merely has words at +0xc and +0x10) and under-reports (pointers reached
only through indirect calls, values spilled across a join). Every hit has to be read.
"""
import bisect, collections, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ps2elf import Elf
import symtab
from textinput import text_lines
import vtab

HANDLE_FUNCS = {
    0x1a1738: 'link', 0x1a1698: 'clear', 0x1a1860: 'initEmpty', 0x1a1868: 'removeNode',
    0x1a1980: 'addNode', 0x1a19d0: 'insertNode', 0x1a1a48: 'iter_begin',
}
POOL_NEW = 0x14fdb8
CALLER_SAVED = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 24, 25]
ARG_REGS = [4, 5, 6, 7, 8, 9, 10, 11]
# deref offsets that mark the base as a GameObject / Creature
VT_OFF = 0x48
VT_OFFS = (0x48, 0x14, 0x60)
POS_OFFS = {0x10, 0x14, 0x18}


def load_bodies(root):
    out = {}
    for line in text_lines(os.path.join(root, 'ghidra_funcs.tsv')):
        if not line.strip() or line.startswith('#'):
            continue
        entry, _name, body = line.rstrip('\n').split('\t')
        rs = []
        for part in body.split(','):
            if part:
                lo, hi = (int(x, 16) for x in part.split('-'))
                rs.append((lo, hi + 1))
        out[int(entry, 16)] = sorted(rs)
    return out


class Events:
    __slots__ = ('stores', 'gstores', 'derefs', 'calls', 'math', 'gloads', 'rets')

    def __init__(self):
        self.stores = []    # (pc, basetag, off, valtag)
        self.gstores = []   # (pc, addr, valtag)
        self.derefs = []    # (pc, basetag, off, 'L'|'S'|'FL'|'FS')
        self.calls = []     # (pc, callee|None, [argtags], calltag)
        self.math = []      # (pc, op, tagA, tagB)
        self.gloads = []    # (pc, addr)
        self.rets = []      # value of $v0 at each jr $ra


def analyse(e, ranges):
    ev = Events()
    reg = {i: None for i in range(32)}
    for i, r in enumerate(ARG_REGS):
        reg[r] = ('A', i)
    reg[0] = ('K', 0)
    stack = {}
    saved = {}
    pcs = []
    for lo, hi in ranges:
        pcs.extend(range(lo, hi, 4))

    def setr(r, v):
        if r:
            reg[r] = v

    def step(pc, w):
        op = w >> 26
        rs, rt, rd = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
        imm = w & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm
        fn = w & 0x3F
        if op == 0x0F:                                   # lui
            setr(rt, ('K', (imm << 16) & 0xFFFFFFFF))
        elif op in (0x09, 0x19):                         # addiu / daddiu
            b = reg[rs]
            if b and b[0] == 'K':
                setr(rt, ('K', (b[1] + simm) & 0xFFFFFFFF))
            elif b and simm == 0:
                setr(rt, b)
            elif b and b[0] == 'P':
                setr(rt, ('P', b[1], b[2] + simm))
            elif b and b[0] == 'T':
                setr(rt, ('T', (b[1] + simm) & 0xFFFFFFFF))
            elif b:
                setr(rt, ('P', b, simm))
            else:
                setr(rt, None)
        elif op == 0x0D:                                 # ori
            b = reg[rs]
            if b and b[0] == 'K':
                setr(rt, ('K', b[1] | imm))
            else:
                if b and b[0] != 'K':
                    ev.math.append((pc, 'ori', b, None))
                setr(rt, None)
        elif op in (0x0C, 0x0E, 0x0A, 0x0B):             # andi xori slti sltiu
            b = reg[rs]
            if b and b[0] != 'K':
                ev.math.append((pc, {0x0C: 'andi', 0x0E: 'xori', 0x0A: 'slti', 0x0B: 'sltiu'}[op], b, imm))
            setr(rt, None)
        elif op == 0 and fn in (0x21, 0x2D, 0x25) and (rt == 0 or rs == 0):  # move
            setr(rd, reg[rs] if rt == 0 else reg[rt])
        elif op == 0 and fn in (0x21, 0x2D):             # addu / daddu
            a, b = reg[rs], reg[rt]
            pa = a and a[0] in 'AFGRPX'
            pb = b and b[0] in 'AFGRPX'
            ka = a and a[0] == 'K' and a[1] >= 0x100000
            kb = b and b[0] == 'K' and b[1] >= 0x100000
            if ka and not kb and not pb:
                setr(rd, ('T', a[1]))                     # a global table plus an index
            elif kb and not ka and not pa:
                setr(rd, ('T', b[1]))
            elif pa and not pb:
                setr(rd, ('X', a if a[0] != 'X' else a[1]))
            elif pb and not pa:
                setr(rd, ('X', b if b[0] != 'X' else b[1]))
            else:
                setr(rd, None)
        elif op == 0 and fn in (0x23, 0x2F):             # subu / dsubu
            a, b = reg[rs], reg[rt]
            if a and b and a[0] != 'K' and b[0] != 'K':
                ev.math.append((pc, 'sub', a, b))
            setr(rd, None)
        elif op == 0 and fn in (0x2A, 0x2B):             # slt / sltu
            a, b = reg[rs], reg[rt]
            if a and b and a[0] != 'K' and b[0] != 'K':
                ev.math.append((pc, 'slt' if fn == 0x2A else 'sltu', a, b))
            setr(rd, None)
        elif op == 0 and fn == 0x00 and w != 0 and ((w >> 6) & 31) == 0:  # sll rd, rt, 0
            setr(rd, reg[rt])
        elif op == 0 and fn in (0x3C, 0x3F, 0x3E) and ((w >> 6) & 31) == 0:  # dsll32/dsra32/dsrl32 by 0
            setr(rd, reg[rt])                             # the two halves of a sign extension
        elif op == 0 and fn in (0x00, 0x02, 0x03, 0x04, 0x06, 0x07) and w != 0:  # shifts
            b = reg[rt]
            if b and b[0] != 'K':
                ev.math.append((pc, 'shift', b, (w >> 6) & 31))
            setr(rd, None)
        elif op == 0 and fn in (0x18, 0x19, 0x1A, 0x1B):  # mult multu div divu
            for t in (reg[rs], reg[rt]):
                if t and t[0] != 'K':
                    ev.math.append((pc, 'muldiv', t, None))
            setr(rd, None)
        elif op == 0 and fn in (0x24, 0x26, 0x27, 0x25):  # and xor nor or
            a, b = reg[rs], reg[rt]
            if fn == 0x26 and a and b and a[0] != 'K' and b[0] != 'K':
                ev.math.append((pc, 'xor', a, b))
            setr(rd, None)
        elif op == 0 and fn in (0x10, 0x12):             # mfhi mflo
            setr(rd, None)
        elif op == 0 and fn in (0x0A, 0x0B):             # movz movn
            setr(rd, None)
        elif op in (0x23, 0x37, 0x27, 0x20, 0x24, 0x21, 0x25, 0x31, 0x1E, 0x1A, 0x1B, 0x22, 0x26):
            # lw ld lwu lb lbu lh lhu lwc1 lq ldl ldr lwl lwr
            b = reg[rs]
            isw = op in (0x23, 0x37, 0x27)
            if rs == 29:
                if op != 0x31 and saved.get(simm) != rt:
                    setr(rt, stack.get(simm) if isw else None)
                return
            if b and b[0] == 'K' and b[1] < 0x10000:
                if op != 0x31:
                    setr(rt, None)                        # a register zeroed on another path
                return
            if b and b[0] == 'K':
                addr = (b[1] + simm) & 0xFFFFFFFF
                ev.gloads.append((pc, addr))
                if op != 0x31:
                    setr(rt, ('G', addr) if isw else None)
                return
            if b and b[0] == 'T':
                if op != 0x31:
                    setr(rt, ('G', (b[1] + simm) & 0xFFFFFFFF, 'i') if isw else None)
                return
            if b:
                ev.derefs.append((pc, b, simm, 'FL' if op == 0x31 else 'L'))
            if op != 0x31:
                setr(rt, ('F', b, simm) if (b and isw) else None)
        elif op in (0x2B, 0x3F, 0x28, 0x29, 0x39, 0x1F, 0x2C, 0x2D, 0x2A, 0x2E):
            # sw sd sb sh swc1 sq sdl sdr swl swr
            b = reg[rs]
            isw = op in (0x2B, 0x3F)
            v = reg[rt] if op != 0x39 else None
            if rs == 29:
                if isw:
                    if v is None and (16 <= rt <= 23 or rt in (28, 30, 31)) and simm not in stack:
                        saved[simm] = rt                  # prologue save of a callee-saved register
                    stack[simm] = v
                return
            if b and b[0] == 'K':
                if op == 0x2B and b[1] >= 0x10000:
                    ev.gstores.append((pc, (b[1] + simm) & 0xFFFFFFFF, v))
                return
            if b and b[0] == 'T':
                if op == 0x2B:
                    ev.gstores.append((pc, (b[1] + simm) & 0xFFFFFFFF, v))
                return
            if b:
                ev.derefs.append((pc, b, simm, 'FS' if op == 0x39 else 'S'))
                if op == 0x2B:
                    ev.stores.append((pc, b, simm, v))
        elif op in (0x11, 0x10, 0x12):                   # coprocessor: mfc1 etc. write rt
            if rs in (0, 2):                              # mfc / cfc
                setr(rt, None)
        else:
            # anything else that writes a general register: be conservative
            if op == 0 and rd:
                setr(rd, None)
            elif op not in (0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17, 0x01, 0x02, 0x03, 0x2F, 0x33):
                if op in (0x08, 0x18, 0x1C):
                    setr(rt if op != 0x1C else rd, None)

    i = 0
    n = len(pcs)
    while i < n:
        pc = pcs[i]
        w = e.u32(pc)
        op = w >> 26
        fn = w & 0x3F
        is_jal = op == 3
        is_jalr = op == 0 and fn == 0x09
        if is_jal or is_jalr:
            calltag = reg[(w >> 21) & 31] if is_jalr else None
            if i + 1 < n:
                step(pcs[i + 1], e.u32(pcs[i + 1]))      # delay slot runs first
            callee = ((pc & 0xF0000000) | ((w & 0x03FFFFFF) << 2)) if is_jal else None
            ev.calls.append((pc, callee, [reg[r] for r in ARG_REGS], calltag))
            for r in CALLER_SAVED:
                reg[r] = None
            reg[2] = ('R', callee, pc)
            i += 2
            continue
        if w == 0x03E00008:                               # jr $ra
            if i + 1 < n:
                step(pcs[i + 1], e.u32(pcs[i + 1]))
            ev.rets.append(reg[2])
            i += 2
            continue
        likely = op in (0x14, 0x15, 0x16, 0x17) or (op == 1 and ((w >> 16) & 31) in (2, 3, 0x12, 0x13)) \
            or (op == 0x11 and ((w >> 21) & 31) == 8 and ((w >> 16) & 31) in (2, 3))
        step(pc, w)
        i += 2 if likely else 1
    return ev


def tag_str(t, names=None):
    if t is None:
        return '?'
    k = t[0]
    if k == 'A':
        return 'arg%d' % t[1]
    if k == 'K':
        return '#%x' % t[1]
    if k == 'G':
        nm = names.get(t[1]) if names else None
        return '[%s%s]' % (nm or '%x' % t[1], '+i' if len(t) > 2 else '')
    if k == 'T':
        return '&%x[i]' % t[1]
    if k == 'R':
        if t[1] is None:
            return 'ret(indirect@%x)' % t[2]
        nm = names.get(t[1]) if names else None
        return 'ret(%s@%x)' % (nm or '%x' % t[1], t[2])
    if k == 'F':
        return '%s->%x' % (tag_str(t[1], names), t[2])
    if k == 'P':
        return '&%s+%x' % (tag_str(t[1], names), t[2])
    if k == 'X':
        return '%s[i]' % tag_str(t[1], names)
    return repr(t)


def tier_of(offs):
    """offs: set of (deref offset, kind). Returns how the pointee is used:
    'object'  virtual call through +0x48, or flag word +0xc together with a position word
    'spell'   virtual call through +0x14        'skill'  virtual call through +0x60
    'passed'  handed to a function that uses its argument as an object
    'pos'     only a position read (+0x10 with +0x14 or +0x18): weak evidence"""
    plain = {o for o, _ in offs}
    v = {o for o, kd in offs if kd == 'V'}
    if VT_OFF in v or (0xc in plain and plain & POS_OFFS):
        return 'object'
    if -1 in v:
        return 'passed'
    if 0x14 in v:
        return 'spell'
    if 0x60 in v:
        return 'skill'
    if 0x10 in plain and plain & {0x14, 0x17, 0x18}:
        return 'pos'
    return None


class Scan:
    def __init__(self, elf_path):
        self.e = Elf(elf_path)
        self.e.analyze()
        self.root = os.path.dirname(os.path.abspath(elf_path))
        if not os.path.exists(os.path.join(self.root, 'ghidra_funcs.tsv')):
            self.root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.bodies = load_bodies(self.root)
        self.names = symtab.load(self.root)
        self.entries = sorted(self.bodies)
        self.ev = {}
        for f, rs in self.bodies.items():
            self.ev[f] = analyse(self.e, rs)
        self.vts = vtab.find_vtables(self.e)
        self.all_fields = False

    def name(self, a):
        return self.names.get(a) or '%x' % a

    # ---- per (function, argument): what is done with the argument as a base ------------
    def arg_summary(self):
        """(func, argIndex) -> {field offset: set of (deref offset, kind, pc)} for words that
        are loaded from the argument and then used as a base. kind 'V' marks a virtual call
        through the loaded word (table pointer at +0x48, +0x14 or +0x60 of the pointee)."""
        out = collections.defaultdict(lambda: collections.defaultdict(set))

        def root_arg(t):
            if t and t[0] == 'X':
                t = t[1]
            return t[1] if t and t[0] == 'A' else None

        for f, ev in self.ev.items():
            for pc, b, off, kind in ev.derefs:
                if b[0] == 'F':
                    k = root_arg(b[1])
                    if k is not None:
                        out[(f, k)][b[2]].add((off, kind, pc))
                    # table pointer loaded from the pointee, entry read directly
                    if b[2] in VT_OFFS and b[1] and b[1][0] == 'F':
                        k = root_arg(b[1][1])
                        if k is not None:
                            out[(f, k)][b[1][2]].add((b[2], 'V', pc))
                # table pointer plus entry offset used as base
                if b[0] == 'P' and b[1] and b[1][0] == 'F' and b[1][2] in VT_OFFS \
                        and b[1][1] and b[1][1][0] == 'F':
                    k = root_arg(b[1][1][1])
                    if k is not None:
                        out[(f, k)][b[1][1][2]].add((b[1][2], 'V', pc))
        return out

    def objlike_args(self):
        """Set of (func, argIndex) whose argument is used as an object: the function calls
        through its table pointer, or reads its flag word and a position word, or passes it
        on unchanged to a function that does."""
        offs = collections.defaultdict(set)
        virt = set()
        passes = collections.defaultdict(set)
        for f, ev in self.ev.items():
            for pc, b, off, kind in ev.derefs:
                if b[0] == 'A':
                    offs[(f, b[1])].add(off)
                elif b[0] == 'F' and b[2] == VT_OFF and b[1] and b[1][0] == 'A':
                    virt.add((f, b[1][1]))
                elif b[0] == 'P' and b[1] and b[1][0] == 'F' and b[1][2] == VT_OFF \
                        and b[1][1] and b[1][1][0] == 'A':
                    virt.add((f, b[1][1][1]))
            for pc, callee, args, _ in ev.calls:
                if callee is None or callee not in self.ev:
                    continue
                for j, t in enumerate(args):
                    if t and t[0] == 'A':
                        passes[(callee, j)].add((f, t[1]))
        good = set(virt)
        for key, o in offs.items():
            if 0xc in o and o & POS_OFFS:
                good.add(key)
        work = list(good)
        while work:
            key = work.pop()
            for up in passes.get(key, ()):
                if up not in good:
                    good.add(up)
                    work.append(up)
        return good

    def this_closure(self, seeds):
        """Follow `this` through direct calls. seeds: iterable of (func, argIndex)."""
        seen = set(seeds)
        work = list(seen)
        while work:
            f, k = work.pop()
            ev = self.ev.get(f)
            if not ev:
                continue
            for pc, callee, args, _ in ev.calls:
                if callee is None or callee not in self.ev or callee in HANDLE_FUNCS:
                    continue
                for j, t in enumerate(args):
                    if t == ('A', k) and (callee, j) not in seen:
                        seen.add((callee, j))
                        work.append((callee, j))
        return seen

    def class_table(self):
        """class name -> (vtable address, member functions, constructors)"""
        ctors = collections.defaultdict(list)       # vtable addr -> [func]
        for f, ev in self.ev.items():
            last = {}
            for pc, b, off, v in ev.stores:
                if b == ('A', 0) and v and v[0] == 'K' and v[1] in self.vts:
                    last[off] = v[1]
            for off, vt in last.items():
                if off in (0x48, 0x14, 0x60):
                    ctors[vt].append(f)
        out = {}
        for vt, (cname, ents) in sorted(self.vts.items()):
            members = {fn for _d, fn in ents if fn in self.ev}
            out[(cname, vt)] = (members, set(ctors.get(vt, [])))
        return out

    # ---- fields ---------------------------------------------------------------------
    def fields(self, only=None):
        summ = self.arg_summary()
        objargs = self.objlike_args()
        rows = []
        stats = collections.Counter()
        for (cname, vt), (members, ctors) in self.class_table().items():
            if only and cname != only:
                continue
            stats['classes'] += 1
            closure = self.this_closure([(f, 0) for f in members | ctors])
            handle_offs = collections.defaultdict(set)
            stores = collections.defaultdict(list)
            uses = collections.defaultdict(list)
            for f, k in closure:
                ev = self.ev[f]
                for pc, callee, args, _ in ev.calls:
                    if callee in HANDLE_FUNCS:
                        t = args[0]
                        if t and t[0] == 'P' and t[1] == ('A', k):
                            handle_offs[t[2]].add(HANDLE_FUNCS[callee])
                        elif t == ('A', k):
                            handle_offs[0].add(HANDLE_FUNCS[callee])
                for pc, b, off, v in ev.stores:
                    if b == ('A', k) or b == ('X', ('A', k)):
                        stores[off].append((f, pc, v))
                for off, ds in summ.get((f, k), {}).items():
                    uses[off].append((f, ds))
                for pc, callee, args, _ in ev.calls:
                    for j, t in enumerate(args):
                        if t and t[0] == 'F' and (t[1] == ('A', k) or t[1] == ('X', ('A', k))) \
                                and (callee, j) in objargs:
                            uses[t[2]].append((f, {(-1, 'V', pc)}))
            for off in sorted(uses):
                stats['pointer fields'] += 1
                offs = set()
                for f, ds in uses[off]:
                    offs |= {(o, kd) for o, kd, _pc in ds}
                plain = {o for o, _ in offs}
                tier = tier_of(offs)
                if not tier and self.all_fields and off not in handle_offs:
                    stats['other'] += 1
                    tier = 'other'
                if not tier:
                    continue
                stats['object-like'] += 1
                if off in handle_offs:
                    stats['handles'] += 1
                    continue
                if off in (0x48, 0x14, 0x60, 0x0, 0x4, 0x8) and not stores.get(off):
                    continue
                if off == 0x24 and any(self.names.get(f) == 'GameObject_ctor' for f, _pc, _v in stores.get(off, [])):
                    continue                              # the class-definition pointer
                rows.append((cname, vt, off, stores.get(off, []), uses[off], sorted(plain), tier))
        return rows, stats

    # ---- stores ---------------------------------------------------------------------
    def object_tags(self):
        """For every function: the tracked values it treats as objects."""
        objargs = self.objlike_args()
        # functions whose result some caller uses as an object, and functions that return a
        # block they took from the pool
        objret = set()
        per = {}
        for f, ev in self.ev.items():
            d = collections.defaultdict(set)
            for pc, b, off, kind in ev.derefs:
                d[b].add((off, kind))
                if b[0] == 'F' and b[2] == VT_OFF and b[1]:
                    d[b[1]].add((VT_OFF, 'V'))
                if b[0] == 'P' and b[1] and b[1][0] == 'F' and b[1][2] == VT_OFF and b[1][1]:
                    d[b[1][1]].add((VT_OFF, 'V'))
            for pc, callee, args, _ in ev.calls:
                for j, t in enumerate(args):
                    if t and t[0] in 'AFGRX' and (callee, j) in objargs:
                        d[t].add((-1, 'V'))
            tags = {t for t, offs in d.items() if tier_of(offs) in ('object', 'passed')}
            for k in range(8):
                if (f, k) in objargs:
                    tags.add(('A', k))
            per[f] = tags
            for t in tags:
                if t[0] == 'R' and t[1] is not None:
                    objret.add(t[1])
        objret.add(POOL_NEW)
        changed = True
        while changed:
            changed = False
            for f, ev in self.ev.items():
                if f in objret:
                    continue
                if any(t and t[0] == 'R' and t[1] in objret for t in ev.rets):
                    objret.add(f)
                    changed = True
        for f, ev in self.ev.items():
            for pc, callee, args, _ in ev.calls:
                if callee in objret:
                    per[f].add(('R', callee, pc))
        # forward: an argument is an object when a caller passes one. This direction is not
        # fed back to other callers, so a general-purpose callee does not spread the mark.
        fwd = set()
        work = []
        for f, ev in self.ev.items():
            for pc, callee, args, _ in ev.calls:
                if callee in self.ev and callee not in HANDLE_FUNCS:
                    for j, t in enumerate(args):
                        if t in per[f] and (callee, j) not in fwd:
                            fwd.add((callee, j))
                            work.append((callee, j))
        while work:
            f, k = work.pop()
            per[f].add(('A', k))
            for pc, callee, args, _ in self.ev[f].calls:
                if callee in self.ev and callee not in HANDLE_FUNCS:
                    for j, t in enumerate(args):
                        if t == ('A', k) and (callee, j) not in fwd:
                            fwd.add((callee, j))
                            work.append((callee, j))
        return per, objret

    def raw_stores(self):
        per, objret = self.object_tags()
        out = []
        for f, ev in sorted(self.ev.items()):
            tags = per[f]
            hoffs = set()
            for pc, callee, args, _ in ev.calls:
                if callee in HANDLE_FUNCS and args[0] and args[0][0] == 'P':
                    hoffs.add((args[0][1], args[0][2]))
            for pc, b, off, v in ev.stores:
                if v in tags and (b, off) not in hoffs:
                    out.append((f, pc, 'field', b, off, v))
            for pc, addr, v in ev.gstores:
                if v in tags:
                    out.append((f, pc, 'global', addr, 0, v))
        return out

    # ---- globals --------------------------------------------------------------------
    def globals_(self):
        use = collections.defaultdict(lambda: collections.defaultdict(set))
        for f, ev in self.ev.items():
            for pc, b, off, kind in ev.derefs:
                if b[0] == 'G':
                    use[b[1]][f].add((off, kind))
                if b[0] == 'F' and b[2] in VT_OFFS and b[1] and b[1][0] == 'G':
                    use[b[1][1]][f].add((b[2], 'V'))
                if b[0] == 'P' and b[1] and b[1][0] == 'F' and b[1][1] and b[1][1][0] == 'G' \
                        and b[1][2] in VT_OFFS:
                    use[b[1][1][1]][f].add((b[1][2], 'V'))
        writers = collections.defaultdict(list)
        for f, ev in self.ev.items():
            for pc, addr, v in ev.gstores:
                writers[addr].append((f, pc, v))
        out = []
        for addr, byf in sorted(use.items()):
            plain = set()
            kinds = set()
            for f, s in byf.items():
                plain |= {o for o, _ in s}
                kinds |= s
            objlike = any(kd == 'V' for _o, kd in kinds) or (0xc in plain and plain & POS_OFFS)
            if objlike:
                out.append((addr, sorted(plain), sorted(byf), writers.get(addr, [])))
        return out

    # ---- pointer arithmetic ---------------------------------------------------------
    def ptrmath(self):
        """(a) arithmetic on a value the function treats as an object; (b) ordering compares
        and differences of two different values that are both used as a base somewhere in
        the function (two pointers compared for order)."""
        per, _ = self.object_tags()
        out = []
        for f, ev in sorted(self.ev.items()):
            objs = per[f]
            based = {b for _pc, b, _o, _k in ev.derefs}
            for pc, op, a, b in ev.math:
                two = isinstance(b, tuple)
                if op in ('slt', 'sltu', 'sub', 'xor') and two:
                    if a != b and ((a in objs and b in objs) or
                                   (op in ('sltu', 'sub') and a in based and b in based)):
                        out.append((f, pc, op, a, b))
                elif a in objs and op != 'ori':
                    out.append((f, pc, op, a, b))
        return out

    # ---- keeps ------------------------------------------------------------------------
    def reach(self, entry):
        seen, work = {entry}, [entry]
        while work:
            f = work.pop()
            for pc, callee, _a, _t in self.ev[f].calls:
                if callee in self.ev and callee not in seen:
                    seen.add(callee)
                    work.append(callee)
        return seen


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    s = Scan(sys.argv[1])
    cmd = sys.argv[2]
    nm = s.names
    if cmd == 'func':
        f = int(sys.argv[3], 16)
        ev = s.ev[f]
        for pc, b, off, v in ev.stores:
            print('%x store  %s + %x  <- %s' % (pc, tag_str(b, nm), off, tag_str(v, nm)))
        for pc, addr, v in ev.gstores:
            print('%x gstore %s <- %s' % (pc, s.name(addr), tag_str(v, nm)))
        for pc, b, off, kind in ev.derefs:
            print('%x deref  %s + %x  %s' % (pc, tag_str(b, nm), off, kind))
        for pc, callee, args, ct in ev.calls:
            print('%x call   %s (%s)' % (pc, s.name(callee) if callee else 'indirect:' + tag_str(ct, nm),
                                         ', '.join(tag_str(a, nm) for a in args[:4])))
        for pc, op, a, b in ev.math:
            print('%x math   %s %s %s' % (pc, op, tag_str(a, nm), tag_str(b, nm) if isinstance(b, tuple) else b))
    elif cmd == 'fields':
        args = [a for a in sys.argv[3:] if a != '--all']
        s.all_fields = '--all' in sys.argv      # also list pointers with no object evidence
        rows, stats = s.fields(args[0] if args else None)
        # group identical (offset, use sites) across classes: inherited fields appear once
        groups = collections.OrderedDict()
        for cname, vt, off, stores, uses, plain, tier in rows:
            key = (off, tuple(sorted(f for f, _ in uses)))
            groups.setdefault(key, []).append((cname, stores, uses, plain, tier))
        print('# classes %d, pointer fields %d, object-like %d, of which handles %d, reported groups %d'
              % (stats['classes'], stats['pointer fields'], stats['object-like'], stats['handles'], len(groups)))
        for (off, _), items in groups.items():
            cnames = sorted({it[0] for it in items})
            _c, stores, uses, plain, tier = items[0]
            print('+%x\t%s\t%s%s' % (off, tier, ','.join(cnames[:6]), ' (+%d more)' % (len(cnames) - 6) if len(cnames) > 6 else ''))
            print('\tread through at: %s' % ' '.join('%x' % o for o in plain))
            for f, pc, v in stores[:12]:
                print('\tstore %s %x <- %s' % (s.name(f), pc, tag_str(v, nm)))
            for f, ds in uses[:12]:
                print('\tuse   %s  %s' % (s.name(f), ' '.join(sorted({'%x:%x%s' % (pc, o, kd) for o, kd, pc in ds})[:8])))
    elif cmd == 'stores':
        owner = {}
        for (cname, vt), (members, ctors) in s.class_table().items():
            for f in members | ctors:
                owner.setdefault(f, []).append(cname)
        for f, pc, kind, b, off, v in s.raw_stores():
            cls = ','.join(sorted(set(owner.get(f, [])))[:3])
            if kind == 'field':
                print('%s\t%x\t%s+%x <- %s\t%s' % (s.name(f), pc, tag_str(b, nm), off, tag_str(v, nm), cls))
            else:
                print('%s\t%x\tglobal %s <- %s\t%s' % (s.name(f), pc, s.name(b), tag_str(v, nm), cls))
    elif cmd == 'globals':
        for addr, plain, funcs, writers in s.globals_():
            print('%08x %s\tread through at: %s' % (addr, nm.get(addr, ''), ' '.join('%x' % o for o in plain)))
            print('\tusers: %s' % ' '.join(s.name(f) for f in funcs[:14]) + (' ...' if len(funcs) > 14 else ''))
            for f, pc, v in writers[:10]:
                print('\twrite %s %x <- %s' % (s.name(f), pc, tag_str(v, nm)))
    elif cmd == 'ptrmath':
        for f, pc, op, a, b in s.ptrmath():
            print('%s\t%x\t%s\t%s\t%s' % (s.name(f), pc, op, tag_str(a, nm), tag_str(b, nm) if isinstance(b, tuple) else b))
    elif cmd == 'keeps':
        entry = int(sys.argv[3], 16)
        for f in sorted(s.reach(entry)):
            ev = s.ev[f]
            for pc, addr, v in ev.gstores:
                if v and v[0] in 'ARFG' and v != ('K', 0):
                    print('%s\t%x\tglobal %s <- %s' % (s.name(f), pc, s.name(addr), tag_str(v, nm)))
            for pc, b, off, v in ev.stores:
                if v and v[0] == 'A' and b and b[0] in 'FGRX' :
                    print('%s\t%x\t%s+%x <- %s' % (s.name(f), pc, tag_str(b, nm), off, tag_str(v, nm)))
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
