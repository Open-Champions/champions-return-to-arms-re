#!/usr/bin/env python3
"""fieldxref.py ELF OFF[,OFF|LO-HI ...] [options] -- who loads, stores or takes the address of a
structure field. OFF is a hexadecimal byte offset, LO-HI an inclusive byte range.

  --stores | --loads      only stores (and addresses handed on) / only loads
  --class NAME[,NAME]     only functions in that class's virtual table (vtables.txt names; read
                          from the ELF) or whose symbol starts with NAME_
  --func HEX[,HEX]        only these functions (entry addresses)
  --range LO:HI           only instructions in this address range
  --this                  only accesses whose base is the function's first argument (a0), or a
                          pointer derived from it: with --class, "this object's own field"
  --array START,STRIDE,COUNT   OFF lies in an array inside the structure: also list indexed and
                          walking accesses that start anywhere in the array (possible hits)
  --static BASE[,STRIDE[,COUNT]]   the structure also exists at a fixed address (COUNT instances
                          STRIDE apart): list absolute accesses to OFF of any instance
  --adjust N              also search OFF-N (a `this` shifted by N; see "cannot see" 6)
  --blocks                also list calls that receive the object's own address together with
                          a constant length that reaches OFF (possible block copy or fill)
  --roots                 print where each hit's base pointer came from
  --certain               drop the possible ('?') hits
  --walk-limit N          how far (bytes, hex) a walking pointer is assumed to travel (200)
  --no-cache              do not read or write disasm/text.fx.pickle

How it works. Every function (bodies from ghidra_funcs.tsv; code no function contains is
grouped and marked) is run through a forward data-flow pass over its real control flow:
branches, delay slots and likely-branches are followed, and values are merged where paths
join. Each register holds "root + constant", where a root is the function's incoming value of
a register, a value loaded from memory, a call's return value or the result of a join.
`addiu`, `move`, `addu`/`subu` with a constant, and spills to the stack frame are followed, so
a pointer formed as object + K and used with a small displacement is reported at the sum. A
pointer that is stepped inside a loop becomes "root + start + n*step". Tracked values in
registers a call may destroy are kept after the call but marked possible. A block reached only
through a jump table is given the merged state of the function's indirect jumps.

Output: one line per function, hits as ADDRESS:OP+OFFSET with marks
  sd+40*          covering: the access starts below OFF and its width reaches it
  uld / usd / ulw / usw   an unaligned (left/right pair) 8- or 4-byte load or store
  sw+0{a0+36c}    derived: the base register holds a0 + 0x36c (displacement 0)
  sw+0{a0+36c~4}  the base walks from there in steps of 4 (listed for every OFF it can reach
                  within --walk-limit; only the first element is certain)
  lw+36c[i]       an index register was added to the base: element i of an array at +0x36c
  lw@4dd54c       absolute access (with --static)
  &+364>NAME      the address of +0x364 is passed to NAME (or `&+364=` stored in memory)
  &+300..100?     a pointer to +0x300 is passed with a constant length 0x100 that reaches OFF
  ?               possible, not certain: the base survived a call in a caller-saved register,
                  came back from the stack frame of a function that takes the address of a
                  local, is in code outside every function, or the hit is a later element of
                  a walking / indexed access
A hit without '?' is certain in this sense only: on every path the instruction touches that
byte offset from the pointer the tool names. It is not a statement about the pointer's type.

What it still cannot see
 1. Which structure. A displacement says nothing about the type of the base. Narrow with
    --class (functions of the class and of its bases that appear in its virtual table),
    --this, --func, --range, and read --roots: a base that is the function's a0 in a class
    method is that class; a base loaded from memory or returned by a call is the reader's
    job to identify, by reading the function.
 2. A base pointer whose constant part was added somewhere the pass does not follow: in
    another function (a callee receives object + K and uses small displacements: only the
    `&+K>callee` line shows it), in memory other than the stack frame, or folded into an
    index register.
 3. Indexed access to an array element other than through --array, and the element a
    walking pointer finally reaches: both are listed as possible for the whole array.
 4. Whole-object copies, fills and comparisons made by a called routine starting at the
    object's own address (clone, save, load): --blocks lists the calls with a constant
    length; a computed length is not seen.
 5. Static instances reached through an address that is not a constant in the code (a
    pointer table, a base folded into the index): --static finds lui/addiu forms only.
 6. A shifted `this`. Only two virtual tables in this executable (library classes) have a
    non-zero adjustment; --adjust N searches the shifted offset.
 7. Values merged from different pointers at a join are forgotten (the hit is then listed at
    its plain displacement only); jump tables are not read, so a wrong guess about a block
    with no visible predecessor can attach a stale register (rare; only derived hits).
 8. 128-bit loads and stores (lq/sq) are decoded from the ELF; vector-unit register moves are
    not memory accesses and are ignored."""
import sys, re, os, bisect, heapq, pickle
from math import gcd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textinput import text_lines

VERSION = 11
MASK64 = (1 << 64) - 1

LOADINFO = {  # op -> (bits, signed load, left half)
    'lb': (8, 1, 0), 'lbu': (8, 0, 0), 'lh': (16, 1, 0), 'lhu': (16, 0, 0), 'lw': (32, 1, 0),
    'lwu': (32, 0, 0), 'lwc1': (32, 0, 0), 'ld': (64, 1, 0), 'lq': (128, 0, 0),
    'lwr': (32, 1, 0), 'lwl': (32, 1, 1), 'ldr': (64, 1, 0), 'ldl': (64, 1, 1)}
STORE_W = {'sb': 1, 'sh': 2, 'sw': 4, 'swc1': 4, 'sd': 8, 'sq': 16,
           'swr': 4, 'swl': 4, 'sdr': 8, 'sdl': 8}
WIDTH = dict({k: v[0] // 8 for k, v in LOADINFO.items()}, **STORE_W)
LEFT = {'lwl': 3, 'swl': 3, 'ldl': 7, 'sdl': 7}      # displacement names the last byte
PAIR = {'lwl': 'ulw', 'lwr': 'ulw', 'ldl': 'uld', 'ldr': 'uld',
        'swl': 'usw', 'swr': 'usw', 'sdl': 'usd', 'sdr': 'usd'}
# what the scanner printed before it was rewritten
OLD_LOADS = {'lw', 'lh', 'lhu', 'lb', 'lbu', 'lwc1', 'ld', 'lwu', 'lq'}
OLD_STORES = {'sw', 'sh', 'sb', 'swc1', 'sd', 'sq'}

(C_NOP, C_ADDI, C_MOVE, C_LOAD, C_STORE, C_LUI, C_ADD, C_SUB, C_LOGI, C_LOG, C_SHI, C_SHV,
 C_WR, C_SET, C_CMOV, C_BR, C_J, C_JR, C_CALL) = range(19)

NOWRITE = set(STORE_W) | {'mtc1', 'dmtc1', 'ctc1', 'ctc2', 'qmtc2', 'mtc0', 'mthi', 'mtlo',
                          'mthi1', 'mtlo1', 'mtsa', 'teq', 'tge', 'tlt', 'tne', 'cache', 'pref',
                          'break', 'nop', 'sync', 'eret', 'sdbbp', 'dmtc2', 'unk', '<unknown>'}
TWO_OP_HILO = {'mult', 'multu', 'div', 'divu', 'dmult', 'dmultu', 'ddiv', 'ddivu', 'madd',
               'maddu'}
CALLER_SAVED = ['$%d' % i for i in list(range(1, 16)) + [24, 25]]
ARGREGS = ['$%d' % i for i in range(4, 12)]
ARGNAME = {'$%d' % (i + 4): 'a%d' % i for i in range(8)}
SIGN_BR = {'bltz', 'bgez', 'bltzl', 'bgezl', 'blez', 'bgtz', 'blezl', 'bgtzl'}
ZERO_BR = {'beqz', 'bnez', 'beqzl', 'bnezl', 'beq', 'bne', 'beql', 'bnel'}
REGNAME = ['$zero'] + ['$%d' % i for i in range(1, 28)] + ['$gp', '$sp', '$fp', '$ra']
SPROOT = ('E', '$sp')
ZERO = (0, 0, 0, 0, 0, 0)

# Register values.
#   (0, root, delta, step, ix, weak)   root + delta (+ n*step) (+ an unknown index when ix)
#        root 0 is "absolute": delta is then a constant or a fixed address
#   (1, load address, sh, valid, set, cleared, toggled, sign bit, shifted, bits, weak)
#        a value loaded from memory, possibly shifted and masked: register bit j is bit
#        j + sh of the loaded quantity; masks are in loaded-quantity bit numbers. Where
#        paths join with the same field loaded on each, the address is a tuple of loads
#   (2, inverted, weak)                a one-bit mask whose bit number is not a constant
#   (3, load address, weak)            a loaded value shifted right by a variable amount


class _Defaults(dict):
    def __missing__(self, r):
        v = self[r] = (0, ('E', r), 0, 0, 0, 0)
        return v


DEF = _Defaults()
DEF['$zero'] = ZERO


def s32(v):
    v &= 0xffffffff
    return v - (1 << 32) if v & 0x80000000 else v


def s64(v):
    v &= MASK64
    return v - (1 << 64) if v >> 63 else v


def _range_mask(lo, hi):
    if lo < 0: lo = 0
    if hi < lo: return 0
    return ((1 << (hi + 1)) - 1) & ~((1 << lo) - 1)


# ---------------------------------------------------------------- listing

def decode_unknown(w):
    """Mnemonic and operands for the R5900 words llvm-objdump prints as <unknown>."""
    if w is None: return 'unk', []
    op = w >> 26; rs = (w >> 21) & 31; rt = (w >> 16) & 31; rd = (w >> 11) & 31
    simm = (w & 0xffff) - ((w & 0x8000) << 1)
    if op in (0x1e, 0x1f):
        return ('lq' if op == 0x1e else 'sq'), [REGNAME[rt], '%d(%s)' % (simm, REGNAME[rs])]
    if op == 0 and (w & 0x3f) in (0x18, 0x19) and rd:      # three-operand mult / multu
        return 'mult3', [REGNAME[rd]]
    if op == 0 and (w & 0x3f) == 0x28:                     # mfsa
        return 'mfsa', [REGNAME[rd]]
    if op == 0x1c:                                         # MMI
        f = w & 0x3f
        if f in (0x11, 0x13, 0x1a, 0x1b, 0x31): return 'unk', []
        return 'mmi', [REGNAME[rd]]
    if op == 0x12 and rs in (1, 2):                        # qmfc2 / cfc2
        return 'cfc2', [REGNAME[rt]]
    return 'unk', []


_LINE = re.compile(r'^\s*([0-9a-f]+):\s+(\S+)\s*(.*)$')
_MEM = re.compile(r'^(-?(?:0x[0-9a-f]+|\d+))\((\$\w+)\)$')


def _imm(s):
    try: return int(s, 0)
    except ValueError: return None


def parse_listing(lines, word_at=None):
    """llvm-objdump lines -> [(addr, op, class, a, b, c, target)]."""
    out = []; elided = False
    for l in lines:
        m = _LINE.match(l)
        if not m:
            if l.strip() == '...': elided = True     # objdump skipped a run of zero words
            continue
        a = int(m.group(1), 16); op = m.group(2)
        if elided:
            elided = False
            if out and 4 < a - out[-1][0] <= 0x1000:
                out.extend((z, 'nop', C_NOP, None, None, None, None)
                           for z in range(out[-1][0] + 4, a, 4))
        p = [x.strip() for x in m.group(3).split('<')[0].split(',')] if m.group(3) else []
        p = [x for x in p if x]
        if op == '<unknown>':
            op, p = decode_unknown(word_at(a) if word_at else None)
        out.append(_classify(a, op, p))
    return out


def _classify(a, op, p):
    n = len(p)
    if op in LOADINFO or op in STORE_W:
        mm = _MEM.match(p[1]) if n == 2 else None
        if mm:
            return (a, op, C_LOAD if op in LOADINFO else C_STORE, p[0], int(mm.group(1), 0),
                    mm.group(2), None)
        return (a, op, C_NOP, None, None, None, None)
    if op in ('addiu', 'daddiu', 'addi', 'daddi') and n == 3 and _imm(p[2]) is not None:
        return (a, op, C_ADDI, p[0], p[1], _imm(p[2]), None)
    if op == 'move' and n == 2:
        return (a, op, C_MOVE, p[0], p[1], None, None)
    if op == 'lui' and n == 2 and _imm(p[1]) is not None:
        return (a, op, C_LUI, p[0], None, _imm(p[1]), None)
    if op in ('addu', 'daddu', 'add', 'dadd') and n == 3:
        return (a, op, C_ADD, p[0], p[1], p[2], None)
    if op in ('subu', 'dsubu', 'sub') and n == 3:
        return (a, op, C_SUB, p[0], p[1], p[2], None)
    if op in ('andi', 'ori', 'xori') and n == 3 and _imm(p[2]) is not None:
        return (a, op, C_LOGI, p[0], p[1], _imm(p[2]) & 0xffff, None)
    if op in ('and', 'or', 'xor', 'nor') and n == 3:
        return (a, op, C_LOG, p[0], p[1], p[2], None)
    if op in ('sll', 'srl', 'sra', 'dsll', 'dsrl', 'dsra', 'dsll32', 'dsrl32', 'dsra32') \
            and n == 3 and _imm(p[2]) is not None:
        return (a, op, C_SHI, p[0], p[1], _imm(p[2]), None)
    if op in ('sllv', 'srlv', 'srav', 'dsllv', 'dsrlv', 'dsrav') and n == 3:
        return (a, op, C_SHV, p[0], p[1], p[2], None)
    if op in ('slt', 'sltu', 'slti', 'sltiu') and n == 3:
        return (a, op, C_SET, p[0], p[1], p[2], None)
    if op in ('movn', 'movz') and n == 3:
        return (a, op, C_CMOV, p[0], p[1], p[2], None)
    if op in ('jal', 'jalr', 'bal', 'bgezal', 'bltzal'):
        return (a, op, C_CALL, None, None, None, _imm(p[-1]) if op != 'jalr' and p else None)
    if op == 'syscall':
        return (a, op, C_WR, '$2', None, None, None)
    if op == 'jr':
        return (a, op, C_JR, p[0] if p else '$ra', None, None, None)
    if op in ('j', 'b'):
        return (a, op, C_J, None, None, None, _imm(p[-1]) if p else None)
    if op[0] == 'b' and op not in ('break',) and p and _imm(p[-1]) is not None \
            and not op.startswith('bbit'):
        regs = [x for x in p[:-1] if x.startswith('$')]
        return (a, op, C_BR, regs[0] if regs else None, regs[1] if len(regs) > 1 else None,
                op.endswith('l') and op not in ('bal',), _imm(p[-1]))
    if p and p[0].startswith('$') and not p[0].startswith('$f') and op not in NOWRITE \
            and not (op in TWO_OP_HILO and n == 2) and op[0] != 'b' and op[0] != 't':
        return (a, op, C_WR, p[0], None, None, None)
    return (a, op, C_NOP, None, None, None, None)


def load_bodies(path):
    """[(entry, [(lo, hi inclusive)])] from ghidra_funcs.tsv."""
    out = []
    for l in text_lines(path):
        p = l.rstrip('\r\n').split('\t')
        try: ent = int(p[0], 16)
        except ValueError: continue
        rs = []
        for r in (p[2].split(',') if len(p) > 2 else []):
            try: lo, hi = (int(x, 16) for x in r.split('-'))
            except ValueError: continue
            rs.append((lo, hi))
        if rs: out.append((ent, rs))
    return out


def split_functions(ins, bodies):
    """Group instructions by function. Returns [(entry, [instr], outside_any_function)]."""
    rng = sorted((lo, hi, ent) for ent, rs in bodies for lo, hi in rs)
    los = [r[0] for r in rng]
    groups = {}; order = []; orphan = None; prev = None
    for x in ins:
        a = x[0]; i = bisect.bisect_right(los, a) - 1
        if i >= 0 and rng[i][0] <= a <= rng[i][1]:
            key = (rng[i][2], False); orphan = None
        else:
            if orphan is None or prev is None or a != prev + 4: orphan = a
            key = (orphan, True)
        if key not in groups: groups[key] = []; order.append(key)
        groups[key].append(x); prev = a
    return [(k[0], groups[k], k[1]) for k in order]


# ---------------------------------------------------------------- transfer functions

def _plain(v):
    return v[2] == 0 and not v[4] and not v[5] and not v[6] and not v[8]


def _narrow(v):
    """A loaded value that has been masked or shifted down to part of its bits."""
    return v[3] != (1 << abs(v[9])) - 1


def _ptr(v, a):
    """The pointer view of a value used as a base register."""
    t = v[0]
    if t == 0: return v
    if t == 1: return (0, ('L', v[1]), 0, 0, 0 if _plain(v) else 1, v[-1])
    return (0, ('U', a), 0, 0, 1, v[-1])


def _isconst(v):
    return v[0] == 0 and v[1] == 0 and not v[3] and not v[4]


_SCORE = {'E': 2, 'L': 2, 'R': 2, 'J': 1}


def _score(p):
    """How pointer-like an addu operand is: the better one is taken as the base."""
    if p[1] == 0 or p[2] or p[3]: return 3
    return _SCORE.get(p[1][0], 0)


def _bitop(a, op, v, c, ev):
    """and / or / xor of a tracked value with the constant c."""
    t = v[0]
    if t == 1:
        _, da, sh, valid, setm, clrm, tglm, sbit, shn, lbits, wk = v
        full = (1 << abs(lbits)) - 1
        rm = c & MASK64
        lm = ((rm << sh) if sh >= 0 else (rm >> -sh)) & full
        if op == 'and':
            if ev is not None: ev[2].append((a, 'and', da, lm & valid, valid, wk))
            return (1, da, sh, valid & lm, setm, clrm | (valid & ~lm), tglm,
                    sbit if c < 0 else None, 0, lbits, wk)
        if op == 'or':
            if ev is not None and lm: ev[2].append((a, 'or', da, lm, valid, wk))
            return (1, da, sh, valid | lm, setm | lm, clrm, tglm,
                    None if c < 0 else sbit, shn, lbits, wk)
        if ev is not None and lm: ev[2].append((a, 'xor', da, lm, valid, wk))
        return (1, da, sh, valid | lm, setm, clrm, tglm | lm, sbit, shn, lbits, wk)
    if t == 3:
        if ev is not None: ev[2].append((a, op + '.varshift', v[1], None, 0, v[-1]))
    return (0, ('U', a), 0, 0, 0, 0)


def _shift(a, op, v, n):
    left = op in ('sll', 'dsll', 'dsll32'); wide = op[0] == 'd'
    if op.endswith('32'): n += 32
    top = 63 if wide else 31
    if _isconst(v):
        c = v[2]
        if left: r = c << n
        elif op.startswith('sra') or op.startswith('dsra'): r = (c if wide else s32(c)) >> n
        else: r = (c & (MASK64 if wide else 0xffffffff)) >> n
        return (0, 0, s64(r) if wide else s32(r), 0, 0, v[5])
    if v[0] == 1:
        _, da, sh, valid, setm, clrm, tglm, sbit, shn, lbits, wk = v
        w = abs(lbits)
        if left:
            nsh = sh - n
            nvalid = valid & _range_mask(sh, nsh + top)
            b = nsh + top
            if b >= w: b = w - 1 if lbits > 0 else None
            elif b < 0: b = None
            return (1, da, nsh, nvalid, setm, clrm, tglm, b, 1 if n else shn, lbits, wk)
        nsh = sh + n
        nvalid = valid & _range_mask(nsh, nsh + top)
        arith = 'sra' in op
        return (1, da, nsh, nvalid, setm, clrm, tglm, sbit if (arith or not n) else None,
                1 if n else shn, lbits, wk)
    if v[0] == 3: return v
    return (0, ('U', a), 0, 0, 0, 0)


def _rootstr(r):
    if r == 0: return 'A'
    k = r[0]
    if k == 'E': return 'E' + r[1]
    if k == 'J': return 'J%x.%s' % (r[1], r[2])
    if k == 'O': return 'O%x.%s' % (r[1], r[2])
    if r[1].__class__ is tuple: return k + '/'.join('%x' % v for v in r[1])
    return '%s%x' % (k, r[1])


def step(x, st, ev, esc):
    """Apply one instruction (not a branch, jump or call) to the state st.
    ev: None, or [accesses, address events, flag events]. esc: a local's address escapes."""
    c = x[2]
    if c == C_NOP: return
    a = x[0]; r1 = x[3]
    if c == C_ADDI:
        v = st.get(x[4])
        if v is None: v = DEF[x[4]]
        if r1 == '$zero': return
        imm = x[5]
        if v[0] == 0:
            if v[1] == 0:
                nd = v[2] + imm
                st[r1] = (0, 0, s64(nd) if x[1][0] == 'd' else s32(nd), v[3], v[4], v[5])
            else:
                st[r1] = (0, v[1], v[2] + imm, v[3], v[4], v[5])
        elif v[0] == 1:
            st[r1] = (0, ('L', v[1]), imm, 0, 0 if _plain(v) else 1, v[-1])
        else:
            st[r1] = (0, ('U', a), 0, 0, 0, 0)
        return
    if c == C_MOVE:
        if r1 == '$zero': return
        v = st.get(x[4])
        st[r1] = DEF[x[4]] if v is None else v
        return
    if c == C_LOAD:
        op = x[1]; d = x[4]; b = x[5]
        if b == '$sp':
            if r1[1] == 'f' or r1 == '$zero': return
            v = None
            if op == 'ld' or op == 'lw':
                spv = st.get('$sp')
                if spv is None: v = st.get(d)
                elif spv[1] == SPROOT and not spv[3] and not spv[4]: v = st.get(spv[2] + d)
            if v is None: st[r1] = (0, ('U', a), 0, 0, 0, 0)
            else:
                if esc[0] and not v[-1]: v = v[:-1] + (1,)
                st[r1] = v
            return
        bv = st.get(b)
        if bv is None: bv = DEF[b]
        if bv[0] != 0: bv = _ptr(bv, a)
        if ev is not None:
            ev[0].append((a, op, d, _rootstr(bv[1]), bv[2], bv[3], bv[4], bv[5], None))
        if r1[1] == 'f' or r1 == '$zero': return
        bits, signed, left = LOADINFO[op]
        if left:
            cur = st.get(r1)
            if cur is not None and cur[0] == 1 and cur[1] == a - 4: return
            st[r1] = (0, ('U', a), 0, 0, 0, 0)
            return
        st[r1] = (1, a, 0, (1 << bits) - 1, 0, 0, 0, bits - 1 if signed else None, 0,
                  bits if signed else -bits, bv[5])
        return
    if c == C_STORE:
        op = x[1]; d = x[4]; b = x[5]
        if b == '$sp':
            spv = st.get('$sp')
            if spv is None: key = d
            elif spv[1] == SPROOT and not spv[3] and not spv[4]: key = spv[2] + d
            else: return
            st.pop(key - 4, None); st.pop(key + 4, None)
            if (op == 'sd' or op == 'sw') and r1[1] != 'f':
                v = st.get(r1)
                st[key] = DEF[r1] if v is None else v
            else:
                st.pop(key, None)
            return
        if ev is None: return
        bv = st.get(b)
        if bv is None: bv = DEF[b]
        if bv[0] != 0: bv = _ptr(bv, a)
        sv = None
        if r1[1] != 'f':
            v = st.get(r1)
            if v is None: v = DEF[r1]
            if v[0] == 1:
                sv = ('F', v[1], v[2], v[4], v[5], v[6], v[-1])
                if v[8] and bin(v[3]).count('1') <= 8:
                    ev[2].append((a, 'zero', v[1], v[3], 0, v[-1]))
            elif v[0] == 0:
                if v[1] == 0:
                    if not v[3] and not v[4]: sv = ('C', v[2])
                elif v[2] != 0 and v[1] != SPROOT:
                    ev[1].append((a, 's', _rootstr(v[1]), v[2], v[4], v[5], None, 0))
        ev[0].append((a, op, d, _rootstr(bv[1]), bv[2], bv[3], bv[4], bv[5], sv))
        return
    if c == C_LUI:
        if r1 != '$zero': st[r1] = (0, 0, s32(x[5] << 16), 0, 0, 0)
        return
    if c == C_ADD or c == C_SUB:
        va = st.get(x[4]); vb = st.get(x[5])
        if va is None: va = DEF[x[4]]
        if vb is None: vb = DEF[x[5]]
        if r1 == '$zero': return
        wide = x[1][0] == 'd'
        ca = _isconst(va); cb = _isconst(vb)
        wk = va[-1] | vb[-1]
        if c == C_SUB:
            if ca and cb:
                r = va[2] - vb[2]
                st[r1] = (0, 0, s64(r) if wide else s32(r), 0, 0, wk)
            elif cb and abs(vb[2]) < 0x10000:
                p = _ptr(va, a)
                st[r1] = (0, p[1], p[2] - vb[2], p[3], p[4], wk)
            else:
                st[r1] = (0, ('U', a), 0, 0, 0, 0)
            return
        if ca and cb:
            r = va[2] + vb[2]
            st[r1] = (0, 0, s64(r) if wide else s32(r), 0, 0, wk)
            return
        if ca or cb:
            k, o = (va, vb) if ca else (vb, va)
            if 0x10000 <= (k[2] & 0xffffffff) < 0xf0000000:     # an address plus an index
                st[r1] = (0, 0, k[2], 0, 1, wk)
            else:                                               # a pointer plus a small constant
                p = _ptr(o, a)
                st[r1] = (0, p[1], p[2] + k[2], p[3], p[4], wk)
            return
        pa = _ptr(va, a); pb = _ptr(vb, a)
        base = pb if _score(pb) > _score(pa) else pa
        st[r1] = (0, base[1], base[2], base[3], 1, wk)
        return
    if c == C_LOGI:
        v = st.get(x[4])
        if v is None: v = DEF[x[4]]
        if r1 == '$zero' and ev is None: return
        op = x[1][:-1]; imm = x[5]
        if _isconst(v):
            cv = v[2]
            r = cv & imm if op == 'and' else cv | imm if op == 'or' else cv ^ imm
            res = (0, 0, r, 0, 0, v[5])
        else:
            res = _bitop(a, op, v, imm, ev)
        if r1 != '$zero': st[r1] = res
        return
    if c == C_LOG:
        va = st.get(x[4]); vb = st.get(x[5])
        if va is None: va = DEF[x[4]]
        if vb is None: vb = DEF[x[5]]
        op = x[1]
        ca = _isconst(va); cb = _isconst(vb)
        if ca and cb:
            p, q = va[2], vb[2]
            r = p & q if op == 'and' else p | q if op == 'or' else p ^ q if op == 'xor' else ~(p | q)
            res = (0, 0, r, 0, 0, va[5] | vb[5])
        elif op == 'nor':
            o = vb if (ca and va[2] == 0) else va if (cb and vb[2] == 0) else None
            if o is not None and o[0] == 2: res = (2, 1 - o[1], o[-1])
            else: res = (0, ('U', a), 0, 0, 0, 0)
        elif cb: res = _bitop(a, op, va, vb[2], ev)
        elif ca: res = _bitop(a, op, vb, va[2], ev)
        else:
            f, m = (va, vb) if va[0] in (1, 3) else (vb, va)
            if f[0] == 1 and m[0] == 1 and _narrow(f) and not _narrow(m): f, m = m, f
            if f[0] == 1 and m[0] == 1 and _narrow(m) and not _narrow(f):
                # the other operand is a loaded value already cut down to a few bits: only
                # those bits can be tested, set or toggled
                rv = (m[3] >> m[2]) if m[2] >= 0 else (m[3] << -m[2])
                res = _bitop(a, op, f, rv & 0x7fffffffffffffff, ev)
                if r1 != '$zero': st[r1] = res
                return
            if ev is not None and f[0] in (1, 3):
                if m[0] == 2:
                    ev[2].append((a, op + ('.varclear' if m[1] else '.varbit'), f[1], None, 0,
                                  f[-1] | m[-1]))
                elif f[0] == 1:
                    mp = _ptr(m, a)
                    ev[2].append((a, op + '.reg', f[1], None,
                                  _rootstr(mp[1]) if not (mp[2] or mp[3] or mp[4]) else '',
                                  f[-1] | m[-1]))
            res = (0, ('U', a), 0, 0, 0, 0)
        if r1 != '$zero': st[r1] = res
        return
    if c == C_SHI:
        v = st.get(x[4])
        if v is None: v = DEF[x[4]]
        if r1 != '$zero': st[r1] = _shift(a, x[1], v, x[5])
        return
    if c == C_SHV:
        v = st.get(x[4]); n = st.get(x[5])
        if v is None: v = DEF[x[4]]
        if n is None: n = DEF[x[5]]
        if r1 == '$zero': return
        op = x[1]
        if _isconst(v) and _isconst(n):
            st[r1] = _shift(a, op[:-1], v, n[2] & (63 if op[0] == 'd' else 31))
        elif _isconst(v) and v[2] and op in ('sllv', 'dsllv'):
            st[r1] = (2, 0, v[5] | n[-1])
        elif v[0] == 1 and op not in ('sllv', 'dsllv'):
            st[r1] = (3, v[1], v[-1])
        else:
            st[r1] = (0, ('U', a), 0, 0, 0, 0)
        return
    if c == C_SET:
        if ev is not None:
            op = x[1]; v = st.get(x[4])
            if v is not None and v[0] == 1:
                if op in ('slt', 'slti') and x[5] in ('$zero', '0', '0x0') and v[7] is not None:
                    ev[2].append((a, 'sign', v[1], 1 << v[7], 0, v[-1]))
                elif op == 'sltiu' and v[8] and v[3] != (1 << abs(v[9])) - 1:
                    ev[2].append((a, 'zero', v[1], v[3], 0, v[-1]))
            v = st.get(x[5]) if x[5][0] == '$' else None
            if v is not None and v[0] == 1 and op == 'sltu' and x[4] == '$zero' \
                    and v[8] and v[3] != (1 << abs(v[9])) - 1:
                ev[2].append((a, 'zero', v[1], v[3], 0, v[-1]))
        if r1 != '$zero': st[r1] = (0, ('U', a), 0, 0, 0, 0)
        return
    if c == C_CMOV:
        if ev is not None:
            v = st.get(x[5])
            if v is not None and v[0] == 1 and v[8] and v[3] != (1 << abs(v[9])) - 1:
                ev[2].append((a, 'zero', v[1], v[3], 0, v[-1]))
        if r1 == '$zero': return
        va = st.get(r1); vb = st.get(x[4])
        if va is None: va = DEF[r1]
        if vb is None: vb = DEF[x[4]]
        if va != vb: st[r1] = (0, ('U', a), 0, 0, 0, 0)
        return
    if c == C_WR:
        if r1 != '$zero': st[r1] = (0, ('U', a), 0, 0, 0, 0)
        if x[1] == 'syscall': st['$3'] = (0, ('U', a), 0, 0, 0, 0)
        return


def _branch_events(x, st, ev):
    op = x[1]
    if op in SIGN_BR:
        v = st.get(x[3])
        if v is not None and v[0] == 1 and v[7] is not None:
            ev[2].append((x[0], 'sign', v[1], 1 << v[7], 0, v[-1]))
    elif op in ZERO_BR:
        for r in (x[3], x[4]):
            v = st.get(r) if r else None
            if v is not None and v[0] == 1 and v[8] and v[3] != (1 << abs(v[9])) - 1:
                ev[2].append((x[0], 'zero', v[1], v[3], 0, v[-1]))


def _after_call(x, st, ev):
    a = x[0]
    if ev is not None:
        maxlen = 0; consts = []
        for r in ARGREGS:
            v = st.get(r)
            if v is not None and _isconst(v):
                if not v[5]: consts.append((r, v[2]))
                if 0 < v[2] < 0x10000 and v[2] > maxlen: maxlen = v[2]
        if consts and x[6] is not None: ev[3].append((a, x[6], tuple(consts)))
        for r in ARGREGS:
            v = st.get(r)
            if v is None: continue
            if v[0] == 0:
                root = v[1]
                if root == 0:
                    if not v[4] and not v[3] and 0x100000 <= (v[2] & 0xffffffff) < 0x2000000:
                        ev[1].append((a, r, 'A', v[2] & 0xffffffff, 0, v[5], x[6], maxlen))
                elif root != SPROOT and (v[2] != 0 or (maxlen >= 0x40 and root[0] in 'ELRJ')):
                    ev[1].append((a, r, _rootstr(root), v[2], v[4], v[5], x[6], maxlen))
            elif v[0] == 1:
                if v[8] and bin(v[3]).count('1') <= 8:
                    ev[2].append((a, 'zero', v[1], v[3], 0, v[-1]))
                elif maxlen >= 0x40 and _plain(v):
                    ev[1].append((a, r, _rootstr(('L', v[1])), 0, 0, v[-1], x[6], maxlen))
    for r in CALLER_SAVED:
        v = st.get(r)
        if v is None: st[r] = DEF[r][:-1] + (1,)
        elif not v[-1]: st[r] = v[:-1] + (1,)
    st['$2'] = (0, ('R', a), 0, 0, 0, 0)


def _join_val(a, b, baddr, k):
    if a[0] == 0 and b[0] == 0 and a[1] == b[1]:
        d = b[2] - a[2]
        if abs(d) <= 0x4000 and (a[1] != 0 or abs(a[2]) >= 0x10000 or d == 0):
            # a pointer stepped in a loop: keep the value it entered with, the step and the
            # direction (step < 0: downward; both directions: an unknown index)
            g = gcd(gcd(abs(a[3]), abs(b[3])), abs(d))
            up = a[3] > 0 or b[3] > 0 or d > 0
            down = a[3] < 0 or b[3] < 0 or d < 0
            ix = a[4] | b[4]
            if up and down: ix = 1
            return (0, a[1], a[2], -g if (down and not up) else g, ix, a[5] | b[5])
    elif a[0] == b[0]:
        if a[:-1] == b[:-1]: return a[:-1] + (1,)
        if a[0] == 1 and a[2:-1] == b[2:-1]:
            # the same field loaded on two paths (a load copied into a delay slot is the
            # usual case): keep both load addresses
            da = a[1] if a[1].__class__ is tuple else (a[1],)
            db = b[1] if b[1].__class__ is tuple else (b[1],)
            u = tuple(sorted(set(da) | set(db)))
            if len(u) <= 6: return (1, u) + a[2:-1] + (a[-1] | b[-1],)
    return (0, ('J', baddr, k), 0, 0, 0, 0)


def _join_into(dst, src, baddr):
    """Merge state src into dst in place; True when dst changed."""
    changed = False
    for k in list(dst):
        a = dst[k]; b = src.get(k)
        if b is a or b == a: continue
        if b is None:
            if k.__class__ is int:
                del dst[k]; changed = True; continue
            b = DEF[k]
            if b == a: continue
        nv = _join_val(a, b, baddr, k)
        if nv != a:
            dst[k] = nv; changed = True
    for k in src:
        if k in dst or k.__class__ is int: continue
        b = src[k]; a = DEF[k]
        if a == b: continue
        nv = _join_val(a, b, baddr, k)
        if nv != a:
            dst[k] = nv; changed = True
    return changed


def analyze_function(ins, orphan=False):
    """Data-flow over one function.
    Returns [accesses, address events, flag events, calls with constant arguments]."""
    n = len(ins)
    pos = {x[0]: i for i, x in enumerate(ins)}
    lead = {0}; gap = set(); targeted = set()
    esc = [0]
    for i, x in enumerate(ins):
        c = x[2]
        if i + 1 < n and ins[i + 1][0] != x[0] + 4:
            lead.add(i + 1); gap.add(i)
        if c == C_BR or c == C_J:
            t = pos.get(x[6])
            if t is not None: lead.add(t); targeted.add(t)
            if i + 2 < n: lead.add(i + 2)
        elif c == C_JR:
            if i + 2 < n: lead.add(i + 2)
        elif ((c == C_ADDI or c == C_MOVE) and x[4] == '$sp' and x[3] != '$sp') \
                or (c == C_ADD and '$sp' in (x[4], x[5])):
            esc[0] = 1
    for i, x in enumerate(ins):
        if x[2] >= C_BR and (i + 1) in lead and i + 2 < n: lead.add(i + 2)
    starts = sorted(lead); nb = len(starts)
    bidx = {s: k for k, s in enumerate(starts)}
    ends = starts[1:] + [n]
    heads = []          # blocks nothing visibly jumps or falls into
    for s in starts[1:]:
        if s in targeted: continue
        if (s - 1) in gap: heads.append(s); continue
        if s >= 2 and ins[s - 2][2] in (C_J, C_JR) and (s - 2) not in gap: heads.append(s)
        elif ins[s - 1][2] in (C_J, C_JR): heads.append(s)

    def run(k, st, ev):
        i = starts[k]; end = ends[k]; out = []
        while i < end:
            x = ins[i]; c = x[2]
            if c < C_BR:
                step(x, st, ev, esc); i += 1; continue
            d = ins[i + 1] if (i + 1 < n and i not in gap) else None
            inblock = d is not None and i + 1 < end
            if c == C_CALL:
                if d is not None:
                    if inblock: step(d, st, ev, esc)
                    else:
                        st = dict(st); step(d, st, None, esc)
                _after_call(x, st, ev)
                i += 2
                if not inblock:
                    if d is not None and i < n: out.append((i, st))
                    return out, None
                continue
            if c == C_BR:
                if ev is not None: _branch_events(x, st, ev)
                if d is None: taken = fall = st
                elif x[5]:                       # likely: the delay slot runs only when taken
                    fall = st; taken = dict(st)
                    step(d, taken, ev if inblock else None, esc)
                else:
                    if not inblock: st = dict(st)
                    step(d, st, ev if inblock else None, esc)
                    taken = fall = st
                t = pos.get(x[6])
                if t is not None: out.append((t, taken))
                if d is not None and i + 2 < n and (i + 1) not in gap: out.append((i + 2, fall))
                return out, None
            if d is not None:
                if not inblock: st = dict(st)
                step(d, st, ev if inblock else None, esc)
            if c == C_J:
                t = pos.get(x[6])
                if t is not None: out.append((t, st))
                return out, None
            return out, (st if x[3] != '$ra' else None)
        if end < n and (end - 1) not in gap: out.append((end, st))
        return out, None

    instate = [None] * nb
    if orphan:
        instate[0] = {r: (0, ('O', ins[0][0], r), 0, 0, 0, 1) for r in REGNAME[1:]}
    else:
        instate[0] = {}
    work = [0]; queued = {0}
    jrout = [None]

    def push(k):
        if k not in queued:
            queued.add(k); heapq.heappush(work, k)

    def merge(t, s):
        k = bidx[t]
        if instate[k] is None:
            instate[k] = dict(s); push(k)
        elif _join_into(instate[k], s, ins[t][0]):
            push(k)

    def flow():
        while work:
            k = heapq.heappop(work); queued.discard(k)
            out, jr = run(k, dict(instate[k]), None)
            for t, s in out: merge(t, s)
            if jr is not None:
                if jrout[0] is None: jrout[0] = dict(jr); ch = True
                else: ch = _join_into(jrout[0], jr, ins[0][0] - 1)
                if ch:
                    for h in heads: merge(h, jrout[0])

    flow()
    while True:
        dead = [k for k in range(nb) if instate[k] is None]
        if not dead: break
        k = dead[0]; b = ins[starts[k]][0]
        instate[k] = {r: (0, ('O', b, r), 0, 0, 0, 1) for r in REGNAME[1:]}
        push(k); flow()
    ev = [[], [], [], []]
    for k in range(nb):
        run(k, dict(instate[k]), ev)
    return ev


# ---------------------------------------------------------------- database

def scan(ins, bodies):
    """Analyse a parsed listing. Returns the event database (a dict of plain lists)."""
    acc = []; amp = []; flg = []; cargs = []; orphans = set(); calls = {}
    for x in ins:
        if x[2] == C_CALL and x[6] is not None: calls[x[0]] = x[6]
    for ent, fins, orphan in split_functions(ins, bodies):
        if orphan: orphans.add(ent)
        ev = analyze_function(fins, orphan)
        acc.extend((e[0], ent) + e[1:] for e in ev[0])
        amp.extend((e[0], ent) + e[1:] for e in ev[1])
        flg.extend((e[0], ent) + e[1:] for e in ev[2])
        cargs.extend((e[0], ent) + e[1:] for e in ev[3])
    acc.sort(); amp.sort(); flg.sort(); cargs.sort()
    return {'acc': acc, 'amp': amp, 'flg': flg, 'cargs': cargs, 'orphans': orphans,
            'calls': calls, 'version': VERSION}


def scan_lines(lines, bodies, word_at=None):
    return scan(parse_listing(lines, word_at), bodies)


def heuristic_bodies(ins, starts):
    """Bodies from a sorted list of function start addresses (no ghidra_funcs.tsv)."""
    if not ins: return []
    starts = sorted(starts); end = ins[-1][0]
    return [(s, [(s, (starts[i + 1] - 4) if i + 1 < len(starts) else end)])
            for i, s in enumerate(starts)]


def load_db(root, elf=None, use_cache=True, warn=sys.stderr):
    asm = os.path.join(root, 'disasm', 'text.asm')
    gf = os.path.join(root, 'ghidra_funcs.tsv')
    cache = os.path.join(root, 'disasm', 'text.fx.pickle')
    stamp = (VERSION, os.path.getmtime(asm), os.path.getsize(asm),
             os.path.getmtime(gf) if os.path.exists(gf) else None)
    if use_cache and os.path.exists(cache):
        try:
            with open(cache, 'rb') as f: db = pickle.load(f)
            if db.get('stamp') == stamp: return db
        except Exception:
            pass
    ins = parse_listing(text_lines(asm), elf.u32 if elf is not None else None)
    if os.path.exists(gf):
        bodies = load_bodies(gf)
    else:
        if warn: print('warning: no ghidra_funcs.tsv, using heuristic function bounds', file=warn)
        elf.analyze(); bodies = heuristic_bodies(ins, elf.funcs)
    db = scan(ins, bodies)
    db['stamp'] = stamp
    if use_cache:
        try:
            tmp = cache + '.tmp%d' % os.getpid()
            with open(tmp, 'wb') as f: pickle.dump(db, f, pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, cache)
        except OSError:
            pass
    return db


# ---------------------------------------------------------------- queries

def access_span(op, disp):
    """(first byte, width) of a load or store."""
    w = WIDTH[op]
    return disp - LEFT.get(op, 0), w


def parse_offsets(s):
    out = []
    for part in s.split(','):
        part = part.strip()
        if not part: continue
        if '-' in part[1:]:
            lo, hi = part.split('-', 1)
            out.append((int(lo, 16), int(hi, 16) + 1))
        else:
            v = int(part, 16); out.append((v, v + 1))
    return out


def root_label(root, db=None, names=None):
    """Readable origin of a base pointer."""
    k = root[0]
    if k == 'A': return 'abs'
    if k == 'E': return ARGNAME.get(root[1:], root[1:])
    if k == 'L': return 'load@' + root[1:]
    if k == 'R':
        a = int(root[1:], 16)
        t = db['calls'].get(a) if db else None
        if t is None: return 'ret@' + root[1:]
        return 'ret:' + ((names or {}).get(t) or '%x' % t)
    if k == 'J': return 'join'
    if k == 'O': return 'nofunc'
    return 'calc'


def _sx(v):
    return '+%x' % v if v >= 0 else '-%x' % -v


def _hit_text(h, db=None, names=None, roots=False):
    op = h['op']
    if h['kind'] == 'addr':
        s = '%x:&+%x' % (h['addr'], h['start'])
        if h.get('len'): s += '..%x' % h['len']
        if h['how'] == 's': s += '='
        elif h.get('target') is not None: s += '>' + ((names or {}).get(h['target']) or '%x' % h['target'])
        else: s += '>?'
    elif h['kind'] == 'abs':
        s = '%x:%s@%x' % (h['addr'], op, h['abs'])
    else:
        s = '%x:%s%s' % (h['addr'], op, _sx(h['disp']))
        if h['cover']: s += '*'
        if h['kind'] == 'derived':
            s += '{%s%s%s}' % (root_label(h['root']), _sx(h['delta']),
                               '~%s' % _sx(h['step']).lstrip('+') if h['step'] else '')
    if h.get('ix'): s += '[i]'
    if roots and h['kind'] in ('raw', 'addr'):
        s += '/' + root_label(h['root'], db, names)
        if h['kind'] == 'raw' and h.get('delta'): s += _sx(h['delta'])
    if not h['certain']: s += '?'
    return s


def query_field(db, intervals, stores=False, loads=False, funcs=None, addr_range=None,
                this=False, array=None, static=None, adjust=0, blocks=False, certain=False,
                walk_limit=0x200):
    """Hits on the byte intervals [(lo, hi exclusive)]. Returns a list of dicts, in address
    order, with the two halves of an unaligned access merged into one hit."""
    q = list(intervals)
    if adjust: q += [(lo - adjust, hi - adjust) for lo, hi in intervals]
    orph = db['orphans']
    if static:
        sbase = static[0]; sstride = static[1] if len(static) > 1 else 0
        scount = static[2] if len(static) > 2 else 1
        send = sbase + (sstride * scount if sstride else max(hi for lo, hi in q))
    if array: astart, astride, acount = array; aend = astart + astride * acount
    lo_all = addr_range[0] if addr_range else None
    hits = []

    def overlap(s, w):
        for lo, hi in q:
            if s < hi and s + w > lo: return lo
        return None

    for (a, fn, op, disp, root, delta, stp, ix, weak, sv) in db['acc']:
        if lo_all is not None and not (addr_range[0] <= a < addr_range[1]): continue
        if funcs is not None and fn not in funcs: continue
        st = op in STORE_W
        if (stores and not st) or (loads and st): continue
        s, w = access_span(op, disp)
        h = None
        rk = root[0]
        wk = bool(weak) or fn in orph
        if this and not root == 'E$4': continue
        lo = overlap(s, w)
        if lo is not None:
            h = dict(kind='raw', disp=s, cover=s < lo, certain=True)
        elif rk != 'A' and root != 'E$sp' and (delta or stp):
            s2 = delta + s
            lo = overlap(s2, w)
            if lo is not None:
                h = dict(kind='derived', disp=s, cover=s2 < lo, certain=not wk)
            elif stp and (delta or blocks):
                g = abs(stp)
                for qlo, qhi in q:
                    # the n nearest 0 with s2 + n*g inside (qlo - w, qhi)
                    n = -((s2 - (qlo - w + 1)) // g)             # ceil((qlo - w + 1 - s2) / g)
                    if s2 + n * g >= qhi: continue
                    if n < 0: n = min(-1, (qhi - 1 - s2) // g)   # the highest that still fits
                    if abs(n * g) > walk_limit: continue
                    if (n > 0 and stp < 0 and not ix) or (n < 0 and stp > 0 and not ix): continue
                    h = dict(kind='derived', disp=s, cover=False, certain=False); break
        elif rk == 'A' and static:
            ab = (delta + s) & 0xffffffff
            if sbase <= ab < send or (ix and sbase - 0x8000 <= ab < send):
                rel = (ab - sbase) % sstride if sstride else ab - sbase
                if overlap(rel, w) is not None:
                    h = dict(kind='abs', abs=ab, disp=s, cover=False, certain=not wk and not ix)
        if h is None and array and (ix or stp):
            for s2 in ((s, delta + s) if (delta and rk != 'A') else (s,)):
                if astart <= s2 < aend:
                    rel = (s2 - astart) % astride
                    for qlo, qhi in q:
                        f = (qlo - astart) % astride       # the field's offset in an element
                        if astart <= qlo < aend and rel < f + (qhi - qlo) and rel + w > f:
                            h = dict(kind='raw' if s2 == s else 'derived', disp=s, cover=False,
                                     certain=False)
                    if h: break
        if h is None: continue
        if certain and not h['certain']: continue
        h.update(addr=a, func=fn, op=op, root=root, delta=delta, step=stp, ix=ix, store=st,
                 width=w)
        hits.append(h)
    if not loads:
        for (a, fn, how, root, delta, ix, weak, tgt, maxlen) in db['amp']:
            if lo_all is not None and not (addr_range[0] <= a < addr_range[1]): continue
            if funcs is not None and fn not in funcs: continue
            if this and root != 'E$4': continue
            wk = bool(weak) or fn in orph
            h = None
            if root == 'A':
                if not static: continue
                if not (sbase <= delta < send): continue
                rel = (delta - sbase) % sstride if sstride else delta - sbase
                if overlap(rel, 1) is not None: h = dict(certain=not wk, len=0)
                elif maxlen and blocks and overlap(rel, maxlen) is not None:
                    h = dict(certain=False, len=maxlen)
                delta = rel
            elif delta == 0:
                if blocks and maxlen and overlap(0, maxlen) is not None:
                    h = dict(certain=False, len=maxlen)
            elif overlap(delta, 1) is not None:
                h = dict(certain=not wk, len=0)
            elif blocks and maxlen and overlap(delta, maxlen) is not None:
                h = dict(certain=False, len=maxlen)
            if h is None or (certain and not h['certain']): continue
            h.update(kind='addr', addr=a, func=fn, op='&', start=delta, root=root, how=how,
                     target=tgt, ix=ix, store=True, width=0)
            hits.append(h)
    hits.sort(key=lambda h: h['addr'])
    # merge the halves of an unaligned access
    out = []
    for h in hits:
        p = out[-1] if out else None
        if p and h['op'] in PAIR and p.get('half') and p['addr'] == h['addr'] - 4 \
                and PAIR[h['op']] == p['op'] and p['disp'] == h['disp'] and p['func'] == h['func']:
            p['half'] = False
            continue
        if h['op'] in PAIR:
            h = dict(h, op=PAIR[h['op']], half=True)
        out.append(h)
    return out


def format_hits(hits, db, names, roots=False, width=22):
    by = {}
    for h in hits: by.setdefault(h['func'], []).append(h)
    lines = []
    for f in sorted(by):
        nm = names.get(f, '')
        if f in db['orphans']: nm = nm or '(outside any function)'
        lines.append('%s %-*s %s' % (hex(f), width, nm,
                                     ' '.join(_hit_text(h, db, names, roots) for h in by[f])))
    return lines


def class_functions(elf, names, classes):
    """Entry addresses of functions that belong to the named classes: every function in a
    virtual table of that class, and every symbol called CLASS_something."""
    import vtab
    want = {c.lower() for c in classes}
    out = set()
    if elf is not None:
        for addr, (name, ents) in vtab.find_vtables(elf).items():
            if name.lower() in want:
                out.update(fn for delta, fn in ents)
    for a, nm in names.items():
        if '_' in nm and nm.split('_', 1)[0].lower() in want: out.add(a)
    return out


def parse_common(argv):
    """Split argv into positionals and the options shared by fieldxref and flagxref."""
    opts = {}; pos = []
    i = 0
    valued = {'--class', '--func', '--range', '--array', '--static', '--adjust', '--walk-limit'}
    while i < len(argv):
        a = argv[i]
        if a in valued:
            if i + 1 >= len(argv): raise SystemExit('%s needs a value' % a)
            opts[a] = argv[i + 1]; i += 2
        elif a.startswith('--'):
            opts[a] = True; i += 1
        else:
            pos.append(a); i += 1
    return pos, opts


def resolve_filters(opts, elf, names, body_of=None):
    funcs = None
    if '--func' in opts:
        funcs = {int(x, 16) for x in opts['--func'].split(',') if x}
    if '--class' in opts:
        cf = class_functions(elf, names, opts['--class'].split(','))
        funcs = cf if funcs is None else funcs | cf
    rng = None
    if '--range' in opts:
        lo, hi = opts['--range'].replace('-', ':').split(':')
        rng = (int(lo, 16), int(hi, 16))
    return funcs, rng


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    pos, opts = parse_common(argv)
    if len(pos) < 2 or '--help' in opts:
        print(__doc__); return 2
    from ps2elf import Elf
    import symtab
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    elf = Elf(pos[0])
    names = symtab.load(root)
    db = load_db(root, elf, use_cache='--no-cache' not in opts)
    funcs, rng = resolve_filters(opts, elf, names)
    ints = lambda s: [int(x, 16) for x in s.split(',')]
    hits = query_field(
        db, parse_offsets(pos[1]), stores='--stores' in opts, loads='--loads' in opts,
        funcs=funcs, addr_range=rng, this='--this' in opts,
        array=ints(opts['--array']) if '--array' in opts else None,
        static=ints(opts['--static']) if '--static' in opts else None,
        adjust=int(opts.get('--adjust', '0'), 16), blocks='--blocks' in opts,
        certain='--certain' in opts, walk_limit=int(opts.get('--walk-limit', '200'), 16))
    for l in format_hits(hits, db, names, roots='--roots' in opts): print(l)
    return 0


if __name__ == '__main__':
    sys.exit(main())
