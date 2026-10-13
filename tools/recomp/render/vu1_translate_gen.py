"""vu1_translate_gen.py - the analysis and the code writer of vu1_translate.py (which has
the description of the whole and the instruction decoder).

Words used below.  A *pair* is one upper and one lower instruction, executed in one cycle.
A *block* is a run of pairs that is entered only at its first pair (its *leader*) and
executed to its end: it ends with a branch and its delay slot, with an end-bit pair and
the pair after it, by falling into the next leader, or by handing over to the interpreter
(*bail*).  An *entry* is a leader the function can be called at.
"""
import struct

from vu1_translate import (ARITH, BRANCH, CLIP_READERS, COND_BRANCH, DIVIDER, DYNAMIC_BRANCH, MAC_READERS, STATIC_BRANCH, U_ABS, U_ADD, U_BAD,
                           U_CLIP, U_FTOI, U_ITOF, U_MADD, U_MAX, U_MINI, U_MSUB, U_MUL, U_NOP, U_SUB, S_BC, S_I, S_Q, S_VEC, disassemble, fnv64,
                           upper_target)
import vu1_translate as T

L = T        # the L_ names


def is_clean_bits(u):
    e = u & 0x7F800000
    return e != 0x7F800000 and (e != 0 or (u & 0x7FFFFFFF) == 0)


class Block:
    def __init__(self, leader):
        self.leader = leader
        self.pairs = []         # absolute pair numbers in execution order
        self.term = None        # ('fall', m) ('cond', T, F) ('jump', T) ('jr',) ('end', pc) ('bail', n) ('leave', m)
        self.entry = False
        self.preds = []         # (block, ) predecessors
        self.clean_in = None    # {'vf': [mask]*32, 'i': bool}


class Program:
    def __init__(self, start, pairs, data, observed_entries, extra_entries):
        self.start, self.count, self.data = start, len(pairs), data
        self.P = {d.n: d for d in pairs}
        self.end = start + len(pairs)
        self.hash = fnv64(data)
        self.notes = []
        self.find_entries(observed_entries, extra_entries)
        self.find_blocks()
        self.find_clean()
        self.find_flags()

    # ---- entries ------------------------------------------------------------------------
    def find_entries(self, observed, extra):
        entries = {self.start}
        # a table of jumps at the start of a program (the game starts programs through one):
        # every pair of it can be started at
        n = self.start
        while n < self.end and self.P[n].uop == U_NOP and self.P[n].lop in (L.L_B, L.L_NOP) and not self.P[n].ibit:
            entries.add(n)
            n += 1
        if n - self.start < 4:       # not a table
            entries = {self.start}
        for a in list(observed) + list(extra):
            if self.start <= a < self.end:
                entries.add(a)
        self.entries = entries

    # ---- blocks -------------------------------------------------------------------------
    def bad(self, n):
        d = self.P[n]
        return d.uop == U_BAD or d.lop == L.L_BAD

    def shape(self, n):
        """How the pair at n ends a block: None (it does not), 'bail', 'branch', 'end'."""
        if n >= self.end:
            return 'leave'
        d = self.P[n]
        if self.bad(n):
            return 'bail'
        if d.lop in BRANCH:
            # the delay slot must be an ordinary pair; an end bit on either is left to the interpreter
            if d.ebit or n + 1 >= self.end or self.bad(n + 1) or self.P[n + 1].lop in BRANCH or self.P[n + 1].ebit:
                return 'bail'
            return 'branch'
        if d.ebit:
            if n + 1 >= self.end or self.bad(n + 1) or self.P[n + 1].lop in BRANCH:
                return 'bail'
            return 'end'
        return None

    def target(self, n):
        d = self.P[n]
        return (n + 1 + d.imm11) & 2047

    def find_blocks(self):
        leaders = set(self.entries)
        work = list(self.entries)
        walked = set()
        while work:
            n = work.pop()
            while n not in walked:
                walked.add(n)
                shape = self.shape(n)
                if shape == 'branch':
                    d = self.P[n]
                    new = []
                    if d.lop in STATIC_BRANCH:
                        new.append(self.target(n))
                        if d.lop in COND_BRANCH:
                            new.append(n + 2)
                    for m in new:
                        if self.start <= m < self.end and m not in leaders:
                            leaders.add(m)
                            work.append(m)
                    break
                if shape is not None:
                    break
                n += 1
        self.blocks = {}
        for leader in sorted(leaders):
            b = Block(leader)
            b.entry = leader in self.entries
            n = leader
            while True:
                shape = self.shape(n)
                if shape == 'leave':
                    b.term = ('leave', n)
                elif shape == 'bail':
                    b.term = ('bail', n)
                elif shape == 'branch':
                    d = self.P[n]
                    b.pairs += [n, n + 1]
                    if d.lop in DYNAMIC_BRANCH:
                        b.term = ('jr',)
                    elif d.lop in COND_BRANCH:
                        b.term = ('cond', self.target(n), n + 2)
                    else:
                        b.term = ('jump', self.target(n))
                elif shape == 'end':
                    b.pairs += [n, n + 1]
                    b.term = ('end', (n + 2) & 2047)
                else:
                    b.pairs.append(n)
                    n += 1
                    if n in leaders:
                        b.term = ('fall', n)
                    else:
                        continue
                break
            self.blocks[leader] = b
        for b in self.blocks.values():
            for m in self.successors(b):
                self.blocks[m].preds.append(b)

    def successors(self, b):
        t = b.term
        if t[0] in ('fall', 'jump'):
            out = [t[1]]
        elif t[0] == 'cond':
            out = [t[1], t[2]]
        else:
            out = []
        return [m for m in out if m in self.blocks]

    # ---- which float fields are known to be results of arithmetic ("clean") ----------------
    def clean_step(self, state, n):
        """state: {'vf': list of 32 masks (bit 8 = x), 'i': bool}; returns the state after pair n."""
        d = self.P[n]
        vf, i_clean = state['vf'], state['i']
        out = list(vf)
        # lower first (the upper half's result is written after it and wins)
        o = d.lop
        if o in (L.L_LQ, L.L_LQI, L.L_LQD, L.L_MFIR) and d.lt:
            out[d.lt] = vf[d.lt] & ~d.ldest & 15
        elif o == L.L_MOVE and d.lt:
            out[d.lt] = (vf[d.lt] & ~d.ldest & 15) | (vf[d.ls] & d.ldest)
        elif o == L.L_MR32 and d.lt:
            rotated = 0
            for k in range(4):
                if vf[d.ls] & (8 >> ((k + 1) & 3)):
                    rotated |= 8 >> k
            out[d.lt] = (vf[d.lt] & ~d.ldest & 15) | (rotated & d.ldest)
        target = upper_target(d)
        if target and target[0] == 'vf' and target[1]:
            t = target[1]
            if d.uop in ARITH or d.uop == U_ITOF:
                res = 15
            elif d.uop == U_ABS:
                res = vf[d.ufs]
            elif d.uop in (U_MAX, U_MINI):
                if d.usrc == S_VEC:
                    other = vf[d.uft]
                elif d.usrc == S_BC:
                    other = 15 if vf[d.uft] & (8 >> d.ubc) else 0
                else:
                    other = 15 if i_clean else 0
                res = vf[d.ufs] & other
            else:                       # FTOI: integers
                res = 0
            out[t] = (vf[t] & ~d.udest & 15) | (res & d.udest)
        out[0] = 15
        if d.ibit:
            i_clean = is_clean_bits(d.lower)
        return {'vf': out, 'i': i_clean}

    def find_clean(self):
        top = {'vf': [15] * 32, 'i': True}
        bottom = {'vf': [15] + [0] * 31, 'i': False}
        for b in self.blocks.values():
            b.clean_in = dict(bottom) if b.entry else {'vf': list(top['vf']), 'i': True}
        changed = True
        while changed:
            changed = False
            for leader in sorted(self.blocks):
                b = self.blocks[leader]
                state = b.clean_in
                for n in b.pairs:
                    state = self.clean_step(state, n)
                for m in self.successors(b):
                    s = self.blocks[m]
                    if s.entry:
                        continue
                    merged = {'vf': [x & y for x, y in zip(s.clean_in['vf'], state['vf'])], 'i': s.clean_in['i'] and state['i']}
                    if merged != s.clean_in:
                        s.clean_in = merged
                        changed = True

    # ---- flags: which instruction's result can a reader see? ------------------------------
    # A reader at cycle c sees the newest event (an arithmetic result for the MAC and status
    # flags, a CLIP or FCSET for the clip flags) that is at least four cycles old.  A pair
    # is one cycle, except that a divide or WAITQ waiting for an earlier divide adds cycles
    # at that pair - which makes everything from that pair back older.
    def walk_back(self, block, index, is_source, exit_walk=False):
        """The pairs whose event a reader placed just after position (block, index - 1) may see.
        Returns (definite, possible, unknown): `definite` are sources found four or more
        pairs back on a path (the walk stops there), `possible` are nearer ones that a wait
        may have aged, `unknown` says a path reached an entry (the event is from before the run)."""
        definite, possible = set(), set()
        unknown = [False]
        seen = set()
        stack = [(block, index, 1, exit_walk)]
        while stack:
            b, i, depth, stall = stack.pop()
            if i == 0:
                if b.entry:
                    unknown[0] = True
                for p in b.preds:
                    stack.append((p, len(p.pairs), depth, stall))
                continue
            n = b.pairs[i - 1]
            key = (b.leader, i, min(depth, 4), stall)
            if key in seen:
                continue
            seen.add(key)
            d = self.P[n]
            if d.lop in DIVIDER or d.lop == L.L_WAITQ:
                stall = True
            if is_source(d):
                if depth >= 4:
                    definite.add(n)
                    continue
                if stall:
                    possible.add(n)
            stack.append((b, i - 1, depth + 1, stall))
        return definite, possible, unknown[0]

    def find_flags(self):
        mac_source = lambda d: d.uop in ARITH
        clip_source = lambda d: d.uop == U_CLIP or d.lop == L.L_FCSET
        self.mac_ring, self.clip_ring = set(), set()        # pairs that must record their event
        self.mac_direct, self.clip_direct = {}, {}          # (leader, index) of a reader -> the one pair it sees
        self.mac_var, self.clip_var = set(), set()          # pairs whose result a reader takes straight from a variable
        self.reader_notes = []
        for b in self.blocks.values():
            for i, n in enumerate(b.pairs):
                d = self.P[n]
                for readers, source, ring, direct, var, name in ((MAC_READERS, mac_source, self.mac_ring, self.mac_direct, self.mac_var, 'mac'),
                                                                (CLIP_READERS, clip_source, self.clip_ring, self.clip_direct, self.clip_var, 'clip')):
                    if d.lop not in readers:
                        continue
                    definite, possible, unknown = self.walk_back(b, i, source)
                    if len(definite) == 1 and not possible and not unknown:
                        only = next(iter(definite))
                        direct[(b.leader, i)] = only
                        var.add(only)
                        self.reader_notes.append('%s reader %03x: sees %03x' % (name, n, only))
                    else:
                        ring |= definite | possible
                        self.reader_notes.append('%s reader %03x: history (%s%s%s)' % (name, n, ' '.join('%03x' % x for x in sorted(definite)),
                                                 ' maybe ' + ' '.join('%03x' % x for x in sorted(possible)) if possible else '', ' or earlier' if unknown else ''))
            # every way out of the translated code: whatever runs next may read the flags
            if b.term[0] in ('end', 'bail', 'jr', 'leave') or (b.term[0] in ('cond', 'jump') and len(self.successors(b)) < (2 if b.term[0] == 'cond' else 1)):
                for source, ring in ((mac_source, self.mac_ring), (clip_source, self.clip_ring)):
                    definite, possible, _unknown = self.walk_back(b, len(b.pairs), source, exit_walk=True)
                    ring |= definite | possible


# ---- the code -----------------------------------------------------------------------------
def hexfloat(value):
    return float.hex(value) + 'f'


class Writer:
    def __init__(self, prog, name):
        self.p = prog
        self.name = name
        self.lines = []
        self.vf_used, self.vf_written, self.vi_used, self.vi_written = set(), set(), set(), set()
        self.uses_acc = False

    def vf(self, r):
        self.vf_used.add(r)
        return 'vf%d' % r

    def vfw(self, r):
        self.vf_used.add(r)
        self.vf_written.add(r)
        return 'vf%d' % r

    def vi(self, r):
        if r == 0:
            return '0u'
        self.vi_used.add(r)
        return 'vi%d' % r

    def viw(self, r):
        self.vi_used.add(r)
        self.vi_written.add(r)
        return 'vi%d' % r

    def emit(self, text):
        self.lines.append(text)

    # one pair at position k of its block; `clean` is the state before it, `role` says what it is to the block
    def pair(self, b, k, clean, role, qstate):
        p = self.p
        n = b.pairs[k]
        d = p.P[n]
        now = 'cyc + %d' % k if k else 'cyc'
        out = []
        out.append('    { // %03x: %s' % (n, disassemble(d)))
        commit = None
        # ---- upper ----
        if d.uop not in (U_NOP, U_CLIP):
            def operand(reg, lanes_needed=15):
                return self.vf(reg)

            def brought_in(expr, is_clean):
                return ('v4_in_clean(%s)' if is_clean else 'v4_in(%s)') % expr
            # (Only the fields the instruction writes count: what it computes in the others
            # is thrown away, and the flags are read from the written fields alone.)
            fs = self.vf(d.ufs)
            fs_clean = (clean['vf'][d.ufs] & d.udest) == d.udest
            if d.usrc == S_VEC:
                other, other_clean = self.vf(d.uft), (clean['vf'][d.uft] & d.udest) == d.udest
            elif d.usrc == S_BC:
                other, other_clean = 'v4_bc(%s, %d)' % (self.vf(d.uft), d.ubc), bool(clean['vf'][d.uft] & (8 >> d.ubc))
            elif d.usrc == S_Q:
                # Q is always the flushed result of a divide: clean while results stay finite
                if qstate[0] == 'unknown':
                    out.append('      if (q_busy && %s >= q_ready) { q = q_next; q_busy = false; }' % now)
                elif qstate[0] == 'pending' and k >= qstate[1]:
                    out.append('      q = q_next; q_busy = false;')
                    qstate[0] = 'none'
                other, other_clean = 'v4_splat_f(q)', True
            else:
                other, other_clean = 'v4_splat(i_reg)', clean['i']
            op = d.uop
            if op in (U_ADD, U_SUB, U_MUL):
                fn = {U_ADD: 'v4_add', U_SUB: 'v4_sub', U_MUL: 'v4_mul'}[op]
                r = 'v4_out(%s(%s, %s))' % (fn, brought_in(fs, fs_clean), brought_in(other, other_clean))
            elif op in (U_MADD, U_MSUB):
                self.uses_acc = True
                r = 'v4_out(%s(acc, v4_out(v4_mul(%s, %s))))' % ('v4_add' if op == U_MADD else 'v4_sub', brought_in(fs, fs_clean), brought_in(other, other_clean))
            elif op == U_MAX:
                r = 'v4_max(%s, %s)' % (fs, other)
            elif op == U_MINI:
                r = 'v4_min(%s, %s)' % (fs, other)
            elif op == U_ITOF:
                r = 'v4_itof(%s, %s)' % (fs, hexfloat(1.0 / (1 << d.ubc)))
            elif op == U_FTOI:
                r = 'v4_ftoi(%s, %s)' % (brought_in(fs, fs_clean), hexfloat(float(1 << d.ubc)))
            elif op == U_ABS:
                r = 'v4_abs(%s)' % fs
            else:
                raise AssertionError('upper %d' % op)
            out.append('      V4 r_ = %s;' % r)
            if op in ARITH:
                if n in p.mac_ring:
                    out.append('      vu1_flag_push(v, %s, r_, %d);' % (now, d.udest))
                if n in p.mac_var:
                    out.append('      fv_%03x = r_;' % n)
            target = upper_target(d)
            if target[0] == 'acc':
                self.uses_acc = True
                commit = 'acc = r_;' if d.udest == 15 else 'acc = u_;'
                if d.udest != 15:
                    out.append('      V4 u_ = v4_blend(%d, r_, acc);' % d.udest)
            elif target[1]:
                t = target[1]
                if d.udest == 15:
                    commit = '%s = r_;' % self.vfw(t)
                else:
                    out.append('      V4 u_ = v4_blend(%d, r_, %s);' % (d.udest, self.vfw(t)))
                    commit = '%s = u_;' % self.vfw(t)
        elif d.uop == U_CLIP:
            out.append('      clip_now = vu1_clip_value(clip_now, %s, %s);' % (self.vf(d.ufs), self.vf(d.uft)))
            if n in p.clip_ring:
                out.append('      vu1_clip_push(v, %s, clip_now);' % now)
        # ---- lower ----
        o = d.lop
        imm = d.imm11 & 0xFFFFFFFF
        go = None

        def lanes_in(reg_expr_new, old):
            return reg_expr_new if d.ldest == 15 else 'v4_blend(%d, %s, %s)' % (d.ldest, reg_expr_new, old)
        if d.ibit or o == L.L_NOP or o == L.L_FSSET:
            pass
        elif o == L.L_LQ:
            if d.lt:
                out.append('      %s = %s;' % (self.vfw(d.lt), lanes_in('v4_load(vu1_at(data, %s + %uu))' % (self.vi(d.ls), imm), self.vf(d.lt))))
        elif o == L.L_SQ:
            m = 'vu1_at(data, %s + %uu)' % (self.vi(d.lt), imm)
            out.append('      { uint8_t* m_ = %s; v4_store(m_, %s); }' % (m, lanes_in(self.vf(d.ls), 'v4_load(m_)')))
        elif o == L.L_LQI:
            if d.lt:
                out.append('      %s = %s;' % (self.vfw(d.lt), lanes_in('v4_load(vu1_at(data, %s))' % self.vi(d.ls), self.vf(d.lt))))
            if d.ls:
                out.append('      %s = (%s + 1) & 0xFFFF;' % (self.viw(d.ls), self.vi(d.ls)))
        elif o == L.L_SQI:
            out.append('      { uint8_t* m_ = vu1_at(data, %s); v4_store(m_, %s); }' % (self.vi(d.lt), lanes_in(self.vf(d.ls), 'v4_load(m_)')))
            if d.lt:
                out.append('      %s = (%s + 1) & 0xFFFF;' % (self.viw(d.lt), self.vi(d.lt)))
        elif o == L.L_LQD:
            if d.ls:
                out.append('      %s = (%s - 1) & 0xFFFF;' % (self.viw(d.ls), self.vi(d.ls)))
            if d.lt:
                out.append('      %s = %s;' % (self.vfw(d.lt), lanes_in('v4_load(vu1_at(data, %s))' % self.vi(d.ls), self.vf(d.lt))))
        elif o == L.L_SQD:
            if d.lt:
                out.append('      %s = (%s - 1) & 0xFFFF;' % (self.viw(d.lt), self.vi(d.lt)))
            out.append('      { uint8_t* m_ = vu1_at(data, %s); v4_store(m_, %s); }' % (self.vi(d.lt), lanes_in(self.vf(d.ls), 'v4_load(m_)')))
        elif o in (L.L_ILW, L.L_ILWR):
            field = next((k2 for k2 in range(4) if d.ldest & (8 >> k2)), None)
            if field is not None and d.lt:
                address = '%s + %uu' % (self.vi(d.ls), imm) if o == L.L_ILW else self.vi(d.ls)
                out.append('      %s = vu1_ilw(vu1_at(data, %s), %d);' % (self.viw(d.lt), address, field))
        elif o in (L.L_ISW, L.L_ISWR):
            address = '%s + %uu' % (self.vi(d.ls), imm) if o == L.L_ISW else self.vi(d.ls)
            if d.ldest:
                out.append('      vu1_isw(vu1_at(data, %s), %d, %s);' % (address, d.ldest, self.vi(d.lt)))
        elif o == L.L_IADDIU:
            if d.lt:
                out.append('      %s = (%s + %uu) & 0xFFFF;' % (self.viw(d.lt), self.vi(d.ls), d.imm15))
        elif o == L.L_ISUBIU:
            if d.lt:
                out.append('      %s = (%s - %uu) & 0xFFFF;' % (self.viw(d.lt), self.vi(d.ls), d.imm15))
        elif o in (L.L_IADD, L.L_ISUB, L.L_IAND, L.L_IOR):
            if d.ld:
                sign = {L.L_IADD: '+', L.L_ISUB: '-', L.L_IAND: '&', L.L_IOR: '|'}[o]
                out.append('      %s = (%s %s %s) & 0xFFFF;' % (self.viw(d.ld), self.vi(d.ls), sign, self.vi(d.lt)))
        elif o == L.L_IADDI:
            if d.lt:
                imm5 = d.ld - 32 if d.ld & 16 else d.ld
                out.append('      %s = (%s + %uu) & 0xFFFF;' % (self.viw(d.lt), self.vi(d.ls), imm5 & 0xFFFFFFFF))
        elif o == L.L_FCSET:
            out.append('      clip_now = 0x%xu;' % d.imm24)
            if n in p.clip_ring:
                out.append('      vu1_clip_push(v, %s, clip_now);' % now)
        elif o in CLIP_READERS:
            source = p.clip_direct.get((b.leader, k))
            seen = 'cv_%03x' % source if source is not None else 'vu1_clip_seen(v, %s)' % now
            if o == L.L_FCAND:
                out.append('      %s = (%s & 0x%xu) ? 1 : 0;' % (self.viw(1), seen, d.imm24))
            elif o == L.L_FCOR:
                out.append('      %s = ((%s | 0x%xu) & 0xFFFFFF) == 0xFFFFFF ? 1 : 0;' % (self.viw(1), seen, d.imm24))
            elif o == L.L_FCEQ:
                out.append('      %s = (%s & 0xFFFFFF) == 0x%xu ? 1 : 0;' % (self.viw(1), seen, d.imm24))
            elif d.lt:
                out.append('      %s = %s & 0xFFF;' % (self.viw(d.lt), seen))
        elif o in MAC_READERS:
            source = p.mac_direct.get((b.leader, k))
            mac = 'vu1_mac_direct(fv_%03x, %d)' % (source, p.P[source].udest) if source is not None else 'vu1_mac_seen(v, %s)' % now
            if d.lt:
                if o in (L.L_FSAND, L.L_FSOR, L.L_FSEQ):
                    imm12 = ((d.lower >> 10) & 0x800) | (d.lower & 0x7FF)
                    status = 'vu1_status(%s)' % mac
                    expr = {L.L_FSAND: '%s & 0x%xu' % (status, imm12), L.L_FSOR: '(%s | 0x%xu) & 0xFFF' % (status, imm12),
                            L.L_FSEQ: '%s == 0x%xu ? 1 : 0' % (status, imm12)}[o]
                else:
                    expr = {L.L_FMAND: '%s & %s' % (mac, self.vi(d.ls)), L.L_FMOR: '(%s | %s) & 0xFFFF' % (mac, self.vi(d.ls)),
                            L.L_FMEQ: '(%s & 0xFFFF) == %s ? 1 : 0' % (mac, self.vi(d.ls))}[o]
                out.append('      %s = %s;' % (self.viw(d.lt), expr))
        elif o in BRANCH:
            if role == 'branch':
                if o == L.L_B or o == L.L_BAL:
                    go = None
                elif o in DYNAMIC_BRANCH:
                    out.append('      jump_ = %s;' % self.vi(d.ls))
                elif o == L.L_IBEQ:
                    go = '%s == %s' % (self.vi(d.lt), self.vi(d.ls))
                elif o == L.L_IBNE:
                    go = '%s != %s' % (self.vi(d.lt), self.vi(d.ls))
                else:
                    sign = {L.L_IBLTZ: '<', L.L_IBGTZ: '>', L.L_IBLEZ: '<=', L.L_IBGEZ: '>='}[o]
                    go = '(int16_t)%s %s 0' % (self.vi(d.ls), sign)
                if go:
                    out.append('      go_ = %s;' % go)
            if o in (L.L_BAL, L.L_JALR) and d.lt:
                out.append('      %s = %uu;' % (self.viw(d.lt), (n + 2) & 0xFFFF))
        elif o == L.L_MOVE:
            if d.lt:
                out.append('      %s = %s;' % (self.vfw(d.lt), lanes_in(self.vf(d.ls), self.vf(d.lt))))
        elif o == L.L_MR32:
            if d.lt:
                out.append('      %s = %s;' % (self.vfw(d.lt), lanes_in('v4_mr32(%s)' % self.vf(d.ls), self.vf(d.lt))))
        elif o == L.L_MTIR:
            if d.lt:
                out.append('      %s = v4_get(%s, %d) & 0xFFFF;' % (self.viw(d.lt), self.vf(d.ls), d.fsf))
        elif o == L.L_MFIR:
            if d.lt:
                out.append('      %s = %s;' % (self.vfw(d.lt), lanes_in('v4_splat((uint32_t)(int32_t)(int16_t)%s)' % self.vi(d.ls), self.vf(d.lt))))
        elif o == L.L_XTOP:
            if d.lt:
                out.append('      %s = top & 0xFFFF;' % self.viw(d.lt))
        elif o == L.L_XITOP:
            if d.lt:
                out.append('      %s = itop & 0x3FF;' % self.viw(d.lt))
        elif o in DIVIDER or o == L.L_WAITQ:
            # a divide still in flight is waited for
            if qstate[0] != 'none':
                out.append('      if (q_busy) { if (q_ready > %s) cyc = q_ready - %d; q = q_next; q_busy = false; }' % (now, k))
            if o == L.L_WAITQ:
                qstate[0] = 'none'
            else:
                fs, ft = 'v4_get(%s, %d)' % (self.vf(d.ls), d.fsf), 'v4_get(%s, %d)' % (self.vf(d.lt), d.ftf)
                call = {L.L_DIV: 'vu1_div(%s, %s)' % (fs, ft), L.L_SQRT: 'vu1_sqrt(%s)' % ft, L.L_RSQRT: 'vu1_rsqrt(%s, %s)' % (fs, ft)}[o]
                latency = 13 if o == L.L_RSQRT else 7
                out.append('      q_next = %s; q_ready = %s + %d; q_busy = true;' % (call, now, latency))
                qstate[0], qstate[1] = 'pending', k + latency
        elif o == L.L_XGKICK:
            out.append('      vu1_fast_kick(v, %s & 0x3FF);' % self.vi(d.ls))
        else:
            raise AssertionError('lower %d' % o)
        if d.ibit:
            out.append('      i_reg = 0x%08xu;' % d.lower)
        if commit:
            out.append('      ' + commit)
        # the clip flags as they are after this pair, for a reader that takes them from here
        if n in p.clip_var:
            out.append('      cv_%03x = clip_now;' % n)
        out.append('    }')
        # a pair that does nothing needs no braces
        if len(out) == 2:
            out = ['    // %03x: %s' % (n, disassemble(d))]
        self.lines += out

    def goto(self, m):
        if m in self.p.blocks:
            return 'goto L_%03x;' % m
        return '{ result = %d; goto leave; }' % (m & 2047)

    def block(self, b):
        p = self.p
        self.emit('L_%03x:' % b.leader)
        if not b.pairs:
            pass
        clean = b.clean_in
        qstate = ['unknown', 0]
        t = b.term
        for k, n in enumerate(b.pairs):
            role = 'normal'
            if t[0] in ('cond', 'jump', 'jr') and k == len(b.pairs) - 2:
                role = 'branch'
            self.pair(b, k, clean, role, qstate)
            clean = p.clean_step(clean, n)
        if b.pairs:
            self.emit('    cyc += %d; pairs += %d;' % (len(b.pairs), len(b.pairs)))
        if t[0] == 'fall':
            self.emit('    ' + self.goto(t[1]))
        elif t[0] == 'jump':
            self.emit('    ' + self.back_edge(b, t[1]) + self.goto(t[1]))
        elif t[0] == 'cond':
            self.emit('    if (go_) { ' + self.back_edge(b, t[1]) + self.goto(t[1]) + ' }')
            self.emit('    ' + self.goto(t[2]))
        elif t[0] == 'jr':
            self.emit('    at = jump_ & 2047; goto dispatch;')
        elif t[0] == 'end':
            self.emit('    v.pc = %d; result = -1; goto leave;' % t[1])
        elif t[0] in ('bail', 'leave'):
            self.emit('    result = %d; goto leave;' % (t[1] & 2047))

    def back_edge(self, b, target):
        # a program that never ends is given to the interpreter, which gives up after a while
        if target in self.p.blocks and target <= b.leader:
            return 'if (pairs > 3000000) { result = %d; goto leave; } ' % target
        return ''

    def function(self):
        p = self.p
        for leader in sorted(p.blocks):
            self.block(p.blocks[leader])
        body = self.lines
        head = []
        head.append('// The program at pair 0x%03x, %d pairs: %d blocks, %d entries.' % (p.start, p.count, len(p.blocks), len(p.entries)))
        for note in p.reader_notes:
            head.append('//   ' + note)
        head.append('//   results recorded for readers elsewhere: mac %s; clip %s' % (' '.join('%03x' % n for n in sorted(p.mac_ring)) or '-',
                                                                                    ' '.join('%03x' % n for n in sorted(p.clip_ring)) or '-'))
        head.append('static int %s(Vu1& v, uint32_t at) {' % self.name)
        head.append('    switch (at) {')
        entries = sorted(e for e in p.entries if e in p.blocks)
        head.append('    ' + ' '.join('case %d:' % e for e in entries) + ' break;')
        head.append('    default: return (int)at;                        // not an entry this was made for: the interpreter')
        head.append('    }')
        head.append('    uint8_t* const data = v.data;')
        head.append('    const uint32_t top = v.top, itop = v.itop;')
        head.append('    const V4 vf0 = v4_load((const uint8_t*)v.vf[0].u);')
        for r in sorted(self.vf_used - {0}):
            head.append('    V4 vf%d = v4_load((const uint8_t*)v.vf[%d].u);' % (r, r))
        head.append('    V4 acc = v4_load((const uint8_t*)v.acc.u);')
        for r in sorted(self.vi_used):
            head.append('    uint32_t vi%d = v.vi[%d];' % (r, r))
        head.append('    float q = v.q, q_next = v.q_next;')
        head.append('    uint32_t i_reg; memcpy(&i_reg, &v.i_reg, 4);')
        head.append('    uint64_t cyc = v.cyc, q_ready = v.q_ready, pairs = 0;')
        head.append('    bool q_busy = v.q_busy, go_ = false;')
        head.append('    uint32_t clip_now = v.clip_now, jump_ = 0;')
        head.append('    int result = -1;')
        for n in sorted(p.mac_var):
            head.append('    V4 fv_%03x = v4_splat(0);' % n)
        for n in sorted(p.clip_var):
            head.append('    uint32_t cv_%03x = 0;' % n)
        head.append('    (void)top; (void)itop; (void)go_; (void)jump_; (void)vf0;')
        head.append('    goto dispatch;')
        head.append('dispatch:')
        head.append('    switch (at) {')
        for e in entries:
            head.append('    case %d: goto L_%03x;' % (e, e))
        head.append('    default: result = (int)at; goto leave;')
        head.append('    }')
        tail = ['leave:']
        for r in sorted(self.vf_written - {0}):
            tail.append('    v4_store((uint8_t*)v.vf[%d].u, vf%d);' % (r, r))
        tail.append('    v4_store((uint8_t*)v.acc.u, acc);')
        for r in sorted(self.vi_written):
            tail.append('    v.vi[%d] = (uint16_t)vi%d;' % (r, r))
        tail.append('    v.q = q; v.q_next = q_next; v.q_ready = q_ready; v.q_busy = q_busy;')
        tail.append('    memcpy(&v.i_reg, &i_reg, 4);')
        tail.append('    v.cyc = cyc; v.instructions += pairs; v.clip_now = clip_now;')
        tail.append('    return result;')
        tail.append('}')
        return '\n'.join(head + body + tail) + '\n'


def generate(programs, observed_entries, extra_entries=(), report=False):
    out = ['// GENERATED by tools/recomp/render/vu1_translate.py from the game\'s VU1 microprograms: derived from the',
           '// game, keep under local/.  Compile like vu1.cpp: -frounding-math -ffp-contract=off.',
           '#include "vu1_fast.h"', '', 'namespace render {', '']
    table = []
    for start, pairs, data in programs:
        prog = Program(start, pairs, data, observed_entries, extra_entries)
        name = 'vu1_fast_run_%03x_%016x' % (start, prog.hash)
        writer = Writer(prog, name)
        out.append(writer.function())
        table.append('    {%d, %d, 0x%016xull, %s},' % (start, prog.count, prog.hash, name))
        if report:
            reached = sum(len(b.pairs) for b in prog.blocks.values())
            bails = sorted(b.term[1] for b in prog.blocks.values() if b.term[0] == 'bail')
            jrs = sum(1 for b in prog.blocks.values() if b.term[0] == 'jr')
            print('program at 0x%03x: %d pairs, %d blocks (%d pairs in them), %d entries, %d computed jumps, handed to the interpreter at: %s' % (
                start, prog.count, len(prog.blocks), reached, len(prog.entries), jrs, ' '.join('%03x' % n for n in bails) or 'nowhere'))
            for note in prog.reader_notes:
                print('   ' + note)
            print('   results recorded: mac %d pairs, clip %d pairs' % (len(prog.mac_ring), len(prog.clip_ring)))
    out.append('extern const Vu1Program vu1_fast_programs[] = {')
    out += table
    out.append('};')
    out.append('extern const uint32_t vu1_fast_program_count = %d;' % len(table))
    out += ['', '}  // namespace render', '']
    return '\n'.join(out)
