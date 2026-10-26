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
slot of g_reloc (0..95).
"""

MASK = 0xFFFFFFFF
TABLES = 96          # the slots of g_reloc (rt/moved.h PARTY8_TABLES)


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
            if not 0 <= k < TABLES or hi <= lo:
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

# Accesses through a pointer into table k (formed by a relocated addiu) whose offset lands outside table k: in another
# listed table (that table then has to move by the same amount: one group) or outside every table (a field next to
# it).  Filled by analyse_unit; recomp.py prints them.  {pc: (k, address, other table or None)}
CROSSES = {}


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
            if src[0] in ('p', 'pi', 'px'):          # a moved pointer: plain arithmetic (not relocated again)
                state[rt] = (src[0], address, src[2])
                return
            k = note(address)
            if k is not None:
                state[rt] = ('p', address, k)        # a moved pointer from here on
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
        if src is not None and src[0] in ('p', 'pi', 'px'):
            address = (src[1] + imm) & MASK
            k = src[2]
            own = [r for r in ranges if r[0] == k]
            # outside the table but near it (a pointer turned into something else - an offset, a count - is not one)
            near = own and own[0][1] - 0x1000 <= address < own[0][2] + 0x1000
            if near and range_of(own, address) is None and decide is not None:
                CROSSES[pc] = (k, address, range_of(ranges, address))
        elif src is not None:
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
            v = a or b
            state[rd] = ('px', v[1], v[2]) if v[0] in ('p', 'pi', 'px') else ('x', v[1])
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
    out = {}
    for r, v in a.items():
        w = b.get(r)
        if w == v:
            out[r] = v
        elif w is not None and v[0] in ('p', 'pi', 'px') and w[0] in ('p', 'pi', 'px') and v[2] == w[2]:
            # a pointer into the same table that a loop moves on: kept with its lowest address (a lower bound;
            # only used to find accesses that reach below the table)
            out[r] = ('pi', min(v[1], w[1]), v[2])
    return out


def data_word(image, address):
    """A word of the executable's loaded data (None when the address is not in the file)."""
    import struct
    for vaddr, offset, filesz, _m in image.segments:
        if vaddr <= address and address + 4 <= vaddr + filesz:
            return struct.unpack_from('<I', image.data, offset + address - vaddr)[0]
    return None


def jump_table(image, nodes, i, index):
    """The targets of the jump table that the `jr` at node i goes through, when the compiler's pattern is there
    (`sltiu t, x, N` ... `lui r, hi` ... `lw r, lo(r)` ... `jr r` within a few instructions): the N words of the
    table that are code of this unit.  None when the pattern is not found (then every label, as before)."""
    reg = (nodes[i][1] >> 21) & 31
    table, bound, upper = None, None, {}
    for j in range(i - 1, max(-1, i - 12), -1):
        w = nodes[j][1]
        op, rs, rt = w >> 26, (w >> 21) & 31, (w >> 16) & 31
        if table is None and op == 0x23 and rt == reg:                 # lw reg, lo(base)
            table = ('lw', rs, sx16(w))
        elif isinstance(table, tuple) and op == 0x0F and rt == table[1]:
            table = ((w & 0xFFFF) << 16) + table[2]
        elif op == 0x0B and bound is None:                              # sltiu t, x, N
            bound = w & 0xFFFF
    if not isinstance(table, int) or not bound or bound > 512:
        return None
    out = []
    for k in range(bound):
        t = data_word(image, (table + 4 * k) & MASK)
        if t is None or t not in index:
            return None
        out.append(index[t])
    return out


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
                # its own targets when the table can be read (a state that reaches every label of the unit from
                # every jump table loses the registers that stay the same across one dispatch), else every label
                targets = jump_table(image, nodes, i, index)
                out += [(j, 'after') for j in (targets if targets is not None else labels)]
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
        # the delta is added to the whole OR (C++ would add it to the immediate first: `r | imm + delta`), in 32 bits
        # with the sign extension of a MIPS address (lui values are sign-extended)
        old = ' | 0x%xull' % (w & 0xFFFF)
        head, eq, rhs = text.partition(' = ')
        if eq and rhs.endswith(';') and old in rhs:
            expr = rhs[:-1]
            return '%s = SX32((u32)(%s) + g_reloc[%d]);' % (head, expr, k)
        return None
    return None


# ---- hard-coded fours (docs/issues/native-8-players.md A.9 step 2) -----------------------------------------------
# A list of instruction addresses whose immediate 4 is the number of player slots (a loop over the four peers, the
# four button tables, ...): the translation emits g_party8_slots there instead (4 unless a game of five to eight runs,
# then 8).  File format: one hex address per line, `#` comments.

# A line may name another kind of site after the address:
#   rxmask   net_receivePackets' `sra $10, $10, 4` (the active mask from the input packet's high nibble): in a game of
#            five to eight the whole mask the network layer took off the packet's trailer (rt/moved.h g_party8_rx_mask)
#   rows:N   an addiu / load / store offset in units of rows of N bytes, a row holding one entry per slot: in a game of
#            five to eight floor(imm / N) x 2N + imm mod N (the rows are moved 2N apart)
#   last     `addiu r, $zero, 3`, the first slot of a count-down over the four: g_party8_slots - 1
#   memtop   `lui r, 0x200`: the top of memory the game's heap is sized by (rt/moved.h g_party8_memtop)
#   shl+1    `sll rd, rt, sa` whose result is a row offset (row x 0x160 made as (row x 11) << 5): sa + 1
#   lastoff:N  `addiu r, r, 3N`: from an array's first element of N bytes to its last of four - of g_party8_slots

def read_sites(path):
    sites = {}
    with open(path) as source:
        for line in source:
            fields = line.split('#')[0].split()
            if fields:
                sites[int(fields[0], 16)] = fields[1] if len(fields) > 1 else 'slots'
    return sites


def slots(pc, w, text, kind='slots'):
    """The statement with its immediate 4 replaced by g_party8_slots; None when the instruction is not one of the
    forms with an immediate 4 (slti, sltiu, addiu, daddiu, ori with 4)."""
    op = w >> 26
    if kind == 'rxmask':
        # sra rd, rt, 4
        if op != 0 or (w & 63) != 0x03 or ((w >> 6) & 31) != 4:
            return None
        head, eq, rhs = text.partition(' = ')
        if not eq or not rhs.endswith(';'):
            return None
        return '%s = g_party8_slots > 4 ? (u64)g_party8_rx_mask : %s;' % (head, rhs[:-1])
    if kind.startswith('rows:'):
        # an offset or step in units of a table's rows, each row one entry per player slot (the equipment cache: rows of
        # 0x160 = 4 x 0x58): in a game of five to eight the rows lie twice as far apart (party8.cpp places them so)
        row = int(kind.split(':', 1)[1], 0)
        imm = sx16(w)
        wide = (imm // row) * 2 * row + imm % row
        token = '0x%xu' % (imm & 0xFFFFFFFF)
        if op not in (0x09,) and op not in LOADS and op not in STORES:
            return None
        if text.count(token) != 1:
            return None
        return text.replace(token, '(g_party8_slots > 4 ? 0x%xu : %s)' % (wide & 0xFFFFFFFF, token))
    if kind == 'memtop':
        # `lui r, 0x200` (32 MB): the top of memory the game sizes its heap by - rt/moved.h g_party8_memtop
        if op != 0x0F or (w & 0xFFFF) != 0x200 or not text.endswith(' = 0x2000000ull;'):
            return None
        return text[:-len('0x2000000ull;')] + '(u64)g_party8_memtop;'
    if kind == 'shl+1':
        # `sll rd, rt, sa` that makes a row offset (rows of one entry per slot): one more in a game of five to eight
        sa = (w >> 6) & 31
        token = ' << %d)' % sa
        if op != 0 or (w & 63) != 0 or text.count(token) != 1:
            return None
        return text.replace(token, ' << (g_party8_slots > 4 ? %d : %d))' % (sa + 1, sa))
    if kind.startswith('lastoff:'):
        # `addiu r, r, 3 x size`: the last of four elements of `size` bytes -> the last of g_party8_slots
        size = int(kind.split(':', 1)[1], 0)
        token = ' + 0x%xu)' % (3 * size)
        if op != 0x09 or sx16(w) != 3 * size or text.count(token) != 1:
            return None
        return text.replace(token, ' + (g_party8_slots - 1) * %du)' % size)
    if kind == 'last':
        # the last slot of a count-down over the four slots (`addiu r, $zero, 3` ... `bgez`): 3, or 7
        if op != 0x09 or (w & 0xFFFF) != 3 or ((w >> 21) & 31) != 0 or not text.endswith(' = 0x3ull;'):
            return None
        return text[:-len('0x3ull;')] + '(u64)(g_party8_slots - 1);'
    if kind != 'slots' or (w & 0xFFFF) != 4:
        return None
    if op == 0x0A and '(s64)4)' in text:                                     # slti
        return text.replace('(s64)4)', '(s64)g_party8_slots)', 1)
    if op == 0x0B and '< 0x4ull)' in text:                                   # sltiu
        return text.replace('< 0x4ull)', '< (u64)g_party8_slots)', 1)
    if op == 0x09 and ' + 0x4u)' in text:                                    # addiu
        return text.replace(' + 0x4u)', ' + g_party8_slots)', 1)
    if op == 0x09 and text.endswith(' = 0x4ull;'):                           # addiu r, $zero, 4
        return text[:-len('0x4ull;')] + '(u64)g_party8_slots;'
    if op == 0x19 and ' + 0x4ull' in text:                                   # daddiu
        return text.replace(' + 0x4ull', ' + (u64)g_party8_slots', 1)
    if op == 0x0D and ' | 0x4ull' in text:                                   # ori
        return text.replace(' | 0x4ull', ' | (u64)g_party8_slots', 1)
    return None
