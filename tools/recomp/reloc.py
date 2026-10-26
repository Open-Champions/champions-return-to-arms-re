"""reloc.py - relocatable tables for recomp.py (--reloc FILE; docs/issues/native-8-players.md A.9).

A table of the game that a mode wants somewhere else at run time (the player records, sized for four, moved to a
place with room for eight) is reached by code that forms its address from a `lui` and an offset.  For every such
access - a load or store whose base register holds a `lui` value (possibly plus an index) and whose constant address
falls in a listed range, and every `addiu` / `ori` that forms such an address - the translation adds `g_reloc[k]`, a
word of the runtime that is 0 unless the mode has moved table k.  With every word 0 the translated code computes
exactly the addresses it computed before.

The analysis is a forward data flow over each unit: per general register, "holds the upper half H" or "holds H plus
an index" (an addu / daddu / or with a register of unknown value), met by equality at joins; a call forgets every
register but s0-s8, gp and sp.  A register written by anything else forgets.  What it cannot follow is simply not
relocated (a missed access, which a test finds by poisoning the old table).

File format (FILE): one range per line, `index start end`: the index in decimal, start and end in hex (end exclusive), `#` comments.  The index is the
slot of g_reloc (0..31).
"""

MASK = 0xFFFFFFFF


def sx16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def read_ranges(path):
    ranges = []
    with open(path) as source:
        for line in source:
            fields = line.split('#')[0].split()
            if not fields:
                continue
            k, lo, hi = int(fields[0]), int(fields[1], 16), int(fields[2], 16)
            if not 0 <= k < 32 or hi <= lo:
                raise ValueError('bad relocation range: %s' % line.strip())
            ranges.append((k, lo, hi))
    return ranges


def range_of(ranges, address):
    for k, lo, hi in ranges:
        if lo <= address < hi:
            return k
    return None


LOADS = {0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x37, 0x1A, 0x1B, 0x1E}   # lb lh lwl lw lbu lhu lwr lwu ld ldl ldr lq
STORES = {0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x3F, 0x1F}                    # sb sh swl sw sdl sdr swr sd sq
FP_MEM = {0x31, 0x39, 0x36, 0x3E}                                                  # lwc1 swc1 lqc2 sqc2 (base is a GPR)
KEEP_OVER_CALL = set(range(16, 24)) | {28, 29, 30}


def transfer(state, w, decide=None, pc=None, ranges=()):
    """The register state after one instruction (state is changed in place).  With `decide`, records the
    relocation of this instruction: decide[pc] = k."""
    op = w >> 26
    rs, rt, rd = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
    imm = sx16(w)

    def note(address):
        k = range_of(ranges, address & MASK)
        if k is not None and decide is not None:
            decide[pc] = k
        return k

    if op == 0x0F:                                   # lui
        if rt:
            state[rt] = ('h', ((w & 0xFFFF) << 16) & MASK)
        return
    if op in (0x09, 0x19):                           # addiu, daddiu
        src = state.get(rs)
        if src is not None and rt:
            address = (src[1] + imm) & MASK
            if note(address) is not None:
                state.pop(rt, None)                  # a moved pointer from here on: plain arithmetic
            else:
                state[rt] = (src[0], address)
        else:
            state.pop(rt, None)
        return
    if op == 0x0D:                                   # ori
        src = state.get(rs)
        if src is not None and src[0] == 'h' and rt:
            address = src[1] | (w & 0xFFFF)
            if note(address) is not None:
                state.pop(rt, None)
            else:
                state[rt] = ('h', address)
        else:
            state.pop(rt, None)
        return
    if op in LOADS or op in STORES or op in FP_MEM:
        src = state.get(rs)
        if src is not None:
            note(src[1] + imm)
        if op in LOADS:
            state.pop(rt, None)
        return
    if op == 0x2F:                                   # cache
        return
    if op == 0 and (w & 63) in (0x21, 0x2D, 0x25):    # addu, daddu, or: base plus an index
        a, b = state.get(rs), state.get(rt)
        if rd == 0:
            return
        if rt == 0 and a is not None:
            state[rd] = a
        elif rs == 0 and b is not None:
            state[rd] = b
        elif (a is None) != (b is None) and rs and rt:
            state[rd] = ('x', (a or b)[1])
        else:
            state.pop(rd, None)
        return
    if op == 0x11:                                   # COP1: only mfc1 / cfc1 write a general register
        if rs in (0, 2):
            state.pop(rt, None)
        return
    if op == 0x12:                                   # COP2: qmfc2 / cfc2
        state.pop(rt, None)
        return
    if op in (0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17, 0x01):   # branches: no register written (bal is not used)
        return
    if op == 0 and (w & 63) == 0x08:                 # jr
        return
    # anything else: whatever it writes is forgotten (rt and rd both, to be sure)
    state.pop(rt, None)
    state.pop(rd, None)


def meet(a, b):
    if a is None:
        return dict(b)
    return {r: v for r, v in a.items() if b.get(r) == v}


def analyse_unit(image, unit, walk, control_kind, branch_target, jump_target, always_taken, ranges, strong=None):
    """{pc: k} for the unit's instructions that form or use an address in a range.  `strong`: the addresses that are
    entered from outside the unit for certain (transfers from other units, the extra entries); an entry the
    translator made only because a data word or a lui/addiu pair happens to hold its address (a loop head in the
    middle of a function, as a rule) is taken as an ordinary label here."""
    nodes = list(walk(image, unit))
    if not nodes:
        return {}
    index = {n[0]: i for i, n in enumerate(nodes)}
    labels = sorted(index[a] for a in unit.labels if a in index)
    # the ways on from each node: (node, which state) - 'after' the node, 'saved' (after a call: only the registers a
    # callee keeps), 'before' (the state before the delay slot: a branch-likely not taken)
    succ = []
    for i, (pc, w, kind, dpc, dw) in enumerate(nodes):
        nxt = i + 1 if i + 1 < len(nodes) else None
        out = []
        if kind is None:
            if nxt is not None:
                out.append((nxt, 'after'))
        elif kind == 'j':
            t = jump_target(pc, w)
            if t in index:
                out.append((index[t], 'after'))
        elif kind in ('jal', 'bal'):
            t = jump_target(pc, w) if kind == 'jal' else branch_target(pc, w)
            if t in index:                          # a call inside the unit: the callee's code is reached from here
                out.append((index[t], 'after'))
            if nxt is not None:
                out.append((nxt, 'saved'))
        elif kind == 'jalr':
            if ((w >> 11) & 31) == 0:                 # a jump through a register (a jump table)
                out += [(j, 'after') for j in labels]
            elif nxt is not None:
                out.append((nxt, 'saved'))
        elif kind == 'jr':
            if ((w >> 21) & 31) != 31:              # a jump through a register other than ra: a jump table
                out += [(j, 'after') for j in labels]
        else:                                       # a branch
            t = branch_target(pc, w)
            if t in index:
                out.append((index[t], 'after'))
            if not always_taken(w) and nxt is not None:
                out.append((nxt, 'before' if kind == 'bl' else 'after'))
        succ.append(out)
    starts = {unit.start} | (set(unit.entries) if strong is None else (set(unit.entries) & strong))
    entries = {index[a] for a in starts if a in index}
    ins = [None] * len(nodes)                       # None: not reached yet
    for e in entries:
        ins[e] = {}
    work = sorted(entries)
    while work:
        i = work.pop()
        before = dict(ins[i])
        pc, w, kind, dpc, dw = nodes[i]
        after = dict(before)
        if kind is None:
            transfer(after, w, ranges=ranges)
        else:
            if kind in ('jal', 'jalr', 'bal'):
                after.pop(31, None)
                if kind == 'jalr':
                    after.pop((w >> 11) & 31, None)
            if dw is not None:
                transfer(after, dw, ranges=ranges)
        saved = {r: v for r, v in after.items() if r in KEEP_OVER_CALL}
        for j, which in succ[i]:
            if j in entries:
                continue
            out = after if which == 'after' else saved if which == 'saved' else before
            new = dict(out) if ins[j] is None else meet(ins[j], out)
            if new != ins[j]:
                ins[j] = new
                work.append(j)
    decide = {}
    for i, (pc, w, kind, dpc, dw) in enumerate(nodes):
        if ins[i] is None:
            continue
        state = dict(ins[i])
        if kind is None:
            transfer(state, w, decide, pc, ranges)
        elif dw is not None and control_kind(dw) is None:
            if kind in ('jal', 'jalr', 'bal'):
                state.pop(31, None)
                if kind == 'jalr':
                    state.pop((w >> 11) & 31, None)
            transfer(state, dw, decide, dpc, ranges)
    return decide


def apply(pc, w, text, k, ea):
    """The statement `text` that simple(pc, w) made, with g_reloc[k] added to the address it forms."""
    op = w >> 26
    add = ' + g_reloc[%d]' % k
    if op in LOADS or op in STORES or op in FP_MEM:
        e = ea(w)
        if e in text:
            if e.startswith('(('):
                return text.replace(e, e[:-1] + add + ')', 1)
            return text.replace(e, '(%s%s)' % (e, add), 1)
        return None
    if op == 0x09:
        imm = sx16(w)
        old = ' + 0x%xu)' % (imm & 0xFFFFFFFF)
        if old in text:
            return text.replace(old, ' + 0x%xu%s)' % (imm & 0xFFFFFFFF, add), 1)
        return None
    if op == 0x19:
        imm = sx16(w)
        old = ' + 0x%xull' % (imm & 0xFFFFFFFFFFFFFFFF)
        if old in text:
            return text.replace(old, old + ' + (u64)(s64)(s32)g_reloc[%d]' % k, 1)
        return None
    if op == 0x0D:
        old = ' | 0x%xull' % (w & 0xFFFF)
        if old in text:
            return text.replace(old, old + ' + (u64)g_reloc[%d]' % k, 1)
        return None
    return None
